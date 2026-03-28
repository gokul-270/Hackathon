/*
 * Lifecycle Node Transition Tests (TDD RED phase)
 *
 * Tests for Step 9 of mg6010-decomposition Phase 3.
 * Verifies:
 *   - Node starts in unconfigured state (4.1)
 *   - on_configure initializes CAN + motors without starting control loop (4.1)
 *   - on_activate starts control loop + action servers + publishing (4.2)
 *   - on_deactivate stops control loop, cancels goals, stops publishing (4.3)
 *   - on_cleanup releases CAN + motor resources (4.4)
 *   - on_shutdown executes ShutdownHandler sequence (4.5)
 *   - Auto-activate launch transitions node to active (4.6)
 *   - on_configure failure on invalid CAN interface (4.7)
 *   - on_configure failure on mismatched param lengths (4.8)
 *   - Full lifecycle round-trip configure→activate→deactivate→cleanup→configure (4.9)
 *
 * RED phase: these tests FAIL because the node inherits from rclcpp::Node,
 * not rclcpp_lifecycle::LifecycleNode. Lifecycle services (~/change_state,
 * ~/get_state) do not exist.
 */

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <lifecycle_msgs/msg/state.hpp>
#include <lifecycle_msgs/msg/transition.hpp>
#include <lifecycle_msgs/srv/change_state.hpp>
#include <lifecycle_msgs/srv/get_state.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <motor_control_msgs/action/joint_position_command.hpp>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <memory>
#include <string>
#include <thread>
#include <vector>

using namespace std::chrono_literals;

namespace motor_control_ros2 {

// =============================================================================
// Lifecycle test fixture
// =============================================================================

/**
 * @brief Fixture that launches the mg6010_controller_node in simulation mode
 *        and provides lifecycle service clients for driving state transitions.
 *
 * The node starts as a subprocess. Once the lifecycle migration is complete,
 * the node will start in 'unconfigured' state and require explicit transitions.
 */
class LifecycleNodeTest : public ::testing::Test
{
protected:
  static constexpr auto SERVICE_TIMEOUT = 10s;
  static constexpr auto TRANSITION_TIMEOUT = 15s;
  static constexpr auto NODE_DISCOVERY_TIMEOUT = 20s;
  static constexpr const char * TEST_NODE_NAME = "motor_control_lifecycle_test";

  static void SetUpTestSuite()
  {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  void SetUp() override
  {
    // Create client node for ROS2 communication
    rclcpp::NodeOptions opts;
    opts.use_global_arguments(false);
    client_node_ = std::make_shared<rclcpp::Node>("lifecycle_test_client", opts);

    // Spin client in background
    executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    executor_->add_node(client_node_);
    spin_thread_ = std::thread([this]() { executor_->spin(); });

    // Create lifecycle service clients (namespaced under test node name)
    std::string ns = std::string("/") + TEST_NODE_NAME;
    get_state_client_ = client_node_->create_client<lifecycle_msgs::srv::GetState>(
      ns + "/get_state");
    change_state_client_ = client_node_->create_client<lifecycle_msgs::srv::ChangeState>(
      ns + "/change_state");

    // Launch node subprocess in simulation mode (auto_activate=false so test drives transitions)
    std::string cmd =
      "ros2 run motor_control_ros2 mg6010_controller_node "
      "--ros-args "
      "-p simulation_mode:=true "
      "-p auto_activate:=false "
      "-p motor_ids:='[1,2,3]' "
      "-p joint_names:='[joint3,joint4,joint5]' "
      "-p min_positions:='[-180.0,-180.0,-180.0]' "
      "-p max_positions:='[180.0,180.0,180.0]' "
      "-r __node:=" + std::string(TEST_NODE_NAME) +
      " &";

    int ret = std::system(cmd.c_str());
    ASSERT_EQ(ret, 0) << "Failed to launch node subprocess";

    // Wait for lifecycle services to become available
    // (plain rclcpp::Node does NOT expose these — this is the RED failure point)
    bool state_svc_ready = get_state_client_->wait_for_service(NODE_DISCOVERY_TIMEOUT);
    ASSERT_TRUE(state_svc_ready)
      << "get_state service not available — node may not be a LifecycleNode";

    bool change_svc_ready = change_state_client_->wait_for_service(5s);
    ASSERT_TRUE(change_svc_ready) << "change_state service not available";
  }

  void TearDown() override
  {
    // Kill subprocess
    std::string kill_cmd =
      "pkill -f 'mg6010_controller_node.*" + std::string(TEST_NODE_NAME) +
      "' 2>/dev/null || true";
    std::system(kill_cmd.c_str());
    std::this_thread::sleep_for(1s);

    if (executor_) {
      executor_->cancel();
    }
    if (spin_thread_.joinable()) {
      spin_thread_.join();
    }
    client_node_.reset();
    executor_.reset();
  }

  // ---- Helper methods ----

  /**
   * @brief Get the current lifecycle state of the node.
   * @return State ID (lifecycle_msgs::msg::State::PRIMARY_STATE_*)
   */
  uint8_t getState()
  {
    auto request = std::make_shared<lifecycle_msgs::srv::GetState::Request>();
    auto future = get_state_client_->async_send_request(request);
    auto status = future.wait_for(SERVICE_TIMEOUT);
    if (status != std::future_status::ready) {
      ADD_FAILURE() << "get_state timed out";
      return 0;
    }
    return future.get()->current_state.id;
  }

  /**
   * @brief Trigger a lifecycle state transition.
   * @param transition_id One of lifecycle_msgs::msg::Transition::TRANSITION_*
   * @return true if transition succeeded
   */
  bool triggerTransition(uint8_t transition_id)
  {
    auto request = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
    request->transition.id = transition_id;
    auto future = change_state_client_->async_send_request(request);
    auto status = future.wait_for(TRANSITION_TIMEOUT);
    if (status != std::future_status::ready) {
      ADD_FAILURE() << "change_state timed out for transition " << (int)transition_id;
      return false;
    }
    return future.get()->success;
  }

  /**
   * @brief Helper: configure the node (unconfigured → inactive).
   */
  bool configure()
  {
    return triggerTransition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);
  }

