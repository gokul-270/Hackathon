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

#include "yanthra_move/core/motion_controller.hpp"
#include "yanthra_move/core/recovery_manager.hpp"
#include "yanthra_move/core/trajectory_planner.hpp"
#include "yanthra_move/core/capture_sequence.hpp"
#include "yanthra_move/core/trajectory_executor.hpp"
#include "yanthra_move/core/aruco_coordinator.hpp"
#include "yanthra_move/core/planned_trajectory.hpp"
#include "yanthra_move/cotton_picking_optimizer.hpp"
#include "yanthra_move/yanthra_utilities.hpp"
#include "yanthra_move/coordinate_transforms.hpp"  // Include before joint_move.h to avoid NO_ERROR conflict
#include "yanthra_move/joint_move.h"
#include "yanthra_move/error_recovery_types.hpp"  // FailureType, FailureContext for recordMoveResult()
// GPIO control for end effector and compressor
// NOTE: We always compile against the motor_control_ros2 GPIO abstraction.
// It handles hardware-vs-simulation internally (based on whether pigpiod_if2 is available
// and whether pigpiod is running).
#include "motor_control_ros2/gpio_control_functions.hpp"
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2_ros/buffer.h>
#include <tf2/exceptions.h>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <future>
#include <sys/time.h>
#include <chrono>
#include <thread>
#include <cmath>
#include <fstream>
#include <sstream>
#include <numeric>  // for std::iota
#include <algorithm>  // for std::sort, std::greater
#include <nlohmann/json.hpp>
#include <common_utils/json_logging.hpp>

// Forward declaration to access simulation_mode from yanthra_move namespace
namespace yanthra_move {
    extern std::atomic<bool> simulation_mode;
}

// REMOVED: extern get_cotton_coordinates() - now using provider callback from YanthraMoveSystem
// Cotton positions come from ROS2 topic /cotton_detection/results via dependency injection

