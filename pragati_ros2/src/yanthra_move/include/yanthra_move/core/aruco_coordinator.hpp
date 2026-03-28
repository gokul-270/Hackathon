// Copyright 2026 Pragati Robotics
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

#pragma once

/**
 * @file aruco_coordinator.hpp
 * @brief Encapsulates ArUco marker detection, multi-position J4 scanning,
 *        preloaded centroid loading, and detection re-trigger gating.
 *
 * Extracted from MotionController as part of the motion-controller-decomposition
 * change.  The coordinator does NOT own the detection hardware or motor
 * commands — it invokes caller-supplied callbacks for both.
 */

#include <chrono>
#include <functional>
#include <optional>
#include <string>
#include <vector>

#include <geometry_msgs/msg/point.hpp>
#include <rclcpp/logger.hpp>
#include <rclcpp/logging.hpp>

#include "yanthra_move/core/cotton_detection.hpp"
#include "yanthra_move/core/multi_position_config.hpp"
#include "yanthra_move/joint_move.h"  // MoveResult

namespace yanthra_move { namespace core {

class ArucoCoordinator {
public:
    // ── callback types ────────────────────────────────────────────────────
    using DetectionCallback =
        std::function<std::optional<std::vector<CottonDetection>>()>;
    using J4MoveCallback = std::function<MoveResult(double position)>;
    using CameraCheckCallback = std::function<bool()>;

    // ── lifecycle ─────────────────────────────────────────────────────────
    explicit ArucoCoordinator(rclcpp::Logger logger);

    // ── callback wiring ───────────────────────────────────────────────────
    void setDetectionCallback(DetectionCallback cb);
    void setJ4MoveCallback(J4MoveCallback cb);
    void setCameraCheckCallback(CameraCheckCallback cb);

    // ── detection ─────────────────────────────────────────────────────────

    /**
     * Execute ArUco detection via the wired detection callback.
     *
     * Respects re-trigger gating: the first call always proceeds; subsequent
     * calls only invoke the callback when re-triggering is enabled.
     *
     * @return Detected marker corner positions (empty on failure or gated).
     */
    std::vector<geometry_msgs::msg::Point> executeArucoDetection();

    /**
     * Check whether a camera is available for detection.
     * Delegates to the wired CameraCheckCallback (returns false if none set).
     */
    bool isCameraAvailable() const;

    // ── multi-position J4 scanning ────────────────────────────────────────

    /**
     * Run a multi-position J4 scan: iterate through config.positions, move
     * J4 to each offset, invoke detection at each, and aggregate results.
     *
     * @param config  Multi-position configuration (positions, strategy, etc.)
     * @return Aggregated detections across all scan positions (nullopt on
     *         total failure).
     */
    std::optional<std::vector<CottonDetection>>
    executeMultiPositionScan(const Joint4MultiPositionConfig& config);

    // ── re-trigger gating ─────────────────────────────────────────────────
    void setReTriggerEnabled(bool enabled);
    bool isReTriggerEnabled() const;

    /**
     * Reset the detection-fired flag so that the next executeArucoDetection()
     * is treated as an initial detection (not a re-trigger).
     */
    void resetDetectionState();

    // ── preloaded centroids ───────────────────────────────────────────────

    /**
     * Load cotton positions from a CSV file (x,y,z per line, optional header).
     * @param filepath  Path to centroid file.
     * @return Parsed detections, or nullopt if the file cannot be opened.
     */
    std::optional<std::vector<CottonDetection>>
    loadPreloadedCentroids(const std::string& filepath);

    // ── accessors ─────────────────────────────────────────────────────────
    double getCurrentJ4ScanOffset() const { return current_j4_scan_offset_; }
    const MultiPositionStats& getMultiPositionStats() const { return stats_; }

private:
    rclcpp::Logger logger_;

    // callbacks (wired by MotionController)
    DetectionCallback detection_callback_;
    J4MoveCallback j4_move_callback_;
    CameraCheckCallback camera_check_callback_;

    // re-trigger gating
    bool retrigger_enabled_{false};
    bool detection_fired_{false};  ///< true after first detection call

    // multi-position state
    double current_j4_scan_offset_{0.0};
    MultiPositionStats stats_;
};

}}  // namespace yanthra_move::core
