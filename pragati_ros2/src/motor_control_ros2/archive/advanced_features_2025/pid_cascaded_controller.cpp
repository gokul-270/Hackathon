/*
 * PID Cascaded Controller Module Implementation
 *
 * This module provides cascaded control loops for enhanced performance:
 * - Position-Velocity cascade
 * - Position-Velocity-Current cascade
 * - Velocity-Current cascade
 * - Advanced feedforward compensation
 * - Loop interaction management
 *
 * The cascaded structure improves tracking performance, disturbance rejection,
 * and stability margins compared to single-loop control.
 */

#include "motor_control_ros2/pid_cascaded_controller.hpp"
#include <algorithm>
#include <cmath>

namespace motor_control_ros2
{

// =============================================================================
// PID CASCADED CONTROLLER IMPLEMENTATION
// =============================================================================

PIDCascadedController::PIDCascadedController(
  const CascadedControlConfig & config,
  std::shared_ptr<ComprehensiveErrorHandler> error_handler)
: config_(config)
  , error_handler_(error_handler)
  , is_initialized_(false)
  , cascade_mode_(CascadeMode::POSITION_VELOCITY)
  , is_active_(false)
{
    // Initialize cascade state
  cascade_state_.outer_loop_output = 0.0;
  cascade_state_.middle_loop_output = 0.0;
  cascade_state_.inner_loop_output = 0.0;
  cascade_state_.feedforward_compensation = 0.0;
  cascade_state_.last_update_time = std::chrono::steady_clock::now();
  cascade_state_.is_valid = false;

    // Initialize performance tracking
  performance_data_.outer_loop_error_rms = 0.0;
  performance_data_.middle_loop_error_rms = 0.0;
  performance_data_.inner_loop_error_rms = 0.0;
  performance_data_.settling_time_ms = 0.0;
  performance_data_.bandwidth_hz = 0.0;
  performance_data_.phase_margin_deg = 0.0;
}

PIDCascadedController::~PIDCascadedController()
{
  shutdown();
}

bool PIDCascadedController::initialize()
{
  std::lock_guard<std::mutex> lock(controller_mutex_);

  if (is_initialized_) {
    return true;
  }

    // Validate configuration
  if (!validate_configuration()) {
    report_error("Invalid cascaded controller configuration");
    return false;
  }

    // Initialize individual controllers
  if (!initialize_controllers()) {
    report_error("Failed to initialize cascade controllers");
    return false;
  }

    // Initialize feedforward compensators
  if (!initialize_feedforward()) {
    report_error("Failed to initialize feedforward compensators");
    return false;
  }

    // Initialize performance monitoring
  initialize_performance_monitoring();

  is_initialized_ = true;
  log_cascade_event("Cascaded controller initialized successfully");

  return true;
}

void PIDCascadedController::shutdown()
{
  std::lock_guard<std::mutex> lock(controller_mutex_);

  if (!is_initialized_) {
    return;
  }

    // Reset controllers
  outer_controller_.reset();
  middle_controller_.reset();
  inner_controller_.reset();

  is_initialized_ = false;
  is_active_ = false;

  log_cascade_event("Cascaded controller shutdown");
}

bool PIDCascadedController::configure_for_position_velocity_cascade()
{
  std::lock_guard<std::mutex> lock(controller_mutex_);

  if (!is_initialized_) {
    return false;
  }

  cascade_mode_ = CascadeMode::POSITION_VELOCITY;

    // Configure outer loop (position)
  if (!outer_controller_->set_parameters(config_.position_loop)) {
    return false;
  }

    // Configure inner loop (velocity)
  if (!middle_controller_->set_parameters(config_.velocity_loop)) {
    return false;
  }

    // Reset controllers
  outer_controller_->reset();
  middle_controller_->reset();

  log_cascade_event("Configured for position-velocity cascade");
  return true;
}

bool PIDCascadedController::configure_for_position_velocity_current_cascade()
{
  std::lock_guard<std::mutex> lock(controller_mutex_);

  if (!is_initialized_) {
    return false;
  }

  cascade_mode_ = CascadeMode::POSITION_VELOCITY_CURRENT;

    // Configure all three loops
  outer_controller_->set_parameters(config_.position_loop);
  middle_controller_->set_parameters(config_.velocity_loop);
  inner_controller_->set_parameters(config_.current_loop);

    // Reset all controllers
  outer_controller_->reset();
  middle_controller_->reset();
  inner_controller_->reset();

  log_cascade_event("Configured for position-velocity-current cascade");
  return true;
}

bool PIDCascadedController::set_cascade_targets(const CascadeTargets & targets)
{
  if (!is_initialized_) {
    return false;
  }

  std::lock_guard<std::mutex> lock(targets_mutex_);

  current_targets_ = targets;
  current_targets_.timestamp = std::chrono::steady_clock::now();

  return true;
}

CascadeControlOutput PIDCascadedController::compute_cascade_control(
  const CascadeFeedback & feedback)
{
  std::lock_guard<std::mutex> lock(controller_mutex_);

  CascadeControlOutput output;
  output.timestamp = std::chrono::steady_clock::now();
  output.is_valid = false;

  if (!is_initialized_ || !is_active_) {
    return output;
  }

  auto computation_start = std::chrono::steady_clock::now();

  try {
        // Validate feedback data
    if (!validate_feedback(feedback)) {
      report_error("Invalid cascade feedback data");
      return output;
    }

        // Compute cascade control based on mode
    bool success = false;

    switch (cascade_mode_) {
      case CascadeMode::POSITION_VELOCITY:
        success = compute_position_velocity_cascade(feedback, output);
        break;

      case CascadeMode::POSITION_VELOCITY_CURRENT:
        success = compute_position_velocity_current_cascade(feedback, output);
        break;

      case CascadeMode::VELOCITY_CURRENT:
        success = compute_velocity_current_cascade(feedback, output);
        break;

      default:
        report_error("Unknown cascade mode");
        return output;
    }

    if (success) {
            // Apply feedforward compensation
      apply_feedforward_compensation(output);

            // Apply output limits and saturation handling
      apply_output_limits(output);

            // Update performance metrics
      update_performance_metrics(feedback, output);

      output.is_valid = true;
    }

        // Update computation time metrics
    auto computation_time = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - computation_start);

    update_computation_metrics(computation_time.count());

  } catch (const std::exception & e) {
    report_error(std::string("Exception in cascade computation: ") + e.what());
  }

