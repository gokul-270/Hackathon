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
 * @file test_blocking_sleep_audit.cpp
 * @brief Source-verification tests for cotton_detection_ros2 blocking sleep audit.
 *
 * Tasks 3.16, 3.17, 3.17b, 3.18, 3.19 from the blocking-sleeps-error-handlers change.
 *
 * All blocking sleeps in cotton_detection_ros2 are on executor threads (Pattern A
 * context) but per design decision were annotated rather than structurally refactored.
 * These tests verify:
 *
 *   3.16: camera_error_ member and isCameraInError() exist in the header
 *   3.17/3.17b: Every sleep call has a BLOCKING_SLEEP_OK annotation
 *   3.18: pauseCamera() propagates teardown failure (returns false, sets Error state)
 *   3.19: Every catch(...) in depthai_manager.cpp has a typed catch preceding it
 *         (except in destructors where catch-all is correct)
 *
 * Pattern reference: yanthra_move/test/test_sleep_annotations.cpp
 */

#include <gtest/gtest.h>
#include <fstream>
#include <string>
#include <sstream>
#include <vector>
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;

// ═════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═════════════════════════════════════════════════════════════════════════════

/// Information about a source issue found during verification.
struct SourceIssue {
    std::string file;
    int line;
    std::string content;
};

/// Resolve the cotton_detection_ros2 package root from SOURCE_DIR compile definition.
static std::string getPackageRoot() {
#ifdef SOURCE_DIR
    return SOURCE_DIR;
#else
    // Fallback: derive from __FILE__
    fs::path test_file(__FILE__);
    return test_file.parent_path().parent_path().string();
#endif
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

/// Read entire file as a single string.
static std::string readFile(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) return {};
    std::ostringstream oss;
    oss << f.rdbuf();
    return oss.str();
}

/// Check if a line contains a sleep call (not inside a comment or preprocessor directive).
static bool lineHasSleepCall(const std::string& line) {
    // Skip pure comment lines
    auto first_non_space = line.find_first_not_of(" \t");
    if (first_non_space != std::string::npos && line.substr(first_non_space, 2) == "//") {
        return false;
    }
    // Skip lines inside block comments (starting with *)
    if (first_non_space != std::string::npos && line[first_non_space] == '*') {
        return false;
    }
    // Skip preprocessor directives (#include, #define, etc.) — these are not sleep calls
    if (first_non_space != std::string::npos && line[first_non_space] == '#') {
        return false;
    }

    return (line.find("blockingThreadSleep") != std::string::npos ||
            line.find("sleep_for") != std::string::npos ||
            line.find("usleep") != std::string::npos);
}

/// Check if a line is a function definition/declaration (not a call site).
static bool lineIsDefinition(const std::string& line) {
    return (line.find("void blockingThreadSleep") != std::string::npos ||
            line.find("inline void") != std::string::npos);
}

/// Find line number (0-indexed) containing pattern, starting from `start`.
static int findLine(const std::vector<std::string>& lines, const std::string& pattern, int start = 0) {
    for (int i = start; i < static_cast<int>(lines.size()); ++i) {
        if (lines[i].find(pattern) != std::string::npos) {
            return i;
        }
    }
    return -1;
}

/// Check if any line in range [start, end) contains the pattern.
static bool rangeContains(const std::vector<std::string>& lines, const std::string& pattern,
                          int start, int end) {
    for (int i = std::max(0, start); i < std::min(end, static_cast<int>(lines.size())); ++i) {
        if (lines[i].find(pattern) != std::string::npos) {
            return true;
        }
    }
    return false;
}

/// Format source issues for readable test failure output.
static std::string formatIssues(const std::string& description,
                                const std::vector<SourceIssue>& issues) {
    std::ostringstream ss;
    ss << description << ": " << issues.size() << " issue(s) found:\n";
    for (const auto& issue : issues) {
        // Show relative path
        auto rel = issue.file;
        auto pos = rel.find("cotton_detection_ros2/");
        if (pos != std::string::npos) {
            rel = rel.substr(pos);
        }
        ss << "  " << rel << ":" << issue.line << ": " << issue.content << "\n";
    }
    return ss.str();
}

// ═════════════════════════════════════════════════════════════════════════════
// Task 3.16: camera_error_ state tracking verification
//
// Verifies that cotton_detection_node.hpp declares camera_error_ and
// isCameraInError(), and that cotton_detection_node.cpp sets camera_error_
// on resume/reinit failures.
// ═════════════════════════════════════════════════════════════════════════════

