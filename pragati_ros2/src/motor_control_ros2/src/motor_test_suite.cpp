/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * MotorTestSuite implementation — extracted from MG6010ControllerNode.
 *
 * Each method is a behavioral-equivalent copy of the original inline
 * implementation in mg6010_controller_node.cpp. Log messages, error
 * handling, and CAN interaction patterns are preserved identically.
 */

#include "motor_control_ros2/motor_test_suite.hpp"

#include <chrono>
#include <cmath>
#include <sstream>
#include <thread>

namespace motor_control_ros2
{

// ════════════════════════════════════════════════════════════════════════
// Construction
// ════════════════════════════════════════════════════════════════════════

MotorTestSuite::MotorTestSuite(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  std::shared_ptr<CANInterface> can_interface,
  std::vector<std::shared_ptr<MotorControllerInterface>> & controllers,
  std::array<std::atomic<bool>, MAX_MOTORS> & motor_available,
  std::vector<std::string> & joint_names)
: node_(std::move(node)),
  can_interface_(std::move(can_interface)),
  controllers_(controllers),
  motor_available_(motor_available),
  joint_names_(joint_names)
{
  if (!node_) {
    throw std::invalid_argument("MotorTestSuite: node must not be null");
  }
  if (!can_interface_) {
    throw std::invalid_argument("MotorTestSuite: can_interface must not be null");
  }
}

// ════════════════════════════════════════════════════════════════════════
// Private helper: findMotorByCanId
// ════════════════════════════════════════════════════════════════════════

size_t MotorTestSuite::findMotorByCanId(uint8_t motor_id) const
{
  for (size_t i = 0; i < controllers_.size(); ++i) {
    if (controllers_[i] == nullptr) {
      continue;
    }
    if (controllers_[i]->get_configuration().can_id == motor_id) {
      return i;
    }
  }
  return SIZE_MAX;
}

// ════════════════════════════════════════════════════════════════════════
// Legacy test methods
// ════════════════════════════════════════════════════════════════════════

void MotorTestSuite::test_status(size_t motor_idx)
{
  if (motor_idx >= controllers_.size()) {
    return;
  }

  RCLCPP_INFO(node_->get_logger(), "═══ Test: Read Motor Status ═══");

  auto status = controllers_[motor_idx]->get_status();

  RCLCPP_INFO(node_->get_logger(), "Status Results:");
  RCLCPP_INFO(
    node_->get_logger(), "  Hardware Connected: %s",
    status.hardware_connected ? "Yes" : "No");
  RCLCPP_INFO(
    node_->get_logger(), "  Motor Enabled: %s",
    status.motor_enabled ? "Yes" : "No");
  RCLCPP_INFO(
    node_->get_logger(), "  Encoder Ready: %s",
    status.encoder_ready ? "Yes" : "No");
  RCLCPP_INFO(node_->get_logger(), "  Temperature: %.1f °C", status.temperature);
  RCLCPP_INFO(node_->get_logger(), "  Voltage: %.1f V", status.voltage);
  RCLCPP_INFO(node_->get_logger(), "  Current: %.2f A", status.current);
  RCLCPP_INFO(node_->get_logger(), "  Health Score: %.2f", status.health_score);

  if (!status.warnings.empty()) {
    RCLCPP_WARN(node_->get_logger(), "Warnings:");
    for (const auto & warning : status.warnings) {
      RCLCPP_WARN(node_->get_logger(), "  - %s", warning.c_str());
    }
  }

  if (status.current_error.category != ErrorFramework::ErrorCategory::NONE) {
    RCLCPP_ERROR(
      node_->get_logger(), "Error: %s",
      status.current_error.message.c_str());
  }
}

void MotorTestSuite::test_enable(size_t motor_idx)
{
  if (motor_idx >= controllers_.size()) {
    return;
  }

  RCLCPP_INFO(node_->get_logger(), "═══ Test: Motor Enable/Disable ═══");

  RCLCPP_INFO(node_->get_logger(), "Enabling motor...");
  if (!controllers_[motor_idx]->set_enabled(true)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ Failed to enable motor");
    return;
  }
  RCLCPP_INFO(node_->get_logger(), "✅ Motor enabled successfully");

  std::this_thread::sleep_for(std::chrono::seconds(2));

  test_status(motor_idx);

  std::this_thread::sleep_for(std::chrono::seconds(1));

  RCLCPP_INFO(node_->get_logger(), "Disabling motor...");
  if (!controllers_[motor_idx]->set_enabled(false)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ Failed to disable motor");
    return;
  }
  RCLCPP_INFO(node_->get_logger(), "✅ Motor disabled successfully");
}

void MotorTestSuite::test_position(size_t motor_idx, double target_position)
{
  if (motor_idx >= controllers_.size()) {
    return;
  }

  RCLCPP_INFO(node_->get_logger(), "═══ Test: Position Control ═══");
  RCLCPP_INFO(
    node_->get_logger(),
    "Target Position: %.3f rad (%.1f degrees)",
    target_position, target_position * 180.0 / M_PI);

  if (!controllers_[motor_idx]->set_enabled(true)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ Failed to enable motor");
    return;
  }
  RCLCPP_INFO(node_->get_logger(), "✅ Motor enabled");

  std::this_thread::sleep_for(std::chrono::milliseconds(500));

  RCLCPP_INFO(node_->get_logger(), "Sending position command...");
  if (!controllers_[motor_idx]->set_position(target_position, 0.0, 0.0)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ Failed to send position command");
    controllers_[motor_idx]->set_enabled(false);
    return;
  }
  RCLCPP_INFO(node_->get_logger(), "✅ Position command sent");

  // Monitor position for 3 seconds (30 x 100ms)
  for (int i = 0; i < 30; ++i) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    double current_pos = controllers_[motor_idx]->get_position();
    double current_vel = controllers_[motor_idx]->get_velocity();
    double error = target_position - current_pos;
    RCLCPP_INFO(
      node_->get_logger(),
      "Position: %.3f rad, Velocity: %.3f rad/s, Error: %.3f rad",
      current_pos, current_vel, error);
  }

