
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

#ifndef YANTHRA_MOVE_JOINT_MOVE_H_
#define YANTHRA_MOVE_JOINT_MOVE_H_

/*
 * JOINT MOVEMENT - ROS2 Version
 */

#include <memory>
#include <string>
#include <atomic>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/float64.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <trajectory_msgs/msg/joint_trajectory_point.hpp>
#include "motor_control_msgs/srv/joint_homing.hpp"
#include "motor_control_msgs/action/joint_position_command.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"
// #include "cotton_detection/capture_cotton_srv.h"
#include "yanthra_move/srv/arm_status.hpp"


// #define JOINT_MOVE(id, pos)    move_joint_in_sync(joint_pub[id], pos, pos)
#define MOVE_JOINT(pos)    {\
  val.data = pos;\
  joint_pub->publish(val);\
}

#define WAIT  true
#define NO_WAIT  false

/* Motor Fail Conditions */
#define MOTOR_TEMP_MAX    (70)
#define MOTOR_LOAD_MAX    (0.50)
#define MOTOR_POS_ERROR_MAX  (0.2)
#define MOTOR_TIME_OUT    (3.0)

#define  NO_ERROR    (0x00)
#define  OVER_HEAT    (0x01)
#define  OVER_LOAD    (0x02)
#define  UNABLE_TO_REACH  (0x04)
#define  TIME_OUT    (0x08)
#define MOTOR_FAIL    (0x10)

/* Trajectory Types */
#define TRAJ_NONE    (0x00)
#define TRAJ_CIRCLE    (0x01)
#define TRAJ_HORIZONTAL  (0x02)
#define TRAJ_VERTICLE  (0x04)

/* Trajectory Speed */
#define SPD_LOW      (1.0)
#define SPD_MEDIUM    (5.0)
#define SPD_HIGH    (8.0)

// Result of a move_joint() call — callers MUST check this.
enum class MoveResult : int {
  SUCCESS,   // Motor reached target (confirmed by CAN feedback or service response)
  TIMEOUT,   // Service call or feedback wait timed out — motor may still be moving
  ERROR      // Service unavailable, publisher missing, or motor error code set
};

// ROS2 Joint Move Class
class joint_move
{
  rclcpp::Node::SharedPtr node_;
  std::string joint_name_;

public:
  static rclcpp::Publisher<trajectory_msgs::msg::JointTrajectory>::SharedPtr joint_pub_trajectory;
          static rclcpp_action::Client<motor_control_msgs::action::JointHoming>::SharedPtr
    joint_homing_action_client;
          static rclcpp::Client<motor_control_msgs::srv::JointHoming>::SharedPtr
    joint_idle_service;
          static rclcpp_action::Client<motor_control_msgs::action::JointPositionCommand>::SharedPtr
    joint_position_action_client;
  // static rclcpp::Client<cotton_detection::srv::CaptureCotton>::SharedPtr cotton_detection_ml_service;

  // Static publishers for fast hardware control
  static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint2_cmd_pub_;
  static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint3_cmd_pub_;
  static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint4_cmd_pub_;
  static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint5_cmd_pub_;

  std::atomic<double> current_position_;
  unsigned int error_code;
  int joint_id;

  // Position wait mode: "service", "feedback", or "blind_sleep"
  //   service    = JointPositionCommand with wait_for_completion (motor-confirmed arrival)
  //   feedback   = poll /joint_states until within tolerance (legacy, has echo bug)
  //   blind_sleep = distance-based sleep estimate (reliable fallback)
  std::string position_wait_mode_{"blind_sleep"};
  double position_tolerance_{0.005};
  double feedback_timeout_{5.0};

  // Helper: map joint name to numeric joint_id for service calls
  int getJointIdFromName() const;

  [[nodiscard]] MoveResult move_joint(double position, bool wait);

  // Update current position from motor controller feedback
  void updatePosition(double position);

  static void move_joint_trajectory(rclcpp::Node::SharedPtr node, int speed, double target_pos_3, double target_pos_4, double target_pos_5);
  static void set_joint_publishers(
      rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint2_pub,
      rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint3_pub,
      rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint4_pub,
      rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint5_pub
  );

  // Static cleanup method for proper resource cleanup
  static void cleanup_static_resources();

  /// Get the node associated with this joint (for spinning callbacks).
  rclcpp::Node::SharedPtr getNode() const { return node_; }

  joint_move(rclcpp::Node::SharedPtr node, std::string name);
  joint_move(rclcpp::Node::SharedPtr node, std::string name, int ODriveJointID);
};

#endif  // YANTHRA_MOVE_JOINT_MOVE_H_

