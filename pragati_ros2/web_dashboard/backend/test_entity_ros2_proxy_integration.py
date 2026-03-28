"""Integration tests for entity ROS2 proxy — full remote-entity proxy flow.

Tests verify the complete proxy chain: entity_ros2_router endpoint receives a
request for a remote entity, resolves the entity via entity_manager, proxies
the request to the RPi agent (mocked httpx), and returns a correctly-formed
response envelope with ``source: "remote"``.

Covers:
- GET /api/entities/{id}/ros2/topics       — remote proxy
- POST /api/entities/{id}/ros2/services/{name}/call — remote proxy
- GET /api/entities/{id}/ros2/nodes/{name} — remote proxy
- GET /api/entities/{id}/ros2/parameters   — remote proxy
- PUT /api/entities/{id}/ros2/parameters/{node} — remote proxy
- GET /api/entities/{id}/logs              — remote proxy
- 502 when agent is unreachable
- Response envelope always has ``source: "remote"`` for remote entities

Task 9.2 of dashboard-ros2-subtabs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity
from backend.entity_ros2_router import entity_ros2_router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_PORT = 8091
MODULE = "backend.entity_ros2_router"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_app(
    entities: dict[str, Entity] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Build a minimal FastAPI app with entity_ros2_router wired in."""
    app = FastAPI()
    app.include_router(entity_ros2_router)

    mgr = MagicMock()
    if entities is None:
        entities = {}
    mgr.get_entity.side_effect = lambda eid: entities.get(eid)
    mgr.get_all_entities.return_value = list(entities.values())
    return app, mgr


def _remote_entity(eid: str = "arm1", ip: str = "192.168.1.101") -> Entity:
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
    """Configure mock httpx for a successful async GET."""
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
    """Configure mock httpx for a successful async POST."""
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
    """Configure mock httpx for a successful async PUT."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx.AsyncClient.return_value = mock_client
    return mock_client


def _mock_httpx_unreachable(mock_httpx):
    """Configure mock httpx to raise ConnectError (agent unreachable)."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.put = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx.AsyncClient.return_value = mock_client
    return mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def remote_arm1():
    """A remote arm entity at 192.168.1.101."""
    return _remote_entity("arm1", "192.168.1.101")


@pytest.fixture()
def remote_arm2():
    """A second remote arm entity at 192.168.1.102."""
    return _remote_entity("arm2", "192.168.1.102")


# ===================================================================
# Integration test 1: GET /api/entities/arm1/ros2/topics (remote)
# ===================================================================


class TestRemoteTopicsProxy:
    """Full proxy flow for GET /api/entities/{id}/ros2/topics."""

    def test_topics_proxied_to_agent_and_envelope_correct(self, remote_arm1):
        """Request proxies to agent and response has source=remote."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_data = [
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
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            client_mock = _mock_httpx_get(mock_httpx, agent_data)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/topics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 2
        assert body["data"][0]["name"] == "/joint_states"

        # Verify httpx was called with the correct agent URL
        client_mock.get.assert_awaited_once()
        call_args = client_mock.get.call_args
        url = call_args[0][0]
        assert "192.168.1.101" in url
        assert str(AGENT_PORT) in url
        assert "/ros2/topics" in url

    def test_topics_proxy_different_entity_ip(self, remote_arm2):
        """Proxy uses the entity's IP address correctly."""
        app, mgr = _create_test_app({"arm2": remote_arm2})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            client_mock = _mock_httpx_get(mock_httpx, [])
            client = TestClient(app)
            resp = client.get("/api/entities/arm2/ros2/topics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm2"
        assert body["source"] == "remote"

        call_url = client_mock.get.call_args[0][0]
        assert "192.168.1.102" in call_url


# ===================================================================
# Integration test 2: POST /api/entities/arm1/ros2/services/{name}/call
# ===================================================================


class TestRemoteServiceCallProxy:
    """Full proxy flow for POST .../ros2/services/{name}/call."""

    def test_service_call_proxied_to_agent(self, remote_arm1):
        """Service call proxies POST to agent with correct body."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_result = {
            "response": {"success": True, "message": "Emergency stop OK"},
            "duration_ms": 18.3,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            client_mock = _mock_httpx_post(mock_httpx, agent_result)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/services/emergency_stop/call",
                json={
                    "service_type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert body["data"]["response"]["success"] is True
        assert body["data"]["duration_ms"] == 18.3

        # Verify POST was called with correct URL + body
        client_mock.post.assert_awaited_once()
        call_url = client_mock.post.call_args[0][0]
        assert "/ros2/services/emergency_stop/call" in call_url
        call_json = client_mock.post.call_args[1].get(
            "json"
        ) or client_mock.post.call_args.kwargs.get("json")
        assert call_json["service_type"] == "std_srvs/srv/Trigger"

    def test_service_call_with_nested_request_body(self, remote_arm1):
        """Service call forwards arbitrary request body to agent."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_result = {
            "response": {"success": True, "message": ""},
            "duration_ms": 5.0,
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, agent_result)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/services/set_joint_position/call",
                json={
                    "service_type": "custom_msgs/srv/SetPosition",
                    "request": {"joint_id": 3, "position": 1.57},
                },
            )

        assert resp.status_code == 200
        assert resp.json()["source"] == "remote"


