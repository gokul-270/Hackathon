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
 * @file joint_move.cpp
 * @brief Implementation of the joint_move class
 * @details Implementation file for joint_move class static members and methods
 *          Extracted from header file to prevent multiple definition errors
 */

#include "yanthra_move/joint_move.h"
#include <rclcpp/rclcpp.hpp>
#include <chrono>
#include <memory>
#include <thread>

// Forward declaration to access simulation_mode from yanthra_move namespace
#include <atomic>
namespace yanthra_move {
    extern std::atomic<bool> simulation_mode;
}

// Static member definitions (moved from header file)
rclcpp::Publisher<trajectory_msgs::msg::JointTrajectory>::SharedPtr joint_move::joint_pub_trajectory;
rclcpp_action::Client<motor_control_msgs::action::JointHoming>::SharedPtr joint_move::joint_homing_action_client;
rclcpp::Client<motor_control_msgs::srv::JointHoming>::SharedPtr joint_move::joint_idle_service;
rclcpp_action::Client<motor_control_msgs::action::JointPositionCommand>::SharedPtr joint_move::joint_position_action_client;

// Static publishers for fast hardware control
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint_move::joint2_cmd_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint_move::joint3_cmd_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint_move::joint4_cmd_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint_move::joint5_cmd_pub_;

// Constructor implementations (moved from header file)
joint_move::joint_move(rclcpp::Node::SharedPtr node, std::string name, int ODriveJointID)
  : node_(node), joint_name_(name), current_position_(0.0), error_code(NO_ERROR), joint_id(ODriveJointID)
{
  // Read position wait mode from node
  position_wait_mode_ = node_->get_parameter("position_wait_mode").as_string();
  // position_tolerance_ set by MotionController::initialize() from motor_control node
  // Default from joint_move.h member initializer used until then
  feedback_timeout_ = node_->get_parameter("feedback_timeout").as_double();

  RCLCPP_DEBUG(node_->get_logger(), "Joint move created for %s (motor_id: %d, wait_mode: %s)",
      name.c_str(), ODriveJointID, position_wait_mode_.c_str());
}

joint_move::joint_move(rclcpp::Node::SharedPtr node, std::string name)
  : node_(node), joint_name_(name), current_position_(0.0), error_code(NO_ERROR), joint_id(-1)
{
  // Read position wait mode from node
  position_wait_mode_ = node_->get_parameter("position_wait_mode").as_string();
  // position_tolerance_ set by MotionController::initialize() from motor_control node
  // Default from joint_move.h member initializer used until then
  feedback_timeout_ = node_->get_parameter("feedback_timeout").as_double();

  RCLCPP_DEBUG(node_->get_logger(), "Joint move created for %s (wait_mode: %s)",
      name.c_str(), position_wait_mode_.c_str());
}

// Map joint name to numeric ID for JointPositionCommand service
int joint_move::getJointIdFromName() const {
  // motor_control maps "jointN" -> joint_id N
  if (joint_name_ == "joint3") return 3;
  if (joint_name_ == "joint4") return 4;
  if (joint_name_ == "joint5") return 5;
  if (joint_name_ == "joint2") return 2;
  return -1;
}

// Function to set publishers from main - static member function implementation
void joint_move::set_joint_publishers(
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint2_pub,
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint3_pub,
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint4_pub,
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint5_pub
) {
    joint2_cmd_pub_ = joint2_pub;
    joint3_cmd_pub_ = joint3_pub;
    joint4_cmd_pub_ = joint4_pub;
    joint5_cmd_pub_ = joint5_pub;
}

// Update position from motor controller feedback (called by motion_controller's /joint_states callback)
void joint_move::updatePosition(double position) {
  current_position_.store(position, std::memory_order_relaxed);
}

