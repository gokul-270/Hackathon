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
 * Generic Motor Controller Implementation
 *
 * This file implements a generic motor controller using the motor abstraction layer.
 * It provides CANopen protocol support for multiple motor types (MG6010, MG4040, etc.)
 * and leverages the enhanced capabilities of modern motor controllers.
 */

#include "motor_control_ros2/generic_motor_controller.hpp"
#include <rclcpp/rclcpp.hpp>
#include <iostream>
#include <cmath>
#include <thread>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <unistd.h>
#include <cstring>

namespace motor_control_ros2
{

// GenericCANInterface implementation
GenericCANInterface::GenericCANInterface()
: interface_name_("can0")
  , baud_rate_(1000000)
  , connected_(false)
  , last_error_("")
  , can_socket_(-1)
{
}

GenericCANInterface::~GenericCANInterface()
{
  close_can_socket();
}

bool GenericCANInterface::initialize(const std::string & interface_name, uint32_t baud_rate)
{
  std::lock_guard<std::mutex> lock(mutex_);

  interface_name_ = interface_name;
  baud_rate_ = baud_rate;

  try {
    setup_can_socket();
    connected_ = true;
    last_error_ = "";
    RCLCPP_INFO(rclcpp::get_logger("motor_control"),
      "Generic CAN interface initialized on %s at %u bps",
      interface_name_.c_str(), baud_rate_);
    return true;
  } catch (const std::exception & e) {
    last_error_ = std::string("CAN initialization failed: ") + e.what();
    connected_ = false;
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "%s", last_error_.c_str());
    return false;
  }
}

bool GenericCANInterface::send_message(uint32_t id, const std::vector<uint8_t> & data)
{
  std::lock_guard<std::mutex> lock(mutex_);

  if (!connected_ || can_socket_ < 0) {
    last_error_ = "CAN interface not connected";
    return false;
  }

  if (data.size() > 8) {
    last_error_ = "CAN message data too long (max 8 bytes)";
    return false;
  }

  struct ::can_frame frame;
  frame.can_id = id;
  frame.can_dlc = data.size();
  std::memcpy(frame.data, data.data(), data.size());

  ssize_t bytes_sent = write(can_socket_, &frame, sizeof(frame));
  if (bytes_sent != sizeof(frame)) {
    last_error_ = "Failed to send CAN message";
    return false;
  }

  return true;
}

bool GenericCANInterface::receive_message(
  uint32_t & id, std::vector<uint8_t> & data,
  int timeout_ms)
{
  std::lock_guard<std::mutex> lock(mutex_);

  if (!connected_ || can_socket_ < 0) {
    last_error_ = "CAN interface not connected";
    return false;
  }

  // Set socket timeout
  struct timeval timeout;
  timeout.tv_sec = timeout_ms / 1000;
  timeout.tv_usec = (timeout_ms % 1000) * 1000;

  if (setsockopt(can_socket_, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) {
    last_error_ = "Failed to set socket timeout";
    return false;
  }

  struct ::can_frame frame;
  ssize_t bytes_received = read(can_socket_, &frame, sizeof(frame));

  if (bytes_received == sizeof(frame)) {
    id = frame.can_id;
    data.assign(frame.data, frame.data + frame.can_dlc);
    return true;
  }

  return false; // Timeout or error
}

bool GenericCANInterface::configure_node(uint8_t node_id, uint32_t baud_rate)
{
  (void)node_id;   // MG6010 node configuration done via SDO
  (void)baud_rate; // Baud rate set during interface initialization

  std::lock_guard<std::mutex> lock(mutex_);

  if (!connected_) {
    last_error_ = "CAN interface not connected";
    return false;
  }

  // MG6010 node configuration would be done via SDO messages
  return true;
}

bool GenericCANInterface::is_connected() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return connected_;
}

std::string GenericCANInterface::get_last_error() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return last_error_;
}

