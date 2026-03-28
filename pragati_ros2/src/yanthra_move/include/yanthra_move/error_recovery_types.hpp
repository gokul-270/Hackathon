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

#pragma once

#include <atomic>
#include <chrono>
#include <mutex>
#include <string>
#include <vector>

namespace yanthra_move {

// Operational failure categories routed through handleOperationalFailure()
enum class FailureType {
    MOTOR_TIMEOUT,            // move_joint() returned TIMEOUT
    MOTOR_ERROR,              // move_joint() returned ERROR
    DETECTION_UNAVAILABLE,    // Detection service not ready or timed out
    PICK_TIMEOUT              // Pick cycle exceeded deadline
};

// Context passed alongside every operational failure report
struct FailureContext {
    int joint_id{0};               // Joint number (3, 4, 5) or 0 if not joint-specific
    double target_position{0.0};   // Target position that was commanded (if applicable)
    int cycle_count{0};            // Current pick cycle number
    std::string phase;             // Operation phase (e.g. "approach_j4", "retreat", "capture")
};

/**
 * @brief Error recovery state tracking for YanthraMoveSystem
 *
 * Tracks recovery status, failure counts, and degraded mode components.
 * Extracted from yanthra_move_system.hpp for independent use by error
 * recovery subsystems.
 */
struct ErrorRecoveryState {
    std::atomic<bool> recovery_active{false};
    std::atomic<bool> safe_mode_active{false};
    std::atomic<bool> degraded_mode_active{false};
    std::atomic<int> consecutive_failures{0};
    std::atomic<int> total_recoveries{0};
    std::chrono::steady_clock::time_point last_error_time;
    std::vector<std::string> disabled_components;
    std::mutex state_mutex;
};

}  // namespace yanthra_move
