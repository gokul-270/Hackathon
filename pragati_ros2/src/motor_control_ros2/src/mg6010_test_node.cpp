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
 * MG6010 Motor Test Node
 *
 * Standalone test node for validating MG6010 motor protocol implementation.
 * Supports multiple test modes without integration into the full motor controller.
 */

#include <rclcpp/rclcpp.hpp>
#include "motor_control_ros2/mg6010_protocol.hpp"
#include "motor_control_ros2/generic_motor_controller.hpp"
#include <memory>
#include <string>
#include <thread>
#include <chrono>
#include <iostream>
#include <iomanip>

using namespace motor_control_ros2;

class MG6010TestNode : public rclcpp::Node
{
public:
  MG6010TestNode() : Node("mg6010_test_node")
  {
    // Declare parameters
    this->declare_parameter<std::string>("interface_name", "can0");
    this->declare_parameter<int>("baud_rate", 500000);  // Pragati default: 500kbps
    this->declare_parameter<int>("node_id", 1);
    this->declare_parameter<std::string>("mode", "status");
    this->declare_parameter<double>("position_rad", 0.0);
    this->declare_parameter<double>("velocity_rad_s", 0.5);
    this->declare_parameter<double>("accel_rad_s2", 1.0);
    this->declare_parameter<double>("torque_amps", 1.0);
    this->declare_parameter<bool>("verbose", true);

    // Get parameters
    std::string interface_name = this->get_parameter("interface_name").as_string();
    int baud_rate = this->get_parameter("baud_rate").as_int();
    int node_id = this->get_parameter("node_id").as_int();
    std::string mode = this->get_parameter("mode").as_string();
    double position_rad = this->get_parameter("position_rad").as_double();
    double velocity_rad_s = this->get_parameter("velocity_rad_s").as_double();
    double accel_rad_s2 = this->get_parameter("accel_rad_s2").as_double();
    double torque_amps = this->get_parameter("torque_amps").as_double();
    verbose_ = this->get_parameter("verbose").as_bool();

    RCLCPP_INFO(this->get_logger(), "MG6010 Test Node Starting");
    RCLCPP_INFO(this->get_logger(), "  Interface: %s", interface_name.c_str());
    RCLCPP_INFO(this->get_logger(), "  Baud Rate: %d", baud_rate);
    RCLCPP_INFO(this->get_logger(), "  Node ID: %d", node_id);
    RCLCPP_INFO(this->get_logger(), "  Mode: %s", mode.c_str());

    // Create CAN interface
    can_interface_ = std::make_shared<GenericCANInterface>();
    if (!can_interface_->initialize(interface_name, baud_rate)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to initialize CAN interface: %s",
                   can_interface_->get_last_error().c_str());
      rclcpp::shutdown();
      return;
    }

    RCLCPP_INFO(this->get_logger(), "CAN interface initialized successfully");

    // Create MG6010 protocol handler
    protocol_ = std::make_shared<MG6010Protocol>();
    if (!protocol_->initialize(can_interface_, static_cast<uint8_t>(node_id), baud_rate)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to initialize MG6010 protocol: %s",
                   protocol_->get_last_error().c_str());
      rclcpp::shutdown();
      return;
    }

    RCLCPP_INFO(this->get_logger(), "MG6010 protocol initialized successfully");

    // Execute test mode
    bool success = false;
    if (mode == "on_off") {
      success = test_on_off();
    } else if (mode == "position") {
      success = test_position(position_rad);
    } else if (mode == "velocity") {
      success = test_velocity(velocity_rad_s);
    } else if (mode == "torque") {
      success = test_torque(torque_amps);
    } else if (mode == "status") {
      success = test_status();
    } else if (mode == "angle") {
      success = test_angle();
    } else if (mode == "pid") {
      success = test_pid();
    } else if (mode == "accel") {
      success = test_acceleration(accel_rad_s2);
    } else if (mode == "encoder") {
      success = test_encoder();
    } else {
      RCLCPP_ERROR(this->get_logger(), "Unknown mode: %s", mode.c_str());
      RCLCPP_INFO(this->get_logger(), "Available modes: on_off, position, velocity, torque, status, angle, pid, accel, encoder");
      rclcpp::shutdown();
      return;
    }

    if (success) {
      RCLCPP_INFO(this->get_logger(), "Test completed successfully");
    } else {
      RCLCPP_ERROR(this->get_logger(), "Test failed");
    }

    // Shutdown after test
    rclcpp::shutdown();
  }

