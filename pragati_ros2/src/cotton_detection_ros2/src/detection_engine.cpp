/**
 * @file detection_engine.cpp
 * @brief Detection orchestration implementation.
 *
 * Contains all detection logic previously spread across:
 *   - cotton_detection_node_detection.cpp (detect_cotton_in_image)
 *   - cotton_detection_node_depthai.cpp   (initialize/shutdown/get_depthai_detections, apply_config)
 *   - cotton_detection_node_utils.cpp     (save_input_image, save_output_image, draw_detections)
 *
 * Pure structural move — no logic changes.
 */

#include "cotton_detection_ros2/detection_engine.hpp"

#include "cotton_detection_ros2/performance_monitor.hpp"
#include "cotton_detection_ros2/async_image_saver.hpp"
#include "cotton_detection_ros2/async_json_logger.hpp"

// OpenCV
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>

// Standard library
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <thread>

// JSON structured logging
#include <nlohmann/json.hpp>
#include <common_utils/json_logging.hpp>

#ifdef HAS_DEPTHAI
#include "cotton_detection_ros2/depthai_manager.hpp"
#include "cotton_detection_ros2/thermal_guard.hpp"
#include <unistd.h>   // dup, dup2, close, STDERR_FILENO
#include <fcntl.h>    // open, O_WRONLY
#endif

using namespace std::chrono_literals;

namespace fs = std::filesystem;

// Helper macro for conditional timing logs
#define TIMING_LOG(logger_cb, verbose_flag, ...) \
    do { \
        if (verbose_flag) { \
            char buf[512]; \
            std::snprintf(buf, sizeof(buf), __VA_ARGS__); \
            logger_cb(cotton_detection::LogLevel::INFO, buf); \
        } \
    } while(0)

