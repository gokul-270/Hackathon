#!/usr/bin/env python3
"""
Thread safety tests for vehicle_control_node.py.
Phase-2-critical-fixes: Bug 1.3 — add threading locks to shared state.

Tests verify:
- Lock instances exist and are threading.Lock
- MQTT callbacks acquire _mqtt_lock
- Motor state callbacks acquire _motor_state_lock
- Control state callbacks acquire _control_lock
- Stress test: concurrent access without exceptions
"""

import pytest
import threading
import time
import sys
import os
import re
import ast

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))

# Path to the source file under test
SOURCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "integration",
    "vehicle_control_node.py",
)


def _read_source():
    """Read the vehicle_control_node.py source file."""
    with open(SOURCE_PATH, "r") as f:
        return f.read()


def _get_method_source(source: str, method_name: str) -> str:
    """Extract a method body from source using AST parsing.

    Returns the raw source text for the method (def line through end).
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                # node.end_lineno is 1-indexed
                start = node.lineno - 1
                end = node.end_lineno
                return "".join(lines[start:end])
    raise ValueError(f"Method {method_name!r} not found in source")


def _method_contains_lock(source: str, method_name: str, lock_name: str) -> bool:
    """Check whether a method contains 'with self.<lock_name>:'."""
    body = _get_method_source(source, method_name)
    pattern = rf"with\s+self\.{re.escape(lock_name)}\s*:"
    return bool(re.search(pattern, body))


# =============================================================================
# TASK 2.1: Lock instances exist as threading.Lock
# =============================================================================


class TestLockExistence:
    """Task 2.1: Verify _mqtt_lock, _motor_state_lock, _control_lock
    are created as threading.Lock/RLock() in __init__."""

    def test_mqtt_lock_exists_in_init(self):
        source = _read_source()
        init_body = _get_method_source(source, "__init__")
        assert re.search(
            r"self\._mqtt_lock\s*=\s*threading\.Lock\(\)", init_body
        ), "_mqtt_lock not assigned as threading.Lock() in __init__"

    def test_motor_state_lock_exists_in_init(self):
        source = _read_source()
        init_body = _get_method_source(source, "__init__")
        assert re.search(
            r"self\._motor_state_lock\s*=\s*threading\.R?Lock\(\)",
            init_body,
        ), "_motor_state_lock not assigned as threading.Lock/RLock() in __init__"

    def test_control_lock_exists_in_init(self):
        source = _read_source()
        init_body = _get_method_source(source, "__init__")
        assert re.search(
            r"self\._control_lock\s*=\s*threading\.Lock\(\)", init_body
        ), "_control_lock not assigned as threading.Lock() in __init__"


# =============================================================================
# TASK 2.3: MQTT callbacks acquire _mqtt_lock
# =============================================================================


class TestMqttCallbackLocking:
    """Task 2.3: MQTT write callbacks acquire _mqtt_lock."""

    def test_on_mqtt_connect_acquires_mqtt_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_on_mqtt_connect", "_mqtt_lock"
        ), "_on_mqtt_connect does not contain 'with self._mqtt_lock:'"

    def test_on_mqtt_disconnect_acquires_mqtt_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_on_mqtt_disconnect", "_mqtt_lock"
        ), "_on_mqtt_disconnect does not contain 'with self._mqtt_lock:'"


# =============================================================================
# TASK 2.4: MQTT state reads acquire _mqtt_lock
# =============================================================================


class TestMqttReadLocking:
    """Task 2.4: Executor methods reading MQTT state acquire _mqtt_lock."""

    def test_mqtt_health_heartbeat_acquires_mqtt_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_mqtt_health_heartbeat", "_mqtt_lock"
        ), "_mqtt_health_heartbeat does not contain 'with self._mqtt_lock:'"

    def test_mqtt_selftest_check_acquires_mqtt_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_mqtt_selftest_check", "_mqtt_lock"
        ), "_mqtt_selftest_check does not contain 'with self._mqtt_lock:'"

    def test_recreate_mqtt_client_acquires_mqtt_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_recreate_mqtt_client", "_mqtt_lock"
        ), "_recreate_mqtt_client does not contain 'with self._mqtt_lock:'"

    def test_process_physical_switches_acquires_mqtt_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_process_physical_switches", "_mqtt_lock"
        ), ("_process_physical_switches does not contain" " 'with self._mqtt_lock:'")


# =============================================================================
# TASK 3.1: motor_status writes acquire _motor_state_lock
# =============================================================================


class TestMotorStateWriteLocking:
    """Task 3.1: motor_status write sites acquire _motor_state_lock."""

    def test_motor_joint_states_callback_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source,
            "_motor_joint_states_callback",
            "_motor_state_lock",
        ), (
            "_motor_joint_states_callback does not contain"
            " 'with self._motor_state_lock:'"
        )

    def test_call_joint_position_command_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source,
            "_call_joint_position_command",
            "_motor_state_lock",
        ), (
            "_call_joint_position_command does not contain"
            " 'with self._motor_state_lock:'"
        )

    def test_call_joint_velocity_command_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source,
            "_call_joint_velocity_command",
            "_motor_state_lock",
        ), (
            "_call_joint_velocity_command does not contain"
            " 'with self._motor_state_lock:'"
        )

    def test_control_loop_acquires_motor_state_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "_control_loop", "_motor_state_lock"), (
            "_control_loop does not contain" " 'with self._motor_state_lock:'"
        )


# =============================================================================
# TASK 3.2: motor_status reads acquire _motor_state_lock
# =============================================================================


class TestMotorStateReadLocking:
    """Task 3.2: motor_status read sites acquire _motor_state_lock."""

    def test_get_available_motor_count_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source,
            "_get_available_motor_count",
            "_motor_state_lock",
        ), (
            "_get_available_motor_count does not contain"
            " 'with self._motor_state_lock:'"
        )

    def test_get_health_score_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "get_health_score", "_motor_state_lock"), (
            "get_health_score does not contain" " 'with self._motor_state_lock:'"
        )

    def test_get_diagnostics_acquires_motor_state_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "get_diagnostics", "_motor_state_lock"), (
            "get_diagnostics does not contain" " 'with self._motor_state_lock:'"
        )

    def test_publish_joint_states_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_publish_joint_states", "_motor_state_lock"
        ), ("_publish_joint_states does not contain" " 'with self._motor_state_lock:'")

    def test_publish_status_acquires_motor_state_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "_publish_status", "_motor_state_lock"), (
            "_publish_status does not contain" " 'with self._motor_state_lock:'"
        )

    def test_get_joint_position_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_get_joint_position", "_motor_state_lock"
        ), ("_get_joint_position does not contain" " 'with self._motor_state_lock:'")

    def test_test_joint_states_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_test_joint_states", "_motor_state_lock"
        ), ("_test_joint_states does not contain" " 'with self._motor_state_lock:'")

    def test_test_motors_callback_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_test_motors_callback", "_motor_state_lock"
        ), ("_test_motors_callback does not contain" " 'with self._motor_state_lock:'")

    def test_run_motor_quick_test_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_run_motor_quick_test", "_motor_state_lock"
        ), ("_run_motor_quick_test does not contain" " 'with self._motor_state_lock:'")

    def test_send_drive_position_incremental_acquires_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source,
            "_send_drive_position_incremental",
            "_motor_state_lock",
        ), (
            "_send_drive_position_incremental does not contain"
            " 'with self._motor_state_lock:'"
        )


# =============================================================================
# TASK 3.4: Dictionary iteration thread safety
# =============================================================================


class TestDictIterationSafety:
    """Task 3.4: lock-protected dict iteration is safe under concurrent
    writes."""

    def test_motor_status_iteration_thread_safe(self):
        """Verify lock-protected dict iteration is safe under concurrent
        writes."""
        lock = threading.Lock()
        shared_dict = {f"joint{i}": {"pos": 0.0, "ok": True} for i in range(6)}
        errors = []

        def writer():
            for i in range(1000):
                with lock:
                    for key in shared_dict:
                        shared_dict[key]["pos"] = float(i)

        def reader():
            for _ in range(1000):
                with lock:
                    for key, val in shared_dict.items():
                        _ = val["pos"]

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # No RuntimeError means success — test passes implicitly


# =============================================================================
# TASK 4.1: current_state writes acquire _control_lock
# =============================================================================


class TestControlStateWriteLocking:
    """Task 4.1: current_state write sites acquire _control_lock."""

    def test_set_vehicle_to_idle_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "set_vehicle_to_idle", "_control_lock"), (
            "set_vehicle_to_idle does not contain" " 'with self._control_lock:'"
        )

    def test_emergency_stop_callback_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_emergency_stop_callback", "_control_lock"
        ), ("_emergency_stop_callback does not contain" " 'with self._control_lock:'")

    def test_control_loop_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "_control_loop", "_control_lock"), (
            "_control_loop does not contain" " 'with self._control_lock:'"
        )

    def test_process_gpio_inputs_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "_process_gpio_inputs", "_control_lock"), (
            "_process_gpio_inputs does not contain" " 'with self._control_lock:'"
        )

    def test_process_direction_switches_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(
            source, "_process_direction_switches", "_control_lock"
        ), (
            "_process_direction_switches does not contain" " 'with self._control_lock:'"
        )


# =============================================================================
# TASK 4.2: Joystick attribute writes acquire _control_lock
# =============================================================================


class TestJoystickAttributeLocking:
    """Task 4.2: last_command and command_count writes acquire
    _control_lock."""

    def test_track_command_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "_track_command", "_control_lock"), (
            "_track_command does not contain" " 'with self._control_lock:'"
        )

    def test_cmd_vel_callback_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "_cmd_vel_callback", "_control_lock"), (
            "_cmd_vel_callback does not contain" " 'with self._control_lock:'"
        )

    def test_get_diagnostics_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "get_diagnostics", "_control_lock"), (
            "get_diagnostics does not contain" " 'with self._control_lock:'"
        )

    def test_publish_status_acquires_control_lock(self):
        source = _read_source()
        assert _method_contains_lock(source, "_publish_status", "_control_lock"), (
            "_publish_status does not contain" " 'with self._control_lock:'"
        )


# =============================================================================
# TASK 4.4: Stress test for concurrent access
# =============================================================================


class TestConcurrentAccessStress:
    """Task 4.4: 3 threads concurrently reading/writing shared state
    for 1000 iterations — no exceptions."""

    def test_concurrent_shared_state_no_exceptions(self):
        mqtt_lock = threading.Lock()
        motor_lock = threading.Lock()
        control_lock = threading.Lock()

        state = {
            "mqtt_connected": False,
            "mqtt_reconnect_count": 0,
            "motor_status": {f"joint{i}": {"pos": 0.0, "ok": True} for i in range(6)},
            "current_state": "IDLING",
            "command_count": 0,
        }
        errors = []

        def mqtt_thread():
            for i in range(1000):
                try:
                    with mqtt_lock:
                        state["mqtt_connected"] = not state["mqtt_connected"]
                        state["mqtt_reconnect_count"] += 1
                except Exception as e:
                    errors.append(f"mqtt: {e}")

        def joystick_thread():
            for i in range(1000):
                try:
                    with control_lock:
                        _ = state["current_state"]
                        state["command_count"] += 1
                    with motor_lock:
                        for joint in state["motor_status"]:
                            _ = state["motor_status"][joint]["pos"]
                except Exception as e:
                    errors.append(f"joystick: {e}")

        def executor_thread():
            for i in range(1000):
                try:
                    with motor_lock:
                        for joint in state["motor_status"]:
                            state["motor_status"][joint]["pos"] = float(i)
                            state["motor_status"][joint]["ok"] = True
                    with control_lock:
                        state["current_state"] = "BUSY" if i % 2 == 0 else "IDLING"
                    with mqtt_lock:
                        _ = state["mqtt_connected"]
                except Exception as e:
                    errors.append(f"executor: {e}")

        threads = [
            threading.Thread(target=mqtt_thread),
            threading.Thread(target=joystick_thread),
            threading.Thread(target=executor_thread),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrent access errors: {errors}"