bool GenericCANInterface::send_sdo_request(
  uint8_t node_id, uint16_t index, uint8_t subindex,
  const std::vector<uint8_t> & data)
{
  uint32_t cob_id = get_cob_id(0x6, node_id); // SDO request COB-ID

  std::vector<uint8_t> sdo_data;
  if (data.empty()) {
    // SDO read request
    sdo_data = {0x40, static_cast<uint8_t>(index & 0xFF), static_cast<uint8_t>(index >> 8),
      subindex, 0, 0, 0, 0};
  } else {
    // SDO write request (expedited transfer for <= 4 bytes)
    if (data.size() <= 4) {
      sdo_data = {static_cast<uint8_t>(0x23 | ((4 - data.size()) << 2)),
        static_cast<uint8_t>(index & 0xFF),
        static_cast<uint8_t>(index >> 8),
        subindex, 0, 0, 0, 0};
      std::copy(data.begin(), data.end(), sdo_data.begin() + 4);
    } else {
      last_error_ = "SDO segmented transfer not implemented";
      return false;
    }
  }

  return send_message(cob_id, sdo_data);
}

bool GenericCANInterface::receive_sdo_response(
  uint8_t node_id, uint16_t & index,
  uint8_t & subindex, std::vector<uint8_t> & data)
{
  uint32_t expected_cob_id = get_cob_id(0x5, node_id); // SDO response COB-ID
  uint32_t received_id;
  std::vector<uint8_t> received_data;

  if (receive_message(received_id, received_data, 100)) { // 100ms timeout
    if (received_id == expected_cob_id && received_data.size() >= 4) {
      uint8_t command = received_data[0];
      index = received_data[1] | (received_data[2] << 8);
      subindex = received_data[3];

      if ((command & 0x80) == 0) { // Success response
        if ((command & 0x02) == 0) { // Expedited transfer
          size_t data_size = 4 - ((command >> 2) & 0x3);
          data.assign(received_data.begin() + 4, received_data.begin() + 4 + data_size);
        }
        return true;
      } else {
        // Error response
        last_error_ = "SDO error response received";
        return false;
      }
    }
  }

  return false;
}

bool GenericCANInterface::send_pdo(
  uint8_t node_id, uint8_t pdo_number,
  const std::vector<uint8_t> & data)
{
  uint32_t cob_id;
  switch (pdo_number) {
    case 1: cob_id = 0x180 + node_id; break; // TPDO1
    case 2: cob_id = 0x280 + node_id; break; // TPDO2
    case 3: cob_id = 0x380 + node_id; break; // TPDO3
    case 4: cob_id = 0x480 + node_id; break; // TPDO4
    default:
      last_error_ = "Invalid PDO number";
      return false;
  }

  return send_message(cob_id, data);
}

void GenericCANInterface::setup_can_socket()
{
  can_socket_ = socket(PF_CAN, SOCK_RAW, CAN_RAW);
  if (can_socket_ < 0) {
    throw std::runtime_error("Failed to create CAN socket");
  }

  struct ifreq ifr;
  strcpy(ifr.ifr_name, interface_name_.c_str());
  ioctl(can_socket_, SIOCGIFINDEX, &ifr);

  struct sockaddr_can addr;
  addr.can_family = AF_CAN;
  addr.can_ifindex = ifr.ifr_ifindex;

  if (bind(can_socket_, reinterpret_cast<struct sockaddr *>(&addr), sizeof(addr)) < 0) {
    close(can_socket_);
    can_socket_ = -1;
    throw std::runtime_error("Failed to bind CAN socket");
  }
}

void GenericCANInterface::close_can_socket()
{
  if (can_socket_ >= 0) {
    close(can_socket_);
    can_socket_ = -1;
  }
}

uint32_t GenericCANInterface::get_cob_id(uint8_t function_code, uint8_t node_id)
{
  return (function_code << 7) | node_id;
}

bool GenericCANInterface::parse_can_frame(
  const struct ::can_frame & frame, uint32_t & id,
  std::vector<uint8_t> & data)
{
  id = frame.can_id;
  data.assign(frame.data, frame.data + frame.can_dlc);
  return true;
}

