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

#include <vector>

namespace yanthra_move { namespace core {

// Joint initialization parameters
struct JointInitParams {
    // NOTE: park_position removed 2025-11-28 - was redundant with homing_position
    double homing_position{0.0};
    bool multiple_zero_poses{false};
    std::vector<double> zero_poses;
    double min{0.0};
    double max{1.0};
    double step{0.1};
    bool height_scan_enable{false};
    double theta_jerk_value{0.0};
    double phi_jerk_value{0.0};
    double end_effector_len{0.085};
    double joint5_vel_limit{2.0};
    double gear_ratio{20.943933333};
    // NOTE: min_length/max_length removed - limits now enforced by motor_control node
};

// Joint limits (loaded from motor_control node parameters)
struct JointLimits {
    double min{0.0};
    double max{0.0};
    bool loaded{false};
};

}}  // namespace yanthra_move::core
