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
#include <std_srvs/srv/empty.hpp>

class BasicServiceTest : public rclcpp::Node
{
public:
    BasicServiceTest() : Node("basic_service_test")
    {
        RCLCPP_INFO(this->get_logger(), "Basic Service Test Node starting...");


        // Create a simple empty service using standard ROS2 service
        service_ = this->create_service<std_srvs::srv::Empty>(
            "/test_empty_service",
            std::bind(&BasicServiceTest::handle_empty_service, this,
                     std::placeholders::_1, std::placeholders::_2));

        RCLCPP_INFO(this->get_logger(), "Empty service created at /test_empty_service");
        RCLCPP_INFO(this->get_logger(), "Basic Service Test Node spinning...");
    }

private:
    void handle_empty_service(
        const std::shared_ptr<std_srvs::srv::Empty::Request>,
        std::shared_ptr<std_srvs::srv::Empty::Response>)
    {
        RCLCPP_INFO(this->get_logger(), "Empty service called successfully!");
    }


    rclcpp::Service<std_srvs::srv::Empty>::SharedPtr service_;
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<BasicServiceTest>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