namespace yanthra_move { namespace core {

MotionController::MotionController(std::shared_ptr<rclcpp::Node> node,
                                   joint_move* joint3,
                                   joint_move* joint5,
                                   joint_move* joint4,
                                   std::shared_ptr<tf2_ros::Buffer> tf_buffer)
    : node_(node), tf_buffer_(tf_buffer), joint_move_3_(joint3), joint_move_5_(joint5), joint_move_4_(joint4) {

    recovery_manager_ = std::make_unique<RecoveryManager>(node_->get_logger());
    trajectory_planner_ = std::make_unique<TrajectoryPlanner>(tf_buffer_, node_->get_logger());

    if (!joint_move_3_ || !joint_move_4_ || !joint_move_5_) {
        RCLCPP_ERROR(node_->get_logger(), "❌ MotionController initialized with NULL joint pointers!");
        throw std::runtime_error("Joint move pointers cannot be null");
    }

    // Initialize GPIO control for end effector and compressor
    // NOTE: GPIO availability is runtime-dependent (pigpiod present/running, permissions, etc.).
    // Never hard-disable end_effector_enable_ here; keep it driven by parameters.
    try {
        gpio_control_ = std::make_shared<motor_control_ros2::GPIOControlFunctions>(node_->get_logger());
        if (gpio_control_ && gpio_control_->initialize()) {
            RCLCPP_INFO(node_->get_logger(), "[EE] ✅ GPIO control initialized successfully");
        } else {
            gpio_degraded_ = true;
            RCLCPP_WARN(node_->get_logger(),
                "{\"event\":\"gpio_init_failure\","
                "\"degraded\":true,"
                "\"error\":\"%s\"}",
                gpio_control_ ? gpio_control_->get_last_error().c_str() : "no instance");
            gpio_control_ = nullptr;
        }
    } catch (const std::exception& e) {
        gpio_degraded_ = true;
        RCLCPP_ERROR(node_->get_logger(),
            "{\"event\":\"gpio_init_failure\","
            "\"degraded\":true,"
            "\"error\":\"%s\"}", e.what());
        gpio_control_ = nullptr;
    }

    // Create CaptureSequence after GPIO is initialized so it gets the valid (or null) pointer
    capture_sequence_ = std::make_unique<CaptureSequence>(gpio_control_, node_->get_logger());

    // Create TrajectoryExecutor with joint motor handles
    trajectory_executor_ = std::make_unique<TrajectoryExecutor>(
        joint_move_3_, joint_move_4_, joint_move_5_, node_->get_logger());
    trajectory_executor_->setRecoveryManager(recovery_manager_.get());
    trajectory_executor_->setCaptureSequence(capture_sequence_.get());

    // Create ArucoCoordinator for ArUco detection and multi-position scanning
    aruco_coordinator_ = std::make_unique<ArucoCoordinator>(node_->get_logger());

    // Subscribe to /joint_states for position-based EE timing
    // This subscription persists for the lifetime of MotionController
    joint_states_sub_ = node_->create_subscription<sensor_msgs::msg::JointState>(
        "/joint_states", 10,
        [this](const sensor_msgs::msg::JointState::SharedPtr msg) {
            std::lock_guard<std::mutex> lock(joint_state_mutex_);
            for (size_t i = 0; i < msg->name.size() && i < msg->position.size(); ++i) {
                latest_joint_positions_[msg->name[i]] = msg->position[i];
            }
            last_joint_state_time_ = msg->header.stamp;

            // Forward positions to joint_move instances for feedback-based waiting
            if (joint_move_3_) {
                auto it = latest_joint_positions_.find("joint3");
                if (it != latest_joint_positions_.end()) {
                    joint_move_3_->updatePosition(it->second);
                }
            }
            if (joint_move_4_) {
                auto it = latest_joint_positions_.find("joint4");
                if (it != latest_joint_positions_.end()) {
                    joint_move_4_->updatePosition(it->second);
                }
            }
            if (joint_move_5_) {
                auto it = latest_joint_positions_.find("joint5");
                if (it != latest_joint_positions_.end()) {
                    joint_move_5_->updatePosition(it->second);
                }
            }
        });
    RCLCPP_INFO(node_->get_logger(), "📍 Subscribed to /joint_states for position-based EE timing");

    RCLCPP_INFO(node_->get_logger(), "✅ Motion Controller initialized with joint3, joint4, and joint5 controllers");
}

MotionController::~MotionController() = default;

bool MotionController::initialize(
    std::function<std::optional<std::vector<CottonDetection>>()> provider) {

    if (initialized_) {
        RCLCPP_WARN(node_->get_logger(), "Motion Controller already initialized");
        return true;
    }

    // Store the provider callback for cotton positions
    cotton_position_provider_ = provider;

    if (!cotton_position_provider_) {
        RCLCPP_ERROR(node_->get_logger(), "Cotton position provider not set!");
        return false;
    }

    // Load motion parameters from ROS2 parameter server
    loadMotionParameters();

    // Load joint limits from motor_control node parameters (CRITICAL for safety)
    if (!loadJointLimits()) {
        RCLCPP_ERROR(node_->get_logger(), "❌ CRITICAL: Failed to load joint limits from motor_control node!");
        RCLCPP_ERROR(node_->get_logger(), "   Motion controller CANNOT operate safely without proper limits.");
        return false;
    }

    // Set per-joint position tolerances from motor_control (single source of truth)
    if (joint_move_3_) joint_move_3_->position_tolerance_ = joint3_position_tolerance_;
    if (joint_move_4_) joint_move_4_->position_tolerance_ = joint4_position_tolerance_;
    if (joint_move_5_) joint_move_5_->position_tolerance_ = joint5_position_tolerance_;
    RCLCPP_INFO(node_->get_logger(), "Position tolerances set from motor_control: J3=%.4f, J4=%.4f, J5=%.4f",
        joint3_position_tolerance_, joint4_position_tolerance_, joint5_position_tolerance_);

    // Load calibration mode flag
    if (node_->has_parameter("YanthraLabCalibrationTesting")) {
        yanthra_lab_calibration_testing_ = node_->get_parameter("YanthraLabCalibrationTesting").as_bool();
        if (yanthra_lab_calibration_testing_) {
            RCLCPP_INFO(node_->get_logger(), "🎯 ArUco calibration mode ENABLED");
        }
    }

    // Load preloaded centroids flag
    if (node_->has_parameter("use_preloaded_centroids")) {
        use_preloaded_centroids_ = node_->get_parameter("use_preloaded_centroids").as_bool();
        if (use_preloaded_centroids_) {
            RCLCPP_INFO(node_->get_logger(), "📂 Preloaded centroids mode ENABLED - will load from centroid.txt");
        }
    }

    // Load detection re-triggering flag (disabled by default - can cause deadlock)
    if (node_->has_parameter("enable_detection_retrigger")) {
        enable_detection_retrigger_ = node_->get_parameter("enable_detection_retrigger").as_bool();
        if (enable_detection_retrigger_) {
            RCLCPP_WARN(node_->get_logger(), "🔄 Detection re-triggering ENABLED - may cause hangs if detection times out");
        }
    }

    // Load post-cycle parking flag (disabled by default - retreat already homes)
    if (node_->has_parameter("enable_post_cycle_parking")) {
        enable_post_cycle_parking_ = node_->get_parameter("enable_post_cycle_parking").as_bool();
        if (enable_post_cycle_parking_) {
            RCLCPP_INFO(node_->get_logger(), "🏠 Post-cycle parking ENABLED");
        }
    }

    // Load position wait mode (replaces enable_position_feedback bool)
    if (node_->has_parameter("position_wait_mode")) {
        position_wait_mode_ = node_->get_parameter("position_wait_mode").as_string();
        RCLCPP_INFO(node_->get_logger(), "📍 Position wait mode: '%s'", position_wait_mode_.c_str());
        if (position_wait_mode_ == "service") {
            RCLCPP_INFO(node_->get_logger(), "   → Using JointPositionCommand service (motor-confirmed arrival, no echo bug)");
        } else if (position_wait_mode_ == "feedback") {
            RCLCPP_WARN(node_->get_logger(), "   → Using /joint_states polling (WARNING: has echo bug, may report false arrivals)");
        } else if (position_wait_mode_ == "blind_sleep") {
            RCLCPP_INFO(node_->get_logger(), "   → Using blind sleep (distance-based estimate, reliable fallback)");
        } else {
            RCLCPP_WARN(node_->get_logger(), "   → Unknown mode '%s', defaulting to blind_sleep", position_wait_mode_.c_str());
            position_wait_mode_ = "blind_sleep";
        }
    }

    // Load L3 idle parking optimization flag (reduces motor temperature during idle)
    if (node_->has_parameter("enable_l3_idle_parking")) {
        enable_l3_idle_parking_ = node_->get_parameter("enable_l3_idle_parking").as_bool();
        if (enable_l3_idle_parking_) {
            RCLCPP_INFO(node_->get_logger(), "🌡️  L3 idle parking ENABLED - L3 will park (tilt up) when idle to reduce motor heat");
            RCLCPP_INFO(node_->get_logger(), "    Parking position: %.4f rotations, Homing position: %.4f rotations",
                        joint3_parking_position_, joint3_init_.homing_position);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // LOAD PHI COMPENSATION PARAMETERS → TrajectoryPlanner
    // ═══════════════════════════════════════════════════════════════════════════
    {
        PhiCompensationParams phi_params;
        phi_params.enabled = loadParamBool("phi_compensation/enable", false);
        if (phi_params.enabled) {
            phi_params.zone1_max_deg = loadParamDouble("phi_compensation/zone1_max_deg", 30.0);
            phi_params.zone2_max_deg = loadParamDouble("phi_compensation/zone2_max_deg", 60.0);
            phi_params.zone1_slope = loadParamDouble("phi_compensation/zone1_slope", 0.0);
            phi_params.zone1_offset = loadParamDouble("phi_compensation/zone1_offset", 0.0);
            phi_params.zone2_slope = loadParamDouble("phi_compensation/zone2_slope", 0.0);
            phi_params.zone2_offset = loadParamDouble("phi_compensation/zone2_offset", 0.0);
            phi_params.zone3_slope = loadParamDouble("phi_compensation/zone3_slope", 0.0);
            phi_params.zone3_offset = loadParamDouble("phi_compensation/zone3_offset", 0.0);
            phi_params.l5_scale = loadParamDouble("phi_compensation/l5_scale", 0.5);

            RCLCPP_INFO(node_->get_logger(), "🔧 PHI COMPENSATION ENABLED");
            RCLCPP_INFO(node_->get_logger(), "    Zone 1 (0-%.0f°): slope=%.4f, offset=%.4f rot",
                        phi_params.zone1_max_deg, phi_params.zone1_slope, phi_params.zone1_offset);
            RCLCPP_INFO(node_->get_logger(), "    Zone 2 (%.0f-%.0f°): slope=%.4f, offset=%.4f rot",
                        phi_params.zone1_max_deg, phi_params.zone2_max_deg, phi_params.zone2_slope, phi_params.zone2_offset);
            RCLCPP_INFO(node_->get_logger(), "    Zone 3 (%.0f-90°): slope=%.4f, offset=%.4f rot",
                        phi_params.zone2_max_deg, phi_params.zone3_slope, phi_params.zone3_offset);
            RCLCPP_INFO(node_->get_logger(), "    L5 scale factor: %.2f", phi_params.l5_scale);
        }
        trajectory_planner_->setPhiCompensation(phi_params);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // WIRE ARUCO COORDINATOR CALLBACKS
    // ═══════════════════════════════════════════════════════════════════════════
    aruco_coordinator_->setReTriggerEnabled(enable_detection_retrigger_);

    // Camera availability check: delegates to node graph inspection
    aruco_coordinator_->setCameraCheckCallback([this]() -> bool {
        auto node_names = node_->get_node_names();
        for (const auto& name : node_names) {
            if (name.find("cotton_detection") != std::string::npos) return true;
            if (name.find("aruco_finder") != std::string::npos) return true;
        }
        if (access(ARUCO_FINDER_PROGRAM, X_OK) == 0) return true;
        return false;
    });

    // ArUco detection: invoke external aruco_finder binary and parse centroid.txt
    aruco_coordinator_->setDetectionCallback(
        [this]() -> std::optional<std::vector<CottonDetection>> {
            RCLCPP_INFO(node_->get_logger(),
                "🎯 Calling %s for marker detection...", ARUCO_FINDER_PROGRAM);
            std::string cmd = std::string(ARUCO_FINDER_PROGRAM) + " --debug-images";
            FILE* pipe = popen(cmd.c_str(), "r");
            if (!pipe) {
                RCLCPP_ERROR(node_->get_logger(),
                    "❌ Failed to execute aruco_finder");
                return std::nullopt;
            }
            // Read and discard stdout (aruco_finder writes to centroid.txt, not stdout)
            char buffer[256];
            while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {}
            int status = pclose(pipe);
            int result = WEXITSTATUS(status);
            if (result != 0) {
                RCLCPP_ERROR(node_->get_logger(),
                    "❌ ArUco finder failed with exit code: %d", result);
                return std::nullopt;
            }
            std::ifstream centroid_file("centroid.txt");
            if (!centroid_file.is_open()) {
                RCLCPP_ERROR(node_->get_logger(),
                    "❌ Failed to open centroid.txt - ArUco detection may have failed");
                return std::nullopt;
            }
            std::vector<CottonDetection> detections;
            double x, y, z;
            int corner_count = 0;
            while (centroid_file >> x >> y >> z) {
                CottonDetection det;
                det.position.x = x;
                det.position.y = y;
                det.position.z = z;
                det.confidence = 1.0f;
                det.detection_id = corner_count;
                det.detection_time = std::chrono::steady_clock::now();
                detections.push_back(det);
                corner_count++;
                RCLCPP_INFO(node_->get_logger(),
                    "   Corner %d: [%.3f, %.3f, %.3f] meters",
                    corner_count, x, y, z);
            }
            centroid_file.close();
            if (detections.empty()) {
                RCLCPP_WARN(node_->get_logger(),
                    "⚠️  centroid.txt was empty - no marker corners detected");
                return std::nullopt;
            }
            RCLCPP_INFO(node_->get_logger(),
                "✅ Successfully read %d marker corners from centroid.txt",
                corner_count);
            return detections;
        });

    // J4 move callback for multi-position scanning
    aruco_coordinator_->setJ4MoveCallback(
        [this](double position) -> MoveResult {
            if (!joint_move_4_) return MoveResult::ERROR;
            auto result = joint_move_4_->move_joint(position, true);
            recordMoveResult(4, result);
            return result;
        });

    initialized_ = true;
    operation_start_time_ = getCurrentTimeMillis();

    // If L3 idle parking enabled, move L3 to parking position after init
    // (motors already homed to operational positions, now park L3 for idle)
    if (enable_l3_idle_parking_ && areMotorsAvailable()) {
        RCLCPP_INFO(node_->get_logger(), "🌡️  Moving L3 to parking position for idle temperature reduction...");
        moveL3ToParking();
    }

    RCLCPP_INFO(node_->get_logger(), "Motion Controller initialized successfully with position provider");
    return true;
}

bool MotionController::executeOperationalCycle() {
    if (!initialized_) {
        RCLCPP_ERROR(node_->get_logger(), "Motion Controller not initialized");
        return false;
    }

    cycle_count_++;
    recovery_manager_->setCycleCount(cycle_count_.load());
    double cycle_start_time = getCurrentTimeMillis();
    bool motion_occurred = false;  // Track if any actual motion happened this cycle

    RCLCPP_INFO(node_->get_logger(), "🔄 Starting operational cycle #%d", cycle_count_.load());

    // Check if in ArUco calibration mode
    if (yanthra_lab_calibration_testing_) {
        std::vector<CottonDetection> aruco_positions;

        // Reset coordinator detection state at start of each cycle
        aruco_coordinator_->resetDetectionState();

        // Check if using preloaded centroids or running ArUco detection
        if (use_preloaded_centroids_) {
            RCLCPP_INFO(node_->get_logger(), "📂 Loading preloaded centroids from centroid.txt...");

            // Try multiple paths to find centroid.txt
            std::vector<std::string> search_paths = {
                "centroid.txt",
                "./centroid.txt",
            };
            if (node_->has_parameter("PRAGATI_INSTALL_DIR")) {
                try {
                    std::string install_dir = node_->get_parameter("PRAGATI_INSTALL_DIR").as_string();
                    search_paths.push_back(install_dir + "/centroid.txt");
                } catch (const std::exception& e) {
                    RCLCPP_ERROR(node_->get_logger(),
                        "{\"event\":\"parameter_read_failure\","
                        "\"parameter\":\"PRAGATI_INSTALL_DIR\","
                        "\"error\":\"%s\"}", e.what());
                }
            }
            search_paths.push_back(std::string(getenv("HOME") ? getenv("HOME") : ".") + "/pragati_ros2/centroid.txt");

            // Try each path via coordinator
            bool loaded = false;
            for (const auto& path : search_paths) {
                auto result = aruco_coordinator_->loadPreloadedCentroids(path);
                if (result.has_value()) {
                    aruco_positions = std::move(*result);
                    RCLCPP_INFO(node_->get_logger(), "✅ Successfully loaded %zu positions from %s",
                                aruco_positions.size(), path.c_str());
                    loaded = true;
                    break;
                }
            }

            if (!loaded) {
                RCLCPP_ERROR(node_->get_logger(), "❌ Failed to open centroid.txt - file not found in any search path");
                for (const auto& path : search_paths) {
                    RCLCPP_ERROR(node_->get_logger(), "   Searched: %s", path.c_str());
                }
                // In simulation mode: don't kill the node, just skip this cycle
                // The user can write centroid.txt via the web UI and re-trigger
                if (yanthra_move::simulation_mode) {
                    RCLCPP_WARN(node_->get_logger(),
                        "⚠️  [SIM] centroid.txt not found - completing cycle with no picks.");
                    RCLCPP_WARN(node_->get_logger(),
                        "   💡 Use the Web UI: set camera coords → click 'Write Centroid' → click 'Trigger Start'");
                    return true;  // Empty cycle, node stays alive for next trigger
                }
                return false;
            }

            if (aruco_positions.empty()) {
                RCLCPP_WARN(node_->get_logger(), "⚠️  centroid.txt was empty - no positions to visit");
                return true;
            }
        } else {
            // Live ArUco detection path — delegated to coordinator
            if (!aruco_coordinator_->isCameraAvailable()) {
                RCLCPP_ERROR(node_->get_logger(), "❌ ArUco calibration requires camera!");
                RCLCPP_ERROR(node_->get_logger(), "   Camera not detected or cotton_detection node not running");
                RCLCPP_ERROR(node_->get_logger(), "   Please:");
                RCLCPP_ERROR(node_->get_logger(), "     1. Check camera USB connection");
                RCLCPP_ERROR(node_->get_logger(), "     2. Verify cotton_detection node is running");
                RCLCPP_ERROR(node_->get_logger(), "     3. Or set YanthraLabCalibrationTesting: false");
                RCLCPP_ERROR(node_->get_logger(), "   System cannot proceed without camera in calibration mode");
                return false;
            }

            RCLCPP_INFO(node_->get_logger(), "🎯 Running ArUco marker detection for calibration...");

            auto aruco_points = aruco_coordinator_->executeArucoDetection();

            if (aruco_points.empty()) {
                RCLCPP_WARN(node_->get_logger(), "❌ ArUco detection failed - no markers found");
                RCLCPP_INFO(node_->get_logger(), "   Arm already at safe position - skipping parking move");
                return true;
            }

            // Convert ArUco points to CottonDetection structs
            for (size_t idx = 0; idx < aruco_points.size(); ++idx) {
                CottonDetection det;
                det.position = aruco_points[idx];
                det.confidence = 1.0f;
                det.detection_id = static_cast<int>(idx);
                det.detection_time = std::chrono::steady_clock::now();
                aruco_positions.push_back(det);
            }

            RCLCPP_INFO(node_->get_logger(), "✅ ArUco marker detected with %zu corner positions",
                        aruco_positions.size());
        }

        // ═══════════════════════════════════════════════════════════════════════════
        // MULTI-POSITION J4 SCANNING (when enabled)
        // Move J4 to each configured scan position, pick centroids at each
        // ═══════════════════════════════════════════════════════════════════════════
        int picked_count = 0;

        if (j4_multipos_config_.enabled && areMotorsAvailable() && joint_move_4_) {
            // Determine scan order
            std::vector<double> scan_order = j4_multipos_config_.positions;
            if (j4_multipos_config_.scan_strategy == "left_to_right") {
                std::sort(scan_order.begin(), scan_order.end());
            } else if (j4_multipos_config_.scan_strategy == "right_to_left") {
                std::sort(scan_order.begin(), scan_order.end(), std::greater<double>());
            }

            RCLCPP_INFO(node_->get_logger(), " ");
            RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
            RCLCPP_INFO(node_->get_logger(), "🔄 MULTI-POSITION J4 SCANNING MODE (%zu positions)", scan_order.size());
            RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
            for (size_t i = 0; i < scan_order.size(); ++i) {
                RCLCPP_INFO(node_->get_logger(), "   Position %zu: %+.3fm (%+.0fmm)",
                           i + 1, scan_order[i], scan_order[i] * 1000.0);
            }
            RCLCPP_INFO(node_->get_logger(), " ");

            for (size_t pos_idx = 0; pos_idx < scan_order.size(); ++pos_idx) {
                const double j4_position = joint4_init_.homing_position + scan_order[pos_idx];

                RCLCPP_INFO(node_->get_logger(), "────────────────────────────────────────────────────────────────────────");
                RCLCPP_INFO(node_->get_logger(), "🔍 Scan %zu/%zu: Moving J4 to %+.3fm (%+.0fmm offset)",
                            pos_idx + 1, scan_order.size(), j4_position, scan_order[pos_idx] * 1000.0);

                // Move J4 to scan position
                auto result = joint_move_4_->move_joint(j4_position, true);
                if (result != MoveResult::SUCCESS) {
                    RCLCPP_WARN(node_->get_logger(),
                        "[MOVE] Joint 4 move failed (result=%d, target=%.4f)",
                        static_cast<int>(result), j4_position);
                }
                recordMoveResult(4, result);

                // Settling time
                double settle_ms = j4_multipos_config_.detection_settling_time * 1000.0;
                if (settle_ms > 0) {
                    // BLOCKING_SLEEP_OK: main-thread camera settling delay — reviewed 2026-03-14
                    std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(settle_ms)));
                }

                RCLCPP_INFO(node_->get_logger(), "🎯 Picking %zu positions at J4=%+.3fm (J4 locked at scan position)",
                           aruco_positions.size(), j4_position);

                // CRITICAL: Tell approach trajectory to SKIP J4 command
                // J4 is already at the scan position, don't let TF override it
                skip_j4_in_approach_ = true;

                // Pick all centroid positions at this J4 offset
                bool is_last = (pos_idx == scan_order.size() - 1);
                int picked_here = executeCottonPickingSequence(aruco_positions, /*home_j5=*/true, /*home_j3=*/true, /*home_j4=*/is_last);

                skip_j4_in_approach_ = false;  // Reset after picking
                picked_count += picked_here;

                RCLCPP_INFO(node_->get_logger(), "✅ Picked %d/%zu at J4=%+.0fmm",
                           picked_here, aruco_positions.size(), scan_order[pos_idx] * 1000.0);
            }

            RCLCPP_INFO(node_->get_logger(), "────────────────────────────────────────────────────────────────────────");
            RCLCPP_INFO(node_->get_logger(), "🏁 Multi-position scan complete: %d total picks across %zu J4 positions",
                       picked_count, scan_order.size());
        } else {
            // Single-position mode (j4_multiposition disabled)
            picked_count = executeCottonPickingSequence(aruco_positions);
            RCLCPP_INFO(node_->get_logger(), "Visited %d/%zu ArUco marker corners",
                        picked_count, aruco_positions.size());
        }

        // Only park if we actually moved
        if (picked_count > 0) {
            (void)moveToPackingPosition();  // Best-effort end-of-ArUco homing
        } else {
            RCLCPP_INFO(node_->get_logger(), "⏩ Skipping parking - no motion occurred (all picks failed planning)");
        }
        return true;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOINT4 MULTI-POSITION SCANNING MODE
    // ═══════════════════════════════════════════════════════════════════════════
    // Scan multiple J4 (left/right) positions to increase camera FOV coverage.
    // At each J4 position: trigger detection, get cotton list, pick all visible.
    // This recovers border cottons that fall outside single-position FOV.
    // ═══════════════════════════════════════════════════════════════════════════
    int picked_count = 0;  // Track picks for stats report
    int total_cotton_detected = 0;  // Track total detections across all positions
    bool use_multiposition = j4_multipos_config_.enabled;  // Local flag for this cycle

    if (use_multiposition) {
        RCLCPP_INFO(node_->get_logger(), " ");
        RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
        RCLCPP_INFO(node_->get_logger(), "🔄 MULTI-POSITION SCANNING MODE");
        RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
        RCLCPP_INFO(node_->get_logger(), "📍 Scanning %zu J4 positions (strategy: %s)",
                    j4_multipos_config_.positions.size(), j4_multipos_config_.scan_strategy.c_str());
        RCLCPP_INFO(node_->get_logger(), "🎯 Strategy: Move J4, trigger detection, pick all visible cotton at each position");
        RCLCPP_INFO(node_->get_logger(), " ");

        ++multipos_stats_.total_scans;

        // Check if detection trigger callback is available
        if (!detection_trigger_callback_) {
            RCLCPP_ERROR(node_->get_logger(), "❌ Multi-position mode requires detection trigger callback!");
            RCLCPP_ERROR(node_->get_logger(), "   Callback not set - cannot trigger fresh detections at each J4 position");
            RCLCPP_ERROR(node_->get_logger(), "   Falling back to single-position mode for this cycle");
            use_multiposition = false;  // Disable for this cycle only
            // Fall through to single-position mode below
        } else {
            // ═══════════════════════════════════════════════════════════════════════════
            // DETERMINE SCAN ORDER BASED ON STRATEGY
            // ═══════════════════════════════════════════════════════════════════════════
            std::vector<double> scan_order = j4_multipos_config_.positions;

            if (j4_multipos_config_.scan_strategy == "left_to_right") {
                // Ensure positions are sorted ascending (left to right)
                std::sort(scan_order.begin(), scan_order.end());
                RCLCPP_INFO(node_->get_logger(), "↪️  Sweep: Left → Right (ascending positions)");
            } else if (j4_multipos_config_.scan_strategy == "right_to_left") {
                // Sort descending (right to left)
                std::sort(scan_order.begin(), scan_order.end(), std::greater<double>());
                RCLCPP_INFO(node_->get_logger(), "↩️  Sweep: Right → Left (descending positions)");
            } else {
                // "as_configured" - use positions exactly as written in config
                RCLCPP_INFO(node_->get_logger(), "📋 Custom order: As configured in YAML");
            }

            // Log the scan order
            RCLCPP_INFO(node_->get_logger(), "📊 Scan order:");
            for (size_t i = 0; i < scan_order.size(); ++i) {
                RCLCPP_INFO(node_->get_logger(), "   %zu. %+.3fm (%+.0fmm)",
                           i + 1, scan_order[i], scan_order[i] * 1000.0);
            }
            RCLCPP_INFO(node_->get_logger(), " ");

            // Iterate through J4 positions in determined scan order
            for (size_t pos_idx = 0; pos_idx < scan_order.size(); ++pos_idx) {
                const double j4_offset = scan_order[pos_idx];
                const double j4_absolute = joint4_init_.homing_position + j4_offset;

                // Track current J4 scan offset for theta correction during picking
                current_j4_scan_offset_ = j4_offset;

                RCLCPP_INFO(node_->get_logger(), "────────────────────────────────────────────────────────────────────────");
                RCLCPP_INFO(node_->get_logger(), "🔍 Position %zu/%zu: J4 = %+.3fm (%+.0fmm offset from home)",
                            pos_idx + 1, scan_order.size(),
                            j4_absolute, j4_offset * 1000.0);

                // Validate J4 position against safety limits
                if (j4_absolute < j4_multipos_config_.safe_min || j4_absolute > j4_multipos_config_.safe_max) {
                    RCLCPP_ERROR(node_->get_logger(), "❌ J4 position %.3fm exceeds safety limits [%.3fm, %.3fm] - SKIPPING",
                                j4_absolute, j4_multipos_config_.safe_min, j4_multipos_config_.safe_max);
                    ++multipos_stats_.j4_move_failures;
                    continue;
                }

                // Also validate against motor limits
                if (joint4_limits_.loaded) {
                    const double PLANNING_MARGIN = 0.98;
                    const double j4_min = joint4_limits_.min * PLANNING_MARGIN;
                    const double j4_max = joint4_limits_.max * PLANNING_MARGIN;

                    if (j4_absolute < j4_min || j4_absolute > j4_max) {
                        RCLCPP_ERROR(node_->get_logger(), "❌ J4 position %.3fm exceeds motor limits [%.3fm, %.3fm] - SKIPPING",
                                    j4_absolute, j4_min, j4_max);
                        recovery_manager_->incrementJointLimitFailures();
                        ++multipos_stats_.j4_move_failures;
                        continue;
                    }
                }

                // Move J4 to scan position
                auto move_start = std::chrono::steady_clock::now();

                if (areMotorsAvailable() && joint_move_4_) {
                    RCLCPP_INFO(node_->get_logger(), "⚙️  Moving J4 to %+.3fm...", j4_absolute);
                    auto result = joint_move_4_->move_joint(j4_absolute, true);  // BLOCKING - wait for completion
                    if (result != MoveResult::SUCCESS) {
                        RCLCPP_WARN(node_->get_logger(),
                            "[MOVE] Joint 4 move failed (result=%d, target=%.4f)",
                            static_cast<int>(result), j4_absolute);
                    }
                    recordMoveResult(4, result);

                    // Additional settling time after motor reaches target (for camera/TF)
                    const double camera_settling = j4_multipos_config_.detection_settling_time;
                    RCLCPP_DEBUG(node_->get_logger(), "⏸  Camera settling: %.0fms (waiting for fresh frame)",
                                camera_settling * 1000.0);
                    // BLOCKING_SLEEP_OK: main-thread camera settling delay — reviewed 2026-03-14
                    yanthra_move::utilities::blockingThreadSleep(
                        std::chrono::milliseconds(static_cast<int>(camera_settling * 1000)));
                } else {
                    RCLCPP_WARN(node_->get_logger(), "⚠️  Motors not available - skipping J4 movement");
                    ++multipos_stats_.j4_move_failures;
                    continue;
                }

                auto move_end = std::chrono::steady_clock::now();
                auto move_duration = std::chrono::duration_cast<std::chrono::milliseconds>(move_end - move_start).count();

                // Trigger fresh detection at this J4 position
                RCLCPP_INFO(node_->get_logger(), "📸 Triggering detection at J4=%+.3fm (move took %ldms)",
                            j4_absolute, move_duration);

                auto detection_start = std::chrono::steady_clock::now();
                RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Calling detection_trigger_callback_()...");
                auto fresh_positions_opt = detection_trigger_callback_();
                RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: detection_trigger_callback_() returned, has_value=%s",
                           fresh_positions_opt.has_value() ? "true" : "false");
                auto detection_end = std::chrono::steady_clock::now();
                auto detection_duration = std::chrono::duration_cast<std::chrono::milliseconds>(detection_end - detection_start).count();

                if (!fresh_positions_opt.has_value()) {
                    RCLCPP_WARN(node_->get_logger(), "⚠️  Detection trigger returned no data at J4=%+.3fm (took %ldms)",
                               j4_absolute, detection_duration);
                    RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Skipping to next J4 position (continue statement)");
                    continue;
                }

                std::vector<CottonDetection> fresh_positions = fresh_positions_opt.value();
                RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Extracted fresh_positions, size=%zu", fresh_positions.size());
                RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: About to check if positions empty...");

                if (fresh_positions.empty()) {
                    RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Positions vector is EMPTY");
                    RCLCPP_INFO(node_->get_logger(), "ℹ️  No cotton detected at J4=%+.3fm (detection took %ldms) - continuing to next position",
                               j4_absolute, detection_duration);

                    // Continue to next position (no early exit - always check all positions)
                    continue;
                }

                RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: Positions vector is NOT empty, size=%zu", fresh_positions.size());
                RCLCPP_INFO(node_->get_logger(), "✅ Found %zu cotton(s) at J4=%+.3fm (detection took %ldms)",
                           fresh_positions.size(), j4_absolute, detection_duration);

                // Track total detections
                total_cotton_detected += fresh_positions.size();

                // Log detected positions
                for (size_t i = 0; i < fresh_positions.size(); ++i) {
                    RCLCPP_INFO(node_->get_logger(), "   Cotton #%zu: cam(%.3f, %.3f, %.3f)",
                               i + 1, fresh_positions[i].position.x, fresh_positions[i].position.y, fresh_positions[i].position.z);
                }

                // Pick ALL cottons visible at this J4 position
                // Per-joint homing: J3 always homes (clears FOV), J4 only homes at last position
                // (saves ~0.5-1s per mid-sweep position by avoiding unnecessary J4 home travel)
                bool is_last_scan_position = (pos_idx == scan_order.size() - 1);
                bool scan_home_j4 = is_last_scan_position;  // Skip J4 homing at mid-sweep

                RCLCPP_INFO(node_->get_logger(), "🎯 Picking %zu cotton(s) at J4=%+.3fm%s",
                           fresh_positions.size(), j4_absolute,
                           scan_home_j4 ? " (full homing - last position)" : " (home J3, skip J4 - mid-sweep)");

                auto pick_start = std::chrono::steady_clock::now();
                int picked_at_position = executeCottonPickingSequence(fresh_positions, /*home_j5=*/true, /*home_j3=*/true, /*home_j4=*/scan_home_j4);
                auto pick_end = std::chrono::steady_clock::now();
                auto pick_duration = std::chrono::duration_cast<std::chrono::milliseconds>(pick_end - pick_start).count();

                RCLCPP_INFO(node_->get_logger(), "🔍 DEBUG: executeCottonPickingSequence() returned: picked=%d", picked_at_position);

                picked_count += picked_at_position;
                total_cotton_picked_ += picked_at_position;

                RCLCPP_INFO(node_->get_logger(), "✅ Picked %d/%zu cotton(s) at J4=%+.3fm (took %ldms)",
                           picked_at_position, fresh_positions.size(), j4_absolute, pick_duration);

                // Update position statistics
                if (j4_multipos_config_.enable_position_stats && picked_at_position > 0) {
                    multipos_stats_.position_hit_count[j4_offset] += picked_at_position;

                    // Track center vs. non-center picks
                    if (std::abs(j4_offset) < 0.001) {  // Center position (0mm)
                        multipos_stats_.cottons_found_center += picked_at_position;
                    } else {
                        multipos_stats_.cottons_found_multipos += picked_at_position;
                    }
                }

                // Track if motion occurred
                if (picked_at_position > 0) {
                    motion_occurred = true;
                }
            }

            // J4 intentionally NOT homed here — end-of-cycle homes J4 directly.
            // Removing this redundant home saves ~300-500ms per cycle.

            // Reset J4 scan offset after multi-position cycle completes
            current_j4_scan_offset_ = 0.0;

            RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
            RCLCPP_INFO(node_->get_logger(), "🏁 Multi-position scan finished: %d total cotton(s) picked across all positions",
                        picked_count);
            RCLCPP_INFO(node_->get_logger(), " ");
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // SINGLE-POSITION MODE (original behavior, or fallback if multi-pos disabled)
    // ═══════════════════════════════════════════════════════════════════════════
    if (!use_multiposition) {
        // Ensure J4 offset is zero when not using multi-positioning
        current_j4_scan_offset_ = 0.0;
        // Normal cotton detection mode
        auto cotton_positions_opt = cotton_position_provider_();

        if (!cotton_positions_opt.has_value()) {
            RCLCPP_DEBUG(node_->get_logger(), "No cotton detection data available yet");
            // Handle gracefully - either idle or execute height scan
            if (height_scan_enable_) {
                RCLCPP_INFO(node_->get_logger(), "No detections available, executing height scan");
                executeHeightScan(height_scan_min_, height_scan_max_, height_scan_step_);
            } else {
                RCLCPP_INFO(node_->get_logger(), "No detections available, skipping cycle");
            }
            return true;  // Not an error, just no data yet
        }

        std::vector<CottonDetection> cotton_positions = cotton_positions_opt.value();
        total_cotton_detected = cotton_positions.size();  // Track for logging

        if (cotton_positions.empty()) {
            RCLCPP_INFO(node_->get_logger(), "No cotton positions detected, executing height scan instead");

            if (height_scan_enable_) {
                executeHeightScan(height_scan_min_, height_scan_max_, height_scan_step_);
            } else {
                RCLCPP_INFO(node_->get_logger(), "Height scan disabled, skipping to end-of-cycle parking");
            }
        } else {
            RCLCPP_INFO(node_->get_logger(), "Found %zu cotton positions for picking:", cotton_positions.size());
            for (size_t i = 0; i < cotton_positions.size(); ++i) {
                RCLCPP_INFO(node_->get_logger(), "   #%zu: (%.3f, %.3f, %.3f)",
                           i + 1, cotton_positions[i].position.x, cotton_positions[i].position.y, cotton_positions[i].position.z);
            }

            // Execute cotton picking sequence
            picked_count = executeCottonPickingSequence(cotton_positions);
            total_cotton_picked_ += picked_count;

            RCLCPP_INFO(node_->get_logger(), "Picked %d cotton pieces this cycle (total: %d)",
                        picked_count, total_cotton_picked_.load());

            // Track if actual motion occurred (successful picks mean arm moved)
            motion_occurred = (picked_count > 0);

            // Note: Cotton is already dropped at home after each pick
            // No need for batch drop at end of cycle
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // END-OF-CYCLE: Home joints that may be out of position.
    // J4 always homes (center of scan range).
    // J3 may need homing if it was left at eject position after a failed pick.
    // J5 should already be home from retreat, but verify just in case.
    // ═══════════════════════════════════════════════════════════════
    if (areMotorsAvailable()) {
        // Check if J3 is at home position (may be stuck at eject after failed pick)
        const double j3_home_tolerance = 0.05;  // 0.05 rotations tolerance
        const double j3_current = getJoint3Position();
        bool j3_needs_homing = (j3_current < -0.5) ||  // Position not available or very negative
                              (std::abs(j3_current - joint3_init_.homing_position) > j3_home_tolerance);

        if (j3_needs_homing) {
            RCLCPP_INFO(node_->get_logger(), "🏠 End of cycle: J3 not at home (%.4f), homing...", j3_current);
            if (joint_move_3_) {
                auto r3 = joint_move_3_->move_joint(joint3_init_.homing_position, true);
                recordMoveResult(3, r3);
                if (r3 != MoveResult::SUCCESS) {
                    RCLCPP_WARN(node_->get_logger(), "[END-OF-CYCLE] J3 homing failed (result=%d)", static_cast<int>(r3));
                }
            }
        }

        RCLCPP_INFO(node_->get_logger(), "🏠 End of cycle: homing J4...");
        if (joint_move_4_) {
            const double joint4_home = joint4_init_.homing_position;
            auto r4 = joint_move_4_->move_joint(joint4_home, true);
            recordMoveResult(4, r4);
            if (r4 != MoveResult::SUCCESS) {
                RCLCPP_WARN(node_->get_logger(), "[END-OF-CYCLE] J4 homing failed (result=%d)", static_cast<int>(r4));
            }
        }
        // Turn off end effector
        if (end_effector_enable_ && gpio_control_) {
            RCLCPP_DEBUG(node_->get_logger(), "[EE] End of cycle: Turning OFF end effector");
            gpio_control_->end_effector_control(false);
            capture_sequence_->markEeInactive();
        }
        // Turn off compressor
        if (gpio_control_) {
            RCLCPP_DEBUG(node_->get_logger(), "[Compressor] End of cycle: Ensuring compressor is OFF");
            gpio_control_->compressor_control(false);
            capture_sequence_->markCompressorInactive();
        }
        RCLCPP_INFO(node_->get_logger(), "✅ End of cycle: J3/J4 homed, EE and compressor OFF");
    } else {
        RCLCPP_WARN(node_->get_logger(), "⚠️ Motors not available - skipping end-of-cycle homing");
    }

    double cycle_end_time = getCurrentTimeMillis();
    double cycle_duration = cycle_end_time - cycle_start_time;

    // Detailed cycle completion stats
    RCLCPP_INFO(node_->get_logger(), " ");
    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), "✅ CYCLE #%d COMPLETION REPORT", cycle_count_.load());
    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), "⏱️  Total cycle time: %.2f ms", cycle_duration);
    RCLCPP_INFO(node_->get_logger(), "🧵 Cotton detected: %d positions", total_cotton_detected);
    RCLCPP_INFO(node_->get_logger(), "🎯 Cotton picked this cycle: %d", picked_count);
    RCLCPP_INFO(node_->get_logger(), "🔄 Motion occurred: %s", motion_occurred ? "YES" : "NO");
    RCLCPP_INFO(node_->get_logger(), "📊 Picks: %d/%d successful", picked_count, total_cotton_detected);

    // Session statistics (cumulative since node start)
    RCLCPP_INFO(node_->get_logger(), "────────────────────────────────────────────────────────────────────────");
    RCLCPP_INFO(node_->get_logger(), "📈 SESSION STATISTICS (cumulative):");
    RCLCPP_INFO(node_->get_logger(), "   🎯 Total picks: %d attempted, %d successful (%.1f%% success rate)",
                recovery_manager_->getTotalPicksAttempted(), recovery_manager_->getTotalPicksSuccessful(),
                recovery_manager_->getTotalPicksAttempted() > 0 ? 100.0 * recovery_manager_->getTotalPicksSuccessful() / recovery_manager_->getTotalPicksAttempted() : 0.0);
    if (recovery_manager_->getTotalPicksAttempted() > 0) {
        RCLCPP_INFO(node_->get_logger(), "   ⏱️  Average pick duration: %.1f ms", getAveragePickDurationMs());
    }
    RCLCPP_INFO(node_->get_logger(), "   🔧 EE activations: %d, Compressor activations: %d",
                recovery_manager_->getEeActivationCount(), recovery_manager_->getCompressorActivationCount());

    // Failure statistics (cumulative since node start)
    if (recovery_manager_->getTfFailureCount() > 0 || recovery_manager_->getPositionFeedbackFailureCount() > 0 || recovery_manager_->getJointLimitFailureCount() > 0) {
        RCLCPP_INFO(node_->get_logger(), "────────────────────────────────────────────────────────────────────────");
        RCLCPP_INFO(node_->get_logger(), "⚠️  FAILURE STATISTICS (cumulative):");
        if (recovery_manager_->getTfFailureCount() > 0) {
            RCLCPP_WARN(node_->get_logger(), "   🔄 TF transform failures: %d (picks aborted due to missing transforms)", recovery_manager_->getTfFailureCount());
        }
        if (recovery_manager_->getJointLimitFailureCount() > 0) {
            RCLCPP_WARN(node_->get_logger(), "   📏 Joint limit violations: %d (cotton out of reach)", recovery_manager_->getJointLimitFailureCount());
        }
        if (recovery_manager_->getPositionFeedbackFailureCount() > 0) {
            RCLCPP_WARN(node_->get_logger(), "   📍 Position feedback timeouts: %d total (J3=%d, J4=%d, J5=%d)",
                        recovery_manager_->getPositionFeedbackFailureCount(),
                        recovery_manager_->getPositionFeedbackFailureJ3(), recovery_manager_->getPositionFeedbackFailureJ4(), recovery_manager_->getPositionFeedbackFailureJ5());
        }
    }

    // GPIO statistics (if available)
    if (gpio_control_) {
        auto gpio_stats = gpio_control_->get_stats();
        if (gpio_stats.write_failures > 0 || gpio_stats.reconnect_count > 0) {
            RCLCPP_INFO(node_->get_logger(), "────────────────────────────────────────────────────────────────────────");
            RCLCPP_INFO(node_->get_logger(), "🔌 GPIO STATISTICS:");
            if (gpio_stats.write_failures > 0) {
                RCLCPP_WARN(node_->get_logger(), "   ❌ Write failures: %d", gpio_stats.write_failures);
            }
            if (gpio_stats.reconnect_count > 0) {
                RCLCPP_INFO(node_->get_logger(), "   🔄 Reconnections: %d (successful recovery from pigpiod restart)", gpio_stats.reconnect_count);
            }
            if (gpio_stats.reconnect_failures > 0) {
                RCLCPP_ERROR(node_->get_logger(), "   💥 Reconnection failures: %d (EE/compressor may not work!)", gpio_stats.reconnect_failures);
            }
        }
    }

    // Multi-position statistics (if enabled and active)
    if (j4_multipos_config_.enabled && multipos_stats_.total_scans > 0) {
        RCLCPP_INFO(node_->get_logger(), "────────────────────────────────────────────────────────────────────────");
        RCLCPP_INFO(node_->get_logger(), "🔄 MULTI-POSITION STATISTICS (session cumulative):");
        RCLCPP_INFO(node_->get_logger(), "   📊 Total scans: %d", multipos_stats_.total_scans);
        RCLCPP_INFO(node_->get_logger(), "   🎯 Cotton found: center=%d, non-center=%d (%.1f%% improvement via multi-pos)",
                    multipos_stats_.cottons_found_center, multipos_stats_.cottons_found_multipos,
                    multipos_stats_.cottons_found_center > 0 ?
                        100.0 * multipos_stats_.cottons_found_multipos / multipos_stats_.cottons_found_center : 0.0);
        RCLCPP_INFO(node_->get_logger(), "   ⏩ Early exits: %d (optimization active)", multipos_stats_.early_exits);

        if (multipos_stats_.j4_move_failures > 0) {
            RCLCPP_WARN(node_->get_logger(), "   ❌ J4 movement failures: %d", multipos_stats_.j4_move_failures);
        }

        // Per-position hit statistics
        if (j4_multipos_config_.enable_position_stats && !multipos_stats_.position_hit_count.empty()) {
            RCLCPP_INFO(node_->get_logger(), "   📍 Position effectiveness:");
            for (const auto& [offset, count] : multipos_stats_.position_hit_count) {
                RCLCPP_INFO(node_->get_logger(), "      J4 offset %+.3fm (%+.0fmm): %d cotton(s) found",
                           offset, offset * 1000.0, count);
            }
        }
    }

    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), " ");

