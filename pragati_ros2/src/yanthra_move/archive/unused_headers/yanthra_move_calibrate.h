// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");

#ifndef YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_
#define YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http:// www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


/* ARM Movement Configuration */

/* Movement config for different modes.
 *
 *                     Calibration Mode    Test140 Mode    Switch Control Mode
 *                     ----------------    ------------    -------------------
 * AGGREGATE_PICK_EN          f                 t                   t
 * BREAD_BOARD                f                 f                   f
 * CAMERA_EN                  f                 f                   t
 * END_EFFECTOR_EN            f                 t                   t
 * HEIGHT_SCAN_EN             t                 t                   t
 * JOINT5_INIT_EN             f                 f                   f
 * MOVE_EN                    f                 f                   f
 * SHUTDOWN_SWITCH_EN         f                 t                   t
 * START_SWITCH_EN            f                 t                   t
 * UBUNTU_SHUTDWON_EN         f                 t                   t
 *
 */

/* Default enable for all modes */
// #define HEIGHT_SCAN_EN      true   // commmented out by ribin since it moved to yaml file

/* For CALIBRATION the operation is only manual and automatic operation using
 * start_switch and shutdown_switch should be disabled.
 */
#if CALIBRATIONMODE == true
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_

#if TEST140MODE == true
#define AGGREGATE_PICK_EN    true
#define END_EFFECTOR_EN     true
#define SHUTDOWN_SWITCH_EN  true
#define START_SWITCH_EN     true
#define UBUNTU_SHUTDWON_EN  true
// #define MOVE_EN              true
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_

/* For Switch control mode the start_switch and shutdown switch has to be
 * enabled.
 */
#if SWITCHCONTROLMODE == true
#define AGGREGATE_PICK_EN    true
#define CAMERA_EN           true
#define END_EFFECTOR_EN     true
#define SHUTDOWN_SWITCH_EN  true
#define START_SWITCH_EN     true
#define UBUNTU_SHUTDWON_EN  true
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_

/* For Joint 2
#if HEIGHT_SCAN_EN == true
  double height_scan_min;    // commmented out by ribin since it moved to yanthra_move.cpp and yaml
  double height_scan_max;
  double height_scan_step;
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_

/* For Joint 3 */
#define PHI_MIN (-0.785398)                 // PHI_MIN is set as  0 radians
#define PHI_MAX (1.570795)          // PHI_MAX is set as 1.570795 radians which is 90 degrees
double joint3_parking_pose;
double joint3_homing_position ;

/* For Joint 4 */
#define THETA_MIN  (-2.3561925)  // -135 deg TODO URDF limit is -110 deg
#define THETA_MAX  (2.3561925)   // 135 deg  TODO URDF limit is +110 deg
double joint4_parking_pose;
double joint4_homing_position ;
bool joint4_multiple_zero_pose;
std::vector<double> joint4_zero_poses;

/* For Joint 5 */
double joint5_parking_pose;
double joint5_homing_position ;

double end_effector_len = 0.049; // Four Roller End Effector Length=49 mm // Non Roller Length=81 mm // Cam with Roller=99mm // calibration pointer length =95 mm
double link5_min_length = 0.295;
double link5_max_length = 0.620;

#if END_EFFECTOR_EN == true
#define LINK5_MAX_LENGTH  (link5_max_length + end_effector_len)
#define LINK5_MIN_LENGTH  (link5_min_length + end_effector_len)
#else
#define LINK5_MAX_LENGTH  (link5_max_length)
#define LINK5_MIN_LENGTH  (link5_min_length)
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_
#define LINK5_LENGTH    (link5_max_length - link5_min_length)


/* TO CHANGE SPEED OF THE JOINT5 using the following computation.
   CHANGING JOINT5_SPEED means the value of joint5_speed in the file  vacuum_valve.ino used in the arduino hardware to control the start and stop time of the END effector */

/* 0.55m/s is computed Using motor Speed of 105000 count/sec which is equivalent to 105000/(8192) =12.81 rps and in rpm of 769 ,gear ratio is 5.5 so motor speed is 140 rpm which is equivalent to 140*0.24/(60)=0.55 metre/s.Here 0.24 is the lead of the link5*/

#define JOINT5_SPEED    (0.55)

/* 1.066   m/s is computed Using motor Speed of 200125 count/sec which is equivalent to 200125 /(8192) = 24.429 rps and in RPM of 1465.7592 ,gear ratio is 5.5 so motor speed is 266.501 rpm which is equivalent to 266.501*0.24/(60)=1.066 metre/s.Here 0.24 is the lead of the link5*/

/* Configuration Parameters */
bool continous_operation = true;
float picking_delay;
float pre_start_len;

/* Cartisian to Spherical coordinates

  |Y     .p
  |     /
  |    /
  |   /
  |  /
  | /
  |/________X

Link2 angle is theta i.e. Horizontal
Link4 angle is phi i.e. Vertical

*/
void xyz_to_polar(double x, double y, double z, double* r, double* theta, double* phi)
{
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Input x=%lf, y=%lf, z=%lf", x, y, z);
  *r = sqrt(x*x + y*y + z*z);
  *phi = asin(y / sqrt(y*y + z*z));
  *theta = asin(x / sqrt(x*x + z*z));
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Output R=%lf, Theta=%lf, Phi=%lf", *r, *theta, *phi);
}

