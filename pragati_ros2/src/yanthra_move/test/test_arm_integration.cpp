/**
 * @file test_arm_integration.cpp
 * @brief Integration tests for the end-to-end arm simulation pipeline.
 *
 * Tests verify that motor_control and cotton_detection nodes work together
 * in simulation mode, exercising the ROS2 interfaces that the YanthraMoveSystem
 * orchestrator depends on:
 *   - Motor node publishes /joint_states and accepts position commands
 *   - Detection node provides cotton positions via service
 *   - Multiple detection cycles produce consistent results
 *   - Joint commands are reflected in joint state feedback
 *
 * These tests launch nodes as subprocesses and interact via ROS2 interfaces.
 * The YanthraMoveSystem node is NOT launched — its orchestration logic is
 * covered by the MotionController unit tests. This suite validates the
 * integration layer (topics, services, message flow) between the nodes
 * that the orchestrator depends on.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <std_msgs/msg/float64.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <cotton_detection_msgs/srv/cotton_detection.hpp>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using namespace std::chrono_literals;

namespace yanthra_move {

using CottonDetectionSrv = cotton_detection_msgs::srv::CottonDetection;

/**
 * @brief Fixture that launches motor_control and cotton_detection nodes as
 *        subprocesses in simulation mode, providing a test client node for
 *        ROS2 communication.
 *
 * SetUp launches both nodes, waits for /joint_states topic and the detection
 * service to become available. TearDown kills both subprocesses.
 */
class ArmIntegrationTest : public ::testing::Test
{
protected:
    static constexpr int NUM_MOTORS = 3;
    static constexpr auto NODE_STARTUP_TIMEOUT = 20s;
    static constexpr auto SERVICE_TIMEOUT = 15s;
    static constexpr auto COMMAND_SETTLE_TIMEOUT = 5s;

    // Unique node names to avoid collisions with other test suites
    static constexpr const char* MOTOR_NODE_NAME = "arm_integ_motor_sim";
    static constexpr const char* DETECTION_NODE_NAME = "arm_integ_detection_sim";

    // Detection service path — the node creates the service with relative name
    // "cotton_detection/detect", which ROS2 resolves under the node's namespace
    // (default "/"), NOT under the node name. So it's always /cotton_detection/detect.
    static constexpr const char* DETECTION_SERVICE =
        "/cotton_detection/detect";

