/*
 * Motor Absence Detection Tests
 *
 * Unit tests for the MotorAbsenceState logic (motor-cpu-burn-fix tasks 4.1-4.6).
 * Tests the pure absence/backoff logic without requiring a ROS2 node.
 */

#include <gtest/gtest.h>
#include "motor_control_ros2/motor_absence.hpp"

using namespace motor_control_ros2;
using namespace std::chrono_literals;

// =============================================================================
// Fixture with default config
// =============================================================================

class MotorAbsenceTest : public ::testing::Test
{
protected:
  MotorAbsenceConfig cfg;
  MotorAbsenceState state;

  void SetUp() override
  {
    cfg.failure_threshold = 5;
    cfg.initial_backoff_ms = 1000;
    cfg.max_backoff_ms = 30000;
    cfg.backoff_multiplier = 2.0;
    state = MotorAbsenceState{};
  }
};

// =============================================================================
// Task 4.1: Motor marked absent after N consecutive failures
// =============================================================================

TEST_F(MotorAbsenceTest, MarkedAbsentAfterThresholdFailures)
{
  auto now = std::chrono::steady_clock::now();

  // Fail (threshold - 1) times — should NOT be absent yet
  for (int i = 0; i < cfg.failure_threshold - 1; ++i) {
    bool became_absent = absence_record_failure(state, cfg, now);
    EXPECT_FALSE(became_absent);
    EXPECT_FALSE(state.is_absent)
      << "Motor should not be absent after " << (i + 1) << " failures";
  }

  EXPECT_EQ(state.consecutive_failures, cfg.failure_threshold - 1);

  // One more failure → absent
  bool became_absent = absence_record_failure(state, cfg, now);
  EXPECT_TRUE(became_absent) << "Motor should become absent at threshold";
  EXPECT_TRUE(state.is_absent);
  EXPECT_EQ(state.consecutive_failures, cfg.failure_threshold);
}

// =============================================================================
// Task 4.2: Transient failures — success resets counter
// =============================================================================

TEST_F(MotorAbsenceTest, TransientFailuresResetOnSuccess)
{
  auto now = std::chrono::steady_clock::now();

  // Fail 3 times (below threshold of 5)
  for (int i = 0; i < 3; ++i) {
    absence_record_failure(state, cfg, now);
  }
  EXPECT_EQ(state.consecutive_failures, 3);
  EXPECT_FALSE(state.is_absent);

  // One success resets everything
  bool recovered = absence_record_success(state, cfg);
  EXPECT_FALSE(recovered) << "Was not absent, so no recovery";
  EXPECT_EQ(state.consecutive_failures, 0);
  EXPECT_FALSE(state.is_absent);

  // Need full threshold again to become absent
  for (int i = 0; i < cfg.failure_threshold - 1; ++i) {
    absence_record_failure(state, cfg, now);
  }
  EXPECT_FALSE(state.is_absent) << "Counter was reset — threshold not reached again";
}

// =============================================================================
// Task 4.3: Exponential backoff intervals (1s, 2s, 4s, ..., cap at 30s)
// =============================================================================

TEST_F(MotorAbsenceTest, ExponentialBackoffIntervals)
{
  auto now = std::chrono::steady_clock::now();

  // Drive to absent state
  for (int i = 0; i < cfg.failure_threshold; ++i) {
    absence_record_failure(state, cfg, now);
  }
  ASSERT_TRUE(state.is_absent);

  // Initial backoff should be 1000ms
  EXPECT_EQ(state.current_backoff.count(), 1000);
  EXPECT_EQ(state.next_probe_time, now + 1000ms);

  // Simulate failed probes and check backoff doubles each time
  std::vector<int> expected_backoffs = {2000, 4000, 8000, 16000, 30000, 30000};
  for (int expected_ms : expected_backoffs) {
    // Advance time to probe window
    now = state.next_probe_time;
    EXPECT_TRUE(absence_should_probe(state, now));

    // Probe fails
    absence_record_failure(state, cfg, now);

    EXPECT_EQ(state.current_backoff.count(), expected_ms)
      << "Backoff should be " << expected_ms << "ms";
    EXPECT_EQ(state.next_probe_time, now + std::chrono::milliseconds(expected_ms));
    EXPECT_TRUE(state.is_absent);
  }
}

// =============================================================================
// Task 4.4: Absent motor restored on successful re-probe, backoff resets
// =============================================================================

TEST_F(MotorAbsenceTest, RestoredOnSuccessfulReProbe)
{
  auto now = std::chrono::steady_clock::now();

  // Drive to absent state
  for (int i = 0; i < cfg.failure_threshold; ++i) {
    absence_record_failure(state, cfg, now);
  }
  ASSERT_TRUE(state.is_absent);

  // Fail a couple of probes to grow backoff
  now = state.next_probe_time;
  absence_record_failure(state, cfg, now);  // backoff → 2000
  now = state.next_probe_time;
  absence_record_failure(state, cfg, now);  // backoff → 4000
  EXPECT_EQ(state.current_backoff.count(), 4000);

  // Now a successful probe
  bool recovered = absence_record_success(state, cfg);
  EXPECT_TRUE(recovered) << "Motor should be marked as recovered";
  EXPECT_FALSE(state.is_absent);
  EXPECT_EQ(state.consecutive_failures, 0);
  // Backoff resets to initial
  EXPECT_EQ(state.current_backoff.count(), cfg.initial_backoff_ms);
}

