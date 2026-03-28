#include "cotton_detection_ros2/service_handler.hpp"

#include "cotton_detection_ros2/detection_engine.hpp"
#include "cotton_detection_ros2/performance_monitor.hpp"

#include <rclcpp/rclcpp.hpp>  // RCLCPP_INFO, RCLCPP_WARN, etc.

#ifdef HAS_DEPTHAI
#include "cotton_detection_ros2/depthai_manager.hpp"
#endif

// Specific OpenCV includes (avoid mega-include for faster builds)
#include <opencv2/core.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <filesystem>
#include <random>
#include <thread>  // For std::this_thread::sleep_for

namespace cotton_detection_ros2
{

namespace fs = std::filesystem;

ServiceHandler::ServiceHandler(NodeInterface iface, const ServiceConfig & config)
    : iface_(std::move(iface))
    , config_(config)
{
    if (config_.simulation_mode) {
        simulation_rng_.seed(std::random_device{}());
    }
}

ServiceHandler::~ServiceHandler() = default;

void ServiceHandler::handle_cotton_detection(
    const std::shared_ptr<cotton_detection_msgs::srv::CottonDetection::Request> request,
    std::shared_ptr<cotton_detection_msgs::srv::CottonDetection::Response> response)
{
    // Check for shutdown - return immediately if shutting down
    if (iface_.shutdown_requested.load()) {
        RCLCPP_WARN(iface_.logger, "🛑 Detection request ignored - node shutting down");
        response->success = false;
        response->message = "Node is shutting down";
        return;
    }

    // First request is warmup from yanthra_move - skip stats but still process
    const bool is_warmup = !iface_.warmup_completed.exchange(true);

    // Task 7.6: Update last request time for idle detection
    iface_.last_request_time = std::chrono::steady_clock::now();
    if (iface_.idle_state.load()) {
        iface_.idle_state.store(false);
        RCLCPP_INFO(iface_.logger, "Resuming from idle state - detection request received");
    }

    // Track total detection requests (service-level), skip warmup
    uint64_t req_id = 0;
    if (!is_warmup) {
        iface_.detection_engine->incrementDetectRequests();
        req_id = iface_.detection_engine->getStats().total_detect_requests;
    }

    if (is_warmup) {
        RCLCPP_INFO(iface_.logger, "🔥 Warmup detection request (not counted in stats): command=%d", request->detect_command);
    } else {
        auto receipt_epoch_us = std::chrono::duration_cast<std::chrono::microseconds>(  // INSTRUMENTATION
            std::chrono::steady_clock::now().time_since_epoch()).count();  // INSTRUMENTATION
        RCLCPP_INFO(iface_.logger, "🔍 Detection request #%lu: command=%d INSTRUMENTATION receipt_epoch_us=%ld", req_id, request->detect_command, receipt_epoch_us);  // INSTRUMENTATION
    }

    if (iface_.performance_monitor) {
        iface_.performance_monitor->start_operation("service_request");
    }

    auto start_time = std::chrono::high_resolution_clock::now();

    // Process the detection request
    std::vector<int32_t> result_data;
    bool success = process_detection_request(request->detect_command, result_data);

    auto end_time = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);

    // Fill response
    response->data = result_data;
    response->success = success;
    response->message = success ? "Detection completed successfully" : "Detection failed";

    // Update counters (skip warmup)
    if (!is_warmup) {
        if (success) {
            iface_.detection_engine->incrementDetectSuccess();
        }
        const size_t pos_count = result_data.size() / 3;  // x,y,z triplets
        if (pos_count > 0) {
            iface_.detection_engine->addPositionsReturned(pos_count);
            iface_.detection_engine->incrementDetectionsWithCotton();  // Track detections that found cotton
        }
    }

    if (iface_.performance_monitor) {
        iface_.performance_monitor->end_operation("service_request", success);
    }

    const size_t positions = result_data.size() / 3;
    if (is_warmup) {
        RCLCPP_INFO(iface_.logger, "✅ Warmup completed in %ld ms, positions=%zu",
                    duration.count(), positions);
    } else {
        RCLCPP_INFO(iface_.logger, "✅ Detection request #%lu completed in %ld ms, positions=%zu",
                    req_id, duration.count(), positions);
    }

