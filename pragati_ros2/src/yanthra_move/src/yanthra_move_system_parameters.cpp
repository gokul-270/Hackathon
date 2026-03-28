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

#include "yanthra_move/yanthra_move_system.hpp"

// System includes for parameter handling
#include <rclcpp/rclcpp.hpp>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>
#include <rcl_interfaces/msg/set_parameters_result.hpp>
#include <std_msgs/msg/string.hpp>
#include <cstdlib>  // for getenv, setenv
#include <cstdio>   // for sprintf
#include <unistd.h> // for getcwd

// Parameter-related method implementations
using namespace yanthra_move;

namespace yanthra_move {
    extern std::atomic<bool> simulation_mode;
}

// ==============================================
// PARAMETER VALIDATION METHODS
// ==============================================

rcl_interfaces::msg::ParameterDescriptor YanthraMoveSystem::createParameterDescriptor(
    const std::string& description,
    const std::string& additional_constraints,
    bool read_only) {
    rcl_interfaces::msg::ParameterDescriptor desc;
    desc.description = description;
    if (!additional_constraints.empty()) {
        desc.additional_constraints = additional_constraints;
    }
    desc.read_only = read_only;
    return desc;
}

rcl_interfaces::msg::ParameterDescriptor YanthraMoveSystem::createDoubleDescriptor(
    const std::string& description,
    double min_value,
    double max_value,
    const std::string& additional_constraints,
    bool read_only) {
    auto desc = createParameterDescriptor(description, additional_constraints, read_only);
    desc.type = rcl_interfaces::msg::ParameterType::PARAMETER_DOUBLE;
    desc.floating_point_range.resize(1);
    desc.floating_point_range[0].from_value = min_value;
    desc.floating_point_range[0].to_value = max_value;
    return desc;
}

rcl_interfaces::msg::ParameterDescriptor YanthraMoveSystem::createIntegerDescriptor(
    const std::string& description,
    int64_t min_value,
    int64_t max_value,
    const std::string& additional_constraints,
    bool read_only) {
    auto desc = createParameterDescriptor(description, additional_constraints, read_only);
    desc.type = rcl_interfaces::msg::ParameterType::PARAMETER_INTEGER;
    desc.integer_range.resize(1);
    desc.integer_range[0].from_value = min_value;
    desc.integer_range[0].to_value = max_value;
    return desc;
}

