/*
 * Dual Encoder System Implementation
 *
 * This implementation provides redundant encoder support with:
 * - Primary/secondary encoder redundancy
 * - Real-time cross-validation and sensor fusion
 * - Advanced fault detection and automatic fallback
 * - Kalman filtering and adaptive weighting algorithms
 * - Comprehensive diagnostics and performance monitoring
 */

#include "motor_control_ros2/dual_encoder_system.hpp"
#include <algorithm>
#include <cmath>
#include <numeric>

namespace motor_control_ros2
{

// =============================================================================
// DUAL ENCODER SYSTEM IMPLEMENTATION
// =============================================================================

DualEncoderSystem::DualEncoderSystem()
: is_initialized_(false)
  , is_acquisition_running_(false)
  , acquisition_thread_active_(false)
  , current_fusion_algorithm_(SensorFusionAlgorithm::ADAPTIVE_WEIGHTED)
  , system_status_({SystemStatus::NOT_INITIALIZED, false, false, false, false})
{
    // Initialize timestamps
  auto now = std::chrono::steady_clock::now();
  last_primary_update_ = now;
  last_secondary_update_ = now;
  last_validation_time_ = now;

    // Initialize Kalman filter
  initialize_kalman_filter();
}

DualEncoderSystem::~DualEncoderSystem()
{
  shutdown();
}

bool DualEncoderSystem::initialize(
  const DualEncoderConfig & config,
  std::shared_ptr<ComprehensiveErrorHandler> error_handler)
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (is_initialized_) {
    return true;     // Already initialized
  }

    // Store configuration and dependencies
  config_ = config;
  error_handler_ = error_handler;

    // Validate configuration
  if (!validate_configuration()) {
    return false;
  }

    // Initialize encoder interfaces
  if (!initialize_encoder_interfaces()) {
    return false;
  }

    // Initialize sensor fusion
  if (!initialize_sensor_fusion()) {
    return false;
  }

    // Initialize diagnostics
  initialize_diagnostics();

    // Update system status
  system_status_.status = SystemStatus::INITIALIZED;
  system_status_.primary_encoder_healthy = true;
  system_status_.secondary_encoder_healthy = true;
  system_status_.cross_validation_active = config_.enable_cross_validation;
  system_status_.sensor_fusion_active = config_.enable_sensor_fusion;

  is_initialized_ = true;

  log_system_event("Dual encoder system initialized successfully");
  return true;
}

void DualEncoderSystem::shutdown()
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (!is_initialized_) {
    return;
  }

    // Stop acquisition
  stop_acquisition();

    // Shutdown encoder interfaces
  primary_encoder_.reset();
  secondary_encoder_.reset();

    // Reset state
  is_initialized_ = false;
  system_status_.status = SystemStatus::NOT_INITIALIZED;

  log_system_event("Dual encoder system shutdown");
}

bool DualEncoderSystem::start_acquisition()
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (!is_initialized_) {
    report_error("Cannot start acquisition - system not initialized");
    return false;
  }

  if (is_acquisition_running_) {
    return true;     // Already running
  }

    // Start acquisition thread
  acquisition_thread_active_ = true;
  acquisition_thread_ = std::thread(&DualEncoderSystem::acquisition_worker_thread, this);

    // Start cross-validation thread if enabled
  if (config_.enable_cross_validation) {
    validation_thread_active_ = true;
    validation_thread_ = std::thread(&DualEncoderSystem::validation_worker_thread, this);
  }

  is_acquisition_running_ = true;

  log_system_event("Dual encoder acquisition started");
  return true;
}

bool DualEncoderSystem::stop_acquisition()
{
  if (!is_acquisition_running_) {
    return true;
  }

    // Signal threads to stop
  acquisition_thread_active_ = false;
  validation_thread_active_ = false;

    // Wait for threads to complete
  if (acquisition_thread_.joinable()) {
    acquisition_thread_.join();
  }

  if (validation_thread_.joinable()) {
    validation_thread_.join();
  }

  is_acquisition_running_ = false;

  log_system_event("Dual encoder acquisition stopped");
  return true;
}

bool DualEncoderSystem::is_initialized() const
{
  std::lock_guard<std::mutex> lock(system_mutex_);
  return is_initialized_;
}

EncoderData DualEncoderSystem::get_primary_encoder_data() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return latest_primary_data_;
}

EncoderData DualEncoderSystem::get_secondary_encoder_data() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return latest_secondary_data_;
}

FusedPositionData DualEncoderSystem::get_position_data() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return latest_fused_position_;
}

FusedVelocityData DualEncoderSystem::get_velocity_data() const
{
  std::lock_guard<std::mutex> lock(data_mutex_);
  return latest_fused_velocity_;
}