  controllers_[motor_idx]->set_enabled(false);
  RCLCPP_INFO(node_->get_logger(), "✅ Motor disabled");
}

void MotorTestSuite::test_velocity(size_t motor_idx, double target_velocity)
{
  if (motor_idx >= controllers_.size()) {
    return;
  }

  RCLCPP_INFO(node_->get_logger(), "═══ Test: Velocity Control ═══");
  RCLCPP_INFO(
    node_->get_logger(), "Target Velocity: %.3f rad/s", target_velocity);

  if (!controllers_[motor_idx]->set_enabled(true)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ Failed to enable motor");
    return;
  }
  RCLCPP_INFO(node_->get_logger(), "✅ Motor enabled");

  std::this_thread::sleep_for(std::chrono::milliseconds(500));

  RCLCPP_INFO(node_->get_logger(), "Sending velocity command...");
  if (!controllers_[motor_idx]->set_velocity(target_velocity, 0.0)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ Failed to send velocity command");
    controllers_[motor_idx]->set_enabled(false);
    return;
  }
  RCLCPP_INFO(node_->get_logger(), "✅ Velocity command sent");

  // Monitor velocity for 3 seconds (30 x 100ms)
  for (int i = 0; i < 30; ++i) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    double current_pos = controllers_[motor_idx]->get_position();
    double current_vel = controllers_[motor_idx]->get_velocity();
    RCLCPP_INFO(
      node_->get_logger(),
      "Position: %.3f rad, Velocity: %.3f rad/s",
      current_pos, current_vel);
  }

  // Stop motor
  controllers_[motor_idx]->set_velocity(0.0, 0.0);
  std::this_thread::sleep_for(std::chrono::milliseconds(500));

  controllers_[motor_idx]->set_enabled(false);
  RCLCPP_INFO(node_->get_logger(), "✅ Motor disabled");
}

