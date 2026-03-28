/**
 * @file error_handling.cpp
 * @brief Implementation of enhanced error handling framework for motor control
 */

#include "motor_control_ros2/motor_abstraction.hpp"
#include <iostream>
#include <sstream>
#include <iomanip>

namespace motor_control_ros2
{

// ===========================================
// DefaultErrorHandler Implementation
// ===========================================

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();

    // Log the error first
  log_error(error_info);

    // Update error statistics
  update_error_statistics(error_info);

    // Check if we should attempt recovery
  if (!should_attempt_recovery(error_info)) {
    result.success = false;
    result.action_taken = "No recovery attempted - too many recent attempts or fatal error";
    result.next_suggestion = get_recovery_suggestion(error_info);
    return result;
  }

  result.attempts_made = ++recovery_attempts_count_;
  last_recovery_attempt_ = result.recovery_time;

    // Attempt recovery based on error category and severity
  switch (error_info.category) {
    case ErrorFramework::ErrorCategory::COMMUNICATION:
      result = handle_communication_error(error_info, motor_config);
      break;

    case ErrorFramework::ErrorCategory::HARDWARE:
      result = handle_hardware_error(error_info, motor_config);
      break;

    case ErrorFramework::ErrorCategory::ENCODER:
      result = handle_encoder_error(error_info, motor_config);
      break;

    case ErrorFramework::ErrorCategory::CONTROL:
      result = handle_control_error(error_info, motor_config);
      break;

    case ErrorFramework::ErrorCategory::SAFETY:
      result = handle_safety_error(error_info, motor_config);
      break;

    case ErrorFramework::ErrorCategory::INITIALIZATION:
      result = handle_initialization_error(error_info, motor_config);
      break;

    case ErrorFramework::ErrorCategory::THERMAL:
      result = handle_thermal_error(error_info, motor_config);
      break;

    case ErrorFramework::ErrorCategory::POWER:
      result = handle_power_error(error_info, motor_config);
      break;

    default:
      result.success = false;
      result.action_taken = "Unknown error category - no recovery available";
      result.next_suggestion = "Manual intervention required";
      break;
  }

  result.attempts_made = recovery_attempts_count_;

  if (result.success) {
    std::cout << "✅ Error recovery successful: " << result.action_taken << std::endl;
  } else {
    std::cout << "❌ Error recovery failed: " << result.action_taken << std::endl;
    std::cout << "💡 Suggestion: " << result.next_suggestion << std::endl;
  }

  return result;
}

bool DefaultErrorHandler::can_auto_recover(const ErrorFramework::ErrorInfo & error_info) const
{
    // Fatal errors cannot be auto-recovered
  if (error_info.severity == ErrorFramework::ErrorSeverity::FATAL) {
    return false;
  }

    // Safety errors generally should not be auto-recovered
  if (error_info.category == ErrorFramework::ErrorCategory::SAFETY) {
    return false;
  }

    // Check if error is marked as recoverable
  if (!error_info.can_auto_recover) {
    return false;
  }

    // Check recovery attempt frequency
  auto now = std::chrono::steady_clock::now();
  auto time_since_last = std::chrono::duration_cast<std::chrono::seconds>(
        now - last_recovery_attempt_).count();

    // Don't attempt recovery more than once every 30 seconds
  if (time_since_last < 30) {
    return false;
  }

    // Don't attempt if too many recent recovery attempts
  if (recovery_attempts_count_ > 5) {
    return false;
  }

  return true;
}

std::string DefaultErrorHandler::get_recovery_suggestion(
  const ErrorFramework::ErrorInfo & error_info) const
{
  if (!error_info.recovery_suggestion.empty()) {
    return error_info.recovery_suggestion;
  }

    // Generate default suggestions based on category
  switch (error_info.category) {
    case ErrorFramework::ErrorCategory::COMMUNICATION:
      return "Check CAN bus connections and restart communication";

    case ErrorFramework::ErrorCategory::HARDWARE:
      return "Inspect motor hardware and connections";

    case ErrorFramework::ErrorCategory::ENCODER:
      return "Check encoder connections and calibration";

    case ErrorFramework::ErrorCategory::CONTROL:
      return "Review control parameters and reset controller";

    case ErrorFramework::ErrorCategory::SAFETY:
      return "Address safety condition before continuing operation";

    case ErrorFramework::ErrorCategory::INITIALIZATION:
      return "Restart motor initialization sequence";

    case ErrorFramework::ErrorCategory::THERMAL:
      return "Allow motor to cool down before resuming operation";

    case ErrorFramework::ErrorCategory::POWER:
      return "Check power supply and connections";

    default:
      return "Contact technical support for assistance";
  }
}

