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

#include "yanthra_move/cotton_picking_optimizer.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <vector>

namespace yanthra_move {

CottonPickingOptimizer::PolarCoord
CottonPickingOptimizer::cartesianToPolar(const geometry_msgs::msg::Point& pt) {
    PolarCoord polar;
    polar.r = std::sqrt(pt.x * pt.x + pt.y * pt.y + pt.z * pt.z);
    polar.phi = std::atan2(pt.y, pt.x);  // Base rotation angle
    polar.theta = std::atan2(pt.z, std::sqrt(pt.x * pt.x + pt.y * pt.y));  // Elevation angle
    polar.index = 0;
    return polar;
}

void CottonPickingOptimizer::optimizePickingOrder(
    std::vector<geometry_msgs::msg::Point>& positions,
    Strategy strategy,
    double current_phi,
    double phi_threshold)
{
    if (positions.size() <= 1) {
        return;  // Nothing to optimize
    }

    switch (strategy) {
        case Strategy::NONE:
            // Keep original detection order
            break;

        case Strategy::PHI_SWEEP:
            // Sort by base angle only - single sweep left-to-right
            std::sort(positions.begin(), positions.end(),
                [](const auto& a, const auto& b) {
                    double phi_a = std::atan2(a.y, a.x);
                    double phi_b = std::atan2(b.y, b.x);
                    return phi_a < phi_b;
                });
            break;

        case Strategy::HIERARCHICAL:
            // 2D hierarchical sort: phi primary (minimize base rotation), theta secondary
            std::sort(positions.begin(), positions.end(),
                [phi_threshold](const auto& a, const auto& b) {
                    double phi_a = std::atan2(a.y, a.x);
                    double phi_b = std::atan2(b.y, b.x);

                    // Primary sort: base angle (phi) - most energy-critical
                    if (std::abs(phi_a - phi_b) > phi_threshold) {
                        return phi_a < phi_b;
                    }

                    // Secondary sort: elevation angle (theta) for similar phi values
                    double r_xy_a = std::sqrt(a.x * a.x + a.y * a.y);
                    double r_xy_b = std::sqrt(b.x * b.x + b.y * b.y);
                    double theta_a = std::atan2(a.z, r_xy_a);
                    double theta_b = std::atan2(b.z, r_xy_b);
                    return theta_a < theta_b;
                });
            break;

        case Strategy::RASTER_SCAN:
            // Serpentine raster scan: alternating direction per row (left->right, right->left, etc.)
            {
                // First, group positions by Y coordinate (rows)
                std::map<double, std::vector<geometry_msgs::msg::Point>> rows;
                for (const auto& pos : positions) {
                    // Find the row this position belongs to (group by Y with 1cm tolerance)
                    double row_key = std::round(pos.y * 100.0) / 100.0;  // Round to nearest cm
                    rows[row_key].push_back(pos);
                }

                // Sort rows by Y coordinate (top to bottom)
                std::vector<double> row_keys;
                for (const auto& pair : rows) {
                    row_keys.push_back(pair.first);
                }
                std::sort(row_keys.begin(), row_keys.end());

                // Clear original positions and rebuild in serpentine order
                positions.clear();
                bool left_to_right = true;  // Start with left to right

                for (size_t row_idx = 0; row_idx < row_keys.size(); ++row_idx) {
                    auto& row_positions = rows[row_keys[row_idx]];

                    // Sort this row by X coordinate
                    std::sort(row_positions.begin(), row_positions.end(),
                        [](const auto& a, const auto& b) {
                            return a.x < b.x;  // Always sort left to right first
                        });

                    // If this is a right-to-left row, reverse the order
                    if (!left_to_right) {
                        std::reverse(row_positions.begin(), row_positions.end());
                    }

                    // Add this row to the final positions
                    positions.insert(positions.end(), row_positions.begin(), row_positions.end());

                    // Alternate direction for next row
                    left_to_right = !left_to_right;
                }
            }
            break;

        case Strategy::NEAREST_FIRST:
            // Greedy nearest-neighbor starting from current position
            {
                std::vector<geometry_msgs::msg::Point> sorted;
                sorted.reserve(positions.size());
                std::vector<bool> picked(positions.size(), false);

                // Start from nearest to current_phi
                size_t current_idx = 0;
                double min_dist = std::numeric_limits<double>::max();
                for (size_t i = 0; i < positions.size(); ++i) {
                    double phi = std::atan2(positions[i].y, positions[i].x);
                    double dist = std::abs(phi - current_phi);
                    if (dist < min_dist) {
                        min_dist = dist;
                        current_idx = i;
                    }
                }

                // Greedily pick nearest unvisited cotton
                for (size_t count = 0; count < positions.size(); ++count) {
                    sorted.push_back(positions[current_idx]);
                    picked[current_idx] = true;

                    // Find nearest unpicked cotton
                    if (count < positions.size() - 1) {
                        auto current_polar = cartesianToPolar(positions[current_idx]);
                        double min_energy = std::numeric_limits<double>::max();
                        size_t next_idx = 0;

                        for (size_t i = 0; i < positions.size(); ++i) {
                            if (!picked[i]) {
                                auto polar = cartesianToPolar(positions[i]);
                                // Energy cost (weighted by joint torque)
                                double energy =
                                    JOINT3_ENERGY_WEIGHT * std::pow(polar.phi - current_polar.phi, 2) +
                                    JOINT4_ENERGY_WEIGHT * std::pow(polar.theta - current_polar.theta, 2) +
                                    JOINT5_ENERGY_WEIGHT * std::pow(polar.r - current_polar.r, 2);

                                if (energy < min_energy) {
                                    min_energy = energy;
                                    next_idx = i;
                                }
                            }
                        }
                        current_idx = next_idx;
                    }
                }

                positions = sorted;
            }
            break;
    }
}

void CottonPickingOptimizer::optimizePickingOrder(
    std::vector<geometry_msgs::msg::PointStamped>& positions,
    Strategy strategy,
    double current_phi,
    double phi_threshold)
{
    if (positions.size() <= 1) {
        return;
    }

    // Convert to Point vector for sorting
    std::vector<geometry_msgs::msg::Point> points;
    points.reserve(positions.size());
    for (const auto& ps : positions) {
        points.push_back(ps.point);
    }

    // Optimize
    optimizePickingOrder(points, strategy, current_phi, phi_threshold);

    // Convert back
    for (size_t i = 0; i < positions.size(); ++i) {
        positions[i].point = points[i];
    }
}

double CottonPickingOptimizer::estimateEnergySavings(
    const std::vector<geometry_msgs::msg::Point>& positions,
    Strategy strategy)
{
    if (positions.size() <= 1) {
        return 0.0;
    }

    // Calculate total path energy for current order
    double current_energy = 0.0;
    for (size_t i = 1; i < positions.size(); ++i) {
        auto prev = cartesianToPolar(positions[i-1]);
        auto curr = cartesianToPolar(positions[i]);

        current_energy +=
            JOINT3_ENERGY_WEIGHT * std::pow(curr.phi - prev.phi, 2) +
            JOINT4_ENERGY_WEIGHT * std::pow(curr.theta - prev.theta, 2) +
            JOINT5_ENERGY_WEIGHT * std::pow(curr.r - prev.r, 2);
    }

    // Estimate energy for optimized order
    double optimized_energy = current_energy;
    switch (strategy) {
        case Strategy::NONE:
            return 0.0;
        case Strategy::PHI_SWEEP:
            optimized_energy *= 0.5;  // ~50% savings
            break;
        case Strategy::HIERARCHICAL:
            optimized_energy *= 0.35; // ~65% savings
            break;
        case Strategy::NEAREST_FIRST:
            optimized_energy *= 0.6;  // ~40% savings
            break;
        case Strategy::RASTER_SCAN:
            break;
    }

    return ((current_energy - optimized_energy) / current_energy) * 100.0;
}

}  // namespace yanthra_move
