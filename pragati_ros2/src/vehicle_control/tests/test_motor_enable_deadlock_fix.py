#!/usr/bin/env python3
"""
Tests for motor enable deadlock fix — phase-1-critical-fixes change.

Task 4.1: _call_motor_enable() uses call_async + polling, NOT spin_until_future_complete
Task 4.2: _call_motor_enable() returns failure on 5s timeout without blocking
Task 4.4: Check _call_motor_disable() for same issue (uses _call_motor_enable(False))
Spec: critical-safety-fixes, item 1.9 — vehicle_control_node.py:1456
"""

import ast
import inspect
import os
import sys
import textwrap
import time
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestMotorEnableDeadlockFix:
    """Tests for spin_until_future_complete → call_async + polling fix."""

    # Task 4.1: Verify _call_motor_enable does NOT use spin_until_future_complete
    def test_no_spin_until_future_complete_in_source(self):
        """_call_motor_enable() code must NOT contain spin_until_future_complete."""
        from integration.vehicle_control_node import (
            ROS2VehicleControlNode as VehicleControlNode,
        )

        source = inspect.getsource(VehicleControlNode._call_motor_enable)
        # Strip the docstring — the warning note mentions spin_until_future_complete
        # as a reminder of what NOT to do. We only care about actual code usage.
        tree = ast.parse(textwrap.dedent(source))
        func_def = tree.body[0]
        # Remove docstring (first statement if it's an Expr with a Constant str)
        if (
            func_def.body
            and isinstance(func_def.body[0], ast.Expr)
            and isinstance(func_def.body[0].value, ast.Constant)
            and isinstance(func_def.body[0].value.value, str)
        ):
            func_def.body.pop(0)
        code_source = ast.unparse(func_def)
        assert "spin_until_future_complete" not in code_source, (
            "_call_motor_enable() still uses spin_until_future_complete — "
            "this causes deadlock on SingleThreadedExecutor"
        )

    # Task 4.1: Verify _call_motor_enable uses call_async
    def test_uses_call_async_pattern(self):
        """_call_motor_enable() source must use call_async() + polling loop."""
        from integration.vehicle_control_node import (
            ROS2VehicleControlNode as VehicleControlNode,
        )

        source = inspect.getsource(VehicleControlNode._call_motor_enable)
        assert (
            "call_async" in source
        ), "_call_motor_enable() must use call_async() for non-blocking service calls"
        assert (
            "future.done()" in source or ".done()" in source
        ), "_call_motor_enable() must poll future.done() instead of blocking"

    # Task 4.2: Verify timeout returns failure without blocking
    def test_timeout_returns_failure(self):
        """_call_motor_enable() returns False on 5s timeout without blocking."""
        from integration.vehicle_control_node import (
            ROS2VehicleControlNode as VehicleControlNode,
        )

        # Create a mock node instance
        node = MagicMock(spec=VehicleControlNode)
        node.logger = MagicMock()

        # Mock client that returns a future that never completes
        mock_client = MagicMock()
        mock_client.service_is_ready.return_value = True
        mock_future = MagicMock()
        mock_future.done.return_value = False  # Never completes
        mock_future.result.return_value = None
        mock_client.call_async.return_value = mock_future
        node.motor_enable_client = mock_client

        # Call the unbound method with the mock
        start = time.time()
        result = VehicleControlNode._call_motor_enable(node, True)
        elapsed = time.time() - start

        assert result is False, "Should return False on timeout"
        # Should timeout around 5s (allow margin for test overhead)
        assert (
            elapsed < 8.0
        ), f"Took {elapsed:.1f}s — should timeout around 5s, not block"
        assert elapsed >= 4.0, f"Took {elapsed:.1f}s — timeout should be ~5s"

    # Task 4.4: _call_motor_enable(False) uses same pattern for disable
    def test_disable_also_uses_async_pattern(self):
        """_call_motor_enable(False) (disable path) also uses call_async + polling."""
        from integration.vehicle_control_node import (
            ROS2VehicleControlNode as VehicleControlNode,
        )

        # The method uses enable parameter to select client, but the async
        # pattern must apply to both paths. Source inspection confirms this
        # since there's a single code path for both enable=True and enable=False.
        source = inspect.getsource(VehicleControlNode._call_motor_enable)
        # Strip docstring before checking for spin_until_future_complete
        tree = ast.parse(textwrap.dedent(source))
        func_def = tree.body[0]
        if (
            func_def.body
            and isinstance(func_def.body[0], ast.Expr)
            and isinstance(func_def.body[0].value, ast.Constant)
            and isinstance(func_def.body[0].value.value, str)
        ):
            func_def.body.pop(0)
        code_source = ast.unparse(func_def)
        # Verify there's no separate blocking path for the disable case
        assert (
            code_source.count("spin_until_future_complete") == 0
        ), "No path in _call_motor_enable should use spin_until_future_complete"
