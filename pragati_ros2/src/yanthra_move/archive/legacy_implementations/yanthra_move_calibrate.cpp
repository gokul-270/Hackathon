// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http:  // www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.



#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float64.hpp>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/buffer.h>
#include <vector>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <std_msgs/msg/bool.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <trajectory_msgs/msg/joint_trajectory_point.hpp>
#include <iostream>
#include <fstream>
#include <time.h>
#include <chrono>
#include <thread>
#include "cotton_detection_ros2/srv/cotton_detection.hpp"
#include "motor_control_msgs/srv/joint_homing.hpp"
// #include <yanthra_move/yanthra_move_calibrate.h>
#include <yanthra_move/yanthra_move.h>
#include <yanthra_move/joint_move.h>
#include <yanthra_move/yanthra_io.h>
bool height_scan_enable;
double height_scan_min;
double height_scan_max;
double height_scan_step;
bool Global_vaccum_motor;
double joint5_vel_limit;
float l2_homing_sleep_time;
float l2_step_sleep_time;
bool jerk_enabled_phi;
bool jerk_enabled_theta;
float theta_jerk_value;
float phi_jerk_value;

namespace {

constexpr std::chrono::seconds kServiceWaitTimeout(5);
constexpr std::chrono::seconds kDetectionWaitTimeout(20);
constexpr std::chrono::seconds kHomingWaitTimeout(30);

bool ensure_cotton_detection_service(
  const rclcpp::Node::SharedPtr & node,
  const rclcpp::Client<cotton_detection_ros2::srv::CottonDetection>::SharedPtr & client)
{
  if (client->service_is_ready()) {
    return true;
  }

  RCLCPP_INFO(node->get_logger(), "Waiting for /cotton_detection/detect service...");
  if (!client->wait_for_service(kServiceWaitTimeout)) {
    RCLCPP_ERROR(node->get_logger(),
      "Cotton detection service /cotton_detection/detect is unavailable");
    return false;
  }

  return true;
}

bool ensure_motor_homing_service(
  const rclcpp::Node::SharedPtr & node,
  const rclcpp::Client<motor_control_msgs::srv::JointHoming>::SharedPtr & client)
{
  if (client->service_is_ready()) {
    return true;
  }

  RCLCPP_INFO(node->get_logger(), "Waiting for motor homing service...");
  if (!client->wait_for_service(kServiceWaitTimeout)) {
    RCLCPP_ERROR(node->get_logger(),
      "Motor homing service is unavailable. Is the motor control node running?");
    return false;
  }

  return true;
}

bool ensure_motor_idle_service(
  const rclcpp::Node::SharedPtr & node,
  const rclcpp::Client<motor_control_msgs::srv::JointHoming>::SharedPtr & client)
{
  if (client->service_is_ready()) {
    return true;
  }

  RCLCPP_INFO(node->get_logger(), "Waiting for motor idle service...");
  if (!client->wait_for_service(kServiceWaitTimeout)) {
    RCLCPP_ERROR(node->get_logger(),
      "Motor idle service is unavailable. Is the motor control node running?");
    return false;
  }

  return true;
}

void decode_detection_points(
  const std::vector<int32_t> & data,
  std::vector<geometry_msgs::msg::Point> * positions,
  const rclcpp::Logger & logger)
{
  if (!positions) {
    return;
  }

  positions->clear();
  if (data.empty()) {
    return;
  }

  if (data.size() % 3 != 0) {
    RCLCPP_WARN(logger,
      "Detection result length %zu is not a multiple of 3; ignoring trailing data",
      data.size());
  }

  const size_t triplet_count = data.size() / 3;
  positions->reserve(triplet_count);
  for (size_t i = 0; i < triplet_count; ++i) {
    geometry_msgs::msg::Point point;
    point.x = static_cast<double>(data[i * 3]) * 0.001;
    point.y = static_cast<double>(data[i * 3 + 1]) * 0.001;
    point.z = static_cast<double>(data[i * 3 + 2]) * 0.001;
    positions->push_back(point);
  }
}

bool invoke_cotton_detection(
  const rclcpp::Node::SharedPtr & node,
  const rclcpp::Client<cotton_detection_ros2::srv::CottonDetection>::SharedPtr & client,
  std::vector<geometry_msgs::msg::Point> * positions)
{
  if (!ensure_cotton_detection_service(node, client)) {
    if (positions) {
      positions->clear();
    }
    return false;
  }

  auto request = std::make_shared<cotton_detection_ros2::srv::CottonDetection::Request>();
  request->detect_command = 1;

  auto future = client->async_send_request(request);
  auto status = rclcpp::spin_until_future_complete(node, future, kDetectionWaitTimeout);
  if (status != rclcpp::FutureReturnCode::SUCCESS) {
    RCLCPP_ERROR(node->get_logger(), "Timed out waiting for cotton detection response");
    if (positions) {
      positions->clear();
    }
    return false;
  }

  auto response = future.get();
  if (!response->success) {
    RCLCPP_ERROR(node->get_logger(), "Cotton detection service failed: %s",
      response->message.c_str());
    if (positions) {
      positions->clear();
    }
    return false;
  }

  decode_detection_points(response->data, positions, node->get_logger());
  RCLCPP_INFO(node->get_logger(), "Cotton detection returned %zu candidate positions",
    positions ? positions->size() : 0);
  return true;
}

}  // namespace