// Move joint implementation - FAST PUBLISHER-BASED CONTROL
MoveResult joint_move::move_joint(double value, bool wait)
{
  if(error_code != NO_ERROR)
  {
    RCLCPP_ERROR(node_->get_logger(), "Can't move joint %s, error: %u", joint_name_.c_str(), error_code);
    return MoveResult::ERROR;
  }

  // Select the correct publisher based on joint name
  rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr publisher;
  if (joint_name_ == "joint2" && joint2_cmd_pub_) {
      publisher = joint2_cmd_pub_;
  } else if (joint_name_ == "joint3" && joint3_cmd_pub_) {
      publisher = joint3_cmd_pub_;
  } else if (joint_name_ == "joint4" && joint4_cmd_pub_) {
      publisher = joint4_cmd_pub_;
  } else if (joint_name_ == "joint5" && joint5_cmd_pub_) {
      publisher = joint5_cmd_pub_;
  } else {
      RCLCPP_ERROR(node_->get_logger(), "No publisher found for joint: %s", joint_name_.c_str());
      return MoveResult::ERROR;
  }

  // In service mode, skip topic publish — the service call sends the CAN command directly.
  // Publishing the topic AND calling the service causes a duplicate CAN command which can
  // interfere with motor_control's motion tracking.
  // Exception: In simulation mode, always publish — there is no service call to send the
  // command, so the topic is the only path to motor_control's physics simulator.
  if (position_wait_mode_ != "service" || !wait || yanthra_move::simulation_mode.load()) {
    // Publish the command (works for both simulation and hardware)
    std_msgs::msg::Float64 cmd_msg;
    cmd_msg.data = value;
    publisher->publish(cmd_msg);
  }

  if (yanthra_move::simulation_mode.load()) {
    RCLCPP_INFO(node_->get_logger(), "SIMULATION: Joint %s -> %.6f (published to /%s_cmd)",
        joint_name_.c_str(), value, joint_name_.c_str());
    current_position_.store(value, std::memory_order_relaxed);
    return MoveResult::SUCCESS;
  }

  RCLCPP_DEBUG(node_->get_logger(), "Joint %s commanded to position: %.6f",
      joint_name_.c_str(), value);

  // If no wait requested, command sent — return SUCCESS immediately (fire-and-forget)
  if (!wait) {
    return MoveResult::SUCCESS;
  }

  // Helper: blind sleep fallback — distance-based sleep estimate
  // Returns SUCCESS because we have no feedback to detect failure
  auto do_blind_sleep = [&]() -> MoveResult {
    double distance = std::abs(value - current_position_.load(std::memory_order_relaxed));
    double estimated_time = (distance / 0.3) + 1.0;  // seconds
    double wait_time = std::min(estimated_time, 3.0);  // Cap at 3 seconds

    RCLCPP_DEBUG(node_->get_logger(), "   [%s] Blind sleep %.1fs (distance=%.4f, target=%.4f)",
                joint_name_.c_str(), wait_time, distance, value);

    // BLOCKING_SLEEP_OK: main-thread blind-wait for motor travel; no position feedback available — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(wait_time * 1000)));

    // Update our internal estimate (actual position unknown without feedback)
    current_position_.store(value, std::memory_order_relaxed);
    return MoveResult::SUCCESS;
  };

  if (position_wait_mode_ == "service") {
    // ACTION MODE: Use JointPositionCommand action with feedback and cancellation.
    // motor_control handles all feedback internally using real CAN bus position data.
    // No echo problem — action blocks until motor actually reaches target.
    if (!joint_position_action_client) {
      RCLCPP_ERROR(node_->get_logger(),
          "   [%s] position_wait_mode=service but action client not initialized!",
          joint_name_.c_str());
      return MoveResult::ERROR;
    }

    int jid = getJointIdFromName();
    if (jid < 0) {
      RCLCPP_ERROR(node_->get_logger(),
          "   [%s] Cannot map joint name to ID for action call!",
          joint_name_.c_str());
      return MoveResult::ERROR;
    }

    // Wait for action server to be available
    if (!joint_position_action_client->wait_for_action_server(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node_->get_logger(),
          "   [%s] JointPositionCommand action server not available!",
          joint_name_.c_str());
      return MoveResult::ERROR;
    }

    // Build action goal
    auto goal_msg = motor_control_msgs::action::JointPositionCommand::Goal();
    goal_msg.joint_id = jid;
    goal_msg.target_position = value;
    goal_msg.max_velocity = 0.0;  // Use default velocity

    RCLCPP_INFO(node_->get_logger(),
        "   [%s] Action send_goal: target=%.4f (joint_id=%d, timeout=%.1fs)...",
        joint_name_.c_str(), value, jid, feedback_timeout_);

    auto send_goal_options = rclcpp_action::Client<motor_control_msgs::action::JointPositionCommand>::SendGoalOptions();

    struct FeedbackSnapshot {
      bool received{false};
      size_t samples{0};
      double current_position{0.0};
      double error_from_target{0.0};
      double elapsed_seconds{0.0};
      std::chrono::steady_clock::time_point last_update{};
    };

    auto last_feedback = std::make_shared<FeedbackSnapshot>();
    send_goal_options.feedback_callback =
        [this, last_feedback](
            auto,
            const std::shared_ptr<const motor_control_msgs::action::JointPositionCommand::Feedback> feedback) {
          if (!feedback) {
            return;
          }

          last_feedback->received = true;
          last_feedback->samples++;
          last_feedback->current_position = feedback->current_position;
          last_feedback->error_from_target = feedback->error_from_target;
          last_feedback->elapsed_seconds = feedback->elapsed_seconds;
          last_feedback->last_update = std::chrono::steady_clock::now();
          current_position_.store(feedback->current_position, std::memory_order_relaxed);
        };

    // Send goal and wait for result
    auto goal_handle_future = joint_position_action_client->async_send_goal(goal_msg, send_goal_options);

    auto start = std::chrono::steady_clock::now();
    double timeout_ms = feedback_timeout_ * 1000.0;

    // Wait for goal acceptance
    if (goal_handle_future.wait_for(std::chrono::seconds(5)) != std::future_status::ready) {
      RCLCPP_WARN(node_->get_logger(),
          "   [%s] Action goal acceptance timed out after 5s.",
          joint_name_.c_str());
      return MoveResult::TIMEOUT;
    }

    auto goal_handle = goal_handle_future.get();
    if (!goal_handle) {
      RCLCPP_WARN(node_->get_logger(),
          "   [%s] Action goal was REJECTED by server (joint_id=%d, target=%.4f).",
          joint_name_.c_str(), jid, value);
      return MoveResult::ERROR;
    }

    RCLCPP_INFO(node_->get_logger(),
        "   [%s] Action goal accepted: target=%.4f (joint_id=%d)",
        joint_name_.c_str(), value, jid);

    // Wait for result
    auto result_future = joint_position_action_client->async_get_result(goal_handle);

    bool got_result = false;
    while (rclcpp::ok()) {
      if (result_future.wait_for(std::chrono::milliseconds(50)) == std::future_status::ready) {
        got_result = true;
        break;
      }

      auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now() - start).count();
      if (elapsed >= static_cast<long>(timeout_ms)) {
        break;
      }
    }

    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - start).count();

    if (got_result) {
      auto wrapped_result = result_future.get();
      auto result = wrapped_result.result;
      current_position_.store(result->actual_position, std::memory_order_relaxed);
      const double feedback_age_ms = last_feedback->received
          ? std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - last_feedback->last_update).count()
          : -1.0;

      if (result->success) {
        RCLCPP_INFO(node_->get_logger(),
            "   [%s] Action confirmed: %s, actual=%.4f, target=%.4f, %ldms, feedback_samples=%zu, last_feedback_pos=%.4f, last_feedback_err=%.4f, last_feedback_age_ms=%.0f",
            joint_name_.c_str(), result->reason.c_str(),
            result->actual_position, value, elapsed_ms,
            last_feedback->samples, last_feedback->current_position,
            last_feedback->error_from_target, feedback_age_ms);
        return MoveResult::SUCCESS;
      } else {
        RCLCPP_WARN(node_->get_logger(),
            "   [%s] Action returned failure: %s, actual=%.4f, target=%.4f, %ldms, code=%d, feedback_samples=%zu, last_feedback_pos=%.4f, last_feedback_err=%.4f, last_feedback_age_ms=%.0f",
            joint_name_.c_str(), result->reason.c_str(),
            result->actual_position, value, elapsed_ms,
            static_cast<int>(wrapped_result.code), last_feedback->samples,
            last_feedback->current_position, last_feedback->error_from_target,
            feedback_age_ms);
        return MoveResult::ERROR;
      }
    } else {
      const double feedback_age_ms = last_feedback->received
          ? std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - last_feedback->last_update).count()
          : -1.0;
      const double cached_position = current_position_.load(std::memory_order_relaxed);
      RCLCPP_WARN(node_->get_logger(),
          "   [%s] Action result timed out after %ldms (timeout=%.1fs, joint_id=%d, target=%.4f). last_feedback_received=%s, feedback_samples=%zu, last_feedback_pos=%.4f, last_feedback_err=%.4f, last_feedback_elapsed=%.3fs, last_feedback_age_ms=%.0f, cached_position=%.4f. Motor may still be moving.",
          joint_name_.c_str(), elapsed_ms, feedback_timeout_, jid, value,
          last_feedback->received ? "true" : "false",
          last_feedback->samples, last_feedback->current_position,
          last_feedback->error_from_target, last_feedback->elapsed_seconds,
          feedback_age_ms, cached_position);
      // Cancel the goal since we're giving up
      joint_position_action_client->async_cancel_goal(goal_handle);
      RCLCPP_WARN(node_->get_logger(),
          "   [%s] Action cancel requested after client timeout (joint_id=%d, target=%.4f, cancel_requested=true).",
          joint_name_.c_str(), jid, value);
      return MoveResult::TIMEOUT;
    }
  } else if (position_wait_mode_ == "feedback") {
    // FEEDBACK MODE: poll current_position_ (from /joint_states) until within tolerance.
    // WARNING: This mode has a known echo bug — motor_control publishes commanded target
    // as position while motor is busy, causing false-arrival in 0-79ms.
    // Kept for future fixing. Use "service" mode instead.
    RCLCPP_INFO(node_->get_logger(),
        "   [%s] Waiting for position feedback (target=%.4f)...",
        joint_name_.c_str(), value);
    auto start = std::chrono::steady_clock::now();
    double timeout_ms = feedback_timeout_ * 1000.0;
    bool arrived = false;

    while (true) {
      // Executor thread processes subscription callbacks — no spin_some() needed
      double current = current_position_.load(std::memory_order_relaxed);
      double error = std::abs(current - value);
      if (error <= position_tolerance_) {
        arrived = true;
        break;
      }

      auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now() - start).count();
      if (elapsed >= timeout_ms) {
        break;
      }

      // BLOCKING_SLEEP_OK: main-thread position poll at 40Hz; executor on separate thread — reviewed 2026-03-14
      std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }

    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - start).count();
    double actual = current_position_.load(std::memory_order_relaxed);

    if (arrived) {
      double final_error = std::abs(actual - value);
      if (final_error > position_tolerance_ * 0.5) {
        RCLCPP_WARN(node_->get_logger(),
            "   [%s] Position reached but error is large: actual=%.4f, target=%.4f, error=%.4f (tol=%.4f), %ldms",
            joint_name_.c_str(), actual, value, final_error, position_tolerance_, elapsed_ms);
      } else {
        RCLCPP_INFO(node_->get_logger(),
            "   [%s] Position reached: actual=%.4f, target=%.4f, error=%.4f, %ldms",
            joint_name_.c_str(), actual, value, final_error, elapsed_ms);
      }
      return MoveResult::SUCCESS;
    } else {
      RCLCPP_WARN(node_->get_logger(),
          "   [%s] Feedback timeout after %ldms (target=%.4f, actual=%.4f, error=%.4f)",
          joint_name_.c_str(), elapsed_ms, value, actual, std::abs(actual - value));
      // DO NOT overwrite current_position_ with target — position is unknown on timeout
      return MoveResult::TIMEOUT;
    }
  } else {
    // BLIND SLEEP MODE (default fallback): distance-based sleep estimate
    return do_blind_sleep();
  }
}

