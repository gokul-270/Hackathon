#!/usr/bin/env python3
"""
Tests for emergency stop retry+escalation behavior.

Task 4.23: motor_controller.py emergency_stop retries 3 times with exponential backoff,
           raises RuntimeError on exhaustion.
Task 4.24: safety_manager.py emergency_stop retries 3 times with exponential backoff,
           sets _estop_incomplete flag on exhaustion.
"""

import time
import sys
import os

import pytest
from unittest.mock import MagicMock, patch, call

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# Add common_utils package root to path (needed by safety_manager.py)
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "common_utils",
    ),
)

from hardware.motor_controller import VehicleMotorController
from core.safety_manager import SafetyManager


class TestMotorControllerEmergencyStop:
    """Tests for VehicleMotorController.emergency_stop retry behavior."""

    def _make_controller(self, motor_interface=None):
        """Create a VehicleMotorController with a mock motor interface."""
        mi = motor_interface or MagicMock()
        # get_status must return a valid MotorStatus-like object for init
        mi.initialize.return_value = True
        mi.get_status.return_value = MagicMock(error_code=0)
        mi.clear_errors.return_value = True
        controller = VehicleMotorController(mi)
        return controller

    def test_succeeds_on_first_attempt(self):
        """Emergency stop succeeds immediately on first attempt."""
        mi = MagicMock()
        mi.disable_motor.return_value = True
        ctrl = self._make_controller(mi)

        result = ctrl.emergency_stop()

        assert result is True
        # All motors disabled at least once
        assert mi.disable_motor.call_count > 0

    def test_retries_on_failure_then_succeeds(self):
        """Emergency stop retries on failure and succeeds on later attempt."""
        mi = MagicMock()
        # Fail first 2 attempts (raises on first motor), succeed on 3rd
        mi.disable_motor.side_effect = [
            RuntimeError("CAN timeout"),  # attempt 1, motor 1 fails
            RuntimeError("CAN timeout"),  # attempt 2, motor 1 fails
            True,
            True,
            True,
            True,
            True,
            True,  # attempt 3, all 6 motors succeed
        ]
        ctrl = self._make_controller(mi)

        result = ctrl.emergency_stop()

        assert result is True

    def test_raises_runtime_error_on_exhaustion(self):
        """Emergency stop raises RuntimeError after all 3 attempts fail."""
        mi = MagicMock()
        mi.disable_motor.side_effect = RuntimeError("CAN bus dead")
        ctrl = self._make_controller(mi)

        with pytest.raises(RuntimeError, match="Emergency stop failed"):
            ctrl.emergency_stop()

    def test_three_retry_attempts(self):
        """Emergency stop makes exactly 3 attempts before raising."""
        mi = MagicMock()
        # Each attempt fails on the first motor
        mi.disable_motor.side_effect = RuntimeError("CAN bus dead")
        ctrl = self._make_controller(mi)

        with pytest.raises(RuntimeError):
            ctrl.emergency_stop()

        # 3 attempts, each fails on first motor
        assert mi.disable_motor.call_count == 3

    @patch("hardware.motor_controller.time.sleep")
    def test_backoff_timing(self, mock_sleep):
        """Backoff uses exponential delays between retries."""
        mi = MagicMock()
        mi.disable_motor.side_effect = RuntimeError("CAN bus dead")
        ctrl = self._make_controller(mi)

        with pytest.raises(RuntimeError):
            ctrl.emergency_stop()

        # Should sleep between attempts with exponential backoff
        # backoff_times = [0.01, 0.1, 1.0] — sleep after attempts 1 and 2
        assert mock_sleep.call_count == 2
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert sleep_calls[0] == pytest.approx(0.01)
        assert sleep_calls[1] == pytest.approx(0.1)

    def test_emergency_stop_sets_event(self):
        """Emergency stop sets the _emergency_stop threading.Event."""
        mi = MagicMock()
        mi.disable_motor.return_value = True
        ctrl = self._make_controller(mi)

        ctrl.emergency_stop()

        assert ctrl._emergency_stop.is_set()


