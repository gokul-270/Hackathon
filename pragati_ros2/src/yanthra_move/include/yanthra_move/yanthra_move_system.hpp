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

#pragma once

#include <memory>
#include <string>
#include <vector>
#include <atomic>
#include <mutex>
#include <thread>
#include <chrono>

// ROS2 includes
#include <rclcpp/rclcpp.hpp>
// Note: multi_threaded_executor.hpp removed - not needed in header, only in cpp if used
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

// Project includes
#include "yanthra_move/joint_move.h"
#include "yanthra_move/yanthra_io.h"
#include "yanthra_move/error_recovery_types.hpp"
#include "yanthra_move/srv/arm_status.hpp"
#include "yanthra_move/core/motion_controller.hpp"
#include "motor_control_msgs/srv/joint_homing.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"
#include <rclcpp_action/rclcpp_action.hpp>
#include "cotton_detection_msgs/srv/cotton_detection.hpp"

// Forward declarations for modular components
namespace yanthra_move {
    class TransformCache;  // Tier 1.3 - Static TF optimization
}

namespace yanthra_move {

/**
 * @brief Main system class that encapsulates all global state and provides RAII resource management
 *
 * This class replaces the global variables and procedural approach in yanthra_move.cpp
 * with a clean, object-oriented design that ensures proper resource initialization,
 * lifecycle management, and cleanup.
 */
class YanthraMoveSystem {
public:
    // Provider callback type for dependency injection into MotionController
    using CottonPositionProvider =
        std::function<std::optional<std::vector<core::CottonDetection>>()>;

    /**
     * @brief Construct and initialize the Yanthra robotic arm system
     *
     * @param argc Command line argument count
     * @param argv Command line arguments
     * @throws std::runtime_error if initialization fails
     */
    YanthraMoveSystem(int argc, char** argv);

    /**
     * @brief Destructor ensures clean shutdown of all resources
     */
    ~YanthraMoveSystem();

    /**
     * @brief Run the main robotic arm operation
     *
     * @return int Exit code (0 for success, non-zero for error)
     */
    int run();

    /**
     * @brief Shutdown all ROS2 objects and call rclcpp::shutdown()
     *
     * This should be called from main() before the YanthraMoveSystem destructor
     * to ensure proper ROS2 cleanup order and prevent segmentation faults.
     */
    void shutdownAndCleanup();

    /**
     * @brief Get the ROS2 node for use with rclcpp::spin()
     *
     * This allows the ROS2 launch system to manage the node's executor
     * instead of creating executor conflicts.
     *
     * @return std::shared_ptr<rclcpp::Node> The node instance
     */
    std::shared_ptr<rclcpp::Node> getNode() const { return node_; }

    /**
     * @brief Request stop - sets the internal global_stop_requested_ flag
     *
     * This allows the signal handler to request a stop without needing
     * to call the full shutdownAndCleanup method.
     */
    void requestStop() { global_stop_requested_.store(true); }

    /**
     * @brief Get cotton position provider callback for dependency injection
     *
     * Returns a callable that MotionController can invoke to get latest
     * cotton positions. Thread-safe, returns empty optional if no data.
     *
     * Example usage in MotionController:
     * @code
     *   auto provider = system->getCottonPositionProvider();
     *   auto positions = provider();  // Get latest positions
     *   if (positions) {
     *       // Use positions for motion planning
     *   }
     * @endcode
     *
     * @return CottonPositionProvider callback function
     */
    CottonPositionProvider getCottonPositionProvider();

    /**
     * @brief Get detection trigger callback for re-validation after each pick
     *
     * Returns a callable that triggers a new detection and waits for fresh results.
     * Used by MotionController to re-validate remaining cotton positions after each pick.
     * This prevents duplicate picks by ensuring we always work with fresh data.
     *
     * @return CottonPositionProvider callback that triggers detection and returns fresh positions
     */
    CottonPositionProvider getDetectionTriggerCallback();

