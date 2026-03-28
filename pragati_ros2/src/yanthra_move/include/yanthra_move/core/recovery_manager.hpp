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

#include <atomic>
#include <cstdint>
#include <functional>
#include <rclcpp/rclcpp.hpp>

// Forward declarations
enum class MoveResult : int;
namespace yanthra_move { enum class FailureType; struct FailureContext; }

namespace yanthra_move { namespace core {

class RecoveryManager {
public:
    using FailureCallback = std::function<void(yanthra_move::FailureType, const yanthra_move::FailureContext&)>;

    explicit RecoveryManager(rclcpp::Logger logger);

    // Move failure tracking
    void recordMoveResult(int joint_id, MoveResult result);
    int getConsecutiveMoveFailures(int joint_id) const;
    int getCumulativeMoveFailures(int joint_id) const;

    // Callback configuration
    void setFailureCallback(FailureCallback cb);
    void setConsecutiveFailureThreshold(int threshold);
    void dispatchFailure(yanthra_move::FailureType type, const yanthra_move::FailureContext& ctx);

    // Stat incrementers
    void incrementTfFailures();
    void incrementInvalidCoordinates();
    void incrementJointLimitFailures();
    void incrementPositionFeedbackFailure(int joint_id);
    void incrementEeActivations();
    void incrementCompressorActivations();
    void recordPickAttempt();
    void recordPickSuccess();
    void addPickDuration(uint64_t ms);
    void recordPickTimeout();

    // Stat accessors
    int getTfFailureCount() const;
    int getInvalidCoordinateCount() const;
    int getJointLimitFailureCount() const;
    int getPositionFeedbackFailureCount() const;
    int getPositionFeedbackFailureJ3() const;
    int getPositionFeedbackFailureJ4() const;
    int getPositionFeedbackFailureJ5() const;
    int getEeActivationCount() const;
    int getCompressorActivationCount() const;
    int getTotalPicksAttempted() const;
    int getTotalPicksSuccessful() const;
    double getAveragePickDurationMs() const;
    int getTotalPicksTimedOut() const;

    // Cycle count tracking (for failure context)
    void setCycleCount(int count);

private:
    rclcpp::Logger logger_;

    // Per-joint failure counters
    std::atomic<int> consecutive_move_failures_j3_{0};
    std::atomic<int> consecutive_move_failures_j4_{0};
    std::atomic<int> consecutive_move_failures_j5_{0};
    std::atomic<int> cumulative_move_failures_j3_{0};
    std::atomic<int> cumulative_move_failures_j4_{0};
    std::atomic<int> cumulative_move_failures_j5_{0};

    // Failure callback
    FailureCallback failure_callback_;
    int consecutive_failure_threshold_{3};
    std::atomic<int> cycle_count_{0};

    // Stat counters
    std::atomic<int> tf_failure_count_{0};
    std::atomic<int> invalid_coordinate_count_{0};
    std::atomic<int> joint_limit_failure_count_{0};
    std::atomic<int> position_feedback_failure_count_{0};
    std::atomic<int> position_feedback_failures_j3_{0};
    std::atomic<int> position_feedback_failures_j4_{0};
    std::atomic<int> position_feedback_failures_j5_{0};
    std::atomic<int> ee_activation_count_{0};
    std::atomic<int> compressor_activation_count_{0};
    std::atomic<int> total_picks_attempted_{0};
    std::atomic<int> total_picks_successful_{0};
    std::atomic<uint64_t> total_pick_duration_ms_{0};
    std::atomic<int> total_picks_timed_out_{0};
};

}}  // namespace yanthra_move::core