bool DualEncoderSystem::perform_cross_validation()
{
  if (!config_.enable_cross_validation) {
    return true;     // Cross-validation disabled
  }

  std::lock_guard<std::mutex> lock(data_mutex_);

    // Get latest data from both encoders
  auto primary_data = latest_primary_data_;
  auto secondary_data = latest_secondary_data_;

    // Check data freshness
  auto now = std::chrono::steady_clock::now();
  auto primary_age = std::chrono::duration_cast<std::chrono::milliseconds>(now -
      primary_data.timestamp);
  auto secondary_age = std::chrono::duration_cast<std::chrono::milliseconds>(now -
      secondary_data.timestamp);

  if (primary_age.count() > config_.max_data_age_ms ||
    secondary_age.count() > config_.max_data_age_ms)
  {
    report_error("Encoder data is too old for cross-validation");
    return false;
  }

    // Perform position cross-validation
  double position_difference = std::abs(primary_data.position - secondary_data.position);
  if (position_difference > config_.position_tolerance_radians) {
    std::ostringstream oss;
    oss << "Position cross-validation failed: difference = " << position_difference << " rad";
    report_error(oss.str());

        // Update validation results
    validation_results_.position_validation_passed = false;
    validation_results_.position_difference = position_difference;
    validation_results_.last_validation_time = now;

    return false;
  }

    // Perform velocity cross-validation
  double velocity_difference = std::abs(primary_data.velocity - secondary_data.velocity);
  if (velocity_difference > config_.velocity_tolerance_radians_per_sec) {
    std::ostringstream oss;
    oss << "Velocity cross-validation failed: difference = " << velocity_difference << " rad/s";
    report_error(oss.str());

    validation_results_.velocity_validation_passed = false;
    validation_results_.velocity_difference = velocity_difference;
    validation_results_.last_validation_time = now;

    return false;
  }

    // Cross-validation passed
  validation_results_.position_validation_passed = true;
  validation_results_.velocity_validation_passed = true;
  validation_results_.position_difference = position_difference;
  validation_results_.velocity_difference = velocity_difference;
  validation_results_.last_validation_time = now;

  return true;
}

std::vector<EncoderFault> DualEncoderSystem::detect_encoder_faults()
{
  std::vector<EncoderFault> faults;

  std::lock_guard<std::mutex> lock(data_mutex_);

  auto now = std::chrono::steady_clock::now();

    // Check primary encoder faults
  auto primary_faults = detect_individual_encoder_faults(latest_primary_data_, "primary", now);
  faults.insert(faults.end(), primary_faults.begin(), primary_faults.end());

    // Check secondary encoder faults
  auto secondary_faults = detect_individual_encoder_faults(latest_secondary_data_, "secondary",
      now);
  faults.insert(faults.end(), secondary_faults.begin(), secondary_faults.end());

    // Check cross-validation faults
  if (config_.enable_cross_validation && !validation_results_.position_validation_passed) {
    EncoderFault fault;
    fault.encoder_name = "cross_validation";
    fault.fault_type = FaultType::VALIDATION_FAILURE;
    fault.severity = FaultSeverity::WARNING;
    fault.description = "Position cross-validation failed";
    fault.detected_time = now;
    fault.is_recoverable = true;
    faults.push_back(fault);
  }

  if (config_.enable_cross_validation && !validation_results_.velocity_validation_passed) {
    EncoderFault fault;
    fault.encoder_name = "cross_validation";
    fault.fault_type = FaultType::VALIDATION_FAILURE;
    fault.severity = FaultSeverity::WARNING;
    fault.description = "Velocity cross-validation failed";
    fault.detected_time = now;
    fault.is_recoverable = true;
    faults.push_back(fault);
  }

  return faults;
}

bool DualEncoderSystem::force_fallback_mode(bool use_primary)
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (use_primary) {
    system_status_.status = SystemStatus::PRIMARY_ONLY;
    system_status_.secondary_encoder_healthy = false;
    log_system_event("Forced fallback to primary encoder only");
  } else {
    system_status_.status = SystemStatus::SECONDARY_ONLY;
    system_status_.primary_encoder_healthy = false;
    log_system_event("Forced fallback to secondary encoder only");
  }

    // Update fusion algorithm to single encoder
  current_fusion_algorithm_ = SensorFusionAlgorithm::SINGLE_ENCODER;

  return true;
}

bool DualEncoderSystem::calibrate_encoders()
{
  if (!is_initialized_) {
    report_error("Cannot calibrate - system not initialized");
    return false;
  }

  log_system_event("Starting encoder calibration");

  bool primary_success = calibrate_individual_encoder(primary_encoder_, "primary");
  bool secondary_success = calibrate_individual_encoder(secondary_encoder_, "secondary");

  if (primary_success && secondary_success) {
    log_system_event("Encoder calibration completed successfully");
    return true;
  } else if (primary_success || secondary_success) {
    std::string message = "Partial encoder calibration success: ";
    message += primary_success ? "primary OK, " : "primary FAILED, ";
    message += secondary_success ? "secondary OK" : "secondary FAILED";
    log_system_event(message);
    return false;
  } else {
    report_error("All encoder calibrations failed");
    return false;
  }
}

bool DualEncoderSystem::set_fusion_algorithm(SensorFusionAlgorithm algorithm)
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  if (algorithm == SensorFusionAlgorithm::SINGLE_ENCODER &&
    (system_status_.status == SystemStatus::DUAL_ENCODER_ACTIVE))
  {
        // Cannot use single encoder mode when both encoders are active
    return false;
  }

  current_fusion_algorithm_ = algorithm;

    // Reinitialize fusion if necessary
  if (algorithm == SensorFusionAlgorithm::KALMAN_FILTER) {
    initialize_kalman_filter();
  }

  log_system_event("Fusion algorithm changed to " + std::to_string(static_cast<int>(algorithm)));
  return true;
}

DualEncoderSystem::SystemStatus DualEncoderSystem::get_system_status() const
{
  std::lock_guard<std::mutex> lock(system_mutex_);
  return system_status_;
}

DiagnosticData DualEncoderSystem::get_diagnostic_data() const
{
  std::lock_guard<std::mutex> lock(diagnostic_mutex_);
  return diagnostic_data_;
}

