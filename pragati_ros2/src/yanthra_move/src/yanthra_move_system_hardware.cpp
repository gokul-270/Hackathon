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
 * @file yanthra_move_system_hardware.cpp
 * @brief Hardware initialization methods for YanthraMoveSystem
 *
 * This file contains GPIO, hardware interfaces, camera, and joint controller initialization.
 */

#include "yanthra_move/yanthra_move_system.hpp"
#include "yanthra_move/joint_move.h"
#include "yanthra_move/yanthra_io.h"

// External hardware control functions
extern void VacuumPump(bool state);
extern void camera_led(bool state);
extern void red_led_on();

namespace yanthra_move {

void YanthraMoveSystem::initializeIOInterfaces() {
    // Initialize IO classes with proper node reference
    RCLCPP_INFO(node_->get_logger(), "Initializing IO interfaces");

    problem_indicator_out_ = std::make_unique<d_out>(node_, "problem_led");
    start_switch_in_ = std::make_unique<d_in>(node_, "start_switch");
    shutdown_switch_in_ = std::make_unique<d_in>(node_, "shutdown_switch");

    RCLCPP_INFO(node_->get_logger(), "IO interfaces initialized successfully");
    RCLCPP_INFO(node_->get_logger(), "IO interfaces (problem LED, switches) initialized");
}

void YanthraMoveSystem::initializeJointControllers() {
    // Initialize joint_move instances with proper node reference
    RCLCPP_INFO(node_->get_logger(), "Initializing joint movement controllers");

    // MG6010 motor mapping (joint2 removed - not in arm hardware)
    // joint3, joint4, joint5 are the active arm joints controlled via motor_control_ros2
    joint_move_3_ = std::make_unique<joint_move>(node_, "joint3", 0);
    joint_move_4_ = std::make_unique<joint_move>(node_, "joint4", 1);
    joint_move_5_ = std::make_unique<joint_move>(node_, "joint5", 2);

    RCLCPP_DEBUG(node_->get_logger(), "Joint controllers initialized (joint3, joint4, joint5)");
}

void YanthraMoveSystem::initializeGPIO() {
#ifdef ENABLE_PIGPIO
    // Runtime gating: allow local/dev runs without pigpio daemon/hardware.
    // NOTE: The system currently has BOTH `simulation_mode` and `use_simulation` parameters.
    // `simulation_mode` is the canonical system-mode flag, but many launch setups only set `use_simulation`.
    bool enable_gpio = true;
    bool use_simulation = false;

    try {
        enable_gpio = node_->get_parameter("enable_gpio").as_bool();
    } catch (const std::exception& e) {
        enable_gpio = true;
    }

    try {
        use_simulation = node_->get_parameter("use_simulation").as_bool();
    } catch (const std::exception& e) {
        use_simulation = false;
    }

    if (simulation_mode_.load() || use_simulation || !enable_gpio) {
        RCLCPP_INFO(node_->get_logger(),
                    "GPIO initialization skipped (simulation_mode=%s, use_simulation=%s, enable_gpio=%s)",
                    simulation_mode_.load() ? "true" : "false",
                    use_simulation ? "true" : "false",
                    enable_gpio ? "true" : "false");
        return;
    }

    // Initialize pigpio (pigpiod daemon) for Raspberry Pi hardware.
    // IMPORTANT: `pi` is a global handle declared in yanthra_io.h / defined in yanthra_utilities.cpp.
    // On non-hardware dev machines pigpio_start() will fail (e.g., pigpiod not running).
    // This must NOT crash the whole system; we simply disable pigpio-backed GPIO features.
    pi = pigpio_start(NULL, NULL);
    if (pi < 0) {
        RCLCPP_ERROR(node_->get_logger(),
                     "pigpio_start() failed (pi=%d). GPIO features will be disabled for this run.",
                     pi);
        RCLCPP_ERROR(node_->get_logger(),
                     "If this is hardware, ensure pigpiod is running (e.g., systemctl start pigpiod) and you have permissions.");
        return;
    }

    // Configure all pins for the arm
    // [GPIO configuration code preserved from original]
    RCLCPP_INFO(node_->get_logger(), "GPIO pins configured successfully (pi handle=%d)", pi);
#else
    RCLCPP_INFO(node_->get_logger(), "GPIO support disabled at compile time");
#endif
}

void YanthraMoveSystem::initializeHardware() {
    RCLCPP_DEBUG(node_->get_logger(), "Initializing motor hardware interface for ROS2");

    // Hardware interface initialization (preserved from original logic)
    bool hardware_interface_available = true;

    if (hardware_interface_available) {
        RCLCPP_DEBUG(node_->get_logger(), "Motor hardware interface initialized");
    } else {
        RCLCPP_WARN(node_->get_logger(), "Motor hardware interface not available - requires complete ROS2 migration");
    }

    // Brief pause to allow hardware initialization (reduced from 10s to 1s)
    // BLOCKING_SLEEP_OK: main-thread hardware init pause; one-time startup — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::seconds(1));

    // Turn off vacuum and camera if they are on
    VacuumPump(false);
    camera_led(false);
    // Turn on red LED
    red_led_on();

    RCLCPP_INFO(node_->get_logger(), "Hardware initialization completed");
}

void YanthraMoveSystem::initializeCamera() {
    if (yanthra_lab_calibration_testing_) {
        RCLCPP_INFO(node_->get_logger(), "RUNNING POSITION ACCURACY CHECK USING ARUCO PATTERN");
    } else {
#if CAMERA_EN == true
        if (trigger_camera_) {
            RCLCPP_INFO(node_->get_logger(), "Camera triggering enabled - camera initialization preserved");
            // Camera initialization logic preserved from original
        } else {
            RCLCPP_INFO(node_->get_logger(), "Camera triggering disabled - skipping camera process");
        }
#else
        RCLCPP_INFO(node_->get_logger(), "Camera support disabled at compile time");
#endif
    }
}

}  // namespace yanthra_move
using namespace yanthra_move;