namespace cotton_detection_ros2
{

// ============================================================================
// Construction / Destruction
// ============================================================================

DetectionEngine::DetectionEngine(
    const DetectionConfig & config,
    cotton_detection::LoggerCallback logger_cb,
    PerformanceMonitor * performance_monitor,
    AsyncImageSaver * async_image_saver,
    AsyncJsonLogger * async_json_logger)
    : config_(config)
    , logger_cb_(std::move(logger_cb))
    , performance_monitor_(performance_monitor)
    , async_image_saver_(async_image_saver)
    , async_json_logger_(async_json_logger)
{
}

DetectionEngine::~DetectionEngine()
{
#ifdef HAS_DEPTHAI
    if (depthai_manager_) {
        shutdown_depthai();
    }
#endif
}

// ============================================================================
// Stats
// ============================================================================

DetectionStats DetectionEngine::getStats() const
{
    DetectionStats s;
    s.total_detect_requests = total_detect_requests_.load();
    s.total_detect_success = total_detect_success_.load();
    s.total_positions_returned = total_positions_returned_.load();
    s.total_detections_with_cotton = total_detections_with_cotton_.load();
    s.total_border_filtered = total_border_filtered_.load();
    s.total_non_pickable_filtered = total_non_pickable_filtered_.load();
    s.total_workspace_filtered = total_workspace_filtered_.load();
    s.total_cache_hits = total_cache_hits_.load();
    s.total_cache_misses = total_cache_misses_.load();
    s.total_reconnects = total_reconnects_.load();
    s.total_downtime_ms = total_downtime_ms_.load();
    s.total_sync_mismatches = total_sync_mismatches_.load();
    s.frame_wait_total_ms = frame_wait_total_ms_.load();
    s.frame_wait_count = frame_wait_count_.load();
    s.frame_wait_max_ms = frame_wait_max_ms_.load();
    s.consecutive_detection_timeouts = consecutive_detection_timeouts_.load();
    s.consecutive_rgb_timeouts = consecutive_rgb_timeouts_.load();
    s.last_successful_detection_time = last_successful_detection_time_;
    return s;
}

// ============================================================================
// Core Detection (moved from cotton_detection_node_detection.cpp)
// ============================================================================

bool DetectionEngine::detect_cotton_in_image(
    const cv::Mat & image, std::vector<geometry_msgs::msg::Point> & positions)
{
    (void)image;

    auto overall_start = std::chrono::steady_clock::now();
    last_detection_start_time_ = overall_start;

    positions.clear();

#ifdef HAS_DEPTHAI
    if (use_depthai_) {
        long detection_ms = 0;
        long frame_capture_ms = 0;
        long image_save_ms = 0;

        if (performance_monitor_) {
            performance_monitor_->start_operation("detection_depthai_direct");
        }

        // Step 1: Get detections from DepthAI
        std::vector<DepthAIDetectionResult> depthai_results;
        auto get_detections_start = std::chrono::steady_clock::now();
        bool success = get_depthai_detections(depthai_results);
        auto get_detections_end = std::chrono::steady_clock::now();
        detection_ms = std::chrono::duration_cast<std::chrono::milliseconds>(get_detections_end - get_detections_start).count();

        // Step 2: Get RGB frame for image saving (if enabled)
        cv::Mat rgb_frame;
        if (config_.save_input_image || config_.save_output_image) {
            auto frame_start = std::chrono::steady_clock::now();
            rgb_frame = depthai_manager_->getRGBFrame(std::chrono::milliseconds(100));
            auto frame_end = std::chrono::steady_clock::now();
            frame_capture_ms = std::chrono::duration_cast<std::chrono::milliseconds>(frame_end - frame_start).count();

            if (rgb_frame.empty()) {
                int timeouts = consecutive_rgb_timeouts_.fetch_add(1) + 1;
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "RGB frame timeout " + std::to_string(timeouts) + "/" +
                    std::to_string(MAX_CONSECUTIVE_TIMEOUTS) +
                    " (will force reconnect after " + std::to_string(MAX_CONSECUTIVE_TIMEOUTS) + " consecutive)");

                if (timeouts >= MAX_CONSECUTIVE_TIMEOUTS) {
                    logger_cb_(cotton_detection::LogLevel::ERROR,
                        "Camera degraded - " + std::to_string(timeouts) +
                        " consecutive RGB timeouts, forcing reconnection");
                    depthai_manager_->forceReconnection();
                    consecutive_rgb_timeouts_.store(0);
                    total_reconnects_.fetch_add(1);
                }
            } else {
                if (consecutive_rgb_timeouts_.load() > 0) {
                    logger_cb_(cotton_detection::LogLevel::INFO,
                        "RGB frame received - resetting timeout counter");
                }
                consecutive_rgb_timeouts_.store(0);
                last_successful_detection_time_ = std::chrono::steady_clock::now();
            }

            // Step 3: Save images
            if (!rgb_frame.empty()) {
                auto save_start = std::chrono::steady_clock::now();
                save_input_image(rgb_frame);
                if (!depthai_results.empty() || depthai_manager_) {
                    // Collect zero-spatial rejected detections for diagnostic annotation
                    std::vector<RejectedDetection> zero_spatial;
                    if (depthai_manager_) {
                        auto rejections = depthai_manager_->getLastZeroSpatialRejections();
                        int img_w = rgb_frame.cols;
                        int img_h = rgb_frame.rows;
                        zero_spatial.reserve(rejections.size());
                        for (const auto & r : rejections) {
                            RejectedDetection rd;
                            rd.x1 = static_cast<int>(r.x_min * img_w);
                            rd.y1 = static_cast<int>(r.y_min * img_h);
                            rd.x2 = static_cast<int>(r.x_max * img_w);
                            rd.y2 = static_cast<int>(r.y_max * img_h);
                            rd.confidence = r.confidence;
                            rd.label = r.label;
                            zero_spatial.push_back(rd);
                        }
                    }
                    save_output_image(rgb_frame, depthai_results, zero_spatial);
                }
                auto save_end = std::chrono::steady_clock::now();
                image_save_ms = std::chrono::duration_cast<std::chrono::milliseconds>(save_end - save_start).count();
            } else {
                logger_cb_(cotton_detection::LogLevel::WARN, "Failed to get RGB frame for saving");
            }
        }

        // Extract positions and confidences with filtering
        std::vector<float> confidences;
        std::vector<float> roi_pcts;
        const size_t raw_detections_this_frame = depthai_results.size();
        size_t border_filtered_this_frame = 0;
        size_t not_pickable_this_frame = 0;
        size_t workspace_filtered_this_frame = 0;

        for (const auto& result : depthai_results) {
            int effective_label = result.label;
            if (config_.depthai_swap_class_labels && config_.depthai_num_classes == 2) {
                effective_label = (result.label == 0) ? 1 : 0;
            }

            // Filter 1: not_pickable class
            if (config_.depthai_num_classes > 1 && effective_label != 0) {
                not_pickable_this_frame++;
                total_non_pickable_filtered_++;
                continue;
            }

            // Filter 2: Border detections
            if (config_.border_filter_enabled) {
                bool touches_border = (result.x_min < config_.border_margin ||
                                       result.y_min < config_.border_margin ||
                                       result.x_max > (1.0f - config_.border_margin) ||
                                       result.y_max > (1.0f - config_.border_margin));
                if (touches_border) {
                    border_filtered_this_frame++;
                    total_border_filtered_++;
                    continue;
                }
            }

            // Filter 3: Workspace bounds
            if (config_.workspace_filter_enabled) {
                const auto& pos = result.position;
                if (pos.x < 0.0 || pos.x > config_.workspace_max_x) {
                    workspace_filtered_this_frame++;
                    total_workspace_filtered_++;
                    continue;
                }
                if (std::abs(pos.y) > config_.workspace_max_y) {
                    workspace_filtered_this_frame++;
                    total_workspace_filtered_++;
                    continue;
                }
                if (pos.z < config_.workspace_min_z || pos.z > config_.workspace_max_z) {
                    workspace_filtered_this_frame++;
                    total_workspace_filtered_++;
                    continue;
                }
            }

            // Accept detection
            positions.push_back(result.position);
            confidences.push_back(result.confidence);
            float bbox_w = result.x_max - result.x_min;
            float bbox_h = result.y_max - result.y_min;
            float roi_pct = bbox_w * bbox_h * 100.0f;
            roi_pcts.push_back(roi_pct);
        }

        logger_cb_(cotton_detection::LogLevel::INFO,
            "Detections: raw=" + std::to_string(raw_detections_this_frame) +
            ", cotton_accepted=" + std::to_string(positions.size()) +
            ", border_skip=" + std::to_string(border_filtered_this_frame) +
            " (total:" + std::to_string(total_border_filtered_.load()) + ")" +
            ", not_pickable=" + std::to_string(not_pickable_this_frame) +
            " (total:" + std::to_string(total_non_pickable_filtered_.load()) + ")" +
            ", workspace_reject=" + std::to_string(workspace_filtered_this_frame) +
            " (total:" + std::to_string(total_workspace_filtered_.load()) + ")");

        if (performance_monitor_) {
            performance_monitor_->end_operation("detection_depthai_direct", success);
            if (success) {
                performance_monitor_->record_frame_processed("depthai_direct", positions.size());
            }
        }

        auto overall_end = std::chrono::steady_clock::now();
        long total_ms = std::chrono::duration_cast<std::chrono::milliseconds>(overall_end - overall_start).count();

        logger_cb_(cotton_detection::LogLevel::INFO,
            "Timing: detect=" + std::to_string(detection_ms) +
            "ms, frame=" + std::to_string(frame_capture_ms) +
            "ms, save=" + std::to_string(image_save_ms) +
            "ms, total=" + std::to_string(total_ms) + "ms");

        if (success && !positions.empty()) {
            logger_cb_(cotton_detection::LogLevel::INFO,
                "Detected " + std::to_string(positions.size()) + " cotton positions");
            {
                std::lock_guard<std::mutex> conf_lock(confidences_mutex_);
                last_detection_confidences_ = confidences;
            }
        } else if (success) {
            logger_cb_(cotton_detection::LogLevel::INFO, "No cotton detected in this frame");
        } else {
            logger_cb_(cotton_detection::LogLevel::WARN, "DepthAI detection failed, no detections available");
        }

        // Structured JSON log line for post-trial analysis
        // Moved to background thread to keep getStats() USB calls off the detection hot path
        if (async_json_logger_) {
            // Capture all data by value — these are cheap (ints, floats, small vectors)
            auto captured_seq = total_detect_requests_.load();
            auto captured_detection_age_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                overall_end - get_detections_end).count();
            auto captured_positions = positions;
            auto captured_confidences = confidences;
            auto captured_roi_pcts = roi_pcts;
            auto captured_success = success;
            auto captured_raw = raw_detections_this_frame;
            auto captured_border = border_filtered_this_frame;
            auto captured_not_pickable = not_pickable_this_frame;
            auto captured_workspace = workspace_filtered_this_frame;
            auto captured_detection_ms = detection_ms;
            auto captured_frame_capture_ms = frame_capture_ms;
            auto captured_image_save_ms = image_save_ms;
            auto captured_total_ms = total_ms;
            // Capture depthai_manager raw pointer — safe because node outlives the logger
            auto* captured_depthai = (use_depthai_.load()) ? depthai_manager_.get() : nullptr;

            async_json_logger_->log_async([=]() -> nlohmann::json {
                nlohmann::json positions_json = nlohmann::json::array();
                for (size_t i = 0; i < captured_positions.size(); ++i) {
                    nlohmann::json pos;
                    pos["x"] = captured_positions[i].x;
                    pos["y"] = captured_positions[i].y;
                    pos["z"] = captured_positions[i].z;
                    pos["confidence"] = (i < captured_confidences.size()) ? captured_confidences[i] : 0.0f;
                    pos["roi_pct"] = (i < captured_roi_pcts.size()) ? captured_roi_pcts[i] : 0.0f;
                    positions_json.push_back(pos);
                }

                nlohmann::json j = pragati::json_envelope("detection_frame", "detection_engine");
                j["seq"] = captured_seq;
                j["detection_age_ms"] = captured_detection_age_ms;
                j["timing_ms"] = {
                    {"detect", captured_detection_ms},
                    {"frame_capture", captured_frame_capture_ms},
                    {"image_save", captured_image_save_ms},
                    {"total", captured_total_ms}
                };
                j["detections"] = {
                    {"raw", captured_raw},
                    {"accepted", captured_positions.size()},
                    {"border_filtered", captured_border},
                    {"not_pickable", captured_not_pickable},
                    {"workspace_filtered", captured_workspace}
                };
                j["positions"] = positions_json;
                j["success"] = captured_success;
                if (captured_depthai) {
                    auto cam_stats_frame = captured_depthai->getStats();
                    j["exposure_us"] = cam_stats_frame.last_exposure_us;
                    j["sensitivity_iso"] = cam_stats_frame.last_sensitivity_iso;
                }
                return j;
            });
        } else {
            // Fallback: synchronous logging if no async logger configured
            auto detection_age_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                overall_end - get_detections_end).count();

