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
 * @file test_detection_engine.cpp
 * @brief Unit tests for DetectionEngine (restore-depthai-manager change).
 *
 * Verifies that DetectionEngine:
 *   - Constructs without crashing with default config
 *   - Stats are zero-initialized after construction
 *   - Stats increment methods work correctly
 *   - detect_cotton_in_image fails gracefully when DepthAI is not initialized
 *   - Under HAS_DEPTHAI, the DepthAIManager accessor is null before init
 *   - Config round-trips correctly
 *
 * Hardware-dependent tests (camera connects, detection pipeline produces)
 * are integration tests that require an OAK-D Lite device.
 */

#include <gtest/gtest.h>

#include <memory>
#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <geometry_msgs/msg/point.hpp>

#include "cotton_detection_ros2/detection_engine.hpp"

using namespace cotton_detection_ros2;

// ---------------------------------------------------------------------------
// Test fixture
// ---------------------------------------------------------------------------

class DetectionEngineTest : public ::testing::Test
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

    std::vector<std::string> log_messages_;
};

// ===========================================================================
// Construction Tests
// ===========================================================================

TEST_F(DetectionEngineTest, ConstructsWithDefaultConfig)
{
    auto engine = makeEngine();
    ASSERT_NE(engine, nullptr);
}

TEST_F(DetectionEngineTest, ConstructsWithCustomConfig)
{
    DetectionConfig config;
    config.detection_confidence_threshold = 0.75;
    config.workspace_filter_enabled = true;
    config.workspace_max_x = 2.0;
    config.border_filter_enabled = false;
    config.cache_validity_ms = 200;

    auto engine = makeEngine(config);
    ASSERT_NE(engine, nullptr);

    // Verify config is stored correctly
    EXPECT_DOUBLE_EQ(engine->getConfig().detection_confidence_threshold, 0.75);
    EXPECT_TRUE(engine->getConfig().workspace_filter_enabled);
    EXPECT_DOUBLE_EQ(engine->getConfig().workspace_max_x, 2.0);
    EXPECT_FALSE(engine->getConfig().border_filter_enabled);
    EXPECT_EQ(engine->getConfig().cache_validity_ms, 200);
}

// ===========================================================================
// Stats Tests
// ===========================================================================

TEST_F(DetectionEngineTest, StatsZeroInitialized)
{
    auto engine = makeEngine();
    auto stats = engine->getStats();

    EXPECT_EQ(stats.total_detect_requests, 0u);
    EXPECT_EQ(stats.total_detect_success, 0u);
    EXPECT_EQ(stats.total_positions_returned, 0u);
    EXPECT_EQ(stats.total_detections_with_cotton, 0u);
    EXPECT_EQ(stats.total_border_filtered, 0u);
    EXPECT_EQ(stats.total_non_pickable_filtered, 0u);
    EXPECT_EQ(stats.total_workspace_filtered, 0u);
    EXPECT_EQ(stats.total_cache_hits, 0u);
    EXPECT_EQ(stats.total_cache_misses, 0u);
    EXPECT_EQ(stats.total_reconnects, 0u);
    EXPECT_EQ(stats.total_downtime_ms, 0u);
    EXPECT_EQ(stats.total_sync_mismatches, 0u);
    EXPECT_EQ(stats.frame_wait_total_ms, 0u);
    EXPECT_EQ(stats.frame_wait_count, 0u);
    EXPECT_EQ(stats.frame_wait_max_ms, 0u);
    EXPECT_EQ(stats.consecutive_detection_timeouts, 0);
    EXPECT_EQ(stats.consecutive_rgb_timeouts, 0);
}

TEST_F(DetectionEngineTest, StatsIncrementMethods)
{
    auto engine = makeEngine();

    engine->incrementDetectRequests();
    engine->incrementDetectRequests();
    engine->incrementDetectSuccess();
    engine->addPositionsReturned(3);
    engine->incrementDetectionsWithCotton();
    engine->incrementCacheHits();
    engine->incrementCacheMisses();
    engine->incrementCacheMisses();

    auto stats = engine->getStats();
    EXPECT_EQ(stats.total_detect_requests, 2u);
    EXPECT_EQ(stats.total_detect_success, 1u);
    EXPECT_EQ(stats.total_positions_returned, 3u);
    EXPECT_EQ(stats.total_detections_with_cotton, 1u);
    EXPECT_EQ(stats.total_cache_hits, 1u);
    EXPECT_EQ(stats.total_cache_misses, 2u);
}

// ===========================================================================
// Detection without DepthAI initialized
// ===========================================================================

