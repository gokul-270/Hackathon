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
 * @file recovery_manager_test.cpp
 * @brief RED tests for RecoveryManager — pure C++ failure/stat tracker
 * @details Tests construction, per-joint failure counters, threshold-based
 *          callback escalation, session statistics, and thread-safety.
 *
 *          This is a RED test file: the header yanthra_move/core/recovery_manager.hpp
 *          and its implementation do not exist yet.  The tests must compile but
 *          will FAIL to link until the class is created.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>

#include "yanthra_move/core/recovery_manager.hpp"
#include "yanthra_move/error_recovery_types.hpp"
#include "yanthra_move/joint_move.h"

#include <atomic>
#include <functional>
#include <thread>
#include <vector>

// =============================================================================
// PROVIDE EXTERN SYMBOLS
// =============================================================================
// These symbols are normally defined in yanthra_move_system_core.cpp.
// We define them here so the test binary links without pulling in the full
// system node (same pattern as test_motion_controller.cpp).
// =============================================================================

namespace yanthra_move {
std::atomic<bool> simulation_mode{true};
std::atomic<bool> executor_running{false};
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor{nullptr};
std::shared_ptr<rclcpp::Node> global_node{nullptr};
std::thread executor_thread;
}  // namespace yanthra_move

// =============================================================================
// TEST FIXTURE
// =============================================================================

class RecoveryManagerTest : public ::testing::Test {
protected:
    static rclcpp::Node::SharedPtr node_;

    static void SetUpTestSuite() {
        node_ = rclcpp::Node::make_shared("test_recovery_manager");
    }

    static void TearDownTestSuite() {
        node_.reset();
    }

    /// Create a fresh RecoveryManager for each test.
    std::unique_ptr<yanthra_move::core::RecoveryManager> makeManager() {
        return std::make_unique<yanthra_move::core::RecoveryManager>(
            node_->get_logger());
    }
};

// Static member definition
rclcpp::Node::SharedPtr RecoveryManagerTest::node_;

// =============================================================================
// 1. Constructor creates instance without throwing
// =============================================================================

TEST_F(RecoveryManagerTest, ConstructsWithoutThrowing) {
    EXPECT_NO_THROW({
        auto mgr = makeManager();
    });
}

// =============================================================================
// 2. Initial counters are all zero
// =============================================================================

TEST_F(RecoveryManagerTest, InitialCountersAreZero) {
    auto mgr = makeManager();

    // Per-joint move failure counters
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(4), 0);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(5), 0);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(3), 0);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(4), 0);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(5), 0);

    // TF, coordinate, joint-limit, feedback failure counters
    EXPECT_EQ(mgr->getTfFailureCount(), 0);
    EXPECT_EQ(mgr->getInvalidCoordinateCount(), 0);
    EXPECT_EQ(mgr->getJointLimitFailureCount(), 0);
    EXPECT_EQ(mgr->getPositionFeedbackFailureCount(), 0);

    // EE / compressor activation counters
    EXPECT_EQ(mgr->getEeActivationCount(), 0);
    EXPECT_EQ(mgr->getCompressorActivationCount(), 0);

    // Session stats
    EXPECT_EQ(mgr->getTotalPicksAttempted(), 0);
    EXPECT_EQ(mgr->getTotalPicksSuccessful(), 0);
    EXPECT_EQ(mgr->getTotalPicksTimedOut(), 0);
    EXPECT_DOUBLE_EQ(mgr->getAveragePickDurationMs(), 0.0);
}

// =============================================================================
// 3. recordMoveResult(3, SUCCESS) resets consecutive counter for J3 only
// =============================================================================