#ifndef BUILD_MG6010_ONLY
// GenericMotorController implementation
GenericMotorController::GenericMotorController()
: initialized_(false)
  , homed_(false)
  , calibrated_(true) // MG6010 doesn't need calibration like ODrive
  , enabled_(false)
  , current_position_counts_(0)
  , current_velocity_counts_(0)
  , current_torque_counts_(0)
  , current_position_(0.0)
  , current_velocity_(0.0)
  , current_torque_(0.0)
  , node_id_(1)
  , current_operation_mode_(OM_PROFILE_POSITION)
  , status_word_(0)
  , control_word_(0)
  , bus_voltage_(NOMINAL_48V_VOLTAGE)
  , max_current_(8.0)
  , max_power_(400.0)
  , voltage_warning_active_(false)
  , motor_state_(MotorStatus::UNKNOWN)
  , last_error_code_(0)
  , last_error_message_("")
  , counts_per_revolution_(16384) // MG6010 default
  , position_factor_(2.0 * M_PI / 16384) // Convert counts to radians
  , velocity_factor_(2.0 * M_PI / 16384) // Convert counts/s to rad/s
  , torque_factor_(1.0) // Placeholder - needs actual MG6010 specs
{
  last_position_time_ = std::chrono::steady_clock::now();
  last_status_update_ = std::chrono::steady_clock::now();
}

GenericMotorController::~GenericMotorController()
{
  if (enabled_) {
    emergency_stop();
  }
}

bool GenericMotorController::initialize(
  const MotorConfiguration & config,
  std::shared_ptr<CANInterface> can_interface)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (initialized_) {
    return true; // Already initialized
  }

  // Validate configuration
  std::string error_msg;
  if (!ConfigurationManager::validate_configuration(config, error_msg)) {
    last_error_message_ = "Invalid configuration: " + error_msg;
    return false;
  }

  // Store configuration and interfaces
  config_ = config;
  can_interface_ = can_interface;

  // Extract MG6010-specific parameters
  node_id_ = config_.can_id; // MG6010 uses CAN ID as node ID

  // Set 48V-specific power limits
  max_current_ = config_.current_limit;
  max_power_ = max_current_ * NOMINAL_48V_VOLTAGE;

  // Configure conversion factors based on configuration
  counts_per_revolution_ = config_.encoder_resolution;
  position_factor_ = 2.0 * M_PI / counts_per_revolution_;
  velocity_factor_ = position_factor_; // Same scaling for velocity

  // Initialize position from configuration
  current_position_ = config_.joint_offset;

  motor_state_ = MotorStatus::IDLE;
  initialized_ = true;

  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "GenericMotorController initialized for joint: %s (Node ID: %d, 48V, %.1fA max)",
    config_.joint_name.c_str(), static_cast<int>(node_id_), max_current_);

  return true;
}

bool GenericMotorController::configure(const MotorConfiguration & config)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  std::string error_msg;
  if (!ConfigurationManager::validate_configuration(config, error_msg)) {
    last_error_message_ = "Invalid configuration: " + error_msg;
    return false;
  }

  config_ = config;
  node_id_ = config_.can_id;
  max_current_ = config_.current_limit;
  max_power_ = max_current_ * NOMINAL_48V_VOLTAGE;

  return true;
}

bool GenericMotorController::set_enabled(bool enable)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    last_error_message_ = "Controller not initialized";
    return false;
  }

  try {
    if (enable) {
      // MG6010 state machine: go through proper sequence
      if (!switch_to_ready_to_switch_on()) {return false;}
      if (!switch_to_switched_on()) {return false;}
      if (!switch_to_operation_enabled()) {return false;}

      motor_state_ = MotorStatus::CLOSED_LOOP_CONTROL;
    } else {
      // Disable operation
      if (!set_control_word(CW_DISABLE_OPERATION)) {return false;}
      motor_state_ = MotorStatus::IDLE;
    }

    enabled_ = enable;
    return true;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Enable/disable failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return false;
  }
}

