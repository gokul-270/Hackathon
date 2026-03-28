// Copyright 2026 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * @file test_sleep_annotations.cpp
 * @brief Source-verification tests for yanthra_move blocking sleep annotations.
 *
 * Tasks 2.18, 2.19, 2.20 from the blocking-sleep-audit change.
 *
 * All blocking sleeps in yanthra_move are Pattern D (annotation only) because
 * they run on the dedicated main operation thread, not the executor.  These
 * tests verify that every blockingThreadSleep(), std::this_thread::sleep_for(),
 * and usleep() call in the source files carries a BLOCKING_SLEEP_OK annotation
 * on the same line or the preceding line.
 *
 * Pattern reference: motor_control_ros2/test/test_watchdog_exempt_flag.cpp
 *
 * Additionally, Task 2.20 verifies parameter fallback values are documented
 * in the loadJointLimits() catch blocks of motion_controller.cpp.
 */

#include <gtest/gtest.h>
#include <fstream>
#include <string>
#include <sstream>
#include <vector>
#include <filesystem>

namespace fs = std::filesystem;

// ═════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═════════════════════════════════════════════════════════════════════════════

/// Information about a sleep call that is missing its BLOCKING_SLEEP_OK annotation.
struct UnannotatedSleep {
    std::string file;
    int line;
    std::string content;
};

/// Resolve the yanthra_move/src/ directory from __FILE__.
static std::string getSourceDir() {
    // __FILE__ is something like .../src/yanthra_move/test/test_sleep_annotations.cpp
    fs::path test_file(__FILE__);
    return (test_file.parent_path().parent_path() / "src").string();
}

/// Resolve the yanthra_move/include/ directory from __FILE__.
static std::string getIncludeDir() {
    fs::path test_file(__FILE__);
    return (test_file.parent_path().parent_path() / "include").string();
}

/// Read all lines from a file, returning them as a vector.
static std::vector<std::string> readLines(const std::string& path) {
    std::vector<std::string> lines;
    std::ifstream f(path);
    if (!f.is_open()) return lines;
    std::string line;
    while (std::getline(f, line)) {
        lines.push_back(line);
    }
    return lines;
}

/// Check if a line contains a sleep call (not just a comment defining one).
static bool lineHasSleepCall(const std::string& line) {
    // Skip pure comment lines (starting with //)
    auto trimmed = line;
    auto first_non_space = trimmed.find_first_not_of(" \t");
    if (first_non_space != std::string::npos && trimmed.substr(first_non_space, 2) == "//") {
        return false;
    }

    return (line.find("blockingThreadSleep") != std::string::npos ||
            line.find("sleep_for") != std::string::npos ||
            line.find("usleep") != std::string::npos);
}

/// Check if a line is a function definition/declaration (not a call).
static bool lineIsDefinition(const std::string& line) {
    return (line.find("void blockingThreadSleep") != std::string::npos ||
            line.find("inline void") != std::string::npos);
}

/// Check if the line is inside a Doxygen/block comment (e.g., " *  ...sleep_for...")
static bool lineIsDocComment(const std::string& line) {
    auto trimmed = line;
    auto first_non_space = trimmed.find_first_not_of(" \t");
    if (first_non_space == std::string::npos) return false;
    // Lines starting with * (inside /** ... */ block comments)
    if (trimmed[first_non_space] == '*') return true;
    return false;
}

/// Check if a sleep call is inside the blockingThreadSleep function body.
/// Detected by checking if the preceding context defines the function.
static bool isInsideBlockingThreadSleepBody(const std::vector<std::string>& lines, size_t idx) {
    // Look backward up to 5 lines for the function signature
    for (size_t back = 1; back <= 5 && idx >= back; ++back) {
        if (lines[idx - back].find("void blockingThreadSleep") != std::string::npos) {
            return true;
        }
    }
    return false;
}

/// Scan a single file for unannotated sleep calls.
/// Returns all sleep call lines that do NOT have BLOCKING_SLEEP_OK on the
/// same line or the immediately preceding line.
static std::vector<UnannotatedSleep> findUnannotatedSleepsInFile(const std::string& path) {
    std::vector<UnannotatedSleep> results;
    auto lines = readLines(path);
    if (lines.empty()) return results;

    std::string prev_line;
    for (size_t i = 0; i < lines.size(); ++i) {
        const auto& line = lines[i];
        int line_num = static_cast<int>(i + 1);

        if (lineHasSleepCall(line) && !lineIsDefinition(line) && !lineIsDocComment(line)) {
            // Skip sleep_for inside the blockingThreadSleep() function body
            // (it IS the implementation, not a call site)
            if (isInsideBlockingThreadSleepBody(lines, i)) {
                prev_line = line;
                continue;
            }

            bool annotated = (line.find("BLOCKING_SLEEP_OK") != std::string::npos ||
                             prev_line.find("BLOCKING_SLEEP_OK") != std::string::npos);
            if (!annotated) {
                results.push_back({path, line_num, line});
            }
        }
        prev_line = line;
    }
    return results;
}

