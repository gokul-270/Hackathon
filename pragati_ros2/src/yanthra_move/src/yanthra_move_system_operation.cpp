// Copyright 2025 Pragati Robotics

#include "yanthra_move/yanthra_move_system.hpp"
#include "yanthra_move/core/motion_controller.hpp"
#include "yanthra_move/error_recovery_types.hpp"
#include "yanthra_move/yanthra_utilities.hpp"
#include "cotton_detection_msgs/msg/detection_result.hpp"
#include "cotton_detection_msgs/msg/cotton_position.hpp"
#include "cotton_detection_msgs/srv/cotton_detection.hpp"

#include <chrono>
#include <thread>

extern std::atomic<bool> global_stop_requested;
extern std::string createTimestampedLogFile(const std::string& prefix);

namespace yanthra_move {

void YanthraMoveSystem::initializeCottonDetection() {
    RCLCPP_INFO(node_->get_logger(), "🌱 Initializing cotton detection subscription...");

    // Create subscription to cotton detection results topic
    // Topic name should match the publisher in cotton_detection_msgs
    // Inline lambda callback to avoid header pollution with message types
    cotton_detection_sub_ = node_->create_subscription<cotton_detection_msgs::msg::DetectionResult>(
        "/cotton_detection/results",
        rclcpp::QoS(10).reliable(),
        [this](const cotton_detection_msgs::msg::DetectionResult::SharedPtr msg) {
            // Thread-safe update of latest detection data
            auto recv_epoch_us = std::chrono::duration_cast<std::chrono::microseconds>(  // INSTRUMENTATION
                std::chrono::steady_clock::now().time_since_epoch()).count();  // INSTRUMENTATION
            std::lock_guard<std::mutex> lock(detection_mutex_);

            // Store the latest detection result in type-erased storage
            latest_detection_ = std::make_shared<cotton_detection_msgs::msg::DetectionResult>(*msg);
            has_detection_ = true;
            last_detection_time_ = node_->get_clock()->now();

            RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Topic callback - Setting last_detection_time_=%ld.%09ld, positions=%zu INSTRUMENTATION recv_epoch_us=%ld",
                       static_cast<long>(last_detection_time_.nanoseconds() / 1000000000L),
                       static_cast<long>(last_detection_time_.nanoseconds() % 1000000000L),
                       msg->positions.size(), recv_epoch_us);  // INSTRUMENTATION

            // CRITICAL: Notify waiting threads that fresh data arrived
            detection_cv_.notify_all();

            // Log reception with summary info
            RCLCPP_DEBUG(node_->get_logger(),
                         "🌱 Received cotton detection: %zu positions, timestamp: %d.%d",
                         msg->positions.size(),
                         msg->header.stamp.sec,
                         msg->header.stamp.nanosec);

            // Log individual positions at debug level for detailed inspection
            for (size_t i = 0; i < msg->positions.size(); ++i) {
                const auto& pos = msg->positions[i];
                RCLCPP_DEBUG(node_->get_logger(),
                             "  Cotton[%zu]: (%.3f, %.3f, %.3f) conf=%.2f",
                             i, pos.position.x, pos.position.y, pos.position.z,
                             pos.confidence);
            }
        });

    // Initialize last detection time
    last_detection_time_ = node_->get_clock()->now();

    RCLCPP_INFO(node_->get_logger(),
                "✅ Cotton detection subscription initialized on topic: /cotton_detection/results");
    RCLCPP_INFO(node_->get_logger(),
                "   Data will be buffered and provided to MotionController via callback");
    RCLCPP_INFO(node_->get_logger(),
                "   ⚠️  IMPORTANT: Cotton detection node must publish to /cotton_detection/results");
}

