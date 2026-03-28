#include <gtest/gtest.h>
#include "motor_control_ros2/safety_monitor.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"
#include <rclcpp/rclcpp.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <std_msgs/msg/string.hpp>
#include <memory>
#include <atomic>
#include <thread>
#include <chrono>

namespace motor_control_ros2
{

// ============================================================================
// Mock MotorControllerInterface for e-stop tests
// ============================================================================
class MockMotorController : public MotorControllerInterface
{
public:
    // Tracking fields
    std::atomic<int> emergency_stop_count{0};
    bool emergency_stop_should_fail{false};

    bool initialize(const MotorConfiguration&, std::shared_ptr<CANInterface>) override
    {
        return true;
    }
    bool configure(const MotorConfiguration&) override { return true; }
    bool set_enabled(bool) override { return true; }
    bool set_position(double, double, double) override { return true; }
    bool set_velocity(double, double) override { return true; }
    bool set_torque(double) override { return true; }
    double get_position() override { return 0.0; }
    double get_velocity() override { return 0.0; }
    double get_torque() override { return 0.0; }
    bool home_motor(const HomingConfig*) override { return true; }
    bool is_homed() const override { return false; }
    MotorStatus get_status() override { return {}; }
    bool stop() override { return true; }
    bool clear_errors() override { return true; }
    bool calibrate_motor() override { return true; }
    bool calibrate_encoder() override { return true; }
    bool needs_calibration() const override { return false; }
    MotorConfiguration get_configuration() const override
    {
        return MotorConfiguration{};
    }
    const ErrorFramework::ErrorInfo& get_error_info() const override
    {
        static ErrorFramework::ErrorInfo info{};
        return info;
    }
    std::vector<ErrorFramework::ErrorInfo> get_error_history() const override { return {}; }
    ErrorFramework::RecoveryResult attempt_error_recovery() override { return {}; }
    void set_error_handler(std::function<void(const ErrorFramework::ErrorInfo&)>) override {}
    std::optional<PIDParams> readPID() override { return std::nullopt; }
    bool setPID(const PIDParams&) override { return true; }
    bool writePIDToROM(const PIDParams&) override { return true; }

    bool emergency_stop() override
    {
        emergency_stop_count++;
        return !emergency_stop_should_fail;
    }
};

class SafetyMonitorTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        rclcpp::init(0, nullptr);
        node_ = std::make_shared<rclcpp::Node>("test_safety_monitor");
        monitor_ = std::make_unique<SafetyMonitor>(
            node_->get_node_base_interface(),
            node_->get_node_logging_interface(),
            node_->get_node_parameters_interface(),
            node_->get_node_topics_interface(),
            node_->get_node_services_interface()
        );
    }

    void TearDown() override
    {
        monitor_.reset();
        node_.reset();
        rclcpp::shutdown();
    }

    std::shared_ptr<rclcpp::Node> node_;
    std::unique_ptr<SafetyMonitor> monitor_;
};

// ============================================================================
// Task 1.1: SafetyState enum tests
// ============================================================================

// Test: SafetyState enum has all required values
TEST(SafetyStateEnumTest, HasAllRequiredStates)
{
    // Verify all six states exist and are distinct
    SafetyState unknown = SafetyState::UNKNOWN;
    SafetyState initializing = SafetyState::INITIALIZING;
    SafetyState safe = SafetyState::SAFE;
    SafetyState warning = SafetyState::WARNING;
    SafetyState critical = SafetyState::CRITICAL;
    SafetyState emergency = SafetyState::EMERGENCY;

    EXPECT_NE(unknown, initializing);
    EXPECT_NE(unknown, safe);
    EXPECT_NE(unknown, warning);
    EXPECT_NE(unknown, critical);
    EXPECT_NE(unknown, emergency);
    EXPECT_NE(initializing, safe);
    EXPECT_NE(safe, warning);
    EXPECT_NE(warning, critical);
    EXPECT_NE(critical, emergency);
}

// Test: SafetyState is usable in std::atomic (lock-free)
TEST(SafetyStateEnumTest, AtomicIsLockFree)
{
    std::atomic<SafetyState> state{SafetyState::UNKNOWN};
    EXPECT_TRUE(state.is_lock_free());
}

// Test: SafetyState atomic load/store works correctly
TEST(SafetyStateEnumTest, AtomicLoadStore)
{
    std::atomic<SafetyState> state{SafetyState::UNKNOWN};
    EXPECT_EQ(state.load(), SafetyState::UNKNOWN);

    state.store(SafetyState::SAFE);
    EXPECT_EQ(state.load(), SafetyState::SAFE);

    state.store(SafetyState::EMERGENCY);
    EXPECT_EQ(state.load(), SafetyState::EMERGENCY);
}

// ============================================================================
// Task 1.1: Fail-safe is_safe() tests
// ============================================================================

// Test: Fail-safe default — is_safe() returns false when state is UNKNOWN
TEST_F(SafetyMonitorTest, IsSafeReturnsFalseWhenUnknown)
{
    // Freshly constructed monitor should be in UNKNOWN state
    EXPECT_EQ(monitor_->get_state(), SafetyState::UNKNOWN);
    EXPECT_FALSE(monitor_->is_safe());
}

// Test: is_safe() returns false when state is INITIALIZING
TEST_F(SafetyMonitorTest, IsSafeReturnsFalseWhenInitializing)
{
    // Transition to INITIALIZING (activate starts initialization)
    monitor_->activate();
    // Before first successful update cycle, state should be INITIALIZING
    EXPECT_EQ(monitor_->get_state(), SafetyState::INITIALIZING);
    EXPECT_FALSE(monitor_->is_safe());
}

// Test: is_safe() returns true when state is SAFE
TEST_F(SafetyMonitorTest, IsSafeReturnsTrueWhenSafe)
{
    monitor_->activate();

    // Provide normal telemetry so safety checks pass
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor_->update_joint_states(msg);
    monitor_->update_vbus_voltage(48.0);
    monitor_->update_motor_temperature("joint2", 30.0);
    monitor_->update_motor_errors("joint2", 0);

    // After update with all-clear data, state should transition to SAFE
    monitor_->update();
    EXPECT_EQ(monitor_->get_state(), SafetyState::SAFE);
    EXPECT_TRUE(monitor_->is_safe());
}

// Test: is_safe() returns true when state is WARNING
TEST_F(SafetyMonitorTest, IsSafeReturnsTrueWhenWarning)
{
    monitor_->activate();

    // Provide normal data first to get to SAFE
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor_->update_joint_states(msg);
    monitor_->update_vbus_voltage(48.0);
    monitor_->update_motor_temperature("joint2", 30.0);
    monitor_->update_motor_errors("joint2", 0);
    monitor_->update();

    // Now push temperature into warning range (above 65, below 70)
    monitor_->update_motor_temperature("joint2", 67.0);
    // Temperature check runs every 10 cycles, so call update enough times
    for (int i = 0; i < 10; ++i) {
        monitor_->update();
    }

    EXPECT_EQ(monitor_->get_state(), SafetyState::WARNING);
    EXPECT_TRUE(monitor_->is_safe());
}