PerformanceMetrics DualEncoderSystem::get_performance_metrics() const
{
  std::lock_guard<std::mutex> lock(diagnostic_mutex_);

  PerformanceMetrics metrics;

    // Calculate average acquisition frequency and error rates
  if (diagnostic_data_.total_acquisition_cycles > 0) {
    auto elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - diagnostic_data_.system_start_time).count();
    metrics.average_acquisition_frequency = diagnostic_data_.total_acquisition_cycles / elapsed;
    
    // Calculate error rates (same guard condition applies)
    metrics.primary_error_rate = static_cast<double>(diagnostic_data_.primary_encoder_errors) /
      diagnostic_data_.total_acquisition_cycles;
    metrics.secondary_error_rate = static_cast<double>(diagnostic_data_.secondary_encoder_errors) /
      diagnostic_data_.total_acquisition_cycles;
    metrics.validation_failure_rate = static_cast<double>(diagnostic_data_.validation_failures) /
      diagnostic_data_.total_acquisition_cycles;
  }

    // Copy other metrics
  metrics.fusion_processing_time_us = diagnostic_data_.average_fusion_time_us;
  metrics.cross_validation_time_us = diagnostic_data_.average_validation_time_us;
  metrics.data_freshness_primary_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - last_primary_update_).count();
  metrics.data_freshness_secondary_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - last_secondary_update_).count();

  return metrics;
}

// =============================================================================
// PRIVATE IMPLEMENTATION METHODS
// =============================================================================

bool DualEncoderSystem::validate_configuration()
{
  if (config_.position_tolerance_radians <= 0) {
    report_error("Invalid position tolerance in configuration");
    return false;
  }

  if (config_.velocity_tolerance_radians_per_sec <= 0) {
    report_error("Invalid velocity tolerance in configuration");
    return false;
  }

  if (config_.acquisition_frequency_hz <= 0 || config_.acquisition_frequency_hz > 10000) {
    report_error("Invalid acquisition frequency in configuration");
    return false;
  }

  return true;
}

bool DualEncoderSystem::initialize_encoder_interfaces()
{
    // Initialize primary encoder interface
  primary_encoder_ = create_encoder_interface(config_.primary_encoder);
  if (!primary_encoder_ || !primary_encoder_->initialize()) {
    report_error("Failed to initialize primary encoder");
    return false;
  }

    // Initialize secondary encoder interface
  secondary_encoder_ = create_encoder_interface(config_.secondary_encoder);
  if (!secondary_encoder_ || !secondary_encoder_->initialize()) {
    report_error("Failed to initialize secondary encoder");
    primary_encoder_.reset();
    return false;
  }

  return true;
}

bool DualEncoderSystem::initialize_sensor_fusion()
{
    // Initialize fusion algorithms based on configuration
  switch (config_.default_fusion_algorithm) {
    case SensorFusionAlgorithm::SIMPLE_AVERAGE:
            // No special initialization needed
      break;

    case SensorFusionAlgorithm::WEIGHTED_AVERAGE:
            // Initialize with default weights
      fusion_weights_.primary_weight = 0.6;
      fusion_weights_.secondary_weight = 0.4;
      break;

    case SensorFusionAlgorithm::KALMAN_FILTER:
      initialize_kalman_filter();
      break;

    case SensorFusionAlgorithm::ADAPTIVE_WEIGHTED:
      initialize_adaptive_weighting();
      break;

    default:
      report_error("Unknown fusion algorithm in configuration");
      return false;
  }

  current_fusion_algorithm_ = config_.default_fusion_algorithm;
  return true;
}

void DualEncoderSystem::initialize_diagnostics()
{
  diagnostic_data_.system_start_time = std::chrono::steady_clock::now();
  diagnostic_data_.total_acquisition_cycles = 0;
  diagnostic_data_.primary_encoder_errors = 0;
  diagnostic_data_.secondary_encoder_errors = 0;
  diagnostic_data_.validation_failures = 0;
  diagnostic_data_.fusion_failures = 0;
  diagnostic_data_.average_fusion_time_us = 0.0;
  diagnostic_data_.average_validation_time_us = 0.0;
  diagnostic_data_.max_position_difference = 0.0;
  diagnostic_data_.max_velocity_difference = 0.0;
}

void DualEncoderSystem::initialize_kalman_filter()
{
    // Initialize Kalman filter for position and velocity estimation
    // State vector: [position, velocity]
    // Measurement: [position_primary, position_secondary]

  kalman_filter_.state = Eigen::Vector2d::Zero();
  kalman_filter_.covariance = Eigen::Matrix2d::Identity() * 0.01;   // Initial uncertainty

    // Process noise (how much we trust the model)
  kalman_filter_.process_noise = Eigen::Matrix2d::Identity() * 0.001;

    // Measurement noise (how much we trust the sensors)
  kalman_filter_.measurement_noise = Eigen::Matrix2d::Identity() * 0.01;

    // State transition matrix (position = position + velocity * dt)
  kalman_filter_.transition_matrix = Eigen::Matrix2d::Identity();

    // Measurement matrix (we observe position directly)
  kalman_filter_.measurement_matrix = Eigen::Matrix2d::Identity();

  kalman_filter_.is_initialized = true;
}

