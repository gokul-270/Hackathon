#!/usr/bin/env python3
"""Integration tests for multi-step motor API workflows.

These tests verify end-to-end behaviour of chained HTTP calls against
the motor configuration REST API.  ROS2 is fully mocked so the tests
run without a live robot or ROS2 installation.

Workflow categories covered:
  1. Select motor -> read limits -> send command -> verify telemetry
  2. Encoder calibration flow (read -> zero -> verify)
  3. Full lifecycle flow (ON -> command -> STOP -> OFF)
  4. Confirmation-token rejection / acceptance for encoder zero
  5. E-stop blocks commands but allows OFF
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ------------------------------------------------------------------
# Mock ROS2 modules before any project imports
# ------------------------------------------------------------------
sys.modules.setdefault("rclpy", MagicMock())
sys.modules.setdefault("rclpy.node", MagicMock())
sys.modules.setdefault("rclpy.action", MagicMock())
sys.modules.setdefault("rclpy.callback_groups", MagicMock())
sys.modules.setdefault("rclpy.executors", MagicMock())
sys.modules.setdefault("rclpy.qos", MagicMock())
sys.modules.setdefault("rclpy.serialization", MagicMock())
sys.modules.setdefault("motor_control_msgs", MagicMock())
sys.modules.setdefault("motor_control_msgs.srv", MagicMock())
sys.modules.setdefault("motor_control_msgs.action", MagicMock())
sys.modules.setdefault("sensor_msgs", MagicMock())
sys.modules.setdefault("sensor_msgs.msg", MagicMock())
sys.modules.setdefault("std_msgs", MagicMock())
sys.modules.setdefault("std_msgs.msg", MagicMock())
sys.modules.setdefault("std_srvs", MagicMock())
sys.modules.setdefault("std_srvs.srv", MagicMock())
sys.modules.setdefault("action_msgs", MagicMock())
sys.modules.setdefault("action_msgs.msg", MagicMock())
sys.modules.setdefault("rosidl_runtime_py", MagicMock())
sys.modules.setdefault("rosidl_runtime_py.utilities", MagicMock())
sys.modules.setdefault("rosidl_runtime_py.convert", MagicMock())

_backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend_dir))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import motor_api  # noqa: E402
from motor_api import motor_router  # noqa: E402

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

MOTOR_ID = 1


def _ok_limits() -> Dict[str, Any]:
    """Successful read-limits bridge response."""
    return {
        "success": True,
        "max_torque_ratio": 1500,
        "acceleration_dps": 720.0,
        "error_message": "",
    }


def _ok_command() -> Dict[str, Any]:
    """Successful motor-command bridge response with telemetry."""
    return {
        "success": True,
        "temperature": 42,
        "torque_current": 300,
        "speed": 180,
        "encoder": 32000,
        "error_message": "",
    }


def _ok_lifecycle(state: int = 1) -> Dict[str, Any]:
    """Successful lifecycle bridge response."""
    return {
        "success": True,
        "motor_state": state,
        "error_message": "",
    }


def _ok_encoder_read() -> Dict[str, Any]:
    """Successful encoder-read bridge response."""
    return {
        "success": True,
        "raw_value": 12345,
        "offset": 100,
        "original_value": 12445,
        "error_message": "",
    }


def _ok_encoder_zero() -> Dict[str, Any]:
    """Successful encoder-zero bridge response."""
    return {
        "success": True,
        "error_message": "",
    }


def _fail(msg: str = "bridge error") -> Dict[str, Any]:
    """Generic failure bridge response."""
    return {"success": False, "error": msg}


def _estop_fail() -> Dict[str, Any]:
    """Bridge response when e-stop is active."""
    return {"success": False, "error": "E-STOP active: commands blocked"}


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def mock_bridge():
    """Patch the module-level ``_bridge`` with an ``AsyncMock``.

    Every bridge method is an ``AsyncMock`` so callers can set
    per-test return values and assert call counts.
    """
    bridge = MagicMock()
    bridge.motor_command = AsyncMock(return_value=_ok_command())
    bridge.motor_lifecycle = AsyncMock(return_value=_ok_lifecycle())
    bridge.read_motor_limits = AsyncMock(return_value=_ok_limits())
    bridge.write_motor_limits = AsyncMock(
        return_value={"success": True, "error_message": ""}
    )
    bridge.read_encoder = AsyncMock(return_value=_ok_encoder_read())
    bridge.write_encoder_zero = AsyncMock(
        return_value=_ok_encoder_zero()
    )
    bridge.read_motor_angles = AsyncMock(
        return_value={
            "success": True,
            "multi_turn_deg": 90.0,
            "single_turn_deg": 45.0,
            "error_message": "",
        }
    )
    bridge.read_motor_state = AsyncMock(
        return_value={
            "success": True,
            "temperature_c": 38.5,
            "voltage_v": 24.1,
            "torque_current_a": 0.5,
            "speed_dps": 0.0,
            "encoder_position": 12345,
            "multi_turn_deg": 90.0,
            "single_turn_deg": 45.0,
            "phase_current_a": [0.1, 0.2, 0.3],
            "error_flags": {},
            "error_message": "",
        }
    )
    bridge.clear_motor_errors = AsyncMock(
        return_value={
            "success": True,
            "error_flags_after": {},
            "error_message": "",
        }
    )

    with patch.object(motor_api, "_bridge", bridge):
        yield bridge


@pytest.fixture()
def client(mock_bridge):
    """FastAPI ``TestClient`` with the motor router mounted."""
    app = FastAPI()
    app.include_router(motor_router)
    return TestClient(app)


# ==================================================================
# 1. Select motor -> read limits -> send command -> verify telemetry
# ==================================================================


class TestSelectLimitsCommandWorkflow:
    """Workflow: read limits, then send a command and verify telemetry."""

    def test_read_limits_then_command_success(self, client, mock_bridge):
        """GET limits -> POST command succeeds with telemetry fields."""
        # Step 1: read limits
        resp = client.get(f"/api/motor/{MOTOR_ID}/limits")
        assert resp.status_code == 200
        limits = resp.json()
        assert limits["success"] is True
        assert limits["max_torque_ratio"] == 1500

        # Step 2: send torque command within limits
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 0, "value": 500.0},
        )
        assert resp.status_code == 200
        cmd = resp.json()
        assert cmd["success"] is True
        assert cmd["temperature"] == 42
        assert cmd["torque_current"] == 300
        assert cmd["speed"] == 180
        assert cmd["encoder"] == 32000

    def test_read_limits_then_command_bridge_failure(
        self, client, mock_bridge
    ):
        """Limits OK but command fails -> 502."""
        mock_bridge.motor_command = AsyncMock(
            return_value=_fail("CAN bus timeout")
        )

        resp = client.get(f"/api/motor/{MOTOR_ID}/limits")
        assert resp.status_code == 200

        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 0, "value": 100.0},
        )
        assert resp.status_code == 502

    def test_invalid_motor_id_rejected(self, client, mock_bridge):
        """Both endpoints reject an invalid motor_id with 400."""
        resp = client.get("/api/motor/99/limits")
        assert resp.status_code == 400

        resp = client.post(
            "/api/motor/99/command",
            json={"mode": 0, "value": 100.0},
        )
        assert resp.status_code == 400


# ==================================================================
# 2. Encoder calibration flow
# ==================================================================


class TestEncoderCalibrationWorkflow:
    """Workflow: read encoder -> zero encoder -> verify change."""

    def test_read_then_zero_success(self, client, mock_bridge):
        """Read encoder, zero it, confirm response."""
        # Step 1: read current encoder
        resp = client.get(f"/api/motor/{MOTOR_ID}/encoder")
        assert resp.status_code == 200
        before = resp.json()
        assert before["success"] is True
        assert before["raw_value"] == 12345

        # Step 2: zero encoder with correct token
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/encoder/zero",
            json={
                "mode": 1,
                "confirmation_token": "CONFIRM_ENCODER_ZERO",
            },
        )
        assert resp.status_code == 200
        after = resp.json()
        assert after["success"] is True
        assert after["mode"] == 1

    def test_read_encoder_failure_aborts_workflow(
        self, client, mock_bridge
    ):
        """When encoder read fails the frontend should not proceed."""
        mock_bridge.read_encoder = AsyncMock(
            return_value=_fail("sensor disconnected")
        )

        resp = client.get(f"/api/motor/{MOTOR_ID}/encoder")
        assert resp.status_code == 502

        # Bridge zero should never be called in a real UI, but the
        # test confirms the read failure propagates correctly.
        assert mock_bridge.write_encoder_zero.call_count == 0

    def test_zero_encoder_bridge_failure(self, client, mock_bridge):
        """Read OK but bridge zero fails -> 502."""
        mock_bridge.write_encoder_zero = AsyncMock(
            return_value=_fail("ROM write error")
        )

        resp = client.get(f"/api/motor/{MOTOR_ID}/encoder")
        assert resp.status_code == 200

        resp = client.post(
            f"/api/motor/{MOTOR_ID}/encoder/zero",
            json={
                "mode": 1,
                "confirmation_token": "CONFIRM_ENCODER_ZERO",
            },
        )
        assert resp.status_code == 502


# ==================================================================
# 3. Lifecycle flow: ON -> command -> STOP -> OFF
# ==================================================================


class TestLifecycleFlow:
    """Full motor lifecycle: ON -> command -> STOP -> OFF."""

    def test_full_lifecycle_sequence(self, client, mock_bridge):
        """Each lifecycle step succeeds in order."""
        # ON (action=0) -> state=1 (RUNNING)
        mock_bridge.motor_lifecycle = AsyncMock(
            return_value=_ok_lifecycle(state=1)
        )
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["motor_state_name"] == "RUNNING"

        # Command
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 1, "value": 360.0},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # STOP (action=2) -> state=2 (STOPPED)
        mock_bridge.motor_lifecycle = AsyncMock(
            return_value=_ok_lifecycle(state=2)
        )
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 2},
        )
        assert resp.status_code == 200
        assert resp.json()["motor_state_name"] == "STOPPED"

        # OFF (action=1) -> state=0 (OFF)
        mock_bridge.motor_lifecycle = AsyncMock(
            return_value=_ok_lifecycle(state=0)
        )
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["motor_state_name"] == "OFF"

    def test_lifecycle_on_failure_blocks_subsequent(
        self, client, mock_bridge
    ):
        """If ON fails (502), the motor never reaches RUNNING."""
        mock_bridge.motor_lifecycle = AsyncMock(
            return_value=_fail("CAN bus not ready")
        )

        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 0},
        )
        assert resp.status_code == 502


# ==================================================================
# 4. Confirmation token rejection / acceptance
# ==================================================================


class TestConfirmationToken:
    """Verify encoder-zero confirmation_token validation."""

    def test_missing_token_returns_422(self, client, mock_bridge):
        """POST encoder/zero without confirmation_token -> 422.

        The ``confirmation_token`` field is required in the Pydantic
        model, so omitting it produces a 422 validation error.
        """
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/encoder/zero",
            json={"mode": 1},
        )
        assert resp.status_code == 422

    def test_wrong_token_returns_400(self, client, mock_bridge):
        """POST encoder/zero with incorrect token -> 400."""
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/encoder/zero",
            json={
                "mode": 1,
                "confirmation_token": "WRONG_TOKEN",
            },
        )
        assert resp.status_code == 400
        assert "CONFIRM_ENCODER_ZERO" in resp.json()["detail"]

    def test_correct_token_succeeds(self, client, mock_bridge):
        """POST encoder/zero with correct token -> 200."""
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/encoder/zero",
            json={
                "mode": 1,
                "confirmation_token": "CONFIRM_ENCODER_ZERO",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_lifecycle_save_zero_rom_requires_token(
        self, client, mock_bridge
    ):
        """Lifecycle SAVE_ZERO_ROM (action=5) without token -> 400."""
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 5},
        )
        assert resp.status_code == 400

    def test_lifecycle_save_zero_rom_wrong_token(
        self, client, mock_bridge
    ):
        """Lifecycle SAVE_ZERO_ROM with wrong token -> 400."""
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={
                "action": 5,
                "confirmation_token": "NOPE",
            },
        )
        assert resp.status_code == 400

    def test_lifecycle_save_zero_rom_correct_token(
        self, client, mock_bridge
    ):
        """Lifecycle SAVE_ZERO_ROM with correct token -> 200."""
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={
                "action": 5,
                "confirmation_token": "CONFIRM_ENCODER_ZERO",
            },
        )
        assert resp.status_code == 200


# ==================================================================
# 5. E-stop blocks commands but allows OFF
# ==================================================================


class TestEstopBehaviour:
    """When the bridge reports e-stop, commands fail but OFF works."""

    def test_estop_blocks_command(self, client, mock_bridge):
        """Motor command during e-stop -> 502."""
        mock_bridge.motor_command = AsyncMock(
            return_value=_estop_fail()
        )

        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 0, "value": 100.0},
        )
        assert resp.status_code == 502
        assert "E-STOP" in resp.json()["detail"]

    def test_estop_allows_lifecycle_off(self, client, mock_bridge):
        """Lifecycle OFF still succeeds even when e-stop is active.

        The bridge returns e-stop for commands but the OFF lifecycle
        action bypasses the e-stop guard.
        """
        mock_bridge.motor_command = AsyncMock(
            return_value=_estop_fail()
        )
        mock_bridge.motor_lifecycle = AsyncMock(
            return_value=_ok_lifecycle(state=0)
        )

        # Command blocked
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 0, "value": 100.0},
        )
        assert resp.status_code == 502

        # OFF still works
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["motor_state_name"] == "OFF"

    def test_estop_blocks_speed_command(self, client, mock_bridge):
        """Speed command also blocked during e-stop -> 502."""
        mock_bridge.motor_command = AsyncMock(
            return_value=_estop_fail()
        )

        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 1, "value": 360.0},
        )
        assert resp.status_code == 502

    def test_estop_command_then_off_then_command_after_clear(
        self, client, mock_bridge
    ):
        """Full e-stop recovery: command fails -> OFF -> clear -> command OK.

        Simulates the real recovery sequence a user would follow.
        """
        # 1. Command blocked by e-stop
        mock_bridge.motor_command = AsyncMock(
            return_value=_estop_fail()
        )
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 0, "value": 50.0},
        )
        assert resp.status_code == 502

        # 2. OFF succeeds
        mock_bridge.motor_lifecycle = AsyncMock(
            return_value=_ok_lifecycle(state=0)
        )
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 1},
        )
        assert resp.status_code == 200

        # 3. Clear errors
        resp = client.post(f"/api/motor/{MOTOR_ID}/errors/clear")
        assert resp.status_code == 200

        # 4. ON again
        mock_bridge.motor_lifecycle = AsyncMock(
            return_value=_ok_lifecycle(state=1)
        )
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/lifecycle",
            json={"action": 0},
        )
        assert resp.status_code == 200

        # 5. Command now succeeds
        mock_bridge.motor_command = AsyncMock(
            return_value=_ok_command()
        )
        resp = client.post(
            f"/api/motor/{MOTOR_ID}/command",
            json={"mode": 0, "value": 50.0},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
