/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * Motor Abstraction Layer Implementation
 *
 * This file implements the core abstraction layer that enables support for
 * multiple motor types (ODrive, MG6010, etc.) through a common interface.
 */

#include "motor_control_ros2/motor_abstraction.hpp"
#include <rclcpp/rclcpp.hpp>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <cmath>
#include <limits>

namespace motor_control_ros2
{

// MotorControllerFactory implementation
std::map<std::string, std::function<std::shared_ptr<MotorControllerInterface>()>> &
MotorControllerFactory::get_registry()
{
  static std::map<std::string, std::function<std::shared_ptr<MotorControllerInterface>()>> registry;
  return registry;
}

std::shared_ptr<MotorControllerInterface>
MotorControllerFactory::create_controller(const std::string & motor_type)
{
  auto & registry = get_registry();
  auto it = registry.find(motor_type);

  if (it != registry.end()) {
    return it->second();
  }

  // If not found, try lowercase version
  std::string lower_type = motor_type;
  std::transform(lower_type.begin(), lower_type.end(), lower_type.begin(), ::tolower);

  it = registry.find(lower_type);
  if (it != registry.end()) {
    return it->second();
  }

  RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
    "Unknown motor controller type: %s", motor_type.c_str());
  return nullptr;
}

void MotorControllerFactory::register_controller_type(
  const std::string & motor_type,
  std::function<std::shared_ptr<MotorControllerInterface>()> create_func)
{
  auto & registry = get_registry();
  registry[motor_type] = create_func;

  // Also register lowercase version for compatibility
  std::string lower_type = motor_type;
  std::transform(lower_type.begin(), lower_type.end(), lower_type.begin(), ::tolower);
  registry[lower_type] = create_func;
}

std::vector<std::string> MotorControllerFactory::get_supported_types()
{
  auto & registry = get_registry();
  std::vector<std::string> types;

  for (const auto & pair : registry) {
    types.push_back(pair.first);
  }

  return types;
}

// ConfigurationManager implementation
MotorConfiguration ConfigurationManager::load_configuration(
  const std::string & joint_name,
  const std::string & default_type)
{
  MotorConfiguration config;

  // Set defaults
  config.joint_name = joint_name;
  config.motor_type = default_type;

  // Load configuration from ROS2 parameter server
  // Parameters are expected in the format: motor.<joint_name>.<parameter>
  // Example: motor.joint1.motor_type, motor.joint1.can_id, etc.
  //
  // Note: This method can be called with a node parameter interface for full functionality.
  // When called without a node (standalone), it returns default configuration.
  //
  // To use with ROS2 parameters:
  //   auto node_params = node->get_node_parameters_interface();
  //   config = ConfigurationManager::load_configuration_with_node(
  //     joint_name, default_type, node_params);
  //
  // Parameters can be set via:
  //   - Launch files (YAML parameters)
  //   - ros2 param set /node_name motor.joint1.can_id 141
  //   - config/motors.yaml file loaded at launch

  RCLCPP_WARN(rclcpp::get_logger("motor_control"),
    "[ConfigurationManager] Loading default configuration for joint: %s (type: %s)",
    joint_name.c_str(), default_type.c_str());
  RCLCPP_WARN(rclcpp::get_logger("motor_control"),
    "[ConfigurationManager] To use ROS2 parameters, call load_configuration_with_node()");

  return config;
}

bool ConfigurationManager::save_configuration(
  const std::string & joint_name,
  const MotorConfiguration & config)
{
  // Validate configuration before saving
  std::string error_msg;
  if (!validate_configuration(config, error_msg)) {
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[ConfigurationManager] Invalid configuration for joint %s: %s",
      joint_name.c_str(), error_msg.c_str());
    return false;
  }

  // Save configuration to ROS2 parameter server
  // Parameters are saved in the format: motor.<joint_name>.<parameter>
  //
  // Note: This method validates and prepares config for saving.
  // Actual parameter updates require a node parameter interface.
  //
  // To save with ROS2 parameters:
  //   auto node_params = node->get_node_parameters_interface();
  //   bool success = ConfigurationManager::save_configuration_with_node(
  //     joint_name, config, node_params);
  //
  // This will:
  //   - Set parameters dynamically via ROS2 parameter service
  //   - Update running configuration without restart
  //   - Optionally persist to config/motors.yaml

  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[ConfigurationManager] Configuration validated for joint: %s", joint_name.c_str());
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[ConfigurationManager] - Motor type: %s", config.motor_type.c_str());
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[ConfigurationManager] - CAN ID: %d", static_cast<int>(config.can_id));
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[ConfigurationManager] To persist to ROS2 parameters, call save_configuration_with_node()");

  return true;
}

