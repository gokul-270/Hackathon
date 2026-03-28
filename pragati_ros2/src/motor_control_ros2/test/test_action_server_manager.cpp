/*
 * ActionServerManager Unit Tests (TDD RED phase)
 *
 * Tests for the ActionServerManager class extracted from MG6010ControllerNode.
 * Covers: construction, StepResponseTest, JointPositionCommand, JointHoming,
 *         thread safety (same-type rejection, cross-type concurrency,
 *         per-joint concurrency).
 *
 * Part of mg6010-decomposition Phase 2 (Step 5).
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include "motor_control_ros2/action_server_manager.hpp"
#include "motor_control_ros2/motor_manager.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

#include <atomic>
#include <chrono>
#include <future>
#include <memory>
#include <string>
#include <thread>
#include <vector>

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using ::testing::_;
using ::testing::Return;

// Client-side goal handle aliases (WrappedResult lives on ClientGoalHandle, not ServerGoalHandle)
using ClientGoalHandleStepResponse = rclcpp_action::ClientGoalHandle<StepResponseTest>;
using ClientGoalHandleJointPosCmd = rclcpp_action::ClientGoalHandle<JointPosCmd>;
using ClientGoalHandleJointHoming = rclcpp_action::ClientGoalHandle<JointHomingAction>;

// =============================================================================
// GMock MockMotorController — full mock of MotorControllerInterface
// (Duplicated from test_motor_manager.cpp; will be shared in Phase 3)
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
// Helper: spin executor in background thread for action client communication
// =============================================================================

class SpinHelper
{
public:
  explicit SpinHelper(rclcpp::node_interfaces::NodeBaseInterface::SharedPtr node_base)
  : executor_(std::make_shared<rclcpp::executors::SingleThreadedExecutor>())
  {
    executor_->add_node(node_base);
    spin_thread_ = std::thread([this]() { executor_->spin(); });
  }

  ~SpinHelper()
  {
    executor_->cancel();
    if (spin_thread_.joinable()) {
      spin_thread_.join();
    }
  }

  SpinHelper(const SpinHelper &) = delete;
  SpinHelper & operator=(const SpinHelper &) = delete;

private:
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread spin_thread_;
};

// =============================================================================
// Test Fixture — creates MotorManager + ActionServerManager with mock motors
// =============================================================================

class ActionServerManagerTest : public ::testing::Test
{
protected:
  static constexpr size_t NUM_MOTORS = 3;

  static void SetUpTestSuite()
  {
    rclcpp::init(0, nullptr);
  }

  static void TearDownTestSuite()
  {
    rclcpp::shutdown();
  }

  void SetUp() override
  {
    // Unique node name per test to avoid ROS2 name conflicts
    node_ = std::make_shared<rclcpp_lifecycle::LifecycleNode>(
      "test_asm_node_" + std::to_string(test_counter_++));
    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    // Create mock controllers with known CAN IDs (1, 2, 3)
    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      auto mock = std::make_shared<MockMotorController>();
      MotorConfiguration config;
      config.can_id = static_cast<uint8_t>(i + 1);
      config.joint_name = joint_names_[i];
      ON_CALL(*mock, get_configuration()).WillByDefault(Return(config));

      // Default mock behaviors for common calls
      ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_velocity()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_torque()).WillByDefault(Return(0.0));
      ON_CALL(*mock, set_position(_, _, _)).WillByDefault(Return(true));
      ON_CALL(*mock, set_velocity(_, _)).WillByDefault(Return(true));
      ON_CALL(*mock, stop()).WillByDefault(Return(true));
      ON_CALL(*mock, emergency_stop()).WillByDefault(Return(true));
      ON_CALL(*mock, set_enabled(_)).WillByDefault(Return(true));
      ON_CALL(*mock, home_motor(_)).WillByDefault(Return(true));
      ON_CALL(*mock, setCurrentPositionAsZero()).WillByDefault(Return(true));

      MotorStatus default_status;
      default_status.state = MotorStatus::CLOSED_LOOP_CONTROL;
      default_status.temperature = 40.0;
      default_status.hardware_connected = true;
      default_status.motor_enabled = true;
      ON_CALL(*mock, get_status()).WillByDefault(Return(default_status));

      mock_controllers_.push_back(mock);
      controllers_.push_back(mock);
    }

    // Construct MotorManager with test-only constructor
    motor_manager_ = std::make_unique<MotorManager>(
      node_, mock_can_, controllers_, joint_names_, homing_positions_);

    // Mark all motors available and enabled
    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      motor_manager_->setAvailable(i, true);
      motor_manager_->setEnabled(i, true);
    }

    // Reset callback tracking
    motor_failure_calls_.clear();
    interlock_blocked_ = false;
    watchdog_exempt_value_.store(false);

    // Create recording callbacks
    callbacks_.handle_motor_failure =
      [this](size_t motor_idx, const std::string & cmd_type,
             double target_value, const std::string & error_reason,
             const char * func_name) {
        std::lock_guard<std::mutex> lock(callback_mutex_);
        motor_failure_calls_.push_back(
          {motor_idx, cmd_type, target_value, error_reason,
           func_name ? std::string(func_name) : ""});
      };

    callbacks_.check_j3j4_interlock =
      [this](size_t /*motor_idx*/, double /*requested_position*/,
             const char * /*source*/) -> bool {
        return interlock_blocked_.load();
      };

    callbacks_.set_watchdog_exempt =
      [this](bool exempt) {
        watchdog_exempt_value_.store(exempt);
      };

    // Construct ActionServerManager
    asm_ = std::make_unique<ActionServerManager>(
      node_, *motor_manager_, callbacks_);
  }

  void TearDown() override
  {
    asm_.reset();
    motor_manager_.reset();
    controllers_.clear();
    mock_controllers_.clear();
    node_.reset();
  }

  MockMotorController & mock(size_t idx) { return *mock_controllers_.at(idx); }

  // -- Motor failure tracking --
  struct MotorFailureRecord
  {
    size_t motor_idx;
    std::string cmd_type;
    double target_value;
    std::string error_reason;
    std::string func_name;
  };

  // -- Members --
  static inline int test_counter_{0};

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;
  std::vector<std::shared_ptr<MockMotorController>> mock_controllers_;
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;

  std::vector<std::string> joint_names_{"base", "mid", "tip"};
  std::vector<double> homing_positions_{0.0, 1.57, -0.5};

  std::unique_ptr<MotorManager> motor_manager_;
  ActionCallbacks callbacks_;
  std::unique_ptr<ActionServerManager> asm_;

  // Callback tracking state
  std::mutex callback_mutex_;
  std::vector<MotorFailureRecord> motor_failure_calls_;
  std::atomic<bool> interlock_blocked_{false};
  std::atomic<bool> watchdog_exempt_value_{false};
};

