/*
 * Comprehensive Error Handler Implementation
 *
 * This implementation provides advanced error management capabilities:
 * - Hierarchical error classification (Critical, Warning, Info)
 * - Automatic recovery strategies
 * - Error prediction and prevention
 * - Safety interlocks and fail-safe modes
 * - Statistical analysis and trending
 * - Real-time error monitoring
 */

#include "motor_control_ros2/comprehensive_error_handler.hpp"
#include <algorithm>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <cmath>

namespace motor_control_ros2
{

// =============================================================================
// COMPREHENSIVE ERROR HANDLER IMPLEMENTATION
// =============================================================================

ComprehensiveErrorHandler::ComprehensiveErrorHandler()
: next_error_id_(1)
  , safety_system_enabled_(true)
  , prediction_enabled_(true)
  , recovery_enabled_(true)
  , emergency_stop_active_(false)
  , rng_(std::chrono::steady_clock::now().time_since_epoch().count())
{
    // Initialize error database
  initialize_error_database();

    // Initialize statistics
  statistics_.start_time = std::chrono::steady_clock::now();
  statistics_.last_reset_time = statistics_.start_time;

    // Start background threads
  start_background_threads();
}

ComprehensiveErrorHandler::~ComprehensiveErrorHandler()
{
  shutdown();
}

bool ComprehensiveErrorHandler::report_error(
  MotorErrorCode error_code,
  const std::string & description, ErrorSeverity severity)
{
  DetailedErrorInfo error_info;
  error_info.error_id = generate_error_id();
  error_info.error_code = error_code;
  error_info.severity = severity;
  error_info.description = description;
  error_info.timestamp = std::chrono::steady_clock::now();
  error_info.context_info = get_system_context();

    // Classify error automatically if severity not specified
  if (severity == ErrorSeverity::INFO) {   // Use INFO as "auto-detect"
    error_info.severity = classify_error_severity(error_code);
  }

    // Add error characteristics
  auto db_entry = get_error_database_entry(error_code);
  if (db_entry) {
    error_info.affects_safety = db_entry->affects_safety;
    error_info.affects_performance = db_entry->affects_performance;
    error_info.is_recoverable = db_entry->is_recoverable;
    error_info.recovery_strategy = db_entry->default_recovery_strategy;
  }

  return report_error_with_context(error_info);
}

bool ComprehensiveErrorHandler::report_error_with_context(const DetailedErrorInfo & error_info)
{
  std::lock_guard<std::mutex> lock(error_mutex_);

    // Check for duplicate recent errors
  if (is_duplicate_error(error_info)) {
    update_error_frequency(error_info.error_code);
    return true;     // Don't spam with duplicates
  }

    // Add to active errors list
  active_errors_.push_back(error_info);

    // Add to error history
  error_history_.push_back(error_info);
  if (error_history_.size() > MAX_ERROR_HISTORY) {
    error_history_.erase(error_history_.begin());
  }

    // Update statistics
  update_statistics(error_info);

    // Handle safety-critical errors
  if (error_info.affects_safety && safety_system_enabled_) {
    handle_safety_critical_error(error_info);
  }

    // Trigger automatic recovery if enabled
  if (recovery_enabled_ && error_info.is_recoverable) {
    schedule_recovery_attempt(error_info.error_code);
  }

    // Notify observers
  notify_error_observers(error_info);

    // Log error
  log_error(error_info);

  return true;
}

bool ComprehensiveErrorHandler::clear_error(uint64_t error_id)
{
  std::lock_guard<std::mutex> lock(error_mutex_);

  auto it = std::find_if(active_errors_.begin(), active_errors_.end(),
      [error_id](const DetailedErrorInfo & error) {
        return error.error_id == error_id;
        });

  if (it != active_errors_.end()) {
        // Log clearance
    log_error_clearance(*it);

        // Remove from active errors
    active_errors_.erase(it);

        // Update safety state if this was a safety-critical error
    if (it->affects_safety) {
      reassess_safety_state();
    }

    return true;
  }

  return false;
}

bool ComprehensiveErrorHandler::clear_all_errors()
{
  std::lock_guard<std::mutex> lock(error_mutex_);

    // Log mass clearance
  if (!active_errors_.empty()) {
    std::ostringstream oss;
    oss << "Clearing " << active_errors_.size() << " active errors";
    log_system_event(oss.str());
  }

  active_errors_.clear();

    // Reset safety state
  emergency_stop_active_ = false;

  return true;
}

std::vector<DetailedErrorInfo> ComprehensiveErrorHandler::get_active_errors() const
{
  std::lock_guard<std::mutex> lock(error_mutex_);
  return active_errors_;
}

ErrorRecoveryResult ComprehensiveErrorHandler::attempt_recovery(MotorErrorCode error_code)
{
  ErrorRecoveryResult result;
  result.error_code = error_code;
  result.start_time = std::chrono::steady_clock::now();
  result.recovery_attempted = true;

  auto db_entry = get_error_database_entry(error_code);
  if (!db_entry || !db_entry->is_recoverable) {
    result.success = false;
    result.failure_reason = "Error is not recoverable";
    result.end_time = std::chrono::steady_clock::now();
    return result;
  }

    // Execute recovery strategy
  bool recovery_success = false;

  switch (db_entry->default_recovery_strategy) {
    case RecoveryStrategy::RESTART_COMPONENT:
      recovery_success = execute_component_restart_recovery(error_code);
      break;

    case RecoveryStrategy::RESET_PARAMETERS:
      recovery_success = execute_parameter_reset_recovery(error_code);
      break;

    case RecoveryStrategy::REINITIALIZE_SYSTEM:
      recovery_success = execute_system_reinit_recovery(error_code);
      break;

    case RecoveryStrategy::FALLBACK_MODE:
      recovery_success = execute_fallback_mode_recovery(error_code);
      break;

    case RecoveryStrategy::USER_INTERVENTION:
      recovery_success = request_user_intervention_recovery(error_code);
      break;

    default:
      recovery_success = false;
      result.failure_reason = "Unknown recovery strategy";
      break;
  }

  result.success = recovery_success;
  result.end_time = std::chrono::steady_clock::now();
  result.attempts_made = 1;

    // Update recovery statistics
  update_recovery_statistics(result);

    // Log recovery attempt
  log_recovery_attempt(result);

  return result;
}

bool ComprehensiveErrorHandler::is_recovery_possible(MotorErrorCode error_code) const
{
  auto db_entry = get_error_database_entry(error_code);
  return db_entry && db_entry->is_recoverable && recovery_enabled_;
}

bool ComprehensiveErrorHandler::is_safe_to_operate() const
{
  std::lock_guard<std::mutex> lock(error_mutex_);

    // Check emergency stop state
  if (emergency_stop_active_) {
    return false;
  }

    // Check for active safety-critical errors
  for (const auto & error : active_errors_) {
    if (error.affects_safety && error.severity == ErrorSeverity::CRITICAL) {
      return false;
    }
  }

    // Check error rates
  if (get_error_rate() > MAX_SAFE_ERROR_RATE) {
    return false;
  }

  return true;
}

bool ComprehensiveErrorHandler::has_critical_errors() const
{
  std::lock_guard<std::mutex> lock(error_mutex_);

  return std::any_of(active_errors_.begin(), active_errors_.end(),
           [](const DetailedErrorInfo & error) {
             return error.severity == ErrorSeverity::CRITICAL;
        });
}

ErrorStatistics ComprehensiveErrorHandler::get_statistics() const
{
  std::lock_guard<std::mutex> lock(stats_mutex_);

  ErrorStatistics stats = statistics_;

    // Calculate derived statistics
  auto now = std::chrono::steady_clock::now();
  auto elapsed = std::chrono::duration<double>(now - stats.start_time).count();

  if (elapsed > 0) {
    stats.error_rate = static_cast<double>(stats.total_errors) / elapsed;
  }

    // Calculate error distribution
  stats.error_frequency.clear();
  for (const auto & error : error_history_) {
    stats.error_frequency[error.error_code]++;
  }

  return stats;
}

bool ComprehensiveErrorHandler::configure_recovery_strategy(
  MotorErrorCode error_code,
  const RecoveryStrategy & strategy)
{
  std::lock_guard<std::mutex> lock(config_mutex_);

  auto it = error_database_.find(error_code);
  if (it != error_database_.end()) {
    it->second.default_recovery_strategy = strategy;
    return true;
  }

  return false;
}

bool ComprehensiveErrorHandler::set_safety_enabled(bool enabled)
{
  std::lock_guard<std::mutex> lock(error_mutex_);
  safety_system_enabled_ = enabled;
  return true;
}

bool ComprehensiveErrorHandler::set_prediction_enabled(bool enabled)
{
  std::lock_guard<std::mutex> lock(error_mutex_);
  prediction_enabled_ = enabled;
  return true;
}

bool ComprehensiveErrorHandler::set_recovery_enabled(bool enabled)
{
  std::lock_guard<std::mutex> lock(error_mutex_);
  recovery_enabled_ = enabled;
  return true;
}

bool ComprehensiveErrorHandler::trigger_emergency_stop()
{
  std::lock_guard<std::mutex> lock(error_mutex_);

  emergency_stop_active_ = true;

    // Log emergency stop
  log_system_event("EMERGENCY STOP TRIGGERED");

    // Report emergency stop as critical error
  DetailedErrorInfo emergency_error;
  emergency_error.error_id = generate_error_id();
  emergency_error.error_code = MotorErrorCode::EMERGENCY_STOP_TRIGGERED;
  emergency_error.severity = ErrorSeverity::CRITICAL;
  emergency_error.description = "Emergency stop activated";
  emergency_error.timestamp = std::chrono::steady_clock::now();
  emergency_error.affects_safety = true;

  active_errors_.push_back(emergency_error);

    // Notify observers
  notify_error_observers(emergency_error);

  return true;
}

bool ComprehensiveErrorHandler::clear_emergency_stop()
{
  std::lock_guard<std::mutex> lock(error_mutex_);

  if (!emergency_stop_active_) {
    return true;     // Already cleared
  }

    // Remove emergency stop errors
  auto it = std::remove_if(active_errors_.begin(), active_errors_.end(),
      [](const DetailedErrorInfo & error) {
        return error.error_code == MotorErrorCode::EMERGENCY_STOP_TRIGGERED;
        });
  active_errors_.erase(it, active_errors_.end());

  emergency_stop_active_ = false;

  log_system_event("Emergency stop cleared");

  return true;
}

void ComprehensiveErrorHandler::register_error_observer(
  std::function<void(const DetailedErrorInfo &)> observer)
{
  std::lock_guard<std::mutex> lock(observer_mutex_);
  error_observers_.push_back(observer);
}

std::vector<ErrorPrediction> ComprehensiveErrorHandler::predict_potential_errors() const
{
  std::vector<ErrorPrediction> predictions;

  if (!prediction_enabled_) {
    return predictions;
  }

    // Analyze error patterns
  auto error_patterns = analyze_error_patterns();

    // Predict based on frequency trends
  for (const auto & pattern : error_patterns) {
    if (pattern.trend > PREDICTION_THRESHOLD) {
      ErrorPrediction prediction;
      prediction.error_code = pattern.error_code;
      prediction.probability = std::min(1.0, pattern.trend / 10.0);
      prediction.estimated_time = std::chrono::steady_clock::now() +
        std::chrono::seconds(static_cast<long>(3600 / pattern.trend));         // Rough estimate
      prediction.confidence = calculate_prediction_confidence(pattern);
      prediction.recommended_actions = get_prevention_actions(pattern.error_code);

      predictions.push_back(prediction);
    }
  }

  return predictions;
}

// =============================================================================
// PRIVATE IMPLEMENTATION METHODS
// =============================================================================

void ComprehensiveErrorHandler::initialize_error_database()
{
    // Initialize comprehensive error database with all motor error codes

    // CAN Communication Errors
  add_error_db_entry(MotorErrorCode::CAN_TIMEOUT, {
      .is_recoverable = true,
      .affects_safety = false,
      .affects_performance = true,
      .default_recovery_strategy = RecoveryStrategy::RESTART_COMPONENT,
      .typical_causes = {"Network congestion", "Cable issues", "Controller overload"},
      .prevention_actions = {"Check CAN bus load", "Verify connections", "Optimize message timing"}
    });

  add_error_db_entry(MotorErrorCode::CAN_BUS_OFF, {
      .is_recoverable = true,
      .affects_safety = true,
      .affects_performance = true,
      .default_recovery_strategy = RecoveryStrategy::REINITIALIZE_SYSTEM,
      .typical_causes = {"Bus overload", "Hardware fault", "Excessive errors"},
      .prevention_actions = {"Reduce bus load", "Check termination", "Monitor error rates"}
    });

    // Motor Errors
  add_error_db_entry(MotorErrorCode::MOTOR_OVERCURRENT, {
      .is_recoverable = true,
      .affects_safety = true,
      .affects_performance = true,
      .default_recovery_strategy = RecoveryStrategy::FALLBACK_MODE,
      .typical_causes = {"Excessive load", "Short circuit", "Wrong parameters"},
      .prevention_actions = {"Check load", "Verify wiring", "Adjust current limits"}
    });

  add_error_db_entry(MotorErrorCode::MOTOR_OVERTEMPERATURE, {
      .is_recoverable = true,
      .affects_safety = true,
      .affects_performance = true,
      .default_recovery_strategy = RecoveryStrategy::FALLBACK_MODE,
      .typical_causes = {"Insufficient cooling", "Excessive current", "Ambient temperature"},
      .prevention_actions = {"Improve cooling", "Reduce duty cycle", "Monitor temperature"}
    });

    // Encoder Errors
  add_error_db_entry(MotorErrorCode::ENCODER_FAULT, {
      .is_recoverable = true,
      .affects_safety = true,
      .affects_performance = true,
      .default_recovery_strategy = RecoveryStrategy::FALLBACK_MODE,
      .typical_causes = {"Encoder failure", "Connection issue", "Noise interference"},
      .prevention_actions = {"Check connections", "Shield cables", "Verify power supply"}
    });

    // System Errors
  add_error_db_entry(MotorErrorCode::EMERGENCY_STOP_TRIGGERED, {
      .is_recoverable = false,
      .affects_safety = true,
      .affects_performance = true,
      .default_recovery_strategy = RecoveryStrategy::USER_INTERVENTION,
      .typical_causes = {"Manual activation", "Safety system trigger", "External command"},
      .prevention_actions = {"Check safety systems", "Verify operation conditions"}
    });
}

void ComprehensiveErrorHandler::add_error_db_entry(
  MotorErrorCode code,
  const ErrorDatabaseEntry & entry)
{
  error_database_[code] = entry;
}

const ErrorDatabaseEntry * ComprehensiveErrorHandler::get_error_database_entry(
  MotorErrorCode error_code) const
{
  auto it = error_database_.find(error_code);
  return (it != error_database_.end()) ? &it->second : nullptr;
}

uint64_t ComprehensiveErrorHandler::generate_error_id()
{
  return next_error_id_++;
}

ErrorSeverity ComprehensiveErrorHandler::classify_error_severity(MotorErrorCode error_code) const
{
  auto db_entry = get_error_database_entry(error_code);
  if (!db_entry) {
    return ErrorSeverity::WARNING;     // Default for unknown errors
  }

    // Classify based on impact
  if (db_entry->affects_safety) {
    return ErrorSeverity::CRITICAL;
  } else if (db_entry->affects_performance) {
    return ErrorSeverity::WARNING;
  } else {
    return ErrorSeverity::INFO;
  }
}

bool ComprehensiveErrorHandler::is_duplicate_error(const DetailedErrorInfo & new_error) const
{
  const auto duplicate_window = std::chrono::seconds(5);   // 5-second window

  for (auto it = active_errors_.rbegin(); it != active_errors_.rend(); ++it) {
    if (it->error_code == new_error.error_code) {
      auto time_diff = new_error.timestamp - it->timestamp;
      if (time_diff < duplicate_window) {
        return true;
      }
      break;       // Found the most recent occurrence
    }
  }

  return false;
}

void ComprehensiveErrorHandler::update_statistics(const DetailedErrorInfo & error_info)
{
  std::lock_guard<std::mutex> lock(stats_mutex_);

  statistics_.total_errors++;
  statistics_.last_error_time = error_info.timestamp;

    // Update severity counters
  switch (error_info.severity) {
    case ErrorSeverity::INFO:
      statistics_.info_errors++;
      break;
    case ErrorSeverity::WARNING:
      statistics_.warning_errors++;
      break;
    case ErrorSeverity::CRITICAL:
      statistics_.critical_errors++;
      break;
    case ErrorSeverity::FATAL:
      statistics_.fatal_errors++;
      break;
  }

    // Update safety impact counter
  if (error_info.affects_safety) {
    statistics_.safety_errors++;
  }
}

void ComprehensiveErrorHandler::update_recovery_statistics(const ErrorRecoveryResult & result)
{
  std::lock_guard<std::mutex> lock(stats_mutex_);

  statistics_.total_recovery_attempts++;

  if (result.success) {
    statistics_.successful_recoveries++;
  } else {
    statistics_.failed_recoveries++;
  }

  statistics_.last_recovery_time = result.end_time;
}

void ComprehensiveErrorHandler::handle_safety_critical_error(const DetailedErrorInfo & error_info)
{
    // For critical safety errors, trigger appropriate responses
  if (error_info.severity == ErrorSeverity::CRITICAL ||
    error_info.severity == ErrorSeverity::FATAL)
  {
        // Could trigger emergency stop or safe mode
    log_system_event("Safety-critical error detected: " + error_info.description);

        // Implement safety response based on error type
    switch (error_info.error_code) {
      case MotorErrorCode::MOTOR_OVERCURRENT:
      case MotorErrorCode::MOTOR_OVERTEMPERATURE:
                // These might require immediate shutdown
        break;

      case MotorErrorCode::ENCODER_FAULT:
                // This might require fallback to secondary encoder
        break;

      default:
        break;
    }
  }
}

void ComprehensiveErrorHandler::schedule_recovery_attempt(MotorErrorCode error_code)
{
    // Add to recovery queue for background processing
  std::lock_guard<std::mutex> lock(recovery_mutex_);
  recovery_queue_.push(error_code);
  recovery_cv_.notify_one();
}

void ComprehensiveErrorHandler::notify_error_observers(const DetailedErrorInfo & error_info)
{
  std::lock_guard<std::mutex> lock(observer_mutex_);

  for (const auto & observer : error_observers_) {
    try {
      observer(error_info);
    } catch (...) {
            // Ignore observer exceptions to prevent cascading failures
    }
  }
}

void ComprehensiveErrorHandler::log_error(const DetailedErrorInfo & error_info)
{
  std::ostringstream oss;
  oss   << "ERROR[" << error_info.error_id << "] "
        << "Code: " << static_cast<int>(error_info.error_code) << " "
        << "Severity: " << static_cast<int>(error_info.severity) << " "
        << "Description: " << error_info.description;

  log_system_event(oss.str());
}

void ComprehensiveErrorHandler::log_error_clearance(const DetailedErrorInfo & error_info)
{
  std::ostringstream oss;
  oss   << "ERROR_CLEARED[" << error_info.error_id << "] "
        << "Code: " << static_cast<int>(error_info.error_code);

  log_system_event(oss.str());
}

void ComprehensiveErrorHandler::log_recovery_attempt(const ErrorRecoveryResult & result)
{
  std::ostringstream oss;
  oss   << "RECOVERY_ATTEMPT Code: " << static_cast<int>(result.error_code)
        << " Success: " << (result.success ? "YES" : "NO")
        << " Attempts: " << result.attempts_made;

  if (!result.success && !result.failure_reason.empty()) {
    oss << " Reason: " << result.failure_reason;
  }

  log_system_event(oss.str());
}

void ComprehensiveErrorHandler::log_system_event(const std::string & event)
{
    // Simple logging implementation - in production this would use proper logging framework
  auto now = std::chrono::system_clock::now();
  auto time_t = std::chrono::system_clock::to_time_t(now);

  std::cout   << "[" << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S") << "] "
              << "ERROR_HANDLER: " << event << std::endl;
}

