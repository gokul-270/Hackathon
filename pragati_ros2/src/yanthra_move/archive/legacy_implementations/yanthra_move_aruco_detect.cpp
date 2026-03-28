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


#History : 5Jan2021
#  Added ability to read aruco markers (No 23) so that it is good for testing in the lab
#  without the need for testing cotton in the lab.

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
#include "dynamixel_msgs/msg/joint_state.hpp"
#include <iostream>
#include <fstream>
#include <stdio.h>
#include <yanthra_move/yanthra_move.h>
#include <yanthra_move/joint_move.h>
#include <yanthra_move/yanthra_io.h>
#include "cotton_detection_ros2/srv/cotton_detection.hpp"
#include "motor_control_msgs/srv/joint_homing.hpp"
// #include "cotton_detection/capture_cotton_srv.h"  // ROS1 service - commented for ROS2
#include <sys/time.h>
#include <time.h>
#include <chrono>
#include <thread>

// Energy-efficient cotton picking path optimizer
#include "yanthra_move/cotton_picking_optimizer.hpp"

double start_time, end_time, last_time;

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
bool YanthraLabCalibrationTesting = true;
int picked = 0;
double joint2_old_pose = 0.001;
// ros::ServiceClient cotton_client;  // ROS1 service client - commented for ROS2
/*
   MAIN PROGRAM
   */

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



static void print_timestamp(const char *msg)
{
  time_t ct = { 0 };
  struct tm lut_tm = { 0 };
  char lut[30] = { 0 };


  assert(msg && (strlen(msg) > 0));
  ct = time(NULL);
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "%s at %s\n", msg, asctime_r(localtime_r(&ct, &lut_tm), lut));
}




double currentTimeMillis()
{
  struct timeval timeVar ;
  gettimeofday(&timeVar, NULL);
  double s1 = (long) (timeVar.tv_sec) * 1000;
  double s2 = (timeVar.tv_usec/1000);
  return(s1+s2);
}






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
        std::vector<std::vector<double>> joint_pose_values;
  // moveit::planning_interface::MoveGroup group("Arm");

  /* Reading Configuration */
  node->declare_parameter("continous_operation");
  node->declare_parameter("delays.picking");
  node->declare_parameter("delays.pre_start_len");
  node->declare_parameter("jerk_enabled_theta");
  node->declare_parameter("jerk_enabled_phi");

  continous_operation = node->get_parameter("continous_operation").as_bool();
  picking_delay = node->get_parameter("delays.picking").as_double();
  pre_start_len = node->get_parameter("delays.pre_start_len").as_double();
  jerk_enabled_theta = node->get_parameter("jerk_enabled_theta").as_bool();
  jerk_enabled_phi = node->get_parameter("jerk_enabled_phi").as_bool();

  /* Joint3 configuration */
  node->declare_parameter("joint3_init.park_position");
  node->declare_parameter("joint3_init.homing_position");
  node->declare_parameter("joint3_init.multiple_zero_poses");
  joint3_parking_pose = node->get_parameter("joint3_init.park_position").as_double();
  joint3_homing_position = node->get_parameter("joint3_init.homing_position").as_double();
  joint3_multiple_zero_pose = node->get_parameter("joint3_init.multiple_zero_poses").as_bool();

  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "Joint3 Homing Position %d ", (int)joint3_homing_position) ;

  /* Joint 4 configuration */
  node->declare_parameter("joint4_init.multiple_zero_poses");
  joint4_multiple_zero_pose = node->get_parameter("joint4_init.multiple_zero_poses").as_bool();
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "multiple_zero_poses value read form config file := %d",joint4_multiple_zero_pose);

  node->declare_parameter("joint4_init.park_position");
  node->declare_parameter("joint4_init.homing_position");
  node->declare_parameter("joint4_init.theta_jerk_value");
  joint4_parking_pose = node->get_parameter("joint4_init.park_position").as_double();
  joint4_homing_position = node->get_parameter("joint4_init.homing_position").as_double();
  theta_jerk_value = node->get_parameter("joint4_init.theta_jerk_value").as_double();

  node->declare_parameter("joint5_init.phi_jerk_value");
  node->declare_parameter("l2_step_sleep_time");
  node->declare_parameter("l2_homing_sleep_time");
  phi_jerk_value = node->get_parameter("joint5_init.phi_jerk_value").as_double();
  l2_step_sleep_time = node->get_parameter("l2_step_sleep_time").as_double();
  l2_homing_sleep_time = node->get_parameter("l2_homing_sleep_time").as_double();

  node->declare_parameter("joint_poses");
  joint_pose_values = node->get_parameter("joint_poses").as_double_array();
  RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "%f",joint_pose_values[0][1]);
        int size_of_pose =joint_pose_values.size();
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "%d",size_of_pose);
        for(int i = 0; i<size_of_pose; i++ )
        {


                // pose values read from yaml file

                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link2 poses %f: = ",joint_pose_values[i][0]);
                double joint2_pose =  joint_pose_values[i][0];
                double joint3_pose  = joint_pose_values[i][1];
                double joint4_pose  = joint_pose_values[i][2];
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link2 poses %f: = ",joint2_pose);
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link2 poses %f: = ",joint3_pose);
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link2 poses %f: = ",joint4_pose);

        }

  d_out vaccum_motor(node,"vaccum_motor");


  if(joint3_multiple_zero_pose==true)
  {
    node->declare_parameter("joint3_init.zero_poses");
    joint3_zero_poses = node->get_parameter("joint3_init.zero_poses").as_double_array();
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "multiple_zero_poses value read form config file := %f, %f",joint3_zero_poses[0],joint3_zero_poses[1]);


  }

  else {
    joint3_zero_poses.push_back(0.0);
  }


  if(joint4_multiple_zero_pose == true)
  {
    node->declare_parameter("joint4_init.zero_poses");
    joint4_zero_poses = node->get_parameter("joint4_init.zero_poses").as_double_array();
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "multiple_zero_poses value read form config file := %f, %f",joint4_zero_poses[0],joint4_zero_poses[1]);
  }


  else{
    joint4_zero_poses.push_back(0.0);
  }

  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Joint4: Total Zero poses: %d", (int)joint4_zero_poses.size());
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "joint3: Total Zero poses: %d",(int)joint3_zero_poses.size());
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
  // the motor controller initialisation is done by adding the joint Parameters in the config file
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
  joint_move::joint_homing_service = node->create_client<motor_control_msgs::srv::JointHoming>("/motor_control/joint_init_to_home");
  // edited by ribin for making the l2 idle
  joint_move::joint_idle_service = node->create_client<motor_control_msgs::srv::JointHoming>("/motor_control/joint_init_to_idle");
  /* Relay switches output */

  // edited by ribin for calling cotton_detectin_service on 20_04_2020
  // TODO: Port cotton_detection service to ROS2 or wrap as needed
  // joint_move::cotton_detection_ml_service = node->create_client<cotton_detection::srv::CaptureCotton>("/capture_cotton");
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "cotton detection service integration pending ROS2 port");



