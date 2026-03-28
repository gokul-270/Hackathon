// Copyright 2025 Pragati Robotics
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
 * @file test_simulation_mode.cpp
 * @brief GTest integration tests for cotton detection simulation mode.
 *
 * Tests verify that CottonDetectionNode in simulation_mode=true:
 *   - Creates successfully without camera hardware
 *   - Returns simulated positions via the cotton_detection/detect service
 *   - Applies Gaussian noise when configured
 *   - Produces deterministic results when noise is disabled
 *   - Publishes DetectionResult messages on the results topic
 *   - Generates confidence values within the configured range
 *   - Reports reasonable processing times
 *
 * The tests instantiate the node in-process and communicate via ROS2
 * service client and topic subscription through a shared executor.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>
#include <mutex>
#include <numeric>
#include <vector>

#include <rclcpp/rclcpp.hpp>

#include "cotton_detection_ros2/cotton_detection_node.hpp"
#include "cotton_detection_msgs/msg/detection_result.hpp"
#include "cotton_detection_msgs/srv/cotton_detection.hpp"

using CottonDetectionSrv = cotton_detection_msgs::srv::CottonDetection;
using DetectionResultMsg = cotton_detection_msgs::msg::DetectionResult;

// ---------------------------------------------------------------------------
// Test fixture
// ---------------------------------------------------------------------------

class SimulationModeTest : public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        rclcpp::init(0, nullptr);
    }

    static void TearDownTestSuite()
    {
        rclcpp::shutdown();
    }

    void SetUp() override
    {
        // Each test gets a unique namespace to avoid service/topic collisions
        test_ns_ = "test_sim_" + std::to_string(test_counter_++);

        // Client node lives in the same namespace
        rclcpp::NodeOptions client_opts;
        client_opts.arguments({"--ros-args", "-r", "__ns:=/" + test_ns_});
        client_node_ = rclcpp::Node::make_shared("test_client", client_opts);

        client_ = client_node_->create_client<CottonDetectionSrv>(
            "cotton_detection/detect");
    }

    void TearDown() override
    {
        // Reset in reverse creation order
        sim_node_.reset();
        client_.reset();
        client_node_.reset();
    }

    // ----- Helpers -----

    /**
     * Create the CottonDetectionNode with simulation_mode=true and optional
     * parameter overrides, then call initialize_interfaces().
     */
    void createSimNode(const std::vector<rclcpp::Parameter> & extra_params = {})
    {
        std::vector<rclcpp::Parameter> params = {
            rclcpp::Parameter("simulation_mode", true),
            rclcpp::Parameter("use_depthai", false),
        };
        for (const auto & p : extra_params) {
            params.push_back(p);
        }

        rclcpp::NodeOptions options;
        options.parameter_overrides(params);
        options.arguments({"--ros-args", "-r", "__ns:=/" + test_ns_});

        sim_node_ = std::make_shared<cotton_detection_ros2::CottonDetectionNode>(options);
        sim_node_->initialize_interfaces();
    }

    /**
     * Send a detect request and spin until the response arrives (or timeout).
     * Returns nullptr on failure/timeout.
     *
     * NOTE: The very first call to the service triggers the "warmup" path
     * (warmup_completed_ starts false and is set true on first request).
     * Tests that need non-warmup behaviour should call warmup() first.
     */
    CottonDetectionSrv::Response::SharedPtr callDetect(int32_t command = 1)
    {
        auto request = std::make_shared<CottonDetectionSrv::Request>();
        request->detect_command = command;

        // Wait for service to be available
        if (!client_->wait_for_service(std::chrono::seconds(5))) {
            return nullptr;
        }

        auto future = client_->async_send_request(request);

        auto executor = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
        executor->add_node(sim_node_);
        executor->add_node(client_node_);

        auto status = executor->spin_until_future_complete(future, std::chrono::seconds(5));
        if (status != rclcpp::FutureReturnCode::SUCCESS) {
            return nullptr;
        }
        return future.get();
    }

    /**
     * Issue a warmup call so that subsequent calls are counted as real
     * detection requests (the node skips the first request for stats).
     */
    void warmup()
    {
        auto resp = callDetect(1);
        ASSERT_NE(resp, nullptr) << "Warmup call failed";
    }

    /**
     * Subscribe to the detection results topic, call detect, and collect
     * the published DetectionResult message.  Returns nullptr on timeout.
     */
    DetectionResultMsg::SharedPtr callDetectAndCaptureTopic(int32_t command = 1)
    {
        DetectionResultMsg::SharedPtr captured;
        std::mutex mtx;
        bool received = false;

        auto sub = client_node_->create_subscription<DetectionResultMsg>(
            "cotton_detection/results", 10,
            [&](DetectionResultMsg::SharedPtr msg) {
                std::lock_guard<std::mutex> lock(mtx);
                if (!received) {
                    captured = msg;
                    received = true;
                }
            });

        auto request = std::make_shared<CottonDetectionSrv::Request>();
        request->detect_command = command;

        if (!client_->wait_for_service(std::chrono::seconds(5))) {
            return nullptr;
        }

        auto future = client_->async_send_request(request);

        auto executor = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
        executor->add_node(sim_node_);
        executor->add_node(client_node_);

        // Spin until both the service response and topic message arrive
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        while (std::chrono::steady_clock::now() < deadline) {
            executor->spin_some(std::chrono::milliseconds(10));
            std::lock_guard<std::mutex> lock(mtx);
            if (received &&
                future.wait_for(std::chrono::milliseconds(0)) == std::future_status::ready) {
                break;
            }
        }

        return captured;
    }

    // ----- Members -----
    static int test_counter_;
    std::string test_ns_;

    rclcpp::Node::SharedPtr client_node_;
    rclcpp::Client<CottonDetectionSrv>::SharedPtr client_;
    std::shared_ptr<cotton_detection_ros2::CottonDetectionNode> sim_node_;
};

