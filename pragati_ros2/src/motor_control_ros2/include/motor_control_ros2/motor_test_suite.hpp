/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * MotorTestSuite — extracted from MG6010ControllerNode
 *
 * Owns legacy motor test methods, read-only diagnostic service callbacks,
 * and motor availability reporting. Stateless — reads from referenced
 * controllers vector and motor_available array.
 */

#ifndef MOTOR_CONTROL_ROS2__MOTOR_TEST_SUITE_HPP_
#define MOTOR_CONTROL_ROS2__MOTOR_TEST_SUITE_HPP_

#include <array>
#include <atomic>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <std_srvs/srv/trigger.hpp>

#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"

#include "motor_control_msgs/srv/clear_motor_errors.hpp"
#include "motor_control_msgs/srv/read_encoder.hpp"
#include "motor_control_msgs/srv/read_motor_angles.hpp"
#include "motor_control_msgs/srv/read_motor_limits.hpp"
#include "motor_control_msgs/srv/read_motor_state.hpp"
#include "motor_control_msgs/srv/read_pid.hpp"

namespace motor_control_ros2
{

/// Maximum number of motors supported by the system.
/// Guarded to avoid redefinition when multiple extracted-class headers
/// are included in the same translation unit.
#ifndef MOTOR_CONTROL_ROS2_MAX_MOTORS_DEFINED
#define MOTOR_CONTROL_ROS2_MAX_MOTORS_DEFINED
constexpr size_t MAX_MOTORS = 6;
#endif

/**
 * @brief Extracted test/diagnostic functionality from MG6010ControllerNode.
 *
 * Contains:
 *  - Legacy single-motor test methods (status, enable, position, velocity, full sequence)
 *  - Read-only diagnostic service callbacks (motor state, encoder, angles, limits, errors, PID)
 *  - Motor availability reporting
 *  - Test dispatch routing
 *
 * This class is stateless — it operates on references to the parent node's
 * controllers vector and motor_available array. All methods produce identical
 * behavior to the original inline implementations in mg6010_controller_node.cpp.
 */
class MotorTestSuite
{
public:
  /**
   * @brief Construct a MotorTestSuite.
   *
   * @param node          Shared pointer to the ROS2 node (for logging). Must not be null.
   * @param can_interface Shared pointer to the CAN interface (for future use). Must not be null.
   * @param controllers   Reference to the controllers vector (read/write by test methods).
   * @param motor_available Reference to the motor availability atomic array.
   * @param joint_names   Reference to joint names vector.
   *
   * @throws std::invalid_argument if node or can_interface is null.
   */
  MotorTestSuite(
    std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
    std::shared_ptr<CANInterface> can_interface,
    std::vector<std::shared_ptr<MotorControllerInterface>> & controllers,
    std::array<std::atomic<bool>, MAX_MOTORS> & motor_available,
    std::vector<std::string> & joint_names);

  // ── Legacy test methods ──────────────────────────────────────────────

  /** @brief Read and log motor status (CAN query). */
  void test_status(size_t motor_idx);

  /** @brief Enable motor, read status, then disable. */
  void test_enable(size_t motor_idx);

  /** @brief Send position command, monitor for 3s, then disable. */
  void test_position(size_t motor_idx, double target_position);

  /** @brief Send velocity command, monitor for 3s, stop, then disable. */
  void test_velocity(size_t motor_idx, double target_velocity);

  /** @brief Run full test sequence: status → enable → position → status → disable. */
  void test_full_sequence(size_t motor_idx, double target_position);

  /**
   * @brief Route a test_mode string to the correct test method.
   *
   * Dispatches "status", "enable", "position", "velocity", "full"
   * to their respective methods using motor index 0.
   */
  void dispatch_test(const std::string & test_mode, double target_position);

  // ── Read-only diagnostic service callbacks ───────────────────────────

  void readMotorStateCallback(
    const std::shared_ptr<motor_control_msgs::srv::ReadMotorState::Request> request,
    std::shared_ptr<motor_control_msgs::srv::ReadMotorState::Response> response);

  void readEncoderCallback(
    const std::shared_ptr<motor_control_msgs::srv::ReadEncoder::Request> request,
    std::shared_ptr<motor_control_msgs::srv::ReadEncoder::Response> response);

  void readMotorAnglesCallback(
    const std::shared_ptr<motor_control_msgs::srv::ReadMotorAngles::Request> request,
    std::shared_ptr<motor_control_msgs::srv::ReadMotorAngles::Response> response);

  void readMotorLimitsCallback(
    const std::shared_ptr<motor_control_msgs::srv::ReadMotorLimits::Request> request,
    std::shared_ptr<motor_control_msgs::srv::ReadMotorLimits::Response> response);

  void clearMotorErrorsCallback(
    const std::shared_ptr<motor_control_msgs::srv::ClearMotorErrors::Request> request,
    std::shared_ptr<motor_control_msgs::srv::ClearMotorErrors::Response> response);

  void readPidCallback(
    const std::shared_ptr<motor_control_msgs::srv::ReadPID::Request> request,
    std::shared_ptr<motor_control_msgs::srv::ReadPID::Response> response);

  // ── Motor availability ───────────────────────────────────────────────

  void motor_availability_callback(
    const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response);

private:
  /**
   * @brief Find motor controller index by CAN motor ID.
   * @param motor_id CAN motor ID (1-32)
   * @return Motor index in controllers_ vector, or SIZE_MAX if not found.
   */
  size_t findMotorByCanId(uint8_t motor_id) const;

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<CANInterface> can_interface_;
  std::vector<std::shared_ptr<MotorControllerInterface>> & controllers_;
  std::array<std::atomic<bool>, MAX_MOTORS> & motor_available_;
  std::vector<std::string> & joint_names_;
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__MOTOR_TEST_SUITE_HPP_
