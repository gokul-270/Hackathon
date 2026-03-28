// Copyright 2025 Pragati Robotics
// ODrive CANSimple ROS2 Service Node
//
// Vehicle drive wheels control for ODrive Pro (firmware v0.6.x)
// Provides position control and status monitoring for drive wheels
//
// Features:
// - Position command topics for each wheel
// - Joint state publishing at 10 Hz
// - Status service for monitoring wheel state
// - Thread-safe CAN communication with mutex-protected state
//
// ODrive Pro CANSimple Protocol Notes:
// - Heartbeat messages: Sent automatically at 10 Hz (every 100ms)
// - Encoder feedback: Requested via RTR at configurable rate
// - State transitions: Take 200-500ms to complete

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/float64.hpp>
#include <motor_control_msgs/srv/joint_status.hpp>
#include <motor_control_msgs/srv/set_axis_state.hpp>
#include <motor_control_msgs/srv/emergency_stop.hpp>
#include <motor_control_msgs/srv/drive_stop.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>

#include "odrive_control_ros2/odrive_cansimple_protocol.hpp"
#include "odrive_control_ros2/socketcan_interface.hpp"

#include <thread>
#include <mutex>
#include <map>
#include <optional>
#include <queue>
#include <chrono>
#include <cmath>

using namespace std::chrono_literals;

namespace odrive_control_ros2 {

// Motion control state machine
enum class MotionState {
  IDLE,                           // Motors in IDLE, ready for commands
  TRANSITIONING_TO_CLOSED_LOOP,   // Sent CLOSED_LOOP command, waiting for confirmation
  READY_FOR_COMMANDS,             // Motors in CLOSED_LOOP, waiting for new commands (NEW - for smooth continuous motion)
  EXECUTING_MOTION,               // Motor moving to target position
  TRANSITIONING_TO_IDLE,          // Sent IDLE command, waiting for confirmation
  ERROR_STATE                     // Error detected, motors in safe state
};

// Per-ODrive state tracking
struct ODriveState {
  // Identity
  uint8_t node_id;
  std::string joint_name;
  int32_t joint_id;

  // Configuration
  double direction;             // -1.0 or 1.0
  double transmission_factor;   // joint units → motor turns
  double position_tolerance;    // in joint units

  // Runtime state
  odrive_cansimple::Heartbeat last_heartbeat;
  odrive_cansimple::EncoderEstimates last_encoder;
  odrive_cansimple::ErrorStatus last_error;

  std::chrono::steady_clock::time_point last_heartbeat_time;
  std::chrono::steady_clock::time_point last_encoder_time;

  bool heartbeat_received = false;
  bool encoder_received = false;
  bool heartbeat_stale = false;  // Set true when heartbeat timeout detected, cleared on recovery

  // Motion control state
  MotionState motion_state = MotionState::IDLE;
  std::optional<double> target_position = std::nullopt;  // Target position in joint units (meters). nullopt = no target set.
  double start_position = 0.0;   // Position when motion started (for logging)
  std::chrono::steady_clock::time_point motion_start_time;
  std::chrono::milliseconds motion_timeout{0};
  bool motion_started = false;   // True when traj_done goes to 0 (motion actually started)

  // Per-motor rate limiter (independent of other motors)
  std::chrono::steady_clock::time_point last_command_time;  // Timestamp of last position command for this motor

  // Stall detection (position-based)
  double last_stall_check_position = 0.0;  // Position at last stall check
  std::chrono::steady_clock::time_point last_stall_check_time;  // Time of last stall check

  // Helper: Convert joint units → ODrive turns
  // Formula: turns = meters / (meters_per_turn)
  // Example: 0.5m / 0.1092 m/turn = 4.58 turns
  double joint_to_turns(double joint_value) const {
    return (joint_value / transmission_factor) * direction;
  }

  // Helper: Convert ODrive turns → joint units
  // Formula: meters = turns × (meters_per_turn)
  // Example: 4.58 turns × 0.1092 m/turn = 0.5m
  double turns_to_joint(double turns) const {
    return (turns * transmission_factor) / direction;
  }
};

class ODriveServiceNode : public rclcpp::Node {
public:
  ODriveServiceNode() : Node("odrive_service_node") {
    // Declare parameters
    this->declare_parameter<std::string>("interface_name", "can0");
    this->declare_parameter<std::vector<std::string>>("joint_names", std::vector<std::string>{});
    this->declare_parameter<std::vector<int64_t>>("node_ids", std::vector<int64_t>{});
    this->declare_parameter<std::vector<double>>("directions", std::vector<double>{});
    this->declare_parameter<std::vector<double>>("transmission_factors", std::vector<double>{});
    this->declare_parameter<std::vector<double>>("position_tolerance", std::vector<double>{});
    this->declare_parameter<double>("joint_states_rate", 10.0);
    this->declare_parameter<double>("encoder_request_rate", 10.0);
    this->declare_parameter<std::string>("completion_detection_mode", "auto");  // "auto", "traj_done", or "position"
    this->declare_parameter<double>("expected_velocity", 0.2);  // Expected velocity for timeout calculation (m/s)
    this->declare_parameter<double>("timeout_safety_margin", 5.0);  // Extra time added to timeout (seconds)
    this->declare_parameter<bool>("incremental_position", true);  // true = relative positioning, false = absolute positioning
    this->declare_parameter<double>("idle_timeout", 8.0);  // Time to wait before transitioning to IDLE (seconds)
                                                             // 8s keeps motors warm between pick cycles (arm ~3-5s per pick)
    this->declare_parameter<double>("min_command_interval", 0.05);  // Minimum time between position commands (seconds) - configurable for testing
    this->declare_parameter<bool>("enable_trajectory_updates", true);  // Allow updating trajectory during motion (smooth continuous motion)
    this->declare_parameter<std::string>("sync_mode", "aggregation");  // "aggregation" or "combined_topic"
    this->declare_parameter<double>("aggregation_window_ms", 5.0);  // Max wait for all motor callbacks (ms)

    // Load parameters
    interface_name_ = this->get_parameter("interface_name").as_string();
    auto joint_names = this->get_parameter("joint_names").as_string_array();
    auto node_ids = this->get_parameter("node_ids").as_integer_array();
    auto directions = this->get_parameter("directions").as_double_array();
    auto transmission_factors = this->get_parameter("transmission_factors").as_double_array();
    auto position_tolerances = this->get_parameter("position_tolerance").as_double_array();
    completion_mode_ = this->get_parameter("completion_detection_mode").as_string();
    expected_velocity_ = this->get_parameter("expected_velocity").as_double();
    timeout_safety_margin_ = this->get_parameter("timeout_safety_margin").as_double();
    incremental_position_ = this->get_parameter("incremental_position").as_bool();
    idle_timeout_seconds_ = this->get_parameter("idle_timeout").as_double();
    min_command_interval_seconds_ = this->get_parameter("min_command_interval").as_double();
    enable_trajectory_updates_ = this->get_parameter("enable_trajectory_updates").as_bool();
    sync_mode_ = this->get_parameter("sync_mode").as_string();
    aggregation_window_ms_ = this->get_parameter("aggregation_window_ms").as_double();

    // Validate parameter arrays
    if (joint_names.empty()) {
      RCLCPP_ERROR(this->get_logger(), "CONFIGURATION ERROR: No joints configured!");
      RCLCPP_ERROR(this->get_logger(), "Check that parameters are loaded from the correct namespace.");
      RCLCPP_ERROR(this->get_logger(), "Expected namespace: '%s/ros__parameters'", this->get_name());
      RCLCPP_ERROR(this->get_logger(), "Config file should have: '%s:' as the top-level key", this->get_name());
      throw std::runtime_error("Empty joint configuration - parameters not loaded");
    }

    if (joint_names.size() != node_ids.size() ||
        joint_names.size() != directions.size() ||
        joint_names.size() != transmission_factors.size() ||
        joint_names.size() != position_tolerances.size()) {
      RCLCPP_ERROR(this->get_logger(), "Parameter array size mismatch!");
      RCLCPP_ERROR(this->get_logger(), "  joint_names: %zu", joint_names.size());
      RCLCPP_ERROR(this->get_logger(), "  node_ids: %zu", node_ids.size());
      RCLCPP_ERROR(this->get_logger(), "  directions: %zu", directions.size());
      RCLCPP_ERROR(this->get_logger(), "  transmission_factors: %zu", transmission_factors.size());
      RCLCPP_ERROR(this->get_logger(), "  position_tolerance: %zu", position_tolerances.size());
      throw std::runtime_error("Invalid configuration");
    }

    RCLCPP_INFO(this->get_logger(), "Loaded configuration for %zu joint(s)", joint_names.size());
    RCLCPP_INFO(this->get_logger(), "Completion detection mode: %s", completion_mode_.c_str());
    RCLCPP_INFO(this->get_logger(), "Expected velocity: %.2f m/s, Timeout safety margin: %.1f s",
                expected_velocity_, timeout_safety_margin_);
    RCLCPP_INFO(this->get_logger(), "Position mode: %s", incremental_position_ ? "INCREMENTAL" : "ABSOLUTE");
    RCLCPP_INFO(this->get_logger(), "[CONFIG] idle_timeout=%.1f s, min_cmd_interval=%.3f s, traj_updates=%s",
                idle_timeout_seconds_, min_command_interval_seconds_,
                enable_trajectory_updates_ ? "ENABLED" : "DISABLED");
    RCLCPP_INFO(this->get_logger(), "[CONFIG] sync_mode=%s, aggregation_window=%.1f ms",
                sync_mode_.c_str(), aggregation_window_ms_);

    // Initialize ODrive states
    for (size_t i = 0; i < joint_names.size(); ++i) {
      ODriveState state;
      state.node_id = static_cast<uint8_t>(node_ids[i]);
      state.joint_name = joint_names[i];

      // For vehicle wheels, use sequential joint_id (0, 1, 2)
      state.joint_id = static_cast<int32_t>(i);

      state.direction = directions[i];
      state.transmission_factor = transmission_factors[i];
      state.position_tolerance = position_tolerances[i];

      odrive_states_[state.node_id] = state;
      joint_name_to_node_id_[state.joint_name] = state.node_id;
      joint_id_to_node_id_[state.joint_id] = state.node_id;

      RCLCPP_INFO(this->get_logger(), "Configured %s (node_id=%d, joint_id=%d)",
                  state.joint_name.c_str(), state.node_id, state.joint_id);
    }

    // Initialize SocketCAN
    can_interface_ = std::make_shared<odrive_cansimple::SocketCANInterface>();
    std::vector<uint8_t> node_id_list;
    for (const auto& pair : odrive_states_) {
      node_id_list.push_back(pair.first);
    }

    if (!can_interface_->initialize(interface_name_, node_id_list)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to initialize CAN interface: %s", interface_name_.c_str());
      throw std::runtime_error("CAN initialization failed");
    }

    RCLCPP_INFO(this->get_logger(), "CAN interface %s initialized with RX filtering", interface_name_.c_str());

    // Create ROS2 services
    status_service_ = this->create_service<motor_control_msgs::srv::JointStatus>(
      "/joint_status",
      std::bind(&ODriveServiceNode::handle_joint_status, this, std::placeholders::_1, std::placeholders::_2));

    set_axis_state_service_ = this->create_service<motor_control_msgs::srv::SetAxisState>(
      "/set_axis_state",
      std::bind(&ODriveServiceNode::handle_set_axis_state, this, std::placeholders::_1, std::placeholders::_2));

    emergency_stop_service_ = this->create_service<motor_control_msgs::srv::EmergencyStop>(
      "/emergency_stop",
      std::bind(&ODriveServiceNode::handle_emergency_stop, this, std::placeholders::_1, std::placeholders::_2));

    RCLCPP_INFO(this->get_logger(), "Emergency stop service initialized");

    // Drive stop service (for joystick control - stops motors when joystick released)
    drive_stop_service_ = this->create_service<motor_control_msgs::srv::DriveStop>(
      "/drive_stop",
      std::bind(&ODriveServiceNode::handle_drive_stop, this, std::placeholders::_1, std::placeholders::_2));

    RCLCPP_INFO(this->get_logger(), "Drive stop service initialized");

    // Create joint_states publisher
    joint_states_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);

