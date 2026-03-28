/*
 * Enhanced Motor Controller Abstraction Layer
 *
 * This file provides comprehensive improvements to the motor abstraction layer
 * addressing the critical enhancement points:
 * 1. Complete CAN bus abstraction for any motor type
 * 2. Proper error handling with recovery mechanisms
 * 3. Initialization without limit switches using absolute encoders
 * 4. Dual encoder support for enhanced precision
 * 5. Advanced motor tuning capabilities (PID, feedforward)
 * 6. Finalized parameters with validation
 */

#pragma once

#include "motor_abstraction.hpp"
#include <chrono>
#include <functional>
#include <deque>
#include <atomic>
#include <thread>

namespace motor_control_ros2
{

// =============================================================================
// 1. ENHANCED CAN BUS ABSTRACTION
// =============================================================================

/**
 * @brief Enhanced CAN message structure for protocol independence
 */
struct CANMessage
{
  uint32_t id;
  std::vector<uint8_t> data;
  uint8_t dlc;
  bool extended_frame;
  bool remote_frame;
  std::chrono::steady_clock::time_point timestamp;

  CANMessage()
  : id(0), dlc(0), extended_frame(false), remote_frame(false) {}
};

/**
 * @brief CAN protocol types supported by the abstraction layer
 */
enum class CANProtocol
{
  CUSTOM = 0,        // ODrive-style custom protocol
  CANOPEN = 1,       // Standard CANopen (MG6010, MG4040, etc.)
  J1939 = 2,         // SAE J1939 protocol
  CANFD = 3,         // CAN FD protocol
  PROPRIETARY = 4    // Vendor-specific protocols
};

/**
 * @brief Enhanced CAN interface with protocol abstraction
 */
class EnhancedCANInterface : public CANInterface
{
public:
  virtual ~EnhancedCANInterface() = default;

  // Original interface methods
  bool initialize(const std::string & interface_name, uint32_t baud_rate = 1000000) override = 0;
  bool send_message(uint32_t id, const std::vector<uint8_t> & data) override = 0;
  bool receive_message(
    uint32_t & id, std::vector<uint8_t> & data,
    int timeout_ms = 10) override = 0;
  bool configure_node(uint8_t node_id, uint32_t baud_rate = 0) override = 0;
  bool is_connected() const override = 0;
  std::string get_last_error() const override = 0;

  // Enhanced protocol-aware methods
  virtual bool send_message(const CANMessage & message) = 0;
  virtual bool receive_message(CANMessage & message, int timeout_ms = 10) = 0;
  virtual bool set_protocol(CANProtocol protocol) = 0;
  virtual CANProtocol get_protocol() const = 0;
  virtual bool set_filters(
    const std::vector<uint32_t> & accept_ids,
    const std::vector<uint32_t> & reject_ids = {}) = 0;
  virtual bool enable_timestamping(bool enable) = 0;
  virtual bool set_loopback(bool enable) = 0;
  virtual uint32_t get_error_count() const = 0;
  virtual void clear_error_count() = 0;
  virtual bool perform_bus_recovery() = 0;

  // Statistics and monitoring
  virtual uint64_t get_tx_count() const = 0;
  virtual uint64_t get_rx_count() const = 0;
  virtual double get_bus_load_percent() const = 0;
};

// =============================================================================
// 2. COMPREHENSIVE ERROR HANDLING FRAMEWORK
// =============================================================================

/**
 * @brief Motor error codes with comprehensive coverage
 */
enum class MotorErrorCode : uint32_t
{
  // General errors
  NO_ERROR = 0x0000,
  GENERIC_ERROR = 0x0001,

  // Communication errors (0x1000 series)
  CAN_TIMEOUT = 0x1001,
  CAN_BUS_OFF = 0x1002,
  CAN_ERROR_PASSIVE = 0x1003,
  CAN_ERROR_ACTIVE = 0x1004,
  NODE_NOT_RESPONDING = 0x1005,
  PROTOCOL_ERROR = 0x1006,
  MESSAGE_LOST = 0x1007,

  // Motor hardware errors (0x2000 series)
  MOTOR_OVERCURRENT = 0x2001,
  MOTOR_OVERVOLTAGE = 0x2002,
  MOTOR_UNDERVOLTAGE = 0x2003,
  MOTOR_OVERTEMPERATURE = 0x2004,
  MOTOR_PHASE_OPEN = 0x2005,
  MOTOR_PHASE_SHORT = 0x2006,
  MOTOR_STALL = 0x2007,

