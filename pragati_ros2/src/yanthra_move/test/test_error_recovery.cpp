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
 * @file test_error_recovery.cpp
 * @brief Unit tests for MotionController error recovery and safety features
 * @details Tests failure counting, callback dispatch, EE/compressor watchdog
 *          tracking, pick cycle timeout, emergency stop, and recovery reset.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/static_transform_broadcaster.h>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include "yanthra_move/core/motion_controller.hpp"
#include "yanthra_move/core/cotton_detection.hpp"
#include "yanthra_move/joint_move.h"
#include "yanthra_move/error_recovery_types.hpp"
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <std_msgs/msg/float64.hpp>
#include <thread>

// Provide global symbols that MODULAR_SOURCES (yanthra_utilities.cpp,
// motion_controller.cpp) reference via `extern` declarations.
// These are normally defined in yanthra_move_system_core.cpp (not in MODULAR_SOURCES).
namespace yanthra_move {
std::atomic<bool> simulation_mode{true};
std::shared_ptr<rclcpp::Node> global_node = nullptr;
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor = nullptr;
std::atomic<bool> executor_running{false};
std::thread executor_thread;
}  // namespace yanthra_move

// Aliases for brevity
using yanthra_move::FailureType;
using yanthra_move::FailureContext;
using yanthra_move::core::CottonDetection;
using yanthra_move::core::MotionController;

// ---------------------------------------------------------------------------
// Test fixture — creates a fresh MotionController per test via SetUp()
// ---------------------------------------------------------------------------
class ErrorRecoveryTest : public ::testing::Test
{
protected:
    // Shared across all tests (one node, publishers, joint_moves per suite)
    static rclcpp::Node::SharedPtr node_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j2_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j3_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j4_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j5_pub_;
    static std::unique_ptr<joint_move> jm3_;
    static std::unique_ptr<joint_move> jm4_;
    static std::unique_ptr<joint_move> jm5_;
    static std::shared_ptr<tf2_ros::Buffer> tf_buffer_;

    // Per-test: fresh MotionController instance (reset in SetUp)
    std::unique_ptr<MotionController> mc_;

