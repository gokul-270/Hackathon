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
 * @file trajectory_planner_test.cpp
 * @brief RED tests for TrajectoryPlanner — pure computation class
 * @details Tests the plan() pipeline, input validation, TF failure handling,
 *          joint limit enforcement, phi compensation, and planning latency.
 *
 *          This is a RED test file: TrajectoryPlanner does not exist yet.
 *          The tests define the expected interface and behavior.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/static_transform_broadcaster.h>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>

#include "yanthra_move/core/trajectory_planner.hpp"
#include "yanthra_move/core/planned_trajectory.hpp"
#include "yanthra_move/core/joint_config_types.hpp"

#include <chrono>
#include <cmath>
#include <limits>

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

using yanthra_move::core::JointLimits;
using yanthra_move::core::PhiCompensationParams;
using yanthra_move::core::PlanError;
using yanthra_move::core::PlanningParams;
using yanthra_move::core::PlannedTrajectory;
using yanthra_move::core::PlanResult;
using yanthra_move::core::TrajectoryPlanner;

// ═══════════════════════════════════════════════════════════════════════════════
// TEST FIXTURE
// ═══════════════════════════════════════════════════════════════════════════════

class TrajectoryPlannerTest : public ::testing::Test {
protected:
    static rclcpp::Node::SharedPtr node_;
    static std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
    static std::shared_ptr<tf2_ros::StaticTransformBroadcaster> tf_broadcaster_;

    // Joint limits: J3 [-1.57, 1.57], J4 [-0.175, 0.175], J5 [0.0, 0.6]
    JointLimits j3_limits_;
    JointLimits j4_limits_;
    JointLimits j5_limits_;
    PlanningParams default_params_;

    // ─────────────────────────────────────────────────────────────────────────
    // SetUpTestSuite — create node, TF buffer with identity transform once
    // ─────────────────────────────────────────────────────────────────────────
    static void SetUpTestSuite() {
        node_ = rclcpp::Node::make_shared("test_trajectory_planner");

        tf_buffer_ = std::make_shared<tf2_ros::Buffer>(node_->get_clock());
        tf_broadcaster_ =
            std::make_shared<tf2_ros::StaticTransformBroadcaster>(node_);

        // Publish a camera_link → yanthra_link identity transform so that
        // TF lookups inside TrajectoryPlanner succeed.
        geometry_msgs::msg::TransformStamped t;
        t.header.stamp = node_->get_clock()->now();
        t.header.frame_id = "yanthra_link";
        t.child_frame_id = "camera_link";
        t.transform.rotation.w = 1.0;  // identity quaternion
        tf_broadcaster_->sendTransform(t);

        // Also inject directly into buffer for immediate availability
        tf_buffer_->setTransform(t, "test_authority", /*is_static=*/true);

        yanthra_move::simulation_mode.store(true);
    }