/*
          MAIN PROGRAM
*/

int main (int argc, char** argv)
{
  rclcpp::init(argc, argv);
  auto node = rclcpp::Node::make_shared("yanthra_move");
  auto cotton_detection_client = node->create_client<cotton_detection_ros2::srv::CottonDetection>(
    "/cotton_detection/detect");

  /* Create executor for handling callbacks */
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);

  /* Create rate for main loop */
  rclcpp::Rate loop_rate(100);
  // moveit::planning_interface::MoveGroup group("Arm");

  /* Reading Configuration */
  node->declare_parameter("continous_operation", true);
  node->declare_parameter("delays.picking", 0.5);
  node->declare_parameter("delays.pre_start_len", 0.010);
  node->declare_parameter("jerk_enabled_theta", true);
  node->declare_parameter("jerk_enabled_phi", true);

  continous_operation = node->get_parameter("continous_operation").as_bool();
  picking_delay = node->get_parameter("delays.picking").as_double();
  pre_start_len = node->get_parameter("delays.pre_start_len").as_double();
  jerk_enabled_theta = node->get_parameter("jerk_enabled_theta").as_bool();
  jerk_enabled_phi = node->get_parameter("jerk_enabled_phi").as_bool();

   /* Joint3 configuration */
    node->declare_parameter("joint3_init.park_position", 0.0001);
    node->declare_parameter("joint3_init.homing_position", 0.001);
    joint3_parking_pose = node->get_parameter("joint3_init.park_position").as_double();
    joint3_homing_position = node->get_parameter("joint3_init.homing_position").as_double();
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "Joint3 Homing Position %d ", (int)joint3_homing_position) ;

      /* Joint 4 configuration */
   node->declare_parameter("joint4_init.multiple_zero_poses", true);
   joint4_multiple_zero_pose = node->get_parameter("joint4_init.multiple_zero_poses").as_bool();
   RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "multiple_zero_poses value read form config file := %d",joint4_multiple_zero_pose);

    node->declare_parameter("joint4_init.park_position", 0.001);
    node->declare_parameter("joint4_init.homing_position", 0.001);
    node->declare_parameter("joint4_init.theta_jerk_value", 0.0);
    joint4_parking_pose = node->get_parameter("joint4_init.park_position").as_double();
    joint4_homing_position = node->get_parameter("joint4_init.homing_position").as_double();
    theta_jerk_value = node->get_parameter("joint4_init.theta_jerk_value").as_double();

    node->declare_parameter("joint5_init.phi_jerk_value", 0.0);
    node->declare_parameter("l2_step_sleep_time", 2.0);
    node->declare_parameter("l2_homing_sleep_time", 5.0);
    phi_jerk_value = node->get_parameter("joint5_init.phi_jerk_value").as_double();
    l2_step_sleep_time = node->get_parameter("l2_step_sleep_time").as_double();
    l2_homing_sleep_time = node->get_parameter("l2_homing_sleep_time").as_double();
    d_out vaccum_motor(node,"vaccum_motor");



    if(joint4_multiple_zero_pose == true)
    {
          node->declare_parameter("joint4_init.zero_poses", std::vector<double>{0.0, 0.0});
          joint4_zero_poses = node->get_parameter("joint4_init.zero_poses").as_double_array();
          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "multiple_zero_poses value read form config file := %f, %f",joint4_zero_poses[0],joint4_zero_poses[1]);
 }


    else{
      joint4_zero_poses.push_back(0.0);
    }

      RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Joint4: Total Zero poses: %d", (int)joint4_zero_poses.size());

  /* Joint 5 configuration */
    node->declare_parameter("joint5_init.park_position", 0.0001);
    node->declare_parameter("joint5_init.homing_position", 0.001);
    node->declare_parameter("joint5_init.end_effector_len", 0.095);
    node->declare_parameter("joint5_init.min_length", 0.313);
    node->declare_parameter("joint5_init.max_length", 0.602);
    node->declare_parameter("joint5_init.joint5_vel_limit", 0.55);

    joint5_parking_pose = node->get_parameter("joint5_init.park_position").as_double();
    joint5_homing_position = node->get_parameter("joint5_init.homing_position").as_double();
    end_effector_len = node->get_parameter("joint5_init.end_effector_len").as_double();
    link5_min_length = node->get_parameter("joint5_init.min_length").as_double();
    link5_max_length = node->get_parameter("joint5_init.max_length").as_double();
    joint5_vel_limit = node->get_parameter("joint5_init.joint5_vel_limit").as_double();

    node->declare_parameter("joint2_init.height_scan_enable", true);
    node->declare_parameter("global_vaccum_motor", true);
    height_scan_enable = node->get_parameter("joint2_init.height_scan_enable").as_bool();
    Global_vaccum_motor = node->get_parameter("global_vaccum_motor").as_bool();
   RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_enable value read form config file := %d",height_scan_enable);
  /*#if HEIGHT_SCAN_EN == true
    double height_scan_min;
    double height_scan_max;
    double height_scan_step;
  #endif*/

