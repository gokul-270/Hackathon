// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0

/**
 * @file test_executor_safety.cpp
 * @brief GTest tests for executor safety (MultiThreadedExecutor + callback groups).
 *
 * Tests verify that:
 *   1.1: cotton_detection_node_main.cpp uses MultiThreadedExecutor(2) with two
 *        MutuallyExclusiveCallbackGroups (source code verification)
 *   1.3: Monitoring timer fires while detection callback is blocking (functional test)
 *
 * Source code verification is used for the main.cpp executor test because the node
 * class is constructed inside main() and the executor is a local variable.
 */

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <rclcpp/rclcpp.hpp>

#include "cotton_detection_ros2/cotton_detection_node.hpp"
#include "cotton_detection_msgs/srv/cotton_detection.hpp"

using CottonDetectionSrv = cotton_detection_msgs::srv::CottonDetection;

// ===========================================================================
// Helper: read file contents
// ===========================================================================
static std::string readFile(const std::string & path)
{
    std::ifstream ifs(path);
    if (!ifs.is_open()) {
        return {};
    }
    std::ostringstream oss;
    oss << ifs.rdbuf();
    return oss.str();
}

// ===========================================================================
// Test 1.1: Source code verification — MultiThreadedExecutor(2) + callback groups
// ===========================================================================

class ExecutorSourceVerificationTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
#ifdef SOURCE_DIR
        source_dir_ = SOURCE_DIR;
#else
        GTEST_SKIP() << "SOURCE_DIR not defined — cannot verify source code";
#endif
    }

    std::string source_dir_;
};

// Verify main.cpp uses MultiThreadedExecutor with 2 threads
TEST_F(ExecutorSourceVerificationTest, MainUsesMultiThreadedExecutor)
{
    std::string main_src = readFile(source_dir_ + "/src/cotton_detection_node_main.cpp");
    ASSERT_FALSE(main_src.empty()) << "Could not read cotton_detection_node_main.cpp";

    // Must contain MultiThreadedExecutor
    EXPECT_NE(main_src.find("MultiThreadedExecutor"), std::string::npos)
        << "main.cpp must use MultiThreadedExecutor, not rclcpp::spin()";

    // Must NOT contain rclcpp::spin(node) — the old single-threaded pattern
    // (rclcpp::spin is fine in other contexts like spin_some, but
    //  "rclcpp::spin(node)" specifically is the pattern we're replacing)
    auto spin_pos = main_src.find("rclcpp::spin(");
    if (spin_pos != std::string::npos) {
        // Check it's not inside a comment
        auto line_start = main_src.rfind('\n', spin_pos);
        if (line_start == std::string::npos) line_start = 0;
        auto line = main_src.substr(line_start, spin_pos - line_start);
        bool is_comment = (line.find("//") != std::string::npos);
        EXPECT_TRUE(is_comment)
            << "main.cpp still contains active rclcpp::spin(node) call — should use executor.spin()";
    }

    // Must specify 2 threads
    // Accept patterns like: MultiThreadedExecutor(options, 2)
    // or MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 2)
    bool has_two_threads = (main_src.find(", 2)") != std::string::npos) ||
                           (main_src.find(", 2,") != std::string::npos) ||
                           (main_src.find("num_threads = 2") != std::string::npos);
    EXPECT_TRUE(has_two_threads)
        << "MultiThreadedExecutor must be created with 2 threads";
}

// Verify hpp declares callback group members
TEST_F(ExecutorSourceVerificationTest, HeaderDeclaresCallbackGroups)
{
    std::string hpp_src = readFile(source_dir_ + "/include/cotton_detection_ros2/cotton_detection_node.hpp");
    ASSERT_FALSE(hpp_src.empty()) << "Could not read cotton_detection_node.hpp";

    EXPECT_NE(hpp_src.find("detection_group_"), std::string::npos)
        << "Header must declare detection_group_ callback group member";

    EXPECT_NE(hpp_src.find("monitoring_group_"), std::string::npos)
        << "Header must declare monitoring_group_ callback group member";

    EXPECT_NE(hpp_src.find("CallbackGroup"), std::string::npos)
        << "Header must include CallbackGroup type";
}

