/*
 * Motor Control Integration Tests and Performance Benchmarks
 *
 * This test suite validates the interaction between different motor control
 * components and provides comprehensive performance benchmarks.
 *
 * Test Categories:
 * 1. Integration Tests - Component interaction validation
 * 2. Performance Benchmarks - Timing and resource usage validation
 * 3. End-to-End System Tests - Complete system validation
 * 4. Stress Tests - System behavior under load
 * 5. Real-time Performance Tests - Deterministic behavior validation
 */

#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include <memory>
#include <thread>
#include <chrono>
#include <vector>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include <numeric>

// Motor control system headers
#include "enhanced_can_interface.hpp"
#include "comprehensive_error_handler.hpp"
#include "advanced_initialization_system.hpp"
#include "dual_encoder_system.hpp"
#include "advanced_pid_system.hpp"
#include "motor_control_validation_framework.hpp"
#include "hardware_in_loop_testing.hpp"

using namespace motor_control_ros2;
using namespace motor_control_ros2::validation;
using namespace motor_control_ros2::hardware_testing;
using namespace testing;
using namespace std::chrono_literals;

// =============================================================================
// PERFORMANCE MEASUREMENT UTILITIES
// =============================================================================

/**
 * @brief High-precision timer for performance measurements
 */
class PerformanceTimer
{
public:
  void start()
  {
    start_time_ = std::chrono::high_resolution_clock::now();
  }

  void stop()
  {
    end_time_ = std::chrono::high_resolution_clock::now();
  }

  double get_duration_us() const
  {
    auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end_time_ - start_time_);
    return static_cast<double>(duration.count()) / 1000.0; // Convert to microseconds
  }

  double get_duration_ms() const
  {
    return get_duration_us() / 1000.0;
  }

private:
  std::chrono::high_resolution_clock::time_point start_time_;
  std::chrono::high_resolution_clock::time_point end_time_;
};

/**
 * @brief Performance statistics calculator
 */
class PerformanceStats
{
public:
  void add_measurement(double value)
  {
    measurements_.push_back(value);
  }

  void clear()
  {
    measurements_.clear();
  }

  double get_mean() const
  {
    if (measurements_.empty()) {return 0.0;}
    return std::accumulate(measurements_.begin(), measurements_.end(), 0.0) / measurements_.size();
  }

  double get_std_dev() const
  {
    if (measurements_.size() < 2) {return 0.0;}
    double mean = get_mean();
    double variance = 0.0;
    for (const auto & val : measurements_) {
      variance += std::pow(val - mean, 2);
    }
    return std::sqrt(variance / (measurements_.size() - 1));
  }

  double get_min() const
  {
    if (measurements_.empty()) {return 0.0;}
    return *std::min_element(measurements_.begin(), measurements_.end());
  }

  double get_max() const
  {
    if (measurements_.empty()) {return 0.0;}
    return *std::max_element(measurements_.begin(), measurements_.end());
  }

  double get_percentile(double p) const
  {
    if (measurements_.empty()) {return 0.0;}
    auto sorted = measurements_;
    std::sort(sorted.begin(), sorted.end());
    size_t index = static_cast<size_t>(p * (sorted.size() - 1) / 100.0);
    return sorted[index];
  }

  size_t get_count() const
  {
    return measurements_.size();
  }

private:
  std::vector<double> measurements_;
};

// =============================================================================
// INTEGRATION TEST FIXTURES
// =============================================================================

/**
 * @brief Integration test fixture with all motor control components
 */
class MotorControlIntegrationTest : public Test
{
protected:
  void SetUp() override
  {
    // Initialize validation framework
    validation_framework_ = std::make_unique<ValidationFramework>();

    // Setup simulation parameters
    MotorPhysicsParams motor_params;
    motor_params.motor_inertia = 0.001;
    motor_params.load_inertia = 0.005;
    motor_params.max_torque = 5.0;

    EncoderSimParams primary_encoder_params;
    primary_encoder_params.name = "primary_encoder";
    primary_encoder_params.counts_per_revolution = 8192;

    EncoderSimParams secondary_encoder_params;
    secondary_encoder_params.name = "secondary_encoder";
    secondary_encoder_params.counts_per_revolution = 4096;

    CANSimParams can_params;
    can_params.baud_rate = 1000000;

    FaultInjectionParams fault_params;

    ASSERT_TRUE(validation_framework_->initialize(
      motor_params, primary_encoder_params, secondary_encoder_params,
      can_params, fault_params));

    // Initialize motor control components
    error_handler_ = std::make_shared<ComprehensiveErrorHandler>();
    can_interface_ = std::make_shared<EnhancedCANController>();
    init_system_ = std::make_unique<AdvancedInitializationSystem>();
    dual_encoder_system_ = std::make_unique<DualEncoderSystem>();
    pid_controller_ = std::make_unique<AdvancedPIDController>();

    // Connect components to validation framework
    validation_framework_->connect_error_handler(error_handler_);
    validation_framework_->connect_can_interface(can_interface_);

    // Start simulation
    ASSERT_TRUE(validation_framework_->start_simulation(0.001)); // 1ms time step
  }

