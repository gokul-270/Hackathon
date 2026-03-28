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

#ifndef ODRIVE_CONTROL_ROS2__GENERIC_MOTOR_CONTROLLER_HPP_
#define ODRIVE_CONTROL_ROS2__GENERIC_MOTOR_CONTROLLER_HPP_

/*
 * Generic Motor Controller Implementation
 *
 * This file implements a generic MotorControllerInterface that can support
 * multiple motor types (MG6010, MG4040, and other CANopen motors),
 * providing a unified interface that can be seamlessly swapped with ODrive
 * motors without changing application-level code.
 *
 * Key Features:
 * - Support for multiple motor types (MG6010, MG4040, etc.)
 * - CANopen protocol support
 * - Higher precision positioning capabilities
 * - Integrated homing and calibration
 * - Configurable voltage systems (24V, 48V, etc.)
 */

#pragma once

#include "motor_control_ros2/motor_abstraction.hpp"
#include <memory>
#include <chrono>
#include <string>
#include <mutex>
#include <map>
#include <vector>

struct can_frame;

namespace motor_control_ros2
{

/**
 * @brief Generic CAN interface implementation for CANopen motors
 *
 * Handles CANopen protocol communication for multiple motor types
 * (MG6010, MG4040, and other CANopen-compatible motors)
 */
class GenericCANInterface : public CANInterface
{
public:
  GenericCANInterface();
  virtual ~GenericCANInterface();

  // CANInterface implementation
  bool initialize(const std::string & interface_name, uint32_t baud_rate = 1000000) override;
  bool send_message(uint32_t id, const std::vector<uint8_t> & data) override;
  bool receive_message(uint32_t & id, std::vector<uint8_t> & data, int timeout_ms = 10) override;
  bool configure_node(uint8_t node_id, uint32_t baud_rate = 0) override;
  bool is_connected() const override;
  std::string get_last_error() const override;

  // CANopen protocol methods
  bool send_sdo_request(
    uint8_t node_id, uint16_t index, uint8_t subindex,
    const std::vector<uint8_t> & data);
  bool receive_sdo_response(
    uint8_t node_id, uint16_t & index, uint8_t & subindex,
    std::vector<uint8_t> & data);
  bool send_pdo(uint8_t node_id, uint8_t pdo_number, const std::vector<uint8_t> & data);

private:
  std::string interface_name_;
  uint32_t baud_rate_;
  bool connected_;
  std::string last_error_;
  mutable std::mutex mutex_;

  // CAN socket handling
  int can_socket_;
  void setup_can_socket();
  void close_can_socket();

  // CANopen protocol helpers
  uint32_t get_cob_id(uint8_t function_code, uint8_t node_id);
  bool parse_can_frame(
    const struct can_frame & frame, uint32_t & id,
    std::vector<uint8_t> & data);
};

/**
 * @brief Generic motor controller implementation for CANopen motors
 *
 * This class implements the MotorControllerInterface for multiple CANopen motor types
 * (MG6010, MG4040, etc.), providing seamless integration with the abstraction layer
 * while leveraging the enhanced capabilities of modern motor controllers.
 */
class GenericMotorController : public MotorControllerInterface
{
public:
  GenericMotorController();
  virtual ~GenericMotorController();

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
  bool emergency_stop() override;
  bool clear_errors() override;

  bool calibrate_motor() override;
  bool calibrate_encoder() override;
  bool needs_calibration() const override;

  MotorConfiguration get_configuration() const override;

  // Enhanced error handling methods
  const ErrorFramework::ErrorInfo & get_error_info() const override;
  std::vector<ErrorFramework::ErrorInfo> get_error_history() const override;
  ErrorFramework::RecoveryResult attempt_error_recovery() override;
  void set_error_handler(std::function<void(const ErrorFramework::ErrorInfo &)> handler) override;

  // CANopen motor-specific methods
  bool set_operation_mode(uint8_t mode);
  bool get_device_status(uint16_t & status_word);
  bool set_control_word(uint16_t control_word);
  bool get_actual_position(int32_t & position);
  bool get_actual_velocity(int32_t & velocity);
  bool get_actual_torque(int16_t & torque);
  bool set_target_position(int32_t position);
  bool set_target_velocity(int32_t velocity);
  bool set_target_torque(int16_t torque);