class CameraErrorStateTest : public ::testing::Test {
protected:
    std::string pkg_root_;
    void SetUp() override { pkg_root_ = getPackageRoot(); }
};

TEST_F(CameraErrorStateTest, HeaderDeclaresCameraErrorMember) {
    std::string hpp = readFile(
        pkg_root_ + "/include/cotton_detection_ros2/cotton_detection_node.hpp");
    ASSERT_FALSE(hpp.empty()) << "Could not read cotton_detection_node.hpp";

    EXPECT_NE(hpp.find("camera_error_"), std::string::npos)
        << "Header must declare camera_error_ member";

    EXPECT_NE(hpp.find("isCameraInError"), std::string::npos)
        << "Header must declare isCameraInError() method";
}

TEST_F(CameraErrorStateTest, NodeSetsErrorOnResumeCameraFailure) {
    auto lines = readLines(pkg_root_ + "/src/cotton_detection_node.cpp");
    ASSERT_FALSE(lines.empty()) << "Could not read cotton_detection_node.cpp";

    // resumeCamera failures should set camera_error_ = true
    // Search for catch blocks in thermal_check_callback that set the flag
    bool found_error_set = false;
    for (size_t i = 0; i < lines.size(); ++i) {
        if (lines[i].find("camera_error_") != std::string::npos &&
            lines[i].find("true") != std::string::npos) {
            found_error_set = true;
            break;
        }
    }
    EXPECT_TRUE(found_error_set)
        << "cotton_detection_node.cpp must set camera_error_ = true on resume/reinit failure";
}

TEST_F(CameraErrorStateTest, NodeClearsErrorOnReconnectSuccess) {
    auto lines = readLines(pkg_root_ + "/src/cotton_detection_node.cpp");
    ASSERT_FALSE(lines.empty()) << "Could not read cotton_detection_node.cpp";

    // After successful reconnect, camera_error_ should be cleared
    bool found_error_clear = false;
    for (size_t i = 0; i < lines.size(); ++i) {
        if (lines[i].find("camera_error_") != std::string::npos &&
            lines[i].find("false") != std::string::npos) {
            found_error_clear = true;
            break;
        }
    }
    EXPECT_TRUE(found_error_clear)
        << "cotton_detection_node.cpp must clear camera_error_ = false on reconnect success";
}

TEST_F(CameraErrorStateTest, ConsecutiveFrameDropsTracked) {
    std::string hpp = readFile(
        pkg_root_ + "/include/cotton_detection_ros2/cotton_detection_node.hpp");
    ASSERT_FALSE(hpp.empty()) << "Could not read cotton_detection_node.hpp";

    EXPECT_NE(hpp.find("consecutive_frame_drops_"), std::string::npos)
        << "Header must declare consecutive_frame_drops_ member";

    EXPECT_NE(hpp.find("kMaxConsecutiveFrameDrops"), std::string::npos)
        << "Header must declare kMaxConsecutiveFrameDrops threshold";
}

TEST_F(CameraErrorStateTest, ImageCallbacksTrackFrameDrops) {
    auto lines = readLines(pkg_root_ + "/src/cotton_detection_node.cpp");
    ASSERT_FALSE(lines.empty()) << "Could not read cotton_detection_node.cpp";

    // Both image_callback and compressed_image_callback should reference
    // consecutive_frame_drops_
    int image_cb_line = findLine(lines, "void CottonDetectionNode::image_callback");
    ASSERT_NE(image_cb_line, -1)
        << "Could not find image_callback definition";

    int compressed_cb_line = findLine(lines, "void CottonDetectionNode::compressed_image_callback");
    ASSERT_NE(compressed_cb_line, -1)
        << "Could not find compressed_image_callback definition";

    // Each callback should reference the counter within ~50 lines of its definition
    EXPECT_TRUE(rangeContains(lines, "consecutive_frame_drops_",
                              image_cb_line, image_cb_line + 50))
        << "image_callback must track consecutive_frame_drops_";

    EXPECT_TRUE(rangeContains(lines, "consecutive_frame_drops_",
                              compressed_cb_line, compressed_cb_line + 50))
        << "compressed_image_callback must track consecutive_frame_drops_";
}

