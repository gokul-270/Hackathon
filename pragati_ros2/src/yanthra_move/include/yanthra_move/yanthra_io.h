// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");

#ifndef YANTHRA_MOVE_YANTHRA_IO_H_
#define YANTHRA_MOVE_YANTHRA_IO_H_
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



/*
   YANTHRA INPUT / OUTPUT - ROS2 Version
 */
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/float32.hpp>
#include <std_msgs/msg/u_int16.hpp>
#include <atomic>

// Conditional pigpio include for Raspberry Pi hardware
#ifdef ENABLE_PIGPIO
#include <pigpiod_if2.h>
#endif  // YANTHRA_MOVE_YANTHRA_IO_H_



#define OPEN  true
#define CLOSE  false
#define START  true
#define STOP  false
#define ON  true
#define OFF  false
#define CLOCK_WISE  true
#define ANTI_CLOCK_WISE  false

// Conditional pigpio variables and classes for Raspberry Pi hardware
#ifdef ENABLE_PIGPIO
extern int pi;
extern unsigned gpio_pin_number;
extern unsigned pulsewidth;

class pi_gpio_control
{
  public:
  unsigned int gpio_pin_number;
  unsigned int gpio_second_pin_number;
  void relay_control(bool status){
    RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "relay control"); // end_effector_clockwise rotation

          if(status == true){
              if(gpio_write(pi,gpio_pin_number,0)!=0)
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Failed to Switch ON the PIN"); // end_effector_clockwise rotation
          }
          if(status == false){
              if(gpio_write(pi,gpio_pin_number,1)!=0) {
                  RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Failed to Switch OFF the PIN"); // end_effector_clockwise rotation
              }
          }
  }

  void servo_control(unsigned pwm){
          // Use parameter instead of global variable
          if(set_servo_pulsewidth(pi, gpio_pin_number, pwm)!=0){
              RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Failed to Switch PWM on  the PIN"); // end_effector_clockwise rotation
          }
  }
};
#endif  // YANTHRA_MOVE_YANTHRA_IO_H_



class d_out
{
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr pub;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr sub;
  std::string output_name;
  rclcpp::Node::SharedPtr node_;

  void callback(const std_msgs::msg::String::SharedPtr msg)
  {
    // Avoid unused parameter warning
    (void)msg;
    //  RCLCPP_INFO(node_->get_logger(), "%s status: %s", output_name.c_str(), msg->data.c_str());
  }
  public:
  void command(bool cmd)
  {
    auto val = std_msgs::msg::Bool();
    val.data = cmd;
    pub->publish(val);
  }
  void command(int cmd)
  {
    auto val = std_msgs::msg::Bool();
    val.data = (cmd != 0);
    pub->publish(val);
  }
  d_out(rclcpp::Node::SharedPtr node, std::string name):
    output_name(name), node_(node)
  {
    pub = node_->create_publisher<std_msgs::msg::Bool>(output_name+"/command", 2);
    // sub = node_->create_subscription<std_msgs::msg::String>(output_name+"/status", 1,
    //  std::bind(&d_out::callback, this, std::placeholders::_1));
  }
};

class a_out
{
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr pub;
  std::string output_name;
  rclcpp::Node::SharedPtr node_;
  public:
  void command(float cmd)
  {
    auto val = std_msgs::msg::Float32();
    val.data = cmd;
    pub->publish(val);
  }
  void command(bool cmd)
  {
    auto val = std_msgs::msg::Float32();
    val.data = cmd ? 1.0f : 0.0f;
    pub->publish(val);
  }
  void command(int cmd)
  {
    auto val = std_msgs::msg::Float32();
    val.data = static_cast<float>(cmd);
    pub->publish(val);
  }
  a_out(rclcpp::Node::SharedPtr node, std::string name):
    output_name(name), node_(node)
  {
    pub = node_->create_publisher<std_msgs::msg::Float32>(output_name+"/command", 2);
  }
};

class d_in
{
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub;
  std::string output_name;
  std::atomic<bool> status{false};
  rclcpp::Node::SharedPtr node_;

  void callback(const std_msgs::msg::Bool::SharedPtr msg)
  {
    status.store(msg->data, std::memory_order_relaxed);
    //  RCLCPP_INFO(node_->get_logger(), "%s status: %d", output_name.c_str(), status);
  }
  public:
  bool state(void)
  {
    // Atomically exchange status with false — returns previous value
    return status.exchange(false, std::memory_order_relaxed);
  }
  d_in(rclcpp::Node::SharedPtr node, std::string name):
    output_name(name), node_(node)
  {
    sub = node_->create_subscription<std_msgs::msg::Bool>(output_name+"/state", 1,
      std::bind(&d_in::callback, this, std::placeholders::_1));
  }
};

class servo_out
{
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr pub_;
  std::string output_name_;
  double pos_;
  double min_;
  double max_;
  rclcpp::Node::SharedPtr node_;
  public:
  void init(void)
  {
    pos_ = 0.000;

    RCLCPP_WARN(node_->get_logger(), "%s: Initialisation", output_name_.c_str());
    auto value = std_msgs::msg::Float32();
    value.data = min_;
    pub_->publish(value);
  }
  bool move(double val)
  {
    if(val == 0)
      return false;
    if(pos_ >= max_)
      return false;

    RCLCPP_WARN(node_->get_logger(), "%s: Present Position: %lf", output_name_.c_str(), pos_);
    pos_ += val;
    auto value = std_msgs::msg::Float32();
    value.data = (val*1000);
    pub_->publish(value);
    return true;
  }


  servo_out(rclcpp::Node::SharedPtr node, std::string name,
      double min,
      double max)
    : output_name_(name),
    min_(min),
    max_(max),
    node_(node)
  {
    pub_ = node_->create_publisher<std_msgs::msg::Float32>(output_name_, 2);
    pos_ = 0.0;
  }
};

#endif  // YANTHRA_MOVE_YANTHRA_IO_H_
