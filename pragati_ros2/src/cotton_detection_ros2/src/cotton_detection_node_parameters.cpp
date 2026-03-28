/**
 * @file cotton_detection_node_parameters.cpp
 * @brief Parameter management for Cotton Detection Node
 *
 * Extracted from cotton_detection_node.cpp to improve build performance.
 * Contains: declare_parameters, load_parameters, validate_parameters, on_parameter_update
 */

#include "cotton_detection_ros2/cotton_detection_node.hpp"

// Standard library
#include <filesystem>
#include <unistd.h>  // For access()

#include <ament_index_cpp/get_package_share_directory.hpp>

namespace cotton_detection_ros2
{

namespace fs = std::filesystem;

void CottonDetectionNode::declare_parameters()
{
    // Camera configuration
    this->declare_parameter("camera_topic", "/camera/image_raw");
    this->declare_parameter("debug_image_topic", "/cotton_detection/debug_image/compressed");
    this->declare_parameter("enable_debug_output", false);

    // Detection parameters
    this->declare_parameter("detection_confidence_threshold", 0.7);
    this->declare_parameter("max_cotton_detections", 50);

    // Coordinate transformation
    this->declare_parameter("coordinate_transform.pixel_to_meter_scale_x", 0.001);
    this->declare_parameter("coordinate_transform.pixel_to_meter_scale_y", 0.001);
    this->declare_parameter("coordinate_transform.assumed_depth_m", 0.5);

    // Calibration export configuration
    this->declare_parameter("calibration.output_dir", "");
    this->declare_parameter("calibration.timeout_sec", 30.0);
    this->declare_parameter("calibration.script_override", "");

    // Camera configuration (DepthAI OAK-D Lite via Python wrapper)
    this->declare_parameter("use_depthai", true);

    // Performance settings
    this->declare_parameter("performance.max_processing_fps", 30.0);
    this->declare_parameter("performance.processing_timeout_ms", 1000);
    this->declare_parameter("performance.enable_monitoring", true);
    this->declare_parameter("performance.detailed_logging", false);
    this->declare_parameter("performance.verbose_timing", false);
    this->declare_parameter("performance.max_recent_measurements", 30);  // Optimized from 100

    // Detection workspace bounds (in meters)
    this->declare_parameter("workspace.max_x", 2.0);   // Forward reach
    this->declare_parameter("workspace.max_y", 1.5);   // Lateral reach
    this->declare_parameter("workspace.max_z", 3.0);   // Height limit
    this->declare_parameter("workspace.min_z", 0.0);   // Ground level

    // Detection mode - depthai_direct is the only production mode
    this->declare_parameter("detection_mode", "depthai_direct");

    // DepthAI parameters
#ifdef HAS_DEPTHAI
    this->declare_parameter("depthai.enable", true);
    this->declare_parameter("depthai.model_path", "");
    this->declare_parameter("depthai.num_classes", 1);  // 1 for YOLOv8, 2 for YOLOv11
    this->declare_parameter("depthai.swap_class_labels", false);  // Swap cotton/not_pickable labels
    this->declare_parameter("depthai.camera_width", 416);
    this->declare_parameter("depthai.camera_height", 416);
    this->declare_parameter("depthai.camera_fps", 30);
    this->declare_parameter("depthai.confidence_threshold", 0.5);
    this->declare_parameter("depthai.depth_min_mm", 100.0);
    this->declare_parameter("depthai.depth_max_mm", 5000.0);
    this->declare_parameter("depthai.enable_depth", true);
    this->declare_parameter("depthai.device_id", "");
    this->declare_parameter("depthai.warmup_seconds", 1);       // Pipeline warmup time (optimized from 3s)
    this->declare_parameter("depthai.max_queue_drain", 3);      // Max frames to drain for freshness (optimized from 10)
    this->declare_parameter("depthai.flush_before_read", false); // Old flush behavior for comparison
    this->declare_parameter("depthai.keep_aspect_ratio", true);  // true = letterbox; false = stretch to fill NN input
    this->declare_parameter("depthai.detection_timeout_ms", 500); // Timeout waiting for fresh detection frame
    // DISABLED BY DEFAULT: Camera pause/resume causes X_LINK_ERROR on some OAK-D devices
    // The setStopStreaming()/setStartStreaming() commands are not reliably supported
    // Enable only if your specific device/firmware supports it without errors
    this->declare_parameter("depthai.auto_pause_after_detection", false);

    // Thermal management parameters
    this->declare_parameter("depthai.thermal.enable", true);
    this->declare_parameter("depthai.thermal.check_interval_sec", 5.0);
    this->declare_parameter("depthai.thermal.warning_temp_c", 70.0);
    this->declare_parameter("depthai.thermal.throttle_temp_c", 80.0);
    this->declare_parameter("depthai.thermal.critical_temp_c", 90.0);
    this->declare_parameter("depthai.thermal.throttle_fps", 15);

    // Periodic stats logging interval (temperature + detect stats)
    // Set to 0 to disable periodic logging, higher for less verbose output
    this->declare_parameter("depthai.stats_log_interval_sec", 30.0);

    // Exposure control parameters
    // mode: "auto" for automatic exposure, "manual" for fixed exposure
    this->declare_parameter("depthai.exposure.mode", "auto");
    // Manual exposure settings (only used when mode="manual")
    // time_us: exposure time in microseconds (1-33000, typical: 1500 for bright sun, 8000 for indoor)
    this->declare_parameter("depthai.exposure.time_us", 8000);
    // iso: sensitivity (100-1600, typical: 300 for bright sun, 800 for indoor)
    this->declare_parameter("depthai.exposure.iso", 400);

    // Border filter: Skip detections touching image edge (bad depth from stereo)
    this->declare_parameter("depthai.border_filter.enabled", true);
    this->declare_parameter("depthai.border_filter.margin", 0.05);  // 5% of image dimension

    // Stereo depth pipeline tuning
    this->declare_parameter("depthai.stereo_confidence_threshold", 200);  // 0-255, lower = stricter
    this->declare_parameter("depthai.bbox_scale_factor", 0.5);  // 0.3-0.8, fraction of bbox for depth
    this->declare_parameter("depthai.extended_disparity", true);  // Close-range depth for arm working range

    // Stereo depth advanced tuning (previously hardcoded)
    this->declare_parameter("depthai.spatial_calc_algorithm", std::string("average"));  // "average", "median", "min", "max"
    this->declare_parameter("depthai.mono_resolution", std::string("400p"));            // "400p", "480p", "720p", "800p"
    this->declare_parameter("depthai.lr_check", true);                                  // Left-right consistency check
    this->declare_parameter("depthai.subpixel", false);                                 // Subpixel disparity
    this->declare_parameter("depthai.median_filter", std::string("7x7"));               // "off", "3x3", "5x5", "7x7"
#endif

    // Image saving configuration
    this->declare_parameter("save_input_image", false);
    this->declare_parameter("save_output_image", false);
    this->declare_parameter("file_save_mode", "overwrite");  // "overwrite" or "timestamp"
    this->declare_parameter("save_async", false);       // Use async image saver (background thread)
    this->declare_parameter("save_queue_depth", 3);     // Async saver queue depth
    this->declare_parameter("save_jpeg_quality", 85);   // JPEG compression quality (0-100)
    this->declare_parameter("simulation_mode", false);  // Simulation mode for hardware-free testing
    this->declare_parameter("simulation_noise_stddev", 0.005);
    this->declare_parameter("simulation_confidence_min", 0.7);
    this->declare_parameter("simulation_confidence_max", 0.95);
    this->declare_parameter("simulated_positions.x", std::vector<double>{0.40, 0.35, 0.50});
    this->declare_parameter("simulated_positions.y", std::vector<double>{-0.15, -0.10, -0.15});
    this->declare_parameter("simulated_positions.z", std::vector<double>{0.10, 0.10, 0.10});
    const char * home_env = std::getenv("HOME");
    std::string default_base = home_env ? (std::string(home_env) + "/pragati_ros2") : "/tmp/pragati_ros2";
    this->declare_parameter("input_dir", default_base + "/data/inputs");
    this->declare_parameter("output_dir", default_base + "/data/outputs");

    // Detection cache configuration
    this->declare_parameter("detection.cache_validity_ms", 100);  // Cache valid for N ms (default 100)

    // Fallback positions when zero cotton detected
    this->declare_parameter("publish_fallback_on_zero", false);
    this->declare_parameter("fallback_positions.x", std::vector<double>{0.40, 0.35, 0.50, 0.45});
    this->declare_parameter("fallback_positions.y", std::vector<double>{-0.15, -0.10, -0.15, -0.10});
    this->declare_parameter("fallback_positions.z", std::vector<double>{0.10, 0.10, 0.10, 0.10});
}

void CottonDetectionNode::load_parameters()
{
    camera_topic_ = this->get_parameter("camera_topic").as_string();
    debug_image_topic_ = this->get_parameter("debug_image_topic").as_string();
    enable_debug_output_ = this->get_parameter("enable_debug_output").as_bool();

    detection_confidence_threshold_ = this->get_parameter("detection_confidence_threshold").as_double();
    max_cotton_detections_ = this->get_parameter("max_cotton_detections").as_int();

    // Coordinate transformation
    pixel_to_meter_scale_x_ = this->get_parameter("coordinate_transform.pixel_to_meter_scale_x").as_double();
    pixel_to_meter_scale_y_ = this->get_parameter("coordinate_transform.pixel_to_meter_scale_y").as_double();
    assumed_depth_m_ = this->get_parameter("coordinate_transform.assumed_depth_m").as_double();

    // Calibration export configuration
    calibration_timeout_sec_ = this->get_parameter("calibration.timeout_sec").as_double();
    calibration_script_override_ = this->get_parameter("calibration.script_override").as_string();
    std::string calibration_output_param = this->get_parameter("calibration.output_dir").as_string();
    if (calibration_output_param.empty()) {
        const char * home_env = std::getenv("HOME");
        if (home_env) {
            calibration_output_dir_ = std::string(home_env) + "/pragati_ros2/data/outputs/calibration";
        } else {
            calibration_output_dir_ = "/tmp/pragati_ros2/data/calibration";
        }
    } else {
        calibration_output_dir_ = calibration_output_param;
    }
    RCLCPP_INFO(this->get_logger(), "   📁 Calibration output dir: %s", calibration_output_dir_.c_str());

    // Performance settings
    max_processing_fps_ = this->get_parameter("performance.max_processing_fps").as_double();
    processing_timeout_ms_ = this->get_parameter("performance.processing_timeout_ms").as_int();
    enable_performance_monitoring_ = this->get_parameter("performance.enable_monitoring").as_bool();
    performance_detailed_logging_ = this->get_parameter("performance.detailed_logging").as_bool();
    verbose_timing_ = this->get_parameter("performance.verbose_timing").as_bool();
    performance_max_recent_measurements_ = this->get_parameter("performance.max_recent_measurements").as_int();

    // Workspace bounds
    workspace_max_x_ = this->get_parameter("workspace.max_x").as_double();
    workspace_max_y_ = this->get_parameter("workspace.max_y").as_double();
    workspace_max_z_ = this->get_parameter("workspace.max_z").as_double();
    workspace_min_z_ = this->get_parameter("workspace.min_z").as_double();

    // Validate workspace bounds and enable/disable filtering
    bool all_zero = (workspace_max_x_ == 0.0 && workspace_max_y_ == 0.0 &&
                     workspace_max_z_ == 0.0 && workspace_min_z_ == 0.0);
    bool any_zero = (workspace_max_x_ == 0.0 || workspace_max_y_ == 0.0 ||
                     workspace_max_z_ == 0.0);
    if (all_zero) {
        RCLCPP_WARN(this->get_logger(),
            "Workspace filtering disabled - all bounds are 0.0");
        workspace_filter_enabled_ = false;
    } else if (any_zero) {
        RCLCPP_ERROR(this->get_logger(),
            "Inconsistent workspace config: some bounds are 0.0 (max_x=%.2f, max_y=%.2f, max_z=%.2f, min_z=%.2f). "
            "Set all to 0.0 to disable or configure all bounds.",
            workspace_max_x_, workspace_max_y_, workspace_max_z_, workspace_min_z_);
        workspace_filter_enabled_ = false;
    } else {
        workspace_filter_enabled_ = true;
        RCLCPP_INFO(this->get_logger(),
            "Workspace filtering enabled: x=[0, %.2f], y=[-%.2f, %.2f], z=[%.2f, %.2f]",
            workspace_max_x_, workspace_max_y_, workspace_max_y_,
            workspace_min_z_, workspace_max_z_);
    }

    // Detection mode - only depthai_direct is supported
    std::string detection_mode_str = this->get_parameter("detection_mode").as_string();
    if (detection_mode_str != "depthai_direct") {
        RCLCPP_WARN(this->get_logger(), "Detection mode '%s' not supported. Using depthai_direct.",
                   detection_mode_str.c_str());
    }

    // Image saving configuration
    save_input_image_ = this->get_parameter("save_input_image").as_bool();
    save_output_image_ = this->get_parameter("save_output_image").as_bool();
    file_save_mode_timestamp_ = (this->get_parameter("file_save_mode").as_string() == "timestamp");
    save_async_ = this->get_parameter("save_async").as_bool();
    save_queue_depth_ = this->get_parameter("save_queue_depth").as_int();
    save_jpeg_quality_ = this->get_parameter("save_jpeg_quality").as_int();
    simulation_mode_ = this->get_parameter("simulation_mode").as_bool();
    if (simulation_mode_) {
        // Load simulation parameters
        simulation_noise_stddev_ = this->get_parameter("simulation_noise_stddev").as_double();
        simulation_confidence_min_ = this->get_parameter("simulation_confidence_min").as_double();
        simulation_confidence_max_ = this->get_parameter("simulation_confidence_max").as_double();

        // Seed the random engine
        simulation_rng_.seed(std::random_device{}());

        // Load simulated positions (same pattern as fallback_positions)
        auto sim_x = this->get_parameter("simulated_positions.x").as_double_array();
        auto sim_y = this->get_parameter("simulated_positions.y").as_double_array();
        auto sim_z = this->get_parameter("simulated_positions.z").as_double_array();

        if (sim_x.size() == sim_y.size() && sim_y.size() == sim_z.size()) {
            simulated_positions_.clear();
            for (size_t i = 0; i < sim_x.size(); ++i) {
                geometry_msgs::msg::Point pt;
                pt.x = sim_x[i];
                pt.y = sim_y[i];
                pt.z = sim_z[i];
                simulated_positions_.push_back(pt);
            }
            RCLCPP_INFO(this->get_logger(), "SIMULATION mode enabled: %zu simulated positions loaded",
                       simulated_positions_.size());
            for (size_t i = 0; i < simulated_positions_.size(); ++i) {
                RCLCPP_INFO(this->get_logger(), "   Sim position %zu: (%.4f, %.4f, %.4f)",
                           i+1, simulated_positions_[i].x, simulated_positions_[i].y, simulated_positions_[i].z);
            }
        } else {
            RCLCPP_ERROR(this->get_logger(), "Simulated position arrays have mismatched sizes (x:%zu, y:%zu, z:%zu)",
                        sim_x.size(), sim_y.size(), sim_z.size());
        }

        RCLCPP_INFO(this->get_logger(), "   Noise stddev: %.4f m, Confidence range: [%.2f, %.2f]",
                   simulation_noise_stddev_, simulation_confidence_min_, simulation_confidence_max_);
    }
    input_dir_ = this->get_parameter("input_dir").as_string();
    output_dir_ = this->get_parameter("output_dir").as_string();

    // If paths are empty, use HOME-based defaults
    if (input_dir_.empty()) {
        const char * home_env = std::getenv("HOME");
        std::string default_base = home_env ? (std::string(home_env) + "/pragati_ros2") : "/tmp/pragati_ros2";
        input_dir_ = default_base + "/data/inputs";
    }
    if (output_dir_.empty()) {
        const char * home_env = std::getenv("HOME");
        std::string default_base = home_env ? (std::string(home_env) + "/pragati_ros2") : "/tmp/pragati_ros2";
        output_dir_ = default_base + "/data/outputs";
    }

    // Always log resolved absolute paths at startup for easy debugging
    RCLCPP_INFO(this->get_logger(), "📁 Data directories (resolved absolute paths):");
    RCLCPP_INFO(this->get_logger(), "   Input:  %s", input_dir_.c_str());
    RCLCPP_INFO(this->get_logger(), "   Output: %s", output_dir_.c_str());

    // Ensure directories exist and enable image saving
    if (save_input_image_ || save_output_image_) {
        std::filesystem::create_directories(input_dir_);
        std::filesystem::create_directories(output_dir_);
        RCLCPP_INFO(this->get_logger(), "💾 Image saving enabled (save_input=%s, save_output=%s, async=%s)",
                   save_input_image_ ? "true" : "false", save_output_image_ ? "true" : "false",
                   save_async_ ? "true" : "false");

        // Initialize async image saver if configured
        if (save_async_) {
            async_image_saver_ = std::make_unique<AsyncImageSaver>(
                static_cast<size_t>(save_queue_depth_), save_jpeg_quality_);
            async_image_saver_->start();
            RCLCPP_INFO(this->get_logger(), "   Async image saver started (queue_depth=%d, jpeg_quality=%d)",
                       save_queue_depth_, save_jpeg_quality_);
        }
    }

    // Load fallback positions configuration
    publish_fallback_on_zero_ = this->get_parameter("publish_fallback_on_zero").as_bool();

    // Detection cache configuration
    int cache_validity_ms = this->get_parameter("detection.cache_validity_ms").as_int();
    RCLCPP_INFO(this->get_logger(), "   💾 Cache validity: %d ms", cache_validity_ms);
    if (detection_engine_) {
        detection_engine_->getConfig().cache_validity_ms = cache_validity_ms;
    }

    auto fb_x = this->get_parameter("fallback_positions.x").as_double_array();
    auto fb_y = this->get_parameter("fallback_positions.y").as_double_array();
    auto fb_z = this->get_parameter("fallback_positions.z").as_double_array();

    // Validate and load fallback positions
    if (fb_x.size() == fb_y.size() && fb_y.size() == fb_z.size()) {
        fallback_positions_.clear();
        for (size_t i = 0; i < fb_x.size(); ++i) {
            geometry_msgs::msg::Point pt;
            pt.x = fb_x[i];
            pt.y = fb_y[i];
            pt.z = fb_z[i];
            fallback_positions_.push_back(pt);
        }
        if (publish_fallback_on_zero_) {
            RCLCPP_INFO(this->get_logger(), "   📍 Fallback positions enabled: %zu positions will be published when 0 cotton detected",
                       fallback_positions_.size());
            for (size_t i = 0; i < fallback_positions_.size(); ++i) {
                RCLCPP_INFO(this->get_logger(), "      Position %zu: (%.4f, %.4f, %.4f)",
                           i+1, fallback_positions_[i].x, fallback_positions_[i].y, fallback_positions_[i].z);
            }
        }
    } else {
        RCLCPP_ERROR(this->get_logger(), "   ❌ Fallback position arrays have mismatched sizes (x:%zu, y:%zu, z:%zu)",
                    fb_x.size(), fb_y.size(), fb_z.size());
    }

#ifdef HAS_DEPTHAI
    depthai_enable_ = this->get_parameter("depthai.enable").as_bool();
    depthai_model_path_ = this->get_parameter("depthai.model_path").as_string();
    depthai_num_classes_ = this->get_parameter("depthai.num_classes").as_int();
    depthai_swap_class_labels_ = this->get_parameter("depthai.swap_class_labels").as_bool();

    // Log raw parameter value (DEBUG - for troubleshooting only)
    RCLCPP_DEBUG(this->get_logger(), "📦 Model path parameter: '%s'",
                depthai_model_path_.empty() ? "(empty)" : depthai_model_path_.c_str());

    depthai_camera_width_ = this->get_parameter("depthai.camera_width").as_int();
    depthai_camera_height_ = this->get_parameter("depthai.camera_height").as_int();
    depthai_camera_fps_ = this->get_parameter("depthai.camera_fps").as_int();
    depthai_confidence_threshold_ = static_cast<float>(this->get_parameter("depthai.confidence_threshold").as_double());
    depthai_depth_min_mm_ = this->get_parameter("depthai.depth_min_mm").as_double();
    depthai_depth_max_mm_ = this->get_parameter("depthai.depth_max_mm").as_double();
    depthai_enable_depth_ = this->get_parameter("depthai.enable_depth").as_bool();
    depthai_device_id_ = this->get_parameter("depthai.device_id").as_string();
    depthai_warmup_seconds_ = this->get_parameter("depthai.warmup_seconds").as_int();
    depthai_max_queue_drain_ = this->get_parameter("depthai.max_queue_drain").as_int();
    depthai_flush_before_read_ = this->get_parameter("depthai.flush_before_read").as_bool();
    depthai_keep_aspect_ratio_ = this->get_parameter("depthai.keep_aspect_ratio").as_bool();
    depthai_detection_timeout_ms_ = this->get_parameter("depthai.detection_timeout_ms").as_int();
    depthai_auto_pause_after_detection_ = this->get_parameter("depthai.auto_pause_after_detection").as_bool();

    // Thermal management
    thermal_enable_ = this->get_parameter("depthai.thermal.enable").as_bool();
    thermal_check_interval_sec_ = this->get_parameter("depthai.thermal.check_interval_sec").as_double();
    thermal_warning_temp_c_ = this->get_parameter("depthai.thermal.warning_temp_c").as_double();
    thermal_throttle_temp_c_ = this->get_parameter("depthai.thermal.throttle_temp_c").as_double();
    thermal_critical_temp_c_ = this->get_parameter("depthai.thermal.critical_temp_c").as_double();
    thermal_throttle_fps_ = this->get_parameter("depthai.thermal.throttle_fps").as_int();
    stats_log_interval_sec_ = this->get_parameter("depthai.stats_log_interval_sec").as_double();

    // Exposure control
    exposure_mode_ = this->get_parameter("depthai.exposure.mode").as_string();
    exposure_time_us_ = this->get_parameter("depthai.exposure.time_us").as_int();
    exposure_iso_ = this->get_parameter("depthai.exposure.iso").as_int();

    RCLCPP_INFO(this->get_logger(), "   📷 Exposure mode: %s", exposure_mode_.c_str());
    if (exposure_mode_ == "manual") {
        RCLCPP_INFO(this->get_logger(), "      Time: %d µs, ISO: %d", exposure_time_us_, exposure_iso_);
    }

    // Border filter
    border_filter_enabled_ = this->get_parameter("depthai.border_filter.enabled").as_bool();
    border_margin_ = static_cast<float>(this->get_parameter("depthai.border_filter.margin").as_double());
    if (border_filter_enabled_) {
        RCLCPP_INFO(this->get_logger(), "   🔲 Border filter: enabled (margin=%.1f%%)", border_margin_ * 100.0f);
    }

    // Stereo depth pipeline tuning
    depthai_stereo_confidence_threshold_ = this->get_parameter("depthai.stereo_confidence_threshold").as_int();
    depthai_bbox_scale_factor_ = static_cast<float>(this->get_parameter("depthai.bbox_scale_factor").as_double());
    depthai_extended_disparity_ = this->get_parameter("depthai.extended_disparity").as_bool();

    // Validate bbox_scale_factor range
    if (depthai_bbox_scale_factor_ < 0.3f || depthai_bbox_scale_factor_ > 0.8f) {
        RCLCPP_WARN(this->get_logger(),
            "   ⚠️ bbox_scale_factor %.2f outside recommended range [0.3, 0.8], clamping",
            depthai_bbox_scale_factor_);
        depthai_bbox_scale_factor_ = std::clamp(depthai_bbox_scale_factor_, 0.3f, 0.8f);
    }

    // Stereo advanced tuning
    depthai_spatial_calc_algorithm_ = this->get_parameter("depthai.spatial_calc_algorithm").as_string();
    depthai_mono_resolution_ = this->get_parameter("depthai.mono_resolution").as_string();
    depthai_lr_check_ = this->get_parameter("depthai.lr_check").as_bool();
    depthai_subpixel_ = this->get_parameter("depthai.subpixel").as_bool();
    depthai_median_filter_ = this->get_parameter("depthai.median_filter").as_string();

    RCLCPP_INFO(this->get_logger(), "   🔧 Stereo tuning: confidence=%d, bbox_scale=%.2f, extended_disparity=%s",
                depthai_stereo_confidence_threshold_, depthai_bbox_scale_factor_,
                depthai_extended_disparity_ ? "true" : "false");
    RCLCPP_INFO(this->get_logger(), "   🔧 Stereo advanced: algorithm=%s, mono=%s, lr_check=%s, subpixel=%s, median=%s",
                depthai_spatial_calc_algorithm_.c_str(), depthai_mono_resolution_.c_str(),
                depthai_lr_check_ ? "true" : "false", depthai_subpixel_ ? "true" : "false",
                depthai_median_filter_.c_str());

    // If model path not provided or file missing, resolve to package share models dir
    if (depthai_model_path_.empty() || access(depthai_model_path_.c_str(), F_OK) != 0) {
        if (!depthai_model_path_.empty()) {
            RCLCPP_WARN(this->get_logger(), "⚠️  Provided model path not found: %s", depthai_model_path_.c_str());
            RCLCPP_WARN(this->get_logger(), "   Falling back to default model...");
        }
        try {
            auto share_dir = ament_index_cpp::get_package_share_directory("cotton_detection_ros2");
            fs::path default_blob = fs::path(share_dir) / "models" / "yolov112.blob";
            depthai_model_path_ = default_blob.string();
            if (access(depthai_model_path_.c_str(), F_OK) != 0) {
                RCLCPP_WARN(this->get_logger(), "❌ DepthAI blob not found at %s", depthai_model_path_.c_str());
            } else {
                RCLCPP_INFO(this->get_logger(), "🧠 Model: %s (classes=%d)", depthai_model_path_.c_str(), depthai_num_classes_);
            }
        } catch (const std::exception &e) {
            RCLCPP_WARN(this->get_logger(), "Failed to resolve package share for model blob: %s", e.what());
        }
    } else {
        RCLCPP_INFO(this->get_logger(), "🧠 Model: %s (classes=%d)", depthai_model_path_.c_str(), depthai_num_classes_);
    }
#endif

    RCLCPP_INFO(this->get_logger(), "📋 Configuration loaded:");
    RCLCPP_INFO(this->get_logger(), "   Camera: %s", camera_topic_.c_str());
    RCLCPP_INFO(this->get_logger(), "   Debug: %s", enable_debug_output_ ? "enabled" : "disabled");
    RCLCPP_INFO(this->get_logger(), "   Detection Mode: depthai_direct");
    RCLCPP_INFO(this->get_logger(), "   Confidence: %.2f", detection_confidence_threshold_);

    // Validate all parameters
    if (!validate_parameters()) {
        RCLCPP_ERROR(this->get_logger(), "❌ Parameter validation failed! Node may not function correctly.");
        throw std::runtime_error("Invalid configuration parameters");
    }
}

bool CottonDetectionNode::validate_parameters()
{
    bool valid = true;

    RCLCPP_INFO(this->get_logger(), "🔍 Validating configuration parameters...");

    // Detection Confidence Threshold
    if (detection_confidence_threshold_ < 0.0 || detection_confidence_threshold_ > 1.0) {
        RCLCPP_ERROR(this->get_logger(), "❌ detection_confidence_threshold must be in range [0.0, 1.0], got %.2f",
                     detection_confidence_threshold_);
        valid = false;
    }

    // Max Cotton Detections
    if (max_cotton_detections_ <= 0 || max_cotton_detections_ > 1000) {
        RCLCPP_ERROR(this->get_logger(), "❌ max_cotton_detections must be in range [1, 1000], got %d",
                     max_cotton_detections_);
        valid = false;
    }

    // Coordinate Transformation
    if (pixel_to_meter_scale_x_ <= 0.0 || pixel_to_meter_scale_y_ <= 0.0) {
        RCLCPP_ERROR(this->get_logger(), "❌ pixel_to_meter scales must be > 0");
        valid = false;
    }
    if (assumed_depth_m_ <= 0.0 || assumed_depth_m_ > 10.0) {
        RCLCPP_ERROR(this->get_logger(), "❌ assumed_depth_m must be in range (0.0, 10.0], got %.2f",
                     assumed_depth_m_);
        valid = false;
    }

    // Performance Settings
    if (max_processing_fps_ <= 0.0 || max_processing_fps_ > 240.0) {
        RCLCPP_ERROR(this->get_logger(), "❌ max_processing_fps must be in range (0.0, 240.0], got %.2f",
                     max_processing_fps_);
        valid = false;
    }
    if (processing_timeout_ms_ < 10 || processing_timeout_ms_ > 10000) {
        RCLCPP_ERROR(this->get_logger(), "❌ processing_timeout_ms must be in range [10, 10000], got %d",
                     processing_timeout_ms_);
        valid = false;
    }
    if (performance_max_recent_measurements_ < 10 || performance_max_recent_measurements_ > 10000) {
        RCLCPP_ERROR(this->get_logger(), "❌ performance_max_recent_measurements must be in range [10, 10000], got %d",
                     performance_max_recent_measurements_);
        valid = false;
    }

    // DepthAI num_classes
#ifdef HAS_DEPTHAI
    if (depthai_num_classes_ <= 0) {
        RCLCPP_ERROR(this->get_logger(), "❌ num_classes must be > 0, got %d", depthai_num_classes_);
        valid = false;
    }
#endif

    // Topic Names
    if (camera_topic_.empty()) {
        RCLCPP_ERROR(this->get_logger(), "❌ camera_topic cannot be empty");
        valid = false;
    }
    if (debug_image_topic_.empty() && enable_debug_output_) {
        RCLCPP_ERROR(this->get_logger(), "❌ debug_image_topic cannot be empty when debug output is enabled");
        valid = false;
    }

    if (valid) {
        RCLCPP_INFO(this->get_logger(), "✅ All parameters validated successfully");
    } else {
        RCLCPP_ERROR(this->get_logger(), "❌ Parameter validation failed - see errors above");
    }

    return valid;
}

rcl_interfaces::msg::SetParametersResult CottonDetectionNode::on_parameter_update(const std::vector<rclcpp::Parameter> & params)
{
    rcl_interfaces::msg::SetParametersResult result;
    result.successful = true;
    std::scoped_lock<std::mutex> lock(parameter_mutex_);

#ifdef HAS_DEPTHAI
    bool depthai_params_changed = false;
    float updated_confidence = depthai_confidence_threshold_;
    double updated_depth_min = depthai_depth_min_mm_;
    double updated_depth_max = depthai_depth_max_mm_;
    bool updated_enable_depth = depthai_enable_depth_;
    bool depth_toggle_changed = false;

    for (const auto & param : params) {
        const auto & name = param.get_name();
        if (name == "depthai.confidence_threshold") {
            if (param.get_type() != rclcpp::ParameterType::PARAMETER_DOUBLE &&
                param.get_type() != rclcpp::ParameterType::PARAMETER_INTEGER) {
                result.successful = false;
                result.reason = "depthai.confidence_threshold must be numeric";
                return result;
            }
            double value = param.as_double();
            if (value < 0.0 || value > 1.0) {
                result.successful = false;
                result.reason = "depthai.confidence_threshold must be within [0.0, 1.0]";
                return result;
            }
            updated_confidence = static_cast<float>(value);
            depthai_params_changed = true;
        } else if (name == "depthai.depth_min_mm") {
            if (param.get_type() != rclcpp::ParameterType::PARAMETER_DOUBLE &&
                param.get_type() != rclcpp::ParameterType::PARAMETER_INTEGER) {
                result.successful = false;
                result.reason = "depthai.depth_min_mm must be numeric";
                return result;
            }
            updated_depth_min = param.as_double();
            depthai_params_changed = true;
        } else if (name == "depthai.depth_max_mm") {
            if (param.get_type() != rclcpp::ParameterType::PARAMETER_DOUBLE &&
                param.get_type() != rclcpp::ParameterType::PARAMETER_INTEGER) {
                result.successful = false;
                result.reason = "depthai.depth_max_mm must be numeric";
                return result;
            }
            updated_depth_max = param.as_double();
            depthai_params_changed = true;
        } else if (name == "depthai.enable_depth") {
            if (param.get_type() != rclcpp::ParameterType::PARAMETER_BOOL) {
                result.successful = false;
                result.reason = "depthai.enable_depth must be a boolean";
                return result;
            }
            bool requested = param.as_bool();
            if (requested != updated_enable_depth) {
                depth_toggle_changed = true;
                updated_enable_depth = requested;
            }
            depthai_params_changed = true;
        }
    }

    if (depthai_params_changed) {
        if (updated_depth_min < 0.0 || updated_depth_max <= 0.0 || updated_depth_min >= updated_depth_max) {
            result.successful = false;
            result.reason = "depthai depth range must satisfy 0 <= min < max";
            return result;
        }

        depthai_confidence_threshold_ = updated_confidence;
        depthai_depth_min_mm_ = updated_depth_min;
        depthai_depth_max_mm_ = updated_depth_max;
        depthai_enable_depth_ = updated_enable_depth;

        // Sync updated parameters to DetectionEngine config
        if (detection_engine_) {
            auto& det_cfg = detection_engine_->getConfig();
            det_cfg.depthai_confidence_threshold = depthai_confidence_threshold_;
            det_cfg.depthai_depth_min_mm = depthai_depth_min_mm_;
            det_cfg.depthai_depth_max_mm = depthai_depth_max_mm_;
            det_cfg.depthai_enable_depth = depthai_enable_depth_;
        }

        if (detection_engine_) {
            std::scoped_lock<std::mutex> depth_lock(detection_engine_->getConfigMutex());
            if (detection_engine_->isDepthAIActive() && detection_engine_->getDepthAIManager()) {
                bool applied = detection_engine_->apply_depthai_runtime_config_locked();
                if (!applied) {
                    RCLCPP_WARN(this->get_logger(), "DepthAI runtime update partial; consider restarting the DepthAI pipeline");
                } else {
                    RCLCPP_INFO(this->get_logger(),
                        "DepthAI runtime config updated (confidence=%.2f depth=%.0f-%.0fmm depth_enabled=%s)",
                        depthai_confidence_threshold_, depthai_depth_min_mm_, depthai_depth_max_mm_,
                        depthai_enable_depth_ ? "true" : "false");
                }
                if (depth_toggle_changed) {
                    RCLCPP_WARN(this->get_logger(),
                        "DepthAI depth stream toggled to %s; a full pipeline restart may be required for this change to take effect",
                        depthai_enable_depth_ ? "ENABLED" : "DISABLED");
                }
            } else {
                RCLCPP_DEBUG(this->get_logger(), "DepthAI parameters updated; runtime config will apply on next initialization");
            }
        }
    }
#else
    (void)params;
#endif

    return result;
}

} // namespace cotton_detection_ros2