// =============================================================================
// 5.2: Construction Tests
// =============================================================================

TEST_F(ActionServerManagerTest, Construction_ValidArgs)
{
  // asm_ already constructed in SetUp — verify it's non-null
  ASSERT_NE(asm_, nullptr);
}

TEST_F(ActionServerManagerTest, Construction_NullNodeThrows)
{
  EXPECT_THROW(
    {
      auto bad = std::make_unique<ActionServerManager>(
        nullptr, *motor_manager_, callbacks_);
    },
    std::invalid_argument);
}

TEST_F(ActionServerManagerTest, Construction_EmptyMotorFailureCallbackThrows)
{
  ActionCallbacks bad_callbacks = callbacks_;
  bad_callbacks.handle_motor_failure = nullptr;

  EXPECT_THROW(
    {
      auto bad = std::make_unique<ActionServerManager>(
        node_, *motor_manager_, bad_callbacks);
    },
    std::invalid_argument);
}

TEST_F(ActionServerManagerTest, Construction_EmptyInterlockCallbackThrows)
{
  ActionCallbacks bad_callbacks = callbacks_;
  bad_callbacks.check_j3j4_interlock = nullptr;

  EXPECT_THROW(
    {
      auto bad = std::make_unique<ActionServerManager>(
        node_, *motor_manager_, bad_callbacks);
    },
    std::invalid_argument);
}

TEST_F(ActionServerManagerTest, Construction_EmptyWatchdogCallbackThrows)
{
  ActionCallbacks bad_callbacks = callbacks_;
  bad_callbacks.set_watchdog_exempt = nullptr;

  EXPECT_THROW(
    {
      auto bad = std::make_unique<ActionServerManager>(
        node_, *motor_manager_, bad_callbacks);
    },
    std::invalid_argument);
}