void YanthraMoveSystem::declareCoreOperationalParameters() {
    try {
        // Core operational parameters with validation
        node_->declare_parameter("continuous_operation", false,
            createParameterDescriptor("Enable continuous operation mode (vs single-cycle)",
                                    "SAFETY: Disable for testing to prevent infinite loops"));

        node_->declare_parameter("max_runtime_minutes", 0,
            createIntegerDescriptor("Maximum runtime in minutes (-1=infinite, 0=defaults: 1min single/30min continuous)",
                                  -1, 999,
                                  "SAFETY: Use -1 for infinite operation (dev/test only)"));

        node_->declare_parameter("save_logs", false,
            createParameterDescriptor("Enable detailed logging to files"));

        node_->declare_parameter("EndEffectorDropConveyor", false,
            createParameterDescriptor("Enable end effector conveyor drop functionality"));

        node_->declare_parameter("arm_calibration", false,
            createParameterDescriptor("Enable arm calibration mode",
                                    "WARNING: Only enable during maintenance"));

        node_->declare_parameter("parking_on", true,
            createParameterDescriptor("Enable automatic parking after operations",
                                    "SAFETY: Recommended to keep enabled"));

        node_->declare_parameter("reverse_endeffector", false,
            createParameterDescriptor("Reverse end effector rotation direction"));

        // Vision and processing parameters with constraints
        node_->declare_parameter("CAPTURE_MODE", 3,
            createIntegerDescriptor("Vision capture mode", 0, 5,
                                  "0=Off, 1=RGB, 2=Depth, 3=RGBD, 4=IR, 5=All"));

        node_->declare_parameter("YanthraDisparityShift", 15,
            createIntegerDescriptor("Disparity shift for depth processing", 0, 50));

        node_->declare_parameter("UsePostProcessingFilter", true,
            createParameterDescriptor("Enable post-processing filters for depth data"));

        node_->declare_parameter("UseThresholdFilter", false,
            createParameterDescriptor("Enable threshold filtering"));

        node_->declare_parameter("UseSpatialFilter", true,
            createParameterDescriptor("Enable spatial noise filtering"));

        node_->declare_parameter("SpatialFilterHoleFillingMode", 1,
            createIntegerDescriptor("Spatial filter hole filling mode", 0, 3));

        node_->declare_parameter("TemporalFilterPersistenceControl", 7,
            createIntegerDescriptor("Temporal filter persistence control", 1, 8));

        node_->declare_parameter("UseTemporalFilter", false,
            createParameterDescriptor("Enable temporal noise filtering"));

        node_->declare_parameter("PRAGATI_BYPASS_INTERNAL_PROCESSING", false,
            createParameterDescriptor("Bypass internal image processing",
                                    "DEVELOPMENT: Use for debugging"));

        node_->declare_parameter("YoloThreshold", 0.55,
            createDoubleDescriptor("YOLO detection confidence threshold", 0.1, 1.0));

        node_->declare_parameter("continuous_vacuum", true,
            createParameterDescriptor("Enable continuous vacuum operation"));

        // System control parameters
        node_->declare_parameter("YanthraLabCalibrationTesting", false,
            createParameterDescriptor("Enable laboratory calibration testing mode"));

        node_->declare_parameter("use_preloaded_centroids", false,
            createParameterDescriptor("Load centroid.txt directly instead of running ArUco detection"));

        node_->declare_parameter("enable_detection_retrigger", false,
            createParameterDescriptor("Re-trigger detection after each pick to validate remaining positions",
                                    "WARNING: Can cause deadlock if detection service times out - disabled by default"));

        node_->declare_parameter("enable_post_cycle_parking", false,
            createParameterDescriptor("Move to parking position after cycle (redundant if retreat homes all joints)",
                                    "OPTIMIZATION: Disabled saves ~800ms per cycle"));

        node_->declare_parameter("position_wait_mode", std::string("service"),
            createParameterDescriptor("Position wait mode after joint commands: 'service' (motor-confirmed), 'feedback' (poll /joint_states), 'blind_sleep' (distance-based estimate)",
                                    "Change to 'blind_sleep' on field if service mode has issues - no rebuild needed"));

        node_->declare_parameter("feedback_timeout", 5.0,
            createDoubleDescriptor("Timeout for feedback-based wait (seconds)", 0.5, 30.0,
                                  "Falls back to blind-sleep behavior if joint doesn't arrive within timeout"));

        node_->declare_parameter("enable_l3_idle_parking", true,
            createParameterDescriptor("Enable L3 idle parking for temperature optimization",
                                    "TEMPERATURE: L3 parks (tilts up) when idle to reduce motor heat"));

        // ═══════════════════════════════════════════════════════════════════════════
        // PHI-ANGLE COMPENSATION PARAMETERS
        // Corrects for mechanical/kinematic errors at different arm angles
        // ═══════════════════════════════════════════════════════════════════════════
        node_->declare_parameter("phi_compensation/enable", false,
            createParameterDescriptor("Enable phi-angle dependent compensation",
                                    "Corrects positioning errors that vary with arm elevation angle"));

        node_->declare_parameter("phi_compensation/zone1_max_deg", 30.0,
            createParameterDescriptor("Zone 1 upper boundary in degrees (0 to this value)"));

        node_->declare_parameter("phi_compensation/zone2_max_deg", 60.0,
            createParameterDescriptor("Zone 2 upper boundary in degrees (zone1_max to this value)"));

        node_->declare_parameter("phi_compensation/zone1_slope", 0.0,
            createParameterDescriptor("Zone 1 slope (rotations per normalized angle)"));

        node_->declare_parameter("phi_compensation/zone1_offset", 0.0,
            createParameterDescriptor("Zone 1 offset (rotations). Positive raises arm."));

        node_->declare_parameter("phi_compensation/zone2_slope", 0.0,
            createParameterDescriptor("Zone 2 slope (rotations per normalized angle)"));

        node_->declare_parameter("phi_compensation/zone2_offset", 0.0,
            createParameterDescriptor("Zone 2 offset (rotations)"));

        node_->declare_parameter("phi_compensation/zone3_slope", 0.0,
            createParameterDescriptor("Zone 3 slope (rotations per normalized angle)"));

        node_->declare_parameter("phi_compensation/zone3_offset", 0.0,
            createParameterDescriptor("Zone 3 offset (rotations). Negative lowers arm."));

        node_->declare_parameter("phi_compensation/l5_scale", 0.5,
            createParameterDescriptor("L5 extension scaling factor for compensation"));

        node_->declare_parameter("trigger_camera", true,
            createParameterDescriptor("Enable camera triggering"));

        node_->declare_parameter("global_vaccum_motor", true,
            createParameterDescriptor("Enable global vacuum motor control"));

        node_->declare_parameter("end_effector_enable", true,
            createParameterDescriptor("Enable end effector operations"));

        node_->declare_parameter("simulation_mode", false,
            createParameterDescriptor("Enable simulation mode (no hardware)",
                                    "DEVELOPMENT: Bypasses hardware interfaces"));

        node_->declare_parameter("skip_homing", false,
            createParameterDescriptor("Skip ODrive homing (motors pre-homed by MG6010)",
                                    "Use when MG6010 controller has already homed motors"));

        // Verification parameters
        node_->declare_parameter("use_simulation", false,
            createParameterDescriptor("Use simulation for testing"));

        node_->declare_parameter("enable_gpio", true,
            createParameterDescriptor("Enable GPIO hardware interfaces"));

        node_->declare_parameter("enable_camera", true,
            createParameterDescriptor("Enable camera hardware interfaces"));

        // Shutdown parameters
        node_->declare_parameter("shutdown_delay_minutes", 1,
            createParameterDescriptor("Delay in minutes before system poweroff (allows cancellation with 'sudo shutdown -c')",
                                    "SAFETY: Set to 0 for immediate shutdown, >0 for scheduled (cancellable)"));

        // Directory parameters (read-only after initialization)
        node_->declare_parameter("PRAGATI_INSTALL_DIR", "./",
            createParameterDescriptor("Installation directory path", "", true));

        // Error recovery thresholds (D3 escalation ladder)
        node_->declare_parameter("consecutive_failure_safe_mode_threshold", 3,
            createIntegerDescriptor(
                "Consecutive motor failures before entering safe mode", 1, 20,
                "SAFETY: Lower = faster escalation to safe mode"));

        node_->declare_parameter("retry_backoff_base_ms", 500,
            createIntegerDescriptor(
                "Base delay for exponential backoff on motor retries (ms)", 100, 5000,
                "Actual delay = base * 2^(attempt-1)"));

        // Safety watchdog timeouts
        node_->declare_parameter("ee_watchdog_timeout_sec", 600.0,
            createDoubleDescriptor(
                "Max seconds EE can stay ON before forced shutoff", 10.0, 3600.0,
                "SAFETY: Prevents EE overheat/burn if control loop stalls"));

        node_->declare_parameter("compressor_watchdog_timeout_sec", 900.0,
            createDoubleDescriptor(
                "Max seconds compressor can stay ON before forced shutoff", 30.0, 7200.0,
                "SAFETY: Prevents compressor overheat if stuck on"));

        node_->declare_parameter("pick_cycle_timeout_sec", 15.0,
            createDoubleDescriptor(
                "Max seconds for a single pick cycle before abort", 5.0, 60.0,
                "SAFETY: Prevents stuck pick cycles from blocking operation"));

        node_->declare_parameter("detection_service_timeout_sec", 2.0,
            createDoubleDescriptor(
                "Seconds to wait for detection service availability", 0.5, 10.0,
                "RESILIENCE: Configurable timeout for detection node crash detection"));

        RCLCPP_INFO(node_->get_logger(), "✅ Core operational parameters declared with validation");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to declare core parameters: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::declareTimingMotionParameters() {
    try {
        // Timing and delay parameters with safety constraints
        node_->declare_parameter("delays/picking", 0.200,
            createDoubleDescriptor("Cotton picking delay (seconds)", 0.05, 2.0,
                                 "SAFETY: Too low may cause mechanical damage"));

        node_->declare_parameter("delays/ee_pre_arrival_time", 0.2,
            createDoubleDescriptor("(Legacy) EE starts this many seconds BEFORE L5 reaches target", 0.0, 0.5));

        node_->declare_parameter("delays/ee_post_retract_time", 0.2,
            createDoubleDescriptor("(Legacy) EE stops this many seconds AFTER L5 starts retracting", 0.0, 0.5));

        // Position-based dynamic EE timing (NEW - preferred over time-based)
        node_->declare_parameter("delays/ee_start_distance", 0.025,
            createDoubleDescriptor("Start EE when J5 is this distance (m) from cotton target", 0.005, 0.250,
                                 "POSITION-BASED: Triggers EE based on actual motor position, not timing"));

        node_->declare_parameter("delays/ee_stop_distance", 0.050,
            createDoubleDescriptor("Stop EE when J5 retracts this distance (m) from cotton", 0.010, 0.250,
                                 "POSITION-BASED: Keeps EE running longer during retract for better fiber pull"));

        node_->declare_parameter("delays/use_dynamic_ee_prestart", false,
            createParameterDescriptor("Enable position-based dynamic EE timing vs sequential (EE after J5)",
                                    "TIMING: Dynamic mode uses position monitoring to start EE before J5 reaches target"));

        node_->declare_parameter("delays/EERunTimeDuringL5ForwardMovement", 2.0,
            createDoubleDescriptor("End effector forward movement time (s)", 0.1, 10.0,
                                 "OPTIMIZED: ROS-1 used 0.25s, can go lower for speed"));

        node_->declare_parameter("delays/EERunTimeDuringL5BackwardMovement", 0.5,
            createDoubleDescriptor("End effector backward movement time (s)", 0.1, 5.0));

        node_->declare_parameter("delays/EERunTimeDuringReverseRotation", 0.5,
            createDoubleDescriptor("End effector reverse rotation time (s)", 0.1, 3.0));
        node_->declare_parameter("delays/ee_post_joint5_delay", 0.3,
            createDoubleDescriptor("Delay after joint5 completes before EE starts (s)", 0.0, 2.0));

        // Motion control parameters with safety limits
        node_->declare_parameter("min_sleep_time_formotor_motion", 0.2,
            createDoubleDescriptor("Minimum sleep time for motor motion (s)", 0.05, 2.0,
                                 "SAFETY: Prevents excessive motor stress. OPTIMIZED: 0.2s tested on RPi"));

        node_->declare_parameter("inter_joint_delay", 0.3,
            createDoubleDescriptor("Delay between sequential joint movements (s)", 0.0, 2.0,
                                 "TIMING: Prevents mechanical stress from simultaneous movements"));

        node_->declare_parameter("cotton_settle_delay", 0.2,
            createDoubleDescriptor("Delay before compressor burst to let cotton settle (s)", 0.0, 2.0,
                                 "TIMING: Set to 0 to disable cotton settling wait"));

        node_->declare_parameter("compressor_burst_duration", 0.5,
            createDoubleDescriptor("Duration to run compressor for cotton drop (s)", 0.1, 3.0,
                                 "HARDWARE: Depends on pneumatic system response time"));

        node_->declare_parameter("enable_cotton_eject", false);

        node_->declare_parameter("enable_compressor_eject", false,
            createParameterDescriptor("Gate all compressor activation (default: off, M2 roller is primary eject)"));

        node_->declare_parameter("j3_eject_position", -0.2,
            createDoubleDescriptor("J3 angle during cotton eject (rotations)", -0.2, 0.0,
                                 "HARDWARE: Do not exceed J3 min limit (-0.2 rot = 72 deg)"));

        node_->declare_parameter("ee_motor2_eject_duration_ms", 300.0,
            createDoubleDescriptor("Duration to run M2 in reverse during eject (ms)", 50.0, 2000.0,
                                 "TUNING: Adjust based on cotton type and ejection effectiveness"));

        node_->declare_parameter("ee_motor2_forward_flush_ms", 200.0,
            createDoubleDescriptor("Duration to run M2 forward after eject to clear belt entrance (ms)", 0.0, 1000.0,
                                 "TUNING: Short pulse clears residual fibers; 0 to disable flush"));

        node_->declare_parameter("j3_eject_feedback_timeout_sec", 1.5,
            createDoubleDescriptor("Max wait for J3 CAN position feedback before M2 fires anyway (s)", 0.5, 10.0,
                                 "TUNING: Graceful degradation timeout; increase if CAN bus is slow"));

        node_->declare_parameter("stats_log_interval_sec", 30.0,
            createDoubleDescriptor("Periodic stats logging interval (s), 0 to disable", 0.0, 300.0,
                                 "MONITORING: Logs system stats (uptime, cycles, cotton picked) periodically"));

        node_->declare_parameter("l2_homing_sleep_time", 6.0,
            createDoubleDescriptor("L2 homing sleep time (s)", 1.0, 15.0));

        node_->declare_parameter("l2_step_sleep_time", 5.0,
            createDoubleDescriptor("L2 step sleep time (s)", 1.0, 15.0));

        node_->declare_parameter("l2_idle_sleep_time", 2.0,
            createDoubleDescriptor("L2 idle sleep time (s)", 0.5, 10.0));

        node_->declare_parameter("joint_velocity", 1.0,
            createDoubleDescriptor("Default joint velocity", 0.1, 5.0,
                                 "SAFETY: Higher values may cause instability"));

        // Joint poses (array parameter)
        node_->declare_parameter("joint_poses", std::vector<double>{0.00001, 0.00001, 1.5708},
            createParameterDescriptor("Default joint positions [rad]",
                                    "Format: [joint1, joint2, joint3]"));

        // Jerk control parameters
        node_->declare_parameter("jerk_enabled_theta", false,
            createParameterDescriptor("Enable jerk control for theta joint"));

        node_->declare_parameter("jerk_enabled_phi", false,
            createParameterDescriptor("Enable jerk control for phi joint"));

        // Hardware timeout and thresholds with safety limits
        node_->declare_parameter("hardware_timeout", 1200000.0,
            createDoubleDescriptor("Hardware operation timeout (ms)", 10000.0, 3600000.0,
                                 "SAFETY: Prevents infinite hardware waits"));

        node_->declare_parameter("cotton_capture_detect_wait_time", 0.0,
            createDoubleDescriptor("Cotton capture detection wait time (s)", 0.0, 5.0,
                                 "TIMING: Set to 0 since EE activation now happens in approach"));

        // Field of view parameters (read-only, calibrated values)
        node_->declare_parameter("fov_theta_max", 0.3926,
            createDoubleDescriptor("Maximum theta field of view (rad)", 0.1, 1.57,
                                 "CALIBRATED: Do not change without recalibration", true));

        node_->declare_parameter("fov_phi_max", 0.3926,
            createDoubleDescriptor("Maximum phi field of view (rad)", 0.1, 1.57,
                                 "CALIBRATED: Do not change without recalibration", true));

        // Height scanning parameters
        node_->declare_parameter("height_scan_enable", true,
            createParameterDescriptor("Enable height scanning functionality"));

        node_->declare_parameter("height_scan_min", 0.01,
            createDoubleDescriptor("Minimum scan height (m)", 0.001, 0.5));

        node_->declare_parameter("height_scan_max", 1.0,
            createDoubleDescriptor("Maximum scan height (m)", 0.1, 2.0));

        node_->declare_parameter("height_scan_step", 0.2,
            createDoubleDescriptor("Height scan step size (m)", 0.01, 0.5));

        // Picking order optimization strategy
        // Options: "none", "nearest_first", "phi_sweep", "hierarchical", "raster_scan"
        node_->declare_parameter("picking_strategy", "raster_scan",
            createParameterDescriptor("Picking order optimization strategy",
                "Options: none (detection order), nearest_first (greedy), "
                "phi_sweep (minimize base rotation), hierarchical (2D energy-optimal), "
                "raster_scan (serpentine rows - default)"));

        RCLCPP_INFO(node_->get_logger(), "✅ Timing and motion parameters declared with validation");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to declare timing/motion parameters: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::declareJointInitParameters() {
    try {
        // Joint 2 initialization parameters
        node_->declare_parameter("joint2_init/height_scan_enable", false,
            createParameterDescriptor("Enable height scanning for joint 2"));

        node_->declare_parameter("joint2_init/min", 0.01,
            createDoubleDescriptor("Joint 2 minimum position (m)", 0.001, 0.5,
                                 "SAFETY: Physical limit constraint"));

        node_->declare_parameter("joint2_init/max", 0.85,
            createDoubleDescriptor("Joint 2 maximum position (m)", 0.1, 1.0,
                                 "SAFETY: Physical limit constraint"));

        node_->declare_parameter("joint2_init/step", 0.125,
            createDoubleDescriptor("Joint 2 step size (m)", 0.01, 0.3));

        // Joint 3 initialization parameters (phi - vertical revolute)
        // NOTE: park_position removed 2025-11-28 - homing_position used for both home and park
        node_->declare_parameter("joint3_init/homing_position", 0.00001,
            createDoubleDescriptor("Joint 3 homing position (rad)", -0.1, 0.1,
                                 "SAFETY: Near-zero position for homing"));

        node_->declare_parameter("joint3_init/multiple_zero_poses", true,
            createParameterDescriptor("Enable multiple zero poses for joint 3"));

        node_->declare_parameter("joint3_init/zero_poses", std::vector<double>{0.261799},
            createParameterDescriptor("Joint 3 zero positions (rad)",
                                    "CALIBRATED: Multiple valid zero positions"));

        // Joint 4 initialization parameters (theta - horizontal revolute)
        // NOTE: park_position removed 2025-11-28 - homing_position used for both home and park
        node_->declare_parameter("joint4_init/homing_position", 0.00001,
            createDoubleDescriptor("Joint 4 homing position (rad)", -0.1, 0.1,
                                 "SAFETY: Near-zero position for homing"));

        node_->declare_parameter("joint4_init/multiple_zero_poses", false,
            createParameterDescriptor("Enable multiple zero poses for joint 4"));

        node_->declare_parameter("joint4_init/theta_jerk_value", 0.0,
            createDoubleDescriptor("Joint 4 theta jerk value", 0.0, 10.0));

        node_->declare_parameter("joint4_init/zero_poses", std::vector<double>{0.0},
            createParameterDescriptor("Joint 4 zero positions (rad)"));

        // Joint 5 initialization parameters (prismatic)
        // NOTE: park_position removed 2025-11-28 - homing_position used for both home and park
        node_->declare_parameter("joint5_init/homing_position", 0.00001,
            createDoubleDescriptor("Joint 5 homing position (m)", -0.1, 0.01,
                                 "SAFETY: Near-zero position for homing"));

        node_->declare_parameter("joint5_init/end_effector_len", 0.085,
            createDoubleDescriptor("End effector length (m)", 0.01, 0.2,
                                 "HARDWARE: Physical measurement", true));

        node_->declare_parameter("joint5_init/joint5_vel_limit", 2.0,
            createDoubleDescriptor("Joint 5 velocity limit (m/s)", 0.1, 5.0,
                                 "SAFETY: Maximum safe velocity"));

        // NOTE: min_length/max_length removed - limits enforced by motor_control (config/production.yaml)

        node_->declare_parameter("joint5_init/gear_ratio", 20.943951,
            createDoubleDescriptor("Joint 5 gear ratio", 1.0, 100.0,
                                 "HARDWARE: Mechanical specification", true));

        node_->declare_parameter("joint5_init/phi_jerk_value", 0.0,
            createDoubleDescriptor("Joint 5 phi jerk value", 0.0, 10.0));

        node_->declare_parameter("joint5_init/hardware_offset", 0.320,
            createDoubleDescriptor("Physical hardware offset from motor zero to joint origin (meters)", 0.0, 1.0,
                                  "HARDWARE: Measured distance, default 320mm"));

        RCLCPP_INFO(node_->get_logger(), "✅ Joint initialization parameters declared with validation");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to declare joint parameters: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::declareMultiPositionScanParameters() {
    try {
        // ═══════════════════════════════════════════════════════════════════════════
        // JOINT4 MULTI-POSITION SCANNING PARAMETERS
        // Enables scanning multiple J4 positions to increase camera FOV coverage
        // ═══════════════════════════════════════════════════════════════════════════

        node_->declare_parameter("joint4_multiposition/enabled", false,
            createParameterDescriptor("Enable J4 multi-position scanning for wider FOV coverage"));

        node_->declare_parameter("joint4_multiposition/positions",
            std::vector<double>{-0.100, -0.050, 0.000, 0.050, 0.100},
            createParameterDescriptor("J4 scan positions in meters, relative to center"));

        node_->declare_parameter("joint4_multiposition/safe_min", -0.175,
            createDoubleDescriptor("J4 safety minimum position (meters)", -0.200, 0.0,
                                  "SAFETY: Must not exceed mechanical limit"));

        node_->declare_parameter("joint4_multiposition/safe_max", 0.175,
            createDoubleDescriptor("J4 safety maximum position (meters)", 0.0, 0.200,
                                  "SAFETY: Must not exceed mechanical limit"));

        node_->declare_parameter("joint4_multiposition/scan_strategy", "left_to_right",
            createParameterDescriptor("Scan order: left_to_right, right_to_left, or as_configured"));

        node_->declare_parameter("joint4_multiposition/j4_settling_time", 0.100,
            createDoubleDescriptor("Wait for TF to stabilize after J4 movement (seconds)", 0.0, 1.0));

        node_->declare_parameter("joint4_multiposition/detection_settling_time", 0.050,
            createDoubleDescriptor("Wait for camera fresh frame after J4 move (seconds)", 0.0, 1.0,
                                  "TUNING: 30fps camera = 33ms/frame, set >= 1 frame time"));

        node_->declare_parameter("joint4_multiposition/early_exit_enabled", true,
            createParameterDescriptor("Skip remaining positions if no cotton found at current position"));

        node_->declare_parameter("joint4_multiposition/on_j4_failure", "skip_position",
            createParameterDescriptor("Error strategy: skip_position, abort_cycle, or fallback_single"));

        node_->declare_parameter("joint4_multiposition/enable_timing_stats", true,
            createParameterDescriptor("Log per-position timing data for optimization"));

        node_->declare_parameter("joint4_multiposition/enable_position_stats", true,
            createParameterDescriptor("Track which scan positions find cotton most often"));

        node_->declare_parameter("joint4_multiposition/enable_j4_offset_compensation", true,
            createParameterDescriptor("Apply J4 offset correction to theta calculation"));

        RCLCPP_INFO(node_->get_logger(), "✅ Multi-position scan parameters declared with validation");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to declare multi-position scan parameters: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::declareCollisionAvoidanceParameters() {
    try {
        // ═══════════════════════════════════════════════════════════════════════════
        // J5 COLLISION AVOIDANCE PARAMETERS
        // Dynamically limits J5 extension based on J3 angle for two-arm setups
        // ═══════════════════════════════════════════════════════════════════════════

        node_->declare_parameter("j5_collision_avoidance/enabled", true,
            createParameterDescriptor("Enable J5 collision avoidance for two-arm setups"));

        node_->declare_parameter("j5_collision_avoidance/clearance", 0.20,
            createDoubleDescriptor("J5 collision clearance in meters (D/2 - hw_offset - margin)",
                                   0.05, 0.50,
                                   "SAFETY: Depends on measured base-to-base distance"));

        RCLCPP_INFO(node_->get_logger(), "✅ J5 collision avoidance parameters declared");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(),
            "Failed to declare collision avoidance parameters: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::declareStartSwitchParameters() {
    try {
        // START_SWITCH parameters with enhanced validation
        node_->declare_parameter("start_switch.timeout_sec", 5.0,
            createDoubleDescriptor("Seconds to wait for START_SWITCH (-1=infinite, >0=timeout)",
                                 -1.0, 3600.0, "SAFETY: Use -1 for production with operator, >0 for automated testing"));

        node_->declare_parameter("start_switch.enable_wait", true,
            createParameterDescriptor("Enable waiting for START_SWITCH (set false for dev/CI environments)",
                                    "DEVELOPMENT: Disable for automated testing"));

        node_->declare_parameter("start_switch.prefer_topic", true,
            createParameterDescriptor("Prefer topic over GPIO for START_SWITCH (easier for testing)",
                                    "TESTING: Topic allows remote/automated triggering"));

        RCLCPP_INFO(node_->get_logger(), "✅ START_SWITCH parameters declared with validation");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to declare START_SWITCH parameters: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::validateAllParameters() {
    try {
        RCLCPP_INFO(node_->get_logger(), "🔍 Validating all parameters for safety and consistency...");

        // Cross-parameter validation
        auto height_min = node_->get_parameter("height_scan_min").as_double();
        auto height_max = node_->get_parameter("height_scan_max").as_double();
        auto height_step = node_->get_parameter("height_scan_step").as_double();

        if (height_min >= height_max) {
            RCLCPP_ERROR(node_->get_logger(), "VALIDATION ERROR: height_scan_min (%.3f) >= height_scan_max (%.3f)", height_min, height_max);
            throw std::runtime_error("Invalid height scan range");
        }

        if (height_step > (height_max - height_min)) {
            RCLCPP_WARN(node_->get_logger(), "WARNING: height_scan_step (%.3f) is very large for range [%.3f, %.3f]",
                       height_step, height_min, height_max);
        }

        // NOTE: Joint 5 length validation removed - limits enforced by motor_control node

        // Joint 2 position validation
        auto joint2_min = node_->get_parameter("joint2_init/min").as_double();
        auto joint2_max = node_->get_parameter("joint2_init/max").as_double();

        if (joint2_min >= joint2_max) {
            RCLCPP_ERROR(node_->get_logger(), "VALIDATION ERROR: joint2_min (%.3f) >= joint2_max (%.3f)",
                        joint2_min, joint2_max);
            throw std::runtime_error("Invalid joint2 position range");
        }

        // Safety validation for continuous operation
        auto continuous = node_->get_parameter("continuous_operation").as_bool();
        auto start_switch_enabled = node_->get_parameter("start_switch.enable_wait").as_bool();

        if (continuous && !start_switch_enabled) {
            RCLCPP_WARN(node_->get_logger(), "SAFETY WARNING: continuous_operation enabled but start_switch.enable_wait disabled");
            RCLCPP_WARN(node_->get_logger(), "This may cause uncontrolled continuous operation!");
        }

        // Timing validation
        auto picking_delay = node_->get_parameter("delays/picking").as_double();
        auto min_sleep = node_->get_parameter("min_sleep_time_formotor_motion").as_double();

        if (picking_delay < min_sleep) {
            RCLCPP_WARN(node_->get_logger(), "WARNING: picking_delay (%.3f) < min_sleep_time (%.3f) - may cause motor stress",
                       picking_delay, min_sleep);
        }

        // Log parameter count for verification
        auto param_names = node_->list_parameters({}, 0).names;
        RCLCPP_INFO(node_->get_logger(), "📊 Validated %zu parameters total", param_names.size());

        // Log safety-critical parameters
        RCLCPP_INFO(node_->get_logger(), "🔒 Safety-critical parameters:");
        RCLCPP_INFO(node_->get_logger(), "   continuous_operation: %s", continuous ? "ENABLED" : "disabled");
        RCLCPP_INFO(node_->get_logger(), "   start_switch.enable_wait: %s", start_switch_enabled ? "ENABLED" : "disabled");
        RCLCPP_INFO(node_->get_logger(), "   simulation_mode: %s",
                   node_->get_parameter("simulation_mode").as_bool() ? "ENABLED" : "disabled");

        RCLCPP_INFO(node_->get_logger(), "✅ All parameter validation completed successfully");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "❌ Parameter validation failed: %s", e.what());
        throw;
    }
}

void YanthraMoveSystem::installParameterValidationCallback() {
    try {
        // Install runtime parameter validation callback
        auto param_callback_handle = node_->add_on_set_parameters_callback(
            std::bind(&YanthraMoveSystem::onParameterChange, this, std::placeholders::_1));

        RCLCPP_INFO(node_->get_logger(), "✅ Runtime parameter validation callback installed");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "❌ Failed to install parameter validation callback: %s", e.what());
        throw;
    }
}

rcl_interfaces::msg::SetParametersResult YanthraMoveSystem::onParameterChange(
    const std::vector<rclcpp::Parameter>& parameters) {

    rcl_interfaces::msg::SetParametersResult result;
    result.successful = true;
    result.reason = "";

    // Phase 4: Track parameter changes for hot reloading
    std::vector<std::string> changed_params;

    for (const auto& param : parameters) {
        const std::string& name = param.get_name();

        try {
            // Validate based on parameter name and type
            if (name == "start_switch.timeout_sec") {
                if (param.get_type() == rclcpp::ParameterType::PARAMETER_DOUBLE) {
                    double value = param.as_double();
                    if (value < 1.0 || value > 30.0) {
                        result.successful = false;
                        result.reason = "start_switch.timeout_sec must be between 1.0 and 30.0 seconds";
                        RCLCPP_ERROR(node_->get_logger(), "❌ Parameter validation failed: %s", result.reason.c_str());
                        break;
                    }
                    changed_params.push_back(name);
                }
            } else if (name == "delays/picking") {
                if (param.get_type() == rclcpp::ParameterType::PARAMETER_DOUBLE) {
                    double value = param.as_double();
                    if (value < 0.05 || value > 2.0) {
                        result.successful = false;
                        result.reason = "delays/picking must be between 0.05 and 2.0 seconds";
                        RCLCPP_ERROR(node_->get_logger(), "❌ Parameter validation failed: %s", result.reason.c_str());
                        break;
                    }
                    changed_params.push_back(name);
                }
            } else if (name == "joint2_init/min") {
                if (param.get_type() == rclcpp::ParameterType::PARAMETER_DOUBLE) {
                    double value = param.as_double();
                    if (value < 0.001 || value > 0.5) {
                        result.successful = false;
                        result.reason = "joint2_init/min must be between 0.001 and 0.5 meters";
                        RCLCPP_ERROR(node_->get_logger(), "❌ Parameter validation failed: %s", result.reason.c_str());
                        break;
                    }
                    changed_params.push_back(name);
                }
            } else if (name == "joint2_init/max") {
                if (param.get_type() == rclcpp::ParameterType::PARAMETER_DOUBLE) {
                    double value = param.as_double();
                    if (value < 0.1 || value > 1.0) {
                        result.successful = false;
                        result.reason = "joint2_init/max must be between 0.1 and 1.0 meters";
                        RCLCPP_ERROR(node_->get_logger(), "❌ Parameter validation failed: %s", result.reason.c_str());
                        break;
                    }
                    changed_params.push_back(name);
                }
            // NOTE: joint3_init/park_position validation removed 2025-11-28
            } else if (name.find("PRAGATI_INSTALL_DIR") != std::string::npos) {
                // Read-only parameter protection
                result.successful = false;
                result.reason = "PRAGATI_INSTALL_DIR is read-only and cannot be modified at runtime";
                RCLCPP_ERROR(node_->get_logger(), "❌ Attempted to modify read-only parameter: %s", name.c_str());
                break;
            } else {
                // For parameters not explicitly validated, track the change
                changed_params.push_back(name);
            }

            // If we reach here, the parameter passed validation
            if (result.successful) {
                RCLCPP_DEBUG(node_->get_logger(), "✅ Parameter %s validated successfully", name.c_str());
            }

        } catch (const std::exception& e) {
            result.successful = false;
            result.reason = "Parameter validation exception: " + std::string(e.what());
            RCLCPP_ERROR(node_->get_logger(), "❌ Parameter validation exception for %s: %s",
                        name.c_str(), e.what());
            break;
        }
    }

    if (result.successful) {
        // Phase 4: Apply hot reloading for accepted parameters
        for (const auto& param_name : changed_params) {
            applyParameterHotReload(param_name);
        }

        // Publish parameter change notifications
        publishParameterChangeNotifications(changed_params);

        RCLCPP_INFO(node_->get_logger(), "🔄 Hot-reloaded %zu parameters successfully", changed_params.size());
    }

    return result;
}

void YanthraMoveSystem::applyParameterHotReload(const std::string& param_name) {
    try {
        RCLCPP_INFO(node_->get_logger(), "🔄 Hot-reloading parameter: %s", param_name.c_str());

        // Phase 4: Apply specific hot reload logic based on parameter type
        if (param_name == "start_switch.timeout_sec") {
            // Update START_SWITCH timeout immediately
            double new_timeout = node_->get_parameter(param_name).as_double();
            // The timeout is already updated in the node parameter - notify components
            RCLCPP_INFO(node_->get_logger(), "🔄 START_SWITCH timeout updated to %.1f seconds", new_timeout);

        } else if (param_name.find("delays/") == 0) {
            // Update timing parameters - these affect motion controller behavior
            double new_value = node_->get_parameter(param_name).as_double();

            // Update motion controller with new timing
            if (motion_controller_) {
                // Notify motion controller of timing changes
                RCLCPP_INFO(node_->get_logger(), "🔄 Motion timing parameter %s updated to %.3f",
                           param_name.c_str(), new_value);
                // Motion controller will pick up new values from parameter server
            }

        } else if (param_name.find("joint") == 0) {
            // Update joint parameters - these affect joint initialization and limits
            // NOTE: park_position handling removed 2025-11-28 - only homing_position used now
            if (param_name.find("min") != std::string::npos || param_name.find("max") != std::string::npos) {
                double new_limit = node_->get_parameter(param_name).as_double();
                RCLCPP_INFO(node_->get_logger(), "🔄 Joint limit %s updated to %.3f",
                           param_name.c_str(), new_limit);
            }

        } else if (param_name == "continuous_operation") {
            bool new_continuous = node_->get_parameter(param_name).as_bool();
            continuous_operation_.store(new_continuous);
            RCLCPP_INFO(node_->get_logger(), "🔄 Continuous operation mode: %s",
                       new_continuous ? "ENABLED" : "DISABLED");

            // Safety check: warn if continuous operation enabled without start switch wait
            bool start_wait = node_->get_parameter("start_switch.enable_wait").as_bool();
            if (new_continuous && !start_wait) {
                RCLCPP_WARN(node_->get_logger(), "⚠️ SAFETY WARNING: Continuous operation enabled without start switch wait!");
            }

        } else if (param_name == "simulation_mode") {
            bool new_simulation = node_->get_parameter(param_name).as_bool();
            simulation_mode_.store(new_simulation);
            RCLCPP_INFO(node_->get_logger(), "🔄 Simulation mode: %s",
                       new_simulation ? "ENABLED" : "DISABLED");
        }

        // Record the time of this parameter change for monitoring
        parameter_change_count_.fetch_add(1);
        {
            std::lock_guard<std::mutex> lock(parameter_time_mutex_);
            last_parameter_change_time_ = std::chrono::steady_clock::now();
        }

    } catch (const std::exception& e) {
        hot_reload_failure_count_.fetch_add(1);
        RCLCPP_ERROR(node_->get_logger(),
            "{\"event\":\"hot_reload_failure\","
            "\"parameter\":\"%s\","
            "\"consecutive_failures\":%u,"
            "\"error\":\"%s\"}",
            param_name.c_str(), hot_reload_failure_count_.load(), e.what());
    }
}

void YanthraMoveSystem::publishParameterChangeNotifications(const std::vector<std::string>& changed_params) {
    if (changed_params.empty()) return;

    try {
        // Phase 4: Publish parameter change notifications for monitoring
        if (!parameter_change_pub_) {
            // Create parameter change notification publisher if it doesn't exist
            parameter_change_pub_ = node_->create_publisher<std_msgs::msg::String>(
                "/yanthra_move/parameter_changes", 10);
        }

        // Create notification message
        auto msg = std::make_unique<std_msgs::msg::String>();
        std::string notification = "Parameter changes: ";
        for (size_t i = 0; i < changed_params.size(); ++i) {
            notification += changed_params[i];
            if (i < changed_params.size() - 1) {
                notification += ", ";
            }
        }

        msg->data = notification;
        parameter_change_pub_->publish(*msg);

        RCLCPP_INFO(node_->get_logger(), "📢 Published parameter change notification: %s",
                   notification.c_str());

    } catch (const std::exception& e) {
        hot_reload_failure_count_.fetch_add(1);
        RCLCPP_ERROR(node_->get_logger(),
            "{\"event\":\"parameter_notification_failure\","
            "\"consecutive_failures\":%u,"
            "\"error\":\"%s\"}",
            hot_reload_failure_count_.load(), e.what());
    }
}

// ==============================================

void YanthraMoveSystem::loadParameters() {
    // Get parameters - use current working directory as default
    char cwd[1024];
    if (getcwd(cwd, sizeof(cwd)) != NULL) {
        pragati_install_dir_ = std::string(cwd) + "/";
    } else {
        pragati_install_dir_ = "./";  // Fallback to relative path
    }

    pragati_install_dir_ = node_->get_parameter("PRAGATI_INSTALL_DIR").as_string();

    // Ensure no double slashes: remove trailing slash if present before adding paths
    if (!pragati_install_dir_.empty() && pragati_install_dir_.back() == '/') {
        pragati_install_dir_.pop_back();
    }
    pragati_input_dir_ = pragati_install_dir_ + "/inputs/";
    pragati_output_dir_ = pragati_install_dir_ + "/outputs/";

    RCLCPP_INFO(node_->get_logger(), "PRAGATI_INSTALL_DIR: %s", pragati_install_dir_.c_str());
    RCLCPP_INFO(node_->get_logger(), "PRAGATI_OUTPUT_DIR: %s", pragati_output_dir_.c_str());
    RCLCPP_INFO(node_->get_logger(), "PRAGATI_INPUT_DIR: %s", pragati_input_dir_.c_str());

    // Read system parameters
    yanthra_lab_calibration_testing_ = node_->get_parameter("YanthraLabCalibrationTesting").as_bool();
    use_preloaded_centroids_ = node_->get_parameter("use_preloaded_centroids").as_bool();
    trigger_camera_ = node_->get_parameter("trigger_camera").as_bool();
    global_vacuum_motor_ = node_->get_parameter("global_vaccum_motor").as_bool();
    end_effector_enable_ = node_->get_parameter("end_effector_enable").as_bool();
    simulation_mode_.store(node_->get_parameter("simulation_mode").as_bool());

    // Update global simulation_mode for compatibility with existing code
    yanthra_move::simulation_mode.store(simulation_mode_.load());

    // Parameters expected by verification script
    bool use_simulation = node_->get_parameter("use_simulation").as_bool();
    bool enable_gpio = node_->get_parameter("enable_gpio").as_bool();
    bool enable_camera = node_->get_parameter("enable_camera").as_bool();

    RCLCPP_INFO(node_->get_logger(), "System parameters - Trigger_Camera: %d, Global_vacuum_motor: %d, End_effector_enable: %d, simulation_mode: %d",
                trigger_camera_, global_vacuum_motor_, end_effector_enable_, simulation_mode_.load());

    RCLCPP_INFO(node_->get_logger(), "Verification parameters - use_simulation: %d, enable_gpio: %d, enable_camera: %d",
                use_simulation, enable_gpio, enable_camera);

    // Read operational parameters
    continuous_operation_.store(node_->get_parameter("continuous_operation").as_bool());
    max_runtime_minutes_ = node_->get_parameter("max_runtime_minutes").as_int();
    save_logs_ = node_->get_parameter("save_logs").as_bool();
    end_effector_drop_conveyor_ = node_->get_parameter("EndEffectorDropConveyor").as_bool();
    picking_delay_ = node_->get_parameter("delays/picking").as_double();
    shutdown_delay_minutes_ = node_->get_parameter("shutdown_delay_minutes").as_int();

    RCLCPP_INFO(node_->get_logger(), "Shutdown delay: %d minute(s) %s",
                shutdown_delay_minutes_,
                shutdown_delay_minutes_ > 0 ? "(cancellable with 'sudo shutdown -c')" : "(immediate)");

    // Log runtime timeout configuration
    if (max_runtime_minutes_ == -1) {
        RCLCPP_INFO(node_->get_logger(), "Maximum runtime: INFINITE (no timeout)");
    } else if (max_runtime_minutes_ == 0) {
        RCLCPP_INFO(node_->get_logger(), "Maximum runtime: DEFAULT (1min single-cycle / 30min continuous)");
    } else {
        RCLCPP_INFO(node_->get_logger(), "Maximum runtime: %d minutes", max_runtime_minutes_);
    }

    RCLCPP_INFO(node_->get_logger(), "Operational parameters loaded successfully");

    // Error recovery thresholds (D3)
    consecutive_failure_safe_mode_threshold_ =
        node_->get_parameter("consecutive_failure_safe_mode_threshold").as_int();
    retry_backoff_base_ms_ =
        node_->get_parameter("retry_backoff_base_ms").as_int();
    RCLCPP_INFO(node_->get_logger(),
        "Error recovery: safe_mode_threshold=%d, backoff_base=%dms",
        consecutive_failure_safe_mode_threshold_, retry_backoff_base_ms_);

    // Safety watchdog timeouts
    ee_watchdog_timeout_sec_ =
        static_cast<float>(node_->get_parameter("ee_watchdog_timeout_sec").as_double());
    compressor_watchdog_timeout_sec_ =
        static_cast<float>(node_->get_parameter("compressor_watchdog_timeout_sec").as_double());
    RCLCPP_INFO(node_->get_logger(),
        "Safety watchdog: ee_timeout=%.0fs, compressor_timeout=%.0fs",
        ee_watchdog_timeout_sec_, compressor_watchdog_timeout_sec_);

    // Pick cycle timeout (applied later in initializeModularComponents after
    // motion_controller_ is created; loadParameters() runs before it exists)
    pick_cycle_timeout_sec_ = node_->get_parameter("pick_cycle_timeout_sec").as_double();
    RCLCPP_INFO(node_->get_logger(),
        "Pick cycle timeout: %.1fs", pick_cycle_timeout_sec_);

    // Detection service timeout
    detection_service_timeout_sec_ =
        node_->get_parameter("detection_service_timeout_sec").as_double();
    RCLCPP_INFO(node_->get_logger(),
        "Detection service timeout: %.1fs", detection_service_timeout_sec_);
}
void YanthraMoveSystem::declareAllParameters() {
    RCLCPP_INFO(node_->get_logger(), "📋 Declaring parameters with comprehensive validation...");

    // Phase 2: Modular parameter declaration with validation
    declareCoreOperationalParameters();
    declareTimingMotionParameters();
    declareJointInitParameters();
    declareMultiPositionScanParameters();
    declareCollisionAvoidanceParameters();
    declareStartSwitchParameters();

    // Install runtime parameter validation callback
    installParameterValidationCallback();

    // Validate all parameters after declaration
    validateAllParameters();

    RCLCPP_INFO(node_->get_logger(), "✅ All parameters declared and validated successfully");

    // Phase 3: Initialize error recovery systems
    initializeErrorRecovery();
}
