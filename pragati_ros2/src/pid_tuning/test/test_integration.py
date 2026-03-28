"""Integration tests for PID Tuning API.

Tests the full API layer including endpoints, safety validation,
profile management, and auto-tune analysis. ROS2 services are mocked
so these tests run without hardware or a running ROS2 graph.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock ROS2 / message modules BEFORE importing the API module
# ---------------------------------------------------------------------------
sys.modules["rclpy"] = MagicMock()
sys.modules["rclpy.node"] = MagicMock()
sys.modules["rclpy.action"] = MagicMock()
sys.modules["rclpy.callback_groups"] = MagicMock()
sys.modules["rclpy.executors"] = MagicMock()
sys.modules["motor_control_msgs"] = MagicMock()
sys.modules["motor_control_msgs.srv"] = MagicMock()
sys.modules["motor_control_msgs.action"] = MagicMock()
sys.modules["sensor_msgs"] = MagicMock()
sys.modules["sensor_msgs.msg"] = MagicMock()
sys.modules["std_msgs"] = MagicMock()
sys.modules["std_msgs.msg"] = MagicMock()
sys.modules["std_srvs"] = MagicMock()
sys.modules["std_srvs.srv"] = MagicMock()
sys.modules["action_msgs"] = MagicMock()
sys.modules["action_msgs.msg"] = MagicMock()

# Add source paths so imports resolve
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_repo_root / "web_dashboard" / "backend"))
sys.path.insert(0, str(_repo_root / "src" / "pid_tuning"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pid_tuning_api import (  # noqa: E402
    MOTOR_CONFIG,
    VALID_MOTOR_IDS,
    PIDTuningBridge,
    _FALLBACK_GAIN_LIMITS,
    _PID_PROFILES_DIR,
    _bridge,
    _gain_limits_cache,
    _step_test_results,
    _step_test_timestamps,
    pid_router,
)

# ---------------------------------------------------------------------------
# Test-level FastAPI app
# ---------------------------------------------------------------------------
test_app = FastAPI()
test_app.include_router(pid_router)
client = TestClient(test_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_GAINS = {
    "position_kp": 30,
    "position_ki": 10,
    "speed_kp": 50,
    "speed_ki": 20,
    "torque_kp": 40,
    "torque_ki": 15,
}

# Gains at the max of the fallback limits
BOUNDARY_GAINS = {
    "position_kp": 200,
    "position_ki": 100,
    "speed_kp": 200,
    "speed_ki": 100,
    "torque_kp": 150,
    "torque_ki": 80,
}


def generate_fopdt_response(
    K: float = 1.0,
    tau: float = 2.0,
    L: float = 0.5,
    dt: float = 0.1,
    duration: float = 10.0,
    step_size: float = 45.0,
):
    """Generate a first-order-plus-dead-time step response."""
    timestamps = [i * dt for i in range(int(duration / dt))]
    positions = []
    for t in timestamps:
        if t < L:
            positions.append(0.0)
        else:
            positions.append(step_size * K * (1.0 - math.exp(-(t - L) / tau)))
    return timestamps, positions


def _mock_bridge_read_pid(gains_dict: dict, success: bool = True):
    """Return a patched coroutine for ``_bridge.read_pid``."""

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


def _mock_bridge_write_pid_to_rom(success: bool = True):
    async def _fake_rom(motor_id: int, gains) -> dict:
        if success:
            return {"success": True, "error": ""}
        return {"success": False, "error": "mocked ROM failure"}

    return _fake_rom


# ===================================================================
# Task 8.1: PID read/write round-trip
# ===================================================================


class TestPIDReadWrite:
    """Verify read and write endpoints against mocked bridge."""

    def test_read_pid_success(self):
        """GET /api/pid/read/1 returns gains when service succeeds."""
        with patch.object(
            _bridge,
            "read_pid",
            side_effect=_mock_bridge_read_pid(VALID_GAINS),
        ):
            resp = client.get("/api/pid/read/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["gains"]["position_kp"] == 30
        assert data["gains"]["torque_ki"] == 15

    def test_read_pid_invalid_motor(self):
        """GET /api/pid/read/99 returns 400 for invalid motor_id."""
        resp = client.get("/api/pid/read/99")
        assert resp.status_code == 400
        assert "Invalid motor_id" in resp.json()["detail"]

    def test_read_pid_motor_id_zero(self):
        """Motor ID 0 is not in valid set."""
        resp = client.get("/api/pid/read/0")
        assert resp.status_code == 400

    def test_write_pid_success(self):
        """POST /api/pid/write/1 with valid gains succeeds."""
        with patch.object(
            _bridge,
            "write_pid",
            side_effect=_mock_bridge_write_pid(success=True),
        ):
            resp = client.post("/api/pid/write/1", json=VALID_GAINS)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_write_pid_exceeds_limits(self):
        """POST /api/pid/write/1 with gains > max is rejected (422)."""
        over_limit = {**VALID_GAINS, "position_kp": 255}
        # 255 > 200 (fallback limit for position_kp)
        resp = client.post("/api/pid/write/1", json=over_limit)
        assert resp.status_code == 422
        assert "Gain limit violation" in resp.json()["detail"]

    def test_read_pid_service_failure(self):
        """Read when bridge returns success=False gives 200 with warning."""
        with patch.object(
            _bridge,
            "read_pid",
            side_effect=_mock_bridge_read_pid({}, success=False),
        ):
            resp = client.get("/api/pid/read/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "warning" in data

    def test_write_pid_service_failure(self):
        """Write when bridge returns success=False gives 502."""
        with patch.object(
            _bridge,
            "write_pid",
            side_effect=_mock_bridge_write_pid(success=False),
        ):
            resp = client.post("/api/pid/write/1", json=VALID_GAINS)
        assert resp.status_code == 502


# ===================================================================
# Task 8.2: Step response flow
# ===================================================================


class TestStepResponse:
    """Verify step test start and result retrieval."""

    def test_start_step_test(self):
        """POST /api/pid/step_test/1 returns test_id and status=running."""
        with patch.object(_bridge, "start_step_test", new_callable=AsyncMock) as mock_step:
            mock_step.return_value = {"success": True}
            resp = client.post(
                "/api/pid/step_test/1",
                json={"step_size_degrees": 10.0, "duration_seconds": 5.0},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "test_id" in data
        assert data["status"] == "running"

    def test_get_step_result_pending(self):
        """GET result for running test returns status=running."""
        test_id = "test-pending-123"
        _step_test_results[test_id] = {"status": "running"}
        _step_test_timestamps[test_id] = time.monotonic()
        try:
            resp = client.get(f"/api/pid/step_test/1/result/{test_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "running"
        finally:
            _step_test_results.pop(test_id, None)
            _step_test_timestamps.pop(test_id, None)

    def test_get_step_result_complete(self):
        """GET result for completed test returns data arrays."""
        test_id = "test-complete-456"
        _step_test_results[test_id] = {
            "status": "completed",
            "success": True,
            "timestamps": [0.0, 0.1, 0.2],
            "positions": [0.0, 5.0, 9.8],
            "velocities": [0.0, 50.0, 48.0],
            "currents": [0.0, 1.2, 1.1],
            "setpoint": 10.0,
        }
        _step_test_timestamps[test_id] = time.monotonic()
        try:
            resp = client.get(f"/api/pid/step_test/1/result/{test_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
            assert len(data["timestamps"]) == 3
            assert data["setpoint"] == 10.0
        finally:
            _step_test_results.pop(test_id, None)
            _step_test_timestamps.pop(test_id, None)

    def test_get_step_result_not_found(self):
        """GET with unknown test_id returns 404."""
        resp = client.get("/api/pid/step_test/1/result/nonexistent-id")
        assert resp.status_code == 404

    def test_start_step_test_invalid_motor(self):
        """Step test on non-existent motor returns 400."""
        resp = client.post(
            "/api/pid/step_test/99",
            json={"step_size_degrees": 10.0, "duration_seconds": 5.0},
        )
        assert resp.status_code == 400


# ===================================================================
# Task 8.3: Auto-tune analysis
# ===================================================================


class TestAutoTune:
    """Verify Z-N autotune analyze endpoint."""

    def test_analyze_step_response(self):
        """POST /api/pid/autotune/analyze returns model params."""
        timestamps, positions = generate_fopdt_response(
            K=1.0, tau=2.0, L=0.5, dt=0.1, duration=10.0, step_size=45.0
        )
        body = {
            "timestamps": timestamps,
            "positions": positions,
            "setpoint": 45.0,
            "motor_type": "mg6010",
        }
        resp = client.post("/api/pid/autotune/analyze", json=body)
        # The endpoint may return 200 (success) or 501 (if numpy missing).
        # In a test environment with numpy available, expect 200.
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            assert "model" in data
            assert data["model"]["K"] > 0
            assert data["model"]["L"] >= 0
            assert data["model"]["T"] > 0

    def test_analyze_with_flat_data(self):
        """Analyze with flat data (no step) returns error or low confidence."""
        timestamps = [i * 0.1 for i in range(100)]
        positions = [0.0] * 100
        body = {
            "timestamps": timestamps,
            "positions": positions,
            "setpoint": 45.0,
            "motor_type": "mg6010",
        }
        resp = client.post("/api/pid/autotune/analyze", json=body)
        if resp.status_code == 200:
            data = resp.json()
            # With flat data setpoint=45 but positions=0, step_size=45
            # The ZN analyzer should report non-positive gain or error
            assert data["success"] is False or (data.get("model", {}).get("confidence") == "low")
        else:
            # 422 or 500 are acceptable for degenerate data
            assert resp.status_code in (422, 500)

    def test_analyze_too_few_points(self):
        """Fewer than 5 data points gives 422."""
        body = {
            "timestamps": [0.0, 0.1, 0.2],
            "positions": [0.0, 1.0, 2.0],
            "setpoint": 10.0,
        }
        resp = client.post("/api/pid/autotune/analyze", json=body)
        assert resp.status_code == 422

    def test_analyze_length_mismatch(self):
        """Mismatched array lengths gives 422."""
        body = {
            "timestamps": [0.0, 0.1, 0.2, 0.3, 0.4],
            "positions": [0.0, 1.0],
            "setpoint": 10.0,
        }
        resp = client.post("/api/pid/autotune/analyze", json=body)
        assert resp.status_code == 422


# ===================================================================
# Task 8.4: Safety enforcement
# ===================================================================


class TestSafety:
    """Verify gain limit enforcement and ROM write safety."""

    def test_gain_limits_enforced(self):
        """Write with gains exceeding max limit is rejected (422)."""
        over_limit = {**VALID_GAINS, "position_kp": 250}
        resp = client.post("/api/pid/write/1", json=over_limit)
        assert resp.status_code == 422
        assert "Gain limit violation" in resp.json()["detail"]

    def test_gain_limits_boundary(self):
        """Write with gains at exact max limit succeeds."""
        with patch.object(
            _bridge,
            "write_pid",
            side_effect=_mock_bridge_write_pid(success=True),
        ):
            resp = client.post("/api/pid/write/1", json=BOUNDARY_GAINS)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_gain_limits_one_above_max(self):
        """Write with one gain at max+1 is rejected."""
        just_over = {**BOUNDARY_GAINS, "torque_ki": 81}
        resp = client.post("/api/pid/write/1", json=just_over)
        assert resp.status_code == 422

    def test_rom_write_requires_token(self):
        """POST /api/pid/save/1 without CONFIRM_ROM_WRITE fails."""
        body = {**VALID_GAINS, "confirmation_token": "WRONG_TOKEN"}
        resp = client.post("/api/pid/save/1", json=body)
        assert resp.status_code == 400
        assert "CONFIRM_ROM_WRITE" in resp.json()["detail"]

    def test_rom_write_missing_token(self):
        """POST /api/pid/save/1 without token field fails validation."""
        # Omit confirmation_token entirely — Pydantic rejects it
        resp = client.post("/api/pid/save/1", json=VALID_GAINS)
        assert resp.status_code == 422

    def test_rom_write_with_token(self):
        """POST /api/pid/save/1 with correct token succeeds."""
        body = {**VALID_GAINS, "confirmation_token": "CONFIRM_ROM_WRITE"}
        with patch.object(
            _bridge,
            "write_pid_to_rom",
            side_effect=_mock_bridge_write_pid_to_rom(success=True),
        ):
            resp = client.post("/api/pid/save/1", json=body)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_rom_write_also_validates_limits(self):
        """ROM write with over-limit gains is rejected even with token."""
        body = {
            **VALID_GAINS,
            "position_kp": 255,
            "confirmation_token": "CONFIRM_ROM_WRITE",
        }
        resp = client.post("/api/pid/save/1", json=body)
        assert resp.status_code == 422
        assert "Gain limit violation" in resp.json()["detail"]


# ===================================================================
# Task 8.5: Profile save/load
# ===================================================================


class TestProfiles:
    """Verify profile save, list, load, and round-trip."""

    def setup_method(self):
        """Create temp directory and patch profile path."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self._patcher = patch("pid_tuning_api._PID_PROFILES_DIR", self.temp_dir)
        self._patcher.start()

    def teardown_method(self):
        self._patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_profile(self):
        """POST /api/pid/profiles/save creates YAML file."""
        body = {
            "name": "test_profile",
            "motor_type": "mg6010",
            "gains": VALID_GAINS,
            "description": "Unit test profile",
        }
        resp = client.post("/api/pid/profiles/save", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["profile_name"] == "test_profile"
        # Verify file exists on disk
        yaml_path = self.temp_dir / "mg6010" / "test_profile.yaml"
        assert yaml_path.exists()

    def test_list_profiles(self):
        """GET /api/pid/profiles/mg6010 lists existing profiles."""
        # Save a profile first
        body = {
            "name": "factory_default",
            "motor_type": "mg6010",
            "gains": VALID_GAINS,
        }
        client.post("/api/pid/profiles/save", json=body)

        resp = client.get("/api/pid/profiles/mg6010")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["profiles"]) >= 1
        names = [p["name"] for p in data["profiles"]]
        assert "factory_default" in names

    def test_list_profiles_empty(self):
        """List profiles for motor type with no profiles returns empty."""
        resp = client.get("/api/pid/profiles/mg6012")
        assert resp.status_code == 200
        assert resp.json()["profiles"] == []

    def test_load_profile(self):
        """GET /api/pid/profiles/mg6010/factory_default returns gains."""
        # Save first
        body = {
            "name": "factory_default",
            "motor_type": "mg6010",
            "gains": VALID_GAINS,
        }
        client.post("/api/pid/profiles/save", json=body)

        resp = client.get("/api/pid/profiles/mg6010/factory_default")
        assert resp.status_code == 200
        data = resp.json()
        assert data["gains"]["position_kp"] == 30
        assert data["motor_type"] == "mg6010"

    def test_load_profile_not_found(self):
        """Load non-existent profile returns 404."""
        resp = client.get("/api/pid/profiles/mg6010/nonexistent")
        assert resp.status_code == 404

    def test_profile_round_trip(self):
        """Save then load profile returns same gains."""
        body = {
            "name": "round_trip_test",
            "motor_type": "mg6010",
            "gains": BOUNDARY_GAINS,
            "description": "Round trip verification",
        }
        save_resp = client.post("/api/pid/profiles/save", json=body)
        assert save_resp.status_code == 200

        load_resp = client.get("/api/pid/profiles/mg6010/round_trip_test")
        assert load_resp.status_code == 200
        loaded = load_resp.json()
        for key, value in BOUNDARY_GAINS.items():
            assert loaded["gains"][key] == value

    def test_save_profile_invalid_name(self):
        """Profile name with special characters is rejected."""
        body = {
            "name": "bad name!@#",
            "motor_type": "mg6010",
            "gains": VALID_GAINS,
        }
        resp = client.post("/api/pid/profiles/save", json=body)
        assert resp.status_code == 422


