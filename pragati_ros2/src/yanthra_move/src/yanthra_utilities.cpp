// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * @file yanthra_utilities.cpp
 * @brief Implementation of utility functions for Yanthra robotic arm system
 * @details Utility and helper functions extracted from yanthra_move.cpp
 *          for better modularity and maintainability.
 */

#include "yanthra_move/yanthra_utilities.hpp"

#include <iostream>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <yanthra_move/joint_move.h>  // For action clients
#include "motor_control_msgs/srv/joint_homing.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"
#include "git_version.h"

// External variables from main yanthra_move module
namespace yanthra_move {
    // These are defined in yanthra_move.cpp and made available here
    extern std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor;
    extern std::shared_ptr<rclcpp::Node> global_node;
    extern std::atomic<bool> executor_running;
    extern std::thread executor_thread;
    extern std::atomic<bool> simulation_mode;
}

namespace yanthra_move {
namespace utilities {

std::string getErrorDescription(unsigned int error_code) {
    switch(error_code) {
        case 0x00: return "NO_ERROR";
        case 0x01: return "OVER_HEAT";
        case 0x02: return "OVER_LOAD";
        case 0x04: return "UNABLE_TO_REACH";
        case 0x08: return "TIME_OUT";
        case 0x10: return "MOTOR_FAIL";
        default: return "UNKNOWN_ERROR(" + std::to_string(error_code) + ")";
    }
}

void blockingThreadSleep(std::chrono::milliseconds duration) {
    // WARNING: Blocks calling thread. Safe only on non-executor threads.
    std::this_thread::sleep_for(duration);
}

void startExecutorThread() {
    if (executor_running.load()) {
        if (global_node) {
            RCLCPP_WARN(global_node->get_logger(), "Executor thread already running - skipping start");
        }
        return;
    }

    if (!global_node) {
        throw std::runtime_error("Cannot start executor thread: global_node is null");
    }

    // Create SingleThreadedExecutor and add the node
    executor = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    executor->add_node(global_node);

    // Spawn background thread running executor->spin()
    executor_running.store(true);
    executor_thread = std::thread([]() {
        try {
            executor->spin();
        } catch (const std::exception& e) {
            RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),
                "Executor thread exception: %s", e.what());
        }
        executor_running.store(false);
    });

    RCLCPP_INFO(global_node->get_logger(),
        "Background executor thread started (SingleThreadedExecutor)");
}

void stopExecutorThread() {
    if (!executor_running.load()) {
        return;  // Already stopped
    }

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Stopping executor thread...");

    // Cancel the executor to unblock spin()
    if (executor) {
        executor->cancel();
    }

    // Join the thread with a 5s timeout
    if (executor_thread.joinable()) {
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        // Wait for executor thread to finish
        while (executor_running.load() &&
               std::chrono::steady_clock::now() < deadline) {
            // BLOCKING_SLEEP_OK: shutdown poll; executor thread is being joined — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }

        if (executor_thread.joinable()) {
            executor_thread.join();
        }
    }

    executor_running.store(false);

    // Remove node and destroy executor
    if (executor) {
        try {
            if (global_node) {
                executor->remove_node(global_node);
            }
        } catch (const std::exception& e) {
            RCLCPP_WARN(rclcpp::get_logger("yanthra_move"),
                        "Error removing node during shutdown: %s", e.what());
        } catch (...) {
            // Non-std exception during shutdown — safe to ignore
        }
        executor.reset();
    }

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Executor thread stopped");
}

void recordDebugData() {
    // Placeholder implementation for debug data recording
    RCLCPP_DEBUG(rclcpp::get_logger("yanthra_move"), "Debug data recording called");
}

bool callHomingService(int joint_id, std::string& reason) {
    try {
        // Check if in simulation mode first
        if (yanthra_move::simulation_mode.load()) {
            reason = "Simulation mode: Homing successful (simulated)";
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Simulation mode: Skipping homing for joint %d", joint_id);
            return true;
        }

        // Check if ROS2 context is still valid
        if (!rclcpp::ok()) {
            reason = "ROS2 context is not valid";
            return false;
        }

        if (!joint_move::joint_homing_action_client) {
            reason = "Homing action client not initialized";
            return false;
        }

        // Wait for action server to be available
        if (!joint_move::joint_homing_action_client->wait_for_action_server(std::chrono::seconds(2))) {
            reason = "Homing action server not available after timeout";
            RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Homing action server not available - this is normal in simulation mode");
            return false;
        }

        // Build action goal
        auto goal_msg = motor_control_msgs::action::JointHoming::Goal();
        goal_msg.joint_ids = {joint_id};

        auto send_goal_options = rclcpp_action::Client<motor_control_msgs::action::JointHoming>::SendGoalOptions();
        auto goal_handle_future = joint_move::joint_homing_action_client->async_send_goal(goal_msg, send_goal_options);

        // Wait for goal acceptance
        if (goal_handle_future.wait_for(std::chrono::seconds(5)) != std::future_status::ready) {
            reason = "Homing action goal acceptance timed out";
            return false;
        }

        auto goal_handle = goal_handle_future.get();
        if (!goal_handle) {
            reason = "Homing action goal was rejected by server";
            return false;
        }

        // Wait for result
        auto result_future = joint_move::joint_homing_action_client->async_get_result(goal_handle);
        if (result_future.wait_for(std::chrono::seconds(15)) != std::future_status::ready) {
            reason = "Homing action result timed out";
            joint_move::joint_homing_action_client->async_cancel_goal(goal_handle);
            return false;
        }

        auto wrapped_result = result_future.get();
        auto result = wrapped_result.result;
        reason = result->reason;
        return result->success;
    } catch (const std::exception& e) {
        reason = std::string("Homing action call exception: ") + e.what();
        return false;
    }
}

bool callIdleService(int joint_id, std::string& reason) {
    try {
        // Check if ROS2 context is still valid
        if (!rclcpp::ok()) {
            reason = "ROS2 context is not valid";
            return false;
        }

        if (!joint_move::joint_idle_service) {
            reason = "Service client not initialized";
            return false;
        }

        if (!joint_move::joint_idle_service->service_is_ready()) {
            reason = "Service not available";
            return false;
        }

        auto request = std::make_shared<motor_control_msgs::srv::JointHoming::Request>();
        request->joint_id = joint_id;

        auto future = joint_move::joint_idle_service->async_send_request(request);

        // Wait for the service call to complete
        std::chrono::seconds timeout(5);  // Reduced timeout for faster failure
        auto status = future.wait_for(timeout);

        if (status == std::future_status::ready) {
            auto response = future.get();
            reason = response->reason;
            return response->success;
        }
        reason = "Service call timed out";
        return false;
    } catch (const std::exception& e) {
        reason = std::string("Service call exception: ") + e.what();
        return false;
    }
}

void printVersionAndDate(const char* program_name) {
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "The %s Version: %s built on: %s", program_name, VERSION, getBuildTimestamp());
}

}  // namespace utilities
}  // namespace yanthra_move
// GPIO global variables definitions (declared in yanthra_io.h)
#ifdef ENABLE_PIGPIO
int pi = -1;
unsigned gpio_pin_number = 0;
unsigned pulsewidth = 0;
#endif
