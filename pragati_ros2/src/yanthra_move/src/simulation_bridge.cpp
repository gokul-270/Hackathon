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
 * @file simulation_bridge.cpp
 * @brief Bridge between yanthra_move joint commands and Gazebo simulation
 * 
 * This node subscribes to individual joint position commands from yanthra_move
 * and publishes them to the joint_trajectory_controller for Gazebo simulation.
 * 
 * Topology:
 *   yanthra_move → /joint2_position_controller/command (Float64)
 *                → /joint3_position_controller/command (Float64)
 *                → /joint4_position_controller/command (Float64)
 *                → /joint5_position_controller/command (Float64)
 *   
 *   simulation_bridge → /joint_trajectory_controller/follow_joint_trajectory (Action)
 *                     → /joint_states (feedback)
 */

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/float64.hpp>
#include <control_msgs/action/follow_joint_trajectory.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <map>
#include <mutex>
#include <chrono>

using namespace std::chrono_literals;
using FollowJointTrajectory = control_msgs::action::FollowJointTrajectory;
using GoalHandleFollowJointTrajectory = rclcpp_action::ClientGoalHandle<FollowJointTrajectory>;

class SimulationBridge : public rclcpp::Node
{
public:
    SimulationBridge() : Node("simulation_bridge")
    {
        RCLCPP_INFO(this->get_logger(), "🤖 Simulation Bridge starting...");

        // Create action client for joint trajectory controller
        trajectory_action_client_ = rclcpp_action::create_client<FollowJointTrajectory>(
            this, "/joint_trajectory_controller/follow_joint_trajectory");

        // Subscribe to individual joint commands from yanthra_move
        joint2_sub_ = this->create_subscription<std_msgs::msg::Float64>(
            "/joint2_position_controller/command", 10,
            std::bind(&SimulationBridge::joint2Callback, this, std::placeholders::_1));

        joint3_sub_ = this->create_subscription<std_msgs::msg::Float64>(
            "/joint3_position_controller/command", 10,
            std::bind(&SimulationBridge::joint3Callback, this, std::placeholders::_1));

        joint4_sub_ = this->create_subscription<std_msgs::msg::Float64>(
            "/joint4_position_controller/command", 10,
            std::bind(&SimulationBridge::joint4Callback, this, std::placeholders::_1));

        joint5_sub_ = this->create_subscription<std_msgs::msg::Float64>(
            "/joint5_position_controller/command", 10,
            std::bind(&SimulationBridge::joint5Callback, this, std::placeholders::_1));

        // Subscribe to joint states for feedback
        joint_states_sub_ = this->create_subscription<sensor_msgs::msg::JointState>(
            "/joint_states", 10,
            std::bind(&SimulationBridge::jointStatesCallback, this, std::placeholders::_1));

        // Timer to send periodic updates
        update_timer_ = this->create_wall_timer(
            100ms, std::bind(&SimulationBridge::updateTimerCallback, this));

        RCLCPP_INFO(this->get_logger(), "✅ Simulation Bridge ready");
        RCLCPP_INFO(this->get_logger(), "   Waiting for /joint_trajectory_controller/follow_joint_trajectory...");
    }

private:
    void joint2Callback(const std_msgs::msg::Float64::SharedPtr msg)
    {
        std::lock_guard<std::mutex> lock(joint_positions_mutex_);
        target_positions_["joint2"] = msg->data;
        command_updated_ = true;
        RCLCPP_DEBUG(this->get_logger(), "Joint 2 target: %.3f", msg->data);
    }

    void joint3Callback(const std_msgs::msg::Float64::SharedPtr msg)
    {
        std::lock_guard<std::mutex> lock(joint_positions_mutex_);
        target_positions_["joint3"] = msg->data;
        command_updated_ = true;
        RCLCPP_DEBUG(this->get_logger(), "Joint 3 target: %.3f", msg->data);
    }

    void joint4Callback(const std_msgs::msg::Float64::SharedPtr msg)
    {
        std::lock_guard<std::mutex> lock(joint_positions_mutex_);
        target_positions_["joint4"] = msg->data;
        command_updated_ = true;
        RCLCPP_DEBUG(this->get_logger(), "Joint 4 target: %.3f", msg->data);
    }