    // Check for emergency stop
    if (isEmergencyStopRequested()) {
        RCLCPP_WARN(node_->get_logger(), "🛑 Emergency stop requested during cycle execution");
        return false;
    }

    return true;
}

int MotionController::executeCottonPickingSequence(const std::vector<CottonDetection>& cotton_detections, bool home_j5, bool home_j3, bool home_j4) {
    (void)home_j5;  // J5 always homes (retraction mandatory) — parameter kept for API consistency
    if (cotton_detections.empty()) {
        RCLCPP_WARN(node_->get_logger(), "No cotton positions provided for picking sequence");
        return 0;
    }

    // Make a mutable copy for optimization
    // Extract positions for the optimizer, keep detections in parallel
    std::vector<CottonDetection> optimized_detections = cotton_detections;
    std::vector<geometry_msgs::msg::Point> optimized_positions;
    optimized_positions.reserve(optimized_detections.size());
    for (const auto& det : optimized_detections) {
        optimized_positions.push_back(det.position);
    }

    // Get picking strategy from parameter
    std::string strategy_str = "raster_scan";
    if (node_->has_parameter("picking_strategy")) {
        strategy_str = node_->get_parameter("picking_strategy").as_string();
    }

    // Convert string to enum
    CottonPickingOptimizer::Strategy strategy = CottonPickingOptimizer::Strategy::RASTER_SCAN;
    std::string strategy_name = "raster_scan";
    if (strategy_str == "none") {
        strategy = CottonPickingOptimizer::Strategy::NONE;
        strategy_name = "none (detection order)";
    } else if (strategy_str == "nearest_first") {
        strategy = CottonPickingOptimizer::Strategy::NEAREST_FIRST;
        strategy_name = "nearest_first (greedy)";
    } else if (strategy_str == "phi_sweep") {
        strategy = CottonPickingOptimizer::Strategy::PHI_SWEEP;
        strategy_name = "phi_sweep (minimize base rotation)";
    } else if (strategy_str == "hierarchical") {
        strategy = CottonPickingOptimizer::Strategy::HIERARCHICAL;
        strategy_name = "hierarchical (2D energy-optimal)";
    } else if (strategy_str == "raster_scan") {
        strategy = CottonPickingOptimizer::Strategy::RASTER_SCAN;
        strategy_name = "raster_scan (serpentine rows)";
    } else {
        RCLCPP_WARN(node_->get_logger(), "⚠️  Unknown picking_strategy '%s', using raster_scan", strategy_str.c_str());
    }

    // Energy-efficient path optimization
    if (optimized_positions.size() > 1 && strategy != CottonPickingOptimizer::Strategy::NONE) {
        RCLCPP_INFO(node_->get_logger(),
                   "📐 Optimizing picking order for %zu cotton positions (%s)",
                   optimized_positions.size(), strategy_name.c_str());

        // Save pre-optimization order to track reordering
        std::vector<geometry_msgs::msg::Point> pre_opt_positions = optimized_positions;

        // Transform positions to arm frame BEFORE optimization
        // The optimizer sorts by phi (base rotation angle), which only makes sense in arm frame
        std::vector<geometry_msgs::msg::Point> arm_frame_positions;
        arm_frame_positions.reserve(optimized_positions.size());

        try {
            auto tf_start = std::chrono::steady_clock::now();
            auto transform = tf_buffer_->lookupTransform(
                "yanthra_link", "camera_link", tf2::TimePointZero, tf2::durationFromSec(0.5));
            auto tf_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - tf_start).count();
            RCLCPP_DEBUG(node_->get_logger(), "🔍 [TIMING] lookupTransform (sequence): %ldms", tf_ms);
            if (tf_ms > 200) {
                RCLCPP_WARN(node_->get_logger(), "⚠️ [TIMING] Slow lookupTransform (sequence): %ldms (threshold: 200ms)", tf_ms);
            }

            for (const auto& cam_pos : optimized_positions) {
                geometry_msgs::msg::PointStamped cam_pt, arm_pt;
                cam_pt.header.frame_id = "camera_link";
                cam_pt.point = cam_pos;
                tf2::doTransform(cam_pt, arm_pt, transform);
                arm_frame_positions.push_back(arm_pt.point);
            }

            // Apply selected optimization strategy
            CottonPickingOptimizer::optimizePickingOrder(
                optimized_positions,
                strategy);

            // Log the optimized order
            RCLCPP_INFO(node_->get_logger(), "📊 Optimized picking order:");
            for (size_t i = 0; i < optimized_positions.size(); ++i) {
                RCLCPP_INFO(node_->get_logger(), "   #%zu: cam(%.3f,%.3f,%.3f)",
                           i + 1, optimized_positions[i].x, optimized_positions[i].y, optimized_positions[i].z);
            }

        } catch (const tf2::TransformException& ex) {
            RCLCPP_WARN(node_->get_logger(),
                       "⚠️  TF lookup failed for optimization, using detection order: %s", ex.what());
            // Fall back to legacy optimizer (uses camera frame - less accurate)
            double current_phi = 0.0;
            CottonPickingOptimizer::optimizePickingOrder(
                optimized_positions,
                strategy,
                current_phi
            );
        }

        // Apply the same reordering to optimized_detections
        // Match each optimized position back to its original index
        std::vector<CottonDetection> reordered_detections;
        reordered_detections.reserve(optimized_positions.size());
        std::vector<bool> used(pre_opt_positions.size(), false);
        for (const auto& opt_pos : optimized_positions) {
            for (size_t j = 0; j < pre_opt_positions.size(); ++j) {
                if (!used[j] &&
                    pre_opt_positions[j].x == opt_pos.x &&
                    pre_opt_positions[j].y == opt_pos.y &&
                    pre_opt_positions[j].z == opt_pos.z) {
                    reordered_detections.push_back(optimized_detections[j]);
                    used[j] = true;
                    break;
                }
            }
        }
        optimized_detections = std::move(reordered_detections);
    } else if (strategy == CottonPickingOptimizer::Strategy::NONE) {
        RCLCPP_INFO(node_->get_logger(), "📐 Using detection order (picking_strategy=none)");
    }

    int picked_count = 0;

    // Timeline tracking for cycle analysis
    struct CottonTiming {
        double approach_ms;
        double capture_ms;
        double retreat_ms;
        double total_ms;
        bool success;
        float confidence = 0.0f;
        int detection_id = -1;
        int64_t delay_ms = 0;
        int64_t detection_age_ms = 0;
    };
    std::vector<CottonTiming> cotton_timings;
    cotton_timings.reserve(optimized_detections.size());
    auto sequence_start = std::chrono::steady_clock::now();
    delay_ms_ = 0;  // No delay before first cotton

    RCLCPP_INFO(node_->get_logger(), "🎯 Starting cotton picking sequence for %zu positions", optimized_detections.size());

    // ═══════════════════════════════════════════════════════════════
    // L3 IDLE PARKING: Move L3 from parking to homing before approach
    // SAFETY: J4 can only move when L3 is at homing (tilted down, creates clearance)
    // ═══════════════════════════════════════════════════════════════
    if (enable_l3_idle_parking_ && l3_at_parking_) {
        RCLCPP_INFO(node_->get_logger(), "🌡️  L3 at parking - moving to homing before approach (creating clearance for J4)...");
        moveL3ToHoming();
    }

    for (size_t i = 0; i < optimized_detections.size() && !isEmergencyStopRequested(); ++i) {
        const auto& detection = optimized_detections[i];
        const auto& position = detection.position;

        // Determine per-cotton homing flags:
        // - Intermediate cottons (not last): only J5 homes (retract), skip J3/J4
        // - Last cotton: use the caller's per-joint flags (which encode scan position intent)
        bool is_last_cotton = (i == optimized_detections.size() - 1);
        bool cotton_home_j5 = true;  // J5 always homes (retraction mandatory)
        bool cotton_home_j3 = is_last_cotton ? home_j3 : false;  // J3 only for last cotton
        bool cotton_home_j4 = is_last_cotton ? home_j4 : false;  // J4 only for last cotton

        auto cotton_start = std::chrono::steady_clock::now();
        CottonTiming timing = {0, 0, 0, 0, false};
        timing.confidence = detection.confidence;
        timing.detection_id = detection.detection_id;

        // Compute detection age (time since detection was captured)
        auto detection_age = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - detection.detection_time).count();
        RCLCPP_INFO(node_->get_logger(), "⏱️ [TIMING] Detection age: %ldms", detection_age);
        timing.detection_age_ms = detection_age;
        if (detection_age > 2000) {
            RCLCPP_WARN(node_->get_logger(), "⚠️ [TIMING] Stale detection! Age: %ldms (threshold: 2000ms)", detection_age);
        }

        int64_t phase_approach_ms = 0, phase_capture_ms = 0, phase_retreat_ms = 0;
        if (pickCottonAtPosition(detection, cotton_home_j5, cotton_home_j3, cotton_home_j4,
                                 &phase_approach_ms, &phase_capture_ms, &phase_retreat_ms)) {
            picked_count++;
            timing.success = true;
            RCLCPP_INFO(node_->get_logger(), "✅ Cotton #%d picked at (%.3f,%.3f,%.3f)",
                        picked_count, position.x, position.y, position.z);

            // Re-trigger detection after each successful pick (except last)
            // to validate remaining positions and prevent duplicate picks
            // NOTE: Disabled by default via enable_detection_retrigger parameter
            // Detection callbacks are processed by the background executor thread
            if (enable_detection_retrigger_ && !is_last_cotton && detection_trigger_callback_) {
                RCLCPP_INFO(node_->get_logger(), "🔄 Re-triggering detection to validate remaining cotton positions...");

                auto retrigger_start = std::chrono::steady_clock::now();
                auto fresh_detections = detection_trigger_callback_();
                auto retrigger_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - retrigger_start).count();
                RCLCPP_INFO(node_->get_logger(), "🔄 [TIMING] Retrigger detection: %ldms", retrigger_ms);

                if (fresh_detections.has_value() && !fresh_detections->empty()) {
                    RCLCPP_INFO(node_->get_logger(), "   ✅ Fresh detection: %zu cotton positions remaining",
                                fresh_detections->size());

                    // Update remaining detections with fresh detection
                    // Clear detections from current index onwards and replace with fresh ones
                    optimized_detections.erase(optimized_detections.begin() + i + 1, optimized_detections.end());

                    // Add fresh detections (they'll be picked in subsequent iterations)
                    for (const auto& fresh_det : *fresh_detections) {
                        optimized_detections.push_back(fresh_det);
                    }

                    RCLCPP_INFO(node_->get_logger(), "   📋 Updated queue: %zu positions to go",
                                optimized_detections.size() - i - 1);
                } else {
                    RCLCPP_INFO(node_->get_logger(), "   ℹ️ No more cotton detected - finishing sequence");
                    break;  // No more cotton, exit loop early
                }
            }
        } else {
            RCLCPP_WARN(node_->get_logger(), "❌ Failed to pick cotton at position [%.3f, %.3f, %.3f]",
                        position.x, position.y, position.z);
        }

        // Record phase durations and timing for this cotton
        timing.approach_ms = phase_approach_ms;
        timing.capture_ms = phase_capture_ms;
        timing.retreat_ms = phase_retreat_ms;
        auto cotton_end = std::chrono::steady_clock::now();
        timing.total_ms = std::chrono::duration_cast<std::chrono::milliseconds>(cotton_end - cotton_start).count();

        // Add delay between picking operations
        if (i > 0 && picking_delay_ > 0.0) {
            auto delay_start = std::chrono::steady_clock::now();
            // BLOCKING_SLEEP_OK: main-thread picking sequence delay — reviewed 2026-03-14
            yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(static_cast<int>(picking_delay_ * 1000)));
            auto delay_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - delay_start).count();
            timing.delay_ms = delay_ms;
        } else {
            timing.delay_ms = 0;
        }

        delay_ms_ = timing.delay_ms;  // Store for next pick's pick_complete JSON
        cotton_timings.push_back(timing);
    }

    // Print cycle timeline summary
    auto sequence_end = std::chrono::steady_clock::now();
    auto sequence_total_ms = std::chrono::duration_cast<std::chrono::milliseconds>(sequence_end - sequence_start).count();

    RCLCPP_INFO(node_->get_logger(), " ");
    RCLCPP_INFO(node_->get_logger(), "📊 CYCLE TIMELINE (%ldms total):", sequence_total_ms);
    for (size_t i = 0; i < cotton_timings.size(); ++i) {
        const auto& t = cotton_timings[i];
        RCLCPP_INFO(node_->get_logger(), "   Cotton #%zu: %ldms (approach=%ldms, capture=%ldms, retreat=%ldms, delay=%ldms) [%s] conf=%.2f",
                   i + 1, static_cast<long>(t.total_ms),
                   static_cast<long>(t.approach_ms), static_cast<long>(t.capture_ms),
                   static_cast<long>(t.retreat_ms), static_cast<long>(t.delay_ms),
                   t.success ? "SUCCESS" : "FAILED", t.confidence);
    }

    RCLCPP_INFO(node_->get_logger(), "🏁 Cotton picking sequence completed: %d/%zu successful",
                picked_count, optimized_detections.size());

    // Emit cycle_complete structured JSON log
    {
        int succeeded = 0, failed = 0;
        int64_t total_detection_age = 0;
        for (const auto& t : cotton_timings) {
            if (t.success) succeeded++;
            else failed++;
            total_detection_age += t.detection_age_ms;
        }
        int attempted = succeeded + failed;

        auto j = pragati::json_envelope("cycle_complete", node_->get_logger().get_name());
        j["total_ms"] = sequence_total_ms;
        j["cottons_attempted"] = attempted;
        j["cottons_succeeded"] = succeeded;
        j["cottons_failed"] = failed;
        j["pick_rate_pct"] = attempted > 0 ? (succeeded * 100.0 / attempted) : 0.0;
        j["detection_count"] = static_cast<int>(cotton_detections.size());
        j["optimizer_strategy"] = strategy_name;
        j["detection_age_ms"] = attempted > 0 ? (total_detection_age / attempted) : 0;

        RCLCPP_INFO(node_->get_logger(), "%s", j.dump().c_str());
    }

    return picked_count;
}

