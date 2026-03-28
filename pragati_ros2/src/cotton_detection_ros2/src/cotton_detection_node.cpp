/**
 * @file cotton_detection_node.cpp
 * @brief Cotton Detection Node — constructor, destructor, callbacks, and publishing
 *
 * Consolidated file containing:
 * - Constructor / destructor / cleanup
 * - Image subscriber callbacks (image_callback, compressed_image_callback)
 * - Image conversion utilities (convert_ros_image_to_cv, convert_compressed_image_to_cv)
 * - Periodic stats logging (stats_log_callback)
 * - Diagnostic callbacks (diagnostic_callback, depthai_diagnostic_callback)
 * - Thermal check callback (thermal_check_callback)
 * - Publishing methods (publish_detection_result, publish_debug_image,
 *   publish_camera_info, publish_static_transforms)
 *
 * Detection logic is delegated to DetectionEngine.
 * Service handling is delegated to ServiceHandler.
 *
 * @author Cotton Detection Team
 * @date 2024-2026
 */

#include "cotton_detection_ros2/cotton_detection_node.hpp"

#ifdef HAS_DEPTHAI
#include "cotton_detection_ros2/depthai_manager.hpp"
#include "cotton_detection_ros2/thermal_guard.hpp"
#endif

// Specific OpenCV includes (avoid mega-include for faster builds)
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include <sensor_msgs/image_encodings.hpp>
#include <sys/resource.h>  // For getrusage (memory stats)
#include <thread>
#include <chrono>
#include <cmath>

// JSON serialization for structured logging
#include <nlohmann/json.hpp>
#include <common_utils/json_logging.hpp>

#include "git_version.h"

using namespace std::chrono_literals;