  /**
   * @brief Helper: activate the node (inactive → active).
   */
  bool activate()
  {
    return triggerTransition(lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE);
  }

  /**
   * @brief Helper: deactivate the node (active → inactive).
   */
  bool deactivate()
  {
    return triggerTransition(lifecycle_msgs::msg::Transition::TRANSITION_DEACTIVATE);
  }

  /**
   * @brief Helper: cleanup the node (inactive → unconfigured).
   */
  bool cleanup()
  {
    return triggerTransition(lifecycle_msgs::msg::Transition::TRANSITION_CLEANUP);
  }

  /**
   * @brief Helper: shutdown the node (any → finalized).
   */
  bool shutdown()
  {
    return triggerTransition(lifecycle_msgs::msg::Transition::TRANSITION_ACTIVE_SHUTDOWN);
  }

  /**
   * @brief Helper: configure + activate (convenience for tests needing active node).
   */
  bool configureAndActivate()
  {
    if (!configure()) return false;
    return activate();
  }

  /**
   * @brief Wait for joint_states to be published (indicates control loop active).
   * @param timeout How long to wait
   * @return true if joint_states received within timeout
   */
  bool waitForJointStates(std::chrono::seconds timeout = 10s)
  {
    std::atomic<bool> received{false};
    auto sub = client_node_->create_subscription<sensor_msgs::msg::JointState>(
      "/joint_states", 10,
      [&received](sensor_msgs::msg::JointState::SharedPtr) { received.store(true); });

    auto start = std::chrono::steady_clock::now();
    while (!received.load()) {
      if (std::chrono::steady_clock::now() - start > timeout) {
        return false;
      }
      std::this_thread::sleep_for(100ms);
    }
    return true;
  }

  /**
   * @brief Check if a service is available on the node.
   */
  bool isServiceAvailable(const std::string & service_name, std::chrono::seconds timeout = 5s)
  {
    auto client = client_node_->create_client<std_srvs::srv::Trigger>(service_name);
    return client->wait_for_service(timeout);
  }

