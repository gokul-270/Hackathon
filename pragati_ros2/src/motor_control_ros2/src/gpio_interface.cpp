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
 * @file gpio_interface.cpp
 * @brief Simplified GPIO interface implementation
 * @details Uses pigpiod_if2 for hardware, simulation mode for offline testing.
 *          Supports: Compressor (GPIO 18), End Effector control.
 * @date November 2025 - Simplified for field deployment
 */

#include "motor_control_ros2/gpio_interface.hpp"
#include <rclcpp/rclcpp.hpp>
#include <iostream>
#include <sstream>
#include <thread>
#include <chrono>

// Use pigpiod_if2 library for GPIO access (requires pigpiod daemon running)
#ifdef USE_PIGPIOD_IF
#include <pigpiod_if2.h>
#endif

namespace motor_control_ros2
{

GPIOInterface::GPIOInterface(bool simulation_mode)
  : initialized_(false), simulation_mode_(simulation_mode), pi_handle_(-1), last_error_("")
{
  if (simulation_mode_) {
    RCLCPP_INFO(rclcpp::get_logger("motor_control"),
      "GPIO: Simulation mode enabled - all operations will succeed without hardware");
  }
}

GPIOInterface::~GPIOInterface()
{
  cleanup();
}

bool GPIOInterface::initialize()
{
  if (initialized_) {
    return true;
  }

  // Simulation mode - no hardware initialization needed
  if (simulation_mode_) {
    initialized_ = true;
    RCLCPP_INFO(rclcpp::get_logger("motor_control"), "GPIO: Initialized in simulation mode");
    return true;
  }

  // Hardware mode - connect to pigpiod daemon
#ifdef USE_PIGPIOD_IF
  pi_handle_ = pigpio_start(NULL, NULL);
  if (pi_handle_ < 0) {
    std::ostringstream oss;
    oss << "Failed to connect to pigpiod daemon (error " << pi_handle_ << "). ";
    oss << "Ensure pigpiod is running: sudo pigpiod";
    last_error_ = oss.str();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "GPIO Error: %s", last_error_.c_str());
    return false;
  }

  initialized_ = true;
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "GPIO: Connected to pigpiod daemon (handle=%d)", pi_handle_);
  return true;
#else
  // Compiled without pigpiod_if2 support - fall back to simulation
  last_error_ = "GPIO hardware support not compiled in (USE_PIGPIOD_IF not defined)";
  RCLCPP_WARN(rclcpp::get_logger("motor_control"), "GPIO Warning: %s", last_error_.c_str());
  RCLCPP_WARN(rclcpp::get_logger("motor_control"), "GPIO: Running in simulation mode");
  simulation_mode_ = true;
  initialized_ = true;
  return true;
#endif
}

void GPIOInterface::cleanup()
{
  if (!initialized_) {
    return;
  }

#ifdef USE_PIGPIOD_IF
  if (!simulation_mode_ && pi_handle_ >= 0) {
    pigpio_stop(pi_handle_);
    RCLCPP_INFO(rclcpp::get_logger("motor_control"), "GPIO: Disconnected from pigpiod");
  }
#endif

  initialized_ = false;
  pi_handle_ = -1;
}

int GPIOInterface::read_gpio([[maybe_unused]] int gpio_pin)
{
  if (!initialized_) {
    last_error_ = "GPIO not initialized";
    return -1;
  }

  // Simulation mode - return 0 (pin low)
  if (simulation_mode_) {
    return 0;
  }

#ifdef USE_PIGPIOD_IF
  int value = gpio_read(pi_handle_, gpio_pin);
  if (value < 0) {
    std::ostringstream oss;
    oss << "Failed to read GPIO pin " << gpio_pin << " (error " << value << ")";
    last_error_ = oss.str();
    return -1;
  }
  return value;
#else
  return 0;
#endif
}

