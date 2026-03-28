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

#include "motor_control_ros2/mg6010_controller.hpp"

#include <rclcpp/rclcpp.hpp>
#include <cmath>
#include <algorithm>
#include <thread>
#include <chrono>

namespace motor_control_ros2
{

namespace
{
inline bool param_enabled(const std::map<std::string, double> & params, const std::string & key)
{
  auto it = params.find(key);
  return it != params.end() && it->second > 0.5;
}
}  // namespace

// ==============================================================================
// Constructor / Destructor
// ==============================================================================

MG6010Controller::MG6010Controller()
: initialized_(false),
  homed_(false),
  enabled_(false),
  calibrated_(true),  // MG6010 motors don't require calibration
  current_position_(0.0),
  current_velocity_(0.0),
  current_torque_(0.0)
{
  last_state_update_ = std::chrono::steady_clock::now();
}

MG6010Controller::~MG6010Controller()
{
  // Read enabled_ under lock to prevent TOCTOU race (another thread may disable
  // the motor between our check and the emergency_stop call)
  bool was_enabled = false;
  {
    std::lock_guard<std::mutex> lock(state_mutex_);
    was_enabled = enabled_;
  }

  if (was_enabled) {
    try {
      emergency_stop();
    } catch (const std::exception& e) {
      // Destructor must not throw — log best-effort
      RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"),
        "Exception in destructor emergency_stop: %s", e.what());
    } catch (...) {
      RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"),
        "Unknown exception in destructor emergency_stop");
    }
  }
}

// ==============================================================================
// Initialization and Configuration
// ==============================================================================

bool MG6010Controller::initialize(
  const MotorConfiguration & config,
  std::shared_ptr<CANInterface> can_interface)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (initialized_) {
    RCLCPP_WARN(rclcpp::get_logger("motor_control"), "MG6010Controller already initialized for %s", config_.joint_name.c_str());
    return false;
  }

  config_ = config;
  can_interface_ = can_interface;

  // Validate coordinate transform parameters to prevent division by zero (task 1.19)
  if (config_.direction != 1 && config_.direction != -1) {
    record_error(
      ErrorFramework::ErrorCategory::INITIALIZATION,
      ErrorFramework::ErrorSeverity::ERROR,
      1,
      "Invalid direction: " + std::to_string(config_.direction) + " (must be +1 or -1)");
    return false;
  }
  if (config_.transmission_factor <= 0.0) {
    record_error(
      ErrorFramework::ErrorCategory::INITIALIZATION,
      ErrorFramework::ErrorSeverity::ERROR,
      1,
      "Invalid transmission_factor: " + std::to_string(config_.transmission_factor) + " (must be > 0)");
    return false;
  }
  double igr = 6.0;
  if (config_.motor_params.find("internal_gear_ratio") != config_.motor_params.end()) {
    igr = config_.motor_params.at("internal_gear_ratio");
  }
  if (igr <= 0.0) {
    record_error(
      ErrorFramework::ErrorCategory::INITIALIZATION,
      ErrorFramework::ErrorSeverity::ERROR,
      1,
      "Invalid internal_gear_ratio: " + std::to_string(igr) + " (must be > 0)");
    return false;
  }

  // Verify CAN interface is connected
  if (!can_interface_ || !can_interface_->is_connected()) {
    record_error(
      ErrorFramework::ErrorCategory::INITIALIZATION,
      ErrorFramework::ErrorSeverity::ERROR,
      1,
      "CAN interface not connected");
    return false;
  }

  // Create MG6010Protocol instance
  protocol_ = std::make_shared<MG6010Protocol>();

  if (!protocol_) {
    record_error(
      ErrorFramework::ErrorCategory::INITIALIZATION,
      ErrorFramework::ErrorSeverity::ERROR,
      2,
      "Failed to create MG6010Protocol instance");
    return false;
  }

  // Baud rate is configured on the CAN interface (e.g., SocketCAN).
  // The protocol stores the baud rate for bookkeeping only.
  uint32_t baud_rate = 500000;  // Pragati default (CAN interface configured externally)
  if (config_.motor_params.count("baud_rate") > 0) {
    baud_rate = static_cast<uint32_t>(config_.motor_params.at("baud_rate"));
  }

  // Initialize protocol with CAN interface
  if (!protocol_->initialize(can_interface_, config_.can_id, baud_rate)) {
    record_error(
      ErrorFramework::ErrorCategory::INITIALIZATION,
      ErrorFramework::ErrorSeverity::ERROR,
      3,
      "Failed to initialize MG6010Protocol: " + protocol_->get_last_error());
    return false;
  }

  RCLCPP_INFO(rclcpp::get_logger("motor_control"), "MG6010Protocol initialized for CAN ID: 0x%X", static_cast<int>(config_.can_id));

  // ===========================================================================
  // Hardened init sequence (motor-control-hardening change):
  //   motor_stop → clear_errors → read_status → verify_clean → motor_on → verify_active
  //
  // This ensures stale errors from previous sessions are cleared before
  // motor_on, preventing inherited error states from causing failures.
  // ===========================================================================

  // Step 1: motor_stop — exit any active position control, reduce power
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[%s] Init step 1/4: motor_stop (reset motor state)", config_.joint_name.c_str());
  if (!protocol_->motor_stop()) {
    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "[%s] motor_stop failed during init (non-fatal): %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    // Non-fatal: motor may already be stopped
  }

  // Step 2: clear_errors + read_status with retry loop (up to 3 attempts)
  // If error flags persist after clear, retry to handle transient hardware faults.
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[%s] Init step 2/4: clear_errors + read_status (verify clean state)", config_.joint_name.c_str());

  constexpr int kMaxClearRetries = 3;
  bool status_clean = false;
  MG6010Protocol::Status status;

  for (int attempt = 0; attempt < kMaxClearRetries; ++attempt) {
    // clear_errors
    if (!protocol_->clear_errors()) {
      RCLCPP_WARN(rclcpp::get_logger("motor_control"),
        "[%s] clear_errors attempt %d/%d failed: %s",
        config_.joint_name.c_str(), attempt + 1, kMaxClearRetries,
        protocol_->get_last_error().c_str());
      // BLOCKING_SLEEP_OK: init sequence, 10ms before retry — reviewed 2026-03-15
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
      continue;
    }

    // BLOCKING_SLEEP_OK: init sequence, 10ms protocol settle after clear_errors — reviewed 2026-03-15
    std::this_thread::sleep_for(std::chrono::milliseconds(10));

    // read_status to verify clean
    bool status_success = protocol_->read_status(status);
    if (!status_success) {
      RCLCPP_WARN(rclcpp::get_logger("motor_control"),
        "[%s] read_status attempt %d/%d failed: %s",
        config_.joint_name.c_str(), attempt + 1, kMaxClearRetries,
        protocol_->get_last_error().c_str());
      // BLOCKING_SLEEP_OK: init sequence, 10ms before retry — reviewed 2026-03-15
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
      continue;
    }

    RCLCPP_INFO(rclcpp::get_logger("motor_control"),
      "[%s]   Temperature: %.0f C, Voltage: %.1fV, Error flags: 0x%X",
      config_.joint_name.c_str(), status.temperature, status.voltage,
      static_cast<unsigned int>(status.error_flags));

    if (status.error_flags == 0) {
      status_clean = true;
      break;
    }

    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "[%s] Error flags 0x%X still set after clear attempt %d/%d",
      config_.joint_name.c_str(), static_cast<unsigned int>(status.error_flags),
      attempt + 1, kMaxClearRetries);
  }

  if (!status_clean) {
    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "[%s] Could not verify clean error state after %d attempts. "
      "Continuing init — motor may still function.",
      config_.joint_name.c_str(), kMaxClearRetries);
  }

  // Step 3: motor_on
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[%s] Init step 3/4: motor_on (enable motor)", config_.joint_name.c_str());

  if (!protocol_->motor_on()) {
    record_error(
      ErrorFramework::ErrorCategory::INITIALIZATION,
      ErrorFramework::ErrorSeverity::ERROR,
      10,
      "Failed to send Motor ON command: " + protocol_->get_last_error());
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] Motor ON command failed. Check CAN connection and motor power.",
      config_.joint_name.c_str());
    return false;
  }

  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[%s] Motor ON command sent successfully", config_.joint_name.c_str());

  // BLOCKING_SLEEP_OK: init sequence, 50ms protocol settle after motor_on — reviewed 2026-03-15
  std::this_thread::sleep_for(std::chrono::milliseconds(50));

  // Step 4: verify_active — confirm motor responded to motor_on
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "[%s] Init step 4/4: verify motor active", config_.joint_name.c_str());

  MG6010Protocol::Status verify_status;
  bool verify_success = protocol_->read_status(verify_status);
  if (verify_success) {
    RCLCPP_INFO(rclcpp::get_logger("motor_control"),
      "[%s]   Temperature: %.0f C, Voltage: %.1fV, Error flags: 0x%X",
      config_.joint_name.c_str(), verify_status.temperature, verify_status.voltage,
      static_cast<unsigned int>(verify_status.error_flags));
  } else {
    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "[%s] Could not verify motor status after motor_on. "
      "Motor may still be functional, continuing initialization...",
      config_.joint_name.c_str());
  }

  initialized_ = true;
  calibrated_ = true;  // MG6010 motors don't require calibration
  enabled_ = true;     // Mark as enabled after successful motor_on

  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "MG6010Controller initialized and motor enabled for joint: %s (CAN ID: 0x%X)",
    config_.joint_name.c_str(), static_cast<int>(config_.can_id));

  return true;
}

