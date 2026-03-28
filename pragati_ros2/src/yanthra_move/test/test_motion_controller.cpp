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
 * @file test_motion_controller.cpp
 * @brief Comprehensive GTest suite for MotionController
 * @details Tests construction, initialization, picking sequences, operational
 *          cycles, phi compensation, J4 multi-position scanning, failure
 *          tracking, emergency stop, and cycle timing (PERF-ARM-001).
 *
 *          Runs entirely in simulation mode with blind_sleep position wait
 *          to avoid hardware and service dependencies.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <rcutils/logging.h>
#include <tf2_ros/buffer.h>
#include <tf2_ros/static_transform_broadcaster.h>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <std_msgs/msg/float64.hpp>

#include "yanthra_move/core/motion_controller.hpp"
#include "yanthra_move/core/cotton_detection.hpp"
#include "yanthra_move/joint_move.h"
#include "yanthra_move/error_recovery_types.hpp"

#include <mutex>
#include <string>
#include <vector>

// ═══════════════════════════════════════════════════════════════════════════════
// PROVIDE EXTERN SYMBOLS
// ═══════════════════════════════════════════════════════════════════════════════
// These symbols are normally defined in yanthra_move_system_core.cpp and
// yanthra_utilities.cpp.  We define them here so the test binary links without
// pulling in the full system node.
// ═══════════════════════════════════════════════════════════════════════════════

namespace yanthra_move {
std::atomic<bool> simulation_mode{true};
std::atomic<bool> executor_running{false};
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor{nullptr};
std::shared_ptr<rclcpp::Node> global_node{nullptr};
std::thread executor_thread;
}  // namespace yanthra_move