    static void TearDownTestSuite() {
        yanthra_move::simulation_mode.store(false);
        tf_broadcaster_.reset();
        tf_buffer_.reset();
        node_.reset();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Per-test setup: fresh joint limits and default params
    // ─────────────────────────────────────────────────────────────────────────
    void SetUp() override {
        j3_limits_.min = -1.57;
        j3_limits_.max = 1.57;
        j3_limits_.loaded = true;

        j4_limits_.min = -0.175;
        j4_limits_.max = 0.175;
        j4_limits_.loaded = true;

        j5_limits_.min = 0.0;
        j5_limits_.max = 0.6;
        j5_limits_.loaded = true;

        default_params_.current_j4_offset = 0.0;
        default_params_.ee_length = 0.085;
        default_params_.j5_vel_limit = 2.0;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────────

    /// Build a TrajectoryPlanner wired to the shared TF buffer.
    std::unique_ptr<TrajectoryPlanner> makePlanner() {
        return std::make_unique<TrajectoryPlanner>(
            tf_buffer_, node_->get_logger());
    }

    /// Build a TrajectoryPlanner with an empty TF buffer (no transforms set)
    /// to trigger TF_FAILURE.
    std::unique_ptr<TrajectoryPlanner> makePlannerWithEmptyTf() {
        auto empty_buffer =
            std::make_shared<tf2_ros::Buffer>(node_->get_clock());
        return std::make_unique<TrajectoryPlanner>(
            empty_buffer, node_->get_logger());
    }

    /// Make a geometry_msgs::msg::Point.
    static geometry_msgs::msg::Point makePoint(double x, double y, double z) {
        geometry_msgs::msg::Point p;
        p.x = x;
        p.y = y;
        p.z = z;
        return p;
    }

    /// A known-good reachable target in camera frame.
    /// With identity TF, camera coords == arm coords.
    /// Polar conversion: r = sqrt(x²+z²), theta = y, phi = asin(z/r)
    /// (0.5, 0.02, 0.0) → r = 0.5, theta = 0.02, phi = 0.0
    /// j5_cmd = r - offset = 0.5 - 0.320 = 0.18 (within [0, 0.588])
    /// j4_cmd = theta = 0.02 (within [-0.1715, 0.1715])
    /// j3_cmd = phi * RAD_TO_ROT = 0.0 (within [-1.57, 1.57])
    static geometry_msgs::msg::Point reachableTarget() {
        return makePoint(0.5, 0.02, 0.0);
    }
};

// Static member definitions
rclcpp::Node::SharedPtr TrajectoryPlannerTest::node_;
std::shared_ptr<tf2_ros::Buffer> TrajectoryPlannerTest::tf_buffer_;
std::shared_ptr<tf2_ros::StaticTransformBroadcaster>
    TrajectoryPlannerTest::tf_broadcaster_;

// ═════════════════════════════════════════════════════════════════════════════
// 1. plan() with valid known-good input returns Status::OK and valid trajectory
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanWithValidInputReturnsOk) {
    auto planner = makePlanner();
    auto target = reachableTarget();

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::OK);
    // Trajectory fields should be finite (not NaN or Inf)
    EXPECT_TRUE(std::isfinite(result.trajectory.j3_command));
    EXPECT_TRUE(std::isfinite(result.trajectory.j4_command));
    EXPECT_TRUE(std::isfinite(result.trajectory.j5_command));
    EXPECT_TRUE(std::isfinite(result.trajectory.phi_deg));
    EXPECT_TRUE(std::isfinite(result.trajectory.l5_extension));
}

// ═════════════════════════════════════════════════════════════════════════════
// 2. plan() with NaN coordinates returns PlanError::INVALID_COORDINATES
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanWithNanXReturnsInvalidCoordinates) {
    auto planner = makePlanner();
    auto target = makePoint(std::numeric_limits<double>::quiet_NaN(), 0.1, 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::INVALID_COORDINATES);
}

TEST_F(TrajectoryPlannerTest, PlanWithNanYReturnsInvalidCoordinates) {
    auto planner = makePlanner();
    auto target = makePoint(0.3, std::numeric_limits<double>::quiet_NaN(), 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::INVALID_COORDINATES);
}

TEST_F(TrajectoryPlannerTest, PlanWithNanZReturnsInvalidCoordinates) {
    auto planner = makePlanner();
    auto target = makePoint(0.3, 0.0, std::numeric_limits<double>::quiet_NaN());

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::INVALID_COORDINATES);
}

// ═════════════════════════════════════════════════════════════════════════════
// 3. plan() with zero (0,0,0) coordinates returns PlanError::INVALID_COORDINATES
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanWithZeroCoordinatesReturnsInvalidCoordinates) {
    auto planner = makePlanner();
    auto target = makePoint(0.0, 0.0, 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::INVALID_COORDINATES);
}

// ═════════════════════════════════════════════════════════════════════════════
// 4. plan() when TF lookup fails returns PlanError::TF_FAILURE
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanWithNoTfReturnsFailure) {
    auto planner = makePlannerWithEmptyTf();
    auto target = reachableTarget();

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::TF_FAILURE);
}

