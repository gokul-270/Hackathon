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
 * @file yanthra_move_system_error_recovery.cpp
 * @brief Error recovery and resilience methods for YanthraMoveSystem
 *
 * This file contains error handling, recovery, and safe mode operations.
 * Note: Template method retryWithBackoff() remains in core file (C++ requirement).
 */

#include "yanthra_move/yanthra_move_system.hpp"
#include "yanthra_move/core/motion_controller.hpp"

#include <future>  // std::async for homing timeout

extern std::atomic<bool> global_stop_requested;

namespace yanthra_move {

// Helper: return string name for FailureType (for logging)
static const char* failureTypeName(FailureType type) {
    switch (type) {
        case FailureType::MOTOR_TIMEOUT:         return "MOTOR_TIMEOUT";
        case FailureType::MOTOR_ERROR:            return "MOTOR_ERROR";
        case FailureType::DETECTION_UNAVAILABLE:  return "DETECTION_UNAVAILABLE";
        case FailureType::PICK_TIMEOUT:           return "PICK_TIMEOUT";
        default:                                  return "UNKNOWN";
    }
}

// Template implementation for retry with backoff
// NOTE: Template methods must be defined in same translation unit where instantiated
template<typename Func>
bool YanthraMoveSystem::retryWithBackoff(Func operation, const std::string& operation_name,
                                        int max_retries, double base_delay) {
    for (int attempt = 1; attempt <= max_retries; ++attempt) {
        RCLCPP_INFO(node_->get_logger(), "%s attempt %d/%d", operation_name.c_str(), attempt, max_retries);

        try {
            if (operation()) {
                RCLCPP_INFO(node_->get_logger(), "%s successful on attempt %d", operation_name.c_str(), attempt);
                return true;
            }
        } catch (const std::exception& e) {
            RCLCPP_WARN(node_->get_logger(), "%s attempt %d failed: %s", operation_name.c_str(), attempt, e.what());
        }

        if (attempt < max_retries) {
            double delay = base_delay * std::pow(2, attempt - 1);  // Exponential backoff
            RCLCPP_INFO(node_->get_logger(), "Waiting %.1f seconds before retry...", delay);
            // BLOCKING_SLEEP_OK: main-thread exponential backoff in retry loop — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::duration<double>(delay));
        }
    }

    RCLCPP_ERROR(node_->get_logger(), "%s failed after %d attempts", operation_name.c_str(), max_retries);
    return false;
}

void YanthraMoveSystem::initializeErrorRecovery() {
    try {
        RCLCPP_INFO(node_->get_logger(), "Initializing error recovery and resilience systems...");

        // Reset error recovery state
        error_recovery_state_.recovery_active.store(false);
        error_recovery_state_.safe_mode_active.store(false);
        error_recovery_state_.degraded_mode_active.store(false);
        error_recovery_state_.consecutive_failures.store(0);
        error_recovery_state_.total_recoveries.store(0);
        {
            // last_error_time and disabled_components are non-atomic — must hold state_mutex
            std::lock_guard<std::mutex> lock(error_recovery_state_.state_mutex);
            error_recovery_state_.last_error_time = std::chrono::steady_clock::now();
            error_recovery_state_.disabled_components.clear();
        }

        RCLCPP_INFO(node_->get_logger(), "Error recovery systems initialized successfully");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to initialize error recovery: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::handleOperationalFailure(FailureType type, const FailureContext& context) {
    // Structured JSON log for the failure event (task 2.6)
    RCLCPP_WARN(node_->get_logger(),
        "{\"event\":\"operational_failure\","
        "\"failure_type\":\"%s\","
        "\"joint_id\":%d,"
        "\"target_position\":%.4f,"
        "\"cycle_count\":%d,"
        "\"phase\":\"%s\"}",
        failureTypeName(type), context.joint_id, context.target_position,
        context.cycle_count, context.phase.c_str());

    // DETECTION_UNAVAILABLE is non-motor: skip cycle, do NOT escalate to safe mode immediately
    if (type == FailureType::DETECTION_UNAVAILABLE) {
        RCLCPP_WARN(node_->get_logger(),
            "{\"event\":\"recovery_action\","
            "\"action\":\"pause_picking\","
            "\"reason\":\"detection_unavailable\"}");
        // Pick loop will skip this cycle; detection may recover on next heartbeat
        return;
    }

    // PICK_TIMEOUT: timeout during a pick cycle — not a motor failure.
    // Skip homing (motor may still be moving); let next cycle retry naturally.
    if (type == FailureType::PICK_TIMEOUT) {
        RCLCPP_WARN(node_->get_logger(),
            "{\"event\":\"recovery_action\","
            "\"action\":\"skip_homing_pick_timeout\","
            "\"reason\":\"pick_timeout_not_motor_failure\","
            "\"joint_id\":%d}", context.joint_id);
        return;
    }

    // Escalation ladder (D3):
    // Step 1: already logged above.
    // Step 2: The per-joint consecutive counter is maintained in MotionController::recordMoveResult().
    //         This function is only called when the threshold is already exceeded.
    // Step 3: Attempt homing before giving up
    RCLCPP_WARN(node_->get_logger(),
        "{\"event\":\"recovery_action\","
        "\"action\":\"attempt_homing\","
        "\"joint_id\":%d}", context.joint_id);

    if (motion_controller_) {
        bool homing_ok = retryWithBackoff(
            [this]() -> bool {
                return motion_controller_->moveToPackingPosition();
            },
            "homing_recovery",
            2,  // max retries
            static_cast<double>(retry_backoff_base_ms_) / 1000.0
        );

        if (homing_ok) {
            RCLCPP_WARN(node_->get_logger(),
                "{\"event\":\"recovery_action\","
                "\"action\":\"homing_succeeded\","
                "\"joint_id\":%d}", context.joint_id);
            // Reset global consecutive counter — joint-level counter stays in MotionController
            error_recovery_state_.consecutive_failures.store(0);
            // Reset per-joint consecutive failure counters (they were the trigger)
            if (motion_controller_) {
                motion_controller_->recordMoveResult(3, MoveResult::SUCCESS);
                motion_controller_->recordMoveResult(4, MoveResult::SUCCESS);
                motion_controller_->recordMoveResult(5, MoveResult::SUCCESS);
            }
            return;
        }
    }

    // Step 4: Homing failed or motion_controller unavailable — enter safe mode
    RCLCPP_ERROR(node_->get_logger(),
        "{\"event\":\"recovery_escalation\","
        "\"action\":\"entering_safe_mode\","
        "\"reason\":\"repeated_motor_failure\","
        "\"joint_id\":%d,"
        "\"failure_type\":\"%s\"}",
        context.joint_id, failureTypeName(type));

    enterSafeMode("repeated_motor_failure");
}

bool YanthraMoveSystem::handleHardwareError(const std::string& component, const std::string& error_msg) {
    std::lock_guard<std::mutex> lock(error_recovery_state_.state_mutex);

    RCLCPP_ERROR(node_->get_logger(), "Hardware error in %s: %s", component.c_str(), error_msg.c_str());

    error_recovery_state_.consecutive_failures.fetch_add(1);
    error_recovery_state_.last_error_time = std::chrono::steady_clock::now();

    // Check if we should enter safe mode due to too many failures
    if (error_recovery_state_.consecutive_failures.load() >= consecutive_failure_safe_mode_threshold_) {
        RCLCPP_ERROR(node_->get_logger(), "Too many consecutive hardware failures (%d), entering safe mode",
                    error_recovery_state_.consecutive_failures.load());
        enterSafeMode("consecutive_hardware_failures");
        return false;
    }

    // Attempt component-specific recovery
    if (component == "ODrive" || component == "joint_controller") {
        RCLCPP_WARN(node_->get_logger(), "Attempting ODrive recovery...");
        return retryWithBackoff([this]() -> bool {
            return resetSystemComponents();
        }, "ODrive_recovery");

    } else if (component == "GPIO" || component == "hardware_interface") {
        RCLCPP_WARN(node_->get_logger(), "Attempting GPIO recovery...");
        enableDegradedMode({"GPIO"});
        return true;

    } else if (component == "camera" || component == "vision") {
        RCLCPP_WARN(node_->get_logger(), "Camera error - enabling vision-free mode");
        enableDegradedMode({"camera", "vision"});
        return true;

    } else {
        RCLCPP_WARN(node_->get_logger(), "Unknown component %s - attempting general recovery", component.c_str());
        return attemptSystemRecovery("unknown_hardware_error");
    }
}

bool YanthraMoveSystem::handleCommunicationError(const std::string& service_name, const std::string& error_msg) {
    {
        std::lock_guard<std::mutex> lock(error_recovery_state_.state_mutex);
        RCLCPP_ERROR(node_->get_logger(), "Communication error with %s: %s", service_name.c_str(), error_msg.c_str());
        error_recovery_state_.consecutive_failures.fetch_add(1);
    }  // Release mutex before retryWithBackoff (which sleeps)

    // Retry communication with exponential backoff
    return retryWithBackoff([this, &service_name]() -> bool {
        if (service_name == "joint_homing" || service_name == "joint_idle") {
            if (!joint_homing_action_client_->wait_for_action_server(std::chrono::seconds(2))) {
                RCLCPP_WARN(node_->get_logger(), "ODrive homing action server not available");
                return false;
            }
            if (!joint_idle_service_->wait_for_service(std::chrono::seconds(2))) {
                RCLCPP_WARN(node_->get_logger(), "ODrive idle service not available");
                return false;
            }
            return true;
        }
        return true;
    }, "communication_recovery");
}

bool YanthraMoveSystem::attemptSystemRecovery(const std::string& failure_type) {
    bool expected = false;
    if (!error_recovery_state_.recovery_active.compare_exchange_strong(expected, true)) {
        RCLCPP_WARN(node_->get_logger(), "Recovery already in progress, skipping new recovery attempt");
        return false;
    }
    error_recovery_state_.total_recoveries.fetch_add(1);

    RCLCPP_INFO(node_->get_logger(), "Attempting system recovery for: %s (attempt #%d)",
                failure_type.c_str(), error_recovery_state_.total_recoveries.load());

    bool recovery_success = false;

    try {
        RCLCPP_INFO(node_->get_logger(), "Step 1: Performing health check...");
        if (!performHealthCheck()) {
            RCLCPP_WARN(node_->get_logger(), "Health check failed, attempting component reset");
        }

        RCLCPP_INFO(node_->get_logger(), "Step 2: Resetting system components...");
        if (resetSystemComponents()) {
            RCLCPP_INFO(node_->get_logger(), "Component reset successful");
            recovery_success = true;
        } else {
            RCLCPP_WARN(node_->get_logger(), "Component reset failed");
        }

        if (!recovery_success) {
            RCLCPP_WARN(node_->get_logger(), "Step 3: Enabling degraded mode for %s (not counted as recovery success)",
                failure_type.c_str());
            enableDegradedMode({failure_type});
            // Do NOT set recovery_success = true — degraded mode is a fallback, not a fix
        }

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Recovery attempt failed: %s", e.what());
        recovery_success = false;
    }

    error_recovery_state_.recovery_active.store(false);

    if (recovery_success) {
        error_recovery_state_.consecutive_failures.store(0);
        RCLCPP_INFO(node_->get_logger(),
            "{\"event\":\"recovery_succeeded\","
            "\"failure_type\":\"%s\"}", failure_type.c_str());
    } else {
        RCLCPP_ERROR(node_->get_logger(),
            "{\"event\":\"recovery_failed\","
            "\"failure_type\":\"%s\","
            "\"action\":\"entering_safe_mode\"}", failure_type.c_str());
        enterSafeMode("recovery_failure");
    }

    return recovery_success;
}

void YanthraMoveSystem::enterSafeMode(const std::string& reason) {
    // Atomic guard against concurrent entry (fixes TOCTOU race)
    bool expected = false;
    if (!error_recovery_state_.safe_mode_active.compare_exchange_strong(expected, true)) {
        return;  // Another thread already entered safe mode
    }

    RCLCPP_ERROR(node_->get_logger(),
        "{\"event\":\"safe_mode_entered\","
        "\"reason\":\"%s\"}", reason.c_str());

    // Step 1: Turn off end effector and compressor immediately (task 2.5)
    try {
        if (motion_controller_) {
            motion_controller_->turnOffEndEffector();
            motion_controller_->turnOffCompressor();
            RCLCPP_INFO(node_->get_logger(), "Safe mode: EE and compressor turned off");
        }
    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(),
            "{\"event\":\"safe_mode_actuator_shutoff_failed\","
            "\"error\":\"%s\"}", e.what());
    }

    // Step 2: Attempt homing with 10-second timeout (spec: homing before safe mode)
    try {
        if (motion_controller_) {
            RCLCPP_INFO(node_->get_logger(), "Safe mode: attempting homing (10s timeout)...");
            auto homing_future = std::async(std::launch::async, [this]() {
                (void)motion_controller_->moveToPackingPosition();
            });
            if (homing_future.wait_for(std::chrono::seconds(10)) == std::future_status::timeout) {
                // Build list of potentially unresponsive joints from failure counters
                std::string unresponsive_joints;
                if (motion_controller_) {
                    if (motion_controller_->getConsecutiveMoveFailures(3) > 0) {
                        unresponsive_joints += "J3,";
                    }
                    if (motion_controller_->getConsecutiveMoveFailures(4) > 0) {
                        unresponsive_joints += "J4,";
                    }
                    if (motion_controller_->getConsecutiveMoveFailures(5) > 0) {
                        unresponsive_joints += "J5,";
                    }
                    if (!unresponsive_joints.empty()) {
                        unresponsive_joints.pop_back();  // Remove trailing comma
                    }
                }
                RCLCPP_ERROR(node_->get_logger(),
                    "{\"event\":\"safe_mode_homing_failed\","
                    "\"reason\":\"timeout_10s\","
                    "\"unresponsive_joints\":\"%s\"}",
                    unresponsive_joints.empty() ? "unknown" : unresponsive_joints.c_str());
                // Detach the homing thread so destructor doesn't block shutdown.
                // std::async's returned future blocks in destructor; moving it to a
                // shared_ptr prevents that — the thread will finish in the background.
                auto detached = std::make_shared<std::future<void>>(std::move(homing_future));
                std::thread([detached]() { detached->wait(); }).detach();
            } else {
                RCLCPP_INFO(node_->get_logger(), "Safe mode: homing completed");
            }
        }
    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(),
            "{\"event\":\"safe_mode_homing_failed\","
            "\"error\":\"%s\"}", e.what());
    }

    // Step 3: Set BOTH stop flags — member AND extern global
    global_stop_requested_.store(true);
    global_stop_requested.store(true);  // extern — read by signal handler paths

    RCLCPP_ERROR(node_->get_logger(),
        "{\"event\":\"safe_mode_active\","
        "\"reason\":\"%s\","
        "\"global_stop\":true}", reason.c_str());
}

bool YanthraMoveSystem::performHealthCheck() {
    RCLCPP_INFO(node_->get_logger(), "🔍 Performing comprehensive health check...");

    bool overall_health = true;

    try {
        // Check 1: ROS2 node health
        if (!rclcpp::ok()) {
            RCLCPP_ERROR(node_->get_logger(), "❌ ROS2 context is not healthy");
            overall_health = false;
        }

        // Check 2: Parameter system
        try {
            (void)node_->get_parameter("continuous_operation").as_bool();
            RCLCPP_DEBUG(node_->get_logger(), "✅ Parameter system healthy");
        } catch (const std::exception& e) {
            RCLCPP_ERROR(node_->get_logger(), "❌ Parameter system unhealthy: %s", e.what());
            overall_health = false;
        }

        // Check 3: Service connections (only in non-simulation mode)
        if (!node_->get_parameter("simulation_mode").as_bool()) {
            if (joint_homing_action_client_ && !joint_homing_action_client_->wait_for_action_server(std::chrono::seconds(1))) {
                RCLCPP_WARN(node_->get_logger(), "⚠️ ODrive homing action server not available");
                // Don't fail health check for this - enable degraded mode instead
            }
        }

        // Check 4: Motion controller
        if (!motion_controller_) {
            RCLCPP_ERROR(node_->get_logger(), "❌ Motion controller not initialized");
            overall_health = false;
        }

        // Check 5: Joint controllers (joint2 removed - not in arm hardware)
        if (!joint_move_3_ || !joint_move_4_ || !joint_move_5_) {
            RCLCPP_ERROR(node_->get_logger(), "❌ Joint controllers not properly initialized");
            overall_health = false;
        }

        RCLCPP_INFO(node_->get_logger(), "%s Overall system health check: %s",
                   overall_health ? "✅" : "❌", overall_health ? "HEALTHY" : "UNHEALTHY");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "❌ Health check failed with exception: %s", e.what());
        overall_health = false;
    }