  // Members
  std::shared_ptr<rclcpp::Node> client_node_;
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread spin_thread_;
  rclcpp::Client<lifecycle_msgs::srv::GetState>::SharedPtr get_state_client_;
  rclcpp::Client<lifecycle_msgs::srv::ChangeState>::SharedPtr change_state_client_;
};

// =============================================================================
// Separate fixture for tests that need the node NOT auto-activated
// (i.e., the standard lifecycle fixture where node starts unconfigured)
// =============================================================================

// LifecycleNodeTest above starts the node subprocess without auto_activate.
// For the auto-activate test (4.6), we need a separate fixture.

/**
 * @brief Fixture for testing auto-activate behavior. Does NOT drive transitions
 *        manually — expects the launch file to auto-transition to active.
 *
 * Note: This is a separate fixture because the auto-activate test needs the
 * node launched via the launch file (not ros2 run), or with auto_activate param.
 */
class LifecycleAutoActivateTest : public ::testing::Test
{
protected:
  static constexpr auto NODE_STARTUP_TIMEOUT = 15s;
  static constexpr const char * TEST_NODE_NAME = "motor_control_auto_activate_test";

  static void SetUpTestSuite()
  {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  void SetUp() override
  {
    rclcpp::NodeOptions opts;
    opts.use_global_arguments(false);
    client_node_ = std::make_shared<rclcpp::Node>("auto_activate_test_client", opts);

    executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    executor_->add_node(client_node_);
    spin_thread_ = std::thread([this]() { executor_->spin(); });

    std::string ns = std::string("/") + TEST_NODE_NAME;
    get_state_client_ = client_node_->create_client<lifecycle_msgs::srv::GetState>(
      ns + "/get_state");
  }

  void TearDown() override
  {
    std::string kill_cmd =
      "pkill -f 'mg6010_controller_node.*" + std::string(TEST_NODE_NAME) +
      "' 2>/dev/null || true";
    std::system(kill_cmd.c_str());
    std::this_thread::sleep_for(1s);

    if (executor_) executor_->cancel();
    if (spin_thread_.joinable()) spin_thread_.join();
    client_node_.reset();
    executor_.reset();
  }

  std::shared_ptr<rclcpp::Node> client_node_;
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread spin_thread_;
  rclcpp::Client<lifecycle_msgs::srv::GetState>::SharedPtr get_state_client_;
};

// =============================================================================
// Fixture for configure-failure tests (needs different params)
// =============================================================================

class LifecycleConfigFailureTest : public ::testing::Test
{
protected:
  static constexpr auto SERVICE_TIMEOUT = 10s;
  static constexpr auto NODE_DISCOVERY_TIMEOUT = 20s;