#if END_EFFECTOR_EN == true
#if AGGREGATE_PICK_EN == false
  d_out front_valve(node, "front_valve");
  d_out back_valve(node, "back_valve");
  d_out end_effector(node, "end_effector");
#elif AGGREGATE_PICK_EN == true
  a_out pick_cotton(node, "pick_cotton");
  a_out drop_cotton(node, "drop_cotton");
  a_out lid_open(node, "lid_open");
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
  d_out problem_indicator_out(node, "problem_indicator_out");
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
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  start_switch_out.command(false);
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "StartSwitch %d SHUTDOWNSWITCH %d \n", STARTSWITCH, SHUTDOWNSWITCH) ;
  if (SHUTDOWNSWITCH)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "SHUTTING  DOWN ROS AND SYSTEM");
    system("sudo poweroff");
    rclcpp::shutdown(); // Shutting down ROS2
    // system("sudo poweroff");
  }


  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "Got STARTSWITCH COMMAND Continuing the program ... \n") ;
#else
  RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Initialisation complete, \n Press ENTER to start the Robot...(type 'return' to terminate the process)\n\n");
  std::getline(std::cin, throwaway);
  if(throwaway.compare("return") == 0)
    return 0;
#endif

  /*From ROS to motor controller homing request*/
  // Note: The motor controller homing position is independent of main program

  // Check whether the joint homing services are available before proceeding
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Checking joint homing service availability...");

  if (!joint_move::joint_homing_service.wait_for_service(std::chrono::seconds(5))) {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),
                 "❌ Joint homing service not available after waiting 5 seconds!");
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),
                 "   Please ensure motor_control_ros2 node is running.");
    problem_indicator_out.command(true);
    return 0;
  }

  if (!joint_move::joint_idle_service.wait_for_service(std::chrono::seconds(5))) {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),
                 "❌ Joint idle service not available after waiting 5 seconds!");
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"),
                 "   Please ensure motor_control_ros2 node is running.");
    problem_indicator_out.command(true);
    return 0;
  }

  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "✅ All required services are available");

  motor_control_msgs::srv::JointHoming srv;
  motor_control_msgs::srv::JointHoming srv_idle;


  // added by ribin for changing the sequance to height scan first
  // >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<,
  if (height_scan_enable ==true) {
    srv.request.joint_id = 3;
    srv_idle.request.joint_id = 3;
    if(joint_move::joint_homing_service.call(srv)! = true)
    {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 Homing, Reason: %s", srv.response.reason.c_str());
      problem_indicator_out.command(true);
      return 0;
    }


                std::this_thread::sleep_for(std::chrono::seconds(10));
    if(joint_move::joint_idle_service.call(srv_idle)! = true)
    {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle, Reason: %s", srv.response.reason.c_str());
      problem_indicator_out.command(true);
      return 0;
    }



  }
  // >>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<  //
  // Joint5 Homing (r, i.e. Prismatic Joint)
  srv.request.joint_id = 2;
  if(joint_move::joint_homing_service.call(srv) != true)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint5 Homing, Reason: %s", srv.response.reason.c_str());
    problem_indicator_out.command(true);
    return 0;
  }


  // Joint3 Homing (phi, i.e. Revolute Joint sweeping along vertical)
  srv.request.joint_id = 0;
  if(joint_move::joint_homing_service.call(srv) != true)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint3 Homing, Reason: %s", srv.response.reason.c_str());
    problem_indicator_out.command(true);
    return 0;
  }


  // Joint4 Homing (theta, i.e. Revolute Joint sweeping along horizontal)
  srv.request.joint_id = 1;
  if(joint_move::joint_homing_service.call(srv) != true)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint4 Homing, Reason: %s", srv.response.reason.c_str());
    problem_indicator_out.command(true);
    return 0;
  }
  // chaned by ribin on 10/03/2020
  // Changing the sequance of initialisation to l2 first so moved this poriton of the code first
  /*
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
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  start_switch_out.command(false);  // Switch OFF the red bulb user indicator
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "StartSwitch %d SHUTDOWNSWITCH %d \n", STARTSWITCH, SHUTDOWNSWITCH) ;
  if (SHUTDOWNSWITCH)
  {
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "SHUTTING DOWN ROS and Powering down ");
    system( "sudo poweroff") ;
    rclcpp::shutdown(); // Shutting down ROS2
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
  /*####################here we are gonna add the call for l2 to initialised##################*/

  /*##########################initialisation of l2 compleated################################*/


  print_timestamp("height sacn started");

  int number_of_steps =0;

  if (height_scan_enable ==true) {
    number_of_steps = height_scan_max /height_scan_step;
  }  // 10/2 =5  // 0.4 /0.15
  else{
    number_of_steps =0;
  }
  double height_scan_value = height_scan_min;

  start_time = currentTimeMillis();
  double time_taken_between_height_scan = start_time - last_time;  // computed in milli seconds

  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "TIMETO taken between height_scan = %f ",time_taken_between_height_scan);

        for(int i = 0; i<size_of_pose; i++ )
        {


                // pose values read from yaml file

                double joint2_pose =  joint_pose_values[i][0];
                double joint3_pose  = joint_pose_values[i][1];
                double joint4_pose  = joint_pose_values[i][2];
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link2 poses %f: = ",joint2_pose);
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link3 poses %f: = ",joint3_pose);
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link2 poses %f: = ",joint4_pose);
                RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "link2 old poses %f: = ",joint2_old_pose);

               if (height_scan_enable ==true) {
      if (joint2_pose < height_scan_max)
      {
         if(joint2_old_pose != joint2_pose){


        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "inside");

                    joint_move_4.move_joint(joint4_homing_position, WAIT);  // TODO(developer) move it to joint4_homing_position
        std::this_thread::sleep_for(std::chrono::seconds(2));
        joint_move_2.move_joint(joint2_pose,WAIT);
        std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(l2_step_sleep_time * 1000)));
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_step value %f: = ", joint2_pose);
        // we are calling the idle for l2 here after moving to a position
        srv_idle->joint_id = 3;
        srv_idle->homing_required = false;
        auto result_idle_height = joint_move::joint_idle_service->async_send_request(srv_idle);
        if (rclcpp::spin_until_future_complete(node, result_idle_height, kHomingWaitTimeout) !=
            rclcpp::FutureReturnCode::SUCCESS)
        {
          RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed - service call timed out");
          problem_indicator_out.command(true);
          return 0;
        }

        auto idle_height_response = result_idle_height.get();
        if (!idle_height_response->success) {
          RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed: %s",
            idle_height_response->reason.c_str());
          problem_indicator_out.command(true);
          return 0;
        }
        //    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan_value %f: = ", height_scan_value);




      }
      joint2_old_pose = joint2_pose;
          }

    }




      joint_move_5.move_joint(joint5_homing_position, WAIT);   // Move joint5 fully back TODO change 0.001 to joint_zero_poses[joint3_cnt]
      std::this_thread::sleep_for(std::chrono::seconds(2));
      joint_move_3.move_joint(joint3_pose,WAIT);
      std::this_thread::sleep_for(std::chrono::seconds(2));
      joint_move_4.move_joint(joint4_pose, WAIT);

      /* Initiate a camera start request */
