/*
 * Advanced PID System Implementation - Main Controller
 *
 * This file contains the main PID system controller with a modular architecture:
 * - Main PID controller coordination
 * - Configuration management
 * - System initialization and lifecycle
 * - Integration with other subsystems
 *
 * The implementation is split into focused modules:
 * - pid_auto_tuner.cpp: Auto-tuning algorithms
 * - pid_cascaded_controller.cpp: Cascaded control loops
 * - pid_motor_optimizer.cpp: Motor-specific optimizations
 * - pid_adaptive_controller.cpp: Adaptive control features
 */

#include "motor_control_ros2/advanced_pid_system.hpp"
#include "motor_control_ros2/pid_auto_tuner.hpp"
#include "motor_control_ros2/pid_cascaded_controller.hpp"
// Note: pid_motor_optimizer and pid_adaptive_controller headers to be created
// #include "motor_control_ros2/pid_motor_optimizer.hpp"
// #include "motor_control_ros2/pid_adaptive_controller.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>

namespace motor_control_ros2
{

// =============================================================================
// ADVANCED PID SYSTEM MAIN IMPLEMENTATION
// =============================================================================

AdvancedPIDSystem::AdvancedPIDSystem()
: is_initialized_(false)
  , is_control_active_(false)
  , current_control_mode_(ControlMode::POSITION)
  , system_state_(SystemState::NOT_INITIALIZED)
  , last_update_time_(std::chrono::steady_clock::now())
{
    // Initialize control output
  control_output_.position_command = 0.0;
  control_output_.velocity_command = 0.0;
  control_output_.torque_command = 0.0;
  control_output_.timestamp = std::chrono::steady_clock::now();
  control_output_.is_valid = false;

    // Initialize performance metrics
  performance_metrics_.average_update_frequency = 0.0;
  performance_metrics_.control_loop_jitter_us = 0.0;
  performance_metrics_.position_tracking_error_rms = 0.0;
  performance_metrics_.velocity_tracking_error_rms = 0.0;
  performance_metrics_.settling_time_ms = 0.0;
  performance_metrics_.overshoot_percentage = 0.0;
}

AdvancedPIDSystem::~AdvancedPIDSystem()
{
  shutdown();
}

bool AdvancedPIDSystem::initialize(
  const PIDSystemConfig & config,
  std::shared_ptr<ComprehensiveErrorHandler> error_handler,
  std::shared_ptr<DualEncoderSystem> encoder_system)
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (is_initialized_) {
    return true;     // Already initialized
  }

    // Store configuration and dependencies
  config_ = config;
  error_handler_ = error_handler;
  encoder_system_ = encoder_system;

    // Validate configuration
  if (!validate_configuration()) {
    report_error("Invalid PID system configuration");
    return false;
  }

    // Initialize modular subsystems
  if (!initialize_subsystems()) {
    report_error("Failed to initialize PID subsystems");
    return false;
  }

    // Initialize control loops based on configuration
  if (!initialize_control_loops()) {
    report_error("Failed to initialize control loops");
    return false;
  }

    // Initialize diagnostics and monitoring
  initialize_diagnostics();

    // Update system state
  system_state_ = SystemState::INITIALIZED;
  is_initialized_ = true;

  log_system_event("Advanced PID system initialized successfully");
  return true;
}

void AdvancedPIDSystem::shutdown()
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (!is_initialized_) {
    return;
  }

    // Stop control if active
  stop_control();

    // Shutdown subsystems
  shutdown_subsystems();

    // Reset state
  is_initialized_ = false;
  system_state_ = SystemState::NOT_INITIALIZED;

  log_system_event("Advanced PID system shutdown");
}