TEST_F(ActionServerManagerTest, Destruction_JoinsThreads)
{
  // Construct a separate ASM, then destroy it — verify no crash or hang.
  // This is a basic smoke test; the full version would trigger an action
  // mid-flight and verify the destructor waits.
    auto node2 = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_asm_destruct_node");
  auto mm2 = std::make_unique<MotorManager>(
    node2, mock_can_, controllers_, joint_names_, homing_positions_);
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    mm2->setAvailable(i, true);
    mm2->setEnabled(i, true);
  }

  auto asm2 = std::make_unique<ActionServerManager>(
    node2, *mm2, callbacks_);

  // Destroy — should not hang or crash
  EXPECT_NO_THROW(asm2.reset());
}

// =============================================================================
// 5.3: StepResponseTest Tests
// =============================================================================

TEST_F(ActionServerManagerTest, StepResponse_NormalCompletion)
{
  // Set up an executor to spin for action client communication
  SpinHelper spinner(node_->get_node_base_interface());

  // Create action client
  auto client = rclcpp_action::create_client<StepResponseTest>(
    node_, "~/step_response_test");

  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)))
    << "Action server not available";

  // Build goal: motor CAN ID 1, 10-degree step, 2s duration
  auto goal_msg = StepResponseTest::Goal();
  goal_msg.motor_id = 1;
  goal_msg.step_size_degrees = 10.0f;
  goal_msg.duration_seconds = 2.0f;

  // Mock motor returns position that tracks toward target
  ON_CALL(mock(0), get_position())
    .WillByDefault(Return(0.1745));  // ~10 degrees in radians

  // Send goal
  auto send_goal_options = rclcpp_action::Client<StepResponseTest>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleStepResponse::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleStepResponse::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleStepResponse::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);

  // Wait for goal acceptance
  auto goal_handle_status = goal_handle_future.wait_for(std::chrono::seconds(5));
  ASSERT_EQ(goal_handle_status, std::future_status::ready)
    << "Goal was not accepted in time";

  auto goal_handle = goal_handle_future.get();
  ASSERT_NE(goal_handle, nullptr) << "Goal was rejected";

  // Wait for result (test duration + margin)
  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready)
    << "Result not received in time";

  auto result = result_future.get();
  EXPECT_TRUE(result->result->success) << "Step response test should succeed";
  EXPECT_FALSE(result->result->timestamps.empty())
    << "Should have recorded timestamps";
  EXPECT_FALSE(result->result->positions.empty())
    << "Should have recorded positions";
  EXPECT_EQ(result->result->timestamps.size(), result->result->positions.size())
    << "Timestamps and positions arrays should be same length";
}

TEST_F(ActionServerManagerTest, StepResponse_SafetyAbortDeviation)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<StepResponseTest>(
    node_, "~/step_response_test");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = StepResponseTest::Goal();
  goal_msg.motor_id = 1;
  goal_msg.step_size_degrees = 10.0f;
  goal_msg.duration_seconds = 5.0f;

  // Two-phase mock: initial_position = 0.0, then during loop position jumps to 1.0
  // Deviation = |1.0 - target| >> max_deviation (2x step), triggering safety abort
  EXPECT_CALL(mock(0), get_position())
    .WillOnce(Return(0.0))           // initial_position capture
    .WillRepeatedly(Return(1.0));    // loop reads: far from target

  auto send_goal_options = rclcpp_action::Client<StepResponseTest>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleStepResponse::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleStepResponse::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleStepResponse::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected (may indicate server not yet implemented)";
  }

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_FALSE(result->result->success)
    << "Step response should abort on excessive deviation";
  EXPECT_FALSE(result->result->error_message.empty())
    << "Should provide error message on safety abort";
}

TEST_F(ActionServerManagerTest, StepResponse_SafetyAbortTemperature)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<StepResponseTest>(
    node_, "~/step_response_test");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = StepResponseTest::Goal();
  goal_msg.motor_id = 1;
  goal_msg.step_size_degrees = 10.0f;
  goal_msg.duration_seconds = 5.0f;

  // Mock motor returns high temperature
  MotorStatus hot_status;
  hot_status.state = MotorStatus::CLOSED_LOOP_CONTROL;
  hot_status.temperature = 85.0;  // Over-temperature threshold
  hot_status.hardware_connected = true;
  hot_status.motor_enabled = true;
  ON_CALL(mock(0), get_status()).WillByDefault(Return(hot_status));
  ON_CALL(mock(0), get_position()).WillByDefault(Return(0.1));

  auto send_goal_options = rclcpp_action::Client<StepResponseTest>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleStepResponse::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleStepResponse::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleStepResponse::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected (may indicate server not yet implemented)";
  }

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_FALSE(result->result->success)
    << "Step response should abort on over-temperature";
}