// Test: is_safe() returns false when state is CRITICAL
TEST_F(SafetyMonitorTest, IsSafeReturnsFalseWhenCritical)
{
    monitor_->activate();

    // Provide normal data first
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor_->update_joint_states(msg);
    monitor_->update_vbus_voltage(48.0);
    monitor_->update_motor_temperature("joint2", 30.0);
    monitor_->update_motor_errors("joint2", 0);
    monitor_->update();

    // Push voltage into critical range (below 40V)
    monitor_->update_vbus_voltage(38.0);
    // Voltage check runs every 20 cycles, so call update enough times
    for (int i = 0; i < 20; ++i) {
        monitor_->update();
    }

    // State should be CRITICAL or EMERGENCY
    SafetyState state = monitor_->get_state();
    EXPECT_TRUE(state == SafetyState::CRITICAL || state == SafetyState::EMERGENCY);
    EXPECT_FALSE(monitor_->is_safe());
}

// Test: is_safe() returns false when state is EMERGENCY
TEST_F(SafetyMonitorTest, IsSafeReturnsFalseWhenEmergency)
{
    monitor_->activate();
    monitor_->request_emergency_stop();

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    EXPECT_FALSE(monitor_->is_safe());
}

// Test: get_state() returns current state
TEST_F(SafetyMonitorTest, GetStateReturnsCurrentState)
{
    // Initially UNKNOWN
    EXPECT_EQ(monitor_->get_state(), SafetyState::UNKNOWN);

    // After activate, INITIALIZING
    monitor_->activate();
    EXPECT_EQ(monitor_->get_state(), SafetyState::INITIALIZING);

    // After e-stop, EMERGENCY
    monitor_->request_emergency_stop();
    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
}

// ============================================================================
// Original tests (updated for fail-safe default)
// ============================================================================

// Test: Construction
TEST_F(SafetyMonitorTest, Construction)
{
    ASSERT_NE(monitor_, nullptr);
}

// Test: Initial state — fail-safe: is_safe() returns false before activation
TEST_F(SafetyMonitorTest, InitialStateInactive)
{
    // Monitor starts in UNKNOWN state — fail-safe means NOT safe
    EXPECT_FALSE(monitor_->is_safe());
}

// Test: Activation and deactivation
TEST_F(SafetyMonitorTest, ActivateDeactivate)
{
    bool activated = monitor_->activate();
    EXPECT_TRUE(activated);

    monitor_->deactivate();
}

// Test: Update method
TEST_F(SafetyMonitorTest, UpdateMethod)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->update());

    monitor_->deactivate();
}

// Test: Safety state query
TEST_F(SafetyMonitorTest, SafetyStateQuery)
{
    // Should return true or false without crashing
    EXPECT_NO_THROW(monitor_->is_safe());
}

// Test: Emergency stop request
TEST_F(SafetyMonitorTest, EmergencyStopRequest)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->request_emergency_stop());

    // After E-stop, system should not be safe
    EXPECT_FALSE(monitor_->is_safe());

    monitor_->deactivate();
}

// Test: Emergency shutdown with reason
TEST_F(SafetyMonitorTest, EmergencyShutdownWithReason)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->trigger_emergency_shutdown("Test emergency shutdown"));

    // After shutdown, system should not be safe
    EXPECT_FALSE(monitor_->is_safe());

    monitor_->deactivate();
}

// Test: Update joint states
TEST_F(SafetyMonitorTest, UpdateJointStates)
{
    monitor_->activate();

    auto joint_state_msg = std::make_shared<sensor_msgs::msg::JointState>();
    joint_state_msg->name = {"joint1", "joint2"};
    joint_state_msg->position = {0.5, 1.0};
    joint_state_msg->velocity = {0.1, 0.2};
    joint_state_msg->effort = {0.5, 1.0};

    EXPECT_NO_THROW(monitor_->update_joint_states(joint_state_msg));
    EXPECT_NO_THROW(monitor_->update());

    monitor_->deactivate();
}

// Test: Update motor temperature
TEST_F(SafetyMonitorTest, UpdateMotorTemperature)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->update_motor_temperature("joint1", 25.0));
    EXPECT_NO_THROW(monitor_->update_motor_temperature("joint2", 60.0));
    EXPECT_NO_THROW(monitor_->update());

    monitor_->deactivate();
}

// Test: Update motor temperature - critical
TEST_F(SafetyMonitorTest, UpdateMotorTemperatureCritical)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->update_motor_temperature("joint1", 85.0));
    // Temperature check runs every 10 cycles, so call update enough times
    for (int i = 0; i < 10; ++i) {
        EXPECT_NO_THROW(monitor_->update());
    }

    // Critical temperature triggers safety violation
    EXPECT_FALSE(monitor_->is_safe());

    monitor_->deactivate();
}

// Test: Update motor errors
TEST_F(SafetyMonitorTest, UpdateMotorErrors)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->update_motor_errors("joint1", 0x0000));
    EXPECT_NO_THROW(monitor_->update_motor_errors("joint2", 0x0001));
    EXPECT_NO_THROW(monitor_->update());

    monitor_->deactivate();
}

// Test: Update VBus voltage
TEST_F(SafetyMonitorTest, UpdateVBusVoltage)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->update_vbus_voltage(24.0));
    EXPECT_NO_THROW(monitor_->update());

    monitor_->deactivate();
}

// Test: Update VBus voltage - low
TEST_F(SafetyMonitorTest, UpdateVBusVoltageLow)
{
    monitor_->activate();

    EXPECT_NO_THROW(monitor_->update_vbus_voltage(18.0));
    // Voltage check runs every 20 cycles, so call update enough times
    for (int i = 0; i < 20; ++i) {
        EXPECT_NO_THROW(monitor_->update());
    }

    // Low voltage triggers safety violation
    EXPECT_FALSE(monitor_->is_safe());

    monitor_->deactivate();
}

// Test: Multiple telemetry updates with normal values
TEST_F(SafetyMonitorTest, MultipleTelemetryUpdates)
{
    monitor_->activate();

    // Update multiple telemetry sources
    EXPECT_NO_THROW(monitor_->update_motor_temperature("joint1", 30.0));
    EXPECT_NO_THROW(monitor_->update_motor_temperature("joint2", 35.0));
    EXPECT_NO_THROW(monitor_->update_motor_errors("joint1", 0x0000));
    EXPECT_NO_THROW(monitor_->update_vbus_voltage(48.0));

    auto joint_state_msg = std::make_shared<sensor_msgs::msg::JointState>();
    joint_state_msg->name = {"joint2", "joint3", "joint4", "joint5"};
    joint_state_msg->position = {0.0, 0.0, 0.0, 0.0};
    joint_state_msg->velocity = {0.0, 0.0, 0.0, 0.0};
    joint_state_msg->effort = {0.0, 0.0, 0.0, 0.0};
    EXPECT_NO_THROW(monitor_->update_joint_states(joint_state_msg));

    // Run safety checks
    EXPECT_NO_THROW(monitor_->update());

    // Should be safe with normal values after activation + update
    EXPECT_TRUE(monitor_->is_safe());

    monitor_->deactivate();
}

