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

// Sub-headers extracted from this file (backward-compatible forwarding)
#include <yanthra_move/core/cotton_detection.hpp>
#include <yanthra_move/core/joint_config_types.hpp>
#include <yanthra_move/core/multi_position_config.hpp>

#include <memory>
#include <vector>
#include <atomic>
#include <map>
#include <mutex>
#include <chrono>
#include <rclcpp/rclcpp.hpp>
#include <tf2_ros/buffer.h>
#include <geometry_msgs/msg/point.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

// GPIO control for end effector and compressor
namespace motor_control_ros2 {
    class GPIOControlFunctions;
}

// Forward declare joint_move to avoid circular dependency
class joint_move;

// Forward declare MoveResult (defined in joint_move.h) for recordMoveResult()
enum class MoveResult : int;

// Forward declare error recovery types (defined in error_recovery_types.hpp)
namespace yanthra_move { enum class FailureType; struct FailureContext; }

namespace yanthra_move { namespace core {

class RecoveryManager;  // Forward declaration
class TrajectoryPlanner;  // Forward declaration
class CaptureSequence;  // Forward declaration
class TrajectoryExecutor;  // Forward declaration
class ArucoCoordinator;  // Forward declaration

/**
 * @brief Motion Controller - handles motion planning and execution
 *
 * This class encapsulates the main operational logic for the robotic arm,
 * including cotton picking sequences, trajectory planning, and motion execution.
 * Extracted from the original 3800-line monolithic file for better maintainability.
 */
class MotionController {
public:
    /**
     * @brief Constructor
     * @param node ROS2 node for logging and communication
     * @param joint3 Pointer to joint3 controller (for phi angle control)
     * @param joint5 Pointer to joint5 controller (for r/theta control)
     */
    explicit MotionController(std::shared_ptr<rclcpp::Node> node,
                            joint_move* joint3,
                            joint_move* joint5,
                            joint_move* joint4,
                            std::shared_ptr<tf2_ros::Buffer> tf_buffer);

    /**
     * @brief Destructor (defined in .cpp to allow unique_ptr with forward-declared types)
     */
    ~MotionController();

    /**
     * @brief Initialize the motion controller with cotton position provider
     * @param provider Callback function to get latest cotton positions from YanthraMoveSystem
     * @return true if initialization successful, false otherwise
     */
    bool initialize(std::function<std::optional<std::vector<CottonDetection>>()> provider);

    /**
     * @brief Set detection trigger callback for re-validation after each pick
     * @param trigger Callback that triggers detection and returns fresh positions
     */
    void setDetectionTriggerCallback(std::function<std::optional<std::vector<CottonDetection>>()> trigger) {
        detection_trigger_callback_ = trigger;
    }

    /**
     * @brief Callback type for operational failure dispatch (D3)
     *
     * Bridges MotionController failures to YanthraMoveSystem::handleOperationalFailure()
     */
    using OperationalFailureCallback =
        std::function<void(yanthra_move::FailureType, const yanthra_move::FailureContext&)>;

    /**
     * @brief Set operational failure callback for centralized error recovery
     * @param callback Function invoked when consecutive failures exceed threshold
     */
    void setOperationalFailureCallback(OperationalFailureCallback callback);

    /**
     * @brief Set the consecutive failure threshold for safe-mode escalation
     * @param threshold Number of consecutive failures before escalation fires
     */
    void setConsecutiveFailureThreshold(int threshold);

    /**
     * @brief Set the pick cycle timeout
     * @param timeout_sec Maximum seconds for a single pick cycle
     */
    void setPickCycleTimeout(double timeout_sec) {
        pick_cycle_timeout_sec_.store(timeout_sec);
    }

    /**
     * @brief Execute the main operational cycle
     * @return true if cycle completed successfully, false otherwise
     */
    bool executeOperationalCycle();

    /**
     * @brief Execute cotton picking sequence
     * @param cotton_positions Vector of cotton positions to pick
     * @param home_j5 If true, homes J5 (extension) during retreat (default: true)
     * @param home_j3 If true, homes J3 (rotation) during retreat (default: true)
     * @param home_j4 If true, homes J4 (left/right) during retreat (default: true)
     * @return Number of cotton pieces picked
     */
    int executeCottonPickingSequence(const std::vector<CottonDetection>& cotton_detections, bool home_j5 = true, bool home_j3 = true, bool home_j4 = true);

