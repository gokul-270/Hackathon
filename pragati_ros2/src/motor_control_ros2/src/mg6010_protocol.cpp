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
 * MG6010-i6 Motor Protocol Implementation
 *
 * Implements official LK-TECH CAN Protocol V2.35 for MG6010-i6 motors.
 * Ported from tested colleague implementation with official spec compliance.
 */

#include "motor_control_ros2/mg6010_protocol.hpp"
#include "motor_control_ros2/mg6010_can_interface.hpp"
#include <sys/epoll.h>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <cstring>
#include <cmath>
#include <thread>
#include <chrono>

namespace motor_control_ros2
{

MG6010Protocol::MG6010Protocol()
: node_id_(0)
, baud_rate_(500000)  // Pragati default: 500kbps (CAN interface configured externally)
, initialized_(false)
, last_error_("")
, default_timeout_ms_(10)  // Official spec: ~0.25ms typical, use 10ms for safety
, num_retries_(3)  // Retry on timeout
{
}

MG6010Protocol::~MG6010Protocol()
{
}

bool MG6010Protocol::initialize(
  std::shared_ptr<CANInterface> can,
  uint8_t node_id,
  uint32_t baud_rate)
{
  if (node_id < 1 || node_id > 32) {
    last_error_ = "Invalid motor node ID (must be 1-32)";
    return false;
  }

  if (!can || !can->is_connected()) {
    last_error_ = "CAN interface not connected";
    return false;
  }

  can_interface_ = can;
  node_id_ = node_id;
  baud_rate_ = baud_rate;
  initialized_ = true;

  last_error_ = "";
  return true;
}

// Helper: clamp speed to uint16 range [0, 65535]
static inline uint16_t clamp_speed_uint16(double speed_dps)
{
  double abs_speed = std::abs(speed_dps);
  if (abs_speed > 65535.0) {
    std::cerr << "[MG6010Protocol] WARNING: speed value " << speed_dps
              << " dps clamped to 65535" << std::endl;
    abs_speed = 65535.0;
  }
  return static_cast<uint16_t>(abs_speed);
}

// ============================================================================
// Basic Motor Control
// ============================================================================

bool MG6010Protocol::motor_on()
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_MOTOR_ON, tx_payload, rx_payload);
}

bool MG6010Protocol::motor_off()
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_MOTOR_OFF, tx_payload, rx_payload);
}

bool MG6010Protocol::motor_stop()
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_MOTOR_STOP, tx_payload, rx_payload);
}

// ============================================================================
// Position Control
// ============================================================================

bool MG6010Protocol::set_absolute_position(double radians)
{
  std::vector<uint8_t> angle_bytes = encode_multi_turn_angle(radians);
  if (angle_bytes.empty()) {
    last_error_ = "Position value overflows int32 range";
    return false;
  }

  // LK-TECH V2.35 CMD 0xA3 wire format:
  //   DATA[0] = 0xA3 (command byte, added by make_frame)
  //   DATA[1] = 0x00 (padding)
  //   DATA[2] = 0x00 (padding)
  //   DATA[3] = 0x00 (padding)
  //   DATA[4]-DATA[7] = int32 LE angle in 0.01° units
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);  // DATA[1] padding
  tx_payload.push_back(0x00);  // DATA[2] padding
  tx_payload.push_back(0x00);  // DATA[3] padding
  for (auto byte : angle_bytes) {
    tx_payload.push_back(byte);  // DATA[4]-DATA[7] angle
  }

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_MULTI_LOOP_ANGLE_1, tx_payload, rx_payload);
}

bool MG6010Protocol::set_absolute_position_with_speed(double radians, double max_speed_rad_s)
{
  // Encode speed (uint16_t in dps)
  double speed_dps = max_speed_rad_s * RAD_PER_SEC_TO_DPS;
  uint16_t speed_control = clamp_speed_uint16(speed_dps);

  // Encode angle (int32 in 0.01 degree units)
  std::vector<uint8_t> angle_bytes = encode_multi_turn_angle(radians);
  if (angle_bytes.empty()) {
    last_error_ = "Position value overflows int32 range";
    return false;
  }

  // LK-TECH V2.35 CMD 0xA4 wire format:
  //   DATA[0] = 0xA4 (command byte, added by make_frame)
  //   DATA[1] = 0x00 (padding)
  //   DATA[2] = speed LSB  \  uint16 LE, 1 dps/LSB
  //   DATA[3] = speed MSB  /
  //   DATA[4]-DATA[7] = int32 LE angle in 0.01° units
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);
  tx_payload.push_back(static_cast<uint8_t>(speed_control & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((speed_control >> 8) & 0xFF));

  for (auto byte : angle_bytes) {
    tx_payload.push_back(byte);
  }

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_MULTI_LOOP_ANGLE_2, tx_payload, rx_payload);
}

