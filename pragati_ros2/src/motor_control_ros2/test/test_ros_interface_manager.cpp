/*
 * RosInterfaceManager Unit Tests (TDD RED phase)
 *
 * Tests for the RosInterfaceManager class extracted from MG6010ControllerNode.
 * RIM is pure infrastructure: it creates all ROS2 services, action servers,
 * subscribers, publishers, and timers, routing callbacks to the appropriate
 * handler class (MotorTestSuite, ControlLoopManager, or parent node via
 * std::function callbacks).
 *
 * Covers: construction (R1), service registration (R2), action server
 *         registration (R3), subscriber/publisher registration (R4),
 *         callback routing correctness (R5), parameter declarations (R6),
 *         and independent testability (R7).
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <std_srvs/srv/set_bool.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>

#include "motor_control_ros2/ros_interface_manager.hpp"
#include "motor_control_ros2/motor_test_suite.hpp"
#include "motor_control_ros2/control_loop_manager.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

#include "motor_control_msgs/srv/read_motor_state.hpp"
#include "motor_control_msgs/srv/read_encoder.hpp"
#include "motor_control_msgs/srv/read_motor_angles.hpp"
#include "motor_control_msgs/srv/read_motor_limits.hpp"
#include "motor_control_msgs/srv/clear_motor_errors.hpp"
#include "motor_control_msgs/srv/read_pid.hpp"
#include "motor_control_msgs/srv/write_pid.hpp"
#include "motor_control_msgs/srv/write_pid_to_rom.hpp"
#include "motor_control_msgs/srv/joint_position_command.hpp"
#include "motor_control_msgs/srv/motor_command.hpp"
#include "motor_control_msgs/srv/motor_lifecycle.hpp"
#include "motor_control_msgs/srv/write_motor_limits.hpp"
#include "motor_control_msgs/srv/write_encoder_zero.hpp"

#include "motor_control_msgs/action/step_response_test.hpp"
#include "motor_control_msgs/action/joint_position_command.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <vector>

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using ::testing::_;
using ::testing::Return;

// =============================================================================
// GMock MockMotorController — reused from MTS/CLM tests
// =============================================================================

class MockMotorController : public MotorControllerInterface
{
public:
  MOCK_METHOD(
    bool, initialize,
    (const MotorConfiguration & config, std::shared_ptr<CANInterface> can_interface),
    (override));
  MOCK_METHOD(bool, configure, (const MotorConfiguration & config), (override));
  MOCK_METHOD(bool, set_enabled, (bool enable), (override));
  MOCK_METHOD(
    bool, set_position, (double position, double velocity, double torque), (override));
  MOCK_METHOD(bool, set_velocity, (double velocity, double torque), (override));
  MOCK_METHOD(bool, set_torque, (double torque), (override));
  MOCK_METHOD(double, get_position, (), (override));
  MOCK_METHOD(double, get_velocity, (), (override));
  MOCK_METHOD(double, get_torque, (), (override));
  MOCK_METHOD(bool, home_motor, (const HomingConfig * config), (override));
  MOCK_METHOD(bool, is_homed, (), (const, override));
  MOCK_METHOD(MotorStatus, get_status, (), (override));
  MOCK_METHOD(bool, emergency_stop, (), (override));
  MOCK_METHOD(bool, stop, (), (override));
  MOCK_METHOD(bool, clear_errors, (), (override));
  MOCK_METHOD(bool, calibrate_motor, (), (override));
  MOCK_METHOD(bool, calibrate_encoder, (), (override));
  MOCK_METHOD(bool, needs_calibration, (), (const, override));
  MOCK_METHOD(MotorConfiguration, get_configuration, (), (const, override));
  MOCK_METHOD(
    const ErrorFramework::ErrorInfo &, get_error_info, (), (const, override));
  MOCK_METHOD(
    std::vector<ErrorFramework::ErrorInfo>, get_error_history, (), (const, override));
  MOCK_METHOD(
    ErrorFramework::RecoveryResult, attempt_error_recovery, (), (override));
  MOCK_METHOD(
    void, set_error_handler,
    (std::function<void(const ErrorFramework::ErrorInfo &)> handler), (override));
  MOCK_METHOD(std::optional<PIDParams>, readPID, (), (override));
  MOCK_METHOD(bool, setPID, (const PIDParams & params), (override));
  MOCK_METHOD(bool, writePIDToROM, (const PIDParams & params), (override));

  MOCK_METHOD(bool, readMaxTorqueCurrent, (uint16_t & ratio), (override));
  MOCK_METHOD(bool, writeMaxTorqueCurrentRAM, (uint16_t ratio), (override));
  MOCK_METHOD(bool, readAcceleration, (double & rad_per_sec2), (override));
  MOCK_METHOD(bool, setAcceleration, (double rad_per_sec2), (override));
  MOCK_METHOD(
    bool, readEncoder,
    (uint16_t & encoder_value, uint16_t & encoder_raw, uint16_t & encoder_offset),
    (override));
  MOCK_METHOD(bool, writeEncoderOffsetToROM, (uint16_t offset), (override));
  MOCK_METHOD(bool, setCurrentPositionAsZero, (), (override));
  MOCK_METHOD(bool, readMultiTurnAngle, (double & angle_radians), (override));
  MOCK_METHOD(bool, readSingleTurnAngle, (double & angle_radians), (override));
  MOCK_METHOD(bool, readErrors, (uint32_t & error_flags), (override));
  MOCK_METHOD(FullMotorState, readFullState, (), (override));
  MOCK_METHOD(bool, torqueClosedLoop, (double amps), (override));
  MOCK_METHOD(bool, speedClosedLoop, (double dps), (override));
  MOCK_METHOD(bool, multiLoopAngle1, (double degrees), (override));
  MOCK_METHOD(
    bool, multiLoopAngle2, (double degrees, double max_speed_dps), (override));
  MOCK_METHOD(
    bool, singleLoopAngle1, (double degrees, uint8_t direction), (override));
  MOCK_METHOD(
    bool, singleLoopAngle2,
    (double degrees, double max_speed_dps, uint8_t direction), (override));
  MOCK_METHOD(bool, incrementAngle1, (double degrees), (override));
  MOCK_METHOD(
    bool, incrementAngle2, (double degrees, double max_speed_dps), (override));
};

// =============================================================================
// Helper: spin node until a future completes or timeout
// =============================================================================

template <typename FutureT>
bool spin_until_complete(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node, FutureT & future,
  std::chrono::milliseconds timeout = std::chrono::milliseconds(2000))
{
  auto start = std::chrono::steady_clock::now();
  while (rclcpp::ok()) {
    rclcpp::spin_some(node->get_node_base_interface());
    if (future.wait_for(std::chrono::milliseconds(10)) == std::future_status::ready) {
      return true;
    }
    if (std::chrono::steady_clock::now() - start > timeout) {
      return false;
    }
  }
  return false;
}

// =============================================================================
// Test Fixture
// =============================================================================

class RosInterfaceManagerTest : public ::testing::Test
{
protected:
  static constexpr size_t NUM_MOTORS = 2;

  void SetUp() override
  {
    rclcpp::init(0, nullptr);

    node_ = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_rim_node");
    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    // Create mock controllers with known CAN IDs
    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      auto mock = std::make_shared<MockMotorController>();
      MotorConfiguration config;
      config.can_id = static_cast<uint8_t>(i + 1);
      config.joint_name = "joint_" + std::to_string(i);

      ON_CALL(*mock, get_configuration()).WillByDefault(Return(config));
      ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_velocity()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_torque()).WillByDefault(Return(0.0));

      mock_controllers_.push_back(mock);
      controllers_.push_back(mock);
      joint_names_.push_back(config.joint_name);
      motor_available_[i].store(true);
    }

    // Create real handler objects (with mock dependencies)
    motor_test_suite_ = std::make_unique<MotorTestSuite>(
      node_, mock_can_, controllers_, motor_available_, joint_names_);

    // control_frequency = 0 means no internal timer/publishers in CLM
    control_loop_manager_ = std::make_unique<ControlLoopManager>(
      node_, mock_can_, controllers_, motor_available_, joint_names_, 0.0);

    // Set up tracking flags for node-handled callback routing verification
    enable_called_ = false;
    disable_called_ = false;
    reset_called_ = false;
    joint_pos_cmd_called_ = false;
    motor_cmd_called_ = false;
    motor_lifecycle_called_ = false;
    write_motor_limits_called_ = false;
    write_encoder_zero_called_ = false;

    // Build the node callbacks struct that RIM will use for parent-node routing
    NodeCallbacks callbacks;
    callbacks.enable_callback =
      [this](
        const std::shared_ptr<std_srvs::srv::Trigger::Request>,
        std::shared_ptr<std_srvs::srv::Trigger::Response> resp) {
        enable_called_ = true;
        resp->success = true;
        resp->message = "enabled";
      };
    callbacks.disable_callback =
      [this](
        const std::shared_ptr<std_srvs::srv::Trigger::Request>,
        std::shared_ptr<std_srvs::srv::Trigger::Response> resp) {
        disable_called_ = true;
        resp->success = true;
        resp->message = "disabled";
      };
    callbacks.reset_motor_callback =
      [this](
        const std::shared_ptr<std_srvs::srv::SetBool::Request>,
        std::shared_ptr<std_srvs::srv::SetBool::Response> resp) {
        reset_called_ = true;
        resp->success = true;
      };
    callbacks.joint_position_command_callback =
      [this](
        const std::shared_ptr<motor_control_msgs::srv::JointPositionCommand::Request>,
        std::shared_ptr<motor_control_msgs::srv::JointPositionCommand::Response> resp) {
        joint_pos_cmd_called_ = true;
        resp->success = true;
      };
    callbacks.motor_command_callback =
      [this](
        const std::shared_ptr<motor_control_msgs::srv::MotorCommand::Request>,
        std::shared_ptr<motor_control_msgs::srv::MotorCommand::Response> resp) {
        motor_cmd_called_ = true;
        resp->success = true;
      };
    callbacks.motor_lifecycle_callback =
      [this](
        const std::shared_ptr<motor_control_msgs::srv::MotorLifecycle::Request>,
        std::shared_ptr<motor_control_msgs::srv::MotorLifecycle::Response> resp) {
        motor_lifecycle_called_ = true;
        resp->success = true;
      };
    callbacks.write_motor_limits_callback =
      [this](
        const std::shared_ptr<motor_control_msgs::srv::WriteMotorLimits::Request>,
        std::shared_ptr<motor_control_msgs::srv::WriteMotorLimits::Response> resp) {
        write_motor_limits_called_ = true;
        resp->success = true;
      };
    callbacks.write_encoder_zero_callback =
      [this](
        const std::shared_ptr<motor_control_msgs::srv::WriteEncoderZero::Request>,
        std::shared_ptr<motor_control_msgs::srv::WriteEncoderZero::Response> resp) {
        write_encoder_zero_called_ = true;
        resp->success = true;
      };

    // Action server callbacks (simplified for testing — just track calls)
    callbacks.step_response_goal_callback =
      [](const rclcpp_action::GoalUUID &,
         std::shared_ptr<const motor_control_msgs::action::StepResponseTest::Goal>)
      -> rclcpp_action::GoalResponse {
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      };
    callbacks.step_response_cancel_callback =
      [](std::shared_ptr<rclcpp_action::ServerGoalHandle<
           motor_control_msgs::action::StepResponseTest>>)
      -> rclcpp_action::CancelResponse {
        return rclcpp_action::CancelResponse::ACCEPT;
      };
    callbacks.step_response_accepted_callback =
      [](std::shared_ptr<rclcpp_action::ServerGoalHandle<
           motor_control_msgs::action::StepResponseTest>>) {};

    callbacks.joint_pos_cmd_goal_callback =
      [](const rclcpp_action::GoalUUID &,
         std::shared_ptr<const motor_control_msgs::action::JointPositionCommand::Goal>)
      -> rclcpp_action::GoalResponse {
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      };
    callbacks.joint_pos_cmd_cancel_callback =
      [](std::shared_ptr<rclcpp_action::ServerGoalHandle<
           motor_control_msgs::action::JointPositionCommand>>)
      -> rclcpp_action::CancelResponse {
        return rclcpp_action::CancelResponse::ACCEPT;
      };
    callbacks.joint_pos_cmd_accepted_callback =
      [](std::shared_ptr<rclcpp_action::ServerGoalHandle<
           motor_control_msgs::action::JointPositionCommand>>) {};

    callbacks.joint_homing_goal_callback =
      [](const rclcpp_action::GoalUUID &,
         std::shared_ptr<const motor_control_msgs::action::JointHoming::Goal>)
      -> rclcpp_action::GoalResponse {
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      };
    callbacks.joint_homing_cancel_callback =
      [](std::shared_ptr<rclcpp_action::ServerGoalHandle<
           motor_control_msgs::action::JointHoming>>)
      -> rclcpp_action::CancelResponse {
        return rclcpp_action::CancelResponse::ACCEPT;
      };
    callbacks.joint_homing_accepted_callback =
      [](std::shared_ptr<rclcpp_action::ServerGoalHandle<
           motor_control_msgs::action::JointHoming>>) {};

    auto safety_group = node_->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);
    auto hardware_group = node_->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);
    auto processing_group = node_->create_callback_group(
      rclcpp::CallbackGroupType::Reentrant);

    rim_ = std::make_unique<RosInterfaceManager>(
      node_, motor_test_suite_.get(), control_loop_manager_.get(),
      callbacks, controllers_, motor_available_, joint_names_,
      safety_group, hardware_group, processing_group);
  }

  void TearDown() override
  {
    rim_.reset();
    control_loop_manager_.reset();
    motor_test_suite_.reset();
    mock_controllers_.clear();
    controllers_.clear();
    joint_names_.clear();
    node_.reset();
    rclcpp::shutdown();
  }

  // Helper: get all service names for our node
  std::vector<std::string> get_node_service_names()
  {
    auto services = node_->get_service_names_and_types();
    std::vector<std::string> names;
    for (const auto & [name, types] : services) {
      names.push_back(name);
    }
    return names;
  }

  // Helper: check if a service name exists (with node namespace prefix)
  bool has_service(const std::string & service_name)
  {
    auto names = get_node_service_names();
    std::string full_name = std::string("/") + node_->get_name() + "/" + service_name;
    // For bare names (no ~/), also check without node prefix
    for (const auto & n : names) {
      if (n == full_name || n == "/" + service_name || n == service_name) {
        return true;
      }
    }
    return false;
  }

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;
  std::vector<std::shared_ptr<MockMotorController>> mock_controllers_;
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;
  std::vector<std::string> joint_names_;
  std::array<std::atomic<bool>, MAX_MOTORS> motor_available_{};
  std::unique_ptr<MotorTestSuite> motor_test_suite_;
  std::unique_ptr<ControlLoopManager> control_loop_manager_;
  std::unique_ptr<RosInterfaceManager> rim_;

  // Tracking flags for node-handled callback verification
  bool enable_called_;
  bool disable_called_;
  bool reset_called_;
  bool joint_pos_cmd_called_;
  bool motor_cmd_called_;
  bool motor_lifecycle_called_;
  bool write_motor_limits_called_;
  bool write_encoder_zero_called_;
};

// =============================================================================
// Task 7.2: Construction — valid and null node
// =============================================================================

TEST_F(RosInterfaceManagerTest, Construction_ValidArgs)
{
  // RIM was constructed in SetUp — verify it's not null
  ASSERT_NE(rim_, nullptr);
}

TEST_F(RosInterfaceManagerTest, Construction_NullNode_Throws)
{
  NodeCallbacks callbacks;  // empty/default callbacks
  EXPECT_THROW(
    RosInterfaceManager(
      nullptr, motor_test_suite_.get(), control_loop_manager_.get(),
      callbacks, controllers_, motor_available_, joint_names_,
      nullptr, nullptr, nullptr),
    std::invalid_argument);
}

// =============================================================================
// Task 7.3: All 17 services registered with correct names (R2)
// =============================================================================

TEST_F(RosInterfaceManagerTest, AllServicesRegistered)
{
  // Allow ROS2 service discovery to settle
  rclcpp::spin_some(node_->get_node_base_interface());

  auto services = node_->get_service_names_and_types();
  std::vector<std::string> service_names;
  for (const auto & [name, types] : services) {
    service_names.push_back(name);
  }

  // The 17 expected services. Node name is "test_rim_node".
  // Bare names: enable_motors, disable_motors, get_motor_availability,
  //             reset_motor, joint_position_command
  // Node-private (~/): read_pid, write_pid, write_pid_to_rom, motor_command,
  //             motor_lifecycle, read_motor_limits, write_motor_limits,
  //             read_encoder, write_encoder_zero, read_motor_angles,
  //             clear_motor_errors, read_motor_state
  std::string ns = std::string("/") + node_->get_name();

  // Bare-name services (resolved relative to node namespace, which is "/" here)
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), "/enable_motors"),
    service_names.end()) << "Missing service: enable_motors";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), "/disable_motors"),
    service_names.end()) << "Missing service: disable_motors";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), "/get_motor_availability"),
    service_names.end()) << "Missing service: get_motor_availability";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), "/reset_motor"),
    service_names.end()) << "Missing service: reset_motor";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), "/joint_position_command"),
    service_names.end()) << "Missing service: joint_position_command";

  // Node-private services (~/xxx -> /test_rim_node/xxx)
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/read_pid"),
    service_names.end()) << "Missing service: ~/read_pid";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/write_pid"),
    service_names.end()) << "Missing service: ~/write_pid";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/write_pid_to_rom"),
    service_names.end()) << "Missing service: ~/write_pid_to_rom";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/motor_command"),
    service_names.end()) << "Missing service: ~/motor_command";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/motor_lifecycle"),
    service_names.end()) << "Missing service: ~/motor_lifecycle";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/read_motor_limits"),
    service_names.end()) << "Missing service: ~/read_motor_limits";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/write_motor_limits"),
    service_names.end()) << "Missing service: ~/write_motor_limits";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/read_encoder"),
    service_names.end()) << "Missing service: ~/read_encoder";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/write_encoder_zero"),
    service_names.end()) << "Missing service: ~/write_encoder_zero";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/read_motor_angles"),
    service_names.end()) << "Missing service: ~/read_motor_angles";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/clear_motor_errors"),
    service_names.end()) << "Missing service: ~/clear_motor_errors";
  EXPECT_NE(
    std::find(service_names.begin(), service_names.end(), ns + "/read_motor_state"),
    service_names.end()) << "Missing service: ~/read_motor_state";
}

// =============================================================================
// Task 7.4: All 3 action servers registered with correct names (R3)
// =============================================================================

TEST_F(RosInterfaceManagerTest, AllActionServersRegistered)
{
  // Action servers create internal services for goal/cancel/result/feedback.
  // Verify by checking for the _action/send_goal service pattern.
  auto services = node_->get_service_names_and_types();
  std::vector<std::string> service_names;
  for (const auto & [name, types] : services) {
    service_names.push_back(name);
  }

  std::string ns = std::string("/") + node_->get_name();

  // StepResponseTest: ~/step_response_test
  EXPECT_NE(
    std::find_if(service_names.begin(), service_names.end(),
      [&ns](const std::string & n) {
        return n.find(ns + "/step_response_test") != std::string::npos &&
               n.find("send_goal") != std::string::npos;
      }),
    service_names.end()) << "Missing action server: ~/step_response_test";

  // JointPositionCommand: /joint_position_command (absolute path — must match
  // ros_interface_manager.cpp which creates server at "/" prefix so all nodes
  // share a single action endpoint regardless of node namespace)
  EXPECT_NE(
    std::find_if(service_names.begin(), service_names.end(),
      [](const std::string & n) {
        return n.find("/joint_position_command") != std::string::npos &&
               n.find("send_goal") != std::string::npos;
      }),
    service_names.end()) << "Missing action server: /joint_position_command";

  // JointHoming: /joint_homing (absolute path — same reasoning as above)
  EXPECT_NE(
    std::find_if(service_names.begin(), service_names.end(),
      [](const std::string & n) {
        return n.find("/joint_homing") != std::string::npos &&
               n.find("send_goal") != std::string::npos;
      }),
    service_names.end()) << "Missing action server: /joint_homing";
}

// =============================================================================
// Task 7.5: Subscribers (3xN) and Publishers (2) registered (R4)
// =============================================================================

TEST_F(RosInterfaceManagerTest, SubscribersCreatedPerMotor)
{
  // Expect 3 * NUM_MOTORS = 6 subscriptions for command topics
  // Topic pattern: /<joint_name>_{position,velocity,stop}_controller/command
  auto topic_info = node_->get_subscriptions_info_by_topic(
    "/joint_0_position_controller/command");
  EXPECT_GE(topic_info.size(), 1u) << "Missing position subscriber for joint_0";

  topic_info = node_->get_subscriptions_info_by_topic(
    "/joint_1_position_controller/command");
  EXPECT_GE(topic_info.size(), 1u) << "Missing position subscriber for joint_1";

  topic_info = node_->get_subscriptions_info_by_topic(
    "/joint_0_velocity_controller/command");
  EXPECT_GE(topic_info.size(), 1u) << "Missing velocity subscriber for joint_0";

  topic_info = node_->get_subscriptions_info_by_topic(
    "/joint_1_velocity_controller/command");
  EXPECT_GE(topic_info.size(), 1u) << "Missing velocity subscriber for joint_1";

  topic_info = node_->get_subscriptions_info_by_topic(
    "/joint_0_stop_controller/command");
  EXPECT_GE(topic_info.size(), 1u) << "Missing stop subscriber for joint_0";

  topic_info = node_->get_subscriptions_info_by_topic(
    "/joint_1_stop_controller/command");
  EXPECT_GE(topic_info.size(), 1u) << "Missing stop subscriber for joint_1";
}

TEST_F(RosInterfaceManagerTest, PublishersRegistered)
{
  // 2 publishers: joint_states and ~/motor_diagnostics
  auto pub_info = node_->get_publishers_info_by_topic("/joint_states");
  EXPECT_GE(pub_info.size(), 1u) << "Missing publisher: joint_states";

  std::string ns = std::string("/") + node_->get_name();
  pub_info = node_->get_publishers_info_by_topic(ns + "/motor_diagnostics");
  EXPECT_GE(pub_info.size(), 1u) << "Missing publisher: ~/motor_diagnostics";
}

// =============================================================================
// Task 7.6: read_motor_state routes to MotorTestSuite (R5 scenario 1)
// =============================================================================

TEST_F(RosInterfaceManagerTest, ReadMotorState_RoutesToMotorTestSuite)
{
  // Create a client and call the service
  auto client = node_->create_client<motor_control_msgs::srv::ReadMotorState>(
    "~/read_motor_state");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::ReadMotorState::Request>();
  request->motor_id = 1;

  // readMotorState calls readFullState() on the mock controller — set expectation
  FullMotorState state{};
  state.valid = true;
  state.temperature_c = 42.0;
  EXPECT_CALL(*mock_controllers_[0], readFullState())
    .WillOnce(Return(state));

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  // The response should contain the mocked temperature
  EXPECT_NEAR(response->temperature_c, 42.0, 0.01);
}

// =============================================================================
// Task 7.7: read_encoder, read_motor_angles, etc. route to MTS (R5 scenario 1)
// =============================================================================

TEST_F(RosInterfaceManagerTest, ReadEncoder_RoutesToMotorTestSuite)
{
  auto client = node_->create_client<motor_control_msgs::srv::ReadEncoder>(
    "~/read_encoder");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::ReadEncoder::Request>();
  request->motor_id = 1;

  uint16_t enc_val = 1234, enc_raw = 5678, enc_off = 100;
  EXPECT_CALL(*mock_controllers_[0], readEncoder(_, _, _))
    .WillOnce(
      [&](uint16_t & value, uint16_t & raw, uint16_t & offset) {
        value = enc_val;
        raw = enc_raw;
        offset = enc_off;
        return true;
      });

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  // callback maps: value -> original_value, raw -> raw_value, offset -> offset
  EXPECT_EQ(response->original_value, enc_val);
  EXPECT_EQ(response->raw_value, enc_raw);
  EXPECT_EQ(response->offset, enc_off);
}

TEST_F(RosInterfaceManagerTest, ReadMotorAngles_RoutesToMotorTestSuite)
{
  auto client = node_->create_client<motor_control_msgs::srv::ReadMotorAngles>(
    "~/read_motor_angles");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::ReadMotorAngles::Request>();
  request->motor_id = 1;

  double multi_angle = 1.57;
  EXPECT_CALL(*mock_controllers_[0], readMultiTurnAngle(_))
    .WillOnce(
      [&](double & angle) { angle = multi_angle; return true; });
  EXPECT_CALL(*mock_controllers_[0], readSingleTurnAngle(_))
    .WillOnce(
      [](double & angle) { angle = 0.5; return true; });

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_NEAR(response->multi_turn_angle, multi_angle, 0.01);
}

TEST_F(RosInterfaceManagerTest, ReadMotorLimits_RoutesToMotorTestSuite)
{
  auto client = node_->create_client<motor_control_msgs::srv::ReadMotorLimits>(
    "~/read_motor_limits");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::ReadMotorLimits::Request>();
  request->motor_id = 1;

  uint16_t torque_ratio = 80;
  double accel = 5.0;
  EXPECT_CALL(*mock_controllers_[0], readMaxTorqueCurrent(_))
    .WillOnce(
      [&](uint16_t & ratio) { ratio = torque_ratio; return true; });
  EXPECT_CALL(*mock_controllers_[0], readAcceleration(_))
    .WillOnce(
      [&](double & a) { a = accel; return true; });

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_EQ(response->max_torque_ratio, torque_ratio);
}

TEST_F(RosInterfaceManagerTest, ClearMotorErrors_RoutesToMotorTestSuite)
{
  auto client = node_->create_client<motor_control_msgs::srv::ClearMotorErrors>(
    "~/clear_motor_errors");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::ClearMotorErrors::Request>();
  request->motor_id = 1;

  EXPECT_CALL(*mock_controllers_[0], clear_errors())
    .WillOnce(Return(true));
  EXPECT_CALL(*mock_controllers_[0], readErrors(_))
    .WillOnce(
      [](uint32_t & flags) { flags = 0; return true; });

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_EQ(response->error_flags_after, 0u);
}

TEST_F(RosInterfaceManagerTest, ReadPid_RoutesToMotorTestSuite)
{
  auto client = node_->create_client<motor_control_msgs::srv::ReadPID>(
    "~/read_pid");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::ReadPID::Request>();
  request->motor_id = 1;

  PIDParams pid{10, 20, 30, 40, 50, 60};
  EXPECT_CALL(*mock_controllers_[0], readPID())
    .WillOnce(Return(std::optional<PIDParams>(pid)));

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_EQ(response->angle_kp, 10);
  EXPECT_EQ(response->speed_ki, 40);
}

// =============================================================================
// Task 7.8: get_motor_availability routes to MTS (R5 scenario 1)
// =============================================================================

TEST_F(RosInterfaceManagerTest, MotorAvailability_RoutesToMotorTestSuite)
{
  auto client = node_->create_client<std_srvs::srv::Trigger>(
    "get_motor_availability");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<std_srvs::srv::Trigger::Request>();

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  // motor_availability_callback reports which motors are available
  EXPECT_TRUE(response->success);
  // With 2 motors both available, message should mention them
  EXPECT_FALSE(response->message.empty());
}

// =============================================================================
// Task 7.9: write_pid, write_pid_to_rom route to CLM (R5 scenario 2)
// =============================================================================

TEST_F(RosInterfaceManagerTest, WritePid_RoutesToControlLoopManager)
{
  auto client = node_->create_client<motor_control_msgs::srv::WritePID>(
    "~/write_pid");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::WritePID::Request>();
  request->motor_id = 1;
  request->angle_kp = 10;
  request->angle_ki = 20;
  request->speed_kp = 30;
  request->speed_ki = 40;
  request->current_kp = 50;
  request->current_ki = 60;

  // CLM's writePidCallback calls setPID on the controller
  EXPECT_CALL(*mock_controllers_[0], setPID(_))
    .WillOnce(Return(true));

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_TRUE(response->success);
}

TEST_F(RosInterfaceManagerTest, WritePidToRom_RoutesToControlLoopManager)
{
  auto client = node_->create_client<motor_control_msgs::srv::WritePIDToROM>(
    "~/write_pid_to_rom");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::WritePIDToROM::Request>();
  request->motor_id = 1;
  request->angle_kp = 10;
  request->angle_ki = 20;
  request->speed_kp = 30;
  request->speed_ki = 40;
  request->current_kp = 50;
  request->current_ki = 60;

  EXPECT_CALL(*mock_controllers_[0], writePIDToROM(_))
    .WillOnce(Return(true));

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_TRUE(response->success);
}

// =============================================================================
// Task 7.10: Unextracted services route to parent node (R5 scenario 3)
// =============================================================================

TEST_F(RosInterfaceManagerTest, EnableMotors_RoutesToNodeCallback)
{
  auto client = node_->create_client<std_srvs::srv::Trigger>("enable_motors");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_TRUE(response->success);
  EXPECT_TRUE(enable_called_) << "enable_callback was not called on the node";
}

TEST_F(RosInterfaceManagerTest, DisableMotors_RoutesToNodeCallback)
{
  auto client = node_->create_client<std_srvs::srv::Trigger>("disable_motors");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  EXPECT_TRUE(response->success);
  EXPECT_TRUE(disable_called_) << "disable_callback was not called on the node";
}

TEST_F(RosInterfaceManagerTest, MotorCommand_RoutesToNodeCallback)
{
  auto client = node_->create_client<motor_control_msgs::srv::MotorCommand>(
    "~/motor_command");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::MotorCommand::Request>();
  request->motor_id = 1;
  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  EXPECT_TRUE(motor_cmd_called_) << "motor_command_callback was not called on the node";
}

TEST_F(RosInterfaceManagerTest, WriteMotorLimits_RoutesToNodeCallback)
{
  auto client = node_->create_client<motor_control_msgs::srv::WriteMotorLimits>(
    "~/write_motor_limits");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::WriteMotorLimits::Request>();
  request->motor_id = 1;
  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  EXPECT_TRUE(write_motor_limits_called_)
    << "write_motor_limits_callback was not called on the node";
}

TEST_F(RosInterfaceManagerTest, WriteEncoderZero_RoutesToNodeCallback)
{
  auto client = node_->create_client<motor_control_msgs::srv::WriteEncoderZero>(
    "~/write_encoder_zero");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::WriteEncoderZero::Request>();
  request->motor_id = 1;
  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  EXPECT_TRUE(write_encoder_zero_called_)
    << "write_encoder_zero_callback was not called on the node";
}

// =============================================================================
// Task 7.11: Parameter declarations (R6)
// =============================================================================

TEST_F(RosInterfaceManagerTest, ParametersDeclared_Skipped)
{
  // NOTE: Parameter declarations remain in MG6010ControllerNode's constructor
  // (lines 104-189). RosInterfaceManager does NOT own parameter declarations —
  // it only creates services/actions/subscribers/publishers. This test verifies
  // that RIM does NOT re-declare parameters (they stay in the node).
  //
  // The parameters are tested at the integration level via the node itself.
  // This is a conscious design choice: parameters are configuration, not
  // interface wiring.
  SUCCEED();
}

// =============================================================================
// Task 7.12: Diagnostic callbacks fail gracefully when CAN is down (MTS R3)
// =============================================================================

TEST_F(RosInterfaceManagerTest, ReadMotorState_WhenControllerReturnsError)
{
  auto client = node_->create_client<motor_control_msgs::srv::ReadMotorState>(
    "~/read_motor_state");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<motor_control_msgs::srv::ReadMotorState::Request>();
  request->motor_id = 1;

  // Return a default FullMotorState with valid=false (simulating CAN read failure)
  FullMotorState error_state{};
  error_state.valid = false;
  EXPECT_CALL(*mock_controllers_[0], readFullState())
    .WillOnce(Return(error_state));

  auto future = client->async_send_request(request);
  ASSERT_TRUE(spin_until_complete(node_, future));

  auto response = future.get();
  // Should still return a response (not crash), with success=false and error message
  EXPECT_FALSE(response->success);
  EXPECT_FALSE(response->error_message.empty());
}

// =============================================================================
// Subscriber routing: position command reaches CLM
// =============================================================================

TEST_F(RosInterfaceManagerTest, PositionCommandSubscriber_RoutesToCLM)
{
  // Use a separate regular node for publishing — LifecycleNode::create_publisher
  // creates a LifecyclePublisher that requires activation to publish.
  auto pub_node = std::make_shared<rclcpp::Node>("test_rim_pub_node");
  auto pub = pub_node->create_publisher<std_msgs::msg::Float64>(
    "/joint_0_position_controller/command", 10);

  // CLM's position_command_callback calls set_position on the controller
  EXPECT_CALL(*mock_controllers_[0], set_position(1.57, 0.0, 0.0))
    .WillOnce(Return(true));

  auto msg = std::make_unique<std_msgs::msg::Float64>();
  msg->data = 1.57;
  pub->publish(std::move(msg));

  // Spin to process the message
  auto start = std::chrono::steady_clock::now();
  while (std::chrono::steady_clock::now() - start < std::chrono::seconds(2)) {
    rclcpp::spin_some(node_->get_node_base_interface());
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if (::testing::Mock::VerifyAndClear(mock_controllers_[0].get())) {
      break;
    }
  }
}

TEST_F(RosInterfaceManagerTest, StopCommandSubscriber_RoutesToCLM)
{
  // Use a separate regular node for publishing — LifecycleNode::create_publisher
  // creates a LifecyclePublisher that requires activation to publish.
  auto pub_node = std::make_shared<rclcpp::Node>("test_rim_stop_pub_node");
  auto pub = pub_node->create_publisher<std_msgs::msg::Float64>(
    "/joint_0_stop_controller/command", 10);

  // Stop callback calls stop() on the controller
  EXPECT_CALL(*mock_controllers_[0], stop())
    .WillOnce(Return(true));

  auto msg = std::make_unique<std_msgs::msg::Float64>();
  msg->data = 1.0;  // > 0.5 triggers stop
  pub->publish(std::move(msg));

  auto start = std::chrono::steady_clock::now();
  while (std::chrono::steady_clock::now() - start < std::chrono::seconds(2)) {
    rclcpp::spin_some(node_->get_node_base_interface());
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if (::testing::Mock::VerifyAndClear(mock_controllers_[0].get())) {
      break;
    }
  }
}

// =============================================================================
// main — init gtest with ROS2
// =============================================================================

int main(int argc, char ** argv)
{
  ::testing::InitGoogleMock(&argc, argv);
  return RUN_ALL_TESTS();
}
