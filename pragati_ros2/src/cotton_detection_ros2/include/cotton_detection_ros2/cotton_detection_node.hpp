#pragma once

#include <atomic>
#include <mutex>
#include <random>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/compressed_image.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <std_msgs/msg/header.hpp>

// Forward declare OpenCV types (heavy includes moved to .cpp to reduce compilation memory)
// This dramatically reduces memory footprint during compilation
namespace cv {
    class Mat;        // Forward declare cv::Mat
    template<typename T> class Point_;  // Forward declare cv::Point_
    typedef Point_<float> Point2f;      // cv::Point2f
    template<typename T> class Scalar_; // Forward declare cv::Scalar_
    typedef Scalar_<double> Scalar;     // cv::Scalar
    template<typename T> class Size_;   // Forward declare cv::Size_
    typedef Size_<int> Size;            // cv::Size
}

// Keep lightweight bridge includes (these are needed)
#include <cv_bridge/cv_bridge.hpp>
#include <image_transport/image_transport.hpp>
#include <tf2_ros/tf2_ros/static_transform_broadcaster.h>
#include <diagnostic_updater/diagnostic_updater.hpp>
#include <rcl_interfaces/msg/set_parameters_result.hpp>
#include <filesystem>
#include <std_srvs/srv/set_bool.hpp>
#include "cotton_detection_msgs/srv/cotton_detection.hpp"
#include "cotton_detection_msgs/msg/cotton_position.hpp"
#include "cotton_detection_msgs/msg/detection_result.hpp"

#include "cotton_detection_ros2/performance_monitor.hpp"
#include "cotton_detection_ros2/async_image_saver.hpp"
#include "cotton_detection_ros2/async_json_logger.hpp"
#include "cotton_detection_ros2/detection_engine.hpp"
#include "cotton_detection_ros2/service_handler.hpp"

// DepthAI camera support (OAK-D Lite) - Phase 1.3 integration
#ifdef HAS_DEPTHAI
#include "cotton_detection_ros2/diagnostics_collector.hpp"
#endif

namespace cotton_detection_ros2
{

/**
 * @brief Cotton Detection ROS2 Node
 *
 * Migrated from ROS1 with enhanced ROS2 features:
 * - Service-based and topic-based communication
 * - Image transport integration
 * - Modern C++ practices
 * - Configurable parameters
 *
 * Detection logic is delegated to DetectionEngine (owns DepthAI pipeline,
 * detection inference, result caching, filtering, image save/draw).
 * Service handling is delegated to ServiceHandler (request processing,
 * calibration, camera control).
 */
class CottonDetectionNode : public rclcpp::Node
{
public:
    explicit CottonDetectionNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());
    ~CottonDetectionNode();

    // Public interface initialization (called after construction)
    void initialize_interfaces();

    // Explicit cleanup before shutdown (ensures DepthAI device is properly released)
    // Called by main() before node destruction to prevent "device in use" errors on restart
    void cleanup_before_shutdown();

    // Shutdown control (public for signal handler access)
    void request_shutdown() { shutdown_requested_.store(true); }
    bool is_shutdown_requested() const { return shutdown_requested_.load(); }

    // Camera error state query (resume/reinit failure tracking)
#ifdef HAS_DEPTHAI
    bool isCameraInError() const { return camera_error_.load(); }
#else
    bool isCameraInError() const { return false; }
#endif

private:
    // === Callback Groups (MultiThreadedExecutor safety) ===
    // detection_group_: detection service callbacks (may block 500ms-12s during inference)
    // monitoring_group_: thermal timer + diagnostics timer (must never be starved)
    rclcpp::CallbackGroup::SharedPtr detection_group_;
    rclcpp::CallbackGroup::SharedPtr monitoring_group_;

    // === ROS2 Interfaces ===

    // Services (enhanced ROS2 service)
    rclcpp::Service<cotton_detection_msgs::srv::CottonDetection>::SharedPtr service_enhanced_;
    rclcpp::Service<std_srvs::srv::SetBool>::SharedPtr service_camera_control_;

    // Publishers
    rclcpp::Publisher<cotton_detection_msgs::msg::DetectionResult>::SharedPtr pub_detection_result_;
    rclcpp::Publisher<sensor_msgs::msg::CompressedImage>::SharedPtr pub_debug_image_;
    rclcpp::Publisher<sensor_msgs::msg::CameraInfo>::SharedPtr pub_camera_info_;

    // Subscribers
    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr sub_camera_image_;
    rclcpp::Subscription<sensor_msgs::msg::CompressedImage>::SharedPtr sub_camera_compressed_;

