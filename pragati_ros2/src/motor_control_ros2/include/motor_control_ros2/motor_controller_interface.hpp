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

#ifndef MOTOR_CONTROL_ROS2__MOTOR_CONTROLLER_INTERFACE_HPP_
#define MOTOR_CONTROL_ROS2__MOTOR_CONTROLLER_INTERFACE_HPP_

#pragma once

#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/motor_types.hpp"

namespace motor_control_ros2
{

/**
 * @brief PID parameters for motor controller tuning
 *
 * MG6010 protocol uses uint8_t values (0-255) for all gains.
 * This struct is defined at the interface level so that higher-level
 * code (services, tuning dashboards) can work with PID parameters
 * without depending on protocol-specific headers.
 */
struct PIDParams
{
  uint8_t angle_kp = 0;
  uint8_t angle_ki = 0;
  uint8_t speed_kp = 0;
  uint8_t speed_ki = 0;
  uint8_t current_kp = 0;
  uint8_t current_ki = 0;
};

/**
 * @brief Full aggregated motor state from all status registers
 *
 * Combines data from STATUS_1, STATUS_2, STATUS_3, multi-turn angle,
 * and single-turn angle reads into a single snapshot. Fields that
 * could not be read retain their default (zero) values; check
 * 'valid' to know if the core data (STATUS_2) succeeded.
 */
struct FullMotorState
{
  double temperature_c = 0.0;
  double voltage_v = 0.0;
  double torque_current_a = 0.0;
  double speed_dps = 0.0;
  uint16_t encoder_position = 0;
  double multi_turn_deg = 0.0;
  double single_turn_deg = 0.0;
  double phase_current_a = 0.0;
  double phase_current_b = 0.0;
  double phase_current_c = 0.0;
  uint8_t error_flags = 0;
  bool valid = false;
};

class MotorControllerInterface
{
public:
  virtual ~MotorControllerInterface() = default;

  /**
   * @brief Initialize motor controller
   * @param config Motor configuration
   * @param can_interface Shared CAN interface
   * @return true if successful
   */
  virtual bool initialize(
    const MotorConfiguration & config,
    std::shared_ptr<CANInterface> can_interface) = 0;

  /**
   * @brief Configure motor parameters
   * @param config Updated configuration
   * @return true if successful
   */
  virtual bool configure(const MotorConfiguration & config) = 0;

  /**
   * @brief Enable/disable motor
   * @param enable true to enable, false to disable
   * @return true if successful
   */
  virtual bool set_enabled(bool enable) = 0;

  /**
   * @brief Set target position (joint space)
   * @param position Target position in radians
   * @param velocity Feed-forward velocity in rad/s (optional)
   * @param torque Feed-forward torque in Nm (optional)
   * @return true if successful
   */
  virtual bool set_position(double position, double velocity = 0.0, double torque = 0.0) = 0;

  /**
   * @brief Set target velocity
   * @param velocity Target velocity in rad/s
   * @param torque Feed-forward torque in Nm (optional)
   * @return true if successful
   */
  virtual bool set_velocity(double velocity, double torque = 0.0) = 0;

  /**
   * @brief Set target torque/current
   * @param torque Target torque in Nm (or current in A for current control)
   * @return true if successful
   */
  virtual bool set_torque(double torque) = 0;

  /**
   * @brief Get current position (joint space)
   * @return Current position in radians
   */
  virtual double get_position() = 0;

  /**
   * @brief Get current velocity (joint space)
   * @return Current velocity in rad/s
   */
  virtual double get_velocity() = 0;

  /**
   * @brief Get current torque/effort
   * @return Current torque in Nm (or current in A)
   */
  virtual double get_torque() = 0;

  /**
   * @brief Perform motor homing sequence
   * @param config Homing configuration (optional, uses default if null)
   * @return true if homing successful
   */
  virtual bool home_motor(const HomingConfig * config = nullptr) = 0;

  /**
   * @brief Check if homing is complete
   * @return true if motor has been homed
   */
  virtual bool is_homed() const = 0;

  /**
   * @brief Get motor status
   * @return Current motor status
   */
  virtual MotorStatus get_status() = 0;

  /**
   * @brief Handle emergency stop
   * @return true if emergency stop handled successfully
   */
  virtual bool emergency_stop() = 0;

  /**
   * @brief Stop motor (exit position control, reduce power)
   * @return true if stop command sent successfully
   */
  virtual bool stop() = 0;

  /**
   * @brief Clear motor errors
   * @return true if errors cleared successfully
   */
  virtual bool clear_errors() = 0;

  /**
   * @brief Perform motor calibration (if needed)
   * @return true if calibration successful
   */
  virtual bool calibrate_motor() = 0;