using yanthra_move::core::CottonDetection;
using yanthra_move::core::MotionController;

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER: Create a CottonDetection at the given camera-frame position
// ═══════════════════════════════════════════════════════════════════════════════
static CottonDetection makeDetection(double x, double y, double z,
                                     float confidence = 0.9f,
                                     int id = 0) {
    CottonDetection det;
    det.position.x = x;
    det.position.y = y;
    det.position.z = z;
    det.confidence = confidence;
    det.detection_id = id;
    det.detection_time = std::chrono::steady_clock::now();
    det.processing_time_ms = 10;
    return det;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEST FIXTURE
// ═══════════════════════════════════════════════════════════════════════════════
class MotionControllerTest : public ::testing::Test {
protected:
    // Shared across the entire test suite (one rclcpp::Node is cheaper)
    static rclcpp::Node::SharedPtr node_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j2_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j3_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j4_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j5_pub_;
    static std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
    static std::shared_ptr<tf2_ros::StaticTransformBroadcaster> tf_broadcaster_;

    // Per-test joint_move instances (lightweight; depend on static publishers)
    std::unique_ptr<joint_move> jm3_;
    std::unique_ptr<joint_move> jm5_;
    std::unique_ptr<joint_move> jm4_;

    // ─────────────────────────────────────────────────────────────────────────
    // SetUpTestSuite — create node, publishers, TF broadcaster once
    // ─────────────────────────────────────────────────────────────────────────
    static void SetUpTestSuite() {
        node_ = rclcpp::Node::make_shared("test_motion_controller");

        // ───────── Declare ALL parameters ─────────
        // Top-level flags
        declareParam("simulation_mode", true);
        declareParam("position_wait_mode", std::string("blind_sleep"));
        declareParam("feedback_timeout", 1.0);
        declareParam("end_effector_enable", false);
        declareParam("YanthraLabCalibrationTesting", false);
        declareParam("use_preloaded_centroids", false);
        declareParam("enable_detection_retrigger", false);
        declareParam("enable_post_cycle_parking", false);
        declareParam("enable_l3_idle_parking", false);
        declareParam("picking_strategy", std::string("none"));

        // Phi compensation (disabled by default)
        declareParam("phi_compensation/enable", false);

        // Joint4 multi-position (disabled by default — individual tests override)
        declareParam("joint4_multiposition/enabled", false);

        // Joint3 init
        declareParam("joint3_init/homing_position", 0.00001);
        declareParam("joint3_init/multiple_zero_poses", false);
        declareParam("joint3_init/zero_poses", std::vector<double>{0.261799});
        declareParam("joint3_init/min_length", -1.57);
        declareParam("joint3_init/max_length", 1.57);
        declareParam("joint3_init/parking_position", 0.3);

        // Joint4 init
        declareParam("joint4_init/homing_position", 0.00001);
        declareParam("joint4_init/multiple_zero_poses", false);
        declareParam("joint4_init/zero_poses", std::vector<double>{0.0});
        declareParam("joint4_init/theta_jerk_value", 0.0);
        declareParam("joint4_init/min_length", -0.175);
        declareParam("joint4_init/max_length", 0.175);

        // Joint5 init
        declareParam("joint5_init/homing_position", 0.00001);
        declareParam("joint5_init/end_effector_len", 0.085);
        declareParam("joint5_init/joint5_vel_limit", 2.0);
        declareParam("joint5_init/gear_ratio", 20.943951);
        declareParam("joint5_init/phi_jerk_value", 0.0);
        declareParam("joint5_init/hardware_offset", 0.320);
        declareParam("joint5_init/min_length", 0.0);
        declareParam("joint5_init/max_length", 0.6);

        // Joint2 init (needed by loadJointInitParameters)
        declareParam("joint2_init/height_scan_enable", false);
        declareParam("joint2_init/min", 0.01);
        declareParam("joint2_init/max", 0.85);
        declareParam("joint2_init/step", 0.125);

        // Timing delays — all zero/tiny so tests run fast
        declareParam("delays/picking", 0.0);
        declareParam("delays/ee_pre_arrival_time", 0.0);
        declareParam("delays/ee_post_retract_time", 0.0);
        declareParam("delays/ee_start_distance", 0.025);
        declareParam("delays/ee_stop_distance", 0.050);
        declareParam("delays/use_dynamic_ee_prestart", false);
        declareParam("delays/EERunTimeDuringL5ForwardMovement", 0.0);
        declareParam("delays/EERunTimeDuringL5BackwardMovement", 0.0);
        declareParam("delays/EERunTimeDuringReverseRotation", 0.0);
        declareParam("delays/ee_post_joint5_delay", 0.0);
        declareParam("min_sleep_time_formotor_motion", 0.01);
        declareParam("inter_joint_delay", 0.01);
        declareParam("cotton_settle_delay", 0.0);
        declareParam("compressor_burst_duration", 0.0);
        declareParam("enable_cotton_eject", false);
        declareParam("enable_compressor_eject", false);
        declareParam("j3_eject_position", -0.2);
        declareParam("ee_motor2_eject_duration_ms", 0.0);
        declareParam("ee_motor2_forward_flush_ms", 0.0);
        declareParam("j3_eject_feedback_timeout_sec", 1.5);
        declareParam("l2_homing_sleep_time", 0.0);
        declareParam("l2_step_sleep_time", 0.0);
        declareParam("l2_idle_sleep_time", 0.0);
        declareParam("cotton_capture_detect_wait_time", 0.0);

        // Pick cycle timeout
        declareParam("pick_cycle_timeout_sec", 15.0);

        // ───────── Publishers for joint_move statics ─────────
        j2_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint2_position_controller/command", 10);
        j3_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint3_position_controller/command", 10);
        j4_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint4_position_controller/command", 10);
        j5_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint5_position_controller/command", 10);
        joint_move::set_joint_publishers(j2_pub_, j3_pub_, j4_pub_, j5_pub_);

        // ───────── TF2 buffer + static broadcaster ─────────
        tf_buffer_ = std::make_shared<tf2_ros::Buffer>(node_->get_clock());
        // Provide a TransformListener so the buffer can receive the broadcast
        // (not strictly required for setTransform, but safer for lookupTransform)
        tf_broadcaster_ = std::make_shared<tf2_ros::StaticTransformBroadcaster>(node_);

        // Publish a camera_link → yanthra_link identity transform so that
        // TF lookups inside MotionController succeed.
        geometry_msgs::msg::TransformStamped t;
        t.header.stamp = node_->get_clock()->now();
        t.header.frame_id = "yanthra_link";
        t.child_frame_id = "camera_link";
        t.transform.rotation.w = 1.0;  // identity quaternion
        tf_broadcaster_->sendTransform(t);

        // Also inject it directly into the buffer for immediate availability
        tf_buffer_->setTransform(t, "test_authority", /*is_static=*/true);

        // Ensure simulation mode is on
        yanthra_move::simulation_mode.store(true);
    }

    static void TearDownTestSuite() {
        yanthra_move::simulation_mode.store(false);
        j2_pub_.reset();
        j3_pub_.reset();
        j4_pub_.reset();
        j5_pub_.reset();
        joint_move::cleanup_static_resources();
        tf_broadcaster_.reset();
        tf_buffer_.reset();
        node_.reset();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Per-test setup: fresh joint_move instances
    // ─────────────────────────────────────────────────────────────────────────
    void SetUp() override {
        jm3_ = std::make_unique<joint_move>(node_, "joint3");
        jm5_ = std::make_unique<joint_move>(node_, "joint5");
        jm4_ = std::make_unique<joint_move>(node_, "joint4");
    }

    void TearDown() override {
        jm3_.reset();
        jm5_.reset();
        jm4_.reset();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────────

    /// Build a MotionController wired to the per-test joints.
    std::unique_ptr<MotionController> makeController() {
        return std::make_unique<MotionController>(
            node_, jm3_.get(), jm5_.get(), jm4_.get(), tf_buffer_);
    }

    /// Initialize controller with a simple provider returning `detections`.
    bool initWithDetections(MotionController& mc,
                            const std::vector<CottonDetection>& detections) {
        auto provider = [detections]()
            -> std::optional<std::vector<CottonDetection>> {
            return detections;
        };
        return mc.initialize(provider);
    }

    /// Initialize controller with provider returning empty (no cotton).
    bool initWithEmptyProvider(MotionController& mc) {
        auto provider = []()
            -> std::optional<std::vector<CottonDetection>> {
            return std::vector<CottonDetection>{};
        };
        return mc.initialize(provider);
    }

    /// Create a set of detections with known-reachable arm-frame positions.
    /// Positions are in camera_link frame; since our TF is identity,
    /// camera_link coords == yanthra_link coords.
    /// Chosen values are within joint limits:
    ///   J3 (phi):  [-1.57, 1.57] rad
    ///   J4 (theta): [-0.175, 0.175] m
    ///   J5 (r):     [0.0, 0.6] m
    static std::vector<CottonDetection> makeReachableDetections(int count = 2) {
        std::vector<CottonDetection> dets;
        // Position in arm frame: x forward, y left, z up.
        // Cotton at (0.3, 0, 0) → r≈0.3, phi≈0, theta≈0 → well within limits
        dets.push_back(makeDetection(0.30, 0.0, 0.0, 0.95f, 1));
        if (count >= 2) {
            dets.push_back(makeDetection(0.25, 0.02, 0.0, 0.88f, 2));
        }
        if (count >= 3) {
            dets.push_back(makeDetection(0.35, -0.01, 0.0, 0.80f, 3));
        }
        return dets;
    }

private:
    // Convenience: declare-if-not-exists (avoids duplicate declare errors)
    template <typename T>
    static void declareParam(const std::string& name, const T& value) {
        if (!node_->has_parameter(name)) {
            node_->declare_parameter<T>(name, value);
        }
    }
};

// Static member definitions
rclcpp::Node::SharedPtr MotionControllerTest::node_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr MotionControllerTest::j2_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr MotionControllerTest::j3_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr MotionControllerTest::j4_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr MotionControllerTest::j5_pub_;
std::shared_ptr<tf2_ros::Buffer> MotionControllerTest::tf_buffer_;
std::shared_ptr<tf2_ros::StaticTransformBroadcaster> MotionControllerTest::tf_broadcaster_;

// ═════════════════════════════════════════════════════════════════════════════
// 2.1  FIXTURE SETUP — construction, initialization, readiness
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, ConstructsWithoutThrowing) {
    EXPECT_NO_THROW({
        auto mc = makeController();
    });
}

TEST_F(MotionControllerTest, IsNotReadyBeforeInit) {
    auto mc = makeController();
    EXPECT_FALSE(mc->isReady());
}

TEST_F(MotionControllerTest, InitializeReturnsTrueWithValidProvider) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    EXPECT_TRUE(initWithDetections(*mc, detections));
}

TEST_F(MotionControllerTest, IsReadyAfterInit) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));
    EXPECT_TRUE(mc->isReady());
}

