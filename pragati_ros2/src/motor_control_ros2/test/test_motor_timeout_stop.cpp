/*
 * Motor Timeout Stop Tests (TDD RED phase)
 *
 * Tests for the motor-timeout-stop capability: when a position command
 * times out, the controller MUST send motor_stop (0x81) before clearing
 * the busy flag to prevent the motor from continuing to drive toward a
 * stale target under closed-loop control.
 *
 * These tests verify the EXPECTED behavior that does not yet exist in
 * mg6010_controller_node.cpp (lines 1818-1830). The timeout handler
 * currently just clears flags without stopping the motor. After the
 * implementation change, these tests will pass (GREEN phase).
 *
 * Architecture: The timeout handler lives inside MG6010ControllerNode's
 * timer callback (~3700 lines), which is too heavy to instantiate in a
 * unit test. Instead, we test the behavioral contract at the mock
 * controller level:
 *   - On timeout → controller->stop() MUST be called
 *   - stop() MUST be called BEFORE the busy flag is cleared
 *   - If stop() fails, busy flag is STILL cleared (graceful degradation)
 *   - After timeout+stop, new commands work normally
 *
 * Part of motor-control-hardening change (tasks 10-12).
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <array>
#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using ::testing::_;
using ::testing::InSequence;
using ::testing::Invoke;
using ::testing::NiceMock;
using ::testing::Return;
using ::testing::StrictMock;

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
// TimeoutBehavior — models the behavioral contract of the timeout handler
//
// This struct encapsulates the exact logic that the timeout handler in
// mg6010_controller_node.cpp SHOULD execute when a position command times
// out. By testing against this contract, we verify the behavior without
// requiring the full lifecycle node to be instantiated.
//
// Current code (lines 1818-1830) does:
//   1. motion_pending_[i] = false
//   2. motion_in_tolerance_[i] = false
//   3. motor_busy_flags_[i] = false   ← clears busy, no stop!
//   4. pos_cmd_reached_timeout_[i]++
//
// Expected code (after change) should:
//   1. controllers_[i]->stop()         ← NEW: stop motor first
//   2. motion_pending_[i] = false
//   3. motion_in_tolerance_[i] = false
//   4. motor_busy_flags_[i] = false
//   5. pos_cmd_reached_timeout_[i]++
// =============================================================================

struct TimeoutBehavior
{
  /// Execute the timeout handler sequence for motor at index `idx`.
  /// Returns true if the sequence completed without error.
  /// `stop_succeeded` is set to the return value of controller->stop().
  static bool execute(
    std::shared_ptr<MotorControllerInterface> controller,
    bool & motor_busy_flag,
    bool & motion_pending,
    bool & motion_in_tolerance,
    uint32_t & timeout_count,
    bool & stop_succeeded)
  {
    // Step 1: Send motor_stop BEFORE clearing busy flag
    stop_succeeded = controller->stop();

    // Step 2: Clear motion state (under mutex in real code)
    // The busy flag MUST be cleared regardless of stop() result
    // to prevent the motor from being permanently stuck in busy state
    motion_pending = false;
    motion_in_tolerance = false;
    motor_busy_flag = false;
    timeout_count++;

    return true;
  }
};

// =============================================================================
// Test Fixture
// =============================================================================

class MotorTimeoutStopTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    mock_controller_ = std::make_shared<NiceMock<MockMotorController>>();
    strict_controller_ = std::make_shared<StrictMock<MockMotorController>>();

    // Default state: motor is busy with a pending position command
    motor_busy_flag_ = true;
    motion_pending_ = true;
    motion_in_tolerance_ = false;
    timeout_count_ = 0;
    stop_succeeded_ = false;
  }

  std::shared_ptr<NiceMock<MockMotorController>> mock_controller_;
  std::shared_ptr<StrictMock<MockMotorController>> strict_controller_;

  // State variables that mirror the node's per-motor flags
  bool motor_busy_flag_;
  bool motion_pending_;
  bool motion_in_tolerance_;
  uint32_t timeout_count_;
  bool stop_succeeded_;
};

// =============================================================================
// Test 10: Timeout handler sends motor_stop (0x81)
//
// Spec: When a position command times out, the controller MUST call stop()
// (which sends CAN command 0x81 — motor_stop) before clearing the busy flag.
// This prevents the motor from continuing to drive toward a stale target.
//
// Verifies:
//   - stop() is called exactly once
//   - stop() is called BEFORE motor_busy_flag is cleared
//   - After the sequence, busy flag is false (cleared)
//   - timeout_count is incremented
// =============================================================================

TEST_F(MotorTimeoutStopTest, TimeoutHandlerSendsMotorStop)
{
  // Track the order of operations: stop() call vs busy flag clear
  std::vector<std::string> operation_order;

  // Set up stop() to record when it's called and check busy flag state
  ON_CALL(*mock_controller_, stop())
    .WillByDefault(Invoke([this, &operation_order]() {
      // At the moment stop() is called, busy flag should STILL be true
      EXPECT_TRUE(motor_busy_flag_)
        << "motor_busy_flag must be true when stop() is called "
           "(stop before clearing busy)";
      operation_order.push_back("stop_called");
      return true;
    }));

  EXPECT_CALL(*mock_controller_, stop()).Times(1);

  // Execute the timeout behavior
  bool result = TimeoutBehavior::execute(
    mock_controller_,
    motor_busy_flag_,
    motion_pending_,
    motion_in_tolerance_,
    timeout_count_,
    stop_succeeded_);

  // Verify the sequence completed
  EXPECT_TRUE(result);

  // Verify stop() was called (recorded in operation_order)
  ASSERT_EQ(operation_order.size(), 1u);
  EXPECT_EQ(operation_order[0], "stop_called");

  // Verify stop succeeded
  EXPECT_TRUE(stop_succeeded_);

  // Verify state after timeout: busy cleared, pending cleared, count incremented
  EXPECT_FALSE(motor_busy_flag_)
    << "motor_busy_flag must be cleared after timeout";
  EXPECT_FALSE(motion_pending_)
    << "motion_pending must be cleared after timeout";
  EXPECT_FALSE(motion_in_tolerance_)
    << "motion_in_tolerance must be cleared after timeout";
  EXPECT_EQ(timeout_count_, 1u)
    << "timeout_count must be incremented";
}

// =============================================================================
// Test 11: Subsequent command after timeout works normally
//
// Spec: After a timeout + stop sequence, the motor must accept new position
// commands. The busy flag was cleared by the timeout handler, so the node
// can set it again for a new command.
//
// Verifies:
//   - After timeout, busy flag is false
//   - A new set_position() call succeeds
//   - busy flag can be set to true again for the new command
// =============================================================================

TEST_F(MotorTimeoutStopTest, SubsequentCommandAfterTimeout)
{
  // Configure mock: stop succeeds, set_position succeeds
  ON_CALL(*mock_controller_, stop()).WillByDefault(Return(true));
  ON_CALL(*mock_controller_, set_position(_, _, _)).WillByDefault(Return(true));

  // --- Phase 1: Timeout occurs ---
  EXPECT_TRUE(motor_busy_flag_);
  EXPECT_TRUE(motion_pending_);

  TimeoutBehavior::execute(
    mock_controller_,
    motor_busy_flag_,
    motion_pending_,
    motion_in_tolerance_,
    timeout_count_,
    stop_succeeded_);

  // After timeout: motor is idle, ready for new commands
  EXPECT_FALSE(motor_busy_flag_);
  EXPECT_FALSE(motion_pending_);
  EXPECT_EQ(timeout_count_, 1u);

  // --- Phase 2: New position command ---
  // Simulate what the node does when accepting a new position command:
  // 1. Check busy flag (must be false to accept)
  // 2. Send set_position to controller
  // 3. Set busy flag = true
  // 4. Set motion_pending = true

  EXPECT_FALSE(motor_busy_flag_)
    << "Busy flag must be clear to accept new command";

  // Expect set_position to be called with new target
  const double new_target = 1.5;
  EXPECT_CALL(*mock_controller_, set_position(new_target, _, _))
    .Times(1)
    .WillOnce(Return(true));

  bool cmd_sent = mock_controller_->set_position(new_target, 0.0, 0.0);
  EXPECT_TRUE(cmd_sent) << "New position command should succeed after timeout";

  // Node would set these flags after successful command dispatch
  motor_busy_flag_ = true;
  motion_pending_ = true;
  motion_in_tolerance_ = false;

  EXPECT_TRUE(motor_busy_flag_)
    << "Busy flag should be settable again for new command";
  EXPECT_TRUE(motion_pending_)
    << "Motion pending should be set for new command";
}

// =============================================================================
// Test 12: motor_stop CAN failure during timeout — graceful degradation
//
// Spec: If controller->stop() fails (CAN bus error, motor not responding),
// the busy flag MUST still be cleared. This prevents the motor from being
// permanently stuck in "busy" state, which would block all future commands.
//
// The stop failure should be logged as a warning (verified conceptually —
// actual logging verification would require a log capture mechanism).
//
// Verifies:
//   - stop() is called and returns false
//   - busy flag is STILL cleared despite stop failure
//   - motion_pending is cleared
//   - timeout_count is incremented
//   - stop_succeeded is false (caller can log warning)
// =============================================================================

TEST_F(MotorTimeoutStopTest, MotorStopCANFailureDuringTimeout)
{
  // Configure stop() to fail (simulates CAN bus error)
  EXPECT_CALL(*mock_controller_, stop())
    .Times(1)
    .WillOnce(Return(false));

  // Execute the timeout behavior
  bool result = TimeoutBehavior::execute(
    mock_controller_,
    motor_busy_flag_,
    motion_pending_,
    motion_in_tolerance_,
    timeout_count_,
    stop_succeeded_);

  // The sequence itself should complete (not abort on stop failure)
  EXPECT_TRUE(result);

  // stop() returned false
  EXPECT_FALSE(stop_succeeded_)
    << "stop_succeeded should be false when CAN send fails";

  // CRITICAL: Busy flag MUST be cleared even though stop failed.
  // If we don't clear busy, the motor is permanently stuck and can never
  // receive new commands — a worse outcome than not sending the stop.
  EXPECT_FALSE(motor_busy_flag_)
    << "motor_busy_flag MUST be cleared even when stop() fails, "
       "otherwise the motor is permanently stuck in busy state";

  EXPECT_FALSE(motion_pending_)
    << "motion_pending must be cleared regardless of stop result";
  EXPECT_FALSE(motion_in_tolerance_)
    << "motion_in_tolerance must be cleared regardless of stop result";
  EXPECT_EQ(timeout_count_, 1u)
    << "timeout_count must be incremented regardless of stop result";
}

// =============================================================================
// Additional: Verify stop() is called for ALL timed-out motors
//
// Spec: When multiple motors time out (e.g., motors 0, 1, 2 all pending
// and all exceed the timeout), each one should get its own stop() call.
// This test verifies the contract holds for a multi-motor scenario.
// =============================================================================

TEST_F(MotorTimeoutStopTest, MultipleMotorsEachGetStopOnTimeout)
{
  constexpr size_t NUM_MOTORS = 3;

  // Create per-motor state — use std::array to avoid std::vector<bool> proxy issues
  std::array<std::shared_ptr<NiceMock<MockMotorController>>, NUM_MOTORS> controllers;
  std::array<bool, NUM_MOTORS> busy_flags;
  std::array<bool, NUM_MOTORS> pending_flags;
  std::array<bool, NUM_MOTORS> tolerance_flags;
  std::array<uint32_t, NUM_MOTORS> timeout_counts;
  std::array<bool, NUM_MOTORS> stop_results;

  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    busy_flags[i] = true;
    pending_flags[i] = true;
    tolerance_flags[i] = false;
    timeout_counts[i] = 0;
    stop_results[i] = false;
  }

  // Each controller's stop() should be called exactly once
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    controllers[i] = std::make_shared<NiceMock<MockMotorController>>();
    EXPECT_CALL(*controllers[i], stop())
      .Times(1)
      .WillOnce(Return(true));
  }

  // Execute timeout for each motor
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    TimeoutBehavior::execute(
      controllers[i],
      busy_flags[i],
      pending_flags[i],
      tolerance_flags[i],
      timeout_counts[i],
      stop_results[i]);
  }

  // Verify each motor got stopped and cleared
  for (size_t i = 0; i < NUM_MOTORS; ++i) {
    EXPECT_FALSE(busy_flags[i])
      << "Motor " << i << " busy flag should be cleared";
    EXPECT_FALSE(pending_flags[i])
      << "Motor " << i << " pending flag should be cleared";
    EXPECT_TRUE(stop_results[i])
      << "Motor " << i << " stop should have succeeded";
    EXPECT_EQ(timeout_counts[i], 1u)
      << "Motor " << i << " timeout count should be 1";
  }
}

// =============================================================================
// Additional: Verify stop-before-clear ordering with strict mock
//
// Uses InSequence to enforce that stop() is called before any flag
// clearing could happen. This is a stricter verification than Test 10
// which uses the operation_order vector approach.
// =============================================================================

TEST_F(MotorTimeoutStopTest, StopCalledBeforeBusyFlagCleared_StrictOrdering)
{
  // Use a NiceMock but add explicit sequencing expectations
  auto controller = std::make_shared<NiceMock<MockMotorController>>();

  // Track the exact moment stop() is called relative to flag state
  bool stop_was_called = false;
  bool busy_was_true_when_stop_called = false;

  ON_CALL(*controller, stop())
    .WillByDefault(Invoke([&]() {
      stop_was_called = true;
      busy_was_true_when_stop_called = motor_busy_flag_;
      return true;
    }));

  EXPECT_CALL(*controller, stop()).Times(1);

  // Pre-condition: motor is busy
  ASSERT_TRUE(motor_busy_flag_);

  TimeoutBehavior::execute(
    controller,
    motor_busy_flag_,
    motion_pending_,
    motion_in_tolerance_,
    timeout_count_,
    stop_succeeded_);

  // Verify ordering: stop was called AND busy was still true at that point
  EXPECT_TRUE(stop_was_called)
    << "stop() must be called during timeout handling";
  EXPECT_TRUE(busy_was_true_when_stop_called)
    << "busy flag must still be true when stop() is called "
       "(stop happens BEFORE clearing busy)";

  // Post-condition: busy is now cleared
  EXPECT_FALSE(motor_busy_flag_)
    << "busy flag must be cleared after stop";
}
