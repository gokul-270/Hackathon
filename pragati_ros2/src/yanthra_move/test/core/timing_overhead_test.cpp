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
 * @file timing_overhead_test.cpp
 * @brief Timing characterization test for decomposition delegation overhead
 * @details Verifies that the extracted classes (RecoveryManager, CaptureSequence,
 *          ArucoCoordinator) add negligible overhead to the pick cycle.
 *
 *          Since the MotionController requires real hardware/ROS2 infrastructure
 *          to run a pick cycle, this test measures the delegation overhead —
 *          the cost of constructing extracted objects and calling through their
 *          methods — and asserts it is negligible (< 1ms for construction,
 *          < 10us per method call).
 *
 *          Task 1.6/7.3 — timing characterization.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>

#include "yanthra_move/core/recovery_manager.hpp"
#include "yanthra_move/core/capture_sequence.hpp"
#include "yanthra_move/core/aruco_coordinator.hpp"
#include "yanthra_move/error_recovery_types.hpp"
#include "yanthra_move/joint_move.h"

#include <chrono>
#include <memory>
#include <vector>

// =============================================================================
// PROVIDE EXTERN SYMBOLS
// =============================================================================
// These symbols are normally defined in yanthra_move_system_core.cpp.
// We define them here so the test binary links without pulling in the full
// system node (same pattern as recovery_manager_test.cpp).
// =============================================================================

namespace yanthra_move {
std::atomic<bool> simulation_mode{true};
std::atomic<bool> executor_running{false};
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor{nullptr};
std::shared_ptr<rclcpp::Node> global_node{nullptr};
std::thread executor_thread;
}  // namespace yanthra_move

// =============================================================================
// HELPER: high-resolution timing
// =============================================================================

using Clock = std::chrono::high_resolution_clock;

/// Measure wall-clock duration of a callable in microseconds.
template <typename Func>
double measureMicroseconds(Func&& fn) {
    auto start = Clock::now();
    fn();
    auto end = Clock::now();
    return std::chrono::duration<double, std::micro>(end - start).count();
}

// =============================================================================
// TEST FIXTURE
// =============================================================================

class TimingOverheadTest : public ::testing::Test {
protected:
    static rclcpp::Node::SharedPtr node_;

    static void SetUpTestSuite() {
        node_ = rclcpp::Node::make_shared("test_timing_overhead");
    }

    static void TearDownTestSuite() {
        node_.reset();
    }
};

rclcpp::Node::SharedPtr TimingOverheadTest::node_;

// =============================================================================
// 1. Construction of all 3 testable extracted objects takes < 1ms total
// =============================================================================

TEST_F(TimingOverheadTest, ConstructionOverheadUnder1ms) {
    constexpr double kMaxConstructionUs = 1000.0;  // 1ms = 1000us

    double total_us = measureMicroseconds([&]() {
        auto rm = std::make_unique<yanthra_move::core::RecoveryManager>(
            node_->get_logger());

        auto cs = std::make_unique<yanthra_move::core::CaptureSequence>(
            nullptr,  // null GPIO — simulation mode
            node_->get_logger());

        auto ac = std::make_unique<yanthra_move::core::ArucoCoordinator>(
            node_->get_logger());
    });

    EXPECT_LT(total_us, kMaxConstructionUs)
        << "Construction of RecoveryManager + CaptureSequence + ArucoCoordinator "
        << "took " << total_us << "us (limit: " << kMaxConstructionUs << "us)";
}

// =============================================================================
// 2. 100 recordMoveResult() calls take < 1ms total
// =============================================================================