    /**
     * @brief Move arm to parking/homing position with arrival verification
     * @return true if all joints reached home, false if any joint failed
     */
    [[nodiscard]] bool moveToPackingPosition();

    /**
     * @brief Execute height scanning sequence
     * @param min_height Minimum height for scanning
     * @param max_height Maximum height for scanning
     * @param step_size Step size for scanning
     */
    void executeHeightScan(double min_height, double max_height, double step_size);

    /**
     * @brief Check if motion controller is ready for operation
     */
    bool isReady() const { return initialized_; }

    /**
     * @brief Request emergency stop
     */
    void requestEmergencyStop() { emergency_stop_requested_.store(true); }

    /**
     * @brief Check if emergency stop was requested
     */
    bool isEmergencyStopRequested() const { return emergency_stop_requested_.load(); }

    bool isEndEffectorEnabled() const { return end_effector_enable_.load(); }

    // EE/Compressor watchdog accessors (thread-safe: delegated to CaptureSequence)
    bool isEeCurrentlyOn() const;
    std::chrono::steady_clock::time_point getEeOnSince() const;
    bool isCompressorCurrentlyOn() const;
    std::chrono::steady_clock::time_point getCompressorOnSince() const;

    void turnOffEndEffector();
    void turnOffCompressor();

    /**
     * @brief Check if motors are responding (publishing to /joint_states)
     * @return true if motors are available and publishing feedback
     */
    bool areMotorsAvailable();

    // Stats accessors for periodic reporting (thread-safe: read from executor thread)
    int getCycleCount() const { return cycle_count_.load(); }
    int getTotalCottonPicked() const { return total_cotton_picked_.load(); }

    // Failure statistics accessors (delegated to RecoveryManager)
    int getTfFailureCount() const;
    int getPositionFeedbackFailureCount() const;
    int getJointLimitFailureCount() const;

    // Extended statistics accessors (delegated to RecoveryManager)
    int getPositionFeedbackFailureJ3() const;
    int getPositionFeedbackFailureJ4() const;
    int getPositionFeedbackFailureJ5() const;
    int getEeActivationCount() const;
    int getCompressorActivationCount() const;
    int getTotalPicksAttempted() const;
    int getTotalPicksSuccessful() const;
    double getAveragePickDurationMs() const;

    // Move failure tracking accessors
    int getConsecutiveMoveFailures(int joint_id) const;
    int getCumulativeMoveFailures(int joint_id) const;

private:
    // ROS2 components
    std::shared_ptr<rclcpp::Node> node_;
    std::shared_ptr<tf2_ros::Buffer> tf_buffer_;

    // Joint controllers for motor commanding (order matches constructor initialization)
    joint_move* joint_move_3_;  // Controls phi angle (base rotation)
    joint_move* joint_move_5_;  // Controls r/theta (extension and vertical)
    joint_move* joint_move_4_;  // Controls theta angle (vertical/elevation)

    // Cotton position provider (dependency injection from YanthraMoveSystem)
    std::function<std::optional<std::vector<CottonDetection>>()> cotton_position_provider_;

    // Detection trigger callback for re-validation after each pick
    // Returns fresh positions after triggering new detection
    std::function<std::optional<std::vector<CottonDetection>>()> detection_trigger_callback_;


    // State management
    bool initialized_{false};
    std::atomic<bool> emergency_stop_requested_{false};

    // Operation counters and metrics (atomic: read cross-thread by statsLogCallback)
    std::atomic<int> cycle_count_{0};
    std::atomic<int> total_cotton_picked_{0};
    double operation_start_time_{0.0};


    // Recovery tracking (extracted class)
    std::unique_ptr<RecoveryManager> recovery_manager_;
    std::unique_ptr<TrajectoryPlanner> trajectory_planner_;
    std::unique_ptr<CaptureSequence> capture_sequence_;
    std::unique_ptr<TrajectoryExecutor> trajectory_executor_;
    std::unique_ptr<ArucoCoordinator> aruco_coordinator_;

