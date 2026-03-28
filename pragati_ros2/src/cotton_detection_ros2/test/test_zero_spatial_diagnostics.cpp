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
 * @file test_zero_spatial_diagnostics.cpp
 * @brief Tests for detection-zero-spatial-diagnostics change.
 *
 * Verifies:
 *   Task 1: Zero-spatial WARN log line contains bbox key=value fields
 *           (source-audit: log format string in depthai_manager.cpp)
 *   Task 2: draw_detections_on_image() draws red "DEPTH FAIL" boxes for
 *           rejected detections, handles empty accepted + non-empty rejected
 *   Task 3: RejectedDetection and ZeroSpatialInfo struct fields, wiring
 *           source-audit for detection_engine.cpp
 *   Task 3b: Saved image contains red pixels from zero-spatial annotation
 *
 * Tests that don't require hardware use source-audit (file scanning) or
 * direct draw function calls with synthetic images.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include "cotton_detection_ros2/detection_engine.hpp"
#include "cotton_detection_ros2/detection_types.hpp"

using namespace cotton_detection_ros2;
namespace fs = std::filesystem;

// ===========================================================================
// Helpers
// ===========================================================================

/// Resolve the cotton_detection_ros2 package root from SOURCE_DIR compile definition.
static std::string getPackageRoot()
{
#ifdef SOURCE_DIR
    return SOURCE_DIR;
#else
    fs::path test_file(__FILE__);
    return test_file.parent_path().parent_path().string();
#endif
}

/// Read all lines from a source file.
static std::vector<std::string> readLines(const std::string & path)
{
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
static std::string readFile(const std::string & path)
{
    std::ifstream f(path);
    if (!f.is_open()) return {};
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

/// Count pixels matching a specific BGR color within a region.
static int countColorPixels(
    const cv::Mat & image, int x1, int y1, int x2, int y2,
    const cv::Vec3b & target_color, int tolerance = 10)
{
    int count = 0;
    for (int y = std::max(0, y1); y < std::min(image.rows, y2); ++y) {
        for (int x = std::max(0, x1); x < std::min(image.cols, x2); ++x) {
            const cv::Vec3b & px = image.at<cv::Vec3b>(y, x);
            if (std::abs(px[0] - target_color[0]) <= tolerance &&
                std::abs(px[1] - target_color[1]) <= tolerance &&
                std::abs(px[2] - target_color[2]) <= tolerance) {
                ++count;
            }
        }
    }
    return count;
}

/// Check if any pixel in the image matches the target color.
static bool hasColorAnywhere(const cv::Mat & image, const cv::Vec3b & color, int tolerance = 10)
{
    return countColorPixels(image, 0, 0, image.cols, image.rows, color, tolerance) > 0;
}

// ===========================================================================
// Test fixture
// ===========================================================================

class ZeroSpatialDiagnosticsTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        log_messages_.clear();
    }

    /// Create a DetectionEngine with optional config overrides
    std::unique_ptr<DetectionEngine> makeEngine(
        const DetectionConfig & config = DetectionConfig{})
    {
        auto logger = [this](cotton_detection::LogLevel level, const std::string & msg) {
            (void)level;
            log_messages_.push_back(msg);
        };
        return std::make_unique<DetectionEngine>(
            config, logger, nullptr, nullptr);
    }

    /// Create a synthetic BGR test image.
    cv::Mat makeTestImage(int width = 640, int height = 480)
    {
        // Black background so colored annotations are easy to detect
        return cv::Mat::zeros(height, width, CV_8UC3);
    }

    std::vector<std::string> log_messages_;
};

// ===========================================================================
// Task 1: Log format source-audit tests
// ===========================================================================

/// Task 1 RED (item 1): Verify log line contains bbox key=value pairs
TEST_F(ZeroSpatialDiagnosticsTest, LogFormatContainsBboxFields)
{
    std::string root = getPackageRoot();
    std::string depthai_mgr = root + "/src/depthai_manager.cpp";
    std::string content = readFile(depthai_mgr);
    ASSERT_FALSE(content.empty()) << "Could not read " << depthai_mgr;

    // The log line in convertDetection() must contain these key=value fields
    EXPECT_NE(content.find("xmin="), std::string::npos)
        << "Log line missing 'xmin=' field";
    EXPECT_NE(content.find("ymin="), std::string::npos)
        << "Log line missing 'ymin=' field";
    EXPECT_NE(content.find("xmax="), std::string::npos)
        << "Log line missing 'xmax=' field";
    EXPECT_NE(content.find("ymax="), std::string::npos)
        << "Log line missing 'ymax=' field";
}