    // NOTE: Performance report is now merged into periodic stats (stats_log_callback)
    // which runs every stats_log_interval_sec (default 30s) regardless of request count
}

bool ServiceHandler::process_detection_request(int32_t command, std::vector<int32_t> & result_data)
{
    result_data.clear();

    switch (command) {
        case 0: // Stop detection
            iface_.detection_active = false;
            RCLCPP_INFO(iface_.logger, "🛑 Detection stopped");
            return true;

        case 1: // Start detection
        {
            iface_.detection_active = true;

            // Simulation mode: return configured positions with optional noise
            if (config_.simulation_mode) {
                std::vector<geometry_msgs::msg::Point> positions;
                std::normal_distribution<double> noise_dist(0.0, config_.simulation_noise_stddev);
                std::uniform_real_distribution<double> conf_dist(
                    config_.simulation_confidence_min, config_.simulation_confidence_max);

                {
                    std::lock_guard<std::mutex> lock(iface_.detection_engine->getConfidencesMutex());
                    iface_.detection_engine->getLastDetectionConfidences().clear();
                    for (const auto & base_pos : config_.simulated_positions) {
                        geometry_msgs::msg::Point pos;
                        if (config_.simulation_noise_stddev > 0.0) {
                            pos.x = base_pos.x + noise_dist(simulation_rng_);
                            pos.y = base_pos.y + noise_dist(simulation_rng_);
                            pos.z = base_pos.z + noise_dist(simulation_rng_);
                        } else {
                            pos = base_pos;
                        }
                        positions.push_back(pos);
                        iface_.detection_engine->getLastDetectionConfidences().push_back(
                            static_cast<float>(conf_dist(simulation_rng_)));
                    }
                }

                // Convert to int32 mm format (same as production path)
                for (const auto & pos : positions) {
                    result_data.push_back(static_cast<int32_t>(pos.x * 1000));
                    result_data.push_back(static_cast<int32_t>(pos.y * 1000));
                    result_data.push_back(static_cast<int32_t>(pos.z * 1000));
                }

                // Simulate brief processing delay
                // BLOCKING_SLEEP_OK: simulation-only 5ms delay, executor-thread (detection_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(5));

                RCLCPP_INFO(iface_.logger,
                    "SIMULATION: Returning %zu simulated cotton positions",
                    positions.size());

                // Publish on topic (same as production path)
                if (iface_.publish_result_fn) {
                    iface_.publish_result_fn(positions, true);
                }
                return true;
            }

            // Check cache first (prevents redundant processing for rapid repeated calls)
            {
                std::lock_guard<std::mutex> cache_lock(iface_.detection_engine->getCacheMutex());
                if (iface_.detection_engine->getCachedDetection().has_value()) {
                    const auto now = iface_.clock->now();
                    const auto age_ms = (now - iface_.detection_engine->getCachedDetection()->timestamp).seconds() * 1000.0;

                    if (age_ms < iface_.detection_engine->getConfig().cache_validity_ms) {
                        RCLCPP_DEBUG(iface_.logger, "💾 Using cached result (age: %.1f ms)", age_ms);
                        iface_.detection_engine->incrementCacheHits();

                        // Convert cached positions to response format
                        for (const auto & pos : iface_.detection_engine->getCachedDetection()->positions) {
                            result_data.push_back(static_cast<int32_t>(pos.x * 1000));
                            result_data.push_back(static_cast<int32_t>(pos.y * 1000));
                            result_data.push_back(static_cast<int32_t>(pos.z * 1000));
                        }

                        return iface_.detection_engine->getCachedDetection()->success;
                    } else {
                        RCLCPP_DEBUG(iface_.logger, "🗑️  Cache expired (age: %.1f ms)", age_ms);
                    }
                }
            }
            iface_.detection_engine->incrementCacheMisses();

            // DepthAI mode - skip image topic entirely
            cv::Mat current_image;
            bool skip_image_topic = false;

#ifdef HAS_DEPTHAI
            if (iface_.detection_engine->isDepthAIActive()) {
                skip_image_topic = true;
                RCLCPP_DEBUG(iface_.logger, "⚡ DepthAI: Using on-device detection, skipping image topic");

            // Auto-resume camera if paused (for thermal management workflow)
                if (iface_.detection_engine->getDepthAIManager() && iface_.detection_engine->getDepthAIManager()->isCameraPaused()) {
                    RCLCPP_INFO(iface_.logger, "📷 Auto-resuming camera for detection...");
                    try {
                        iface_.detection_engine->getDepthAIManager()->resumeCamera();
                        // SOFT PAUSE: No stabilization delay needed - camera was always running
                        // resumeCamera() already flushes stale frames
                        RCLCPP_INFO(iface_.logger, "✅ Camera resumed (soft pause)");
                    } catch (const std::logic_error& e) {
                        RCLCPP_WARN(iface_.logger, "⚠️ Failed to auto-resume camera: %s", e.what());
                    }
                }
            }
#endif

            // Get current image (only for non-DepthAI modes)
            if (!skip_image_topic) {
                // Use timestamp-based freshness check instead of waiting for arbitrary new frame
                // This reduces latency from ~1.5s to <150ms while still avoiding stale images
                const rclcpp::Time call_time = iface_.clock->now();

                // Configurable freshness threshold (100ms optimized for 30 FPS)
                const auto freshness_threshold_ms = 100;
                const auto max_wait_ms = 100;  // Short wait if no frame available
                const auto start = std::chrono::steady_clock::now();
                rclcpp::Rate rate(200);  // Check at 200 Hz (optimized from 100 Hz)

                bool got_usable_frame = false;

                // Quick drain: Wait briefly if no image available yet
                while (rclcpp::ok() &&
                       (std::chrono::steady_clock::now() - start) < std::chrono::milliseconds(max_wait_ms)) {
                    std::lock_guard<std::mutex> lock(iface_.image_mutex);

                    if (iface_.image_available && !iface_.latest_image.empty()) {
                        // Check frame age
                        const double frame_age_ms = (call_time - iface_.latest_image_stamp).seconds() * 1000.0;

                        // Accept frame if it's fresh enough (captured within threshold)
                        if (frame_age_ms < freshness_threshold_ms) {
                            current_image = iface_.latest_image.clone();
                            got_usable_frame = true;
                            RCLCPP_DEBUG(iface_.logger,
                                        "✅ Using frame with age %.1f ms (within %d ms threshold)",
                                        frame_age_ms, freshness_threshold_ms);
                            break;
                        } else {
                            RCLCPP_DEBUG(iface_.logger,
                                        "⏳ Frame age %.1f ms exceeds threshold, waiting...",
                                        frame_age_ms);
                        }
                    }

                    // Release lock before sleeping
                    // BLOCKING_SLEEP_OK: frame poll 5ms (200Hz rate), up to 100ms total, executor-thread (detection_group_) — reviewed 2026-03-14
                    rate.sleep();
                }

                // If still no usable frame, use whatever we have
                if (!got_usable_frame) {
                    std::lock_guard<std::mutex> lock(iface_.image_mutex);
                    if (!iface_.image_available || iface_.latest_image.empty()) {
                        RCLCPP_ERROR(iface_.logger, "❌ No image available for detection");
                        return false;
                    }

                    const double frame_age_ms = (call_time - iface_.latest_image_stamp).seconds() * 1000.0;
                    RCLCPP_WARN(iface_.logger,
                               "⚠️ Using frame with age %.1f ms (exceeds %d ms threshold)",
                               frame_age_ms, freshness_threshold_ms);
                    current_image = iface_.latest_image.clone();
                }
            }

            // Perform detection
            std::vector<geometry_msgs::msg::Point> positions;
            bool success = iface_.detection_engine->detect_cotton_in_image(current_image, positions);

            // Cache the result for rapid repeated calls
            auto cache_start = std::chrono::steady_clock::now();  // INSTRUMENTATION
            {
                std::lock_guard<std::mutex> cache_lock(iface_.detection_engine->getCacheMutex());
                DetectionEngine::CachedDetectionResult cache_entry;
                cache_entry.positions = positions;
                {
                    std::lock_guard<std::mutex> conf_lock(iface_.detection_engine->getConfidencesMutex());
                    cache_entry.confidences = iface_.detection_engine->getLastDetectionConfidences();  // Copy confidences
                }
                cache_entry.timestamp = iface_.clock->now();
                cache_entry.detection_capture_time = std::chrono::steady_clock::now();  // When DepthAI returned result
                cache_entry.success = success;
                iface_.detection_engine->getCachedDetection() = cache_entry;
            }
            auto cache_end = std::chrono::steady_clock::now();  // INSTRUMENTATION

            if (success && !positions.empty()) {
                // Convert positions to int32 array (legacy format: x,y,z triplets)
                for (const auto & pos : positions) {
                    result_data.push_back(static_cast<int32_t>(pos.x * 1000)); // Convert to mm
                    result_data.push_back(static_cast<int32_t>(pos.y * 1000));
                    result_data.push_back(static_cast<int32_t>(pos.z * 1000));
                }

                RCLCPP_INFO(iface_.logger, "🎯 Detected %zu cotton positions", positions.size());
            } else if (success) {
                RCLCPP_DEBUG(iface_.logger, "🔍 No cotton detected in frame");
            } else {
                RCLCPP_WARN(iface_.logger, "⚠️ Cotton detection failed");
            }

            // ALWAYS publish detection result so yanthra_move's subscription receives it
            // This prevents "Timeout waiting for fresh detection data" when no cotton found
            auto publish_start = std::chrono::steady_clock::now();  // INSTRUMENTATION
            if (iface_.publish_result_fn) {
                iface_.publish_result_fn(positions, success);
            }
            auto publish_end = std::chrono::steady_clock::now();  // INSTRUMENTATION
            {  // INSTRUMENTATION
                long cache_us = std::chrono::duration_cast<std::chrono::microseconds>(cache_end - cache_start).count();  // INSTRUMENTATION
                long publish_us = std::chrono::duration_cast<std::chrono::microseconds>(publish_end - publish_start).count();  // INSTRUMENTATION
                RCLCPP_INFO(iface_.logger, "INSTRUMENTATION cache_us=%ld publish_total_us=%ld", cache_us, publish_us);  // INSTRUMENTATION
            }  // INSTRUMENTATION

#ifdef HAS_DEPTHAI
            // Auto-pause camera after detection for thermal management
            // Camera will auto-resume on next detection request
            if (iface_.detection_engine->isDepthAIActive() && iface_.detection_engine->getConfig().depthai_auto_pause_after_detection && iface_.detection_engine->getDepthAIManager()) {
                if (!iface_.detection_engine->getDepthAIManager()->isCameraPaused()) {
                    RCLCPP_DEBUG(iface_.logger, "📷 Auto-pausing camera after detection (thermal management)");
                    try {
                        iface_.detection_engine->getDepthAIManager()->pauseCamera();
                    } catch (const std::logic_error& e) {
                        RCLCPP_WARN(iface_.logger, "⚠️ Failed to auto-pause camera: %s", e.what());
                    }
                }
            }
#endif

            return success;
        }

        case 2: // Calibration mode
            return handle_calibration_request(result_data);

        default:
            RCLCPP_ERROR(iface_.logger, "❌ Unknown detection command: %d", command);
            return false;
    }
}

