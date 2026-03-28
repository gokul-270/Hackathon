/*
 * ShutdownHandler Unit Tests (TDD RED phase)
 *
 * Tests for the ShutdownHandler class extracted from MG6010ControllerNode.
 * Covers: construction, arm/vehicle sequences, timeouts, signal abort,
 *         result reporting, timer cancellation, standalone compilation.
 *
 * Part of mg6010-decomposition Phase 3 (Step 7).
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

#include "motor_control_ros2/shutdown_handler.hpp"
#include "motor_control_ros2/role_strategy.hpp"
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
using ::testing::AtLeast;
using ::testing::InSequence;
using ::testing::Invoke;
using ::testing::NiceMock;
using ::testing::Return;

// =============================================================================
// GMock MockMotorController — full mock of MotorControllerInterface
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
// Test Fixture — Arm configuration (3 joints: joint5, joint3, joint4)
// =============================================================================

static int g_test_counter = 0;

class ShutdownHandlerTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite() { rclcpp::init(0, nullptr); }
  static void TearDownTestSuite() { rclcpp::shutdown(); }

  void SetUp() override
  {
    std::string suffix = std::to_string(++g_test_counter);
    node_ = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_shutdown_" + suffix);

    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    // Create 3 mock controllers (arm: joint5, joint3, joint4)
    for (size_t i = 0; i < 3; ++i) {
      auto mock = std::make_shared<NiceMock<MockMotorController>>();
      ON_CALL(*mock, set_enabled(_)).WillByDefault(Return(true));
      ON_CALL(*mock, set_position(_, _, _)).WillByDefault(Return(true));
      ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
      mock_controllers_.push_back(mock);
      controllers_.push_back(mock);
    }

    arm_joint_names_ = {"joint5", "joint3", "joint4"};
    arm_homing_positions_ = {0.0, -1.57, 0.0};
    arm_packing_positions_ = {0.5, 1.0, 0.8};

    arm_strategy_ = std::make_shared<ArmRoleStrategy>();
  }

  // Helper: create MotorManager with test constructor
  std::unique_ptr<MotorManager> makeMotorManager()
  {
    return std::make_unique<MotorManager>(
      node_, mock_can_, controllers_, arm_joint_names_, arm_homing_positions_);
  }

  // Helper: create MotorManager with custom config
  std::unique_ptr<MotorManager> makeMotorManager(
    const std::vector<std::shared_ptr<MotorControllerInterface>> & ctrls,
    const std::vector<std::string> & names,
    const std::vector<double> & homing)
  {
    return std::make_unique<MotorManager>(node_, mock_can_, ctrls, names, homing);
  }

  // Helper: declare shutdown params on node with defaults
  void declareShutdownParams(
    bool enable_packing = true,
    double max_duration_s = 10.0,
    double position_tolerance = 0.02,
    double poll_interval_ms = 100.0)
  {
    node_->declare_parameter("shutdown.enable_packing", enable_packing);
    node_->declare_parameter("shutdown.max_duration_s", max_duration_s);
    node_->declare_parameter("shutdown.position_tolerance", position_tolerance);
    node_->declare_parameter("shutdown.poll_interval_ms", poll_interval_ms);
    // Packing positions needed by ShutdownHandler
    node_->declare_parameter("packing_positions", arm_packing_positions_);
  }

  // Helper: set mock to return target position immediately (within tolerance)
  void setMockAtTarget(size_t idx, double target)
  {
    ON_CALL(*mock_controllers_[idx], get_position()).WillByDefault(Return(target));
  }

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;
  std::vector<std::shared_ptr<NiceMock<MockMotorController>>> mock_controllers_;
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;
  std::vector<std::string> arm_joint_names_;
  std::vector<double> arm_homing_positions_;
  std::vector<double> arm_packing_positions_;
  std::shared_ptr<RoleStrategy> arm_strategy_;
};

// =============================================================================
// 2.1 Construction — valid inputs succeed
// =============================================================================

TEST_F(ShutdownHandlerTest, ConstructionValid)
{
  declareShutdownParams();
  auto mm = makeMotorManager();

  EXPECT_NO_THROW(
    ShutdownHandler handler(node_, *mm, arm_strategy_));
}

// =============================================================================
// 2.2 Construction — default params when none declared
// =============================================================================

TEST_F(ShutdownHandlerTest, DefaultParams)
{
  // Don't declare any shutdown.* params — handler should use defaults
  node_->declare_parameter("packing_positions", arm_packing_positions_);
  auto mm = makeMotorManager();

  // Should not throw — defaults are applied internally
  ShutdownHandler handler(node_, *mm, arm_strategy_);

  // Verify defaults by executing with motors already at target
  // (defaults: enable_packing=true, max_duration_s=10, tolerance=0.02, poll=100ms)
  // Set all motors at their target positions
  // ArmRoleStrategy sequence: J5(park=0.5), J3(home=-1.57), J4(park=0.8), J3(park=1.0)
  setMockAtTarget(0, 0.5);   // joint5 at packing
  setMockAtTarget(1, -1.57); // joint3 at homing (first pass)
  setMockAtTarget(2, 0.8);   // joint4 at packing

  auto result = handler.execute();
  // With defaults (enable_packing=true), all 4 steps attempted
  // parked_count should be >= 3 (all joints successfully parked)
  EXPECT_GE(result.parked_count, 3u);
  EXPECT_FALSE(result.deadline_exceeded);
}

// =============================================================================
// 2.3 Construction — null node throws
// =============================================================================

TEST_F(ShutdownHandlerTest, NullNodeThrows)
{
  auto mm = makeMotorManager();

  try {
    ShutdownHandler handler(nullptr, *mm, arm_strategy_);
    FAIL() << "Expected std::invalid_argument";
  } catch (const std::invalid_argument & e) {
    EXPECT_THAT(std::string(e.what()), ::testing::HasSubstr("node"));
  }
}

// =============================================================================
// 2.4 Construction — null RoleStrategy throws
// =============================================================================

TEST_F(ShutdownHandlerTest, NullRoleStrategyThrows)
{
  declareShutdownParams();
  auto mm = makeMotorManager();

  try {
    ShutdownHandler handler(node_, *mm, nullptr);
    FAIL() << "Expected std::invalid_argument";
  } catch (const std::invalid_argument & e) {
    std::string what(e.what());
    EXPECT_TRUE(
      what.find("strategy") != std::string::npos ||
      what.find("role") != std::string::npos)
      << "Exception message should mention strategy or role: " << what;
  }
}

// =============================================================================
// 2.5 Construction — zero motors throws
// =============================================================================

TEST_F(ShutdownHandlerTest, ZeroMotorThrows)
{
  declareShutdownParams();
  std::vector<std::shared_ptr<MotorControllerInterface>> empty_ctrls;
  std::vector<std::string> empty_names;
  std::vector<double> empty_homing;

  // MotorManager itself throws on zero motors — defense in depth.
  // ShutdownHandler additionally validates motor_manager.getMotorCount() == 0.
  // Either layer may throw std::invalid_argument.
  EXPECT_THROW(
    {
      auto mm = makeMotorManager(empty_ctrls, empty_names, empty_homing);
      ShutdownHandler(node_, *mm, arm_strategy_);
    },
    std::invalid_argument);
}

// =============================================================================
// 2.6 Construction — poll_interval_ms < 10 clamped to 100
// =============================================================================

TEST_F(ShutdownHandlerTest, PollIntervalClamped)
{
  declareShutdownParams(true, 10.0, 0.02, 5.0);  // poll_interval_ms = 5 (< 10)
  auto mm = makeMotorManager();

  // Should not throw — clamped to 100ms internally
  EXPECT_NO_THROW(
    ShutdownHandler handler(node_, *mm, arm_strategy_));

  // Verify clamping by timing: with 3 joints already at target, if poll was 5ms
  // the handler would be very fast. With 100ms clamped, it should take at least
  // a few ms but not be affected by tight-loop polling.
  // (The real verification is that it doesn't peg CPU)
}

// =============================================================================
// 2.7 Arm shutdown sequence — J5→J3-home→J4→J3-park
// =============================================================================

TEST_F(ShutdownHandlerTest, ArmShutdownSequence)
{
  declareShutdownParams();
  auto mm = makeMotorManager();

  // Track set_position calls in order
  std::vector<std::pair<size_t, double>> position_commands;

  // All motors start at 0.0 (NOT at their targets) so they need commanding
  // joint5 (idx 0): tracks commanded position, returns it on get_position
  std::atomic<double> j5_pos{0.0};
  ON_CALL(*mock_controllers_[0], set_position(_, _, _))
    .WillByDefault(Invoke(
      [&j5_pos, &position_commands](double pos, double, double) {
        position_commands.push_back({0, pos});
        j5_pos.store(pos);
        return true;
      }));
  ON_CALL(*mock_controllers_[0], get_position())
    .WillByDefault(Invoke([&j5_pos]() { return j5_pos.load(); }));

  // joint3 (idx 1): tracks commanded position
  std::atomic<double> j3_pos{0.0};
  ON_CALL(*mock_controllers_[1], set_position(_, _, _))
    .WillByDefault(Invoke(
      [&j3_pos, &position_commands](double pos, double, double) {
        position_commands.push_back({1, pos});
        j3_pos.store(pos);
        return true;
      }));
  ON_CALL(*mock_controllers_[1], get_position())
    .WillByDefault(Invoke([&j3_pos]() { return j3_pos.load(); }));

  // joint4 (idx 2): tracks commanded position
  std::atomic<double> j4_pos{0.0};
  ON_CALL(*mock_controllers_[2], set_position(_, _, _))
    .WillByDefault(Invoke(
      [&j4_pos, &position_commands](double pos, double, double) {
        position_commands.push_back({2, pos});
        j4_pos.store(pos);
        return true;
      }));
  ON_CALL(*mock_controllers_[2], get_position())
    .WillByDefault(Invoke([&j4_pos]() { return j4_pos.load(); }));

  ShutdownHandler handler(node_, *mm, arm_strategy_);
  auto result = handler.execute();

  // Verify sequence: J5(park=0.5), J3(home=-1.57), J4(park=0.8), J3(park=1.0)
  ASSERT_GE(position_commands.size(), 4u)
    << "Expected at least 4 set_position calls for arm sequence";

  // Command 0: J5 to packing (0.5)
  EXPECT_EQ(position_commands[0].first, 0u);  // joint5 index
  EXPECT_DOUBLE_EQ(position_commands[0].second, 0.5);

  // Command 1: J3 to homing (-1.57)
  EXPECT_EQ(position_commands[1].first, 1u);  // joint3 index
  EXPECT_DOUBLE_EQ(position_commands[1].second, -1.57);

  // Command 2: J4 to packing (0.8)
  EXPECT_EQ(position_commands[2].first, 2u);  // joint4 index
  EXPECT_DOUBLE_EQ(position_commands[2].second, 0.8);

  // Command 3: J3 to packing (1.0) — only when enable_packing=true
  EXPECT_EQ(position_commands[3].first, 1u);  // joint3 index
  EXPECT_DOUBLE_EQ(position_commands[3].second, 1.0);
}

// =============================================================================
// 2.8 Arm without packing — enable_packing=false skips J3 final park
// =============================================================================

TEST_F(ShutdownHandlerTest, ArmWithoutPacking)
{
  declareShutdownParams(false);  // enable_packing = false
  auto mm = makeMotorManager();

  std::vector<std::pair<size_t, double>> position_commands;

  // All motors start at 0.0, update position atomically on set_position
  for (size_t i = 0; i < mock_controllers_.size(); ++i) {
    auto pos = std::make_shared<std::atomic<double>>(0.0);
    ON_CALL(*mock_controllers_[i], set_position(_, _, _))
      .WillByDefault(Invoke(
        [i, pos, &position_commands](double target, double, double) {
          position_commands.push_back({i, target});
          pos->store(target);
          return true;
        }));
    ON_CALL(*mock_controllers_[i], get_position())
      .WillByDefault(Invoke([pos]() { return pos->load(); }));
  }

  ShutdownHandler handler(node_, *mm, arm_strategy_);
  auto result = handler.execute();

  // Without packing: only 3 commands (J5-park, J3-home, J4-park), NOT 4
  ASSERT_EQ(position_commands.size(), 3u)
    << "Expected exactly 3 set_position calls when enable_packing=false";

  EXPECT_EQ(position_commands[0].first, 0u);    // J5
  EXPECT_EQ(position_commands[1].first, 1u);    // J3 to homing
  EXPECT_DOUBLE_EQ(position_commands[1].second, -1.57);  // homing, not packing
  EXPECT_EQ(position_commands[2].first, 2u);    // J4
}

// =============================================================================
// 2.9 Vehicle shutdown — steering parked, drive disabled (no position cmd)
// =============================================================================

TEST_F(ShutdownHandlerTest, VehicleShutdown)
{
  // Vehicle config: 3 motors (2 steering + 1 drive)
  std::vector<std::string> vehicle_names = {
    "steering_left", "steering_right", "front_left_drive"};
  std::vector<double> vehicle_homing = {0.0, 0.0, 0.0};
  std::vector<double> vehicle_packing = {0.0, 0.0, 0.0};

  // Re-declare packing_positions for vehicle
    auto vehicle_node = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_shutdown_vehicle");
  vehicle_node->declare_parameter("shutdown.enable_packing", true);
  vehicle_node->declare_parameter("shutdown.max_duration_s", 10.0);
  vehicle_node->declare_parameter("shutdown.position_tolerance", 0.02);
  vehicle_node->declare_parameter("shutdown.poll_interval_ms", 100.0);
  vehicle_node->declare_parameter("packing_positions", vehicle_packing);

  std::vector<std::shared_ptr<NiceMock<MockMotorController>>> vehicle_mocks;
  std::vector<std::shared_ptr<MotorControllerInterface>> vehicle_ctrls;
  for (size_t i = 0; i < 3; ++i) {
    auto mock = std::make_shared<NiceMock<MockMotorController>>();
    ON_CALL(*mock, set_enabled(_)).WillByDefault(Return(true));
    ON_CALL(*mock, set_position(_, _, _)).WillByDefault(Return(true));
    ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
    vehicle_mocks.push_back(mock);
    vehicle_ctrls.push_back(mock);
  }

  auto vehicle_mm = std::make_unique<MotorManager>(
    vehicle_node, mock_can_, vehicle_ctrls, vehicle_names, vehicle_homing);
  auto vehicle_strategy = std::make_shared<VehicleRoleStrategy>();

  // Track position commands and disable calls per motor
  std::vector<size_t> position_commanded_motors;
  std::vector<size_t> disabled_motors;
  for (size_t i = 0; i < 3; ++i) {
    ON_CALL(*vehicle_mocks[i], set_position(_, _, _))
      .WillByDefault(Invoke(
        [i, &position_commanded_motors](double, double, double) {
          position_commanded_motors.push_back(i);
          return true;
        }));
    ON_CALL(*vehicle_mocks[i], set_enabled(false))
      .WillByDefault(Invoke(
        [i, &disabled_motors](bool) {
          disabled_motors.push_back(i);
          return true;
        }));
  }

  ShutdownHandler handler(vehicle_node, *vehicle_mm, vehicle_strategy);
  auto result = handler.execute();

  // Steering motors (idx 0, 1) should get position commands
  // Drive motor (idx 2) should NOT get position command
  for (size_t motor_idx : position_commanded_motors) {
    EXPECT_NE(motor_idx, 2u)
      << "Drive motor should not receive position command during vehicle shutdown";
  }

  // All motors (including drive) should be disabled
  for (size_t i = 0; i < 3; ++i) {
    bool found = std::find(disabled_motors.begin(), disabled_motors.end(), i)
      != disabled_motors.end();
    EXPECT_TRUE(found) << "Motor " << i << " should be disabled during shutdown";
  }
}

// =============================================================================
// 2.10 Per-joint timeout — 2s per joint, moves on after timeout
// =============================================================================

TEST_F(ShutdownHandlerTest, PerJointTimeout)
{
  // Use short global deadline but enough for at least one joint to timeout
  declareShutdownParams(false, 30.0, 0.02, 50.0);  // 30s global, 50ms poll
  auto mm = makeMotorManager();

  // All motors return position far from target (never reach it)
  for (auto & mock : mock_controllers_) {
    ON_CALL(*mock, get_position()).WillByDefault(Return(999.0));
  }

  ShutdownHandler handler(node_, *mm, arm_strategy_);
  auto start = std::chrono::steady_clock::now();
  auto result = handler.execute();
  auto elapsed = std::chrono::steady_clock::now() - start;

  // Each of 3 joints should take ~2s (per-joint timeout)
  // Total should be ~6s (3 joints × 2s each), not 30s (global deadline)
  auto elapsed_s = std::chrono::duration<double>(elapsed).count();
  EXPECT_GT(elapsed_s, 4.0) << "Should wait at least ~2s per joint";
  EXPECT_LT(elapsed_s, 12.0) << "Should not exceed ~2s × 3 joints + margin";

  // No joints should be parked
  EXPECT_EQ(result.parked_count, 0u);
  for (bool status : result.per_joint_status) {
    EXPECT_FALSE(status) << "Timed-out joints should be marked false";
  }
}

// =============================================================================
// 2.11 Global deadline — skip remaining joints, motors still disabled
// =============================================================================

TEST_F(ShutdownHandlerTest, GlobalDeadline)
{
  // Very short global deadline: 0.5s. With 2s per-joint timeout, only ~0 joints finish.
  declareShutdownParams(false, 0.5, 0.02, 50.0);
  auto mm = makeMotorManager();

  // Motors never reach target
  for (auto & mock : mock_controllers_) {
    ON_CALL(*mock, get_position()).WillByDefault(Return(999.0));
  }

  // Track disable calls per motor using ON_CALL (before execute)
  std::vector<size_t> disabled_motors;
  for (size_t i = 0; i < mock_controllers_.size(); ++i) {
    ON_CALL(*mock_controllers_[i], set_enabled(false))
      .WillByDefault(Invoke(
        [i, &disabled_motors](bool) {
          disabled_motors.push_back(i);
          return true;
        }));
  }

  ShutdownHandler handler(node_, *mm, arm_strategy_);
  auto start = std::chrono::steady_clock::now();
  auto result = handler.execute();
  auto elapsed = std::chrono::steady_clock::now() - start;

  // Should return within ~0.5s + small margin, NOT 6s (3 × 2s per-joint)
  auto elapsed_s = std::chrono::duration<double>(elapsed).count();
  EXPECT_LT(elapsed_s, 2.0) << "Global deadline should cut short the sequence";

  EXPECT_TRUE(result.deadline_exceeded);

  // Motors should still be disabled despite deadline
  for (size_t i = 0; i < mock_controllers_.size(); ++i) {
    bool found = std::find(disabled_motors.begin(), disabled_motors.end(), i)
      != disabled_motors.end();
    EXPECT_TRUE(found) << "Motor " << i << " should be disabled even after global deadline";
  }
}

// =============================================================================
// 2.12 Joint already at target — no position command, marked parked
// =============================================================================

TEST_F(ShutdownHandlerTest, JointAlreadyAtTarget)
{
  declareShutdownParams();
  auto mm = makeMotorManager();

  // Arm sequence: J5(park=0.5), J3(home=-1.57), J4(park=0.8), J3(park=1.0)
  // Set all motors already at their targets
  setMockAtTarget(0, 0.5);   // joint5 at packing position
  setMockAtTarget(1, -1.57); // joint3 at homing position

  // For J3's second pass (packing), we need position to change
  // But for this test, let's track set_position calls
  std::vector<size_t> commanded_motors;
  for (size_t i = 0; i < mock_controllers_.size(); ++i) {
    ON_CALL(*mock_controllers_[i], set_position(_, _, _))
      .WillByDefault(Invoke(
        [i, &commanded_motors](double, double, double) {
          commanded_motors.push_back(i);
          return true;
        }));
  }

  // joint4 also at target
  setMockAtTarget(2, 0.8);

  ShutdownHandler handler(node_, *mm, arm_strategy_);
  auto result = handler.execute();

  // Since motors are already at target, no set_position should be called
  // (or at minimum, joints that are already at target should not get commands)
  // At least joint5 (idx 0) should not get a position command since it's at 0.5
  bool j5_commanded = false;
  for (size_t m : commanded_motors) {
    if (m == 0) j5_commanded = true;
  }
  EXPECT_FALSE(j5_commanded)
    << "Joint already at target should not receive position command";

  // All joints should be marked as parked
  EXPECT_GE(result.parked_count, 3u);
}

// =============================================================================
// 2.13 Signal abort — requestAbort() causes early return
// =============================================================================

TEST_F(ShutdownHandlerTest, SignalAbort)
{
  declareShutdownParams(false, 30.0, 0.02, 100.0);
  auto mm = makeMotorManager();

  // Motors never reach target (slow shutdown)
  for (auto & mock : mock_controllers_) {
    ON_CALL(*mock, get_position()).WillByDefault(Return(999.0));
  }

  ShutdownHandler handler(node_, *mm, arm_strategy_);

  // Run execute in a separate thread
  auto future = std::async(std::launch::async, [&handler]() {
    return handler.execute();
  });

  // Wait 200ms then request abort
  std::this_thread::sleep_for(std::chrono::milliseconds(200));
  handler.requestAbort();
  handler.notifyAbort();

  // Should return within ~500ms total (200ms wait + poll interval + margin)
  auto status = future.wait_for(std::chrono::milliseconds(800));
  ASSERT_EQ(status, std::future_status::ready)
    << "execute() should return promptly after requestAbort()";

  auto result = future.get();
  // Parking should be incomplete
  EXPECT_LT(result.parked_count, 3u);
}

// =============================================================================
// 2.14 Notify abort — immediate wake from wait_for
// =============================================================================

TEST_F(ShutdownHandlerTest, NotifyAbort)
{
  declareShutdownParams(false, 30.0, 0.02, 2000.0);  // Very long poll: 2s
  auto mm = makeMotorManager();

  // Motors never reach target
  for (auto & mock : mock_controllers_) {
    ON_CALL(*mock, get_position()).WillByDefault(Return(999.0));
  }

  ShutdownHandler handler(node_, *mm, arm_strategy_);

  auto future = std::async(std::launch::async, [&handler]() {
    return handler.execute();
  });

  // Wait 100ms, then requestAbort + notifyAbort
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  handler.requestAbort();
  handler.notifyAbort();

  // If notify works, should return well before 2s poll interval
  auto status = future.wait_for(std::chrono::milliseconds(500));
  ASSERT_EQ(status, std::future_status::ready)
    << "notifyAbort() should wake execute() from wait_for immediately";
}

// =============================================================================
// 2.15 All joints parked — full success result
// =============================================================================

TEST_F(ShutdownHandlerTest, AllJointsParked)
{
  declareShutdownParams(false);  // No packing (3-step sequence)
  auto mm = makeMotorManager();

  // Motors immediately at target
  setMockAtTarget(0, 0.5);    // joint5 at packing
  setMockAtTarget(1, -1.57);  // joint3 at homing
  setMockAtTarget(2, 0.8);    // joint4 at packing

  ShutdownHandler handler(node_, *mm, arm_strategy_);
  auto result = handler.execute();

  EXPECT_EQ(result.parked_count, 3u);
  EXPECT_EQ(result.total_count, 3u);
  EXPECT_FALSE(result.deadline_exceeded);
  ASSERT_EQ(result.per_joint_status.size(), 3u);
  for (bool status : result.per_joint_status) {
    EXPECT_TRUE(status);
  }
}

// =============================================================================
// 2.16 Partial parking — some joints timeout
// =============================================================================

TEST_F(ShutdownHandlerTest, PartialParking)
{
  declareShutdownParams(false, 30.0, 0.02, 50.0);
  auto mm = makeMotorManager();

  // Joint5 (idx 0) reaches target
  setMockAtTarget(0, 0.5);

  // Joint3 (idx 1) and Joint4 (idx 2) never reach target
  ON_CALL(*mock_controllers_[1], get_position()).WillByDefault(Return(999.0));
  ON_CALL(*mock_controllers_[2], get_position()).WillByDefault(Return(999.0));

  ShutdownHandler handler(node_, *mm, arm_strategy_);
  auto result = handler.execute();

  // Only joint5 parked successfully
  EXPECT_EQ(result.parked_count, 1u);
  ASSERT_EQ(result.per_joint_status.size(), 3u);
  EXPECT_TRUE(result.per_joint_status[0]);   // joint5 OK
  EXPECT_FALSE(result.per_joint_status[1]);  // joint3 failed
  EXPECT_FALSE(result.per_joint_status[2]);  // joint4 failed
}

// =============================================================================
// 2.17 Timers cancelled before parking
// =============================================================================

TEST_F(ShutdownHandlerTest, TimersCancelledFirst)
{
  declareShutdownParams();
  auto mm = makeMotorManager();

  // Create real timers on the node
  std::vector<rclcpp::TimerBase::SharedPtr> timers;
  for (int i = 0; i < 3; ++i) {
    auto timer = node_->create_wall_timer(
      std::chrono::seconds(60), []() {});  // Long period, won't fire
    timers.push_back(timer);
  }

  // Track whether position is called (timers should be cancelled first)
  bool any_position_called = false;

  for (auto & mock : mock_controllers_) {
    ON_CALL(*mock, set_position(_, _, _))
      .WillByDefault(Invoke(
        [&any_position_called](double, double, double) {
          any_position_called = true;
          return true;
        }));
    ON_CALL(*mock, get_position()).WillByDefault(Return(0.5));  // At target
  }

  ShutdownHandler handler(node_, *mm, arm_strategy_, timers);

  auto result = handler.execute();

  // Verify all timers are cancelled
  for (const auto & timer : timers) {
    EXPECT_TRUE(timer->is_canceled())
      << "Timer should be cancelled during shutdown";
  }
}

// =============================================================================
// 2.18 Standalone compilation — no MG6010ControllerNode dependency
// =============================================================================

TEST_F(ShutdownHandlerTest, StandaloneCompilation)
{
  // This test verifies that test_shutdown_handler.cpp compiles without
  // including any mg6010_controller_node header. The test passing (or
  // failing with the expected "shutdown_handler.hpp not found") proves
  // the ShutdownHandler is independently testable.
  SUCCEED();
}

// =============================================================================
// 2.22 Vehicle shutdown sends motor_stop before motor_off (RED — will fail)
// =============================================================================

TEST_F(ShutdownHandlerTest, VehicleStopBeforeDisable)
{
  // Vehicle config: 3 motors (2 steering + 1 drive)
  std::vector<std::string> vehicle_names = {
    "steering_left", "steering_right", "front_left_drive"};
  std::vector<double> vehicle_homing = {0.0, 0.0, 0.0};
  std::vector<double> vehicle_packing = {0.0, 0.0, 0.0};

  auto vehicle_node = std::make_shared<rclcpp_lifecycle::LifecycleNode>(
    "test_shutdown_stop_before_disable");
  vehicle_node->declare_parameter("shutdown.enable_packing", true);
  vehicle_node->declare_parameter("shutdown.max_duration_s", 10.0);
  vehicle_node->declare_parameter("shutdown.position_tolerance", 0.02);
  vehicle_node->declare_parameter("shutdown.poll_interval_ms", 100.0);
  vehicle_node->declare_parameter("packing_positions", vehicle_packing);

  std::vector<std::shared_ptr<NiceMock<MockMotorController>>> vehicle_mocks;
  std::vector<std::shared_ptr<MotorControllerInterface>> vehicle_ctrls;
  for (size_t i = 0; i < 3; ++i) {
    auto mock = std::make_shared<NiceMock<MockMotorController>>();
    ON_CALL(*mock, set_enabled(_)).WillByDefault(Return(true));
    ON_CALL(*mock, set_position(_, _, _)).WillByDefault(Return(true));
    ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
    ON_CALL(*mock, stop()).WillByDefault(Return(true));
    ON_CALL(*mock, clear_errors()).WillByDefault(Return(true));
    vehicle_mocks.push_back(mock);
    vehicle_ctrls.push_back(mock);
  }

  auto vehicle_mm = std::make_unique<MotorManager>(
    vehicle_node, mock_can_, vehicle_ctrls, vehicle_names, vehicle_homing);
  auto vehicle_strategy = std::make_shared<VehicleRoleStrategy>();

  // Track call order per motor: record "stop" and "disable" events
  // Use a shared vector guarded by mutex for thread safety
  struct CallEvent {
    size_t motor_idx;
    std::string action;  // "stop" or "disable"
  };
  auto call_log = std::make_shared<std::vector<CallEvent>>();
  auto log_mutex = std::make_shared<std::mutex>();

  for (size_t i = 0; i < 3; ++i) {
    ON_CALL(*vehicle_mocks[i], stop())
      .WillByDefault(Invoke(
        [i, call_log, log_mutex]() {
          std::lock_guard<std::mutex> lock(*log_mutex);
          call_log->push_back({i, "stop"});
          return true;
        }));
    ON_CALL(*vehicle_mocks[i], set_enabled(false))
      .WillByDefault(Invoke(
        [i, call_log, log_mutex](bool) {
          std::lock_guard<std::mutex> lock(*log_mutex);
          call_log->push_back({i, "disable"});
          return true;
        }));
  }

  ShutdownHandler handler(vehicle_node, *vehicle_mm, vehicle_strategy);
  auto result = handler.execute();

  // Verify: for each motor, stop() was called BEFORE set_enabled(false)
  for (size_t motor = 0; motor < 3; ++motor) {
    int stop_order = -1;
    int disable_order = -1;
    for (size_t j = 0; j < call_log->size(); ++j) {
      const auto & evt = (*call_log)[j];
      if (evt.motor_idx == motor && evt.action == "stop" && stop_order < 0) {
        stop_order = static_cast<int>(j);
      }
      if (evt.motor_idx == motor && evt.action == "disable" && disable_order < 0) {
        disable_order = static_cast<int>(j);
      }
    }
    EXPECT_GE(stop_order, 0)
      << "Motor " << motor << ": stop() was never called";
    EXPECT_GE(disable_order, 0)
      << "Motor " << motor << ": set_enabled(false) was never called";
    if (stop_order >= 0 && disable_order >= 0) {
      EXPECT_LT(stop_order, disable_order)
        << "Motor " << motor << ": stop() must be called BEFORE set_enabled(false)";
    }
  }
}

// =============================================================================
// 2.23 Clear errors called after all motors disabled (RED — will fail)
// =============================================================================

TEST_F(ShutdownHandlerTest, ClearErrorsAfterDisable)
{
  // Vehicle config: 3 motors (2 steering + 1 drive)
  std::vector<std::string> vehicle_names = {
    "steering_left", "steering_right", "front_left_drive"};
  std::vector<double> vehicle_homing = {0.0, 0.0, 0.0};
  std::vector<double> vehicle_packing = {0.0, 0.0, 0.0};

  auto vehicle_node = std::make_shared<rclcpp_lifecycle::LifecycleNode>(
    "test_shutdown_clear_errors");
  vehicle_node->declare_parameter("shutdown.enable_packing", true);
  vehicle_node->declare_parameter("shutdown.max_duration_s", 10.0);
  vehicle_node->declare_parameter("shutdown.position_tolerance", 0.02);
  vehicle_node->declare_parameter("shutdown.poll_interval_ms", 100.0);
  vehicle_node->declare_parameter("packing_positions", vehicle_packing);

  std::vector<std::shared_ptr<NiceMock<MockMotorController>>> vehicle_mocks;
  std::vector<std::shared_ptr<MotorControllerInterface>> vehicle_ctrls;
  for (size_t i = 0; i < 3; ++i) {
    auto mock = std::make_shared<NiceMock<MockMotorController>>();
    ON_CALL(*mock, set_enabled(_)).WillByDefault(Return(true));
    ON_CALL(*mock, set_position(_, _, _)).WillByDefault(Return(true));
    ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
    ON_CALL(*mock, stop()).WillByDefault(Return(true));
    ON_CALL(*mock, clear_errors()).WillByDefault(Return(true));
    vehicle_mocks.push_back(mock);
    vehicle_ctrls.push_back(mock);
  }

  auto vehicle_mm = std::make_unique<MotorManager>(
    vehicle_node, mock_can_, vehicle_ctrls, vehicle_names, vehicle_homing);
  auto vehicle_strategy = std::make_shared<VehicleRoleStrategy>();

  // Track call order: record "disable" and "clear_errors" events
  struct CallEvent {
    size_t motor_idx;
    std::string action;
  };
  auto call_log = std::make_shared<std::vector<CallEvent>>();
  auto log_mutex = std::make_shared<std::mutex>();

  for (size_t i = 0; i < 3; ++i) {
    ON_CALL(*vehicle_mocks[i], set_enabled(false))
      .WillByDefault(Invoke(
        [i, call_log, log_mutex](bool) {
          std::lock_guard<std::mutex> lock(*log_mutex);
          call_log->push_back({i, "disable"});
          return true;
        }));
    ON_CALL(*vehicle_mocks[i], clear_errors())
      .WillByDefault(Invoke(
        [i, call_log, log_mutex]() {
          std::lock_guard<std::mutex> lock(*log_mutex);
          call_log->push_back({i, "clear_errors"});
          return true;
        }));
  }

  ShutdownHandler handler(vehicle_node, *vehicle_mm, vehicle_strategy);
  auto result = handler.execute();

  // Verify: clear_errors() was called on each motor
  for (size_t motor = 0; motor < 3; ++motor) {
    bool clear_called = false;
    for (const auto & evt : *call_log) {
      if (evt.motor_idx == motor && evt.action == "clear_errors") {
        clear_called = true;
        break;
      }
    }
    EXPECT_TRUE(clear_called)
      << "Motor " << motor << ": clear_errors() was never called";
  }

  // Verify: ALL disable calls happen BEFORE any clear_errors call
  int last_disable = -1;
  int first_clear = static_cast<int>(call_log->size());
  for (size_t j = 0; j < call_log->size(); ++j) {
    if ((*call_log)[j].action == "disable") {
      last_disable = static_cast<int>(j);
    }
    if ((*call_log)[j].action == "clear_errors" &&
        static_cast<int>(j) < first_clear) {
      first_clear = static_cast<int>(j);
    }
  }
  EXPECT_GE(last_disable, 0) << "No disable calls were recorded";
  EXPECT_LT(first_clear, static_cast<int>(call_log->size()))
    << "No clear_errors calls were recorded";
  if (last_disable >= 0 && first_clear < static_cast<int>(call_log->size())) {
    EXPECT_LT(last_disable, first_clear)
      << "All motors must be disabled BEFORE any clear_errors is called";
  }
}

// =============================================================================
// 2.24 Clear errors failure doesn't fail shutdown (RED — will fail)
// =============================================================================

TEST_F(ShutdownHandlerTest, ClearErrorsFailureDoesNotFailShutdown)
{
  // Vehicle config: 3 motors (2 steering + 1 drive)
  std::vector<std::string> vehicle_names = {
    "steering_left", "steering_right", "front_left_drive"};
  std::vector<double> vehicle_homing = {0.0, 0.0, 0.0};
  std::vector<double> vehicle_packing = {0.0, 0.0, 0.0};

  auto vehicle_node = std::make_shared<rclcpp_lifecycle::LifecycleNode>(
    "test_shutdown_clear_errors_fail");
  vehicle_node->declare_parameter("shutdown.enable_packing", true);
  vehicle_node->declare_parameter("shutdown.max_duration_s", 10.0);
  vehicle_node->declare_parameter("shutdown.position_tolerance", 0.02);
  vehicle_node->declare_parameter("shutdown.poll_interval_ms", 100.0);
  vehicle_node->declare_parameter("packing_positions", vehicle_packing);

  std::vector<std::shared_ptr<NiceMock<MockMotorController>>> vehicle_mocks;
  std::vector<std::shared_ptr<MotorControllerInterface>> vehicle_ctrls;
  for (size_t i = 0; i < 3; ++i) {
    auto mock = std::make_shared<NiceMock<MockMotorController>>();
    ON_CALL(*mock, set_enabled(_)).WillByDefault(Return(true));
    ON_CALL(*mock, set_position(_, _, _)).WillByDefault(Return(true));
    ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
    ON_CALL(*mock, stop()).WillByDefault(Return(true));
    // Default: clear_errors succeeds
    ON_CALL(*mock, clear_errors()).WillByDefault(Return(true));
    vehicle_mocks.push_back(mock);
    vehicle_ctrls.push_back(mock);
  }

  // Motor 1 (steering_right): clear_errors fails
  ON_CALL(*vehicle_mocks[1], clear_errors()).WillByDefault(Return(false));

  auto vehicle_mm = std::make_unique<MotorManager>(
    vehicle_node, mock_can_, vehicle_ctrls, vehicle_names, vehicle_homing);
  auto vehicle_strategy = std::make_shared<VehicleRoleStrategy>();

  ShutdownHandler handler(vehicle_node, *vehicle_mm, vehicle_strategy);
  auto result = handler.execute();

  // Shutdown should still report success despite clear_errors failure
  // Vehicle steering motors park at 0.0 (already at target), so all should park
  EXPECT_FALSE(result.deadline_exceeded)
    << "Shutdown should not be marked as deadline-exceeded due to clear_errors failure";

  // All steering motors should be parked (positions already at 0.0 = target)
  // The clear_errors failure should be logged as warning but not affect result
  EXPECT_GE(result.parked_count, 2u)
    << "Steering motors should be parked regardless of clear_errors failure";
}