bool check_reachability(double r, double theta, double phi)
{
  bool status = false;
  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "LINK_5_MAX_LENGTH _for debug =%f",link5_max_length);
  if((r > LINK5_MAX_LENGTH) || (r < LINK5_MIN_LENGTH))
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "R is out of bound ");
  else if((theta < THETA_MIN) || (theta > THETA_MAX)){
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Theta is out of bound");
          RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "theta min =%f",THETA_MIN);
                RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "theta max =%f",THETA_MAX);
  }
  else if((phi < PHI_MIN) || (phi > PHI_MAX)){
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Phi is out of bound");
          RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "phi min =%f",PHI_MIN);
                RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "phi max =%f",PHI_MAX);
  }
  else
    status = true;

  return status;
}

/* Read the coordinates from file, created by image processing software*/
/*void get_cotton_coordinates(std::vector<geometry_msgs::msg::Point> *positions)
{
  std::string path;
#if CALIBRATIONMODE == true
  path = CALIBRATION_MODE_DATA_DIR;
#elif TEST140MODE == true
  path = TEST140_MODE_DATA_DIR;
#else
  path = YANTHRA_DATA_OUTPUT_DIR;
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_
  std::string cotton_coordinates_file = path + "/cotton_details.txt";

  RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Cotton Coordinates from %s", cotton_coordinates_file.c_str());
  std::ifstream cotton_fs(cotton_coordinates_file);
  float tmp, point_3d_x, point_3d_y, point_3d_z;
  geometry_msgs::msg::Point pos;

  positions->clear();
  while(cotton_fs >> tmp >> tmp >> point_3d_x >> point_3d_y >> point_3d_z)
  {
    std::cout <<point_3d_x << " " << point_3d_y << " " << point_3d_z << std::endl;
    pos.x = point_3d_x;
    pos.y = point_3d_y;
    pos.z = point_3d_z;
    positions->push_back(pos);
  }
#if CAMERA_EN == true
  // Pragati_Pending: We need to see if this new line is really required.
  std::string echo_newline = "echo > " + cotton_coordinates_file;
  system(echo_newline.c_str());
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_
}
*/

void getCottonCoordinates_cameraToLink3(std::shared_ptr<tf2_ros::Buffer> tf_buffer,
                    std::vector<geometry_msgs::msg::Point> *positions,
                    std::vector<geometry_msgs::msg::PointStamped> *positions_baseLink)
{
  geometry_msgs::msg::PointStamped position_in, position_out;

  positions_baseLink->clear();
  for(std::vector<geometry_msgs::msg::Point>::iterator it = positions->begin(); it != positions->end(); it++)
  {
    position_in.header.frame_id = "/camera_depth_optical_frame";
    position_in.point = *it;
    tf2::doTransform(position_in, position_out, tf_buffer->lookupTransform("link3", "camera_depth_optical_frame", tf2::TimePointZero));
    positions_baseLink->push_back(position_out);

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Camera to Link3\n Input x=%lf, y=%lf, z=%lf\n Output x=%lf, y=%lf, z=%lf\n",
         it->x, it->y, it->z, position_out.point.x, position_out.point.y, position_out.point.z);
  }
}


void getCottonCoordinates_ToLink3(std::vector<geometry_msgs::msg::Point> *positions,
                  std::vector<geometry_msgs::msg::PointStamped> *positions_baseLink)
{
  geometry_msgs::msg::PointStamped position_out;

  positions_baseLink->clear();
  for(std::vector<geometry_msgs::msg::Point>::iterator it = positions->begin(); it != positions->end(); it++)
  {
    position_out.point = *it;
    positions_baseLink->push_back(position_out);
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Camera to Link3\n Input x=%lf, y=%lf, z=%lf\n Output x=%lf, y=%lf, z=%lf\n",
         it->x, it->y, it->z, position_out.point.x, position_out.point.y, position_out.point.z);
  }
}

void record_debug_data(void)
{
  char datecode[80];
  std::stringstream copy_command;
  // Pragati_Pending (Ribin): We need to write a common library routine which
  // gives us all the paths for temporary files.
  std::string path;
#if CALIBRATIONMODE == true
  path = CALIBRATION_MODE_DATA_DIR;
#elif TEST140MODE == true
  path = TEST140_MODE_DATA_DIR;
#else
  path = YANTHRA_DATA_OUTPUT_DIR;
#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_

  std::time_t t = std::time(NULL);
  std::strftime(datecode, 80, "%Y_%m_%d_%H_%M_%S", std::localtime(&t));

  copy_command.str("");
  copy_command << "cp " YANTHRA_DATA_OUTPUT_DIR "/img106.jpg " << path + "debug/" << datecode << "_img100.jpg";
  system(copy_command.str().c_str());

  copy_command.str("");
  copy_command << "cp " YANTHRA_DATA_OUTPUT_DIR "/img107.jpg " << path + "debug/" << datecode << "_img101.jpg";
  system(copy_command.str().c_str());

  copy_command.str("");
  copy_command << "cp " YANTHRA_DATA_OUTPUT_DIR "/img108.jpg " << path + "debug/" << datecode << "_img102.jpg";
  system(copy_command.str().c_str());

  copy_command.str("");
  copy_command << "cp " YANTHRA_DATA_OUTPUT_DIR "/img109.jpg " << path + "debug/" << datecode << "_img103.jpg";
  system(copy_command.str().c_str());

  copy_command.str("");
  copy_command << "cp " YANTHRA_DATA_OUTPUT_DIR "/points.pcd " << path + "debug/" << datecode << "_points100.pcd";
  system(copy_command.str().c_str());

  copy_command.str("");
  copy_command << "cp " YANTHRA_DATA_OUTPUT_DIR "/cotton_result.jpg " << path + "debug/" << datecode << "_cotton_result.jpg";
  system(copy_command.str().c_str());
}

#endif  // YANTHRA_MOVE_YANTHRA_MOVE_CALIBRATE_H_
