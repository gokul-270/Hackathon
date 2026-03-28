# Copyright 2025 Pragati Robotics
# SPDX-License-Identifier: Apache-2.0
"""Consecutive failure tracker for monitoring loops.

Counts consecutive failures and triggers after exceeding a threshold.
Thread-safe via threading.Lock.
"""

import threading


class ConsecutiveFailureTracker:
    """Track consecutive failures and trigger after threshold exceeded.

    Args:
        threshold: Number of consecutive failures before exceeded() returns True.
                   Default is 5.
    """

    def __init__(self, threshold: int = 5):
        self._threshold = threshold
        self._count = 0
        self._lock = threading.Lock()

    def increment(self) -> bool:
        """Increment failure count. Returns True if threshold is now exceeded."""
        with self._lock:
            self._count += 1
            return self._count >= self._threshold

    def reset(self) -> None:
        """Reset failure count to zero (call on success)."""
        with self._lock:
            self._count = 0

    def exceeded(self, custom_threshold: int | None = None) -> bool:
        """Check if failure count has reached or exceeded the threshold.

        Args:
            custom_threshold: Optional override for the configured threshold.
        """
        with self._lock:
            threshold = custom_threshold if custom_threshold is not None else self._threshold
            return self._count >= threshold

    @property
    def count(self) -> int:
        """Current failure count."""
        with self._lock:
            return self._count

    @property
    def threshold(self) -> int:
        """Configured threshold."""
        return self._threshold