  return output;
}

bool PIDCascadedController::enable_cascade(bool enable)
{
  std::lock_guard<std::mutex> lock(controller_mutex_);

  if (!is_initialized_) {
    return false;
  }

  if (enable && !is_active_) {
        // Reset all controllers when enabling
    if (outer_controller_) {outer_controller_->reset();}
    if (middle_controller_) {middle_controller_->reset();}
    if (inner_controller_) {inner_controller_->reset();}
  }

  is_active_ = enable;

  log_cascade_event(enable ? "Cascade control enabled" : "Cascade control disabled");
  return true;
}

CascadeStatus PIDCascadedController::get_cascade_status() const
{
  std::lock_guard<std::mutex> lock(controller_mutex_);

  CascadeStatus status;
  status.is_active = is_active_;
  status.cascade_mode = cascade_mode_;
  status.outer_loop_saturated = is_controller_saturated(outer_controller_.get());
  status.middle_loop_saturated = is_controller_saturated(middle_controller_.get());
  status.inner_loop_saturated = is_controller_saturated(inner_controller_.get());
  status.last_update_time = cascade_state_.last_update_time;

  return status;
}

CascadePerformanceData PIDCascadedController::get_performance_data() const
{
  std::lock_guard<std::mutex> lock(performance_mutex_);
  return performance_data_;
}

// =============================================================================
// PRIVATE IMPLEMENTATION METHODS
// =============================================================================

bool PIDCascadedController::validate_configuration()
{
    // Validate loop update rates (inner loop should be fastest)
  if (config_.inner_loop_frequency_hz <= config_.middle_loop_frequency_hz ||
    config_.middle_loop_frequency_hz <= config_.outer_loop_frequency_hz)
  {
    return false;
  }

    // Validate frequency ratios (common rule: inner loop 5-10x faster than outer)
  double inner_to_outer_ratio = config_.inner_loop_frequency_hz / config_.outer_loop_frequency_hz;
  if (inner_to_outer_ratio < 5.0 || inner_to_outer_ratio > 20.0) {
    log_cascade_event("Warning: Inner/outer loop frequency ratio is " +
                         std::to_string(inner_to_outer_ratio) + " (recommended 5-20)");
  }

    // Validate PID parameters
  if (!validate_pid_parameters(config_.position_loop) ||
    !validate_pid_parameters(config_.velocity_loop) ||
    !validate_pid_parameters(config_.current_loop))
  {
    return false;
  }

  return true;
}

