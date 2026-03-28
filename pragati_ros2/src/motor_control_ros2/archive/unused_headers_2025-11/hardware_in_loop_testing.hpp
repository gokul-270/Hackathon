/*
 * Hardware-in-Loop (HIL) Testing System
 *
 * This system provides comprehensive testing capabilities that can validate
 * motor control components with actual hardware when available.
 *
 * Features:
 * 1. Automatic hardware detection and configuration
 * 2. ODrive controller testing with real CAN communication
 * 3. Physical encoder validation and calibration
 * 4. Motor parameter identification
 * 5. Safety interlocks and emergency procedures
 * 6. Hardware fault injection and recovery testing
 * 7. Performance characterization with real hardware
 * 8. Data logging and analysis
 */

#pragma once

#include <memory>
#include <vector>
#include <map>
#include <string>
#include <functional>
#include <chrono>
#include <thread>
#include <mutex>
#include <atomic>
#include <fstream>

// Motor control system headers
#include "enhanced_can_interface.hpp"
#include "comprehensive_error_handler.hpp"
#include "advanced_initialization_system.hpp"
#include "dual_encoder_system.hpp"
#include "advanced_pid_system.hpp"
#include "motor_control_validation_framework.hpp"

namespace motor_control_ros2
{
namespace hardware_testing
{

// =============================================================================
// HARDWARE CONFIGURATION AND DETECTION
// =============================================================================

/**
 * @brief Hardware component identification
 */
enum class HardwareType
{
  ODRIVE_V3_6,
  ODRIVE_V4_1,
  ODRIVE_S1,
  GENERIC_CAN_MOTOR,
  INCREMENTAL_ENCODER,
  ABSOLUTE_ENCODER,
  HALL_SENSOR,
  CURRENT_SENSOR,
  TEMPERATURE_SENSOR,
  EMERGENCY_STOP,
  POWER_SUPPLY,
  UNKNOWN
};

/**
 * @brief Hardware component description
 */
struct HardwareComponent
{
  std::string name;
  HardwareType type;
  std::string interface; // e.g., "can0", "/dev/ttyUSB0", "spi0.0"
  std::map<std::string, std::string> properties;
  bool is_connected{false};
  bool is_operational{false};
  std::string firmware_version;
  std::string serial_number;
};

/**
 * @brief Motor hardware specifications
 */
struct MotorHardwareSpec
{
  std::string model;
  double rated_voltage{24.0};        ///< Rated voltage [V]
  double rated_current{10.0};        ///< Rated current [A]
  double rated_power{240.0};         ///< Rated power [W]
  double rated_torque{1.0};          ///< Rated torque [N⋅m]
  double rated_speed{3000.0};        ///< Rated speed [RPM]
  double pole_pairs{7};              ///< Number of pole pairs
  double resistance{1.0};            ///< Phase resistance [Ω]
  double inductance{0.001};          ///< Phase inductance [H]
  double inertia{0.001};            ///< Rotor inertia [kg⋅m²]
  double kt{0.1};                   ///< Torque constant [N⋅m/A]
  double ke{0.1};                   ///< Back EMF constant [V⋅s/rad]
  std::string encoder_type{"incremental"};
  uint32_t encoder_cpr{8192};       ///< Counts per revolution
};

/**
 * @brief Hardware detection and management
 */
class HardwareManager
{
public:
  HardwareManager() = default;
  ~HardwareManager() = default;

  // Hardware discovery
  bool scan_for_hardware();
  std::vector<HardwareComponent> get_detected_hardware() const {return detected_hardware_;}
  bool is_hardware_present(HardwareType type) const;

  // Component access
  HardwareComponent * get_component(const std::string & name);
  std::vector<HardwareComponent *> get_components_by_type(HardwareType type);

  // Connection management
  bool connect_to_hardware(const std::string & component_name);
  bool disconnect_from_hardware(const std::string & component_name);
  void disconnect_all();

  // Health monitoring
  bool verify_hardware_health();
  std::map<std::string, std::string> get_hardware_status();

  // Safety interlocks
  bool enable_emergency_stop();
  bool disable_emergency_stop();
  bool is_emergency_stop_active() const {return emergency_stop_active_;}

