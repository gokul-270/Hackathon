#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include "motor_control_msgs/action/joint_position_command.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"
#include <memory>
#include <type_traits>
#include <vector>

namespace motor_control_ros2
{

using JointPosCmd = motor_control_msgs::action::JointPositionCommand;
using JointHoming = motor_control_msgs::action::JointHoming;

// ---------------------------------------------------------------------------
// Fixture: creates an rclcpp node for tests that need one
// ---------------------------------------------------------------------------
class ActionServerTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        node_ = std::make_shared<rclcpp::Node>("test_action_servers");
    }

    void TearDown() override
    {
        node_.reset();
    }

    std::shared_ptr<rclcpp::Node> node_;
};

// ===========================================================================
// JointPositionCommand — Message structure tests
// ===========================================================================

TEST_F(ActionServerTest, JointPosCmdGoalConstruction)
{
    JointPosCmd::Goal goal;
    goal.joint_id = 3;
    goal.target_position = 1.57;
    goal.max_velocity = 2.0;

    EXPECT_EQ(goal.joint_id, 3);
    EXPECT_DOUBLE_EQ(goal.target_position, 1.57);
    EXPECT_DOUBLE_EQ(goal.max_velocity, 2.0);
}

TEST_F(ActionServerTest, JointPosCmdGoalDefaults)
{
    JointPosCmd::Goal goal;

    EXPECT_EQ(goal.joint_id, 0);
    EXPECT_DOUBLE_EQ(goal.target_position, 0.0);
    EXPECT_DOUBLE_EQ(goal.max_velocity, 0.0);
}

TEST_F(ActionServerTest, JointPosCmdResultConstruction)
{
    JointPosCmd::Result result;
    result.success = true;
    result.reason = "REACHED";
    result.actual_position = 1.565;

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.reason, "REACHED");
    EXPECT_DOUBLE_EQ(result.actual_position, 1.565);
}

TEST_F(ActionServerTest, JointPosCmdFeedbackConstruction)
{
    JointPosCmd::Feedback feedback;
    feedback.current_position = 0.78;
    feedback.error_from_target = 0.79;
    feedback.elapsed_seconds = 0.5;

    EXPECT_DOUBLE_EQ(feedback.current_position, 0.78);
    EXPECT_DOUBLE_EQ(feedback.error_from_target, 0.79);
    EXPECT_DOUBLE_EQ(feedback.elapsed_seconds, 0.5);
}

// ===========================================================================
// JointHoming — Message structure tests
// ===========================================================================

TEST_F(ActionServerTest, JointHomingGoalConstruction)
{
    JointHoming::Goal goal;
    goal.joint_ids = {2, 3, 4, 5};

    ASSERT_EQ(goal.joint_ids.size(), 4u);
    EXPECT_EQ(goal.joint_ids[0], 2);
    EXPECT_EQ(goal.joint_ids[1], 3);
    EXPECT_EQ(goal.joint_ids[2], 4);
    EXPECT_EQ(goal.joint_ids[3], 5);
}

TEST_F(ActionServerTest, JointHomingGoalEmptyMeansAll)
{
    JointHoming::Goal goal;

    // Empty joint_ids vector means "home all joints" per the action definition
    EXPECT_TRUE(goal.joint_ids.empty());
}

TEST_F(ActionServerTest, JointHomingResultConstruction)
{
    JointHoming::Result result;
    result.success = true;
    result.reason = "All joints homed";
    result.final_positions = {0.0, 0.01, -0.005, 0.002};

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.reason, "All joints homed");
    ASSERT_EQ(result.final_positions.size(), 4u);
    EXPECT_DOUBLE_EQ(result.final_positions[0], 0.0);
    EXPECT_DOUBLE_EQ(result.final_positions[2], -0.005);
}

TEST_F(ActionServerTest, JointHomingFeedbackConstruction)
{
    JointHoming::Feedback feedback;
    feedback.current_joint_id = 3;
    feedback.progress_percent = 50.0f;
    feedback.status_message = "Homing joint3: moving to zero";

    EXPECT_EQ(feedback.current_joint_id, 3);
    EXPECT_FLOAT_EQ(feedback.progress_percent, 50.0f);
    EXPECT_EQ(feedback.status_message, "Homing joint3: moving to zero");
}

// ===========================================================================
// Action type trait tests — verify sub-type relationships
// ===========================================================================

TEST(ActionTypeTraits, JointPosCmdHasCorrectSubTypes)
{
    // Verify the action type exposes Goal, Result, Feedback as nested types
    bool goal_ok = std::is_class<JointPosCmd::Goal>::value;
    bool result_ok = std::is_class<JointPosCmd::Result>::value;
    bool feedback_ok = std::is_class<JointPosCmd::Feedback>::value;

    EXPECT_TRUE(goal_ok);
    EXPECT_TRUE(result_ok);
    EXPECT_TRUE(feedback_ok);

    // GoalRequestService and GoalResultService are generated for every action
    bool send_goal_ok =
        std::is_class<JointPosCmd::Impl::SendGoalService>::value;
    bool get_result_ok =
        std::is_class<JointPosCmd::Impl::GetResultService>::value;

    EXPECT_TRUE(send_goal_ok);
    EXPECT_TRUE(get_result_ok);
}