  // Encoder errors (0x3000 series)
  ENCODER_ERROR = 0x3001,
  ENCODER_NOT_READY = 0x3002,
  ENCODER_COUNT_ERROR = 0x3003,
  ENCODER_COMMUNICATION_ERROR = 0x3004,
  DUAL_ENCODER_MISMATCH = 0x3005,
  ENCODER_CALIBRATION_FAILED = 0x3006,

  // Control errors (0x4000 series)
  POSITION_LIMIT_EXCEEDED = 0x4001,
  VELOCITY_LIMIT_EXCEEDED = 0x4002,
  ACCELERATION_LIMIT_EXCEEDED = 0x4003,
  FOLLOWING_ERROR_TOO_LARGE = 0x4004,
  CONTROL_LOOP_TIMEOUT = 0x4005,
  PID_SATURATION = 0x4006,

  // Safety errors (0x5000 series)
  EMERGENCY_STOP_ACTIVE = 0x5001,
  SAFETY_CIRCUIT_OPEN = 0x5002,
  WATCHDOG_TIMEOUT = 0x5003,
  SAFE_TORQUE_OFF = 0x5004,

  // Initialization errors (0x6000 series)
  NOT_INITIALIZED = 0x6001,
  INITIALIZATION_FAILED = 0x6002,
  HOMING_FAILED = 0x6003,
  CALIBRATION_REQUIRED = 0x6004,
  PARAMETER_ERROR = 0x6005
};

/**
 * @brief Error severity levels
 */
enum class ErrorSeverity
{
  INFO = 0,
  WARNING = 1,
  ERROR = 2,
  CRITICAL = 3,
  FATAL = 4
};

/**
 * @brief Motor error with detailed information
 */
struct MotorError
{
  MotorErrorCode code;
  ErrorSeverity severity;
  std::string description;
  std::chrono::steady_clock::time_point timestamp;
  std::string recovery_suggestion;
  bool auto_recoverable;
  uint32_t occurrence_count;

  MotorError()
  : code(MotorErrorCode::NO_ERROR), severity(ErrorSeverity::INFO),
    occurrence_count(0), auto_recoverable(false)
  {
    timestamp = std::chrono::steady_clock::now();
  }
};

/**
 * @brief Error handler interface for recovery mechanisms
 */
class MotorErrorHandler
{
public:
  virtual ~MotorErrorHandler() = default;

  virtual bool handle_error(const MotorError & error) = 0;
  virtual bool attempt_recovery(MotorErrorCode error_code) = 0;
  virtual std::vector<MotorError> get_error_history() const = 0;
  virtual void clear_errors() = 0;
  virtual bool is_error_critical(MotorErrorCode error_code) const = 0;
};

// =============================================================================
// 3. DUAL ENCODER SUPPORT
// =============================================================================

/**
 * @brief Dual encoder configuration and data
 */
struct DualEncoderData
{
  // Motor encoder (high resolution, motor side)
  struct MotorEncoder
  {
    double position_raw;      // Raw position in encoder counts
    double position_filtered; // Filtered position
    double velocity;         // Velocity estimate
    uint64_t count_per_rev;  // Encoder resolution
    bool valid;              // Data validity
    double signal_strength;  // Signal quality (0.0-1.0)
    std::chrono::steady_clock::time_point last_update;
  } motor;

  // Output encoder (absolute, output side)
  struct OutputEncoder
  {
    double position_raw;     // Raw position in encoder counts
    double position_filtered; // Filtered position
    double velocity;         // Velocity estimate
    uint64_t count_per_rev;  // Encoder resolution
    bool valid;              // Data validity
    bool absolute;           // True if absolute encoder
    double signal_strength;  // Signal quality (0.0-1.0)
    std::chrono::steady_clock::time_point last_update;
  } output;

  // Computed values from dual encoder fusion
  double fused_position;     // Best position estimate
  double fused_velocity;     // Best velocity estimate
  double position_error;     // Difference between encoders
  double gear_ratio;         // Computed gear ratio
  bool encoders_aligned;     // True if encoders are properly aligned
  double confidence_level;   // Fusion confidence (0.0-1.0)
};

/**
 * @brief Dual encoder manager for fusion algorithms
 */
class DualEncoderManager
{
public:
  virtual ~DualEncoderManager() = default;

  virtual bool initialize(const MotorConfiguration & config) = 0;
  virtual bool update_encoder_data(const DualEncoderData & data) = 0;
  virtual DualEncoderData get_fused_data() const = 0;
  virtual bool calibrate_encoders() = 0;
  virtual bool is_calibrated() const = 0;
  virtual double get_position_accuracy() const = 0;
  virtual bool detect_encoder_failure() = 0;
};

// =============================================================================
// 4. ADVANCED MOTOR TUNING CAPABILITIES
// =============================================================================

/**
 * @brief PID controller parameters with advanced features
 */
struct AdvancedPIDConfig
{
  // Basic PID gains
  double kp;              // Proportional gain
  double ki;              // Integral gain
  double kd;              // Derivative gain