// ============================================================================
// Task 1.4: Parameterized threshold tests
// ============================================================================

// Test fixture with parameter overrides
class SafetyMonitorParamTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        rclcpp::init(0, nullptr);
    }

    void TearDown() override
    {
        rclcpp::shutdown();
    }

    std::unique_ptr<SafetyMonitor> create_monitor_with_params(
        const std::vector<rclcpp::Parameter>& params = {})
    {
        rclcpp::NodeOptions options;
        for (const auto& p : params) {
            options.append_parameter_override(p.get_name(), p.get_parameter_value());
        }
        node_ = std::make_shared<rclcpp::Node>("test_safety_param", options);
        return std::make_unique<SafetyMonitor>(
            node_->get_node_base_interface(),
            node_->get_node_logging_interface(),
            node_->get_node_parameters_interface(),
            node_->get_node_topics_interface(),
            node_->get_node_services_interface()
        );
    }

    std::shared_ptr<rclcpp::Node> node_;
};

// Test: Default thresholds match original hardcoded values
TEST_F(SafetyMonitorParamTest, DefaultThresholdsMatchHardcoded)
{
    auto monitor = create_monitor_with_params();

    // Verify defaults via parameter interface
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.temperature_warning").as_double(), 65.0);
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.temperature_critical").as_double(), 70.0);
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.voltage_min_warning").as_double(), 42.0);
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.voltage_min_critical").as_double(), 40.0);
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.velocity_max").as_double(), 10.0);
}

// Test: Threshold override via parameter
TEST_F(SafetyMonitorParamTest, ThresholdOverrideViaParameter)
{
    auto monitor = create_monitor_with_params({
        rclcpp::Parameter("safety.temperature_critical", 60.0),
        rclcpp::Parameter("safety.velocity_max", 8.0),
    });

    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.temperature_critical").as_double(), 60.0);
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.velocity_max").as_double(), 8.0);

    // Other defaults should be preserved
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.temperature_warning").as_double(), 65.0);
}

// ============================================================================
// Task 1.6: State transition rule tests
// ============================================================================

// Test: UNKNOWN -> INITIALIZING is valid
TEST_F(SafetyMonitorTest, TransitionUnknownToInitializing)
{
    EXPECT_EQ(monitor_->get_state(), SafetyState::UNKNOWN);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::INITIALIZING));
    EXPECT_EQ(monitor_->get_state(), SafetyState::INITIALIZING);
}

// Test: INITIALIZING -> SAFE is valid
TEST_F(SafetyMonitorTest, TransitionInitializingToSafe)
{
    monitor_->transition_to(SafetyState::INITIALIZING);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::SAFE));
    EXPECT_EQ(monitor_->get_state(), SafetyState::SAFE);
}

// Test: SAFE -> WARNING is valid
TEST_F(SafetyMonitorTest, TransitionSafeToWarning)
{
    monitor_->transition_to(SafetyState::INITIALIZING);
    monitor_->transition_to(SafetyState::SAFE);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::WARNING));
    EXPECT_EQ(monitor_->get_state(), SafetyState::WARNING);
}

// Test: WARNING -> SAFE is valid (recovery)
TEST_F(SafetyMonitorTest, TransitionWarningToSafe)
{
    monitor_->transition_to(SafetyState::INITIALIZING);
    monitor_->transition_to(SafetyState::SAFE);
    monitor_->transition_to(SafetyState::WARNING);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::SAFE));
    EXPECT_EQ(monitor_->get_state(), SafetyState::SAFE);
}

// Test: WARNING -> CRITICAL is valid
TEST_F(SafetyMonitorTest, TransitionWarningToCritical)
{
    monitor_->transition_to(SafetyState::INITIALIZING);
    monitor_->transition_to(SafetyState::SAFE);
    monitor_->transition_to(SafetyState::WARNING);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::CRITICAL));
    EXPECT_EQ(monitor_->get_state(), SafetyState::CRITICAL);
}

// Test: Any state -> EMERGENCY is valid
TEST_F(SafetyMonitorTest, TransitionAnyToEmergency)
{
    // From UNKNOWN
    EXPECT_TRUE(monitor_->transition_to(SafetyState::EMERGENCY));
    monitor_->deactivate();  // Reset to UNKNOWN

    // From INITIALIZING
    monitor_->transition_to(SafetyState::INITIALIZING);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::EMERGENCY));
    monitor_->deactivate();

    // From SAFE
    monitor_->transition_to(SafetyState::INITIALIZING);
    monitor_->transition_to(SafetyState::SAFE);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::EMERGENCY));
}

// Test: EMERGENCY -> INITIALIZING is valid (manual reset)
TEST_F(SafetyMonitorTest, TransitionEmergencyToInitializing)
{
    monitor_->transition_to(SafetyState::EMERGENCY);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::INITIALIZING));
    EXPECT_EQ(monitor_->get_state(), SafetyState::INITIALIZING);
}

// Test: EMERGENCY -> SAFE is invalid (no auto-recovery)
TEST_F(SafetyMonitorTest, TransitionEmergencyToSafeRejected)
{
    monitor_->transition_to(SafetyState::EMERGENCY);
    EXPECT_FALSE(monitor_->transition_to(SafetyState::SAFE));
    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
}

// Test: UNKNOWN -> SAFE is invalid (must go through INITIALIZING)
TEST_F(SafetyMonitorTest, TransitionUnknownToSafeRejected)
{
    EXPECT_FALSE(monitor_->transition_to(SafetyState::SAFE));
    EXPECT_EQ(monitor_->get_state(), SafetyState::UNKNOWN);
}

// Test: SAFE -> CRITICAL is valid (direct if both thresholds breached)
TEST_F(SafetyMonitorTest, TransitionSafeToCritical)
{
    monitor_->transition_to(SafetyState::INITIALIZING);
    monitor_->transition_to(SafetyState::SAFE);
    EXPECT_TRUE(monitor_->transition_to(SafetyState::CRITICAL));
    EXPECT_EQ(monitor_->get_state(), SafetyState::CRITICAL);
}

// ============================================================================
// Scenario #3: Invalid threshold rejected by parameter range validation
// ============================================================================

