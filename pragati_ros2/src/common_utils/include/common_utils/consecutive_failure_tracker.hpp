// Copyright 2025 Pragati Robotics Team
// SPDX-License-Identifier: Apache-2.0
//
// Header-only consecutive failure tracker for monitoring loops.
// Counts consecutive failures and triggers after exceeding a threshold.
// Thread-safe via std::atomic.

#pragma once

#include <atomic>
#include <cstdint>

namespace pragati {

class ConsecutiveFailureTracker {
public:
  explicit ConsecutiveFailureTracker(uint32_t threshold = 5)
    : threshold_(threshold), count_(0) {}

  /// Increment failure count. Returns true if threshold is now exceeded.
  bool increment() {
    uint32_t new_count = count_.fetch_add(1, std::memory_order_relaxed) + 1;
    return new_count >= threshold_;
  }

  /// Reset failure count to zero (call on success).
  void reset() {
    count_.store(0, std::memory_order_relaxed);
  }

  /// Check if failure count has reached or exceeded the threshold.
  bool exceeded() const {
    return count_.load(std::memory_order_relaxed) >= threshold_;
  }

  /// Check if failure count has reached or exceeded a custom threshold.
  bool exceeded(uint32_t custom_threshold) const {
    return count_.load(std::memory_order_relaxed) >= custom_threshold;
  }

  /// Get current failure count.
  uint32_t count() const {
    return count_.load(std::memory_order_relaxed);
  }

  /// Get configured threshold.
  uint32_t threshold() const {
    return threshold_;
  }

private:
  uint32_t threshold_;
  std::atomic<uint32_t> count_;
};

}  // namespace pragati