MotorConfiguration ConfigurationManager::convert_odrive_config(
  const std::map<std::string, double> & odrive_params)
{
  MotorConfiguration config;
  config.motor_type = "odrive";

  // Map ODrive parameters to generic configuration
  auto get_param = [&odrive_params](const std::string & key, double default_val) {
      auto it = odrive_params.find(key);
      return (it != odrive_params.end()) ? it->second : default_val;
    };

  // Basic motor parameters
  config.can_id = static_cast<uint8_t>(get_param("can_id", 0x001));
  config.axis_id = static_cast<uint8_t>(get_param("axis_id", 0));

  // Mechanical configuration
  config.transmission_factor = get_param("transmission_factor", 1.0);
  config.joint_offset = get_param("joint_offset", 0.0);
  config.encoder_offset = get_param("encoder_offset", 0.0);
  config.encoder_resolution = static_cast<int32_t>(get_param("encoder_resolution", 8192));
  config.direction = static_cast<int>(get_param("direction", 1));

  // Control parameters
  config.p_gain = get_param("p_gain", 20.0);
  config.v_gain = get_param("v_gain", 0.16);
  config.v_int_gain = get_param("v_int_gain", 0.32);
  config.current_limit = get_param("current_limit", 10.0);
  config.velocity_limit = get_param("velocity_limit", 10.0);

  // Safety limits
  config.limits.position_min = get_param("position_min", -std::numeric_limits<double>::infinity());
  config.limits.position_max = get_param("position_max", std::numeric_limits<double>::infinity());
  config.limits.velocity_max = get_param("velocity_max", 10.0);
  config.limits.velocity_min = get_param("velocity_min", -10.0);
  config.limits.current_max = get_param("current_max", 10.0);
  config.limits.temperature_max = get_param("temperature_max", 80.0);
  config.limits.error_threshold = get_param("error_threshold", 0.1);

  // Homing configuration
  config.homing.method = static_cast<HomingConfig::HomingMethod>(
    static_cast<int>(get_param("homing_method", HomingConfig::LIMIT_SWITCH_ONLY)));
  config.homing.homing_velocity = get_param("homing_velocity", 1.0);
  config.homing.homing_acceleration = get_param("homing_acceleration", 2.0);
  config.homing.switch_search_velocity = get_param("switch_search_velocity", 0.5);
  config.homing.index_search_velocity = get_param("index_search_velocity", 0.1);
  config.homing.home_offset = get_param("home_offset", 0.0);
  config.homing.limit_switch_pin = static_cast<int>(get_param("limit_switch_pin", -1));
  config.homing.invert_limit_switch = (get_param("invert_limit_switch", 0) != 0);
  config.homing.timeout_seconds = get_param("homing_timeout", 30.0);

  // Store original ODrive parameters for reference
  config.motor_params = odrive_params;

  return config;
}

