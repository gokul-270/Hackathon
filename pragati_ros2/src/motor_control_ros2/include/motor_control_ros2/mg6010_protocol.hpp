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
 * This implements the official LK-TECH CAN Protocol V2.35 for MG6010-i6 motors.
 * Based on tested implementation from colleague code and official documentation.
 *
 * Key differences from CANopen:
 * - Uses proprietary protocol, not CANopen SDO/PDO
 * - Arbitration ID: 0x140 + motor_id (1-32)
 * - Default baud rate: 500kbps (Pragati configuration)
 * - Fast response time: ~0.25ms typical
 * - Multi-turn angle: int64_t (7 bytes), 0.01°/LSB
 * - Single-turn angle: uint32_t (4 bytes), 0.01°/LSB, range 0-35999
 * - PID parameters: uint8_t (not float)
 *
 * References:
 * - LK-TECH CAN Protocol V2.35 (CANprotocal.pdf)
 * - Tested implementation: mg_can_compat.cpp/hpp
 */

#ifndef ODRIVE_CONTROL_ROS2__MG6010_PROTOCOL_HPP_
#define ODRIVE_CONTROL_ROS2__MG6010_PROTOCOL_HPP_

#pragma once

#define _USE_MATH_DEFINES
#include <cmath>
#include "motor_control_ros2/motor_abstraction.hpp"
#include <memory>
#include <vector>
#include <cstdint>
#include <string>

namespace motor_control_ros2
{

/**
 * @brief MG6010-i6 Motor Protocol Handler
 *
 * Implements the official LK-TECH CAN protocol for MG6010 motors.
 * This is a lightweight wrapper around CANInterface that handles
 * MG-specific command encoding/decoding without introducing CANopen.
 */
class MG6010Protocol
{
public:
  // Command codes (from official LK-TECH protocol V2.35)
  static constexpr uint8_t CMD_MOTOR_OFF = 0x80;
  static constexpr uint8_t CMD_MOTOR_ON = 0x88;
  static constexpr uint8_t CMD_MOTOR_STOP = 0x81;

  // Control commands
  static constexpr uint8_t CMD_TORQUE_CLOSED_LOOP = 0xA1;  // -2048~2048 = -33A~33A
  static constexpr uint8_t CMD_SPEED_CLOSED_LOOP = 0xA2;   // int32_t, 0.01dps/LSB
  static constexpr uint8_t CMD_MULTI_LOOP_ANGLE_1 = 0xA3;
  static constexpr uint8_t CMD_MULTI_LOOP_ANGLE_2 = 0xA4;
  static constexpr uint8_t CMD_SINGLE_LOOP_ANGLE_1 = 0xA5;
  static constexpr uint8_t CMD_SINGLE_LOOP_ANGLE_2 = 0xA6;
  static constexpr uint8_t CMD_INCREMENT_ANGLE_1 = 0xA7;
  static constexpr uint8_t CMD_INCREMENT_ANGLE_2 = 0xA8;

  // PID and acceleration
  static constexpr uint8_t CMD_READ_PID = 0x30;
  static constexpr uint8_t CMD_WRITE_PID_RAM = 0x31;
  static constexpr uint8_t CMD_WRITE_PID_ROM = 0x32;
  static constexpr uint8_t CMD_READ_ACCEL = 0x33;
  static constexpr uint8_t CMD_WRITE_ACCEL_RAM = 0x34;
  static constexpr uint8_t CMD_READ_MAX_TORQUE = 0x37;
  static constexpr uint8_t CMD_WRITE_MAX_TORQUE_RAM = 0x38;

  // Encoder commands
  static constexpr uint8_t CMD_READ_ENCODER = 0x90;
  static constexpr uint8_t CMD_WRITE_ENCODER_OFFSET_ROM = 0x91;
  static constexpr uint8_t CMD_SET_ZERO_ROM = 0x19;

