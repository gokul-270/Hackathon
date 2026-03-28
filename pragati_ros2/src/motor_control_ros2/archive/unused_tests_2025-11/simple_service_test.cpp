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
#include <motor_control_ros2/srv/motor_calibration.hpp>

class SimpleServiceTest : public rclcpp::Node
{
public:
    SimpleServiceTest() : Node("simple_service_test")
    {
        RCLCPP_INFO(this->get_logger(), "SimpleServiceTest starting...");


        // Try to create just one service
        try {
            auto service = this->create_service<motor_control_ros2::srv::MotorCalibration>(
                "/test_motor_calibration",
                [this](const std::shared_ptr<motor_control_ros2::srv::MotorCalibration::Request> request,
                      std::shared_ptr<motor_control_ros2::srv::MotorCalibration::Response> response) {
                    (void)request;  // Mark as intentionally unused
                    // Simple response - just set success and default time
                    response->success = true;
                    response->calibration_time = 5.0;
                });

            RCLCPP_INFO(this->get_logger(), "Motor calibration service created successfully!");
        } catch (const std::exception& e) {
            RCLCPP_ERROR(this->get_logger(), "Failed to create service: %s", e.what());
        }

        RCLCPP_INFO(this->get_logger(), "SimpleServiceTest initialized");
    }
};

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<SimpleServiceTest>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
