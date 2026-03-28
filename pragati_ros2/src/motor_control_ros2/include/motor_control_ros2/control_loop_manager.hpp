/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * ControlLoopManager — extracted from MG6010ControllerNode
 *
 * Owns the real-time control loop, joint state publishing, motor
 * diagnostics publishing, PID write services, and command callbacks
 * (position, velocity, stop).
 */

#ifndef MOTOR_CONTROL_ROS2__CONTROL_LOOP_MANAGER_HPP_
#define MOTOR_CONTROL_ROS2__CONTROL_LOOP_MANAGER_HPP_

#include <array>
#include <atomic>
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>

#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"

#include "motor_control_msgs/srv/write_pid.hpp"
#include "motor_control_msgs/srv/write_pid_to_rom.hpp"

namespace motor_control_ros2
{

/// Maximum number of motors supported by the system.
/// Also defined in motor_test_suite.hpp — guarded to avoid redefinition
/// when both headers are included in the same translation unit.
#ifndef MOTOR_CONTROL_ROS2_MAX_MOTORS_DEFINED
#define MOTOR_CONTROL_ROS2_MAX_MOTORS_DEFINED
constexpr size_t MAX_MOTORS = 6;
#endif

/**
 * @brief Extracted control-loop functionality from MG6010ControllerNode.
 *
 * Contains:
 *  - Periodic control loop (timer-driven)
 *  - JointState and DiagnosticArray publishing
 *  - PID write service callbacks (RAM and ROM)
 *  - Position, velocity, and stop command callbacks
 *
 * This class operates on references to the parent node's controllers vector,
 * motor_available array, and joint_names vector. All methods produce identical
 * behavior to the original inline implementations in mg6010_controller_node.cpp.
 */
class ControlLoopManager
{
public:
  /**
   * @brief Construct a ControlLoopManager.
   *
   * @param node              Shared pointer to the ROS2 node (for logging, timers, publishers).
   *                          Must not be null.
   * @param can_interface     Shared pointer to the CAN interface. Must not be null.
   * @param controllers       Reference to the controllers vector.
   * @param motor_available   Reference to the motor availability atomic array.
   * @param joint_names       Reference to joint names vector.
   * @param control_frequency Control loop frequency in Hz (default 10.0).
   *
   * @throws std::invalid_argument if node or can_interface is null.
   */
  ControlLoopManager(
    std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
    std::shared_ptr<CANInterface> can_interface,
    std::vector<std::shared_ptr<MotorControllerInterface>> & controllers,
    std::array<std::atomic<bool>, MAX_MOTORS> & motor_available,
    std::vector<std::string> & joint_names,
    double control_frequency = 10.0);

  // ── PID Write Service Callbacks ─────────────────────────────────────

  /** @brief Write PID parameters to motor RAM (lost on power cycle). */
  void writePidCallback(
    const std::shared_ptr<motor_control_msgs::srv::WritePID::Request> request,
    std::shared_ptr<motor_control_msgs::srv::WritePID::Response> response);

  /** @brief Write PID parameters to motor ROM (persists across power cycles). */
  void writePidToRomCallback(
    const std::shared_ptr<motor_control_msgs::srv::WritePIDToROM::Request> request,
    std::shared_ptr<motor_control_msgs::srv::WritePIDToROM::Response> response);

  // ── Command Callbacks ───────────────────────────────────────────────

  /** @brief Set target position for a motor (radians). */
  void position_command_callback(size_t motor_idx, double position);

  /** @brief Set target velocity for a motor (rad/s). */
  void velocity_command_callback(size_t motor_idx, double velocity);

  /** @brief Stop a motor. */
  void stop_command_callback(size_t motor_idx);

private:
  // ── Private Methods ─────────────────────────────────────────────────

  /** @brief Timer callback — runs the control loop at control_frequency_. */
  void control_loop();

  /**
   * @brief Find motor index by CAN ID.
   * @param motor_id CAN motor ID to search for.
   * @return Index into controllers_ vector, or SIZE_MAX if not found.
   */
  size_t findMotorByCanId(uint8_t motor_id) const;

  // ── Private Members ─────────────────────────────────────────────────

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<CANInterface> can_interface_;
  std::vector<std::shared_ptr<MotorControllerInterface>> & controllers_;
  std::array<std::atomic<bool>, MAX_MOTORS> & motor_available_;
  std::vector<std::string> & joint_names_;
  double control_frequency_;

  rclcpp::TimerBase::SharedPtr control_timer_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr motor_diagnostics_pub_;
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__CONTROL_LOOP_MANAGER_HPP_