bool AdvancedPIDSystem::start_control(ControlMode mode)
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (!is_initialized_) {
    report_error("Cannot start control - system not initialized");
    return false;
  }

  if (is_control_active_ && current_control_mode_ == mode) {
    return true;     // Already running in requested mode
  }

    // Validate control mode compatibility
  if (!is_control_mode_supported(mode)) {
    report_error("Unsupported control mode requested: " + std::to_string(static_cast<int>(mode)));
    return false;
  }

    // Stop current control if active
  if (is_control_active_) {
    stop_control();
  }

    // Configure for new control mode
  current_control_mode_ = mode;

    // Initialize controllers based on mode
  if (!configure_controllers_for_mode(mode)) {
    report_error("Failed to configure controllers for mode: " +
        std::to_string(static_cast<int>(mode)));
    return false;
  }

    // Start control loop
  is_control_active_ = true;
  control_thread_ = std::thread(&AdvancedPIDSystem::control_loop_worker, this);

    // Update system state
  system_state_ = SystemState::ACTIVE;

  log_system_event("PID control started in mode: " + control_mode_to_string(mode));
  return true;
}

bool AdvancedPIDSystem::stop_control()
{
  if (!is_control_active_) {
    return true;
  }

    // Signal control thread to stop
  is_control_active_ = false;

    // Wait for control thread to complete
  if (control_thread_.joinable()) {
    control_thread_.join();
  }

    // Reset control output to safe state
  reset_control_output();

    // Update system state
  system_state_ = SystemState::INITIALIZED;

  log_system_event("PID control stopped");
  return true;
}

bool AdvancedPIDSystem::set_position_target(
  double position_radians, double velocity_ff,
  double acceleration_ff)
{
  if (!is_control_active_ || !supports_position_control(current_control_mode_)) {
    return false;
  }

  std::lock_guard<std::mutex> lock(target_mutex_);

  target_state_.position = position_radians;
  target_state_.velocity = velocity_ff;
  target_state_.acceleration = acceleration_ff;
  target_state_.timestamp = std::chrono::steady_clock::now();
  target_state_.is_valid = true;

  return true;
}

bool AdvancedPIDSystem::set_velocity_target(double velocity_radians_per_sec, double acceleration_ff)
{
  if (!is_control_active_ || !supports_velocity_control(current_control_mode_)) {
    return false;
  }

  std::lock_guard<std::mutex> lock(target_mutex_);

  target_state_.velocity = velocity_radians_per_sec;
  target_state_.acceleration = acceleration_ff;
  target_state_.timestamp = std::chrono::steady_clock::now();
  target_state_.is_valid = true;

  return true;
}

bool AdvancedPIDSystem::set_torque_target(double torque_nm)
{
  if (!is_control_active_ || !supports_torque_control(current_control_mode_)) {
    return false;
  }

  std::lock_guard<std::mutex> lock(target_mutex_);

  target_state_.torque = torque_nm;
  target_state_.timestamp = std::chrono::steady_clock::now();
  target_state_.is_valid = true;

  return true;
}

PIDControlOutput AdvancedPIDSystem::get_control_output() const
{
  std::lock_guard<std::mutex> lock(output_mutex_);
  return control_output_;
}

bool AdvancedPIDSystem::update_pid_parameters(
  const PIDParameters & params,
  ControllerType controller_type)
{
  if (!is_initialized_) {
    return false;
  }

  std::lock_guard<std::mutex> lock(config_mutex_);

    // Validate parameters
  if (!validate_pid_parameters(params)) {
    report_error("Invalid PID parameters provided");
    return false;
  }

    // Update parameters based on controller type
  switch (controller_type) {
    case ControllerType::POSITION_CONTROLLER:
      config_.position_pid = params;
      break;
    case ControllerType::VELOCITY_CONTROLLER:
      config_.velocity_pid = params;
      break;
    case ControllerType::TORQUE_CONTROLLER:
      config_.torque_pid = params;
      break;
    default:
      return false;
  }

    // Apply parameters to active controllers
  if (is_control_active_) {
    apply_pid_parameters_to_controllers();
  }

  log_system_event("PID parameters updated for controller: " +
      std::to_string(static_cast<int>(controller_type)));
  return true;
}