  // Configuration
  bool load_hardware_config(const std::string & config_file);
  bool save_hardware_config(const std::string & config_file);

private:
  bool detect_odrive_controllers();
  bool detect_encoders();
  bool detect_sensors();
  bool detect_can_interfaces();
  bool probe_component(HardwareComponent & component);

  std::vector<HardwareComponent> detected_hardware_;
  std::atomic<bool> emergency_stop_active_{false};
  mutable std::mutex hardware_mutex_;
};

// =============================================================================
// ODRIVE HARDWARE TESTING
// =============================================================================

/**
 * @brief ODrive-specific test parameters
 */
struct ODriveTestParams
{
  uint8_t node_id{0};
  double max_velocity{10.0};         ///< Maximum velocity [rad/s]
  double max_acceleration{50.0};     ///< Maximum acceleration [rad/s²]
  double max_current{20.0};          ///< Maximum current [A]
  double calibration_current{10.0};  ///< Current for calibration [A]
  bool enable_anticogging{false};    ///< Enable anticogging calibration
  bool enable_index_search{true};    ///< Enable encoder index search
  double brake_resistor_ohms{2.0};   ///< Brake resistor value [Ω]
  double dc_bus_voltage{24.0};       ///< DC bus voltage [V]
};

/**
 * @brief ODrive hardware testing interface
 */
class ODriveHardwareTester
{
public:
  ODriveHardwareTester(
    std::shared_ptr<EnhancedCANController> can_interface,
    std::shared_ptr<ComprehensiveErrorHandler> error_handler);
  ~ODriveHardwareTester() = default;

  // ODrive discovery and connection
  bool discover_odrives();
  std::vector<uint8_t> get_detected_node_ids() const {return detected_nodes_;}
  bool connect_to_odrive(uint8_t node_id, const ODriveTestParams & params);
  bool disconnect_from_odrive(uint8_t node_id);

  // Calibration procedures
  bool run_motor_calibration(uint8_t node_id);
  bool run_encoder_calibration(uint8_t node_id);
  bool run_full_calibration_sequence(uint8_t node_id);

  // Basic functionality tests
  bool test_can_communication(uint8_t node_id);
  bool test_encoder_functionality(uint8_t node_id);
  bool test_motor_movement(uint8_t node_id, double test_position);
  bool test_current_control(uint8_t node_id, double test_current);
  bool test_velocity_control(uint8_t node_id, double test_velocity);
  bool test_position_control(uint8_t node_id, double test_position);

  // Advanced testing
  bool characterize_motor_parameters(uint8_t node_id, MotorHardwareSpec & spec);
  bool test_thermal_performance(uint8_t node_id, double duration_minutes);
  bool test_dynamic_response(uint8_t node_id);
  bool test_error_recovery(uint8_t node_id);

  // Safety testing
  bool test_emergency_stop(uint8_t node_id);
  bool test_overcurrent_protection(uint8_t node_id);
  bool test_overvoltage_protection(uint8_t node_id);
  bool test_thermal_protection(uint8_t node_id);

  // Data collection
  struct ODriveTestData
  {
    std::chrono::steady_clock::time_point timestamp;
    uint8_t node_id;
    double position;
    double velocity;
    double current_q;
    double current_d;
    double voltage_q;
    double voltage_d;
    double temperature_motor;
    double temperature_fet;
    double dc_voltage;
    double dc_current;
    uint32_t error_flags;
    uint32_t state;
  };

  std::vector<ODriveTestData> get_test_data() const {return test_data_;}
  void clear_test_data() {test_data_.clear();}
  bool save_test_data(const std::string & filename);

private:
  bool send_odrive_command(uint8_t node_id, uint16_t cmd, const std::vector<uint8_t> & data);
  bool read_odrive_parameter(uint8_t node_id, uint16_t param_id, std::vector<uint8_t> & data);
  bool wait_for_calibration_complete(uint8_t node_id, int timeout_seconds);
  void log_test_data(uint8_t node_id);