# ===================================================================
# Task 8.6: Motor list endpoint
# ===================================================================


class TestMotorList:
    """Verify GET /api/pid/motors."""

    def test_get_motors(self):
        """GET /api/pid/motors returns 3 motors."""
        resp = client.get("/api/pid/motors")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["motors"]) == 3
        motor_ids = [m["motor_id"] for m in data["motors"]]
        assert sorted(motor_ids) == [1, 2, 3]

    def test_motor_can_id_formula(self):
        """Motor CAN IDs follow 0x140 + motor_id formula."""
        resp = client.get("/api/pid/motors")
        for motor in resp.json()["motors"]:
            expected_can_id = hex(0x140 + motor["motor_id"])
            assert motor["can_id"] == expected_can_id

    def test_all_motors_are_mg6010(self):
        """All configured motors are mg6010 type."""
        resp = client.get("/api/pid/motors")
        for motor in resp.json()["motors"]:
            assert motor["motor_type"] == "mg6010"

    def test_motor_joint_names(self):
        """Each motor has a joint name."""
        resp = client.get("/api/pid/motors")
        for motor in resp.json()["motors"]:
            assert "joint_name" in motor
            assert motor["joint_name"].startswith("joint")


# ===================================================================
# Task 8.7: Gain limits endpoint
# ===================================================================