bool MG6010Controller::configure(const MotorConfiguration & config)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    record_error(
      ErrorFramework::ErrorCategory::CONTROL,
      ErrorFramework::ErrorSeverity::ERROR,
      3,
      "Cannot configure: controller not initialized");
    return false;
  }

  // Update configuration (except motor_type and can_id which can't be changed)
  config_.joint_name = config.joint_name;
  config_.transmission_factor = config.transmission_factor;
  config_.joint_offset = config.joint_offset;
  config_.encoder_offset = config.encoder_offset;
  config_.encoder_resolution = config.encoder_resolution;
  config_.direction = config.direction;
  config_.p_gain = config.p_gain;
  config_.v_gain = config.v_gain;
  config_.v_int_gain = config.v_int_gain;
  config_.current_limit = config.current_limit;
  config_.velocity_limit = config.velocity_limit;
  config_.limits = config.limits;
  config_.homing = config.homing;
  config_.motor_params = config.motor_params;
  config_.motor_strings = config.motor_strings;

  // Validate coordinate transform parameters to prevent division by zero (task 1.19)
  if (config_.direction != 1 && config_.direction != -1) {
    record_error(
      ErrorFramework::ErrorCategory::CONTROL,
      ErrorFramework::ErrorSeverity::ERROR,
      3,
      "Invalid direction: " + std::to_string(config_.direction) + " (must be +1 or -1)");
    return false;
  }
  if (config_.transmission_factor <= 0.0) {
    record_error(
      ErrorFramework::ErrorCategory::CONTROL,
      ErrorFramework::ErrorSeverity::ERROR,
      3,
      "Invalid transmission_factor: " + std::to_string(config_.transmission_factor) + " (must be > 0)");
    return false;
  }
  {
    double igr = 6.0;
    if (config_.motor_params.find("internal_gear_ratio") != config_.motor_params.end()) {
      igr = config_.motor_params.at("internal_gear_ratio");
    }
    if (igr <= 0.0) {
      record_error(
        ErrorFramework::ErrorCategory::CONTROL,
        ErrorFramework::ErrorSeverity::ERROR,
        3,
        "Invalid internal_gear_ratio: " + std::to_string(igr) + " (must be > 0)");
      return false;
    }
  }

  RCLCPP_INFO(rclcpp::get_logger("motor_control"), "MG6010Controller reconfigured for joint: %s", config_.joint_name.c_str());

  return true;
}

// ==============================================================================
// Motor Control
// ==============================================================================

bool MG6010Controller::set_enabled(bool enable)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    record_error(
      ErrorFramework::ErrorCategory::CONTROL,
      ErrorFramework::ErrorSeverity::ERROR,
      4,
      "Cannot enable/disable: controller not initialized");
    return false;
  }

  bool success = false;

  if (enable) {
    // Try to clear errors first, just in case the motor was in an error state
    protocol_->clear_errors();
    // BLOCKING_SLEEP_OK: enable sequence, 10ms protocol settle after clear_errors — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::milliseconds(10));

    success = protocol_->motor_on();
    if (success) {
      enabled_ = true;
      RCLCPP_INFO(rclcpp::get_logger("motor_control"), "Motor enabled: %s", config_.joint_name.c_str());
    } else {
      record_error(
        ErrorFramework::ErrorCategory::CONTROL,
        ErrorFramework::ErrorSeverity::ERROR,
        5,
        "Failed to enable motor: " + protocol_->get_last_error());
    }
  } else {
    // Hardened shutdown sequence: motor_stop → motor_off → clear_errors
    // motor_stop exits position control and reduces power before motor_off.
    // clear_errors after motor_off ensures clean state for next session.

    // Step 1: motor_stop (exit position control, reduce power)
    if (!protocol_->motor_stop()) {
      RCLCPP_WARN(rclcpp::get_logger("motor_control"),
        "[%s] motor_stop failed during disable (non-fatal): %s",
        config_.joint_name.c_str(), protocol_->get_last_error().c_str());
      // Non-fatal: continue with motor_off
    }

    // Step 2: motor_off
    success = protocol_->motor_off();
    if (success) {
      enabled_ = false;
      RCLCPP_INFO(rclcpp::get_logger("motor_control"), "Motor disabled: %s", config_.joint_name.c_str());
    } else {
      record_error(
        ErrorFramework::ErrorCategory::CONTROL,
        ErrorFramework::ErrorSeverity::ERROR,
        6,
        "Failed to disable motor: " + protocol_->get_last_error());
    }

    // Step 3: clear_errors (ensure clean state for next session)
    if (!protocol_->clear_errors()) {
      RCLCPP_WARN(rclcpp::get_logger("motor_control"),
        "[%s] clear_errors failed during disable (non-fatal): %s",
        config_.joint_name.c_str(), protocol_->get_last_error().c_str());
      // Non-fatal: motor is already off
    }
  }

  return success;
}

bool MG6010Controller::set_position(double position, double velocity, double torque)
{
  (void)torque;  // Torque not used in MG6010 position control
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (param_enabled(config_.motor_params, "debug_commands")) {
    RCLCPP_DEBUG(rclcpp::get_logger("motor_control"), "[%s] set_position called: pos=%f | initialized=%s | enabled=%s",
      config_.joint_name.c_str(), position, (initialized_ ? "YES" : "NO"), (enabled_ ? "YES" : "NO"));
  }

  if (!initialized_ || !enabled_) {
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "[%s] REJECTED: Motor not initialized or not enabled!", config_.joint_name.c_str());
    return false;
  }

  // Clear stall protection on new command (task 4.5)
  if (stall_detected_) {
    stall_detected_ = false;
    stall_monitoring_ = false;
    RCLCPP_INFO(rclcpp::get_logger("motor_control"), "[%s] Stall protection cleared on new position command", config_.joint_name.c_str());
  }

  // Clamp position to safety limits (task 4.3) — send clamped value instead of rejecting
  double clamped_position = position;
  if (config_.joint_name.find("drive") == std::string::npos) {
    // Apply position clamping for non-drive motors
    if (position < config_.limits.position_min) {
      clamped_position = config_.limits.position_min;
      RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s] Position command %f clamped to min limit %f",
        config_.joint_name.c_str(), position, config_.limits.position_min);
    } else if (position > config_.limits.position_max) {
      clamped_position = config_.limits.position_max;
      RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s] Position command %f clamped to max limit %f",
        config_.joint_name.c_str(), position, config_.limits.position_max);
    }
  }

  // Check velocity limits (still reject on velocity violation)
  if (!check_velocity_limits(velocity)) {
    record_error(
      ErrorFramework::ErrorCategory::SAFETY,
      ErrorFramework::ErrorSeverity::WARNING,
      7,
      "Velocity command exceeds safety limits");
    return false;
  }

  // Convert to motor space
  double motor_position = joint_to_motor_position(clamped_position);
  // Note: velocity parameter currently unused (motor uses internal velocity profile in mode 1)
  (void)velocity;  // Suppress unused parameter warning

  // Send position command (use multi-loop angle mode 1 - CMD_MULTI_LOOP_ANGLE_1)
  // Note: velocity parameter is ignored in mode 1 (motor uses internal velocity profile)
  bool success = protocol_->set_absolute_position(motor_position);

  if (!success) {
    record_error(
      ErrorFramework::ErrorCategory::COMMUNICATION,
      ErrorFramework::ErrorSeverity::WARNING,
      8,
      "Failed to send position command: " + protocol_->get_last_error());
  }

  return success;
}