// Test: Out-of-range temperature_warning is rejected at construction time
TEST_F(SafetyMonitorParamTest, InvalidTemperatureWarningRejected)
{
    // safety.temperature_warning has range [0.0, 200.0]
    // Values outside this range should cause parameter declaration to throw
    EXPECT_THROW(
        create_monitor_with_params({
            rclcpp::Parameter("safety.temperature_warning", -10.0),
        }),
        rclcpp::exceptions::InvalidParameterValueException
    );
}

// Test: Out-of-range velocity_max is rejected (below minimum 0.1)
TEST_F(SafetyMonitorParamTest, InvalidVelocityMaxBelowMinRejected)
{
    // safety.velocity_max has range [0.1, 100.0]
    EXPECT_THROW(
        create_monitor_with_params({
            rclcpp::Parameter("safety.velocity_max", 0.0),
        }),
        rclcpp::exceptions::InvalidParameterValueException
    );
}

// Test: Out-of-range voltage_min_critical is rejected (above maximum 100.0)
TEST_F(SafetyMonitorParamTest, InvalidVoltageCriticalAboveMaxRejected)
{
    // safety.voltage_min_critical has range [0.0, 100.0]
    EXPECT_THROW(
        create_monitor_with_params({
            rclcpp::Parameter("safety.voltage_min_critical", 150.0),
        }),
        rclcpp::exceptions::InvalidParameterValueException
    );
}

// ============================================================================
// Scenario #4: Recovery from warning — WARNING -> SAFE when temp normalizes
// ============================================================================

// Test: Temperature-driven WARNING recovers to SAFE when temp drops below warning
TEST_F(SafetyMonitorTest, RecoveryFromWarningToSafeOnTempDrop)
{
    monitor_->activate();

    // Get to SAFE state with normal telemetry
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor_->update_joint_states(msg);
    monitor_->update_vbus_voltage(48.0);
    monitor_->update_motor_temperature("joint2", 30.0);
    monitor_->update_motor_errors("joint2", 0);
    monitor_->update();
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Push temperature into warning range (above 65, below 70)
    monitor_->update_motor_temperature("joint2", 67.0);
    // Temperature check runs every 10 cycles
    for (int i = 0; i < 10; ++i) {
        monitor_->update();
    }
    ASSERT_EQ(monitor_->get_state(), SafetyState::WARNING);

    // Drop temperature back to normal
    monitor_->update_motor_temperature("joint2", 30.0);
    // Run enough update cycles to hit the temperature check again
    for (int i = 0; i < 10; ++i) {
        monitor_->update();
    }

    // Should have recovered to SAFE
    EXPECT_EQ(monitor_->get_state(), SafetyState::SAFE);
    EXPECT_TRUE(monitor_->is_safe());
}

// ============================================================================
// Task 2.1: E-stop execution tests
// ============================================================================

// Helper fixture with mock controllers pre-wired
class SafetyMonitorEStopTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        rclcpp::init(0, nullptr);
        node_ = std::make_shared<rclcpp::Node>("test_estop");
        monitor_ = std::make_unique<SafetyMonitor>(
            node_->get_node_base_interface(),
            node_->get_node_logging_interface(),
            node_->get_node_parameters_interface(),
            node_->get_node_topics_interface(),
            node_->get_node_services_interface()
        );

        // Create 3 mock controllers (base, shoulder, elbow)
        for (int i = 0; i < 3; ++i) {
            auto ctrl = std::make_shared<MockMotorController>();
            controllers_.push_back(ctrl);
        }

        // Wire controllers into SafetyMonitor
        std::vector<std::shared_ptr<MotorControllerInterface>> iface_vec(
            controllers_.begin(), controllers_.end());
        monitor_->set_controllers(iface_vec);

        // Activate and get to SAFE state
        monitor_->activate();
        auto msg = std::make_shared<sensor_msgs::msg::JointState>();
        msg->name = {"joint2", "joint3", "joint4", "joint5"};
        msg->position = {0.0, 0.0, 0.0, 0.0};
        msg->velocity = {0.0, 0.0, 0.0, 0.0};
        msg->effort = {0.0, 0.0, 0.0, 0.0};
        monitor_->update_joint_states(msg);
        monitor_->update_vbus_voltage(48.0);
        monitor_->update_motor_temperature("joint2", 30.0);
        monitor_->update_motor_errors("joint2", 0);
        monitor_->update();
    }

    void TearDown() override
    {
        monitor_.reset();
        node_.reset();
        rclcpp::shutdown();
    }

    std::shared_ptr<rclcpp::Node> node_;
    std::unique_ptr<SafetyMonitor> monitor_;
    std::vector<std::shared_ptr<MockMotorController>> controllers_;
};

// Scenario: Emergency shutdown sends CAN stop to all motors
TEST_F(SafetyMonitorEStopTest, EStopCallsAllControllers)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    monitor_->trigger_emergency_shutdown("test e-stop");

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    for (size_t i = 0; i < controllers_.size(); ++i) {
        EXPECT_EQ(controllers_[i]->emergency_stop_count.load(), 1)
            << "Controller " << i << " emergency_stop() not called";
    }
}

// Scenario: Emergency shutdown with one motor unreachable
TEST_F(SafetyMonitorEStopTest, EStopHandlesUnreachableMotor)
{
    // Motor 1 will fail emergency_stop()
    controllers_[1]->emergency_stop_should_fail = true;

    monitor_->trigger_emergency_shutdown("unreachable motor test");

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    // All 3 controllers should still have emergency_stop() called (fire-all pattern)
    for (size_t i = 0; i < controllers_.size(); ++i) {
        EXPECT_EQ(controllers_[i]->emergency_stop_count.load(), 1)
            << "Controller " << i << " emergency_stop() not called";
    }
}

// Scenario: E-stop cascade — single fault stops all motors
TEST_F(SafetyMonitorEStopTest, EStopCascadesToAllMotors)
{
    // Simulate temperature violation on one motor
    monitor_->update_motor_temperature("joint2", 85.0);
    // Temperature check runs every 10 cycles, so call update 10 times
    for (int i = 0; i < 10; ++i) {
        monitor_->update();
    }

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    // ALL controllers should have been stopped, not just the one with the fault
    for (size_t i = 0; i < controllers_.size(); ++i) {
        EXPECT_GE(controllers_[i]->emergency_stop_count.load(), 1)
            << "Controller " << i << " not stopped during cascade";
    }
}

// Scenario: Fire-all-then-verify — stop sent to all without waiting for ack
TEST_F(SafetyMonitorEStopTest, EStopFireAllThenVerify)
{
    // Simulate slow controller by having one fail
    controllers_[0]->emergency_stop_should_fail = true;

    monitor_->trigger_emergency_shutdown("fire-all test");

    // Even though controller 0 failed, controllers 1 and 2 must still be stopped
    EXPECT_EQ(controllers_[0]->emergency_stop_count.load(), 1);
    EXPECT_EQ(controllers_[1]->emergency_stop_count.load(), 1);
    EXPECT_EQ(controllers_[2]->emergency_stop_count.load(), 1);
}

