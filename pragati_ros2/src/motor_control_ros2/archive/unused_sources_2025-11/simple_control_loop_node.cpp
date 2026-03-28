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

/*
 * Author: ROS2 Migration Team
 * Description: Simple Control Loop Node for ODrive Hardware Interface
 *
 * This provides a simpler control loop implementation that coordinates
 * hardware read/write operations.
 */

#include <chrono>
#include <memory>
#include <thread>

#include "rclcpp/rclcpp.hpp"
#include "hardware_interface/system_interface.hpp"
#include "motor_control_ros2/odrive_legacy/odrive_hardware_interface.hpp"

class SimpleControlLoopNode : public rclcpp::Node
{
public:
    explicit SimpleControlLoopNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions())
    : rclcpp::Node("odrive_control_loop", options)
    , control_loop_running_(false)
    {
        // Declare parameters
        this->declare_parameter("loop_hz", 100.0);


        loop_hz_ = this->get_parameter("loop_hz").as_double();

        RCLCPP_INFO(this->get_logger(), "Simple Control Loop Node initialized at %.1f Hz", loop_hz_);

        // Initialize hardware interface
        hw_interface_ = std::make_shared<motor_control_ros2::ODriveHardwareInterface>();

        // Start control loop
        start_control_loop();
    }

    ~SimpleControlLoopNode()
    {
        stop_control_loop();
    }


private:
    void start_control_loop()
    {
        if (control_loop_running_) {
            return;
        }


        control_loop_running_ = true;
        control_thread_ = std::thread(&SimpleControlLoopNode::control_loop, this);

        RCLCPP_INFO(this->get_logger(), "Control loop started");
    }

    void stop_control_loop()
    {
        if (!control_loop_running_) {
            return;
        }


        control_loop_running_ = false;
        if (control_thread_.joinable()) {
            control_thread_.join();
        }

        RCLCPP_INFO(this->get_logger(), "Control loop stopped");
    }

    void control_loop()
    {
        auto loop_rate = rclcpp::Rate(loop_hz_);
        auto last_time = this->now();


        RCLCPP_INFO(this->get_logger(), "Control loop thread started");

        while (control_loop_running_ && rclcpp::ok()) {
            auto current_time = this->now();
            auto elapsed_duration = current_time - last_time;
            last_time = current_time;

            // Simple read/write cycle
            try {
                if (hw_interface_) {
                    // Read from hardware
                    auto read_result = hw_interface_->read(current_time, elapsed_duration);
                    if (read_result != hardware_interface::return_type::OK) {
                        RCLCPP_WARN_THROTTLE(
                            this->get_logger(), *this->get_clock(), 1000,
                            "Hardware interface read failed"
                        );
                    }

                    // Write to hardware
                    auto write_result = hw_interface_->write(current_time, elapsed_duration);
                    if (write_result != hardware_interface::return_type::OK) {
                        RCLCPP_WARN_THROTTLE(
                            this->get_logger(), *this->get_clock(), 1000,
                            "Hardware interface write failed"
                        );
                    }
                }
            }
            catch (const std::exception & e) {
                RCLCPP_ERROR_THROTTLE(
                    this->get_logger(), *this->get_clock(), 1000,
                    "Exception in control loop: %s", e.what()
                );
            }

            loop_rate.sleep();
        }

        RCLCPP_INFO(this->get_logger(), "Control loop thread finished");
    }

    // Core components
    std::shared_ptr<motor_control_ros2::ODriveHardwareInterface> hw_interface_;

    // Control loop management
    std::thread control_thread_;
    std::atomic<bool> control_loop_running_;

    // Configuration
    double loop_hz_;
};

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);


    auto node = std::make_shared<SimpleControlLoopNode>();

    RCLCPP_INFO(node->get_logger(), "Starting Simple ODrive Control Loop Node");

    try {
        rclcpp::spin(node);
    }
    catch (const std::exception & e) {
        RCLCPP_FATAL(node->get_logger(), "Exception in main: %s", e.what());
    }

    RCLCPP_INFO(node->get_logger(), "Shutting down Simple ODrive Control Loop Node");
    rclcpp::shutdown();
    return 0;
}
