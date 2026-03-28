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
 * @file test_thermal_guard.cpp
 * @brief GTest unit tests for ThermalGuard component.
 *
 * Tests verify that ThermalGuard:
 *   - Constructs with valid temperature source and rejects null/invalid
 *   - Evaluates temperature thresholds correctly (Normal/Warning/Throttle/Critical)
 *   - Applies 5°C hysteresis on downward transitions
 *   - Reports shouldThrottle() correctly for each status
 *   - Invokes status change callbacks on transitions
 *   - Isolates temperature source exceptions
 *   - Operates non-blocking (no sleep, completes in <1ms)
 *   - Supports concurrent reads during update (no torn reads)
 *
 * This test binary does NOT link against depthai::core.
 * ThermalGuard is hardware-decoupled via std::function<double()>.
 */

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <functional>
#include <stdexcept>
#include <thread>
#include <vector>

#include "cotton_detection_ros2/thermal_guard.hpp"

namespace cotton_detection {
namespace test {

// Default thresholds matching TSD config schema
static constexpr double kWarningTemp = 70.0;
static constexpr double kThrottleTemp = 80.0;
static constexpr double kCriticalTemp = 90.0;
static constexpr double kHysteresis = 5.0;

// Helper: create a ThermalGuard with a controllable temperature
class ThermalGuardTest : public ::testing::Test {
protected:
    double current_temp_ = 25.0;

    std::function<double()> makeSource() {
        return [this]() { return current_temp_; };
    }

    std::unique_ptr<ThermalGuard> makeGuard(
        double warning = kWarningTemp,
        double throttle = kThrottleTemp,
        double critical = kCriticalTemp,
        double hysteresis = kHysteresis)
    {
        ThermalGuard::Config config;
        config.warning_temp = warning;
        config.throttle_temp = throttle;
        config.critical_temp = critical;
        config.hysteresis = hysteresis;
        return std::make_unique<ThermalGuard>(makeSource(), config);
    }
};

// ============================================================================
// Task 1.2: Construction tests
// ============================================================================

TEST_F(ThermalGuardTest, ConstructionWithValidSource_ReturnsNormalAndZeroTemp) {
    auto guard = makeGuard();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Normal);
    EXPECT_DOUBLE_EQ(guard->getCurrentTemperature(), 0.0);
}

TEST_F(ThermalGuardTest, ConstructionWithNullSource_ThrowsInvalidArgument) {
    ThermalGuard::Config config;
    config.warning_temp = kWarningTemp;
    config.throttle_temp = kThrottleTemp;
    config.critical_temp = kCriticalTemp;
    EXPECT_THROW(
        ThermalGuard(std::function<double()>(nullptr), config),
        std::invalid_argument);
}

TEST_F(ThermalGuardTest, InvalidThresholdOrdering_WarningGteThrottle_Throws) {
    EXPECT_THROW(makeGuard(80.0, 70.0, 90.0), std::invalid_argument);
}

TEST_F(ThermalGuardTest, InvalidThresholdOrdering_ThrottleGteCritical_Throws) {
    EXPECT_THROW(makeGuard(70.0, 90.0, 80.0), std::invalid_argument);
}

TEST_F(ThermalGuardTest, InvalidThresholdOrdering_EqualWarningThrottle_Throws) {
    EXPECT_THROW(makeGuard(80.0, 80.0, 90.0), std::invalid_argument);
}

// ============================================================================
// Task 1.3: Threshold evaluation tests
// ============================================================================

TEST_F(ThermalGuardTest, NormalTemperature_BelowAllThresholds) {
    auto guard = makeGuard();
    current_temp_ = 55.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Normal);
    EXPECT_DOUBLE_EQ(guard->getCurrentTemperature(), 55.0);
}

TEST_F(ThermalGuardTest, WarningThreshold_AtExactly70) {
    auto guard = makeGuard();
    current_temp_ = 70.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Warning);
}

TEST_F(ThermalGuardTest, ThrottleThreshold_AtExactly80) {
    auto guard = makeGuard();
    current_temp_ = 80.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Throttle);
}