// ═════════════════════════════════════════════════════════════════════════════
// Tasks 3.17 / 3.17b: Sleep annotation verification
//
// All sleeps in cotton_detection_ros2 source files must carry a
// BLOCKING_SLEEP_OK annotation on the same or preceding line.
// ═════════════════════════════════════════════════════════════════════════════

class SleepAnnotationTest : public ::testing::Test {
protected:
    std::string pkg_root_;

    void SetUp() override { pkg_root_ = getPackageRoot(); }

    /// Scan a single file for unannotated sleep calls.
    std::vector<SourceIssue> findUnannotatedSleeps(const std::string& path) {
        std::vector<SourceIssue> results;
        auto lines = readLines(path);
        if (lines.empty()) return results;

        std::string prev_line;
        for (size_t i = 0; i < lines.size(); ++i) {
            const auto& line = lines[i];

            if (lineHasSleepCall(line) && !lineIsDefinition(line)) {
                bool annotated = (line.find("BLOCKING_SLEEP_OK") != std::string::npos ||
                                 prev_line.find("BLOCKING_SLEEP_OK") != std::string::npos);
                if (!annotated) {
                    results.push_back({path, static_cast<int>(i + 1), line});
                }
            }
            prev_line = line;
        }
        return results;
    }
};

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInServiceHandler) {
    std::string path = pkg_root_ + "/src/service_handler.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find: " << path;

    auto issues = findUnannotatedSleeps(path);
    EXPECT_EQ(issues.size(), 0u) << formatIssues("Unannotated sleeps", issues);
}

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInCottonDetectionNode) {
    std::string path = pkg_root_ + "/src/cotton_detection_node.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find: " << path;

    auto issues = findUnannotatedSleeps(path);
    EXPECT_EQ(issues.size(), 0u) << formatIssues("Unannotated sleeps", issues);
}

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInDetectionEngine) {
    std::string path = pkg_root_ + "/src/detection_engine.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find: " << path;

    auto issues = findUnannotatedSleeps(path);
    EXPECT_EQ(issues.size(), 0u) << formatIssues("Unannotated sleeps", issues);
}

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInDepthaiManager) {
    std::string path = pkg_root_ + "/src/depthai_manager.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find: " << path;

    auto issues = findUnannotatedSleeps(path);
    EXPECT_EQ(issues.size(), 0u) << formatIssues("Unannotated sleeps", issues);
}

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedInNodeMain) {
    std::string path = pkg_root_ + "/src/cotton_detection_node_main.cpp";
    ASSERT_TRUE(fs::exists(path)) << "Cannot find: " << path;

    auto issues = findUnannotatedSleeps(path);
    EXPECT_EQ(issues.size(), 0u) << formatIssues("Unannotated sleeps", issues);
}

TEST_F(SleepAnnotationTest, AllSleepsAnnotatedAcrossPackage) {
    // Catch-all: scan ALL .cpp files in src/ directory
    std::string src_dir = pkg_root_ + "/src";
    ASSERT_TRUE(fs::exists(src_dir)) << "Cannot find src directory: " << src_dir;

    std::vector<SourceIssue> all_issues;
    for (auto& entry : fs::recursive_directory_iterator(src_dir)) {
        if (!entry.is_regular_file()) continue;
        auto ext = entry.path().extension().string();
        if (ext != ".cpp" && ext != ".hpp") continue;
        // Skip test files
        if (entry.path().string().find("/test/") != std::string::npos) continue;

        auto issues = findUnannotatedSleeps(entry.path().string());
        all_issues.insert(all_issues.end(), issues.begin(), issues.end());
    }

    EXPECT_EQ(all_issues.size(), 0u) << formatIssues("Unannotated sleeps across package", all_issues);
}

// ═════════════════════════════════════════════════════════════════════════════
// Task 3.18: pauseCamera state consistency verification
//
// Verifies that camera_manager.cpp's pauseCamera() propagates teardown
// failure (returns false, sets Error state) rather than always succeeding.
// ═════════════════════════════════════════════════════════════════════════════

class PauseCameraConsistencyTest : public ::testing::Test {
protected:
    std::vector<std::string> lines_;
    int pause_func_start_ = -1;
    int pause_func_end_ = -1;

