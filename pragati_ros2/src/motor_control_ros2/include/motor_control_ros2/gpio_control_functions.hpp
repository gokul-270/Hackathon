/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http:  // www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @file gpio_control_functions.hpp
 * @brief GPIO control functions for Pragati cotton picking robot (migrated from ROS-1)
 * @author Migrated from ROS-1 yanthra_move implementation
 * @date September 2025
 *
 * This file contains all the GPIO control functions for:
 * - Vacuum pump control
 * - End effector motor control
 * - LED status indicators
 * - Camera illumination
 * - Cotton collection system
 * - User input switches
 */

#ifndef ODRIVE_CONTROL_ROS2__GPIO_CONTROL_FUNCTIONS_HPP_
#define ODRIVE_CONTROL_ROS2__GPIO_CONTROL_FUNCTIONS_HPP_

#include <string>
#include <atomic>

#include "motor_control_ros2/gpio_interface.hpp"
#include "rclcpp/rclcpp.hpp"
#include <memory>
#include <chrono>

namespace motor_control_ros2
{


/**
 * @class GPIOControlFunctions
 * @brief High-level GPIO control functions for Pragati robot hardware
 *
 * This class provides the same GPIO control interface as the ROS-1 yanthra_move
 * implementation, including vacuum pump, end effector, LEDs, and sensors.
 */
class GPIOControlFunctions
{
public:
  /**
   * @brief Constructor
   * @param logger ROS2 logger for output
   */
  explicit GPIOControlFunctions(const rclcpp::Logger& logger = rclcpp::get_logger("GPIOControl"));


  /**
   * @brief Destructor
   */
  ~GPIOControlFunctions();

  /**
   * @brief Initialize GPIO control system
   * @return true if successful
   */
  bool initialize();

  /**
   * @brief Cleanup GPIO resources
   */
  void cleanup();

  // ==================================================================================
  // VACUUM SYSTEM CONTROL (from ROS-1)
  // ==================================================================================

  /**
   * @brief Control vacuum pump motor
   * @param vacuum_pump_state true = on, false = off
   *
   * Equivalent to ROS-1 VacuumPump() function
   */
  void vacuum_pump_control(bool vacuum_pump_state);

  // ==================================================================================
  // END EFFECTOR CONTROL (from ROS-1)
  // ==================================================================================

  /**
   * @brief Control end effector motor
   * @param end_effector_condition true = on, false = off
   *
   * Equivalent to ROS-1 EndEffector() function
   */
  void end_effector_control(bool end_effector_condition);

  /**
   * @brief Set end effector rotation direction
   * @param direction true = clockwise, false = anti-clockwise
   *
   * Equivalent to ROS-1 SetEndEffectorDirection() function
   */
  void set_end_effector_direction(bool direction);

  /**
   * @brief Control end effector drop conveyor
   * @param conveyor true = drop cotton, false = stop
   *
   * Equivalent to ROS-1 EndEffectorDrop() function
   */
  void end_effector_drop_control(bool conveyor);

  /**
   * @brief Run end effector drop motor (M2) in reverse for active cotton ejection
   * @param duration_ms How long to run M2 in reverse (milliseconds)
   *
   * Sets BCM 12 HIGH (enable) and BCM 20 LOW (DIR = reverse), sleeps for duration_ms,
   * then clears both pins. Blocking call.
   */
  void end_effector_drop_eject(int duration_ms);

  // ==================================================================================
  // LED STATUS INDICATORS (from ROS-1)
  // ==================================================================================

  /**
   * @brief Turn on green status LED (robot ready)
   *
   * Equivalent to ROS-1 green_led_on() function
   */
  void green_led_on();

  /**
   * @brief Turn on red status LED (robot error/busy)
   *
   * Equivalent to ROS-1 red_led_on() function
   */
  void red_led_on();

  /**
   * @brief Blink red LED for attention
   *
   * Equivalent to ROS-1 blink_led_on() function
   */
  void blink_led_on();

  /**
   * @brief Control camera illumination LED
   * @param direction true = on, false = off
   *
   * Equivalent to ROS-1 camera_led() function
   */
  void camera_led_control(bool direction);

  // ==================================================================================
  // COTTON COLLECTION SYSTEM (from ROS-1)
  // ==================================================================================

  /**
   * @brief Operate cotton drop shutter (servo controlled)
   *
   * Equivalent to ROS-1 cotton_drop_shutter() function
   */
  void cotton_drop_shutter();

  /**
   * @brief Operate cotton drop solenoid shutter
   *
   * Equivalent to ROS-1 cotton_drop_solenoid_shutter() function
   */
  void cotton_drop_solenoid_shutter();

  /**
   * @brief Control compressor (on for 2 seconds)
   * @param state true = on, false = off
   *
   * Activates compressor when L5 returns to home position
   */
  void compressor_control(bool state);

  // ==================================================================================
  // USER INPUT SWITCHES (from ROS-1)
  // ==================================================================================

