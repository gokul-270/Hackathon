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

#include <cstddef>
#include <vector>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>

namespace yanthra_move {

/**
 * @brief Energy-efficient cotton picking path optimizer
 *
 * Optimizes the picking sequence to minimize energy consumption for battery-operated robots.
 * Prioritizes minimizing base rotation (Joint3) which consumes the most energy due to
 * moving the entire arm mass.
 */
class CottonPickingOptimizer {
public:
    /**
     * @brief Optimization strategy
     */
    enum class Strategy {
        NONE,              // No optimization - pick in detection order
        NEAREST_FIRST,     // Greedy nearest-neighbor
        PHI_SWEEP,         // Sort by base angle (phi) - minimizes Joint3 movement
        HIERARCHICAL,      // 2D sort: phi primary, theta secondary (BEST for energy)
        RASTER_SCAN        // Serpentine: alternating row directions (L→R, R→L, L→R...)
    };

    /**
     * @brief Sort cotton positions for energy-efficient picking
     *
     * @param positions Vector of cotton positions to sort (modified in-place)
     * @param strategy Optimization strategy to use
     * @param current_phi Current base angle (radians) for NEAREST_FIRST strategy
     * @param phi_threshold Threshold for grouping similar phi angles (radians, default 0.05 ~= 2.8°)
     */
    static void optimizePickingOrder(
        std::vector<geometry_msgs::msg::Point>& positions,
        Strategy strategy = Strategy::HIERARCHICAL,
        double current_phi = 0.0,
        double phi_threshold = 0.05);

    /**
     * @brief Sort PointStamped positions (legacy compatibility)
     */
    static void optimizePickingOrder(
        std::vector<geometry_msgs::msg::PointStamped>& positions,
        Strategy strategy = Strategy::HIERARCHICAL,
        double current_phi = 0.0,
        double phi_threshold = 0.05);

    /**
     * @brief Estimate energy savings compared to random picking
     *
     * @param positions Cotton positions
     * @param strategy Optimization strategy used
     * @return Estimated energy savings as percentage (0-100)
     */
    static double estimateEnergySavings(
        const std::vector<geometry_msgs::msg::Point>& positions,
        Strategy strategy);

private:
    // Convert cartesian to polar coordinates
    struct PolarCoord {
        double r;      // radial distance
        double theta;  // elevation angle
        double phi;    // base rotation angle
        size_t index;  // original index
    };

    static PolarCoord cartesianToPolar(const geometry_msgs::msg::Point& pt);

    // Energy cost weights (based on joint torque requirements)
    static constexpr double JOINT3_ENERGY_WEIGHT = 10.0;  // Base rotation - highest cost
    static constexpr double JOINT4_ENERGY_WEIGHT = 3.0;   // Upper arm rotation
    static constexpr double JOINT5_ENERGY_WEIGHT = 1.0;   // Prismatic extension - lowest cost
};

}  // namespace yanthra_move
