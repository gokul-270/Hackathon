// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "yanthra_move/yanthra_move_system.hpp"
#include "yanthra_move/core/motion_controller.hpp"
#include "yanthra_move/joint_move.h"
#include "yanthra_move/transform_cache.hpp"  // Tier 1.3 - Static TF optimization
#include "git_version.h"

// Cotton detection integration
#include "cotton_detection_msgs/msg/detection_result.hpp"
#include "cotton_detection_msgs/msg/cotton_position.hpp"

// System includes
#include <signal.h>
#include <unistd.h>
#include <sys/wait.h>       // For waitpid, WNOHANG (crash handler)
#include <sys/time.h>
#include <sys/resource.h>  // For getrusage (memory stats)
#include <iostream>
#include <fstream>
#include <thread>
#include <chrono>
#include <cstdio>  // For sscanf, fprintf
#include <filesystem>


// Project utilities
#include "yanthra_move/yanthra_utilities.hpp"
#include "yanthra_move/coordinate_transforms.hpp"

// External declarations for global variables
extern std::atomic<bool> global_stop_requested;

// NOTE: yanthra_move does NOT use pragati::install_signal_handlers() because
// it requires SAFETY-CRITICAL crash handling (fork+exec pigs for GPIO cleanup
// on SIGSEGV/SIGABRT) and a second-signal forced exit via std::_Exit().
// These behaviors cannot be expressed through the shared handler's API.
// See signal_handler() and crash_signal_handler() in main() below.

// Keyboard monitoring stubs
// DISABLED: void start_keyboard_monitoring() {
// DISABLED:     // TODO(hardware): Implement keyboard monitoring for manual control
// DISABLED:     //
// DISABLED:     // Purpose: Allow operator to control system via keyboard (emergency stop, mode switch, etc.)
// DISABLED:     //
// DISABLED:     // Expected implementation:
// DISABLED:     //   1. Create background thread to monitor keyboard input
// DISABLED:     //   2. Map keys to commands (e.g., 'e' = emergency stop, 's' = start, 'p' = pause)
// DISABLED:     //   3. Use termios or similar for non-blocking keyboard input
// DISABLED:     //   4. Publish commands to appropriate topics or call service callbacks
// DISABLED:     //   5. Handle Ctrl+C gracefully
// DISABLED:     //
// DISABLED:     // Example skeleton:
// DISABLED:     //   keyboard_thread_ = std::thread([]() {
// DISABLED:     //     struct termios old_tio, new_tio;
// DISABLED:     //     tcgetattr(STDIN_FILENO, &old_tio);
// DISABLED:     //     new_tio = old_tio;
// DISABLED:     //     new_tio.c_lflag &= (~ICANON & ~ECHO);
// DISABLED:     //     tcsetattr(STDIN_FILENO, TCSANOW, &new_tio);
// DISABLED:     //
// DISABLED:     //     while (keyboard_monitoring_active_) {
// DISABLED:     //       char c = getchar();
// DISABLED:     //       switch(c) {
// DISABLED:     //         case 'e': trigger_emergency_stop(); break;
// DISABLED:     //         case 's': start_operation(); break;
// DISABLED:     //         case 'p': pause_operation(); break;
// DISABLED:     //       }
// DISABLED:     //     }
// DISABLED:     //
// DISABLED:     //     tcsetattr(STDIN_FILENO, TCSANOW, &old_tio);
// DISABLED:     //   });
// DISABLED:     //
// DISABLED:     // For now, keyboard monitoring is not active (system uses ROS2 services/topics)
// DISABLED: }

// DISABLED: void stop_keyboard_monitoring() {
// DISABLED:     // TODO(hardware): Implement keyboard monitoring cleanup
// DISABLED:     //
// DISABLED:     // Expected implementation:
// DISABLED:     //   1. Set monitoring flag to false
// DISABLED:     //   2. Join keyboard thread
// DISABLED:     //   3. Restore terminal settings
// DISABLED:     //
// DISABLED:     // Example:
// DISABLED:     //   keyboard_monitoring_active_ = false;
// DISABLED:     //   if (keyboard_thread_.joinable()) {
// DISABLED:     //     keyboard_thread_.join();
// DISABLED:     //   }
// DISABLED: }

// Hardware control stubs - GPIO-based peripheral control
void VacuumPump(bool state) {
    // TODO(hardware): Implement vacuum pump GPIO control
    //
    // Purpose: Control vacuum pump for cotton picking end effector
    //
    // Expected implementation:
    //   1. Use GPIO library (gpiod, wiringPi, or sysfs)
    //   2. Set GPIO pin HIGH/LOW based on state parameter
    //   3. Add safety timeout to prevent continuous operation
    //   4. Log state changes for debugging
    //
    // Example using gpiod:
    //   static struct gpiod_chip *chip = nullptr;
    //   static struct gpiod_line *line = nullptr;
    //
    //   if (!chip) {
    //     chip = gpiod_chip_open_by_name("gpiochip0");
    //     line = gpiod_chip_get_line(chip, VACUUM_PUMP_GPIO_PIN);
    //     gpiod_line_request_output(line, "vacuum_pump", 0);
    //   }
    //
    //   gpiod_line_set_value(line, state ? 1 : 0);
    //
    // For now, just log the command (allows software testing)
    RCLCPP_DEBUG(rclcpp::get_logger("yanthra_move"), "VacuumPump: %s", state ? "ON" : "OFF");
}

void camera_led(bool state) {
    // TODO(hardware): Implement camera LED GPIO control
    //
    // Purpose: Control LED illumination for camera (improves cotton detection)
    //
    // Expected implementation:
    //   Similar to vacuum pump control but for LED GPIO pin
    //   May use PWM for brightness control if needed
    //
    // Example:
    //   gpio_set_value(CAMERA_LED_GPIO_PIN, state ? 1 : 0);
    //
    RCLCPP_DEBUG(rclcpp::get_logger("yanthra_move"), "Camera LED: %s", state ? "ON" : "OFF");
}