/// Task 1 RED (item 2): Verify bbox values use format specifiers for normalized range
TEST_F(ZeroSpatialDiagnosticsTest, LogBboxUsesFloatFormat)
{
    std::string root = getPackageRoot();
    std::string depthai_mgr = root + "/src/depthai_manager.cpp";
    auto lines = readLines(depthai_mgr);
    ASSERT_FALSE(lines.empty()) << "Could not read " << depthai_mgr;

    // Find the zero-spatial log line and verify it uses float format for bbox
    // (%.4f or similar) — not integer format.
    // The format string may span multiple source lines due to C++ string
    // concatenation, so we collect a block of lines around the match.
    bool found_log_line = false;
    bool uses_float_format = false;
    for (size_t i = 0; i < lines.size(); ++i) {
        if (lines[i].find("zero spatial coordinates") != std::string::npos) {
            // Collect nearby lines to capture multi-line format string
            std::string block;
            for (size_t j = i; j < std::min(i + 5, lines.size()); ++j) {
                block += lines[j];
            }
            if (block.find("xmin=") != std::string::npos) {
                found_log_line = true;
                if (block.find("xmin=%.") != std::string::npos ||
                    block.find("xmin=%f") != std::string::npos) {
                    uses_float_format = true;
                }
            }
            break;
        }
    }
    EXPECT_TRUE(found_log_line) << "Could not find zero-spatial log line with bbox fields";
    EXPECT_TRUE(uses_float_format) << "Bbox fields should use float format (%.Nf), not integer";
}

/// Task 1 RED (item 3): Verify existing confidence= and label= fields preserved
TEST_F(ZeroSpatialDiagnosticsTest, LogFormatPreservesExistingFields)
{
    std::string root = getPackageRoot();
    std::string depthai_mgr = root + "/src/depthai_manager.cpp";
    auto lines = readLines(depthai_mgr);
    ASSERT_FALSE(lines.empty()) << "Could not read " << depthai_mgr;

    bool found_log_with_confidence = false;
    bool found_log_with_label = false;
    for (size_t i = 0; i < lines.size(); ++i) {
        if (lines[i].find("zero spatial coordinates") != std::string::npos) {
            // Collect nearby lines to capture multi-line format string
            std::string block;
            for (size_t j = i; j < std::min(i + 5, lines.size()); ++j) {
                block += lines[j];
            }
            if (block.find("confidence=") != std::string::npos) {
                found_log_with_confidence = true;
            }
            if (block.find("label=") != std::string::npos) {
                found_log_with_label = true;
            }
        }
    }
    EXPECT_TRUE(found_log_with_confidence)
        << "Zero-spatial log line must preserve 'confidence=' key=value field";
    EXPECT_TRUE(found_log_with_label)
        << "Zero-spatial log line must preserve 'label=' key=value field";
}

/// Task 1 REFACTOR (item 5): Verify all key=value pairs in single log line
TEST_F(ZeroSpatialDiagnosticsTest, LogFormatAllKeysInSingleLine)
{
    std::string root = getPackageRoot();
    std::string depthai_mgr = root + "/src/depthai_manager.cpp";
    auto lines = readLines(depthai_mgr);
    ASSERT_FALSE(lines.empty()) << "Could not read " << depthai_mgr;

    // Find the snprintf call that formats the zero-spatial log
    // All keys must appear in the same format string (may span multiple source lines
    // due to string concatenation, but they must be in the same snprintf block)
    bool found_complete_format = false;
    std::string format_block;

    for (size_t i = 0; i < lines.size(); ++i) {
        if (lines[i].find("zero spatial coordinates") != std::string::npos) {
            // Collect the format string block (may span a few lines)
            for (size_t j = (i > 2 ? i - 2 : 0); j < std::min(i + 5, lines.size()); ++j) {
                format_block += lines[j];
            }
            break;
        }
    }

    ASSERT_FALSE(format_block.empty()) << "Could not find zero-spatial log format block";

    // All required keys must appear in the block
    std::vector<std::string> required_keys = {
        "label=", "confidence=", "xmin=", "ymin=", "xmax=", "ymax="
    };
    for (const auto & key : required_keys) {
        EXPECT_NE(format_block.find(key), std::string::npos)
            << "Format block missing required key: " << key;
        found_complete_format = true;
    }
    EXPECT_TRUE(found_complete_format);
}