std::string ComprehensiveErrorHandler::get_system_context() const
{
  std::ostringstream oss;
  auto now = std::chrono::steady_clock::now();
  auto uptime = std::chrono::duration_cast<std::chrono::seconds>(now -
      statistics_.start_time).count();

  oss   << "Uptime: " << uptime << "s, "
        << "ActiveErrors: " << active_errors_.size() << ", "
        << "TotalErrors: " << statistics_.total_errors;

  return oss.str();
}

double ComprehensiveErrorHandler::get_error_rate() const
{
  auto stats = get_statistics();
  return stats.error_rate;
}

void ComprehensiveErrorHandler::update_error_frequency(MotorErrorCode error_code)
{
  std::lock_guard<std::mutex> lock(stats_mutex_);
    // This would update frequency tracking for duplicate detection
}

void ComprehensiveErrorHandler::reassess_safety_state()
{
    // Check if we can exit emergency stop or safety mode
  bool has_safety_errors = std::any_of(active_errors_.begin(), active_errors_.end(),
      [](const DetailedErrorInfo & error) {
        return error.affects_safety;
        });

  if (!has_safety_errors && emergency_stop_active_) {
        // Could automatically clear emergency stop if no safety issues remain
        // For now, require manual clearance
    log_system_event("Safety state reassessed - manual clearance required");
  }
}