/// Scan a directory recursively for unannotated sleep calls in .cpp/.hpp files.
/// Skips files under /test/ directories.
static std::vector<UnannotatedSleep> findUnannotatedSleeps(const std::string& dir) {
    std::vector<UnannotatedSleep> results;
    if (!fs::exists(dir)) return results;

    for (auto& entry : fs::recursive_directory_iterator(dir)) {
        if (!entry.is_regular_file()) continue;
        auto ext = entry.path().extension().string();
        if (ext != ".cpp" && ext != ".hpp") continue;

        // Skip test files
        if (entry.path().string().find("/test/") != std::string::npos) continue;

        auto file_results = findUnannotatedSleepsInFile(entry.path().string());
        results.insert(results.end(), file_results.begin(), file_results.end());
    }
    return results;
}

/// Format unannotated sleep results for readable test failure output.
static std::string formatResults(const std::vector<UnannotatedSleep>& results) {
    std::ostringstream ss;
    ss << results.size() << " unannotated sleep call(s) found:\n";
    for (const auto& r : results) {
        // Show path relative to yanthra_move for readability
        auto rel = r.file;
        auto pos = rel.find("yanthra_move/");
        if (pos != std::string::npos) {
            rel = rel.substr(pos);
        }
        ss << "  " << rel << ":" << r.line << ": " << r.content << "\n";
    }
    return ss.str();
}

// ═════════════════════════════════════════════════════════════════════════════
// Task 2.18: Sleep annotation tests for motion_controller.cpp,
//            trajectory_executor.cpp, and all other source files
// ═════════════════════════════════════════════════════════════════════════════

class SleepAnnotationTest : public ::testing::Test {};

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInMotionController) {
    std::string path = getSourceDir() + "/core/motion_controller.cpp";
    ASSERT_TRUE(fs::exists(path))
        << "Cannot find source file: " << path;

    auto results = findUnannotatedSleepsInFile(path);
    EXPECT_EQ(results.size(), 0u) << formatResults(results);
}

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInTrajectoryExecutor) {
    std::string path = getSourceDir() + "/core/trajectory_executor.cpp";
    ASSERT_TRUE(fs::exists(path))
        << "Cannot find source file: " << path;

    auto results = findUnannotatedSleepsInFile(path);
    EXPECT_EQ(results.size(), 0u) << formatResults(results);
}

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInOtherFiles) {
    // Check ALL .cpp files under src/ except the two already tested above
    // and except test files
    std::string src_dir = getSourceDir();
    ASSERT_TRUE(fs::exists(src_dir))
        << "Cannot find source directory: " << src_dir;

    std::vector<UnannotatedSleep> all_results;
    for (auto& entry : fs::recursive_directory_iterator(src_dir)) {
        if (!entry.is_regular_file()) continue;
        auto ext = entry.path().extension().string();
        if (ext != ".cpp" && ext != ".hpp") continue;
        if (entry.path().string().find("/test/") != std::string::npos) continue;

        // Skip the two files tested individually above
        auto filename = entry.path().filename().string();
        if (filename == "motion_controller.cpp" || filename == "trajectory_executor.cpp") {
            continue;
        }

        auto file_results = findUnannotatedSleepsInFile(entry.path().string());
        all_results.insert(all_results.end(), file_results.begin(), file_results.end());
    }

    EXPECT_EQ(all_results.size(), 0u) << formatResults(all_results);
}

// ═════════════════════════════════════════════════════════════════════════════
// Task 2.19: Sleep annotation test for joint_move.cpp
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInJointMove) {
    std::string path = getSourceDir() + "/joint_move.cpp";
    ASSERT_TRUE(fs::exists(path))
        << "Cannot find source file: " << path;

    auto results = findUnannotatedSleepsInFile(path);
    EXPECT_EQ(results.size(), 0u) << formatResults(results);
}

// ═════════════════════════════════════════════════════════════════════════════
// Also check header files under include/
// ═════════════════════════════════════════════════════════════════════════════

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInHeaders) {
    std::string include_dir = getIncludeDir();
    if (!fs::exists(include_dir)) {
        // No headers with sleeps is fine
        SUCCEED() << "Include directory not found (ok if no headers have sleep calls)";
        return;
    }

    auto results = findUnannotatedSleeps(include_dir);
    EXPECT_EQ(results.size(), 0u) << formatResults(results);
}

// ═════════════════════════════════════════════════════════════════════════════
// Task 2.20: Parameter fallback value verification (source-verification)
//
// Verifies that the catch blocks in loadJointLimits() log the fallback values
// matching the header defaults. This ensures the safety-critical fallbacks
// are documented in structured log messages.
// ═════════════════════════════════════════════════════════════════════════════