TEST_F(DetectionEngineTest, DetectFailsGracefullyWithoutDepthAI)
{
    // Default config: depthai_enable=false (or HAS_DEPTHAI not active for pipeline)
    // The engine should return false and log an error
    auto engine = makeEngine();

    cv::Mat empty_image;
    std::vector<geometry_msgs::msg::Point> positions;
    bool result = engine->detect_cotton_in_image(empty_image, positions);

    EXPECT_FALSE(result);
    EXPECT_TRUE(positions.empty());

    // Should have logged an error about DepthAI not being available
    bool found_error = false;
    for (const auto & msg : log_messages_) {
        if (msg.find("DepthAI not available") != std::string::npos) {
            found_error = true;
            break;
        }
    }
    EXPECT_TRUE(found_error) << "Expected 'DepthAI not available' log message";
}

// ===========================================================================
// DepthAI-specific tests (compile-time guarded)
// ===========================================================================

#ifdef HAS_DEPTHAI

TEST_F(DetectionEngineTest, DepthAIManagerNullBeforeInit)
{
    // Before initialize_depthai() is called, the manager should be null
    auto engine = makeEngine();
    EXPECT_EQ(engine->getDepthAIManager(), nullptr);
    EXPECT_EQ(engine->getThermalGuard(), nullptr);
    EXPECT_FALSE(engine->isDepthAIActive());
}

TEST_F(DetectionEngineTest, DepthAIConfigRoundTrip)
{
    DetectionConfig config;
    config.depthai_enable = true;
    config.depthai_model_path = "/tmp/test_model.blob";
    config.depthai_num_classes = 2;
    config.depthai_camera_width = 640;
    config.depthai_camera_height = 480;
    config.depthai_camera_fps = 15;
    config.depthai_confidence_threshold = 0.7f;
    config.depthai_depth_min_mm = 200.0;
    config.depthai_depth_max_mm = 3000.0;
    config.depthai_warmup_seconds = 1;
    config.depthai_detection_timeout_ms = 300;
    config.depthai_swap_class_labels = true;

    auto engine = makeEngine(config);
    const auto & stored = engine->getConfig();

    EXPECT_TRUE(stored.depthai_enable);
    EXPECT_EQ(stored.depthai_model_path, "/tmp/test_model.blob");
    EXPECT_EQ(stored.depthai_num_classes, 2);
    EXPECT_EQ(stored.depthai_camera_width, 640);
    EXPECT_EQ(stored.depthai_camera_height, 480);
    EXPECT_EQ(stored.depthai_camera_fps, 15);
    EXPECT_FLOAT_EQ(stored.depthai_confidence_threshold, 0.7f);
    EXPECT_DOUBLE_EQ(stored.depthai_depth_min_mm, 200.0);
    EXPECT_DOUBLE_EQ(stored.depthai_depth_max_mm, 3000.0);
    EXPECT_EQ(stored.depthai_warmup_seconds, 1);
    EXPECT_EQ(stored.depthai_detection_timeout_ms, 300);
    EXPECT_TRUE(stored.depthai_swap_class_labels);
}

TEST_F(DetectionEngineTest, DetectWithDepthAIEnabledButNotInitialized)
{
    // depthai_enable=true but initialize_depthai() never called
    // use_depthai_ atomic is still false, so it should fall through to the
    // "DepthAI not available" error path
    DetectionConfig config;
    config.depthai_enable = true;

    auto engine = makeEngine(config);

    cv::Mat empty_image;
    std::vector<geometry_msgs::msg::Point> positions;
    bool result = engine->detect_cotton_in_image(empty_image, positions);

    EXPECT_FALSE(result);
    EXPECT_TRUE(positions.empty());
}

#endif  // HAS_DEPTHAI

// ===========================================================================
// Cache Tests
// ===========================================================================

TEST_F(DetectionEngineTest, CacheInitiallyEmpty)
{
    auto engine = makeEngine();

    std::lock_guard<std::mutex> lock(engine->getCacheMutex());
    EXPECT_FALSE(engine->getCachedDetection().has_value());
}

TEST_F(DetectionEngineTest, ConfidencesInitiallyEmpty)
{
    auto engine = makeEngine();

    std::lock_guard<std::mutex> lock(engine->getConfidencesMutex());
    EXPECT_TRUE(engine->getLastDetectionConfidences().empty());
}

// ===========================================================================
// Config Mutability Tests
// ===========================================================================

TEST_F(DetectionEngineTest, ConfigIsMutableAtRuntime)
{
    auto engine = makeEngine();

    // Modify config through mutable accessor
    engine->getConfig().detection_confidence_threshold = 0.9;
    engine->getConfig().border_filter_enabled = false;

    EXPECT_DOUBLE_EQ(engine->getConfig().detection_confidence_threshold, 0.9);
    EXPECT_FALSE(engine->getConfig().border_filter_enabled);
}

// ===========================================================================
// Main
// ===========================================================================

int main(int argc, char ** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
