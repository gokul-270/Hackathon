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
 * Description: ROS2 Control Loop Node for ODrive Hardware Interface
 *
 * This file replaces the ROS1 generic_hw_control_loop.cpp functionality
 * with ROS2-compatible lifecycle management and controller coordination.
 *
 * Key Features:
 * - Monotonic timing for precise control cycles
 * - Lifecy    // Core components
    std::shared_ptr<ODriveHardwareInterface> hw_interface_;
    std::shared_ptr<controller_manager::ControllerManager> controller_manager_;
    std::shared_ptr<SafetyMonitor> safety_monitor_;node management
 * - Controller manager integration
 * - Safety monitoring integration
 * - Configurable loop frequency
 */

#include <chrono>
#include <memory>
#include <string>
#include <thread>

#include <pthread.h>
#include <sched.h>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "controller_manager/controller_manager.hpp"
#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/resource_manager.hpp"
#include "realtime_tools/realtime_helpers.hpp"

#include "motor_control_ros2/odrive_hardware_interface.hpp"
#include "motor_control_ros2/safety_monitor.hpp"

namespace motor_control_ros2
{


class ControlLoopNode : public rclcpp_lifecycle::LifecycleNode
{
public:
    explicit ControlLoopNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions())
    : rclcpp_lifecycle::LifecycleNode("odrive_control_loop", options)
    , control_loop_running_(false)
    , cycle_time_error_threshold_(0.01)  // 10ms threshold
    {
        // Declare parameters
        this->declare_parameter("loop_hz", 100.0);
        this->declare_parameter("cycle_time_error_threshold", 0.01);
        this->declare_parameter("realtime_priority", 50);
        this->declare_parameter("enable_safety_monitoring", true);


        RCLCPP_INFO(this->get_logger(), "ODrive Control Loop Node initialized");
    }

    ~ControlLoopNode()
    {
        stop_control_loop();
    }


    // Lifecycle callbacks
    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_configure(const rclcpp_lifecycle::State &) override
    {
        RCLCPP_INFO(this->get_logger(), "Configuring ODrive Control Loop");


        try {
            // Get parameters
            loop_hz_ = this->get_parameter("loop_hz").as_double();
            cycle_time_error_threshold_ = this->get_parameter("cycle_time_error_threshold").as_double();
            realtime_priority_ = this->get_parameter("realtime_priority").as_int();
            enable_safety_monitoring_ = this->get_parameter("enable_safety_monitoring").as_bool();

            desired_update_period_ = std::chrono::duration<double>(1.0 / loop_hz_);

            RCLCPP_INFO(this->get_logger(), "Control loop configured: %.1f Hz, cycle threshold: %.3f ms",
                       loop_hz_, cycle_time_error_threshold_ * 1000.0);

            // Initialize hardware interface
            hw_interface_ = std::make_shared<ODriveHardwareInterface>();

            // Initialize controller manager using a simpler approach
            controller_manager_ = std::make_shared<controller_manager::ControllerManager>(
                std::make_shared<rclcpp::executors::SingleThreadedExecutor>(),
                "controller_manager"
            );

            // Initialize safety monitor if enabled
            if (enable_safety_monitoring_) {
                safety_monitor_ = std::make_shared<SafetyMonitor>(
                    this->get_node_base_interface(),
                    this->get_node_logging_interface(),
                    this->get_node_parameters_interface(),
                    this->get_node_topics_interface()
                );
                RCLCPP_INFO(this->get_logger(), "Safety monitoring enabled");
            }

            return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
        }
        catch (const std::exception & e) {
            RCLCPP_ERROR(this->get_logger(), "Failed to configure: %s", e.what());
            return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
        }
    }

    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_activate(const rclcpp_lifecycle::State &) override
    {
        RCLCPP_INFO(this->get_logger(), "Activating ODrive Control Loop");


        try {
            // Initialize hardware interface
            if (hw_interface_->on_init(hardware_interface::HardwareInfo{}) !=
                hardware_interface::CallbackReturn::SUCCESS) {
                RCLCPP_ERROR(this->get_logger(), "Failed to initialize hardware interface");
                return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
            }

            // Configure hardware interface
            if (hw_interface_->on_configure(rclcpp_lifecycle::State{}) !=
                hardware_interface::CallbackReturn::SUCCESS) {
                RCLCPP_ERROR(this->get_logger(), "Failed to configure hardware interface");
                return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
            }

            // Activate hardware interface
            if (hw_interface_->on_activate(rclcpp_lifecycle::State{}) !=
                hardware_interface::CallbackReturn::SUCCESS) {
                RCLCPP_ERROR(this->get_logger(), "Failed to activate hardware interface");
                return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
            }

            // Activate safety monitor
            if (safety_monitor_ && !safety_monitor_->activate()) {
                RCLCPP_ERROR(this->get_logger(), "Failed to activate safety monitor");
                return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
            }

            // Start control loop
            start_control_loop();

            RCLCPP_INFO(this->get_logger(), "ODrive Control Loop activated successfully");
            return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
        }
        catch (const std::exception & e) {
            RCLCPP_ERROR(this->get_logger(), "Failed to activate: %s", e.what());
            return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
        }
    }

    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_deactivate(const rclcpp_lifecycle::State &) override
    {
        RCLCPP_INFO(this->get_logger(), "Deactivating ODrive Control Loop");


        stop_control_loop();

        // Deactivate safety monitor
        if (safety_monitor_) {
            safety_monitor_->deactivate();
        }

        // Deactivate hardware interface
        if (hw_interface_) {
            hw_interface_->on_deactivate(rclcpp_lifecycle::State{});
        }

        RCLCPP_INFO(this->get_logger(), "ODrive Control Loop deactivated");
        return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
    }

    rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
    on_cleanup(const rclcpp_lifecycle::State &) override
    {
        RCLCPP_INFO(this->get_logger(), "Cleaning up ODrive Control Loop");


        stop_control_loop();

        // Cleanup hardware interface
        if (hw_interface_) {
            hw_interface_->on_cleanup(rclcpp_lifecycle::State{});
            hw_interface_.reset();
        }

        // Cleanup controller manager
        controller_manager_.reset();

        // Cleanup safety monitor
        safety_monitor_.reset();

        RCLCPP_INFO(this->get_logger(), "ODrive Control Loop cleaned up");
        return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
    }

private:
    void start_control_loop()
    {
        if (control_loop_running_) {
            return;
        }


        control_loop_running_ = true;
        control_thread_ = std::thread(&ControlLoopNode::control_loop, this);

        // Set realtime priority
        if (realtime_priority_ > 0 && realtime_priority_ <= 99) {
            if (set_thread_realtime_priority(control_thread_.native_handle(), realtime_priority_)) {
                RCLCPP_INFO(this->get_logger(), 
                    "✅ Realtime priority %d set successfully for control loop thread",
                    realtime_priority_);
            } else {
                RCLCPP_WARN(this->get_logger(), 
                    "⚠️  Failed to set realtime priority %d (may need sudo/CAP_SYS_NICE). Running with normal priority.",
                    realtime_priority_);
            }
        }

        RCLCPP_INFO(this->get_logger(), "Control loop started at %.1f Hz", loop_hz_);
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

    /**
     * @brief Set realtime priority for a thread using POSIX scheduling
     * @param thread_handle Native thread handle
     * @param priority Priority level (1-99, higher = more priority)
     * @return true if successful, false otherwise
     * 
     * Note: Requires CAP_SYS_NICE capability or sudo privileges
     * To enable without sudo: sudo setcap cap_sys_nice+ep /path/to/executable
     */
    bool set_thread_realtime_priority(pthread_t thread_handle, int priority)
    {
        struct sched_param param;
        param.sched_priority = priority;

        int result = pthread_setschedparam(thread_handle, SCHED_FIFO, &param);
        
        if (result != 0) {
            return false;
        }

        // Verify the setting
        int policy;
        struct sched_param verify_param;
        if (pthread_getschedparam(thread_handle, &policy, &verify_param) == 0) {
            return (policy == SCHED_FIFO && verify_param.sched_priority == priority);
        }

        return true;
    }

    void control_loop()
    {
        auto last_time = std::chrono::steady_clock::now();
        auto next_iteration_time = last_time + desired_update_period_;


        RCLCPP_INFO(this->get_logger(), "Control loop thread started");

        while (control_loop_running_ && rclcpp::ok()) {
            auto current_time = std::chrono::steady_clock::now();
            auto elapsed_time = current_time - last_time;
            last_time = current_time;

            // Convert to ros2 duration
            auto elapsed_duration = rclcpp::Duration::from_nanoseconds(
                std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed_time).count()
            );

            // Check cycle time
            auto cycle_time_error = elapsed_time - desired_update_period_;
            if (std::chrono::duration<double>(cycle_time_error).count() > cycle_time_error_threshold_) {
                RCLCPP_WARN_THROTTLE(
                    this->get_logger(), *this->get_clock(), 1000,
                    "Control loop cycle time exceeded threshold by: %.3f ms (cycle: %.3f ms, threshold: %.3f ms)",
                    std::chrono::duration<double>(cycle_time_error).count() * 1000.0,
                    std::chrono::duration<double>(elapsed_time).count() * 1000.0,
                    cycle_time_error_threshold_ * 1000.0
                );
            }

            // Safety monitoring check
            if (safety_monitor_ && !safety_monitor_->is_safe()) {
                RCLCPP_ERROR(this->get_logger(), "Safety violation detected - stopping control loop");
                // Emergency stop - deactivate hardware interface
                if (hw_interface_) {
                    hw_interface_->on_deactivate(rclcpp_lifecycle::State{});
                }
                break;
            }

            // Read from hardware
            try {
                if (hw_interface_) {
                    auto return_type = hw_interface_->read(this->now(), elapsed_duration);
                    if (return_type != hardware_interface::return_type::OK) {
                        RCLCPP_ERROR_THROTTLE(
                            this->get_logger(), *this->get_clock(), 1000,
                            "Hardware interface read failed with return type: %d",
                            static_cast<int>(return_type)
                        );
                    }
                }
            }
            catch (const std::exception & e) {
                RCLCPP_ERROR_THROTTLE(
                    this->get_logger(), *this->get_clock(), 1000,
                    "Exception during hardware read: %s", e.what()
                );
            }

            // Update controller manager
            try {
                if (controller_manager_) {
                    controller_manager_->update(this->now(), elapsed_duration);
                }
            }
            catch (const std::exception & e) {
                RCLCPP_ERROR_THROTTLE(
                    this->get_logger(), *this->get_clock(), 1000,
                    "Exception during controller manager update: %s", e.what()
                );
            }

            // Write to hardware
            try {
                if (hw_interface_) {
                    auto return_type = hw_interface_->write(this->now(), elapsed_duration);
                    if (return_type != hardware_interface::return_type::OK) {
                        RCLCPP_ERROR_THROTTLE(
                            this->get_logger(), *this->get_clock(), 1000,
                            "Hardware interface write failed with return type: %d",
                            static_cast<int>(return_type)
                        );
                    }
                }
            }
            catch (const std::exception & e) {
                RCLCPP_ERROR_THROTTLE(
                    this->get_logger(), *this->get_clock(), 1000,
                    "Exception during hardware write: %s", e.what()
                );
            }

            // Update safety monitor
            if (safety_monitor_) {
                safety_monitor_->update();
            }

            // Sleep until next iteration
            next_iteration_time += desired_update_period_;
            std::this_thread::sleep_until(next_iteration_time);
        }

        RCLCPP_INFO(this->get_logger(), "Control loop thread finished");
    }

    // Control loop management
    std::thread control_thread_;
    std::atomic<bool> control_loop_running_;

    // Timing parameters
    double loop_hz_;
    std::chrono::duration<double> desired_update_period_;
    double cycle_time_error_threshold_;
    int realtime_priority_;
    bool enable_safety_monitoring_;
}

}  // namespace motor_control_ros2

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);


    auto node = std::make_shared<motor_control_ros2::ControlLoopNode>();

    // Use MultiThreadedExecutor for proper lifecycle handling
    rclcpp::executors::MultiThreadedExecutor executor;
    executor.add_node(node->get_node_base_interface());

    RCLCPP_INFO(node->get_logger(), "Starting ODrive Control Loop Node");

    try {
        executor.spin();
    }
    catch (const std::exception & e) {
        RCLCPP_FATAL(node->get_logger(), "Exception in executor: %s", e.what());
    }

    RCLCPP_INFO(node->get_logger(), "Shutting down ODrive Control Loop Node");
    rclcpp::shutdown();
    return 0;
}
