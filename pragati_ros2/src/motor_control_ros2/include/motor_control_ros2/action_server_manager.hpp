/*
 * Copyright (c) 2026 Pragati Robotics
 *
 * ActionServerManager — owns the three ROS2 action servers
 * (StepResponseTest, JointPositionCommand, JointHoming) and all
 * motion-tracking state extracted from MG6010ControllerNode.
 *
 * Communicates with the parent node exclusively through std::function
 * callbacks (design decision D2) — no back-pointer to the god-class.
 *
 * Part of mg6010-decomposition Phase 2 (Step 5).
 */

#ifndef MOTOR_CONTROL_ROS2_ACTION_SERVER_MANAGER_HPP_
#define MOTOR_CONTROL_ROS2_ACTION_SERVER_MANAGER_HPP_

#include <atomic>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include "motor_control_msgs/action/step_response_test.hpp"
#include "motor_control_msgs/action/joint_position_command.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"

#include "motor_control_ros2/motor_manager.hpp"

namespace motor_control_ros2
{

// ── Action type aliases ──────────────────────────────────────────────────

using StepResponseTest = motor_control_msgs::action::StepResponseTest;
using GoalHandleStepResponse = rclcpp_action::ServerGoalHandle<StepResponseTest>;

using JointPosCmd = motor_control_msgs::action::JointPositionCommand;
using GoalHandleJointPosCmd = rclcpp_action::ServerGoalHandle<JointPosCmd>;

using JointHomingAction = motor_control_msgs::action::JointHoming;
using GoalHandleJointHoming = rclcpp_action::ServerGoalHandle<JointHomingAction>;

// ── Callbacks struct (design decision D2) ────────────────────────────────

/**
 * @brief Callbacks for parent-node interactions.
 *
 * ActionServerManager never holds a pointer to the parent node. All
 * cross-boundary communication is through these std::function members.
 */
struct ActionCallbacks
{
  /**
   * @brief Called when a CAN command to a motor fails.
   * @param motor_idx   Motor index (0-based).
   * @param cmd_type    Command type string (e.g. "set_position").
   * @param target_value The commanded value that failed.
   * @param error_reason Human-readable error description.
   * @param func_name   Calling function name (__func__).
   */
  std::function<void(size_t motor_idx,
                     const std::string & cmd_type,
                     double target_value,
                     const std::string & error_reason,
                     const char * func_name)> handle_motor_failure;

  /**
   * @brief J3/J4 interlock check before commanding motion.
   * @param motor_idx   Motor index being commanded.
   * @param requested_position  Target position (radians).
   * @param source      Calling context description.
   * @return true if the motion is BLOCKED (must not proceed).
   */
  std::function<bool(size_t motor_idx,
                     double requested_position,
                     const char * source)> check_j3j4_interlock;

  /**
   * @brief Set/clear watchdog exemption during homing.
   * @param exempt  true to exempt (disable watchdog), false to restore.
   */
  std::function<void(bool exempt)> set_watchdog_exempt;
};

// ── ActionServerManager ──────────────────────────────────────────────────

/**
 * @brief Manages the three motor-control action servers and all motion
 *        tracking state.
 *
 * Owns:
 *   - StepResponseTest action server + execution thread
 *   - JointPositionCommand action server + execution thread
 *   - JointHoming action server + execution thread
 *   - Motion tracking arrays: busy flags, pending flags, target positions,
 *     tolerances, command counters, feedback snapshots
 *   - Motion feedback timer
 *
 * Thread model: each action spawns a detached-style std::thread (joined on
 * destruction). Mutexes protect per-action state and shared motion arrays.
 *
 * This is a plain C++ class — not a ROS2 node. It takes a shared_ptr<Node>
 * for creating action servers, timers, and logging.
 */
class ActionServerManager
{
public:
  /**
   * @brief Construct ActionServerManager and register all action servers.
   *
   * @param node           Shared pointer to ROS2 node (for action servers, timers, logging).
   *                       Must not be null.
   * @param motor_manager  Reference to MotorManager for motor access.
   * @param callbacks      Callbacks for parent-node interactions.
   *                       All three function members must be non-empty.
   *
   * @throws std::invalid_argument if node is null or any callback is empty.
   */
  ActionServerManager(
    std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
    MotorManager & motor_manager,
    ActionCallbacks callbacks);

  /**
   * @brief Destructor — signals shutdown and joins all execution threads.
   *
   * Sets shutdown_requested_ and waits for any running action threads to
   * complete before destruction.
   */
  ~ActionServerManager();

  // Non-copyable, non-movable (owns mutexes, threads, atomics)
  ActionServerManager(const ActionServerManager &) = delete;
  ActionServerManager & operator=(const ActionServerManager &) = delete;
  ActionServerManager(ActionServerManager &&) = delete;
  ActionServerManager & operator=(ActionServerManager &&) = delete;

private:
  // ── StepResponseTest handlers ──────────────────────────────────────

  rclcpp_action::GoalResponse handleStepResponseGoal(
    const rclcpp_action::GoalUUID & uuid,
    std::shared_ptr<const StepResponseTest::Goal> goal);

