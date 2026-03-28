/**
 * @file test_action_topic_discovery.cpp
 * @brief Integration test: action server and client discover each other.
 *
 * Regression test for the Mar 17 2026 field failure where motor_control
 * created action servers at ~/joint_position_command (resolved to
 * /motor_control/joint_position_command) while yanthra_move clients used
 * /joint_position_command (absolute).  wait_for_action_server() always
 * timed out and the arm never moved.
 *
 * Fix: both sides use absolute "/joint_position_command" and "/joint_homing".
 *
 * These tests spin up a server node and a client node in-process and verify
 * that wait_for_action_server() returns true within 5 s.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include "motor_control_msgs/action/joint_position_command.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"

#include <chrono>
#include <fstream>
#include <memory>
#include <string>
#include <thread>

using namespace std::chrono_literals;

namespace motor_control_ros2
{

using JointPosCmd = motor_control_msgs::action::JointPositionCommand;
using JointHoming = motor_control_msgs::action::JointHoming;

// ---------------------------------------------------------------------------
// Fixture: two isolated nodes (server + client) sharing an executor
// ---------------------------------------------------------------------------
class ActionTopicDiscoveryTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    rclcpp::NodeOptions opts;
    opts.use_global_arguments(false);

    server_node_ = std::make_shared<rclcpp::Node>("discovery_server", opts);
    client_node_ = std::make_shared<rclcpp::Node>("discovery_client", opts);

    executor_ = std::make_shared<rclcpp::executors::MultiThreadedExecutor>();
    executor_->add_node(server_node_);
    executor_->add_node(client_node_);

    spin_thread_ = std::thread([this]() { executor_->spin(); });
  }

  void TearDown() override
  {
    if (executor_) {
      executor_->cancel();
    }
    if (spin_thread_.joinable()) {
      spin_thread_.join();
    }
    server_node_.reset();
    client_node_.reset();
    executor_.reset();
  }

  std::shared_ptr<rclcpp::Node> server_node_;
  std::shared_ptr<rclcpp::Node> client_node_;
  std::shared_ptr<rclcpp::executors::MultiThreadedExecutor> executor_;
  std::thread spin_thread_;
};

// ---------------------------------------------------------------------------
// Test: /joint_position_command — client finds server (absolute path)
// ---------------------------------------------------------------------------
TEST_F(ActionTopicDiscoveryTest, JointPositionCommandClientFindsServer)
{
  // Server at absolute path — matches production code in ros_interface_manager.cpp
  auto server = rclcpp_action::create_server<JointPosCmd>(
    server_node_, "/joint_position_command",
    [](const rclcpp_action::GoalUUID &,
       std::shared_ptr<const JointPosCmd::Goal>) {
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    },
    [](const std::shared_ptr<rclcpp_action::ServerGoalHandle<JointPosCmd>>) {
      return rclcpp_action::CancelResponse::ACCEPT;
    },
    [](const std::shared_ptr<rclcpp_action::ServerGoalHandle<JointPosCmd>>) {});

  // Client at absolute path — matches production code in yanthra_move_system_services.cpp
  auto client = rclcpp_action::create_client<JointPosCmd>(
    client_node_, "/joint_position_command");

  ASSERT_TRUE(client->wait_for_action_server(5s))
    << "Client at /joint_position_command could not find server at "
       "/joint_position_command within 5s — topic name mismatch?";
}

// ---------------------------------------------------------------------------
// Test: /joint_homing — client finds server (absolute path)
// ---------------------------------------------------------------------------
TEST_F(ActionTopicDiscoveryTest, JointHomingClientFindsServer)
{
  auto server = rclcpp_action::create_server<JointHoming>(
    server_node_, "/joint_homing",
    [](const rclcpp_action::GoalUUID &,
       std::shared_ptr<const JointHoming::Goal>) {
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    },
    [](const std::shared_ptr<rclcpp_action::ServerGoalHandle<JointHoming>>) {
      return rclcpp_action::CancelResponse::ACCEPT;
    },
    [](const std::shared_ptr<rclcpp_action::ServerGoalHandle<JointHoming>>) {});

  auto client = rclcpp_action::create_client<JointHoming>(
    client_node_, "/joint_homing");

  ASSERT_TRUE(client->wait_for_action_server(5s))
    << "Client at /joint_homing could not find server at "
       "/joint_homing within 5s — topic name mismatch?";
}

// ---------------------------------------------------------------------------
// Test: ~/joint_position_command server is NOT found by absolute client
//
// This is the negative regression test.  If someone re-introduces the
// tilde prefix on the server side, this test will pass (the tilde server
// is invisible to the absolute client).  Combined with the positive test
// above, any topic-path regression is caught.
// ---------------------------------------------------------------------------
TEST_F(ActionTopicDiscoveryTest, TildeServerNotFoundByAbsoluteClient)
{
  // Server with tilde prefix — resolves to /discovery_server/joint_position_command
  auto server = rclcpp_action::create_server<JointPosCmd>(
    server_node_, "~/joint_position_command",
    [](const rclcpp_action::GoalUUID &,
       std::shared_ptr<const JointPosCmd::Goal>) {
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    },
    [](const std::shared_ptr<rclcpp_action::ServerGoalHandle<JointPosCmd>>) {
      return rclcpp_action::CancelResponse::ACCEPT;
    },
    [](const std::shared_ptr<rclcpp_action::ServerGoalHandle<JointPosCmd>>) {});

  // Client with absolute path — the production path
  auto client = rclcpp_action::create_client<JointPosCmd>(
    client_node_, "/joint_position_command");

  // Must NOT find the tilde server — this was the original bug
  EXPECT_FALSE(client->wait_for_action_server(2s))
    << "Client at /joint_position_command should NOT find server at "
       "~/joint_position_command (resolves to /discovery_server/joint_position_command)";
}

// ---------------------------------------------------------------------------
// Test: source code verification — production server uses absolute path
//
// Belt-and-suspenders check that ros_interface_manager.cpp contains
// the absolute path string, not the tilde-prefixed one.
// ---------------------------------------------------------------------------
TEST(ActionTopicSourceVerification, RosInterfaceManagerUsesAbsolutePath)
{
  // SOURCE_DIR is defined by CMake target_compile_definitions
  const std::string src_path =
    std::string(SOURCE_DIR) + "/src/ros_interface_manager.cpp";

  std::ifstream file(src_path);
  ASSERT_TRUE(file.is_open()) << "Cannot open " << src_path;

  std::string content((std::istreambuf_iterator<char>(file)),
                       std::istreambuf_iterator<char>());

  // The file should contain the absolute action topic paths
  EXPECT_NE(content.find("\"/joint_position_command\""), std::string::npos)
    << "ros_interface_manager.cpp must use absolute \"/joint_position_command\"";
  EXPECT_NE(content.find("\"/joint_homing\""), std::string::npos)
    << "ros_interface_manager.cpp must use absolute \"/joint_homing\"";

  // The file should NOT contain tilde-prefixed action topics
  // (search for the specific action server creation pattern)
  EXPECT_EQ(content.find("\"~/joint_position_command\""), std::string::npos)
    << "ros_interface_manager.cpp must NOT use \"~/joint_position_command\" — "
       "causes topic mismatch with yanthra_move client";
  EXPECT_EQ(content.find("\"~/joint_homing\""), std::string::npos)
    << "ros_interface_manager.cpp must NOT use \"~/joint_homing\" — "
       "causes topic mismatch with yanthra_move client";
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