void DualEncoderSystem::initialize_adaptive_weighting()
{
  adaptive_weights_.primary_reliability = 1.0;
  adaptive_weights_.secondary_reliability = 1.0;
  adaptive_weights_.adaptation_rate = 0.01;
  adaptive_weights_.min_weight = 0.1;
  adaptive_weights_.max_weight = 0.9;
  adaptive_weights_.reliability_window_size = 100;
  adaptive_weights_.primary_error_history.clear();
  adaptive_weights_.secondary_error_history.clear();
}

std::unique_ptr<EncoderInterface> DualEncoderSystem::create_encoder_interface(
  const EncoderConfig & config)
{
    // This would create the appropriate encoder interface based on the configuration
    // For now, return a placeholder
  return std::make_unique<GenericEncoderInterface>(config);
}

void DualEncoderSystem::acquisition_worker_thread()
{
  const auto cycle_time = std::chrono::microseconds(
        static_cast<long>(1000000.0 / config_.acquisition_frequency_hz));

  auto next_cycle_time = std::chrono::steady_clock::now();

  while (acquisition_thread_active_) {
    auto cycle_start = std::chrono::steady_clock::now();

        // Acquire data from both encoders
    EncoderData primary_data;
    EncoderData secondary_data;

    bool primary_success = acquire_encoder_data(primary_encoder_, primary_data);
    bool secondary_success = acquire_encoder_data(secondary_encoder_, secondary_data);

        // Update system status based on acquisition results
    update_encoder_health_status(primary_success, secondary_success);

        // Perform sensor fusion if both encoders are healthy
    if (primary_success && secondary_success) {
      perform_sensor_fusion(primary_data, secondary_data);
    } else if (primary_success) {
            // Use primary only
      use_single_encoder_data(primary_data, true);
    } else if (secondary_success) {
            // Use secondary only
      use_single_encoder_data(secondary_data, false);
    } else {
            // Both encoders failed
      handle_total_encoder_failure();
    }

        // Update diagnostics
    update_diagnostics(cycle_start);

        // Sleep until next cycle
    next_cycle_time += cycle_time;
    std::this_thread::sleep_until(next_cycle_time);
  }
}

void DualEncoderSystem::validation_worker_thread()
{
  const auto validation_interval = std::chrono::milliseconds(config_.validation_interval_ms);

  while (validation_thread_active_) {
    std::this_thread::sleep_for(validation_interval);

    if (!validation_thread_active_) {
      break;
    }

    auto validation_start = std::chrono::steady_clock::now();

        // Perform cross-validation
    bool validation_success = perform_cross_validation();

        // Update validation statistics
    auto validation_time = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - validation_start);

    std::lock_guard<std::mutex> lock(diagnostic_mutex_);
    diagnostic_data_.average_validation_time_us =
      (diagnostic_data_.average_validation_time_us + validation_time.count()) / 2.0;

    if (!validation_success) {
      diagnostic_data_.validation_failures++;
    }
  }
}

bool DualEncoderSystem::acquire_encoder_data(
  std::unique_ptr<EncoderInterface> & encoder,
  EncoderData & data)
{
  if (!encoder) {
    return false;
  }

  try {
    data.timestamp = std::chrono::steady_clock::now();
    data.position = encoder->get_position();
    data.velocity = encoder->get_velocity();
    data.raw_counts = encoder->get_raw_counts();
    data.is_valid = encoder->is_data_valid();
    data.quality_metric = encoder->get_signal_quality();

        // Calculate raw position from counts
    data.raw_position = (static_cast<double>(data.raw_counts) /
      encoder->get_counts_per_revolution()) * 2.0 * M_PI;

    return data.is_valid;

  } catch (const std::exception & e) {
    report_error(std::string("Encoder acquisition failed: ") + e.what());
    return false;
  }
}

void DualEncoderSystem::update_encoder_health_status(bool primary_ok, bool secondary_ok)
{
  std::lock_guard<std::mutex> lock(system_mutex_);

  system_status_.primary_encoder_healthy = primary_ok;
  system_status_.secondary_encoder_healthy = secondary_ok;

    // Update system status
  if (primary_ok && secondary_ok) {
    system_status_.status = SystemStatus::DUAL_ENCODER_ACTIVE;
  } else if (primary_ok) {
    system_status_.status = SystemStatus::PRIMARY_ONLY;
  } else if (secondary_ok) {
    system_status_.status = SystemStatus::SECONDARY_ONLY;
  } else {
    system_status_.status = SystemStatus::BOTH_FAILED;
  }
}

void DualEncoderSystem::perform_sensor_fusion(
  const EncoderData & primary,
  const EncoderData & secondary)
{
  auto fusion_start = std::chrono::steady_clock::now();

  FusedPositionData fused_position;
  FusedVelocityData fused_velocity;

  switch (current_fusion_algorithm_) {
    case SensorFusionAlgorithm::SIMPLE_AVERAGE:
      fuse_simple_average(primary, secondary, fused_position, fused_velocity);
      break;

    case SensorFusionAlgorithm::WEIGHTED_AVERAGE:
      fuse_weighted_average(primary, secondary, fused_position, fused_velocity);
      break;

    case SensorFusionAlgorithm::KALMAN_FILTER:
      fuse_kalman_filter(primary, secondary, fused_position, fused_velocity);
      break;

    case SensorFusionAlgorithm::ADAPTIVE_WEIGHTED:
      fuse_adaptive_weighted(primary, secondary, fused_position, fused_velocity);
      break;

    default:
            // Fallback to simple average
      fuse_simple_average(primary, secondary, fused_position, fused_velocity);
      break;
  }

    // Update latest data
  {
    std::lock_guard<std::mutex> lock(data_mutex_);
    latest_primary_data_ = primary;
    latest_secondary_data_ = secondary;
    latest_fused_position_ = fused_position;
    latest_fused_velocity_ = fused_velocity;
    last_primary_update_ = primary.timestamp;
    last_secondary_update_ = secondary.timestamp;
  }

    // Update fusion timing
  auto fusion_time = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - fusion_start);

  std::lock_guard<std::mutex> diag_lock(diagnostic_mutex_);
  diagnostic_data_.average_fusion_time_us =
    (diagnostic_data_.average_fusion_time_us + fusion_time.count()) / 2.0;
}

