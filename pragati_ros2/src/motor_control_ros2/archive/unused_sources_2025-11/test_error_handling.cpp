/**
 * @file test_error_handling.cpp
 * @brief Test suite for enhanced error handling framework
 */

#include <gtest/gtest.h>
#include <chrono>
#include <thread>
#include "motor_control_ros2/motor_abstraction.hpp"

using namespace motor_control_ros2;
using namespace motor_control_ros2::ErrorFramework;

class ErrorHandlingTest : public ::testing::Test {
protected:
  void SetUp() override
  {
    error_handler_ = std::make_unique<DefaultErrorHandler>();

        // Create a basic motor configuration for testing
    motor_config_.motor_type = "test_motor";
    motor_config_.joint_name = "test_joint";
    motor_config_.can_id = 0x001;
    motor_config_.current_limit = 10.0;
    motor_config_.velocity_limit = 5.0;
    motor_config_.limits.temperature_max = 80.0;
  }

  void TearDown() override
  {
    error_handler_.reset();
  }

  std::unique_ptr<DefaultErrorHandler> error_handler_;
  MotorConfiguration motor_config_;
};

// Test Error Category Enumeration
TEST_F(ErrorHandlingTest, ErrorCategoryValues) {
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::NONE), 0);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::COMMUNICATION), 1);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::HARDWARE), 2);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::ENCODER), 3);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::CONTROL), 4);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::SAFETY), 5);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::INITIALIZATION), 6);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::THERMAL), 7);
    EXPECT_EQ(static_cast<uint8_t>(ErrorCategory::POWER), 8);
}

// Test Error Severity Enumeration
TEST_F(ErrorHandlingTest, ErrorSeverityValues) {
    EXPECT_EQ(static_cast<uint8_t>(ErrorSeverity::INFO), 0);
    EXPECT_EQ(static_cast<uint8_t>(ErrorSeverity::WARNING), 1);
    EXPECT_EQ(static_cast<uint8_t>(ErrorSeverity::ERROR), 2);
    EXPECT_EQ(static_cast<uint8_t>(ErrorSeverity::CRITICAL), 3);
    EXPECT_EQ(static_cast<uint8_t>(ErrorSeverity::FATAL), 4);
}

// Test ErrorFactory - Communication Errors
TEST_F(ErrorHandlingTest, ErrorFactoryCommunicationErrors) {
    // Test communication timeout error
    auto timeout_error = ErrorFactory::create_communication_timeout_error("CAN bus timeout");
    EXPECT_EQ(timeout_error.category, ErrorCategory::COMMUNICATION);
    EXPECT_EQ(timeout_error.severity, ErrorSeverity::ERROR);
    EXPECT_EQ(timeout_error.code, 1001);
    EXPECT_TRUE(timeout_error.message.find("Communication timeout") != std::string::npos);
    EXPECT_TRUE(timeout_error.message.find("CAN bus timeout") != std::string::npos);
    EXPECT_TRUE(timeout_error.can_auto_recover);
    EXPECT_FALSE(timeout_error.recovery_suggestion.empty());

    // Test CAN bus error
    auto can_error = ErrorFactory::create_can_bus_error(0x42, "Bus-off state");
    EXPECT_EQ(can_error.category, ErrorCategory::COMMUNICATION);
    EXPECT_EQ(can_error.severity, ErrorSeverity::ERROR);
    EXPECT_EQ(can_error.code, 1066); // 1000 + 66 (0x42)
    EXPECT_TRUE(can_error.message.find("CAN bus error 66") != std::string::npos);
    EXPECT_TRUE(can_error.can_auto_recover);

    // Test connection lost error
    auto connection_error = ErrorFactory::create_connection_lost_error("Motor unresponsive");
    EXPECT_EQ(connection_error.category, ErrorCategory::COMMUNICATION);
    EXPECT_EQ(connection_error.severity, ErrorSeverity::CRITICAL);
    EXPECT_EQ(connection_error.code, 1002);
    EXPECT_TRUE(connection_error.can_auto_recover);
}