bool AdvancedPIDSystem::start_auto_tuning(ControllerType controller_type, AutoTuningMethod method)
{
  if (!is_initialized_ || !auto_tuner_) {
    return false;
  }

  return auto_tuner_->start_tuning(controller_type, method);
}

bool AdvancedPIDSystem::stop_auto_tuning()
{
  if (!auto_tuner_) {
    return false;
  }

  return auto_tuner_->stop_tuning();
}

AutoTuningStatus AdvancedPIDSystem::get_auto_tuning_status() const
{
  if (!auto_tuner_) {
    AutoTuningStatus status;
    status.is_active = false;
    status.progress_percentage = 0.0;
    status.current_method = AutoTuningMethod::ZIEGLER_NICHOLS;
    status.estimated_completion_time = std::chrono::steady_clock::now();
    return status;
  }

  return auto_tuner_->get_status();
}

bool AdvancedPIDSystem::enable_adaptive_control(bool enable)
{
    // Placeholder - adaptive controller to be implemented
    // if (!adaptive_controller_) {
    //     return false;
    // }
    // return adaptive_controller_->enable_adaptation(enable);
  return false;   // Not implemented yet
}

bool AdvancedPIDSystem::optimize_for_motor_characteristics(const MotorCharacteristics & motor_chars)
{
    // Placeholder - motor optimizer to be implemented
    // if (!motor_optimizer_) {
    //     return false;
    // }
    // return motor_optimizer_->optimize_for_motor(motor_chars);
  return false;   // Not implemented yet
}

SystemState AdvancedPIDSystem::get_system_state() const
{
  std::lock_guard<std::mutex> lock(system_mutex_);
  return system_state_;
}

PIDPerformanceMetrics AdvancedPIDSystem::get_performance_metrics() const
{
  std::lock_guard<std::mutex> lock(metrics_mutex_);
  return performance_metrics_;
}

PIDDiagnosticData AdvancedPIDSystem::get_diagnostic_data() const
{
  std::lock_guard<std::mutex> lock(diagnostics_mutex_);
  return diagnostic_data_;
}

// =============================================================================
// PRIVATE IMPLEMENTATION METHODS
// =============================================================================

bool AdvancedPIDSystem::validate_configuration()
{
    // Validate basic parameters
  if (config_.control_frequency_hz <= 0 || config_.control_frequency_hz > 10000) {
    return false;
  }

    // Validate PID parameters for each controller
  if (!validate_pid_parameters(config_.position_pid) ||
    !validate_pid_parameters(config_.velocity_pid) ||
    !validate_pid_parameters(config_.torque_pid))
  {
    return false;
  }

    // Validate limits
  if (config_.max_position_error_radians <= 0 ||
    config_.max_velocity_error_radians_per_sec <= 0 ||
    config_.max_torque_output_nm <= 0)
  {
    return false;
  }

  return true;
}

bool AdvancedPIDSystem::validate_pid_parameters(const PIDParameters & params)
{
  return  params.kp >= 0.0 && params.ki >= 0.0 && params.kd >= 0.0 &&
         params.output_min < params.output_max &&
         params.integral_windup_limit > 0.0;
}

bool AdvancedPIDSystem::initialize_subsystems()
{
  try {
        // Initialize auto-tuner
    auto_tuner_ = std::make_unique<PIDAutoTuner>(config_.auto_tuning, error_handler_);
    if (!auto_tuner_->initialize()) {
      return false;
    }

        // Initialize cascaded controller
    cascaded_controller_ = std::make_unique<PIDCascadedController>(config_.cascaded_control,
        error_handler_);
    if (!cascaded_controller_->initialize()) {
      return false;
    }

        // Initialize motor optimizer (placeholder - to be implemented)
        // motor_optimizer_ = std::make_unique<PIDMotorOptimizer>(config_.motor_optimization, error_handler_);
        // if (!motor_optimizer_->initialize()) {
        //     return false;
        // }

        // Initialize adaptive controller (placeholder - to be implemented)
        // adaptive_controller_ = std::make_unique<PIDAdaptiveController>(config_.adaptive_control, error_handler_);
        // if (!adaptive_controller_->initialize()) {
        //     return false;
        // }

    return true;

  } catch (const std::exception & e) {
    report_error(std::string("Exception during subsystem initialization: ") + e.what());
    return false;
  }
}

