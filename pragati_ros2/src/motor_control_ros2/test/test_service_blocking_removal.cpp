/**
 * @file test_service_blocking_removal.cpp
 * @brief Tests for phase-2-critical-fixes tasks 1.1-1.6: service handler blocking removal
 *
 * Verifies that:
 * - wait_for_completion=true returns an immediate error (no blocking)
 * - wait_for_completion=false still returns ACCEPTED
 * - No blocking loop (while/sleep_for) remains in the service handler
 * - watchdog_exempt_ is NOT used in the service handler
 * - watchdog_exempt_ IS still used in homing (perform_motor_homing, executeJointHoming)
 *
 * Uses source-code-parsing pattern (Pattern A) since MG6010ControllerNode is not exported.
 * Same approach as test_watchdog_exempt_flag.cpp.
 */

#include <gtest/gtest.h>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>

class ServiceBlockingRemovalTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    std::string source_dir;
#ifdef SOURCE_DIR
    source_dir = SOURCE_DIR;
#else
    source_dir = "..";
#endif
    std::string filepath = source_dir + "/src/mg6010_controller_node.cpp";
    std::ifstream file(filepath);
    ASSERT_TRUE(file.is_open())
        << "Cannot open source file: " << filepath
        << " (SOURCE_DIR=" << source_dir << ")";

    std::string line;
    while (std::getline(file, line)) {
      source_lines_.push_back(line);
    }
    ASSERT_GT(source_lines_.size(), 2000u)
        << "Source file suspiciously small - wrong file?";
  }

  int findLine(const std::string& pattern, int start = 0) const
  {
    for (int i = start; i < static_cast<int>(source_lines_.size()); ++i) {
      if (source_lines_[i].find(pattern) != std::string::npos) {
        return i;
      }
    }
    return -1;
  }

  std::vector<int> findAllLines(const std::string& pattern, int start, int end) const
  {
    std::vector<int> results;
    for (int i = start; i < end && i < static_cast<int>(source_lines_.size()); ++i) {
      if (source_lines_[i].find(pattern) != std::string::npos) {
        results.push_back(i);
      }
    }
    return results;
  }

  // Find the approximate end of a function by tracking brace depth
  // starting from the opening brace of the function body.
  int findFunctionEnd(int body_start) const
  {
    int depth = 0;
    for (int i = body_start; i < static_cast<int>(source_lines_.size()); ++i) {
      for (char c : source_lines_[i]) {
        if (c == '{') depth++;
        if (c == '}') {
          depth--;
          if (depth == 0) return i;
        }
      }
    }
    return -1;
  }

  std::vector<std::string> source_lines_;
};

// ---------------------------------------------------------------------------
// Task 1.1: wait_for_completion=true returns immediate error
// ---------------------------------------------------------------------------
TEST_F(ServiceBlockingRemovalTest, WaitForCompletionTrueReturnsError)
{
  // Find the service callback definition (not the bind() reference)
  int callback_line = findLine("void joint_position_command_callback");
  ASSERT_GE(callback_line, 0)
      << "Could not find joint_position_command_callback definition in source";

  // Find the wait_for_completion check
  int wait_check = findLine("if (!request->wait_for_completion)", callback_line);
  ASSERT_GE(wait_check, 0)
      << "Could not find wait_for_completion check in service handler";

  // After the !wait_for_completion early-return block (ACCEPTED path), there should
  // be an immediate error return for the true case. Look for the deprecation response.
  // Search from the wait_for_completion check to the end of the function.
  int func_end = findFunctionEnd(callback_line);
  ASSERT_GT(func_end, wait_check)
      << "Could not find end of joint_position_command_callback";

  // The true path (after the early-return block) must set success = false
  auto success_false = findAllLines("success = false", wait_check, func_end);
  ASSERT_GE(static_cast<int>(success_false.size()), 1)
      << "wait_for_completion=true path must return success = false "
         "(deprecation error)";

  // The reason must mention action server or deprecated (case-insensitive via
  // checking for common substrings)
  bool found_deprecation = false;
  for (int i = wait_check; i < func_end; ++i) {
    const std::string& line = source_lines_[i];
    // Convert to lowercase for case-insensitive search
    std::string lower = line;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    if (lower.find("deprecated") != std::string::npos ||
        lower.find("action server") != std::string::npos ||
        lower.find("action_server") != std::string::npos) {
      found_deprecation = true;
      break;
    }
  }
  EXPECT_TRUE(found_deprecation)
      << "wait_for_completion=true error response must mention 'deprecated' or "
         "'action server' to guide callers to the replacement API";
}