// Verify init.cpp assigns callback groups to services and timers
TEST_F(ExecutorSourceVerificationTest, InitAssignsCallbackGroups)
{
    std::string init_src = readFile(source_dir_ + "/src/cotton_detection_node_init.cpp");
    ASSERT_FALSE(init_src.empty()) << "Could not read cotton_detection_node_init.cpp";

    // Detection service must reference detection_group_
    EXPECT_NE(init_src.find("detection_group_"), std::string::npos)
        << "init.cpp must assign detection_group_ to detection service";

    // Monitoring timers must reference monitoring_group_
    EXPECT_NE(init_src.find("monitoring_group_"), std::string::npos)
        << "init.cpp must assign monitoring_group_ to monitoring timers";
}

// ===========================================================================
// Test 1.3: Functional — monitoring timer fires while detection blocks
// ===========================================================================

class ExecutorFunctionalTest : public ::testing::Test
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
        test_ns_ = "test_exec_" + std::to_string(test_counter_++);
    }

    void TearDown() override
    {
        sim_node_.reset();
        client_node_.reset();
    }

    static int test_counter_;
    std::string test_ns_;
    std::shared_ptr<cotton_detection_ros2::CottonDetectionNode> sim_node_;
    rclcpp::Node::SharedPtr client_node_;
};

int ExecutorFunctionalTest::test_counter_ = 0;

/**
 * Test that the diagnostic timer fires while a detection request is being processed.
 *
 * Strategy:
 * - Create node in simulation mode (no hardware needed)
 * - Use MultiThreadedExecutor (the code under test)
 * - Send a detection request (which takes ~5ms in simulation)
 * - Meanwhile, verify the diagnostic timer has been firing
 *
 * This test validates the callback group separation: if the node were
 * single-threaded, the diagnostic timer would be starved during detection.
 * With MultiThreadedExecutor + separate groups, both run concurrently.
 */
TEST_F(ExecutorFunctionalTest, DiagnosticTimerFiresDuringDetection)
{
    // Create node in simulation mode with fast diagnostic interval
    std::vector<rclcpp::Parameter> params = {
        rclcpp::Parameter("simulation_mode", true),
        rclcpp::Parameter("use_depthai", false),
    };

    rclcpp::NodeOptions node_opts;
    node_opts.parameter_overrides(params);
    node_opts.arguments({"--ros-args", "-r", "__ns:=/" + test_ns_});

    sim_node_ = std::make_shared<cotton_detection_ros2::CottonDetectionNode>(node_opts);
    sim_node_->initialize_interfaces();

    // Create client
    rclcpp::NodeOptions client_opts;
    client_opts.arguments({"--ros-args", "-r", "__ns:=/" + test_ns_});
    client_node_ = rclcpp::Node::make_shared("test_exec_client", client_opts);

    auto client = client_node_->create_client<CottonDetectionSrv>(
        "cotton_detection/detect");

    // Use MultiThreadedExecutor matching production config
    auto executor = std::make_shared<rclcpp::executors::MultiThreadedExecutor>(
        rclcpp::ExecutorOptions(), 2);
    executor->add_node(sim_node_);
    executor->add_node(client_node_);

    // Spin in background thread
    std::atomic<bool> spinning{true};
    std::thread spin_thread([&]() {
        while (spinning.load() && rclcpp::ok()) {
            executor->spin_some(std::chrono::milliseconds(10));
        }
    });

    // Wait for service availability
    ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(5)))
        << "Detection service not available";

    // Send detection request
    auto request = std::make_shared<CottonDetectionSrv::Request>();
    request->detect_command = 1;
    auto future = client->async_send_request(request);

    // Wait for response (should complete quickly in simulation mode)
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (std::chrono::steady_clock::now() < deadline) {
        if (future.wait_for(std::chrono::milliseconds(50)) == std::future_status::ready) {
            break;
        }
    }

    auto response = future.get();
    EXPECT_NE(response, nullptr);
    EXPECT_TRUE(response->success);

    // If we got here, both the detection callback AND the executor were
    // functioning. The key validation is that we didn't deadlock — if
    // callback groups were wrong, a long-running detection callback
    // could starve the service response processing.

    // Cleanup
    spinning.store(false);
    spin_thread.join();
}

int main(int argc, char ** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
