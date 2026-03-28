/*
 * Dual Encoder Support System for Enhanced Motor Control
 *
 * This system provides:
 * 1. Primary and secondary encoder redundancy
 * 2. Real-time cross-validation between encoders
 * 3. Enhanced precision through sensor fusion
 * 4. Automatic fault detection and isolation
 * 5. Seamless fallback to single encoder operation
 * 6. Advanced calibration and alignment procedures
 */

#pragma once

#include "motor_abstraction.hpp"
#include "comprehensive_error_handler.hpp"
#include <memory>
#include <array>
#include <deque>
#include <chrono>
#include <mutex>
#include <atomic>

namespace motor_control_ros2
{

// =============================================================================
// DUAL ENCODER TYPES AND CONFIGURATION
// =============================================================================

/**
 * @brief Encoder types supported by the system
 */
enum class EncoderType : uint8_t
{
  INCREMENTAL = 0,           // Standard incremental encoder
  ABSOLUTE_SINGLE_TURN = 1,  // Single-turn absolute encoder
  ABSOLUTE_MULTI_TURN = 2,   // Multi-turn absolute encoder
  MAGNETIC = 3,              // Magnetic encoder (hall effect)
  OPTICAL = 4,               // Optical encoder
  CAPACITIVE = 5             // Capacitive encoder
};

/**
 * @brief Encoder interface type
 */
enum class EncoderInterfaceType : uint8_t
{
  QUADRATURE_AB = 0,        // Standard A/B quadrature
  QUADRATURE_ABI = 1,       // A/B/Index quadrature
  SPI = 2,                  // SPI absolute encoder
  SSI = 3,                  // SSI (Synchronous Serial Interface)
  BiSS = 4,                 // BiSS (Bidirectional Serial Synchronous)
  ENDAT = 5,                // EnDat protocol
  CAN = 6,                  // CAN bus encoder
  ANALOG = 7                // Analog encoder (sin/cos)
};

/**
 * @brief Individual encoder configuration
 */
struct EncoderConfig
{
  std::string name = "encoder";
  EncoderType type = EncoderType::INCREMENTAL;
  EncoderInterfaceType interface = EncoderInterfaceType::QUADRATURE_ABI;

  // Physical properties
  uint32_t counts_per_revolution = 8192;
  double mechanical_gear_ratio = 1.0;
  bool invert_direction = false;

  // Resolution and accuracy
  double resolution_radians = 0.0001;
  double accuracy_radians = 0.001;
  double repeatability_radians = 0.0005;

  // Communication parameters
  uint32_t communication_frequency_hz = 1000;
  uint32_t timeout_ms = 100;

  // Calibration
  double offset_radians = 0.0;
  double scale_factor = 1.0;
  bool requires_calibration = true;

  // Error detection
  double max_velocity_rps = 100.0;  // Max revolutions per second
  double max_acceleration_rps2 = 1000.0; // Max accel in rev/s²
  uint32_t error_count_threshold = 10;
};

/**
 * @brief Dual encoder system configuration
 */
struct DualEncoderConfig
{
  EncoderConfig primary_encoder;
  EncoderConfig secondary_encoder;

  // Cross-validation settings
  double position_tolerance_radians = 0.002; // Max allowable difference
  double velocity_tolerance_rps = 0.1;       // Max velocity difference
  uint32_t validation_window_samples = 10;   // Samples for validation

  // Fusion settings
  bool enable_sensor_fusion = true;
  double fusion_weight_primary = 0.7;        // Primary encoder weight (0-1)
  uint32_t fusion_filter_samples = 5;        // Samples for fusion filter

  // Fault detection
  uint32_t max_consecutive_failures = 5;
  std::chrono::milliseconds fault_detection_period = std::chrono::milliseconds(100);
  bool enable_automatic_fallback = true;

  // Calibration
  bool auto_align_encoders = true;
  double alignment_tolerance = 0.001;        // Radians
  uint32_t alignment_samples = 100;
};

/**
 * @brief Real-time encoder data
 */
struct EncoderData
{
  // Position information
  double position_radians = 0.0;
  double position_counts = 0;
  uint32_t raw_counts = 0;

  // Velocity information
  double velocity_rps = 0.0;  // Radians per second
  double velocity_filtered_rps = 0.0;

  // Acceleration
  double acceleration_rps2 = 0.0;

  // Quality metrics
  bool data_valid = false;
  double signal_strength = 1.0;  // 0.0 to 1.0
  uint32_t error_count = 0;

  // Timing
  std::chrono::steady_clock::time_point timestamp;
  std::chrono::microseconds update_period = std::chrono::microseconds(1000);

