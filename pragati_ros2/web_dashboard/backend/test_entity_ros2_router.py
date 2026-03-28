"""Unit tests for entity_ros2_router — entity-scoped ROS2 & logs proxy routes.

Tests cover:
- 2.1: GET /api/entities/{id}/ros2/topics (local + remote)
- 2.2: GET /api/entities/{id}/ros2/topics/{name}/echo (SSE, local 501, remote proxy)
- 2.3: GET /api/entities/{id}/ros2/services (local + remote)
- 2.4: POST /api/entities/{id}/ros2/services/{name}/call (local + remote)
- 2.5: GET /api/entities/{id}/ros2/nodes (local + remote)
- 2.6: GET /api/entities/{id}/ros2/nodes/{name} (local + remote)
- 2.7: POST /api/entities/{id}/ros2/nodes/{name}/lifecycle/{transition}
- 2.8: GET /api/entities/{id}/ros2/parameters (local + remote)
-      PUT /api/entities/{id}/ros2/parameters/{node} (local + remote)
- 2.10: GET /api/entities/{id}/logs (local + remote)
-       GET /api/entities/{id}/logs/{name}/tail (SSE, local 501, remote proxy)
- Errors: 404, 502, 503

All httpx calls are mocked — no real network needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity
from backend.entity_ros2_router import entity_ros2_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(
    entities: dict[str, Entity] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal FastAPI app with entity_ros2_router wired up."""
    app = FastAPI()
    app.include_router(entity_ros2_router)

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


def _mock_httpx_get(mock_httpx, payload: dict):
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


async def _async_iter(items):
    """Convert a list to an async iterator for mocking aiter_lines()."""
    for item in items:
        yield item


def _mock_httpx_post(mock_httpx, payload: dict):
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


def _mock_httpx_put(mock_httpx, payload: dict):
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


MODULE = "backend.entity_ros2_router"
HELPERS_MODULE = "backend.entity_proxy_helpers"


# ===================================================================
# 2.1 — GET /api/entities/{id}/ros2/topics
# ===================================================================


class TestEntityRos2Topics:
    """GET /api/entities/{entity_id}/ros2/topics"""

    def test_local_topics_uses_ros2_monitor(self):
        """Local entity topics calls ros2_monitor.get_topics()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_topics = [
            {
                "name": "/joint_states",
                "type": "sensor_msgs/msg/JointState",
                "publisher_count": 1,
                "subscriber_count": 2,
            },
            {
                "name": "/cmd_vel",
                "type": "geometry_msgs/msg/Twist",
                "publisher_count": 0,
                "subscriber_count": 1,
            },
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.get_topics", return_value=mock_topics),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/topics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert len(data["data"]) == 2
        assert data["data"][0]["name"] == "/joint_states"

    def test_remote_topics_proxied_to_agent(self):
        """Remote entity topics proxies GET /ros2/topics to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = [
            {"name": "/joint_states", "type": "sensor_msgs/msg/JointState"},
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/topics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# 2.2 — GET /api/entities/{id}/ros2/topics/{name}/echo (SSE)
# ===================================================================


class TestEntityRos2TopicEcho:
    """GET /api/entities/{entity_id}/ros2/topics/{name}/echo"""

    def test_local_topic_echo_returns_501(self):
        """Local entity topic echo returns 501 (not yet implemented)."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/topics/joint_states/echo")

        assert resp.status_code == 501

    def test_local_topic_echo_slashed_name_returns_501(self):
        """Local topic echo with slashed topic name returns 501."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/topics//sensor/imu/data/echo")

        assert resp.status_code == 501


# ===================================================================
# 2.3 — GET /api/entities/{id}/ros2/services
# ===================================================================


