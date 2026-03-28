#ifndef COTTON_DETECTION_ROS2__PERFORMANCE_MONITOR_HPP_
#define COTTON_DETECTION_ROS2__PERFORMANCE_MONITOR_HPP_

#include <chrono>
#include <vector>
#include <string>
#include <memory>
#include <mutex>
#include <rclcpp/rclcpp.hpp>

namespace cotton_detection_ros2
{

/**
 * @brief Performance monitoring and benchmarking for cotton detection
 */
class PerformanceMonitor
{
public:
    /**
     * @brief Performance metrics structure
     */
    struct PerformanceMetrics
    {
        double fps = 0.0;
        double avg_latency_ms = 0.0;
        double min_latency_ms = 0.0;
        double max_latency_ms = 0.0;
        double p50_latency_ms = 0.0;
        double p95_latency_ms = 0.0;
        double p99_latency_ms = 0.0;
        double cpu_usage_percent = 0.0;
        size_t memory_usage_mb = 0;
        size_t total_frames_processed = 0;
        std::chrono::steady_clock::time_point start_time;
        std::vector<double> recent_latencies_ms;
    };

    /**
     * @brief Detection mode performance comparison
     */
    struct DetectionModeMetrics
    {
        std::string mode_name;
        PerformanceMetrics metrics;
        double accuracy_score = 0.0;  // Placeholder for future accuracy metrics
    };

    /**
     * @brief Constructor
     * @param node ROS2 node for logging and parameters
     */
    explicit PerformanceMonitor(rclcpp::Node* node);

    /**
     * @brief Start performance monitoring session
     */
    void start_monitoring();

    /**
     * @brief Stop performance monitoring session
     */
    void stop_monitoring();

    /**
     * @brief Record the start of a detection operation
     * @param operation_name Name of the operation (e.g., "hsv_detection", "yolo_detection")
     */
    void start_operation(const std::string& operation_name);

    /**
     * @brief Record the end of a detection operation
     * @param operation_name Name of the operation
     * @param success Whether the operation was successful
     */
    void end_operation(const std::string& operation_name, bool success = true);

    /**
     * @brief Record a complete frame processing cycle
     * @param detection_mode The detection mode used
     * @param num_detections Number of detections found
     */
    void record_frame_processed(const std::string& detection_mode, size_t num_detections);

    /**
     * @brief Get current performance metrics
     * @return Current performance metrics
     */
    PerformanceMetrics get_metrics() const;

    /**
     * @brief Get performance metrics for a specific detection mode
     * @param mode_name Detection mode name
     * @return Metrics for the specified mode
     */
    DetectionModeMetrics get_mode_metrics(const std::string& mode_name) const;

    /**
     * @brief Get all detection mode metrics
     * @return Vector of all mode metrics
     */
    std::vector<DetectionModeMetrics> get_all_mode_metrics() const;

    /**
     * @brief Reset all performance metrics
     */
    void reset_metrics();

    /**
     * @brief Generate performance report
     * @return Formatted performance report string
     */
    std::string generate_report() const;

    /**
     * @brief Enable/disable detailed logging
     * @param enable Whether to enable detailed logging
     */
    void set_detailed_logging(bool enable);

    /**
     * @brief Set maximum number of recent latencies to keep
     * @param max_recent Maximum number of recent measurements
     */
    void set_max_recent_measurements(size_t max_recent);

private:
    rclcpp::Node* node_;
    mutable std::mutex metrics_mutex_;

    PerformanceMetrics global_metrics_;
    std::map<std::string, DetectionModeMetrics> mode_metrics_;
    std::map<std::string, std::chrono::steady_clock::time_point> active_operations_;

    bool detailed_logging_;
    size_t max_recent_measurements_;
    bool monitoring_active_;

    /**
     * @brief Update FPS calculation
     */
    void update_fps();

    /**
     * @brief Calculate CPU usage (simplified)
     * @return CPU usage percentage
     */
    double calculate_cpu_usage() const;

    /**
     * @brief Get current memory usage
     * @return Memory usage in MB
     */
    size_t get_memory_usage() const;

    /**
     * @brief Update latency statistics
     * @param latency_ms New latency measurement
     */
    void update_latency_stats(double latency_ms);

    /**
     * @brief Log performance metrics
     */
    void log_metrics() const;
};

} // namespace cotton_detection_ros2

#endif // COTTON_DETECTION_ROS2__PERFORMANCE_MONITOR_HPP_