// #if HEIGHT_SCAN_EN == true
    node->declare_parameter("joint2_init.min", 0.01);
    node->declare_parameter("joint2_init.max", 1.000);
    node->declare_parameter("joint2_init.step", 0.200);
    height_scan_min = node->get_parameter("joint2_init.min").as_double();
    height_scan_max = node->get_parameter("joint2_init.max").as_double();
    height_scan_step = node->get_parameter("joint2_init.step").as_double();
 // height_scan_value = height_scan_step;

  servo_out servo_joint_2(node, "joint2_move", height_scan_min, height_scan_max);  // commmented out by ribin this function is used for initialisation of servo,
  // the initialisation of odrive is done by adding the joint Parameters in the config file
  // so we dont need to initialise from here
// #endif

#if SECTOR_SCAN_EN == true
  servo_out servo_joint_1(node, "joint1_move", JOINT1_CONV_FACTOR);
  servo_joint_1.init();
#endif

  joint_move joint_move_3(node, "joint3_position_controller/");
  joint_move joint_move_4(node, "joint4_position_controller/");
  joint_move joint_move_5(node, "joint5_position_controller/");

/*####################here we are gonna add the call for l2 to initialised##################*/
  joint_move joint_move_2(node, "joint2_position_controller/");   // edited by ribin this is the joint for l2
/*##########################initialisation of l2 compleated################################*/

        joint_move::joint_pub_trajectory = node->create_publisher<trajectory_msgs::msg::JointTrajectory>("/arm_controller/command", 1000);
        joint_move::joint_homing_service = node->create_client<motor_control_msgs::srv::JointHoming>("/odrive_control/joint_init_to_home");
        // edited by ribin for making the l2 idle
        joint_move::joint_idle_service = node->create_client<motor_control_msgs::srv::JointHoming>("/odrive_control/joint_init_to_idle");
  /* Relay switches output */
#if END_EFFECTOR_EN == true
#if AGGREGATE_PICK_EN == false
  d_out front_valve(node, "front_valve");
  d_out back_valve(node, "back_valve");
  d_out end_effector(node, "end_effector");
#elif AGGREGATE_PICK_EN == true
  a_out pick_cotton(node, "pick_cotton");
#endif

