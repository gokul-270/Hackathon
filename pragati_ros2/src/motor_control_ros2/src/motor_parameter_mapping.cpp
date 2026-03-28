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
 * MG6010 Parameter Mapping Implementation
 *
 * This file implements utilities to convert ODrive parameters to MG6010 48V
 * equivalents, providing seamless migration while leveraging the enhanced
 * capabilities of MG6010 hardware.
 */

#include "motor_control_ros2/motor_parameter_mapping.hpp"
#include <iostream>
#include <sstream>
#include <algorithm>
#include <cmath>

namespace motor_control_ros2
{

// MotorParameterMapper implementation
MotorConfiguration MotorParameterMapper::convert_odrive_to_mg6010(
  const MotorConfiguration & odrive_config)
{
  MotorConfiguration mg6010_config = odrive_config; // Start with copy

  // Change motor type
  mg6010_config.motor_type = "mg6010";

  // Convert power parameters for 48V operation
  double mg6010_current, mg6010_power;
  convert_power_parameters(odrive_config.current_limit,
                          odrive_config.current_limit * 24.0, // Estimate ODrive power
                          mg6010_current, mg6010_power);

  mg6010_config.current_limit = mg6010_current;
  mg6010_config.velocity_limit = calculate_optimal_velocity_limit(odrive_config.velocity_limit,
                                                                odrive_config.joint_name);

  // Convert control gains for MG6010's better precision
  double mg6010_p, mg6010_v, mg6010_vi;
  convert_control_gains(odrive_config.p_gain, odrive_config.v_gain, odrive_config.v_int_gain,
                       mg6010_p, mg6010_v, mg6010_vi);

  mg6010_config.p_gain = mg6010_p;
  mg6010_config.v_gain = mg6010_v;
  mg6010_config.v_int_gain = mg6010_vi;

  // Upgrade encoder resolution for MG6010's higher precision capability
  mg6010_config.encoder_resolution = get_recommended_encoder_resolution(odrive_config.joint_name,
      "HIGH");

  // Convert safety limits
  mg6010_config.limits = convert_safety_limits(odrive_config.limits);

  // Convert homing configuration
  mg6010_config.homing = convert_homing_config(odrive_config.homing);

  // Add MG6010-specific parameters
  mg6010_config.motor_params = create_mg6010_motor_params(odrive_config);

  // Add 48V specific parameters
  mg6010_config.motor_params["bus_voltage_nominal"] = 48.0;
  mg6010_config.motor_params["bus_voltage_min"] = MG6010_MIN_VOLTAGE_48V;
  mg6010_config.motor_params["bus_voltage_max"] = MG6010_MAX_VOLTAGE_48V;
  mg6010_config.motor_params["max_power_48v"] = mg6010_power;

  return mg6010_config;
}

MotorConfiguration MotorParameterMapper::create_mg6010_default_config(
  const std::string & joint_name,
  uint8_t node_id)
{
  MotorConfiguration config;

  // Basic identification
  config.motor_type = "mg6010";
  config.joint_name = joint_name;
  config.can_id = node_id;
  config.axis_id = 0; // MG6010 is single-axis per controller

  // MG6010 48V optimized parameters
  config.transmission_factor = 1.0; // Will be set per joint
  config.joint_offset = 0.0;
  config.encoder_offset = 0.0;
  config.encoder_resolution = ENCODER_RESOLUTION_HIGH; // 16384 for high precision
  config.direction = 1;

  // 48V optimized control parameters
  config.p_gain = 100.0;   // MG6010 typically uses higher gains
  config.v_gain = 0.5;
  config.v_int_gain = 1.0;
  config.current_limit = 8.0 * CURRENT_SAFETY_MARGIN; // 8A with safety margin
  config.velocity_limit = 15.0; // MG6010 can handle higher velocities

  // 48V safety limits
  config.limits.position_min = -std::numeric_limits<double>::infinity();
  config.limits.position_max = std::numeric_limits<double>::infinity();
  config.limits.velocity_max = 20.0;
  config.limits.velocity_min = -20.0;
  config.limits.current_max = MG6010_MAX_CURRENT_48V;
  config.limits.temperature_max = MG6010_MAX_TEMP_48V * TEMP_SAFETY_MARGIN;
  config.limits.error_threshold = 0.05; // Better precision than ODrive

  // MG6010 optimized homing with built-in capabilities
  config.homing.method = HomingConfig::LIMIT_SWITCH_AND_INDEX;
  config.homing.homing_velocity = 2.0;      // Faster homing
  config.homing.homing_acceleration = 5.0;  // Higher acceleration
  config.homing.switch_search_velocity = 0.2;
  config.homing.index_search_velocity = 0.1;
  config.homing.home_offset = 0.0;
  config.homing.limit_switch_pin = 1;       // MG6010 built-in input
  config.homing.invert_limit_switch = false;
  config.homing.timeout_seconds = 60.0;

  // 48V specific motor parameters
  config.motor_params["bus_voltage_nominal"] = 48.0;
  config.motor_params["bus_voltage_min"] = MG6010_MIN_VOLTAGE_48V;
  config.motor_params["bus_voltage_max"] = MG6010_MAX_VOLTAGE_48V;
  config.motor_params["max_power_48v"] = MG6010_MAX_POWER_48V;
  config.motor_params["encoder_counts_per_rev"] = ENCODER_RESOLUTION_HIGH;
  config.motor_params["gear_ratio"] = 1.0;
  config.motor_params["position_kp"] = config.p_gain;
  config.motor_params["velocity_kp"] = config.v_gain;
  config.motor_params["velocity_ki"] = config.v_int_gain;
  config.motor_params["max_current"] = config.current_limit;
  config.motor_params["max_velocity"] = config.velocity_limit;

  return config;
}

void MotorParameterMapper::convert_power_parameters(
  double odrive_current_limit,
  double odrive_power_limit,
  double & mg6010_current_limit,
  double & mg6010_power_limit)
{
  (void)odrive_current_limit; // Suppress unused parameter warning - may be used in future enhancements

  // Convert from 24V ODrive to 48V MG6010 system
  // Power = Voltage × Current, so for same power at higher voltage, we need less current

  // Calculate equivalent current at 48V for same mechanical power
  double equivalent_current = (odrive_power_limit / 48.0) * POWER_EFFICIENCY_FACTOR;

  // Apply safety margins and hardware limits
  mg6010_current_limit = std::min(equivalent_current * CURRENT_SAFETY_MARGIN,
                                 MG6010_MAX_CURRENT_48V);

  // Calculate available power at 48V
  mg6010_power_limit = std::min(mg6010_current_limit * 48.0,
                               MG6010_MAX_POWER_48V);

  // Ensure we don't exceed MG6010 capabilities
  mg6010_current_limit = std::min(mg6010_current_limit, MG6010_MAX_CURRENT_48V);
  mg6010_power_limit = std::min(mg6010_power_limit, MG6010_MAX_POWER_48V);
}

void MotorParameterMapper::convert_control_gains(
  double odrive_p_gain,
  double odrive_v_gain,
  double odrive_v_int_gain,
  double & mg6010_p_gain,
  double & mg6010_v_gain,
  double & mg6010_v_int_gain)
{
  // MG6010 has better precision and different control characteristics
  // Scale gains appropriately

  mg6010_p_gain = odrive_p_gain * POSITION_GAIN_SCALING;
  mg6010_v_gain = odrive_v_gain * VELOCITY_GAIN_SCALING;
  mg6010_v_int_gain = odrive_v_int_gain * INTEGRAL_GAIN_SCALING;

  // Apply reasonable limits based on MG6010 characteristics
  mg6010_p_gain = std::min(mg6010_p_gain, 500.0);    // Max reasonable P gain
  mg6010_v_gain = std::min(mg6010_v_gain, 2.0);      // Max reasonable V gain
  mg6010_v_int_gain = std::min(mg6010_v_int_gain, 5.0); // Max reasonable I gain
}

HomingConfig MotorParameterMapper::convert_homing_config(const HomingConfig & odrive_homing)
{
  HomingConfig mg6010_homing = odrive_homing; // Start with copy

  // MG6010 has better built-in homing capabilities
  // Upgrade homing method if possible
  if (odrive_homing.method == HomingConfig::LIMIT_SWITCH_ONLY) {
    mg6010_homing.method = HomingConfig::LIMIT_SWITCH_AND_INDEX; // Better precision
  }

  // MG6010 can handle higher homing speeds and accelerations
  mg6010_homing.homing_velocity = std::min(odrive_homing.homing_velocity * 1.5, 3.0);
  mg6010_homing.homing_acceleration = std::min(odrive_homing.homing_acceleration * 2.0, 8.0);
  mg6010_homing.switch_search_velocity = std::min(odrive_homing.switch_search_velocity * 1.2, 1.0);

  // Use MG6010 built-in limit switch input
  if (mg6010_homing.limit_switch_pin <= 0) {
    mg6010_homing.limit_switch_pin = 1; // MG6010 default input
  }

  return mg6010_homing;
}

int32_t MotorParameterMapper::get_recommended_encoder_resolution(
  const std::string & joint_name,
  const std::string & precision_requirement)
{
  // Joint-specific recommendations based on typical requirements
  if (precision_requirement == "ULTRA_HIGH") {
    return ENCODER_RESOLUTION_ULTRA_HIGH; // 32768 for ultimate precision
  }

  if (precision_requirement == "STANDARD") {
    return ENCODER_RESOLUTION_STANDARD;   // 8192 same as ODrive
  }

  // HIGH precision (default)
  // Different joints have different precision needs
  if (joint_name.find("joint2") != std::string::npos) {
    return ENCODER_RESOLUTION_HIGH;       // Base rotation needs high precision
  } else if (joint_name.find("joint3") != std::string::npos) {
    return ENCODER_RESOLUTION_HIGH;       // Shoulder needs high precision
  } else if (joint_name.find("joint4") != std::string::npos) {
    return ENCODER_RESOLUTION_HIGH;       // Elbow needs high precision
  } else if (joint_name.find("joint5") != std::string::npos) {
    return ENCODER_RESOLUTION_ULTRA_HIGH; // Wrist needs ultimate precision
  }

  return ENCODER_RESOLUTION_HIGH; // Default high precision
}

bool MotorParameterMapper::validate_mg6010_config(
  const MotorConfiguration & config,
  std::vector<std::string> & warnings,
  std::vector<std::string> & errors)
{
  warnings.clear();
  errors.clear();

  // Critical errors that must be fixed
  if (config.motor_type != "mg6010" && config.motor_type != "MG6010") {
    errors.push_back("Motor type must be 'mg6010' for MG6010 configuration");
  }

  if (config.can_id == 0 || config.can_id > 127) {
    errors.push_back("CAN node ID must be between 1 and 127");
  }

  if (config.current_limit > MG6010_MAX_CURRENT_48V) {
    errors.push_back("Current limit exceeds MG6010 48V maximum (" +
                    std::to_string(MG6010_MAX_CURRENT_48V) + "A)");
  }

  if (config.limits.temperature_max > MG6010_MAX_TEMP_48V) {
    errors.push_back("Temperature limit exceeds MG6010 48V maximum (" +
                    std::to_string(MG6010_MAX_TEMP_48V) + "°C)");
  }

  // Warnings for non-optimal settings
  if (config.encoder_resolution < ENCODER_RESOLUTION_HIGH) {
    warnings.push_back("Encoder resolution below MG6010 recommended minimum (" +
                      std::to_string(ENCODER_RESOLUTION_HIGH) + " counts/rev)");
  }

  if (config.current_limit < 2.0) {
    warnings.push_back("Current limit very low for 48V system, may limit performance");
  }

  if (config.p_gain < 20.0) {
    warnings.push_back("Position gain low for MG6010, may result in poor tracking");
  }

  if (config.homing.timeout_seconds < 30.0) {
    warnings.push_back("Homing timeout may be too short for reliable operation");
  }

  // Check 48V specific parameters
  if (config.motor_params.count("bus_voltage_nominal") > 0) {
    double nominal_voltage = config.motor_params.at("bus_voltage_nominal");
    if (std::abs(nominal_voltage - 48.0) > 1.0) {
      warnings.push_back("Nominal bus voltage not set to 48V for MG6010");
    }
  }

  return errors.empty(); // Valid if no errors
}

std::string MotorParameterMapper::create_migration_summary(
  const MotorConfiguration & odrive_config,
  const MotorConfiguration & mg6010_config)
{
  std::stringstream summary;

  summary << "=== ODrive to MG6010 48V Migration Summary ===" << std::endl;
  summary << "Joint: " << odrive_config.joint_name << std::endl << std::endl;

  summary << "POWER SYSTEM UPGRADE:" << std::endl;
  summary << "  Voltage:        24V  →  48V" << std::endl;
  summary << "  Current Limit:  " << odrive_config.current_limit << "A  →  "
          << mg6010_config.current_limit << "A" << std::endl;
  summary << "  Max Power:      " << (odrive_config.current_limit * 24.0) << "W  →  "
          << (mg6010_config.current_limit * 48.0) << "W" << std::endl << std::endl;

  summary << "PRECISION IMPROVEMENTS:" << std::endl;
  summary << "  Encoder Res:    " << odrive_config.encoder_resolution << "  →  "
          << mg6010_config.encoder_resolution << " counts/rev" << std::endl;
  summary << "  Position Error: " << odrive_config.limits.error_threshold << "  →  "
          << mg6010_config.limits.error_threshold << " rad" << std::endl << std::endl;

  summary << "CONTROL GAINS:" << std::endl;
  summary << "  P Gain:         " << odrive_config.p_gain << "  →  "
          << mg6010_config.p_gain << std::endl;
  summary << "  V Gain:         " << odrive_config.v_gain << "  →  "
          << mg6010_config.v_gain << std::endl;
  summary << "  VI Gain:        " << odrive_config.v_int_gain << "  →  "
          << mg6010_config.v_int_gain << std::endl << std::endl;

  summary << "PERFORMANCE CAPABILITIES:" << std::endl;
  summary << "  Max Velocity:   " << odrive_config.velocity_limit << "  →  "
          << mg6010_config.velocity_limit << " rad/s" << std::endl;
  summary << "  Max Temperature:" << odrive_config.limits.temperature_max << "  →  "
          << mg6010_config.limits.temperature_max << " °C" << std::endl << std::endl;

  summary << "SAFETY ENHANCEMENTS:" << std::endl;
  summary << "  Hardware Safety: Software only  →  Hardware + Software" << std::endl;
  summary << "  Fault Detection: Basic  →  Advanced built-in diagnostics" << std::endl;
  summary << "  Emergency Stop:  Software  →  Hardware safe torque off" << std::endl << std::endl;

  summary << "EXPECTED BENEFITS:" << std::endl;
  summary << "  ✓ Higher precision positioning" << std::endl;
  summary << "  ✓ Faster response times" << std::endl;
  summary << "  ✓ Better power efficiency" << std::endl;
  summary << "  ✓ Enhanced safety features" << std::endl;
  summary << "  ✓ Reduced heat generation" << std::endl;
  summary << "  ✓ More reliable operation" << std::endl;

  return summary.str();
}

// Helper method implementations
double MotorParameterMapper::calculate_optimal_current_limit(
  double odrive_current,
  const std::string & joint_name)
{
  // Joint-specific current optimization
  double base_current = odrive_current * 0.8; // Start conservative

  // Adjust based on joint requirements
  if (joint_name.find("joint2") != std::string::npos) {
    base_current *= 1.2; // Base rotation needs more torque
  } else if (joint_name.find("joint3") != std::string::npos) {
    base_current *= 1.3; // Shoulder needs most torque
  } else if (joint_name.find("joint4") != std::string::npos) {
    base_current *= 1.0; // Elbow moderate torque
  } else if (joint_name.find("joint5") != std::string::npos) {
    base_current *= 0.8; // Wrist needs less torque, more precision
  }

  return std::min(base_current, MG6010_MAX_CURRENT_48V);
}

double MotorParameterMapper::calculate_optimal_velocity_limit(
  double odrive_velocity,
  const std::string & joint_name)
{
  // MG6010 can generally handle higher velocities
  double mg6010_velocity = odrive_velocity * 1.5;

  // Joint-specific velocity limits
  if (joint_name.find("joint2") != std::string::npos) {
    mg6010_velocity = std::min(mg6010_velocity, 8.0);  // Base rotation limited
  } else if (joint_name.find("joint3") != std::string::npos) {
    mg6010_velocity = std::min(mg6010_velocity, 12.0); // Shoulder can move faster
  } else if (joint_name.find("joint4") != std::string::npos) {
    mg6010_velocity = std::min(mg6010_velocity, 15.0); // Elbow fastest
  } else if (joint_name.find("joint5") != std::string::npos) {
    mg6010_velocity = std::min(mg6010_velocity, 20.0); // Wrist very fast
  }

  return mg6010_velocity;
}

SafetyLimits MotorParameterMapper::convert_safety_limits(const SafetyLimits & odrive_limits)
{
  SafetyLimits mg6010_limits = odrive_limits; // Start with copy

  // Upgrade limits for MG6010 48V capabilities
  mg6010_limits.current_max = std::min(odrive_limits.current_max * 1.2, MG6010_MAX_CURRENT_48V);
  mg6010_limits.temperature_max = std::min(odrive_limits.temperature_max * 1.05,
                                          MG6010_MAX_TEMP_48V * TEMP_SAFETY_MARGIN);
  mg6010_limits.velocity_max = odrive_limits.velocity_max * 1.5; // MG6010 faster
  mg6010_limits.velocity_min = odrive_limits.velocity_min * 1.5;
  mg6010_limits.error_threshold = odrive_limits.error_threshold * 0.5; // Better precision

  return mg6010_limits;
}

std::map<std::string,
  double> MotorParameterMapper::create_mg6010_motor_params(const MotorConfiguration & odrive_config)
{
  std::map<std::string, double> params;

  // Convert ODrive parameters to MG6010 equivalents
  params["node_id"] = odrive_config.can_id;
  params["gear_ratio"] = odrive_config.transmission_factor;
  params["position_offset"] = odrive_config.joint_offset;
  params["encoder_counts_per_rev"] = get_recommended_encoder_resolution(odrive_config.joint_name);
  params["direction"] = odrive_config.direction;

  // MG6010 specific control parameters (CANopen naming)
  params["position_kp"] = odrive_config.p_gain * POSITION_GAIN_SCALING;
  params["velocity_kp"] = odrive_config.v_gain * VELOCITY_GAIN_SCALING;
  params["velocity_ki"] = odrive_config.v_int_gain * INTEGRAL_GAIN_SCALING;

  // 48V power parameters
  params["max_current"] = calculate_optimal_current_limit(odrive_config.current_limit,
      odrive_config.joint_name);
  params["max_velocity"] = calculate_optimal_velocity_limit(odrive_config.velocity_limit,
      odrive_config.joint_name);
  params["max_temperature"] = MG6010_MAX_TEMP_48V * TEMP_SAFETY_MARGIN;
  params["position_error_limit"] = odrive_config.limits.error_threshold * 0.5;

  // Homing parameters
  params["homing_method"] = static_cast<double>(odrive_config.homing.method);
  params["homing_speed_high"] = odrive_config.homing.homing_velocity * 1.5;
  params["homing_speed_low"] = odrive_config.homing.switch_search_velocity * 1.2;
  params["homing_acceleration"] = odrive_config.homing.homing_acceleration * 2.0;
  params["home_offset"] = odrive_config.homing.home_offset;
  params["limit_switch_input"] = std::max(1.0,
      static_cast<double>(odrive_config.homing.limit_switch_pin));
  params["limit_switch_polarity"] = odrive_config.homing.invert_limit_switch ? 1.0 : 0.0;
  params["homing_timeout"] = odrive_config.homing.timeout_seconds;

  return params;
}

// MG6010PresetConfigurations implementation
MotorConfiguration MG6010PresetConfigurations::create_base_mg6010_config(
  const std::string & joint_name,
  uint8_t node_id)
{
  return MotorParameterMapper::create_mg6010_default_config(joint_name, node_id);
}

MotorConfiguration MG6010PresetConfigurations::get_joint2_config(uint8_t node_id)
{
  auto config = create_base_mg6010_config("joint2", node_id);

  // Joint2 (base rotation) specific optimizations
  config.transmission_factor = 5.0;    // High gear ratio for precision
  config.current_limit = 8.0;          // High torque for base rotation
  config.velocity_limit = 8.0;         // Moderate speed for stability
  config.p_gain = 120.0;               // Higher gain for precision
  config.v_gain = 0.6;
  config.v_int_gain = 1.2;

  // Position limits for base rotation (example)
  config.limits.position_min = -M_PI;
  config.limits.position_max = M_PI;

  return config;
}

MotorConfiguration MG6010PresetConfigurations::get_joint3_config(uint8_t node_id)
{
  auto config = create_base_mg6010_config("joint3", node_id);

  // Joint3 (shoulder) specific optimizations
  config.transmission_factor = 8.0;    // Very high gear ratio for power
  config.current_limit = 9.0;          // Maximum current for shoulder
  config.velocity_limit = 12.0;        // Fast movement capability
  config.p_gain = 150.0;               // Highest gain for load handling
  config.v_gain = 0.8;
  config.v_int_gain = 1.5;

  // Shoulder range of motion (example)
  config.limits.position_min = -M_PI / 2;
  config.limits.position_max = M_PI / 2;

  return config;
}

MotorConfiguration MG6010PresetConfigurations::get_joint4_config(uint8_t node_id)
{
  auto config = create_base_mg6010_config("joint4", node_id);

  // Joint4 (elbow) specific optimizations
  config.transmission_factor = 6.0;    // Moderate gear ratio
  config.current_limit = 7.0;          // Medium torque
  config.velocity_limit = 15.0;        // Fast elbow movement
  config.p_gain = 100.0;               // Balanced gain
  config.v_gain = 0.5;
  config.v_int_gain = 1.0;

  // Elbow range of motion (example)
  config.limits.position_min = 0.0;
  config.limits.position_max = M_PI;

  return config;
}

MotorConfiguration MG6010PresetConfigurations::get_joint5_config(uint8_t node_id)
{
  auto config = create_base_mg6010_config("joint5", node_id);

  // Joint5 (wrist) specific optimizations
  config.transmission_factor = 3.0;    // Lower gear ratio for speed
  config.current_limit = 5.0;          // Lower torque, higher precision
  config.velocity_limit = 20.0;        // Fastest movement
  config.encoder_resolution = 32768;   // Ultra-high precision for wrist
  config.p_gain = 80.0;                // Lower gain for smooth operation
  config.v_gain = 0.4;
  config.v_int_gain = 0.8;

  // Better precision for wrist
  config.limits.error_threshold = 0.02; // Very tight tolerance

  // Wrist range of motion (example)
  config.limits.position_min = -2 * M_PI;
  config.limits.position_max = 2 * M_PI;

  return config;
}

std::map<std::string, MotorConfiguration> MG6010PresetConfigurations::get_all_joint_configs()
{
  std::map<std::string, MotorConfiguration> configs;

  // Sequential node IDs starting from 1
  configs["joint2"] = get_joint2_config(1);
  configs["joint3"] = get_joint3_config(2);
  configs["joint4"] = get_joint4_config(3);
  configs["joint5"] = get_joint5_config(4);

  return configs;
}

} // namespace motor_control_ros2