    /**
     * @brief Get latest cotton detection result (for diagnostics/testing)
     *
     * Thread-safe accessor for latest detection result.
     * Returns empty optional if no detection received yet.
     *
     * @return Latest DetectionResult or nullopt
     */
    std::optional<std::vector<core::CottonDetection>> getLatestCottonPositions() const;

    /**
     * @brief Internal helper - get latest positions without acquiring mutex
     *
     * Assumes caller already holds detection_mutex_ lock.
     * Used internally to avoid deadlock when mutex is already held.
     *
     * @return Latest cotton positions or nullopt
     */
    std::optional<std::vector<core::CottonDetection>> getLatestCottonPositions_NoLock() const;

    // Delete copy and move constructors/assignments to prevent accidental copying
    YanthraMoveSystem(const YanthraMoveSystem&) = delete;
    YanthraMoveSystem& operator=(const YanthraMoveSystem&) = delete;
    YanthraMoveSystem(YanthraMoveSystem&&) = delete;
    YanthraMoveSystem& operator=(YanthraMoveSystem&&) = delete;

private:
    // ==============================================
    // CORE ROS2 RESOURCES
    // ==============================================
    std::shared_ptr<rclcpp::Node> node_;
    // Executor removed to prevent conflicts - use external rclcpp::spin() instead

    // ==============================================
    // MODULAR COMPONENTS
    // ==============================================
    std::unique_ptr<core::MotionController> motion_controller_;

    // ==============================================
    // JOINT CONTROL SYSTEM
    // ==============================================
    std::unique_ptr<joint_move> joint_move_2_;
    std::unique_ptr<joint_move> joint_move_3_;
    std::unique_ptr<joint_move> joint_move_4_;
    std::unique_ptr<joint_move> joint_move_5_;

    // Joint command publishers for fast motor control
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint2_cmd_pub_;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint3_cmd_pub_;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint4_cmd_pub_;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr joint5_cmd_pub_;

    // ==============================================
    // IO INTERFACES
    // ==============================================
    std::unique_ptr<d_out> problem_indicator_out_;
    std::unique_ptr<d_in> start_switch_in_;
    std::unique_ptr<d_in> shutdown_switch_in_;

    // Hardware state publishers
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr start_switch_state_pub_;
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr shutdown_switch_state_pub_;
    rclcpp::TimerBase::SharedPtr switch_state_timer_;

    // Periodic stats timer (similar to cotton_detection stats)
    rclcpp::TimerBase::SharedPtr stats_timer_;
    double stats_log_interval_sec_{30.0};  // Default 30 seconds
    std::chrono::steady_clock::time_point system_start_time_;

    // Periodic stats callback
    void statsLogCallback();

    // EE/Compressor safety watchdog (1s polling interval)
    rclcpp::TimerBase::SharedPtr safety_watchdog_timer_;
    float ee_watchdog_timeout_sec_{600.0f};          // Max EE on-duration before forced shutoff
    float compressor_watchdog_timeout_sec_{900.0f};  // Max compressor on-duration before forced shutoff
    void safetyWatchdogCallback();

    // Phase 4: Parameter change notification system
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr parameter_change_pub_;

    // START_SWITCH topic interface (preferred over GPIO)
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr start_switch_topic_sub_;
    std::atomic<bool> start_switch_topic_received_{false};

    // SAFETY: Flag to prevent START_SWITCH from being processed during initialization
    // This prevents race conditions where START_SWITCH arrives before system is ready
    std::atomic<bool> system_ready_for_start_switch_{false};

    // SHUTDOWN_SWITCH topic interface (for ARM client MQTT bridge)
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr shutdown_switch_topic_sub_;

    // Flag to track if system poweroff was requested (from vehicle shutdown command)
    // When true, shutdownAndCleanup() will execute 'sudo shutdown -h now' after cleanup
    std::atomic<bool> shutdown_poweroff_requested_{false};

    // ==============================================
    // TF2 TRANSFORM SYSTEM
    // ==============================================
    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::unique_ptr<tf2_ros::TransformListener> tf_listener_;

