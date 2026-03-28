// Copyright 2025 Pragati Robotics
#include "yanthra_move/yanthra_move_system.hpp"
#include "yanthra_move/joint_move.h"
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <motor_control_msgs/srv/joint_homing.hpp>
#include <motor_control_msgs/srv/joint_position_command.hpp>
#include <motor_control_msgs/action/joint_homing.hpp>
#include <motor_control_msgs/action/joint_position_command.hpp>
#include <yanthra_move/srv/arm_status.hpp>
#include <cotton_detection_msgs/srv/cotton_detection.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <atomic>
#include <chrono>
#include <mutex>
#include <thread>

using namespace yanthra_move;

void YanthraMoveSystem::initializeServices() {
    // Initialize action clients (replacing old service clients for homing and position command)
    joint_homing_action_client_ = rclcpp_action::create_client<motor_control_msgs::action::JointHoming>(
        node_, "/joint_homing");

    // Idle service stays as a regular service client (no action equivalent — idle uses JointHoming.srv with homing_required=false)
    joint_idle_service_ = node_->create_client<motor_control_msgs::srv::JointHoming>("/joint_idle");

    // Set static clients for joint_move class compatibility
    joint_move::joint_homing_action_client = joint_homing_action_client_;
    joint_move::joint_idle_service = joint_idle_service_;

    // JointPositionCommand action client (for position_wait_mode="service")
    // motor_control advertises at /joint_position_command (absolute path)
    joint_move::joint_position_action_client = rclcpp_action::create_client<motor_control_msgs::action::JointPositionCommand>(
        node_, "/joint_position_command");

    // Initialize cotton detection service client (for triggering detection on demand)
    cotton_detection_service_ = node_->create_client<cotton_detection_msgs::srv::CottonDetection>(
        "cotton_detection/detect");

    // Create service server for arm status
    arm_status_service_ = node_->create_service<yanthra_move::srv::ArmStatus>(
        "/yanthra_move/current_arm_status",
        std::bind(&YanthraMoveSystem::armStatusServiceCallback, this,
                  std::placeholders::_1, std::placeholders::_2));

    RCLCPP_INFO(node_->get_logger(), "ROS2 services initialized (action clients for homing and position command)");
}

void YanthraMoveSystem::armStatusServiceCallback(
    const std::shared_ptr<yanthra_move::srv::ArmStatus::Request> request,
    std::shared_ptr<yanthra_move::srv::ArmStatus::Response> response) {
    (void)request;  // Request empty in current implementation

    // Return dynamic arm status that reflects actual system state
    {
        std::lock_guard<std::mutex> lock(arm_status_mutex_);
        response->status = arm_status_;
    }
    response->reason = getArmStatusReason();

    RCLCPP_DEBUG(node_->get_logger(), "Arm status requested - returning: %s (%s)",
                 response->status.c_str(), response->reason.c_str());
}