bool MotionController::pickCottonAtPosition(const CottonDetection& detection, bool home_j5, bool home_j3, bool home_j4,
                                              int64_t* approach_ms, int64_t* capture_ms, int64_t* retreat_ms) {
    const auto& position = detection.position;
    auto pick_start = std::chrono::steady_clock::now();
    recovery_manager_->recordPickAttempt();
    ee_total_on_ms_ = 0;
    approach_j3_ms_ = 0;
    approach_j4_ms_ = 0;
    approach_j5_ms_ = 0;
    retreat_j5_ms_ = 0;
    retreat_ee_off_ms_ = 0;
    retreat_j3_ms_ = 0;
    retreat_j4_ms_ = 0;
    retreat_compressor_ms_ = 0;
    // Reset per-pick logging fields
    polar_r_ = 0.0;
    polar_theta_ = 0.0;
    polar_phi_ = 0.0;
    plan_status_ = "N/A";
    plan_j3_cmd_ = 0.0;
    plan_j4_cmd_ = 0.0;
    plan_j5_cmd_ = 0.0;
    feedback_j3_ok_ = true;
    feedback_j3_error_ = 0.0;
    feedback_j4_ok_ = true;
    feedback_j4_error_ = 0.0;
    feedback_j5_ok_ = true;
    feedback_j5_error_ = 0.0;
    last_cotton_position_ = 0.0;  // F16: Reset stale position from previous pick cycle
    int64_t recovery_ms_total = 0;  // Accumulated recovery time across failure paths
    bool success = false;
    bool timed_out = false;

    // Pick cycle deadline (D6 safety timeout)
    const double timeout_sec = pick_cycle_timeout_sec_.load();
    const auto pick_deadline = pick_start + std::chrono::milliseconds(
        static_cast<int64_t>(timeout_sec * 1000.0));

    // Lambda to check if pick cycle has exceeded deadline
    auto isPickTimedOut = [&](const char* phase_name) -> bool {
        if (std::chrono::steady_clock::now() > pick_deadline) {
            recovery_manager_->recordPickTimeout();
            timed_out = true;
            auto j = pragati::json_envelope("pick_cycle_timeout", node_->get_logger().get_name());
            double elapsed_seconds = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - pick_start).count();
            j["phase"] = phase_name;
            j["elapsed_seconds"] = elapsed_seconds;
            j["timeout_threshold"] = timeout_sec;
            j["cotton_id"] = detection.detection_id;
            j["total_timed_out"] = recovery_manager_->getTotalPicksTimedOut();
            RCLCPP_WARN(node_->get_logger(), "%s", j.dump().c_str());
            // Escalate to error recovery (D3 centralized dispatch)
            {
                yanthra_move::FailureContext ctx;
                ctx.joint_id = 0;  // Not joint-specific
                ctx.cycle_count = cycle_count_.load();
                recovery_manager_->dispatchFailure(yanthra_move::FailureType::PICK_TIMEOUT, ctx);
            }
            return true;
        }
        return false;
    };

    RCLCPP_INFO(node_->get_logger(), "🎯 Picking cotton at (%.3f, %.3f, %.3f) conf=%.2f id=%d",
        detection.position.x, detection.position.y, detection.position.z,
        detection.confidence, detection.detection_id);

    // Compute detection age for JSON logging
    auto detection_age_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - detection.detection_time).count();

    // Determine if this is a "full homing" scenario (all joints home = end of cycle)
    bool full_homing = home_j5 && home_j3 && home_j4;

    // Lambda to emit pick_complete JSON log before return
    auto emit_pick_complete_json = [&]() {
        auto j = pragati::json_envelope("pick_complete", node_->get_logger().get_name());
        auto total_pick_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - pick_start).count();

        j["cotton_id"] = detection.detection_id;
        j["confidence"] = detection.confidence;
        j["detection_id"] = detection.detection_id;
        j["detection_age_ms"] = detection_age_ms;
        j["approach_ms"] = approach_ms ? *approach_ms : 0;
        j["capture_ms"] = ee_total_on_ms_;
        j["retreat_ms"] = retreat_ms ? *retreat_ms : 0;
        j["delay_ms"] = delay_ms_;
        j["total_ms"] = total_pick_ms;
        j["success"] = success;
        j["timed_out"] = timed_out;
        j["ee_on_ms"] = ee_total_on_ms_;
        j["j3_ms"] = approach_j3_ms_;
        j["j4_ms"] = approach_j4_ms_;
        j["j5_ms"] = approach_j5_ms_;
        j["retreat_j5_ms"] = retreat_j5_ms_;
        j["retreat_ee_off_ms"] = retreat_ee_off_ms_;
        j["retreat_j3_ms"] = retreat_j3_ms_;
        j["retreat_j4_ms"] = retreat_j4_ms_;
        j["retreat_compressor_ms"] = retreat_compressor_ms_;
        j["position"] = {{"x", detection.position.x}, {"y", detection.position.y}, {"z", detection.position.z}};
        j["polar"] = {{"r", polar_r_}, {"theta", polar_theta_}, {"phi", polar_phi_}};
        j["plan_status"] = plan_status_;
        j["plan_j3"] = plan_j3_cmd_;
        j["plan_j4"] = plan_j4_cmd_;
        j["plan_j5"] = plan_j5_cmd_;
        j["feedback_j3_ok"] = feedback_j3_ok_;
        j["feedback_j3_error"] = feedback_j3_error_;
        j["feedback_j4_ok"] = feedback_j4_ok_;
        j["feedback_j4_error"] = feedback_j4_error_;
        j["feedback_j5_ok"] = feedback_j5_ok_;
        j["feedback_j5_error"] = feedback_j5_error_;
        j["recovery_ms"] = recovery_ms_total;

        RCLCPP_INFO(node_->get_logger(), "%s", j.dump().c_str());
    };

    // Execute approach trajectory (does TF + calculations, skips motor commands if unavailable)
    if (isPickTimedOut("approach")) {
        // Timeout before approach - turn off EE (safety) and home joints
        if (gpio_control_ && end_effector_enable_) {
            gpio_control_->end_effector_control(false);
            capture_sequence_->markEeInactive();
        }
        if (areMotorsAvailable()) {
            executeRetreatTrajectory(home_j5, home_j3, home_j4, retreat_ms);
        }
        emit_pick_complete_json();
        return false;
    }
    if (!executeApproachTrajectory(position, approach_ms)) {
        // Approach failure happens BEFORE motor commands are sent (TF error, joint limits, etc.)
        // J5 is still at home position from previous pick - no recovery needed for non-last
        // Only home all joints if full homing requested (end of cycle will also do this)
        int64_t phase_approach_ms = approach_ms ? *approach_ms : 0;
        RCLCPP_WARN(node_->get_logger(), "❌ [TIMING] Pick FAILED at approach: %ldms (reason: approach_failed)",
            phase_approach_ms);
        auto recovery_start = std::chrono::steady_clock::now();
        if (full_homing && areMotorsAvailable()) {
            RCLCPP_WARN(node_->get_logger(), "🔙 Approach failed (last cotton): homing all joints...");
            (void)moveToPackingPosition();  // Best-effort recovery homing
            recovery_ms_total = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - recovery_start).count();
            RCLCPP_WARN(node_->get_logger(), "🔧 [TIMING] Recovery: %ldms (path: full_homing)", recovery_ms_total);
        } else if (home_j3 && areMotorsAvailable()) {
            // Last cotton at mid-sweep scan position: J4 stays (not last scan pos),
            // J5 already at home (approach failed before it moved), home J3 only
            // so the camera FOV is clear before J4 moves to the next scan position.
            RCLCPP_WARN(node_->get_logger(), "🔙 Approach failed (last at scan pos): homing J3 to clear FOV...");
            if (joint_move_3_) {
                auto j3_result = joint_move_3_->move_joint(joint3_init_.homing_position, true);
                recovery_ms_total = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - recovery_start).count();
                RCLCPP_WARN(node_->get_logger(), "🔧 [TIMING] Recovery: %ldms (path: j3_home_mid_sweep, result=%d)",
                    recovery_ms_total, static_cast<int>(j3_result));
            }
        } else {
            RCLCPP_DEBUG(node_->get_logger(), "⏩ Approach failed: J5 still at home, no recovery needed");
        }
        emit_pick_complete_json();
        return false;
    }

    // Execute capture sequence (activates end-effector + vacuum via GPIO)
    if (isPickTimedOut("capture")) {
        // Timeout after approach but before capture - EE may be on, turn off and retreat
        if (gpio_control_ && end_effector_enable_) {
            gpio_control_->end_effector_control(false);
            capture_sequence_->markEeInactive();
        }
        if (areMotorsAvailable()) {
            executeRetreatTrajectory(home_j5, home_j3, home_j4, retreat_ms);
        }
        emit_pick_complete_json();
        return false;
    }
    if (!executeCaptureSequence(capture_ms)) {
        // Capture failure: J5 is extended at cotton position, need to retract
        int64_t phase_capture_ms = capture_ms ? *capture_ms : 0;
        RCLCPP_WARN(node_->get_logger(), "❌ [TIMING] Pick FAILED at capture: %ldms (reason: capture_failed)",
            phase_capture_ms);
        RCLCPP_ERROR(node_->get_logger(), "Failed to execute capture sequence - recovering");
        auto recovery_start = std::chrono::steady_clock::now();
        if (areMotorsAvailable()) {
            if (full_homing) {
                RCLCPP_WARN(node_->get_logger(), "🔙 Recovery (last cotton): homing all joints...");
                (void)moveToPackingPosition();  // Best-effort recovery homing
                recovery_ms_total = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - recovery_start).count();
                RCLCPP_WARN(node_->get_logger(), "🔧 [TIMING] Recovery: %ldms (path: full_homing)", recovery_ms_total);
            } else {
                RCLCPP_WARN(node_->get_logger(), "🔙 Recovery: retracting J5 only (keeping J3/J4 for next pick)...");
                if (joint_move_5_) {
                    (void)joint_move_5_->move_joint(joint5_init_.homing_position, false);
                }
                // BLOCKING_SLEEP_OK: main-thread motor recovery wait — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(
                    std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
                recovery_ms_total = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - recovery_start).count();
                RCLCPP_WARN(node_->get_logger(), "🔧 [TIMING] Recovery: %ldms (path: j5_retract)", recovery_ms_total);
            }
            RCLCPP_INFO(node_->get_logger(), "✅ Recovery complete - ready for next pick");
        }
        emit_pick_complete_json();
        return false;
    }

    // Execute retreat trajectory (pull back with cotton attached)
    // Pass per-joint homing flags to control which joints home
    if (isPickTimedOut("retreat")) {
        // Timeout after capture but before retreat - EE is on, turn off and force retreat
        if (gpio_control_ && end_effector_enable_) {
            gpio_control_->end_effector_control(false);
            capture_sequence_->markEeInactive();
        }
        if (areMotorsAvailable()) {
            executeRetreatTrajectory(home_j5, home_j3, home_j4, retreat_ms);
        }
        emit_pick_complete_json();
        return false;
    }
    if (!executeRetreatTrajectory(home_j5, home_j3, home_j4, retreat_ms)) {
        // Retreat failure: J5 could be anywhere (mid-retract), need to ensure it's home
        int64_t phase_retreat_ms = retreat_ms ? *retreat_ms : 0;
        RCLCPP_WARN(node_->get_logger(), "❌ [TIMING] Pick FAILED at retreat: %ldms (reason: retreat_failed)",
            phase_retreat_ms);
        RCLCPP_ERROR(node_->get_logger(), "Failed to execute retreat trajectory - recovering");
        auto recovery_start = std::chrono::steady_clock::now();
        if (areMotorsAvailable()) {
            if (full_homing) {
                RCLCPP_WARN(node_->get_logger(), "🔙 Recovery (last cotton): homing all joints...");
                (void)moveToPackingPosition();  // Best-effort recovery homing
                recovery_ms_total = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - recovery_start).count();
                RCLCPP_WARN(node_->get_logger(), "🔧 [TIMING] Recovery: %ldms (path: full_homing)", recovery_ms_total);
            } else {
                RCLCPP_WARN(node_->get_logger(), "🔙 Recovery: retracting J5 only (keeping J3/J4 for next pick)...");
                if (joint_move_5_) {
                    (void)joint_move_5_->move_joint(joint5_init_.homing_position, false);
                }
                // BLOCKING_SLEEP_OK: main-thread motor recovery wait — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(
                    std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
                recovery_ms_total = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - recovery_start).count();
                RCLCPP_WARN(node_->get_logger(), "🔧 [TIMING] Recovery: %ldms (path: j5_retract)", recovery_ms_total);
            }
            RCLCPP_INFO(node_->get_logger(), "✅ Recovery complete - ready for next pick");
        }
        emit_pick_complete_json();
        return false;
    }

    // Skip home return during ArUco calibration testing (faster corner-to-corner movement)
    if (yanthra_lab_calibration_testing_) {
        RCLCPP_DEBUG(node_->get_logger(), "⏩ ArUco mode: Skipping home return - moving directly to next corner");
        // Small delay for stability between picks
        // BLOCKING_SLEEP_OK: main-thread stability delay — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(200));

        // Track successful pick
        success = true;
        recovery_manager_->recordPickSuccess();
        auto pick_end = std::chrono::steady_clock::now();
        recovery_manager_->addPickDuration(std::chrono::duration_cast<std::chrono::milliseconds>(pick_end - pick_start).count());
        emit_pick_complete_json();
        return true;
    }

    // Normal mode: Retreat already brings arm to home and drops cotton

    // Track successful pick
    success = true;
    recovery_manager_->recordPickSuccess();
    auto pick_end = std::chrono::steady_clock::now();
    recovery_manager_->addPickDuration(std::chrono::duration_cast<std::chrono::milliseconds>(pick_end - pick_start).count());

    RCLCPP_INFO(node_->get_logger(), "⚡ [TIMING] EE total ON duration: %ldms", ee_total_on_ms_);

    emit_pick_complete_json();
    return true;
}

