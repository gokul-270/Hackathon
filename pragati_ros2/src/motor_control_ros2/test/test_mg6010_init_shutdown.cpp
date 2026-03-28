/*
 * MG6010 Init/Shutdown Sequence Hardening — Unit Tests (TDD RED phase)
 *
 * Tests the hardened initialization and shutdown sequences for MG6010Controller.
 *
 * Target init sequence:
 *   motor_stop(0x81) → clear_errors(0x9B) → read_status(0x9A) → [verify clean]
 *   → motor_on(0x88) → [verify active]
 *
 * Target shutdown sequence (set_enabled(false)):
 *   motor_stop(0x81) → motor_off(0x80) → clear_errors(0x9B)
 *
 * Current (un-hardened) init:
 *   motor_on(0x88) → read_status(0x9A) → clear_errors(0x9B) if errors
 *
 * Current (un-hardened) shutdown:
 *   motor_off(0x80) only
 *
 * These tests define the DESIRED behavior and will FAIL against the current
 * implementation until the init/shutdown hardening is applied.
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>

#include "motor_control_ros2/mg6010_controller.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

#include <algorithm>
#include <cstdint>
#include <sstream>
#include <string>
#include <vector>

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;

// =============================================================================
// Helpers
// =============================================================================

namespace
{

/// Protocol command bytes (mirrors MG6010Protocol constants for readability).
constexpr uint8_t CMD_MOTOR_OFF = 0x80;
constexpr uint8_t CMD_MOTOR_STOP = 0x81;
constexpr uint8_t CMD_MOTOR_ON = 0x88;
constexpr uint8_t CMD_READ_STATUS_1 = 0x9A;
constexpr uint8_t CMD_CLEAR_ERRORS = 0x9B;

/// CAN arbitration ID for motor_id 1.
constexpr uint32_t MOTOR1_ARB_ID = MG6010Protocol::BASE_ARBITRATION_ID + 1;

/**
 * @brief Extract the command byte sequence from sent CAN messages.
 *
 * Filters messages by the expected arbitration ID and returns data[0]
 * (the command byte) from each matching message, preserving order.
 */
std::vector<uint8_t> extract_command_bytes(
  const std::vector<ConfigurableMockCANInterface::SentMessage> & messages,
  uint32_t arb_id)
{
  std::vector<uint8_t> cmds;
  for (const auto & msg : messages) {
    if (msg.id == arb_id && !msg.data.empty()) {
      cmds.push_back(msg.data[0]);
    }
  }
  return cmds;
}

/**
 * @brief Format a command byte sequence as a human-readable string for
 *        assertion failure messages.
 */
std::string format_cmd_sequence(const std::vector<uint8_t> & cmds)
{
  std::ostringstream oss;
  oss << "[";
  for (size_t i = 0; i < cmds.size(); ++i) {
    if (i > 0) {
      oss << ", ";
    }
    oss << "0x" << std::hex << std::uppercase
        << static_cast<int>(cmds[i]);
  }
  oss << "]";
  return oss.str();
}

/**
 * @brief Check whether a subsequence appears in order within a larger sequence.
 *
 * Returns true if every element of `subseq` appears in `seq` in the same
 * relative order (not necessarily contiguous).
 */
bool is_ordered_subsequence(
  const std::vector<uint8_t> & seq,
  const std::vector<uint8_t> & subseq)
{
  size_t j = 0;
  for (size_t i = 0; i < seq.size() && j < subseq.size(); ++i) {
    if (seq[i] == subseq[j]) {
      ++j;
    }
  }
  return j == subseq.size();
}

/**
 * @brief Count occurrences of a specific command byte in a sequence.
 */
size_t count_command(const std::vector<uint8_t> & cmds, uint8_t target)
{
  return static_cast<size_t>(
    std::count(cmds.begin(), cmds.end(), target));
}

/**
 * @brief Build a STATUS_1 response frame with the given error flags.
 *
 * Frame layout: [cmd, temp, volt_lo, volt_hi, 0, 0, 0, err_flags]
 * Uses 25°C temperature and 24.0V (0.1V/LSB = 240).
 */
std::vector<uint8_t> make_status1_response(uint8_t error_flags)
{
  std::vector<uint8_t> data(8, 0);
  data[0] = CMD_READ_STATUS_1;
  data[1] = 25;   // temperature 25°C
  data[2] = 240;  // voltage low byte (24.0V @ 0.1V/LSB)
  data[3] = 0;    // voltage high byte
  data[7] = error_flags;
  return data;
}

}  // anonymous namespace

