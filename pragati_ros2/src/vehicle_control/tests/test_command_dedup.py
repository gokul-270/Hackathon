#!/usr/bin/env python3
"""
Tests for vehicle command deduplication logic.

Tasks 14-18 of the vehicle-command-dedup change.
CommandDedup prevents re-publishing identical (within epsilon) position
commands to ROS2 motor controller topics.

RED phase: these tests will fail with ImportError until the implementation
exists at utils/command_dedup.py.
"""

import pytest
from unittest.mock import MagicMock

from utils.command_dedup import CommandDedup

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dedup():
    """Fresh CommandDedup instance with no logger."""
    return CommandDedup()


@pytest.fixture
def dedup_with_logger():
    """CommandDedup backed by a mock logger for log-emission assertions."""
    logger = MagicMock()
    return CommandDedup(logger=logger), logger


# ---------------------------------------------------------------------------
# Task 14: First command always sent
# ---------------------------------------------------------------------------


class TestFirstCommandAlwaysSent:
    """When no cache exists for a motor, dedup must allow the command."""

    def test_first_command_returns_true(self, dedup):
        """should_send() returns True for a joint seen for the first time."""
        assert dedup.should_send("front_left_steering", 45.0) is True

    def test_first_command_populates_cache(self, dedup):
        """After sending, the cache stores the position for that joint."""
        dedup.should_send("front_left_steering", 45.0)
        assert "front_left_steering" in dedup._cache
        assert dedup._cache["front_left_steering"] == 45.0

    def test_first_command_different_joints_independent(self, dedup):
        """Each joint gets its own independent cache entry."""
        assert dedup.should_send("front_left_steering", 10.0) is True
        assert dedup.should_send("front_right_steering", 20.0) is True
        assert dedup._cache["front_left_steering"] == 10.0
        assert dedup._cache["front_right_steering"] == 20.0


# ---------------------------------------------------------------------------
# Task 15: Duplicate command skipped
# ---------------------------------------------------------------------------


class TestDuplicateCommandSkipped:
    """A command within EPSILON of the cached value must be suppressed."""

    def test_identical_value_skipped(self, dedup):
        """Exact same value is skipped."""
        dedup.should_send("steer", 45.0)
        assert dedup.should_send("steer", 45.0) is False

    def test_within_epsilon_skipped(self, dedup):
        """Value differing by < EPSILON (0.01 deg) is skipped."""
        dedup.should_send("steer", 45.0)
        assert dedup.should_send("steer", 45.005) is False

    def test_cache_unchanged_after_skip(self, dedup):
        """Cache retains the original value when a duplicate is skipped."""
        dedup.should_send("steer", 45.0)
        dedup.should_send("steer", 45.005)
        assert dedup._cache["steer"] == 45.0


# ---------------------------------------------------------------------------
# Task 16: Changed command sent
# ---------------------------------------------------------------------------


class TestChangedCommandSent:
    """A command outside EPSILON of the cached value must be dispatched."""

    def test_large_change_sent(self, dedup):
        """1-degree change is clearly above epsilon — command sent."""
        dedup.should_send("steer", 45.0)
        assert dedup.should_send("steer", 46.0) is True

    def test_cache_updated_after_send(self, dedup):
        """Cache is updated to the new target after a non-duplicate send."""
        dedup.should_send("steer", 45.0)
        dedup.should_send("steer", 46.0)
        assert dedup._cache["steer"] == 46.0

    def test_skip_counter_resets_on_new_value(self, dedup):
        """Skip counter for the joint resets to 0 after a real send."""
        dedup.should_send("steer", 45.0)
        # Accumulate some skips
        for _ in range(5):
            dedup.should_send("steer", 45.0)
        assert dedup._skip_counts["steer"] == 5
        # Now send a genuinely different command
        dedup.should_send("steer", 46.0)
        assert dedup._skip_counts["steer"] == 0


# ---------------------------------------------------------------------------
# Task 17: Epsilon boundary
# ---------------------------------------------------------------------------


class TestEpsilonBoundary:
    """Verify the strict-less-than boundary: abs(diff) < 0.01."""

    def test_just_below_epsilon_skipped(self, dedup):
        """0.009 deg difference (< 0.01) → skip."""
        dedup.should_send("steer", 0.0)
        assert dedup.should_send("steer", 0.009) is False

    def test_just_above_epsilon_sent(self, dedup):
        """0.011 deg difference (> 0.01) → send."""
        dedup.should_send("steer", 0.0)
        assert dedup.should_send("steer", 0.011) is True

    def test_exactly_at_epsilon_sent(self, dedup):
        """Exactly 0.01 deg difference (not < 0.01) → send.

        The check is strict-less-than, so exactly epsilon is NOT skipped.
        """
        dedup.should_send("steer", 0.0)
        assert dedup.should_send("steer", 0.01) is True

    def test_negative_direction_boundary(self, dedup):
        """Epsilon boundary works in the negative direction too."""
        dedup.should_send("steer", 10.0)
        assert dedup.should_send("steer", 9.989) is True  # diff = 0.011 → send
        # Reset to known state
        dedup2 = CommandDedup()
        dedup2.should_send("steer", 10.0)
        assert dedup2.should_send("steer", 9.991) is False  # diff = 0.009 → skip


# ---------------------------------------------------------------------------
# Task 18: Dedup counter logging
# ---------------------------------------------------------------------------


class TestDedupCounterLogging:
    """Every LOG_INTERVAL (100) skips, a DEBUG message must be emitted."""

    def test_log_emitted_at_100_skips(self, dedup_with_logger):
        """After exactly 100 duplicate skips, logger.debug is called once."""
        dedup, logger = dedup_with_logger
        dedup.should_send("steer", 45.0)

        for _ in range(100):
            dedup.should_send("steer", 45.0)

        assert logger.debug.call_count == 1

    def test_log_message_contains_joint_name(self, dedup_with_logger):
        """The log message includes the joint name for traceability."""
        dedup, logger = dedup_with_logger
        dedup.should_send("front_left_drive", 0.0)

        for _ in range(100):
            dedup.should_send("front_left_drive", 0.0)

        log_msg = logger.debug.call_args[0][0]
        assert "front_left_drive" in log_msg

    def test_log_message_contains_skip_count(self, dedup_with_logger):
        """The log message includes the cumulative skip count."""
        dedup, logger = dedup_with_logger
        dedup.should_send("steer", 0.0)

        for _ in range(100):
            dedup.should_send("steer", 0.0)

        log_msg = logger.debug.call_args[0][0]
        assert "100" in log_msg

    def test_log_emitted_at_each_interval(self, dedup_with_logger):
        """Log fires at 100, 200, 300 — once per interval."""
        dedup, logger = dedup_with_logger
        dedup.should_send("steer", 0.0)

        for _ in range(300):
            dedup.should_send("steer", 0.0)

        assert logger.debug.call_count == 3

    def test_no_log_before_interval(self, dedup_with_logger):
        """No DEBUG log before the first 100 skips."""
        dedup, logger = dedup_with_logger
        dedup.should_send("steer", 0.0)

        for _ in range(99):
            dedup.should_send("steer", 0.0)

        logger.debug.assert_not_called()

    def test_no_log_when_no_logger(self, dedup):
        """With logger=None, 100 skips complete without error."""
        dedup.should_send("steer", 0.0)
        # Should not raise even though there is no logger
        for _ in range(100):
            dedup.should_send("steer", 0.0)
