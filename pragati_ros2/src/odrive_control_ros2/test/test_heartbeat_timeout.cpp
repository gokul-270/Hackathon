// Copyright 2025 Pragati Robotics
// Tests for ODrive Heartbeat Timeout Detection
//
// Source-verification gtest: scans odrive_service_node.cpp for the
// heartbeat timeout detection implementation. Verifies:
// (a) heartbeat_stale field exists in ODriveState
// (b) 1Hz timer checks heartbeat freshness
// (c) 2-second timeout constant
// (d) heartbeat_received==false guard (skip uninitialized motors)
// (e) transition-based logging (stale→stale produces no new log)
// (f) recovery detection (stale→healthy clears flag and logs)
// (g) CAN RX handler clears stale flag on heartbeat arrival

#include <gtest/gtest.h>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>

// SOURCE_DIR is set via CMakeLists.txt compile definition
#ifndef SOURCE_DIR
#error "SOURCE_DIR must be defined to point to the package source directory"
#endif

namespace {

// Read the entire source file into a string
std::string read_source_file(const std::string& relative_path) {
  std::string full_path = std::string(SOURCE_DIR) + "/" + relative_path;
  std::ifstream file(full_path);
  EXPECT_TRUE(file.is_open()) << "Failed to open: " << full_path;
  std::ostringstream ss;
  ss << file.rdbuf();
  return ss.str();
}

// Split source into lines for line-by-line analysis
std::vector<std::string> split_lines(const std::string& content) {
  std::vector<std::string> lines;
  std::istringstream stream(content);
  std::string line;
  while (std::getline(stream, line)) {
    lines.push_back(line);
  }
  return lines;
}

// Find all lines containing a pattern
std::vector<size_t> find_lines_matching(const std::vector<std::string>& lines,
                                        const std::string& pattern) {
  std::vector<size_t> result;
  for (size_t i = 0; i < lines.size(); ++i) {
    if (lines[i].find(pattern) != std::string::npos) {
      result.push_back(i);
    }
  }
  return result;
}

// Find text within a range of lines
bool find_in_range(const std::vector<std::string>& lines,
                   size_t start, size_t end, const std::string& pattern) {
  for (size_t i = start; i < std::min(end, lines.size()); ++i) {
    if (lines[i].find(pattern) != std::string::npos) {
      return true;
    }
  }
  return false;
}

// Find the line number of a function definition
size_t find_function_start(const std::vector<std::string>& lines,
                           const std::string& func_signature) {
  for (size_t i = 0; i < lines.size(); ++i) {
    if (lines[i].find(func_signature) != std::string::npos) {
      return i;
    }
  }
  return std::string::npos;
}

// Find the end of a function (matching closing brace) starting from a given line
size_t find_function_end(const std::vector<std::string>& lines, size_t start) {
  int brace_depth = 0;
  bool found_first_brace = false;
  for (size_t i = start; i < lines.size(); ++i) {
    for (char c : lines[i]) {
      if (c == '{') {
        brace_depth++;
        found_first_brace = true;
      }
      if (c == '}') {
        brace_depth--;
        if (found_first_brace && brace_depth == 0) {
          return i;
        }
      }
    }
  }
  return lines.size();
}

}  // namespace

class HeartbeatTimeoutSourceTest : public ::testing::Test {
protected:
  void SetUp() override {
    source_ = read_source_file("src/odrive_service_node.cpp");
    ASSERT_FALSE(source_.empty()) << "Source file is empty";
    lines_ = split_lines(source_);
  }

  std::string source_;
  std::vector<std::string> lines_;
};

// (a) Verify heartbeat_stale field exists in ODriveState struct
TEST_F(HeartbeatTimeoutSourceTest, HeartbeatStaleFieldExists) {
  // Find the ODriveState struct
  auto struct_lines = find_lines_matching(lines_, "struct ODriveState");
  ASSERT_GT(struct_lines.size(), 0u) << "ODriveState struct not found";

  size_t struct_start = struct_lines[0];
  size_t struct_end = find_function_end(lines_, struct_start);

  // heartbeat_stale field must exist with default = false
  bool has_stale_field = false;
  for (size_t i = struct_start; i <= struct_end; ++i) {
    if (lines_[i].find("heartbeat_stale") != std::string::npos &&
        lines_[i].find("bool") != std::string::npos) {
      has_stale_field = true;
      // Verify default initialization to false
      EXPECT_NE(lines_[i].find("false"), std::string::npos)
          << "heartbeat_stale should be initialized to false. Line "
          << (i + 1) << ": " << lines_[i];
      break;
    }
  }

  EXPECT_TRUE(has_stale_field)
      << "ODriveState struct must have a 'bool heartbeat_stale = false' field "
      << "for tracking stale heartbeat state per motor";
}