  // Status and angle reading
  static constexpr uint8_t CMD_READ_MULTI_TURN_ANGLE = 0x92;
  static constexpr uint8_t CMD_READ_SINGLE_TURN_ANGLE = 0x94;
  static constexpr uint8_t CMD_READ_STATUS_1 = 0x9A;  // temp, voltage, errors
  static constexpr uint8_t CMD_CLEAR_ERRORS = 0x9B;
  static constexpr uint8_t CMD_READ_STATUS_2 = 0x9C;  // temp, iq, speed, encoder
  static constexpr uint8_t CMD_READ_STATUS_3 = 0x9D;  // temp, phase currents A/B/C

  // Base arbitration ID for commands (add motor_id: 1-32)
  static constexpr uint32_t BASE_ARBITRATION_ID = 0x140;

  // Multi-motor broadcast ID (up to 4 motors)
  static constexpr uint32_t MULTI_MOTOR_BROADCAST_ID = 0x280;

  // Error bit masks (from STATUS_1)
  static constexpr uint8_t ERROR_VOLTAGE = 0x01;  // bit 0
  static constexpr uint8_t ERROR_TEMPERATURE = 0x08;  // bit 3

  /**
   * @brief Motor status data structure
   */
  struct Status
  {
    double voltage{0.0};           // Volts
    double temperature{0.0};       // Celsius
    uint32_t error_flags{0};       // Error bits
    bool motor_running{false};     // Motor state
    double torque_current{0.0};    // Amps
    double speed{0.0};             // rad/s
    uint16_t encoder_position{0};  // Raw encoder value
    double phase_current_a{0.0};   // Phase A current (Amps)
    double phase_current_b{0.0};   // Phase B current (Amps)
    double phase_current_c{0.0};   // Phase C current (Amps)
  };

  /**
   * @brief PID parameters (uint8_t as per official spec)
   */
  struct PIDParams
  {
    uint8_t angle_kp;
    uint8_t angle_ki;
    uint8_t speed_kp;
    uint8_t speed_ki;
    uint8_t current_kp;
    uint8_t current_ki;
  };

  /**
   * @brief Constructor
   */
  MG6010Protocol();

  /**
   * @brief Destructor
   */
  virtual ~MG6010Protocol();

  /**
   * @brief Initialize the protocol handler
   *
   * @param can Shared pointer to CANInterface (reuses existing socket)
   * @param node_id Motor ID (1-32)
   * @param baud_rate CAN baud rate (default 500kbps; configured externally on SocketCAN)
   * @return true if initialized successfully
   */
  bool initialize(std::shared_ptr<CANInterface> can, uint8_t node_id, uint32_t baud_rate = 500000);

  /**
   * @brief Check if protocol is initialized
   */
  bool is_initialized() const { return initialized_; }

  /**
   * @brief Get motor node ID
   */
  uint8_t get_node_id() const { return node_id_; }

  // Basic motor control
  bool motor_on();
  bool motor_off();
  bool motor_stop();

  // Position control (multi-turn and single-turn)
  bool set_absolute_position(double radians);
  bool set_absolute_position_with_speed(double radians, double max_speed_rad_s);
  bool set_single_turn_position(double radians, uint8_t spin_direction = 0);
  bool set_single_turn_position_with_speed(double radians, double max_speed_rad_s, uint8_t spin_direction = 0);
  bool set_incremental_position(double radians);
  bool set_incremental_position_with_speed(double radians, double max_speed_rad_s);

  // Velocity control
  bool speed_closed_loop_control(double rad_per_sec);

  // Torque control
  bool torque_closed_loop_control(double torque_amps);

  // PID configuration
  bool set_pid(const PIDParams & pid);
  bool read_pid(PIDParams & pid);
  bool write_pid_to_rom(const PIDParams & pid);

  // Acceleration configuration
  bool set_acceleration(double rad_per_sec2);
  bool read_acceleration(double & rad_per_sec2);

  // Max torque current ratio configuration
  bool read_max_torque_current(uint16_t & ratio);
  bool write_max_torque_current_ram(uint16_t ratio);

  // Status reading
  bool read_status(Status & status, int max_retries = -1);
  bool read_status_detailed(Status & status, int max_retries = -1);  // Uses STATUS_2 with more details
  bool read_status_phase_currents(Status & status);  // Uses STATUS_3 (phase currents A/B/C)

