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

#include "yanthra_move/core/trajectory_planner.hpp"
#include "yanthra_move/coordinate_transforms.hpp"

#include <tf2/exceptions.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>

#include <cmath>
#include <limits>

namespace yanthra_move { namespace core {

// Constants
static constexpr double RAD_TO_ROT = 1.0 / (2.0 * M_PI);
static constexpr double PLANNING_MARGIN = 0.98;

TrajectoryPlanner::TrajectoryPlanner(
    std::shared_ptr<tf2_ros::Buffer> tf_buffer,
    rclcpp::Logger logger)
    : tf_buffer_(std::move(tf_buffer)), logger_(logger) {}

// ---------------------------------------------------------------------------
// plan()
// ---------------------------------------------------------------------------

PlanResult TrajectoryPlanner::plan(
    const geometry_msgs::msg::Point& position,
    const JointLimits& j3_limits,
    const JointLimits& j4_limits,
    const JointLimits& j5_limits,
    const PlanningParams& params) const {

    PlanResult result;

    // Step 1: Input validation
    if (!validateInputCoordinates(position)) {
        result.status = PlanResult::Status::ERROR;
        result.error = PlanError::INVALID_COORDINATES;
        return result;
    }

    // Step 2: TF transform from camera_link to yanthra_link
    auto arm_point = transformToArmFrame(position);
    if (!arm_point.has_value()) {
        result.status = PlanResult::Status::ERROR;
        result.error = PlanError::TF_FAILURE;
        return result;
    }

    // Step 3: Convert to polar coordinates
    double r = 0.0, theta = 0.0, phi = 0.0;
    coordinate_transforms::convertXYZToPolarFLUROSCoordinates(
        arm_point->x, arm_point->y, arm_point->z, &r, &theta, &phi);

    // Step 4: Validate polar output
    if (!std::isfinite(r) || !std::isfinite(theta) || !std::isfinite(phi)) {
        RCLCPP_WARN(logger_,
            "[PLAN] Polar conversion produced NaN/Inf: r=%.4f, theta=%.4f, phi=%.4f",
            r, theta, phi);
        result.status = PlanResult::Status::ERROR;
        result.error = PlanError::INVALID_COORDINATES;
        // Save polar coords even on error (for field-trial logging diagnostics)
        result.trajectory.polar_r = r;
        result.trajectory.polar_theta = theta;
        result.trajectory.polar_phi = phi;
        return result;
    }

    RCLCPP_DEBUG(logger_,
        "[PLAN] Polar coords: r=%.4f m, theta=%.4f m, phi=%.4f rad (%.1f°)",
        r, theta, phi, phi * 180.0 / M_PI);

    // Step 5: Calculate joint commands
    double joint5_cmd = r - j5_hardware_offset_;

    // Phi compensation (if enabled)
    double phi_compensation = computePhiCompensation(phi, joint5_cmd, j5_limits.max);
    double joint3_cmd = (phi + phi_compensation) * RAD_TO_ROT;

    // J4 command with optional offset compensation
    double joint4_cmd = theta;
    if (std::abs(params.current_j4_offset) > 1e-9) {
        joint4_cmd = theta + params.current_j4_offset;
        RCLCPP_DEBUG(logger_,
            "[PLAN] J4 offset compensation: theta=%.4f + offset=%.4f = %.4f",
            theta, params.current_j4_offset, joint4_cmd);
    }

    // Step 5b: J5 collision avoidance clamp (two-arm safety)
    // Dynamically limits J5 based on J3 tilt: J5_limit = clearance / cos(J3)
    // At J3=0 (horizontal), most restrictive. At J3=-54° (tilted), full range.
    if (collision_avoidance_enabled_ && j5_collision_clearance_ > 0.0) {
        const double j3_angle_rad = joint3_cmd * 2.0 * M_PI;  // rotations → radians
        const double j3_angle_deg = joint3_cmd * 360.0;
        const double cos_j3 = std::max(std::cos(j3_angle_rad), 0.1);  // floor prevents div-by-zero
        const double j5_collision_limit = std::min(
            j5_limits.max,
            j5_collision_clearance_ / cos_j3
        );

        // Populate diagnostics in result trajectory
        result.trajectory.collision_avoidance_active = true;
        result.trajectory.collision_j5_requested = joint5_cmd;
        result.trajectory.collision_j5_limit = j5_collision_limit;
        result.trajectory.collision_clearance = j5_collision_clearance_;
        result.trajectory.collision_cos_j3 = cos_j3;

        if (joint5_cmd > j5_collision_limit) {
            result.trajectory.collision_j5_clamped = true;
            const double overshoot = joint5_cmd - j5_collision_limit;
            RCLCPP_WARN(logger_,
                "\n"
                "  ╔══════════════════════════════════════════════════════════════╗\n"
                "  ║  ⛔ COLLISION AVOIDANCE — PICK SKIPPED                      ║\n"
                "  ╠══════════════════════════════════════════════════════════════╣\n"
                "  ║  Requested J5   : %.4fm                                  ║\n"
                "  ║  Safe J5 limit  : %.4fm                                  ║\n"
                "  ║  Overshoot      : %.4fm (%.1f%%)                          ║\n"
                "  ╠══════════════════════════════════════════════════════════════╣\n"
                "  ║  J3 angle       : %.4f rot (%.1f°)                       ║\n"
                "  ║  cos(J3)        : %.4f                                    ║\n"
                "  ║  Clearance      : %.4fm                                  ║\n"
                "  ║  J5 hw max      : %.4fm                                  ║\n"
                "  ╠══════════════════════════════════════════════════════════════╣\n"
                "  ║  Formula: J5_limit = %.4f / %.4f = %.4fm              ║\n"
                "  ║  Result : %.4fm > %.4fm → BLOCKED                   ║\n"
                "  ╚══════════════════════════════════════════════════════════════╝",
                joint5_cmd, j5_collision_limit,
                overshoot, (overshoot / j5_collision_limit) * 100.0,
                joint3_cmd, j3_angle_deg,
                cos_j3,
                j5_collision_clearance_,
                j5_limits.max,
                j5_collision_clearance_, cos_j3, j5_collision_limit,
                joint5_cmd, j5_collision_limit);
            // REJECT — do not clamp, skip the pick entirely
            result.status = PlanResult::Status::ERROR;
            result.error = PlanError::COLLISION_BLOCKED;
            return result;
        } else {
            RCLCPP_DEBUG(logger_,
                "[COLLISION AVOIDANCE] ✅ J5 within safe limit: cmd=%.4fm <= limit=%.4fm "
                "(J3=%.1f°, clearance=%.4fm, cos(J3)=%.4f)",
                joint5_cmd, j5_collision_limit, j3_angle_deg, j5_collision_clearance_, cos_j3);
        }
    }

    // Step 6: Planning limits with margin
    const double j3_planning_min = j3_limits.min * PLANNING_MARGIN;
    const double j3_planning_max = j3_limits.max;  // No margin at zero boundary
    const double j4_planning_min = j4_limits.min * PLANNING_MARGIN;
    const double j4_planning_max = j4_limits.max * PLANNING_MARGIN;
    const double j5_planning_min = j5_limits.min;  // No margin at zero boundary
    const double j5_planning_max = j5_limits.max * PLANNING_MARGIN;

    // Motor rotation estimates (for logging/safety warnings only)
    const double j3_motor_est = joint3_cmd * j3_transmission_factor_;
    const double j4_motor_est = joint4_cmd * j4_transmission_factor_;
    const double j5_motor_est = joint5_cmd * j5_transmission_factor_ * j5_direction_;

    RCLCPP_DEBUG(logger_,
        "[PLAN] Joint commands: J3=%.4f rot, J4=%.4f m, J5=%.4f m "
        "(motor est: J3=%.1f, J4=%.1f, J5=%.1f rot)",
        joint3_cmd, joint4_cmd, joint5_cmd,
        j3_motor_est, j4_motor_est, j5_motor_est);

    // Step 7: Reachability check
    if (!coordinate_transforms::checkReachability(r, theta, phi)) {
        RCLCPP_WARN(logger_,
            "[PLAN] Target unreachable: r=%.4f, theta=%.4f, phi=%.4f", r, theta, phi);
        result.status = PlanResult::Status::ERROR;
        result.error = PlanError::OUT_OF_REACH;
        result.trajectory.polar_r = r;
        result.trajectory.polar_theta = theta;
        result.trajectory.polar_phi = phi;
        return result;
    }

    // Step 8: Joint limit checks
    // J3 (phi rotation) limits
    if (joint3_cmd < j3_planning_min || joint3_cmd > j3_planning_max) {
        RCLCPP_WARN(logger_,
            "[PLAN] J3 limit exceeded: cmd=%.4f rot, limits=[%.4f, %.4f]",
            joint3_cmd, j3_planning_min, j3_planning_max);
        result.status = PlanResult::Status::ERROR;
        result.error = PlanError::JOINT_LIMIT_EXCEEDED;
        result.trajectory.polar_r = r;
        result.trajectory.polar_theta = theta;
        result.trajectory.polar_phi = phi;
        return result;
    }

    // J4 (theta lateral) limits — returns OUT_OF_REACH (lateral unreachable)
    if (joint4_cmd < j4_planning_min || joint4_cmd > j4_planning_max) {
        RCLCPP_WARN(logger_,
            "[PLAN] J4 limit exceeded: cmd=%.4f m, limits=[%.4f, %.4f]",
            joint4_cmd, j4_planning_min, j4_planning_max);
        result.status = PlanResult::Status::ERROR;
        result.error = PlanError::OUT_OF_REACH;
        result.trajectory.polar_r = r;
        result.trajectory.polar_theta = theta;
        result.trajectory.polar_phi = phi;
        return result;
    }

    // J5 (extension) limits
    if (joint5_cmd < j5_planning_min || joint5_cmd > j5_planning_max) {
        RCLCPP_WARN(logger_,
            "[PLAN] J5 limit exceeded: cmd=%.4f m, limits=[%.4f, %.4f]",
            joint5_cmd, j5_planning_min, j5_planning_max);
        result.status = PlanResult::Status::ERROR;
        result.error = PlanError::JOINT_LIMIT_EXCEEDED;
        result.trajectory.polar_r = r;
        result.trajectory.polar_theta = theta;
        result.trajectory.polar_phi = phi;
        return result;
    }

    // Motor rotation safety warning
    if (std::abs(j3_motor_est) > 5.0 || std::abs(j4_motor_est) > 5.0 ||
        std::abs(j5_motor_est) > 5.0) {
        RCLCPP_WARN(logger_,
            "[PLAN] ⚠️  Large motor rotation: J3=%.1f, J4=%.1f, J5=%.1f rotations",
            j3_motor_est, j4_motor_est, j5_motor_est);
    }

    // Step 9: Populate result
    result.status = PlanResult::Status::OK;
    result.trajectory.j3_command = joint3_cmd;
    result.trajectory.j4_command = joint4_cmd;
    result.trajectory.j5_command = joint5_cmd;
    result.trajectory.phi_deg = std::abs(phi) * 180.0 / M_PI;
    result.trajectory.l5_extension = joint5_cmd;
    result.trajectory.polar_r = r;
    result.trajectory.polar_theta = theta;
    result.trajectory.polar_phi = phi;

    return result;
}

// ---------------------------------------------------------------------------
// setPhiCompensation()
// ---------------------------------------------------------------------------

void TrajectoryPlanner::setPhiCompensation(const PhiCompensationParams& params) {
    phi_comp_params_ = params;
}

// ---------------------------------------------------------------------------
// setHardwareParams()
// ---------------------------------------------------------------------------

void TrajectoryPlanner::setHardwareParams(
    double j5_hardware_offset,
    double j3_transmission,
    double j4_transmission,
    double j5_transmission,
    double j3_direction,
    double j4_direction,
    double j5_direction) {
    j5_hardware_offset_ = j5_hardware_offset;
    j3_transmission_factor_ = j3_transmission;
    j4_transmission_factor_ = j4_transmission;
    j5_transmission_factor_ = j5_transmission;
    j3_direction_ = j3_direction;
    j4_direction_ = j4_direction;
    j5_direction_ = j5_direction;
}

// ---------------------------------------------------------------------------
// setCollisionAvoidanceParams()
// ---------------------------------------------------------------------------

void TrajectoryPlanner::setCollisionAvoidanceParams(bool enabled, double clearance) {
    collision_avoidance_enabled_ = enabled;
    j5_collision_clearance_ = clearance;
}

// ---------------------------------------------------------------------------
// validateInputCoordinates()
// ---------------------------------------------------------------------------

bool TrajectoryPlanner::validateInputCoordinates(
    const geometry_msgs::msg::Point& p) const {
    // Check for NaN or Infinity
    if (!std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z)) {
        RCLCPP_WARN(logger_,
            "[PLAN] Invalid coordinates (NaN/Inf): x=%.4f, y=%.4f, z=%.4f",
            p.x, p.y, p.z);
        return false;
    }

