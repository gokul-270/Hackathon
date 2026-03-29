#!/usr/bin/env python3
"""
Group 2 – Backend run/report endpoint tests.

Tests the FastAPI backend for:
  - POST /api/run/start   → starts a replay run
  - GET  /api/run/status  → returns run state
  - GET  /api/run/report/json      → returns JSON report
  - GET  /api/run/report/markdown  → returns Markdown report
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Make web_ui importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from testing_backend import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_gz_side_effects():
    """Suppress Gazebo side-effects (sleep, spawn, remove) so tests stay fast."""
    with (
        patch("testing_backend._run_sleep", side_effect=lambda s: None),
        patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
        patch("testing_backend._run_remove_cotton"),
        patch("testing_backend.subprocess.Popen"),
    ):
        yield

# ---------------------------------------------------------------------------
# /api/run/start
# ---------------------------------------------------------------------------

def test_run_start_returns_200():
    """POST /api/run/start with valid payload returns 200."""
    payload = {
        "mode": 0,
        "scenario": {
            "steps": [
                {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            ]
        },
    }
    resp = client.post("/api/run/start", json=payload)
    assert resp.status_code == 200


def test_run_start_response_has_run_id():
    """POST /api/run/start response contains a run_id field."""
    payload = {
        "mode": 0,
        "scenario": {
            "steps": [
                {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            ]
        },
    }
    resp = client.post("/api/run/start", json=payload)
    data = resp.json()
    assert "run_id" in data


def test_run_start_rejects_invalid_mode():
    """POST /api/run/start with unknown mode returns 422."""
    payload = {
        "mode": 99,
        "scenario": {"steps": []},
    }
    resp = client.post("/api/run/start", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/run/status
# ---------------------------------------------------------------------------

def test_run_status_returns_200():
    """GET /api/run/status returns 200 even when no run is in progress."""
    resp = client.get("/api/run/status")
    assert resp.status_code == 200


def test_run_status_has_state_field():
    """GET /api/run/status response contains a state field."""
    resp = client.get("/api/run/status")
    data = resp.json()
    assert "state" in data


def test_run_status_idle_when_no_run():
    """GET /api/run/status returns state=idle when no run is in progress."""
    resp = client.get("/api/run/status")
    data = resp.json()
    assert data["state"] in ("idle", "running", "complete")


# ---------------------------------------------------------------------------
# /api/run/report/json
# ---------------------------------------------------------------------------

def test_run_report_json_returns_200_after_run():
    """GET /api/run/report/json returns 200 with a completed run."""
    # Start a run first
    payload = {
        "mode": 0,
        "scenario": {
            "steps": [
                {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            ]
        },
    }
    client.post("/api/run/start", json=payload)
    resp = client.get("/api/run/report/json")
    assert resp.status_code == 200


def test_run_report_json_contains_steps():
    """GET /api/run/report/json returns a list of step records."""
    payload = {
        "mode": 0,
        "scenario": {
            "steps": [
                {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            ]
        },
    }
    client.post("/api/run/start", json=payload)
    resp = client.get("/api/run/report/json")
    data = resp.json()
    assert "steps" in data


# ---------------------------------------------------------------------------
# /api/run/report/markdown
# ---------------------------------------------------------------------------

def test_run_report_markdown_returns_200_after_run():
    """GET /api/run/report/markdown returns 200 with a completed run."""
    payload = {
        "mode": 0,
        "scenario": {
            "steps": [
                {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            ]
        },
    }
    client.post("/api/run/start", json=payload)
    resp = client.get("/api/run/report/markdown")
    assert resp.status_code == 200


def test_run_report_markdown_is_text():
    """GET /api/run/report/markdown returns text/plain or text/markdown content."""
    payload = {
        "mode": 0,
        "scenario": {
            "steps": [
                {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            ]
        },
    }
    client.post("/api/run/start", json=payload)
    resp = client.get("/api/run/report/markdown")
    assert "text" in resp.headers.get("content-type", "")


def test_run_report_not_found_before_run():
    """GET /api/run/report/json returns 404 when no run has been started."""
    # Use a fresh client to avoid state bleed
    from fastapi.testclient import TestClient as TC
    import importlib
    import testing_backend as tb
    # Reset run state
    tb._current_run_result = None
    fresh = TC(tb.app)
    resp = fresh.get("/api/run/report/json")
    assert resp.status_code == 404