  /**
   * @brief Check start switch status
   * @return true if start switch is pressed for sufficient duration
   *
   * Equivalent to ROS-1 start_switch_status() function
   */
  bool start_switch_status();

  /**
   * @brief Check shutdown switch status
   * @return true if shutdown switch is pressed for sufficient duration
   *
   * Equivalent to ROS-1 shutdown_switch_status() function
   */
  bool shutdown_switch_status();

  // ==================================================================================
  // SERVO CONTROL (from ROS-1)
  // ==================================================================================

  /**
   * @brief Control servo motor with PWM
   * @param pwm PWM pulse width value
   *
   * Equivalent to ROS-1 servo_control() function
   */
  void servo_control(unsigned int pwm);

  /**
   * @brief Control transport shutter servo
   *
   * Equivalent to ROS-1 transport_shutter() function
   */
  void transport_shutter();

  // ==================================================================================
  // UTILITY FUNCTIONS
  // ==================================================================================

  /**
   * @brief Check if GPIO control system is initialized
   * @return true if initialized
   */
  bool is_initialized() const { return initialized_.load(); }

  /**
   * @brief Get last error message
   * @return Error message string
   */
  std::string get_last_error() const { return last_error_; }

  /**
   * @brief Get GPIO interface statistics
   * @return Struct with failure counts and reconnect stats
   */
  struct GPIOStats {
    int write_failures{0};
    int reconnect_count{0};
    int reconnect_failures{0};
  };
  GPIOStats get_stats() const;

  /**
   * @brief Enable/disable global vacuum motor operation
   * @param enable true to enable vacuum operations
   */
  void set_global_vacuum_enable(bool enable) { global_vacuum_motor_ = enable; }

private:
  // GPIO Interface
  std::unique_ptr<GPIOInterface> gpio_interface_;
  rclcpp::Logger logger_;

  // State tracking
  std::atomic<bool> initialized_{false};
  std::string last_error_;

  // Configuration flags (from ROS-1)
  bool global_vacuum_motor_;
  bool end_effector_enable_;
  bool continous_vacuum_;

  // Pin definitions (from ROS-1 yanthra_move.cpp)
  static constexpr int VACUUM_MOTOR_ON_PIN = 24;
  // End effector pins - updated for Cytron board (BCM 21 enable, BCM 13 direction)
  static constexpr int END_EFFECTOR_ON_PIN = 21;          // Enable
  static constexpr int END_EFFECTOR_DIRECTION_PIN = 13;   // Direction
  static constexpr int END_EFFECTOR_DROP_ON = 12;         // M2 enable (BCM 12)
  static constexpr int END_EFFECTOR_DROP_DIRECTION = 20;  // M2 direction (BCM 20)
  static constexpr int GREEN_LED_PIN = 4;
  static constexpr int RED_LED_PIN = 15;
  // WARNING: COTTON_DROP_SERVO_PIN aliases END_EFFECTOR_DROP_ON (BCM 12). cotton_drop_shutter()
  // is not called in production; if re-enabled, reassign this to the correct servo pin first.
  static constexpr int COTTON_DROP_SERVO_PIN = 12;
  static constexpr int TRANSPORT_SERVO_PIN = 14;
  static constexpr int COMPRESSOR_PIN = 18;  // Compressor flow control (2sec on after L5 home) - BCM GPIO 18 = Physical Pin 12
  static constexpr int CAMERA_LED_PIN = 17;
  static constexpr int SHUTDOWN_SWITCH = 2;
  static constexpr int START_SWITCH = 3;

  // State values (from ROS-1)
  static constexpr int VACUUM_ON = 1;
  static constexpr int VACUUM_OFF = 0;
  static constexpr int END_EFFECTOR_ON = 1;
  static constexpr int END_EFFECTOR_OFF = 0;
  static constexpr int CLOCKWISE = 1;
  static constexpr int ANTICLOCKWISE = 0;
  static constexpr int DROP_EEF = 1;
  static constexpr int STOP_EEF = 0;
  static constexpr int LED_ON = 0;
  static constexpr int LED_OFF = 1;

  // Direction and state tracking
  int end_effector_direction_;
  int start_switch_pulses_;
  int shutdown_switch_pulses_;

  // Timing parameters (from ROS-1)
  static constexpr float MIN_SLEEP_TIME_FOR_COTTON_DROP = 0.8f;
  static constexpr float MIN_SLEEP_TIME_FOR_COTTON_DROP_FROM_EEF = 0.5f;

  // Helper functions
  bool setup_gpio_pins();
  void log_gpio_operation(const std::string& operation, int pin, int value);
  std::chrono::steady_clock::time_point get_current_time() const;
};  // class GPIOControlFunctions

}  // namespace motor_control_ros2

#endif  // ODRIVE_CONTROL_ROS2__GPIO_CONTROL_FUNCTIONS_HPP_