bool PIDCascadedController::validate_pid_parameters(const PIDParameters & params)
{
  return  params.kp >= 0.0 && params.ki >= 0.0 && params.kd >= 0.0 &&
         params.output_min < params.output_max &&
         params.integral_windup_limit > 0.0;
}

bool PIDCascadedController::initialize_controllers()
{
  try {
        // Create individual PID controllers
    outer_controller_ = std::make_unique<BasicPIDController>(config_.position_loop);
    middle_controller_ = std::make_unique<BasicPIDController>(config_.velocity_loop);
    inner_controller_ = std::make_unique<BasicPIDController>(config_.current_loop);

    return  outer_controller_ && middle_controller_ && inner_controller_;

  } catch (const std::exception & e) {
    report_error(std::string("Exception creating controllers: ") + e.what());
    return false;
  }
}

bool PIDCascadedController::initialize_feedforward()
{
    // Initialize feedforward compensators
  position_feedforward_ = std::make_unique<FeedforwardCompensator>(config_.position_feedforward);
  velocity_feedforward_ = std::make_unique<FeedforwardCompensator>(config_.velocity_feedforward);

  return  position_feedforward_ && velocity_feedforward_;
}

void PIDCascadedController::initialize_performance_monitoring()
{
    // Initialize error tracking
  position_error_history_.clear();
  velocity_error_history_.clear();
  current_error_history_.clear();

    // Reserve space for efficiency
  position_error_history_.reserve(config_.performance_window_size);
  velocity_error_history_.reserve(config_.performance_window_size);
  current_error_history_.reserve(config_.performance_window_size);

    // Initialize performance data
  performance_data_.outer_loop_error_rms = 0.0;
  performance_data_.middle_loop_error_rms = 0.0;
  performance_data_.inner_loop_error_rms = 0.0;
  performance_data_.settling_time_ms = 0.0;
  performance_data_.bandwidth_hz = 0.0;
  performance_data_.phase_margin_deg = 0.0;
  performance_data_.last_update_time = std::chrono::steady_clock::now();
}

bool PIDCascadedController::validate_feedback(const CascadeFeedback & feedback)
{
    // Check timestamp freshness
  auto now = std::chrono::steady_clock::now();
  auto feedback_age = std::chrono::duration_cast<std::chrono::milliseconds>(now -
      feedback.timestamp);

  if (feedback_age.count() > config_.max_feedback_age_ms) {
    return false;
  }

    // Check for reasonable values
  if (!std::isfinite(feedback.position) || !std::isfinite(feedback.velocity) ||
    !std::isfinite(feedback.current))
  {
    return false;
  }

  return feedback.is_valid;
}

bool PIDCascadedController::compute_position_velocity_cascade(
  const CascadeFeedback & feedback,
  CascadeControlOutput & output)
{
  std::lock_guard<std::mutex> lock(targets_mutex_);

    // Outer loop: Position control
  double position_error = current_targets_.position - feedback.position;
  double velocity_command = outer_controller_->compute(position_error,
      std::chrono::steady_clock::now());

    // Add position feedforward
  velocity_command += current_targets_.velocity_feedforward;

    // Apply velocity limits
  velocity_command = std::max(config_.velocity_limits.min_value,
                               std::min(config_.velocity_limits.max_value, velocity_command));

    // Inner loop: Velocity control
  double velocity_error = velocity_command - feedback.velocity;
  double torque_command = middle_controller_->compute(velocity_error,
      std::chrono::steady_clock::now());

    // Add acceleration feedforward
  torque_command += current_targets_.acceleration_feedforward * config_.motor_inertia_kg_m2;

    // Store intermediate results
  cascade_state_.outer_loop_output = velocity_command;
  cascade_state_.middle_loop_output = torque_command;
  cascade_state_.inner_loop_output = 0.0;   // Not used in 2-loop cascade

    // Set output
  output.position_command = current_targets_.position;
  output.velocity_command = velocity_command;
  output.torque_command = torque_command;
  output.current_command = 0.0;   // Not used

    // Store errors for performance tracking
  store_error_data(position_error, velocity_error, 0.0);

  return true;
}