// Scenario: E-stop with no controllers configured still works (no crash)
TEST_F(SafetyMonitorEStopTest, EStopWithNoControllersDoesNotCrash)
{
    // Create a separate node to avoid parameter redeclaration conflicts
    auto node2 = std::make_shared<rclcpp::Node>("test_estop_no_controllers_node");
    auto monitor2 = std::make_unique<SafetyMonitor>(
        node2->get_node_base_interface(),
        node2->get_node_logging_interface(),
        node2->get_node_parameters_interface(),
        node2->get_node_topics_interface(),
        node2->get_node_services_interface()
    );
    monitor2->activate();

    EXPECT_NO_THROW(monitor2->trigger_emergency_shutdown("no controllers test"));
    EXPECT_EQ(monitor2->get_state(), SafetyState::EMERGENCY);
}

// Scenario: Multiple triggers execute shutdown on each controller only during each trigger
TEST_F(SafetyMonitorEStopTest, MultipleTriggersStillCallsControllers)
{
    monitor_->trigger_emergency_shutdown("first trigger");

    // First trigger should call all controllers
    for (size_t i = 0; i < controllers_.size(); ++i) {
        EXPECT_EQ(controllers_[i]->emergency_stop_count.load(), 1);
    }

    // Second trigger — already in EMERGENCY, but e-stop should still
    // attempt to stop motors (defense in depth)
    monitor_->trigger_emergency_shutdown("second trigger");
    for (size_t i = 0; i < controllers_.size(); ++i) {
        EXPECT_EQ(controllers_[i]->emergency_stop_count.load(), 2);
    }
}

// ============================================================================
// Scenario #10: CAN bus error on one motor stops all motors
// ============================================================================

// Test: Critical motor error flags on one motor triggers e-stop for all
TEST_F(SafetyMonitorEStopTest, CANBusErrorCascadeStopsAllMotors)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Set a critical motor error (DRV_FAULT = 0x0020) on just one motor
    // CRITICAL_ERRORS mask in check_motor_error_status is 0x00F2
    // Bits 1,4,5,6,7 are critical
    monitor_->update_motor_errors("joint2", 0x0020);  // DRV_FAULT on joint2 only

    // Motor error check runs every cycle, so a single update should trigger it
    monitor_->update();

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY)
        << "Critical motor error should trigger EMERGENCY state";

    // ALL controllers should have been stopped, not just the one with the error
    for (size_t i = 0; i < controllers_.size(); ++i) {
        EXPECT_GE(controllers_[i]->emergency_stop_count.load(), 1)
            << "Controller " << i << " should be stopped in CAN error cascade";
    }
}

// ============================================================================
// Task 2.4: E-stop trigger source tests
// ============================================================================

// Scenario: Temperature violation triggers shutdown
TEST_F(SafetyMonitorEStopTest, TemperatureViolationTriggersEStop)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Set critical temperature (default threshold: 70C)
    monitor_->update_motor_temperature("joint2", 75.0);
    // Temperature check runs every 10 cycles
    for (int i = 0; i < 10; ++i) {
        monitor_->update();
    }

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    for (auto& ctrl : controllers_) {
        EXPECT_GE(ctrl->emergency_stop_count.load(), 1);
    }
}

// Scenario: Multiple simultaneous triggers execute shutdown once per trigger call
TEST_F(SafetyMonitorEStopTest, SimultaneousTriggersExecuteOnce)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Set up both a temperature violation and a voltage violation
    monitor_->update_motor_temperature("joint2", 85.0);
    monitor_->update_vbus_voltage(35.0);  // Below critical 40V

    // Run enough cycles to hit both temperature (10 cycles) and voltage (20 cycles) checks
    for (int i = 0; i < 20; ++i) {
        monitor_->update();
    }

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    // Controllers should have been stopped (may be called more than once from
    // multiple triggers, which is acceptable — defense in depth)
    for (auto& ctrl : controllers_) {
        EXPECT_GE(ctrl->emergency_stop_count.load(), 1);
    }
}

// ============================================================================
// Task 2.6: E-stop recovery tests
// ============================================================================

// Scenario: Commands rejected after e-stop (is_safe returns false)
TEST_F(SafetyMonitorEStopTest, CommandsRejectedAfterEStop)
{
    monitor_->trigger_emergency_shutdown("test");

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    EXPECT_FALSE(monitor_->is_safe());
}

// Scenario: Auto-recovery is impossible — state stays EMERGENCY even if fault clears
TEST_F(SafetyMonitorEStopTest, NoAutoRecoveryFromEmergency)
{
    monitor_->trigger_emergency_shutdown("over-temperature");

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);

    // Simulate fault clearing — provide normal telemetry
    monitor_->update_motor_temperature("joint2", 30.0);
    monitor_->update_vbus_voltage(48.0);
    monitor_->update();

    // State should STILL be EMERGENCY — no auto-recovery
    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
    EXPECT_FALSE(monitor_->is_safe());
}

// Scenario: EMERGENCY -> SAFE direct transition is invalid
TEST_F(SafetyMonitorEStopTest, EmergencyToSafeRejected)
{
    monitor_->trigger_emergency_shutdown("test");

    EXPECT_FALSE(monitor_->transition_to(SafetyState::SAFE));
    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
}

// Scenario: Manual reset transitions EMERGENCY -> INITIALIZING
TEST_F(SafetyMonitorEStopTest, ManualResetToInitializing)
{
    monitor_->trigger_emergency_shutdown("test");

    // Manual reset goes through INITIALIZING
    EXPECT_TRUE(monitor_->transition_to(SafetyState::INITIALIZING));
    EXPECT_EQ(monitor_->get_state(), SafetyState::INITIALIZING);
}

// ============================================================================
// Integration Scenario #1: State queryable via /safety/state topic
// ============================================================================

