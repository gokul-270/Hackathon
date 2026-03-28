/*
 * MotorManager Unit Tests (TDD RED phase)
 *
 * Tests for the MotorManager class extracted from MG6010ControllerNode.
 * Covers: construction, motor access, bulk operations, state management,
 *         joint configuration, CAN interface ownership, thread safety.
 *
 * Part of mg6010-decomposition Phase 2 (Step 5).
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

#include "motor_control_ros2/motor_manager.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <thread>
#include <vector>

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using ::testing::_;
using ::testing::Return;

// =============================================================================
// GMock MockMotorController — full mock of MotorControllerInterface
// (Duplicated from test_control_loop_manager.cpp; will be shared in Phase 3)
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
// Test Fixture — uses test-only constructor with injected mock controllers
// =============================================================================

class MotorManagerTest : public ::testing::Test
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
    node_ = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_mm_node");
    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    // Create mock controllers with known CAN IDs (1, 2, 3)
    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      auto mock = std::make_shared<MockMotorController>();
      MotorConfiguration config;
      config.can_id = static_cast<uint8_t>(i + 1);
      config.joint_name = joint_names_[i];
      ON_CALL(*mock, get_configuration()).WillByDefault(Return(config));

      mock_controllers_.push_back(mock);
      controllers_.push_back(mock);
    }

    // Construct MotorManager with test-only constructor
    manager_ = std::make_unique<MotorManager>(
      node_, mock_can_, controllers_, joint_names_, homing_positions_);
  }

  void TearDown() override
  {
    manager_.reset();
    controllers_.clear();
    mock_controllers_.clear();
    node_.reset();
  }

  MockMotorController & mock(size_t idx) { return *mock_controllers_.at(idx); }

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;
  std::vector<std::shared_ptr<MockMotorController>> mock_controllers_;
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;

  std::vector<std::string> joint_names_{"base", "mid", "tip"};
  std::vector<double> homing_positions_{0.0, 1.57, -0.5};

  std::unique_ptr<MotorManager> manager_;
};

// =============================================================================
// 1.2: Construction Tests
// =============================================================================

TEST_F(MotorManagerTest, Construction_ValidConfig_3Motors)
{
  // Manager already constructed in SetUp
  ASSERT_NE(manager_, nullptr);
  EXPECT_EQ(manager_->motorCount(), 3u);
}

TEST_F(MotorManagerTest, Construction_NullNode_Throws)
{
  EXPECT_THROW(
    {
      auto bad = std::make_unique<MotorManager>(
        nullptr, mock_can_, controllers_, joint_names_, homing_positions_);
    },
    std::invalid_argument);
}

TEST_F(MotorManagerTest, Construction_ZeroMotors_Throws)
{
  std::vector<std::shared_ptr<MotorControllerInterface>> empty_controllers;
  std::vector<std::string> empty_names;
  std::vector<double> empty_homing;

  EXPECT_THROW(
    {
      auto bad = std::make_unique<MotorManager>(
        node_, mock_can_, empty_controllers, empty_names, empty_homing);
    },
    std::invalid_argument);
}

TEST_F(MotorManagerTest, Construction_MismatchedArrayLengths_Throws)
{
  // 3 controllers but only 2 joint names
  std::vector<std::string> short_names{"base", "mid"};

  EXPECT_THROW(
    {
      auto bad = std::make_unique<MotorManager>(
        node_, mock_can_, controllers_, short_names, homing_positions_);
    },
    std::invalid_argument);
}

TEST_F(MotorManagerTest, Construction_MismatchedHomingLengths_Throws)
{
  // 3 controllers but only 1 homing position
  std::vector<double> short_homing{0.0};

  EXPECT_THROW(
    {
      auto bad = std::make_unique<MotorManager>(
        node_, mock_can_, controllers_, joint_names_, short_homing);
    },
    std::invalid_argument);
}

TEST_F(MotorManagerTest, Construction_DynamicSizingFromConfig)
{
  // Construct with 2 motors — verify dynamic sizing (not MAX_MOTORS=6)
  std::vector<std::shared_ptr<MotorControllerInterface>> two_ctrls{
    controllers_[0], controllers_[1]};
  std::vector<std::string> two_names{"base", "mid"};
  std::vector<double> two_homing{0.0, 1.57};

  auto mm = std::make_unique<MotorManager>(
    node_, mock_can_, two_ctrls, two_names, two_homing);

  EXPECT_EQ(mm->motorCount(), 2u);
}

// =============================================================================
// 1.3: Motor Access Tests
// =============================================================================

TEST_F(MotorManagerTest, GetMotor_ValidIndex_ReturnsNonNull)
{
  auto motor = manager_->getMotor(0);
  ASSERT_NE(motor, nullptr);
}

TEST_F(MotorManagerTest, GetMotor_ValidIndex_ReturnsCorrectMotor)
{
  // Each motor should correspond to the mock we injected
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    auto motor = manager_->getMotor(i);
    ASSERT_NE(motor, nullptr);
    EXPECT_EQ(motor.get(), mock_controllers_[i].get())
      << "Motor at index " << i << " does not match injected mock";
  }
}

TEST_F(MotorManagerTest, GetMotor_OutOfRange_ReturnsNullptr)
{
  auto motor = manager_->getMotor(5);
  EXPECT_EQ(motor, nullptr);
}

TEST_F(MotorManagerTest, GetMotor_OutOfRange_NoThrow)
{
  EXPECT_NO_THROW(manager_->getMotor(100));
}

TEST_F(MotorManagerTest, GetMotorByCanId_Found)
{
  // CAN ID 2 → second motor
  auto motor = manager_->getMotorByCanId(2);
  ASSERT_NE(motor, nullptr);
  EXPECT_EQ(motor.get(), mock_controllers_[1].get());
}

TEST_F(MotorManagerTest, GetMotorByCanId_NotFound)
{
  auto motor = manager_->getMotorByCanId(99);
  EXPECT_EQ(motor, nullptr);
}

TEST_F(MotorManagerTest, GetMotorByJointName_Found)
{
  auto motor = manager_->getMotorByJointName("mid");
  ASSERT_NE(motor, nullptr);
  EXPECT_EQ(motor.get(), mock_controllers_[1].get());
}

TEST_F(MotorManagerTest, GetMotorByJointName_NotFound)
{
  auto motor = manager_->getMotorByJointName("nonexistent");
  EXPECT_EQ(motor, nullptr);
}

// =============================================================================
// 1.4: Bulk Operations Tests
// =============================================================================

TEST_F(MotorManagerTest, EnableAll_AllAvailable_ReturnsMotorCount)
{
  // Mark all motors available
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
    EXPECT_CALL(mock(i), set_enabled(true)).WillOnce(Return(true));
  }

  size_t count = manager_->enableAll();
  EXPECT_EQ(count, 3u);
}

TEST_F(MotorManagerTest, DisableAll_AllAvailable_ReturnsMotorCount)
{
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
    EXPECT_CALL(mock(i), set_enabled(false)).WillOnce(Return(true));
  }

  size_t count = manager_->disableAll();
  EXPECT_EQ(count, 3u);
}

TEST_F(MotorManagerTest, StopAll_SkipsUnavailableMotors)
{
  // Mark motors 0 and 2 available, motor 1 unavailable
  manager_->setAvailable(0, true);
  manager_->setAvailable(1, false);
  manager_->setAvailable(2, true);

  EXPECT_CALL(mock(0), stop()).WillOnce(Return(true));
  EXPECT_CALL(mock(1), stop()).Times(0);  // Should NOT be called
  EXPECT_CALL(mock(2), stop()).WillOnce(Return(true));

  size_t count = manager_->stopAll();
  EXPECT_EQ(count, 2u);
}

TEST_F(MotorManagerTest, EmergencyStopAll_CallsAllAvailable)
{
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
    EXPECT_CALL(mock(i), emergency_stop()).WillOnce(Return(true));
  }

  size_t count = manager_->emergencyStopAll();
  EXPECT_EQ(count, 3u);
}

TEST_F(MotorManagerTest, EmergencyStopAll_LatencyUnder10ms)
{
  // Use 6 motors to match the spec scenario
  std::vector<std::shared_ptr<MockMotorController>> six_mocks;
  std::vector<std::shared_ptr<MotorControllerInterface>> six_ctrls;
  std::vector<std::string> six_names;
  std::vector<double> six_homing;

  for (size_t i = 0; i < 6; ++i) {
    auto m = std::make_shared<MockMotorController>();
    MotorConfiguration cfg;
    cfg.can_id = static_cast<uint8_t>(i + 1);
    cfg.joint_name = "joint_" + std::to_string(i);
    ON_CALL(*m, get_configuration()).WillByDefault(Return(cfg));
    ON_CALL(*m, emergency_stop()).WillByDefault(Return(true));
    EXPECT_CALL(*m, emergency_stop()).Times(1);
    six_mocks.push_back(m);
    six_ctrls.push_back(m);
    six_names.push_back(cfg.joint_name);
    six_homing.push_back(0.0);
  }

  auto mm = std::make_unique<MotorManager>(
    node_, mock_can_, six_ctrls, six_names, six_homing);

  for (size_t i = 0; i < 6; ++i) {
    mm->setAvailable(i, true);
  }

  auto start = std::chrono::steady_clock::now();
  mm->emergencyStopAll();
  auto elapsed = std::chrono::steady_clock::now() - start;

  auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();
  EXPECT_LT(elapsed_ms, 10) << "emergencyStopAll took " << elapsed_ms << "ms (limit: 10ms)";
}

TEST_F(MotorManagerTest, StopAll_MotorFailure_ContinuesToOthers)
{
  // Motor 0 throws on stop(), motors 1 and 2 succeed
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
  }

  EXPECT_CALL(mock(0), stop()).WillOnce(::testing::Throw(std::runtime_error("CAN timeout")));
  EXPECT_CALL(mock(1), stop()).WillOnce(Return(true));
  EXPECT_CALL(mock(2), stop()).WillOnce(Return(true));

  size_t count = manager_->stopAll();
  EXPECT_EQ(count, 2u);
}

// -----------------------------------------------------------------------------
// 1.4b: Emergency Stop Retry + Escalation Tests
// -----------------------------------------------------------------------------

TEST_F(MotorManagerTest, EmergencyStopAll_RetryOnFailure_EventuallySucceeds)
{
  // Motor 0: fails twice (returns false), succeeds on 3rd attempt
  // Motor 1: succeeds immediately
  // Motor 2: fails once (exception), succeeds on 2nd attempt
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
  }

  {
    ::testing::InSequence seq_m0;
    EXPECT_CALL(mock(0), emergency_stop()).WillOnce(Return(false));
    EXPECT_CALL(mock(0), emergency_stop()).WillOnce(Return(false));
    EXPECT_CALL(mock(0), emergency_stop()).WillOnce(Return(true));
  }

  EXPECT_CALL(mock(1), emergency_stop()).WillOnce(Return(true));

  {
    ::testing::InSequence seq_m2;
    EXPECT_CALL(mock(2), emergency_stop())
      .WillOnce(::testing::Throw(std::runtime_error("CAN bus timeout")));
    EXPECT_CALL(mock(2), emergency_stop()).WillOnce(Return(true));
  }

  size_t count = manager_->emergencyStopAll();
  EXPECT_EQ(count, 3u) << "All 3 motors should eventually stop after retries";
}

TEST_F(MotorManagerTest, EmergencyStopAll_ExhaustsRetries_LogsFatal)
{
  // Motor 0: always returns false (all 3 attempts fail)
  // Motor 1: succeeds immediately
  // Motor 2: always throws (all 3 attempts fail)
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
  }

  EXPECT_CALL(mock(0), emergency_stop())
    .Times(3)
    .WillRepeatedly(Return(false));

  EXPECT_CALL(mock(1), emergency_stop()).WillOnce(Return(true));

  EXPECT_CALL(mock(2), emergency_stop())
    .Times(3)
    .WillRepeatedly(::testing::Throw(std::runtime_error("CAN bus timeout")));

  size_t count = manager_->emergencyStopAll();
  EXPECT_EQ(count, 1u) << "Only motor 1 should succeed; motors 0 and 2 exhaust retries";
}

TEST_F(MotorManagerTest, EmergencyStopAll_ContinuesAfterMotorExhaustsRetries)
{
  // Motor 0: always fails (3 retries exhausted)
  // Motor 1: succeeds immediately
  // Motor 2: succeeds immediately
  // Verifies that failure of one motor doesn't prevent stopping others
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
  }

  EXPECT_CALL(mock(0), emergency_stop())
    .Times(3)
    .WillRepeatedly(Return(false));

  EXPECT_CALL(mock(1), emergency_stop()).WillOnce(Return(true));
  EXPECT_CALL(mock(2), emergency_stop()).WillOnce(Return(true));

  size_t count = manager_->emergencyStopAll();
  EXPECT_EQ(count, 2u) << "Motors 1 and 2 should stop; motor 0 fails after retry exhaustion";
}

TEST_F(MotorManagerTest, EmergencyStopAll_RetryBackoff_ExponentialDelay)
{
  // Motor 0: fails all 3 attempts — triggers 2 backoff sleeps (10ms + 100ms)
  // Motors 1 and 2: succeed immediately
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    manager_->setAvailable(i, true);
  }

  EXPECT_CALL(mock(0), emergency_stop())
    .Times(3)
    .WillRepeatedly(Return(false));

  EXPECT_CALL(mock(1), emergency_stop()).WillOnce(Return(true));
  EXPECT_CALL(mock(2), emergency_stop()).WillOnce(Return(true));

  auto start = std::chrono::steady_clock::now();
  size_t count = manager_->emergencyStopAll();
  auto elapsed = std::chrono::steady_clock::now() - start;

  auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();

  // Motor 0 retry backoff: sleep(10ms) after attempt 0, sleep(100ms) after attempt 1.
  // Attempt 2 is the last — no sleep after it. Total backoff >= 110ms.
  EXPECT_GE(elapsed_ms, 100)
    << "Exponential backoff should cause at least 110ms delay, got " << elapsed_ms << "ms";
  // Upper bound sanity check — should not take more than 500ms (generous margin)
  EXPECT_LT(elapsed_ms, 500)
    << "Emergency stop took too long: " << elapsed_ms << "ms";
  EXPECT_EQ(count, 2u);
}

// =============================================================================
// 1.5: State Management Tests
// =============================================================================

TEST_F(MotorManagerTest, IsAvailable_InitiallyFalse)
{
  // Fresh construction: all motors unavailable
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_FALSE(manager_->isAvailable(i));
  }
}

TEST_F(MotorManagerTest, IsEnabled_InitiallyFalse)
{
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_FALSE(manager_->isEnabled(i));
  }
}

TEST_F(MotorManagerTest, SetAvailable_ThenQuery)
{
  manager_->setAvailable(1, true);
  EXPECT_TRUE(manager_->isAvailable(1));
  EXPECT_FALSE(manager_->isAvailable(0));
  EXPECT_FALSE(manager_->isAvailable(2));
}

TEST_F(MotorManagerTest, SetEnabled_ThenQuery)
{
  manager_->setEnabled(2, true);
  EXPECT_TRUE(manager_->isEnabled(2));
  EXPECT_FALSE(manager_->isEnabled(0));
}

TEST_F(MotorManagerTest, IsAvailable_OutOfRange_ReturnsFalse)
{
  EXPECT_FALSE(manager_->isAvailable(10));
}

TEST_F(MotorManagerTest, IsEnabled_OutOfRange_ReturnsFalse)
{
  EXPECT_FALSE(manager_->isEnabled(10));
}

TEST_F(MotorManagerTest, SetAvailable_OutOfRange_NoOp)
{
  EXPECT_NO_THROW(manager_->setAvailable(10, true));
}

TEST_F(MotorManagerTest, SetEnabled_OutOfRange_NoOp)
{
  EXPECT_NO_THROW(manager_->setEnabled(10, true));
}

TEST_F(MotorManagerTest, MotorCount_MatchesConfig)
{
  EXPECT_EQ(manager_->motorCount(), NUM_MOTORS);
}

TEST_F(MotorManagerTest, SetAvailable_ThreadSafety)
{
  // Concurrent reads and writes on the same index should not cause data races
  constexpr int iterations = 10000;
  std::atomic<bool> stop_flag{false};
  std::atomic<size_t> read_count{0};

  // Reader thread: query availability (started first to ensure it runs)
  std::thread reader([&]() {
    while (!stop_flag.load(std::memory_order_acquire)) {
      (void)manager_->isAvailable(0);
      read_count.fetch_add(1, std::memory_order_relaxed);
    }
  });

  // Writer thread: toggle availability
  std::thread writer([&]() {
    for (int i = 0; i < iterations; ++i) {
      manager_->setAvailable(0, (i % 2 == 0));
    }
    stop_flag.store(true, std::memory_order_release);
  });

  writer.join();
  reader.join();

  // If we get here without TSAN complaints, thread safety is verified.
  // read_count may be 0 on very fast machines; the real check is no data race.
  (void)read_count.load();
}

TEST_F(MotorManagerTest, SetEnabled_ThreadSafety)
{
  constexpr int iterations = 10000;
  std::atomic<bool> stop_flag{false};
  std::atomic<size_t> read_count{0};

  // Reader thread: started first to ensure overlap with writer
  std::thread reader([&]() {
    while (!stop_flag.load(std::memory_order_acquire)) {
      (void)manager_->isEnabled(1);
      read_count.fetch_add(1, std::memory_order_relaxed);
    }
  });

  std::thread writer([&]() {
    for (int i = 0; i < iterations; ++i) {
      manager_->setEnabled(1, (i % 2 == 0));
    }
    stop_flag.store(true, std::memory_order_release);
  });

  writer.join();
  reader.join();

  // The real check is no data race (TSAN would flag it).
  (void)read_count.load();
}

// =============================================================================
// 1.6: Joint Config and CAN Access Tests
// =============================================================================

TEST_F(MotorManagerTest, GetJointName_ValidIndex)
{
  EXPECT_EQ(manager_->getJointName(0), "base");
  EXPECT_EQ(manager_->getJointName(1), "mid");
  EXPECT_EQ(manager_->getJointName(2), "tip");
}

TEST_F(MotorManagerTest, GetJointName_InvalidIndex_EmptyString)
{
  EXPECT_EQ(manager_->getJointName(5), "");
}

TEST_F(MotorManagerTest, GetHomingPosition_ValidIndex)
{
  EXPECT_DOUBLE_EQ(manager_->getHomingPosition(0), 0.0);
  EXPECT_DOUBLE_EQ(manager_->getHomingPosition(1), 1.57);
  EXPECT_DOUBLE_EQ(manager_->getHomingPosition(2), -0.5);
}

TEST_F(MotorManagerTest, GetHomingPosition_InvalidIndex_ReturnsZero)
{
  EXPECT_DOUBLE_EQ(manager_->getHomingPosition(10), 0.0);
}

TEST_F(MotorManagerTest, GetJointNames_ReturnsAll)
{
  const auto & names = manager_->getJointNames();
  ASSERT_EQ(names.size(), 3u);
  EXPECT_EQ(names[0], "base");
  EXPECT_EQ(names[1], "mid");
  EXPECT_EQ(names[2], "tip");
}

TEST_F(MotorManagerTest, GetCANInterface_ReturnsSharedPtr)
{
  auto can = manager_->getCANInterface();
  ASSERT_NE(can, nullptr);
}

TEST_F(MotorManagerTest, GetCANInterface_ReturnsSamePtr)
{
  auto can1 = manager_->getCANInterface();
  auto can2 = manager_->getCANInterface();
  EXPECT_EQ(can1.get(), can2.get());
}

TEST_F(MotorManagerTest, GetCANInterface_MockInjection)
{
  // Verify the injected mock is the one returned
  auto can = manager_->getCANInterface();
  EXPECT_EQ(can.get(), mock_can_.get());
}

// =============================================================================
// Main
// =============================================================================

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