#endif
  /* LED and Polariser working if Camera is enabled */
#if CAMERA_EN == true
  d_out led_control(node, "led_control");

#endif
  /* Limit Switch I/P for Joint 5 Initialisation */
#if JOINT5_INIT_EN == true
  d_in joint5_switch_in(node, "joint5_switch_in");
  d_out joint5_init_start(node, "joint5_init_start");
#endif
  /* START_SWITCH_IN and OUTPUT_INDICAATOR_LED for User to Start Picking operation */
#if START_SWITCH_EN == true
  d_in start_switch_in(node, "start_switch_in");
  d_out start_switch_out(node, "start_switch_out");
#endif
  a_out problem_indicator_out(node, "problem_indicator_out");
  /* SHUTDOWN_SWITCH_IN, if start_stop switch is pressed for more than 5sec, initiate shutdown */
#if SHUTDOWN_SWITCH_EN == true
  d_in shutdown_switch_in(node, "shutdown_switch_in");
#endif




  /* INITIALISATION */


  RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Starting Initialisation\n\n");

  /* Cotton Coordinates */
  std::vector<geometry_msgs::msg::Point> positions;
  std::vector<geometry_msgs::msg::PointStamped> positions_link3;

  /* Find the transformed coordinates from camera_reference_frame to link3 */
  geometry_msgs::msg::TransformStamped tf_camera_base;
  std::shared_ptr<tf2_ros::Buffer> tf_buffer; std::shared_ptr<tf2_ros::TransformListener> tf_listener;

  try
  {
    // TF2: Wait and lookup transform
    tf_camera_base = tf_buffer->lookupTransform("link3", "camera_depth_optical_frame", tf2::TimePointZero, tf2::durationFromSec(30.0));
  }
  catch(tf2::TransformException &ex)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "%s", ex.what());
  }
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Difference between Camera and Link3, x: %lf, y: %lf, z: %lf",
       tf_camera_base.transform.translation.x,
       tf_camera_base.transform.translation.y,
       tf_camera_base.transform.translation.z);


  /* Wait for callback to be called */
  std::this_thread::sleep_for(std::chrono::milliseconds(5000));



#if BREAD_BOARD == true
  return 0;
#endif
  std::string throwaway;
#if START_SWITCH_EN == true
         start_switch_out.command(true);
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Initialisation complete, \n Press START_SWITCH to start the Robot...\n\n");
        bool STARTSWITCH,SHUTDOWNSWITCH;
  while(  (!(SHUTDOWNSWITCH = shutdown_switch_in.state())) && (!(STARTSWITCH = start_switch_in.state())) )
  {
    // ros::spinOnce(); // TODO: Replace with ROS2 executor pattern
  }
  start_switch_out.command(false);
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "StartSwitch %d SHUTDOWNSWITCH %d \n", STARTSWITCH, SHUTDOWNSWITCH) ;
        if (SHUTDOWNSWITCH)
        {
                        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "SHUTTING  DOWN ROS AND SYSTEM");
                        system("sudo poweroff");
                        // rclcpp::shutdown(); // TODO: Implement proper ROS2 shutdown
                        // system("sudo poweroff");
        }


        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "Got STARTSWITCH COMMAND Continuing the program ... \n") ;
#else
  RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Initialisation complete, \n Press ENTER to start the Robot...(type 'return' to terminate the process)\n\n");
  std::getline(std::cin, throwaway);
  if(throwaway.compare("return") == 0)
    return 0;
