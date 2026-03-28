// Copyright 2026 Pragati Robotics
// Tests for SocketCAN loopback disable bugfix (Section 7)
//
// Verifies that CAN_RAW_LOOPBACK and CAN_RAW_RECV_OWN_MSGS setsockopt calls
// are in initialize() (after bind), NOT gated behind apply_filters()'s
// non-empty node_ids check. This prevents the bug where loopback remains
// enabled when no CAN filters are configured.
//
// Uses source-code verification since testing actual socket options requires
// a real CAN interface (vcan or hardware).

#include <gtest/gtest.h>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#ifndef SOURCE_DIR
#error "SOURCE_DIR must be defined to point to the package source directory"
#endif

namespace {

std::string read_source(const std::string& relative_path) {
  std::string full_path = std::string(SOURCE_DIR) + "/" + relative_path;
  std::ifstream file(full_path);
  EXPECT_TRUE(file.is_open()) << "Failed to open: " << full_path;
  std::ostringstream ss;
  ss << file.rdbuf();
  return ss.str();
}

std::vector<std::string> split_lines(const std::string& content) {
  std::vector<std::string> lines;
  std::istringstream stream(content);
  std::string line;
  while (std::getline(stream, line)) {
    lines.push_back(line);
  }
  return lines;
}

// Find the line range for a function definition (simplistic: first '{' to
// matching '}' at column 0).
// Returns {start_line, end_line} (0-indexed) or {-1, -1} if not found.
std::pair<int, int> find_function_range(
    const std::vector<std::string>& lines,
    const std::string& function_signature_fragment) {
  int start = -1;
  int brace_depth = 0;

  for (size_t i = 0; i < lines.size(); ++i) {
    if (start == -1) {
      if (lines[i].find(function_signature_fragment) != std::string::npos) {
        // Find the opening brace (may be on this line or next)
        for (size_t j = i; j < lines.size() && j < i + 5; ++j) {
          if (lines[j].find('{') != std::string::npos) {
            start = static_cast<int>(j);
            // Count braces on this line
            for (char c : lines[j]) {
              if (c == '{') brace_depth++;
              if (c == '}') brace_depth--;
            }
            break;
          }
        }
      }
    } else {
      for (char c : lines[i]) {
        if (c == '{') brace_depth++;
        if (c == '}') brace_depth--;
      }
      if (brace_depth == 0) {
        return {start, static_cast<int>(i)};
      }
    }
  }
  return {-1, -1};
}

bool function_contains(const std::vector<std::string>& lines,
                       int start, int end,
                       const std::string& pattern) {
  for (int i = start; i <= end && i < static_cast<int>(lines.size()); ++i) {
    if (lines[i].find(pattern) != std::string::npos) {
      return true;
    }
  }
  return false;
}

}  // namespace

class SocketCANLoopbackTest : public ::testing::Test {
protected:
  void SetUp() override {
    source_ = read_source("src/socketcan_interface.cpp");
    lines_ = split_lines(source_);

    auto init_range = find_function_range(lines_, "SocketCANInterface::initialize");
    init_start_ = init_range.first;
    init_end_ = init_range.second;

    auto filter_range = find_function_range(lines_, "SocketCANInterface::apply_filters");
    filter_start_ = filter_range.first;
    filter_end_ = filter_range.second;
  }

  std::string source_;
  std::vector<std::string> lines_;
  int init_start_, init_end_;
  int filter_start_, filter_end_;
};

// Scenario: Loopback disabled in initialize
TEST_F(SocketCANLoopbackTest, LoopbackDisabledInInitialize) {
  ASSERT_GE(init_start_, 0) << "Could not find initialize() function";
  ASSERT_GE(init_end_, init_start_) << "Could not find initialize() function end";

  EXPECT_TRUE(function_contains(lines_, init_start_, init_end_, "CAN_RAW_LOOPBACK"))
      << "CAN_RAW_LOOPBACK setsockopt must be in initialize(), not only in apply_filters()";

  EXPECT_TRUE(function_contains(lines_, init_start_, init_end_, "CAN_RAW_RECV_OWN_MSGS"))
      << "CAN_RAW_RECV_OWN_MSGS setsockopt must be in initialize(), not only in apply_filters()";
}

// Scenario: Loopback disabled without filters
// The apply_filters() early return for empty node_ids must NOT gate the loopback disable.
TEST_F(SocketCANLoopbackTest, ApplyFiltersDoesNotGateLoopbackDisable) {
  ASSERT_GE(filter_start_, 0) << "Could not find apply_filters() function";
  ASSERT_GE(filter_end_, filter_start_) << "Could not find apply_filters() function end";

  // After the fix, apply_filters should NOT contain loopback setsockopt calls
  // (they should be in initialize instead)
  EXPECT_FALSE(function_contains(lines_, filter_start_, filter_end_, "CAN_RAW_LOOPBACK"))
      << "CAN_RAW_LOOPBACK should NOT be in apply_filters() — move to initialize()";

  EXPECT_FALSE(function_contains(lines_, filter_start_, filter_end_, "CAN_RAW_RECV_OWN_MSGS"))
      << "CAN_RAW_RECV_OWN_MSGS should NOT be in apply_filters() — move to initialize()";
}

// Verify loopback is set after bind() but before apply_filters() call in initialize()
TEST_F(SocketCANLoopbackTest, LoopbackSetAfterBindBeforeFilters) {
  ASSERT_GE(init_start_, 0) << "Could not find initialize() function";

  int bind_line = -1;
  int loopback_line = -1;
  int apply_filters_line = -1;

  for (int i = init_start_; i <= init_end_; ++i) {
    if (lines_[i].find("bind(socket_fd_") != std::string::npos && bind_line == -1) {
      bind_line = i;
    }
    if (lines_[i].find("CAN_RAW_LOOPBACK") != std::string::npos && loopback_line == -1) {
      loopback_line = i;
    }
    // Find the actual apply_filters() *call* (not comment mentions)
    if (lines_[i].find("apply_filters(") != std::string::npos
        && lines_[i].find("//") == std::string::npos
        && apply_filters_line == -1) {
      apply_filters_line = i;
    }
  }

  ASSERT_GE(bind_line, 0) << "bind() call not found in initialize()";
  ASSERT_GE(loopback_line, 0) << "CAN_RAW_LOOPBACK not found in initialize()";
  ASSERT_GE(apply_filters_line, 0) << "apply_filters() call not found in initialize()";

  EXPECT_GT(loopback_line, bind_line)
      << "CAN_RAW_LOOPBACK (line " << loopback_line + 1
      << ") must come after bind() (line " << bind_line + 1 << ")";

  EXPECT_LT(loopback_line, apply_filters_line)
      << "CAN_RAW_LOOPBACK (line " << loopback_line + 1
      << ") must come before apply_filters() (line " << apply_filters_line + 1 << ")";
}