            nlohmann::json positions_json = nlohmann::json::array();
            for (size_t i = 0; i < positions.size(); ++i) {
                nlohmann::json pos;
                pos["x"] = positions[i].x;
                pos["y"] = positions[i].y;
                pos["z"] = positions[i].z;
                pos["confidence"] = (i < confidences.size()) ? confidences[i] : 0.0f;
                pos["roi_pct"] = (i < roi_pcts.size()) ? roi_pcts[i] : 0.0f;
                positions_json.push_back(pos);
            }

            nlohmann::json j = pragati::json_envelope("detection_frame", "detection_engine");
            j["seq"] = total_detect_requests_.load();
            j["detection_age_ms"] = detection_age_ms;
            j["timing_ms"] = {
                {"detect", detection_ms},
                {"frame_capture", frame_capture_ms},
                {"image_save", image_save_ms},
                {"total", total_ms}
            };
            j["detections"] = {
                {"raw", raw_detections_this_frame},
                {"accepted", positions.size()},
                {"border_filtered", border_filtered_this_frame},
                {"not_pickable", not_pickable_this_frame},
                {"workspace_filtered", workspace_filtered_this_frame}
            };
            j["positions"] = positions_json;
            j["success"] = success;
            if (use_depthai_ && depthai_manager_) {
                auto cam_stats_frame = depthai_manager_->getStats();
                j["exposure_us"] = cam_stats_frame.last_exposure_us;
                j["sensitivity_iso"] = cam_stats_frame.last_sensitivity_iso;
            }

