#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <geometry_msgs/msg/point.hpp>
#include <rclcpp/time.hpp>

#include "cotton_detection_ros2/logging_types.hpp"

// Forward declarations to avoid pulling in heavy headers
namespace cv {
class Mat;
}

namespace cotton_detection {
class DepthAIManager;
class ThermalGuard;
struct CameraConfig;
}  // namespace cotton_detection

namespace cotton_detection_ros2 {

class PerformanceMonitor;
class AsyncImageSaver;
class AsyncJsonLogger;

/**
 * @brief Detection result with confidence and bounding box.
 *
 * Moved from CottonDetectionNode (was inside #ifdef HAS_DEPTHAI).
 * Now always available — methods that use it are still guarded.
 */
struct DepthAIDetectionResult {
    geometry_msgs::msg::Point position;
    float confidence{0.0f};
    int label{0};  // Class ID (0=cotton, 1=not_pickable)
    // Normalized bounding box coordinates [0, 1]
    float x_min{0.0f};
    float y_min{0.0f};
    float x_max{0.0f};
    float y_max{0.0f};
};

/**
 * @brief Lightweight struct for zero-spatial rejected detections.
 *
 * Holds only the data needed for drawing diagnostic annotations on output
 * images.  Pixel-space bbox coordinates (already scaled from normalized
 * DepthAI values) so the drawing function does not need image dimensions.
 */
struct RejectedDetection {
    int x1{0};              // Pixel-space bbox left
    int y1{0};              // Pixel-space bbox top
    int x2{0};              // Pixel-space bbox right
    int y2{0};              // Pixel-space bbox bottom
    float confidence{0.0f};
    int label{0};
};

/**
 * @brief Read-only snapshot of detection statistics.
 *
 * Returned by DetectionEngine::getStats() for observability.
 * All values are point-in-time snapshots of atomic counters.
 */
struct DetectionStats {
    uint64_t total_detect_requests{0};
    uint64_t total_detect_success{0};
    uint64_t total_positions_returned{0};
    uint64_t total_detections_with_cotton{0};
    uint64_t total_border_filtered{0};
    uint64_t total_non_pickable_filtered{0};
    uint64_t total_workspace_filtered{0};
    uint64_t total_cache_hits{0};
    uint64_t total_cache_misses{0};
    uint64_t total_reconnects{0};
    uint64_t total_downtime_ms{0};
    uint64_t total_sync_mismatches{0};
    uint64_t frame_wait_total_ms{0};
    uint64_t frame_wait_count{0};
    uint64_t frame_wait_max_ms{0};
    int consecutive_detection_timeouts{0};
    int consecutive_rgb_timeouts{0};
    std::chrono::steady_clock::time_point last_successful_detection_time;
};

/**
 * @brief Configuration for DetectionEngine.
 *
 * Populated from node parameters at construction time.
 */
struct DetectionConfig {
    // Detection confidence
    double detection_confidence_threshold{0.5};

    // Workspace bounds
    double workspace_max_x{1.0};
    double workspace_max_y{0.5};
    double workspace_max_z{0.5};
    double workspace_min_z{-0.5};
    bool workspace_filter_enabled{false};

    // Border filter configuration
    bool border_filter_enabled{true};
    float border_margin{0.05f};

    // Image saving
    bool save_input_image{false};
    bool save_output_image{false};
    bool file_save_mode_timestamp{false};
    bool save_async{false};
    int save_queue_depth{3};
    int save_jpeg_quality{85};
    std::string input_dir;
    std::string output_dir;

    // Cache
    int cache_validity_ms{100};

    // Verbose timing
    bool verbose_timing{false};

#ifdef HAS_DEPTHAI
    // DepthAI configuration
    bool depthai_enable{false};
    std::string depthai_model_path;
    int depthai_num_classes{1};
    bool depthai_swap_class_labels{false};
    int depthai_camera_width{416};
    int depthai_camera_height{416};
    int depthai_camera_fps{30};
    float depthai_confidence_threshold{0.5f};
    double depthai_depth_min_mm{100.0};
    double depthai_depth_max_mm{5000.0};
    bool depthai_enable_depth{true};
    std::string depthai_device_id;
    int depthai_warmup_seconds{3};
    int depthai_max_queue_drain{10};
    bool depthai_flush_before_read{false};
    bool depthai_keep_aspect_ratio{true};
    bool depthai_auto_pause_after_detection{true};
    int depthai_detection_timeout_ms{500};
    int depthai_stereo_confidence_threshold{200};
    float depthai_bbox_scale_factor{0.5f};
    bool depthai_extended_disparity{true};