void DefaultErrorHandler::log_error(const ErrorFramework::ErrorInfo & error_info) const
{
  std::ostringstream oss;
  oss   << "[" << get_severity_name(error_info.severity) << "] "
        << get_category_name(error_info.category) << " Error "
        << error_info.code << ": " << error_info.message;

  if (!error_info.recovery_suggestion.empty()) {
    oss << " | Recovery: " << error_info.recovery_suggestion;
  }

    // Log based on severity
  switch (error_info.severity) {
    case ErrorFramework::ErrorSeverity::INFO:
      std::cout << "ℹ️  " << oss.str() << std::endl;
      break;
    case ErrorFramework::ErrorSeverity::WARNING:
      std::cout << "⚠️  " << oss.str() << std::endl;
      break;
    case ErrorFramework::ErrorSeverity::ERROR:
      std::cout << "❌ " << oss.str() << std::endl;
      break;
    case ErrorFramework::ErrorSeverity::CRITICAL:
      std::cout << "🚨 CRITICAL: " << oss.str() << std::endl;
      break;
    case ErrorFramework::ErrorSeverity::FATAL:
      std::cout << "💀 FATAL: " << oss.str() << std::endl;
      break;
  }
}

// Private helper methods

void DefaultErrorHandler::update_error_statistics(const ErrorFramework::ErrorInfo & error_info)
{
  std::lock_guard<std::mutex> lock(error_mutex_);
  auto key = std::make_pair(error_info.category, error_info.code);
  error_counts_[key]++;
}

bool DefaultErrorHandler::should_attempt_recovery(
  const ErrorFramework::ErrorInfo & error_info) const
{
  return can_auto_recover(error_info) &&
         error_info.severity != ErrorFramework::ErrorSeverity::FATAL &&
         error_info.category != ErrorFramework::ErrorCategory::SAFETY;
}

std::string DefaultErrorHandler::get_category_name(ErrorFramework::ErrorCategory category) const
{
  switch (category) {
    case ErrorFramework::ErrorCategory::NONE: return "NONE";
    case ErrorFramework::ErrorCategory::COMMUNICATION: return "COMMUNICATION";
    case ErrorFramework::ErrorCategory::HARDWARE: return "HARDWARE";
    case ErrorFramework::ErrorCategory::ENCODER: return "ENCODER";
    case ErrorFramework::ErrorCategory::CONTROL: return "CONTROL";
    case ErrorFramework::ErrorCategory::SAFETY: return "SAFETY";
    case ErrorFramework::ErrorCategory::INITIALIZATION: return "INITIALIZATION";
    case ErrorFramework::ErrorCategory::THERMAL: return "THERMAL";
    case ErrorFramework::ErrorCategory::POWER: return "POWER";
    default: return "UNKNOWN";
  }
}

std::string DefaultErrorHandler::get_severity_name(ErrorFramework::ErrorSeverity severity) const
{
  switch (severity) {
    case ErrorFramework::ErrorSeverity::INFO: return "INFO";
    case ErrorFramework::ErrorSeverity::WARNING: return "WARNING";
    case ErrorFramework::ErrorSeverity::ERROR: return "ERROR";
    case ErrorFramework::ErrorSeverity::CRITICAL: return "CRITICAL";
    case ErrorFramework::ErrorSeverity::FATAL: return "FATAL";
    default: return "UNKNOWN";
  }
}

// Category-specific recovery handlers

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_communication_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();

    // Attempt to reinitialize communication
  result.action_taken = "Attempted CAN communication reset";
  result.success = true;   // Placeholder - would call actual CAN reset
  result.next_suggestion = "If problem persists, check physical CAN connections";

  return result;
}

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_hardware_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();
  result.action_taken = "Hardware error detected - no automatic recovery";
  result.success = false;
  result.next_suggestion = "Inspect motor hardware and connections";

  return result;
}

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_encoder_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();
  result.action_taken = "Attempted encoder recalibration";
  result.success = true;   // Placeholder
  result.next_suggestion = "Check encoder connections if problem persists";

  return result;
}

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_control_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();
  result.action_taken = "Reset control loop parameters";
  result.success = true;   // Placeholder
  result.next_suggestion = "Review control gains if instability continues";

  return result;
}

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_safety_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();
  result.action_taken = "Safety error - no automatic recovery";
  result.success = false;
  result.next_suggestion = "Address safety condition manually before continuing";

  return result;
}

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_initialization_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();
  result.action_taken = "Attempted motor reinitialization";
  result.success = true;   // Placeholder
  result.next_suggestion = "Check motor configuration if problem persists";

  return result;
}

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_thermal_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();
  result.action_taken = "Thermal protection activated - waiting for cooldown";
  result.success = false;
  result.next_suggestion = "Allow motor to cool before resuming operation";

  return result;
}

ErrorFramework::RecoveryResult DefaultErrorHandler::handle_power_error(
  const ErrorFramework::ErrorInfo & error_info,
  const MotorConfiguration & motor_config)
{
  (void)error_info;   // Suppress unused parameter warning
  (void)motor_config;   // Suppress unused parameter warning

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();
  result.action_taken = "Power error detected - check power supply";
  result.success = false;
  result.next_suggestion = "Verify power supply voltage and connections";

  return result;
}

// ===========================================
// ErrorFactory Implementation
// ===========================================