#endif

  /*From ROS to ODRIVE HOMING REQUEST*/
  // The Odrive Homing Position is Independent of main program

  // Check whether the motor control services are available
  if (!ensure_motor_homing_service(node, joint_move::joint_homing_service)) {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),
      "Motor homing service unavailable. Cannot proceed with joint initialization.");
    problem_indicator_out.command(true);
    return 0;
  }

  if (!ensure_motor_idle_service(node, joint_move::joint_idle_service)) {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),
      "Motor idle service unavailable. Cannot proceed with joint initialization.");
    problem_indicator_out.command(true);
    return 0;
  }

  auto srv = std::make_shared<motor_control_msgs::srv::JointHoming::Request>();
  auto srv_idle = std::make_shared<motor_control_msgs::srv::JointHoming::Request>();

  // added by ribin for changing the sequance to height scan first
  // >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<,
  if (height_scan_enable == true) {
    srv->joint_id = 3;
    srv->homing_required = true;
    auto result = joint_move::joint_homing_service->async_send_request(srv);
    if (rclcpp::spin_until_future_complete(node, result, kHomingWaitTimeout) !=
        rclcpp::FutureReturnCode::SUCCESS)
    {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 Homing failed - service call timed out");
      problem_indicator_out.command(true);
      return 0;
    }

    auto homing_response = result.get();
    if (!homing_response->success) {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 Homing failed: %s",
        homing_response->reason.c_str());
      problem_indicator_out.command(true);
      return 0;
    }

    srv_idle->joint_id = 3;
    srv_idle->homing_required = false;
    auto result_idle = joint_move::joint_idle_service->async_send_request(srv_idle);
    if (rclcpp::spin_until_future_complete(node, result_idle, kHomingWaitTimeout) !=
        rclcpp::FutureReturnCode::SUCCESS)
    {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed - service call timed out");
      problem_indicator_out.command(true);
      return 0;
    }

    auto idle_response = result_idle.get();
    if (!idle_response->success) {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed: %s",
        idle_response->reason.c_str());
      problem_indicator_out.command(true);
      return 0;
    }
  }
  // >>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<  //

  // Joint5 Homing (r, i.e. Prismatic Joint)
  srv->joint_id = 2;
  srv->homing_required = true;
  auto result5 = joint_move::joint_homing_service->async_send_request(srv);
  if (rclcpp::spin_until_future_complete(node, result5, kHomingWaitTimeout) !=
      rclcpp::FutureReturnCode::SUCCESS)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint5 Homing failed - service call timed out");
    problem_indicator_out.command(true);
    return 0;
  }

  auto response5 = result5.get();
  if (!response5->success) {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint5 Homing failed: %s",
      response5->reason.c_str());
    problem_indicator_out.command(true);
    return 0;
  }

  // Joint3 Homing (phi, i.e. Revolute Joint sweeping along vertical)
  srv->joint_id = 0;
  srv->homing_required = true;
  auto result3 = joint_move::joint_homing_service->async_send_request(srv);
  if (rclcpp::spin_until_future_complete(node, result3, kHomingWaitTimeout) !=
      rclcpp::FutureReturnCode::SUCCESS)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint3 Homing failed - service call timed out");
    problem_indicator_out.command(true);
    return 0;
  }

  auto response3 = result3.get();
  if (!response3->success) {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint3 Homing failed: %s",
      response3->reason.c_str());
    problem_indicator_out.command(true);
    return 0;
  }

  // Joint4 Homing (theta, i.e. Revolute Joint sweeping along horizontal)
  srv->joint_id = 1;
  srv->homing_required = true;
  auto result4 = joint_move::joint_homing_service->async_send_request(srv);
  if (rclcpp::spin_until_future_complete(node, result4, kHomingWaitTimeout) !=
      rclcpp::FutureReturnCode::SUCCESS)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint4 Homing failed - service call timed out");
    problem_indicator_out.command(true);
    return 0;
  }

  auto response4 = result4.get();
  if (!response4->success) {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint4 Homing failed: %s",
      response4->reason.c_str());
    problem_indicator_out.command(true);
    return 0;
  }
            // chaned by ribin on 10/03/2020
          // Changing the sequance of initialisation to l2 first so moved this poriton of the code first
