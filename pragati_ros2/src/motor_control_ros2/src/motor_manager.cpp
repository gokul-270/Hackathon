/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * MotorManager implementation — centralized motor array ownership, CAN
 * interface lifecycle, and motor-level operations.
 *
 * Part of mg6010-decomposition Phase 2 (Step 5).
 */

#include "motor_control_ros2/motor_manager.hpp"

#include <chrono>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "motor_control_ros2/mg6010_controller.hpp"
#include "motor_control_ros2/mg6010_can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

namespace motor_control_ros2
{

// ─── Primary constructor: reads ROS2 params, creates CAN + motors ────────────

MotorManager::MotorManager(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  std::shared_ptr<CANInterface> can_interface)
: node_(std::move(node))
{
  if (!node_) {
    throw std::invalid_argument("MotorManager: node must not be null");
  }

  // Read motor configuration from ROS2 parameters
  auto motor_ids_param = node_->get_parameter("motor_ids").as_integer_array();
  auto joint_names_param = node_->get_parameter("joint_names").as_string_array();
  auto homing_positions_param = node_->get_parameter("homing_positions").as_double_array();
  auto transmission_factors_param = node_->get_parameter("transmission_factors").as_double_array();
  auto internal_gear_ratios_param = node_->get_parameter("internal_gear_ratios").as_double_array();
  auto directions_param = node_->get_parameter("directions").as_integer_array();
  auto min_positions_param = node_->get_parameter("min_positions").as_double_array();
  auto max_positions_param = node_->get_parameter("max_positions").as_double_array();

  motor_count_ = motor_ids_param.size();

  if (motor_count_ == 0) {
    throw std::invalid_argument("MotorManager: zero motors configured (motor_ids is empty)");
  }

  if (!joint_names_param.empty() && joint_names_param.size() != motor_count_) {
    throw std::invalid_argument(
      "MotorManager: mismatched parameter array lengths — motor_ids has " +
      std::to_string(motor_count_) + " entries but joint_names has " +
      std::to_string(joint_names_param.size()));
  }

  // CAN interface: use injected or create from params
  if (can_interface) {
    can_interface_ = std::move(can_interface);
  } else {
    bool simulation_mode = node_->get_parameter("simulation_mode").as_bool();
    std::string interface_name = node_->get_parameter("interface_name").as_string();
    int baud_rate = static_cast<int>(node_->get_parameter("baud_rate").as_int());

    if (simulation_mode) {
      auto sim_can = std::make_shared<test::ConfigurableMockCANInterface>();
      sim_can->initialize("sim_can0", baud_rate);
      can_interface_ = sim_can;
    } else {
      auto hw_can = std::make_shared<MG6010CANInterface>();
      if (!hw_can->initialize(interface_name, baud_rate)) {
        RCLCPP_ERROR(node_->get_logger(),
          "MotorManager: CAN interface init failed on %s: %s",
          interface_name.c_str(), hw_can->get_last_error().c_str());
      }
      can_interface_ = hw_can;
    }
  }

  // Size all vectors
  controllers_.resize(motor_count_);
  joint_names_.resize(motor_count_);
  homing_positions_.resize(motor_count_, 0.0);
  motor_available_ = std::vector<std::atomic<bool>>(motor_count_);
  motor_enabled_ = std::vector<std::atomic<bool>>(motor_count_);

  // Initialize per-motor state (all false initially)
  for (size_t i = 0; i < motor_count_; ++i) {
    motor_available_[i].store(false);
    motor_enabled_[i].store(false);
  }

  // Populate joint names and homing positions
  for (size_t i = 0; i < motor_count_; ++i) {
    joint_names_[i] = (i < joint_names_param.size())
      ? joint_names_param[i]
      : "joint_" + std::to_string(i);

    homing_positions_[i] = (i < homing_positions_param.size())
      ? homing_positions_param[i]
      : 0.0;
  }

  // Create motor controllers
  bool auto_recover = node_->get_parameter("auto_recover_errors").as_bool();

  for (size_t i = 0; i < motor_count_; ++i) {
    uint8_t can_id = static_cast<uint8_t>(motor_ids_param[i]);
    double transmission_factor = (i < transmission_factors_param.size())
      ? transmission_factors_param[i] : 1.0;
    double internal_gear_ratio = (i < internal_gear_ratios_param.size())
      ? internal_gear_ratios_param[i] : 1.0;
    int direction = (i < directions_param.size())
      ? static_cast<int>(directions_param[i]) : 1;

    MotorConfiguration config;
    config.motor_type = "mg6010";
    config.joint_name = joint_names_[i];
    config.can_id = can_id;
    config.axis_id = static_cast<uint8_t>(i);
    config.transmission_factor = transmission_factor;
    config.joint_offset = 0.0;
    config.encoder_offset = 0.0;
    config.encoder_resolution = 16384;
    config.direction = direction;
    config.motor_params["internal_gear_ratio"] = internal_gear_ratio;
    config.motor_params["auto_recover_errors"] = auto_recover ? 1.0 : 0.0;
    config.p_gain = 100.0;
    config.v_gain = 0.5;
    config.v_int_gain = 1.0;
    config.current_limit = 8.0;
    config.velocity_limit = 15.0;

    // Safety limits from params
    if (i < min_positions_param.size()) {
      config.limits.position_min = min_positions_param[i];
    }
    if (i < max_positions_param.size()) {
      config.limits.position_max = max_positions_param[i];
    }
    config.limits.velocity_max = 15.0;
    config.limits.current_max = 8.0;
    config.limits.temperature_max = 85.0;

    auto controller = std::make_shared<MG6010Controller>();
    if (!controller->initialize(config, can_interface_)) {
      RCLCPP_ERROR(node_->get_logger(),
        "MotorManager: failed to initialize motor %d (%s)",
        can_id, joint_names_[i].c_str());
      controllers_[i] = nullptr;
      continue;
    }

    controllers_[i] = controller;
    motor_available_[i].store(true);
    motor_enabled_[i].store(true);

    RCLCPP_INFO(node_->get_logger(),
      "MotorManager: motor %d initialized: %s", can_id, joint_names_[i].c_str());
  }
}

// ─── Test-only constructor: inject pre-built controllers ─────────────────────

MotorManager::MotorManager(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  std::shared_ptr<CANInterface> can_interface,
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers,
  std::vector<std::string> joint_names,
  std::vector<double> homing_positions)
: node_(std::move(node)),
  can_interface_(std::move(can_interface)),
  controllers_(std::move(controllers)),
  joint_names_(std::move(joint_names)),
  homing_positions_(std::move(homing_positions))
{
  if (!node_) {
    throw std::invalid_argument("MotorManager: node must not be null");
  }
  if (!can_interface_) {
    throw std::invalid_argument("MotorManager: CAN interface must not be null (test constructor)");
  }
  if (controllers_.empty()) {
    throw std::invalid_argument("MotorManager: zero motors provided (empty controllers vector)");
  }
  if (joint_names_.size() != controllers_.size()) {
    throw std::invalid_argument(
      "MotorManager: mismatched array lengths — controllers has " +
      std::to_string(controllers_.size()) + " entries but joint_names has " +
      std::to_string(joint_names_.size()));
  }
  if (homing_positions_.size() != controllers_.size()) {
    throw std::invalid_argument(
      "MotorManager: mismatched array lengths — controllers has " +
      std::to_string(controllers_.size()) + " entries but homing_positions has " +
      std::to_string(homing_positions_.size()));
  }

  motor_count_ = controllers_.size();

  // Initialize per-motor state (all false initially — caller must setAvailable)
  motor_available_ = std::vector<std::atomic<bool>>(motor_count_);
  motor_enabled_ = std::vector<std::atomic<bool>>(motor_count_);
  for (size_t i = 0; i < motor_count_; ++i) {
    motor_available_[i].store(false);
    motor_enabled_[i].store(false);
  }
}

// ─── Motor Access ────────────────────────────────────────────────────────────

std::shared_ptr<MotorControllerInterface> MotorManager::getMotor(size_t idx) const
{
  if (idx >= motor_count_) {
    return nullptr;
  }
  return controllers_[idx];
}

std::shared_ptr<MotorControllerInterface> MotorManager::getMotorByCanId(uint8_t can_id) const
{
  for (size_t i = 0; i < motor_count_; ++i) {
    if (controllers_[i]) {
      auto config = controllers_[i]->get_configuration();
      if (config.can_id == can_id) {
        return controllers_[i];
      }
    }
  }
  return nullptr;
}

std::shared_ptr<MotorControllerInterface> MotorManager::getMotorByJointName(
  const std::string & name) const
{
  for (size_t i = 0; i < motor_count_; ++i) {
    if (joint_names_[i] == name) {
      return controllers_[i];
    }
  }
  return nullptr;
}

// ─── Bulk Operations ─────────────────────────────────────────────────────────

size_t MotorManager::enableAll()
{
  size_t count = 0;
  for (size_t i = 0; i < motor_count_; ++i) {
    if (!motor_available_[i].load() || !controllers_[i]) {
      continue;
    }
    try {
      if (controllers_[i]->set_enabled(true)) {
        ++count;
      } else {
        RCLCPP_WARN(node_->get_logger(),
          "MotorManager::enableAll: motor %zu returned false", i);
      }
    } catch (const std::exception & e) {
      RCLCPP_ERROR(node_->get_logger(),
        "MotorManager::enableAll: motor %zu exception: %s", i, e.what());
    }
  }
  return count;
}

size_t MotorManager::disableAll()
{
  size_t count = 0;
  for (size_t i = 0; i < motor_count_; ++i) {
    if (!motor_available_[i].load() || !controllers_[i]) {
      continue;
    }
    try {
      if (controllers_[i]->set_enabled(false)) {
        ++count;
      } else {
        RCLCPP_WARN(node_->get_logger(),
          "MotorManager::disableAll: motor %zu returned false", i);
      }
    } catch (const std::exception & e) {
      RCLCPP_ERROR(node_->get_logger(),
        "MotorManager::disableAll: motor %zu exception: %s", i, e.what());
    }
  }
  return count;
}

size_t MotorManager::stopAll()
{
  size_t count = 0;
  for (size_t i = 0; i < motor_count_; ++i) {
    if (!motor_available_[i].load() || !controllers_[i]) {
      continue;
    }
    try {
      if (controllers_[i]->stop()) {
        ++count;
      } else {
        RCLCPP_WARN(node_->get_logger(),
          "MotorManager::stopAll: motor %zu returned false", i);
      }
    } catch (const std::exception & e) {
      RCLCPP_ERROR(node_->get_logger(),
        "MotorManager::stopAll: motor %zu exception: %s", i, e.what());
    }
  }
  return count;
}

size_t MotorManager::emergencyStopAll()
{
  size_t count = 0;
  std::vector<size_t> failed_motor_ids;

  for (size_t i = 0; i < motor_count_; ++i) {
    if (!motor_available_[i].load() || !controllers_[i]) {
      continue;
    }

    bool stopped = false;
    static constexpr int MAX_RETRIES = 3;
    // Exponential backoff delays: 10ms, 100ms, 1000ms
    static constexpr std::chrono::milliseconds BACKOFF_DELAYS[] = {
      std::chrono::milliseconds(10),
      std::chrono::milliseconds(100),
      std::chrono::milliseconds(1000)
    };

    for (int attempt = 0; attempt < MAX_RETRIES && !stopped; ++attempt) {
      try {
        stopped = controllers_[i]->emergency_stop();
        if (!stopped) {
          RCLCPP_ERROR(node_->get_logger(),
            "emergencyStopAll: motor %zu returned false (attempt %d/%d)",
            i, attempt + 1, MAX_RETRIES);
        }
      } catch (const std::exception & e) {
        RCLCPP_ERROR(node_->get_logger(),
          "emergencyStopAll: motor %zu exception (attempt %d/%d): %s",
          i, attempt + 1, MAX_RETRIES, e.what());
      }

      if (!stopped && attempt < MAX_RETRIES - 1) {
        // BLOCKING_SLEEP_OK: e-stop retry backoff, safety-critical path — reviewed 2026-03-14
        std::this_thread::sleep_for(BACKOFF_DELAYS[attempt]);
      }
    }

    if (stopped) {
      ++count;
    } else {
      failed_motor_ids.push_back(i);
      RCLCPP_FATAL(node_->get_logger(),
        "emergencyStopAll: FAILED to stop motor %zu (%s) after %d attempts",
        i,
        (i < joint_names_.size() ? joint_names_[i].c_str() : "unknown"),
        MAX_RETRIES);
    }
  }

  if (!failed_motor_ids.empty()) {
    std::string ids_str;
    for (size_t id : failed_motor_ids) {
      if (!ids_str.empty()) ids_str += ", ";
      ids_str += std::to_string(id);
    }
    RCLCPP_FATAL(node_->get_logger(),
      "emergencyStopAll: %zu/%zu motors FAILED to stop (IDs: %s) — SYSTEM UNSAFE",
      failed_motor_ids.size(), motor_count_, ids_str.c_str());
  }

  return count;
}

// ─── State Management ────────────────────────────────────────────────────────

bool MotorManager::isAvailable(size_t idx) const
{
  if (idx >= motor_count_) {
    return false;
  }
  return motor_available_[idx].load();
}

bool MotorManager::isEnabled(size_t idx) const
{
  if (idx >= motor_count_) {
    return false;
  }
  return motor_enabled_[idx].load();
}

void MotorManager::setAvailable(size_t idx, bool available)
{
  if (idx >= motor_count_) {
    return;
  }
  motor_available_[idx].store(available);
}

void MotorManager::setEnabled(size_t idx, bool enabled)
{
  if (idx >= motor_count_) {
    return;
  }
  motor_enabled_[idx].store(enabled);
}

size_t MotorManager::motorCount() const
{
  return motor_count_;
}

// ─── Joint Configuration ─────────────────────────────────────────────────────

std::string MotorManager::getJointName(size_t idx) const
{
  if (idx >= motor_count_) {
    return "";
  }
  return joint_names_[idx];
}

double MotorManager::getHomingPosition(size_t idx) const
{
  if (idx >= motor_count_) {
    return 0.0;
  }
  return homing_positions_[idx];
}

const std::vector<std::string> & MotorManager::getJointNames() const
{
  return joint_names_;
}

// ─── CAN Interface ───────────────────────────────────────────────────────────

std::shared_ptr<CANInterface> MotorManager::getCANInterface() const
{
  return can_interface_;
}

}  // namespace motor_control_ros2