  // Advanced PID features
  double integral_limit;   // Integral windup limit
  double derivative_filter; // Derivative filter time constant
  double output_limit_pos; // Positive output limit
  double output_limit_neg; // Negative output limit
  bool anti_windup_enabled; // Anti-windup compensation

  // Feedforward terms
  double kff_velocity;     // Velocity feedforward
  double kff_acceleration; // Acceleration feedforward
  double kff_friction;     // Friction compensation

  // Adaptive parameters
  bool adaptive_enabled;   // Enable adaptive tuning
  double adaptation_rate;  // Rate of parameter adaptation
  double performance_threshold; // Performance threshold for adaptation
};

/**
 * @brief Motor tuning interface with advanced algorithms
 */
class MotorTuner
{
public:
  virtual ~MotorTuner() = default;

  // Automatic tuning methods
  virtual bool auto_tune_position_loop(double test_amplitude = 0.1) = 0;
  virtual bool auto_tune_velocity_loop(double test_velocity = 1.0) = 0;
  virtual bool auto_tune_current_loop() = 0;

  // Manual tuning support
  virtual bool set_pid_config(const AdvancedPIDConfig & config) = 0;
  virtual AdvancedPIDConfig get_pid_config() const = 0;
  virtual bool validate_tuning_parameters(const AdvancedPIDConfig & config) = 0;

  // Performance analysis
  virtual double measure_step_response_time() = 0;
  virtual double measure_steady_state_error() = 0;
  virtual double measure_overshoot_percent() = 0;
  virtual bool analyze_stability() = 0;

  // Adaptive control
  virtual bool enable_adaptive_control(bool enable) = 0;
  virtual bool is_adaptive_control_active() const = 0;
  virtual void reset_adaptive_parameters() = 0;
};

// =============================================================================
// 5. ENHANCED MOTOR STATUS WITH COMPREHENSIVE MONITORING
// =============================================================================

/**
 * @brief Enhanced motor status with detailed information
 */
struct EnhancedMotorStatus : public MotorStatus
{
  // Additional status information
  DualEncoderData encoder_status;
  std::vector<MotorError> active_errors;
  std::vector<MotorError> warning_list;

  // Performance metrics
  double position_accuracy;        // Current position accuracy (mm or deg)
  double velocity_accuracy;        // Current velocity accuracy
  double control_loop_frequency;   // Actual control loop rate (Hz)
  double cpu_usage_percent;        // Motor controller CPU usage

  // Thermal status
  double motor_temperature;        // Motor winding temperature (°C)
  double driver_temperature;       // Driver/controller temperature (°C)
  double ambient_temperature;      // Ambient temperature (°C)

  // Power status
  double bus_voltage_actual;       // Actual bus voltage (V)
  double current_rms;             // RMS current consumption (A)
  double power_consumption;        // Power consumption (W)

  // Mechanical status
  double vibration_level;         // Vibration magnitude
  double load_estimate;           // Estimated mechanical load (%)
  bool mechanical_brake_active;   // Brake status if available

  // Communication status
  uint32_t can_tx_errors;         // CAN transmission errors
  uint32_t can_rx_errors;         // CAN reception errors
  double communication_quality;   // Link quality (0.0-1.0)

  // Timing information
  std::chrono::steady_clock::time_point last_command_time;
  std::chrono::steady_clock::time_point last_feedback_time;
  double max_response_time_ms;    // Maximum response time observed
};

// =============================================================================
// 6. FINALIZED MOTOR CONFIGURATION WITH VALIDATION
// =============================================================================

/**
 * @brief Complete motor configuration with validation
 */
struct FinalizedMotorConfiguration : public MotorConfiguration
{
  // Dual encoder configuration
  struct EncoderConfig
  {
    bool use_dual_encoders = true;
    uint32_t motor_encoder_resolution = 16384;    // Motor encoder CPR
    uint32_t output_encoder_resolution = 4096;    // Output encoder CPR
    bool output_encoder_absolute = true;          // Absolute vs incremental
    double encoder_fusion_weight = 0.7;           // Motor encoder weight in fusion
    double max_encoder_error = 0.01;              // Max allowable encoder error (rad)
  } encoder_config;

  // Advanced control parameters
  AdvancedPIDConfig position_pid;
  AdvancedPIDConfig velocity_pid;
  AdvancedPIDConfig current_pid;