// Fusion algorithm implementations
void DualEncoderSystem::fuse_simple_average(
  const EncoderData & primary, const EncoderData & secondary,
  FusedPositionData & fused_pos, FusedVelocityData & fused_vel)
{
  fused_pos.position = (primary.position + secondary.position) / 2.0;
  fused_pos.uncertainty = std::abs(primary.position - secondary.position) / 2.0;
  fused_pos.primary_weight = 0.5;
  fused_pos.secondary_weight = 0.5;
  fused_pos.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_pos.is_valid = primary.is_valid && secondary.is_valid;

  fused_vel.velocity = (primary.velocity + secondary.velocity) / 2.0;
  fused_vel.uncertainty = std::abs(primary.velocity - secondary.velocity) / 2.0;
  fused_vel.primary_weight = 0.5;
  fused_vel.secondary_weight = 0.5;
  fused_vel.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_vel.is_valid = primary.is_valid && secondary.is_valid;
}

void DualEncoderSystem::fuse_weighted_average(
  const EncoderData & primary, const EncoderData & secondary,
  FusedPositionData & fused_pos, FusedVelocityData & fused_vel)
{
  double total_weight = fusion_weights_.primary_weight + fusion_weights_.secondary_weight;
  double norm_primary = fusion_weights_.primary_weight / total_weight;
  double norm_secondary = fusion_weights_.secondary_weight / total_weight;

  fused_pos.position = primary.position * norm_primary + secondary.position * norm_secondary;
  fused_pos.uncertainty = std::abs(primary.position - secondary.position) * std::min(norm_primary,
      norm_secondary);
  fused_pos.primary_weight = norm_primary;
  fused_pos.secondary_weight = norm_secondary;
  fused_pos.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_pos.is_valid = primary.is_valid && secondary.is_valid;

  fused_vel.velocity = primary.velocity * norm_primary + secondary.velocity * norm_secondary;
  fused_vel.uncertainty = std::abs(primary.velocity - secondary.velocity) * std::min(norm_primary,
      norm_secondary);
  fused_vel.primary_weight = norm_primary;
  fused_vel.secondary_weight = norm_secondary;
  fused_vel.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_vel.is_valid = primary.is_valid && secondary.is_valid;
}

// =============================================================================
// ADVANCED FUSION ALGORITHMS
// =============================================================================

void DualEncoderSystem::fuse_kalman_filter(
  const EncoderData & primary, const EncoderData & secondary,
  FusedPositionData & fused_pos, FusedVelocityData & fused_vel)
{
  if (!kalman_filter_.is_initialized) {
    initialize_kalman_filter();
  }

    // Calculate time delta for state transition
  static auto last_kalman_update = std::chrono::steady_clock::now();
  auto now = std::chrono::steady_clock::now();
  double dt = std::chrono::duration<double>(now - last_kalman_update).count();
  last_kalman_update = now;

    // Clamp dt to reasonable bounds
  dt = std::max(0.001, std::min(dt, 0.1));

    // Update state transition matrix with current dt
  kalman_filter_.transition_matrix(0, 1) = dt;

    // Prediction step
  Eigen::Vector2d predicted_state = kalman_filter_.transition_matrix * kalman_filter_.state;
  Eigen::Matrix2d predicted_covariance = kalman_filter_.transition_matrix *
    kalman_filter_.covariance *
    kalman_filter_.transition_matrix.transpose() + kalman_filter_.process_noise;

    // Measurement vector [primary_position, secondary_position]
  Eigen::Vector2d measurement;
  measurement << primary.position, secondary.position;

    // Innovation (measurement residual)
  Eigen::Vector2d innovation = measurement - kalman_filter_.measurement_matrix * predicted_state;

    // Innovation covariance
  Eigen::Matrix2d innovation_covariance = kalman_filter_.measurement_matrix * predicted_covariance *
    kalman_filter_.measurement_matrix.transpose() + kalman_filter_.measurement_noise;

    // Kalman gain
  Eigen::Matrix2d kalman_gain = predicted_covariance *
    kalman_filter_.measurement_matrix.transpose() *
    innovation_covariance.inverse();

    // Update step
  kalman_filter_.state = predicted_state + kalman_gain * innovation;
  kalman_filter_.covariance = (Eigen::Matrix2d::Identity() - kalman_gain *
    kalman_filter_.measurement_matrix) * predicted_covariance;

    // Extract results
  fused_pos.position = kalman_filter_.state(0);
  fused_pos.uncertainty = std::sqrt(kalman_filter_.covariance(0, 0));
  fused_pos.primary_weight = 0.5;   // Kalman filter doesn't provide explicit weights
  fused_pos.secondary_weight = 0.5;
  fused_pos.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_pos.is_valid = primary.is_valid && secondary.is_valid;

  fused_vel.velocity = kalman_filter_.state(1);
  fused_vel.uncertainty = std::sqrt(kalman_filter_.covariance(1, 1));
  fused_vel.primary_weight = 0.5;
  fused_vel.secondary_weight = 0.5;
  fused_vel.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_vel.is_valid = primary.is_valid && secondary.is_valid;
}

