"""Unit tests for entity_motor_router — entity-scoped motor API routes.

Tests cover:
- Motor status: GET /{id}/motors/status (local + remote)
- Motor command: POST /{id}/motors/command (local + remote)
- PID read/write: GET/POST /{id}/motors/pid/* (local + remote)
- Calibrate: GET/POST /{id}/motors/calibrate/* (local + remote)
- Motor limits: GET/PUT /{id}/motors/limits (local + remote)
- Step response: POST /{id}/motors/step-response (local + remote)
- Errors: 404, 502, 503

All httpx calls are mocked — no real network needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity
from backend.entity_motor_router import entity_motor_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "backend.entity_motor_router"


def _make_app(
    entities: dict[str, Entity] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal FastAPI app with entity_motor_router wired up."""
    app = FastAPI()
    app.include_router(entity_motor_router)

    mgr = MagicMock()
    if entities is None:
        entities = {}
    mgr.get_entity.side_effect = lambda eid: entities.get(eid)
    mgr.get_all_entities.return_value = list(entities.values())

    return app, mgr


def _local_entity() -> Entity:
    return Entity(
        id="local",
        name="Local Machine",
        entity_type="vehicle",
        source="local",
        ip=None,
        status="online",
        last_seen=datetime.now(timezone.utc),
    )


def _remote_entity(eid: str = "arm1", ip: str = "192.168.137.12") -> Entity:
    return Entity(
        id=eid,
        name=f"Arm {eid[-1]} RPi",
        entity_type="arm",
        source="remote",
        ip=ip,
        status="online",
        last_seen=datetime.now(timezone.utc),
    )


def _mock_httpx_get(mock_httpx, payload):
    """Set up mock httpx for a successful GET proxy."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx.AsyncClient.return_value = mock_client
    return mock_client


def _mock_httpx_post(mock_httpx, payload):
    """Set up mock httpx for a successful POST proxy."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx.AsyncClient.return_value = mock_client
    return mock_client


