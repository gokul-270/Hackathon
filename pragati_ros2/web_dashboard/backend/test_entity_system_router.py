"""Unit tests for entity_system_router — entity-scoped system management routes.

Tests cover:
- List services: GET /{id}/system/services (local + remote)
- Service action: POST /{id}/system/services/{name}/{action} (local + remote)
- Service action disallowed: 403 for non-allowlisted services
- Service logs: GET /{id}/system/services/{name}/logs (local + remote)
- Reboot: POST /{id}/system/reboot (local + remote)
- Shutdown: POST /{id}/system/shutdown (local + remote)
- Entity not found: 404
- Entity manager unavailable: 503
- Agent unreachable: 502

All httpx / subprocess calls are mocked — no real network or system calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity
from backend.entity_system_router import entity_system_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "backend.entity_system_router"

# Test allowlist — we patch this into the module to isolate from real config
TEST_ALLOWED_SERVICES = ["pragati-arm", "pragati-vehicle", "pragati-dashboard"]


def _make_app(
    entities: dict[str, Entity] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal FastAPI app with entity_system_router wired up."""
    app = FastAPI()
    app.include_router(entity_system_router)

    mgr = MagicMock()
    if entities is None:
        entities = {}
    mgr.get_entity.side_effect = lambda eid: entities.get(eid)
    mgr.get_all_entities.return_value = list(entities.values())

    return app, mgr


def _patch_allowlist():
    """Return a patch context that overrides ALLOWED_SERVICES in the router module."""
    return patch(f"{MODULE}.ALLOWED_SERVICES", TEST_ALLOWED_SERVICES)


def _validate_test_service_name(name: str) -> None:
    """Test version of _validate_service_name using TEST_ALLOWED_SERVICES."""
    from fastapi import HTTPException as _HTTPException

    if name not in TEST_ALLOWED_SERVICES:
        raise _HTTPException(
            status_code=403,
            detail=(
                f"Service '{name}' is not in the allowed list. "
                f"Allowed: {TEST_ALLOWED_SERVICES}"
            ),
        )


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


def _mock_subprocess_ok(stdout: str = "", returncode: int = 0):
    """Create a mock asyncio subprocess that returns successfully."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(
        return_value=(
            stdout.encode("utf-8"),
            b"",
        )
    )
    mock_proc.returncode = returncode
    return mock_proc


# ===================================================================
# List Services — GET /api/entities/{id}/system/services
# ===================================================================


class TestListServicesRoute:
    """GET /api/entities/{entity_id}/system/services"""

    def test_local_list_services(self):
        """Local entity lists services via systemd_api helpers."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_status = {
            "name": "pragati-arm",
            "active_state": "active",
            "sub_state": "running",
            "enabled": True,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            _patch_allowlist(),
            patch(
                f"{MODULE}._get_service_status",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/system/services")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert "services" in data["data"]
        assert len(data["data"]["services"]) == 3  # 3 test allowed services

    def test_local_list_services_with_error(self):
        """Local entity list services handles exceptions per-service."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        async def _status_side_effect(name):
            if name == "pragati-arm":
                raise RuntimeError("systemctl failed")
            return {
                "name": name,
                "active_state": "inactive",
                "sub_state": "dead",
                "enabled": False,
            }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            _patch_allowlist(),
            patch(
                f"{MODULE}._get_service_status",
                new_callable=AsyncMock,
                side_effect=_status_side_effect,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/system/services")

        assert resp.status_code == 200
        data = resp.json()
        services = data["data"]["services"]
        # The one that errored should have "error" key
        arm_svc = [s for s in services if s["name"] == "pragati-arm"][0]
        assert "error" in arm_svc

    def test_remote_list_services(self):
        """Remote entity proxies service list GET to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "services": [
                {
                    "name": "pragati-arm",
                    "active_state": "active",
                    "sub_state": "running",
                    "enabled": True,
                }
            ]
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/system/services")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Service Action — POST /api/entities/{id}/system/services/{name}/{action}
# ===================================================================


class TestServiceActionRoute:
    """POST /api/entities/{entity_id}/system/services/{name}/{action}"""

    @pytest.mark.parametrize(
        "action", ["start", "stop", "restart", "enable", "disable"]
    )
    def test_local_service_action(self, action):
        """Local entity service action calls _run_systemctl."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
            patch(
                f"{MODULE}._run_systemctl",
                new_callable=AsyncMock,
                return_value=("", "", 0),
            ) as mock_ctl,
        ):
            client = TestClient(app)
            resp = client.post(
                f"/api/entities/local/system/services/pragati-arm/{action}"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["success"] is True
        assert data["data"]["service"] == "pragati-arm"
        assert data["data"]["action"] == action
        mock_ctl.assert_awaited_once()

    def test_local_service_action_failure(self):
        """Local service action returns 502 when systemctl fails."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
            patch(
                f"{MODULE}._run_systemctl",
                new_callable=AsyncMock,
                return_value=("", "Failed to start", 1),
            ),
        ):
            client = TestClient(app)
            resp = client.post("/api/entities/local/system/services/pragati-arm/start")

        assert resp.status_code == 502

    def test_local_service_action_disallowed(self):
        """Disallowed service name returns 403."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
        ):
            client = TestClient(app)
            resp = client.post("/api/entities/local/system/services/sshd/start")

        assert resp.status_code == 403

    def test_local_service_action_invalid_action(self):
        """Invalid action returns 400."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/system/services/pragati-arm/destroy"
            )

        assert resp.status_code == 400

    def test_remote_service_action(self):
        """Remote entity proxies service action POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "success": True,
            "service": "pragati-arm",
            "action": "restart",
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post("/api/entities/arm1/system/services/pragati-arm/restart")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_remote_service_action_disallowed(self):
        """Remote entity also validates allowlist before proxying."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
        ):
            client = TestClient(app)
            resp = client.post("/api/entities/arm1/system/services/nginx/start")

        assert resp.status_code == 403