bool GPIOInterface::write_gpio([[maybe_unused]] int gpio_pin, [[maybe_unused]] int value)
{
  if (!initialized_) {
    last_error_ = "GPIO not initialized";
    return false;
  }

  // Simulation mode - succeed silently
  if (simulation_mode_) {
    return true;
  }

#ifdef USE_PIGPIOD_IF
  int result = gpio_write(pi_handle_, gpio_pin, value);
  if (result < 0) {
    ++write_failure_count_;
    std::ostringstream oss;
    oss << "Failed to write GPIO pin " << gpio_pin << " (error " << result << ")";
    last_error_ = oss.str();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "GPIO Error: %s (failures: %d)", last_error_.c_str(), write_failure_count_);

    // Mark that reconnection may be needed (pigpiod may have restarted)
    needs_reconnect_ = true;

    // Attempt auto-recovery
    if (reconnect()) {
      // Retry the write after successful reconnection
      result = gpio_write(pi_handle_, gpio_pin, value);
      if (result >= 0) {
        RCLCPP_INFO(rclcpp::get_logger("motor_control"),
          "GPIO: Write succeeded after reconnection (pin=%d, value=%d)", gpio_pin, value);
        return true;
      }
    }
    return false;
  }
  return true;
#else
  return true;
#endif
}

bool GPIOInterface::reconnect()
{
  if (simulation_mode_) {
    return true;  // Nothing to reconnect in simulation
  }

#ifdef USE_PIGPIOD_IF
  RCLCPP_INFO(rclcpp::get_logger("motor_control"), "GPIO: Attempting reconnection to pigpiod...");

  // First, cleanup existing connection
  if (pi_handle_ >= 0) {
    pigpio_stop(pi_handle_);
    pi_handle_ = -1;
  }
  initialized_ = false;

  // Exponential backoff retry
  int backoff_ms = INITIAL_BACKOFF_MS;

  for (int attempt = 1; attempt <= MAX_RECONNECT_ATTEMPTS; ++attempt) {
    RCLCPP_INFO(rclcpp::get_logger("motor_control"),
      "GPIO: Reconnect attempt %d/%d (waiting %dms)...", attempt, MAX_RECONNECT_ATTEMPTS, backoff_ms);

    // Wait before retry
    std::this_thread::sleep_for(std::chrono::milliseconds(backoff_ms));

    pi_handle_ = pigpio_start(NULL, NULL);
    if (pi_handle_ >= 0) {
      initialized_ = true;
      needs_reconnect_ = false;
      ++reconnect_count_;
      RCLCPP_INFO(rclcpp::get_logger("motor_control"),
        "GPIO: Reconnection successful on attempt %d (handle=%d, total reconnects: %d)",
        attempt, pi_handle_, reconnect_count_);

      // Re-setup GPIO pins after reconnection
      // Note: Caller should re-call setup_gpio_pins() if needed
      return true;
    }

    backoff_ms *= 2;  // Exponential backoff
  }

  ++reconnect_failure_count_;
  std::ostringstream oss;
  oss << "GPIO reconnection failed after " << MAX_RECONNECT_ATTEMPTS << " attempts "
      << "(total failures: " << reconnect_failure_count_ << ")";
  last_error_ = oss.str();
  RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "GPIO Error: %s", last_error_.c_str());
  return false;
#else
  return false;
#endif
}

bool GPIOInterface::set_mode([[maybe_unused]] int gpio_pin, [[maybe_unused]] int mode)
{
  if (!initialized_) {
    last_error_ = "GPIO not initialized";
    return false;
  }

  // Simulation mode - succeed silently
  if (simulation_mode_) {
    return true;
  }

#ifdef USE_PIGPIOD_IF
  int result = ::set_mode(pi_handle_, gpio_pin, mode);
  if (result < 0) {
    std::ostringstream oss;
    oss << "Failed to set GPIO pin " << gpio_pin << " mode (error " << result << ")";
    last_error_ = oss.str();
    return false;
  }
  return true;
#else
  return true;
#endif
}

bool GPIOInterface::set_servo_pulsewidth([[maybe_unused]] int gpio_pin, [[maybe_unused]] int pulsewidth)
{
  if (!initialized_) {
    last_error_ = "GPIO not initialized";
    return false;
  }

  // Simulation mode - succeed silently
  if (simulation_mode_) {
    return true;
  }

#ifdef USE_PIGPIOD_IF
  int result = ::set_servo_pulsewidth(pi_handle_, gpio_pin, pulsewidth);
  if (result < 0) {
    std::ostringstream oss;
    oss << "Failed to set servo pulsewidth on GPIO pin " << gpio_pin << " (error " << result << ")";
    last_error_ = oss.str();
    return false;
  }
  return true;
#else
  return true;
#endif
}

}  // namespace motor_control_ros2