#if CAMERA_EN == true
    if (!YanthraLabCalibrationTesting) {
      std::this_thread::sleep_for(std::chrono::seconds(3));
      led_control.command(START);
      // vaccum_motor.command(START);  // added by ribin for controlling the blower motor
      RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),
        "Invoking /cotton_detection/detect for target acquisition");
      bool detection_ok = invoke_cotton_detection(
        node, cotton_detection_client, &positions);
      if (!detection_ok) {
        problem_indicator_out.command(true);
        positions_link3.clear();
      }
      led_control.command(STOP);
      record_debug_data();    // Store the captured images in debug folder
      RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),
        "Cotton detection supplied %zu raw coordinates", positions.size());
      getCottonCoordinates_cameraToLink3(&listener_camera_base, &positions, &positions_link3);
    } else {  // of YanthraLabCalibrationTesting
          // sprintf(FilePathName,"%s/result_image", PRAGATI_OUTPUT_DIR);
      sprintf(cotton_coordinate_filename ,"%s/cotton_details.txt", PRAGATI_OUTPUT_DIR);

      // Call ARUCO_FINDER_PROGRAM
      // Aruco_Finder put the location of the files in the file centroid.tx
      // Read data from centroid.txt and then move the arm

      system(ARUCO_FINDER_PROGRAM);

      /* Read  from the generated centroid.txt file from aruco_finder */
      std::ifstream mark_centroid("centroid.txt");
      if (!mark_centroid.is_open()) {
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Error: not able to open the file : centroid.txt ");
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Exiting yanthra_move ");
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Error: not able to open the file : centroid.txt ");
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Exiting yanthra_move ");
        exit(1) ;
      }

      std::ofstream cotton_fs(cotton_coordinate_filename.c_str());

      if (!cotton_fs.is_open()) {
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Error: not able to open the file : %s ", cotton_coordinate_filename.c_str());
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Exiting yanthra_move ");
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Error: not able to open the file : %s ", cotton_coordinate_filename.c_str());
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Exiting yanthra_move ");
        exit(1) ;
      }


      float XValue, YValue, ZValue;
      int PixelColumn = 0 ;
      int PixelRow = 0 ;
      while(mark_centroid >> x >> y >> z)
      {
        // Print to the cotton_details.txt file the four corners of the marker
        // These values are w.r.t to the Camera origin.
        // When using in the arm this has to be converted to ARM's origin.


        cotton_fs << PixelColumn <<" " << PixelRow << " " <<" "<< (float) XValue << " " <<(float)YValue << " " << (float) ZValue << std::endl ;
        cotton_fs.flush();
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),  "( XValue : %.2f, YValue :  %.2f, ZValue : %.2f)", XValue, YValue, ZValue) ;
      }
      // Close the output steam
      cotton_fs.close();
      mark_centroid.close();

      // Reading the CottonCoordinate from a file
      get_cotton_coordinates(&positions);
      getCottonCoordinates_cameraToLink3(&listener_camera_base, &positions, &positions_link3);
  }  //  of -- if (YanthraLabCalibration)