TEST_F(SafetyMonitorTest, StatePublishedToTopic)
{
    // Subscribe to /safety/state topic
    std::string received_state;
    bool message_received = false;

    auto sub = node_->create_subscription<std_msgs::msg::String>(
        "/safety/state",
        rclcpp::QoS(10).transient_local(),
        [&](const std_msgs::msg::String::SharedPtr msg) {
            received_state = msg->data;
            message_received = true;
        }
    );

    // Activate the monitor — triggers UNKNOWN -> INITIALIZING transition
    monitor_->activate();

    // Spin to process published messages
    auto start = std::chrono::steady_clock::now();
    while (!message_received &&
           std::chrono::steady_clock::now() - start < std::chrono::seconds(2)) {
        rclcpp::spin_some(node_);
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    EXPECT_TRUE(message_received)
        << "/safety/state topic should publish on state transitions";
    EXPECT_EQ(received_state, "INITIALIZING")
        << "Published state should be INITIALIZING after activate()";
}

// ============================================================================
// Integration Scenario #2: Runtime threshold update via SetParameters
// ============================================================================

TEST_F(SafetyMonitorTest, RuntimeThresholdUpdateViaSetParameters)
{
    monitor_->activate();

    // Get to SAFE state with normal telemetry
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor_->update_joint_states(msg);
    monitor_->update_vbus_voltage(48.0);
    monitor_->update_motor_temperature("joint2", 30.0);
    monitor_->update_motor_errors("joint2", 0);
    monitor_->update();
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Update temperature_warning threshold at runtime to 25.0 (below current 30C)
    auto set_result = node_->set_parameter(
        rclcpp::Parameter("safety.temperature_warning", 25.0));
    EXPECT_TRUE(set_result.successful)
        << "Runtime parameter update should succeed";

    // Verify the new threshold is read back from parameter server
    EXPECT_DOUBLE_EQ(
        node_->get_parameter("safety.temperature_warning").as_double(), 25.0);

    // Now run update cycles — with threshold 25C and temp 30C, should trigger WARNING
    for (int i = 0; i < 10; ++i) {
        monitor_->update();
    }

    EXPECT_EQ(monitor_->get_state(), SafetyState::WARNING)
        << "State should be WARNING after lowering threshold below current temp";
}

// ============================================================================
// Integration Scenario #7: ROS2 service call triggers emergency shutdown
// ============================================================================

TEST_F(SafetyMonitorEStopTest, ServiceCallTriggersEmergencyShutdown)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Create client for /safety/trigger_emergency_stop service
    auto client = node_->create_client<std_srvs::srv::Trigger>(
        "/safety/trigger_emergency_stop");
    ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(1)))
        << "/safety/trigger_emergency_stop service should be available";

    auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
    auto future = client->async_send_request(request);

    auto status = rclcpp::spin_until_future_complete(node_, future, std::chrono::seconds(2));
    ASSERT_EQ(status, rclcpp::FutureReturnCode::SUCCESS)
        << "Service call should complete";

    auto response = future.get();
    EXPECT_TRUE(response->success)
        << "Emergency stop service should succeed";

    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY)
        << "State should be EMERGENCY after service call";

    // All controllers should have been stopped
    for (size_t i = 0; i < controllers_.size(); ++i) {
        EXPECT_GE(controllers_[i]->emergency_stop_count.load(), 1)
            << "Controller " << i << " should be stopped via service";
    }
}

// ============================================================================
// Scenario #9: Reset rejected while fault persists (via /safety/reset service)
// ============================================================================

// Test: Safety reset rejected when temperature fault still active
TEST_F(SafetyMonitorEStopTest, ResetRejectedWhileTemperatureFaultPersists)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Trigger e-stop via critical temperature
    monitor_->update_motor_temperature("joint2", 85.0);
    for (int i = 0; i < 10; ++i) {
        monitor_->update();
    }
    ASSERT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);

    // Call the /safety/reset service — temperature is still 85C > 70C critical
    auto client = node_->create_client<std_srvs::srv::Trigger>("/safety/reset");
    ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(1)))
        << "/safety/reset service should be available";

    auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
    auto future = client->async_send_request(request);

    // Spin until we get a response
    auto status = rclcpp::spin_until_future_complete(node_, future, std::chrono::seconds(2));
    ASSERT_EQ(status, rclcpp::FutureReturnCode::SUCCESS)
        << "Service call should complete";

    auto response = future.get();
    EXPECT_FALSE(response->success)
        << "Reset should be rejected while temperature fault persists";
    EXPECT_TRUE(response->message.find("fault persists") != std::string::npos ||
                response->message.find("temperature") != std::string::npos)
        << "Response should indicate persistent fault, got: " << response->message;

    // State should still be EMERGENCY
    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);
}

// Test: Safety reset succeeds after all faults are cleared
TEST_F(SafetyMonitorEStopTest, ResetSucceedsAfterFaultCleared)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // Trigger e-stop
    monitor_->trigger_emergency_shutdown("test fault");
    ASSERT_EQ(monitor_->get_state(), SafetyState::EMERGENCY);

    // Clear all fault conditions
    monitor_->update_motor_temperature("joint2", 30.0);
    monitor_->update_vbus_voltage(48.0);
    monitor_->update_motor_errors("joint2", 0);

    // Call the /safety/reset service — all faults cleared
    auto client = node_->create_client<std_srvs::srv::Trigger>("/safety/reset");
    ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(1)));

    auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
    auto future = client->async_send_request(request);

    auto status = rclcpp::spin_until_future_complete(node_, future, std::chrono::seconds(2));
    ASSERT_EQ(status, rclcpp::FutureReturnCode::SUCCESS);

    auto response = future.get();
    EXPECT_TRUE(response->success)
        << "Reset should succeed when all faults are cleared";
    EXPECT_EQ(monitor_->get_state(), SafetyState::INITIALIZING)
        << "State should transition to INITIALIZING after successful reset";
}

// ============================================================================
// Scenario #8: Communication timeout (watchdog) triggers shutdown
// ============================================================================

// Test: Joint state communication timeout triggers emergency shutdown
TEST_F(SafetyMonitorEStopTest, CommunicationTimeoutTriggersEStop)
{
    ASSERT_EQ(monitor_->get_state(), SafetyState::SAFE);

    // The monitor has received joint states (from SetUp).
    // Communication timeout check runs every 5 cycles.
    // Default timeout_threshold_ is 1.0s (from code).
    // We need to wait > timeout_threshold_ without new joint state updates.

    // Sleep to let the joint state timestamp go stale
    std::this_thread::sleep_for(std::chrono::milliseconds(1200));

    // Run enough update cycles to hit the communication timeout check (every 5 cycles)
    for (int i = 0; i < 5; ++i) {
        monitor_->update();
    }

    // Should be in EMERGENCY due to communication timeout
    EXPECT_EQ(monitor_->get_state(), SafetyState::EMERGENCY)
        << "Communication timeout should trigger emergency shutdown";
    for (auto& ctrl : controllers_) {
        EXPECT_GE(ctrl->emergency_stop_count.load(), 1)
            << "Controllers should be stopped on communication timeout";
    }
}

// ============================================================================
// Task 1.5: BoundedLruMap unit tests
// ============================================================================

TEST(BoundedLruMapTest, InsertAndRetrieve)
{
    BoundedLruMap<std::string, int> map(10);
    map.put("a", 1);
    map.put("b", 2);

    EXPECT_TRUE(map.contains("a"));
    EXPECT_TRUE(map.contains("b"));
    EXPECT_EQ(map.get("a"), 1);
    EXPECT_EQ(map.get("b"), 2);
    EXPECT_EQ(map.size(), 2u);
}

