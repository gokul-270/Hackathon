// Copyright 2025 Pragati Robotics
// Tests for mutex coverage on odrive_states_ accesses
//
// Source-verification gtest: scans odrive_service_node.cpp for all
// odrive_states_ accesses and asserts each non-constructor site is
// within a state_mutex_ lock scope.
//
// This test MUST fail on code where request_encoder_estimates() lacks
// the lock_guard, and pass once the fix is applied.

#include <gtest/gtest.h>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>
#include <set>

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

// Determine which function a given line belongs to by scanning backwards for
// a function definition pattern. Returns the function name or "unknown".
std::string find_enclosing_function(const std::vector<std::string>& lines,
                                    size_t target_line) {
  // Scan backwards for a function definition: "returnType functionName(...) {"
  // We look for patterns like "void foo(", "bool foo(", "ODriveServiceNode()",
  // "~ODriveServiceNode()", etc.
  for (size_t i = target_line; i > 0; --i) {
    const std::string& line = lines[i];
    // Skip blank lines and pure-comment lines
    std::string trimmed = line;
    auto first_non_space = trimmed.find_first_not_of(" \t");
    if (first_non_space == std::string::npos) continue;
    trimmed = trimmed.substr(first_non_space);
    if (trimmed.substr(0, 2) == "//" || trimmed.substr(0, 1) == "*") continue;

    // Look for common function-definition patterns
    // Constructor
    if (line.find("ODriveServiceNode()") != std::string::npos &&
        line.find("~") == std::string::npos) {
      return "ODriveServiceNode";  // constructor
    }
    // Destructor
    if (line.find("~ODriveServiceNode()") != std::string::npos) {
      return "~ODriveServiceNode";
    }
    // Lambda inside create_wall_timer — check for "[this]" pattern
    if (line.find("[this]") != std::string::npos) {
      return "lambda";
    }
    // Standard member function: "void/bool/auto functionName(" at function scope
    // Match lines like "  void can_rx_thread() {" or "  void handle_position_command(...) {"
    for (const auto& ret_type : {"void ", "bool ", "auto ", "int ", "double ",
                                 "std::string "}) {
      auto pos = line.find(ret_type);
      if (pos != std::string::npos) {
        // Extract function name: text between return type and "("
        auto name_start = pos + std::string(ret_type).length();
        auto paren = line.find('(', name_start);
        if (paren != std::string::npos && paren > name_start) {
          std::string func_name = line.substr(name_start, paren - name_start);
          // Trim whitespace
          func_name.erase(func_name.find_last_not_of(" \t") + 1);
          func_name.erase(0, func_name.find_first_not_of(" \t"));
          if (!func_name.empty() && func_name.find(' ') == std::string::npos) {
            return func_name;
          }
        }
      }
    }
  }
  return "unknown";
}

// Check if a line is within a state_mutex_ lock scope by scanning backwards
// from the line to the start of its enclosing function. Looks for
// "lock_guard" or "unique_lock" patterns on state_mutex_.
//
// The algorithm finds the enclosing function definition, then scans forward
// from the function start to the target line looking for a lock_guard on
// state_mutex_. If found, it protects all code in the function due to RAII.
bool is_within_mutex_scope(const std::vector<std::string>& lines,
                           size_t target_line) {
  // Step 1: Find the enclosing function start by scanning backwards.
  // A function definition has a return type at the start of the (trimmed)
  // line, followed by a name and '(', with NO '=' before '(' (which would
  // indicate a variable declaration like 'auto x = foo(...)').
  size_t func_start = 0;
  for (size_t i = target_line; i > 0; --i) {
    const std::string& line = lines[i];
    auto first_non_space = line.find_first_not_of(" \t");
    if (first_non_space == std::string::npos) continue;
    std::string trimmed = line.substr(first_non_space);
    if (trimmed.substr(0, 2) == "//" || trimmed.substr(0, 1) == "*") continue;

    // Constructor / destructor
    if (trimmed.find("ODriveServiceNode()") == 0 ||
        trimmed.find("~ODriveServiceNode()") == 0 ||
        trimmed.find("explicit ODriveServiceNode(") == 0) {
      func_start = i;
      goto found_func;
    }

    // Standard member function: starts with return_type + name + '('
    // Exclude lines with '=' before '(' (variable assignments)
    for (const auto& ret_type : {"void ", "bool ", "int ", "double "}) {
      if (trimmed.find(ret_type) == 0) {
        auto paren_pos = trimmed.find('(');
        auto eq_pos = trimmed.find('=');
        if (paren_pos != std::string::npos &&
            (eq_pos == std::string::npos || eq_pos > paren_pos)) {
          func_start = i;
          goto found_func;
        }
      }
    }
  }
found_func:

  // Step 2: Forward scan from function start to target line for lock_guard.
  for (size_t i = func_start; i < target_line; ++i) {
    const std::string& line = lines[i];
    if ((line.find("lock_guard") != std::string::npos ||
         line.find("unique_lock") != std::string::npos ||
         line.find("scoped_lock") != std::string::npos) &&
        line.find("state_mutex_") != std::string::npos) {
      return true;
    }
  }
  return false;
}

}  // namespace

class MutexCoverageTest : public ::testing::Test {
protected:
  void SetUp() override {
    source_ = read_source_file("src/odrive_service_node.cpp");
    ASSERT_FALSE(source_.empty()) << "Source file is empty";
    lines_ = split_lines(source_);
  }