bool PIDCascadedController::compute_position_velocity_current_cascade(
  const CascadeFeedback & feedback,
  CascadeControlOutput & output)
{
  std::lock_guard<std::mutex> lock(targets_mutex_);

    // Outer loop: Position control
  double position_error = current_targets_.position - feedback.position;
  double velocity_command = outer_controller_->compute(position_error,
      std::chrono::steady_clock::now());

    // Add position feedforward
  velocity_command += current_targets_.velocity_feedforward;

    // Apply velocity limits
  velocity_command = std::max(config_.velocity_limits.min_value,
                               std::min(config_.velocity_limits.max_value, velocity_command));

    // Middle loop: Velocity control
  double velocity_error = velocity_command - feedback.velocity;
  double current_command = middle_controller_->compute(velocity_error,
      std::chrono::steady_clock::now());

    // Add acceleration feedforward (converted to current)
  double accel_feedforward_current = current_targets_.acceleration_feedforward *
    config_.motor_inertia_kg_m2 / config_.motor_torque_constant_nm_per_a;
  current_command += accel_feedforward_current;

    // Apply current limits
  current_command = std::max(config_.current_limits.min_value,
                              std::min(config_.current_limits.max_value, current_command));

    // Inner loop: Current control (if current feedback available)
  double torque_command = current_command * config_.motor_torque_constant_nm_per_a;

  if (feedback.has_current_feedback) {
    double current_error = current_command - feedback.current;
    double current_correction = inner_controller_->compute(current_error,
        std::chrono::steady_clock::now());
    torque_command += current_correction;
  }

    // Store intermediate results
  cascade_state_.outer_loop_output = velocity_command;
  cascade_state_.middle_loop_output = current_command;
  cascade_state_.inner_loop_output = torque_command;

    // Set output
  output.position_command = current_targets_.position;
  output.velocity_command = velocity_command;
  output.current_command = current_command;
  output.torque_command = torque_command;

    // Store errors for performance tracking
  double current_error = feedback.has_current_feedback ? (current_command - feedback.current) : 0.0;
  store_error_data(position_error, velocity_error, current_error);

  return true;
}

bool PIDCascadedController::compute_velocity_current_cascade(
  const CascadeFeedback & feedback,
  CascadeControlOutput & output)
{
  std::lock_guard<std::mutex> lock(targets_mutex_);

    // Outer loop: Velocity control
  double velocity_error = current_targets_.velocity - feedback.velocity;
  double current_command = outer_controller_->compute(velocity_error,
      std::chrono::steady_clock::now());

    // Add acceleration feedforward
  double accel_feedforward_current = current_targets_.acceleration_feedforward *
    config_.motor_inertia_kg_m2 / config_.motor_torque_constant_nm_per_a;
  current_command += accel_feedforward_current;

    // Apply current limits
  current_command = std::max(config_.current_limits.min_value,
                              std::min(config_.current_limits.max_value, current_command));

    // Inner loop: Current control
  double torque_command = current_command * config_.motor_torque_constant_nm_per_a;

  if (feedback.has_current_feedback) {
    double current_error = current_command - feedback.current;
    double current_correction = middle_controller_->compute(current_error,
        std::chrono::steady_clock::now());
    torque_command += current_correction;
  }

    // Store intermediate results
  cascade_state_.outer_loop_output = current_command;
  cascade_state_.middle_loop_output = torque_command;
  cascade_state_.inner_loop_output = 0.0;

    // Set output
  output.position_command = 0.0;   // Not controlled
  output.velocity_command = current_targets_.velocity;
  output.current_command = current_command;
  output.torque_command = torque_command;

    // Store errors for performance tracking
  double current_error = feedback.has_current_feedback ? (current_command - feedback.current) : 0.0;
  store_error_data(0.0, velocity_error, current_error);

  return true;
}

void PIDCascadedController::apply_feedforward_compensation(CascadeControlOutput & output)
{
    // Apply position feedforward compensation
  if (position_feedforward_) {
    FeedforwardInput ff_input;
    ff_input.reference_position = current_targets_.position;
    ff_input.reference_velocity = current_targets_.velocity_feedforward;
    ff_input.reference_acceleration = current_targets_.acceleration_feedforward;

    double position_ff = position_feedforward_->compute_compensation(ff_input);
    output.velocity_command += position_ff;
  }

    // Apply velocity feedforward compensation
  if (velocity_feedforward_) {
    FeedforwardInput ff_input;
    ff_input.reference_position = 0.0;     // Not used for velocity FF
    ff_input.reference_velocity = output.velocity_command;
    ff_input.reference_acceleration = current_targets_.acceleration_feedforward;

    double velocity_ff = velocity_feedforward_->compute_compensation(ff_input);
    output.torque_command += velocity_ff;
  }

    // Update feedforward compensation tracking
  cascade_state_.feedforward_compensation =
    (position_feedforward_ ? position_feedforward_->get_last_compensation() : 0.0) +
    (velocity_feedforward_ ? velocity_feedforward_->get_last_compensation() : 0.0);
}

