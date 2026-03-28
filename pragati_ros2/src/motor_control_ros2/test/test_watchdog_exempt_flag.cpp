/**
 * @file test_watchdog_exempt_flag.cpp
 * @brief Tests for watchdog_exempt_ flag correctness after phase-2-critical-fixes.
 *
 * Phase-1 added watchdog_exempt_ around the blocking wait_for_completion loop.
 * Phase-2 REMOVED that blocking loop entirely (replaced with immediate deprecation
 * error). Therefore:
 *
 * - watchdog_exempt_ must NOT appear in joint_position_command_callback
 *   (the blocking loop is gone, so there's nothing to exempt)
 * - watchdog_exempt_ MUST still appear in perform_motor_homing
 *   (homing is still a long-running blocking operation)
 *
 * The MG6010ControllerNode class is defined inside mg6010_controller_node.cpp
 * and is NOT exported, so we use source-code parsing to verify.
 */

#include <gtest/gtest.h>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>

class WatchdogExemptFlagTest : public ::testing::Test
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
        << "Source file suspiciously small — wrong file?";
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

  // Find approximate end of a function by tracking brace depth.
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

// Phase-2: watchdog_exempt_ must NOT appear in the service handler
// (blocking loop was removed, so there's nothing to exempt)
TEST_F(WatchdogExemptFlagTest, WatchdogExemptNotInServiceHandler)
{
  int callback_line = findLine("void joint_position_command_callback");
  ASSERT_GE(callback_line, 0)
      << "Could not find joint_position_command_callback definition";

  int func_end = findFunctionEnd(callback_line);
  ASSERT_GT(func_end, callback_line)
      << "Could not find end of joint_position_command_callback";

  auto exempt_lines = findAllLines("watchdog_exempt_", callback_line, func_end);
  EXPECT_EQ(static_cast<int>(exempt_lines.size()), 0)
      << "watchdog_exempt_ must NOT appear in joint_position_command_callback. "
         "The blocking wait loop was removed in phase-2-critical-fixes, so "
         "there is no long-running operation to exempt from watchdog checks. "
         "Found " << exempt_lines.size() << " occurrence(s).";
}

// Phase-2: watchdog_exempt_ MUST still appear in perform_motor_homing
// (homing is still a long-running blocking operation that needs exemption)
TEST_F(WatchdogExemptFlagTest, WatchdogExemptStillInHoming)
{
  int homing_line = findLine("void perform_motor_homing");
  ASSERT_GE(homing_line, 0)
      << "Could not find perform_motor_homing definition in source";

  int func_end = findFunctionEnd(homing_line);
  ASSERT_GT(func_end, homing_line)
      << "Could not find end of perform_motor_homing";

  auto exempt_true = findAllLines("watchdog_exempt_.store(true", homing_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_true.size()), 1)
      << "watchdog_exempt_.store(true) must appear in perform_motor_homing. "
         "Homing is a long-running blocking operation that must be exempt "
         "from watchdog timeout checks.";

  auto exempt_false = findAllLines("watchdog_exempt_.store(false", homing_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_false.size()), 1)
      << "watchdog_exempt_.store(false) must appear in perform_motor_homing "
         "to re-enable watchdog checks after homing completes.";
}

// Phase-2: watchdog_exempt_ stores in homing use memory_order_release
// (matching existing convention for cross-thread visibility)
TEST_F(WatchdogExemptFlagTest, WatchdogExemptUsesCorrectMemoryOrdering)
{
  int homing_line = findLine("void perform_motor_homing");
  ASSERT_GE(homing_line, 0);

  int func_end = findFunctionEnd(homing_line);
  ASSERT_GT(func_end, homing_line);

  auto all_stores = findAllLines("watchdog_exempt_.store(", homing_line, func_end);
  ASSERT_GE(static_cast<int>(all_stores.size()), 1)
      << "No watchdog_exempt_.store() calls found in perform_motor_homing";

  for (int line_num : all_stores) {
    const std::string& line = source_lines_[line_num];
    EXPECT_TRUE(line.find("memory_order_release") != std::string::npos)
        << "watchdog_exempt_.store() at line " << line_num + 1
        << " should use std::memory_order_release (matches existing convention).\n"
        << "Actual line: " << line;
  }
}

// Task 1.8: watchdog_exempt_ MUST appear in executeJointPositionCommand
// (the action server blocking loop is a long-running operation that needs exemption)
TEST_F(WatchdogExemptFlagTest, WatchdogExemptInPositionCommandAction)
{
  int execute_line = findLine("void executeJointPositionCommand");
  ASSERT_GE(execute_line, 0)
      << "Could not find executeJointPositionCommand definition in source";

  int func_end = findFunctionEnd(execute_line);
  ASSERT_GT(func_end, execute_line)
      << "Could not find end of executeJointPositionCommand";

  auto exempt_true = findAllLines("watchdog_exempt_.store(true", execute_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_true.size()), 1)
      << "watchdog_exempt_.store(true) must appear in executeJointPositionCommand. "
         "The action server blocking feedback loop is a long-running operation "
         "that must be exempt from watchdog timeout checks.";

  auto exempt_false = findAllLines("watchdog_exempt_.store(false", execute_line, func_end);
  EXPECT_GE(static_cast<int>(exempt_false.size()), 1)
      << "watchdog_exempt_.store(false) must appear in executeJointPositionCommand "
         "to re-enable watchdog checks after position command completes.";
}

// Task 1.8: watchdog_exempt_ stores in position command use memory_order_release
TEST_F(WatchdogExemptFlagTest, WatchdogExemptPositionCommandUsesCorrectMemoryOrdering)
{
  int execute_line = findLine("void executeJointPositionCommand");
  ASSERT_GE(execute_line, 0);

  int func_end = findFunctionEnd(execute_line);
  ASSERT_GT(func_end, execute_line);

  auto all_stores = findAllLines("watchdog_exempt_.store(", execute_line, func_end);
  ASSERT_GE(static_cast<int>(all_stores.size()), 1)
      << "No watchdog_exempt_.store() calls found in executeJointPositionCommand";

  for (int line_num : all_stores) {
    const std::string& line = source_lines_[line_num];
    EXPECT_TRUE(line.find("memory_order_release") != std::string::npos)
        << "watchdog_exempt_.store() at line " << line_num + 1
        << " should use std::memory_order_release (matches existing convention).\n"
        << "Actual line: " << line;
  }
}

// Task 1.8: watchdog_exempt_ must be cleared on ALL exit paths in executeJointPositionCommand
// (success, timeout, cancellation, shutdown, error — at least 4 clear calls)
TEST_F(WatchdogExemptFlagTest, WatchdogExemptPositionCommandClearedOnAllExitPaths)
{
  int execute_line = findLine("void executeJointPositionCommand");
  ASSERT_GE(execute_line, 0);

  int func_end = findFunctionEnd(execute_line);
  ASSERT_GT(func_end, execute_line);

  auto exempt_false = findAllLines("watchdog_exempt_.store(false", execute_line, func_end);
  // Exit paths: success (REACHED), timeout (TIMEOUT), cancel (CANCELLED),
  // shutdown (rclcpp shutting down), motor-not-available, CAN-command-failed
  // At minimum 4 false stores (some early-exit paths before loop don't need exemption)
  EXPECT_GE(static_cast<int>(exempt_false.size()), 4)
      << "watchdog_exempt_.store(false) must appear on ALL exit paths in "
         "executeJointPositionCommand. Expected at least 4 occurrences "
         "(success, timeout, cancel, shutdown). Found " << exempt_false.size() << ".";
}