    return overall_health;
}

bool YanthraMoveSystem::resetSystemComponents() {
    RCLCPP_INFO(node_->get_logger(), "🔄 Resetting system components for recovery...");

    bool reset_success = true;

    try {
        // Reset 1: Clear any error states
        error_recovery_state_.consecutive_failures.store(0);
        // Only clear global stop if safe mode is NOT active — safe mode intentionally set it
        if (!error_recovery_state_.safe_mode_active.load()) {
            global_stop_requested_.store(false);
        }

        // Reset 2: Reinitialize joint controllers if needed
        if (!joint_move_3_ || !joint_move_4_ || !joint_move_5_) {
            RCLCPP_INFO(node_->get_logger(), "🔧 Reinitializing joint controllers...");
            try {
                initializeJointControllers();
                RCLCPP_INFO(node_->get_logger(), "✅ Joint controllers reinitialized");
            } catch (const std::exception& e) {
                RCLCPP_ERROR(node_->get_logger(), "❌ Failed to reinitialize joint controllers: %s", e.what());
                reset_success = false;
            }
        }

        // Reset 3: Reinitialize motion controller if needed
        if (!motion_controller_) {
            RCLCPP_INFO(node_->get_logger(), "🔧 Reinitializing motion controller...");
            try {
                initializeModularComponents();
                RCLCPP_INFO(node_->get_logger(), "✅ Motion controller reinitialized");
            } catch (const std::exception& e) {
                RCLCPP_ERROR(node_->get_logger(), "❌ Failed to reinitialize motion controller: %s", e.what());
                reset_success = false;
            }
        }

        // Reset 4: Clear any stuck states
        if (motion_controller_) {
            // Reset motion controller internal state if available
            RCLCPP_INFO(node_->get_logger(), "🔄 Clearing motion controller state...");
        }

        RCLCPP_INFO(node_->get_logger(), "%s Component reset: %s",
                   reset_success ? "✅" : "❌", reset_success ? "SUCCESS" : "FAILED");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "❌ Component reset failed: %s", e.what());
        reset_success = false;
    }

    return reset_success;
}

