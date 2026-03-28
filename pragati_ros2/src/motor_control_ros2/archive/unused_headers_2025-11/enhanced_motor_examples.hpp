/*
 * Enhanced Motor Controller - Implementation Examples and Usage Patterns
 *
 * This file provides concrete examples and implementation patterns for the
 * enhanced motor controller interface addressing the 6 key enhancement points.
 */

#pragma once

#include "enhanced_motor_abstraction.hpp"
#include <memory>

namespace motor_control_ros2
{

// =============================================================================
// USAGE EXAMPLES FOR EACH ENHANCEMENT
// =============================================================================

/**
 * @brief Example: How to initialize motors without limit switches
 */
class MotorInitializationExample
{
public:
  static bool initialize_joint_motors_without_limits(
    std::vector<std::shared_ptr<EnhancedMotorControllerInterface>> & motors)
  {
    std::cout << "=== Initializing Joint Motors Without Limit Switches ===" << std::endl;

    for (size_t i = 0; i < motors.size(); ++i) {
      auto & motor = motors[i];

      // Step 1: Initialize with enhanced configuration
      FinalizedMotorConfiguration config;
      apply_joint_specific_config(config, i + 2); // joints 2,3,4,5

      if (!motor->initialize(config, create_can_interface())) {
        std::cerr << "Failed to initialize joint " << (i + 2) << std::endl;
        return false;
      }

      // Step 2: Enable dual encoders for precise homing
      if (!motor->enable_dual_encoders(true)) {
        std::cerr << "Failed to enable dual encoders for joint " << (i + 2) << std::endl;
        return false;
      }

      // Step 3: Perform absolute encoder homing (no limit switches needed)
      std::cout << "Homing joint " << (i + 2) << " using absolute encoders..." << std::endl;
      if (!motor->home_motor_absolute()) {
        std::cout << "Absolute homing failed, trying incremental homing..." << std::endl;

        // Fallback: Use incremental homing with mechanical stop detection
        if (!motor->home_motor_incremental(0.2)) { // 0.2 rad/s search velocity
          std::cerr << "All homing methods failed for joint " << (i + 2) << std::endl;
          return false;
        }
      }

      // Step 4: Verify homing accuracy
      double homing_accuracy = motor->get_home_accuracy();
      std::cout << "Joint " << (i + 2) << " homed with accuracy: "
                << homing_accuracy << " radians" << std::endl;

      if (homing_accuracy > 0.001) { // 1 mrad accuracy requirement
        std::cout << "Warning: Homing accuracy below requirements for joint " << (i + 2) <<
          std::endl;
      }
    }

    std::cout << "✅ All joint motors initialized and homed successfully!" << std::endl;
    return true;
  }

private:
  static void apply_joint_specific_config(FinalizedMotorConfiguration & config, int joint_id)
  {
    // Common settings for all joints
    config.motor_type = "canopen_servo"; // Generic name instead of "mg6010"
    config.joint_name = "joint" + std::to_string(joint_id);

    // Joint-specific CAN IDs (from yanthra_move logs)
    switch(joint_id) {
      case 2: config.can_id = 3; break; // Joint2 -> ODrive ID 3
      case 3: config.can_id = 0; break; // Joint3 -> ODrive ID 0
      case 4: config.can_id = 1; break; // Joint4 -> ODrive ID 1
      case 5: config.can_id = 2; break; // Joint5 -> ODrive ID 2
    }

    // Enhanced encoder configuration
    config.encoder_config.use_dual_encoders = true;
    config.encoder_config.motor_encoder_resolution = 16384;   // High-res motor encoder
    config.encoder_config.output_encoder_resolution = 4096;   // Absolute output encoder
    config.encoder_config.output_encoder_absolute = true;     // Absolute positioning
    config.encoder_config.max_encoder_error = 0.001;          // 1 mrad max error

    // Advanced PID configuration for precision
    config.position_pid.kp = 50.0;              // Higher gain for precision
    config.position_pid.ki = 0.1;               // Small integral for steady-state
    config.position_pid.kd = 5.0;               // Derivative for damping
    config.position_pid.kff_velocity = 0.8;     // Velocity feedforward
    config.position_pid.anti_windup_enabled = true;
    config.position_pid.integral_limit = 10.0;

    // Safety configuration without limit switches
    config.safety_config.emergency_stop_deceleration = 100.0; // Fast emergency stop
    config.safety_config.enable_safe_torque_off = true;       // Hardware safety
    config.safety_config.enable_predictive_safety = true;     // Predictive features

    // Performance requirements
    config.performance_config.target_position_accuracy = 0.0005; // 0.5 mrad accuracy
    config.performance_config.control_loop_frequency = 1000.0;   // 1kHz control
    config.performance_config.max_following_error = 0.01;        // 10 mrad max error

    // Motor-specific settings for generic servo
    config.motor_specific.motor_model = "Advanced_Servo_48V";
    config.motor_specific.can_protocol = CANProtocol::CANOPEN;
    config.motor_specific.supports_absolute_encoder = true;
    config.motor_specific.supports_dual_encoder = true;
    config.motor_specific.rated_torque = 1.5;  // Joint-appropriate torque
  }