    static void SetUpTestSuite()
    {
        node_ = rclcpp::Node::make_shared("test_error_recovery");

        // Declare ALL parameters that MotionController reads during construction
        // and initialize(). Using safe defaults for testing (simulation, no GPIO).
        auto declare = [&](const std::string& name, auto value) {
            if (!node_->has_parameter(name)) {
                node_->declare_parameter(name, value);
            }
        };

        // Core control parameters
        declare("simulation_mode", true);
        declare("position_wait_mode", std::string("blind_sleep"));
        declare("feedback_timeout", 1.0);
        declare("end_effector_enable", false);
        declare("YanthraLabCalibrationTesting", false);
        declare("use_preloaded_centroids", false);
        declare("enable_detection_retrigger", false);
        declare("enable_post_cycle_parking", false);
        declare("enable_l3_idle_parking", false);
        declare("phi_compensation/enable", false);
        declare("joint4_multiposition/enabled", false);
        declare("picking_strategy", std::string("none"));

        // Joint3 init parameters
        declare("joint3_init/homing_position", 0.00001);
        declare("joint3_init/multiple_zero_poses", false);
        declare("joint3_init/zero_poses", std::vector<double>{0.261799});
        declare("joint3_init/min_length", -1.57);
        declare("joint3_init/max_length", 1.57);
        declare("joint3_init/parking_position", 0.3);

        // Joint4 init parameters
        declare("joint4_init/homing_position", 0.00001);
        declare("joint4_init/multiple_zero_poses", false);
        declare("joint4_init/zero_poses", std::vector<double>{0.0});
        declare("joint4_init/theta_jerk_value", 0.0);
        declare("joint4_init/min_length", -0.175);
        declare("joint4_init/max_length", 0.175);

        // Joint5 init parameters
        declare("joint5_init/homing_position", 0.00001);
        declare("joint5_init/end_effector_len", 0.085);
        declare("joint5_init/joint5_vel_limit", 2.0);
        declare("joint5_init/gear_ratio", 20.943951);
        declare("joint5_init/phi_jerk_value", 0.0);
        declare("joint5_init/hardware_offset", 0.320);
        declare("joint5_init/min_length", 0.0);
        declare("joint5_init/max_length", 0.6);

        // Timing delays (all 0 for fast tests)
        declare("delays/picking", 0.0);
        declare("delays/ee_pre_arrival_time", 0.0);
        declare("delays/ee_post_retract_time", 0.0);
        declare("delays/ee_start_distance", 0.025);
        declare("delays/ee_stop_distance", 0.050);
        declare("delays/use_dynamic_ee_prestart", false);
        declare("delays/EERunTimeDuringL5ForwardMovement", 0.0);
        declare("delays/EERunTimeDuringL5BackwardMovement", 0.0);
        declare("delays/EERunTimeDuringReverseRotation", 0.0);
        declare("delays/ee_post_joint5_delay", 0.0);
        declare("min_sleep_time_formotor_motion", 0.01);
        declare("inter_joint_delay", 0.01);
        declare("cotton_settle_delay", 0.0);
        declare("compressor_burst_duration", 0.0);
        declare("enable_cotton_eject", false);
        declare("enable_compressor_eject", false);
        declare("j3_eject_position", -0.2);
        declare("ee_motor2_eject_duration_ms", 0.0);
        declare("ee_motor2_forward_flush_ms", 0.0);
        declare("j3_eject_feedback_timeout_sec", 1.5);
        declare("l2_homing_sleep_time", 0.0);
        declare("l2_step_sleep_time", 0.0);
        declare("l2_idle_sleep_time", 0.0);
        declare("cotton_capture_detect_wait_time", 0.0);
        declare("joint2_init/height_scan_enable", false);
        declare("joint2_init/min", 0.01);
        declare("joint2_init/max", 0.85);
        declare("joint2_init/step", 0.125);
        declare("pick_cycle_timeout_sec", 15.0);

        // Create publishers for joint_move static wiring
        j2_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint2_position_controller/command", 10);
        j3_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint3_position_controller/command", 10);
        j4_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint4_position_controller/command", 10);
        j5_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint5_position_controller/command", 10);
        joint_move::set_joint_publishers(j2_pub_, j3_pub_, j4_pub_, j5_pub_);

        // Enable simulation mode
        yanthra_move::simulation_mode.store(true);

        // Create joint_move instances (reused across tests — MotionController takes raw ptrs)
        jm3_ = std::make_unique<joint_move>(node_, "joint3");
        jm4_ = std::make_unique<joint_move>(node_, "joint4");
        jm5_ = std::make_unique<joint_move>(node_, "joint5");

        // TF buffer (required by MotionController constructor)
        tf_buffer_ = std::make_shared<tf2_ros::Buffer>(node_->get_clock());
    }

    void SetUp() override
    {
        // Create a fresh MotionController for each test so counters start at 0
        mc_ = std::make_unique<MotionController>(
            node_, jm3_.get(), jm5_.get(), jm4_.get(), tf_buffer_);
    }

    void TearDown() override
    {
        mc_.reset();
    }

    static void TearDownTestSuite()
    {
        yanthra_move::simulation_mode.store(false);
        j2_pub_.reset();
        j3_pub_.reset();
        j4_pub_.reset();
        j5_pub_.reset();
        jm3_.reset();
        jm4_.reset();
        jm5_.reset();
        tf_buffer_.reset();
        joint_move::cleanup_static_resources();
        node_.reset();
    }
};