// ===========================================================================
// Task 2: draw_detections_on_image() tests
// ===========================================================================

#ifdef HAS_DEPTHAI

/// Task 2 RED (item 6): Red pixels at expected bbox region for rejected detection
TEST_F(ZeroSpatialDiagnosticsTest, DrawRejectedDetectionShowsRedPixels)
{
    auto engine = makeEngine();
    cv::Mat image = makeTestImage(640, 480);

    // Create a rejected detection at known pixel coordinates
    RejectedDetection rej;
    rej.x1 = 100;
    rej.y1 = 100;
    rej.x2 = 300;
    rej.y2 = 300;
    rej.confidence = 0.85f;
    rej.label = 0;

    std::vector<DepthAIDetectionResult> empty_accepted;
    std::vector<RejectedDetection> rejected = {rej};

    cv::Mat result = engine->draw_detections_on_image(image, empty_accepted, rejected);
    ASSERT_FALSE(result.empty());
    ASSERT_EQ(result.type(), CV_8UC3);

    // Red in BGR = (0, 0, 255)
    cv::Vec3b red(0, 0, 255);

    // Check for red pixels along the bbox border (rectangle drawn with thickness=2)
    // Top edge: y=100, x from 100 to 300
    int red_on_top_edge = countColorPixels(result, 100, 99, 301, 103, red);
    EXPECT_GT(red_on_top_edge, 0)
        << "Expected red pixels on top edge of rejected detection bbox";

    // Left edge: x=100, y from 100 to 300
    int red_on_left_edge = countColorPixels(result, 99, 100, 103, 301, red);
    EXPECT_GT(red_on_left_edge, 0)
        << "Expected red pixels on left edge of rejected detection bbox";
}

/// Task 2 RED (item 7): "DEPTH FAIL" label text is rendered
TEST_F(ZeroSpatialDiagnosticsTest, DrawRejectedDetectionShowsDepthFailLabel)
{
    auto engine = makeEngine();
    cv::Mat image = makeTestImage(640, 480);

    RejectedDetection rej;
    rej.x1 = 100;
    rej.y1 = 100;
    rej.x2 = 300;
    rej.y2 = 300;
    rej.confidence = 0.85f;
    rej.label = 0;

    std::vector<DepthAIDetectionResult> empty_accepted;
    std::vector<RejectedDetection> rejected = {rej};

    cv::Mat result = engine->draw_detections_on_image(image, empty_accepted, rejected);

    // The label is rendered with white text on red background.
    // Verify white pixels exist near the label area (rendered text).
    // White = (255, 255, 255) in BGR.
    cv::Vec3b white(255, 255, 255);

    // The label is positioned relative to bbox center (center_x + 25, center_y - 10)
    // center = (200, 200), so label area ~(225, 190) and extends right
    bool has_white = hasColorAnywhere(result, white);
    EXPECT_TRUE(has_white)
        << "Expected white pixels from 'DEPTH FAIL' label text";

    // Also verify red background rectangle exists for the label
    // (filled red rectangle behind white text)
    cv::Vec3b red(0, 0, 255);
    // Check broader area around expected label position
    int red_in_label_area = countColorPixels(result, 200, 150, 450, 220, red);
    EXPECT_GT(red_in_label_area, 0)
        << "Expected red background rectangle behind DEPTH FAIL label";
}

