/*
 * Copyright (c) 2025 Pragati Robotics
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

#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <map>
#include <optional>
#include <random>
#include <utility>
#include <vector>

#include "motor_control_ros2/simulation/motor_sim_config.hpp"
#include "motor_control_ros2/mg6010_protocol.hpp"

namespace motor_control_ros2
{
namespace test
{

// =============================================================================
// Per-motor internal state
// =============================================================================

struct MotorState
{
  double position_deg = 0.0;
  double velocity_dps = 0.0;
  double target_position_deg = 0.0;
  double temperature_c = 25.0;
  double torque_current = 0.0;
  int16_t speed_command = 0;
  uint8_t error_flags = 0;
  bool motor_on = false;
  FaultType active_faults = FaultType::NONE;
  FaultConfig fault_config;
  MotorSimConfig config;
  uint16_t encoder_position = 0;
};

// =============================================================================
// MotorPhysicsSimulator (Tasks 1.2 - 1.6, 2.2 - 2.7)
// =============================================================================

/**
 * @brief Deterministic motor physics simulator for CAN-level integration tests.
 *
 * Provides first-order position dynamics, a simple thermal model, and
 * injectable faults (stall, overcurrent, over-temperature, CAN timeout,
 * encoder drift). All state updates are time-stepped via advanceTime()
 * so tests can run without wall-clock delays.
 *
 * This is a header-only test utility -- not part of production code.
 */
class MotorPhysicsSimulator
{
public:
  // -- Motor management -------------------------------------------------------

  inline void addMotor(uint8_t motor_id, const MotorSimConfig & config)
  {
    MotorState state;
    state.config = config;
    state.position_deg = config.initial_position_deg;
    state.target_position_deg = config.initial_position_deg;
    state.temperature_c = config.ambient_temperature_c;
    motors_[motor_id] = state;
  }

  inline void removeMotor(uint8_t motor_id)
  {
    motors_.erase(motor_id);
  }

  inline bool hasMotor(uint8_t motor_id) const
  {
    return motors_.count(motor_id) > 0;
  }

  // -- Time advancement (task 1.3, 1.4) ---------------------------------------

  inline void advanceTime(std::chrono::milliseconds dt)
  {
    double dt_seconds = dt.count() / 1000.0;
    if (dt_seconds <= 0.0) {
      return;
    }
    for (auto & [id, state] : motors_) {
      advanceMotor(state, dt_seconds);
    }
  }

  // -- Command processing (task 1.5, 1.6) ------------------------------------

  /**
   * @brief Process a CAN command frame destined for a simulated motor.
   *
   * @param motor_id  Target motor ID (1-32).
   * @param cmd_byte  Byte 0 of the transmitted CAN frame (command code).
   * @param payload   Bytes 1-7 of the transmitted CAN frame.
   * @return Response pair {arbitration_id, 8-byte data} or empty if the
   *         command is dropped by a CAN timeout fault.
   */
  inline std::optional<std::pair<uint32_t, std::vector<uint8_t>>>
  processCommand(uint8_t motor_id, uint8_t cmd_byte,
                 const std::vector<uint8_t> & payload)
  {
    auto it = motors_.find(motor_id);
    if (it == motors_.end()) {
      return std::nullopt;
    }

    MotorState & state = it->second;

    // Task 2.5 -- CAN timeout fault: probabilistic frame drop
    if (hasFault(state.active_faults, FaultType::CAN_TIMEOUT)) {
      if (shouldDropFrame(state.fault_config.timeout_drop_rate)) {
        return std::nullopt;
      }
    }

    uint32_t response_id = MG6010Protocol::BASE_ARBITRATION_ID +
                           static_cast<uint32_t>(motor_id);
    std::vector<uint8_t> response_data;

    switch (cmd_byte) {
      // -- Control commands ---------------------------------------------------
      case MG6010Protocol::CMD_MOTOR_OFF:
      case MG6010Protocol::CMD_MOTOR_ON:
      case MG6010Protocol::CMD_MOTOR_STOP:
      case MG6010Protocol::CMD_CLEAR_ERRORS:
        response_data = handleControlCommand(state, cmd_byte);
        break;

      // -- Read commands ------------------------------------------------------
      case MG6010Protocol::CMD_READ_STATUS_1:
        response_data = generateStatus1(state);
        break;
      case MG6010Protocol::CMD_READ_STATUS_2:
        response_data = generateStatus2(state);
        break;
      case MG6010Protocol::CMD_READ_STATUS_3:
        response_data = generateStatus3(state);
        break;
      case MG6010Protocol::CMD_READ_MULTI_TURN_ANGLE:
        response_data = generateMultiTurnAngle(state);
        break;
      case MG6010Protocol::CMD_READ_SINGLE_TURN_ANGLE:
        response_data = generateSingleTurnAngle(state);
        break;
      case MG6010Protocol::CMD_READ_ENCODER:
        response_data = generateEncoderRead(state);
        break;
      case MG6010Protocol::CMD_READ_PID:
        response_data = generatePidRead(state);
        break;

      // -- Motion commands ----------------------------------------------------
      case MG6010Protocol::CMD_TORQUE_CLOSED_LOOP:
      case MG6010Protocol::CMD_SPEED_CLOSED_LOOP:
      case MG6010Protocol::CMD_MULTI_LOOP_ANGLE_1:
      case MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2:
      case MG6010Protocol::CMD_SINGLE_LOOP_ANGLE_1:
      case MG6010Protocol::CMD_SINGLE_LOOP_ANGLE_2:
      case MG6010Protocol::CMD_INCREMENT_ANGLE_1:
      case MG6010Protocol::CMD_INCREMENT_ANGLE_2:
        response_data = handleMotionCommand(state, cmd_byte, payload);
        break;

      default:
        // Unknown command -- return a minimal echo
        response_data.resize(8, 0);
        response_data[0] = cmd_byte;
        break;
    }

    return std::make_pair(response_id, response_data);
  }

