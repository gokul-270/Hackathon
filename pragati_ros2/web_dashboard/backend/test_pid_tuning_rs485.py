"""Tests for RS485 fallback integration in PIDTuningBridge.

Verifies that when ROS2 is unavailable but an RS485 driver is connected,
the PID bridge methods fall back to direct serial communication with the
motor, mapping field names between RS485 protocol and PID bridge format.

RS485 field mapping:
    angle_kp / angle_ki   <-->  position_kp / position_ki
    speed_kp / speed_ki   <-->  speed_kp / speed_ki  (same)
    current_kp / current_ki <--> torque_kp / torque_ki

RED phase: These tests should all FAIL before implementation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Mock ROS2 modules so we can import pid_tuning_api without ROS2 installed.
# Force ROS2_AVAILABLE = False to test the RS485 fallback path.
# ---------------------------------------------------------------------------
sys.modules.setdefault("rclpy", MagicMock())
sys.modules.setdefault("rclpy.node", MagicMock())
sys.modules.setdefault("rclpy.action", MagicMock())
sys.modules.setdefault("rclpy.callback_groups", MagicMock())
sys.modules.setdefault("rclpy.qos", MagicMock())
sys.modules.setdefault("motor_control_msgs", MagicMock())
sys.modules.setdefault("motor_control_msgs.srv", MagicMock())
sys.modules.setdefault("motor_control_msgs.action", MagicMock())
sys.modules.setdefault("std_msgs", MagicMock())
sys.modules.setdefault("std_msgs.msg", MagicMock())

# Ensure backend is importable
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import backend.pid_tuning_api as pid_api_module  # noqa: E402
from backend.pid_tuning_api import (  # noqa: E402
    PIDGains,
    PIDTuningBridge,
)
from backend.rs485_driver import RS485MotorDriver  # noqa: E402

# Force ROS2 unavailable for all tests in this file
pid_api_module.ROS2_AVAILABLE = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_rs485():
    """Create a mock RS485MotorDriver with all PID methods stubbed."""
    driver = MagicMock(spec=RS485MotorDriver)
    driver.port = "/dev/ttyUSB0"
    driver.motor_id = 3
    driver.connect.return_value = True
    driver._serial = MagicMock()
    driver._serial.is_open = True
    return driver


@pytest.fixture
def bridge():
    """Create a bare PIDTuningBridge (no RS485, no ROS2)."""
    return PIDTuningBridge()


@pytest.fixture
def bridge_with_rs485(mock_rs485):
    """Create a PIDTuningBridge with RS485 driver injected."""
    b = PIDTuningBridge()
    b.set_rs485_driver(mock_rs485)
    return b


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

# What the RS485 driver returns from read_pid()
RS485_PID_RESPONSE = {
    "angle_kp": 100,
    "angle_ki": 50,
    "speed_kp": 60,
    "speed_ki": 30,
    "current_kp": 80,
    "current_ki": 40,
}

# Expected mapped field names in the PID bridge response
EXPECTED_BRIDGE_GAINS = {
    "position_kp": 100,
    "position_ki": 50,
    "speed_kp": 60,
    "speed_ki": 30,
    "torque_kp": 80,
    "torque_ki": 40,
}

# PIDGains model for write tests
SAMPLE_PID_GAINS = PIDGains(
    position_kp=100,
    position_ki=50,
    speed_kp=60,
    speed_ki=30,
    torque_kp=80,
    torque_ki=40,
)

# What the bridge should send to RS485 write_pid_ram/write_pid_rom
EXPECTED_RS485_WRITE_GAINS = {
    "angle_kp": 100,
    "angle_ki": 50,
    "speed_kp": 60,
    "speed_ki": 30,
    "current_kp": 80,
    "current_ki": 40,
}


# ---------------------------------------------------------------------------
# 1. Setup / Initialization Tests
# ---------------------------------------------------------------------------


class TestPIDBridgeRS485Setup:
    """Test that PIDTuningBridge can accept and track RS485 driver."""

    def test_pid_bridge_has_rs485_driver_attribute(self, bridge):
        """PIDTuningBridge should have _rs485_driver attribute."""
        assert hasattr(bridge, "_rs485_driver")
        assert bridge._rs485_driver is None

    def test_pid_bridge_set_rs485_driver(self, mock_rs485):
        """set_rs485_driver() should store the driver."""
        bridge = PIDTuningBridge()
        bridge.set_rs485_driver(mock_rs485)
        assert bridge._rs485_driver is mock_rs485

    def test_pid_bridge_has_rs485_property(self, bridge_with_rs485):
        """has_rs485 property returns True when driver is set."""
        assert bridge_with_rs485.has_rs485 is True

    def test_pid_bridge_has_rs485_false_when_no_driver(self, bridge):
        """has_rs485 returns False when no driver is set."""
        assert bridge.has_rs485 is False


# ---------------------------------------------------------------------------
# 2. PID Read Tests
# ---------------------------------------------------------------------------


class TestRS485ReadPID:
    """Test read_pid falls back to RS485 when ROS2 unavailable."""

    @pytest.mark.asyncio
    async def test_rs485_read_pid_success(self, bridge_with_rs485, mock_rs485):
        """read_pid() should return mapped gains via RS485."""
        mock_rs485.read_pid.return_value = RS485_PID_RESPONSE.copy()

        result = await bridge_with_rs485.read_pid(motor_id=3)

        assert result["success"] is True
        assert "gains" in result
        gains = result["gains"]
        assert gains["position_kp"] == 100
        assert gains["position_ki"] == 50
        assert gains["speed_kp"] == 60
        assert gains["speed_ki"] == 30
        assert gains["torque_kp"] == 80
        assert gains["torque_ki"] == 40
        mock_rs485.read_pid.assert_called_once()

    @pytest.mark.asyncio
    async def test_rs485_read_pid_field_mapping(self, bridge_with_rs485, mock_rs485):
        """Verify exact field mapping: RS485 names -> bridge names.

        angle_kp=10 -> position_kp=10
        angle_ki=20 -> position_ki=20
        speed_kp=30 -> speed_kp=30
        speed_ki=40 -> speed_ki=40
        current_kp=50 -> torque_kp=50
        current_ki=60 -> torque_ki=60
        """
        mock_rs485.read_pid.return_value = {
            "angle_kp": 10,
            "angle_ki": 20,
            "speed_kp": 30,
            "speed_ki": 40,
            "current_kp": 50,
            "current_ki": 60,
        }

        result = await bridge_with_rs485.read_pid(motor_id=3)

        assert result["success"] is True
        gains = result["gains"]
        # angle -> position
        assert gains["position_kp"] == 10
        assert gains["position_ki"] == 20
        # speed -> speed (unchanged)
        assert gains["speed_kp"] == 30
        assert gains["speed_ki"] == 40
        # current -> torque
        assert gains["torque_kp"] == 50
        assert gains["torque_ki"] == 60

    @pytest.mark.asyncio
    async def test_rs485_read_pid_driver_error(self, bridge_with_rs485, mock_rs485):
        """RS485 driver exception should produce success=False."""
        mock_rs485.read_pid.side_effect = RuntimeError("Serial port disconnected")

        result = await bridge_with_rs485.read_pid(motor_id=3)

        assert result["success"] is False
        assert "error" in result
        assert len(result["error"]) > 0

    @pytest.mark.asyncio
    async def test_rs485_read_pid_returns_none(self, bridge_with_rs485, mock_rs485):
        """RS485 driver returning None should produce success=False."""
        mock_rs485.read_pid.return_value = None

        result = await bridge_with_rs485.read_pid(motor_id=3)

        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# 3. PID Write RAM Tests
# ---------------------------------------------------------------------------


class TestRS485WritePID:
    """Test write_pid falls back to RS485 when ROS2 unavailable."""

    @pytest.mark.asyncio
    async def test_rs485_write_pid_success(self, bridge_with_rs485, mock_rs485):
        """write_pid() should call RS485 write_pid_ram with mapped gains."""
        # write_pid_ram returns ack response
        mock_rs485.write_pid_ram.return_value = {
            "cmd": 0x31,
            "motor_id": 3,
        }
        # read-back for verification
        mock_rs485.read_pid.return_value = RS485_PID_RESPONSE.copy()

        result = await bridge_with_rs485.write_pid(motor_id=3, gains=SAMPLE_PID_GAINS)

        assert result["success"] is True
        mock_rs485.write_pid_ram.assert_called_once()

    @pytest.mark.asyncio
    async def test_rs485_write_pid_field_mapping(self, bridge_with_rs485, mock_rs485):
        """Verify reverse mapping: bridge names -> RS485 names.

        position_kp=100 -> angle_kp=100
        position_ki=50  -> angle_ki=50
        torque_kp=80    -> current_kp=80
        torque_ki=40    -> current_ki=40
        """
        mock_rs485.write_pid_ram.return_value = {
            "cmd": 0x31,
            "motor_id": 3,
        }
        mock_rs485.read_pid.return_value = RS485_PID_RESPONSE.copy()

        await bridge_with_rs485.write_pid(motor_id=3, gains=SAMPLE_PID_GAINS)

        call_args = mock_rs485.write_pid_ram.call_args
        # The gains dict passed to RS485 driver
        rs485_gains = call_args[0][0] if call_args[0] else call_args[1]
        assert rs485_gains["angle_kp"] == 100
        assert rs485_gains["angle_ki"] == 50
        assert rs485_gains["speed_kp"] == 60
        assert rs485_gains["speed_ki"] == 30
        assert rs485_gains["current_kp"] == 80
        assert rs485_gains["current_ki"] == 40

    @pytest.mark.asyncio
    async def test_rs485_write_pid_verification(self, bridge_with_rs485, mock_rs485):
        """After write, should read back gains and verify match."""
        mock_rs485.write_pid_ram.return_value = {
            "cmd": 0x31,
            "motor_id": 3,
        }
        mock_rs485.read_pid.return_value = RS485_PID_RESPONSE.copy()

        result = await bridge_with_rs485.write_pid(motor_id=3, gains=SAMPLE_PID_GAINS)

        assert result["success"] is True
        # Verification should have triggered a read-back
        mock_rs485.read_pid.assert_called()
        # Result should include verification status
        assert "verified" in result

    @pytest.mark.asyncio
    async def test_rs485_write_pid_driver_error(self, bridge_with_rs485, mock_rs485):
        """RS485 write failure should produce success=False."""
        mock_rs485.write_pid_ram.side_effect = RuntimeError("Write failed")

        result = await bridge_with_rs485.write_pid(motor_id=3, gains=SAMPLE_PID_GAINS)

        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# 4. PID Write ROM Tests
# ---------------------------------------------------------------------------


class TestRS485WritePIDToROM:
    """Test write_pid_to_rom falls back to RS485 when ROS2 unavailable."""

    @pytest.mark.asyncio
    async def test_rs485_write_pid_rom_success(self, bridge_with_rs485, mock_rs485):
        """write_pid_to_rom() should call RS485 write_pid_rom."""
        mock_rs485.write_pid_rom.return_value = {
            "cmd": 0x32,
            "motor_id": 3,
        }
        mock_rs485.read_pid.return_value = RS485_PID_RESPONSE.copy()

        result = await bridge_with_rs485.write_pid_to_rom(motor_id=3, gains=SAMPLE_PID_GAINS)

        assert result["success"] is True
        mock_rs485.write_pid_rom.assert_called_once()

    @pytest.mark.asyncio
    async def test_rs485_write_pid_rom_field_mapping(self, bridge_with_rs485, mock_rs485):
        """Verify reverse mapping for ROM write: bridge -> RS485 names."""
        mock_rs485.write_pid_rom.return_value = {
            "cmd": 0x32,
            "motor_id": 3,
        }
        mock_rs485.read_pid.return_value = RS485_PID_RESPONSE.copy()

        await bridge_with_rs485.write_pid_to_rom(motor_id=3, gains=SAMPLE_PID_GAINS)

        call_args = mock_rs485.write_pid_rom.call_args
        rs485_gains = call_args[0][0] if call_args[0] else call_args[1]
        assert rs485_gains["angle_kp"] == 100
        assert rs485_gains["angle_ki"] == 50
        assert rs485_gains["speed_kp"] == 60
        assert rs485_gains["speed_ki"] == 30
        assert rs485_gains["current_kp"] == 80
        assert rs485_gains["current_ki"] == 40

    @pytest.mark.asyncio
    async def test_rs485_write_pid_rom_driver_error(self, bridge_with_rs485, mock_rs485):
        """RS485 ROM write failure should produce success=False."""
        mock_rs485.write_pid_rom.side_effect = RuntimeError("ROM write failed")

        result = await bridge_with_rs485.write_pid_to_rom(motor_id=3, gains=SAMPLE_PID_GAINS)

        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# 5. Fallback Logic Tests
# ---------------------------------------------------------------------------


class TestPIDFallbackLogic:
    """Test transport selection: ROS2 preferred, RS485 fallback."""

    @pytest.mark.asyncio
    async def test_pid_read_prefers_ros2_over_rs485(self, mock_rs485):
        """When transport preference is 'ros2', read_pid should use ROS2, not RS485.

        We temporarily enable ROS2_AVAILABLE and mock the service call
        to verify RS485 driver is NOT invoked.
        """
        bridge = PIDTuningBridge()
        bridge.set_rs485_driver(mock_rs485)
        # Force ROS2 transport to test that it is used over RS485
        bridge.set_transport_preference("ros2")

        # Simulate ROS2 being available with a mock node
        mock_node = MagicMock()
        bridge._node = mock_node

        # Create a mock ROS2 service client
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.success = True
        mock_resp.position_kp = 10
        mock_resp.position_ki = 20
        mock_resp.speed_kp = 30
        mock_resp.speed_ki = 40
        mock_resp.torque_kp = 50
        mock_resp.torque_ki = 60
        bridge._read_pid_client = mock_client

        # Make service call succeed
        future = MagicMock()
        future.done.return_value = True
        future.result.return_value = mock_resp
        mock_client.wait_for_service.return_value = True
        mock_client.call_async.return_value = future

        with patch.object(pid_api_module, "ROS2_AVAILABLE", True):
            result = await bridge.read_pid(motor_id=3)

        # RS485 should NOT have been called
        mock_rs485.read_pid.assert_not_called()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_pid_read_falls_back_to_rs485(self, bridge_with_rs485, mock_rs485):
        """When ROS2 unavailable, read_pid should fall back to RS485."""
        mock_rs485.read_pid.return_value = RS485_PID_RESPONSE.copy()

        # ROS2_AVAILABLE is already False (module-level override)
        result = await bridge_with_rs485.read_pid(motor_id=3)

        assert result["success"] is True
        mock_rs485.read_pid.assert_called_once()

    @pytest.mark.asyncio
    async def test_pid_no_transport_returns_error(self, bridge):
        """When neither ROS2 nor RS485 available, return error."""
        # bridge has no RS485 driver and ROS2_AVAILABLE is False
        result = await bridge.read_pid(motor_id=3)

        assert result["success"] is False
        assert "error" in result
        assert len(result["error"]) > 0


# ---------------------------------------------------------------------------
# 6. Step Test Response Format Bug Fix (Task 0)
# ---------------------------------------------------------------------------


class TestStepTestResultFormat:
    """Test that _run_step_test_background wraps result in 'result' key."""

    @pytest.mark.asyncio
    async def test_step_test_result_wrapped_in_result_key(self):
        """Completed step test must nest data under 'result' key.

        The frontend reads pollResp.result, so the backend must store:
        {"status": "completed", "result": {<step_test_data>}}
        not {"status": "completed", **step_test_data}.
        """
        mock_result = {
            "success": True,
            "timestamps": [0.0, 0.1, 0.2],
            "positions": [100.0, 105.0, 110.0],
            "velocities": [50.0, 25.0, 0.0],
            "currents": [1.0, 0.5, 0.1],
            "setpoint": 110.0,
        }

        # Mock _bridge.start_step_test to return our data
        original_bridge = pid_api_module._bridge
        mock_bridge = AsyncMock()
        mock_bridge.start_step_test = AsyncMock(return_value=mock_result)
        pid_api_module._bridge = mock_bridge

        try:
            await pid_api_module._run_step_test_background(
                "test-123",
                3,
                10.0,
                5.0,
            )

            stored = pid_api_module._step_test_results["test-123"]
            assert stored["status"] == "completed"
            assert "result" in stored, "Result data must be nested under 'result' key"
            assert stored["result"]["timestamps"] == [0.0, 0.1, 0.2]
            assert stored["result"]["success"] is True
        finally:
            pid_api_module._bridge = original_bridge
            pid_api_module._step_test_results.pop("test-123", None)


# ---------------------------------------------------------------------------
# 7. RS485 Step Test (Task 1)
# ---------------------------------------------------------------------------


# Sample status2 response for mocking
_SAMPLE_STATUS2 = {
    "temperature_c": 35.0,
    "torque_current_a": 0.5,
    "speed_dps": 20.0,
    "encoder_position": 1234,
}


class TestRS485StepTest:
    """Test RS485-based step test execution."""

    @pytest.mark.asyncio
    async def test_rs485_step_test_basic_flow(
        self,
        bridge_with_rs485,
        mock_rs485,
    ):
        """RS485 step test: read angle, send command, poll, return data."""
        # Initial angle read returns 100.0 degrees
        # Subsequent reads during polling return simulated positions
        mock_rs485.read_multi_turn_angle.side_effect = [100.0] + [  # initial read
            102.0,
            105.0,
            108.0,
            110.0,
            110.0,
        ]  # polling
        mock_rs485.send_position_command.return_value = {
            "temperature_c": 30.0,
            "torque_current_a": 1.0,
            "speed_dps": 50.0,
            "encoder_position": 1000,
        }
        mock_rs485.read_status_2.return_value = _SAMPLE_STATUS2.copy()

        result = await bridge_with_rs485.start_step_test(
            3,
            10.0,
            0.5,
        )

        assert result["success"] is True
        assert "timestamps" in result
        assert "positions" in result
        assert "velocities" in result
        assert "currents" in result
        assert "setpoint" in result
        assert result["setpoint"] == 110.0  # 100 + 10
        # Position command should use centidegrees
        mock_rs485.send_position_command.assert_called_once_with(
            11000,
            max_speed_dps=0,
        )

    @pytest.mark.asyncio
    async def test_rs485_step_test_no_driver(self, bridge):
        """No RS485 driver and no ROS2 → error."""
        result = await bridge.start_step_test(3, 10.0, 5.0)

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_rs485_step_test_initial_angle_fails(
        self,
        bridge_with_rs485,
        mock_rs485,
    ):
        """read_multi_turn_angle returning None → error."""
        mock_rs485.read_multi_turn_angle.return_value = None

        result = await bridge_with_rs485.start_step_test(
            3,
            10.0,
            5.0,
        )

        assert result["success"] is False
        assert "initial" in result["error"].lower() or ("angle" in result["error"].lower())

    @pytest.mark.asyncio
    async def test_rs485_step_test_position_command_fails(
        self,
        bridge_with_rs485,
        mock_rs485,
    ):
        """send_position_command returning None → error."""
        mock_rs485.read_multi_turn_angle.return_value = 100.0
        mock_rs485.send_position_command.return_value = None

        result = await bridge_with_rs485.start_step_test(
            3,
            10.0,
            5.0,
        )

        assert result["success"] is False
        assert "command" in result["error"].lower() or "position" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rs485_step_test_temperature_abort(
        self,
        bridge_with_rs485,
        mock_rs485,
    ):
        """Temperature exceeding limit → motor_stop + error."""
        mock_rs485.read_multi_turn_angle.side_effect = [100.0] + [  # initial
            105.0,
            108.0,
        ]  # polling reads
        mock_rs485.send_position_command.return_value = _SAMPLE_STATUS2.copy()
        # First status2: safe temp, second: overtemp
        mock_rs485.read_status_2.side_effect = [
            {
                "temperature_c": 30.0,
                "torque_current_a": 0.5,
                "speed_dps": 20.0,
                "encoder_position": 1234,
            },
            {
                "temperature_c": 85.0,
                "torque_current_a": 0.5,
                "speed_dps": 20.0,
                "encoder_position": 1234,
            },
        ]

        result = await bridge_with_rs485.start_step_test(
            3,
            10.0,
            2.0,
        )

        assert result["success"] is False
        assert "temperature" in result["error"].lower()
        mock_rs485.motor_stop.assert_called()

    @pytest.mark.asyncio
    async def test_rs485_step_test_has_metrics(
        self,
        bridge_with_rs485,
        mock_rs485,
    ):
        """With enough data points, result should include metrics."""
        # 15+ angles transitioning from 100 to 110
        angles = [100.0] + [100.0 + (10.0 * min(i / 10.0, 1.0)) for i in range(16)]
        mock_rs485.read_multi_turn_angle.side_effect = angles
        mock_rs485.send_position_command.return_value = _SAMPLE_STATUS2.copy()
        mock_rs485.read_status_2.return_value = _SAMPLE_STATUS2.copy()

        # Mock compute_step_metrics since it may not be on sys.path
        fake_metrics = MagicMock()
        fake_metrics.rise_time = 0.3
        fake_metrics.settling_time = 0.8
        fake_metrics.overshoot_percent = 5.0
        fake_metrics.steady_state_error = 0.1
        fake_metrics.iae = 2.0
        fake_metrics.ise = 1.5
        fake_metrics.itse = 0.5
        fake_metrics.data_points = 16
        fake_metrics.confidence = "high"

        with patch.object(
            pid_api_module,
            "compute_step_metrics",
            return_value=fake_metrics,
        ):
            result = await bridge_with_rs485.start_step_test(
                3,
                10.0,
                1.5,
            )

        assert result["success"] is True
        assert "metrics" in result
        metrics = result["metrics"]
        assert "rise_time" in metrics
        assert "settling_time" in metrics
        assert "overshoot_percent" in metrics
        assert "steady_state_error" in metrics
        assert "iae" in metrics
        assert "ise" in metrics
        assert "itse" in metrics
        assert "data_points" in metrics
        assert "confidence" in metrics

    @pytest.mark.asyncio
    async def test_rs485_step_test_insufficient_data(
        self,
        bridge_with_rs485,
        mock_rs485,
    ):
        """All polling reads return None → insufficient data error."""
        mock_rs485.read_multi_turn_angle.side_effect = [100.0] + [  # initial read succeeds
            None
        ] * 20  # all polling reads fail
        mock_rs485.send_position_command.return_value = _SAMPLE_STATUS2.copy()
        mock_rs485.read_status_2.return_value = None

        result = await bridge_with_rs485.start_step_test(
            3,
            10.0,
            0.5,
        )

        assert result["success"] is False
        assert "insufficient" in result["error"].lower()


# ---------------------------------------------------------------------------
# 8. Benchmark Persistent Storage
# ---------------------------------------------------------------------------


class TestBenchmarkStorage:
    """Test persistent benchmark storage."""

    def test_save_benchmark_creates_file(self, tmp_path):
        """_save_benchmark creates a JSON file with correct structure."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = tmp_path / "benchmarks"
        try:
            result = {
                "success": True,
                "timestamps": [0.0, 0.1],
                "positions": [0.0, 10.0],
                "velocities": [0.0, 50.0],
                "currents": [0.0, 1.0],
                "setpoint": 10.0,
            }
            bid = mod._save_benchmark(3, 10.0, 5.0, result)
            assert bid is not None
            assert "motor3" in bid

            files = list((tmp_path / "benchmarks").glob("*.json"))
            assert len(files) == 1

            with open(files[0]) as f:
                data = json.load(f)
            assert data["motor_id"] == 3
            assert data["parameters"]["step_size_degrees"] == 10.0
            assert data["result"]["success"] is True
        finally:
            mod._PID_BENCHMARKS_DIR = original_dir

    def test_save_benchmark_returns_none_on_error(self):
        """_save_benchmark returns None if writing fails."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = Path("/nonexistent/readonly/path")
        try:
            bid = mod._save_benchmark(3, 10.0, 5.0, {"success": True})
            assert bid is None
        finally:
            mod._PID_BENCHMARKS_DIR = original_dir

    @pytest.mark.asyncio
    async def test_list_benchmarks_empty(self, tmp_path):
        """list_benchmarks returns empty list when no files exist."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = tmp_path / "benchmarks"
        try:
            resp = await mod.list_benchmarks(3)
            assert resp == {"benchmarks": []}
        finally:
            mod._PID_BENCHMARKS_DIR = original_dir

    @pytest.mark.asyncio
    async def test_list_benchmarks_returns_saved(self, tmp_path):
        """list_benchmarks returns previously saved benchmarks."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = tmp_path / "benchmarks"
        try:
            result = {
                "success": True,
                "timestamps": [0.0],
                "positions": [10.0],
                "velocities": [50.0],
                "currents": [1.0],
                "setpoint": 10.0,
            }
            bid = mod._save_benchmark(3, 10.0, 5.0, result)

            resp = await mod.list_benchmarks(3)
            assert len(resp["benchmarks"]) == 1
            assert resp["benchmarks"][0]["benchmark_id"] == bid
        finally:
            mod._PID_BENCHMARKS_DIR = original_dir

    @pytest.mark.asyncio
    async def test_get_benchmark_returns_data(self, tmp_path):
        """get_benchmark returns full benchmark data."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = tmp_path / "benchmarks"
        try:
            result = {
                "success": True,
                "timestamps": [0.0],
                "positions": [10.0],
                "velocities": [50.0],
                "currents": [1.0],
                "setpoint": 10.0,
            }
            bid = mod._save_benchmark(3, 10.0, 5.0, result)

            data = await mod.get_benchmark(3, bid)
            assert data["benchmark_id"] == bid
            assert data["result"]["setpoint"] == 10.0
        finally:
            mod._PID_BENCHMARKS_DIR = original_dir

    @pytest.mark.asyncio
    async def test_get_benchmark_404_for_missing(self, tmp_path):
        """get_benchmark raises 404 for nonexistent benchmark."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = tmp_path / "benchmarks"
        (tmp_path / "benchmarks").mkdir()
        try:
            with pytest.raises(HTTPException) as exc_info:
                await mod.get_benchmark(3, "nonexistent")
            assert exc_info.value.status_code == 404
        finally:
            mod._PID_BENCHMARKS_DIR = original_dir

    @pytest.mark.asyncio
    async def test_delete_benchmark(self, tmp_path):
        """delete_benchmark removes the file."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = tmp_path / "benchmarks"
        try:
            result = {
                "success": True,
                "timestamps": [0.0],
                "positions": [10.0],
                "velocities": [50.0],
                "currents": [1.0],
                "setpoint": 10.0,
            }
            bid = mod._save_benchmark(3, 10.0, 5.0, result)

            resp = await mod.delete_benchmark(3, bid)
            assert resp["deleted"] == bid

            # Verify file is gone
            files = list((tmp_path / "benchmarks").glob("*.json"))
            assert len(files) == 0
        finally:
            mod._PID_BENCHMARKS_DIR = original_dir

    @pytest.mark.asyncio
    async def test_background_step_test_saves_benchmark(self, tmp_path):
        """_run_step_test_background saves benchmark on success."""
        import backend.pid_tuning_api as mod

        original_dir = mod._PID_BENCHMARKS_DIR
        mod._PID_BENCHMARKS_DIR = tmp_path / "benchmarks"
        original_bridge = mod._bridge

        mock_bridge = MagicMock()
        mock_bridge.start_step_test = AsyncMock(
            return_value={
                "success": True,
                "timestamps": [0.0, 0.1],
                "positions": [0.0, 10.0],
                "velocities": [0.0, 50.0],
                "currents": [0.0, 1.0],
                "setpoint": 10.0,
            }
        )
        mod._bridge = mock_bridge
        try:
            await mod._run_step_test_background("test-bm", 3, 10.0, 5.0)
            stored = mod._step_test_results["test-bm"]
            assert stored["status"] == "completed"
            assert stored.get("benchmark_id") is not None

            # Verify file exists on disk
            files = list((tmp_path / "benchmarks").glob("*.json"))
            assert len(files) == 1
        finally:
            mod._bridge = original_bridge
            mod._PID_BENCHMARKS_DIR = original_dir
            mod._step_test_results.pop("test-bm", None)