void AdvancedPIDSystem::shutdown_subsystems()
{
    // if (adaptive_controller_) {
    //     adaptive_controller_->shutdown();
    //     adaptive_controller_.reset();
    // }

    // if (motor_optimizer_) {
    //     motor_optimizer_->shutdown();
    //     motor_optimizer_.reset();
    // }

  if (cascaded_controller_) {
    cascaded_controller_->shutdown();
    cascaded_controller_.reset();
  }

  if (auto_tuner_) {
    auto_tuner_->shutdown();
    auto_tuner_.reset();
  }
}

bool AdvancedPIDSystem::initialize_control_loops()
{
    // Initialize individual PID controllers
  position_controller_ = std::make_unique<BasicPIDController>(config_.position_pid);
  velocity_controller_ = std::make_unique<BasicPIDController>(config_.velocity_pid);
  torque_controller_ = std::make_unique<BasicPIDController>(config_.torque_pid);

  return  position_controller_ && velocity_controller_ && torque_controller_;
}

void AdvancedPIDSystem::initialize_diagnostics()
{
  diagnostic_data_.system_start_time = std::chrono::steady_clock::now();
  diagnostic_data_.total_control_cycles = 0;
  diagnostic_data_.control_loop_overruns = 0;
  diagnostic_data_.pid_computation_failures = 0;
  diagnostic_data_.target_update_failures = 0;
  diagnostic_data_.encoder_read_failures = 0;
  diagnostic_data_.max_computation_time_us = 0.0;
  diagnostic_data_.average_computation_time_us = 0.0;
}

bool AdvancedPIDSystem::is_control_mode_supported(ControlMode mode)
{
    // All control modes are supported in this implementation
  return true;
}

bool AdvancedPIDSystem::configure_controllers_for_mode(ControlMode mode)
{
  try {
    switch (mode) {
      case ControlMode::POSITION:
        return configure_position_mode();
      case ControlMode::VELOCITY:
        return configure_velocity_mode();
      case ControlMode::TORQUE:
        return configure_torque_mode();
      case ControlMode::CASCADED_POSITION_VELOCITY:
        return configure_cascaded_mode();
      case ControlMode::ADAPTIVE_POSITION:
        return configure_adaptive_mode();
      default:
        return false;
    }
  } catch (const std::exception & e) {
    report_error(std::string("Exception during controller configuration: ") + e.what());
    return false;
  }
}

bool AdvancedPIDSystem::configure_position_mode()
{
    // Configure for position control
  position_controller_->reset();
  position_controller_->set_parameters(config_.position_pid);
  return true;
}

bool AdvancedPIDSystem::configure_velocity_mode()
{
    // Configure for velocity control
  velocity_controller_->reset();
  velocity_controller_->set_parameters(config_.velocity_pid);
  return true;
}

bool AdvancedPIDSystem::configure_torque_mode()
{
    // Configure for torque control
  torque_controller_->reset();
  torque_controller_->set_parameters(config_.torque_pid);
  return true;
}

bool AdvancedPIDSystem::configure_cascaded_mode()
{
    // Configure cascaded position-velocity control
  if (!cascaded_controller_) {
    return false;
  }

  return cascaded_controller_->configure_for_position_velocity_cascade();
}

bool AdvancedPIDSystem::configure_adaptive_mode()
{
    // Configure adaptive position control
  if (!adaptive_controller_) {
    return false;
  }

  return adaptive_controller_->configure_for_position_control();
}

