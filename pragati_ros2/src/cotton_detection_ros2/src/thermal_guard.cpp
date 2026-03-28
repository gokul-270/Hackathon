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

#include "cotton_detection_ros2/thermal_guard.hpp"

#include <exception>

namespace cotton_detection {

ThermalGuard::ThermalGuard(TemperatureSource source, const Config& config)
    : source_(std::move(source)), config_(config)
{
    if (!source_) {
        throw std::invalid_argument("ThermalGuard: temperature source must not be null");
    }
    if (config_.warning_temp >= config_.throttle_temp) {
        throw std::invalid_argument(
            "ThermalGuard: warning_temp (" + std::to_string(config_.warning_temp) +
            ") must be less than throttle_temp (" + std::to_string(config_.throttle_temp) + ")");
    }
    if (config_.throttle_temp >= config_.critical_temp) {
        throw std::invalid_argument(
            "ThermalGuard: throttle_temp (" + std::to_string(config_.throttle_temp) +
            ") must be less than critical_temp (" + std::to_string(config_.critical_temp) + ")");
    }
}

void ThermalGuard::update()
{
    double temp;
    try {
        temp = source_();
    } catch (const std::exception&) {
        // Retain previous reading on source failure (spec: exception isolation)
        return;
    }

    temperature_.store(temp, std::memory_order_relaxed);

    auto old_status = status_.load(std::memory_order_relaxed);
    auto new_status = evaluateStatus(temp, old_status);
    status_.store(new_status, std::memory_order_relaxed);

    if (new_status != old_status && on_status_change_) {
        on_status_change_(old_status, new_status);
    }
}

ThermalStatus ThermalGuard::getStatus() const
{
    return status_.load(std::memory_order_relaxed);
}

double ThermalGuard::getCurrentTemperature() const
{
    return temperature_.load(std::memory_order_relaxed);
}

bool ThermalGuard::shouldThrottle() const
{
    auto s = status_.load(std::memory_order_relaxed);
    return s >= ThermalStatus::Throttle;
}

void ThermalGuard::onStatusChange(StatusChangeCallback callback)
{
    on_status_change_ = std::move(callback);
}

ThermalStatus ThermalGuard::evaluateStatus(double temp, ThermalStatus current_status) const
{
    // Upward transitions: if temp reaches or exceeds a higher threshold, always promote.
    // This takes priority over hysteresis (you can't stay at Warning if temp hits Critical).
    if (temp >= config_.critical_temp) {
        return ThermalStatus::Critical;
    }

    // Hysteresis: if currently at a higher status, stay there until temp drops below
    // (threshold - hysteresis). Check hysteresis BEFORE lower upward thresholds.
    if (current_status == ThermalStatus::Critical) {
        if (temp >= config_.critical_temp - config_.hysteresis) {
            return ThermalStatus::Critical;
        }
        // Fell below critical hysteresis band — fall through to evaluate lower statuses
    }

    if (temp >= config_.throttle_temp) {
        return ThermalStatus::Throttle;
    }

    if (current_status >= ThermalStatus::Throttle) {
        if (temp >= config_.throttle_temp - config_.hysteresis) {
            return ThermalStatus::Throttle;
        }
    }

    if (temp >= config_.warning_temp) {
        return ThermalStatus::Warning;
    }

    if (current_status >= ThermalStatus::Warning) {
        if (temp >= config_.warning_temp - config_.hysteresis) {
            return ThermalStatus::Warning;
        }
    }

    return ThermalStatus::Normal;
}

}  // namespace cotton_detection