// =============================================================================
// Task 4.5: ~/reset_motors service clears absence state
// =============================================================================

TEST_F(MotorAbsenceTest, ResetClearsAbsenceState)
{
  auto now = std::chrono::steady_clock::now();

  // Drive to absent state with grown backoff
  for (int i = 0; i < cfg.failure_threshold; ++i) {
    absence_record_failure(state, cfg, now);
  }
  now = state.next_probe_time;
  absence_record_failure(state, cfg, now);  // backoff → 2000
  ASSERT_TRUE(state.is_absent);
  ASSERT_EQ(state.current_backoff.count(), 2000);

  // Reset clears everything
  absence_reset(state, cfg);
  EXPECT_FALSE(state.is_absent);
  EXPECT_EQ(state.consecutive_failures, 0);
  EXPECT_EQ(state.current_backoff.count(), cfg.initial_backoff_ms);
}

// =============================================================================
// Task 4.6: Re-probes use max_retries=1 (logic check — the node passes 1,
// protocol layer was verified in task 3.1)
// =============================================================================

TEST_F(MotorAbsenceTest, ShouldProbeOnlyWhenAbsentAndTimeReached)
{
  auto now = std::chrono::steady_clock::now();

  // Not absent — should never probe
  EXPECT_FALSE(absence_should_probe(state, now));

  // Drive to absent
  for (int i = 0; i < cfg.failure_threshold; ++i) {
    absence_record_failure(state, cfg, now);
  }
  ASSERT_TRUE(state.is_absent);

  // Before probe time — should not probe
  EXPECT_FALSE(absence_should_probe(state, now))
    << "Should not probe before next_probe_time";

  // At probe time — should probe
  EXPECT_TRUE(absence_should_probe(state, state.next_probe_time))
    << "Should probe at next_probe_time";

  // After probe time — should still probe
  EXPECT_TRUE(absence_should_probe(state, state.next_probe_time + 1ms))
    << "Should probe after next_probe_time";
}

// =============================================================================
// Task 5.1: Diagnostics — absent_motor_count via absence_count_absent()
// =============================================================================

TEST_F(MotorAbsenceTest, CountAbsentReturnsCorrectCount)
{
  constexpr size_t N = 4;
  MotorAbsenceState states[N] = {};
  auto now = std::chrono::steady_clock::now();

  // Initially none absent
  EXPECT_EQ(absence_count_absent(states, N), 0u);

  // Mark motor 0 and motor 2 as absent
  for (int i = 0; i < cfg.failure_threshold; ++i) {
    absence_record_failure(states[0], cfg, now);
    absence_record_failure(states[2], cfg, now);
  }
  ASSERT_TRUE(states[0].is_absent);
  ASSERT_FALSE(states[1].is_absent);
  ASSERT_TRUE(states[2].is_absent);
  ASSERT_FALSE(states[3].is_absent);

  EXPECT_EQ(absence_count_absent(states, N), 2u);

  // Recover one motor — count drops
  absence_record_success(states[0], cfg);
  EXPECT_EQ(absence_count_absent(states, N), 1u);
}

// =============================================================================
// Task 5.1: Diagnostics — consecutive_failures exposed in state struct
// =============================================================================

TEST_F(MotorAbsenceTest, ConsecutiveFailuresTrackableForDiagnostics)
{
  auto now = std::chrono::steady_clock::now();

  // Record 3 failures (below threshold)
  for (int i = 0; i < 3; ++i) {
    absence_record_failure(state, cfg, now);
  }
  EXPECT_EQ(state.consecutive_failures, 3)
    << "consecutive_failures should be readable for diagnostics reporting";

  // After going absent, failures still track
  for (int i = 3; i < cfg.failure_threshold; ++i) {
    absence_record_failure(state, cfg, now);
  }
  EXPECT_EQ(state.consecutive_failures, cfg.failure_threshold);

  // After recovery, failures reset
  absence_record_success(state, cfg);
  EXPECT_EQ(state.consecutive_failures, 0);
}

// =============================================================================
// Edge case: custom threshold via parameter
// =============================================================================

TEST_F(MotorAbsenceTest, CustomThresholdRespected)
{
  cfg.failure_threshold = 10;
  auto now = std::chrono::steady_clock::now();

  for (int i = 0; i < 9; ++i) {
    absence_record_failure(state, cfg, now);
  }
  EXPECT_FALSE(state.is_absent) << "Threshold is 10, only 9 failures";

  absence_record_failure(state, cfg, now);
  EXPECT_TRUE(state.is_absent) << "Should be absent at 10 failures";
}