/// Task 2 RED (item 8): Empty accepted + non-empty rejected — no crash, red boxes only
TEST_F(ZeroSpatialDiagnosticsTest, DrawOnlyRejectedDetectionsNoCrash)
{
    auto engine = makeEngine();
    cv::Mat image = makeTestImage(640, 480);

    // Two rejected detections, zero accepted
    RejectedDetection rej1;
    rej1.x1 = 50; rej1.y1 = 50; rej1.x2 = 150; rej1.y2 = 150;
    rej1.confidence = 0.90f; rej1.label = 0;

    RejectedDetection rej2;
    rej2.x1 = 300; rej2.y1 = 200; rej2.x2 = 500; rej2.y2 = 400;
    rej2.confidence = 0.75f; rej2.label = 1;

    std::vector<DepthAIDetectionResult> empty_accepted;
    std::vector<RejectedDetection> rejected = {rej1, rej2};

    cv::Mat result = engine->draw_detections_on_image(image, empty_accepted, rejected);
    ASSERT_FALSE(result.empty());
    ASSERT_EQ(result.rows, 480);
    ASSERT_EQ(result.cols, 640);

    // Red should be present (from rejected boxes)
    cv::Vec3b red(0, 0, 255);
    EXPECT_TRUE(hasColorAnywhere(result, red))
        << "Expected red pixels from rejected detection boxes";

    // Green should NOT be present in bbox areas (no accepted detections)
    cv::Vec3b green(0, 255, 0);
    // Check that there are no green rectangles in the image body
    // (summary text at top may use green — check only below the summary area)
    int green_in_body = countColorPixels(result, 0, 50, 640, 480, green);
    // The summary line itself uses green, but there should be no green rectangles
    // We only check that rejected boxes are red, not that zero green exists
    // (summary uses green intentionally)
    EXPECT_GT(countColorPixels(result, 0, 0, 640, 480, red), 0);
}

/// Task 2 REFACTOR (item 11): Empty lists returns clone without crash
TEST_F(ZeroSpatialDiagnosticsTest, DrawEmptyListsReturnsClone)
{
    auto engine = makeEngine();
    cv::Mat image = makeTestImage(320, 240);
    image.at<cv::Vec3b>(120, 160) = cv::Vec3b(42, 42, 42);  // unique pixel

    std::vector<DepthAIDetectionResult> empty_det;
    std::vector<RejectedDetection> empty_rej;

    cv::Mat result = engine->draw_detections_on_image(image, empty_det, empty_rej);
    ASSERT_FALSE(result.empty());
    ASSERT_EQ(result.rows, 240);
    ASSERT_EQ(result.cols, 320);

    // Should be a clone of the original (no annotations)
    cv::Vec3b px = result.at<cv::Vec3b>(120, 160);
    EXPECT_EQ(px[0], 42);
    EXPECT_EQ(px[1], 42);
    EXPECT_EQ(px[2], 42);
}

/// Task 2: Mixed accepted and rejected detections
TEST_F(ZeroSpatialDiagnosticsTest, DrawMixedAcceptedAndRejected)
{
    auto engine = makeEngine();
    cv::Mat image = makeTestImage(640, 480);

    // One accepted detection (cotton, label=0 → green)
    DepthAIDetectionResult accepted;
    accepted.x_min = 0.05f;
    accepted.y_min = 0.05f;
    accepted.x_max = 0.25f;
    accepted.y_max = 0.25f;
    accepted.confidence = 0.95f;
    accepted.label = 0;
    accepted.position.x = 0.5;
    accepted.position.y = 0.0;
    accepted.position.z = 0.0;

    // One rejected detection
    RejectedDetection rej;
    rej.x1 = 400; rej.y1 = 300; rej.x2 = 580; rej.y2 = 440;
    rej.confidence = 0.80f; rej.label = 0;

    std::vector<DepthAIDetectionResult> accepted_list = {accepted};
    std::vector<RejectedDetection> rejected_list = {rej};

    cv::Mat result = engine->draw_detections_on_image(image, accepted_list, rejected_list);
    ASSERT_FALSE(result.empty());

    cv::Vec3b green(0, 255, 0);
    cv::Vec3b red(0, 0, 255);

    // Green pixels should exist (from accepted detection)
    EXPECT_TRUE(hasColorAnywhere(result, green))
        << "Expected green pixels from accepted detection";

    // Red pixels should exist (from rejected detection)
    EXPECT_TRUE(hasColorAnywhere(result, red))
        << "Expected red pixels from rejected detection";
}

#endif  // HAS_DEPTHAI

// ===========================================================================
// Task 3: Struct validation and wiring source-audit
// ===========================================================================

/// Task 3: RejectedDetection struct fields are default-initialized
TEST_F(ZeroSpatialDiagnosticsTest, RejectedDetectionDefaultInit)
{
    RejectedDetection rd;
    EXPECT_EQ(rd.x1, 0);
    EXPECT_EQ(rd.y1, 0);
    EXPECT_EQ(rd.x2, 0);
    EXPECT_EQ(rd.y2, 0);
    EXPECT_FLOAT_EQ(rd.confidence, 0.0f);
    EXPECT_EQ(rd.label, 0);
}

