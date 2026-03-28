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

#include <rclcpp/logger.hpp>
#include <rclcpp/node.hpp>

#include "yanthra_move/core/planned_trajectory.hpp"

// Forward declarations
class joint_move;
enum class MoveResult : int;

namespace yanthra_move { namespace core {

// Forward declarations
class RecoveryManager;
class CaptureSequence;

/**
 * @brief Executes pre-planned trajectories by commanding joints in the correct
 *        sequence with inter-joint delays and timing instrumentation.
 *
 * Extracted from MotionController to isolate motor commanding logic.
 * Receives PlannedTrajectory from TrajectoryPlanner and sequences the
 * J4->J3->J5 approach and J5-first retreat motor commands.
 *
 * Non-owning: does not own joint_move pointers or optional collaborators.
 * SingleThreadedExecutor: no internal threading or synchronization needed.
 */
class TrajectoryExecutor {
public:
    /**
     * @brief Construct a TrajectoryExecutor with joint motor handles.
     * @param j3 Non-owning pointer to joint3 (rotation) motor
     * @param j4 Non-owning pointer to joint4 (left/right) motor
     * @param j5 Non-owning pointer to joint5 (extension) motor
     * @param logger ROS2 logger for diagnostics
     * @throws std::invalid_argument if any joint pointer is nullptr
     */
    TrajectoryExecutor(joint_move* j3, joint_move* j4, joint_move* j5,
                       rclcpp::Logger logger);

    // --- Optional collaborator setters ---

    /// Set the RecoveryManager for move failure tracking. Accepts nullptr to disable.
    void setRecoveryManager(RecoveryManager* rm);

    /// Set the CaptureSequence for end-effector coordination. Accepts nullptr to disable.
    void setCaptureSequence(CaptureSequence* cs);

    // --- Core execution methods ---

    /**
     * @brief Execute approach trajectory: command joints in J4->J3->J5 order.
     * @param traj Planned joint targets (j3_command, j4_command, j5_command)
     * @param params Approach parameters (delays, skip flags, speeds)
     * @return true if all commanded moves succeed, false on any failure
     */
    bool executeApproach(const PlannedTrajectory& traj,
                         const ApproachParams& params);

    /**
     * @brief Execute retreat: retract J5 first, then conditionally home J3/J4.
     * @param params Retreat parameters (home flags, positions, delays)
     * @return true if all commanded moves succeed, false on any failure
     */
    bool executeRetreat(const RetreatParams& params);

    /**
     * @brief Move all joints to home positions (fire-and-forget).
     * @param j3_home Joint3 home position
     * @param j5_home Joint5 home position
     * @param j4_home Joint4 home position
     */
    void moveToHomePosition(double j3_home, double j5_home, double j4_home);

    /**
     * @brief Move all joints to packing/home positions with optional feedback wait.
     * @param j3_home Joint3 home position
     * @param j5_home Joint5 home position
     * @param j4_home Joint4 home position
     * @param position_wait_mode "blind_sleep", "feedback", or "service"
     * @return true if all joints reached position (or in simulation/blind_sleep mode)
     */
    bool moveToPackingPosition(double j3_home, double j5_home, double j4_home,
                               const std::string& position_wait_mode);

    /**
     * @brief Move J3 to idle parking position (tilt up for cooling).
     * @param parking_position Target parking position for J3
     */
    void moveL3ToParking(double parking_position);

    /**
     * @brief Move J3 back from parking to homing position.
     * @param homing_position Target homing position for J3
     */
    void moveL3ToHoming(double homing_position);

    /**
     * @brief Wait for a joint to reach target position via feedback.
     * @param joint_name Name of the joint ("joint3", "joint4", "joint5")
     * @param target Target position
     * @param tolerance Position tolerance for arrival check
     * @param timeout_sec Maximum wait time in seconds
     * @return true if position reached or mode is "blind_sleep"/simulation
     */
    bool waitForPositionFeedback(const std::string& joint_name, double target,
                                 double tolerance, double timeout_sec);

    // --- Timing accessors ---

    double getApproachJ3Ms() const { return approach_j3_ms_; }
    double getApproachJ4Ms() const { return approach_j4_ms_; }
    double getApproachJ5Ms() const { return approach_j5_ms_; }
    double getRetreatJ5Ms() const { return retreat_j5_ms_; }

private:
    /// Record a move result with the recovery manager (if set).
    void recordMoveResult(int joint_id, MoveResult result);

    /// Spin the node briefly to process pending subscription callbacks.
    /// Ensures published messages are delivered to subscribers before the next publish.
    void spinOnce();

    // Non-owning joint motor handles
    joint_move* j3_;
    joint_move* j4_;
    joint_move* j5_;

    rclcpp::Logger logger_;
    rclcpp::Node::SharedPtr node_;  // For spinning callbacks between publishes

    // Optional collaborators (non-owning)
    RecoveryManager* recovery_manager_{nullptr};
    CaptureSequence* capture_sequence_{nullptr};

    // Sub-phase timing (milliseconds)
    double approach_j3_ms_{0.0};
    double approach_j4_ms_{0.0};
    double approach_j5_ms_{0.0};
    double retreat_j5_ms_{0.0};
};

}}  // namespace yanthra_move::core