  // Power management methods (configurable voltage)
  bool check_voltage_levels();
  bool set_power_limits(double max_current, double max_power);
  bool get_temperature_status(double & motor_temp, double & driver_temp);

private:
  // Configuration and state
  MotorConfiguration config_;
  std::shared_ptr<CANInterface> can_interface_;

  // Motor controller state
  bool initialized_;
  bool homed_;
  bool calibrated_;
  bool enabled_;
  mutable std::mutex state_mutex_;

  // Position tracking (in encoder counts)
  int32_t current_position_counts_;
  int32_t current_velocity_counts_;
  int16_t current_torque_counts_;
  double current_position_;
  double current_velocity_;
  double current_torque_;
  std::chrono::steady_clock::time_point last_position_time_;

  // CANopen device parameters
  uint8_t node_id_;
  uint8_t current_operation_mode_;
  uint16_t status_word_;
  uint16_t control_word_;

  // Power management (configurable voltage)
  double bus_voltage_;
  double max_current_;
  double max_power_;
  bool voltage_warning_active_;

  // Safety and error handling
  MotorStatus::State motor_state_;
  uint32_t last_error_code_;
  std::string last_error_message_;
  std::chrono::steady_clock::time_point last_status_update_;

  // Conversion factors
  double counts_per_revolution_;
  double position_factor_;  // Convert counts to radians
  double velocity_factor_;  // Convert counts/s to rad/s
  double torque_factor_;    // Convert internal units to Nm

  // Error handling callback
  std::function<void(const ErrorFramework::ErrorInfo &)> error_handler_callback_;

  // Helper methods
  bool send_sdo_write(uint16_t index, uint8_t subindex, const std::vector<uint8_t> & data);
  bool send_sdo_read(uint16_t index, uint8_t subindex, std::vector<uint8_t> & data);
  bool wait_for_status_change(uint16_t expected_status, uint16_t mask, int timeout_ms = 5000);
  bool perform_state_machine_transition(uint16_t target_state);

  // Position/velocity conversion helpers
  int32_t radians_to_counts(double radians);
  double counts_to_radians(int32_t counts);
  int32_t rad_per_sec_to_counts_per_sec(double rad_per_sec);
  double counts_per_sec_to_rad_per_sec(int32_t counts_per_sec);

  // CANopen state machine helpers
  bool switch_to_operation_enabled();
  bool switch_to_switched_on();
  bool switch_to_ready_to_switch_on();
  bool perform_quick_stop();

  // Homing implementation
  bool perform_canopen_homing(const HomingConfig & homing_config);
  bool set_homing_method(uint8_t method);
  bool start_homing();
  bool wait_for_homing_complete(double timeout_seconds);

  // Error handling
  void update_motor_status();
  MotorStatus::State canopen_state_to_motor_status(uint16_t status_word);
  bool handle_canopen_fault();

  // Power monitoring
  bool monitor_power_levels();
  bool check_voltage_range();

  // Constants for CANopen communication

  // CANopen Object Dictionary Indices (standard CANopen)
  static constexpr uint16_t OD_DEVICE_TYPE = 0x1000;
  static constexpr uint16_t OD_ERROR_REGISTER = 0x1001;
  static constexpr uint16_t OD_MANUFACTURER_STATUS = 0x1002;
  static constexpr uint16_t OD_IDENTITY_OBJECT = 0x1018;

  // Control and Status
  static constexpr uint16_t OD_CONTROL_WORD = 0x6040;
  static constexpr uint16_t OD_STATUS_WORD = 0x6041;
  static constexpr uint16_t OD_OPERATION_MODE = 0x6060;
  static constexpr uint16_t OD_OPERATION_MODE_DISPLAY = 0x6061;

  // Position Control
  static constexpr uint16_t OD_POSITION_DEMAND = 0x6062;
  static constexpr uint16_t OD_POSITION_ACTUAL = 0x6064;
  static constexpr uint16_t OD_POSITION_WINDOW = 0x6067;
  static constexpr uint16_t OD_POSITION_WINDOW_TIME = 0x6068;
  static constexpr uint16_t OD_TARGET_POSITION = 0x607A;

