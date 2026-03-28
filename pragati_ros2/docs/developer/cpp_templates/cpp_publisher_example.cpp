/**
 * @file cpp_publisher_example.cpp
 * @brief Example ROS2 C++ publisher with best practices
 * 
 * Demonstrates:
 * - Efficient message publishing
 * - QoS configuration
 * - Rate limiting
 * - Publisher lifecycle management
 */

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/string.hpp>
#include <chrono>
#include <memory>

using namespace std::chrono_literals;

/**
 * @brief Example publisher node
 */
class ExamplePublisher : public rclcpp::Node
{
public:
  ExamplePublisher()
  : Node("example_publisher"),
    count_(0)
  {
    // Declare parameters
    this->declare_parameter<std::string>("topic_name", "example_topic");
    this->declare_parameter<double>("publish_rate_hz", 10.0);
    this->declare_parameter<int>("queue_size", 10);
    
    // Get parameters
    std::string topic_name = this->get_parameter("topic_name").as_string();
    double rate_hz = this->get_parameter("publish_rate_hz").as_double();
    int queue_size = this->get_parameter("queue_size").as_int();
    
    // Configure QoS
    auto qos = rclcpp::QoS(rclcpp::KeepLast(queue_size))
      .reliable()              // or .best_effort() for real-time
      .durability_volatile();  // or .transient_local() to cache messages
    
    // Create publisher
    publisher_ = this->create_publisher<std_msgs::msg::String>(topic_name, qos);
    
    // Setup timer for periodic publishing
    auto timer_period = std::chrono::duration<double>(1.0 / rate_hz);
    timer_ = this->create_wall_timer(
      timer_period,
      std::bind(&ExamplePublisher::timer_callback, this)
    );
    
    RCLCPP_INFO(
      this->get_logger(),
      "Publisher initialized: topic=%s, rate=%.1f Hz",
      topic_name.c_str(),
      rate_hz
    );
  }

private:
  /**
   * @brief Timer callback - publishes messages at fixed rate
   */
  void timer_callback()
  {
    // Create message
    auto message = std_msgs::msg::String();
    message.data = "Message " + std::to_string(count_++);
    
    // Publish message
    publisher_->publish(message);
    
    // Optional: Log at reduced rate to avoid spam
    if (count_ % 50 == 0) {
      RCLCPP_INFO(this->get_logger(), "Published %zu messages", count_);
    }
  }
  
  // Member variables
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
  size_t count_;
};

/**
 * @brief Advanced example with pre-allocated messages
 */
class OptimizedPublisher : public rclcpp::Node
{
public:
  OptimizedPublisher()
  : Node("optimized_publisher")
  {
    // Configure QoS for real-time performance
    auto qos = rclcpp::QoS(rclcpp::KeepLast(1))
      .best_effort()           // Low latency
      .durability_volatile();  // No history
    
    publisher_ = this->create_publisher<sensor_msgs::msg::JointState>("joint_states", qos);
    
    // Pre-allocate message to avoid runtime allocation
    message_ = std::make_unique<sensor_msgs::msg::JointState>();
    message_->name = {"joint_1", "joint_2", "joint_3"};
    message_->position.resize(3);
    message_->velocity.resize(3);
    message_->effort.resize(3);
    
    // High-frequency timer (100 Hz)
    timer_ = this->create_wall_timer(
      10ms,
      std::bind(&OptimizedPublisher::publish_joint_states, this)
    );
    
    RCLCPP_INFO(this->get_logger(), "Optimized publisher ready (100 Hz)");
  }

private:
  /**
   * @brief Publish joint states efficiently
   */
  void publish_joint_states()
  {
    // Update message (reuse allocated memory)
    auto now = this->now();
    message_->header.stamp = now;
    message_->header.frame_id = "base_link";
    
    // Simulate sensor readings
    for (size_t i = 0; i < 3; ++i) {
      message_->position[i] = std::sin(now.seconds() + i);
      message_->velocity[i] = std::cos(now.seconds() + i);
      message_->effort[i] = 0.1 * i;
    }
    
    // Publish (no memory allocation in hot path)
    publisher_->publish(*message_);
  }
  
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::unique_ptr<sensor_msgs::msg::JointState> message_;
};

/**
 * @brief Main function
 */
int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  
  // Choose which example to run
  bool use_optimized = false;  // Set to true for optimized version
  
  if (use_optimized) {
    auto node = std::make_shared<OptimizedPublisher>();
    rclcpp::spin(node);
  } else {
    auto node = std::make_shared<ExamplePublisher>();
    rclcpp::spin(node);
  }
  
  rclcpp::shutdown();
  return 0;
}

/**
 * @example Basic usage:
 * 
 * ```bash
 * # Run publisher
 * ros2 run <package> example_publisher
 * 
 * # Monitor published messages
 * ros2 topic echo /example_topic
 * 
 * # Check publish rate
 * ros2 topic hz /example_topic
 * ```
 * 
 * @example With parameters:
 * 
 * ```bash
 * ros2 run <package> example_publisher --ros-args \
 *   -p topic_name:=/my_topic \
 *   -p publish_rate_hz:=50.0 \
 *   -p queue_size:=20
 * ```
 * 
 * @example In launch file:
 * 
 * ```python
 * Node(
 *     package='<package>',
 *     executable='example_publisher',
 *     name='my_publisher',
 *     parameters=[{
 *         'topic_name': '/robot/status',
 *         'publish_rate_hz': 30.0,
 *         'queue_size': 10
 *     }],
 *     remappings=[
 *         ('example_topic', '/remapped_topic')
 *     ]
 * )
 * ```
 * 
 * @note For real-time performance:
 * - Use .best_effort() QoS
 * - Pre-allocate messages
 * - Avoid logging in hot paths
 * - Use fixed-size containers
 */