bool GenericMotorController::set_position(double position, double velocity, double torque)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !enabled_) {
    return false;
  }

  try {
    // Apply safety limits
    position = std::max(position, config_.limits.position_min);
    position = std::min(position, config_.limits.position_max);

    // Convert joint position to motor position with transmission factor and offset
    double motor_position_rad = (position - config_.joint_offset) / config_.transmission_factor;
    motor_position_rad *= config_.direction;

    // Convert to encoder counts
    int32_t target_counts = radians_to_counts(motor_position_rad);

    // Set operation mode to profile position if not already set
    if (current_operation_mode_ != OM_PROFILE_POSITION) {
      if (!set_operation_mode(OM_PROFILE_POSITION)) {
        return false;
      }
    }

    // Set target position via SDO
    if (!set_target_position(target_counts)) {
      return false;
    }

    // Trigger new setpoint
    if (!set_control_word(CW_ENABLE_OPERATION_NEW_SETPOINT)) {
      return false;
    }

    last_position_time_ = std::chrono::steady_clock::now();

    // For logging/debugging
    (void)velocity; // Feed-forward velocity not implemented yet
    (void)torque;   // Feed-forward torque not implemented yet

    return true;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Position command failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return false;
  }
}

bool GenericMotorController::set_velocity(double velocity, double torque)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !enabled_) {
    return false;
  }

  try {
    // Apply velocity limits
    velocity = std::max(velocity, config_.limits.velocity_min);
    velocity = std::min(velocity, config_.limits.velocity_max);

    // Convert joint velocity to motor velocity
    double motor_velocity = velocity / config_.transmission_factor * config_.direction;

    // Convert to counts/s
    int32_t target_velocity_counts = rad_per_sec_to_counts_per_sec(motor_velocity);

    // Set operation mode to profile velocity
    if (current_operation_mode_ != OM_PROFILE_VELOCITY) {
      if (!set_operation_mode(OM_PROFILE_VELOCITY)) {
        return false;
      }
    }

    // Set target velocity via SDO
    if (!set_target_velocity(target_velocity_counts)) {
      return false;
    }

    (void)torque; // Feed-forward torque not implemented yet

    return true;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Velocity command failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return false;
  }
}

bool GenericMotorController::set_torque(double torque)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_ || !enabled_) {
    return false;
  }

  try {
    // Apply torque limits
    double limited_torque = std::max(-config_.limits.current_max,
                                   std::min(config_.limits.current_max, torque));

    // Convert to MG6010 internal units (placeholder)
    int16_t target_torque_counts = static_cast<int16_t>(limited_torque / torque_factor_);

    // Set operation mode to torque profile
    if (current_operation_mode_ != OM_TORQUE_PROFILE) {
      if (!set_operation_mode(OM_TORQUE_PROFILE)) {
        return false;
      }
    }

    // Set target torque via SDO
    if (!set_target_torque(target_torque_counts)) {
      return false;
    }

    return true;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Torque command failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return false;
  }
}

double GenericMotorController::get_position()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return 0.0;
  }

  try {
    // Read actual position from MG6010
    int32_t position_counts;
    if (get_actual_position(position_counts)) {
      current_position_counts_ = position_counts;

      // Convert counts to radians, then apply transmission factor and offset
      double motor_position_rad = counts_to_radians(position_counts) * config_.direction;
      current_position_ = motor_position_rad * config_.transmission_factor + config_.joint_offset;
    }

    return current_position_;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Position read failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return current_position_; // Return last known position
  }
}

double GenericMotorController::get_velocity()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return 0.0;
  }

  try {
    // Read actual velocity from MG6010
    int32_t velocity_counts;
    if (get_actual_velocity(velocity_counts)) {
      current_velocity_counts_ = velocity_counts;

      // Convert counts/s to rad/s, then apply transmission factor
      double motor_velocity = counts_per_sec_to_rad_per_sec(velocity_counts) * config_.direction;
      current_velocity_ = motor_velocity * config_.transmission_factor;
    }

    return current_velocity_;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Velocity read failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return current_velocity_;
  }
}