bool ServiceHandler::handle_calibration_request(std::vector<int32_t> & result_data)
{
    result_data.clear();

    // In simulation mode, calibration is not meaningful — no real camera hardware
    if (config_.simulation_mode) {
        RCLCPP_INFO(iface_.logger,
            "SIMULATION: Calibration request ignored (no real camera hardware)");
        return true;
    }

    std::string exported_location;
    std::string status_message;
    bool success = false;

#ifdef HAS_DEPTHAI
    if (iface_.detection_engine->isDepthAIActive() && iface_.detection_engine->getDepthAIManager()) {
        success = export_calibration_via_depthai(exported_location, status_message);
        if (!success) {
            RCLCPP_WARN(iface_.logger, "⚠️ DepthAI calibration export failed: %s. Trying script fallback...", status_message.c_str());
        }
    }
#endif

    if (!success) {
        success = export_calibration_via_script(exported_location, status_message);
    }

    if (!success) {
        RCLCPP_ERROR(iface_.logger, "❌ Calibration export failed: %s", status_message.c_str());
        return false;
    }

    result_data = encode_ascii_path(exported_location);
    RCLCPP_INFO(iface_.logger, "✅ Calibration exported: %s", exported_location.c_str());
    return true;
}

std::vector<int32_t> ServiceHandler::encode_ascii_path(const std::string & path) const
{
    std::vector<int32_t> encoded;
    encoded.reserve(path.size());
    for (unsigned char c : path) {
        encoded.push_back(static_cast<int32_t>(c));
    }
    return encoded;
}

