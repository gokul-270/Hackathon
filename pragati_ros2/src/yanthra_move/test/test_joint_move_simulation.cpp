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
 * @file test_joint_move_simulation.cpp
 * @brief Unit tests for joint_move simulation path
 * @details Verifies that move_joint() returns SUCCESS immediately in
 *          simulation mode, stores the target position, and works
 *          for both WAIT and NO_WAIT modes.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float64.hpp>
#include "yanthra_move/joint_move.h"

// Provide the simulation_mode symbol that joint_move.cpp references via
// `extern std::atomic<bool> yanthra_move::simulation_mode`.
// In production this lives in yanthra_move_system_core.cpp; in tests we
// define it here so the test binary links without pulling in the full system.
namespace yanthra_move {
std::atomic<bool> simulation_mode{false};
}  // namespace yanthra_move

// ---------------------------------------------------------------------------
// Test fixture
// ---------------------------------------------------------------------------
class JointMoveSimulationTest : public ::testing::Test
{
protected:
    static rclcpp::Node::SharedPtr node_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j2_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j3_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j4_pub_;
    static rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr j5_pub_;

    static void SetUpTestSuite()
    {
        // Create a shared test node
        node_ = rclcpp::Node::make_shared("test_joint_move_simulation");

        // Declare parameters ONCE — the joint_move constructor reads these
        if (!node_->has_parameter("position_wait_mode")) {
            node_->declare_parameter("position_wait_mode", "blind_sleep");
        }
        if (!node_->has_parameter("feedback_timeout")) {
            node_->declare_parameter("feedback_timeout", 5.0);
        }

        // Create publishers on the same topics the production code expects
        j2_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint2_position_controller/command", 10);
        j3_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint3_position_controller/command", 10);
        j4_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint4_position_controller/command", 10);
        j5_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
            "joint5_position_controller/command", 10);

        // Wire up the static publishers inside joint_move
        joint_move::set_joint_publishers(j2_pub_, j3_pub_, j4_pub_, j5_pub_);

        // Enable simulation mode for every test in this suite
        yanthra_move::simulation_mode.store(true);
    }

    static void TearDownTestSuite()
    {
        yanthra_move::simulation_mode.store(false);
        // Reset the test-owned publisher copies BEFORE cleaning up
        // joint_move statics, so ref-counts drop cleanly.
        j2_pub_.reset();
        j3_pub_.reset();
        j4_pub_.reset();
        j5_pub_.reset();
        joint_move::cleanup_static_resources();
        node_.reset();
    }
};

// Static member definitions
rclcpp::Node::SharedPtr                                JointMoveSimulationTest::node_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   JointMoveSimulationTest::j2_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   JointMoveSimulationTest::j3_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   JointMoveSimulationTest::j4_pub_;
rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr   JointMoveSimulationTest::j5_pub_;

// ---------------------------------------------------------------------------
// Task 5.1 — Simulation shortcut returns SUCCESS immediately
// ---------------------------------------------------------------------------
TEST_F(JointMoveSimulationTest, MoveJointReturnsSuccessInSimulation)
{
    joint_move jm(node_, "joint3");
    MoveResult result = jm.move_joint(1.0, WAIT);
    EXPECT_EQ(result, MoveResult::SUCCESS);
}

// ---------------------------------------------------------------------------
// Task 5.2 — current_position_ stores the target after simulated move
// ---------------------------------------------------------------------------
TEST_F(JointMoveSimulationTest, CurrentPositionMatchesTargetAfterSimulatedMove)
{
    joint_move jm(node_, "joint3");

    const double target = 0.42;
    MoveResult result = jm.move_joint(target, WAIT);

    ASSERT_EQ(result, MoveResult::SUCCESS);
    EXPECT_DOUBLE_EQ(jm.current_position_.load(), target);
}

// ---------------------------------------------------------------------------
// Task 5.3 — Both WAIT and NO_WAIT return SUCCESS in simulation
// ---------------------------------------------------------------------------
TEST_F(JointMoveSimulationTest, WaitModeReturnsSuccessInSimulation)
{
    joint_move jm(node_, "joint4");
    MoveResult result = jm.move_joint(0.75, WAIT);
    EXPECT_EQ(result, MoveResult::SUCCESS);
}

TEST_F(JointMoveSimulationTest, NoWaitModeReturnsSuccessInSimulation)
{
    joint_move jm(node_, "joint4");
    MoveResult result = jm.move_joint(0.75, NO_WAIT);
    EXPECT_EQ(result, MoveResult::SUCCESS);
}

// ---------------------------------------------------------------------------
// Additional coverage: all supported joints route correctly in simulation
// ---------------------------------------------------------------------------
TEST_F(JointMoveSimulationTest, AllJointsReturnSuccessInSimulation)
{
    for (const auto& name : {"joint2", "joint3", "joint4", "joint5"}) {
        joint_move jm(node_, name);
        MoveResult result = jm.move_joint(0.5, WAIT);
        EXPECT_EQ(result, MoveResult::SUCCESS)
            << "Failed for " << name;
    }
}

// ---------------------------------------------------------------------------
// Edge: position stores correctly per-joint (each instance is independent)
// ---------------------------------------------------------------------------
TEST_F(JointMoveSimulationTest, PositionStoreIsPerInstance)
{
    joint_move jm3(node_, "joint3");
    joint_move jm5(node_, "joint5");

    const double target3 = 1.23;
    const double target5 = -0.77;

    ASSERT_EQ(jm3.move_joint(target3, WAIT), MoveResult::SUCCESS);
    ASSERT_EQ(jm5.move_joint(target5, WAIT), MoveResult::SUCCESS);

    EXPECT_DOUBLE_EQ(jm3.current_position_.load(), target3);
    EXPECT_DOUBLE_EQ(jm5.current_position_.load(), target5);
}

// ---------------------------------------------------------------------------
// Edge: error_code blocks move even in simulation mode
// ---------------------------------------------------------------------------
TEST_F(JointMoveSimulationTest, ErrorCodeBlocksMoveInSimulation)
{
    joint_move jm(node_, "joint3");
    jm.error_code = OVER_HEAT;

    MoveResult result = jm.move_joint(1.0, WAIT);
    EXPECT_EQ(result, MoveResult::ERROR);
}

// ---------------------------------------------------------------------------
// Edge: unknown joint name returns ERROR (no matching publisher)
// ---------------------------------------------------------------------------
TEST_F(JointMoveSimulationTest, UnknownJointReturnsError)
{
    joint_move jm(node_, "joint99");
    MoveResult result = jm.move_joint(1.0, WAIT);
    EXPECT_EQ(result, MoveResult::ERROR);
}

// ---------------------------------------------------------------------------
// main — initialize / shutdown rclcpp around the test run
// ---------------------------------------------------------------------------
int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int ret = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return ret;
}