# ===================================================================
# Integration test 3: GET /api/entities/arm1/ros2/nodes/{name}
# ===================================================================


class TestRemoteNodeDetailProxy:
    """Full proxy flow for GET .../ros2/nodes/{name}."""

    def test_node_detail_proxied_to_agent(self, remote_arm1):
        """Node detail proxies GET to agent and wraps in envelope."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_detail = {
            "name": "motor_control",
            "namespace": "/",
            "publishers": [
                {
                    "name": "/joint_states",
                    "type": "sensor_msgs/msg/JointState",
                }
            ],
            "subscribers": [{"name": "/cmd_vel", "type": "geometry_msgs/msg/Twist"}],
            "services": [],
            "parameters": [{"name": "max_velocity", "type": "double", "value": 1.0}],
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            client_mock = _mock_httpx_get(mock_httpx, agent_detail)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/nodes/motor_control")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert body["data"]["name"] == "motor_control"
        assert len(body["data"]["publishers"]) == 1

        call_url = client_mock.get.call_args[0][0]
        assert "/ros2/nodes/motor_control" in call_url


# ===================================================================
# Integration test 4: GET /api/entities/arm1/ros2/parameters
# ===================================================================


class TestRemoteParametersProxy:
    """Full proxy flow for GET .../ros2/parameters."""

    def test_parameters_proxied_to_agent(self, remote_arm1):
        """Parameters proxies GET to agent."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_params = {
            "nodes": [
                {
                    "name": "/motor_control",
                    "parameters": [
                        {
                            "name": "max_velocity",
                            "type": "double",
                            "value": 1.0,
                        },
                        {
                            "name": "kp",
                            "type": "double",
                            "value": 0.5,
                        },
                    ],
                },
                {
                    "name": "/safety_monitor",
                    "parameters": [
                        {
                            "name": "timeout_ms",
                            "type": "integer",
                            "value": 500,
                        },
                    ],
                },
            ]
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, agent_params)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/parameters")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert "nodes" in body["data"]
        assert len(body["data"]["nodes"]) == 2
        assert body["data"]["nodes"][0]["parameters"][0]["name"] == "max_velocity"


# ===================================================================
# Integration test 5: PUT /api/entities/arm1/ros2/parameters/{node}
# ===================================================================


class TestRemoteSetParametersProxy:
    """Full proxy flow for PUT .../ros2/parameters/{node}."""

    def test_set_parameters_proxied_to_agent(self, remote_arm1):
        """Set parameters proxies PUT to agent."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_result = {
            "results": [
                {"success": True, "name": "max_velocity", "value": 2.5},
                {"success": True, "name": "kp", "value": 0.8},
            ]
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            client_mock = _mock_httpx_put(mock_httpx, agent_result)
            client = TestClient(app)
            resp = client.put(
                "/api/entities/arm1/ros2/parameters/motor_control",
                json={
                    "params": [
                        {"name": "max_velocity", "value": 2.5},
                        {"name": "kp", "value": 0.8},
                    ],
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert len(body["data"]["results"]) == 2
        assert body["data"]["results"][0]["success"] is True

        # Verify PUT was called with correct URL + JSON body
        client_mock.put.assert_awaited_once()
        call_url = client_mock.put.call_args[0][0]
        assert "/ros2/parameters/motor_control" in call_url
        call_json = client_mock.put.call_args[1].get(
            "json"
        ) or client_mock.put.call_args.kwargs.get("json")
        assert len(call_json["params"]) == 2

    def test_set_single_parameter_proxied(self, remote_arm1):
        """Set a single parameter on a remote node."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_result = {
            "results": [{"success": True, "name": "timeout_ms", "value": 1000}]
        }

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_put(mock_httpx, agent_result)
            client = TestClient(app)
            resp = client.put(
                "/api/entities/arm1/ros2/parameters/safety_monitor",
                json={"params": [{"name": "timeout_ms", "value": 1000}]},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "remote"
        assert body["data"]["results"][0]["name"] == "timeout_ms"


# ===================================================================
# Integration test 6: GET /api/entities/arm1/logs
# ===================================================================


class TestRemoteLogsProxy:
    """Full proxy flow for GET .../logs."""

    def test_logs_proxied_to_agent(self, remote_arm1):
        """Logs proxies GET to agent."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        agent_logs = [
            {
                "name": "latest.log",
                "path": "latest.log",
                "size_bytes": 2048,
                "modified": "2025-06-01T12:00:00+00:00",
            },
            {
                "name": "pragati-arm.log",
                "path": "pragati-arm.log",
                "size_bytes": 10240,
                "modified": "2025-06-01T11:30:00+00:00",
            },
            {
                "name": "System Journal (pragati-*)",
                "path": "__journald__",
                "size_bytes": 0,
                "modified": None,
            },
        ]

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            client_mock = _mock_httpx_get(mock_httpx, agent_logs)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/logs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "arm1"
        assert body["source"] == "remote"
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 3
        assert body["data"][0]["name"] == "latest.log"

        call_url = client_mock.get.call_args[0][0]
        assert "/logs" in call_url


# ===================================================================
# Integration test 7: 502 when agent is unreachable
# ===================================================================


class TestAgentUnreachable502:
    """All proxy endpoints return 502 when agent cannot be reached."""

    def test_topics_returns_502_on_connect_error(self, remote_arm1):
        """GET .../ros2/topics returns 502 when agent is down."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_unreachable(mock_httpx)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/topics")

        assert resp.status_code == 502
        assert "unreachable" in resp.json()["detail"].lower()

    def test_service_call_returns_502_on_connect_error(self, remote_arm1):
        """POST .../ros2/services/{name}/call returns 502."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_unreachable(mock_httpx)
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/services/foo/call",
                json={
                    "service_type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )

        assert resp.status_code == 502

    def test_nodes_returns_502_on_connect_error(self, remote_arm1):
        """GET .../ros2/nodes returns 502 when agent is down."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_unreachable(mock_httpx)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/nodes")

        assert resp.status_code == 502

    def test_parameters_returns_502_on_connect_error(self, remote_arm1):
        """GET .../ros2/parameters returns 502 when agent is down."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_unreachable(mock_httpx)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/parameters")

        assert resp.status_code == 502

    def test_set_parameters_returns_502_on_connect_error(self, remote_arm1):
        """PUT .../ros2/parameters/{node} returns 502."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_unreachable(mock_httpx)
            client = TestClient(app)
            resp = client.put(
                "/api/entities/arm1/ros2/parameters/motor_control",
                json={"params": [{"name": "max_velocity", "value": 2.0}]},
            )

        assert resp.status_code == 502

    def test_logs_returns_502_on_connect_error(self, remote_arm1):
        """GET .../logs returns 502 when agent is down."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_unreachable(mock_httpx)
            client = TestClient(app)
            resp = client.get("/api/entities/arm1/logs")

        assert resp.status_code == 502

    def test_502_with_timeout_error(self, remote_arm1):
        """GET returns 502 on ConnectTimeout too."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            client = TestClient(app)
            resp = client.get("/api/entities/arm1/ros2/topics")

        assert resp.status_code == 502