// ═════════════════════════════════════════════════════════════════════════════
// 5. plan() with target outside J5 extension limits → JOINT_LIMIT_EXCEEDED
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanBeyondJ5MaxReturnsJointLimitExceeded) {
    auto planner = makePlanner();

    // Target far away — r ≈ 1.5 m, well beyond J5 max of 0.6 m
    auto target = makePoint(1.5, 0.0, 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::JOINT_LIMIT_EXCEEDED);
}

// ═════════════════════════════════════════════════════════════════════════════
// 6. plan() with target outside J3 phi limits → JOINT_LIMIT_EXCEEDED
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanBeyondJ3PhiLimitReturnsJointLimitExceeded) {
    auto planner = makePlanner();

    // Narrow J3 limits to force a phi violation: j3_cmd must be within [-0.01, 0.01] rot
    JointLimits narrow_j3;
    narrow_j3.min = -0.01;
    narrow_j3.max = 0.01;
    narrow_j3.loaded = true;

    // Polar mapping: phi = asin(z / sqrt(x²+z²)), j3_cmd = phi * RAD_TO_ROT
    // Target (0.4, 0.0, 0.4) → r = 0.5657, theta = 0.0, phi = 0.7854 rad (45°)
    // j3_cmd = 0.7854 / (2π) ≈ 0.125 rot — exceeds narrow J3 limit of ±0.01 rot
    // theta = 0.0 keeps J4 within default limits; r = 0.5657 keeps J5 within limits
    // Check order: reachability → J3 → J4 → J5, so J3 triggers first
    auto target = makePoint(0.4, 0.0, 0.4);

    PlanResult result =
        planner->plan(target, narrow_j3, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::JOINT_LIMIT_EXCEEDED);
}

// ═════════════════════════════════════════════════════════════════════════════
// 7. Phi compensation: disabled → trajectory unchanged vs no compensation
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PhiCompensationDisabledDoesNotModifyTrajectory) {
    auto planner = makePlanner();
    auto target = reachableTarget();

    // Plan without any phi compensation set (default is disabled)
    PlanResult baseline =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);
    ASSERT_EQ(baseline.status, PlanResult::Status::OK);

    // Explicitly set phi compensation disabled
    PhiCompensationParams disabled_params;
    disabled_params.enabled = false;
    planner->setPhiCompensation(disabled_params);

    PlanResult after_disable =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);
    ASSERT_EQ(after_disable.status, PlanResult::Status::OK);

    // Trajectories should be identical
    EXPECT_DOUBLE_EQ(baseline.trajectory.j3_command,
                     after_disable.trajectory.j3_command);
    EXPECT_DOUBLE_EQ(baseline.trajectory.j4_command,
                     after_disable.trajectory.j4_command);
    EXPECT_DOUBLE_EQ(baseline.trajectory.j5_command,
                     after_disable.trajectory.j5_command);
    EXPECT_DOUBLE_EQ(baseline.trajectory.l5_extension,
                     after_disable.trajectory.l5_extension);
}

// ═════════════════════════════════════════════════════════════════════════════
// 8. Phi compensation: enabled with zone1 params modifies trajectory
//    for low-phi targets
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest,
       PhiCompensationEnabledModifiesTrajectoryForLowPhi) {
    auto planner = makePlanner();

    // Target with small phi angle: (0.5, 0.05, 0.0) → phi = 0.0°
    // Phi compensation with non-zero offset will still modify j3_command
    // r = 0.5, j5_cmd = 0.18 (within limits), theta = 0.05 (within J4)
    auto target = makePoint(0.5, 0.05, 0.0);

    // Plan without compensation
    PlanResult no_comp =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);
    ASSERT_EQ(no_comp.status, PlanResult::Status::OK);

    // Enable phi compensation with non-trivial zone1 params
    PhiCompensationParams comp_params;
    comp_params.enabled = true;
    comp_params.zone1_max_deg = 30.0;
    comp_params.zone2_max_deg = 60.0;
    comp_params.zone1_slope = 0.5;
    comp_params.zone1_offset = 0.1;
    comp_params.zone2_slope = 0.3;
    comp_params.zone2_offset = 0.05;
    comp_params.zone3_slope = 0.1;
    comp_params.zone3_offset = 0.02;
    comp_params.l5_scale = 0.5;
    planner->setPhiCompensation(comp_params);

    PlanResult with_comp =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);
    ASSERT_EQ(with_comp.status, PlanResult::Status::OK);

    // At least one trajectory field should differ when compensation is active
    bool trajectory_changed =
        (no_comp.trajectory.j3_command != with_comp.trajectory.j3_command) ||
        (no_comp.trajectory.j5_command != with_comp.trajectory.j5_command) ||
        (no_comp.trajectory.l5_extension != with_comp.trajectory.l5_extension);
    EXPECT_TRUE(trajectory_changed)
        << "Phi compensation enabled with zone1 params should modify "
           "trajectory (non-zero offset produces compensation even at phi=0°)";
}