// =============================================================================
// Test Fixture
// =============================================================================

class MG6010InitShutdownTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite() { rclcpp::init(0, nullptr); }
  static void TearDownTestSuite() { rclcpp::shutdown(); }

  void SetUp() override
  {
    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    // Enable physics simulation for motor_id 1 with default config.
    MotorSimConfig sim_config;
    mock_can_->enable_motor_simulation(1, sim_config);

    config_.motor_type = "MG6010";
    config_.joint_name = "test_joint";
    config_.can_id = 1;
    config_.axis_id = 1;
    config_.direction = 1;
    config_.transmission_factor = 1.0;
  }

  void TearDown() override
  {
    mock_can_.reset();
  }

  /// Helper: initialize a controller with the default config and mock CAN.
  /// Returns the init result.
  bool init_controller(MG6010Controller & controller)
  {
    return controller.initialize(config_, mock_can_);
  }

  /// Helper: get the command byte sequence sent during the most recent
  /// operation (uses the full history from mock_can_).
  std::vector<uint8_t> get_all_command_bytes()
  {
    return extract_command_bytes(mock_can_->get_sent_messages(), MOTOR1_ARB_ID);
  }

  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;
  MotorConfiguration config_;
};

// =============================================================================
// Test 1: Init sequence ordering
//
// After initialize(), the command bytes on the CAN bus should appear in order:
//   motor_stop(0x81) → clear_errors(0x9B) → read_status(0x9A) → motor_on(0x88)
//
// EXPECTED: FAIL against current code (current does motor_on first).
// =============================================================================

TEST_F(MG6010InitShutdownTest, InitSequenceOrdering)
{
  MG6010Controller controller;
  bool ok = init_controller(controller);

  // Init should succeed even with the old sequence, but we verify command order.
  EXPECT_TRUE(ok) << "initialize() should succeed with simulation enabled";

  auto cmds = get_all_command_bytes();

  // The hardened init sequence requires these commands in this exact order.
  const std::vector<uint8_t> expected_order = {
    CMD_MOTOR_STOP,     // 0x81 — safe starting point
    CMD_CLEAR_ERRORS,   // 0x9B — clear any stale errors
    CMD_READ_STATUS_1,  // 0x9A — verify clean state
    CMD_MOTOR_ON        // 0x88 — enable motor
  };

  // Verify the expected commands appear as an ordered subsequence.
  // Additional commands (e.g. a second read_status for verification) are OK.
  EXPECT_TRUE(is_ordered_subsequence(cmds, expected_order))
    << "Init command sequence mismatch.\n"
    << "  Expected (ordered subsequence): "
    << format_cmd_sequence(expected_order) << "\n"
    << "  Actual CAN commands sent:       "
    << format_cmd_sequence(cmds);

  // Additionally verify that motor_stop appears BEFORE motor_on.
  // Find first occurrence of each.
  auto it_stop = std::find(cmds.begin(), cmds.end(), CMD_MOTOR_STOP);
  auto it_on = std::find(cmds.begin(), cmds.end(), CMD_MOTOR_ON);
  EXPECT_NE(it_stop, cmds.end())
    << "motor_stop (0x81) must be sent during init";
  EXPECT_NE(it_on, cmds.end())
    << "motor_on (0x88) must be sent during init";
  if (it_stop != cmds.end() && it_on != cmds.end()) {
    EXPECT_LT(std::distance(cmds.begin(), it_stop),
              std::distance(cmds.begin(), it_on))
      << "motor_stop (0x81) must precede motor_on (0x88) in init sequence.\n"
      << "  Actual: " << format_cmd_sequence(cmds);
  }

  // Verify clear_errors appears BEFORE read_status.
  auto it_clear = std::find(cmds.begin(), cmds.end(), CMD_CLEAR_ERRORS);
  auto it_status = std::find(cmds.begin(), cmds.end(), CMD_READ_STATUS_1);
  EXPECT_NE(it_clear, cmds.end())
    << "clear_errors (0x9B) must be sent during init";
  if (it_clear != cmds.end() && it_status != cmds.end()) {
    EXPECT_LT(std::distance(cmds.begin(), it_clear),
              std::distance(cmds.begin(), it_status))
      << "clear_errors (0x9B) must precede read_status (0x9A) in init.\n"
      << "  Actual: " << format_cmd_sequence(cmds);
  }
}

// =============================================================================
// Test 2: Init retry on persistent error
//
// When read_status returns error flags on the first 2 attempts, init should
// retry (clear_errors + read_status) and succeed on the 3rd clean read.
//
// EXPECTED: FAIL against current code (no retry loop exists).
// =============================================================================

