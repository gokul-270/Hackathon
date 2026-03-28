// Copyright 2026 Pragati Robotics
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

#include <rclcpp/logger.hpp>

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>

namespace motor_control_ros2 { class GPIOControlFunctions; }

namespace yanthra_move { namespace core {

/// Manages end-effector and compressor GPIO operations for cotton capture.
/// Extracted from MotionController to isolate actuator sequencing logic.
class CaptureSequence {
public:
    CaptureSequence(std::shared_ptr<motor_control_ros2::GPIOControlFunctions> gpio,
                    rclcpp::Logger logger);

    /// Set callback that returns current J5 position (-1.0 when unavailable).
    void setJ5PositionCallback(std::function<double()> callback);

    /// Activate end-effector with optional dynamic pre-start based on J5 proximity.
    /// Returns false if EE is disabled via master enable flag.
    /// When use_dynamic_prestart is true, activates only when J5 is within
    /// ee_start_distance of target_j5. Falls back to timeout if J5 callback
    /// returns -1.0 (no position data).
    bool activateEE(double target_j5, float ee_start_distance, bool use_dynamic_prestart);

    /// Deactivate EE if J5 has retreated past stop distance from target.
    /// Returns true if EE was turned off.
    bool deactivateOnRetreat(double target_j5, float ee_stop_distance);

    /// Blocking call: turns EE on, sleeps for duration_ms, turns EE off.
    /// Returns false if EE is disabled via master enable flag.
    bool activateEESequential(float duration_ms);

    /// Blocking call: turns compressor on, sleeps for duration_sec, turns off.
    void compressorBurst(double duration_sec);

    /// Master enable/disable for end-effector operations.
    void setEndEffectorEnabled(bool enabled);

    /// Force end-effector off immediately.
    void turnOffEndEffector();

    /// Force compressor off immediately.
    void turnOffCompressor();

    /// Low-level state primitives for use by orchestrator when it controls GPIO directly
    /// (e.g., position-monitoring loops that haven't been extracted yet).
    /// These update internal state WITHOUT touching GPIO hardware.
    void markEeActive();    ///< Record EE as active: sets flag, records timestamp, increments counter
    void markEeInactive();  ///< Record EE as inactive: clears flag
    void markCompressorActive();   ///< Record compressor as active: sets flag, records timestamp, increments counter
    void markCompressorInactive(); ///< Record compressor as inactive: clears flag

    // --- State queries ---

    bool isEeCurrentlyOn() const;
    bool isCompressorCurrentlyOn() const;

    /// Returns the time point when EE was last turned on (mutex-protected).
    std::chrono::steady_clock::time_point getEeOnSince() const;

    /// Returns the time point when compressor was last turned on (mutex-protected).
    std::chrono::steady_clock::time_point getCompressorOnSince() const;

    int getEeActivationCount() const;
    int getCompressorActivationCount() const;

private:
    std::shared_ptr<motor_control_ros2::GPIOControlFunctions> gpio_;
    rclcpp::Logger logger_;

    std::function<double()> j5_position_callback_;

    std::atomic<bool> ee_currently_on_{false};
    std::atomic<bool> compressor_currently_on_{false};
    std::atomic<bool> end_effector_enabled_{true};

    std::chrono::steady_clock::time_point ee_on_start_time_;
    std::chrono::steady_clock::time_point compressor_on_start_time_;
    mutable std::mutex actuator_time_mutex_;

    std::atomic<int> ee_activation_count_{0};
    std::atomic<int> compressor_activation_count_{0};
};

}}  // namespace yanthra_move::core
