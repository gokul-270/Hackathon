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
 * @file test_dead_global_removal.cpp
 * @brief Source-verification tests for dead global char buffer removal.
 *
 * Tech debt item 4.2 (partial): Verifies that the dead global char[512]
 * arrays PRAGATI_INPUT_DIR and PRAGATI_OUTPUT_DIR have been removed from
 * production code, along with their unsafe sprintf writes and unused
 * setenv calls.
 *
 * These globals were written but never read by any active production code.
 * The only reader was archived legacy code (yanthra_move_aruco_detect.cpp).
 *
 * Pattern reference: test_sleep_annotations.cpp (source-verification via
 * __FILE__, std::ifstream, std::string::find).
 */

#include <gtest/gtest.h>
#include <fstream>
#include <string>
#include <filesystem>

namespace fs = std::filesystem;

// ═════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═════════════════════════════════════════════════════════════════════════════

/// Read entire file contents into a single string.
static std::string readFileContents(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) return "";
    return std::string(
        (std::istreambuf_iterator<char>(f)),
        std::istreambuf_iterator<char>()
    );
}

/// Resolve the yanthra_move/src/ directory from __FILE__.
static std::string getSourceDir() {
    // __FILE__ is .../src/yanthra_move/test/test_dead_global_removal.cpp
    fs::path test_file(__FILE__);
    return (test_file.parent_path().parent_path() / "src").string();
}

/// Resolve the yanthra_move/include/ directory from __FILE__.
static std::string getIncludeDir() {
    fs::path test_file(__FILE__);
    return (test_file.parent_path().parent_path() / "include").string();
}

// ═════════════════════════════════════════════════════════════════════════════
// TEST CASES
// ═════════════════════════════════════════════════════════════════════════════

class DeadGlobalRemovalTest : public ::testing::Test {};

/// Verify that char PRAGATI_INPUT_DIR[] and char PRAGATI_OUTPUT_DIR[] global
/// definitions and extern declarations do NOT appear in yanthra_move_system_core.cpp.
TEST_F(DeadGlobalRemovalTest, NoPragatiDirCharArrays) {
    std::string path = getSourceDir() + "/yanthra_move_system_core.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find source file: " << path;

    std::string content = readFileContents(path);
    ASSERT_FALSE(content.empty()) << "File is empty: " << path;

    EXPECT_EQ(content.find("char PRAGATI_INPUT_DIR"), std::string::npos)
        << "Dead global 'char PRAGATI_INPUT_DIR' still present in "
        << "yanthra_move_system_core.cpp — should be removed";

    EXPECT_EQ(content.find("char PRAGATI_OUTPUT_DIR"), std::string::npos)
        << "Dead global 'char PRAGATI_OUTPUT_DIR' still present in "
        << "yanthra_move_system_core.cpp — should be removed";
}

/// Verify that sprintf(PRAGATI_INPUT_DIR, ...) and sprintf(PRAGATI_OUTPUT_DIR, ...)
/// do NOT appear in yanthra_move_system_parameters.cpp.
TEST_F(DeadGlobalRemovalTest, NoSprintfToGlobalBuffers) {
    std::string path = getSourceDir() + "/yanthra_move_system_parameters.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find source file: " << path;

    std::string content = readFileContents(path);
    ASSERT_FALSE(content.empty()) << "File is empty: " << path;

    EXPECT_EQ(content.find("sprintf(PRAGATI_INPUT_DIR"), std::string::npos)
        << "Dead sprintf to PRAGATI_INPUT_DIR still present in "
        << "yanthra_move_system_parameters.cpp — should be removed";

    EXPECT_EQ(content.find("sprintf(PRAGATI_OUTPUT_DIR"), std::string::npos)
        << "Dead sprintf to PRAGATI_OUTPUT_DIR still present in "
        << "yanthra_move_system_parameters.cpp — should be removed";
}

/// Verify that setenv("PRAGATI_INPUT_DIR", ...) and setenv("PRAGATI_OUTPUT_DIR", ...)
/// do NOT appear in yanthra_move_system_parameters.cpp.
TEST_F(DeadGlobalRemovalTest, NoSetenvForPragatiDirs) {
    std::string path = getSourceDir() + "/yanthra_move_system_parameters.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find source file: " << path;

    std::string content = readFileContents(path);
    ASSERT_FALSE(content.empty()) << "File is empty: " << path;

    EXPECT_EQ(content.find("setenv(\"PRAGATI_INPUT_DIR\""), std::string::npos)
        << "Dead setenv for PRAGATI_INPUT_DIR still present in "
        << "yanthra_move_system_parameters.cpp — should be removed";

    EXPECT_EQ(content.find("setenv(\"PRAGATI_OUTPUT_DIR\""), std::string::npos)
        << "Dead setenv for PRAGATI_OUTPUT_DIR still present in "
        << "yanthra_move_system_parameters.cpp — should be removed";
}

/// Verify that the std::string class members pragati_input_dir_ and
/// pragati_output_dir_ still exist in the header — we removed globals, not members.
TEST_F(DeadGlobalRemovalTest, ClassMembersStillExist) {
    std::string path = getIncludeDir() + "/yanthra_move/yanthra_move_system.hpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find header file: " << path;

    std::string content = readFileContents(path);
    ASSERT_FALSE(content.empty()) << "File is empty: " << path;

    EXPECT_NE(content.find("pragati_input_dir_"), std::string::npos)
        << "Class member 'pragati_input_dir_' missing from header — "
        << "only the global char arrays should be removed, not the std::string members";

    EXPECT_NE(content.find("pragati_output_dir_"), std::string::npos)
        << "Class member 'pragati_output_dir_' missing from header — "
        << "only the global char arrays should be removed, not the std::string members";
}
