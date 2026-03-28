"""Unit tests for entity_rosbag_router — entity-scoped rosbag API routes.

Tests cover:
- Bag listing: GET /{id}/rosbag/list (local + remote)
- Record start/stop/status: POST/GET /{id}/rosbag/record/* (local + remote)
- Download: GET /{id}/rosbag/download/{name} (local + remote)
- Playback start/stop: POST /{id}/rosbag/play/* (local + remote)
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
from starlette.responses import StreamingResponse

from backend.entity_model import Entity
from backend.entity_rosbag_router import entity_rosbag_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "backend.entity_rosbag_router"


def _make_app(
    entities: dict[str, Entity] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal FastAPI app with entity_rosbag_router wired up."""
    app = FastAPI()
    app.include_router(entity_rosbag_router)

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


# ===================================================================
# Rosbag List — GET /api/entities/{id}/rosbag/list
# ===================================================================


class TestRosbagListRoute:
    """GET /api/entities/{entity_id}/rosbag/list"""

    def test_local_list_bags(self):
        """Local entity list bags calls _local_list_bags."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_bags = [
            {
                "name": "2025-01-15_field_test",
                "path": "/bags/2025-01-15_field_test",
                "size_bytes": 1048576,
                "duration_s": 120.5,
                "message_count": 5000,
            },
            {
                "name": "2025-01-14_lab",
                "path": "/bags/2025-01-14_lab",
                "size_bytes": 524288,
                "duration_s": 60.0,
                "message_count": 2500,
            },
        ]

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_list_bags",
                new_callable=AsyncMock,
                return_value=mock_bags,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/rosbag/list")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert len(data["data"]) == 2

    def test_local_list_bags_empty(self):
        """Local entity list bags returns empty list when no bags."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_list_bags",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/rosbag/list")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []

    def test_remote_list_bags_proxied(self):
        """Remote entity list bags proxies to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = [
            {
                "name": "2025-01-15_field_test",
                "size_bytes": 1048576,
            },
        ]

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/rosbag/list")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Record Routes — POST/GET /api/entities/{id}/rosbag/record/*
# ===================================================================


class TestRosbagRecordRoutes:
    """POST/GET /api/entities/{entity_id}/rosbag/record/start|stop"""

    def test_local_record_start(self):
        """Local entity record start calls _local_record_start."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {
            "recording": True,
            "bag_name": "2025-01-15_12-00-00",
            "pid": 12345,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_record_start",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/rosbag/record/start",
                json={"profile": "default"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["recording"] is True

    def test_remote_record_start_proxied(self):
        """Remote entity record start proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "recording": True,
            "bag_name": "2025-01-15_12-00-00",
            "pid": 54321,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/rosbag/record/start",
                json={"profile": "default"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_record_stop(self):
        """Local entity record stop calls _local_record_stop."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {
            "recording": False,
            "bag_name": "2025-01-15_12-00-00",
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_record_stop",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/rosbag/record/stop",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["recording"] is False

    def test_remote_record_stop_proxied(self):
        """Remote entity record stop proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "recording": False,
            "bag_name": "2025-01-15_12-00-00",
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/rosbag/record/stop",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Record Status — GET /api/entities/{id}/rosbag/record/status
# ===================================================================


class TestRosbagRecordStatusRoute:
    """GET /api/entities/{entity_id}/rosbag/record/status"""

    def test_local_record_status(self):
        """Local entity record status calls _local_record_status."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_status = {
            "recording": True,
            "bag_name": "2025-01-15_12-00-00",
            "duration_s": 45.2,
            "size_bytes": 512000,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_record_status",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/rosbag/record/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["recording"] is True

    def test_local_record_status_not_recording(self):
        """Local entity record status when not recording."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_status = {"recording": False}

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_record_status",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/rosbag/record/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["recording"] is False

    def test_remote_record_status_proxied(self):
        """Remote entity record status proxies GET to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "recording": True,
            "bag_name": "2025-01-15_12-00-00",
            "duration_s": 30.0,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/rosbag/record/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# Download — GET /api/entities/{id}/rosbag/download/{name}
# ===================================================================


class TestRosbagDownloadRoute:
    """GET /api/entities/{entity_id}/rosbag/download/{name}"""

    def test_local_download(self):
        """Local entity download calls _local_download."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        # Mock _local_download to return a StreamingResponse
        async def _fake_chunks():
            yield b"fake-bag-data"

        mock_streaming = StreamingResponse(
            _fake_chunks(),
            media_type="application/gzip",
            headers={"Content-Disposition": 'attachment; filename="test.tar.gz"'},
        )

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_download",
                new_callable=AsyncMock,
                return_value=mock_streaming,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/rosbag/download/test_bag")

        assert resp.status_code == 200
        assert "content-disposition" in resp.headers

    def test_local_download_not_found(self):
        """Local entity download returns 404 for missing bag."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        from fastapi import HTTPException

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_download",
                new_callable=AsyncMock,
                side_effect=HTTPException(
                    status_code=404, detail="Bag 'missing' not found"
                ),
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/rosbag/download/missing")

        assert resp.status_code == 404

    def test_remote_download_proxied(self):
        """Remote entity download proxies streaming from agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        # Mock _proxy_stream to return a StreamingResponse
        async def _fake_chunks():
            yield b"remote-bag-data"

        mock_streaming = StreamingResponse(
            _fake_chunks(),
            media_type="application/gzip",
            headers={"Content-Disposition": 'attachment; filename="test.tar.gz"'},
        )

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._proxy_stream",
                new_callable=AsyncMock,
                return_value=mock_streaming,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/rosbag/download/test_bag")

        assert resp.status_code == 200

    def test_remote_download_agent_unreachable(self):
        """Remote entity download returns 502 when agent unreachable."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        from fastapi import HTTPException

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._proxy_stream",
                new_callable=AsyncMock,
                side_effect=HTTPException(
                    status_code=502,
                    detail="Agent at 192.168.137.12 unreachable",
                ),
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/rosbag/download/test_bag")

        assert resp.status_code == 502


# ===================================================================
# Play Routes — POST /api/entities/{id}/rosbag/play/*
# ===================================================================


class TestRosbagPlayRoutes:
    """POST /api/entities/{entity_id}/rosbag/play/start|stop"""

    def test_local_play_start(self):
        """Local entity play start calls _local_play_start."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {
            "playing": True,
            "bag_name": "2025-01-15_field_test",
            "pid": 99999,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_play_start",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/rosbag/play/start",
                json={"bag_name": "2025-01-15_field_test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["playing"] is True

    def test_remote_play_start_proxied(self):
        """Remote entity play start proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "playing": True,
            "bag_name": "2025-01-15_field_test",
            "pid": 88888,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/rosbag/play/start",
                json={"bag_name": "2025-01-15_field_test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_play_stop(self):
        """Local entity play stop calls _local_play_stop."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {
            "playing": False,
            "bag_name": "2025-01-15_field_test",
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_play_stop",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/rosbag/play/stop",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["playing"] is False

    def test_remote_play_stop_proxied(self):
        """Remote entity play stop proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "playing": False,
            "bag_name": "2025-01-15_field_test",
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/rosbag/play/stop",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_play_start_conflict_returns_409(self):
        """Local play start returns 409 when playback already active."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        from fastapi import HTTPException

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_play_start",
                new_callable=AsyncMock,
                side_effect=HTTPException(
                    status_code=409, detail="Playback already active"
                ),
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/rosbag/play/start",
                json={"bag_name": "test_bag"},
            )

        assert resp.status_code == 409

    def test_local_play_stop_no_active_returns_409(self):
        """Local play stop returns 409 when no active playback."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        from fastapi import HTTPException

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}._local_play_stop",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=409, detail="No active playback"),
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/rosbag/play/stop",
            )

        assert resp.status_code == 409