bool MG6010Protocol::set_single_turn_position(double radians, uint8_t spin_direction)
{
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(spin_direction);
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);

  // Encode single-turn angle
  std::vector<uint8_t> angle_bytes = encode_single_turn_angle(radians);
  for (auto byte : angle_bytes) {
    tx_payload.push_back(byte);
  }

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_SINGLE_LOOP_ANGLE_1, tx_payload, rx_payload);
}

bool MG6010Protocol::set_single_turn_position_with_speed(
  double radians, double max_speed_rad_s, uint8_t spin_direction)
{
  double speed_dps = max_speed_rad_s * RAD_PER_SEC_TO_DPS;
  uint16_t speed_control = clamp_speed_uint16(speed_dps);

  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(spin_direction);
  tx_payload.push_back(static_cast<uint8_t>(speed_control & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((speed_control >> 8) & 0xFF));

  std::vector<uint8_t> angle_bytes = encode_single_turn_angle(radians);
  for (auto byte : angle_bytes) {
    tx_payload.push_back(byte);
  }

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_SINGLE_LOOP_ANGLE_2, tx_payload, rx_payload);
}

bool MG6010Protocol::set_incremental_position(double radians)
{
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);

  // Encode as int32 in 0.01 degrees
  double degrees = radians * RADIANS_TO_DEGREES;
  int32_t angle_control = static_cast<int32_t>(degrees * 100.0);

  tx_payload.push_back(static_cast<uint8_t>(angle_control & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((angle_control >> 8) & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((angle_control >> 16) & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((angle_control >> 24) & 0xFF));

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_INCREMENT_ANGLE_1, tx_payload, rx_payload);
}

bool MG6010Protocol::set_incremental_position_with_speed(double radians, double max_speed_rad_s)
{
  double speed_dps = max_speed_rad_s * RAD_PER_SEC_TO_DPS;
  uint16_t speed_control = clamp_speed_uint16(speed_dps);

  double degrees = radians * RADIANS_TO_DEGREES;
  int32_t angle_control = static_cast<int32_t>(degrees * 100.0);

  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);
  tx_payload.push_back(static_cast<uint8_t>(speed_control & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((speed_control >> 8) & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>(angle_control & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((angle_control >> 8) & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((angle_control >> 16) & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((angle_control >> 24) & 0xFF));

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_INCREMENT_ANGLE_2, tx_payload, rx_payload);
}

// ============================================================================
// Velocity Control
// ============================================================================

bool MG6010Protocol::speed_closed_loop_control(double rad_per_sec)
{
  std::vector<uint8_t> speed_bytes = encode_speed(rad_per_sec);
  // Explicit byte-index assignment: [0x00, 0x00, 0x00, speed_b0..b3]
  std::vector<uint8_t> tx_payload(7, 0x00);
  for (size_t i = 0; i < speed_bytes.size() && i < 4; ++i) {
    tx_payload[3 + i] = speed_bytes[i];
  }

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_SPEED_CLOSED_LOOP, tx_payload, rx_payload);
}

// ============================================================================
// Torque Control
// ============================================================================

bool MG6010Protocol::torque_closed_loop_control(double torque_amps)
{
  std::vector<uint8_t> torque_bytes = encode_torque(torque_amps);
  // Explicit byte-index: [0x00, 0x00, 0x00, torque_lo, torque_hi, 0x00, 0x00]
  std::vector<uint8_t> tx_payload(7, 0x00);
  for (size_t i = 0; i < torque_bytes.size() && i < 2; ++i) {
    tx_payload[3 + i] = torque_bytes[i];
  }

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_TORQUE_CLOSED_LOOP, tx_payload, rx_payload);
}

// ============================================================================
// PID Configuration
// ============================================================================

bool MG6010Protocol::set_pid(const PIDParams & pid)
{
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);
  tx_payload.push_back(pid.angle_kp);
  tx_payload.push_back(pid.angle_ki);
  tx_payload.push_back(pid.speed_kp);
  tx_payload.push_back(pid.speed_ki);
  tx_payload.push_back(pid.current_kp);
  tx_payload.push_back(pid.current_ki);

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_WRITE_PID_RAM, tx_payload, rx_payload);
}