def _mock_httpx_put(mock_httpx, payload):
    """Set up mock httpx for a successful PUT proxy."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx.AsyncClient.return_value = mock_client
    return mock_client


# ===================================================================
# Motor Status — GET /api/entities/{id}/motors/status
# ===================================================================


class TestMotorStatusRoute:
    """GET /api/entities/{entity_id}/motors/status"""

    def test_local_motor_status_with_bridge(self):
        """Local entity motor status reads from motor bridge."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.motor_states = {
            1: {
                "angle": 45.0,
                "speed": 10,
                "current": 0.5,
                "temperature": 35,
            },
            2: {
                "angle": 90.0,
                "speed": 0,
                "current": 0.2,
                "temperature": 32,
            },
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert len(data["data"]) == 2

    def test_local_motor_status_single_motor(self):
        """Local entity motor status with motor_id filter."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.motor_states = {
            1: {
                "angle": 45.0,
                "speed": 10,
                "current": 0.5,
                "temperature": 35,
            },
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/status?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        # Single motor returns a dict, not a list
        assert data["data"]["motor_id"] == 1
        assert data["data"]["angle_deg"] == 45.0

    def test_local_motor_status_no_bridge_returns_offline(self):
        """Local entity with no bridge returns offline motors."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        # Without a bridge, returns default offline motors
        for motor in data["data"]:
            assert motor["online"] is False

    def test_remote_motor_status_proxied(self):
        """Remote entity motor status proxies to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = [
            {"motor_id": 1, "angle_deg": 90.0, "speed_dps": 0},
        ]

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Motor Command — POST /api/entities/{id}/motors/command
# ===================================================================


class TestMotorCommandRoute:
    """POST /api/entities/{entity_id}/motors/command"""

    def test_local_motor_command_stop(self):
        """Local entity motor stop command calls bridge."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.send_stop_all = MagicMock()

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/command",
                json={"motor_id": 1, "mode": "stop", "params": {}},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["success"] is True

    def test_local_motor_command_send(self):
        """Local entity motor send_command dispatches to bridge."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.send_command = MagicMock()

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/command",
                json={
                    "motor_id": 1,
                    "mode": "position",
                    "params": {"angle": 90},
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["success"] is True

    def test_local_motor_command_no_bridge_returns_503(self):
        """Local entity motor command with no bridge returns 503."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/command",
                json={"motor_id": 1, "mode": "stop", "params": {}},
            )

        assert resp.status_code == 503

    def test_remote_motor_command_proxied(self):
        """Remote entity motor command proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"success": True, "motor_id": 1}

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/motors/command",
                json={"motor_id": 1, "mode": "stop", "params": {}},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# PID Routes — GET/POST /api/entities/{id}/motors/pid/*
# ===================================================================


class TestPIDRoutes:
    """GET/POST /api/entities/{entity_id}/motors/pid/read|write"""

    def test_local_pid_read(self):
        """Local entity PID read calls pid bridge."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.read_gains.return_value = {
            "angle_kp": 100,
            "angle_ki": 10,
            "speed_kp": 50,
            "speed_ki": 5,
            "current_kp": 30,
            "current_ki": 3,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_pid_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/pid/read?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["motor_id"] == 1
        assert data["data"]["angle_kp"] == 100

    def test_local_pid_read_no_bridge_returns_503(self):
        """Local entity PID read with no bridge returns 503."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_pid_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/pid/read?motor_id=1")

        assert resp.status_code == 503

    def test_remote_pid_read_proxied(self):
        """Remote entity PID read proxies to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "motor_id": 1,
            "angle_kp": 100,
            "angle_ki": 10,
            "speed_kp": 50,
            "speed_ki": 5,
            "current_kp": 30,
            "current_ki": 3,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/pid/read?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_pid_write(self):
        """Local entity PID write calls pid bridge."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.write_gains = MagicMock()

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_pid_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/pid/write",
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
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["success"] is True

    def test_local_pid_write_no_bridge_returns_503(self):
        """Local entity PID write with no bridge returns 503."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_pid_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/pid/write",
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

        assert resp.status_code == 503

    def test_remote_pid_write_proxied(self):
        """Remote entity PID write proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"success": True}

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/motors/pid/write",
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
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Calibrate Routes — GET/POST /api/entities/{id}/motors/calibrate/*
# ===================================================================


class TestCalibrateRoutes:
    """GET/POST /api/entities/{entity_id}/motors/calibrate/read|zero"""

    def test_local_calibrate_read(self):
        """Local entity calibrate read calls bridge read_encoder."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.read_encoder.return_value = {
            "motor_id": 1,
            "encoder_raw": 16384,
            "offset": 0,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/calibrate/read?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["encoder_raw"] == 16384

    def test_local_calibrate_read_no_bridge_returns_503(self):
        """Local entity calibrate read with no bridge returns 503."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/calibrate/read?motor_id=1")

        assert resp.status_code == 503

    def test_local_calibrate_read_exception_returns_500(self):
        """Local entity calibrate read exception returns 500."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.read_encoder.side_effect = RuntimeError("CAN timeout")

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/calibrate/read?motor_id=1")

        assert resp.status_code == 500

    def test_remote_calibrate_read_proxied(self):
        """Remote entity calibrate read proxies to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "motor_id": 1,
            "encoder_raw": 16384,
            "offset": 0,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/calibrate/read?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_calibrate_zero(self):
        """Local entity calibrate zero calls bridge write_encoder_zero."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.write_encoder_zero = MagicMock()

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/calibrate/zero",
                json={"motor_id": 1},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["success"] is True
        assert data["data"]["motor_id"] == 1

    def test_local_calibrate_zero_no_bridge_returns_503(self):
        """Local entity calibrate zero with no bridge returns 503."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/calibrate/zero",
                json={"motor_id": 1},
            )

        assert resp.status_code == 503

    def test_remote_calibrate_zero_proxied(self):
        """Remote entity calibrate zero proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"success": True, "motor_id": 1}

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/motors/calibrate/zero",
                json={"motor_id": 1},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Motor Limits — GET/PUT /api/entities/{id}/motors/limits
# ===================================================================