class TestEntityRos2Services:
    """GET /api/entities/{entity_id}/ros2/services"""

    def test_local_services_uses_ros2_monitor(self):
        """Local entity services calls ros2_monitor.get_services()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_services = [
            {"name": "/emergency_stop", "type": "std_srvs/srv/Trigger"},
            {"name": "/joint_homing", "type": "std_srvs/srv/Trigger"},
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.get_services", return_value=mock_services),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/services")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert len(data["data"]) == 2
        assert data["data"][0]["name"] == "/emergency_stop"

    def test_remote_services_proxied(self):
        """Remote entity services proxies GET /ros2/services to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = [
            {"name": "/emergency_stop", "type": "std_srvs/srv/Trigger"},
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/services")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# 2.4 — POST /api/entities/{id}/ros2/services/{name}/call
# ===================================================================


class TestEntityRos2ServiceCall:
    """POST /api/entities/{entity_id}/ros2/services/{name}/call"""

    def test_local_service_call_uses_ros2_monitor(self):
        """Local entity service call uses ros2_monitor.call_service()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {
            "response": {"success": True, "message": ""},
            "duration_ms": 12.5,
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.call_service", return_value=mock_result),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/ros2/services/emergency_stop/call",
                json={
                    "service_type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["response"]["success"] is True

    def test_remote_service_call_proxied(self):
        """Remote entity service call proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "response": {"success": True, "message": ""},
            "duration_ms": 25.0,
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/services/emergency_stop/call",
                json={
                    "service_type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_service_call_runtime_error_returns_500(self):
        """Local service call that raises RuntimeError returns 500."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}.call_service",
                side_effect=RuntimeError("ROS2 not available"),
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/local/ros2/services/emergency_stop/call",
                json={
                    "service_type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )

        assert resp.status_code == 500


# ===================================================================
# 2.5 — GET /api/entities/{id}/ros2/nodes
# ===================================================================


class TestEntityRos2Nodes:
    """GET /api/entities/{entity_id}/ros2/nodes"""

    def test_local_nodes_uses_ros2_monitor(self):
        """Local entity nodes calls ros2_monitor.get_nodes()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_nodes = [
            {"name": "motor_control", "namespace": "/", "lifecycle_state": None},
            {"name": "safety_monitor", "namespace": "/", "lifecycle_state": None},
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.get_nodes", return_value=mock_nodes),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/nodes")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert len(data["data"]) == 2

    def test_remote_nodes_proxied(self):
        """Remote entity nodes proxies GET /ros2/nodes to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = [
            {"name": "motor_control", "namespace": "/"},
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/nodes")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# 2.6 — GET /api/entities/{id}/ros2/nodes/{name}
# ===================================================================


class TestEntityRos2NodeDetail:
    """GET /api/entities/{entity_id}/ros2/nodes/{name}"""

    def test_local_node_detail_found(self):
        """Local entity node detail calls ros2_monitor.get_node_detail()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_detail = {
            "name": "motor_control",
            "namespace": "/",
            "publishers": [{"name": "/joint_states", "type": "sensor_msgs/msg/JointState"}],
            "subscribers": [],
            "services": [],
            "parameters": [],
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.get_node_detail", return_value=mock_detail),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/nodes/motor_control")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["name"] == "motor_control"

    def test_local_node_detail_not_found_returns_404(self):
        """Local entity node detail returns 404 if node not found."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.get_node_detail", return_value=None),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/nodes/nonexistent")

        assert resp.status_code == 404

    def test_remote_node_detail_proxied(self):
        """Remote entity node detail proxies to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "name": "motor_control",
            "namespace": "/",
            "publishers": [],
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/nodes/motor_control")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# 2.7 — POST /api/entities/{id}/ros2/nodes/{name}/lifecycle/{transition}
# ===================================================================


class TestEntityRos2Lifecycle:
    """POST /api/entities/{id}/ros2/nodes/{name}/lifecycle/{transition}"""

    def test_local_lifecycle_transition(self):
        """Local entity lifecycle calls ros2_monitor.lifecycle_transition()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {
            "success": True,
            "node": "/motor_control",
            "transition": "activate",
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}.lifecycle_transition",
                return_value=mock_result,
            ),
        ):
            client = TestClient(app)
            resp = client.post("/api/entities/local/ros2/nodes/motor_control/lifecycle/activate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["success"] is True

    def test_remote_lifecycle_transition_proxied(self):
        """Remote entity lifecycle proxies POST to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "success": True,
            "node": "/motor_control",
            "transition": "activate",
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.post("/api/entities/arm1/ros2/nodes/motor_control/lifecycle/activate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_lifecycle_runtime_error_returns_500(self):
        """Local lifecycle that raises RuntimeError returns 500."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}.lifecycle_transition",
                side_effect=RuntimeError("ROS2 not available"),
            ),
        ):
            client = TestClient(app)
            resp = client.post("/api/entities/local/ros2/nodes/motor_control/lifecycle/activate")

        assert resp.status_code == 500

    def test_local_lifecycle_value_error_returns_400(self):
        """Local lifecycle with invalid transition returns 400."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}.lifecycle_transition",
                side_effect=ValueError("Invalid lifecycle transition: 'bogus'"),
            ),
        ):
            client = TestClient(app)
            resp = client.post("/api/entities/local/ros2/nodes/motor_control/lifecycle/bogus")

        assert resp.status_code == 400


# ===================================================================
# 2.8 — GET /api/entities/{id}/ros2/parameters
# ===================================================================


class TestEntityRos2Parameters:
    """GET /api/entities/{entity_id}/ros2/parameters"""

    def test_local_parameters_uses_ros2_monitor(self):
        """Local entity parameters calls ros2_monitor.get_parameters()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_params = {
            "nodes": [
                {
                    "name": "/motor_control",
                    "parameters": [
                        {"name": "max_velocity", "type": "double", "value": 1.0},
                    ],
                }
            ]
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.get_parameters", return_value=mock_params),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/ros2/parameters")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert "nodes" in data["data"]
        assert data["data"]["nodes"][0]["name"] == "/motor_control"

    def test_remote_parameters_proxied(self):
        """Remote entity parameters proxies GET /ros2/parameters to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {
            "nodes": [
                {"name": "/motor_control", "parameters": []},
            ]
        }

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/parameters")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# 2.8 — PUT /api/entities/{id}/ros2/parameters/{node}
# ===================================================================


class TestEntityRos2SetParameters:
    """PUT /api/entities/{entity_id}/ros2/parameters/{node}"""

    def test_local_set_parameter(self):
        """Local entity set_parameter calls ros2_monitor.set_parameter()."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {"success": True, "name": "max_velocity", "value": 2.0}

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.set_parameter", return_value=mock_result),
        ):
            client = TestClient(app)
            resp = client.put(
                "/api/entities/local/ros2/parameters/motor_control",
                json={
                    "params": [{"name": "max_velocity", "value": 2.0}],
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert data["data"]["results"][0]["success"] is True

    def test_local_set_multiple_parameters(self):
        """Local entity set_parameter handles multiple params."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        results = [
            {"success": True, "name": "max_velocity", "value": 2.0},
            {"success": True, "name": "min_velocity", "value": 0.1},
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.set_parameter", side_effect=results),
        ):
            client = TestClient(app)
            resp = client.put(
                "/api/entities/local/ros2/parameters/motor_control",
                json={
                    "params": [
                        {"name": "max_velocity", "value": 2.0},
                        {"name": "min_velocity", "value": 0.1},
                    ],
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["results"]) == 2

    def test_remote_set_parameter_proxied(self):
        """Remote entity set_parameter proxies PUT to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"results": [{"success": True, "name": "max_velocity", "value": 2.0}]}

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_put(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.put(
                "/api/entities/arm1/ros2/parameters/motor_control",
                json={
                    "params": [{"name": "max_velocity", "value": 2.0}],
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"

    def test_local_set_parameter_runtime_error_returns_500(self):
        """Local set_parameter that raises RuntimeError returns 500."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(
                f"{MODULE}.set_parameter",
                side_effect=RuntimeError("ROS2 not available"),
            ),
        ):
            client = TestClient(app)
            resp = client.put(
                "/api/entities/local/ros2/parameters/motor_control",
                json={
                    "params": [{"name": "max_velocity", "value": 2.0}],
                },
            )

        assert resp.status_code == 500