std::string ServiceHandler::get_timestamped_filename(const std::string & prefix, const std::string & extension) const
{
    auto now = std::chrono::system_clock::now();
    std::time_t now_c = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
    localtime_r(&now_c, &tm);

    std::ostringstream oss;
    // Human readable ISO-style format: 2025-12-23_12-20-39
    oss << prefix << "_" << std::put_time(&tm, "%Y-%m-%d_%H-%M-%S") << "." << extension;
    return oss.str();
}

bool ServiceHandler::ensure_directory(const std::string & path) const
{
    std::error_code ec;
    if (fs::exists(path, ec)) {
        return !ec;
    }
    return fs::create_directories(path, ec);
}

bool ServiceHandler::export_calibration_via_depthai(std::string & exported_to, std::string & status_message)
{
#ifdef HAS_DEPTHAI
    if (!iface_.detection_engine->getDepthAIManager()) {
        status_message = "DepthAI manager unavailable";
        return false;
    }

    auto calibration_opt = iface_.detection_engine->getDepthAIManager()->getCalibration();
    if (!calibration_opt) {
        status_message = "DepthAI calibration data not available";
        return false;
    }

    std::string yaml = iface_.detection_engine->getDepthAIManager()->exportCalibrationYAML();
    if (yaml.empty()) {
        status_message = "DepthAI calibration export returned empty YAML";
        return false;
    }

    if (!ensure_directory(config_.calibration_output_dir)) {
        status_message = "Failed to create calibration output directory: " + config_.calibration_output_dir;
        return false;
    }

    fs::path file_path = fs::path(config_.calibration_output_dir) / get_timestamped_filename("calibration", "yaml");
    std::ofstream ofs(file_path);
    if (!ofs.is_open()) {
        status_message = "Failed to open calibration file for writing: " + file_path.string();
        return false;
    }
    ofs << yaml;
    ofs.close();

    exported_to = file_path.string();
    status_message = "Calibration YAML written to " + exported_to;
    return true;
#else
    (void)exported_to;
    status_message = "DepthAI support not compiled";
    return false;
#endif
}

