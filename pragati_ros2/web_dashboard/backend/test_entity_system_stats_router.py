"""Unit tests for entity_system_stats_router — entity-scoped system stats proxy routes.

Tests cover:
- GET /{id}/system/stats (local + remote)
- GET /{id}/system/processes (local + remote)
- Entity not found: 404
- Entity manager unavailable: 503
- Agent unreachable: 502

All httpx / psutil calls are mocked — no real network or system calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity
from backend.entity_system_stats_router import entity_system_stats_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "backend.entity_system_stats_router"


def _make_app(
    entities: dict[str, Entity] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal FastAPI app with entity_system_stats_router wired up."""
    app = FastAPI()
    app.include_router(entity_system_stats_router)

    mgr = MagicMock()
    if entities is None:
        entities = {}
    mgr.get_entity.side_effect = lambda eid: entities.get(eid)

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


# ===================================================================
# GET /api/entities/{id}/system/stats
# ===================================================================


class TestGetEntitySystemStats:
    """GET /api/entities/{entity_id}/system/stats"""

    def test_local_entity_collects_via_psutil(self):
        """Local entity collects system stats directly via psutil."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.psutil") as mock_psutil:
                mock_psutil.cpu_percent.return_value = 42.0
                mock_psutil.virtual_memory.return_value = MagicMock(
                    used=4 * 1024**3, total=8 * 1024**3
                )
                mock_psutil.disk_usage.return_value = MagicMock(
                    used=30 * 1024**3, total=64 * 1024**3
                )
                mock_psutil.sensors_temperatures.return_value = {
                    "cpu_thermal": [MagicMock(current=55.0)]
                }

                client = TestClient(app)
                resp = client.get("/api/entities/local/system/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "local"
        assert body["source"] == "local"
        assert body["data"]["cpu_percent"] == 42.0
        assert body["data"]["memory_used"] == 4 * 1024**3
        assert body["data"]["memory_total"] == 8 * 1024**3
        assert body["data"]["disk_used"] == 30 * 1024**3
        assert body["data"]["disk_total"] == 64 * 1024**3
        assert body["data"]["cpu_temp"] == 55.0

    def test_local_entity_null_temp(self):
        """Local entity with no thermal sensors returns cpu_temp=null."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.psutil") as mock_psutil:
                mock_psutil.cpu_percent.return_value = 10.0
                mock_psutil.virtual_memory.return_value = MagicMock(
                    used=1024**3, total=4 * 1024**3
                )
                mock_psutil.disk_usage.return_value = MagicMock(
                    used=10 * 1024**3, total=32 * 1024**3
                )
                mock_psutil.sensors_temperatures.return_value = {}

                client = TestClient(app)
                resp = client.get("/api/entities/local/system/stats")

        assert resp.status_code == 200
        assert resp.json()["data"]["cpu_temp"] is None

    def test_remote_entity_proxies_to_agent(self):
        """Remote entity proxies GET to agent /system/stats."""
        remote = _remote_entity()
        app, mgr = _make_app({"arm1": remote})

        agent_payload = {
            "cpu_percent": 60.0,
            "memory_used": 2 * 1024**3,
            "memory_total": 4 * 1024**3,
            "disk_used": 10 * 1024**3,
            "disk_total": 32 * 1024**3,
            "cpu_temp": 48.5,
        }

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.httpx") as mock_httpx:
                _mock_httpx_get(mock_httpx, agent_payload)

                client = TestClient(app)
                resp = client.get("/api/entities/arm1/system/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert body["data"] == agent_payload

    def test_entity_not_found_returns_404(self):
        """Unknown entity_id returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/nonexistent/system/stats")

        assert resp.status_code == 404

    def test_entity_manager_unavailable_returns_503(self):
        """If EntityManager is None, returns 503."""
        app, _ = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/entities/any/system/stats")

        assert resp.status_code == 503

    def test_remote_agent_unreachable_returns_502(self):
        """If remote agent is unreachable, returns 502."""
        remote = _remote_entity()
        app, mgr = _make_app({"arm1": remote})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.httpx") as mock_httpx:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_httpx.AsyncClient.return_value = mock_client
                mock_httpx.ConnectTimeout = httpx.ConnectTimeout
                mock_httpx.ReadTimeout = httpx.ReadTimeout
                mock_httpx.ConnectError = httpx.ConnectError
                mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
                mock_httpx.Timeout = httpx.Timeout

                client = TestClient(app)
                resp = client.get("/api/entities/arm1/system/stats")

        assert resp.status_code == 502

    def test_remote_agent_non_200_returns_502(self):
        """If remote agent returns non-200, returns 502."""
        remote = _remote_entity()
        app, mgr = _make_app({"arm1": remote})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.httpx") as mock_httpx:
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_httpx.AsyncClient.return_value = mock_client
                mock_httpx.Timeout = httpx.Timeout

                client = TestClient(app)
                resp = client.get("/api/entities/arm1/system/stats")

        assert resp.status_code == 502


# ===================================================================
# GET /api/entities/{id}/system/processes
# ===================================================================


class TestGetEntitySystemProcesses:
    """GET /api/entities/{entity_id}/system/processes"""

    def test_local_entity_collects_via_psutil(self):
        """Local entity collects top 15 processes directly via psutil."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        # Create 20 mock processes
        mock_procs = []
        for i in range(1, 21):
            proc = MagicMock()
            proc.info = {
                "pid": i,
                "name": f"proc{i}",
                "cpu_percent": float(i),
                "memory_info": MagicMock(rss=i * 1024 * 1024),
                "status": "running",
            }
            mock_procs.append(proc)

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.psutil") as mock_psutil:
                mock_psutil.process_iter.return_value = mock_procs
                mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
                mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
                mock_psutil.ZombieProcess = type("ZombieProcess", (Exception,), {})

                client = TestClient(app)
                resp = client.get("/api/entities/local/system/processes")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "local"
        assert body["source"] == "local"
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) == 15
        # Sorted by cpu_percent descending
        cpu_values = [p["cpu_percent"] for p in data]
        assert cpu_values == sorted(cpu_values, reverse=True)

    def test_remote_entity_proxies_to_agent(self):
        """Remote entity proxies GET to agent /system/processes."""
        remote = _remote_entity()
        app, mgr = _make_app({"arm1": remote})

        agent_payload = [
            {
                "pid": 1,
                "name": "python3",
                "cpu_percent": 25.0,
                "memory_mb": 50.0,
                "status": "running",
            },
            {
                "pid": 2,
                "name": "ros2",
                "cpu_percent": 15.0,
                "memory_mb": 30.0,
                "status": "running",
            },
        ]

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.httpx") as mock_httpx:
                _mock_httpx_get(mock_httpx, agent_payload)

                client = TestClient(app)
                resp = client.get("/api/entities/arm1/system/processes")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert body["data"] == agent_payload

    def test_entity_not_found_returns_404(self):
        """Unknown entity_id returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/nonexistent/system/processes")

        assert resp.status_code == 404

    def test_remote_agent_unreachable_returns_502(self):
        """If remote agent is unreachable, returns 502."""
        remote = _remote_entity()
        app, mgr = _make_app({"arm1": remote})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            with patch(f"{MODULE}.httpx") as mock_httpx:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_httpx.AsyncClient.return_value = mock_client
                mock_httpx.ConnectTimeout = httpx.ConnectTimeout
                mock_httpx.ReadTimeout = httpx.ReadTimeout
                mock_httpx.ConnectError = httpx.ConnectError
                mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
                mock_httpx.Timeout = httpx.Timeout

                client = TestClient(app)
                resp = client.get("/api/entities/arm1/system/processes")

        assert resp.status_code == 502