class TestSafetyManagerEmergencyStop:
    """Tests for SafetyManager.emergency_stop retry behavior."""

    def _make_manager(self, motor_controller=None):
        """Create a SafetyManager with a mock motor controller."""
        mc = motor_controller or MagicMock()
        return SafetyManager(motor_controller=mc)

    def test_succeeds_on_first_attempt(self):
        """Emergency stop succeeds immediately — _estop_incomplete is False."""
        mc = MagicMock()
        mc.emergency_stop.return_value = True
        mgr = self._make_manager(mc)

        result = mgr.emergency_stop("test")

        assert result is True
        assert mgr._estop_incomplete is False
        assert mgr._emergency_stop_active is True

    def test_sets_estop_incomplete_on_all_retries_failed(self):
        """_estop_incomplete flag set when all retries exhausted."""
        mc = MagicMock()
        mc.emergency_stop.side_effect = RuntimeError("motor stop failed")
        mgr = self._make_manager(mc)

        result = mgr.emergency_stop("test")

        assert result is False
        assert mgr._estop_incomplete is True

    @patch("core.safety_manager.time.sleep")
    def test_three_retry_attempts(self, mock_sleep):
        """SafetyManager makes exactly 3 attempts on its own level."""
        mc = MagicMock()
        mc.emergency_stop.side_effect = RuntimeError("motor stop failed")
        mgr = self._make_manager(mc)

        mgr.emergency_stop("test")

        assert mc.emergency_stop.call_count == 3

    @patch("core.safety_manager.time.sleep")
    def test_backoff_timing(self, mock_sleep):
        """SafetyManager uses exponential backoff between retries."""
        mc = MagicMock()
        mc.emergency_stop.side_effect = RuntimeError("motor stop failed")
        mgr = self._make_manager(mc)

        mgr.emergency_stop("test")

        # backoff_times = [0.01, 0.1, 1.0] — sleep after attempts 1 and 2
        assert mock_sleep.call_count == 2
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert sleep_calls[0] == pytest.approx(0.01)
        assert sleep_calls[1] == pytest.approx(0.1)

    def test_clears_estop_incomplete_on_success_after_prior_failure(self):
        """_estop_incomplete flag cleared when retry eventually succeeds."""
        mc = MagicMock()
        # First call fails all retries, second call succeeds
        mc.emergency_stop.side_effect = [
            RuntimeError("fail 1"),
            RuntimeError("fail 2"),
            RuntimeError("fail 3"),
        ]
        mgr = self._make_manager(mc)

        # First emergency stop: all retries fail
        result1 = mgr.emergency_stop("test")
        assert result1 is False
        assert mgr._estop_incomplete is True

        # Reset for second call (simulating retry from monitoring loop)
        mc.emergency_stop.side_effect = None
        mc.emergency_stop.return_value = True
        mgr._emergency_stop_active = False  # Allow re-entry

        result2 = mgr.emergency_stop("test again")
        assert result2 is True
        assert mgr._estop_incomplete is False

    def test_already_in_estop_returns_true(self):
        """If already in emergency stop, return True immediately."""
        mc = MagicMock()
        mgr = self._make_manager(mc)
        mgr._emergency_stop_active = True

        result = mgr.emergency_stop("test")

        assert result is True
        mc.emergency_stop.assert_not_called()

    def test_ensure_emergency_stop_retries_on_incomplete(self):
        """_ensure_emergency_stop re-issues stop when _estop_incomplete is True."""
        mc = MagicMock()
        mc.check_motor_errors.return_value = {}
        mc.emergency_stop.return_value = True
        mgr = self._make_manager(mc)
        mgr._estop_incomplete = True

        mgr._ensure_emergency_stop()

        mc.emergency_stop.assert_called_once()
        assert mgr._estop_incomplete is False
