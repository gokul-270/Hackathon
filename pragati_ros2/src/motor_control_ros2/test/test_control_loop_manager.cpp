/*
 * ControlLoopManager Unit Tests (TDD RED phase)
 *
 * Tests for the ControlLoopManager class extracted from MG6010ControllerNode.
 * The class under test does NOT exist yet — these tests define its expected
 * public API and behavior. All tests should FAIL to compile or link until
 * the implementation is written (GREEN phase).
 *
 * Covers: construction, control loop timer, PID write callbacks,
 *         position/velocity/stop commands, trajectory execution,
 *         timing stability, and zero-copy review checklist.
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

#include "motor_control_ros2/control_loop_manager.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

#include "motor_control_msgs/srv/write_pid.hpp"
#include "motor_control_msgs/srv/write_pid_to_rom.hpp"

#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <memory>
#include <string>
#include <thread>
#include <vector>

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::InSequence;
using ::testing::Return;
using ::testing::SaveArg;

// =============================================================================
// GMock MockMotorController — full mock of MotorControllerInterface
// =============================================================================

class MockMotorController : public MotorControllerInterface
{
public:
  // Pure virtual methods (must be mocked)
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

  // Defaulted virtual methods (also mocked so we can set expectations)
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
// Test Fixture (4.1)
// =============================================================================

class ControlLoopManagerTest : public ::testing::Test
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
    node_ = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_clm_node");
    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    // Create mock controllers with known CAN IDs (1, 2, 3)
    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      auto mock = std::make_shared<MockMotorController>();
      MotorConfiguration config;
      config.can_id = static_cast<uint8_t>(i + 1);  // CAN IDs: 1, 2, 3
      config.joint_name = "joint_" + std::to_string(i);

      // Default: get_configuration returns the config with correct can_id
      ON_CALL(*mock, get_configuration()).WillByDefault(Return(config));

      // Default: get_position/velocity/torque return 0.0 (needed for joint_states)
      ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_velocity()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_torque()).WillByDefault(Return(0.0));

      mock_controllers_.push_back(mock);
      controllers_.push_back(mock);
      joint_names_.push_back(config.joint_name);
      motor_available_[i].store(true);
    }

    manager_ = std::make_unique<ControlLoopManager>(
      node_, mock_can_, controllers_, motor_available_, joint_names_);
  }

  void TearDown() override
  {
    manager_.reset();
    controllers_.clear();
    mock_controllers_.clear();
    node_.reset();
  }

  // Helper: get raw mock pointer for setting expectations
  MockMotorController & mock(size_t idx) { return *mock_controllers_.at(idx); }

  // Helper: spin the node for a given duration using spin_some in a loop
  void spinFor(std::chrono::milliseconds duration)
  {
    auto start = std::chrono::steady_clock::now();
    while (std::chrono::steady_clock::now() - start < duration) {
      rclcpp::spin_some(node_->get_node_base_interface());
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
  }

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;

  // Mock controllers (typed access for EXPECT_CALL)
  std::vector<std::shared_ptr<MockMotorController>> mock_controllers_;

  // Passed by reference to ControlLoopManager
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;
  std::array<std::atomic<bool>, MAX_MOTORS> motor_available_{};
  std::vector<std::string> joint_names_;

  std::unique_ptr<ControlLoopManager> manager_;
};

// =============================================================================
// 4.2: Construction — valid args
// =============================================================================

TEST_F(ControlLoopManagerTest, Construction_ValidArgs)
{
  // Manager was already constructed in SetUp — verify it didn't throw
  ASSERT_NE(manager_, nullptr);
}

// =============================================================================
// 4.2: Construction — null node throws
// =============================================================================

TEST_F(ControlLoopManagerTest, Construction_NullNode_Throws)
{
  manager_.reset();

  EXPECT_THROW(
    {
      auto bad = std::make_unique<ControlLoopManager>(
        nullptr, mock_can_, controllers_, motor_available_, joint_names_);
    },
    std::invalid_argument);
}

// =============================================================================
// 4.2: Construction — null CAN interface throws
// =============================================================================

TEST_F(ControlLoopManagerTest, Construction_NullCanInterface_Throws)
{
  manager_.reset();

  EXPECT_THROW(
    {
      auto bad = std::make_unique<ControlLoopManager>(
        node_, nullptr, controllers_, motor_available_, joint_names_);
    },
    std::invalid_argument);
}

// =============================================================================
// 4.3: Control loop timer fires at default 10Hz
// =============================================================================

TEST_F(ControlLoopManagerTest, ControlLoopTimer_Default10Hz_PublishesJointStates)
{
  // Subscribe to joint_states topic and count messages
  size_t message_count = 0;
  auto sub = node_->create_subscription<sensor_msgs::msg::JointState>(
    "joint_states", 10,
    [&message_count](sensor_msgs::msg::JointState::SharedPtr /*msg*/) {
      message_count++;
    });

  // Allow default expectations for status polling during control loop
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_CALL(mock(i), get_position()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
    EXPECT_CALL(mock(i), get_velocity()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
    EXPECT_CALL(mock(i), get_torque()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
  }

  // Spin for 350ms — at 10Hz expect ~3-4 callbacks, at least 2
  spinFor(std::chrono::milliseconds(350));

  EXPECT_GE(message_count, 2u)
    << "Expected at least 2 joint_states messages at 10Hz over 350ms, got "
    << message_count;
}

// =============================================================================
// 4.4: Control loop timer fires at overridden frequency (20Hz)
// =============================================================================

TEST_F(ControlLoopManagerTest, ControlLoopTimer_20Hz_MoreMessagesThan10Hz)
{
  // Destroy the default 10Hz manager and create a 20Hz one
  manager_.reset();

  auto manager_20hz = std::make_unique<ControlLoopManager>(
    node_, mock_can_, controllers_, motor_available_, joint_names_, 20.0);

  size_t message_count = 0;
  auto sub = node_->create_subscription<sensor_msgs::msg::JointState>(
    "joint_states", 10,
    [&message_count](sensor_msgs::msg::JointState::SharedPtr /*msg*/) {
      message_count++;
    });

  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_CALL(mock(i), get_position()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
    EXPECT_CALL(mock(i), get_velocity()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
    EXPECT_CALL(mock(i), get_torque()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
  }

  // Spin for 350ms — at 20Hz expect ~6-7 callbacks
  spinFor(std::chrono::milliseconds(350));

  EXPECT_GE(message_count, 5u)
    << "Expected at least 5 joint_states messages at 20Hz over 350ms, got "
    << message_count;

  manager_20hz.reset();
}

// =============================================================================
// 4.5: writePidCallback — success case
// =============================================================================

TEST_F(ControlLoopManagerTest, WritePidCallback_Success)
{
  // Motor CAN ID 1 → index 0
  EXPECT_CALL(mock(0), setPID(_))
    .Times(1)
    .WillOnce(Return(true));

  auto request = std::make_shared<motor_control_msgs::srv::WritePID::Request>();
  auto response = std::make_shared<motor_control_msgs::srv::WritePID::Response>();
  request->motor_id = 1;  // CAN ID of first mock controller
  request->angle_kp = 10;
  request->angle_ki = 20;
  request->speed_kp = 30;
  request->speed_ki = 40;
  request->current_kp = 50;
  request->current_ki = 60;

  manager_->writePidCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
}

// =============================================================================
// 4.6: writePidCallback — PID gains match request fields exactly
// =============================================================================

TEST_F(ControlLoopManagerTest, WritePidCallback_PidGainsMatchRequest)
{
  PIDParams captured_params;
  EXPECT_CALL(mock(0), setPID(_))
    .Times(1)
    .WillOnce(DoAll(SaveArg<0>(&captured_params), Return(true)));

  auto request = std::make_shared<motor_control_msgs::srv::WritePID::Request>();
  auto response = std::make_shared<motor_control_msgs::srv::WritePID::Response>();
  request->motor_id = 1;
  request->angle_kp = 11;
  request->angle_ki = 22;
  request->speed_kp = 33;
  request->speed_ki = 44;
  request->current_kp = 55;
  request->current_ki = 66;

  manager_->writePidCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(captured_params.angle_kp, 11);
  EXPECT_EQ(captured_params.angle_ki, 22);
  EXPECT_EQ(captured_params.speed_kp, 33);
  EXPECT_EQ(captured_params.speed_ki, 44);
  EXPECT_EQ(captured_params.current_kp, 55);
  EXPECT_EQ(captured_params.current_ki, 66);
}

// =============================================================================
// 4.6: writePidCallback — failure case (setPID returns false)
// =============================================================================

TEST_F(ControlLoopManagerTest, WritePidCallback_SetPIDFails)
{
  EXPECT_CALL(mock(0), setPID(_))
    .Times(1)
    .WillOnce(Return(false));

  auto request = std::make_shared<motor_control_msgs::srv::WritePID::Request>();
  auto response = std::make_shared<motor_control_msgs::srv::WritePID::Response>();
  request->motor_id = 1;
  request->angle_kp = 10;
  request->angle_ki = 20;
  request->speed_kp = 30;
  request->speed_ki = 40;
  request->current_kp = 50;
  request->current_ki = 60;

  manager_->writePidCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_FALSE(response->error_message.empty())
    << "Expected non-empty error_message when setPID fails";
}

// =============================================================================
// 4.6: writePidCallback — motor not found
// =============================================================================

TEST_F(ControlLoopManagerTest, WritePidCallback_MotorNotFound)
{
  auto request = std::make_shared<motor_control_msgs::srv::WritePID::Request>();
  auto response = std::make_shared<motor_control_msgs::srv::WritePID::Response>();
  request->motor_id = 99;  // Non-existent CAN ID

  manager_->writePidCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_NE(response->error_message.find("not found"), std::string::npos)
    << "Expected error_message to mention 'not found', got: "
    << response->error_message;
}

// =============================================================================
// 4.7: writePidToRomCallback — success case
// =============================================================================

TEST_F(ControlLoopManagerTest, WritePidToRomCallback_Success)
{
  PIDParams captured_params;
  EXPECT_CALL(mock(1), writePIDToROM(_))
    .Times(1)
    .WillOnce(DoAll(SaveArg<0>(&captured_params), Return(true)));

  auto request = std::make_shared<motor_control_msgs::srv::WritePIDToROM::Request>();
  auto response = std::make_shared<motor_control_msgs::srv::WritePIDToROM::Response>();
  request->motor_id = 2;  // CAN ID of second mock controller
  request->angle_kp = 15;
  request->angle_ki = 25;
  request->speed_kp = 35;
  request->speed_ki = 45;
  request->current_kp = 55;
  request->current_ki = 65;

  manager_->writePidToRomCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
  EXPECT_EQ(captured_params.angle_kp, 15);
  EXPECT_EQ(captured_params.angle_ki, 25);
  EXPECT_EQ(captured_params.speed_kp, 35);
  EXPECT_EQ(captured_params.speed_ki, 45);
  EXPECT_EQ(captured_params.current_kp, 55);
  EXPECT_EQ(captured_params.current_ki, 65);
}

// =============================================================================
// 4.7: writePidToRomCallback — failure case
// =============================================================================

TEST_F(ControlLoopManagerTest, WritePidToRomCallback_Fails)
{
  EXPECT_CALL(mock(0), writePIDToROM(_))
    .Times(1)
    .WillOnce(Return(false));

  auto request = std::make_shared<motor_control_msgs::srv::WritePIDToROM::Request>();
  auto response = std::make_shared<motor_control_msgs::srv::WritePIDToROM::Response>();
  request->motor_id = 1;
  request->angle_kp = 10;
  request->angle_ki = 20;
  request->speed_kp = 30;
  request->speed_ki = 40;
  request->current_kp = 50;
  request->current_ki = 60;

  manager_->writePidToRomCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_FALSE(response->error_message.empty())
    << "Expected non-empty error_message when writePIDToROM fails";
}

// =============================================================================
// 4.7: writePidToRomCallback — motor not found
// =============================================================================

TEST_F(ControlLoopManagerTest, WritePidToRomCallback_MotorNotFound)
{
  auto request = std::make_shared<motor_control_msgs::srv::WritePIDToROM::Request>();
  auto response = std::make_shared<motor_control_msgs::srv::WritePIDToROM::Response>();
  request->motor_id = 99;  // Non-existent CAN ID

  manager_->writePidToRomCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_NE(response->error_message.find("not found"), std::string::npos)
    << "Expected error_message to mention 'not found', got: "
    << response->error_message;
}

// =============================================================================
// 4.8: Position command for motor_id=3 at 45.0 deg
// =============================================================================

TEST_F(ControlLoopManagerTest, PositionCommand_Motor3_At45Degrees)
{
  double captured_position = 0.0;
  // Index 2 = 3rd motor (0-indexed)
  EXPECT_CALL(mock(2), set_position(_, _, _))
    .Times(1)
    .WillOnce(DoAll(SaveArg<0>(&captured_position), Return(true)));

  double target_radians = 45.0 * M_PI / 180.0;
  manager_->position_command_callback(2, target_radians);

  EXPECT_NEAR(captured_position, target_radians, 1e-9)
    << "Expected set_position called with " << target_radians
    << " rad (45 deg), got " << captured_position;
}

// =============================================================================
// 4.8: Position command — out-of-range motor index
// =============================================================================

TEST_F(ControlLoopManagerTest, PositionCommand_OutOfRange)
{
  // Calling with an out-of-range motor index should not crash
  EXPECT_NO_THROW(manager_->position_command_callback(99, 1.0));
}

// =============================================================================
// 4.9: Velocity command for motor_id=2 at 30.0 deg/s
// =============================================================================

TEST_F(ControlLoopManagerTest, VelocityCommand_Motor2_At30DegPerSec)
{
  double captured_velocity = 0.0;
  // Index 1 = 2nd motor (0-indexed)
  EXPECT_CALL(mock(1), set_velocity(_, _))
    .Times(1)
    .WillOnce(DoAll(SaveArg<0>(&captured_velocity), Return(true)));

  double target_rads = 30.0 * M_PI / 180.0;
  manager_->velocity_command_callback(1, target_rads);

  EXPECT_NEAR(captured_velocity, target_rads, 1e-9)
    << "Expected set_velocity called with " << target_rads
    << " rad/s (30 deg/s), got " << captured_velocity;
}

// =============================================================================
// 4.9: Velocity command — out-of-range motor index
// =============================================================================

TEST_F(ControlLoopManagerTest, VelocityCommand_OutOfRange)
{
  EXPECT_NO_THROW(manager_->velocity_command_callback(99, 1.0));
}

// =============================================================================
// 4.9: Stop command — calls stop() on correct motor
// =============================================================================

TEST_F(ControlLoopManagerTest, StopCommand_CallsStop)
{
  EXPECT_CALL(mock(0), stop())
    .Times(1)
    .WillOnce(Return(true));

  manager_->stop_command_callback(0);
}

// =============================================================================
// 4.9: Stop command — out-of-range motor index
// =============================================================================

TEST_F(ControlLoopManagerTest, StopCommand_OutOfRange)
{
  EXPECT_NO_THROW(manager_->stop_command_callback(99));
}

// =============================================================================
// 4.10: Trajectory point execution — sequential position commands
// =============================================================================

TEST_F(ControlLoopManagerTest, TrajectoryExecution_SequentialPositionCommands)
{
  // Send 3 sequential position commands to different motors
  double pos0 = 0.0, pos1 = 0.0, pos2 = 0.0;

  {
    InSequence seq;

    EXPECT_CALL(mock(0), set_position(_, _, _))
      .Times(1)
      .WillOnce(DoAll(SaveArg<0>(&pos0), Return(true)));
    EXPECT_CALL(mock(1), set_position(_, _, _))
      .Times(1)
      .WillOnce(DoAll(SaveArg<0>(&pos1), Return(true)));
    EXPECT_CALL(mock(2), set_position(_, _, _))
      .Times(1)
      .WillOnce(DoAll(SaveArg<0>(&pos2), Return(true)));
  }

  double target0 = 10.0 * M_PI / 180.0;
  double target1 = 20.0 * M_PI / 180.0;
  double target2 = 30.0 * M_PI / 180.0;

  manager_->position_command_callback(0, target0);
  manager_->position_command_callback(1, target1);
  manager_->position_command_callback(2, target2);

  EXPECT_NEAR(pos0, target0, 1e-9);
  EXPECT_NEAR(pos1, target1, 1e-9);
  EXPECT_NEAR(pos2, target2, 1e-9);
}

// =============================================================================
// 4.11: Control loop timing stability — mean period matches ±10%
// =============================================================================

TEST_F(ControlLoopManagerTest, ControlLoopTimingStability_100Iterations)
{
  // Use a higher frequency (50Hz → 20ms period) so 100 iterations takes ~2s
  manager_.reset();
  auto manager_50hz = std::make_unique<ControlLoopManager>(
    node_, mock_can_, controllers_, motor_available_, joint_names_, 50.0);

  // Track inter-message timestamps
  std::vector<std::chrono::steady_clock::time_point> timestamps;
  timestamps.reserve(110);

  auto sub = node_->create_subscription<sensor_msgs::msg::JointState>(
    "joint_states", 200,
    [&timestamps](sensor_msgs::msg::JointState::SharedPtr /*msg*/) {
      timestamps.push_back(std::chrono::steady_clock::now());
    });

  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_CALL(mock(i), get_position()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
    EXPECT_CALL(mock(i), get_velocity()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
    EXPECT_CALL(mock(i), get_torque()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
  }

  // Spin until we collect enough samples or time out (max 4s for safety)
  auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(4);
  while (timestamps.size() < 101 && std::chrono::steady_clock::now() < deadline) {
    rclcpp::spin_some(node_->get_node_base_interface());
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }

  ASSERT_GE(timestamps.size(), 50u)
    << "Not enough timer callbacks collected for timing analysis";

  // Calculate mean inter-callback period
  double total_period_ms = 0.0;
  size_t count = timestamps.size() - 1;
  for (size_t i = 1; i < timestamps.size(); ++i) {
    auto dt = std::chrono::duration_cast<std::chrono::microseconds>(
      timestamps[i] - timestamps[i - 1]);
    total_period_ms += dt.count() / 1000.0;
  }
  double mean_period_ms = total_period_ms / static_cast<double>(count);
  double expected_period_ms = 20.0;  // 50Hz → 20ms

  // Allow ±10% tolerance (test environments have jitter)
  EXPECT_NEAR(mean_period_ms, expected_period_ms, expected_period_ms * 0.10)
    << "Mean period " << mean_period_ms << "ms deviates more than 10% from expected "
    << expected_period_ms << "ms";

  manager_50hz.reset();
}

// =============================================================================
// 4.12: Zero-copy verification — code review checklist placeholder
// =============================================================================

TEST_F(ControlLoopManagerTest, ZeroCopyReview_Placeholder)
{
  // CODE REVIEW CHECKLIST — not a runtime test.
  //
  // Verify during code review that ControlLoopManager::control_loop() does NOT:
  //   [ ] Use std::copy to duplicate joint state vectors
  //   [ ] Create temporary vectors per iteration (position, velocity, effort)
  //   [ ] Allocate new JointState messages each callback (should reuse)
  //
  // Verify that it DOES:
  //   [ ] Populate the pre-allocated JointState message in-place
  //   [ ] Use direct indexing (msg.position[i] = ...) instead of push_back
  //   [ ] Reserve or pre-size vectors in constructor, not in control_loop
  //
  // This test is a compile-only check: if ControlLoopManager compiles,
  // the type structure is correct. Actual zero-copy review is manual.
  SUCCEED() << "Zero-copy review is a manual code review checklist item";
}

// =============================================================================
// Additional: joint_states message has correct structure
// =============================================================================

TEST_F(ControlLoopManagerTest, JointStates_CorrectStructure)
{
  sensor_msgs::msg::JointState::SharedPtr received_msg;
  auto sub = node_->create_subscription<sensor_msgs::msg::JointState>(
    "joint_states", 10,
    [&received_msg](sensor_msgs::msg::JointState::SharedPtr msg) {
      if (!received_msg) {
        received_msg = msg;
      }
    });

  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_CALL(mock(i), get_position()).Times(AtLeast(1)).WillRepeatedly(Return(0.1 * (i + 1)));
    EXPECT_CALL(mock(i), get_velocity()).Times(AtLeast(1)).WillRepeatedly(Return(0.2 * (i + 1)));
    EXPECT_CALL(mock(i), get_torque()).Times(AtLeast(1)).WillRepeatedly(Return(0.3 * (i + 1)));
  }

  // Spin until we get at least one message
  auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!received_msg && std::chrono::steady_clock::now() < deadline) {
    rclcpp::spin_some(node_->get_node_base_interface());
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  ASSERT_NE(received_msg, nullptr) << "No joint_states message received within 2s";

  // Verify joint count
  EXPECT_EQ(received_msg->name.size(), NUM_MOTORS);
  EXPECT_EQ(received_msg->position.size(), NUM_MOTORS);
  EXPECT_EQ(received_msg->velocity.size(), NUM_MOTORS);
  EXPECT_EQ(received_msg->effort.size(), NUM_MOTORS);

  // Verify joint names match
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_EQ(received_msg->name[i], joint_names_[i]);
  }
}

// =============================================================================
// Additional: control loop skips unavailable motors
// =============================================================================

TEST_F(ControlLoopManagerTest, ControlLoop_SkipsUnavailableMotors)
{
  // Mark motor 1 (index 1) as unavailable
  motor_available_[1].store(false);

  sensor_msgs::msg::JointState::SharedPtr received_msg;
  auto sub = node_->create_subscription<sensor_msgs::msg::JointState>(
    "joint_states", 10,
    [&received_msg](sensor_msgs::msg::JointState::SharedPtr msg) {
      if (!received_msg) {
        received_msg = msg;
      }
    });

  // Only expect calls on available motors (0 and 2)
  EXPECT_CALL(mock(0), get_position()).Times(AtLeast(1)).WillRepeatedly(Return(1.0));
  EXPECT_CALL(mock(0), get_velocity()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
  EXPECT_CALL(mock(0), get_torque()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));

  // Motor 1 should NOT be polled (unavailable)
  EXPECT_CALL(mock(1), get_position()).Times(0);
  EXPECT_CALL(mock(1), get_velocity()).Times(0);
  EXPECT_CALL(mock(1), get_torque()).Times(0);

  EXPECT_CALL(mock(2), get_position()).Times(AtLeast(1)).WillRepeatedly(Return(2.0));
  EXPECT_CALL(mock(2), get_velocity()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));
  EXPECT_CALL(mock(2), get_torque()).Times(AtLeast(1)).WillRepeatedly(Return(0.0));

  auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!received_msg && std::chrono::steady_clock::now() < deadline) {
    rclcpp::spin_some(node_->get_node_base_interface());
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  ASSERT_NE(received_msg, nullptr) << "No joint_states message received";
}

// =============================================================================
// Additional: position command on unavailable motor is rejected
// =============================================================================

TEST_F(ControlLoopManagerTest, PositionCommand_UnavailableMotor)
{
  motor_available_[0].store(false);

  // set_position should NOT be called on an unavailable motor
  EXPECT_CALL(mock(0), set_position(_, _, _)).Times(0);

  manager_->position_command_callback(0, 1.0);
}

// =============================================================================
// Additional: velocity command on unavailable motor is rejected
// =============================================================================

TEST_F(ControlLoopManagerTest, VelocityCommand_UnavailableMotor)
{
  motor_available_[1].store(false);

  EXPECT_CALL(mock(1), set_velocity(_, _)).Times(0);

  manager_->velocity_command_callback(1, 1.0);
}

// =============================================================================
// Additional: stop command on unavailable motor is handled gracefully
// =============================================================================

TEST_F(ControlLoopManagerTest, StopCommand_UnavailableMotor)
{
  motor_available_[2].store(false);

  EXPECT_CALL(mock(2), stop()).Times(0);

  manager_->stop_command_callback(2);
}

// =============================================================================
// Main
// =============================================================================

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
