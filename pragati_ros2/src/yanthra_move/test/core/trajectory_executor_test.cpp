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
 * @file trajectory_executor_test.cpp
 * @brief RED tests for TrajectoryExecutor — motor command sequencing
 * @details Tests construction, joint ordering (J4→J3→J5 approach, J5-first
 *          retreat), home/packing/parking moves, sub-phase timing, and
 *          failure propagation.
 *
 *          This is a RED test file: the header
 *          yanthra_move/core/trajectory_executor.hpp and its implementation
 *          do not exist yet.  The tests must compile but will FAIL to link
 *          until the class is created.
 *
 *          Runs entirely in simulation mode with blind_sleep position wait
 *          to avoid hardware and service dependencies.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float64.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>

#include "yanthra_move/core/trajectory_executor.hpp"
#include "yanthra_move/core/planned_trajectory.hpp"
#include "yanthra_move/joint_move.h"

#include <atomic>
#include <chrono>
#include <future>
#include <map>
#include <string>
#include <thread>
#include <vector>

// =============================================================================
// PROVIDE EXTERN SYMBOLS
// =============================================================================
// These symbols are normally defined in yanthra_move_system_core.cpp and
// yanthra_utilities.cpp.  We define them here so the test binary links without
// pulling in the full system node (same pattern as test_motion_controller.cpp).
// =============================================================================

namespace yanthra_move {
std::atomic<bool> simulation_mode{true};
std::atomic<bool> executor_running{false};
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor{nullptr};
std::shared_ptr<rclcpp::Node> global_node{nullptr};
std::thread executor_thread;
}  // namespace yanthra_move

using yanthra_move::core::TrajectoryExecutor;
using yanthra_move::core::ApproachParams;
using yanthra_move::core::RetreatParams;
using yanthra_move::core::PlannedTrajectory;

// =============================================================================
// TRACKING MOCK — records move_joint calls for order verification
// =============================================================================
// We wrap joint_move instances and record calls in a shared log vector so that
// tests can assert on joint command ordering (J4→J3→J5 for approach, etc.).
// Since joint_move::move_joint is the actual method called by TrajectoryExecutor,
// and in simulation mode it returns SUCCESS immediately, the tracking is done
// by subscribing to the command topics published by joint_move.
// =============================================================================

namespace {

struct MoveRecord {
    std::string joint_name;
    double position;
    std::chrono::steady_clock::time_point timestamp;
};

/// Thread-safe move log shared across subscriber callbacks.
std::mutex g_move_log_mutex;
std::vector<MoveRecord> g_move_log;

void clearMoveLog() {
    std::lock_guard<std::mutex> lock(g_move_log_mutex);
    g_move_log.clear();
}

std::vector<MoveRecord> getMoveLog() {
    std::lock_guard<std::mutex> lock(g_move_log_mutex);
    return g_move_log;
}

/// Extract the ordered joint names from the move log.
std::vector<std::string> getMoveOrder() {
    auto log = getMoveLog();
    std::vector<std::string> order;
    order.reserve(log.size());
    for (const auto& rec : log) {
        order.push_back(rec.joint_name);
    }
    return order;
}

void recordMove(const std::string& joint_name, double position) {
    std::lock_guard<std::mutex> lock(g_move_log_mutex);
    g_move_log.push_back(
        {joint_name, position, std::chrono::steady_clock::now()});
}

bool approximatelyEqual(double lhs, double rhs, double tolerance = 1e-6) {
    return std::abs(lhs - rhs) <= tolerance;
}

}  // namespace

// =============================================================================
// TEST FIXTURE
// =============================================================================

class TrajectoryExecutorTest : public ::testing::Test {
protected:
    // Shared across the entire test suite
    static rclcpp::Node::SharedPtr node_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j2_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j3_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j4_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j5_pub_;

    // Subscribers to capture command ordering
    static rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr j3_sub_;
    static rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr j4_sub_;
    static rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr j5_sub_;

    // Per-test joint_move instances
    std::unique_ptr<joint_move> jm3_;
    std::unique_ptr<joint_move> jm4_;
    std::unique_ptr<joint_move> jm5_;

