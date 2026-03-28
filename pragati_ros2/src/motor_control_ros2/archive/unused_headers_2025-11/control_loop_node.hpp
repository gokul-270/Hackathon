/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http:  // www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef ODRIVE_CONTROL_ROS2_CONTROL_LOOP_NODE_HPP_
#define ODRIVE_CONTROL_ROS2_CONTROL_LOOP_NODE_HPP_


/*
 * Author: ROS2 Migration Team
 * Description: Header for ROS2 Control Loop Node for ODrive Hardware Interface
 *
 * This header defines the control loop node class that replaces the ROS1
 * generic_hw_control_loop functionality with ROS2-compatible lifecycle management.
 */

#pragma once

#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <thread>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "controller_manager/controller_manager.hpp"
#include "hardware_interface/system_interface.hpp"

namespace motor_control_ros2
{


// Forward declarations
class ODriveHardwareInterface;
class SafetyMonitor;

/**
 * @brief Lifecycle node that manages the main control loop for ODrive hardware
 *
 * This class provides:
 * - Monotonic timing for precise control cycles
 * - Lifecycle node management (configure, activate, deactivate, cleanup)
 * - Controller manager integration
 * - Safety monitoring integration
 * - Configurable loop frequency and realtime priority
 * - Error handling and cycle time monitoring
 */
class ControlLoopNode : public rclcpp_lifecycle::LifecycleNode
{
public:
    /**
     * @brief Constructor
     * @param options Node options for configuration
     */
    explicit ControlLoopNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());


    /**
     * @brief Destructor - ensures control loop is stopped
     */
    ~ControlLoopNode();

    // Lifecycle callbacks
    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_configure(const rclcpp_lifecycle::State &) override;

    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_activate(const rclcpp_lifecycle::State &) override;

    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_deactivate(const rclcpp_lifecycle::State &) override;

    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_cleanup(const rclcpp_lifecycle::State &) override;

private:
    /**
     * @brief Start the control loop thread
     */
    void start_control_loop();

    /**
     * @brief Stop the control loop thread and wait for completion
     */
    void stop_control_loop();

    /**
     * @brief Main control loop function running in separate thread
     *
     * This function:
     * - Maintains precise timing using monotonic clock
     * - Reads from hardware interface
     * - Updates controller manager
     * - Writes to hardware interface
     * - Monitors safety conditions
     * - Tracks cycle time performance
     */
    void control_loop();

    // Core components
    std::shared_ptr<ODriveHardwareInterface> hw_interface_;
    std::shared_ptr<controller_manager::ControllerManager> controller_manager_;
    std::shared_ptr<SafetyMonitor> safety_monitor_;

    // Control loop management
    std::thread control_thread_;
    std::atomic<bool> control_loop_running_;

    // Timing parameters
    double loop_hz_;                                          /  // < Control loop frequency in Hz
    std::chrono::duration<double> desired_update_period_;    /  // < Target period between updates
    double cycle_time_error_threshold_;                      /  // < Maximum acceptable cycle time error (seconds)
    int realtime_priority_;                                  /  // < Realtime thread priority (0 = no realtime)
    bool enable_safety_monitoring_;                          /  // < Whether to enable safety monitoring
}

}  // namespace motor_control_ros2

#endif  // ODRIVE_CONTROL_ROS2__CONTROL_LOOP_NODE_HPP_
