/*
 * RosInterfaceManager — ROS2 service/action/subscriber/publisher wiring
 *
 * Pure infrastructure class that creates all ROS2 interfaces for the motor
 * controller node and routes callbacks to the appropriate handler class:
 *   - MotorTestSuite (read-only diagnostics + motor availability)
 *   - ControlLoopManager (PID write + command processing)
 *   - Parent node via std::function callbacks (enable, disable, reset, etc.)
 *
 * Part of the mg6010-decomposition refactoring.
 */

#pragma once

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <std_srvs/srv/set_bool.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>

#include "motor_control_ros2/motor_controller_interface.hpp"
#include "motor_control_ros2/can_interface.hpp"

#include "motor_control_msgs/srv/joint_position_command.hpp"
#include "motor_control_msgs/srv/motor_command.hpp"
#include "motor_control_msgs/srv/motor_lifecycle.hpp"
#include "motor_control_msgs/srv/write_motor_limits.hpp"
#include "motor_control_msgs/srv/write_encoder_zero.hpp"
#include "motor_control_msgs/srv/read_motor_state.hpp"
#include "motor_control_msgs/srv/read_encoder.hpp"
#include "motor_control_msgs/srv/read_motor_angles.hpp"
#include "motor_control_msgs/srv/read_motor_limits.hpp"
#include "motor_control_msgs/srv/clear_motor_errors.hpp"
#include "motor_control_msgs/srv/read_pid.hpp"
#include "motor_control_msgs/srv/write_pid.hpp"
#include "motor_control_msgs/srv/write_pid_to_rom.hpp"

#include "motor_control_msgs/action/step_response_test.hpp"
#include "motor_control_msgs/action/joint_position_command.hpp"
#include "motor_control_msgs/action/joint_homing.hpp"

#include <array>
#include <atomic>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace motor_control_ros2 {

#ifndef MOTOR_CONTROL_ROS2_MAX_MOTORS_DEFINED
#define MOTOR_CONTROL_ROS2_MAX_MOTORS_DEFINED
constexpr size_t MAX_MOTORS = 6;
#endif

// Forward declarations
class MotorTestSuite;
class ControlLoopManager;

// Action type aliases
using StepResponseTest = motor_control_msgs::action::StepResponseTest;
using JointPosCmd = motor_control_msgs::action::JointPositionCommand;
using JointHomingAction = motor_control_msgs::action::JointHoming;
using GoalHandleStepResponse = rclcpp_action::ServerGoalHandle<StepResponseTest>;
using GoalHandleJointPosCmd = rclcpp_action::ServerGoalHandle<JointPosCmd>;
using GoalHandleJointHoming = rclcpp_action::ServerGoalHandle<JointHomingAction>;

/**
 * Struct of std::function callbacks for services/actions still handled
 * by the parent MG6010ControllerNode (not yet extracted to a handler class).
 */
struct NodeCallbacks
{
  // Service callbacks (8 services handled by the parent node)
  std::function<void(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response>)> enable_callback;

  std::function<void(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response>)> disable_callback;

  std::function<void(
    const std::shared_ptr<std_srvs::srv::SetBool::Request>,
    std::shared_ptr<std_srvs::srv::SetBool::Response>)> reset_motor_callback;

  std::function<void(
    const std::shared_ptr<motor_control_msgs::srv::JointPositionCommand::Request>,
    std::shared_ptr<motor_control_msgs::srv::JointPositionCommand::Response>)>
    joint_position_command_callback;

  std::function<void(
    const std::shared_ptr<motor_control_msgs::srv::MotorCommand::Request>,
    std::shared_ptr<motor_control_msgs::srv::MotorCommand::Response>)>
    motor_command_callback;

  std::function<void(
    const std::shared_ptr<motor_control_msgs::srv::MotorLifecycle::Request>,
    std::shared_ptr<motor_control_msgs::srv::MotorLifecycle::Response>)>
    motor_lifecycle_callback;