bool MotionController::executeApproachTrajectory(const geometry_msgs::msg::Point& position, int64_t* duration_ms) {
    auto start_time = std::chrono::steady_clock::now();

    // ═══════════════════════════════════════════════════════════════
    // TRAJECTORY PLANNING (delegated to TrajectoryPlanner)
    // ═══════════════════════════════════════════════════════════════
    RCLCPP_INFO(node_->get_logger(), "🎯 Executing approach trajectory to cotton at [%.3f, %.3f, %.3f] meters (camera_link frame)",
                position.x, position.y, position.z);

    PlanningParams plan_params;
    plan_params.current_j4_offset = j4_multipos_config_.enable_j4_offset_compensation
                                    ? current_j4_scan_offset_ : 0.0;

    auto plan_result = trajectory_planner_->plan(
        position, joint3_limits_, joint4_limits_, joint5_limits_, plan_params);

    // Store plan result in member variables for pick_complete JSON logging
    polar_r_ = plan_result.trajectory.polar_r;
    polar_theta_ = plan_result.trajectory.polar_theta;
    polar_phi_ = plan_result.trajectory.polar_phi;
    plan_j3_cmd_ = plan_result.trajectory.j3_command;
    plan_j4_cmd_ = plan_result.trajectory.j4_command;
    plan_j5_cmd_ = plan_result.trajectory.j5_command;

    if (plan_result.status != PlanResult::Status::OK) {
        // Map plan error to string for JSON logging
        switch (plan_result.error) {
            case PlanError::INVALID_COORDINATES:
                plan_status_ = "INVALID_COORDINATES"; break;
            case PlanError::TF_FAILURE:
                plan_status_ = "TF_FAILURE"; break;
            case PlanError::OUT_OF_REACH:
                plan_status_ = "OUT_OF_REACH"; break;
            case PlanError::JOINT_LIMIT_EXCEEDED:
                plan_status_ = "JOINT_LIMIT_EXCEEDED"; break;
            case PlanError::COLLISION_BLOCKED:
                plan_status_ = "COLLISION_BLOCKED"; break;
            default:
                plan_status_ = "UNKNOWN_ERROR"; break;
        }

        // Map planning errors to recovery counters
        switch (plan_result.error) {
            case PlanError::INVALID_COORDINATES:
                recovery_manager_->incrementInvalidCoordinates();
                break;
            case PlanError::TF_FAILURE:
                recovery_manager_->incrementTfFailures();
                break;
            case PlanError::OUT_OF_REACH:
            case PlanError::JOINT_LIMIT_EXCEEDED:
            case PlanError::COLLISION_BLOCKED:
                recovery_manager_->incrementJointLimitFailures();
                break;
            default:
                break;
        }
        RCLCPP_WARN(node_->get_logger(), "❌ Planning failed — aborting this pick");
        if (duration_ms) {
            *duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start_time).count();
        }
        return false;
    }

    plan_status_ = "OK";

    // Unpack trajectory for execution
    const double joint3_cmd = plan_result.trajectory.j3_command;
    const double joint4_cmd = plan_result.trajectory.j4_command;
    const double joint5_cmd = plan_result.trajectory.j5_command;

    RCLCPP_INFO(node_->get_logger(), "⚙️  Joints: j3=%.3frot(%.1f°) j4=%.3fm j5=%.3fm",
                joint3_cmd, joint3_cmd * 360.0, joint4_cmd, joint5_cmd);

    // Log collision avoidance status for this cotton pick
    if (plan_result.trajectory.collision_avoidance_active) {
        double headroom = plan_result.trajectory.collision_j5_limit - joint5_cmd;
        RCLCPP_INFO(node_->get_logger(),
            "🛡️  [COLLISION AVOIDANCE] Cotton at [%.3f, %.3f, %.3f] → J5 OK: "
            "%.4fm within safe limit %.4fm (headroom=%.4fm) | "
            "J3=%.1f° cos=%.4f clearance=%.4fm",
            position.x, position.y, position.z,
            joint5_cmd,
            plan_result.trajectory.collision_j5_limit,
            headroom,
            joint3_cmd * 360.0,
            plan_result.trajectory.collision_cos_j3,
            plan_result.trajectory.collision_clearance);
    } else {
        RCLCPP_INFO(node_->get_logger(),
            "🛡️  [COLLISION AVOIDANCE] OFF — J5=%.4fm sent without collision check",
            joint5_cmd);
    }

    // ═══════════════════════════════════════════════════════════════
    // MOTOR AVAILABILITY CHECK: Skip actual motor commands if unavailable
    // TF and calculations are done above (for debugging), only skip execution
    // ═══════════════════════════════════════════════════════════════
    auto motors_start = std::chrono::steady_clock::now();
    bool motors_ok = areMotorsAvailable();
    auto motors_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - motors_start).count();
    if (motors_ms > 100) {
        RCLCPP_WARN(node_->get_logger(), "⚠️ [TIMING] Slow areMotorsAvailable: %ldms (threshold: 100ms)", motors_ms);
    }
    if (!motors_ok) {
        RCLCPP_WARN(node_->get_logger(), "⚠️ Motors NOT available - skipping motor commands (calculations shown above)");
        auto end_time = std::chrono::steady_clock::now();
        auto total_time = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();
        RCLCPP_INFO(node_->get_logger(), "🦾 Approach: %ldms (SKIPPED - no motors)", total_time);
        if (duration_ms) {
            *duration_ms = total_time;
        }
        return true;  // Return true so cycle continues (for testing)
    }

    // ═══════════════════════════════════════════════════════════════
    // MOTOR COMMANDING (delegated to TrajectoryExecutor)
    // J4→J3→J5 sequence with inter-joint delays
    // ═══════════════════════════════════════════════════════════════
    auto cmd_start = std::chrono::steady_clock::now();

    // Capture J5 position BEFORE sending any motor commands.
    // This avoids false TIMEOUTs when monitoring starts after most/all of the move has already completed.
    // NOTE: getJoint5Position() returns -1.0 if position is not available.
    const double pre_command_j5 = getJoint5Position();
    const bool pre_command_position_available = (pre_command_j5 >= -0.5);

    ApproachParams approach_params;
    approach_params.inter_joint_delay = inter_joint_delay_.load();
    approach_params.min_sleep_time = min_sleep_time_for_motor_motion_;
    approach_params.skip_j4 = skip_j4_in_approach_;
    approach_params.position_wait_mode = position_wait_mode_;
    approach_params.position_feedback_timeout = position_feedback_timeout_sec_;
    approach_params.position_feedback_tolerance = 0.01;
    approach_params.enable_l3_idle_parking = enable_l3_idle_parking_;
    approach_params.j3_parking_position = joint3_parking_position_;

    bool motors_ok_approach = trajectory_executor_->executeApproach(plan_result.trajectory, approach_params);

    // j5_start marks when J5 command was issued (last action in executeApproach).
    // Used by EE timing code below for position-based and sequential modes.
    auto j5_start = std::chrono::steady_clock::now();

    // Copy sub-phase timings back for JSON logging
    approach_j4_ms_ = static_cast<int64_t>(trajectory_executor_->getApproachJ4Ms());
    approach_j3_ms_ = static_cast<int64_t>(trajectory_executor_->getApproachJ3Ms());
    approach_j5_ms_ = static_cast<int64_t>(trajectory_executor_->getApproachJ5Ms());

    RCLCPP_INFO(node_->get_logger(), "      🎯 [TIMING] Approach motors: J4=%ldms J3=%ldms J5=%ldms",
                approach_j4_ms_, approach_j3_ms_, approach_j5_ms_);

    if (!motors_ok_approach) {
        RCLCPP_WARN(node_->get_logger(), "❌ Approach motor commanding failed");
        if (duration_ms) {
            *duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start_time).count();
        }
        return false;
    }

    // ═══════════════════════════════════════════════════════════════
    // START JOINT5 MOVEMENT (NON-BLOCKING) + END EFFECTOR TIMING
    // Two modes controlled by use_dynamic_ee_prestart_ parameter:
    //   false (default): EE starts AFTER joint5 reaches position + stability delay
    //   true (dynamic):  EE starts when joint5 is ee_start_distance_ from target position
    // ═══════════════════════════════════════════════════════════════
    // NOTE: J5 command already sent by TrajectoryExecutor (non-blocking)

    // Calculate actual travel time for joint5
    const double l5_extension_distance = joint5_cmd - joint5_init_.homing_position;
    const double l5_travel_time = std::abs(l5_extension_distance) / joint5_init_.joint5_vel_limit;

    RCLCPP_DEBUG(node_->get_logger(), "[EE] Approach: L5 extension=%.3fm, velocity=%.2fm/s, travel_time=%.3fs",
                l5_extension_distance, joint5_init_.joint5_vel_limit, l5_travel_time);

    if (use_dynamic_ee_prestart_) {
        // ═══════════════════════════════════════════════════════════════
        // DYNAMIC EE MODE (POSITION-BASED) - EE spans L5 forward AND backward motion
        // Uses position monitoring instead of time-based calculation:
        //   1. L5 starts moving forward (non-blocking command sent above)
        //   2. Monitor /joint_states until J5 is ee_start_distance_ from target
        //   3. Turn EE ON (L5 still moving)
        //   4. Wait until J5 reaches target position
        //   5. Return from this function (EE stays ON)
        //   6. executeRetreatTrajectory() starts L5 retract
        //   7. Monitor position, turn EE OFF when J5 retracts ee_stop_distance_
        // This allows cotton fibers to be pulled properly during retract
        // ═══════════════════════════════════════════════════════════════

        // Store cotton position for retreat phase EE shutoff
        last_cotton_position_ = joint5_cmd;

        const double ee_trigger_position = joint5_cmd - static_cast<double>(ee_start_distance_);
        const double position_tolerance = 0.005;  // 5mm tolerance for "reached"
        const double max_movement_threshold = 0.010;  // 10mm (used for larger moves)

        // Give motor time to start + spin to get fresh position data
        // Motor command was just sent (non-blocking), need to wait for:
        // 1. Motor to actually start moving (CAN command latency ~50-100ms)
        // 2. Position feedback to update in /joint_states (published at 10Hz = 100ms)
        // BLOCKING_SLEEP_OK: main-thread motor start + CAN latency wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(200));

        // Executor thread continuously processes callbacks — position data arrives
        // via /joint_states subscription without needing manual spin_some() calls.
        // BLOCKING_SLEEP_OK: main-thread motor start + CAN latency wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(100));

        // Use pre-command position as the baseline when available.
        // This prevents the "started monitoring too late" case for short moves.
        double starting_j5 = pre_command_position_available ? pre_command_j5 : getJoint5Position();
        bool position_available = (starting_j5 >= -0.5);  // -1.0 means not available

        if (!position_available) {
            // Position not available - /joint_states not publishing joint5?
            // Fall back to time-based mode
            RCLCPP_WARN(node_->get_logger(), "[EE] DYNAMIC MODE: J5 position NOT available! Falling back to SEQUENTIAL mode");
            starting_j5 = joint5_init_.homing_position;

            // Use time-based fallback (same as sequential mode but without stability delay)
            double remaining_travel_time = l5_travel_time - 0.3;  // Already waited 300ms
            if (remaining_travel_time > 0) {
                RCLCPP_DEBUG(node_->get_logger(), "[EE] Time-based fallback: waiting %.2fs for J5 to reach cotton", remaining_travel_time);
                // BLOCKING_SLEEP_OK: main-thread time-based travel fallback — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(
                    std::chrono::milliseconds(static_cast<int>(remaining_travel_time * 1000)));
            }

            // Turn on EE at cotton position
            if (end_effector_enable_ && gpio_control_ && areMotorsAvailable()) {
                gpio_control_->set_end_effector_direction(true);
                gpio_control_->end_effector_control(true);
                recovery_manager_->incrementEeActivations();
                capture_sequence_->markEeActive();
                RCLCPP_DEBUG(node_->get_logger(), "[EE] Time-based fallback: EE started at cotton position");

                // Dwell time at cotton
                if (ee_runtime_during_l5_forward_movement_ > 0.0) {
                    RCLCPP_DEBUG(node_->get_logger(), "[EE] Time-based fallback: Dwelling for %.2fs",
                                ee_runtime_during_l5_forward_movement_.load());
                    // BLOCKING_SLEEP_OK: main-thread end-effector dwell — reviewed 2026-03-14
                    yanthra_move::utilities::blockingThreadSleep(
                        std::chrono::milliseconds(static_cast<int>(ee_runtime_during_l5_forward_movement_ * 1000)));
                }
            }
        } else {
            // Position available - use position-based monitoring
            RCLCPP_DEBUG(node_->get_logger(), "[EE] DYNAMIC MODE: start=%.3fm, target=%.3fm, EE trigger=%.3fm",
                        starting_j5, joint5_cmd, ee_trigger_position);

            const bool moving_forward = (joint5_cmd >= starting_j5);

            // Expected movement (used to avoid false TIMEOUTs on very short moves)
            const double expected_move = std::abs(joint5_cmd - starting_j5);
            const bool expected_move_is_tiny = (expected_move <= position_tolerance);

            // Adaptive movement threshold:
            // - For large moves, keep the original 10mm threshold (helps avoid stale joint_states false-exit)
            // - For short moves (<10mm), lower the threshold so we don't wait out the full timeout
            double movement_threshold = max_movement_threshold;
            if (expected_move < max_movement_threshold) {
                movement_threshold = expected_move * 0.5;
                if (movement_threshold < 0.001) {  // 1mm floor to avoid noise
                    movement_threshold = 0.001;
                }
            }

            // Dynamic timeout: tie to expected travel time so worst-case does not become a fixed 10 seconds.
            // Still keep a reasonable minimum to tolerate /joint_states (10Hz) and CAN latency.
            double expected_travel_sec = 0.0;
            if (joint5_init_.joint5_vel_limit > 1e-6) {
                expected_travel_sec = expected_move / joint5_init_.joint5_vel_limit;
            }
            double monitor_timeout_sec = expected_travel_sec + 1.0;  // 1s margin
            if (monitor_timeout_sec < 2.0) monitor_timeout_sec = 2.0;
            if (monitor_timeout_sec > 6.0) monitor_timeout_sec = 6.0;

            RCLCPP_DEBUG(node_->get_logger(),
                        "[EE] Dynamic: expected_move=%.2fmm, threshold=%.2fmm, moving_forward=%d, timeout=%.2fs",
                        expected_move * 1000.0, movement_threshold * 1000.0, moving_forward ? 1 : 0, monitor_timeout_sec);

            // Monitor J5 position until we should start EE
            auto monitor_start = std::chrono::steady_clock::now();
            const auto monitor_timeout = std::chrono::duration<double>(monitor_timeout_sec);
            bool ee_started = false;
            bool motor_started_moving = false;
            int loop_count = 0;
            int no_data_count = 0;  // Track consecutive reads without valid data

            // Use faster polling (10ms) to catch the trigger point more accurately
            // Motor moves ~200mm/s, so 10ms = ~2mm movement per poll
            const int poll_interval_ms = 10;

            if (end_effector_enable_ && gpio_control_ && areMotorsAvailable()) {
                // Phase 1: Wait until J5 reaches ee_trigger_position, then start EE
                while (std::chrono::steady_clock::now() - monitor_start < monitor_timeout) {
                    // Executor thread delivers fresh /joint_states data via subscription
                    double current_j5 = getJoint5Position();
                    loop_count++;

                    // Log every 100 iterations (~1s) for debugging - reduced verbosity
                    if (loop_count % 100 == 0) {
                        RCLCPP_DEBUG(node_->get_logger(), "[EE] Monitoring: pos=%.3fm, trigger=%.3fm, target=%.3fm",
                                    current_j5, ee_trigger_position, joint5_cmd);
                    }

                    if (current_j5 < -0.5) {
                        // Position not available (returns -1.0)
                        no_data_count++;
                        if (no_data_count > 100) {  // 100*10ms = 1 second of no data
                            RCLCPP_WARN(node_->get_logger(), "[EE] Dynamic: Lost position data! Aborting position monitoring");
                            break;
                        }
                        // Sleep to prevent tight busy-loop when no data available
                        // BLOCKING_SLEEP_OK: main-thread position poll — reviewed 2026-03-14
                        std::this_thread::sleep_for(std::chrono::milliseconds(poll_interval_ms));
                        continue;
                    }
                    no_data_count = 0;  // Reset counter when we get valid data

                    // Check if motor has started moving.
                    // For short moves, use adaptive threshold to avoid waiting out the full timeout.
                    if (!motor_started_moving && std::abs(current_j5 - starting_j5) >= movement_threshold) {
                        motor_started_moving = true;
                        RCLCPP_DEBUG(node_->get_logger(), "[EE] Dynamic: Motor moving (pos=%.3fm, start=%.3fm)",
                                    current_j5, starting_j5);
                    }

                    // Check if J5 has reached the EE trigger point
                    const bool trigger_reached = moving_forward ? (current_j5 >= ee_trigger_position)
                                                                : (current_j5 <= ee_trigger_position);
                    if (trigger_reached && !ee_started) {
                        RCLCPP_INFO(node_->get_logger(), "[EE] Dynamic: J5 at %.3fm, starting EE (%.1fmm from cotton)",
                                    current_j5, std::abs(joint5_cmd - current_j5) * 1000.0);
                        gpio_control_->set_end_effector_direction(true);  // true = CLOCKWISE
                        gpio_control_->end_effector_control(true);        // true = ON
                        recovery_manager_->incrementEeActivations();
                        capture_sequence_->markEeActive();
                        ee_started = true;
                    }

                    // Check if J5 has reached final cotton position
                    // IMPORTANT:
                    // - For large moves, require observed motion before declaring success (avoid stale joint_states)
                    // - For very short moves, allow success without waiting for >=movement_threshold
                    const bool target_reached = moving_forward ? (current_j5 >= joint5_cmd - position_tolerance)
                                                              : (current_j5 <= joint5_cmd + position_tolerance);
                    if ((motor_started_moving || expected_move_is_tiny) && target_reached) {
                        RCLCPP_DEBUG(node_->get_logger(), "[EE] Dynamic: J5 reached target (%.3fm), ee_started=%d",
                                    current_j5, ee_started ? 1 : 0);
                        break;
                    }

                    // BLOCKING_SLEEP_OK: main-thread position poll — reviewed 2026-03-14
                    yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(poll_interval_ms));
                }

                // Log if we exited due to timeout
                if (std::chrono::steady_clock::now() - monitor_start >= monitor_timeout) {
                    RCLCPP_WARN(node_->get_logger(), "[EE] Dynamic: Position monitoring TIMEOUT! loops=%d, last_pos=%.3fm",
                                loop_count, getJoint5Position());
                }

                // If EE wasn't started during position monitoring (e.g., short move), start it now
                if (!ee_started && end_effector_enable_ && gpio_control_) {
                    RCLCPP_WARN(node_->get_logger(), "[EE] Dynamic: EE not triggered during monitoring, starting now");
                    gpio_control_->set_end_effector_direction(true);
                    gpio_control_->end_effector_control(true);
                    recovery_manager_->incrementEeActivations();
                    capture_sequence_->markEeActive();
                }

                // DWELL TIME: Let EE run at cotton position before retreat
                // This is equivalent to ee_runtime_during_l5_forward_movement_ in sequential mode
                auto j5_target_time = std::chrono::steady_clock::now();
                if (ee_runtime_during_l5_forward_movement_ > 0.0) {
                    RCLCPP_DEBUG(node_->get_logger(), "[EE] Dynamic: Dwelling at cotton for %.2fs",
                                ee_runtime_during_l5_forward_movement_.load());
                    // BLOCKING_SLEEP_OK: main-thread end-effector dwell — reviewed 2026-03-14
                    yanthra_move::utilities::blockingThreadSleep(
                        std::chrono::milliseconds(static_cast<int>(ee_runtime_during_l5_forward_movement_ * 1000)));
                }

                RCLCPP_DEBUG(node_->get_logger(), "[EE] Dynamic: Dwell complete, EE stays ON for retract");

                // Log J5/EE approach timing breakdown
                auto j5_travel_ms = std::chrono::duration_cast<std::chrono::milliseconds>(j5_target_time - j5_start).count();
                auto dwell_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - j5_target_time).count();
                if (ee_started) {
                    auto ee_pretravel_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                        capture_sequence_->getEeOnSince() - j5_start).count();
                    auto ee_overlap_ms = j5_travel_ms - ee_pretravel_ms;
                    RCLCPP_INFO(node_->get_logger(),
                        "      🎯 [TIMING] J5+EE breakdown: j5_travel=%ldms, ee_pretravel=%ldms, ee_overlap=%ldms, ee_dwell=%ldms",
                        j5_travel_ms, ee_pretravel_ms, ee_overlap_ms, dwell_ms);
                } else {
                    RCLCPP_INFO(node_->get_logger(),
                        "      🎯 [TIMING] J5+EE breakdown: j5_travel=%ldms, ee_pretravel=n/a, ee_overlap=0ms, ee_dwell=%ldms",
                        j5_travel_ms, dwell_ms);
                }
            } else if (end_effector_enable_ && gpio_control_ && !areMotorsAvailable()) {
                RCLCPP_WARN(node_->get_logger(), "[EE] Dynamic: Motors NOT available - skipping EE activation");
                // Still need to wait for J5 to complete - use time-based fallback
                // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(
                    std::chrono::milliseconds(static_cast<int>(l5_travel_time * 1000)));
            } else if (end_effector_enable_) {
                RCLCPP_WARN(node_->get_logger(), "[EE] Dynamic: gpio_control_ is null; using time-based wait");
                // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(
                    std::chrono::milliseconds(static_cast<int>(l5_travel_time * 1000)));
            } else {
                RCLCPP_DEBUG(node_->get_logger(), "[EE] Dynamic: end_effector_enable_=false; using time-based wait");
                // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(
                    std::chrono::milliseconds(static_cast<int>(l5_travel_time * 1000)));
            }
        }  // end else (position_available)
    } else {
        // ═══════════════════════════════════════════════════════════════
        // SEQUENTIAL MODE (current default behavior)
        // EE starts AFTER joint5 reaches position + stability delay
        // ═══════════════════════════════════════════════════════════════
        RCLCPP_DEBUG(node_->get_logger(), "[EE] SEQUENTIAL MODE: Waiting %.3fs for joint5 to reach position...", l5_travel_time);
        // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(l5_travel_time * 1000)));

        // Add configurable delay AFTER joint5 completes for stability
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Sequential: Joint5 reached position. Waiting %.3fs for stability...", ee_post_joint5_delay_.load());
        // BLOCKING_SLEEP_OK: main-thread stability delay — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(ee_post_joint5_delay_ * 1000)));

        // NOW activate end effector after joint5 is fully at position and stable
        // SAFETY: Only activate if motors are actually available
        if (end_effector_enable_) {
            if (gpio_control_ && areMotorsAvailable()) {
                RCLCPP_DEBUG(node_->get_logger(), "[EE] Sequential: Joint5 stable, now setting EE direction CLOCKWISE and turning ON");
                gpio_control_->set_end_effector_direction(true);  // true = CLOCKWISE
                gpio_control_->end_effector_control(true);        // true = ON
                recovery_manager_->incrementEeActivations();  // Track activation
                capture_sequence_->markEeActive();

                RCLCPP_DEBUG(node_->get_logger(), "[EE] Sequential: letting EE run for %.3fs",
                            ee_runtime_during_l5_forward_movement_.load());
                // BLOCKING_SLEEP_OK: main-thread end-effector dwell — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(
                    std::chrono::milliseconds(static_cast<int>(ee_runtime_during_l5_forward_movement_ * 1000)));

                // Turn off end effector after runtime
                RCLCPP_DEBUG(node_->get_logger(), "[EE] Sequential: turning OFF end effector after %.3fs runtime",
                            ee_runtime_during_l5_forward_movement_.load());
                gpio_control_->end_effector_control(false);  // false = OFF
                capture_sequence_->markEeInactive();
                ee_total_on_ms_ += std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - capture_sequence_->getEeOnSince()).count();
            } else if (gpio_control_ && !areMotorsAvailable()) {
                RCLCPP_WARN(node_->get_logger(), "[EE] Sequential: Motors NOT available - skipping EE activation (no point grabbing air!)");
            } else {
                RCLCPP_WARN(node_->get_logger(), "[EE] Sequential: gpio_control_ is null; skipping EE activation");
            }
        } else {
            RCLCPP_DEBUG(node_->get_logger(), "[EE] Sequential: end_effector_enable_=false; skipping EE activation");
        }
    }

    auto j5_end = std::chrono::steady_clock::now();
    auto j5_ee_duration = std::chrono::duration_cast<std::chrono::milliseconds>(j5_end - j5_start).count();
    RCLCPP_INFO(node_->get_logger(), "      🎯 [TIMING] J5+EE approach motion: %ldms", j5_ee_duration);

    auto cmd_end = std::chrono::steady_clock::now();
    auto total_cmd_time = std::chrono::duration_cast<std::chrono::milliseconds>(cmd_end - cmd_start).count();

    RCLCPP_DEBUG(node_->get_logger(), "   📊 Sequential motion timing: j3=%ldms, j4=%ldms, j5+ee=%ldms, total=%ldms",
                approach_j3_ms_, approach_j4_ms_, j5_ee_duration, total_cmd_time);

    // Position feedback verification (when mode is "feedback" — the only mode that uses MotionController-level polling)
    // In "service" mode, joint_move already confirmed arrival via JointPositionCommand service — skip double-waiting.
    // In "blind_sleep" mode, no feedback available — skip.
    if (position_wait_mode_ == "feedback") {
        RCLCPP_DEBUG(node_->get_logger(), "   📍 Position feedback: verifying joint positions...");

        bool j3_ok = waitForPositionFeedback("joint3", joint3_cmd);
        bool j4_ok = waitForPositionFeedback("joint4", joint4_cmd);
        bool j5_ok = waitForPositionFeedback("joint5", joint5_cmd);

        if (!j3_ok || !j4_ok || !j5_ok) {
            std::string failed_joints;
            if (!j3_ok) failed_joints += "joint3 ";
            if (!j4_ok) failed_joints += "joint4 ";
            if (!j5_ok) failed_joints += "joint5 ";
            RCLCPP_WARN(node_->get_logger(), "   ⚠️  Position feedback: %s did not reach target within timeout!",
                        failed_joints.c_str());
        } else {
            RCLCPP_DEBUG(node_->get_logger(), "   ✅ Position feedback: all joints verified");
        }
    }


    auto end_time = std::chrono::steady_clock::now();
    auto total_time = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();
    RCLCPP_INFO(node_->get_logger(), "🦾 Approach: %ldms (j4→j3→j5+EE)", total_time);
    if (duration_ms) {
        *duration_ms = total_time;
    }
    return true;
}
bool MotionController::executeCaptureSequence(int64_t* duration_ms) {
    auto capture_start = std::chrono::steady_clock::now();
    RCLCPP_DEBUG(node_->get_logger(), "Executing cotton capture sequence");

    // NOTE: This function is currently NOT used in the cotton picking flow.
    // End effector activation happens in executeApproachTrajectory() during L5 forward motion.
    // Compressor activation for cotton drop happens in executeRetreatTrajectory().
    //
    // Legacy vacuum-based method references removed (replaced with compressor push method):
    // - OLD: vacuum_pump_control() to pull cotton
    // - NEW: end_effector grabs cotton mechanically, compressor pushes it out at home

    // Wait for capture and detection (if this function gets used in future)
    // BLOCKING_SLEEP_OK: main-thread capture wait — reviewed 2026-03-14
    yanthra_move::utilities::blockingThreadSleep(
        std::chrono::milliseconds(static_cast<int>(cotton_capture_detect_wait_time_ * 1000)));

    if (duration_ms) {
        *duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - capture_start).count();
    }
    return true;
}