bool YanthraMoveSystem::shouldTriggerCottonDetection() const {
    // Check if in ArUco calibration mode - ArUco mode uses different detection method
    if (yanthra_lab_calibration_testing_) {
        RCLCPP_DEBUG(node_->get_logger(),
                    "Cotton detection service not triggered: ArUco calibration mode active");
        return false;
    }

    // Check if service client is initialized
    if (!cotton_detection_service_) {
        RCLCPP_DEBUG(node_->get_logger(),
                    "Cotton detection service not triggered: service client not initialized");
        return false;
    }

    // Check if the detection service node is actually running
    if (!cotton_detection_service_->service_is_ready()) {
        ++detection_unavailable_count_;
        RCLCPP_WARN(node_->get_logger(),
                    "Cotton detection service not ready (node may have crashed). "
                    "Unavailable count: %d", detection_unavailable_count_.load());
        return false;
    }

    // All conditions met - cotton detection should be triggered
    return true;
}
void YanthraMoveSystem::runMainOperationLoop() {
    RCLCPP_INFO(node_->get_logger(), "🚀 Starting main robotic arm operation loop");

    // Initialize arm status
    { std::lock_guard<std::mutex> lock(arm_status_mutex_); arm_status_ = "uninit"; }
    RCLCPP_INFO(node_->get_logger(), "Publishing Arm Status to ARMCLIENT");

    // Create timestamped log files
    std::string log_filename = createTimestampedLogFile("xyz");
    if (log_filename.empty()) {
        throw std::runtime_error("Failed to create log file");
    }
    std::string log_movement = createTimestampedLogFile("arm");
    if (log_movement.empty()) {
        throw std::runtime_error("Failed to create movement log file");
    }

    RCLCPP_INFO(node_->get_logger(), "Log files created successfully");

    // CRITICAL FIX: Perform initialization and homing BEFORE waiting for start_switch
    if (!performInitializationAndHoming()) {
        RCLCPP_ERROR(node_->get_logger(), "❌ Initialization and homing failed! Cannot proceed with operation.");
        { std::lock_guard<std::mutex> lock(arm_status_mutex_); arm_status_ = "error"; }
        throw std::runtime_error("Initialization and homing failed");
    }

    RCLCPP_INFO(node_->get_logger(), "✅ Initialization and homing completed successfully");

    // FIX: Warm-up detection trigger to ensure camera is ready before declaring system ready
    // This prevents "first trigger fails" issue where camera cold start takes >500ms
    if (shouldTriggerCottonDetection()) {
        RCLCPP_INFO(node_->get_logger(), "🔄 Performing warm-up detection to initialize camera pipeline...");

        if (cotton_detection_service_->wait_for_service(std::chrono::seconds(10))) {
            auto request = std::make_shared<cotton_detection_msgs::srv::CottonDetection::Request>();
            request->detect_command = 1;

            try {
                // Clear any stale data
                {
                    std::lock_guard<std::mutex> lock(detection_mutex_);
                    has_detection_ = false;
                    latest_detection_.reset();
                }

                // Trigger warm-up detection
                cotton_detection_service_->async_send_request(request);
                RCLCPP_INFO(node_->get_logger(), "   📤 Warm-up detection triggered");

                // Wait for camera to warm up (first detection can take 1-2 seconds)
                auto warmup_start = std::chrono::steady_clock::now();
                constexpr int warmup_timeout_ms = 3000;  // 3 seconds for cold camera start
                bool warmup_success = false;

                while (std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::steady_clock::now() - warmup_start).count() < warmup_timeout_ms) {
                    {
                        std::lock_guard<std::mutex> lock(detection_mutex_);
                        if (has_detection_) {
                            warmup_success = true;
                            break;
                        }
                    }
                    // BLOCKING_SLEEP_OK: main-thread camera warm-up poll — reviewed 2026-03-14
                    std::this_thread::sleep_for(std::chrono::milliseconds(50));
                }

                if (warmup_success) {
                    RCLCPP_INFO(node_->get_logger(), "   ✅ Camera warm-up complete - detection pipeline verified");
                } else {
                    RCLCPP_WARN(node_->get_logger(), "   ⚠️ Camera warm-up timed out - first trigger may be slow");
                }
            } catch (const std::exception& e) {
                detection_service_failure_count_.fetch_add(1);
                RCLCPP_WARN(node_->get_logger(),
                    "{\"event\":\"warmup_detection_failure\","
                    "\"consecutive_failures\":%u,"
                    "\"error\":\"%s\"}",
                    detection_service_failure_count_.load(), e.what());
            }
        } else {
            RCLCPP_WARN(node_->get_logger(), "   ⚠️ Cotton detection service not available for warm-up");
        }
    }

    // Set arm status to ready after successful homing and camera warm-up
    { std::lock_guard<std::mutex> lock(arm_status_mutex_); arm_status_ = "ready"; }
    RCLCPP_INFO(node_->get_logger(), "✅ ARM STATUS: ready (system initialized and awaiting start command)");

    // CRITICAL SAFETY: Clear any stale START_SWITCH flags and enable processing
    // This prevents race conditions where START_SWITCH arrives during initialization
    start_switch_topic_received_.store(false);  // Clear any stale triggers
    system_ready_for_start_switch_.store(true);  // NOW enable START_SWITCH processing
    RCLCPP_INFO(node_->get_logger(), "🔓 START_SWITCH processing enabled (stale triggers cleared)");

    // Use the modular Motion Controller for the main operational logic
    bool continue_operation = true;

    // Configure timeouts based on max_runtime_minutes parameter
    auto start_time = std::chrono::steady_clock::now();
    bool use_timeout = (max_runtime_minutes_ != -1); // -1 means infinite, no timeout

    // Initialize with defaults to avoid compiler warnings
    std::chrono::seconds max_runtime_single = std::chrono::seconds(60);
    std::chrono::minutes max_runtime_continuous = std::chrono::minutes(30);

    if (max_runtime_minutes_ == 0) {
        // Use defaults (already initialized above)
        max_runtime_single = std::chrono::seconds(60); // 1 minute for single-run
        max_runtime_continuous = std::chrono::minutes(30); // 30 minutes max for continuous
    } else if (max_runtime_minutes_ > 0) {
        // Use configured value for both modes
        max_runtime_single = std::chrono::minutes(max_runtime_minutes_);
        max_runtime_continuous = std::chrono::minutes(max_runtime_minutes_);
    }
    // If max_runtime_minutes_ == -1, use_timeout is false and we skip timeout checks

        while (continue_operation && rclcpp::ok() && !global_stop_requested.load() && !global_stop_requested_.load()
               && yanthra_move::executor_running.load()) {
            // Callbacks are processed by the background executor thread

            start_time_ = getCurrentTimeMillis();

            // Check for executor thread health (if it died, callbacks stop processing)
            if (!yanthra_move::executor_running.load()) {
                RCLCPP_FATAL(node_->get_logger(), "Executor thread died! ROS2 callbacks are no longer being processed. Stopping operation.");
                continue_operation = false;
                break;
            }

            // Check for shutdown signals more frequently in continuous mode
            if (global_stop_requested.load() || global_stop_requested_.load()) {
                RCLCPP_WARN(node_->get_logger(), "🛑 Shutdown signal detected, stopping operation loop gracefully");
                continue_operation = false;
                break;
            }

        // Safety timeouts to prevent infinite operation (unless disabled with max_runtime_minutes=-1)
        if (use_timeout) {
            auto elapsed = std::chrono::steady_clock::now() - start_time;
            if (!continuous_operation_.load()) {
                // Single-run mode timeout
                if (elapsed > max_runtime_single) {
                    auto minutes = std::chrono::duration_cast<std::chrono::minutes>(max_runtime_single).count();
                    auto seconds = std::chrono::duration_cast<std::chrono::seconds>(max_runtime_single).count();
                    if (minutes > 0) {
                        RCLCPP_WARN(node_->get_logger(), "⏰ Safety timeout reached in single-run mode (%ldmin), shutting down gracefully", minutes);
                    } else {
                        RCLCPP_WARN(node_->get_logger(), "⏰ Safety timeout reached in single-run mode (%lds), shutting down gracefully", seconds);
                    }
                    continue_operation = false;
                    break;
                }
            } else {
                // Continuous mode timeout
                if (elapsed > max_runtime_continuous) {
                    auto minutes = std::chrono::duration_cast<std::chrono::minutes>(max_runtime_continuous).count();
                    RCLCPP_WARN(node_->get_logger(), "⏰ Safety timeout reached in continuous mode (%ldmin), shutting down gracefully", minutes);
                    RCLCPP_WARN(node_->get_logger(), "💡 To continue operation, restart the system or set max_runtime_minutes to a higher value");
                    continue_operation = false;
                    break;
                }
            }
        }

        // NOW WAIT FOR START_SWITCH SIGNAL (after initialization and homing are complete)

        // CRITICAL: Clear any stale start_switch flag before waiting
        // This prevents double-triggering when the flag was set during previous cycle's spin_some()
        start_switch_topic_received_.store(false);

        // Get configurable START_SWITCH parameters (declared during initialization)
        double start_switch_timeout_sec = node_->get_parameter("start_switch.timeout_sec").as_double();
        bool start_switch_enable_wait = node_->get_parameter("start_switch.enable_wait").as_bool();

        // In continuous operation mode, disable start switch timeout (wait indefinitely)
        // Field trial: robot must wait for operator start signal without timing out
        if (continuous_operation_.load() && start_switch_timeout_sec > 0.0) {
            RCLCPP_INFO(node_->get_logger(),
                        "🔄 Continuous operation mode: overriding start_switch timeout "
                        "(%.1fs -> indefinite wait)", start_switch_timeout_sec);
            start_switch_timeout_sec = 0.0;
        }
        // NOTE: start_switch.prefer_topic no longer used - arm only monitors topic (not GPIO)
        // GPIO start button is monitored by vehicle controller which forwards via MQTT/topic

        bool start_switch_pressed = false;

        // Skip START_SWITCH wait entirely if disabled (for dev/CI/simulation)
        if (!start_switch_enable_wait) {
            RCLCPP_INFO(node_->get_logger(), "💡 START_SWITCH wait disabled - proceeding directly to operation");
            start_switch_pressed = true;
        }

        // CRITICAL: If start_switch_pressed is already true (disabled), skip the entire wait loop
        if (start_switch_pressed) {
            RCLCPP_INFO(node_->get_logger(), "🚀 Bypassing START_SWITCH wait - starting operation immediately");
        } else {
            // Only enter wait loop if START_SWITCH is enabled
            auto wait_start = std::chrono::steady_clock::now();
            bool use_start_switch_timeout = (start_switch_timeout_sec > 0.0); // -1 or negative means infinite wait
            const auto max_wait_time = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::duration<double>(start_switch_timeout_sec > 0.0 ? start_switch_timeout_sec : 1.0));

            if (!use_start_switch_timeout) {
                RCLCPP_INFO(node_->get_logger(), "⏳ Waiting for START_SWITCH trigger (no timeout)...");
                RCLCPP_INFO(node_->get_logger(), "   💡 Send trigger: ros2 topic pub --once /start_switch/command std_msgs/msg/Bool \"data: true\"");
            } else {
                RCLCPP_INFO(node_->get_logger(), "⏳ Will timeout after %.1f seconds if no START_SWITCH signal", start_switch_timeout_sec);
            }

            auto last_heartbeat = std::chrono::steady_clock::now();

            while (!start_switch_pressed && continue_operation && rclcpp::ok() && !global_stop_requested.load() && !global_stop_requested_.load()
                   && yanthra_move::executor_running.load()) {
                // Check for executor thread health (if it died, we'll never receive START_SWITCH topic)
                if (!yanthra_move::executor_running.load()) {
                    RCLCPP_FATAL(node_->get_logger(), "Executor thread died during START_SWITCH wait! Cannot receive topic callbacks. Stopping.");
                    continue_operation = false;
                    break;
                }

                // Check for shutdown first (most important)
                if (global_stop_requested.load() || global_stop_requested_.load()) {
                    RCLCPP_WARN(node_->get_logger(), "🛑 Shutdown requested during START_SWITCH wait");
                    continue_operation = false;
                    break;
                }

                // CRITICAL: Process ROS2 callbacks while waiting (non-blocking)
                // Callbacks are processed by the background executor thread

                // Check START_SWITCH state - ARM ONLY USES TOPIC (not GPIO)
                if (start_switch_topic_received_.load()) {
                    start_switch_pressed = true;
                    RCLCPP_INFO(node_->get_logger(), "🎯 START_SWITCH topic received! Beginning operation.");
                    start_switch_topic_received_.store(false); // Clear flag immediately
                    break;
                }

                // Periodic heartbeat log (every 30 seconds) so user knows system is alive
                auto now = std::chrono::steady_clock::now();
                if (std::chrono::duration_cast<std::chrono::seconds>(now - last_heartbeat).count() >= 30) {
                    last_heartbeat = now;
                    RCLCPP_INFO(node_->get_logger(), "Waiting for start switch signal...");
                }

                // Check for timeout (only if enabled)
                if (use_start_switch_timeout) {
                    auto wait_elapsed = std::chrono::steady_clock::now() - wait_start;
                    if (wait_elapsed > max_wait_time) {
                        RCLCPP_ERROR(node_->get_logger(), "[PARAM] ⏰ START_SWITCH timeout after %.1f seconds! Entering safe idle state.", start_switch_timeout_sec);
                        RCLCPP_ERROR(node_->get_logger(), "[PARAM] 💡 To fix: ros2 topic pub --once /start_switch/command std_msgs/msg/Bool \"data: true\"");
                        RCLCPP_ERROR(node_->get_logger(), "[PARAM] 🛑 Robot entering safe idle state to prevent infinite loops.");

                        // Move arm to safe parking position
                        if (motion_controller_) {
                            (void)motion_controller_->moveToPackingPosition();  // Best-effort safe idle
                        }

                        // Exit immediately - do not continue operation
                        continue_operation = false;
                        break;
                    }
                }

                // Very small delay to prevent busy waiting but remain responsive
                // BLOCKING_SLEEP_OK: main-thread anti-busy-wait in operation loop — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        }

        if (!continue_operation) {
            break;
        }

        // CRITICAL: Final shutdown check before starting operational cycle
        // This prevents race condition where signal arrives during START_SWITCH wait
        if (global_stop_requested.load() || global_stop_requested_.load()) {
            RCLCPP_WARN(node_->get_logger(), "🛑 Shutdown signal detected - aborting operational cycle");
            continue_operation = false;
            break;
        }

        // Trigger cotton detection service if enabled and not in ArUco mode
        // This sends a detect command to the cotton detection node to capture a fresh frame
        // System still relies on topic subscription for actual detection results
        if (shouldTriggerCottonDetection()) {
            RCLCPP_INFO(node_->get_logger(),
                       "🌱 START_SWITCH pressed - triggering cotton detection service (detect_command=1)");

            // Wait briefly for service availability (max 5 seconds)
            if (!cotton_detection_service_->wait_for_service(std::chrono::seconds(5))) {
                RCLCPP_WARN(node_->get_logger(),
                           "⚠️  Cotton detection service not available after 5 seconds; "
                           "continuing with topic subscription only");
            } else {
                auto request = std::make_shared<cotton_detection_msgs::srv::CottonDetection::Request>();
                request->detect_command = 1;  // 1 = detect (single frame capture)

                try {
                    // Clear stale detection data BEFORE triggering new detection
                    {
                        std::lock_guard<std::mutex> lock(detection_mutex_);
                        has_detection_ = false;
                        latest_detection_.reset();
                        RCLCPP_DEBUG(node_->get_logger(), "🧹 Cleared stale detection buffer");
                    }

                    // Send async request (fire and forget - we'll use subscription data)
                    cotton_detection_service_->async_send_request(request);
                    auto trigger_epoch_us = std::chrono::duration_cast<std::chrono::microseconds>(  // INSTRUMENTATION
                        std::chrono::steady_clock::now().time_since_epoch()).count();  // INSTRUMENTATION
                    RCLCPP_INFO(node_->get_logger(), "📤 Cotton detection service triggered INSTRUMENTATION trigger_epoch_us=%ld", trigger_epoch_us);  // INSTRUMENTATION

                    // Wait for fresh detection result with timeout and polling
                    // Detection node responds in ~65ms avg, so 200ms is plenty of margin
                    auto start_wait = std::chrono::steady_clock::now();
                    constexpr int max_wait_ms = 200;  // 200ms max wait (detection avg ~65ms)
                    constexpr int poll_interval_ms = 5;  // Check every 5ms for responsiveness

                    bool received_fresh_data = false;
                    while (std::chrono::duration_cast<std::chrono::milliseconds>(
                            std::chrono::steady_clock::now() - start_wait).count() < max_wait_ms) {
                        {
                            std::lock_guard<std::mutex> lock(detection_mutex_);
                            if (has_detection_) {
                                received_fresh_data = true;
                                RCLCPP_INFO(node_->get_logger(), "✅ Fresh detection data received");
                                break;
                            }
                        }
                        // Executor thread processes callbacks (including subscription)
                        // Small sleep to avoid busy-waiting
                        // BLOCKING_SLEEP_OK: main-thread detection data poll — reviewed 2026-03-14
                        std::this_thread::sleep_for(std::chrono::milliseconds(poll_interval_ms));
                    }

                    if (!received_fresh_data) {
                        detection_timeout_count_.fetch_add(1);
                        RCLCPP_WARN(node_->get_logger(), "⚠️  Timeout waiting for fresh detection data (timeout #%lu)",
                                    detection_timeout_count_.load());
                    } else {
                        // Log detection timing stats
                        auto detection_wait_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                            std::chrono::steady_clock::now() - start_wait).count();
                        RCLCPP_INFO(node_->get_logger(), "⏱️  Detection data received in %ld ms", detection_wait_ms);
                    }

                } catch (const std::exception& e) {
                    detection_service_failure_count_.fetch_add(1);
                    RCLCPP_WARN(node_->get_logger(),
                        "{\"event\":\"detection_service_failure\","
                        "\"consecutive_failures\":%u,"
                        "\"error\":\"%s\"}",
                        detection_service_failure_count_.load(), e.what());
                }
            }
        } else {
            RCLCPP_DEBUG(node_->get_logger(),
                        "ℹ️  Cotton detection service not triggered (ArUco mode or service unavailable)");
            // If detection was skipped due to service unavailability (not ArUco mode),
            // feed into error recovery for escalation tracking
            if (!yanthra_lab_calibration_testing_ && cotton_detection_service_ &&
                !cotton_detection_service_->service_is_ready()) {
                FailureContext ctx;
                ctx.joint_id = 0;  // Not joint-specific
                ctx.phase = "detection_trigger";
                handleOperationalFailure(FailureType::DETECTION_UNAVAILABLE, ctx);
            }
        }

        // Log cycle start
        RCLCPP_INFO(node_->get_logger(), " ");
        RCLCPP_INFO(node_->get_logger(), "╔════════════════════════════════════════════════════════════════╗");
        RCLCPP_INFO(node_->get_logger(), "║  🚀 STARTING OPERATIONAL CYCLE                                 ║");
        RCLCPP_INFO(node_->get_logger(), "╚════════════════════════════════════════════════════════════════╝");

        // Set arm status to busy when starting operational cycle
        { std::lock_guard<std::mutex> lock(arm_status_mutex_); arm_status_ = "busy"; }
        cycle_in_progress_.store(true);  // Mark cycle as running (for start switch tracking)
        RCLCPP_INFO(node_->get_logger(), "🔄 ARM STATUS: busy (executing operational cycle)");

        // Execute operational cycle using Motion Controller
        bool cycle_successful = motion_controller_->executeOperationalCycle();

        // Mark cycle as complete (before status update)
        cycle_in_progress_.store(false);

        if (!cycle_successful) {
            RCLCPP_ERROR(node_->get_logger(), "❌ Operational cycle failed, stopping operations");
            { std::lock_guard<std::mutex> lock(arm_status_mutex_); arm_status_ = "error"; }
            continue_operation = false;
            break;
        }

        // Set arm status back to ready after successful cycle completion
        { std::lock_guard<std::mutex> lock(arm_status_mutex_); arm_status_ = "ready"; }
        RCLCPP_INFO(node_->get_logger(), "✅ ARM STATUS: ready (cycle completed successfully)");

        end_time_ = getCurrentTimeMillis();
        // Cycle timing completed

        // Check continuous operation parameter
        if (continuous_operation_.load()) {
            RCLCPP_INFO(node_->get_logger(), "✅ Operational cycle completed. Continuous operation enabled - starting next cycle...");
            // Don't hardcode true - check for stop conditions
            continue_operation = !global_stop_requested.load() && !global_stop_requested_.load();

            // Brief pause between cycles to prevent CPU spin and allow ROS2 processing
            // BLOCKING_SLEEP_OK: main-thread cycle pause between operations — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        } else {
            RCLCPP_WARN(node_->get_logger(), "✅ Operational cycle completed. Continuous operation DISABLED - stopping after this cycle.");
            RCLCPP_INFO(node_->get_logger(), "💡 Exiting gracefully after one cycle (continuous_operation=false). To enable continuous operation, launch with continuous_operation:=true");
            continue_operation = false;
        }

        // Check for emergency stop from Motion Controller or global ESC key
        if (motion_controller_->isEmergencyStopRequested() || global_stop_requested_.load()) {
            RCLCPP_WARN(node_->get_logger(), "🛑 Emergency stop requested! Stopping robot operation immediately.");
            continue_operation = false;
        }
    }

    RCLCPP_INFO(node_->get_logger(), "🏁 Main operation loop completed successfully");
}
YanthraMoveSystem::CottonPositionProvider YanthraMoveSystem::getCottonPositionProvider() {
    // Return a lambda that captures 'this' and provides thread-safe access
    // to the latest cotton detection data with staleness and integrity checks.
    // MotionController will call this lambda when it needs cotton positions.
    return [this]() -> std::optional<std::vector<core::CottonDetection>> {
        std::lock_guard<std::mutex> lock(detection_mutex_);

    // Track total requests
    detection_requests_total_.fetch_add(1);

    // Check if we have any detection data
    if (!has_detection_ || !latest_detection_) {
        detection_timeout_count_.fetch_add(1);
            RCLCPP_WARN(node_->get_logger(),
                        "⚠️  No cotton detection data available yet (timeout #%lu)",
                        detection_timeout_count_.load());
            return std::nullopt;
        }

        // Calculate age of latest detection (staleness check using MAX_DETECTION_AGE_MS)
        auto now = node_->get_clock()->now();
        auto detection_age = (now - last_detection_time_).nanoseconds() / 1000000;  // ms

        if (detection_age > MAX_DETECTION_AGE_MS.count()) {
            detection_stale_filtered_.fetch_add(1);
            RCLCPP_WARN(node_->get_logger(),
                        "⏰ Detection data STALE (age: %ld ms > max: %ld ms) - filtered #%lu",
                        detection_age, MAX_DETECTION_AGE_MS.count(), detection_stale_filtered_.load());
            return std::nullopt;
        }

        // Cast from type-erased storage to actual type
        auto detection_ptr = std::static_pointer_cast<cotton_detection_msgs::msg::DetectionResult>(
            latest_detection_);

        // Check detection_successful flag
        if (!detection_ptr->detection_successful) {
            RCLCPP_WARN(node_->get_logger(), "⚠️ Detection unsuccessful — skipping positions");
            return std::nullopt;
        }

        // Extract positions and metadata from DetectionResult
        std::vector<core::CottonDetection> detections;
        detections.reserve(detection_ptr->positions.size());

        auto steady_now = std::chrono::steady_clock::now();

        for (const auto& cotton_pos : detection_ptr->positions) {
            core::CottonDetection det;
            det.position = cotton_pos.position;
            det.confidence = cotton_pos.confidence;
            det.detection_id = cotton_pos.detection_id;
            det.detection_time = steady_now;
            det.processing_time_ms = static_cast<int64_t>(detection_ptr->processing_time_ms);
            detections.push_back(det);
        }

        // Log detection age and processing time
        if (!detections.empty()) {
            RCLCPP_INFO(node_->get_logger(), "⏱️ [TIMING] Detection age: %ldms, processing: %ldms",
                detection_age, static_cast<long>(detections[0].processing_time_ms));
        }

        // Track success stats
        detection_success_count_.fetch_add(1);
        detection_last_age_ms_.store(detection_age);

        RCLCPP_INFO(node_->get_logger(),
                    "🌱 Detection: %zu positions (age: %ld ms, fresh ✓)",
                    detections.size(), detection_age);

        return detections;
    };
}