#else
  getCottonCoordinates_ToLink3(&positions, &positions_link3);
#endif

      // ========================================================================
      // ENERGY OPTIMIZATION: Sort cotton positions for battery-efficient picking
      // ========================================================================
      if (!positions_link3.empty()) {
          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),
                     "🔋 Optimizing picking order for %zu cotton positions (energy-efficient)",
                     positions_link3.size());

          // Get current base angle (phi) from joint3_pose for nearest-neighbor starting point
          double current_phi = std::atan2(
              std::sin(joint3_pose * 2 * M_PI),  // Assuming joint3_pose in rotations
              std::cos(joint3_pose * 2 * M_PI)
          );

          // Apply hierarchical optimization (minimizes Joint3 base rotation - highest energy cost)
          yanthra_move::CottonPickingOptimizer::optimizePickingOrder(
              positions_link3,
              yanthra_move::CottonPickingOptimizer::Strategy::HIERARCHICAL,
              current_phi
          );

          // Estimate and log energy savings
          double savings = yanthra_move::CottonPickingOptimizer::estimateEnergySavings(
              positions_link3,
              yanthra_move::CottonPickingOptimizer::Strategy::HIERARCHICAL
          );

          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"),
                     "⚡ Estimated energy savings: %.1f%% (sorted for smooth phi sweep)",
                     savings);
      }
      // ========================================================================

                                        if(Global_vaccum_motor == true)
                                        {
                                                vaccum_motor.command(START);  // added by ribin for controlling the blower motor
                                                // TODO(developer) check whether the motor is still on or not




                                        }
      // here we are gonna pick all cotton in current pose, the positions_link3 variable is loaded with positions of each cotton which is validated for reachability
      int trgt = 0;
    //  int picked =0;
      double  start_time_to_pick_n_number_of_cotton = currentTimeMillis();
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
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"),  " YANTHRA_MOVE found R : %f, theta : %f , phi :%f ",r, theta, phi) ;
        if(check_reachability(r, theta, phi) == true)
        {
          double picking_time_started = currentTimeMillis();
          joint_move_5.move_joint(joint5_homing_position, WAIT);   // Move joint5 fully back TODO change 0.001 to joint_zero_poses[joint3_cnt]
          float joint5_delay = (r/joint5_vel_limit);
          std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(joint5_delay * 1000)));
          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "joint5 return delay: %f ", joint5_delay);
          RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "picked number: %d ", picked);




          joint_move_4.move_joint(joint4_pose + theta, WAIT);
          joint_move_3.move_joint(joint3_pose + phi,WAIT);
          float joint_velocity = (10000/8192)*2*3.14;
          float joint4_delay = joint4_pose/joint_velocity;
          float joint3_delay = joint3_pose/joint_velocity;
          if(joint4_delay < 0)
          {
            joint4_delay = joint4_delay * -1 ;


          }
          if(joint3_delay < 0)
          {
            joint3_delay = joint3_delay * -1;
          }


          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "joint4_delay %f ", joint4_delay);            // joint4 delay
          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "joint3_delay %f ", joint3_delay);            // joint3 delay

          if (joint4_delay > joint3_delay)
          {
            std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>((joint4_delay+0.2) * 1000)));


          } else
          {
            std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>((joint3_delay+0.2) * 1000)));
          }


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
          double link_5_start_time = currentTimeMillis();
          joint_move_5.move_joint(r, WAIT);
          float joint5_forward_delay = joint5_delay + picking_delay;

          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "joint5_forward_delay %f ", joint5_forward_delay);     // joint5 forward delay
          std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(joint5_forward_delay * 1000)));
          double link_5_end_time = currentTimeMillis();
          double link_5_moving_time = link_5_end_time - link_5_start_time;
          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "TIMETO link_5_moving_time = %f ",link_5_moving_time);

          double end_picking_time =currentTimeMillis();
          picked++;
          double time_taken_for_each_pick = end_picking_time - picking_time_started;
          RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "TIMETO pick one cotton by arm and EEffector = %f ",time_taken_for_each_pick);
          joint_move_5.move_joint(joint5_homing_position, WAIT);   // Move joint5 fully back TODO change 0.001 to joint_zero_poses[joint3_cnt]
          std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(joint5_delay * 1000)));
        /*  if (picked == 5){

              if(Global_vaccum_motor == true)
                                          {
                                                vaccum_motor.command(STOP);  // added by ribin for controlling the blower motor
                                                // TODO(developer) check whether the motor is still on or not
                                          }
            RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "inisde picking");
            joint_move_3.move_joint(joint3_parking_pose,WAIT);
           std::this_thread::sleep_for(std::chrono::seconds(1));
            joint_move_4.move_joint(joint4_parking_pose,WAIT);
           std::this_thread::sleep_for(std::chrono::seconds(1));

            std::this_thread::sleep_for(std::chrono::seconds(1));
            lid_open.command(2);
            std::this_thread::sleep_for(std::chrono::seconds(3));
            picked = 0;
            joint_move_4.move_joint(joint4_zero_poses[joint4_cnt] , WAIT);
            joint_move_3.move_joint(joint3_zero_poses[joint3_cnt] ,WAIT);
            std::this_thread::sleep_for(std::chrono::milliseconds(1500));

              if(Global_vaccum_motor == true)
                                          {
                                                vaccum_motor.command(START);  // added by ribin for controlling the blower motor
                                                // TODO(developer) check whether the motor is still on or not
                                          }
          }*/


                                       drop_cotton.command(joint5_delay);
        } else
        {
          RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Cotton target %d is out of bound", trgt);
        }
        executor.spin_some();
        if((joint_move_3.error_code != NO_ERROR) ||
            (joint_move_4.error_code != NO_ERROR) ||
            (joint_move_5.error_code != NO_ERROR))
        {
          RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "PROBLEM IN SOME JOINT");
          problem_indicator_out.command(true);
          break;
        }  // if ((joint_move_3.error ...
      }
      end_time = currentTimeMillis();
      double time_taken_for_picking_n_number_of_cotton = end_time - start_time_to_pick_n_number_of_cotton;
      RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "TIMETO pick %d number of cotton = %f",picked,time_taken_for_picking_n_number_of_cotton);
      // RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "TIMETO pick %d number of cotton %f",picked,(int)time_taken_for_picking_n_number_of_cotton);
      RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "NUMBEROF cotton picked = %d",picked);


      if(Global_vaccum_motor == true){
        vaccum_motor.command(STOP);  // here we are gonna publish a msg that gonna swithoff the blower
      }

        if (picked > 10){

            RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "inisde picking");
            joint_move_3.move_joint(joint3_parking_pose,WAIT);
           std::this_thread::sleep_for(std::chrono::seconds(1));
            joint_move_4.move_joint(joint4_parking_pose,WAIT);
            std::this_thread::sleep_for(std::chrono::seconds(1));

            lid_open.command(0);
            std::this_thread::sleep_for(std::chrono::seconds(3));
            picked = 0;
            std::this_thread::sleep_for(std::chrono::milliseconds(1500));
            picked = 0;

          }


    // dropping all the cottons at end of every pose





  }
    /* Move joint4 to align with the row, so that height can be changed */
    joint_move_5.move_joint(joint5_homing_position, WAIT);  // TODO(developer) This homing Position is different from Initialisation homing position but both can be same
    std::this_thread::sleep_for(std::chrono::seconds(2));
    joint_move_4.move_joint(joint4_homing_position, WAIT);  // TODO(developer) move it to joint4_homing_position
                std::this_thread::sleep_for(std::chrono::seconds(2));
    joint_move_3.move_joint(joint3_homing_position, WAIT);
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "all joints are in homing_position going for l2 movement");
    // joint_move_2.move_joint(height_scan_value,WAIT);


  if(height_scan_enable ==true)
  {
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "height_scan is enabled, height_scan_value:= %f", height_scan_value);
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "moving to top position");
    joint_move_2.move_joint(height_scan_min,WAIT);
    std::this_thread::sleep_for(std::chrono::seconds(20));
    lid_open.command(1);
    std::this_thread::sleep_for(std::chrono::seconds(5));
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "moving to top position");
    // we are calling the idle for l2 here after moving to a position
    srv_idle->joint_id = 3;
    srv_idle->homing_required = false;
    auto result_idle_end = joint_move::joint_idle_service->async_send_request(srv_idle);
    if (rclcpp::spin_until_future_complete(node, result_idle_end, kHomingWaitTimeout) !=
        rclcpp::FutureReturnCode::SUCCESS)
    {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed - service call timed out");
      problem_indicator_out.command(true);
      return 0;
    }

    auto idle_end_response = result_idle_end.get();
    if (!idle_end_response->success) {
      RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Joint2 idle failed: %s",
        idle_end_response->reason.c_str());
      problem_indicator_out.command(true);
      return 0;
    }



    end_time = currentTimeMillis();
    double time_taken = end_time - start_time;  // converted into milli seconds
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "TIMETO taken by height scan is = %f ", time_taken);
    print_timestamp(" height scan done ");
  }
}

/  // / #####################l2 height_scan_step ##########################  //
// #endif
/* Parking Position */
joint_move_5.move_joint(joint5_parking_pose, WAIT);
joint_move_4.move_joint(joint4_parking_pose, WAIT);
joint_move_3.move_joint(joint3_parking_pose, WAIT);
last_time =currentTimeMillis();



return 0;
}