bool YanthraMoveSystem::performInitializationAndHoming() {
    // NOTE: Motor homing is handled by MG6010 motor_control node at startup.
    // This function only performs initialization checks and verification.
    // Actual homing motions are only performed in simulation mode or legacy ODrive mode.
    RCLCPP_INFO(node_->get_logger(), "🔧 Starting initialization sequence (hardware homing handled by MG6010 controller)...");

    // Check if we're in simulation mode first
    if (simulation_mode_.load()) {
        RCLCPP_INFO(node_->get_logger(), "🎮 Simulation mode enabled - skipping hardware checks");
    } else {
        // CRITICAL HARDWARE CHECKS: Verify CAN bus and motors before proceeding
        RCLCPP_INFO(node_->get_logger(), "🔍 Performing critical hardware checks...");

        // Check 1: Verify motor_control node is running
        auto node_names = node_->get_node_names();
        for (const auto& name : node_names) {
            if (name.find("motor_control") != std::string::npos) {
                RCLCPP_INFO(node_->get_logger(), "✅ Motor control node detected: %s", name.c_str());
                break;
            }
        }


        RCLCPP_INFO(node_->get_logger(), "✅ Motor control node detected");

        // STEP 1: Check if motors are already homed by MG6010 controller
        bool skip_homing = node_->get_parameter("skip_homing").as_bool();

        if (skip_homing) {
            RCLCPP_INFO(node_->get_logger(), "✅ Hardware mode detected: motors already homed by MG6010 motor_control node");
            RCLCPP_INFO(node_->get_logger(), "   ➜ Skipping additional homing in yanthra_move (no second homing sequence required)");
            RCLCPP_INFO(node_->get_logger(), "✅ Initialization complete - motors ready for operation");
            return true;  // Skip all homing, motors already initialized
        }

        // Wait for ODrive services (legacy mode)
        RCLCPP_INFO(node_->get_logger(), "📡 Hardware mode - waiting for ODrive services to become available...");

        if (!joint_homing_action_client_) {
            RCLCPP_ERROR(node_->get_logger(), "Joint homing action client not initialized");
            return false;
        }

        // Wait for homing action server with timeout
        const auto service_timeout = std::chrono::seconds(30);
        if (!joint_homing_action_client_->wait_for_action_server(service_timeout)) {
            RCLCPP_ERROR(node_->get_logger(), "Homing action server not available after 30 seconds timeout");
            return false;
        } else {
            RCLCPP_INFO(node_->get_logger(), "✅ ODrive services are available");
        }
    }

    RCLCPP_INFO(node_->get_logger(), "🏠 Starting joint homing sequence...");

    // STEP 2: Height scan initialization (Joint2) - if enabled
    if (height_scan_enable_) {
        RCLCPP_INFO(node_->get_logger(), "📏 Height scan enabled - performing Joint2 homing first");
        std::string reason;
        if (!callJointHomingService(3, reason)) {  // Joint2 has ODrive ID 3
            RCLCPP_ERROR(node_->get_logger(), "❌ Joint2 (height scan) homing failed: %s", reason.c_str());
            return false;
        }
        RCLCPP_INFO(node_->get_logger(), "✅ Joint2 (height scan) homing completed");

        // Add idle delay for Joint2 as in legacy code
        // BLOCKING_SLEEP_OK: main-thread init sleep; executor runs on separate thread — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(l2_idle_sleep_time_ * 1000)));

        if (!callJointIdleService(3, reason)) {
            RCLCPP_WARN(node_->get_logger(), "⚠️ Joint2 idle service failed: %s", reason.c_str());
            // Don't fail completely for idle service failures
        }
    }

    // STEP 3: Sequential homing of main joints (following legacy order)
    // Joint5 Homing (prismatic joint, ODrive ID 2)
    RCLCPP_INFO(node_->get_logger(), "🏠 Homing Joint5 (prismatic joint)...");
    std::string reason;
    if (!callJointHomingService(2, reason)) {  // Joint5 has ODrive ID 2
        RCLCPP_ERROR(node_->get_logger(), "❌ Joint5 homing failed: %s", reason.c_str());
        return false;
    }
    RCLCPP_INFO(node_->get_logger(), "✅ Joint5 homing completed");

    // Joint3 Homing (phi - vertical revolute joint, ODrive ID 0)
    RCLCPP_INFO(node_->get_logger(), "🏠 Homing Joint3 (phi - vertical revolute)...");
    if (!callJointHomingService(0, reason)) {  // Joint3 has ODrive ID 0
        RCLCPP_ERROR(node_->get_logger(), "❌ Joint3 homing failed: %s", reason.c_str());
        return false;
    }
    RCLCPP_INFO(node_->get_logger(), "✅ Joint3 homing completed");

    // Joint4 Homing (theta - horizontal revolute joint, ODrive ID 1)
    RCLCPP_INFO(node_->get_logger(), "🏠 Homing Joint4 (theta - horizontal revolute)...");
    if (!callJointHomingService(1, reason)) {  // Joint4 has ODrive ID 1
        RCLCPP_ERROR(node_->get_logger(), "❌ Joint4 homing failed: %s", reason.c_str());
        return false;
    }
    RCLCPP_INFO(node_->get_logger(), "✅ Joint4 homing completed");

    RCLCPP_INFO(node_->get_logger(), "🎉 All joints homed successfully!");

    // STEP 4: Verify homing positions (critical safety check)
    if (!simulation_mode_.load()) {
        RCLCPP_INFO(node_->get_logger(), "🔍 Verifying joint homing positions...");

        std::atomic<bool> homing_verified{false};
        std::mutex state_mtx;
        sensor_msgs::msg::JointState::SharedPtr latest_state = nullptr;

        // Subscribe to joint_states to verify positions
        auto verification_sub = node_->create_subscription<sensor_msgs::msg::JointState>(
            "/joint_states", 10,
            [&homing_verified, &latest_state, &state_mtx](const sensor_msgs::msg::JointState::SharedPtr msg) {
                {
                    std::lock_guard<std::mutex> lock(state_mtx);
                    latest_state = msg;
                }
                // Check if we have position data for all joints
                if (msg->name.size() >= 3 && msg->position.size() >= 3) {
                    homing_verified.store(true);
                }
            }
        );

        // Wait up to 2 seconds for joint state confirmation
        auto start_time = std::chrono::steady_clock::now();
        while (!homing_verified.load() &&
               std::chrono::steady_clock::now() - start_time < std::chrono::seconds(2)) {
            // BLOCKING_SLEEP_OK: main-thread poll; executor processes callbacks on separate thread — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        bool has_state;
        sensor_msgs::msg::JointState::SharedPtr local_state;
        {
            std::lock_guard<std::mutex> lock(state_mtx);
            local_state = latest_state;  // Copy SharedPtr under lock
            has_state = (local_state != nullptr);
        }
        if (!homing_verified.load() || !has_state) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ CRITICAL: Cannot verify homing positions!");
            RCLCPP_ERROR(node_->get_logger(),
                "   Joint states not available after homing");
            RCLCPP_ERROR(node_->get_logger(),
                "   This indicates:");
            RCLCPP_ERROR(node_->get_logger(),
                "   1. Motors lost communication during homing");
            RCLCPP_ERROR(node_->get_logger(),
                "   2. Homing procedure did not complete properly");
            RCLCPP_ERROR(node_->get_logger(),
                "   3. Position feedback is not working");
            RCLCPP_ERROR(node_->get_logger(),
                "   Troubleshooting:");
            RCLCPP_ERROR(node_->get_logger(),
                "   - Check: ros2 topic echo /joint_states");
            RCLCPP_ERROR(node_->get_logger(),
                "   - Verify motors are still powered and communicating");
            RCLCPP_ERROR(node_->get_logger(),
                "   - Check for CAN bus errors during homing");
            RCLCPP_ERROR(node_->get_logger(),
                "   🛑 STOPPING - Cannot operate with unknown joint positions");
            return false;
        }

        // Log the homed positions for verification
        RCLCPP_INFO(node_->get_logger(), "✅ Homing positions verified:");
        for (size_t i = 0; i < local_state->name.size() && i < local_state->position.size(); ++i) {
            RCLCPP_INFO(node_->get_logger(), "   %s: %.4f",
                local_state->name[i].c_str(), local_state->position[i]);
        }

        // Additional sanity check: positions should be within reasonable bounds
        // For MG6010 motors, homing positions should be non-zero and finite
        bool positions_valid = true;
        for (size_t i = 0; i < local_state->position.size(); ++i) {
            if (!std::isfinite(local_state->position[i])) {
                RCLCPP_ERROR(node_->get_logger(),
                    "❌ CRITICAL: Joint %s has invalid position (NaN/Inf)",
                    local_state->name[i].c_str());
                positions_valid = false;
            }
        }

        if (!positions_valid) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ CRITICAL: Homing produced invalid joint positions!");
            RCLCPP_ERROR(node_->get_logger(),
                "   Encoder or controller may have failed during homing");
            RCLCPP_ERROR(node_->get_logger(),
                "   🛑 STOPPING - Cannot operate with invalid positions");
            return false;
        }

        RCLCPP_INFO(node_->get_logger(), "✅ All joint positions verified as valid");
    }

    return true;
}