# ===================================================================
# 2.10 — GET /api/entities/{id}/logs
# ===================================================================


class TestEntityLogs:
    """GET /api/entities/{entity_id}/logs"""

    def test_local_logs_lists_files(self):
        """Local entity logs returns local log file listing."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_logs = [
            {
                "name": "latest.log",
                "path": "latest.log",
                "size_bytes": 1024,
                "modified": "2025-01-01T00:00:00",
            },
            {
                "name": "System Journal (pragati-*)",
                "path": "__journald__",
                "size_bytes": 0,
                "modified": None,
            },
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._list_local_logs", return_value=mock_logs),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/logs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "local"
        assert data["source"] == "local"
        assert len(data["data"]) == 2

    def test_remote_logs_proxied(self):
        """Remote entity logs proxies GET /logs to agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = [
            {"name": "latest.log", "path": "latest.log", "size_bytes": 512},
        ]

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/logs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"


# ===================================================================
# 2.10 — GET /api/entities/{id}/logs/{name}/tail (SSE)
# ===================================================================


class TestEntityLogTail:
    """GET /api/entities/{entity_id}/logs/{name}/tail"""

    def test_local_log_tail_streams_sse(self):
        """Local entity log tail returns 200 SSE stream via tail -f."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        # Mock asyncio.create_subprocess_exec to simulate tail -f output
        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = MagicMock(
            return_value=_async_iter([b"2025-03-10 log line 1\n", b"2025-03-10 log line 2\n"])
        )
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        # Mock _get_log_dirs to return a directory with the log file
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "latest.log"
            log_file.write_text("test log content")

            with (
                patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
                patch(f"{MODULE}.asyncio.create_subprocess_exec", return_value=mock_proc),
                patch(f"{MODULE}._get_log_dirs", return_value=[tmpdir]),
            ):
                client = TestClient(app)
                resp = client.get("/api/entities/local/logs/latest.log/tail")

            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            # Verify SSE data lines are present
            body = resp.text
            assert "data:" in body

    def test_local_log_tail_sanitizes_path(self):
        """Local log tail rejects path traversal attempts."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/local/logs/..%2F..%2Fetc%2Fpasswd/tail")

        assert resp.status_code == 400