void red_led_on() {
    // TODO(hardware): Implement status LED GPIO control
    //
    // Purpose: Visual indicator for system status (error, warning, etc.)
    //
    // Expected implementation:
    //   Control red LED GPIO pin (error indicator)
    //   Consider adding red_led_off() for completeness
    //   May use blinking pattern for different error types
    //
    // Example:
    //   gpio_set_value(RED_LED_GPIO_PIN, 1);
    //
    RCLCPP_DEBUG(rclcpp::get_logger("yanthra_move"), "Red LED: ON");
}

// Logging stub - Timestamped log file creation
std::string createTimestampedLogFile(const std::string& prefix) {
    // TODO(enhancement): Implement timestamped log file creation
    //
    // Purpose: Create unique log files with timestamps for debugging and analysis
    //
    // Expected implementation:
    //   1. Get current timestamp (YYYY-MM-DD_HH-MM-SS format)
    //   2. Create log directory if it doesn't exist
    //   3. Generate filename: <prefix>_<timestamp>.log
    //   4. Return full path to log file
    //   5. Optionally rotate old logs (keep last N days)
    //
    // Example:
    //   auto now = std::chrono::system_clock::now();
    //   auto time_t = std::chrono::system_clock::to_time_t(now);
    //   std::tm tm = *std::localtime(&time_t);
    //
    //   char timestamp[64];
    //   std::strftime(timestamp, sizeof(timestamp), "%Y-%m-%d_%H-%M-%S", &tm);
    //
    //   std::string log_dir = "/var/log/pragati_ros2/";  // Or use ROS2 log directory
    //   std::filesystem::create_directories(log_dir);
    //
    //   std::string filename = log_dir + prefix + "_" + timestamp + ".log";
    //   return filename;
    //
    // For now, return simple filename (ROS2 logger handles timestamps)
    return prefix + "_log.txt";
}

namespace yanthra_move {

// Global variables required by other modules
std::shared_ptr<rclcpp::Node> global_node = nullptr;
std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor = nullptr;
std::atomic<bool> simulation_mode{true};
std::atomic<bool> executor_running{false};
std::thread executor_thread;

} // namespace yanthra_move

// Global variables
std::atomic<bool> global_stop_requested{false};

// Forward declaration for signal handling
extern yanthra_move::YanthraMoveSystem* g_system;

// DEPRECATED: Legacy file-based cotton detection stub - REMOVED
// Now using ROS2 topic-based cotton detection integration:
// cotton_detection_msgs publishes to /cotton_detection/results
// YanthraMoveSystem subscribes and provides data to MotionController
// via the getCottonPositionProvider() callback interface.

namespace yanthra_move {

// ==============================================
// CONSTRUCTOR & DESTRUCTOR
// ==============================================

YanthraMoveSystem::YanthraMoveSystem(int argc, char** argv) {
    try {
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move_system"), "Initializing YanthraMoveSystem...");

        // Initialize in the correct order to ensure dependencies are met
        initializeROS2(argc, argv);
        initializeSignalHandlers();
        initializeKeyboardMonitoring();
        initializeIOInterfaces();
        initializeJointControllers();
        initializeTransformSystem();
        initializeServices();
        initializePublishers();
        initializeCottonDetection();
        loadParameters();
        initializeGPIO();
        initializeHardware();
        initializeCamera();
        initializeModularComponents();

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move_system"), "✅ YanthraMoveSystem initialized successfully");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move_system"), "❌ Failed to initialize YanthraMoveSystem: %s", e.what());
        throw std::runtime_error(std::string("YanthraMoveSystem initialization failed: ") + e.what());
    }
}

YanthraMoveSystem::~YanthraMoveSystem() {
    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "YanthraMoveSystem destructor started");

    // CRITICAL FIX: Don't try to reset publishers here
    // They're already reset in shutdownAndCleanup() called from main()
    // Attempting to reset already-null publishers after rclcpp::shutdown() causes Fast-DDS errors
    // The proper cleanup happens in shutdownAndCleanup() while ROS context is still valid
    // Destructor should just verify cleanup was done, not do it again

    if (rclcpp::ok()) {
        // This should NOT happen - shutdownAndCleanup() should have been called from main()
        // But if it didn't, we need to clean up now
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "WARNING: ROS2 still running in destructor - shutdownAndCleanup() not called!");
        shutdown();
    }

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "YanthraMoveSystem destructor finished");
}

// ==============================================
// PUBLIC INTERFACE
// ==============================================

int YanthraMoveSystem::run() {
    try {
        RCLCPP_INFO(node_->get_logger(), "Starting YanthraMoveSystem main operation");

        // Start background executor thread for continuous callback processing
        // All publishers, subscriptions, services, and timers are registered by now
        yanthra_move::utilities::startExecutorThread();

        runMainOperationLoop();

        // Stop executor thread BEFORE any resource cleanup
        yanthra_move::utilities::stopExecutorThread();

        RCLCPP_INFO(node_->get_logger(), "YanthraMoveSystem operation completed successfully");
        return 0;
    } catch (const std::exception& e) {
        // Ensure executor is stopped even on exception
        yanthra_move::utilities::stopExecutorThread();
        RCLCPP_ERROR(node_->get_logger(), "YanthraMoveSystem operation failed: %s", e.what());
        return 1;
    }
}

// ==============================================
// INITIALIZATION METHODS
// ==============================================