namespace cotton_detection_ros2
{

// =========================================================================
// Constructor / Destructor / Cleanup
// =========================================================================

CottonDetectionNode::CottonDetectionNode(const rclcpp::NodeOptions & options)
: Node("cotton_detection_node", options)
{
    // Record start time for uptime calculation in periodic stats
    node_start_time_ = std::chrono::steady_clock::now();

    // Initialize last_request_time_ to now so we don't falsely trigger
    // idle detection before the first real request arrives (Task 7.6)
    last_request_time_ = node_start_time_;

    RCLCPP_INFO(this->get_logger(), "🌱 Cotton Detection ROS2 Node Starting...");
    if (std::string(GIT_HASH).empty()) {
        RCLCPP_INFO(this->get_logger(), "   Built: %s", getBuildTimestamp());
    } else {
        RCLCPP_INFO(this->get_logger(), "   Built: %s (%s on %s)",
                     getBuildTimestamp(), GIT_HASH, GIT_BRANCH);
    }

    // Declare and load parameters
    declare_parameters();
    load_parameters();

    // Initialize detection components
    performance_monitor_ = std::make_unique<PerformanceMonitor>(this);
    configure_performance_monitor();

    parameter_callback_handle_ = this->add_on_set_parameters_callback(
        [this](const std::vector<rclcpp::Parameter> & params) {
            return this->on_parameter_update(params);
        });

    RCLCPP_INFO(this->get_logger(), "🌱 Cotton Detection Node Ready!");
    RCLCPP_INFO(this->get_logger(), "   📡 Service: /cotton_detection/detect");
    RCLCPP_INFO(this->get_logger(), "   📷 Camera Topic: %s", camera_topic_.c_str());
    RCLCPP_INFO(this->get_logger(), "   📊 Results Topic: /cotton_detection/results");
}

CottonDetectionNode::~CottonDetectionNode()
{
    RCLCPP_INFO(this->get_logger(), "🌱 Cotton Detection Node Shutdown");
}

void CottonDetectionNode::cleanup_before_shutdown()
{
    RCLCPP_INFO(this->get_logger(), "🧹 Performing explicit cleanup before shutdown...");

    // Destroy ServiceHandler first (holds raw pointers to DetectionEngine)
    service_handler_.reset();

#ifdef HAS_DEPTHAI
    // Explicitly shutdown DepthAI to release USB device
    // This MUST complete before the node is destroyed
    if (detection_engine_ && detection_engine_->getDepthAIManager()) {
        RCLCPP_INFO(this->get_logger(), "📷 Shutting down DepthAI camera...");
        detection_engine_.reset();

        // Brief wait for USB threads (most cleanup done in DetectionEngine destructor)
        // BLOCKING_SLEEP_OK: post-shutdown USB drain 100ms, main thread (executor already stopped) — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        RCLCPP_INFO(this->get_logger(), "✅ DepthAI camera released");
    }
#endif

    // Stop thermal timer if running
#ifdef HAS_DEPTHAI
    if (thermal_timer_) {
        thermal_timer_->cancel();
        thermal_timer_.reset();
    }
#endif

    // Stop async image saver (drain remaining queue items)
    if (async_image_saver_) {
        RCLCPP_INFO(this->get_logger(), "💾 Stopping async image saver...");
        async_image_saver_->stop();
        async_image_saver_.reset();
    }

    // Stop async JSON logger (drain remaining queue items)
    if (async_json_logger_) {
        RCLCPP_INFO(this->get_logger(), "📝 Stopping async JSON logger...");
        async_json_logger_->stop();
        async_json_logger_.reset();
    }

    RCLCPP_INFO(this->get_logger(), "✅ Cleanup complete");
}

// =========================================================================
// Image Subscriber Callbacks
// =========================================================================

void CottonDetectionNode::image_callback(const sensor_msgs::msg::Image::ConstSharedPtr & msg)
{
    std::lock_guard<std::mutex> lock(image_mutex_);

    try {
        latest_image_ = convert_ros_image_to_cv(msg);
        latest_image_stamp_ = msg->header.stamp;  // Store timestamp for freshness check
        image_available_ = true;
        consecutive_frame_drops_.store(0);  // Reset on success

        // RCLCPP_DEBUG(this->get_logger(), "📷 Image received: %dx%d",
        //             latest_image_.cols, latest_image_.rows);
    } catch (const std::exception & e) {
        int drops = consecutive_frame_drops_.fetch_add(1) + 1;
        RCLCPP_ERROR(this->get_logger(), "❌ Image conversion failed (%d consecutive): %s",
            drops, e.what());
        if (drops >= kMaxConsecutiveFrameDrops) {
            RCLCPP_ERROR(this->get_logger(),
                "{\"event\":\"frame_drop_threshold\",\"consecutive_drops\":%d,\"error\":\"%s\"}",
                drops, e.what());
        }
    }
}

void CottonDetectionNode::compressed_image_callback(
    const sensor_msgs::msg::CompressedImage::ConstSharedPtr & msg)
{
    std::lock_guard<std::mutex> lock(image_mutex_);

    try {
        latest_image_ = convert_compressed_image_to_cv(msg);
        latest_image_stamp_ = msg->header.stamp;  // Store timestamp for freshness check
        image_available_ = true;
        consecutive_frame_drops_.store(0);  // Reset on success

        // RCLCPP_DEBUG(this->get_logger(), "📷 Compressed image received: %dx%d",
        //             latest_image_.cols, latest_image_.rows);
    } catch (const std::exception & e) {
        int drops = consecutive_frame_drops_.fetch_add(1) + 1;
        RCLCPP_ERROR(this->get_logger(), "❌ Compressed image conversion failed (%d consecutive): %s",
            drops, e.what());
        if (drops >= kMaxConsecutiveFrameDrops) {
            RCLCPP_ERROR(this->get_logger(),
                "{\"event\":\"frame_drop_threshold\",\"consecutive_drops\":%d,\"error\":\"%s\"}",
                drops, e.what());
        }
    }
}

// =========================================================================
// Image Conversion Utilities
// =========================================================================

cv::Mat CottonDetectionNode::convert_ros_image_to_cv(const sensor_msgs::msg::Image::ConstSharedPtr & msg)
{
    cv_bridge::CvImagePtr cv_ptr = cv_bridge::toCvCopy(msg, sensor_msgs::image_encodings::BGR8);
    return cv_ptr->image;
}

cv::Mat CottonDetectionNode::convert_compressed_image_to_cv(
    const sensor_msgs::msg::CompressedImage::ConstSharedPtr & msg)
{
    cv::Mat image = cv::imdecode(cv::Mat(msg->data), cv::IMREAD_COLOR);
    return image;
}

// =========================================================================
// Periodic Stats Logging
// =========================================================================

void CottonDetectionNode::stats_log_callback()
{
#ifdef HAS_DEPTHAI
    // Comprehensive periodic stats report (merged with performance monitor)
    auto det_stats = detection_engine_->getStats();
    const uint64_t req = det_stats.total_detect_requests;
    const uint64_t ok = det_stats.total_detect_success;
    const uint64_t positions = det_stats.total_positions_returned;
    const uint64_t with_cotton = det_stats.total_detections_with_cotton;

    // Calculate uptime
    auto now = std::chrono::steady_clock::now();
    auto uptime_sec = std::chrono::duration_cast<std::chrono::seconds>(now - node_start_time_).count();

    // Task 7.6: Idle detection — if no request for IDLE_TIMEOUT_SEC, emit idle event
    {
        auto since_last_request = std::chrono::duration_cast<std::chrono::seconds>(
            now - last_request_time_).count();
        if (since_last_request >= IDLE_TIMEOUT_SEC && req > 0) {
            if (!idle_state_.load()) {
                idle_state_.store(true);
                // Emit idle event JSON
                auto j_idle = pragati::json_envelope("detection_idle", this->get_logger().get_name());
                j_idle["idle_seconds"] = since_last_request;
                j_idle["uptime_s"] = uptime_sec;
                RCLCPP_INFO(this->get_logger(), "%s", j_idle.dump().c_str());
            }
            // Continue to print stats even during idle for monitoring
        }
    }

    // Get temperature and camera stats
    double temp = 0.0;
    uint64_t frames_processed = 0;
    if (detection_engine_->isDepthAIActive() && detection_engine_->getDepthAIManager()) {
        auto cam_stats = detection_engine_->getDepthAIManager()->getStats();
        temp = cam_stats.temperature_celsius;
        frames_processed = cam_stats.frames_processed;
    }

    // Calculate frame wait stats
    uint64_t frame_wait_count = det_stats.frame_wait_count;
    uint64_t frame_wait_avg = frame_wait_count > 0 ? det_stats.frame_wait_total_ms / frame_wait_count : 0;
    uint64_t frame_wait_max = det_stats.frame_wait_max_ms;

    // Get latency stats from performance monitor
    double latency_avg = 0.0, latency_min = 0.0, latency_max = 0.0;
    double latency_p50 = 0.0, latency_p95 = 0.0, latency_p99 = 0.0;
    size_t memory_mb = 0;
    if (performance_monitor_) {
        auto metrics = performance_monitor_->get_metrics();
        latency_avg = metrics.avg_latency_ms;
        latency_min = metrics.min_latency_ms;
        latency_max = metrics.max_latency_ms;
        latency_p50 = metrics.p50_latency_ms;
        latency_p95 = metrics.p95_latency_ms;
        latency_p99 = metrics.p99_latency_ms;
        // Get memory usage
        struct rusage usage;
        if (getrusage(RUSAGE_SELF, &usage) == 0) {
            memory_mb = usage.ru_maxrss / 1024;
        }
    }

    // Detection rate calculation
    double detection_rate = req > 0 ? (100.0 * with_cotton / req) : 0.0;

    // Format uptime
    int hours = uptime_sec / 3600;
    int mins = (uptime_sec % 3600) / 60;
    int secs = uptime_sec % 60;

    // Log comprehensive stats
    RCLCPP_INFO(this->get_logger(), " ");
    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(this->get_logger(), "📊 COTTON DETECTION STATS (uptime: %02d:%02d:%02d)", hours, mins, secs);
    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════════════════");

    // Camera connection status with active health probe
    bool camera_initialized = (detection_engine_->isDepthAIActive() && detection_engine_->getDepthAIManager() && detection_engine_->getDepthAIManager()->isInitialized());
    bool needs_reconnect = false;
    bool camera_healthy = false;

    if (camera_initialized) {
        // Active probe: Try to check if device is responsive
        // Temperature read can return cached values, so also check reconnect flag
        needs_reconnect = detection_engine_->getDepthAIManager()->needsReconnect();

        // Healthy means: initialized AND not flagged for reconnection
        camera_healthy = !needs_reconnect && detection_engine_->getDepthAIManager()->isHealthy();

        // Additional check: If temp is reading properly, device is likely connected
        // (Note: temp can be 0.0 if device doesn't support it, so can't rely on this alone)
    }

    if (camera_healthy) {
        RCLCPP_INFO(this->get_logger(), "📷 Camera: ✅ CONNECTED & HEALTHY");
    } else if (needs_reconnect) {
        RCLCPP_WARN(this->get_logger(), "📷 Camera: 🔄 RECONNECTION NEEDED (XLink error detected)");
    } else if (camera_initialized) {
        RCLCPP_WARN(this->get_logger(), "📷 Camera: ⚠️  INITIALIZED BUT UNHEALTHY");
    } else {
        RCLCPP_ERROR(this->get_logger(), "📷 Camera: ❌ NOT INITIALIZED");
    }

    // Camera stats
    if (temp > 0.0) {
        RCLCPP_INFO(this->get_logger(),
            "🌡️  Temp: %.1f°C | Frames: %lu", temp, frames_processed);
    }

    // Extended camera diagnostics (CPU/Memory usage - helps debug XLink errors)
    if (detection_engine_->isDepthAIActive() && detection_engine_->getDepthAIManager() && camera_healthy) {
        auto cam_stats = detection_engine_->getDepthAIManager()->getStats();
        if (cam_stats.css_cpu_usage_percent > 0.0 || cam_stats.mss_cpu_usage_percent > 0.0) {
            RCLCPP_INFO(this->get_logger(),
                "📹 OAK-D: CSS=%.1f%% MSS=%.1f%% | DDR: %.1f/%.1f MB | CMX: %.1f/%.1f KB",
                cam_stats.css_cpu_usage_percent, cam_stats.mss_cpu_usage_percent,
                cam_stats.ddr_memory_used_mb, cam_stats.ddr_memory_total_mb,
                cam_stats.cmx_memory_used_kb, cam_stats.cmx_memory_total_kb);
        }
        // Log USB path and XLink error count (critical for debugging disconnects)
        RCLCPP_INFO(this->get_logger(),
            "🔌 USB: %s @ path %s | MXID: %s | XLink errors: %u, reconnects: %u",
            cam_stats.usb_speed.c_str(), cam_stats.usb_path.c_str(),
            cam_stats.device_mxid.c_str(),
            cam_stats.xlink_error_count, cam_stats.reconnect_count);
    }

    // Detection stats
    RCLCPP_INFO(this->get_logger(),
        "🔍 Requests: %lu | Success: %lu | WithCotton: %lu (%.1f%%)",
        req, ok, with_cotton, detection_rate);
    RCLCPP_INFO(this->get_logger(),
        "🎯 Positions returned: %lu", positions);

    // Latency stats
    if (latency_avg > 0.0) {
        RCLCPP_INFO(this->get_logger(),
            "⏱️  Latency: avg=%.1fms, min=%.1fms, max=%.1fms",
            latency_avg, latency_min, latency_max);
    }

    // Frame wait stats
    if (frame_wait_count > 0) {
        RCLCPP_INFO(this->get_logger(),
            "📷 Frame wait: avg=%lums, max=%lums (n=%lu)",
            frame_wait_avg, frame_wait_max, frame_wait_count);
    }

    // Reliability stats (timeouts, reconnects, sync)
    uint64_t reconnects = det_stats.total_reconnects;
    int det_timeouts = det_stats.consecutive_detection_timeouts;
    int rgb_timeouts = det_stats.consecutive_rgb_timeouts;
    uint64_t sync_mismatches = det_stats.total_sync_mismatches;
    uint64_t downtime_ms = det_stats.total_downtime_ms;

    if (reconnects > 0 || det_timeouts > 0 || rgb_timeouts > 0 || sync_mismatches > 0) {
        RCLCPP_INFO(this->get_logger(),
            "🔄 Reliability: reconnects=%lu (downtime=%.1fs), det_timeouts=%d/%d, rgb_timeouts=%d/%d",
            reconnects, downtime_ms / 1000.0, det_timeouts, DetectionEngine::MAX_CONSECUTIVE_TIMEOUTS, rgb_timeouts, DetectionEngine::MAX_CONSECUTIVE_TIMEOUTS);
    }
    if (sync_mismatches > 0) {
        RCLCPP_WARN(this->get_logger(),
            "⚠️  Sync mismatches: %lu (detection/RGB frame mismatch)", sync_mismatches);
    }

    // Memory stats
    if (memory_mb > 0) {
        RCLCPP_INFO(this->get_logger(),
            "💾 Memory: %zu MB", memory_mb);
    }

    RCLCPP_INFO(this->get_logger(), "════════════════════════════════════════════════════════════════════════");

    // Structured JSON log line for post-trial analysis
    {
        // Camera stats for JSON (re-fetch for extended fields)
        double json_temp = 0.0;
        std::string json_usb_speed;
        std::string json_device_mxid;
        double json_css_cpu = 0.0;
        double json_mss_cpu = 0.0;
        uint32_t json_xlink_errors = 0;
        uint32_t json_reconnect_count = 0;
        // Task 7.2/7.3/7.4/7.8: Extended camera stats
        double json_vpu_p50 = 0.0, json_vpu_p95 = 0.0;
        double json_avg_exposure_us = 0.0, json_avg_sensitivity_iso = 0.0;
        uint64_t json_cam_frames_processed = 0, json_cam_frames_dropped = 0;
        double json_frame_drop_rate_pct = 0.0;
        int json_queue_det = -1, json_queue_rgb = -1, json_queue_depth = -1;
        uint64_t json_zero_spatial_count = 0;  // Task 7.5
        if (detection_engine_->isDepthAIActive() && detection_engine_->getDepthAIManager() && camera_healthy) {
            auto cam_stats_json = detection_engine_->getDepthAIManager()->getStats();
            json_temp = cam_stats_json.temperature_celsius;
            json_usb_speed = cam_stats_json.usb_speed;
            json_device_mxid = cam_stats_json.device_mxid;
            json_css_cpu = cam_stats_json.css_cpu_usage_percent;
            json_mss_cpu = cam_stats_json.mss_cpu_usage_percent;
            json_xlink_errors = cam_stats_json.xlink_error_count;
            json_reconnect_count = cam_stats_json.reconnect_count;
            // Task 7.2
            json_vpu_p50 = cam_stats_json.vpu_inference_p50_ms;
            json_vpu_p95 = cam_stats_json.vpu_inference_p95_ms;
            // Task 7.3
            json_avg_exposure_us = cam_stats_json.avg_exposure_us;
            json_avg_sensitivity_iso = cam_stats_json.avg_sensitivity_iso;
            // Task 7.4
            json_cam_frames_processed = cam_stats_json.camera_frames_processed;
            json_cam_frames_dropped = cam_stats_json.camera_frames_dropped;
            json_frame_drop_rate_pct = cam_stats_json.frame_drop_rate_pct;
            // Task 7.8
            json_queue_det = cam_stats_json.queue_detection_size;
            json_queue_rgb = cam_stats_json.queue_rgb_size;
            json_queue_depth = cam_stats_json.queue_depth_size;
            // Task 7.5
            json_zero_spatial_count = cam_stats_json.zero_spatial_rejections;
        }

        nlohmann::json j = pragati::json_envelope("detection_summary", this->get_logger().get_name());
        j["uptime_s"] = uptime_sec;
        j["requests"] = {
            {"total", req},
            {"success", ok},
            {"with_cotton", with_cotton},
            {"detection_rate_pct", detection_rate},
            {"cache_hits", det_stats.total_cache_hits},
            {"cache_misses", det_stats.total_cache_misses}
        };
        j["latency_ms"] = {
            {"avg", latency_avg},
            {"min", latency_min},
            {"max", latency_max},
            {"p50", latency_p50},
            {"p95", latency_p95},
            {"p99", latency_p99}
        };
        j["camera"] = {
            {"healthy", camera_healthy},
            {"temp_c", json_temp},
            {"usb_speed", json_usb_speed},
            {"css_cpu_pct", json_css_cpu},
            {"mss_cpu_pct", json_mss_cpu},
            {"reconnect_count", json_reconnect_count},
            {"mxid", json_device_mxid}
        };
        j["reliability"] = {
            {"reconnects", reconnects},
            {"downtime_s", downtime_ms / 1000.0},
            {"xlink_errors", json_xlink_errors},
            {"sync_mismatches", sync_mismatches}
        };
        j["thermal"] = {
            {"throttle_effective", is_throttled_.load()},
            {"paused", is_paused_.load()}
        };
        j["host"] = {
            {"memory_mb", memory_mb}
        };
        // Task 7.2: VPU inference timing
        j["vpu_ms"] = {
            {"p50", json_vpu_p50},
            {"p95", json_vpu_p95}
        };
        // Task 7.3: Exposure rolling averages
        j["exposure"] = {
            {"avg_exposure_us", json_avg_exposure_us},
            {"avg_sensitivity_iso", json_avg_sensitivity_iso}
        };
        // Task 7.4: Frame gap stats
        j["frames"] = {
            {"processed", json_cam_frames_processed},
            {"dropped", json_cam_frames_dropped},
            {"drop_rate_pct", json_frame_drop_rate_pct}
        };
        // Task 7.5: Depth quality summary
        {
            j["depth_quality"] = {
                {"zero_spatial_count", json_zero_spatial_count}
            };
            // Note: per-detection valid_depth_pct is not implemented because
            // DepthAI does not expose the raw depth ROI pixels through the
            // SpatialDetectionNetwork output. boundingBoxMapping would be
            // needed from the depth frame, which is not readily available
            // in the current getSynchronizedDetection() flow.
        }
        // Task 7.8: Queue depths
        j["queues"] = {
            {"detection", json_queue_det},
            {"rgb", json_queue_rgb},
            {"depth", json_queue_depth}
        };
        j["model"] = detection_engine_->getConfig().depthai_model_path;

        RCLCPP_INFO(this->get_logger(), "%s", j.dump().c_str());
    }
#endif
}

// =========================================================================
// Diagnostic Callbacks
// =========================================================================

void CottonDetectionNode::diagnostic_callback(diagnostic_updater::DiagnosticStatusWrapper & stat)
{
    // General node health status
    if (detection_active_) {
        stat.summary(diagnostic_msgs::msg::DiagnosticStatus::OK, "Detection active");
    } else {
        stat.summary(diagnostic_msgs::msg::DiagnosticStatus::WARN, "Detection inactive");
    }

    // Add diagnostic data
    stat.add("Detection Active", detection_active_ ? "Yes" : "No");
    stat.add("Image Available", image_available_ ? "Yes" : "No");
    stat.add("Detection Mode", "DepthAI Direct");

    // Detection request stats
    auto det_stats = detection_engine_->getStats();
    stat.add("Total Detect Requests", std::to_string(det_stats.total_detect_requests));
    stat.add("Successful Detect Requests", std::to_string(det_stats.total_detect_success));
    stat.add("Positions Returned (sum)", std::to_string(det_stats.total_positions_returned));

    // Performance metrics (if available)
    if (performance_monitor_ && enable_performance_monitoring_) {
        stat.add("Performance Monitoring", "Active");
    } else {
        stat.add("Performance Monitoring", "Inactive");
    }
}

#ifdef HAS_DEPTHAI
void CottonDetectionNode::depthai_diagnostic_callback(diagnostic_updater::DiagnosticStatusWrapper & stat)
{
    // DepthAI camera health status
    if (detection_engine_->isDepthAIActive() && detection_engine_->getDepthAIManager() && detection_engine_->getDepthAIManager()->isInitialized()) {
        if (detection_engine_->getDepthAIManager()->isHealthy()) {
            stat.summary(diagnostic_msgs::msg::DiagnosticStatus::OK, "DepthAI camera healthy");

            // Get camera statistics
            auto stats = detection_engine_->getDepthAIManager()->getStats();
            stat.add("FPS", std::to_string(stats.fps));
            stat.add("Frames Processed", std::to_string(stats.frames_processed));
            stat.add("Total Detections", std::to_string(stats.detection_count));
            stat.add("Avg Latency (ms)", std::to_string(stats.avg_latency.count()));
            stat.add("Uptime (s)", std::to_string(stats.uptime.count() / 1000));
            stat.add("Temperature (C)", std::to_string(stats.temperature_celsius));

            // Enrich with ThermalGuard status
            if (detection_engine_->getThermalGuard()) {
                auto ts = detection_engine_->getThermalGuard()->getStatus();
                const char* ts_name = "Normal";
                switch (ts) {
                    case cotton_detection::ThermalStatus::Warning: ts_name = "Warning"; break;
                    case cotton_detection::ThermalStatus::Throttle: ts_name = "Throttle"; break;
                    case cotton_detection::ThermalStatus::Critical: ts_name = "Critical"; break;
                    default: break;
                }
                stat.add("Thermal Status", ts_name);
            }
        } else {
            stat.summary(diagnostic_msgs::msg::DiagnosticStatus::ERROR, "DepthAI camera unhealthy");

            // Use DiagnosticsCollector for XLink error classification
            if (detection_engine_->getDepthAIManager()->needsReconnect()) {
                auto category = cotton_detection::DiagnosticsCollector::classifyXLinkError(
                    "device needs reconnect");
                const char* cat_name = "unknown";
                switch (category) {
                    case cotton_detection::XLinkErrorCategory::timeout: cat_name = "timeout"; break;
                    case cotton_detection::XLinkErrorCategory::link_down: cat_name = "link_down"; break;
                    case cotton_detection::XLinkErrorCategory::device_removed: cat_name = "device_removed"; break;
                    case cotton_detection::XLinkErrorCategory::pipe_error: cat_name = "pipe_error"; break;
                    default: break;
                }
                stat.add("XLink Error Category", cat_name);
            }
        }

        stat.add("Device Info", detection_engine_->getDepthAIManager()->getDeviceInfo());
        stat.add("Model Path", detection_engine_->getConfig().depthai_model_path);
    } else if (detection_engine_->isDepthAIActive()) {
        stat.summary(diagnostic_msgs::msg::DiagnosticStatus::ERROR, "DepthAI initialization failed");
        stat.add("Status", "Failed to initialize");
    } else {
        stat.summary(diagnostic_msgs::msg::DiagnosticStatus::OK, "DepthAI not enabled (using Python wrapper)");
        stat.add("Status", "Disabled");
    }
}
#endif

// =========================================================================
// Thermal Check Callback (node-level per design D4)
// =========================================================================

#ifdef HAS_DEPTHAI
void CottonDetectionNode::thermal_check_callback()
{
    if (!thermal_enable_ || !detection_engine_ || !detection_engine_->isDepthAIActive() || !detection_engine_->getDepthAIManager()) {
        return;
    }

    // Local convenience pointers for readability
    auto* cam = detection_engine_->getDepthAIManager();
    auto* tguard = detection_engine_->getThermalGuard();

    // HEALTH CHECK: Poll detection queue to detect XLink disconnects.
    // IMPROVED: Only poll when necessary to avoid stressing idle VPU:
    // 1. When paused: keepalive (XLink dies after ~30-60s idle)
    // 2. When NOT idle: detect hot-swap/cable disconnect within one thermal cycle (5s)
    // 3. When idle for extended periods: SKIP polling (reduces XLink errors on idle VPU)
    // Without this check, a USB disconnect while running leaves the node
    // in a zombie state — reading garbage from a destroyed device but reporting "HEALTHY".
    bool is_paused = is_paused_.load();
    bool is_idle = idle_state_.load();
    bool should_poll_health = is_paused || !is_idle;  // Only poll when needed

    if (should_poll_health) {
        try {
            cam->hasDetections();
        } catch (const std::exception& e) {
            RCLCPP_WARN(this->get_logger(), "Exception in thermal_check_callback/health_check: %s - continuing", e.what());
        }
    }

    // AUTO-RECONNECT: If hasDetections() (or any prior call) detected an XLink error,
    // trigger autonomous reconnection. Without this, the node loops forever logging
    // "Error checking detections" and never recovers.
    if (cam->needsReconnect()) {
        RCLCPP_WARN(this->get_logger(),
            "Camera needs reconnection (detected in thermal health check) - attempting reconnect...");

        constexpr int max_retries = 3;
        int retry_delay_ms = 2000;
        bool reconnected = false;

        for (int attempt = 1; attempt <= max_retries; ++attempt) {
            RCLCPP_INFO(this->get_logger(), "Reconnection attempt %d/%d...", attempt, max_retries);
            try {
                if (cam->reconnect()) {
                    RCLCPP_INFO(this->get_logger(), "Reconnected successfully on attempt %d", attempt);
                    reconnected = true;
                    // BLOCKING_SLEEP_OK: post-reconnect warmup 1s, executor-thread (monitoring_group_) — reviewed 2026-03-14
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                    cam->flushAllQueues();
                    break;
                }
            } catch (const std::logic_error& e) {
                RCLCPP_WARN(this->get_logger(), "Reconnection attempt %d rejected: %s", attempt, e.what());
            } catch (const std::exception& e) {
                RCLCPP_WARN(this->get_logger(), "Reconnection attempt %d failed: %s", attempt, e.what());
            }

            if (attempt < max_retries) {
                RCLCPP_WARN(this->get_logger(),
                    "Reconnection attempt %d failed, waiting %d ms before retry...", attempt, retry_delay_ms);
                // BLOCKING_SLEEP_OK: reconnect backoff 2-4s, executor-thread (monitoring_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(retry_delay_ms));
                retry_delay_ms *= 2;
            }
        }

        if (!reconnected) {
            RCLCPP_ERROR(this->get_logger(),
                "Autonomous reconnection failed after %d attempts", max_retries);
        } else {
            // Clear thermal state — the reconnect created a fresh device/pipeline,
            // so the old pause/throttle state is stale. Without this, the next
            // thermal_check_callback sees is_paused_==true, finds isCameraPaused()==false
            // (fresh device was never paused), and triggers a full reinitialize — creating
            // a second device that corrupts the first.
            is_paused_.store(false);
            is_throttled_.store(false);
            camera_error_.store(false);
        }
        return;  // Skip thermal evaluation this cycle
    }

    // Delegate threshold evaluation to ThermalGuard (handles hysteresis)
    if (!tguard) {
        return;
    }
    tguard->update();

    double temp = tguard->getCurrentTemperature();
    if (temp <= 0.0) {
        return;  // Temperature not available (requires hardware)
    }

    auto status = tguard->getStatus();

    // Act on thermal status — actions use camera manager (node-level concern)
    switch (status) {
        case cotton_detection::ThermalStatus::Critical:
            if (!is_paused_.load()) {
                RCLCPP_ERROR(this->get_logger(),
                    "CRITICAL: Chip temperature %.1f C >= %.1f C - PAUSING CAMERA (fast)",
                    temp, thermal_critical_temp_c_);
                try {
                    cam->pauseCamera();
                    is_paused_.store(true);
                    is_throttled_.store(false);
                    RCLCPP_INFO(this->get_logger(), "Camera paused for thermal protection (~10ms)");
                } catch (const std::logic_error& e) {
                    RCLCPP_WARN(this->get_logger(), "Fast pause failed (%s), using full shutdown", e.what());
                    detection_engine_->shutdown_depthai();
                    is_paused_.store(true);
                    is_throttled_.store(false);
                }
            }
            break;

        case cotton_detection::ThermalStatus::Throttle:
            // Recovery from pause takes priority over throttle
            if (is_paused_.load()) {
                RCLCPP_INFO(this->get_logger(),
                    "Temperature %.1f C dropped to Throttle - RESUMING CAMERA", temp);
                if (cam && cam->isCameraPaused()) {
                    try {
                        bool resumed = cam->resumeCamera();
                        if (!resumed) {
                            RCLCPP_ERROR(this->get_logger(), "resumeCamera returned failure — camera in error state");
                            camera_error_.store(true);
                        } else {
                            camera_error_.store(false);
                            // Wait for stereo pipeline to stabilize after resume
                            // BLOCKING_SLEEP_OK: stereo stabilization 100ms after resume, executor-thread (monitoring_group_) — reviewed 2026-03-14
                            std::this_thread::sleep_for(std::chrono::milliseconds(100));
                            int flushed = 0;
                            while (cam->hasDetections() && flushed < 10) {
                                cam->getDetections(std::chrono::milliseconds(10));
                                flushed++;
                            }
                            is_paused_.store(false);
                            RCLCPP_INFO(this->get_logger(), "Camera resumed (flushed %d frames)", flushed);
                        }
                    } catch (const std::logic_error& e) {
                        RCLCPP_ERROR(this->get_logger(), "Fast resume failed: %s", e.what());
                        camera_error_.store(true);
                    }
                } else {
                    try {
                        detection_engine_->initialize_depthai();
                        is_paused_.store(false);
                        camera_error_.store(false);
                        RCLCPP_INFO(this->get_logger(), "Camera reinitialized (full)");
                    } catch (const std::exception& e) {
                        RCLCPP_ERROR(this->get_logger(), "Failed to reinitialize camera: %s", e.what());
                        camera_error_.store(true);
                    }
                }
            } else if (!is_throttled_.load()) {
                // Throttle FPS — DepthAIManager::setFPS updates config (pipeline NOT rebuilt)
                RCLCPP_WARN(this->get_logger(),
                    "Chip temperature %.1f C >= %.1f C - THROTTLING to %d FPS",
                    temp, thermal_throttle_temp_c_, thermal_throttle_fps_);
                original_fps_.store(depthai_camera_fps_);
                try {
                    cam->setFPS(thermal_throttle_fps_);
                } catch (const std::logic_error& e) {
                    RCLCPP_WARN(this->get_logger(), "Failed to set throttle FPS: %s", e.what());
                }
                is_throttled_.store(true);
            }
            break;

        case cotton_detection::ThermalStatus::Warning:
            // Recovery from pause if temperature dropped enough (hysteresis handled by ThermalGuard)
            if (is_paused_.load()) {
                RCLCPP_INFO(this->get_logger(),
                    "Temperature %.1f C dropped to Warning - RESUMING CAMERA", temp);
                if (cam && cam->isCameraPaused()) {
                    try {
                        bool resumed = cam->resumeCamera();
                        if (!resumed) {
                            RCLCPP_ERROR(this->get_logger(), "resumeCamera returned failure — camera in error state");
                            camera_error_.store(true);
                        } else {
                            camera_error_.store(false);
                            // BLOCKING_SLEEP_OK: stereo stabilization 100ms after resume, executor-thread (monitoring_group_) — reviewed 2026-03-14
                            std::this_thread::sleep_for(std::chrono::milliseconds(100));
                            int flushed = 0;
                            while (cam->hasDetections() && flushed < 10) {
                                cam->getDetections(std::chrono::milliseconds(10));
                                flushed++;
                            }
                            is_paused_.store(false);
                            RCLCPP_INFO(this->get_logger(), "Camera resumed (flushed %d frames)", flushed);
                        }
                    } catch (const std::logic_error& e) {
                        RCLCPP_ERROR(this->get_logger(), "Fast resume failed: %s", e.what());
                        camera_error_.store(true);
                    }
                } else {
                    try {
                        detection_engine_->initialize_depthai();
                        is_paused_.store(false);
                        camera_error_.store(false);
                    } catch (const std::exception& e) {
                        RCLCPP_ERROR(this->get_logger(), "Failed to reinitialize camera: %s", e.what());
                        camera_error_.store(true);
                    }
                }
            }
            // Recovery from throttle
            if (is_throttled_.load()) {
                RCLCPP_INFO(this->get_logger(),
                    "Temperature %.1f C dropped - RESTORING to %d FPS",
                    temp, original_fps_.load());
                try {
                    cam->setFPS(original_fps_.load());
                } catch (const std::logic_error& e) {
                    RCLCPP_WARN(this->get_logger(), "Failed to restore FPS: %s", e.what());
                }
                is_throttled_.store(false);
            }
            RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 30000,
                "Chip temperature %.1f C >= %.1f C (warning threshold)",
                temp, thermal_warning_temp_c_);
            break;

        case cotton_detection::ThermalStatus::Normal:
            // Recovery from pause
            if (is_paused_.load()) {
                RCLCPP_INFO(this->get_logger(),
                    "Temperature %.1f C returned to Normal - RESUMING CAMERA", temp);
                if (cam && cam->isCameraPaused()) {
                    try {
                        bool resumed = cam->resumeCamera();
                        if (!resumed) {
                            RCLCPP_ERROR(this->get_logger(), "resumeCamera returned failure — camera in error state");
                            camera_error_.store(true);
                        } else {
                            camera_error_.store(false);
                            // BLOCKING_SLEEP_OK: stereo stabilization 100ms after resume, executor-thread (monitoring_group_) — reviewed 2026-03-14
                            std::this_thread::sleep_for(std::chrono::milliseconds(100));
                            int flushed = 0;
                            while (cam->hasDetections() && flushed < 10) {
                                cam->getDetections(std::chrono::milliseconds(10));
                                flushed++;
                            }
                            is_paused_.store(false);
                            RCLCPP_INFO(this->get_logger(), "Camera resumed (flushed %d frames)", flushed);
                        }
                    } catch (const std::logic_error& e) {
                        RCLCPP_ERROR(this->get_logger(), "Fast resume failed: %s", e.what());
                        camera_error_.store(true);
                    }
                } else {
                    try {
                        detection_engine_->initialize_depthai();
                        is_paused_.store(false);
                        camera_error_.store(false);
                    } catch (const std::exception& e) {
                        RCLCPP_ERROR(this->get_logger(), "Failed to reinitialize camera: %s", e.what());
                        camera_error_.store(true);
                    }
                }
            }
            // Recovery from throttle
            if (is_throttled_.load()) {
                RCLCPP_INFO(this->get_logger(),
                    "Temperature %.1f C - RESTORING to %d FPS",
                    temp, original_fps_.load());
                try {
                    cam->setFPS(original_fps_.load());
                } catch (const std::logic_error& e) {
                    RCLCPP_WARN(this->get_logger(), "Failed to restore FPS: %s", e.what());
                }
                is_throttled_.store(false);
            }
            break;
    }
}
#endif