# ===================================================================
# Service Logs — GET /api/entities/{id}/system/services/{name}/logs
# ===================================================================


class TestServiceLogsRoute:
    """GET /api/entities/{entity_id}/system/services/{name}/logs"""

    def test_local_service_logs(self):
        """Local entity fetches logs via journalctl subprocess."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_proc = _mock_subprocess_ok(
            "Mar 01 10:00:00 rpi pragati[123]: Started\n"
            "Mar 01 10:00:01 rpi pragati[123]: Running\n"
        )

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
            patch(
                f"{MODULE}.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            client = TestClient(app)
            resp = client.get(
                "/api/entities/local/system/services/pragati-arm/logs?lines=50"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["service"] == "pragati-arm"
        assert data["data"]["count"] == 2

    def test_local_service_logs_disallowed(self):
        """Disallowed service returns 403 for logs."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/system/services/sshd/logs")

        assert resp.status_code == 403

    def test_remote_service_logs(self):
        """Remote entity proxies logs GET to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "service": "pragati-arm",
            "lines": ["line1", "line2"],
            "count": 2,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get(
                "/api/entities/arm1/system/services/pragati-arm/logs?lines=100"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Reboot — POST /api/entities/{id}/system/reboot
# ===================================================================


class TestRebootRoute:
    """POST /api/entities/{entity_id}/system/reboot"""

    def test_local_reboot(self):
        """Local entity reboot fires subprocess.Popen."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.subprocess.Popen") as mock_popen,
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/system/reboot",
                json={"token": "REBOOT"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["status"] == "reboot_initiated"
        mock_popen.assert_called_once_with(
            ["sudo", "reboot"],
            stdout=-3,  # subprocess.DEVNULL
            stderr=-3,
        )

    def test_local_reboot_bad_token(self):
        """Local reboot with wrong token returns 403."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/system/reboot",
                json={"token": "WRONG"},
            )

        assert resp.status_code == 403

    def test_local_reboot_missing_token(self):
        """Local reboot without token returns 403."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/system/reboot",
                json={},
            )

        assert resp.status_code == 403

    def test_remote_reboot(self):
        """Remote entity proxies reboot POST with token to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"status": "reboot_initiated"}

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_client = _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/system/reboot",
                json={"token": "REBOOT"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"
        # Verify the POST body sent to agent includes the token
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs.get("json") == {"token": "REBOOT"}


# ===================================================================
# Shutdown — POST /api/entities/{id}/system/shutdown
# ===================================================================


class TestShutdownRoute:
    """POST /api/entities/{entity_id}/system/shutdown"""

    def test_local_shutdown(self):
        """Local entity shutdown fires subprocess.Popen."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.subprocess.Popen") as mock_popen,
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/system/shutdown",
                json={"token": "SHUTDOWN"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["status"] == "shutdown_initiated"
        mock_popen.assert_called_once_with(
            ["sudo", "shutdown", "-h", "now"],
            stdout=-3,
            stderr=-3,
        )

    def test_local_shutdown_bad_token(self):
        """Local shutdown with wrong token returns 403."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/system/shutdown",
                json={"token": "WRONG"},
            )

        assert resp.status_code == 403

    def test_local_shutdown_missing_token(self):
        """Local shutdown without token returns 403."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/system/shutdown",
                json={},
            )

        assert resp.status_code == 403

    def test_remote_shutdown(self):
        """Remote entity proxies shutdown POST with token to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"status": "shutdown_initiated"}

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_client = _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/system/shutdown",
                json={"token": "SHUTDOWN"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs.get("json") == {"token": "SHUTDOWN"}


# ===================================================================
# Entity Not Found — 404
# ===================================================================


class TestEntityNotFound:
    """404 for unknown entity_id across different endpoints."""

    def test_list_services_unknown_entity(self):
        """GET services for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/system/services")

        assert resp.status_code == 404

    def test_service_action_unknown_entity(self):
        """POST service action for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/system/services/pragati-arm/restart"
            )

        assert resp.status_code == 404

    def test_service_logs_unknown_entity(self):
        """GET service logs for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/system/services/pragati-arm/logs")

        assert resp.status_code == 404

    def test_reboot_unknown_entity(self):
        """POST reboot for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/system/reboot",
                json={"token": "REBOOT"},
            )

        assert resp.status_code == 404

    def test_shutdown_unknown_entity(self):
        """POST shutdown for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/system/shutdown",
                json={"token": "SHUTDOWN"},
            )

        assert resp.status_code == 404


# ===================================================================
# Entity Manager Unavailable — 503
# ===================================================================


class TestEntityManagerUnavailable:
    """503 when entity manager is not initialized."""

    def test_list_services_no_manager(self):
        """List services returns 503 when manager is None."""
        app = FastAPI()
        app.include_router(entity_system_router)

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/system/services")

        assert resp.status_code == 503

    def test_reboot_no_manager(self):
        """Reboot returns 503 when manager is None."""
        app = FastAPI()
        app.include_router(entity_system_router)

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/system/reboot",
                json={"token": "REBOOT"},
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
            resp = client.get("/api/entities/arm1/system/services")

        assert resp.status_code == 502

    def test_agent_timeout_returns_502(self):
        """Timeout to remote agent returns 502."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._validate_service_name",
                side_effect=_validate_test_service_name,
            ),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.post("/api/entities/arm1/system/services/pragati-arm/restart")

        assert resp.status_code == 502

    def test_agent_non_200_forwarded(self):
        """Non-200 response from agent is forwarded."""
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
            resp = client.get("/api/entities/arm1/system/services")

        assert resp.status_code == 500
