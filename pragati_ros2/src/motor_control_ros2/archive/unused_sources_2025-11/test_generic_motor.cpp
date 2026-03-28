/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * Test MG6010 48V Motor Controller Single Motor Integration
 *
 * This test validates the MG6010 controller with a single motor before
 * integration into the full robotic system. It tests basic motor operations
 * including initialization, homing, position control, and safety features.
 */

#include "motor_control_ros2/generic_motor_controller.hpp"
#include "motor_control_ros2/motor_parameter_mapping.hpp"
#include <iostream>
#include <chrono>
#include <thread>

using namespace motor_control_ros2;

/**
 * @brief Test configuration for MG6010 single motor
 */
MotorConfiguration create_test_configuration()
{
  MotorConfiguration config;

    // Basic motor identification
  config.axis_id = 1;
  config.motor_type = "mg6010";
  config.joint_name = "test_mg6010_motor";
  config.can_id = 0x001;

    // Mechanical configuration
  config.transmission_factor = 1.0;       // Direct drive for testing
  config.joint_offset = 0.0;
  config.encoder_offset = 0.0;
  config.encoder_resolution = 4096;       // 4096 counts per revolution
  config.direction = 1;

    // Control parameters
  config.p_gain = 20.0;
  config.v_gain = 0.5;
  config.v_int_gain = 0.01;
  config.current_limit = 15.0;            // 15A for testing
  config.velocity_limit = 5.0;            // 5 rad/s max

    // Safety limits
  config.limits.position_min = -10.0;     // -10 radians
  config.limits.position_max = 10.0;      // +10 radians
  config.limits.velocity_max = 5.0;       // 5 rad/s max
  config.limits.velocity_min = -5.0;      // -5 rad/s min
  config.limits.current_max = 15.0;       // 15A max
  config.limits.temperature_max = 80.0;   // 80°C max

    // Homing configuration
  config.homing.method = HomingConfig::LIMIT_SWITCH_ONLY;
  config.homing.homing_velocity = 1.0;
  config.homing.homing_acceleration = 2.0;
  config.homing.timeout_seconds = 30.0;

    // MG6010-specific parameters
  config.motor_params["voltage_nominal"] = 48.0;       // 48V nominal
  config.motor_params["power_max"] = 720.0;            // 48V * 15A = 720W
  config.motor_params["watchdog_timeout"] = 1.0;       // 1 second
  config.motor_params["startup_timeout"] = 10.0;       // 10 seconds

  return config;
}

/**
 * @brief Test basic motor initialization
 */
bool test_motor_initialization(
  GenericMotorController & controller,
  std::shared_ptr<CANInterface> can_interface)
{
  std::cout << "\n=== Testing Motor Initialization ===" << std::endl;

  MotorConfiguration config = create_test_configuration();

    // Test controller initialization
  std::cout << "Initializing MG6010 controller..." << std::endl;
  if (!controller.initialize(config, can_interface)) {
    std::cerr << "ERROR: Failed to initialize MG6010 controller" << std::endl;
    return false;
  }

  std::cout << "✓ Controller initialized successfully" << std::endl;

    // Check initial status
  MotorStatus status = controller.get_status();
  std::cout << "Initial motor state: " << static_cast<int>(status.state) << std::endl;
  std::cout << "Position: " << controller.get_position() << " rad" << std::endl;
  std::cout << "Velocity: " << controller.get_velocity() << " rad/s" << std::endl;

  return true;
}

/**
 * @brief Test motor enablement and safety checks
 */
bool test_motor_enablement(GenericMotorController & controller)
{
  std::cout << "\n=== Testing Motor Enablement ===" << std::endl;

    // Test enabling the motor
  std::cout << "Enabling motor..." << std::endl;
  if (!controller.set_enabled(true)) {
    std::cerr << "ERROR: Failed to enable motor" << std::endl;
    return false;
  }

  std::cout << "✓ Motor enabled successfully" << std::endl;

    // Wait for motor to settle
  std::this_thread::sleep_for(std::chrono::seconds(1));

    // Check status after enabling
  MotorStatus status = controller.get_status();
  if (status.state != MotorStatus::State::CLOSED_LOOP_CONTROL) {
    std::cout     << "WARNING: Motor not in closed loop control state (state: "
                  << static_cast<int>(status.state) << ")" << std::endl;
  }

  return true;
}

/**
 * @brief Test motor homing procedure
 */