bool MotionController::executeRetreatTrajectory(bool home_j5, bool home_j3, bool home_j4, int64_t* duration_ms) {
    (void)home_j5;  // J5 always retracts — parameter kept for API consistency
    RCLCPP_DEBUG(node_->get_logger(), "🔙 Executing retreat trajectory - retracting arm to home with cotton");
    auto retreat_start = std::chrono::steady_clock::now();

    // Skip motor commands and GPIO if motors not available
    if (!areMotorsAvailable()) {
        RCLCPP_DEBUG(node_->get_logger(), "⚠️ Motors NOT available - skipping retreat motor commands");
        auto retreat_end = std::chrono::steady_clock::now();
        auto retreat_time = std::chrono::duration_cast<std::chrono::milliseconds>(retreat_end - retreat_start).count();
        RCLCPP_INFO(node_->get_logger(), "🔙 Retreat: %ldms (SKIPPED - no motors)", retreat_time);
        if (duration_ms) {
            *duration_ms = retreat_time;
        }
        return true;
    }

    // In ArUco mode: Only retract joint5 to avoid collisions, keep joint3/joint4 positioned
    // This allows faster corner-to-corner movement without full reset
    if (yanthra_lab_calibration_testing_) {
        RCLCPP_DEBUG(node_->get_logger(), "   ArUco mode: Retracting only joint5 (keeping joint3/joint4 in place)");

        const double joint5_homing = joint5_init_.homing_position;
        if (joint_move_5_) {
            (void)joint_move_5_->move_joint(joint5_homing, false);  // Non-blocking start
        }

        // ═══════════════════════════════════════════════════════════════
        // DYNAMIC EE OFF (POSITION-BASED): Turn off EE when J5 retracts ee_stop_distance_ from cotton
        // In dynamic mode, EE is still running from approach phase
        // ═══════════════════════════════════════════════════════════════
        if (use_dynamic_ee_prestart_ && end_effector_enable_ && gpio_control_) {
            // Position-based EE shutoff: turn off when J5 retracts ee_stop_distance_ from cotton position
            const double ee_shutoff_position = last_cotton_position_ - static_cast<double>(ee_stop_distance_);
            RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat (ArUco): Dynamic mode - EE will turn OFF when J5 < %.3fm",
                        ee_shutoff_position);

            auto monitor_start = std::chrono::steady_clock::now();
            const auto monitor_timeout = std::chrono::seconds(10);
            bool ee_stopped = false;

            while (std::chrono::steady_clock::now() - monitor_start < monitor_timeout) {
                double current_j5 = getJoint5Position();

                if (current_j5 < 0) {
                    // BLOCKING_SLEEP_OK: main-thread position poll — reviewed 2026-03-14
                    yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(20));
                    continue;
                }

                // Turn off EE when J5 has retracted enough
                if (current_j5 <= ee_shutoff_position && !ee_stopped) {
                    RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat (ArUco): J5 at %.3fm, turning EE OFF (retracted %.1fmm from cotton)",
                                current_j5, (last_cotton_position_ - current_j5) * 1000.0);
                    gpio_control_->end_effector_control(false);
                    capture_sequence_->markEeInactive();
                    ee_stopped = true;
                }

                // Check if J5 has reached home (or close to it)
                if (current_j5 <= joint5_homing + 0.005) {
                    RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat (ArUco): J5 reached home (%.3fm)", current_j5);
                    break;
                }

                // BLOCKING_SLEEP_OK: main-thread position poll — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(20));
            }

            // Safety: ensure EE is off if not stopped during monitoring
            if (!ee_stopped) {
                RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat (ArUco): EE not stopped during monitoring, turning OFF now");
                gpio_control_->end_effector_control(false);
                capture_sequence_->markEeInactive();
            }
        } else if (end_effector_enable_ && gpio_control_) {
            // Sequential mode - EE already off, just ensure it's off
            RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat (ArUco): Sequential mode - ensuring EE is OFF");
            gpio_control_->end_effector_control(false);
            capture_sequence_->markEeInactive();
            // Wait for L5 to complete retraction
            // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
            yanthra_move::utilities::blockingThreadSleep(
                std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
        } else {
            // No EE control - just wait for L5 to complete
            // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
            yanthra_move::utilities::blockingThreadSleep(
                std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
        }

        RCLCPP_DEBUG(node_->get_logger(), "✅ Retreat completed - joint5 retracted, ready for next corner");

        // Add stabilization delay before cotton drop (configurable)
        if (cotton_settle_delay_ > 0.0) {
            RCLCPP_DEBUG(node_->get_logger(), "      ⏸  Waiting %.3fs for cotton to settle before drop...", cotton_settle_delay_.load());
            // BLOCKING_SLEEP_OK: main-thread cotton handling delay — reviewed 2026-03-14
            yanthra_move::utilities::blockingThreadSleep(
                std::chrono::milliseconds(static_cast<int>(cotton_settle_delay_ * 1000)));
        }

        // Activate compressor for configurable duration after L5 returns to home
        // Only if motors are available (arm actually moved and grabbed cotton)
        if (gpio_control_ && compressor_burst_duration_ > 0.0 && areMotorsAvailable()) {
            RCLCPP_DEBUG(node_->get_logger(), "[Compressor] Activating compressor for %.3fs", compressor_burst_duration_.load());
            gpio_control_->compressor_control(true);
            capture_sequence_->markCompressorActive();
            recovery_manager_->incrementCompressorActivations();  // Track activation
            // BLOCKING_SLEEP_OK: main-thread cotton handling delay — reviewed 2026-03-14
            yanthra_move::utilities::blockingThreadSleep(
                std::chrono::milliseconds(static_cast<int>(compressor_burst_duration_ * 1000)));
            gpio_control_->compressor_control(false);
            capture_sequence_->markCompressorInactive();
            RCLCPP_DEBUG(node_->get_logger(), "[Compressor] Compressor deactivated");
        } else if (gpio_control_ && compressor_burst_duration_ > 0.0 && !areMotorsAvailable()) {
            RCLCPP_DEBUG(node_->get_logger(), "[Compressor] Motors NOT available - skipping compressor (nothing to eject)");
        }

        // ═══════════════════════════════════════════════════════════════
        // L3 IDLE PARKING (ArUco mode): Move L3 to parking after last corner
        // ═══════════════════════════════════════════════════════════════
        if (enable_l3_idle_parking_ && home_j4) {
            RCLCPP_INFO(node_->get_logger(), "🌡️  Moving L3 to parking position for idle temperature reduction...");
            moveL3ToParking();
        }

        auto retreat_end = std::chrono::steady_clock::now();
        auto retreat_time = std::chrono::duration_cast<std::chrono::milliseconds>(retreat_end - retreat_start).count();
        RCLCPP_INFO(node_->get_logger(), "🔙 Retreat: %ldms (ArUco mode)%s", retreat_time,
                    (enable_l3_idle_parking_ && home_j4) ? " (L3 parked)" : "");
        if (duration_ms) {
            *duration_ms = retreat_time;
        }
        return true;
    }

    // ═══════════════════════════════════════════════════════════════
    // RETREAT TO HOME: Full sequence with DYNAMIC EE deactivation
    // This brings arm to home position (where cotton will be dropped)
    // ═══════════════════════════════════════════════════════════════

    // Retreat sub-phase timing variables
    int64_t retreat_j5_ms = 0, retreat_ee_off_ms = 0, retreat_j3_ms = 0, retreat_j4_ms = 0, retreat_compressor_ms = 0;
    bool retreat_all_ok = true;  // Track if all retreat moves succeeded

    // CRITICAL: Capture J5 position BEFORE sending retract command!
    // The motor is fast - if we wait, it will already be at home
    // Executor thread keeps /joint_states subscription data fresh
    double j5_before_retract = getJoint5Position();
    if (j5_before_retract < -0.5) {
        // Position not available yet, use last_cotton_position_ as fallback
        j5_before_retract = last_cotton_position_;
        RCLCPP_WARN(node_->get_logger(), "[EE] Retreat: J5 position not available, using last_cotton_position_=%.3fm", j5_before_retract);
    }
    RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: J5 position BEFORE retract command: %.3fm", j5_before_retract);

    // Step 1: Start retracting joint5 (extension) - pull arm back to home
    auto j5_start = std::chrono::steady_clock::now();
    const double joint5_homing = joint5_init_.homing_position;
    const double joint5_current = j5_before_retract;
    const double l5_retraction_distance = std::abs(joint5_current - joint5_homing);
    const double l5_retraction_time = l5_retraction_distance / joint5_init_.joint5_vel_limit;

    RCLCPP_DEBUG(node_->get_logger(), "   Retracting joint5 to home position: %.3f", joint5_homing);
    RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: J5 retraction: from=%.3fm to=%.3fm, distance=%.3fm, est_time=%.2fs",
                j5_before_retract, joint5_homing, l5_retraction_distance, l5_retraction_time);

    MoveResult r5_retreat = MoveResult::SUCCESS;  // Track J5 retreat result
    if (joint_move_5_) {
        r5_retreat = joint_move_5_->move_joint(joint5_homing, false);  // Non-blocking (EE timing depends on this)
    }

    // ═══════════════════════════════════════════════════════════════
    // DYNAMIC EE DEACTIVATION (POSITION-BASED): Turn off EE when J5 retracts ee_stop_distance_ from cotton
    // Dynamic mode: EE still running from approach, monitor position to turn off
    // Sequential mode: EE already off from approach, just ensure it's off
    // ═══════════════════════════════════════════════════════════════
    auto ee_off_start = std::chrono::steady_clock::now();
    if (use_dynamic_ee_prestart_ && end_effector_enable_ && gpio_control_) {
        // DYNAMIC MODE: EE is still ON from approach phase
        // Motor is VERY FAST (~2.5m/s actual), position feedback can't keep up
        // Use TIME-BASED control for retreat instead of position monitoring

        // Calculate when to turn EE off based on desired stop distance
        // EE should stay on until J5 retracts ee_stop_distance_ from cotton
        const double total_retract_distance = j5_before_retract - joint5_homing;
        const double ee_on_distance = std::min(static_cast<double>(ee_stop_distance_), total_retract_distance);
        const double ee_off_distance = total_retract_distance - ee_on_distance;

        // Use actual motor speed (measured ~212mm/s from logs: 254mm in 1.2s)
        // Lower value = EE stays ON longer during retreat
        const double actual_motor_speed = 0.20;  // 200mm/s = 0.20m/s (tuned for retreat EE timing)
        const double ee_on_time_ms = (ee_on_distance / actual_motor_speed) * 1000.0;

        RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: TIME-BASED MODE j5=%.3fm->%.3fm, EE on for %.0fmm (%.0fms), then OFF for remaining %.0fmm",
                    j5_before_retract, joint5_homing, ee_on_distance * 1000.0, ee_on_time_ms, ee_off_distance * 1000.0);

        if (total_retract_distance < 0.020) {
            // Very short retract, just turn EE off
            RCLCPP_WARN(node_->get_logger(), "[EE] Retreat: Very short retract (%.0fmm), turning EE OFF immediately", total_retract_distance * 1000.0);
            gpio_control_->end_effector_control(false);
            capture_sequence_->markEeInactive();
            ee_total_on_ms_ += std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - capture_sequence_->getEeOnSince()).count();
        } else {
            // Keep EE ON for calculated time, then turn OFF
            // EE is already ON from approach phase
            int ee_on_time_int = static_cast<int>(ee_on_time_ms);
            if (ee_on_time_int < 50) ee_on_time_int = 50;  // Minimum 50ms

            RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: Keeping EE ON for %dms while J5 retracts first %.0fmm...",
                        ee_on_time_int, ee_on_distance * 1000.0);

            // BLOCKING_SLEEP_OK: main-thread end-effector dwell — reviewed 2026-03-14
            yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(ee_on_time_int));

            // Now turn EE OFF
            RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: Turning EE OFF (J5 retracted ~%.0fmm from cotton)",
                        ee_on_distance * 1000.0);
            gpio_control_->end_effector_control(false);
            capture_sequence_->markEeInactive();
            ee_total_on_ms_ += std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - capture_sequence_->getEeOnSince()).count();

            // Wait for remaining retract to complete
            const double remaining_time_ms = (ee_off_distance / actual_motor_speed) * 1000.0;
            if (remaining_time_ms > 50) {
                RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: Waiting %.0fms for J5 to reach home...", remaining_time_ms);
                // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
                yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(static_cast<int>(remaining_time_ms)));
            }
        }
    } else if (end_effector_enable_ && gpio_control_) {
        // SEQUENTIAL MODE: EE was already turned off in approach, ensure it stays off
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: Sequential mode - ensuring EE is OFF");
        gpio_control_->end_effector_control(false);
        capture_sequence_->markEeInactive();
        // Wait for L5 to complete retraction
        // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
    } else if (!gpio_control_) {
        RCLCPP_WARN(node_->get_logger(), "[EE] Retreat: gpio_control_ is null; skipping EE deactivation");
        // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
    } else {
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Retreat: end_effector_enable_=false; skipping EE deactivation");
        // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
    }
    retreat_ee_off_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - ee_off_start).count();
    RCLCPP_INFO(node_->get_logger(), "🔙 [TIMING] Retreat EE deactivation: %ldms", retreat_ee_off_ms);

    retreat_j5_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - j5_start).count();
    RCLCPP_INFO(node_->get_logger(), "🔙 [TIMING] Retreat J5 retract: %ldms", retreat_j5_ms);

    recordMoveResult(5, r5_retreat);
    if (r5_retreat != MoveResult::SUCCESS) {
        RCLCPP_WARN(node_->get_logger(), "[MOVE] J5 retreat failed (result=%d)", static_cast<int>(r5_retreat));
    }

    // Step 2: J3 homing / eject sequence
    if (enable_cotton_eject_) {
        // Eject sub-sequence: J3 → eject position (blocking w/ CAN feedback) → M2 reverse → optional J3 home.
        // If home_j3=true (last cotton at this J4 scan position), J3 homes after eject so the
        // camera FOV is clear before the arm moves to the next J4 position.
        // If home_j3=false (mid-cycle cotton), J3 stays at eject position for speed.
        auto j3_start = std::chrono::steady_clock::now();
        bool j3_eject_ok = false;  // Track whether J3 reached eject position
        RCLCPP_DEBUG(node_->get_logger(), "      ⏸  Waiting %.3fs before J3 eject move...", inter_joint_delay_.load());
        // BLOCKING_SLEEP_OK: main-thread inter-joint delay — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(inter_joint_delay_ * 1000)));

        // Move J3 to eject position — blocking (wait=true) uses position_wait_mode="service"
        // to receive real CAN position feedback before continuing.
        RCLCPP_INFO(node_->get_logger(), "🌀 [EJECT] Moving J3 to eject position: %.3f rot (waiting for CAN feedback, timeout %.2fs)",
            j3_eject_position_, j3_eject_feedback_timeout_sec_);
        auto j3_move_start = std::chrono::steady_clock::now();
        if (joint_move_3_) {
            auto result_j3_eject = joint_move_3_->move_joint(j3_eject_position_, true);  // Blocking: waits for CAN position feedback
            if (result_j3_eject != MoveResult::SUCCESS) {
                RCLCPP_WARN(node_->get_logger(),
                    "[MOVE] Joint 3 eject move failed (result=%d, target=%.4f)",
                    static_cast<int>(result_j3_eject), j3_eject_position_);
            }
            recordMoveResult(3, result_j3_eject);
            j3_eject_ok = (result_j3_eject == MoveResult::SUCCESS);
        }
        auto j3_elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - j3_move_start).count();
        if (j3_elapsed_ms >= static_cast<long>(j3_eject_feedback_timeout_sec_ * 1000)) {
            RCLCPP_WARN(node_->get_logger(),
                "🌀 [EJECT] J3 feedback timed out after %ldms (timeout %.2fs) — target=%.3f rot — firing M2 anyway (graceful degradation)",
                j3_elapsed_ms, j3_eject_feedback_timeout_sec_, j3_eject_position_);
        } else {
            RCLCPP_INFO(node_->get_logger(),
                "🌀 [EJECT] J3 arrived at eject position in %ldms — holding at %.3f rot for pick cycle",
                j3_elapsed_ms, j3_eject_position_);
        }

        // Only fire M2 if J3 successfully reached eject position
        if (j3_eject_ok) {
            // Run M2 in reverse to eject cotton
            RCLCPP_INFO(node_->get_logger(), "🌀 [EJECT] Running M2 reverse for %.0fms", ee_motor2_eject_duration_ms_);
            if (gpio_control_) {
                gpio_control_->end_effector_drop_eject(static_cast<int>(ee_motor2_eject_duration_ms_));
            }

            // M2 forward flush: clear residual cotton fibers from belt entrance after reverse eject
            RCLCPP_INFO(node_->get_logger(), "🌀 [EJECT] Running M2 forward flush for %.0fms", ee_motor2_forward_flush_ms_);
            if (gpio_control_) {
                gpio_control_->end_effector_drop_control(true);   // DROP_EEF: M2 forward
                // BLOCKING_SLEEP_OK: main-thread end-effector dwell — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(ee_motor2_forward_flush_ms_)));
                gpio_control_->end_effector_drop_control(false);  // STOP_EEF: M2 stop
            }
        } else {
            RCLCPP_WARN(node_->get_logger(),
                "🌀 [EJECT] Skipping M2 eject — J3 failed to reach eject position");
        }

        // After eject: home J3 if this is the last cotton at this J4 scan position,
        // so the camera FOV is clear before the arm moves to the next J4 position.
        // For mid-cycle cottons, J3 stays at eject position (faster — no unnecessary travel).
        if (home_j3) {
            RCLCPP_INFO(node_->get_logger(), "🌀 [EJECT] Last cotton at scan position — homing J3 after eject");
            const double joint3_homing = joint3_init_.homing_position;
            if (joint_move_3_) {
                auto j3_result = joint_move_3_->move_joint(joint3_homing, true);  // Blocking: waits for CAN feedback
                recordMoveResult(3, j3_result);
                retreat_all_ok = (j3_result == MoveResult::SUCCESS) && retreat_all_ok;
            }
            RCLCPP_INFO(node_->get_logger(), "🌀 [EJECT] J3 homed to %.3f rot after eject", joint3_homing);
        } else {
            RCLCPP_INFO(node_->get_logger(), "🌀 [EJECT] J3 holding at eject position %.3f rot — next pick in same scan position",
                j3_eject_position_);
        }

        retreat_j3_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - j3_start).count();
        RCLCPP_INFO(node_->get_logger(), "🔙 [TIMING] Retreat J3 eject: %ldms", retreat_j3_ms);
    } else if (home_j3) {
        auto j3_start = std::chrono::steady_clock::now();
        // Add delay before starting joint3 homing
        RCLCPP_DEBUG(node_->get_logger(), "      ⏸  Waiting %.3fs before joint3 homing...", inter_joint_delay_.load());
        // BLOCKING_SLEEP_OK: main-thread inter-joint delay — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(inter_joint_delay_ * 1000)));

        // Return joint3 (rotation) to home — clears arm from camera FOV
        const double joint3_homing = joint3_init_.homing_position;
        RCLCPP_DEBUG(node_->get_logger(), "   Retracting joint3 to home position: %.3f", joint3_homing);

        if (joint_move_3_) {
            auto j3_result = joint_move_3_->move_joint(joint3_homing, true);  // Blocking: waits for CAN feedback
            recordMoveResult(3, j3_result);
            retreat_all_ok = (j3_result == MoveResult::SUCCESS) && retreat_all_ok;
        }
        retreat_j3_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - j3_start).count();
        RCLCPP_INFO(node_->get_logger(), "🔙 [TIMING] Retreat J3 home: %ldms", retreat_j3_ms);
    } else {
        RCLCPP_DEBUG(node_->get_logger(), "   ⏩ Skipping J3 homing — keeping position for next pick");
    }

    // Step 3: Conditional J4 homing based on home_j4 flag
    if (home_j4) {
        auto j4_start = std::chrono::steady_clock::now();
        // Add delay before joint4 homing
        RCLCPP_DEBUG(node_->get_logger(), "      ⏸  Waiting %.3fs before joint4 homing...", inter_joint_delay_.load());
        // BLOCKING_SLEEP_OK: main-thread inter-joint delay — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(inter_joint_delay_ * 1000)));

        // Return joint4 (left/right) to center
        const double joint4_homing = joint4_init_.homing_position;
        RCLCPP_DEBUG(node_->get_logger(), "   Retracting joint4 to home position: %.3f", joint4_homing);

        if (joint_move_4_) {
            auto r4 = joint_move_4_->move_joint(joint4_homing, false);  // Non-blocking
            recordMoveResult(4, r4);
            if (r4 != MoveResult::SUCCESS) {
                RCLCPP_WARN(node_->get_logger(), "[MOVE] J4 retreat homing failed (result=%d)", static_cast<int>(r4));
            }
        }
        // BLOCKING_SLEEP_OK: main-thread motor travel wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
        retreat_j4_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - j4_start).count();
        RCLCPP_INFO(node_->get_logger(), "🔙 [TIMING] Retreat J4 home: %ldms", retreat_j4_ms);
    } else {
        RCLCPP_DEBUG(node_->get_logger(), "   ⏩ Skipping J4 homing — keeping position for scan loop");
    }

    // ═══════════════════════════════════════════════════════════════
    // COTTON DROP: Activate compressor at home position
    // Arm is now at home (= retreat position), so drop cotton here
    // ═══════════════════════════════════════════════════════════════
    auto compressor_start = std::chrono::steady_clock::now();
    RCLCPP_DEBUG(node_->get_logger(), "🏠 Arm now at home position - dropping cotton");

    // Add stabilization delay before cotton drop (configurable)
    if (cotton_settle_delay_ > 0.0) {
        RCLCPP_DEBUG(node_->get_logger(), "      ⏸  Waiting %.3fs for cotton to settle before drop...", cotton_settle_delay_.load());
        // BLOCKING_SLEEP_OK: main-thread cotton handling delay — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(cotton_settle_delay_ * 1000)));
    }

    // Only activate compressor if motors are available (arm actually moved and grabbed cotton)
    if (enable_compressor_eject_ && gpio_control_ && areMotorsAvailable()) {
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Home: 💨 activating compressor to eject cotton");
#ifdef ENABLE_PIGPIO
        gpio_control_->cotton_drop_solenoid_shutter();
        recovery_manager_->incrementCompressorActivations();  // Track compressor activation
#endif
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Home: ✅ cotton ejected, ready for next pick");
    } else if (!enable_compressor_eject_) {
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Home: Compressor eject disabled by config — skipping");
    } else if (gpio_control_ && !areMotorsAvailable()) {
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Home: Motors NOT available - skipping compressor (nothing to eject)");
    } else {
        RCLCPP_WARN(node_->get_logger(), "[EE] Home: gpio_control_ is null; cannot activate compressor");
    }
    retreat_compressor_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - compressor_start).count();
    RCLCPP_INFO(node_->get_logger(), "🔙 [TIMING] Retreat compressor burst: %ldms", retreat_compressor_ms);

    // Retreat sub-phase summary
    RCLCPP_INFO(node_->get_logger(), "🔙 [TIMING] Retreat breakdown: J5=%ldms, EE_off=%ldms, J3=%ldms, J4=%ldms, compressor=%ldms",
        retreat_j5_ms, retreat_ee_off_ms, retreat_j3_ms, retreat_j4_ms, retreat_compressor_ms);

    // Propagate retreat sub-phase timings to member variables for JSON logging
    retreat_j5_ms_ = retreat_j5_ms;
    retreat_ee_off_ms_ = retreat_ee_off_ms;
    retreat_j3_ms_ = retreat_j3_ms;
    retreat_j4_ms_ = retreat_j4_ms;
    retreat_compressor_ms_ = retreat_compressor_ms;

    // ═══════════════════════════════════════════════════════════════
    // L3 IDLE PARKING: Move L3 to parking after last cotton (temperature optimization)
    // SAFETY: Only after J4 has finished homing - J4 is now at home, safe to tilt L3 up
    // ═══════════════════════════════════════════════════════════════
    if (enable_l3_idle_parking_ && home_j4) {
        RCLCPP_INFO(node_->get_logger(), "🌡️  Moving L3 to parking position for idle temperature reduction...");
        moveL3ToParking();
    }

    auto retreat_end = std::chrono::steady_clock::now();
    auto retreat_time = std::chrono::duration_cast<std::chrono::milliseconds>(retreat_end - retreat_start).count();

    // Build homing status string for log
    std::string homing_status;
    if (home_j3 && home_j4) homing_status = " (homed J3+J4)";
    else if (home_j3) homing_status = " (homed J3, skipped J4)";
    else if (home_j4) homing_status = " (skipped J3, homed J4)";
    else homing_status = " (skipped J3+J4)";

    RCLCPP_INFO(node_->get_logger(), "🔙 Retreat+drop: %ldms%s%s", retreat_time,
                homing_status.c_str(),
                (enable_l3_idle_parking_ && home_j4) ? " (L3 parked)" : "");
    if (duration_ms) {
        *duration_ms = retreat_time;
    }
    return retreat_all_ok;
}