    void SetUp() override {
        std::string path = getPackageRoot() + "/src/camera_manager.cpp";
        lines_ = readLines(path);
        ASSERT_FALSE(lines_.empty()) << "Could not read camera_manager.cpp";

        // Find pauseCamera function
        pause_func_start_ = findLine(lines_, "CameraManager::pauseCamera()");
        ASSERT_NE(pause_func_start_, -1) << "Could not find pauseCamera() definition";

        // Find approximate end (next function or 100 lines, whichever first)
        pause_func_end_ = std::min(pause_func_start_ + 100,
                                   static_cast<int>(lines_.size()));
        for (int i = pause_func_start_ + 5; i < pause_func_end_; ++i) {
            // Look for next top-level function definition (starts at column 0 with a return type)
            if (lines_[i].find("CameraManager::") != std::string::npos &&
                lines_[i].find("{") != std::string::npos &&
                i > pause_func_start_ + 3) {
                pause_func_end_ = i;
                break;
            }
        }
    }
};

TEST_F(PauseCameraConsistencyTest, PropagatesTeardownFailure) {
    // pauseCamera must contain "return false" for the failure path
    EXPECT_TRUE(rangeContains(lines_, "return false", pause_func_start_, pause_func_end_))
        << "pauseCamera() must return false when teardown fails";
}

TEST_F(PauseCameraConsistencyTest, SetsErrorStateOnFailure) {
    // pauseCamera must set Error state on failure
    EXPECT_TRUE(rangeContains(lines_, "Error", pause_func_start_, pause_func_end_))
        << "pauseCamera() must transition to Error state on teardown failure";
}

TEST_F(PauseCameraConsistencyTest, HasCameraErrorFlag) {
    // pauseCamera must set camera_error_ on failure
    EXPECT_TRUE(rangeContains(lines_, "camera_error_", pause_func_start_, pause_func_end_))
        << "pauseCamera() must set camera_error_ flag on failure";
}

TEST_F(PauseCameraConsistencyTest, CameraManagerExposesErrorQuery) {
    // camera_manager.hpp must declare isCameraInError() and clearCameraError()
    std::string hpp = readFile(
        getPackageRoot() + "/include/cotton_detection_ros2/camera_manager.hpp");
    ASSERT_FALSE(hpp.empty()) << "Could not read camera_manager.hpp";

    EXPECT_NE(hpp.find("isCameraInError"), std::string::npos)
        << "camera_manager.hpp must declare isCameraInError()";

    EXPECT_NE(hpp.find("clearCameraError"), std::string::npos)
        << "camera_manager.hpp must declare clearCameraError()";
}

// ═════════════════════════════════════════════════════════════════════════════
// Task 3.19: catch(...) → typed catch verification in depthai_manager.cpp
//
// Every catch(...) block in depthai_manager.cpp must either:
//   a) Be preceded by a catch(const std::exception& e) on the same try, OR
//   b) Be inside a destructor (where catch-all is correct)
//
// This verifies the error-propagation-safety spec requirement that all
// catch-all blocks have typed exception handlers.
// ═════════════════════════════════════════════════════════════════════════════

class TypedCatchVerificationTest : public ::testing::Test {
protected:
    std::vector<std::string> lines_;

    void SetUp() override {
        std::string path = getPackageRoot() + "/src/depthai_manager.cpp";
        lines_ = readLines(path);
        ASSERT_FALSE(lines_.empty()) << "Could not read depthai_manager.cpp";
    }

    /// Check if a catch(...) at line_idx is preceded by a typed catch
    /// (within the same try block) or is inside a destructor.
    bool isValidCatchAll(int line_idx) {
        // Check if inside a destructor (search backward for ~ClassName pattern)
        for (int i = line_idx; i >= std::max(0, line_idx - 80); --i) {
            if (lines_[i].find("~") != std::string::npos &&
                lines_[i].find("DepthAI") != std::string::npos) {
                return true;  // catch-all in destructor is correct
            }
            // Stop looking if we hit another function definition
            if (i < line_idx - 2 &&
                lines_[i].find("DepthAIManager::") != std::string::npos &&
                lines_[i].find("~") == std::string::npos) {
                break;
            }
        }

        // Check if preceded by catch(const std::exception& e) within 10 lines
        // (the typed catch immediately before catch-all in the same try)
        for (int i = line_idx - 1; i >= std::max(0, line_idx - 10); --i) {
            if (lines_[i].find("catch") != std::string::npos &&
                lines_[i].find("std::exception") != std::string::npos) {
                return true;  // has typed catch preceding it
            }
            // If we hit a 'try' keyword, the catch-all has no typed predecessor
            auto trimmed = lines_[i];
            auto pos = trimmed.find_first_not_of(" \t");
            if (pos != std::string::npos && trimmed.substr(pos, 4) == "try " ||
                (pos != std::string::npos && trimmed.substr(pos, 4) == "try{") ||
                (pos != std::string::npos && trimmed.length() > pos + 2 &&
                 trimmed[pos] == 't' && trimmed[pos+1] == 'r' && trimmed[pos+2] == 'y' &&
                 (pos + 3 >= trimmed.length() || trimmed[pos+3] == ' ' || trimmed[pos+3] == '{'))) {
                break;
            }
        }

        return false;
    }
};

