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

#ifndef ODRIVE_CONTROL_ROS2__MOTOR_ABSTRACTION_HPP_
#define ODRIVE_CONTROL_ROS2__MOTOR_ABSTRACTION_HPP_

/*
 * Hardware Abstraction Layer for Motor Control
 *
 * This file defines the core abstractions needed to support multiple motor types
 * (ODrive, MG6010, etc.) through a common interface. This enables seamless
 * migration between motor systems without changing application-level code.
 *
 * Design Principles:
 * 1. Motor-agnostic interface for position, velocity, and torque control
 * 2. Unified configuration and parameter management
 * 3. Common safety and error handling
 * 4. Extensible factory pattern for new motor types
 * 5. Maintain all existing ODrive functionality while enabling MG6010 migration
 *
 * NOTE: This is now a forwarding header. The types and interfaces have been
 * split into focused headers for faster incremental builds. Include the
 * specific header you need instead of this umbrella header when possible:
 *
 *   motor_types.hpp               - MotorStatus, SafetyLimits, HomingConfig, MotorConfiguration
 *   can_interface.hpp             - CANInterface abstract class
 *   motor_controller_interface.hpp - MotorControllerInterface abstract class
 *   error_handling.hpp            - ErrorFramework, ErrorHandler, DefaultErrorHandler, ErrorFactory
 *   motor_factory.hpp             - MotorControllerFactory, ConfigurationManager
 */

#pragma once

#include "motor_control_ros2/error_handling.hpp"
#include "motor_control_ros2/motor_types.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/motor_factory.hpp"

#endif // ODRIVE_CONTROL_ROS2__MOTOR_ABSTRACTION_HPP_