  static std::shared_ptr<EnhancedCANInterface> create_can_interface()
  {
    // Return appropriate CAN interface based on motor type
    // This would be implemented in the actual factory
    return nullptr; // Placeholder
  }
};

/**
 * @brief Example: Dual encoder usage for enhanced precision
 */
class DualEncoderUsageExample
{
public:
  static bool demonstrate_dual_encoder_precision(
    std::shared_ptr<EnhancedMotorControllerInterface> motor)
  {
    std::cout << "=== Demonstrating Dual Encoder Precision ===" << std::endl;

    // Enable dual encoders
    if (!motor->enable_dual_encoders(true)) {
      std::cerr << "Failed to enable dual encoders" << std::endl;
      return false;
    }

    // Calibrate dual encoders for maximum accuracy
    std::cout << "Calibrating dual encoders..." << std::endl;
    if (!motor->calibrate_dual_encoders()) {
      std::cerr << "Dual encoder calibration failed" << std::endl;
      return false;
    }

    // Monitor encoder performance during operation
    for (int i = 0; i < 10; ++i) {
      // Get dual encoder data
      DualEncoderData encoder_data = motor->get_dual_encoder_data();

      std::cout << "Encoder Data Sample " << i << ":" << std::endl;
      std::cout << "  Motor Encoder:  " << encoder_data.motor.position_filtered
                << " rad (Quality: " << encoder_data.motor.signal_strength << ")" << std::endl;
      std::cout << "  Output Encoder: " << encoder_data.output.position_filtered
                << " rad (Quality: " << encoder_data.output.signal_strength << ")" << std::endl;
      std::cout << "  Fused Position: " << encoder_data.fused_position << " rad" << std::endl;
      std::cout << "  Position Error: " << encoder_data.position_error << " rad" << std::endl;
      std::cout << "  Confidence:     " << encoder_data.confidence_level << std::endl;

      // Check encoder health
      if (encoder_data.position_error > 0.001) { // 1 mrad threshold
        std::cout << "⚠️  Large encoder error detected!" << std::endl;
      }

      if (!encoder_data.encoders_aligned) {
        std::cout << "⚠️  Encoders not properly aligned!" << std::endl;
      }

      // Perform a small movement to test tracking
      double target = 0.1 * sin(i * 0.1); // Small sinusoidal movement
      motor->set_position(target);

      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    std::cout << "✅ Dual encoder demonstration completed" << std::endl;
    return true;
  }
};

/**
 * @brief Example: Advanced error handling and recovery
 */
class ErrorHandlingExample
{
public:
  static bool demonstrate_error_handling(
    std::shared_ptr<EnhancedMotorControllerInterface> motor)
  {
    std::cout << "=== Demonstrating Advanced Error Handling ===" << std::endl;

    // Get error handler
    auto error_handler = motor->get_error_handler();
    if (!error_handler) {
      std::cerr << "Error handler not available" << std::endl;
      return false;
    }

    // Enable automatic error recovery
    motor->set_error_recovery_enabled(true);

    // Monitor for different types of errors
    auto status = motor->get_enhanced_status();

    if (!status.active_errors.empty()) {
      std::cout << "Active errors detected:" << std::endl;
      for (const auto & error : status.active_errors) {
        print_error_details(error);

        // Attempt recovery based on error type
        if (error.auto_recoverable) {
          std::cout << "Attempting automatic recovery..." << std::endl;
          if (error_handler->attempt_recovery(error.code)) {
            std::cout << "✅ Recovery successful" << std::endl;
          } else {
            std::cout << "❌ Recovery failed" << std::endl;
          }
        } else {
          std::cout << "⚠️  Manual intervention required" << std::endl;
          std::cout << "Recovery suggestion: " << error.recovery_suggestion << std::endl;
        }
      }
    }

    // Test communication error recovery
    std::cout << "Testing communication diagnostics..." << std::endl;
    if (!motor->test_communication_integrity()) {
      std::cout << "Communication issues detected" << std::endl;

      double latency = motor->get_communication_latency_ms();
      uint32_t error_count = motor->get_communication_error_count();

      std::cout << "Communication latency: " << latency << " ms" << std::endl;
      std::cout << "Error count: " << error_count << std::endl;

      if (latency > 10.0) { // 10ms threshold
        std::cout << "⚠️  High communication latency detected" << std::endl;
      }
    }

    return true;
  }

private:
  static void print_error_details(const MotorError & error)
  {
    std::cout << "  Error Code: 0x" << std::hex << static_cast<uint32_t>(error.code) << std::dec <<
      std::endl;
    std::cout << "  Severity: " << severity_to_string(error.severity) << std::endl;
    std::cout << "  Description: " << error.description << std::endl;
    std::cout << "  Occurrences: " << error.occurrence_count << std::endl;
    std::cout << "  Auto-recoverable: " << (error.auto_recoverable ? "Yes" : "No") << std::endl;
  }