void YanthraMoveSystem::initializeROS2(int argc, char** argv) {
    // Initialize ROS2 WITHOUT default signal handlers
    // CRITICAL: We install our own signal handlers in main() that do proper cleanup
    // ROS2's default handlers call rclcpp::shutdown() immediately, preventing clean publisher destruction
    rclcpp::InitOptions init_options;
    init_options.shutdown_on_signal = false;  // Disable automatic shutdown on SIGINT/SIGTERM
    rclcpp::init(argc, argv, init_options);

    // Create node
    node_ = std::make_shared<rclcpp::Node>("yanthra_move");

    // Update global node reference for compatibility with existing code
    yanthra_move::global_node = node_;

    // Executor is managed by startExecutorThread()/stopExecutorThread() in run()
    // No explicit initialization needed — shared_ptr default-constructs to null

    // Declare ALL parameters with defaults - YAML will override these
    declareAllParameters();

    // Use standard ROS2 logging only to avoid conflicts
    RCLCPP_INFO(node_->get_logger(), "=== YANTHRA MOVE SYSTEM STARTUP ===");
    if (std::string(GIT_HASH).empty()) {
        RCLCPP_INFO(node_->get_logger(), "   Built: %s", getBuildTimestamp());
    } else {
        RCLCPP_INFO(node_->get_logger(), "   Built: %s (%s on %s)",
                     getBuildTimestamp(), GIT_HASH, GIT_BRANCH);
    }
    RCLCPP_INFO(node_->get_logger(), "ROS2 node initialized successfully");

    // Log RMW implementation for field diagnostics (Bug 3: service degradation investigation)
    const char* rmw_env = std::getenv("RMW_IMPLEMENTATION");
    RCLCPP_INFO(node_->get_logger(), "🔧 RMW_IMPLEMENTATION env: %s", rmw_env ? rmw_env : "NOT SET (check launch configuration!)");
    const char* localhost_only = std::getenv("ROS_LOCALHOST_ONLY");
    RCLCPP_INFO(node_->get_logger(), "🔧 ROS_LOCALHOST_ONLY: %s", localhost_only ? localhost_only : "NOT SET");

    RCLCPP_INFO(node_->get_logger(), "ROS2 node 'yanthra_move' created successfully");
}


// REMOVED: loadParametersFromYAML()
// ROS2 launch system automatically loads YAML parameters after declaration
// This approach caused "parameter not declared" warnings

void YanthraMoveSystem::initializeSignalHandlers() {
    // Signal handlers are now installed in main() for better control
    // but we can initialize the internal flags here
    global_stop_requested_.store(false);

    RCLCPP_INFO(node_->get_logger(), "Signal handlers installed for graceful shutdown");
    RCLCPP_INFO(node_->get_logger(), "Signal handlers installed");
}

void YanthraMoveSystem::initializeKeyboardMonitoring() {
    // Start ESC key monitoring for emergency stop
    RCLCPP_INFO(node_->get_logger(), "Starting keyboard monitoring for emergency stop");

    // Initialize keyboard monitoring for emergency stop
    // DISABLED (empty stub):     start_keyboard_monitoring();

    RCLCPP_INFO(node_->get_logger(), "Keyboard monitoring initialization completed (bypassed)");
}


void YanthraMoveSystem::initializeTransformSystem() {
    // Initialize TF2 buffer and listener
    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(node_->get_clock());
    tf_listener_ = std::make_unique<tf2_ros::TransformListener>(*tf_buffer_);

    // Initialize transform cache for static TF optimization (Tier 1.3)
    // Convert unique_ptr to shared_ptr for cache (buffer is owned by YanthraMoveSystem)
    std::shared_ptr<tf2_ros::Buffer> buffer_ptr(tf_buffer_.get(), [](tf2_ros::Buffer*){});
    transform_cache_ = std::make_shared<TransformCache>(node_, buffer_ptr);

    RCLCPP_INFO(node_->get_logger(), "TF2 transform system initialized with caching");
}


