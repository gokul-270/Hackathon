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

#ifndef ODRIVE_CONTROL_ROS2__MOTOR_PARAMETER_MAPPING_HPP_
#define ODRIVE_CONTROL_ROS2__MOTOR_PARAMETER_MAPPING_HPP_

/*
 * MG6010 Parameter Mapping Utilities
 *
 * This file provides utilities to convert ODrive parameters to MG6010 48V
 * equivalents, enabling seamless migration from ODrive to MG6010 motors
 * while maintaining all existing functionality and improving performance.
 *
 * Key Features:
 * - Automatic parameter conversion from ODrive to MG6010 format
 * - 48V power system considerations
 * - Safety limit adaptations
 * - Mechanical parameter scaling
 * - Configuration validation
 */

#pragma once

#include "motor_control_ros2/motor_abstraction.hpp"
#include <map>
#include <string>
#include <vector>

namespace motor_control_ros2
{

/**
 * @brief MG6010 parameter mapping and conversion utilities
 */
class MotorParameterMapper
{
public:
  /**
   * @brief Convert ODrive configuration to MG6010 configuration
   * @param odrive_config Existing ODrive configuration
   * @return Equivalent MG6010 configuration with 48V adaptations
   */
  static MotorConfiguration convert_odrive_to_mg6010(const MotorConfiguration & odrive_config);

  /**
   * @brief Create default MG6010 configuration for a joint
   * @param joint_name Joint name (e.g., "joint2", "joint3")
   * @param node_id CAN node ID for the MG6010 motor
   * @return Default MG6010 configuration optimized for 48V operation
   */
  static MotorConfiguration create_mg6010_default_config(
    const std::string & joint_name,
    uint8_t node_id);

  /**
   * @brief Convert ODrive power parameters to MG6010 48V equivalents
   * @param odrive_current_limit ODrive current limit (typically 24V based)
   * @param odrive_power_limit ODrive power limit
   * @param mg6010_current_limit [out] MG6010 current limit for 48V
   * @param mg6010_power_limit [out] MG6010 power limit for 48V
   */
  static void convert_power_parameters(
    double odrive_current_limit,
    double odrive_power_limit,
    double & mg6010_current_limit,
    double & mg6010_power_limit);

  /**
   * @brief Convert ODrive control gains to MG6010 equivalents
   * @param odrive_p_gain ODrive proportional gain
   * @param odrive_v_gain ODrive velocity gain
   * @param odrive_v_int_gain ODrive velocity integral gain
   * @param mg6010_p_gain [out] MG6010 position gain
   * @param mg6010_v_gain [out] MG6010 velocity gain
   * @param mg6010_v_int_gain [out] MG6010 velocity integral gain
   */
  static void convert_control_gains(
    double odrive_p_gain,
    double odrive_v_gain,
    double odrive_v_int_gain,
    double & mg6010_p_gain,
    double & mg6010_v_gain,
    double & mg6010_v_int_gain);

  /**
   * @brief Convert ODrive homing configuration to MG6010 equivalent
   * @param odrive_homing ODrive homing configuration
   * @return MG6010 homing configuration with built-in homing features
   */
  static HomingConfig convert_homing_config(const HomingConfig & odrive_homing);

  /**
   * @brief Get recommended MG6010 encoder resolution based on application
   * @param joint_name Joint name for application-specific tuning
   * @param precision_requirement Precision requirement (STANDARD, HIGH, ULTRA_HIGH)
   * @return Recommended encoder resolution
   */
  static int32_t get_recommended_encoder_resolution(
    const std::string & joint_name,
    const std::string & precision_requirement = "HIGH");

  /**
   * @brief Validate MG6010 configuration for 48V operation
   * @param config MG6010 configuration to validate
   * @param warnings [out] Non-critical warnings
   * @param errors [out] Critical errors that must be fixed
   * @return true if configuration is safe for 48V operation
   */
  static bool validate_mg6010_config(
    const MotorConfiguration & config,
    std::vector<std::string> & warnings,
    std::vector<std::string> & errors);