TEST_F(MotionControllerTest, InitializeReturnsFalseWithNullProvider) {
    auto mc = makeController();
    std::function<std::optional<std::vector<CottonDetection>>()> null_provider;
    EXPECT_FALSE(mc->initialize(null_provider));
}

TEST_F(MotionControllerTest, DoubleInitReturnsTrue) {
    // Second initialize should return true (already initialized)
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));
    // Calling again — should warn but return true
    auto provider = [&detections]()
        -> std::optional<std::vector<CottonDetection>> { return detections; };
    EXPECT_TRUE(mc->initialize(provider));
}

TEST_F(MotionControllerTest, ConstructorThrowsWithNullJoint3) {
    EXPECT_THROW(
        MotionController(node_, nullptr, jm5_.get(), jm4_.get(), tf_buffer_),
        std::runtime_error);
}

TEST_F(MotionControllerTest, ConstructorThrowsWithNullJoint5) {
    EXPECT_THROW(
        MotionController(node_, jm3_.get(), nullptr, jm4_.get(), tf_buffer_),
        std::runtime_error);
}

TEST_F(MotionControllerTest, ConstructorThrowsWithNullJoint4) {
    EXPECT_THROW(
        MotionController(node_, jm3_.get(), jm5_.get(), nullptr, tf_buffer_),
        std::runtime_error);
}

// ═════════════════════════════════════════════════════════════════════════════
// MOTORS AVAILABLE — simulation mode always true
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, AreMotorsAvailableReturnsTrueInSimulation) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));
    EXPECT_TRUE(mc->areMotorsAvailable());
}

// ═════════════════════════════════════════════════════════════════════════════
// EMERGENCY STOP
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, EmergencyStopInitiallyFalse) {
    auto mc = makeController();
    EXPECT_FALSE(mc->isEmergencyStopRequested());
}

TEST_F(MotionControllerTest, EmergencyStopSetsFlag) {
    auto mc = makeController();
    mc->requestEmergencyStop();
    EXPECT_TRUE(mc->isEmergencyStopRequested());
}

// ═════════════════════════════════════════════════════════════════════════════
// STAT COUNTERS — initial values
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, InitialStatsAreZero) {
    auto mc = makeController();
    EXPECT_EQ(mc->getCycleCount(), 0);
    EXPECT_EQ(mc->getTotalCottonPicked(), 0);
    EXPECT_EQ(mc->getTotalPicksAttempted(), 0);
    EXPECT_EQ(mc->getTotalPicksSuccessful(), 0);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(4), 0);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(5), 0);
    EXPECT_EQ(mc->getCumulativeMoveFailures(3), 0);
    EXPECT_EQ(mc->getCumulativeMoveFailures(4), 0);
    EXPECT_EQ(mc->getCumulativeMoveFailures(5), 0);
}