            logger_cb_(cotton_detection::LogLevel::INFO, j.dump());
        }

        return success;
    }
#endif

    logger_cb_(cotton_detection::LogLevel::ERROR,
        "DepthAI not available. Detection requires DepthAI camera.");
    return false;
}

// ============================================================================
// DepthAI Lifecycle (moved from cotton_detection_node_depthai.cpp)
// ============================================================================

#ifdef HAS_DEPTHAI

bool DetectionEngine::initialize_depthai()
{
    logger_cb_(cotton_detection::LogLevel::INFO, "Initializing DepthAI C++ integration...");

    try {
        cotton_detection::CameraConfig cam_config;
        std::string model_path;
        {
            std::scoped_lock<std::mutex> depth_lock(depthai_config_mutex_);
            use_depthai_ = config_.depthai_enable;
            if (!use_depthai_) {
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "DepthAI C++ integration DISABLED (using Python wrapper)");
                return false;
            }

            model_path = config_.depthai_model_path;
            cam_config.width = config_.depthai_camera_width;
            cam_config.height = config_.depthai_camera_height;
            cam_config.fps = config_.depthai_camera_fps;
            cam_config.num_classes = config_.depthai_num_classes;
            cam_config.confidence_threshold = config_.depthai_confidence_threshold;
            cam_config.depth_min_mm = config_.depthai_depth_min_mm;
            cam_config.depth_max_mm = config_.depthai_depth_max_mm;
            cam_config.enable_depth = config_.depthai_enable_depth;
            cam_config.device_id = config_.depthai_device_id;
            cam_config.exposure_mode = config_.exposure_mode;
            cam_config.exposure_time_us = config_.exposure_time_us;
            cam_config.exposure_iso = config_.exposure_iso;
            cam_config.keep_aspect_ratio = config_.depthai_keep_aspect_ratio;
            cam_config.stereo_confidence_threshold = config_.depthai_stereo_confidence_threshold;
            cam_config.bbox_scale_factor = config_.depthai_bbox_scale_factor;
            cam_config.extended_disparity = config_.depthai_extended_disparity;
            cam_config.spatial_calc_algorithm = config_.depthai_spatial_calc_algorithm;
            cam_config.mono_resolution = config_.depthai_mono_resolution;
            cam_config.lr_check = config_.depthai_lr_check;
            cam_config.subpixel = config_.depthai_subpixel;
            cam_config.median_filter = config_.depthai_median_filter;
        }

        depthai_manager_ = std::make_unique<cotton_detection::DepthAIManager>();
        depthai_manager_->setLogger(logger_cb_);

        logger_cb_(cotton_detection::LogLevel::INFO, "Initializing DepthAI pipeline...");
        if (!depthai_manager_->initialize(model_path, cam_config)) {
            throw std::runtime_error("DepthAIManager::initialize() failed");
        }

        logger_cb_(cotton_detection::LogLevel::INFO, "DepthAI initialization SUCCESS");
        {
            char buf[256];
            std::snprintf(buf, sizeof(buf),
                "Resolution: %dx%d @ %d FPS, Confidence: %.2f, Depth: %.0f-%.0fmm",
                cam_config.width, cam_config.height, cam_config.fps,
                cam_config.confidence_threshold, cam_config.depth_min_mm, cam_config.depth_max_mm);
            logger_cb_(cotton_detection::LogLevel::INFO, buf);
        }
        logger_cb_(cotton_detection::LogLevel::INFO, depthai_manager_->getDeviceInfo());

        {
            char buf[128];
            std::snprintf(buf, sizeof(buf), "Camera: RGB 4MP, Stereo 400p, NN %dx%d, Depth %s",
                cam_config.width, cam_config.height, cam_config.enable_depth ? "ON" : "OFF");
            logger_cb_(cotton_detection::LogLevel::INFO, buf);
        }

        logger_cb_(cotton_detection::LogLevel::INFO,
            "Warming up pipeline (" + std::to_string(config_.depthai_warmup_seconds) + " seconds)...");
        // BLOCKING_SLEEP_OK: DepthAI warmup (default 3s), executor-thread at runtime (startup: main thread) — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::seconds(config_.depthai_warmup_seconds));

        logger_cb_(cotton_detection::LogLevel::INFO, "Flushing warm-up frames from all queues...");
        int flushed = depthai_manager_->flushAllQueues();
        logger_cb_(cotton_detection::LogLevel::INFO,
            "Pipeline ready! (flushed " + std::to_string(flushed) + " frames from all queues)");

        logger_cb_(cotton_detection::LogLevel::INFO,
            "Detection mode: DepthAI Direct (using C++ DepthAI pipeline)");

        {
            std::scoped_lock<std::mutex> depth_lock(depthai_config_mutex_);
            apply_depthai_runtime_config_locked();
        }

        // Initialize ThermalGuard
        {
            cotton_detection::ThermalGuard::Config tg_config;
            tg_config.warning_temp = config_.thermal_warning_temp_c;
            tg_config.throttle_temp = config_.thermal_throttle_temp_c;
            tg_config.critical_temp = config_.thermal_critical_temp_c;
            tg_config.hysteresis = 5.0;

            auto temp_source = [this]() -> double {
                if (depthai_manager_) {
                    return depthai_manager_->getStats().temperature_celsius;
                }
                return 0.0;
            };

            thermal_guard_ = std::make_unique<cotton_detection::ThermalGuard>(
                temp_source, tg_config);

            thermal_guard_->onStatusChange(
                [this](cotton_detection::ThermalStatus old_s,
                       cotton_detection::ThermalStatus new_s) {
                    auto status_name = [](cotton_detection::ThermalStatus s) -> const char* {
                        switch (s) {
                            case cotton_detection::ThermalStatus::Normal: return "Normal";
                            case cotton_detection::ThermalStatus::Warning: return "Warning";
                            case cotton_detection::ThermalStatus::Throttle: return "Throttle";
                            case cotton_detection::ThermalStatus::Critical: return "Critical";
                        }
                        return "Unknown";
                    };
                    char buf[128];
                    std::snprintf(buf, sizeof(buf),
                        "Thermal transition: %s -> %s (%.1f C)",
                        status_name(old_s), status_name(new_s),
                        thermal_guard_->getCurrentTemperature());
                    logger_cb_(cotton_detection::LogLevel::WARN, buf);
                });

            {
                char buf[128];
                std::snprintf(buf, sizeof(buf),
                    "ThermalGuard initialized (warn=%.0f, throttle=%.0f, critical=%.0f, hysteresis=%.0f)",
                    tg_config.warning_temp, tg_config.throttle_temp,
                    tg_config.critical_temp, tg_config.hysteresis);
                logger_cb_(cotton_detection::LogLevel::INFO, buf);
            }
        }

        // Auto-pause if configured
        if (config_.depthai_auto_pause_after_detection) {
            logger_cb_(cotton_detection::LogLevel::INFO,
                "Auto-pause enabled: Starting camera in PAUSED state");
            try {
                depthai_manager_->pauseCamera();
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "Camera paused - will resume on detect command");
            } catch (const std::logic_error& e) {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    std::string("Failed to pause camera at startup: ") + e.what());
            }
        }

        return true;

    } catch (const std::exception& e) {
        logger_cb_(cotton_detection::LogLevel::ERROR,
            std::string("DepthAI exception: ") + e.what());
        logger_cb_(cotton_detection::LogLevel::ERROR,
            "No fallback available - DepthAI C++ is required!");
        use_depthai_ = false;
        depthai_manager_.reset();
        throw;
    }
}