    // Create diagnostics publisher for CAN write failure reporting
    diagnostics_pub_ = this->create_publisher<diagnostic_msgs::msg::DiagnosticArray>("/diagnostics", 10);

    double js_rate = this->get_parameter("joint_states_rate").as_double();
    auto js_period = std::chrono::duration<double>(1.0 / js_rate);
    joint_states_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::milliseconds>(js_period),
      std::bind(&ODriveServiceNode::publish_joint_states, this));

    // Create position command subscribers
    for (const auto& pair : odrive_states_) {
      const auto& state = pair.second;
      std::string topic = "/" + state.joint_name + "_position_controller/command";

      auto callback = [this, node_id = state.node_id](const std_msgs::msg::Float64::SharedPtr msg) {
        this->handle_position_command(node_id, msg->data);
      };

      position_command_subs_[state.node_id] = this->create_subscription<std_msgs::msg::Float64>(
        topic, 10, callback);

      RCLCPP_INFO(this->get_logger(), "Subscribed to %s", topic.c_str());
    }

    // Start CAN RX thread
    rx_thread_running_ = true;
    rx_thread_ = std::thread(&ODriveServiceNode::can_rx_thread, this);

    // Start encoder request timer (RTR)
    double enc_rate = this->get_parameter("encoder_request_rate").as_double();
    auto enc_period = std::chrono::duration<double>(1.0 / enc_rate);
    encoder_request_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::milliseconds>(enc_period),
      std::bind(&ODriveServiceNode::request_encoder_estimates, this));

    // Start state machine update timer (20 Hz for responsive control)
    state_machine_timer_ = this->create_wall_timer(
      50ms,  // 20 Hz
      std::bind(&ODriveServiceNode::update_state_machine, this));

    // Start heartbeat timeout detection timer (1 Hz)
    heartbeat_timeout_timer_ = this->create_wall_timer(
      1000ms,
      std::bind(&ODriveServiceNode::check_heartbeat_timeouts, this));

    RCLCPP_INFO(this->get_logger(), "ODrive service node started successfully");

    // Initialize all motors to IDLE state
    RCLCPP_INFO(this->get_logger(), "Setting all motors to IDLE state...");
    std::this_thread::sleep_for(500ms);  // Wait for CAN to stabilize
    set_all_motors_to_idle();

    RCLCPP_INFO(this->get_logger(), "NOTE: ODrive control mode (POSITION_CONTROL + TRAP_TRAJ) should be configured via USB and saved to ODrive NVM");
  }

  ~ODriveServiceNode() {
    RCLCPP_INFO(this->get_logger(), "Shutting down - setting all motors to IDLE state...");

    // Stop state machine timer
    if (state_machine_timer_) {
      state_machine_timer_->cancel();
    }

    // Set all motors to IDLE before shutdown
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::IDLE);
    }

    // Wait for motors to reach IDLE (max 2 seconds)
    auto shutdown_start = std::chrono::steady_clock::now();
    bool all_idle = false;
    while (!all_idle && std::chrono::steady_clock::now() - shutdown_start < std::chrono::seconds(2)) {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));

      std::lock_guard<std::mutex> lock(state_mutex_);
      all_idle = true;
      for (const auto& pair : odrive_states_) {
        if (pair.second.heartbeat_received) {
          if (pair.second.last_heartbeat.axis_state != odrive_cansimple::AXIS_STATE::IDLE) {
            all_idle = false;
            break;
          }
        }
      }
    }

    if (all_idle) {
      RCLCPP_INFO(this->get_logger(), "All motors safely in IDLE state");
    } else {
      RCLCPP_WARN(this->get_logger(), "Timeout waiting for motors to reach IDLE - shutting down anyway");
    }

    // Stop CAN RX thread
    rx_thread_running_ = false;
    if (rx_thread_.joinable()) {
      rx_thread_.join();
    }

    can_interface_->close();
    RCLCPP_INFO(this->get_logger(), "Shutdown complete");
  }