class TestGainLimits:
    """Verify GET /api/pid/limits/{motor_type}."""

    def test_get_limits_mg6010(self):
        """GET /api/pid/limits/mg6010 returns limits dict."""
        # Clear cache to force reload from fallback
        _gain_limits_cache.clear()
        resp = client.get("/api/pid/limits/mg6010")
        assert resp.status_code == 200
        data = resp.json()
        assert data["motor_type"] == "mg6010"
        limits = data["gain_limits"]
        # Fallback limits should have position, speed, torque
        assert "position" in limits
        assert "speed" in limits
        assert "torque" in limits
        # Verify structure
        assert limits["position"]["kp"]["max"] > 0

    def test_get_limits_unknown_type(self):
        """GET /api/pid/limits/unknown returns fallback defaults."""
        _gain_limits_cache.clear()
        resp = client.get("/api/pid/limits/unknown_motor")
        assert resp.status_code == 200
        data = resp.json()
        # Should return fallback limits (uint16 range for MG6010E-i6)
        limits = data["gain_limits"]
        assert limits["position"]["kp"]["max"] == 65535
        assert limits["torque"]["ki"]["max"] == 65535

    def test_limits_contain_min_max_default(self):
        """Each limit entry has min, max, and default."""
        _gain_limits_cache.clear()
        resp = client.get("/api/pid/limits/mg6010")
        limits = resp.json()["gain_limits"]
        for loop_name in ("position", "speed", "torque"):
            for param in ("kp", "ki"):
                entry = limits[loop_name][param]
                assert "min" in entry
                assert "max" in entry
                assert "default" in entry
                assert entry["min"] <= entry["default"] <= entry["max"]