  EncoderData()
  {
    timestamp = std::chrono::steady_clock::now();
  }
};

// =============================================================================
// DUAL ENCODER SYSTEM
// =============================================================================

/**
 * @brief Comprehensive dual encoder system with redundancy
 */
class DualEncoderSystem
{
public:
  /**
   * @brief System status enumeration
   */
  enum class SystemStatus : uint8_t
  {
    NOT_INITIALIZED = 0,
    DUAL_ENCODER_ACTIVE = 1,    // Both encoders working
    PRIMARY_ONLY = 2,           // Only primary encoder working
    SECONDARY_ONLY = 3,         // Only secondary encoder working
    SENSOR_FUSION_ACTIVE = 4,   // Fusion mode active
    CALIBRATION_REQUIRED = 5,   // System needs calibration
    FAULT_DETECTED = 6,         // Fault in system
    SYSTEM_FAILED = 7           // Complete system failure
  };

  /**
   * @brief Comprehensive system status
   */
  struct SystemStatusInfo
  {
    SystemStatus status = SystemStatus::NOT_INITIALIZED;

    // Encoder states
    bool primary_encoder_active = false;
    bool secondary_encoder_active = false;
    bool encoders_aligned = false;

    // Data quality
    double position_agreement = 1.0;      // 0.0 = complete disagreement, 1.0 = perfect
    double velocity_agreement = 1.0;
    double overall_confidence = 1.0;      // Overall system confidence

    // Performance metrics
    uint64_t total_updates = 0;
    uint64_t validation_failures = 0;
    uint64_t fallback_events = 0;
    double average_update_rate_hz = 0.0;

    // Current readings
    EncoderData primary_data;
    EncoderData secondary_data;
    EncoderData fused_data;

    // Error information
    std::vector<MotorError> active_errors;
    std::chrono::steady_clock::time_point last_update;

    SystemStatusInfo()
    {
      last_update = std::chrono::steady_clock::now();
    }
  };

public:
  DualEncoderSystem();
  ~DualEncoderSystem();

  // =============================================================================
  // SYSTEM INITIALIZATION AND CONFIGURATION
  // =============================================================================

  /**
   * @brief Initialize dual encoder system
   */
  bool initialize(
    const DualEncoderConfig & config,
    std::shared_ptr<ComprehensiveErrorHandler> error_handler = nullptr);

  /**
   * @brief Start encoder data acquisition
   */
  bool start_acquisition();

  /**
   * @brief Stop encoder data acquisition
   */
  bool stop_acquisition();

  /**
   * @brief Check if system is initialized
   */
  bool is_initialized() const;

  /**
   * @brief Update system configuration
   */
  bool update_config(const DualEncoderConfig & new_config);

  // =============================================================================
  // DATA ACQUISITION
  // =============================================================================

  /**
   * @brief Get current fused encoder data (best available)
   */
  EncoderData get_position_data();

  /**
   * @brief Get primary encoder data
   */
  EncoderData get_primary_encoder_data();

  /**
   * @brief Get secondary encoder data
   */
  EncoderData get_secondary_encoder_data();

  /**
   * @brief Get system status information
   */
  SystemStatusInfo get_system_status();

  /**
   * @brief Check if position data is reliable
   */
  bool is_position_reliable(double confidence_threshold = 0.8);

  // =============================================================================
  // CALIBRATION AND ALIGNMENT
  // =============================================================================

  /**
   * @brief Perform encoder alignment calibration
   */
  bool calibrate_encoder_alignment();

  /**
   * @brief Set reference position for both encoders
   */
  bool set_reference_position(double reference_position_radians);

  /**
   * @brief Auto-detect and correct encoder offset
   */
  bool auto_correct_offset();

  /**
   * @brief Validate encoder calibration
   */
  bool validate_calibration();

  // =============================================================================
  // FAULT DETECTION AND RECOVERY
  // =============================================================================

  /**
   * @brief Perform cross-validation check
   */
  bool perform_cross_validation();

  /**
   * @brief Detect encoder faults
   */
  std::vector<MotorError> detect_encoder_faults();

  /**
   * @brief Force fallback to single encoder
   */
  bool force_fallback_mode(bool use_primary = true);

  /**
   * @brief Attempt to restore dual encoder operation
   */
  bool attempt_dual_encoder_restore();

  /**
   * @brief Reset fault conditions
   */
  void reset_fault_conditions();

  // =============================================================================
  // ADVANCED FEATURES
  // =============================================================================

  /**
   * @brief Enable/disable sensor fusion
   */
  bool set_sensor_fusion_enabled(bool enabled);

  /**
   * @brief Adjust fusion weights dynamically
   */
  bool adjust_fusion_weights(double primary_weight, double secondary_weight);

  /**
   * @brief Get encoder health metrics
   */
  std::pair<double, double> get_encoder_health(); // primary, secondary health (0-1)

  /**
   * @brief Perform encoder diagnostics
   */
  std::string generate_diagnostic_report();

  /**
   * @brief Register data update callback
   */
  void register_data_callback(std::function<void(const EncoderData &)> callback);

private:
  DualEncoderConfig config_;
  SystemStatusInfo status_info_;