TEST_F(RecoveryManagerTest, SuccessResetsConsecutiveForTargetJointOnly) {
    auto mgr = makeManager();

    // Accumulate failures on J3 and J4
    mgr->recordMoveResult(3, MoveResult::TIMEOUT);
    mgr->recordMoveResult(3, MoveResult::TIMEOUT);
    mgr->recordMoveResult(4, MoveResult::TIMEOUT);

    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 2);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(4), 1);

    // SUCCESS on J3 resets J3 consecutive only
    mgr->recordMoveResult(3, MoveResult::SUCCESS);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(3), 2);  // cumulative untouched
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(4), 1);  // J4 untouched
}

// =============================================================================
// 4. recordMoveResult(3, TIMEOUT) increments both consecutive and cumulative
// =============================================================================

TEST_F(RecoveryManagerTest, TimeoutIncrementsBothCounters) {
    auto mgr = makeManager();

    mgr->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 1);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(3), 1);

    mgr->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 2);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(3), 2);

    mgr->recordMoveResult(3, MoveResult::ERROR);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 3);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(3), 3);
}

// =============================================================================
// 5. recordMoveResult(99, ERROR) for unknown joint_id does nothing (no crash)
// =============================================================================

TEST_F(RecoveryManagerTest, UnknownJointIdDoesNotCrash) {
    auto mgr = makeManager();

    EXPECT_NO_THROW(mgr->recordMoveResult(99, MoveResult::ERROR));
    EXPECT_NO_THROW(mgr->recordMoveResult(0, MoveResult::TIMEOUT));
    EXPECT_NO_THROW(mgr->recordMoveResult(-1, MoveResult::TIMEOUT));
    EXPECT_NO_THROW(mgr->recordMoveResult(2, MoveResult::ERROR));
    EXPECT_NO_THROW(mgr->recordMoveResult(6, MoveResult::SUCCESS));

    // Getters for unknown joints return 0
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(99), 0);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(99), 0);

    // Valid joints remain untouched
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(4), 0);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(5), 0);
}

// =============================================================================
// 6. Threshold callback: fires when consecutive failures reach threshold
// =============================================================================

TEST_F(RecoveryManagerTest, CallbackFiresAtThreshold) {
    auto mgr = makeManager();

    int callback_count = 0;
    yanthra_move::FailureType captured_type{};
    int captured_joint_id = 0;

    mgr->setFailureCallback(
        [&](yanthra_move::FailureType type,
            const yanthra_move::FailureContext& ctx) {
            ++callback_count;
            captured_type = type;
            captured_joint_id = ctx.joint_id;
        });

    mgr->setConsecutiveFailureThreshold(3);

    // 1st and 2nd failure: below threshold, no callback
    mgr->recordMoveResult(4, MoveResult::TIMEOUT);
    mgr->recordMoveResult(4, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 0);

    // 3rd failure: threshold reached, callback fires
    mgr->recordMoveResult(4, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 1);
    EXPECT_EQ(captured_type, yanthra_move::FailureType::MOTOR_TIMEOUT);
    EXPECT_EQ(captured_joint_id, 4);
}

// =============================================================================
// 7. Threshold callback: does NOT fire below threshold
// =============================================================================

TEST_F(RecoveryManagerTest, CallbackDoesNotFireBelowThreshold) {
    auto mgr = makeManager();

    int callback_count = 0;
    mgr->setFailureCallback(
        [&](yanthra_move::FailureType,
            const yanthra_move::FailureContext&) {
            ++callback_count;
        });

    mgr->setConsecutiveFailureThreshold(5);

    // Record 4 failures (below threshold of 5)
    for (int i = 0; i < 4; ++i) {
        mgr->recordMoveResult(3, MoveResult::TIMEOUT);
    }
    EXPECT_EQ(callback_count, 0);
}

// =============================================================================
// 8. Threshold callback: null callback doesn't crash when threshold exceeded
// =============================================================================