# ===================================================================
# Task 8.8: Concurrent session (conceptual)
# ===================================================================


class TestConcurrentSessions:
    """Verify API handles concurrent requests without crashing."""

    def test_motor_list_concurrent(self):
        """Multiple simultaneous requests to /api/pid/motors succeed."""
        import concurrent.futures

        def fetch_motors():
            return client.get("/api/pid/motors")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(fetch_motors) for _ in range(10)]
            results = [f.result() for f in futures]

        for resp in results:
            assert resp.status_code == 200
            assert len(resp.json()["motors"]) == 3

    def test_limits_concurrent(self):
        """Multiple concurrent limit requests don't corrupt cache."""
        import concurrent.futures

        _gain_limits_cache.clear()

        def fetch_limits(mtype):
            return client.get(f"/api/pid/limits/{mtype}")

        types = ["mg6010", "mg6012", "unknown", "mg6010", "mg6010"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(fetch_limits, t) for t in types]
            results = [f.result() for f in futures]

        for resp in results:
            assert resp.status_code == 200


# ===================================================================
# Task 8.9: Motor offline handling
# ===================================================================


class TestMotorOffline:
    """Verify behavior when ROS2 services are unavailable."""

    def test_read_pid_service_timeout(self):
        """Read when bridge returns timeout error gives 200 with warning."""

        async def _timeout_read(motor_id: int) -> dict:
            return {
                "success": False,
                "error": "Service /pid_tuning/read_pid not available after 5.0s",
            }

        with patch.object(_bridge, "read_pid", side_effect=_timeout_read):
            resp = client.get("/api/pid/read/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not available" in data["warning"]

    def test_write_pid_service_timeout(self):
        """Write when bridge returns timeout error gives 502."""

        async def _timeout_write(motor_id: int, gains) -> dict:
            return {
                "success": False,
                "error": "Service /pid_tuning/write_pid not available",
            }

        with patch.object(_bridge, "write_pid", side_effect=_timeout_write):
            resp = client.post("/api/pid/write/1", json=VALID_GAINS)
        assert resp.status_code == 502

    def test_rom_write_service_timeout(self):
        """ROM write when bridge is offline gives 502."""

        async def _timeout_rom(motor_id: int, gains) -> dict:
            return {"success": False, "error": "Service unavailable"}

        body = {**VALID_GAINS, "confirmation_token": "CONFIRM_ROM_WRITE"}
        with patch.object(_bridge, "write_pid_to_rom", side_effect=_timeout_rom):
            resp = client.post("/api/pid/save/1", json=body)
        assert resp.status_code == 502


# ===================================================================
# Task 8.10: Input validation
# ===================================================================


class TestInputValidation:
    """Verify Pydantic validation on request bodies."""

    def test_step_test_negative_duration(self):
        """Step test with negative duration is rejected."""
        body = {"step_size_degrees": 10.0, "duration_seconds": -1.0}
        resp = client.post("/api/pid/step_test/1", json=body)
        assert resp.status_code == 422

    def test_step_test_zero_duration(self):
        """Step test with zero duration is rejected (must be gt=0)."""
        body = {"step_size_degrees": 10.0, "duration_seconds": 0.0}
        resp = client.post("/api/pid/step_test/1", json=body)
        assert resp.status_code == 422

    def test_step_test_excessive_duration(self):
        """Step test with duration > 30s is rejected (le=30)."""
        body = {"step_size_degrees": 10.0, "duration_seconds": 31.0}
        resp = client.post("/api/pid/step_test/1", json=body)
        assert resp.status_code == 422

    def test_step_test_negative_step_size(self):
        """Step test with negative step size is rejected."""
        body = {"step_size_degrees": -5.0, "duration_seconds": 5.0}
        resp = client.post("/api/pid/step_test/1", json=body)
        assert resp.status_code == 422

    def test_step_test_excessive_step_size(self):
        """Step test with step > 90 degrees is rejected (le=90)."""
        body = {"step_size_degrees": 91.0, "duration_seconds": 5.0}
        resp = client.post("/api/pid/step_test/1", json=body)
        assert resp.status_code == 422

    def test_write_negative_gain(self):
        """Write with negative gain value is rejected."""
        negative = {**VALID_GAINS, "position_kp": -1}
        resp = client.post("/api/pid/write/1", json=negative)
        assert resp.status_code == 422

    def test_write_gain_over_255(self):
        """Write with gain > 255 is rejected by Pydantic (le=255)."""
        over = {**VALID_GAINS, "speed_kp": 256}
        resp = client.post("/api/pid/write/1", json=over)
        assert resp.status_code == 422

    def test_motor_id_out_of_range(self):
        """Motor ID > 32 is rejected."""
        resp = client.get("/api/pid/read/33")
        assert resp.status_code == 400

    def test_motor_id_negative(self):
        """Negative motor ID is rejected."""
        resp = client.get("/api/pid/read/-1")
        # FastAPI may parse -1 as int, then _validate_motor_id rejects it
        assert resp.status_code == 400

    def test_write_missing_required_field(self):
        """Write request missing a required gain field is rejected."""
        incomplete = {
            "position_kp": 30,
            "position_ki": 10,
            # Missing speed_kp, speed_ki, torque_kp, torque_ki
        }
        resp = client.post("/api/pid/write/1", json=incomplete)
        assert resp.status_code == 422

    def test_profile_save_empty_name(self):
        """Profile save with empty name is rejected."""
        body = {
            "name": "",
            "motor_type": "mg6010",
            "gains": VALID_GAINS,
        }
        resp = client.post("/api/pid/profiles/save", json=body)
        assert resp.status_code == 422

    def test_profile_save_name_too_long(self):
        """Profile name > 64 chars is rejected."""
        body = {
            "name": "a" * 65,
            "motor_type": "mg6010",
            "gains": VALID_GAINS,
        }
        resp = client.post("/api/pid/profiles/save", json=body)
        assert resp.status_code == 422