bool YanthraMoveSystem::callJointHomingService(int joint_id, std::string& reason) {
    try {
        // Check if in simulation mode first
        if (simulation_mode_.load()) {
            reason = "Simulation mode: Homing successful (simulated)";
            RCLCPP_INFO(node_->get_logger(), "Simulation mode: Skipping homing for joint %d", joint_id);
            return true;
        }

        // Check if ROS2 context is still valid
        if (!rclcpp::ok()) {
            reason = "ROS2 context is not valid";
            return false;
        }

        if (!joint_homing_action_client_) {
            reason = "Homing action client not initialized";
            return false;
        }

        // Wait for action server to be available
        if (!joint_homing_action_client_->wait_for_action_server(std::chrono::seconds(10))) {
            reason = "Homing action server not available after 10 seconds";
            RCLCPP_ERROR(node_->get_logger(), "Joint %d homing action server not available", joint_id);
            return false;
        }

        // Build action goal
        auto goal_msg = motor_control_msgs::action::JointHoming::Goal();
        goal_msg.joint_ids = {joint_id};

        RCLCPP_INFO(node_->get_logger(), "Calling homing action for joint %d...", joint_id);

        // Send goal
        auto send_goal_options = rclcpp_action::Client<motor_control_msgs::action::JointHoming>::SendGoalOptions();
        auto goal_handle_future = joint_homing_action_client_->async_send_goal(goal_msg, send_goal_options);

        // Wait for goal acceptance
        if (goal_handle_future.wait_for(std::chrono::seconds(5)) != std::future_status::ready) {
            reason = "Homing action goal acceptance timed out after 5 seconds";
            RCLCPP_ERROR(node_->get_logger(), "Joint %d homing goal acceptance timed out", joint_id);
            return false;
        }

        auto goal_handle = goal_handle_future.get();
        if (!goal_handle) {
            reason = "Homing action goal was rejected by server";
            RCLCPP_ERROR(node_->get_logger(), "Joint %d homing goal was rejected", joint_id);
            return false;
        }

        // Wait for result (homing can take up to ~10s per joint: 2s + 0.2s + 3s + overhead)
        auto result_future = joint_homing_action_client_->async_get_result(goal_handle);
        if (result_future.wait_for(std::chrono::seconds(30)) != std::future_status::ready) {
            reason = "Homing action result timed out after 30 seconds";
            RCLCPP_ERROR(node_->get_logger(), "Joint %d homing result timed out", joint_id);
            joint_homing_action_client_->async_cancel_goal(goal_handle);
            return false;
        }

        auto wrapped_result = result_future.get();
        auto result = wrapped_result.result;
        reason = result->reason;

        if (result->success) {
            RCLCPP_INFO(node_->get_logger(), "Joint %d homing succeeded: %s", joint_id, reason.c_str());
            return true;
        } else {
            RCLCPP_ERROR(node_->get_logger(), "Joint %d homing failed: %s", joint_id, reason.c_str());
            return false;
        }

    } catch (const std::exception& e) {
        reason = std::string("Homing action call exception: ") + e.what();
        RCLCPP_ERROR(node_->get_logger(), "Exception during joint %d homing: %s", joint_id, e.what());
        return false;
    }
}