/*


    if (height_scan_enable ==true) {
    srv.request.joint_id = 3;
    srv_idle.request.joint_id = 3;
    if(joint_move::joint_homing_service.call(srv)! = true)
    {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 Homing, Reason: %s", srv.response.reason.c_str());
      problem_indicator_out.command(true);
      return 0;
    }


    if(joint_move::joint_idle_service.call(srv_idle)! = true)
   {
     RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle, Reason: %s", srv.response.reason.c_str());
     problem_indicator_out.command(true);
     return 0;
   }



  }
  */

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "All joints are initialised");

    /* Move Joint3 and Joint4 to their default pose */
    // joint_move_3.move_joint(0.0, WAIT);
    // joint_move_4.move_joint(0.0, WAIT);

  /* While ROS OK */
  while(rclcpp::ok())
  {


#if START_SWITCH_EN == true
    RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Ready to go to another cycle, \n Press START_SWITCH start the Robot...\n\n");
    start_switch_out.command(true);  // Switch On the Red bulb indicator

          while(  (!(SHUTDOWNSWITCH = shutdown_switch_in.state())) && (!(STARTSWITCH = start_switch_in.state())) )
    {
      // ros::spinOnce(); // TODO: Replace with ROS2 executor pattern
    }
    start_switch_out.command(false);  // Switch OFF the red bulb user indicator
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "StartSwitch %d SHUTDOWNSWITCH %d \n", STARTSWITCH, SHUTDOWNSWITCH) ;
                if (SHUTDOWNSWITCH)
                {
                        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "SHUTTING DOWN ROS and Powering down ");
                        system( "sudo poweroff") ;
                        // rclcpp::shutdown(); // TODO: Implement proper ROS2 shutdown
                        // system( "sudo poweroff") ;
                }


                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "Got STARTSWITCH COMMAND Continuing the program ... \n") ;
#else
    RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Ready to go to another cycle, \n Press ENTER to start the Robot...(type 'return' to terminate the process)\n\n");
    std::getline(std::cin, throwaway);
    if(throwaway.compare("return") == 0)
                  return 0;
#endif


    /* **** Height SCAN **** */
// #if HEIGHT_SCAN_EN == true
//  servo_joint_2.init();  // commmented out by ribin for l2
// since the motor is initialised and homing position is done, we dont have to do the initialisation again so commenting out this init()

/*####################here we are gonna add the call for l2 to initialised##################*/

/*##########################initialisation of l2 compleated################################*/

  // ros::Duration(10.0).sleep();
/*  do
  {
      std::this_thread::sleep_for(std::chrono::seconds(2));
#endif */
int number_of_steps =0;


if (height_scan_enable ==true) {
  number_of_steps = height_scan_max /height_scan_step;
}  // 10/2 =5  // 0.4 /0.15
else{
   number_of_steps =0;
}
double height_scan_value = height_scan_min;

for(int i = 0; i <= number_of_steps; i++)
{



  if (height_scan_enable ==true) {
    if (height_scan_value < height_scan_max)
    {
    joint_move_2.move_joint(height_scan_value,WAIT);
    std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(l2_step_sleep_time * 1000)));
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_value %f:= ",height_scan_value);
    height_scan_value = height_scan_value+height_scan_step;
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_step value %f: = ", height_scan_step);
    // we are calling the idle for l2 here after moving to a position
    srv_idle->joint_id = 3;
    srv_idle->homing_required = false;
    auto result_idle_step = joint_move::joint_idle_service->async_send_request(srv_idle);
    if (rclcpp::spin_until_future_complete(node, result_idle_step, kHomingWaitTimeout) !=
        rclcpp::FutureReturnCode::SUCCESS)
    {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed - service call timed out");
      problem_indicator_out.command(true);
      return 0;
    }

    auto idle_step_response = result_idle_step.get();
    if (!idle_step_response->success) {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed: %s",
        idle_step_response->reason.c_str());
      problem_indicator_out.command(true);
      return 0;
    }
//    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_value %f: = ", height_scan_value);


  }

}

            for(size_t joint4_cnt = 0; joint4_cnt < joint4_zero_poses.size(); joint4_cnt++)
            {
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Joint4: Moving to Zero Pose: %f", (int)joint4_cnt);


                /* Make link3 to look down, while capturing */

                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Joint3: Moving to Homing Position: \n");
                joint_move_5.move_joint(joint5_homing_position, WAIT);   // Move joint5 fully back TODO change 0.001 to joint_zero_poses[joint3_cnt]
                joint_move_3.move_joint(joint3_homing_position, WAIT);  // TODO(developer) change 0.001 to joint_zero_poses[joint3_cnt]
                joint_move_4.move_joint(joint4_zero_poses[joint4_cnt], WAIT);

                /* Initiate a camera start request */
#if CAMERA_EN == true
                led_control.command(START);
    // vaccum_motor.command(START);  // added by ribin for controlling the blower motor
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),
                  "Invoking /cotton_detection/detect to capture cotton targets");
                bool detection_ok = invoke_cotton_detection(
                  node, cotton_detection_client, &positions);
                if (!detection_ok) {
                  problem_indicator_out.command(true);
                  positions_link3.clear();
                }
                led_control.command(STOP);
                record_debug_data();    // Store the captured images in debug folder