TEST_F(TimingOverheadTest, RecordMoveResult100CallsUnder1ms) {
    constexpr double kMaxTotalUs = 1000.0;  // 1ms = 1000us
    constexpr int kIterations = 100;

    auto rm = std::make_unique<yanthra_move::core::RecoveryManager>(
        node_->get_logger());

    double total_us = measureMicroseconds([&]() {
        for (int i = 0; i < kIterations; ++i) {
            // Alternate between joints and results for realistic mix
            int joint_id = 3 + (i % 3);  // joints 3, 4, 5
            MoveResult result = (i % 5 == 0) ? MoveResult::SUCCESS : MoveResult::TIMEOUT;
            rm->recordMoveResult(joint_id, result);
        }
    });

    EXPECT_LT(total_us, kMaxTotalUs)
        << kIterations << " recordMoveResult() calls took " << total_us
        << "us (limit: " << kMaxTotalUs << "us)";

    // Also report per-call average for diagnostics
    double per_call_us = total_us / kIterations;
    std::cout << "[  TIMING ] recordMoveResult: " << per_call_us
              << " us/call (" << kIterations << " calls, "
              << total_us << " us total)" << std::endl;
}

// =============================================================================
// 3. RecoveryManager stat accessor overhead < 10us per call
// =============================================================================

TEST_F(TimingOverheadTest, RecoveryManagerAccessorsUnder10us) {
    constexpr double kMaxPerCallUs = 10.0;

    auto rm = std::make_unique<yanthra_move::core::RecoveryManager>(
        node_->get_logger());

    // Seed some data so accessors have something to read
    rm->recordMoveResult(3, MoveResult::TIMEOUT);
    rm->recordMoveResult(4, MoveResult::TIMEOUT);
    rm->incrementTfFailures();
    rm->recordPickAttempt();
    rm->addPickDuration(100);

    // Measure each accessor
    double us_consecutive = measureMicroseconds([&]() {
        volatile int v = rm->getConsecutiveMoveFailures(3);
        (void)v;
    });
    EXPECT_LT(us_consecutive, kMaxPerCallUs)
        << "getConsecutiveMoveFailures took " << us_consecutive << "us";

    double us_cumulative = measureMicroseconds([&]() {
        volatile int v = rm->getCumulativeMoveFailures(3);
        (void)v;
    });
    EXPECT_LT(us_cumulative, kMaxPerCallUs)
        << "getCumulativeMoveFailures took " << us_cumulative << "us";

    double us_tf = measureMicroseconds([&]() {
        volatile int v = rm->getTfFailureCount();
        (void)v;
    });
    EXPECT_LT(us_tf, kMaxPerCallUs)
        << "getTfFailureCount took " << us_tf << "us";

    double us_avg_pick = measureMicroseconds([&]() {
        volatile double v = rm->getAveragePickDurationMs();
        (void)v;
    });
    EXPECT_LT(us_avg_pick, kMaxPerCallUs)
        << "getAveragePickDurationMs took " << us_avg_pick << "us";

    double us_picks = measureMicroseconds([&]() {
        volatile int v = rm->getTotalPicksAttempted();
        (void)v;
    });
    EXPECT_LT(us_picks, kMaxPerCallUs)
        << "getTotalPicksAttempted took " << us_picks << "us";
}

// =============================================================================
// 4. CaptureSequence accessors overhead < 10us per call
// =============================================================================

TEST_F(TimingOverheadTest, CaptureSequenceAccessorsUnder10us) {
    constexpr double kMaxPerCallUs = 10.0;

    auto cs = std::make_unique<yanthra_move::core::CaptureSequence>(
        nullptr, node_->get_logger());

    double us_ee_on = measureMicroseconds([&]() {
        volatile bool v = cs->isEeCurrentlyOn();
        (void)v;
    });
    EXPECT_LT(us_ee_on, kMaxPerCallUs)
        << "isEeCurrentlyOn took " << us_ee_on << "us";

    double us_comp_on = measureMicroseconds([&]() {
        volatile bool v = cs->isCompressorCurrentlyOn();
        (void)v;
    });
    EXPECT_LT(us_comp_on, kMaxPerCallUs)
        << "isCompressorCurrentlyOn took " << us_comp_on << "us";

    double us_ee_count = measureMicroseconds([&]() {
        volatile int v = cs->getEeActivationCount();
        (void)v;
    });
    EXPECT_LT(us_ee_count, kMaxPerCallUs)
        << "getEeActivationCount took " << us_ee_count << "us";

    double us_comp_count = measureMicroseconds([&]() {
        volatile int v = cs->getCompressorActivationCount();
        (void)v;
    });
    EXPECT_LT(us_comp_count, kMaxPerCallUs)
        << "getCompressorActivationCount took " << us_comp_count << "us";
}