bool MotionController::moveToPackingPosition() {
    // NOTE: "Parking" and "homing" are now the same position (simplified 2025-11-28)
    RCLCPP_INFO(node_->get_logger(), "🏠 Moving arm to home/park position");

    bool all_ok = true;

    // Move joints to homing positions in correct sequence: joint5 → joint3 → joint4
    const double joint5_home = joint5_init_.homing_position;
    const double joint3_home = joint3_init_.homing_position;
    const double joint4_home = joint4_init_.homing_position;

    RCLCPP_INFO(node_->get_logger(), "   Commanding: joint3=%.3f, joint4=%.3f, joint5=%.3f", joint3_home, joint4_home, joint5_home);

    // Delegate motor commanding to TrajectoryExecutor
    all_ok = trajectory_executor_->moveToPackingPosition(
        joint3_home, joint5_home, joint4_home, position_wait_mode_);

    // Turn off end effector at home position
    if (end_effector_enable_ && gpio_control_) {
        RCLCPP_DEBUG(node_->get_logger(), "[EE] Home: Turning OFF end effector");
        gpio_control_->end_effector_control(false);
        capture_sequence_->markEeInactive();
    }

    // Turn off compressor at home position
    if (gpio_control_) {
        RCLCPP_DEBUG(node_->get_logger(), "[Compressor] Home: Ensuring compressor is OFF");
        gpio_control_->compressor_control(false);
        capture_sequence_->markCompressorInactive();
    }

    if (all_ok) {
        RCLCPP_INFO(node_->get_logger(), "✅ Arm at home position");
    } else {
        RCLCPP_WARN(node_->get_logger(), "⚠️ Arm homing completed with failures — not all joints reached home");
    }
    return all_ok;
}

void MotionController::executeHeightScan(double min_height, double max_height, double step_size) {
    RCLCPP_INFO(node_->get_logger(), "Executing height scan: min=%.3f, max=%.3f, step=%.3f",
                min_height, max_height, step_size);

    double current_height = min_height;
    int scan_points = 0;

    while (current_height <= max_height && !isEmergencyStopRequested()) {
        RCLCPP_DEBUG(node_->get_logger(), "Scanning at height: %.3f", current_height);

        // Move to scan height and wait
        // BLOCKING_SLEEP_OK: main-thread height scan pause — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(std::chrono::milliseconds(100));

        current_height += step_size;
        scan_points++;
    }

    RCLCPP_INFO(node_->get_logger(), "Height scan completed: %d scan points", scan_points);
}

void MotionController::loadMotionParameters() {
    // Load motion control parameters using helpers
    RCLCPP_INFO(node_->get_logger(), "Loading motion parameters...");

    // Core timing parameters - ALL CONFIGURABLE FROM YAML
    picking_delay_ = loadParamDouble("delays/picking", 0.1);
    min_sleep_time_for_motor_motion_ = loadParamDouble("min_sleep_time_formotor_motion", 0.2);
    inter_joint_delay_ = loadParamDouble("inter_joint_delay", 0.3);
    cotton_settle_delay_ = loadParamDouble("cotton_settle_delay", 0.2);
    cotton_capture_detect_wait_time_ = loadParamDouble("cotton_capture_detect_wait_time", 0.0);
    compressor_burst_duration_ = loadParamDouble("compressor_burst_duration", 0.5);

    // Cotton eject sub-sequence parameters
    enable_cotton_eject_ = loadParamBool("enable_cotton_eject", false);
    enable_compressor_eject_ = loadParamBool("enable_compressor_eject", false);
    j3_eject_position_ = loadParamDouble("j3_eject_position", -0.2);
    ee_motor2_eject_duration_ms_ = loadParamDouble("ee_motor2_eject_duration_ms", 300.0);
    ee_motor2_forward_flush_ms_ = loadParamDouble("ee_motor2_forward_flush_ms", 200.0);
    j3_eject_feedback_timeout_sec_ = loadParamDouble("j3_eject_feedback_timeout_sec", 1.5);

    // End effector timing
    ee_runtime_during_l5_forward_movement_ = loadParamFloat("delays/EERunTimeDuringL5ForwardMovement", 2.0f);
    ee_runtime_during_l5_backward_movement_ = loadParamFloat("delays/EERunTimeDuringL5BackwardMovement", 0.5f);
    ee_runtime_during_reverse_rotation_ = loadParamFloat("delays/EERunTimeDuringReverseRotation", 0.5f);
    ee_post_joint5_delay_ = loadParamFloat("delays/ee_post_joint5_delay", 0.3f);

    // Position-based dynamic EE timing (NEW - preferred over time-based)
    // ee_start_distance: Start EE when J5 is this distance before reaching cotton
    // ee_stop_distance: Stop EE when J5 has retracted this distance from cotton
    ee_start_distance_ = loadParamFloat("delays/ee_start_distance", 0.025f);  // 25mm default
    ee_stop_distance_ = loadParamFloat("delays/ee_stop_distance", 0.050f);    // 50mm default

    // Dynamic EE mode flag
    // false (default) = sequential: EE starts AFTER joint5 reaches position + stability delay
    // true = dynamic: EE uses position-based monitoring to start before J5 reaches target
    use_dynamic_ee_prestart_ = loadParamBool("delays/use_dynamic_ee_prestart", false);

    // End effector enable flag
    end_effector_enable_ = loadParamBool("end_effector_enable", true);

    // If GPIO is unavailable, keep the parameter value but be explicit about behavior.
    // The operational code paths already guard on gpio_control_ and will log skips.
    if (!gpio_control_ && end_effector_enable_) {
        RCLCPP_WARN(node_->get_logger(), "[EE] GPIO control not available - EE/Compressor commands will be skipped (end_effector_enable remains true)");
    }

    // Load joint initialization parameters
    loadJointInitParameters();

    // ═══════════════════════════════════════════════════════════════════════════
    // JOINT4 MULTI-POSITION SCANNING CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════════════
    j4_multipos_config_.enabled = loadParamBool("joint4_multiposition/enabled", true);
    if (j4_multipos_config_.enabled) {
        RCLCPP_INFO(node_->get_logger(), "🔄 Joint4 multi-position scanning ENABLED");

        // Load position array
        if (node_->has_parameter("joint4_multiposition/positions")) {
            j4_multipos_config_.positions = node_->get_parameter("joint4_multiposition/positions").as_double_array();
            RCLCPP_INFO(node_->get_logger(), "   Positions: %zu configured", j4_multipos_config_.positions.size());
            for (size_t i = 0; i < j4_multipos_config_.positions.size(); ++i) {
                RCLCPP_INFO(node_->get_logger(), "     [%zu] %+.3f m (%+.0f mm)",
                           i, j4_multipos_config_.positions[i], j4_multipos_config_.positions[i] * 1000.0);
            }
        } else {
            // Default to 5 positions: -100mm, -50mm, 0mm, +50mm, +100mm
            j4_multipos_config_.positions = {-0.100, -0.050, 0.000, 0.050, 0.100};
            RCLCPP_WARN(node_->get_logger(), "   Using default positions: 5 positions from -100mm to +100mm");
        }

        // Load safety limits
        j4_multipos_config_.safe_min = loadParamDouble("joint4_multiposition/safe_min", -0.175);
        j4_multipos_config_.safe_max = loadParamDouble("joint4_multiposition/safe_max", 0.175);
        RCLCPP_INFO(node_->get_logger(), "   Safety limits: [%.3fm, %.3fm] ([%+.0fmm, %+.0fmm])",
                   j4_multipos_config_.safe_min, j4_multipos_config_.safe_max,
                   j4_multipos_config_.safe_min * 1000.0, j4_multipos_config_.safe_max * 1000.0);

        // Load scan strategy
        if (node_->has_parameter("joint4_multiposition/scan_strategy")) {
            j4_multipos_config_.scan_strategy = node_->get_parameter("joint4_multiposition/scan_strategy").as_string();
        }
        RCLCPP_INFO(node_->get_logger(), "   Scan strategy: %s", j4_multipos_config_.scan_strategy.c_str());

        // Load timing parameters
        j4_multipos_config_.j4_settling_time = loadParamDouble("joint4_multiposition/j4_settling_time", 0.100);
        j4_multipos_config_.detection_settling_time = loadParamDouble("joint4_multiposition/detection_settling_time", 0.050);
        RCLCPP_INFO(node_->get_logger(), "   Settling times: J4=%.0fms, Detection=%.0fms",
                   j4_multipos_config_.j4_settling_time * 1000.0,
                   j4_multipos_config_.detection_settling_time * 1000.0);

        // Load optimization flags
        j4_multipos_config_.early_exit_enabled = loadParamBool("joint4_multiposition/early_exit_enabled", true);
        RCLCPP_INFO(node_->get_logger(), "   Early exit: %s", j4_multipos_config_.early_exit_enabled ? "ENABLED" : "DISABLED");

        // Load error handling strategy
        if (node_->has_parameter("joint4_multiposition/on_j4_failure")) {
            j4_multipos_config_.on_j4_failure = node_->get_parameter("joint4_multiposition/on_j4_failure").as_string();
        }
        RCLCPP_INFO(node_->get_logger(), "   J4 failure handling: %s", j4_multipos_config_.on_j4_failure.c_str());

        // Load stats flags
        j4_multipos_config_.enable_timing_stats = loadParamBool("joint4_multiposition/enable_timing_stats", true);
        j4_multipos_config_.enable_position_stats = loadParamBool("joint4_multiposition/enable_position_stats", true);
        j4_multipos_config_.enable_j4_offset_compensation = loadParamBool("joint4_multiposition/enable_j4_offset_compensation", true);
        RCLCPP_INFO(node_->get_logger(), "   Statistics: timing=%s, position=%s",
                   j4_multipos_config_.enable_timing_stats ? "ON" : "OFF",
                   j4_multipos_config_.enable_position_stats ? "ON" : "OFF");
        RCLCPP_INFO(node_->get_logger(), "   J4 offset compensation: %s",
                   j4_multipos_config_.enable_j4_offset_compensation ? "ENABLED" : "DISABLED");

        // Validate configuration
        if (j4_multipos_config_.positions.empty()) {
            RCLCPP_ERROR(node_->get_logger(), "❌ Joint4 multi-position enabled but no positions configured - DISABLING");
            j4_multipos_config_.enabled = false;
        }

        // Check if any positions exceed safety limits
        bool positions_valid = true;
        for (const auto& pos : j4_multipos_config_.positions) {
            if (pos < j4_multipos_config_.safe_min || pos > j4_multipos_config_.safe_max) {
                RCLCPP_ERROR(node_->get_logger(), "❌ Position %.3fm exceeds safety limits [%.3fm, %.3fm]",
                            pos, j4_multipos_config_.safe_min, j4_multipos_config_.safe_max);
                positions_valid = false;
            }
        }

        if (!positions_valid) {
            RCLCPP_ERROR(node_->get_logger(), "❌ Invalid positions detected - DISABLING multi-position scanning");
            j4_multipos_config_.enabled = false;
        }
    }

    // Load hardware-specific parameters
    joint5_hardware_offset_ = loadParamDouble("joint5_init/hardware_offset", 0.320);

    // Log timing summary for easy verification
    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), "⏱️  TIMING PARAMETERS SUMMARY");
    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), "  inter_joint_delay:               %.3fs (between J4→J3→J5)", inter_joint_delay_.load());
    RCLCPP_INFO(node_->get_logger(), "  min_sleep_time_for_motor_motion: %.3fs (after joint cmd)", min_sleep_time_for_motor_motion_.load());
    RCLCPP_INFO(node_->get_logger(), "  ee_post_joint5_delay:            %.3fs (before EE start)", ee_post_joint5_delay_.load());
    RCLCPP_INFO(node_->get_logger(), "  EE_forward_runtime:              %.3fs (capture time)", ee_runtime_during_l5_forward_movement_.load());
    RCLCPP_INFO(node_->get_logger(), "  cotton_settle_delay:             %.3fs (before compressor)", cotton_settle_delay_.load());
    RCLCPP_INFO(node_->get_logger(), "  compressor_burst_duration:       %.3fs (drop cotton)", compressor_burst_duration_.load());
    RCLCPP_INFO(node_->get_logger(), "  picking_delay:                   %.3fs (between picks)", picking_delay_.load());
    RCLCPP_INFO(node_->get_logger(), "  use_dynamic_ee_prestart:         %s", use_dynamic_ee_prestart_.load() ? "true (position-based EE)" : "false (EE after J5)");
    if (use_dynamic_ee_prestart_) {
        RCLCPP_INFO(node_->get_logger(), "  ee_start_distance:               %.3fm (EE starts when J5 this far from cotton)", ee_start_distance_.load());
        RCLCPP_INFO(node_->get_logger(), "  ee_stop_distance:                %.3fm (EE stops when J5 retracts this far)", ee_stop_distance_.load());
    }
    RCLCPP_INFO(node_->get_logger(), "════════════════════════════════════════════════════════════════════════");
    RCLCPP_INFO(node_->get_logger(), "Motion parameters loaded successfully");
}

double MotionController::getCurrentTimeMillis() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec * 1000.0 + tv.tv_usec / 1000.0;
}

// ═══════════════════════════════════════════════════════════════
// PARAMETER LOADING HELPERS (reduce boilerplate)
// ═══════════════════════════════════════════════════════════════

double MotionController::loadParamDouble(const std::string& name, double default_val) {
    if (node_->has_parameter(name)) {
        double val = node_->get_parameter(name).as_double();
        RCLCPP_DEBUG(node_->get_logger(), "Loaded %s: %.3f", name.c_str(), val);
        return val;
    }
    RCLCPP_DEBUG(node_->get_logger(), "Using default %s: %.3f", name.c_str(), default_val);
    return default_val;
}

float MotionController::loadParamFloat(const std::string& name, float default_val) {
    if (node_->has_parameter(name)) {
        float val = static_cast<float>(node_->get_parameter(name).as_double());
        RCLCPP_DEBUG(node_->get_logger(), "Loaded %s: %.3f", name.c_str(), val);
        return val;
    }
    RCLCPP_DEBUG(node_->get_logger(), "Using default %s: %.3f", name.c_str(), default_val);
    return default_val;
}

bool MotionController::loadParamBool(const std::string& name, bool default_val) {
    if (node_->has_parameter(name)) {
        bool val = node_->get_parameter(name).as_bool();
        RCLCPP_DEBUG(node_->get_logger(), "Loaded %s: %s", name.c_str(), val ? "true" : "false");
        return val;
    }
    RCLCPP_DEBUG(node_->get_logger(), "Using default %s: %s", name.c_str(), default_val ? "true" : "false");
    return default_val;
}

void MotionController::loadJointInitParameters() {
    // Joint2 parameters
    joint2_init_.height_scan_enable = loadParamBool("joint2_init/height_scan_enable", false);
    joint2_init_.min = loadParamDouble("joint2_init/min", 0.0);
    joint2_init_.max = loadParamDouble("joint2_init/max", 1.0);
    joint2_init_.step = loadParamDouble("joint2_init/step", 0.1);

    // Joint3 parameters (park_position removed 2025-11-28)
    joint3_init_.homing_position = loadParamDouble("joint3_init/homing_position", 0.0);
    joint3_init_.multiple_zero_poses = loadParamBool("joint3_init/multiple_zero_poses", false);
    if (node_->has_parameter("joint3_init/zero_poses")) {
        joint3_init_.zero_poses = node_->get_parameter("joint3_init/zero_poses").as_double_array();
        RCLCPP_DEBUG(node_->get_logger(), "Loaded joint3_init/zero_poses: %zu values", joint3_init_.zero_poses.size());
    }

    // Joint4 parameters (park_position removed 2025-11-28)
    joint4_init_.homing_position = loadParamDouble("joint4_init/homing_position", 0.0);
    joint4_init_.multiple_zero_poses = loadParamBool("joint4_init/multiple_zero_poses", false);
    joint4_init_.theta_jerk_value = loadParamDouble("joint4_init/theta_jerk_value", 0.0);

    // Joint5 parameters (park_position removed 2025-11-28)
    joint5_init_.homing_position = loadParamDouble("joint5_init/homing_position", 0.0);
    joint5_init_.end_effector_len = loadParamDouble("joint5_init/end_effector_len", 0.085);
    joint5_init_.joint5_vel_limit = loadParamDouble("joint5_init/joint5_vel_limit", 2.0);
    joint5_init_.gear_ratio = loadParamDouble("joint5_init/gear_ratio", 20.943933333);
    joint5_init_.phi_jerk_value = loadParamDouble("joint5_init/phi_jerk_value", 0.0);

    RCLCPP_INFO(node_->get_logger(), "Joint initialization parameters loaded");
}