double GenericMotorController::get_torque()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    return 0.0;
  }

  try {
    // Read actual torque from MG6010
    int16_t torque_counts;
    if (get_actual_torque(torque_counts)) {
      current_torque_counts_ = torque_counts;
      current_torque_ = torque_counts * torque_factor_;
    }

    return current_torque_;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Torque read failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return current_torque_;
  }
}

bool GenericMotorController::home_motor(const HomingConfig * config)
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!initialized_) {
    last_error_message_ = "Controller not initialized";
    return false;
  }

  const HomingConfig & homing_config = config ? *config : config_.homing;

  try {
    motor_state_ = MotorStatus::HOMING;

    // Perform MG6010-specific homing sequence
    bool success = perform_canopen_homing(homing_config);

    if (success) {
      homed_ = true;
      motor_state_ = MotorStatus::IDLE;
      current_position_ = homing_config.home_offset + config_.joint_offset;
    } else {
      motor_state_ = MotorStatus::AXIS_ERROR;
    }

    return success;

  } catch (const std::exception & e) {
    last_error_message_ = std::string("Homing failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    motor_state_ = MotorStatus::AXIS_ERROR;
    return false;
  }
}

bool GenericMotorController::is_homed() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  return homed_;
}

MotorStatus GenericMotorController::get_status()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  // Update status from hardware
  update_motor_status();

  MotorStatus status;
  status.state = motor_state_;
  status.hardware_connected = can_interface_ && can_interface_->is_connected();
  status.motor_enabled = enabled_;
  status.encoder_ready = calibrated_;
  status.error_code = last_error_code_;
  status.error_message = last_error_message_;
  status.voltage = bus_voltage_;
  status.current = current_torque_ / torque_factor_; // Approximate current from torque
  status.temperature = 25.0; // Placeholder - would read from MG6010
  status.last_update = std::chrono::steady_clock::now();

  return status;
}

bool GenericMotorController::emergency_stop()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  try {
    // MG6010 emergency stop via quick stop
    if (!perform_quick_stop()) {
      return false;
    }

    enabled_ = false;
    motor_state_ = MotorStatus::IDLE;

    return true;
  } catch (const std::exception & e) {
    last_error_message_ = std::string("Emergency stop failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return false;
  }
}

bool GenericMotorController::clear_errors()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  try {
    // MG6010 fault reset via control word
    if (!handle_canopen_fault()) {
      return false;
    }

    last_error_code_ = 0;
    last_error_message_ = "";

    if (motor_state_ == MotorStatus::AXIS_ERROR) {
      motor_state_ = MotorStatus::IDLE;
    }

    return true;
  } catch (const std::exception & e) {
    last_error_message_ = std::string("Error clearing failed: ") + e.what();
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), last_error_message_.c_str());
    return false;
  }
}

bool GenericMotorController::calibrate_motor()
{
  // MG6010 doesn't need motor calibration like ODrive
  calibrated_ = true;
  return true;
}

bool GenericMotorController::calibrate_encoder()
{
  // MG6010 has absolute encoders, no calibration needed
  return true;
}

bool GenericMotorController::needs_calibration() const
{
  return false; // MG6010 doesn't need calibration
}

MotorConfiguration GenericMotorController::get_configuration() const
{
  return config_;
}

// Enhanced error handling methods
const ErrorFramework::ErrorInfo & GenericMotorController::get_error_info() const
{
  std::lock_guard<std::mutex> lock(state_mutex_);
  static ErrorFramework::ErrorInfo current_error_info;

  // Convert legacy error information to new format
  if (last_error_code_ != 0) {
    current_error_info.code = last_error_code_;
    current_error_info.message = last_error_message_;
    current_error_info.category = ErrorFramework::ErrorCategory::HARDWARE; // Default category
    current_error_info.severity = ErrorFramework::ErrorSeverity::ERROR;
    current_error_info.timestamp = std::chrono::steady_clock::now();
    current_error_info.can_auto_recover = true; // MG6010 errors can often be recovered
  } else {
    current_error_info = ErrorFramework::ErrorInfo(); // Default/clear error
  }

  return current_error_info;
}

