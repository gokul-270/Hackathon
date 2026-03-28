/*
 * Copyright (c) 2024 Pragati Robotics
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

#ifndef ODRIVE_CONTROL_ROS2__MG6010_CONTROLLER_HPP_
#define ODRIVE_CONTROL_ROS2__MG6010_CONTROLLER_HPP_

#include "motor_control_ros2/motor_abstraction.hpp"
#include "motor_control_ros2/mg6010_protocol.hpp"
#include "motor_control_ros2/mg6010_can_interface.hpp"

#include <memory>
#include <string>
#include <vector>
#include <mutex>
#include <chrono>

namespace motor_control_ros2
{

/**
 * @brief Motor controller implementation for MG6010-i6 motors
 *
 * This class implements the MotorControllerInterface using the MG6010Protocol
 * for low-level CAN communication. It provides the bridge between the generic
 * motor abstraction layer and MG6010-specific protocol implementation.
 *
 * Key features:
 * - Joint-space to motor-space coordinate transformations
 * - Safety limit enforcement
 * - State caching and management
 * - Error handling with recovery
 * - Thread-safe operation
 */
class MG6010Controller : public MotorControllerInterface
{
public:
  MG6010Controller();
  virtual ~MG6010Controller();

  // MotorControllerInterface implementation
  bool initialize(
    const MotorConfiguration & config,
    std::shared_ptr<CANInterface> can_interface) override;

  bool configure(const MotorConfiguration & config) override;
  bool set_enabled(bool enable) override;

  bool set_position(double position, double velocity = 0.0, double torque = 0.0) override;
  bool set_velocity(double velocity, double torque = 0.0) override;
  bool set_torque(double torque) override;

  double get_position() override;
  double get_velocity() override;
  double get_torque() override;

  bool home_motor(const HomingConfig * config = nullptr) override;
  bool is_homed() const override;

  MotorStatus get_status() override;
  /**
   * @brief Get motor status with reduced CAN retries (non-virtual overload).
   *
   * Used by absence-detection re-probes (D4, task 4.6) to keep bus quiet.
   * @param max_retries  Maximum CAN retries per sub-command (≤0 = default).
   */
  MotorStatus get_status(int max_retries);
  bool emergency_stop() override;
  bool stop();  // Send motor_stop() command (exit position control, reduce power)
  bool clear_errors() override;

  bool calibrate_motor() override;
  bool calibrate_encoder() override;
  bool needs_calibration() const override;

  MotorConfiguration get_configuration() const override;

  // Error handling
  const ErrorFramework::ErrorInfo & get_error_info() const override;
  std::vector<ErrorFramework::ErrorInfo> get_error_history() const override;
  ErrorFramework::RecoveryResult attempt_error_recovery() override;
  void set_error_handler(
    std::function<void(const ErrorFramework::ErrorInfo &)> handler) override;

  // PID parameter access
  std::optional<PIDParams> readPID() override;
  bool setPID(const PIDParams & params) override;
  bool writePIDToROM(const PIDParams & params) override;

  // Motor config bridge methods
  bool readMaxTorqueCurrent(uint16_t & ratio) override;
  bool writeMaxTorqueCurrentRAM(uint16_t ratio) override;
  bool readAcceleration(double & rad_per_sec2) override;
  bool setAcceleration(double rad_per_sec2) override;
  bool readEncoder(
    uint16_t & encoder_value, uint16_t & encoder_raw, uint16_t & encoder_offset) override;
  bool writeEncoderOffsetToROM(uint16_t offset) override;
  bool setCurrentPositionAsZero() override;
  bool readMultiTurnAngle(double & angle_radians) override;
  bool readSingleTurnAngle(double & angle_radians) override;
  bool readErrors(uint32_t & error_flags) override;
  FullMotorState readFullState() override;
  bool torqueClosedLoop(double amps) override;
  bool speedClosedLoop(double dps) override;
  bool multiLoopAngle1(double degrees) override;
  bool multiLoopAngle2(double degrees, double max_speed_dps) override;
  bool singleLoopAngle1(double degrees, uint8_t direction) override;
  bool singleLoopAngle2(double degrees, double max_speed_dps, uint8_t direction) override;
  bool incrementAngle1(double degrees) override;
  bool incrementAngle2(double degrees, double max_speed_dps) override;

private:
  // Configuration and protocol
  MotorConfiguration config_;
  std::shared_ptr<MG6010Protocol> protocol_;
  std::shared_ptr<CANInterface> can_interface_;

  // State flags
  bool initialized_;
  bool homed_;
  bool enabled_;
  bool calibrated_;

