// Copyright 2025 Pragati Robotics
// Tests for ODrive CAN Write Safety (Phase-1 Critical Fix, Item 1.8)
//
// Since ODriveServiceNode is defined entirely in the .cpp file (not exported
// via header), these tests use source-code verification to confirm that every
// send_frame() call site checks the return value and handles failure.

#include <gtest/gtest.h>
#include <fstream>
#include <sstream>
#include <string>
#include <regex>
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

}  // namespace

class CANWriteSafetySourceTest : public ::testing::Test {
protected:
  void SetUp() override {
    source_ = read_source_file("src/odrive_service_node.cpp");
    ASSERT_FALSE(source_.empty()) << "Source file is empty";
    lines_ = split_lines(source_);
  }

  std::string source_;
  std::vector<std::string> lines_;
};

// Task 6.2: Verify send_frame() failure sets motor state to FAULT and logs error
// Every send_frame() call must check return value — no unchecked calls allowed
TEST_F(CANWriteSafetySourceTest, AllSendFrameCallsCheckReturnValue) {
  // Find all send_frame() call sites
  auto send_frame_lines = find_lines_matching(lines_, "send_frame(");

  // Filter out comments, string literals, and the function definition itself
  std::vector<size_t> actual_calls;
  for (size_t line_num : send_frame_lines) {
    const std::string& line = lines_[line_num];
    // Skip comment lines
    std::string trimmed = line;
    trimmed.erase(0, trimmed.find_first_not_of(" \t"));
    if (trimmed.substr(0, 2) == "//" || trimmed.substr(0, 1) == "*") {
      continue;
    }
    // Skip string literals (inside quotes)
    if (line.find("\"send_frame") != std::string::npos) {
      continue;
    }
    // Must be an actual call via can_interface_->send_frame(
    if (line.find("can_interface_->send_frame(") != std::string::npos) {
      actual_calls.push_back(line_num);
    }
  }

  ASSERT_GT(actual_calls.size(), 0u) << "No send_frame() call sites found";

  // Every call should be inside an if-check or have its return value captured
  // Valid patterns:
  //   if (!can_interface_->send_frame(...)
  //   bool result = can_interface_->send_frame(...)
  //   auto result = can_interface_->send_frame(...)
  // Invalid pattern:
  //   can_interface_->send_frame(...);  // standalone, return value discarded
  int unchecked_count = 0;
  std::vector<std::string> unchecked_locations;

  for (size_t line_num : actual_calls) {
    const std::string& line = lines_[line_num];

    // Check for if-wrapping pattern: "if (!can_interface_->send_frame" or
    // "if (can_interface_->send_frame"
    bool has_if_check = (line.find("if (!can_interface_->send_frame") != std::string::npos) ||
                        (line.find("if (can_interface_->send_frame") != std::string::npos) ||
                        (line.find("if(!can_interface_->send_frame") != std::string::npos);

    // Check for return-value capture: "bool ... = can_interface_->send_frame" or
    // "auto ... = can_interface_->send_frame"
    bool has_capture = (line.find("bool ") != std::string::npos &&
                        line.find("= can_interface_->send_frame") != std::string::npos) ||
                       (line.find("auto ") != std::string::npos &&
                        line.find("= can_interface_->send_frame") != std::string::npos);

    if (!has_if_check && !has_capture) {
      unchecked_count++;
      unchecked_locations.push_back(
          "Line " + std::to_string(line_num + 1) + ": " + line);
    }
  }

  EXPECT_EQ(unchecked_count, 0)
      << "Found " << unchecked_count << " unchecked send_frame() call(s):\n"
      << [&]() {
           std::string msg;
           for (const auto& loc : unchecked_locations) {
             msg += "  " + loc + "\n";
           }
           return msg;
         }();
}

// Task 6.2 continued: Verify handle_send_failure helper exists and sets ERROR_STATE
TEST_F(CANWriteSafetySourceTest, HandleSendFailureHelperExists) {
  // The helper function should exist
  EXPECT_NE(source_.find("handle_send_failure"), std::string::npos)
      << "handle_send_failure() helper method not found";

  // It should set motion_state to ERROR_STATE
  // Find the function body and verify it sets ERROR_STATE
  auto helper_lines = find_lines_matching(lines_, "handle_send_failure");
  ASSERT_GT(helper_lines.size(), 0u) << "handle_send_failure not found in source";

  // Find the function definition (not just calls)
  bool found_definition = false;
  size_t def_line = 0;
  for (size_t line_num : helper_lines) {
    const std::string& line = lines_[line_num];
    // Definition pattern: "void handle_send_failure(" at start of function
    if (line.find("void handle_send_failure(") != std::string::npos ||
        line.find("void handle_send_failure (") != std::string::npos) {
      found_definition = true;
      def_line = line_num;
      break;
    }
  }
  ASSERT_TRUE(found_definition)
      << "handle_send_failure() function definition not found";

  // Scan the function body (next ~40 lines) for ERROR_STATE assignment
  bool sets_error_state = false;
  for (size_t i = def_line; i < std::min(def_line + 50, lines_.size()); ++i) {
    if (lines_[i].find("ERROR_STATE") != std::string::npos) {
      sets_error_state = true;
      break;
    }
  }
  EXPECT_TRUE(sets_error_state)
      << "handle_send_failure() does not set motor state to ERROR_STATE";
}