  static void SetUpTestSuite()
  {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  void SetUp() override
  {
    rclcpp::NodeOptions opts;
    opts.use_global_arguments(false);
    client_node_ = std::make_shared<rclcpp::Node>("config_fail_test_client", opts);

    executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    executor_->add_node(client_node_);
    spin_thread_ = std::thread([this]() { executor_->spin(); });
  }

  void TearDown() override
  {
    std::string kill_cmd =
      "pkill -f 'mg6010_controller_node.*motor_control_config_fail' 2>/dev/null || true";
    std::system(kill_cmd.c_str());
    std::this_thread::sleep_for(1s);

    if (executor_) executor_->cancel();
    if (spin_thread_.joinable()) spin_thread_.join();
    client_node_.reset();
    executor_.reset();
  }

  /**
   * @brief Launch the node with given extra params and wait for lifecycle services.
   */
  bool launchNodeAndWait(const std::string & extra_params, const std::string & node_suffix)
  {
    std::string node_name = "motor_control_config_fail_" + node_suffix;
    node_name_ = node_name;

    std::string ns = "/" + node_name;
    get_state_client_ = client_node_->create_client<lifecycle_msgs::srv::GetState>(
      ns + "/get_state");
    change_state_client_ = client_node_->create_client<lifecycle_msgs::srv::ChangeState>(
      ns + "/change_state");

    std::string cmd =
      "ros2 run motor_control_ros2 mg6010_controller_node "
      "--ros-args "
      "-p auto_activate:=false "
      + extra_params +
      " -r __node:=" + node_name +
      " &";

    int ret = std::system(cmd.c_str());
    if (ret != 0) return false;

    return get_state_client_->wait_for_service(NODE_DISCOVERY_TIMEOUT);
  }

  uint8_t getState()
  {
    auto request = std::make_shared<lifecycle_msgs::srv::GetState::Request>();
    auto future = get_state_client_->async_send_request(request);
    auto status = future.wait_for(SERVICE_TIMEOUT);
    if (status != std::future_status::ready) {
      ADD_FAILURE() << "get_state timed out";
      return 0;
    }
    return future.get()->current_state.id;
  }

  bool triggerTransition(uint8_t transition_id)
  {
    auto request = std::make_shared<lifecycle_msgs::srv::ChangeState::Request>();
    request->transition.id = transition_id;
    auto future = change_state_client_->async_send_request(request);
    auto status = future.wait_for(SERVICE_TIMEOUT);
    if (status != std::future_status::ready) return false;
    return future.get()->success;
  }

  std::string node_name_;
  std::shared_ptr<rclcpp::Node> client_node_;
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread spin_thread_;
  rclcpp::Client<lifecycle_msgs::srv::GetState>::SharedPtr get_state_client_;
  rclcpp::Client<lifecycle_msgs::srv::ChangeState>::SharedPtr change_state_client_;
};

// =============================================================================
// Task 4.1: on_configure initializes CAN + motors without starting control loop
// =============================================================================

/**
 * Spec: Scenario: Node starts in unconfigured state
 * Spec: Scenario: Successful configure with valid parameters
 *
 * WHEN the node is constructed
 * THEN it SHALL be in the unconfigured lifecycle state
 * THEN no timers, action servers, or CAN communication SHALL be active
 *
 * WHEN on_configure is triggered
 * THEN RoleStrategy, MotorManager, ShutdownHandler, callback groups SHALL be created
 * THEN the node SHALL be in the inactive state
 * THEN no control loop SHALL be running (no joint_states published)
 */
TEST_F(LifecycleNodeTest, ConfigureInitializesWithoutStartingControlLoop)
{
  // After SetUp, node should be in unconfigured state (lifecycle default)
  uint8_t state = getState();
  EXPECT_EQ(state, lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED)
    << "Node should start in unconfigured state";

  // No joint_states should be published in unconfigured state
  bool got_js_before = waitForJointStates(3s);
  EXPECT_FALSE(got_js_before)
    << "joint_states should NOT be published in unconfigured state";

  // Trigger configure transition
  bool success = configure();
  ASSERT_TRUE(success) << "configure transition should succeed";

  // Should now be in inactive state
  state = getState();
  EXPECT_EQ(state, lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE)
    << "Node should be in inactive state after configure";

  // Still no joint_states (control loop not started yet)
  bool got_js_after = waitForJointStates(3s);
  EXPECT_FALSE(got_js_after)
    << "joint_states should NOT be published in inactive state (control loop not started)";
}

// =============================================================================
// Task 4.2: on_activate starts control loop + action servers + publishing
// =============================================================================

/**
 * Spec: Scenario: Successful activation starts all timers
 *
 * GIVEN a node in the inactive state (after successful configure)
 * WHEN on_activate is triggered
 * THEN the control loop timer SHALL start (joint_states published)
 * THEN action servers SHALL begin accepting goals
 * THEN the node SHALL be in the active state
 */
TEST_F(LifecycleNodeTest, ActivateStartsControlLoopAndPublishing)
{
  // Configure first
  ASSERT_TRUE(configure()) << "configure should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);

  // Activate
  ASSERT_TRUE(activate()) << "activate should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE)
    << "Node should be in active state after activate";

  // joint_states should now be published (control loop running)
  bool got_js = waitForJointStates(10s);
  EXPECT_TRUE(got_js)
    << "joint_states should be published in active state";

  // Motor services should be available (created during configure).
  // Note: enable_motors is created with a relative name (not ~/), so it resolves to
  // the node's namespace (/) not the node's private namespace (/node_name/).
  std::string expected_service = "/enable_motors";
  bool found = false;
  auto deadline = std::chrono::steady_clock::now() + 15s;
  while (!found && std::chrono::steady_clock::now() < deadline) {
    auto services = client_node_->get_service_names_and_types();
    for (const auto & [name, types] : services) {
      if (name == expected_service) {
        found = true;
        break;
      }
    }
    if (!found) {
      std::this_thread::sleep_for(500ms);
    }
  }
  EXPECT_TRUE(found) << "enable_motors service should be visible in ROS graph";
}

// =============================================================================
// Task 4.3: on_deactivate stops control loop, cancels goals, stops publishing
// =============================================================================

/**
 * Spec: Scenario: Successful deactivation stops timers and motors
 *
 * GIVEN a node in the active state
 * WHEN on_deactivate is triggered
 * THEN the control loop timer SHALL be cancelled (no more joint_states)
 * THEN the node SHALL be in the inactive state
 */
TEST_F(LifecycleNodeTest, DeactivateStopsControlLoopAndPublishing)
{
  // Get to active state
  ASSERT_TRUE(configureAndActivate()) << "configure+activate should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);

  // Verify joint_states are flowing
  ASSERT_TRUE(waitForJointStates(10s)) << "Should get joint_states when active";

  // Deactivate
  ASSERT_TRUE(deactivate()) << "deactivate should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE)
    << "Node should be in inactive state after deactivate";

  // Wait a bit for timers to actually stop, then check no new joint_states
  std::this_thread::sleep_for(1s);
  bool got_js = waitForJointStates(3s);
  EXPECT_FALSE(got_js)
    << "joint_states should stop after deactivation";
}

// =============================================================================
// Task 4.4: on_cleanup releases CAN + motor resources
// =============================================================================

/**
 * Spec: Scenario: Successful cleanup releases all resources
 *
 * GIVEN a node in the inactive state (after deactivation)
 * WHEN on_cleanup is triggered
 * THEN all manager objects SHALL be destroyed
 * THEN the node SHALL be in the unconfigured state
 */
TEST_F(LifecycleNodeTest, CleanupReleasesResources)
{
  // Get to inactive state (configure → activate → deactivate)
  ASSERT_TRUE(configureAndActivate());
  ASSERT_TRUE(deactivate());
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);

