#!/usr/bin/env python3
"""
Tests for _is_safe_to_clear_emergency exception handling.

Task 4.28c: Verify structured JSON logging on exception, proper return value,
and that BaseException subclasses (KeyboardInterrupt, SystemExit) propagate.
"""

import json
import sys
import os

import pytest
from unittest.mock import MagicMock

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

from core.safety_manager import SafetyManager


class TestIsSafeToClearEmergency:
    """Tests for _is_safe_to_clear_emergency exception handling."""

    def _make_manager(self, motor_controller=None):
        """Create a SafetyManager with a mock motor controller."""
        mc = motor_controller or MagicMock()
        return SafetyManager(motor_controller=mc)

    def test_returns_true_when_no_errors(self):
        """Returns True when motor controller reports no errors."""
        mc = MagicMock()
        mc.check_motor_errors.return_value = {}
        mgr = self._make_manager(mc)
        assert mgr._is_safe_to_clear_emergency() is True

    def test_returns_true_when_empty_list(self):
        """Returns True when motor controller returns empty list."""
        mc = MagicMock()
        mc.check_motor_errors.return_value = []
        mgr = self._make_manager(mc)
        assert mgr._is_safe_to_clear_emergency() is True

    def test_returns_false_when_errors_present(self):
        """Returns False when motor errors exist."""
        mc = MagicMock()
        mc.check_motor_errors.return_value = {1: 0x11}
        mgr = self._make_manager(mc)
        assert mgr._is_safe_to_clear_emergency() is False

    def test_returns_false_on_runtime_error(self):
        """Returns False when check_motor_errors raises RuntimeError."""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = RuntimeError("CAN bus timeout")
        mgr = self._make_manager(mc)
        assert mgr._is_safe_to_clear_emergency() is False

    def test_returns_false_on_os_error(self):
        """Returns False when check_motor_errors raises OSError."""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = OSError("device not found")
        mgr = self._make_manager(mc)
        assert mgr._is_safe_to_clear_emergency() is False

    def test_returns_false_on_attribute_error(self):
        """Returns False when check_motor_errors raises AttributeError."""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = AttributeError("bad attr")
        mgr = self._make_manager(mc)
        assert mgr._is_safe_to_clear_emergency() is False

    def test_logs_structured_json_on_exception(self, capsys):
        """Exception triggers structured JSON logging with required fields."""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = RuntimeError("CAN bus timeout")
        mgr = self._make_manager(mc)

        mgr._is_safe_to_clear_emergency()

        captured = capsys.readouterr()
        # The logger emits to stderr via its handler
        output = captured.err

        # Find the JSON object in the output
        assert (
            "safety_check_exception" in output
        ), "Expected structured JSON log with 'safety_check_exception' in stderr"

        # Parse the JSON from the output line
        for line in output.strip().split("\n"):
            line = line.strip()
            if "safety_check_exception" in line:
                log_data = json.loads(line)
                break
        else:
            pytest.fail("Could not find JSON line with 'safety_check_exception'")

        assert log_data["event"] == "safety_check_exception"
        assert log_data["component"] == "safety_manager"
        assert log_data["method"] == "_is_safe_to_clear_emergency"
        assert log_data["error_type"] == "RuntimeError"
        assert "CAN bus timeout" in log_data["error_message"]
        assert "traceback" in log_data

    def test_keyboard_interrupt_propagates(self):
        """KeyboardInterrupt is NOT caught — propagates to caller."""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = KeyboardInterrupt()
        mgr = self._make_manager(mc)

        with pytest.raises(KeyboardInterrupt):
            mgr._is_safe_to_clear_emergency()

    def test_system_exit_propagates(self):
        """SystemExit is NOT caught — propagates to caller."""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = SystemExit(1)
        mgr = self._make_manager(mc)

        with pytest.raises(SystemExit):
            mgr._is_safe_to_clear_emergency()

    def test_clear_emergency_stop_calls_is_safe_check(self):
        """clear_emergency_stop() calls _is_safe_to_clear_emergency()."""
        mc = MagicMock()
        mc.check_motor_errors.return_value = {}
        mc.clear_emergency_stop.return_value = True
        mgr = self._make_manager(mc)
        mgr._emergency_stop_active = True

        result = mgr.clear_emergency_stop()

        assert result is True
        mc.check_motor_errors.assert_called_once()

    def test_clear_emergency_stop_denied_on_exception(self):
        """clear_emergency_stop() returns False when safety check raises."""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = RuntimeError("CAN bus timeout")
        mgr = self._make_manager(mc)
        mgr._emergency_stop_active = True

        result = mgr.clear_emergency_stop()

        assert result is False
        assert mgr._emergency_stop_active is True  # Still active