bool MG6010Protocol::read_pid(PIDParams & pid)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_PID, tx_payload, rx_payload)) {
    return false;
  }

  // Response format after wait_response strips cmd byte:
  // [pad, angle_kp, angle_ki, speed_kp, speed_ki, current_kp, current_ki]
  // The pad byte at index 0 is left by wait_response() which strips only the command byte
  // from the 8-byte CAN frame, leaving 7 payload bytes with the first being unused padding.
  if (rx_payload.size() >= 7) {
    pid.angle_kp = rx_payload[1];   // +1 offset to skip pad byte
    pid.angle_ki = rx_payload[2];
    pid.speed_kp = rx_payload[3];
    pid.speed_ki = rx_payload[4];
    pid.current_kp = rx_payload[5];
    pid.current_ki = rx_payload[6];
    return true;
  }

  last_error_ = "Invalid PID response payload size";
  return false;
}

bool MG6010Protocol::write_pid_to_rom(const PIDParams & pid)
{
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);
  tx_payload.push_back(pid.angle_kp);
  tx_payload.push_back(pid.angle_ki);
  tx_payload.push_back(pid.speed_kp);
  tx_payload.push_back(pid.speed_ki);
  tx_payload.push_back(pid.current_kp);
  tx_payload.push_back(pid.current_ki);

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_WRITE_PID_ROM, tx_payload, rx_payload);
}

// ============================================================================
// Acceleration Configuration
// ============================================================================

bool MG6010Protocol::set_acceleration(double rad_per_sec2)
{
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);

  std::vector<uint8_t> accel_bytes = encode_acceleration(rad_per_sec2);
  for (auto byte : accel_bytes) {
    tx_payload.push_back(byte);
  }

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_WRITE_ACCEL_RAM, tx_payload, rx_payload);
}

bool MG6010Protocol::read_acceleration(double & rad_per_sec2)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_ACCEL, tx_payload, rx_payload)) {
    return false;
  }

  // Acceleration is in bytes 3-6 as int32 (1 dps/s per LSB)
  if (rx_payload.size() >= 7) {
    rad_per_sec2 = decode_acceleration(rx_payload, 3);
    return true;
  }

  last_error_ = "Invalid acceleration response payload size";
  return false;
}

// ============================================================================
// Max Torque Current Ratio (0x37 read, 0x38 write)
// ============================================================================

bool MG6010Protocol::read_max_torque_current(uint16_t & ratio)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_MAX_TORQUE, tx_payload, rx_payload)) {
    return false;
  }

  // Response format: [pad, pad, pad, pad, ratio_low, ratio_high, pad]
  // The ratio is a uint16 at bytes 4-5 of the payload (after cmd byte stripped)
  if (rx_payload.size() >= 7) {
    ratio = static_cast<uint16_t>(rx_payload[4]) |
            (static_cast<uint16_t>(rx_payload[5]) << 8);
    return true;
  }

  last_error_ = "Invalid max torque current response payload size";
  return false;
}

bool MG6010Protocol::write_max_torque_current_ram(uint16_t ratio)
{
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);  // pad
  tx_payload.push_back(0x00);  // pad
  tx_payload.push_back(0x00);  // pad
  tx_payload.push_back(0x00);  // pad
  tx_payload.push_back(static_cast<uint8_t>(ratio & 0xFF));         // ratio low
  tx_payload.push_back(static_cast<uint8_t>((ratio >> 8) & 0xFF));  // ratio high
  tx_payload.push_back(0x00);  // pad

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_WRITE_MAX_TORQUE_RAM, tx_payload, rx_payload);
}

// ============================================================================
// Status Reading
// ============================================================================

bool MG6010Protocol::read_status(Status & status, int max_retries)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_STATUS_1, tx_payload, rx_payload, -1, max_retries)) {
    return false;
  }

  // STATUS_1 format: [cmd, temp, volt_low, volt_high, pad, pad, pad, errors]
  // Note: rx_payload excludes the command byte, so indices are shifted by -1
  if (rx_payload.size() >= 7) {
    status.temperature = decode_temperature(rx_payload[0]);
    status.voltage = decode_voltage(rx_payload, 1);  // Fixed: was reading wrong position
    status.error_flags = rx_payload[6];
    status.motor_running = true;  // Motor responded
    return true;
  }

  last_error_ = "Invalid status response payload size";
  return false;
}

