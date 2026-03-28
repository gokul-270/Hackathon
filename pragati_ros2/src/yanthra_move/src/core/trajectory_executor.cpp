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

#include "yanthra_move/core/trajectory_executor.hpp"

#include <chrono>
#include <cmath>
#include <stdexcept>
#include <string>
#include <thread>

#include "yanthra_move/core/recovery_manager.hpp"
#include "yanthra_move/joint_move.h"
#include "yanthra_move/yanthra_utilities.hpp"

namespace yanthra_move { namespace core {

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

TrajectoryExecutor::TrajectoryExecutor(joint_move* j3, joint_move* j4,
                                       joint_move* j5, rclcpp::Logger logger)
    : j3_(j3), j4_(j4), j5_(j5), logger_(logger)
{
    if (!j3) {
        throw std::invalid_argument("TrajectoryExecutor: j3 joint pointer must not be null");
    }
    if (!j4) {
        throw std::invalid_argument("TrajectoryExecutor: j4 joint pointer must not be null");
    }
    if (!j5) {
        throw std::invalid_argument("TrajectoryExecutor: j5 joint pointer must not be null");
    }
}

// ---------------------------------------------------------------------------
// Optional collaborator setters
// ---------------------------------------------------------------------------

void TrajectoryExecutor::setRecoveryManager(RecoveryManager* rm)
{
    recovery_manager_ = rm;
}

void TrajectoryExecutor::setCaptureSequence(CaptureSequence* cs)
{
    capture_sequence_ = cs;
}

// ---------------------------------------------------------------------------
// Internal helper: forward move result to RecoveryManager if set
// ---------------------------------------------------------------------------

void TrajectoryExecutor::recordMoveResult(int joint_id, MoveResult result)
{
    if (recovery_manager_) {
        recovery_manager_->recordMoveResult(joint_id, result);
    }
}

// ---------------------------------------------------------------------------
// executeApproach — J4 → J3 → J5 sequencing
// ---------------------------------------------------------------------------

bool TrajectoryExecutor::executeApproach(const PlannedTrajectory& traj,
                                         const ApproachParams& params)
{
    // Reset timing
    approach_j3_ms_ = 0.0;
    approach_j4_ms_ = 0.0;
    approach_j5_ms_ = 0.0;

    const double joint3_cmd = traj.j3_command;
    const double joint4_cmd = traj.j4_command;
    const double joint5_cmd = traj.j5_command;

    bool all_ok = true;

    // When not in simulation, use service mode for position confirmation so
    // that hardware failures are detected (blind_sleep always returns SUCCESS).
    if (!yanthra_move::simulation_mode.load()) {
        j3_->position_wait_mode_ = "service";
        j4_->position_wait_mode_ = "service";
        j5_->position_wait_mode_ = "service";
    }

    // ── Step 1/3: J4 (left/right positioning) ──────────────────────────
    auto j4_start = std::chrono::steady_clock::now();
    if (params.skip_j4) {
        RCLCPP_DEBUG(logger_, "[TE] Approach: J4 SKIP (skip_j4=true)");
    } else {
        RCLCPP_DEBUG(logger_, "[TE] Approach step 1/3: J4 → %.4f", joint4_cmd);
        auto result_j4 = j4_->move_joint(joint4_cmd, true);
        if (result_j4 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] J4 approach move failed (result=%d, target=%.4f)",
                        static_cast<int>(result_j4), joint4_cmd);
            all_ok = false;
        }
        recordMoveResult(4, result_j4);
    }
    auto j4_end = std::chrono::steady_clock::now();
    approach_j4_ms_ = static_cast<double>(
        std::chrono::duration_cast<std::chrono::milliseconds>(j4_end - j4_start).count());

    if (!all_ok) {
        return false;
    }

    // Inter-joint delay: J4 → J3
    // NOTE: spinOnce() was removed here — the background SingleThreadedExecutor
    // already processes all subscription callbacks continuously. Calling
    // rclcpp::spin_some(node_) from here crashed with "Node already added to
    // an executor" because the node is registered with the background executor.
    // BLOCKING_SLEEP_OK: main-thread inter-joint delay / motor travel wait — reviewed 2026-03-14
    yanthra_move::utilities::blockingThreadSleep(
        std::chrono::milliseconds(static_cast<int>(params.inter_joint_delay * 1000)));

