/*
 * ActionServerManager implementation.
 *
 * Part of mg6010-decomposition Phase 2 (Steps 5-6).
 * Owns 3 action servers: StepResponseTest, JointPositionCommand, JointHoming.
 * All motor access goes through MotorManager references; all parent-node
 * interactions go through ActionCallbacks (design decision D2).
 */

#include "motor_control_ros2/action_server_manager.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace motor_control_ros2
{

// ── Helper: find motor index by CAN ID ──────────────────────────────────

static size_t findMotorByCanId(MotorManager & mm, uint8_t can_id)
{
  for (size_t i = 0; i < mm.motorCount(); ++i) {
    auto motor = mm.getMotor(i);
    if (motor && motor->get_configuration().can_id == can_id) {
      return i;
    }
  }
  return SIZE_MAX;
}

// ── Helper: resolve joint_id to motor index (god-class hybrid logic) ────
// Tries "joint<N>" name match first, then falls back to raw index.

static size_t resolveJointId(MotorManager & mm, int64_t joint_id)
{
  // First: try CAN-ID match (action tests use CAN IDs as joint_id)
  if (joint_id > 0 && joint_id <= 255) {
    size_t idx = findMotorByCanId(mm, static_cast<uint8_t>(joint_id));
    if (idx != SIZE_MAX) return idx;
  }
  // Fallback: raw index
  if (joint_id >= 0 && static_cast<size_t>(joint_id) < mm.motorCount()) {
    return static_cast<size_t>(joint_id);
  }
  return SIZE_MAX;
}

// ── Constructor ──────────────────────────────────────────────────────────

ActionServerManager::ActionServerManager(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  MotorManager & motor_manager,
  ActionCallbacks callbacks)
: node_(std::move(node)),
  motor_manager_(motor_manager),
  callbacks_(std::move(callbacks))
{
  if (!node_) {
    throw std::invalid_argument("ActionServerManager: node must not be null");
  }
  if (!callbacks_.handle_motor_failure) {
    throw std::invalid_argument(
      "ActionServerManager: handle_motor_failure callback must not be empty");
  }
  if (!callbacks_.check_j3j4_interlock) {
    throw std::invalid_argument(
      "ActionServerManager: check_j3j4_interlock callback must not be empty");
  }
  if (!callbacks_.set_watchdog_exempt) {
    throw std::invalid_argument(
      "ActionServerManager: set_watchdog_exempt callback must not be empty");
  }

  const size_t n = motor_manager_.motorCount();

  // Size per-joint active flags
  joint_pos_cmd_active_.resize(n, false);

  // Size motion tracking vectors
  motor_busy_flags_.resize(n, false);
  motor_command_times_.resize(n);
  last_commanded_positions_.resize(n, 0.0);

  motion_pending_.resize(n, false);
  motion_target_positions_.resize(n, 0.0);
  motion_start_times_.resize(n);
  motion_in_tolerance_.resize(n, false);
  motion_in_tolerance_since_.resize(n);

  last_feedback_valid_.resize(n, false);
  last_feedback_position_.resize(n, 0.0);
  last_feedback_time_.resize(n);

  pos_cmd_received_.resize(n, 0);
  pos_cmd_sent_ok_.resize(n, 0);
  pos_cmd_sent_fail_.resize(n, 0);
  pos_cmd_reached_ok_.resize(n, 0);
  pos_cmd_reached_timeout_.resize(n, 0);

  motion_feedback_position_tolerance_by_motor_.resize(
    n, motion_feedback_position_tolerance_);

  // Create action servers
  using namespace std::placeholders;

  step_response_server_ = rclcpp_action::create_server<StepResponseTest>(
    node_, "~/step_response_test",
    std::bind(&ActionServerManager::handleStepResponseGoal, this, _1, _2),
    std::bind(&ActionServerManager::handleStepResponseCancel, this, _1),
    std::bind(&ActionServerManager::handleStepResponseAccepted, this, _1));

  joint_pos_cmd_server_ = rclcpp_action::create_server<JointPosCmd>(
    node_, "/joint_position_command",
    std::bind(&ActionServerManager::handleJointPosCmdGoal, this, _1, _2),
    std::bind(&ActionServerManager::handleJointPosCmdCancel, this, _1),
    std::bind(&ActionServerManager::handleJointPosCmdAccepted, this, _1));

  joint_homing_server_ = rclcpp_action::create_server<JointHomingAction>(
    node_, "/joint_homing",
    std::bind(&ActionServerManager::handleJointHomingGoal, this, _1, _2),
    std::bind(&ActionServerManager::handleJointHomingCancel, this, _1),
    std::bind(&ActionServerManager::handleJointHomingAccepted, this, _1));

  RCLCPP_INFO(node_->get_logger(),
    "ActionServerManager: created 3 action servers for %zu motors", n);
}

// ── Destructor ───────────────────────────────────────────────────────────

ActionServerManager::~ActionServerManager()
{
  shutdown_requested_.store(true);

  if (step_test_thread_.joinable()) {
    step_test_thread_.join();
  }
  for (auto & [idx, t] : joint_pos_cmd_threads_) {
    if (t.joinable()) {
      t.join();
    }
  }
  if (joint_homing_thread_.joinable()) {
    joint_homing_thread_.join();
  }
}

// ═════════════════════════════════════════════════════════════════════════
// StepResponseTest
// ═════════════════════════════════════════════════════════════════════════

rclcpp_action::GoalResponse ActionServerManager::handleStepResponseGoal(
  const rclcpp_action::GoalUUID & /*uuid*/,
  std::shared_ptr<const StepResponseTest::Goal> goal)
{
  // Validate motor exists via CAN ID
  const size_t idx = findMotorByCanId(motor_manager_, goal->motor_id);
  if (idx == SIZE_MAX) {
    RCLCPP_WARN(node_->get_logger(),
      "StepResponseTest: REJECTED - motor_id=%d not found", goal->motor_id);
    return rclcpp_action::GoalResponse::REJECT;
  }

  auto motor = motor_manager_.getMotor(idx);
  if (!motor || !motor_manager_.isAvailable(idx)) {
    RCLCPP_WARN(node_->get_logger(),
      "StepResponseTest: REJECTED - motor_id=%d unavailable", goal->motor_id);
    return rclcpp_action::GoalResponse::REJECT;
  }

  // Validate parameters
  if (goal->duration_seconds <= 0.0f) {
    RCLCPP_WARN(node_->get_logger(),
      "StepResponseTest: REJECTED - duration_seconds must be > 0");
    return rclcpp_action::GoalResponse::REJECT;
  }
  if (std::abs(goal->step_size_degrees) < 0.01f) {
    RCLCPP_WARN(node_->get_logger(),
      "StepResponseTest: REJECTED - step_size_degrees too small");
    return rclcpp_action::GoalResponse::REJECT;
  }

  // Check if another step test is already running
  {
    std::lock_guard<std::mutex> lock(step_test_mutex_);
    if (step_test_running_) {
      RCLCPP_WARN(node_->get_logger(),
        "StepResponseTest: REJECTED - another test is already running");
      return rclcpp_action::GoalResponse::REJECT;
    }
  }

  RCLCPP_INFO(node_->get_logger(),
    "StepResponseTest: ACCEPTED motor_id=%d step=%.1f deg duration=%.1f s",
    goal->motor_id, goal->step_size_degrees, goal->duration_seconds);
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse ActionServerManager::handleStepResponseCancel(
  std::shared_ptr<GoalHandleStepResponse> /*goal_handle*/)
{
  RCLCPP_INFO(node_->get_logger(), "StepResponseTest: cancel requested");
  return rclcpp_action::CancelResponse::ACCEPT;
}

void ActionServerManager::handleStepResponseAccepted(
  std::shared_ptr<GoalHandleStepResponse> goal_handle)
{
  if (step_test_thread_.joinable()) {
    step_test_thread_.join();
  }

  {
    std::lock_guard<std::mutex> lock(step_test_mutex_);
    step_test_running_ = true;
  }

  step_test_thread_ = std::thread(
    &ActionServerManager::executeStepResponseTest, this, std::move(goal_handle));
}

void ActionServerManager::executeStepResponseTest(
  std::shared_ptr<GoalHandleStepResponse> goal_handle)
{
  auto result = std::make_shared<StepResponseTest::Result>();
  result->success = false;

  const auto goal = goal_handle->get_goal();
  const size_t idx = findMotorByCanId(motor_manager_, goal->motor_id);

  // Safety lambda: hold position and clear running flag
  auto cleanup = [&](double hold_position) {
    auto motor = motor_manager_.getMotor(idx);
    if (motor) {
      motor->set_position(hold_position, 0.0, 0.0);
    }
    std::lock_guard<std::mutex> lock(step_test_mutex_);
    step_test_running_ = false;
  };

  // Validate motor is still available
  auto motor = motor_manager_.getMotor(idx);
  if (idx == SIZE_MAX || !motor) {
    result->error_message = "Motor not available";
    cleanup(0.0);
    goal_handle->abort(result);
    return;
  }

  // Get temperature limit from motor config
  const double temp_limit = motor->get_configuration().limits.temperature_max;

  // Record initial position (in joint units — rotations for MG6010)
  const double initial_position = motor->get_position();

  // Convert step size from degrees to joint units (rotations)
  const double step_size_rotations =
    static_cast<double>(goal->step_size_degrees) / 360.0;
  const double target_position = initial_position + step_size_rotations;
  const double max_deviation = std::abs(step_size_rotations) * 2.0;

  // Convert target to degrees for result setpoint
  result->setpoint =
    initial_position * 360.0 + static_cast<double>(goal->step_size_degrees);

  RCLCPP_INFO(node_->get_logger(),
    "StepResponseTest: START motor_id=%d initial=%.4f rot target=%.4f rot "
    "step=%.1f deg duration=%.1f s temp_limit=%.0f C",
    goal->motor_id, initial_position, target_position,
    goal->step_size_degrees, goal->duration_seconds, temp_limit);

  // Pre-allocate data vectors (10 Hz * duration)
  const double sample_rate_hz = 10.0;
  const double duration_s = static_cast<double>(goal->duration_seconds);
  const size_t estimated_samples =
    static_cast<size_t>(sample_rate_hz * duration_s) + 10;
  result->timestamps.reserve(estimated_samples);
  result->positions.reserve(estimated_samples);
  result->velocities.reserve(estimated_samples);
  result->currents.reserve(estimated_samples);

  // Command the step
  if (!motor->set_position(target_position, 0.0, 0.0)) {
    result->error_message = "Failed to command step position";
    cleanup(initial_position);
    goal_handle->abort(result);
    RCLCPP_ERROR(node_->get_logger(),
      "StepResponseTest: %s", result->error_message.c_str());
    return;
  }

  // Mark motor as busy
  if (idx < motor_manager_.motorCount()) {
    motor_busy_flags_[idx] = true;
    motor_command_times_[idx] = std::chrono::steady_clock::now();
    last_commanded_positions_[idx] = target_position;
  }

  // Data collection loop at 10 Hz
  const auto test_start = std::chrono::steady_clock::now();
  const auto sample_period = std::chrono::duration<double>(1.0 / sample_rate_hz);
  auto next_sample_time = test_start;

  while (rclcpp::ok() && !shutdown_requested_.load()) {
    // Check for cancellation
    if (goal_handle->is_canceling()) {
      RCLCPP_INFO(node_->get_logger(), "StepResponseTest: CANCELED by client");
      result->success = false;
      result->error_message = "Test canceled by client";
      cleanup(target_position);
      goal_handle->canceled(result);
      return;
    }

    const auto now = std::chrono::steady_clock::now();
    const double elapsed_s =
      std::chrono::duration<double>(now - test_start).count();

    // Check duration complete
    if (elapsed_s >= duration_s) {
      break;
    }

    // Wait until next sample time
    if (now < next_sample_time) {
      // BLOCKING_SLEEP_OK: dedicated step-test thread, 10Hz data acquisition — reviewed 2026-03-14
      std::this_thread::sleep_until(next_sample_time);
    }
    next_sample_time += std::chrono::duration_cast<
      std::chrono::steady_clock::duration>(sample_period);

    // Read motor state
    const double current_position = motor->get_position();
    const double current_velocity = motor->get_velocity();
    const auto status = motor->get_status();

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

    // --- Safety checks ---

    // Check position deviation: abort if > 2x step size from target
    const double deviation = std::abs(current_position - target_position);
    if (deviation > max_deviation && max_deviation > 0.001) {
      result->error_message = "Position deviation " +
        std::to_string(deviation * 360.0) + " deg exceeds safety limit " +
        std::to_string(max_deviation * 360.0) + " deg (2x step size)";
      RCLCPP_ERROR(node_->get_logger(),
        "StepResponseTest: ABORT - %s", result->error_message.c_str());
      cleanup(target_position);
      goal_handle->abort(result);
      return;
    }

    // Check temperature: abort if > configured limit
    if (status.temperature > temp_limit) {
      result->error_message = "Motor temperature " +
        std::to_string(status.temperature) + " C exceeds limit " +
        std::to_string(temp_limit) + " C";
      RCLCPP_ERROR(node_->get_logger(),
        "StepResponseTest: ABORT - %s", result->error_message.c_str());
      cleanup(target_position);
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
  cleanup(target_position);
  goal_handle->succeed(result);

  RCLCPP_INFO(node_->get_logger(),
    "StepResponseTest: COMPLETE motor_id=%d samples=%zu",
    goal->motor_id, result->timestamps.size());
}

// ═════════════════════════════════════════════════════════════════════════
// JointPositionCommand
// ═════════════════════════════════════════════════════════════════════════

rclcpp_action::GoalResponse ActionServerManager::handleJointPosCmdGoal(
  const rclcpp_action::GoalUUID & /*uuid*/,
  std::shared_ptr<const JointPosCmd::Goal> goal)
{
  // Resolve joint_id to motor index
  const size_t idx = resolveJointId(motor_manager_, goal->joint_id);
  if (idx == SIZE_MAX) {
    RCLCPP_WARN(node_->get_logger(),
      "JointPosCmd: REJECTED - unknown joint_id=%ld", goal->joint_id);
    return rclcpp_action::GoalResponse::REJECT;
  }

  auto motor = motor_manager_.getMotor(idx);
  if (!motor || !motor_manager_.isAvailable(idx)) {
    RCLCPP_WARN(node_->get_logger(),
      "JointPosCmd: REJECTED - motor unavailable for joint_id=%ld",
      goal->joint_id);
    return rclcpp_action::GoalResponse::REJECT;
  }

  if (!motor_manager_.isEnabled(idx)) {
    RCLCPP_WARN(node_->get_logger(),
      "JointPosCmd: REJECTED - motor disabled for joint_id=%ld",
      goal->joint_id);
    return rclcpp_action::GoalResponse::REJECT;
  }

  // J3/J4 interlock check
  if (callbacks_.check_j3j4_interlock(
        idx, goal->target_position, "joint_position_command_action")) {
    RCLCPP_WARN(node_->get_logger(),
      "JointPosCmd: REJECTED - J4 interlock (J3 in parking zone)");
    return rclcpp_action::GoalResponse::REJECT;
  }

  // Per-joint active check
  {
    std::lock_guard<std::mutex> lock(joint_pos_cmd_mutex_);
    if (idx < joint_pos_cmd_active_.size() && joint_pos_cmd_active_[idx]) {
      RCLCPP_WARN(node_->get_logger(),
        "JointPosCmd: REJECTED - joint_id=%ld already has active command",
        goal->joint_id);
      return rclcpp_action::GoalResponse::REJECT;
    }
  }

  RCLCPP_INFO(node_->get_logger(),
    "JointPosCmd: ACCEPTED joint_id=%ld target=%.4f max_vel=%.2f",
    goal->joint_id, goal->target_position, goal->max_velocity);
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse ActionServerManager::handleJointPosCmdCancel(
  std::shared_ptr<GoalHandleJointPosCmd> /*goal_handle*/)
{
  RCLCPP_INFO(node_->get_logger(), "JointPosCmd: cancel requested");
  return rclcpp_action::CancelResponse::ACCEPT;
}

void ActionServerManager::handleJointPosCmdAccepted(
  std::shared_ptr<GoalHandleJointPosCmd> goal_handle)
{
  const auto goal = goal_handle->get_goal();
  const size_t idx = resolveJointId(motor_manager_, goal->joint_id);

  // Join previous thread for this joint (if any — it will have finished since
  // the goal handler rejects duplicate joints)
  auto it = joint_pos_cmd_threads_.find(idx);
  if (it != joint_pos_cmd_threads_.end() && it->second.joinable()) {
    it->second.join();
  }

  joint_pos_cmd_threads_[idx] = std::thread(
    &ActionServerManager::executeJointPositionCommand, this,
    std::move(goal_handle));
}

void ActionServerManager::executeJointPositionCommand(
  std::shared_ptr<GoalHandleJointPosCmd> goal_handle)
{
  auto result = std::make_shared<JointPosCmd::Result>();
  result->success = false;

  const auto goal = goal_handle->get_goal();
  const size_t idx = resolveJointId(motor_manager_, goal->joint_id);

  // Mark joint as active
  {
    std::lock_guard<std::mutex> lock(joint_pos_cmd_mutex_);
    if (idx < joint_pos_cmd_active_.size()) {
      joint_pos_cmd_active_[idx] = true;
    }
  }

  // Cleanup lambda: clear active flag and motion state
  auto cleanup = [&]() {
    if (idx < motor_manager_.motorCount()) {
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
  auto motor = motor_manager_.getMotor(idx);
  if (idx == SIZE_MAX || !motor) {
    result->reason = "Motor not available";
    cleanup();
    goal_handle->abort(result);
    return;
  }

  // J3/J4 interlock check (in execute, not just goal handler)
  if (callbacks_.check_j3j4_interlock(
        idx, goal->target_position, "executeJointPositionCommand")) {
    result->success = false;
    result->reason = "INTERLOCK";
    result->actual_position = motor->get_position();
    cleanup();
    goal_handle->abort(result);
    return;
  }

  const double target = goal->target_position;

  // Stats
  total_position_commands_++;
  if (idx < motor_manager_.motorCount()) {
    pos_cmd_received_[idx]++;
  }

  // Mark motor busy
  if (idx < motor_manager_.motorCount()) {
    motor_busy_flags_[idx] = true;
    motor_command_times_[idx] = std::chrono::steady_clock::now();
    last_commanded_positions_[idx] = target;
  }

  // Send command
  const double max_vel = goal->max_velocity;
  const bool ok = motor->set_position(target, max_vel, 0.0);
  if (!ok) {
    if (idx < motor_manager_.motorCount()) {
      pos_cmd_sent_fail_[idx]++;
    }
    callbacks_.handle_motor_failure(
      idx, "position", target, "CAN_COMMAND_FAILED", __func__);
    result->reason = "ERROR";
    result->actual_position = motor->get_position();
    cleanup();
    goal_handle->abort(result);
    return;
  }

  if (idx < motor_manager_.motorCount()) {
    pos_cmd_sent_ok_[idx]++;
    {
      std::lock_guard<std::mutex> lock(motion_mutex_);
      motion_pending_[idx] = true;
      motion_target_positions_[idx] = target;
      motion_start_times_[idx] = std::chrono::steady_clock::now();
      motion_in_tolerance_[idx] = false;
    }
  }

  // Exempt watchdog during blocking position feedback loop (task 1.8)
  callbacks_.set_watchdog_exempt(true);

  // Feedback loop at ~20Hz (50ms period)
  const auto start = std::chrono::steady_clock::now();
  bool in_tol = false;
  auto in_tol_since = start;
  const auto poll_period = std::chrono::milliseconds(50);

  while (rclcpp::ok() && !shutdown_requested_.load()) {
    // Check for cancellation (safe deceleration)
    if (goal_handle->is_canceling()) {
      RCLCPP_INFO(node_->get_logger(),
        "JointPosCmd: CANCELING joint_id=%ld — safe stop", goal->joint_id);
      motor->stop();
      // BLOCKING_SLEEP_OK: dedicated action thread, 200ms motor deceleration settle — reviewed 2026-03-14
      std::this_thread::sleep_for(std::chrono::milliseconds(200));
      result->success = false;
      result->reason = "CANCELLED";
      result->actual_position = motor->get_position();
      callbacks_.set_watchdog_exempt(false);
      cleanup();
      goal_handle->canceled(result);
      return;
    }

    const auto now = std::chrono::steady_clock::now();
    const double elapsed_s =
      std::chrono::duration<double>(now - start).count();

    // Read current state
    const auto st = motor->get_status();
    const double pos = motor->get_position();
    result->actual_position = pos;

    // Update feedback snapshots
    {
      std::lock_guard<std::mutex> lock(motion_mutex_);
      if (idx < motor_manager_.motorCount()) {
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

    // Check tolerance + settle
    if (st.hardware_connected) {
      const double err = std::abs(pos - target);
      const double tol =
        (idx < motion_feedback_position_tolerance_by_motor_.size())
          ? motion_feedback_position_tolerance_by_motor_[idx]
          : motion_feedback_position_tolerance_;
      if (err <= tol) {
        if (!in_tol) {
          in_tol = true;
          in_tol_since = now;
        } else if ((now - in_tol_since) >= motion_feedback_settle_time_) {
          if (idx < motor_manager_.motorCount()) {
            pos_cmd_reached_ok_[idx]++;
          }
          result->success = true;
          result->reason = "REACHED";
          result->actual_position = pos;
          callbacks_.set_watchdog_exempt(false);
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
      if (idx < motor_manager_.motorCount()) {
        pos_cmd_reached_timeout_[idx]++;
      }
      result->success = false;
      result->reason = "TIMEOUT";
      result->actual_position = pos;
      callbacks_.set_watchdog_exempt(false);
      cleanup();
      goal_handle->abort(result);
      return;
    }

    // BLOCKING_SLEEP_OK: dedicated action thread, 50ms position feedback poll — reviewed 2026-03-14
    std::this_thread::sleep_for(poll_period);
  }

  // rclcpp shutting down
  callbacks_.set_watchdog_exempt(false);
  result->reason = "SHUTDOWN";
  cleanup();
  goal_handle->abort(result);
}

// ═════════════════════════════════════════════════════════════════════════
// JointHoming
// ═════════════════════════════════════════════════════════════════════════

rclcpp_action::GoalResponse ActionServerManager::handleJointHomingGoal(
  const rclcpp_action::GoalUUID & /*uuid*/,
  std::shared_ptr<const JointHomingAction::Goal> goal)
{
  // Reject if homing is already in progress
  {
    std::lock_guard<std::mutex> lock(joint_homing_mutex_);
    if (joint_homing_active_) {
      RCLCPP_WARN(node_->get_logger(),
        "JointHoming: REJECTED - homing already in progress");
      return rclcpp_action::GoalResponse::REJECT;
    }
  }

  // Validate joint IDs (if specified)
  if (!goal->joint_ids.empty()) {
    for (const auto & jid : goal->joint_ids) {
      size_t idx = resolveJointId(motor_manager_, jid);
      if (idx == SIZE_MAX) {
        RCLCPP_WARN(node_->get_logger(),
          "JointHoming: REJECTED - unknown joint_id=%d", jid);
        return rclcpp_action::GoalResponse::REJECT;
      }
    }
  }

  RCLCPP_INFO(node_->get_logger(),
    "JointHoming: ACCEPTED (%zu joints requested)",
    goal->joint_ids.empty() ? motor_manager_.motorCount()
                            : goal->joint_ids.size());
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse ActionServerManager::handleJointHomingCancel(
  std::shared_ptr<GoalHandleJointHoming> /*goal_handle*/)
{
  RCLCPP_INFO(node_->get_logger(), "JointHoming: cancel requested");
  return rclcpp_action::CancelResponse::ACCEPT;
}

void ActionServerManager::handleJointHomingAccepted(
  std::shared_ptr<GoalHandleJointHoming> goal_handle)
{
  if (joint_homing_thread_.joinable()) {
    joint_homing_thread_.join();
  }

  {
    std::lock_guard<std::mutex> lock(joint_homing_mutex_);
    joint_homing_active_ = true;
  }

  joint_homing_thread_ = std::thread(
    &ActionServerManager::executeJointHoming, this, std::move(goal_handle));
}

void ActionServerManager::executeJointHoming(
  std::shared_ptr<GoalHandleJointHoming> goal_handle)
{
  auto result = std::make_shared<JointHomingAction::Result>();
  result->success = false;

  auto cleanup = [&]() {
    std::lock_guard<std::mutex> lock(joint_homing_mutex_);
    joint_homing_active_ = false;
  };

  const auto goal = goal_handle->get_goal();

  // Build list of motor indices to home
  std::vector<size_t> joints_to_home;
  if (goal->joint_ids.empty()) {
    // Home all joints
    for (size_t i = 0; i < motor_manager_.motorCount(); ++i) {
      if (motor_manager_.getMotor(i)) {
        joints_to_home.push_back(i);
      }
    }
  } else {
    for (const auto & jid : goal->joint_ids) {
      size_t idx = resolveJointId(motor_manager_, jid);
      if (idx != SIZE_MAX) {
        joints_to_home.push_back(idx);
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
  callbacks_.set_watchdog_exempt(true);

  const size_t total_joints = joints_to_home.size();
  size_t completed = 0;

  for (size_t ji = 0; ji < total_joints; ++ji) {
    const size_t idx = joints_to_home[ji];
    const std::string jname = motor_manager_.getJointName(idx);
    auto motor = motor_manager_.getMotor(idx);

    // Check for cancellation
    if (goal_handle->is_canceling()) {
      RCLCPP_INFO(node_->get_logger(),
        "JointHoming: CANCELING after %zu/%zu joints",
        completed, total_joints);
      if (motor) {
        motor->stop();
      }
      result->success = false;
      result->reason = "CANCELLED";
      result->final_positions.clear();
      for (size_t k = 0; k <= ji && k < joints_to_home.size(); ++k) {
        auto m = motor_manager_.getMotor(joints_to_home[k]);
        result->final_positions.push_back(m ? m->get_position() : 0.0);
      }
      callbacks_.set_watchdog_exempt(false);
      cleanup();
      goal_handle->canceled(result);
      return;
    }

    // Skip drive motors
    if (jname.find("drive") != std::string::npos) {
      completed++;
      continue;
    }

    if (!motor) {
      completed++;
      continue;
    }

    // Publish feedback: starting this joint
    auto feedback = std::make_shared<JointHomingAction::Feedback>();
    feedback->current_joint_id = static_cast<int32_t>(idx);
    feedback->progress_percent =
      static_cast<float>(completed * 100.0 / total_joints);
    feedback->status_message = "Homing " + jname + ": moving to zero";
    goal_handle->publish_feedback(feedback);

    // Get homing position
    const double homing_pos = motor_manager_.getHomingPosition(idx);

    const double pos_tol =
      (idx < motion_feedback_position_tolerance_by_motor_.size())
        ? motion_feedback_position_tolerance_by_motor_[idx]
        : motion_feedback_position_tolerance_;

    // Step 1: Move to motor's built-in zero
    if (!motor->set_position(0.0, 0.0, 0.0)) {
      RCLCPP_ERROR(node_->get_logger(),
        "JointHoming: failed to send zero command for %s", jname.c_str());
      result->reason = "Failed to command zero for " + jname;
      callbacks_.set_watchdog_exempt(false);
      cleanup();
      goal_handle->abort(result);
      return;
    }

    // Wait for motor to reach zero (cancel-aware: 40 × 50ms = 2s)
    for (int w = 0; w < 40; ++w) {
      if (goal_handle->is_canceling() || shutdown_requested_.load()) break;
      // BLOCKING_SLEEP_OK: dedicated homing thread, 50ms cancel-aware poll — reviewed 2026-03-14
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    if (goal_handle->is_canceling()) continue;  // Caught at loop top

    // Update feedback: verifying
    feedback->status_message = "Homing " + jname + ": verifying zero";
    feedback->progress_percent =
      static_cast<float>((completed + 0.4) * 100.0 / total_joints);
    goal_handle->publish_feedback(feedback);

    double verify_pos = motor->get_position();
    // BLOCKING_SLEEP_OK: dedicated homing thread, 200ms position verify settle — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    // Step 3: Move to final homing position if needed
    const double homing_err = verify_pos - homing_pos;
    if (std::abs(homing_err) > pos_tol) {
      feedback->status_message =
        "Homing " + jname + ": moving to homing position";
      feedback->progress_percent =
        static_cast<float>((completed + 0.6) * 100.0 / total_joints);
      goal_handle->publish_feedback(feedback);

      if (!motor->set_position(homing_pos, 0.0, 0.0)) {
        RCLCPP_ERROR(node_->get_logger(),
          "JointHoming: failed to move to homing pos for %s", jname.c_str());
        result->reason = "Failed to command homing position for " + jname;
        callbacks_.set_watchdog_exempt(false);
        cleanup();
        goal_handle->abort(result);
        return;
      }

      // Wait for motor to reach homing position (cancel-aware: 60 × 50ms = 3s)
      for (int w = 0; w < 60; ++w) {
        if (goal_handle->is_canceling() || shutdown_requested_.load()) break;
        // BLOCKING_SLEEP_OK: dedicated homing thread, 50ms cancel-aware poll — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
    }

    completed++;
    RCLCPP_INFO(node_->get_logger(), "JointHoming: %s homed (%zu/%zu)",
      jname.c_str(), completed, total_joints);
  }

  callbacks_.set_watchdog_exempt(false);

  // Collect final positions
  result->final_positions.clear();
  for (const auto & idx : joints_to_home) {
    auto m = motor_manager_.getMotor(idx);
    result->final_positions.push_back(m ? m->get_position() : 0.0);
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

  RCLCPP_INFO(node_->get_logger(),
    "JointHoming: COMPLETE (%zu joints homed)", total_joints);
}

}  // namespace motor_control_ros2