void YanthraMoveSystem::initializePublishers() {
    // Create joint command publishers for fast motor control
    RCLCPP_INFO(node_->get_logger(), "Creating joint command publishers for fast motor control...");

    // Create joint command publishers for active arm joints (joint2 not in hardware)
    joint3_cmd_pub_ = node_->create_publisher<std_msgs::msg::Float64>("/joint3_position_controller/command", 10);
    joint4_cmd_pub_ = node_->create_publisher<std_msgs::msg::Float64>("/joint4_position_controller/command", 10);
    joint5_cmd_pub_ = node_->create_publisher<std_msgs::msg::Float64>("/joint5_position_controller/command", 10);

    // Connect publishers to joint_move class for fast hardware control
    joint_move::set_joint_publishers(nullptr, joint3_cmd_pub_, joint4_cmd_pub_, joint5_cmd_pub_);

    // Create hardware state publishers for verification compliance
    start_switch_state_pub_ = node_->create_publisher<std_msgs::msg::Bool>("/start_switch/state", 10);
    shutdown_switch_state_pub_ = node_->create_publisher<std_msgs::msg::Bool>("/shutdown_switch/state", 10);

    // Create START_SWITCH topic subscriber (preferred over GPIO)
    start_switch_topic_sub_ = node_->create_subscription<std_msgs::msg::Bool>(
        "/start_switch/command", 10,
        [this](const std_msgs::msg::Bool::SharedPtr msg) {
            if (msg->data) {
                this->start_switch_total_triggers_.fetch_add(1);

                // SAFETY: Ignore START_SWITCH until system is fully initialized
                // This prevents race conditions where stale messages arrive during startup
                if (!this->system_ready_for_start_switch_.load()) {
                    RCLCPP_WARN(this->node_->get_logger(),
                        "⚠️ START_SWITCH IGNORED - system not yet initialized! (trigger #%lu)",
                        this->start_switch_total_triggers_.load());
                    return;  // Discard this message
                }

                // Check if we're currently in a pick cycle
                if (this->cycle_in_progress_.load()) {
                    this->start_switch_ignored_during_cycle_.fetch_add(1);
                    RCLCPP_WARN(this->node_->get_logger(),
                        "⚠️ START_SWITCH ignored (cycle in progress) - trigger #%lu",
                        this->start_switch_total_triggers_.load());
                } else if (this->start_switch_topic_received_.load()) {
                    // Flag already set - this trigger will be coalesced (lost)
                    this->start_switch_coalesced_.fetch_add(1);
                    RCLCPP_WARN(this->node_->get_logger(),
                        "⚠️ START_SWITCH coalesced (flag already set) - trigger #%lu",
                        this->start_switch_total_triggers_.load());
                } else {
                    // This trigger will actually start a cycle
                    this->start_switch_topic_received_.store(true);
                    RCLCPP_INFO(this->node_->get_logger(), "🎯 START_SWITCH command received via topic!");
                    RCLCPP_INFO(this->node_->get_logger(),
                        "[SIGNAL_CHAIN] yanthra_move: Received start_switch command"
                        " | source=/start_switch/command dest=pick_cycle");
                }
            }
        });

    // Create SHUTDOWN_SWITCH topic subscriber (for ARM client MQTT bridge)
    // When shutdown is requested from vehicle, we perform a graceful shutdown sequence:
    // 1. Stop any ongoing pick cycle (global_stop_requested)
    // 2. Exit the operation loop
    // 3. motor_control destructor will park motors safely
    // 4. Then trigger system poweroff
    shutdown_switch_topic_sub_ = node_->create_subscription<std_msgs::msg::Bool>(
        "/shutdown_switch/command", 10,
        [this](const std_msgs::msg::Bool::SharedPtr msg) {
            if (msg->data) {
                RCLCPP_INFO(this->node_->get_logger(),
                    "[SIGNAL_CHAIN] yanthra_move: Received shutdown_switch command"
                    " | source=/shutdown_switch/command dest=shutdown_sequence");
                RCLCPP_WARN(this->node_->get_logger(), " ");
                RCLCPP_WARN(this->node_->get_logger(), "════════════════════════════════════════════════════════════");
                RCLCPP_WARN(this->node_->get_logger(), "🛑 SHUTDOWN COMMAND RECEIVED FROM VEHICLE");
                RCLCPP_WARN(this->node_->get_logger(), "════════════════════════════════════════════════════════════");
                RCLCPP_WARN(this->node_->get_logger(), "Sequence: Stop cycle → Park motors → System poweroff");

                // Set ALL stop flags to exit operation loop and interrupt pick cycle
                // 1. Class member flag (checked by operation loop)
                this->global_stop_requested_.store(true);
                // 2. External global flag (checked by signal handler and motion controller loops)
                global_stop_requested.store(true);
                // 3. Motion controller emergency stop (stops mid-pick operations)
                if (this->motion_controller_) {
                    this->motion_controller_->requestEmergencyStop();
                }

                { std::lock_guard<std::mutex> lock(this->arm_status_mutex_); this->arm_status_ = "shutdown"; }

                // Mark that we should poweroff after cleanup
                this->shutdown_poweroff_requested_.store(true);

                RCLCPP_WARN(this->node_->get_logger(), "✓ All stop flags set - pick cycle will abort immediately");
                RCLCPP_WARN(this->node_->get_logger(), "✓ Motors will park during shutdown sequence");
                RCLCPP_WARN(this->node_->get_logger(), "✓ System poweroff will execute after cleanup");
            }
        });

    // Create timer to publish switch states periodically (simulate hardware)
    switch_state_timer_ = node_->create_wall_timer(
        std::chrono::milliseconds(500),
        std::bind(&YanthraMoveSystem::publishSwitchStates, this));

    // Record system start time for uptime calculation
    system_start_time_ = std::chrono::steady_clock::now();

    // Create periodic stats timer (similar to cotton_detection)
    // Get interval from parameter (declared in declareTimingMotionParameters)
    stats_log_interval_sec_ = node_->get_parameter("stats_log_interval_sec").as_double();
    if (stats_log_interval_sec_ > 0.0) {
        auto interval_ms = static_cast<int>(stats_log_interval_sec_ * 1000);
        stats_timer_ = node_->create_wall_timer(
            std::chrono::milliseconds(interval_ms),
            std::bind(&YanthraMoveSystem::statsLogCallback, this));
        RCLCPP_INFO(node_->get_logger(), "📊 Periodic stats logging enabled (every %.1fs)", stats_log_interval_sec_);
    }

    // EE/Compressor safety watchdog — 1-second polling
    safety_watchdog_timer_ = node_->create_wall_timer(
        std::chrono::seconds(1),
        std::bind(&YanthraMoveSystem::safetyWatchdogCallback, this));
    RCLCPP_INFO(node_->get_logger(),
                "🛡️ Safety watchdog enabled (EE timeout=%.0fs, compressor timeout=%.0fs)",
                ee_watchdog_timeout_sec_, compressor_watchdog_timeout_sec_);

    RCLCPP_INFO(node_->get_logger(), "✅ Joint command publishers and hardware state publishers created");
}


// REMOVED: initializeExecutor() - Let ROS2 launch system handle executor management
// This fixes the ROS2 executor conflict where node was added to executor twice

// ==============================================
// PHASE 2: PARAMETER VALIDATION METHODS
// ==============================================

// PHASE 3: ERROR RECOVERY & RESILIENCE METHODS
// ==============================================


// Template implementation for retry with backoff
template<typename Func>
bool YanthraMoveSystem::retryWithBackoff(Func operation, const std::string& operation_name,
                                        int max_retries, double base_delay) {
    for (int attempt = 1; attempt <= max_retries; ++attempt) {
        RCLCPP_INFO(node_->get_logger(), "🔄 %s attempt %d/%d", operation_name.c_str(), attempt, max_retries);

        try {
            if (operation()) {
                RCLCPP_INFO(node_->get_logger(), "✅ %s successful on attempt %d", operation_name.c_str(), attempt);
                return true;
            }
        } catch (const std::exception& e) {
            RCLCPP_WARN(node_->get_logger(), "⚠️ %s attempt %d failed: %s", operation_name.c_str(), attempt, e.what());
        }

        if (attempt < max_retries) {
            double delay = base_delay * std::pow(2, attempt - 1);  // Exponential backoff
            RCLCPP_INFO(node_->get_logger(), "⏳ Waiting %.1f seconds before retry...", delay);
            // BLOCKING_SLEEP_OK: main-thread exponential backoff in retry loop — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::duration<double>(delay));
        }
    }

    RCLCPP_ERROR(node_->get_logger(), "❌ %s failed after %d attempts", operation_name.c_str(), max_retries);
    return false;
}