void AdvancedPIDSystem::apply_pid_parameters_to_controllers()
{
  if (position_controller_) {
    position_controller_->set_parameters(config_.position_pid);
  }
  if (velocity_controller_) {
    velocity_controller_->set_parameters(config_.velocity_pid);
  }
  if (torque_controller_) {
    torque_controller_->set_parameters(config_.torque_pid);
  }
}

bool AdvancedPIDSystem::supports_position_control(ControlMode mode)
{
  return  mode == ControlMode::POSITION ||
         mode == ControlMode::CASCADED_POSITION_VELOCITY ||
         mode == ControlMode::ADAPTIVE_POSITION;
}

bool AdvancedPIDSystem::supports_velocity_control(ControlMode mode)
{
  return  mode == ControlMode::VELOCITY ||
         mode == ControlMode::CASCADED_POSITION_VELOCITY;
}

bool AdvancedPIDSystem::supports_torque_control(ControlMode mode)
{
  return  mode == ControlMode::TORQUE;
}

void AdvancedPIDSystem::reset_control_output()
{
  std::lock_guard<std::mutex> lock(output_mutex_);

  control_output_.position_command = 0.0;
  control_output_.velocity_command = 0.0;
  control_output_.torque_command = 0.0;
  control_output_.timestamp = std::chrono::steady_clock::now();
  control_output_.is_valid = false;
}

std::string AdvancedPIDSystem::control_mode_to_string(ControlMode mode)
{
  switch (mode) {
    case ControlMode::POSITION: return "POSITION";
    case ControlMode::VELOCITY: return "VELOCITY";
    case ControlMode::TORQUE: return "TORQUE";
    case ControlMode::CASCADED_POSITION_VELOCITY: return "CASCADED_POSITION_VELOCITY";
    case ControlMode::ADAPTIVE_POSITION: return "ADAPTIVE_POSITION";
    default: return "UNKNOWN";
  }
}

void AdvancedPIDSystem::report_error(const std::string & message)
{
  if (error_handler_) {
    error_handler_->report_error(
            ErrorLevel::ERROR,
            "ADVANCED_PID_ERROR",
            message,
            ErrorType::SYSTEM_ERROR,
            "advanced_pid_system"
    );
  }

  log_system_event("ERROR: " + message);
}

void AdvancedPIDSystem::log_system_event(const std::string & message)
{
    // Simple timestamp + message logging
  auto now = std::chrono::system_clock::now();
  auto time_t = std::chrono::system_clock::to_time_t(now);

  std::lock_guard<std::mutex> lock(log_mutex_);
  system_event_log_.push_back("[" + std::to_string(time_t) + "] " + message);

    // Maintain log size
  if (system_event_log_.size() > config_.max_log_entries) {
    system_event_log_.pop_front();
  }
}

// =============================================================================
// CONTROL LOOP WORKER THREAD
// =============================================================================