YanthraMoveSystem::CottonPositionProvider YanthraMoveSystem::getDetectionTriggerCallback() {
    // Return a lambda that triggers a new detection and returns fresh positions.
    // Used by MotionController to re-validate remaining cotton after each pick.
    return [this]() -> std::optional<std::vector<core::CottonDetection>> {
        // Check if detection service is available
        if (!shouldTriggerCottonDetection()) {
            RCLCPP_DEBUG(node_->get_logger(), "Detection trigger skipped (ArUco mode or service unavailable)");
            return std::nullopt;
        }

        // Wait for service availability
        if (!cotton_detection_service_->wait_for_service(std::chrono::seconds(2))) {
            RCLCPP_WARN(node_->get_logger(), "Detection service not available for re-validation");
            return std::nullopt;
        }

        // Store timestamp BEFORE triggering detection (to detect fresh data)
        rclcpp::Time trigger_time = node_->get_clock()->now();
        RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Trigger timestamp: %ld.%09ld",
                   static_cast<long>(trigger_time.nanoseconds() / 1000000000L),
                   static_cast<long>(trigger_time.nanoseconds() % 1000000000L));

        // Trigger new detection
        auto request = std::make_shared<cotton_detection_msgs::srv::CottonDetection::Request>();
        request->detect_command = 1;

        try {
            cotton_detection_service_->async_send_request(request);
        } catch (const std::exception& e) {
            detection_service_failure_count_.fetch_add(1);
            RCLCPP_WARN(node_->get_logger(),
                "{\"event\":\"revalidation_detection_failure\","
                "\"consecutive_failures\":%u,"
                "\"error\":\"%s\"}",
                detection_service_failure_count_.load(), e.what());
            return std::nullopt;
        }

        // Wait for FRESH detection data (timestamp after trigger)
        // CRITICAL: Must periodically spin to process incoming topic callbacks
        std::unique_lock<std::mutex> lock(detection_mutex_);

        RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Before wait - has_detection=%s, last_detection_time=%ld.%09ld",
                   has_detection_ ? "true" : "false",
                   static_cast<long>(last_detection_time_.nanoseconds() / 1000000000L),
                   static_cast<long>(last_detection_time_.nanoseconds() % 1000000000L));

        // Wait with periodic spinning to process callbacks
        auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(1500);
        bool received = false;

        while (std::chrono::steady_clock::now() < deadline) {
            // Unlock mutex FIRST to allow callback to execute
            lock.unlock();

            // Executor thread processes callbacks (including topic callback)
            // Short sleep to avoid busy-waiting
            // BLOCKING_SLEEP_OK: main-thread detection wait with mutex unlock — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::milliseconds(10));

            // Re-lock for condition check
            lock.lock();

            // Check condition
            if (has_detection_ && last_detection_time_ > trigger_time) {
                auto det_ns = static_cast<long>(last_detection_time_.nanoseconds());
                auto trig_ns = static_cast<long>(trigger_time.nanoseconds());
                RCLCPP_INFO(node_->get_logger(), "✅ Fresh detection received (timestamp %ld.%09ld > %ld.%09ld)",
                           det_ns / 1000000000L, det_ns % 1000000000L,
                           trig_ns / 1000000000L, trig_ns % 1000000000L);
                received = true;
                break;
            }
        }

        if (received) {
            // CRITICAL: Lock is still held here - use no-lock version
            return this->getLatestCottonPositions_NoLock();
        }

        detection_timeout_count_.fetch_add(1);
        RCLCPP_WARN(node_->get_logger(), "Timeout waiting for re-detection data (timeout #%lu)",
                    detection_timeout_count_.load());
        return std::nullopt;
    };
}