bool MG6010Protocol::read_status_detailed(Status & status, int max_retries)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_STATUS_2, tx_payload, rx_payload, -1, max_retries)) {
    return false;
  }

  // STATUS_2 format: [cmd, temp, torque_low, torque_high, speed_low, speed_high, enc_low, enc_high]
  if (rx_payload.size() >= 7) {
    status.temperature = decode_temperature(rx_payload[0]);
    status.torque_current = decode_torque(rx_payload, 1);
    status.speed = decode_speed(rx_payload, 3);
    status.encoder_position = decode_encoder(rx_payload, 5);
    status.motor_running = true;
    status.error_flags = 0;  // STATUS_2 doesn't include error flags
    return true;
  }

  last_error_ = "Invalid detailed status response payload size";
  return false;
}

bool MG6010Protocol::read_status_phase_currents(Status & status)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_STATUS_3, tx_payload, rx_payload)) {
    return false;
  }

  // STATUS_3 format: [temp, phase_a_low, phase_a_high, phase_b_low, phase_b_high, phase_c_low, phase_c_high]
  if (rx_payload.size() >= 7) {
    status.temperature = decode_temperature(rx_payload[0]);
    status.phase_current_a = decode_phase_current(rx_payload, 1);
    status.phase_current_b = decode_phase_current(rx_payload, 3);
    status.phase_current_c = decode_phase_current(rx_payload, 5);
    status.motor_running = true;
    return true;
  }

  last_error_ = "Invalid phase current status response payload size";
  return false;
}

// ============================================================================
// Angle Reading
// ============================================================================

bool MG6010Protocol::read_multi_turn_angle(double & angle_radians, int max_retries)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_MULTI_TURN_ANGLE, tx_payload, rx_payload, -1, max_retries)) {
    return false;
  }

  // Multi-turn angle is in bytes 0-6 (7 bytes total, 56-bit signed integer)
  if (rx_payload.size() >= 7) {
    angle_radians = decode_multi_turn_angle(rx_payload, 0);
    return true;
  }

  last_error_ = "Invalid multi-turn angle response payload size";
  return false;
}

bool MG6010Protocol::read_single_turn_angle(double & angle_radians)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_SINGLE_TURN_ANGLE, tx_payload, rx_payload)) {
    return false;
  }

  // Single-turn angle is in bytes 3-6 (4 bytes, uint32)
  if (rx_payload.size() >= 7) {
    angle_radians = decode_single_turn_angle(rx_payload, 3);
    return true;
  }

  last_error_ = "Invalid single-turn angle response payload size";
  return false;
}

// ============================================================================
// Encoder Operations
// ============================================================================

bool MG6010Protocol::read_encoder(
  uint16_t & encoder_value,
  uint16_t & encoder_raw,
  uint16_t & encoder_offset)
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;

  if (!send_and_wait(CMD_READ_ENCODER, tx_payload, rx_payload)) {
    return false;
  }

  // Format: [cmd, pad, enc_low, enc_high, raw_low, raw_high, off_low, off_high]
  if (rx_payload.size() >= 7) {
    encoder_value = decode_encoder(rx_payload, 1);
    encoder_raw = decode_encoder(rx_payload, 3);
    encoder_offset = decode_encoder(rx_payload, 5);
    return true;
  }

  last_error_ = "Invalid encoder response payload size";
  return false;
}

bool MG6010Protocol::write_encoder_offset_to_rom(uint16_t offset)
{
  std::vector<uint8_t> tx_payload;
  tx_payload.push_back(0x00);
  tx_payload.push_back(static_cast<uint8_t>(offset & 0xFF));
  tx_payload.push_back(static_cast<uint8_t>((offset >> 8) & 0xFF));
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);
  tx_payload.push_back(0x00);

  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_WRITE_ENCODER_OFFSET_ROM, tx_payload, rx_payload);
}

bool MG6010Protocol::set_current_position_as_zero()
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_SET_ZERO_ROM, tx_payload, rx_payload);
}

// ============================================================================
// Error Handling
// ============================================================================

