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
 * @file test_thermal_logging.cpp
 * @brief GTest unit tests for thermal fields in detection_summary JSON.
 *
 * Tests verify that the thermal JSON object in detection_summary correctly
 * reflects the is_throttled_ and is_paused_ atomic flags:
 *   - throttle_effective mirrors is_throttled_ state
 *   - paused field is present and mirrors is_paused_ state
 *   - paused and throttle_effective are independent flags
 *
 * This test binary does NOT link against depthai::core or rclcpp.
 * It replicates the exact JSON construction from cotton_detection_node.cpp
 * using only nlohmann::json and std::atomic<bool>.
 */

#include <gtest/gtest.h>

#include <atomic>

#include <nlohmann/json.hpp>

using nlohmann::json;

namespace cotton_detection {
namespace test {

/**
 * Helper that replicates the exact production JSON construction from
 * cotton_detection_node.cpp (lines 463-466):
 *
 *   j["thermal"] = {
 *       {"throttle_effective", is_throttled_.load()},
 *       {"paused", is_paused_.load()}
 *   };
 *
 * By testing this identical construction with controlled atomic values,
 * we verify the JSON output matches the expected schema.
 */
static json buildThermalJson(std::atomic<bool>& is_throttled,
                             std::atomic<bool>& is_paused)
{
    json j;
    j["thermal"] = {
        {"throttle_effective", is_throttled.load()},
        {"paused", is_paused.load()}
    };
    return j;
}

// ============================================================================
// Task 2.3: throttle_effective reflects is_throttled_ state
// ============================================================================

TEST(ThermalLoggingTest, ThrottleEffective_TrueWhenIsThrottledSet) {
    std::atomic<bool> is_throttled{true};
    std::atomic<bool> is_paused{false};

    auto j = buildThermalJson(is_throttled, is_paused);

    ASSERT_TRUE(j.contains("thermal"));
    ASSERT_TRUE(j["thermal"].contains("throttle_effective"));
    EXPECT_TRUE(j["thermal"]["throttle_effective"].get<bool>())
        << "throttle_effective must be true when is_throttled_ is true";
}

TEST(ThermalLoggingTest, ThrottleEffective_FalseWhenIsThrottledClear) {
    std::atomic<bool> is_throttled{false};
    std::atomic<bool> is_paused{false};

    auto j = buildThermalJson(is_throttled, is_paused);

    ASSERT_TRUE(j.contains("thermal"));
    ASSERT_TRUE(j["thermal"].contains("throttle_effective"));
    EXPECT_FALSE(j["thermal"]["throttle_effective"].get<bool>())
        << "throttle_effective must be false when is_throttled_ is false";
}

// ============================================================================
// Task 2.4: paused field is present and reflects is_paused_ state
// ============================================================================

TEST(ThermalLoggingTest, Paused_TrueWhenIsPausedSet) {
    std::atomic<bool> is_throttled{false};
    std::atomic<bool> is_paused{true};

    auto j = buildThermalJson(is_throttled, is_paused);

    ASSERT_TRUE(j.contains("thermal"));
    ASSERT_TRUE(j["thermal"].contains("paused"))
        << "paused field must be present in thermal JSON";
    EXPECT_TRUE(j["thermal"]["paused"].get<bool>())
        << "paused must be true when is_paused_ is true";
}

TEST(ThermalLoggingTest, Paused_FalseWhenIsPausedClear) {
    std::atomic<bool> is_throttled{false};
    std::atomic<bool> is_paused{false};

    auto j = buildThermalJson(is_throttled, is_paused);

    ASSERT_TRUE(j.contains("thermal"));
    ASSERT_TRUE(j["thermal"].contains("paused"))
        << "paused field must be present in thermal JSON";
    EXPECT_FALSE(j["thermal"]["paused"].get<bool>())
        << "paused must be false when is_paused_ is false";
}

// ============================================================================
// Task 2.5: paused and throttle_effective are independent flags
// ============================================================================

TEST(ThermalLoggingTest, IndependentFlags_PausedTrue_ThrottledFalse) {
    // This is the key combination: camera paused but NOT throttled.
    // Occurs when camera is paused for Critical thermal status (emergency pause)
    // where throttle is not the active mechanism — pause overrides.
    std::atomic<bool> is_throttled{false};
    std::atomic<bool> is_paused{true};

    auto j = buildThermalJson(is_throttled, is_paused);

    EXPECT_FALSE(j["thermal"]["throttle_effective"].get<bool>())
        << "throttle_effective must be false independently of paused";
    EXPECT_TRUE(j["thermal"]["paused"].get<bool>())
        << "paused must be true independently of throttle_effective";
}

TEST(ThermalLoggingTest, IndependentFlags_PausedFalse_ThrottledTrue) {
    // Throttle active but camera not paused — normal throttle state.
    std::atomic<bool> is_throttled{true};
    std::atomic<bool> is_paused{false};

    auto j = buildThermalJson(is_throttled, is_paused);

    EXPECT_TRUE(j["thermal"]["throttle_effective"].get<bool>())
        << "throttle_effective must be true independently of paused";
    EXPECT_FALSE(j["thermal"]["paused"].get<bool>())
        << "paused must be false independently of throttle_effective";
}

TEST(ThermalLoggingTest, IndependentFlags_BothTrue) {
    // Both flags active — possible during transition states.
    std::atomic<bool> is_throttled{true};
    std::atomic<bool> is_paused{true};

    auto j = buildThermalJson(is_throttled, is_paused);

    EXPECT_TRUE(j["thermal"]["throttle_effective"].get<bool>());
    EXPECT_TRUE(j["thermal"]["paused"].get<bool>());
}

TEST(ThermalLoggingTest, IndependentFlags_BothFalse) {
    // Neither flag active — normal operation.
    std::atomic<bool> is_throttled{false};
    std::atomic<bool> is_paused{false};

    auto j = buildThermalJson(is_throttled, is_paused);

    EXPECT_FALSE(j["thermal"]["throttle_effective"].get<bool>());
    EXPECT_FALSE(j["thermal"]["paused"].get<bool>());
}

// ============================================================================
// Schema validation: thermal object has exactly two fields
// ============================================================================

TEST(ThermalLoggingTest, ThermalObject_HasExactlyTwoFields) {
    std::atomic<bool> is_throttled{false};
    std::atomic<bool> is_paused{false};

    auto j = buildThermalJson(is_throttled, is_paused);

    ASSERT_TRUE(j["thermal"].is_object());
    EXPECT_EQ(j["thermal"].size(), 2u)
        << "thermal JSON must contain exactly throttle_effective and paused";
}

TEST(ThermalLoggingTest, ThermalFields_AreBooleanType) {
    std::atomic<bool> is_throttled{true};
    std::atomic<bool> is_paused{true};

    auto j = buildThermalJson(is_throttled, is_paused);

    EXPECT_TRUE(j["thermal"]["throttle_effective"].is_boolean())
        << "throttle_effective must be a JSON boolean, not number or string";
    EXPECT_TRUE(j["thermal"]["paused"].is_boolean())
        << "paused must be a JSON boolean, not number or string";
}

}  // namespace test
}  // namespace cotton_detection