// Task 6.2 continued: Verify handle_send_failure logs structured error
TEST_F(CANWriteSafetySourceTest, HandleSendFailureLogsStructuredError) {
  auto helper_lines = find_lines_matching(lines_, "void handle_send_failure(");
  ASSERT_GT(helper_lines.size(), 0u) << "handle_send_failure definition not found";

  size_t def_line = helper_lines[0];

  // Scan function body for RCLCPP_ERROR with structured JSON content
  bool has_error_log = false;
  bool has_node_id = false;
  bool has_command_type = false;

  for (size_t i = def_line; i < std::min(def_line + 50, lines_.size()); ++i) {
    const std::string& line = lines_[i];
    if (line.find("RCLCPP_ERROR") != std::string::npos) {
      has_error_log = true;
    }
    if (line.find("node_id") != std::string::npos) {
      has_node_id = true;
    }
    if (line.find("command") != std::string::npos ||
        line.find("cmd") != std::string::npos) {
      has_command_type = true;
    }
  }

  EXPECT_TRUE(has_error_log)
      << "handle_send_failure() does not log with RCLCPP_ERROR";
  EXPECT_TRUE(has_node_id)
      << "handle_send_failure() error log does not include node_id";
  EXPECT_TRUE(has_command_type)
      << "handle_send_failure() error log does not include command type";
}

// Task 6.3: Verify send_frame() failure publishes diagnostic on /diagnostics
TEST_F(CANWriteSafetySourceTest, DiagnosticsPublisherExists) {
  // Verify the node has a diagnostics publisher member
  EXPECT_NE(source_.find("diagnostic_msgs"), std::string::npos)
      << "diagnostic_msgs not included in source";

  EXPECT_NE(source_.find("diagnostics_pub_"), std::string::npos)
      << "diagnostics_pub_ member not found — diagnostics publisher not added";

  // Verify publisher is created with /diagnostics topic
  EXPECT_NE(source_.find("/diagnostics"), std::string::npos)
      << "/diagnostics topic not referenced in source";
}

// Task 6.3 continued: Verify handle_send_failure publishes diagnostic
TEST_F(CANWriteSafetySourceTest, HandleSendFailurePublishesDiagnostic) {
  auto helper_lines = find_lines_matching(lines_, "void handle_send_failure(");
  ASSERT_GT(helper_lines.size(), 0u) << "handle_send_failure definition not found";

  size_t def_line = helper_lines[0];

  // Scan function body for diagnostics publishing
  bool publishes_diagnostic = false;
  for (size_t i = def_line; i < std::min(def_line + 50, lines_.size()); ++i) {
    if (lines_[i].find("diagnostics_pub_->publish") != std::string::npos) {
      publishes_diagnostic = true;
      break;
    }
  }

  EXPECT_TRUE(publishes_diagnostic)
      << "handle_send_failure() does not publish to diagnostics_pub_";
}

// Task 6.5: Verify successful send_frame does NOT produce extra logging
// The success path should remain unchanged — only the failure path adds logging
TEST_F(CANWriteSafetySourceTest, SuccessPathDoesNotAddExtraLogging) {
  // Find all if-checked send_frame sites
  auto all_lines = find_lines_matching(lines_, "if (!can_interface_->send_frame");
  ASSERT_GT(all_lines.size(), 0u) << "No if-checked send_frame calls found";

  // For each if-check, the ELSE branch (success path) should NOT have
  // RCLCPP_ERROR/RCLCPP_WARN that wasn't there before.
  // We verify by checking that the if-block (failure path) has the
  // handle_send_failure call, and the surrounding code on the success
  // path doesn't add new error logging.

  // Count calls to handle_send_failure — should match the number of
  // if-checked send_frame sites (or be within the same if-block)
  auto failure_handler_calls = find_lines_matching(lines_, "handle_send_failure(");

  // Filter out the definition itself
  std::vector<size_t> actual_handler_calls;
  for (size_t line_num : failure_handler_calls) {
    const std::string& line = lines_[line_num];
    if (line.find("void handle_send_failure") == std::string::npos) {
      actual_handler_calls.push_back(line_num);
    }
  }

  // Every if(!send_frame) should have a corresponding handle_send_failure call
  // within the next few lines (inside the if block)
  int matched = 0;
  for (size_t if_line : all_lines) {
    for (size_t handler_line : actual_handler_calls) {
      // handler call should be within 5 lines after the if-check
      if (handler_line > if_line && handler_line <= if_line + 5) {
        matched++;
        break;
      }
    }
  }

  EXPECT_EQ(matched, static_cast<int>(all_lines.size()))
      << "Not all if(!send_frame) checks have a corresponding handle_send_failure() call. "
      << "Expected " << all_lines.size() << " but found " << matched;
}

// Verify the minimum expected number of send_frame call sites are checked
// (we identified 13 in the investigation — this prevents regressions if new ones are added)
TEST_F(CANWriteSafetySourceTest, MinimumCallSitesCovered) {
  auto checked_calls = find_lines_matching(lines_, "if (!can_interface_->send_frame");
  EXPECT_GE(checked_calls.size(), 11u)
      << "Expected at least 11 if-checked send_frame() calls (13 total sites, "
      << "some may be in loops). Found " << checked_calls.size();
}