    // Image transport
    std::shared_ptr<image_transport::ImageTransport> image_transport_;
    image_transport::Subscriber image_sub_;
    image_transport::Publisher debug_image_pub_;

    // TF2 broadcaster for camera transforms
    std::shared_ptr<tf2_ros::StaticTransformBroadcaster> tf_static_broadcaster_;

    // Camera info
    sensor_msgs::msg::CameraInfo camera_info_;

    // Diagnostics
    std::shared_ptr<diagnostic_updater::Updater> diagnostic_updater_;
    rclcpp::TimerBase::SharedPtr diagnostic_timer_;

    // Periodic detection stats logging
    rclcpp::TimerBase::SharedPtr stats_timer_;
    void stats_log_callback();

    // === Service Callbacks (delegated to ServiceHandler) ===
    // handle_cotton_detection, handle_camera_control, process_detection_request,
    // handle_calibration_request, encode_ascii_path, get_timestamped_filename,
    // ensure_directory, export_calibration_via_depthai, export_calibration_via_script
    // all moved to ServiceHandler class.

    // === Image Callbacks ===
    void image_callback(const sensor_msgs::msg::Image::ConstSharedPtr & msg);
    void compressed_image_callback(const sensor_msgs::msg::CompressedImage::ConstSharedPtr & msg);

    // === Detection Logic (delegated to DetectionEngine + ServiceHandler) ===

    // === Utilities ===
    void publish_detection_result(const std::vector<geometry_msgs::msg::Point> & positions, bool success);
    void publish_debug_image(const cv::Mat & image);
    void publish_camera_info();
    void publish_static_transforms();
    cv::Mat convert_ros_image_to_cv(const sensor_msgs::msg::Image::ConstSharedPtr & msg);
    cv::Mat convert_compressed_image_to_cv(const sensor_msgs::msg::CompressedImage::ConstSharedPtr & msg);

    // === Diagnostics ===
    void diagnostic_callback(diagnostic_updater::DiagnosticStatusWrapper & stat);
    void depthai_diagnostic_callback(diagnostic_updater::DiagnosticStatusWrapper & stat);

    // === Configuration ===
    void declare_parameters();
    void load_parameters();
    bool validate_parameters();  // Phase 3.9: Parameter validation
    void configure_performance_monitor();
    rcl_interfaces::msg::SetParametersResult on_parameter_update(const std::vector<rclcpp::Parameter> & params);

    // === Members ===
    std::mutex image_mutex_;
    cv::Mat latest_image_;
    rclcpp::Time latest_image_stamp_{0, 0, RCL_ROS_TIME};  // Track image timestamp for freshness check
    std::atomic<bool> image_available_{false};
    std::atomic<int> consecutive_frame_drops_{0};  // Track consecutive image conversion failures
    static constexpr int kMaxConsecutiveFrameDrops{5};  // ERROR threshold

    // Detection components
    std::unique_ptr<PerformanceMonitor> performance_monitor_;
    std::unique_ptr<DetectionEngine> detection_engine_;
    std::unique_ptr<ServiceHandler> service_handler_;

    // Parameters
    std::string camera_topic_;
    std::string debug_image_topic_;
    bool enable_debug_output_;
    double detection_confidence_threshold_;
    int max_cotton_detections_;

    // Calibration export configuration
    std::string calibration_output_dir_;
    double calibration_timeout_sec_{30.0};
    std::string calibration_script_override_;

    // Coordinate transformation
    double pixel_to_meter_scale_x_;
    double pixel_to_meter_scale_y_;
    double assumed_depth_m_;

    // Performance settings
    double max_processing_fps_;
    int processing_timeout_ms_;
    bool enable_performance_monitoring_;
    bool performance_detailed_logging_;
    bool verbose_timing_;
    int performance_max_recent_measurements_;

    // Workspace bounds (kept in node for DetectionConfig population)
    double workspace_max_x_;
    double workspace_max_y_;
    double workspace_max_z_;
    double workspace_min_z_;
    bool workspace_filter_enabled_{false};

    // Detection state
    std::atomic<bool> detection_active_{false};
    std::atomic<bool> shutdown_requested_{false};  // Signal for graceful shutdown

    // Detection request stats (service-level)
    // Note: First request is warmup from yanthra_move, skip it in stats
    std::atomic<bool> warmup_completed_{false};

    // Node start time for uptime calculation
    std::chrono::steady_clock::time_point node_start_time_;