  // -- Fault injection (tasks 2.2 - 2.7) ------------------------------------

  inline void injectFault(uint8_t motor_id, FaultType fault)
  {
    auto it = motors_.find(motor_id);
    if (it != motors_.end()) {
      it->second.active_faults |= fault;
    }
  }

  inline void injectFault(uint8_t motor_id, FaultType fault,
                           const FaultConfig & config)
  {
    auto it = motors_.find(motor_id);
    if (it != motors_.end()) {
      it->second.active_faults |= fault;
      it->second.fault_config = config;
    }
  }

  inline void clearFault(uint8_t motor_id, FaultType fault)
  {
    auto it = motors_.find(motor_id);
    if (it != motors_.end()) {
      it->second.active_faults &= ~fault;
    }
  }

  inline void clearAllFaults(uint8_t motor_id)
  {
    auto it = motors_.find(motor_id);
    if (it != motors_.end()) {
      it->second.active_faults = FaultType::NONE;
    }
  }

  // -- State inspection (for test assertions) --------------------------------

  inline const MotorState * getMotorState(uint8_t motor_id) const
  {
    auto it = motors_.find(motor_id);
    if (it == motors_.end()) {
      return nullptr;
    }
    return &it->second;
  }

private:
  std::map<uint8_t, MotorState> motors_;
  std::mt19937 rng_{42};  // deterministic seed for reproducible fault behavior

  // ===========================================================================
  // Physics update (tasks 1.3, 1.4)
  // ===========================================================================

  inline void advanceMotor(MotorState & state, double dt_seconds)
  {
    // -- Task 1.3: First-order position dynamics ------------------------------
    if (state.motor_on && !hasFault(state.active_faults, FaultType::STALL)) {
      double tau = state.config.settling_time_constant_ms / 1000.0;
      double alpha = 1.0 - std::exp(-dt_seconds / tau);
      double new_position = state.position_deg +
                            alpha * (state.target_position_deg - state.position_deg);

      // Implied velocity from position change
      double implied_velocity = (new_position - state.position_deg) / dt_seconds;

      // Clamp by velocity limit
      double vel_max = state.config.velocity_max_dps;
      if (std::abs(implied_velocity) > vel_max) {
        double sign = (implied_velocity >= 0.0) ? 1.0 : -1.0;
        implied_velocity = sign * vel_max;
        new_position = state.position_deg + implied_velocity * dt_seconds;
      }

      state.velocity_dps = implied_velocity;
      state.position_deg = std::clamp(
        new_position, state.config.position_min_deg, state.config.position_max_deg);
    } else {
      // Motor off or stalled -- velocity decays to zero
      state.velocity_dps = 0.0;
    }

    // Update encoder from current position
    state.encoder_position = positionToEncoder(state.position_deg);

    // -- Task 1.4: Thermal model ----------------------------------------------
    double current_sq = state.torque_current * state.torque_current;
    double heat_input = current_sq * state.config.thermal_gain;
    double cooling = (state.temperature_c - state.config.ambient_temperature_c) /
                     state.config.thermal_time_constant_s;
    state.temperature_c += (heat_input - cooling) * dt_seconds;

    // Clamp to a reasonable range
    state.temperature_c = std::clamp(
      state.temperature_c, state.config.ambient_temperature_c - 10.0, 150.0);

    // Over-temperature error flag (natural)
    if (state.temperature_c >= state.config.over_temp_threshold_c) {
      state.error_flags |= MG6010Protocol::ERROR_TEMPERATURE;
    }

    // Task 2.7 -- Over-temperature fault injection: force temp to threshold
    if (hasFault(state.active_faults, FaultType::OVER_TEMPERATURE)) {
      state.temperature_c =
        std::max(state.temperature_c, state.config.over_temp_threshold_c);
      state.error_flags |= MG6010Protocol::ERROR_TEMPERATURE;
    }
  }