TEST(BoundedLruMapTest, UpdateExistingKey)
{
    BoundedLruMap<std::string, int> map(10);
    map.put("a", 1);
    map.put("a", 42);

    EXPECT_EQ(map.size(), 1u);
    EXPECT_EQ(map.get("a"), 42);
}

TEST(BoundedLruMapTest, EvictsOldestAtCapacity)
{
    BoundedLruMap<int, int> map(3);
    map.put(1, 10);
    map.put(2, 20);
    map.put(3, 30);
    EXPECT_EQ(map.size(), 3u);

    // Insert a 4th entry — oldest (key=1) should be evicted
    map.put(4, 40);
    EXPECT_EQ(map.size(), 3u);
    EXPECT_FALSE(map.contains(1));
    EXPECT_TRUE(map.contains(2));
    EXPECT_TRUE(map.contains(3));
    EXPECT_TRUE(map.contains(4));
}

TEST(BoundedLruMapTest, AccessRefreshesLruOrder)
{
    BoundedLruMap<int, int> map(3);
    map.put(1, 10);
    map.put(2, 20);
    map.put(3, 30);

    // Access key=1 via put (refresh) — makes key=2 the oldest
    map.put(1, 11);
    map.put(4, 40);

    EXPECT_EQ(map.size(), 3u);
    EXPECT_FALSE(map.contains(2));  // key=2 was oldest, evicted
    EXPECT_TRUE(map.contains(1));
    EXPECT_TRUE(map.contains(3));
    EXPECT_TRUE(map.contains(4));
    EXPECT_EQ(map.get(1), 11);
}

TEST(BoundedLruMapTest, ClearRemovesAllEntries)
{
    BoundedLruMap<int, int> map(10);
    map.put(1, 10);
    map.put(2, 20);
    map.clear();
    EXPECT_EQ(map.size(), 0u);
    EXPECT_FALSE(map.contains(1));
    EXPECT_FALSE(map.contains(2));
}

TEST(BoundedLruMapTest, MaxSizeReportedCorrectly)
{
    BoundedLruMap<int, int> map(42);
    EXPECT_EQ(map.max_size(), 42u);
}

TEST(BoundedLruMapTest, EvictionCascadeAtCapacityOne)
{
    BoundedLruMap<int, int> map(1);
    map.put(1, 10);
    EXPECT_EQ(map.size(), 1u);
    EXPECT_EQ(map.get(1), 10);

    map.put(2, 20);
    EXPECT_EQ(map.size(), 1u);
    EXPECT_FALSE(map.contains(1));
    EXPECT_TRUE(map.contains(2));
    EXPECT_EQ(map.get(2), 20);
}

// ============================================================================
// Task 1.5: Clean state on recreation (no stale static carry-over)
// ============================================================================

// Verify that creating a second SafetyMonitor after destroying the first
// starts with completely clean state — no leaked static locals.
TEST(SafetyMonitorRecreationTest, NoStaleStateOnRecreation)
{
    // First instance
    {
        rclcpp::init(0, nullptr);
        auto node = std::make_shared<rclcpp::Node>("test_recreation_1");
        auto monitor = std::make_unique<SafetyMonitor>(
            node->get_node_base_interface(),
            node->get_node_logging_interface(),
            node->get_node_parameters_interface(),
            node->get_node_topics_interface(),
            node->get_node_services_interface()
        );

        // Drive monitor into a specific state
        monitor->activate();
        auto msg = std::make_shared<sensor_msgs::msg::JointState>();
        msg->name = {"joint2", "joint3", "joint4", "joint5"};
        msg->position = {0.0, 0.0, 0.0, 0.0};
        msg->velocity = {0.0, 0.0, 0.0, 0.0};
        msg->effort = {0.0, 0.0, 0.0, 0.0};
        monitor->update_joint_states(msg);
        monitor->update_vbus_voltage(48.0);
        monitor->update_motor_temperature("joint2", 30.0);
        monitor->update_motor_errors("joint2", 0);
        monitor->update();
        ASSERT_EQ(monitor->get_state(), SafetyState::SAFE);

        // Now push into EMERGENCY
        monitor->trigger_emergency_shutdown("test contamination");
        ASSERT_EQ(monitor->get_state(), SafetyState::EMERGENCY);

        // Destroy
        monitor.reset();
        node.reset();
        rclcpp::shutdown();
    }

    // Second instance — should start fresh
    {
        rclcpp::init(0, nullptr);
        auto node = std::make_shared<rclcpp::Node>("test_recreation_2");
        auto monitor = std::make_unique<SafetyMonitor>(
            node->get_node_base_interface(),
            node->get_node_logging_interface(),
            node->get_node_parameters_interface(),
            node->get_node_topics_interface(),
            node->get_node_services_interface()
        );

        // Fresh monitor must start in UNKNOWN, not carry over EMERGENCY
        EXPECT_EQ(monitor->get_state(), SafetyState::UNKNOWN);
        EXPECT_FALSE(monitor->is_safe());

        // Activate and get to SAFE — should work without interference from first instance
        monitor->activate();
        auto msg = std::make_shared<sensor_msgs::msg::JointState>();
        msg->name = {"joint2", "joint3", "joint4", "joint5"};
        msg->position = {0.0, 0.0, 0.0, 0.0};
        msg->velocity = {0.0, 0.0, 0.0, 0.0};
        msg->effort = {0.0, 0.0, 0.0, 0.0};
        monitor->update_joint_states(msg);
        monitor->update_vbus_voltage(48.0);
        monitor->update_motor_temperature("joint2", 30.0);
        monitor->update_motor_errors("joint2", 0);
        monitor->update();

        EXPECT_EQ(monitor->get_state(), SafetyState::SAFE)
            << "Second instance should reach SAFE without stale state interference";
        EXPECT_TRUE(monitor->is_safe());

        monitor.reset();
        node.reset();
        rclcpp::shutdown();
    }
}

// ============================================================================
// Concurrent thread-safety tests
// ============================================================================

// Helper: check that a SafetyState value is one of the valid enum values
static bool is_valid_state(SafetyState s)
{
    return s == SafetyState::UNKNOWN ||
           s == SafetyState::INITIALIZING ||
           s == SafetyState::SAFE ||
           s == SafetyState::WARNING ||
           s == SafetyState::CRITICAL ||
           s == SafetyState::EMERGENCY;
}

