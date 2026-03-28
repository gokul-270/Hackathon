/**
 * @file cpp_service_client_example.cpp
 * @brief Example ROS2 C++ service client with best practices
 * 
 * This example demonstrates:
 * - Synchronous and asynchronous service calls
 * - Timeout handling
 * - Error recovery
 * - Connection monitoring
 */

#include <rclcpp/rclcpp.hpp>
#include <std_srvs/srv/set_bool.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <memory>
#include <chrono>

using namespace std::chrono_literals;
using SetBool = std_srvs::srv::SetBool;
using Trigger = std_srvs::srv::Trigger;

/**
 * @brief Example service client node
 */
class ExampleServiceClient : public rclcpp::Node
{
public:
  ExampleServiceClient()
  : Node("example_service_client")
  {
    // Declare parameters
    this->declare_parameter<std::string>("service_name", "/example_service");
    this->declare_parameter<double>("timeout_sec", 5.0);
    
    std::string service_name = this->get_parameter("service_name").as_string();
    timeout_ = std::chrono::duration<double>(this->get_parameter("timeout_sec").as_double());
    
    // Create service client
    client_ = this->create_client<SetBool>(service_name);
    
    RCLCPP_INFO(this->get_logger(), "Service client created for: %s", service_name.c_str());
  }
  
  /**
   * @brief Call service synchronously (blocking)
   * @param data Request data
   * @return true if successful, false otherwise
   */
  bool call_service_sync(bool data)
  {
    // Wait for service to be available
    if (!wait_for_service()) {
      return false;
    }
    
    // Create request
    auto request = std::make_shared<SetBool::Request>();
    request->data = data;
    
    // Call service (blocking)
    try {
      auto result = client_->async_send_request(request);
      
      // Wait for result with timeout
      auto status = result.wait_for(timeout_);
      
      if (status == std::future_status::ready) {
        auto response = result.get();
        RCLCPP_INFO(
          this->get_logger(),
          "Service call succeeded: %s (message: %s)",
          response->success ? "true" : "false",
          response->message.c_str()
        );
        return response->success;
      } else {
        RCLCPP_ERROR(this->get_logger(), "Service call timed out after %.1f seconds", 
                    std::chrono::duration<double>(timeout_).count());
        return false;
      }
    } catch (const std::exception & e) {
      RCLCPP_ERROR(this->get_logger(), "Service call failed: %s", e.what());
      return false;
    }
  }
  
  /**
   * @brief Call service asynchronously (non-blocking)
   * @param data Request data
   */
  void call_service_async(bool data)
  {
    // Wait for service to be available
    if (!wait_for_service()) {
      return;
    }
    
    // Create request
    auto request = std::make_shared<SetBool::Request>();
    request->data = data;
    
    // Call service asynchronously
    client_->async_send_request(
      request,
      std::bind(&ExampleServiceClient::response_callback, this, std::placeholders::_1)
    );
    
    RCLCPP_INFO(this->get_logger(), "Async service call initiated");
  }

private:
  /**
   * @brief Wait for service to become available
   * @return true if service available, false if timeout
   */
  bool wait_for_service()
  {
    RCLCPP_INFO(this->get_logger(), "Waiting for service...");
    
    if (!client_->wait_for_service(timeout_)) {
      RCLCPP_ERROR(
        this->get_logger(),
        "Service not available after waiting %.1f seconds",
        std::chrono::duration<double>(timeout_).count()
      );
      return false;
    }
    
    RCLCPP_INFO(this->get_logger(), "Service available");
    return true;
  }
  
  /**
   * @brief Callback for async service response
   * @param future Future containing the response
   */
  void response_callback(rclcpp::Client<SetBool>::SharedFuture future)
  {
    try {
      auto response = future.get();
      RCLCPP_INFO(
        this->get_logger(),
        "Async response received: %s (message: %s)",
        response->success ? "true" : "false",
        response->message.c_str()
      );
      
      if (!response->success) {
        RCLCPP_WARN(this->get_logger(), "Service request was unsuccessful");
      }
    } catch (const std::exception & e) {
      RCLCPP_ERROR(this->get_logger(), "Exception in response callback: %s", e.what());
    }
  }
  
  // Member variables
  rclcpp::Client<SetBool>::SharedPtr client_;
  std::chrono::duration<double> timeout_;
};

/**
 * @brief Main function demonstrating both sync and async usage
 */
int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  
  auto node = std::make_shared<ExampleServiceClient>();
  
  // Example 1: Synchronous call
  RCLCPP_INFO(node->get_logger(), "=== Testing Synchronous Call ===");
  bool sync_result = node->call_service_sync(true);
  RCLCPP_INFO(node->get_logger(), "Sync call result: %s", sync_result ? "SUCCESS" : "FAILURE");
  
  // Example 2: Asynchronous call
  RCLCPP_INFO(node->get_logger(), "=== Testing Asynchronous Call ===");
  node->call_service_async(false);
  
  // Spin to process async callback
  rclcpp::spin_some(node);
  
  // Give async call time to complete
  rclcpp::sleep_for(1s);
  rclcpp::spin_some(node);
  
  rclcpp::shutdown();
  return 0;
}

/**
 * @example Usage in your code:
 * 
 * ```cpp
 * // Create node
 * auto client_node = std::make_shared<ExampleServiceClient>();
 * 
 * // Synchronous call (blocks until response or timeout)
 * bool result = client_node->call_service_sync(true);
 * 
 * // Asynchronous call (returns immediately, callback later)
 * client_node->call_service_async(false);
 * rclcpp::spin(client_node);  // Process callbacks
 * ```
 * 
 * @example Error handling:
 * 
 * ```cpp
 * try {
 *     if (!client_node->call_service_sync(true)) {
 *         // Handle service failure
 *         RCLCPP_ERROR(logger, "Service call failed");
 *     }
 * } catch (const std::exception& e) {
 *     RCLCPP_ERROR(logger, "Exception: %s", e.what());
 * }
 * ```
 * 
 * @example Launch:
 * 
 * ```bash
 * # Run client
 * ros2 run <package> example_service_client
 * 
 * # Test with CLI
 * ros2 service call /example_service std_srvs/srv/SetBool "{data: true}"
 * ```
 */
