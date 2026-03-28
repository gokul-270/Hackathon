"""Tests for Graph Introspection API endpoints (Bug 4 regression).

Verifies:
- /api/graph/nodes returns node data even when topic_graph_introspection
  capability is disabled (fallback to system_state).
- /api/graph/nodes returns a dict (not a list) in all cases so the frontend
  can index by node name.
- /api/graph/topics returns topic data when capability is disabled.
- /api/graph/edges returns edge data when capability is disabled.

ROS2 modules are mocked so tests run without a live ROS2 graph.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────────────


FAKE_SYSTEM_STATE = {
    "nodes": {
        "/arm_controller": {
            "status": "active",
            "publishers": ["/joint_states", "/arm_status"],
            "subscribers": ["/joint_commands"],
            "services": ["/arm_controller/get_state"],
            "clients": [],
        },
        "/cotton_detector": {
            "status": "active",
            "publishers": ["/detections"],
            "subscribers": ["/camera/image_raw"],
            "services": [],
            "clients": [],
        },
    },
    "topics": {
        "/joint_states": {
            "type": "sensor_msgs/msg/JointState",
            "publishers": ["/arm_controller"],
            "subscribers": ["/state_monitor"],
        },
        "/detections": {
            "type": "vision_msgs/msg/Detection2DArray",
            "publishers": ["/cotton_detector"],
            "subscribers": ["/planner"],
        },
    },
    "services": {},
    "parameters": {},
    "system_health": "ok",
    "pragati_status": {},
    "logs": [],
    "last_update": None,
}


def _make_disabled_capabilities_manager():
    """CapabilitiesManager mock where topic_graph_introspection is disabled."""
    mgr = MagicMock()
    mgr.is_enabled.side_effect = lambda cap: False
    mgr.get_server_config.return_value = True
    mgr.get_enabled_capabilities.return_value = []
    mgr.capabilities = {}
    return mgr


def _make_enabled_capabilities_manager():
    """CapabilitiesManager mock where topic_graph_introspection is enabled."""
    mgr = MagicMock()
    mgr.is_enabled.side_effect = lambda cap: cap == "topic_graph_introspection"
    mgr.get_server_config.return_value = True
    mgr.get_enabled_capabilities.return_value = ["topic_graph_introspection"]
    mgr.capabilities = {"topic_graph_introspection": True}
    return mgr


# ── /api/graph/nodes ─────────────────────────────────────────────────────


class TestGraphNodesCapabilityDisabled:
    """Bug 4: /api/graph/nodes must return data when capability is disabled."""

    def test_returns_nodes_dict_not_empty_list(self):
        """Nodes field must be a dict (keyed by node name), never an empty list.

        Root cause of Bug 4: the old code returned {"nodes": []} when the
        capability was disabled, but the frontend indexes nodes by name
        (graphNodes.nodes[nodeName]), which fails on a list.
        """
        from backend.dashboard_server import app

        disabled_mgr = _make_disabled_capabilities_manager()

        with (
            patch("backend.api_routes_operations._capabilities_manager", disabled_mgr),
            patch("backend.api_routes_operations._system_state", FAKE_SYSTEM_STATE),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/nodes")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["nodes"], dict), (
            f"nodes must be a dict, got {type(data['nodes']).__name__}: {data['nodes']}"
        )

    def test_returns_cached_system_state_nodes(self):
        """When capability is disabled, nodes come from system_state cache."""
        from backend.dashboard_server import app

        disabled_mgr = _make_disabled_capabilities_manager()

        with (
            patch("backend.api_routes_operations._capabilities_manager", disabled_mgr),
            patch("backend.api_routes_operations._system_state", FAKE_SYSTEM_STATE),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/nodes")

        data = resp.json()
        nodes = data["nodes"]
        assert "/arm_controller" in nodes
        assert "/cotton_detector" in nodes
        assert nodes["/arm_controller"]["publishers"] == ["/joint_states", "/arm_status"]
        assert nodes["/cotton_detector"]["subscribers"] == ["/camera/image_raw"]

    def test_returns_count_and_timestamp(self):
        """Response must include count and timestamp fields."""
        from backend.dashboard_server import app

        disabled_mgr = _make_disabled_capabilities_manager()

        with (
            patch("backend.api_routes_operations._capabilities_manager", disabled_mgr),
            patch("backend.api_routes_operations._system_state", FAKE_SYSTEM_STATE),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/nodes")

        data = resp.json()
        assert data["count"] == 2
        assert "timestamp" in data

    def test_no_error_field_in_response(self):
        """Fallback response must not contain an error field."""
        from backend.dashboard_server import app

        disabled_mgr = _make_disabled_capabilities_manager()

        with (
            patch("backend.api_routes_operations._capabilities_manager", disabled_mgr),
            patch("backend.api_routes_operations._system_state", FAKE_SYSTEM_STATE),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/nodes")

        data = resp.json()
        assert "error" not in data, (
            f"Fallback path should not return an error, got: {data.get('error')}"
        )

    def test_empty_system_state_returns_empty_dict(self):
        """When system_state has no nodes, return empty dict (not empty list)."""
        from backend.dashboard_server import app

        disabled_mgr = _make_disabled_capabilities_manager()
        empty_state = {
            "nodes": {},
            "topics": {},
            "services": {},
            "parameters": {},
            "system_health": "unknown",
            "pragati_status": {},
            "logs": [],
            "last_update": None,
        }

        with (
            patch("backend.api_routes_operations._capabilities_manager", disabled_mgr),
            patch("backend.api_routes_operations._system_state", empty_state),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/nodes")

        data = resp.json()
        assert data["nodes"] == {}
        assert data["count"] == 0

    def test_no_capabilities_manager_returns_fallback(self):
        """When capabilities_manager is None, still return system_state data."""
        from backend.dashboard_server import app

        with (
            patch("backend.api_routes_operations._capabilities_manager", None),
            patch("backend.api_routes_operations._system_state", FAKE_SYSTEM_STATE),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/nodes")

        data = resp.json()
        assert isinstance(data["nodes"], dict)
        assert len(data["nodes"]) == 2


# ── /api/graph/topics ────────────────────────────────────────────────────


class TestGraphTopicsCapabilityDisabled:
    """graph/topics must return data when capability is disabled."""

    def test_returns_topics_from_system_state(self):
        """When capability is disabled, topics come from system_state cache."""
        from backend.dashboard_server import app

        disabled_mgr = _make_disabled_capabilities_manager()

        with (
            patch("backend.api_routes_operations._capabilities_manager", disabled_mgr),
            patch("backend.api_routes_operations._system_state", FAKE_SYSTEM_STATE),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/topics")

        data = resp.json()
        topics = data["topics"]
        assert isinstance(topics, dict)
        assert "/joint_states" in topics
        assert "/detections" in topics
        assert topics["/joint_states"]["type"] == "sensor_msgs/msg/JointState"
        assert data["count"] == 2


# ── /api/graph/edges ─────────────────────────────────────────────────────


class TestGraphEdgesCapabilityDisabled:
    """graph/edges must return data when capability is disabled."""

    def test_returns_edges_from_system_state(self):
        """When capability is disabled, edges are derived from topic fallback."""
        from backend.dashboard_server import app

        disabled_mgr = _make_disabled_capabilities_manager()

        with (
            patch("backend.api_routes_operations._capabilities_manager", disabled_mgr),
            patch("backend.api_routes_operations._system_state", FAKE_SYSTEM_STATE),
        ):
            client = TestClient(app)
            resp = client.get("/api/graph/edges")

        data = resp.json()
        edges = data["edges"]
        assert isinstance(edges, list)
        # Our fake data has 2 topics each with 1 publisher and 1 subscriber = 2 edges
        assert len(edges) == 2

        # Verify edge structure
        edge_topics = {e["topic"] for e in edges}
        assert "/joint_states" in edge_topics
        assert "/detections" in edge_topics