class ParameterFallbackTest : public ::testing::Test {
protected:
    std::vector<std::string> mc_lines_;

    void SetUp() override {
        std::string path = getSourceDir() + "/core/motion_controller.cpp";
        mc_lines_ = readLines(path);
        ASSERT_GT(mc_lines_.size(), 100u)
            << "motion_controller.cpp too small or not found";
    }

    /// Find line number (0-indexed) containing pattern, starting from `start`.
    int findLine(const std::string& pattern, int start = 0) const {
        for (int i = start; i < static_cast<int>(mc_lines_.size()); ++i) {
            if (mc_lines_[i].find(pattern) != std::string::npos) {
                return i;
            }
        }
        return -1;
    }

    /// Check if any line in range [start, end) contains the pattern.
    bool rangeContains(const std::string& pattern, int start, int end) const {
        for (int i = start; i < end && i < static_cast<int>(mc_lines_.size()); ++i) {
            if (mc_lines_[i].find(pattern) != std::string::npos) {
                return true;
            }
        }
        return false;
    }
};

// Verify that the packing_positions catch block logs the fallback value.
// Header default: joint3_parking_position_ = 0.008
TEST_F(ParameterFallbackTest, PackingPositionFallbackDocumented) {
    // Find the JSON log line inside the catch block (uses C-escaped quotes in source).
    // The get_parameter call is ~13 lines before the catch block's JSON log, so
    // we search for the JSON format string directly rather than starting from
    // the get_parameter call.
    int json_log_line = findLine("\\\"parameter\\\":\\\"packing_positions\\\"");
    ASSERT_NE(json_log_line, -1)
        << "Could not find packing_positions JSON log in motion_controller.cpp";

    // The JSON log should contain the fallback format string nearby
    EXPECT_TRUE(rangeContains("fallback", json_log_line - 3, json_log_line + 3))
        << "packing_positions catch block does not log fallback value "
        << "(expected 'fallback' near line " << (json_log_line + 1) << ")";
}

// Verify that the position_tolerance catch block logs all 3 fallback values.
// Header defaults: joint3=0.05, joint4=0.005, joint5=0.005
TEST_F(ParameterFallbackTest, PositionToleranceFallbackDocumented) {
    // Find the catch block for position_tolerance parameter.
    // Source uses C-escaped quotes: "\"parameter\":\"position_tolerance\","
    int catch_line = findLine("\\\"parameter\\\":\\\"position_tolerance\\\"");
    ASSERT_NE(catch_line, -1)
        << "Could not find position_tolerance catch block in motion_controller.cpp";

    // The JSON log should contain all three fallback values
    EXPECT_TRUE(rangeContains("fallback_j3", catch_line - 5, catch_line + 5))
        << "position_tolerance catch block does not log J3 fallback";
    EXPECT_TRUE(rangeContains("fallback_j4", catch_line - 5, catch_line + 5))
        << "position_tolerance catch block does not log J4 fallback";
    EXPECT_TRUE(rangeContains("fallback_j5", catch_line - 5, catch_line + 5))
        << "position_tolerance catch block does not log J5 fallback";
}

// Verify that the short-array warning also logs fallback values.
// This is the non-exception path: when the array is too short.
TEST_F(ParameterFallbackTest, PositionToleranceShortArrayWarningDocumented) {
    // Find the warning for short position_tolerance array
    int warn_line = findLine("position_tolerance array too short");
    ASSERT_NE(warn_line, -1)
        << "Could not find short-array warning for position_tolerance";

    // The warning format string should include the defaults inline
    // e.g., "using defaults: J3=%.4f, J4=%.4f, J5=%.4f"
    EXPECT_TRUE(rangeContains("using defaults", warn_line, warn_line + 1))
        << "Short-array warning does not mention 'using defaults'";
}

// Verify that the loadJointLimits function tracks parameter failures.
// Each catch block should increment param_load_failure_count_.
TEST_F(ParameterFallbackTest, ParameterFailureCountTracked) {
    // Find the loadJointLimits function
    int func_start = findLine("bool MotionController::loadJointLimits()");
    ASSERT_NE(func_start, -1)
        << "Could not find loadJointLimits() in motion_controller.cpp";

    // Count how many catch blocks increment param_load_failure_count_
    int increment_count = 0;
    for (int i = func_start; i < static_cast<int>(mc_lines_.size()) && i < func_start + 300; ++i) {
        if (mc_lines_[i].find("param_load_failure_count_++") != std::string::npos) {
            increment_count++;
        }
    }

    // There should be at least 2 catch blocks that track failures
    // (packing_positions and position_tolerance)
    EXPECT_GE(increment_count, 2)
        << "Expected at least 2 param_load_failure_count_ increments in loadJointLimits(), found "
        << increment_count;
}
