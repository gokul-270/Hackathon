/**
 * @file cotton_detection_node_main.cpp
 * @brief Main entry point for Cotton Detection Node
 *
 * Extracted from cotton_detection_node.cpp to improve build performance and maintainability.
 * Contains: main() function with proper signal handling for DepthAI cleanup
 */

#include "cotton_detection_ros2/cotton_detection_node.hpp"
#include "common_utils/signal_handler.hpp"
#include <rclcpp/rclcpp.hpp>
#include <chrono>
#include <thread>

// === Main Function ===
int main(int argc, char ** argv)
{
    // Initialize ROS2 without default signal handlers
    rclcpp::InitOptions init_options;
    init_options.shutdown_on_signal = false;
    rclcpp::init(argc, argv, init_options);

    // Install shared signal handlers (SIGINT + SIGTERM set atomic flag)
    pragati::install_signal_handlers(true);  // enable SIGSEGV/SIGABRT backtrace

    auto node = std::make_shared<cotton_detection_ros2::CottonDetectionNode>();

#ifdef HAS_DEPTHAI
    RCLCPP_INFO(node->get_logger(), "Build: HAS_DEPTHAI=1 (DepthAI C++ enabled)");
#else
    RCLCPP_ERROR(node->get_logger(), "Build: HAS_DEPTHAI=0 (DepthAI C++ DISABLED) - this build is unsupported");
#endif

    // Initialize ROS2 interfaces after node is fully constructed
    node->initialize_interfaces();

    RCLCPP_INFO(node->get_logger(), "Cotton Detection ROS2 Node Started");

    // Use MultiThreadedExecutor(2) so monitoring timers (thermal, diagnostics)
    // are never starved by long-running detection inference (500ms-12s).
    // The node's callback groups (detection_group_, monitoring_group_) ensure
    // mutual exclusion within each group while allowing cross-group concurrency.
    rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 2);
    executor.add_node(node);

    // Run executor in background thread to preserve multi-threaded behavior.
    // Main thread polls shutdown flag instead of relying on unsafe
    // rclcpp::shutdown() from signal handler.
    auto spin_thread = std::thread([&executor]() {
        executor.spin();
    });

    while (rclcpp::ok() && !pragati::shutdown_requested()) {
        // BLOCKING_SLEEP_OK: shutdown poll 100ms, main thread (not executor) — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    // Stop executor from main thread (safe - not in signal handler)
    executor.cancel();
    spin_thread.join();

    // CRITICAL: Signal DepthAI to stop blocking operations, then clean up
    RCLCPP_INFO(node->get_logger(), "Shutdown requested - cleaning up DepthAI...");
    node->request_shutdown();
    node->cleanup_before_shutdown();

    // Now safe to destroy node and shutdown ROS2
    node.reset();

    if (rclcpp::ok()) {
        rclcpp::shutdown();
    }

    return 0;
}
