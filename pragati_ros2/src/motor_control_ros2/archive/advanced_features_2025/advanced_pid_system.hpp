/*
 * Advanced PID Control and Motor Optimization System
 *
 * This comprehensive system provides:
 * 1. Advanced PID controllers with multiple tuning algorithms
 * 2. Auto-tuning capabilities using various methods
 * 3. Adaptive control with real-time parameter adjustment
 * 4. Performance monitoring and optimization
 * 5. Motor-specific optimization parameters
 * 6. Feed-forward compensation and disturbance rejection
 */

#pragma once

#include "motor_abstraction.hpp"
#include "comprehensive_error_handler.hpp"
#include "dual_encoder_system.hpp"
#include <memory>
#include <array>
#include <deque>
#include <chrono>
#include <mutex>
#include <atomic>
#include <functional>

namespace motor_control_ros2
{

// =============================================================================
// ADVANCED PID CONFIGURATION AND TYPES
// =============================================================================

/**
 * @brief Control loop types supported
 */
enum class ControlLoopType : uint8_t
{
  POSITION_CONTROL = 0,     // Position control loop
  VELOCITY_CONTROL = 1,     // Velocity control loop
  TORQUE_CONTROL = 2,       // Torque/current control loop
  CASCADE_CONTROL = 3,      // Cascaded position->velocity->torque
  HYBRID_CONTROL = 4        // Hybrid control with mode switching
};

/**
 * @brief PID tuning methods
 */
enum class TuningMethod : uint8_t
{
  MANUAL = 0,               // Manual tuning
  ZIEGLER_NICHOLS = 1,      // Ziegler-Nichols method
  COHEN_COON = 2,           // Cohen-Coon method
  AUTO_RELAY = 3,           // Auto-relay tuning
  GENETIC_ALGORITHM = 4,    // GA-based optimization
  PARTICLE_SWARM = 5,       // PSO-based optimization
  ADAPTIVE_ONLINE = 6       // Online adaptive tuning
};

/**
 * @brief Comprehensive PID parameters
 */
struct AdvancedPIDParams
{
  // Basic PID gains
  double kp = 1.0;                    // Proportional gain
  double ki = 0.0;                    // Integral gain
  double kd = 0.0;                    // Derivative gain

  // Advanced parameters
  double feed_forward_gain = 0.0;     // Feed-forward gain
  double derivative_filter_freq = 0.0; // Derivative filter frequency (Hz)
  double integral_windup_limit = 1.0; // Anti-windup limit

  // Limits and constraints
  double output_min = -1.0;           // Minimum output
  double output_max = 1.0;            // Maximum output
  double integral_min = -0.5;         // Integral term limits
  double integral_max = 0.5;

  // Adaptive parameters
  bool enable_adaptive_gains = false; // Enable adaptive gain adjustment
  double adaptation_rate = 0.01;      // Rate of adaptation
  double noise_band = 0.001;          // Dead band for noise rejection

  // Performance tuning
  double settling_time_target = 1.0;  // Desired settling time (seconds)
  double overshoot_limit = 0.1;       // Maximum overshoot (0-1)
  double steady_state_error_limit = 0.001; // Steady-state error limit

  AdvancedPIDParams() = default;
};

/**
 * @brief Motor-specific optimization parameters
 */
struct MotorOptimizationParams
{
  // Motor characteristics
  double motor_inertia = 0.001;       // Motor inertia (kg⋅m²)
  double friction_coefficient = 0.01;  // Friction coefficient
  double back_emf_constant = 0.1;     // Back EMF constant
  double resistance = 1.0;            // Motor resistance (Ω)
  double inductance = 0.001;          // Motor inductance (H)

  // Load characteristics
  double load_inertia = 0.005;        // Load inertia (kg⋅m²)
  double gear_ratio = 1.0;            // Gear ratio
  double load_friction = 0.02;        // Load friction

  // Environmental factors
  double temperature_coefficient = 0.001; // Temperature effect on resistance
  double supply_voltage_nominal = 24.0;   // Nominal supply voltage

  // Control constraints
  double max_current = 10.0;          // Maximum motor current (A)
  double max_velocity = 100.0;        // Maximum velocity (rad/s)
  double max_acceleration = 1000.0;   // Maximum acceleration (rad/s²)

