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
 * @file test_system_call_safety.cpp
 * @brief Source-verification tests for tech debt item 3.6.
 *
 * Verifies that motion_controller.cpp does NOT contain hardcoded
 * /usr/local/bin/aruco_finder paths (should use ARUCO_FINDER_PROGRAM macro)
 * and does NOT use system() for aruco detection (should use popen()).
 *
 * Pattern reference: test_sleep_annotations.cpp
 */

#include <gtest/gtest.h>
#include <fstream>
#include <string>
#include <sstream>
#include <filesystem>

namespace fs = std::filesystem;

// ═════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═════════════════════════════════════════════════════════════════════════════

/// Read entire file contents into a string.
static std::string readFileContents(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) return "";
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

/// Resolve yanthra_move package root from __FILE__.
static fs::path getPackageRoot() {
    // __FILE__ is .../src/yanthra_move/test/test_system_call_safety.cpp
    return fs::path(__FILE__).parent_path().parent_path();
}

// ═════════════════════════════════════════════════════════════════════════════
// TESTS
// ═════════════════════════════════════════════════════════════════════════════

/// Test: motion_controller.cpp must NOT contain hardcoded "/usr/local/bin/aruco_finder"
/// string literals. The ARUCO_FINDER_PROGRAM macro should be used instead.
/// The macro definition in yanthra_utilities.hpp is allowed.
TEST(SystemCallSafety, NoHardcodedArucoPath) {
    fs::path src_file = getPackageRoot() / "src" / "core" / "motion_controller.cpp";
    ASSERT_TRUE(fs::exists(src_file)) << "Source file not found: " << src_file;

    std::string contents = readFileContents(src_file.string());
    ASSERT_FALSE(contents.empty()) << "Failed to read: " << src_file;

    // The literal path string should NOT appear in motion_controller.cpp
    // (it should use the ARUCO_FINDER_PROGRAM macro instead)
    EXPECT_EQ(contents.find("/usr/local/bin/aruco_finder"), std::string::npos)
        << "motion_controller.cpp still contains hardcoded '/usr/local/bin/aruco_finder' path. "
        << "Use the ARUCO_FINDER_PROGRAM macro from yanthra_utilities.hpp instead.";
}

/// Test: motion_controller.cpp must NOT use system() for aruco detection.
/// popen() should be used instead for safety and proper exit code handling.
TEST(SystemCallSafety, NoSystemCallForAruco) {
    fs::path src_file = getPackageRoot() / "src" / "core" / "motion_controller.cpp";
    ASSERT_TRUE(fs::exists(src_file)) << "Source file not found: " << src_file;

    std::string contents = readFileContents(src_file.string());
    ASSERT_FALSE(contents.empty()) << "Failed to read: " << src_file;

    // system() should not appear in motion_controller.cpp at all
    // (the aruco call should use popen, and there are no other system() calls here)
    EXPECT_EQ(contents.find("system("), std::string::npos)
        << "motion_controller.cpp still uses system() call. "
        << "Replace with popen() for aruco_finder invocation.";
}

/// Test: ARUCO_FINDER_PROGRAM macro must be defined in yanthra_utilities.hpp
TEST(SystemCallSafety, ArucoFinderMacroExists) {
    fs::path header = getPackageRoot() / "include" / "yanthra_move" / "yanthra_utilities.hpp";
    ASSERT_TRUE(fs::exists(header)) << "Header not found: " << header;

    std::string contents = readFileContents(header.string());
    ASSERT_FALSE(contents.empty()) << "Failed to read: " << header;

    EXPECT_NE(contents.find("ARUCO_FINDER_PROGRAM"), std::string::npos)
        << "yanthra_utilities.hpp does not define ARUCO_FINDER_PROGRAM macro.";
}

/// Test: motion_controller.cpp must include yanthra_utilities.hpp
/// so the ARUCO_FINDER_PROGRAM macro is available.
TEST(SystemCallSafety, MotionControllerIncludesUtilities) {
    fs::path src_file = getPackageRoot() / "src" / "core" / "motion_controller.cpp";
    ASSERT_TRUE(fs::exists(src_file)) << "Source file not found: " << src_file;

    std::string contents = readFileContents(src_file.string());
    ASSERT_FALSE(contents.empty()) << "Failed to read: " << src_file;

    EXPECT_NE(contents.find("yanthra_utilities.hpp"), std::string::npos)
        << "motion_controller.cpp does not include yanthra_utilities.hpp. "
        << "The ARUCO_FINDER_PROGRAM macro requires this include.";
}