# ===================================================================
# GET /api/entities/{id}/logs/journal/{unit} (SSE proxy)
# ===================================================================


class TestEntityJournalStream:
    """GET /api/entities/{entity_id}/logs/journal/{unit}"""

    def test_local_journal_streams_sse(self):
        """Local entity journal stream returns 200 SSE via journalctl -f."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        # Mock asyncio.create_subprocess_exec to simulate journalctl output
        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = MagicMock(
            return_value=_async_iter(
                [
                    b'{"MESSAGE":"hello","PRIORITY":"6","_SYSTEMD_UNIT":"test.service"}\n',
                ]
            )
        )
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            client = TestClient(app)
            resp = client.get("/api/entities/local/logs/journal/pragati-agent")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body

    def test_local_journal_sanitizes_unit_name(self):
        """Local journal rejects dangerous unit names."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            # Try to inject shell commands via unit name
            resp = client.get("/api/entities/local/logs/journal/; rm -rf /")

        assert resp.status_code == 400

    def test_remote_journal_proxies_sse(self):
        """Remote entity journal stream proxies SSE from agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            # Mock the SSE proxy chain:
            # httpx.AsyncClient().__aenter__() -> client
            # client.stream("GET", url).__aenter__() -> resp
            # async for line in resp.aiter_lines(): ...
            #
            # aiter_lines() must return an async iterator directly
            # (not a coroutine), so use MagicMock, not AsyncMock.
            mock_resp = MagicMock()
            mock_resp.aiter_lines = MagicMock(
                return_value=_async_iter(
                    [
                        'data: {"MESSAGE":"hello","PRIORITY":"6"}',
                        "",
                    ]
                )
            )
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_client = MagicMock()
            mock_client.stream = MagicMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.Timeout = httpx.Timeout

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/logs/journal/pragati-agent")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # Verify SSE double-newline termination (RFC 8895).
        # _proxy_sse must emit "\n\n" after each data line, not just "\n".
        body = resp.text
        assert "data:" in body
        # Every data line must be followed by a blank line (\n\n).
        # If only \n is used, consecutive data lines would merge into one
        # multi-line SSE field — wrong behaviour.
        import re as _re

        data_events = _re.findall(r"data:[^\n]*\n\n", body)
        assert (
            len(data_events) >= 1
        ), f"Expected SSE events terminated by \\n\\n, got body: {body!r}"

    def test_nonexistent_entity_returns_404(self):
        """Journal stream on unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/logs/journal/pragati-agent")

        assert resp.status_code == 404


# ===================================================================
# Error cases
# ===================================================================