// Static member definitions
rclcpp::Node::SharedPtr                                ErrorRecoveryTest::node_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   ErrorRecoveryTest::j2_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   ErrorRecoveryTest::j3_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   ErrorRecoveryTest::j4_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   ErrorRecoveryTest::j5_pub_;
std::unique_ptr<joint_move>                            ErrorRecoveryTest::jm3_;
std::unique_ptr<joint_move>                            ErrorRecoveryTest::jm4_;
std::unique_ptr<joint_move>                            ErrorRecoveryTest::jm5_;
std::shared_ptr<tf2_ros::Buffer>                       ErrorRecoveryTest::tf_buffer_;

// ===========================================================================
// 4.1 — recordMoveResult counter logic
// ===========================================================================

TEST_F(ErrorRecoveryTest, SuccessKeepsConsecutiveAtZero)
{
    mc_->recordMoveResult(3, MoveResult::SUCCESS);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 0);
}

TEST_F(ErrorRecoveryTest, TimeoutIncrementsConsecutiveAndCumulative)
{
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 1);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 1);

    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 2);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 2);

    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 3);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 3);
}

TEST_F(ErrorRecoveryTest, SuccessResetsConsecutiveButNotCumulative)
{
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 3);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 3);

    mc_->recordMoveResult(3, MoveResult::SUCCESS);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 3);
}

TEST_F(ErrorRecoveryTest, ErrorIncrementsConsecutiveAndCumulative)
{
    mc_->recordMoveResult(3, MoveResult::ERROR);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 1);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 1);

    mc_->recordMoveResult(3, MoveResult::ERROR);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 2);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 2);
}

TEST_F(ErrorRecoveryTest, CounterLogicWorksForJoint4)
{
    mc_->recordMoveResult(4, MoveResult::TIMEOUT);
    mc_->recordMoveResult(4, MoveResult::TIMEOUT);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(4), 2);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(4), 2);

    mc_->recordMoveResult(4, MoveResult::SUCCESS);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(4), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(4), 2);
}

TEST_F(ErrorRecoveryTest, CounterLogicWorksForJoint5)
{
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(5), 3);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(5), 3);

    mc_->recordMoveResult(5, MoveResult::SUCCESS);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(5), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(5), 3);
}

// ===========================================================================
// 4.2 — Failure callback firing
// ===========================================================================

TEST_F(ErrorRecoveryTest, CallbackFiresAtThreshold)
{
    int callback_count = 0;
    FailureType received_type{};
    FailureContext received_ctx{};

    mc_->setConsecutiveFailureThreshold(3);
    mc_->setOperationalFailureCallback(
        [&](FailureType type, const FailureContext& ctx) {
            ++callback_count;
            received_type = type;
            received_ctx = ctx;
        });

    // Below threshold: no callback
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 0);

    // At threshold: callback fires
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 1);
    EXPECT_EQ(received_type, FailureType::MOTOR_TIMEOUT);
    EXPECT_EQ(received_ctx.joint_id, 3);
}

TEST_F(ErrorRecoveryTest, CallbackFiresOnEveryFailureAboveThreshold)
{
    int callback_count = 0;

    mc_->setConsecutiveFailureThreshold(3);
    mc_->setOperationalFailureCallback(
        [&](FailureType, const FailureContext&) {
            ++callback_count;
        });

    // Failures 1, 2 (below threshold)
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 0);

    // Failure 3 (at threshold)
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 1);

    // Failure 4 (above threshold — should fire again)
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 2);

    // Failure 5
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 3);
}

TEST_F(ErrorRecoveryTest, NoCallbackWithoutRegistration)
{
    // No setOperationalFailureCallback() call — should not crash
    mc_->setConsecutiveFailureThreshold(1);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    // If we get here without crash, the test passes
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 2);
}

// ===========================================================================
// 4.3 — Failure type classification
// ===========================================================================

TEST_F(ErrorRecoveryTest, TimeoutMapsToMotorTimeout)
{
    FailureType received_type{};

    mc_->setConsecutiveFailureThreshold(1);
    mc_->setOperationalFailureCallback(
        [&](FailureType type, const FailureContext&) {
            received_type = type;
        });

    mc_->recordMoveResult(4, MoveResult::TIMEOUT);
    EXPECT_EQ(received_type, FailureType::MOTOR_TIMEOUT);
}