  rclcpp_action::CancelResponse handleStepResponseCancel(
    std::shared_ptr<GoalHandleStepResponse> goal_handle);

  void handleStepResponseAccepted(
    std::shared_ptr<GoalHandleStepResponse> goal_handle);

  void executeStepResponseTest(
    std::shared_ptr<GoalHandleStepResponse> goal_handle);

  // ── JointPositionCommand handlers ──────────────────────────────────

  rclcpp_action::GoalResponse handleJointPosCmdGoal(
    const rclcpp_action::GoalUUID & uuid,
    std::shared_ptr<const JointPosCmd::Goal> goal);

  rclcpp_action::CancelResponse handleJointPosCmdCancel(
    std::shared_ptr<GoalHandleJointPosCmd> goal_handle);

  void handleJointPosCmdAccepted(
    std::shared_ptr<GoalHandleJointPosCmd> goal_handle);

  void executeJointPositionCommand(
    std::shared_ptr<GoalHandleJointPosCmd> goal_handle);

  // ── JointHoming handlers ───────────────────────────────────────────

  rclcpp_action::GoalResponse handleJointHomingGoal(
    const rclcpp_action::GoalUUID & uuid,
    std::shared_ptr<const JointHomingAction::Goal> goal);

  rclcpp_action::CancelResponse handleJointHomingCancel(
    std::shared_ptr<GoalHandleJointHoming> goal_handle);

  void handleJointHomingAccepted(
    std::shared_ptr<GoalHandleJointHoming> goal_handle);

  void executeJointHoming(
    std::shared_ptr<GoalHandleJointHoming> goal_handle);

  // ── Core references ────────────────────────────────────────────────

  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;
  MotorManager & motor_manager_;
  ActionCallbacks callbacks_;

  // ── Shutdown coordination ──────────────────────────────────────────

  std::atomic<bool> shutdown_requested_{false};

  // ── Action servers ─────────────────────────────────────────────────

  rclcpp_action::Server<StepResponseTest>::SharedPtr step_response_server_;
  rclcpp_action::Server<JointPosCmd>::SharedPtr joint_pos_cmd_server_;
  rclcpp_action::Server<JointHomingAction>::SharedPtr joint_homing_server_;

  // ── StepResponseTest thread/mutex/flag ─────────────────────────────

  std::mutex step_test_mutex_;
  bool step_test_running_{false};
  std::thread step_test_thread_;

  // ── JointPositionCommand thread/mutex/flag ─────────────────────────

  std::mutex joint_pos_cmd_mutex_;
  std::vector<bool> joint_pos_cmd_active_;   // per-joint active flag
  std::unordered_map<size_t, std::thread> joint_pos_cmd_threads_;  // per-joint threads

  // ── JointHoming thread/mutex/flag ──────────────────────────────────

  std::mutex joint_homing_mutex_;
  bool joint_homing_active_{false};
  std::thread joint_homing_thread_;

  // ── Smart polling state ────────────────────────────────────────────

  bool smart_polling_enabled_{true};
  std::chrono::steady_clock::duration motor_busy_timeout_{std::chrono::seconds(5)};
  std::vector<bool> motor_busy_flags_;  // guarded by motion_mutex_
  std::vector<std::chrono::steady_clock::time_point> motor_command_times_;
  std::vector<double> last_commanded_positions_;

  // ── Motion feedback config ─────────────────────────────────────────

  bool motion_feedback_enabled_{true};
  double motion_feedback_poll_hz_{5.0};
  bool motion_feedback_publish_actual_while_busy_{true};
  double motion_feedback_position_tolerance_{0.01};
  std::vector<double> motion_feedback_position_tolerance_by_motor_;
  mutable std::mutex motion_mutex_;
  std::chrono::steady_clock::duration motion_feedback_settle_time_{
    std::chrono::milliseconds(200)};
  std::chrono::steady_clock::duration motion_feedback_timeout_{
    std::chrono::seconds(5)};
  rclcpp::TimerBase::SharedPtr motion_feedback_timer_;

  // ── Motion state arrays ────────────────────────────────────────────

  std::vector<bool> motion_pending_;
  std::vector<double> motion_target_positions_;
  std::vector<std::chrono::steady_clock::time_point> motion_start_times_;
  std::vector<bool> motion_in_tolerance_;
  std::vector<std::chrono::steady_clock::time_point> motion_in_tolerance_since_;

  // ── Last feedback snapshots ────────────────────────────────────────

  std::vector<bool> last_feedback_valid_;
  std::vector<double> last_feedback_position_;
  std::vector<std::chrono::steady_clock::time_point> last_feedback_time_;

  // ── Command counters ───────────────────────────────────────────────

  std::vector<uint64_t> pos_cmd_received_;
  std::vector<uint64_t> pos_cmd_sent_ok_;
  std::vector<uint64_t> pos_cmd_sent_fail_;
  std::vector<uint64_t> pos_cmd_reached_ok_;
  std::vector<uint64_t> pos_cmd_reached_timeout_;
  uint64_t total_position_commands_{0};
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2_ACTION_SERVER_MANAGER_HPP_