// ═════════════════════════════════════════════════════════════════════════════
// 9. Planning latency: plan() completes within 10ms for valid input
//    (excludes TF wait — buffer already has the transform)
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanCompletesWithin10ms) {
    auto planner = makePlanner();
    auto target = reachableTarget();

    // Warm up: ensure any lazy initialization is done
    planner->plan(target, j3_limits_, j4_limits_, j5_limits_, default_params_);

    // Measure over multiple iterations to get a stable measurement
    constexpr int iterations = 100;
    auto start = std::chrono::steady_clock::now();
    for (int i = 0; i < iterations; ++i) {
        PlanResult result =
            planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                          default_params_);
        // Prevent optimizer from eliding the call
        ASSERT_EQ(result.status, PlanResult::Status::OK);
    }
    auto end = std::chrono::steady_clock::now();

    auto avg_us = std::chrono::duration_cast<std::chrono::microseconds>(
                      end - start)
                      .count() /
                  iterations;

    // 10ms = 10000µs
    EXPECT_LT(avg_us, 10000)
        << "Average plan() latency " << avg_us
        << "µs exceeds 10ms target";
}

// ═════════════════════════════════════════════════════════════════════════════
// 10. plan() with target outside J4 theta limits → OUT_OF_REACH
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanBeyondJ4ThetaLimitReturnsOutOfReach) {
    auto planner = makePlanner();

    // Narrow J4 limits to force a theta violation: [-0.001, 0.001]
    JointLimits narrow_j4;
    narrow_j4.min = -0.001;
    narrow_j4.max = 0.001;
    narrow_j4.loaded = true;

    // Polar mapping: theta = y (direct), so Y drives J4 command.
    // Target at (0.5, 0.15, 0.0) → r = 0.5, theta = 0.15, phi = 0.0
    // j4_cmd = 0.15, well beyond narrow J4 limits of ±0.001
    // j5_cmd = 0.5 - 0.320 = 0.18 (within J5 limits)
    // j3_cmd = 0.0 (within J3 limits)
    // Check order: reachability → J3 → J4 → J5, so J4 triggers with OUT_OF_REACH
    auto target = makePoint(0.5, 0.15, 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, narrow_j4, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::OUT_OF_REACH);
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: setHardwareParams does not throw
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, SetHardwareParamsDoesNotThrow) {
    auto planner = makePlanner();

    EXPECT_NO_THROW(planner->setHardwareParams(
        /*j5_hardware_offset=*/0.320,
        /*j3_transmission=*/1.0,
        /*j4_transmission=*/1.0,
        /*j5_transmission=*/20.943951,
        /*j3_direction=*/1.0,
        /*j4_direction=*/1.0,
        /*j5_direction=*/1.0));
}

// ═════════════════════════════════════════════════════════════════════════════
// ADDITIONAL: plan() with Inf coordinates returns INVALID_COORDINATES
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanWithInfCoordinatesReturnsInvalidCoordinates) {
    auto planner = makePlanner();
    auto target = makePoint(std::numeric_limits<double>::infinity(), 0.1, 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::INVALID_COORDINATES);
}

