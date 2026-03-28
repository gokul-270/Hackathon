/**
 * @file cpp_subscriber_example.cpp
 * @brief Example ROS2 C++ subscriber demonstrating best practices
 * 
 * This example shows:
 * - Proper node initialization
 * - Type-safe message handling
 * - QoS configuration
 * - Lifecycle management
 * - Error handling
 */

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/string.hpp>
#include <memory>
#include <chrono>

using namespace std::chrono_literals;

/**
 * @brief Example subscriber node with best practices
 */
class ExampleSubscriber : public rclcpp::Node
{
public:
  /**
   * @brief Constructor - initializes node and subscriptions
   */
  ExampleSubscriber()
  : Node("example_subscriber"),
    message_count_(0)
  {
    // Declare parameters with defaults
    this->declare_parameter<std::string>("topic_name", "example_topic");
    this->declare_parameter<int>("queue_size", 10);
    
    // Get parameters
    std::string topic_name = this->get_parameter("topic_name").as_string();
    int queue_size = this->get_parameter("queue_size").as_int();
    
    // Configure QoS profile
    auto qos = rclcpp::QoS(rclcpp::KeepLast(queue_size))
      .reliable()  // or .best_effort() for real-time data
      .durability_volatile();  // or .transient_local() for late joiners
    
    // Create subscription
    subscription_ = this->create_subscription<std_msgs::msg::String>(
      topic_name,
      qos,
      std::bind(&ExampleSubscriber::message_callback, this, std::placeholders::_1)
    );
    
    RCLCPP_INFO(this->get_logger(), "Subscriber initialized on topic: %s", topic_name.c_str());
    
    // Optional: Setup timer for periodic tasks
    timer_ = this->create_wall_timer(
      1s,
      std::bind(&ExampleSubscriber::timer_callback, this)
    );
  }

private:
  /**
   * @brief Callback for received messages
   * @param msg Received message
   */
  void message_callback(const std_msgs::msg::String::SharedPtr msg)
  {
    // Process message
    RCLCPP_INFO(this->get_logger(), "Received: '%s'", msg->data.c_str());
    
    message_count_++;
    last_message_time_ = this->now();
    
    // Example: Error handling
    if (msg->data.empty()) {
      RCLCPP_WARN(this->get_logger(), "Received empty message");
      return;
    }
    
    // Example: Processing logic
    process_message(msg);
  }
  
  /**
   * @brief Process received message
   * @param msg Message to process
   */
  void process_message(const std_msgs::msg::String::SharedPtr msg)
  {
    // Your processing logic here
    // Example: Parse, validate, transform, publish results
  }
  
  /**
   * @brief Timer callback for periodic tasks
   */
  void timer_callback()
  {
    // Example: Log statistics
    RCLCPP_INFO(
      this->get_logger(),
      "Messages received: %zu, Last message: %.2f seconds ago",
      message_count_,
      (this->now() - last_message_time_).seconds()
    );
    
    // Example: Watchdog - detect stale data
    if ((this->now() - last_message_time_).seconds() > 5.0) {
      RCLCPP_WARN_THROTTLE(
        this->get_logger(),
        *this->get_clock(),
        5000,  // 5 seconds
        "No messages received for >5 seconds"
      );
    }
  }
  
  // Member variables
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
  rclcpp::TimerBase::SharedPtr timer_;
  size_t message_count_;
  rclcpp::Time last_message_time_;
};

/**
 * @brief Main function
 */
int main(int argc, char * argv[])
{
  // Initialize ROS2
  rclcpp::init(argc, argv);
  
  // Create node
  auto node = std::make_shared<ExampleSubscriber>();
  
  // Spin (process callbacks)
  try {
    rclcpp::spin(node);
  } catch (const std::exception & e) {
    RCLCPP_ERROR(node->get_logger(), "Exception in spin: %s", e.what());
  }
  
  // Cleanup
  rclcpp::shutdown();
  return 0;
}

/**
 * @example Launch this node:
 * 
 * ```bash
 * ros2 run <package_name> example_subscriber --ros-args -p topic_name:=/my_topic
 * ```
 * 
 * @example With remapping:
 * 
 * ```bash
 * ros2 run <package_name> example_subscriber --ros-args -r example_topic:=/remapped_topic
 * ```
 * 
 * @example In launch file:
 * 
 * ```python
 * from launch import LaunchDescription
 * from launch_ros.actions import Node
 * 
 * def generate_launch_description():
 *     return LaunchDescription([
 *         Node(
 *             package='<package_name>',
 *             executable='example_subscriber',
 *             name='my_subscriber',
 *             parameters=[{
 *                 'topic_name': '/my_topic',
 *                 'queue_size': 20
 *             }],
 *             output='screen'
 *         )
 *     ])
 * ```
 */