TEST(ActionTypeTraits, JointHomingHasCorrectSubTypes)
{
    bool goal_ok = std::is_class<JointHoming::Goal>::value;
    bool result_ok = std::is_class<JointHoming::Result>::value;
    bool feedback_ok = std::is_class<JointHoming::Feedback>::value;

    EXPECT_TRUE(goal_ok);
    EXPECT_TRUE(result_ok);
    EXPECT_TRUE(feedback_ok);

    bool send_goal_ok =
        std::is_class<JointHoming::Impl::SendGoalService>::value;
    bool get_result_ok =
        std::is_class<JointHoming::Impl::GetResultService>::value;

    EXPECT_TRUE(send_goal_ok);
    EXPECT_TRUE(get_result_ok);
}

// ===========================================================================
// Action client creation tests
// ===========================================================================

TEST_F(ActionServerTest, CreateJointPosCmdClient)
{
    auto client = rclcpp_action::create_client<JointPosCmd>(
        node_, "/joint_position_command");

    ASSERT_NE(client, nullptr);
    // Server is not running so it should not be available
    EXPECT_FALSE(client->wait_for_action_server(std::chrono::milliseconds(100)));
}

TEST_F(ActionServerTest, CreateJointHomingClient)
{
    auto client = rclcpp_action::create_client<JointHoming>(
        node_, "/joint_homing");

    ASSERT_NE(client, nullptr);
    EXPECT_FALSE(client->wait_for_action_server(std::chrono::milliseconds(100)));
}

// ===========================================================================
// Goal builder / SendGoal options tests
// ===========================================================================

TEST_F(ActionServerTest, JointPosCmdSendGoalOptions)
{
    using GoalHandle = rclcpp_action::ClientGoalHandle<JointPosCmd>;

    // Verify SendGoalOptions can be constructed and callbacks assigned
    rclcpp_action::Client<JointPosCmd>::SendGoalOptions opts;

    bool goal_cb_invoked = false;
    bool feedback_cb_invoked = false;
    bool result_cb_invoked = false;

    opts.goal_response_callback =
        [&goal_cb_invoked](const GoalHandle::SharedPtr &) {
            goal_cb_invoked = true;
        };

    opts.feedback_callback =
        [&feedback_cb_invoked](
            GoalHandle::SharedPtr,
            const std::shared_ptr<const JointPosCmd::Feedback>) {
            feedback_cb_invoked = true;
        };

    opts.result_callback =
        [&result_cb_invoked](const GoalHandle::WrappedResult &) {
            result_cb_invoked = true;
        };

    // Callbacks are assigned (non-null) — we cannot invoke them without a
    // real server, but their assignability is the contract we verify here.
    EXPECT_TRUE(opts.goal_response_callback != nullptr);
    EXPECT_TRUE(opts.feedback_callback != nullptr);
    EXPECT_TRUE(opts.result_callback != nullptr);
}

TEST_F(ActionServerTest, JointHomingSendGoalOptions)
{
    using GoalHandle = rclcpp_action::ClientGoalHandle<JointHoming>;

    rclcpp_action::Client<JointHoming>::SendGoalOptions opts;

    opts.goal_response_callback =
        [](const GoalHandle::SharedPtr &) {};

    opts.feedback_callback =
        [](GoalHandle::SharedPtr,
           const std::shared_ptr<const JointHoming::Feedback>) {};

    opts.result_callback =
        [](const GoalHandle::WrappedResult &) {};

    EXPECT_TRUE(opts.goal_response_callback != nullptr);
    EXPECT_TRUE(opts.feedback_callback != nullptr);
    EXPECT_TRUE(opts.result_callback != nullptr);
}

// ===========================================================================
// Result failure-mode construction tests
// ===========================================================================

TEST_F(ActionServerTest, JointPosCmdResultFailureModes)
{
    // Verify the result message can represent each failure mode documented
    // in the action definition: REACHED, TIMEOUT, CANCELLED, ERROR
    const std::vector<std::string> expected_reasons = {
        "REACHED", "TIMEOUT", "CANCELLED", "ERROR"};

    for (const auto & reason : expected_reasons) {
        JointPosCmd::Result result;
        result.success = (reason == "REACHED");
        result.reason = reason;
        result.actual_position = (reason == "REACHED") ? 1.57 : 0.0;

        EXPECT_EQ(result.reason, reason) << "Failed for reason: " << reason;
        if (reason == "REACHED") {
            EXPECT_TRUE(result.success);
        } else {
            EXPECT_FALSE(result.success);
        }
    }
}

}  // namespace motor_control_ros2

int main(int argc, char ** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    rclcpp::init(argc, argv);
    int result = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return result;
}