    // ─────────────────────────────────────────────────────────────────────────
    // SetUpTestSuite — create node, publishers, subscribers once
    // ─────────────────────────────────────────────────────────────────────────
    static void SetUpTestSuite() {
        node_ = rclcpp::Node::make_shared("test_trajectory_executor");

        // ───────── Declare parameters needed for joint_move ─────────
        declareParam("simulation_mode", true);
        declareParam("position_wait_mode", std::string("blind_sleep"));
        declareParam("feedback_timeout", 1.0);
        declareParam("min_sleep_time_formotor_motion", 0.01);
        declareParam("inter_joint_delay", 0.01);

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

        // ───────── Subscribers to track command ordering ─────────
        j3_sub_ = node_->create_subscription<std_msgs::msg::Float64>(
            "joint3_position_controller/command", 10,
            [](const std_msgs::msg::Float64::SharedPtr msg) {
                recordMove("joint3", msg->data);
            });
        j4_sub_ = node_->create_subscription<std_msgs::msg::Float64>(
            "joint4_position_controller/command", 10,
            [](const std_msgs::msg::Float64::SharedPtr msg) {
                recordMove("joint4", msg->data);
            });
        j5_sub_ = node_->create_subscription<std_msgs::msg::Float64>(
            "joint5_position_controller/command", 10,
            [](const std_msgs::msg::Float64::SharedPtr msg) {
                recordMove("joint5", msg->data);
            });

        // Ensure simulation mode is on
        yanthra_move::simulation_mode.store(true);
    }