std::vector<ErrorFramework::ErrorInfo> GenericMotorController::get_error_history() const
{
  // For now, return empty history. In a full implementation, this would
  // maintain a history of previous errors
  return std::vector<ErrorFramework::ErrorInfo>();
}

ErrorFramework::RecoveryResult GenericMotorController::attempt_error_recovery()
{
  std::lock_guard<std::mutex> lock(state_mutex_);

  ErrorFramework::RecoveryResult result;
  result.recovery_time = std::chrono::steady_clock::now();

  if (last_error_code_ == 0) {
    result.success = true;
    result.action_taken = "No error to recover from";
    result.next_suggestion = "System operating normally";
    return result;
  }

  // Attempt basic MG6010 error recovery
  try {
    // Clear errors first
    if (clear_errors()) {
      result.success = true;
      result.action_taken = "Cleared MG6010 errors and reset controller state";
      result.next_suggestion = "Monitor system for stability";
    } else {
      result.success = false;
      result.action_taken = "Failed to clear MG6010 errors";
      result.next_suggestion = "Check MG6010 hardware and CAN communication";
    }

    result.attempts_made = 1;

  } catch (const std::exception & e) {
    result.success = false;
    result.action_taken = std::string("Recovery attempt failed: ") + e.what();
    result.next_suggestion = "Manual intervention required";
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
      "[%s] %s", config_.joint_name.c_str(), result.action_taken.c_str());
  }

  return result;
}

void GenericMotorController::set_error_handler(
  std::function<void(const ErrorFramework::ErrorInfo &)> handler)
{
  error_handler_callback_ = handler;
}

// Helper method implementations (stubs for now - would need actual SDO communication)
bool GenericMotorController::send_sdo_write(
  uint16_t index, uint8_t subindex,
  const std::vector<uint8_t> & data)
{
  auto mg6010_can = std::dynamic_pointer_cast<GenericCANInterface>(can_interface_);
  if (!mg6010_can) {
    last_error_message_ = "Invalid CAN interface for MG6010";
    return false;
  }

  return mg6010_can->send_sdo_request(node_id_, index, subindex, data);
}

bool GenericMotorController::send_sdo_read(
  uint16_t index, uint8_t subindex,
  std::vector<uint8_t> & data)
{
  auto mg6010_can = std::dynamic_pointer_cast<GenericCANInterface>(can_interface_);
  if (!mg6010_can) {
    last_error_message_ = "Invalid CAN interface for MG6010";
    return false;
  }

  // Send read request
  if (!mg6010_can->send_sdo_request(node_id_, index, subindex, {})) {
    return false;
  }

  // Wait for response
  uint16_t resp_index;
  uint8_t resp_subindex;
  return mg6010_can->receive_sdo_response(node_id_, resp_index, resp_subindex, data);
}

// Placeholder implementations for MG6010-specific methods
bool GenericMotorController::set_operation_mode(uint8_t mode)
{
  std::vector<uint8_t> data = {mode};
  if (send_sdo_write(OD_OPERATION_MODE, 0, data)) {
    current_operation_mode_ = mode;
    return true;
  }
  return false;
}

bool GenericMotorController::get_device_status(uint16_t & status_word)
{
  std::vector<uint8_t> data;
  if (send_sdo_read(OD_STATUS_WORD, 0, data) && data.size() >= 2) {
    status_word = data[0] | (data[1] << 8);
    status_word_ = status_word;
    return true;
  }
  return false;
}

bool GenericMotorController::set_control_word(uint16_t control_word)
{
  std::vector<uint8_t> data = {static_cast<uint8_t>(control_word & 0xFF),
    static_cast<uint8_t>(control_word >> 8)};
  if (send_sdo_write(OD_CONTROL_WORD, 0, data)) {
    control_word_ = control_word;
    return true;
  }
  return false;
}

bool GenericMotorController::get_actual_position(int32_t & position)
{
  std::vector<uint8_t> data;
  if (send_sdo_read(OD_POSITION_ACTUAL, 0, data) && data.size() >= 4) {
    position = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24);
    return true;
  }
  return false;
}