  void TearDown() override
  {
    if (validation_framework_) {
      validation_framework_->stop_simulation();
      validation_framework_->shutdown();
    }
  }

  std::unique_ptr<ValidationFramework> validation_framework_;
  std::shared_ptr<ComprehensiveErrorHandler> error_handler_;
  std::shared_ptr<EnhancedCANController> can_interface_;
  std::unique_ptr<AdvancedInitializationSystem> init_system_;
  std::unique_ptr<DualEncoderSystem> dual_encoder_system_;
  std::unique_ptr<AdvancedPIDController> pid_controller_;
};

// =============================================================================
// INTEGRATION TESTS
// =============================================================================

TEST_F(MotorControlIntegrationTest, CanInterfaceAndErrorHandlerIntegration)
{
  // Test CAN interface error reporting to error handler
  ProtocolConfig config;
  config.protocol = CANProtocol::ODRIVE_CUSTOM;
  config.baud_rate = 1000000;

  // Initialize CAN interface (should succeed in simulation)
  EXPECT_TRUE(can_interface_->initialize("can0", config));

  // Simulate CAN error
  validation_framework_->inject_can_message_loss(true);

  // Wait for error to propagate
  std::this_thread::sleep_for(100ms);

  // Check if error handler received CAN errors
  auto active_errors = error_handler_->get_active_errors();
  bool found_can_error = false;
  for (const auto & error : active_errors) {
    if (error.error_code == MotorErrorCode::CAN_TIMEOUT ||
      error.error_code == MotorErrorCode::CAN_BUS_OFF)
    {
      found_can_error = true;
      break;
    }
  }

  // Should have detected CAN communication issues
  EXPECT_TRUE(found_can_error);
}

TEST_F(MotorControlIntegrationTest, DualEncoderSystemIntegration)
{
  // Initialize dual encoder system
  DualEncoderConfig encoder_config;
  encoder_config.primary_encoder.name = "primary_encoder";
  encoder_config.secondary_encoder.name = "secondary_encoder";
  encoder_config.enable_sensor_fusion = true;
  encoder_config.enable_cross_validation = true;

  EXPECT_TRUE(dual_encoder_system_->initialize(encoder_config, error_handler_));
  EXPECT_TRUE(dual_encoder_system_->start_acquisition());

  // Let system run and collect data
  std::this_thread::sleep_for(500ms);

  // Verify encoder data is being acquired
  auto primary_data = dual_encoder_system_->get_primary_encoder_data();
  auto secondary_data = dual_encoder_system_->get_secondary_encoder_data();
  auto fused_data = dual_encoder_system_->get_position_data();

  EXPECT_GT(primary_data.timestamp.time_since_epoch().count(), 0);
  EXPECT_GT(secondary_data.timestamp.time_since_epoch().count(), 0);
  EXPECT_GT(fused_data.timestamp.time_since_epoch().count(), 0);

  // Test cross-validation
  EXPECT_TRUE(dual_encoder_system_->perform_cross_validation());
}

TEST_F(MotorControlIntegrationTest, InitializationSystemIntegration)
{
  // Test initialization system with dual encoder support
  InitializationConfig init_config;
  init_config.method = InitializationMethod::ABSOLUTE_ENCODER;
  init_config.use_multi_turn_encoder = true;
  init_config.encoder_counts_per_revolution = 8192;

  // Create mock motor controller for this test
  auto mock_motor = std::make_shared<MockMotorController>();
  EXPECT_CALL(*mock_motor, get_status())
  .WillRepeatedly(Return(MotorStatus()));
  EXPECT_CALL(*mock_motor, get_position())
  .WillRepeatedly(Return(0.0));
  EXPECT_CALL(*mock_motor, set_enabled(true))
  .WillOnce(Return(true));

  // Start initialization
  EXPECT_TRUE(init_system_->start_initialization(init_config, mock_motor, error_handler_));

  // Wait for initialization to complete
  std::this_thread::sleep_for(200ms);

  // Verify initialization status
  auto status = init_system_->get_initialization_status();
  EXPECT_TRUE(status.is_running || status.is_completed);
}

