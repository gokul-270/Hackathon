/*
 * PID Cascaded Controller Header
 *
 * This header defines the interface for cascaded PID control loops
 * including position-velocity, position-velocity-current cascades.
 */

#ifndef PID_CASCADED_CONTROLLER_HPP
#define PID_CASCADED_CONTROLLER_HPP

#include <memory>
#include <mutex>
#include <chrono>
#include <vector>
#include <string>
#include "motor_control_ros2/comprehensive_error_handler.hpp"
#include "motor_control_ros2/pid_auto_tuner.hpp"

namespace motor_control_ros2
{

// Forward declarations
class BasicPIDController;
class FeedforwardCompensator;

// Cascade modes
enum class CascadeMode
{
  POSITION_VELOCITY,
  POSITION_VELOCITY_CURRENT,
  VELOCITY_CURRENT
};

// Cascade configuration
struct CascadedControlConfig
{
    // Loop frequencies (inner loop should be fastest)
  double outer_loop_frequency_hz = 100.0;
  double middle_loop_frequency_hz = 500.0;
  double inner_loop_frequency_hz = 2000.0;

    // PID parameters for each loop
  PIDParameters position_loop;
  PIDParameters velocity_loop;
  PIDParameters current_loop;

    // Feedforward configurations
  struct FeedforwardConfig
  {
    bool enable = true;
    double gain = 1.0;
    double time_constant = 0.01;
  } position_feedforward, velocity_feedforward;

    // Safety limits
  struct SafetyLimits
  {
    double min_value = -1000.0;
    double max_value = 1000.0;
  } velocity_limits, current_limits, torque_limits;

    // Motor parameters
  double motor_inertia_kg_m2 = 0.001;
  double motor_torque_constant_nm_per_a = 0.1;

    // Performance monitoring
  size_t performance_window_size = 100;
  int max_feedback_age_ms = 10;
};

// Cascade targets
struct CascadeTargets
{
  double position = 0.0;
  double velocity = 0.0;
  double current = 0.0;
  double velocity_feedforward = 0.0;
  double acceleration_feedforward = 0.0;
  std::chrono::steady_clock::time_point timestamp;
};

// Cascade feedback
struct CascadeFeedback
{
  double position = 0.0;
  double velocity = 0.0;
  double current = 0.0;
  bool has_current_feedback = false;
  std::chrono::steady_clock::time_point timestamp;
  bool is_valid = true;
};

// Cascade control output
struct CascadeControlOutput
{
  double position_command = 0.0;
  double velocity_command = 0.0;
  double current_command = 0.0;
  double torque_command = 0.0;
  std::chrono::steady_clock::time_point timestamp;
  bool is_valid = false;
};

// Cascade status
struct CascadeStatus
{
  bool is_active = false;
  CascadeMode cascade_mode = CascadeMode::POSITION_VELOCITY;
  bool outer_loop_saturated = false;
  bool middle_loop_saturated = false;
  bool inner_loop_saturated = false;
  std::chrono::steady_clock::time_point last_update_time;
};

// Performance data
struct CascadePerformanceData
{
  double outer_loop_error_rms = 0.0;
  double middle_loop_error_rms = 0.0;
  double inner_loop_error_rms = 0.0;
  double settling_time_ms = 0.0;
  double bandwidth_hz = 0.0;
  double phase_margin_deg = 0.0;
  std::chrono::steady_clock::time_point last_update_time;
};

// Cascade state tracking
struct CascadeState
{
  double outer_loop_output = 0.0;
  double middle_loop_output = 0.0;
  double inner_loop_output = 0.0;
  double feedforward_compensation = 0.0;
  std::chrono::steady_clock::time_point last_update_time;
  bool is_valid = false;
};

// Feedforward input
struct FeedforwardInput
{
  double reference_position = 0.0;
  double reference_velocity = 0.0;
  double reference_acceleration = 0.0;
};

/**
 * Feedforward Compensator Class
 *
 * Provides feedforward compensation for improved tracking performance.
 */
class FeedforwardCompensator {
public:
  struct Config
  {
    bool enable = true;
    double gain = 1.0;
    double time_constant = 0.01;
    double derivative_gain = 0.0;
  };

  explicit FeedforwardCompensator(const Config & config)
  : config_(config), last_compensation_(0.0) {}

  double compute_compensation(const FeedforwardInput & input)
  {
    if (!config_.enable) {
      return 0.0;
    }

        // Simple feedforward: gain * reference + derivative term
    last_compensation_ = config_.gain * input.reference_velocity +
      config_.derivative_gain * input.reference_acceleration;
    return last_compensation_;
  }

  double get_last_compensation() const {return last_compensation_;}

private:
  Config config_;
  double last_compensation_;
};

/**
 * Basic PID Controller Class
 *
 * Simple PID controller for use in cascaded loops.
 */
class BasicPIDController {
public:
  explicit BasicPIDController(const PIDParameters & params)
  : params_(params), last_error_(0.0), integral_(0.0), last_output_(0.0) {}

