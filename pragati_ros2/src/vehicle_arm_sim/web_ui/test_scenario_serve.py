#!/usr/bin/env python3
"""
Tests for GET /scenarios/{name}.json endpoint.

The browser UI fetches preset scenario JSON files directly from the backend
at /scenarios/contention_pack.json and /scenarios/geometry_pack.json.
Without a matching route these requests return 404, silently breaking the
preset dropdown in the Scenario Run panel.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

from testing_backend import app

client = TestClient(app)


def test_contention_pack_returns_200():
    """GET /scenarios/contention_pack.json returns HTTP 200."""
    resp = client.get("/scenarios/contention_pack.json")
    assert resp.status_code == 200


def test_geometry_pack_returns_200():
    """GET /scenarios/geometry_pack.json returns HTTP 200."""
    resp = client.get("/scenarios/geometry_pack.json")
    assert resp.status_code == 200


def test_contention_pack_content_type_is_json():
    """GET /scenarios/contention_pack.json returns application/json content-type."""
    resp = client.get("/scenarios/contention_pack.json")
    assert "application/json" in resp.headers["content-type"]


def test_geometry_pack_content_type_is_json():
    """GET /scenarios/geometry_pack.json returns application/json content-type."""
    resp = client.get("/scenarios/geometry_pack.json")
    assert "application/json" in resp.headers["content-type"]


def test_contention_pack_has_steps_key():
    """GET /scenarios/contention_pack.json body contains a 'steps' list."""
    resp = client.get("/scenarios/contention_pack.json")
    data = resp.json()
    assert "steps" in data
    assert isinstance(data["steps"], list)
    assert len(data["steps"]) > 0


def test_geometry_pack_has_steps_key():
    """GET /scenarios/geometry_pack.json body contains a 'steps' list."""
    resp = client.get("/scenarios/geometry_pack.json")
    data = resp.json()
    assert "steps" in data
    assert isinstance(data["steps"], list)
    assert len(data["steps"]) > 0


def test_unknown_scenario_returns_404():
    """GET /scenarios/nonexistent.json returns HTTP 404."""
    resp = client.get("/scenarios/nonexistent.json")
    assert resp.status_code == 404
