/*
 * Comprehensive Motor Control Error Handling System
 *
 * This system provides:
 * 1. Complete error classification and severity assessment
 * 2. Automatic error recovery mechanisms with retry logic
 * 3. Fail-safe behaviors and graceful degradation
 * 4. Error logging and reporting for diagnostics
 * 5. Predictive error detection and prevention
 */

#pragma once

#include "motor_abstraction.hpp"
#include "enhanced_can_interface.hpp"
#include <memory>
#include <unordered_map>
#include <functional>
#include <queue>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>

namespace motor_control_ros2
{

// =============================================================================
// COMPREHENSIVE ERROR CLASSIFICATION
// =============================================================================

/**
 * @brief Detailed motor error codes with comprehensive coverage
 */
enum class MotorErrorCode : uint32_t
{
  // System Status (0x0000 series)
  NO_ERROR = 0x0000,
  GENERIC_ERROR = 0x0001,
  SYSTEM_INITIALIZING = 0x0002,
  SYSTEM_READY = 0x0003,

  // Communication Errors (0x1000 series)
  CAN_TIMEOUT = 0x1001,
  CAN_BUS_OFF = 0x1002,
  CAN_ERROR_PASSIVE = 0x1003,
  CAN_OVERRUN = 0x1004,
  NODE_NOT_RESPONDING = 0x1005,
  PROTOCOL_MISMATCH = 0x1006,
  MESSAGE_CORRUPTION = 0x1007,
  COMMUNICATION_LOST = 0x1008,

  // Motor Hardware Errors (0x2000 series)
  MOTOR_OVERCURRENT = 0x2001,
  MOTOR_OVERVOLTAGE = 0x2002,
  MOTOR_UNDERVOLTAGE = 0x2003,
  MOTOR_OVERTEMPERATURE = 0x2004,
  MOTOR_PHASE_FAILURE = 0x2005,
  MOTOR_SHORT_CIRCUIT = 0x2006,
  MOTOR_STALL_DETECTED = 0x2007,
  INVERTER_FAULT = 0x2008,
  BRAKE_RESISTOR_FAULT = 0x2009,

  // Encoder Errors (0x3000 series)
  ENCODER_COMMUNICATION_ERROR = 0x3001,
  ENCODER_NOT_CALIBRATED = 0x3002,
  ENCODER_COUNT_INVALID = 0x3003,
  ENCODER_INDEX_NOT_FOUND = 0x3004,
  DUAL_ENCODER_MISMATCH = 0x3005,
  ENCODER_SIGNAL_WEAK = 0x3006,
  ENCODER_MECHANICAL_FAULT = 0x3007,
  ABSOLUTE_ENCODER_ERROR = 0x3008,

  // Control System Errors (0x4000 series)
  POSITION_LIMIT_VIOLATION = 0x4001,
  VELOCITY_LIMIT_VIOLATION = 0x4002,
  ACCELERATION_LIMIT_VIOLATION = 0x4003,
  TORQUE_LIMIT_VIOLATION = 0x4004,
  FOLLOWING_ERROR_EXCESSIVE = 0x4005,
  CONTROL_LOOP_UNSTABLE = 0x4006,
  PID_WINDUP_DETECTED = 0x4007,
  TRAJECTORY_ERROR = 0x4008,

  // Safety System Errors (0x5000 series)
  EMERGENCY_STOP_TRIGGERED = 0x5001,
  SAFETY_CIRCUIT_FAULT = 0x5002,
  WATCHDOG_TIMEOUT = 0x5003,
  SAFE_TORQUE_OFF_ACTIVE = 0x5004,
  PROTECTIVE_STOP = 0x5005,
  COLLISION_DETECTED = 0x5006,