    // Transform cache for static TF optimization (Tier 1.3)
    std::shared_ptr<class TransformCache> transform_cache_;

    // ==============================================
    // ROS2 SERVICES
    // ==============================================
    rclcpp_action::Client<motor_control_msgs::action::JointHoming>::SharedPtr joint_homing_action_client_;
    rclcpp::Client<motor_control_msgs::srv::JointHoming>::SharedPtr joint_idle_service_;
    rclcpp::Service<yanthra_move::srv::ArmStatus>::SharedPtr arm_status_service_;

    // Cotton detection service client (trigger detection on demand)
    rclcpp::Client<cotton_detection_msgs::srv::CottonDetection>::SharedPtr cotton_detection_service_;
    mutable std::atomic<int> detection_unavailable_count_{0};  // Detection service not-ready count
    double detection_service_timeout_sec_{2.0};        // Configurable wait_for_service timeout
    double pick_cycle_timeout_sec_{15.0};              // Max duration for a single pick cycle

    // ==============================================
    // COTTON DETECTION INTEGRATION
    // ==============================================
    // Design: YanthraMoveSystem owns the ROS2 subscription and provides
    // data to MotionController via a provider callback (dependency injection).
    // This maintains separation of concerns: YanthraMoveSystem = I/O layer,
    // MotionController = logic layer (remains ROS2-agnostic for testability).

    // Note: cotton_detection_msgs types are forward-declared in separate namespace
    // Full includes are in the .cpp file to avoid header pollution

    // Cotton detection subscription and buffer
    rclcpp::SubscriptionBase::SharedPtr cotton_detection_sub_;

    // Thread-safe buffer for latest detection results with staleness filtering
    // Using type-erased storage to avoid header pollution
    mutable std::mutex detection_mutex_;
    mutable std::condition_variable detection_cv_;  // Signal fresh data arrival
    std::shared_ptr<void> latest_detection_;  // Type-erased DetectionResult
    bool has_detection_{false};
    rclcpp::Time last_detection_time_;

    // Detection staleness parameters (Tier 2.1)
    static constexpr auto MAX_DETECTION_AGE_MS = std::chrono::milliseconds(200);  // 200ms max age

    // Detection stats tracking (for periodic stats logging)
    mutable std::atomic<uint64_t> detection_requests_total_{0};      // Total detection requests
    mutable std::atomic<uint64_t> detection_stale_filtered_{0};      // Filtered due to staleness
    mutable std::atomic<uint64_t> detection_timeout_count_{0};       // Timed out waiting for data
    mutable std::atomic<uint64_t> detection_success_count_{0};       // Successfully returned positions
    mutable std::atomic<int64_t> detection_last_age_ms_{0};          // Age of last detection used

    /**
     * @brief Get latest detection with staleness filtering
     *
     * Returns the latest detection only if it's not older than MAX_DETECTION_AGE_MS.
     * This prevents using stale detection data that may no longer be accurate.
     *
     * @return Latest detection positions or empty optional if no recent detection
     */
    std::optional<std::vector<geometry_msgs::msg::Point>> getLatestDetectionWithStalenessCheck() const;

    // ==============================================
    // CONFIGURATION PARAMETERS
    // ==============================================

    // System operation parameters
    std::atomic<bool> continuous_operation_{false};
    int max_runtime_minutes_{0};  // 0=use defaults, -1=infinite, >0=custom timeout in minutes
    bool save_logs_{false};
    std::atomic<bool> simulation_mode_{false};
    bool arm_calibration_{false};

    // Hardware enable flags
    bool trigger_camera_{false};
    bool global_vacuum_motor_{false};
    bool end_effector_enable_{false};
    bool continuous_vacuum_{true};
    bool end_effector_drop_conveyor_{false};

    // Joint configuration parameters
    bool joint3_multiple_zero_pose_{false};
    double joint3_parking_pose_{0.0};
    double joint3_homing_position_{0.0};
    std::vector<double> joint3_zero_poses_;