void YanthraMoveSystem::initializeModularComponents() {
    RCLCPP_INFO(node_->get_logger(), "🔧 Initializing modular components...");

    // Validate that joint controllers are initialized before creating MotionController
    if (!joint_move_3_ || !joint_move_5_ || !joint_move_4_) {
        RCLCPP_ERROR(node_->get_logger(), "❌ Cannot initialize MotionController: joint controllers not ready");
        throw std::runtime_error("Joint controllers must be initialized before MotionController");
    }

    // Initialize Motion Controller with joint controller pointers
    // This gives MotionController the ability to command motors directly
    motion_controller_ = std::make_unique<core::MotionController>(
        node_,
        joint_move_3_.get(),  // joint3 for phi angle control
        joint_move_5_.get(),  // joint5 for radial extension
        joint_move_4_.get(),  // joint4 for vertical/elevation
        std::shared_ptr<tf2_ros::Buffer>(tf_buffer_.get(), [](tf2_ros::Buffer*){})
    );

    // Get the cotton position provider callback from YanthraMoveSystem
    auto cotton_provider = getCottonPositionProvider();

    // Initialize the motion controller with the provider callback
    // This wires the subscription buffer in YanthraMoveSystem to the MotionController
    if (!motion_controller_->initialize(cotton_provider)) {
        throw std::runtime_error("Failed to initialize Motion Controller");
    }

    // Set detection trigger callback for re-validation after each pick
    // This prevents duplicate cotton picks by refreshing positions after each successful pick
    motion_controller_->setDetectionTriggerCallback(getDetectionTriggerCallback());

    // Wire operational failure callback for centralized error recovery (D3)
    motion_controller_->setOperationalFailureCallback(
        [this](yanthra_move::FailureType type, const yanthra_move::FailureContext& ctx) {
            handleOperationalFailure(type, ctx);
        });
    // Propagate threshold from ROS2 parameter to MotionController
    motion_controller_->setConsecutiveFailureThreshold(consecutive_failure_safe_mode_threshold_);

    // Apply pick cycle timeout (read during loadParameters(), but motion_controller_
    // doesn't exist yet at that point so we apply it here)
    motion_controller_->setPickCycleTimeout(pick_cycle_timeout_sec_);

    RCLCPP_INFO(node_->get_logger(), "✅ Motion Controller initialized with joint controllers and cotton position provider");
    RCLCPP_INFO(node_->get_logger(), "✅ Modular components initialization completed");
}


// ==============================================
// MAIN OPERATION LOOP
// ==============================================


// ==============================================
// SHUTDOWN AND CLEANUP
// ==============================================

void YanthraMoveSystem::shutdownAndCleanup() {
    static std::atomic<bool> cleanup_called{false};
    if (cleanup_called.exchange(true)) {
        return; // Prevent recursive calls
    }

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Starting controlled shutdown sequence...");

    // Set all stop flags immediately
    global_stop_requested_.store(true);
    global_stop_requested.store(true);

    // Check if system poweroff was requested (from vehicle shutdown command)
    bool should_poweroff = shutdown_poweroff_requested_.load();

    // CRITICAL: Clean up all ROS2 resources BEFORE calling rclcpp::shutdown()
    // This ensures publishers/subscriptions are destroyed while context is still valid
    try {
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 1: Cleaning up ROS2 resources");
        shutdown();

        // Now it's safe to shut down ROS2 context
        if (rclcpp::ok()) {
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 2: Shutting down ROS2 context");
            rclcpp::shutdown();
        }
    } catch (const std::exception& e) {
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Exception during shutdown: %s", e.what());
    }

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Shutdown completed");

    // Execute system poweroff if requested from vehicle shutdown command
    if (should_poweroff) {
        // Get shutdown delay from parameter (stored before node cleanup)
        int delay_minutes = shutdown_delay_minutes_;

        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "════════════════════════════════════════════════════════════");
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "SYSTEM POWEROFF SEQUENCE");
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "════════════════════════════════════════════════════════════");

        // CRITICAL: Signal motor_control_node to gracefully shutdown and park motors
        // This triggers its destructor which handles the parking sequence:
        //   J5 → J3(homing) → J4 → J3(parking) → disable all
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 1: Signaling motor_control_node to park motors...");

        // Send SIGTERM specifically to mg6010_controller_node
        // NOTE: We only target motor_control, not all ROS2 nodes, to avoid killing SSH session
        int pkill_ret = std::system("pkill -TERM -f 'mg6010_controller_node'");
        if (pkill_ret == 0) {
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "   SIGTERM sent to motor_control_node");
        } else {
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "   motor_control_node may already be stopped (pkill returned %d)", pkill_ret);
        }

        // Wait for motor parking to complete
        // Parking sequence: J5(2s) + J3(2s) + J4(2s) + J3(2s) = ~8s, plus margin
        const int motor_park_wait_seconds = 12;
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "   Waiting %ds for motors to park...", motor_park_wait_seconds);
        // BLOCKING_SLEEP_OK: main-thread motor parking wait before poweroff; one-time shutdown sequence — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::seconds(motor_park_wait_seconds));
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "   Motor parking wait complete");

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 2: Initiating system poweroff...");

        // Build shutdown command based on delay
        std::string shutdown_cmd;
        if (delay_minutes <= 0) {
            // Immediate shutdown
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Executing: sudo shutdown -h now (immediate)");
            shutdown_cmd = "sudo shutdown -h now";
        } else {
            // Scheduled shutdown (allows cancellation)
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Executing: sudo shutdown -h +%d (in %d minute(s))", delay_minutes, delay_minutes);
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "To cancel: sudo shutdown -c");
            shutdown_cmd = "sudo shutdown -h +" + std::to_string(delay_minutes) + " 'System shutdown requested by vehicle'";
        }

        // Execute system poweroff
        int ret = std::system(shutdown_cmd.c_str());
        if (ret != 0) {
            RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "shutdown command returned %d", ret);
        }
    }
}