  std::shared_ptr<EnhancedCANController> can_interface_;
  std::shared_ptr<ComprehensiveErrorHandler> error_handler_;
  std::vector<uint8_t> detected_nodes_;
  std::map<uint8_t, ODriveTestParams> node_configs_;
  std::vector<ODriveTestData> test_data_;
  mutable std::mutex data_mutex_;
};

// =============================================================================
// ENCODER HARDWARE TESTING
// =============================================================================

/**
 * @brief Encoder test parameters
 */
struct EncoderTestParams
{
  std::string interface_type; // "spi", "i2c", "uart", "analog"
  std::string device_path;    // "/dev/spidev0.0", "/dev/i2c-1", etc.
  uint32_t baud_rate{1000000}; // For UART encoders
  double supply_voltage{5.0};  // Supply voltage [V]
  uint32_t counts_per_revolution{8192};
  bool is_absolute{true};
  bool has_index{false};
  double max_frequency{1000000.0}; // Maximum update frequency [Hz]
};

/**
 * @brief Physical encoder hardware tester
 */
class EncoderHardwareTester
{
public:
  EncoderHardwareTester(std::shared_ptr<ComprehensiveErrorHandler> error_handler);
  ~EncoderHardwareTester() = default;

  // Encoder discovery and connection
  bool discover_encoders();
  std::vector<std::string> get_detected_encoders() const {return detected_encoders_;}
  bool connect_to_encoder(const std::string & encoder_name, const EncoderTestParams & params);
  bool disconnect_from_encoder(const std::string & encoder_name);

  // Basic functionality tests
  bool test_encoder_communication(const std::string & encoder_name);
  bool test_position_reading(const std::string & encoder_name);
  bool test_velocity_calculation(const std::string & encoder_name);
  bool test_direction_sensing(const std::string & encoder_name);

  // Accuracy and precision tests
  bool test_repeatability(const std::string & encoder_name, int num_samples = 1000);
  bool test_linearity(const std::string & encoder_name, int num_positions = 100);
  bool test_hysteresis(const std::string & encoder_name);
  bool characterize_noise(const std::string & encoder_name, double duration_seconds = 10.0);

  // Dynamic performance tests
  bool test_maximum_frequency(const std::string & encoder_name);
  bool test_acceleration_response(const std::string & encoder_name);
  bool test_step_response(const std::string & encoder_name);

  // Environmental tests
  bool test_temperature_stability(const std::string & encoder_name, double temp_range_celsius);
  bool test_supply_voltage_variation(const std::string & encoder_name, double voltage_range);
  bool test_electromagnetic_immunity(const std::string & encoder_name);

  // Calibration and compensation
  bool calibrate_encoder(const std::string & encoder_name);
  bool generate_error_compensation_table(const std::string & encoder_name);
  bool validate_compensation(const std::string & encoder_name);

  // Data collection
  struct EncoderTestData
  {
    std::chrono::steady_clock::time_point timestamp;
    std::string encoder_name;
    double position_raw;
    double position_compensated;
    double velocity;
    double temperature;
    double supply_voltage;
    uint32_t error_flags;
    bool is_valid;
  };

  std::vector<EncoderTestData> get_test_data() const {return test_data_;}
  void clear_test_data() {test_data_.clear();}
  bool save_test_data(const std::string & filename);

private:
  bool initialize_encoder_interface(
    const std::string & encoder_name,
    const EncoderTestParams & params);
  double read_raw_position(const std::string & encoder_name);
  bool check_encoder_health(const std::string & encoder_name);
  void log_encoder_data(const std::string & encoder_name);

  std::shared_ptr<ComprehensiveErrorHandler> error_handler_;
  std::vector<std::string> detected_encoders_;
  std::map<std::string, EncoderTestParams> encoder_configs_;
  std::vector<EncoderTestData> test_data_;
  mutable std::mutex data_mutex_;
};

// =============================================================================
// INTEGRATED HARDWARE TEST SUITE
// =============================================================================

/**
 * @brief Test execution parameters
 */
struct HILTestParams
{
  bool enable_safety_checks{true};
  double max_test_duration_hours{1.0};
  double emergency_stop_timeout_ms{100.0};
  std::string log_directory{"hil_test_logs"};
  bool enable_real_time_monitoring{true};
  double data_logging_frequency_hz{1000.0};

  // Test selection
  bool run_calibration_tests{true};
  bool run_functionality_tests{true};
  bool run_performance_tests{true};
  bool run_safety_tests{true};
  bool run_endurance_tests{false};
  bool run_environmental_tests{false};
};

/**
 * @brief Hardware-in-Loop Test Coordinator
 */
class HILTestCoordinator
{
public:
  HILTestCoordinator();
  ~HILTestCoordinator();

