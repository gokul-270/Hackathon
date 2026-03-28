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

#include "yanthra_move/core/aruco_coordinator.hpp"

#include <algorithm>
#include <fstream>
#include <sstream>
#include <thread>

namespace yanthra_move { namespace core {

// ═══════════════════════════════════════════════════════════════════════════════
// LIFECYCLE
// ═══════════════════════════════════════════════════════════════════════════════

ArucoCoordinator::ArucoCoordinator(rclcpp::Logger logger)
    : logger_(logger)
{}

// ═══════════════════════════════════════════════════════════════════════════════
// CALLBACK WIRING
// ═══════════════════════════════════════════════════════════════════════════════

void ArucoCoordinator::setDetectionCallback(DetectionCallback cb) {
    detection_callback_ = std::move(cb);
}

void ArucoCoordinator::setJ4MoveCallback(J4MoveCallback cb) {
    j4_move_callback_ = std::move(cb);
}

void ArucoCoordinator::setCameraCheckCallback(CameraCheckCallback cb) {
    camera_check_callback_ = std::move(cb);
}

// ═══════════════════════════════════════════════════════════════════════════════
// DETECTION
// ═══════════════════════════════════════════════════════════════════════════════

std::vector<geometry_msgs::msg::Point> ArucoCoordinator::executeArucoDetection() {
    // Re-trigger gating: first call always proceeds; subsequent calls only
    // proceed if re-triggering is enabled.
    if (detection_fired_ && !retrigger_enabled_) {
        RCLCPP_DEBUG(logger_, "ArUco detection gated (re-trigger disabled)");
        return {};
    }

    if (!detection_callback_) {
        RCLCPP_WARN(logger_, "ArUco detection callback not set");
        return {};
    }

    auto result = detection_callback_();
    detection_fired_ = true;

    if (!result.has_value() || result->empty()) {
        RCLCPP_DEBUG(logger_, "ArUco detection returned no results");
        return {};
    }

    // Convert CottonDetection → geometry_msgs::msg::Point
    std::vector<geometry_msgs::msg::Point> points;
    points.reserve(result->size());
    for (const auto& det : *result) {
        points.push_back(det.position);
    }

    RCLCPP_DEBUG(logger_, "ArUco detection returned %zu marker positions",
                 points.size());
    return points;
}

bool ArucoCoordinator::isCameraAvailable() const {
    if (camera_check_callback_) {
        return camera_check_callback_();
    }
    return false;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MULTI-POSITION J4 SCANNING
// ═══════════════════════════════════════════════════════════════════════════════

std::optional<std::vector<CottonDetection>>
ArucoCoordinator::executeMultiPositionScan(const Joint4MultiPositionConfig& config) {
    if (!config.enabled || config.positions.empty()) {
        RCLCPP_DEBUG(logger_, "Multi-position scan skipped (disabled or no positions)");
        return std::nullopt;
    }

    if (!j4_move_callback_) {
        RCLCPP_WARN(logger_, "J4 move callback not set — cannot execute multi-position scan");
        return std::nullopt;
    }

    if (!detection_callback_) {
        RCLCPP_WARN(logger_, "Detection callback not set — cannot execute multi-position scan");
        return std::nullopt;
    }

    // Determine scan order based on strategy
    std::vector<double> scan_order = config.positions;
    if (config.scan_strategy == "left_to_right") {
        std::sort(scan_order.begin(), scan_order.end());
    } else if (config.scan_strategy == "right_to_left") {
        std::sort(scan_order.begin(), scan_order.end(), std::greater<double>());
    }
    // "as_configured" preserves original order

    RCLCPP_INFO(logger_, "Multi-position J4 scan: %zu positions, strategy=%s",
                scan_order.size(), config.scan_strategy.c_str());

    std::vector<CottonDetection> aggregated;
    stats_.total_scans++;

    for (size_t pos_idx = 0; pos_idx < scan_order.size(); ++pos_idx) {
        const double offset = scan_order[pos_idx];

        RCLCPP_INFO(logger_, "Scan %zu/%zu: J4 offset %+.3fm",
                     pos_idx + 1, scan_order.size(), offset);

        // Move J4 to scan position
        auto move_result = j4_move_callback_(offset);
        if (move_result != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "J4 move to %+.3f failed (result=%d)",
                        offset, static_cast<int>(move_result));
            stats_.j4_move_failures++;

            if (config.on_j4_failure == "abort_scan") {
                RCLCPP_WARN(logger_, "Aborting multi-position scan due to J4 failure");
                break;
            }
            // "skip_position" — continue to next position
            continue;
        }

        // Settling time for TF and detection pipeline
        double settle_ms = config.j4_settling_time * 1000.0 +
                           config.detection_settling_time * 1000.0;
        if (settle_ms > 0) {
            // BLOCKING_SLEEP_OK: main-thread settling delay for TF + detection pipeline — reviewed 2026-03-14
            std::this_thread::sleep_for(
                std::chrono::milliseconds(static_cast<int>(settle_ms)));
        }

        // Update current J4 scan offset BEFORE detection
        current_j4_scan_offset_ = offset;

        // Invoke detection at this position
        auto detections = detection_callback_();
        if (!detections.has_value() || detections->empty()) {
            RCLCPP_DEBUG(logger_, "No detections at J4 offset %+.3f", offset);

            if (config.early_exit_enabled && pos_idx > 0) {
                RCLCPP_INFO(logger_, "Early exit: no detections at position %zu",
                            pos_idx + 1);
                stats_.early_exits++;
                break;
            }
            continue;
        }

        // Apply J4 offset compensation if enabled
        if (config.enable_j4_offset_compensation) {
            for (auto& det : *detections) {
                // Compensate detection position.x by the J4 scan offset.
                // This corrects for the camera moving with J4 — the
                // detected position in camera frame needs the J4 offset
                // added to translate back to the base frame.
                det.position.x += offset;
            }
        }

        // Track per-position statistics
        int count = static_cast<int>(detections->size());
        stats_.position_hit_count[offset] += count;
        if (offset == 0.0) {
            stats_.cottons_found_center += count;
        } else {
            stats_.cottons_found_multipos += count;
        }

        // Aggregate
        aggregated.insert(aggregated.end(), detections->begin(), detections->end());

        RCLCPP_INFO(logger_, "Found %d detections at J4 offset %+.3f",
                     count, offset);
    }

    if (aggregated.empty()) {
        return std::nullopt;
    }

    return aggregated;
}

// ═══════════════════════════════════════════════════════════════════════════════
// RE-TRIGGER GATING
// ═══════════════════════════════════════════════════════════════════════════════

void ArucoCoordinator::setReTriggerEnabled(bool enabled) {
    retrigger_enabled_ = enabled;
}

bool ArucoCoordinator::isReTriggerEnabled() const {
    return retrigger_enabled_;
}

void ArucoCoordinator::resetDetectionState() {
    detection_fired_ = false;
    current_j4_scan_offset_ = 0.0;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PRELOADED CENTROIDS
// ═══════════════════════════════════════════════════════════════════════════════

std::optional<std::vector<CottonDetection>>
ArucoCoordinator::loadPreloadedCentroids(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        RCLCPP_WARN(logger_, "Cannot open centroid file: %s", filepath.c_str());
        return std::nullopt;
    }

    std::vector<CottonDetection> detections;
    std::string line;
    int line_num = 0;

    while (std::getline(file, line)) {
        line_num++;

        // Trim leading whitespace
        size_t first_char = line.find_first_not_of(" \t\r\n");
        if (first_char == std::string::npos) continue;

        // Skip comment lines
        if (line[first_char] == '#') continue;

        // Skip CSV header (contains non-numeric first field)
        if (line_num == 1 && (line.find("x,y,z") != std::string::npos ||
                              line.find("X,Y,Z") != std::string::npos)) {
            continue;
        }

        // Parse comma-separated or space-separated x,y,z
        double x, y, z;
        // Try comma-separated first
        char c1, c2;
        std::istringstream iss(line);
        if (iss >> x >> c1 >> y >> c2 >> z && c1 == ',' && c2 == ',') {
            // CSV format
        } else {
            // Try space-separated
            iss.clear();
            iss.str(line);
            if (!(iss >> x >> y >> z)) {
                RCLCPP_DEBUG(logger_, "Skipping malformed line %d: %s",
                             line_num, line.c_str());
                continue;
            }
        }

        CottonDetection det;
        det.position.x = x;
        det.position.y = y;
        det.position.z = z;
        det.confidence = 1.0f;  // Preloaded centroids are fully trusted
        det.detection_id = static_cast<int>(detections.size());
        det.detection_time = std::chrono::steady_clock::now();
        detections.push_back(det);
    }

    file.close();

    if (detections.empty()) {
        RCLCPP_WARN(logger_, "Centroid file %s contained no valid entries",
                     filepath.c_str());
        return std::nullopt;
    }

    RCLCPP_INFO(logger_, "Loaded %zu preloaded centroids from %s",
                 detections.size(), filepath.c_str());
    return detections;
}

}}  // namespace yanthra_move::core