void MotorTestSuite::test_full_sequence(size_t motor_idx, double target_position)
{
  if (motor_idx >= controllers_.size()) {
    return;
  }

  RCLCPP_INFO(node_->get_logger(), "═══ Test: Full Integration Sequence ═══");

  // Step 1: Initial Status
  RCLCPP_INFO(node_->get_logger(), "\n--- Step 1: Initial Status ---");
  test_status(motor_idx);
  std::this_thread::sleep_for(std::chrono::seconds(1));

  // Step 2: Enable Motor
  RCLCPP_INFO(node_->get_logger(), "\n--- Step 2: Enable Motor ---");
  if (!controllers_[motor_idx]->set_enabled(true)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ Failed to enable motor");
    return;
  }
  RCLCPP_INFO(node_->get_logger(), "✅ Motor enabled");
  std::this_thread::sleep_for(std::chrono::seconds(1));

  // Step 3: Position Control
  RCLCPP_INFO(node_->get_logger(), "\n--- Step 3: Position Control ---");
  RCLCPP_INFO(
    node_->get_logger(), "Moving to %.3f rad...", target_position);
  controllers_[motor_idx]->set_position(target_position, 0.0, 0.0);
  std::this_thread::sleep_for(std::chrono::seconds(2));
  double final_pos = controllers_[motor_idx]->get_position();
  RCLCPP_INFO(
    node_->get_logger(), "Final position: %.3f rad", final_pos);

  // Step 4: Final Status
  RCLCPP_INFO(node_->get_logger(), "\n--- Step 4: Final Status ---");
  test_status(motor_idx);

  // Step 5: Disable Motor
  RCLCPP_INFO(node_->get_logger(), "\n--- Step 5: Disable Motor ---");
  controllers_[motor_idx]->set_enabled(false);
  RCLCPP_INFO(node_->get_logger(), "✅ Motor disabled");

  RCLCPP_INFO(node_->get_logger(), "\n═══ Full Integration Test Complete ═══");
  RCLCPP_INFO(
    node_->get_logger(),
    "✅ MG6010Controller working via MotorControllerInterface!");
}

void MotorTestSuite::dispatch_test(
  const std::string & test_mode, double target_position)
{
  if (controllers_.empty() || controllers_[0] == nullptr) {
    RCLCPP_ERROR(
      node_->get_logger(),
      "Cannot dispatch test: no motor controller available");
    return;
  }

  if (test_mode == "status") {
    test_status(0);
  } else if (test_mode == "enable") {
    test_enable(0);
  } else if (test_mode == "position") {
    test_position(0, target_position);
  } else if (test_mode == "velocity") {
    test_velocity(0, 1.0);
  } else if (test_mode == "full") {
    test_full_sequence(0, target_position);
  } else {
    RCLCPP_ERROR(
      node_->get_logger(), "Unknown test mode: %s", test_mode.c_str());
    RCLCPP_INFO(
      node_->get_logger(),
      "Available modes: multi_motor, status, enable, position, velocity, full");
  }
}

// ════════════════════════════════════════════════════════════════════════
// Read-only diagnostic service callbacks
// ════════════════════════════════════════════════════════════════════════