// ═════════════════════════════════════════════════════════════════════════════
// 11. plan() success populates polar coordinate fields (Gap 1, Task 1.7)
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanSuccess_PopulatesPolarFields) {
    auto planner = makePlanner();
    auto target = reachableTarget();  // (0.5, 0.02, 0.0)

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    ASSERT_EQ(result.status, PlanResult::Status::OK);

    // Radius must be positive for any valid non-origin point
    EXPECT_GT(result.trajectory.polar_r, 0.0);
    // For (0.5, 0.02, 0.0) with identity TF: r = 0.5, theta = 0.02, phi = 0.0
    EXPECT_DOUBLE_EQ(result.trajectory.polar_r, 0.5);
    EXPECT_DOUBLE_EQ(result.trajectory.polar_theta, 0.02);
    EXPECT_DOUBLE_EQ(result.trajectory.polar_phi, 0.0);

    // All polar fields must be finite
    EXPECT_TRUE(std::isfinite(result.trajectory.polar_r));
    EXPECT_TRUE(std::isfinite(result.trajectory.polar_theta));
    EXPECT_TRUE(std::isfinite(result.trajectory.polar_phi));
}

// ═════════════════════════════════════════════════════════════════════════════
// 12. plan() failure from NaN input leaves polar fields at zero (Gap 1, Task 1.8)
//     NaN triggers INVALID_COORDINATES before polar conversion runs.
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanFailureNaN_PolarFieldsZero) {
    auto planner = makePlanner();
    auto target = makePoint(std::numeric_limits<double>::quiet_NaN(), 0.1, 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    ASSERT_EQ(result.status, PlanResult::Status::ERROR);
    ASSERT_EQ(result.error, PlanError::INVALID_COORDINATES);

    // Polar conversion never ran — fields stay at struct defaults (0.0)
    EXPECT_DOUBLE_EQ(result.trajectory.polar_r, 0.0);
    EXPECT_DOUBLE_EQ(result.trajectory.polar_theta, 0.0);
    EXPECT_DOUBLE_EQ(result.trajectory.polar_phi, 0.0);
}

// ═════════════════════════════════════════════════════════════════════════════
// 13. plan() failure from TF lookup leaves polar fields at zero (Gap 1, Task 1.8)
//     TF_FAILURE triggers before polar conversion runs.
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanFailureTf_PolarFieldsZero) {
    auto planner = makePlannerWithEmptyTf();
    auto target = reachableTarget();

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    ASSERT_EQ(result.status, PlanResult::Status::ERROR);
    ASSERT_EQ(result.error, PlanError::TF_FAILURE);

    // Polar conversion never ran — fields stay at struct defaults (0.0)
    EXPECT_DOUBLE_EQ(result.trajectory.polar_r, 0.0);
    EXPECT_DOUBLE_EQ(result.trajectory.polar_theta, 0.0);
    EXPECT_DOUBLE_EQ(result.trajectory.polar_phi, 0.0);
}

// ═════════════════════════════════════════════════════════════════════════════
// 14. plan() failure from J5 limit exceeded still populates polar fields
//     (Gap 1, Task 1.8) — polar conversion runs before the limit check.
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanFailureJointLimit_PolarFieldsPopulated) {
    auto planner = makePlanner();

    // Target far away — r ≈ 1.5 m, beyond J5 max of 0.6 m.
    // Polar conversion succeeds, then J5 limit check fails.
    auto target = makePoint(1.5, 0.0, 0.0);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    ASSERT_EQ(result.status, PlanResult::Status::ERROR);
    ASSERT_EQ(result.error, PlanError::JOINT_LIMIT_EXCEEDED);

    // Polar conversion DID run — fields should reflect the actual computation
    EXPECT_GT(result.trajectory.polar_r, 0.0);
    EXPECT_DOUBLE_EQ(result.trajectory.polar_r, 1.5);
    EXPECT_TRUE(std::isfinite(result.trajectory.polar_theta));
    EXPECT_TRUE(std::isfinite(result.trajectory.polar_phi));
}