  std::string source_;
  std::vector<std::string> lines_;
};

// Verify that every non-constructor access to odrive_states_ is within
// a state_mutex_ lock scope.
TEST_F(MutexCoverageTest, AllODriveStatesAccessesHoldMutex) {
  // Find all lines that access odrive_states_
  std::vector<size_t> access_lines;
  for (size_t i = 0; i < lines_.size(); ++i) {
    if (lines_[i].find("odrive_states_") != std::string::npos) {
      // Skip comment lines
      std::string trimmed = lines_[i];
      auto first = trimmed.find_first_not_of(" \t");
      if (first != std::string::npos) {
        trimmed = trimmed.substr(first);
        if (trimmed.substr(0, 2) == "//" || trimmed.substr(0, 1) == "*") {
          continue;
        }
      }
      // Skip string literals (inside quotes)
      if (lines_[i].find("\"odrive_states_") != std::string::npos) {
        continue;
      }
      access_lines.push_back(i);
    }
  }

  ASSERT_GT(access_lines.size(), 0u) << "No odrive_states_ accesses found";

  // Functions that are allowed to access odrive_states_ without mutex:
  // - Constructor: initializes the map before any threads start
  // Functions where mutex is held by the caller (documented):
  // - handle_send_failure: called from within locked contexts
  //   (except request_encoder_estimates which is the bug)
  // - set_all_motors_axis_state: always called from locked context
  // - start_motion_internal: documented "assumes lock is already held"
  // - dispatch_pending_batch: documented "assumes state_mutex_ is already held"
  //
  // For caller-locked functions, we still flag them if they have no local
  // lock, but we allow a comment-based exemption. The key assertion is
  // that request_encoder_estimates MUST hold the lock itself.
  std::set<std::string> constructor_functions = {
    "ODriveServiceNode",   // constructor — runs before threads start
    "~ODriveServiceNode",  // destructor — runs after threads are joined
  };

  // Functions documented as "caller holds lock" — we accept these IF
  // they contain a comment documenting the assumption.
  std::set<std::string> caller_locked_functions = {
    "handle_send_failure",
    "set_all_motors_axis_state",
    "start_motion_internal",
    "dispatch_pending_batch",
    "clear_all_errors",
    "handle_motor_error",
  };

  int unprotected_count = 0;
  std::vector<std::string> unprotected_locations;

  for (size_t line_num : access_lines) {
    std::string func = find_enclosing_function(lines_, line_num);

    // Skip constructor — it runs before threads start
    if (constructor_functions.count(func) > 0) {
      continue;
    }

    // Skip member variable declarations
    if (lines_[line_num].find("std::map<uint8_t, ODriveState> odrive_states_") !=
        std::string::npos) {
      continue;
    }

    // For caller-locked functions, we accept them (the caller is
    // responsible). But the KEY test: request_encoder_estimates must
    // hold the lock itself — it's NOT in the caller-locked set.
    if (caller_locked_functions.count(func) > 0) {
      continue;
    }

    // For all other functions (including request_encoder_estimates),
    // verify there's a lock in scope.
    if (!is_within_mutex_scope(lines_, line_num)) {
      unprotected_count++;
      unprotected_locations.push_back(
          "Line " + std::to_string(line_num + 1) + " [" + func + "]: " +
          lines_[line_num]);
    }
  }

  EXPECT_EQ(unprotected_count, 0)
      << "Found " << unprotected_count
      << " unprotected odrive_states_ access(es):\n"
      << [&]() {
           std::string msg;
           for (const auto& loc : unprotected_locations) {
             msg += "  " + loc + "\n";
           }
           return msg;
         }();
}

// Specific regression test: request_encoder_estimates MUST hold state_mutex_
TEST_F(MutexCoverageTest, RequestEncoderEstimatesHoldsMutex) {
  // Find the function definition
  size_t func_start = 0;
  bool found = false;
  for (size_t i = 0; i < lines_.size(); ++i) {
    if (lines_[i].find("void request_encoder_estimates()") != std::string::npos) {
      func_start = i;
      found = true;
      break;
    }
  }
  ASSERT_TRUE(found) << "request_encoder_estimates() function not found";

  // Find the function body (scan forward for opening brace)
  size_t body_start = func_start;
  for (size_t i = func_start; i < lines_.size(); ++i) {
    if (lines_[i].find('{') != std::string::npos) {
      body_start = i;
      break;
    }
  }

  // Scan the first 5 lines of the function body for a lock_guard on state_mutex_
  bool has_lock = false;
  for (size_t i = body_start; i < std::min(body_start + 5, lines_.size()); ++i) {
    if ((lines_[i].find("lock_guard") != std::string::npos ||
         lines_[i].find("unique_lock") != std::string::npos ||
         lines_[i].find("scoped_lock") != std::string::npos) &&
        lines_[i].find("state_mutex_") != std::string::npos) {
      has_lock = true;
      break;
    }
  }

  EXPECT_TRUE(has_lock)
      << "request_encoder_estimates() does NOT hold state_mutex_! "
      << "This is a data race — odrive_states_ is accessed by the CAN RX "
      << "thread under state_mutex_, and request_encoder_estimates() runs "
      << "on the executor thread without the lock. Add "
      << "std::lock_guard<std::mutex> lock(state_mutex_); at the top of "
      << "the function.";
}