// ═════════════════════════════════════════════════════════════════════════════
// 2.5b  RECORD MOVE RESULT — failure tracking
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, RecordMoveResultSuccessResetsConsecutive) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    // Record a failure then a success
    mc->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(3), 1);
    EXPECT_EQ(mc->getCumulativeMoveFailures(3), 1);

    mc->recordMoveResult(3, MoveResult::SUCCESS);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mc->getCumulativeMoveFailures(3), 1);  // cumulative stays
}

TEST_F(MotionControllerTest, RecordMoveResultAccumulatesFailures) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    mc->recordMoveResult(5, MoveResult::ERROR);
    mc->recordMoveResult(5, MoveResult::ERROR);
    mc->recordMoveResult(5, MoveResult::TIMEOUT);

    EXPECT_EQ(mc->getConsecutiveMoveFailures(5), 3);
    EXPECT_EQ(mc->getCumulativeMoveFailures(5), 3);
}

TEST_F(MotionControllerTest, RecordMoveResultIgnoresUnknownJoint) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    // Unknown joint_id=99 should silently return without crash
    EXPECT_NO_THROW(mc->recordMoveResult(99, MoveResult::ERROR));
    // The getters should return 0 for unknown joints
    EXPECT_EQ(mc->getConsecutiveMoveFailures(99), 0);
    EXPECT_EQ(mc->getCumulativeMoveFailures(99), 0);
}

TEST_F(MotionControllerTest, FailureCallbackFiresAtThreshold) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    // Track callback invocations
    int callback_count = 0;
    yanthra_move::FailureType captured_type{};
    int captured_joint_id = 0;

    mc->setOperationalFailureCallback(
        [&](yanthra_move::FailureType type,
            const yanthra_move::FailureContext& ctx) {
            ++callback_count;
            captured_type = type;
            captured_joint_id = ctx.joint_id;
        });

    mc->setConsecutiveFailureThreshold(2);

    // First failure — no callback
    mc->recordMoveResult(4, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 0);

    // Second failure — threshold reached, callback fires
    mc->recordMoveResult(4, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 1);
    EXPECT_EQ(captured_type, yanthra_move::FailureType::MOTOR_TIMEOUT);
    EXPECT_EQ(captured_joint_id, 4);
}

TEST_F(MotionControllerTest, FailureCallbackDistinguishesTimeoutVsError) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    yanthra_move::FailureType captured_type{};
    mc->setOperationalFailureCallback(
        [&](yanthra_move::FailureType type,
            const yanthra_move::FailureContext&) {
            captured_type = type;
        });

    mc->setConsecutiveFailureThreshold(1);

    mc->recordMoveResult(3, MoveResult::ERROR);
    EXPECT_EQ(captured_type, yanthra_move::FailureType::MOTOR_ERROR);
}

// ═════════════════════════════════════════════════════════════════════════════
// SET PICK CYCLE TIMEOUT
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, SetPickCycleTimeoutDoesNotCrash) {
    auto mc = makeController();
    EXPECT_NO_THROW(mc->setPickCycleTimeout(5.0));
}

// ═════════════════════════════════════════════════════════════════════════════
// 2.8  MOVE TO PACKING POSITION — simulation mode
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, MoveToPackingPositionSucceedsInSim) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    bool ok = mc->moveToPackingPosition();
    EXPECT_TRUE(ok);
}

// ═════════════════════════════════════════════════════════════════════════════
// 2.2  EXECUTE COTTON PICKING SEQUENCE
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, PickingSequenceReturnsNonNegativeCount) {
    auto mc = makeController();
    auto detections = makeReachableDetections(2);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    int picked = mc->executeCottonPickingSequence(detections);
    EXPECT_GE(picked, 0);
}

TEST_F(MotionControllerTest, PickingSequenceReturnsZeroForEmpty) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    std::vector<CottonDetection> empty;
    int picked = mc->executeCottonPickingSequence(empty);
    EXPECT_EQ(picked, 0);
}

TEST_F(MotionControllerTest, PickingSequenceIncreasesPicksAttempted) {
    auto mc = makeController();
    auto detections = makeReachableDetections(2);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    int before = mc->getTotalPicksAttempted();
    mc->executeCottonPickingSequence(detections);
    int after = mc->getTotalPicksAttempted();

    // Each detection should produce at least one attempt
    EXPECT_GT(after, before);
}

TEST_F(MotionControllerTest, PickingSequenceWithSingleDetection) {
    auto mc = makeController();
    auto detections = makeReachableDetections(1);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    int picked = mc->executeCottonPickingSequence(detections);
    // In simulation mode with blind_sleep, the pick should succeed
    EXPECT_GE(picked, 0);
    EXPECT_LE(picked, 1);
}

TEST_F(MotionControllerTest, PickingSequenceWithMultipleDetections) {
    auto mc = makeController();
    auto detections = makeReachableDetections(3);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    int picked = mc->executeCottonPickingSequence(detections);
    EXPECT_GE(picked, 0);
    EXPECT_LE(picked, 3);
}

// ═════════════════════════════════════════════════════════════════════════════
// 2.3  EXECUTE OPERATIONAL CYCLE
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, OperationalCycleReturnsTrueWhenInitialized) {
    auto mc = makeController();
    auto detections = makeReachableDetections(2);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    bool result = mc->executeOperationalCycle();
    EXPECT_TRUE(result);
}