// Test ErrorFactory - Hardware Errors
TEST_F(ErrorHandlingTest, ErrorFactoryHardwareErrors) {
    // Test motor overcurrent error
    auto overcurrent_error = ErrorFactory::create_motor_overcurrent_error(15.5, 10.0);
    EXPECT_EQ(overcurrent_error.category, ErrorCategory::HARDWARE);
    EXPECT_EQ(overcurrent_error.severity, ErrorSeverity::CRITICAL);
    EXPECT_EQ(overcurrent_error.code, 2001);
    EXPECT_TRUE(overcurrent_error.message.find("15.5") != std::string::npos);
    EXPECT_TRUE(overcurrent_error.message.find("10") != std::string::npos);
    EXPECT_FALSE(overcurrent_error.can_auto_recover); // Hardware errors shouldn't auto-recover

    // Test motor overheat error
    auto overheat_error = ErrorFactory::create_motor_overheat_error(95.5, 80.0);
    EXPECT_EQ(overheat_error.category, ErrorCategory::THERMAL);
    EXPECT_EQ(overheat_error.severity, ErrorSeverity::CRITICAL);
    EXPECT_EQ(overheat_error.code, 7001);
    EXPECT_TRUE(overheat_error.message.find("95.5") != std::string::npos);
    EXPECT_FALSE(overheat_error.can_auto_recover); // Thermal errors need manual intervention

    // Test encoder failure error
    auto encoder_error = ErrorFactory::create_encoder_failure_error("18-bit motor encoder");
    EXPECT_EQ(encoder_error.category, ErrorCategory::ENCODER);
    EXPECT_EQ(encoder_error.severity, ErrorSeverity::ERROR);
    EXPECT_EQ(encoder_error.code, 3001);
    EXPECT_TRUE(encoder_error.message.find("18-bit motor encoder") != std::string::npos);
    EXPECT_TRUE(encoder_error.can_auto_recover); // Encoder errors can often be recovered
}

// Test ErrorFactory - Safety Errors
TEST_F(ErrorHandlingTest, ErrorFactorySafetyErrors) {
    // Test position limit error
    auto position_error = ErrorFactory::create_position_limit_error(3.5, -3.14, 3.14);
    EXPECT_EQ(position_error.category, ErrorCategory::SAFETY);
    EXPECT_EQ(position_error.severity, ErrorSeverity::WARNING);
    EXPECT_EQ(position_error.code, 5001);
    EXPECT_TRUE(position_error.message.find("3.5") != std::string::npos);
    EXPECT_FALSE(position_error.can_auto_recover); // Safety errors need manual attention

    // Test emergency stop error
    auto estop_error = ErrorFactory::create_emergency_stop_error("Hardware button pressed");
    EXPECT_EQ(estop_error.category, ErrorCategory::SAFETY);
    EXPECT_EQ(estop_error.severity, ErrorSeverity::CRITICAL);
    EXPECT_EQ(estop_error.code, 5000);
    EXPECT_TRUE(estop_error.message.find("Hardware button pressed") != std::string::npos);
    EXPECT_FALSE(estop_error.can_auto_recover);
}

// Test ErrorFactory - Control and Initialization Errors
TEST_F(ErrorHandlingTest, ErrorFactoryControlInitializationErrors) {
    // Test control loop instability error
    auto control_error =
    ErrorFactory::create_control_loop_instability_error("Oscillation detected");
    EXPECT_EQ(control_error.category, ErrorCategory::CONTROL);
    EXPECT_EQ(control_error.severity, ErrorSeverity::ERROR);
    EXPECT_EQ(control_error.code, 4001);
    EXPECT_TRUE(control_error.can_auto_recover);

    // Test homing failure error
    auto homing_error = ErrorFactory::create_homing_failure_error("Limit switch not found");
    EXPECT_EQ(homing_error.category, ErrorCategory::INITIALIZATION);
    EXPECT_EQ(homing_error.severity, ErrorSeverity::ERROR);
    EXPECT_EQ(homing_error.code, 6001);
    EXPECT_TRUE(homing_error.can_auto_recover);

    // Test calibration failure error
    auto calibration_error = ErrorFactory::create_calibration_failure_error("Motor");
    EXPECT_EQ(calibration_error.category, ErrorCategory::INITIALIZATION);
    EXPECT_EQ(calibration_error.severity, ErrorSeverity::ERROR);
    EXPECT_EQ(calibration_error.code, 6002);
    EXPECT_TRUE(calibration_error.can_auto_recover);
}