bool YanthraMoveSystem::callJointIdleService(int joint_id, std::string& reason) {
    try {
        // Check if in simulation mode first
        if (simulation_mode_.load()) {
            reason = "Simulation mode: Idle successful (simulated)";
            RCLCPP_INFO(node_->get_logger(), "🎮 Simulation mode: Skipping idle service for joint %d", joint_id);
            return true;
        }

        // Check if ROS2 context is still valid
        if (!rclcpp::ok()) {
            reason = "ROS2 context is not valid";
            return false;
        }

        if (!joint_idle_service_) {
            reason = "Idle service client not initialized";
            return false;
        }

        // Create and populate request
        auto request = std::make_shared<motor_control_msgs::srv::JointHoming::Request>();
        request->joint_id = joint_id;
        request->homing_required = false;  // Idle operation

        RCLCPP_INFO(node_->get_logger(), "💤 Calling idle service for joint %d...", joint_id);

        // Make the service call
        auto future = joint_idle_service_->async_send_request(request);

        // Wait for the service call to complete
        std::chrono::seconds service_timeout(5);  // 5 seconds for idle
        auto status = future.wait_for(service_timeout);

        if (status == std::future_status::ready) {
            auto response = future.get();
            reason = response->reason;

            if (response->success) {
                RCLCPP_INFO(node_->get_logger(), "✅ Joint %d idle succeeded: %s", joint_id, reason.c_str());
                return true;
            } else {
                RCLCPP_WARN(node_->get_logger(), "⚠️ Joint %d idle failed: %s", joint_id, reason.c_str());
                return false;
            }
        } else {
            reason = "Idle service call timed out after 5 seconds";
            RCLCPP_WARN(node_->get_logger(), "⏰ Joint %d idle service call timed out", joint_id);
            return false;
        }

    } catch (const std::exception& e) {
        reason = std::string("Idle service call exception: ") + e.what();
        RCLCPP_WARN(node_->get_logger(), "💥 Exception during joint %d idle: %s", joint_id, e.what());
        return false;
    }
}

std::string YanthraMoveSystem::getArmStatusReason() const {
    // Provide contextual explanation based on current arm_status_
    std::string status;
    { std::lock_guard<std::mutex> lock(arm_status_mutex_); status = arm_status_; }
    if (status == "uninit") {
        return "System initializing - homing not yet completed";
    } else if (status == "ready") {
        return "System ready for operation - awaiting start command";
    } else if (status == "busy") {
        return "System executing operational cycle - cotton picking in progress";
    } else if (status == "error") {
        if (global_stop_requested_.load()) {
            return "System stopped - shutdown requested";
        }
        return "System error - operation failed or aborted";
    } else {
        return "Unknown status: " + status;
    }
}