TEST_F(MotionControllerTest, OperationalCycleReturnsFalseWhenNotInitialized) {
    auto mc = makeController();
    // Do NOT call initialize
    bool result = mc->executeOperationalCycle();
    EXPECT_FALSE(result);
}

TEST_F(MotionControllerTest, OperationalCycleIncrementsCycleCount) {
    auto mc = makeController();
    auto detections = makeReachableDetections(1);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    EXPECT_EQ(mc->getCycleCount(), 0);
    mc->executeOperationalCycle();
    EXPECT_EQ(mc->getCycleCount(), 1);
    mc->executeOperationalCycle();
    EXPECT_EQ(mc->getCycleCount(), 2);
}

TEST_F(MotionControllerTest, OperationalCycleWithNoDetectionsReturnsTrueGracefully) {
    auto mc = makeController();
    // Provider returns empty vector → no cotton detected, still returns true
    ASSERT_TRUE(initWithEmptyProvider(*mc));

    bool result = mc->executeOperationalCycle();
    EXPECT_TRUE(result);
}

TEST_F(MotionControllerTest, OperationalCycleWithNulloptProviderReturnsTrueGracefully) {
    auto mc = makeController();
    // Provider returns nullopt → detection unavailable, returns true (not an error)
    auto provider = []() -> std::optional<std::vector<CottonDetection>> {
        return std::nullopt;
    };
    ASSERT_TRUE(mc->initialize(provider));

    bool result = mc->executeOperationalCycle();
    EXPECT_TRUE(result);
}

// ═════════════════════════════════════════════════════════════════════════════
// 2.4  PHI COMPENSATION — enable and verify no crash
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, PhiCompensationEnabledDoesNotCrash) {
    // Override the phi_compensation/enable parameter
    node_->set_parameter(rclcpp::Parameter("phi_compensation/enable", true));

    auto mc = makeController();
    auto detections = makeReachableDetections(2);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    // Execute a picking sequence — should not crash with phi compensation on
    int picked = mc->executeCottonPickingSequence(detections);
    EXPECT_GE(picked, 0);

    // Restore default for other tests
    node_->set_parameter(rclcpp::Parameter("phi_compensation/enable", false));
}

TEST_F(MotionControllerTest, PhiCompensationDisabledDoesNotCrash) {
    node_->set_parameter(rclcpp::Parameter("phi_compensation/enable", false));

    auto mc = makeController();
    auto detections = makeReachableDetections(2);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    int picked = mc->executeCottonPickingSequence(detections);
    EXPECT_GE(picked, 0);
}

// ═════════════════════════════════════════════════════════════════════════════
// 2.5  J4 MULTI-POSITION SCANNING
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, J4MultiPositionScanCompletes) {
    // Enable J4 multi-position and configure positions
    node_->set_parameter(rclcpp::Parameter("joint4_multiposition/enabled", true));
    // Need to declare positions if not already
    if (!node_->has_parameter("joint4_multiposition/positions")) {
        node_->declare_parameter<std::vector<double>>(
            "joint4_multiposition/positions", {-0.1, 0.0, 0.1});
    } else {
        node_->set_parameter(rclcpp::Parameter(
            "joint4_multiposition/positions", std::vector<double>{-0.1, 0.0, 0.1}));
    }

    auto mc = makeController();
    auto detections = makeReachableDetections(2);

    // For multi-position mode in non-calibration, the code uses
    // detection_trigger_callback_ which must be set.  If not set,
    // it falls back to single-position mode.  To test multi-pos,
    // set the detection trigger callback.
    int trigger_count = 0;
    mc->setDetectionTriggerCallback(
        [&detections, &trigger_count]()
            -> std::optional<std::vector<CottonDetection>> {
            ++trigger_count;
            return detections;
        });

    ASSERT_TRUE(initWithDetections(*mc, detections));

    bool result = mc->executeOperationalCycle();
    EXPECT_TRUE(result);

    // Multi-position scan should call the trigger at each position
    // (3 positions configured)
    EXPECT_GE(trigger_count, 1);

    // Restore defaults
    node_->set_parameter(rclcpp::Parameter("joint4_multiposition/enabled", false));
}

TEST_F(MotionControllerTest, J4MultiPositionProviderCalledPerPosition) {
    node_->set_parameter(rclcpp::Parameter("joint4_multiposition/enabled", true));
    if (!node_->has_parameter("joint4_multiposition/positions")) {
        node_->declare_parameter<std::vector<double>>(
            "joint4_multiposition/positions", {-0.05, 0.0, 0.05});
    } else {
        node_->set_parameter(rclcpp::Parameter(
            "joint4_multiposition/positions",
            std::vector<double>{-0.05, 0.0, 0.05}));
    }

    auto mc = makeController();
    auto detections = makeReachableDetections(1);

    int trigger_count = 0;
    mc->setDetectionTriggerCallback(
        [&detections, &trigger_count]()
            -> std::optional<std::vector<CottonDetection>> {
            ++trigger_count;
            return detections;
        });

    ASSERT_TRUE(initWithDetections(*mc, detections));
    mc->executeOperationalCycle();

    // Should be called at least 3 times (one per J4 position)
    EXPECT_GE(trigger_count, 3);

    node_->set_parameter(rclcpp::Parameter("joint4_multiposition/enabled", false));
}

