/*
 * Copyright (c) 2024 Pragati Robotics
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @file mg6010_controller_node.cpp
 * @brief Production motor controller node for MG6010 motors
 *
 * This is the main production controller node that manages MG6010 motors.
 * Provides ROS interface for multi-motor control, homing, and state publishing.
 * Stack: ROS Topics/Services -> MotorControllerInterface -> MG6010Controller -> MG6010Protocol -> CAN
 */

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <rclcpp_lifecycle/lifecycle_publisher.hpp>
#include <lifecycle_msgs/msg/state.hpp>
#include <lifecycle_msgs/msg/transition.hpp>
#include "motor_control_ros2/mg6010_controller.hpp"
#include "motor_control_ros2/mg6010_can_interface.hpp"
#include "motor_control_ros2/motor_abstraction.hpp"
#include "motor_control_ros2/safety_monitor.hpp"
#include "motor_control_ros2/motor_absence.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"
#include "motor_control_ros2/simulation/motor_sim_config.hpp"
#include "motor_control_ros2/motor_test_suite.hpp"
#include "motor_control_ros2/control_loop_manager.hpp"
#include "motor_control_ros2/ros_interface_manager.hpp"
#include "motor_control_ros2/role_strategy.hpp"
#include "motor_control_ros2/motor_manager.hpp"
#include "motor_control_ros2/shutdown_handler.hpp"
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <std_srvs/srv/set_bool.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <diagnostic_msgs/msg/diagnostic_status.hpp>
#include <diagnostic_msgs/msg/key_value.hpp>

#include "motor_control_msgs/srv/joint_position_command.hpp"
#include "motor_control_msgs/srv/read_pid.hpp"
#include "motor_control_msgs/srv/write_pid.hpp"
#include "motor_control_msgs/srv/write_pid_to_rom.hpp"
#include "motor_control_msgs/srv/motor_command.hpp"
#include "motor_control_msgs/srv/motor_lifecycle.hpp"
#include "motor_control_msgs/srv/read_motor_limits.hpp"
#include "motor_control_msgs/srv/write_motor_limits.hpp"
#include "motor_control_msgs/srv/read_encoder.hpp"
#include "motor_control_msgs/srv/write_encoder_zero.hpp"
#include "motor_control_msgs/srv/read_motor_angles.hpp"
#include "motor_control_msgs/srv/clear_motor_errors.hpp"
#include "motor_control_msgs/srv/read_motor_state.hpp"

#include <rclcpp_action/rclcpp_action.hpp>
#include "motor_control_msgs/action/step_response_test.hpp"
#include "motor_control_msgs/action/joint_position_command.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"

#include <iostream>
#include <sstream>
#include <iomanip>
#include <memory>
#include <thread>
#include <chrono>
#include <vector>
#include <array>
#include <algorithm>
#include <atomic>
#include <mutex>
#include <condition_variable>
#include <cmath>
#include <csignal>
#include <nlohmann/json.hpp>
#include <common_utils/signal_handler.hpp>
#include <common_utils/json_logging.hpp>
#include "git_version.h"

using namespace motor_control_ros2;

// Smart polling configuration
// MAX_MOTORS is defined in motor_control_ros2/motor_test_suite.hpp (namespace motor_control_ros2)
// Available here via 'using namespace motor_control_ros2;' above
// Note: busy timeout is runtime-configurable via ROS params (smart_polling.busy_timeout_s)

class MG6010ControllerNode : public rclcpp_lifecycle::LifecycleNode
{
public:
  using CallbackReturn = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;

  MG6010ControllerNode()
  : LifecycleNode("motor_control")
  {
    RCLCPP_INFO(this->get_logger(), "🔧 Motor Control Node Starting...");
    if (std::string(GIT_HASH).empty()) {
        RCLCPP_INFO(this->get_logger(), "   Built: %s", getBuildTimestamp());
    } else {
        RCLCPP_INFO(this->get_logger(), "   Built: %s (%s on %s)",
                     getBuildTimestamp(), GIT_HASH, GIT_BRANCH);
    }

    // Declare parameters with empty/zero defaults to allow YAML override
    this->declare_parameter<std::string>("interface_name", "can0");
    this->declare_parameter<int>("baud_rate", 500000);
    this->declare_parameter<std::vector<int64_t>>("motor_ids", std::vector<int64_t>());  // Empty default - YAML MUST provide
    this->declare_parameter<std::vector<std::string>>("joint_names", std::vector<std::string>());  // Empty default - YAML MUST provide
    this->declare_parameter<std::string>("role", "");  // "arm" or "vehicle" - auto-detect if empty
    this->declare_parameter<std::vector<std::string>>("joint_types", std::vector<std::string>());  // "prismatic" or "revolute" per joint
    this->declare_parameter<std::vector<double>>("homing_positions", std::vector<double>());  // Operational start positions
    this->declare_parameter<std::vector<double>>("packing_positions", std::vector<double>());  // Shutdown positions (ready for transport)
    this->declare_parameter<std::vector<double>>("transmission_factors", std::vector<double>());  // Per-joint transmission factors
    this->declare_parameter<std::vector<double>>("internal_gear_ratios", std::vector<double>());  // Per-joint internal gear ratios
    this->declare_parameter<std::vector<int64_t>>("directions", std::vector<int64_t>());  // Per-joint directions
    this->declare_parameter<std::string>("test_mode", "multi_motor");  // New default mode
    this->declare_parameter<double>("target_position", 1.57);  // 90 degrees
    this->declare_parameter<double>("control_frequency", 10.0);  // 10 Hz control loop
    this->declare_parameter<std::vector<double>>("min_positions", std::vector<double>());  // Joint limit minimums
    this->declare_parameter<std::vector<double>>("max_positions", std::vector<double>());  // Joint limit maximums

    // Optional per-joint reach detection parameters (often used by higher-level nodes)
    // If present, we reuse them for motion_feedback defaults.
    this->declare_parameter<std::vector<double>>("position_tolerance", std::vector<double>());
    this->declare_parameter<double>("position_timeout", -1.0);

    // Degraded mode parameters
    // NOTE: skip_motors is NOT declared here - will be loaded from YAML only if present
    this->declare_parameter<bool>("degraded_mode.enabled", true);  // Allow partial motor operation
    this->declare_parameter<int>("degraded_mode.min_drive_motors", 2);  // Minimum drive motors
    this->declare_parameter<int>("degraded_mode.min_steering_motors", 2);  // Minimum steering motors
    this->declare_parameter<int>("degraded_mode.max_init_failures", 1);  // Max failures at init

    // Health monitoring parameters (runtime safety with bypass options)
    this->declare_parameter<bool>("health_monitoring.enabled", true);  // Master ON/OFF
    this->declare_parameter<bool>("health_monitoring.auto_disable_on_failure", true);  // Auto-disable
    this->declare_parameter<bool>("health_monitoring.log_only_mode", false);  // Field bypass - never disable
    this->declare_parameter<int>("health_monitoring.consecutive_failure_threshold", 3);  // Failures before action

    // Smart polling parameters
    // Set enabled=false to force full polling (useful for bus-off reproduction tests)
    this->declare_parameter<bool>("smart_polling.enabled", true);
    this->declare_parameter<double>("smart_polling.busy_timeout_s", 5.0);

    // Motion feedback (target reached detection)
    // When enabled, we poll commanded motors at a low rate and:
    //  - publish a more realistic /joint_states position while busy
    //  - emit "reached target" logs
    //  - power higher-level logic without arbitrary sleep() timeouts
    this->declare_parameter<bool>("motion_feedback.enabled", true);
    this->declare_parameter<double>("motion_feedback.poll_hz", 5.0);
    this->declare_parameter<bool>("motion_feedback.publish_actual_while_busy", true);
    this->declare_parameter<double>("motion_feedback.position_tolerance", 0.01);
    this->declare_parameter<double>("motion_feedback.settle_time_s", 0.20);
    // If < 0, defaults to smart_polling.busy_timeout_s
    this->declare_parameter<double>("motion_feedback.timeout_s", -1.0);

    // Shutdown behavior
    // Default to graceful parking for arm safety (prevents arm drop on power loss)
    this->declare_parameter<bool>("shutdown.enable_packing", true);  // true = park + move to packing position; false = park only
    this->declare_parameter<double>("shutdown.max_duration_s", 10.0);  // CHANGED: allow more time for parking
    this->declare_parameter<double>("shutdown.position_tolerance", 0.02);  // Position tolerance for parking verification
    this->declare_parameter<double>("shutdown.poll_interval_ms", 100.0);  // Polling interval during parking

    // Collision interlock parameters (prevent J4 commands when J3 is in parking zone)
    this->declare_parameter<bool>("enable_j3_j4_collision_interlock", true);
    this->declare_parameter<double>("j3_parking_position", 0.0);   // J3 parking position (rotations)
    this->declare_parameter<double>("j3_parking_tolerance", 5.0);  // Tolerance band (degrees)

    // Auto-recovery parameter
    this->declare_parameter<bool>("auto_recover_errors", true);

    // Simulation mode parameter (D4: matches YanthraMoveSystem convention)
    this->declare_parameter<bool>("simulation_mode", false);

    // Thermal derating parameters (task 3.1)
    this->declare_parameter<double>("thermal_derating.derating_onset_temp", 65.0);
    this->declare_parameter<double>("thermal_derating.thermal_limit_temp", 85.0);
    this->declare_parameter<double>("thermal_derating.min_derating_pct", 0.0);
    this->declare_parameter<double>("thermal_derating.thermal_hysteresis", 5.0);

    // Stall detection parameters (task 4.6)
    this->declare_parameter<double>("stall_detection.stall_current_threshold", 0.8);
    this->declare_parameter<double>("stall_detection.stall_position_threshold_deg", 0.5);
    this->declare_parameter<int>("stall_detection.stall_time_threshold_ms", 500);

    // Motor absence detection parameters (task 4.7)
    this->declare_parameter<int>("motor_absence.failure_threshold", 5);
    this->declare_parameter<int>("motor_absence.initial_backoff_ms", 1000);
    this->declare_parameter<int>("motor_absence.max_backoff_ms", 30000);
    this->declare_parameter<double>("motor_absence.backoff_multiplier", 2.0);

    // Auto-activate parameter: when true, main() will auto-configure+activate after construction
    this->declare_parameter<bool>("auto_activate", true);
  }

  CallbackReturn on_configure(const rclcpp_lifecycle::State &) override
  {
    // Get parameters
    std::string interface_name = this->get_parameter("interface_name").as_string();
    int baud_rate = this->get_parameter("baud_rate").as_int();
    simulation_mode_ = this->get_parameter("simulation_mode").as_bool();
    auto motor_ids_param = this->get_parameter("motor_ids").as_integer_array();
    auto joint_names = this->get_parameter("joint_names").as_string_array();
    auto joint_types_param = this->get_parameter("joint_types").as_string_array();
    auto homing_positions_deg = this->get_parameter("homing_positions").as_double_array();
    auto packing_positions_param = this->get_parameter("packing_positions").as_double_array();
    auto transmission_factors = this->get_parameter("transmission_factors").as_double_array();
    auto internal_gear_ratios = this->get_parameter("internal_gear_ratios").as_double_array();
    auto directions_param = this->get_parameter("directions").as_integer_array();
    auto position_tolerance_param = this->get_parameter("position_tolerance").as_double_array();
    double position_timeout_s = this->get_parameter("position_timeout").as_double();
    std::string test_mode = this->get_parameter("test_mode").as_string();
    double target_position = this->get_parameter("target_position").as_double();
    double control_frequency = this->get_parameter("control_frequency").as_double();

    // Position limits from YAML (task 4.1)
    auto min_positions_param = this->get_parameter("min_positions").as_double_array();
    auto max_positions_param = this->get_parameter("max_positions").as_double_array();
    if (min_positions_param.empty() || max_positions_param.empty()) {
      RCLCPP_WARN(this->get_logger(),
        "min_positions/max_positions not configured in YAML — using safe defaults (+-90 deg)");
    }

    // Get degraded mode parameters
    // Handle skip_motors carefully - ROS2 has issues with empty arrays
    std::vector<std::string> skip_motors;
    if (this->has_parameter("skip_motors")) {
      try {
        skip_motors = this->get_parameter("skip_motors").as_string_array();
      } catch (const std::exception& e) {
        RCLCPP_WARN(this->get_logger(), "Failed to load skip_motors parameter: %s. Using empty list.", e.what());
        skip_motors = std::vector<std::string>();
      }
    }
    bool degraded_mode_enabled = this->get_parameter("degraded_mode.enabled").as_bool();
    int min_drive_motors = this->get_parameter("degraded_mode.min_drive_motors").as_int();
    int min_steering_motors = this->get_parameter("degraded_mode.min_steering_motors").as_int();
    int max_init_failures = this->get_parameter("degraded_mode.max_init_failures").as_int();

    // Get health monitoring parameters
    health_monitoring_enabled_ = this->get_parameter("health_monitoring.enabled").as_bool();
    auto_disable_on_failure_ = this->get_parameter("health_monitoring.auto_disable_on_failure").as_bool();
    log_only_mode_ = this->get_parameter("health_monitoring.log_only_mode").as_bool();
    failure_threshold_ = this->get_parameter("health_monitoring.consecutive_failure_threshold").as_int();

    // Get smart polling parameters
    smart_polling_enabled_ = this->get_parameter("smart_polling.enabled").as_bool();
    double busy_timeout_s = this->get_parameter("smart_polling.busy_timeout_s").as_double();

    // Get collision interlock parameters
    interlock_enabled_ = this->get_parameter("enable_j3_j4_collision_interlock").as_bool();
    j3_parking_position_ = this->get_parameter("j3_parking_position").as_double();
    j3_parking_tolerance_ = this->get_parameter("j3_parking_tolerance").as_double();
    if (!interlock_enabled_) {
        RCLCPP_WARN(this->get_logger(),
            "{\"event\":\"collision_interlock_disabled\","
            "\"warning\":\"J3-J4 collision interlock is DISABLED via parameter\"}");
    }

    // Auto-recovery parameter
    bool auto_recover = this->get_parameter("auto_recover_errors").as_bool();

    // Thermal derating parameters (task 3.1)
    double td_onset = this->get_parameter("thermal_derating.derating_onset_temp").as_double();
    double td_limit = this->get_parameter("thermal_derating.thermal_limit_temp").as_double();
    double td_min_pct = this->get_parameter("thermal_derating.min_derating_pct").as_double();
    double td_hysteresis = this->get_parameter("thermal_derating.thermal_hysteresis").as_double();
    RCLCPP_INFO(this->get_logger(),
      "Thermal derating: onset=%.1f°C, limit=%.1f°C, min_pct=%.2f, hysteresis=%.1f°C",
      td_onset, td_limit, td_min_pct, td_hysteresis);

    // Stall detection parameters (task 4.6)
    double sd_current = this->get_parameter("stall_detection.stall_current_threshold").as_double();
    double sd_position = this->get_parameter("stall_detection.stall_position_threshold_deg").as_double();
    int sd_time_ms = this->get_parameter("stall_detection.stall_time_threshold_ms").as_int();
    RCLCPP_INFO(this->get_logger(),
      "Stall detection: current_threshold=%.2f, position_threshold=%.1f°, time_threshold=%dms",
      sd_current, sd_position, sd_time_ms);

    // Motor absence detection parameters (task 4.7)
    absence_config_.failure_threshold =
      this->get_parameter("motor_absence.failure_threshold").as_int();
    absence_config_.initial_backoff_ms =
      this->get_parameter("motor_absence.initial_backoff_ms").as_int();
    absence_config_.max_backoff_ms =
      this->get_parameter("motor_absence.max_backoff_ms").as_int();
    absence_config_.backoff_multiplier =
      this->get_parameter("motor_absence.backoff_multiplier").as_double();
    RCLCPP_INFO(this->get_logger(),
      "Motor absence detection: threshold=%d, initial_backoff=%dms, max_backoff=%dms, multiplier=%.1f",
      absence_config_.failure_threshold, absence_config_.initial_backoff_ms,
      absence_config_.max_backoff_ms, absence_config_.backoff_multiplier);

    if (busy_timeout_s < 0.0) {
      RCLCPP_WARN(this->get_logger(), "smart_polling.busy_timeout_s < 0; clamping to 0");
      busy_timeout_s = 0.0;
    }
    motor_busy_timeout_ = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(busy_timeout_s));

    // Motion feedback configuration
    motion_feedback_enabled_ = this->get_parameter("motion_feedback.enabled").as_bool();
    motion_feedback_publish_actual_while_busy_ = this->get_parameter("motion_feedback.publish_actual_while_busy").as_bool();
    motion_feedback_poll_hz_ = this->get_parameter("motion_feedback.poll_hz").as_double();
    motion_feedback_position_tolerance_ = this->get_parameter("motion_feedback.position_tolerance").as_double();