// Static trajectory movement implementation
void joint_move::move_joint_trajectory(rclcpp::Node::SharedPtr node, int speed, double target_pos_3, double target_pos_4, double target_pos_5)
{
    if (!joint_pub_trajectory) {
        RCLCPP_ERROR(node->get_logger(), "Trajectory publisher not initialized");
        return;
    }

    // Check for simulation mode
    if (yanthra_move::simulation_mode.load()) {
        RCLCPP_INFO(node->get_logger(), "🤖 SIMULATION: Trajectory movement to positions: joint3=%.3f, joint4=%.3f, joint5=%.3f",
            target_pos_3, target_pos_4, target_pos_5);
        return;
    }

    trajectory_msgs::msg::JointTrajectory trajectory_msg;
    trajectory_msg.header.stamp = node->now();
    trajectory_msg.joint_names = {"joint3", "joint4", "joint5"};

    trajectory_msgs::msg::JointTrajectoryPoint point;
    point.positions = {target_pos_3, target_pos_4, target_pos_5};
    point.velocities = {0.0, 0.0, 0.0};
    point.accelerations = {0.0, 0.0, 0.0};

    // Calculate time based on speed parameter
    double time_from_start = 1.0 + (10.0 - speed) * 0.5;  // Speed 1-10, slower = more time
    point.time_from_start = rclcpp::Duration::from_seconds(time_from_start);

    trajectory_msg.points.push_back(point);
    joint_pub_trajectory->publish(trajectory_msg);

    RCLCPP_INFO(node->get_logger(), "🎯 Trajectory published for joints 3,4,5 with speed %d", speed);
}

// Static cleanup method implementation
void joint_move::cleanup_static_resources() {
    // Clean up static publishers
    joint2_cmd_pub_.reset();
    joint3_cmd_pub_.reset();
    joint4_cmd_pub_.reset();
    joint5_cmd_pub_.reset();

    // Clean up static clients
    joint_pub_trajectory.reset();
    joint_homing_action_client.reset();
    joint_idle_service.reset();
    joint_position_action_client.reset();
}