    bool joint4_multiple_zero_pose_{false};
    double joint4_parking_pose_{0.0};
    double joint4_homing_position_{0.0};
    std::vector<double> joint4_zero_poses_;

    double joint5_parking_pose_{0.0};
    double joint5_homing_position_{0.0};
    double joint5_vel_limit_{0.0};

    // Timing parameters
    double picking_delay_{0.0};
    double pre_start_len_{0.0};
    double pre_start_delay_{0.0};
    float l2_homing_sleep_time_{0.0f};
    float l2_step_sleep_time_{0.0f};
    float l2_idle_sleep_time_{0.0f};
    float min_sleep_time_for_motor_motion_{0.5f};
    float cotton_capture_detect_wait_time_{1.0f};
    float min_sleep_time_for_cotton_drop_{0.8f};
    float min_sleep_time_for_cotton_drop_from_eef_{0.5f};

    // End effector timing parameters
    float ee_runtime_during_l5_forward_movement_{0.250f};
    float ee_runtime_during_l5_backward_movement_{0.500f};
    float ee_runtime_during_reverse_rotation_{0.500f};

    // Physical system parameters
    double end_effector_len_{0.0};
    double link5_min_length_{0.0};
    double link5_max_length_{0.0};
    float fov_theta_max_{0.3926f};  // 22.5 degrees
    float fov_phi_max_{0.3926f};    // 22.5 degrees

    // Jerk control parameters
    bool jerk_enabled_phi_{false};
    bool jerk_enabled_theta_{false};
    float theta_jerk_value_{0.0f};
    float phi_jerk_value_{0.0f};

    // Height scanning parameters
    bool height_scan_enable_{false};
    double height_scan_min_{0.0};
    double height_scan_max_{0.0};
    double height_scan_step_{0.0};

    // Testing and calibration flags
    bool yanthra_lab_calibration_testing_{false};
    bool use_preloaded_centroids_{false};

    // Directory paths
    std::string pragati_install_dir_{"."};
    std::string pragati_input_dir_;
    std::string pragati_output_dir_;


    // Shutdown parameters
    int shutdown_delay_minutes_{1};  // Delay before system poweroff (0 = immediate, >0 = scheduled/cancellable)

    // ==============================================
    // RUNTIME STATE
    // ==============================================
    std::string arm_status_{"uninit"};
    mutable std::mutex arm_status_mutex_;
    std::atomic<bool> global_stop_requested_{false};
    std::atomic<bool> keyboard_monitor_active_{false};
    std::atomic<bool> cycle_in_progress_{false};  // Track if a pick cycle is running
    int picked_cotton_count_{0};
    double joint2_old_pose_{0.001};

    // Start switch stats (track triggers during operation for timing analysis)
    std::atomic<uint64_t> start_switch_total_triggers_{0};      // Total triggers received
    std::atomic<uint64_t> start_switch_ignored_during_cycle_{0}; // Triggers ignored (cycle was running)
    std::atomic<uint64_t> start_switch_coalesced_{0};           // Triggers coalesced (flag already set)

    // Timing variables
    double start_time_{0.0};
    double end_time_{0.0};
    double last_time_{0.0};

    // Phase 4: Parameter change tracking
    std::atomic<int> parameter_change_count_{0};
    // Protected by parameter_time_mutex_ — written by executor thread (parameter callback),
    // may be read by main thread for diagnostics
    std::chrono::steady_clock::time_point last_parameter_change_time_;
    mutable std::mutex parameter_time_mutex_;

    // ==============================================
    // PRIVATE METHODS
    // ==============================================

    /**
     * @brief Initialize ROS2 node and basic logging
     */
    void initializeROS2(int argc, char** argv);

    /**
     * @brief Initialize signal handlers for graceful shutdown
     */
    void initializeSignalHandlers();

    /**
     * @brief Initialize keyboard monitoring for emergency stop
     */
    void initializeKeyboardMonitoring();

    /**
     * @brief Initialize IO interfaces (LEDs, switches, etc.)
     */
    void initializeIOInterfaces();