bool MG6010Controller::set_velocity(double velocity, double torque)
{
  (void)torque;  // Torque not used in MG6010 velocity control
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !enabled_) {
    return false;
  }

  // Check velocity limits
  if (!check_velocity_limits(velocity)) {
    record_error(
      ErrorFramework::ErrorCategory::SAFETY,
      ErrorFramework::ErrorSeverity::WARNING,
      9,
      "Velocity command exceeds safety limits");
    return false;
  }

  // Convert to motor space
  double motor_velocity = joint_to_motor_velocity(velocity);

  // Send velocity command
  bool success = protocol_->speed_closed_loop_control(motor_velocity);

  if (!success) {
    record_error(
      ErrorFramework::ErrorCategory::COMMUNICATION,
      ErrorFramework::ErrorSeverity::WARNING,
      10,
      "Failed to send velocity command: " + protocol_->get_last_error());
  }

  return success;
}

bool MG6010Controller::set_torque(double torque)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !enabled_) {
    return false;
  }

  // Convert to motor space
  double motor_torque = joint_to_motor_torque(torque);

  // Clamp to current limit
  double max_torque = config_.current_limit;
  motor_torque = std::clamp(motor_torque, -max_torque, max_torque);

  // Apply thermal derating (task 3.3)
  motor_torque = applyThermalDerating(motor_torque, cached_temperature_c_);

  // Send torque command
  bool success = protocol_->torque_closed_loop_control(motor_torque);

  if (!success) {
    record_error(
      ErrorFramework::ErrorCategory::COMMUNICATION,
      ErrorFramework::ErrorSeverity::WARNING,
      11,
      "Failed to send torque command: " + protocol_->get_last_error());
  }

  return success;
}

// ==============================================================================
// State Reading
// ==============================================================================

double MG6010Controller::get_position()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return 0.0;
  }

  // Update cached state
  update_cached_state();

  return current_position_;
}

double MG6010Controller::get_velocity()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return 0.0;
  }

  // Update cached state
  update_cached_state();

  return current_velocity_;
}

double MG6010Controller::get_torque()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return 0.0;
  }

  // Update cached state
  update_cached_state();

  return current_torque_;
}

MotorStatus MG6010Controller::get_status()
{
  return get_status(-1);
}

MotorStatus MG6010Controller::get_status(int max_retries)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  MotorStatus status;

  if (!initialized_) {
    status.state = MotorStatus::UNKNOWN;
    status.hardware_connected = false;
    return status;
  }

  // Read motor status from protocol (STATUS_1: temp, voltage, error flags)
  MG6010Protocol::Status mg_status{};
  const bool ok_status1 = protocol_->read_status(mg_status, max_retries);

  // Update cached kinematics/current (STATUS_2 + angle), but rate-limited inside update_cached_state().
  const bool ok_cached = update_cached_state(max_retries);

  status.hardware_connected = (ok_status1 || ok_cached);
  status.motor_enabled = enabled_;
  status.encoder_ready = true;  // MG6010 always has encoder ready

  if (ok_status1) {
    status.temperature = mg_status.temperature;
    status.voltage = mg_status.voltage;
    cached_temperature_c_ = mg_status.temperature;  // Cache for thermal derating (task 3.3)

    // Determine state
    if (!enabled_) {
      status.state = MotorStatus::IDLE;
    } else if (homed_) {
      status.state = MotorStatus::CLOSED_LOOP_CONTROL;
    } else {
      status.state = MotorStatus::STARTUP;
    }

    // Check for errors and attempt auto-recovery if enabled
    if (mg_status.error_flags != 0) {
      status.state = MotorStatus::AXIS_ERROR;
      record_error(
        ErrorFramework::ErrorCategory::HARDWARE,
        ErrorFramework::ErrorSeverity::ERROR,
        static_cast<uint32_t>(mg_status.error_flags),
        "Motor reported error state");

      // Auto-recovery: flag for background recovery timer (D2, task 2.1).
      // Previously, recovery was called inline here under state_mutex_, blocking
      // ALL motor operations for up to 3.5s. Now we just set a flag — the node
      // layer's recovery timer calls advanceRecovery() outside the hot path.
      bool auto_recovery_enabled = config_.motor_params.count("auto_recover_errors") > 0 &&
                                   config_.motor_params.at("auto_recover_errors") > 0.5;

      if (auto_recovery_enabled && !auto_recovery_disabled_) {
        auto now = std::chrono::steady_clock::now();

        // Check if this is a temperature error (needs longer physical cooldown)
        bool is_temperature_error = (mg_status.error_flags & MG6010Protocol::ERROR_TEMPERATURE) != 0;

        // Use longer cooldown for temperature errors (60s) vs normal errors (10s)
        auto required_cooldown = is_temperature_error ? TEMPERATURE_RECOVERY_COOLDOWN : RECOVERY_COOLDOWN;
        bool cooldown_elapsed = (now - last_recovery_attempt_) > required_cooldown;

        if (is_temperature_error && !cooldown_elapsed) {
          // Log once per temperature error event, then stay silent during cooldown
          if (!temperature_cooldown_logged_) {
            auto remaining_s = std::chrono::duration_cast<std::chrono::seconds>(
              required_cooldown - (now - last_recovery_attempt_)).count();
            RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s] Temperature error - waiting %lds for motor to cool before recovery attempt", config_.joint_name.c_str(), remaining_s);
            temperature_cooldown_logged_ = true;
          }
        } else if (!cooldown_elapsed) {
          // Silently skip - don't spam logs during cooldown
        } else if (recovery_step_ == RecoveryStep::IDLE) {
          // Flag for background recovery — don't call recovery inline (task 2.1)
          recovery_needed_ = true;
          recovery_error_flags_ = mg_status.error_flags;
        }
      } else if (auto_recovery_disabled_) {
        // Task 2.4: Re-enable auto-recovery after cooldown period
        auto now = std::chrono::steady_clock::now();
        if ((now - auto_recovery_disabled_time_) > AUTO_RECOVERY_REENABLE_COOLDOWN) {
          RCLCPP_INFO(rclcpp::get_logger("motor_control"), "[%s] Auto-recovery re-enabled after %lds cooldown",
            config_.joint_name.c_str(), std::chrono::duration_cast<std::chrono::seconds>(AUTO_RECOVERY_REENABLE_COOLDOWN).count());
          auto_recovery_disabled_ = false;
          consecutive_recovery_failures_ = 0;
        }
      }
    }
  } else {
    status.state = MotorStatus::UNKNOWN;
  }

  // Current telemetry: MG6010 STATUS_2 torque_current (A) cached by update_cached_state().
  status.current = current_torque_;

  // Copy error information
  status.current_error = current_error_;
  status.error_history = error_history_;
  status.error_code = current_error_.code;
  status.error_message = current_error_.message;

  status.last_update = std::chrono::steady_clock::now();

  // Evaluate motor health
  evaluate_motor_health(status);

  return status;
}

// ==============================================================================
// Homing and Calibration
// ==============================================================================

bool MG6010Controller::home_motor(const HomingConfig * config)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return false;
  }

  // MG6010 motors can use various homing methods
  // For now, we'll implement a simple zero-position homing
  (void)config;  // Suppress unused parameter warning

  // Use the built-in zero position command
  if (protocol_->set_current_position_as_zero()) {
    homed_ = true;
    RCLCPP_INFO(rclcpp::get_logger("motor_control"), "[%s] Motor homed (current position set as zero)", config_.joint_name.c_str());
    return true;
  } else {
    record_error(
      ErrorFramework::ErrorCategory::CONTROL,
      ErrorFramework::ErrorSeverity::ERROR,
      12,
      "Failed to set home position: " + protocol_->get_last_error());
    return false;
  }
}

