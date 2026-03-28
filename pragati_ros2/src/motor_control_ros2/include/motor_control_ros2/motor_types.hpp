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

#ifndef MOTOR_CONTROL_ROS2__MOTOR_TYPES_HPP_
#define MOTOR_CONTROL_ROS2__MOTOR_TYPES_HPP_

#pragma once

#include <string>
#include <vector>
#include <map>
#include <chrono>
#include <cstdint>
#include <limits>

#include "motor_control_ros2/error_handling.hpp"

namespace motor_control_ros2
{

/**
 * @brief Motor status information with enhanced error handling
 */
struct MotorStatus
{
  enum State
  {
    UNKNOWN = 0,
    IDLE,
    STARTUP,
    MOTOR_CALIBRATION,
    ENCODER_CALIBRATION,
    CLOSED_LOOP_CONTROL,
    LOCKIN_SPIN,
    ENCODER_DIR_FIND,
    HOMING,
    ENCODER_OFFSET_CALIBRATION,
    AXIS_ERROR
  };

  State state = UNKNOWN;
  bool hardware_connected = false;
  bool motor_enabled = false;
  bool encoder_ready = false;

  // Enhanced error information
  ErrorFramework::ErrorInfo current_error;
  std::vector<ErrorFramework::ErrorInfo> error_history;

  // Legacy support (deprecated - use current_error instead)
  uint32_t error_code = 0;  // Deprecated
  std::string error_message = "";  // Deprecated

  // System status
  double temperature = 0.0;
  double voltage = 0.0;
  double current = 0.0;
  std::chrono::steady_clock::time_point last_update;

  // Health indicators
  double health_score = 1.0;  // 0.0 = critical, 1.0 = perfect
  bool requires_attention = false;
  std::vector<std::string> warnings;
};

/**
 * @brief Safety limits for motor operation
 */
struct SafetyLimits
{
  // Safe finite defaults (task 4.2): ±90° ≈ ±1.5708 rad.
  // Previous ±infinity meant any commanded position was "within limits".
  double position_min = -1.5708;
  double position_max = 1.5708;
  double velocity_max = 10.0;
  double velocity_min = -10.0;
  double current_max = 10.0;
  double temperature_max = 80.0;
  double error_threshold = 0.1;  // Position error threshold
};

/**
 * @brief Homing configuration
 */
struct HomingConfig
{
  enum HomingMethod
  {
    LIMIT_SWITCH_ONLY = 1,
    ENCODER_INDEX_ONLY = 2,
    LIMIT_SWITCH_AND_INDEX = 3,
    MECHANICAL_STOP = 4,
    ABSOLUTE_ENCODER = 5
  };

  HomingMethod method = LIMIT_SWITCH_ONLY;
  double homing_velocity = 1.0;      // m/s
  double homing_acceleration = 2.0;   // m/s²
  double switch_search_velocity = 0.5; // m/s for limit switch search
  double index_search_velocity = 0.1;  // m/s for encoder index search
  double home_offset = 0.0;           // Offset from home position
  int limit_switch_pin = -1;          // GPIO pin for limit switch (-1 = disabled)
  bool invert_limit_switch = false;   // True if switch is active low
  double timeout_seconds = 30.0;      // Homing timeout
};

/**
 * @brief Complete motor configuration
 */
struct MotorConfiguration
{
  // Motor identification
  std::string motor_type = "odrive";  // "odrive", "mg6010", etc.
  std::string joint_name = "";
  uint8_t can_id = 0x001;
  uint8_t axis_id = 0;

  // Mechanical configuration
  double transmission_factor = 1.0;   // Gear ratio (motor_pos = joint_pos / transmission_factor)
  double joint_offset = 0.0;          // Joint position offset (radians)
  double encoder_offset = 0.0;        // Encoder position offset
  int32_t encoder_resolution = 8192;  // Encoder counts per revolution
  int direction = 1;                  // Motor direction multiplier (+1 or -1)

  // Control parameters
  double p_gain = 20.0;
  double v_gain = 0.16;
  double v_int_gain = 0.32;
  double current_limit = 10.0;
  double velocity_limit = 10.0;

  // Safety and limits
  SafetyLimits limits;
  HomingConfig homing;

  // Motor-specific parameters (key-value pairs for extensibility)
  std::map<std::string, double> motor_params;
  std::map<std::string, std::string> motor_strings;
};

} // namespace motor_control_ros2

#endif // MOTOR_CONTROL_ROS2__MOTOR_TYPES_HPP_
