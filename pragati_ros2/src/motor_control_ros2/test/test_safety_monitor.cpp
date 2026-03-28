/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 * Test program for SafetyMonitor implementation
 */

#include <memory>
#include <chrono>
#include <thread>
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "motor_control_ros2/safety_monitor.hpp"

using namespace std::chrono_literals;

class SafetyMonitorTestNode : public rclcpp::Node
{
public:
    SafetyMonitorTestNode() : Node("safety_monitor_test")
    {
        RCLCPP_INFO(this->get_logger(), "=== SafetyMonitor Test Program ===");

        // Create SafetyMonitor
        safety_monitor_ = std::make_shared<motor_control_ros2::SafetyMonitor>(
            this->get_node_base_interface(),
            this->get_node_logging_interface(),
            this->get_node_parameters_interface(),
            this->get_node_topics_interface(),
            this->get_node_services_interface()
        );

        // With fail-safe defaults, new monitor starts in UNKNOWN (is_safe() == false).
        // activate() transitions to INITIALIZING, then update() with safe data -> SAFE.
        safety_monitor_->activate();

        RCLCPP_INFO(this->get_logger(), "SafetyMonitor created and activated (state: INITIALIZING)");
    }

    void run_tests()
    {
        RCLCPP_INFO(this->get_logger(), "\n=== Running Safety Monitor Tests ===\n");

        // Test 1: Normal operation (should pass)
        test_normal_operation();

        // Test 2: Position limit violation (should trigger E-stop)
        test_position_limit();

        // Test 3: Velocity limit violation (should trigger E-stop)
        test_velocity_limit();

        // Test 4: Temperature warning and critical (should warn then stop)
        test_temperature_limits();

        // Test 5: Low voltage warning and critical
        test_voltage_limits();

        // Test 6: Motor error detection
        test_motor_errors();

        // Test 7: Communication timeout
        test_communication_timeout();

        RCLCPP_INFO(this->get_logger(), "\n=== All Tests Complete ===");
    }

private:
    std::shared_ptr<motor_control_ros2::SafetyMonitor> safety_monitor_;

    // Helper: reset safety monitor and transition to SAFE state with baseline data.
    // With the fail-safe state machine, deactivate()→activate() puts the monitor into
    // INITIALIZING. We must feed safe data and call update() to reach SAFE before
    // running the actual test scenario.
    void reset_to_safe_state()
    {
        safety_monitor_->deactivate();
        safety_monitor_->activate();

        // Feed baseline safe data to pass all safety checks
        auto msg = std::make_shared<sensor_msgs::msg::JointState>();
        msg->name = {"joint2", "joint3", "joint4", "joint5"};
        msg->position = {0.0, 0.0, 0.0, 0.0};
        msg->velocity = {0.0, 0.0, 0.0, 0.0};
        msg->effort = {0.0, 0.0, 0.0, 0.0};

        safety_monitor_->update_joint_states(msg);
        safety_monitor_->update_motor_temperature("joint2", 30.0);
        safety_monitor_->update_motor_temperature("joint3", 30.0);
        safety_monitor_->update_motor_temperature("joint4", 30.0);
        safety_monitor_->update_motor_temperature("joint5", 30.0);
        safety_monitor_->update_vbus_voltage(48.0);
        safety_monitor_->update_motor_errors("joint2", 0);
        safety_monitor_->update_motor_errors("joint3", 0);
        safety_monitor_->update_motor_errors("joint4", 0);
        safety_monitor_->update_motor_errors("joint5", 0);

        // This update transitions INITIALIZING → SAFE
        safety_monitor_->update();
    }

    void test_normal_operation()
    {
        RCLCPP_INFO(this->get_logger(), "Test 1: Normal Operation");

        // Simulate normal joint states — first update transitions INITIALIZING -> SAFE
        auto msg = std::make_shared<sensor_msgs::msg::JointState>();
        msg->name = {"joint2", "joint3", "joint4", "joint5"};
        msg->position = {0.5, 0.3, -0.2, 1.0};  // Safe positions
        msg->velocity = {0.5, 0.3, 0.2, 0.1};   // Safe velocities
        msg->effort = {1.0, 1.0, 1.0, 1.0};

        safety_monitor_->update_joint_states(msg);
        safety_monitor_->update_motor_temperature("joint2", 50.0);  // Safe temp
        safety_monitor_->update_vbus_voltage(48.0);  // Normal voltage
        safety_monitor_->update_motor_errors("joint2", 0);  // No errors

        safety_monitor_->update();

        if (safety_monitor_->is_safe()) {
            RCLCPP_INFO(this->get_logger(), "  PASS: System is safe with normal parameters");
        } else {
            RCLCPP_ERROR(this->get_logger(), "  FAIL: System should be safe!");
        }

        std::this_thread::sleep_for(500ms);
    }