  // Safety configuration
  struct SafetyConfig
  {
    double emergency_stop_deceleration = 50.0;   // Emergency stop decel (rad/s²)
    double watchdog_timeout_ms = 1000.0;         // Watchdog timeout
    bool enable_safe_torque_off = true;          // Hardware STO support
    double safe_operating_temperature = 70.0;    // Safe temp limit (°C)
    double critical_temperature = 85.0;          // Critical temp limit (°C)
    bool enable_predictive_safety = true;        // Predictive safety features
  } safety_config;

  // Performance requirements
  struct PerformanceConfig
  {
    double target_position_accuracy = 0.001;     // Target accuracy (rad)
    double target_velocity_accuracy = 0.01;      // Target vel accuracy (rad/s)
    double max_following_error = 0.05;           // Max following error (rad)
    double control_loop_frequency = 1000.0;      // Control frequency (Hz)
    double communication_timeout_ms = 100.0;     // Comm timeout
  } performance_config;

  // Motor-specific parameters (enhanced)
  struct MotorSpecificConfig
  {
    std::string motor_model;                     // e.g., "MG6010-48V"
    std::string firmware_version;               // Required firmware version
    CANProtocol can_protocol = CANProtocol::CANOPEN;
    uint32_t can_baudrate = 1000000;
    bool supports_absolute_encoder = true;
    bool supports_dual_encoder = true;
    bool supports_torque_control = true;
    double rated_torque = 1.3;                  // Rated torque (Nm)
    double peak_torque = 3.9;                   // Peak torque (Nm)
    double rated_speed = 3000.0;                // Rated speed (RPM)
  } motor_specific;
};

/**
 * @brief Configuration validator with comprehensive checks
 */
class ConfigurationValidator
{
public:
  struct ValidationResult
  {
    bool is_valid = false;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
    std::vector<std::string> suggestions;
  };

  static ValidationResult validate_configuration(const FinalizedMotorConfiguration & config);
  static bool apply_default_parameters(
    FinalizedMotorConfiguration & config,
    const std::string & motor_type);
  static bool validate_parameter_ranges(const FinalizedMotorConfiguration & config);
  static bool check_hardware_compatibility(const FinalizedMotorConfiguration & config);
};

// =============================================================================
// 7. ENHANCED MOTOR CONTROLLER INTERFACE
// =============================================================================

/**
 * @brief Enhanced motor controller interface with all improvements
 */
class EnhancedMotorControllerInterface : public MotorControllerInterface
{
public:
  virtual ~EnhancedMotorControllerInterface() = default;

  // Enhanced initialization with comprehensive configuration
  virtual bool initialize(
    const FinalizedMotorConfiguration & config,
    std::shared_ptr<EnhancedCANInterface> can_interface) = 0;

  // Dual encoder support
  virtual bool enable_dual_encoders(bool enable) = 0;
  virtual DualEncoderData get_dual_encoder_data() const = 0;
  virtual bool calibrate_dual_encoders() = 0;

  // Advanced control methods
  virtual bool set_position_with_profile(
    double position, double max_velocity,
    double max_acceleration) = 0;
  virtual bool set_velocity_with_acceleration_limit(double velocity, double max_acceleration) = 0;
  virtual bool set_torque_with_limits(double torque, double max_rate_of_change) = 0;

  // Enhanced status and monitoring
  virtual EnhancedMotorStatus get_enhanced_status() = 0;
  virtual bool start_continuous_monitoring(double update_rate_hz) = 0;
  virtual bool stop_continuous_monitoring() = 0;

  // Motor tuning interface
  virtual std::shared_ptr<MotorTuner> get_tuner() = 0;
  virtual bool apply_tuning_configuration(const AdvancedPIDConfig & config) = 0;

  // Error handling
  virtual std::shared_ptr<MotorErrorHandler> get_error_handler() = 0;
  virtual bool set_error_recovery_enabled(bool enable) = 0;
  virtual bool perform_diagnostic_test() = 0;

  // Advanced homing without limit switches
  virtual bool home_motor_absolute() = 0;  // Using absolute encoder
  virtual bool home_motor_incremental(double search_velocity = 0.5) = 0;  // Find mechanical stop
  virtual bool set_home_offset(double offset) = 0;
  virtual double get_home_accuracy() const = 0;

  // Power and thermal management
  virtual bool set_thermal_limits(double warning_temp, double critical_temp) = 0;
  virtual bool enable_thermal_protection(bool enable) = 0;
  virtual bool set_power_limits(
    double continuous_power, double peak_power,
    double peak_duration) = 0;

  // Communication diagnostics
  virtual double get_communication_latency_ms() const = 0;
  virtual uint32_t get_communication_error_count() const = 0;
  virtual bool test_communication_integrity() = 0;
};

} // namespace motor_control_ros2