// ═════════════════════════════════════════════════════════════════════════════
// 2.6  PICK CYCLE TIMING (PERF-ARM-001)
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, OperationalCycleCompletesWithin15Seconds) {
    auto mc = makeController();
    auto detections = makeReachableDetections(2);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    auto start = std::chrono::steady_clock::now();
    mc->executeOperationalCycle();
    auto end = std::chrono::steady_clock::now();

    auto duration_ms =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start)
            .count();

    // PERF-ARM-001: Each cycle should complete within 15 seconds
    EXPECT_LT(duration_ms, 15000)
        << "Operational cycle took " << duration_ms
        << "ms — exceeds PERF-ARM-001 target of 15000ms";
}

TEST_F(MotionControllerTest, PickingSequenceCompletesWithin15Seconds) {
    auto mc = makeController();
    auto detections = makeReachableDetections(3);
    ASSERT_TRUE(initWithDetections(*mc, detections));

    auto start = std::chrono::steady_clock::now();
    mc->executeCottonPickingSequence(detections);
    auto end = std::chrono::steady_clock::now();

    auto duration_ms =
        std::chrono::duration_cast<std::chrono::milliseconds>(end - start)
            .count();

    EXPECT_LT(duration_ms, 15000)
        << "Picking sequence took " << duration_ms
        << "ms — exceeds PERF-ARM-001 target of 15000ms";
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: End effector enable flag
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, EndEffectorDisabledByParameter) {
    // We declared end_effector_enable = false in SetUpTestSuite
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));
    EXPECT_FALSE(mc->isEndEffectorEnabled());
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: Consecutive failure threshold setter
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, SetConsecutiveFailureThresholdWorks) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    int callback_count = 0;
    mc->setOperationalFailureCallback(
        [&](yanthra_move::FailureType,
            const yanthra_move::FailureContext&) { ++callback_count; });

    mc->setConsecutiveFailureThreshold(5);

    // Record 4 failures — should not trigger (threshold 5)
    for (int i = 0; i < 4; ++i) {
        mc->recordMoveResult(3, MoveResult::TIMEOUT);
    }
    EXPECT_EQ(callback_count, 0);

    // 5th failure — should trigger
    mc->recordMoveResult(3, MoveResult::TIMEOUT);
    EXPECT_EQ(callback_count, 1);
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: Per-joint failure tracking isolation
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, PerJointFailureTrackingIsIndependent) {
    auto mc = makeController();
    auto detections = makeReachableDetections();
    ASSERT_TRUE(initWithDetections(*mc, detections));

    mc->recordMoveResult(3, MoveResult::ERROR);
    mc->recordMoveResult(3, MoveResult::ERROR);
    mc->recordMoveResult(4, MoveResult::TIMEOUT);
    mc->recordMoveResult(5, MoveResult::ERROR);
    mc->recordMoveResult(5, MoveResult::ERROR);
    mc->recordMoveResult(5, MoveResult::ERROR);

    EXPECT_EQ(mc->getConsecutiveMoveFailures(3), 2);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(4), 1);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(5), 3);

    EXPECT_EQ(mc->getCumulativeMoveFailures(3), 2);
    EXPECT_EQ(mc->getCumulativeMoveFailures(4), 1);
    EXPECT_EQ(mc->getCumulativeMoveFailures(5), 3);

    // Success on J3 resets only J3 consecutive
    mc->recordMoveResult(3, MoveResult::SUCCESS);
    EXPECT_EQ(mc->getConsecutiveMoveFailures(3), 0);
    EXPECT_EQ(mc->getCumulativeMoveFailures(3), 2);  // unchanged
    EXPECT_EQ(mc->getConsecutiveMoveFailures(5), 3);  // J5 unaffected
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: Height scan parameters loaded
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, HeightScanDisabledByDefault) {
    // joint2_init/height_scan_enable declared false — cycle with no detections
    // should NOT execute height scan (just skip gracefully)
    auto mc = makeController();
    auto provider = []() -> std::optional<std::vector<CottonDetection>> {
        return std::vector<CottonDetection>{};  // empty
    };
    ASSERT_TRUE(mc->initialize(provider));

    // Should return true without entering height scan
    EXPECT_TRUE(mc->executeOperationalCycle());
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: Average pick duration with zero attempts
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, AveragePickDurationZeroWhenNoAttempts) {
    auto mc = makeController();
    EXPECT_DOUBLE_EQ(mc->getAveragePickDurationMs(), 0.0);
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: Failure stats counters start at zero
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, FailureStatCountersStartAtZero) {
    auto mc = makeController();
    EXPECT_EQ(mc->getTfFailureCount(), 0);
    EXPECT_EQ(mc->getPositionFeedbackFailureCount(), 0);
    EXPECT_EQ(mc->getJointLimitFailureCount(), 0);
    EXPECT_EQ(mc->getPositionFeedbackFailureJ3(), 0);
    EXPECT_EQ(mc->getPositionFeedbackFailureJ4(), 0);
    EXPECT_EQ(mc->getPositionFeedbackFailureJ5(), 0);
    EXPECT_EQ(mc->getEeActivationCount(), 0);
    EXPECT_EQ(mc->getCompressorActivationCount(), 0);
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: EE/Compressor watchdog initial state
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(MotionControllerTest, EeAndCompressorInitiallyOff) {
    auto mc = makeController();
    EXPECT_FALSE(mc->isEeCurrentlyOn());
    EXPECT_FALSE(mc->isCompressorCurrentlyOn());
}

// ═════════════════════════════════════════════════════════════════════════════
// Log capture utility for testing RCLCPP_ERROR output
// ═════════════════════════════════════════════════════════════════════════════

namespace {
std::mutex g_captured_logs_mutex;
std::vector<std::string> g_captured_logs;
rcutils_logging_output_handler_t g_original_handler = nullptr;

void test_log_handler(
    const rcutils_log_location_t * location,
    int severity,
    const char * name,
    rcutils_time_point_value_t timestamp,
    const char * format,
    va_list * args)
{
    if (severity <= RCUTILS_LOG_SEVERITY_ERROR) {
        // va_copy is required: vsnprintf consumes the va_list, so passing
        // the original to the default handler afterward is UB (SIGSEGV).
        va_list args_copy;
        va_copy(args_copy, *args);
        char buffer[2048];
        vsnprintf(buffer, sizeof(buffer), format, args_copy);
        va_end(args_copy);
        std::lock_guard<std::mutex> lock(g_captured_logs_mutex);
        g_captured_logs.emplace_back(buffer);
    }
    // Also call original handler so logs still appear in test output
    if (g_original_handler) {
        g_original_handler(location, severity, name, timestamp, format, args);
    }
}

void install_log_capture() {
    std::lock_guard<std::mutex> lock(g_captured_logs_mutex);
    g_captured_logs.clear();
    g_original_handler = rcutils_logging_get_output_handler();
    rcutils_logging_set_output_handler(test_log_handler);
}

void remove_log_capture() {
    if (g_original_handler) {
        rcutils_logging_set_output_handler(g_original_handler);
        g_original_handler = nullptr;
    }
}

bool logs_contain(const std::string& substring) {
    std::lock_guard<std::mutex> lock(g_captured_logs_mutex);
    for (const auto& msg : g_captured_logs) {
        if (msg.find(substring) != std::string::npos) {
            return true;
        }
    }
    return false;
}
}  // namespace

// ═════════════════════════════════════════════════════════════════════════════
// 7.1  Empty catch block logs RCLCPP_ERROR with parameter name
// 7.2  Empty catch block assigns safe fallback (execution continues)
// Spec: critical-safety-fixes, item 1.5 — motion_controller.cpp:296
// ═════════════════════════════════════════════════════════════════════════════

/// Dedicated fixture for parameter read failure tests.
/// Uses its own node so we can set PRAGATI_INSTALL_DIR to a wrong type.
class MotionControllerParamFailureTest : public ::testing::Test {
protected:
    rclcpp::Node::SharedPtr node_;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j2_pub_;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j3_pub_;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j4_pub_;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j5_pub_;
    std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
    std::shared_ptr<tf2_ros::StaticTransformBroadcaster> tf_broadcaster_;
    std::unique_ptr<joint_move> jm3_;
    std::unique_ptr<joint_move> jm5_;
    std::unique_ptr<joint_move> jm4_;

    void SetUp() override {
        // Create node with unique name to avoid collision
        node_ = rclcpp::Node::make_shared("test_param_failure_node");

        // ─── Declare standard parameters needed for MotionController ───
        auto d = [this](const std::string& n, auto v) {
            if (!node_->has_parameter(n)) node_->declare_parameter(n, v);
        };
        d("simulation_mode", true);
        d("position_wait_mode", std::string("blind_sleep"));
        d("feedback_timeout", 1.0);
        d("end_effector_enable", false);
        // Enable calibration + preloaded centroids to trigger the code path
        d("YanthraLabCalibrationTesting", true);
        d("use_preloaded_centroids", true);
        d("enable_detection_retrigger", false);
        d("enable_post_cycle_parking", false);
        d("enable_l3_idle_parking", false);
        d("picking_strategy", std::string("none"));
        d("phi_compensation/enable", false);
        d("joint4_multiposition/enabled", false);
        d("joint3_init/homing_position", 0.00001);
        d("joint3_init/multiple_zero_poses", false);
        d("joint3_init/zero_poses", std::vector<double>{0.261799});
        d("joint3_init/min_length", -1.57);
        d("joint3_init/max_length", 1.57);
        d("joint3_init/parking_position", 0.3);
        d("joint4_init/homing_position", 0.00001);
        d("joint4_init/multiple_zero_poses", false);
        d("joint4_init/zero_poses", std::vector<double>{0.0});
        d("joint4_init/theta_jerk_value", 0.0);
        d("joint4_init/min_length", -0.175);
        d("joint4_init/max_length", 0.175);
        d("joint5_init/homing_position", 0.00001);
        d("joint5_init/end_effector_len", 0.085);
        d("joint5_init/joint5_vel_limit", 2.0);
        d("joint5_init/gear_ratio", 20.943951);
        d("joint5_init/phi_jerk_value", 0.0);
        d("joint5_init/hardware_offset", 0.320);
        d("joint5_init/min_length", 0.0);
        d("joint5_init/max_length", 0.6);
        d("joint2_init/height_scan_enable", false);
        d("joint2_init/min", 0.01);
        d("joint2_init/max", 0.85);
        d("joint2_init/step", 0.125);
        d("delays/picking", 0.0);
        d("delays/ee_pre_arrival_time", 0.0);
        d("delays/ee_post_retract_time", 0.0);
        d("delays/ee_start_distance", 0.025);
        d("delays/ee_stop_distance", 0.050);
        d("delays/use_dynamic_ee_prestart", false);
        d("delays/EERunTimeDuringL5ForwardMovement", 0.0);
        d("delays/EERunTimeDuringL5BackwardMovement", 0.0);
        d("delays/EERunTimeDuringReverseRotation", 0.0);
        d("delays/ee_post_joint5_delay", 0.0);
        d("min_sleep_time_formotor_motion", 0.01);
        d("inter_joint_delay", 0.01);
        d("cotton_settle_delay", 0.0);
        d("compressor_burst_duration", 0.0);
        d("enable_cotton_eject", false);
        d("enable_compressor_eject", false);
        d("j3_eject_position", -0.2);
        d("ee_motor2_eject_duration_ms", 0.0);
        d("ee_motor2_forward_flush_ms", 0.0);
        d("j3_eject_feedback_timeout_sec", 1.5);
        d("l2_homing_sleep_time", 0.0);
        d("l2_step_sleep_time", 0.0);
        d("l2_idle_sleep_time", 0.0);
        d("cotton_capture_detect_wait_time", 0.0);
        d("pick_cycle_timeout_sec", 15.0);

        // Declare PRAGATI_INSTALL_DIR as INTEGER (wrong type) to force
        // as_string() to throw rclcpp::ParameterTypeException
        d("PRAGATI_INSTALL_DIR", 12345);

        // Publishers
        j2_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint2_position_controller/command", 10);
        j3_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint3_position_controller/command", 10);
        j4_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint4_position_controller/command", 10);
        j5_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint5_position_controller/command", 10);
        joint_move::set_joint_publishers(j2_pub_, j3_pub_, j4_pub_, j5_pub_);

        // TF
        tf_buffer_ = std::make_shared<tf2_ros::Buffer>(node_->get_clock());
        tf_broadcaster_ = std::make_shared<tf2_ros::StaticTransformBroadcaster>(node_);
        geometry_msgs::msg::TransformStamped t;
        t.header.stamp = node_->get_clock()->now();
        t.header.frame_id = "yanthra_link";
        t.child_frame_id = "camera_link";
        t.transform.rotation.w = 1.0;
        tf_broadcaster_->sendTransform(t);
        tf_buffer_->setTransform(t, "test_authority", true);

        // Joint moves
        jm3_ = std::make_unique<joint_move>(node_, "joint3");
        jm5_ = std::make_unique<joint_move>(node_, "joint5");
        jm4_ = std::make_unique<joint_move>(node_, "joint4");

        yanthra_move::simulation_mode.store(true);
    }

    void TearDown() override {
        jm3_.reset();
        jm5_.reset();
        jm4_.reset();
        joint_move::cleanup_static_resources();
        j2_pub_.reset();
        j3_pub_.reset();
        j4_pub_.reset();
        j5_pub_.reset();
        tf_broadcaster_.reset();
        tf_buffer_.reset();
        node_.reset();
    }

    std::unique_ptr<MotionController> makeController() {
        return std::make_unique<MotionController>(
            node_, jm3_.get(), jm5_.get(), jm4_.get(), tf_buffer_);
    }
};

// Task 7.1: Catch block at motion_controller.cpp:296 logs RCLCPP_ERROR
// with parameter name when as_string() throws on wrong type.
TEST_F(MotionControllerParamFailureTest, ParameterReadFailureLogsError) {
    install_log_capture();

    auto mc = makeController();
    auto provider = []() -> std::optional<std::vector<CottonDetection>> {
        return std::vector<CottonDetection>{};
    };
    mc->initialize(provider);
    // This triggers executeOperationalCycle → ArUco path → try/catch at line 296
    mc->executeOperationalCycle();

    remove_log_capture();

    // Verify that an error was logged mentioning the parameter name
    EXPECT_TRUE(logs_contain("PRAGATI_INSTALL_DIR"))
        << "Expected RCLCPP_ERROR mentioning 'PRAGATI_INSTALL_DIR' parameter name";
}

// Task 7.2: Catch block assigns safe fallback (execution continues
// without crash, other search paths are still used).
TEST_F(MotionControllerParamFailureTest, ParameterReadFailureContinuesWithFallback) {
    auto mc = makeController();
    auto provider = []() -> std::optional<std::vector<CottonDetection>> {
        return std::vector<CottonDetection>{};
    };
    mc->initialize(provider);
    // Should not crash even though PRAGATI_INSTALL_DIR has wrong type
    EXPECT_NO_THROW(mc->executeOperationalCycle());
}

// ═════════════════════════════════════════════════════════════════════════════
// main — custom main to manage rclcpp lifecycle
// ═════════════════════════════════════════════════════════════════════════════

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int ret = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return ret;
}