    // Check for zero XZ plane (would produce degenerate polar coords)
    if (std::abs(p.x) < 1e-9 && std::abs(p.z) < 1e-9) {
        RCLCPP_WARN(logger_,
            "[PLAN] Invalid coordinates (zero XZ plane): x=%.4f, z=%.4f",
            p.x, p.z);
        return false;
    }

    return true;
}

// ---------------------------------------------------------------------------
// transformToArmFrame()
// ---------------------------------------------------------------------------

std::optional<geometry_msgs::msg::Point>
TrajectoryPlanner::transformToArmFrame(
    const geometry_msgs::msg::Point& camera_point) const {
    try {
        geometry_msgs::msg::PointStamped target_camera;
        target_camera.header.frame_id = "camera_link";
        target_camera.point = camera_point;

        auto transform = tf_buffer_->lookupTransform(
            "yanthra_link", "camera_link", tf2::TimePointZero,
            tf2::durationFromSec(0.5));

        geometry_msgs::msg::PointStamped target_base;
        tf2::doTransform(target_camera, target_base, transform);

        RCLCPP_INFO(logger_,
            "[PLAN] TF transform: camera(%.4f, %.4f, %.4f) → arm(%.4f, %.4f, %.4f)",
            camera_point.x, camera_point.y, camera_point.z,
            target_base.point.x, target_base.point.y, target_base.point.z);

        return target_base.point;
    } catch (const tf2::TransformException& ex) {
        RCLCPP_WARN(logger_, "[PLAN] TF lookup failed: %s", ex.what());
        return std::nullopt;
    }
}

// ---------------------------------------------------------------------------
// computePhiCompensation()
// ---------------------------------------------------------------------------

double TrajectoryPlanner::computePhiCompensation(
    double phi_rad, double j5_cmd, double j5_max) const {
    if (!phi_comp_params_.enabled) {
        return 0.0;
    }

    const double phi_deg = std::abs(phi_rad) * 180.0 / M_PI;
    const double phi_normalized = phi_deg / 90.0;

    double slope = 0.0, offset = 0.0;
    std::string zone_name;

    if (phi_deg <= phi_comp_params_.zone1_max_deg) {
        slope = phi_comp_params_.zone1_slope;
        offset = phi_comp_params_.zone1_offset;
        zone_name = "Zone1";
    } else if (phi_deg <= phi_comp_params_.zone2_max_deg) {
        slope = phi_comp_params_.zone2_slope;
        offset = phi_comp_params_.zone2_offset;
        zone_name = "Zone2";
    } else {
        slope = phi_comp_params_.zone3_slope;
        offset = phi_comp_params_.zone3_offset;
        zone_name = "Zone3";
    }

    double base_compensation = slope * phi_normalized + offset;

    // L5 extension scaling
    double l5_normalized = (j5_max > 0.0 && j5_cmd > 0.0)
        ? std::max(0.0, j5_cmd) / j5_max
        : 0.0;
    double l5_scale_factor = 1.0 + phi_comp_params_.l5_scale * l5_normalized;
    double final_compensation_rot = base_compensation * l5_scale_factor;

    // Convert from rotations to radians
    double phi_compensation_rad = final_compensation_rot * 2.0 * M_PI;

    RCLCPP_DEBUG(logger_,
        "[PLAN] Phi compensation (%s): phi=%.1f°, base=%.4f rot, "
        "l5_scale=%.2f, final=%.4f rot (%.4f rad)",
        zone_name.c_str(), phi_deg, base_compensation,
        l5_scale_factor, final_compensation_rot, phi_compensation_rad);

    return phi_compensation_rad;
}

}}  // namespace yanthra_move::core