// ═════════════════════════════════════════════════════════════════════════════
// 15. plan() failure from J3 limit exceeded still populates polar fields
//     (Gap 1, Task 1.8) — polar conversion runs before J3 limit check.
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanFailureJ3Limit_PolarFieldsPopulated) {
    auto planner = makePlanner();

    // Reuse the narrow J3 limit scenario from test #6
    JointLimits narrow_j3;
    narrow_j3.min = -0.01;
    narrow_j3.max = 0.01;
    narrow_j3.loaded = true;

    // (0.4, 0.0, 0.4) → r ≈ 0.5657, phi ≈ 0.7854 rad
    auto target = makePoint(0.4, 0.0, 0.4);

    PlanResult result =
        planner->plan(target, narrow_j3, j4_limits_, j5_limits_,
                      default_params_);

    ASSERT_EQ(result.status, PlanResult::Status::ERROR);
    ASSERT_EQ(result.error, PlanError::JOINT_LIMIT_EXCEEDED);

    // Polar fields should be non-zero — the conversion ran successfully
    EXPECT_GT(result.trajectory.polar_r, 0.0);
    EXPECT_NEAR(result.trajectory.polar_r, std::sqrt(0.4 * 0.4 + 0.4 * 0.4),
                1e-6);
    EXPECT_TRUE(std::isfinite(result.trajectory.polar_theta));
    EXPECT_NE(result.trajectory.polar_phi, 0.0);  // phi ≈ 0.7854 rad
}

// ═════════════════════════════════════════════════════════════════════════════
// 16. plan() success populates j3/j4/j5 command fields (Gap 1, Task 1.9)
//     These are the values that flow to plan_j3_cmd_, plan_j4_cmd_,
//     plan_j5_cmd_ in MotionController for pick_complete JSON.
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanSuccess_PopulatesJointCommandFields) {
    auto planner = makePlanner();
    auto target = reachableTarget();  // (0.5, 0.02, 0.0)

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    ASSERT_EQ(result.status, PlanResult::Status::OK);

    // j5_command = r - j5_hardware_offset = 0.5 - 0.320 = 0.18
    EXPECT_NEAR(result.trajectory.j5_command, 0.18, 0.01);
    EXPECT_TRUE(std::isfinite(result.trajectory.j5_command));

    // j4_command = theta = 0.02 (no J4 offset in default_params_)
    EXPECT_DOUBLE_EQ(result.trajectory.j4_command, 0.02);
    EXPECT_TRUE(std::isfinite(result.trajectory.j4_command));

    // j3_command = phi * RAD_TO_ROT = 0.0 (phi is 0 for z=0)
    EXPECT_DOUBLE_EQ(result.trajectory.j3_command, 0.0);
    EXPECT_TRUE(std::isfinite(result.trajectory.j3_command));
}

// ═════════════════════════════════════════════════════════════════════════════
// 17. plan() success with non-zero phi produces non-zero j3 command
//     (Gap 1, Task 1.9) — ensures j3 is not always zero.
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(TrajectoryPlannerTest, PlanSuccess_NonZeroPhi_NonZeroJ3Command) {
    auto planner = makePlanner();

    // Target with moderate phi: (0.4, 0.02, 0.15)
    // r = sqrt(0.16 + 0.0225) ≈ 0.427, phi = asin(0.15/0.427) ≈ 0.358 rad
    // j3_cmd = 0.358 * RAD_TO_ROT ≈ 0.057 (within J3 limits of ±1.57)
    // j5_cmd = 0.427 - 0.320 = 0.107 (within J5 limits)
    // j4_cmd = 0.02 (within J4 limits)
    auto target = makePoint(0.4, 0.02, 0.15);

    PlanResult result =
        planner->plan(target, j3_limits_, j4_limits_, j5_limits_,
                      default_params_);

    ASSERT_EQ(result.status, PlanResult::Status::OK);

    // j3 must be non-zero when phi is non-zero
    EXPECT_NE(result.trajectory.j3_command, 0.0);
    EXPECT_TRUE(std::isfinite(result.trajectory.j3_command));

    // j4 and j5 should also be populated
    EXPECT_NE(result.trajectory.j4_command, 0.0);
    EXPECT_GT(result.trajectory.j5_command, 0.0);

    // Polar fields should match
    EXPECT_GT(result.trajectory.polar_r, 0.0);
    EXPECT_NE(result.trajectory.polar_phi, 0.0);
}