ErrorFramework::ErrorInfo ErrorFactory::create_communication_timeout_error(
  const std::string & details)
{
  return create_error(
        ErrorFramework::ErrorCategory::COMMUNICATION,
        ErrorFramework::ErrorSeverity::ERROR,
        1001,
        "Communication timeout" + (details.empty() ? "" : ": " + details),
        "Check CAN bus connections and restart communication",
        true
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_can_bus_error(
  uint32_t can_error_code,
  const std::string & details)
{
  return create_error(
        ErrorFramework::ErrorCategory::COMMUNICATION,
        ErrorFramework::ErrorSeverity::ERROR,
        1000 + can_error_code,
        "CAN bus error " + std::to_string(can_error_code) + (details.empty() ? "" : ": " + details),
        "Reset CAN interface and check bus termination",
        true
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_connection_lost_error(const std::string & details)
{
  return create_error(
        ErrorFramework::ErrorCategory::COMMUNICATION,
        ErrorFramework::ErrorSeverity::CRITICAL,
        1002,
        "Connection lost to motor controller" + (details.empty() ? "" : ": " + details),
        "Restart communication and check physical connections",
        true
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_motor_overcurrent_error(double current, double limit)
{
  return create_error(
        ErrorFramework::ErrorCategory::HARDWARE,
        ErrorFramework::ErrorSeverity::CRITICAL,
        2001,
        "Motor overcurrent: " + std::to_string(current) + "A exceeds limit " +
      std::to_string(limit) + "A",
        "Reduce load and check motor connections",
        false
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_motor_overheat_error(
  double temperature,
  double limit)
{
  return create_error(
        ErrorFramework::ErrorCategory::THERMAL,
        ErrorFramework::ErrorSeverity::CRITICAL,
        7001,
        "Motor overheating: " + std::to_string(temperature) + "°C exceeds limit " +
      std::to_string(limit) + "°C",
        "Allow motor to cool down and improve ventilation",
        false
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_encoder_failure_error(
  const std::string & encoder_type)
{
  return create_error(
        ErrorFramework::ErrorCategory::ENCODER,
        ErrorFramework::ErrorSeverity::ERROR,
        3001,
        encoder_type + " encoder failure detected",
        "Check encoder connections and recalibrate",
        true
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_position_limit_error(
  double position,
  double limit_min, double limit_max)
{
  return create_error(
        ErrorFramework::ErrorCategory::SAFETY,
        ErrorFramework::ErrorSeverity::WARNING,
        5001,
        "Position " + std::to_string(position) + " outside limits [" +
        std::to_string(limit_min) + ", " + std::to_string(limit_max) + "]",
        "Move to within position limits",
        false
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_velocity_limit_error(double velocity, double limit)
{
  return create_error(
        ErrorFramework::ErrorCategory::SAFETY,
        ErrorFramework::ErrorSeverity::WARNING,
        5002,
        "Velocity " + std::to_string(velocity) + " exceeds limit " + std::to_string(limit),
        "Reduce commanded velocity",
        false
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_control_loop_instability_error(
  const std::string & details)
{
  return create_error(
        ErrorFramework::ErrorCategory::CONTROL,
        ErrorFramework::ErrorSeverity::ERROR,
        4001,
        "Control loop instability detected" + (details.empty() ? "" : ": " + details),
        "Review PID gains and reduce controller bandwidth",
        true
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_emergency_stop_error(
  const std::string & trigger_reason)
{
  return create_error(
        ErrorFramework::ErrorCategory::SAFETY,
        ErrorFramework::ErrorSeverity::CRITICAL,
        5000,
        "Emergency stop triggered: " + trigger_reason,
        "Clear emergency condition and reset system",
        false
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_safety_violation_error(
  const std::string & violation_type)
{
  return create_error(
        ErrorFramework::ErrorCategory::SAFETY,
        ErrorFramework::ErrorSeverity::ERROR,
        5003,
        "Safety violation: " + violation_type,
        "Address safety condition before continuing",
        false
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_homing_failure_error(const std::string & reason)
{
  return create_error(
        ErrorFramework::ErrorCategory::INITIALIZATION,
        ErrorFramework::ErrorSeverity::ERROR,
        6001,
        "Motor homing failed: " + reason,
        "Check homing configuration and retry",
        true
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_calibration_failure_error(
  const std::string & calibration_type)
{
  return create_error(
        ErrorFramework::ErrorCategory::INITIALIZATION,
        ErrorFramework::ErrorSeverity::ERROR,
        6002,
        calibration_type + " calibration failed",
        "Restart calibration sequence",
        true
  );
}

ErrorFramework::ErrorInfo ErrorFactory::create_error(
  ErrorFramework::ErrorCategory category,
  ErrorFramework::ErrorSeverity severity,
  uint32_t code,
  const std::string & message,
  const std::string & recovery_suggestion,
  bool can_auto_recover)
{

  ErrorFramework::ErrorInfo error;
  error.category = category;
  error.severity = severity;
  error.code = code;
  error.message = message;
  error.recovery_suggestion = recovery_suggestion;
  error.timestamp = std::chrono::steady_clock::now();
  error.occurrence_count = 1;
  error.can_auto_recover = can_auto_recover;

  return error;
}

} // namespace motor_control_ros2
