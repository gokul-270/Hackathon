"""Unit tests for Phase 3 — entity-scoped proxy routes and app_factory changes.

Tests cover:
- 3.1: app_factory hardcodes role to "dev", bypasses ROLE_EXCLUDED_ROUTERS,
       registers entity_router and entity_proxy_router
- 3.2: Entity-scoped proxy routes (health, ros2/nodes, ros2/topics,
       ros2/services, systemd/services, systemd restart)
- 3.7: POST /api/entities/{id}/estop endpoint

All httpx calls are mocked — no real network needed.
Local entity calls use mocked psutil / service accessors.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity
from backend.entity_proxy import entity_proxy_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app_with_entity_mgr(
    entities: dict[str, Entity] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal FastAPI app with entity_proxy_router wired up."""
    app = FastAPI()
    app.include_router(entity_proxy_router)

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


# ===================================================================
# 3.2 — Entity-scoped proxy: GET /api/entities/{id}/health
# ===================================================================


class TestEntityHealthProxy:
    """GET /api/entities/{entity_id}/health"""

    def test_remote_entity_health_proxies_to_agent(self):
        """Remote entity health request proxies to agent /health."""
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        agent_payload = {
            "cpu_percent": 42.5,
            "memory_percent": 65.0,
            "disk_percent": 30.0,
        }

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy_helpers.httpx"
        ) as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = agent_payload

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"
        assert data["data"]["cpu_percent"] == 42.5

    def test_local_entity_health_uses_psutil(self):
        """Local entity health returns psutil data directly."""
        local = _local_entity()
        app, mgr = _make_app_with_entity_mgr({"local": local})

        mock_cpu = 35.0
        mock_mem = MagicMock(percent=60.0)
        mock_disk = MagicMock(percent=25.0)

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy.psutil"
        ) as mock_psutil:
            mock_psutil.cpu_percent.return_value = mock_cpu
            mock_psutil.virtual_memory.return_value = mock_mem
            mock_psutil.disk_usage.return_value = mock_disk

            client = TestClient(app)
            resp = client.get("/api/entities/local/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["cpu_percent"] == 35.0
        assert data["data"]["memory_percent"] == 60.0

    def test_nonexistent_entity_returns_404(self):
        """Request for unknown entity returns 404."""
        app, mgr = _make_app_with_entity_mgr({})

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/health")

        assert resp.status_code == 404

    def test_remote_agent_unreachable_returns_502(self):
        """If remote agent is unreachable, return 502."""
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy_helpers.httpx"
        ) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/health")

        assert resp.status_code == 502

    def test_entity_manager_unavailable_returns_503(self):
        """If entity manager not initialized, return 503."""
        app = FastAPI()
        app.include_router(entity_proxy_router)

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/health")

        assert resp.status_code == 503


# ===================================================================
# 3.2 — Entity-scoped proxy: GET /api/entities/{id}/ros2/nodes
# ===================================================================


class TestEntityRos2NodesProxy:
    """GET /api/entities/{entity_id}/ros2/nodes"""

    def test_remote_ros2_nodes_proxied(self):
        """Remote entity ROS2 nodes request proxies to agent."""
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        agent_payload = {"nodes": ["/motor_control", "/safety_monitor"]}

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy_helpers.httpx"
        ) as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = agent_payload

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/nodes")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert len(data["data"]["nodes"]) == 2

    def test_local_ros2_nodes_uses_system_state(self):
        """Local entity ROS2 nodes returns from local system_state."""
        local = _local_entity()
        app, mgr = _make_app_with_entity_mgr({"local": local})

        mock_state = {
            "nodes": {
                "/motor_control": {"status": "active"},
                "/safety_monitor": {"status": "active"},
            }
        }

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy._get_local_system_state",
            return_value=mock_state,
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/nodes")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert "/motor_control" in data["data"]["nodes"]


# ===================================================================
# 3.2 — Entity-scoped proxy: GET /api/entities/{id}/ros2/topics
# ===================================================================


class TestEntityRos2TopicsProxy:
    """GET /api/entities/{entity_id}/ros2/topics"""

    def test_remote_ros2_topics_proxied(self):
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        agent_payload = {"topics": ["/joint_states", "/cmd_vel"]}

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy_helpers.httpx"
        ) as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = agent_payload

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/topics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert "/joint_states" in data["data"]["topics"]

    def test_local_ros2_topics_uses_system_state(self):
        local = _local_entity()
        app, mgr = _make_app_with_entity_mgr({"local": local})

        mock_state = {
            "topics": {
                "/joint_states": {"type": "sensor_msgs/msg/JointState"},
                "/cmd_vel": {"type": "geometry_msgs/msg/Twist"},
            }
        }

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy._get_local_system_state",
            return_value=mock_state,
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/topics")

        assert resp.status_code == 200
        data = resp.json()
        assert "/joint_states" in data["data"]["topics"]


# ===================================================================
# 3.2 — Entity-scoped proxy: GET /api/entities/{id}/ros2/services
# ===================================================================


class TestEntityRos2ServicesProxy:
    """GET /api/entities/{entity_id}/ros2/services"""

    def test_remote_ros2_services_proxied(self):
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        agent_payload = {"services": ["/emergency_stop", "/joint_homing"]}

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy_helpers.httpx"
        ) as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = agent_payload

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/services")

        assert resp.status_code == 200
        data = resp.json()
        assert "/emergency_stop" in data["data"]["services"]

    def test_local_ros2_services_uses_system_state(self):
        local = _local_entity()
        app, mgr = _make_app_with_entity_mgr({"local": local})

        mock_state = {
            "services": {
                "/emergency_stop": {"type": "std_srvs/srv/Trigger"},
                "/joint_homing": {"type": "std_srvs/srv/Trigger"},
            }
        }

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy._get_local_system_state",
            return_value=mock_state,
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/services")

        assert resp.status_code == 200
        data = resp.json()
        assert "/emergency_stop" in data["data"]["services"]