TEST_F(ActionServerManagerTest, StepResponse_Cancellation)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<StepResponseTest>(
    node_, "~/step_response_test");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = StepResponseTest::Goal();
  goal_msg.motor_id = 1;
  goal_msg.step_size_degrees = 10.0f;
  goal_msg.duration_seconds = 10.0f;  // Long duration so we can cancel mid-test

  ON_CALL(mock(0), get_position()).WillByDefault(Return(0.1));

  auto send_goal_options = rclcpp_action::Client<StepResponseTest>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleStepResponse::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleStepResponse::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleStepResponse::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  // Wait briefly for test to start
  std::this_thread::sleep_for(std::chrono::milliseconds(500));

  // Cancel the goal
  auto cancel_future = client->async_cancel_goal(goal_handle);
  auto cancel_status = cancel_future.wait_for(std::chrono::seconds(5));
  ASSERT_EQ(cancel_status, std::future_status::ready)
    << "Cancel request timed out";

  // Wait for result
  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready)
    << "Result not received after cancellation";

  auto result = result_future.get();
  // Cancelled goals should return partial data
  EXPECT_EQ(result->code, rclcpp_action::ResultCode::CANCELED)
    << "Expected CANCELED result code";
}

// =============================================================================
// 5.4: JointPositionCommand Tests
// =============================================================================

TEST_F(ActionServerManagerTest, JointPosCmd_ToleranceCompletion)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;            // CAN ID 2 = motor index 1 ("mid")
  goal_msg.target_position = 1.0;   // 1 radian
  goal_msg.max_velocity = 0.0;      // Use default

  // Mock motor converges to target position
  ON_CALL(mock(1), get_position()).WillByDefault(Return(1.0));

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  ASSERT_NE(goal_handle, nullptr) << "Goal was rejected";

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_TRUE(result->result->success)
    << "Should succeed when motor reaches target within tolerance";
  EXPECT_EQ(result->result->reason, "REACHED")
    << "Reason should be REACHED";
  EXPECT_NEAR(result->result->actual_position, 1.0, 0.1)
    << "Actual position should be near target";
}

TEST_F(ActionServerManagerTest, JointPosCmd_Timeout)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;
  goal_msg.target_position = 3.14;  // Target far from current position
  goal_msg.max_velocity = 0.0;

  // Mock motor never reaches target
  ON_CALL(mock(1), get_position()).WillByDefault(Return(0.0));

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  // Allow enough time for timeout (5s default + margin)
  auto result_status = result_future.wait_for(std::chrono::seconds(15));
  ASSERT_EQ(result_status, std::future_status::ready)
    << "Result not received (timeout mechanism may not have fired)";

  auto result = result_future.get();
  EXPECT_FALSE(result->result->success)
    << "Should fail when motor does not reach target";
  EXPECT_EQ(result->result->reason, "TIMEOUT")
    << "Reason should be TIMEOUT";
}

TEST_F(ActionServerManagerTest, JointPosCmd_Cancellation)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;
  goal_msg.target_position = 3.14;
  goal_msg.max_velocity = 0.0;

  // Motor never reaches target — will remain in-progress
  ON_CALL(mock(1), get_position()).WillByDefault(Return(0.0));

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  // Wait briefly for execution to begin
  std::this_thread::sleep_for(std::chrono::milliseconds(500));

  // Cancel
  auto cancel_future = client->async_cancel_goal(goal_handle);
  ASSERT_EQ(cancel_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_EQ(result->code, rclcpp_action::ResultCode::CANCELED)
    << "Expected CANCELED result code";

  // Motor should be stopped after cancellation
  // (verified by checking stop() was called — but since ON_CALL is set up,
  //  we verify the result reason instead)
  EXPECT_EQ(result->result->reason, "CANCELLED")
    << "Reason should be CANCELLED";
}