// =========================================================================
// Publishing Methods
// =========================================================================

void CottonDetectionNode::publish_detection_result(
    const std::vector<geometry_msgs::msg::Point> & positions, bool success)
{
    // NOTE: Positions passed to this function are already in FLU (Forward-Left-Up) coordinates.
    // For DepthAI detections, the conversion from RUF (Right-Up-Forward) to FLU happens in
    // get_depthai_detections() before calling this function.
    // See cotton_detection_node_depthai.cpp lines 259-287 for the conversion details.

    // Use fallback positions if enabled and zero cotton detected
    std::vector<geometry_msgs::msg::Point> positions_to_publish = positions;
    if (publish_fallback_on_zero_ && positions.empty() && success) {
        positions_to_publish = fallback_positions_;
        RCLCPP_INFO(this->get_logger(), "📍 Zero cotton detected - publishing %zu fallback positions",
                   fallback_positions_.size());
    }

    auto result_msg = cotton_detection_msgs::msg::DetectionResult();
    result_msg.header.stamp = this->now();
    result_msg.header.frame_id = "camera_link";  // Positions are in FLU coordinate system

    result_msg.total_count = static_cast<int32_t>(positions_to_publish.size());
    result_msg.detection_successful = success;

    // Calculate processing time from detection start
    auto current_time = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(
        current_time - detection_engine_->getLastDetectionStartTime());
    result_msg.processing_time_ms = static_cast<float>(duration.count());

    // Convert positions to CottonPosition messages
    {
        std::lock_guard<std::mutex> conf_lock(detection_engine_->getConfidencesMutex());
        for (size_t i = 0; i < positions_to_publish.size(); ++i) {
            cotton_detection_msgs::msg::CottonPosition cotton_pos;
            cotton_pos.position = positions_to_publish[i];

            // Use stored confidence if available (from DepthAI), otherwise use threshold
            if (i < detection_engine_->getLastDetectionConfidences().size()) {
                cotton_pos.confidence = detection_engine_->getLastDetectionConfidences()[i];
            } else {
                cotton_pos.confidence = static_cast<float>(detection_confidence_threshold_);
            }

            cotton_pos.detection_id = simulation_detection_id_counter_.fetch_add(
                simulation_mode_ ? 1 : 0);
            if (!simulation_mode_) {
                // Non-simulation: keep 0-indexed per-call IDs
                cotton_pos.detection_id = static_cast<int32_t>(i);
            }
            cotton_pos.header = result_msg.header;

            result_msg.positions.push_back(cotton_pos);
        }

        // Clear stored confidences after use
        detection_engine_->getLastDetectionConfidences().clear();
    }

    RCLCPP_INFO(this->get_logger(), "📤 Publishing detection result: %zu positions, success=%s",
               positions_to_publish.size(), success ? "true" : "false");
    auto dds_pub_start = std::chrono::steady_clock::now();  // INSTRUMENTATION
    pub_detection_result_->publish(result_msg);
    auto dds_pub_end = std::chrono::steady_clock::now();  // INSTRUMENTATION
    long dds_pub_us = std::chrono::duration_cast<std::chrono::microseconds>(dds_pub_end - dds_pub_start).count();  // INSTRUMENTATION
    auto pub_epoch_us = std::chrono::duration_cast<std::chrono::microseconds>(  // INSTRUMENTATION
        dds_pub_end.time_since_epoch()).count();  // INSTRUMENTATION
    RCLCPP_INFO(this->get_logger(), "INSTRUMENTATION dds_publish_us=%ld pub_epoch_us=%ld", dds_pub_us, pub_epoch_us);  // INSTRUMENTATION
    RCLCPP_INFO(this->get_logger(), "✅ Detection result published to /cotton_detection/results");
}