    static void TearDownTestSuite() {
        yanthra_move::simulation_mode.store(false);
        j3_sub_.reset();
        j4_sub_.reset();
        j5_sub_.reset();
        j2_pub_.reset();
        j3_pub_.reset();
        j4_pub_.reset();
        j5_pub_.reset();
        joint_move::cleanup_static_resources();
        node_.reset();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Per-test setup: fresh joint_move instances and clear tracking log
    // ─────────────────────────────────────────────────────────────────────────
    void SetUp() override {
        clearMoveLog();
        jm3_ = std::make_unique<joint_move>(node_, "joint3");
        jm4_ = std::make_unique<joint_move>(node_, "joint4");
        jm5_ = std::make_unique<joint_move>(node_, "joint5");
    }

    void TearDown() override {
        jm3_.reset();
        jm4_.reset();
        jm5_.reset();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────────

    /// Build a TrajectoryExecutor wired to the per-test joints.
    std::unique_ptr<TrajectoryExecutor> makeExecutor() {
        return std::make_unique<TrajectoryExecutor>(
            jm3_.get(), jm4_.get(), jm5_.get(), node_->get_logger());
    }

    /// Create a simple PlannedTrajectory with reachable target positions.
    static PlannedTrajectory makeSimpleTrajectory() {
        PlannedTrajectory traj;
        traj.j3_command = 0.3;   // phi — within [-1.57, 1.57]
        traj.j4_command = 0.05;  // theta — within [-0.175, 0.175]
        traj.j5_command = 0.25;  // r — within [0.0, 0.6]
        return traj;
    }

    /// Create default ApproachParams for fast simulation tests.
    static ApproachParams makeDefaultApproachParams() {
        ApproachParams params;
        params.inter_joint_delay = 0.01;
        params.min_sleep_time = 0.01;
        params.skip_j4 = false;
        params.position_wait_mode = "blind_sleep";
        params.position_feedback_timeout = 1.0;
        params.position_feedback_tolerance = 0.01;
        params.enable_l3_idle_parking = false;
        params.j3_parking_position = 0.008;
        return params;
    }

    /// Create default RetreatParams for fast simulation tests.
    static RetreatParams makeDefaultRetreatParams() {
        RetreatParams params;
        params.home_j5 = true;
        params.home_j3 = true;
        params.home_j4 = true;
        params.j3_home = 0.0;
        params.j5_home = 0.0;
        params.j4_home = 0.0;
        params.inter_joint_delay = 0.01;
        params.cotton_settle_delay = 0.01;
        params.compressor_burst_duration = 0.0;
        params.position_wait_mode = "blind_sleep";
        params.position_feedback_timeout = 1.0;
        params.position_feedback_tolerance = 0.01;
        params.enable_cotton_eject = false;
        params.enable_compressor_eject = false;
        params.j3_eject_position = -0.2;
        params.ee_motor2_eject_duration_ms = 0.0;
        params.ee_motor2_forward_flush_ms = 0.0;
        params.j3_eject_feedback_timeout_sec = 1.5;
        params.enable_l3_idle_parking = false;
        params.j3_parking_position = 0.008;
        return params;
    }

    /// Spin the node briefly to process subscription callbacks.
    void spinBriefly() {
        auto start = std::chrono::steady_clock::now();
        while (std::chrono::steady_clock::now() - start <
               std::chrono::milliseconds(50)) {
            rclcpp::spin_some(node_);
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }

    struct PositionObservation {
        bool observed{false};
        std::chrono::steady_clock::time_point timestamp{};
    };

    std::map<std::string, PositionObservation> observeJointUpdates(
        const std::vector<std::pair<std::string, std::pair<joint_move*, double>>>&
            targets,
        std::chrono::milliseconds timeout = std::chrono::milliseconds(500)) {
        std::map<std::string, PositionObservation> observations;
        const auto start = std::chrono::steady_clock::now();

        while (std::chrono::steady_clock::now() - start < timeout) {
            bool all_observed = true;
            const auto now = std::chrono::steady_clock::now();
            for (const auto& [joint_name, joint_target] : targets) {
                auto* joint = joint_target.first;
                const double target = joint_target.second;
                auto& obs = observations[joint_name];
                if (!obs.observed &&
                    approximatelyEqual(
                        joint->current_position_.load(std::memory_order_relaxed),
                        target)) {
                    obs.observed = true;
                    obs.timestamp = now;
                }
                all_observed = all_observed && obs.observed;
            }
            if (all_observed) {
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }

        return observations;
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
rclcpp::Node::SharedPtr TrajectoryExecutorTest::node_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr TrajectoryExecutorTest::j2_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr TrajectoryExecutorTest::j3_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr TrajectoryExecutorTest::j4_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr TrajectoryExecutorTest::j5_pub_;
rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr TrajectoryExecutorTest::j3_sub_;
rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr TrajectoryExecutorTest::j4_sub_;
rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr TrajectoryExecutorTest::j5_sub_;

// =============================================================================
// 1. Constructor creates instance without throwing (valid joint_move pointers)
// =============================================================================

TEST_F(TrajectoryExecutorTest, ConstructsWithoutThrowing) {
    EXPECT_NO_THROW({
        auto te = makeExecutor();
    });
}

// =============================================================================
// 2. Constructor throws with null J3 pointer
// =============================================================================

TEST_F(TrajectoryExecutorTest, ConstructorThrowsWithNullJ3) {
    EXPECT_THROW(
        TrajectoryExecutor(nullptr, jm4_.get(), jm5_.get(),
                           node_->get_logger()),
        std::invalid_argument);
}

TEST_F(TrajectoryExecutorTest, ConstructorThrowsWithNullJ4) {
    EXPECT_THROW(
        TrajectoryExecutor(jm3_.get(), nullptr, jm5_.get(),
                           node_->get_logger()),
        std::invalid_argument);
}

TEST_F(TrajectoryExecutorTest, ConstructorThrowsWithNullJ5) {
    EXPECT_THROW(
        TrajectoryExecutor(jm3_.get(), jm4_.get(), nullptr,
                           node_->get_logger()),
        std::invalid_argument);
}

// =============================================================================
// 3. executeApproach() commands joints in J4→J3→J5 order
// =============================================================================

TEST_F(TrajectoryExecutorTest, ApproachCommandsJointsInJ4J3J5Order) {
    auto te = makeExecutor();
    auto traj = makeSimpleTrajectory();
    auto params = makeDefaultApproachParams();
    auto future = std::async(std::launch::async, [&]() {
        return te->executeApproach(traj, params);
    });

    auto observations = observeJointUpdates({
        {"joint4", {jm4_.get(), traj.j4_command}},
        {"joint3", {jm3_.get(), traj.j3_command}},
        {"joint5", {jm5_.get(), traj.j5_command}},
    });

    EXPECT_TRUE(future.get());

    ASSERT_TRUE(observations["joint4"].observed)
        << "J4 target position was never observed";
    ASSERT_TRUE(observations["joint3"].observed)
        << "J3 target position was never observed";
    ASSERT_TRUE(observations["joint5"].observed)
        << "J5 target position was never observed";

    EXPECT_LT(observations["joint4"].timestamp, observations["joint3"].timestamp)
        << "J4 must be commanded before J3 during approach";
    EXPECT_LT(observations["joint3"].timestamp, observations["joint5"].timestamp)
        << "J3 must be commanded before J5 during approach";
}

// =============================================================================
// 4. executeApproach() with skip_j4=true omits J4 command
// =============================================================================

TEST_F(TrajectoryExecutorTest, ApproachSkipsJ4WhenFlagSet) {
    auto te = makeExecutor();
    auto traj = makeSimpleTrajectory();
    auto params = makeDefaultApproachParams();
    params.skip_j4 = true;

    bool result = te->executeApproach(traj, params);
    EXPECT_TRUE(result);
    EXPECT_TRUE(approximatelyEqual(
        jm4_->current_position_.load(std::memory_order_relaxed), 0.0))
        << "J4 should be omitted when skip_j4=true";
    EXPECT_TRUE(approximatelyEqual(
        jm3_->current_position_.load(std::memory_order_relaxed), traj.j3_command))
        << "J3 must still be commanded when skip_j4=true";
    EXPECT_TRUE(approximatelyEqual(
        jm5_->current_position_.load(std::memory_order_relaxed), traj.j5_command))
        << "J5 must still be commanded when skip_j4=true";
}

// =============================================================================
// 5. executeRetreat() commands J5 retract first, then J3/J4 home
// =============================================================================

TEST_F(TrajectoryExecutorTest, RetreatCommandsJ5FirstThenJ3J4) {
    auto te = makeExecutor();
    auto params = makeDefaultRetreatParams();
    params.j5_home = 0.11;
    params.j3_home = 0.22;
    params.j4_home = 0.07;

    auto future = std::async(std::launch::async, [&]() {
        return te->executeRetreat(params);
    });

    auto observations = observeJointUpdates({
        {"joint5", {jm5_.get(), params.j5_home}},
        {"joint3", {jm3_.get(), params.j3_home}},
        {"joint4", {jm4_.get(), params.j4_home}},
    });

    EXPECT_TRUE(future.get());

    ASSERT_TRUE(observations["joint5"].observed)
        << "J5 retract target position was never observed";
    ASSERT_TRUE(observations["joint3"].observed)
        << "J3 home target position was never observed";
    ASSERT_TRUE(observations["joint4"].observed)
        << "J4 home target position was never observed";

    EXPECT_LT(observations["joint5"].timestamp, observations["joint3"].timestamp)
        << "J5 must retract before J3 moves home during retreat";
    EXPECT_LT(observations["joint5"].timestamp, observations["joint4"].timestamp)
        << "J5 must retract before J4 moves home during retreat";
}

// =============================================================================
// 6. moveToHomePosition() commands all joints to home positions
// =============================================================================

TEST_F(TrajectoryExecutorTest, MoveToHomePositionCommandsAllJoints) {
    auto te = makeExecutor();
    const double j3_home = 0.0;
    const double j5_home = 0.0;
    const double j4_home = 0.0;

    EXPECT_NO_THROW(te->moveToHomePosition(j3_home, j5_home, j4_home));

    spinBriefly();

    auto log = getMoveLog();
    // All three joints should have received a command
    bool j3_found = false, j4_found = false, j5_found = false;
    for (const auto& rec : log) {
        if (rec.joint_name == "joint3") j3_found = true;
        if (rec.joint_name == "joint4") j4_found = true;
        if (rec.joint_name == "joint5") j5_found = true;
    }

    EXPECT_TRUE(j3_found) << "J3 must receive home command";
    EXPECT_TRUE(j4_found) << "J4 must receive home command";
    EXPECT_TRUE(j5_found) << "J5 must receive home command";
}

// =============================================================================
// 7. moveToPackingPosition() commands all joints and returns arrival status
// =============================================================================

TEST_F(TrajectoryExecutorTest, MoveToPackingPositionReturnsTrue) {
    auto te = makeExecutor();
    const double j3_home = 0.0;
    const double j5_home = 0.0;
    const double j4_home = 0.0;

    bool arrived = te->moveToPackingPosition(
        j3_home, j5_home, j4_home, "blind_sleep");
    EXPECT_TRUE(arrived);

    spinBriefly();

    auto log = getMoveLog();
    // All three joints should have received a command
    bool j3_found = false, j4_found = false, j5_found = false;
    for (const auto& rec : log) {
        if (rec.joint_name == "joint3") j3_found = true;
        if (rec.joint_name == "joint4") j4_found = true;
        if (rec.joint_name == "joint5") j5_found = true;
    }

    EXPECT_TRUE(j3_found) << "J3 must receive packing command";
    EXPECT_TRUE(j4_found) << "J4 must receive packing command";
    EXPECT_TRUE(j5_found) << "J5 must receive packing command";
}

// =============================================================================
// 8. Sub-phase timing: approach timing fields are set after executeApproach()
// =============================================================================

TEST_F(TrajectoryExecutorTest, ApproachTimingFieldsAreSetAfterExecution) {
    auto te = makeExecutor();
    auto traj = makeSimpleTrajectory();
    auto params = makeDefaultApproachParams();

    // Before execution, timing fields should be zero/default
    EXPECT_DOUBLE_EQ(te->getApproachJ3Ms(), 0.0);
    EXPECT_DOUBLE_EQ(te->getApproachJ4Ms(), 0.0);
    EXPECT_DOUBLE_EQ(te->getApproachJ5Ms(), 0.0);

    te->executeApproach(traj, params);

    // After execution, at least one timing field should be non-negative
    // (in simulation with tiny delays, values may be very small but >= 0)
    EXPECT_GE(te->getApproachJ3Ms(), 0.0);
    EXPECT_GE(te->getApproachJ4Ms(), 0.0);
    EXPECT_GE(te->getApproachJ5Ms(), 0.0);

    // At least J3 and J5 timings should be set (J4 is always commanded
    // unless skip_j4 is true)
    double total_approach_ms =
        te->getApproachJ3Ms() + te->getApproachJ4Ms() + te->getApproachJ5Ms();
    EXPECT_GT(total_approach_ms, 0.0)
        << "Total approach timing should be > 0 after executeApproach()";
}

TEST_F(TrajectoryExecutorTest, RetreatTimingFieldsAreSetAfterExecution) {
    auto te = makeExecutor();
    auto params = makeDefaultRetreatParams();

    te->executeRetreat(params);

    // Retreat timing for J5 should be non-negative
    EXPECT_GE(te->getRetreatJ5Ms(), 0.0);
}

// =============================================================================
// 9. L3 parking: moveL3ToParking() and moveL3ToHoming() don't crash
// =============================================================================

TEST_F(TrajectoryExecutorTest, MoveL3ToParkingDoesNotCrash) {
    auto te = makeExecutor();
    EXPECT_NO_THROW(te->moveL3ToParking(0.3));
}

TEST_F(TrajectoryExecutorTest, MoveL3ToHomingDoesNotCrash) {
    auto te = makeExecutor();
    EXPECT_NO_THROW(te->moveL3ToHoming(0.0));
}

// =============================================================================
// 10. Motors-unavailable: approach returns false if a motor move fails
// =============================================================================
// In simulation mode, move_joint always returns SUCCESS. To test the failure
// path, we set simulation_mode to false temporarily — without a real motor
// controller the move should fail (service unavailable → MoveResult::ERROR).
// =============================================================================

TEST_F(TrajectoryExecutorTest, ApproachReturnsFalseOnMotorFailure) {
    auto te = makeExecutor();
    auto traj = makeSimpleTrajectory();
    auto params = makeDefaultApproachParams();

    // Temporarily disable simulation mode so move_joint hits the real
    // service/action path which will fail (no motor controller running)
    yanthra_move::simulation_mode.store(false);

    bool result = te->executeApproach(traj, params);

    // Restore simulation mode before asserting (so TearDown is safe)
    yanthra_move::simulation_mode.store(true);

    EXPECT_FALSE(result)
        << "executeApproach() must return false when motor moves fail";
}

// =============================================================================
// ADDITIONAL: setRecoveryManager and setCaptureSequence don't crash
// =============================================================================

TEST_F(TrajectoryExecutorTest, SetRecoveryManagerAcceptsNullptr) {
    auto te = makeExecutor();
    // Setting nullptr should not crash (disables recovery tracking)
    EXPECT_NO_THROW(te->setRecoveryManager(nullptr));
}

TEST_F(TrajectoryExecutorTest, SetCaptureSequenceAcceptsNullptr) {
    auto te = makeExecutor();
    // Setting nullptr should not crash (disables EE coordination)
    EXPECT_NO_THROW(te->setCaptureSequence(nullptr));
}

// =============================================================================
// ADDITIONAL: waitForPositionFeedback returns true in blind_sleep mode
// =============================================================================

TEST_F(TrajectoryExecutorTest, WaitForPositionFeedbackReturnsTrueBlindSleep) {
    auto te = makeExecutor();
    // In blind_sleep mode, feedback check is a no-op that always succeeds
    bool ok = te->waitForPositionFeedback("joint3", 0.3, 0.01, 2.0);
    EXPECT_TRUE(ok);
}

// =============================================================================
// ADDITIONAL: moveToPackingPosition with position_feedback mode
// =============================================================================

TEST_F(TrajectoryExecutorTest, MoveToPackingPositionWithFeedbackMode) {
    auto te = makeExecutor();
    // In simulation mode, even "position_feedback" should succeed
    // (simulation always reports target reached)
    bool arrived = te->moveToPackingPosition(
        0.0, 0.0, 0.0, "position_feedback");
    EXPECT_TRUE(arrived);
}

// =============================================================================
// ADDITIONAL: Approach with all-zero trajectory
// =============================================================================

TEST_F(TrajectoryExecutorTest, ApproachWithZeroTrajectorySucceeds) {
    auto te = makeExecutor();
    PlannedTrajectory traj;
    traj.j3_command = 0.0;
    traj.j4_command = 0.0;
    traj.j5_command = 0.0;
    auto params = makeDefaultApproachParams();

    bool result = te->executeApproach(traj, params);
    EXPECT_TRUE(result);
}

// =============================================================================
// ADDITIONAL: Retreat with selective joint homing
// =============================================================================

TEST_F(TrajectoryExecutorTest, RetreatSkipsJ3WhenDisabled) {
    auto te = makeExecutor();
    auto params = makeDefaultRetreatParams();
    params.home_j3 = false;
    params.j5_home = 0.11;
    params.j3_home = 0.22;
    params.j4_home = 0.07;

    bool result = te->executeRetreat(params);
    EXPECT_TRUE(result);
    EXPECT_TRUE(approximatelyEqual(
        jm5_->current_position_.load(std::memory_order_relaxed), params.j5_home));
    EXPECT_TRUE(approximatelyEqual(
        jm4_->current_position_.load(std::memory_order_relaxed), params.j4_home));
    EXPECT_TRUE(approximatelyEqual(
        jm3_->current_position_.load(std::memory_order_relaxed), 0.0))
        << "J3 should not be commanded when home_j3=false";
}

// =============================================================================
// REGRESSION: Approach/retreat succeed when node is on a background executor
//
// This test reproduces the exact production crash from 2026-03-18 field trial:
// the yanthra_move node was added to a background SingleThreadedExecutor,
// and the old spinOnce() method called rclcpp::spin_some(node_) which tried
// to add the node to a second temporary executor, throwing:
//   "Node '/yanthra_move' has already been added to an executor."
//
// With the fix (spinOnce removed), approach/retreat must succeed even when the
// node is registered with a background executor — exactly as in production.
// =============================================================================

TEST_F(TrajectoryExecutorTest, ApproachSucceedsWithBackgroundExecutor) {
    // Simulate production: add the test node to a background executor
    auto bg_executor = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    bg_executor->add_node(node_);

    std::atomic<bool> bg_running{true};
    std::thread bg_thread([&bg_executor, &bg_running]() {
        while (bg_running.load()) {
            bg_executor->spin_some(std::chrono::milliseconds(10));
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    });

    // Execute approach — this is where the old code crashed
    auto te = makeExecutor();
    auto traj = makeSimpleTrajectory();
    auto params = makeDefaultApproachParams();

    bool result = te->executeApproach(traj, params);
    EXPECT_TRUE(result) << "executeApproach must not crash when node is on background executor";

    // Also test retreat in the same scenario
    auto retreat_params = makeDefaultRetreatParams();
    bool retreat_ok = te->executeRetreat(retreat_params);
    EXPECT_TRUE(retreat_ok) << "executeRetreat must not crash when node is on background executor";

    // Cleanup: stop background executor and remove node
    bg_running.store(false);
    bg_thread.join();
    bg_executor->remove_node(node_);
}

// =============================================================================
// main — initialize / shutdown rclcpp around the test run
// =============================================================================

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int ret = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return ret;
}