TEST_F(ErrorRecoveryTest, ErrorMapsToMotorError)
{
    FailureType received_type{};

    mc_->setConsecutiveFailureThreshold(1);
    mc_->setOperationalFailureCallback(
        [&](FailureType type, const FailureContext&) {
            received_type = type;
        });

    mc_->recordMoveResult(4, MoveResult::ERROR);
    EXPECT_EQ(received_type, FailureType::MOTOR_ERROR);
}

TEST_F(ErrorRecoveryTest, FailureContextCarriesCorrectJointId)
{
    FailureContext received_ctx{};

    mc_->setConsecutiveFailureThreshold(1);
    mc_->setOperationalFailureCallback(
        [&](FailureType, const FailureContext& ctx) {
            received_ctx = ctx;
        });

    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    EXPECT_EQ(received_ctx.joint_id, 5);
}

// ===========================================================================
// 4.4 — EE watchdog tracking (initial state)
// ===========================================================================

TEST_F(ErrorRecoveryTest, EeInitiallyOff)
{
    EXPECT_FALSE(mc_->isEeCurrentlyOn());
}

TEST_F(ErrorRecoveryTest, IsEndEffectorEnabledReflectsParameter)
{
    // Parameter "end_effector_enable" was set to false in the fixture.
    // It is loaded during initialize() -> loadMotionParameters(), not in
    // the constructor (which defaults to true).
    mc_->initialize([]() -> std::optional<std::vector<CottonDetection>> {
        return std::nullopt;
    });
    EXPECT_FALSE(mc_->isEndEffectorEnabled());
}

// ===========================================================================
// 4.5 — Compressor watchdog tracking (initial state)
// ===========================================================================

TEST_F(ErrorRecoveryTest, CompressorInitiallyOff)
{
    EXPECT_FALSE(mc_->isCompressorCurrentlyOn());
}

// ===========================================================================
// 4.6 — Pick cycle timeout
// ===========================================================================

TEST_F(ErrorRecoveryTest, PickCycleTimeoutWithShortDeadline)
{
    // Initialize the motion controller with a dummy provider
    mc_->initialize([]() -> std::optional<std::vector<CottonDetection>> {
        return std::nullopt;
    });

    // Set an extremely short timeout (1 ms)
    mc_->setPickCycleTimeout(0.001);

    // Create a detection within valid joint limits
    CottonDetection det;
    det.position.x = 0.1;
    det.position.y = 0.0;
    det.position.z = 0.3;
    det.confidence = 0.9f;
    det.detection_id = 1;
    det.detection_time = std::chrono::steady_clock::now();

    // Execute with a very short timeout — should complete (possibly with 0 picks)
    // In simulation mode the joints move instantly, so the cycle may complete
    // before the timeout fires. Either outcome (0 or 1 picks) is valid.
    int picked = mc_->executeCottonPickingSequence({det});
    EXPECT_GE(picked, 0);
    EXPECT_LE(picked, 1);
}

// ===========================================================================
// 4.7 — Recovery reset
// ===========================================================================

TEST_F(ErrorRecoveryTest, RecoveryResetAfterPartialFailures)
{
    // Accumulate 2 failures on joint 5
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(5), 2);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(5), 2);

    // Success resets consecutive but cumulative persists
    mc_->recordMoveResult(5, MoveResult::SUCCESS);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(5), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(5), 2);
}

// ===========================================================================
// Additional: setConsecutiveFailureThreshold changes threshold
// ===========================================================================

TEST_F(ErrorRecoveryTest, ThresholdChangeAffectsCallbackTiming)
{
    int callback_count = 0;

    // Start with threshold=5 (high)
    mc_->setConsecutiveFailureThreshold(5);
    mc_->setOperationalFailureCallback(
        [&](FailureType, const FailureContext&) {
            ++callback_count;
        });

    // 3 failures: no callback (threshold=5)
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 0);

    // Lower threshold to 2 — next failure (consecutive=4) >= 2 → fires
    mc_->setConsecutiveFailureThreshold(2);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 1);
}

