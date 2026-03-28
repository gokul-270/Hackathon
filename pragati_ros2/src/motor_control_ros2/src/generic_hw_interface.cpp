/*********************************************************************
 * Software License Agreement (BSD License)
 *
 *  Copyright (c) 2015, PickNik LLC
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
 *   * Neither the name of PickNik LLC nor the names of its
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

/* Author: Dave Coleman
   Desc:   ROS2 Hardware Interface for Pragati robot (MG6010 motor controller)
*/

#include "motor_control_ros2/generic_hw_interface.hpp"

#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <set>
#include <vector>

#include <hardware_interface/types/hardware_interface_type_values.hpp>
#include <rclcpp/rclcpp.hpp>


namespace motor_control_ros2
{


hardware_interface::CallbackReturn GenericHWInterface::on_init(
  const hardware_interface::HardwareInfo & info)
{
  // Use base class assignment instead of deprecated on_init() call
  info_ = info;

  // Validate basic info structure
  if (info_.joints.empty()) {
    RCLCPP_ERROR(rclcpp::get_logger("GenericHWInterface"), "No joints defined in URDF");
    return hardware_interface::CallbackReturn::ERROR;
  }


  RCLCPP_INFO(logger_, "Initializing Generic Hardware Interface...");

  name_ = info_.name;

  // Parse hardware parameters
  if (parse_parameters() != hardware_interface::CallbackReturn::SUCCESS)
  {
    RCLCPP_ERROR(logger_, "Failed to parse hardware parameters");
    return hardware_interface::CallbackReturn::ERROR;
  }


  // Get joint information
  num_joints_ = info_.joints.size();
  joint_names_.resize(num_joints_);

  RCLCPP_INFO(logger_, "Number of joints: %zu", num_joints_);

  // Initialize joint arrays
  hw_positions_.resize(num_joints_, 0.0);
  hw_velocities_.resize(num_joints_, 0.0);
  hw_efforts_.resize(num_joints_, 0.0);
  hw_position_commands_.resize(num_joints_, 0.0);
  hw_velocity_commands_.resize(num_joints_, 0.0);
  hw_effort_commands_.resize(num_joints_, 0.0);
  joint_configs_.resize(num_joints_);

  // Configure joints
  for (size_t i = 0; i < num_joints_; i++)
  {
    joint_names_[i] = info_.joints[i].name;
    RCLCPP_INFO(logger_, "Configuring joint: %s", joint_names_[i].c_str());


    // Validate state interfaces
    if (info_.joints[i].state_interfaces.size() != 3)
    {
      RCLCPP_FATAL(
        logger_, "Joint '%s' has %zu state interface. Expected exactly 3.",
        info_.joints[i].name.c_str(), info_.joints[i].state_interfaces.size());
      return hardware_interface::CallbackReturn::ERROR;
    }


    // Validate command interfaces
    if (info_.joints[i].command_interfaces.size() != 3)
    {
      RCLCPP_FATAL(
        logger_, "Joint '%s' has %zu command interfaces. Expected exactly 3.",
        info_.joints[i].name.c_str(), info_.joints[i].command_interfaces.size());
      return hardware_interface::CallbackReturn::ERROR;
    }


    // Check state interface types
    for (const auto & interface : info_.joints[i].state_interfaces)
    {
      if (!(interface.name == hardware_interface::HW_IF_POSITION ||
            interface.name == hardware_interface::HW_IF_VELOCITY ||
            interface.name == hardware_interface::HW_IF_EFFORT))
      {
        RCLCPP_FATAL(
          logger_, "Joint '%s' has unexpected state interface '%s'",
          info_.joints[i].name.c_str(), interface.name.c_str());
        return hardware_interface::CallbackReturn::ERROR;
      }
    }


    // Check command interface types
    for (const auto & interface : info_.joints[i].command_interfaces)
    {
      if (!(interface.name == hardware_interface::HW_IF_POSITION ||
            interface.name == hardware_interface::HW_IF_VELOCITY ||
            interface.name == hardware_interface::HW_IF_EFFORT))
      {
        RCLCPP_FATAL(
          logger_, "Joint '%s' has unexpected command interface '%s'",
          info_.joints[i].name.c_str(), interface.name.c_str());
        return hardware_interface::CallbackReturn::ERROR;
      }
    }
  }


  // Initialize joint parameters
  if (init_joint_parameters() != hardware_interface::CallbackReturn::SUCCESS)
  {
    RCLCPP_ERROR(logger_, "Failed to initialize joint parameters");
    return hardware_interface::CallbackReturn::ERROR;
  }


  hardware_connected_ = false;
  use_simulation_ = false;

  RCLCPP_INFO(logger_, "Generic Hardware Interface initialized successfully");
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn GenericHWInterface::on_configure(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  RCLCPP_DEBUG(logger_, "[ENTER] on_configure");


  RCLCPP_INFO(logger_, "Configuring Generic Hardware Interface...");
  RCLCPP_INFO(logger_, "Starting hardware interface configuration");

  // Initialize CAN communication if not in simulation mode
  if (!use_simulation_)
  {
    RCLCPP_INFO(logger_, "Attempting CAN communication initialization");
    if (init_can_communication() != hardware_interface::CallbackReturn::SUCCESS)
    {
      RCLCPP_ERROR(logger_, "CAN communication initialization failed - "
        "returning ERROR (simulation mode fallback removed for safety)");
      return hardware_interface::CallbackReturn::ERROR;
    } else {
      RCLCPP_INFO(logger_, "CAN communication initialized successfully");
    }
  }


  if (use_simulation_)
  {
    RCLCPP_INFO(logger_, "Running in simulation mode");
    RCLCPP_INFO(logger_, "Operating in simulation mode - no hardware communication");
  } else
  {
    RCLCPP_INFO(logger_, "Hardware communication initialized successfully");
    RCLCPP_INFO(logger_, "Hardware communication mode active");
  }

  // Validate joint configuration before activation
  if (!validate_joint_config())
  {
    RCLCPP_ERROR(logger_, "Joint configuration validation failed - "
      "returning ERROR to prevent activation with invalid config");
    return hardware_interface::CallbackReturn::ERROR;
  }

  RCLCPP_DEBUG(logger_, "[EXIT] on_configure: mode = %s", use_simulation_ ? "simulation" : "hardware");
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn GenericHWInterface::on_cleanup(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  RCLCPP_INFO(logger_, "Cleaning up Generic Hardware Interface...");
  hardware_connected_ = false;
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn GenericHWInterface::on_shutdown(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  RCLCPP_INFO(logger_, "Shutting down Generic Hardware Interface...");
  return on_cleanup(rclcpp_lifecycle::State());
}


hardware_interface::CallbackReturn GenericHWInterface::on_activate(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  RCLCPP_INFO(logger_, "Activating Generic Hardware Interface...");


  // Command and state should be equal when starting
  for (size_t i = 0; i < num_joints_; i++)
  {
    if (std::isnan(hw_positions_[i]))
    {
      hw_positions_[i] = 0.0;
    }
    if (std::isnan(hw_velocities_[i]))
    {
      hw_velocities_[i] = 0.0;
    }
    if (std::isnan(hw_efforts_[i]))
    {
      hw_efforts_[i] = 0.0;
    }


    hw_position_commands_[i] = hw_positions_[i];
    hw_velocity_commands_[i] = 0.0;
    hw_effort_commands_[i] = 0.0;
  }

  last_read_time_ = rclcpp::Clock().now();
  last_write_time_ = rclcpp::Clock().now();

  RCLCPP_INFO(logger_, "Generic Hardware Interface activated successfully");
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn GenericHWInterface::on_deactivate(
  const rclcpp_lifecycle::State & /*previous_state*/)
{
  RCLCPP_INFO(logger_, "Deactivating Generic Hardware Interface...");
  return hardware_interface::CallbackReturn::SUCCESS;
}


std::vector<hardware_interface::StateInterface> GenericHWInterface::export_state_interfaces()
{
  std::vector<hardware_interface::StateInterface> state_interfaces;


  for (size_t i = 0; i < num_joints_; i++)
  {
    state_interfaces.emplace_back(hardware_interface::StateInterface(
      joint_names_[i], hardware_interface::HW_IF_POSITION, &hw_positions_[i]));
    state_interfaces.emplace_back(hardware_interface::StateInterface(
      joint_names_[i], hardware_interface::HW_IF_VELOCITY, &hw_velocities_[i]));
    state_interfaces.emplace_back(hardware_interface::StateInterface(
      joint_names_[i], hardware_interface::HW_IF_EFFORT, &hw_efforts_[i]));
  }


  RCLCPP_INFO(logger_, "Exported %zu state interfaces", state_interfaces.size());
  return state_interfaces;
}

std::vector<hardware_interface::CommandInterface> GenericHWInterface::export_command_interfaces()
{
  std::vector<hardware_interface::CommandInterface> command_interfaces;


  for (size_t i = 0; i < num_joints_; i++)
  {
    command_interfaces.emplace_back(hardware_interface::CommandInterface(
      joint_names_[i], hardware_interface::HW_IF_POSITION, &hw_position_commands_[i]));
    command_interfaces.emplace_back(hardware_interface::CommandInterface(
      joint_names_[i], hardware_interface::HW_IF_VELOCITY, &hw_velocity_commands_[i]));
    command_interfaces.emplace_back(hardware_interface::CommandInterface(
      joint_names_[i], hardware_interface::HW_IF_EFFORT, &hw_effort_commands_[i]));
  }


  RCLCPP_INFO(logger_, "Exported %zu command interfaces", command_interfaces.size());
  return command_interfaces;
}

hardware_interface::return_type GenericHWInterface::read(
  const rclcpp::Time & time, const rclcpp::Duration & period)
{
  (void)period;  // Suppress unused parameter warning


  if (use_simulation_)
  {
    // Simulation mode - simple integration
    for (size_t i = 0; i < num_joints_; i++)
    {
      // Simple position integration from velocity commands
      hw_positions_[i] += hw_velocity_commands_[i] * period.seconds();
      hw_velocities_[i] = hw_velocity_commands_[i];
      hw_efforts_[i] = hw_effort_commands_[i];
    }
  }
  else
  {
    // Hardware mode - read from MG6010 motor controllers via CAN
    // TODO(hardware): Implement MG6010 CAN reading
    // For now, keep previous values (allows simulation and testing)
  }

  last_read_time_ = time;
  return hardware_interface::return_type::OK;
}

hardware_interface::return_type GenericHWInterface::write(
  const rclcpp::Time & time, const rclcpp::Duration & period)
{
  (void)period;  // Suppress unused parameter warning

  // Safety gate: check safety state before sending commands
  if (safety_monitor_) {
    SafetyState state = safety_monitor_->get_state();
    if (state == SafetyState::CRITICAL || state == SafetyState::EMERGENCY) {
      RCLCPP_WARN_THROTTLE(logger_, *rclcpp::Clock::make_shared(), 1000,
        "write() rejected: safety state is %s",
        safety_state_to_string(state));
      last_write_time_ = time;
      return hardware_interface::return_type::ERROR;
    }
    if (state == SafetyState::UNKNOWN || state == SafetyState::INITIALIZING) {
      RCLCPP_WARN_THROTTLE(logger_, *rclcpp::Clock::make_shared(), 1000,
        "write() rejected: safety monitor not ready (state: %s)",
        safety_state_to_string(state));
      last_write_time_ = time;
      return hardware_interface::return_type::ERROR;
    }
    // SAFE and WARNING: proceed (WARNING may apply derating at motor level)
  }

  // Hardware mode - write commands to MG6010 motor controllers via CAN
  // TODO(hardware): Implement MG6010 CAN writing
  // For now, commands are accepted but not sent to hardware (allows simulation/testing)

  last_write_time_ = time;
  return hardware_interface::return_type::OK;
}

void GenericHWInterface::set_safety_monitor(
  std::shared_ptr<SafetyMonitor> safety_monitor)
{
  safety_monitor_ = safety_monitor;
  RCLCPP_INFO(logger_, "Safety monitor set for command gating");
}

hardware_interface::CallbackReturn GenericHWInterface::parse_parameters()
{
  try
  {
    // Parse simulation mode
    auto it = info_.hardware_parameters.find("use_simulation");
    if (it != info_.hardware_parameters.end())
    {
      use_simulation_ = (it->second == "true" || it->second == "True" || it->second == "1");
    }


    // Parse CAN interface
    it = info_.hardware_parameters.find("can_interface");
    if (it != info_.hardware_parameters.end())
    {
      can_interface_ = it->second;
    } else
    {
      can_interface_ = "can0";  // Default
    }


    // Parse CAN socket
    it = info_.hardware_parameters.find("can_socket");
    if (it != info_.hardware_parameters.end())
    {
      can_socket_ = it->second;
    } else
    {
      can_socket_ = "socketcan";  // Default
    }


    RCLCPP_INFO(logger_, "Hardware parameters parsed successfully");
    RCLCPP_INFO(logger_, "  use_simulation: %s", use_simulation_ ? "true" : "false");
    RCLCPP_INFO(logger_, "  can_interface: %s", can_interface_.c_str());
    RCLCPP_INFO(logger_, "  can_socket: %s", can_socket_.c_str());

    return hardware_interface::CallbackReturn::SUCCESS;
  }
  catch (const std::exception & e)
  {
    RCLCPP_ERROR(logger_, "Failed to parse parameters: %s", e.what());
    return hardware_interface::CallbackReturn::ERROR;
  }
}


hardware_interface::CallbackReturn GenericHWInterface::init_can_communication()
{
  // MG Motor Controller Initialization
  // TODO(hardware): Implement MG6010/MG4040 CAN initialization when hardware available
  //
  // Expected implementation:
  //   1. Create GenericMotorController or MG6010Protocol instances
  //   2. Initialize CAN interface (GenericCANInterface)
  //   3. Configure each motor controller:
  //      - Set operation mode (position/velocity/torque)
  //      - Configure control parameters (PID gains, limits)
  //      - Enable motors and verify ready state
  //   4. Perform homing sequence if required
  //   5. Set hardware_connected_ = true on success
  //
  RCLCPP_INFO(logger_, "Initializing communication for MG motor controller...");
  RCLCPP_WARN(logger_, "MG motor controller communication not yet implemented - using simulation mode");
  RCLCPP_INFO(logger_, "Hardware interface will accept commands but not send to motors");
  hardware_connected_ = false;  // Not connected until implemented
  return hardware_interface::CallbackReturn::SUCCESS;  // Allow to continue in simulation
}


hardware_interface::CallbackReturn GenericHWInterface::init_joint_parameters()
{
  try
  {
    RCLCPP_INFO(logger_, "Initializing joint parameters...");


    for (size_t i = 0; i < num_joints_; i++)
    {
      auto& config = joint_configs_[i];


      // Set default values
      config.can_id = 0x001 + i;  // Default CAN IDs
      config.axis_id = i;         // Motor axis index
      config.transmission_factor = 1.0;
      config.direction = 1;
      config.position_offset = 0.0;
      config.velocity_limit = 10.0;
      config.effort_limit = 100.0;

      // Try to get parameters from joint configuration
      const auto& joint_info = info_.joints[i];

      // Parse joint-specific parameters
      for (const auto& param : joint_info.parameters)
      {
        if (param.first == "can_id")
        {
          config.can_id = std::stoul(param.second, nullptr, 0);  // Support hex format
        } else if (param.first == "axis_id")
        {
          config.axis_id = std::stoul(param.second);
        } else if (param.first == "transmission_factor")
        {
          config.transmission_factor = std::stod(param.second);
        } else if (param.first == "direction")
        {
          config.direction = std::stoi(param.second);
        } else if (param.first == "position_offset")
        {
          config.position_offset = std::stod(param.second);
        } else if (param.first == "velocity_limit")
        {
          config.velocity_limit = std::stod(param.second);
        } else if (param.first == "effort_limit")
        {
          config.effort_limit = std::stod(param.second);
        }
      }


      RCLCPP_INFO(logger_, "Joint %s: CAN = 0x%03X, Axis = %u, TF = %.3f, Dir = %d",
        joint_names_[i].c_str(), config.can_id,
        config.axis_id, config.transmission_factor, config.direction);
    }

    return hardware_interface::CallbackReturn::SUCCESS;
  }
  catch (const std::exception & e)
  {
    RCLCPP_ERROR(logger_, "Failed to initialize joint parameters: %s", e.what());
    return hardware_interface::CallbackReturn::ERROR;
  }
}


bool GenericHWInterface::validate_joint_config()
{
  // Validate joint configuration
  std::set<uint32_t> seen_can_ids;

  for (size_t i = 0; i < num_joints_; i++)
  {
    const auto& config = joint_configs_[i];

    // CAN ID must be explicitly configured — auto-assigned IDs are unsafe
    const auto& joint_params = info_.joints[i].parameters;
    if (joint_params.find("can_id") == joint_params.end())
    {
      RCLCPP_ERROR(logger_, "Joint %s missing required can_id parameter", joint_names_[i].c_str());
      return false;
    }


    if (config.transmission_factor == 0.0)
    {
      RCLCPP_ERROR(logger_, "Joint %s has zero transmission factor", joint_names_[i].c_str());
      return false;
    }


    if (config.velocity_limit <= 0.0)
    {
      RCLCPP_ERROR(logger_, "Joint %s has invalid velocity limit", joint_names_[i].c_str());
      return false;
    }


    if (config.effort_limit <= 0.0)
    {
      RCLCPP_ERROR(logger_, "Joint %s has invalid effort limit", joint_names_[i].c_str());
      return false;
    }

    // Check for duplicate CAN IDs
    if (seen_can_ids.count(config.can_id) > 0)
    {
      RCLCPP_ERROR(logger_, "Joint %s has duplicate CAN ID 0x%03X",
        joint_names_[i].c_str(), config.can_id);
      return false;
    }
    seen_can_ids.insert(config.can_id);
  }


  return true;
}

}  // namespace motor_control_ros2

#include "pluginlib/class_list_macros.hpp"
PLUGINLIB_EXPORT_CLASS(
  motor_control_ros2::GenericHWInterface, hardware_interface::SystemInterface)