    // Stereo depth advanced tuning
    std::string depthai_spatial_calc_algorithm{"average"};
    std::string depthai_mono_resolution{"400p"};
    bool depthai_lr_check{true};
    bool depthai_subpixel{false};
    std::string depthai_median_filter{"7x7"};

    // Exposure control
    std::string exposure_mode{"auto"};
    int exposure_time_us{8000};
    int exposure_iso{400};

    // Thermal thresholds (for ThermalGuard initialization)
    double thermal_warning_temp_c{70.0};
    double thermal_throttle_temp_c{80.0};
    double thermal_critical_temp_c{90.0};
#endif
};

/**
 * @brief Encapsulates all detection orchestration logic.
 *
 * Owns the DepthAI pipeline lifecycle, detection inference, result caching,
 * spatial/confidence filtering, and image save/draw methods.
 * Extracted from CottonDetectionNode to enable independent unit testing
 * and reduce the monolithic class's member count.
 *
 * Thread safety: atomic counters for stats, mutex for cache and config.
 * No reference to CottonDetectionNode — dependencies injected via constructor.
 */
class DetectionEngine {
public:
    /**
     * @brief Construct a DetectionEngine.
     * @param config  Detection configuration (populated from node parameters)
     * @param logger_cb  Logging callback (forwarded to DepthAIManager)
     * @param performance_monitor  Optional performance monitor (nullable)
     * @param async_image_saver  Optional async image saver (nullable)
     */
    DetectionEngine(
        const DetectionConfig & config,
        cotton_detection::LoggerCallback logger_cb,
        PerformanceMonitor * performance_monitor,
        AsyncImageSaver * async_image_saver,
        AsyncJsonLogger * async_json_logger = nullptr);

    ~DetectionEngine();

    // Non-copyable, non-movable (owns unique_ptr resources)
    DetectionEngine(const DetectionEngine &) = delete;
    DetectionEngine & operator=(const DetectionEngine &) = delete;

    // === Core Detection API ===

    /**
     * @brief Run cotton detection on an image (or via DepthAI direct path).
     * @param image  Input image (unused for DepthAI direct path)
     * @param positions  Output: detected cotton positions in FLU coordinates
     * @return true if detection succeeded (even if no cotton found)
     */
    bool detect_cotton_in_image(
        const cv::Mat & image,
        std::vector<geometry_msgs::msg::Point> & positions);

    // === DepthAI Lifecycle ===
#ifdef HAS_DEPTHAI
    /**
     * @brief Initialize DepthAI camera pipeline.
     * @return true if initialization succeeded
     * @throws std::exception on fatal initialization errors
     */
    bool initialize_depthai();

    /** @brief Shut down DepthAI camera (with stderr suppression workaround). */
    void shutdown_depthai();

    /** @brief Apply runtime configuration changes (called under depthai_config_mutex_). */
    bool apply_depthai_runtime_config_locked();

    // === DepthAI Manager Access (for node-level integration) ===
    cotton_detection::DepthAIManager * getDepthAIManager() { return depthai_manager_.get(); }
    const cotton_detection::DepthAIManager * getDepthAIManager() const { return depthai_manager_.get(); }

    cotton_detection::ThermalGuard * getThermalGuard() { return thermal_guard_.get(); }
    const cotton_detection::ThermalGuard * getThermalGuard() const { return thermal_guard_.get(); }

    bool isDepthAIActive() const { return use_depthai_.load(); }

    /** @brief Get mutable reference to DepthAI config mutex (for parameter updates). */
    std::mutex & getConfigMutex() { return depthai_config_mutex_; }

    /**
     * @brief Draw detection annotations on an image.
     *
     * Pure function: takes an image and detection lists, returns annotated copy.
     * Public for unit testing — no internal state dependencies.
     *
     * @param image         Source image (BGR, not modified)
     * @param detections    Accepted detections (drawn as green/colored boxes)
     * @param zero_spatial  Rejected zero-spatial detections (drawn as red "DEPTH FAIL" boxes)
     * @return Annotated image copy
     */
    cv::Mat draw_detections_on_image(const cv::Mat & image,
                                     const std::vector<DepthAIDetectionResult> & detections,
                                     const std::vector<RejectedDetection> & zero_spatial = {});
#endif

    // === Stats / Observability ===

