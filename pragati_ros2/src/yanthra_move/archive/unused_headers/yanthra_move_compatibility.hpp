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

#pragma once

/**
 * @file yanthra_move_compatibility.hpp
 * @brief Compatibility layer between YanthraMoveSystem class and existing global functions
 * 
 * This file provides function declarations and forward declarations needed to bridge
 * between the new class-based architecture and the existing procedural code.
 * This allows for gradual migration without breaking existing functionality.
 */

#include <atomic>
#include <string>
#include <memory>
#include "yanthra_move/srv/arm_status.hpp"

// Forward declarations for compatibility with existing code
extern std::atomic<bool> g_shutdown_requested;

// Global variables from yanthra_move namespace (defined in original yanthra_move.cpp)
namespace yanthra_move {
    extern std::shared_ptr<rclcpp::executors::MultiThreadedExecutor> executor;
    extern std::shared_ptr<rclcpp::Node> global_node;
    extern std::atomic<bool> executor_running;
    extern std::thread executor_thread;
    extern bool simulation_mode;
}

// Function declarations for existing global functions
extern void signal_handler_shutdown(int sig);
extern void start_keyboard_monitoring();
extern void stop_keyboard_monitoring();
extern std::string createTimestampedLogFile(std::string prefix);
extern void arm_status_function(
    const std::shared_ptr<yanthra_move::srv::ArmStatus::Request> request,
    std::shared_ptr<yanthra_move::srv::ArmStatus::Response> response);
extern void VacuumPump(bool state);
extern void camera_led(bool state);
extern void red_led_on();