void PIDCascadedController::apply_output_limits(CascadeControlOutput & output)
{
    // Apply velocity limits
  output.velocity_command = std::max(config_.velocity_limits.min_value,
                                      std::min(config_.velocity_limits.max_value,
      output.velocity_command));

    // Apply current limits
  output.current_command = std::max(config_.current_limits.min_value,
                                     std::min(config_.current_limits.max_value,
      output.current_command));

    // Apply torque limits
  output.torque_command = std::max(config_.torque_limits.min_value,
                                    std::min(config_.torque_limits.max_value,
      output.torque_command));
}

void PIDCascadedController::store_error_data(
  double position_error, double velocity_error,
  double current_error)
{
    // Store errors in circular buffers for performance analysis
  position_error_history_.push_back(position_error);
  velocity_error_history_.push_back(velocity_error);
  current_error_history_.push_back(current_error);

    // Maintain buffer size
  if (position_error_history_.size() > config_.performance_window_size) {
    position_error_history_.erase(position_error_history_.begin());
  }
  if (velocity_error_history_.size() > config_.performance_window_size) {
    velocity_error_history_.erase(velocity_error_history_.begin());
  }
  if (current_error_history_.size() > config_.performance_window_size) {
    current_error_history_.erase(current_error_history_.begin());
  }
}

void PIDCascadedController::update_performance_metrics(
  const CascadeFeedback & feedback,
  const CascadeControlOutput & output)
{
  std::lock_guard<std::mutex> lock(performance_mutex_);

    // Calculate RMS errors
  if (!position_error_history_.empty()) {
    double sum_sq = 0.0;
    for (double error : position_error_history_) {
      sum_sq += error * error;
    }
    performance_data_.outer_loop_error_rms = std::sqrt(sum_sq / position_error_history_.size());
  }

  if (!velocity_error_history_.empty()) {
    double sum_sq = 0.0;
    for (double error : velocity_error_history_) {
      sum_sq += error * error;
    }
    performance_data_.middle_loop_error_rms = std::sqrt(sum_sq / velocity_error_history_.size());
  }

  if (!current_error_history_.empty()) {
    double sum_sq = 0.0;
    for (double error : current_error_history_) {
      sum_sq += error * error;
    }
    performance_data_.inner_loop_error_rms = std::sqrt(sum_sq / current_error_history_.size());
  }

  performance_data_.last_update_time = std::chrono::steady_clock::now();
}

void PIDCascadedController::update_computation_metrics(double computation_time_us)
{
  std::lock_guard<std::mutex> lock(performance_mutex_);

    // Update average computation time (simple moving average)
  static double average_computation_time = 0.0;
  static int sample_count = 0;

  sample_count++;
  average_computation_time = (average_computation_time * (sample_count - 1) + computation_time_us) /
    sample_count;

    // Reset periodically to prevent overflow
  if (sample_count > 1000) {
    sample_count = 100;
  }
}

bool PIDCascadedController::is_controller_saturated(const BasicPIDController * controller) const
{
  if (!controller) {
    return false;
  }

    // Check if controller output is at limits (simplified check)
  double output = controller->get_last_output();
  double output_min = controller->get_output_min();
  double output_max = controller->get_output_max();

  const double saturation_threshold = 0.95;   // 95% of limit

  return (output >= saturation_threshold * output_max) ||
         (output <= saturation_threshold * output_min);
}

void PIDCascadedController::report_error(const std::string & message)
{
  if (error_handler_) {
    error_handler_->report_error(
            ErrorLevel::ERROR,
            "PID_CASCADE_ERROR",
            message,
            ErrorType::SYSTEM_ERROR,
            "pid_cascaded_controller"
    );
  }

  log_cascade_event("ERROR: " + message);
}

void PIDCascadedController::log_cascade_event(const std::string & message)
{
    // Simple event logging
  auto now = std::chrono::system_clock::now();
  auto time_t = std::chrono::system_clock::to_time_t(now);

    // In real implementation, this would use proper logging
}

} // namespace motor_control_ros2
