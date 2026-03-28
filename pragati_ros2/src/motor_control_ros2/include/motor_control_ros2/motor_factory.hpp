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

#ifndef MOTOR_CONTROL_ROS2__MOTOR_FACTORY_HPP_
#define MOTOR_CONTROL_ROS2__MOTOR_FACTORY_HPP_

#pragma once

#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "motor_control_ros2/motor_controller_interface.hpp"

namespace motor_control_ros2
{

/**
 * @brief Factory for creating motor controllers
 */
class MotorControllerFactory
{
public:
  /**
   * @brief Create motor controller based on type
   * @param motor_type Motor type string ("odrive", "mg6010", etc.)
   * @return Shared pointer to motor controller, or nullptr if type not supported
   */
  static std::shared_ptr<MotorControllerInterface> create_controller(
    const std::string & motor_type);

  /**
   * @brief Register new motor controller type
   * @param motor_type Type name
   * @param create_func Factory function
   */
  static void register_controller_type(
    const std::string & motor_type,
    std::function<std::shared_ptr<MotorControllerInterface>()> create_func);

  /**
   * @brief Get list of supported motor types
   * @return Vector of supported type names
   */
  static std::vector<std::string> get_supported_types();

private:
  static std::map<std::string,
    std::function<std::shared_ptr<MotorControllerInterface>()>> & get_registry();
};

/**
 * @brief Configuration manager for motor parameters
 */
class ConfigurationManager
{
public:
  /**
   * @brief Load motor configuration from parameter server/file
   * @param joint_name Joint name to load configuration for
   * @param default_type Default motor type if not specified
   * @return Motor configuration
   */
  static MotorConfiguration load_configuration(
    const std::string & joint_name,
    const std::string & default_type = "odrive");

  /**
   * @brief Save motor configuration
   * @param joint_name Joint name
   * @param config Configuration to save
   * @return true if successful
   */
  static bool save_configuration(const std::string & joint_name, const MotorConfiguration & config);

  /**
   * @brief Convert ODrive parameters to generic configuration
   * @param odrive_params ODrive-specific parameters
   * @return Generic motor configuration
   */
  static MotorConfiguration convert_odrive_config(
    const std::map<std::string,
    double> & odrive_params);

  /**
   * @brief Convert MG6010 parameters to generic configuration
   * @param mg6010_params MG6010-specific parameters
   * @return Generic motor configuration
   */
  static MotorConfiguration convert_mg6010_config(
    const std::map<std::string,
    double> & mg6010_params);

  /**
   * @brief Validate configuration parameters
   * @param config Configuration to validate
   * @param error_msg [out] Error message if validation fails
   * @return true if configuration is valid
   */
  static bool validate_configuration(const MotorConfiguration & config, std::string & error_msg);
};

} // namespace motor_control_ros2

#endif // MOTOR_CONTROL_ROS2__MOTOR_FACTORY_HPP_