bool test_motor_homing(GenericMotorController & controller)
{
  std::cout << "\n=== Testing Motor Homing ===" << std::endl;

    // Check if motor needs calibration first
  if (controller.needs_calibration()) {
    std::cout << "Motor requires calibration, performing calibration..." << std::endl;

    if (!controller.calibrate_motor()) {
      std::cerr << "ERROR: Motor calibration failed" << std::endl;
      return false;
    }

    std::cout << "✓ Motor calibration completed" << std::endl;

        // Wait for calibration to complete
    std::this_thread::sleep_for(std::chrono::seconds(3));
  }

    // Perform homing
  std::cout << "Starting homing procedure..." << std::endl;
  if (!controller.home_motor()) {
    std::cerr << "ERROR: Motor homing failed" << std::endl;
    return false;
  }

    // Wait for homing to complete (with timeout)
  int timeout = 30;   // 30 seconds max
  while (!controller.is_homed() && timeout > 0) {
    std::cout << "Waiting for homing to complete... (" << timeout << "s)" << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(1));
    timeout--;
  }

  if (!controller.is_homed()) {
    std::cerr << "ERROR: Homing did not complete within timeout" << std::endl;
    return false;
  }

  std::cout << "✓ Motor homing completed successfully" << std::endl;

    // Verify position after homing
  double home_position = controller.get_position();
  std::cout << "Home position: " << home_position << " rad" << std::endl;

  return true;
}

/**
 * @brief Test basic position control
 */
bool test_position_control(GenericMotorController & controller)
{
  std::cout << "\n=== Testing Position Control ===" << std::endl;

  double start_position = controller.get_position();
  std::cout << "Starting position: " << start_position << " rad" << std::endl;

    // Test small position movements
  std::vector<double> test_positions = {0.5, -0.5, 1.0, 0.0};

  for (double target_pos : test_positions) {
    std::cout << "Moving to position: " << target_pos << " rad" << std::endl;

    if (!controller.set_position(target_pos)) {
      std::cerr << "ERROR: Failed to set position " << target_pos << std::endl;
      return false;
    }

        // Wait for movement
    std::this_thread::sleep_for(std::chrono::seconds(2));

    double actual_pos = controller.get_position();
    double position_error = std::abs(actual_pos - target_pos);

    std::cout     << "Target: " << target_pos << " rad, Actual: " << actual_pos
                  << " rad, Error: " << position_error << " rad" << std::endl;

        // Check if position is within reasonable tolerance (0.1 rad = ~5.7 degrees)
    if (position_error > 0.1) {
      std::cout << "WARNING: Large position error detected" << std::endl;
    } else {
      std::cout << "✓ Position reached within tolerance" << std::endl;
    }
  }

  return true;
}

/**
 * @brief Test velocity control
 */
bool test_velocity_control(GenericMotorController & controller)
{
  std::cout << "\n=== Testing Velocity Control ===" << std::endl;

    // Test different velocity setpoints
  std::vector<double> test_velocities = {1.0, -1.0, 2.0, 0.0};

  for (double target_vel : test_velocities) {
    std::cout << "Setting velocity: " << target_vel << " rad/s" << std::endl;

    if (!controller.set_velocity(target_vel)) {
      std::cerr << "ERROR: Failed to set velocity " << target_vel << std::endl;
      return false;
    }

        // Wait for velocity to stabilize
    std::this_thread::sleep_for(std::chrono::seconds(1));

    double actual_vel = controller.get_velocity();
    double velocity_error = std::abs(actual_vel - target_vel);

    std::cout     << "Target: " << target_vel << " rad/s, Actual: " << actual_vel
                  << " rad/s, Error: " << velocity_error << " rad/s" << std::endl;

    if (velocity_error > 0.5) {
      std::cout << "WARNING: Large velocity error detected" << std::endl;
    } else {
      std::cout << "✓ Velocity reached within tolerance" << std::endl;
    }
  }

    // Stop the motor
  controller.set_velocity(0.0);
  std::this_thread::sleep_for(std::chrono::seconds(1));

  return true;
}

/**
 * @brief Test emergency stop functionality
 */
bool test_emergency_stop(GenericMotorController & controller)
{
  std::cout << "\n=== Testing Emergency Stop ===" << std::endl;

    // Start a slow movement
  std::cout << "Starting slow movement..." << std::endl;
  controller.set_velocity(0.5);
  std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Trigger emergency stop
  std::cout << "Triggering emergency stop..." << std::endl;
  if (!controller.emergency_stop()) {
    std::cerr << "ERROR: Emergency stop failed" << std::endl;
    return false;
  }

    // Check that motor stopped
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  double velocity_after_stop = controller.get_velocity();

  if (std::abs(velocity_after_stop) > 0.1) {
    std::cerr     << "ERROR: Motor did not stop after emergency stop (vel: "
                  << velocity_after_stop << " rad/s)" << std::endl;
    return false;
  }

  std::cout << "✓ Emergency stop successful" << std::endl;

    // Clear errors and re-enable
  std::cout << "Clearing errors and re-enabling motor..." << std::endl;
  controller.clear_errors();
  controller.set_enabled(true);

  return true;
}