  // Initialization Errors (0x6000 series)
  NOT_INITIALIZED = 0x6001,
  INITIALIZATION_TIMEOUT = 0x6002,
  HOMING_SEQUENCE_FAILED = 0x6003,
  CALIBRATION_INCOMPLETE = 0x6004,
  PARAMETER_VALIDATION_FAILED = 0x6005,
  CONFIGURATION_INVALID = 0x6006,
  HARDWARE_NOT_DETECTED = 0x6007
};

/**
 * @brief Error severity with operational impact
 */
enum class ErrorSeverity : uint8_t
{
  INFO = 0,        // Informational, no action needed
  WARNING = 1,     // Warning condition, monitor closely
  ERROR = 2,       // Error condition, may affect performance
  CRITICAL = 3,    // Critical error, immediate attention required
  FATAL = 4        // Fatal error, system shutdown required
};

/**
 * @brief Error recovery strategies
 */
enum class RecoveryStrategy : uint8_t
{
  NO_RECOVERY = 0,        // No automatic recovery possible
  RETRY_OPERATION = 1,    // Retry the failed operation
  RESET_SUBSYSTEM = 2,    // Reset affected subsystem
  RECALIBRATE = 3,        // Perform recalibration
  GRACEFUL_STOP = 4,      // Stop operation gracefully
  EMERGENCY_STOP = 5,     // Immediate emergency stop
  FALLBACK_MODE = 6,      // Switch to fallback operation
  USER_INTERVENTION = 7   // Requires user intervention
};

/**
 * @brief Comprehensive error information structure
 */
struct MotorError
{
  MotorErrorCode error_code;
  ErrorSeverity severity;
  RecoveryStrategy suggested_recovery;

  std::string description;
  std::string technical_details;
  std::string user_message;
  std::string recovery_instructions;

  std::chrono::steady_clock::time_point occurrence_time;
  std::chrono::steady_clock::time_point last_occurrence;
  uint32_t occurrence_count;

  bool is_recoverable;
  bool requires_user_action;
  bool affects_safety;

  // Context information
  std::unordered_map<std::string, std::string> context_data;
  std::vector<std::string> related_parameters;

  MotorError()
  : error_code(MotorErrorCode::NO_ERROR),
    severity(ErrorSeverity::INFO),
    suggested_recovery(RecoveryStrategy::NO_RECOVERY),
    occurrence_count(0),
    is_recoverable(false),
    requires_user_action(false),
    affects_safety(false)
  {
    occurrence_time = std::chrono::steady_clock::now();
    last_occurrence = occurrence_time;
  }
};

// =============================================================================
// ERROR RECOVERY SYSTEM
// =============================================================================

/**
 * @brief Recovery action result
 */
struct RecoveryResult
{
  bool success;
  RecoveryStrategy strategy_used;
  std::string action_description;
  std::chrono::milliseconds recovery_time;
  uint32_t attempts_made;
  std::string next_suggested_action;

  RecoveryResult()
  : success(false), strategy_used(RecoveryStrategy::NO_RECOVERY),
    recovery_time(0), attempts_made(0) {}
};

/**
 * @brief Motor error handler with comprehensive recovery capabilities
 */
class ComprehensiveErrorHandler
{
public:
  /**
   * @brief Error handler configuration
   */
  struct Config
  {
    uint32_t max_retry_attempts = 3;
    std::chrono::milliseconds retry_delay_ms = std::chrono::milliseconds(100);
    std::chrono::milliseconds critical_error_timeout_ms = std::chrono::milliseconds(5000);
    bool enable_automatic_recovery = true;
    bool enable_predictive_detection = true;
    uint32_t error_history_size = 1000;

    // Recovery timeouts for different strategies
    std::chrono::milliseconds retry_timeout_ms = std::chrono::milliseconds(1000);
    std::chrono::milliseconds reset_timeout_ms = std::chrono::milliseconds(5000);
    std::chrono::milliseconds calibration_timeout_ms = std::chrono::milliseconds(30000);
  };

  /**
   * @brief Error statistics for monitoring
   */
  struct ErrorStatistics
  {
    uint64_t total_errors = 0;
    uint64_t errors_by_severity[5] = {0}; // Index by ErrorSeverity
    uint64_t successful_recoveries = 0;
    uint64_t failed_recoveries = 0;
    uint64_t manual_interventions = 0;

    std::chrono::steady_clock::time_point last_error_time;
    std::chrono::steady_clock::time_point last_recovery_time;
    std::chrono::milliseconds average_recovery_time = std::chrono::milliseconds(0);

    // Most frequent errors
    std::unordered_map<MotorErrorCode, uint32_t> error_frequency;

    void reset()
    {
      total_errors = 0;
      std::fill(std::begin(errors_by_severity), std::end(errors_by_severity), 0);
      successful_recoveries = 0;
      failed_recoveries = 0;
      manual_interventions = 0;
      error_frequency.clear();
    }
  };

public:
  ComprehensiveErrorHandler(const Config & config = {});
  ~ComprehensiveErrorHandler();

  // =============================================================================
  // ERROR DETECTION AND REPORTING
  // =============================================================================

  /**
   * @brief Report a motor error
   */
  bool report_error(
    MotorErrorCode error_code,
    const std::string & context = "",
    const std::unordered_map<std::string, std::string> & additional_data = {});

