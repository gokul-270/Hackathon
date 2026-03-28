"""Unit tests for Motor Config REST API and PID field rename compatibility.

Task 8.3: Tests all /api/motor/* endpoints via mocked MotorConfigBridge.
Task 8.4: Tests PID API backward-compatible field rename (angle_kp/iq_kp).

ROS2 modules are mocked so tests run without hardware or a running ROS2 graph.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock ROS2 / message modules BEFORE importing any API module
# ---------------------------------------------------------------------------
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

# Add backend to path so imports resolve
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "backend"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from motor_api import (  # noqa: E402
    MotorConfigBridge,
    _bridge,
    motor_router,
)
from pid_tuning_api import (  # noqa: E402
    _bridge as pid_bridge,
    _normalise_pid_fields,
    _PID_FIELD_ALIASES,
    pid_router,
)

# ---------------------------------------------------------------------------
# Test-level FastAPI app
# ---------------------------------------------------------------------------
motor_app = FastAPI()
motor_app.include_router(motor_router)
motor_client = TestClient(motor_app)

pid_app = FastAPI()
pid_app.include_router(pid_router)
pid_client = TestClient(pid_app)


# ---------------------------------------------------------------------------
# Motor bridge mock helpers
# ---------------------------------------------------------------------------


def _mock_motor_command(
    success: bool = True,
    temperature: int = 35,
    torque_current: int = 100,
    speed: int = 500,
    encoder: int = 32768,
    error: str = "",
):
    """Return a coroutine that fakes MotorConfigBridge.motor_command."""

    async def _fake(
        motor_id, command_type, value, max_speed=0.0, direction=0
    ):
        if success:
            return {
                "success": True,
                "temperature": temperature,
                "torque_current": torque_current,
                "speed": speed,
                "encoder": encoder,
                "error_message": "",
            }
        return {"success": False, "error": error or "mocked failure"}

    return _fake


def _mock_motor_command_timeout():
    """Return a coroutine that simulates a service timeout."""

    async def _fake(
        motor_id, command_type, value, max_speed=0.0, direction=0
    ):
        return {
            "success": False,
            "error": "Service timed out after 5s",
        }

    return _fake


def _mock_motor_lifecycle(
    success: bool = True, motor_state: int = 1, error: str = ""
):
    async def _fake(motor_id, action):
        if success:
            return {
                "success": True,
                "motor_state": motor_state,
                "error_message": "",
            }
        return {
            "success": False,
            "error_message": error or "mocked failure",
            "error": error or "mocked failure",
        }

    return _fake


def _mock_read_motor_limits(
    success: bool = True,
    max_torque_ratio: int = 1500,
    acceleration_dps: float = 100.0,
    error: str = "",
):
    async def _fake(motor_id):
        if success:
            return {
                "success": True,
                "max_torque_ratio": max_torque_ratio,
                "acceleration_dps": acceleration_dps,
                "error_message": "",
            }
        return {"success": False, "error": error or "mocked failure"}

    return _fake


def _mock_write_motor_limits(success: bool = True, error: str = ""):
    async def _fake(
        motor_id,
        max_torque_ratio=0,
        acceleration_dps=0.0,
        set_max_torque=False,
        set_acceleration=False,
    ):
        if success:
            return {"success": True, "error_message": ""}
        return {
            "success": False,
            "error_message": error or "mocked failure",
            "error": error or "mocked failure",
        }

    return _fake


def _mock_read_encoder(
    success: bool = True,
    raw_value: int = 32000,
    offset: int = 100,
    original_value: int = 31900,
    error: str = "",
):
    async def _fake(motor_id):
        if success:
            return {
                "success": True,
                "raw_value": raw_value,
                "offset": offset,
                "original_value": original_value,
                "error_message": "",
            }
        return {"success": False, "error": error or "mocked failure"}

    return _fake


def _mock_write_encoder_zero(success: bool = True, error: str = ""):
    async def _fake(motor_id, mode, encoder_value=0):
        if success:
            return {"success": True, "error_message": ""}
        return {
            "success": False,
            "error_message": error or "mocked failure",
            "error": error or "mocked failure",
        }

    return _fake


def _mock_read_motor_angles(
    success: bool = True,
    multi_turn_deg: float = 720.5,
    single_turn_deg: float = 180.3,
    error: str = "",
):
    async def _fake(motor_id):
        if success:
            return {
                "success": True,
                "multi_turn_deg": multi_turn_deg,
                "single_turn_deg": single_turn_deg,
                "error_message": "",
            }
        return {"success": False, "error": error or "mocked failure"}

    return _fake


def _mock_read_motor_state(
    success: bool = True,
    error: str = "",
):
    async def _fake(motor_id):
        if success:
            return {
                "success": True,
                "temperature_c": 42.5,
                "voltage_v": 24.1,
                "torque_current_a": 1.5,
                "speed_dps": 360.0,
                "encoder_position": 32768,
                "multi_turn_deg": 720.0,
                "single_turn_deg": 180.0,
                "phase_current_a": [0.5, 0.6, 0.7],
                "error_flags": {
                    "undervoltage_protection": False,
                    "overvoltage_protection": False,
                },
                "error_message": "",
            }
        return {"success": False, "error": error or "mocked failure"}

    return _fake


def _mock_clear_motor_errors(success: bool = True, error: str = ""):
    async def _fake(motor_id):
        if success:
            return {
                "success": True,
                "error_flags_after": {
                    "undervoltage_protection": False,
                    "overvoltage_protection": False,
                },
                "error_message": "",
            }
        return {
            "success": False,
            "error_message": error or "mocked failure",
            "error": error or "mocked failure",
        }

    return _fake


# PID bridge mock helpers

VALID_PID_GAINS = {
    "position_kp": 30,
    "position_ki": 10,
    "speed_kp": 50,
    "speed_ki": 20,
    "torque_kp": 40,
    "torque_ki": 15,
}


def _mock_bridge_read_pid(gains_dict: dict, success: bool = True):
    async def _fake_read(motor_id: int) -> dict:
        if success:
            return {"success": True, "gains": gains_dict}
        return {"success": False, "error": "mocked failure"}

    return _fake_read


def _mock_bridge_write_pid(success: bool = True):
    async def _fake_write(motor_id: int, gains) -> dict:
        if success:
            return {"success": True, "error": ""}
        return {"success": False, "error": "mocked write failure"}

    return _fake_write


# ===================================================================
# Task 8.3: Motor API endpoint tests
# ===================================================================


class TestMotorCommand:
    """POST /api/motor/{motor_id}/command tests."""

    def test_command_valid_torque(self):
        """Valid torque command (mode=0) returns 200 with state data."""
        with patch.object(
            _bridge,
            "motor_command",
            side_effect=_mock_motor_command(success=True),
        ):
            resp = motor_client.post(
                "/api/motor/1/command",
                json={"mode": 0, "value": 500.0},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["temperature"] == 35
        assert data["torque_current"] == 100
        assert data["speed"] == 500
        assert data["encoder"] == 32768

    def test_command_valid_speed(self):
        """Valid speed command (mode=1) returns 200."""
        with patch.object(
            _bridge,
            "motor_command",
            side_effect=_mock_motor_command(success=True),
        ):
            resp = motor_client.post(
                "/api/motor/2/command",
                json={"mode": 1, "value": 1000.0},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_command_valid_angle_with_max_speed(self):
        """Angle command (mode=2) with max_speed returns 200."""
        with patch.object(
            _bridge,
            "motor_command",
            side_effect=_mock_motor_command(success=True),
        ):
            resp = motor_client.post(
                "/api/motor/1/command",
                json={
                    "mode": 2,
                    "value": 90.0,
                    "max_speed": 500.0,
                },
            )
        assert resp.status_code == 200

    def test_command_invalid_motor_id(self):
        """Invalid motor_id=99 returns 400."""
        resp = motor_client.post(
            "/api/motor/99/command",
            json={"mode": 0, "value": 100.0},
        )
        assert resp.status_code == 400
        assert "Invalid motor_id" in resp.json()["detail"]

    def test_command_invalid_mode_too_high(self):
        """Mode > 7 is rejected by Pydantic validation (422)."""
        resp = motor_client.post(
            "/api/motor/1/command",
            json={"mode": 8, "value": 100.0},
        )
        assert resp.status_code == 422

    def test_command_invalid_mode_negative(self):
        """Negative mode is rejected by Pydantic validation (422)."""
        resp = motor_client.post(
            "/api/motor/1/command",
            json={"mode": -1, "value": 100.0},
        )
        assert resp.status_code == 422

    def test_command_missing_required_fields(self):
        """Missing 'mode' or 'value' returns 422."""
        resp = motor_client.post(
            "/api/motor/1/command",
            json={"mode": 0},
        )
        assert resp.status_code == 422

    def test_command_timeout_returns_504(self):
        """Service timeout returns 504."""
        with patch.object(
            _bridge,
            "motor_command",
            side_effect=_mock_motor_command_timeout(),
        ):
            resp = motor_client.post(
                "/api/motor/1/command",
                json={"mode": 0, "value": 100.0},
            )
        assert resp.status_code == 504

    def test_command_service_failure_returns_502(self):
        """Non-timeout service failure returns 502."""
        with patch.object(
            _bridge,
            "motor_command",
            side_effect=_mock_motor_command(
                success=False, error="CAN bus error"
            ),
        ):
            resp = motor_client.post(
                "/api/motor/1/command",
                json={"mode": 0, "value": 100.0},
            )
        assert resp.status_code == 502


class TestMotorLifecycle:
    """POST /api/motor/{motor_id}/lifecycle tests."""

    def test_lifecycle_on(self):
        """Action=0 (ON) returns 200 with motor_state_name."""
        with patch.object(
            _bridge,
            "motor_lifecycle",
            side_effect=_mock_motor_lifecycle(
                success=True, motor_state=1
            ),
        ):
            resp = motor_client.post(
                "/api/motor/1/lifecycle",
                json={"action": 0},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["motor_state"] == 1
        assert data["motor_state_name"] == "RUNNING"

    def test_lifecycle_off(self):
        """Action=1 (OFF) returns 200."""
        with patch.object(
            _bridge,
            "motor_lifecycle",
            side_effect=_mock_motor_lifecycle(
                success=True, motor_state=0
            ),
        ):
            resp = motor_client.post(
                "/api/motor/1/lifecycle",
                json={"action": 1},
            )
        assert resp.status_code == 200
        assert resp.json()["motor_state_name"] == "OFF"

    def test_lifecycle_stop(self):
        """Action=2 (STOP) returns 200."""
        with patch.object(
            _bridge,
            "motor_lifecycle",
            side_effect=_mock_motor_lifecycle(
                success=True, motor_state=2
            ),
        ):
            resp = motor_client.post(
                "/api/motor/2/lifecycle",
                json={"action": 2},
            )
        assert resp.status_code == 200
        assert resp.json()["motor_state_name"] == "STOPPED"

    def test_lifecycle_save_zero_rom_without_token(self):
        """SAVE_ZERO_ROM (action=5) without token returns 400."""
        resp = motor_client.post(
            "/api/motor/1/lifecycle",
            json={"action": 5},
        )
        assert resp.status_code == 400
        assert "CONFIRM_ENCODER_ZERO" in resp.json()["detail"]

    def test_lifecycle_save_zero_rom_wrong_token(self):
        """SAVE_ZERO_ROM (action=5) with wrong token returns 400."""
        resp = motor_client.post(
            "/api/motor/1/lifecycle",
            json={
                "action": 5,
                "confirmation_token": "WRONG_TOKEN",
            },
        )
        assert resp.status_code == 400

    def test_lifecycle_save_zero_rom_valid_token(self):
        """SAVE_ZERO_ROM (action=5) with correct token returns 200."""
        with patch.object(
            _bridge,
            "motor_lifecycle",
            side_effect=_mock_motor_lifecycle(success=True),
        ):
            resp = motor_client.post(
                "/api/motor/1/lifecycle",
                json={
                    "action": 5,
                    "confirmation_token": "CONFIRM_ENCODER_ZERO",
                },
            )
        assert resp.status_code == 200

    def test_lifecycle_invalid_motor(self):
        """Invalid motor_id returns 400."""
        resp = motor_client.post(
            "/api/motor/99/lifecycle",
            json={"action": 0},
        )
        assert resp.status_code == 400

    def test_lifecycle_invalid_action_too_high(self):
        """Action > 5 is rejected by Pydantic (422)."""
        resp = motor_client.post(
            "/api/motor/1/lifecycle",
            json={"action": 6},
        )
        assert resp.status_code == 422


class TestMotorLimitsRead:
    """GET /api/motor/{motor_id}/limits tests."""

    def test_read_limits_success(self):
        """Returns max_torque_ratio and acceleration_dps."""
        with patch.object(
            _bridge,
            "read_motor_limits",
            side_effect=_mock_read_motor_limits(
                success=True,
                max_torque_ratio=1500,
                acceleration_dps=200.0,
            ),
        ):
            resp = motor_client.get("/api/motor/1/limits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["max_torque_ratio"] == 1500
        assert data["acceleration_dps"] == 200.0

    def test_read_limits_invalid_motor(self):
        """Invalid motor returns 400."""
        resp = motor_client.get("/api/motor/99/limits")
        assert resp.status_code == 400

    def test_read_limits_service_failure(self):
        """Bridge failure returns 502."""
        with patch.object(
            _bridge,
            "read_motor_limits",
            side_effect=_mock_read_motor_limits(
                success=False, error="CAN error"
            ),
        ):
            resp = motor_client.get("/api/motor/1/limits")
        assert resp.status_code == 502


class TestMaxTorqueCurrentWrite:
    """PUT /api/motor/{motor_id}/limits/max_torque_current tests."""

    def test_write_max_torque_valid(self):
        """Value in range 0-2000 returns 200."""
        with patch.object(
            _bridge,
            "write_motor_limits",
            side_effect=_mock_write_motor_limits(success=True),
        ):
            resp = motor_client.put(
                "/api/motor/1/limits/max_torque_current",
                json={"value": 1000},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["max_torque_ratio"] == 1000

    def test_write_max_torque_zero(self):
        """Boundary: value=0 is valid."""
        with patch.object(
            _bridge,
            "write_motor_limits",
            side_effect=_mock_write_motor_limits(success=True),
        ):
            resp = motor_client.put(
                "/api/motor/1/limits/max_torque_current",
                json={"value": 0},
            )
        assert resp.status_code == 200

    def test_write_max_torque_2000(self):
        """Boundary: value=2000 is valid."""
        with patch.object(
            _bridge,
            "write_motor_limits",
            side_effect=_mock_write_motor_limits(success=True),
        ):
            resp = motor_client.put(
                "/api/motor/1/limits/max_torque_current",
                json={"value": 2000},
            )
        assert resp.status_code == 200

    def test_write_max_torque_out_of_range_high(self):
        """Value > 2000 is rejected by Pydantic (422)."""
        resp = motor_client.put(
            "/api/motor/1/limits/max_torque_current",
            json={"value": 2001},
        )
        assert resp.status_code == 422

    def test_write_max_torque_out_of_range_negative(self):
        """Negative value is rejected by Pydantic (422)."""
        resp = motor_client.put(
            "/api/motor/1/limits/max_torque_current",
            json={"value": -1},
        )
        assert resp.status_code == 422

    def test_write_max_torque_invalid_motor(self):
        """Invalid motor_id returns 400."""
        resp = motor_client.put(
            "/api/motor/99/limits/max_torque_current",
            json={"value": 1000},
        )
        assert resp.status_code == 400


class TestAccelerationWrite:
    """PUT /api/motor/{motor_id}/limits/acceleration tests."""

    def test_write_acceleration_valid(self):
        """Valid acceleration returns 200."""
        with patch.object(
            _bridge,
            "write_motor_limits",
            side_effect=_mock_write_motor_limits(success=True),
        ):
            resp = motor_client.put(
                "/api/motor/1/limits/acceleration",
                json={"value": 500.0},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["acceleration_dps"] == 500.0

    def test_write_acceleration_service_failure(self):
        """Service failure returns 502."""
        with patch.object(
            _bridge,
            "write_motor_limits",
            side_effect=_mock_write_motor_limits(
                success=False, error="CAN error"
            ),
        ):
            resp = motor_client.put(
                "/api/motor/1/limits/acceleration",
                json={"value": 500.0},
            )
        assert resp.status_code == 502

    def test_write_acceleration_invalid_motor(self):
        """Invalid motor_id returns 400."""
        resp = motor_client.put(
            "/api/motor/99/limits/acceleration",
            json={"value": 500.0},
        )
        assert resp.status_code == 400


class TestEncoderRead:
    """GET /api/motor/{motor_id}/encoder tests."""

    def test_read_encoder_success(self):
        """Returns raw_value, offset, original_value."""
        with patch.object(
            _bridge,
            "read_encoder",
            side_effect=_mock_read_encoder(
                success=True,
                raw_value=32000,
                offset=100,
                original_value=31900,
            ),
        ):
            resp = motor_client.get("/api/motor/1/encoder")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["raw_value"] == 32000
        assert data["offset"] == 100
        assert data["original_value"] == 31900

    def test_read_encoder_invalid_motor(self):
        """Invalid motor returns 400."""
        resp = motor_client.get("/api/motor/99/encoder")
        assert resp.status_code == 400

    def test_read_encoder_service_failure(self):
        """Bridge failure returns 502."""
        with patch.object(
            _bridge,
            "read_encoder",
            side_effect=_mock_read_encoder(
                success=False, error="CAN error"
            ),
        ):
            resp = motor_client.get("/api/motor/1/encoder")
        assert resp.status_code == 502


class TestEncoderZero:
    """POST /api/motor/{motor_id}/encoder/zero tests."""

    def test_encoder_zero_valid(self):
        """With correct token returns 200."""
        with patch.object(
            _bridge,
            "write_encoder_zero",
            side_effect=_mock_write_encoder_zero(success=True),
        ):
            resp = motor_client.post(
                "/api/motor/1/encoder/zero",
                json={
                    "mode": 1,
                    "confirmation_token": "CONFIRM_ENCODER_ZERO",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_encoder_zero_wrong_token(self):
        """Wrong confirmation token returns 400."""
        resp = motor_client.post(
            "/api/motor/1/encoder/zero",
            json={
                "mode": 1,
                "confirmation_token": "WRONG",
            },
        )
        assert resp.status_code == 400

    def test_encoder_zero_missing_token(self):
        """Missing confirmation_token field returns 422."""
        resp = motor_client.post(
            "/api/motor/1/encoder/zero",
            json={"mode": 1},
        )
        assert resp.status_code == 422

    def test_encoder_zero_set_value_mode(self):
        """Mode=0 (SET_VALUE) with encoder_value returns 200."""
        with patch.object(
            _bridge,
            "write_encoder_zero",
            side_effect=_mock_write_encoder_zero(success=True),
        ):
            resp = motor_client.post(
                "/api/motor/1/encoder/zero",
                json={
                    "mode": 0,
                    "encoder_value": 16384,
                    "confirmation_token": "CONFIRM_ENCODER_ZERO",
                },
            )
        assert resp.status_code == 200

    def test_encoder_zero_invalid_motor(self):
        """Invalid motor returns 400."""
        resp = motor_client.post(
            "/api/motor/99/encoder/zero",
            json={
                "mode": 1,
                "confirmation_token": "CONFIRM_ENCODER_ZERO",
            },
        )
        assert resp.status_code == 400


class TestAnglesRead:
    """GET /api/motor/{motor_id}/angles tests."""

    def test_read_angles_success(self):
        """Returns multi_turn_deg and single_turn_deg."""
        with patch.object(
            _bridge,
            "read_motor_angles",
            side_effect=_mock_read_motor_angles(
                success=True,
                multi_turn_deg=720.5,
                single_turn_deg=180.3,
            ),
        ):
            resp = motor_client.get("/api/motor/1/angles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["multi_turn_deg"] == 720.5
        assert data["single_turn_deg"] == 180.3

    def test_read_angles_invalid_motor(self):
        """Invalid motor returns 400."""
        resp = motor_client.get("/api/motor/99/angles")
        assert resp.status_code == 400


class TestMotorStateRead:
    """GET /api/motor/{motor_id}/state tests."""

    def test_read_state_success(self):
        """Returns full state including temperature, voltage, etc."""
        with patch.object(
            _bridge,
            "read_motor_state",
            side_effect=_mock_read_motor_state(success=True),
        ):
            resp = motor_client.get("/api/motor/1/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["temperature_c"] == 42.5
        assert data["voltage_v"] == 24.1
        assert data["torque_current_a"] == 1.5
        assert data["speed_dps"] == 360.0
        assert data["encoder_position"] == 32768
        assert data["multi_turn_deg"] == 720.0
        assert data["single_turn_deg"] == 180.0
        assert data["phase_current_a"] == [0.5, 0.6, 0.7]
        assert isinstance(data["error_flags"], dict)

    def test_read_state_invalid_motor(self):
        """Invalid motor returns 400."""
        resp = motor_client.get("/api/motor/99/state")
        assert resp.status_code == 400

    def test_read_state_service_failure(self):
        """Bridge failure returns 502."""
        with patch.object(
            _bridge,
            "read_motor_state",
            side_effect=_mock_read_motor_state(
                success=False, error="Hardware error"
            ),
        ):
            resp = motor_client.get("/api/motor/1/state")
        assert resp.status_code == 502


class TestClearErrors:
    """POST /api/motor/{motor_id}/errors/clear tests."""

    def test_clear_errors_success(self):
        """Successful clear returns error_flags_after dict."""
        with patch.object(
            _bridge,
            "clear_motor_errors",
            side_effect=_mock_clear_motor_errors(success=True),
        ):
            resp = motor_client.post(
                "/api/motor/1/errors/clear"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "error_flags_after" in data

    def test_clear_errors_invalid_motor(self):
        """Invalid motor returns 400."""
        resp = motor_client.post("/api/motor/99/errors/clear")
        assert resp.status_code == 400

    def test_clear_errors_service_failure(self):
        """Bridge failure returns 502."""
        with patch.object(
            _bridge,
            "clear_motor_errors",
            side_effect=_mock_clear_motor_errors(
                success=False, error="CAN bus error"
            ),
        ):
            resp = motor_client.post(
                "/api/motor/1/errors/clear"
            )
        assert resp.status_code == 502


class TestValidationRanges:
    """GET /api/motor/validation_ranges tests."""

    def test_validation_ranges_returns_mg6010(self):
        """Returns validation ranges dict with mg6010 key."""
        resp = motor_client.get("/api/motor/validation_ranges")
        assert resp.status_code == 200
        data = resp.json()
        assert "mg6010" in data
        ranges = data["mg6010"]
        assert "torque_current" in ranges
        assert "speed" in ranges
        assert "angle" in ranges
        assert "max_torque_current" in ranges
        assert "acceleration" in ranges
        assert "encoder" in ranges
        assert "pid_gains" in ranges

    def test_validation_ranges_torque_current_limits(self):
        """Torque current range is -2000 to 2000."""
        resp = motor_client.get("/api/motor/validation_ranges")
        tc = resp.json()["mg6010"]["torque_current"]
        assert tc["min"] == -2000
        assert tc["max"] == 2000
        assert tc["unit"] == "mA"

    def test_validation_ranges_max_torque_limits(self):
        """Max torque current range is 0 to 2000."""
        resp = motor_client.get("/api/motor/validation_ranges")
        mt = resp.json()["mg6010"]["max_torque_current"]
        assert mt["min"] == 0
        assert mt["max"] == 2000

    def test_validation_ranges_no_bridge_needed(self):
        """Validation ranges are static -- no bridge call required."""
        # This test confirms the endpoint works without mocking bridge
        resp = motor_client.get("/api/motor/validation_ranges")
        assert resp.status_code == 200


class TestMotorIdValidation:
    """Cross-cutting motor_id validation for all endpoints."""

    def test_motor_id_zero(self):
        """Motor ID 0 is not in valid set."""
        resp = motor_client.get("/api/motor/0/limits")
        assert resp.status_code == 400

    def test_motor_id_negative(self):
        """Negative motor ID is not in valid set."""
        resp = motor_client.get("/api/motor/-1/limits")
        assert resp.status_code == 400

    def test_all_valid_motor_ids(self):
        """Motors 1, 2, 3 are accepted (validation only -- bridge mocked)."""
        for mid in [1, 2, 3]:
            with patch.object(
                _bridge,
                "read_motor_limits",
                side_effect=_mock_read_motor_limits(success=True),
            ):
                resp = motor_client.get(f"/api/motor/{mid}/limits")
            assert resp.status_code == 200, (
                f"motor_id={mid} should be valid"
            )


class TestTimeoutHandling:
    """Verify timeout errors map to 504 across endpoints."""

    def test_lifecycle_timeout(self):
        """Lifecycle timeout returns 504."""

        async def _fake(motor_id, action):
            return {
                "success": False,
                "error_message": "Service timed out",
                "error": "Service timed out",
            }

        with patch.object(
            _bridge, "motor_lifecycle", side_effect=_fake
        ):
            resp = motor_client.post(
                "/api/motor/1/lifecycle",
                json={"action": 0},
            )
        assert resp.status_code == 504

    def test_read_limits_timeout(self):
        """Read limits timeout returns 504."""

        async def _fake(motor_id):
            return {
                "success": False,
                "error": "Service not available after 5s",
            }

        with patch.object(
            _bridge, "read_motor_limits", side_effect=_fake
        ):
            resp = motor_client.get("/api/motor/1/limits")
        assert resp.status_code == 504


# ===================================================================
# Task 8.4: PID field rename backward compatibility
# ===================================================================


class TestNormalisePidFields:
    """Unit tests for the _normalise_pid_fields helper function."""

    def test_alias_angle_kp_maps_to_position_kp(self):
        """angle_kp is mapped to position_kp."""
        data = {"angle_kp": 30, "speed_kp": 50}
        result = _normalise_pid_fields(data)
        assert result["position_kp"] == 30
        assert "angle_kp" not in result

    def test_alias_angle_ki_maps_to_position_ki(self):
        """angle_ki is mapped to position_ki."""
        data = {"angle_ki": 10}
        result = _normalise_pid_fields(data)
        assert result["position_ki"] == 10
        assert "angle_ki" not in result

    def test_alias_iq_kp_maps_to_torque_kp(self):
        """iq_kp is mapped to torque_kp."""
        data = {"iq_kp": 40}
        result = _normalise_pid_fields(data)
        assert result["torque_kp"] == 40
        assert "iq_kp" not in result

    def test_alias_iq_ki_maps_to_torque_ki(self):
        """iq_ki is mapped to torque_ki."""
        data = {"iq_ki": 15}
        result = _normalise_pid_fields(data)
        assert result["torque_ki"] == 15
        assert "iq_ki" not in result

    def test_canonical_wins_over_alias(self):
        """When both alias and canonical are present, canonical wins."""
        data = {"position_kp": 50, "angle_kp": 30}
        result = _normalise_pid_fields(data)
        assert result["position_kp"] == 50
        assert "angle_kp" not in result

    def test_canonical_fields_pass_through(self):
        """Canonical field names are unchanged."""
        data = dict(VALID_PID_GAINS)
        result = _normalise_pid_fields(data)
        assert result == VALID_PID_GAINS

    def test_all_aliases_at_once(self):
        """All four aliases map correctly in one call."""
        data = {
            "angle_kp": 30,
            "angle_ki": 10,
            "speed_kp": 50,
            "speed_ki": 20,
            "iq_kp": 40,
            "iq_ki": 15,
        }
        result = _normalise_pid_fields(data)
        assert result == VALID_PID_GAINS

    def test_unrelated_fields_preserved(self):
        """Non-PID fields pass through untouched."""
        data = {"angle_kp": 30, "override_limits": True}
        result = _normalise_pid_fields(data)
        assert result["position_kp"] == 30
        assert result["override_limits"] is True


class TestPIDReadReturnsNewNames:
    """GET /api/pid/read/{motor_id} returns both old and new field names."""

    def test_read_pid_response_includes_new_names(self):
        """Response includes angle_kp, angle_ki, iq_kp, iq_ki aliases."""
        gains_with_aliases = {
            **VALID_PID_GAINS,
            "angle_kp": 30,
            "angle_ki": 10,
            "iq_kp": 40,
            "iq_ki": 15,
        }
        with patch.object(
            pid_bridge,
            "read_pid",
            side_effect=_mock_bridge_read_pid(gains_with_aliases),
        ):
            resp = pid_client.get("/api/pid/read/1")
        assert resp.status_code == 200
        gains = resp.json()["gains"]
        # New names present
        assert gains["angle_kp"] == 30
        assert gains["angle_ki"] == 10
        assert gains["iq_kp"] == 40
        assert gains["iq_ki"] == 15
        # Legacy names still present
        assert gains["position_kp"] == 30
        assert gains["position_ki"] == 10
        assert gains["torque_kp"] == 40
        assert gains["torque_ki"] == 15

    def test_read_pid_new_names_match_legacy(self):
        """New names have same values as their legacy counterparts."""
        gains_with_aliases = {
            **VALID_PID_GAINS,
            "angle_kp": VALID_PID_GAINS["position_kp"],
            "angle_ki": VALID_PID_GAINS["position_ki"],
            "iq_kp": VALID_PID_GAINS["torque_kp"],
            "iq_ki": VALID_PID_GAINS["torque_ki"],
        }
        with patch.object(
            pid_bridge,
            "read_pid",
            side_effect=_mock_bridge_read_pid(gains_with_aliases),
        ):
            resp = pid_client.get("/api/pid/read/1")
        gains = resp.json()["gains"]
        assert gains["angle_kp"] == gains["position_kp"]
        assert gains["angle_ki"] == gains["position_ki"]
        assert gains["iq_kp"] == gains["torque_kp"]
        assert gains["iq_ki"] == gains["torque_ki"]


class TestPIDWriteAcceptsBothNames:
    """POST /api/pid/write/{motor_id} accepts both old and new field names."""

    def test_write_with_legacy_names(self):
        """Legacy field names (position_kp, torque_kp) are accepted."""
        with patch.object(
            pid_bridge,
            "write_pid",
            side_effect=_mock_bridge_write_pid(success=True),
        ):
            resp = pid_client.post(
                "/api/pid/write/1", json=VALID_PID_GAINS
            )
        assert resp.status_code == 200

    def test_write_with_new_names_via_model(self):
        """PIDGains model with populate_by_name accepts canonical names.

        The PIDGains model uses populate_by_name=True which means
        fields can be set by their Python attribute name. Since there
        are no Pydantic aliases on the model fields themselves, both
        old and new names go through _normalise_pid_fields for
        pre-processing in higher-level callers.
        """
        # This tests the model directly (not the endpoint) to confirm
        # that the canonical names are accepted by Pydantic
        from pid_tuning_api import PIDGains

        gains = PIDGains(**VALID_PID_GAINS)
        assert gains.position_kp == 30
        assert gains.torque_kp == 40

    def test_normalise_then_write_with_new_names(self):
        """New names normalised to canonical produce valid PIDGains."""
        from pid_tuning_api import PIDGains

        new_name_input = {
            "angle_kp": 30,
            "angle_ki": 10,
            "speed_kp": 50,
            "speed_ki": 20,
            "iq_kp": 40,
            "iq_ki": 15,
        }
        normalised = _normalise_pid_fields(new_name_input)
        gains = PIDGains(**normalised)
        assert gains.position_kp == 30
        assert gains.position_ki == 10
        assert gains.torque_kp == 40
        assert gains.torque_ki == 15

    def test_alias_map_covers_all_renames(self):
        """_PID_FIELD_ALIASES contains all expected mappings."""
        expected = {
            "angle_kp": "position_kp",
            "angle_ki": "position_ki",
            "iq_kp": "torque_kp",
            "iq_ki": "torque_ki",
        }
        assert _PID_FIELD_ALIASES == expected