void MotorTestSuite::readMotorStateCallback(
  const std::shared_ptr<motor_control_msgs::srv::ReadMotorState::Request> request,
  std::shared_ptr<motor_control_msgs::srv::ReadMotorState::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "read_motor_state: %s",
      response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  auto state = controllers_[idx]->readFullState();
  if (!state.valid) {
    response->error_message =
      "Failed to read motor state from motor";
    RCLCPP_ERROR(
      node_->get_logger(),
      "read_motor_state: readFullState() failed for motor_id=%d",
      request->motor_id);
    return;
  }

  response->success = true;
  response->temperature_c = static_cast<float>(state.temperature_c);
  response->voltage_v = static_cast<float>(state.voltage_v);
  response->torque_current_a = static_cast<float>(state.torque_current_a);
  response->speed_dps = static_cast<float>(state.speed_dps);
  response->encoder_position = state.encoder_position;
  response->multi_turn_deg = state.multi_turn_deg;
  response->single_turn_deg = state.single_turn_deg;
  response->phase_a = static_cast<float>(state.phase_current_a);
  response->phase_b = static_cast<float>(state.phase_current_b);
  response->phase_c = static_cast<float>(state.phase_current_c);
  response->error_flags = state.error_flags;

  RCLCPP_INFO(
    node_->get_logger(),
    "read_motor_state: motor_id=%d temp=%.1fC volt=%.1fV speed=%.1fdps "
    "encoder=%u err=0x%02X",
    request->motor_id, state.temperature_c, state.voltage_v,
    state.speed_dps, state.encoder_position, state.error_flags);
}

void MotorTestSuite::readEncoderCallback(
  const std::shared_ptr<motor_control_msgs::srv::ReadEncoder::Request> request,
  std::shared_ptr<motor_control_msgs::srv::ReadEncoder::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "read_encoder: %s",
      response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  uint16_t value = 0, raw = 0, offset = 0;
  if (!controllers_[idx]->readEncoder(value, raw, offset)) {
    response->error_message = "Failed to read encoder from motor";
    RCLCPP_ERROR(
      node_->get_logger(),
      "read_encoder: CAN read failed for motor_id=%d",
      request->motor_id);
    return;
  }

  response->success = true;
  response->original_value = value;
  response->raw_value = raw;
  response->offset = offset;

  RCLCPP_INFO(
    node_->get_logger(),
    "read_encoder: motor_id=%d value=%u raw=%u offset=%u",
    request->motor_id, value, raw, offset);
}

void MotorTestSuite::readMotorAnglesCallback(
  const std::shared_ptr<motor_control_msgs::srv::ReadMotorAngles::Request> request,
  std::shared_ptr<motor_control_msgs::srv::ReadMotorAngles::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "read_motor_angles: %s",
      response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  double multi = 0.0, single = 0.0;
  bool ok = true;

  if (!controllers_[idx]->readMultiTurnAngle(multi)) {
    response->error_message += "Failed to read multi-turn angle. ";
    ok = false;
  }

  if (!controllers_[idx]->readSingleTurnAngle(single)) {
    response->error_message += "Failed to read single-turn angle. ";
    ok = false;
  }

  // Populate even on partial failure
  response->multi_turn_angle = multi;
  response->single_turn_angle = single;
  response->success = ok;

  if (ok) {
    RCLCPP_INFO(
      node_->get_logger(),
      "read_motor_angles: motor_id=%d multi=%.4f single=%.4f (rad)",
      request->motor_id, multi, single);
  } else {
    RCLCPP_ERROR(
      node_->get_logger(),
      "read_motor_angles: motor_id=%d partial/full failure: %s",
      request->motor_id, response->error_message.c_str());
  }
}

void MotorTestSuite::readMotorLimitsCallback(
  const std::shared_ptr<motor_control_msgs::srv::ReadMotorLimits::Request> request,
  std::shared_ptr<motor_control_msgs::srv::ReadMotorLimits::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "read_motor_limits: %s",
      response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  uint16_t ratio = 0;
  double accel_rad = 0.0;
  bool limits_ok = true;

  if (!controllers_[idx]->readMaxTorqueCurrent(ratio)) {
    response->error_message += "Failed to read max torque current. ";
    limits_ok = false;
  }

  if (!controllers_[idx]->readAcceleration(accel_rad)) {
    response->error_message += "Failed to read acceleration. ";
    limits_ok = false;
  }

  // Populate even on partial failure
  response->max_torque_ratio = ratio;
  response->acceleration = accel_rad;
  response->success = limits_ok;

  if (limits_ok) {
    RCLCPP_INFO(
      node_->get_logger(),
      "read_motor_limits: motor_id=%d torque_ratio=%u accel=%.2f",
      request->motor_id, ratio, accel_rad);
  } else {
    RCLCPP_ERROR(
      node_->get_logger(),
      "read_motor_limits: motor_id=%d partial/full failure: %s",
      request->motor_id, response->error_message.c_str());
  }
}