void YanthraMoveSystem::shutdown() {
    static std::atomic<bool> shutdown_called{false};
    if (shutdown_called.exchange(true)) {
        return; // Already shutdown, prevent multiple calls
    }

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Starting resource cleanup (not shutting down ROS2 context)...");

    // CRITICAL FIX: Do cleanup EVEN IF rclcpp::ok() is false
    // ROS2's built-in signal handler calls rclcpp::shutdown() automatically
    // before our shutdownAndCleanup() runs, so we must clean up publishers anyway
    // to avoid Fast-DDS errors when they're destroyed after context is invalid
    bool ros_was_running = rclcpp::ok();
    if (!ros_was_running) {
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "ROS2 context already shut down by signal handler - forcing cleanup anyway");
    }

    try {
        // STEP 0: Stop executor thread FIRST — ensures no callbacks are running
        // before we reset any publishers, subscriptions, or shared state.
        // This is idempotent — safe to call even if already stopped by run().
        yanthra_move::utilities::stopExecutorThread();

        // STEP 1: Stop all active operations and threads FIRST
        // This prevents any new operations from starting
        global_stop_requested_.store(true);

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 1: Set stop flags");

        // Clear cached cotton detection positions to prevent execution after shutdown
        {
            std::lock_guard<std::mutex> lock(detection_mutex_);
            latest_detection_.reset();  // Clear cached cotton positions
        }

        // Turn off end effector if running
        if (motion_controller_ && motion_controller_->isEndEffectorEnabled()) {
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Turning off end effector...");
            try {
                motion_controller_->turnOffEndEffector();
            } catch (const std::exception& e) {
                RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Failed to turn off end effector: %s", e.what());
            }
        }

        // Turn off compressor if running (unconditional — not gated on EE enable)
        if (motion_controller_) {
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Turning off compressor...");
            try {
                motion_controller_->turnOffCompressor();
            } catch (const std::exception& e) {
                RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "Failed to turn off compressor: %s", e.what());
            }
        }

        // STEP 1.5: Disable START_SWITCH processing immediately
        system_ready_for_start_switch_.store(false);
        start_switch_topic_received_.store(false);
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "START_SWITCH processing disabled");

        // STEP 2: Stop motion controller (request emergency stop for any ongoing movements)
        // NOTE: Joint homing/parking is handled by motor_control_node's graceful shutdown
        // which includes position verification - we don't duplicate that here
        if (motion_controller_) {
            motion_controller_->requestEmergencyStop();
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 2: Requested motion controller emergency stop");
        }
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Joint parking will be handled by motor_control_node shutdown");

        // STEP 3: Clean up timers (these might trigger callbacks)
        if (switch_state_timer_) {
            switch_state_timer_->cancel();
            switch_state_timer_.reset();
        }
        if (stats_timer_) {
            stats_timer_->cancel();
            stats_timer_.reset();
        }
        if (safety_watchdog_timer_) {
            safety_watchdog_timer_->cancel();
            safety_watchdog_timer_.reset();
        }
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 3: Timers cleaned up");

        // STEP 4: Clean up static publishers in joint_move class FIRST
        // These are the ones causing the static destruction errors
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 4: Cleaning up static joint_move resources...");
        joint_move::cleanup_static_resources();

        // STEP 5: Now it's safe to destroy publishers and services
        // No callbacks should be running at this point
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 5: Cleaning up publishers and services...");

        // Clean up instance publishers
        start_switch_state_pub_.reset();
        shutdown_switch_state_pub_.reset();
        joint2_cmd_pub_.reset();
        joint3_cmd_pub_.reset();
        joint4_cmd_pub_.reset();
        joint5_cmd_pub_.reset();
        parameter_change_pub_.reset();

        // Clean up subscriptions
        start_switch_topic_sub_.reset();
        cotton_detection_sub_.reset();

        // Clean up services
        arm_status_service_.reset();
        joint_homing_action_client_.reset();
        joint_idle_service_.reset();

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 5: Publishers, services, and subscriptions cleaned up");

        // STEP 6: Clean up other ROS2 objects
        tf_listener_.reset();
        tf_buffer_.reset();
        transform_cache_.reset();

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 6: TF system cleaned up");

        // STEP 7: Clean up joint controllers and motion components
        // These may have internal state that references destroyed publishers
        joint_move_2_.reset();
        joint_move_3_.reset();
        joint_move_4_.reset();
        joint_move_5_.reset();
        motion_controller_.reset();

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 7: Joint controllers and motion components cleaned up");

        // STEP 8: Clean up IO interfaces
        problem_indicator_out_.reset();
        start_switch_in_.reset();
        shutdown_switch_in_.reset();

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 8: IO interfaces cleaned up");

        // STEP 9: Clear global references BEFORE clearing local node reference
        // This prevents static destruction issues with global_node
        if (yanthra_move::global_node) {
            yanthra_move::global_node.reset();
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 9: Global node reference cleared");
        }

        // STEP 10: Final cleanup - local node reference
        // Note: Do NOT call rclcpp::shutdown() here - that's done in shutdownAndCleanup()
        if (node_) {
            node_.reset();
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Step 10: Local node reference cleared");
        }

    } catch (const std::exception& e) {
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Exception during resource cleanup: %s", e.what());
    } catch (...) {
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Unknown exception during resource cleanup");
    }

    RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Resource cleanup completed");
}

// ==============================================
// CALLBACK METHODS
// ==============================================