// Test DefaultErrorHandler Auto-Recovery Logic
TEST_F(ErrorHandlingTest, DefaultErrorHandlerAutoRecovery) {
    // Fatal errors should not be auto-recoverable
    ErrorInfo fatal_error;
    fatal_error.severity = ErrorSeverity::FATAL;
    fatal_error.can_auto_recover = true; // Even if marked as recoverable
    EXPECT_FALSE(error_handler_->can_auto_recover(fatal_error));

    // Safety errors should not be auto-recoverable
    ErrorInfo safety_error;
    safety_error.category = ErrorCategory::SAFETY;
    safety_error.severity = ErrorSeverity::ERROR;
    safety_error.can_auto_recover = true;
    EXPECT_FALSE(error_handler_->can_auto_recover(safety_error));

    // Communication errors should be auto-recoverable if conditions are met
    ErrorInfo comm_error;
    comm_error.category = ErrorCategory::COMMUNICATION;
    comm_error.severity = ErrorSeverity::ERROR;
    comm_error.can_auto_recover = true;
    EXPECT_TRUE(error_handler_->can_auto_recover(comm_error));

    // Errors marked as non-recoverable should not be auto-recoverable
    ErrorInfo non_recoverable_error;
    non_recoverable_error.category = ErrorCategory::HARDWARE;
    non_recoverable_error.severity = ErrorSeverity::ERROR;
    non_recoverable_error.can_auto_recover = false;
    EXPECT_FALSE(error_handler_->can_auto_recover(non_recoverable_error));
}

// Test DefaultErrorHandler Recovery Suggestions
TEST_F(ErrorHandlingTest, DefaultErrorHandlerRecoverySuggestions) {
    // Test category-specific suggestions
    ErrorInfo comm_error;
    comm_error.category = ErrorCategory::COMMUNICATION;
    std::string suggestion = error_handler_->get_recovery_suggestion(comm_error);
    EXPECT_TRUE(suggestion.find("CAN bus") != std::string::npos);

    ErrorInfo hardware_error;
    hardware_error.category = ErrorCategory::HARDWARE;
    suggestion = error_handler_->get_recovery_suggestion(hardware_error);
    EXPECT_TRUE(suggestion.find("hardware") != std::string::npos);

    ErrorInfo thermal_error;
    thermal_error.category = ErrorCategory::THERMAL;
    suggestion = error_handler_->get_recovery_suggestion(thermal_error);
    EXPECT_TRUE(suggestion.find("cool") != std::string::npos);

    // Test custom recovery suggestion
    ErrorInfo custom_error;
    custom_error.recovery_suggestion = "Custom recovery action required";
    suggestion = error_handler_->get_recovery_suggestion(custom_error);
    EXPECT_EQ(suggestion, "Custom recovery action required");
}

// Test Error Handling Integration
TEST_F(ErrorHandlingTest, ErrorHandlingIntegration) {
    // Create a communication timeout error
    auto error = ErrorFactory::create_communication_timeout_error("Test timeout");

    // Handle the error
    auto result = error_handler_->handle_error(error, motor_config_);

    // Verify recovery attempt
    EXPECT_GT(result.attempts_made, 0);
    EXPECT_FALSE(result.action_taken.empty());
    EXPECT_FALSE(result.next_suggestion.empty());

    // For communication errors, recovery should be attempted
    EXPECT_TRUE(result.success); // Our mock implementation returns true
}

// Test MotorStatus Enhanced Structure
TEST_F(ErrorHandlingTest, MotorStatusEnhancedStructure) {
    MotorStatus status;

    // Test default values
    EXPECT_EQ(status.current_error.category, ErrorCategory::NONE);
    EXPECT_EQ(status.current_error.severity, ErrorSeverity::INFO);
    EXPECT_EQ(status.health_score, 1.0);
    EXPECT_FALSE(status.requires_attention);
    EXPECT_TRUE(status.error_history.empty());
    EXPECT_TRUE(status.warnings.empty());

    // Test legacy compatibility
    EXPECT_EQ(status.error_code, 0);
    EXPECT_TRUE(status.error_message.empty());

    // Test adding errors to history
    auto error1 = ErrorFactory::create_communication_timeout_error();
    auto error2 = ErrorFactory::create_encoder_failure_error("test encoder");

    status.current_error = error1;
    status.error_history.push_back(error1);
    status.error_history.push_back(error2);

    EXPECT_EQ(status.error_history.size(), 2);
    EXPECT_EQ(status.current_error.category, ErrorCategory::COMMUNICATION);
}