void AdvancedPIDSystem::control_loop_worker()
{
  log_system_event("Control loop worker thread started");

    // Calculate control loop timing
  const auto cycle_time = std::chrono::microseconds(
        static_cast<long>(1000000.0 / config_.control_frequency_hz));

  auto next_cycle_time = std::chrono::steady_clock::now();
  auto last_encoder_read = std::chrono::steady_clock::now();

    // Note: Error tracking for performance metrics implemented via update_control_performance_metrics()

  while (is_control_active_) {
    auto cycle_start = std::chrono::steady_clock::now();

    try {
            // Read encoder data
      EncoderData encoder_data;
      bool encoder_valid = read_encoder_data(encoder_data);

      if (!encoder_valid) {
        handle_encoder_read_failure();
        continue;
      }

            // Get current targets
      TargetState current_targets;
      {
        std::lock_guard<std::mutex> lock(target_mutex_);
        current_targets = target_state_;
      }

            // Check target validity and age
      if (!validate_targets(current_targets)) {
        handle_invalid_targets();
        continue;
      }

            // Compute control output based on active mode
      PIDControlOutput output;
      bool computation_success = false;

      switch (current_control_mode_) {
        case ControlMode::POSITION:
          computation_success = compute_position_control(encoder_data, current_targets, output);
          break;

        case ControlMode::VELOCITY:
          computation_success = compute_velocity_control(encoder_data, current_targets, output);
          break;

        case ControlMode::TORQUE:
          computation_success = compute_torque_control(encoder_data, current_targets, output);
          break;

        case ControlMode::CASCADED_POSITION_VELOCITY:
          computation_success = compute_cascaded_control(encoder_data, current_targets, output);
          break;

        case ControlMode::ADAPTIVE_POSITION:
          computation_success = compute_adaptive_control(encoder_data, current_targets, output);
          break;

        default:
          report_error("Unknown control mode in worker thread");
          computation_success = false;
          break;
      }

      if (computation_success) {
                // Apply safety limits
        apply_safety_limits(output);

                // Update output
        {
          std::lock_guard<std::mutex> lock(output_mutex_);
          control_output_ = output;
          control_output_.timestamp = cycle_start;
          control_output_.is_valid = true;
        }

                // Update performance metrics
        update_control_performance_metrics(encoder_data, current_targets, cycle_start);

      } else {
                // Handle computation failure
        handle_computation_failure();
      }

            // Update diagnostics
      update_control_diagnostics(cycle_start);

    } catch (const std::exception & e) {
      report_error(std::string("Exception in control loop: ") + e.what());
      handle_control_exception();
    }

        // Sleep until next cycle
    next_cycle_time += cycle_time;

        // Check for timing violations
    auto now = std::chrono::steady_clock::now();
    if (now > next_cycle_time) {
            // Control loop overrun
      std::lock_guard<std::mutex> lock(diagnostics_mutex_);
      diagnostic_data_.control_loop_overruns++;

            // Reset timing to avoid permanent overrun
      next_cycle_time = now + cycle_time;
    }

    std::this_thread::sleep_until(next_cycle_time);
  }

  log_system_event("Control loop worker thread completed");
}

bool AdvancedPIDSystem::read_encoder_data(EncoderData & encoder_data)
{
  if (!encoder_system_) {
    return false;
  }

  try {
        // Get fused position and velocity data from dual encoder system
    auto position_data = encoder_system_->get_position_data();
    auto velocity_data = encoder_system_->get_velocity_data();

    if (!position_data.is_valid || !velocity_data.is_valid) {
      return false;
    }

        // Fill encoder data structure
    encoder_data.position = position_data.position;
    encoder_data.velocity = velocity_data.velocity;
    encoder_data.timestamp = std::max(position_data.timestamp, velocity_data.timestamp);
    encoder_data.is_valid = true;
    encoder_data.position_uncertainty = position_data.uncertainty;
    encoder_data.velocity_uncertainty = velocity_data.uncertainty;

    return true;

  } catch (const std::exception & e) {
    report_error(std::string("Exception reading encoder data: ") + e.what());
    return false;
  }
}

bool AdvancedPIDSystem::validate_targets(const TargetState & targets)
{
  if (!targets.is_valid) {
    return false;
  }

    // Check target age
  auto now = std::chrono::steady_clock::now();
  auto target_age = std::chrono::duration_cast<std::chrono::milliseconds>(now - targets.timestamp);

  if (target_age.count() > config_.max_target_age_ms) {
    return false;
  }

    // Check for reasonable values
  if (!std::isfinite(targets.position) || !std::isfinite(targets.velocity) ||
    !std::isfinite(targets.torque))
  {
    return false;
  }

    // Check limits
  if (std::abs(targets.position) > config_.max_position_radians ||
    std::abs(targets.velocity) > config_.max_velocity_radians_per_sec ||
    std::abs(targets.torque) > config_.max_torque_output_nm)
  {
    return false;
  }

  return true;
}