class TestMotorLimitsRoutes:
    """GET/PUT /api/entities/{entity_id}/motors/limits"""

    def test_local_limits_read_with_bridge(self):
        """Local entity limits read calls bridge read_limits."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.read_limits.return_value = {
            "motor_id": 1,
            "min_angle_deg": -90.0,
            "max_angle_deg": 90.0,
            "max_speed_dps": 180.0,
            "max_current_a": 5.0,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/limits?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["min_angle_deg"] == -90.0

    def test_local_limits_read_no_bridge_returns_defaults(self):
        """Local entity limits with no bridge returns default limits."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/motors/limits?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["min_angle_deg"] == -180.0
        assert data["data"]["max_angle_deg"] == 180.0

    def test_remote_limits_read_proxied(self):
        """Remote entity limits read proxies to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "motor_id": 1,
            "min_angle_deg": -90.0,
            "max_angle_deg": 90.0,
            "max_speed_dps": 180.0,
            "max_current_a": 5.0,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/limits?motor_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_limits_write(self):
        """Local entity limits write calls bridge write_limits."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.write_limits = MagicMock()

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.put(
                "/api/entities/local/motors/limits",
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
        assert data["data"]["success"] is True

    def test_local_limits_write_no_bridge_returns_503(self):
        """Local entity limits write with no bridge returns 503."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_motor_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.put(
                "/api/entities/local/motors/limits",
                json={
                    "motor_id": 1,
                    "min_angle_deg": -90.0,
                    "max_angle_deg": 90.0,
                    "max_speed_dps": 180.0,
                    "max_current_a": 5.0,
                },
            )

        assert resp.status_code == 503

    def test_remote_limits_write_proxied(self):
        """Remote entity limits write proxies PUT to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"success": True, "motor_id": 1}

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_put(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.put(
                "/api/entities/arm1/motors/limits",
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
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Step Response — POST /api/entities/{id}/motors/step-response
# ===================================================================


class TestStepResponseRoute:
    """POST /api/entities/{entity_id}/motors/step-response"""

    def test_local_step_response(self):
        """Local entity step response calls PID bridge run_step_test."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.run_step_test.return_value = {
            "motor_id": 1,
            "target_angle_deg": 90.0,
            "samples": [{"t": 0.0, "angle": 0.0}, {"t": 0.1, "angle": 45.0}],
            "settling_time_s": 0.8,
            "overshoot_pct": 5.2,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_pid_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/step-response",
                json={
                    "motor_id": 1,
                    "target_angle_deg": 90.0,
                    "duration_s": 5.0,
                    "sample_rate_hz": 50,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["motor_id"] == 1

    def test_local_step_response_no_bridge_returns_503(self):
        """Local entity step response with no bridge returns 503."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_pid_bridge", return_value=None),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/step-response",
                json={
                    "motor_id": 1,
                    "target_angle_deg": 90.0,
                },
            )

        assert resp.status_code == 503

    def test_local_step_response_exception_returns_500(self):
        """Local entity step response exception returns 500."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bridge = MagicMock()
        mock_bridge.run_step_test.side_effect = RuntimeError("Motor stall")

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_pid_bridge", return_value=mock_bridge),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/motors/step-response",
                json={
                    "motor_id": 1,
                    "target_angle_deg": 90.0,
                },
            )

        assert resp.status_code == 500

    def test_remote_step_response_proxied(self):
        """Remote entity step response proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "motor_id": 1,
            "target_angle_deg": 90.0,
            "samples": [],
            "settling_time_s": 0.8,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/motors/step-response",
                json={
                    "motor_id": 1,
                    "target_angle_deg": 90.0,
                    "duration_s": 5.0,
                    "sample_rate_hz": 50,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Entity Not Found — 404
# ===================================================================


class TestEntityNotFound:
    """404 for unknown entity_id across different endpoints."""

    def test_motor_status_unknown_entity(self):
        """GET motor status for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/motors/status")

        assert resp.status_code == 404

    def test_motor_command_unknown_entity(self):
        """POST motor command for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/motors/command",
                json={"motor_id": 1, "mode": "stop", "params": {}},
            )

        assert resp.status_code == 404

    def test_pid_read_unknown_entity(self):
        """GET PID read for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/motors/pid/read?motor_id=1")

        assert resp.status_code == 404

    def test_limits_unknown_entity(self):
        """GET limits for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/motors/limits?motor_id=1")

        assert resp.status_code == 404

    def test_step_response_unknown_entity(self):
        """POST step response for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/motors/step-response",
                json={"motor_id": 1, "target_angle_deg": 90.0},
            )

        assert resp.status_code == 404


# ===================================================================
# Entity Manager Unavailable — 503
# ===================================================================


class TestEntityManagerUnavailable:
    """503 when entity manager is not initialized."""

    def test_motor_status_no_manager(self):
        """Motor status returns 503 when manager is None."""
        app = FastAPI()
        app.include_router(entity_motor_router)

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/status")

        assert resp.status_code == 503

    def test_motor_command_no_manager(self):
        """Motor command returns 503 when manager is None."""
        app = FastAPI()
        app.include_router(entity_motor_router)

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/motors/command",
                json={"motor_id": 1, "mode": "stop", "params": {}},
            )

        assert resp.status_code == 503


# ===================================================================
# Remote Agent Errors — 502
# ===================================================================


class TestRemoteAgentError:
    """Proxy error propagation for remote entities."""

    def test_agent_unreachable_returns_502(self):
        """Network error to remote agent returns 502."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/status")

        assert resp.status_code == 502

    def test_agent_timeout_returns_502(self):
        """Timeout to remote agent returns 502."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/status")

        assert resp.status_code == 502

    def test_agent_non_200_forwarded(self):
        """Non-200 response from agent is forwarded as JSONResponse."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.json.return_value = {"error": "internal error"}
            mock_resp.headers = {"content-type": "application/json"}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/motors/status")

        # The router wraps non-200 in a JSONResponse with the agent's status
        assert resp.status_code == 500

    def test_remote_post_agent_unreachable_returns_502(self):
        """Network error on POST proxy returns 502."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/motors/command",
                json={"motor_id": 1, "mode": "stop", "params": {}},
            )

        assert resp.status_code == 502