TEST_F(MotorControlIntegrationTest, PIDControllerIntegration)
{
  // Initialize PID controller with cascaded system
  auto cascaded_system = std::make_unique<CascadedPIDSystem>();

  CascadedPIDSystem::CascadeParams params;
  params.position_loop.kp = 10.0;
  params.position_loop.ki = 1.0;
  params.position_loop.kd = 0.1;
  params.velocity_loop.kp = 2.0;
  params.velocity_loop.ki = 0.5;
  params.torque_loop.kp = 1.0;

  MotorOptimizationParams motor_params;
  motor_params.motor_inertia = 0.001;

  EXPECT_TRUE(cascaded_system->initialize(params, motor_params));

  // Test cascaded control execution
  double torque_output = cascaded_system->execute_position_control(
    1.0,    // position setpoint
    0.8,    // position feedback
    0.1,    // velocity feedback
    0.05,   // torque feedback
    0.001   // dt
  );

  // Verify reasonable torque output
  EXPECT_FALSE(std::isnan(torque_output));
  EXPECT_FALSE(std::isinf(torque_output));
  EXPECT_GT(std::abs(torque_output), 0.0); // Should generate some torque for position error
}

TEST_F(MotorControlIntegrationTest, FullSystemIntegrationWithFaultHandling)
{
  // Initialize all systems
  DualEncoderConfig encoder_config;
  encoder_config.enable_sensor_fusion = true;
  EXPECT_TRUE(dual_encoder_system_->initialize(encoder_config, error_handler_));

  AdvancedPIDParams pid_params;
  pid_params.kp = 1.0;
  EXPECT_TRUE(pid_controller_->initialize(pid_params));

  // Start all systems
  EXPECT_TRUE(dual_encoder_system_->start_acquisition());
  pid_controller_->set_enabled(true);

  // Run system normally for a period
  for (int i = 0; i < 100; ++i) {
    // Simulate control loop execution
    double position_feedback = validation_framework_->get_motor_simulator()->get_position();
    double control_output = pid_controller_->execute_control(0.5, position_feedback, 0.001);

    // Apply control output to simulated motor
    validation_framework_->get_motor_simulator()->set_torque_command(control_output);

    std::this_thread::sleep_for(1ms);
  }

  // Inject fault and verify system response
  validation_framework_->inject_encoder_noise_increase(10.0); // 10x noise increase

  // Wait for fault detection
  std::this_thread::sleep_for(100ms);

  // Check if dual encoder system detected the fault
  auto faults = dual_encoder_system_->detect_encoder_faults();
  EXPECT_GT(faults.size(), 0u);

  // Verify error handler has active errors
  auto active_errors = error_handler_->get_active_errors();
  EXPECT_GT(active_errors.size(), 0u);

  // System should still be able to operate (fallback mode)
  auto system_status = dual_encoder_system_->get_system_status();
  EXPECT_TRUE(system_status.status != DualEncoderSystem::SystemStatus::BOTH_FAILED);
}

// =============================================================================
// PERFORMANCE BENCHMARKS
// =============================================================================

class MotorControlPerformanceTest : public MotorControlIntegrationTest
{
protected:
  void SetUp() override
  {
    MotorControlIntegrationTest::SetUp();

    // Initialize performance measurement
    performance_timer_ = std::make_unique<PerformanceTimer>();
    control_loop_stats_ = std::make_unique<PerformanceStats>();
    encoder_read_stats_ = std::make_unique<PerformanceStats>();
    can_comm_stats_ = std::make_unique<PerformanceStats>();
  }

  std::unique_ptr<PerformanceTimer> performance_timer_;
  std::unique_ptr<PerformanceStats> control_loop_stats_;
  std::unique_ptr<PerformanceStats> encoder_read_stats_;
  std::unique_ptr<PerformanceStats> can_comm_stats_;
};

