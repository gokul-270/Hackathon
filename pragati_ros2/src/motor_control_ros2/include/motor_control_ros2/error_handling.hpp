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

#ifndef MOTOR_CONTROL_ROS2__ERROR_HANDLING_HPP_
#define MOTOR_CONTROL_ROS2__ERROR_HANDLING_HPP_

#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

namespace motor_control_ros2
{

// Forward declaration to avoid circular dependency with motor_types.hpp
struct MotorConfiguration;

/**
 * @brief Enhanced error handling framework
 */
namespace ErrorFramework
{
  /**
   * @brief Comprehensive error categories for motor control
   */
enum class ErrorCategory : uint8_t
{
  NONE = 0,
  COMMUNICATION = 1,
  HARDWARE = 2,
  ENCODER = 3,
  CONTROL = 4,
  SAFETY = 5,
  INITIALIZATION = 6,
  THERMAL = 7,
  POWER = 8
};

  /**
   * @brief Error severity levels
   */
enum class ErrorSeverity : uint8_t
{
  INFO = 0,
  WARNING = 1,
  ERROR = 2,
  CRITICAL = 3,
  FATAL = 4
};

  /**
   * @brief Comprehensive error information
   */
struct ErrorInfo
{
  ErrorCategory category = ErrorCategory::NONE;
  ErrorSeverity severity = ErrorSeverity::INFO;
  uint32_t code = 0;
  std::string message = "";
  std::string recovery_suggestion = "";
  std::chrono::steady_clock::time_point timestamp;
  uint32_t occurrence_count = 0;
  bool can_auto_recover = false;
  std::map<std::string, std::string> context_data;
};

  /**
   * @brief Error recovery result
   */
struct RecoveryResult
{
  bool success = false;
  std::string action_taken = "";
  std::string next_suggestion = "";
  uint32_t attempts_made = 0;
  std::chrono::steady_clock::time_point recovery_time;
};
}

/**
 * @brief Error handler interface for pluggable error handling
 */
class ErrorHandler
{
public:
  virtual ~ErrorHandler() = default;

  /**
   * @brief Handle motor error with context
   * @param error_info Detailed error information
   * @param motor_config Motor configuration for context
   * @return Recovery result
   */
  virtual ErrorFramework::RecoveryResult handle_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config) = 0;

  /**
   * @brief Check if error can be automatically recovered
   * @param error_info Error information to check
   * @return True if auto-recovery is possible
   */
  virtual bool can_auto_recover(const ErrorFramework::ErrorInfo & error_info) const = 0;

  /**
   * @brief Get recovery suggestion for specific error
   * @param error_info Error information
   * @return Human-readable recovery suggestion
   */
  virtual std::string get_recovery_suggestion(
    const ErrorFramework::ErrorInfo & error_info) const = 0;

  /**
   * @brief Log error with appropriate severity
   * @param error_info Error information to log
   */
  virtual void log_error(const ErrorFramework::ErrorInfo & error_info) const = 0;
};

/**
 * @brief Default error handler implementation
 */
class DefaultErrorHandler : public ErrorHandler
{
private:
  mutable std::mutex error_mutex_;
  std::map<std::pair<ErrorFramework::ErrorCategory, uint32_t>, uint32_t> error_counts_;
  std::chrono::steady_clock::time_point last_recovery_attempt_;
  uint32_t recovery_attempts_count_ = 0;

public:
  ErrorFramework::RecoveryResult handle_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config) override;

  bool can_auto_recover(const ErrorFramework::ErrorInfo & error_info) const override;
  std::string get_recovery_suggestion(const ErrorFramework::ErrorInfo & error_info) const override;
  void log_error(const ErrorFramework::ErrorInfo & error_info) const override;

private:
  void update_error_statistics(const ErrorFramework::ErrorInfo & error_info);
  bool should_attempt_recovery(const ErrorFramework::ErrorInfo & error_info) const;
  std::string get_category_name(ErrorFramework::ErrorCategory category) const;
  std::string get_severity_name(ErrorFramework::ErrorSeverity severity) const;

  // Category-specific recovery handlers
  ErrorFramework::RecoveryResult handle_communication_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
  ErrorFramework::RecoveryResult handle_hardware_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
  ErrorFramework::RecoveryResult handle_encoder_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
  ErrorFramework::RecoveryResult handle_control_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
  ErrorFramework::RecoveryResult handle_safety_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
  ErrorFramework::RecoveryResult handle_initialization_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
  ErrorFramework::RecoveryResult handle_thermal_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
  ErrorFramework::RecoveryResult handle_power_error(
    const ErrorFramework::ErrorInfo & error_info,
    const MotorConfiguration & motor_config);
};

/**
 * @brief Error factory for creating specific error types
 */
class ErrorFactory
{
public:
  // Communication errors
  static ErrorFramework::ErrorInfo create_communication_timeout_error(
    const std::string & details = "");
  static ErrorFramework::ErrorInfo create_can_bus_error(
    uint32_t can_error_code,
    const std::string & details = "");
  static ErrorFramework::ErrorInfo create_connection_lost_error(const std::string & details = "");

  // Hardware errors
  static ErrorFramework::ErrorInfo create_motor_overcurrent_error(double current, double limit);
  static ErrorFramework::ErrorInfo create_motor_overheat_error(double temperature, double limit);
  static ErrorFramework::ErrorInfo create_encoder_failure_error(const std::string & encoder_type);

  // Control errors
  static ErrorFramework::ErrorInfo create_position_limit_error(
    double position, double limit_min,
    double limit_max);
  static ErrorFramework::ErrorInfo create_velocity_limit_error(double velocity, double limit);
  static ErrorFramework::ErrorInfo create_control_loop_instability_error(
    const std::string & details = "");

  // Safety errors
  static ErrorFramework::ErrorInfo create_emergency_stop_error(const std::string & trigger_reason);
  static ErrorFramework::ErrorInfo create_safety_violation_error(
    const std::string & violation_type);

  // Initialization errors
  static ErrorFramework::ErrorInfo create_homing_failure_error(const std::string & reason);
  static ErrorFramework::ErrorInfo create_calibration_failure_error(
    const std::string & calibration_type);

private:
  static ErrorFramework::ErrorInfo create_error(
    ErrorFramework::ErrorCategory category,
    ErrorFramework::ErrorSeverity severity,
    uint32_t code,
    const std::string & message,
    const std::string & recovery_suggestion = "",
    bool can_auto_recover = false);
};

} // namespace motor_control_ros2

#endif // MOTOR_CONTROL_ROS2__ERROR_HANDLING_HPP_