bool ServiceHandler::export_calibration_via_script(std::string & exported_to, std::string & status_message)
{
    std::string script_path = config_.calibration_script_override;
    if (script_path.empty()) {
        try {
            auto share_dir = ament_index_cpp::get_package_share_directory("cotton_detection_ros2");
            fs::path script_candidate = fs::path(share_dir) / "config" / "cameras" / "oak_d_lite" / "export_calibration.py";
            script_path = script_candidate.string();
        } catch (const std::exception & e) {
            status_message = std::string("Unable to locate package share directory: ") + e.what();
            return false;
        }
    }

    if (!fs::exists(script_path)) {
        status_message = "Calibration script not found: " + script_path;
        return false;
    }

    if (!ensure_directory(config_.calibration_output_dir)) {
        status_message = "Failed to create calibration output directory: " + config_.calibration_output_dir;
        return false;
    }

    fs::path calib_dir = fs::path(config_.calibration_output_dir);
    std::stringstream command;
    command << "python3 \"" << script_path << "\" --output \"" << calib_dir.string() << "\"";

    RCLCPP_INFO(iface_.logger, "🔧 Running calibration script: %s", command.str().c_str());
    int rc = std::system(command.str().c_str());
    if (rc != 0) {
        std::ostringstream oss;
        oss << "Calibration script exited with code " << rc;
        status_message = oss.str();
        return false;
    }

    exported_to = calib_dir.string();
    status_message = "Calibration artifacts exported to directory " + exported_to;
    return true;
}