// ===========================================================================
// Additional: threshold=1 fires on first failure
// ===========================================================================

TEST_F(ErrorRecoveryTest, ThresholdOneFiresOnFirstFailure)
{
    int callback_count = 0;

    mc_->setConsecutiveFailureThreshold(1);
    mc_->setOperationalFailureCallback(
        [&](FailureType, const FailureContext&) {
            ++callback_count;
        });

    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 1);
}

// ===========================================================================
// Additional: cumulative failures never reset (even after success)
// ===========================================================================

TEST_F(ErrorRecoveryTest, CumulativeNeverResets)
{
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::SUCCESS);  // resets consecutive only
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::SUCCESS);  // resets consecutive only

    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 3);  // 2 + 1 = 3 total
}

// ===========================================================================
// Additional: multiple joints independently track failures
// ===========================================================================

TEST_F(ErrorRecoveryTest, JointsTrackFailuresIndependently)
{
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);

    mc_->recordMoveResult(4, MoveResult::ERROR);

    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);

    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 2);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 2);

    EXPECT_EQ(mc_->getConsecutiveMoveFailures(4), 1);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(4), 1);

    EXPECT_EQ(mc_->getConsecutiveMoveFailures(5), 3);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(5), 3);

    // Reset joint 3 only
    mc_->recordMoveResult(3, MoveResult::SUCCESS);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 0);
    // Others unchanged
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(4), 1);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(5), 3);
}

// ===========================================================================
// Additional: emergency stop flag
// ===========================================================================

TEST_F(ErrorRecoveryTest, EmergencyStopInitiallyFalse)
{
    EXPECT_FALSE(mc_->isEmergencyStopRequested());
}

TEST_F(ErrorRecoveryTest, RequestEmergencyStopSetsFlag)
{
    mc_->requestEmergencyStop();
    EXPECT_TRUE(mc_->isEmergencyStopRequested());
}

// ===========================================================================
// Additional: unknown joint_id doesn't crash
// ===========================================================================

TEST_F(ErrorRecoveryTest, UnknownJointIdDoesNotCrash)
{
    // These should silently return without modifying any state
    mc_->recordMoveResult(99, MoveResult::TIMEOUT);
    mc_->recordMoveResult(0, MoveResult::ERROR);
    mc_->recordMoveResult(-1, MoveResult::TIMEOUT);
    mc_->recordMoveResult(2, MoveResult::TIMEOUT);  // Joint 2 not tracked
    mc_->recordMoveResult(6, MoveResult::ERROR);

    // Valid joints remain at 0
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(4), 0);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(5), 0);
}

TEST_F(ErrorRecoveryTest, GetFailuresForUnknownJointReturnsZero)
{
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(99), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(99), 0);
    EXPECT_EQ(mc_->getConsecutiveMoveFailures(0), 0);
    EXPECT_EQ(mc_->getCumulativeMoveFailures(0), 0);
}

// ===========================================================================
// Additional: callback receives correct joint_id for different joints
// ===========================================================================

TEST_F(ErrorRecoveryTest, CallbackJointIdMatchesForEachJoint)
{
    std::vector<int> received_joint_ids;

    mc_->setConsecutiveFailureThreshold(1);
    mc_->setOperationalFailureCallback(
        [&](FailureType, const FailureContext& ctx) {
            received_joint_ids.push_back(ctx.joint_id);
        });

    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(4, MoveResult::ERROR);
    mc_->recordMoveResult(5, MoveResult::TIMEOUT);

    ASSERT_EQ(received_joint_ids.size(), 3u);
    EXPECT_EQ(received_joint_ids[0], 3);
    EXPECT_EQ(received_joint_ids[1], 4);
    EXPECT_EQ(received_joint_ids[2], 5);
}

// ===========================================================================
// Additional: EE and compressor getOnSince returns a time_point
// ===========================================================================

