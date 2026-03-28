"""Tests for the parameter aggregation API.

Validates GET /api/parameters/all endpoint:
- Multi-node aggregation (2+ nodes with different params)
- Empty nodes (node exists but has no parameters)
- Error handling (unreachable node returns error field, doesn't crash)
- Response structure validation
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.parameter_api import parameter_router


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture()
def client():
    """FastAPI test client with only the parameter router."""
    app = FastAPI()
    app.include_router(parameter_router)
    return TestClient(app)


# -----------------------------------------------------------------
# Helper: build a fake per-node parameter result
# -----------------------------------------------------------------


def _make_node_params(node_name, params_dict, error=None):
    """Build a dict matching NodeLifecycleService.get_node_parameters output."""
    result = {
        "node_name": node_name,
        "parameters": params_dict,
        "parameter_count": len(params_dict),
        "timestamp": "2026-03-07T10:00:00+00:00",
    }
    if error:
        result["error"] = error
    return result


# -----------------------------------------------------------------
# Tests
# -----------------------------------------------------------------


class TestGetAllParameters:
    """Tests for GET /api/parameters/all."""

    def test_multi_node_aggregation(self, client):
        """Two nodes with different parameters are aggregated correctly."""
        mock_nodes = ["/node_a", "/node_b"]
        mock_params = {
            "/node_a": _make_node_params(
                "/node_a",
                {
                    "max_speed": 1.5,
                    "enabled": True,
                },
            ),
            "/node_b": _make_node_params(
                "/node_b",
                {
                    "timeout_ms": 500,
                },
            ),
        }

        async def fake_get_params(node_name):
            return mock_params[node_name]

        with (
            patch(
                "backend.parameter_api.list_known_nodes",
                return_value=mock_nodes,
            ),
            patch(
                "backend.parameter_api.get_node_parameters",
                side_effect=fake_get_params,
            ),
        ):
            resp = client.get("/api/parameters/all")

        assert resp.status_code == 200
        data = resp.json()

        # Top-level keys: both nodes present
        assert "/node_a" in data
        assert "/node_b" in data

        # node_a params
        assert data["/node_a"]["parameters"]["max_speed"] == 1.5
        assert data["/node_a"]["parameters"]["enabled"] is True
        assert data["/node_a"]["parameter_count"] == 2

        # node_b params
        assert data["/node_b"]["parameters"]["timeout_ms"] == 500
        assert data["/node_b"]["parameter_count"] == 1

    def test_empty_node_has_no_parameters(self, client):
        """A node that exists but has zero parameters."""
        mock_nodes = ["/empty_node"]
        mock_params = {
            "/empty_node": _make_node_params("/empty_node", {}),
        }

        async def fake_get_params(node_name):
            return mock_params[node_name]

        with (
            patch(
                "backend.parameter_api.list_known_nodes",
                return_value=["/empty_node"],
            ),
            patch(
                "backend.parameter_api.get_node_parameters",
                side_effect=fake_get_params,
            ),
        ):
            resp = client.get("/api/parameters/all")

        assert resp.status_code == 200
        data = resp.json()
        assert "/empty_node" in data
        assert data["/empty_node"]["parameters"] == {}
        assert data["/empty_node"]["parameter_count"] == 0

    def test_unreachable_node_returns_error_field(self, client):
        """An unreachable node gets an error entry but does not crash."""
        mock_nodes = ["/good_node", "/bad_node"]

        async def fake_get_params(node_name):
            if node_name == "/bad_node":
                raise Exception("Connection refused")
            return _make_node_params(
                "/good_node",
                {"rate_hz": 10},
            )

        with (
            patch(
                "backend.parameter_api.list_known_nodes",
                return_value=mock_nodes,
            ),
            patch(
                "backend.parameter_api.get_node_parameters",
                side_effect=fake_get_params,
            ),
        ):
            resp = client.get("/api/parameters/all")

        assert resp.status_code == 200
        data = resp.json()

        # Good node present with params
        assert "/good_node" in data
        assert data["/good_node"]["parameters"]["rate_hz"] == 10

        # Bad node present with error info, no crash
        assert "/bad_node" in data
        assert "error" in data["/bad_node"]
        assert data["/bad_node"]["parameters"] == {}

    def test_no_nodes_returns_empty_dict(self, client):
        """When no nodes are known, the response is an empty dict."""
        with (
            patch(
                "backend.parameter_api.list_known_nodes",
                return_value=[],
            ),
            patch(
                "backend.parameter_api.get_node_parameters",
                side_effect=AsyncMock(),
            ),
        ):
            resp = client.get("/api/parameters/all")

        assert resp.status_code == 200
        assert resp.json() == {}

    def test_response_structure_per_node(self, client):
        """Each node entry has the expected keys."""
        mock_nodes = ["/struct_node"]
        mock_params = {
            "/struct_node": _make_node_params(
                "/struct_node",
                {"my_param": "hello"},
            ),
        }

        async def fake_get_params(node_name):
            return mock_params[node_name]

        with (
            patch(
                "backend.parameter_api.list_known_nodes",
                return_value=mock_nodes,
            ),
            patch(
                "backend.parameter_api.get_node_parameters",
                side_effect=fake_get_params,
            ),
        ):
            resp = client.get("/api/parameters/all")

        data = resp.json()
        node_data = data["/struct_node"]
        assert "parameters" in node_data
        assert "parameter_count" in node_data
        assert "node_name" in node_data
        assert "timestamp" in node_data
