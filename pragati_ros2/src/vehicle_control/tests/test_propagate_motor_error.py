#!/usr/bin/env python3
"""
Tests for @propagate_motor_error decorator.

Task 4.25: Decorator sets _degraded[motor_id]=True on failure,
           clears on success, logs errors, and re-raises exceptions.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hardware.motor_controller import propagate_motor_error


class MockMotorController:
    """Minimal mock that matches the interface expected by propagate_motor_error."""

    def __init__(self):
        self._degraded = {}
        self._logger = MagicMock()

    @propagate_motor_error
    def good_command(self, motor_id):
        """A command that succeeds."""
        return True

    @propagate_motor_error
    def bad_command(self, motor_id):
        """A command that raises RuntimeError."""
        raise RuntimeError("Motor fault")

    @propagate_motor_error
    def bad_value_error(self, motor_id):
        """A command that raises ValueError."""
        raise ValueError("Invalid position")

    @propagate_motor_error
    def command_with_kwargs(self, motor_id=None):
        """A command using keyword argument for motor_id."""
        return True

    @propagate_motor_error
    def command_with_no_args(self):
        """A command with no motor_id argument."""
        return True


class TestPropagateMotorError:
    """Tests for the @propagate_motor_error decorator."""

    def test_success_returns_value(self):
        """Decorated method returns its original return value on success."""
        mc = MockMotorController()
        result = mc.good_command(1)
        assert result is True

    def test_success_clears_degraded(self):
        """On success, degraded flag for motor_id is cleared."""
        mc = MockMotorController()
        mc._degraded[1] = True
        mc.good_command(1)
        assert mc._degraded[1] is False

    def test_failure_sets_degraded(self):
        """On failure, degraded flag for motor_id is set to True."""
        mc = MockMotorController()
        with pytest.raises(RuntimeError):
            mc.bad_command(1)
        assert mc._degraded[1] is True

    def test_failure_reraises_exception(self):
        """On failure, the original exception is re-raised."""
        mc = MockMotorController()
        with pytest.raises(RuntimeError, match="Motor fault"):
            mc.bad_command(1)

    def test_failure_reraises_different_exception_types(self):
        """Decorator re-raises any exception type, not just RuntimeError."""
        mc = MockMotorController()
        with pytest.raises(ValueError, match="Invalid position"):
            mc.bad_value_error(1)
        assert mc._degraded[1] is True

    def test_logs_on_failure(self):
        """Decorator logs an error message on failure."""
        mc = MockMotorController()
        with pytest.raises(RuntimeError):
            mc.bad_command(1)
        mc._logger.error.assert_called_once()
        log_msg = mc._logger.error.call_args[0][0]
        assert "bad_command" in log_msg
        assert "motor_id=1" in log_msg

    def test_no_log_on_success(self):
        """Decorator does not log on success."""
        mc = MockMotorController()
        mc.good_command(1)
        mc._logger.error.assert_not_called()

    def test_kwargs_motor_id(self):
        """Decorator extracts motor_id from keyword arguments."""
        mc = MockMotorController()
        mc._degraded[42] = True
        mc.command_with_kwargs(motor_id=42)
        assert mc._degraded[42] is False

    def test_no_motor_id_does_not_crash(self):
        """Decorator handles methods with no motor_id gracefully."""
        mc = MockMotorController()
        result = mc.command_with_no_args()
        assert result is True

    def test_multiple_motors_independent(self):
        """Degraded state is tracked independently per motor_id."""
        mc = MockMotorController()

        # Motor 1 fails
        with pytest.raises(RuntimeError):
            mc.bad_command(1)

        # Motor 2 succeeds
        mc.good_command(2)

        assert mc._degraded[1] is True
        assert mc._degraded[2] is False

    def test_preserves_function_name(self):
        """Decorator preserves the original function name via functools.wraps."""
        mc = MockMotorController()
        assert mc.good_command.__name__ == "good_command"
        assert mc.bad_command.__name__ == "bad_command"
