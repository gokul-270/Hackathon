"""Tests for the Service Type introspection API (Tasks 3.1-3.3).

Verifies:
- Known service type returns correct structure
- Unknown service returns 404
- Nested message types are flattened correctly
- Response has correct schema (service_name, service_type, request, response)

ROS2/rosidl modules are mocked so tests run without a live ROS2 graph.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.service_api import service_type_router


@pytest.fixture()
def app():
    """Create a test FastAPI app with the service type router."""
    _app = FastAPI()
    _app.include_router(service_type_router)
    return _app


@pytest.fixture()
def client(app):
    return TestClient(app)


# ── Fake introspection payloads ──────────────────────────────────────────

SETBOOL_TYPE_INFO = {
    "service_name": "/test/set_bool",
    "service_type": "std_srvs/srv/SetBool",
    "request": {
        "fields": [
            {"name": "data", "type": "bool", "default": False},
        ]
    },
    "response": {
        "fields": [
            {"name": "success", "type": "bool", "default": None},
            {"name": "message", "type": "string", "default": ""},
        ]
    },
}

NESTED_TYPE_INFO = {
    "service_name": "/test/nested",
    "service_type": "example_interfaces/srv/AddTwoInts",
    "request": {
        "fields": [
            {"name": "a", "type": "int64", "default": 0},
            {"name": "b", "type": "int64", "default": 0},
            {
                "name": "metadata",
                "type": "example_interfaces/msg/Header",
                "fields": [
                    {"name": "stamp", "type": "float64", "default": 0.0},
                    {"name": "frame_id", "type": "string", "default": ""},
                ],
            },
        ]
    },
    "response": {
        "fields": [
            {"name": "sum", "type": "int64", "default": 0},
        ]
    },
}


# ── Test: known service returns correct structure ────────────────────────


class TestKnownService:
    """GET /api/services/{service_name}/type for a known service."""

    @patch("backend.service_api.introspect_service_type")
    def test_returns_correct_structure(self, mock_introspect, client):
        """Response contains service_name, service_type, request, response."""
        mock_introspect.return_value = SETBOOL_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fset_bool/type")

        assert resp.status_code == 200
        body = resp.json()
        assert body["service_name"] == "/test/set_bool"
        assert body["service_type"] == "std_srvs/srv/SetBool"
        assert "request" in body
        assert "response" in body

    @patch("backend.service_api.introspect_service_type")
    def test_request_fields(self, mock_introspect, client):
        """Request fields match expected schema."""
        mock_introspect.return_value = SETBOOL_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fset_bool/type")

        body = resp.json()
        req_fields = body["request"]["fields"]
        assert len(req_fields) == 1
        assert req_fields[0]["name"] == "data"
        assert req_fields[0]["type"] == "bool"

    @patch("backend.service_api.introspect_service_type")
    def test_response_fields(self, mock_introspect, client):
        """Response fields match expected schema."""
        mock_introspect.return_value = SETBOOL_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fset_bool/type")

        body = resp.json()
        resp_fields = body["response"]["fields"]
        assert len(resp_fields) == 2
        field_names = [f["name"] for f in resp_fields]
        assert "success" in field_names
        assert "message" in field_names


# ── Test: unknown service returns 404 ────────────────────────────────────


class TestUnknownService:
    """GET /api/services/{service_name}/type for an unknown service."""

    @patch("backend.service_api.introspect_service_type")
    def test_returns_404(self, mock_introspect, client):
        """Unknown service returns 404 with detail message."""
        mock_introspect.return_value = None

        resp = client.get("/api/services/%2Fno%2Fsuch%2Fservice/type")

        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    @patch("backend.service_api.introspect_service_type")
    def test_404_detail_contains_service_name(self, mock_introspect, client):
        """404 detail includes the requested service name for debugging."""
        mock_introspect.return_value = None

        resp = client.get("/api/services/%2Fno%2Fsuch%2Fservice/type")

        body = resp.json()
        assert "/no/such/service" in body["detail"]


# ── Test: nested message types ───────────────────────────────────────────


class TestNestedMessageTypes:
    """Nested message types are represented with sub-fields."""

    @patch("backend.service_api.introspect_service_type")
    def test_nested_fields_present(self, mock_introspect, client):
        """Nested message field contains sub-fields list."""
        mock_introspect.return_value = NESTED_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fnested/type")

        body = resp.json()
        req_fields = body["request"]["fields"]
        # Find the nested 'metadata' field
        nested = [f for f in req_fields if f["name"] == "metadata"]
        assert len(nested) == 1
        assert "fields" in nested[0]
        assert len(nested[0]["fields"]) == 2

    @patch("backend.service_api.introspect_service_type")
    def test_nested_sub_field_names(self, mock_introspect, client):
        """Nested sub-fields have correct names."""
        mock_introspect.return_value = NESTED_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fnested/type")

        body = resp.json()
        req_fields = body["request"]["fields"]
        nested = [f for f in req_fields if f["name"] == "metadata"][0]
        sub_names = [f["name"] for f in nested["fields"]]
        assert "stamp" in sub_names
        assert "frame_id" in sub_names

    @patch("backend.service_api.introspect_service_type")
    def test_nested_type_annotation(self, mock_introspect, client):
        """Nested field includes its message type."""
        mock_introspect.return_value = NESTED_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fnested/type")

        body = resp.json()
        req_fields = body["request"]["fields"]
        nested = [f for f in req_fields if f["name"] == "metadata"][0]
        assert nested["type"] == "example_interfaces/msg/Header"


# ── Test: response schema completeness ───────────────────────────────────


class TestResponseSchema:
    """Every field in the response has required keys."""

    @patch("backend.service_api.introspect_service_type")
    def test_all_fields_have_name_and_type(self, mock_introspect, client):
        """Each field dict must have at least 'name' and 'type'."""
        mock_introspect.return_value = SETBOOL_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fset_bool/type")

        body = resp.json()
        for section in ("request", "response"):
            for field in body[section]["fields"]:
                assert "name" in field, f"Missing 'name' in {section} field"
                assert "type" in field, f"Missing 'type' in {section} field"

    @patch("backend.service_api.introspect_service_type")
    def test_top_level_keys(self, mock_introspect, client):
        """Top-level response has exactly the expected keys."""
        mock_introspect.return_value = SETBOOL_TYPE_INFO

        resp = client.get("/api/services/%2Ftest%2Fset_bool/type")

        body = resp.json()
        expected_keys = {"service_name", "service_type", "request", "response"}
        assert set(body.keys()) == expected_keys