    void SetUp() override
    {
        // Create test client node (isolated from global args)
        rclcpp::NodeOptions opts;
        opts.use_global_arguments(false);
        client_node_ = std::make_shared<rclcpp::Node>("arm_integ_test_client", opts);

        // Spin client node in a background thread
        executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
        executor_->add_node(client_node_);
        spin_thread_ = std::thread([this]() { executor_->spin(); });

        // Subscribe to /joint_states for motor node readiness tracking
        joint_state_received_.store(false);
        {
            std::lock_guard<std::mutex> lock(joint_state_mutex_);
            last_joint_state_ = nullptr;
        }
        joint_state_sub_ = client_node_->create_subscription<sensor_msgs::msg::JointState>(
            "/joint_states", 10,
            [this](sensor_msgs::msg::JointState::SharedPtr msg) {
                std::lock_guard<std::mutex> lock(joint_state_mutex_);
                last_joint_state_ = msg;
                joint_state_received_.store(true);
            });

        // Launch motor_control node subprocess
        // motor_ids [1,2,3] with default joint_names gives joint3, joint4, joint5
        // (matching the arm configuration the orchestrator expects)
        std::string motor_cmd =
            "ros2 run motor_control_ros2 mg6010_controller_node "
            "--ros-args "
            "-p simulation_mode:=true "
            "-p motor_ids:='[1,2,3]' "
            "-p joint_names:='[\"joint3\",\"joint4\",\"joint5\"]' "
            "-p min_positions:='[-180.0,-180.0,-180.0]' "
            "-p max_positions:='[180.0,180.0,180.0]' "
            "-r __node:=arm_integ_motor_sim "
            " &";

        int ret = std::system(motor_cmd.c_str());
        ASSERT_EQ(ret, 0) << "Failed to launch motor_control subprocess";

        // Launch cotton_detection node subprocess
        std::string detection_cmd =
            "ros2 run cotton_detection_ros2 cotton_detection_node "
            "--ros-args "
            "-p simulation_mode:=true "
            "-p \"simulated_positions.x:=[0.40, 0.35, 0.50]\" "
            "-p \"simulated_positions.y:=[-0.15, -0.10, -0.15]\" "
            "-p \"simulated_positions.z:=[0.10, 0.10, 0.10]\" "
            "-p simulation_noise_stddev:=0.0 "
            "-r __node:=arm_integ_detection_sim "
            " &";

        ret = std::system(detection_cmd.c_str());
        ASSERT_EQ(ret, 0) << "Failed to launch cotton_detection subprocess";

        // Wait for motor node: /joint_states must be published
        auto start = std::chrono::steady_clock::now();
        while (!joint_state_received_.load()) {
            if (std::chrono::steady_clock::now() - start > NODE_STARTUP_TIMEOUT) {
                GTEST_FAIL() << "Motor node did not publish /joint_states within "
                             << NODE_STARTUP_TIMEOUT.count() << "s timeout";
                return;
            }
            std::this_thread::sleep_for(100ms);
        }

        // Create detection service client
        detection_client_ = client_node_->create_client<CottonDetectionSrv>(
            DETECTION_SERVICE);

        // Wait for detection service to become available
        bool service_ready = detection_client_->wait_for_service(SERVICE_TIMEOUT);
        ASSERT_TRUE(service_ready)
            << "Detection service " << DETECTION_SERVICE
            << " not available within " << SERVICE_TIMEOUT.count() << "s timeout";

        // Allow extra DDS discovery time for all interfaces to settle
        std::this_thread::sleep_for(2s);
    }

    void TearDown() override
    {
        // Kill both subprocess nodes
        std::system(
            "pkill -f 'arm_integ_motor_sim' 2>/dev/null || true");
        std::system(
            "pkill -f 'arm_integ_detection_sim' 2>/dev/null || true");
        std::this_thread::sleep_for(1s);

        // Stop executor and join spin thread
        if (executor_) {
            executor_->cancel();
        }
        if (spin_thread_.joinable()) {
            spin_thread_.join();
        }

        // Reset all resources
        detection_client_.reset();
        joint_state_sub_.reset();
        client_node_.reset();
        executor_.reset();
    }

    // ----- Helpers -----

    /**
     * Call the detection service with the given command.
     * Returns nullptr on timeout or failure.
     */
    CottonDetectionSrv::Response::SharedPtr callDetection(int32_t command = 1)
    {
        auto request = std::make_shared<CottonDetectionSrv::Request>();
        request->detect_command = command;

        auto future = detection_client_->async_send_request(request);
        auto status = future.wait_for(10s);
        if (status != std::future_status::ready) {
            return nullptr;
        }
        return future.get();
    }

    /**
     * Publish a position command to a specific joint's position controller topic.
     * Joint names are "joint3", "joint4", "joint5" (matching motor_ids [1,2,3]).
     */
    void publishJointCommand(const std::string& joint_name, double position_rad)
    {
        std::string topic = "/" + joint_name + "_position_controller/command";
        auto pub = client_node_->create_publisher<std_msgs::msg::Float64>(topic, 10);
        // Allow publisher discovery
        std::this_thread::sleep_for(500ms);

        auto msg = std::make_shared<std_msgs::msg::Float64>();
        msg->data = position_rad;
        pub->publish(*msg);
    }

    /**
     * Wait until /joint_states reports a position for the given joint index
     * that is within tolerance of the expected value, or until timeout.
     * Returns true if the position converged.
     */
    bool waitForJointPosition(
        const std::string& joint_name,
        double expected_rad,
        double tolerance_rad,
        std::chrono::seconds timeout)
    {
        auto start = std::chrono::steady_clock::now();
        while (std::chrono::steady_clock::now() - start < timeout) {
            {
                std::lock_guard<std::mutex> lock(joint_state_mutex_);
                if (last_joint_state_) {
                    for (size_t i = 0; i < last_joint_state_->name.size(); ++i) {
                        if (last_joint_state_->name[i] == joint_name &&
                            i < last_joint_state_->position.size()) {
                            if (std::abs(last_joint_state_->position[i] - expected_rad)
                                <= tolerance_rad) {
                                return true;
                            }
                        }
                    }
                }
            }  // lock released here
            std::this_thread::sleep_for(100ms);
        }
        return false;
    }