// =============================================================================
// 5. ArucoCoordinator state checks overhead < 10us per call
// =============================================================================

TEST_F(TimingOverheadTest, ArucoCoordinatorStateChecksUnder10us) {
    constexpr double kMaxPerCallUs = 10.0;

    auto ac = std::make_unique<yanthra_move::core::ArucoCoordinator>(
        node_->get_logger());

    double us_retrigger = measureMicroseconds([&]() {
        volatile bool v = ac->isReTriggerEnabled();
        (void)v;
    });
    EXPECT_LT(us_retrigger, kMaxPerCallUs)
        << "isReTriggerEnabled took " << us_retrigger << "us";

    double us_camera = measureMicroseconds([&]() {
        volatile bool v = ac->isCameraAvailable();
        (void)v;
    });
    EXPECT_LT(us_camera, kMaxPerCallUs)
        << "isCameraAvailable took " << us_camera << "us";

    double us_offset = measureMicroseconds([&]() {
        volatile double v = ac->getCurrentJ4ScanOffset();
        (void)v;
    });
    EXPECT_LT(us_offset, kMaxPerCallUs)
        << "getCurrentJ4ScanOffset took " << us_offset << "us";

    double us_stats = measureMicroseconds([&]() {
        const auto& stats = ac->getMultiPositionStats();
        volatile int v = stats.total_scans;
        (void)v;
    });
    EXPECT_LT(us_stats, kMaxPerCallUs)
        << "getMultiPositionStats took " << us_stats << "us";
}

// =============================================================================
// 6. RecoveryManager stat incrementers overhead < 10us per call
// =============================================================================

TEST_F(TimingOverheadTest, RecoveryManagerIncrementersUnder10us) {
    constexpr double kMaxPerCallUs = 10.0;

    auto rm = std::make_unique<yanthra_move::core::RecoveryManager>(
        node_->get_logger());

    double us_tf = measureMicroseconds([&]() {
        rm->incrementTfFailures();
    });
    EXPECT_LT(us_tf, kMaxPerCallUs)
        << "incrementTfFailures took " << us_tf << "us";

    double us_coord = measureMicroseconds([&]() {
        rm->incrementInvalidCoordinates();
    });
    EXPECT_LT(us_coord, kMaxPerCallUs)
        << "incrementInvalidCoordinates took " << us_coord << "us";

    double us_jl = measureMicroseconds([&]() {
        rm->incrementJointLimitFailures();
    });
    EXPECT_LT(us_jl, kMaxPerCallUs)
        << "incrementJointLimitFailures took " << us_jl << "us";

    double us_pick = measureMicroseconds([&]() {
        rm->recordPickAttempt();
    });
    EXPECT_LT(us_pick, kMaxPerCallUs)
        << "recordPickAttempt took " << us_pick << "us";

    double us_dur = measureMicroseconds([&]() {
        rm->addPickDuration(50);
    });
    EXPECT_LT(us_dur, kMaxPerCallUs)
        << "addPickDuration took " << us_dur << "us";
}

// =============================================================================
// 7. ArucoCoordinator setter overhead < 10us per call
// =============================================================================

TEST_F(TimingOverheadTest, ArucoCoordinatorSettersUnder10us) {
    constexpr double kMaxPerCallUs = 10.0;

    auto ac = std::make_unique<yanthra_move::core::ArucoCoordinator>(
        node_->get_logger());

    double us_retrigger = measureMicroseconds([&]() {
        ac->setReTriggerEnabled(true);
    });
    EXPECT_LT(us_retrigger, kMaxPerCallUs)
        << "setReTriggerEnabled took " << us_retrigger << "us";

    double us_reset = measureMicroseconds([&]() {
        ac->resetDetectionState();
    });
    EXPECT_LT(us_reset, kMaxPerCallUs)
        << "resetDetectionState took " << us_reset << "us";

    double us_detect_cb = measureMicroseconds([&]() {
        ac->setDetectionCallback([]() {
            return std::nullopt;
        });
    });
    EXPECT_LT(us_detect_cb, kMaxPerCallUs)
        << "setDetectionCallback took " << us_detect_cb << "us";
}

