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

/**
 * @file capture_sequence_test.cpp
 * @brief RED tests for CaptureSequence — EE/compressor GPIO orchestration
 * @details Tests dynamic/sequential EE activation, compressor burst, watchdog
 *          accessors, activation counters, master enable flag, and graceful
 *          degradation when GPIO is null (simulation mode) or J5 position
 *          data is unavailable.
 *
 * This is a RED test file: CaptureSequence does not exist yet.
 * The header will be created at yanthra_move/core/capture_sequence.hpp.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>

// Header under test — does NOT exist yet (RED)
#include "yanthra_move/core/capture_sequence.hpp"

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <thread>

// ---------------------------------------------------------------------------
// Provide extern symbols that yanthra_move sources reference.
// These are normally defined in yanthra_move_system_core.cpp.
// ---------------------------------------------------------------------------
namespace yanthra_move {
std::atomic<bool> simulation_mode{true};
std::shared_ptr<rclcpp::Node> global_node = nullptr;
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor = nullptr;
std::atomic<bool> executor_running{false};
std::thread executor_thread;
}  // namespace yanthra_move

using yanthra_move::core::CaptureSequence;

// ---------------------------------------------------------------------------
// Test fixture
// ---------------------------------------------------------------------------
class CaptureSequenceTest : public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        if (!rclcpp::ok()) {
            rclcpp::init(0, nullptr);
        }
    }

    static void TearDownTestSuite()
    {
        if (rclcpp::ok()) {
            rclcpp::shutdown();
        }
    }

    void SetUp() override
    {
        // Use nullptr for GPIO — simulation mode means GPIO calls are no-ops
        gpio_ = nullptr;
        logger_ = rclcpp::get_logger("capture_sequence_test");

        cs_ = std::make_unique<CaptureSequence>(gpio_, logger_);

        // Default J5 position callback: returns 0.0 (home)
        j5_position_ = 0.0;
        cs_->setJ5PositionCallback([this]() -> double { return j5_position_; });
    }

    void TearDown() override
    {
        cs_.reset();
    }

    // Helpers
    void setJ5Position(double pos) { j5_position_ = pos; }

    std::shared_ptr<motor_control_ros2::GPIOControlFunctions> gpio_;
    rclcpp::Logger logger_{rclcpp::get_logger("capture_sequence_test")};
    std::unique_ptr<CaptureSequence> cs_;
    double j5_position_{0.0};
};

// ===========================================================================
// 1. Constructor creates instance without throwing (simulation mode, null GPIO)
// ===========================================================================
TEST_F(CaptureSequenceTest, ConstructorDoesNotThrow)
{
    EXPECT_NO_THROW({
        CaptureSequence cs(nullptr, rclcpp::get_logger("ctor_test"));
    });
}

// ===========================================================================
// 2. Dynamic EE activation: activates when J5 within trigger distance
// ===========================================================================
TEST_F(CaptureSequenceTest, DynamicEeActivation_ActivatesWhenJ5WithinTriggerDistance)
{
    // Target J5 position for cotton capture
    const double target_j5 = 2.0;       // radians
    const float ee_start_distance = 0.3f; // activate when within 0.3 rad

    // Place J5 within trigger distance of target
    setJ5Position(target_j5 - 0.1);  // 0.1 rad away, within 0.3 threshold

    bool result = cs_->activateEE(target_j5, ee_start_distance, /*use_dynamic_prestart=*/true);

    EXPECT_TRUE(result) << "activateEE should return true when J5 is within trigger distance";
    EXPECT_TRUE(cs_->isEeCurrentlyOn()) << "EE should be on after successful activation";
}

// ===========================================================================
// 3. Dynamic EE deactivation on retreat: deactivates past stop distance
// ===========================================================================
TEST_F(CaptureSequenceTest, DeactivateOnRetreat_DeactivatesWhenJ5PastStopDistance)
{
    // First activate EE
    const double target_j5 = 2.0;
    const float ee_start_distance = 0.5f;
    setJ5Position(target_j5 - 0.1);
    cs_->activateEE(target_j5, ee_start_distance, true);
    ASSERT_TRUE(cs_->isEeCurrentlyOn()) << "Precondition: EE must be on";

    // Now simulate retreat — J5 has pulled back past stop distance
    const double target_j5_retract = 1.0;
    const float ee_stop_distance = 0.2f;
    setJ5Position(target_j5_retract + 0.3);  // past the stop threshold

    bool result = cs_->deactivateOnRetreat(target_j5_retract, ee_stop_distance);

    EXPECT_TRUE(result) << "deactivateOnRetreat should return true when past stop distance";
    EXPECT_FALSE(cs_->isEeCurrentlyOn()) << "EE should be off after retreat deactivation";
}