// ---------------------------------------------------------------------------
// Task 1.2: wait_for_completion=false still returns ACCEPTED
// ---------------------------------------------------------------------------
TEST_F(ServiceBlockingRemovalTest, WaitForCompletionFalseStillAccepted)
{
  int callback_line = findLine("joint_position_command_callback");
  ASSERT_GE(callback_line, 0);

  int wait_check = findLine("if (!request->wait_for_completion)", callback_line);
  ASSERT_GE(wait_check, 0);

  // The !wait_for_completion block should contain success = true and "ACCEPTED"
  // Search a small window after the check (the early-return block is ~6 lines)
  int block_end = wait_check + 10;

  auto success_true = findAllLines("success = true", wait_check, block_end);
  EXPECT_GE(static_cast<int>(success_true.size()), 1)
      << "!wait_for_completion path must still set success = true";

  auto accepted = findAllLines("\"ACCEPTED\"", wait_check, block_end);
  EXPECT_GE(static_cast<int>(accepted.size()), 1)
      << "!wait_for_completion path must still set reason = \"ACCEPTED\"";
}

// ---------------------------------------------------------------------------
// Task 1.3 verification: No blocking while loop in service handler
// ---------------------------------------------------------------------------
TEST_F(ServiceBlockingRemovalTest, NoBlockingLoopRemains)
{
  int callback_line = findLine("joint_position_command_callback");
  ASSERT_GE(callback_line, 0);

  int func_end = findFunctionEnd(callback_line);
  ASSERT_GT(func_end, callback_line);

  auto while_loops = findAllLines("while (rclcpp::ok())", callback_line, func_end);
  EXPECT_EQ(static_cast<int>(while_loops.size()), 0)
      << "joint_position_command_callback must NOT contain a while(rclcpp::ok()) loop. "
         "The blocking wait path was removed in phase-2-critical-fixes (bug 1.2). "
         "Found " << while_loops.size() << " occurrence(s).";
}

// ---------------------------------------------------------------------------
// Task 1.3 verification: No sleep_for in service handler
// ---------------------------------------------------------------------------
TEST_F(ServiceBlockingRemovalTest, NoSleepForInServiceHandler)
{
  int callback_line = findLine("joint_position_command_callback");
  ASSERT_GE(callback_line, 0);

  int func_end = findFunctionEnd(callback_line);
  ASSERT_GT(func_end, callback_line);

  auto sleep_calls = findAllLines("sleep_for", callback_line, func_end);
  EXPECT_EQ(static_cast<int>(sleep_calls.size()), 0)
      << "joint_position_command_callback must NOT contain sleep_for calls. "
         "The blocking wait path was removed in phase-2-critical-fixes (bug 1.2). "
         "Found " << sleep_calls.size() << " occurrence(s).";
}

// ---------------------------------------------------------------------------
// Task 1.4: watchdog_exempt_ NOT set during service calls
// ---------------------------------------------------------------------------
TEST_F(ServiceBlockingRemovalTest, WatchdogExemptNotSetInServiceHandler)
{
  int callback_line = findLine("joint_position_command_callback");
  ASSERT_GE(callback_line, 0);

  int func_end = findFunctionEnd(callback_line);
  ASSERT_GT(func_end, callback_line);

  auto exempt_calls = findAllLines("watchdog_exempt_", callback_line, func_end);
  EXPECT_EQ(static_cast<int>(exempt_calls.size()), 0)
      << "joint_position_command_callback must NOT reference watchdog_exempt_. "
         "The blocking wait path (which needed watchdog exemption) was removed. "
         "Found " << exempt_calls.size() << " occurrence(s).";
}

// ---------------------------------------------------------------------------
// Task 1.6: watchdog_exempt_ still set during homing (perform_motor_homing)
// ---------------------------------------------------------------------------
TEST_F(ServiceBlockingRemovalTest, WatchdogExemptStillInHoming)
{
  int homing_line = findLine("void perform_motor_homing(");
  ASSERT_GE(homing_line, 0)
      << "Could not find perform_motor_homing function";

  int func_end = findFunctionEnd(homing_line);
  ASSERT_GT(func_end, homing_line);

  auto exempt_true = findAllLines("watchdog_exempt_.store(true", homing_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_true.size()), 1)
      << "perform_motor_homing must still set watchdog_exempt_ = true. "
         "Homing involves blocking motor movement and needs watchdog exemption.";

  auto exempt_false = findAllLines("watchdog_exempt_.store(false", homing_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_false.size()), 1)
      << "perform_motor_homing must still clear watchdog_exempt_ on exit paths.";
}

// ---------------------------------------------------------------------------
// Task 1.6: watchdog_exempt_ still set in homing action server
// ---------------------------------------------------------------------------
TEST_F(ServiceBlockingRemovalTest, WatchdogExemptStillInHomingActionServer)
{
  int execute_line = findLine("void executeJointHoming(");
  ASSERT_GE(execute_line, 0)
      << "Could not find executeJointHoming function";

  int func_end = findFunctionEnd(execute_line);
  ASSERT_GT(func_end, execute_line);

  auto exempt_true = findAllLines("watchdog_exempt_.store(true", execute_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_true.size()), 1)
      << "executeJointHoming must still set watchdog_exempt_ = true. "
         "The homing action server involves blocking motor movement and needs "
         "watchdog exemption.";

  auto exempt_false = findAllLines("watchdog_exempt_.store(false", execute_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_false.size()), 1)
      << "executeJointHoming must still clear watchdog_exempt_ on exit paths.";
}