  /**
   * @brief Check for predictive error conditions
   */
  std::vector<MotorError> detect_potential_errors(const MotorStatus & status);

  /**
   * @brief Get current active errors
   */
  std::vector<MotorError> get_active_errors() const;

  /**
   * @brief Get error history
   */
  std::vector<MotorError> get_error_history(uint32_t max_count = 100) const;

  /**
   * @brief Check if system has any critical errors
   */
  bool has_critical_errors() const;

  /**
   * @brief Check if system is safe to operate
   */
  bool is_safe_to_operate() const;

  // =============================================================================
  // ERROR RECOVERY
  // =============================================================================

  /**
   * @brief Attempt automatic error recovery
   */
  RecoveryResult attempt_recovery(MotorErrorCode error_code);

  /**
   * @brief Attempt recovery for all active errors
   */
  std::vector<RecoveryResult> attempt_recovery_all();

  /**
   * @brief Register custom recovery function
   */
  void register_recovery_handler(
    MotorErrorCode error_code,
    std::function<RecoveryResult()> recovery_func);

  /**
   * @brief Clear specific error if recovery was successful
   */
  bool clear_error(MotorErrorCode error_code);

  /**
   * @brief Clear all non-critical errors
   */
  void clear_all_errors();

  /**
   * @brief Force clear all errors (use with caution)
   */
  void force_clear_all_errors();

  // =============================================================================
  // MONITORING AND DIAGNOSTICS
  // =============================================================================

  /**
   * @brief Get comprehensive error statistics
   */
  ErrorStatistics get_statistics() const;

  /**
   * @brief Reset error statistics
   */
  void reset_statistics();

  /**
   * @brief Generate diagnostic report
   */
  std::string generate_diagnostic_report() const;

  /**
   * @brief Export error log to file
   */
  bool export_error_log(const std::string & filename) const;

  /**
   * @brief Register error callback for external monitoring
   */
  void register_error_callback(std::function<void(const MotorError &)> callback);

  // =============================================================================
  // CONFIGURATION
  // =============================================================================

  /**
   * @brief Update handler configuration
   */
  void update_config(const Config & new_config);

  /**
   * @brief Get current configuration
   */
  Config get_config() const;

private:
  Config config_;
  mutable std::mutex error_mutex_;

  // Error storage
  std::unordered_map<MotorErrorCode, MotorError> active_errors_;
  std::deque<MotorError> error_history_;

  // Recovery handlers
  std::unordered_map<MotorErrorCode, std::function<RecoveryResult()>> recovery_handlers_;

  // Statistics
  ErrorStatistics statistics_;

  // Monitoring
  std::vector<std::function<void(const MotorError &)>> error_callbacks_;

  // Background processing
  std::atomic<bool> running_;
  std::thread monitoring_thread_;
  std::condition_variable monitor_cv_;

  // Helper methods
  MotorError create_error_info(
    MotorErrorCode error_code, const std::string & context,
    const std::unordered_map<std::string, std::string> & data);
  void update_statistics(const MotorError & error);
  void start_monitoring_thread();
  void stop_monitoring_thread();
  void monitoring_loop();

  // Built-in recovery strategies
  RecoveryResult retry_operation_recovery();
  RecoveryResult reset_subsystem_recovery();
  RecoveryResult recalibration_recovery();
  RecoveryResult graceful_stop_recovery();
  RecoveryResult emergency_stop_recovery();
  RecoveryResult fallback_mode_recovery();
};

// =============================================================================
// ERROR INFORMATION DATABASE
// =============================================================================

/**
 * @brief Static database of error information
 */
class MotorErrorDatabase
{
public:
  struct ErrorInfo
  {
    std::string name;
    std::string description;
    std::string technical_details;
    std::string user_message;
    std::string recovery_instructions;
    ErrorSeverity default_severity;
    RecoveryStrategy suggested_recovery;
    bool is_recoverable;
    bool requires_user_action;
    bool affects_safety;
  };

  static const ErrorInfo & get_error_info(MotorErrorCode error_code);
  static std::vector<MotorErrorCode> get_errors_by_category(uint32_t category_mask);
  static bool is_communication_error(MotorErrorCode error_code);
  static bool is_hardware_error(MotorErrorCode error_code);
  static bool is_safety_error(MotorErrorCode error_code);

private:
  static const std::unordered_map<MotorErrorCode, ErrorInfo> error_database_;
  static const ErrorInfo unknown_error_;
};

} // namespace motor_control_ros2