TEST_F(RecoveryManagerTest, NullCallbackDoesNotCrashWhenThresholdExceeded) {
    auto mgr = makeManager();

    // Do NOT set any callback — leave it as default (null)
    mgr->setConsecutiveFailureThreshold(1);

    // This must not crash even though threshold is exceeded and callback is null
    EXPECT_NO_THROW({
        mgr->recordMoveResult(3, MoveResult::TIMEOUT);
        mgr->recordMoveResult(3, MoveResult::TIMEOUT);
        mgr->recordMoveResult(3, MoveResult::ERROR);
    });

    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 3);
}

// =============================================================================
// 9. Per-joint tracking is independent (J3 failure doesn't affect J4/J5)
// =============================================================================

TEST_F(RecoveryManagerTest, PerJointTrackingIsIndependent) {
    auto mgr = makeManager();

    mgr->recordMoveResult(3, MoveResult::ERROR);
    mgr->recordMoveResult(3, MoveResult::ERROR);
    mgr->recordMoveResult(4, MoveResult::TIMEOUT);
    mgr->recordMoveResult(5, MoveResult::ERROR);
    mgr->recordMoveResult(5, MoveResult::ERROR);
    mgr->recordMoveResult(5, MoveResult::ERROR);

    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 2);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(4), 1);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(5), 3);

    EXPECT_EQ(mgr->getCumulativeMoveFailures(3), 2);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(4), 1);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(5), 3);

    // Success on J3 resets only J3 consecutive
    mgr->recordMoveResult(3, MoveResult::SUCCESS);
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mgr->getCumulativeMoveFailures(3), 2);   // cumulative unchanged
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(4), 1);   // J4 unaffected
    EXPECT_EQ(mgr->getConsecutiveMoveFailures(5), 3);   // J5 unaffected
}

// =============================================================================
// 10. Thread-safe reads: concurrent reads and writes don't crash (smoke test)
// =============================================================================

TEST_F(RecoveryManagerTest, ConcurrentReadsAndWritesDoNotCrash) {
    auto mgr = makeManager();

    mgr->setConsecutiveFailureThreshold(100);  // high threshold to avoid callback noise

    std::atomic<bool> stop{false};
    constexpr int kNumWriterThreads = 3;
    constexpr int kNumReaderThreads = 3;

    std::vector<std::thread> threads;

    // Writer threads: hammer recordMoveResult on different joints
    for (int t = 0; t < kNumWriterThreads; ++t) {
        int joint_id = 3 + t;  // joints 3, 4, 5
        threads.emplace_back([&mgr, &stop, joint_id]() {
            int i = 0;
            while (!stop.load(std::memory_order_relaxed)) {
                if (i % 5 == 0) {
                    mgr->recordMoveResult(joint_id, MoveResult::SUCCESS);
                } else {
                    mgr->recordMoveResult(joint_id, MoveResult::TIMEOUT);
                }
                ++i;
            }
        });
    }

    // Reader threads: hammer getters
    for (int t = 0; t < kNumReaderThreads; ++t) {
        int joint_id = 3 + t;
        threads.emplace_back([&mgr, &stop, joint_id]() {
            while (!stop.load(std::memory_order_relaxed)) {
                volatile int c = mgr->getConsecutiveMoveFailures(joint_id);
                volatile int d = mgr->getCumulativeMoveFailures(joint_id);
                (void)c;
                (void)d;
            }
        });
    }

    // Let them run briefly
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    stop.store(true, std::memory_order_relaxed);

    for (auto& th : threads) {
        th.join();
    }

    // If we get here without TSAN errors or crashes, the test passes
    SUCCEED();
}

// =============================================================================
// 11. Session stats: getAveragePickDurationMs() returns 0 when no attempts
// =============================================================================

TEST_F(RecoveryManagerTest, AveragePickDurationZeroWithNoAttempts) {
    auto mgr = makeManager();
    EXPECT_DOUBLE_EQ(mgr->getAveragePickDurationMs(), 0.0);
}

// =============================================================================
// 12. Session stats: getAveragePickDurationMs() computes correctly with data
// =============================================================================

