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
 * @file aruco_coordinator_test.cpp
 * @brief RED tests for ArucoCoordinator — ArUco detection, multi-position J4
 *        scanning, preloaded centroids, and re-trigger gating
 * @details Tests construction, detection callback wiring, multi-position scan
 *          iteration, J4 offset compensation, re-trigger enable/disable, and
 *          preloaded centroid loading.
 *
 *          This is a RED test file: the header
 *          yanthra_move/core/aruco_coordinator.hpp and its implementation do
 *          not exist yet.  The tests must compile but will FAIL to link until
 *          the class is created.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>

#include "yanthra_move/core/aruco_coordinator.hpp"
#include "yanthra_move/core/cotton_detection.hpp"
#include "yanthra_move/core/multi_position_config.hpp"
#include "yanthra_move/joint_move.h"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <functional>
#include <optional>
#include <string>
#include <vector>

// =============================================================================
// PROVIDE EXTERN SYMBOLS
// =============================================================================
// These symbols are normally defined in yanthra_move_system_core.cpp.
// We define them here so the test binary links without pulling in the full
// system node (same pattern as recovery_manager_test.cpp).
// =============================================================================

namespace yanthra_move {
std::atomic<bool> simulation_mode{true};
std::atomic<bool> executor_running{false};
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor{nullptr};
std::shared_ptr<rclcpp::Node> global_node{nullptr};
std::thread executor_thread;
}  // namespace yanthra_move

// =============================================================================
// TEST FIXTURE
// =============================================================================

class ArucoCoordinatorTest : public ::testing::Test {
protected:
    static rclcpp::Node::SharedPtr node_;

    static void SetUpTestSuite() {
        node_ = rclcpp::Node::make_shared("test_aruco_coordinator");
    }

    static void TearDownTestSuite() {
        node_.reset();
    }

    /// Create a fresh ArucoCoordinator for each test.
    std::unique_ptr<yanthra_move::core::ArucoCoordinator> makeCoordinator() {
        return std::make_unique<yanthra_move::core::ArucoCoordinator>(
            node_->get_logger());
    }

    /// Build a Joint4MultiPositionConfig with 3 test positions.
    yanthra_move::core::Joint4MultiPositionConfig makeTestConfig() {
        yanthra_move::core::Joint4MultiPositionConfig config;
        config.enabled = true;
        config.positions = {-0.10, 0.0, 0.10};
        config.scan_strategy = "as_configured";
        config.early_exit_enabled = false;
        config.enable_j4_offset_compensation = true;
        return config;
    }

    /// Helper: create a single CottonDetection at the given position.
    yanthra_move::core::CottonDetection makeDetection(
        double x, double y, double z, float confidence = 0.9f)
    {
        yanthra_move::core::CottonDetection det;
        det.position.x = x;
        det.position.y = y;
        det.position.z = z;
        det.confidence = confidence;
        det.detection_id = 1;
        det.detection_time = std::chrono::steady_clock::now();
        det.processing_time_ms = 10;
        return det;
    }

    /// Helper: write a temporary centroid file and return its path.
    std::string writeTempCentroidFile(
        const std::vector<std::tuple<double, double, double>>& points)
    {
        // Use /tmp to avoid polluting the repo
        std::string path = "/tmp/aruco_test_centroids_" +
                           std::to_string(::getpid()) + ".csv";
        std::ofstream ofs(path);
        ofs << "x,y,z\n";
        for (const auto& [x, y, z] : points) {
            ofs << x << "," << y << "," << z << "\n";
        }
        ofs.close();
        return path;
    }
};

// Static member definition
rclcpp::Node::SharedPtr ArucoCoordinatorTest::node_;

// =============================================================================
// 1. Constructor creates instance without throwing
// =============================================================================

TEST_F(ArucoCoordinatorTest, ConstructsWithoutThrowing) {
    EXPECT_NO_THROW({
        auto coord = makeCoordinator();
    });
}

// =============================================================================
// 2. Detection callback: detection succeeds when callback returns valid data
// =============================================================================

TEST_F(ArucoCoordinatorTest, DetectionSucceedsWithValidCallback) {
    auto coord = makeCoordinator();

    // Wire up a detection callback that returns two detections
    std::vector<yanthra_move::core::CottonDetection> mock_detections = {
        makeDetection(0.1, 0.2, 0.3),
        makeDetection(0.4, 0.5, 0.6),
    };
    coord->setDetectionCallback(
        [&]() -> std::optional<std::vector<yanthra_move::core::CottonDetection>> {
            return mock_detections;
        });

    auto points = coord->executeArucoDetection();
    ASSERT_EQ(points.size(), 2u);
    EXPECT_DOUBLE_EQ(points[0].x, 0.1);
    EXPECT_DOUBLE_EQ(points[0].y, 0.2);
    EXPECT_DOUBLE_EQ(points[0].z, 0.3);
    EXPECT_DOUBLE_EQ(points[1].x, 0.4);
    EXPECT_DOUBLE_EQ(points[1].y, 0.5);
    EXPECT_DOUBLE_EQ(points[1].z, 0.6);
}