    // Motor availability tracking
    std::atomic<bool> motors_available_{false};  // True if motors are publishing to /joint_states
    std::chrono::steady_clock::time_point last_motor_check_time_;
    static constexpr std::chrono::seconds MOTOR_CHECK_INTERVAL{5};  // Re-check every 5 seconds
    rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr motor_availability_client_;  // Reusable client


    // End-effector ON duration tracking (per-pick accumulation, kept in MC for timing accounting)
    int64_t ee_total_on_ms_ = 0;

    // Per-pick sub-phase timing (set by approach/retreat, read by JSON logger)
    int64_t approach_j3_ms_ = 0;
    int64_t approach_j4_ms_ = 0;
    int64_t approach_j5_ms_ = 0;
    int64_t retreat_j5_ms_ = 0;
    int64_t retreat_ee_off_ms_ = 0;
    int64_t retreat_j3_ms_ = 0;
    int64_t retreat_j4_ms_ = 0;
    int64_t retreat_compressor_ms_ = 0;

    // Per-pick plan result (set by pickCottonAtPosition, read by JSON logger)
    double polar_r_ = 0.0;
    double polar_theta_ = 0.0;
    double polar_phi_ = 0.0;
    std::string plan_status_{"N/A"};
    double plan_j3_cmd_ = 0.0;
    double plan_j4_cmd_ = 0.0;
    double plan_j5_cmd_ = 0.0;

    // Per-pick inter-pick delay (set by executeCottonPickingSequence, read by JSON logger)
    int64_t delay_ms_ = 0;

    // Per-pick position feedback results (set by waitForPositionFeedback, read by JSON logger)
    bool feedback_j3_ok_ = true;
    double feedback_j3_error_ = 0.0;
    bool feedback_j4_ok_ = true;
    double feedback_j4_error_ = 0.0;
    bool feedback_j5_ok_ = true;
    double feedback_j5_error_ = 0.0;

    // Motion parameters (loaded from ROS2 parameters)
    // NOTE: Hot-reloadable params are std::atomic — they may be written by the
    // executor thread (parameter hot-reload callback) and read by the pick-cycle
    // thread.  std::atomic<double/float/bool> is lock-free on aarch64 (RPi 4B).
    std::atomic<double> picking_delay_{0.1};
    std::atomic<double> min_sleep_time_for_motor_motion_{0.2};
    std::atomic<double> inter_joint_delay_{0.3};  // Delay between sequential joint movements
    std::atomic<double> cotton_settle_delay_{0.2};  // Wait before compressor burst to let cotton settle
    std::atomic<double> cotton_capture_detect_wait_time_{0.0};  // Additional wait in capture (0 since EE runs in approach)
    std::atomic<double> compressor_burst_duration_{0.5};  // How long to run compressor for cotton drop

    // Pick cycle safety timeout
    std::atomic<double> pick_cycle_timeout_sec_{15.0};  // Max duration for a single pick cycle

    // Cotton eject sub-sequence parameters
    bool enable_cotton_eject_{false};                  // Gate for the eject sequence (default off)
    bool enable_compressor_eject_{false};              // Gate for compressor activation (default off)
    double j3_eject_position_{-0.2};                   // J3 angle during eject (rotations, <= -0.2 limit)
    double ee_motor2_eject_duration_ms_{300.0};            // How long to run M2 in reverse (ms)
    double ee_motor2_forward_flush_ms_{200.0};             // How long to run M2 forward after eject to clear belt entrance (ms)
    double j3_eject_feedback_timeout_sec_{1.5};        // Max wait for J3 CAN feedback before M2 fires anyway

    // PHI compensation parameters: moved to TrajectoryPlanner

    // Height scanning parameters
    bool height_scan_enable_{false};
    double height_scan_min_{0.0};
    double height_scan_max_{0.0};
    double height_scan_step_{0.0};

    // ArUco calibration mode
    bool yanthra_lab_calibration_testing_{false};
    bool use_preloaded_centroids_{false};

    // Re-triggering detection after each pick (disabled by default - can cause deadlock)
    bool enable_detection_retrigger_{false};

    // Post-cycle parking (disabled by default - retreat already homes all joints)
    bool enable_post_cycle_parking_{false};

    // Multi-position scan: skip J4 command in approach (J4 already at scan position)
    bool skip_j4_in_approach_{false};

