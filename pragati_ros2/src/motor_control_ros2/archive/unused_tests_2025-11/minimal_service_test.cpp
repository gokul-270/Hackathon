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

#include <rclcpp/rclcpp.hpp>
#include <motor_control_ros2/srv/joint_homing.hpp>
#include <motor_control_ros2/srv/motor_calibration.hpp>

class MinimalServiceTest : public rclcpp::Node
{
public:
    MinimalServiceTest() : Node("minimal_service_test")
    {
        RCLCPP_INFO(this->get_logger(), "Minimal Service Test starting...");


        // Create basic service
        joint_homing_service_ = this->create_service<motor_control_ros2::srv::JointHoming>(
            "/joint_homing",
            std::bind(&MinimalServiceTest::handle_joint_homing, this,
                     std::placeholders::_1, std::placeholders::_2));

        // Try to create motor calibration service
        try {
            motor_calibration_service_ = this->create_service<motor_control_ros2::srv::MotorCalibration>(
                "/motor_calibration",
                std::bind(&MinimalServiceTest::handle_motor_calibration, this,
                         std::placeholders::_1, std::placeholders::_2));
            RCLCPP_INFO(this->get_logger(), "Motor calibration service created successfully");
        } catch (const std::exception& e) {
            RCLCPP_ERROR(this->get_logger(), "Failed to create motor calibration service: %s", e.what());
        }

        RCLCPP_INFO(this->get_logger(), "Minimal Service Test initialized");
    }

private:
    void handle_joint_homing(
        const std::shared_ptr<motor_control_ros2::srv::JointHoming::Request> request,
        std::shared_ptr<motor_control_ros2::srv::JointHoming::Response> response)
    {
        response->success = true;
        response->reason = "Basic homing test";
        RCLCPP_INFO(this->get_logger(), "Joint homing called for joint %d", request->joint_id);
    }


    void handle_motor_calibration(
        const std::shared_ptr<motor_control_ros2::srv::MotorCalibration::Request> request,
        std::shared_ptr<motor_control_ros2::srv::MotorCalibration::Response> response)
    {
        response->success = true;
        response->reason = "Motor calibration test";
        response->calibration_time = 1.0;
        RCLCPP_INFO(this->get_logger(), "Motor calibration called for joint %ld", request->joint_id);
    }


    rclcpp::Service<motor_control_ros2::srv::JointHoming>::SharedPtr joint_homing_service_;
    rclcpp::Service<motor_control_ros2::srv::MotorCalibration>::SharedPtr motor_calibration_service_;
};

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<MinimalServiceTest>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