bool MG6010Controller::is_homed() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return homed_;
}

bool MG6010Controller::calibrate_motor()
{
  // MG6010 motors don't require motor calibration
  calibrated_ = true;
  return true;
}

bool MG6010Controller::calibrate_encoder()
{
  // MG6010 motors have factory-calibrated encoders
  return true;
}

bool MG6010Controller::needs_calibration() const
{
  // MG6010 motors don't require calibration
  return false;
}

// ==============================================================================
// Emergency Handling
// ==============================================================================

bool MG6010Controller::emergency_stop()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return false;
  }

  // Send motor stop command immediately
  bool success = protocol_->motor_stop();

  if (success) {
    enabled_ = false;
    RCLCPP_WARN(rclcpp::get_logger("motor_control"), "EMERGENCY STOP executed for: %s", config_.joint_name.c_str());
  } else {
    record_error(
      ErrorFramework::ErrorCategory::SAFETY,
      ErrorFramework::ErrorSeverity::CRITICAL,
      13,
      "Emergency stop command failed: " + protocol_->get_last_error());
  }

  return success;
}

bool MG6010Controller::stop()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return false;
  }

  // Send motor stop command (exit position control, reduce power)
  bool success = protocol_->motor_stop();

  if (!success) {
    record_error(
      ErrorFramework::ErrorCategory::HARDWARE,
      ErrorFramework::ErrorSeverity::WARNING,
      14,
      "Motor stop command failed: " + protocol_->get_last_error());
  }

  return success;
}

bool MG6010Controller::clear_errors()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  // Send hardware clear_errors command over CAN first
  if (initialized_ && protocol_) {
    if (!protocol_->clear_errors()) {
      RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "Failed to send CAN clear_errors for: %s - %s",
        config_.joint_name.c_str(), protocol_->get_last_error().c_str());
      return false;
    }
  }

  // Clear internal C++ error state
  clear_error();

  // Re-enable auto-recovery if it was disabled by consecutive failures
  if (auto_recovery_disabled_) {
    auto_recovery_disabled_ = false;
    consecutive_recovery_failures_ = 0;
    RCLCPP_INFO(rclcpp::get_logger("motor_control"), "Auto-recovery re-enabled after manual clear for: %s", config_.joint_name.c_str());
  }

  RCLCPP_INFO(rclcpp::get_logger("motor_control"), "Errors cleared for: %s", config_.joint_name.c_str());
  return true;
}

// ==============================================================================
// Configuration Access
// ==============================================================================

MotorConfiguration MG6010Controller::get_configuration() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return config_;  // Return by value to prevent dangling reference after lock release
}

// ==============================================================================
// Error Handling
// ==============================================================================

const ErrorFramework::ErrorInfo & MG6010Controller::get_error_info() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return current_error_;
}

std::vector<ErrorFramework::ErrorInfo> MG6010Controller::get_error_history() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return error_history_;
}

ErrorFramework::RecoveryResult MG6010Controller::attempt_error_recovery()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();

  if (current_error_.category == ErrorFramework::ErrorCategory::NONE) {
    result.success = true;
    result.action_taken = "No error to recover from";
    return result;
  }

  // Attempt recovery based on error category
  switch (current_error_.category) {
    case ErrorFramework::ErrorCategory::COMMUNICATION:
      // Try to re-establish communication
      result.action_taken = "Attempting to clear communication error";
      clear_error();
      result.success = true;
      result.next_suggestion = "Verify CAN connection and baud rate";
      break;

    case ErrorFramework::ErrorCategory::SAFETY:
      // Safety errors require manual intervention
      result.action_taken = "Safety error requires manual reset";
      result.success = false;
      result.next_suggestion = "Check position/velocity limits and call clear_errors()";
      break;

    default:
      result.action_taken = "Error cleared";
      clear_error();
      result.success = true;
      break;
  }

  result.attempts_made = 1;
  return result;
}

bool MG6010Controller::attempt_motor_error_recovery(uint32_t error_flags)
{
  // Don't attempt recovery if not initialized
  if (!initialized_ || !protocol_) {
    return false;
  }

  RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s] Motor error detected (flags: 0x%X), attempting recovery with up to %d attempts...",
    config_.joint_name.c_str(), error_flags, MAX_RECOVERY_RETRIES);

  int retry_delay_ms = 500;  // Start with 500ms, doubles each retry

  for (int attempt = 1; attempt <= MAX_RECOVERY_RETRIES; ++attempt) {
    total_recovery_attempts_++;

    RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s] Recovery attempt %d/%d...", config_.joint_name.c_str(), attempt, MAX_RECOVERY_RETRIES);

    // Step 1: Clear motor errors
    RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s]   - Clearing motor errors...", config_.joint_name.c_str());
    if (!protocol_->clear_errors()) {
      RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "[%s]   - Failed to clear errors: %s", config_.joint_name.c_str(), protocol_->get_last_error().c_str());
      if (attempt < MAX_RECOVERY_RETRIES) {
        RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s]   - Waiting %dms before retry...", config_.joint_name.c_str(), retry_delay_ms);
        // BLOCKING_SLEEP_OK: legacy recovery path, exponential backoff between clear_errors retries — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(retry_delay_ms));
        retry_delay_ms *= 2;  // Exponential backoff
        continue;
      }
      failed_recoveries_++;
      return false;
    }
    // BLOCKING_SLEEP_OK: legacy recovery path, 100ms settle after clear_errors — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Step 2: Reboot motor (OFF -> ON)
    RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s]   - Rebooting motor (OFF->ON)...", config_.joint_name.c_str());
    if (!protocol_->motor_off()) {
      RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "[%s]   - Failed to turn motor off", config_.joint_name.c_str());
      if (attempt < MAX_RECOVERY_RETRIES) {
        RCLCPP_WARN(rclcpp::get_logger("motor_control"), "[%s]   - Waiting %dms before retry...", config_.joint_name.c_str(), retry_delay_ms);
        // BLOCKING_SLEEP_OK: legacy recovery path, exponential backoff after motor_off failure — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(retry_delay_ms));
        retry_delay_ms *= 2;
        continue;
      }
      failed_recoveries_++;
      return false;
    }
    // BLOCKING_SLEEP_OK: legacy recovery path, 200ms settle after motor_off — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    if (!protocol_->motor_on()) {
      RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "[%s]   - Failed to turn motor on", config_.joint_name.c_str());
      if (attempt < MAX_RECOVERY_RETRIES) {
        RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"), "[%s]   - Waiting %dms before retry...", config_.joint_name.c_str(), retry_delay_ms);
        // BLOCKING_SLEEP_OK: legacy recovery path, exponential backoff after motor_on failure — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(retry_delay_ms));
        retry_delay_ms *= 2;
        continue;
      }
      failed_recoveries_++;
      return false;
    }
    // BLOCKING_SLEEP_OK: legacy recovery path, 200ms settle after motor_on — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    // Step 3: Verify recovery - read status and check error flags
    RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"), "[%s]   - Verifying recovery...", config_.joint_name.c_str());
    MG6010Protocol::Status verify_status;
    if (!protocol_->read_status(verify_status)) {
      RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "[%s]   - Failed to read status for verification", config_.joint_name.c_str());
      if (attempt < MAX_RECOVERY_RETRIES) {
        RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"), "[%s]   - Waiting %dms before retry...", config_.joint_name.c_str(), retry_delay_ms);
        // BLOCKING_SLEEP_OK: legacy recovery path, exponential backoff after verify failure — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(retry_delay_ms));
        retry_delay_ms *= 2;
        continue;
      }
      failed_recoveries_++;
      return false;
    }

    if (verify_status.error_flags == 0) {
      RCLCPP_INFO(rclcpp::get_logger("mg6010_controller"), "[%s]   - Recovery successful on attempt %d, motor operational", config_.joint_name.c_str(), attempt);
      // Clear internal error state
      clear_error();
      enabled_ = true;
      successful_recoveries_++;
      return true;
    } else {
      RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"), "[%s]   - Motor still has errors (0x%X)",
        config_.joint_name.c_str(), static_cast<unsigned int>(verify_status.error_flags));
      if (attempt < MAX_RECOVERY_RETRIES) {
        RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"), "[%s]   - Waiting %dms before retry...", config_.joint_name.c_str(), retry_delay_ms);
        // BLOCKING_SLEEP_OK: legacy recovery path, exponential backoff after verify shows errors — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(retry_delay_ms));
        retry_delay_ms *= 2;
        continue;
      }
    }
  }

  RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "[%s]   - Recovery failed after %d attempts", config_.joint_name.c_str(), MAX_RECOVERY_RETRIES);
  failed_recoveries_++;
  return false;
}

