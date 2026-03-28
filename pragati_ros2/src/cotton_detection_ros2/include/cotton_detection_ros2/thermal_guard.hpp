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

/**
 * @file thermal_guard.hpp
 * @brief Non-blocking thermal monitoring for OAK-D Lite camera chip temperature.
 *
 * Replaces inline thermal logic scattered across depthai_manager.cpp and
 * cotton_detection_node_services.cpp. Uses std::atomic for lock-free
 * status reads during concurrent update/query from separate threads.
 *
 * NO rclcpp or DepthAI dependencies — testable with mocked temperature sources.
 *
 * PRD: PERF-ARM-001, FR-DET-001
 * TSD: depthai.thermal.* parameters
 */

#include <atomic>
#include <cstdint>
#include <functional>
#include <stdexcept>

namespace cotton_detection {

/**
 * @brief Thermal severity levels in increasing order.
 *
 * Supports operator< for ordering: Normal < Warning < Throttle < Critical.
 */
enum class ThermalStatus : uint8_t {
    Normal = 0,
    Warning = 1,
    Throttle = 2,
    Critical = 3
};

inline bool operator<(ThermalStatus lhs, ThermalStatus rhs) {
    return static_cast<uint8_t>(lhs) < static_cast<uint8_t>(rhs);
}

inline bool operator<=(ThermalStatus lhs, ThermalStatus rhs) {
    return static_cast<uint8_t>(lhs) <= static_cast<uint8_t>(rhs);
}

inline bool operator>(ThermalStatus lhs, ThermalStatus rhs) {
    return static_cast<uint8_t>(lhs) > static_cast<uint8_t>(rhs);
}

inline bool operator>=(ThermalStatus lhs, ThermalStatus rhs) {
    return static_cast<uint8_t>(lhs) >= static_cast<uint8_t>(rhs);
}

/**
 * @brief Non-blocking thermal monitor driven by an external temperature source.
 *
 * Thread safety (D7):
 *   - temperature_: std::atomic<double> — lock-free reads from any thread
 *   - status_: std::atomic<ThermalStatus> — lock-free reads from any thread
 *   - update() is NOT thread-safe with itself (single writer assumed, e.g. timer callback)
 *   - getStatus(), getCurrentTemperature(), shouldThrottle() are safe from any thread
 *
 * The caller (CottonDetectionNode) creates a ROS2 wall timer that calls update().
 * ThermalGuard itself never creates timers or threads.
 */
class ThermalGuard {
public:
    /**
     * @brief Threshold configuration.
     *
     * Must satisfy: warning_temp < throttle_temp < critical_temp.
     * Hysteresis applies on downward transitions only.
     */
    struct Config {
        double warning_temp = 70.0;
        double throttle_temp = 80.0;
        double critical_temp = 90.0;
        double hysteresis = 5.0;
    };

    using TemperatureSource = std::function<double()>;
    using StatusChangeCallback = std::function<void(ThermalStatus, ThermalStatus)>;

    /**
     * @brief Construct a ThermalGuard.
     *
     * @param source Temperature source callback (must not be null/empty)
     * @param config Threshold configuration
     * @throws std::invalid_argument if source is null or thresholds violate ordering
     */
    ThermalGuard(TemperatureSource source, const Config& config);

    /**
     * @brief Read the temperature source and evaluate thresholds.
     *
     * If the source throws, the exception is caught and the previous reading
     * is retained. Must be called from a single writer thread (e.g. timer callback).
     * Completes in <1ms — no sleep, no blocking I/O.
     */
    void update();

    /**
     * @brief Get the current thermal status. Thread-safe, lock-free.
     */
    ThermalStatus getStatus() const;

    /**
     * @brief Get the last successful temperature reading. Thread-safe, lock-free.
     *
     * Returns 0.0 if update() has never been called.
     */
    double getCurrentTemperature() const;

    /**
     * @brief Returns true if status is Throttle or Critical. Thread-safe.
     */
    bool shouldThrottle() const;

    /**
     * @brief Register a callback invoked on status transitions.
     *
     * The callback receives (old_status, new_status). It is called synchronously
     * from within update(). Only one callback is supported; subsequent calls
     * replace the previous callback.
     */
    void onStatusChange(StatusChangeCallback callback);

private:
    /**
     * @brief Evaluate which ThermalStatus corresponds to a given temperature,
     *        applying hysteresis on downward transitions from current_status.
     */
    ThermalStatus evaluateStatus(double temp, ThermalStatus current_status) const;

    TemperatureSource source_;
    Config config_;

    std::atomic<double> temperature_{0.0};
    std::atomic<ThermalStatus> status_{ThermalStatus::Normal};

    // Callback — only accessed from update() (single writer), so no mutex needed.
    StatusChangeCallback on_status_change_;
};

}  // namespace cotton_detection