    void joint5Callback(const std_msgs::msg::Float64::SharedPtr msg)
    {
        std::lock_guard<std::mutex> lock(joint_positions_mutex_);
        target_positions_["joint5"] = msg->data;
        command_updated_ = true;
        RCLCPP_DEBUG(this->get_logger(), "Joint 5 target: %.3f", msg->data);
    }

    void joint7Callback(const std_msgs::msg::Float64::SharedPtr msg)
    {
        std::lock_guard<std::mutex> lock(joint_positions_mutex_);
        target_positions_["joint7"] = msg->data;
        command_updated_ = true;
        RCLCPP_DEBUG(this->get_logger(), "Joint 7 target: %.3f", msg->data);
    }

    void jointStatesCallback(const sensor_msgs::msg::JointState::SharedPtr msg)
    {
        std::lock_guard<std::mutex> lock(joint_positions_mutex_);
        for (size_t i = 0; i < msg->name.size() && i < msg->position.size(); ++i) {
            current_positions_[msg->name[i]] = msg->position[i];
        }
    }

    void updateTimerCallback()
    {
        std::lock_guard<std::mutex> lock(joint_positions_mutex_);

        // Only send if we have updates and action server is available
        if (!command_updated_) {
            return;
        }

        if (!trajectory_action_client_->wait_for_action_server(std::chrono::milliseconds(100))) {
            RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                               "⏳ Waiting for joint_trajectory_controller action server...");
            return;
        }

        // Build trajectory goal
        auto goal_msg = FollowJointTrajectory::Goal();
        goal_msg.trajectory.header.stamp = this->now();

        // Joint names matching Gazebo simulation
        goal_msg.trajectory.joint_names = {"joint2", "joint3", "joint4", "joint5", "joint7"};

        // Create trajectory point with current targets
        trajectory_msgs::msg::JointTrajectoryPoint point;
        
        // Get positions for each joint (use current if no target set)
        for (const auto& joint_name : goal_msg.trajectory.joint_names) {
            double position = 0.0;
            if (target_positions_.find(joint_name) != target_positions_.end()) {
                position = target_positions_[joint_name];
            } else if (current_positions_.find(joint_name) != current_positions_.end()) {
                position = current_positions_[joint_name];
            }
            point.positions.push_back(position);
        }

        // Set execution time (faster for responsive simulation)
        point.time_from_start = rclcpp::Duration::from_seconds(0.5);
        
        goal_msg.trajectory.points.push_back(point);

        // Send goal
        auto send_goal_options = rclcpp_action::Client<FollowJointTrajectory>::SendGoalOptions();
        
        send_goal_options.result_callback =
            [this](const GoalHandleFollowJointTrajectory::WrappedResult & result) {
                switch (result.code) {
                    case rclcpp_action::ResultCode::SUCCEEDED:
                        RCLCPP_DEBUG(this->get_logger(), "✅ Trajectory execution succeeded");
                        break;
                    case rclcpp_action::ResultCode::ABORTED:
                        RCLCPP_WARN(this->get_logger(), "❌ Trajectory execution aborted");
                        break;
                    case rclcpp_action::ResultCode::CANCELED:
                        RCLCPP_WARN(this->get_logger(), "⚠️ Trajectory execution canceled");
                        break;
                    default:
                        RCLCPP_ERROR(this->get_logger(), "❓ Unknown result code");
                        break;
                }
            };

        trajectory_action_client_->async_send_goal(goal_msg, send_goal_options);
        
        RCLCPP_DEBUG(this->get_logger(), "🎯 Sent trajectory: J2=%.3f, J3=%.3f, J4=%.3f, J5=%.3f",
                    point.positions[0], point.positions[1], point.positions[2], point.positions[3]);

        command_updated_ = false;
    }

    // Subscriptions
    rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr joint2_sub_;
    rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr joint3_sub_;
    rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr joint4_sub_;
    rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr joint5_sub_;
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_states_sub_;

    // Action client
    rclcpp_action::Client<FollowJointTrajectory>::SharedPtr trajectory_action_client_;

    // Timer
    rclcpp::TimerBase::SharedPtr update_timer_;

    // State tracking
    std::map<std::string, double> target_positions_;
    std::map<std::string, double> current_positions_;
    std::mutex joint_positions_mutex_;
    bool command_updated_{false};
};

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<SimulationBridge>();
    
    RCLCPP_INFO(node->get_logger(), "🚀 Simulation Bridge node running...");
    
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