// ==============================================================================
// Background Recovery State Machine (tasks 2.2-2.3)
// ==============================================================================

bool MG6010Controller::isRecoveryInProgress() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return recovery_step_ != RecoveryStep::IDLE;
}

bool MG6010Controller::advanceRecovery()
{
  // Called from the node layer's recovery timer (~2s interval).
  // Each call does ONE non-blocking CAN operation and returns.
  // Holds state_mutex_ only briefly — never calls sleep_for.

  std::unique_lock<std::mutex> lock(state_mutex_);

  // Check if recovery was requested by get_status()
  if (recovery_needed_ && recovery_step_ == RecoveryStep::IDLE) {
    recovery_needed_ = false;
    recovery_attempt_ = 1;
    recovery_retry_delay_ms_ = 500;
    recovery_step_time_ = std::chrono::steady_clock::now();
    last_recovery_attempt_ = recovery_step_time_;
    temperature_cooldown_logged_ = false;
    total_recovery_attempts_++;

    // Task 3.4: Thermal-aware recovery — if error is thermal (0x08), skip
    // clear_errors cycle and wait for temperature to drop below onset-hysteresis.
    bool is_thermal = (recovery_error_flags_ & MG6010Protocol::ERROR_TEMPERATURE) != 0;
    if (is_thermal) {
      recovery_step_ = RecoveryStep::COOLDOWN;
      recovery_retry_delay_ms_ = 2000;  // Poll temperature every 2s
      RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"),
        "[%s] Thermal error detected — skipping clear_errors, waiting for temp to drop below %.1f°C",
        config_.joint_name.c_str(), derating_onset_temp_ - thermal_hysteresis_);
    } else {
      recovery_step_ = RecoveryStep::CLEAR_ERRORS;
    }

    RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"),
      "[%s] Background recovery started (flags: 0x%X, attempt %d/%d%s)",
      config_.joint_name.c_str(), recovery_error_flags_, recovery_attempt_, MAX_RECOVERY_RETRIES,
      is_thermal ? ", thermal-aware" : "");
  }

  if (recovery_step_ == RecoveryStep::IDLE) {
    return false;  // Nothing to do
  }

  auto now = std::chrono::steady_clock::now();
  auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
    now - recovery_step_time_).count();

  // For WAIT_* and COOLDOWN steps, check if enough time has elapsed
  switch (recovery_step_) {
    case RecoveryStep::WAIT_CLEAR:
      if (elapsed_ms < 100) return false;  // Wait 100ms after clear_errors
      recovery_step_ = RecoveryStep::MOTOR_OFF;
      recovery_step_time_ = now;
      return false;

    case RecoveryStep::WAIT_OFF:
      if (elapsed_ms < 200) return false;  // Wait 200ms after motor_off
      recovery_step_ = RecoveryStep::MOTOR_ON;
      recovery_step_time_ = now;
      return false;

    case RecoveryStep::WAIT_ON:
      if (elapsed_ms < 200) return false;  // Wait 200ms after motor_on
      recovery_step_ = RecoveryStep::VERIFY;
      recovery_step_time_ = now;
      return false;

    case RecoveryStep::COOLDOWN:
      if (elapsed_ms < recovery_retry_delay_ms_) return false;

      // Task 3.4: If this is a thermal error, check temperature before retrying
      if ((recovery_error_flags_ & MG6010Protocol::ERROR_TEMPERATURE) != 0) {
        if (cached_temperature_c_ > (derating_onset_temp_ - thermal_hysteresis_)) {
          // Still too hot — keep waiting, poll every 2s
          recovery_step_time_ = now;
          recovery_retry_delay_ms_ = 2000;
          if (!temperature_cooldown_logged_) {
            RCLCPP_INFO(rclcpp::get_logger("mg6010_controller"),
              "[%s] Thermal recovery: temp=%.1f°C, waiting for <%.1f°C",
              config_.joint_name.c_str(), cached_temperature_c_, derating_onset_temp_ - thermal_hysteresis_);
            temperature_cooldown_logged_ = true;
          }
          return false;
        }
        // Temperature dropped — proceed with normal recovery
        RCLCPP_INFO(rclcpp::get_logger("mg6010_controller"),
          "[%s] Thermal recovery: temp=%.1f°C below threshold, attempting clear_errors",
          config_.joint_name.c_str(), cached_temperature_c_);
        temperature_cooldown_logged_ = false;
        recovery_step_ = RecoveryStep::CLEAR_ERRORS;
        recovery_step_time_ = now;
        return false;
      }

      // Non-thermal: start next attempt
      recovery_attempt_++;
      if (recovery_attempt_ > MAX_RECOVERY_RETRIES) {
        // All retries exhausted
        RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"),
          "[%s] Background recovery failed after %d attempts", config_.joint_name.c_str(), MAX_RECOVERY_RETRIES);
        failed_recoveries_++;
        consecutive_recovery_failures_++;
        if (consecutive_recovery_failures_ >= MAX_CONSECUTIVE_FAILURES) {
          RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"),
            "[%s] %d consecutive failures - disabling auto-recovery for %lds",
            config_.joint_name.c_str(), consecutive_recovery_failures_,
            std::chrono::duration_cast<std::chrono::seconds>(
              AUTO_RECOVERY_REENABLE_COOLDOWN).count());
          auto_recovery_disabled_ = true;
          auto_recovery_disabled_time_ = now;
        }
        recovery_step_ = RecoveryStep::IDLE;
        return true;  // Recovery complete (failed)
      }
      total_recovery_attempts_++;
      recovery_step_ = RecoveryStep::CLEAR_ERRORS;
      recovery_step_time_ = now;
      RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"),
        "[%s] Background recovery attempt %d/%d", config_.joint_name.c_str(), recovery_attempt_, MAX_RECOVERY_RETRIES);
      return false;

    default:
      break;
  }

  // Action steps — do ONE CAN operation then advance state
  // Release mutex during CAN I/O to avoid blocking other operations
  lock.unlock();

  switch (recovery_step_) {
    case RecoveryStep::CLEAR_ERRORS: {
      bool ok = protocol_->clear_errors();
      lock.lock();
      if (!ok) {
        RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "[%s] Background recovery: clear_errors failed", config_.joint_name.c_str());
        recovery_step_ = RecoveryStep::COOLDOWN;
        recovery_retry_delay_ms_ = std::min(recovery_retry_delay_ms_ * 2, 5000);
      } else {
        recovery_step_ = RecoveryStep::WAIT_CLEAR;
      }
      recovery_step_time_ = std::chrono::steady_clock::now();
      return false;
    }

    case RecoveryStep::MOTOR_OFF: {
      bool ok = protocol_->motor_off();
      lock.lock();
      if (!ok) {
        RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "[%s] Background recovery: motor_off failed", config_.joint_name.c_str());
        recovery_step_ = RecoveryStep::COOLDOWN;
        recovery_retry_delay_ms_ = std::min(recovery_retry_delay_ms_ * 2, 5000);
      } else {
        recovery_step_ = RecoveryStep::WAIT_OFF;
      }
      recovery_step_time_ = std::chrono::steady_clock::now();
      return false;
    }

    case RecoveryStep::MOTOR_ON: {
      bool ok = protocol_->motor_on();
      lock.lock();
      if (!ok) {
        RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "[%s] Background recovery: motor_on failed", config_.joint_name.c_str());
        recovery_step_ = RecoveryStep::COOLDOWN;
        recovery_retry_delay_ms_ = std::min(recovery_retry_delay_ms_ * 2, 5000);
      } else {
        recovery_step_ = RecoveryStep::WAIT_ON;
      }
      recovery_step_time_ = std::chrono::steady_clock::now();
      return false;
    }

    case RecoveryStep::VERIFY: {
      MG6010Protocol::Status verify_status;
      bool ok = protocol_->read_status(verify_status);
      lock.lock();
      if (!ok) {
        RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "[%s] Background recovery: read_status failed", config_.joint_name.c_str());
        recovery_step_ = RecoveryStep::COOLDOWN;
        recovery_retry_delay_ms_ = std::min(recovery_retry_delay_ms_ * 2, 5000);
        recovery_step_time_ = std::chrono::steady_clock::now();
        return false;
      }

      if (verify_status.error_flags == 0) {
        // Success!
        RCLCPP_INFO(rclcpp::get_logger("mg6010_controller"),
          "[%s] Background recovery successful on attempt %d", config_.joint_name.c_str(), recovery_attempt_);
        clear_error();
        enabled_ = true;
        successful_recoveries_++;
        consecutive_recovery_failures_ = 0;
        recovery_step_ = RecoveryStep::IDLE;
        return true;  // Recovery complete (success)
      } else {
        RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"),
          "[%s] Background recovery: motor still has errors (0x%X)",
          config_.joint_name.c_str(), static_cast<unsigned int>(verify_status.error_flags));
        recovery_step_ = RecoveryStep::COOLDOWN;
        recovery_retry_delay_ms_ = std::min(recovery_retry_delay_ms_ * 2, 5000);
        recovery_step_time_ = std::chrono::steady_clock::now();
        return false;
      }
    }

    default:
      break;
  }

  return false;
}

