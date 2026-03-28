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

#include <string>

namespace yanthra_move { namespace core {

enum class PlanError {
    INVALID_COORDINATES,   // NaN or zero input
    TF_FAILURE,           // TF lookup failed
    OUT_OF_REACH,         // Target unreachable (theta beyond J4 limits)
    JOINT_LIMIT_EXCEEDED, // Computed joint angle exceeds limits
    COLLISION_BLOCKED     // J5 exceeds collision avoidance safe limit — pick skipped
};

struct PlannedTrajectory {
    double j3_command{0.0};     // phi angle (rotations)
    double j4_command{0.0};     // theta offset (meters)
    double j5_command{0.0};     // radial extension (meters)
    double phi_deg{0.0};        // phi in degrees (for logging/compensation)
    double l5_extension{0.0};   // computed L5 extension
    double polar_r{0.0};       // polar radius (meters) — for field-trial logging
    double polar_theta{0.0};   // polar theta (meters) — for field-trial logging
    double polar_phi{0.0};     // polar phi (radians) — for field-trial logging

    // Collision avoidance diagnostics (populated when feature is enabled)
    bool collision_avoidance_active{false};  // true if collision avoidance was evaluated
    bool collision_j5_clamped{false};        // true if J5 was clamped by collision limit
    double collision_j5_requested{0.0};      // J5 before clamping (original value)
    double collision_j5_limit{0.0};          // computed safe J5 limit
    double collision_clearance{0.0};         // clearance config used
    double collision_cos_j3{0.0};            // cos(J3) used in formula
};

struct PlanResult {
    enum class Status { OK, ERROR } status{Status::ERROR};
    PlanError error{PlanError::INVALID_COORDINATES};  // only valid when status == ERROR
    PlannedTrajectory trajectory;  // only valid when status == OK
};

struct PlanningParams {
    double current_j4_offset{0.0};  // Current J4 scan offset for theta correction
    double ee_length{0.085};         // End effector length
    double j5_vel_limit{2.0};
};

struct PhiCompensationParams {
    bool enabled{false};
    double zone1_max_deg{30.0};
    double zone2_max_deg{60.0};
    double zone1_slope{0.0};
    double zone1_offset{0.0};
    double zone2_slope{0.0};
    double zone2_offset{0.0};
    double zone3_slope{0.0};
    double zone3_offset{0.0};
    double l5_scale{0.5};
};

// Parameters for approach phase motor sequencing
struct ApproachParams {
    double inter_joint_delay{0.3};
    double min_sleep_time{0.2};
    bool skip_j4{false};
    std::string position_wait_mode{"blind_sleep"};
    double position_feedback_timeout{2.0};
    double position_feedback_tolerance{0.01};
    bool enable_l3_idle_parking{false};
    double j3_parking_position{0.008};
};

// Parameters for retreat phase motor sequencing
struct RetreatParams {
    bool home_j5{true};
    bool home_j3{true};
    bool home_j4{true};
    double j3_home{0.0};
    double j5_home{0.0};
    double j4_home{0.0};
    double inter_joint_delay{0.3};
    double cotton_settle_delay{0.2};
    double compressor_burst_duration{0.5};
    std::string position_wait_mode{"blind_sleep"};
    double position_feedback_timeout{2.0};
    double position_feedback_tolerance{0.01};
    bool enable_cotton_eject{false};
    bool enable_compressor_eject{false};
    double j3_eject_position{-0.2};
    double ee_motor2_eject_duration_ms{300.0};
    double ee_motor2_forward_flush_ms{200.0};
    double j3_eject_feedback_timeout_sec{1.5};
    bool enable_l3_idle_parking{false};
    double j3_parking_position{0.008};
};

}}  // namespace yanthra_move::core
