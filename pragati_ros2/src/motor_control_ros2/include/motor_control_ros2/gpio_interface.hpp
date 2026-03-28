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

#ifndef MOTOR_CONTROL_ROS2__GPIO_INTERFACE_HPP_
#define MOTOR_CONTROL_ROS2__GPIO_INTERFACE_HPP_

/**
 * @file gpio_interface.hpp
 * @brief Simplified GPIO interface for Pragati robot
 * @details Uses pigpiod_if2 for hardware, simulation mode for offline testing.
 *          Supports: Compressor (GPIO 18), End Effector control.
 * @date November 2025 - Simplified for field deployment
 */

#include <string>

namespace motor_control_ros2
{

/**
 * @class GPIOInterface
 * @brief Simplified GPIO interface for Raspberry Pi
 *
 * Hardware mode: Uses pigpiod daemon via pigpiod_if2 library
 * Simulation mode: All operations succeed silently (for offline development)
 *
 * Supported GPIO pins:
 * - GPIO 18: Compressor control
 * - End effector control pins (as configured)
 */
class GPIOInterface
{
public:
  /**
   * @brief Constructor
   * @param simulation_mode If true, all GPIO operations succeed without hardware
   */
  explicit GPIOInterface(bool simulation_mode = false);

  /**
   * @brief Destructor - cleans up pigpiod connection
   */
  ~GPIOInterface();

  // Disable copy
  GPIOInterface(const GPIOInterface&) = delete;
  GPIOInterface& operator=(const GPIOInterface&) = delete;

  /**
   * @brief Initialize GPIO interface
   * @return true if successful (or in simulation mode), false on hardware error
   */
  bool initialize();

  /**
   * @brief Cleanup GPIO interface
   */
  void cleanup();

  /**
   * @brief Read digital value from GPIO pin
   * @param gpio_pin GPIO pin number (BCM numbering)
   * @return GPIO value (0 or 1), -1 on error
   */
  int read_gpio(int gpio_pin);

  /**
   * @brief Write digital value to GPIO pin
   * @param gpio_pin GPIO pin number (BCM numbering)
   * @param value Value to write (0 or 1)
   * @return true if successful
   */
  bool write_gpio(int gpio_pin, int value);

  /**
   * @brief Set GPIO pin mode
   * @param gpio_pin GPIO pin number (BCM numbering)
   * @param mode Pin mode (0=input, 1=output)
   * @return true if successful
   */
  bool set_mode(int gpio_pin, int mode);

  /**
   * @brief Set servo pulse width (for PWM servo control)
   * @param gpio_pin GPIO pin number (BCM numbering)
   * @param pulsewidth Pulse width in microseconds (500-2500, 0 to disable)
   * @return true if successful
   */
  bool set_servo_pulsewidth(int gpio_pin, int pulsewidth);

  /**
   * @brief Check if GPIO is initialized
   */
  bool is_initialized() const { return initialized_; }

  /**
   * @brief Check if running in simulation mode
   */
  bool is_simulation_mode() const { return simulation_mode_; }

  /**
   * @brief Get last error message
   */
  std::string get_last_error() const { return last_error_; }
  
  /**
   * @brief Attempt to reconnect to pigpiod daemon
   * @return true if reconnection successful
   * 
   * Call this if GPIO operations start failing - pigpiod may have restarted.
   * Uses exponential backoff: 100ms -> 200ms -> 400ms (max 3 attempts)
   */
  bool reconnect();
  
  /**
   * @brief Check if reconnection is needed (connection lost)
   */
  bool needs_reconnect() const { return needs_reconnect_; }
  
  // Statistics accessors
  int get_write_failure_count() const { return write_failure_count_; }
  int get_reconnect_count() const { return reconnect_count_; }
  int get_reconnect_failure_count() const { return reconnect_failure_count_; }

  // GPIO pin modes
  static constexpr int PI_INPUT = 0;
  static constexpr int PI_OUTPUT = 1;

  // Known GPIO pins for Pragati robot
  static constexpr int GPIO_COMPRESSOR = 18;

private:
  bool initialized_;
  bool simulation_mode_;
  int pi_handle_;  // pigpiod connection handle
  std::string last_error_;
  
  // Recovery state
  bool needs_reconnect_{false};
  
  // Statistics
  int write_failure_count_{0};
  int reconnect_count_{0};
  int reconnect_failure_count_{0};
  
  // Recovery constants
  static constexpr int MAX_RECONNECT_ATTEMPTS = 3;
  static constexpr int INITIAL_BACKOFF_MS = 100;
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__GPIO_INTERFACE_HPP_