    // L3 idle parking optimization (reduces motor temperature when idle)
    // When enabled, L3 moves to parking position (tilted up) when not actively picking
    // SAFETY: J4 can only move when L3 is at homing position (tilted down, creates clearance)
    bool enable_l3_idle_parking_{false};
    double joint3_parking_position_{0.008};  // Natural resting position (loaded from motor_control)
    std::atomic<bool> l3_at_parking_{false};  // Track if L3 is currently at parking position

    // Position wait mode: "service", "feedback", or "blind_sleep"
    //   service    = JointPositionCommand with wait_for_completion (motor-confirmed arrival)
    //   feedback   = poll /joint_states until within tolerance (legacy, has echo bug)
    //   blind_sleep = distance-based sleep estimate (reliable fallback)
    std::string position_wait_mode_{"blind_sleep"};
    double position_feedback_timeout_sec_{2.0};  // Timeout for position verification
    double position_feedback_tolerance_{0.01};   // Position error tolerance (joint units)

    // Latest joint positions from /joint_states subscription
    std::mutex joint_state_mutex_;
    std::map<std::string, double> latest_joint_positions_;  // joint_name -> position
    rclcpp::Time last_joint_state_time_;
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_states_sub_;  // Persistent subscription

    // Position-based dynamic EE timing parameters (replaces time-based calculation)
    // ee_start_distance_: Start EE when J5 is this distance (m) before reaching cotton
    // ee_stop_distance_: Stop EE when J5 has retracted this distance (m) from cotton
    std::atomic<float> ee_start_distance_{0.025f};  // Default 25mm (similar to ROS1 pre_start_len)
    std::atomic<float> ee_stop_distance_{0.050f};   // Default 50mm
    double last_cotton_position_{0.0}; // Track last J5 cotton position for retreat EE stop

    // End effector timing
    std::atomic<float> ee_runtime_during_l5_forward_movement_{0.250f};
    std::atomic<float> ee_runtime_during_l5_backward_movement_{0.500f};
    std::atomic<float> ee_runtime_during_reverse_rotation_{0.500f};
    std::atomic<float> ee_post_joint5_delay_{0.3f};  // Delay AFTER joint5 completes before EE starts

    // Dynamic EE pre-start timing (ROS-1 method)
    // When true: EE starts when joint5 is ee_start_distance_ from target position
    // When false: EE starts ee_post_joint5_delay_ seconds AFTER joint5 reaches target (current behavior)
    std::atomic<bool> use_dynamic_ee_prestart_{false};

    // GPIO control for end effector and compressor (new cotton collection method)
    std::shared_ptr<motor_control_ros2::GPIOControlFunctions> gpio_control_;
    bool gpio_degraded_{false};  // Task 2.14: Set true if GPIO init fails
    std::atomic<bool> end_effector_enable_{true};  // Master enable flag from parameters

    // Joint initialization parameters (defined in joint_config_types.hpp)

    JointInitParams joint2_init_;
    JointInitParams joint3_init_;
    JointInitParams joint4_init_;
    JointInitParams joint5_init_;

    // Joint limits (defined in joint_config_types.hpp)

    JointLimits joint3_limits_;  // Rotation limits (rotations)
    JointLimits joint4_limits_;  // Left/right limits (meters)
    JointLimits joint5_limits_;  // Extension limits (meters)

    // Per-joint position tolerances (loaded from motor_control node - single source of truth)
    // Used by joint_move instances for feedback-based arrival detection
    double joint3_position_tolerance_{0.05};   // Default: 0.05 rotations (~18 degrees)
    double joint4_position_tolerance_{0.005};  // Default: 5mm
    double joint5_position_tolerance_{0.005};  // Default: 5mm

    // Joint4 multi-position scanning configuration (defined in multi_position_config.hpp)
    Joint4MultiPositionConfig j4_multipos_config_;

    // Multi-position statistics (defined in multi_position_config.hpp)
    MultiPositionStats multipos_stats_;

    // Current J4 scan offset (for multi-position theta correction)
    double current_j4_scan_offset_{0.0};  // Current J4 offset from home position (meters)

    // Parameter fallback tracking (Task 2.16)
    uint32_t param_load_failure_count_{0};

    // Hardware parameters
    double joint5_hardware_offset_{0.320};  // Hardware offset in meters (forwarded to TrajectoryPlanner)
    // Transmission factors and directions: moved to TrajectoryPlanner