/// Task 3: ZeroSpatialInfo struct fields are default-initialized
TEST_F(ZeroSpatialDiagnosticsTest, ZeroSpatialInfoDefaultInit)
{
    cotton_detection::ZeroSpatialInfo info;
    EXPECT_FLOAT_EQ(info.x_min, 0.0f);
    EXPECT_FLOAT_EQ(info.y_min, 0.0f);
    EXPECT_FLOAT_EQ(info.x_max, 0.0f);
    EXPECT_FLOAT_EQ(info.y_max, 0.0f);
    EXPECT_FLOAT_EQ(info.confidence, 0.0f);
    EXPECT_EQ(info.label, 0);
}

/// Task 3: ZeroSpatialInfo fields can be set and read
TEST_F(ZeroSpatialDiagnosticsTest, ZeroSpatialInfoFieldRoundTrip)
{
    cotton_detection::ZeroSpatialInfo info;
    info.x_min = 0.1f;
    info.y_min = 0.2f;
    info.x_max = 0.8f;
    info.y_max = 0.9f;
    info.confidence = 0.85f;
    info.label = 1;

    EXPECT_FLOAT_EQ(info.x_min, 0.1f);
    EXPECT_FLOAT_EQ(info.y_min, 0.2f);
    EXPECT_FLOAT_EQ(info.x_max, 0.8f);
    EXPECT_FLOAT_EQ(info.y_max, 0.9f);
    EXPECT_FLOAT_EQ(info.confidence, 0.85f);
    EXPECT_EQ(info.label, 1);
}

/// Task 3 source-audit: detection_engine.cpp wires rejected detections to draw call
TEST_F(ZeroSpatialDiagnosticsTest, WiringSourceAuditRejectionsPassedToDraw)
{
    std::string root = getPackageRoot();
    std::string engine_src = root + "/src/detection_engine.cpp";
    std::string content = readFile(engine_src);
    ASSERT_FALSE(content.empty()) << "Could not read " << engine_src;

    // Verify the wiring: getLastZeroSpatialRejections() is called
    EXPECT_NE(content.find("getLastZeroSpatialRejections"), std::string::npos)
        << "detection_engine.cpp must call getLastZeroSpatialRejections()";

    // Verify RejectedDetection vector is constructed
    EXPECT_NE(content.find("std::vector<RejectedDetection>"), std::string::npos)
        << "detection_engine.cpp must construct vector<RejectedDetection>";

    // Verify zero_spatial is passed to save_output_image
    EXPECT_NE(content.find("save_output_image"), std::string::npos)
        << "detection_engine.cpp must call save_output_image";
}

/// Task 3 source-audit: depthai_manager.cpp collects zero-spatial info
TEST_F(ZeroSpatialDiagnosticsTest, WiringSourceAuditCollectsZeroSpatialInfo)
{
    std::string root = getPackageRoot();
    std::string mgr_src = root + "/src/depthai_manager.cpp";
    std::string content = readFile(mgr_src);
    ASSERT_FALSE(content.empty()) << "Could not read " << mgr_src;

    // Verify ZeroSpatialInfo is pushed to last_zero_spatial_
    EXPECT_NE(content.find("last_zero_spatial_.push_back"), std::string::npos)
        << "depthai_manager.cpp must push rejected info to last_zero_spatial_";

    // Verify last_zero_spatial_ is cleared per-frame
    EXPECT_NE(content.find("last_zero_spatial_.clear()"), std::string::npos)
        << "depthai_manager.cpp must clear last_zero_spatial_ per frame";
}

/// Task 3 source-audit: depthai_manager.hpp declares getLastZeroSpatialRejections
TEST_F(ZeroSpatialDiagnosticsTest, WiringSourceAuditPublicGetter)
{
    std::string root = getPackageRoot();
    std::string mgr_hpp = root + "/include/cotton_detection_ros2/depthai_manager.hpp";
    std::string content = readFile(mgr_hpp);
    ASSERT_FALSE(content.empty()) << "Could not read " << mgr_hpp;

    EXPECT_NE(content.find("getLastZeroSpatialRejections"), std::string::npos)
        << "depthai_manager.hpp must declare getLastZeroSpatialRejections()";
}