class TestEntityRos2Errors:
    """Cross-cutting error scenarios: 404, 502, 503."""

    def test_nonexistent_entity_returns_404(self):
        """Request for unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/ros2/topics")

        assert resp.status_code == 404

    def test_entity_manager_unavailable_returns_503(self):
        """If entity manager not initialized, return 503."""
        app = FastAPI()
        app.include_router(entity_ros2_router)

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/topics")

        assert resp.status_code == 503

    def test_remote_agent_unreachable_returns_502(self):
        """If remote agent is unreachable, return 502."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/topics")

        assert resp.status_code == 502

    def test_remote_agent_bad_status_returns_502(self):
        """If remote agent returns non-200 status, return 502."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.json.return_value = {}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/nodes")

        assert resp.status_code == 502

    def test_404_on_nonexistent_entity_for_service_call(self):
        """POST service call on unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/unknown/ros2/services/foo/call",
                json={"service_type": "std_srvs/srv/Trigger", "request": {}},
            )

        assert resp.status_code == 404

    def test_404_on_nonexistent_entity_for_logs(self):
        """GET logs on unknown entity returns 404."""
        app, mgr = _make_app({})

        with patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr):
            client = TestClient(app)
            resp = client.get("/api/entities/unknown/logs")

        assert resp.status_code == 404


# ===================================================================
# Regression — leading-slash node name in PUT parameter save
# ===================================================================