TEST_F(TypedCatchVerificationTest, AllCatchAllBlocksHaveTypedPredecessorOrDestructor) {
    std::vector<SourceIssue> issues;

    for (size_t i = 0; i < lines_.size(); ++i) {
        const auto& line = lines_[i];

        // Skip comment lines
        auto first_non_space = line.find_first_not_of(" \t");
        if (first_non_space != std::string::npos && line.substr(first_non_space, 2) == "//") {
            continue;
        }

        // Find catch(...) patterns
        if (line.find("catch") != std::string::npos &&
            line.find("...") != std::string::npos) {
            if (!isValidCatchAll(static_cast<int>(i))) {
                issues.push_back({"depthai_manager.cpp", static_cast<int>(i + 1), line});
            }
        }
    }

    EXPECT_EQ(issues.size(), 0u)
        << formatIssues("catch(...) blocks without typed catch predecessor", issues);
}

TEST_F(TypedCatchVerificationTest, TypedCatchBlocksLogException) {
    // Every catch(const std::exception& e) block should reference e.what()
    // within the next 10 lines (ensuring the exception message is logged)
    std::vector<SourceIssue> issues;

    for (size_t i = 0; i < lines_.size(); ++i) {
        const auto& line = lines_[i];

        // Find typed catch blocks
        if (line.find("catch") != std::string::npos &&
            line.find("std::exception") != std::string::npos) {
            // Check if e.what() is referenced within next 10 lines
            bool logs_what = false;
            for (size_t j = i; j < std::min(i + 10, lines_.size()); ++j) {
                if (lines_[j].find("e.what()") != std::string::npos ||
                    lines_[j].find(".what()") != std::string::npos) {
                    logs_what = true;
                    break;
                }
            }
            if (!logs_what) {
                issues.push_back({"depthai_manager.cpp", static_cast<int>(i + 1), line});
            }
        }
    }

    EXPECT_EQ(issues.size(), 0u)
        << formatIssues("Typed catch blocks not logging e.what()", issues);
}

TEST_F(TypedCatchVerificationTest, CatchAllBlocksLogWarning) {
    // Every catch(...) block (except in destructors) should log an "unknown exception" warning
    std::vector<SourceIssue> issues;

    for (size_t i = 0; i < lines_.size(); ++i) {
        const auto& line = lines_[i];

        if (line.find("catch") != std::string::npos &&
            line.find("...") != std::string::npos) {

            // Skip destructor catch-all (already verified as correct)
            bool in_destructor = false;
            for (int j = static_cast<int>(i); j >= std::max(0, static_cast<int>(i) - 80); --j) {
                if (lines_[j].find("~") != std::string::npos &&
                    lines_[j].find("DepthAI") != std::string::npos) {
                    in_destructor = true;
                    break;
                }
                if (j < static_cast<int>(i) - 2 &&
                    lines_[j].find("DepthAIManager::") != std::string::npos &&
                    lines_[j].find("~") == std::string::npos) {
                    break;
                }
            }

            if (!in_destructor) {
                // Check if catch-all block logs "unknown" within next 10 lines
                bool logs_unknown = false;
                for (size_t j = i; j < std::min(i + 10, lines_.size()); ++j) {
                    if (lines_[j].find("unknown") != std::string::npos ||
                        lines_[j].find("Unknown") != std::string::npos ||
                        lines_[j].find("non-standard") != std::string::npos) {
                        logs_unknown = true;
                        break;
                    }
                }
                if (!logs_unknown) {
                    issues.push_back({"depthai_manager.cpp", static_cast<int>(i + 1), line});
                }
            }
        }
    }

    EXPECT_EQ(issues.size(), 0u)
        << formatIssues("catch(...) blocks not logging unknown exception warning", issues);
}

// ═════════════════════════════════════════════════════════════════════════════

int main(int argc, char ** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