// ===========================================================================
// 4. Sequential EE activation: activates for duration then deactivates
// ===========================================================================
TEST_F(CaptureSequenceTest, SequentialActivation_ActivatesForDurationThenDeactivates)
{
    // Short duration for test speed (50ms)
    const float duration_ms = 50.0f;

    bool result = cs_->activateEESequential(duration_ms);

    EXPECT_TRUE(result) << "activateEESequential should return true on success";
    // After the call returns, EE should be deactivated (method is blocking)
    EXPECT_FALSE(cs_->isEeCurrentlyOn())
        << "EE should be off after sequential activation completes";
}

// ===========================================================================
// 5. EE stays off when master enable flag is false
// ===========================================================================
TEST_F(CaptureSequenceTest, MasterEnableFlag_PreventsActivationWhenDisabled)
{
    cs_->setEndEffectorEnabled(false);

    const double target_j5 = 2.0;
    const float ee_start_distance = 0.5f;
    setJ5Position(target_j5 - 0.1);

    bool result = cs_->activateEE(target_j5, ee_start_distance, true);

    EXPECT_FALSE(result) << "activateEE should return false when EE is disabled";
    EXPECT_FALSE(cs_->isEeCurrentlyOn()) << "EE must stay off when master enable is false";
}

TEST_F(CaptureSequenceTest, MasterEnableFlag_PreventsSequentialActivationWhenDisabled)
{
    cs_->setEndEffectorEnabled(false);

    bool result = cs_->activateEESequential(100.0f);

    EXPECT_FALSE(result)
        << "activateEESequential should return false when EE is disabled";
    EXPECT_FALSE(cs_->isEeCurrentlyOn())
        << "EE must stay off when master enable is false (sequential)";
}

// ===========================================================================
// 6. Compressor burst: activates for specified duration
// ===========================================================================
TEST_F(CaptureSequenceTest, CompressorBurst_ActivatesForDuration)
{
    const double duration_sec = 0.05;  // 50ms for test speed

    // Should not throw even with null GPIO (simulation mode)
    EXPECT_NO_THROW(cs_->compressorBurst(duration_sec));

    // After blocking call returns, compressor should be off
    EXPECT_FALSE(cs_->isCompressorCurrentlyOn())
        << "Compressor should be off after burst completes";
}

// ===========================================================================
// 7. Watchdog accessors: initial state
// ===========================================================================
TEST_F(CaptureSequenceTest, WatchdogAccessors_InitialStateIsOff)
{
    // Fresh instance — nothing activated yet
    EXPECT_FALSE(cs_->isEeCurrentlyOn())
        << "EE should be off initially";
    EXPECT_FALSE(cs_->isCompressorCurrentlyOn())
        << "Compressor should be off initially";
}

TEST_F(CaptureSequenceTest, WatchdogAccessors_EeOnSinceUpdatesOnActivation)
{
    auto before = std::chrono::steady_clock::now();

    const double target_j5 = 2.0;
    setJ5Position(target_j5 - 0.1);
    cs_->activateEE(target_j5, 0.5f, true);

    auto after = std::chrono::steady_clock::now();

    ASSERT_TRUE(cs_->isEeCurrentlyOn());
    auto ee_on_since = cs_->getEeOnSince();

    // The timestamp should be between before and after
    EXPECT_GE(ee_on_since, before)
        << "EE on-since timestamp should be >= time before activation";
    EXPECT_LE(ee_on_since, after)
        << "EE on-since timestamp should be <= time after activation";
}

TEST_F(CaptureSequenceTest, WatchdogAccessors_CompressorOnSinceAvailableDuringBurst)
{
    // We need to check compressor state during the burst, not after.
    // Since compressorBurst is blocking, we run it in a thread and
    // check the state while it's active.
    const double duration_sec = 0.2;  // 200ms to give us time to check

    std::atomic<bool> was_on{false};
    std::atomic<bool> burst_started{false};

    std::thread burst_thread([&]() {
        burst_started = true;
        cs_->compressorBurst(duration_sec);
    });

    // Wait for burst to start
    while (!burst_started) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    // Small delay to let the compressor actually turn on
    std::this_thread::sleep_for(std::chrono::milliseconds(20));

    if (cs_->isCompressorCurrentlyOn()) {
        was_on = true;
    }

    burst_thread.join();

    EXPECT_TRUE(was_on)
        << "Compressor should have been on during the burst window";
}