    /** @brief Get a point-in-time snapshot of all detection counters. */
    DetectionStats getStats() const;

    // === Stats Increment (called by node for service-level tracking) ===
    void incrementDetectRequests() { total_detect_requests_.fetch_add(1); }
    void incrementDetectSuccess() { total_detect_success_.fetch_add(1); }
    void addPositionsReturned(uint64_t count) { total_positions_returned_.fetch_add(count); }
    void incrementDetectionsWithCotton() { total_detections_with_cotton_.fetch_add(1); }
    void incrementCacheHits() { total_cache_hits_.fetch_add(1); }
    void incrementCacheMisses() { total_cache_misses_.fetch_add(1); }

    // === Cache Access ===
    struct CachedDetectionResult {
        std::vector<geometry_msgs::msg::Point> positions;
        std::vector<float> confidences;
        rclcpp::Time timestamp;
        std::chrono::steady_clock::time_point detection_capture_time;
        bool success{false};
    };

    std::mutex & getCacheMutex() { return cache_mutex_; }
    std::optional<CachedDetectionResult> & getCachedDetection() { return cached_detection_; }

    // === Config Access (for runtime parameter updates) ===
    DetectionConfig & getConfig() { return config_; }
    const DetectionConfig & getConfig() const { return config_; }

    // === Confidence Access ===
    std::mutex & getConfidencesMutex() { return confidences_mutex_; }
    std::vector<float> & getLastDetectionConfidences() { return last_detection_confidences_; }

    // === Detection Timing ===
    std::chrono::steady_clock::time_point getLastDetectionStartTime() const {
        return last_detection_start_time_;
    }

    // Atomic state exposed for node integration
    static constexpr int MAX_CONSECUTIVE_TIMEOUTS = 3;

private:
    DetectionConfig config_;
    cotton_detection::LoggerCallback logger_cb_;
    PerformanceMonitor * performance_monitor_;  // Non-owning
    AsyncImageSaver * async_image_saver_;        // Non-owning
    AsyncJsonLogger * async_json_logger_;        // Non-owning (nullable)

    // === Detection Stats (atomic for thread safety) ===
    std::atomic<uint64_t> total_detect_requests_{0};
    std::atomic<uint64_t> total_detect_success_{0};
    std::atomic<uint64_t> total_positions_returned_{0};
    std::atomic<uint64_t> total_detections_with_cotton_{0};
    std::atomic<uint64_t> total_border_filtered_{0};
    std::atomic<uint64_t> total_non_pickable_filtered_{0};
    std::atomic<uint64_t> total_workspace_filtered_{0};
    std::atomic<uint64_t> total_cache_hits_{0};
    std::atomic<uint64_t> total_cache_misses_{0};
    std::atomic<uint64_t> total_reconnects_{0};
    std::atomic<uint64_t> total_downtime_ms_{0};
    std::atomic<uint64_t> total_sync_mismatches_{0};

    // Frame wait timing
    std::atomic<uint64_t> frame_wait_total_ms_{0};
    std::atomic<uint64_t> frame_wait_count_{0};
    std::atomic<uint64_t> frame_wait_max_ms_{0};

    // Consecutive timeout tracking
    std::atomic<int> consecutive_detection_timeouts_{0};
    std::atomic<int> consecutive_rgb_timeouts_{0};
    std::chrono::steady_clock::time_point last_successful_detection_time_;
    std::chrono::steady_clock::time_point last_detection_start_time_;

    // Confidence tracking
    std::vector<float> last_detection_confidences_;
    mutable std::mutex confidences_mutex_;

    // Detection result caching
    std::optional<CachedDetectionResult> cached_detection_;
    std::mutex cache_mutex_;

#ifdef HAS_DEPTHAI
    // DepthAI components
    std::unique_ptr<cotton_detection::DepthAIManager> depthai_manager_;
    std::atomic<bool> use_depthai_{false};
    std::mutex depthai_config_mutex_;

    // Decomposed components
    std::unique_ptr<cotton_detection::ThermalGuard> thermal_guard_;

    // DepthAI internal methods
    bool get_depthai_detections(std::vector<DepthAIDetectionResult> & detections);

    // Image save methods (moved from _utils.cpp)
    void save_input_image(const cv::Mat & image);
    void save_output_image(const cv::Mat & image,
                           const std::vector<DepthAIDetectionResult> & detections,
                           const std::vector<RejectedDetection> & zero_spatial = {});
#endif
};

}  // namespace cotton_detection_ros2