    /**
     * Get the latest joint state snapshot (thread-safe copy).
     */
    sensor_msgs::msg::JointState::SharedPtr getLatestJointState()
    {
        std::lock_guard<std::mutex> lock(joint_state_mutex_);
        return last_joint_state_;
    }

    // ----- Members -----
    std::shared_ptr<rclcpp::Node> client_node_;
    std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
    std::thread spin_thread_;

    // Joint state tracking
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_state_sub_;
    std::atomic<bool> joint_state_received_{false};
    sensor_msgs::msg::JointState::SharedPtr last_joint_state_;
    std::mutex joint_state_mutex_;

    // Detection service client
    rclcpp::Client<CottonDetectionSrv>::SharedPtr detection_client_;
};

// ===========================================================================
// Test 6.1: Pipeline Nodes Launch Successfully
// ===========================================================================

/**
 * Verifies that both motor_control and cotton_detection nodes launch
 * in simulation mode and their primary interfaces become available:
 *   - /joint_states topic from motor node
 *   - Detection service from cotton_detection node
 *
 * SetUp already validates this; this test adds explicit interface checks.
 */
TEST_F(ArmIntegrationTest, PipelineNodesLaunchSuccessfully)
{
    // Motor node: /joint_states should have been received (SetUp guarantees this)
    EXPECT_TRUE(joint_state_received_.load())
        << "/joint_states topic not received from motor node";

    // Motor node: verify correct number of joints
    auto js = getLatestJointState();
    ASSERT_NE(js, nullptr) << "No joint_states message captured";
    EXPECT_EQ(js->name.size(), static_cast<size_t>(NUM_MOTORS))
        << "Expected " << NUM_MOTORS << " joints in joint_states";
    EXPECT_EQ(js->position.size(), static_cast<size_t>(NUM_MOTORS))
        << "Expected " << NUM_MOTORS << " positions in joint_states";

    // Detection node: service should be available (SetUp guarantees this)
    EXPECT_TRUE(detection_client_->service_is_ready())
        << "Detection service is not ready";
}

// ===========================================================================
// Test 6.2: Detection Service Returns Simulated Positions
// ===========================================================================

/**
 * Calls the detection service with detect_command=1 and verifies:
 *   - Response success=true
 *   - Response data contains 9 int32 values (3 positions x 3 coords)
 *   - Values approximately match configured simulated positions (in mm)
 *
 * Configured positions:
 *   x=[0.40, 0.45, 0.30]  -> mm: [400, 450, 300]
 *   y=[0.45, 0.50, 0.35]  -> mm: [450, 500, 350]
 *   z=[-0.30, -0.40, -0.15] -> mm: [-300, -400, -150]
 *
 * Data format: [x0,y0,z0, x1,y1,z1, x2,y2,z2]
 */
