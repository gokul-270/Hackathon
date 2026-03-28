/*
 * Copyright 2024-2026 Pragati Robotics
 *
 * ShutdownHandler — role-aware motor shutdown orchestration.
 * Extracted from MG6010ControllerNode::perform_shutdown().
 *
 * Owns: timer cancellation, role-aware motor parking sequence,
 * position polling with per-joint/global timeouts, signal-based abort.
 *
 * Part of mg6010-decomposition Phase 3 (Step 7).
 */

#include "motor_control_ros2/shutdown_handler.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <stdexcept>

namespace motor_control_ros2
{

ShutdownHandler::ShutdownHandler(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  MotorManager & motor_manager,
  std::shared_ptr<RoleStrategy> role_strategy,
  std::vector<rclcpp::TimerBase::SharedPtr> timers_to_cancel)
: node_(std::move(node)),
  motor_manager_(motor_manager),
  role_strategy_(std::move(role_strategy)),
  timers_to_cancel_(std::move(timers_to_cancel))
{
  // Validate inputs
  if (!node_) {
    throw std::invalid_argument("ShutdownHandler: node must not be null");
  }
  if (!role_strategy_) {
    throw std::invalid_argument("ShutdownHandler: role strategy must not be null");
  }
  if (motor_manager_.motorCount() == 0) {
    throw std::invalid_argument("ShutdownHandler: motor_manager has zero motors");
  }

  // Read shutdown parameters with safe defaults
  try {
    enable_packing_ = node_->get_parameter("shutdown.enable_packing").as_bool();
  } catch (const std::exception &) {
    enable_packing_ = true;  // default
  }
  try {
    max_duration_s_ = node_->get_parameter("shutdown.max_duration_s").as_double();
  } catch (const std::exception &) {
    max_duration_s_ = 10.0;  // default
  }
  try {
    position_tolerance_ = node_->get_parameter("shutdown.position_tolerance").as_double();
  } catch (const std::exception &) {
    position_tolerance_ = 0.02;  // default
  }
  try {
    poll_interval_ms_ = node_->get_parameter("shutdown.poll_interval_ms").as_double();
  } catch (const std::exception &) {
    poll_interval_ms_ = 100.0;  // default
  }

  // Sanitize
  if (max_duration_s_ < 0.0) {
    max_duration_s_ = 10.0;
  }
  if (position_tolerance_ <= 0.0) {
    position_tolerance_ = 0.02;
  }
  if (poll_interval_ms_ < 10.0) {
    poll_interval_ms_ = 100.0;
  }

  // Read packing positions
  try {
    packing_positions_ = node_->get_parameter("packing_positions")
      .as_double_array();
  } catch (const std::exception &) {
    // Default: zeros for all motors
    packing_positions_.resize(motor_manager_.motorCount(), 0.0);
  }
}

ShutdownResult ShutdownHandler::execute()
{
  const size_t motor_count = motor_manager_.motorCount();
  ShutdownResult result;
  result.total_count = motor_count;
  result.per_joint_status.resize(motor_count, false);
  result.deadline_exceeded = false;

  // Step 1: Cancel all timers before doing anything with motors
  for (auto & timer : timers_to_cancel_) {
    if (timer) {
      timer->cancel();
    }
  }

  // Check abort before starting
  if (shutdown_requested_.load()) {
    return result;
  }

  // Step 2: Get shutdown sequence from RoleStrategy
  auto joint_names = motor_manager_.getJointNames();
  std::vector<double> homing_positions;
  homing_positions.reserve(motor_count);
  for (size_t i = 0; i < motor_count; ++i) {
    homing_positions.push_back(motor_manager_.getHomingPosition(i));
  }

  auto sequence = role_strategy_->getShutdownSequence(
    joint_names, homing_positions, packing_positions_);

  // If enable_packing is false for arm, remove the final J3 packing step.
  // ArmRoleStrategy returns 4 steps: J5-park, J3-home, J4-park, J3-park.
  // When enable_packing=false, we only want the first 3.
  if (!enable_packing_ && role_strategy_->isArm() && sequence.size() == 4) {
    sequence.pop_back();
  }

  // Step 3: Execute the shutdown sequence
  auto shutdown_deadline = std::chrono::steady_clock::now() +
    std::chrono::duration<double>(max_duration_s_);
  auto poll_interval = std::chrono::milliseconds(
    static_cast<int>(poll_interval_ms_));

  for (const auto & step : sequence) {
    // Check global deadline
    if (std::chrono::steady_clock::now() >= shutdown_deadline) {
      result.deadline_exceeded = true;
      break;
    }

    // Check abort
    if (shutdown_requested_.load()) {
      break;
    }

    size_t idx = step.joint_index;
    if (idx >= motor_count) {
      continue;
    }

    auto motor = motor_manager_.getMotor(idx);
    if (!motor) {
      continue;
    }

    // Drive motors (no position parking) — just mark as parked
    if (!step.needs_position_parking) {
      result.per_joint_status[idx] = true;
      continue;
    }

    double target = step.target_position;

    // Check if already at target
    double current_pos = motor->get_position();
    double error = std::abs(current_pos - target);
    if (error <= position_tolerance_) {
      result.per_joint_status[idx] = true;
      continue;
    }

    // Command motor to target position
    if (!motor->set_position(target, 0.0, 0.0)) {
      continue;
    }

    // Poll position until reached or per-joint timeout (2s)
    auto joint_start = std::chrono::steady_clock::now();
    const double per_joint_timeout_s = 2.0;
    auto joint_deadline = joint_start +
      std::chrono::duration<double>(per_joint_timeout_s);

    while (!shutdown_requested_.load() &&
           std::chrono::steady_clock::now() < shutdown_deadline &&
           std::chrono::steady_clock::now() < joint_deadline) {
      {
        std::unique_lock<std::mutex> lk(shutdown_cv_mutex_);
        shutdown_cv_.wait_for(lk, poll_interval,
          [this] { return shutdown_requested_.load(); });
      }
      if (shutdown_requested_.load()) {
        break;
      }

      current_pos = motor->get_position();
      error = std::abs(current_pos - target);
      if (error <= position_tolerance_) {
        result.per_joint_status[idx] = true;
        break;
      }
    }

    // Check if global deadline was exceeded during this joint
    if (std::chrono::steady_clock::now() >= shutdown_deadline) {
      result.deadline_exceeded = true;
      break;
    }
  }

  // Step 4: Stop and disable all motors unconditionally
  // Hardened shutdown: motor_stop before motor_off for each motor,
  // then clear_errors after all motors are disabled.
  for (size_t i = 0; i < motor_count; ++i) {
    auto motor = motor_manager_.getMotor(i);
    if (motor) {
      // motor_stop (0x81): exit position control, reduce power
      if (!motor->stop()) {
        RCLCPP_WARN(rclcpp::get_logger("motor_control"),
          "Shutdown: motor_stop failed for motor %zu (non-fatal)", i);
      }
      motor->set_enabled(false);
    }
  }

  // Step 5: Clear errors on all motors after disable
  // Ensures clean state for next power-on session.
  for (size_t i = 0; i < motor_count; ++i) {
    auto motor = motor_manager_.getMotor(i);
    if (motor) {
      if (!motor->clear_errors()) {
        RCLCPP_WARN(rclcpp::get_logger("motor_control"),
          "Shutdown: clear_errors failed for motor %zu (non-fatal)", i);
      }
    }
  }

  // Count parked joints
  result.parked_count = static_cast<size_t>(
    std::count(result.per_joint_status.begin(),
               result.per_joint_status.end(), true));

  return result;
}

void ShutdownHandler::requestAbort()
{
  shutdown_requested_.store(true, std::memory_order_release);
}

void ShutdownHandler::notifyAbort()
{
  shutdown_cv_.notify_all();
}

}  // namespace motor_control_ros2
