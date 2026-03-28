// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");

#ifndef YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_
#define YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http:// www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


// History
// Last updated 6SEP2023 - Migrated to ROS2 Jazzy
// 6SEP2023 : Added a function ConvertXYZToPolarFLUROSCoordinates
// ROS2_MIGRATION: Updated from ROS1 to ROS2 - headers and includes updated

#ifndef YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_
#define YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_

/* ARM Movement Configuration */

/* Movement config for different modes.
 *
 *                     Calibration Mode    Test140 Mode    Switch Control Mode
 *                     ----------------    ------------    -------------------
 * AGGREGATE_PICK_EN          f                 t                   t
 * BREAD_BOARD                f                 f                   f
 * CAMERA_EN                  f                 f                   t
 * END_EFFECTOR_EN            f                 t                   t
 * HEIGHT_SCAN_EN             t                 t                   t
 * JOINT5_INIT_EN             f                 f                   f
 * MOVE_EN                    f                 f                   f
 * SHUTDOWN_SWITCH_EN         f                 t                   t
 * START_SWITCH_EN            f                 t                   t
 * UBUNTU_SHUTDWON_EN         f                 t                   t
 *
 */

// ROS2 includes
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/bool.hpp>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <trajectory_msgs/msg/joint_trajectory_point.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/buffer.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2/transform_datatypes.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>
#include <tf2/exceptions.h>

// Custom message includes (ROS2 format)
#include "yanthra_move/srv/arm_status.hpp"
#include "motor_control_msgs/srv/joint_homing.hpp"

#include <sstream>

// Standard includes
#include <vector>
#include <iostream>
#include <fstream>
#include <stdio.h>
#include <sys/time.h>
#include <time.h>
#include <string>
#include <memory>

/* Default enable for all modes */
// #define HEIGHT_SCAN_EN      true   // commmented out by ribin since it moved to yaml file

/* For CALIBRATION the operation is only manual and automatic operation using
 * start_switch and shutdown_switch should be disabled.
 */
#if CALIBRATIONMODE == true
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_


/* For Switch control mode the start_switch and shutdown switch has to be
 * enabled.
 */
#if SWITCHCONTROLMODE == true
#define AGGREGATE_PICK_EN    true
#define CAMERA_EN           true
#define END_EFFECTOR_EN     true
#define SHUTDOWN_SWITCH_EN  true
#define START_SWITCH_EN     true
#define UBUNTU_SHUTDWON_EN  true
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_

#if TEST140MODE == true
#define AGGREGATE_PICK_EN    true
#define CAMERA_EN           false
#define END_EFFECTOR_EN     true
#define SHUTDOWN_SWITCH_EN  true
#define START_SWITCH_EN     true
#define UBUNTU_SHUTDWON_EN  true
// #define MOVE_EN              true
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_

// Function declarations for coordinate transformations
void getCottonCoordinates_cameraToLink3(std::shared_ptr<tf2_ros::Buffer> tf_buffer,
    std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

void getCottonCoordinates_cameraToLink4(std::shared_ptr<tf2_ros::Buffer> tf_buffer,
    std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

void getCottonCoordinates_cameraToLink5(std::shared_ptr<tf2_ros::Buffer> tf_buffer,
    std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

void getCottonCoordinates_cameraToLink5Origin(std::shared_ptr<tf2_ros::Buffer> tf_buffer,
    std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

void getCottonCoordinates_ToYanthraOrigin(std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

void getCottonCoordinates_ToLink3(std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

void getCottonCoordinates_ToLink4(std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

void getCottonCoordinates_ToLink5(std::vector<geometry_msgs::msg::Point>* positions,
    std::vector<geometry_msgs::msg::PointStamped>* positions_baseLink);

// Debug recording function declaration
void record_debug_data();

#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_

#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CLEAN_H_