// (b) Verify 1Hz heartbeat timeout timer exists
TEST_F(HeartbeatTimeoutSourceTest, HeartbeatTimeoutTimerExists) {
  // Check for the timer member variable
  EXPECT_NE(source_.find("heartbeat_timeout_timer_"), std::string::npos)
      << "heartbeat_timeout_timer_ member variable not found";

  // Check that the timer is created (in constructor or init)
  auto timer_creation_lines = find_lines_matching(lines_, "heartbeat_timeout_timer_");
  bool found_creation = false;
  for (size_t line_num : timer_creation_lines) {
    if (lines_[line_num].find("create_wall_timer") != std::string::npos) {
      found_creation = true;
      break;
    }
  }
  EXPECT_TRUE(found_creation)
      << "heartbeat_timeout_timer_ must be created with create_wall_timer()";

  // Verify it's ~1Hz (1000ms or 1s period)
  // Look for "1000ms" or "1s" near the timer creation
  bool found_1hz = false;
  for (size_t line_num : timer_creation_lines) {
    if (lines_[line_num].find("create_wall_timer") != std::string::npos) {
      // Check nearby lines for the period
      for (size_t i = (line_num > 2 ? line_num - 2 : 0);
           i < std::min(line_num + 3, lines_.size()); ++i) {
        if (lines_[i].find("1000ms") != std::string::npos ||
            lines_[i].find("1s") != std::string::npos ||
            lines_[i].find("1000") != std::string::npos) {
          found_1hz = true;
          break;
        }
      }
      break;
    }
  }
  EXPECT_TRUE(found_1hz)
      << "heartbeat_timeout_timer_ should fire at ~1Hz (1000ms period)";
}

// (c) Verify 2-second timeout constant
TEST_F(HeartbeatTimeoutSourceTest, TwoSecondTimeoutConstant) {
  // Look for the heartbeat timeout constant (constexpr, const, or inline value)
  bool found_timeout = false;

  // Check for constexpr/const definition
  for (size_t i = 0; i < lines_.size(); ++i) {
    const std::string& line = lines_[i];
    if ((line.find("heartbeat_timeout") != std::string::npos ||
         line.find("HEARTBEAT_TIMEOUT") != std::string::npos) &&
        (line.find("2.0") != std::string::npos ||
         line.find("2s") != std::string::npos ||
         line.find("2000") != std::string::npos)) {
      found_timeout = true;
      break;
    }
  }

  // Also check check_heartbeat_timeouts function body for inline 2.0 or 2s
  if (!found_timeout) {
    auto func_start = find_function_start(lines_, "void check_heartbeat_timeouts()");
    if (func_start != std::string::npos) {
      size_t func_end = find_function_end(lines_, func_start);
      for (size_t i = func_start; i <= func_end; ++i) {
        if (lines_[i].find("2.0") != std::string::npos ||
            lines_[i].find("2s") != std::string::npos ||
            lines_[i].find("2000") != std::string::npos) {
          found_timeout = true;
          break;
        }
      }
    }
  }

  EXPECT_TRUE(found_timeout)
      << "Heartbeat timeout constant of 2 seconds not found. "
      << "ODrive sends heartbeat at ~10Hz (100ms), so 2 seconds = ~20 missed "
      << "heartbeats. This should be defined as constexpr.";
}

// (d) Verify check_heartbeat_timeouts function exists and has heartbeat_received guard
TEST_F(HeartbeatTimeoutSourceTest, CheckHeartbeatTimeoutsWithReceivedGuard) {
  auto func_start = find_function_start(lines_, "void check_heartbeat_timeouts()");
  ASSERT_NE(func_start, std::string::npos)
      << "check_heartbeat_timeouts() function not found";

  size_t func_end = find_function_end(lines_, func_start);

  // Must check heartbeat_received to skip uninitialized motors
  EXPECT_TRUE(find_in_range(lines_, func_start, func_end, "heartbeat_received"))
      << "check_heartbeat_timeouts() must check heartbeat_received to skip "
      << "motors that haven't sent any heartbeat yet (prevents false alarms "
      << "during startup)";
}