TEST_F(ArmIntegrationTest, DetectionServiceReturnsSimulatedPositions)
{
    // Warmup call (first call triggers warmup path in detection node)
    auto warmup_resp = callDetection(1);
    ASSERT_NE(warmup_resp, nullptr) << "Warmup detection call failed";

    // Actual detection call
    auto resp = callDetection(1);
    ASSERT_NE(resp, nullptr) << "Detection service call returned nullptr (timeout?)";
    EXPECT_TRUE(resp->success)
        << "Detection failed: " << resp->message;

    // Expect 3 positions * 3 coordinates = 9 values
    ASSERT_EQ(resp->data.size(), 9u)
        << "Expected 9 int32 values (3 positions x 3 coords), got "
        << resp->data.size();

    // Verify positions match configured values (noise=0, so exact match expected)
    // Position 0: (0.40, -0.15, 0.10) -> (400, -150, 100) mm
    EXPECT_EQ(resp->data[0], 400)  << "Position 0 X mismatch";
    EXPECT_EQ(resp->data[1], -150)  << "Position 0 Y mismatch";
    EXPECT_EQ(resp->data[2], 100) << "Position 0 Z mismatch";

    // Position 1: (0.35, -0.10, 0.10) -> (350, -100, 100) mm
    EXPECT_EQ(resp->data[3], 350)  << "Position 1 X mismatch";
    EXPECT_EQ(resp->data[4], -100)  << "Position 1 Y mismatch";
    EXPECT_EQ(resp->data[5], 100) << "Position 1 Z mismatch";

    // Position 2: (0.50, -0.15, 0.10) -> (500, -150, 100) mm
    EXPECT_EQ(resp->data[6], 500)  << "Position 2 X mismatch";
    EXPECT_EQ(resp->data[7], -150)  << "Position 2 Y mismatch";
    EXPECT_EQ(resp->data[8], 100) << "Position 2 Z mismatch";
}

// ===========================================================================
// Test 6.3: Detection Handles Stop Command Gracefully
// ===========================================================================

/**
 * Verifies that the detection service handles detect_command=0 (stop)
 * without error. The stop command should return success with empty data.
 */
TEST_F(ArmIntegrationTest, DetectionHandlesStopCommandGracefully)
{
    auto resp = callDetection(0);
    ASSERT_NE(resp, nullptr) << "Stop command call returned nullptr (timeout?)";
    EXPECT_TRUE(resp->success)
        << "Stop command should succeed, got: " << resp->message;
    EXPECT_TRUE(resp->data.empty())
        << "Stop command should return empty data, got " << resp->data.size() << " values";
}

// ===========================================================================
// Test 6.4: Motor Controller Accepts Joint Commands
// ===========================================================================

/**
 * Publishes a position command to joint3 and verifies that /joint_states
 * reflects the commanded position within tolerance.
 *
 * In simulation mode, the motor controller's physics simulation drives
 * positions toward commanded values. We use a small target (0.5 rad ~= 28.6 deg)
 * well within the +-180 degree limits.
 */
TEST_F(ArmIntegrationTest, MotorControllerAcceptsJointCommands)
{
    const double target_rad = 0.5;  // ~28.6 degrees
    const double tolerance_rad = 0.15;  // Generous tolerance for simulation convergence

    // Publish command to joint3
    publishJointCommand("joint3", target_rad);

    // Keep publishing to ensure the command is received (VOLATILE QoS means
    // the subscriber only gets messages published after it connected)
    auto pub = client_node_->create_publisher<std_msgs::msg::Float64>(
        "/joint3_position_controller/command", 10);
    std::this_thread::sleep_for(500ms);

    auto msg = std::make_shared<std_msgs::msg::Float64>();
    msg->data = target_rad;

    // Publish repeatedly and check convergence
    auto start = std::chrono::steady_clock::now();
    bool converged = false;
    while (std::chrono::steady_clock::now() - start < COMMAND_SETTLE_TIMEOUT) {
        pub->publish(*msg);
        std::this_thread::sleep_for(200ms);

        auto js = getLatestJointState();
        if (js) {
            for (size_t i = 0; i < js->name.size(); ++i) {
                if (js->name[i] == "joint3" && i < js->position.size()) {
                    if (std::abs(js->position[i] - target_rad) <= tolerance_rad) {
                        converged = true;
                        break;
                    }
                }
            }
        }
        if (converged) break;
    }

    EXPECT_TRUE(converged)
        << "joint3 did not converge to " << target_rad
        << " rad within " << COMMAND_SETTLE_TIMEOUT.count() << "s";
}

// ===========================================================================
// Test 6.5: Multiple Detection Cycles Don't Leak State
// ===========================================================================

/**
 * Calls the detection service twice in sequence and verifies:
 *   - Both calls return the same number of positions
 *   - Response data is identical (noise=0, so deterministic)
 *   - No corruption or state leakage between calls
 */
