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

#include "yanthra_move/core/recovery_manager.hpp"
#include "yanthra_move/error_recovery_types.hpp"
#include "yanthra_move/joint_move.h"

namespace yanthra_move { namespace core {

RecoveryManager::RecoveryManager(rclcpp::Logger logger)
    : logger_(logger) {}

// ---------------------------------------------------------------------------
// Move failure tracking
// ---------------------------------------------------------------------------

void RecoveryManager::recordMoveResult(int joint_id, MoveResult result) {
    std::atomic<int>* consecutive = nullptr;
    std::atomic<int>* cumulative = nullptr;

    switch (joint_id) {
        case 3:
            consecutive = &consecutive_move_failures_j3_;
            cumulative = &cumulative_move_failures_j3_;
            break;
        case 4:
            consecutive = &consecutive_move_failures_j4_;
            cumulative = &cumulative_move_failures_j4_;
            break;
        case 5:
            consecutive = &consecutive_move_failures_j5_;
            cumulative = &cumulative_move_failures_j5_;
            break;
        default:
            return;  // Unknown joint
    }

    if (result == MoveResult::SUCCESS) {
        consecutive->store(0);
    } else {
        int new_consecutive = consecutive->fetch_add(1) + 1;
        int new_cumulative = cumulative->fetch_add(1) + 1;
        RCLCPP_WARN(logger_,
            "[MOVE] Joint %d failure recorded: result=%d, consecutive=%d, cumulative=%d",
            joint_id, static_cast<int>(result), new_consecutive, new_cumulative);

        // Dispatch to centralized error recovery when threshold exceeded
        if (failure_callback_ && new_consecutive >= consecutive_failure_threshold_) {
            yanthra_move::FailureContext ctx;
            ctx.joint_id = joint_id;
            ctx.cycle_count = cycle_count_.load();
            auto failure_type = (result == MoveResult::TIMEOUT)
                ? yanthra_move::FailureType::MOTOR_TIMEOUT
                : yanthra_move::FailureType::MOTOR_ERROR;
            failure_callback_(failure_type, ctx);
        }
    }
}

int RecoveryManager::getConsecutiveMoveFailures(int joint_id) const {
    switch (joint_id) {
        case 3: return consecutive_move_failures_j3_.load();
        case 4: return consecutive_move_failures_j4_.load();
        case 5: return consecutive_move_failures_j5_.load();
        default: return 0;
    }
}

int RecoveryManager::getCumulativeMoveFailures(int joint_id) const {
    switch (joint_id) {
        case 3: return cumulative_move_failures_j3_.load();
        case 4: return cumulative_move_failures_j4_.load();
        case 5: return cumulative_move_failures_j5_.load();
        default: return 0;
    }
}

// ---------------------------------------------------------------------------
// Callback configuration
// ---------------------------------------------------------------------------

void RecoveryManager::setFailureCallback(FailureCallback cb) {
    failure_callback_ = std::move(cb);
}

void RecoveryManager::setConsecutiveFailureThreshold(int threshold) {
    consecutive_failure_threshold_ = threshold;
}

void RecoveryManager::dispatchFailure(yanthra_move::FailureType type, const yanthra_move::FailureContext& ctx) {
    if (failure_callback_) {
        failure_callback_(type, ctx);
    }
}

// ---------------------------------------------------------------------------
// Stat incrementers
// ---------------------------------------------------------------------------

void RecoveryManager::incrementTfFailures() {
    tf_failure_count_.fetch_add(1);
}

void RecoveryManager::incrementInvalidCoordinates() {
    invalid_coordinate_count_.fetch_add(1);
}

void RecoveryManager::incrementJointLimitFailures() {
    joint_limit_failure_count_.fetch_add(1);
}

void RecoveryManager::incrementPositionFeedbackFailure(int joint_id) {
    position_feedback_failure_count_.fetch_add(1);
    switch (joint_id) {
        case 3: position_feedback_failures_j3_.fetch_add(1); break;
        case 4: position_feedback_failures_j4_.fetch_add(1); break;
        case 5: position_feedback_failures_j5_.fetch_add(1); break;
        default: break;
    }
}

void RecoveryManager::incrementEeActivations() {
    ee_activation_count_.fetch_add(1);
}

void RecoveryManager::incrementCompressorActivations() {
    compressor_activation_count_.fetch_add(1);
}

void RecoveryManager::recordPickAttempt() {
    total_picks_attempted_.fetch_add(1);
}

void RecoveryManager::recordPickSuccess() {
    total_picks_successful_.fetch_add(1);
}

void RecoveryManager::addPickDuration(uint64_t ms) {
    total_pick_duration_ms_.fetch_add(ms);
}

void RecoveryManager::recordPickTimeout() {
    total_picks_timed_out_.fetch_add(1);
}

// ---------------------------------------------------------------------------
// Stat accessors
// ---------------------------------------------------------------------------

int RecoveryManager::getTfFailureCount() const {
    return tf_failure_count_.load();
}

int RecoveryManager::getInvalidCoordinateCount() const {
    return invalid_coordinate_count_.load();
}

int RecoveryManager::getJointLimitFailureCount() const {
    return joint_limit_failure_count_.load();
}

int RecoveryManager::getPositionFeedbackFailureCount() const {
    return position_feedback_failure_count_.load();
}

int RecoveryManager::getPositionFeedbackFailureJ3() const {
    return position_feedback_failures_j3_.load();
}

int RecoveryManager::getPositionFeedbackFailureJ4() const {
    return position_feedback_failures_j4_.load();
}

int RecoveryManager::getPositionFeedbackFailureJ5() const {
    return position_feedback_failures_j5_.load();
}

int RecoveryManager::getEeActivationCount() const {
    return ee_activation_count_.load();
}

int RecoveryManager::getCompressorActivationCount() const {
    return compressor_activation_count_.load();
}

int RecoveryManager::getTotalPicksAttempted() const {
    return total_picks_attempted_.load();
}

int RecoveryManager::getTotalPicksSuccessful() const {
    return total_picks_successful_.load();
}

double RecoveryManager::getAveragePickDurationMs() const {
    int attempts = total_picks_attempted_.load();
    if (attempts == 0) {
        return 0.0;
    }
    return static_cast<double>(total_pick_duration_ms_.load()) / attempts;
}

int RecoveryManager::getTotalPicksTimedOut() const {
    return total_picks_timed_out_.load();
}

// ---------------------------------------------------------------------------
// Cycle count tracking
// ---------------------------------------------------------------------------

void RecoveryManager::setCycleCount(int count) {
    cycle_count_.store(count);
}

}}  // namespace yanthra_move::core