  // Initialization
  bool initialize(const HILTestParams & params);
  void shutdown();

  // Hardware management
  bool setup_test_hardware();
  bool verify_safety_systems();
  bool configure_emergency_procedures();

  // Test execution
  bool run_comprehensive_test_suite();
  bool run_quick_functionality_check();
  bool run_performance_characterization();
  bool run_safety_validation();
  bool run_endurance_test(double duration_hours);

  // Individual test categories
  bool run_can_communication_tests();
  bool run_motor_control_tests();
  bool run_encoder_validation_tests();
  bool run_dual_encoder_comparison_tests();
  bool run_pid_tuning_validation_tests();
  bool run_fault_injection_tests();

  // Results and reporting
  struct HILTestResults
  {
    bool overall_success{false};
    std::chrono::steady_clock::time_point start_time;
    std::chrono::steady_clock::time_point end_time;
    std::map<std::string, bool> test_results;
    std::map<std::string, std::string> performance_metrics;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
    std::string detailed_report_path;
  };

  HILTestResults get_last_test_results() const {return last_results_;}
  bool generate_test_report(const std::string & filename);

  // Real-time monitoring
  void start_monitoring();
  void stop_monitoring();
  bool is_monitoring_active() const {return monitoring_active_;}

  // Emergency procedures
  bool trigger_emergency_stop();
  bool clear_emergency_stop();
  bool is_system_safe() const;

private:
  void monitoring_thread();
  void safety_monitoring_thread();
  bool execute_test_sequence(const std::vector<std::function<bool()>> & tests);
  void log_test_event(const std::string & event, const std::string & details = "");
  bool check_hardware_limits();

  HILTestParams params_;
  HILTestResults last_results_;

  // Hardware components
  std::unique_ptr<HardwareManager> hardware_manager_;
  std::unique_ptr<ODriveHardwareTester> odrive_tester_;
  std::unique_ptr<EncoderHardwareTester> encoder_tester_;

  // Motor control system components
  std::shared_ptr<EnhancedCANController> can_interface_;
  std::shared_ptr<ComprehensiveErrorHandler> error_handler_;
  std::shared_ptr<AdvancedInitializationSystem> init_system_;
  std::shared_ptr<DualEncoderSystem> dual_encoder_system_;
  std::shared_ptr<AdvancedPIDController> pid_controller_;

  // Monitoring and safety
  std::atomic<bool> monitoring_active_{false};
  std::atomic<bool> safety_monitoring_active_{false};
  std::thread monitoring_thread_;
  std::thread safety_thread_;

  // Logging
  std::ofstream test_log_;
  mutable std::mutex log_mutex_;
};

// =============================================================================
// HIL TEST AUTOMATION
// =============================================================================

/**
 * @brief Automated test sequence generator
 */
class HILTestAutomation
{
public:
  // Standard test sequences
  static std::vector<std::function<bool()>> generate_odrive_test_sequence(uint8_t node_id);
  static std::vector<std::function<bool()>> generate_encoder_test_sequence(
    const std::string & encoder_name);
  static std::vector<std::function<bool()>> generate_system_integration_test_sequence();
  static std::vector<std::function<bool()>> generate_performance_benchmark_sequence();

  // Custom test builders
  class TestSequenceBuilder
  {
public:
    TestSequenceBuilder & add_hardware_check();
    TestSequenceBuilder & add_calibration_step();
    TestSequenceBuilder & add_functionality_test(const std::string & test_name);
    TestSequenceBuilder & add_performance_test(const std::string & test_name);
    TestSequenceBuilder & add_safety_test(const std::string & test_name);
    TestSequenceBuilder & add_custom_test(std::function<bool()> test_function);
    TestSequenceBuilder & add_delay(double seconds);
    TestSequenceBuilder & add_checkpoint(const std::string & description);

    std::vector<std::function<bool()>> build();

private:
    std::vector<std::function<bool()>> sequence_;
  };

  static TestSequenceBuilder create_sequence() {return TestSequenceBuilder();}
};

} // namespace hardware_testing
} // namespace motor_control_ros2