  std::function<void(
    const std::shared_ptr<motor_control_msgs::srv::WriteMotorLimits::Request>,
    std::shared_ptr<motor_control_msgs::srv::WriteMotorLimits::Response>)>
    write_motor_limits_callback;

  std::function<void(
    const std::shared_ptr<motor_control_msgs::srv::WriteEncoderZero::Request>,
    std::shared_ptr<motor_control_msgs::srv::WriteEncoderZero::Response>)>
    write_encoder_zero_callback;

  // Action server callbacks — StepResponseTest
  std::function<rclcpp_action::GoalResponse(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const StepResponseTest::Goal>)>
    step_response_goal_callback;

  std::function<rclcpp_action::CancelResponse(
    std::shared_ptr<GoalHandleStepResponse>)>
    step_response_cancel_callback;

  std::function<void(
    std::shared_ptr<GoalHandleStepResponse>)>
    step_response_accepted_callback;

  // Action server callbacks — JointPositionCommand
  std::function<rclcpp_action::GoalResponse(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const JointPosCmd::Goal>)>
    joint_pos_cmd_goal_callback;

  std::function<rclcpp_action::CancelResponse(
    std::shared_ptr<GoalHandleJointPosCmd>)>
    joint_pos_cmd_cancel_callback;

  std::function<void(
    std::shared_ptr<GoalHandleJointPosCmd>)>
    joint_pos_cmd_accepted_callback;

  // Action server callbacks — JointHoming
  std::function<rclcpp_action::GoalResponse(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const JointHomingAction::Goal>)>
    joint_homing_goal_callback;

  std::function<rclcpp_action::CancelResponse(
    std::shared_ptr<GoalHandleJointHoming>)>
    joint_homing_cancel_callback;

  std::function<void(
    std::shared_ptr<GoalHandleJointHoming>)>
    joint_homing_accepted_callback;
};

/**
 * RosInterfaceManager — creates and owns all ROS2 interface objects
 * (services, action servers, subscribers, publishers) and routes incoming
 * requests to the appropriate handler class.
 */
class RosInterfaceManager
{
public:
  /**
   * Construct RosInterfaceManager and create all ROS2 interfaces.
   *
   * @param node            Shared pointer to the ROS2 node (non-null)
   * @param test_suite      Pointer to MotorTestSuite for diagnostic routing
   * @param control_loop    Pointer to ControlLoopManager for PID/command routing
   * @param node_callbacks  Callbacks for services still handled by parent node
   * @param controllers     Reference to motor controller vector
   * @param motor_available Reference to motor availability flags
   * @param joint_names     Reference to joint name vector
   * @param safety_group    MutuallyExclusive group for safety callbacks
   * @param hardware_group  MutuallyExclusive group for service/control callbacks
   * @param processing_group Reentrant group for action servers/diagnostics
   *
   * @throws std::invalid_argument if node is null
   */
  RosInterfaceManager(
    std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
    MotorTestSuite * test_suite,
    ControlLoopManager * control_loop,
    const NodeCallbacks & node_callbacks,
    std::vector<std::shared_ptr<MotorControllerInterface>> & controllers,
    std::array<std::atomic<bool>, MAX_MOTORS> & motor_available,
    std::vector<std::string> & joint_names,
    rclcpp::CallbackGroup::SharedPtr safety_group,
    rclcpp::CallbackGroup::SharedPtr hardware_group,
    rclcpp::CallbackGroup::SharedPtr processing_group);

  ~RosInterfaceManager() = default;

  // Non-copyable, non-movable (owns ROS2 shared_ptrs)
  RosInterfaceManager(const RosInterfaceManager &) = delete;
  RosInterfaceManager & operator=(const RosInterfaceManager &) = delete;

  /// Access publishers (needed by the parent node's control_loop)
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr
  joint_state_publisher() const { return joint_state_pub_; }

  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr
  motor_diagnostics_publisher() const { return motor_diagnostics_pub_; }