void MG6010Controller::set_error_handler(
  std::function<void(const ErrorFramework::ErrorInfo &)> handler)
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  error_handler_ = handler;
}

// ==============================================================================
// PID Parameter Access
// ==============================================================================

std::optional<PIDParams> MG6010Controller::readPID()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    return std::nullopt;
  }

  MG6010Protocol::PIDParams proto_params;
  if (!protocol_->read_pid(proto_params)) {
    return std::nullopt;
  }

  // Convert protocol PIDParams to interface PIDParams
  PIDParams params;
  params.angle_kp = proto_params.angle_kp;
  params.angle_ki = proto_params.angle_ki;
  params.speed_kp = proto_params.speed_kp;
  params.speed_ki = proto_params.speed_ki;
  params.current_kp = proto_params.current_kp;
  params.current_ki = proto_params.current_ki;
  return params;
}

bool MG6010Controller::setPID(const PIDParams & params)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    return false;
  }

  MG6010Protocol::PIDParams proto_params;
  proto_params.angle_kp = params.angle_kp;
  proto_params.angle_ki = params.angle_ki;
  proto_params.speed_kp = params.speed_kp;
  proto_params.speed_ki = params.speed_ki;
  proto_params.current_kp = params.current_kp;
  proto_params.current_ki = params.current_ki;
  return protocol_->set_pid(proto_params);
}

bool MG6010Controller::writePIDToROM(const PIDParams & params)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    return false;
  }

  MG6010Protocol::PIDParams proto_params;
  proto_params.angle_kp = params.angle_kp;
  proto_params.angle_ki = params.angle_ki;
  proto_params.speed_kp = params.speed_kp;
  proto_params.speed_ki = params.speed_ki;
  proto_params.current_kp = params.current_kp;
  proto_params.current_ki = params.current_ki;
  return protocol_->write_pid_to_rom(proto_params);
}

// ==============================================================================
// Motor Config Bridge Methods
// ==============================================================================

// -- Max torque current ratio ---------------------------------------------------

bool MG6010Controller::readMaxTorqueCurrent(uint16_t & ratio)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->read_max_torque_current(ratio)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to read max torque current for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::writeMaxTorqueCurrentRAM(uint16_t ratio)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->write_max_torque_current_ram(ratio)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to write max torque current for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

// -- Acceleration ---------------------------------------------------------------

bool MG6010Controller::readAcceleration(double & rad_per_sec2)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->read_acceleration(rad_per_sec2)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to read acceleration for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::setAcceleration(double rad_per_sec2)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->set_acceleration(rad_per_sec2)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to set acceleration for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

// -- Encoder --------------------------------------------------------------------

bool MG6010Controller::readEncoder(
  uint16_t & encoder_value, uint16_t & encoder_raw, uint16_t & encoder_offset)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->read_encoder(encoder_value, encoder_raw, encoder_offset)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to read encoder for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::writeEncoderOffsetToROM(uint16_t offset)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->write_encoder_offset_to_rom(offset)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to write encoder offset for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::setCurrentPositionAsZero()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->set_current_position_as_zero()) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to set current position as zero for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

// -- Angle reading (motor-space, no joint conversion) ---------------------------

bool MG6010Controller::readMultiTurnAngle(double & angle_radians)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->read_multi_turn_angle(angle_radians)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to read multi-turn angle for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::readSingleTurnAngle(double & angle_radians)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->read_single_turn_angle(angle_radians)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to read single-turn angle for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

// -- Error reading --------------------------------------------------------------

bool MG6010Controller::readErrors(uint32_t & error_flags)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!protocol_->read_errors(error_flags)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed to read errors for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

// -- Full aggregated state ------------------------------------------------------

FullMotorState MG6010Controller::readFullState()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  FullMotorState state;

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return state;  // valid = false
  }

  static constexpr double RAD_TO_DEG = 180.0 / M_PI;

  // STATUS_1: temperature, voltage, error flags
  MG6010Protocol::Status status1{};
  if (protocol_->read_status(status1)) {
    state.temperature_c = status1.temperature;
    state.voltage_v = status1.voltage;
    state.error_flags = static_cast<uint8_t>(status1.error_flags);
  }

  // STATUS_2: torque current, speed, encoder position (core data)
  MG6010Protocol::Status status2{};
  if (protocol_->read_status_detailed(status2)) {
    state.torque_current_a = status2.torque_current;
    state.speed_dps = status2.speed * RAD_TO_DEG;  // rad/s -> dps
    state.encoder_position = status2.encoder_position;
    state.valid = true;  // Core data succeeded
  }

  // STATUS_3: phase currents A/B/C
  MG6010Protocol::Status status3{};
  if (protocol_->read_status_phase_currents(status3)) {
    state.phase_current_a = status3.phase_current_a;
    state.phase_current_b = status3.phase_current_b;
    state.phase_current_c = status3.phase_current_c;
  }

  // Multi-turn angle
  double multi_turn_rad = 0.0;
  if (protocol_->read_multi_turn_angle(multi_turn_rad)) {
    state.multi_turn_deg = multi_turn_rad * RAD_TO_DEG;
  }

  // Single-turn angle
  double single_turn_rad = 0.0;
  if (protocol_->read_single_turn_angle(single_turn_rad)) {
    state.single_turn_deg = single_turn_rad * RAD_TO_DEG;
  }

  return state;
}

// -- Direct motor control (8 command modes) -------------------------------------

static constexpr double DEG_TO_RAD = M_PI / 180.0;
static constexpr double DPS_TO_RAD_S = M_PI / 180.0;

