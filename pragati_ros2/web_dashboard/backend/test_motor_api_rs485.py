"""Tests for RS485 fallback integration in MotorConfigBridge.

Verifies that when ROS2 is unavailable but an RS485 driver is connected,
the bridge methods fall back to direct serial communication with the motor.

RED phase: These tests should all FAIL before implementation.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock ROS2 modules so we can import motor_api without ROS2 installed.
# Force ROS2_AVAILABLE = False to test the RS485 fallback path.
# ---------------------------------------------------------------------------
sys.modules.setdefault("rclpy", MagicMock())
sys.modules.setdefault("rclpy.node", MagicMock())
sys.modules.setdefault("rclpy.callback_groups", MagicMock())
sys.modules.setdefault("rclpy.qos", MagicMock())
sys.modules.setdefault("motor_control_msgs", MagicMock())
sys.modules.setdefault("motor_control_msgs.srv", MagicMock())
sys.modules.setdefault("std_msgs", MagicMock())
sys.modules.setdefault("std_msgs.msg", MagicMock())

# Ensure backend is importable
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import backend.motor_api as motor_api_module  # noqa: E402
from backend.motor_api import MotorConfigBridge, initialize_motor_bridge  # noqa: E402
from backend.rs485_driver import RS485MotorDriver  # noqa: E402

# Force ROS2 unavailable for all tests in this file
motor_api_module.ROS2_AVAILABLE = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_rs485():
    """Create a mock RS485MotorDriver with all methods stubbed."""
    driver = MagicMock(spec=RS485MotorDriver)
    driver.port = "/dev/ttyUSB0"
    driver.motor_id = 3
    driver.connect.return_value = True
    # Simulate connected state
    driver._serial = MagicMock()
    driver._serial.is_open = True
    return driver


@pytest.fixture
def bridge_with_rs485(mock_rs485):
    """Create a MotorConfigBridge with RS485 driver injected."""
    bridge = MotorConfigBridge()
    bridge.set_rs485_driver(mock_rs485)
    return bridge


# ---------------------------------------------------------------------------
# 1. Bridge accepts and stores RS485 driver
# ---------------------------------------------------------------------------


class TestBridgeRS485Setup:
    """Test that MotorConfigBridge can accept an RS485 driver."""

    def test_set_rs485_driver(self, mock_rs485):
        """Bridge should have a set_rs485_driver() method."""
        bridge = MotorConfigBridge()
        bridge.set_rs485_driver(mock_rs485)
        assert bridge._rs485_driver is mock_rs485

    def test_has_rs485_property(self, bridge_with_rs485):
        """Bridge should expose whether RS485 is available."""
        assert bridge_with_rs485.has_rs485 is True

    def test_has_rs485_false_by_default(self):
        """Bridge without RS485 driver should report False."""
        bridge = MotorConfigBridge()
        assert bridge.has_rs485 is False

    def test_transport_mode_rs485(self, bridge_with_rs485):
        """Bridge should report transport mode as 'rs485' when driver set."""
        assert bridge_with_rs485.transport_mode == "rs485"

    def test_transport_mode_none(self):
        """Bridge without any transport should report 'none'."""
        bridge = MotorConfigBridge()
        # ROS2 unavailable and no RS485
        bridge._node = None
        assert bridge.transport_mode == "none"


# ---------------------------------------------------------------------------
# 2. initialize_motor_bridge() accepts serial config
# ---------------------------------------------------------------------------


class TestInitializeMotorBridge:
    """Test that initialize_motor_bridge() can accept RS485 config."""

    def test_initialize_with_serial_port(self):
        """initialize_motor_bridge should accept serial_port kwarg."""
        with patch.object(motor_api_module, "_bridge", MotorConfigBridge()) as mock_bridge_inst:
            # Should not raise
            initialize_motor_bridge(serial_port="/dev/ttyUSB0", motor_id=3)

    def test_initialize_without_serial_is_backward_compatible(self):
        """Calling with no args should still work (backward compatible)."""
        with patch.object(motor_api_module, "_bridge", MotorConfigBridge()):
            # Should not raise — existing call sites pass no args
            initialize_motor_bridge()


# ---------------------------------------------------------------------------
# 3. Bridge methods fall back to RS485 when ROS2 unavailable
# ---------------------------------------------------------------------------


class TestRS485FallbackMotorCommand:
    """Test motor_command falls back to RS485."""

    @pytest.mark.asyncio
    async def test_torque_command_via_rs485(self, bridge_with_rs485, mock_rs485):
        """mode=0 (TORQUE) should call rs485 send_torque_command."""
        mock_rs485.send_torque_command.return_value = {
            "temperature_c": 35.0,
            "torque_current_a": 0.5,
            "speed_dps": 10.0,
            "encoder_position": 1234,
        }

        result = await bridge_with_rs485.motor_command(motor_id=3, command_type=0, value=500.0)

        assert result["success"] is True
        assert result["temperature"] == 35
        mock_rs485.send_torque_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_speed_command_via_rs485(self, bridge_with_rs485, mock_rs485):
        """mode=1 (SPEED) should call rs485 send_speed_command."""
        mock_rs485.send_speed_command.return_value = {
            "temperature_c": 36.0,
            "torque_current_a": 1.0,
            "speed_dps": 360.0,
            "encoder_position": 2000,
        }

        result = await bridge_with_rs485.motor_command(motor_id=3, command_type=1, value=360.0)

        assert result["success"] is True
        assert result["speed"] == 360
        mock_rs485.send_speed_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_position_command_via_rs485(self, bridge_with_rs485, mock_rs485):
        """mode=2 (MULTI_ANGLE_1) should call rs485 send_position_command."""
        mock_rs485.send_position_command.return_value = {
            "temperature_c": 37.0,
            "torque_current_a": 2.0,
            "speed_dps": 100.0,
            "encoder_position": 3000,
        }

        result = await bridge_with_rs485.motor_command(motor_id=3, command_type=2, value=90.0)

        assert result["success"] is True
        mock_rs485.send_position_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_rs485_command_timeout(self, bridge_with_rs485, mock_rs485):
        """RS485 returning None should produce success=False."""
        mock_rs485.send_torque_command.return_value = None

        result = await bridge_with_rs485.motor_command(motor_id=3, command_type=0, value=100.0)

        assert result["success"] is False
        assert "error" in result or "error_message" in result


class TestRS485FallbackLifecycle:
    """Test motor_lifecycle falls back to RS485."""

    @pytest.mark.asyncio
    async def test_motor_on_via_rs485(self, bridge_with_rs485, mock_rs485):
        """action=0 (ON) should call rs485 motor_on."""
        mock_rs485.motor_on.return_value = {
            "cmd": 0x88,
            "motor_id": 3,
            "data_len": 0,
            "data": b"",
        }

        result = await bridge_with_rs485.motor_lifecycle(motor_id=3, action=0)

        assert result["success"] is True
        mock_rs485.motor_on.assert_called_once()

    @pytest.mark.asyncio
    async def test_motor_off_via_rs485(self, bridge_with_rs485, mock_rs485):
        """action=1 (OFF) should call rs485 motor_off."""
        mock_rs485.motor_off.return_value = {
            "cmd": 0x80,
            "motor_id": 3,
            "data_len": 0,
            "data": b"",
        }

        result = await bridge_with_rs485.motor_lifecycle(motor_id=3, action=1)

        assert result["success"] is True
        mock_rs485.motor_off.assert_called_once()

    @pytest.mark.asyncio
    async def test_motor_stop_via_rs485(self, bridge_with_rs485, mock_rs485):
        """action=2 (STOP) should call rs485 motor_stop."""
        mock_rs485.motor_stop.return_value = {
            "cmd": 0x81,
            "motor_id": 3,
            "data_len": 0,
            "data": b"",
        }

        result = await bridge_with_rs485.motor_lifecycle(motor_id=3, action=2)

        assert result["success"] is True
        mock_rs485.motor_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsupported_lifecycle_action(self, bridge_with_rs485, mock_rs485):
        """action=3 (REBOOT) is not supported via RS485 -- should fail gracefully."""
        result = await bridge_with_rs485.motor_lifecycle(motor_id=3, action=3)

        assert result["success"] is False
        assert (
            "not supported" in result.get("error", "").lower()
            or "not supported" in result.get("error_message", "").lower()
        )


class TestRS485FallbackReadMotorLimits:
    """Test read_motor_limits falls back to RS485."""

    @pytest.mark.asyncio
    async def test_read_limits_via_rs485(self, bridge_with_rs485, mock_rs485):
        """Should read max_torque and acceleration via RS485."""
        mock_rs485.read_max_torque.return_value = 1500
        mock_rs485.read_acceleration.return_value = 3600.0

        result = await bridge_with_rs485.read_motor_limits(motor_id=3)

        assert result["success"] is True
        assert result["max_torque_ratio"] == 1500
        assert result["acceleration_dps"] == 3600.0
        mock_rs485.read_max_torque.assert_called_once()
        mock_rs485.read_acceleration.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_limits_rs485_failure(self, bridge_with_rs485, mock_rs485):
        """RS485 returning None should produce success=False."""
        mock_rs485.read_max_torque.return_value = None
        mock_rs485.read_acceleration.return_value = None

        result = await bridge_with_rs485.read_motor_limits(motor_id=3)

        assert result["success"] is False


class TestRS485FallbackWriteMotorLimits:
    """Test write_motor_limits falls back to RS485."""

    @pytest.mark.asyncio
    async def test_write_max_torque_via_rs485(self, bridge_with_rs485, mock_rs485):
        """set_max_torque=True should call rs485 write_max_torque."""
        mock_rs485.write_max_torque.return_value = {"cmd": 0x38}

        result = await bridge_with_rs485.write_motor_limits(
            motor_id=3, max_torque_ratio=1500, set_max_torque=True
        )

        assert result["success"] is True
        mock_rs485.write_max_torque.assert_called_once_with(1500)

    @pytest.mark.asyncio
    async def test_write_acceleration_via_rs485(self, bridge_with_rs485, mock_rs485):
        """set_acceleration=True should call rs485 write_acceleration."""
        mock_rs485.write_acceleration.return_value = {"cmd": 0x34}

        result = await bridge_with_rs485.write_motor_limits(
            motor_id=3, acceleration_dps=3600.0, set_acceleration=True
        )

        assert result["success"] is True
        mock_rs485.write_acceleration.assert_called_once_with(3600)


class TestRS485FallbackReadEncoder:
    """Test read_encoder falls back to RS485."""

    @pytest.mark.asyncio
    async def test_read_encoder_via_rs485(self, bridge_with_rs485, mock_rs485):
        """Should return encoder values from RS485 driver."""
        mock_rs485.read_encoder.return_value = {
            "raw_value": 12345,
            "offset": 100,
            "original_value": 12245,
        }

        result = await bridge_with_rs485.read_encoder(motor_id=3)

        assert result["success"] is True
        assert result["raw_value"] == 12345
        assert result["offset"] == 100
        assert result["original_value"] == 12245


class TestRS485FallbackWriteEncoderZero:
    """Test write_encoder_zero falls back to RS485."""

    @pytest.mark.asyncio
    async def test_write_encoder_zero_via_rs485(self, bridge_with_rs485, mock_rs485):
        """mode=1 (SET_CURRENT_POS) should call rs485 set_encoder_zero."""
        mock_rs485.set_encoder_zero.return_value = {"success": True}

        result = await bridge_with_rs485.write_encoder_zero(motor_id=3, mode=1)

        assert result["success"] is True
        mock_rs485.set_encoder_zero.assert_called_once()


class TestRS485FallbackReadMotorAngles:
    """Test read_motor_angles falls back to RS485."""

    @pytest.mark.asyncio
    async def test_read_angles_via_rs485(self, bridge_with_rs485, mock_rs485):
        """Should read multi-turn and single-turn angles from RS485."""
        mock_rs485.read_multi_turn_angle.return_value = 720.5
        mock_rs485.read_single_turn_angle.return_value = 45.3

        result = await bridge_with_rs485.read_motor_angles(motor_id=3)

        assert result["success"] is True
        assert result["multi_turn_deg"] == 720.5
        assert result["single_turn_deg"] == 45.3


class TestRS485FallbackClearErrors:
    """Test clear_motor_errors falls back to RS485."""

    @pytest.mark.asyncio
    async def test_clear_errors_via_rs485(self, bridge_with_rs485, mock_rs485):
        """Should call rs485 clear_errors and decode flags."""
        mock_rs485.clear_errors.return_value = {"error_byte": 0}

        result = await bridge_with_rs485.clear_motor_errors(motor_id=3)

        assert result["success"] is True
        assert "error_flags_after" in result
        mock_rs485.clear_errors.assert_called_once()


class TestRS485FallbackReadMotorState:
    """Test read_motor_state falls back to RS485."""

    @pytest.mark.asyncio
    async def test_read_state_via_rs485(self, bridge_with_rs485, mock_rs485):
        """Should combine status1 + status2 + status3 + angles into full state."""
        mock_rs485.read_status_1.return_value = {
            "temperature_c": 35.0,
            "voltage_v": 46.1,
            "error_byte": 0,
        }
        mock_rs485.read_status_2.return_value = {
            "temperature_c": 35.0,
            "torque_current_a": 0.5,
            "speed_dps": 10.0,
            "encoder_position": 1234,
        }
        mock_rs485.read_status_3.return_value = {
            "phase_current_a": [0.1, 0.2, 0.3],
        }
        mock_rs485.read_multi_turn_angle.return_value = 360.0
        mock_rs485.read_single_turn_angle.return_value = 90.0

        result = await bridge_with_rs485.read_motor_state(motor_id=3)

        assert result["success"] is True
        assert result["temperature_c"] == 35.0
        assert result["voltage_v"] == 46.1
        assert result["torque_current_a"] == 0.5
        assert result["speed_dps"] == 10.0
        assert result["encoder_position"] == 1234
        assert result["multi_turn_deg"] == 360.0
        assert result["single_turn_deg"] == 90.0
        assert result["phase_current_a"] == [0.1, 0.2, 0.3]
        assert "error_flags" in result

    @pytest.mark.asyncio
    async def test_read_state_partial_failure(self, bridge_with_rs485, mock_rs485):
        """If status1 works but status3 fails, should still return partial data."""
        mock_rs485.read_status_1.return_value = {
            "temperature_c": 35.0,
            "voltage_v": 46.1,
            "error_byte": 0,
        }
        mock_rs485.read_status_2.return_value = {
            "temperature_c": 35.0,
            "torque_current_a": 0.5,
            "speed_dps": 10.0,
            "encoder_position": 1234,
        }
        mock_rs485.read_status_3.return_value = None  # failed
        mock_rs485.read_multi_turn_angle.return_value = 360.0
        mock_rs485.read_single_turn_angle.return_value = None  # failed

        result = await bridge_with_rs485.read_motor_state(motor_id=3)

        # Should still succeed with available data, missing fields get defaults
        assert result["success"] is True
        assert result["temperature_c"] == 35.0
        assert result["phase_current_a"] == [0.0, 0.0, 0.0]
        assert result["single_turn_deg"] == 0.0


# ---------------------------------------------------------------------------
# 4. WebSocket state polling via RS485
# ---------------------------------------------------------------------------


class TestRS485StatePolling:
    """Test the RS485 background polling thread for WebSocket state."""

    def test_rs485_polling_populates_latest_state(self, bridge_with_rs485, mock_rs485):
        """Background poller should populate _latest_motor_state."""
        mock_rs485.read_status_1.return_value = {
            "temperature_c": 35.0,
            "voltage_v": 46.1,
            "error_byte": 0,
        }
        mock_rs485.read_status_2.return_value = {
            "temperature_c": 35.0,
            "torque_current_a": 0.0,
            "speed_dps": 0.0,
            "encoder_position": 1000,
        }
        mock_rs485.read_status_3.return_value = {
            "phase_current_a": [0.0, 0.0, 0.0],
        }
        mock_rs485.read_multi_turn_angle.return_value = 0.0
        mock_rs485.read_single_turn_angle.return_value = 0.0

        # Start polling
        bridge_with_rs485.start_rs485_polling()

        # Wait a bit for the polling thread to run
        time.sleep(
            0.5
        )  # BLOCKING_SLEEP_OK: test synchronization — wait for polling thread — reviewed 2026-03-14

        state_json = bridge_with_rs485.get_latest_motor_state()
        assert state_json is not None

        state = json.loads(state_json)
        assert state["motor_id"] == 3
        assert state["temperature"] == 35.0
        assert state["voltage"] == 46.1

        # Stop polling
        bridge_with_rs485.stop_rs485_polling()

    def test_rs485_polling_stops_cleanly(self, bridge_with_rs485, mock_rs485):
        """Polling thread should stop when stop_rs485_polling is called."""
        mock_rs485.read_status_1.return_value = {
            "temperature_c": 35.0,
            "voltage_v": 46.1,
            "error_byte": 0,
        }
        mock_rs485.read_status_2.return_value = {
            "temperature_c": 35.0,
            "torque_current_a": 0.0,
            "speed_dps": 0.0,
            "encoder_position": 0,
        }

        bridge_with_rs485.start_rs485_polling()
        time.sleep(
            0.2
        )  # BLOCKING_SLEEP_OK: test synchronization — wait for poll thread startup — reviewed 2026-03-14
        bridge_with_rs485.stop_rs485_polling()
        time.sleep(
            0.2
        )  # BLOCKING_SLEEP_OK: test synchronization — wait for poll thread shutdown — reviewed 2026-03-14

        # Thread should have exited
        assert (
            bridge_with_rs485._rs485_poll_thread is None
            or not bridge_with_rs485._rs485_poll_thread.is_alive()
        )


# ---------------------------------------------------------------------------
# 5. No RS485 driver = original "ROS2 not available" error
# ---------------------------------------------------------------------------


class TestNoRS485NoROS2:
    """When neither ROS2 nor RS485 is available, original error is returned."""

    @pytest.mark.asyncio
    async def test_motor_command_no_transport(self):
        """Without RS485 or ROS2, motor_command returns error."""
        bridge = MotorConfigBridge()
        bridge._node = None

        result = await bridge.motor_command(motor_id=3, command_type=0, value=100.0)

        assert result["success"] is False
        assert "not available" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_read_motor_state_no_transport(self):
        """Without RS485 or ROS2, read_motor_state returns error."""
        bridge = MotorConfigBridge()
        bridge._node = None

        result = await bridge.read_motor_state(motor_id=3)

        assert result["success"] is False


# ---------------------------------------------------------------------------
# 6. Motor ID mismatch handling
# ---------------------------------------------------------------------------


class TestRS485MotorIdHandling:
    """Test that RS485 commands use the driver's configured motor_id."""

    @pytest.mark.asyncio
    async def test_ignores_api_motor_id_uses_driver_id(self, bridge_with_rs485, mock_rs485):
        """RS485 driver has a fixed motor_id. Bridge should use it.

        The API motor_id (from URL path) identifies which motor in the
        ROS2 graph. With RS485, there's only one motor on the serial line.
        The bridge should use the RS485 driver's motor_id.
        """
        mock_rs485.read_encoder.return_value = {
            "raw_value": 5000,
            "offset": 50,
            "original_value": 4950,
        }

        # API says motor 3, driver is also motor 3 — should work
        result = await bridge_with_rs485.read_encoder(motor_id=3)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_wrong_motor_id_returns_error(self, bridge_with_rs485, mock_rs485):
        """If API requests motor_id != driver's motor_id, return error."""
        mock_rs485.motor_id = 3

        result = await bridge_with_rs485.read_encoder(motor_id=1)

        assert result["success"] is False
        assert "motor" in result.get("error", "").lower()