int SimulationModeTest::test_counter_ = 0;

// ===========================================================================
// Tests
// ===========================================================================

// 1. Node starts in simulation mode without errors
TEST_F(SimulationModeTest, NodeCreatesSuccessfully)
{
    ASSERT_NO_THROW(createSimNode());
    ASSERT_NE(sim_node_, nullptr);
}

// 2. Simulated positions loaded from parameter overrides
TEST_F(SimulationModeTest, CustomPositionsReturnedViaService)
{
    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{0.10, 0.20}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{0.30, 0.40}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{0.50, 0.60}),
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();
    auto resp = callDetect(1);
    ASSERT_NE(resp, nullptr);
    EXPECT_TRUE(resp->success);

    // Positions are encoded as int32 mm triplets: x,y,z, x,y,z, ...
    ASSERT_EQ(resp->data.size(), 6u);  // 2 positions * 3 coords

    // First position
    EXPECT_EQ(resp->data[0], 100);  // 0.10 * 1000
    EXPECT_EQ(resp->data[1], 300);  // 0.30 * 1000
    EXPECT_EQ(resp->data[2], 500);  // 0.50 * 1000

    // Second position
    EXPECT_EQ(resp->data[3], 200);  // 0.20 * 1000
    EXPECT_EQ(resp->data[4], 400);  // 0.40 * 1000
    EXPECT_EQ(resp->data[5], 600);  // 0.60 * 1000
}

// 3. Default simulated positions are returned when none explicitly configured
TEST_F(SimulationModeTest, DefaultSimulatedPositionsExist)
{
    createSimNode({
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();
    auto resp = callDetect(1);
    ASSERT_NE(resp, nullptr);
    EXPECT_TRUE(resp->success);

    // Defaults from cotton_detection_node_parameters.cpp:
    //   x=[0.40, 0.35, 0.50], y=[-0.15, -0.10, -0.15], z=[0.10, 0.10, 0.10]
    ASSERT_EQ(resp->data.size(), 9u);  // 3 positions * 3 coords

    EXPECT_EQ(resp->data[0], 400);   // 0.40 * 1000
    EXPECT_EQ(resp->data[1], -150);  // -0.15 * 1000
    EXPECT_EQ(resp->data[2], 100);   // 0.10 * 1000

    EXPECT_EQ(resp->data[3], 350);   // 0.35 * 1000
    EXPECT_EQ(resp->data[4], -100);  // -0.10 * 1000
    EXPECT_EQ(resp->data[5], 100);   // 0.10 * 1000

    EXPECT_EQ(resp->data[6], 500);   // 0.50 * 1000
    EXPECT_EQ(resp->data[7], -150);  // -0.15 * 1000
    EXPECT_EQ(resp->data[8], 100);   // 0.10 * 1000
}

// 4. Empty position list produces success=true but empty data
TEST_F(SimulationModeTest, EmptyPositionListReturnsEmptyData)
{
    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{}),
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();
    auto resp = callDetect(1);
    ASSERT_NE(resp, nullptr);
    EXPECT_TRUE(resp->success);
    EXPECT_TRUE(resp->data.empty());
}

// 5. Detect command=1 returns success and correct message
TEST_F(SimulationModeTest, DetectCommandReturnsSuccessWithMessage)
{
    createSimNode();

    warmup();
    auto resp = callDetect(1);
    ASSERT_NE(resp, nullptr);
    EXPECT_TRUE(resp->success);
    EXPECT_EQ(resp->message, "Detection completed successfully");
}

// 6. Positions include noise when simulation_noise_stddev > 0
TEST_F(SimulationModeTest, PositionsVaryWithNoiseEnabled)
{
    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{0.50}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{0.00}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{0.10}),
        rclcpp::Parameter("simulation_noise_stddev", 0.01),  // 10mm stddev
    });

    warmup();

    // Collect positions across multiple calls - at least one should differ
    std::vector<int32_t> first_data;
    bool found_difference = false;
    constexpr int NUM_CALLS = 10;

    for (int i = 0; i < NUM_CALLS; ++i) {
        auto resp = callDetect(1);
        ASSERT_NE(resp, nullptr);
        EXPECT_TRUE(resp->success);
        ASSERT_EQ(resp->data.size(), 3u);

        if (first_data.empty()) {
            first_data = resp->data;
        } else {
            for (size_t j = 0; j < resp->data.size(); ++j) {
                if (resp->data[j] != first_data[j]) {
                    found_difference = true;
                    break;
                }
            }
        }
        if (found_difference) break;
    }

    EXPECT_TRUE(found_difference)
        << "After " << NUM_CALLS << " calls with noise_stddev=0.01, "
        << "expected at least one position to differ";
}