void ServiceHandler::handle_camera_control(
    const std::shared_ptr<std_srvs::srv::SetBool::Request> request,
    std::shared_ptr<std_srvs::srv::SetBool::Response> response)
{
#ifdef HAS_DEPTHAI
    if (request->data) {
        // Resume/Start camera
        if (!iface_.detection_engine->isDepthAIActive() || !iface_.detection_engine->getDepthAIManager()) {
            // Camera not initialized at all - need full init
            RCLCPP_INFO(iface_.logger, "📷 Camera control: starting camera (full init)...");
            try {
                if (iface_.detection_engine->initialize_depthai()) {
                    response->success = true;
                    response->message = "Camera started successfully";
                    RCLCPP_INFO(iface_.logger, "✅ Camera started");
                } else {
                    response->success = false;
                    response->message = "Failed to start camera";
                    RCLCPP_ERROR(iface_.logger, "❌ Failed to start camera");
                }
            } catch (const std::exception& e) {
                response->success = false;
                response->message = std::string("Camera start exception: ") + e.what();
                RCLCPP_ERROR(iface_.logger, "❌ Camera start exception: %s", e.what());
            }
        } else if (iface_.detection_engine->getDepthAIManager()->isCameraPaused()) {
            // Camera paused - use fast resume
            RCLCPP_INFO(iface_.logger, "📷 Camera control: resuming camera...");
            try {
                iface_.detection_engine->getDepthAIManager()->resumeCamera();
                // CRITICAL: Wait for stereo pipeline to stabilize after resume
                // Without this, X_LINK_ERROR can occur due to camera sync issues
                // BLOCKING_SLEEP_OK: stereo pipeline stabilization 100ms, executor-thread (detection_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(100));

                // Flush stale frames
                int flushed = 0;
                while (iface_.detection_engine->getDepthAIManager()->hasDetections() && flushed < 10) {
                    iface_.detection_engine->getDepthAIManager()->getDetections(std::chrono::milliseconds(10));
                    flushed++;
                }

                response->success = true;
                response->message = "Camera resumed successfully (flushed " + std::to_string(flushed) + " frames)";
                RCLCPP_INFO(iface_.logger, "✅ Camera resumed (flushed %d frames)", flushed);
            } catch (const std::logic_error& e) {
                response->success = false;
                response->message = std::string("Failed to resume camera: ") + e.what();
                RCLCPP_ERROR(iface_.logger, "❌ Failed to resume camera: %s", e.what());
            }
        } else {
            // Camera already running
            response->success = true;
            response->message = "Camera already running";
            RCLCPP_INFO(iface_.logger, "📷 Camera control: already running");
        }
    } else {
        // Pause/Stop camera
        if (!iface_.detection_engine->isDepthAIActive() || !iface_.detection_engine->getDepthAIManager()) {
            response->success = true;
            response->message = "Camera already stopped";
            RCLCPP_INFO(iface_.logger, "📷 Camera control: already stopped");
        } else if (iface_.detection_engine->getDepthAIManager()->isCameraPaused()) {
            response->success = true;
            response->message = "Camera already paused";
            RCLCPP_INFO(iface_.logger, "📷 Camera control: already paused");
        } else {
            // Use fast pause (~10ms) instead of full shutdown (~4-5 sec)
            RCLCPP_INFO(iface_.logger, "📷 Camera control: pausing camera (fast)...");
            try {
                iface_.detection_engine->getDepthAIManager()->pauseCamera();
                response->success = true;
                response->message = "Camera paused successfully (fast)";
                RCLCPP_INFO(iface_.logger, "✅ Camera paused (~10ms)");
            } catch (const std::logic_error& e) {
                // Fallback to full shutdown if pause fails
                RCLCPP_WARN(iface_.logger, "⚠️ Fast pause failed (%s), falling back to full shutdown", e.what());
                iface_.detection_engine->shutdown_depthai();
                response->success = true;
                response->message = "Camera stopped (full shutdown)";
                RCLCPP_INFO(iface_.logger, "✅ Camera stopped (full shutdown)");
            }
        }
    }
#else
    (void)request;
    response->success = false;
    response->message = "DepthAI not available - camera control disabled";
    RCLCPP_WARN(iface_.logger, "⚠️ Camera control unavailable (no DepthAI)");
#endif
}

}  // namespace cotton_detection_ros2