bool MG6010Controller::torqueClosedLoop(double amps)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!enabled_) {
    RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"),
      "torqueClosedLoop rejected: motor not enabled for %s", config_.joint_name.c_str());
    return false;
  }

  // Apply current limit clamping (same as set_torque)
  double max_torque = config_.current_limit;
  amps = std::clamp(amps, -max_torque, max_torque);

  // Apply thermal derating (same as set_torque)
  amps = applyThermalDerating(amps, cached_temperature_c_);

  if (!protocol_->torque_closed_loop_control(amps)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed torque closed-loop for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::speedClosedLoop(double dps)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  if (!enabled_) {
    RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"),
      "speedClosedLoop rejected: motor not enabled for %s", config_.joint_name.c_str());
    return false;
  }

  // Apply velocity limit clamping (same as set_velocity)
  double velocity_limit_dps = config_.velocity_limit / DPS_TO_RAD_S;  // Convert rad/s to dps
  dps = std::clamp(dps, -velocity_limit_dps, velocity_limit_dps);

  // Apply thermal derating — scale velocity by derating factor (task 1.18)
  dps = applyThermalDerating(dps, cached_temperature_c_);

  double rad_s = dps * DPS_TO_RAD_S;
  if (!protocol_->speed_closed_loop_control(rad_s)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed speed closed-loop for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::multiLoopAngle1(double degrees)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  double radians = degrees * DEG_TO_RAD;
  if (!protocol_->set_absolute_position(radians)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed multi-loop angle 1 for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::multiLoopAngle2(double degrees, double max_speed_dps)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  double radians = degrees * DEG_TO_RAD;
  double max_speed_rad_s = max_speed_dps * DPS_TO_RAD_S;
  if (!protocol_->set_absolute_position_with_speed(radians, max_speed_rad_s)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed multi-loop angle 2 for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::singleLoopAngle1(double degrees, uint8_t direction)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  double radians = degrees * DEG_TO_RAD;
  if (!protocol_->set_single_turn_position(radians, direction)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed single-loop angle 1 for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::singleLoopAngle2(
  double degrees, double max_speed_dps, uint8_t direction)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  double radians = degrees * DEG_TO_RAD;
  double max_speed_rad_s = max_speed_dps * DPS_TO_RAD_S;
  if (!protocol_->set_single_turn_position_with_speed(radians, max_speed_rad_s, direction)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed single-loop angle 2 for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::incrementAngle1(double degrees)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  double radians = degrees * DEG_TO_RAD;
  if (!protocol_->set_incremental_position(radians)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed increment angle 1 for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

bool MG6010Controller::incrementAngle2(double degrees, double max_speed_dps)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !protocol_) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Not initialized for: %s", config_.joint_name.c_str());
    return false;
  }

  double radians = degrees * DEG_TO_RAD;
  double max_speed_rad_s = max_speed_dps * DPS_TO_RAD_S;
  if (!protocol_->set_incremental_position_with_speed(radians, max_speed_rad_s)) {
    RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Failed increment angle 2 for: %s - %s",
      config_.joint_name.c_str(), protocol_->get_last_error().c_str());
    return false;
  }

  return true;
}

// ==============================================================================
// Private: Coordinate Transformations
// ==============================================================================
double MG6010Controller::joint_to_motor_position(double joint_pos) const
{
  // Input: joint_pos in ROTATIONS (vehicle_control converts radians→rotations)
  // Process in rotations, convert to radians at end for protocol
  // transmission_factor = external gearbox ratio only
  // Get internal gear ratio from config (6.0 for MG6010-i6, 36.0 for MG6012-i36)
  double internal_gear_ratio = 6.0;  // default
  if (config_.motor_params.find("internal_gear_ratio") != config_.motor_params.end()) {
    internal_gear_ratio = config_.motor_params.at("internal_gear_ratio");
  }

  // MULTIPLY by transmission factor (more transmission = more motor movement per joint unit)
  double after_offset = joint_pos - config_.joint_offset;
  double after_transmission = after_offset * config_.transmission_factor;
  double output_rotations = after_transmission * config_.direction;

  // Convert output rotations to radians
  double output_angle_rad = output_rotations * 2.0 * M_PI;

  // Apply internal gear ratio to get motor rotor angle
  double motor_angle_rad = output_angle_rad * internal_gear_ratio;

  if (param_enabled(config_.motor_params, "debug_conversion")) {
    RCLCPP_DEBUG(rclcpp::get_logger("mg6010_controller"),
      "JOINT TO MOTOR CONVERSION (%s): "
      "Input joint_pos=%.6f rot, joint_offset=%.6f, transmission_factor=%.6f, "
      "internal_gear_ratio=%.1f, direction=%d, "
      "after_offset=%.6f rot, after_transmission=%.6f rot, "
      "output_rotations=%.6f, output_angle=%.6f rad, "
      "motor_rotor_angle=%.6f rad (%.2f deg)",
      config_.joint_name.c_str(), joint_pos, config_.joint_offset,
      config_.transmission_factor, internal_gear_ratio, config_.direction,
      after_offset, after_transmission, output_rotations, output_angle_rad,
      motor_angle_rad, motor_angle_rad * 180.0 / M_PI);
  }

  return motor_angle_rad;
}

double MG6010Controller::motor_to_joint_position(double motor_pos) const
{
  // Inverse of joint_to_motor_position
  double internal_gear_ratio = 6.0;  // default
  if (config_.motor_params.find("internal_gear_ratio") != config_.motor_params.end()) {
    internal_gear_ratio = config_.motor_params.at("internal_gear_ratio");
  }

  // Remove internal gear ratio to get output shaft angle
  double output_angle_rad = motor_pos / internal_gear_ratio;

  // Convert radians to rotations
  double output_rotations = output_angle_rad / (2.0 * M_PI);

  // Apply inverse transmission
  double joint_pos = (output_rotations / config_.direction / config_.transmission_factor) + config_.joint_offset;

  return joint_pos;
}

double MG6010Controller::joint_to_motor_velocity(double joint_vel) const
{
  // Velocity transformation: apply transmission, direction, AND internal gear ratio
  // (matching joint_to_motor_position which applies all three)
  double internal_gear_ratio = 6.0;  // default
  if (config_.motor_params.find("internal_gear_ratio") != config_.motor_params.end()) {
    internal_gear_ratio = config_.motor_params.at("internal_gear_ratio");
  }
  return joint_vel * config_.transmission_factor * config_.direction * internal_gear_ratio;
}

double MG6010Controller::motor_to_joint_velocity(double motor_vel) const
{
  // Inverse velocity transformation: undo internal gear ratio, direction, and transmission
  double internal_gear_ratio = 6.0;  // default
  if (config_.motor_params.find("internal_gear_ratio") != config_.motor_params.end()) {
    internal_gear_ratio = config_.motor_params.at("internal_gear_ratio");
  }
  return motor_vel / internal_gear_ratio / config_.direction / config_.transmission_factor;
}

double MG6010Controller::joint_to_motor_torque(double joint_torque) const
{
  // Torque transformation: motor_torque = joint_torque * transmission_factor
  // (Note: torque increases with gear ratio, opposite of velocity)
  return joint_torque * config_.transmission_factor;
}

double MG6010Controller::motor_to_joint_torque(double motor_torque) const
{
  // Inverse torque transformation
  return motor_torque / config_.transmission_factor;
}

// ==============================================================================
// Private: State Management
// ==============================================================================

bool MG6010Controller::update_cached_state(int max_retries)
{
  // Don't update if not initialized
  if (!initialized_) {
    return false;
  }

  const auto now = std::chrono::steady_clock::now();

  // Avoid redundant back-to-back polling (e.g., get_status() + get_position() + get_velocity()
  // in the same control loop iteration). This reduces CAN traffic significantly.
  if (last_state_update_success_ && (now - last_state_update_) < min_state_update_period_) {
    return true;
  }

  // Read motor angle and detailed status (STATUS_2 provides speed + torque_current)
  double motor_angle = 0.0;
  MG6010Protocol::Status status2{};

  const bool ok_angle = protocol_->read_multi_turn_angle(motor_angle, max_retries);
  const bool ok_status2 = protocol_->read_status_detailed(status2, max_retries);

  if (ok_angle) {
    // Update cached position (convert to joint space)
    current_position_ = motor_to_joint_position(motor_angle);
  }

  if (ok_status2) {
    // Speed is reported by the motor; convert to joint space.
    current_velocity_ = motor_to_joint_velocity(status2.speed);

    // MG6010 STATUS_2 reports torque current (A). Keep as "current" telemetry.
    current_torque_ = status2.torque_current;
  }

  const bool success = (ok_angle || ok_status2);
  if (success) {
    last_state_update_ = now;
    last_state_update_success_ = true;
  } else {
    last_state_update_success_ = false;
  }

  return success;
}

bool MG6010Controller::check_safety_limits(double position, double velocity) const
{
  return check_position_limits(position) && check_velocity_limits(velocity);
}

bool MG6010Controller::check_position_limits(double position) const
{
  // Skip position limit checks for drive motors (contain "drive" in name)
  if (config_.joint_name.find("drive") != std::string::npos) {
    return true;  // No position limits for drive motors
  }

  // Check limits only for steering motors
  return (position >= config_.limits.position_min &&
          position <= config_.limits.position_max);
}

bool MG6010Controller::check_velocity_limits(double velocity) const
{
  return (std::abs(velocity) <= config_.limits.velocity_max);
}

// ==============================================================================
// Private: Error Handling
// ==============================================================================

void MG6010Controller::record_error(
  ErrorFramework::ErrorCategory category,
  ErrorFramework::ErrorSeverity severity,
  uint32_t code,
  const std::string & message)
{
  current_error_.category = category;
  current_error_.severity = severity;
  current_error_.code = code;
  current_error_.message = message;
  current_error_.timestamp = std::chrono::steady_clock::now();
  current_error_.occurrence_count++;

  // Add to history
  error_history_.push_back(current_error_);

  // Limit history size
  if (error_history_.size() > 100) {
    error_history_.erase(error_history_.begin());
  }

  // Call custom error handler if set
  if (error_handler_) {
    error_handler_(current_error_);
  }

  RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"), "Error [%s]: %s (Code: %u)",
    config_.joint_name.c_str(), message.c_str(), code);
}

void MG6010Controller::clear_error()
{
  current_error_ = ErrorFramework::ErrorInfo();
}

void MG6010Controller::evaluate_motor_health(MotorStatus & status)
{
  status.health_score = 1.0;
  status.requires_attention = false;
  status.warnings.clear();

  // Check temperature
  if (status.temperature > config_.limits.temperature_max * 0.9) {
    status.health_score -= 0.3;
    status.warnings.push_back("Temperature approaching limit");
  }
  if (status.temperature > config_.limits.temperature_max) {
    status.health_score -= 0.5;
    status.requires_attention = true;
    status.warnings.push_back("Temperature exceeded limit");
  }

  // Check voltage
  if (status.voltage < 20.0) {  // Assuming 24V nominal
    status.health_score -= 0.2;
    status.warnings.push_back("Low voltage detected");
  }

  // Check errors
  if (current_error_.category != ErrorFramework::ErrorCategory::NONE) {
    status.health_score -= 0.4;
    status.requires_attention = true;
    status.warnings.push_back("Active error: " + current_error_.message);
  }

  // Check communication
  auto time_since_update = std::chrono::steady_clock::now() - last_state_update_;
  if (time_since_update > std::chrono::milliseconds(100)) {
    status.health_score -= 0.3;
    status.warnings.push_back("Communication delay detected");
  }

  // Ensure health score stays in [0, 1]
  status.health_score = std::clamp(status.health_score, 0.0, 1.0);
}

// ==============================================================================
// Stall Detection (tasks 4.4-4.5)
// ==============================================================================

bool MG6010Controller::isStallDetected() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return stall_detected_;
}