private:
  // CAN RX thread
  // ODrive Pro sends heartbeats automatically at 10 Hz (every 100ms)
  void can_rx_thread() {
    while (rx_thread_running_ && rclcpp::ok()) {
      uint16_t arb_id;
      std::vector<uint8_t> data;

      if (can_interface_->receive_frame(arb_id, data, 100)) {
        uint8_t node_id = odrive_cansimple::extract_node_id(arb_id);
        uint8_t cmd_id = odrive_cansimple::extract_cmd_id(arb_id);

        std::lock_guard<std::mutex> lock(state_mutex_);

        auto it = odrive_states_.find(node_id);
        if (it == odrive_states_.end()) {
          continue;  // Unknown node_id (shouldn't happen with filtering)
        }

        auto& state = it->second;

        // Decode based on cmd_id
        switch (cmd_id) {
          case odrive_cansimple::CMD::HEARTBEAT:
            if (data.size() >= 7) {
              state.last_heartbeat = odrive_cansimple::Heartbeat::decode(data.data());
              state.last_heartbeat_time = std::chrono::steady_clock::now();
              state.heartbeat_received = true;

              // Clear stale flag on heartbeat arrival (recovery path)
              if (state.heartbeat_stale) {
                RCLCPP_WARN(this->get_logger(),
                            "[HEARTBEAT] Motor %s (node_id=%u) heartbeat received "
                            "— clearing stale flag (CAN RX recovery)",
                            state.joint_name.c_str(), state.node_id);
                state.heartbeat_stale = false;
              }
            }
            break;

          case odrive_cansimple::CMD::GET_ERROR:
            if (data.size() >= 8) {
              state.last_error = odrive_cansimple::ErrorStatus::decode(data.data());
            }
            break;

          case odrive_cansimple::CMD::GET_ENCODER_ESTIMATES:
            if (data.size() >= 8) {
              state.last_encoder = odrive_cansimple::EncoderEstimates::decode(data.data());
              state.last_encoder_time = std::chrono::steady_clock::now();
              if (!state.encoder_received) {
                RCLCPP_INFO(this->get_logger(),
                            "[MOTOR_INIT] %s (node_id=%u): first encoder pos=%.4f m (%.4f turns)",
                            state.joint_name.c_str(), state.node_id,
                            state.turns_to_joint(state.last_encoder.pos_estimate),
                            state.last_encoder.pos_estimate);
              }
              state.encoder_received = true;
            }
            break;

          default:
            break;
        }
      }
    }
  }

  // Helper: Handle CAN send_frame() failure — log, set FAULT, publish diagnostic
  void handle_send_failure(uint8_t node_id, const std::string& command_type) {
    // Find motor name for logging
    std::string joint_name = "unknown";
    auto it = odrive_states_.find(node_id);
    if (it != odrive_states_.end()) {
      joint_name = it->second.joint_name;
      it->second.motion_state = MotionState::ERROR_STATE;
    }

    // Structured JSON error log
    RCLCPP_ERROR(this->get_logger(),
                 "{\"event\":\"can_send_failure\",\"component\":\"odrive_service_node\","
                 "\"node_id\":%d,\"joint_name\":\"%s\",\"command\":\"%s\"}",
                 node_id, joint_name.c_str(), command_type.c_str());

    // Publish diagnostic
    diagnostic_msgs::msg::DiagnosticArray diag_array;
    diag_array.header.stamp = this->now();

    diagnostic_msgs::msg::DiagnosticStatus status;
    status.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
    status.name = "odrive_motor_" + std::to_string(node_id);
    status.message = "CAN send_frame failed for " + command_type;
    status.hardware_id = "odrive_node_" + std::to_string(node_id);

    diagnostic_msgs::msg::KeyValue kv_cmd;
    kv_cmd.key = "command";
    kv_cmd.value = command_type;
    status.values.push_back(kv_cmd);

    diagnostic_msgs::msg::KeyValue kv_joint;
    kv_joint.key = "joint_name";
    kv_joint.value = joint_name;
    status.values.push_back(kv_joint);

    diag_array.status.push_back(status);
    diagnostics_pub_->publish(diag_array);
  }

  // Request encoder estimates via RTR
  void request_encoder_estimates() {
    std::lock_guard<std::mutex> lock(state_mutex_);
    for (const auto& pair : odrive_states_) {
      uint8_t node_id = pair.first;
      uint16_t arb_id = odrive_cansimple::make_arbitration_id(node_id, odrive_cansimple::CMD::GET_ENCODER_ESTIMATES);
      if (!can_interface_->send_frame(arb_id, {}, true)) {  // RTR
        handle_send_failure(node_id, "GET_ENCODER_ESTIMATES");
      }
    }
  }

  // Publish joint_states
  void publish_joint_states() {
    std::lock_guard<std::mutex> lock(state_mutex_);

    sensor_msgs::msg::JointState msg;
    msg.header.stamp = this->now();

    for (const auto& pair : odrive_states_) {
      const auto& state = pair.second;

      msg.name.push_back(state.joint_name);

      if (state.encoder_received) {
        msg.position.push_back(state.turns_to_joint(state.last_encoder.pos_estimate));
        msg.velocity.push_back(state.turns_to_joint(state.last_encoder.vel_estimate));
      } else {
        msg.position.push_back(0.0);
        msg.velocity.push_back(0.0);
      }

      msg.effort.push_back(0.0);  // Not available
    }

    joint_states_pub_->publish(msg);

    // Throttled log: every ~2 seconds (publish rate × 20 counts)
    ++joint_states_log_counter_;
    if (joint_states_log_counter_ >= 20) {
      joint_states_log_counter_ = 0;
      std::string summary;
      for (size_t i = 0; i < msg.name.size(); ++i) {
        if (i > 0) summary += ", ";
        char buf[64];
        snprintf(buf, sizeof(buf), "%s=%.4fm", msg.name[i].c_str(),
                 i < msg.position.size() ? msg.position[i] : 0.0);
        summary += buf;
      }
      RCLCPP_INFO(this->get_logger(),
                  "[JOINT_STATES] Published to %s: [%s]",
                  joint_states_pub_->get_topic_name(), summary.c_str());
    }
  }

  // Internal: Start motion (assumes lock is already held)
  void start_motion_internal(uint8_t node_id, double target_position) {
    auto it = odrive_states_.find(node_id);
    if (it == odrive_states_.end()) {
      RCLCPP_WARN(this->get_logger(), "Unknown node_id %d in start_motion_internal", node_id);
      return;
    }

    // Get current position
    double current_position = it->second.turns_to_joint(it->second.last_encoder.pos_estimate);

    // Start new motion
    RCLCPP_INFO(this->get_logger(), "[MOTION] %s: %.4f m → %.4f m (delta=%.4f m)",
                it->second.joint_name.c_str(), current_position, target_position,
                target_position - current_position);

    // Store target position and start position
    it->second.target_position = target_position;
    it->second.start_position = current_position;
    it->second.motion_start_time = std::chrono::steady_clock::now();
    it->second.motion_started = false;  // Reset flag - will set to true when traj_done goes to 0

    // Calculate timeout based on distance and configured velocity
    double distance = std::abs(target_position - current_position);
    double timeout_seconds = std::max(5.0, distance / expected_velocity_ + timeout_safety_margin_);
    it->second.motion_timeout = std::chrono::milliseconds(static_cast<int>(timeout_seconds * 1000));

    RCLCPP_DEBUG(this->get_logger(), "[MOTION] %s: dist=%.4f m, timeout=%.1f s",
                 it->second.joint_name.c_str(), distance, timeout_seconds);

    // Check if already in CLOSED_LOOP (READY_FOR_COMMANDS state)
    if (global_motion_state_ == MotionState::READY_FOR_COMMANDS) {
      // Already in CLOSED_LOOP — batch-send position commands to ALL motors simultaneously
      // to eliminate ROS2 callback scheduling jitter (~1-10ms) as a source of desync.
      RCLCPP_INFO(this->get_logger(),
                  "[SYNC] Motors already in CLOSED_LOOP — batching position commands for all motors");
      global_motion_state_ = MotionState::EXECUTING_MOTION;
      motion_in_progress_ = true;

      int sent_count = 0;
      for (auto& pair : odrive_states_) {
        auto& state = pair.second;
        if (state.target_position.has_value()) {
          double pos_turns = state.joint_to_turns(state.target_position.value());
          uint16_t arb = odrive_cansimple::make_arbitration_id(pair.first, odrive_cansimple::CMD::SET_INPUT_POS);
          auto frame = odrive_cansimple::encode_set_input_pos(pos_turns, 0.0f, 0.0f);
          if (!can_interface_->send_frame(arb, frame)) {
            handle_send_failure(pair.first, "SET_INPUT_POS");
          }
          RCLCPP_INFO(this->get_logger(),
                      "[SYNC] CAN SET_INPUT_POS → node_id=%d (%s): %.4f m (%.4f turns)",
                      pair.first, state.joint_name.c_str(),
                      state.target_position.value(), pos_turns);
          ++sent_count;
        }
      }
      RCLCPP_INFO(this->get_logger(),
                  "[SYNC] Batched %d/%zu position frames (CLOSED_LOOP path)", sent_count,
                  odrive_states_.size());
      return;
    }

    // Fire-and-forget path (motors were IDLE):
    // 1. Send CLOSED_LOOP to ALL motors so they all start re-arming simultaneously.
    // 2. Send SET_INPUT_POS to ALL motors with their already-stored targets so that
    //    each ODrive executes its command as soon as it individually reaches CLOSED_LOOP.
    //    This eliminates the original single-motor dispatch bug (Issue 1) — all three
    //    wheels start from the same CLOSED_LOOP moment instead of whichever callback
    //    fires first getting an exclusive head start.
    motion_in_progress_ = true;
    global_motion_state_ = MotionState::EXECUTING_MOTION;

    // Step 1 — CLOSED_LOOP to all motors (synchronized arm)
    RCLCPP_INFO(this->get_logger(),
                "[SYNC] Sending CLOSED_LOOP to all %zu motors simultaneously", odrive_states_.size());
    set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::CLOSED_LOOP_CONTROL);

    // Step 2 — SET_INPUT_POS to all motors that have a target (batched CAN burst)
    int sent_count = 0;
    for (auto& pair : odrive_states_) {
      auto& state = pair.second;
      if (state.target_position.has_value()) {
        double pos_turns = state.joint_to_turns(state.target_position.value());
        uint16_t arb = odrive_cansimple::make_arbitration_id(pair.first, odrive_cansimple::CMD::SET_INPUT_POS);
        auto frame = odrive_cansimple::encode_set_input_pos(pos_turns, 0.0f, 0.0f);
        if (!can_interface_->send_frame(arb, frame)) {
          handle_send_failure(pair.first, "SET_INPUT_POS");
        }
        RCLCPP_INFO(this->get_logger(),
                    "[SYNC] CAN SET_INPUT_POS → node_id=%d (%s): %.4f m (%.4f turns)",
                    pair.first, state.joint_name.c_str(),
                    state.target_position.value(), pos_turns);
        ++sent_count;
      }
    }
    RCLCPP_INFO(this->get_logger(),
                "[SYNC] Batched %d/%zu position frames (fire-and-forget path)", sent_count,
                odrive_states_.size());
  }

  // Dispatch all buffered targets in pending_targets_ as a single tight CAN burst.
  // Called either when all motors arrive within the aggregation window, or when the
  // window timer fires (partial arrival). Assumes state_mutex_ is already held.
  void dispatch_pending_batch() {
    if (pending_targets_.empty()) {
      RCLCPP_WARN(this->get_logger(), "[SYNC] dispatch_pending_batch called with empty buffer — ignoring");
      return;
    }

    RCLCPP_INFO(this->get_logger(),
                "[SYNC] dispatch_pending_batch: dispatching %zu motor target(s)", pending_targets_.size());

    // Ensure targets are stored in odrive_states_ (they were written there when buffered,
    // but do it again defensively to cover any edge cases).
    for (const auto& kv : pending_targets_) {
      auto it = odrive_states_.find(kv.first);
      if (it != odrive_states_.end()) {
        it->second.target_position = kv.second;
        it->second.start_position = it->second.turns_to_joint(it->second.last_encoder.pos_estimate);
        it->second.motion_start_time = std::chrono::steady_clock::now();
        it->second.motion_started = false;

        double distance = std::abs(kv.second - it->second.start_position);
        double timeout_s = std::max(5.0, distance / expected_velocity_ + timeout_safety_margin_);
        it->second.motion_timeout = std::chrono::milliseconds(static_cast<int>(timeout_s * 1000));

        RCLCPP_INFO(this->get_logger(),
                    "[SYNC] %s: %.4f m → %.4f m (delta=%.4f m)",
                    it->second.joint_name.c_str(),
                    it->second.start_position, kv.second,
                    kv.second - it->second.start_position);
      }
    }

    pending_targets_.clear();

    if (global_motion_state_ == MotionState::READY_FOR_COMMANDS) {
      // Motors already in CLOSED_LOOP — send position commands immediately.
      global_motion_state_ = MotionState::EXECUTING_MOTION;
      motion_in_progress_ = true;

      int sent_count = 0;
      for (auto& pair : odrive_states_) {
        auto& state = pair.second;
        if (state.target_position.has_value()) {
          double pos_turns = state.joint_to_turns(state.target_position.value());
          uint16_t arb = odrive_cansimple::make_arbitration_id(pair.first, odrive_cansimple::CMD::SET_INPUT_POS);
          auto frame = odrive_cansimple::encode_set_input_pos(pos_turns, 0.0f, 0.0f);
          if (!can_interface_->send_frame(arb, frame)) {
            handle_send_failure(pair.first, "SET_INPUT_POS");
          }
          RCLCPP_INFO(this->get_logger(),
                      "[SYNC] CAN SET_INPUT_POS → node_id=%d (%s): %.4f m (%.4f turns)",
                      pair.first, state.joint_name.c_str(),
                      state.target_position.value(), pos_turns);
          ++sent_count;
        }
      }
      RCLCPP_INFO(this->get_logger(),
                  "[SYNC] Batched %d/%zu position frames (READY_FOR_COMMANDS path)",
                  sent_count, odrive_states_.size());

    } else {
      // Motors are IDLE (or transitioning) — send CLOSED_LOOP to all motors simultaneously,
      // then send SET_INPUT_POS to all motors immediately so that each ODrive executes its
      // command as soon as it individually confirms CLOSED_LOOP.
      // The TRANSITIONING_TO_CLOSED_LOOP handler in the state machine also re-sends positions
      // once all motors confirm, providing a safety net for any frames lost in transition.
      motion_in_progress_ = true;
      global_motion_state_ = MotionState::EXECUTING_MOTION;

      RCLCPP_INFO(this->get_logger(),
                  "[SYNC] Sending CLOSED_LOOP to all %zu motors simultaneously", odrive_states_.size());
      set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::CLOSED_LOOP_CONTROL);

      int sent_count = 0;
      for (auto& pair : odrive_states_) {
        auto& state = pair.second;
        if (state.target_position.has_value()) {
          double pos_turns = state.joint_to_turns(state.target_position.value());
          uint16_t arb = odrive_cansimple::make_arbitration_id(pair.first, odrive_cansimple::CMD::SET_INPUT_POS);
          auto frame = odrive_cansimple::encode_set_input_pos(pos_turns, 0.0f, 0.0f);
          if (!can_interface_->send_frame(arb, frame)) {
            handle_send_failure(pair.first, "SET_INPUT_POS");
          }
          RCLCPP_INFO(this->get_logger(),
                      "[SYNC] CAN SET_INPUT_POS → node_id=%d (%s): %.4f m (%.4f turns)",
                      pair.first, state.joint_name.c_str(),
                      state.target_position.value(), pos_turns);
          ++sent_count;
        }
      }
      RCLCPP_INFO(this->get_logger(),
                  "[SYNC] Batched %d/%zu position frames (IDLE path — pre-arming CAN burst)",
                  sent_count, odrive_states_.size());
    }
  }

  // Handle position commands - Queue commands if motion in progress
  void handle_position_command(uint8_t node_id, double joint_position_command, bool is_queued_absolute = false) {
    std::lock_guard<std::mutex> lock(state_mutex_);

    // Block commands during emergency stop
    if (emergency_stop_active_) {
      RCLCPP_ERROR(this->get_logger(),
                   "Command rejected - emergency stop active. Call /resume_from_emergency service to resume.");
      return;
    }

    // Block commands during drive stop
    if (drive_stop_active_) {
      RCLCPP_ERROR(this->get_logger(),
                   "Command rejected - drive stop active. Call /drive_stop with activate=false to resume.");
      return;
    }

    auto it = odrive_states_.find(node_id);
    if (it == odrive_states_.end()) {
      RCLCPP_WARN(this->get_logger(), "Unknown node_id %d in position command", node_id);
      return;
    }

    // Guard: if encoder not yet received, we have no valid position — skip command
    if (!it->second.encoder_received) {
      RCLCPP_WARN(this->get_logger(),
                  "Command for %s dropped — encoder not yet received (position unknown)",
                  it->second.joint_name.c_str());
      return;
    }

    // Get current position
    double current_position = it->second.turns_to_joint(it->second.last_encoder.pos_estimate);

    // Calculate target position based on mode
    double target_position;
    if (is_queued_absolute) {
      // QUEUED COMMAND: Already an absolute target position
      target_position = joint_position_command;
      RCLCPP_INFO(this->get_logger(), "Processing QUEUED command for %s: current=%.4f m → target=%.4f m",
                  it->second.joint_name.c_str(), current_position, target_position);
    } else if (incremental_position_) {
      // INCREMENTAL MODE: command is relative to current position
      // If motion in progress, use the target of the last queued command (or current motion target)
      // This allows commands to chain: cmd1=+1, cmd2=+1 → targets: 1, 2 (not both 1)
      double base_position;
      if (motion_in_progress_) {
        // Use the last target in the queue, or current motion target if queue is empty
        if (!command_queue_.empty()) {
          // Get the last queued target for this node_id
          auto& last_cmd = command_queue_.back();
          if (last_cmd.find(node_id) != last_cmd.end()) {
            base_position = last_cmd[node_id];
          } else {
            // If target_position has no value, motor has never been commanded — use live encoder
            base_position = it->second.target_position.has_value()
                ? it->second.target_position.value()
                : current_position;
          }
        } else {
          // If target_position has no value, motor has never been commanded — use live encoder
          base_position = it->second.target_position.has_value()
              ? it->second.target_position.value()
              : current_position;
        }
        target_position = base_position + joint_position_command;
        RCLCPP_INFO(this->get_logger(), "Received INCREMENTAL command for %s: base=%.4f m + delta=%.4f m → target=%.4f m (queued)",
                    it->second.joint_name.c_str(), base_position, joint_position_command, target_position);
      } else {
        // No motion in progress, use current encoder position
        base_position = current_position;
        target_position = base_position + joint_position_command;
        RCLCPP_INFO(this->get_logger(), "Received INCREMENTAL command for %s: current=%.4f m + delta=%.4f m → target=%.4f m",
                    it->second.joint_name.c_str(), base_position, joint_position_command, target_position);
      }
    } else {
      // ABSOLUTE MODE: command is absolute position
      target_position = joint_position_command;
      RCLCPP_INFO(this->get_logger(), "Received ABSOLUTE command for %s: %.4f m [topic: /%s_position_controller/command]",
                  it->second.joint_name.c_str(), target_position, it->second.joint_name.c_str());
    }

    // Check if motion is already in progress (only queue new commands, not already-queued ones)
    if (motion_in_progress_ && !is_queued_absolute) {
      // SMOOTH MOTION: Update trajectory instead of queuing (if enabled)
      if (enable_trajectory_updates_) {
        // Check command rate limiting — per-motor, so other wheels are never blocked
        auto now = std::chrono::steady_clock::now();
        auto time_since_last_cmd = std::chrono::duration<double>(now - it->second.last_command_time).count();

        if (time_since_last_cmd < min_command_interval_seconds_) {
          // Drop command - too fast (using latest command strategy)
          RCLCPP_DEBUG(this->get_logger(),
                      "Command dropped - too fast (%.3f s < %.3f s min interval) for %s",
                      time_since_last_cmd, min_command_interval_seconds_,
                      it->second.joint_name.c_str());
          return;
        }

        // Update target position (don't queue)
        it->second.target_position = target_position;

        // RESET MOTION TIMEOUT - keeps continuous motion alive while commands arriving
        // Recalculate timeout based on new target distance
        double new_distance = std::abs(target_position - current_position);
        double new_timeout_seconds = std::max(5.0, new_distance / expected_velocity_ + timeout_safety_margin_);
        it->second.motion_timeout = std::chrono::milliseconds(static_cast<int>(new_timeout_seconds * 1000));
        it->second.motion_start_time = now;  // Reset start time
        it->second.motion_started = false;  // Reset traj_done tracking

        // Send position command immediately - ODrive blends trajectories automatically
        double position_turns = it->second.joint_to_turns(target_position);
        uint16_t arb_id = odrive_cansimple::make_arbitration_id(node_id, odrive_cansimple::CMD::SET_INPUT_POS);
        auto data = odrive_cansimple::encode_set_input_pos(position_turns, 0.0f, 0.0f);
        if (!can_interface_->send_frame(arb_id, data)) {
          handle_send_failure(node_id, "SET_INPUT_POS");
        }

        it->second.last_command_time = now;  // Per-motor — does not affect other wheels

        RCLCPP_DEBUG(this->get_logger(),
                    "🎯 Trajectory UPDATED for %s: new target=%.4f m (%.3f turns), timeout reset to %.1f s",
                    it->second.joint_name.c_str(), target_position, position_turns, new_timeout_seconds);
        return;
      } else {
        // Legacy queuing mode (if trajectory updates disabled for testing).
        // Issue 4 fix: snapshot ALL motors' current targets (not just the one
        // whose callback fired), so the queue entry is a complete 3-motor command.
        // When drained, start_motion_internal is called for every motor in the
        // snapshot, and the batched CAN burst in start_motion_internal sends all
        // 3 SET_INPUT_POS frames together.
        std::map<uint8_t, double> queued_command;
        for (const auto& motor_pair : odrive_states_) {
          uint8_t mid = motor_pair.first;
          if (mid == node_id) {
            // Use the freshly computed target for the motor that triggered this callback
            queued_command[mid] = target_position;
          } else if (motor_pair.second.target_position.has_value()) {
            // Carry forward current target for the other motors (continuity)
            queued_command[mid] = motor_pair.second.target_position.value();
          }
          // Motors with no target yet are omitted — they will be skipped in drain loop
        }
        command_queue_.push(queued_command);

        RCLCPP_INFO(this->get_logger(),
                    "[QUEUE] Queued command for %s (target=%.4f m) with %zu motor(s) in snapshot (queue size: %zu)",
                    it->second.joint_name.c_str(), target_position,
                    queued_command.size(), command_queue_.size());
        return;
      }
    }

    // Start motion: aggregation mode buffers targets and batches them;
    // pass-through mode calls start_motion_internal immediately (legacy).
    if (sync_mode_ == "aggregation") {
      // Buffer this motor's target. Store it in odrive_states_ as well so
      // start_motion_internal's batch loop can see it immediately if called
      // via dispatch_pending_batch.
      it->second.target_position = target_position;
      pending_targets_[node_id] = target_position;

      RCLCPP_INFO(this->get_logger(),
                  "[SYNC] Aggregation: buffered target for %s (%.4f m) — %zu/%zu motors pending",
                  it->second.joint_name.c_str(), target_position,
                  pending_targets_.size(), odrive_states_.size());

      // If all motors have a pending target, dispatch immediately (no need to wait for timer).
      if (pending_targets_.size() == odrive_states_.size()) {
        RCLCPP_INFO(this->get_logger(),
                    "[SYNC] All %zu motors buffered — dispatching immediately", odrive_states_.size());
        if (pending_dispatch_timer_) {
          pending_dispatch_timer_->cancel();
          pending_dispatch_timer_.reset();
        }
        dispatch_pending_batch();
        return;
      }

      // Start the aggregation window timer if not already running.
      if (!pending_dispatch_timer_) {
        auto window_ms = std::chrono::milliseconds(static_cast<int>(aggregation_window_ms_));
        pending_dispatch_timer_ = this->create_wall_timer(
          window_ms,
          [this]() {
            std::lock_guard<std::mutex> timer_lock(state_mutex_);
            RCLCPP_WARN(this->get_logger(),
                        "[SYNC] Aggregation window expired — dispatching %zu/%zu motors (partial arrival)",
                        pending_targets_.size(), odrive_states_.size());
            pending_dispatch_timer_->cancel();
            pending_dispatch_timer_.reset();
            dispatch_pending_batch();
          });
        RCLCPP_DEBUG(this->get_logger(),
                     "[SYNC] Aggregation window started (%.1f ms)", aggregation_window_ms_);
      }
    } else {
      // Pass-through: call start_motion_internal immediately (original behaviour).
      start_motion_internal(node_id, target_position);
    }
  }

  // Helper: Set axis state for all motors
  void set_all_motors_axis_state(uint32_t axis_state) {
    for (const auto& pair : odrive_states_) {
      uint8_t node_id = pair.first;
      uint16_t arb_id = odrive_cansimple::make_arbitration_id(node_id, odrive_cansimple::CMD::SET_AXIS_STATE);
      auto data = odrive_cansimple::encode_set_axis_state(axis_state);
      if (!can_interface_->send_frame(arb_id, data)) {
        handle_send_failure(node_id, "SET_AXIS_STATE");
      }
    }
  }

  // Helper: Set all motors to IDLE
  void set_all_motors_to_idle() {
    std::lock_guard<std::mutex> lock(state_mutex_);
    set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::IDLE);
    global_motion_state_ = MotionState::IDLE;
    motion_in_progress_ = false;
    RCLCPP_INFO(this->get_logger(), "All motors set to IDLE");
  }

  // Helper: Clear errors on all motors
  void clear_all_errors() {
    for (const auto& pair : odrive_states_) {
      uint8_t node_id = pair.first;
      uint16_t arb_id = odrive_cansimple::make_arbitration_id(node_id, odrive_cansimple::CMD::CLEAR_ERRORS);
      auto data = odrive_cansimple::encode_clear_errors(0);
      if (!can_interface_->send_frame(arb_id, data)) {
        handle_send_failure(node_id, "CLEAR_ERRORS");
      }
    }
    RCLCPP_INFO(this->get_logger(), "Sent CLEAR_ERRORS to all motors");
  }

  // Helper: Handle motor error with automatic recovery
  void handle_motor_error(uint8_t failed_node_id) {
    // Log error code from the failing motor before we start recovery
    auto it = odrive_states_.find(failed_node_id);
    uint32_t error_code = (it != odrive_states_.end()) ? it->second.last_heartbeat.axis_error : 0xFFFFFFFF;
    RCLCPP_ERROR(this->get_logger(),
                 "[ERROR] Motor node_id=%d error=0x%08X — stopping ALL motors for safe recovery",
                 failed_node_id, error_code);

    // Stop ALL motors immediately (safety first!)
    set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::IDLE);
    global_motion_state_ = MotionState::ERROR_STATE;
    motion_in_progress_ = false;

    // Clear command queue
    while (!command_queue_.empty()) {
      command_queue_.pop();
    }

    // Clear aggregation buffer and cancel pending dispatch timer
    pending_targets_.clear();
    if (pending_dispatch_timer_) {
      pending_dispatch_timer_->cancel();
      pending_dispatch_timer_.reset();
    }

    // Clear errors on the failed motor
    uint16_t arb_id = odrive_cansimple::make_arbitration_id(failed_node_id, odrive_cansimple::CMD::CLEAR_ERRORS);
    auto data = odrive_cansimple::encode_clear_errors(0);
    if (!can_interface_->send_frame(arb_id, data)) {
      handle_send_failure(failed_node_id, "CLEAR_ERRORS");
    }

    RCLCPP_INFO(this->get_logger(), "Sent CLEAR_ERRORS to motor node_id=%d — ERROR_STATE handler will poll for clearance", failed_node_id);
    // NOTE: No sleep here. The ERROR_STATE handler in update_state_machine() polls at 20 Hz
    // until all axis_error fields clear, then transitions to IDLE. Adding a sleep_for() here
    // would block the entire ROS2 timer callback for that duration, freezing heartbeat
    // processing, encoder reads, and all other state machine ticks.
  }

  // Heartbeat timeout constant: 2 seconds (~20 missed heartbeats at 10Hz)
  // Safety constant — not a ROS2 parameter to prevent misconfiguration.
  static constexpr double HEARTBEAT_TIMEOUT_SECONDS = 2.0;

  // Check heartbeat freshness for all motors (called at 1Hz)
  void check_heartbeat_timeouts() {
    std::lock_guard<std::mutex> lock(state_mutex_);
    auto now = std::chrono::steady_clock::now();

    for (auto& pair : odrive_states_) {
      auto& state = pair.second;

      // Skip motors that haven't sent any heartbeat yet (startup guard)
      if (!state.heartbeat_received) {
        continue;
      }

      auto elapsed = std::chrono::duration<double>(now - state.last_heartbeat_time).count();

      if (elapsed > HEARTBEAT_TIMEOUT_SECONDS) {
        // Motor heartbeat is stale
        if (!state.heartbeat_stale) {
          // Transition: healthy → stale (log once)
          state.heartbeat_stale = true;
          RCLCPP_ERROR(this->get_logger(),
                       "[HEARTBEAT] Motor %s (node_id=%u) heartbeat STALE: "
                       "last seen %.1f s ago (timeout=%.1f s)",
                       state.joint_name.c_str(), state.node_id,
                       elapsed, HEARTBEAT_TIMEOUT_SECONDS);
        }
        // If already stale, no additional log (throttled by design)
      } else {
        // Motor heartbeat is fresh
        if (state.heartbeat_stale) {
          // Transition: stale → healthy (recovery)
          auto downtime = elapsed;
          RCLCPP_WARN(this->get_logger(),
                      "[HEARTBEAT] Motor %s (node_id=%u) heartbeat RECOVERED "
                      "(was stale for ~%.1f s, now healthy)",
                      state.joint_name.c_str(), state.node_id, downtime);
          state.heartbeat_stale = false;
        }
      }
    }
  }

  // State machine update (called at 20 Hz)
  void update_state_machine() {
    std::lock_guard<std::mutex> lock(state_mutex_);

    // Check for errors first - ONLY on connected motors (have received heartbeat)
    bool any_errors = false;
    for (const auto& pair : odrive_states_) {
      const auto& state = pair.second;
      // Only check errors on motors that are actually connected
      if (state.heartbeat_received && state.last_heartbeat.axis_error != 0) {
        RCLCPP_ERROR(this->get_logger(), "Motor %s has error: 0x%08X",
                     state.joint_name.c_str(), state.last_heartbeat.axis_error);
        any_errors = true;
      }
    }

    if (any_errors && global_motion_state_ != MotionState::ERROR_STATE) {
      RCLCPP_ERROR(this->get_logger(), "Errors detected - transitioning to ERROR_STATE");
      global_motion_state_ = MotionState::ERROR_STATE;
      set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::IDLE);
      clear_all_errors();
      motion_in_progress_ = false;

      // Clear command queue on error
      while (!command_queue_.empty()) {
        command_queue_.pop();
      }

      // Clear aggregation buffer and cancel pending dispatch timer
      pending_targets_.clear();
      if (pending_dispatch_timer_) {
        pending_dispatch_timer_->cancel();
        pending_dispatch_timer_.reset();
      }
      return;
    }

    // State machine logic
    switch (global_motion_state_) {
      case MotionState::IDLE:
        // Ready for commands - nothing to do
        break;

      case MotionState::READY_FOR_COMMANDS:
        {
          // Motors in CLOSED_LOOP, waiting for commands
          // Check idle timeout - transition to IDLE to save power if no commands received
          auto elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - last_command_time_).count();

          if (elapsed > idle_timeout_seconds_) {
            RCLCPP_INFO(this->get_logger(),
                       "⏱️ Idle timeout (%.2f s) exceeded - transitioning to IDLE to save power",
                       idle_timeout_seconds_);
            global_motion_state_ = MotionState::TRANSITIONING_TO_IDLE;
            last_idle_transition_time_ = std::chrono::steady_clock::now();
            set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::IDLE);
          }
          // Accept new commands with zero latency (handled in handle_position_command)
        }
        break;

      case MotionState::TRANSITIONING_TO_CLOSED_LOOP:
        {
          // Check if all CONNECTED motors have reached CLOSED_LOOP state
          bool all_closed_loop = true;
          for (const auto& pair : odrive_states_) {
            // Only check motors that have received heartbeat (are connected)
            if (pair.second.heartbeat_received) {
              if (pair.second.last_heartbeat.axis_state != odrive_cansimple::AXIS_STATE::CLOSED_LOOP_CONTROL) {
                all_closed_loop = false;
                RCLCPP_DEBUG(this->get_logger(),
                             "[SYNC] Waiting for %s (node_id=%d) to reach CLOSED_LOOP — current axis_state=%u",
                             pair.second.joint_name.c_str(), pair.first,
                             pair.second.last_heartbeat.axis_state);
              }
            }
          }

          if (all_closed_loop) {
            RCLCPP_INFO(this->get_logger(),
                        "[SYNC] All motors confirmed CLOSED_LOOP — sending batched position commands");
            global_motion_state_ = MotionState::EXECUTING_MOTION;
            int sent_count = 0;
            for (auto& pair : odrive_states_) {
              auto& state = pair.second;
              if (state.target_position.has_value()) {
                double position_turns = state.joint_to_turns(state.target_position.value());
                uint16_t arb_id = odrive_cansimple::make_arbitration_id(pair.first, odrive_cansimple::CMD::SET_INPUT_POS);
                auto data = odrive_cansimple::encode_set_input_pos(position_turns, 0.0f, 0.0f);
                if (!can_interface_->send_frame(arb_id, data)) {
                  handle_send_failure(pair.first, "SET_INPUT_POS");
                }

                RCLCPP_INFO(this->get_logger(),
                            "[SYNC] CAN SET_INPUT_POS → node_id=%d (%s): %.4f m (%.4f turns)",
                            pair.first, state.joint_name.c_str(),
                            state.target_position.value(), position_turns);
                ++sent_count;
              }
            }
            RCLCPP_INFO(this->get_logger(),
                        "[SYNC] Batched %d/%zu position frames (TRANSITIONING_TO_CLOSED_LOOP path)",
                        sent_count, odrive_states_.size());
          }
        }
        break;

      case MotionState::EXECUTING_MOTION:
        {
          // Completion detection with automatic fallback
          // Mode 1: traj_done flag (preferred) - waits for motion to start (traj_done=0) then complete (traj_done=1)
          // Mode 2: position tolerance (fallback) - checks if position within tolerance

          bool all_complete = true;
          bool timeout_exceeded = false;
          bool use_traj_done = (completion_mode_ == "traj_done" || completion_mode_ == "auto");
          bool use_position = (completion_mode_ == "position");

          for (auto& pair : odrive_states_) {
            auto& state = pair.second;

            // Only check motors that have a target position and are connected
            if (state.heartbeat_received && state.target_position.has_value()) {
              uint8_t traj_done = state.last_heartbeat.traj_done;
              double current_pos = state.turns_to_joint(state.last_encoder.pos_estimate);
              double error = std::abs(current_pos - state.target_position.value());

              // AUTO MODE: Try traj_done first, fallback to position if traj_done doesn't work
              if (completion_mode_ == "auto") {
                // Check if motion has started (traj_done goes to 0)
                if (!state.motion_started && traj_done == 0) {
                  state.motion_started = true;
                  RCLCPP_INFO(this->get_logger(), "%s: Motion started (traj_done=0, pos=%.4f m)",
                             state.joint_name.c_str(), current_pos);
                }

                // If motion never starts (traj_done stuck at 1), fallback to position tolerance
                auto elapsed = std::chrono::steady_clock::now() - state.motion_start_time;
                if (!state.motion_started && elapsed > std::chrono::milliseconds(1000)) {
                  RCLCPP_WARN(this->get_logger(),
                             "%s: traj_done stuck at 1 for >1s - FALLBACK to position tolerance mode",
                             state.joint_name.c_str());
                  use_position = true;
                  use_traj_done = false;
                }
              }

              // TRAJ_DONE MODE
              if (use_traj_done) {
                // Log current state periodically
                static int log_counter = 0;
                if (log_counter++ % 10 == 0) {
                  RCLCPP_INFO(this->get_logger(),
                              "[EXEC] %s: traj_done=%d, pos=%.4f m, target=%.4f m, error=%.4f m",
                              state.joint_name.c_str(), traj_done, current_pos,
                              state.target_position.value(), error);
                }

                // Only check for completion if motion has actually started
                if (state.motion_started) {
                  if (traj_done != 1) {
                    all_complete = false;
                  }
                } else {
                  // Motion hasn't started yet, keep waiting
                  all_complete = false;
                }
              }

              // POSITION TOLERANCE MODE (explicit or fallback)
              if (use_position) {
                // Log position periodically
                static int pos_log_counter = 0;
                if (pos_log_counter++ % 10 == 0) {
                  RCLCPP_INFO(this->get_logger(),
                              "[EXEC] %s: pos=%.4f m, target=%.4f m, error=%.4f m (tol=%.4f m)",
                              state.joint_name.c_str(), current_pos,
                              state.target_position.value(), error, state.position_tolerance);
                }

                if (error > state.position_tolerance) {
                  all_complete = false;
                }
              }

              // Check timeout
              auto elapsed = std::chrono::steady_clock::now() - state.motion_start_time;
              if (elapsed > state.motion_timeout) {
                RCLCPP_WARN(this->get_logger(), "Motion timeout for %s (%.1f s, pos=%.4f m, error=%.4f m)",
                           state.joint_name.c_str(),
                           std::chrono::duration<double>(elapsed).count(),
                           current_pos, error);
                timeout_exceeded = true;
              }

              // MOTOR STALL DETECTION (position-based)
              // Check if motor position hasn't changed significantly while far from target
              const double STALL_POSITION_THRESHOLD = 0.01;  // m - motor considered stalled if moved less than this
              const double STALL_ERROR_THRESHOLD = 0.1;      // m - only check stall if error > this
              const double STALL_CHECK_INTERVAL = 2.0;       // seconds - check stall every N seconds

              if (error > STALL_ERROR_THRESHOLD) {
                // Motor should be moving to reach target
                // Initialize stall check if first time
                if (state.last_stall_check_time.time_since_epoch().count() == 0) {
                  state.last_stall_check_position = current_pos;
                  state.last_stall_check_time = std::chrono::steady_clock::now();
                } else {
                  // Check if enough time has passed since last stall check
                  auto time_since_last_check = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - state.last_stall_check_time).count();

                  if (time_since_last_check >= STALL_CHECK_INTERVAL) {
                    // Check how much position has changed
                    double position_change = std::abs(current_pos - state.last_stall_check_position);

                    if (position_change < STALL_POSITION_THRESHOLD) {
                      // Position hasn't changed enough - motor is stalled!
                      RCLCPP_ERROR(this->get_logger(),
                                 "🛑 MOTOR STALL DETECTED: %s position change=%.4f m (< %.3f m threshold) over %.1f s, error=%.4f m",
                                 state.joint_name.c_str(), position_change, STALL_POSITION_THRESHOLD,
                                 time_since_last_check, error);

                      // Treat stall as error - call error handler
                      handle_motor_error(pair.first);
                      return;  // Exit state machine update - error handler takes over
                    }

                    // Update stall check tracking
                    state.last_stall_check_position = current_pos;
                    state.last_stall_check_time = std::chrono::steady_clock::now();
                  }
                }
              } else {
                // Close to target - reset stall detection
                state.last_stall_check_time = std::chrono::steady_clock::time_point{};
              }
            }
          }

          if (all_complete || timeout_exceeded) {
            // Log final positions
            for (const auto& pair : odrive_states_) {
              const auto& state = pair.second;
              if (state.heartbeat_received && state.target_position.has_value()) {
                double final_pos = state.turns_to_joint(state.last_encoder.pos_estimate);
                double error = final_pos - state.target_position.value();
                RCLCPP_INFO(this->get_logger(),
                            "[MOTION] %s: complete. start=%.4f m, target=%.4f m, final=%.4f m, error=%.4f m",
                            state.joint_name.c_str(), state.start_position,
                            state.target_position.value(), final_pos, error);
              }
            }

            // Log completion reason
            if (all_complete) {
              if (use_traj_done) {
                RCLCPP_INFO(this->get_logger(), "[MOTION] All trajectories complete (traj_done=1)");
              } else {
                RCLCPP_INFO(this->get_logger(), "[MOTION] All positions reached (within tolerance)");
              }
            } else {
              RCLCPP_WARN(this->get_logger(), "[MOTION] Timeout exceeded — treating as complete");
            }

            // Check if we have queued commands - if so, stay in CLOSED_LOOP
            if (!command_queue_.empty()) {
              RCLCPP_INFO(this->get_logger(),
                          "[QUEUE] Processing next queued command (%zu remaining) — staying in CLOSED_LOOP",
                          command_queue_.size());

              // Get next command
              auto next_command = command_queue_.front();
              command_queue_.pop();

              // Clear previous target positions
              for (auto& pair : odrive_states_) {
                pair.second.target_position = std::nullopt;
              }

              // Start next motion using internal function (Issue 4 fix:
              // next_command now contains all 3 motor targets, not just 1).
              for (const auto& cmd_pair : next_command) {
                uint8_t node_id = cmd_pair.first;
                double target_position = cmd_pair.second;
                start_motion_internal(node_id, target_position);
              }

              // Note: start_motion_internal now batches CAN frames for all motors
              // in the loop above — no separate re-send loop needed here.

              // Stay in EXECUTING_MOTION state - no transition needed
            } else {
              // Queue is empty — transition to READY_FOR_COMMANDS (stay in CLOSED_LOOP)
              RCLCPP_INFO(this->get_logger(),
                          "[STATE] Motion complete — READY_FOR_COMMANDS (motors staying in CLOSED_LOOP)");
              global_motion_state_ = MotionState::READY_FOR_COMMANDS;
              motion_in_progress_ = false;
              last_command_time_ = std::chrono::steady_clock::now();  // Start idle timeout

              // Clear old queued commands if trajectory updates are enabled
              if (enable_trajectory_updates_) {
                while (!command_queue_.empty()) {
                  command_queue_.pop();
                }
              }

              // Clear target positions (nullopt = "no command pending")
              for (auto& pair : odrive_states_) {
                pair.second.target_position = std::nullopt;
              }
            }
          }
        }
        break;

      case MotionState::TRANSITIONING_TO_IDLE:
        {
          // Check if all CONNECTED motors have reached IDLE state
          bool all_idle = true;
          for (const auto& pair : odrive_states_) {
            // Only check motors that have received heartbeat (are connected)
            if (pair.second.heartbeat_received) {
              if (pair.second.last_heartbeat.axis_state != odrive_cansimple::AXIS_STATE::IDLE) {
                all_idle = false;
                break;
              }
            }
          }

          if (all_idle) {
            RCLCPP_INFO(this->get_logger(), "[STATE] All motors in IDLE");
            global_motion_state_ = MotionState::IDLE;
            motion_in_progress_ = false;

            // Clear target positions
            for (auto& pair : odrive_states_) {
              pair.second.target_position = std::nullopt;
            }

            // Note: Queue processing now happens in EXECUTING_MOTION state
            // to avoid unnecessary IDLE transitions
          }
        }
        break;

      case MotionState::ERROR_STATE:
        // Wait for errors to clear, then return to IDLE
        {
          bool all_clear = true;
          for (const auto& pair : odrive_states_) {
            if (pair.second.last_heartbeat.axis_error != 0) {
              all_clear = false;
              break;
            }
          }

          if (all_clear) {
            RCLCPP_INFO(this->get_logger(), "[STATE] ERROR_STATE → IDLE (all axis_error fields cleared)");
            global_motion_state_ = MotionState::IDLE;
          }
        }
        break;
    }
  }

  // Service: /set_axis_state
  void handle_set_axis_state(
    const std::shared_ptr<motor_control_msgs::srv::SetAxisState::Request> request,
    std::shared_ptr<motor_control_msgs::srv::SetAxisState::Response> response)
  {
    std::lock_guard<std::mutex> lock(state_mutex_);

    std::vector<uint8_t> node_ids_to_set;

    if (request->joint_id == -1) {
      // Set state for all joints
      for (const auto& pair : odrive_states_) {
        node_ids_to_set.push_back(pair.first);
      }
    } else {
      // Set state for specific joint
      auto it = joint_id_to_node_id_.find(request->joint_id);
      if (it == joint_id_to_node_id_.end()) {
        response->success = false;
        response->reason = "Unknown joint_id: " + std::to_string(request->joint_id);
        return;
      }
      node_ids_to_set.push_back(it->second);
    }

    // Check if requesting IDLE state - clear queue and reset motion state
    if (request->axis_state == odrive_cansimple::AXIS_STATE::IDLE) {
      // Clear command queue
      size_t queue_size = command_queue_.size();
      while (!command_queue_.empty()) {
        command_queue_.pop();
      }

      // Reset motion state
      motion_in_progress_ = false;

      // Clear aggregation buffer and cancel pending dispatch timer
      pending_targets_.clear();
      if (pending_dispatch_timer_) {
        pending_dispatch_timer_->cancel();
        pending_dispatch_timer_.reset();
      }

      // Log the action
      if (queue_size > 0) {
        RCLCPP_WARN(this->get_logger(),
                    "Manual IDLE requested - cleared %zu queued commands and reset motion state",
                    queue_size);
      } else {
        RCLCPP_INFO(this->get_logger(), "Manual IDLE requested - no queued commands to clear");
      }

      // Update global state (unless in error state, keep error state)
      if (global_motion_state_ != MotionState::ERROR_STATE) {
        global_motion_state_ = MotionState::IDLE;
      }
    }

    // Send Set_Axis_State command to each motor
    for (uint8_t node_id : node_ids_to_set) {
      const auto& state = odrive_states_[node_id];

      uint16_t arb_id = odrive_cansimple::make_arbitration_id(node_id, odrive_cansimple::CMD::SET_AXIS_STATE);
      auto data = odrive_cansimple::encode_set_axis_state(request->axis_state);

      if (!can_interface_->send_frame(arb_id, data)) {
        handle_send_failure(node_id, "SET_AXIS_STATE");
      }

      RCLCPP_INFO(this->get_logger(), "Set axis state for %s (node_id=%d) to %u",
                  state.joint_name.c_str(), node_id, request->axis_state);
    }

    response->success = true;
    response->reason = "Axis state set for " + std::to_string(node_ids_to_set.size()) + " joint(s)";
  }

  // Service: /emergency_stop
  void handle_emergency_stop(
    const std::shared_ptr<motor_control_msgs::srv::EmergencyStop::Request> request,
    std::shared_ptr<motor_control_msgs::srv::EmergencyStop::Response> response)
  {
    std::lock_guard<std::mutex> lock(state_mutex_);

    if (request->activate) {
      // ACTIVATE EMERGENCY STOP
      RCLCPP_ERROR(this->get_logger(), "🚨 EMERGENCY STOP ACTIVATED 🚨");

      // 1. Immediately send IDLE to all motors
      set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::IDLE);

      // 2. Clear all queued commands
      int32_t commands_cleared = 0;
      while (!command_queue_.empty()) {
        command_queue_.pop();
        commands_cleared++;
      }

      // 3. Set emergency stop flag
      emergency_stop_active_ = true;
      motion_in_progress_ = false;
      global_motion_state_ = MotionState::IDLE;

      // 4. Clear all target positions
      for (auto& pair : odrive_states_) {
        pair.second.target_position = std::nullopt;
      }

      // 5. Clear aggregation buffer and cancel pending dispatch timer
      pending_targets_.clear();
      if (pending_dispatch_timer_) {
        pending_dispatch_timer_->cancel();
        pending_dispatch_timer_.reset();
      }

      RCLCPP_ERROR(this->get_logger(),
                   "Emergency stop complete: All motors IDLE, %d commands cleared, system locked",
                   commands_cleared);
      RCLCPP_ERROR(this->get_logger(),
                   "Call service again with activate=false to unlock system");

      response->success = true;
      response->message = "Emergency stop activated - system locked";
      response->commands_cleared = commands_cleared;

    } else {
      // DEACTIVATE EMERGENCY STOP (RESUME)
      if (!emergency_stop_active_) {
        response->success = false;
        response->message = "No emergency stop active";
        response->commands_cleared = 0;
        RCLCPP_WARN(this->get_logger(), "Resume requested but no emergency stop active");
        return;
      }

      emergency_stop_active_ = false;

      RCLCPP_WARN(this->get_logger(), "Emergency stop cleared - system ready for new commands");

      response->success = true;
      response->message = "Emergency stop cleared - system operational";
      response->commands_cleared = 0;
    }
  }

  // Service: /drive_stop
  void handle_drive_stop(
      const std::shared_ptr<motor_control_msgs::srv::DriveStop::Request> request,
      std::shared_ptr<motor_control_msgs::srv::DriveStop::Response> response)
  {
    std::lock_guard<std::mutex> lock(state_mutex_);

    if (request->activate) {
      // ACTIVATE: Stop motors and clear queue
      RCLCPP_WARN(this->get_logger(), "🛑 DRIVE STOP ACTIVATED 🛑");

      // Count queued commands
      int cleared = command_queue_.size();

      // Clear command queue
      while (!command_queue_.empty()) {
        command_queue_.pop();
      }

      // Set all motors to IDLE
      set_all_motors_axis_state(odrive_cansimple::AXIS_STATE::IDLE);
      global_motion_state_ = MotionState::IDLE;
      motion_in_progress_ = false;

      // Clear aggregation buffer and cancel pending dispatch timer
      pending_targets_.clear();
      if (pending_dispatch_timer_) {
        pending_dispatch_timer_->cancel();
        pending_dispatch_timer_.reset();
      }

      // Set drive stop flag
      drive_stop_active_ = true;

      response->success = true;
      response->message = "Drive stop activated - motors stopped, queue cleared";
      response->commands_cleared = cleared;

      RCLCPP_INFO(this->get_logger(),
                 "Drive stop complete: Motors IDLE, %d commands cleared", cleared);
    } else {
      // DEACTIVATE: Resume normal operation
      if (!drive_stop_active_) {
        response->success = true;
        response->message = "Drive stop already inactive";
        response->commands_cleared = 0;
        return;
      }

      drive_stop_active_ = false;

      response->success = true;
      response->message = "Drive stop deactivated - motors ready for commands";
      response->commands_cleared = 0;

      RCLCPP_INFO(this->get_logger(), "Drive stop cleared - system ready for commands");
    }
  }

  // Service: /joint_status
  void handle_joint_status(
    const std::shared_ptr<motor_control_msgs::srv::JointStatus::Request> request,
    std::shared_ptr<motor_control_msgs::srv::JointStatus::Response> response)
  {
    std::lock_guard<std::mutex> lock(state_mutex_);

    std::vector<uint8_t> node_ids_to_query;

    if (request->joint_id == -1) {
      // Query all joints
      for (const auto& pair : odrive_states_) {
        node_ids_to_query.push_back(pair.first);
      }
    } else {
      // Query specific joint
      auto it = joint_id_to_node_id_.find(request->joint_id);
      if (it == joint_id_to_node_id_.end()) {
        response->success = false;
        response->reason = "Unknown joint_id: " + std::to_string(request->joint_id);
        return;
      }
      node_ids_to_query.push_back(it->second);
    }

    // Populate response
    for (uint8_t node_id : node_ids_to_query) {
      const auto& state = odrive_states_[node_id];

      response->joint_ids.push_back(state.joint_id);

      if (state.encoder_received) {
        response->positions.push_back(state.turns_to_joint(state.last_encoder.pos_estimate));
        response->velocities.push_back(state.turns_to_joint(state.last_encoder.vel_estimate));
      } else {
        response->positions.push_back(0.0);
        response->velocities.push_back(0.0);
      }

      response->efforts.push_back(0.0);  // Not available
      response->temperatures.push_back(0.0);  // Not available
      response->error_counts.push_back(state.last_error.active_errors);

      // Status message
      std::string status_msg = state.joint_name + ": ";
      if (state.heartbeat_received) {
        status_msg += "axis_state=" + std::to_string(state.last_heartbeat.axis_state);
        status_msg += ", axis_error=" + std::to_string(state.last_heartbeat.axis_error);
      } else {
        status_msg += "No heartbeat";
      }
      response->status_messages.push_back(status_msg);
    }

    response->success = true;
    response->reason = "Status retrieved for " + std::to_string(node_ids_to_query.size()) + " joint(s)";
  }

  // Member variables
  std::string interface_name_;
  std::shared_ptr<odrive_cansimple::SocketCANInterface> can_interface_;

  std::map<uint8_t, ODriveState> odrive_states_;  // node_id → state
  std::map<std::string, uint8_t> joint_name_to_node_id_;
  std::map<int32_t, uint8_t> joint_id_to_node_id_;

  std::mutex state_mutex_;

  // Global motion control state (synchronized across all motors)
  MotionState global_motion_state_ = MotionState::IDLE;
  std::queue<std::map<uint8_t, double>> command_queue_;  // Queue of position commands (node_id → position)
  bool motion_in_progress_ = false;
  std::string completion_mode_;  // "auto", "traj_done", or "position"
  double expected_velocity_;  // Expected velocity for timeout calculation (m/s)
  double timeout_safety_margin_;  // Extra time added to timeout (seconds)
  bool incremental_position_;  // true = relative positioning, false = absolute positioning

  // Smooth motion control parameters
  double idle_timeout_seconds_;  // Time to wait before transitioning to IDLE state
  double min_command_interval_seconds_;  // Minimum interval between position commands
  bool enable_trajectory_updates_;  // Allow trajectory updates during motion
  std::chrono::steady_clock::time_point last_command_time_;  // Timestamp of last position command
  std::chrono::steady_clock::time_point last_idle_transition_time_;  // Timestamp of last transition to IDLE

  // Aggregation sync mode — buffers per-motor callbacks and dispatches as one CAN burst
  std::string sync_mode_;                                // "aggregation" or "combined_topic"
  double aggregation_window_ms_;                         // Max wait time for all motors (ms)
  std::map<uint8_t, double> pending_targets_;            // node_id → computed target (buffer)
  rclcpp::TimerBase::SharedPtr pending_dispatch_timer_;  // One-shot aggregation window timer

  std::thread rx_thread_;
  std::atomic<bool> rx_thread_running_;

  // ROS2 interfaces
  rclcpp::Service<motor_control_msgs::srv::JointStatus>::SharedPtr status_service_;
  rclcpp::Service<motor_control_msgs::srv::SetAxisState>::SharedPtr set_axis_state_service_;
  rclcpp::Service<motor_control_msgs::srv::EmergencyStop>::SharedPtr emergency_stop_service_;

  bool emergency_stop_active_ = false;

  rclcpp::Service<motor_control_msgs::srv::DriveStop>::SharedPtr drive_stop_service_;
  bool drive_stop_active_ = false;

  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_states_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diagnostics_pub_;
  rclcpp::TimerBase::SharedPtr joint_states_timer_;
  uint32_t joint_states_log_counter_ = 0;  // Throttle counter for periodic joint_states log

  std::map<uint8_t, rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr> position_command_subs_;

  rclcpp::TimerBase::SharedPtr encoder_request_timer_;
  rclcpp::TimerBase::SharedPtr state_machine_timer_;
  rclcpp::TimerBase::SharedPtr heartbeat_timeout_timer_;
};

}  // namespace odrive_control_ros2

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<odrive_control_ros2::ODriveServiceNode>();

  // Use spin_once(100ms) loop instead of rclcpp::spin() to prevent
  // executor busy-spinning.  Matches MG6010 pattern
  // (mg6010_controller_node.cpp:4484-4488).
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  while (rclcpp::ok()) {
    executor.spin_once(std::chrono::milliseconds(100));
  }

  rclcpp::shutdown();
  return 0;
}