// 7. Positions are deterministic when noise is disabled (stddev=0)
TEST_F(SimulationModeTest, PositionsDeterministicWithNoiseDisabled)
{
    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{0.55, 0.50}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{0.04, -0.03}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{0.09, 0.17}),
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();

    auto resp1 = callDetect(1);
    auto resp2 = callDetect(1);
    ASSERT_NE(resp1, nullptr);
    ASSERT_NE(resp2, nullptr);

    ASSERT_EQ(resp1->data.size(), resp2->data.size());
    for (size_t i = 0; i < resp1->data.size(); ++i) {
        EXPECT_EQ(resp1->data[i], resp2->data[i])
            << "Position data[" << i << "] differs between calls with noise disabled";
    }
}

// 8. Confidence values are within [min, max] range (via topic)
TEST_F(SimulationModeTest, ConfidenceValuesWithinRange)
{
    const double conf_min = 0.60;
    const double conf_max = 0.85;
    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{0.50, 0.55}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{0.00, 0.05}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{0.10, 0.15}),
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
        rclcpp::Parameter("simulation_confidence_min", conf_min),
        rclcpp::Parameter("simulation_confidence_max", conf_max),
    });

    warmup();

    // Call multiple times and check confidence on each
    constexpr int NUM_CALLS = 5;
    for (int call = 0; call < NUM_CALLS; ++call) {
        auto result_msg = callDetectAndCaptureTopic(1);
        ASSERT_NE(result_msg, nullptr) << "Failed to capture topic on call " << call;

        for (size_t i = 0; i < result_msg->positions.size(); ++i) {
            float conf = result_msg->positions[i].confidence;
            EXPECT_GE(conf, static_cast<float>(conf_min))
                << "Confidence " << conf << " below min " << conf_min
                << " (call=" << call << ", pos=" << i << ")";
            EXPECT_LE(conf, static_cast<float>(conf_max))
                << "Confidence " << conf << " above max " << conf_max
                << " (call=" << call << ", pos=" << i << ")";
        }
    }
}

// 9. Detection IDs increment sequentially across calls (1-indexed)
TEST_F(SimulationModeTest, DetectionIDsIncrementAcrossCalls)
{
    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{0.50, 0.55}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{0.00, 0.05}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{0.10, 0.15}),
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();

    // First real call: IDs should start from some value and be sequential
    auto result_msg1 = callDetectAndCaptureTopic(1);
    ASSERT_NE(result_msg1, nullptr);
    ASSERT_EQ(result_msg1->positions.size(), 2u);

    int32_t first_id = result_msg1->positions[0].detection_id;
    EXPECT_EQ(result_msg1->positions[1].detection_id, first_id + 1);

    // Second call: IDs should continue from where the first left off
    auto result_msg2 = callDetectAndCaptureTopic(1);
    ASSERT_NE(result_msg2, nullptr);
    ASSERT_EQ(result_msg2->positions.size(), 2u);

    EXPECT_EQ(result_msg2->positions[0].detection_id, first_id + 2);
    EXPECT_EQ(result_msg2->positions[1].detection_id, first_id + 3);
}

