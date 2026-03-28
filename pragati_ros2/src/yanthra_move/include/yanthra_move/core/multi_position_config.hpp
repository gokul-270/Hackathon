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

#pragma once

#include <map>
#include <string>
#include <vector>

namespace yanthra_move { namespace core {

// ═══════════════════════════════════════════════════════════════════════════
// JOINT4 MULTI-POSITION SCANNING CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════
// Enables scanning multiple J4 (left/right) positions to increase camera FOV
// coverage and recover border cotton detections (16 lost in Jan 2026 trial)
// ═══════════════════════════════════════════════════════════════════════════
struct Joint4MultiPositionConfig {
    bool enabled{false};                    // Master enable/disable flag
    std::vector<double> positions;          // Scan positions (meters, relative to center)
    double safe_min{-0.175};                // Mechanical limit
    double safe_max{0.175};                 // Mechanical limit
    std::string scan_strategy{"left_to_right"};  // "left_to_right", "right_to_left", "as_configured"
    double j4_settling_time{0.100};         // TF stabilization wait (seconds)
    double detection_settling_time{0.050};  // Detection pipeline wait (seconds)
    bool early_exit_enabled{true};          // Skip remaining if no cotton found
    std::string on_j4_failure{"skip_position"};  // Error handling strategy
    bool enable_timing_stats{true};         // Log per-position timing
    bool enable_position_stats{true};       // Track position effectiveness
    bool enable_j4_offset_compensation{true};  // Apply J4 offset correction to theta
};

// Multi-position statistics (session-level metrics)
struct MultiPositionStats {
    int total_scans{0};                      // Total multi-position scans executed
    int cottons_found_multipos{0};           // Cottons found via multi-position
    int cottons_found_center{0};             // Cottons found at center position
    std::map<double, int> position_hit_count;  // Per-position cotton detection count
    std::map<double, double> position_avg_time_ms;  // Per-position average time
    int early_exits{0};                      // Times early exit triggered
    int j4_move_failures{0};                 // J4 movement failures
};

}}  // namespace yanthra_move::core