  double compute(double error, const std::chrono::steady_clock::time_point & timestamp)
  {
    static auto last_time = timestamp;
    auto dt = std::chrono::duration<double>(timestamp - last_time).count();
    last_time = timestamp;

        // Clamp dt to reasonable bounds
    dt = std::max(0.001, std::min(dt, 0.1));

        // Proportional term
    double proportional = params_.kp * error;

        // Integral term with windup protection
    integral_ += error * dt;
    if (std::abs(integral_) > params_.integral_windup_limit) {
      integral_ = std::copysign(params_.integral_windup_limit, integral_);
    }
    double integral_term = params_.ki * integral_;

        // Derivative term
    double derivative = params_.kd * (error - last_error_) / dt;
    last_error_ = error;

        // Combine terms
    double output = proportional + integral_term + derivative;

        // Apply output limits
    output = std::max(params_.output_min, std::min(params_.output_max, output));

    last_output_ = output;
    return output;
  }

  void reset()
  {
    last_error_ = 0.0;
    integral_ = 0.0;
    last_output_ = 0.0;
  }

  bool set_parameters(const PIDParameters & params)
  {
    params_ = params;
    return true;
  }

  double get_last_output() const {return last_output_;}
  double get_output_min() const {return params_.output_min;}
  double get_output_max() const {return params_.output_max;}

private:
  PIDParameters params_;
  double last_error_;
  double integral_;
  double last_output_;
};

/**
 * PID Cascaded Controller Class
 *
 * Implements cascaded PID control loops for enhanced performance.
 */
class PIDCascadedController {
public:
  explicit PIDCascadedController(
    const CascadedControlConfig & config,
    std::shared_ptr<ComprehensiveErrorHandler> error_handler);
  ~PIDCascadedController();

    // Lifecycle
  bool initialize();
  void shutdown();

    // Configuration
  bool configure_for_position_velocity_cascade();
  bool configure_for_position_velocity_current_cascade();

    // Control
  bool set_cascade_targets(const CascadeTargets & targets);
  CascadeControlOutput compute_cascade_control(const CascadeFeedback & feedback);
  bool enable_cascade(bool enable);

    // Status and diagnostics
  CascadeStatus get_cascade_status() const;
  CascadePerformanceData get_performance_data() const;

private:
    // Configuration and dependencies
  CascadedControlConfig config_;
  std::shared_ptr<ComprehensiveErrorHandler> error_handler_;

    // State management
  bool is_initialized_;
  CascadeMode cascade_mode_;
  bool is_active_;

    // Controllers
  std::unique_ptr<BasicPIDController> outer_controller_;
  std::unique_ptr<BasicPIDController> middle_controller_;
  std::unique_ptr<BasicPIDController> inner_controller_;

    // Feedforward compensators
  std::unique_ptr<FeedforwardCompensator> position_feedforward_;
  std::unique_ptr<FeedforwardCompensator> velocity_feedforward_;

    // Threading and synchronization
  mutable std::mutex controller_mutex_;
  mutable std::mutex targets_mutex_;
  mutable std::mutex performance_mutex_;

    // Data
  CascadeTargets current_targets_;
  CascadeState cascade_state_;
  CascadePerformanceData performance_data_;

    // Performance tracking
  std::vector<double> position_error_history_;
  std::vector<double> velocity_error_history_;
  std::vector<double> current_error_history_;

    // Private methods
  bool validate_configuration();
  bool validate_pid_parameters(const PIDParameters & params);
  bool initialize_controllers();
  bool initialize_feedforward();
  void initialize_performance_monitoring();

  bool validate_feedback(const CascadeFeedback & feedback);

    // Cascade computation methods
  bool compute_position_velocity_cascade(
    const CascadeFeedback & feedback,
    CascadeControlOutput & output);
  bool compute_position_velocity_current_cascade(
    const CascadeFeedback & feedback,
    CascadeControlOutput & output);
  bool compute_velocity_current_cascade(
    const CascadeFeedback & feedback,
    CascadeControlOutput & output);

    // Utility methods
  void apply_feedforward_compensation(CascadeControlOutput & output);
  void apply_output_limits(CascadeControlOutput & output);
  void store_error_data(double position_error, double velocity_error, double current_error);
  void update_performance_metrics(
    const CascadeFeedback & feedback,
    const CascadeControlOutput & output);
  void update_computation_metrics(double computation_time_us);

  bool is_controller_saturated(const BasicPIDController * controller) const;

  void report_error(const std::string & message);
  void log_cascade_event(const std::string & message);
};

} // namespace motor_control_ros2

#endif // PID_CASCADED_CONTROLLER_HPP