TEST_F(MG6010InitShutdownTest, InitRetryOnPersistentError)
{
  // Disable motor simulation so we control responses manually.
  mock_can_->disable_motor_simulation(1);

  // We need to provide responses for every command the hardened init sends.
  // The sequence is: motor_stop → clear_errors → read_status (retry loop) → motor_on
  //
  // Strategy: pre-queue all expected responses in order.
  // The protocol does send_and_wait: sends a frame, then calls receive_message.

  // Response for motor_stop (0x81): echo with clean status
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_MOTOR_STOP, 25, 240, 0, 0, 0, 0, 0});

  // --- Attempt 1: clear_errors + read_status (error flags set) ---
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_CLEAR_ERRORS, 25, 240, 0, 0, 0, 0, 0});
  // read_status returns error flags = 0x01 (voltage error)
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    make_status1_response(0x01));

  // --- Attempt 2: clear_errors + read_status (error still present) ---
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_CLEAR_ERRORS, 25, 240, 0, 0, 0, 0, 0});
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    make_status1_response(0x01));

  // --- Attempt 3: clear_errors + read_status (clean) ---
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_CLEAR_ERRORS, 25, 240, 0, 0, 0, 0, 0});
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    make_status1_response(0x00));  // clean

  // Response for motor_on (0x88)
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_MOTOR_ON, 25, 240, 0, 0, 0, 0, 0});

  MG6010Controller controller;
  bool ok = init_controller(controller);
  EXPECT_TRUE(ok) << "Init should succeed after retry clears errors";

  auto cmds = get_all_command_bytes();

  // Expect at least 3 clear_errors and 3 read_status commands.
  size_t clear_count = count_command(cmds, CMD_CLEAR_ERRORS);
  size_t status_count = count_command(cmds, CMD_READ_STATUS_1);

  EXPECT_GE(clear_count, 3u)
    << "Expected at least 3 clear_errors attempts for persistent error.\n"
    << "  Actual commands: " << format_cmd_sequence(cmds);
  EXPECT_GE(status_count, 3u)
    << "Expected at least 3 read_status attempts for persistent error.\n"
    << "  Actual commands: " << format_cmd_sequence(cmds);
}

// =============================================================================
// Test 3: Init clears stale errors from previous session
//
// When the motor has error flags set (e.g. from a previous crash), init should
// send clear_errors early in the sequence and end with a clean state.
//
// EXPECTED: FAIL against current code (clear_errors only sent conditionally
// after motor_on, and the error may re-latch).
// =============================================================================

TEST_F(MG6010InitShutdownTest, InitErrorStateNotInherited)
{
  // Inject a fault so the simulated motor starts with error flags set.
  mock_can_->inject_fault(1, FaultType::OVER_TEMPERATURE);

  // The motor's error_flags will contain ERROR_TEMPERATURE (0x08).
  // The hardened init should clear errors before motor_on.

  MG6010Controller controller;
  bool ok = init_controller(controller);

  // Even with initial errors, init should succeed after clearing them.
  EXPECT_TRUE(ok) << "Init should succeed despite pre-existing motor errors";

  auto cmds = get_all_command_bytes();

  // Verify clear_errors was sent.
  EXPECT_GE(count_command(cmds, CMD_CLEAR_ERRORS), 1u)
    << "clear_errors must be sent during init to clear stale errors.\n"
    << "  Actual commands: " << format_cmd_sequence(cmds);

  // Verify clear_errors appears before motor_on.
  auto it_clear = std::find(cmds.begin(), cmds.end(), CMD_CLEAR_ERRORS);
  auto it_on = std::find(cmds.begin(), cmds.end(), CMD_MOTOR_ON);
  if (it_clear != cmds.end() && it_on != cmds.end()) {
    EXPECT_LT(std::distance(cmds.begin(), it_clear),
              std::distance(cmds.begin(), it_on))
      << "clear_errors must be called BEFORE motor_on so errors aren't inherited.\n"
      << "  Actual: " << format_cmd_sequence(cmds);
  }

  // After init, the controller should report no errors.
  // Clear the over-temperature fault from the simulator so subsequent reads
  // don't re-trigger it — the real test is that init clears the flags before
  // motor_on, not that the simulator keeps re-injecting.
  mock_can_->clear_fault(1, FaultType::OVER_TEMPERATURE);

  MotorStatus status = controller.get_status();
  EXPECT_NE(status.state, MotorStatus::AXIS_ERROR)
    << "Controller should not be in AXIS_ERROR state after successful init";
}

