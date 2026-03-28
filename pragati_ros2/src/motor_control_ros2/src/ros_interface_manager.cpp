/*
 * RosInterfaceManager implementation
 *
 * Creates all ROS2 interfaces (services, action servers, subscribers,
 * publishers) and routes callbacks to the appropriate handler class.
 */

#include "motor_control_ros2/ros_interface_manager.hpp"
#include "motor_control_ros2/motor_test_suite.hpp"
#include "motor_control_ros2/control_loop_manager.hpp"

#include <stdexcept>

namespace motor_control_ros2 {

RosInterfaceManager::RosInterfaceManager(
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node,
  MotorTestSuite * test_suite,
  ControlLoopManager * control_loop,
  const NodeCallbacks & node_callbacks,
  std::vector<std::shared_ptr<MotorControllerInterface>> & controllers,
  std::array<std::atomic<bool>, MAX_MOTORS> & motor_available,
  std::vector<std::string> & joint_names,
  rclcpp::CallbackGroup::SharedPtr safety_group,
  rclcpp::CallbackGroup::SharedPtr hardware_group,
  rclcpp::CallbackGroup::SharedPtr processing_group)
: node_(node),
  test_suite_(test_suite),
  control_loop_(control_loop),
  node_callbacks_(node_callbacks),
  controllers_(controllers),
  motor_available_(motor_available),
  joint_names_(joint_names),
  safety_cb_group_(safety_group),
  hardware_cb_group_(hardware_group),
  processing_cb_group_(processing_group)
{
  if (!node_) {
    throw std::invalid_argument("RosInterfaceManager: node pointer must not be null");
  }

  create_publishers();
  create_services();
  create_action_servers();
  create_position_command_subscribers();
  create_velocity_command_subscribers();
  create_stop_command_subscribers();

  RCLCPP_INFO(node_->get_logger(),
    "RosInterfaceManager: created 17 services, 3 action servers, "
    "%zu×3 subscribers, 2 publishers (3 callback groups: safety/hardware/processing)",
    controllers_.size());
}

void RosInterfaceManager::create_publishers()
{
  joint_state_pub_ = node_->create_publisher<sensor_msgs::msg::JointState>(
    "joint_states", 10);

  motor_diagnostics_pub_ =
    node_->create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
      "~/motor_diagnostics", 10);
}

void RosInterfaceManager::create_services()
{
  using namespace std::placeholders;

  // All services assigned to hardware_cb_group_ (Phase 3 Step 8)

  // --- Node-handled services (8) ---

  enable_srv_ = node_->create_service<std_srvs::srv::Trigger>(
    "enable_motors", node_callbacks_.enable_callback,
    rclcpp::ServicesQoS(), hardware_cb_group_);

  disable_srv_ = node_->create_service<std_srvs::srv::Trigger>(
    "disable_motors", node_callbacks_.disable_callback,
    rclcpp::ServicesQoS(), hardware_cb_group_);

  reset_motor_srv_ = node_->create_service<std_srvs::srv::SetBool>(
    "reset_motor", node_callbacks_.reset_motor_callback,
    rclcpp::ServicesQoS(), hardware_cb_group_);

  joint_position_command_srv_ =
    node_->create_service<motor_control_msgs::srv::JointPositionCommand>(
      "joint_position_command",
      node_callbacks_.joint_position_command_callback,
      rclcpp::ServicesQoS(), hardware_cb_group_);

  motor_command_service_ =
    node_->create_service<motor_control_msgs::srv::MotorCommand>(
      "~/motor_command", node_callbacks_.motor_command_callback,
      rclcpp::ServicesQoS(), hardware_cb_group_);

  motor_lifecycle_service_ =
    node_->create_service<motor_control_msgs::srv::MotorLifecycle>(
      "~/motor_lifecycle", node_callbacks_.motor_lifecycle_callback,
      rclcpp::ServicesQoS(), hardware_cb_group_);

  write_motor_limits_service_ =
    node_->create_service<motor_control_msgs::srv::WriteMotorLimits>(
      "~/write_motor_limits", node_callbacks_.write_motor_limits_callback,
      rclcpp::ServicesQoS(), hardware_cb_group_);

  write_encoder_zero_service_ =
    node_->create_service<motor_control_msgs::srv::WriteEncoderZero>(
      "~/write_encoder_zero", node_callbacks_.write_encoder_zero_callback,
      rclcpp::ServicesQoS(), hardware_cb_group_);

  // --- MotorTestSuite-handled services (7) ---

  motor_availability_srv_ = node_->create_service<std_srvs::srv::Trigger>(
    "get_motor_availability",
    std::bind(&MotorTestSuite::motor_availability_callback, test_suite_, _1, _2),
    rclcpp::ServicesQoS(), hardware_cb_group_);

  read_pid_service_ = node_->create_service<motor_control_msgs::srv::ReadPID>(
    "~/read_pid",
    std::bind(&MotorTestSuite::readPidCallback, test_suite_, _1, _2),
    rclcpp::ServicesQoS(), hardware_cb_group_);

  read_motor_limits_service_ =
    node_->create_service<motor_control_msgs::srv::ReadMotorLimits>(
      "~/read_motor_limits",
      std::bind(&MotorTestSuite::readMotorLimitsCallback, test_suite_, _1, _2),
      rclcpp::ServicesQoS(), hardware_cb_group_);

  read_encoder_service_ =
    node_->create_service<motor_control_msgs::srv::ReadEncoder>(
      "~/read_encoder",
      std::bind(&MotorTestSuite::readEncoderCallback, test_suite_, _1, _2),
      rclcpp::ServicesQoS(), hardware_cb_group_);

  read_motor_angles_service_ =
    node_->create_service<motor_control_msgs::srv::ReadMotorAngles>(
      "~/read_motor_angles",
      std::bind(&MotorTestSuite::readMotorAnglesCallback, test_suite_, _1, _2),
      rclcpp::ServicesQoS(), hardware_cb_group_);

  clear_motor_errors_service_ =
    node_->create_service<motor_control_msgs::srv::ClearMotorErrors>(
      "~/clear_motor_errors",
      std::bind(&MotorTestSuite::clearMotorErrorsCallback, test_suite_, _1, _2),
      rclcpp::ServicesQoS(), hardware_cb_group_);

  read_motor_state_service_ =
    node_->create_service<motor_control_msgs::srv::ReadMotorState>(
      "~/read_motor_state",
      std::bind(&MotorTestSuite::readMotorStateCallback, test_suite_, _1, _2),
      rclcpp::ServicesQoS(), hardware_cb_group_);

  // --- ControlLoopManager-handled services (2) ---

  write_pid_service_ = node_->create_service<motor_control_msgs::srv::WritePID>(
    "~/write_pid",
    std::bind(&ControlLoopManager::writePidCallback, control_loop_, _1, _2),
    rclcpp::ServicesQoS(), hardware_cb_group_);

  write_pid_to_rom_service_ =
    node_->create_service<motor_control_msgs::srv::WritePIDToROM>(
      "~/write_pid_to_rom",
      std::bind(&ControlLoopManager::writePidToRomCallback, control_loop_, _1, _2),
      rclcpp::ServicesQoS(), hardware_cb_group_);
}