void DetectionEngine::shutdown_depthai()
{
    if (depthai_manager_) {
        logger_cb_(cotton_detection::LogLevel::INFO, "Shutting down DepthAI...");

        // WORKAROUND: DepthAI stderr suppression during shutdown
        int stderr_backup = dup(STDERR_FILENO);
        int devnull = open("/dev/null", O_WRONLY);
        dup2(devnull, STDERR_FILENO);
        close(devnull);

        depthai_manager_->shutdown();
        depthai_manager_.reset();

        // BLOCKING_SLEEP_OK: post-shutdown drain 100ms, executor-thread at runtime (cleanup: main thread) — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        dup2(stderr_backup, STDERR_FILENO);
        close(stderr_backup);
    }
    use_depthai_ = false;
}

bool DetectionEngine::get_depthai_detections(std::vector<DepthAIDetectionResult> & detections)
{
    if (!use_depthai_ || !depthai_manager_) {
        return false;
    }

    // AUTO-RECONNECTION
    if (depthai_manager_->needsReconnect()) {
        logger_cb_(cotton_detection::LogLevel::WARN,
            "DepthAI device needs reconnection (X_LINK_ERROR detected)");

        constexpr int max_retries = 3;
        int retry_delay_ms = 2000;
        bool reconnected = false;

        for (int attempt = 1; attempt <= max_retries; ++attempt) {
            logger_cb_(cotton_detection::LogLevel::INFO,
                "Reconnection attempt " + std::to_string(attempt) + "/" + std::to_string(max_retries) + "...");

            try {
                if (depthai_manager_->reconnect()) {
                    logger_cb_(cotton_detection::LogLevel::INFO,
                        "DepthAI reconnection successful on attempt " + std::to_string(attempt));
                    reconnected = true;

                    auto stats = depthai_manager_->getStats();
                    total_downtime_ms_.store(stats.total_downtime_ms.count());
                    total_reconnects_.store(stats.reconnect_count);

                    logger_cb_(cotton_detection::LogLevel::INFO,
                        "Warming up pipeline after reconnection...");
                    // BLOCKING_SLEEP_OK: post-reconnect warmup 1s, executor-thread (detection_group_) — reviewed 2026-03-14
                    std::this_thread::sleep_for(std::chrono::seconds(1));

                    int flushed = depthai_manager_->flushAllQueues();
                    logger_cb_(cotton_detection::LogLevel::INFO,
                        "Pipeline ready (flushed " + std::to_string(flushed) + " frames from all queues)");
                    break;
                }
            } catch (const std::logic_error& e) {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "Reconnection attempt " + std::to_string(attempt) + " rejected: " + e.what());
            } catch (const std::exception& e) {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "Reconnection attempt " + std::to_string(attempt) + " failed: " + e.what());
            }

            if (attempt < max_retries) {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "Reconnection attempt " + std::to_string(attempt) +
                    " failed, waiting " + std::to_string(retry_delay_ms) + " ms before retry...");
                // BLOCKING_SLEEP_OK: reconnect backoff 2-8s, executor-thread (detection_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(retry_delay_ms));
                retry_delay_ms *= 2;
            }
        }

        if (!reconnected) {
            logger_cb_(cotton_detection::LogLevel::ERROR,
                "DepthAI reconnection failed after " + std::to_string(max_retries) + " attempts");
            return false;
        }
    }

    try {
        // Verbose pre-capture status
        if (config_.verbose_timing) {
            auto stats = depthai_manager_->getStats();
            char buf[256];
            std::snprintf(buf, sizeof(buf),
                "Pre-Capture: Temp=%.1fC, FPS=%.1f, Frames=%lu, Detections=%zu, Latency=%ldms, Uptime=%.1fs",
                stats.temperature_celsius, stats.fps, stats.frames_processed,
                stats.detection_count, stats.avg_latency.count(), stats.uptime.count() / 1000.0);
            logger_cb_(cotton_detection::LogLevel::INFO, buf);
        }

        auto get_depthai_start = std::chrono::steady_clock::now();

        std::optional<std::vector<cotton_detection::CottonDetection>> latest_detections;
        int frames_flushed = 0;

        if (config_.depthai_flush_before_read) {
            frames_flushed = depthai_manager_->flushAllQueues();
            // BLOCKING_SLEEP_OK: frame flush wait 120ms, executor-thread (detection_group_) — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::milliseconds(120));
            latest_detections = depthai_manager_->getDetections(
                std::chrono::milliseconds(config_.depthai_detection_timeout_ms));
        } else {
            frames_flushed = depthai_manager_->flushAllQueues();

            if (frames_flushed > 0 && config_.verbose_timing) {
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "Flushed " + std::to_string(frames_flushed) +
                    " stale frames from all queues (detection+rgb+depth)");
            }

            latest_detections = depthai_manager_->getDetections(
                std::chrono::milliseconds(config_.depthai_detection_timeout_ms));
        }

        auto get_depthai_end = std::chrono::steady_clock::now();
        auto get_depthai_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            get_depthai_end - get_depthai_start).count();

        logger_cb_(cotton_detection::LogLevel::INFO,
            "Frame freshness: flushed " + std::to_string(frames_flushed) +
            " stale (all queues), waited " + std::to_string(get_depthai_ms) +
            " ms for fresh detection");

        // Track frame wait stats
        frame_wait_total_ms_.fetch_add(static_cast<uint64_t>(get_depthai_ms));
        frame_wait_count_.fetch_add(1);
        uint64_t current_max = frame_wait_max_ms_.load();
        while (static_cast<uint64_t>(get_depthai_ms) > current_max &&
               !frame_wait_max_ms_.compare_exchange_weak(current_max, static_cast<uint64_t>(get_depthai_ms)));

        // Track consecutive detection timeouts
        const long DETECTION_TIMEOUT_THRESHOLD_MS = config_.depthai_detection_timeout_ms - 5;
        if (get_depthai_ms >= DETECTION_TIMEOUT_THRESHOLD_MS && !latest_detections) {
            int timeouts = consecutive_detection_timeouts_.fetch_add(1) + 1;
            logger_cb_(cotton_detection::LogLevel::WARN,
                "Detection timeout " + std::to_string(timeouts) + "/" +
                std::to_string(MAX_CONSECUTIVE_TIMEOUTS) +
                " (waited " + std::to_string(get_depthai_ms) + "ms)");

            if (timeouts >= MAX_CONSECUTIVE_TIMEOUTS) {
                logger_cb_(cotton_detection::LogLevel::ERROR,
                    "Camera degraded - " + std::to_string(timeouts) +
                    " consecutive detection timeouts, forcing reconnection");
                depthai_manager_->forceReconnection();
                consecutive_detection_timeouts_.store(0);
            }
        } else if (latest_detections) {
            if (consecutive_detection_timeouts_.load() > 0) {
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "Detection received - resetting timeout counter");
            }
            consecutive_detection_timeouts_.store(0);
            last_successful_detection_time_ = std::chrono::steady_clock::now();
        }

        if (!latest_detections || latest_detections->empty()) {
            if (depthai_manager_->needsReconnect()) {
                logger_cb_(cotton_detection::LogLevel::ERROR,
                    "Detection failed due to camera communication error (XLink)");
                return false;
            }
            return true;  // No detections is not an error
        }

        auto& depthai_detections = *latest_detections;

        for (const auto& det : depthai_detections) {
            DepthAIDetectionResult result;

            // RUF -> FLU coordinate conversion, mm -> m
            result.position.x = det.spatial_z / 1000.0;
            result.position.y = -det.spatial_x / 1000.0;
            result.position.z = det.spatial_y / 1000.0;
            result.confidence = std::clamp(det.confidence, 0.0f, 1.0f);

            result.x_min = det.x_min;
            result.y_min = det.y_min;
            result.x_max = det.x_max;
            result.y_max = det.y_max;

            bool is_cotton = false;
            if (config_.depthai_num_classes > 1) {
                is_cotton = (det.label == 0);
                result.label = det.label;
            } else {
                is_cotton = true;
                result.label = 0;
            }
            (void)is_cotton;  // Used only in logging (suppressed in engine)

            detections.push_back(result);
        }

        return true;

    } catch (const std::exception& e) {
        logger_cb_(cotton_detection::LogLevel::ERROR,
            std::string("DepthAI detection error: ") + e.what());
        return false;
    }
}