bool GenericMotorController::get_actual_velocity(int32_t & velocity)
{
  std::vector<uint8_t> data;
  if (send_sdo_read(OD_VELOCITY_ACTUAL, 0, data) && data.size() >= 4) {
    velocity = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24);
    return true;
  }
  return false;
}

bool GenericMotorController::get_actual_torque(int16_t & torque)
{
  std::vector<uint8_t> data;
  if (send_sdo_read(OD_TORQUE_ACTUAL, 0, data) && data.size() >= 2) {
    torque = data[0] | (data[1] << 8);
    return true;
  }
  return false;
}

bool GenericMotorController::set_target_position(int32_t position)
{
  std::vector<uint8_t> data = {static_cast<uint8_t>(position & 0xFF),
    static_cast<uint8_t>((position >> 8) & 0xFF),
    static_cast<uint8_t>((position >> 16) & 0xFF),
    static_cast<uint8_t>((position >> 24) & 0xFF)};
  return send_sdo_write(OD_TARGET_POSITION, 0, data);
}

bool GenericMotorController::set_target_velocity(int32_t velocity)
{
  std::vector<uint8_t> data = {static_cast<uint8_t>(velocity & 0xFF),
    static_cast<uint8_t>((velocity >> 8) & 0xFF),
    static_cast<uint8_t>((velocity >> 16) & 0xFF),
    static_cast<uint8_t>((velocity >> 24) & 0xFF)};
  return send_sdo_write(OD_TARGET_VELOCITY, 0, data);
}

bool GenericMotorController::set_target_torque(int16_t torque)
{
  std::vector<uint8_t> data = {static_cast<uint8_t>(torque & 0xFF),
    static_cast<uint8_t>(torque >> 8)};
  return send_sdo_write(OD_TARGET_TORQUE, 0, data);
}

// Additional helper method implementations (stubs)
int32_t GenericMotorController::radians_to_counts(double radians)
{
  return static_cast<int32_t>(radians / position_factor_);
}

double GenericMotorController::counts_to_radians(int32_t counts)
{
  return counts * position_factor_;
}

int32_t GenericMotorController::rad_per_sec_to_counts_per_sec(double rad_per_sec)
{
  return static_cast<int32_t>(rad_per_sec / velocity_factor_);
}

double GenericMotorController::counts_per_sec_to_rad_per_sec(int32_t counts_per_sec)
{
  return counts_per_sec * velocity_factor_;
}

bool GenericMotorController::switch_to_operation_enabled()
{
  return set_control_word(CW_ENABLE_OPERATION);
}

bool GenericMotorController::switch_to_switched_on()
{
  return set_control_word(CW_SWITCH_ON);
}

bool GenericMotorController::switch_to_ready_to_switch_on()
{
  return set_control_word(CW_DISABLE_VOLTAGE);
}

bool GenericMotorController::perform_quick_stop()
{
  return set_control_word(CW_QUICK_STOP);
}

bool GenericMotorController::perform_canopen_homing(const HomingConfig & homing_config)
{
  // Set homing method
  if (!set_homing_method(static_cast<uint8_t>(homing_config.method))) {
    return false;
  }

  // Start homing
  if (!start_homing()) {
    return false;
  }

  // Wait for completion
  return wait_for_homing_complete(homing_config.timeout_seconds);
}

bool GenericMotorController::set_homing_method(uint8_t method)
{
  std::vector<uint8_t> data = {method};
  return send_sdo_write(OD_HOMING_METHOD, 0, data);
}

bool GenericMotorController::start_homing()
{
  // Set operation mode to homing
  if (!set_operation_mode(OM_HOMING)) {
    return false;
  }

  // Start homing operation
  return set_control_word(CW_START_HOMING);
}