    /**
     * @brief Initialize joint movement controllers
     */
    void initializeJointControllers();

    /**
     * @brief Initialize TF2 transform system
     */
    void initializeTransformSystem();

    /**
     * @brief Initialize ROS2 service clients and servers
     */
    void initializeServices();

    /**
     * @brief Initialize ROS2 publishers for joint commands
     */
    void initializePublishers();

    /**
     * @brief Initialize cotton detection subscription
     */
    void initializeCottonDetection();

    /**
     * @brief Check if cotton detection should be triggered on start switch press
     *
     * Returns false if:
     * - ArUco calibration mode is active (yanthra_lab_calibration_testing_)
     * - Cotton detection service client is not initialized
     *
     * Returns true otherwise (normal cotton detection mode).
     *
     * @return bool True if cotton detection should be triggered, false otherwise
     */
    bool shouldTriggerCottonDetection() const;

    // Note: cottonDetectionCallback is implemented internally in .cpp
    // to avoid exposing cotton_detection_msgs types in the header

    // initializeExecutor removed to prevent ROS2 executor conflicts

    /**
     * @brief Declare all ROS2 parameters with default values
     */
    void declareAllParameters();

    /**
     * @brief Declare START_SWITCH parameters early for external access
     */
    void declareStartSwitchParameters();

    /**
     * @brief Declare and validate core operational parameters with constraints
     */
    void declareCoreOperationalParameters();

    /**
     * @brief Declare and validate timing/motion parameters with range constraints
     */
    void declareTimingMotionParameters();

    /**
     * @brief Declare and validate joint initialization parameters with safety limits
     */
    void declareJointInitParameters();

    /**
     * @brief Declare and validate J4 multi-position scanning parameters
     */
    void declareMultiPositionScanParameters();

    /**
     * @brief Declare J5 collision avoidance parameters for two-arm setups
     */
    void declareCollisionAvoidanceParameters();

    /**
     * @brief Validate all parameters after loading and apply safety constraints
     */
    void validateAllParameters();

    /**
     * @brief Install runtime parameter validation callback for constraint enforcement
     */
    void installParameterValidationCallback();

    /**
     * @brief Runtime parameter change validation callback
     */
    rcl_interfaces::msg::SetParametersResult onParameterChange(
        const std::vector<rclcpp::Parameter>& parameters);

    /**
     * @brief Apply hot reloading for specific parameter changes
     */
    void applyParameterHotReload(const std::string& param_name);

    /**
     * @brief Publish parameter change notifications
     */
    void publishParameterChangeNotifications(const std::vector<std::string>& changed_params);

    /**
     * @brief Create a parameter descriptor with validation constraints
     */
    rcl_interfaces::msg::ParameterDescriptor createParameterDescriptor(
        const std::string& description,
        const std::string& additional_constraints = "",
        bool read_only = false);

    /**
     * @brief Create a double parameter descriptor with range constraints
     */
    rcl_interfaces::msg::ParameterDescriptor createDoubleDescriptor(
        const std::string& description,
        double min_value,
        double max_value,
        const std::string& additional_constraints = "",
        bool read_only = false);

    /**
     * @brief Create an integer parameter descriptor with range constraints
     */
    rcl_interfaces::msg::ParameterDescriptor createIntegerDescriptor(
        const std::string& description,
        int64_t min_value,
        int64_t max_value,
        const std::string& additional_constraints = "",
        bool read_only = false);

    // ==============================================
    // PHASE 3: ERROR RECOVERY & RESILIENCE
    // ==============================================

    /**
     * @brief Initialize error recovery and resilience systems
     */
    void initializeErrorRecovery();

    /**
     * @brief Centralized dispatch for all operational failures (D3 escalation ladder)
     *
     * Routes MOTOR_TIMEOUT, MOTOR_ERROR, DETECTION_UNAVAILABLE, PICK_TIMEOUT
     * through a single escalation path: log -> retry -> home -> safe mode.
     */
    void handleOperationalFailure(FailureType type, const FailureContext& context);