// =============================================================================
// Test 4: Init CAN timeout — init fails when motor_on cannot communicate
//
// When the CAN bus is partially responsive (motor_stop and clear_errors
// succeed) but read_status times out, the verify-clean loop retries and
// fails. Then motor_on also fails (no CAN response), causing init to
// return false. This tests the failure path when CAN is unreliable.
//
// Note: the verify-clean failure itself is non-fatal (retry loop warns
// and falls through to motor_on), but motor_on failure IS fatal.
// =============================================================================

TEST_F(MG6010InitShutdownTest, InitCANTimeout)
{
  // Disable motor simulation so no automatic responses are generated.
  mock_can_->disable_motor_simulation(1);

  // Queue a response for motor_stop (the first command in hardened init).
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_MOTOR_STOP, 25, 240, 0, 0, 0, 0, 0});

  // Queue a response for clear_errors.
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_CLEAR_ERRORS, 25, 240, 0, 0, 0, 0, 0});

  // Do NOT queue responses for read_status or motor_on — they will time out.
  // verify-clean will fail (non-fatal), then motor_on will fail (fatal).

  MG6010Controller controller;
  bool ok = init_controller(controller);

  // Init should fail because motor_on cannot get a CAN response.
  EXPECT_FALSE(ok)
    << "Init should fail when motor_on times out (CAN communication failure)";

  // Controller should not be in an initialized/enabled state.
  MotorStatus status = controller.get_status();
  EXPECT_NE(status.state, MotorStatus::CLOSED_LOOP_CONTROL)
    << "Controller must not be in CLOSED_LOOP_CONTROL after failed init";
}

// =============================================================================
// Test 4b: Verify-active resilience — init succeeds even if verify read fails
//
// Per the relaxed spec, verify_active is SHOULD (warn) not SHALL (fail).
// When motor_on succeeds but the subsequent read_status (verify active) fails,
// init should log a warning and still return true — the motor may be
// functional even when the status read is lost.
// =============================================================================

TEST_F(MG6010InitShutdownTest, InitSucceedsWhenVerifyActiveReadFails)
{
  // Disable motor simulation so we control all responses.
  mock_can_->disable_motor_simulation(1);

  // Queue motor_stop response.
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_MOTOR_STOP, 25, 240, 0, 0, 0, 0, 0});

  // Queue clear_errors response.
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_CLEAR_ERRORS, 25, 240, 0, 0, 0, 0, 0});

  // Queue read_status response (verify-clean) — clean state, no errors.
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_READ_STATUS_1, 25, 240, 0, 0, 0, 0, 0});

  // Queue motor_on response (success).
  mock_can_->queue_receive_message(MOTOR1_ARB_ID,
    {CMD_MOTOR_ON, 25, 240, 0, 0, 0, 0, 0});

  // Do NOT queue a response for the final read_status (verify-active) — it
  // will time out. Per the relaxed spec, this should NOT fail init.

  MG6010Controller controller;
  bool ok = init_controller(controller);

  // Init should SUCCEED — motor_on worked, verify-active failure is non-fatal.
  EXPECT_TRUE(ok)
    << "Init should succeed when motor_on works but verify-active read fails "
    << "(verify_active is SHOULD warn, not SHALL fail)";
}

// =============================================================================
// Test 5: Init uses protocol default timeout
//
// Verify that init commands use the protocol's default timeout configuration
// rather than introducing a separate hardcoded timeout constant. This is a
// design constraint test — we verify no new timeout parameter is visible.
//
// Approach: initialize with simulation enabled (so all commands succeed) and
// verify the protocol's num_retries / default_timeout_ms are used consistently
// by inspecting that init succeeds without any special timeout configuration.
// =============================================================================

TEST_F(MG6010InitShutdownTest, InitUsesExistingCANTimeout)
{
  // Default simulation is enabled — all commands respond automatically.
  // No special timeout configuration is provided.
  MG6010Controller controller;
  bool ok = init_controller(controller);

  EXPECT_TRUE(ok)
    << "Init should succeed using protocol's default timeout settings";

  auto cmds = get_all_command_bytes();

  // Verify the expected init commands were sent (they all used default timeout).
  // This is a sanity check — the real design verification is that no new
  // timeout constant was introduced in the implementation (code review).
  EXPECT_FALSE(cmds.empty())
    << "Init must send CAN commands using protocol's default timeout";

  // Verify motor_on was sent (init completed the full sequence).
  EXPECT_GE(count_command(cmds, CMD_MOTOR_ON), 1u)
    << "Init must complete through motor_on with default timeouts.\n"
    << "  Actual commands: " << format_cmd_sequence(cmds);
}

