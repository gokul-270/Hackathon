"""Tests for diagnostics_api.py — GET /api/diagnostics/run endpoint.

TDD: covers all-pass, unreachable entity, local entity, and fix_hint content.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport

DIAG_MODULE = "backend.diagnostics_api"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(
    entity_id: str,
    name: str,
    source: str = "remote",
    ip: str = "192.168.1.10",
    ros2_available: bool = True,
    mqtt_status: str = "active",
) -> MagicMock:
    entity = MagicMock()
    entity.id = entity_id
    entity.name = name
    entity.source = source
    entity.ip = ip
    entity.ros2_available = ros2_available
    entity.health = {"mqtt": mqtt_status}
    entity.agent_base_url.return_value = f"http://{ip}:8091"
    return entity


def _make_test_app() -> FastAPI:
    from backend.diagnostics_api import diagnostics_router

    app = FastAPI()
    app.include_router(diagnostics_router)
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_client():
    """Plain test client for the diagnostics app."""
    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDiagnosticsRun:
    """Tests for GET /api/diagnostics/run."""

    @pytest.mark.asyncio
    async def test_all_pass_scenario(self, test_client):
        """All checks pass when entity is reachable, ROS2 up, systemd ok, MQTT active."""
        entity = _make_entity("arm1", "Arm 1 RPi", source="remote", ros2_available=True)
        mock_mgr = MagicMock()
        mock_mgr.get_all_entities.return_value = [entity]

        agent_http_result = {
            "status": "pass",
            "latency_ms": 45,
            "message": "Agent responded in 45ms",
            "fix_hint": None,
            "_agent_data": {"uptime_seconds": 3600},
        }
        diag_probe_result = {
            "ok": True,
            "latency_ms": 30,
            "data": {"systemd_sudo": True},
        }

        with (
            patch(f"{DIAG_MODULE}.get_entity_manager", return_value=mock_mgr),
            patch(
                f"{DIAG_MODULE}._probe_agent_http", new=AsyncMock(return_value=agent_http_result)
            ),
            patch(
                f"{DIAG_MODULE}._probe_agent_diagnostics",
                new=AsyncMock(return_value=diag_probe_result),
            ),
        ):
            resp = await test_client.get("/api/diagnostics/run")

        assert resp.status_code == 200
        data = resp.json()
        assert "entities" in data
        assert len(data["entities"]) == 1

        entity_result = data["entities"][0]
        assert entity_result["entity_id"] == "arm1"
        assert entity_result["overall"] == "pass"

        checks = entity_result["checks"]
        assert checks["agent_http"]["status"] == "pass"
        assert checks["agent_http"]["latency_ms"] == 45
        assert checks["ros2"]["status"] == "pass"
        assert checks["systemd"]["status"] == "pass"
        assert checks["mqtt"]["status"] == "pass"

    @pytest.mark.asyncio
    async def test_unreachable_entity_skips_dependent_checks(self, test_client):
        """When agent unreachable, ROS2 and systemd checks are skipped."""
        entity = _make_entity("arm2", "Arm 2 RPi", source="remote")
        mock_mgr = MagicMock()
        mock_mgr.get_all_entities.return_value = [entity]

        agent_http_fail = {
            "status": "fail",
            "latency_ms": 5000,
            "message": "Connection timed out after 5s",
            "fix_hint": "Start the agent: systemctl start pragati-agent",
            "_agent_data": None,
        }

        with (
            patch(f"{DIAG_MODULE}.get_entity_manager", return_value=mock_mgr),
            patch(f"{DIAG_MODULE}._probe_agent_http", new=AsyncMock(return_value=agent_http_fail)),
        ):
            resp = await test_client.get("/api/diagnostics/run")

        assert resp.status_code == 200
        data = resp.json()
        entity_result = data["entities"][0]
        assert entity_result["overall"] == "fail"

        checks = entity_result["checks"]
        assert checks["agent_http"]["status"] == "fail"
        assert checks["ros2"]["status"] == "skip"
        assert checks["ros2"]["message"] == "Skipped — agent unreachable"
        assert checks["systemd"]["status"] == "skip"
        assert checks["systemd"]["message"] == "Skipped — agent unreachable"
        # MQTT still runs (uses cached data)
        assert checks["mqtt"]["status"] in ("pass", "fail", "skip")

    @pytest.mark.asyncio
    async def test_local_entity_skips_agent_checks(self, test_client):
        """Local entity skips agent HTTP, ROS2, and systemd checks."""
        entity = _make_entity("local", "Local", source="local", ip=None, mqtt_status="disabled")
        entity.agent_base_url.return_value = "http://127.0.0.1:8091"
        mock_mgr = MagicMock()
        mock_mgr.get_all_entities.return_value = [entity]

        with patch(f"{DIAG_MODULE}.get_entity_manager", return_value=mock_mgr):
            resp = await test_client.get("/api/diagnostics/run")

        assert resp.status_code == 200
        data = resp.json()
        entity_result = data["entities"][0]

        checks = entity_result["checks"]
        assert checks["agent_http"]["status"] == "skip"
        assert checks["agent_http"]["message"] == "Local entity"
        assert checks["ros2"]["status"] == "skip"
        assert checks["ros2"]["message"] == "Local entity"
        assert checks["systemd"]["status"] == "skip"
        assert checks["systemd"]["message"] == "Local entity"

    @pytest.mark.asyncio
    async def test_systemd_fail_has_fix_hint(self):
        """Failed systemd check includes fix_hint with provision command."""
        from backend.diagnostics_api import _build_systemd_result

        result = _build_systemd_result({"systemd_sudo": False}, 50)
        assert result["status"] == "fail"
        assert "provision" in result["fix_hint"]

    @pytest.mark.asyncio
    async def test_agent_http_timeout_message(self):
        """Timeout returns descriptive message with timeout duration."""
        from backend.diagnostics_api import _probe_agent_http

        entity = _make_entity("arm3", "Arm 3 RPi")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))
        mock_async_context = AsyncMock()
        mock_async_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_context.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{DIAG_MODULE}.httpx.AsyncClient", return_value=mock_async_context):
            result = await _probe_agent_http(entity)

        assert result["status"] == "fail"
        assert "timed out" in result["message"].lower() or "5s" in result["message"]
        assert result["fix_hint"] is not None

    @pytest.mark.asyncio
    async def test_no_entity_manager_returns_empty(self, test_client):
        """When EntityManager is not initialized, returns empty entities list."""
        with patch(f"{DIAG_MODULE}.get_entity_manager", return_value=None):
            resp = await test_client.get("/api/diagnostics/run")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entities"] == []

    @pytest.mark.asyncio
    async def test_response_schema_per_check_fields(self, test_client):
        """Each check result has required fields: status, latency_ms, message, fix_hint."""
        entity = _make_entity("arm2", "Arm 2 RPi", source="remote")
        mock_mgr = MagicMock()
        mock_mgr.get_all_entities.return_value = [entity]

        agent_http_fail = {
            "status": "fail",
            "latency_ms": 5000,
            "message": "Connection timed out after 5s",
            "fix_hint": "Start the agent",
            "_agent_data": None,
        }

        with (
            patch(f"{DIAG_MODULE}.get_entity_manager", return_value=mock_mgr),
            patch(f"{DIAG_MODULE}._probe_agent_http", new=AsyncMock(return_value=agent_http_fail)),
        ):
            resp = await test_client.get("/api/diagnostics/run")

        data = resp.json()
        for check in data["entities"][0]["checks"].values():
            assert "status" in check
            assert "latency_ms" in check
            assert "message" in check
            assert "fix_hint" in check
            assert check["status"] in ("pass", "fail", "skip")

    @pytest.mark.asyncio
    async def test_mqtt_fail_has_fix_hint(self):
        """Failed MQTT check includes fix_hint referencing mosquitto."""
        from backend.diagnostics_api import _build_mqtt_result

        entity = _make_entity("arm1", "Arm 1", mqtt_status="broker_down")
        result = _build_mqtt_result(entity)
        assert result["status"] == "fail"
        assert "mosquitto" in result["fix_hint"]