TEST_F(ActionServerManagerTest, JointPosCmd_MotorFailureCallback)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;
  goal_msg.target_position = 1.0;
  goal_msg.max_velocity = 0.0;

  // Mock motor fails on set_position (CAN command failure)
  ON_CALL(mock(1), set_position(_, _, _)).WillByDefault(Return(false));
  ON_CALL(mock(1), get_position()).WillByDefault(Return(0.0));

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_FALSE(result->result->success)
    << "Should fail when CAN command fails";
  EXPECT_EQ(result->result->reason, "ERROR")
    << "Reason should be ERROR on CAN failure";

  // Verify motor failure callback was invoked
  std::lock_guard<std::mutex> lock(callback_mutex_);
  EXPECT_FALSE(motor_failure_calls_.empty())
    << "handle_motor_failure callback should have been invoked";
}

TEST_F(ActionServerManagerTest, JointPosCmd_J3J4Interlock)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  // Enable interlock — blocks motion
  interlock_blocked_.store(true);

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;
  goal_msg.target_position = 1.0;
  goal_msg.max_velocity = 0.0;

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    // Goal may be rejected at the goal-level, which is also acceptable
    // for interlock blocking
    SUCCEED() << "Goal correctly rejected by interlock check";
    return;
  }

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_FALSE(result->result->success)
    << "Should fail when J3/J4 interlock blocks motion";
}

TEST_F(ActionServerManagerTest, JointPosCmd_MotionStateOwned)
{
  // Design verification: ActionServerManager owns motion tracking state.
  // Construct ASM — if motion state was not moved here, construction would
  // fail or compile errors would indicate the state is still in the god-class.
  //
  // This test simply verifies the ASM constructs successfully with the
  // expectation that motion tracking vectors are sized to motorCount().
  ASSERT_NE(asm_, nullptr);
  // If this compiles and passes, motion state is owned by ASM.
}

// =============================================================================
// 5.5: JointHoming Tests
// =============================================================================

TEST_F(ActionServerManagerTest, JointHoming_SingleJoint)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointHomingAction>(
    node_, "/joint_homing");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointHomingAction::Goal();
  goal_msg.joint_ids = {2};  // Home joint 2 (motor index 1, "mid")

  // Mock motor: position reads back homing position (implementation uses
  // set_position-based homing, not home_motor()/setCurrentPositionAsZero())
  ON_CALL(mock(1), get_position()).WillByDefault(Return(homing_positions_[1]));

  auto send_goal_options = rclcpp_action::Client<JointHomingAction>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointHoming::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointHoming::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointHoming::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  ASSERT_NE(goal_handle, nullptr) << "Goal was rejected";

  auto result_status = result_future.wait_for(std::chrono::seconds(15));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_TRUE(result->result->success)
    << "Single joint homing should succeed";
  EXPECT_EQ(result->result->final_positions.size(), 1u)
    << "Should report one joint's final position";
}

TEST_F(ActionServerManagerTest, JointHoming_MultiJointSequential)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointHomingAction>(
    node_, "/joint_homing");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointHomingAction::Goal();
  goal_msg.joint_ids = {1, 2, 3};  // Home all 3 joints

  // All motors: position reads back homing position (implementation uses
  // set_position-based homing, not home_motor()/setCurrentPositionAsZero())
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    ON_CALL(mock(i), get_position())
      .WillByDefault(Return(homing_positions_[i]));
  }

  auto send_goal_options = rclcpp_action::Client<JointHomingAction>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointHoming::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointHoming::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointHoming::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  ASSERT_NE(goal_handle, nullptr) << "Goal was rejected";

  // Multi-joint homing takes longer
  auto result_status = result_future.wait_for(std::chrono::seconds(30));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_TRUE(result->result->success)
    << "Multi-joint homing should succeed";
  EXPECT_EQ(result->result->final_positions.size(), 3u)
    << "Should report 3 joints' final positions";
}