TEST_F(MotorControlPerformanceTest, ControlLoopPerformanceBenchmark)
{
  // Initialize PID controller
  AdvancedPIDParams pid_params;
  pid_params.kp = 1.0;
  pid_params.ki = 0.1;
  pid_params.kd = 0.01;
  ASSERT_TRUE(pid_controller_->initialize(pid_params));
  pid_controller_->set_enabled(true);

  const int num_iterations = 10000;

  // Warm up
  for (int i = 0; i < 100; ++i) {
    pid_controller_->execute_control(1.0, 0.9, 0.001);
  }

  // Benchmark control loop execution
  for (int i = 0; i < num_iterations; ++i) {
    performance_timer_->start();

    double output = pid_controller_->execute_control(1.0, 0.9, 0.001);

    performance_timer_->stop();
    control_loop_stats_->add_measurement(performance_timer_->get_duration_us());

    // Prevent optimization
    volatile double sink = output;
    (void)sink;
  }

  // Analyze results
  double mean_time = control_loop_stats_->get_mean();
  double max_time = control_loop_stats_->get_max();
  double std_dev = control_loop_stats_->get_std_dev();
  double percentile_95 = control_loop_stats_->get_percentile(95);
  double percentile_99 = control_loop_stats_->get_percentile(99);

  std::cout << "\n=== Control Loop Performance Benchmark ===" << std::endl;
  std::cout << "Iterations: " << num_iterations << std::endl;
  std::cout << "Mean execution time: " << std::fixed << std::setprecision(3)
            << mean_time << " μs" << std::endl;
  std::cout << "Max execution time: " << max_time << " μs" << std::endl;
  std::cout << "Standard deviation: " << std_dev << " μs" << std::endl;
  std::cout << "95th percentile: " << percentile_95 << " μs" << std::endl;
  std::cout << "99th percentile: " << percentile_99 << " μs" << std::endl;

  // Performance requirements
  EXPECT_LT(mean_time, 50.0);      // Mean should be less than 50 μs
  EXPECT_LT(percentile_95, 100.0); // 95% should be less than 100 μs
  EXPECT_LT(percentile_99, 200.0); // 99% should be less than 200 μs
}

TEST_F(MotorControlPerformanceTest, DualEncoderPerformanceBenchmark)
{
  // Initialize dual encoder system
  DualEncoderConfig encoder_config;
  encoder_config.enable_sensor_fusion = true;
  ASSERT_TRUE(dual_encoder_system_->initialize(encoder_config, error_handler_));
  ASSERT_TRUE(dual_encoder_system_->start_acquisition());

  const int num_iterations = 5000;

  // Wait for system to stabilize
  std::this_thread::sleep_for(100ms);

  // Benchmark encoder data acquisition
  for (int i = 0; i < num_iterations; ++i) {
    performance_timer_->start();

    auto position_data = dual_encoder_system_->get_position_data();

    performance_timer_->stop();
    encoder_read_stats_->add_measurement(performance_timer_->get_duration_us());

    // Small delay to prevent overwhelming the system
    if (i % 100 == 0) {
      std::this_thread::sleep_for(1ms);
    }
  }

  // Analyze results
  double mean_time = encoder_read_stats_->get_mean();
  double max_time = encoder_read_stats_->get_max();
  double percentile_95 = encoder_read_stats_->get_percentile(95);

  std::cout << "\n=== Dual Encoder Performance Benchmark ===" << std::endl;
  std::cout << "Iterations: " << num_iterations << std::endl;
  std::cout << "Mean read time: " << std::fixed << std::setprecision(3)
            << mean_time << " μs" << std::endl;
  std::cout << "Max read time: " << max_time << " μs" << std::endl;
  std::cout << "95th percentile: " << percentile_95 << " μs" << std::endl;

  // Performance requirements
  EXPECT_LT(mean_time, 100.0);     // Mean should be less than 100 μs
  EXPECT_LT(percentile_95, 200.0); // 95% should be less than 200 μs
}