// (e) Verify transition-based logging (set heartbeat_stale on transition only)
TEST_F(HeartbeatTimeoutSourceTest, TransitionBasedStaleFlagSetting) {
  auto func_start = find_function_start(lines_, "void check_heartbeat_timeouts()");
  ASSERT_NE(func_start, std::string::npos)
      << "check_heartbeat_timeouts() function not found";

  size_t func_end = find_function_end(lines_, func_start);

  // Must check the existing heartbeat_stale value before setting it
  // (i.e., only log on transition, not every tick)
  // Pattern: check !heartbeat_stale or heartbeat_stale == false before
  // setting it to true
  bool has_transition_check = false;
  for (size_t i = func_start; i <= func_end; ++i) {
    if ((lines_[i].find("!") != std::string::npos &&
         lines_[i].find("heartbeat_stale") != std::string::npos) ||
        (lines_[i].find("heartbeat_stale") != std::string::npos &&
         lines_[i].find("false") != std::string::npos)) {
      has_transition_check = true;
      break;
    }
  }

  EXPECT_TRUE(has_transition_check)
      << "check_heartbeat_timeouts() must check the current heartbeat_stale "
      << "value before logging — only log on healthy→stale transition, not "
      << "every 1Hz tick while motor remains stale. Pattern: "
      << "if (!state.heartbeat_stale) { state.heartbeat_stale = true; log; }";

  // Must log RCLCPP_ERROR on stale detection
  EXPECT_TRUE(find_in_range(lines_, func_start, func_end, "RCLCPP_ERROR"))
      << "check_heartbeat_timeouts() must log RCLCPP_ERROR when a motor "
      << "heartbeat goes stale";
}

// (f) Verify recovery detection: stale→healthy transition logging
TEST_F(HeartbeatTimeoutSourceTest, RecoveryDetectionAndLogging) {
  // Recovery can be in check_heartbeat_timeouts OR in the CAN RX handler
  // Check for RCLCPP_WARN with recovery-related content
  bool has_recovery_log = false;

  // Check check_heartbeat_timeouts
  auto func_start = find_function_start(lines_, "void check_heartbeat_timeouts()");
  if (func_start != std::string::npos) {
    size_t func_end = find_function_end(lines_, func_start);
    if (find_in_range(lines_, func_start, func_end, "RCLCPP_WARN")) {
      has_recovery_log = true;
    }
  }

  // Also check CAN RX thread for recovery logging
  if (!has_recovery_log) {
    auto rx_start = find_function_start(lines_, "void can_rx_thread()");
    if (rx_start != std::string::npos) {
      size_t rx_end = find_function_end(lines_, rx_start);
      if (find_in_range(lines_, rx_start, rx_end, "heartbeat_stale") &&
          find_in_range(lines_, rx_start, rx_end, "RCLCPP_WARN")) {
        has_recovery_log = true;
      }
    }
  }

  EXPECT_TRUE(has_recovery_log)
      << "Recovery detection must log RCLCPP_WARN when a stale motor resumes "
      << "sending heartbeats. This can be in check_heartbeat_timeouts() or "
      << "in the CAN RX heartbeat handler.";
}

// (g) Verify CAN RX handler clears heartbeat_stale on heartbeat arrival
TEST_F(HeartbeatTimeoutSourceTest, CANRXClearsStaleFlag) {
  auto rx_start = find_function_start(lines_, "void can_rx_thread()");
  ASSERT_NE(rx_start, std::string::npos)
      << "can_rx_thread() function not found";

  size_t rx_end = find_function_end(lines_, rx_start);

  // The heartbeat case in the CAN RX handler must reference heartbeat_stale
  // to clear it when a heartbeat arrives for a stale motor
  EXPECT_TRUE(find_in_range(lines_, rx_start, rx_end, "heartbeat_stale"))
      << "CAN RX heartbeat handler must clear heartbeat_stale when a "
      << "heartbeat arrives for a motor that was marked stale. This enables "
      << "recovery detection.";
}

// Verify check_heartbeat_timeouts holds state_mutex_
TEST_F(HeartbeatTimeoutSourceTest, CheckTimeoutsHoldsMutex) {
  auto func_start = find_function_start(lines_, "void check_heartbeat_timeouts()");
  ASSERT_NE(func_start, std::string::npos)
      << "check_heartbeat_timeouts() function not found";

  // Check first 5 lines of the function for a lock
  bool has_lock = false;
  for (size_t i = func_start; i < std::min(func_start + 8, lines_.size()); ++i) {
    if ((lines_[i].find("lock_guard") != std::string::npos ||
         lines_[i].find("unique_lock") != std::string::npos ||
         lines_[i].find("scoped_lock") != std::string::npos) &&
        lines_[i].find("state_mutex_") != std::string::npos) {
      has_lock = true;
      break;
    }
  }

  EXPECT_TRUE(has_lock)
      << "check_heartbeat_timeouts() must hold state_mutex_ when iterating "
      << "odrive_states_ (shared with CAN RX thread)";
}

// Verify the timeout check iterates odrive_states_ (not a subset)
TEST_F(HeartbeatTimeoutSourceTest, IteratesAllMotors) {
  auto func_start = find_function_start(lines_, "void check_heartbeat_timeouts()");
  ASSERT_NE(func_start, std::string::npos)
      << "check_heartbeat_timeouts() function not found";

  size_t func_end = find_function_end(lines_, func_start);

  EXPECT_TRUE(find_in_range(lines_, func_start, func_end, "odrive_states_"))
      << "check_heartbeat_timeouts() must iterate over odrive_states_ to "
      << "check all configured motors";
}