void RosInterfaceManager::create_action_servers()
{
  using namespace std::placeholders;

  // All action servers assigned to processing_cb_group_ (Phase 3 Step 8)

  step_response_action_server_ =
    rclcpp_action::create_server<StepResponseTest>(
      node_, "~/step_response_test",
      node_callbacks_.step_response_goal_callback,
      node_callbacks_.step_response_cancel_callback,
      node_callbacks_.step_response_accepted_callback,
      rcl_action_server_get_default_options(),
      processing_cb_group_);

  joint_pos_cmd_action_server_ =
    rclcpp_action::create_server<JointPosCmd>(
      node_, "/joint_position_command",
      node_callbacks_.joint_pos_cmd_goal_callback,
      node_callbacks_.joint_pos_cmd_cancel_callback,
      node_callbacks_.joint_pos_cmd_accepted_callback,
      rcl_action_server_get_default_options(),
      processing_cb_group_);

  joint_homing_action_server_ =
    rclcpp_action::create_server<JointHomingAction>(
      node_, "/joint_homing",
      node_callbacks_.joint_homing_goal_callback,
      node_callbacks_.joint_homing_cancel_callback,
      node_callbacks_.joint_homing_accepted_callback,
      rcl_action_server_get_default_options(),
      processing_cb_group_);
}

void RosInterfaceManager::create_position_command_subscribers()
{
  auto qos = rclcpp::QoS(10);
  qos.durability(rclcpp::DurabilityPolicy::Volatile);

  rclcpp::SubscriptionOptions sub_opts;
  sub_opts.callback_group = hardware_cb_group_;

  for (size_t i = 0; i < controllers_.size(); ++i) {
    std::string topic = "/" + joint_names_[i] + "_position_controller/command";
    auto sub = node_->create_subscription<std_msgs::msg::Float64>(
      topic, qos,
      [this, i](const std_msgs::msg::Float64::SharedPtr msg) {
        control_loop_->position_command_callback(i, msg->data);
      },
      sub_opts);
    position_cmd_subs_.push_back(sub);
  }
}

void RosInterfaceManager::create_velocity_command_subscribers()
{
  auto qos = rclcpp::QoS(10);
  qos.durability(rclcpp::DurabilityPolicy::Volatile);

  rclcpp::SubscriptionOptions sub_opts;
  sub_opts.callback_group = hardware_cb_group_;

  for (size_t i = 0; i < controllers_.size(); ++i) {
    std::string topic = "/" + joint_names_[i] + "_velocity_controller/command";
    auto sub = node_->create_subscription<std_msgs::msg::Float64>(
      topic, qos,
      [this, i](const std_msgs::msg::Float64::SharedPtr msg) {
        control_loop_->velocity_command_callback(i, msg->data);
      },
      sub_opts);
    velocity_cmd_subs_.push_back(sub);
  }
}

void RosInterfaceManager::create_stop_command_subscribers()
{
  auto qos = rclcpp::QoS(10);
  qos.durability(rclcpp::DurabilityPolicy::Volatile);

  rclcpp::SubscriptionOptions sub_opts;
  sub_opts.callback_group = hardware_cb_group_;

  for (size_t i = 0; i < controllers_.size(); ++i) {
    std::string topic = "/" + joint_names_[i] + "_stop_controller/command";
    auto sub = node_->create_subscription<std_msgs::msg::Float64>(
      topic, qos,
      [this, i](const std_msgs::msg::Float64::SharedPtr msg) {
        if (msg->data > 0.5) {
          control_loop_->stop_command_callback(i);
        }
      },
      sub_opts);
    stop_cmd_subs_.push_back(sub);
  }
}

}  // namespace motor_control_ros2