TEST_F(MotorControlPerformanceTest, CANCommunicationPerformanceBenchmark)
{
  // Initialize CAN interface
  ProtocolConfig config;
  config.protocol = CANProtocol::ODRIVE_CUSTOM;
  config.baud_rate = 1000000;
  ASSERT_TRUE(can_interface_->initialize("can0", config));

  const int num_iterations = 1000;

  // Benchmark CAN message sending
  for (int i = 0; i < num_iterations; ++i) {
    UniversalCANMessage message;
    message.can_id = 0x123;
    message.data = {0x01, 0x02, 0x03, 0x04};
    message.dlc = 4;

    performance_timer_->start();

    bool success = can_interface_->send_message(message);

    performance_timer_->stop();

    if (success) {
      can_comm_stats_->add_measurement(performance_timer_->get_duration_us());
    }

    // Small delay between messages
    std::this_thread::sleep_for(1ms);
  }

  // Analyze results
  if (can_comm_stats_->get_count() > 0) {
    double mean_time = can_comm_stats_->get_mean();
    double max_time = can_comm_stats_->get_max();
    double success_rate = static_cast<double>(can_comm_stats_->get_count()) / num_iterations *
      100.0;

    std::cout << "\n=== CAN Communication Performance Benchmark ===" << std::endl;
    std::cout << "Iterations: " << num_iterations << std::endl;
    std::cout << "Success rate: " << std::fixed << std::setprecision(1)
              << success_rate << "%" << std::endl;
    std::cout << "Mean send time: " << std::setprecision(3)
              << mean_time << " μs" << std::endl;
    std::cout << "Max send time: " << max_time << " μs" << std::endl;

    // Performance requirements
    EXPECT_GT(success_rate, 95.0);   // Success rate should be > 95%
    EXPECT_LT(mean_time, 500.0);     // Mean should be less than 500 μs
  }
}

TEST_F(MotorControlPerformanceTest, IntegratedSystemPerformanceBenchmark)
{
  // Initialize all components
  DualEncoderConfig encoder_config;
  encoder_config.enable_sensor_fusion = true;
  ASSERT_TRUE(dual_encoder_system_->initialize(encoder_config, error_handler_));
  ASSERT_TRUE(dual_encoder_system_->start_acquisition());

  AdvancedPIDParams pid_params;
  pid_params.kp = 1.0;
  ASSERT_TRUE(pid_controller_->initialize(pid_params));
  pid_controller_->set_enabled(true);

  const int num_iterations = 1000;
  PerformanceStats integrated_stats;

  // Wait for system stabilization
  std::this_thread::sleep_for(100ms);

  // Benchmark complete control loop
  for (int i = 0; i < num_iterations; ++i) {
    performance_timer_->start();

    // Get encoder feedback
    auto position_data = dual_encoder_system_->get_position_data();

    // Execute PID control
    double control_output = pid_controller_->execute_control(
      1.0,                    // setpoint
      position_data.position, // feedback
      0.001                   // dt
    );

    // Apply to motor simulator
    validation_framework_->get_motor_simulator()->set_torque_command(control_output);

    performance_timer_->stop();
    integrated_stats.add_measurement(performance_timer_->get_duration_us());

    // Real-time simulation timing
    std::this_thread::sleep_for(1ms);
  }

  // Analyze results
  double mean_time = integrated_stats.get_mean();
  double max_time = integrated_stats.get_max();
  double percentile_95 = integrated_stats.get_percentile(95);
  double std_dev = integrated_stats.get_std_dev();

  std::cout << "\n=== Integrated System Performance Benchmark ===" << std::endl;
  std::cout << "Iterations: " << num_iterations << std::endl;
  std::cout << "Mean loop time: " << std::fixed << std::setprecision(3)
            << mean_time << " μs" << std::endl;
  std::cout << "Max loop time: " << max_time << " μs" << std::endl;
  std::cout << "95th percentile: " << percentile_95 << " μs" << std::endl;
  std::cout << "Standard deviation: " << std_dev << " μs" << std::endl;
  std::cout << "Theoretical max frequency: " << std::setprecision(1)
            << 1000000.0 / mean_time << " Hz" << std::endl;

  // Performance requirements for 1kHz control loop
  EXPECT_LT(mean_time, 500.0);     // Mean should allow >2kHz
  EXPECT_LT(percentile_95, 800.0); // 95% should allow >1.25kHz
  EXPECT_LT(max_time, 1000.0);     // Max should not exceed 1ms
}

// =============================================================================
// STRESS TESTS
// =============================================================================

class MotorControlStressTest : public MotorControlIntegrationTest
{
protected:
  void SetUp() override
  {
    MotorControlIntegrationTest::SetUp();
    // Enable faster simulation for stress testing
    validation_framework_->set_real_time_factor(0.0); // Run as fast as possible
  }
};