// =============================================================================
// 3. Detection callback: returns empty when callback returns nullopt
// =============================================================================

TEST_F(ArucoCoordinatorTest, DetectionReturnsEmptyWhenCallbackReturnsNullopt) {
    auto coord = makeCoordinator();

    coord->setDetectionCallback(
        [&]() -> std::optional<std::vector<yanthra_move::core::CottonDetection>> {
            return std::nullopt;
        });

    auto points = coord->executeArucoDetection();
    EXPECT_TRUE(points.empty());
}

// =============================================================================
// 4. Camera unavailable: isCameraAvailable() returns false when no camera
// =============================================================================

TEST_F(ArucoCoordinatorTest, CameraUnavailableByDefault) {
    auto coord = makeCoordinator();

    // Without any camera hardware or detection callback, camera should be
    // reported unavailable.
    EXPECT_FALSE(coord->isCameraAvailable());
}

// =============================================================================
// 5. Multi-position scan: iterates through all configured positions
//    (3 positions → 3 move calls)
// =============================================================================

TEST_F(ArucoCoordinatorTest, MultiPositionScanIteratesAllPositions) {
    auto coord = makeCoordinator();
    auto config = makeTestConfig();

    // Track J4 move calls
    std::vector<double> moved_positions;
    coord->setJ4MoveCallback(
        [&](double position) -> MoveResult {
            moved_positions.push_back(position);
            return MoveResult::SUCCESS;
        });

    // Detection callback returns one detection per position
    coord->setDetectionCallback(
        [&]() -> std::optional<std::vector<yanthra_move::core::CottonDetection>> {
            return std::vector<yanthra_move::core::CottonDetection>{
                makeDetection(0.1, 0.2, 0.3)};
        });

    auto result = coord->executeMultiPositionScan(config);

    // All 3 positions should have been visited
    ASSERT_EQ(moved_positions.size(), 3u);
    EXPECT_DOUBLE_EQ(moved_positions[0], -0.10);
    EXPECT_DOUBLE_EQ(moved_positions[1], 0.0);
    EXPECT_DOUBLE_EQ(moved_positions[2], 0.10);

    // Result should contain detections
    ASSERT_TRUE(result.has_value());
    EXPECT_GE(result->size(), 3u);
}

// =============================================================================
// 6. Multi-position scan: J4 offset compensation applied to detected positions
// =============================================================================

TEST_F(ArucoCoordinatorTest, MultiPositionScanAppliesJ4OffsetCompensation) {
    auto coord = makeCoordinator();
    auto config = makeTestConfig();
    // Use a single non-zero position to verify offset is applied
    config.positions = {0.10};
    config.enable_j4_offset_compensation = true;

    double moved_to = 0.0;
    coord->setJ4MoveCallback(
        [&](double position) -> MoveResult {
            moved_to = position;
            return MoveResult::SUCCESS;
        });

    // Detection callback returns a detection at known position
    coord->setDetectionCallback(
        [&]() -> std::optional<std::vector<yanthra_move::core::CottonDetection>> {
            return std::vector<yanthra_move::core::CottonDetection>{
                makeDetection(0.05, 0.20, 0.30)};
        });

    auto result = coord->executeMultiPositionScan(config);
    ASSERT_TRUE(result.has_value());
    ASSERT_EQ(result->size(), 1u);

    // The returned position should have the J4 offset (0.10) compensated.
    // The exact compensation formula depends on implementation, but the
    // position.x should differ from the raw 0.05 by the J4 offset.
    // With offset 0.10 applied, we expect position.x ≈ 0.05 + 0.10 = 0.15
    // (or whatever the compensation formula yields — the key assertion is
    // that the raw value is NOT returned unmodified).
    EXPECT_NE(result->at(0).position.x, 0.05)
        << "J4 offset compensation should modify the detection x position";

    // Also verify getCurrentJ4ScanOffset reflects the last scan offset
    EXPECT_DOUBLE_EQ(coord->getCurrentJ4ScanOffset(), 0.10);
}

// =============================================================================
// 7. Re-trigger gating: detection not re-triggered when disabled
// =============================================================================