  // ===========================================================================
  // Response frame generation (task 1.5)
  // ===========================================================================

  // STATUS_1 (0x9A): [cmd, temp, volt_lo, volt_hi, 0, 0, 0, err_flags]
  inline std::vector<uint8_t> generateStatus1(const MotorState & state)
  {
    std::vector<uint8_t> data(8, 0);
    data[0] = MG6010Protocol::CMD_READ_STATUS_1;
    data[1] = static_cast<uint8_t>(static_cast<int8_t>(state.temperature_c));
    // Voltage: 24.0V at 0.1V/LSB = 240
    uint16_t voltage = 240;
    data[2] = static_cast<uint8_t>(voltage & 0xFF);
    data[3] = static_cast<uint8_t>((voltage >> 8) & 0xFF);
    data[7] = state.error_flags;
    return data;
  }

  // STATUS_2 (0x9C): [cmd, temp, iq_lo, iq_hi, speed_lo, speed_hi, enc_lo, enc_hi]
  inline std::vector<uint8_t> generateStatus2(const MotorState & state)
  {
    std::vector<uint8_t> data(8, 0);
    data[0] = MG6010Protocol::CMD_READ_STATUS_2;
    data[1] = static_cast<uint8_t>(static_cast<int8_t>(state.temperature_c));

    // Torque current: raw value -2048..2048 maps to -33A..33A
    auto iq = static_cast<int16_t>(state.torque_current * (2048.0 / 33.0));
    data[2] = static_cast<uint8_t>(iq & 0xFF);
    data[3] = static_cast<uint8_t>((iq >> 8) & 0xFF);

    // Speed: int16_t, 1 dps/LSB in response
    auto speed = static_cast<int16_t>(state.velocity_dps);
    data[4] = static_cast<uint8_t>(speed & 0xFF);
    data[5] = static_cast<uint8_t>((speed >> 8) & 0xFF);

    // Encoder: position modulo 360 mapped to 0-65535
    // Task 2.6 -- Encoder drift: offset the reported encoder value
    double enc_deg = state.position_deg;
    if (hasFault(state.active_faults, FaultType::ENCODER_DRIFT)) {
      enc_deg += state.fault_config.encoder_drift_deg;
    }
    uint16_t enc = positionToEncoder(enc_deg);
    data[6] = static_cast<uint8_t>(enc & 0xFF);
    data[7] = static_cast<uint8_t>((enc >> 8) & 0xFF);

    return data;
  }