double MG6010Controller::getDeratingFactor() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return current_derating_factor_;
}

bool MG6010Controller::isThermalProtectionActive() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return thermal_protection_active_;
}

void MG6010Controller::updateStallDetector(double current_amps, double position_deg)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  // If stall is already detected, nothing to monitor — stall clears on next command (task 4.5)
  if (stall_detected_) {
    return;
  }

  // Calculate rated current from config
  double rated_current = config_.current_limit;
  double threshold_amps = stall_current_threshold_ * rated_current;

  auto now = std::chrono::steady_clock::now();

  if (current_amps > threshold_amps) {
    if (!stall_monitoring_) {
      // Start monitoring — record baseline
      stall_monitoring_ = true;
      stall_monitor_start_ = now;
      stall_track_current_ = current_amps;
      stall_track_position_ = position_deg;
    } else {
      // Check if position has changed enough to NOT be a stall
      double position_delta = std::abs(position_deg - stall_track_position_);
      if (position_delta > stall_position_threshold_deg_) {
        // Motor is moving — reset monitoring baseline
        stall_track_position_ = position_deg;
        stall_monitor_start_ = now;
      } else {
        // High current + no movement — check duration
        auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
          now - stall_monitor_start_).count();
        if (elapsed_ms >= stall_time_threshold_ms_) {
          // STALL DETECTED — trigger protection (task 4.5)
          stall_detected_ = true;
          stall_monitoring_ = false;

          RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"),
            "[%s] STALL DETECTED: current=%.2fA (threshold=%.2fA), position_delta=%.2f deg over %ldms — commanding zero current",
            config_.joint_name.c_str(), current_amps, threshold_amps,
            position_delta, elapsed_ms);

          // Command zero current to protect motor
          if (protocol_) {
            protocol_->torque_closed_loop_control(0.0);
          }

          record_error(
            ErrorFramework::ErrorCategory::SAFETY,
            ErrorFramework::ErrorSeverity::WARNING,
            20,
            "Motor stall detected — zero current commanded");
        }
      }
    }
  } else {
    // Current below threshold — reset monitoring
    stall_monitoring_ = false;
  }
}

void MG6010Controller::configureStallDetection(
  double current_threshold, double position_threshold_deg, int time_threshold_ms)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  stall_current_threshold_ = current_threshold;
  stall_position_threshold_deg_ = position_threshold_deg;
  stall_time_threshold_ms_ = time_threshold_ms;

  RCLCPP_INFO(rclcpp::get_logger("mg6010_controller"),
    "[%s] Stall detection configured: current_threshold=%.2f (fraction of rated), position_threshold=%.2f deg, time_threshold=%dms",
    config_.joint_name.c_str(), current_threshold, position_threshold_deg, time_threshold_ms);
}

// ==============================================================================
// Thermal Derating (tasks 3.1-3.4)
// ==============================================================================

double MG6010Controller::applyThermalDerating(double commanded_current, double temperature_c)
{
  if (temperature_c < derating_onset_temp_) {
    // Below onset — full power, clear thermal protection if it was active
    if (thermal_protection_active_) {
      // Check hysteresis: only clear if below (onset - hysteresis)
      if (temperature_c < (derating_onset_temp_ - thermal_hysteresis_)) {
        thermal_protection_active_ = false;
        current_derating_factor_ = 1.0;
        RCLCPP_INFO(rclcpp::get_logger("mg6010_controller"),
          "[%s] Thermal protection cleared, temp=%.1f°C (below onset-hysteresis=%.1f°C)",
          config_.joint_name.c_str(), temperature_c, derating_onset_temp_ - thermal_hysteresis_);
      } else {
        // In hysteresis band — maintain current derating
        return commanded_current * current_derating_factor_;
      }
    }
    current_derating_factor_ = 1.0;
    return commanded_current;
  }

  if (temperature_c >= thermal_limit_temp_) {
    // At or above limit — minimum current
    current_derating_factor_ = min_derating_pct_;
    if (!thermal_protection_active_) {
      thermal_protection_active_ = true;
      RCLCPP_ERROR(rclcpp::get_logger("mg6010_controller"),
        "[%s] THERMAL PROTECTION ACTIVE: temp=%.1f°C >= limit=%.1f°C — current reduced to %.0f%%",
        config_.joint_name.c_str(), temperature_c, thermal_limit_temp_, min_derating_pct_ * 100.0);
    }
    return commanded_current * min_derating_pct_;
  }

  // Linear derating between onset and limit
  double range = thermal_limit_temp_ - derating_onset_temp_;
  double fraction = (temperature_c - derating_onset_temp_) / range;
  current_derating_factor_ = 1.0 - fraction * (1.0 - min_derating_pct_);
  current_derating_factor_ = std::clamp(current_derating_factor_, min_derating_pct_, 1.0);

  if (!thermal_protection_active_ && current_derating_factor_ < 1.0) {
    thermal_protection_active_ = true;
    RCLCPP_WARN(rclcpp::get_logger("mg6010_controller"),
      "[%s] Thermal derating active: temp=%.1f°C, derating_factor=%.3f",
      config_.joint_name.c_str(), temperature_c, current_derating_factor_);
  }

  return commanded_current * current_derating_factor_;
}

void MG6010Controller::configureThermalDerating(
  double onset_temp, double limit_temp, double min_pct, double hysteresis)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  derating_onset_temp_ = onset_temp;
  thermal_limit_temp_ = limit_temp;
  min_derating_pct_ = min_pct;
  thermal_hysteresis_ = hysteresis;

  RCLCPP_INFO(rclcpp::get_logger("mg6010_controller"),
    "[%s] Thermal derating configured: onset=%.1f°C, limit=%.1f°C, min_pct=%.2f, hysteresis=%.1f°C",
    config_.joint_name.c_str(), onset_temp, limit_temp, min_pct, hysteresis);
}

}  // namespace motor_control_ros2