bool MG6010Protocol::clear_errors()
{
  std::vector<uint8_t> tx_payload;
  std::vector<uint8_t> rx_payload;
  return send_and_wait(CMD_CLEAR_ERRORS, tx_payload, rx_payload);
}

bool MG6010Protocol::read_errors(uint32_t & error_flags)
{
  Status status;
  if (read_status(status)) {
    error_flags = status.error_flags;
    return true;
  }
  return false;
}

// ============================================================================
// Low-level Communication Helpers
// ============================================================================

bool MG6010Protocol::send_command(uint8_t cmd, const std::vector<uint8_t> & payload)
{
  if (!initialized_ || !can_interface_) {
    last_error_ = "Protocol not initialized";
    return false;
  }

  uint32_t arb_id = make_arbitration_id(cmd);
  std::vector<uint8_t> frame = make_frame(cmd, payload);

  if (!can_interface_->send_message(arb_id, frame)) {
    last_error_ = "Failed to send CAN message: " + can_interface_->get_last_error();
    return false;
  }

  return true;
}

bool MG6010Protocol::wait_response(
  uint8_t expected_cmd,
  std::vector<uint8_t> & payload,
  int timeout_ms)
{
  if (!initialized_ || !can_interface_) {
    last_error_ = "Protocol not initialized";
    return false;
  }

  uint32_t expected_id = make_arbitration_id(expected_cmd);

  // C2 fix: Check response buffer first — a previous wait_response() call for another
  // motor may have buffered a frame intended for us (can-io-efficiency spec scenarios 15-16).
  auto mg_can = std::dynamic_pointer_cast<MG6010CANInterface>(can_interface_);
  if (mg_can) {
    std::vector<uint8_t> buffered_data;
    if (mg_can->getBufferedResponse(expected_id, buffered_data)) {
      if (!buffered_data.empty() && buffered_data[0] == expected_cmd) {
        if (buffered_data.size() > 1) {
          payload.assign(buffered_data.begin() + 1, buffered_data.end());
        } else {
          payload.clear();
        }
        return true;
      }
      // Task 2.8: buffered frame has correct CAN ID but wrong command byte —
      // re-buffer it instead of silently discarding a valid response for another command.
      if (!buffered_data.empty()) {
        mg_can->bufferCurrentFrame(expected_id, buffered_data);
      }
    }
  }

  // Use epoll_wait() instead of busy-polling (task 2.2).
  // If epoll is unavailable (mock interface or failed init), fall back to
  // receive_message() with SO_RCVTIMEO deadline.
  int epoll_fd = mg_can ? mg_can->get_epoll_fd() : -1;

  auto start = std::chrono::steady_clock::now();
  auto timeout_duration = std::chrono::milliseconds(timeout_ms);

  while (true) {
    // Compute remaining time in ms for epoll_wait / fallback check
    auto elapsed = std::chrono::steady_clock::now() - start;
    if (elapsed >= timeout_duration) {
      break;
    }
    int remaining_ms = static_cast<int>(
      std::chrono::duration_cast<std::chrono::milliseconds>(timeout_duration - elapsed).count());
    if (remaining_ms <= 0) {
      break;
    }

    // Wait for CAN socket readability via epoll (or fall through immediately if no epoll)
    if (epoll_fd >= 0) {
      struct epoll_event ev;
      int nfds = epoll_wait(epoll_fd, &ev, 1, remaining_ms);
      if (nfds < 0) {
        if (errno == EINTR) {
          continue;  // Task 2.4: interrupted by signal — retry
        }
        last_error_ = "epoll_wait failed: " + std::string(strerror(errno));
        return false;
      }
      if (nfds == 0) {
        break;  // Timeout — no data ready
      }
    }

    uint32_t rx_id;
    std::vector<uint8_t> rx_data;

    if (can_interface_->receive_message(rx_id, rx_data, 1)) {
      // Check if this is our response
      if (rx_id == expected_id && !rx_data.empty() && rx_data[0] == expected_cmd) {
        // Parse out the payload (everything after command byte)
        if (rx_data.size() > 1) {
          payload.assign(rx_data.begin() + 1, rx_data.end());
        } else {
          payload.clear();
        }
        return true;
      }
      // Task 2.8: Buffer ALL non-matching frames (not just CAN-ID mismatches).
      // A frame with the right CAN ID but wrong command byte is a valid response
      // for a different command and must not be discarded.
      if (mg_can) {
        mg_can->bufferCurrentFrame(rx_id, rx_data);
      }
    }
  }

  last_error_ = "Response timeout";
  return false;
}