TEST_F(RecoveryManagerTest, AveragePickDurationComputesCorrectly) {
    auto mgr = makeManager();

    // Record 3 pick attempts with durations 100, 200, 300 ms
    mgr->recordPickAttempt();
    mgr->addPickDuration(100);
    mgr->recordPickAttempt();
    mgr->addPickDuration(200);
    mgr->recordPickAttempt();
    mgr->addPickDuration(300);

    // Average should be (100 + 200 + 300) / 3 = 200.0
    EXPECT_DOUBLE_EQ(mgr->getAveragePickDurationMs(), 200.0);
    EXPECT_EQ(mgr->getTotalPicksAttempted(), 3);
}

// =============================================================================
// ADDITIONAL: Stat incrementers and accessors
// =============================================================================

TEST_F(RecoveryManagerTest, TfFailureIncrements) {
    auto mgr = makeManager();
    mgr->incrementTfFailures();
    mgr->incrementTfFailures();
    EXPECT_EQ(mgr->getTfFailureCount(), 2);
}

TEST_F(RecoveryManagerTest, InvalidCoordinateIncrements) {
    auto mgr = makeManager();
    mgr->incrementInvalidCoordinates();
    EXPECT_EQ(mgr->getInvalidCoordinateCount(), 1);
}

TEST_F(RecoveryManagerTest, JointLimitFailureIncrements) {
    auto mgr = makeManager();
    mgr->incrementJointLimitFailures();
    mgr->incrementJointLimitFailures();
    mgr->incrementJointLimitFailures();
    EXPECT_EQ(mgr->getJointLimitFailureCount(), 3);
}

TEST_F(RecoveryManagerTest, PositionFeedbackFailurePerJoint) {
    auto mgr = makeManager();
    mgr->incrementPositionFeedbackFailure(3);
    mgr->incrementPositionFeedbackFailure(3);
    mgr->incrementPositionFeedbackFailure(5);

    // Total across all joints
    EXPECT_EQ(mgr->getPositionFeedbackFailureCount(), 3);
}

TEST_F(RecoveryManagerTest, EeActivationIncrements) {
    auto mgr = makeManager();
    mgr->incrementEeActivations();
    mgr->incrementEeActivations();
    EXPECT_EQ(mgr->getEeActivationCount(), 2);
}

TEST_F(RecoveryManagerTest, CompressorActivationIncrements) {
    auto mgr = makeManager();
    mgr->incrementCompressorActivations();
    EXPECT_EQ(mgr->getCompressorActivationCount(), 1);
}

TEST_F(RecoveryManagerTest, PickSuccessAndTimeoutTracking) {
    auto mgr = makeManager();
    mgr->recordPickAttempt();
    mgr->recordPickSuccess();
    mgr->recordPickAttempt();
    mgr->recordPickTimeout();

    EXPECT_EQ(mgr->getTotalPicksAttempted(), 2);
    EXPECT_EQ(mgr->getTotalPicksSuccessful(), 1);
    EXPECT_EQ(mgr->getTotalPicksTimedOut(), 1);
}

TEST_F(RecoveryManagerTest, CallbackDistinguishesTimeoutVsError) {
    auto mgr = makeManager();

    yanthra_move::FailureType captured_type{};
    mgr->setFailureCallback(
        [&](yanthra_move::FailureType type,
            const yanthra_move::FailureContext&) {
            captured_type = type;
        });

    mgr->setConsecutiveFailureThreshold(1);

    mgr->recordMoveResult(3, MoveResult::ERROR);
    EXPECT_EQ(captured_type, yanthra_move::FailureType::MOTOR_ERROR);

    // Reset consecutive via success, then test TIMEOUT
    mgr->recordMoveResult(3, MoveResult::SUCCESS);
    mgr->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(captured_type, yanthra_move::FailureType::MOTOR_TIMEOUT);
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