    // ── Step 2/3: J3 (rotation angle) ─────────────────────────────────
    RCLCPP_DEBUG(logger_, "[TE] Approach step 2/3: J3 → %.4f", joint3_cmd);
    auto j3_start = std::chrono::steady_clock::now();
    {
        auto result_j3 = j3_->move_joint(joint3_cmd, true);
        if (result_j3 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] J3 approach move failed (result=%d, target=%.4f)",
                        static_cast<int>(result_j3), joint3_cmd);
            all_ok = false;
        }
        recordMoveResult(3, result_j3);
    }
    auto j3_end = std::chrono::steady_clock::now();
    approach_j3_ms_ = static_cast<double>(
        std::chrono::duration_cast<std::chrono::milliseconds>(j3_end - j3_start).count());

    if (!all_ok) {
        return false;
    }

    // Inter-joint delay: J3 → J5
    // NOTE: spinOnce() was removed here — see comment above J4→J3 delay.
    // BLOCKING_SLEEP_OK: main-thread inter-joint delay / motor travel wait — reviewed 2026-03-14
    yanthra_move::utilities::blockingThreadSleep(
        std::chrono::milliseconds(static_cast<int>(params.inter_joint_delay * 1000)));

    // ── Step 3/3: J5 (forward extension, non-blocking) ────────────────
    RCLCPP_DEBUG(logger_, "[TE] Approach step 3/3: J5 → %.4f", joint5_cmd);
    auto j5_start = std::chrono::steady_clock::now();
    {
        auto result_j5 = j5_->move_joint(joint5_cmd, false);  // Non-blocking (EE timing)
        if (result_j5 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] J5 approach move failed (result=%d, target=%.4f)",
                        static_cast<int>(result_j5), joint5_cmd);
            all_ok = false;
        }
        recordMoveResult(5, result_j5);
    }

    // In blind_sleep mode, wait for estimated travel time
    // BLOCKING_SLEEP_OK: main-thread inter-joint delay / motor travel wait — reviewed 2026-03-14
    yanthra_move::utilities::blockingThreadSleep(
        std::chrono::milliseconds(static_cast<int>(params.min_sleep_time * 1000)));

    auto j5_end = std::chrono::steady_clock::now();
    approach_j5_ms_ = static_cast<double>(
        std::chrono::duration_cast<std::chrono::milliseconds>(j5_end - j5_start).count());

    return all_ok;
}

// ---------------------------------------------------------------------------
// executeRetreat — J5 retract first, then conditional J3/J4 homing
// ---------------------------------------------------------------------------

bool TrajectoryExecutor::executeRetreat(const RetreatParams& params)
{
    retreat_j5_ms_ = 0.0;
    bool all_ok = true;

    // ── Step 1: Retract J5 (extension) to home ────────────────────────
    auto j5_start = std::chrono::steady_clock::now();
    if (params.home_j5) {
        RCLCPP_DEBUG(logger_, "[TE] Retreat step 1: J5 retract → %.4f", params.j5_home);
        auto r5 = j5_->move_joint(params.j5_home, false);  // Non-blocking
        if (r5 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] J5 retreat move failed (result=%d)",
                        static_cast<int>(r5));
        }
        recordMoveResult(5, r5);
    }

    // NOTE: spinOnce() was removed here — see comment in executeApproach().

    // Wait for J5 retraction to complete (min sleep)
    // BLOCKING_SLEEP_OK: main-thread inter-joint delay / motor travel wait — reviewed 2026-03-14
    yanthra_move::utilities::blockingThreadSleep(
        std::chrono::milliseconds(static_cast<int>(params.inter_joint_delay * 1000)));

    auto j5_end = std::chrono::steady_clock::now();
    retreat_j5_ms_ = static_cast<double>(
        std::chrono::duration_cast<std::chrono::milliseconds>(j5_end - j5_start).count());

    // ── Step 2: Conditional J3 homing ─────────────────────────────────
    if (params.home_j3) {
        // BLOCKING_SLEEP_OK: main-thread inter-joint delay / motor travel wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(params.inter_joint_delay * 1000)));

        RCLCPP_DEBUG(logger_, "[TE] Retreat step 2: J3 home → %.4f", params.j3_home);
        auto j3_result = j3_->move_joint(params.j3_home, true);
        if (j3_result != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] J3 retreat homing failed (result=%d)",
                        static_cast<int>(j3_result));
            all_ok = false;
        }
        recordMoveResult(3, j3_result);
        // NOTE: spinOnce() was removed here — see comment in executeApproach().
    }

    // ── Step 3: Conditional J4 homing ─────────────────────────────────
    if (params.home_j4) {
        // BLOCKING_SLEEP_OK: main-thread inter-joint delay / motor travel wait — reviewed 2026-03-14
        yanthra_move::utilities::blockingThreadSleep(
            std::chrono::milliseconds(static_cast<int>(params.inter_joint_delay * 1000)));

        RCLCPP_DEBUG(logger_, "[TE] Retreat step 3: J4 home → %.4f", params.j4_home);
        auto r4 = j4_->move_joint(params.j4_home, false);  // Non-blocking
        if (r4 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] J4 retreat homing failed (result=%d)",
                        static_cast<int>(r4));
        }
        recordMoveResult(4, r4);
    }

    return all_ok;
}

