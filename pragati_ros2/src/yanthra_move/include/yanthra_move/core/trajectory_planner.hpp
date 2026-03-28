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

#include <memory>
#include <optional>
#include <rclcpp/rclcpp.hpp>
#include <tf2_ros/buffer.h>
#include <geometry_msgs/msg/point.hpp>

#include "yanthra_move/core/planned_trajectory.hpp"
#include "yanthra_move/core/joint_config_types.hpp"

namespace yanthra_move { namespace core {

/**
 * @brief Pure-computation trajectory planner — converts a camera-frame target
 *        into joint commands via TF transform, polar conversion, phi
 *        compensation, and limit checking.
 *
 * Extracted from MotionController::executeApproachTrajectory() planning section.
 * No motor I/O or side effects beyond logging.
 */
class TrajectoryPlanner {
public:
    TrajectoryPlanner(std::shared_ptr<tf2_ros::Buffer> tf_buffer,
                      rclcpp::Logger logger);

    /**
     * @brief Plan a trajectory from camera-frame target to joint commands.
     *
     * Steps: validate input → TF transform → polar conversion → phi compensation
     * → joint command calculation → limit checks.
     *
     * @param position Camera-frame target (x, y, z)
     * @param j3_limits Joint3 (rotation) limits
     * @param j4_limits Joint4 (left/right) limits
     * @param j5_limits Joint5 (extension) limits
     * @param params Planning parameters (J4 offset, etc.)
     * @return PlanResult with Status::OK and trajectory, or Status::ERROR and error code
     */
    PlanResult plan(const geometry_msgs::msg::Point& position,
                    const JointLimits& j3_limits,
                    const JointLimits& j4_limits,
                    const JointLimits& j5_limits,
                    const PlanningParams& params) const;

    /**
     * @brief Set phi compensation parameters
     */
    void setPhiCompensation(const PhiCompensationParams& params);

    /**
     * @brief Set hardware parameters (offsets, transmission factors, directions)
     */
    void setHardwareParams(double j5_hardware_offset,
                           double j3_transmission,
                           double j4_transmission,
                           double j5_transmission,
                           double j3_direction,
                           double j4_direction,
                           double j5_direction);

    /**
     * @brief Set collision avoidance parameters for two-arm setups
     */
    void setCollisionAvoidanceParams(bool enabled, double clearance);

private:
    std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
    rclcpp::Logger logger_;

    // Hardware params (set via setHardwareParams)
    double j5_hardware_offset_{0.320};
    double j3_transmission_factor_{1.0};
    double j4_transmission_factor_{12.74};
    double j5_transmission_factor_{12.74};
    double j3_direction_{-1.0};
    double j4_direction_{-1.0};
    double j5_direction_{-1.0};

    // Collision avoidance params (set via setCollisionAvoidanceParams)
    bool collision_avoidance_enabled_{false};
    double j5_collision_clearance_{0.20};

    // Phi compensation (set via setPhiCompensation)
    PhiCompensationParams phi_comp_params_;

    // Internal helpers
    bool validateInputCoordinates(const geometry_msgs::msg::Point& p) const;
    std::optional<geometry_msgs::msg::Point> transformToArmFrame(
        const geometry_msgs::msg::Point& camera_point) const;
    double computePhiCompensation(double phi_rad, double j5_cmd, double j5_max) const;
};

}}  // namespace yanthra_move::core
