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
 * @file yanthra_utilities.hpp
 * @brief Utility functions for Yanthra robotic arm system
 * @details This module contains utility and helper functions
 *          extracted from yanthra_move.cpp for better modularity.
 *          Includes error handling, ROS2 service calls, threading utilities, etc.
 */

#ifndef YANTHRA_MOVE_YANTHRA_UTILITIES_HPP_
#define YANTHRA_MOVE_YANTHRA_UTILITIES_HPP_

#include <string>
#include <chrono>
#include <memory>
#include <atomic>
#include <thread>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/single_threaded_executor.hpp>

// Forward declarations to avoid circular dependencies
namespace yanthra_move {

// External dependencies that need to be available
extern std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor;
extern std::shared_ptr<rclcpp::Node> global_node;
extern std::atomic<bool> executor_running;
extern std::thread executor_thread;
extern std::atomic<bool> simulation_mode;

namespace utilities {

// Program constants
#define VERSION "1.0.0"
#define ARUCO_FINDER_PROGRAM "/usr/local/bin/aruco_finder"

/**
 * @brief Convert error code to human-readable description
 * @param error_code Error code from hardware
 * @return String description of the error
 */
std::string getErrorDescription(unsigned int error_code);

/**
 * @brief Blocking thread sleep — WARNING: blocks the calling thread
 * @param duration Duration to sleep in milliseconds
 * @details WARNING: Do NOT call from ROS2 executor callbacks. This function
 *          blocks the calling thread with std::this_thread::sleep_for.
 *          Callbacks are processed by the background executor thread, so this
 *          is safe ONLY on the main operation thread or dedicated worker threads.
 */
void blockingThreadSleep(std::chrono::milliseconds duration);

/**
 * @brief Start executor thread for continuous ROS2 callback processing
 * @details Creates a separate thread to handle ROS2 callbacks continuously
 */
void startExecutorThread();

/**
 * @brief Stop executor thread gracefully
 * @details Stops the executor thread and waits for it to join
 */
void stopExecutorThread();

/**
 * @brief Record debug data for troubleshooting
 * @details Placeholder implementation for debug data recording
 */
void recordDebugData();

/**
 * @brief Call homing service for a specific joint
 * @param joint_id ID of the joint to home
 * @param reason Output parameter containing success/failure reason
 * @return true if homing successful, false otherwise
 * @details Handles simulation mode, timeouts, and proper error handling
 */
bool callHomingService(int joint_id, std::string& reason);

/**
 * @brief Call idle service for a specific joint
 * @param joint_id ID of the joint to set idle
 * @param reason Output parameter containing success/failure reason
 * @return true if idle successful, false otherwise
 * @details Handles timeouts and proper error handling
 */
bool callIdleService(int joint_id, std::string& reason);

/**
 * @brief Print version and compilation date information
 * @param program_name Name of the program to display
 * @details Displays version, build date, and other program information
 */
void printVersionAndDate(const char* program_name);

}  // namespace utilities
}  // namespace yanthra_move

#endif  // YANTHRA_MOVE_YANTHRA_UTILITIES_HPP_