TEST_F(ThermalGuardTest, CriticalThreshold_AtExactly90) {
    auto guard = makeGuard();
    current_temp_ = 90.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Critical);
}

TEST_F(ThermalGuardTest, BoundaryAt80_ReturnsThrottleNotWarning) {
    // >= comparison means exactly at throttle threshold is Throttle
    auto guard = makeGuard();
    current_temp_ = 80.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Throttle);
}

TEST_F(ThermalGuardTest, Hysteresis_DropFrom82To76_StaysThrottle) {
    auto guard = makeGuard();
    // Go to Throttle
    current_temp_ = 82.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Throttle);

    // Drop to 76°C — within hysteresis (80 - 5 = 75), so should stay Throttle
    current_temp_ = 76.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Throttle);
}

TEST_F(ThermalGuardTest, Hysteresis_DropFrom82To74_TransitionsToWarning) {
    auto guard = makeGuard();
    // Go to Throttle
    current_temp_ = 82.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Throttle);

    // Drop to 74°C — below hysteresis band (80 - 5 = 75), should transition
    current_temp_ = 74.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Warning);
}

TEST_F(ThermalGuardTest, Hysteresis_CriticalToThrottle) {
    auto guard = makeGuard();
    // Go to Critical
    current_temp_ = 95.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Critical);

    // Drop to 86°C — within hysteresis of critical (90 - 5 = 85)
    current_temp_ = 86.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Critical);

    // Drop to 84°C — below hysteresis of critical, should be Throttle
    current_temp_ = 84.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Throttle);
}

TEST_F(ThermalGuardTest, StatusQueryableAfterMultipleUpdates) {
    auto guard = makeGuard();

    current_temp_ = 50.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Normal);

    current_temp_ = 72.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Warning);

    current_temp_ = 50.0;
    guard->update();
    EXPECT_EQ(guard->getStatus(), ThermalStatus::Normal);
}

// ============================================================================
// Task 1.4: shouldThrottle, callbacks, exception isolation
// ============================================================================

TEST_F(ThermalGuardTest, ShouldThrottle_FalseAtNormal) {
    auto guard = makeGuard();
    current_temp_ = 50.0;
    guard->update();
    EXPECT_FALSE(guard->shouldThrottle());
}

TEST_F(ThermalGuardTest, ShouldThrottle_FalseAtWarning) {
    auto guard = makeGuard();
    current_temp_ = 72.0;
    guard->update();
    EXPECT_FALSE(guard->shouldThrottle());
}

TEST_F(ThermalGuardTest, ShouldThrottle_TrueAtThrottle) {
    auto guard = makeGuard();
    current_temp_ = 82.0;
    guard->update();
    EXPECT_TRUE(guard->shouldThrottle());
}

TEST_F(ThermalGuardTest, ShouldThrottle_TrueAtCritical) {
    auto guard = makeGuard();
    current_temp_ = 95.0;
    guard->update();
    EXPECT_TRUE(guard->shouldThrottle());
}

TEST_F(ThermalGuardTest, StatusChangeCallback_InvokedOnTransition) {
    auto guard = makeGuard();

    ThermalStatus old_status = ThermalStatus::Normal;
    ThermalStatus new_status = ThermalStatus::Normal;
    int callback_count = 0;

    guard->onStatusChange([&](ThermalStatus old_s, ThermalStatus new_s) {
        old_status = old_s;
        new_status = new_s;
        callback_count++;
    });

    // Normal -> Warning
    current_temp_ = 72.0;
    guard->update();
    EXPECT_EQ(callback_count, 1);
    EXPECT_EQ(old_status, ThermalStatus::Normal);
    EXPECT_EQ(new_status, ThermalStatus::Warning);

    // Warning -> Throttle
    current_temp_ = 82.0;
    guard->update();
    EXPECT_EQ(callback_count, 2);
    EXPECT_EQ(old_status, ThermalStatus::Warning);
    EXPECT_EQ(new_status, ThermalStatus::Throttle);
}

TEST_F(ThermalGuardTest, StatusChangeCallback_NotInvokedWhenNoTransition) {
    auto guard = makeGuard();
    int callback_count = 0;
    guard->onStatusChange([&](ThermalStatus, ThermalStatus) {
        callback_count++;
    });

    current_temp_ = 50.0;
    guard->update();
    EXPECT_EQ(callback_count, 0);  // Was already Normal

    guard->update();  // Same temp
    EXPECT_EQ(callback_count, 0);
}