    /**
     * @brief Load motion parameters from ROS2 parameter server
     */
    void loadMotionParameters();

    /**
     * @brief Load joint limits from motor_control node parameters
     * @return true if limits loaded successfully, false otherwise
     */
    bool loadJointLimits();

    // Parameter loading helpers (reduces boilerplate)
    double loadParamDouble(const std::string& name, double default_val);
    float loadParamFloat(const std::string& name, float default_val);
    bool loadParamBool(const std::string& name, bool default_val);

    /**
     * @brief Load joint initialization parameters from ROS2 parameter server
     */
    void loadJointInitParameters();

    /**
     * @brief Execute single cotton picking operation
     * @param position Cotton position to pick
     * @param home_j5 If true, homes J5 during retreat (default: true)
     * @param home_j3 If true, homes J3 during retreat (default: true)
     * @param home_j4 If true, homes J4 during retreat (default: true)
     * @return true if successful, false otherwise
     */
    bool pickCottonAtPosition(const CottonDetection& detection, bool home_j5 = true, bool home_j3 = true, bool home_j4 = true,
                              int64_t* approach_ms = nullptr, int64_t* capture_ms = nullptr, int64_t* retreat_ms = nullptr);

    /**
     * @brief Execute approach trajectory to cotton position
     * @param position Target position
     */
    bool executeApproachTrajectory(const geometry_msgs::msg::Point& position, int64_t* duration_ms = nullptr);

    /**
     * @brief Execute cotton capture sequence
     */
    bool executeCaptureSequence(int64_t* duration_ms = nullptr);

    /**
     * @brief Execute retreat trajectory after picking
     * @param home_j5 If true, homes J5 (extension) to retracted position (default: true)
     * @param home_j3 If true, homes J3 (rotation) to home position (default: true)
     * @param home_j4 If true, homes J4 (left/right) to center position (default: true)
     */
    bool executeRetreatTrajectory(bool home_j5 = true, bool home_j3 = true, bool home_j4 = true, int64_t* duration_ms = nullptr);

    /**
     * @brief Move L3 to parking position (tilted up, reduces motor heat)
     * SAFETY: Only call when J4 is at home position or won't move
     */
    void moveL3ToParking();

    /**
     * @brief Move L3 from parking to homing position (tilted down, creates clearance)
     * SAFETY: Must be called before any J4 movement
     */
    void moveL3ToHoming();

    /**
     * @brief Get current time in milliseconds
     */
    double getCurrentTimeMillis();

    /**
     * @brief Wait for joint to reach target position with feedback verification
     * @param joint_name Name of joint (e.g., "joint3", "joint4", "joint5")
     * @param target_position Target position in joint units
     * @return true if position reached within tolerance, false if timeout
     */
    bool waitForPositionFeedback(const std::string& joint_name, double target_position);

    /**
     * @brief Get current joint3 position from /joint_states topic
     * @return Current joint3 position in rotations, or -1.0 if not available
     */
    double getJoint3Position();

    /**
     * @brief Get current joint5 position from /joint_states topic
     * @return Current joint5 position in meters, or -1.0 if not available
     */
    double getJoint5Position();

public:
    /**
     * @brief Record a move_joint() result for per-joint failure tracking
     * On SUCCESS: reset consecutive counter for that joint
     * On TIMEOUT/ERROR: increment consecutive + cumulative counters
     * @param joint_id Joint number (3, 4, or 5)
     * @param result The MoveResult from move_joint()
     *
     * Public because YanthraMoveSystem::handleOperationalFailure() resets
     * per-joint counters after successful homing recovery (F5).
     */
    void recordMoveResult(int joint_id, MoveResult result);

    /**
     * @brief Get the motor availability service client (for diagnostic health checks)
     * @return Shared pointer to the Trigger service client, or nullptr if not created
     */
    rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr getMotorAvailabilityClient() const {
        return motor_availability_client_;
    }

    /**
     * @brief Get recovery manager for external access (e.g., YanthraMoveSystem counter resets)
     */
    RecoveryManager* getRecoveryManager() const { return recovery_manager_.get(); }
    TrajectoryPlanner* getTrajectoryPlanner() const { return trajectory_planner_.get(); }
};

}}  // namespace yanthra_move::core