void MotorTestSuite::clearMotorErrorsCallback(
  const std::shared_ptr<motor_control_msgs::srv::ClearMotorErrors::Request> request,
  std::shared_ptr<motor_control_msgs::srv::ClearMotorErrors::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "clear_motor_errors: %s",
      response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  if (!controllers_[idx]->clear_errors()) {
    response->error_message = "Failed to clear motor errors";
    RCLCPP_ERROR(
      node_->get_logger(),
      "clear_motor_errors: CAN command failed for motor_id=%d",
      request->motor_id);
    return;
  }

  // Read back error flags to confirm
  uint32_t flags = 0;
  controllers_[idx]->readErrors(flags);

  response->success = true;
  response->error_flags_after = static_cast<uint8_t>(flags);

  RCLCPP_INFO(
    node_->get_logger(),
    "clear_motor_errors: motor_id=%d flags_after=0x%02X",
    request->motor_id, response->error_flags_after);
}

void MotorTestSuite::readPidCallback(
  const std::shared_ptr<motor_control_msgs::srv::ReadPID::Request> request,
  std::shared_ptr<motor_control_msgs::srv::ReadPID::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "read_pid: %s",
      response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  auto pid = controllers_[idx]->readPID();
  if (!pid.has_value()) {
    response->error_message = "Failed to read PID parameters from motor";
    RCLCPP_ERROR(
      node_->get_logger(),
      "read_pid: CAN read failed for motor_id=%d",
      request->motor_id);
    return;
  }

  response->success = true;
  response->angle_kp = pid->angle_kp;
  response->angle_ki = pid->angle_ki;
  response->speed_kp = pid->speed_kp;
  response->speed_ki = pid->speed_ki;
  response->current_kp = pid->current_kp;
  response->current_ki = pid->current_ki;

  RCLCPP_INFO(
    node_->get_logger(),
    "read_pid: motor_id=%d angle_kp=%d angle_ki=%d spd_kp=%d spd_ki=%d "
    "current_kp=%d current_ki=%d",
    request->motor_id, pid->angle_kp, pid->angle_ki,
    pid->speed_kp, pid->speed_ki, pid->current_kp, pid->current_ki);
}

// ════════════════════════════════════════════════════════════════════════
// Motor availability
// ════════════════════════════════════════════════════════════════════════

void MotorTestSuite::motor_availability_callback(
  const std::shared_ptr<std_srvs::srv::Trigger::Request>,
  std::shared_ptr<std_srvs::srv::Trigger::Response> response)
{
  size_t available_count = 0;
  std::stringstream motor_list;

  for (size_t i = 0; i < controllers_.size(); ++i) {
    bool is_available = (controllers_[i] != nullptr);
    if (i < MAX_MOTORS) {
      is_available = is_available && motor_available_[i];
    }
    if (is_available) {
      available_count++;
    }

    std::string joint_name =
      (i < joint_names_.size()) ? joint_names_[i] : "unknown";
    motor_list << joint_name << ": "
               << (is_available ? "AVAILABLE" : "UNAVAILABLE");
    if (i < controllers_.size() - 1) {
      motor_list << ", ";
    }
  }

  response->success = (available_count > 0);
  response->message =
    "Motors: " + std::to_string(available_count) + "/" +
    std::to_string(controllers_.size()) + " available. " +
    motor_list.str();

  RCLCPP_INFO(
    node_->get_logger(), "Motor availability query: %s",
    response->message.c_str());
}

}  // namespace motor_control_ros2