TEST_F(ThermalGuardTest, TemperatureSourceException_RetainsPreviousReading) {
    bool should_throw = false;
    double temp = 55.0;
    auto source = [&]() -> double {
        if (should_throw) throw std::runtime_error("sensor failure");
        return temp;
    };

    ThermalGuard::Config config;
    config.warning_temp = kWarningTemp;
    config.throttle_temp = kThrottleTemp;
    config.critical_temp = kCriticalTemp;
    config.hysteresis = kHysteresis;
    ThermalGuard guard(source, config);

    // First update: 55°C
    guard.update();
    EXPECT_DOUBLE_EQ(guard.getCurrentTemperature(), 55.0);
    EXPECT_EQ(guard.getStatus(), ThermalStatus::Normal);

    // Source now throws
    should_throw = true;
    guard.update();  // Should NOT propagate
    EXPECT_DOUBLE_EQ(guard.getCurrentTemperature(), 55.0);  // Retained
    EXPECT_EQ(guard.getStatus(), ThermalStatus::Normal);    // Retained
}

// ============================================================================
// Task 1.5: Non-blocking guarantee and concurrency
// ============================================================================

TEST_F(ThermalGuardTest, UpdateCompletesInUnder1ms) {
    auto guard = makeGuard();
    current_temp_ = 75.0;

    auto start = std::chrono::steady_clock::now();
    guard->update();
    auto elapsed = std::chrono::steady_clock::now() - start;

    EXPECT_LT(std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count(), 1000)
        << "update() took longer than 1ms";
}

TEST_F(ThermalGuardTest, ConcurrentStatusReadsDuringUpdate) {
    auto guard = makeGuard();
    std::atomic<bool> done{false};
    std::atomic<int> read_count{0};
    std::atomic<bool> any_error{false};

    // Thread B: continuously read status
    std::thread reader([&]() {
        while (!done.load()) {
            auto status = guard->getStatus();
            // Verify no torn reads: status must be a valid enum value
            if (status != ThermalStatus::Normal &&
                status != ThermalStatus::Warning &&
                status != ThermalStatus::Throttle &&
                status != ThermalStatus::Critical) {
                any_error.store(true);
            }
            read_count++;
        }
    });

    // Let reader thread start
    std::this_thread::yield();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));

    // Thread A: do many updates with varying temperatures
    for (int i = 0; i < 10000; ++i) {
        current_temp_ = 50.0 + (i % 50);  // 50-99°C range
        guard->update();
        if (i % 100 == 0) {
            std::this_thread::yield();
        }
    }

    done.store(true);
    reader.join();

    EXPECT_FALSE(any_error.load()) << "Torn reads detected during concurrent access";
    EXPECT_GT(read_count.load(), 0) << "Reader thread did not execute";
}

TEST_F(ThermalGuardTest, ConcurrentUpdateAndRead_NeitherBlocksOver1ms) {
    auto guard = makeGuard();
    std::atomic<bool> done{false};
    std::atomic<int64_t> max_read_us{0};

    // Reader thread
    std::thread reader([&]() {
        while (!done.load()) {
            auto start = std::chrono::steady_clock::now();
            guard->getStatus();
            auto elapsed_us = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - start).count();
            int64_t expected = max_read_us.load();
            while (elapsed_us > expected &&
                   !max_read_us.compare_exchange_weak(expected, elapsed_us)) {}
        }
    });

    // Writer thread
    for (int i = 0; i < 500; ++i) {
        current_temp_ = 50.0 + (i % 50);
        auto start = std::chrono::steady_clock::now();
        guard->update();
        auto elapsed_us = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - start).count();
        EXPECT_LT(elapsed_us, 1000) << "update() blocked for >1ms at iteration " << i;
    }

    done.store(true);
    reader.join();

    EXPECT_LT(max_read_us.load(), 1000) << "getStatus() blocked for >1ms";
}

}  // namespace test
}  // namespace cotton_detection