    // Idle detection (Task 7.6): track last detection request time
    std::chrono::steady_clock::time_point last_request_time_;
    std::atomic<bool> idle_state_{false};
    static constexpr int IDLE_TIMEOUT_SEC = 60;

    // Image saving configuration (kept in node for AsyncImageSaver ownership + params)
    bool save_input_image_{false};
    bool save_output_image_{false};
    bool file_save_mode_timestamp_{false};  // true = timestamped files, false = overwrite
    bool save_async_{false};                // Use async image saver (background thread)
    int save_queue_depth_{3};               // Async saver queue depth
    int save_jpeg_quality_{85};             // JPEG compression quality (0-100)
    bool simulation_mode_{false};           // Simulation mode for hardware-free testing
    std::vector<geometry_msgs::msg::Point> simulated_positions_;  // Configurable sim positions
    double simulation_noise_stddev_{0.005};     // Gaussian noise stddev (meters)
    double simulation_confidence_min_{0.7};     // Min confidence for simulated detections
    double simulation_confidence_max_{0.95};    // Max confidence for simulated detections
    std::atomic<int32_t> simulation_detection_id_counter_{0};  // Sequential detection IDs
    std::mt19937 simulation_rng_;               // Random engine for noise/confidence
    std::string input_dir_;
    std::string output_dir_;
    std::unique_ptr<AsyncImageSaver> async_image_saver_;  // Async saver instance (null if save_async=false)
    std::unique_ptr<AsyncJsonLogger> async_json_logger_;  // Async JSON logger (off hot path)

    // Fallback positions when zero cotton detected
    bool publish_fallback_on_zero_{false};
    std::vector<geometry_msgs::msg::Point> fallback_positions_;

    rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameter_callback_handle_;
    std::mutex parameter_mutex_;

    // DepthAI-specific node-level state (NOT moved to DetectionEngine)
#ifdef HAS_DEPTHAI
    // DiagnosticsCollector (node-level concern)
    cotton_detection::DiagnosticsCollector diagnostics_collector_;

    // Thermal management (node-level — per design D4)
    bool thermal_enable_{true};
    double thermal_check_interval_sec_{5.0};
    double thermal_warning_temp_c_{70.0};
    double thermal_throttle_temp_c_{80.0};
    double thermal_critical_temp_c_{90.0};
    int thermal_throttle_fps_{15};
    double stats_log_interval_sec_{30.0};  // Periodic stats logging (temp + detect stats)

    rclcpp::TimerBase::SharedPtr thermal_timer_;
    std::atomic<int> original_fps_{30};      // Store original FPS before throttling
    std::atomic<bool> is_throttled_{false};  // Track throttle state
    std::atomic<bool> is_paused_{false};     // Track pause state
    std::atomic<bool> camera_error_{false};  // Track camera error state (resume/reinit failed)
    void thermal_check_callback();   // Timer callback for thermal monitoring

    // DepthAI parameter cache (for load_parameters / on_parameter_update)
    bool depthai_enable_{false};
    std::string depthai_model_path_;
    int depthai_num_classes_{1};
    bool depthai_swap_class_labels_{false};
    int depthai_camera_width_{416};
    int depthai_camera_height_{416};
    int depthai_camera_fps_{30};
    float depthai_confidence_threshold_{0.5f};
    double depthai_depth_min_mm_{100.0};
    double depthai_depth_max_mm_{5000.0};
    bool depthai_enable_depth_{true};
    std::string depthai_device_id_;
    int depthai_warmup_seconds_{3};
    int depthai_max_queue_drain_{10};
    bool depthai_flush_before_read_{false};
    bool depthai_keep_aspect_ratio_{true};
    bool depthai_auto_pause_after_detection_{true};
    int depthai_detection_timeout_ms_{500};
    int depthai_stereo_confidence_threshold_{200};
    float depthai_bbox_scale_factor_{0.5f};
    bool depthai_extended_disparity_{true};

    // Stereo advanced tuning (cached for parameter management)
    std::string depthai_spatial_calc_algorithm_{"average"};
    std::string depthai_mono_resolution_{"400p"};
    bool depthai_lr_check_{true};
    bool depthai_subpixel_{false};
    std::string depthai_median_filter_{"7x7"};

    // Exposure control (cached for parameter management)
    std::string exposure_mode_{"auto"};
    int exposure_time_us_{8000};
    int exposure_iso_{400};

    // Border filter (cached for parameter management)
    bool border_filter_enabled_{true};
    float border_margin_{0.05f};
#endif
};

} // namespace cotton_detection_ros2