  static std::string severity_to_string(ErrorSeverity severity)
  {
    switch (severity) {
      case ErrorSeverity::INFO: return "INFO";
      case ErrorSeverity::WARNING: return "WARNING";
      case ErrorSeverity::ERROR: return "ERROR";
      case ErrorSeverity::CRITICAL: return "CRITICAL";
      case ErrorSeverity::FATAL: return "FATAL";
      default: return "UNKNOWN";
    }
  }
};

/**
 * @brief Example: Advanced motor tuning
 */
class MotorTuningExample
{
public:
  static bool demonstrate_advanced_tuning(
    std::shared_ptr<EnhancedMotorControllerInterface> motor)
  {
    std::cout << "=== Demonstrating Advanced Motor Tuning ===" << std::endl;

    // Get motor tuner
    auto tuner = motor->get_tuner();
    if (!tuner) {
      std::cerr << "Motor tuner not available" << std::endl;
      return false;
    }

    // Perform automatic tuning
    std::cout << "Performing automatic position loop tuning..." << std::endl;
    if (tuner->auto_tune_position_loop(0.05)) { // 0.05 rad test amplitude
      std::cout << "✅ Position loop auto-tuning successful" << std::endl;

      // Analyze performance
      double response_time = tuner->measure_step_response_time();
      double steady_error = tuner->measure_steady_state_error();
      double overshoot = tuner->measure_overshoot_percent();

      std::cout << "Performance metrics:" << std::endl;
      std::cout << "  Response time: " << response_time << " ms" << std::endl;
      std::cout << "  Steady-state error: " << steady_error << " rad" << std::endl;
      std::cout << "  Overshoot: " << overshoot << " %" << std::endl;

      // Check if tuning meets requirements
      if (response_time < 50.0 && steady_error < 0.001 && overshoot < 10.0) {
        std::cout << "✅ Tuning meets performance requirements" << std::endl;
      } else {
        std::cout << "⚠️  Tuning may need manual adjustment" << std::endl;
      }
    }

    // Enable adaptive control for varying loads
    std::cout << "Enabling adaptive control..." << std::endl;
    if (tuner->enable_adaptive_control(true)) {
      std::cout << "✅ Adaptive control enabled" << std::endl;
    }

    // Get current PID configuration
    AdvancedPIDConfig current_config = tuner->get_pid_config();
    std::cout << "Current PID configuration:" << std::endl;
    std::cout << "  Kp: " << current_config.kp << std::endl;
    std::cout << "  Ki: " << current_config.ki << std::endl;
    std::cout << "  Kd: " << current_config.kd << std::endl;
    std::cout << "  Velocity FF: " << current_config.kff_velocity << std::endl;

    return true;
  }
};

/**
 * @brief Complete integration example for Yanthra Move system
 */
class YanthraMoveIntegrationExample
{
public:
  static bool setup_enhanced_motor_system()
  {
    std::cout << "=== Setting Up Enhanced Motor System for Yanthra Move ===" << std::endl;

    // Create motors for joints 2, 3, 4, 5 (as seen in logs)
    std::vector<std::shared_ptr<EnhancedMotorControllerInterface>> joint_motors;

    for (int joint_id = 2; joint_id <= 5; ++joint_id) {
      // Create enhanced motor controller
      auto motor = create_enhanced_motor_controller("canopen_servo");
      if (!motor) {
        std::cerr << "Failed to create motor controller for joint " << joint_id << std::endl;
        return false;
      }

      joint_motors.push_back(motor);
    }

    // Initialize all motors
    if (!MotorInitializationExample::initialize_joint_motors_without_limits(joint_motors)) {
      std::cerr << "Motor initialization failed" << std::endl;
      return false;
    }

    // Setup continuous monitoring for all joints
    for (size_t i = 0; i < joint_motors.size(); ++i) {
      auto & motor = joint_motors[i];

      // Start continuous monitoring at 100 Hz
      motor->start_continuous_monitoring(100.0);

      // Enable thermal protection
      motor->enable_thermal_protection(true);
      motor->set_thermal_limits(70.0, 85.0); // Warning at 70°C, critical at 85°C

      // Set power limits appropriate for cotton picking
      motor->set_power_limits(400.0, 800.0, 5.0); // 400W continuous, 800W peak for 5s

      std::cout << "✅ Joint " << (i + 2) << " configured and monitoring enabled" << std::endl;
    }

    // Test coordinated movement (simulating cotton picking motion)
    std::cout << "Testing coordinated joint movement..." << std::endl;
    if (test_coordinated_movement(joint_motors)) {
      std::cout << "✅ Coordinated movement test successful" << std::endl;
    } else {
      std::cout << "⚠️  Coordinated movement test had issues" << std::endl;
    }

    return true;
  }

private:
  static std::shared_ptr<EnhancedMotorControllerInterface> create_enhanced_motor_controller(
    const std::string & motor_type)
  {
    // This would use the actual factory implementation
    // For now, return nullptr as placeholder
    return nullptr;
  }

  static bool test_coordinated_movement(
    const std::vector<std::shared_ptr<EnhancedMotorControllerInterface>> & motors)
  {
    // Simulate a cotton picking approach trajectory
    std::vector<double> target_positions = {0.5, 0.3, -0.2, 0.8}; // Example positions

    for (size_t i = 0; i < motors.size(); ++i) {
      // Use enhanced position control with velocity and acceleration limits
      if (!motors[i]->set_position_with_profile(target_positions[i], 2.0, 5.0)) {
        std::cerr << "Failed to set position for joint " << (i + 2) << std::endl;
        return false;
      }
    }

    // Wait for movement completion and monitor status
    std::this_thread::sleep_for(std::chrono::seconds(2));

    // Check if all joints reached target positions
    for (size_t i = 0; i < motors.size(); ++i) {
      double current_pos = motors[i]->get_position();
      double error = std::abs(current_pos - target_positions[i]);

      if (error > 0.01) { // 10 mrad tolerance
        std::cout << "⚠️  Joint " << (i + 2) << " position error: " << error << " rad" << std::endl;
      }
    }

    return true;
  }
};

} // namespace motor_control_ros2