// ═════════════════════════════════════════════════════════════════════════════
// J5 COLLISION AVOIDANCE TESTS
// ═════════════════════════════════════════════════════════════════════════════

// Test: Collision avoidance disabled by default — J5 NOT clamped
TEST_F(TrajectoryPlannerTest, CollisionAvoidanceDisabledByDefault) {
    auto planner = makePlanner();
    // Default: collision_avoidance_enabled_ = false
    // Target producing J3≈0 and J5 > 0.17m
    auto target = makePoint(0.6, 0.0, 0.0);  // r=0.6 → j5=0.28, j3=0.0

    PlanResult result = planner->plan(target, j3_limits_, j4_limits_, j5_limits_, default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::OK);
    // Without collision avoidance, J5 should be unclamped (~0.28m)
    EXPECT_GT(result.trajectory.j5_command, 0.17);
}

// Test: Collision avoidance enabled — J5 blocked at J3≈0 (pick skipped)
TEST_F(TrajectoryPlannerTest, CollisionAvoidanceBlocksJ5AtJ3Zero) {
    auto planner = makePlanner();
    planner->setCollisionAvoidanceParams(true, 0.17);

    // Target producing J3≈0 (phi≈0) and J5 > 0.17m
    auto target = makePoint(0.6, 0.0, 0.0);  // r=0.6 → j5=0.28, j3≈0.0

    PlanResult result = planner->plan(target, j3_limits_, j4_limits_, j5_limits_, default_params_);

    // With collision avoidance at J3≈0: limit = 0.17/cos(0) = 0.17m
    // J5=0.28 > 0.17 → BLOCKED (pick skipped, not clamped)
    EXPECT_EQ(result.status, PlanResult::Status::ERROR);
    EXPECT_EQ(result.error, PlanError::COLLISION_BLOCKED);
    EXPECT_TRUE(result.trajectory.collision_j5_clamped);
    EXPECT_TRUE(result.trajectory.collision_avoidance_active);
    EXPECT_NEAR(result.trajectory.collision_j5_limit, 0.17, 0.01);
}

// Test: Collision avoidance enabled but J5 within limit — no clamp
TEST_F(TrajectoryPlannerTest, CollisionAvoidanceNoClampWhenWithinLimit) {
    auto planner = makePlanner();
    planner->setCollisionAvoidanceParams(true, 0.17);

    // Target producing small J5 (well within 0.17m limit)
    auto target = makePoint(0.45, 0.0, 0.0);  // r=0.45 → j5=0.13, j3≈0.0

    PlanResult result = planner->plan(target, j3_limits_, j4_limits_, j5_limits_, default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::OK);
    // J5=0.13 < 0.17 limit → no clamp, value preserved
    EXPECT_NEAR(result.trajectory.j5_command, 0.13, 0.02);
}

// Test: Collision avoidance explicitly disabled — no clamp effect
TEST_F(TrajectoryPlannerTest, CollisionAvoidanceNoEffectWhenDisabled) {
    auto planner = makePlanner();
    planner->setCollisionAvoidanceParams(false, 0.17);

    auto target = makePoint(0.6, 0.0, 0.0);  // j5=0.28, j3≈0.0

    PlanResult result = planner->plan(target, j3_limits_, j4_limits_, j5_limits_, default_params_);

    EXPECT_EQ(result.status, PlanResult::Status::OK);
    EXPECT_GT(result.trajectory.j5_command, 0.17);  // NOT clamped
}

// Test: setCollisionAvoidanceParams does not throw
TEST_F(TrajectoryPlannerTest, SetCollisionAvoidanceParamsDoesNotThrow) {
    auto planner = makePlanner();
    EXPECT_NO_THROW(planner->setCollisionAvoidanceParams(true, 0.17));
    EXPECT_NO_THROW(planner->setCollisionAvoidanceParams(false, 0.0));
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN — initialise ROS2 context before running tests
// ═════════════════════════════════════════════════════════════════════════════

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int ret = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return ret;
}