bool GenericMotorController::wait_for_homing_complete(double timeout_seconds)
{
  auto start_time = std::chrono::steady_clock::now();
  auto timeout = std::chrono::duration<double>(timeout_seconds);

  while (std::chrono::steady_clock::now() - start_time < timeout) {
    uint16_t status;
    if (get_device_status(status)) {
      if (status & SW_HOMING_ATTAINED) {
        return true; // Homing successful
      }
      if (status & SW_HOMING_ERROR) {
        return false; // Homing failed
      }
    }
    // BLOCKING_SLEEP_OK: homing poll on caller thread, behind BUILD_MG6010_ONLY guard — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  return false; // Timeout
}

void GenericMotorController::update_motor_status()
{
  uint16_t status;
  if (get_device_status(status)) {
    motor_state_ = canopen_state_to_motor_status(status);
    last_status_update_ = std::chrono::steady_clock::now();
  }
}

MotorStatus::State GenericMotorController::canopen_state_to_motor_status(uint16_t status_word)
{
  if (status_word & SW_FAULT) {
    return MotorStatus::AXIS_ERROR;
  }
  if (status_word & SW_HOMING_ATTAINED) {
    return MotorStatus::IDLE;
  }
  if (status_word & SW_OPERATION_ENABLED) {
    return MotorStatus::CLOSED_LOOP_CONTROL;
  }
  if (status_word & SW_SWITCHED_ON) {
    return MotorStatus::IDLE;
  }
  if (status_word & SW_READY_TO_SWITCH_ON) {
    return MotorStatus::STARTUP;
  }

  return MotorStatus::UNKNOWN;
}

bool GenericMotorController::handle_canopen_fault()
{
  // Clear fault via control word (fault reset)
  return set_control_word(0x80); // Fault reset bit
}

bool GenericMotorController::check_voltage_levels()
{
  std::vector<uint8_t> data;
  if (send_sdo_read(OD_DC_LINK_VOLTAGE, 0, data) && data.size() >= 2) {
    uint16_t voltage_raw = data[0] | (data[1] << 8);
    bus_voltage_ = voltage_raw / 10.0; // Assuming 0.1V resolution

    voltage_warning_active_ = (bus_voltage_<MIN_48V_VOLTAGE || bus_voltage_> MAX_48V_VOLTAGE);
    return !voltage_warning_active_;
  }
  return false;
}

bool GenericMotorController::monitor_power_levels()
{
  return check_voltage_levels();
}

bool GenericMotorController::check_voltage_range()
{
  return !voltage_warning_active_;
}

bool GenericMotorController::get_temperature_status(double & motor_temp, double & driver_temp)
{
  // Temperature monitoring stub - waiting for MG6010 protocol support
  // When the motor protocol supports temperature readouts, this will read from:
  // - OD_MOTOR_TEMPERATURE (TBD - motor winding temperature)
  // - OD_DRIVER_TEMPERATURE (TBD - driver board temperature)

  // For now, return safe default values indicating unknown temperature
  motor_temp = -1.0;   // -1 indicates "not available"
  driver_temp = -1.0;  // -1 indicates "not available"

  // TODO: Implement actual temperature reading when MG6010 protocol documentation
  // includes temperature sensor object dictionary indices
  // Expected implementation:
  //   1. Send SDO read request to motor temperature object
  //   2. Send SDO read request to driver temperature object
  //   3. Parse raw temperature values and convert to Celsius
  //   4. Check against warning/critical thresholds
  //   5. Return true if temperatures are within safe limits

  // Return false to indicate feature not yet implemented
  return false;
}

// Factory function
std::shared_ptr<MotorControllerInterface> create_generic_motor_controller()
{
  return std::make_shared<GenericMotorController>();
}

// Register MG6010 controller with factory (this would be called during initialization)
namespace
{
struct GenericMotorControllerRegistration
{
  GenericMotorControllerRegistration()
  {
    MotorControllerFactory::register_controller_type("mg6010", create_generic_motor_controller);
    MotorControllerFactory::register_controller_type("MG6010", create_generic_motor_controller);
  }
};

static GenericMotorControllerRegistration registration;
}
#endif // BUILD_MG6010_ONLY

} // namespace motor_control_ros2
