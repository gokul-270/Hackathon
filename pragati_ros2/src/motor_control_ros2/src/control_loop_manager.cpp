/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * ControlLoopManager implementation — extracted from MG6010ControllerNode.
 *
 * Owns the periodic control loop, JointState/DiagnosticArray publishing,
 * PID write service callbacks, and position/velocity/stop command callbacks.
 */

#include "motor_control_ros2/control_loop_manager.hpp"

#include <chrono>
#include <stdexcept>
#include <string>

namespace motor_control_ros2
{

// =============================================================================
// Constructor
// =============================================================================

ControlLoopManager::ControlLoopManager(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  std::shared_ptr<CANInterface> can_interface,
  std::vector<std::shared_ptr<MotorControllerInterface>> & controllers,
  std::array<std::atomic<bool>, MAX_MOTORS> & motor_available,
  std::vector<std::string> & joint_names,
  double control_frequency)
: node_(std::move(node)),
  can_interface_(std::move(can_interface)),
  controllers_(controllers),
  motor_available_(motor_available),
  joint_names_(joint_names),
  control_frequency_(control_frequency)
{
  if (!node_) {
    throw std::invalid_argument("ControlLoopManager: node must not be null");
  }
  if (!can_interface_) {
    throw std::invalid_argument("ControlLoopManager: can_interface must not be null");
  }

  // Only create timer and publishers when control_frequency > 0.
  // When embedded in the node (which has its own control loop), pass 0 to skip.
  if (control_frequency_ > 0.0) {
    // Create publishers
    joint_state_pub_ = node_->create_publisher<sensor_msgs::msg::JointState>(
      "joint_states", 10);
    motor_diagnostics_pub_ = node_->create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
      "~/motor_diagnostics", 10);

    // Create control loop timer
    auto period = std::chrono::duration<double>(1.0 / control_frequency_);
    control_timer_ = node_->create_wall_timer(
      std::chrono::duration_cast<std::chrono::milliseconds>(period),
      std::bind(&ControlLoopManager::control_loop, this));
  }
}

// =============================================================================
// control_loop — periodic timer callback
// =============================================================================

void ControlLoopManager::control_loop()
{
  auto msg = sensor_msgs::msg::JointState();
  msg.header.stamp = node_->now();

  if (controllers_.empty()) {
    RCLCPP_WARN_ONCE(
      node_->get_logger(),
      "Control loop active but no motors initialized — joint_states will be empty");
    return;
  }

  // Pre-size arrays for zero-copy efficiency (populate via indexing, not push_back)
  const size_t num_motors = controllers_.size();
  msg.name.resize(num_motors);
  msg.position.resize(num_motors, 0.0);
  msg.velocity.resize(num_motors, 0.0);
  msg.effort.resize(num_motors, 0.0);

  for (size_t i = 0; i < num_motors; ++i) {
    // Populate joint name
    if (i < joint_names_.size()) {
      msg.name[i] = joint_names_[i];
    } else {
      msg.name[i] = "joint_" + std::to_string(i);
    }

    // Skip unavailable motors — report zero values
    if (controllers_[i] == nullptr ||
        (i < MAX_MOTORS && !motor_available_[i].load())) {
      // Position/velocity/effort already zeroed by resize
      continue;
    }

    // Poll motor state
    msg.position[i] = controllers_[i]->get_position();
    msg.velocity[i] = controllers_[i]->get_velocity();
    msg.effort[i] = controllers_[i]->get_torque();
  }

  // Publish joint states
  if (joint_state_pub_) {
    joint_state_pub_->publish(msg);
  }

  // Publish diagnostics (minimal — full diagnostics stay in node for now)
  if (motor_diagnostics_pub_) {
    auto diag_msg = diagnostic_msgs::msg::DiagnosticArray();
    diag_msg.header.stamp = node_->now();
    motor_diagnostics_pub_->publish(diag_msg);
  }
}

// =============================================================================
// PID Write Callbacks
// =============================================================================

void ControlLoopManager::writePidCallback(
  const std::shared_ptr<motor_control_msgs::srv::WritePID::Request> request,
  std::shared_ptr<motor_control_msgs::srv::WritePID::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "write_pid: %s", response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  PIDParams params;
  params.angle_kp = request->angle_kp;
  params.angle_ki = request->angle_ki;
  params.speed_kp = request->speed_kp;
  params.speed_ki = request->speed_ki;
  params.current_kp = request->current_kp;
  params.current_ki = request->current_ki;

  if (!controllers_[idx]->setPID(params)) {
    response->error_message = "Failed to write PID parameters to motor RAM";
    RCLCPP_ERROR(
      node_->get_logger(), "write_pid: CAN write failed for motor_id=%d",
      request->motor_id);
    return;
  }

  response->success = true;
  RCLCPP_INFO(
    node_->get_logger(),
    "write_pid: motor_id=%d angle_kp=%d angle_ki=%d spd_kp=%d spd_ki=%d "
    "current_kp=%d current_ki=%d",
    request->motor_id,
    params.angle_kp, params.angle_ki,
    params.speed_kp, params.speed_ki,
    params.current_kp, params.current_ki);
}