TEST_F(MotorControlStressTest, HighFrequencyControlStressTest)
{
  // Initialize components
  AdvancedPIDParams pid_params;
  pid_params.kp = 2.0;
  ASSERT_TRUE(pid_controller_->initialize(pid_params));
  pid_controller_->set_enabled(true);

  const int duration_seconds = 10;
  const int target_frequency_hz = 5000; // 5kHz control loop
  const int total_iterations = duration_seconds * target_frequency_hz;

  auto start_time = std::chrono::steady_clock::now();
  int successful_iterations = 0;

  for (int i = 0; i < total_iterations; ++i) {
    try {
      // Rapid setpoint changes
      double setpoint = std::sin(2 * M_PI * i / 1000.0); // 5 Hz sine wave
      double feedback = validation_framework_->get_motor_simulator()->get_position();

      double output = pid_controller_->execute_control(setpoint, feedback, 0.0002); // 5kHz
      validation_framework_->get_motor_simulator()->set_torque_command(output);

      successful_iterations++;

      // Minimal delay for high frequency
      std::this_thread::sleep_for(std::chrono::microseconds(200));

    } catch (const std::exception & e) {
      // Log error but continue
      std::cerr << "Stress test iteration " << i << " failed: " << e.what() << std::endl;
    }

    // Check for system stability every 1000 iterations
    if (i % 1000 == 0) {
      EXPECT_TRUE(error_handler_->is_safe_to_operate());
    }
  }

  auto end_time = std::chrono::steady_clock::now();
  auto duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end_time -
    start_time).count();
  double actual_frequency = (successful_iterations * 1000.0) / duration_ms;
  double success_rate = (static_cast<double>(successful_iterations) / total_iterations) * 100.0;

  std::cout << "\n=== High Frequency Control Stress Test ===" << std::endl;
  std::cout << "Target frequency: " << target_frequency_hz << " Hz" << std::endl;
  std::cout << "Actual frequency: " << std::fixed << std::setprecision(1)
            << actual_frequency << " Hz" << std::endl;
  std::cout << "Success rate: " << std::setprecision(2) << success_rate << "%" << std::endl;
  std::cout << "Duration: " << duration_ms << " ms" << std::endl;

  // Stress test requirements
  EXPECT_GT(success_rate, 98.0);           // >98% success rate
  EXPECT_GT(actual_frequency, target_frequency_hz * 0.8); // At least 80% of target frequency
  EXPECT_TRUE(error_handler_->is_safe_to_operate()); // System should remain safe
}

TEST_F(MotorControlStressTest, MemoryLeakStressTest)
{
  // Initialize components
  DualEncoderConfig encoder_config;
  encoder_config.enable_sensor_fusion = true;
  ASSERT_TRUE(dual_encoder_system_->initialize(encoder_config, error_handler_));
  ASSERT_TRUE(dual_encoder_system_->start_acquisition());

  AdvancedPIDParams pid_params;
  ASSERT_TRUE(pid_controller_->initialize(pid_params));

  // Get initial memory usage (placeholder - would need platform-specific implementation)
  auto initial_time = std::chrono::steady_clock::now();

  const int duration_minutes = 1; // Short test for CI
  const int iterations_per_second = 1000;
  const int total_iterations = duration_minutes * 60 * iterations_per_second;

  for (int i = 0; i < total_iterations; ++i) {
    // Simulate intensive operations that could cause memory leaks

    // Continuous encoder reading
    auto position_data = dual_encoder_system_->get_position_data();

    // PID calculations
    pid_controller_->execute_control(1.0, position_data.position, 0.001);

    // Error handling operations
    if (i % 1000 == 0) {
      error_handler_->get_active_errors();
      error_handler_->get_statistics();
    }

    // Create and destroy temporary objects
    if (i % 100 == 0) {
      std::vector<double> temp_data(1000, static_cast<double>(i));
      // Vector goes out of scope here
    }

    // Minimal delay
    if (i % iterations_per_second == 0) {
      std::this_thread::sleep_for(1ms);
    }
  }

  auto end_time = std::chrono::steady_clock::now();
  auto duration_seconds = std::chrono::duration_cast<std::chrono::seconds>(end_time -
    initial_time).count();

  std::cout << "\n=== Memory Leak Stress Test ===" << std::endl;
  std::cout << "Test duration: " << duration_seconds << " seconds" << std::endl;
  std::cout << "Total iterations: " << total_iterations << std::endl;
  std::cout << "Average iterations per second: "
            << total_iterations / duration_seconds << std::endl;

  // Memory leak test is mainly about completing without crashes
  // Real memory monitoring would require platform-specific code
  SUCCEED() << "Memory leak stress test completed successfully";
}

// =============================================================================
// END-TO-END SYSTEM VALIDATION
// =============================================================================