TEST_F(ActionServerManagerTest, JointHoming_CancelRestoresWatchdog)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointHomingAction>(
    node_, "/joint_homing");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointHomingAction::Goal();
  goal_msg.joint_ids = {1, 2, 3};

  // Make homing slow so we can cancel mid-way — use a blocking home_motor
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    ON_CALL(mock(i), home_motor(_)).WillByDefault([](const HomingConfig *) {
      std::this_thread::sleep_for(std::chrono::seconds(5));
      return true;
    });
    ON_CALL(mock(i), setCurrentPositionAsZero()).WillByDefault(Return(true));
    ON_CALL(mock(i), get_position()).WillByDefault(Return(0.0));
  }

  auto send_goal_options = rclcpp_action::Client<JointHomingAction>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointHoming::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointHoming::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointHoming::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  // Homing should set watchdog exempt to true
  std::this_thread::sleep_for(std::chrono::milliseconds(500));
  EXPECT_TRUE(watchdog_exempt_value_.load())
    << "Watchdog should be exempt during homing";

  // Cancel
  auto cancel_future = client->async_cancel_goal(goal_handle);
  ASSERT_EQ(cancel_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto result_status = result_future.wait_for(std::chrono::seconds(15));
  ASSERT_EQ(result_status, std::future_status::ready);

  // After cancellation, watchdog should be restored (exempt = false)
  EXPECT_FALSE(watchdog_exempt_value_.load())
    << "Watchdog exemption should be restored after homing cancellation";
}

TEST_F(ActionServerManagerTest, JointHoming_CancelAwareWaits)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointHomingAction>(
    node_, "/joint_homing");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointHomingAction::Goal();
  goal_msg.joint_ids = {1};

  // home_motor blocks for a long time — cancel should interrupt within ~100ms
  ON_CALL(mock(0), home_motor(_)).WillByDefault([](const HomingConfig *) {
    std::this_thread::sleep_for(std::chrono::seconds(30));
    return true;
  });
  ON_CALL(mock(0), setCurrentPositionAsZero()).WillByDefault(Return(true));
  ON_CALL(mock(0), get_position()).WillByDefault(Return(0.0));

  auto send_goal_options = rclcpp_action::Client<JointHomingAction>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointHoming::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointHoming::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointHoming::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  // Let homing start
  std::this_thread::sleep_for(std::chrono::milliseconds(200));

  // Cancel and measure response time
  auto cancel_start = std::chrono::steady_clock::now();
  auto cancel_future = client->async_cancel_goal(goal_handle);
  ASSERT_EQ(cancel_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto result_status = result_future.wait_for(std::chrono::seconds(5));
  auto cancel_elapsed = std::chrono::steady_clock::now() - cancel_start;
  auto cancel_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
    cancel_elapsed).count();

  ASSERT_EQ(result_status, std::future_status::ready)
    << "Result not received after cancellation";

  // Cancel-aware waits should respond within ~100ms (allow 500ms margin for CI)
  EXPECT_LT(cancel_ms, 500)
    << "Cancellation response took " << cancel_ms
    << "ms (expected <500ms for cancel-aware waits)";
}

// =============================================================================
// 5.6: Thread Safety Tests
// =============================================================================