  // Angle reading
  bool read_multi_turn_angle(double & angle_radians, int max_retries = -1);
  bool read_single_turn_angle(double & angle_radians);

  // Encoder operations
  bool read_encoder(uint16_t & encoder_value, uint16_t & encoder_raw, uint16_t & encoder_offset);
  bool write_encoder_offset_to_rom(uint16_t offset);
  bool set_current_position_as_zero();

  // Error handling
  bool clear_errors();
  bool read_errors(uint32_t & error_flags);

  /**
   * @brief Get last error message
   */
  std::string get_last_error() const { return last_error_; }

private:
  // State
  std::shared_ptr<CANInterface> can_interface_;
  uint8_t node_id_;
  uint32_t baud_rate_;
  bool initialized_;
  std::string last_error_;
  int default_timeout_ms_;
  int num_retries_;

  // Low-level communication helpers
  bool send_command(uint8_t cmd, const std::vector<uint8_t> & payload);
  bool wait_response(uint8_t expected_cmd, std::vector<uint8_t> & payload, int timeout_ms);
  bool send_and_wait(uint8_t cmd, const std::vector<uint8_t> & tx_payload,
                     std::vector<uint8_t> & rx_payload, int timeout_ms = -1,
                     int max_retries = -1);

  // Frame construction/parsing
  uint32_t make_arbitration_id(uint8_t cmd) const;
  std::vector<uint8_t> make_frame(uint8_t cmd, const std::vector<uint8_t> & payload) const;
  bool parse_response(const std::vector<uint8_t> & data, uint8_t & cmd,
                      std::vector<uint8_t> & payload) const;

  // Data encoding/decoding helpers
  // Multi-turn angle: int64_t (7 bytes), 0.01°/LSB
  std::vector<uint8_t> encode_multi_turn_angle(double radians) const;
  double decode_multi_turn_angle(const std::vector<uint8_t> & data, size_t offset) const;

  // Single-turn angle: uint32_t (4 bytes), 0.01°/LSB, range 0-35999
  std::vector<uint8_t> encode_single_turn_angle(double radians) const;
  double decode_single_turn_angle(const std::vector<uint8_t> & data, size_t offset) const;

  // Speed: int32_t, 0.01dps/LSB
  std::vector<uint8_t> encode_speed(double rad_per_sec) const;
  double decode_speed(const std::vector<uint8_t> & data, size_t offset) const;

  // Torque: int16_t, -2048~2048 = -33A~33A (for MG series)
  std::vector<uint8_t> encode_torque(double amps) const;
  double decode_torque(const std::vector<uint8_t> & data, size_t offset) const;

  // Acceleration: int32_t, 1dps/s/LSB
  std::vector<uint8_t> encode_acceleration(double rad_per_sec2) const;
  double decode_acceleration(const std::vector<uint8_t> & data, size_t offset) const;

  // Temperature: int8_t, 1°C/LSB
  double decode_temperature(uint8_t temp_byte) const;

  // Voltage: uint16_t, 0.01V/LSB (10mV resolution, matches decode at mg6010_protocol.cpp:947)
  double decode_voltage(const std::vector<uint8_t> & data, size_t offset) const;

  // Phase currents: int16_t, 1A/64LSB
  double decode_phase_current(const std::vector<uint8_t> & data, size_t offset) const;

  // Encoder position: uint16_t
  uint16_t decode_encoder(const std::vector<uint8_t> & data, size_t offset) const;

  // Unit conversion constants
  static constexpr double DEGREES_TO_RADIANS = 3.14159265358979323846 / 180.0;
  static constexpr double RADIANS_TO_DEGREES = 180.0 / 3.14159265358979323846;
  static constexpr double DPS_TO_RAD_PER_SEC = 3.14159265358979323846 / 180.0;
  static constexpr double RAD_PER_SEC_TO_DPS = 180.0 / 3.14159265358979323846;
};

} // namespace motor_control_ros2

#endif // ODRIVE_CONTROL_ROS2__MG6010_PROTOCOL_HPP_