  /**
   * @brief Create migration summary comparing ODrive vs MG6010 configurations
   * @param odrive_config Original ODrive configuration
   * @param mg6010_config Converted MG6010 configuration
   * @return Human-readable migration summary
   */
  static std::string create_migration_summary(
    const MotorConfiguration & odrive_config,
    const MotorConfiguration & mg6010_config);

private:
  // Internal conversion constants

  // Power conversion factors (ODrive 24V -> MG6010 48V)
  static constexpr double VOLTAGE_SCALING_FACTOR = 2.0;  // 48V / 24V
  static constexpr double POWER_EFFICIENCY_FACTOR = 1.1; // MG6010 is ~10% more efficient

  // Control gain conversion factors
  static constexpr double POSITION_GAIN_SCALING = 2.5;   // MG6010 higher precision
  static constexpr double VELOCITY_GAIN_SCALING = 1.8;   // MG6010 better velocity control
  static constexpr double INTEGRAL_GAIN_SCALING = 2.0;   // MG6010 better integration

  // Safety margin factors
  static constexpr double CURRENT_SAFETY_MARGIN = 0.9;   // 10% safety margin
  static constexpr double TEMP_SAFETY_MARGIN = 0.95;     // 5% temperature margin

  // MG6010 48V specific limits
  static constexpr double MG6010_MAX_CURRENT_48V = 10.0;     // Amperes
  static constexpr double MG6010_MAX_POWER_48V = 480.0;      // Watts
  static constexpr double MG6010_MAX_VOLTAGE_48V = 52.0;     // Volts
  static constexpr double MG6010_MIN_VOLTAGE_48V = 44.0;     // Volts
  static constexpr double MG6010_MAX_TEMP_48V = 85.0;        // Celsius

  // Default encoder resolutions for different precision levels
  static constexpr int32_t ENCODER_RESOLUTION_STANDARD = 8192;   // Same as ODrive
  static constexpr int32_t ENCODER_RESOLUTION_HIGH = 16384;      // MG6010 default
  static constexpr int32_t ENCODER_RESOLUTION_ULTRA_HIGH = 32768; // Maximum precision

  // Helper methods
  static double calculate_optimal_current_limit(
    double odrive_current,
    const std::string & joint_name);
  static double calculate_optimal_velocity_limit(
    double odrive_velocity,
    const std::string & joint_name);
  static SafetyLimits convert_safety_limits(const SafetyLimits & odrive_limits);
  static std::map<std::string,
    double> create_mg6010_motor_params(const MotorConfiguration & odrive_config);
};

/**
 * @brief Pre-defined MG6010 configurations for common joint types
 */
class MG6010PresetConfigurations
{
public:
  /**
   * @brief Get optimized MG6010 configuration for joint2 (base rotation)
   * @param node_id CAN node ID
   * @return Optimized configuration for high-torque, precision rotation
   */
  static MotorConfiguration get_joint2_config(uint8_t node_id);

  /**
   * @brief Get optimized MG6010 configuration for joint3 (shoulder)
   * @param node_id CAN node ID
   * @return Optimized configuration for high-power arm movement
   */
  static MotorConfiguration get_joint3_config(uint8_t node_id);

  /**
   * @brief Get optimized MG6010 configuration for joint4 (elbow)
   * @param node_id CAN node ID
   * @return Optimized configuration for medium-power precision
   */
  static MotorConfiguration get_joint4_config(uint8_t node_id);

  /**
   * @brief Get optimized MG6010 configuration for joint5 (wrist)
   * @param node_id CAN node ID
   * @return Optimized configuration for high-precision, low-power
   */
  static MotorConfiguration get_joint5_config(uint8_t node_id);

  /**
   * @brief Get all standard joint configurations
   * @return Map of joint_name -> MotorConfiguration with sequential node IDs
   */
  static std::map<std::string, MotorConfiguration> get_all_joint_configs();

private:
  // Base configuration template for all MG6010 motors
  static MotorConfiguration create_base_mg6010_config(
    const std::string & joint_name,
    uint8_t node_id);
};

} // namespace motor_control_ros2

#endif // ODRIVE_CONTROL_ROS2__MOTOR_PARAMETER_MAPPING_HPP_
