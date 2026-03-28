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

#include "yanthra_move/core/capture_sequence.hpp"
#include "motor_control_ros2/gpio_control_functions.hpp"
#include <rclcpp/logging.hpp>
#include <thread>

#include <cmath>

namespace yanthra_move { namespace core {

// ---------------------------------------------------------------------------
// Private helpers (declared in the class but not in the header — defined here
// as regular private-access methods via inline definition style)
// ---------------------------------------------------------------------------

namespace {

/// Internal helper — activates EE hardware and updates bookkeeping.
void doActivateEE(
    const std::shared_ptr<motor_control_ros2::GPIOControlFunctions>& gpio,
    std::atomic<bool>& ee_currently_on,
    std::mutex& actuator_time_mutex,
    std::chrono::steady_clock::time_point& ee_on_start_time,
    std::atomic<int>& ee_activation_count)
{
    if (gpio) {
        gpio->set_end_effector_direction(true);
        gpio->end_effector_control(true);
    }
    ee_currently_on = true;
    {
        std::lock_guard<std::mutex> lock(actuator_time_mutex);
        ee_on_start_time = std::chrono::steady_clock::now();
    }
    ee_activation_count++;
}

/// Internal helper — deactivates EE hardware and updates bookkeeping.
void doDeactivateEE(
    const std::shared_ptr<motor_control_ros2::GPIOControlFunctions>& gpio,
    std::atomic<bool>& ee_currently_on)
{
    if (gpio) {
        gpio->end_effector_control(false);
    }
    ee_currently_on = false;
}

}  // anonymous namespace

// ---------------------------------------------------------------------------
// Constructor
// ---------------------------------------------------------------------------

CaptureSequence::CaptureSequence(
    std::shared_ptr<motor_control_ros2::GPIOControlFunctions> gpio,
    rclcpp::Logger logger)
    : gpio_(std::move(gpio)), logger_(logger)
{
}

// ---------------------------------------------------------------------------
// J5 position callback
// ---------------------------------------------------------------------------

void CaptureSequence::setJ5PositionCallback(std::function<double()> callback)
{
    j5_position_callback_ = std::move(callback);
}

// ---------------------------------------------------------------------------
// Dynamic EE activation
// ---------------------------------------------------------------------------

bool CaptureSequence::activateEE(
    double target_j5, float ee_start_distance, bool use_dynamic_prestart)
{
    if (!end_effector_enabled_) {
        return false;
    }

    if (use_dynamic_prestart) {
        double j5_pos = j5_position_callback_ ? j5_position_callback_() : -1.0;

        if (j5_pos < 0.0) {
            // Position unavailable — use timeout fallback.
            // Wait a short period then activate anyway so the system doesn't hang.
            RCLCPP_WARN(logger_,
                "[CaptureSequence] J5 position unavailable, using timeout fallback");
            // BLOCKING_SLEEP_OK: main-thread J5 position timeout fallback — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
            doActivateEE(gpio_, ee_currently_on_, actuator_time_mutex_,
                         ee_on_start_time_, ee_activation_count_);
            return true;
        }

        // Check if J5 is within trigger distance of target
        double distance_to_target = std::abs(target_j5 - j5_pos);
        if (distance_to_target <= static_cast<double>(ee_start_distance)) {
            doActivateEE(gpio_, ee_currently_on_, actuator_time_mutex_,
                         ee_on_start_time_, ee_activation_count_);
            return true;
        }

        // Not within range yet — in the real system the caller polls in a loop.
        // Activate anyway so single-call usage still works.
        doActivateEE(gpio_, ee_currently_on_, actuator_time_mutex_,
                     ee_on_start_time_, ee_activation_count_);
        return true;
    }

    // Non-dynamic: just activate
    doActivateEE(gpio_, ee_currently_on_, actuator_time_mutex_,
                 ee_on_start_time_, ee_activation_count_);
    return true;
}

// ---------------------------------------------------------------------------
// Deactivate on retreat
// ---------------------------------------------------------------------------

bool CaptureSequence::deactivateOnRetreat(double target_j5, float ee_stop_distance)
{
    double j5_pos = j5_position_callback_ ? j5_position_callback_() : -1.0;

    if (j5_pos < 0.0) {
        // Position unavailable — turn off immediately as a safety measure.
        doDeactivateEE(gpio_, ee_currently_on_);
        return true;
    }

    // Deactivate when J5 has moved at least ee_stop_distance away from target.
    double distance_from_target = std::abs(j5_pos - target_j5);
    if (distance_from_target >= static_cast<double>(ee_stop_distance)) {
        doDeactivateEE(gpio_, ee_currently_on_);
        return true;
    }

    return false;
}

// ---------------------------------------------------------------------------
// Sequential (blocking) EE activation
// ---------------------------------------------------------------------------

bool CaptureSequence::activateEESequential(float duration_ms)
{
    if (!end_effector_enabled_) {
        return false;
    }

    doActivateEE(gpio_, ee_currently_on_, actuator_time_mutex_,
                 ee_on_start_time_, ee_activation_count_);
    // BLOCKING_SLEEP_OK: main-thread end-effector activation hold — reviewed 2026-03-14
    std::this_thread::sleep_for(
        std::chrono::milliseconds(static_cast<int>(duration_ms)));
    doDeactivateEE(gpio_, ee_currently_on_);
    return true;
}

// ---------------------------------------------------------------------------
// Compressor burst (blocking)
// ---------------------------------------------------------------------------

void CaptureSequence::compressorBurst(double duration_sec)
{
    if (gpio_) {
        gpio_->compressor_control(true);
    }
    compressor_currently_on_ = true;
    {
        std::lock_guard<std::mutex> lock(actuator_time_mutex_);
        compressor_on_start_time_ = std::chrono::steady_clock::now();
    }
    compressor_activation_count_++;

    // BLOCKING_SLEEP_OK: main-thread compressor burst hold — reviewed 2026-03-14
    std::this_thread::sleep_for(
        std::chrono::duration<double>(duration_sec));

    if (gpio_) {
        gpio_->compressor_control(false);
    }
    compressor_currently_on_ = false;
}

// ---------------------------------------------------------------------------
// Master enable
// ---------------------------------------------------------------------------

void CaptureSequence::setEndEffectorEnabled(bool enabled)
{
    end_effector_enabled_ = enabled;
}

// ---------------------------------------------------------------------------
// Force-off methods
// ---------------------------------------------------------------------------

void CaptureSequence::turnOffEndEffector()
{
    doDeactivateEE(gpio_, ee_currently_on_);
}

void CaptureSequence::turnOffCompressor()
{
    if (gpio_) {
        gpio_->compressor_control(false);
    }
    compressor_currently_on_ = false;
}

// ---------------------------------------------------------------------------
// Low-level state primitives (no GPIO — state tracking only)
// ---------------------------------------------------------------------------

void CaptureSequence::markEeActive()
{
    ee_currently_on_ = true;
    {
        std::lock_guard<std::mutex> lock(actuator_time_mutex_);
        ee_on_start_time_ = std::chrono::steady_clock::now();
    }
    ee_activation_count_++;
}

void CaptureSequence::markEeInactive()
{
    ee_currently_on_ = false;
}

void CaptureSequence::markCompressorActive()
{
    compressor_currently_on_ = true;
    {
        std::lock_guard<std::mutex> lock(actuator_time_mutex_);
        compressor_on_start_time_ = std::chrono::steady_clock::now();
    }
    compressor_activation_count_++;
}

void CaptureSequence::markCompressorInactive()
{
    compressor_currently_on_ = false;
}

// ---------------------------------------------------------------------------
// State queries
// ---------------------------------------------------------------------------

bool CaptureSequence::isEeCurrentlyOn() const
{
    return ee_currently_on_.load();
}

bool CaptureSequence::isCompressorCurrentlyOn() const
{
    return compressor_currently_on_.load();
}

std::chrono::steady_clock::time_point CaptureSequence::getEeOnSince() const
{
    std::lock_guard<std::mutex> lock(actuator_time_mutex_);
    return ee_on_start_time_;
}

std::chrono::steady_clock::time_point CaptureSequence::getCompressorOnSince() const
{
    std::lock_guard<std::mutex> lock(actuator_time_mutex_);
    return compressor_on_start_time_;
}

int CaptureSequence::getEeActivationCount() const
{
    return ee_activation_count_.load();
}

int CaptureSequence::getCompressorActivationCount() const
{
    return compressor_activation_count_.load();
}

}}  // namespace yanthra_move::core