// ===========================================================================
// 8. Activation counters increment correctly
// ===========================================================================
TEST_F(CaptureSequenceTest, ActivationCounters_IncrementOnEeActivation)
{
    EXPECT_EQ(cs_->getEeActivationCount(), 0) << "Counter should start at 0";

    const double target_j5 = 2.0;
    setJ5Position(target_j5 - 0.1);

    cs_->activateEE(target_j5, 0.5f, true);
    EXPECT_EQ(cs_->getEeActivationCount(), 1);

    // Deactivate then activate again
    cs_->turnOffEndEffector();
    cs_->activateEE(target_j5, 0.5f, true);
    EXPECT_EQ(cs_->getEeActivationCount(), 2);
}

TEST_F(CaptureSequenceTest, ActivationCounters_IncrementOnCompressorBurst)
{
    EXPECT_EQ(cs_->getCompressorActivationCount(), 0) << "Counter should start at 0";

    cs_->compressorBurst(0.01);  // 10ms burst
    EXPECT_EQ(cs_->getCompressorActivationCount(), 1);

    cs_->compressorBurst(0.01);
    EXPECT_EQ(cs_->getCompressorActivationCount(), 2);
}

// ===========================================================================
// 9. turnOffEndEffector / turnOffCompressor set state to off
// ===========================================================================
TEST_F(CaptureSequenceTest, TurnOffEndEffector_SetsStateToOff)
{
    // Activate first
    const double target_j5 = 2.0;
    setJ5Position(target_j5 - 0.1);
    cs_->activateEE(target_j5, 0.5f, true);
    ASSERT_TRUE(cs_->isEeCurrentlyOn()) << "Precondition: EE must be on";

    cs_->turnOffEndEffector();

    EXPECT_FALSE(cs_->isEeCurrentlyOn())
        << "EE should be off after turnOffEndEffector()";
}

TEST_F(CaptureSequenceTest, TurnOffCompressor_SetsStateToOff)
{
    // Start a long burst in a thread, then force it off
    const double long_duration = 5.0;  // 5s — we'll cut it short

    std::thread burst_thread([&]() {
        cs_->compressorBurst(long_duration);
    });

    // Wait for compressor to start
    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    cs_->turnOffCompressor();

    EXPECT_FALSE(cs_->isCompressorCurrentlyOn())
        << "Compressor should be off after turnOffCompressor()";

    burst_thread.join();
}

// ===========================================================================
// 10. Simulation mode: graceful handling when GPIO is null
// ===========================================================================
TEST_F(CaptureSequenceTest, NullGpio_ActivateEeDoesNotCrash)
{
    // cs_ already has nullptr GPIO
    const double target_j5 = 2.0;
    setJ5Position(target_j5 - 0.1);

    EXPECT_NO_THROW(cs_->activateEE(target_j5, 0.5f, true))
        << "activateEE must not crash with null GPIO (simulation mode)";
}

TEST_F(CaptureSequenceTest, NullGpio_CompressorBurstDoesNotCrash)
{
    EXPECT_NO_THROW(cs_->compressorBurst(0.01))
        << "compressorBurst must not crash with null GPIO (simulation mode)";
}

TEST_F(CaptureSequenceTest, NullGpio_TurnOffMethodsDoNotCrash)
{
    EXPECT_NO_THROW(cs_->turnOffEndEffector())
        << "turnOffEndEffector must not crash with null GPIO";
    EXPECT_NO_THROW(cs_->turnOffCompressor())
        << "turnOffCompressor must not crash with null GPIO";
}

// ===========================================================================
// 11. Position data loss: J5 callback returns -1.0 (unavailable) —
//     EE should use timeout fallback rather than hanging
// ===========================================================================
TEST_F(CaptureSequenceTest, J5PositionUnavailable_UsesTimeoutFallback)
{
    // Set J5 callback to return -1.0 (position unavailable sentinel)
    cs_->setJ5PositionCallback([]() -> double { return -1.0; });

    const double target_j5 = 2.0;
    const float ee_start_distance = 0.5f;

    auto start = std::chrono::steady_clock::now();
    bool result = cs_->activateEE(target_j5, ee_start_distance, /*use_dynamic_prestart=*/true);
    auto elapsed = std::chrono::steady_clock::now() - start;

    // The method should return within a reasonable timeout (not hang forever).
    // We allow up to 5 seconds; the actual timeout should be much shorter.
    EXPECT_LT(elapsed, std::chrono::seconds(5))
        << "activateEE must not hang when J5 position is unavailable";

    // The method should still activate (fallback behavior) or return false gracefully.
    // Either outcome is acceptable — the key requirement is no hang.
    // If it activated via fallback, the counter should reflect it.
    if (result) {
        EXPECT_GE(cs_->getEeActivationCount(), 1)
            << "If fallback activated EE, counter should increment";
    }
}