bool AdvancedPIDSystem::compute_position_control(
  const EncoderData & encoder_data,
  const TargetState & targets,
  PIDControlOutput & output)
{
  if (!position_controller_) {
    return false;
  }

    // Calculate position error
  double position_error = targets.position - encoder_data.position;

    // Compute PID output
  double control_output = position_controller_->compute(position_error, encoder_data.timestamp);

    // Add feedforward
  control_output += targets.velocity;   // Velocity feedforward

    // Set output (position control typically outputs velocity command)
  output.position_command = targets.position;
  output.velocity_command = control_output;
  output.torque_command = 0.0;   // Not used in pure position control

  return true;
}

bool AdvancedPIDSystem::compute_velocity_control(
  const EncoderData & encoder_data,
  const TargetState & targets,
  PIDControlOutput & output)
{
  if (!velocity_controller_) {
    return false;
  }

    // Calculate velocity error
  double velocity_error = targets.velocity - encoder_data.velocity;

    // Compute PID output
  double control_output = velocity_controller_->compute(velocity_error, encoder_data.timestamp);

    // Add feedforward
  control_output += targets.acceleration * config_.motor_inertia_kg_m2;   // Acceleration feedforward

    // Set output (velocity control typically outputs torque command)
  output.position_command = 0.0;   // Not controlled
  output.velocity_command = targets.velocity;
  output.torque_command = control_output;

  return true;
}

bool AdvancedPIDSystem::compute_torque_control(
  const EncoderData & encoder_data,
  const TargetState & targets,
  PIDControlOutput & output)
{
    // Direct torque control - minimal processing
  output.position_command = 0.0;   // Not controlled
  output.velocity_command = 0.0;   // Not controlled
  output.torque_command = targets.torque;

  return true;
}

bool AdvancedPIDSystem::compute_cascaded_control(
  const EncoderData & encoder_data,
  const TargetState & targets,
  PIDControlOutput & output)
{
  if (!cascaded_controller_) {
    return false;
  }

    // Prepare cascade feedback
  CascadeFeedback feedback;
  feedback.position = encoder_data.position;
  feedback.velocity = encoder_data.velocity;
  feedback.current = 0.0;   // Not available in this context
  feedback.has_current_feedback = false;
  feedback.timestamp = encoder_data.timestamp;
  feedback.is_valid = encoder_data.is_valid;

    // Prepare cascade targets
  CascadeTargets cascade_targets;
  cascade_targets.position = targets.position;
  cascade_targets.velocity = targets.velocity;
  cascade_targets.velocity_feedforward = targets.velocity;
  cascade_targets.acceleration_feedforward = targets.acceleration;
  cascade_targets.timestamp = targets.timestamp;

    // Set targets
  if (!cascaded_controller_->set_cascade_targets(cascade_targets)) {
    return false;
  }

    // Compute cascade control
  auto cascade_output = cascaded_controller_->compute_cascade_control(feedback);

  if (!cascade_output.is_valid) {
    return false;
  }

    // Transfer results
  output.position_command = cascade_output.position_command;
  output.velocity_command = cascade_output.velocity_command;
  output.torque_command = cascade_output.torque_command;

  return true;
}

bool AdvancedPIDSystem::compute_adaptive_control(
  const EncoderData & encoder_data,
  const TargetState & targets,
  PIDControlOutput & output)
{
    // Placeholder - adaptive controller to be implemented
    // if (!adaptive_controller_) {
    //     return false;
    // }
    // return adaptive_controller_->compute_adaptive_control(encoder_data, targets, output);

    // For now, fallback to position control
  return compute_position_control(encoder_data, targets, output);
}