void YanthraMoveSystem::publishSwitchStates() {
    auto start_msg = std_msgs::msg::Bool();
    auto shutdown_msg = std_msgs::msg::Bool();

    // Simulate switch states (in real system, read from GPIO)
    start_msg.data = false;     // Default start switch state
    shutdown_msg.data = false;  // Default shutdown switch state

    start_switch_state_pub_->publish(start_msg);
    shutdown_switch_state_pub_->publish(shutdown_msg);
}

// ==============================================
// EE/COMPRESSOR SAFETY WATCHDOG
// ==============================================
void YanthraMoveSystem::safetyWatchdogCallback() {
    if (!motion_controller_) {
        return;
    }

    auto now = std::chrono::steady_clock::now();

    // --- EE watchdog ---
    if (motion_controller_->isEeCurrentlyOn()) {
        auto ee_on_since = motion_controller_->getEeOnSince();
        double elapsed_sec = std::chrono::duration<double>(now - ee_on_since).count();
        if (elapsed_sec > static_cast<double>(ee_watchdog_timeout_sec_)) {
            // Force EE OFF
            motion_controller_->turnOffEndEffector();
            RCLCPP_ERROR(node_->get_logger(),
                "[EE] Safety watchdog: forced OFF after %.1fs (limit=%.0fs) "
                "| {\"event\":\"ee_watchdog_triggered\",\"elapsed_sec\":%.1f,\"limit_sec\":%.0f}",
                elapsed_sec, ee_watchdog_timeout_sec_, elapsed_sec, ee_watchdog_timeout_sec_);
        }
    }

    // --- Compressor watchdog ---
    if (motion_controller_->isCompressorCurrentlyOn()) {
        auto comp_on_since = motion_controller_->getCompressorOnSince();
        double elapsed_sec = std::chrono::duration<double>(now - comp_on_since).count();
        if (elapsed_sec > static_cast<double>(compressor_watchdog_timeout_sec_)) {
            motion_controller_->turnOffCompressor();
            RCLCPP_ERROR(node_->get_logger(),
                "[EE] Safety watchdog: compressor forced OFF after %.1fs (limit=%.0fs) "
                "| {\"event\":\"compressor_watchdog_triggered\",\"elapsed_sec\":%.1f,\"limit_sec\":%.0f}",
                elapsed_sec, compressor_watchdog_timeout_sec_, elapsed_sec, compressor_watchdog_timeout_sec_);
        }
    }
}

void YanthraMoveSystem::statsLogCallback() {
    // Calculate uptime
    auto now = std::chrono::steady_clock::now();
    auto uptime_sec = std::chrono::duration_cast<std::chrono::seconds>(now - system_start_time_).count();
    int hours = uptime_sec / 3600;
    int mins = (uptime_sec % 3600) / 60;
    int secs = uptime_sec % 60;

    // Get motion controller stats
    int cycle_count = 0;
    int picked_count = 0;
    if (motion_controller_) {
        cycle_count = motion_controller_->getCycleCount();
        picked_count = motion_controller_->getTotalCottonPicked();
    }

    // Get memory usage (current RSS from /proc/self/status)
    size_t memory_mb = 0;
    std::ifstream status("/proc/self/status");
    std::string line;
    while (std::getline(status, line)) {
        if (line.substr(0, 6) == "VmRSS:") {
            size_t kb = 0;
            sscanf(line.c_str(), "VmRSS: %zu kB", &kb);
            memory_mb = kb / 1024;  // Convert KB to MB
            break;
        }
    }

    // Get start switch stats
    uint64_t ss_total = start_switch_total_triggers_.load();
    uint64_t ss_ignored = start_switch_ignored_during_cycle_.load();
    uint64_t ss_coalesced = start_switch_coalesced_.load();
    uint64_t ss_effective = ss_total - ss_ignored - ss_coalesced;  // Triggers that started cycles

    // Get detection stats
    uint64_t det_total = detection_requests_total_.load();
    uint64_t det_success = detection_success_count_.load();
    uint64_t det_stale = detection_stale_filtered_.load();
    uint64_t det_timeout = detection_timeout_count_.load();
    int64_t det_last_age = detection_last_age_ms_.load();

    // Log comprehensive stats
    RCLCPP_INFO(node_->get_logger(), " ");
    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), "📊 YANTHRA_MOVE PERIODIC STATS (uptime: %02d:%02d:%02d)", hours, mins, secs);
    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), "🔄 Cycles completed: %d", cycle_count);
    RCLCPP_INFO(node_->get_logger(), "🧵 Cotton picked: %d", picked_count);
    RCLCPP_INFO(node_->get_logger(), "🎯 Triggers: %lu total | %lu effective | %lu coalesced | %lu during-cycle",
        ss_total, ss_effective, ss_coalesced, ss_ignored);
    RCLCPP_INFO(node_->get_logger(), "🌱 Detection: %lu requests | %lu ok | %lu stale | %lu timeout | last_age=%ld ms",
        det_total, det_success, det_stale, det_timeout, det_last_age);
    std::string current_status;
    { std::lock_guard<std::mutex> lock(arm_status_mutex_); current_status = arm_status_; }
    RCLCPP_INFO(node_->get_logger(), "💾 Memory: %zu MB | Status: %s", memory_mb, current_status.c_str());

    // Service health diagnostic (Bug 3 investigation):
    // Probe service discovery every stats interval (30s) to detect exactly when services degrade.
    // Uses service_is_ready() which is a non-blocking DDS graph check — no actual service call.
    bool motor_svc_ready = false;
    if (motion_controller_ && motion_controller_->getMotorAvailabilityClient()) {
        motor_svc_ready = motion_controller_->getMotorAvailabilityClient()->service_is_ready();
    }
    bool detection_svc_ready = false;
    if (cotton_detection_service_) {
        detection_svc_ready = cotton_detection_service_->service_is_ready();
    }
    RCLCPP_INFO(node_->get_logger(), "🔌 Service health: motor_avail=%s | cotton_detect=%s | executor=%s",
        motor_svc_ready ? "OK" : "UNREACHABLE",
        detection_svc_ready ? "OK" : "UNREACHABLE",
        yanthra_move::executor_running.load() ? "running" : "DEAD");

    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
}