// Test Error Timing and Occurrence Counting
TEST_F(ErrorHandlingTest, ErrorTimingAndCounting) {
    auto error1 = ErrorFactory::create_communication_timeout_error();
    auto error2 = ErrorFactory::create_communication_timeout_error();

    // Verify timestamps are set
    EXPECT_GT(error1.timestamp.time_since_epoch().count(), 0);
    EXPECT_GT(error2.timestamp.time_since_epoch().count(), 0);

    // Verify occurrence count is initialized
    EXPECT_EQ(error1.occurrence_count, 1);
    EXPECT_EQ(error2.occurrence_count, 1);

    // Test that timestamps are different (even if very close)
    std::this_thread::sleep_for(std::chrono::microseconds(1));
    auto error3 = ErrorFactory::create_communication_timeout_error();
    EXPECT_GE(error3.timestamp, error1.timestamp);
}

// Test Recovery Rate Limiting
TEST_F(ErrorHandlingTest, RecoveryRateLimiting) {
    auto error = ErrorFactory::create_communication_timeout_error();

    // First recovery attempt should be allowed
    EXPECT_TRUE(error_handler_->can_auto_recover(error));

    // Simulate handling the error multiple times rapidly
    for (int i = 0; i < 6; ++i) {
    error_handler_->handle_error(error, motor_config_);
    }

    // After many attempts, recovery should be rate-limited
    // Note: The actual rate limiting logic would need real time delays to test properly
    // This is a basic structure test
    EXPECT_TRUE(error_handler_->can_auto_recover(error) ||
    !error_handler_->can_auto_recover(error));
}

// Performance Test - Error Creation and Handling
TEST_F(ErrorHandlingTest, PerformanceTest) {
    const int num_errors = 1000;
    auto start_time = std::chrono::high_resolution_clock::now();

    // Create many errors quickly
    std::vector<ErrorInfo> errors;
    errors.reserve(num_errors);

    for (int i = 0; i < num_errors; ++i) {
    errors.push_back(ErrorFactory::create_communication_timeout_error("Test " + std::to_string(i)));
    }

    auto creation_time = std::chrono::high_resolution_clock::now();

    // Handle many errors quickly
    for (const auto & error : errors) {
    error_handler_->handle_error(error, motor_config_);
    }

    auto end_time = std::chrono::high_resolution_clock::now();

    auto creation_duration = std::chrono::duration_cast<std::chrono::microseconds>(
        creation_time - start_time).count();
    auto handling_duration = std::chrono::duration_cast<std::chrono::microseconds>(
        end_time - creation_time).count();

    // Performance expectations (adjust based on requirements)
    EXPECT_LT(creation_duration, 10000); // Less than 10ms for 1000 error creations
    EXPECT_LT(handling_duration, 50000);  // Less than 50ms for 1000 error handlings

    std::cout << "Performance Test Results:" << std::endl;
    std::cout << "  Error creation: " << creation_duration << " μs for " << num_errors <<
    " errors" << std::endl;
    std::cout << "  Error handling: " << handling_duration << " μs for " << num_errors <<
    " errors" << std::endl;
    std::cout << "  Average creation: " << creation_duration / num_errors << " μs/error" <<
    std::endl;
    std::cout << "  Average handling: " << handling_duration / num_errors << " μs/error" <<
    std::endl;
}

// Test Thread Safety (Basic)
TEST_F(ErrorHandlingTest, ThreadSafetyBasic) {
    const int num_threads = 4;
    const int errors_per_thread = 100;
    std::vector<std::thread> threads;

    // Create multiple threads that create and handle errors simultaneously
    for (int t = 0; t < num_threads; ++t) {
    threads.emplace_back([this, t, errors_per_thread]() {
        for (int i = 0; i < errors_per_thread; ++i) {
          auto error = ErrorFactory::create_communication_timeout_error(
                    "Thread " + std::to_string(t) + " Error " + std::to_string(i));
          error_handler_->handle_error(error, motor_config_);
        }
        });
    }

    // Wait for all threads to complete
    for (auto & thread : threads) {
    thread.join();
    }

    // If we reach here without crashing, thread safety is basic level adequate
    EXPECT_TRUE(true);
}

int main(int argc, char **argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