# ===================================================================
# Integration test 8: Response envelope source field
# ===================================================================


class TestResponseEnvelopeSource:
    """All remote proxy responses must have source='remote'."""

    ENDPOINTS_GET = [
        "/api/entities/arm1/ros2/topics",
        "/api/entities/arm1/ros2/services",
        "/api/entities/arm1/ros2/nodes",
        "/api/entities/arm1/ros2/nodes/motor_control",
        "/api/entities/arm1/ros2/parameters",
        "/api/entities/arm1/logs",
    ]

    @pytest.mark.parametrize("endpoint", ENDPOINTS_GET)
    def test_get_endpoints_have_source_remote(self, endpoint, remote_arm1):
        """GET endpoints return source='remote' for remote entities."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_get(mock_httpx, {"placeholder": True})
            client = TestClient(app)
            resp = client.get(endpoint)

        assert resp.status_code == 200
        assert resp.json()["source"] == "remote"

    def test_post_service_call_has_source_remote(self, remote_arm1):
        """POST service call returns source='remote'."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_post(mock_httpx, {"response": {}})
            client = TestClient(app)
            resp = client.post(
                "/api/entities/arm1/ros2/services/test_svc/call",
                json={
                    "service_type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )

        assert resp.status_code == 200
        assert resp.json()["source"] == "remote"

    def test_put_parameters_has_source_remote(self, remote_arm1):
        """PUT parameters returns source='remote'."""
        app, mgr = _create_test_app({"arm1": remote_arm1})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            _mock_httpx_put(mock_httpx, {"results": []})
            client = TestClient(app)
            resp = client.put(
                "/api/entities/arm1/ros2/parameters/node1",
                json={"params": [{"name": "p", "value": 1}]},
            )

        assert resp.status_code == 200
        assert resp.json()["source"] == "remote"


# ===================================================================
# Integration test: Multi-entity isolation
# ===================================================================


class TestMultiEntityIsolation:
    """Requests for different entities hit different agent IPs."""

    def test_different_entities_proxy_to_different_ips(self, remote_arm1, remote_arm2):
        """arm1 and arm2 proxy to their respective IPs."""
        app, mgr = _create_test_app({"arm1": remote_arm1, "arm2": remote_arm2})

        with (
            patch(f"{MODULE}.get_entity_manager", return_value=mgr),
            patch(f"{MODULE}.httpx") as mock_httpx,
        ):
            client_mock = _mock_httpx_get(mock_httpx, [])
            client = TestClient(app)

            resp1 = client.get("/api/entities/arm1/ros2/topics")
            url1 = client_mock.get.call_args[0][0]

            resp2 = client.get("/api/entities/arm2/ros2/topics")
            url2 = client_mock.get.call_args[0][0]

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert "192.168.1.101" in url1
        assert "192.168.1.102" in url2
        assert resp1.json()["entity_id"] == "arm1"
        assert resp2.json()["entity_id"] == "arm2"