void AdvancedPIDSystem::apply_safety_limits(PIDControlOutput & output)
{
    // Apply position limits
  if (config_.enable_position_limits) {
    output.position_command = std::max(config_.position_limits.min_value,
                                          std::min(config_.position_limits.max_value,
        output.position_command));
  }

    // Apply velocity limits
  if (config_.enable_velocity_limits) {
    output.velocity_command = std::max(config_.velocity_limits.min_value,
                                          std::min(config_.velocity_limits.max_value,
        output.velocity_command));
  }

    // Apply torque limits
  if (config_.enable_torque_limits) {
    output.torque_command = std::max(config_.torque_limits.min_value,
                                        std::min(config_.torque_limits.max_value,
        output.torque_command));
  }
}

void AdvancedPIDSystem::update_control_performance_metrics(
  const EncoderData & encoder_data,
  const TargetState & targets,
  const std::chrono::steady_clock::time_point & cycle_start)
{
  std::lock_guard<std::mutex> lock(metrics_mutex_);

    // Calculate tracking errors
  double position_error = targets.position - encoder_data.position;
  double velocity_error = targets.velocity - encoder_data.velocity;

    // Update RMS tracking errors (simple moving average)
  static std::deque<double> position_error_history;
  static std::deque<double> velocity_error_history;
  const size_t max_history = 100;

  position_error_history.push_back(position_error * position_error);
  velocity_error_history.push_back(velocity_error * velocity_error);

  if (position_error_history.size() > max_history) {
    position_error_history.pop_front();
  }
  if (velocity_error_history.size() > max_history) {
    velocity_error_history.pop_front();
  }

    // Calculate RMS values
  if (!position_error_history.empty()) {
    double sum = std::accumulate(position_error_history.begin(), position_error_history.end(), 0.0);
    performance_metrics_.position_tracking_error_rms = std::sqrt(sum /
        position_error_history.size());
  }

  if (!velocity_error_history.empty()) {
    double sum = std::accumulate(velocity_error_history.begin(), velocity_error_history.end(), 0.0);
    performance_metrics_.velocity_tracking_error_rms = std::sqrt(sum /
        velocity_error_history.size());
  }

    // Update control frequency
  static auto last_update = std::chrono::steady_clock::now();
  static int cycle_count = 0;

  cycle_count++;
  if (cycle_count >= 100) {   // Update every 100 cycles
    auto elapsed = std::chrono::duration<double>(cycle_start - last_update).count();
    performance_metrics_.average_update_frequency = cycle_count / elapsed;

    last_update = cycle_start;
    cycle_count = 0;
  }
}

void AdvancedPIDSystem::update_control_diagnostics(
  const std::chrono::steady_clock::time_point & cycle_start)
{
  std::lock_guard<std::mutex> lock(diagnostics_mutex_);

  diagnostic_data_.total_control_cycles++;

    // Update computation time
  auto computation_time = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - cycle_start);

  diagnostic_data_.max_computation_time_us = std::max(diagnostic_data_.max_computation_time_us,
                                                        static_cast<double>(computation_time.count()));

    // Update average computation time
  diagnostic_data_.average_computation_time_us =
    (diagnostic_data_.average_computation_time_us + computation_time.count()) / 2.0;
}

void AdvancedPIDSystem::handle_encoder_read_failure()
{
  std::lock_guard<std::mutex> lock(diagnostics_mutex_);
  diagnostic_data_.encoder_read_failures++;

    // Reset control output to safe state
  reset_control_output();
}

void AdvancedPIDSystem::handle_invalid_targets()
{
  std::lock_guard<std::mutex> lock(diagnostics_mutex_);
  diagnostic_data_.target_update_failures++;
}

void AdvancedPIDSystem::handle_computation_failure()
{
  std::lock_guard<std::mutex> lock(diagnostics_mutex_);
  diagnostic_data_.pid_computation_failures++;

    // Reset control output to safe state
  reset_control_output();
}

void AdvancedPIDSystem::handle_control_exception()
{
    // Stop control on exception
  is_control_active_ = false;

    // Reset control output
  reset_control_output();

    // Update system state
  system_state_ = SystemState::ERROR;
}

} // namespace motor_control_ros2
