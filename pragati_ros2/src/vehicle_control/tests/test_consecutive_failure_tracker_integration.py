#!/usr/bin/env python3
"""
Tests for ConsecutiveFailureTracker Python module.

Task 4.26: Verify the tracker used in safety_manager's monitoring loop.

The tracker API:
- increment() -> bool: increment count, return True if threshold exceeded
- reset(): reset count to 0
- exceeded(custom_threshold=None) -> bool: check if count >= threshold
- count (property): current failure count
- threshold (property): configured threshold
"""

import os
import sys
import threading

import pytest

# Add common_utils package root to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "common_utils",
    ),
)

from common_utils.consecutive_failure_tracker import ConsecutiveFailureTracker


class TestConsecutiveFailureTracker:
    """Tests for ConsecutiveFailureTracker core behavior."""

    def test_initial_state(self):
        """New tracker starts at count 0."""
        t = ConsecutiveFailureTracker(threshold=3)
        assert t.count == 0
        assert t.threshold == 3

    def test_threshold_not_reached(self):
        """increment() returns False when below threshold."""
        t = ConsecutiveFailureTracker(threshold=3)
        assert t.increment() is False  # count=1
        assert t.increment() is False  # count=2

    def test_threshold_reached(self):
        """increment() returns True when threshold is reached."""
        t = ConsecutiveFailureTracker(threshold=3)
        t.increment()  # count=1
        t.increment()  # count=2
        assert t.increment() is True  # count=3

    def test_threshold_exceeded_continues_returning_true(self):
        """increment() keeps returning True after threshold is exceeded."""
        t = ConsecutiveFailureTracker(threshold=2)
        t.increment()  # count=1
        assert t.increment() is True  # count=2
        assert t.increment() is True  # count=3

    def test_reset_clears_count(self):
        """reset() sets count back to 0."""
        t = ConsecutiveFailureTracker(threshold=3)
        t.increment()
        t.increment()
        t.reset()
        assert t.count == 0

    def test_reset_allows_recount(self):
        """After reset, threshold is not exceeded until count reaches it again."""
        t = ConsecutiveFailureTracker(threshold=3)
        t.increment()
        t.increment()
        t.reset()
        assert t.increment() is False  # count=1
        assert t.increment() is False  # count=2
        assert t.increment() is True  # count=3

    def test_exceeded_check(self):
        """exceeded() reflects whether count >= threshold."""
        t = ConsecutiveFailureTracker(threshold=3)
        assert t.exceeded() is False
        t.increment()
        t.increment()
        assert t.exceeded() is False
        t.increment()
        assert t.exceeded() is True

    def test_exceeded_custom_threshold(self):
        """exceeded() accepts a custom threshold override."""
        t = ConsecutiveFailureTracker(threshold=5)
        t.increment()
        t.increment()
        assert t.exceeded(custom_threshold=2) is True
        assert t.exceeded() is False  # default threshold=5 not reached

    def test_default_threshold_is_five(self):
        """Default threshold is 5 when not specified."""
        t = ConsecutiveFailureTracker()
        assert t.threshold == 5

    def test_count_property(self):
        """count property tracks current failure count."""
        t = ConsecutiveFailureTracker(threshold=10)
        assert t.count == 0
        for i in range(7):
            t.increment()
        assert t.count == 7

    def test_threshold_property(self):
        """threshold property returns configured threshold."""
        t = ConsecutiveFailureTracker(threshold=42)
        assert t.threshold == 42


class TestConsecutiveFailureTrackerThreadSafety:
    """Thread safety tests for ConsecutiveFailureTracker."""

    def test_concurrent_increments(self):
        """Concurrent increments don't lose counts."""
        t = ConsecutiveFailureTracker(threshold=1000)
        num_threads = 10
        increments_per_thread = 100

        def worker():
            for _ in range(increments_per_thread):
                t.increment()

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert t.count == num_threads * increments_per_thread

    def test_concurrent_increment_and_reset(self):
        """Concurrent increment and reset don't cause crashes."""
        t = ConsecutiveFailureTracker(threshold=100)
        errors = []

        def incrementer():
            try:
                for _ in range(1000):
                    t.increment()
            except Exception as e:
                errors.append(e)

        def resetter():
            try:
                for _ in range(100):
                    t.reset()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=incrementer),
            threading.Thread(target=resetter),
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