  // Cached state (joint space)
  double current_position_;       // radians
  double current_velocity_;       // rad/s
  // NOTE: For MG6010 we currently treat this as motor current feedback (A).
  // The abstraction layer allows either torque (Nm) or current (A) depending on motor type.
  double current_torque_;         // A (torque current)
  double cached_temperature_c_{0.0};  // Last known motor temperature (°C), updated by get_status()
  std::chrono::steady_clock::time_point last_state_update_;
  bool last_state_update_success_{false};
  std::chrono::steady_clock::duration min_state_update_period_{std::chrono::milliseconds(5)};

  // Error handling
  ErrorFramework::ErrorInfo current_error_;
  std::vector<ErrorFramework::ErrorInfo> error_history_;
  std::function<void(const ErrorFramework::ErrorInfo &)> error_handler_;

  // Auto-recovery state tracking
  std::chrono::steady_clock::time_point last_recovery_attempt_;
  int consecutive_recovery_failures_{0};
  bool auto_recovery_disabled_{false};  // Disabled after too many failures
  std::chrono::steady_clock::time_point auto_recovery_disabled_time_;  // When auto-recovery was disabled (for re-enable cooldown, task 2.4)

  // Background recovery state machine (tasks 2.1-2.3)
  // Recovery is driven by a timer in the node layer, advancing through steps
  // without holding state_mutex_ during waits.
  bool recovery_needed_{false};          // Flag set by get_status() when error detected
  uint32_t recovery_error_flags_{0};     // Error flags that triggered recovery
  enum class RecoveryStep {
    IDLE,           // No recovery in progress
    CLEAR_ERRORS,   // Step 1: send clear_errors command
    WAIT_CLEAR,     // Wait after clear_errors (100ms)
    MOTOR_OFF,      // Step 2: send motor_off command
    WAIT_OFF,       // Wait after motor_off (200ms)
    MOTOR_ON,       // Step 3: send motor_on command
    WAIT_ON,        // Wait after motor_on (200ms)
    VERIFY,         // Step 4: read status and check error flags
    COOLDOWN        // Waiting for next retry after failure
  };
  RecoveryStep recovery_step_{RecoveryStep::IDLE};
  int recovery_attempt_{0};              // Current attempt number (1-based)
  int recovery_retry_delay_ms_{500};     // Current backoff delay
  std::chrono::steady_clock::time_point recovery_step_time_;  // When current step started

  // Auto-recovery re-enable cooldown (task 2.4)
  static constexpr auto AUTO_RECOVERY_REENABLE_COOLDOWN = std::chrono::seconds(60);

  // Recovery statistics
  uint32_t total_recovery_attempts_{0};
  uint32_t successful_recoveries_{0};
  uint32_t failed_recoveries_{0};

  // Stall detection state (tasks 4.4-4.5)
  bool stall_detected_{false};                  // True when stall protection is active
  double stall_current_threshold_{0.8};         // Fraction of rated current (80%)
  double stall_position_threshold_deg_{0.5};    // Position change threshold (degrees)
  int stall_time_threshold_ms_{500};            // Duration before stall triggers (ms)
  double stall_track_current_{0.0};             // Current sample at stall monitor start
  double stall_track_position_{0.0};            // Position at stall monitor start (joint-space)
  std::chrono::steady_clock::time_point stall_monitor_start_;  // When high-current was first detected
  bool stall_monitoring_{false};                // True when monitoring a potential stall

  // Thermal derating state (tasks 3.2-3.3)
  double derating_onset_temp_{65.0};            // °C — derating begins
  double thermal_limit_temp_{85.0};             // °C — zero current
  double min_derating_pct_{0.0};                // Minimum current fraction at limit (0 = full shutoff)
  double thermal_hysteresis_{5.0};              // °C below onset for recovery re-enable
  double current_derating_factor_{1.0};         // Current multiplier [0..1]
  bool thermal_protection_active_{false};       // True when temp >= thermal_limit

  // Recovery constants
  static constexpr int MAX_RECOVERY_RETRIES = 3;
  static constexpr int MAX_CONSECUTIVE_FAILURES = 3;
  static constexpr auto RECOVERY_COOLDOWN = std::chrono::seconds(10);
  static constexpr auto TEMPERATURE_RECOVERY_COOLDOWN = std::chrono::seconds(60);  // Longer cooldown for thermal errors

  // Temperature error tracking
  std::chrono::steady_clock::time_point last_temperature_error_time_;
  bool temperature_cooldown_logged_{false};  // Avoid log spam during thermal cooldown

  // Thread safety
  mutable std::mutex state_mutex_;

  // ============================================================================
  // Coordinate Transformation
  // ============================================================================

  /**
   * @brief Convert joint space position to motor space
   * @param joint_pos Position in radians (joint space)
   * @return Position in radians (motor space)
   */
  double joint_to_motor_position(double joint_pos) const;