# ===================================================================
# Entity Not Found — 404
# ===================================================================


class TestEntityNotFound:
    """404 for unknown entity_id across different rosbag endpoints."""

    def test_list_unknown_entity(self):
        """GET rosbag list for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/rosbag/list")

        assert resp.status_code == 404

    def test_record_start_unknown_entity(self):
        """POST record start for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/rosbag/record/start",
                json={"profile": "default"},
            )

        assert resp.status_code == 404

    def test_record_stop_unknown_entity(self):
        """POST record stop for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/rosbag/record/stop",
            )

        assert resp.status_code == 404

    def test_record_status_unknown_entity(self):
        """GET record status for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/rosbag/record/status")

        assert resp.status_code == 404

    def test_download_unknown_entity(self):
        """GET download for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/rosbag/download/test_bag")

        assert resp.status_code == 404

    def test_play_start_unknown_entity(self):
        """POST play start for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/rosbag/play/start",
                json={"bag_name": "test"},
            )

        assert resp.status_code == 404

    def test_play_stop_unknown_entity(self):
        """POST play stop for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/rosbag/play/stop",
            )

        assert resp.status_code == 404


# ===================================================================
# Entity Manager Unavailable — 503
# ===================================================================


class TestEntityManagerUnavailable:
    """503 when entity manager is not initialized."""

    def test_rosbag_list_no_manager(self):
        """Rosbag list returns 503 when manager is None."""
        app = FastAPI()
        app.include_router(entity_rosbag_router)

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/rosbag/list")

        assert resp.status_code == 503

    def test_record_start_no_manager(self):
        """Record start returns 503 when manager is None."""
        app = FastAPI()
        app.include_router(entity_rosbag_router)

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/rosbag/record/start",
                json={"profile": "default"},
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
            resp = client.get("/api/entities/arm1/rosbag/list")

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
            resp = client.get("/api/entities/arm1/rosbag/record/status")

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
            resp = client.get("/api/entities/arm1/rosbag/list")

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
                "/api/entities/arm1/rosbag/record/start",
                json={"profile": "default"},
            )

        assert resp.status_code == 502
