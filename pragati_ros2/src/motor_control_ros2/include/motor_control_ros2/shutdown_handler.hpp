/*
 * Copyright 2024-2026 Pragati Robotics
 *
 * ShutdownHandler — Extracted motor shutdown orchestration.
 * Owns the full shutdown sequence: timer cancellation, role-aware motor parking,
 * position polling, timeout management, signal-based abort.
 *
 * Part of mg6010-decomposition Phase 3 (Step 7).
 */

#pragma once

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

#include "motor_control_ros2/motor_manager.hpp"
#include "motor_control_ros2/role_strategy.hpp"

#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace motor_control_ros2
{

/// Result of a shutdown sequence execution.
struct ShutdownResult
{
  size_t parked_count{0};                ///< Number of joints successfully parked
  size_t total_count{0};                 ///< Total joint count
  std::vector<bool> per_joint_status;    ///< Per-joint parking success
  bool deadline_exceeded{false};         ///< Whether global deadline was exceeded
};

/**
 * @brief Orchestrates role-aware motor shutdown.
 *
 * Extracts perform_shutdown() logic from MG6010ControllerNode into a
 * standalone, testable class. Delegates sequence ordering to RoleStrategy,
 * motor commands to MotorManager, position polling via MotorControllerInterface.
 *
 * No dependency on MG6010ControllerNode — testable with mock node + controllers.
 */
class ShutdownHandler
{
public:
  /**
   * @brief Construct ShutdownHandler, reading params from node.
   *
   * Parameters read: shutdown.enable_packing, shutdown.max_duration_s,
   * shutdown.position_tolerance, shutdown.poll_interval_ms, packing_positions.
   *
   * @param node        ROS2 node for parameters and logging.
   * @param motor_manager MotorManager with initialized motors.
   * @param role_strategy Role strategy for shutdown sequence ordering.
   * @param timers_to_cancel Optional timers to cancel before parking.
   * @throws std::invalid_argument if node is null, role_strategy is null,
   *         or motor_manager has zero motors.
   */
  ShutdownHandler(
    std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
    MotorManager & motor_manager,
    std::shared_ptr<RoleStrategy> role_strategy,
    std::vector<rclcpp::TimerBase::SharedPtr> timers_to_cancel = {});

  /**
   * @brief Execute the shutdown sequence.
   *
   * 1. Cancel all timers.
   * 2. Get shutdown sequence from RoleStrategy.
   * 3. For each step: command motor, poll position, handle timeout.
   * 4. Disable all motors.
   *
   * @return ShutdownResult with parking status per joint.
   */
  ShutdownResult execute();

  /// Request early abort of shutdown (thread-safe).
  void requestAbort();

  /// Wake the condition variable for immediate abort response (thread-safe).
  void notifyAbort();

private:
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  MotorManager & motor_manager_;
  std::shared_ptr<RoleStrategy> role_strategy_;
  std::vector<rclcpp::TimerBase::SharedPtr> timers_to_cancel_;

  // Shutdown parameters
  bool enable_packing_{true};
  double max_duration_s_{10.0};
  double position_tolerance_{0.02};
  double poll_interval_ms_{100.0};
  std::vector<double> packing_positions_;

  // Abort signaling
  std::atomic<bool> shutdown_requested_{false};
  std::mutex shutdown_cv_mutex_;
  std::condition_variable shutdown_cv_;
};

}  // namespace motor_control_ros2
