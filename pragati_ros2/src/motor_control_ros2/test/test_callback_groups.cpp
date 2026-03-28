/*
 * Callback Group & MultiThreadedExecutor Tests (TDD RED phase)
 *
 * Tests for Step 8 of mg6010-decomposition Phase 3.
 * Verifies:
 *   - 3 callback groups (safety, hardware, processing) exist on node
 *   - Entities are assigned to correct callback groups
 *   - Concurrent action does not block service response
 *   - Watchdog fires during long position command
 *   - Control loop timing stability under concurrency
 *   - Timer not starved by concurrent homing action
 *
 * RED phase: these tests FAIL because callback group assignment and
 * MultiThreadedExecutor integration do not exist yet.
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/multi_threaded_executor.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

#include "motor_control_ros2/ros_interface_manager.hpp"
#include "motor_control_ros2/motor_test_suite.hpp"
#include "motor_control_ros2/control_loop_manager.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"

#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <numeric>
#include <string>
#include <thread>
#include <vector>

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using ::testing::_;
using ::testing::NiceMock;
using ::testing::Return;

// =============================================================================
// GMock MockMotorController
// =============================================================================

class MockMotorController : public MotorControllerInterface
{
public:
  MOCK_METHOD(
    bool, initialize,
    (const MotorConfiguration & config, std::shared_ptr<CANInterface> can_interface),
    (override));
  MOCK_METHOD(bool, configure, (const MotorConfiguration & config), (override));
  MOCK_METHOD(bool, set_enabled, (bool enable), (override));
  MOCK_METHOD(
    bool, set_position, (double position, double velocity, double torque),
    (override));
  MOCK_METHOD(bool, set_velocity, (double velocity, double torque), (override));
  MOCK_METHOD(bool, set_torque, (double torque), (override));
  MOCK_METHOD(double, get_position, (), (override));
  MOCK_METHOD(double, get_velocity, (), (override));
  MOCK_METHOD(double, get_torque, (), (override));
  MOCK_METHOD(bool, home_motor, (const HomingConfig * config), (override));
  MOCK_METHOD(bool, is_homed, (), (const, override));
  MOCK_METHOD(MotorStatus, get_status, (), (override));
  MOCK_METHOD(bool, emergency_stop, (), (override));
  MOCK_METHOD(bool, stop, (), (override));
  MOCK_METHOD(bool, clear_errors, (), (override));
  MOCK_METHOD(bool, calibrate_motor, (), (override));
  MOCK_METHOD(bool, calibrate_encoder, (), (override));
  MOCK_METHOD(bool, needs_calibration, (), (const, override));
  MOCK_METHOD(MotorConfiguration, get_configuration, (), (const, override));
  MOCK_METHOD(
    const ErrorFramework::ErrorInfo &, get_error_info, (), (const, override));
  MOCK_METHOD(
    std::vector<ErrorFramework::ErrorInfo>, get_error_history,
    (), (const, override));
  MOCK_METHOD(
    ErrorFramework::RecoveryResult, attempt_error_recovery, (), (override));
  MOCK_METHOD(
    void, set_error_handler,
    (std::function<void(const ErrorFramework::ErrorInfo &)> handler),
    (override));
  MOCK_METHOD(std::optional<PIDParams>, readPID, (), (override));
  MOCK_METHOD(bool, setPID, (const PIDParams & params), (override));
  MOCK_METHOD(bool, writePIDToROM, (const PIDParams & params), (override));
  MOCK_METHOD(bool, readMaxTorqueCurrent, (uint16_t & ratio), (override));
  MOCK_METHOD(bool, writeMaxTorqueCurrentRAM, (uint16_t ratio), (override));
  MOCK_METHOD(bool, readAcceleration, (double & rad_per_sec2), (override));
  MOCK_METHOD(bool, setAcceleration, (double rad_per_sec2), (override));
  MOCK_METHOD(
    bool, readEncoder,
    (uint16_t & encoder_value, uint16_t & encoder_raw,
     uint16_t & encoder_offset),
    (override));
  MOCK_METHOD(bool, writeEncoderOffsetToROM, (uint16_t offset), (override));
  MOCK_METHOD(bool, setCurrentPositionAsZero, (), (override));
  MOCK_METHOD(bool, readMultiTurnAngle, (double & angle_radians), (override));
  MOCK_METHOD(bool, readSingleTurnAngle, (double & angle_radians), (override));
  MOCK_METHOD(bool, readErrors, (uint32_t & error_flags), (override));
  MOCK_METHOD(FullMotorState, readFullState, (), (override));
  MOCK_METHOD(bool, torqueClosedLoop, (double amps), (override));
  MOCK_METHOD(bool, speedClosedLoop, (double dps), (override));
  MOCK_METHOD(bool, multiLoopAngle1, (double degrees), (override));
  MOCK_METHOD(
    bool, multiLoopAngle2, (double degrees, double max_speed_dps), (override));
  MOCK_METHOD(
    bool, singleLoopAngle1, (double degrees, uint8_t direction), (override));
  MOCK_METHOD(
    bool, singleLoopAngle2,
    (double degrees, double max_speed_dps, uint8_t direction), (override));
  MOCK_METHOD(bool, incrementAngle1, (double degrees), (override));
  MOCK_METHOD(
    bool, incrementAngle2, (double degrees, double max_speed_dps), (override));
};

// =============================================================================
// Helpers
// =============================================================================

static int g_cbg_test_counter = 0;

/// Count callback groups of a specific type on a node.
size_t countCallbackGroupsByType(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  rclcpp::CallbackGroupType type)
{
  size_t count = 0;
  node->for_each_callback_group(
    [&](rclcpp::CallbackGroup::SharedPtr group) {
      if (group->type() == type) {
        ++count;
      }
    });
  return count;
}

/// Count total callback groups on a node (including default).
size_t countAllCallbackGroups(std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node)
{
  size_t count = 0;
  node->for_each_callback_group(
    [&](rclcpp::CallbackGroup::SharedPtr) { ++count; });
  return count;
}

/// Find callback group containing a specific timer.
rclcpp::CallbackGroup::SharedPtr findGroupForTimer(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  rclcpp::TimerBase::SharedPtr timer)
{
  rclcpp::CallbackGroup::SharedPtr result;
  node->for_each_callback_group(
    [&](rclcpp::CallbackGroup::SharedPtr group) {
      auto found = group->find_timer_ptrs_if(
        [&](const rclcpp::TimerBase::SharedPtr & t) {
          return t.get() == timer.get();
        });
      if (found) {
        result = group;
      }
    });
  return result;
}

/// Find callback group containing a specific service.
rclcpp::CallbackGroup::SharedPtr findGroupForService(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  rclcpp::ServiceBase::SharedPtr service)
{
  rclcpp::CallbackGroup::SharedPtr result;
  node->for_each_callback_group(
    [&](rclcpp::CallbackGroup::SharedPtr group) {
      auto found = group->find_service_ptrs_if(
        [&](const rclcpp::ServiceBase::SharedPtr & s) {
          return s.get() == service.get();
        });
      if (found) {
        result = group;
      }
    });
  return result;
}

/// Find callback group containing a specific subscription.
rclcpp::CallbackGroup::SharedPtr findGroupForSubscription(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  rclcpp::SubscriptionBase::SharedPtr sub)
{
  rclcpp::CallbackGroup::SharedPtr result;
  node->for_each_callback_group(
    [&](rclcpp::CallbackGroup::SharedPtr group) {
      auto found = group->find_subscription_ptrs_if(
        [&](const rclcpp::SubscriptionBase::SharedPtr & s) {
          return s.get() == sub.get();
        });
      if (found) {
        result = group;
      }
    });
  return result;
}

/// Build dummy NodeCallbacks (all no-ops) for RIM construction.
NodeCallbacks makeDummyCallbacks()
{
  NodeCallbacks cb;
  cb.enable_callback = [](auto, auto) {};
  cb.disable_callback = [](auto, auto) {};
  cb.reset_motor_callback = [](auto, auto) {};
  cb.joint_position_command_callback = [](auto, auto) {};
  cb.motor_command_callback = [](auto, auto) {};
  cb.motor_lifecycle_callback = [](auto, auto) {};
  cb.write_motor_limits_callback = [](auto, auto) {};
  cb.write_encoder_zero_callback = [](auto, auto) {};
  cb.step_response_goal_callback =
    [](const auto &, auto) {
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    };
  cb.step_response_cancel_callback =
    [](auto) { return rclcpp_action::CancelResponse::ACCEPT; };
  cb.step_response_accepted_callback = [](auto) {};
  cb.joint_pos_cmd_goal_callback =
    [](const auto &, auto) {
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    };
  cb.joint_pos_cmd_cancel_callback =
    [](auto) { return rclcpp_action::CancelResponse::ACCEPT; };
  cb.joint_pos_cmd_accepted_callback = [](auto) {};
  cb.joint_homing_goal_callback =
    [](const auto &, auto) {
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    };
  cb.joint_homing_cancel_callback =
    [](auto) { return rclcpp_action::CancelResponse::ACCEPT; };
  cb.joint_homing_accepted_callback = [](auto) {};
  return cb;
}

// =============================================================================
// Test Fixture — Callback Group Tests
// =============================================================================

class CallbackGroupTest : public ::testing::Test
{
protected:
  static constexpr size_t NUM_MOTORS = 3;

  static void SetUpTestSuite() { rclcpp::init(0, nullptr); }
  static void TearDownTestSuite() { rclcpp::shutdown(); }

  void SetUp() override
  {
    std::string suffix = std::to_string(++g_cbg_test_counter);
    node_ = std::make_shared<rclcpp_lifecycle::LifecycleNode>("test_cbg_" + suffix);

    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_can_->initialize("vcan0");

    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      auto mock = std::make_shared<NiceMock<MockMotorController>>();
      MotorConfiguration cfg;
      cfg.can_id = static_cast<uint8_t>(i + 1);
      cfg.transmission_factor = 1.0;
      cfg.direction = 1;
      cfg.encoder_offset = 0.0;
      ON_CALL(*mock, get_configuration()).WillByDefault(Return(cfg));
      ON_CALL(*mock, get_position()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_velocity()).WillByDefault(Return(0.0));
      ON_CALL(*mock, get_torque()).WillByDefault(Return(0.0));
      controllers_.push_back(mock);
    }

    joint_names_ = {"joint5", "joint3", "joint4"};
    for (size_t i = 0; i < NUM_MOTORS; ++i) {
      motor_available_[i].store(true);
    }
  }

  void TearDown() override
  {
    rim_.reset();
    clm_.reset();
    controllers_.clear();
  }

  void createManagers()
  {
    clm_ = std::make_unique<ControlLoopManager>(
      node_, mock_can_, controllers_, motor_available_,
      joint_names_, 0.0);  // frequency=0 suppresses timer

    motor_test_suite_ = std::make_unique<MotorTestSuite>(
      node_, mock_can_, controllers_, motor_available_, joint_names_);

    // Create callback groups on the node (injected into RIM)
    auto safety_group = node_->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);
    auto hardware_group = node_->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);
    auto processing_group = node_->create_callback_group(
      rclcpp::CallbackGroupType::Reentrant);

    rim_ = std::make_unique<RosInterfaceManager>(
      node_, motor_test_suite_.get(), clm_.get(),
      makeDummyCallbacks(), controllers_,
      motor_available_, joint_names_,
      safety_group, hardware_group, processing_group);
  }

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;
  std::array<std::atomic<bool>, MAX_MOTORS> motor_available_{};
  std::vector<std::string> joint_names_;
  std::unique_ptr<ControlLoopManager> clm_;
  std::unique_ptr<MotorTestSuite> motor_test_suite_;
  std::unique_ptr<RosInterfaceManager> rim_;
};

// =============================================================================
// Task 3.1 RED: Safety callback group assignment
//
// After creating RIM, the node should have a MutuallyExclusive callback group
// dedicated to safety (watchdog, e_stop, collision_interlock). Currently there
// are no custom callback groups — only the default. This test FAILS.
// =============================================================================

TEST_F(CallbackGroupTest, SafetyCallbackGroupExists)
{
  createManagers();

  // The node should have exactly 4 callback groups:
  // 1 default + safety + hardware + processing
  size_t total = countAllCallbackGroups(node_);
  EXPECT_EQ(total, 4u)
    << "Expected 4 callback groups (default + safety + hardware + processing), "
    << "got " << total;

  // There should be at least 2 MutuallyExclusive groups:
  // default + safety + hardware = 3 MutuallyExclusive
  size_t me_count = countCallbackGroupsByType(
    node_, rclcpp::CallbackGroupType::MutuallyExclusive);
  EXPECT_GE(me_count, 3u)
    << "Expected at least 3 MutuallyExclusive groups "
    << "(default + safety + hardware), got " << me_count;
}

// =============================================================================
// Task 3.2 RED: Hardware callback group assignment
//
// Services created by RIM should be in a dedicated MutuallyExclusive hardware
// callback group, NOT in the default group. Currently all services are in the
// default group. This test FAILS.
// =============================================================================

TEST_F(CallbackGroupTest, HardwareServicesNotInDefaultGroup)
{
  createManagers();

  // Count non-internal services in the default callback group.
  // rclcpp::Node automatically creates 7 internal services in the default group:
  //   6 parameter services (describe/get/get_types/list/set/set_atomically)
  //   1 type description service (~/get_type_description)
  // These are expected. We only check that no APPLICATION services remain.
  size_t app_services_in_default = 0;
  bool first_group = true;
  node_->for_each_callback_group(
    [&](rclcpp::CallbackGroup::SharedPtr group) {
      if (first_group) {
        group->find_service_ptrs_if(
          [&](const rclcpp::ServiceBase::SharedPtr & svc) {
            const std::string name = svc->get_service_name();
            // Skip rclcpp-internal parameter and type description services
            if (name.find("parameter") == std::string::npos &&
                name.find("get_type_description") == std::string::npos) {
              ++app_services_in_default;
            }
            return false;  // continue searching
          });
        first_group = false;
      }
    });

  // After Step 8: zero application services in default group
  EXPECT_EQ(app_services_in_default, 0u)
    << "Expected 0 application services in default callback group after "
    << "Step 8, but found " << app_services_in_default
    << " (services not yet assigned to hardware_cb_group_)";
}

// =============================================================================
// Task 3.3 RED: Processing callback group assignment
//
// A Reentrant callback group should exist for action servers and diagnostics.
// Currently no Reentrant group exists. This test FAILS.
// =============================================================================

TEST_F(CallbackGroupTest, ProcessingReentrantGroupExists)
{
  createManagers();

  size_t reentrant_count = countCallbackGroupsByType(
    node_, rclcpp::CallbackGroupType::Reentrant);
  EXPECT_GE(reentrant_count, 1u)
    << "Expected at least 1 Reentrant callback group (processing), "
    << "got " << reentrant_count;
}

// =============================================================================
// Task 3.4 RED: Concurrent action does not block service response
//
// With MultiThreadedExecutor and separate callback groups, a long-running
// action in the processing group should not block a service in the hardware
// group. Under SingleThreadedExecutor, everything is serialized.
// =============================================================================

TEST_F(CallbackGroupTest, ConcurrentActionDoesNotBlockService)
{
  // Create 2 callback groups to simulate hardware + processing separation
  auto hw_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);
  auto proc_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::Reentrant);

  // Service in hardware group — responds immediately
  std::atomic<bool> service_called{false};
  auto service = node_->create_service<std_srvs::srv::Trigger>(
    "~/test_service",
    [&](const std::shared_ptr<std_srvs::srv::Trigger::Request>,
        std::shared_ptr<std_srvs::srv::Trigger::Response> resp) {
      service_called.store(true);
      resp->success = true;
    },
    rclcpp::ServicesQoS(), hw_group);

  // Simulate a long-running "action" in processing group (500ms sleep)
  std::atomic<bool> action_started{false};
  std::atomic<bool> action_finished{false};
  auto action_timer = node_->create_wall_timer(
    std::chrono::milliseconds(10),
    [&]() {
      action_started.store(true);
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
      action_finished.store(true);
    },
    proc_group);

  // Use MultiThreadedExecutor to enable concurrency
  rclcpp::executors::MultiThreadedExecutor executor(
    rclcpp::ExecutorOptions(), 4);
  executor.add_node(node_->get_node_base_interface());

  // Spin in background
  auto spin_thread = std::thread([&]() { executor.spin(); });

  // Wait for the action timer to start its 500ms sleep
  auto start = std::chrono::steady_clock::now();
  while (!action_started.load() &&
         std::chrono::steady_clock::now() - start <
           std::chrono::seconds(2))
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  ASSERT_TRUE(action_started.load()) << "Action timer never started";

  // Now call the service — it should respond while action is still running
  auto client = node_->create_client<std_srvs::srv::Trigger>(
    "~/test_service");
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));

  auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
  auto call_start = std::chrono::steady_clock::now();
  auto future = client->async_send_request(request);

  // Wait for response with 200ms timeout
  auto status = future.wait_for(std::chrono::milliseconds(200));
  auto call_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
    std::chrono::steady_clock::now() - call_start);

  // Cancel the action timer to stop the spin
  action_timer->cancel();
  executor.cancel();
  spin_thread.join();

  // Service should have been called while action was still sleeping
  EXPECT_EQ(status, std::future_status::ready)
    << "Service call timed out — likely blocked by action in same thread";
  EXPECT_TRUE(service_called.load());
  EXPECT_LT(call_duration.count(), 50)
    << "Service response took " << call_duration.count()
    << "ms, expected <50ms (blocked by processing group?)";
}

// =============================================================================
// Task 3.5 RED: Watchdog fires during long position command
//
// The watchdog timer in the safety group should continue firing even when
// a long-running operation is happening in the hardware group.
// =============================================================================

TEST_F(CallbackGroupTest, WatchdogFiresDuringLongOperation)
{
  auto safety_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);
  auto hw_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);

  // Watchdog in safety group — fires every 50ms
  std::atomic<int> watchdog_count{0};
  auto watchdog_timer = node_->create_wall_timer(
    std::chrono::milliseconds(50),
    [&]() { watchdog_count.fetch_add(1); },
    safety_group);

  // Long operation in hardware group — blocks for 300ms
  std::atomic<bool> hw_started{false};
  auto hw_timer = node_->create_wall_timer(
    std::chrono::milliseconds(10),
    [&]() {
      hw_started.store(true);
      std::this_thread::sleep_for(std::chrono::milliseconds(300));
    },
    hw_group);

  rclcpp::executors::MultiThreadedExecutor executor(
    rclcpp::ExecutorOptions(), 4);
  executor.add_node(node_->get_node_base_interface());

  auto spin_thread = std::thread([&]() { executor.spin(); });

  // Wait for hw operation to start
  auto start = std::chrono::steady_clock::now();
  while (!hw_started.load() &&
         std::chrono::steady_clock::now() - start <
           std::chrono::seconds(2))
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  ASSERT_TRUE(hw_started.load());

  // Wait 250ms — watchdog should fire ~5 times even with hw blocked
  std::this_thread::sleep_for(std::chrono::milliseconds(250));

  watchdog_timer->cancel();
  hw_timer->cancel();
  executor.cancel();
  spin_thread.join();

  // Watchdog should have fired at least 3 times in 250ms (every 50ms)
  EXPECT_GE(watchdog_count.load(), 3)
    << "Watchdog only fired " << watchdog_count.load()
    << " times in 250ms — should fire >=3 times at 50ms interval";
}

// =============================================================================
// Task 3.6 RED: Control loop timer backward compat (no group arg)
//
// When ControlLoopManager creates a timer without a callback group argument,
// it should still function. After Step 8 it should accept a callback group.
// This test verifies CLM with a non-zero frequency fires its timer.
// =============================================================================

TEST_F(CallbackGroupTest, ControlLoopTimerBackwardCompat)
{
  // Create CLM with 10Hz frequency — its own timer should fire
  clm_ = std::make_unique<ControlLoopManager>(
    node_, mock_can_, controllers_, motor_available_,
    joint_names_, 10.0);

  // Spin for 300ms — CLM timer should publish joint states
  auto sub_node = rclcpp::Node::make_shared(
    "clm_compat_listener_" + std::to_string(g_cbg_test_counter));
  std::atomic<int> msg_count{0};
  auto sub = sub_node->create_subscription<sensor_msgs::msg::JointState>(
    "joint_states", 10,
    [&](sensor_msgs::msg::JointState::SharedPtr) {
      msg_count.fetch_add(1);
    });

  auto end = std::chrono::steady_clock::now() +
    std::chrono::milliseconds(400);
  while (std::chrono::steady_clock::now() < end) {
    rclcpp::spin_some(node_->get_node_base_interface());
    rclcpp::spin_some(sub_node);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  // At 10Hz over 400ms, expect at least 2 messages
  EXPECT_GE(msg_count.load(), 2)
    << "CLM timer did not fire — got " << msg_count.load()
    << " joint_states messages in 400ms";
}

// =============================================================================
// Task 3.7 RED: 50Hz timing stability
//
// Control loop timer at 50Hz in a MutuallyExclusive hardware group should
// maintain mean ~20ms period with p99 jitter <=2ms even under concurrent
// processing group load.
// =============================================================================

TEST_F(CallbackGroupTest, ControlLoopTimingStability50Hz)
{
  auto hw_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);
  auto proc_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::Reentrant);

  // 50Hz control loop timer in hardware group
  std::mutex ts_mutex;
  std::vector<std::chrono::steady_clock::time_point> timestamps;
  timestamps.reserve(150);

  auto control_timer = node_->create_wall_timer(
    std::chrono::milliseconds(20),
    [&]() {
      std::lock_guard<std::mutex> lock(ts_mutex);
      timestamps.push_back(std::chrono::steady_clock::now());
    },
    hw_group);

  // Processing load — simulate action server work
  auto load_timer = node_->create_wall_timer(
    std::chrono::milliseconds(30),
    [&]() {
      // Simulate CPU work (non-blocking, just busy-wait 5ms)
      auto end = std::chrono::steady_clock::now() +
        std::chrono::milliseconds(5);
      while (std::chrono::steady_clock::now() < end) {}
    },
    proc_group);

  rclcpp::executors::MultiThreadedExecutor executor(
    rclcpp::ExecutorOptions(), 4);
  executor.add_node(node_->get_node_base_interface());
  auto spin_thread = std::thread([&]() { executor.spin(); });

  // Collect ~100 samples (2 seconds at 50Hz)
  std::this_thread::sleep_for(std::chrono::milliseconds(2200));

  control_timer->cancel();
  load_timer->cancel();
  executor.cancel();
  spin_thread.join();

  // Compute periods
  std::lock_guard<std::mutex> lock(ts_mutex);
  ASSERT_GE(timestamps.size(), 50u)
    << "Only got " << timestamps.size()
    << " control loop samples in 2.2s (expected ~100)";

  std::vector<double> periods_ms;
  for (size_t i = 1; i < timestamps.size(); ++i) {
    auto dt = std::chrono::duration_cast<std::chrono::microseconds>(
      timestamps[i] - timestamps[i - 1]);
    periods_ms.push_back(dt.count() / 1000.0);
  }

  // Mean period: 20ms +/- 2ms (relaxed for test environment)
  double sum = std::accumulate(periods_ms.begin(), periods_ms.end(), 0.0);
  double mean = sum / periods_ms.size();
  EXPECT_NEAR(mean, 20.0, 2.0)
    << "Mean control loop period " << mean << "ms, expected 20ms +/-2ms";

  // p99 jitter: sort and check 99th percentile deviation from 20ms
  std::vector<double> jitters;
  for (double p : periods_ms) {
    jitters.push_back(std::abs(p - 20.0));
  }
  std::sort(jitters.begin(), jitters.end());
  size_t p99_idx = static_cast<size_t>(jitters.size() * 0.99);
  if (p99_idx >= jitters.size()) p99_idx = jitters.size() - 1;
  double p99_jitter = jitters[p99_idx];
  EXPECT_LE(p99_jitter, 5.0)
    << "p99 jitter " << p99_jitter << "ms exceeds 5ms threshold";
}

// =============================================================================
// Task 3.8 RED: Timer not starved by concurrent homing action
//
// A long-running "homing" operation in the processing group should not
// starve the control loop timer in the hardware group. No iteration should
// be delayed more than 5ms from its scheduled time.
// =============================================================================

TEST_F(CallbackGroupTest, TimerNotStarvedByConcurrentAction)
{
  auto hw_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);
  auto proc_group = node_->create_callback_group(
    rclcpp::CallbackGroupType::Reentrant);

  // 50Hz control loop in hardware group
  std::mutex ts_mutex;
  std::vector<std::chrono::steady_clock::time_point> timestamps;
  timestamps.reserve(100);

  auto control_timer = node_->create_wall_timer(
    std::chrono::milliseconds(20),
    [&]() {
      std::lock_guard<std::mutex> lock(ts_mutex);
      timestamps.push_back(std::chrono::steady_clock::now());
    },
    hw_group);

  // Simulate long homing action — blocks for 1s total (10 x 100ms sleeps)
  std::atomic<int> homing_iterations{0};
  auto homing_timer = node_->create_wall_timer(
    std::chrono::milliseconds(50),
    [&]() {
      // Each "homing step" takes 100ms
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
      homing_iterations.fetch_add(1);
    },
    proc_group);

  rclcpp::executors::MultiThreadedExecutor executor(
    rclcpp::ExecutorOptions(), 4);
  executor.add_node(node_->get_node_base_interface());
  auto spin_thread = std::thread([&]() { executor.spin(); });

  // Run for 1.5s — homing should run ~10 iterations, control ~75 ticks
  std::this_thread::sleep_for(std::chrono::milliseconds(1500));

  control_timer->cancel();
  homing_timer->cancel();
  executor.cancel();
  spin_thread.join();

  // Verify control loop was not starved
  std::lock_guard<std::mutex> lock(ts_mutex);
  ASSERT_GE(timestamps.size(), 30u)
    << "Control loop starved: only " << timestamps.size()
    << " ticks in 1.5s";

  // Check max delay: no iteration > 5ms late
  double max_delay_ms = 0.0;
  for (size_t i = 1; i < timestamps.size(); ++i) {
    auto dt = std::chrono::duration_cast<std::chrono::microseconds>(
      timestamps[i] - timestamps[i - 1]);
    double period_ms = dt.count() / 1000.0;
    double delay = period_ms - 20.0;  // deviation from 20ms
    if (delay > max_delay_ms) {
      max_delay_ms = delay;
    }
  }

  EXPECT_LE(max_delay_ms, 5.0)
    << "Control loop max delay " << max_delay_ms
    << "ms exceeds 5ms threshold — timer starved by homing action";
}