// =============================================================================
// 8. CaptureSequence mark/state toggle overhead < 10us per call
// =============================================================================

TEST_F(TimingOverheadTest, CaptureSequenceMarkToggleUnder10us) {
    constexpr double kMaxPerCallUs = 10.0;

    auto cs = std::make_unique<yanthra_move::core::CaptureSequence>(
        nullptr, node_->get_logger());

    double us_mark_active = measureMicroseconds([&]() {
        cs->markEeActive();
    });
    EXPECT_LT(us_mark_active, kMaxPerCallUs)
        << "markEeActive took " << us_mark_active << "us";

    double us_mark_inactive = measureMicroseconds([&]() {
        cs->markEeInactive();
    });
    EXPECT_LT(us_mark_inactive, kMaxPerCallUs)
        << "markEeInactive took " << us_mark_inactive << "us";

    double us_enable = measureMicroseconds([&]() {
        cs->setEndEffectorEnabled(true);
    });
    EXPECT_LT(us_enable, kMaxPerCallUs)
        << "setEndEffectorEnabled took " << us_enable << "us";

    double us_j5_cb = measureMicroseconds([&]() {
        cs->setJ5PositionCallback([]() -> double { return 0.0; });
    });
    EXPECT_LT(us_j5_cb, kMaxPerCallUs)
        << "setJ5PositionCallback took " << us_j5_cb << "us";
}

// =============================================================================
// 9. Aggregate: full delegation round-trip (construct + 100 calls + read)
//    should be < 2ms total — proves decomposition adds negligible overhead
//    to a pick cycle that typically takes 2000-5000ms.
// =============================================================================

TEST_F(TimingOverheadTest, FullDelegationRoundTripUnder2ms) {
    constexpr double kMaxTotalUs = 2000.0;  // 2ms = 2000us

    double total_us = measureMicroseconds([&]() {
        // Phase 1: Construct all 3 objects
        auto rm = std::make_unique<yanthra_move::core::RecoveryManager>(
            node_->get_logger());
        auto cs = std::make_unique<yanthra_move::core::CaptureSequence>(
            nullptr, node_->get_logger());
        auto ac = std::make_unique<yanthra_move::core::ArucoCoordinator>(
            node_->get_logger());

        // Phase 2: Simulate delegation calls during a pick cycle
        rm->recordPickAttempt();
        for (int i = 0; i < 100; ++i) {
            rm->recordMoveResult(3 + (i % 3), MoveResult::SUCCESS);
        }
        rm->recordPickSuccess();
        rm->addPickDuration(150);

        // Phase 3: Read state (as MotionController would for timing JSON)
        volatile int v1 = rm->getTotalPicksAttempted();
        volatile int v2 = rm->getTotalPicksSuccessful();
        volatile double v3 = rm->getAveragePickDurationMs();
        volatile bool v4 = cs->isEeCurrentlyOn();
        volatile bool v5 = cs->isCompressorCurrentlyOn();
        volatile bool v6 = ac->isReTriggerEnabled();
        volatile double v7 = ac->getCurrentJ4ScanOffset();
        (void)v1; (void)v2; (void)v3; (void)v4; (void)v5; (void)v6; (void)v7;
    });

    EXPECT_LT(total_us, kMaxTotalUs)
        << "Full delegation round-trip took " << total_us
        << "us (limit: " << kMaxTotalUs << "us). "
        << "A pick cycle is typically 2000-5000ms, so this is < 0.1% overhead.";

    std::cout << "[  TIMING ] Full delegation round-trip: " << total_us
              << " us (" << (total_us / 1000.0) << " ms)" << std::endl;
}

// =============================================================================
// main -- initialize / shutdown rclcpp around the test run
// =============================================================================

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int ret = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return ret;
}
