/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * RoleStrategy — polymorphic role detection for arm vs vehicle configurations.
 *
 * Replaces scattered joint_name.find("steering"/"drive"/"joint3"/etc.) checks
 * in mg6010_controller_node.cpp with a clean strategy pattern.
 *
 * Part of mg6010-decomposition Phase 3 (Step 6).
 */

#ifndef MOTOR_CONTROL_ROS2__ROLE_STRATEGY_HPP_
#define MOTOR_CONTROL_ROS2__ROLE_STRATEGY_HPP_

#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

namespace motor_control_ros2
{

// Forward declaration — no dependency on mg6010_controller_node.hpp
class MotorManager;

/// Describes one step in a shutdown sequence.
struct ShutdownStep
{
  size_t joint_index;         ///< Index into the joint_names vector
  std::string joint_name;     ///< Human-readable joint name
  enum class Action { PARK, HOME, DISABLE } action;
  double target_position;     ///< Target position (radians/meters depending on joint)
  bool needs_position_parking;  ///< Whether to command and verify position before disable
};

/// Conversion factors for joint state publishing.
struct JointStateConversion
{
  double position_factor;  ///< Multiply motor position by this for /joint_states
  double velocity_factor;  ///< Multiply motor velocity by this for /joint_states
};

/**
 * @brief Abstract base class for role-specific behavior.
 *
 * Concrete implementations: ArmRoleStrategy, VehicleRoleStrategy.
 * No dependency on MG6010ControllerNode — testable with mock node.
 */
class RoleStrategy
{
public:
  virtual ~RoleStrategy() = default;

  /// @brief Returns "arm" or "vehicle".
  virtual std::string roleType() const = 0;

  /// @brief True if this is an arm configuration.
  virtual bool isArm() const = 0;

  /// @brief True if this is a vehicle configuration.
  virtual bool isVehicle() const = 0;

  /// @brief True if the named joint is a drive motor.
  virtual bool isDriveMotor(const std::string & joint_name) const = 0;

  /// @brief True if the named joint is a steering motor.
  virtual bool isSteeringMotor(const std::string & joint_name) const = 0;

  /// @brief True if the named joint requires position parking on shutdown.
  virtual bool needsPositionParking(const std::string & joint_name) const = 0;

  /// @brief True if the named joint participates in the control loop.
  virtual bool isControlLoopJoint(const std::string & joint_name) const = 0;

  /**
   * @brief Get the ordered shutdown sequence for the given joints.
   *
   * @param joint_names   Joint names in config order.
   * @param homing_positions  Homing (operational) positions per joint.
   * @param packing_positions Packing (transport/shutdown) positions per joint.
   * @return Ordered vector of ShutdownStep structs.
   */
  virtual std::vector<ShutdownStep> getShutdownSequence(
    const std::vector<std::string> & joint_names,
    const std::vector<double> & homing_positions,
    const std::vector<double> & packing_positions) const = 0;

  /**
   * @brief Get joint state conversion factors for a joint.
   * @param joint_name Joint name.
   * @return JointStateConversion with position and velocity factors.
   */
  virtual JointStateConversion getJointStateConversions(
    const std::string & joint_name) const = 0;

  /**
   * @brief Apply role-specific motor configuration (PID gains, limits, etc.)
   * @param motor_manager Reference to MotorManager.
   */
  virtual void configureMotors(MotorManager & motor_manager) const = 0;
};

/**
 * @brief ArmRoleStrategy — 3-joint arm (joint3, joint4, joint5).
 *
 * Shutdown sequence: J5 → J3(homing) → J4 → J3(parking).
 * All joints need position parking. No drive or steering motors.
 */
class ArmRoleStrategy : public RoleStrategy
{
public:
  std::string roleType() const override;
  bool isArm() const override;
  bool isVehicle() const override;
  bool isDriveMotor(const std::string & joint_name) const override;
  bool isSteeringMotor(const std::string & joint_name) const override;
  bool needsPositionParking(const std::string & joint_name) const override;
  bool isControlLoopJoint(const std::string & joint_name) const override;

  std::vector<ShutdownStep> getShutdownSequence(
    const std::vector<std::string> & joint_names,
    const std::vector<double> & homing_positions,
    const std::vector<double> & packing_positions) const override;

  JointStateConversion getJointStateConversions(
    const std::string & joint_name) const override;

  void configureMotors(MotorManager & motor_manager) const override;
};

/**
 * @brief VehicleRoleStrategy — steering + drive motors.
 *
 * Shutdown sequence: steering motors first (position park), then drive motors (disable only).
 * Drive motors do not need position parking (continuous rotation).
 */
class VehicleRoleStrategy : public RoleStrategy
{
public:
  std::string roleType() const override;
  bool isArm() const override;
  bool isVehicle() const override;
  bool isDriveMotor(const std::string & joint_name) const override;
  bool isSteeringMotor(const std::string & joint_name) const override;
  bool needsPositionParking(const std::string & joint_name) const override;
  bool isControlLoopJoint(const std::string & joint_name) const override;

  std::vector<ShutdownStep> getShutdownSequence(
    const std::vector<std::string> & joint_names,
    const std::vector<double> & homing_positions,
    const std::vector<double> & packing_positions) const override;

  JointStateConversion getJointStateConversions(
    const std::string & joint_name) const override;

  void configureMotors(MotorManager & motor_manager) const override;
};

/**
 * @brief Factory function to create the appropriate RoleStrategy.
 *
 * Reads the `role` parameter from the node:
 * - "arm" → ArmRoleStrategy
 * - "vehicle" → VehicleRoleStrategy
 * - missing/empty → auto-detect from joint_names with deprecation warning
 *
 * @param node ROS2 node for parameter access and logging.
 * @return Shared pointer to the created RoleStrategy.
 *
 * @throws std::invalid_argument if role value is invalid (not arm/vehicle/empty).
 */
std::shared_ptr<RoleStrategy> createRoleStrategy(
  const std::shared_ptr<rclcpp_lifecycle::LifecycleNode> & node);

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__ROLE_STRATEGY_HPP_