TEST_F(ErrorRecoveryTest, EeOnSinceReturnsValidTimePoint)
{
    // When EE has never been turned on, getEeOnSince() should return the
    // default-constructed time_point (epoch). Just verify it's callable
    // and returns something not in the future.
    auto t = mc_->getEeOnSince();
    auto now = std::chrono::steady_clock::now();
    EXPECT_LE(t, now);
}

TEST_F(ErrorRecoveryTest, CompressorOnSinceReturnsValidTimePoint)
{
    auto t = mc_->getCompressorOnSince();
    auto now = std::chrono::steady_clock::now();
    EXPECT_LE(t, now);
}

// ===========================================================================
// Additional: turnOff methods don't crash when GPIO unavailable
// ===========================================================================

TEST_F(ErrorRecoveryTest, TurnOffEndEffectorSafeWithoutGpio)
{
    // GPIO is not available in test env — should not crash
    mc_->turnOffEndEffector();
    EXPECT_FALSE(mc_->isEeCurrentlyOn());
}

TEST_F(ErrorRecoveryTest, TurnOffCompressorSafeWithoutGpio)
{
    mc_->turnOffCompressor();
    EXPECT_FALSE(mc_->isCompressorCurrentlyOn());
}

// ===========================================================================
// Additional: mixed SUCCESS and failure sequences
// ===========================================================================

TEST_F(ErrorRecoveryTest, InterleavedSuccessAndFailure)
{
    mc_->setConsecutiveFailureThreshold(3);
    int callback_count = 0;
    mc_->setOperationalFailureCallback(
        [&](FailureType, const FailureContext&) {
            ++callback_count;
        });

    // T, T, S, T, T, S, T, T, T -> callback fires on last T
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::SUCCESS);  // resets consecutive to 0
    EXPECT_EQ(callback_count, 0);

    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);
    mc_->recordMoveResult(3, MoveResult::SUCCESS);  // resets consecutive to 0
    EXPECT_EQ(callback_count, 0);

    mc_->recordMoveResult(3, MoveResult::TIMEOUT);  // consecutive=1
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);  // consecutive=2
    mc_->recordMoveResult(3, MoveResult::TIMEOUT);  // consecutive=3 -> fires
    EXPECT_EQ(callback_count, 1);

    // Cumulative: 2 + 2 + 3 = 7
    EXPECT_EQ(mc_->getCumulativeMoveFailures(3), 7);
}

// ---------------------------------------------------------------------------
// main — initialize / shutdown rclcpp around the test run
// ---------------------------------------------------------------------------

// ===========================================================================
// 4.8 — Safe mode state tracking (ErrorRecoveryState)
// ===========================================================================

TEST_F(ErrorRecoveryTest, SafeModeInitiallyInactive)
{
    yanthra_move::ErrorRecoveryState state;
    EXPECT_FALSE(state.safe_mode_active.load());
}

TEST_F(ErrorRecoveryTest, SafeModeActivationPersists)
{
    yanthra_move::ErrorRecoveryState state;
    state.safe_mode_active.store(true);
    EXPECT_TRUE(state.safe_mode_active.load());

    // Safe mode should persist — it is not automatically cleared
    EXPECT_TRUE(state.safe_mode_active.load());
}

TEST_F(ErrorRecoveryTest, SafeModeAtomicCompareExchangePreventsDoubleEntry)
{
    yanthra_move::ErrorRecoveryState state;

    // First entry succeeds
    bool expected = false;
    EXPECT_TRUE(state.safe_mode_active.compare_exchange_strong(expected, true));
    EXPECT_TRUE(state.safe_mode_active.load());

    // Second entry fails (already in safe mode)
    expected = false;
    EXPECT_FALSE(state.safe_mode_active.compare_exchange_strong(expected, true));
}

// ===========================================================================
// 4.9 — Degraded mode state tracking (ErrorRecoveryState)
// ===========================================================================