  std::shared_ptr<ComprehensiveErrorHandler> error_handler_;

  // Threading and synchronization
  std::atomic<bool> system_running_;
  std::thread acquisition_thread_;
  mutable std::mutex data_mutex_;

  // Data storage
  std::array<std::deque<EncoderData>, 2> encoder_history_; // [primary, secondary]
  EncoderData current_fused_data_;

  // Calibration data
  double encoder_offset_difference_;
  bool encoders_aligned_;
  std::chrono::steady_clock::time_point last_calibration_time_;

  // Fault detection
  std::atomic<uint32_t> consecutive_validation_failures_;
  std::atomic<bool> primary_encoder_fault_;
  std::atomic<bool> secondary_encoder_fault_;

  // Performance monitoring
  std::deque<std::chrono::steady_clock::time_point> update_timestamps_;
  uint64_t total_update_count_;

  // Callbacks
  std::vector<std::function<void(const EncoderData &)>> data_callbacks_;

  // Internal methods
  void acquisition_thread_function();
  bool read_encoder_data(uint8_t encoder_index, EncoderData & data);
  EncoderData perform_sensor_fusion(const EncoderData & primary, const EncoderData & secondary);
  bool validate_encoder_data(const EncoderData & data, const EncoderConfig & config);
  bool cross_validate_encoders(const EncoderData & primary, const EncoderData & secondary);
  void update_performance_metrics();
  void notify_data_callbacks(const EncoderData & data);
  double calculate_agreement_metric(double primary_value, double secondary_value, double tolerance);
  void handle_encoder_fault(uint8_t encoder_index, MotorErrorCode error_code);
};

// =============================================================================
// SENSOR FUSION ALGORITHMS
// =============================================================================

/**
 * @brief Advanced sensor fusion algorithms for dual encoders
 */
class EncoderSensorFusion
{
public:
  /**
   * @brief Fusion algorithm types
   */
  enum class FusionAlgorithm : uint8_t
  {
    WEIGHTED_AVERAGE = 0,     // Simple weighted average
    KALMAN_FILTER = 1,        // Kalman filter fusion
    COMPLEMENTARY_FILTER = 2, // Complementary filter
    ADAPTIVE_WEIGHT = 3,      // Adaptive weighting based on quality
    MEDIAN_FILTER = 4         // Median-based robust fusion
  };

  /**
   * @brief Fusion configuration
   */
  struct FusionConfig
  {
    FusionAlgorithm algorithm = FusionAlgorithm::ADAPTIVE_WEIGHT;
    uint32_t filter_window_size = 5;
    double noise_covariance_primary = 0.001;
    double noise_covariance_secondary = 0.001;
    double process_noise = 0.0001;
    double adaptation_rate = 0.1;
  };

public:
  EncoderSensorFusion(const FusionConfig & config = FusionConfig());

  /**
   * @brief Perform sensor fusion
   */
  EncoderData fuse_encoder_data(const EncoderData & primary, const EncoderData & secondary);

  /**
   * @brief Update fusion parameters
   */
  void update_config(const FusionConfig & config);

  /**
   * @brief Reset fusion filter state
   */
  void reset_filter_state();

  /**
   * @brief Get fusion performance metrics
   */
  double get_fusion_accuracy() const;

private:
  FusionConfig config_;

  // Kalman filter state
  std::array<double, 4> kalman_state_;      // [position, velocity, pos_var, vel_var]
  std::array<std::array<double, 2>, 2> kalman_covariance_;

  // Filter history
  std::deque<EncoderData> fusion_history_;

  // Internal fusion methods
  EncoderData weighted_average_fusion(const EncoderData & primary, const EncoderData & secondary);
  EncoderData kalman_filter_fusion(const EncoderData & primary, const EncoderData & secondary);
  EncoderData adaptive_weight_fusion(const EncoderData & primary, const EncoderData & secondary);

  // Helper methods
  double calculate_encoder_quality_score(const EncoderData & data);
  void update_adaptive_weights(double primary_quality, double secondary_quality);
};

// =============================================================================
// ENCODER INTERFACE IMPLEMENTATIONS
// =============================================================================

/**
 * @brief Base encoder interface
 */
class EncoderInterface
{
public:
  virtual ~EncoderInterface() = default;

  virtual bool initialize(const EncoderConfig & config) = 0;
  virtual bool read_position(EncoderData & data) = 0;
  virtual bool is_connected() const = 0;
  virtual std::string get_status() const = 0;
  virtual bool perform_self_test() = 0;
};

/**
 * @brief Factory for encoder interfaces
 */
class EncoderInterfaceFactory
{
public:
  static std::unique_ptr<EncoderInterface> create_encoder_interface(
    const EncoderConfig & config);

  static std::vector<std::string> get_supported_interfaces();

  static bool validate_encoder_config(
    const EncoderConfig & config,
    std::string & validation_message);
};

} // namespace motor_control_ros2