private:
  std::shared_ptr<GenericCANInterface> can_interface_;
  std::shared_ptr<MG6010Protocol> protocol_;
  bool verbose_;

  void log_verbose(const std::string & msg)
  {
    if (verbose_) {
      RCLCPP_INFO(this->get_logger(), "%s", msg.c_str());
    }
  }

  bool test_on_off()
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Motor ON/OFF ===");

    log_verbose("Turning motor ON...");
    if (!protocol_->motor_on()) {
      RCLCPP_ERROR(this->get_logger(), "Failed to turn motor ON: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "Motor ON successful");

    std::this_thread::sleep_for(std::chrono::seconds(2));

    log_verbose("Turning motor OFF...");
    if (!protocol_->motor_off()) {
      RCLCPP_ERROR(this->get_logger(), "Failed to turn motor OFF: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "Motor OFF successful");

    return true;
  }

  bool test_position(double target_rad)
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Position Control ===");
    RCLCPP_INFO(this->get_logger(), "Target position: %.3f rad (%.1f deg)",
                target_rad, target_rad * 180.0 / M_PI);

    log_verbose("Turning motor ON...");
    if (!protocol_->motor_on()) {
      RCLCPP_ERROR(this->get_logger(), "Failed to turn motor ON: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    log_verbose("Setting absolute position...");
    if (!protocol_->set_absolute_position(target_rad)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to set position: %s",
                   protocol_->get_last_error().c_str());
      protocol_->motor_off();
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "Position command sent successfully");

    // Wait and check status
    std::this_thread::sleep_for(std::chrono::seconds(3));

    MG6010Protocol::Status status;
    if (protocol_->read_status(status)) {
      RCLCPP_INFO(this->get_logger(), "Motor status: temp=%.1f°C, voltage=%.1fV, errors=0x%02X",
                  status.temperature, status.voltage, status.error_flags);
    }

    // Read current angle
    double current_angle = 0.0;
    if (protocol_->read_multi_turn_angle(current_angle)) {
      RCLCPP_INFO(this->get_logger(), "Current angle: %.3f rad (%.1f deg)",
                  current_angle, current_angle * 180.0 / M_PI);
    }

    log_verbose("Turning motor OFF...");
    protocol_->motor_off();

    return true;
  }

  bool test_velocity(double target_rad_s)
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Velocity Control ===");
    RCLCPP_INFO(this->get_logger(), "Target velocity: %.3f rad/s (%.1f deg/s)",
                target_rad_s, target_rad_s * 180.0 / M_PI);

    log_verbose("Turning motor ON...");
    if (!protocol_->motor_on()) {
      RCLCPP_ERROR(this->get_logger(), "Failed to turn motor ON: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    log_verbose("Setting velocity...");
    if (!protocol_->speed_closed_loop_control(target_rad_s)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to set velocity: %s",
                   protocol_->get_last_error().c_str());
      protocol_->motor_off();
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "Velocity command sent successfully");

    // Run for a few seconds
    for (int i = 0; i < 3; ++i) {
      std::this_thread::sleep_for(std::chrono::seconds(1));

      MG6010Protocol::Status status;
      if (protocol_->read_status_detailed(status)) {
        RCLCPP_INFO(this->get_logger(), "Status: speed=%.3f rad/s, temp=%.1f°C, torque=%.2fA",
                    status.speed, status.temperature, status.torque_current);
      }
    }

    log_verbose("Stopping motor...");
    protocol_->motor_stop();
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    protocol_->motor_off();

    return true;
  }

  bool test_torque(double target_amps)
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Torque Control ===");
    RCLCPP_INFO(this->get_logger(), "Target torque: %.2f A", target_amps);

    log_verbose("Turning motor ON...");
    if (!protocol_->motor_on()) {
      RCLCPP_ERROR(this->get_logger(), "Failed to turn motor ON: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    log_verbose("Setting torque...");
    if (!protocol_->torque_closed_loop_control(target_amps)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to set torque: %s",
                   protocol_->get_last_error().c_str());
      protocol_->motor_off();
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "Torque command sent successfully");

    // Hold for a few seconds
    std::this_thread::sleep_for(std::chrono::seconds(2));

    log_verbose("Stopping motor...");
    protocol_->motor_off();

    return true;
  }

  bool test_status()
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Status Reading ===");

    // Enable motor first - required for MG6010 to respond to status queries
    log_verbose("Enabling motor...");
    if (!protocol_->motor_on()) {
      RCLCPP_WARN(this->get_logger(), "Motor enable failed (might already be on): %s",
                   protocol_->get_last_error().c_str());
      // Continue anyway - motor might already be enabled
    } else {
      log_verbose("Motor enabled successfully");
    }

    // Small delay to ensure motor is ready
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    MG6010Protocol::Status status;
    if (!protocol_->read_status(status)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to read status: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    RCLCPP_INFO(this->get_logger(), "Motor Status (STATUS_1):");
    RCLCPP_INFO(this->get_logger(), "  Temperature: %.1f °C", status.temperature);
    RCLCPP_INFO(this->get_logger(), "  Voltage: %.1f V", status.voltage);
    RCLCPP_INFO(this->get_logger(), "  Error Flags: 0x%02X", status.error_flags);
    RCLCPP_INFO(this->get_logger(), "  Motor Running: %s", status.motor_running ? "Yes" : "No");

    if (status.error_flags & MG6010Protocol::ERROR_VOLTAGE) {
      RCLCPP_WARN(this->get_logger(), "  - Voltage error detected");
    }
    if (status.error_flags & MG6010Protocol::ERROR_TEMPERATURE) {
      RCLCPP_WARN(this->get_logger(), "  - Temperature error detected");
    }

    // Try detailed status too
    if (protocol_->read_status_detailed(status)) {
      RCLCPP_INFO(this->get_logger(), "Motor Status (STATUS_2):");
      RCLCPP_INFO(this->get_logger(), "  Temperature: %.1f °C", status.temperature);
      RCLCPP_INFO(this->get_logger(), "  Torque Current: %.2f A", status.torque_current);
      RCLCPP_INFO(this->get_logger(), "  Speed: %.3f rad/s (%.1f deg/s)",
                  status.speed, status.speed * 180.0 / M_PI);
      RCLCPP_INFO(this->get_logger(), "  Encoder Position: %u", status.encoder_position);
    }

    return true;
  }

  bool test_angle()
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Angle Reading ===");

    double multi_turn = 0.0;
    if (!protocol_->read_multi_turn_angle(multi_turn)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to read multi-turn angle: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    RCLCPP_INFO(this->get_logger(), "Multi-turn angle: %.3f rad (%.2f deg)",
                multi_turn, multi_turn * 180.0 / M_PI);

    double single_turn = 0.0;
    if (!protocol_->read_single_turn_angle(single_turn)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to read single-turn angle: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    RCLCPP_INFO(this->get_logger(), "Single-turn angle: %.3f rad (%.2f deg)",
                single_turn, single_turn * 180.0 / M_PI);

    return true;
  }

  bool test_pid()
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing PID Reading ===");

    MG6010Protocol::PIDParams pid;
    if (!protocol_->read_pid(pid)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to read PID: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    RCLCPP_INFO(this->get_logger(), "PID Parameters:");
    RCLCPP_INFO(this->get_logger(), "  Angle: Kp=%u, Ki=%u", pid.angle_kp, pid.angle_ki);
    RCLCPP_INFO(this->get_logger(), "  Speed: Kp=%u, Ki=%u", pid.speed_kp, pid.speed_ki);
    RCLCPP_INFO(this->get_logger(), "  Current: Kp=%u, Ki=%u", pid.current_kp, pid.current_ki);

    return true;
  }

  bool test_acceleration(double accel_rad_s2)
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Acceleration ===");

    // Read current acceleration
    double current_accel = 0.0;
    if (protocol_->read_acceleration(current_accel)) {
      RCLCPP_INFO(this->get_logger(), "Current acceleration: %.2f rad/s² (%.1f deg/s²)",
                  current_accel, current_accel * 180.0 / M_PI);
    }

    // Set new acceleration
    log_verbose("Setting acceleration...");
    if (!protocol_->set_acceleration(accel_rad_s2)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to set acceleration: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "Acceleration set to %.2f rad/s² (%.1f deg/s²)",
                accel_rad_s2, accel_rad_s2 * 180.0 / M_PI);

    // Read back
    if (protocol_->read_acceleration(current_accel)) {
      RCLCPP_INFO(this->get_logger(), "Verified acceleration: %.2f rad/s² (%.1f deg/s²)",
                  current_accel, current_accel * 180.0 / M_PI);
    }

    return true;
  }

  bool test_encoder()
  {
    RCLCPP_INFO(this->get_logger(), "=== Testing Encoder Reading ===");

    uint16_t encoder_value = 0;
    uint16_t encoder_raw = 0;
    uint16_t encoder_offset = 0;

    if (!protocol_->read_encoder(encoder_value, encoder_raw, encoder_offset)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to read encoder: %s",
                   protocol_->get_last_error().c_str());
      return false;
    }

    RCLCPP_INFO(this->get_logger(), "Encoder Data:");
    RCLCPP_INFO(this->get_logger(), "  Value: %u", encoder_value);
    RCLCPP_INFO(this->get_logger(), "  Raw: %u", encoder_raw);
    RCLCPP_INFO(this->get_logger(), "  Offset: %u", encoder_offset);

    return true;
  }
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<MG6010TestNode>();
  // Node will execute test in constructor and shutdown
  return 0;
}
