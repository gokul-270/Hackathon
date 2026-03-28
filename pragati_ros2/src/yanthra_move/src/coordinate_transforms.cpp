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

/**
 * @file coordinate_transforms.cpp
 * @brief Implementation of coordinate transformation utilities for Yanthra robotic arm
 * @details Pure coordinate transformation functions extracted from yanthra_move.cpp
 *          for better modularity and maintainability.
 */

#include "yanthra_move/coordinate_transforms.hpp"

#include <cmath>

namespace yanthra_move {
namespace coordinate_transforms {

void convertXYZToPolarFLUROSCoordinates(double x, double y, double z, double* r, double* theta, double* phi) {
    // Zero-coordinate guard: prevent division by zero when x==0 && z==0
    double xz_mag = sqrt(x*x + z*z);
    if (xz_mag < 1e-9) {
        // Degenerate: point is on the Y-axis, r and phi are undefined
        *r = 0.0;
        *theta = y;
        *phi = 0.0;
        return;
    }
    *r = xz_mag;
    *theta = y;  // Y value for joint4 left/right movement (perpendicular to forward axis)
    *phi = asin(z / xz_mag);  // Elevation angle in XZ plane for joint3
}

bool checkReachability(double r, double theta, double phi) {
    // Simple reachability check - placeholder implementation
    (void)theta; (void)phi;  // Suppress unused parameter warnings
    return (r > 0.1 && r < 2.0);  // Basic range check
}

}  // namespace coordinate_transforms
}  // namespace yanthra_move