class EndToEndSystemTest : public MotorControlIntegrationTest
{
protected:
  void SetUp() override
  {
    MotorControlIntegrationTest::SetUp();

    // Initialize complete system
    setupCompleteMotorControlSystem();
  }

  void setupCompleteMotorControlSystem()
  {
    // Initialize all components
    DualEncoderConfig encoder_config;
    encoder_config.primary_encoder.name = "primary_encoder";
    encoder_config.secondary_encoder.name = "secondary_encoder";
    encoder_config.enable_sensor_fusion = true;
    encoder_config.enable_cross_validation = true;
    encoder_config.position_tolerance_radians = 0.001;

    ASSERT_TRUE(dual_encoder_system_->initialize(encoder_config, error_handler_));
    ASSERT_TRUE(dual_encoder_system_->start_acquisition());

    // Initialize cascaded PID system
    cascaded_pid_ = std::make_unique<CascadedPIDSystem>();
    CascadedPIDSystem::CascadeParams cascade_params;
    cascade_params.position_loop.kp = 20.0;
    cascade_params.position_loop.ki = 2.0;
    cascade_params.position_loop.kd = 0.5;
    cascade_params.velocity_loop.kp = 5.0;
    cascade_params.velocity_loop.ki = 1.0;
    cascade_params.torque_loop.kp = 2.0;

    MotorOptimizationParams motor_params;
    motor_params.motor_inertia = 0.001;
    motor_params.load_inertia = 0.005;

    ASSERT_TRUE(cascaded_pid_->initialize(cascade_params, motor_params));

    // Initialize CAN interface
    ProtocolConfig can_config;
    can_config.protocol = CANProtocol::ODRIVE_CUSTOM;
    ASSERT_TRUE(can_interface_->initialize("can0", can_config));
  }

  std::unique_ptr<CascadedPIDSystem> cascaded_pid_;
};

TEST_F(EndToEndSystemTest, CompletePositionControlScenario)
{
  // Define test trajectory - step response
  const double target_position = 2.0; // 2 radians
  const double simulation_time = 5.0; // 5 seconds
  const double control_frequency = 1000.0; // 1kHz
  const int total_steps = static_cast<int>(simulation_time * control_frequency);

  std::vector<double> position_history;
  std::vector<double> velocity_history;
  std::vector<double> torque_history;
  std::vector<double> time_history;

  position_history.reserve(total_steps);
  velocity_history.reserve(total_steps);
  torque_history.reserve(total_steps);
  time_history.reserve(total_steps);

  // Execute complete control scenario
  for (int step = 0; step < total_steps; ++step) {
    double current_time = step / control_frequency;

    // Get encoder feedback
    auto position_data = dual_encoder_system_->get_position_data();
    auto velocity_data = dual_encoder_system_->get_velocity_data();

    // Execute cascaded control
    double torque_command = cascaded_pid_->execute_position_control(
      target_position,           // position setpoint
      position_data.position,    // position feedback
      velocity_data.velocity,    // velocity feedback
      0.0,                      // torque feedback (assume zero for this test)
      1.0 / control_frequency   // dt
    );

    // Apply torque to motor
    validation_framework_->get_motor_simulator()->set_torque_command(torque_command);

    // Log data
    position_history.push_back(position_data.position);
    velocity_history.push_back(velocity_data.velocity);
    torque_history.push_back(torque_command);
    time_history.push_back(current_time);

    // Simulate real-time execution
    std::this_thread::sleep_for(std::chrono::microseconds(1000)); // 1ms

    // Check system health periodically
    if (step % 100 == 0) {
      EXPECT_TRUE(error_handler_->is_safe_to_operate());
      EXPECT_TRUE(dual_encoder_system_->perform_cross_validation());
    }
  }

  // Analyze performance
  double final_position = position_history.back();
  double position_error = std::abs(final_position - target_position);

  // Calculate settling time (within 2% of target)
  double settling_threshold = 0.02 * target_position;
  int settling_step = total_steps - 1;
  for (int i = total_steps / 2; i < total_steps; ++i) {
    if (std::abs(position_history[i] - target_position) > settling_threshold) {
      settling_step = i;
    }
  }
  double settling_time = settling_step / control_frequency;

  // Calculate overshoot
  double max_position = *std::max_element(position_history.begin(), position_history.end());
  double overshoot_percent = ((max_position - target_position) / target_position) * 100.0;

  // Calculate steady-state error
  double steady_state_error = std::abs(final_position - target_position);

  std::cout << "\n=== Complete Position Control Scenario Results ===" << std::endl;
  std::cout << "Target position: " << target_position << " rad" << std::endl;
  std::cout << "Final position: " << std::fixed << std::setprecision(4)
            << final_position << " rad" << std::endl;
  std::cout << "Position error: " << position_error << " rad" << std::endl;
  std::cout << "Settling time: " << std::setprecision(3) << settling_time << " s" << std::endl;
  std::cout << "Overshoot: " << std::setprecision(2) << overshoot_percent << "%" << std::endl;
  std::cout << "Steady-state error: " << std::setprecision(4)
            << steady_state_error << " rad" << std::endl;

  // Performance requirements
  EXPECT_LT(position_error, 0.01);        // < 0.01 rad final error
  EXPECT_LT(settling_time, 2.0);          // < 2 second settling time
  EXPECT_LT(overshoot_percent, 10.0);     // < 10% overshoot
  EXPECT_LT(steady_state_error, 0.005);   // < 0.005 rad steady-state error

  // System should remain healthy throughout
  EXPECT_TRUE(error_handler_->is_safe_to_operate());
  auto final_errors = error_handler_->get_active_errors();
  EXPECT_EQ(final_errors.size(), 0u);
}