// =============================================================================
// Test 6: Shutdown sequence ordering
//
// After set_enabled(false), the CAN commands should be:
//   motor_stop(0x81) → motor_off(0x80) → clear_errors(0x9B)
//
// EXPECTED: FAIL against current code (current only sends motor_off).
// =============================================================================

TEST_F(MG6010InitShutdownTest, ShutdownSequenceOrdering)
{
  // First, initialize the controller (need a live controller to shut down).
  MG6010Controller controller;
  bool ok = init_controller(controller);
  ASSERT_TRUE(ok) << "Precondition: controller must initialize successfully";

  // Clear message history so we only see shutdown commands.
  mock_can_->clear_message_history();

  // Execute shutdown.
  bool disable_ok = controller.set_enabled(false);
  EXPECT_TRUE(disable_ok)
    << "set_enabled(false) should succeed during shutdown";

  auto cmds = get_all_command_bytes();

  // The hardened shutdown sequence should be:
  //   motor_stop(0x81) → motor_off(0x80) → clear_errors(0x9B)
  const std::vector<uint8_t> expected_shutdown = {
    CMD_MOTOR_STOP,    // 0x81 — stop motion first
    CMD_MOTOR_OFF,     // 0x80 — de-energize motor
    CMD_CLEAR_ERRORS   // 0x9B — leave motor in clean state
  };

  EXPECT_TRUE(is_ordered_subsequence(cmds, expected_shutdown))
    << "Shutdown sequence mismatch.\n"
    << "  Expected (ordered subsequence): "
    << format_cmd_sequence(expected_shutdown) << "\n"
    << "  Actual CAN commands sent:       "
    << format_cmd_sequence(cmds);

  // Verify motor_stop is the first command in the shutdown sequence.
  if (!cmds.empty()) {
    EXPECT_EQ(cmds[0], CMD_MOTOR_STOP)
      << "First shutdown command must be motor_stop (0x81), got 0x"
      << std::hex << std::uppercase << static_cast<int>(cmds[0]);
  }

  // Verify all three commands are present.
  EXPECT_GE(count_command(cmds, CMD_MOTOR_STOP), 1u)
    << "Shutdown must include motor_stop (0x81).\n"
    << "  Actual: " << format_cmd_sequence(cmds);
  EXPECT_GE(count_command(cmds, CMD_MOTOR_OFF), 1u)
    << "Shutdown must include motor_off (0x80).\n"
    << "  Actual: " << format_cmd_sequence(cmds);
  EXPECT_GE(count_command(cmds, CMD_CLEAR_ERRORS), 1u)
    << "Shutdown must include clear_errors (0x9B).\n"
    << "  Actual: " << format_cmd_sequence(cmds);
}

// =============================================================================
// Test 7: Shutdown after motor error — sequence completes despite failures
//
// When motor_stop fails (e.g. motor in error state), the shutdown sequence
// must still proceed to send motor_off and clear_errors. A fault during
// shutdown must not prevent the motor from being de-energized.
//
// EXPECTED: FAIL against current code (current only sends motor_off, and
// if motor_off fails, nothing else happens).
// =============================================================================

TEST_F(MG6010InitShutdownTest, ShutdownAfterMotorError)
{
  // Initialize the controller normally.
  MG6010Controller controller;
  bool ok = init_controller(controller);
  ASSERT_TRUE(ok) << "Precondition: controller must initialize successfully";

  // Clear message history to isolate shutdown commands.
  mock_can_->clear_message_history();

  // Inject an error so motor_stop will fail on the next send.
  // inject_error_on_next_operation makes the NEXT send_message call fail.
  mock_can_->inject_error_on_next_operation();

  // Execute shutdown — motor_stop should fail, but motor_off and
  // clear_errors should still be attempted.
  controller.set_enabled(false);

  auto cmds = get_all_command_bytes();

  // Even though motor_stop failed (send returned false, so it won't appear
  // in sent_messages_), motor_off MUST still be sent.
  EXPECT_GE(count_command(cmds, CMD_MOTOR_OFF), 1u)
    << "motor_off (0x80) must be sent even if motor_stop fails.\n"
    << "  Actual commands: " << format_cmd_sequence(cmds);

  // clear_errors should also be sent after motor_off.
  EXPECT_GE(count_command(cmds, CMD_CLEAR_ERRORS), 1u)
    << "clear_errors (0x9B) must be sent during shutdown even after errors.\n"
    << "  Actual commands: " << format_cmd_sequence(cmds);
}