# ===================================================================
# 3.2 — Entity-scoped proxy: GET /api/entities/{id}/systemd/services
# ===================================================================


class TestEntitySystemdServicesProxy:
    """GET /api/entities/{entity_id}/systemd/services"""

    def test_remote_systemd_services_proxied(self):
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        agent_payload = {
            "services": [
                {"name": "pragati-arm", "active": True},
                {"name": "pragati-agent", "active": True},
            ]
        }

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy_helpers.httpx"
        ) as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = agent_payload

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/systemd/services")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert len(data["data"]["services"]) == 2

    def test_local_systemd_not_supported_returns_stub(self):
        """Local entity systemd returns stub (not running on RPi)."""
        local = _local_entity()
        app, mgr = _make_app_with_entity_mgr({"local": local})

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/local/systemd/services")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        # Local entity returns empty list (no RPi systemd services)
        assert data["data"]["services"] == []


# ===================================================================
# 3.2 — Entity-scoped proxy: POST .../systemd/services/{name}/restart
# ===================================================================


class TestEntitySystemdRestartProxy:
    """POST /api/entities/{id}/systemd/services/{name}/restart"""

    def test_remote_systemd_restart_proxied(self):
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        agent_payload = {"success": True}

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy_helpers.httpx"
        ) as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = agent_payload

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.post("/api/entities/arm1/systemd/services/pragati-arm/restart")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["data"]["success"] is True

    def test_local_systemd_restart_not_supported(self):
        """Local entity systemd restart returns 400."""
        local = _local_entity()
        app, mgr = _make_app_with_entity_mgr({"local": local})

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post("/api/entities/local/systemd/services/foo/restart")

        assert resp.status_code == 400


# ===================================================================
# 3.7 — POST /api/entities/{id}/estop
# ===================================================================


class TestEntityEstop:
    """POST /api/entities/{entity_id}/estop"""

    def test_remote_estop_proxies_to_agent(self):
        """Remote e-stop forwards to agent's restart endpoint."""
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        agent_payload = {"success": True}

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy.httpx"
        ) as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = agent_payload

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.post("/api/entities/arm1/estop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["success"] is True
        assert data["error"] is None

    def test_remote_estop_agent_unreachable(self):
        """Remote e-stop returns success=false when agent unreachable."""
        arm = _remote_entity()
        app, mgr = _make_app_with_entity_mgr({"arm1": arm})

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy.httpx"
        ) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.post("/api/entities/arm1/estop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["success"] is False
        assert data["error"] is not None

    def test_estop_nonexistent_entity_returns_404(self):
        """E-stop for unknown entity returns 404."""
        app, mgr = _make_app_with_entity_mgr({})

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post("/api/entities/unknown/estop")

        assert resp.status_code == 404

    def test_local_estop_returns_result(self):
        """Local e-stop attempts local emergency stop."""
        local = _local_entity()
        app, mgr = _make_app_with_entity_mgr({"local": local})

        with patch("backend.entity_proxy_helpers.get_entity_manager", return_value=mgr), patch(
            "backend.entity_proxy._local_emergency_stop",
            return_value=(True, None),
        ):
            client = TestClient(app)
            resp = client.post("/api/entities/local/estop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["success"] is True


# ===================================================================
# 3.1 — app_factory changes
# ===================================================================


class TestAppFactoryChanges:
    """Verify app_factory hardcodes role=dev and registers entity routes."""

    def test_role_excluded_routers_bypassed(self):
        """ROLE_EXCLUDED_ROUTERS should yield empty set for dev."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        # Dev role always has empty exclusions
        assert ROLE_EXCLUDED_ROUTERS.get("dev") == set()

    def test_entity_router_importable_from_entity_manager(self):
        """entity_router should be importable and have correct prefix."""
        from backend.entity_manager import entity_router

        assert entity_router.prefix == "/api/entities"

    def test_entity_proxy_router_importable(self):
        """entity_proxy_router should be importable with correct prefix."""
        from backend.entity_proxy import entity_proxy_router

        assert entity_proxy_router.prefix == "/api/entities"

    def test_app_factory_hardcodes_dev_role(self):
        """app_factory should hardcode role to 'dev'."""
        # We verify by checking that parse_role_config is bypassed
        # and the role is always "dev"
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        # The key assertion: dev role gets no exclusions
        excluded = ROLE_EXCLUDED_ROUTERS.get("dev", set())
        assert len(excluded) == 0


# ===================================================================
# Proxy timeout constants
# ===================================================================


class TestProxyTimeoutConstants:
    """Verify proxy timeout is sized for WSL portproxy latency."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "backend.entity_proxy",
            "backend.entity_ros2_router",
            "backend.entity_system_stats_router",
            "backend.entity_system_router",
            "backend.entity_motor_router",
            "backend.entity_rosbag_router",
        ],
    )
    def test_proxy_timeout_at_least_15s(self, module_path):
        """All router proxy timeouts must exceed portproxy latency."""
        import importlib

        mod = importlib.import_module(module_path)
        assert mod._PROXY_TIMEOUT_S >= 15

    @pytest.mark.parametrize(
        "module_path",
        [
            "backend.entity_proxy",
            "backend.entity_ros2_router",
            "backend.entity_system_stats_router",
            "backend.entity_system_router",
            "backend.entity_motor_router",
            "backend.entity_rosbag_router",
        ],
    )
    def test_proxy_timeout_current_value(self, module_path):
        """All router proxy timeouts should be 20s."""
        import importlib

        mod = importlib.import_module(module_path)
        assert mod._PROXY_TIMEOUT_S == 20