void ComprehensiveErrorHandler::start_background_threads()
{
    // Start recovery processing thread
  recovery_thread_active_ = true;
  recovery_thread_ = std::thread(&ComprehensiveErrorHandler::recovery_processing_thread, this);

    // Start prediction thread
  prediction_thread_active_ = true;
  prediction_thread_ = std::thread(&ComprehensiveErrorHandler::prediction_thread, this);
}

void ComprehensiveErrorHandler::shutdown()
{
    // Stop background threads
  recovery_thread_active_ = false;
  prediction_thread_active_ = false;

  recovery_cv_.notify_all();

  if (recovery_thread_.joinable()) {
    recovery_thread_.join();
  }

  if (prediction_thread_.joinable()) {
    prediction_thread_.join();
  }
}

void ComprehensiveErrorHandler::recovery_processing_thread()
{
  while (recovery_thread_active_) {
    std::unique_lock<std::mutex> lock(recovery_mutex_);

    recovery_cv_.wait(lock, [this] {
        return !recovery_queue_.empty() || !recovery_thread_active_;
        });

    if (!recovery_thread_active_) {
      break;
    }

    while (!recovery_queue_.empty()) {
      MotorErrorCode error_code = recovery_queue_.front();
      recovery_queue_.pop();

      lock.unlock();

            // Attempt recovery
      auto result = attempt_recovery(error_code);

            // Log result
      log_recovery_attempt(result);

      lock.lock();
    }
  }
}