void CottonDetectionNode::publish_debug_image(const cv::Mat & image)
{
    if (!enable_debug_output_ || image.empty()) return;

    try {
        // Publish as compressed image
        auto compressed_msg = std::make_shared<sensor_msgs::msg::CompressedImage>();
        compressed_msg->header.stamp = this->now();
        compressed_msg->header.frame_id = "camera_link";
        compressed_msg->format = "jpeg";

        std::vector<uchar> buffer;
        cv::imencode(".jpg", image, buffer);
        compressed_msg->data = buffer;

        pub_debug_image_->publish(*compressed_msg);

        // Also publish via image transport
        auto cv_bridge_msg = cv_bridge::CvImage(compressed_msg->header, "bgr8", image);
        debug_image_pub_.publish(cv_bridge_msg.toImageMsg());

    } catch (const std::exception & e) {
        RCLCPP_ERROR(this->get_logger(), "❌ Debug image publishing failed: %s", e.what());
    }
}

void CottonDetectionNode::publish_camera_info()
{
    // Initialize camera info with default values
    // These will be updated with real calibration from DepthAI in Phase 2.3
    camera_info_.header.stamp = this->now();
    camera_info_.header.frame_id = "camera_link";

    // Default camera parameters (416x416 for DepthAI)
    camera_info_.width = 416;
    camera_info_.height = 416;

    // Default intrinsic matrix (placeholder until real calibration)
    // K = [fx  0 cx]
    //     [ 0 fy cy]
    //     [ 0  0  1]
    camera_info_.k = {
        400.0, 0.0, 208.0,  // fx, 0, cx
        0.0, 400.0, 208.0,  // 0, fy, cy
        0.0, 0.0, 1.0       // 0, 0, 1
    };

    // Default distortion (no distortion model for now)
    camera_info_.distortion_model = "plumb_bob";
    camera_info_.d = {0.0, 0.0, 0.0, 0.0, 0.0};

    // Rectification matrix (identity for now)
    camera_info_.r = {
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0
    };

    // Projection matrix
    camera_info_.p = {
        400.0, 0.0, 208.0, 0.0,
        0.0, 400.0, 208.0, 0.0,
        0.0, 0.0, 1.0, 0.0
    };

    pub_camera_info_->publish(camera_info_);
}

void CottonDetectionNode::publish_static_transforms()
{
    // Camera TF is already defined in URDF:
    // base_link -> link2 -> link4 -> link7 -> camera_mount_link -> camera_link
    // The robot_state_publisher publishes this complete chain based on joint states.
    // Publishing a static base_link->camera_link would:
    //   1. Create TF conflicts
    //   2. Bypass arm movement (joint3, joint4)
    //   3. Give incorrect detection coordinates
    // Therefore, we do NOT publish any transforms here.

    RCLCPP_INFO(this->get_logger(), "📍 Camera TF provided by URDF (via robot_state_publisher)");
}

} // namespace cotton_detection_ros2