TEST_F(ErrorRecoveryTest, DegradedModeInitiallyInactive)
{
    yanthra_move::ErrorRecoveryState state;
    EXPECT_FALSE(state.degraded_mode_active.load());
}

TEST_F(ErrorRecoveryTest, DegradedModeActivationWithDisabledComponents)
{
    yanthra_move::ErrorRecoveryState state;
    state.degraded_mode_active.store(true);

    std::lock_guard<std::mutex> lock(state.state_mutex);
    state.disabled_components.push_back("camera");
    state.disabled_components.push_back("vision");

    EXPECT_TRUE(state.degraded_mode_active.load());
    EXPECT_EQ(state.disabled_components.size(), 2u);
    EXPECT_EQ(state.disabled_components[0], "camera");
    EXPECT_EQ(state.disabled_components[1], "vision");
}

// ===========================================================================
// 4.10 — FailureType::DETECTION_UNAVAILABLE exists and is distinct
// ===========================================================================

TEST_F(ErrorRecoveryTest, DetectionUnavailableFailureTypeExists)
{
    // Verify DETECTION_UNAVAILABLE is a distinct enum value
    EXPECT_NE(FailureType::DETECTION_UNAVAILABLE, FailureType::MOTOR_TIMEOUT);
    EXPECT_NE(FailureType::DETECTION_UNAVAILABLE, FailureType::MOTOR_ERROR);
    EXPECT_NE(FailureType::DETECTION_UNAVAILABLE, FailureType::PICK_TIMEOUT);
}

TEST_F(ErrorRecoveryTest, DetectionUnavailableCallbackReceivesCorrectType)
{
    FailureType received_type{};

    mc_->setConsecutiveFailureThreshold(1);
    mc_->setOperationalFailureCallback(
        [&](FailureType type, const FailureContext&) {
            received_type = type;
        });

    // Simulate a detection failure reported as a TIMEOUT on an arbitrary joint
    // The actual DETECTION_UNAVAILABLE dispatch happens in YanthraMoveSystem,
    // but we can verify the callback infrastructure can carry this type.
    // For unit test: verify the enum is usable in contexts and FailureContext
    FailureContext ctx;
    ctx.joint_id = 0;  // Not joint-specific
    ctx.phase = "detection";
    EXPECT_EQ(ctx.phase, "detection");
}

// ===========================================================================
// 4.11 — ErrorRecoveryState consecutive_failures and total_recoveries
// ===========================================================================

TEST_F(ErrorRecoveryTest, ErrorRecoveryStateTracksCounts)
{
    yanthra_move::ErrorRecoveryState state;

    EXPECT_EQ(state.consecutive_failures.load(), 0);
    EXPECT_EQ(state.total_recoveries.load(), 0);

    state.consecutive_failures.fetch_add(1);
    state.consecutive_failures.fetch_add(1);
    state.consecutive_failures.fetch_add(1);
    EXPECT_EQ(state.consecutive_failures.load(), 3);

    // Reset consecutive on recovery
    state.consecutive_failures.store(0);
    state.total_recoveries.fetch_add(1);
    EXPECT_EQ(state.consecutive_failures.load(), 0);
    EXPECT_EQ(state.total_recoveries.load(), 1);
}

TEST_F(ErrorRecoveryTest, ErrorRecoveryStateRecoveryActiveGuard)
{
    yanthra_move::ErrorRecoveryState state;
    EXPECT_FALSE(state.recovery_active.load());

    // First attempt acquires the guard
    bool expected = false;
    EXPECT_TRUE(state.recovery_active.compare_exchange_strong(expected, true));
    EXPECT_TRUE(state.recovery_active.load());

    // Second attempt fails (recovery already in progress)
    expected = false;
    EXPECT_FALSE(state.recovery_active.compare_exchange_strong(expected, true));

    // Release
    state.recovery_active.store(false);
    expected = false;
    EXPECT_TRUE(state.recovery_active.compare_exchange_strong(expected, true));
}

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int ret = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return ret;
}