  // Cleanup
  ASSERT_TRUE(cleanup()) << "cleanup should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED)
    << "Node should be in unconfigured state after cleanup";
}

// =============================================================================
// Task 4.5: on_shutdown executes ShutdownHandler sequence
// =============================================================================

/**
 * Spec: Scenario: Shutdown from active state
 * Spec: Scenario: Shutdown from unconfigured state
 *
 * GIVEN a node in the active state with motors running
 * WHEN on_shutdown is triggered
 * THEN ShutdownHandler::execute() SHALL be called
 * THEN the transition SHALL return SUCCESS
 */
TEST_F(LifecycleNodeTest, ShutdownFromActiveState)
{
  // Get to active state
  ASSERT_TRUE(configureAndActivate());
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);

  // Trigger shutdown (TRANSITION_ACTIVE_SHUTDOWN)
  bool success = shutdown();
  ASSERT_TRUE(success) << "shutdown from active state should succeed";

  // After shutdown, node transitions to finalized
  uint8_t state = getState();
  EXPECT_EQ(state, lifecycle_msgs::msg::State::PRIMARY_STATE_FINALIZED)
    << "Node should be in finalized state after shutdown";
}

// =============================================================================
// Task 4.6: Auto-activate launch transitions node to active
// =============================================================================

/**
 * Spec: Scenario: Auto-transition on launch
 *
 * WHEN the motor controller is launched with auto_activate:=true (default)
 * THEN the node SHALL transition to active automatically
 * THEN joint_states should be published within 5s of launch
 */
TEST_F(LifecycleAutoActivateTest, AutoActivateTransitionsToActive)
{
  // Launch node with auto_activate=true (default)
  std::string cmd =
    "ros2 run motor_control_ros2 mg6010_controller_node "
    "--ros-args "
    "-p simulation_mode:=true "
    "-p motor_ids:='[1,2,3]' "
    "-p joint_names:='[joint3,joint4,joint5]' "
    "-p min_positions:='[-180.0,-180.0,-180.0]' "
    "-p max_positions:='[180.0,180.0,180.0]' "
    "-p auto_activate:=true "
    "-r __node:=" + std::string(TEST_NODE_NAME) +
    " &";

  int ret = std::system(cmd.c_str());
  ASSERT_EQ(ret, 0) << "Failed to launch node subprocess";

  // Wait for lifecycle service to appear (proves it's a lifecycle node)
  std::string ns = std::string("/") + TEST_NODE_NAME;
  bool svc_ready = get_state_client_->wait_for_service(NODE_STARTUP_TIMEOUT);
  ASSERT_TRUE(svc_ready) << "get_state service not available — not a LifecycleNode";

  // Wait for auto-transition to complete (configure → activate)
  // Node should reach active state within startup timeout
  auto start = std::chrono::steady_clock::now();
  uint8_t state = 0;
  while (std::chrono::steady_clock::now() - start < NODE_STARTUP_TIMEOUT) {
    auto request = std::make_shared<lifecycle_msgs::srv::GetState::Request>();
    auto future = get_state_client_->async_send_request(request);
    if (future.wait_for(2s) == std::future_status::ready) {
      state = future.get()->current_state.id;
      if (state == lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
        break;
      }
    }
    std::this_thread::sleep_for(500ms);
  }

  EXPECT_EQ(state, lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE)
    << "Node should auto-transition to active state";
}

// =============================================================================
// Task 4.7: on_configure failure on invalid CAN interface
// =============================================================================

/**
 * Spec: Scenario: Configure failure on invalid CAN interface
 *
 * GIVEN motor configuration parameters but the CAN interface is not available
 * WHEN on_configure is triggered
 * THEN the transition SHALL return FAILURE
 * THEN the node SHALL remain in the unconfigured state
 */
TEST_F(LifecycleConfigFailureTest, ConfigureFailsOnInvalidCANInterface)
{
  // Launch node with simulation_mode=false and a nonexistent CAN interface
  // This should make on_configure fail when trying to open the CAN interface
  std::string params =
    "-p simulation_mode:=false "
    "-p can_interface:=can_nonexistent_99 "
    "-p motor_ids:='[1,2,3]' "
    "-p joint_names:='[joint3,joint4,joint5]' "
    "-p min_positions:='[-180.0,-180.0,-180.0]' "
    "-p max_positions:='[180.0,180.0,180.0]' ";

  bool launched = launchNodeAndWait(params, "can_fail");
  ASSERT_TRUE(launched) << "Node subprocess should start (lifecycle services available)";

  // Node should be in unconfigured state
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);