bool MG6010Protocol::send_and_wait(
  uint8_t cmd,
  const std::vector<uint8_t> & tx_payload,
  std::vector<uint8_t> & rx_payload,
  int timeout_ms,
  int max_retries)
{
  if (timeout_ms < 0) {
    timeout_ms = default_timeout_ms_;
  }

  // Use caller's retry override, or fall back to the default num_retries_ (D3).
  int retries = (max_retries > 0) ? max_retries : num_retries_;

  // Task 2.9: Incremental position commands are NOT idempotent — resending doubles the
  // motion.  For these commands, send once and only retry the receive (wait_response).
  // All other commands are idempotent (absolute position, speed, torque, config reads)
  // and safe to fully resend on timeout.
  bool is_non_idempotent = (cmd == CMD_INCREMENT_ANGLE_1 || cmd == CMD_INCREMENT_ANGLE_2);

  // Acquire bus-level transaction lock to serialize CAN send+receive pairs.
  // Without this, MultiThreadedExecutor threads interleave sends to different motors,
  // causing response frame cross-buffering and CAN controller bus-off errors.
  auto mg_can = std::dynamic_pointer_cast<MG6010CANInterface>(can_interface_);
  std::unique_lock<std::mutex> txn_lock;
  if (mg_can) {
    txn_lock = std::unique_lock<std::mutex>(mg_can->transaction_mutex());
  }

  if (is_non_idempotent) {
    // Send the command exactly once
    if (!send_command(cmd, tx_payload)) {
      return false;
    }
    // Retry only the receive
    for (int attempt = 0; attempt < retries; ++attempt) {
      if (wait_response(cmd, rx_payload, timeout_ms)) {
        return true;
      }
      // Small delay before retry
      if (attempt < retries - 1) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
      }
    }
  } else {
    // Idempotent command — full send+receive retry is safe
    for (int attempt = 0; attempt < retries; ++attempt) {
      if (send_command(cmd, tx_payload)) {
        if (wait_response(cmd, rx_payload, timeout_ms)) {
          return true;
        }
      }
      // Small delay before retry
      if (attempt < retries - 1) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
      }
    }
  }

  // All retries failed
  std::ostringstream oss;
  oss << "Command 0x" << std::hex << static_cast<int>(cmd)
      << " failed after " << std::dec << retries << " attempts";
  last_error_ = oss.str();
  return false;
}

// ============================================================================
// Frame Construction/Parsing
// ============================================================================

uint32_t MG6010Protocol::make_arbitration_id(uint8_t cmd) const
{
  (void)cmd;  // Arbitration ID doesn't depend on command
  return BASE_ARBITRATION_ID + node_id_;
}

std::vector<uint8_t> MG6010Protocol::make_frame(
  uint8_t cmd,
  const std::vector<uint8_t> & payload) const
{
  std::vector<uint8_t> frame;
  frame.push_back(cmd);

  // Add payload
  for (size_t i = 0; i < payload.size() && i < 7; ++i) {
    frame.push_back(payload[i]);
  }

  // Pad to 8 bytes total
  while (frame.size() < 8) {
    frame.push_back(0x00);
  }

  return frame;
}

bool MG6010Protocol::parse_response(
  const std::vector<uint8_t> & data,
  uint8_t & cmd,
  std::vector<uint8_t> & payload) const
{
  if (data.empty()) {
    return false;
  }

  cmd = data[0];
  if (data.size() > 1) {
    payload.assign(data.begin() + 1, data.end());
  } else {
    payload.clear();
  }

  return true;
}

// ============================================================================
// Data Encoding/Decoding Helpers
// ============================================================================