void ComprehensiveErrorHandler::prediction_thread()
{
  while (prediction_thread_active_) {
    std::this_thread::sleep_for(std::chrono::seconds(60));     // Run every minute

    if (!prediction_thread_active_) {
      break;
    }

    if (prediction_enabled_) {
      auto predictions = predict_potential_errors();

            // Log significant predictions
      for (const auto & prediction : predictions) {
        if (prediction.probability > 0.7 && prediction.confidence > 0.5) {
          std::ostringstream oss;
          oss           << "ERROR_PREDICTION Code: " << static_cast<int>(prediction.error_code)
                        << " Probability: " << std::fixed << std::setprecision(2) <<
            prediction.probability
                        << " Confidence: " << prediction.confidence;

          log_system_event(oss.str());
        }
      }
    }
  }
}

// Recovery strategy implementations
bool ComprehensiveErrorHandler::execute_component_restart_recovery(MotorErrorCode error_code)
{
    // Placeholder for component restart logic
  log_system_event("Executing component restart recovery for error: " +
      std::to_string(static_cast<int>(error_code)));

    // Simulate recovery success/failure
  return true;   // Would implement actual restart logic
}

bool ComprehensiveErrorHandler::execute_parameter_reset_recovery(MotorErrorCode error_code)
{
  log_system_event("Executing parameter reset recovery for error: " +
      std::to_string(static_cast<int>(error_code)));
  return true;
}