  MotorOptimizationParams() = default;
};

// =============================================================================
// ADVANCED PID CONTROLLER
// =============================================================================

/**
 * @brief Advanced PID controller with comprehensive features
 */
class AdvancedPIDController
{
public:
  /**
   * @brief Control performance metrics
   */
  struct PerformanceMetrics
  {
    double settling_time = 0.0;        // Actual settling time
    double rise_time = 0.0;            // Rise time (10% to 90%)
    double overshoot_percent = 0.0;    // Peak overshoot percentage
    double steady_state_error = 0.0;   // Steady-state error
    double integral_absolute_error = 0.0; // IAE
    double integral_squared_error = 0.0;   // ISE
    double root_mean_square_error = 0.0;   // RMSE

    // Real-time metrics
    double current_error = 0.0;
    double current_output = 0.0;
    double derivative_term = 0.0;
    double integral_term = 0.0;
    double proportional_term = 0.0;

    std::chrono::steady_clock::time_point last_update;

    PerformanceMetrics()
    {
      last_update = std::chrono::steady_clock::now();
    }
  };

  /**
   * @brief Controller status
   */
  struct ControllerStatus
  {
    bool is_active = false;
    bool is_tuned = false;
    bool is_stable = true;
    bool windup_active = false;

    ControlLoopType loop_type = ControlLoopType::POSITION_CONTROL;
    TuningMethod last_tuning_method = TuningMethod::MANUAL;

    double control_frequency_hz = 1000.0;
    std::chrono::steady_clock::time_point last_execution;

    PerformanceMetrics performance;
    std::vector<MotorError> controller_errors;
  };

public:
  AdvancedPIDController(ControlLoopType loop_type = ControlLoopType::POSITION_CONTROL);
  ~AdvancedPIDController();

  // =============================================================================
  // CONTROLLER OPERATION
  // =============================================================================

  /**
   * @brief Initialize controller with parameters
   */
  bool initialize(
    const AdvancedPIDParams & params,
    const MotorOptimizationParams & motor_params = MotorOptimizationParams());

  /**
   * @brief Execute control loop
   */
  double execute_control(double setpoint, double process_value, double dt);

  /**
   * @brief Reset controller state
   */
  void reset_controller();

  /**
   * @brief Enable/disable controller
   */
  void set_enabled(bool enabled);

  /**
   * @brief Check if controller is enabled
   */
  bool is_enabled() const;

  // =============================================================================
  // PARAMETER MANAGEMENT
  // =============================================================================

  /**
   * @brief Update PID parameters
   */
  bool update_parameters(const AdvancedPIDParams & params);

  /**
   * @brief Get current parameters
   */
  AdvancedPIDParams get_parameters() const;

  /**
   * @brief Update motor parameters
   */
  bool update_motor_parameters(const MotorOptimizationParams & motor_params);

  /**
   * @brief Set output limits
   */
  void set_output_limits(double min_output, double max_output);

  // =============================================================================
  // AUTO-TUNING CAPABILITIES
  // =============================================================================

  /**
   * @brief Start auto-tuning process
   */
  bool start_auto_tuning(
    TuningMethod method = TuningMethod::AUTO_RELAY,
    double amplitude = 0.1,
    std::chrono::milliseconds duration = std::chrono::milliseconds(30000));

  /**
   * @brief Check if auto-tuning is complete
   */
  bool is_auto_tuning_complete() const;

  /**
   * @brief Get auto-tuning results
   */
  bool get_auto_tuning_results(AdvancedPIDParams & tuned_params, double & performance_score);

  /**
   * @brief Stop auto-tuning
   */
  void stop_auto_tuning();

  // =============================================================================
  // MONITORING AND DIAGNOSTICS
  // =============================================================================

  /**
   * @brief Get controller status
   */
  ControllerStatus get_status() const;

  /**
   * @brief Get performance metrics
   */
  PerformanceMetrics get_performance_metrics() const;

  /**
   * @brief Generate performance report
   */
  std::string generate_performance_report() const;

  /**
   * @brief Register performance callback
   */
  void register_performance_callback(std::function<void(const PerformanceMetrics &)> callback);

private:
  ControlLoopType loop_type_;
  AdvancedPIDParams params_;
  MotorOptimizationParams motor_params_;
  ControllerStatus status_;

  // Internal state
  double previous_error_;
  double integral_sum_;
  double derivative_filtered_;
  std::chrono::steady_clock::time_point last_execution_time_;

  // Auto-tuning state
  std::atomic<bool> auto_tuning_active_;
  std::thread auto_tuning_thread_;
  TuningMethod current_tuning_method_;

