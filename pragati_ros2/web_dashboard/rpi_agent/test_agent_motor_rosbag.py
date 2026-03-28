"""Tests for motor and rosbag endpoints in the Pragati RPi Agent.

Covers:
  - /motors/status, /motors/command, /motors/pid/*, /motors/calibrate/*,
    /motors/limits, /motors/step-response
  - /rosbag/list, /rosbag/record/*, /rosbag/download/*, /rosbag/play/*

Uses the same fixtures and patterns as test_agent.py.
All subprocess / filesystem calls are mocked — no ROS2 required.
"""

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_MODULE = "rpi_agent.agent"


@pytest.fixture
def _clean_env(monkeypatch):
    """Ensure PRAGATI_AGENT_API_KEY is unset unless a test sets it."""
    monkeypatch.delenv("PRAGATI_AGENT_API_KEY", raising=False)


@pytest.fixture
def app(_clean_env):
    """Import a fresh app instance with auth disabled (no env key)."""
    from rpi_agent.agent import create_app

    return create_app()


@pytest.fixture
def app_with_auth(monkeypatch):
    """App with API-key auth enabled."""
    monkeypatch.setenv("PRAGATI_AGENT_API_KEY", "test-secret-key")
    from rpi_agent.agent import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


AUTH_HEADER = {"X-API-Key": "test-secret-key"}


# ---------------------------------------------------------------------------
# Helpers for subprocess mock returns
# ---------------------------------------------------------------------------


def _mock_subprocess_ok(stdout="", stderr=""):
    """Return a MagicMock resembling a successful subprocess.run result."""
    return MagicMock(returncode=0, stdout=stdout, stderr=stderr)


def _mock_subprocess_fail(stdout="", stderr="error"):
    """Return a MagicMock resembling a failed subprocess.run result."""
    return MagicMock(returncode=1, stdout=stdout, stderr=stderr)


def _motor_state_stdout(
    motor_id=1,
    angle=45.0,
    speed=10.5,
    current=2.1,
    temp=35.0,
):
    """Produce fake ros2 service call output for motor state."""
    return (
        f"response:\n"
        f"  angle_deg: {angle}\n"
        f"  speed_dps: {speed}\n"
        f"  current_a: {current}\n"
        f"  temperature_c: {temp}\n"
    )


# ===================================================================
# Motor Status — GET /motors/status
# ===================================================================