  // STATUS_3 (0x9D): [cmd, temp, phA_lo, phA_hi, phB_lo, phB_hi, phC_lo, phC_hi]
  inline std::vector<uint8_t> generateStatus3(const MotorState & state)
  {
    std::vector<uint8_t> data(8, 0);
    data[0] = MG6010Protocol::CMD_READ_STATUS_3;
    data[1] = static_cast<uint8_t>(static_cast<int8_t>(state.temperature_c));

    // Balanced three-phase currents from torque_current (1A / 64 LSB)
    double phase_a = state.torque_current;
    double phase_b = -state.torque_current / 2.0;
    double phase_c = -state.torque_current / 2.0;

    // Task 2.4 -- Overcurrent fault: override phase A
    if (hasFault(state.active_faults, FaultType::OVERCURRENT)) {
      phase_a = state.fault_config.overcurrent_amps;
    }

    auto a = static_cast<int16_t>(phase_a * 64.0);
    auto b = static_cast<int16_t>(phase_b * 64.0);
    auto c = static_cast<int16_t>(phase_c * 64.0);

    data[2] = static_cast<uint8_t>(a & 0xFF);
    data[3] = static_cast<uint8_t>((a >> 8) & 0xFF);
    data[4] = static_cast<uint8_t>(b & 0xFF);
    data[5] = static_cast<uint8_t>((b >> 8) & 0xFF);
    data[6] = static_cast<uint8_t>(c & 0xFF);
    data[7] = static_cast<uint8_t>((c >> 8) & 0xFF);

    return data;
  }

  // Multi-turn angle (0x92): [cmd, ang_b0..ang_b6] -- 7-byte int64 LE, 0.01 deg/LSB
  // Reports the true position (no encoder-drift offset).
  inline std::vector<uint8_t> generateMultiTurnAngle(const MotorState & state)
  {
    std::vector<uint8_t> data(8, 0);
    data[0] = MG6010Protocol::CMD_READ_MULTI_TURN_ANGLE;

    auto centideg = static_cast<int64_t>(std::round(state.position_deg * 100.0));
    for (int i = 0; i < 7; ++i) {
      data[1 + i] = static_cast<uint8_t>((centideg >> (8 * i)) & 0xFF);
    }
    return data;
  }

  // Single-turn angle (0x94): [cmd, 0, 0, 0, ang_b0, ang_b1, ang_b2, ang_b3]
  // uint32 LE, 0.01 deg/LSB, range 0-35999
  inline std::vector<uint8_t> generateSingleTurnAngle(const MotorState & state)
  {
    std::vector<uint8_t> data(8, 0);
    data[0] = MG6010Protocol::CMD_READ_SINGLE_TURN_ANGLE;

    double single = std::fmod(state.position_deg, 360.0);
    if (single < 0.0) {
      single += 360.0;
    }
    auto centideg = static_cast<uint32_t>(std::round(single * 100.0));
    if (centideg > 35999) {
      centideg = 35999;
    }
    data[4] = static_cast<uint8_t>(centideg & 0xFF);
    data[5] = static_cast<uint8_t>((centideg >> 8) & 0xFF);
    data[6] = static_cast<uint8_t>((centideg >> 16) & 0xFF);
    data[7] = static_cast<uint8_t>((centideg >> 24) & 0xFF);

    return data;
  }

  // Encoder read (0x90): [cmd, 0, enc_lo, enc_hi, raw_lo, raw_hi, off_lo, off_hi]
  inline std::vector<uint8_t> generateEncoderRead(const MotorState & state)
  {
    std::vector<uint8_t> data(8, 0);
    data[0] = MG6010Protocol::CMD_READ_ENCODER;

    // Task 2.6 -- Encoder drift applied to reported value
    double enc_deg = state.position_deg;
    if (hasFault(state.active_faults, FaultType::ENCODER_DRIFT)) {
      enc_deg += state.fault_config.encoder_drift_deg;
    }
    uint16_t enc = positionToEncoder(enc_deg);

    // Encoder value (bytes 2-3)
    data[2] = static_cast<uint8_t>(enc & 0xFF);
    data[3] = static_cast<uint8_t>((enc >> 8) & 0xFF);
    // Raw encoder (bytes 4-5) -- same as encoder for simulation
    data[4] = static_cast<uint8_t>(enc & 0xFF);
    data[5] = static_cast<uint8_t>((enc >> 8) & 0xFF);
    // Offset (bytes 6-7) -- zero for simulation
    data[6] = 0;
    data[7] = 0;

    return data;
  }

  // PID read (0x30): [cmd, 0, angle_kp, angle_ki, speed_kp, speed_ki, iq_kp, iq_ki]
  inline std::vector<uint8_t> generatePidRead(const MotorState & /*state*/)
  {
    std::vector<uint8_t> data(8, 0);
    data[0] = MG6010Protocol::CMD_READ_PID;
    // Default PID values for simulation
    data[2] = 50;  // angle_kp
    data[3] = 50;  // angle_ki
    data[4] = 50;  // speed_kp
    data[5] = 50;  // speed_ki
    data[6] = 50;  // current_kp
    data[7] = 50;  // current_ki
    return data;
  }