void DualEncoderSystem::fuse_adaptive_weighted(
  const EncoderData & primary, const EncoderData & secondary,
  FusedPositionData & fused_pos, FusedVelocityData & fused_vel)
{
    // Update reliability metrics based on recent performance
  update_adaptive_weights(primary, secondary);

    // Calculate normalized weights based on reliability
  double total_reliability = adaptive_weights_.primary_reliability +
    adaptive_weights_.secondary_reliability;
  double primary_weight = adaptive_weights_.primary_reliability / total_reliability;
  double secondary_weight = adaptive_weights_.secondary_reliability / total_reliability;

    // Clamp weights to reasonable bounds
  primary_weight = std::max(adaptive_weights_.min_weight,
                             std::min(primary_weight, adaptive_weights_.max_weight));
  secondary_weight = std::max(adaptive_weights_.min_weight,
                               std::min(secondary_weight, adaptive_weights_.max_weight));

    // Renormalize
  double weight_sum = primary_weight + secondary_weight;
  primary_weight /= weight_sum;
  secondary_weight /= weight_sum;

    // Perform weighted fusion
  fused_pos.position = primary.position * primary_weight + secondary.position * secondary_weight;
  fused_pos.uncertainty = std::abs(primary.position - secondary.position) * std::min(primary_weight,
      secondary_weight);
  fused_pos.primary_weight = primary_weight;
  fused_pos.secondary_weight = secondary_weight;
  fused_pos.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_pos.is_valid = primary.is_valid && secondary.is_valid;

  fused_vel.velocity = primary.velocity * primary_weight + secondary.velocity * secondary_weight;
  fused_vel.uncertainty = std::abs(primary.velocity - secondary.velocity) * std::min(primary_weight,
      secondary_weight);
  fused_vel.primary_weight = primary_weight;
  fused_vel.secondary_weight = secondary_weight;
  fused_vel.timestamp = std::max(primary.timestamp, secondary.timestamp);
  fused_vel.is_valid = primary.is_valid && secondary.is_valid;
}

void DualEncoderSystem::update_adaptive_weights(
  const EncoderData & primary,
  const EncoderData & secondary)
{
    // Calculate individual encoder errors (simplified metric based on noise/consistency)
  double primary_error = calculate_encoder_error_metric(primary);
  double secondary_error = calculate_encoder_error_metric(secondary);

    // Add to history
  adaptive_weights_.primary_error_history.push_back(primary_error);
  adaptive_weights_.secondary_error_history.push_back(secondary_error);

    // Maintain window size
  if (adaptive_weights_.primary_error_history.size() > adaptive_weights_.reliability_window_size) {
    adaptive_weights_.primary_error_history.pop_front();
  }
  if (adaptive_weights_.secondary_error_history.size() >
    adaptive_weights_.reliability_window_size)
  {
    adaptive_weights_.secondary_error_history.pop_front();
  }

    // Calculate average errors over window
  double avg_primary_error = std::accumulate(adaptive_weights_.primary_error_history.begin(),
                                              adaptive_weights_.primary_error_history.end(), 0.0) /
    adaptive_weights_.primary_error_history.size();
  double avg_secondary_error = std::accumulate(adaptive_weights_.secondary_error_history.begin(),
                                                adaptive_weights_.secondary_error_history.end(),
      0.0) /
    adaptive_weights_.secondary_error_history.size();

    // Update reliability (lower error = higher reliability)
  double target_primary_reliability = 1.0 / (1.0 + avg_primary_error);
  double target_secondary_reliability = 1.0 / (1.0 + avg_secondary_error);

    // Apply smoothing
  adaptive_weights_.primary_reliability =
    (1.0 - adaptive_weights_.adaptation_rate) * adaptive_weights_.primary_reliability +
    adaptive_weights_.adaptation_rate * target_primary_reliability;

  adaptive_weights_.secondary_reliability =
    (1.0 - adaptive_weights_.adaptation_rate) * adaptive_weights_.secondary_reliability +
    adaptive_weights_.adaptation_rate * target_secondary_reliability;
}

double DualEncoderSystem::calculate_encoder_error_metric(const EncoderData & data)
{
    // Simple error metric based on data quality and consistency
  double error_metric = 0.0;

    // Factor in quality metric (if available)
  if (data.quality_metric >= 0.0 && data.quality_metric <= 1.0) {
    error_metric += (1.0 - data.quality_metric) * 0.5;
  }

    // Factor in data validity
  if (!data.is_valid) {
    error_metric += 1.0;
  }

    // Add small random component to prevent weights from becoming too extreme
  error_metric += 0.01;

  return error_metric;
}

// =============================================================================
// FAULT DETECTION AND HANDLING
// =============================================================================