  /// Access callback groups (needed by the parent node for timer assignment)
  rclcpp::CallbackGroup::SharedPtr safety_callback_group() const
  { return safety_cb_group_; }

  rclcpp::CallbackGroup::SharedPtr hardware_callback_group() const
  { return hardware_cb_group_; }

  rclcpp::CallbackGroup::SharedPtr processing_callback_group() const
  { return processing_cb_group_; }

private:
  // Node reference
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node_;

  // Callback groups (Phase 3 Step 8)
  rclcpp::CallbackGroup::SharedPtr safety_cb_group_;     // MutuallyExclusive: watchdog, e-stop, interlock
  rclcpp::CallbackGroup::SharedPtr hardware_cb_group_;   // MutuallyExclusive: services, control loop, command subs
  rclcpp::CallbackGroup::SharedPtr processing_cb_group_; // Reentrant: action servers, diagnostics, stats

  // Handler references (non-owning)
  MotorTestSuite * test_suite_;
  ControlLoopManager * control_loop_;
  NodeCallbacks node_callbacks_;

  // Data references (non-owning)
  std::vector<std::shared_ptr<MotorControllerInterface>> & controllers_;
  std::array<std::atomic<bool>, MAX_MOTORS> & motor_available_;
  std::vector<std::string> & joint_names_;

  // Service servers (17)
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr enable_srv_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr disable_srv_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr motor_availability_srv_;
  rclcpp::Service<std_srvs::srv::SetBool>::SharedPtr reset_motor_srv_;
  rclcpp::Service<motor_control_msgs::srv::JointPositionCommand>::SharedPtr
    joint_position_command_srv_;
  rclcpp::Service<motor_control_msgs::srv::ReadPID>::SharedPtr read_pid_service_;
  rclcpp::Service<motor_control_msgs::srv::WritePID>::SharedPtr write_pid_service_;
  rclcpp::Service<motor_control_msgs::srv::WritePIDToROM>::SharedPtr
    write_pid_to_rom_service_;
  rclcpp::Service<motor_control_msgs::srv::MotorCommand>::SharedPtr
    motor_command_service_;
  rclcpp::Service<motor_control_msgs::srv::MotorLifecycle>::SharedPtr
    motor_lifecycle_service_;
  rclcpp::Service<motor_control_msgs::srv::ReadMotorLimits>::SharedPtr
    read_motor_limits_service_;
  rclcpp::Service<motor_control_msgs::srv::WriteMotorLimits>::SharedPtr
    write_motor_limits_service_;
  rclcpp::Service<motor_control_msgs::srv::ReadEncoder>::SharedPtr
    read_encoder_service_;
  rclcpp::Service<motor_control_msgs::srv::WriteEncoderZero>::SharedPtr
    write_encoder_zero_service_;
  rclcpp::Service<motor_control_msgs::srv::ReadMotorAngles>::SharedPtr
    read_motor_angles_service_;
  rclcpp::Service<motor_control_msgs::srv::ClearMotorErrors>::SharedPtr
    clear_motor_errors_service_;
  rclcpp::Service<motor_control_msgs::srv::ReadMotorState>::SharedPtr
    read_motor_state_service_;

  // Action servers (3)
  rclcpp_action::Server<StepResponseTest>::SharedPtr
    step_response_action_server_;
  rclcpp_action::Server<JointPosCmd>::SharedPtr
    joint_pos_cmd_action_server_;
  rclcpp_action::Server<JointHomingAction>::SharedPtr
    joint_homing_action_server_;

  // Subscribers (3 groups, dynamic per motor)
  std::vector<rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr>
    position_cmd_subs_;
  std::vector<rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr>
    velocity_cmd_subs_;
  std::vector<rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr>
    stop_cmd_subs_;

  // Publishers (2)
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr
    motor_diagnostics_pub_;

  // Private setup helpers
  void create_services();
  void create_action_servers();
  void create_position_command_subscribers();
  void create_velocity_command_subscribers();
  void create_stop_command_subscribers();
  void create_publishers();
};

}  // namespace motor_control_ros2