bool DetectionEngine::apply_depthai_runtime_config_locked()
{
    if (!depthai_manager_) {
        return false;
    }

    bool applied = depthai_manager_->setDepthEnabled(config_.depthai_enable_depth);
    applied = depthai_manager_->setConfidenceThreshold(config_.depthai_confidence_threshold) && applied;
    if (config_.depthai_enable_depth) {
        applied = depthai_manager_->setDepthRange(
            static_cast<float>(config_.depthai_depth_min_mm),
            static_cast<float>(config_.depthai_depth_max_mm)) && applied;
    }
    return applied;
}

// ============================================================================
// Image Saving (moved from cotton_detection_node_utils.cpp)
// ============================================================================

void DetectionEngine::save_input_image(const cv::Mat & image)
{
    if (!config_.save_input_image || image.empty()) {
        return;
    }

    try {
        // Note: get_timestamped_filename is now provided by ServiceHandler.
        // For DetectionEngine, we use a simple timestamp format directly.
        std::string filename;
        if (config_.file_save_mode_timestamp) {
            auto now = std::chrono::system_clock::now();
            std::time_t now_c = std::chrono::system_clock::to_time_t(now);
            std::tm tm{};
            localtime_r(&now_c, &tm);
            char buf[64];
            std::strftime(buf, sizeof(buf), "%Y-%m-%d_%H-%M-%S", &tm);
            filename = std::string("img_") + buf + ".jpg";
        } else {
            filename = "img100.jpg";
        }
        fs::path filepath = fs::path(config_.input_dir) / filename;

        if (config_.save_async && async_image_saver_) {
            bool queued = async_image_saver_->save_async(image, filepath.string());
            if (queued) {
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "Saved input image: " + filepath.string());
            } else {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "Async image saver queue full - input image dropped: " + filepath.string());
            }
        } else {
            bool success = cv::imwrite(filepath.string(), image);
            if (success) {
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "Saved input image: " + filepath.string());
            } else {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "Failed to save input image: " + filepath.string());
            }
        }
    } catch (const std::exception & e) {
        logger_cb_(cotton_detection::LogLevel::ERROR,
            std::string("Error saving input image: ") + e.what());
    }
}