// Helper function - assumes caller already holds detection_mutex_
std::optional<std::vector<core::CottonDetection>>
YanthraMoveSystem::getLatestCottonPositions_NoLock() const {
    // Check if we have any detection data
    if (!has_detection_ || !latest_detection_) {
        RCLCPP_DEBUG(node_->get_logger(),
                     "⚠️  No cotton detection data available yet");
        return std::nullopt;
    }

    // Cast from type-erased storage to actual type
    auto detection_ptr = std::static_pointer_cast<cotton_detection_msgs::msg::DetectionResult>(
        latest_detection_);

    // Extract positions and metadata from DetectionResult
    std::vector<core::CottonDetection> detections;
    detections.reserve(detection_ptr->positions.size());

    auto now = std::chrono::steady_clock::now();

    for (const auto& cotton_pos : detection_ptr->positions) {
        core::CottonDetection det;
        det.position = cotton_pos.position;
        det.confidence = cotton_pos.confidence;
        det.detection_id = cotton_pos.detection_id;
        det.detection_time = now;  // Use current time as detection timestamp
        det.processing_time_ms = static_cast<int64_t>(detection_ptr->processing_time_ms);
        detections.push_back(det);
    }

    RCLCPP_DEBUG(node_->get_logger(),
                 "✅ Returning %zu cotton detections from latest detection",
                 detections.size());

    return detections;
}

