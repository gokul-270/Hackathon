/**
 * @file cotton_detection_node_init.cpp
 * @brief Initialization and configuration for Cotton Detection Node
 *
 * Extracted from cotton_detection_node.cpp to improve build performance.
 * Contains: initialize_interfaces, configure_performance_monitor
 */

#include "cotton_detection_ros2/cotton_detection_node.hpp"

namespace cotton_detection_ros2
{

void CottonDetectionNode::initialize_interfaces()
{
    // === Callback Groups (MultiThreadedExecutor safety) ===
    // Two MutuallyExclusiveCallbackGroups ensure detection inference (500ms-12s)
    // never starves thermal monitoring or diagnostics timers.
    detection_group_ = this->create_callback_group(
        rclcpp::CallbackGroupType::MutuallyExclusive);
    monitoring_group_ = this->create_callback_group(
        rclcpp::CallbackGroupType::MutuallyExclusive);

    // Initialize image transport
    image_transport_ = std::make_shared<image_transport::ImageTransport>(shared_from_this());

    // Initialize TF2 static broadcaster
    tf_static_broadcaster_ = std::make_shared<tf2_ros::StaticTransformBroadcaster>(shared_from_this());

    // Initialize diagnostic updater (Phase 3.2)
    diagnostic_updater_ = std::make_shared<diagnostic_updater::Updater>(shared_from_this());
    diagnostic_updater_->setHardwareID("cotton_detection_node");
    diagnostic_updater_->add("Cotton Detection Status", this, &CottonDetectionNode::diagnostic_callback);
#ifdef HAS_DEPTHAI
    diagnostic_updater_->add("DepthAI Camera Status", this, &CottonDetectionNode::depthai_diagnostic_callback);
#endif

    // === Publishers ===
    // Configure QoS for reliable detection result publishing
    auto qos = rclcpp::QoS(10)
        .reliability(rclcpp::ReliabilityPolicy::Reliable)
        .history(rclcpp::HistoryPolicy::KeepLast)
        .durability(rclcpp::DurabilityPolicy::Volatile);

    pub_detection_result_ = this->create_publisher<cotton_detection_msgs::msg::DetectionResult>(
        "cotton_detection/results", qos);

    pub_camera_info_ = this->create_publisher<sensor_msgs::msg::CameraInfo>(
        "camera/camera_info", qos);

    if (enable_debug_output_) {
        pub_debug_image_ = this->create_publisher<sensor_msgs::msg::CompressedImage>(
            debug_image_topic_, 10);
        debug_image_pub_ = image_transport_->advertise("cotton_detection/debug_image", 1);
    }

    // Construct DetectionEngine with current configuration
    {
        DetectionConfig det_config;
        det_config.detection_confidence_threshold = detection_confidence_threshold_;
        det_config.workspace_max_x = workspace_max_x_;
        det_config.workspace_max_y = workspace_max_y_;
        det_config.workspace_max_z = workspace_max_z_;
        det_config.workspace_min_z = workspace_min_z_;
        det_config.workspace_filter_enabled = workspace_filter_enabled_;
        det_config.save_input_image = save_input_image_;
        det_config.save_output_image = save_output_image_;
        det_config.file_save_mode_timestamp = file_save_mode_timestamp_;
        det_config.save_async = save_async_;
        det_config.save_queue_depth = save_queue_depth_;
        det_config.save_jpeg_quality = save_jpeg_quality_;
        det_config.input_dir = input_dir_;
        det_config.output_dir = output_dir_;
        det_config.cache_validity_ms = static_cast<int>(this->get_parameter("detection.cache_validity_ms").as_int());
        det_config.verbose_timing = verbose_timing_;
#ifdef HAS_DEPTHAI
        det_config.depthai_enable = depthai_enable_;
        det_config.depthai_model_path = depthai_model_path_;
        det_config.depthai_num_classes = depthai_num_classes_;
        det_config.depthai_swap_class_labels = depthai_swap_class_labels_;
        det_config.depthai_camera_width = depthai_camera_width_;
        det_config.depthai_camera_height = depthai_camera_height_;
        det_config.depthai_camera_fps = depthai_camera_fps_;
        det_config.depthai_confidence_threshold = depthai_confidence_threshold_;
        det_config.depthai_depth_min_mm = depthai_depth_min_mm_;
        det_config.depthai_depth_max_mm = depthai_depth_max_mm_;
        det_config.depthai_enable_depth = depthai_enable_depth_;
        det_config.depthai_device_id = depthai_device_id_;
        det_config.depthai_warmup_seconds = depthai_warmup_seconds_;
        det_config.depthai_max_queue_drain = depthai_max_queue_drain_;
        det_config.depthai_flush_before_read = depthai_flush_before_read_;
        det_config.depthai_keep_aspect_ratio = depthai_keep_aspect_ratio_;
        det_config.depthai_auto_pause_after_detection = depthai_auto_pause_after_detection_;
        det_config.depthai_detection_timeout_ms = depthai_detection_timeout_ms_;
        det_config.depthai_stereo_confidence_threshold = depthai_stereo_confidence_threshold_;
        det_config.depthai_bbox_scale_factor = depthai_bbox_scale_factor_;
        det_config.depthai_extended_disparity = depthai_extended_disparity_;
        det_config.depthai_spatial_calc_algorithm = depthai_spatial_calc_algorithm_;
        det_config.depthai_mono_resolution = depthai_mono_resolution_;
        det_config.depthai_lr_check = depthai_lr_check_;
        det_config.depthai_subpixel = depthai_subpixel_;
        det_config.depthai_median_filter = depthai_median_filter_;
        det_config.exposure_mode = exposure_mode_;
        det_config.exposure_time_us = exposure_time_us_;
        det_config.exposure_iso = exposure_iso_;
        det_config.thermal_warning_temp_c = thermal_warning_temp_c_;
        det_config.thermal_throttle_temp_c = thermal_throttle_temp_c_;
        det_config.thermal_critical_temp_c = thermal_critical_temp_c_;
        det_config.border_filter_enabled = border_filter_enabled_;
        det_config.border_margin = border_margin_;
#endif

        auto logger_cb = [this](cotton_detection::LogLevel level, const std::string& msg) {
            switch (level) {
                case cotton_detection::LogLevel::DEBUG:
                    RCLCPP_DEBUG(this->get_logger(), "%s", msg.c_str()); break;
                case cotton_detection::LogLevel::INFO:
                    RCLCPP_INFO(this->get_logger(), "%s", msg.c_str()); break;
                case cotton_detection::LogLevel::WARN:
                    RCLCPP_WARN(this->get_logger(), "%s", msg.c_str()); break;
                case cotton_detection::LogLevel::ERROR:
                    RCLCPP_ERROR(this->get_logger(), "%s", msg.c_str()); break;
            }
        };

        // Create async JSON logger for background structured logging
        async_json_logger_ = std::make_unique<AsyncJsonLogger>(logger_cb, 5);
        async_json_logger_->start();

        detection_engine_ = std::make_unique<DetectionEngine>(
            det_config, logger_cb, performance_monitor_.get(),
            async_image_saver_.get(), async_json_logger_.get());
    }

    // Construct ServiceHandler with NodeInterface and ServiceConfig
    {
        ServiceConfig svc_config;
        svc_config.calibration_output_dir = calibration_output_dir_;
        svc_config.calibration_timeout_sec = calibration_timeout_sec_;
        svc_config.calibration_script_override = calibration_script_override_;
        svc_config.simulation_mode = simulation_mode_;
        svc_config.simulated_positions = simulated_positions_;
        svc_config.simulation_noise_stddev = simulation_noise_stddev_;
        svc_config.simulation_confidence_min = simulation_confidence_min_;
        svc_config.simulation_confidence_max = simulation_confidence_max_;

        NodeInterface node_iface{
            this->get_logger(),
            this->get_clock(),
            detection_engine_.get(),
            performance_monitor_.get(),
            shutdown_requested_,
            detection_active_,
            last_request_time_,
            idle_state_,
            warmup_completed_,
            image_mutex_,
            latest_image_,
            latest_image_stamp_,
            image_available_,
            [this](const std::vector<geometry_msgs::msg::Point> & positions, bool success) {
                publish_detection_result(positions, success);
            }
        };

        service_handler_ = std::make_unique<ServiceHandler>(
            std::move(node_iface), svc_config);
    }

    // === Service Servers (assigned to detection_group_) ===
    // Must be created AFTER service_handler_ construction (above)
    service_enhanced_ = this->create_service<cotton_detection_msgs::srv::CottonDetection>(
        "cotton_detection/detect",
        std::bind(&ServiceHandler::handle_cotton_detection, service_handler_.get(),
                  std::placeholders::_1, std::placeholders::_2),
        rmw_qos_profile_services_default,
        detection_group_);

    // Camera power control service (thermal management)
    service_camera_control_ = this->create_service<std_srvs::srv::SetBool>(
        "cotton_detection/camera_control",
        std::bind(&ServiceHandler::handle_camera_control, service_handler_.get(),
                  std::placeholders::_1, std::placeholders::_2),
        rmw_qos_profile_services_default,
        detection_group_);

    if (!simulation_mode_) {
        // === Subscribers (skipped in simulation - no camera hardware) ===
        sub_camera_image_ = this->create_subscription<sensor_msgs::msg::Image>(
            camera_topic_, 10,
            std::bind(&CottonDetectionNode::image_callback, this, std::placeholders::_1));

        sub_camera_compressed_ = this->create_subscription<sensor_msgs::msg::CompressedImage>(
            camera_topic_ + "/compressed", 10,
            std::bind(&CottonDetectionNode::compressed_image_callback, this, std::placeholders::_1));

        // Image transport subscriber as backup
        image_sub_ = image_transport_->subscribe(
            camera_topic_, 1,
            [this](const sensor_msgs::msg::Image::ConstSharedPtr & msg) {
                this->image_callback(msg);
            });

        // DepthAI camera initialization (OAK-D Lite) - Phase 1.3
#ifdef HAS_DEPTHAI
        if (detection_engine_->initialize_depthai()) {
            RCLCPP_INFO(this->get_logger(), "📷 Camera: Using DepthAI OAK-D Lite (C++ Direct Integration)");

            // Start thermal monitoring timer if enabled
            if (thermal_enable_ && thermal_check_interval_sec_ > 0.0) {
                auto interval_ms = static_cast<int>(thermal_check_interval_sec_ * 1000);
                thermal_timer_ = this->create_wall_timer(
                    std::chrono::milliseconds(interval_ms),
                    std::bind(&CottonDetectionNode::thermal_check_callback, this),
                    monitoring_group_
                );
                RCLCPP_INFO(this->get_logger(),
                    "🌡️ Thermal monitoring enabled (check every %.1fs, warn=%.0f°C, throttle=%.0f°C, critical=%.0f°C)",
                    thermal_check_interval_sec_, thermal_warning_temp_c_,
                    thermal_throttle_temp_c_, thermal_critical_temp_c_);
            }
        } else {
            RCLCPP_INFO(this->get_logger(), "📷 Camera: Using DepthAI OAK-D Lite (via Python wrapper)");
        }
#else
        RCLCPP_INFO(this->get_logger(), "📷 Camera: Using DepthAI OAK-D Lite (via Python wrapper)");
#endif
    } else {
        RCLCPP_INFO(this->get_logger(), "SIMULATION mode: Skipping camera initialization (no hardware required)");
    }

    // Note: Camera TF is handled by robot_state_publisher from URDF
    // Do not publish transforms here to avoid conflicts

    // Start diagnostic timer (update every 5 seconds - reduced overhead)
    // Assigned to monitoring_group_ so diagnostics are never starved by detection
    diagnostic_timer_ = this->create_wall_timer(
        std::chrono::seconds(5),
        [this]() { diagnostic_updater_->force_update(); },
        monitoring_group_
    );

    // Periodic stats logging (temperature + detect stats) - configurable interval
#ifdef HAS_DEPTHAI
    if (stats_log_interval_sec_ > 0.0) {
        auto interval_ms = static_cast<int>(stats_log_interval_sec_ * 1000);
        stats_timer_ = this->create_wall_timer(
            std::chrono::milliseconds(interval_ms),
            std::bind(&CottonDetectionNode::stats_log_callback, this),
            monitoring_group_
        );
        RCLCPP_INFO(this->get_logger(), "📊 Periodic stats logging enabled (every %.1fs)", stats_log_interval_sec_);
    } else {
        RCLCPP_INFO(this->get_logger(), "📊 Periodic stats logging disabled (interval=0)");
    }
#endif
}

void CottonDetectionNode::configure_performance_monitor()
{
    if (!performance_monitor_) return;

    performance_monitor_->set_detailed_logging(performance_detailed_logging_);
    performance_monitor_->set_max_recent_measurements(performance_max_recent_measurements_);

    if (enable_performance_monitoring_) {
        performance_monitor_->start_monitoring();
        RCLCPP_INFO(this->get_logger(), "🔧 Performance monitor configured and started");
    } else {
        RCLCPP_INFO(this->get_logger(), "🔧 Performance monitor disabled");
    }
}

} // namespace cotton_detection_ros2