  /**
   * @brief Convert motor space position to joint space
   * @param motor_pos Position in radians (motor space)
   * @return Position in radians (joint space)
   */
  double motor_to_joint_position(double motor_pos) const;

  /**
   * @brief Convert joint space velocity to motor space
   * @param joint_vel Velocity in rad/s (joint space)
   * @return Velocity in rad/s (motor space)
   */
  double joint_to_motor_velocity(double joint_vel) const;

  /**
   * @brief Convert motor space velocity to joint space
   * @param motor_vel Velocity in rad/s (motor space)
   * @return Velocity in rad/s (joint space)
   */
  double motor_to_joint_velocity(double motor_vel) const;

  /**
   * @brief Convert joint space torque to motor space
   * @param joint_torque Torque in Nm (joint space)
   * @return Torque in Nm (motor space)
   */
  double joint_to_motor_torque(double joint_torque) const;

  /**
   * @brief Convert motor space torque to joint space
   * @param motor_torque Torque in Nm (motor space)
   * @return Torque in Nm (joint space)
   */
  double motor_to_joint_torque(double motor_torque) const;

  // ============================================================================
  // State Management
  // ============================================================================

  /**
   * @brief Update cached state from motor
   * @param max_retries  CAN retry override (≤0 = default).
   * @return true if state updated successfully
   */
  bool update_cached_state(int max_retries = -1);

  /**
   * @brief Check if command is within safety limits
   * @param position Position to check (joint space)
   * @param velocity Velocity to check (joint space)
   * @return true if within limits
   */
  bool check_safety_limits(double position, double velocity) const;

  /**
   * @brief Check if position is within limits
   * @param position Position to check (joint space)
   * @return true if within limits
   */
  bool check_position_limits(double position) const;

  /**
   * @brief Check if velocity is within limits
   * @param velocity Velocity to check (joint space)
   * @return true if within limits
   */
  bool check_velocity_limits(double velocity) const;

  // ============================================================================
  // Error Handling
  // ============================================================================

  /**
   * @brief Record error with context
   * @param category Error category
   * @param severity Error severity
   * @param code Error code
   * @param message Error message
   */
  void record_error(
    ErrorFramework::ErrorCategory category,
    ErrorFramework::ErrorSeverity severity,
    uint32_t code,
    const std::string & message);

  /**
   * @brief Clear current error state
   */
  void clear_error();

  /**
    * @brief Attempt automatic motor error recovery
    * Clears errors, reboots motor (OFF->ON), and verifies recovery
    * @param error_flags Current motor error flags
    * @return true if recovery successful
    */
  bool attempt_motor_error_recovery(uint32_t error_flags);

public:
  /**
   * @brief Advance background recovery state machine by one step (task 2.2-2.3).
   *
   * Called from a ROS2 timer at 2s intervals. Each call does ONE non-blocking
   * CAN operation and returns. Holds state_mutex_ only briefly for state
   * read/write — never calls sleep_for.
   *
   * @return true if recovery completed (success or permanent failure)
   */
  bool advanceRecovery();

  /**
   * @brief Check if recovery is currently in progress.
   */
  bool isRecoveryInProgress() const;

  /**
   * @brief Update stall detector with current motor state (task 4.4).
   * Called from control loop. Checks current draw vs position change over time.
   * @param current_amps Current draw in amps
   * @param position_deg Current position in degrees (joint-space)
   */
  void updateStallDetector(double current_amps, double position_deg);

  /**
   * @brief Check if motor is in stall protection state (task 4.5).
   */
  bool isStallDetected() const;

  /**
   * @brief Apply thermal derating to a commanded current/torque value (task 3.2).
   * @param commanded_current Raw current command (amps)
   * @param temperature_c Current motor temperature in Celsius
   * @return Derated current value
   */
  double applyThermalDerating(double commanded_current, double temperature_c);

  /**
   * @brief Get current thermal derating factor [0..1].
   */
  double getDeratingFactor() const;

  /**
   * @brief Check if thermal protection is currently active.
   */
  bool isThermalProtectionActive() const;

  /**
   * @brief Configure stall detection parameters (task 4.6).
   */
  void configureStallDetection(double current_threshold, double position_threshold_deg,
                               int time_threshold_ms);

  /**
   * @brief Configure thermal derating parameters (task 3.1).
   */
  void configureThermalDerating(double onset_temp, double limit_temp,
                                double min_pct, double hysteresis);

private:
  /**
    * @brief Check if motor needs attention based on state
    * @param status Motor status to evaluate
    */
  void evaluate_motor_health(MotorStatus & status);
};

}  // namespace motor_control_ros2

#endif  // ODRIVE_CONTROL_ROS2__MG6010_CONTROLLER_HPP_