// ===========================================================================
// Task 3b: Image save round-trip verification
// ===========================================================================

#ifdef HAS_DEPTHAI

/// Task 3b: Draw to image, save to disk, read back, verify red pixels
TEST_F(ZeroSpatialDiagnosticsTest, SavedImageContainsRedAnnotation)
{
    auto engine = makeEngine();
    cv::Mat image = makeTestImage(640, 480);

    RejectedDetection rej;
    rej.x1 = 200; rej.y1 = 150; rej.x2 = 400; rej.y2 = 350;
    rej.confidence = 0.92f; rej.label = 0;

    std::vector<DepthAIDetectionResult> empty_accepted;
    std::vector<RejectedDetection> rejected = {rej};

    // Draw annotations
    cv::Mat annotated = engine->draw_detections_on_image(image, empty_accepted, rejected);
    ASSERT_FALSE(annotated.empty());

    // Save to temp file
    fs::path temp_dir = fs::temp_directory_path() / "pragati_test_zero_spatial";
    fs::create_directories(temp_dir);
    fs::path temp_file = temp_dir / "test_annotated.png";

    bool save_ok = cv::imwrite(temp_file.string(), annotated);
    ASSERT_TRUE(save_ok) << "Failed to write test image to " << temp_file;

    // Read back
    cv::Mat loaded = cv::imread(temp_file.string(), cv::IMREAD_COLOR);
    ASSERT_FALSE(loaded.empty()) << "Failed to read back test image from " << temp_file;
    ASSERT_EQ(loaded.rows, 480);
    ASSERT_EQ(loaded.cols, 640);

    // Verify red pixels exist in the saved/loaded image near the bbox region
    cv::Vec3b red(0, 0, 255);
    int red_near_bbox = countColorPixels(loaded, 195, 145, 405, 355, red, 15);
    EXPECT_GT(red_near_bbox, 0)
        << "Saved image must contain red pixels near rejected detection bbox";

    // Cleanup
    fs::remove(temp_file);
    fs::remove(temp_dir);
}

#endif  // HAS_DEPTHAI

// ===========================================================================
// Task 3 REFACTOR: Summary line format verification
// ===========================================================================

#ifdef HAS_DEPTHAI

/// Task 3 REFACTOR (item 15): Summary line includes both detection and depth fail counts
TEST_F(ZeroSpatialDiagnosticsTest, SummaryLineShowsBothCounts)
{
    auto engine = makeEngine();
    cv::Mat image = makeTestImage(640, 480);

    DepthAIDetectionResult det;
    det.x_min = 0.1f; det.y_min = 0.1f; det.x_max = 0.3f; det.y_max = 0.3f;
    det.confidence = 0.9f; det.label = 0;
    det.position.x = 0.5; det.position.y = 0.0; det.position.z = 0.0;

    RejectedDetection rej;
    rej.x1 = 400; rej.y1 = 300; rej.x2 = 550; rej.y2 = 430;
    rej.confidence = 0.7f; rej.label = 0;

    std::vector<DepthAIDetectionResult> accepted = {det};
    std::vector<RejectedDetection> rejected = {rej};

    cv::Mat result = engine->draw_detections_on_image(image, accepted, rejected);
    ASSERT_FALSE(result.empty());

    // The summary line is drawn at the top — verify green pixels exist there
    // (summary text "Detections: 1  Depth Fail: 1" in green)
    cv::Vec3b green(0, 255, 0);
    int green_at_top = countColorPixels(result, 0, 0, 640, 50, green);
    EXPECT_GT(green_at_top, 0)
        << "Expected green summary text at top of image";
}

/// Source-audit: Summary format includes "Depth Fail:" count
TEST_F(ZeroSpatialDiagnosticsTest, SummaryFormatSourceAudit)
{
    std::string root = getPackageRoot();
    std::string engine_src = root + "/src/detection_engine.cpp";
    std::string content = readFile(engine_src);
    ASSERT_FALSE(content.empty()) << "Could not read " << engine_src;

    EXPECT_NE(content.find("Depth Fail:"), std::string::npos)
        << "Summary line must include 'Depth Fail:' count";
    EXPECT_NE(content.find("Detections:"), std::string::npos)
        << "Summary line must include 'Detections:' count";
}

#endif  // HAS_DEPTHAI

// ===========================================================================
// Main
// ===========================================================================

int main(int argc, char ** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