std::vector<uint8_t> MG6010Protocol::encode_multi_turn_angle(double radians) const
{
  // Convert to degrees, then multiply by 100 for 0.01° units (centidegrees)
  // Motor protocol uses 0.01° per LSB for multi-turn angle commands
  // LK-TECH V2.35: WRITE commands (0xA3, 0xA4) use int32 (4 bytes) for angle,
  // placed at DATA[4]-DATA[7] of the CAN frame. Only the READ response (0x92)
  // uses 7-byte int64 — see decode_multi_turn_angle() for that path.
  double degrees = radians * RADIANS_TO_DEGREES;
  int64_t angle_centidegrees = static_cast<int64_t>(degrees * 100.0);

  // Overflow check: reject values outside int32 range
  if (angle_centidegrees > INT32_MAX || angle_centidegrees < INT32_MIN) {
    // Return empty vector to signal overflow error
    return std::vector<uint8_t>();
  }

  int32_t angle_i32 = static_cast<int32_t>(angle_centidegrees);

  // Pack as int32 little-endian, 4 bytes
  std::vector<uint8_t> bytes(4);
  for (int i = 0; i < 4; ++i) {
    bytes[i] = static_cast<uint8_t>((angle_i32 >> (i * 8)) & 0xFF);
  }

  return bytes;
}

double MG6010Protocol::decode_multi_turn_angle(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  // Motor returns 0.01° units (centidegrees) for multi-turn angle
  // LK-TECH V2.35: 7 bytes (56-bit signed integer), little-endian
  if (data.size() < offset + 7) {
    return 0.0;
  }

  int64_t angle_centidegrees = 0;
  for (int i = 0; i < 7; ++i) {
    angle_centidegrees |= static_cast<int64_t>(data[offset + i]) << (i * 8);
  }
  // Sign-extend from 56 bits to 64 bits
  if (angle_centidegrees & (static_cast<int64_t>(1) << 55)) {
    angle_centidegrees |= static_cast<int64_t>(0xFF) << 56;
  }

  // Convert centidegrees to degrees, then to radians
  double degrees = static_cast<double>(angle_centidegrees) * 0.01;
  return degrees * DEGREES_TO_RADIANS;
}

std::vector<uint8_t> MG6010Protocol::encode_single_turn_angle(double radians) const
{
  // Normalize to 0-2π range
  double normalized = std::fmod(radians, 2.0 * M_PI);
  if (normalized < 0) {
    normalized += 2.0 * M_PI;
  }

  // Convert to degrees (0-360), then to 0.01 degree units
  double degrees = normalized * RADIANS_TO_DEGREES;
  uint32_t angle_0_01deg = static_cast<uint32_t>(degrees * 100.0);

  // Clamp to 0-35999 per official spec
  if (angle_0_01deg > 35999) {
    angle_0_01deg = 35999;
  }

  // Pack as uint32 little-endian
  std::vector<uint8_t> bytes;
  bytes.push_back(static_cast<uint8_t>(angle_0_01deg & 0xFF));
  bytes.push_back(static_cast<uint8_t>((angle_0_01deg >> 8) & 0xFF));
  bytes.push_back(static_cast<uint8_t>((angle_0_01deg >> 16) & 0xFF));
  bytes.push_back(static_cast<uint8_t>((angle_0_01deg >> 24) & 0xFF));

  return bytes;
}

double MG6010Protocol::decode_single_turn_angle(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  // Official spec: 4 bytes (uint32), 0.01°/LSB, range 0-35999
  if (data.size() < offset + 4) {
    return 0.0;
  }

  uint32_t angle_raw = static_cast<uint32_t>(data[offset]) |
                       (static_cast<uint32_t>(data[offset + 1]) << 8) |
                       (static_cast<uint32_t>(data[offset + 2]) << 16) |
                       (static_cast<uint32_t>(data[offset + 3]) << 24);

  // Convert from 0.01 degrees to radians
  double degrees = static_cast<double>(angle_raw) * 0.01;
  return degrees * DEGREES_TO_RADIANS;
}

std::vector<uint8_t> MG6010Protocol::encode_speed(double rad_per_sec) const
{
  // Convert to dps, then to 0.01 dps units (int32)
  double dps = rad_per_sec * RAD_PER_SEC_TO_DPS;
  int32_t speed_0_01dps = static_cast<int32_t>(dps * 100.0);

  // Pack as int32 little-endian
  std::vector<uint8_t> bytes;
  bytes.push_back(static_cast<uint8_t>(speed_0_01dps & 0xFF));
  bytes.push_back(static_cast<uint8_t>((speed_0_01dps >> 8) & 0xFF));
  bytes.push_back(static_cast<uint8_t>((speed_0_01dps >> 16) & 0xFF));
  bytes.push_back(static_cast<uint8_t>((speed_0_01dps >> 24) & 0xFF));

  return bytes;
}

