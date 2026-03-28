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
#include "motor_control_ros2/srv/motor_calibration.hpp"
#include <memory>

class SimpleServiceTest : public rclcpp::Node
{
public:
    SimpleServiceTest() : Node("simple_service_test")
    {
        RCLCPP_INFO(this->get_logger(), "Simple Service Test Node starting...");


        // Create a very basic motor calibration service
        service_ = this->create_service<motor_control_ros2::srv::MotorCalibration>(
            "test_motor_calibration",
            std::bind(&SimpleServiceTest::handle_service, this,
                     std::placeholders::_1, std::placeholders::_2));

        RCLCPP_INFO(this->get_logger(), "Test motor calibration service created");
        RCLCPP_INFO(this->get_logger(), "Test node ready for service calls");
    }

private:
    void handle_service(
        const std::shared_ptr<motor_control_ros2::srv::MotorCalibration::Request> request,
        std::shared_ptr<motor_control_ros2::srv::MotorCalibration::Response> response)
    {
        RCLCPP_INFO(this->get_logger(), "Received motor calibration request for joint %ld", request->joint_id);


        // Simple response
        response->success = true;
        response->reason = "Test calibration completed";
        response->calibration_time = 1.5;

        RCLCPP_INFO(this->get_logger(), "Sent motor calibration response");
    }

    rclcpp::Service<motor_control_ros2::srv::MotorCalibration>::SharedPtr service_;
};

int main(int argc, char * argv[])
{
    rclcpp::init(argc, argv);


    auto node = std::make_shared<SimpleServiceTest>();

    RCLCPP_INFO(node->get_logger(), "Simple Service Test Node spinning...");
    rclcpp::spin(node);

    rclcpp::shutdown();
    return 0;
}
