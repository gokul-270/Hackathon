/*
 * MotorTestSuite Unit Tests (TDD RED phase)
 *
 * Tests for the MotorTestSuite class extracted from MG6010ControllerNode.
 * The class under test does NOT exist yet — these tests define its expected
 * public API and behavior. All tests should FAIL to compile or link until
 * the implementation is written (GREEN phase).
 *
 * Covers: construction, legacy test methods, diagnostic service callbacks,
 *         motor availability, dispatch routing, and boundary conditions.
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <std_srvs/srv/trigger.hpp>

#include "motor_control_ros2/motor_test_suite.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

#include "motor_control_msgs/srv/read_motor_state.hpp"
#include "motor_control_msgs/srv/read_encoder.hpp"
#include "motor_control_msgs/srv/read_motor_angles.hpp"
#include "motor_control_msgs/srv/read_motor_limits.hpp"
#include "motor_control_msgs/srv/clear_motor_errors.hpp"
#include "motor_control_msgs/srv/read_pid.hpp"

#include <array>
#include <atomic>
#include <memory>
#include <string>
#include <vector>

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::InSequence;
using ::testing::Return;
using ::testing::SetArgReferee;

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
// Test Fixture
// =============================================================================

class MotorTestSuiteTest : public ::testing::Test
{
protected:
  static constexpr size_t NUM_MOTORS = 2;

  void SetUp() override
  {
    rclcpp::init(0, nullptr);

    node_ = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_mts_node");
    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    // Create mock controllers with known CAN IDs
    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      auto mock = std::make_shared<MockMotorController>();
      MotorConfiguration config;
      config.can_id = static_cast<uint8_t>(i + 1);  // CAN IDs: 1, 2
      config.joint_name = "joint_" + std::to_string(i);

      // Default: get_configuration returns the config with correct can_id
      ON_CALL(*mock, get_configuration()).WillByDefault(Return(config));

      mock_controllers_.push_back(mock);
      controllers_.push_back(mock);
      joint_names_.push_back(config.joint_name);
      motor_available_[i].store(true);
    }

    suite_ = std::make_unique<MotorTestSuite>(
      node_, mock_can_, controllers_, motor_available_, joint_names_);
  }

  void TearDown() override
  {
    suite_.reset();
    controllers_.clear();
    mock_controllers_.clear();
    node_.reset();
    rclcpp::shutdown();
  }

  // Helper: get raw mock pointer for setting expectations
  MockMotorController & mock(size_t idx) { return *mock_controllers_.at(idx); }

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;

  // Mock controllers (typed access for EXPECT_CALL)
  std::vector<std::shared_ptr<MockMotorController>> mock_controllers_;

  // Passed by reference to MotorTestSuite
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;
  std::array<std::atomic<bool>, MAX_MOTORS> motor_available_{};
  std::vector<std::string> joint_names_;

  std::unique_ptr<MotorTestSuite> suite_;
};

// =============================================================================
// 1. Construction_ValidArgs
// =============================================================================

TEST_F(MotorTestSuiteTest, Construction_ValidArgs)
{
  // Suite was already constructed in SetUp — verify it didn't throw
  ASSERT_NE(suite_, nullptr);
}

// =============================================================================
// 2. Construction_NullNode_Throws
// =============================================================================

TEST_F(MotorTestSuiteTest, Construction_NullNode_Throws)
{
  // Tear down the existing suite so we can test construction independently
  suite_.reset();

  EXPECT_THROW(
    {
      auto bad_suite = std::make_unique<MotorTestSuite>(
        nullptr, mock_can_, controllers_, motor_available_, joint_names_);
    },
    std::invalid_argument);
}

// =============================================================================
// 3. TestStatus_SendsCorrectQuery
// =============================================================================

TEST_F(MotorTestSuiteTest, TestStatus_SendsCorrectQuery)
{
  MotorStatus status;
  status.hardware_connected = true;
  status.motor_enabled = false;
  status.temperature = 35.0;

  EXPECT_CALL(mock(0), get_status())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(status));

  suite_->test_status(0);
}

// =============================================================================
// 4. TestEnable_EnableDisableCycle
// =============================================================================

TEST_F(MotorTestSuiteTest, TestEnable_EnableDisableCycle)
{
  {
    InSequence seq;
    EXPECT_CALL(mock(0), set_enabled(true))
      .Times(1)
      .WillOnce(Return(true));
    EXPECT_CALL(mock(0), set_enabled(false))
      .Times(1)
      .WillOnce(Return(true));
  }

  suite_->test_enable(0);
}

// =============================================================================
// 5. TestPosition_SendsPositionCommand
// =============================================================================

TEST_F(MotorTestSuiteTest, TestPosition_SendsPositionCommand)
{
  {
    InSequence seq;
    EXPECT_CALL(mock(0), set_enabled(true))
      .Times(1)
      .WillOnce(Return(true));
    EXPECT_CALL(mock(0), set_position(45.0, 0.0, 0.0))
      .Times(1)
      .WillOnce(Return(true));
  }

  // get_position may be called multiple times during position monitoring
  EXPECT_CALL(mock(0), get_position())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(45.0));

  EXPECT_CALL(mock(0), set_enabled(false))
    .Times(1)
    .WillOnce(Return(true));

  suite_->test_position(0, 45.0);
}

// =============================================================================
// 6. TestVelocity_SendsVelocityCommand
// =============================================================================

TEST_F(MotorTestSuiteTest, TestVelocity_SendsVelocityCommand)
{
  {
    InSequence seq;
    EXPECT_CALL(mock(0), set_enabled(true))
      .Times(1)
      .WillOnce(Return(true));
    EXPECT_CALL(mock(0), set_velocity(30.0, 0.0))
      .Times(1)
      .WillOnce(Return(true));
  }

  // Velocity may be read during monitoring
  EXPECT_CALL(mock(0), get_velocity())
    .Times(AtLeast(0))
    .WillRepeatedly(Return(30.0));

  // Stop command: velocity=0
  EXPECT_CALL(mock(0), set_velocity(0.0, 0.0))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  EXPECT_CALL(mock(0), set_enabled(false))
    .Times(1)
    .WillOnce(Return(true));

  suite_->test_velocity(0, 30.0);
}

// =============================================================================
// 7. TestFullSequence_RunsAllSteps
// =============================================================================

TEST_F(MotorTestSuiteTest, TestFullSequence_RunsAllSteps)
{
  MotorStatus status;
  status.hardware_connected = true;
  status.motor_enabled = false;

  EXPECT_CALL(mock(0), get_status())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(status));

  EXPECT_CALL(mock(0), set_enabled(true))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  EXPECT_CALL(mock(0), set_position(45.0, _, _))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  EXPECT_CALL(mock(0), get_position())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(45.0));

  EXPECT_CALL(mock(0), set_enabled(false))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  suite_->test_full_sequence(0, 45.0);
}

// =============================================================================
// 8. ReadMotorStateCallback_ReturnsState
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadMotorStateCallback_ReturnsState)
{
  FullMotorState state;
  state.temperature_c = 42.5;
  state.voltage_v = 24.0;
  state.torque_current_a = 1.5;
  state.speed_dps = 100.0;
  state.encoder_position = 4096;
  state.multi_turn_deg = 720.0;
  state.single_turn_deg = 180.0;
  state.phase_current_a = 0.5;
  state.phase_current_b = 0.6;
  state.phase_current_c = 0.7;
  state.error_flags = 0;
  state.valid = true;

  EXPECT_CALL(mock(0), readFullState())
    .Times(1)
    .WillOnce(Return(state));

  auto request =
    std::make_shared<motor_control_msgs::srv::ReadMotorState::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadMotorState::Response>();
  request->motor_id = 1;  // CAN ID of first mock controller

  suite_->readMotorStateCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
  EXPECT_FLOAT_EQ(response->temperature_c, 42.5f);
  EXPECT_FLOAT_EQ(response->voltage_v, 24.0f);
  EXPECT_FLOAT_EQ(response->torque_current_a, 1.5f);
  EXPECT_FLOAT_EQ(response->speed_dps, 100.0f);
  EXPECT_EQ(response->encoder_position, 4096);
  EXPECT_DOUBLE_EQ(response->multi_turn_deg, 720.0);
  EXPECT_DOUBLE_EQ(response->single_turn_deg, 180.0);
  EXPECT_FLOAT_EQ(response->phase_a, 0.5f);
  EXPECT_FLOAT_EQ(response->phase_b, 0.6f);
  EXPECT_FLOAT_EQ(response->phase_c, 0.7f);
  EXPECT_EQ(response->error_flags, 0);
}

// =============================================================================
// 9. ReadEncoderCallback_ReturnsEncoderValues
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadEncoderCallback_ReturnsEncoderValues)
{
  EXPECT_CALL(mock(0), readEncoder(_, _, _))
    .Times(1)
    .WillOnce(DoAll(
      SetArgReferee<0>(static_cast<uint16_t>(1234)),
      SetArgReferee<1>(static_cast<uint16_t>(5678)),
      SetArgReferee<2>(static_cast<uint16_t>(100)),
      Return(true)));

  auto request =
    std::make_shared<motor_control_msgs::srv::ReadEncoder::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadEncoder::Response>();
  request->motor_id = 1;

  suite_->readEncoderCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
  EXPECT_EQ(response->original_value, 1234);
  EXPECT_EQ(response->raw_value, 5678);
  EXPECT_EQ(response->offset, 100);
}

// =============================================================================
// 10. ReadMotorAnglesCallback_ReturnsAngles
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadMotorAnglesCallback_ReturnsAngles)
{
  EXPECT_CALL(mock(0), readMultiTurnAngle(_))
    .Times(1)
    .WillOnce(DoAll(
      SetArgReferee<0>(3.14159),
      Return(true)));

  EXPECT_CALL(mock(0), readSingleTurnAngle(_))
    .Times(1)
    .WillOnce(DoAll(
      SetArgReferee<0>(1.5708),
      Return(true)));

  auto request =
    std::make_shared<motor_control_msgs::srv::ReadMotorAngles::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadMotorAngles::Response>();
  request->motor_id = 1;

  suite_->readMotorAnglesCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
  EXPECT_DOUBLE_EQ(response->multi_turn_angle, 3.14159);
  EXPECT_DOUBLE_EQ(response->single_turn_angle, 1.5708);
}

// =============================================================================
// 11. ReadMotorLimitsCallback_ReturnsLimits
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadMotorLimitsCallback_ReturnsLimits)
{
  EXPECT_CALL(mock(0), readMaxTorqueCurrent(_))
    .Times(1)
    .WillOnce(DoAll(
      SetArgReferee<0>(static_cast<uint16_t>(1500)),
      Return(true)));

  EXPECT_CALL(mock(0), readAcceleration(_))
    .Times(1)
    .WillOnce(DoAll(
      SetArgReferee<0>(5.0),
      Return(true)));

  auto request =
    std::make_shared<motor_control_msgs::srv::ReadMotorLimits::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadMotorLimits::Response>();
  request->motor_id = 1;

  suite_->readMotorLimitsCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
  EXPECT_EQ(response->max_torque_ratio, 1500);
  EXPECT_DOUBLE_EQ(response->acceleration, 5.0);
}

// =============================================================================
// 12. ClearMotorErrorsCallback_ClearsAndConfirms
// =============================================================================

TEST_F(MotorTestSuiteTest, ClearMotorErrorsCallback_ClearsAndConfirms)
{
  EXPECT_CALL(mock(0), clear_errors())
    .Times(1)
    .WillOnce(Return(true));

  EXPECT_CALL(mock(0), readErrors(_))
    .Times(1)
    .WillOnce(DoAll(
      SetArgReferee<0>(static_cast<uint32_t>(0)),
      Return(true)));

  auto request =
    std::make_shared<motor_control_msgs::srv::ClearMotorErrors::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ClearMotorErrors::Response>();
  request->motor_id = 1;

  suite_->clearMotorErrorsCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
  EXPECT_EQ(response->error_flags_after, 0);
}

// =============================================================================
// 13. ReadPidCallback_ReturnsPidGains
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadPidCallback_ReturnsPidGains)
{
  PIDParams params;
  params.angle_kp = 10;
  params.angle_ki = 20;
  params.speed_kp = 30;
  params.speed_ki = 40;
  params.current_kp = 50;
  params.current_ki = 60;

  EXPECT_CALL(mock(0), readPID())
    .Times(1)
    .WillOnce(Return(std::optional<PIDParams>(params)));

  auto request =
    std::make_shared<motor_control_msgs::srv::ReadPID::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadPID::Response>();
  request->motor_id = 1;

  suite_->readPidCallback(request, response);

  EXPECT_TRUE(response->success);
  EXPECT_EQ(response->error_message, "");
  EXPECT_EQ(response->angle_kp, 10);
  EXPECT_EQ(response->angle_ki, 20);
  EXPECT_EQ(response->speed_kp, 30);
  EXPECT_EQ(response->speed_ki, 40);
  EXPECT_EQ(response->current_kp, 50);
  EXPECT_EQ(response->current_ki, 60);
}

// =============================================================================
// 14. MotorAvailabilityCallback_ReturnsAvailability
// =============================================================================

TEST_F(MotorTestSuiteTest, MotorAvailabilityCallback_ReturnsAvailability)
{
  // Motor 0: available, Motor 1: unavailable
  motor_available_[0].store(true);
  motor_available_[1].store(false);

  auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
  auto response = std::make_shared<std_srvs::srv::Trigger::Response>();

  suite_->motor_availability_callback(request, response);

  EXPECT_TRUE(response->success);
  // Message should indicate 1 out of 2 available
  EXPECT_NE(response->message.find("1/2"), std::string::npos)
    << "Expected message to contain '1/2 available', got: " << response->message;
  EXPECT_NE(response->message.find("available"), std::string::npos)
    << "Expected message to contain 'available', got: " << response->message;
}

// =============================================================================
// 15. DispatchTest_RoutesToCorrectMethod — "status"
// =============================================================================

TEST_F(MotorTestSuiteTest, DispatchTest_RoutesToStatus)
{
  MotorStatus status;
  status.hardware_connected = true;

  EXPECT_CALL(mock(0), get_status())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(status));

  suite_->dispatch_test("status", 0.0);
}

// =============================================================================
// 15b. DispatchTest_RoutesToCorrectMethod — "enable"
// =============================================================================

TEST_F(MotorTestSuiteTest, DispatchTest_RoutesToEnable)
{
  EXPECT_CALL(mock(0), set_enabled(true))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));
  EXPECT_CALL(mock(0), set_enabled(false))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  suite_->dispatch_test("enable", 0.0);
}

// =============================================================================
// 15c. DispatchTest_RoutesToCorrectMethod — "position"
// =============================================================================

TEST_F(MotorTestSuiteTest, DispatchTest_RoutesToPosition)
{
  EXPECT_CALL(mock(0), set_enabled(true))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));
  EXPECT_CALL(mock(0), set_position(90.0, _, _))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));
  EXPECT_CALL(mock(0), get_position())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(90.0));
  EXPECT_CALL(mock(0), set_enabled(false))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  suite_->dispatch_test("position", 90.0);
}

// =============================================================================
// 15d. DispatchTest_RoutesToCorrectMethod — "velocity"
// =============================================================================

TEST_F(MotorTestSuiteTest, DispatchTest_RoutesToVelocity)
{
  EXPECT_CALL(mock(0), set_enabled(true))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));
  EXPECT_CALL(mock(0), set_velocity(_, _))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));
  EXPECT_CALL(mock(0), get_velocity())
    .Times(AtLeast(0))
    .WillRepeatedly(Return(0.0));
  EXPECT_CALL(mock(0), set_enabled(false))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  suite_->dispatch_test("velocity", 30.0);
}

// =============================================================================
// 15e. DispatchTest_RoutesToCorrectMethod — "full"
// =============================================================================

TEST_F(MotorTestSuiteTest, DispatchTest_RoutesToFull)
{
  MotorStatus status;
  status.hardware_connected = true;

  EXPECT_CALL(mock(0), get_status())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(status));
  EXPECT_CALL(mock(0), set_enabled(true))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));
  EXPECT_CALL(mock(0), set_position(60.0, _, _))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));
  EXPECT_CALL(mock(0), get_position())
    .Times(AtLeast(1))
    .WillRepeatedly(Return(60.0));
  EXPECT_CALL(mock(0), set_enabled(false))
    .Times(AtLeast(1))
    .WillRepeatedly(Return(true));

  suite_->dispatch_test("full", 60.0);
}

// =============================================================================
// 16. DiagnosticCallback_MotorNotFound
// =============================================================================

TEST_F(MotorTestSuiteTest, DiagnosticCallback_MotorNotFound)
{
  auto request =
    std::make_shared<motor_control_msgs::srv::ReadPID::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadPID::Response>();
  request->motor_id = 99;  // Non-existent CAN ID

  suite_->readPidCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_NE(response->error_message.find("not found"), std::string::npos)
    << "Expected error_message to mention 'not found', got: "
    << response->error_message;
}

// =============================================================================
// 16b. DiagnosticCallback_MotorNotFound — readMotorState
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadMotorStateCallback_MotorNotFound)
{
  auto request =
    std::make_shared<motor_control_msgs::srv::ReadMotorState::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadMotorState::Response>();
  request->motor_id = 99;

  suite_->readMotorStateCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_NE(response->error_message.find("not found"), std::string::npos)
    << "Expected error_message to mention 'not found', got: "
    << response->error_message;
}

// =============================================================================
// 17. TestStatus_OutOfRange — boundary check
// =============================================================================

TEST_F(MotorTestSuiteTest, TestStatus_OutOfRange)
{
  // Calling with an out-of-range motor index should not crash.
  // The method should handle the boundary gracefully (log error, return early).
  // No EXPECT_CALL on any mock — out-of-range index should not touch controllers.
  EXPECT_NO_THROW(suite_->test_status(99));
}

// =============================================================================
// Additional boundary: TestEnable_OutOfRange
// =============================================================================

TEST_F(MotorTestSuiteTest, TestEnable_OutOfRange)
{
  EXPECT_NO_THROW(suite_->test_enable(99));
}

// =============================================================================
// Additional: ReadEncoderCallback_MotorNotFound
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadEncoderCallback_MotorNotFound)
{
  auto request =
    std::make_shared<motor_control_msgs::srv::ReadEncoder::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadEncoder::Response>();
  request->motor_id = 99;

  suite_->readEncoderCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_NE(response->error_message.find("not found"), std::string::npos)
    << "Expected error_message to mention 'not found', got: "
    << response->error_message;
}

// =============================================================================
// Additional: ClearMotorErrorsCallback_MotorNotFound
// =============================================================================

TEST_F(MotorTestSuiteTest, ClearMotorErrorsCallback_MotorNotFound)
{
  auto request =
    std::make_shared<motor_control_msgs::srv::ClearMotorErrors::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ClearMotorErrors::Response>();
  request->motor_id = 99;

  suite_->clearMotorErrorsCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_NE(response->error_message.find("not found"), std::string::npos)
    << "Expected error_message to mention 'not found', got: "
    << response->error_message;
}

// =============================================================================
// Additional: ReadPidCallback_ReadPIDFails
// =============================================================================

TEST_F(MotorTestSuiteTest, ReadPidCallback_ReadPIDFails)
{
  EXPECT_CALL(mock(0), readPID())
    .Times(1)
    .WillOnce(Return(std::nullopt));

  auto request =
    std::make_shared<motor_control_msgs::srv::ReadPID::Request>();
  auto response =
    std::make_shared<motor_control_msgs::srv::ReadPID::Response>();
  request->motor_id = 1;

  suite_->readPidCallback(request, response);

  EXPECT_FALSE(response->success);
  EXPECT_FALSE(response->error_message.empty())
    << "Expected non-empty error_message when readPID fails";
}

// =============================================================================
// Main
// =============================================================================

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