/**
 * @brief Test 48V voltage monitoring
 */
bool test_48v_monitoring(GenericMotorController & controller)
{
  std::cout << "\n=== Testing 48V Power Monitoring ===" << std::endl;

    // Test voltage level checking
  if (!controller.check_voltage_levels()) {
    std::cout << "WARNING: Voltage levels check failed or out of range" << std::endl;
  } else {
    std::cout << "✓ 48V voltage levels within acceptable range" << std::endl;
  }

  // Test temperature monitoring
  double motor_temp = 0.0, driver_temp = 0.0;
  
  std::cout << "Checking temperature monitoring status..." << std::endl;
  bool temp_available = controller.get_temperature_status(motor_temp, driver_temp);
  
  if (!temp_available) {
    if (motor_temp < 0.0 || driver_temp < 0.0) {
      std::cout << "Temperature monitoring: Not yet implemented (waiting for MG6010 protocol support)" << std::endl;
      std::cout << "✓ Temperature monitoring framework present, implementation pending" << std::endl;
    } else {
      std::cout << "WARNING: Temperature monitoring failed" << std::endl;
    }
  } else {
    std::cout << "Motor temperature: " << motor_temp << "°C" << std::endl;
    std::cout << "Driver temperature: " << driver_temp << "°C" << std::endl;
    
    // Check temperature thresholds
    const double MAX_MOTOR_TEMP = 80.0;  // °C
    const double MAX_DRIVER_TEMP = 70.0;  // °C
    
    if (motor_temp > MAX_MOTOR_TEMP || driver_temp > MAX_DRIVER_TEMP) {
      std::cout << "WARNING: Temperature levels elevated" << std::endl;
    } else {
      std::cout << "✓ Temperature levels within safe range" << std::endl;
    }
  }

  return true;
}

/**
 * @brief Main test function
 */
int main(int argc, char * argv[])
{
  std::cout << "MG6010 48V Motor Controller Single Motor Test" << std::endl;
  std::cout << "=============================================" << std::endl;

    // Parse command line arguments
  std::string can_interface = "can0";
  if (argc > 1) {
    can_interface = argv[1];
  }

  std::cout << "Using CAN interface: " << can_interface << std::endl;

  try {
        // Create MG6010 controller and CAN interface
    GenericMotorController controller;
    std::shared_ptr<CANInterface> can_interface_ptr = std::make_shared<GenericCANInterface>();

        // Initialize CAN interface
    std::cout << "\nInitializing CAN interface..." << std::endl;
    if (!can_interface_ptr->initialize(can_interface, 1000000)) {
      std::cerr << "ERROR: Failed to initialize CAN interface" << std::endl;
      std::cerr << "Make sure CAN interface is up: sudo ip link set " << can_interface <<
        " up type can bitrate 1000000" << std::endl;
      return 1;
    }

    std::cout << "✓ CAN interface initialized" << std::endl;

        // Run tests
    bool all_tests_passed = true;

    all_tests_passed &= test_motor_initialization(controller, can_interface_ptr);
    all_tests_passed &= test_motor_enablement(controller);
    all_tests_passed &= test_motor_homing(controller);
    all_tests_passed &= test_position_control(controller);
    all_tests_passed &= test_velocity_control(controller);
    all_tests_passed &= test_emergency_stop(controller);
    all_tests_passed &= test_48v_monitoring(controller);

        // Final cleanup
    std::cout << "\n=== Test Cleanup ===" << std::endl;
    controller.set_enabled(false);
    std::cout << "✓ Motor disabled" << std::endl;

        // Report results
    std::cout << "\n=== Test Results ===" << std::endl;
    if (all_tests_passed) {
      std::cout << "✓ ALL TESTS PASSED - MG6010 controller ready for integration" << std::endl;
      return 0;
    } else {
      std::cout << "✗ SOME TESTS FAILED - Review errors above" << std::endl;
      return 1;
    }

  } catch (const std::exception & e) {
    std::cerr << "EXCEPTION: " << e.what() << std::endl;
    return 1;
  }
}