  // Velocity Control
  static constexpr uint16_t OD_VELOCITY_DEMAND = 0x606B;
  static constexpr uint16_t OD_VELOCITY_ACTUAL = 0x606C;
  static constexpr uint16_t OD_TARGET_VELOCITY = 0x60FF;

  // Torque Control
  static constexpr uint16_t OD_TORQUE_DEMAND = 0x6071;
  static constexpr uint16_t OD_TORQUE_ACTUAL = 0x6077;
  static constexpr uint16_t OD_TARGET_TORQUE = 0x6071;

  // Homing
  static constexpr uint16_t OD_HOME_OFFSET = 0x607C;
  static constexpr uint16_t OD_HOMING_METHOD = 0x6098;
  static constexpr uint16_t OD_HOMING_SPEEDS = 0x6099;
  static constexpr uint16_t OD_HOMING_ACCELERATION = 0x609A;

  // Motor Parameters
  static constexpr uint16_t OD_MOTOR_RATED_CURRENT = 0x6075;
  static constexpr uint16_t OD_MOTOR_RATED_TORQUE = 0x6076;
  static constexpr uint16_t OD_MAX_CURRENT = 0x6073;
  static constexpr uint16_t OD_MAX_TORQUE = 0x6072;

  // 48V Power Specific
  static constexpr uint16_t OD_DC_LINK_VOLTAGE = 0x6079;
  static constexpr uint16_t OD_MAX_PROFILE_VELOCITY = 0x607F;

  // Operation Modes
  static constexpr uint8_t OM_PROFILE_POSITION = 1;
  static constexpr uint8_t OM_VELOCITY = 2;
  static constexpr uint8_t OM_PROFILE_VELOCITY = 3;
  static constexpr uint8_t OM_TORQUE_PROFILE = 4;
  static constexpr uint8_t OM_HOMING = 6;
  static constexpr uint8_t OM_CYCLIC_SYNC_POSITION = 8;
  static constexpr uint8_t OM_CYCLIC_SYNC_VELOCITY = 9;
  static constexpr uint8_t OM_CYCLIC_SYNC_TORQUE = 10;

  // Status Word Bit Masks
  static constexpr uint16_t SW_READY_TO_SWITCH_ON = 0x0001;
  static constexpr uint16_t SW_SWITCHED_ON = 0x0002;
  static constexpr uint16_t SW_OPERATION_ENABLED = 0x0004;
  static constexpr uint16_t SW_FAULT = 0x0008;
  static constexpr uint16_t SW_VOLTAGE_ENABLED = 0x0010;
  static constexpr uint16_t SW_QUICK_STOP = 0x0020;
  static constexpr uint16_t SW_SWITCH_ON_DISABLED = 0x0040;
  static constexpr uint16_t SW_WARNING = 0x0080;
  static constexpr uint16_t SW_TARGET_REACHED = 0x0400;
  static constexpr uint16_t SW_INTERNAL_LIMIT = 0x0800;
  static constexpr uint16_t SW_HOMING_ATTAINED = 0x1000;
  static constexpr uint16_t SW_HOMING_ERROR = 0x2000;

  // Control Word Commands
  static constexpr uint16_t CW_SWITCH_ON = 0x0007;
  static constexpr uint16_t CW_ENABLE_OPERATION = 0x000F;
  static constexpr uint16_t CW_DISABLE_VOLTAGE = 0x0000;
  static constexpr uint16_t CW_QUICK_STOP = 0x0002;
  static constexpr uint16_t CW_DISABLE_OPERATION = 0x0007;
  static constexpr uint16_t CW_ENABLE_OPERATION_NEW_SETPOINT = 0x001F;
  static constexpr uint16_t CW_START_HOMING = 0x001F;

  // 48V Voltage Limits
  static constexpr double MIN_48V_VOLTAGE = 44.0;  // Minimum safe voltage
  static constexpr double MAX_48V_VOLTAGE = 52.0;  // Maximum safe voltage
  static constexpr double NOMINAL_48V_VOLTAGE = 48.0;  // Nominal voltage
};

/**
 * @brief Factory function for creating generic motor controllers
 */
std::shared_ptr<MotorControllerInterface> create_generic_motor_controller();

} // namespace motor_control_ros2

#endif // ODRIVE_CONTROL_ROS2__GENERIC_MOTOR_CONTROLLER_HPP_
