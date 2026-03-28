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
 * @file coordinate_transforms.hpp
 * @brief Coordinate transformation utilities for Yanthra robotic arm
 * @details This module contains pure coordinate transformation functions
 *          extracted from yanthra_move.cpp for better modularity and maintainability.
 *          These functions handle transforms between different coordinate frames.
 */

#ifndef YANTHRA_MOVE_COORDINATE_TRANSFORMS_HPP_
#define YANTHRA_MOVE_COORDINATE_TRANSFORMS_HPP_

#include <vector>
#include <tf2_ros/buffer.h>
#include <geometry_msgs/msg/point.hpp>

namespace yanthra_move {
namespace coordinate_transforms {

/**
 * @brief Convert XYZ coordinates to polar coordinates in FLU-ROS coordinate system
 * @param x X coordinate
 * @param y Y coordinate
 * @param z Z coordinate
 * @param r Output radial distance
 * @param theta Output theta angle (azimuth)
 * @param phi Output phi angle (elevation)
 */
void convertXYZToPolarFLUROSCoordinates(double x, double y, double z, double* r, double* theta, double* phi);

/**
 * @brief Check if the given polar coordinates are reachable by the arm
 * @param r Radial distance
 * @param theta Theta angle (azimuth)
 * @param phi Phi angle (elevation)
 * @return true if reachable, false otherwise
 */
bool checkReachability(double r, double theta, double phi);

}  // namespace coordinate_transforms
}  // namespace yanthra_move

#endif  // YANTHRA_MOVE_COORDINATE_TRANSFORMS_HPP_