double MG6010Protocol::decode_speed(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  // Speed: int16_t in dps (not 0.01dps for response!)
  if (data.size() < offset + 2) {
    return 0.0;
  }

  int16_t speed_dps = static_cast<int16_t>(data[offset] | (data[offset + 1] << 8));
  return static_cast<double>(speed_dps) * DPS_TO_RAD_PER_SEC;
}

std::vector<uint8_t> MG6010Protocol::encode_torque(double amps) const
{
  // Torque: int16_t, -2048~2048 = -33A~33A (for MG series)
  double ratio = 2048.0 / 33.0;
  int16_t torque_raw = static_cast<int16_t>(amps * ratio);

  // Clamp
  if (torque_raw > 2048) {
    std::cerr << "[MG6010Protocol] WARNING: torque value " << amps
              << " A clamped to max (2048 raw = 33A)" << std::endl;
    torque_raw = 2048;
  }
  if (torque_raw < -2048) {
    std::cerr << "[MG6010Protocol] WARNING: torque value " << amps
              << " A clamped to min (-2048 raw = -33A)" << std::endl;
    torque_raw = -2048;
  }

  // Cast to unsigned before shifting to avoid undefined behavior with negative values
  uint16_t torque_unsigned = static_cast<uint16_t>(torque_raw);

  std::vector<uint8_t> bytes;
  bytes.push_back(static_cast<uint8_t>(torque_unsigned & 0xFF));
  bytes.push_back(static_cast<uint8_t>((torque_unsigned >> 8) & 0xFF));

  return bytes;
}

double MG6010Protocol::decode_torque(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  if (data.size() < offset + 2) {
    return 0.0;
  }

  int16_t torque_raw = static_cast<int16_t>(data[offset] | (data[offset + 1] << 8));

  // Convert from -2048~2048 to -33A~33A
  double ratio = 33.0 / 2048.0;
  return static_cast<double>(torque_raw) * ratio;
}

std::vector<uint8_t> MG6010Protocol::encode_acceleration(double rad_per_sec2) const
{
  // Acceleration: int32_t, 1 dps/s per LSB
  double dps_per_sec = rad_per_sec2 * RAD_PER_SEC_TO_DPS;
  int32_t accel = static_cast<int32_t>(dps_per_sec);

  std::vector<uint8_t> bytes;
  bytes.push_back(static_cast<uint8_t>(accel & 0xFF));
  bytes.push_back(static_cast<uint8_t>((accel >> 8) & 0xFF));
  bytes.push_back(static_cast<uint8_t>((accel >> 16) & 0xFF));
  bytes.push_back(static_cast<uint8_t>((accel >> 24) & 0xFF));

  return bytes;
}

double MG6010Protocol::decode_acceleration(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  if (data.size() < offset + 4) {
    return 0.0;
  }

  int32_t accel = static_cast<int32_t>(data[offset]) |
                  (static_cast<int32_t>(data[offset + 1]) << 8) |
                  (static_cast<int32_t>(data[offset + 2]) << 16) |
                  (static_cast<int32_t>(data[offset + 3]) << 24);

  // Convert from dps/s to rad/s²
  return static_cast<double>(accel) * DPS_TO_RAD_PER_SEC;
}

double MG6010Protocol::decode_temperature(uint8_t temp_byte) const
{
  // Temperature: int8_t, 1°C/LSB
  return static_cast<double>(static_cast<int8_t>(temp_byte));
}

double MG6010Protocol::decode_voltage(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  // Voltage: uint16_t, 0.01V/LSB (10mV resolution)
  if (data.size() < offset + 2) {
    return 0.0;
  }

  uint16_t voltage_raw = static_cast<uint16_t>(data[offset] | (data[offset + 1] << 8));
  return static_cast<double>(voltage_raw) * 0.01;
}

double MG6010Protocol::decode_phase_current(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  // Phase current: int16_t, 1A/64LSB
  if (data.size() < offset + 2) {
    return 0.0;
  }

  int16_t current_raw = static_cast<int16_t>(data[offset] | (data[offset + 1] << 8));
  return static_cast<double>(current_raw) / 64.0;
}

uint16_t MG6010Protocol::decode_encoder(
  const std::vector<uint8_t> & data,
  size_t offset) const
{
  if (data.size() < offset + 2) {
    return 0;
  }

  return static_cast<uint16_t>(data[offset] | (data[offset + 1] << 8));
}

} // namespace motor_control_ros2