class TestMotorStatus:
    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_status_all_motors(self, mock_run, client):
        """GET /motors/status returns a list of 6 motor states."""
        mock_run.return_value = _mock_subprocess_ok(stdout=_motor_state_stdout())
        resp = await client.get("/motors/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 6
        # Each motor should have the expected keys
        for motor in data:
            assert "motor_id" in motor
            assert "angle_deg" in motor
            assert "online" in motor

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_status_single_motor(self, mock_run, client):
        """GET /motors/status?motor_id=3 returns a single motor dict."""
        mock_run.return_value = _mock_subprocess_ok(
            stdout=_motor_state_stdout(motor_id=3, angle=90.0)
        )
        resp = await client.get("/motors/status", params={"motor_id": 3})
        assert resp.status_code == 200
        data = resp.json()
        # Single motor returns a dict, not a list
        assert isinstance(data, dict)
        assert data["motor_id"] == 3
        assert data["angle_deg"] == 90.0
        assert data["online"] is True

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_status_offline_motor(self, mock_run, client):
        """Subprocess failure -> motor reported offline."""
        mock_run.return_value = _mock_subprocess_fail()
        resp = await client.get("/motors/status", params={"motor_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["online"] is False
        assert data["angle_deg"] is None

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_status_ros2_unavailable(self, mock_run, client):
        """FileNotFoundError from subprocess -> motor reported offline.

        _ros2_motor_status catches FileNotFoundError per-motor and returns
        _offline_motor(), so the endpoint returns 200 with offline state.
        """
        mock_run.side_effect = FileNotFoundError("ros2 not found")
        resp = await client.get("/motors/status", params={"motor_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["online"] is False

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_status_timeout(self, mock_run, client):
        """TimeoutExpired from subprocess -> motor reported offline.

        _ros2_motor_status catches TimeoutExpired per-motor and returns
        _offline_motor(), so the endpoint returns 200 with offline state.
        """
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ros2", timeout=5)
        resp = await client.get("/motors/status", params={"motor_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["online"] is False


# ===================================================================
# Motor Command — POST /motors/command
# ===================================================================


class TestMotorCommand:
    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_command_stop_all(self, mock_run, client):
        """POST stop command to all motors."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post(
            "/motors/command",
            json={"mode": "stop", "params": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "stopped_motors" in data
        # Should have called subprocess for each of the 6 default motors
        assert mock_run.call_count == 6

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_command_single_motor(self, mock_run, client):
        """POST a position command to motor 2."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post(
            "/motors/command",
            json={
                "motor_id": 2,
                "mode": "position",
                "params": {"angle_deg": 90.0},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["motor_id"] == 2

    @pytest.mark.asyncio
    async def test_command_missing_motor_id_for_non_stop(self, client):
        """Non-stop command without motor_id -> 400."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = ValueError("motor_id required for non-stop commands")
            resp = await client.post(
                "/motors/command",
                json={"mode": "position", "params": {"angle_deg": 45.0}},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_command_subprocess_failure(self, mock_run, client):
        """Subprocess returncode != 0 -> 500."""
        mock_run.return_value = _mock_subprocess_fail(stderr="Motor command failed")
        resp = await client.post(
            "/motors/command",
            json={"motor_id": 1, "mode": "position", "params": {}},
        )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_command_requires_auth(self, auth_client):
        """POST /motors/command without key -> 401 when auth enabled."""
        resp = await auth_client.post(
            "/motors/command",
            json={"motor_id": 1, "mode": "stop", "params": {}},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_command_with_valid_auth(self, mock_run, auth_client):
        """POST with correct X-API-Key succeeds."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await auth_client.post(
            "/motors/command",
            json={"motor_id": 1, "mode": "stop", "params": {}},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200


# ===================================================================
# PID Endpoints — GET /motors/pid/read, POST /motors/pid/write
# ===================================================================


class TestPIDEndpoints:
    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_pid_read_success(self, mock_run, client):
        """GET /motors/pid/read?motor_id=1 returns PID gains."""
        mock_run.return_value = _mock_subprocess_ok(
            stdout=(
                "response:\n"
                "  angle_kp: 100\n"
                "  angle_ki: 10\n"
                "  speed_kp: 50\n"
                "  speed_ki: 5\n"
                "  current_kp: 30\n"
                "  current_ki: 3\n"
            )
        )
        resp = await client.get("/motors/pid/read", params={"motor_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["motor_id"] == 1
        assert data["angle_kp"] == 100
        assert data["angle_ki"] == 10
        assert data["speed_kp"] == 50
        assert data["speed_ki"] == 5
        assert data["current_kp"] == 30
        assert data["current_ki"] == 3

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_pid_read_timeout(self, mock_run, client):
        """Motor not responding -> 504."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ros2", timeout=5)
        resp = await client.get("/motors/pid/read", params={"motor_id": 1})
        assert resp.status_code == 504
        assert resp.json()["error"] == "motor_timeout"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_pid_read_failure(self, mock_run, client):
        """Subprocess returns non-zero -> 504 (RuntimeError path)."""
        mock_run.return_value = _mock_subprocess_fail()
        resp = await client.get("/motors/pid/read", params={"motor_id": 1})
        assert resp.status_code == 504

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_pid_write_success(self, mock_run, client):
        """POST /motors/pid/write with gains -> 200."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post(
            "/motors/pid/write",
            json={
                "motor_id": 1,
                "angle_kp": 100,
                "angle_ki": 10,
                "speed_kp": 50,
                "speed_ki": 5,
                "current_kp": 30,
                "current_ki": 3,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_pid_write_timeout(self, mock_run, client):
        """Motor not responding on write -> 504."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ros2", timeout=5)
        resp = await client.post(
            "/motors/pid/write",
            json={
                "motor_id": 1,
                "angle_kp": 100,
                "angle_ki": 10,
                "speed_kp": 50,
                "speed_ki": 5,
                "current_kp": 30,
                "current_ki": 3,
            },
        )
        assert resp.status_code == 504

    @pytest.mark.asyncio
    async def test_pid_write_requires_auth(self, auth_client):
        """POST /motors/pid/write without key -> 401."""
        resp = await auth_client.post(
            "/motors/pid/write",
            json={
                "motor_id": 1,
                "angle_kp": 100,
                "angle_ki": 10,
                "speed_kp": 50,
                "speed_ki": 5,
                "current_kp": 30,
                "current_ki": 3,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_pid_write_with_valid_auth(self, mock_run, auth_client):
        """POST with correct X-API-Key succeeds."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await auth_client.post(
            "/motors/pid/write",
            json={
                "motor_id": 1,
                "angle_kp": 100,
                "angle_ki": 10,
                "speed_kp": 50,
                "speed_ki": 5,
                "current_kp": 30,
                "current_ki": 3,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200


# ===================================================================
# Calibrate Endpoints — GET /motors/calibrate/read,
#                        POST /motors/calibrate/zero
# ===================================================================


class TestCalibrateEndpoints:
    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_calibrate_read_success(self, mock_run, client):
        """GET /motors/calibrate/read?motor_id=1 returns encoder data."""
        mock_run.return_value = _mock_subprocess_ok(
            stdout=(
                "response:\n"
                "  raw_position: 16384\n"
                "  angle_deg: 90.0\n"
                "  offset: 0\n"
            )
        )
        resp = await client.get("/motors/calibrate/read", params={"motor_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["motor_id"] == 1
        assert data["raw_position"] == 16384
        assert data["angle_deg"] == 90.0
        assert data["offset"] == 0

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_calibrate_read_timeout(self, mock_run, client):
        """Motor timeout -> 504."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ros2", timeout=5)
        resp = await client.get("/motors/calibrate/read", params={"motor_id": 1})
        assert resp.status_code == 504
        assert resp.json()["error"] == "motor_timeout"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_calibrate_read_failure(self, mock_run, client):
        """Subprocess non-zero return -> 500."""
        mock_run.return_value = _mock_subprocess_fail()
        resp = await client.get("/motors/calibrate/read", params={"motor_id": 1})
        assert resp.status_code == 500

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_calibrate_zero_success(self, mock_run, client):
        """POST /motors/calibrate/zero -> 200 with success."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post(
            "/motors/calibrate/zero",
            json={"motor_id": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["motor_id"] == 1

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_calibrate_zero_timeout(self, mock_run, client):
        """Motor timeout on zero -> 504."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ros2", timeout=5)
        resp = await client.post(
            "/motors/calibrate/zero",
            json={"motor_id": 1},
        )
        assert resp.status_code == 504

    @pytest.mark.asyncio
    async def test_calibrate_zero_requires_auth(self, auth_client):
        """POST /motors/calibrate/zero without key -> 401."""
        resp = await auth_client.post(
            "/motors/calibrate/zero",
            json={"motor_id": 1},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_calibrate_zero_with_valid_auth(self, mock_run, auth_client):
        """POST with correct X-API-Key succeeds."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await auth_client.post(
            "/motors/calibrate/zero",
            json={"motor_id": 1},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200


# ===================================================================
# Motor Limits — GET /motors/limits, PUT /motors/limits
# ===================================================================


class TestMotorLimits:
    @pytest.mark.asyncio
    async def test_limits_read_defaults(self, client):
        """GET /motors/limits?motor_id=1 returns default limits."""
        with patch(f"{AGENT_MODULE}.os.path.isfile", return_value=False):
            resp = await client.get("/motors/limits", params={"motor_id": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["motor_id"] == 1
        assert data["min_angle_deg"] == -180.0
        assert data["max_angle_deg"] == 180.0
        assert data["max_speed_dps"] == 360.0
        assert data["max_current_a"] == 10.0

    @pytest.mark.asyncio
    async def test_limits_read_from_file(self, client):
        """GET /motors/limits reads overrides from motor_limits.json."""
        custom_limits = {
            "2": {
                "min_angle_deg": -90.0,
                "max_angle_deg": 90.0,
                "max_speed_dps": 180.0,
                "max_current_a": 5.0,
            }
        }
        mock_open_data = json.dumps(custom_limits)

        with (
            patch(f"{AGENT_MODULE}.os.path.isfile", return_value=True),
            patch(
                "builtins.open",
                new_callable=lambda: lambda *a, **k: __import__("io").StringIO(
                    mock_open_data
                ),
            ),
        ):
            resp = await client.get("/motors/limits", params={"motor_id": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["min_angle_deg"] == -90.0
        assert data["max_angle_deg"] == 90.0

    @pytest.mark.asyncio
    async def test_limits_write_success(self, client):
        """PUT /motors/limits writes limits to file."""
        with (
            patch(f"{AGENT_MODULE}.os.path.isfile", return_value=False),
            patch(f"{AGENT_MODULE}.os.makedirs"),
            patch("builtins.open", MagicMock()),
            patch(f"{AGENT_MODULE}.json.dump"),
        ):
            resp = await client.put(
                "/motors/limits",
                json={
                    "motor_id": 1,
                    "min_angle_deg": -90.0,
                    "max_angle_deg": 90.0,
                    "max_speed_dps": 180.0,
                    "max_current_a": 5.0,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["motor_id"] == 1

    @pytest.mark.asyncio
    async def test_limits_write_requires_auth(self, auth_client):
        """PUT /motors/limits without key -> 401."""
        resp = await auth_client.put(
            "/motors/limits",
            json={
                "motor_id": 1,
                "min_angle_deg": -90.0,
                "max_angle_deg": 90.0,
                "max_speed_dps": 180.0,
                "max_current_a": 5.0,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_limits_write_with_valid_auth(self, auth_client):
        """PUT with correct X-API-Key succeeds."""
        with (
            patch(f"{AGENT_MODULE}.os.path.isfile", return_value=False),
            patch(f"{AGENT_MODULE}.os.makedirs"),
            patch("builtins.open", MagicMock()),
            patch(f"{AGENT_MODULE}.json.dump"),
        ):
            resp = await auth_client.put(
                "/motors/limits",
                json={
                    "motor_id": 1,
                    "min_angle_deg": -90.0,
                    "max_angle_deg": 90.0,
                    "max_speed_dps": 180.0,
                    "max_current_a": 5.0,
                },
                headers=AUTH_HEADER,
            )
        assert resp.status_code == 200


# ===================================================================
# Step Response — POST /motors/step-response
# ===================================================================


class TestStepResponse:
    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_step_response_success(self, mock_run, client):
        """POST /motors/step-response -> 200 with step data."""
        step_data = json.dumps(
            {
                "samples": [{"t": 0.0, "angle": 0.0}, {"t": 0.1, "angle": 45.0}],
                "rise_time_s": 0.5,
                "settling_time_s": 1.2,
                "overshoot_percent": 5.0,
                "steady_state_error_deg": 0.3,
            }
        )
        mock_run.return_value = _mock_subprocess_ok(stdout=f"response:\n{step_data}")
        resp = await client.post(
            "/motors/step-response",
            json={
                "motor_id": 1,
                "target_angle_deg": 90.0,
                "duration_s": 5.0,
                "sample_rate_hz": 50,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["motor_id"] == 1
        assert "rise_time_s" in data

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_step_response_fallback(self, mock_run, client):
        """Non-JSON output returns fallback structure."""
        mock_run.return_value = _mock_subprocess_ok(stdout="some raw text without JSON")
        resp = await client.post(
            "/motors/step-response",
            json={
                "motor_id": 1,
                "target_angle_deg": 90.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["motor_id"] == 1
        assert data["samples"] == []
        assert "raw_output" in data

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_step_response_timeout(self, mock_run, client):
        """Step response timeout -> 504."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ros2", timeout=30)
        resp = await client.post(
            "/motors/step-response",
            json={
                "motor_id": 1,
                "target_angle_deg": 90.0,
            },
        )
        assert resp.status_code == 504
        assert resp.json()["error"] == "motor_timeout"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_step_response_failure(self, mock_run, client):
        """Subprocess non-zero return -> 500."""
        mock_run.return_value = _mock_subprocess_fail(stderr="Step test failed")
        resp = await client.post(
            "/motors/step-response",
            json={
                "motor_id": 1,
                "target_angle_deg": 90.0,
            },
        )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_step_response_requires_auth(self, auth_client):
        """POST /motors/step-response without key -> 401."""
        resp = await auth_client.post(
            "/motors/step-response",
            json={
                "motor_id": 1,
                "target_angle_deg": 90.0,
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_step_response_with_valid_auth(self, mock_run, auth_client):
        """POST with correct X-API-Key succeeds."""
        mock_run.return_value = _mock_subprocess_ok(stdout="no json here")
        resp = await auth_client.post(
            "/motors/step-response",
            json={
                "motor_id": 1,
                "target_angle_deg": 90.0,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200


# ===================================================================
# Rosbag List — GET /rosbag/list
# ===================================================================


class TestRosbagList:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        """No bag directory -> empty list."""
        with patch(f"{AGENT_MODULE}.os.path.isdir", return_value=False):
            resp = await client.get("/rosbag/list")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_with_bags(self, client):
        """Bag directory with entries -> list with metadata."""

        def _isdir(path):
            # _BAG_DIR exists, and each bag subdir exists
            return True

        def _isfile(path):
            # metadata.yaml exists inside each bag
            return path.endswith("metadata.yaml")

        def _listdir(path):
            return ["bag_2025_01", "bag_2025_02"]

        def _walk(path):
            yield path, [], ["metadata.yaml", "data.mcap"]

        def _getsize(path):
            return 1024

        def _getctime(path):
            return 1700000000.0

        with (
            patch(f"{AGENT_MODULE}.os.path.isdir", side_effect=_isdir),
            patch(f"{AGENT_MODULE}.os.path.isfile", side_effect=_isfile),
            patch(f"{AGENT_MODULE}.os.listdir", side_effect=_listdir),
            patch(f"{AGENT_MODULE}.os.walk", side_effect=_walk),
            patch(f"{AGENT_MODULE}.os.path.getsize", side_effect=_getsize),
            patch(f"{AGENT_MODULE}.os.path.getctime", side_effect=_getctime),
            patch(f"{AGENT_MODULE}.os.path.join", side_effect=os.path.join),
            patch(f"{AGENT_MODULE}.subprocess.run") as mock_run,
        ):
            # ros2 bag info returns empty (no detailed metadata)
            mock_run.return_value = _mock_subprocess_fail()
            resp = await client.get("/rosbag/list")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "bag_2025_02"  # sorted reverse
        for bag in data:
            assert "name" in bag
            assert "size_bytes" in bag

    @pytest.mark.asyncio
    async def test_list_with_ros2_bag_info(self, client):
        """ros2 bag info output is parsed for duration/messages."""

        def _isdir(path):
            return True

        def _isfile(path):
            return path.endswith("metadata.yaml")

        def _listdir(path):
            return ["test_bag"]

        def _walk(path):
            yield path, [], ["metadata.yaml", "data.mcap"]

        def _getsize(path):
            return 2048

        def _getctime(path):
            return 1700000000.0

        bag_info_output = (
            "Duration: 10.5s\n"
            "Topic count: 4\n"
            "Messages: 1200\n"
            "Start: 2025-01-01T00:00:00\n"
        )

        with (
            patch(f"{AGENT_MODULE}.os.path.isdir", side_effect=_isdir),
            patch(f"{AGENT_MODULE}.os.path.isfile", side_effect=_isfile),
            patch(f"{AGENT_MODULE}.os.listdir", side_effect=_listdir),
            patch(f"{AGENT_MODULE}.os.walk", side_effect=_walk),
            patch(f"{AGENT_MODULE}.os.path.getsize", side_effect=_getsize),
            patch(f"{AGENT_MODULE}.os.path.getctime", side_effect=_getctime),
            patch(f"{AGENT_MODULE}.os.path.join", side_effect=os.path.join),
            patch(f"{AGENT_MODULE}.subprocess.run") as mock_run,
        ):
            mock_run.return_value = _mock_subprocess_ok(stdout=bag_info_output)
            resp = await client.get("/rosbag/list")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        bag = data[0]
        assert bag["duration_s"] == 10.5
        assert bag["topic_count"] == 4
        assert bag["message_count"] == 1200


# ===================================================================
# Rosbag Record — POST /rosbag/record/start, stop, GET status
# ===================================================================


class TestRosbagRecord:
    @pytest.mark.asyncio
    async def test_record_start_success(self, client):
        """POST /rosbag/record/start -> 200 with active=True."""
        import rpi_agent.agent as agent_mod

        # Reset module-level state
        agent_mod._recording_process = None

        with (
            patch(f"{AGENT_MODULE}.os.makedirs"),
            patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen,
        ):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            resp = await client.post(
                "/rosbag/record/start",
                json={"profile": "standard"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["profile"] == "standard"

        # Clean up module state
        agent_mod._recording_process = None
        agent_mod._recording_start_time = None
        agent_mod._recording_profile = None

    @pytest.mark.asyncio
    async def test_record_start_conflict(self, client):
        """409 when recording is already active."""
        import rpi_agent.agent as agent_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        agent_mod._recording_process = mock_proc

        try:
            resp = await client.post(
                "/rosbag/record/start",
                json={"profile": "minimal"},
            )
            assert resp.status_code == 409
            assert resp.json()["error"] == "recording_active"
        finally:
            agent_mod._recording_process = None

    @pytest.mark.asyncio
    async def test_record_stop_success(self, client):
        """POST /rosbag/record/stop -> 200."""
        import rpi_agent.agent as agent_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.wait.return_value = 0
        agent_mod._recording_process = mock_proc
        agent_mod._recording_start_time = 1000.0
        agent_mod._recording_profile = "standard"

        try:
            resp = await client.post("/rosbag/record/stop")
            assert resp.status_code == 200
            assert resp.json()["active"] is False
        finally:
            agent_mod._recording_process = None
            agent_mod._recording_start_time = None
            agent_mod._recording_profile = None

    @pytest.mark.asyncio
    async def test_record_stop_not_recording(self, client):
        """409 when not recording."""
        import rpi_agent.agent as agent_mod

        agent_mod._recording_process = None

        resp = await client.post("/rosbag/record/stop")
        assert resp.status_code == 409
        assert resp.json()["error"] == "not_recording"

    @pytest.mark.asyncio
    async def test_record_status_idle(self, client):
        """GET /rosbag/record/status when idle."""
        import rpi_agent.agent as agent_mod

        agent_mod._recording_process = None

        with patch(f"{AGENT_MODULE}.psutil.disk_usage") as mock_disk:
            mock_disk.return_value = MagicMock(free=10_000_000_000)
            resp = await client.get("/rosbag/record/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False
        assert data["profile"] is None
        assert data["duration_s"] is None

    @pytest.mark.asyncio
    async def test_record_status_active(self, client):
        """GET /rosbag/record/status when recording."""
        import rpi_agent.agent as agent_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        agent_mod._recording_process = mock_proc
        agent_mod._recording_start_time = 1000.0
        agent_mod._recording_profile = "debug"

        try:
            with (
                patch(f"{AGENT_MODULE}.psutil.disk_usage") as mock_disk,
                patch(f"{AGENT_MODULE}.time.time", return_value=1010.0),
            ):
                mock_disk.return_value = MagicMock(free=5_000_000_000)
                resp = await client.get("/rosbag/record/status")

            assert resp.status_code == 200
            data = resp.json()
            assert data["active"] is True
            assert data["profile"] == "debug"
            assert data["duration_s"] == 10.0
        finally:
            agent_mod._recording_process = None
            agent_mod._recording_start_time = None
            agent_mod._recording_profile = None

    @pytest.mark.asyncio
    async def test_record_start_requires_auth(self, auth_client):
        """POST /rosbag/record/start without key -> 401."""
        resp = await auth_client.post(
            "/rosbag/record/start",
            json={"profile": "standard"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_record_stop_requires_auth(self, auth_client):
        """POST /rosbag/record/stop without key -> 401."""
        resp = await auth_client.post("/rosbag/record/stop")
        assert resp.status_code == 401


# ===================================================================
# Rosbag Download — GET /rosbag/download/{name}
# ===================================================================


class TestRosbagDownload:
    @pytest.mark.asyncio
    async def test_download_path_traversal_dotdot(self, client):
        """Path traversal with .. in bag name is blocked (400)."""
        resp = await client.get("/rosbag/download/..secret")
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_path"

    @pytest.mark.asyncio
    async def test_download_path_traversal_slash(self, client):
        """Path with / is rejected by FastAPI router (404) or by check (400).

        FastAPI {bag_name} path param does not capture '/', so the URL
        with encoded slash ends up as a 404 from routing. This is safe.
        """
        resp = await client.get("/rosbag/download/foo%2Fbar")
        # Router returns 404 because {bag_name} doesn't match slashes
        assert resp.status_code in (400, 404)

    @pytest.mark.asyncio
    async def test_download_path_traversal_backslash(self, client):
        """Path with backslash is blocked (400)."""
        resp = await client.get("/rosbag/download/foo\\bar")
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_path"

    @pytest.mark.asyncio
    async def test_download_bag_not_found(self, client):
        """Non-existent bag -> 404."""
        with patch(f"{AGENT_MODULE}.os.path.isdir", return_value=False):
            resp = await client.get("/rosbag/download/nonexistent_bag")
        assert resp.status_code == 404
        assert resp.json()["error"] == "bag_not_found"

    @pytest.mark.asyncio
    async def test_download_success(self, client, tmp_path):
        """Valid bag -> streaming tar.gz response."""
        # Create a temp bag directory
        bag_dir = tmp_path / "test_bag"
        bag_dir.mkdir()
        (bag_dir / "metadata.yaml").write_text("rosbag2_bagfile_information:")
        (bag_dir / "data.mcap").write_bytes(b"\x00" * 100)

        with patch(f"{AGENT_MODULE}._BAG_DIR", str(tmp_path)):
            resp = await client.get("/rosbag/download/test_bag")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/gzip"
        assert "test_bag.tar.gz" in resp.headers.get("content-disposition", "")
        # Response body should be non-empty gzip data
        assert len(resp.content) > 0


# ===================================================================
# Rosbag Play — POST /rosbag/play/start, POST /rosbag/play/stop
# ===================================================================


class TestRosbagPlay:
    @pytest.mark.asyncio
    async def test_play_start_success(self, client, tmp_path):
        """POST /rosbag/play/start -> 200."""
        import rpi_agent.agent as agent_mod

        agent_mod._recording_process = None
        agent_mod._playback_process = None

        bag_dir = tmp_path / "my_bag"
        bag_dir.mkdir()

        with (
            patch(f"{AGENT_MODULE}._BAG_DIR", str(tmp_path)),
            patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen,
        ):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            resp = await client.post(
                "/rosbag/play/start",
                json={"bag_name": "my_bag"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["playing"] is True
        assert data["bag_name"] == "my_bag"

        # Clean up
        agent_mod._playback_process = None

    @pytest.mark.asyncio
    async def test_play_start_conflict_recording(self, client):
        """409 when recording is active."""
        import rpi_agent.agent as agent_mod

        mock_rec = MagicMock()
        mock_rec.poll.return_value = None
        agent_mod._recording_process = mock_rec

        try:
            resp = await client.post(
                "/rosbag/play/start",
                json={"bag_name": "some_bag"},
            )
            assert resp.status_code == 409
            assert resp.json()["error"] == "recording_active"
        finally:
            agent_mod._recording_process = None

    @pytest.mark.asyncio
    async def test_play_start_conflict_playback(self, client):
        """409 when playback is already active."""
        import rpi_agent.agent as agent_mod

        agent_mod._recording_process = None
        mock_play = MagicMock()
        mock_play.poll.return_value = None
        agent_mod._playback_process = mock_play

        try:
            resp = await client.post(
                "/rosbag/play/start",
                json={"bag_name": "some_bag"},
            )
            assert resp.status_code == 409
            assert resp.json()["error"] == "playback_active"
        finally:
            agent_mod._playback_process = None

    @pytest.mark.asyncio
    async def test_play_start_bag_not_found(self, client):
        """404 when bag directory doesn't exist."""
        import rpi_agent.agent as agent_mod

        agent_mod._recording_process = None
        agent_mod._playback_process = None

        with patch(f"{AGENT_MODULE}.os.path.isdir", return_value=False):
            resp = await client.post(
                "/rosbag/play/start",
                json={"bag_name": "nonexistent"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_play_stop_success(self, client):
        """POST /rosbag/play/stop -> 200."""
        import rpi_agent.agent as agent_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        agent_mod._playback_process = mock_proc

        try:
            resp = await client.post("/rosbag/play/stop")
            assert resp.status_code == 200
            assert resp.json()["playing"] is False
        finally:
            agent_mod._playback_process = None

    @pytest.mark.asyncio
    async def test_play_stop_when_idle(self, client):
        """Stop when not playing -> still 200 (idempotent)."""
        import rpi_agent.agent as agent_mod

        agent_mod._playback_process = None
        resp = await client.post("/rosbag/play/stop")
        assert resp.status_code == 200
        assert resp.json()["playing"] is False

    @pytest.mark.asyncio
    async def test_play_start_requires_auth(self, auth_client):
        """POST /rosbag/play/start without key -> 401."""
        resp = await auth_client.post(
            "/rosbag/play/start",
            json={"bag_name": "test"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_play_stop_requires_auth(self, auth_client):
        """POST /rosbag/play/stop without key -> 401."""
        resp = await auth_client.post("/rosbag/play/stop")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_play_start_with_valid_auth(self, auth_client, tmp_path):
        """POST with correct X-API-Key succeeds."""
        import rpi_agent.agent as agent_mod

        agent_mod._recording_process = None
        agent_mod._playback_process = None

        bag_dir = tmp_path / "auth_bag"
        bag_dir.mkdir()

        with (
            patch(f"{AGENT_MODULE}._BAG_DIR", str(tmp_path)),
            patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen,
        ):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            resp = await auth_client.post(
                "/rosbag/play/start",
                json={"bag_name": "auth_bag"},
                headers=AUTH_HEADER,
            )
        assert resp.status_code == 200

        # Clean up
        agent_mod._playback_process = None