std::vector<EncoderFault> DualEncoderSystem::detect_individual_encoder_faults(
  const EncoderData & data, const std::string & encoder_name,
  const std::chrono::steady_clock::time_point & current_time)
{
  std::vector<EncoderFault> faults;

    // Check data validity
  if (!data.is_valid) {
    EncoderFault fault;
    fault.encoder_name = encoder_name;
    fault.fault_type = FaultType::DATA_INVALID;
    fault.severity = FaultSeverity::ERROR;
    fault.description = "Encoder data marked as invalid";
    fault.detected_time = current_time;
    fault.is_recoverable = true;
    faults.push_back(fault);
  }

    // Check data freshness
  auto data_age = std::chrono::duration_cast<std::chrono::milliseconds>(current_time -
      data.timestamp);
  if (data_age.count() > config_.max_data_age_ms) {
    EncoderFault fault;
    fault.encoder_name = encoder_name;
    fault.fault_type = FaultType::DATA_TIMEOUT;
    fault.severity = FaultSeverity::WARNING;
    fault.description = "Encoder data is stale (age: " + std::to_string(data_age.count()) + "ms)";
    fault.detected_time = current_time;
    fault.is_recoverable = true;
    faults.push_back(fault);
  }

    // Check signal quality
  if (data.quality_metric >= 0.0 && data.quality_metric < config_.min_signal_quality) {
    EncoderFault fault;
    fault.encoder_name = encoder_name;
    fault.fault_type = FaultType::SIGNAL_QUALITY_LOW;
    fault.severity = FaultSeverity::WARNING;
    fault.description = "Low signal quality: " + std::to_string(data.quality_metric);
    fault.detected_time = current_time;
    fault.is_recoverable = true;
    faults.push_back(fault);
  }

    // Check for unreasonable velocity
  if (std::abs(data.velocity) > config_.max_reasonable_velocity_radians_per_sec) {
    EncoderFault fault;
    fault.encoder_name = encoder_name;
    fault.fault_type = FaultType::UNREASONABLE_VALUE;
    fault.severity = FaultSeverity::ERROR;
    fault.description = "Unreasonable velocity: " + std::to_string(data.velocity) + " rad/s";
    fault.detected_time = current_time;
    fault.is_recoverable = false;
    faults.push_back(fault);
  }

  return faults;
}

void DualEncoderSystem::use_single_encoder_data(const EncoderData & data, bool is_primary)
{
  FusedPositionData fused_position;
  FusedVelocityData fused_velocity;

    // Use single encoder data directly
  fused_position.position = data.position;
  fused_position.uncertainty = config_.single_encoder_uncertainty;
  fused_position.primary_weight = is_primary ? 1.0 : 0.0;
  fused_position.secondary_weight = is_primary ? 0.0 : 1.0;
  fused_position.timestamp = data.timestamp;
  fused_position.is_valid = data.is_valid;

  fused_velocity.velocity = data.velocity;
  fused_velocity.uncertainty = config_.single_encoder_uncertainty;
  fused_velocity.primary_weight = is_primary ? 1.0 : 0.0;
  fused_velocity.secondary_weight = is_primary ? 0.0 : 1.0;
  fused_velocity.timestamp = data.timestamp;
  fused_velocity.is_valid = data.is_valid;

    // Update latest data
  {
    std::lock_guard<std::mutex> lock(data_mutex_);
    if (is_primary) {
      latest_primary_data_ = data;
      last_primary_update_ = data.timestamp;
            // Mark secondary as invalid
      latest_secondary_data_.is_valid = false;
    } else {
      latest_secondary_data_ = data;
      last_secondary_update_ = data.timestamp;
            // Mark primary as invalid
      latest_primary_data_.is_valid = false;
    }
    latest_fused_position_ = fused_position;
    latest_fused_velocity_ = fused_velocity;
  }
}

void DualEncoderSystem::handle_total_encoder_failure()
{
    // Both encoders have failed - this is a critical situation
  std::lock_guard<std::mutex> lock(system_mutex_);

  system_status_.status = SystemStatus::BOTH_FAILED;
  system_status_.primary_encoder_healthy = false;
  system_status_.secondary_encoder_healthy = false;

    // Report critical error
  if (error_handler_) {
    error_handler_->report_error(
            ErrorLevel::CRITICAL,
            "DUAL_ENCODER_TOTAL_FAILURE",
            "Both encoders have failed - position feedback unavailable",
            ErrorType::HARDWARE_FAILURE,
            "dual_encoder_system"
    );
  }

    // Invalidate all fused data
  {
    std::lock_guard<std::mutex> data_lock(data_mutex_);
    latest_fused_position_.is_valid = false;
    latest_fused_velocity_.is_valid = false;
    latest_primary_data_.is_valid = false;
    latest_secondary_data_.is_valid = false;
  }

  log_system_event("CRITICAL: Total encoder failure detected");
}

// =============================================================================
// CALIBRATION AND UTILITY FUNCTIONS
// =============================================================================

bool DualEncoderSystem::calibrate_individual_encoder(
  std::unique_ptr<EncoderInterface> & encoder,
  const std::string & encoder_name)
{
  if (!encoder) {
    report_error("Cannot calibrate " + encoder_name + " encoder - interface not available");
    return false;
  }

  log_system_event("Starting calibration for " + encoder_name + " encoder");

  try {
        // Perform encoder-specific calibration
    bool success = encoder->calibrate();

    if (success) {
      log_system_event(encoder_name + " encoder calibration completed successfully");
    } else {
      report_error(encoder_name + " encoder calibration failed");
    }

    return success;

  } catch (const std::exception & e) {
    std::string error_msg = encoder_name + " encoder calibration exception: " + e.what();
    report_error(error_msg);
    return false;
  }
}

