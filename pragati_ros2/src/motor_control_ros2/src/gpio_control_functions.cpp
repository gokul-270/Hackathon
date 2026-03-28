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

/**
 * @file gpio_control_functions.cpp
 * @brief GPIO control functions implementation for Pragati cotton picking robot
 * @author Migrated from ROS-1 yanthra_move implementation
 * @date September 2025
 */

#include "motor_control_ros2/gpio_control_functions.hpp"
#include <thread>
#include <chrono>

namespace motor_control_ros2
{

GPIOControlFunctions::GPIOControlFunctions(const rclcpp::Logger& logger)
  : logger_(logger),
    initialized_(false),
    last_error_(""),
    global_vacuum_motor_(true),
    end_effector_enable_(true),
    continous_vacuum_(false),
    end_effector_direction_(CLOCKWISE),
    start_switch_pulses_(0),
    shutdown_switch_pulses_(0)
{
  gpio_interface_ = std::make_unique<GPIOInterface>();
}

GPIOControlFunctions::~GPIOControlFunctions()
{
  cleanup();
}

bool GPIOControlFunctions::initialize()
{
  // Atomic test-and-set: prevent concurrent double-initialization
  if (initialized_.exchange(true))
  {
    return true;
  }

  // Initialize the underlying GPIO interface
  if (!gpio_interface_->initialize())
  {
    last_error_ = "Failed to initialize GPIO interface: " + gpio_interface_->get_last_error();
    RCLCPP_ERROR(logger_, "%s", last_error_.c_str());
    initialized_ = false;  // Revert on failure
    return false;
  }

  // Setup all GPIO pins for outputs/inputs
  if (!setup_gpio_pins())
  {
    last_error_ = "Failed to setup GPIO pins";
    RCLCPP_ERROR(logger_, "%s", last_error_.c_str());
    initialized_ = false;  // Revert on failure
    return false;
  }

  RCLCPP_INFO(logger_, "✅ GPIO Control Functions initialized successfully");
  return true;
}

void GPIOControlFunctions::cleanup()
{
  if (initialized_)
  {
    // Turn off all outputs before cleanup
    vacuum_pump_control(false);
    end_effector_control(false);
    compressor_control(false);
    end_effector_drop_control(false);
    camera_led_control(false);

    gpio_interface_->cleanup();
    initialized_ = false;
    RCLCPP_INFO(logger_, "GPIO Control Functions cleaned up");
  }
}

bool GPIOControlFunctions::setup_gpio_pins()
{
  // Setup output pins
  const int PI_OUTPUT = 1;
  const int PI_INPUT = 0;

  bool success = true;

  // Vacuum and end effector outputs
  success &= gpio_interface_->set_mode(VACUUM_MOTOR_ON_PIN, PI_OUTPUT);
  success &= gpio_interface_->set_mode(END_EFFECTOR_ON_PIN, PI_OUTPUT);
  success &= gpio_interface_->set_mode(END_EFFECTOR_DIRECTION_PIN, PI_OUTPUT);
  success &= gpio_interface_->set_mode(END_EFFECTOR_DROP_ON, PI_OUTPUT);
  success &= gpio_interface_->set_mode(END_EFFECTOR_DROP_DIRECTION, PI_OUTPUT);

  // LED outputs
  success &= gpio_interface_->set_mode(GREEN_LED_PIN, PI_OUTPUT);
  success &= gpio_interface_->set_mode(RED_LED_PIN, PI_OUTPUT);

  // Solenoid and camera outputs
  success &= gpio_interface_->set_mode(COMPRESSOR_PIN, PI_OUTPUT);
  success &= gpio_interface_->set_mode(CAMERA_LED_PIN, PI_OUTPUT);

  // Switch inputs
  success &= gpio_interface_->set_mode(SHUTDOWN_SWITCH, PI_INPUT);
  success &= gpio_interface_->set_mode(START_SWITCH, PI_INPUT);

  // Initialize all outputs to safe state (OFF)
  gpio_interface_->write_gpio(VACUUM_MOTOR_ON_PIN, VACUUM_OFF);
  gpio_interface_->write_gpio(END_EFFECTOR_ON_PIN, END_EFFECTOR_OFF);
  gpio_interface_->write_gpio(END_EFFECTOR_DIRECTION_PIN, 0);
  gpio_interface_->write_gpio(END_EFFECTOR_DROP_ON, 0);
  gpio_interface_->write_gpio(END_EFFECTOR_DROP_DIRECTION, 0);
  gpio_interface_->write_gpio(GREEN_LED_PIN, LED_OFF);
  gpio_interface_->write_gpio(RED_LED_PIN, LED_OFF);
  gpio_interface_->write_gpio(COMPRESSOR_PIN, 0);
  gpio_interface_->write_gpio(CAMERA_LED_PIN, 0);

  if (!success)
  {
    RCLCPP_WARN(logger_, "⚠️  Some GPIO pins failed to initialize (may be in simulation mode)");
  }

  return success;
}

void GPIOControlFunctions::log_gpio_operation(const std::string& operation, int pin, int value)
{
  RCLCPP_DEBUG(logger_, "[GPIO] %s: pin=%d, value=%d", operation.c_str(), pin, value);
}

// ==================================================================================
// VACUUM SYSTEM CONTROL
// ==================================================================================

void GPIOControlFunctions::vacuum_pump_control(bool vacuum_pump_state)
{
  if (!global_vacuum_motor_)
  {
    RCLCPP_DEBUG(logger_, "[GPIO] Vacuum pump disabled by global_vacuum_motor flag");
    return;
  }

  if (vacuum_pump_state)
  {
    gpio_interface_->write_gpio(VACUUM_MOTOR_ON_PIN, VACUUM_ON);
    log_gpio_operation("Vacuum Pump ON", VACUUM_MOTOR_ON_PIN, VACUUM_ON);
  }
  else
  {
    gpio_interface_->write_gpio(VACUUM_MOTOR_ON_PIN, VACUUM_OFF);
    log_gpio_operation("Vacuum Pump OFF", VACUUM_MOTOR_ON_PIN, VACUUM_OFF);
  }
}

// ==================================================================================
// END EFFECTOR CONTROL
// ==================================================================================

void GPIOControlFunctions::end_effector_control(bool end_effector_condition)
{
  if (end_effector_condition)
  {
    // Turn ON with current direction
    if (end_effector_direction_ == CLOCKWISE)
    {
      // CLOCKWISE (forward) -> DIR HIGH (Cytron board)
      gpio_interface_->write_gpio(END_EFFECTOR_ON_PIN, 1);
      gpio_interface_->write_gpio(END_EFFECTOR_DIRECTION_PIN, 1);
      log_gpio_operation("End Effector ON (CLOCKWISE)", END_EFFECTOR_ON_PIN, 1);
    }
    else
    {
      // ANTICLOCKWISE (reverse) -> DIR LOW (Cytron board)
      gpio_interface_->write_gpio(END_EFFECTOR_ON_PIN, 1);
      gpio_interface_->write_gpio(END_EFFECTOR_DIRECTION_PIN, 0);
      log_gpio_operation("End Effector ON (ANTICLOCKWISE)", END_EFFECTOR_ON_PIN, 1);
    }
  }
  else
  {
    // Turn OFF
    gpio_interface_->write_gpio(END_EFFECTOR_ON_PIN, 0);
    gpio_interface_->write_gpio(END_EFFECTOR_DIRECTION_PIN, 0);
    log_gpio_operation("End Effector OFF", END_EFFECTOR_ON_PIN, 0);
  }
}

void GPIOControlFunctions::set_end_effector_direction(bool direction)
{
  // Set the direction for next activation
  if (direction == CLOCKWISE)
  {
    end_effector_direction_ = CLOCKWISE;
    RCLCPP_DEBUG(logger_, "[GPIO] End Effector direction set to CLOCKWISE");
  }
  else
  {
    end_effector_direction_ = ANTICLOCKWISE;
    RCLCPP_DEBUG(logger_, "[GPIO] End Effector direction set to ANTICLOCKWISE");
  }
}

void GPIOControlFunctions::end_effector_drop_control(bool conveyor)
{
  if (conveyor == DROP_EEF)
  {
    RCLCPP_INFO(logger_, "[GPIO] END EFFECTOR DROP BELT RUNNING FORWARD");
    gpio_interface_->write_gpio(END_EFFECTOR_DROP_ON, 1);
    gpio_interface_->write_gpio(END_EFFECTOR_DROP_DIRECTION, 1);  // HIGH = forward (inverted)
  }
  else if (conveyor == STOP_EEF)
  {
    RCLCPP_INFO(logger_, "[GPIO] END EFFECTOR DROP BELT STOPS");
    gpio_interface_->write_gpio(END_EFFECTOR_DROP_ON, 0);
    gpio_interface_->write_gpio(END_EFFECTOR_DROP_DIRECTION, 0);
  }
}

void GPIOControlFunctions::end_effector_drop_eject(int duration_ms)
{
  RCLCPP_INFO(logger_, "[GPIO] END EFFECTOR DROP BELT RUNNING REVERSE (eject) for %dms", duration_ms);
  gpio_interface_->write_gpio(END_EFFECTOR_DROP_ON, 1);       // BCM 12 HIGH - enable
  gpio_interface_->write_gpio(END_EFFECTOR_DROP_DIRECTION, 0); // BCM 20 LOW - reverse direction (inverted)
  std::this_thread::sleep_for(std::chrono::milliseconds(duration_ms));
  gpio_interface_->write_gpio(END_EFFECTOR_DROP_ON, 0);       // BCM 12 LOW - disable
  gpio_interface_->write_gpio(END_EFFECTOR_DROP_DIRECTION, 0); // BCM 20 LOW - clear direction
  RCLCPP_INFO(logger_, "[GPIO] END EFFECTOR DROP BELT EJECT COMPLETE");
}

// ==================================================================================
// LED STATUS INDICATORS
// ==================================================================================

void GPIOControlFunctions::green_led_on()
{
  gpio_interface_->write_gpio(GREEN_LED_PIN, LED_ON);
  gpio_interface_->write_gpio(RED_LED_PIN, LED_OFF);
  log_gpio_operation("Green LED ON", GREEN_LED_PIN, LED_ON);
}

void GPIOControlFunctions::red_led_on()
{
  gpio_interface_->write_gpio(RED_LED_PIN, LED_ON);
  gpio_interface_->write_gpio(GREEN_LED_PIN, LED_OFF);
  log_gpio_operation("Red LED ON", RED_LED_PIN, LED_ON);
}

void GPIOControlFunctions::blink_led_on()
{
  gpio_interface_->write_gpio(RED_LED_PIN, LED_ON);
  gpio_interface_->write_gpio(GREEN_LED_PIN, LED_OFF);
  std::this_thread::sleep_for(std::chrono::seconds(1));

  gpio_interface_->write_gpio(RED_LED_PIN, LED_ON);
  std::this_thread::sleep_for(std::chrono::seconds(1));

  gpio_interface_->write_gpio(RED_LED_PIN, LED_OFF);
  std::this_thread::sleep_for(std::chrono::seconds(1));

  gpio_interface_->write_gpio(RED_LED_PIN, LED_ON);
  log_gpio_operation("Red LED Blink", RED_LED_PIN, LED_ON);
}

void GPIOControlFunctions::camera_led_control(bool direction)
{
  if (direction)
  {
    gpio_interface_->write_gpio(CAMERA_LED_PIN, 1);
    log_gpio_operation("Camera LED ON", CAMERA_LED_PIN, 1);
  }
  else
  {
    gpio_interface_->write_gpio(CAMERA_LED_PIN, 0);
    log_gpio_operation("Camera LED OFF", CAMERA_LED_PIN, 0);
  }
}

// ==================================================================================
// COTTON COLLECTION SYSTEM
// ==================================================================================

void GPIOControlFunctions::cotton_drop_shutter()
{
  RCLCPP_DEBUG(logger_, "[GPIO] Activating cotton drop shutter (servo)");

  // Open the shutter
  gpio_interface_->set_servo_pulsewidth(COTTON_DROP_SERVO_PIN, 500);
  std::this_thread::sleep_for(
    std::chrono::milliseconds(static_cast<int>(MIN_SLEEP_TIME_FOR_COTTON_DROP * 1000)));

  // Close the shutter
  gpio_interface_->set_servo_pulsewidth(COTTON_DROP_SERVO_PIN, 1420);

  RCLCPP_DEBUG(logger_, "[GPIO] Cotton drop shutter cycle complete");
}

void GPIOControlFunctions::cotton_drop_solenoid_shutter()
{
  RCLCPP_DEBUG(logger_, "[GPIO] 💨 Activating cotton drop solenoid (compressor push method)");

  // Ensure pin is output mode
  gpio_interface_->set_mode(COMPRESSOR_PIN, 1);  // 1 = OUTPUT

  // Activate solenoid (opens compressor valve)
  gpio_interface_->write_gpio(COMPRESSOR_PIN, 1);
  log_gpio_operation("Solenoid Shutter ON", COMPRESSOR_PIN, 1);

  // Wait for cotton to be pushed out
  std::this_thread::sleep_for(
    std::chrono::milliseconds(static_cast<int>(MIN_SLEEP_TIME_FOR_COTTON_DROP * 1000)));

  // Deactivate solenoid (closes compressor valve)
  gpio_interface_->write_gpio(COMPRESSOR_PIN, 0);
  log_gpio_operation("Solenoid Shutter OFF", COMPRESSOR_PIN, 0);

  RCLCPP_DEBUG(logger_, "[GPIO] ✅ Cotton ejected via compressor");
}

// ==================================================================================
// USER INPUT SWITCHES
// ==================================================================================

bool GPIOControlFunctions::start_switch_status()
{
  int switch_state = gpio_interface_->read_gpio(START_SWITCH);

  if (switch_state == 1)
  {
    start_switch_pulses_++;

    // Require multiple consecutive readings to debounce
    if (start_switch_pulses_ > 5)
    {
      RCLCPP_INFO(logger_, "[GPIO] Start switch activated");
      start_switch_pulses_ = 0;  // Reset counter
      return true;
    }
  }
  else
  {
    start_switch_pulses_ = 0;  // Reset if switch released
  }

  return false;
}

bool GPIOControlFunctions::shutdown_switch_status()
{
  int switch_state = gpio_interface_->read_gpio(SHUTDOWN_SWITCH);

  if (switch_state == 1)
  {
    shutdown_switch_pulses_++;

    // Require multiple consecutive readings to debounce
    if (shutdown_switch_pulses_ > 5)
    {
      RCLCPP_INFO(logger_, "[GPIO] Shutdown switch activated");
      shutdown_switch_pulses_ = 0;  // Reset counter
      return true;
    }
  }
  else
  {
    shutdown_switch_pulses_ = 0;  // Reset if switch released
  }

  return false;
}

// ==================================================================================
// SERVO CONTROL
// ==================================================================================

void GPIOControlFunctions::servo_control(unsigned int pwm)
{
  // Generic servo control - use COTTON_DROP_SERVO_PIN as default
  if (!gpio_interface_->set_servo_pulsewidth(COTTON_DROP_SERVO_PIN, pwm))
  {
    RCLCPP_ERROR(logger_, "[GPIO] Failed to set servo PWM on pin %d", COTTON_DROP_SERVO_PIN);
  }
  else
  {
    log_gpio_operation("Servo PWM", COTTON_DROP_SERVO_PIN, pwm);
  }
}

void GPIOControlFunctions::transport_shutter()
{
  RCLCPP_INFO(logger_, "[GPIO] Activating transport shutter");

  gpio_interface_->set_servo_pulsewidth(TRANSPORT_SERVO_PIN, 650);
  std::this_thread::sleep_for(std::chrono::seconds(5));

  gpio_interface_->set_servo_pulsewidth(TRANSPORT_SERVO_PIN, 1500);

  RCLCPP_INFO(logger_, "[GPIO] Transport shutter cycle complete");
}

std::chrono::steady_clock::time_point GPIOControlFunctions::get_current_time() const
{
  return std::chrono::steady_clock::now();
}



void GPIOControlFunctions::compressor_control(bool state) {
  if (!gpio_interface_) {
    RCLCPP_ERROR(logger_, "[Compressor] GPIO interface not initialized");
    return;
  }

  if (state) {
    RCLCPP_INFO(logger_, "[Compressor] Turning ON compressor (BCM GPIO 18 = Physical Pin 12)");
    gpio_interface_->write_gpio(COMPRESSOR_PIN, 1);
  } else {
    RCLCPP_INFO(logger_, "[Compressor] Turning OFF compressor (BCM GPIO 18 = Physical Pin 12)");
    gpio_interface_->write_gpio(COMPRESSOR_PIN, 0);
  }
}

GPIOControlFunctions::GPIOStats GPIOControlFunctions::get_stats() const {
  GPIOStats stats;
  if (gpio_interface_) {
    stats.write_failures = gpio_interface_->get_write_failure_count();
    stats.reconnect_count = gpio_interface_->get_reconnect_count();
    stats.reconnect_failures = gpio_interface_->get_reconnect_failure_count();
  }
  return stats;
}

}  // namespace motor_control_ros2