void DetectionEngine::save_output_image(const cv::Mat & image,
    const std::vector<DepthAIDetectionResult> & detections,
    const std::vector<RejectedDetection> & zero_spatial)
{
    if (!config_.save_output_image || image.empty()) {
        return;
    }

    try {
        cv::Mat output_image = draw_detections_on_image(image, detections, zero_spatial);

        std::string filename;
        if (config_.file_save_mode_timestamp) {
            auto now = std::chrono::system_clock::now();
            std::time_t now_c = std::chrono::system_clock::to_time_t(now);
            std::tm tm{};
            localtime_r(&now_c, &tm);
            char buf[64];
            std::strftime(buf, sizeof(buf), "%Y-%m-%d_%H-%M-%S", &tm);
            filename = std::string("DetectionOutput_") + buf + ".jpg";
        } else {
            filename = "DetectionOutput.jpg";
        }
        fs::path filepath = fs::path(config_.output_dir) / filename;

        if (config_.save_async && async_image_saver_) {
            bool queued = async_image_saver_->save_async(output_image, filepath.string());
            if (queued) {
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "Saved output image: " + filepath.string() +
                    " (" + std::to_string(detections.size()) + " detections)");
            } else {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "Async image saver queue full - output image dropped: " + filepath.string());
            }
        } else {
            bool success = cv::imwrite(filepath.string(), output_image);
            if (success) {
                logger_cb_(cotton_detection::LogLevel::INFO,
                    "Saved output image: " + filepath.string() +
                    " (" + std::to_string(detections.size()) + " detections)");
            } else {
                logger_cb_(cotton_detection::LogLevel::WARN,
                    "Failed to save output image: " + filepath.string());
            }
        }
    } catch (const std::exception & e) {
        logger_cb_(cotton_detection::LogLevel::ERROR,
            std::string("Error saving output image: ") + e.what());
    }
}