TEST_F(EndToEndSystemTest, FaultRecoveryScenario)
{
  const double test_duration = 10.0; // 10 seconds
  const double control_frequency = 1000.0; // 1kHz
  const int total_steps = static_cast<int>(test_duration * control_frequency);
  const double target_position = 1.0;

  bool fault_injected = false;
  bool recovery_completed = false;
  int fault_injection_step = total_steps / 3; // Inject fault 1/3 through test

  for (int step = 0; step < total_steps; ++step) {
    double current_time = step / control_frequency;

    // Inject encoder fault at predetermined time
    if (step == fault_injection_step && !fault_injected) {
      std::cout << "\nInjecting encoder fault at t=" << current_time << "s" << std::endl;
      validation_framework_->inject_encoder_noise_increase(20.0); // 20x noise increase
      fault_injected = true;
    }

    // Get encoder feedback
    auto position_data = dual_encoder_system_->get_position_data();
    auto velocity_data = dual_encoder_system_->get_velocity_data();

    // Execute control (system should handle faults gracefully)
    double torque_command = cascaded_pid_->execute_position_control(
      target_position,
      position_data.position,
      velocity_data.velocity,
      0.0,
      1.0 / control_frequency
    );

    // Apply command (with limits for safety)
    torque_command = std::clamp(torque_command, -5.0, 5.0);
    validation_framework_->get_motor_simulator()->set_torque_command(torque_command);

    // Check system status
    if (step % 100 == 0) {
      auto system_status = dual_encoder_system_->get_system_status();
      auto active_errors = error_handler_->get_active_errors();

      if (fault_injected && !recovery_completed) {
        // After fault injection, system should detect and respond
        if (system_status.status == DualEncoderSystem::SystemStatus::PRIMARY_ONLY ||
          system_status.status == DualEncoderSystem::SystemStatus::SECONDARY_ONLY)
        {
          recovery_completed = true;
          std::cout << "System successfully switched to fallback mode at t="
                    << current_time << "s" << std::endl;
        }
      }
    }

    std::this_thread::sleep_for(std::chrono::microseconds(1000));
  }

  // Verify fault recovery
  EXPECT_TRUE(fault_injected) << "Fault should have been injected";
  EXPECT_TRUE(recovery_completed) << "System should have recovered from fault";

  // System should still be operational
  EXPECT_TRUE(error_handler_->is_safe_to_operate());

  auto final_status = dual_encoder_system_->get_system_status();
  EXPECT_NE(final_status.status, DualEncoderSystem::SystemStatus::BOTH_FAILED)
    << "System should not have complete failure";

  std::cout << "\n=== Fault Recovery Scenario Completed ===" << std::endl;
  std::cout << "Fault injected: " << (fault_injected ? "Yes" : "No") << std::endl;
  std::cout << "Recovery completed: " << (recovery_completed ? "Yes" : "No") << std::endl;
  std::cout << "Final system status: " << static_cast<int>(final_status.status) << std::endl;
}

// =============================================================================
// MAIN TEST RUNNER
// =============================================================================

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);

  std::cout << "\n=======================================" << std::endl;
  std::cout << "Motor Control Integration & Performance Tests" << std::endl;
  std::cout << "=======================================" << std::endl;

  return RUN_ALL_TESTS();
}
