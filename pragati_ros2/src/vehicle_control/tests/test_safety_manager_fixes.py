#!/usr/bin/env python3
"""
Tests for SafetyManager fixes — phase-1-critical-fixes change.

Task 3.1: _is_safe_to_clear_emergency() catches RuntimeError, logs details, returns False
Task 3.2: _is_safe_to_clear_emergency() does NOT catch KeyboardInterrupt
Spec: critical-safety-fixes, item 1.4 — safety_manager.py:261
"""

import logging
import pytest
import sys
import os
from unittest.mock import MagicMock, PropertyMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.safety_manager import SafetyManager


class TestBareExceptFix:
    """Tests for bare except → except Exception as e fix in _is_safe_to_clear_emergency"""

    def _make_manager(self, motor_controller=None):
        """Create a SafetyManager with a mock motor controller."""
        mc = motor_controller or MagicMock()
        return SafetyManager(motor_controller=mc)

    # Task 3.1: catches RuntimeError, logs details, returns False
    def test_runtime_error_caught_and_logged(self, capfd):
        """_is_safe_to_clear_emergency() catches RuntimeError, logs details, returns False"""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = RuntimeError("CAN bus timeout")
        mgr = self._make_manager(mc)

        result = mgr._is_safe_to_clear_emergency()

        assert result is False
        # Verify structured JSON error was logged (via logging → stderr handler)
        captured = capfd.readouterr()
        log_output = captured.err + captured.out
        assert (
            "safety_check_exception" in log_output
        ), f"Expected structured JSON log with 'safety_check_exception', got: {log_output}"
        assert (
            "CAN bus timeout" in log_output or "RuntimeError" in log_output
        ), f"Expected log to contain exception details, got: {log_output}"

    # Task 3.1 (additional): catches generic Exception subclasses
    def test_attribute_error_caught_returns_false(self):
        """_is_safe_to_clear_emergency() catches AttributeError and returns False"""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = AttributeError("bad attr")
        mgr = self._make_manager(mc)

        result = mgr._is_safe_to_clear_emergency()
        assert result is False

    def test_os_error_caught_returns_false(self):
        """_is_safe_to_clear_emergency() catches OSError and returns False"""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = OSError("device not found")
        mgr = self._make_manager(mc)

        result = mgr._is_safe_to_clear_emergency()
        assert result is False

    # Task 3.2: does NOT catch KeyboardInterrupt
    def test_keyboard_interrupt_propagates(self):
        """_is_safe_to_clear_emergency() does NOT catch KeyboardInterrupt"""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = KeyboardInterrupt()
        mgr = self._make_manager(mc)

        with pytest.raises(KeyboardInterrupt):
            mgr._is_safe_to_clear_emergency()

    # Task 3.2 (additional): does NOT catch SystemExit
    def test_system_exit_propagates(self):
        """_is_safe_to_clear_emergency() does NOT catch SystemExit"""
        mc = MagicMock()
        mc.check_motor_errors.side_effect = SystemExit(1)
        mgr = self._make_manager(mc)

        with pytest.raises(SystemExit):
            mgr._is_safe_to_clear_emergency()

    # Regression: normal operation still works
    def test_no_errors_returns_true(self):
        """_is_safe_to_clear_emergency() returns True when no motor errors"""
        mc = MagicMock()
        mc.check_motor_errors.return_value = []
        mgr = self._make_manager(mc)

        result = mgr._is_safe_to_clear_emergency()
        assert result is True

    def test_motor_errors_present_returns_false(self):
        """_is_safe_to_clear_emergency() returns False when motor errors exist"""
        mc = MagicMock()
        mc.check_motor_errors.return_value = [{"motor_id": 1, "error": "overcurrent"}]
        mgr = self._make_manager(mc)

        result = mgr._is_safe_to_clear_emergency()
        assert result is False