cv::Mat DetectionEngine::draw_detections_on_image(const cv::Mat & image,
    const std::vector<DepthAIDetectionResult> & detections,
    const std::vector<RejectedDetection> & zero_spatial)
{
    if (detections.empty() && zero_spatial.empty()) {
        return image.clone();
    }

    cv::Mat vis = image.clone();
    int img_width = image.cols;
    int img_height = image.rows;

    for (size_t i = 0; i < detections.size(); ++i) {
        const auto & det = detections[i];

        int x1 = static_cast<int>(det.x_min * img_width);
        int y1 = static_cast<int>(det.y_min * img_height);
        int x2 = static_cast<int>(det.x_max * img_width);
        int y2 = static_cast<int>(det.y_max * img_height);

        x1 = std::max(0, std::min(img_width - 1, x1));
        y1 = std::max(0, std::min(img_height - 1, y1));
        x2 = std::max(0, std::min(img_width - 1, x2));
        y2 = std::max(0, std::min(img_height - 1, y2));

        cv::Scalar box_color, point_color;
        std::string class_name;

        if (det.label == 0) {
            box_color = cv::Scalar(0, 255, 0);
            point_color = cv::Scalar(0, 255, 0);
            class_name = "cotton";
        } else if (det.label == 1) {
            box_color = cv::Scalar(0, 0, 255);
            point_color = cv::Scalar(0, 0, 255);
            class_name = "not_pickable";
        } else {
            box_color = cv::Scalar(0, 255, 255);
            point_color = cv::Scalar(0, 255, 255);
            class_name = "unknown";
        }

        cv::rectangle(vis, cv::Point(x1, y1), cv::Point(x2, y2), box_color, 2);

        int center_x = (x1 + x2) / 2;
        int center_y = (y1 + y2) / 2;
        cv::circle(vis, cv::Point(center_x, center_y), 4, point_color, -1);

        char label_buf[64];
        std::snprintf(label_buf, sizeof(label_buf), "%s %.2f (%.2fm)",
                     class_name.c_str(), det.confidence, det.position.x);
        std::string label(label_buf);

        int baseline = 0;
        cv::Size text_size = cv::getTextSize(label, cv::FONT_HERSHEY_SIMPLEX, 0.5, 1, &baseline);
        cv::Point text_org(center_x + 25, center_y - 10);

        if (text_org.x + text_size.width >= img_width) {
            text_org.x = center_x - text_size.width - 25;
        }
        if (text_org.y - text_size.height < 0) {
            text_org.y = center_y + text_size.height + 10;
        }

        cv::rectangle(vis,
                     cv::Point(text_org.x - 3, text_org.y - text_size.height - 3),
                     cv::Point(text_org.x + text_size.width + 3, text_org.y + baseline + 3),
                     box_color, cv::FILLED);

        cv::putText(vis, label, text_org, cv::FONT_HERSHEY_SIMPLEX, 0.5,
                   cv::Scalar(0, 0, 0), 1, cv::LINE_AA);
    }

    // Draw zero-spatial rejected detections with red boxes and "DEPTH FAIL" label
    for (const auto & rej : zero_spatial) {
        int rx1 = std::max(0, std::min(img_width - 1, rej.x1));
        int ry1 = std::max(0, std::min(img_height - 1, rej.y1));
        int rx2 = std::max(0, std::min(img_width - 1, rej.x2));
        int ry2 = std::max(0, std::min(img_height - 1, rej.y2));

        cv::Scalar reject_color(0, 0, 255);  // Red in BGR
        cv::rectangle(vis, cv::Point(rx1, ry1), cv::Point(rx2, ry2), reject_color, 2);

        char rej_label_buf[64];
        std::snprintf(rej_label_buf, sizeof(rej_label_buf), "DEPTH FAIL %.2f", rej.confidence);
        std::string rej_label(rej_label_buf);

        int rej_center_x = (rx1 + rx2) / 2;
        int rej_center_y = (ry1 + ry2) / 2;

        int rej_baseline = 0;
        cv::Size rej_text_size = cv::getTextSize(rej_label, cv::FONT_HERSHEY_SIMPLEX, 0.5, 1, &rej_baseline);
        cv::Point rej_text_org(rej_center_x + 25, rej_center_y - 10);

        if (rej_text_org.x + rej_text_size.width >= img_width) {
            rej_text_org.x = rej_center_x - rej_text_size.width - 25;
        }
        if (rej_text_org.y - rej_text_size.height < 0) {
            rej_text_org.y = rej_center_y + rej_text_size.height + 10;
        }

        cv::rectangle(vis,
                     cv::Point(rej_text_org.x - 3, rej_text_org.y - rej_text_size.height - 3),
                     cv::Point(rej_text_org.x + rej_text_size.width + 3, rej_text_org.y + rej_baseline + 3),
                     reject_color, cv::FILLED);

        cv::putText(vis, rej_label, rej_text_org, cv::FONT_HERSHEY_SIMPLEX, 0.5,
                   cv::Scalar(255, 255, 255), 1, cv::LINE_AA);
    }

    char summary[128];
    std::snprintf(summary, sizeof(summary), "Detections: %zu  Depth Fail: %zu",
                 detections.size(), zero_spatial.size());
    cv::putText(vis, summary, cv::Point(10, 30), cv::FONT_HERSHEY_SIMPLEX, 1.0,
               cv::Scalar(0, 255, 0), 2, cv::LINE_AA);

    return vis;
}

#endif  // HAS_DEPTHAI

}  // namespace cotton_detection_ros2
