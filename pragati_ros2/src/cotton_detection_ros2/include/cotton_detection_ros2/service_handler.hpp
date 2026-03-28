#pragma once

#include <atomic>
#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <random>
#include <string>
#include <vector>

#include <geometry_msgs/msg/point.hpp>
#include <rclcpp/clock.hpp>
#include <rclcpp/logger.hpp>
#include <rclcpp/time.hpp>
#include <std_srvs/srv/set_bool.hpp>

#include "cotton_detection_msgs/srv/cotton_detection.hpp"

// Forward declarations to avoid pulling in heavy headers
namespace cv {
class Mat;
}

namespace cotton_detection {
class DepthAIManager;
}

namespace cotton_detection_ros2 {

class DetectionEngine;
class PerformanceMonitor;

/**
 * @brief Configuration for ServiceHandler.
 *
 * Populated from node parameters at construction time.
 * Contains calibration and simulation parameters that the node
 * previously held as member variables.
 */
struct ServiceConfig {
    // Calibration export configuration
    std::string calibration_output_dir;
    double calibration_timeout_sec{30.0};
    std::string calibration_script_override;

    // Simulation configuration
    bool simulation_mode{false};
    std::vector<geometry_msgs::msg::Point> simulated_positions;
    double simulation_noise_stddev{0.005};
    double simulation_confidence_min{0.7};
    double simulation_confidence_max{0.95};
};

/**
 * @brief Node-level shared state that ServiceHandler needs read/write access to.
 *
 * Passed by reference from the node — ServiceHandler does NOT own these.
 * This avoids a back-pointer to the node while providing necessary state access.
 */
struct NodeInterface {
    // Logging & timing (non-owning)
    rclcpp::Logger logger;
    rclcpp::Clock::SharedPtr clock;

    // Detection components (non-owning)
    DetectionEngine * detection_engine{nullptr};
    PerformanceMonitor * performance_monitor{nullptr};

    // Shared node state (non-owning references)
    std::atomic<bool> & shutdown_requested;
    std::atomic<bool> & detection_active;
    std::chrono::steady_clock::time_point & last_request_time;
    std::atomic<bool> & idle_state;
    std::atomic<bool> & warmup_completed;

    // Image state (non-owning references)
    std::mutex & image_mutex;
    cv::Mat & latest_image;
    rclcpp::Time & latest_image_stamp;
    std::atomic<bool> & image_available;

    // Callback for publishing detection results (stays in node)
    std::function<void(const std::vector<geometry_msgs::msg::Point> &, bool)> publish_result_fn;
};

/**
 * @brief Encapsulates all ROS2 service callback logic.
 *
 * Owns service handler methods previously in `_services.cpp`:
 * - Cotton detection service (handle_cotton_detection, process_detection_request)
 * - Camera control service (handle_camera_control)
 * - Calibration handling (handle_calibration_request, export_calibration_via_depthai,
 *   export_calibration_via_script)
 * - File/path utilities (encode_ascii_path, get_timestamped_filename, ensure_directory)
 *
 * Does NOT contain thermal_check_callback (stays in node per design D4).
 * Does NOT hold a back-pointer to CottonDetectionNode.
 * Dependencies injected via NodeInterface struct.
 *
 * Thread safety: Uses atomics and mutexes from NodeInterface for shared state.
 */
class ServiceHandler {
public:
    /**
     * @brief Construct a ServiceHandler.
     * @param iface  Node interface with all dependencies (non-owning references)
     * @param config  Service configuration (calibration, simulation params)
     */
    ServiceHandler(NodeInterface iface, const ServiceConfig & config);

    ~ServiceHandler();

    // Non-copyable, non-movable (holds references)
    ServiceHandler(const ServiceHandler &) = delete;
    ServiceHandler & operator=(const ServiceHandler &) = delete;

    // === Service Callbacks ===

    /**
     * @brief Handle cotton detection service request.
     * Dispatches to process_detection_request and fills the response.
     */
    void handle_cotton_detection(
        const std::shared_ptr<cotton_detection_msgs::srv::CottonDetection::Request> request,
        std::shared_ptr<cotton_detection_msgs::srv::CottonDetection::Response> response);

    /**
     * @brief Handle camera control service request (pause/resume/start).
     */
    void handle_camera_control(
        const std::shared_ptr<std_srvs::srv::SetBool::Request> request,
        std::shared_ptr<std_srvs::srv::SetBool::Response> response);

    // === Config Access ===
    ServiceConfig & getConfig() { return config_; }
    const ServiceConfig & getConfig() const { return config_; }

private:
    // === Internal Methods ===

    /**
     * @brief Process a detection request (command dispatch).
     * @param command  0=stop, 1=detect, 2=calibrate
     * @param result_data  Output: detection data as int32 triplets
     * @return true if detection succeeded
     */
    bool process_detection_request(int32_t command, std::vector<int32_t> & result_data);

    /**
     * @brief Handle calibration request (command=2).
     */
    bool handle_calibration_request(std::vector<int32_t> & result_data);

    /**
     * @brief Encode a file path as ASCII int32 values.
     */
    std::vector<int32_t> encode_ascii_path(const std::string & path) const;

    /**
     * @brief Generate a timestamped filename.
     */
    std::string get_timestamped_filename(const std::string & prefix, const std::string & extension) const;

    /**
     * @brief Ensure a directory exists (create if needed).
     */
    bool ensure_directory(const std::string & path) const;

    /**
     * @brief Export calibration via DepthAI API.
     */
    bool export_calibration_via_depthai(std::string & exported_to, std::string & status_message);

    /**
     * @brief Export calibration via external Python script.
     */
    bool export_calibration_via_script(std::string & exported_to, std::string & status_message);

    // === Members ===
    NodeInterface iface_;
    ServiceConfig config_;

    // Simulation random engine (owned by ServiceHandler, seeded at construction)
    std::mt19937 simulation_rng_;
};

}  // namespace cotton_detection_ros2
