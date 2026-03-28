/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * MotorManager — centralized motor array ownership, CAN interface lifecycle,
 * and motor-level operations extracted from MG6010ControllerNode.
 *
 * Replaces direct motor array access, CAN initialization, and parallel arrays
 * (controllers_, motor_available_, motor_enabled_flags_, joint_names_,
 * homing_positions_) with a single queryable API.
 *
 * Part of mg6010-decomposition Phase 2 (Step 5).
 */

#ifndef MOTOR_CONTROL_ROS2__MOTOR_MANAGER_HPP_
#define MOTOR_CONTROL_ROS2__MOTOR_MANAGER_HPP_

#include <atomic>
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"

namespace motor_control_ros2
{

/**
 * @brief Centralized motor ownership and operations.
 *
 * MotorManager owns the motor controller array, CAN interface, and per-motor
 * state flags. It replaces the god-class's parallel arrays with a single
 * API using dynamic std::vector sizing (no compile-time MAX_MOTORS).
 *
 * This is a plain C++ class — not a ROS2 node. It reads configuration from
 * a ROS2 node's parameter server during construction but does not own or
 * extend the node.
 */
class MotorManager
{
public:
  /**
   * @brief Construct a MotorManager.
   *
   * Reads motor_ids, joint_names, motor_types, homing_positions, and other
   * per-motor parameters from the node's parameter server. Creates a CAN
   * interface (or uses the injected one) and instantiates motor controllers.
   *
   * @param node         Shared pointer to ROS2 node for parameter access and logging.
   *                     Must not be null.
   * @param can_interface Optional injected CAN interface for dependency injection / testing.
   *                     If null, a new CAN interface is created from ROS2 parameters.
   *
   * @throws std::invalid_argument if node is null, zero motors configured,
   *         or parameter arrays have mismatched lengths.
   */
  MotorManager(
    std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
    std::shared_ptr<CANInterface> can_interface = nullptr);

  /**
    * @brief Test-only constructor: inject pre-built controllers.
    *
    * Bypasses ROS2 parameter reading and motor creation. Used for unit testing
    * with mock MotorControllerInterface instances.
    *
    * @param node         Shared pointer to ROS2 node (for logging). Must not be null.
    * @param can_interface Shared CAN interface. Must not be null.
    * @param controllers  Pre-built motor controllers (size determines motorCount).
    * @param joint_names  Joint names (must match controllers size).
    * @param homing_positions Homing positions (must match controllers size).
    *
    * @throws std::invalid_argument on null node/CAN, empty controllers, or size mismatch.
    */
  MotorManager(
    std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
    std::shared_ptr<CANInterface> can_interface,
    std::vector<std::shared_ptr<MotorControllerInterface>> controllers,
    std::vector<std::string> joint_names,
    std::vector<double> homing_positions);

  ~MotorManager() = default;

  // Non-copyable, non-movable (owns atomic vectors)
  MotorManager(const MotorManager &) = delete;
  MotorManager & operator=(const MotorManager &) = delete;
  MotorManager(MotorManager &&) = delete;
  MotorManager & operator=(MotorManager &&) = delete;

  // ── Motor Access ───────────────────────────────────────────────────

  /**
   * @brief Get motor controller by index.
   * @param idx Motor index (0-based).
   * @return shared_ptr to motor controller, or nullptr if out of range.
   */
  std::shared_ptr<MotorControllerInterface> getMotor(size_t idx) const;

  /**
   * @brief Find motor controller by CAN ID.
   * @param can_id CAN motor ID to search for.
   * @return shared_ptr to motor controller, or nullptr if not found.
   */
  std::shared_ptr<MotorControllerInterface> getMotorByCanId(uint8_t can_id) const;

  /**
   * @brief Find motor controller by joint name.
   * @param name Joint name to search for.
   * @return shared_ptr to motor controller, or nullptr if not found.
   */
  std::shared_ptr<MotorControllerInterface> getMotorByJointName(const std::string & name) const;

  // ── Bulk Operations ────────────────────────────────────────────────

  /**
   * @brief Enable all available motors.
   * @return Number of motors successfully enabled.
   */
  size_t enableAll();

  /**
   * @brief Disable all available motors.
   * @return Number of motors successfully disabled.
   */
  size_t disableAll();

  /**
   * @brief Stop all available motors (exit position control).
   * @return Number of motors successfully stopped.
   */
  size_t stopAll();

  /**
   * @brief Emergency stop all available motors. Safety-critical: <10ms for 6 motors.
   * @return Number of motors successfully emergency-stopped.
   */
  size_t emergencyStopAll();

  // ── State Management ───────────────────────────────────────────────

  /**
   * @brief Check if motor is available (discovered on CAN bus).
   * @param idx Motor index.
   * @return true if available, false if out of range or unavailable.
   */
  bool isAvailable(size_t idx) const;

  /**
   * @brief Check if motor is enabled.
   * @param idx Motor index.
   * @return true if enabled, false if out of range or disabled.
   */
  bool isEnabled(size_t idx) const;

  /**
   * @brief Set motor availability flag (thread-safe).
   * @param idx Motor index. No-op if out of range.
   * @param available New availability state.
   */
  void setAvailable(size_t idx, bool available);

  /**
   * @brief Set motor enabled flag (thread-safe).
   * @param idx Motor index. No-op if out of range.
   * @param enabled New enabled state.
   */
  void setEnabled(size_t idx, bool enabled);

  /**
   * @brief Get total number of configured motors.
   * @return Motor count (immutable after construction).
   */
  size_t motorCount() const;

  // ── Joint Configuration ────────────────────────────────────────────

  /**
   * @brief Get joint name by index.
   * @param idx Motor index.
   * @return Joint name, or empty string if out of range.
   */
  std::string getJointName(size_t idx) const;

  /**
   * @brief Get homing position by index.
   * @param idx Motor index.
   * @return Homing position, or 0.0 if out of range.
   */
  double getHomingPosition(size_t idx) const;

  /**
   * @brief Get all joint names.
   * @return Const reference to joint names vector.
   */
  const std::vector<std::string> & getJointNames() const;

  // ── CAN Interface ──────────────────────────────────────────────────

  /**
   * @brief Get the shared CAN interface.
   * @return shared_ptr to CAN interface.
   */
  std::shared_ptr<CANInterface> getCANInterface() const;

private:
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<CANInterface> can_interface_;

  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;
  std::vector<std::string> joint_names_;
  std::vector<double> homing_positions_;

  // Thread-safe per-motor state flags (sized at construction, never resized)
  std::vector<std::atomic<bool>> motor_available_;
  std::vector<std::atomic<bool>> motor_enabled_;

  size_t motor_count_{0};
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__MOTOR_MANAGER_HPP_