#endif
                /* Get the coordinates of cotton */
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),
                  "Cotton detection supplied %zu raw coordinates", positions.size());


                /* Convert cotton coordinates from camera_frame to link3 frame */
#if CAMERA_EN == true
                getCottonCoordinates_cameraToLink3(&listener_camera_base, &positions, &positions_link3);
#else
                getCottonCoordinates_ToLink3(&positions, &positions_link3);
#endif






                int trgt = 0;
                for(std::vector<geometry_msgs::msg::PointStamped>::iterator it = positions_link3.begin(); it != positions_link3.end(); it++)
                {
                    double  r = 0,
                    theta = 0,
                    phi = 0;


                    /* If targets to be reached in steps, rather continous operation */
                    if(continous_operation != true)
                    {
                        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Press ENTER to move to next target...(type 'done' to terminate the process)\n\n");
                        std::getline(std::cin, throwaway);
                        if(throwaway.compare("done") == 0)
                            break;
                    }
                    RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Moving to target %d\n", ++trgt);


                    /* Convert XYZ coordinate to polar coordinates */
                    xyz_to_polar(it->point.x, it->point.y, it->point.z, &r, &theta, &phi);
                    RCLCPP_WARN(rclcpp::get_logger("yanthra_move"),  "In yanthra_move_calibrate.cpp") ;
                    RCLCPP_WARN(rclcpp::get_logger("yanthra_move"),  " YANTHRA_MOVE found R : %f, theta : %f , phi :%f ",r, theta, phi) ;
                    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),  "CHECKING REACHABILITY") ;
                    if(check_reachability(r, theta, phi) == true)
                    {
                      if(Global_vaccum_motor == true)
                      {
                        vaccum_motor.command(START);  // added by ribin for controlling the blower motor
                        // TODO(developer) check whether the motor is still on or not
                        }


                        joint_move_5.move_joint(joint5_homing_position, WAIT);   // Move joint5 fully back TODO change 0.001 to joint_zero_poses[joint3_cnt]

                        joint_move_4.move_joint(joint4_zero_poses[joint4_cnt] + theta, WAIT);
                        joint_move_3.move_joint(joint3_homing_position + phi, WAIT);
                        // here we are gonna add a jerk to the theta



                        r -= LINK5_MIN_LENGTH;
#if END_EFFECTOR_EN == true
#if AGGREGATE_PICK_EN == true
                        float pre_start_delay = ((r - pre_start_len) / joint5_vel_limit);
                        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "End-Effector will start in %f sec", pre_start_delay);
                        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "End-Effector will start in %f sec", pre_start_delay);
                        if (pre_start_delay <0)  // added by ribin for calling the pick cotton if the pre_start_delay is negative
                        {
                          pre_start_delay = 0;
                        }


                        pick_cotton.command(pre_start_delay);