    double settle_s = this->get_parameter("motion_feedback.settle_time_s").as_double();
    if (settle_s < 0.0) {
      RCLCPP_WARN(this->get_logger(), "motion_feedback.settle_time_s < 0; clamping to 0");
      settle_s = 0.0;
    }
    motion_feedback_settle_time_ = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(settle_s));

    double timeout_s = this->get_parameter("motion_feedback.timeout_s").as_double();
    if (timeout_s < 0.0) {
      // Prefer explicit position_timeout (if configured) over busy_timeout.
      if (position_timeout_s > 0.0) {
        timeout_s = position_timeout_s;
      } else {
        timeout_s = busy_timeout_s;  // fallback aligned with existing busy timeout behavior
      }
    }
    if (timeout_s < 0.0) {
      timeout_s = 0.0;
    }
    motion_feedback_timeout_ = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(timeout_s));

    if (motion_feedback_poll_hz_ <= 0.0) {
      if (motion_feedback_enabled_) {
        RCLCPP_WARN(this->get_logger(), "motion_feedback.poll_hz <= 0; disabling motion feedback");
      }
      motion_feedback_enabled_ = false;
    }

    // Initialize motion tracking state
    for (size_t i = 0; i < MAX_MOTORS; ++i) {
      motion_pending_[i] = false;
      motion_in_tolerance_[i] = false;
      last_feedback_valid_[i] = false;

      // Default per-motor tolerance to the scalar tolerance.
      motion_feedback_position_tolerance_by_motor_[i] = motion_feedback_position_tolerance_;

      pos_cmd_received_[i] = 0;
      pos_cmd_sent_ok_[i] = 0;
      pos_cmd_sent_fail_[i] = 0;
      pos_cmd_reached_ok_[i] = 0;
      pos_cmd_reached_timeout_[i] = 0;
    }

    // If position_tolerance[] is provided (same ordering as joint_names/motor_ids), use it.
    for (size_t i = 0; i < motor_ids_param.size() && i < MAX_MOTORS; ++i) {
      if (i < position_tolerance_param.size()) {
        motion_feedback_position_tolerance_by_motor_[i] = position_tolerance_param[i];
      }
    }

    // Initialize motor availability and failure tracking
    for (size_t i = 0; i < MAX_MOTORS; ++i) {
      motor_available_[i] = true;        // Default to available
      motor_enabled_flags_[i] = true;   // Default to enabled (updated by services)
      motor_failure_count_[i] = 0;
      motor_last_error_[i] = "";
    }

    // Log health monitoring config
    RCLCPP_INFO(this->get_logger(), "Health Monitoring: enabled=%s, auto_disable=%s, log_only=%s, threshold=%d",
                health_monitoring_enabled_ ? "true" : "false",
                auto_disable_on_failure_ ? "true" : "false",
                log_only_mode_ ? "true" : "false",
                failure_threshold_);

    // Validate parameter array sizes
    if (motor_ids_param.size() != joint_names.size()) {
      RCLCPP_ERROR(this->get_logger(), "motor_ids and joint_names must be the same length (%zu vs %zu)",
                   motor_ids_param.size(), joint_names.size());
      return CallbackReturn::FAILURE;
    }

    // Convert motor IDs
    std::vector<uint8_t> motor_ids;
    for (auto id : motor_ids_param) {
      motor_ids.push_back(static_cast<uint8_t>(id));
    }

    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════");
    RCLCPP_INFO(this->get_logger(), "🔧 MG6010 Multi-Motor Controller (ROS 2 Interface)");
    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════");
    RCLCPP_INFO(this->get_logger(), " ");  // Blank line for readability
    RCLCPP_INFO(this->get_logger(), "Configuration:");
    RCLCPP_INFO(this->get_logger(), "  CAN Interface: %s", interface_name.c_str());
    RCLCPP_INFO(this->get_logger(), "  CAN Bitrate (expected): %d (SocketCAN configured externally)", baud_rate);
    RCLCPP_INFO(this->get_logger(), "  Motor Count: %zu", motor_ids.size());
    RCLCPP_INFO(this->get_logger(), "  Test Mode: %s", test_mode.c_str());
    RCLCPP_INFO(this->get_logger(), "  Control Frequency: %.1f Hz", control_frequency);
    RCLCPP_INFO(this->get_logger(), "  Smart Polling: enabled=%s, busy_timeout=%.3fs",
                smart_polling_enabled_ ? "true" : "false",
                std::chrono::duration_cast<std::chrono::duration<double>>(motor_busy_timeout_).count());

    RCLCPP_INFO(this->get_logger(), "  Motion Feedback: enabled=%s, poll_hz=%.2f, tol=%.4f, settle=%.3fs, timeout=%.3fs, publish_actual_while_busy=%s",
                motion_feedback_enabled_ ? "true" : "false",
                motion_feedback_poll_hz_,
                motion_feedback_position_tolerance_,
                std::chrono::duration_cast<std::chrono::duration<double>>(motion_feedback_settle_time_).count(),
                std::chrono::duration_cast<std::chrono::duration<double>>(motion_feedback_timeout_).count(),
                motion_feedback_publish_actual_while_busy_ ? "true" : "false");
    RCLCPP_INFO(this->get_logger(), " ");  // Blank line for readability

    // Initialize CAN interface (shared by all motors)
    if (simulation_mode_) {
      // Simulation mode: use ConfigurableMockCANInterface with physics simulation (D1, D3)
      sim_can_interface_ = std::make_shared<test::ConfigurableMockCANInterface>();
      sim_can_interface_->initialize("sim_can0", baud_rate);
      can_interface_ = sim_can_interface_;

      // Enable physics simulation for each configured motor (D5)
      for (size_t i = 0; i < motor_ids.size(); ++i) {
        uint8_t motor_id = static_cast<uint8_t>(motor_ids[i]);
        test::MotorSimConfig sim_config;
        // NOTE: position_min/max_deg are in MOTOR degrees (after gear ratio).
        // Node params min/max_positions are in JOINT rotations — wrong unit space.
        // Keep MotorSimConfig defaults (±3600 motor degrees = ±10 joint rotations
        // at IGR=1.0) which cover the practical simulation range.
        // Use fast velocity for simulation so actions complete within timeout.
        // Default 360 dps is too slow for multi-turn targets through the
        // internal gear ratio (e.g. 10 rotations at IGR=1 = 3,600 motor degrees).
        sim_config.velocity_max_dps = 36000.0;
        sim_config.settling_time_constant_ms = 50.0;
        sim_can_interface_->enable_motor_simulation(motor_id, sim_config);
      }

      // Create 10ms wall timer to advance physics (D3)
      sim_physics_timer_ = this->create_wall_timer(
        std::chrono::milliseconds(10),
        [this]() {
          sim_can_interface_->advance_time(std::chrono::milliseconds(10));
        });

      can_available_ = true;
      RCLCPP_INFO(this->get_logger(),
        "{\"event\":\"can_init_simulation\",\"motors\":%zu}",
        motor_ids.size());
      RCLCPP_INFO(this->get_logger(),
        "CAN interface initialized in SIMULATION mode — no hardware required");
    } else {
      // Hardware mode: use real MG6010CANInterface
      can_interface_ = std::make_shared<MG6010CANInterface>();
      if (!can_interface_->initialize(interface_name, baud_rate)) {
        RCLCPP_ERROR(this->get_logger(),
          "{\"event\":\"can_init_failed\",\"interface\":\"%s\",\"error\":\"%s\"}",
          interface_name.c_str(), can_interface_->get_last_error().c_str());
        RCLCPP_ERROR(this->get_logger(),
          "CAN interface initialization failed in hardware mode — cannot proceed");
        return CallbackReturn::FAILURE;
      } else {
        RCLCPP_INFO(this->get_logger(), "✅ CAN interface initialized");
        can_available_ = true;

        // C1 fix: Register connection status callback for CAN disconnect/reconnect logging
        // These methods are MG6010CANInterface-specific (not in CANInterface base class)
        auto hw_can = std::dynamic_pointer_cast<MG6010CANInterface>(can_interface_);
        if (hw_can) {
          hw_can->setConnectionStatusCallback(
            [this, hw_can](bool connected) {
              if (connected) {
                RCLCPP_INFO(this->get_logger(),
                  "{\"event\":\"can_reconnected\",\"interface\":\"%s\"}",
                  hw_can->get_interface_name().c_str());
              } else {
                RCLCPP_WARN(this->get_logger(),
                  "{\"event\":\"can_disconnected\",\"interface\":\"%s\"}",
                  hw_can->get_interface_name().c_str());
              }
            });
        }
      }
    }

    // Create role strategy from 'role' parameter (or auto-detect from joint_names)
    {
      std::string role_param = this->get_parameter("role").as_string();
      if (role_param == "arm") {
        role_strategy_ = std::make_shared<ArmRoleStrategy>();
      } else if (role_param == "vehicle") {
        role_strategy_ = std::make_shared<VehicleRoleStrategy>();
      } else if (role_param.empty()) {
        // TODO(cleanup): Remove auto-detect after v1.0 field trial — require explicit role param
        // Auto-detect from joint_names (deprecated path)
        bool has_j3 = false, has_j4 = false, has_j5 = false;
        bool has_steering = false, has_drive = false;
        for (const auto & jn : joint_names) {
          if (jn == "joint3") has_j3 = true;
          if (jn == "joint4") has_j4 = true;
          if (jn == "joint5") has_j5 = true;
          if (jn.find("steering") != std::string::npos) has_steering = true;
          if (jn.find("drive") != std::string::npos) has_drive = true;
        }
        if (has_j3 && has_j4 && has_j5) {
          RCLCPP_WARN(this->get_logger(),
            "Auto-detected role as 'arm' from joint names. This is deprecated — "
            "please add 'role: arm' to your config YAML.");
          role_strategy_ = std::make_shared<ArmRoleStrategy>();
        } else if (has_steering || has_drive) {
          RCLCPP_WARN(this->get_logger(),
            "Auto-detected role as 'vehicle' from joint names. This is deprecated — "
            "please add 'role: vehicle' to your config YAML.");
          role_strategy_ = std::make_shared<VehicleRoleStrategy>();
        } else {
          // No recognizable pattern — default to arm (safe: no drive/steering logic)
          RCLCPP_WARN(this->get_logger(),
            "Cannot auto-detect role from joint names; defaulting to 'arm'. "
            "Please add 'role: arm' or 'role: vehicle' to your config YAML.");
          role_strategy_ = std::make_shared<ArmRoleStrategy>();
        }
      } else {
        throw std::invalid_argument(
          "Invalid role '" + role_param + "': must be 'arm' or 'vehicle'");
      }
      RCLCPP_INFO(this->get_logger(), "Role strategy: %s", role_strategy_->roleType().c_str());
    }

    // Initialize all motors (skip if CAN not available)
    size_t init_failures = 0;
    size_t steering_count = 0;
    size_t drive_count = 0;

    if (!can_available_) {
      RCLCPP_WARN(this->get_logger(), "⚠️ Skipping motor initialization (no CAN interface)");
      // Populate placeholder entries so joint_names_/controllers_ indexing is consistent
      for (size_t i = 0; i < motor_ids.size(); ++i) {
        std::string joint_name = (i < joint_names.size()) ? joint_names[i] : "joint_" + std::to_string(i);
        joint_names_.push_back(joint_name);
        controllers_.push_back(nullptr);
        homing_positions_.push_back(0.0);
        packing_positions_.push_back(0.0);
        if (i < MAX_MOTORS) {
          motor_available_[i] = false;
          motor_enabled_flags_[i] = false;
        }
        init_failures++;
      }
    } else {

    for (size_t i = 0; i < motor_ids.size(); ++i) {
      uint8_t node_id = motor_ids[i];
      std::string joint_name = (i < joint_names.size()) ? joint_names[i] : "joint_" + std::to_string(i);
      double transmission_factor = (i < transmission_factors.size()) ? transmission_factors[i] : 1.0;
      double internal_gear_ratio = (i < internal_gear_ratios.size()) ? internal_gear_ratios[i] : 1.0;
      int direction = (i < directions_param.size()) ? static_cast<int>(directions_param[i]) : 1;

      // Check if this motor should be skipped
      bool should_skip = false;
      for (const auto& skip_name : skip_motors) {
        if (joint_name == skip_name) {
          RCLCPP_WARN(this->get_logger(), "⏭️  Skipping motor %s (in skip_motors list)", joint_name.c_str());
          should_skip = true;
          if (i < MAX_MOTORS) motor_available_[i] = false;
          init_failures++;
          break;
        }
      }
      if (should_skip) {
        // Still need to add placeholder for joint_names_ indexing
        joint_names_.push_back(joint_name);
        controllers_.push_back(nullptr);  // Null controller for skipped motor
        homing_positions_.push_back(0.0);
        packing_positions_.push_back(0.0);  // Also add packing position placeholder
        if (i < MAX_MOTORS) motor_enabled_flags_[i] = false;
        continue;
      }

      // Create motor configuration
      MotorConfiguration config;
      config.motor_type = "mg6010";
      config.joint_name = joint_name;
      config.can_id = node_id;
      config.axis_id = i;
      config.transmission_factor = transmission_factor;
      config.joint_offset = 0.0;
      config.encoder_offset = 0.0;
      config.encoder_resolution = 16384;
      config.direction = direction;

      // Store baud rate in motor_params for bookkeeping/debugging (CAN interface is configured separately)
      config.motor_params["baud_rate"] = static_cast<double>(baud_rate);
      config.motor_params["internal_gear_ratio"] = internal_gear_ratio;
      config.motor_params["auto_recover_errors"] = auto_recover ? 1.0 : 0.0;

      RCLCPP_INFO(this->get_logger(), "  %s: transmission=%.1f, internal_gear=%.1f, direction=%d",
                  joint_name.c_str(), transmission_factor, internal_gear_ratio, direction);
      config.p_gain = 100.0;
      config.v_gain = 0.5;
      config.v_int_gain = 1.0;
      config.current_limit = 8.0;
      config.velocity_limit = 15.0;

      // Safety limits — wire from YAML min_positions/max_positions (task 4.1)
      // Defaults are ±90° (safe finite fallback) if YAML not provided
      if (i < min_positions_param.size()) {
        config.limits.position_min = min_positions_param[i];
      }
      if (i < max_positions_param.size()) {
        config.limits.position_max = max_positions_param[i];
      }
      RCLCPP_INFO(this->get_logger(), "  %s limits: [%.4f, %.4f]",
                  joint_name.c_str(), config.limits.position_min, config.limits.position_max);
      config.limits.velocity_max = 15.0;
      config.limits.current_max = 8.0;
      config.limits.temperature_max = 85.0;

      // Create controller via MotorControllerInterface
      auto controller = std::make_shared<MG6010Controller>();

      if (!controller->initialize(config, can_interface_)) {
        RCLCPP_ERROR(this->get_logger(), "❌ Failed to initialize motor %d (%s)", node_id, joint_name.c_str());
        if (i < MAX_MOTORS) {
          motor_available_[i] = false;
          motor_enabled_flags_[i] = false;
        }
        init_failures++;
        // Add placeholder to maintain indexing
        controllers_.push_back(nullptr);
        joint_names_.push_back(joint_name);
        homing_positions_.push_back(0.0);
        packing_positions_.push_back(0.0);  // Also add packing position placeholder
        continue;
      }

      controllers_.push_back(controller);
      joint_names_.push_back(joint_name);  // Store joint name
      if (i < MAX_MOTORS) motor_enabled_flags_[i] = true;
      RCLCPP_INFO(this->get_logger(), "✅ Motor %d initialized: %s", node_id, joint_name.c_str());

      // Configure thermal derating and stall detection (tasks 3.1, 4.6)
      controller->configureThermalDerating(td_onset, td_limit, td_min_pct, td_hysteresis);
      controller->configureStallDetection(sd_current, sd_position, sd_time_ms);

      // Track motor type for degraded mode validation
      if (role_strategy_ && role_strategy_->isSteeringMotor(joint_name)) {
        steering_count++;
      } else if (role_strategy_ && role_strategy_->isDriveMotor(joint_name)) {
        drive_count++;
      }

      // Store homing position (for reference)
      if (i < homing_positions_deg.size()) {
        homing_positions_.push_back(homing_positions_deg[i]);
      } else {
        homing_positions_.push_back(0.0);
      }

      // Store packing position (for safe shutdown)
      // Falls back to homing position if packing not specified
      if (i < packing_positions_param.size()) {
        packing_positions_.push_back(packing_positions_param[i]);
      } else if (i < homing_positions_deg.size()) {
        packing_positions_.push_back(homing_positions_deg[i]);  // Fallback to homing
      } else {
        packing_positions_.push_back(0.0);
      }

      // Perform homing sequence for this motor
      if (i < homing_positions_deg.size()) {
        perform_motor_homing(controller, i, joint_name, homing_positions_deg[i]);
      }
    }
    }  // end else (can_available_)

    // Build revolute-joint flag vector for rotations→radians conversion on /joint_states.
    // URDF revolute joints expect radians in sensor_msgs/JointState, but motor_control
    // stores revolute positions in rotations internally.  Prismatic joints are already
    // in meters and need no conversion.
    joint_is_revolute_.resize(joint_names_.size(), false);
    for (size_t i = 0; i < joint_names_.size(); ++i) {
      if (i < joint_types_param.size() && joint_types_param[i] == "revolute") {
        joint_is_revolute_[i] = true;
      }
    }

    // Count actually available motors
    size_t available_motors = 0;
    for (size_t i = 0; i < controllers_.size(); ++i) {
      if (controllers_[i] != nullptr) available_motors++;
    }

    RCLCPP_INFO(this->get_logger(), "✅ Initialized %zu / %zu motors", available_motors, motor_ids.size());

    // Check degraded mode requirements
    if (degraded_mode_enabled) {
      bool can_operate = true;
      std::string degraded_reason;

      // Vehicle-specific validation: only enforce steering/drive minimums if this config
      // actually uses vehicle-style joint naming (contains "steering" or "drive").
      const bool has_vehicle_roles = (steering_count > 0 || drive_count > 0);
      if (!has_vehicle_roles && (min_drive_motors > 0 || min_steering_motors > 0)) {
        RCLCPP_INFO(this->get_logger(),
                    "ℹ️ Degraded-mode drive/steering checks skipped (no 'drive'/'steering' joints configured)");
      }

      if (has_vehicle_roles) {
        if (steering_count < static_cast<size_t>(min_steering_motors)) {
          can_operate = false;
          degraded_reason = "Not enough steering motors: " + std::to_string(steering_count) +
                           " < " + std::to_string(min_steering_motors);
        }
        if (drive_count < static_cast<size_t>(min_drive_motors)) {
          can_operate = false;
          degraded_reason = "Not enough drive motors: " + std::to_string(drive_count) +
                           " < " + std::to_string(min_drive_motors);
        }
      }

      if (init_failures > static_cast<size_t>(max_init_failures)) {
        can_operate = false;
        degraded_reason = "Too many init failures: " + std::to_string(init_failures) +
                         " > " + std::to_string(max_init_failures);
      }

      if (init_failures > 0 && can_operate) {
        RCLCPP_WARN(this->get_logger(), "⚠️ DEGRADED MODE: %zu motor(s) failed, continuing with %zu available",
                    init_failures, available_motors);
        if (has_vehicle_roles) {
          RCLCPP_WARN(this->get_logger(), "   Steering: %zu, Drive: %zu", steering_count, drive_count);
        }
        degraded_mode_active_ = true;
      } else if (!can_operate) {
        RCLCPP_ERROR(this->get_logger(), "❌ Cannot operate: %s", degraded_reason.c_str());
        // Continue anyway in ROS mode (services should still be available for diagnostics)
      }
    } else if (init_failures > 0) {
      RCLCPP_ERROR(this->get_logger(), "❌ %zu motor(s) failed and degraded_mode disabled", init_failures);
    }

    RCLCPP_INFO(this->get_logger(), " ");  // Blank line for readability

    // Create SafetyMonitor and wire controllers for e-stop execution
    safety_monitor_ = std::make_shared<SafetyMonitor>(
        this->get_node_base_interface(),
        this->get_node_logging_interface(),
        this->get_node_parameters_interface(),
        this->get_node_topics_interface(),
        this->get_node_services_interface()
    );
    safety_monitor_->set_controllers(controllers_);
    safety_monitor_->activate();
    RCLCPP_INFO(this->get_logger(), "SafetyMonitor activated with %zu controllers",
                controllers_.size());

    // NOTE: When GenericHWInterface is loaded via ros2_control controller_manager,
    // the SafetyMonitor should be wired into it via:
    //   hw_interface->set_safety_monitor(safety_monitor_);
    // This enables the write() safety gate in the ros2_control command path.
    // Currently, this node manages motors directly (not via ros2_control),
    // so the wiring is prepared but not active until ros2_control integration.

    // Create ROS 2 interface if in multi_motor mode
    // IMPORTANT: Always setup interface even with 0 motors so services are available

    // Construct MotorTestSuite delegate (mg6010-decomposition)
    // Uses shared_from_this() — node is fully constructed at this point.
    motor_test_suite_ = std::make_unique<MotorTestSuite>(
      std::shared_ptr<rclcpp_lifecycle::LifecycleNode>(this, [](rclcpp_lifecycle::LifecycleNode*){}),
      can_interface_, controllers_, motor_available_, joint_names_);

    // Construct ControlLoopManager delegate (mg6010-decomposition)
    // Non-owning shared_ptr to this node (no-op deleter), same pattern as MotorTestSuite.
    // Pass 0.0 for control_frequency — the node's own control_loop() and publishers
    // remain active; CLM is only used for PID write service callbacks at this stage.
    control_loop_manager_ = std::make_unique<ControlLoopManager>(
      std::shared_ptr<rclcpp_lifecycle::LifecycleNode>(this, [](rclcpp_lifecycle::LifecycleNode*){}),
      can_interface_, controllers_, motor_available_, joint_names_,
      0.0);

    // Construct MotorManager delegate — wraps existing controllers/joint_names/homing_positions
    // Uses injection constructor (same controllers the node already created).
    // This bridge pattern is temporary: Step 9 (LifecycleNode) will make MotorManager the
    // primary owner, constructing controllers directly during on_configure.
    motor_manager_ = std::make_unique<MotorManager>(
      std::shared_ptr<rclcpp_lifecycle::LifecycleNode>(this, [](rclcpp_lifecycle::LifecycleNode*){}),
      can_interface_, controllers_, joint_names_, homing_positions_);

    if (test_mode == "multi_motor") {
      configure_ros_interface(control_frequency);
      if (available_motors == 0) {
        RCLCPP_WARN(this->get_logger(), "⚠️ ROS 2 interface ready but NO MOTORS available");
      } else if (degraded_mode_active_) {
        RCLCPP_WARN(this->get_logger(), "⚠️ ROS 2 interface ready (DEGRADED MODE - %zu motors)", available_motors);
      } else {
        RCLCPP_INFO(this->get_logger(), "✅ ROS 2 interface ready (control loop, joint_states, services)");
      }
    } else if (controllers_.size() >= 1 && controllers_[0] != nullptr) {
      // Legacy single-motor test modes — delegated to MotorTestSuite
      motor_test_suite_->dispatch_test(test_mode, target_position);
    }

    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_activate(const rclcpp_lifecycle::State &) override
  {
    RCLCPP_INFO(this->get_logger(), "Activating motor control node...");

    // Create all timers
    activate_timers(control_frequency_);

    // Construct ShutdownHandler delegate (Phase 3 Step 7)
    // Must be after activate_timers() so timers exist. Guarded by motorCount > 0
    // since ShutdownHandler rejects zero-motor MotorManager.
    if (motor_manager_ && motor_manager_->motorCount() > 0 && role_strategy_) {
      shutdown_handler_ = std::make_unique<ShutdownHandler>(
        std::shared_ptr<rclcpp_lifecycle::LifecycleNode>(this, [](rclcpp_lifecycle::LifecycleNode*){}),
        *motor_manager_, role_strategy_,
        std::vector<rclcpp::TimerBase::SharedPtr>{
          control_timer_, watchdog_timer_, recovery_timer_,
          stats_timer_, motion_feedback_timer_});
    }

    // Enable all motors via MotorManager (spec: on_activate enables motors)
    if (motor_manager_) {
      motor_manager_->enableAll();
    }

    startup_time_ = std::chrono::steady_clock::now();
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_deactivate(const rclcpp_lifecycle::State &) override
  {
    RCLCPP_INFO(this->get_logger(), "Deactivating motor control node...");

    // Signal deactivation to running action loops
    deactivating_.store(true, std::memory_order_release);

    // Grace period: wait up to 5s for in-progress actions to complete
    static constexpr auto GRACE_PERIOD = std::chrono::seconds(5);
    static constexpr auto POLL_INTERVAL = std::chrono::milliseconds(100);
    auto deadline = std::chrono::steady_clock::now() + GRACE_PERIOD;

    bool actions_active = true;
    while (actions_active && std::chrono::steady_clock::now() < deadline) {
      actions_active = step_test_running_ || joint_homing_active_;
      if (!actions_active) {
        for (size_t i = 0; i < MAX_MOTORS && !actions_active; ++i) {
          if (joint_pos_cmd_active_[i]) actions_active = true;
        }
      }
      if (actions_active) {
        // BLOCKING_SLEEP_OK: deactivation grace period, waiting for actions to finish
        std::this_thread::sleep_for(POLL_INTERVAL);
      }
    }

    if (actions_active) {
      RCLCPP_WARN(this->get_logger(),
        "Deactivation grace period expired (5s) — forcing deactivation with active actions");
    }

    // Cancel all timers
    if (control_timer_) control_timer_->cancel();
    if (watchdog_timer_) watchdog_timer_->cancel();
    if (recovery_timer_) recovery_timer_->cancel();
    if (stats_timer_) stats_timer_->cancel();
    if (motion_feedback_timer_) motion_feedback_timer_->cancel();
    if (sim_physics_timer_) sim_physics_timer_->cancel();
    if (reboot_timer_) reboot_timer_->cancel();

    // Skip motor disable if coming from on_shutdown (motors already disabled by perform_shutdown)
    // Only disable here if called standalone (e.g., lifecycle management from external tool)
    // Check: if controllers exist but aren't all disabled, then we need to disable them
    bool any_motor_enabled = false;
    for (size_t i = 0; i < controllers_.size() && i < MAX_MOTORS; ++i) {
      if (motor_enabled_flags_[i]) {
        any_motor_enabled = true;
        break;
      }
    }
    if (any_motor_enabled && motor_manager_) {
      motor_manager_->disableAll();
    }

    // NOTE: shutdown_handler_ is NOT reset here - it must survive until
    // perform_shutdown() is called in on_shutdown(). Premature destruction
    // prevents motor parking sequence from executing (arm doesn't return home).
    // It will be reset in on_cleanup() or after perform_shutdown() completes.

    // Reset deactivating flag
    deactivating_.store(false, std::memory_order_release);

    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_cleanup(const rclcpp_lifecycle::State &) override
  {
    RCLCPP_INFO(this->get_logger(), "Cleaning up motor control node...");

    // Reset timers
    control_timer_.reset();
    watchdog_timer_.reset();
    recovery_timer_.reset();
    stats_timer_.reset();
    motion_feedback_timer_.reset();
    sim_physics_timer_.reset();
    reboot_timer_.reset();

    // Reset managers
    shutdown_handler_.reset();
    motor_manager_.reset();
    ros_interface_manager_.reset();
    control_loop_manager_.reset();
    motor_test_suite_.reset();
    safety_monitor_.reset();

    // Reset callback groups
    safety_cb_group_.reset();
    hardware_cb_group_.reset();
    processing_cb_group_.reset();

    // Clear motor state
    controllers_.clear();
    joint_names_.clear();
    joint_is_revolute_.clear();
    homing_positions_.clear();
    packing_positions_.clear();

    // Reset publisher caches
    joint_state_pub_.reset();
    motor_diagnostics_pub_.reset();

    // Reset CAN interfaces
    can_interface_.reset();
    sim_can_interface_.reset();
    can_available_ = false;

    // Reset role strategy
    role_strategy_.reset();

    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_shutdown(const rclcpp_lifecycle::State & previous_state) override
  {
    RCLCPP_INFO(this->get_logger(), "Shutting down motor control node...");

    // CRITICAL: perform_shutdown() must run BEFORE on_deactivate() disables motors.
    // The shutdown sequence needs motors enabled to park them to safe positions.
    // Only after parking should motors be disabled.
    perform_shutdown();

    // Now deactivate (cancel timers, disable motors) - motors already disabled by perform_shutdown
    if (previous_state.id() == lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
      on_deactivate(previous_state);
    }

    // Clean up all resources
    on_cleanup(previous_state);

    return CallbackReturn::SUCCESS;
  }

  /**
   * @brief Destructor - performs safe shutdown sequence
   * LifecycleNode: on_shutdown should have been called already.
   * Guard against double-shutdown: only call perform_shutdown if controllers still exist.
   */
  ~MG6010ControllerNode()
  {
    if (!controllers_.empty()) {
      perform_shutdown();
    }
  }

  /**
   * @brief Request early termination of shutdown polling loops (task 1.4).
   * Called from main when a second signal arrives during an already-in-progress shutdown.
   */
  void request_shutdown_abort()
  {
    shutdown_requested_.store(true);
    shutdown_cv_.notify_all();
    // Also signal the extracted ShutdownHandler (Phase 3 Step 7)
    if (shutdown_handler_) {
      shutdown_handler_->requestAbort();
      shutdown_handler_->notifyAbort();
    }
  }

private:
  std::shared_ptr<CANInterface> can_interface_;
  bool can_available_{false};  // True once CAN interface is successfully initialized
  bool simulation_mode_{false};  // True when running with simulated CAN (no hardware)
  std::shared_ptr<test::ConfigurableMockCANInterface> sim_can_interface_;  // Non-null only in sim mode
  rclcpp::TimerBase::SharedPtr sim_physics_timer_;  // 10ms wall timer driving physics
  std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;  // Multi-motor support!
  std::vector<std::string> joint_names_;  // Store joint names for publishing
  std::vector<bool> joint_is_revolute_;  // True for revolute joints (rotations→radians on publish)
  std::vector<double> homing_positions_;  // Store homing positions (operational start)
  std::vector<double> packing_positions_;  // Packing positions (shutdown, ready for transport)
  std::shared_ptr<SafetyMonitor> safety_monitor_;  // Safety state machine and e-stop execution

  // Extracted test/diagnostic delegate (mg6010-decomposition)
  std::unique_ptr<MotorTestSuite> motor_test_suite_;

  // Extracted control loop delegate (mg6010-decomposition)
  std::unique_ptr<ControlLoopManager> control_loop_manager_;

  // Extracted ROS interface manager (mg6010-decomposition)
  std::unique_ptr<RosInterfaceManager> ros_interface_manager_;

  // Callback groups (Phase 3 Step 8) — owned by node, injected into managers
  rclcpp::CallbackGroup::SharedPtr safety_cb_group_;     // MutuallyExclusive: watchdog, e-stop, interlock
  rclcpp::CallbackGroup::SharedPtr hardware_cb_group_;   // MutuallyExclusive: services, control loop, commands
  rclcpp::CallbackGroup::SharedPtr processing_cb_group_; // Reentrant: action servers, diagnostics, stats

  // Extracted role strategy delegate (mg6010-decomposition Phase 3)
  std::shared_ptr<RoleStrategy> role_strategy_;

  // Extracted motor manager — wraps controllers_/joint_names_/homing_positions_ (Phase 3 Step 7)
  std::unique_ptr<MotorManager> motor_manager_;

  // Extracted shutdown handler delegate (mg6010-decomposition Phase 3 Step 7)
  std::unique_ptr<ShutdownHandler> shutdown_handler_;

  // ROS 2 interface (publishers cached from RosInterfaceManager for control_loop use)
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr motor_diagnostics_pub_;
  rclcpp::TimerBase::SharedPtr control_timer_;

  // Error state tracking for control loop skip (task 5.3)
  std::array<bool, MAX_MOTORS> motor_error_state_{};  // True if motor is in error/thermal/stall
  std::array<std::chrono::steady_clock::time_point, MAX_MOTORS> motor_error_last_log_;  // Rate-limit WARN logs
  std::array<std::chrono::steady_clock::time_point, MAX_MOTORS> motor_error_onset_time_;  // W6: When error state began
  static constexpr auto ERROR_LOG_INTERVAL = std::chrono::seconds(1);  // Max 1 WARN per second per motor

  // Control loop watchdog: detect hung control loop
  rclcpp::TimerBase::SharedPtr watchdog_timer_;
  std::chrono::steady_clock::time_point last_control_loop_tick_{std::chrono::steady_clock::now()};
  double control_frequency_{10.0};  // cached for watchdog period calculation
  std::atomic<bool> watchdog_exempt_{false};  // Suppress watchdog during known blocking ops (homing, shutdown)

  // Shutdown coordination: condition variable to wake blocking poll loops early (task 1.4)
  std::atomic<bool> shutdown_requested_{false};
  std::atomic<bool> deactivating_{false};  // Lifecycle deactivation in progress (grace period)
  std::mutex shutdown_cv_mutex_;
  std::condition_variable shutdown_cv_;

  // Background recovery timer (D2, tasks 2.2-2.3)
  rclcpp::TimerBase::SharedPtr recovery_timer_;

  // Smart polling: Track motor busy state to avoid CAN saturation during motion
  // When a motor is commanded, skip polling it until timeout (assume busy during motion)
  // std::atomic<bool> — thread-safe without external lock
  bool smart_polling_enabled_{true};
  std::chrono::steady_clock::duration motor_busy_timeout_{std::chrono::seconds(5)};
  std::array<std::atomic<bool>, MAX_MOTORS> motor_busy_flags_{};  // Default to false
  std::array<std::chrono::steady_clock::time_point, MAX_MOTORS> motor_command_times_;
  std::array<double, MAX_MOTORS> last_commanded_positions_{};  // Default to 0.0 - For RViz display during motion

  // Degraded mode: Track which motors are available
  // std::atomic<bool> — thread-safe without external lock
  std::array<std::atomic<bool>, MAX_MOTORS> motor_available_{};  // True if motor is allowed to accept commands
  std::array<std::atomic<bool>, MAX_MOTORS> motor_enabled_flags_{};  // Track enable/disable state to avoid false failure counts
  bool degraded_mode_active_{false};  // True if running with partial motors

  // Health monitoring: Runtime failure detection with bypass options
  bool health_monitoring_enabled_{true};
  bool auto_disable_on_failure_{true};
  bool log_only_mode_{false};  // Field bypass - only log, never disable
  int failure_threshold_{3};
  std::array<int, MAX_MOTORS> motor_failure_count_{};  // Consecutive failures per motor
  std::array<std::string, MAX_MOTORS> motor_last_error_;  // Last error reason for debugging

  // Motor absence detection: exponential backoff for disconnected motors (task 4.7)
  MotorAbsenceConfig absence_config_;
  std::array<MotorAbsenceState, MAX_MOTORS> motor_absence_;

  // Stats logging (similar to camera)
  rclcpp::TimerBase::SharedPtr stats_timer_;
  std::chrono::steady_clock::time_point startup_time_;
  size_t total_position_commands_{0};
  size_t total_velocity_commands_{0};

  // Motion feedback / target reach detection
  bool motion_feedback_enabled_{true};
  double motion_feedback_poll_hz_{5.0};
  bool motion_feedback_publish_actual_while_busy_{true};
  double motion_feedback_position_tolerance_{0.01};
  std::array<double, MAX_MOTORS> motion_feedback_position_tolerance_by_motor_{};
  mutable std::mutex motion_mutex_;
  std::chrono::steady_clock::duration motion_feedback_settle_time_{std::chrono::milliseconds(200)};
  std::chrono::steady_clock::duration motion_feedback_timeout_{std::chrono::seconds(5)};
  rclcpp::TimerBase::SharedPtr motion_feedback_timer_;

  // One-shot timer for non-blocking REBOOT lifecycle (task 3.12)
  rclcpp::TimerBase::SharedPtr reboot_timer_;

  std::array<bool, MAX_MOTORS> motion_pending_{};
  std::array<double, MAX_MOTORS> motion_target_positions_{};
  std::array<std::chrono::steady_clock::time_point, MAX_MOTORS> motion_start_times_;
  std::array<bool, MAX_MOTORS> motion_in_tolerance_{};
  std::array<std::chrono::steady_clock::time_point, MAX_MOTORS> motion_in_tolerance_since_;

  // Last feedback (used to publish something more realistic while motor is marked busy)
  std::array<bool, MAX_MOTORS> last_feedback_valid_{};
  std::array<double, MAX_MOTORS> last_feedback_position_{};
  std::array<std::chrono::steady_clock::time_point, MAX_MOTORS> last_feedback_time_;

  // Per-motor command outcome counters (position commands)
  std::array<uint64_t, MAX_MOTORS> pos_cmd_received_{};
  std::array<uint64_t, MAX_MOTORS> pos_cmd_sent_ok_{};
  std::array<uint64_t, MAX_MOTORS> pos_cmd_sent_fail_{};
  std::array<uint64_t, MAX_MOTORS> pos_cmd_reached_ok_{};
  std::array<uint64_t, MAX_MOTORS> pos_cmd_reached_timeout_{};

  // Collision interlock: prevent J4 commands when J3 is in parking zone
  bool interlock_enabled_{true};
  double j3_parking_position_{0.0};   // J3 parking position (joint units: rotations)
  double j3_parking_tolerance_{5.0};  // Tolerance band (degrees) around parking position

  // Step response test action server
  using StepResponseTest = motor_control_msgs::action::StepResponseTest;
  using GoalHandleStepResponse = rclcpp_action::ServerGoalHandle<StepResponseTest>;
  std::mutex step_test_mutex_;  // Prevent concurrent step tests
  bool step_test_running_{false};

  // JointPositionCommand action server (task 3.4)
  using JointPosCmd = motor_control_msgs::action::JointPositionCommand;
  using GoalHandleJointPosCmd = rclcpp_action::ServerGoalHandle<JointPosCmd>;
  std::mutex joint_pos_cmd_mutex_;  // Prevent concurrent position commands to same joint
  std::array<bool, MAX_MOTORS> joint_pos_cmd_active_{};  // Per-joint active flag

  // JointHoming action server (task 3.5)
  using JointHomingAction = motor_control_msgs::action::JointHoming;
  using GoalHandleJointHoming = rclcpp_action::ServerGoalHandle<JointHomingAction>;
  std::mutex joint_homing_mutex_;
  bool joint_homing_active_{false};

  /**
   * @brief Perform motor homing sequence
   * Sequence: Motor ON -> Enter closed-loop mode -> Move to motor zero -> Move to homing position
   * NOTE: homing_position is in joint units (rotations for revolute, meters for prismatic)
   */

  /**
   * @brief Find motor controller index by CAN motor ID
   * @param motor_id CAN motor ID (1-32)
   * @return Motor index in controllers_ vector, or SIZE_MAX if not found
   */
  size_t findMotorByCanId(uint8_t motor_id) const
  {
    for (size_t i = 0; i < controllers_.size(); ++i) {
      if (controllers_[i] == nullptr) {
        continue;
      }
      if (controllers_[i]->get_configuration().can_id == motor_id) {
        return i;
      }
    }
    return SIZE_MAX;
  }

  void perform_motor_homing(
    std::shared_ptr<MotorControllerInterface> controller,
    size_t motor_idx,
    const std::string& joint_name,
    double homing_position)
  {
    // Exempt watchdog during homing (blocking motor movement)
    watchdog_exempt_.store(true, std::memory_order_release);

    // Skip homing for drive motors (continuous rotation)
    if (role_strategy_->isDriveMotor(joint_name)) {
      RCLCPP_INFO(this->get_logger(), "⏭️  Skipping homing for drive motor: %s", joint_name.c_str());
      watchdog_exempt_.store(false, std::memory_order_release);
      return;
    }

    double pos_tol = motion_feedback_position_tolerance_;
    if (motor_idx < MAX_MOTORS) {
      pos_tol = motion_feedback_position_tolerance_by_motor_[motor_idx];
    }

    RCLCPP_INFO(this->get_logger(), " ");
    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════");
    RCLCPP_INFO(this->get_logger(), "🏠 Homing Sequence: %s", joint_name.c_str());
    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════");

    // Step 1: Move to motor's built-in zero position (stored in ROM)
    RCLCPP_INFO(this->get_logger(), "[1/3] Moving to motor's built-in zero position...");
    if (controller->set_position(0.0, 0.0, 0.0)) {
      RCLCPP_INFO(this->get_logger(), "      ✓ Command sent - motor moving to zero position");
    } else {
      RCLCPP_ERROR(this->get_logger(), "      ✗ Failed to send zero position command");
      watchdog_exempt_.store(false, std::memory_order_release);
      return;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2000));  // Wait for motor to reach zero

    // Step 2: Verify motor reached zero position
    RCLCPP_INFO(this->get_logger(), "[2/3] Verifying motor zero position...");
    double verify_pos = controller->get_position();
    RCLCPP_INFO(this->get_logger(), "      Current position: %.4f (joint units)", verify_pos);
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    // Step 3: Move to final homing position if different from zero
    const double homing_err = verify_pos - homing_position;
    if (std::abs(homing_err) <= pos_tol) {
      RCLCPP_INFO(this->get_logger(),
                  "      ✓ Already at homing target (target=%.4f, actual=%.4f, err=%.4f, tol=%.4f)",
                  homing_position, verify_pos, homing_err, pos_tol);
      RCLCPP_INFO(this->get_logger(), "✅ Homing sequence completed for %s", joint_name.c_str());
      RCLCPP_INFO(this->get_logger(), " ");
      watchdog_exempt_.store(false, std::memory_order_release);
      return;
    }

    RCLCPP_INFO(this->get_logger(), "[3/3] Moving to final homing position: %.4f (joint units)...",
                homing_position);
    if (controller->set_position(homing_position, 0.0, 0.0)) {
      RCLCPP_INFO(this->get_logger(), "      ✓ Moving to final homing position...");
      std::this_thread::sleep_for(std::chrono::milliseconds(3000));
      double final_pos = controller->get_position();
      RCLCPP_INFO(this->get_logger(), "      Final position: %.4f (joint units)", final_pos);
      RCLCPP_INFO(this->get_logger(), "✅ Homing sequence completed for %s", joint_name.c_str());
    } else {
      RCLCPP_ERROR(this->get_logger(), "      ✗ Failed to move to final homing position");
      watchdog_exempt_.store(false, std::memory_order_release);
      return;
    }
    RCLCPP_INFO(this->get_logger(), " ");  // Blank line for readability
    watchdog_exempt_.store(false, std::memory_order_release);
  }

  /**
   * @brief Perform safe shutdown sequence
   * Delegates to ShutdownHandler for role-aware motor parking, then disables all motors.
   *
   * CRITICAL FOR ARM SAFETY: This prevents sudden arm drop when motors are disabled.
   * Each joint is moved to home position and verified before proceeding to next.
   */
  void perform_shutdown()
  {
    if (controllers_.empty()) {
      return;  // Nothing to shut down
    }

    // Exempt watchdog during shutdown (blocking motor park/home operations)
    watchdog_exempt_.store(true, std::memory_order_release);

    if (shutdown_handler_) {
      // Delegate to extracted ShutdownHandler (Phase 3 Step 7)
      RCLCPP_INFO(this->get_logger(), " ");
      RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════");
      RCLCPP_INFO(this->get_logger(), "🛑 SHUTDOWN: Graceful Motor Park & Disable");
      RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════");

      auto result = shutdown_handler_->execute();

      RCLCPP_INFO(this->get_logger(), "🏁 Parking complete: %zu/%zu joints at safe resting position",
                  result.parked_count, result.total_count);
      if (result.deadline_exceeded) {
        RCLCPP_WARN(this->get_logger(), "⏰ Shutdown global deadline exceeded");
      }

      // Update node-level motor_enabled_flags_ (ShutdownHandler disables motors via MotorManager)
      for (size_t i = 0; i < controllers_.size() && i < MAX_MOTORS; ++i) {
        motor_enabled_flags_[i] = false;
      }

      RCLCPP_INFO(this->get_logger(), "✅ Graceful shutdown complete");
      RCLCPP_INFO(this->get_logger(), " ");
    } else {
      // Fallback: ShutdownHandler not constructed (e.g., zero motors or missing role strategy)
      // Disable all motors directly without parking sequence
      RCLCPP_WARN(this->get_logger(), "ShutdownHandler not available — disabling motors without parking");
      for (size_t i = 0; i < controllers_.size(); ++i) {
        if (controllers_[i]) {
          controllers_[i]->set_enabled(false);
        }
        if (i < MAX_MOTORS) {
          motor_enabled_flags_[i] = false;
        }
      }
    }

    watchdog_exempt_.store(false, std::memory_order_release);
  }

  void configure_ros_interface(double frequency)
  {
    // Helper for readable names in logs
    std::string ns = this->get_namespace();
    if (ns == "/") {
      ns.clear();
    }

    // Build NodeCallbacks struct for services/actions still handled by this node
    using namespace std::placeholders;
    NodeCallbacks callbacks;
    callbacks.enable_callback = std::bind(&MG6010ControllerNode::enable_callback, this, _1, _2);
    callbacks.disable_callback = std::bind(&MG6010ControllerNode::disable_callback, this, _1, _2);
    callbacks.reset_motor_callback = std::bind(&MG6010ControllerNode::reset_motor_callback, this, _1, _2);
    callbacks.joint_position_command_callback = std::bind(&MG6010ControllerNode::joint_position_command_callback, this, _1, _2);
    callbacks.motor_command_callback = std::bind(&MG6010ControllerNode::motorCommandCallback, this, _1, _2);
    callbacks.motor_lifecycle_callback = std::bind(&MG6010ControllerNode::motorLifecycleCallback, this, _1, _2);
    callbacks.write_motor_limits_callback = std::bind(&MG6010ControllerNode::writeMotorLimitsCallback, this, _1, _2);
    callbacks.write_encoder_zero_callback = std::bind(&MG6010ControllerNode::writeEncoderZeroCallback, this, _1, _2);

    // Action server callbacks — StepResponseTest
    callbacks.step_response_goal_callback = std::bind(&MG6010ControllerNode::handleStepResponseGoal, this, _1, _2);
    callbacks.step_response_cancel_callback = std::bind(&MG6010ControllerNode::handleStepResponseCancel, this, _1);
    callbacks.step_response_accepted_callback = std::bind(&MG6010ControllerNode::handleStepResponseAccepted, this, _1);

    // Action server callbacks — JointPositionCommand
    callbacks.joint_pos_cmd_goal_callback = std::bind(&MG6010ControllerNode::handleJointPosCmdGoal, this, _1, _2);
    callbacks.joint_pos_cmd_cancel_callback = std::bind(&MG6010ControllerNode::handleJointPosCmdCancel, this, _1);
    callbacks.joint_pos_cmd_accepted_callback = std::bind(&MG6010ControllerNode::handleJointPosCmdAccepted, this, _1);

    // Action server callbacks — JointHoming
    callbacks.joint_homing_goal_callback = std::bind(&MG6010ControllerNode::handleJointHomingGoal, this, _1, _2);
    callbacks.joint_homing_cancel_callback = std::bind(&MG6010ControllerNode::handleJointHomingCancel, this, _1);
    callbacks.joint_homing_accepted_callback = std::bind(&MG6010ControllerNode::handleJointHomingAccepted, this, _1);

    // Create callback groups on the node (Phase 3 Step 8)
    // Ownership: node creates and owns the groups; RIM and timers reference them.
    safety_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);
    hardware_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::MutuallyExclusive);
    processing_cb_group_ = this->create_callback_group(
      rclcpp::CallbackGroupType::Reentrant);

    // Create RosInterfaceManager — owns all services, action servers, subscribers, publishers
    // Uses non-owning shared_ptr (no-op deleter) since the node owns itself
    ros_interface_manager_ = std::make_unique<RosInterfaceManager>(
      std::shared_ptr<rclcpp_lifecycle::LifecycleNode>(this, [](rclcpp_lifecycle::LifecycleNode*) {}),
      motor_test_suite_.get(),
      control_loop_manager_.get(),
      callbacks,
      controllers_,
      motor_available_,
      joint_names_,
      safety_cb_group_,
      hardware_cb_group_,
      processing_cb_group_);

    // Cache publisher pointers from RIM for use in control_loop()
    joint_state_pub_ = ros_interface_manager_->joint_state_publisher();
    motor_diagnostics_pub_ = ros_interface_manager_->motor_diagnostics_publisher();

    // Cache control frequency for activate_timers()
    control_frequency_ = frequency;

    RCLCPP_INFO(this->get_logger(), "Publishing: joint_states (typically remapped to /vehicle/joint_states)");
    RCLCPP_INFO(this->get_logger(), "Services: enable_motors, disable_motors (may be remapped/namespaced)");
  }

  void activate_timers(double frequency)
  {
    // Create control loop timer — assigned to hardware callback group
    auto period = std::chrono::duration<double>(1.0 / frequency);
    control_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::milliseconds>(period),
      std::bind(&MG6010ControllerNode::control_loop, this),
      hardware_cb_group_);

    // Create control loop watchdog timer (5x control loop period) — safety callback group
    // Detects hung control loop (e.g., mutex deadlock during recovery)
    {
      auto watchdog_period = std::chrono::duration<double>(5.0 / frequency);
      watchdog_timer_ = this->create_wall_timer(
        std::chrono::duration_cast<std::chrono::milliseconds>(watchdog_period),
        std::bind(&MG6010ControllerNode::watchdog_check, this),
        safety_cb_group_);
    }

    // Background recovery timer (D2, tasks 2.2-2.3) — hardware callback group
    // Drives the per-motor recovery state machines without blocking the control loop.
    // Runs at 500ms intervals — each call advances one step per motor that needs recovery.
    recovery_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(500),
      std::bind(&MG6010ControllerNode::recovery_timer_callback, this),
      hardware_cb_group_);

    // Create stats timer (log every 30 seconds like camera) — processing callback group
    stats_timer_ = this->create_wall_timer(
      std::chrono::seconds(30),
      std::bind(&MG6010ControllerNode::log_stats, this),
      processing_cb_group_);

    // Motion feedback timer (poll commanded motors at low rate) — processing callback group
    if (motion_feedback_enabled_) {
      auto period = std::chrono::duration<double>(1.0 / motion_feedback_poll_hz_);
      motion_feedback_timer_ = this->create_wall_timer(
        std::chrono::duration_cast<std::chrono::milliseconds>(period),
        std::bind(&MG6010ControllerNode::motion_feedback_poll, this),
        processing_cb_group_);
      RCLCPP_INFO(this->get_logger(), "🎯 Motion feedback enabled (poll_hz=%.2f)", motion_feedback_poll_hz_);
    }

    RCLCPP_INFO(this->get_logger(), "📊 Stats logging enabled (every 30s)");
  }

  // --------------------------------------------------------------------------
  // Collision interlock: shared check for J3-J4 interaction
  // Returns true if the command should be blocked (interlock fires).
  // --------------------------------------------------------------------------
  bool checkJ3J4Interlock(size_t motor_idx, double requested_position, const char * source)
  {
    if (!interlock_enabled_) return false;

    // Only applies to J4 commands
    if (motor_idx >= joint_names_.size() || joint_names_[motor_idx] != "joint4") return false;

    // Find J3 motor index
    size_t j3_idx = controllers_.size();  // sentinel: not found
    for (size_t i = 0; i < joint_names_.size(); ++i) {
      if (joint_names_[i] == "joint3") {
        j3_idx = i;
        break;
      }
    }

    if (j3_idx >= controllers_.size() || controllers_[j3_idx] == nullptr) return false;

    double j3_pos = controllers_[j3_idx]->get_position();
    // Convert tolerance from degrees to rotations for comparison (J3 uses rotations)
    double tol_rotations = j3_parking_tolerance_ / 360.0;
    if (std::abs(j3_pos - j3_parking_position_) < tol_rotations) {
      // Structured JSON log for interlock rejection
      auto interlock_json = pragati::json_envelope("interlock_rejection", this->get_logger().get_name());
      interlock_json["source"] = source;
      interlock_json["joint_blocked"] = "joint4";
      interlock_json["reason"] = "j3_in_parking_zone";
      interlock_json["j3_position"] = j3_pos;
      interlock_json["j3_parking_position"] = j3_parking_position_;
      interlock_json["j3_parking_tolerance_deg"] = j3_parking_tolerance_;
      interlock_json["j4_requested_position"] = requested_position;

      RCLCPP_WARN(this->get_logger(), "%s", interlock_json.dump().c_str());
      return true;  // blocked
    }

    return false;  // allowed
  }

  void position_command_callback(size_t motor_idx, const std_msgs::msg::Float64::SharedPtr msg)
  {
    if (motor_idx >= controllers_.size()) {
      RCLCPP_ERROR(this->get_logger(), "Invalid motor index: %zu", motor_idx);
      return;
    }

    // Check if motor is available (degraded mode support)
    if (controllers_[motor_idx] == nullptr ||
        (motor_idx < MAX_MOTORS && !motor_available_[motor_idx])) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "⚠️ Motor %s unavailable - command ignored",
                           joint_names_[motor_idx].c_str());
      return;
    }

    // Avoid counting failures when motors are intentionally disabled
    if (motor_idx < MAX_MOTORS && !motor_enabled_flags_[motor_idx]) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "⚠️ Motor %s is DISABLED - command ignored (call enable_motors)",
                           joint_names_[motor_idx].c_str());
      return;
    }

    total_position_commands_++;  // Track for stats
    double position = msg->data;

    // Collision interlock: reject J4 commands when J3 is in parking zone
    if (checkJ3J4Interlock(motor_idx, position, "position_command_topic")) {
      return;
    }

    if (motor_idx < MAX_MOTORS) {
      pos_cmd_received_[motor_idx]++;
    }

    RCLCPP_DEBUG(this->get_logger(), "🎯 Received position command for %s: %.4f (joint units)",
                 joint_names_[motor_idx].c_str(), position);

    // Mark motor as busy (skip polling during motion to prevent CAN saturation)
    if (motor_idx < MAX_MOTORS) {
      motor_busy_flags_[motor_idx] = true;
      motor_command_times_[motor_idx] = std::chrono::steady_clock::now();
      last_commanded_positions_[motor_idx] = position;  // Cache for joint_states during motion
    }

    // Send position command to motor with failure tracking
    if (controllers_[motor_idx]->set_position(position, 0.0, 0.0)) {
      RCLCPP_DEBUG(this->get_logger(), "✅ Position command sent to %s", joint_names_[motor_idx].c_str());

      if (motor_idx < MAX_MOTORS) {
        pos_cmd_sent_ok_[motor_idx]++;
        motor_failure_count_[motor_idx] = 0;

        // Register this motion for feedback-based reach detection
        {
          std::lock_guard<std::mutex> lock(motion_mutex_);
          motion_pending_[motor_idx] = true;
          motion_target_positions_[motor_idx] = position;
          motion_start_times_[motor_idx] = std::chrono::steady_clock::now();
          motion_in_tolerance_[motor_idx] = false;
        }
      }
    } else {
      if (motor_idx < MAX_MOTORS) {
        pos_cmd_sent_fail_[motor_idx]++;
      }
      // Handle failure with detailed logging and auto-disable
      handle_motor_failure(motor_idx, "position", position, "CAN_COMMAND_FAILED", __func__);
    }
  }

  void velocity_command_callback(size_t motor_idx, const std_msgs::msg::Float64::SharedPtr msg)
  {
    if (motor_idx >= controllers_.size()) {
      RCLCPP_ERROR(this->get_logger(), "Invalid motor index: %zu", motor_idx);
      return;
    }

    // Check if motor is available (degraded mode support)
    if (controllers_[motor_idx] == nullptr ||
        (motor_idx < MAX_MOTORS && !motor_available_[motor_idx])) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "⚠️ Motor %s unavailable - velocity command ignored",
                           joint_names_[motor_idx].c_str());
      return;
    }

    // Avoid counting failures when motors are intentionally disabled
    if (motor_idx < MAX_MOTORS && !motor_enabled_flags_[motor_idx]) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "⚠️ Motor %s is DISABLED - velocity command ignored (call enable_motors)",
                           joint_names_[motor_idx].c_str());
      return;
    }

    total_velocity_commands_++;  // Track for stats
    double velocity = msg->data;

    RCLCPP_DEBUG(this->get_logger(), "🔄 Received velocity command for %s: %.4f rad/s",
                 joint_names_[motor_idx].c_str(), velocity);

    // Mark motor as busy during velocity control
    if (motor_idx < MAX_MOTORS) {
      motor_busy_flags_[motor_idx] = true;
      motor_command_times_[motor_idx] = std::chrono::steady_clock::now();
    }

    // Send velocity command to motor with failure tracking
    if (controllers_[motor_idx]->set_velocity(velocity, 0.0)) {
      RCLCPP_DEBUG(this->get_logger(), "✅ Velocity command sent to %s", joint_names_[motor_idx].c_str());
      // Reset failure count on success
      if (motor_idx < MAX_MOTORS) {
        motor_failure_count_[motor_idx] = 0;
      }
    } else {
      // Handle failure with detailed logging and auto-disable
      handle_motor_failure(motor_idx, "velocity", velocity, "CAN_COMMAND_FAILED", __func__);
    }
  }

  void stop_command_callback(size_t motor_idx)
  {
    if (motor_idx >= controllers_.size()) {
      RCLCPP_ERROR(this->get_logger(), "Invalid motor index: %zu", motor_idx);
      return;
    }

    // Check if motor is available
    if (controllers_[motor_idx] == nullptr ||
        (motor_idx < MAX_MOTORS && !motor_available_[motor_idx])) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "⚠️ Motor %s unavailable - stop command ignored",
                           joint_names_[motor_idx].c_str());
      return;
    }

    RCLCPP_INFO(this->get_logger(), "🛑 Sending motor_stop() to %s (exit position control, reduce power)",
                joint_names_[motor_idx].c_str());

    // Send motor_stop() CAN command
    if (controllers_[motor_idx]->stop()) {
      RCLCPP_INFO(this->get_logger(), "✅ Motor stop sent to %s", joint_names_[motor_idx].c_str());
      // Clear busy flag
      if (motor_idx < MAX_MOTORS) {
        motor_busy_flags_[motor_idx] = false;
      }
    } else {
      RCLCPP_ERROR(this->get_logger(), "❌ Failed to send motor_stop() to %s",
                   joint_names_[motor_idx].c_str());
    }
  }

  /**
   * @brief Handle motor command failure with detailed logging and optional auto-disable
   *
   * Provides comprehensive failure information for field debugging:
   * - What motor failed
   * - What command type (position/velocity)
   * - What the target value was
   * - Why it failed (error string)
   * - Where in code it happened (function name)
   * - How many consecutive failures
   * - What action was taken (logged only / motor disabled)
   */
  void handle_motor_failure(size_t motor_idx, const std::string& cmd_type,
                           double target_value, const std::string& error_reason,
                           const char* func_name)
  {
    if (motor_idx >= MAX_MOTORS) return;

    // Skip if health monitoring disabled (field bypass)
    if (!health_monitoring_enabled_) {
      RCLCPP_WARN(this->get_logger(),
        "MOTOR_FAILURE (monitoring disabled) | motor=%s | cmd=%s | target=%.4f | error=%s | func=%s",
        joint_names_[motor_idx].c_str(), cmd_type.c_str(), target_value,
        error_reason.c_str(), func_name);
      return;
    }

    // Increment failure count
    motor_failure_count_[motor_idx]++;
    motor_last_error_[motor_idx] = error_reason;

    int count = motor_failure_count_[motor_idx];
    bool threshold_reached = (count >= failure_threshold_);

    // Determine action based on config
    std::string action;
    if (threshold_reached && auto_disable_on_failure_ && !log_only_mode_) {
      action = "MOTOR_DISABLED";
      motor_available_[motor_idx] = false;
      motor_enabled_flags_[motor_idx] = false;
      if (controllers_[motor_idx] != nullptr) {
        controllers_[motor_idx]->set_enabled(false);
      }
      // Clear any pending motion tracking for this motor
      {
        std::lock_guard<std::mutex> lock(motion_mutex_);
        motion_pending_[motor_idx] = false;
        motion_in_tolerance_[motor_idx] = false;
        last_feedback_valid_[motor_idx] = false;
      }
    } else if (threshold_reached && log_only_mode_) {
      action = "LOGGED_ONLY (log_only_mode=true)";
    } else if (threshold_reached && !auto_disable_on_failure_) {
      action = "LOGGED_ONLY (auto_disable=false)";
    } else {
      action = "FAILURE_COUNTED";
    }

    // Detailed structured log for debugging
    RCLCPP_ERROR(this->get_logger(),
      "MOTOR_FAILURE | motor=%s | cmd=%s | target=%.4f | error=%s | "
      "failures=%d/%d | action=%s | func=%s",
      joint_names_[motor_idx].c_str(),
      cmd_type.c_str(),
      target_value,
      error_reason.c_str(),
      count,
      failure_threshold_,
      action.c_str(),
      func_name);

    // Extra warning when motor is disabled
    if (action == "MOTOR_DISABLED") {
      std::string ns = this->get_namespace();
      std::string reset_srv = (ns == "/") ? "/reset_motor" : (ns + "/reset_motor");
      RCLCPP_ERROR(this->get_logger(),
        "🔴 Motor %s AUTO-DISABLED after %d consecutive failures. "
        "Use 'ros2 service call %s std_srvs/srv/SetBool "
        "\"{data: true}\"' to re-enable.",
        joint_names_[motor_idx].c_str(), count, reset_srv.c_str());
    }
  }

  /**
   * @brief Service callback to reset (re-enable) a disabled motor
   *
   * Usage:
   *   ros2 service call <ns>/reset_motor std_srvs/srv/SetBool "{data: true}"
   * Example (vehicle):
   *   ros2 service call /vehicle/reset_motor std_srvs/srv/SetBool "{data: true}"
   * Note: This resets ALL disabled motors. For single motor reset, would need a custom service.
   */
  void reset_motor_callback(
    const std::shared_ptr<std_srvs::srv::SetBool::Request> request,
    std::shared_ptr<std_srvs::srv::SetBool::Response> response)
  {
    if (!request->data) {
      response->success = false;
      response->message = "Set data=true to reset motors";
      return;
    }

    std::string reset_motors;
    int reset_count = 0;

    for (size_t i = 0; i < MAX_MOTORS && i < joint_names_.size(); ++i) {
      if (!motor_available_[i] && controllers_[i] != nullptr) {
        // Re-enable this motor
        bool enabled_ok = controllers_[i]->set_enabled(true);
        if (enabled_ok) {
          motor_available_[i] = true;
          motor_enabled_flags_[i] = true;
          motor_failure_count_[i] = 0;

          RCLCPP_INFO(this->get_logger(),
            "✅ Motor %s RE-ENABLED | previous_error=%s | failures_cleared",
            joint_names_[i].c_str(), motor_last_error_[i].c_str());

          motor_last_error_[i] = "";
          reset_motors += joint_names_[i] + " ";
          reset_count++;
        } else {
          RCLCPP_WARN(this->get_logger(), "⚠️ Failed to re-enable motor %s", joint_names_[i].c_str());
        }
      }
    }

    if (reset_count > 0) {
      response->success = true;
      response->message = "Reset motors: " + reset_motors;
      RCLCPP_INFO(this->get_logger(), "🔄 Reset %d motor(s): %s", reset_count, reset_motors.c_str());
    } else {
      response->success = true;
      response->message = "No disabled motors to reset";
    }

    // Task 4.11: Clear absence state for ALL motors so they are immediately re-probed
    for (size_t i = 0; i < MAX_MOTORS && i < joint_names_.size(); ++i) {
      absence_reset(motor_absence_[i], absence_config_);
    }
    RCLCPP_INFO(this->get_logger(),
      "Motor absence state cleared for all motors — immediate re-probe enabled");
  }

  // --------------------------------------------------------------------------
  // Motion feedback: poll commanded motors and emit reached/timeout events
  // --------------------------------------------------------------------------
  void motion_feedback_poll()
  {
    if (!motion_feedback_enabled_) {
      return;
    }

    if (controllers_.empty()) {
      return;
    }

    // Snapshot state without holding the mutex during CAN calls
    std::array<bool, MAX_MOTORS> pending;
    std::array<double, MAX_MOTORS> targets;
    std::array<std::chrono::steady_clock::time_point, MAX_MOTORS> start_times;

    {
      std::lock_guard<std::mutex> lock(motion_mutex_);
      pending = motion_pending_;
      targets = motion_target_positions_;
      start_times = motion_start_times_;
    }

    struct Event
    {
      enum Type { REACHED, TIMEOUT } type;
      size_t idx;
      double target;
      double actual;
      double velocity;
      double current;
      double temperature;
      bool connected;
      double error;
      double elapsed_s;
    };

    std::vector<Event> events;

    const auto now = std::chrono::steady_clock::now();

    for (size_t i = 0; i < controllers_.size() && i < MAX_MOTORS; ++i) {
      if (!pending[i]) {
        continue;
      }

      // Skip motors with active action feedback loop — the action's own 20Hz polling
      // already reads status/position and publishes feedback.  Polling here too would
      // generate redundant CAN traffic and contend on the transaction mutex.
      {
        std::lock_guard<std::mutex> lock(joint_pos_cmd_mutex_);
        if (joint_pos_cmd_active_[i]) {
          continue;
        }
      }

      // If motor became unavailable/disabled, drop tracking.
      if (controllers_[i] == nullptr || !motor_available_[i] || !motor_enabled_flags_[i]) {
        std::lock_guard<std::mutex> lock(motion_mutex_);
        motion_pending_[i] = false;
        motion_in_tolerance_[i] = false;
        last_feedback_valid_[i] = false;
        continue;
      }

      // Poll motor (rate is controlled by this timer)
      const auto st = controllers_[i]->get_status();
      const double pos = controllers_[i]->get_position();
      const double velocity = controllers_[i]->get_velocity();

      // Update last feedback for /joint_states display
      {
        std::lock_guard<std::mutex> lock(motion_mutex_);
        last_feedback_valid_[i] = st.hardware_connected;
        last_feedback_position_[i] = pos;
        last_feedback_time_[i] = now;
      }

      if (!st.hardware_connected) {
        // Don't make reach decisions without confirmed comms.
        continue;
      }

      const double target = targets[i];
      const double err = pos - target;
      const double abs_err = std::abs(err);

      // Timeout check
      if ((now - start_times[i]) >= motion_feedback_timeout_) {
        // Hardened timeout: send motor_stop (0x81) to halt the motor before
        // clearing the busy flag.  This prevents the motor from continuing
        // to drive toward an unreachable position after timeout.
        if (!controllers_[i]->stop()) {
          RCLCPP_WARN(get_logger(),
            "[motor %zu] motor_stop failed during timeout handling (non-fatal)", i);
        }

        {
          std::lock_guard<std::mutex> lock(motion_mutex_);
          motion_pending_[i] = false;
          motion_in_tolerance_[i] = false;
          motor_busy_flags_[i] = false;  // allow normal polling again
          pos_cmd_reached_timeout_[i]++;
        }

        events.push_back(Event{Event::TIMEOUT, i, target, pos, velocity,
                               st.current, st.temperature, st.hardware_connected, err,
                               std::chrono::duration_cast<std::chrono::duration<double>>(now - start_times[i]).count()});
        continue;
      }

      // In-tolerance tracking for a small settle duration
      const double tol = motion_feedback_position_tolerance_by_motor_[i];
      if (abs_err <= tol) {
        bool reached_now = false;
        {
          std::lock_guard<std::mutex> lock(motion_mutex_);
          if (!motion_in_tolerance_[i]) {
            motion_in_tolerance_[i] = true;
            motion_in_tolerance_since_[i] = now;
          } else {
            if ((now - motion_in_tolerance_since_[i]) >= motion_feedback_settle_time_) {
              // Reached and settled
              motion_pending_[i] = false;
              motion_in_tolerance_[i] = false;
              motor_busy_flags_[i] = false;  // allow normal polling immediately
              pos_cmd_reached_ok_[i]++;
              reached_now = true;
            }
          }
        }

        if (reached_now) {
          events.push_back(Event{Event::REACHED, i, target, pos, velocity,
                                 st.current, st.temperature, st.hardware_connected, err,
                                 std::chrono::duration_cast<std::chrono::duration<double>>(now - start_times[i]).count()});
        }
      } else {
        std::lock_guard<std::mutex> lock(motion_mutex_);
        motion_in_tolerance_[i] = false;
      }
    }

    // Emit logs outside of locks
    for (const auto & e : events) {
      if (e.type == Event::REACHED) {
        RCLCPP_INFO(this->get_logger(),
          "✅ Reached target | motor=%s | target=%.4f | actual=%.4f | err=%.4f | vel=%.4f | current=%.3f | temp=%.1f | connected=%s | t=%.3fs",
          joint_names_[e.idx].c_str(), e.target, e.actual, e.error,
          e.velocity, e.current, e.temperature, e.connected ? "true" : "false", e.elapsed_s);
      } else {
        RCLCPP_WARN(this->get_logger(),
          "⏱️ Target timeout | motor=%s | target=%.4f | last=%.4f | err=%.4f | vel=%.4f | current=%.3f | temp=%.1f | connected=%s | timeout=%.3fs",
          joint_names_[e.idx].c_str(), e.target, e.actual, e.error,
          e.velocity, e.current, e.temperature, e.connected ? "true" : "false",
          std::chrono::duration_cast<std::chrono::duration<double>>(motion_feedback_timeout_).count());
      }
    }
  }

  // --------------------------------------------------------------------------
  // Service: joint_position_command (move + optional wait_for_completion)
  // --------------------------------------------------------------------------
  void joint_position_command_callback(
    const std::shared_ptr<motor_control_msgs::srv::JointPositionCommand::Request> request,
    std::shared_ptr<motor_control_msgs::srv::JointPositionCommand::Response> response)
  {
    response->success = false;
    response->reason = "";
    response->actual_position = 0.0;

    if (!request) {
      response->reason = "Null request";
      return;
    }

    // Map joint_id -> motor index. Prefer names like "joint3".
    size_t idx = controllers_.size();
    const std::string joint_name = "joint" + std::to_string(request->joint_id);
    for (size_t i = 0; i < joint_names_.size(); ++i) {
      if (joint_names_[i] == joint_name) {
        idx = i;
        break;
      }
    }

    // Fallback: allow using joint_id as direct index if not found by name.
    if (idx >= controllers_.size() && request->joint_id >= 0) {
      const size_t as_index = static_cast<size_t>(request->joint_id);
      if (as_index < controllers_.size()) {
        idx = as_index;
      }
    }

    if (idx >= controllers_.size()) {
      response->reason = "Unknown joint_id (no matching joint name/index)";
      return;
    }

    if (controllers_[idx] == nullptr || (idx < MAX_MOTORS && !motor_available_[idx])) {
      response->reason = "Motor unavailable";
      return;
    }

    if (idx < MAX_MOTORS && !motor_enabled_flags_[idx]) {
      response->reason = "Motor disabled";
      return;
    }

    // Collision interlock: reject J4 commands when J3 is in parking zone
    if (checkJ3J4Interlock(idx, request->target_position, "joint_position_command_service")) {
      response->success = false;
      response->reason = "Interlock: J4 blocked — J3 in parking zone";
      return;
    }

    const double target = request->target_position;

    // Count as a position command for stats
    total_position_commands_++;
    if (idx < MAX_MOTORS) {
      pos_cmd_received_[idx]++;
    }

    // Mark motor busy so /joint_states doesn't hammer CAN during motion
    if (idx < MAX_MOTORS) {
      motor_busy_flags_[idx] = true;
      motor_command_times_[idx] = std::chrono::steady_clock::now();
      last_commanded_positions_[idx] = target;
    }

    // Send command (velocity is currently ignored by MG6010 position mode 1, but keep for API compatibility)
    const double max_vel = request->max_velocity;
    const bool ok = controllers_[idx]->set_position(target, max_vel, 0.0);

    if (!ok) {
      if (idx < MAX_MOTORS) {
        pos_cmd_sent_fail_[idx]++;
      }
      handle_motor_failure(idx, "position", target, "CAN_COMMAND_FAILED", __func__);
      response->reason = "Command send failed";
      return;
    }

    if (idx < MAX_MOTORS) {
      pos_cmd_sent_ok_[idx]++;
      motor_failure_count_[idx] = 0;
      {
        std::lock_guard<std::mutex> lock(motion_mutex_);
        motion_pending_[idx] = true;
        motion_target_positions_[idx] = target;
        motion_start_times_[idx] = std::chrono::steady_clock::now();
        motion_in_tolerance_[idx] = false;
      }
    }

    if (!request->wait_for_completion) {
      // Accepted/queued by motor (acknowledged at protocol level)
      response->success = true;
      response->reason = "ACCEPTED";
      response->actual_position = controllers_[idx]->get_position();
      return;
    }

    // wait_for_completion=true is DEPRECATED — use /joint_position_command action server instead.
    // The blocking path was removed in phase-2-critical-fixes (bug 1.2) because it
    // starved the SingleThreadedExecutor for up to 5 seconds, preventing watchdog,
    // control loop, and safety callbacks from firing.
    response->success = false;
    response->reason = "DEPRECATED: wait_for_completion=true is no longer supported. "
                       "Use the /joint_position_command action server for position commands "
                       "that require completion feedback.";
    response->actual_position = controllers_[idx]->get_position();
  }

  // --------------------------------------------------------------------------
  // Watchdog: detect hung control loop (e.g., mutex deadlock in recovery)
  // --------------------------------------------------------------------------
  // Background recovery timer callback (D2, tasks 2.2-2.3)
  // Advances each motor's recovery state machine by one step.
  void recovery_timer_callback()
  {
    // C1 fix: Attempt CAN reconnection if disconnected (can-bus-resilience spec scenarios 5-6).
    // attemptReconnection() is MG6010CANInterface-specific; skip for simulated CAN.
    if (can_interface_ && !can_interface_->is_connected()) {
      auto hw_can = std::dynamic_pointer_cast<MG6010CANInterface>(can_interface_);
      if (hw_can) {
        hw_can->attemptReconnection();
      }
    }

    for (size_t i = 0; i < controllers_.size(); ++i) {
      auto * ctrl = dynamic_cast<MG6010Controller *>(controllers_[i].get());
      if (ctrl != nullptr) {
        ctrl->advanceRecovery();
      }
    }
  }

  void watchdog_check()
  {
    // Skip watchdog during known blocking operations (homing, shutdown, etc.)
    if (watchdog_exempt_.load(std::memory_order_acquire)) {
      return;
    }

    auto now = std::chrono::steady_clock::now();
    auto elapsed = now - last_control_loop_tick_;
    // Stale if control loop hasn't ticked in 5× its expected period
    auto stale_threshold = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
      std::chrono::duration<double>(5.0 / control_frequency_));

    if (elapsed > stale_threshold) {
      double stale_s = std::chrono::duration_cast<std::chrono::duration<double>>(elapsed).count();
      RCLCPP_FATAL(this->get_logger(),
        "{\"event\":\"control_loop_watchdog\",\"stale_s\":%.3f,\"threshold_s\":%.3f,"
        "\"action\":\"emergency_stop_all\"}",
        stale_s,
        std::chrono::duration_cast<std::chrono::duration<double>>(stale_threshold).count());

      // Emergency stop all motors
      for (size_t i = 0; i < controllers_.size(); ++i) {
        if (controllers_[i] != nullptr) {
          controllers_[i]->emergency_stop();
        }
      }
    }
  }

  void control_loop()
  {
    // Stamp watchdog tick at entry — watchdog_check() monitors this
    last_control_loop_tick_ = std::chrono::steady_clock::now();

    // Publish joint states using SMART POLLING
    // Only poll motors that are NOT currently moving to prevent CAN bus saturation
    // This allows feedback when motors are idle while avoiding bus-off during motion

    const auto now_steady = std::chrono::steady_clock::now();

    auto msg = sensor_msgs::msg::JointState();
    msg.header.stamp = this->now();

    // Motor diagnostics message (task 5.4-5.5)
    auto diag_msg = diagnostic_msgs::msg::DiagnosticArray();
    diag_msg.header.stamp = this->now();

    if (controllers_.empty()) {
      // Only warn once since this condition won't change during runtime
      RCLCPP_WARN_ONCE(this->get_logger(), "Control loop active but no motors initialized - joint_states will be empty");
      return;
    }

    size_t polled_count = 0;
    size_t skipped_count = 0;

    for (size_t i = 0; i < controllers_.size(); ++i) {
      // Skip unavailable motors (degraded mode)
      if (controllers_[i] == nullptr ||
          (i < MAX_MOTORS && !motor_available_[i])) {
        // Report unavailable motors with zero values
        msg.name.push_back(joint_names_[i]);
        msg.position.push_back(0.0);
        msg.velocity.push_back(0.0);
        msg.effort.push_back(0.0);
        skipped_count++;
        continue;
      }

      // Smart polling: Skip motors that were recently commanded (likely still moving)
      // If smart_polling.enabled=false, this is bypassed and we always poll (full polling).
      if (smart_polling_enabled_ && i < MAX_MOTORS) {
        if (motor_busy_flags_[i]) {
          auto elapsed = now_steady - motor_command_times_[i];
          if (elapsed < motor_busy_timeout_) {
            // Motor is busy - skip polling to reduce CAN traffic
            // Default behavior: publish target position while moving.
            double display_pos = last_commanded_positions_[i];

            // If motion feedback is enabled and we have recent actual feedback, publish that instead.
            if (motion_feedback_enabled_ && motion_feedback_publish_actual_while_busy_) {
              std::lock_guard<std::mutex> mlock(motion_mutex_);
              if (last_feedback_valid_[i]) {
                auto fb_age = now_steady - last_feedback_time_[i];
                // Consider feedback fresh if within ~2 polling periods.
                const auto fresh_window = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                  std::chrono::duration<double>(2.0 / std::max(0.1, motion_feedback_poll_hz_)));
                if (fb_age <= fresh_window) {
                  display_pos = last_feedback_position_[i];
                }
              }
            }

            msg.name.push_back(joint_names_[i]);
            // Revolute joints: convert rotations → radians for URDF/rviz2 compatibility
            double pub_pos_a = (i < joint_is_revolute_.size() && joint_is_revolute_[i])
                               ? display_pos * 2.0 * M_PI : display_pos;
            msg.position.push_back(pub_pos_a);
            msg.velocity.push_back(0.0);  // Unknown during motion
            msg.effort.push_back(0.0);    // Unknown during motion
            skipped_count++;
            continue;
          }
          // Timeout expired - motor should be idle now, clear busy flag
          motor_busy_flags_[i] = false;
          RCLCPP_DEBUG(this->get_logger(), "Motor %s busy timeout expired, resuming polling",
                       joint_names_[i].c_str());
        }
      }

      // Motor absence detection (task 4.8): skip absent motors unless it's time to re-probe
      if (i < MAX_MOTORS && motor_absence_[i].is_absent) {
        if (!absence_should_probe(motor_absence_[i], now_steady)) {
          // Not time to probe yet — publish zeros and skip
          msg.name.push_back(joint_names_[i]);
          msg.position.push_back(0.0);
          msg.velocity.push_back(0.0);
          msg.effort.push_back(-4.0);  // CAN_DISCONNECTED sentinel
          skipped_count++;
          continue;
        }
        // Time to re-probe — fall through but use reduced retries
      }

      // Poll this motor (it's idle or being re-probed)
      MotorStatus status;
      if (i < MAX_MOTORS && motor_absence_[i].is_absent) {
        // Re-probe with single retry to minimize CAN overhead
        auto * mg_ctrl_probe = dynamic_cast<MG6010Controller *>(controllers_[i].get());
        if (mg_ctrl_probe) {
          status = mg_ctrl_probe->get_status(1);
        } else {
          status = controllers_[i]->get_status();
        }
      } else {
        status = controllers_[i]->get_status();
      }
      double position = controllers_[i]->get_position();

      // Track absence based on hardware_connected (task 4.8)
      if (i < MAX_MOTORS) {
        if (!status.hardware_connected) {
          bool just_absent = absence_record_failure(
            motor_absence_[i], absence_config_, now_steady);
          if (just_absent) {
            RCLCPP_WARN(this->get_logger(),
              "Motor %s marked ABSENT after %d consecutive CAN failures — "
              "backoff %dms",
              joint_names_[i].c_str(),
              motor_absence_[i].consecutive_failures,
              static_cast<int>(motor_absence_[i].current_backoff.count()));
          }
        } else {
          bool recovered = absence_record_success(
            motor_absence_[i], absence_config_);
          if (recovered) {
            RCLCPP_INFO(this->get_logger(),
              "Motor %s RECOVERED from absence — resuming normal polling",
              joint_names_[i].c_str());
          }
        }
      }

      // Task 5.3: Check error state — skip commands for motors in error/thermal/stall
      auto * mg_ctrl = dynamic_cast<MG6010Controller *>(controllers_[i].get());
      bool is_errored = (status.state == MotorStatus::AXIS_ERROR);
      bool is_stalled = (mg_ctrl && mg_ctrl->isStallDetected());
      bool is_thermal = (mg_ctrl && mg_ctrl->isThermalProtectionActive());
      bool was_errored = (i < MAX_MOTORS) ? motor_error_state_[i] : false;

      if (is_errored || is_stalled || is_thermal) {
        // Motor is in error state — skip commands, rate-limited WARN log
        if (i < MAX_MOTORS) {
          if (!was_errored) {
            motor_error_onset_time_[i] = now_steady;  // W6: Record error onset time
          }
          motor_error_state_[i] = true;
          auto since_last_log = now_steady - motor_error_last_log_[i];
          if (since_last_log >= ERROR_LOG_INTERVAL) {
            const char * reason = is_errored ? "AXIS_ERROR" :
                                  is_thermal ? "THERMAL_PROTECTION" : "STALL_PROTECTION";
            RCLCPP_WARN(this->get_logger(),
                        "Motor %s in %s state — skipping commands",
                        joint_names_[i].c_str(), reason);
            motor_error_last_log_[i] = now_steady;
          }
        }

        // Task 5.1 + W7 fix: Publish actual position (last-known) when motor is errored.
        // Always prefer most recent feedback position in error state, regardless of config.
        double display_pos = position;  // get_position() returns last-known actual
        {
          std::lock_guard<std::mutex> lock(motion_mutex_);
          if (last_feedback_valid_[i]) {
            display_pos = last_feedback_position_[i];
          }
        }

        msg.name.push_back(joint_names_[i]);
        // Revolute joints: convert rotations → radians for URDF/rviz2 compatibility
        double pub_pos_b = (i < joint_is_revolute_.size() && joint_is_revolute_[i])
                           ? display_pos * 2.0 * M_PI : display_pos;
        msg.position.push_back(pub_pos_b);
        msg.velocity.push_back(0.0);

        // Task 5.2: Encode error state as negative effort value
        // -1.0 = AXIS_ERROR, -2.0 = thermal protection, -3.0 = stall protection
        // -4.0 = CAN disconnected
        double error_effort = -1.0;  // Default: AXIS_ERROR
        if (is_thermal) {
          error_effort = -2.0;
        } else if (is_stalled) {
          error_effort = -3.0;
        } else if (!status.hardware_connected) {
          error_effort = -4.0;
        }
        msg.effort.push_back(error_effort);

        // Still update stall detector even when errored (for stall clear detection)
        if (mg_ctrl) {
          double position_deg = position * (180.0 / M_PI);
          mg_ctrl->updateStallDetector(std::abs(status.current), position_deg);
        }

        skipped_count++;
      } else {
        // Motor is OK — publish normal state
        if (was_errored && i < MAX_MOTORS) {
          // Task 5.3: Motor recovered — log return to service
          motor_error_state_[i] = false;
          RCLCPP_INFO(this->get_logger(),
                      "Motor %s recovered — resuming commands",
                      joint_names_[i].c_str());
        }

        msg.name.push_back(joint_names_[i]);
        // Revolute joints: convert rotations → radians for URDF/rviz2 compatibility
        double pub_pos_c = (i < joint_is_revolute_.size() && joint_is_revolute_[i])
                           ? position * 2.0 * M_PI : position;
        msg.position.push_back(pub_pos_c);
        msg.velocity.push_back(controllers_[i]->get_velocity());
        msg.effort.push_back(status.current);
        polled_count++;

        // Update stall detector with current data (task 4.4)
        if (mg_ctrl) {
          double position_deg = position * (180.0 / M_PI);
          mg_ctrl->updateStallDetector(std::abs(status.current), position_deg);
        }
      }

      // Task 5.5: Populate diagnostics for this motor
      diagnostic_msgs::msg::DiagnosticStatus motor_diag;
      motor_diag.hardware_id = joint_names_[i];
      motor_diag.name = "motor/" + joint_names_[i];

      // Determine diagnostic level
      if (is_errored || is_stalled || is_thermal) {
        motor_diag.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
        if (is_thermal) {
          motor_diag.message = "THERMAL_PROTECTION";
        } else if (is_stalled) {
          motor_diag.message = "STALL_PROTECTION";
        } else {
          motor_diag.message = "AXIS_ERROR";
        }
      } else if (!status.hardware_connected) {
        motor_diag.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
        motor_diag.message = "CAN_DISCONNECTED";
      } else if (status.requires_attention) {
        motor_diag.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
        motor_diag.message = "REQUIRES_ATTENTION";
      } else {
        motor_diag.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
        motor_diag.message = "OK";
      }

      // Key-value pairs for detailed motor state
      auto add_kv = [&motor_diag](const std::string & key, const std::string & value) {
        diagnostic_msgs::msg::KeyValue kv;
        kv.key = key;
        kv.value = value;
        motor_diag.values.push_back(kv);
      };

      add_kv("temperature_c", std::to_string(status.temperature));
      add_kv("current_a", std::to_string(status.current));
      add_kv("voltage_v", std::to_string(status.voltage));
      add_kv("connected", status.hardware_connected ? "true" : "false");
      add_kv("enabled", status.motor_enabled ? "true" : "false");
      add_kv("error_code", std::to_string(status.error_code));

      if (mg_ctrl) {
        add_kv("stall_detected", mg_ctrl->isStallDetected() ? "true" : "false");
        add_kv("derating_pct", std::to_string(
            static_cast<int>((1.0 - mg_ctrl->getDeratingFactor()) * 100.0)));
        add_kv("thermal_protection", mg_ctrl->isThermalProtectionActive() ? "true" : "false");
        add_kv("recovery_in_progress", mg_ctrl->isRecoveryInProgress() ? "true" : "false");
      }

      // W6: Time since error onset
      if (i < MAX_MOTORS && motor_error_state_[i]) {
        auto error_duration = std::chrono::steady_clock::now() - motor_error_onset_time_[i];
        double error_seconds = std::chrono::duration<double>(error_duration).count();
        add_kv("error_duration_s", std::to_string(error_seconds));
      }

      // motor-cpu-burn-fix task 5.2: per-motor CAN failure count for diagnostics
      if (i < MAX_MOTORS) {
        add_kv("consecutive_failures",
               std::to_string(motor_absence_[i].consecutive_failures));
      }

      diag_msg.status.push_back(motor_diag);
    }

    // motor-cpu-burn-fix task 5.2: loop-level diagnostics entry
    {
      auto loop_end = std::chrono::steady_clock::now();
      double loop_duration_ms = std::chrono::duration<double, std::milli>(
        loop_end - last_control_loop_tick_).count();

      diagnostic_msgs::msg::DiagnosticStatus loop_diag;
      loop_diag.hardware_id = "control_loop";
      loop_diag.name = "motor/control_loop";
      loop_diag.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
      loop_diag.message = "OK";

      auto add_kv = [&loop_diag](const std::string & key, const std::string & value) {
        diagnostic_msgs::msg::KeyValue kv;
        kv.key = key;
        kv.value = value;
        loop_diag.values.push_back(kv);
      };

      add_kv("loop_duration_ms", std::to_string(loop_duration_ms));
      add_kv("absent_motor_count",
             std::to_string(absence_count_absent(motor_absence_.data(), MAX_MOTORS)));

      diag_msg.status.push_back(loop_diag);
    }

    if (joint_state_pub_) {
      joint_state_pub_->publish(msg);
      // Debug log for joint states
      RCLCPP_DEBUG_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                            "Published joint_states: polled=%zu, skipped=%zu (busy/errored)",
                            polled_count, skipped_count);
    } else {
      RCLCPP_ERROR_ONCE(this->get_logger(), "joint_state_pub_ is null!");
    }

    // Publish motor diagnostics (task 5.5)
    if (motor_diagnostics_pub_) {
      motor_diagnostics_pub_->publish(diag_msg);
    }
  }

  /**
   * @brief Log periodic stats (temperature, health, command count)
   * Similar to camera temperature logging in cotton_detection node
   */
  void log_stats()
  {
    auto runtime = std::chrono::duration_cast<std::chrono::seconds>(
      std::chrono::steady_clock::now() - startup_time_).count();

    int hours = runtime / 3600;
    int minutes = (runtime % 3600) / 60;
    int seconds = runtime % 60;

    RCLCPP_INFO(this->get_logger(), " ");
    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(this->get_logger(), "📊 MOTOR CONTROL STATS (uptime: %02d:%02d:%02d)", hours, minutes, seconds);
    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(this->get_logger(), "🔧 Motors initialized: %zu", controllers_.size());
    RCLCPP_INFO(this->get_logger(), "📝 Total position commands: %zu", total_position_commands_);
    RCLCPP_INFO(this->get_logger(), "🔄 Total velocity commands: %zu", total_velocity_commands_);

    // Check if any motors are available
    if (controllers_.empty()) {
      RCLCPP_WARN(this->get_logger(), "⚠️  No motors initialized - cannot show per-motor stats");
      RCLCPP_INFO(this->get_logger(), " ");
      return;
    }

    // Log temperature and health for each motor
    RCLCPP_INFO(this->get_logger(), "📊 Per-motor status:");
    double max_temp = 0.0;
    bool any_unavailable = false;
    bool any_status_warnings = false;
    std::string unavailable_list;

    // Build JSON motor array alongside human-readable logs
    nlohmann::json motors_json = nlohmann::json::array();
    double vbus_v = 0.0;  // Track max voltage as approximate vbus

    for (size_t i = 0; i < controllers_.size(); ++i) {
      // Skip unavailable motors
      if (controllers_[i] == nullptr ||
          (i < MAX_MOTORS && !motor_available_[i])) {
        RCLCPP_INFO(this->get_logger(), "⛔ %s: UNAVAILABLE", joint_names_[i].c_str());
        any_unavailable = true;
        if (!unavailable_list.empty()) unavailable_list += ", ";
        unavailable_list += joint_names_[i];

        // Add unavailable motor to JSON
        nlohmann::json motor_j;
        motor_j["joint"] = joint_names_[i];
        motor_j["ok"] = false;
        motor_j["temp_c"] = 0.0;
        motor_j["voltage_v"] = 0.0;
        motor_j["current_a"] = 0.0;
        motor_j["health"] = 0.0;
        motor_j["err_flags"] = 0;
        motor_j["cmds"] = {{"rx", 0}, {"tx_ok", 0}, {"tx_fail", 0}, {"reached", 0}, {"timeout", 0}};
        motor_j["warnings"] = nlohmann::json::array();
        motors_json.push_back(motor_j);
        continue;
      }

      auto status = controllers_[i]->get_status();

      // Track max temp for summary
      if (status.temperature > max_temp) {
        max_temp = status.temperature;
      }

      // Track voltage for vbus approximation
      if (status.voltage > vbus_v) {
        vbus_v = status.voltage;
      }

      // Determine status emoji
      std::string temp_emoji = "✅";
      if (status.temperature > 70.0) {
        temp_emoji = "🔴";
        any_status_warnings = true;
      } else if (status.temperature > 60.0) {
        temp_emoji = "🟡";
      }

      if (i < MAX_MOTORS) {
        RCLCPP_INFO(this->get_logger(),
          "%s %s: 🌡️ %.1f°C | ⚡ %.1fV | 💪 %.2fA | ❤️ %.0f%% | 🎯 rx=%llu ok=%llu fail=%llu | ✅ reach=%llu ⏱ %llu",
          temp_emoji.c_str(),
          joint_names_[i].c_str(),
          status.temperature,
          status.voltage,
          status.current,
          status.health_score * 100.0,
          static_cast<unsigned long long>(pos_cmd_received_[i]),
          static_cast<unsigned long long>(pos_cmd_sent_ok_[i]),
          static_cast<unsigned long long>(pos_cmd_sent_fail_[i]),
          static_cast<unsigned long long>(pos_cmd_reached_ok_[i]),
          static_cast<unsigned long long>(pos_cmd_reached_timeout_[i]));
      } else {
        RCLCPP_INFO(this->get_logger(),
          "%s %s: 🌡️ %.1f°C | ⚡ %.1fV | 💪 %.2fA | ❤️ %.0f%%",
          temp_emoji.c_str(),
          joint_names_[i].c_str(),
          status.temperature,
          status.voltage,
          status.current,
          status.health_score * 100.0);
      }

      // Build per-motor JSON
      nlohmann::json motor_j;
      motor_j["joint"] = joint_names_[i];
      motor_j["ok"] = true;
      motor_j["temp_c"] = status.temperature;
      motor_j["voltage_v"] = status.voltage;
      motor_j["current_a"] = status.current;
      motor_j["health"] = status.health_score;
      motor_j["err_flags"] = status.error_code;
      if (i < MAX_MOTORS) {
        motor_j["cmds"] = {
          {"rx", pos_cmd_received_[i]},
          {"tx_ok", pos_cmd_sent_ok_[i]},
          {"tx_fail", pos_cmd_sent_fail_[i]},
          {"reached", pos_cmd_reached_ok_[i]},
          {"timeout", pos_cmd_reached_timeout_[i]}
        };
      } else {
        motor_j["cmds"] = {{"rx", 0}, {"tx_ok", 0}, {"tx_fail", 0}, {"reached", 0}, {"timeout", 0}};
      }

      // Add warnings
      nlohmann::json warnings_json = nlohmann::json::array();
      if (!status.warnings.empty()) {
        for (const auto& warning : status.warnings) {
          RCLCPP_WARN(this->get_logger(), "   ⚠️  %s: %s",
                      joint_names_[i].c_str(), warning.c_str());
          warnings_json.push_back(warning);
        }
        any_status_warnings = true;
      }
      motor_j["warnings"] = warnings_json;
      motors_json.push_back(motor_j);
    }

    // Summary lines
    RCLCPP_INFO(this->get_logger(), "📊 Max temp: %.1f°C", max_temp);
    if (any_unavailable) {
      RCLCPP_WARN(this->get_logger(), "⚠️  Unavailable motors: %s", unavailable_list.c_str());
    }
    if (any_status_warnings) {
      RCLCPP_WARN(this->get_logger(), "⚠️  One or more motors reported warnings");
    }

    // Temperature threshold warnings
    if (max_temp > 80.0) {
      RCLCPP_ERROR(this->get_logger(),
        "🔴 CRITICAL: Motor temperature %.1f°C exceeds 80°C! Consider cooldown.", max_temp);
    } else if (max_temp > 70.0) {
      RCLCPP_WARN(this->get_logger(),
        "🟡 WARNING: Motor temperature %.1f°C approaching limit (80°C)", max_temp);
    }

    // Emit motor_health JSON line (structured logging)
    {
      auto health_json = pragati::json_envelope("motor_health", this->get_logger().get_name());
      health_json["uptime_s"] = runtime;
      health_json["vbus_v"] = vbus_v;
      health_json["degraded"] = degraded_mode_active_;
      health_json["motors"] = motors_json;

      RCLCPP_INFO(this->get_logger(), "%s", health_json.dump().c_str());
    }

    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════════════════");
  }

  void enable_callback(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response)
  {
    bool all_success = true;
    std::string message = "";

    for (size_t i = 0; i < controllers_.size(); ++i) {
      if (controllers_[i] == nullptr) {
        continue;
      }
      if (!controllers_[i]->set_enabled(true)) {
        all_success = false;
        if (i < MAX_MOTORS) motor_enabled_flags_[i] = false;
        message += "Failed motor " + std::to_string(i) + "; ";
      } else {
        if (i < MAX_MOTORS) motor_enabled_flags_[i] = true;
      }
    }

    response->success = all_success;
    response->message = all_success ? "All motors enabled" : message;

    RCLCPP_INFO(this->get_logger(), "%s", response->message.c_str());
  }

  void disable_callback(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response)
  {
    bool all_success = true;
    std::string message = "";

    for (size_t i = 0; i < controllers_.size(); ++i) {
      if (controllers_[i] == nullptr) {
        continue;
      }
      if (!controllers_[i]->set_enabled(false)) {
        all_success = false;
        message += "Failed motor " + std::to_string(i) + "; ";
      }
      if (i < MAX_MOTORS) {
        motor_enabled_flags_[i] = false;
      }
    }

    response->success = all_success;
    response->message = all_success ? "All motors disabled" : message;

    RCLCPP_INFO(this->get_logger(), "%s", response->message.c_str());
  }

  // --------------------------------------------------------------------------
  // Motor Config Service Callbacks (motor-config-ux)
  // --------------------------------------------------------------------------

  void motorCommandCallback(
    const std::shared_ptr<motor_control_msgs::srv::MotorCommand::Request> request,
    std::shared_ptr<motor_control_msgs::srv::MotorCommand::Response> response)
  {
    response->success = false;

    size_t idx = findMotorByCanId(request->motor_id);
    if (idx == SIZE_MAX) {
      response->error_message = "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
      RCLCPP_WARN(this->get_logger(), "motor_command: %s", response->error_message.c_str());
      return;
    }

    if (controllers_[idx] == nullptr) {
      response->error_message = "Motor controller is null";
      return;
    }

    bool result = false;
    switch (request->command_type) {
      case motor_control_msgs::srv::MotorCommand::Request::TORQUE:
        result = controllers_[idx]->torqueClosedLoop(request->value);
        break;
      case motor_control_msgs::srv::MotorCommand::Request::SPEED:
        result = controllers_[idx]->speedClosedLoop(request->value);
        break;
      case motor_control_msgs::srv::MotorCommand::Request::MULTI_ANGLE_1:
        result = controllers_[idx]->multiLoopAngle1(request->value);
        break;
      case motor_control_msgs::srv::MotorCommand::Request::MULTI_ANGLE_2:
        result = controllers_[idx]->multiLoopAngle2(request->value, request->max_speed);
        break;
      case motor_control_msgs::srv::MotorCommand::Request::SINGLE_ANGLE_1:
        result = controllers_[idx]->singleLoopAngle1(request->value, request->direction);
        break;
      case motor_control_msgs::srv::MotorCommand::Request::SINGLE_ANGLE_2:
        result = controllers_[idx]->singleLoopAngle2(request->value, request->max_speed, request->direction);
        break;
      case motor_control_msgs::srv::MotorCommand::Request::INCREMENT_1:
        result = controllers_[idx]->incrementAngle1(request->value);
        break;
      case motor_control_msgs::srv::MotorCommand::Request::INCREMENT_2:
        result = controllers_[idx]->incrementAngle2(request->value, request->max_speed);
        break;
      default:
        response->error_message = "Invalid command_type: " + std::to_string(request->command_type);
        return;
    }

    if (!result) {
      response->error_message = "Motor command failed";
      RCLCPP_ERROR(this->get_logger(), "motor_command: CAN command failed for motor_id=%d type=%d",
                   request->motor_id, request->command_type);
      return;
    }

    // Populate response with current motor status
    auto status = controllers_[idx]->get_status();
    response->success = true;
    response->temperature = static_cast<int8_t>(status.temperature);
    response->torque_current = static_cast<int16_t>(status.current);
    response->speed = 0;  // Not directly available from MotorStatus; real-time data via WebSocket
    response->encoder = 0;  // Not directly available from MotorStatus; real-time data via WebSocket

    RCLCPP_INFO(this->get_logger(), "motor_command: motor_id=%d type=%d value=%.2f success",
                request->motor_id, request->command_type, request->value);
  }

  void motorLifecycleCallback(
    const std::shared_ptr<motor_control_msgs::srv::MotorLifecycle::Request> request,
    std::shared_ptr<motor_control_msgs::srv::MotorLifecycle::Response> response)
  {
    response->success = false;
    response->motor_state = motor_control_msgs::srv::MotorLifecycle::Response::STATE_UNKNOWN;

    size_t idx = findMotorByCanId(request->motor_id);
    if (idx == SIZE_MAX) {
      response->error_message = "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
      RCLCPP_WARN(this->get_logger(), "motor_lifecycle: %s", response->error_message.c_str());
      return;
    }

    if (controllers_[idx] == nullptr) {
      response->error_message = "Motor controller is null";
      return;
    }

    bool result = false;
    switch (request->action) {
      case motor_control_msgs::srv::MotorLifecycle::Request::ON:
        result = controllers_[idx]->set_enabled(true);
        response->motor_state = result
          ? motor_control_msgs::srv::MotorLifecycle::Response::STATE_RUNNING
          : motor_control_msgs::srv::MotorLifecycle::Response::STATE_ERROR;
        break;
      case motor_control_msgs::srv::MotorLifecycle::Request::OFF:
        result = controllers_[idx]->set_enabled(false);
        response->motor_state = result
          ? motor_control_msgs::srv::MotorLifecycle::Response::STATE_OFF
          : motor_control_msgs::srv::MotorLifecycle::Response::STATE_ERROR;
        break;
      case motor_control_msgs::srv::MotorLifecycle::Request::STOP:
        result = controllers_[idx]->stop();
        response->motor_state = result
          ? motor_control_msgs::srv::MotorLifecycle::Response::STATE_STOPPED
          : motor_control_msgs::srv::MotorLifecycle::Response::STATE_ERROR;
        break;
      case motor_control_msgs::srv::MotorLifecycle::Request::REBOOT:
      {
        controllers_[idx]->set_enabled(false);
        // Non-blocking reboot: use a one-shot timer to re-enable after 500ms
        // instead of blocking the service callback thread with sleep_for.
        reboot_timer_ = this->create_wall_timer(
            std::chrono::milliseconds(500),
            [this, idx]() {
              bool re_enabled = controllers_[idx]->set_enabled(true);
              if (re_enabled) {
                RCLCPP_INFO(this->get_logger(), "Motor %zu re-enabled after reboot delay", idx);
              } else {
                RCLCPP_ERROR(this->get_logger(), "Motor %zu failed to re-enable after reboot", idx);
              }
              // Cancel so we only fire once
              if (reboot_timer_) {
                reboot_timer_->cancel();
              }
            });
        // Respond immediately — re-enable happens asynchronously
        result = true;
        response->motor_state = motor_control_msgs::srv::MotorLifecycle::Response::STATE_RUNNING;
        RCLCPP_INFO(this->get_logger(), "Motor %zu reboot initiated (re-enable in 500ms)", idx);
        break;
      }
      case motor_control_msgs::srv::MotorLifecycle::Request::SAVE_PID_ROM:
        {
          auto pid = controllers_[idx]->readPID();
          if (pid.has_value()) {
            result = controllers_[idx]->writePIDToROM(pid.value());
          }
        }
        break;
      case motor_control_msgs::srv::MotorLifecycle::Request::SAVE_ZERO_ROM:
        result = controllers_[idx]->setCurrentPositionAsZero();
        break;
      default:
        response->error_message = "Invalid lifecycle action: " + std::to_string(request->action);
        return;
    }

    if (!result) {
      response->error_message = "Lifecycle action failed";
      response->motor_state = motor_control_msgs::srv::MotorLifecycle::Response::STATE_ERROR;
      RCLCPP_ERROR(this->get_logger(), "motor_lifecycle: action=%d failed for motor_id=%d",
                   request->action, request->motor_id);
      return;
    }

    response->success = true;
    RCLCPP_INFO(this->get_logger(), "motor_lifecycle: motor_id=%d action=%d success (state=%d)",
                request->motor_id, request->action, response->motor_state);
  }

  void writeMotorLimitsCallback(
    const std::shared_ptr<motor_control_msgs::srv::WriteMotorLimits::Request> request,
    std::shared_ptr<motor_control_msgs::srv::WriteMotorLimits::Response> response)
  {
    response->success = false;

    size_t idx = findMotorByCanId(request->motor_id);
    if (idx == SIZE_MAX) {
      response->error_message = "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
      RCLCPP_WARN(this->get_logger(), "write_motor_limits: %s", response->error_message.c_str());
      return;
    }

    if (controllers_[idx] == nullptr) {
      response->error_message = "Motor controller is null";
      return;
    }

    bool all_ok = true;
    if (request->set_max_torque) {
      if (!controllers_[idx]->writeMaxTorqueCurrentRAM(request->max_torque_ratio)) {
        response->error_message = "Failed to write max torque current";
        all_ok = false;
      }
    }
    if (request->set_acceleration) {
      if (!controllers_[idx]->setAcceleration(request->acceleration)) {
        if (all_ok) response->error_message = "Failed to write acceleration";
        all_ok = false;
      }
    }

    response->success = all_ok;

    if (all_ok) {
      RCLCPP_INFO(this->get_logger(), "write_motor_limits: motor_id=%d success", request->motor_id);
    } else {
      RCLCPP_ERROR(this->get_logger(), "write_motor_limits: motor_id=%d failed: %s",
                   request->motor_id, response->error_message.c_str());
    }
  }

  void writeEncoderZeroCallback(
    const std::shared_ptr<motor_control_msgs::srv::WriteEncoderZero::Request> request,
    std::shared_ptr<motor_control_msgs::srv::WriteEncoderZero::Response> response)
  {
    response->success = false;

    size_t idx = findMotorByCanId(request->motor_id);
    if (idx == SIZE_MAX) {
      response->error_message = "Motor with CAN ID " + std::to_string(request->motor_id) + " not found";
      RCLCPP_WARN(this->get_logger(), "write_encoder_zero: %s", response->error_message.c_str());
      return;
    }

    if (controllers_[idx] == nullptr) {
      response->error_message = "Motor controller is null";
      return;
    }

    bool result = false;
    if (request->mode == motor_control_msgs::srv::WriteEncoderZero::Request::SET_VALUE) {
      result = controllers_[idx]->writeEncoderOffsetToROM(request->encoder_value);
    } else if (request->mode == motor_control_msgs::srv::WriteEncoderZero::Request::SET_CURRENT_POS) {
      result = controllers_[idx]->setCurrentPositionAsZero();
    } else {
      response->error_message = "Invalid encoder zero mode: " + std::to_string(request->mode);
      return;
    }

    if (!result) {
      response->error_message = "Failed to set encoder zero";
      RCLCPP_ERROR(this->get_logger(), "write_encoder_zero: failed for motor_id=%d mode=%d",
                   request->motor_id, request->mode);
      return;
    }

    response->success = true;
    RCLCPP_INFO(this->get_logger(), "write_encoder_zero: motor_id=%d mode=%d success",
                request->motor_id, request->mode);
  }

  // --------------------------------------------------------------------------
  // Step Response Test Action Callbacks
  // --------------------------------------------------------------------------

  rclcpp_action::GoalResponse handleStepResponseGoal(
    const rclcpp_action::GoalUUID & /*uuid*/,
    std::shared_ptr<const StepResponseTest::Goal> goal)
  {
    // Validate motor exists
    size_t idx = findMotorByCanId(goal->motor_id);
    if (idx == SIZE_MAX) {
      RCLCPP_WARN(this->get_logger(),
        "step_response_test: REJECTED - motor_id=%d not found", goal->motor_id);
      return rclcpp_action::GoalResponse::REJECT;
    }

    if (controllers_[idx] == nullptr ||
        (idx < MAX_MOTORS && !motor_available_[idx])) {
      RCLCPP_WARN(this->get_logger(),
        "step_response_test: REJECTED - motor_id=%d unavailable", goal->motor_id);
      return rclcpp_action::GoalResponse::REJECT;
    }

    // Validate parameters
    if (goal->duration_seconds <= 0.0f) {
      RCLCPP_WARN(this->get_logger(),
        "step_response_test: REJECTED - duration_seconds must be > 0");
      return rclcpp_action::GoalResponse::REJECT;
    }

    if (std::abs(goal->step_size_degrees) < 0.01f) {
      RCLCPP_WARN(this->get_logger(),
        "step_response_test: REJECTED - step_size_degrees too small");
      return rclcpp_action::GoalResponse::REJECT;
    }

    // Check if another step test is already running
    {
      std::lock_guard<std::mutex> lock(step_test_mutex_);
      if (step_test_running_) {
        RCLCPP_WARN(this->get_logger(),
          "step_response_test: REJECTED - another test is already running");
        return rclcpp_action::GoalResponse::REJECT;
      }
    }

    RCLCPP_INFO(this->get_logger(),
      "step_response_test: ACCEPTED - motor_id=%d step=%.1f deg duration=%.1f s",
      goal->motor_id, goal->step_size_degrees, goal->duration_seconds);
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handleStepResponseCancel(
    const std::shared_ptr<GoalHandleStepResponse> /*goal_handle*/)
  {
    RCLCPP_INFO(this->get_logger(), "step_response_test: cancel requested");
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handleStepResponseAccepted(
    const std::shared_ptr<GoalHandleStepResponse> goal_handle)
  {
    // With MultiThreadedExecutor + Reentrant processing callback group,
    // this accepted callback already runs in an executor thread.
    // Execute directly instead of spawning a raw std::thread.
    executeStepResponseTest(goal_handle);
  }

  /**
   * @brief Execute step response test (runs in executor thread via processing callback group)
   *
   * Sequence:
   *   1. Record initial position
   *   2. Command step (initial_pos + step_size_degrees converted to joint units)
   *   3. Collect position/velocity/current data at 10 Hz
   *   4. Publish feedback with progress
   *   5. Safety: abort if position deviation > 2x step_size or temperature > 80C
   *   6. On completion/abort: hold current position, return data
   */
  void executeStepResponseTest(
    const std::shared_ptr<GoalHandleStepResponse> goal_handle)
  {
    // Mark test as running
    {
      std::lock_guard<std::mutex> lock(step_test_mutex_);
      step_test_running_ = true;
    }

    auto result = std::make_shared<StepResponseTest::Result>();
    result->success = false;

    const auto goal = goal_handle->get_goal();
    const size_t idx = findMotorByCanId(goal->motor_id);

    // Safety lambda: hold position and clean up
    auto cleanup = [&](double hold_position) {
      // Command motor to hold at the given position
      if (idx < controllers_.size() && controllers_[idx] != nullptr) {
        controllers_[idx]->set_position(hold_position, 0.0, 0.0);
      }
      std::lock_guard<std::mutex> lock(step_test_mutex_);
      step_test_running_ = false;
    };

    // Validate motor is still available
    if (idx == SIZE_MAX || controllers_[idx] == nullptr) {
      result->error_message = "Motor not available";
      cleanup(0.0);
      goal_handle->abort(result);
      return;
    }

    // Get temperature limit from motor config
    const double temp_limit = controllers_[idx]->get_configuration().limits.temperature_max;

    // Record initial position (in joint units — rotations for MG6010)
    const double initial_position = controllers_[idx]->get_position();

    // Convert step size from degrees to joint units (rotations)
    // MG6010 uses rotations as joint units: 1 rotation = 360 degrees
    const double step_size_rotations = static_cast<double>(goal->step_size_degrees) / 360.0;
    const double target_position = initial_position + step_size_rotations;
    const double max_deviation = std::abs(step_size_rotations) * 2.0;

    // Convert target to degrees for result setpoint
    result->setpoint = initial_position * 360.0 + static_cast<double>(goal->step_size_degrees);

    RCLCPP_INFO(this->get_logger(),
      "step_response_test: START motor_id=%d initial=%.4f rot target=%.4f rot step=%.1f deg "
      "duration=%.1f s temp_limit=%.0f C",
      goal->motor_id, initial_position, target_position,
      goal->step_size_degrees, goal->duration_seconds, temp_limit);

    // Pre-allocate data vectors (10 Hz * duration)
    const double sample_rate_hz = 10.0;
    const double duration_s = static_cast<double>(goal->duration_seconds);
    const size_t estimated_samples = static_cast<size_t>(sample_rate_hz * duration_s) + 10;
    result->timestamps.reserve(estimated_samples);
    result->positions.reserve(estimated_samples);
    result->velocities.reserve(estimated_samples);
    result->currents.reserve(estimated_samples);

    // Command the step
    if (!controllers_[idx]->set_position(target_position, 0.0, 0.0)) {
      result->error_message = "Failed to command step position";
      cleanup(initial_position);
      goal_handle->abort(result);
      RCLCPP_ERROR(this->get_logger(), "step_response_test: %s", result->error_message.c_str());
      return;
    }

    // Mark motor as busy to prevent polling interference
    if (idx < MAX_MOTORS) {
      motor_busy_flags_[idx] = true;
      motor_command_times_[idx] = std::chrono::steady_clock::now();
      last_commanded_positions_[idx] = target_position;
    }

    // Data collection loop at 10 Hz
    const auto test_start = std::chrono::steady_clock::now();
    const auto sample_period = std::chrono::duration<double>(1.0 / sample_rate_hz);
    auto next_sample_time = test_start;

    while (rclcpp::ok() && !deactivating_.load(std::memory_order_acquire)) {
      // Check for cancellation
      if (goal_handle->is_canceling()) {
        RCLCPP_INFO(this->get_logger(), "step_response_test: CANCELED by client");
        // Return partial data
        result->success = false;
        result->error_message = "Test canceled by client";
        cleanup(target_position);  // Hold at step target
        goal_handle->canceled(result);
        return;
      }

      const auto now = std::chrono::steady_clock::now();
      const double elapsed_s = std::chrono::duration<double>(now - test_start).count();

      // Check duration complete
      if (elapsed_s >= duration_s) {
        break;
      }

      // Wait until next sample time
      if (now < next_sample_time) {
        std::this_thread::sleep_until(next_sample_time);
      }
      next_sample_time += std::chrono::duration_cast<std::chrono::steady_clock::duration>(sample_period);

      // Read motor state
      const double current_position = controllers_[idx]->get_position();
      const double current_velocity = controllers_[idx]->get_velocity();
      const auto status = controllers_[idx]->get_status();

      // Convert to degrees for recording
      const double position_deg = current_position * 360.0;
      const double velocity_deg_s = current_velocity * 360.0;

      // Record data point
      const double sample_time = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - test_start).count();
      result->timestamps.push_back(sample_time);
      result->positions.push_back(position_deg);
      result->velocities.push_back(velocity_deg_s);
      result->currents.push_back(status.current);

      // --- Safety checks (Task 1.4c) ---

      // Check position deviation: abort if > 2x step size from target
      const double deviation = std::abs(current_position - target_position);
      if (deviation > max_deviation && max_deviation > 0.001) {
        result->error_message = "Position deviation " +
          std::to_string(deviation * 360.0) + " deg exceeds safety limit " +
          std::to_string(max_deviation * 360.0) + " deg (2x step size)";
        RCLCPP_ERROR(this->get_logger(), "step_response_test: ABORT - %s",
                     result->error_message.c_str());
        cleanup(target_position);  // Hold at step target
        goal_handle->abort(result);
        return;
      }

      // Check temperature: abort if > configured limit (default 80C)
      if (status.temperature > temp_limit) {
        result->error_message = "Motor temperature " +
          std::to_string(status.temperature) + " C exceeds limit " +
          std::to_string(temp_limit) + " C";
        RCLCPP_ERROR(this->get_logger(), "step_response_test: ABORT - %s",
                     result->error_message.c_str());
        cleanup(target_position);  // Hold at step target
        goal_handle->abort(result);
        return;
      }

      // Publish feedback
      auto feedback = std::make_shared<StepResponseTest::Feedback>();
      feedback->progress_percent = static_cast<float>(
        std::min(100.0, (elapsed_s / duration_s) * 100.0));
      feedback->current_position = position_deg;
      feedback->elapsed_seconds = elapsed_s;
      goal_handle->publish_feedback(feedback);
    }

    // Test completed successfully
    result->success = true;
    cleanup(target_position);  // Hold at step target position
    goal_handle->succeed(result);

    RCLCPP_INFO(this->get_logger(),
      "step_response_test: COMPLETE motor_id=%d samples=%zu",
      goal->motor_id, result->timestamps.size());
  }

  // --------------------------------------------------------------------------
  // JointPositionCommand Action Callbacks (task 3.4, 3.6)
  // --------------------------------------------------------------------------

  rclcpp_action::GoalResponse handleJointPosCmdGoal(
    const rclcpp_action::GoalUUID & /*uuid*/,
    std::shared_ptr<const JointPosCmd::Goal> goal)
  {
    // Map joint_id -> motor index (same logic as service callback)
    size_t idx = controllers_.size();
    const std::string joint_name = "joint" + std::to_string(goal->joint_id);
    for (size_t i = 0; i < joint_names_.size(); ++i) {
      if (joint_names_[i] == joint_name) {
        idx = i;
        break;
      }
    }
    if (idx >= controllers_.size() && goal->joint_id >= 0) {
      const size_t as_index = static_cast<size_t>(goal->joint_id);
      if (as_index < controllers_.size()) idx = as_index;
    }
    if (idx >= controllers_.size()) {
      RCLCPP_WARN(this->get_logger(),
        "joint_position_command action: REJECTED - unknown joint_id=%ld", goal->joint_id);
      return rclcpp_action::GoalResponse::REJECT;
    }
    if (controllers_[idx] == nullptr || (idx < MAX_MOTORS && !motor_available_[idx])) {
      RCLCPP_WARN(this->get_logger(),
        "joint_position_command action: REJECTED - motor unavailable for joint_id=%ld", goal->joint_id);
      return rclcpp_action::GoalResponse::REJECT;
    }
    if (idx < MAX_MOTORS && !motor_enabled_flags_[idx]) {
      RCLCPP_WARN(this->get_logger(),
        "joint_position_command action: REJECTED - motor disabled for joint_id=%ld", goal->joint_id);
      return rclcpp_action::GoalResponse::REJECT;
    }
    // Collision interlock
    if (checkJ3J4Interlock(idx, goal->target_position, "joint_position_command_action")) {
      RCLCPP_WARN(this->get_logger(),
        "joint_position_command action: REJECTED - J4 interlock (J3 in parking zone)");
      return rclcpp_action::GoalResponse::REJECT;
    }
    // Reject if this joint already has an active action command
    {
      std::unique_lock<std::mutex> lock(joint_pos_cmd_mutex_);
      if (idx < MAX_MOTORS && joint_pos_cmd_active_[idx]) {
        // The previous action may be processing a cancel/timeout — its feedback loop
        // runs at 50ms intervals thus cleanup may not have run yet.  Wait briefly
        // for the in-flight cleanup before rejecting.
        lock.unlock();
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
        lock.lock();
        if (joint_pos_cmd_active_[idx]) {
          RCLCPP_WARN(this->get_logger(),
            "joint_position_command action: REJECTED - joint_id=%ld already has active command", goal->joint_id);
          return rclcpp_action::GoalResponse::REJECT;
        }
        // Cleanup completed during wait — fall through to accept
        RCLCPP_INFO(this->get_logger(),
          "joint_position_command action: previous action completed during wait, accepting joint_id=%ld", goal->joint_id);
      }
    }

    RCLCPP_INFO(this->get_logger(),
      "joint_position_command action: ACCEPTED joint_id=%ld target=%.4f max_vel=%.2f",
      goal->joint_id, goal->target_position, goal->max_velocity);
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handleJointPosCmdCancel(
    const std::shared_ptr<GoalHandleJointPosCmd> goal_handle)
  {
    if (goal_handle && goal_handle->get_goal()) {
      const auto goal = goal_handle->get_goal();
      RCLCPP_INFO(this->get_logger(),
        "joint_position_command action: cancel requested joint_id=%ld target=%.4f",
        goal->joint_id, goal->target_position);
    } else {
      RCLCPP_INFO(this->get_logger(), "joint_position_command action: cancel requested (goal unavailable)");
    }
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handleJointPosCmdAccepted(
    const std::shared_ptr<GoalHandleJointPosCmd> goal_handle)
  {
    // With MultiThreadedExecutor + Reentrant processing callback group,
    // execute directly in the executor thread.
    executeJointPositionCommand(goal_handle);
  }

  /**
   * @brief Execute joint position command (runs in executor thread via processing callback group)
   *
   * Replaces the blocking while(rclcpp::ok()) loop from the service callback.
   * Publishes position feedback at >=10Hz. Supports cancellation with safe decel.
   */
  void executeJointPositionCommand(
    const std::shared_ptr<GoalHandleJointPosCmd> goal_handle)
  {
    auto result = std::make_shared<JointPosCmd::Result>();
    result->success = false;

    const auto goal = goal_handle->get_goal();

    // Resolve joint index (same as goal handler)
    size_t idx = controllers_.size();
    const std::string joint_name = "joint" + std::to_string(goal->joint_id);
    for (size_t i = 0; i < joint_names_.size(); ++i) {
      if (joint_names_[i] == joint_name) {
        idx = i;
        break;
      }
    }
    if (idx >= controllers_.size() && goal->joint_id >= 0) {
      const size_t as_index = static_cast<size_t>(goal->joint_id);
      if (as_index < controllers_.size()) idx = as_index;
    }

    // Mark joint as active
    {
      std::lock_guard<std::mutex> lock(joint_pos_cmd_mutex_);
      if (idx < MAX_MOTORS) joint_pos_cmd_active_[idx] = true;
    }

    // Cleanup lambda: clear active flag and motion state
    auto cleanup = [&]() {
      if (idx < MAX_MOTORS) {
        {
          std::lock_guard<std::mutex> lock(motion_mutex_);
          motion_pending_[idx] = false;
          motion_in_tolerance_[idx] = false;
          motor_busy_flags_[idx] = false;
        }
        std::lock_guard<std::mutex> lock(joint_pos_cmd_mutex_);
        joint_pos_cmd_active_[idx] = false;
      }
    };

    // Validate motor still available
    if (idx >= controllers_.size() || controllers_[idx] == nullptr) {
      result->reason = "Motor not available";
      cleanup();
      goal_handle->abort(result);
      return;
    }

    const double target = goal->target_position;
    const double start_position = controllers_[idx]->get_position();
    const double command_delta = target - start_position;
    const double timeout_s = std::chrono::duration_cast<std::chrono::duration<double>>(
      motion_feedback_timeout_).count();
    const double settle_s = std::chrono::duration_cast<std::chrono::duration<double>>(
      motion_feedback_settle_time_).count();
    const double tolerance = (idx < MAX_MOTORS)
      ? motion_feedback_position_tolerance_by_motor_[idx]
      : motion_feedback_position_tolerance_;

    // Stats
    total_position_commands_++;
    if (idx < MAX_MOTORS) pos_cmd_received_[idx]++;

    // Mark motor busy
    if (idx < MAX_MOTORS) {
      motor_busy_flags_[idx] = true;
      motor_command_times_[idx] = std::chrono::steady_clock::now();
      last_commanded_positions_[idx] = target;
    }

    // Send command
    const double max_vel = goal->max_velocity;
    const bool ok = controllers_[idx]->set_position(target, max_vel, 0.0);
    if (!ok) {
      if (idx < MAX_MOTORS) pos_cmd_sent_fail_[idx]++;
      handle_motor_failure(idx, "position", target, "CAN_COMMAND_FAILED", __func__);
      result->reason = "Command send failed";
      cleanup();
      goal_handle->abort(result);
      return;
    }

    RCLCPP_INFO(this->get_logger(),
      "joint_position_command action: START joint=%s joint_id=%ld index=%zu start=%.4f target=%.4f delta=%.4f max_vel=%.2f tol=%.4f settle=%.3fs timeout=%.3fs",
      joint_names_[idx].c_str(), goal->joint_id, idx, start_position, target,
      command_delta, max_vel, tolerance, settle_s, timeout_s);

    if (idx < MAX_MOTORS) {
      pos_cmd_sent_ok_[idx]++;
      motor_failure_count_[idx] = 0;
      {
        std::lock_guard<std::mutex> lock(motion_mutex_);
        motion_pending_[idx] = true;
        motion_target_positions_[idx] = target;
        motion_start_times_[idx] = std::chrono::steady_clock::now();
        motion_in_tolerance_[idx] = false;
      }
    }

    // Exempt watchdog during blocking position feedback loop (task 1.8)
    watchdog_exempt_.store(true, std::memory_order_release);

    // Feedback loop at ~20Hz (50ms period) — publishes >=10Hz feedback
    const auto start = std::chrono::steady_clock::now();
    bool in_tol = false;
    auto in_tol_since = start;
    const auto poll_period = std::chrono::milliseconds(50);
    auto next_progress_log = start + std::chrono::seconds(1);

    while (rclcpp::ok() && !deactivating_.load(std::memory_order_acquire)) {
      const auto now = std::chrono::steady_clock::now();
      const double elapsed_s = std::chrono::duration<double>(now - start).count();

      // Read current state
      const auto st = controllers_[idx]->get_status();
      const double pos = controllers_[idx]->get_position();
      result->actual_position = pos;

      // Update feedback snapshots (same as old service callback)
      {
        std::lock_guard<std::mutex> lock(motion_mutex_);
        if (idx < MAX_MOTORS) {
          last_feedback_valid_[idx] = st.hardware_connected;
          last_feedback_position_[idx] = pos;
          last_feedback_time_[idx] = now;
        }
      }

      // Publish feedback
      auto feedback = std::make_shared<JointPosCmd::Feedback>();
      feedback->current_position = pos;
      feedback->error_from_target = target - pos;
      feedback->elapsed_seconds = elapsed_s;
      goal_handle->publish_feedback(feedback);

      const double err = std::abs(pos - target);

      if (goal_handle->is_canceling()) {
        const double velocity = controllers_[idx]->get_velocity();
        RCLCPP_INFO(this->get_logger(),
          "joint_position_command action: CANCELING joint=%s joint_id=%ld elapsed=%.3fs pos=%.4f target=%.4f err=%.4f vel=%.4f current=%.3f temp=%.1f connected=%s — safe stop",
          joint_names_[idx].c_str(), goal->joint_id, elapsed_s, pos, target,
          err, velocity, st.current, st.temperature,
          st.hardware_connected ? "true" : "false");
        controllers_[idx]->stop();
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        result->success = false;
        result->reason = "CANCELLED";
        result->actual_position = controllers_[idx]->get_position();
        const double stopped_velocity = controllers_[idx]->get_velocity();
        RCLCPP_INFO(this->get_logger(),
          "joint_position_command action: CANCEL COMPLETE joint=%s joint_id=%ld final_pos=%.4f final_vel=%.4f",
          joint_names_[idx].c_str(), goal->joint_id,
          result->actual_position, stopped_velocity);
        watchdog_exempt_.store(false, std::memory_order_release);
        cleanup();
        goal_handle->canceled(result);
        return;
      }

      if (now >= next_progress_log) {
        const double velocity = controllers_[idx]->get_velocity();
        RCLCPP_INFO(this->get_logger(),
          "joint_position_command action: PROGRESS joint=%s joint_id=%ld elapsed=%.3fs pos=%.4f target=%.4f err=%.4f vel=%.4f current=%.3f temp=%.1f connected=%s in_tol=%s",
          joint_names_[idx].c_str(), goal->joint_id, elapsed_s, pos, target,
          err, velocity, st.current, st.temperature,
          st.hardware_connected ? "true" : "false",
          in_tol ? "true" : "false");
        next_progress_log = now + std::chrono::seconds(1);
      }

      // Check tolerance + settle
      if (st.hardware_connected) {
        const double tol = (idx < MAX_MOTORS) ? motion_feedback_position_tolerance_by_motor_[idx]
                                               : motion_feedback_position_tolerance_;
        if (err <= tol) {
          if (!in_tol) {
            in_tol = true;
            in_tol_since = now;
          } else if ((now - in_tol_since) >= motion_feedback_settle_time_) {
            if (idx < MAX_MOTORS) pos_cmd_reached_ok_[idx]++;
            result->success = true;
            result->reason = "REACHED";
            result->actual_position = pos;
            const double velocity = controllers_[idx]->get_velocity();
            const double in_tol_s = std::chrono::duration<double>(now - in_tol_since).count();
            RCLCPP_INFO(this->get_logger(),
              "joint_position_command action: REACHED joint=%s joint_id=%ld elapsed=%.3fs pos=%.4f target=%.4f err=%.4f vel=%.4f current=%.3f temp=%.1f connected=%s in_tol_for=%.3fs",
              joint_names_[idx].c_str(), goal->joint_id, elapsed_s, pos, target,
              err, velocity, st.current, st.temperature,
              st.hardware_connected ? "true" : "false", in_tol_s);
            watchdog_exempt_.store(false, std::memory_order_release);
            cleanup();
            goal_handle->succeed(result);
            return;
          }
        } else {
          in_tol = false;
        }
      }

      // Timeout
      if ((now - start) >= motion_feedback_timeout_) {
        if (idx < MAX_MOTORS) pos_cmd_reached_timeout_[idx]++;
        result->success = false;
        result->reason = "TIMEOUT";
        result->actual_position = pos;
        const double velocity = controllers_[idx]->get_velocity();
        RCLCPP_WARN(this->get_logger(),
          "joint_position_command action: TIMEOUT joint=%s joint_id=%ld elapsed=%.3fs pos=%.4f target=%.4f err=%.4f vel=%.4f current=%.3f temp=%.1f connected=%s timeout=%.3fs",
          joint_names_[idx].c_str(), goal->joint_id, elapsed_s, pos, target,
          err, velocity, st.current, st.temperature,
          st.hardware_connected ? "true" : "false", timeout_s);
        watchdog_exempt_.store(false, std::memory_order_release);
        cleanup();
        goal_handle->abort(result);
        return;
      }

      std::this_thread::sleep_for(poll_period);
    }

    // rclcpp shutting down
    watchdog_exempt_.store(false, std::memory_order_release);
    result->reason = "SHUTDOWN";
    RCLCPP_WARN(this->get_logger(),
      "joint_position_command action: SHUTDOWN joint=%s joint_id=%ld target=%.4f",
      idx < joint_names_.size() ? joint_names_[idx].c_str() : "unknown",
      goal->joint_id, target);
    cleanup();
    goal_handle->abort(result);
  }

  // --------------------------------------------------------------------------
  // JointHoming Action Callbacks (task 3.5, 3.6)
  // --------------------------------------------------------------------------

  rclcpp_action::GoalResponse handleJointHomingGoal(
    const rclcpp_action::GoalUUID & /*uuid*/,
    std::shared_ptr<const JointHomingAction::Goal> goal)
  {
    // Reject if homing is already in progress
    {
      std::lock_guard<std::mutex> lock(joint_homing_mutex_);
      if (joint_homing_active_) {
        RCLCPP_WARN(this->get_logger(),
          "joint_homing action: REJECTED - homing already in progress");
        return rclcpp_action::GoalResponse::REJECT;
      }
    }

    // Validate joint IDs (if specified)
    if (!goal->joint_ids.empty()) {
      for (const auto& jid : goal->joint_ids) {
        const std::string jname = "joint" + std::to_string(jid);
        bool found = false;
        for (const auto& name : joint_names_) {
          if (name == jname) { found = true; break; }
        }
        if (!found) {
          RCLCPP_WARN(this->get_logger(),
            "joint_homing action: REJECTED - unknown joint_id=%d", jid);
          return rclcpp_action::GoalResponse::REJECT;
        }
      }
    }

    RCLCPP_INFO(this->get_logger(),
      "joint_homing action: ACCEPTED (%zu joints requested)",
      goal->joint_ids.empty() ? controllers_.size() : goal->joint_ids.size());
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handleJointHomingCancel(
    const std::shared_ptr<GoalHandleJointHoming> /*goal_handle*/)
  {
    RCLCPP_INFO(this->get_logger(), "joint_homing action: cancel requested");
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handleJointHomingAccepted(
    const std::shared_ptr<GoalHandleJointHoming> goal_handle)
  {
    // With MultiThreadedExecutor + Reentrant processing callback group,
    // execute directly in the executor thread.
    executeJointHoming(goal_handle);
  }

  /**
   * @brief Execute joint homing (runs in executor thread via processing callback group)
   *
   * Non-blocking replacement for perform_motor_homing() called from constructor.
   * Publishes progress feedback per joint.
   */
  void executeJointHoming(
    const std::shared_ptr<GoalHandleJointHoming> goal_handle)
  {
    {
      std::lock_guard<std::mutex> lock(joint_homing_mutex_);
      joint_homing_active_ = true;
    }

    auto result = std::make_shared<JointHomingAction::Result>();
    result->success = false;

    auto cleanup = [&]() {
      std::lock_guard<std::mutex> lock(joint_homing_mutex_);
      joint_homing_active_ = false;
    };

    const auto goal = goal_handle->get_goal();

    // Build list of joints to home
    std::vector<size_t> joints_to_home;
    if (goal->joint_ids.empty()) {
      // Home all joints
      for (size_t i = 0; i < controllers_.size(); ++i) {
        if (controllers_[i] != nullptr) joints_to_home.push_back(i);
      }
    } else {
      for (const auto& jid : goal->joint_ids) {
        const std::string jname = "joint" + std::to_string(jid);
        for (size_t i = 0; i < joint_names_.size(); ++i) {
          if (joint_names_[i] == jname) {
            joints_to_home.push_back(i);
            break;
          }
        }
      }
    }

    if (joints_to_home.empty()) {
      result->reason = "No valid joints to home";
      cleanup();
      goal_handle->abort(result);
      return;
    }

    // Exempt watchdog during homing
    watchdog_exempt_.store(true, std::memory_order_release);

    const size_t total_joints = joints_to_home.size();
    size_t completed = 0;

    for (size_t ji = 0; ji < total_joints; ++ji) {
      const size_t idx = joints_to_home[ji];
      const std::string& jname = (idx < joint_names_.size()) ? joint_names_[idx] : "unknown";

      // Check for cancellation or deactivation (task 3.6 + lifecycle grace period)
      if (goal_handle->is_canceling() || deactivating_.load(std::memory_order_acquire)) {
        RCLCPP_INFO(this->get_logger(),
          "joint_homing action: CANCELING after %zu/%zu joints", completed, total_joints);
        // Stop the current motor safely
        if (controllers_[idx] != nullptr) controllers_[idx]->stop();
        result->success = false;
        result->reason = "CANCELLED";
        // Collect final positions for completed joints
        result->final_positions.clear();
        for (size_t k = 0; k <= ji && k < joints_to_home.size(); ++k) {
          const size_t kidx = joints_to_home[k];
          result->final_positions.push_back(
            controllers_[kidx] ? controllers_[kidx]->get_position() : 0.0);
        }
        watchdog_exempt_.store(false, std::memory_order_release);
        cleanup();
        goal_handle->canceled(result);
        return;
      }

      // Skip drive motors (same as perform_motor_homing)
      if (role_strategy_->isDriveMotor(jname)) {
        completed++;
        continue;
      }

      // Publish feedback: starting this joint
      auto feedback = std::make_shared<JointHomingAction::Feedback>();
      feedback->current_joint_id = static_cast<int32_t>(idx < joint_names_.size() ? idx : 0);
      feedback->progress_percent = static_cast<float>(completed * 100.0 / total_joints);
      feedback->status_message = "Homing " + jname + ": moving to zero";
      goal_handle->publish_feedback(feedback);

      // Get homing position
      double homing_pos = 0.0;
      if (idx < homing_positions_.size()) {
        homing_pos = homing_positions_[idx];
      }

      double pos_tol = motion_feedback_position_tolerance_;
      if (idx < MAX_MOTORS) {
        pos_tol = motion_feedback_position_tolerance_by_motor_[idx];
      }

      // Step 1: Move to motor's built-in zero
      if (!controllers_[idx]->set_position(0.0, 0.0, 0.0)) {
        RCLCPP_ERROR(this->get_logger(),
          "joint_homing action: failed to send zero command for %s", jname.c_str());
        result->reason = "Failed to command zero for " + jname;
        watchdog_exempt_.store(false, std::memory_order_release);
        cleanup();
        goal_handle->abort(result);
        return;
      }

      // Wait for motor to reach zero (non-blocking sleep with cancel checks)
      for (int w = 0; w < 40; ++w) {  // 40 * 50ms = 2000ms
        if (goal_handle->is_canceling() || deactivating_.load(std::memory_order_acquire)) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
      if (goal_handle->is_canceling() || deactivating_.load(std::memory_order_acquire)) continue;  // Will be caught at loop top

      // Update feedback: verifying
      feedback->status_message = "Homing " + jname + ": verifying zero";
      feedback->progress_percent = static_cast<float>((completed + 0.4) * 100.0 / total_joints);
      goal_handle->publish_feedback(feedback);

      double verify_pos = controllers_[idx]->get_position();
      std::this_thread::sleep_for(std::chrono::milliseconds(200));

      // Step 3: Move to final homing position if needed
      const double homing_err = verify_pos - homing_pos;
      if (std::abs(homing_err) > pos_tol) {
        feedback->status_message = "Homing " + jname + ": moving to homing position";
        feedback->progress_percent = static_cast<float>((completed + 0.6) * 100.0 / total_joints);
        goal_handle->publish_feedback(feedback);

        if (!controllers_[idx]->set_position(homing_pos, 0.0, 0.0)) {
          RCLCPP_ERROR(this->get_logger(),
            "joint_homing action: failed to move to homing pos for %s", jname.c_str());
          result->reason = "Failed to command homing position for " + jname;
          watchdog_exempt_.store(false, std::memory_order_release);
          cleanup();
          goal_handle->abort(result);
          return;
        }

        // Wait for motor to reach homing position (3s, cancel-aware)
        for (int w = 0; w < 60; ++w) {  // 60 * 50ms = 3000ms
          if (goal_handle->is_canceling() || deactivating_.load(std::memory_order_acquire)) break;
          std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
      }

      completed++;
      RCLCPP_INFO(this->get_logger(), "joint_homing action: %s homed (%zu/%zu)",
        jname.c_str(), completed, total_joints);
    }

    watchdog_exempt_.store(false, std::memory_order_release);

    // Collect final positions
    result->final_positions.clear();
    for (const auto& idx : joints_to_home) {
      result->final_positions.push_back(
        controllers_[idx] ? controllers_[idx]->get_position() : 0.0);
    }

    result->success = true;
    result->reason = "All joints homed";

    // Final feedback
    auto feedback = std::make_shared<JointHomingAction::Feedback>();
    feedback->progress_percent = 100.0f;
    feedback->status_message = "Homing complete";
    goal_handle->publish_feedback(feedback);

    cleanup();
    goal_handle->succeed(result);

    RCLCPP_INFO(this->get_logger(),
      "joint_homing action: COMPLETE (%zu joints homed)", total_joints);
  }

};

// Global node pointer for signal handler
std::shared_ptr<MG6010ControllerNode> g_node = nullptr;

// SSH disconnect: re-map SIGHUP to SIGTERM so the shared handler handles it
void sighup_to_sigterm(int) { raise(SIGTERM); }

int main(int argc, char** argv)
{
  // Shared handler covers SIGINT + SIGTERM; SIGHUP remapped to SIGTERM
  pragati::install_signal_handlers();
  std::signal(SIGHUP, sighup_to_sigterm);

  rclcpp::init(argc, argv);

  try {
    g_node = std::make_shared<MG6010ControllerNode>();

    // Auto-activate: configure + activate the lifecycle node
    bool auto_activate = g_node->get_parameter("auto_activate").as_bool();
    if (auto_activate) {
      RCLCPP_INFO(g_node->get_logger(), "Auto-activating lifecycle node...");
      auto state = g_node->trigger_transition(
        lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);
      if (state.id() != lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE) {
        RCLCPP_ERROR(g_node->get_logger(), "Failed to configure node (state: %s)", state.label().c_str());
        rclcpp::shutdown();
        return 1;
      }
      state = g_node->trigger_transition(
        lifecycle_msgs::msg::Transition::TRANSITION_ACTIVATE);
      if (state.id() != lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
        RCLCPP_ERROR(g_node->get_logger(), "Failed to activate node (state: %s)", state.label().c_str());
        rclcpp::shutdown();
        return 1;
      }
      RCLCPP_INFO(g_node->get_logger(), "Lifecycle node active");
    }

    // MultiThreadedExecutor with 4 threads matches RPi 4B core count.
    // Callback groups (safety, hardware, processing) ensure that safety-critical
    // callbacks are never blocked by long-running actions or diagnostics.
    // spin() blocks until rclcpp::shutdown() is triggered by signal handlers.
    rclcpp::executors::MultiThreadedExecutor executor(
      rclcpp::ExecutorOptions(), 4 /* num_threads */);
    executor.add_node(g_node->get_node_base_interface());
    executor.spin();

    if (pragati::shutdown_requested()) {
      RCLCPP_INFO(rclcpp::get_logger("motor_control"), "Signal received, shutting down...");
    }
  } catch (const std::exception& e) {
    RCLCPP_ERROR(rclcpp::get_logger("motor_control"), "Exception: %s", e.what());
  }

  // Shutdown order: rclcpp::shutdown() BEFORE g_node.reset() to prevent
  // shutdown order inversion (node destruction while ROS2 context is active)
  rclcpp::shutdown();
  // Abort any in-progress shutdown polling loops before destroying the node (task 1.4)
  if (g_node) {
    g_node->request_shutdown_abort();
  }
  g_node.reset();

  return 0;
}