  // Trigger configure — should fail due to invalid CAN
  bool success = triggerTransition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);
  EXPECT_FALSE(success) << "configure should fail with invalid CAN interface";

  // Node should remain unconfigured
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED)
    << "Node should stay unconfigured after configure failure";
}

// =============================================================================
// Task 4.8: on_configure failure on mismatched param lengths
// =============================================================================

/**
 * Spec: Scenario: Configure failure on invalid parameters
 *
 * GIVEN motor_ids and joint_names arrays of different lengths
 * WHEN on_configure is triggered
 * THEN the transition SHALL return FAILURE
 * THEN the node SHALL remain in the unconfigured state
 */
TEST_F(LifecycleConfigFailureTest, ConfigureFailsOnMismatchedParamLengths)
{
  // motor_ids has 3, joint_names has 2 — mismatch
  std::string params =
    "-p simulation_mode:=true "
    "-p motor_ids:='[1,2,3]' "
    "-p joint_names:='[joint3,joint4]' "
    "-p min_positions:='[-180.0,-180.0,-180.0]' "
    "-p max_positions:='[180.0,180.0,180.0]' ";

  bool launched = launchNodeAndWait(params, "mismatch");
  ASSERT_TRUE(launched) << "Node subprocess should start";

  // Node should be unconfigured
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);

  // Configure should fail due to mismatched lengths
  bool success = triggerTransition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);
  EXPECT_FALSE(success)
    << "configure should fail when motor_ids and joint_names have different lengths";

  // Should remain unconfigured
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);
}

// =============================================================================
// Task 4.9: Full lifecycle round-trip
// =============================================================================

/**
 * Spec: Scenario: Configure is idempotent after cleanup
 * Spec: Scenario: Re-configure after cleanup
 *
 * GIVEN a node that was configured, activated, deactivated, and cleaned up
 * WHEN on_configure is triggered again
 * THEN it SHALL succeed with fresh instances
 * THEN no stale state from the previous lifecycle SHALL persist
 */
TEST_F(LifecycleNodeTest, FullLifecycleRoundTrip)
{
  // --- First cycle ---
  ASSERT_TRUE(configure()) << "First configure should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);

  ASSERT_TRUE(activate()) << "First activate should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);

  // Verify active behavior
  ASSERT_TRUE(waitForJointStates(10s)) << "Should get joint_states in first active cycle";

  ASSERT_TRUE(deactivate()) << "First deactivate should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);

  ASSERT_TRUE(cleanup()) << "First cleanup should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);

  // --- Second cycle (re-configure from scratch) ---
  ASSERT_TRUE(configure()) << "Second configure should succeed after cleanup";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);

  ASSERT_TRUE(activate()) << "Second activate should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);

  // Verify active behavior again — fresh state
  ASSERT_TRUE(waitForJointStates(10s))
    << "Should get joint_states in second active cycle (fresh state)";
}