class TestParameterSaveNodeNameNormalization:
    """Verify PUT /api/entities/{id}/ros2/parameters/{node} normalizes node names.

    Root cause of the param-save bug: the frontend sent node names with a
    leading slash (e.g. /cotton_detection_node) which, when percent-encoded
    as %2F, caused FastAPI to return 404.  The backend must normalize the
    node name so that both slashed and bare names resolve correctly.

    Since FastAPI cannot route %2F in path params, the primary fix is in the
    frontend.  These tests verify the backend's *defensive* normalization:
    - Local: set_parameter always gets exactly one leading slash
    - Remote: proxy URL never has double-slashes
    """

    def test_local_put_bare_name_gets_single_leading_slash(self):
        """Local: bare 'motor_control' → set_parameter('/motor_control', ...)."""
        local = _local_entity()
        app, mgr = _make_app({"local": local})

        mock_result = {"success": True, "name": "max_velocity", "value": 2.0}

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.set_parameter", return_value=mock_result) as mock_set,
        ):
            client = TestClient(app)
            resp = client.put(
                "/api/entities/local/ros2/parameters/motor_control",
                json={"params": [{"name": "max_velocity", "value": 2.0}]},
            )

        assert resp.status_code == 200
        # set_parameter must receive node_name with exactly one leading slash
        mock_set.assert_called_once_with(
            node_name="/motor_control",
            param_name="max_velocity",
            value=2.0,
        )

    def test_remote_put_bare_name_proxy_url_has_no_double_slash(self):
        """Remote: bare 'cotton_detection_node' → proxy to /ros2/parameters/cotton_detection_node."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        agent_payload = {"results": [{"success": True, "name": "confidence", "value": 0.85}]}

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            mock_client = _mock_httpx_put(mock_httpx, agent_payload)
            client = TestClient(app)
            resp = client.put(
                "/api/entities/arm1/ros2/parameters/cotton_detection_node",
                json={"params": [{"name": "confidence", "value": 0.85}]},
            )

        assert resp.status_code == 200
        # Verify the proxy URL sent to the agent has no double-slash
        call_args = mock_client.put.call_args
        proxy_url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        # Split on :// to ignore the scheme double-slash (http://)
        path_part = proxy_url.split("://", 1)[-1]
        assert "//" not in path_part, f"Proxy URL has double-slash: {proxy_url}"

    @pytest.mark.asyncio
    async def test_handler_local_normalizes_slashed_node_name(self):
        """Direct handler call: node_name with leading slash → set_parameter('/node', ...)."""
        from backend.entity_ros2_router import put_entity_ros2_parameters, SetParametersRequest

        local = _local_entity()
        mock_result = {"success": True, "name": "confidence", "value": 0.85}

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager") as mock_get_mgr,
            patch(f"{MODULE}.set_parameter", return_value=mock_result) as mock_set,
        ):
            mgr = MagicMock()
            mgr.get_entity.return_value = local
            mock_get_mgr.return_value = mgr

            body = SetParametersRequest(params=[{"name": "confidence", "value": "0.85"}])
            result = await put_entity_ros2_parameters(
                entity_id="local",
                node_name="/cotton_detection_node",
                body=body,
            )

        # Must call set_parameter with '/cotton_detection_node', NOT '//cotton_detection_node'
        mock_set.assert_called_once()
        actual_node = mock_set.call_args.kwargs.get(
            "node_name", mock_set.call_args.args[0] if mock_set.call_args.args else None
        )
        assert (
            actual_node == "/cotton_detection_node"
        ), f"Expected '/cotton_detection_node', got '{actual_node}'"

    @pytest.mark.asyncio
    async def test_handler_remote_normalizes_slashed_node_name(self):
        """Direct handler call: node_name with leading slash → proxy to /ros2/parameters/node."""
        from backend.entity_ros2_router import put_entity_ros2_parameters, SetParametersRequest

        arm = _remote_entity()
        agent_payload = {"results": [{"success": True, "name": "confidence", "value": 0.85}]}

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager") as mock_get_mgr,
            patch(
                f"{MODULE}._proxy_put", new_callable=AsyncMock, return_value=agent_payload
            ) as mock_proxy,
        ):
            mgr = MagicMock()
            mgr.get_entity.return_value = arm
            mock_get_mgr.return_value = mgr

            body = SetParametersRequest(params=[{"name": "confidence", "value": "0.85"}])
            result = await put_entity_ros2_parameters(
                entity_id="arm1",
                node_name="/cotton_detection_node",
                body=body,
            )

        # Proxy path must NOT have double slash
        mock_proxy.assert_called_once()
        proxy_path = (
            mock_proxy.call_args.args[1]
            if len(mock_proxy.call_args.args) > 1
            else mock_proxy.call_args.kwargs.get("path", "")
        )
        assert (
            proxy_path == "/ros2/parameters/cotton_detection_node"
        ), f"Expected '/ros2/parameters/cotton_detection_node', got '{proxy_path}'"


# ===================================================================
# 5.3 / 5.4 — POST /api/entities/{id}/ros2/topics/{name}/publish
# ===================================================================

_ALLOWLIST_WITH_START_SWITCH = [
    {
        "name": "/start_switch/command",
        "message_type": "std_msgs/msg/Bool",
        "label": "Start Switch",
        "default_data": {"data": False},
    }
]


class TestTopicPublish:
    """POST /api/entities/{entity_id}/ros2/topics/{name}/publish"""

    def test_topic_publish_proxies_to_agent(self):
        """Allowlisted topic is proxied to the entity agent."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})
        agent_payload = {"status": "ok"}

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_publishable_topics", return_value=_ALLOWLIST_WITH_START_SWITCH),
            patch(
                f"{MODULE}._proxy_post", new_callable=AsyncMock, return_value=agent_payload
            ) as mock_proxy,
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/topics/%2Fstart_switch%2Fcommand/publish",
                json={"data": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "arm1"
        assert data["source"] == "remote"
        mock_proxy.assert_called_once()

    def test_topic_publish_rejected_when_not_in_allowlist(self):
        """Topic not in allowlist returns 403 with error message."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_publishable_topics", return_value=_ALLOWLIST_WITH_START_SWITCH),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/topics/%2Frandom%2Ftopic/publish",
                json={"data": True},
            )

        assert resp.status_code == 403
        assert resp.json() == {"error": "Topic not in publishable allowlist"}

    def test_topic_publish_returns_502_when_agent_unreachable(self):
        """Allowlisted topic with unreachable agent returns 502."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_publishable_topics", return_value=_ALLOWLIST_WITH_START_SWITCH),
            patch(f"{HELPERS_MODULE}.httpx") as mock_httpx,
        ):
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.Timeout = httpx.Timeout

            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/topics/%2Fstart_switch%2Fcommand/publish",
                json={"data": True},
            )

        assert resp.status_code == 502

    def test_topic_publish_no_config_rejects_all(self):
        """Empty/missing publishable_topics config rejects any publish attempt with 403."""
        arm = _remote_entity()
        app, mgr = _make_app({"arm1": arm})

        # Empty allowlist — no topics configured
        with (
            patch(f"{HELPERS_MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}._get_publishable_topics", return_value=[]),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/topics/%2Fstart_switch%2Fcommand/publish",
                json={"data": True},
            )

        assert resp.status_code == 403
        assert resp.json() == {"error": "Topic not in publishable allowlist"}