  // ===========================================================================
  // Motion command handling (task 1.6)
  // ===========================================================================

  /**
   * @brief Decode a motion command and update the motor's setpoint.
   *
   * All motion commands return a STATUS_2-style response frame so the
   * caller receives immediate feedback on the motor state.
   */
  inline std::vector<uint8_t> handleMotionCommand(
    MotorState & state, uint8_t cmd, const std::vector<uint8_t> & payload)
  {
    state.motor_on = true;

    switch (cmd) {
      case MG6010Protocol::CMD_TORQUE_CLOSED_LOOP: {
        // Payload bytes 3-4: int16 LE torque value (-2048..2048 raw)
        int16_t raw = decodeInt16LE(payload, 3);
        state.torque_current = raw * (33.0 / 2048.0);
        break;
      }

      case MG6010Protocol::CMD_SPEED_CLOSED_LOOP: {
        // Payload bytes 3-6: int32 LE, 0.01 dps/LSB
        int32_t raw = decodeInt32LE(payload, 3);
        double speed_dps = raw * 0.01;
        state.speed_command = static_cast<int16_t>(speed_dps);
        // For the speed command, set the target far ahead in the direction of travel
        // so the velocity-clamped dynamics produce constant speed.
        double far_target = (speed_dps >= 0.0) ? state.config.position_max_deg
                                                : state.config.position_min_deg;
        state.target_position_deg = far_target;
        break;
      }

      case MG6010Protocol::CMD_MULTI_LOOP_ANGLE_1: {
        // LK-TECH V2.35 CMD 0xA3 wire format:
        //   Payload bytes 0-2: padding (0x00)
        //   Payload bytes 3-6: int32 LE angle (0.01 deg/LSB)
        int32_t centideg = decodeInt32LE(payload, 3);
        state.target_position_deg = centideg / 100.0;
        break;
      }

      case MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2: {
        // Payload bytes 1-2: uint16 LE max speed (1 dps/LSB)
        // Payload bytes 3-6: int32 LE angle (0.01 deg/LSB)
        // (speed limit is noted but the first-order dynamics already clamp)
        int32_t centideg = decodeInt32LE(payload, 3);
        state.target_position_deg = centideg / 100.0;
        break;
      }

      case MG6010Protocol::CMD_SINGLE_LOOP_ANGLE_1: {
        // Payload byte 0: spin direction (0 = CW, 1 = CCW)
        // Payload bytes 3-4: uint16 LE angle (0.01 deg/LSB, 0-35999)
        uint16_t centideg = decodeUint16LE(payload, 3);
        double angle = centideg / 100.0;
        state.target_position_deg = nearestSingleTurn(state.position_deg, angle);
        break;
      }

      case MG6010Protocol::CMD_SINGLE_LOOP_ANGLE_2: {
        // Payload byte 0: spin direction
        // Payload bytes 1-2: uint16 LE max speed (1 dps/LSB)
        // Payload bytes 3-4: uint16 LE angle (0.01 deg/LSB, 0-35999)
        uint16_t centideg = decodeUint16LE(payload, 3);
        double angle = centideg / 100.0;
        state.target_position_deg = nearestSingleTurn(state.position_deg, angle);
        break;
      }

      case MG6010Protocol::CMD_INCREMENT_ANGLE_1: {
        // Payload bytes 0-3: int32 LE incremental angle (0.01 deg/LSB)
        int32_t centideg = decodeInt32LE(payload, 0);
        state.target_position_deg = state.position_deg + centideg / 100.0;
        break;
      }

      case MG6010Protocol::CMD_INCREMENT_ANGLE_2: {
        // Payload bytes 1-2: uint16 LE max speed (1 dps/LSB)
        // Payload bytes 3-6: int32 LE incremental angle (0.01 deg/LSB)
        int32_t centideg = decodeInt32LE(payload, 3);
        state.target_position_deg = state.position_deg + centideg / 100.0;
        break;
      }

      default:
        break;
    }

    // Real MG6010 echoes the command byte in the response (byte 0),
    // followed by status data. MG6010Protocol::wait_response() validates
    // that byte 0 matches the expected command.
    auto response = generateStatus2(state);
    response[0] = cmd;
    return response;
  }

