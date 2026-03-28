/*
 * RoleStrategy implementation — polymorphic role detection.
 *
 * Replaces scattered joint_name.find("steering"/"drive"/"joint3"/etc.) checks
 * in mg6010_controller_node.cpp with strategy-pattern method calls.
 *
 * Part of mg6010-decomposition Phase 3 (Step 6).
 */

#include "motor_control_ros2/role_strategy.hpp"

#include <algorithm>
#include <stdexcept>

namespace motor_control_ros2
{

// =============================================================================
// ArmRoleStrategy
// =============================================================================

std::string ArmRoleStrategy::roleType() const
{
  return "arm";
}

bool ArmRoleStrategy::isArm() const
{
  return true;
}

bool ArmRoleStrategy::isVehicle() const
{
  return false;
}

bool ArmRoleStrategy::isDriveMotor(const std::string & /*joint_name*/) const
{
  // Arm has no drive motors
  return false;
}

bool ArmRoleStrategy::isSteeringMotor(const std::string & /*joint_name*/) const
{
  // Arm has no steering motors
  return false;
}

bool ArmRoleStrategy::needsPositionParking(const std::string & /*joint_name*/) const
{
  // All arm joints require position parking before disable
  return true;
}

bool ArmRoleStrategy::isControlLoopJoint(const std::string & /*joint_name*/) const
{
  // All arm joints participate in the control loop
  return true;
}

std::vector<ShutdownStep> ArmRoleStrategy::getShutdownSequence(
  const std::vector<std::string> & joint_names,
  const std::vector<double> & homing_positions,
  const std::vector<double> & packing_positions) const
{
  std::vector<ShutdownStep> sequence;

  // Find arm joint indices in the config-ordered joint_names
  size_t j5_idx = SIZE_MAX;
  size_t j3_idx = SIZE_MAX;
  size_t j4_idx = SIZE_MAX;

  for (size_t i = 0; i < joint_names.size(); ++i) {
    if (joint_names[i] == "joint5") {
      j5_idx = i;
    } else if (joint_names[i] == "joint3") {
      j3_idx = i;
    } else if (joint_names[i] == "joint4") {
      j4_idx = i;
    }
  }

  // ARM shutdown sequence: J5 → J3(HOME) → J4 → J3(PARK)
  // This ordering ensures J4 only moves when J3 is tilted down (homing),
  // creating clearance to avoid collision.

  // Step 1: J5 parks to packing position
  if (j5_idx < joint_names.size()) {
    ShutdownStep step;
    step.joint_index = j5_idx;
    step.joint_name = joint_names[j5_idx];
    step.action = ShutdownStep::Action::PARK;
    step.target_position = (j5_idx < packing_positions.size())
      ? packing_positions[j5_idx] : 0.0;
    step.needs_position_parking = true;
    sequence.push_back(step);
  }

  // Step 2: J3 goes to HOMING position (creates clearance for J4)
  if (j3_idx < joint_names.size()) {
    ShutdownStep step;
    step.joint_index = j3_idx;
    step.joint_name = joint_names[j3_idx];
    step.action = ShutdownStep::Action::HOME;
    step.target_position = (j3_idx < homing_positions.size())
      ? homing_positions[j3_idx] : 0.0;
    step.needs_position_parking = true;
    sequence.push_back(step);
  }

  // Step 3: J4 parks to packing position (safe now, J3 is down)
  if (j4_idx < joint_names.size()) {
    ShutdownStep step;
    step.joint_index = j4_idx;
    step.joint_name = joint_names[j4_idx];
    step.action = ShutdownStep::Action::PARK;
    step.target_position = (j4_idx < packing_positions.size())
      ? packing_positions[j4_idx] : 0.0;
    step.needs_position_parking = true;
    sequence.push_back(step);
  }

  // Step 4: J3 moves to PARKING position (transport-ready, temperature optimization)
  if (j3_idx < joint_names.size()) {
    ShutdownStep step;
    step.joint_index = j3_idx;
    step.joint_name = joint_names[j3_idx];
    step.action = ShutdownStep::Action::PARK;
    step.target_position = (j3_idx < packing_positions.size())
      ? packing_positions[j3_idx] : 0.0;
    step.needs_position_parking = true;
    sequence.push_back(step);
  }

  return sequence;
}

JointStateConversion ArmRoleStrategy::getJointStateConversions(
  const std::string & /*joint_name*/) const
{
  // Arm joints use the motor controller's internal conversion.
  // Position: rotations → radians (2*PI), velocity: same factor.
  // The generic_motor_controller handles per-motor conversion internally,
  // so at the strategy level we use 1.0 (pass-through to motor controller).
  // If needed, joint-specific factors can be looked up from config.
  return {1.0, 1.0};
}

void ArmRoleStrategy::configureMotors(MotorManager & /*motor_manager*/) const
{
  // Arm-specific motor configuration (PID gains, limits) is currently
  // handled by per-motor config in YAML. This hook exists for future
  // role-specific runtime tuning.
}

// =============================================================================
// VehicleRoleStrategy
// =============================================================================

std::string VehicleRoleStrategy::roleType() const
{
  return "vehicle";
}

bool VehicleRoleStrategy::isArm() const
{
  return false;
}

bool VehicleRoleStrategy::isVehicle() const
{
  return true;
}

bool VehicleRoleStrategy::isDriveMotor(const std::string & joint_name) const
{
  return joint_name.find("drive") != std::string::npos;
}

bool VehicleRoleStrategy::isSteeringMotor(const std::string & joint_name) const
{
  return joint_name.find("steering") != std::string::npos;
}

bool VehicleRoleStrategy::needsPositionParking(const std::string & joint_name) const
{
  // Drive motors are continuous rotation — no position parking needed.
  // Steering motors need to be parked at a known position.
  if (isDriveMotor(joint_name)) {
    return false;
  }
  return true;  // steering and any other motors need parking
}

bool VehicleRoleStrategy::isControlLoopJoint(const std::string & joint_name) const
{
  // Steering motors use position control (in control loop).
  // Drive motors are velocity-only (managed by ODrive, not in control loop).
  if (isDriveMotor(joint_name)) {
    return false;
  }
  return true;
}

std::vector<ShutdownStep> VehicleRoleStrategy::getShutdownSequence(
  const std::vector<std::string> & joint_names,
  const std::vector<double> & homing_positions,
  const std::vector<double> & packing_positions) const
{
  std::vector<ShutdownStep> sequence;

  // Vehicle shutdown: steering motors first (position park), then drive motors (disable)
  // Two passes: first collect steering, then drive

  // Pass 1: Steering motors — PARK action with position parking
  for (size_t i = 0; i < joint_names.size(); ++i) {
    if (!isDriveMotor(joint_names[i])) {
      ShutdownStep step;
      step.joint_index = i;
      step.joint_name = joint_names[i];
      step.action = ShutdownStep::Action::PARK;
      step.target_position = (i < packing_positions.size())
        ? packing_positions[i]
        : ((i < homing_positions.size()) ? homing_positions[i] : 0.0);
      step.needs_position_parking = true;
      sequence.push_back(step);
    }
  }

  // Pass 2: Drive motors — DISABLE action, no position parking
  for (size_t i = 0; i < joint_names.size(); ++i) {
    if (isDriveMotor(joint_names[i])) {
      ShutdownStep step;
      step.joint_index = i;
      step.joint_name = joint_names[i];
      step.action = ShutdownStep::Action::DISABLE;
      step.target_position = 0.0;  // irrelevant for disable
      step.needs_position_parking = false;
      sequence.push_back(step);
    }
  }

  return sequence;
}

JointStateConversion VehicleRoleStrategy::getJointStateConversions(
  const std::string & /*joint_name*/) const
{
  // Vehicle joints use motor controller's internal conversion.
  // Pass-through factors — per-motor conversion is in generic_motor_controller.
  return {1.0, 1.0};
}

void VehicleRoleStrategy::configureMotors(MotorManager & /*motor_manager*/) const
{
  // Vehicle-specific motor configuration is handled by per-motor config in YAML.
  // This hook exists for future role-specific runtime tuning
  // (e.g., velocity mode for drive, position mode for steering).
}

// =============================================================================
// Factory function
// =============================================================================

std::shared_ptr<RoleStrategy> createRoleStrategy(
  const std::shared_ptr<rclcpp_lifecycle::LifecycleNode> & node)
{
  // Read the 'role' parameter if declared
  std::string role;
  bool has_role = false;

  if (node->has_parameter("role")) {
    role = node->get_parameter("role").as_string();
    has_role = !role.empty();
  }

  if (has_role) {
    // Explicit role from config
    if (role == "arm") {
      return std::make_shared<ArmRoleStrategy>();
    } else if (role == "vehicle") {
      return std::make_shared<VehicleRoleStrategy>();
    } else {
      throw std::invalid_argument(
        "Invalid role '" + role + "': must be 'arm' or 'vehicle'");
    }
  }

  // Auto-detect from joint_names (deprecated path)
  std::vector<std::string> joint_names;
  if (node->has_parameter("joint_names")) {
    joint_names = node->get_parameter("joint_names").as_string_array();
  }

  // Check for arm pattern: presence of joint3, joint4, joint5
  bool has_joint3 = false;
  bool has_joint4 = false;
  bool has_joint5 = false;
  bool has_steering = false;
  bool has_drive = false;

  for (const auto & name : joint_names) {
    if (name == "joint3") has_joint3 = true;
    if (name == "joint4") has_joint4 = true;
    if (name == "joint5") has_joint5 = true;
    if (name.find("steering") != std::string::npos) has_steering = true;
    if (name.find("drive") != std::string::npos) has_drive = true;
  }

  bool is_arm = has_joint3 && has_joint4 && has_joint5;
  bool is_vehicle = has_steering || has_drive;

  if (is_arm) {
    RCLCPP_WARN(node->get_logger(),
      "Auto-detected role as 'arm' from joint names. This is deprecated — "
      "please add 'role: arm' to your config YAML.");
    return std::make_shared<ArmRoleStrategy>();
  }

  if (is_vehicle) {
    RCLCPP_WARN(node->get_logger(),
      "Auto-detected role as 'vehicle' from joint names. This is deprecated — "
      "please add 'role: vehicle' to your config YAML.");
    return std::make_shared<VehicleRoleStrategy>();
  }

  // Neither arm nor vehicle pattern detected — default to arm (safe: no drive/steering logic)
  RCLCPP_WARN(node->get_logger(),
    "Cannot auto-detect role from joint names; defaulting to 'arm'. "
    "Please add 'role: arm' or 'role: vehicle' to your config YAML.");
  return std::make_shared<ArmRoleStrategy>();
}

}  // namespace motor_control_ros2