    void test_position_limit()
    {
        RCLCPP_INFO(this->get_logger(), "\nTest 2: Position Limit Violation");

        // Reset to clean SAFE state (fail-safe: need full init cycle)
        reset_to_safe_state();

        auto msg = std::make_shared<sensor_msgs::msg::JointState>();
        msg->name = {"joint2", "joint3", "joint4", "joint5"};
        msg->position = {1.55, 0.3, -0.2, 1.0};  // Joint2 near +90 limit (1.57)
        msg->velocity = {0.1, 0.1, 0.1, 0.1};
        msg->effort = {1.0, 1.0, 1.0, 1.0};

        safety_monitor_->update_joint_states(msg);
        safety_monitor_->update();

        if (!safety_monitor_->is_safe()) {
            RCLCPP_INFO(this->get_logger(), "  PASS: Position limit violation detected");
        } else {
            RCLCPP_WARN(this->get_logger(), "  WARNING: Position limit should have triggered E-stop");
        }

        std::this_thread::sleep_for(500ms);
    }

    void test_velocity_limit()
    {
        RCLCPP_INFO(this->get_logger(), "\nTest 3: Velocity Limit Violation");

        // Reset to clean SAFE state
        reset_to_safe_state();

        auto msg = std::make_shared<sensor_msgs::msg::JointState>();
        msg->name = {"joint2", "joint3", "joint4", "joint5"};
        msg->position = {0.5, 0.3, -0.2, 1.0};
        msg->velocity = {15.0, 0.1, 0.1, 0.1};  // Exceeds 10 rad/s limit
        msg->effort = {1.0, 1.0, 1.0, 1.0};

        safety_monitor_->update_joint_states(msg);
        safety_monitor_->update();

        if (!safety_monitor_->is_safe()) {
            RCLCPP_INFO(this->get_logger(), "  PASS: Velocity limit violation detected");
        } else {
            RCLCPP_WARN(this->get_logger(), "  WARNING: Velocity limit should have triggered E-stop");
        }

        std::this_thread::sleep_for(500ms);
    }

    void test_temperature_limits()
    {
        RCLCPP_INFO(this->get_logger(), "\nTest 4: Temperature Limits");

        // Reset to clean SAFE state
        reset_to_safe_state();

        // Test warning temperature (should continue in WARNING state)
        safety_monitor_->update_motor_temperature("joint2", 67.0);  // Warning level
        safety_monitor_->update();

        RCLCPP_INFO(this->get_logger(), "  Temperature warning (67C) should be logged above");

        // Test critical temperature (should stop)
        safety_monitor_->update_motor_temperature("joint2", 72.0);  // Critical
        safety_monitor_->update();

        if (!safety_monitor_->is_safe()) {
            RCLCPP_INFO(this->get_logger(), "  PASS: Critical temperature detected");
        } else {
            RCLCPP_WARN(this->get_logger(), "  WARNING: Critical temp should have triggered E-stop");
        }

        std::this_thread::sleep_for(500ms);
    }

    void test_voltage_limits()
    {
        RCLCPP_INFO(this->get_logger(), "\nTest 5: Voltage Limits");

        // Reset to clean SAFE state
        reset_to_safe_state();

        // Test warning voltage
        safety_monitor_->update_vbus_voltage(41.0);  // Warning level
        safety_monitor_->update();
        RCLCPP_INFO(this->get_logger(), "  Low voltage warning (41V) should be logged above");

        // Test critical voltage
        safety_monitor_->update_vbus_voltage(38.0);  // Critical
        safety_monitor_->update();

        if (!safety_monitor_->is_safe()) {
            RCLCPP_INFO(this->get_logger(), "  PASS: Critical voltage detected");
        } else {
            RCLCPP_WARN(this->get_logger(), "  WARNING: Critical voltage should have triggered E-stop");
        }

        std::this_thread::sleep_for(500ms);
    }

    void test_motor_errors()
    {
        RCLCPP_INFO(this->get_logger(), "\nTest 6: Motor Error Detection");

        // Reset to clean SAFE state
        reset_to_safe_state();

        // Simulate critical motor error (DRV_FAULT = 0x0020)
        safety_monitor_->update_motor_errors("joint2", 0x0020);
        safety_monitor_->update();

        if (!safety_monitor_->is_safe()) {
            RCLCPP_INFO(this->get_logger(), "  PASS: Motor error detected");
        } else {
            RCLCPP_WARN(this->get_logger(), "  WARNING: Motor error should have triggered E-stop");
        }

        std::this_thread::sleep_for(500ms);
    }

    void test_communication_timeout()
    {
        RCLCPP_INFO(this->get_logger(), "\nTest 7: Communication Timeout");

        // Reset to clean SAFE state
        reset_to_safe_state();

        RCLCPP_INFO(this->get_logger(), "  Waiting 1.5 seconds to simulate timeout...");
        std::this_thread::sleep_for(1500ms);

        // Update without new data (should detect timeout)
        safety_monitor_->update();

        if (!safety_monitor_->is_safe()) {
            RCLCPP_INFO(this->get_logger(), "  PASS: Communication timeout detected");
        } else {
            RCLCPP_WARN(this->get_logger(), "  WARNING: Timeout should have been detected");
        }
    }
};

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);

    auto test_node = std::make_shared<SafetyMonitorTestNode>();
    test_node->run_tests();

    rclcpp::shutdown();
    return 0;
}