  /**
   * @brief Perform encoder calibration (if needed)
   * @return true if calibration successful
   */
  virtual bool calibrate_encoder() = 0;

  /**
   * @brief Check if motor needs calibration
   * @return true if calibration is required
   */
  virtual bool needs_calibration() const = 0;

  /**
   * @brief Get motor configuration
   * @return Current motor configuration
   */
  virtual MotorConfiguration get_configuration() const = 0;

  /**
   * @brief Get enhanced error information
   * @return Current error information with recovery suggestions
   */
  virtual const ErrorFramework::ErrorInfo & get_error_info() const = 0;

  /**
   * @brief Get error history
   * @return Vector of historical error information
   */
  virtual std::vector<ErrorFramework::ErrorInfo> get_error_history() const = 0;

  /**
   * @brief Attempt error recovery
   * @return Recovery result with actions taken
   */
  virtual ErrorFramework::RecoveryResult attempt_error_recovery() = 0;

  /**
   * @brief Set custom error handler
   * @param handler Custom error handler function
   */
  virtual void set_error_handler(
    std::function<void(const ErrorFramework::ErrorInfo &)> handler) = 0;

  // ============================================================================
  // PID Parameter Access
  // ============================================================================

  /**
   * @brief Read current PID parameters from motor
   * @return PIDParams if successful, std::nullopt on failure
   */
  virtual std::optional<PIDParams> readPID() = 0;

  /**
   * @brief Set PID parameters in motor RAM (lost on power cycle)
   * @param params PID parameters to set
   * @return true if successful
   */
  virtual bool setPID(const PIDParams & params) = 0;

  /**
   * @brief Write PID parameters to motor ROM (persists across power cycles)
   * @param params PID parameters to write
   * @return true if successful
   */
  virtual bool writePIDToROM(const PIDParams & params) = 0;

  // ============================================================================
  // Motor Config Bridge Methods
  // ============================================================================
  // These expose protocol-level operations that have no ROS2 service wrappers
  // yet. Default implementations return false / invalid so that controllers
  // that do not support a particular operation are safe to call.

  // -- Max torque current ratio -------------------------------------------------
  virtual bool readMaxTorqueCurrent(uint16_t & ratio) { (void)ratio; return false; }
  virtual bool writeMaxTorqueCurrentRAM(uint16_t ratio) { (void)ratio; return false; }

  // -- Acceleration -------------------------------------------------------------
  virtual bool readAcceleration(double & rad_per_sec2) { (void)rad_per_sec2; return false; }
  virtual bool setAcceleration(double rad_per_sec2) { (void)rad_per_sec2; return false; }

  // -- Encoder ------------------------------------------------------------------
  virtual bool readEncoder(
    uint16_t & encoder_value, uint16_t & encoder_raw, uint16_t & encoder_offset)
  {
    (void)encoder_value; (void)encoder_raw; (void)encoder_offset;
    return false;
  }
  virtual bool writeEncoderOffsetToROM(uint16_t offset) { (void)offset; return false; }
  virtual bool setCurrentPositionAsZero() { return false; }

  // -- Angle reading (motor-space, no joint conversion) -------------------------
  virtual bool readMultiTurnAngle(double & angle_radians) { (void)angle_radians; return false; }
  virtual bool readSingleTurnAngle(double & angle_radians) { (void)angle_radians; return false; }

  // -- Error reading ------------------------------------------------------------
  virtual bool readErrors(uint32_t & error_flags) { (void)error_flags; return false; }

  // -- Full aggregated state ----------------------------------------------------
  virtual FullMotorState readFullState() { return FullMotorState{}; }

  // -- Direct motor control (8 command modes) -----------------------------------
  // All angles in degrees, speeds in degrees-per-second (motor space).
  // Implementations convert to protocol units (radians, rad/s) internally.
  virtual bool torqueClosedLoop(double amps) { (void)amps; return false; }
  virtual bool speedClosedLoop(double dps) { (void)dps; return false; }
  virtual bool multiLoopAngle1(double degrees) { (void)degrees; return false; }
  virtual bool multiLoopAngle2(double degrees, double max_speed_dps)
  {
    (void)degrees; (void)max_speed_dps;
    return false;
  }
  virtual bool singleLoopAngle1(double degrees, uint8_t direction)
  {
    (void)degrees; (void)direction;
    return false;
  }
  virtual bool singleLoopAngle2(double degrees, double max_speed_dps, uint8_t direction)
  {
    (void)degrees; (void)max_speed_dps; (void)direction;
    return false;
  }
  virtual bool incrementAngle1(double degrees) { (void)degrees; return false; }
  virtual bool incrementAngle2(double degrees, double max_speed_dps)
  {
    (void)degrees; (void)max_speed_dps;
    return false;
  }
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__MOTOR_CONTROLLER_INTERFACE_HPP_