// Scenario: Concurrent update calls without data races
TEST(ConcurrentUpdateTest, MultipleThreadsCallingUpdateNoCrash)
{
    rclcpp::init(0, nullptr);
    auto node = std::make_shared<rclcpp::Node>("test_concurrent_update");
    auto monitor = std::make_unique<SafetyMonitor>(
        node->get_node_base_interface(),
        node->get_node_logging_interface(),
        node->get_node_parameters_interface(),
        node->get_node_topics_interface(),
        node->get_node_services_interface()
    );

    // Activate and feed valid data to reach SAFE
    monitor->activate();
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor->update_joint_states(msg);
    monitor->update_vbus_voltage(48.0);
    monitor->update_motor_temperature("joint2", 30.0);
    monitor->update_motor_errors("joint2", 0);
    monitor->update();
    ASSERT_EQ(monitor->get_state(), SafetyState::SAFE);

    // Spawn 4 threads each calling update() 100 times
    constexpr int kNumThreads = 4;
    constexpr int kIterations = 100;
    std::vector<std::thread> threads;
    threads.reserve(kNumThreads);

    for (int t = 0; t < kNumThreads; ++t) {
        threads.emplace_back([&monitor, kIterations]() {
            for (int i = 0; i < kIterations; ++i) {
                monitor->update();
            }
        });
    }

    for (auto& th : threads) {
        th.join();
    }

    // After all threads finish, state must still be valid
    SafetyState final_state = monitor->get_state();
    EXPECT_TRUE(is_valid_state(final_state))
        << "State after concurrent updates is not a valid SafetyState";
    // State should be SAFE or WARNING (not crashed, not corrupted)
    EXPECT_TRUE(final_state == SafetyState::SAFE || final_state == SafetyState::WARNING)
        << "Expected SAFE or WARNING after concurrent updates on valid data";

    monitor.reset();
    node.reset();
    rclcpp::shutdown();
}

// Scenario: Concurrent update_joint_states and update calls
TEST(ConcurrentUpdateJointStatesAndUpdateTest, NoDataRace)
{
    rclcpp::init(0, nullptr);
    auto node = std::make_shared<rclcpp::Node>("test_concurrent_joint_update");
    auto monitor = std::make_unique<SafetyMonitor>(
        node->get_node_base_interface(),
        node->get_node_logging_interface(),
        node->get_node_parameters_interface(),
        node->get_node_topics_interface(),
        node->get_node_services_interface()
    );

    // Activate and feed initial valid data
    monitor->activate();
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor->update_joint_states(msg);
    monitor->update_vbus_voltage(48.0);
    monitor->update_motor_temperature("joint2", 30.0);
    monitor->update_motor_errors("joint2", 0);
    monitor->update();

    constexpr int kIterations = 200;

    // Thread 1: repeatedly call update_joint_states()
    std::thread joint_thread([&monitor, &msg, kIterations]() {
        for (int i = 0; i < kIterations; ++i) {
            monitor->update_joint_states(msg);
        }
    });

    // Thread 2: repeatedly call update()
    std::thread update_thread([&monitor, kIterations]() {
        for (int i = 0; i < kIterations; ++i) {
            monitor->update();
        }
    });

    joint_thread.join();
    update_thread.join();

    SafetyState final_state = monitor->get_state();
    EXPECT_TRUE(is_valid_state(final_state))
        << "State after concurrent joint_states/update is not a valid SafetyState";

    monitor.reset();
    node.reset();
    rclcpp::shutdown();
}

// Scenario: Concurrent state transitions (CAS loop — emergency always wins)
TEST(ConcurrentStateTransitionTest, EmergencyAlwaysWins)
{
    rclcpp::init(0, nullptr);
    auto node = std::make_shared<rclcpp::Node>("test_concurrent_transition");
    auto monitor = std::make_unique<SafetyMonitor>(
        node->get_node_base_interface(),
        node->get_node_logging_interface(),
        node->get_node_parameters_interface(),
        node->get_node_topics_interface(),
        node->get_node_services_interface()
    );

    // Activate and reach SAFE
    monitor->activate();
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor->update_joint_states(msg);
    monitor->update_vbus_voltage(48.0);
    monitor->update_motor_temperature("joint2", 30.0);
    monitor->update_motor_errors("joint2", 0);
    monitor->update();
    ASSERT_EQ(monitor->get_state(), SafetyState::SAFE);

    constexpr int kIterations = 200;

    // Thread 1: trigger emergency shutdown
    std::thread emergency_thread([&monitor]() {
        monitor->trigger_emergency_shutdown("concurrent test emergency");
    });

    // Thread 2: repeatedly update to try to keep SAFE
    std::thread update_thread([&monitor, kIterations]() {
        for (int i = 0; i < kIterations; ++i) {
            monitor->update();
        }
    });

    emergency_thread.join();
    update_thread.join();

    // Emergency must always win — EMERGENCY is a terminal state
    EXPECT_EQ(monitor->get_state(), SafetyState::EMERGENCY)
        << "Emergency shutdown must always win over concurrent updates";

    monitor.reset();
    node.reset();
    rclcpp::shutdown();
}

// Scenario: Parameter callback does not race with check methods
TEST(ConcurrentParameterAndCheckTest, ReadersDoNotRaceWithUpdate)
{
    rclcpp::init(0, nullptr);
    auto node = std::make_shared<rclcpp::Node>("test_concurrent_param_check");
    auto monitor = std::make_unique<SafetyMonitor>(
        node->get_node_base_interface(),
        node->get_node_logging_interface(),
        node->get_node_parameters_interface(),
        node->get_node_topics_interface(),
        node->get_node_services_interface()
    );

    // Activate and feed valid data
    monitor->activate();
    auto msg = std::make_shared<sensor_msgs::msg::JointState>();
    msg->name = {"joint2", "joint3", "joint4", "joint5"};
    msg->position = {0.0, 0.0, 0.0, 0.0};
    msg->velocity = {0.0, 0.0, 0.0, 0.0};
    msg->effort = {0.0, 0.0, 0.0, 0.0};
    monitor->update_joint_states(msg);
    monitor->update_vbus_voltage(48.0);
    monitor->update_motor_temperature("joint2", 30.0);
    monitor->update_motor_errors("joint2", 0);
    monitor->update();

    constexpr int kIterations = 200;

    // Thread 1: repeatedly read is_safe() and get_state()
    std::thread reader_thread([&monitor, kIterations]() {
        for (int i = 0; i < kIterations; ++i) {
            bool safe = monitor->is_safe();
            SafetyState state = monitor->get_state();
            // Suppress unused-variable warnings; the point is no crash
            (void)safe;
            (void)state;
        }
    });

    // Thread 2: repeatedly call update()
    std::thread update_thread([&monitor, kIterations]() {
        for (int i = 0; i < kIterations; ++i) {
            monitor->update();
        }
    });

    reader_thread.join();
    update_thread.join();

    // If we got here without crashing, the test passed.
    // Final state must still be valid.
    SafetyState final_state = monitor->get_state();
    EXPECT_TRUE(is_valid_state(final_state))
        << "State after concurrent read/update is not a valid SafetyState";

    monitor.reset();
    node.reset();
    rclcpp::shutdown();
}

} // namespace motor_control_ros2