  // ===========================================================================
  // Control command handling (task 1.6)
  // ===========================================================================

  inline std::vector<uint8_t> handleControlCommand(MotorState & state, uint8_t cmd)
  {
    switch (cmd) {
      case MG6010Protocol::CMD_MOTOR_OFF:
        state.motor_on = false;
        state.torque_current = 0.0;
        state.speed_command = 0;
        state.velocity_dps = 0.0;
        break;

      case MG6010Protocol::CMD_MOTOR_STOP:
        // Stop motion but keep motor enabled
        state.target_position_deg = state.position_deg;
        state.torque_current = 0.0;
        state.speed_command = 0;
        break;

      case MG6010Protocol::CMD_MOTOR_ON:
        state.motor_on = true;
        break;

      case MG6010Protocol::CMD_CLEAR_ERRORS:
        state.error_flags = 0;
        break;

      default:
        break;
    }

    // Real MG6010 echoes the command byte in the response (byte 0),
    // followed by status data. MG6010Protocol::wait_response() validates
    // that byte 0 matches the expected command.
    auto response = generateStatus1(state);
    response[0] = cmd;
    return response;
  }

  // ===========================================================================
  // Helpers
  // ===========================================================================

  // Convert a position in degrees to a uint16 encoder value (0-65535 for 0-360 deg).
  static inline uint16_t positionToEncoder(double position_deg)
  {
    double normalized = std::fmod(position_deg + 36000.0, 360.0);
    return static_cast<uint16_t>(normalized / 360.0 * 65535.0);
  }

  // Map a single-turn target (0-360) onto the nearest full turn from current.
  static inline double nearestSingleTurn(double current_deg, double single_deg)
  {
    double base = std::floor(current_deg / 360.0) * 360.0;
    double candidate = base + single_deg;
    // Pick the turn that is closest to the current position
    if (std::abs(candidate - current_deg) > 180.0) {
      if (candidate > current_deg) {
        candidate -= 360.0;
      } else {
        candidate += 360.0;
      }
    }
    return candidate;
  }

  // Task 2.5 -- Decide whether to drop a CAN frame based on drop rate.
  inline bool shouldDropFrame(double drop_rate)
  {
    if (drop_rate >= 1.0) {
      return true;
    }
    if (drop_rate <= 0.0) {
      return false;
    }
    std::uniform_real_distribution<double> dist(0.0, 1.0);
    return dist(rng_) < drop_rate;
  }

  // -- Little-endian decode helpers -------------------------------------------

  static inline int16_t decodeInt16LE(const std::vector<uint8_t> & v, size_t offset)
  {
    if (offset + 1 >= v.size()) {
      return 0;
    }
    uint16_t raw = static_cast<uint16_t>(v[offset]) |
                   (static_cast<uint16_t>(v[offset + 1]) << 8);
    return static_cast<int16_t>(raw);
  }

  static inline uint16_t decodeUint16LE(const std::vector<uint8_t> & v, size_t offset)
  {
    if (offset + 1 >= v.size()) {
      return 0;
    }
    return static_cast<uint16_t>(v[offset]) |
           (static_cast<uint16_t>(v[offset + 1]) << 8);
  }

  static inline int32_t decodeInt32LE(const std::vector<uint8_t> & v, size_t offset)
  {
    if (offset + 3 >= v.size()) {
      return 0;
    }
    uint32_t raw = static_cast<uint32_t>(v[offset]) |
                   (static_cast<uint32_t>(v[offset + 1]) << 8) |
                   (static_cast<uint32_t>(v[offset + 2]) << 16) |
                   (static_cast<uint32_t>(v[offset + 3]) << 24);
    return static_cast<int32_t>(raw);
  }

  // Decode 7 bytes of a sign-extended int64 in little-endian order.
  static inline int64_t decodeInt64LE7(const std::vector<uint8_t> & v, size_t offset)
  {
    if (offset + 6 >= v.size()) {
      return 0;
    }
    int64_t val = 0;
    for (int i = 0; i < 7; ++i) {
      val |= static_cast<int64_t>(v[offset + i]) << (8 * i);
    }
    // Sign-extend from bit 55
    if (val & (static_cast<int64_t>(1) << 55)) {
      val |= static_cast<int64_t>(0xFF) << 56;
    }
    return val;
  }
};

}  // namespace test
}  // namespace motor_control_ros2