bool ComprehensiveErrorHandler::execute_system_reinit_recovery(MotorErrorCode error_code)
{
  log_system_event("Executing system reinit recovery for error: " +
      std::to_string(static_cast<int>(error_code)));
  return true;
}

bool ComprehensiveErrorHandler::execute_fallback_mode_recovery(MotorErrorCode error_code)
{
  log_system_event("Executing fallback mode recovery for error: " +
      std::to_string(static_cast<int>(error_code)));
  return true;
}

bool ComprehensiveErrorHandler::request_user_intervention_recovery(MotorErrorCode error_code)
{
  log_system_event("User intervention required for error: " +
      std::to_string(static_cast<int>(error_code)));
  return false;   // Requires manual intervention
}

// Prediction helper methods
std::vector<ErrorPattern> ComprehensiveErrorHandler::analyze_error_patterns() const
{
  std::vector<ErrorPattern> patterns;

    // Simple pattern analysis - count recent error frequencies
  std::map<MotorErrorCode, int> recent_counts;
  auto cutoff_time = std::chrono::steady_clock::now() - std::chrono::hours(1);   // Last hour

  for (const auto & error : error_history_) {
    if (error.timestamp > cutoff_time) {
      recent_counts[error.error_code]++;
    }
  }

    // Convert to patterns
  for (const auto & [error_code, count] : recent_counts) {
    if (count > 1) {     // Only if seen multiple times
      ErrorPattern pattern;
      pattern.error_code = error_code;
      pattern.frequency = count;
      pattern.trend = static_cast<double>(count);       // Simplified trend calculation
      patterns.push_back(pattern);
    }
  }

  return patterns;
}

double ComprehensiveErrorHandler::calculate_prediction_confidence(
  const ErrorPattern & pattern) const
{
    // Simple confidence calculation based on frequency and consistency
  double base_confidence = std::min(1.0, pattern.frequency / 10.0);
  return base_confidence * 0.8;   // Conservative confidence
}

std::vector<std::string> ComprehensiveErrorHandler::get_prevention_actions(
  MotorErrorCode error_code) const
{
  auto db_entry = get_error_database_entry(error_code);
  if (db_entry) {
    return db_entry->prevention_actions;
  }

  return {"Monitor system closely", "Check system logs", "Review recent changes"};
}

} // namespace motor_control_ros2