  // Performance monitoring
  std::deque<double> error_history_;
  std::deque<double> output_history_;
  std::deque<std::chrono::steady_clock::time_point> timestamp_history_;

  // Callbacks
  std::vector<std::function<void(const PerformanceMetrics &)>> performance_callbacks_;

  mutable std::mutex controller_mutex_;

  // Internal methods
  double calculate_proportional_term(double error);
  double calculate_integral_term(double error, double dt);
  double calculate_derivative_term(double error, double dt);
  double calculate_feed_forward_term(double setpoint);
  double apply_output_limits(double output);
  void handle_integral_windup();
  void update_performance_metrics(double setpoint, double process_value, double output);

  // Auto-tuning methods
  void auto_tuning_thread_function();
  bool tune_ziegler_nichols();
  bool tune_cohen_coon();
  bool tune_auto_relay();
  bool tune_genetic_algorithm();
  double evaluate_controller_performance(const AdvancedPIDParams & test_params);
};

// =============================================================================
// CASCADED CONTROL SYSTEM
// =============================================================================

/**
 * @brief Cascaded PID controller (Position -> Velocity -> Torque)
 */
class CascadedPIDSystem
{
public:
  struct CascadeParams
  {
    AdvancedPIDParams position_loop;
    AdvancedPIDParams velocity_loop;
    AdvancedPIDParams torque_loop;

    // Inter-loop settings
    double position_loop_frequency = 100.0;  // Hz
    double velocity_loop_frequency = 1000.0; // Hz
    double torque_loop_frequency = 10000.0;  // Hz

    // Feedforward paths
    bool enable_velocity_feedforward = true;
    bool enable_acceleration_feedforward = true;
    double velocity_ff_gain = 1.0;
    double acceleration_ff_gain = 0.1;
  };

public:
  CascadedPIDSystem();
  ~CascadedPIDSystem();

  bool initialize(const CascadeParams & params, const MotorOptimizationParams & motor_params);
  double execute_position_control(
    double position_setpoint, double position_feedback,
    double velocity_feedback, double torque_feedback, double dt);
  bool tune_cascade_system(TuningMethod method = TuningMethod::AUTO_RELAY);

  AdvancedPIDController & get_position_controller() {return position_controller_;}
  AdvancedPIDController & get_velocity_controller() {return velocity_controller_;}
  AdvancedPIDController & get_torque_controller() {return torque_controller_;}

private:
  CascadeParams cascade_params_;
  AdvancedPIDController position_controller_;
  AdvancedPIDController velocity_controller_;
  AdvancedPIDController torque_controller_;

  // Internal state for feedforward
  double previous_position_setpoint_;
  double previous_velocity_setpoint_;
  std::chrono::steady_clock::time_point last_execution_;
};

// =============================================================================
// MOTOR OPTIMIZATION SYSTEM
// =============================================================================

/**
 * @brief Comprehensive motor optimization system
 */
class MotorOptimizationSystem
{
public:
  struct OptimizationResult
  {
    AdvancedPIDParams optimized_params;
    MotorOptimizationParams motor_params;
    double performance_score;
    std::string optimization_report;
    std::chrono::milliseconds optimization_time;
    bool success;
  };

public:
  MotorOptimizationSystem();

  /**
   * @brief Optimize motor parameters for specific application
   */
  OptimizationResult optimize_for_application(
    const std::string & application_type, // "precision", "speed", "efficiency", "balanced"
    const MotorOptimizationParams & initial_motor_params,
    std::shared_ptr<DualEncoderSystem> encoder_system = nullptr);

  /**
   * @brief Optimize for specific performance criteria
   */
  OptimizationResult optimize_for_criteria(
    double settling_time_weight = 0.3,
    double overshoot_weight = 0.3,
    double steady_state_error_weight = 0.2,
    double energy_efficiency_weight = 0.2);

  /**
   * @brief Real-time adaptive optimization
   */
  bool start_adaptive_optimization(std::shared_ptr<AdvancedPIDController> controller);
  void stop_adaptive_optimization();

private:
  std::atomic<bool> adaptive_optimization_running_;
  std::thread adaptive_thread_;

  // Optimization methods
  AdvancedPIDParams genetic_algorithm_optimization(const MotorOptimizationParams & motor_params);
  AdvancedPIDParams particle_swarm_optimization(const MotorOptimizationParams & motor_params);
  double objective_function(const AdvancedPIDParams & params, const std::string & criteria);
};

} // namespace motor_control_ros2