    /**
     * @brief Handle hardware errors with automatic recovery
     */
    bool handleHardwareError(const std::string& component, const std::string& error_msg);

    /**
     * @brief Handle ROS2 communication errors
     */
    bool handleCommunicationError(const std::string& service_name, const std::string& error_msg);

    /**
     * @brief Attempt automatic recovery from common failure modes
     */
    bool attemptSystemRecovery(const std::string& failure_type);

    /**
     * @brief Enter safe mode — EE off, compressor off, attempt homing, set global_stop
     */
    void enterSafeMode(const std::string& reason);

    /**
     * @brief Check system health and trigger recovery if needed
     */
    bool performHealthCheck();

    /**
     * @brief Reset system components for recovery
     */
    bool resetSystemComponents();

    /**
     * @brief Graceful degradation when full functionality isn't available
     */
    void enableDegradedMode(const std::vector<std::string>& disabled_components);

    /**
     * @brief Retry mechanism with exponential backoff
     */
    template<typename Func>
    bool retryWithBackoff(Func operation, const std::string& operation_name,
                         int max_retries = 3, double base_delay = 1.0);

    // Error recovery state tracking (type defined in error_recovery_types.hpp)
    ErrorRecoveryState error_recovery_state_;

    // Configurable error recovery thresholds (D3)
    int consecutive_failure_safe_mode_threshold_{3};
    int retry_backoff_base_ms_{500};

    // Hot-reload failure tracking (Task 2.13)
    std::atomic<uint32_t> hot_reload_failure_count_{0};

    // Detection service failure tracking (Task 2.15)
    std::atomic<uint32_t> detection_service_failure_count_{0};


    /**
     * @brief Load all configuration parameters from ROS2 parameter server
     */
    void loadParameters();

    /**
     * @brief Initialize GPIO pins (if enabled)
     */
    void initializeGPIO();

    /**
     * @brief Initialize hardware interfaces
     */
    void initializeHardware();

    /**
     * @brief Initialize camera system (if enabled)
     */
    void initializeCamera();

    /**
     * @brief Initialize modular components
     */
    void initializeModularComponents();

    /**
     * @brief Run the main robotic arm operation loop
     */
    void runMainOperationLoop();

    /**
     * @brief Perform initialization and homing sequence for all joints
     *
     * This method waits for ODrive services to become available,
     * then performs sequential homing of joints in the correct order.
     * Must be called before waiting for start_switch.
     *
     * @return bool True if initialization and homing succeeded, false otherwise
     */
    bool performInitializationAndHoming();

    /**
     * @brief Call ODrive joint homing service for a specific joint
     *
     * @param joint_id The ODrive joint ID to home
     * @param reason Output parameter for success/failure reason
     * @return bool True if homing succeeded, false otherwise
     */
    bool callJointHomingService(int joint_id, std::string& reason);

    /**
     * @brief Call ODrive joint idle service for a specific joint
     *
     * @param joint_id The ODrive joint ID to idle
     * @param reason Output parameter for success/failure reason
     * @return bool True if idle succeeded, false otherwise
     */
    bool callJointIdleService(int joint_id, std::string& reason);

    /**
     * @brief Perform system shutdown and cleanup
     */
    void shutdown();

    /**
     * @brief Arm status service callback
     */
    void armStatusServiceCallback(
        const std::shared_ptr<yanthra_move::srv::ArmStatus::Request> request,
        std::shared_ptr<yanthra_move::srv::ArmStatus::Response> response);

    /**
     * @brief Get detailed reason for current arm status
     *
     * @return string Contextual explanation of the current arm_status_
     */
    std::string getArmStatusReason() const;

    /**
     * @brief Switch state timer callback for hardware simulation
     */
    void publishSwitchStates();

    /**
     * @brief Get current time in milliseconds
     */
    double getCurrentTimeMillis();

    /**
     * @brief Print timestamp with message
     */
    void printTimestamp(const std::string& message);
};

}  // namespace yanthra_move