// 10. Processing time is positive and reasonable
TEST_F(SimulationModeTest, ProcessingTimeReasonable)
{
    createSimNode({
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();
    auto result_msg = callDetectAndCaptureTopic(1);
    ASSERT_NE(result_msg, nullptr);

    // The simulation path has a 5ms sleep, so processing_time should be >= 5ms
    // and well under 100ms (no actual image processing)
    EXPECT_GT(result_msg->processing_time_ms, 0.0f)
        << "Processing time should be positive";
    EXPECT_LT(result_msg->processing_time_ms, 100.0f)
        << "Processing time should be under 100ms in simulation mode";
}

// 11. Stop command (command=0) returns success with empty data
TEST_F(SimulationModeTest, StopCommandReturnsSuccess)
{
    createSimNode();

    warmup();
    auto resp = callDetect(0);
    ASSERT_NE(resp, nullptr);
    EXPECT_TRUE(resp->success);
    EXPECT_TRUE(resp->data.empty());
}

// 11b. Calibrate command (command=2) returns success with empty data in simulation mode
TEST_F(SimulationModeTest, CalibrateCommandReturnsSuccessInSimMode)
{
    createSimNode();

    warmup();
    auto resp = callDetect(2);
    ASSERT_NE(resp, nullptr);
    EXPECT_TRUE(resp->success);
    EXPECT_TRUE(resp->data.empty());
}

// 12. Unknown command returns failure
TEST_F(SimulationModeTest, UnknownCommandReturnsFalse)
{
    createSimNode();

    warmup();
    auto resp = callDetect(99);
    ASSERT_NE(resp, nullptr);
    EXPECT_FALSE(resp->success);
}

// 13. Topic message total_count matches number of positions
TEST_F(SimulationModeTest, TopicTotalCountMatchesPositions)
{
    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{0.50, 0.55}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{0.00, 0.05}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{0.10, 0.15}),
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();
    auto result_msg = callDetectAndCaptureTopic(1);
    ASSERT_NE(result_msg, nullptr);

    EXPECT_EQ(result_msg->total_count, 2);
    EXPECT_EQ(result_msg->positions.size(), 2u);
    EXPECT_TRUE(result_msg->detection_successful);
}

// 14. Topic message header has valid stamp and frame_id
TEST_F(SimulationModeTest, TopicHeaderIsValid)
{
    createSimNode({
        rclcpp::Parameter("simulation_noise_stddev", 0.0),
    });

    warmup();
    auto result_msg = callDetectAndCaptureTopic(1);
    ASSERT_NE(result_msg, nullptr);

    // Stamp should be non-zero
    EXPECT_GT(result_msg->header.stamp.sec + result_msg->header.stamp.nanosec, 0u);
    // Frame ID should be camera_link (set by publish_detection_result)
    EXPECT_EQ(result_msg->header.frame_id, "camera_link");
}

// 15. Noise magnitude stays within reasonable bounds (6-sigma sanity)
TEST_F(SimulationModeTest, NoiseMagnitudeWithinBounds)
{
    const double base_x = 0.50;
    const double stddev = 0.005;  // 5mm

    createSimNode({
        rclcpp::Parameter("simulated_positions.x", std::vector<double>{base_x}),
        rclcpp::Parameter("simulated_positions.y", std::vector<double>{0.0}),
        rclcpp::Parameter("simulated_positions.z", std::vector<double>{0.1}),
        rclcpp::Parameter("simulation_noise_stddev", stddev),
    });

    warmup();

    // Collect x-values and verify they stay within 6-sigma of the base
    constexpr int NUM_CALLS = 20;
    const double bound = 6.0 * stddev;  // ~30mm — very generous

    for (int i = 0; i < NUM_CALLS; ++i) {
        auto resp = callDetect(1);
        ASSERT_NE(resp, nullptr);
        ASSERT_GE(resp->data.size(), 3u);

        double returned_x = resp->data[0] / 1000.0;
        double deviation = std::abs(returned_x - base_x);
        EXPECT_LT(deviation, bound)
            << "Position x=" << returned_x << " deviates " << deviation
            << " from base " << base_x << " (6-sigma bound=" << bound << ")";
    }
}

// ===========================================================================
// Main
// ===========================================================================

int main(int argc, char ** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