// ==============================================
// COTTON DETECTION ACCESS METHODS
// ==============================================


// ==============================================
// UTILITY METHODS
// ==============================================

double YanthraMoveSystem::getCurrentTimeMillis() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec * 1000.0 + tv.tv_usec / 1000.0;
}

void YanthraMoveSystem::printTimestamp(const std::string& message) {
    // Print timestamp implementation
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    RCLCPP_INFO(node_->get_logger(), "[%ld] %s", time_t, message.c_str());
}

// ==============================================
// INITIALIZATION AND HOMING
// ==============================================



} // namespace yanthra_move

// ==============================================
// MAIN ENTRY POINT
// ==============================================

// Global pointer for signal handling
yanthra_move::YanthraMoveSystem* g_system = nullptr;

// Minimal async-signal-safe signal handler for graceful shutdown (SIGINT, SIGTERM)
void signal_handler(int sig) {
    (void)sig;  // Signal type not used in this handler
    // Only perform async-signal-safe operations here
    static volatile sig_atomic_t signal_count = 0;

    signal_count++;

    if (signal_count > 1) {
        // Second signal - write to stderr and force exit
        const char msg[] = "\n⚡ Second signal received - forcing immediate exit!\n";
        [[maybe_unused]] auto result = write(STDERR_FILENO, msg, sizeof(msg) - 1);
        std::_Exit(1);
    }

    // First signal - just set the flag and let main() handle shutdown
    global_stop_requested.store(true, std::memory_order_release);

    // Write message using async-signal-safe write()
    const char msg[] = "\n🛑 Signal received - initiating clean shutdown...\n";
    [[maybe_unused]] auto result = write(STDERR_FILENO, msg, sizeof(msg) - 1);
}

// Crash signal handler for SIGSEGV and SIGABRT — best-effort GPIO cleanup.
// Uses pigs (pigpio daemon client) to turn off all motor/pneumatic GPIO pins,
// since the process memory may be corrupted and calling library functions is unsafe.
// After cleanup attempt, re-raises the signal with default disposition for core dump.
void crash_signal_handler(int sig) {
    // Write crash message (async-signal-safe)
    const char msg[] = "\n💥 CRASH: Attempting emergency GPIO cleanup before abort...\n";
    [[maybe_unused]] auto result = write(STDERR_FILENO, msg, sizeof(msg) - 1);

    // Best-effort: fork a child to run pigs commands for GPIO cleanup.
    // fork() is not strictly async-signal-safe per POSIX, but works reliably
    // on Linux in single-threaded-at-signal contexts. This is a last resort.
    pid_t pid = fork();
    if (pid == 0) {
        // Child process — exec pigs to clear all 6 motor/pneumatic GPIO pins.
        // BCM 18 (compressor), 24 (vacuum), 21 (EE enable), 12 (EE drop),
        // 13 (EE direction), 20 (EE drop direction)
        // Using sh -c to run multiple pigs commands in sequence.
        execl("/bin/sh", "sh", "-c",
              "pigs w 18 0; pigs w 24 0; pigs w 21 0; pigs w 12 0; pigs w 13 0; pigs w 20 0",
              nullptr);
        // If exec fails, just exit the child
        std::_Exit(1);
    } else if (pid > 0) {
        // Parent: wait briefly for child to complete (100ms max)
        // Using a simple spin-wait since waitpid with WNOHANG is async-signal-safe
        for (int i = 0; i < 100; ++i) {
            int status;
            pid_t ret = waitpid(pid, &status, WNOHANG);
            if (ret == pid || ret == -1) break;
            usleep(1000);  // BLOCKING_SLEEP_OK: signal handler crash path; no executor available — reviewed 2026-03-14
        }
    }

    const char done_msg[] = "💥 GPIO cleanup attempted. Re-raising signal for core dump.\n";
    [[maybe_unused]] auto result2 = write(STDERR_FILENO, done_msg, sizeof(done_msg) - 1);

    // Restore default handler and re-raise to get proper core dump / termination
    std::signal(sig, SIG_DFL);
    raise(sig);
}

int main(int argc, char** argv) {
    try {
        // NOTE: ROS2 not yet initialized — use fprintf for pre-init messages
        fprintf(stderr, "=== YANTHRA ROBOTIC ARM SYSTEM ===\n");
        fprintf(stderr, "Starting modular robotic arm system...\n");

        // Install signal handlers BEFORE initializing ROS2
        std::signal(SIGINT, signal_handler);
        std::signal(SIGTERM, signal_handler);
        std::signal(SIGSEGV, crash_signal_handler);
        std::signal(SIGABRT, crash_signal_handler);

        // Create and initialize the system
        yanthra_move::YanthraMoveSystem system(argc, argv);
        g_system = &system;

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Yanthra Move System initialized successfully");
        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Starting robotic arm operations...");

        // Run the main operation (this will check global_stop_requested periodically)
        int result = system.run();

        // Check if we were interrupted by signal
        if (global_stop_requested.load(std::memory_order_acquire)) {
            RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Shutdown requested by signal");
        }

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "Operations completed with result: %d", result);

        // CRITICAL: Clean up all ROS2 resources BEFORE rclcpp::shutdown()
        // This is the proper shutdown order that prevents core dumps
        system.shutdownAndCleanup();

        RCLCPP_INFO(rclcpp::get_logger("yanthra_move"), "System shutdown completed successfully");
        return result;

    } catch (const std::exception& e) {
        RCLCPP_ERROR(rclcpp::get_logger("yanthra_move"), "System failed: %s", e.what());

        // Ensure ROS2 is shut down even on exception
        if (rclcpp::ok()) {
            rclcpp::shutdown();
        }

        return 1;
    }
}