std::optional<std::vector<core::CottonDetection>>
YanthraMoveSystem::getLatestCottonPositions() const {
    std::lock_guard<std::mutex> lock(detection_mutex_);
    return getLatestCottonPositions_NoLock();
}

std::optional<std::vector<geometry_msgs::msg::Point>>
YanthraMoveSystem::getLatestDetectionWithStalenessCheck() const {
    std::lock_guard<std::mutex> lock(detection_mutex_);

    // Track total requests
    detection_requests_total_.fetch_add(1);

    // Check if we have any detection data
    if (!has_detection_ || !latest_detection_) {
        detection_timeout_count_.fetch_add(1);
        RCLCPP_WARN(node_->get_logger(),
                    "⚠️  No cotton detection data available yet (timeout #%lu)",
                    detection_timeout_count_.load());
        return std::nullopt;
    }

    // Calculate age of latest detection
    auto now = node_->get_clock()->now();
    auto detection_age = (now - last_detection_time_).nanoseconds() / 1000000;  // Convert to milliseconds

    // Check if detection is stale
    if (detection_age > MAX_DETECTION_AGE_MS.count()) {
        detection_stale_filtered_.fetch_add(1);
        RCLCPP_WARN(node_->get_logger(),
                    "⏰ Detection data STALE (age: %ld ms > max: %ld ms) - filtered #%lu",
                    detection_age, MAX_DETECTION_AGE_MS.count(), detection_stale_filtered_.load());
        return std::nullopt;
    }

    // Cast from type-erased storage to actual type
    auto detection_ptr = std::static_pointer_cast<cotton_detection_msgs::msg::DetectionResult>(
        latest_detection_);

    // Extract positions from positions array in DetectionResult
    std::vector<geometry_msgs::msg::Point> positions;
    positions.reserve(detection_ptr->positions.size());

    for (const auto& cotton_pos : detection_ptr->positions) {
        // Each CottonPosition has a geometry_msgs/Point position field
        positions.push_back(cotton_pos.position);
    }

    // Track success stats
    detection_success_count_.fetch_add(1);
    detection_last_age_ms_.store(detection_age);

    // Log at INFO level for visibility during testing
    RCLCPP_INFO(node_->get_logger(),
                "🌱 Detection: %zu positions (age: %ld ms, fresh ✓)",
                positions.size(), detection_age);

    return positions;
}

}  // namespace yanthra_move