void DualEncoderSystem::update_diagnostics(
  const std::chrono::steady_clock::time_point & cycle_start)
{
  std::lock_guard<std::mutex> lock(diagnostic_mutex_);

  diagnostic_data_.total_acquisition_cycles++;

    // Update position difference statistics
  {
    std::lock_guard<std::mutex> data_lock(data_mutex_);
    if (latest_primary_data_.is_valid && latest_secondary_data_.is_valid) {
      double pos_diff = std::abs(latest_primary_data_.position - latest_secondary_data_.position);
      double vel_diff = std::abs(latest_primary_data_.velocity - latest_secondary_data_.velocity);

      diagnostic_data_.max_position_difference = std::max(diagnostic_data_.max_position_difference,
          pos_diff);
      diagnostic_data_.max_velocity_difference = std::max(diagnostic_data_.max_velocity_difference,
          vel_diff);
    }
  }

    // Count encoder errors
  if (!latest_primary_data_.is_valid) {
    diagnostic_data_.primary_encoder_errors++;
  }
  if (!latest_secondary_data_.is_valid) {
    diagnostic_data_.secondary_encoder_errors++;
  }
}

void DualEncoderSystem::report_error(const std::string & message)
{
  if (error_handler_) {
    error_handler_->report_error(
            ErrorLevel::ERROR,
            "DUAL_ENCODER_ERROR",
            message,
            ErrorType::SYSTEM_ERROR,
            "dual_encoder_system"
    );
  }

    // Also log to system event log
  log_system_event("ERROR: " + message);
}

void DualEncoderSystem::log_system_event(const std::string & message)
{
    // This would typically log to a system logger
    // For now, we'll use a simple timestamp + message format
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
// ENCODER INTERFACE IMPLEMENTATIONS
// =============================================================================

// Generic Encoder Interface Implementation (placeholder)
class GenericEncoderInterface : public EncoderInterface {
private:
  EncoderConfig config_;
  bool is_initialized_;
  double current_position_;
  double current_velocity_;
  int64_t current_counts_;
  std::chrono::steady_clock::time_point last_update_;

public:
  explicit GenericEncoderInterface(const EncoderConfig & config)
  : config_(config), is_initialized_(false), current_position_(0.0),
    current_velocity_(0.0), current_counts_(0), last_update_(std::chrono::steady_clock::now()) {}

  bool initialize() override
  {
        // Simulate initialization
    is_initialized_ = true;
    current_position_ = 0.0;
    current_velocity_ = 0.0;
    current_counts_ = 0;
    last_update_ = std::chrono::steady_clock::now();
    return true;
  }

  void shutdown() override
  {
    is_initialized_ = false;
  }

  double get_position() override
  {
    if (!is_initialized_) {return 0.0;}

        // Simulate encoder position with some noise
    auto now = std::chrono::steady_clock::now();
    auto dt = std::chrono::duration<double>(now - last_update_).count();

        // Simple integration for simulation
    current_position_ += current_velocity_ * dt;
    last_update_ = now;

        // Add small amount of noise
    double noise = (static_cast<double>(rand()) / RAND_MAX - 0.5) * 0.001;
    return current_position_ + noise;
  }

  double get_velocity() override
  {
    if (!is_initialized_) {return 0.0;}

        // Simulate slowly varying velocity
    static double target_velocity = 0.0;
    static auto last_target_update = std::chrono::steady_clock::now();

    auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration<double>(now - last_target_update).count() > 1.0) {
      target_velocity = (static_cast<double>(rand()) / RAND_MAX - 0.5) * 2.0;       // -1 to 1 rad/s
      last_target_update = now;
    }

        // Smooth approach to target
    current_velocity_ = current_velocity_ * 0.99 + target_velocity * 0.01;

        // Add small amount of noise
    double noise = (static_cast<double>(rand()) / RAND_MAX - 0.5) * 0.01;
    return current_velocity_ + noise;
  }

  int64_t get_raw_counts() override
  {
    if (!is_initialized_) {return 0;}

        // Convert position to counts
    double revolutions = current_position_ / (2.0 * M_PI);
    current_counts_ = static_cast<int64_t>(revolutions * get_counts_per_revolution());
    return current_counts_;
  }

  bool is_data_valid() override
  {
        // Simulate occasional data validity issues
    return is_initialized_ && (rand() % 1000) != 0;     // 99.9% validity
  }

  double get_signal_quality() override
  {
    if (!is_initialized_) {return 0.0;}

        // Simulate signal quality with some variation
    static double base_quality = 0.95;
    double variation = (static_cast<double>(rand()) / RAND_MAX - 0.5) * 0.1;
    return std::max(0.0, std::min(1.0, base_quality + variation));
  }

  int32_t get_counts_per_revolution() override
  {
    return config_.counts_per_revolution;
  }

  bool calibrate() override
  {
    if (!is_initialized_) {return false;}

        // Simulate calibration process
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

        // Reset position
    current_position_ = 0.0;
    current_counts_ = 0;

    return true;     // Assume calibration always succeeds for simulation
  }
};

// Factory method implementation - now moved to bottom of file
std::unique_ptr<EncoderInterface> DualEncoderSystem::create_encoder_interface(
  const EncoderConfig & config)
{
    // In a real implementation, this would create different encoder interfaces
    // based on the encoder type specified in the configuration
  return std::make_unique<GenericEncoderInterface>(config);
}

} // namespace motor_control_ros2