#endif
#endif

                        joint_move_5.move_joint(r, WAIT);
                        if(jerk_enabled_theta == true)
                        {
                          float delta_theta = theta_jerk_value/r;
                          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "delta_theta %lf",delta_theta);
                          joint_move_4.move_joint(joint4_zero_poses[joint4_cnt] + theta + delta_theta, WAIT);
                          joint_move_4.move_joint(joint4_zero_poses[joint4_cnt] + theta - delta_theta, WAIT);
                          joint_move_4.move_joint(joint4_zero_poses[joint4_cnt] + theta, WAIT);


                        }
                        if(jerk_enabled_phi == true)
                        {
                          float delta_phi =phi_jerk_value/r;
                          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "delta_phi %lf",delta_phi);
                          joint_move_3.move_joint(joint3_homing_position + phi + delta_phi, WAIT);
                          joint_move_3.move_joint(joint3_homing_position + phi - delta_phi , WAIT);
                          joint_move_3.move_joint(joint3_homing_position + phi, WAIT);


                        }

                    /*    // ros::Duration(1).sleep();
                        joint_move_5.move_joint(r-0.025, WAIT);     // TODO(developer) Jerky Motion  // Author Mani
                        // ros::Duration(1).sleep();
                        joint_move_5.move_joint(r+0.010, WAIT); */
                        std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(picking_delay * 1000)));
                    } else
                    {
                        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Cotton target %d is out of bound", trgt);
                    }
                    // ros::spinOnce(); // TODO: Replace with ROS2 executor pattern
                    if((joint_move_3.error_code != NO_ERROR) ||
                       (joint_move_4.error_code != NO_ERROR) ||
                       (joint_move_5.error_code != NO_ERROR))
                    {
                        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "PROBLEM IN SOME JOINT");
                        problem_indicator_out.command(true);
                        break;
                    }  // if ((joint_move_3.error ...
                }  // for ((std::vector<geometry_msgs::msg::PointStamped>::iterator it = positions_link3.begin(); it != positions_link3.end(); it++
                if(Global_vaccum_motor == true){
                    vaccum_motor.command(STOP);  // here we are gonna publish a msg that gonna swithoff the blower
                }
    }  // for(size_t joint4_cnt = 0; joint4_cnt < joint4_zero_poses.size(); joint4_cnt++)
// #if HEIGHT_SCAN_EN == true



            /* Move joint4 to align with the row, so that height can be changed */
            joint_move_5.move_joint(joint5_homing_position, WAIT);  // TODO(developer) This homing Position is different from Initialisation homing position but both can be same
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            joint_move_4.move_joint(joint4_homing_position, WAIT);  // TODO(developer) move it to joint4_homing_position
            joint_move_3.move_joint(joint3_homing_position, WAIT);
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "all joints are in homing_position going for l2 movement");
            // joint_move_2.move_joint(height_scan_value,WAIT);



/*
if (height_scan_enable ==true) {

  if (height_scan_value < height_scan_max)
  {
  joint_move_2.move_joint(height_scan_value,WAIT);
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_value %d:= ",height_scan_value);
  height_scan_value = height_scan_value+height_scan_step;
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_step value %d : = ", height_scan_step);
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_max value %d : = ", height_scan_max);


}
  if (height_scan_value >= height_scan_max)
  {
    // height_scan_value = height_scan_step; logic error .0.2
    height_scan_value = height_scan_min;
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_value %f:= ",height_scan_value);


  }
}
*/

}
if(height_scan_enable ==true)
{
     RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan is enabled, height_scan_value:= %f", height_scan_value);
     RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "moving to top position");
     joint_move_2.move_joint(height_scan_min,WAIT);
     std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(l2_homing_sleep_time * 1000)));
     // we are calling the idle for l2 here after moving to a position
     srv_idle->joint_id = 3;
     srv_idle->homing_required = false;
     auto result_idle_final = joint_move::joint_idle_service->async_send_request(srv_idle);
     if (rclcpp::spin_until_future_complete(node, result_idle_final, kHomingWaitTimeout) !=
         rclcpp::FutureReturnCode::SUCCESS)
     {
       RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed - service call timed out");
       problem_indicator_out.command(true);
       return 0;
     }

     auto idle_final_response = result_idle_final.get();
     if (!idle_final_response->success) {
       RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed: %s",
         idle_final_response->reason.c_str());
       problem_indicator_out.command(true);
       return 0;
     }


}

}

  // while(servo_joint_2.move(height_scan_step));  // commmented out by ribin  // this is the code used for moving the servo motor step by step,
// so we are gonna change this code for calling odrive so we can move step by step
// ##########################l2 height_scan_step ###############  //
// while (true) {

// break;
// }
// here we have to pass the value for moving the l2 up and down, repeatedly so lets assume the l2 is at homing_position
// so the starting posiiton is 0.0 , the max pos and min pose is loaded from the config file.
// lets consider the min pose to be 0.0 and max position to be 1000 cm. or 1 meter
// here we have to find the zero_offset_
/  // / #####################l2 height_scan_step ##########################  //
// #endif
    /* Parking Position */
    joint_move_5.move_joint(joint5_parking_pose, WAIT);
    joint_move_4.move_joint(joint4_parking_pose, WAIT);
    joint_move_3.move_joint(joint3_parking_pose, WAIT);




  return 0;
}