void YanthraMoveSystem::enableDegradedMode(const std::vector<std::string>& disabled_components) {
    std::lock_guard<std::mutex> lock(error_recovery_state_.state_mutex);

    error_recovery_state_.degraded_mode_active.store(true);
    error_recovery_state_.disabled_components.insert(
        error_recovery_state_.disabled_components.end(),
        disabled_components.begin(), disabled_components.end());

    RCLCPP_WARN(node_->get_logger(), "⚠️ ENTERING DEGRADED MODE");
    RCLCPP_WARN(node_->get_logger(), "⚠️ Disabled components: ");
    for (const auto& component : disabled_components) {
        RCLCPP_WARN(node_->get_logger(), "   - %s", component.c_str());
    }

    // Log operational capabilities in degraded mode
    bool has_motion = std::find(disabled_components.begin(), disabled_components.end(), "joint_controller") == disabled_components.end();
    bool has_vision = std::find(disabled_components.begin(), disabled_components.end(), "camera") == disabled_components.end();
    bool has_gpio = std::find(disabled_components.begin(), disabled_components.end(), "GPIO") == disabled_components.end();

    RCLCPP_WARN(node_->get_logger(), "📊 Remaining capabilities:");
    RCLCPP_WARN(node_->get_logger(), "   Motion Control: %s", has_motion ? "✅ Available" : "❌ Disabled");
    RCLCPP_WARN(node_->get_logger(), "   Vision System: %s", has_vision ? "✅ Available" : "❌ Disabled");
    RCLCPP_WARN(node_->get_logger(), "   GPIO Interface: %s", has_gpio ? "✅ Available" : "❌ Disabled");

    RCLCPP_WARN(node_->get_logger(), "⚠️ System will continue with reduced functionality");
}

}  // namespace yanthra_move