bool MotionController::loadJointLimits() {
    // Check if in simulation mode - use local parameters instead of motor_control node
    bool simulation_mode = node_->get_parameter("simulation_mode").as_bool();

    if (simulation_mode) {
        RCLCPP_INFO(node_->get_logger(), "🤖 SIMULATION MODE: Loading joint limits from local parameters...");

        // Load limits directly from yanthra_move parameters (set in simulation.yaml)
        joint3_limits_.min = loadParamDouble("joint3_init/min_length", -1.57);
        joint3_limits_.max = loadParamDouble("joint3_init/max_length", 1.57);
        joint4_limits_.min = loadParamDouble("joint4_init/min_length", -0.175);
        joint4_limits_.max = loadParamDouble("joint4_init/max_length", 0.175);
        joint5_limits_.min = loadParamDouble("joint5_init/min_length", 0.0);
        joint5_limits_.max = loadParamDouble("joint5_init/max_length", 0.6);

        // Configure TrajectoryPlanner with default transmission factors for simulation
        trajectory_planner_->setHardwareParams(
            joint5_hardware_offset_, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0);
        trajectory_planner_->setCollisionAvoidanceParams(
            loadParamBool("j5_collision_avoidance/enabled", true),
            loadParamDouble("j5_collision_avoidance/clearance", 0.20));

        {
            bool ca_on = loadParamBool("j5_collision_avoidance/enabled", true);
            double ca_clr = loadParamDouble("j5_collision_avoidance/clearance", 0.20);
            RCLCPP_INFO(node_->get_logger(),
                "🛡️  [COLLISION AVOIDANCE] %s | clearance=%.4fm | formula: J5_limit = %.4f / cos(J3)",
                ca_on ? "ENABLED ✅" : "DISABLED ❌", ca_clr, ca_clr);
        }

        joint3_parking_position_ = loadParamDouble("joint3_init/parking_position", 0.3);

        // Use default tolerances for simulation
        joint3_position_tolerance_ = 0.05;
        joint4_position_tolerance_ = 0.005;
        joint5_position_tolerance_ = 0.005;

        RCLCPP_INFO(node_->get_logger(), "✅ Simulation joint limits loaded:");
        RCLCPP_INFO(node_->get_logger(), "   Joint3 (phi): [%.3f, %.3f] rad", joint3_limits_.min, joint3_limits_.max);
        RCLCPP_INFO(node_->get_logger(), "   Joint4 (theta): [%.3f, %.3f] m", joint4_limits_.min, joint4_limits_.max);
        RCLCPP_INFO(node_->get_logger(), "   Joint5 (r): [%.3f, %.3f] m", joint5_limits_.min, joint5_limits_.max);

        return true;
    }

    RCLCPP_INFO(node_->get_logger(), "🔒 Loading joint limits from motor_control node parameters...");

    try {
        // Create synchronous parameter client to read from motor_control node
        auto param_client = std::make_shared<rclcpp::SyncParametersClient>(node_, "motor_control");

        // Wait for motor_control node to be available (timeout: 5 seconds)
        if (!param_client->wait_for_service(std::chrono::seconds(5))) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ motor_control node not available after 5 seconds!");
            RCLCPP_ERROR(node_->get_logger(),
                "   Ensure motor_control node is running before starting motion controller.");
            return false;
        }

        // Read min_positions and max_positions arrays from motor_control
        // Format: [joint5, joint3, joint4] (indices 0, 1, 2)
        std::vector<double> min_positions;
        std::vector<double> max_positions;

        try {
            min_positions = param_client->get_parameter<std::vector<double>>(
                "min_positions");
            max_positions = param_client->get_parameter<std::vector<double>>(
                "max_positions");
        } catch (const rclcpp::exceptions::ParameterNotDeclaredException& e) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ Joint limit parameters not found in motor_control config!");
            RCLCPP_ERROR(node_->get_logger(),
                "   Expected: min_positions and max_positions");
            return false;
        }

        // Validate array sizes
        if (min_positions.size() < 3 || max_positions.size() < 3) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ Invalid limit arrays! Expected 3 values [joint5, joint3, joint4], got min=%zu, max=%zu",
                min_positions.size(), max_positions.size());
            return false;
        }

        // Extract limits for each joint
        // Index mapping: [0]=joint5, [1]=joint3, [2]=joint4
        joint5_limits_.min = min_positions[0];
        joint5_limits_.max = max_positions[0];
        joint3_limits_.min = min_positions[1];
        joint3_limits_.max = max_positions[1];
        joint4_limits_.min = min_positions[2];
        joint4_limits_.max = max_positions[2];

        // Load packing positions for L3 idle temperature optimization
        // Index mapping: [0]=joint5, [1]=joint3, [2]=joint4
        try {
            std::vector<double> packing_positions = param_client->get_parameter<std::vector<double>>(
                "packing_positions");
            if (packing_positions.size() >= 3) {
                joint3_parking_position_ = packing_positions[1];  // Index 1 = joint3
                RCLCPP_INFO(node_->get_logger(),
                    "Loaded joint3 parking position: %.4f rotations", joint3_parking_position_);
            }
        } catch (const std::exception& e) {
            param_load_failure_count_++;
            RCLCPP_WARN(node_->get_logger(),
                "{\"event\":\"parameter_read_failure\","
                "\"parameter\":\"packing_positions\","
                "\"failures\":%u,"
                "\"fallback\":%.4f,"
                "\"error\":\"%s\"}",
                param_load_failure_count_, joint3_parking_position_, e.what());
        }

        // Load transmission factors and directions for accurate motor estimation
        std::vector<double> transmission_factors;
        std::vector<double> directions;

        try {
            transmission_factors = param_client->get_parameter<std::vector<double>>(
                "transmission_factors");

            // directions is stored as an integer array in motor_control_ros2 (e.g., [-1, 1]).
            // Accept either double_array or integer_array for compatibility.
            try {
                directions = param_client->get_parameter<std::vector<double>>(
                    "directions");
            } catch (const std::exception&) {
                const auto directions_int = param_client->get_parameter<std::vector<int64_t>>(
                    "directions");
                directions.clear();
                directions.reserve(directions_int.size());
                for (const auto d : directions_int) {
                    directions.push_back(static_cast<double>(d));
                }
            }

            if (transmission_factors.size() >= 3 && directions.size() >= 3) {
                // Index mapping: [0]=joint5, [1]=joint3, [2]=joint4
                double j5_trans = transmission_factors[0];
                double j3_trans = transmission_factors[1];
                double j4_trans = transmission_factors[2];
                double j5_dir = directions[0];
                double j3_dir = directions[1];
                double j4_dir = directions[2];

                trajectory_planner_->setHardwareParams(
                    joint5_hardware_offset_,
                    j3_trans, j4_trans, j5_trans,
                    j3_dir, j4_dir, j5_dir);
                trajectory_planner_->setCollisionAvoidanceParams(
                    loadParamBool("j5_collision_avoidance/enabled", true),
                    loadParamDouble("j5_collision_avoidance/clearance", 0.20));

                {
                    bool ca_on = loadParamBool("j5_collision_avoidance/enabled", true);
                    double ca_clr = loadParamDouble("j5_collision_avoidance/clearance", 0.20);
                    RCLCPP_INFO(node_->get_logger(),
                        "🛡️  [COLLISION AVOIDANCE] %s | clearance=%.4fm | formula: J5_limit = %.4f / cos(J3)",
                        ca_on ? "ENABLED ✅" : "DISABLED ❌", ca_clr, ca_clr);
                }

                RCLCPP_DEBUG(node_->get_logger(),
                    "Loaded transmission factors: J3=%.2f, J4=%.2f, J5=%.2f",
                    j3_trans, j4_trans, j5_trans);
                RCLCPP_DEBUG(node_->get_logger(),
                    "Loaded directions: J3=%.0f, J4=%.0f, J5=%.0f",
                    j3_dir, j4_dir, j5_dir);
            }
        } catch (const std::exception& e) {
            param_load_failure_count_++;
            RCLCPP_WARN(node_->get_logger(),
                "{\"event\":\"parameter_read_failure\","
                "\"parameter\":\"transmission_factors\","
                "\"failures\":%u,"
                "\"error\":\"%s\"}",
                param_load_failure_count_, e.what());
        }

        // Load per-joint position tolerances (for joint_move feedback-based arrival detection)
        // Index mapping: [0]=joint5, [1]=joint3, [2]=joint4
        try {
            std::vector<double> position_tolerances = param_client->get_parameter<std::vector<double>>(
                "position_tolerance");
            if (position_tolerances.size() >= 3) {
                joint5_position_tolerance_ = position_tolerances[0];
                joint3_position_tolerance_ = position_tolerances[1];
                joint4_position_tolerance_ = position_tolerances[2];
                RCLCPP_INFO(node_->get_logger(),
                    "  Position tolerances: J3=%.4f, J4=%.4f, J5=%.4f (from motor_control)",
                    joint3_position_tolerance_, joint4_position_tolerance_, joint5_position_tolerance_);
            } else {
                RCLCPP_WARN(node_->get_logger(),
                    "  position_tolerance array too short (%zu), using defaults: J3=%.4f, J4=%.4f, J5=%.4f",
                    position_tolerances.size(), joint3_position_tolerance_, joint4_position_tolerance_, joint5_position_tolerance_);
            }
        } catch (const std::exception& e) {
            param_load_failure_count_++;
            RCLCPP_WARN(node_->get_logger(),
                "{\"event\":\"parameter_read_failure\","
                "\"parameter\":\"position_tolerance\","
                "\"failures\":%u,"
                "\"fallback_j3\":%.4f,\"fallback_j4\":%.4f,\"fallback_j5\":%.4f,"
                "\"error\":\"%s\"}",
                param_load_failure_count_,
                joint3_position_tolerance_, joint4_position_tolerance_, joint5_position_tolerance_,
                e.what());
        }

        // Validate limits (min < max)
        bool valid = true;

        if (joint3_limits_.min >= joint3_limits_.max) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ Invalid joint3 limits: min=%.3f >= max=%.3f",
                joint3_limits_.min, joint3_limits_.max);
            valid = false;
        }

        if (joint4_limits_.min >= joint4_limits_.max) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ Invalid joint4 limits: min=%.3f >= max=%.3f",
                joint4_limits_.min, joint4_limits_.max);
            valid = false;
        }

        if (joint5_limits_.min >= joint5_limits_.max) {
            RCLCPP_ERROR(node_->get_logger(),
                "❌ Invalid joint5 limits: min=%.3f >= max=%.3f",
                joint5_limits_.min, joint5_limits_.max);
            valid = false;
        }

        if (!valid) {
            return false;
        }

        // Mark as loaded
        joint3_limits_.loaded = true;
        joint4_limits_.loaded = true;
        joint5_limits_.loaded = true;

        // Log loaded limits
        RCLCPP_INFO(node_->get_logger(), " ");  // Empty line for readability
        RCLCPP_INFO(node_->get_logger(), "╔═══════════════════════════════════════════════════════════╗");
        RCLCPP_INFO(node_->get_logger(), "║  JOINT LIMITS LOADED FROM motor_control (Single Source)   ║");
        RCLCPP_INFO(node_->get_logger(), "╚═══════════════════════════════════════════════════════════╝");
        RCLCPP_INFO(node_->get_logger(), "  Joint3 (rotation):  [%.3f, %.3f] rotations (%.1f° to %.1f°)",
            joint3_limits_.min, joint3_limits_.max,
            joint3_limits_.min * 360.0, joint3_limits_.max * 360.0);
        RCLCPP_INFO(node_->get_logger(), "  Joint4 (left/right): [%.3f, %.3f] meters",
            joint4_limits_.min, joint4_limits_.max);
        RCLCPP_INFO(node_->get_logger(), "  Joint5 (extension):  [%.3f, %.3f] meters",
            joint5_limits_.min, joint5_limits_.max);
        RCLCPP_INFO(node_->get_logger(), "  Position tolerances: J3=%.4f, J4=%.4f, J5=%.4f",
            joint3_position_tolerance_, joint4_position_tolerance_, joint5_position_tolerance_);
        RCLCPP_INFO(node_->get_logger(), " ");  // Empty line for readability
        RCLCPP_INFO(node_->get_logger(), "✅ Single Source of Truth: motor_control/config/production.yaml");
        RCLCPP_INFO(node_->get_logger(), " ");  // Empty line for readability

        return true;

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(),
            "❌ Exception while loading joint limits: %s", e.what());
        return false;
    }
}


bool MotionController::waitForPositionFeedback(const std::string& joint_name, double target_position) {
    if (position_wait_mode_ != "feedback") {
        return true;  // Skip verification unless in feedback mode
    }

    RCLCPP_INFO(node_->get_logger(), "   📍 [%s] Waiting for position feedback (target=%.4f)...",
                joint_name.c_str(), target_position);

    // Subscribe to /joint_states topic to get actual motor positions
    // This reads from motor_control node which publishes joint positions at 10Hz

    auto start_time = std::chrono::steady_clock::now();
    auto timeout = std::chrono::duration<double>(position_feedback_timeout_sec_);
    bool position_reached = false;
    double current_position = 0.0;
    double position_error = 0.0;

    // Create one-shot subscription to /joint_states
    std::promise<bool> position_promise;
    auto position_future = position_promise.get_future();
    std::atomic<bool> promise_set{false};  // Shared between main thread and executor callback

    auto joint_state_sub = node_->create_subscription<sensor_msgs::msg::JointState>(
        "/joint_states", 10,
        [this, &joint_name, &target_position, &position_promise, &promise_set, &current_position, &position_error]
        (const sensor_msgs::msg::JointState::SharedPtr msg) {
            if (promise_set.load()) return;  // Already resolved

            // Find this joint in the message
            for (size_t i = 0; i < msg->name.size(); ++i) {
                if (msg->name[i] == joint_name && i < msg->position.size()) {
                    current_position = msg->position[i];
                    position_error = std::abs(current_position - target_position);

                    if (position_error <= position_feedback_tolerance_) {
                        promise_set.store(true);
                        position_promise.set_value(true);
                        return;
                    }
                    break;
                }
            }
        });

    // Wait for position with timeout — executor thread processes subscription callbacks
    while (std::chrono::steady_clock::now() - start_time < timeout) {
        if (position_future.wait_for(std::chrono::milliseconds(10)) == std::future_status::ready) {
            position_reached = position_future.get();
            break;
        }
    }

    // Destroy subscription (RAII cleanup)
    joint_state_sub.reset();

    if (position_reached) {
        auto duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start_time).count();
        {
            auto j = pragati::json_envelope("position_feedback", node_->get_logger().get_name());
            j["joint"] = joint_name;
            j["target"] = target_position;
            j["actual"] = current_position;
            j["error"] = position_error;
            j["duration_ms"] = duration_ms;
            j["is_timeout"] = false;
            RCLCPP_INFO(node_->get_logger(), "%s", j.dump().c_str());
        }
        // Store feedback result in per-joint member variables
        if (joint_name == "joint3") { feedback_j3_ok_ = true; feedback_j3_error_ = position_error; }
        else if (joint_name == "joint4") { feedback_j4_ok_ = true; feedback_j4_error_ = position_error; }
        else if (joint_name == "joint5") { feedback_j5_ok_ = true; feedback_j5_error_ = position_error; }

        RCLCPP_INFO(node_->get_logger(), "   ✅ [%s] Position reached: actual=%.4f, target=%.4f, error=%.4f",
                    joint_name.c_str(), current_position, target_position, position_error);
        return true;
    } else {
        auto duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start_time).count();
        {
            auto j = pragati::json_envelope("position_feedback", node_->get_logger().get_name());
            j["joint"] = joint_name;
            j["target"] = target_position;
            j["actual"] = current_position;
            j["error"] = position_error;
            j["duration_ms"] = duration_ms;
            j["is_timeout"] = true;
            RCLCPP_INFO(node_->get_logger(), "%s", j.dump().c_str());
        }
        // Store feedback result in per-joint member variables
        if (joint_name == "joint3") { feedback_j3_ok_ = false; feedback_j3_error_ = position_error; }
        else if (joint_name == "joint4") { feedback_j4_ok_ = false; feedback_j4_error_ = position_error; }
        else if (joint_name == "joint5") { feedback_j5_ok_ = false; feedback_j5_error_ = position_error; }

        int joint_id = 0;
        if (joint_name == "joint3") joint_id = 3;
        else if (joint_name == "joint4") joint_id = 4;
        else if (joint_name == "joint5") joint_id = 5;
        recovery_manager_->incrementPositionFeedbackFailure(joint_id);

        RCLCPP_WARN(node_->get_logger(), "   ⚠️  [%s] Position timeout: actual=%.4f, target=%.4f, error=%.4f",
                    joint_name.c_str(), current_position, target_position, position_error);
        RCLCPP_WARN(node_->get_logger(), "   📊 Position feedback failures: total=%d (J3=%d, J4=%d, J5=%d)",
                    recovery_manager_->getPositionFeedbackFailureCount(),
                    recovery_manager_->getPositionFeedbackFailureJ3(), recovery_manager_->getPositionFeedbackFailureJ4(), recovery_manager_->getPositionFeedbackFailureJ5());
        return false;  // Timeout - position not reached
    }
}

void MotionController::turnOffEndEffector() {
    if (gpio_control_) {
        gpio_control_->end_effector_control(false);
        capture_sequence_->markEeInactive();
    }
}

void MotionController::turnOffCompressor() {
    if (gpio_control_) {
        gpio_control_->compressor_control(false);
        capture_sequence_->markCompressorInactive();
    }
}

bool MotionController::isEeCurrentlyOn() const {
    return capture_sequence_->isEeCurrentlyOn();
}

std::chrono::steady_clock::time_point MotionController::getEeOnSince() const {
    return capture_sequence_->getEeOnSince();
}

bool MotionController::isCompressorCurrentlyOn() const {
    return capture_sequence_->isCompressorCurrentlyOn();
}

std::chrono::steady_clock::time_point MotionController::getCompressorOnSince() const {
    return capture_sequence_->getCompressorOnSince();
}

double MotionController::getJoint3Position() {
    // Executor thread continuously processes /joint_states subscription callbacks
    std::lock_guard<std::mutex> lock(joint_state_mutex_);
    auto it = latest_joint_positions_.find("joint3");
    if (it != latest_joint_positions_.end()) {
        return it->second;
    }
    return -1.0;  // Position not available
}

double MotionController::getJoint5Position() {
    // Executor thread continuously processes /joint_states subscription callbacks
    std::lock_guard<std::mutex> lock(joint_state_mutex_);
    auto it = latest_joint_positions_.find("joint5");
    if (it != latest_joint_positions_.end()) {
        return it->second;
    }
    return -1.0;  // Position not available
}

bool MotionController::areMotorsAvailable() {
    // In simulation mode, always return true - simulate full pick sequence
    if (yanthra_move::simulation_mode.load()) {
        RCLCPP_DEBUG(node_->get_logger(), "🤖 SIMULATION MODE: Motors assumed available");
        motors_available_ = true;
        return true;
    }

    auto now = std::chrono::steady_clock::now();

    // Cache result for MOTOR_CHECK_INTERVAL to avoid spamming service.
    // Bypass cache when there's been a recent motor failure (need fresh check).
    bool has_recent_failure = (recovery_manager_->getConsecutiveMoveFailures(3) > 0 ||
                               recovery_manager_->getConsecutiveMoveFailures(4) > 0 ||
                               recovery_manager_->getConsecutiveMoveFailures(5) > 0);
    if (!has_recent_failure && (now - last_motor_check_time_) < MOTOR_CHECK_INTERVAL) {
        return motors_available_;
    }

    // Diagnostic: track service call attempts for Bug 3 investigation
    static uint64_t svc_call_count = 0;
    static uint64_t svc_success_count = 0;
    static uint64_t svc_timeout_count = 0;
    static uint64_t svc_not_available_count = 0;
    svc_call_count++;

    RCLCPP_DEBUG(node_->get_logger(), "🔍 Checking motor availability via /get_motor_availability service...");

    // Create client once and reuse (creating each time causes timeouts due to service discovery delay)
    if (!motor_availability_client_) {
        motor_availability_client_ = node_->create_client<std_srvs::srv::Trigger>("/get_motor_availability");
        RCLCPP_INFO(node_->get_logger(), "[SVC_DIAG] Created motor_availability_client_ (first call)");
    }

    auto wait_start = std::chrono::steady_clock::now();
    if (!motor_availability_client_->wait_for_service(std::chrono::milliseconds(100))) {
        svc_not_available_count++;
        auto wait_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - wait_start).count();
        RCLCPP_WARN(node_->get_logger(),
            "[SVC_DIAG] Motor availability service NOT FOUND in DDS (wait_for_service failed after %ldms) "
            "| calls=%lu ok=%lu timeout=%lu not_found=%lu",
            wait_ms, svc_call_count, svc_success_count, svc_timeout_count, svc_not_available_count);
        motors_available_ = false;
        last_motor_check_time_ = now;
        return false;
    }

    auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
    auto future = motor_availability_client_->async_send_request(request);

    // Wait for response with timeout — executor thread processes response callback
    auto end_time = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
    while (std::chrono::steady_clock::now() < end_time) {
        if (future.wait_for(std::chrono::milliseconds(10)) == std::future_status::ready) {
            auto response = future.get();
            motors_available_ = response->success;
            last_motor_check_time_ = now;
            svc_success_count++;

            auto total_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - wait_start).count();

            if (!motors_available_) {
                RCLCPP_WARN_THROTTLE(node_->get_logger(), *node_->get_clock(), 10000,
                    "⚠️ Motors NOT available - %s", response->message.c_str());
            } else {
                RCLCPP_DEBUG(node_->get_logger(), "[SVC_DIAG] Motor availability OK (%ldms) | calls=%lu ok=%lu timeout=%lu",
                    total_ms, svc_call_count, svc_success_count, svc_timeout_count);
            }

            return motors_available_;
        }
    }

    svc_timeout_count++;
    auto total_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - wait_start).count();

    // Diagnostic: on timeout, check if service is still in graph
    bool service_still_exists = motor_availability_client_->service_is_ready();

    RCLCPP_WARN(node_->get_logger(),
        "[SVC_DIAG] Motor availability TIMEOUT (%ldms) | service_in_graph=%s | "
        "calls=%lu ok=%lu timeout=%lu not_found=%lu | "
        "executor_running=%s",
        total_ms,
        service_still_exists ? "true" : "false",
        svc_call_count, svc_success_count, svc_timeout_count, svc_not_available_count,
        yanthra_move::executor_running.load() ? "true" : "false");

    // On repeated timeouts, try destroying and recreating the client
    if (svc_timeout_count > 0 && (svc_timeout_count % 3) == 0) {
        RCLCPP_WARN(node_->get_logger(),
            "[SVC_DIAG] %lu consecutive-group timeouts — recreating service client",
            svc_timeout_count);
        motor_availability_client_.reset();
    }

    motors_available_ = false;
    last_motor_check_time_ = now;
    return false;
}

// ═══════════════════════════════════════════════════════════════
// L3 IDLE PARKING OPTIMIZATION METHODS
// Reduces motor temperature by keeping L3 tilted up when not picking
// SAFETY: J4 can only move when L3 is at homing (tilted down)
// ═══════════════════════════════════════════════════════════════

void MotionController::moveL3ToParking() {
    if (!enable_l3_idle_parking_) {
        return;  // Feature disabled
    }

    if (l3_at_parking_) {
        RCLCPP_DEBUG(node_->get_logger(), "🌡️  L3 already at parking position");
        return;
    }

    if (!areMotorsAvailable()) {
        RCLCPP_DEBUG(node_->get_logger(), "⚠️  Motors not available - skipping L3 parking");
        return;
    }

    RCLCPP_INFO(node_->get_logger(), "🌡️  Moving L3 to parking position: %.4f rotations (tilting up)",
                joint3_parking_position_);

    auto start = std::chrono::steady_clock::now();

    trajectory_executor_->moveL3ToParking(joint3_parking_position_);

    // Wait for movement to complete
    // BLOCKING_SLEEP_OK: main-thread L3 movement wait — reviewed 2026-03-14
    yanthra_move::utilities::blockingThreadSleep(
        std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));

    auto end = std::chrono::steady_clock::now();
    auto duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    l3_at_parking_ = true;
    RCLCPP_INFO(node_->get_logger(), "🌡️  L3 parked (tilted up) in %ldms - motor can now cool", duration_ms);
}

void MotionController::moveL3ToHoming() {
    if (!enable_l3_idle_parking_) {
        return;  // Feature disabled
    }

    if (!l3_at_parking_) {
        RCLCPP_DEBUG(node_->get_logger(), "🏠 L3 already at homing position");
        return;
    }

    if (!areMotorsAvailable()) {
        RCLCPP_DEBUG(node_->get_logger(), "⚠️  Motors not available - skipping L3 homing");
        return;
    }

    const double joint3_homing = joint3_init_.homing_position;
    RCLCPP_INFO(node_->get_logger(), "🏠 Moving L3 to homing position: %.4f rotations (tilting down, creating clearance)",
                joint3_homing);

    auto start = std::chrono::steady_clock::now();

    trajectory_executor_->moveL3ToHoming(joint3_homing);

    // Wait for movement to complete
    // BLOCKING_SLEEP_OK: main-thread L3 movement wait — reviewed 2026-03-14
    yanthra_move::utilities::blockingThreadSleep(
        std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));

    auto end = std::chrono::steady_clock::now();
    auto duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();

    l3_at_parking_ = false;
    RCLCPP_INFO(node_->get_logger(), "🏠 L3 at homing (tilted down) in %ldms - clearance created for J4", duration_ms);
}

void MotionController::recordMoveResult(int joint_id, MoveResult result) {
    recovery_manager_->recordMoveResult(joint_id, result);
}

int MotionController::getConsecutiveMoveFailures(int joint_id) const {
    return recovery_manager_->getConsecutiveMoveFailures(joint_id);
}

int MotionController::getCumulativeMoveFailures(int joint_id) const {
    return recovery_manager_->getCumulativeMoveFailures(joint_id);
}

void MotionController::setOperationalFailureCallback(OperationalFailureCallback callback) {
    recovery_manager_->setFailureCallback(std::move(callback));
}

void MotionController::setConsecutiveFailureThreshold(int threshold) {
    recovery_manager_->setConsecutiveFailureThreshold(threshold);
}

int MotionController::getTfFailureCount() const {
    return recovery_manager_->getTfFailureCount();
}

int MotionController::getPositionFeedbackFailureCount() const {
    return recovery_manager_->getPositionFeedbackFailureCount();
}

int MotionController::getJointLimitFailureCount() const {
    return recovery_manager_->getJointLimitFailureCount();
}

int MotionController::getPositionFeedbackFailureJ3() const {
    return recovery_manager_->getPositionFeedbackFailureJ3();
}

int MotionController::getPositionFeedbackFailureJ4() const {
    return recovery_manager_->getPositionFeedbackFailureJ4();
}

int MotionController::getPositionFeedbackFailureJ5() const {
    return recovery_manager_->getPositionFeedbackFailureJ5();
}

int MotionController::getEeActivationCount() const {
    return recovery_manager_->getEeActivationCount();
}

int MotionController::getCompressorActivationCount() const {
    return recovery_manager_->getCompressorActivationCount();
}

int MotionController::getTotalPicksAttempted() const {
    return recovery_manager_->getTotalPicksAttempted();
}

int MotionController::getTotalPicksSuccessful() const {
    return recovery_manager_->getTotalPicksSuccessful();
}

double MotionController::getAveragePickDurationMs() const {
    return recovery_manager_->getAveragePickDurationMs();
}

}}  // namespace yanthra_move::core