TEST_F(ArucoCoordinatorTest, ReTriggerGatingBlocksWhenDisabled) {
    auto coord = makeCoordinator();

    int detection_call_count = 0;
    coord->setDetectionCallback(
        [&]() -> std::optional<std::vector<yanthra_move::core::CottonDetection>> {
            ++detection_call_count;
            return std::vector<yanthra_move::core::CottonDetection>{
                makeDetection(0.1, 0.2, 0.3)};
        });

    coord->setReTriggerEnabled(false);
    EXPECT_FALSE(coord->isReTriggerEnabled());

    // First call should always work (initial detection, not a re-trigger)
    auto points1 = coord->executeArucoDetection();
    EXPECT_FALSE(points1.empty());
    int calls_after_first = detection_call_count;

    // Second call is a re-trigger — should be blocked when disabled
    auto points2 = coord->executeArucoDetection();
    EXPECT_TRUE(points2.empty())
        << "Re-trigger should be gated when disabled";
    EXPECT_EQ(detection_call_count, calls_after_first)
        << "Detection callback should NOT be invoked on gated re-trigger";
}

// =============================================================================
// 8. Re-trigger gating: detection re-triggered when enabled
// =============================================================================

TEST_F(ArucoCoordinatorTest, ReTriggerGatingAllowsWhenEnabled) {
    auto coord = makeCoordinator();

    int detection_call_count = 0;
    coord->setDetectionCallback(
        [&]() -> std::optional<std::vector<yanthra_move::core::CottonDetection>> {
            ++detection_call_count;
            return std::vector<yanthra_move::core::CottonDetection>{
                makeDetection(0.1, 0.2, 0.3)};
        });

    coord->setReTriggerEnabled(true);
    EXPECT_TRUE(coord->isReTriggerEnabled());

    // First call
    auto points1 = coord->executeArucoDetection();
    EXPECT_FALSE(points1.empty());

    // Second call (re-trigger) should proceed when enabled
    auto points2 = coord->executeArucoDetection();
    EXPECT_FALSE(points2.empty())
        << "Re-trigger should succeed when enabled";
    EXPECT_EQ(detection_call_count, 2)
        << "Detection callback should be invoked twice";
}

// =============================================================================
// 9. Preloaded centroids: loading from valid file returns detections
// =============================================================================

TEST_F(ArucoCoordinatorTest, PreloadedCentroidsLoadFromValidFile) {
    auto coord = makeCoordinator();

    auto filepath = writeTempCentroidFile({
        {0.10, 0.20, 0.30},
        {0.40, 0.50, 0.60},
        {0.70, 0.80, 0.90},
    });

    auto result = coord->loadPreloadedCentroids(filepath);
    ASSERT_TRUE(result.has_value());
    ASSERT_EQ(result->size(), 3u);

    EXPECT_DOUBLE_EQ(result->at(0).position.x, 0.10);
    EXPECT_DOUBLE_EQ(result->at(0).position.y, 0.20);
    EXPECT_DOUBLE_EQ(result->at(0).position.z, 0.30);

    EXPECT_DOUBLE_EQ(result->at(1).position.x, 0.40);
    EXPECT_DOUBLE_EQ(result->at(1).position.y, 0.50);
    EXPECT_DOUBLE_EQ(result->at(1).position.z, 0.60);

    EXPECT_DOUBLE_EQ(result->at(2).position.x, 0.70);
    EXPECT_DOUBLE_EQ(result->at(2).position.y, 0.80);
    EXPECT_DOUBLE_EQ(result->at(2).position.z, 0.90);

    // Clean up temp file
    std::remove(filepath.c_str());
}

// =============================================================================
// 10. Preloaded centroids: loading from non-existent file returns nullopt
// =============================================================================

TEST_F(ArucoCoordinatorTest, PreloadedCentroidsNulloptForMissingFile) {
    auto coord = makeCoordinator();

    auto result = coord->loadPreloadedCentroids(
        "/tmp/nonexistent_centroids_file_12345.csv");
    EXPECT_FALSE(result.has_value());
}

// =============================================================================
// ADDITIONAL: getMultiPositionStats() returns zero-initialized stats
// =============================================================================

TEST_F(ArucoCoordinatorTest, InitialMultiPositionStatsAreZero) {
    auto coord = makeCoordinator();

    const auto& stats = coord->getMultiPositionStats();
    EXPECT_EQ(stats.total_scans, 0);
    EXPECT_EQ(stats.cottons_found_multipos, 0);
    EXPECT_EQ(stats.cottons_found_center, 0);
    EXPECT_EQ(stats.early_exits, 0);
    EXPECT_EQ(stats.j4_move_failures, 0);
    EXPECT_TRUE(stats.position_hit_count.empty());
    EXPECT_TRUE(stats.position_avg_time_ms.empty());
}

// =============================================================================
// main -- initialize / shutdown rclcpp around the test run
// =============================================================================

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int ret = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return ret;
}
