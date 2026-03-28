/*********************************************************************
 * Software License Agreement (BSD License)
 *
 *  Copyright (c) 2015, University of Colorado, Boulder
 *  All rights reserved.
 *
 *  Redistribution and use in source and binary forms, with or without
 *  modification, are permitted provided that the following conditions
 *  are met:
 *
 *   * Redistributions of source code must retain the above copyright
 *     notice, this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above
 *     copyright notice, this list of conditions and the following
 *     disclaimer in the documentation and/or other materials provided
 *     with the distribution.
 *   * Neither the name of the Univ of CO, Boulder nor the names of its
 *     contributors may be used to endorse or promote products derived
 *     from this software without specific prior written permission.
 *
 *  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 *  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 *  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 *  FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 *  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 *  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 *  BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 *  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 *  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 *  LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 *  ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 *  POSSIBILITY OF SUCH DAMAGE.
 *********************************************************************/

#ifndef MOTOR_CONTROL_ROS2__GENERIC_HW_INTERFACE_HPP_
#define MOTOR_CONTROL_ROS2__GENERIC_HW_INTERFACE_HPP_

/* Author: Dave Coleman
   Desc:   ROS2 Hardware Interface for Pragati robot (MG6010 motor controller)
*/

#include <memory>
#include <string>
#include <vector>

// ROS2
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/node_interfaces/lifecycle_node_interface.hpp>
#include <rclcpp_lifecycle/state.hpp>

// ROS2 Hardware Interface
#include <hardware_interface/handle.hpp>
#include <hardware_interface/hardware_info.hpp>
#include <hardware_interface/system_interface.hpp>
#include <hardware_interface/types/hardware_interface_return_values.hpp>
#include <hardware_interface/types/hardware_interface_type_values.hpp>

// Safety
#include "motor_control_ros2/safety_monitor.hpp"

namespace motor_control_ros2
{


class GenericHWInterface : public hardware_interface::SystemInterface
{
public:
  RCLCPP_SHARED_PTR_DEFINITIONS(GenericHWInterface)


  /// \brief Initialize the hardware interface from hardware description
  hardware_interface::CallbackReturn on_init(
    const hardware_interface::HardwareInfo & info) override;

  /// \brief Configure the hardware interface
  hardware_interface::CallbackReturn on_configure(
    const rclcpp_lifecycle::State & previous_state) override;

  /// \brief Cleanup the hardware interface
  hardware_interface::CallbackReturn on_cleanup(
    const rclcpp_lifecycle::State & previous_state) override;

  /// \brief Shutdown the hardware interface
  hardware_interface::CallbackReturn on_shutdown(
    const rclcpp_lifecycle::State & previous_state) override;

  /// \brief Activate the hardware interface
  hardware_interface::CallbackReturn on_activate(
    const rclcpp_lifecycle::State & previous_state) override;

  /// \brief Deactivate the hardware interface
  hardware_interface::CallbackReturn on_deactivate(
    const rclcpp_lifecycle::State & previous_state) override;

  /// \brief Export state interfaces for the hardware
  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;

  /// \brief Export command interfaces for the hardware
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;

  /// \brief Read the current state from the hardware
  hardware_interface::return_type read(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

  /// \brief Write commands to the hardware
  hardware_interface::return_type write(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

  /// \brief Set safety monitor for command gating
  void set_safety_monitor(std::shared_ptr<SafetyMonitor> safety_monitor);

protected:
  /// \brief Parse hardware parameters from configuration
  hardware_interface::CallbackReturn parse_parameters();

  /// \brief Initialize CAN communication (virtual for testability)
  virtual hardware_interface::CallbackReturn init_can_communication();

  /// \brief Initialize joint parameters
  hardware_interface::CallbackReturn init_joint_parameters();

  /// \brief Validate joint configuration
  bool validate_joint_config();

protected:
  // Hardware configuration
  std::string name_;
  std::vector<std::string> joint_names_;
  size_t num_joints_;

  // Hardware communication
  std::string can_interface_;
  std::string can_socket_;

  // Joint states (read from hardware)
  std::vector<double> hw_positions_;
  std::vector<double> hw_velocities_;
  std::vector<double> hw_efforts_;

  // Joint commands (written to hardware)
  std::vector<double> hw_position_commands_;
  std::vector<double> hw_velocity_commands_;
  std::vector<double> hw_effort_commands_;

  // Joint limits (for ROS2 compatibility)
  std::vector<double> joint_position_lower_limits_;
  std::vector<double> joint_position_upper_limits_;
  std::vector<double> joint_velocity_limits_;
  std::vector<double> joint_effort_limits_;

  // Motor controller parameters (MG6010)
  struct MotorJointConfig {
    uint32_t can_id;
    uint32_t axis_id;
    double transmission_factor;
    int direction;
    double position_offset;
    double velocity_limit;
    double effort_limit;
  };

  std::vector<MotorJointConfig> joint_configs_;

  // Communication parameters
  bool hardware_connected_;
  bool use_simulation_;

  // Timing
  rclcpp::Time last_read_time_;
  rclcpp::Time last_write_time_;

  // Logging
  rclcpp::Logger logger_ = rclcpp::get_logger("GenericHWInterface");

  // Safety monitor for command gating
  std::shared_ptr<SafetyMonitor> safety_monitor_;
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__GENERIC_HW_INTERFACE_HPP_