MotorConfiguration ConfigurationManager::convert_mg6010_config(
  const std::map<std::string, double> & mg6010_params)
{
  MotorConfiguration config;
  config.motor_type = "mg6010";

  // Map MG6010 parameters to generic configuration
  auto get_param = [&mg6010_params](const std::string & key, double default_val) {
      auto it = mg6010_params.find(key);
      return (it != mg6010_params.end()) ? it->second : default_val;
    };

  // Basic motor parameters
  config.can_id = static_cast<uint8_t>(get_param("node_id", 0x01));  // MG6010 uses node_id
  config.axis_id = 0;  // MG6010 typically single axis per controller

  // Mechanical configuration
  config.transmission_factor = get_param("gear_ratio", 1.0);  // MG6010 uses gear_ratio
  config.joint_offset = get_param("position_offset", 0.0);
  config.encoder_offset = get_param("encoder_offset", 0.0);
  config.encoder_resolution = static_cast<int32_t>(get_param("encoder_counts_per_rev", 16384));
  config.direction = static_cast<int>(get_param("direction", 1));

  // Control parameters (MG6010 may use different parameter names)
  config.p_gain = get_param("position_kp", 100.0);  // Typically higher for MG6010
  config.v_gain = get_param("velocity_kp", 0.5);
  config.v_int_gain = get_param("velocity_ki", 1.0);
  config.current_limit = get_param("max_current", 8.0);  // MG6010 current limit
  config.velocity_limit = get_param("max_velocity", 15.0);  // Higher velocity capability

  // Safety limits
  config.limits.position_min = get_param("min_position", -std::numeric_limits<double>::infinity());
  config.limits.position_max = get_param("max_position", std::numeric_limits<double>::infinity());
  config.limits.velocity_max = get_param("max_velocity", 15.0);
  config.limits.velocity_min = get_param("min_velocity", -15.0);
  config.limits.current_max = get_param("max_current", 8.0);
  config.limits.temperature_max = get_param("max_temperature", 85.0);  // Higher temp tolerance
  config.limits.error_threshold = get_param("position_error_limit", 0.05);  // Better accuracy

  // Homing configuration (MG6010 has built-in homing)
  config.homing.method = static_cast<HomingConfig::HomingMethod>(
    static_cast<int>(get_param("homing_method", HomingConfig::LIMIT_SWITCH_AND_INDEX)));
  config.homing.homing_velocity = get_param("homing_speed_high", 2.0);
  config.homing.homing_acceleration = get_param("homing_acceleration", 5.0);
  config.homing.switch_search_velocity = get_param("homing_speed_low", 0.2);
  config.homing.index_search_velocity = get_param("index_search_speed", 0.1);
  config.homing.home_offset = get_param("home_offset", 0.0);
  config.homing.limit_switch_pin = static_cast<int>(get_param("limit_switch_input", 1));  // MG6010 built-in
  config.homing.invert_limit_switch = (get_param("limit_switch_polarity", 0) != 0);
  config.homing.timeout_seconds = get_param("homing_timeout", 60.0);

  // Store original MG6010 parameters for reference
  config.motor_params = mg6010_params;

  return config;
}

bool ConfigurationManager::validate_configuration(
  const MotorConfiguration & config,
  std::string & error_msg)
{
  // Validate basic parameters
  if (config.joint_name.empty()) {
    error_msg = "Joint name cannot be empty";
    return false;
  }

  if (config.motor_type.empty()) {
    error_msg = "Motor type cannot be empty";
    return false;
  }

  if (config.can_id == 0 || config.can_id > 127) {
    error_msg = "CAN ID must be between 1 and 127";
    return false;
  }

  if (config.transmission_factor <= 0.0) {
    error_msg = "Transmission factor must be positive";
    return false;
  }

  if (config.encoder_resolution <= 0) {
    error_msg = "Encoder resolution must be positive";
    return false;
  }

  if (std::abs(config.direction) != 1) {
    error_msg = "Direction must be +1 or -1";
    return false;
  }

  // Validate control parameters
  if (config.p_gain < 0.0) {
    error_msg = "P gain cannot be negative";
    return false;
  }

  if (config.v_gain < 0.0) {
    error_msg = "V gain cannot be negative";
    return false;
  }

  if (config.current_limit <= 0.0) {
    error_msg = "Current limit must be positive";
    return false;
  }

  if (config.velocity_limit <= 0.0) {
    error_msg = "Velocity limit must be positive";
    return false;
  }

  // Validate safety limits
  if (config.limits.position_min >= config.limits.position_max) {
    error_msg = "Position min must be less than position max";
    return false;
  }

  if (config.limits.velocity_min >= config.limits.velocity_max) {
    error_msg = "Velocity min must be less than velocity max";
    return false;
  }

  if (config.limits.current_max <= 0.0) {
    error_msg = "Maximum current must be positive";
    return false;
  }

  if (config.limits.temperature_max <= 0.0) {
    error_msg = "Maximum temperature must be positive";
    return false;
  }

  if (config.limits.error_threshold <= 0.0) {
    error_msg = "Error threshold must be positive";
    return false;
  }

  // Validate homing configuration
  if (config.homing.homing_velocity <= 0.0) {
    error_msg = "Homing velocity must be positive";
    return false;
  }

  if (config.homing.homing_acceleration <= 0.0) {
    error_msg = "Homing acceleration must be positive";
    return false;
  }

  if (config.homing.timeout_seconds <= 0.0) {
    error_msg = "Homing timeout must be positive";
    return false;
  }

  // Validate consistency between parameters
  if (config.current_limit > config.limits.current_max) {
    error_msg = "Current limit exceeds safety maximum current";
    return false;
  }

  if (config.velocity_limit > config.limits.velocity_max) {
    error_msg = "Velocity limit exceeds safety maximum velocity";
    return false;
  }

  return true;
}

} // namespace motor_control_ros2