TEST_F(ArmIntegrationTest, MultipleDetectionCyclesDontLeakState)
{
    // Warmup call
    auto warmup_resp = callDetection(1);
    ASSERT_NE(warmup_resp, nullptr) << "Warmup detection call failed";

    // First detection call
    auto resp1 = callDetection(1);
    ASSERT_NE(resp1, nullptr) << "First detection call returned nullptr";
    EXPECT_TRUE(resp1->success) << "First detection failed: " << resp1->message;

    // Second detection call
    auto resp2 = callDetection(1);
    ASSERT_NE(resp2, nullptr) << "Second detection call returned nullptr";
    EXPECT_TRUE(resp2->success) << "Second detection failed: " << resp2->message;

    // Both should return the same number of values
    ASSERT_EQ(resp1->data.size(), resp2->data.size())
        << "Detection calls returned different data sizes: "
        << resp1->data.size() << " vs " << resp2->data.size();

    // With noise=0, data should be identical
    for (size_t i = 0; i < resp1->data.size(); ++i) {
        EXPECT_EQ(resp1->data[i], resp2->data[i])
            << "Data mismatch at index " << i << ": "
            << resp1->data[i] << " vs " << resp2->data[i]
            << " — possible state leakage between detection cycles";
    }

    // Verify consistent position count (3 positions = 9 values)
    EXPECT_EQ(resp1->data.size(), 9u)
        << "Expected 9 values (3 positions), got " << resp1->data.size();
}

// ===========================================================================
// Test 6.6: Joint States Reflect Simulated Motor Positions
// ===========================================================================

/**
 * Commands all three joints (joint3, joint4, joint5) to specific positions
 * and verifies that /joint_states reports positions matching the commands.
 *
 * This validates the full command->simulation->feedback loop for the motor
 * controller node in simulation mode.
 */
TEST_F(ArmIntegrationTest, JointStatesReflectSimulatedMotorPositions)
{
    // Target positions for each joint (all within +-180 deg = +-pi rad)
    struct JointTarget {
        std::string name;
        double target_rad;
    };

    std::vector<JointTarget> targets = {
        {"joint3", 0.3},   // ~17.2 degrees
        {"joint4", -0.2},  // ~-11.5 degrees
        {"joint5", 0.7},   // ~40.1 degrees
    };

    // Create publishers for all joints
    std::vector<rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr> pubs;
    for (const auto& target : targets) {
        std::string topic = "/" + target.name + "_position_controller/command";
        pubs.push_back(
            client_node_->create_publisher<std_msgs::msg::Float64>(topic, 10));
    }

    // Allow publisher discovery
    std::this_thread::sleep_for(1s);

    // Publish commands repeatedly and check convergence
    const double tolerance_rad = 0.15;
    auto start = std::chrono::steady_clock::now();
    std::vector<bool> converged(targets.size(), false);

    while (std::chrono::steady_clock::now() - start < 10s) {
        // Publish all commands
        for (size_t j = 0; j < targets.size(); ++j) {
            auto msg = std::make_shared<std_msgs::msg::Float64>();
            msg->data = targets[j].target_rad;
            pubs[j]->publish(*msg);
        }

        std::this_thread::sleep_for(200ms);

        // Check convergence
        auto js = getLatestJointState();
        if (js) {
            for (size_t j = 0; j < targets.size(); ++j) {
                for (size_t i = 0; i < js->name.size(); ++i) {
                    if (js->name[i] == targets[j].name &&
                        i < js->position.size()) {
                        if (std::abs(js->position[i] - targets[j].target_rad)
                            <= tolerance_rad) {
                            converged[j] = true;
                        }
                    }
                }
            }
        }

        // Check if all converged
        bool all_converged = true;
        for (bool c : converged) {
            if (!c) {
                all_converged = false;
                break;
            }
        }
        if (all_converged) break;
    }

    // Verify each joint converged
    for (size_t j = 0; j < targets.size(); ++j) {
        EXPECT_TRUE(converged[j])
            << targets[j].name << " did not converge to "
            << targets[j].target_rad << " rad within 10s timeout";
    }
}

}  // namespace yanthra_move

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    ::testing::InitGoogleTest(&argc, argv);
    int result = RUN_ALL_TESTS();
    rclcpp::shutdown();
    return result;
}