void ControlLoopManager::writePidToRomCallback(
  const std::shared_ptr<motor_control_msgs::srv::WritePIDToROM::Request> request,
  std::shared_ptr<motor_control_msgs::srv::WritePIDToROM::Response> response)
{
  response->success = false;

  size_t idx = findMotorByCanId(request->motor_id);
  if (idx == SIZE_MAX) {
    response->error_message =
      "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
    RCLCPP_WARN(
      node_->get_logger(), "write_pid_to_rom: %s",
      response->error_message.c_str());
    return;
  }

  if (controllers_[idx] == nullptr) {
    response->error_message = "Motor controller is null";
    return;
  }

  PIDParams params;
  params.angle_kp = request->angle_kp;
  params.angle_ki = request->angle_ki;
  params.speed_kp = request->speed_kp;
  params.speed_ki = request->speed_ki;
  params.current_kp = request->current_kp;
  params.current_ki = request->current_ki;

  if (!controllers_[idx]->writePIDToROM(params)) {
    response->error_message = "Failed to write PID parameters to motor ROM";
    RCLCPP_ERROR(
      node_->get_logger(),
      "write_pid_to_rom: CAN write failed for motor_id=%d",
      request->motor_id);
    return;
  }

  response->success = true;
  RCLCPP_INFO(
    node_->get_logger(),
    "write_pid_to_rom: motor_id=%d angle_kp=%d angle_ki=%d spd_kp=%d spd_ki=%d "
    "current_kp=%d current_ki=%d",
    request->motor_id,
    params.angle_kp, params.angle_ki,
    params.speed_kp, params.speed_ki,
    params.current_kp, params.current_ki);
}

// =============================================================================
// Command Callbacks
// =============================================================================

void ControlLoopManager::position_command_callback(
  size_t motor_idx, double position)
{
  if (motor_idx >= controllers_.size()) {
    RCLCPP_WARN(
      node_->get_logger(),
      "position_command: motor_idx %zu out of range (size=%zu)",
      motor_idx, controllers_.size());
    return;
  }

  if (motor_idx < MAX_MOTORS && !motor_available_[motor_idx].load()) {
    RCLCPP_WARN(
      node_->get_logger(),
      "position_command: motor %zu is unavailable", motor_idx);
    return;
  }

  if (controllers_[motor_idx] == nullptr) {
    RCLCPP_WARN(
      node_->get_logger(),
      "position_command: controller %zu is null", motor_idx);
    return;
  }

  if (!controllers_[motor_idx]->set_position(position, 0.0, 0.0)) {
    RCLCPP_ERROR(
      node_->get_logger(),
      "position_command: set_position failed for motor %zu", motor_idx);
  }
}

void ControlLoopManager::velocity_command_callback(
  size_t motor_idx, double velocity)
{
  if (motor_idx >= controllers_.size()) {
    RCLCPP_WARN(
      node_->get_logger(),
      "velocity_command: motor_idx %zu out of range (size=%zu)",
      motor_idx, controllers_.size());
    return;
  }

  if (motor_idx < MAX_MOTORS && !motor_available_[motor_idx].load()) {
    RCLCPP_WARN(
      node_->get_logger(),
      "velocity_command: motor %zu is unavailable", motor_idx);
    return;
  }

  if (controllers_[motor_idx] == nullptr) {
    RCLCPP_WARN(
      node_->get_logger(),
      "velocity_command: controller %zu is null", motor_idx);
    return;
  }

  if (!controllers_[motor_idx]->set_velocity(velocity, 0.0)) {
    RCLCPP_ERROR(
      node_->get_logger(),
      "velocity_command: set_velocity failed for motor %zu", motor_idx);
  }
}

void ControlLoopManager::stop_command_callback(size_t motor_idx)
{
  if (motor_idx >= controllers_.size()) {
    RCLCPP_WARN(
      node_->get_logger(),
      "stop_command: motor_idx %zu out of range (size=%zu)",
      motor_idx, controllers_.size());
    return;
  }

  if (motor_idx < MAX_MOTORS && !motor_available_[motor_idx].load()) {
    RCLCPP_WARN(
      node_->get_logger(),
      "stop_command: motor %zu is unavailable", motor_idx);
    return;
  }

  if (controllers_[motor_idx] == nullptr) {
    RCLCPP_WARN(
      node_->get_logger(),
      "stop_command: controller %zu is null", motor_idx);
    return;
  }

  if (!controllers_[motor_idx]->stop()) {
    RCLCPP_ERROR(
      node_->get_logger(),
      "stop_command: stop() failed for motor %zu", motor_idx);
  }
}

// =============================================================================
// Private Helpers
// =============================================================================

size_t ControlLoopManager::findMotorByCanId(uint8_t motor_id) const
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

}  // namespace motor_control_ros2