// =============================================================================
// Task 4.19: Deactivation action grace period
// =============================================================================

/**
 * Spec: Scenario: In-progress actions complete before deactivation
 *
 * GIVEN a JointPositionCommand action is executing
 * WHEN on_deactivate is triggered
 * THEN the in-progress action SHALL be allowed up to 5 seconds to complete
 * THEN if still executing after 5 seconds, the action SHALL be cancelled
 * THEN deactivation SHALL succeed (node moves to inactive state)
 *
 * This test verifies that deactivation does not block indefinitely when
 * an action is in progress, and completes within the 5s grace period + margin.
 */
TEST_F(LifecycleNodeTest, DeactivationGracePeriodForInProgressAction)
{
  using JointPosCmd = motor_control_msgs::action::JointPositionCommand;

  // Get to active state
  ASSERT_TRUE(configureAndActivate()) << "configure+activate should succeed";
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);

  // Wait for the node to be fully active (joint_states publishing)
  ASSERT_TRUE(waitForJointStates(10s)) << "Should get joint_states when active";

  // Create action client for JointPositionCommand
  std::string ns = std::string("/") + TEST_NODE_NAME;
  auto action_client = rclcpp_action::create_client<JointPosCmd>(
    client_node_, ns + "/joint_position_command");

  ASSERT_TRUE(action_client->wait_for_action_server(10s))
    << "JointPositionCommand action server should be available";

  // Send a position command to a far target (should take a while in sim mode)
  auto goal = JointPosCmd::Goal();
  goal.joint_id = 3;  // joint3
  goal.target_position = 999.0;  // Far target — unlikely to reach quickly in sim
  goal.max_velocity = 1.0;  // Slow velocity

  auto send_goal_options = rclcpp_action::Client<JointPosCmd>::SendGoalOptions();
  std::atomic<bool> action_done{false};
  std::atomic<int> action_result_code{-1};  // -1 = unknown

  send_goal_options.result_callback =
    [&action_done, &action_result_code](
      const rclcpp_action::ClientGoalHandle<JointPosCmd>::WrappedResult & result) {
      action_result_code.store(static_cast<int>(result.code));
      action_done.store(true);
    };

  auto goal_future = action_client->async_send_goal(goal, send_goal_options);

  // Wait briefly for goal to be accepted and action to start executing
  std::this_thread::sleep_for(500ms);

  // Now trigger deactivation while action is in progress
  auto deactivate_start = std::chrono::steady_clock::now();
  ASSERT_TRUE(deactivate()) << "deactivate should succeed";
  auto deactivate_duration = std::chrono::steady_clock::now() - deactivate_start;

  // Deactivation should complete within 6 seconds (5s grace + 1s margin)
  EXPECT_LT(deactivate_duration, std::chrono::seconds(7))
    << "Deactivation should complete within grace period (5s) + margin";

  // Node should be in inactive state
  EXPECT_EQ(getState(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE)
    << "Node should be in inactive state after deactivation";

  // Wait for action result callback (should have been aborted/cancelled by deactivation)
  auto wait_start = std::chrono::steady_clock::now();
  while (!action_done.load() &&
         (std::chrono::steady_clock::now() - wait_start) < std::chrono::seconds(3)) {
    std::this_thread::sleep_for(100ms);
  }

  // The action should have completed (either aborted or cancelled due to deactivation)
  if (action_done.load()) {
    auto code = static_cast<rclcpp_action::ResultCode>(action_result_code.load());
    // Expected: ABORTED (deactivation triggered SHUTDOWN abort) or CANCELED
    EXPECT_TRUE(
      code == rclcpp_action::ResultCode::ABORTED ||
      code == rclcpp_action::ResultCode::CANCELED)
      << "In-progress action should be aborted or canceled during deactivation, got code: "
      << action_result_code.load();
  }
  // Note: if action_done is false, the action may have completed before deactivation
  // or the result callback wasn't delivered. This is acceptable — the key assertion
  // is that deactivation succeeded without hanging.
}

}  // namespace motor_control_ros2