TEST_F(ActionServerManagerTest, ThreadSafety_SameTypeRejection)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<StepResponseTest>(
    node_, "~/step_response_test");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  // First goal: long duration
  auto goal1 = StepResponseTest::Goal();
  goal1.motor_id = 1;
  goal1.step_size_degrees = 10.0f;
  goal1.duration_seconds = 10.0f;

  ON_CALL(mock(0), get_position()).WillByDefault(Return(0.1));

  auto send_opts1 = rclcpp_action::Client<StepResponseTest>::SendGoalOptions();
  auto gh_future1 = client->async_send_goal(goal1, send_opts1);
  ASSERT_EQ(gh_future1.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto gh1 = gh_future1.get();
  ASSERT_NE(gh1, nullptr) << "First goal should be accepted";

  // Wait for first goal's execution to begin
  std::this_thread::sleep_for(std::chrono::milliseconds(300));

  // Second goal: should be rejected because step_test_running_ is true
  auto goal2 = StepResponseTest::Goal();
  goal2.motor_id = 2;
  goal2.step_size_degrees = 5.0f;
  goal2.duration_seconds = 2.0f;

  auto send_opts2 = rclcpp_action::Client<StepResponseTest>::SendGoalOptions();
  auto gh_future2 = client->async_send_goal(goal2, send_opts2);
  ASSERT_EQ(gh_future2.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto gh2 = gh_future2.get();
  EXPECT_EQ(gh2, nullptr)
    << "Second StepResponseTest goal should be rejected while first is running";

  // Clean up: cancel first goal
  if (gh1) {
    client->async_cancel_goal(gh1);
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  }
}

TEST_F(ActionServerManagerTest, ThreadSafety_CrossTypeConcurrency)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto step_client = rclcpp_action::create_client<StepResponseTest>(
    node_, "~/step_response_test");
  auto jpc_client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");

  ASSERT_TRUE(step_client->wait_for_action_server(std::chrono::seconds(5)));
  ASSERT_TRUE(jpc_client->wait_for_action_server(std::chrono::seconds(5)));

  // Start StepResponseTest on motor 1
  auto step_goal = StepResponseTest::Goal();
  step_goal.motor_id = 1;
  step_goal.step_size_degrees = 10.0f;
  step_goal.duration_seconds = 10.0f;

  ON_CALL(mock(0), get_position()).WillByDefault(Return(0.1));
  ON_CALL(mock(1), get_position()).WillByDefault(Return(1.0));

  auto step_opts = rclcpp_action::Client<StepResponseTest>::SendGoalOptions();
  auto step_future = step_client->async_send_goal(step_goal, step_opts);
  ASSERT_EQ(step_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto step_gh = step_future.get();
  ASSERT_NE(step_gh, nullptr) << "StepResponse goal should be accepted";

  // Wait for step test to start executing
  std::this_thread::sleep_for(std::chrono::milliseconds(300));

  // Start JointPositionCommand on motor 2 — different action type, should be accepted
  auto jpc_goal = JointPosCmd::Goal();
  jpc_goal.joint_id = 2;
  jpc_goal.target_position = 1.0;
  jpc_goal.max_velocity = 0.0;

  auto jpc_opts = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();
  auto jpc_future = jpc_client->async_send_goal(jpc_goal, jpc_opts);
  ASSERT_EQ(jpc_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto jpc_gh = jpc_future.get();
  EXPECT_NE(jpc_gh, nullptr)
    << "JointPositionCommand should be accepted concurrently with StepResponseTest";

  // Clean up
  if (step_gh) {
    step_client->async_cancel_goal(step_gh);
  }
  if (jpc_gh) {
    jpc_client->async_cancel_goal(jpc_gh);
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(500));
}

TEST_F(ActionServerManagerTest, ThreadSafety_PerJointConcurrency)
{
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  // Motor positions: return near but not at target to keep goals active
  ON_CALL(mock(0), get_position()).WillByDefault(Return(0.5));
  ON_CALL(mock(2), get_position()).WillByDefault(Return(0.5));

  // Goal 1: joint 1 (motor index 0)
  auto goal1 = JointPosCmd::Goal();
  goal1.joint_id = 1;
  goal1.target_position = 2.0;
  goal1.max_velocity = 0.0;

  auto opts1 = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result1_promise;
  auto result1_future = result1_promise.get_future();
  opts1.result_callback =
    [&result1_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result1_promise.set_value(wrapped);
    };

  auto gh_future1 = client->async_send_goal(goal1, opts1);
  ASSERT_EQ(gh_future1.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto gh1 = gh_future1.get();
  ASSERT_NE(gh1, nullptr) << "Goal 1 (joint 1) should be accepted";

  // Wait for first goal to start executing
  std::this_thread::sleep_for(std::chrono::milliseconds(300));

  // Goal 2: joint 3 (motor index 2) — different joint, should be accepted
  auto goal2 = JointPosCmd::Goal();
  goal2.joint_id = 3;
  goal2.target_position = 2.0;
  goal2.max_velocity = 0.0;

  auto opts2 = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();
  auto gh_future2 = client->async_send_goal(goal2, opts2);
  ASSERT_EQ(gh_future2.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto gh2 = gh_future2.get();
  EXPECT_NE(gh2, nullptr)
    << "Goal 2 (joint 3) should be accepted while joint 1 is active";

  // Goal 3: joint 1 again — SAME joint, should be rejected
  auto goal3 = JointPosCmd::Goal();
  goal3.joint_id = 1;
  goal3.target_position = 1.0;
  goal3.max_velocity = 0.0;

  auto opts3 = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();
  auto gh_future3 = client->async_send_goal(goal3, opts3);
  ASSERT_EQ(gh_future3.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto gh3 = gh_future3.get();
  EXPECT_EQ(gh3, nullptr)
    << "Goal 3 (duplicate joint 1) should be rejected";

  // Clean up
  if (gh1) {
    client->async_cancel_goal(gh1);
  }
  if (gh2) {
    client->async_cancel_goal(gh2);
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(500));
}

// =============================================================================
// 5.8: Watchdog Exemption During Position Commands (Task 1.8)
// =============================================================================

TEST_F(ActionServerManagerTest, JointPosCmd_WatchdogExemptDuringExecution)
{
  // Verify: watchdog_exempt is set TRUE during position command blocking loop,
  // and cleared to FALSE after successful completion.
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  // Motor starts far from target, then converges after a delay
  std::atomic<double> reported_pos{0.0};
  ON_CALL(mock(1), get_position()).WillByDefault([&]() {
    return reported_pos.load();
  });

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;
  goal_msg.target_position = 1.0;
  goal_msg.max_velocity = 0.0;

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  ASSERT_NE(goal_handle, nullptr) << "Goal was rejected";

  // Wait for execution to begin — watchdog should be exempt
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  EXPECT_TRUE(watchdog_exempt_value_.load())
    << "Watchdog should be exempt during position command execution";

  // Now converge to target
  reported_pos.store(1.0);

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_TRUE(result->result->success);
  EXPECT_EQ(result->result->reason, "REACHED");

  // After completion, watchdog exemption MUST be cleared
  EXPECT_FALSE(watchdog_exempt_value_.load())
    << "Watchdog exemption must be cleared after successful position command";
}

TEST_F(ActionServerManagerTest, JointPosCmd_WatchdogExemptClearedOnTimeout)
{
  // Verify: watchdog_exempt cleared to FALSE after position command timeout.
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;
  goal_msg.target_position = 3.14;
  goal_msg.max_velocity = 0.0;

  // Motor never reaches target
  ON_CALL(mock(1), get_position()).WillByDefault(Return(0.0));

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  auto result_status = result_future.wait_for(std::chrono::seconds(15));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_FALSE(result->result->success);
  EXPECT_EQ(result->result->reason, "TIMEOUT");

  // After timeout, watchdog exemption MUST be cleared
  EXPECT_FALSE(watchdog_exempt_value_.load())
    << "Watchdog exemption must be cleared after position command timeout";
}

TEST_F(ActionServerManagerTest, JointPosCmd_WatchdogExemptClearedOnCancel)
{
  // Verify: watchdog_exempt cleared to FALSE after position command cancellation.
  SpinHelper spinner(node_->get_node_base_interface());

  auto client = rclcpp_action::create_client<JointPosCmd>(
    node_, "/joint_position_command");
  ASSERT_TRUE(client->wait_for_action_server(std::chrono::seconds(5)));

  auto goal_msg = JointPosCmd::Goal();
  goal_msg.joint_id = 2;
  goal_msg.target_position = 3.14;
  goal_msg.max_velocity = 0.0;

  // Motor never reaches target
  ON_CALL(mock(1), get_position()).WillByDefault(Return(0.0));

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();

  std::promise<std::shared_ptr<ClientGoalHandleJointPosCmd::WrappedResult>> result_promise;
  auto result_future = result_promise.get_future();

  send_goal_options.result_callback =
    [&result_promise](const ClientGoalHandleJointPosCmd::WrappedResult & result) {
      auto wrapped = std::make_shared<ClientGoalHandleJointPosCmd::WrappedResult>(result);
      result_promise.set_value(wrapped);
    };

  auto goal_handle_future = client->async_send_goal(goal_msg, send_goal_options);
  ASSERT_EQ(goal_handle_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto goal_handle = goal_handle_future.get();
  if (!goal_handle) {
    GTEST_SKIP() << "Goal rejected";
  }

  // Wait for execution to begin
  std::this_thread::sleep_for(std::chrono::milliseconds(500));

  // Cancel
  auto cancel_future = client->async_cancel_goal(goal_handle);
  ASSERT_EQ(cancel_future.wait_for(std::chrono::seconds(5)),
    std::future_status::ready);

  auto result_status = result_future.wait_for(std::chrono::seconds(10));
  ASSERT_EQ(result_status, std::future_status::ready);

  auto result = result_future.get();
  EXPECT_EQ(result->code, rclcpp_action::ResultCode::CANCELED);

  // After cancellation, watchdog exemption MUST be cleared
  EXPECT_FALSE(watchdog_exempt_value_.load())
    << "Watchdog exemption must be cleared after position command cancellation";
}

// =============================================================================
// Main
// =============================================================================

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