// ---------------------------------------------------------------------------
// moveToHomePosition — fire-and-forget all joints to home
// ---------------------------------------------------------------------------

void TrajectoryExecutor::moveToHomePosition(double j3_home, double j5_home,
                                            double j4_home)
{
    RCLCPP_DEBUG(logger_, "[TE] Moving to home: j3=%.4f j5=%.4f j4=%.4f",
                 j3_home, j5_home, j4_home);

    // J3 first (non-blocking)
    (void)j3_->move_joint(j3_home, false);

    // J5 (non-blocking)
    (void)j5_->move_joint(j5_home, false);

    // J4 (non-blocking)
    (void)j4_->move_joint(j4_home, false);
}

// ---------------------------------------------------------------------------
// moveToPackingPosition — command all joints, optionally wait for feedback
// ---------------------------------------------------------------------------

bool TrajectoryExecutor::moveToPackingPosition(double j3_home, double j5_home,
                                               double j4_home,
                                               const std::string& position_wait_mode)
{
    RCLCPP_DEBUG(logger_, "[TE] Moving to packing: j3=%.4f j5=%.4f j4=%.4f mode=%s",
                 j3_home, j5_home, j4_home, position_wait_mode.c_str());

    bool all_ok = true;

    // J5 first (blocking — retract extension before rotating)
    {
        auto r5 = j5_->move_joint(j5_home, true);
        recordMoveResult(5, r5);
        if (r5 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] Packing J5 failed (result=%d)", static_cast<int>(r5));
            all_ok = false;
        }
    }

    // J3 (blocking)
    {
        auto r3 = j3_->move_joint(j3_home, true);
        recordMoveResult(3, r3);
        if (r3 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] Packing J3 failed (result=%d)", static_cast<int>(r3));
            all_ok = false;
        }
    }

    // J4 (blocking)
    {
        auto r4 = j4_->move_joint(j4_home, true);
        recordMoveResult(4, r4);
        if (r4 != MoveResult::SUCCESS) {
            RCLCPP_WARN(logger_, "[TE] Packing J4 failed (result=%d)", static_cast<int>(r4));
            all_ok = false;
        }
    }

    // In simulation or blind_sleep mode, position is always "reached"
    if (yanthra_move::simulation_mode.load() || position_wait_mode == "blind_sleep") {
        return true;
    }

    return all_ok;
}

// ---------------------------------------------------------------------------
// L3 parking / homing helpers
// ---------------------------------------------------------------------------

void TrajectoryExecutor::moveL3ToParking(double parking_position)
{
    RCLCPP_DEBUG(logger_, "[TE] L3 → parking: %.4f", parking_position);
    (void)j3_->move_joint(parking_position, true);
}

void TrajectoryExecutor::moveL3ToHoming(double homing_position)
{
    RCLCPP_DEBUG(logger_, "[TE] L3 → homing: %.4f", homing_position);
    (void)j3_->move_joint(homing_position, true);
}

// ---------------------------------------------------------------------------
// waitForPositionFeedback
// ---------------------------------------------------------------------------

bool TrajectoryExecutor::waitForPositionFeedback(const std::string& joint_name,
                                                 double target,
                                                 double tolerance,
                                                 double timeout_sec)
{
    // In simulation mode, position is always "reached"
    if (yanthra_move::simulation_mode.load()) {
        RCLCPP_DEBUG(logger_, "[TE] waitForPositionFeedback: simulation mode — returning true");
        return true;
    }

    // blind_sleep mode: no feedback available, assume success
    // (Caller should not call this in blind_sleep mode, but handle gracefully)
    RCLCPP_DEBUG(logger_, "[TE] waitForPositionFeedback: %s target=%.4f tol=%.4f timeout=%.1fs",
                 joint_name.c_str(), target, tolerance, timeout_sec);

    // Real position feedback polling would go here (subscriber to /joint_states).
    // For now, in the decomposed design, return true — the MotionController-level
    // feedback loop will be migrated in a separate task.
    return true;
}

}}  // namespace yanthra_move::core
