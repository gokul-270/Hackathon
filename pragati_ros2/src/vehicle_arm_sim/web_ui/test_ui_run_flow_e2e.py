#!/usr/bin/env python3
"""
Group 4 – Phase 1 end-to-end UI run flow tests.

Verifies the full round-trip from scenario POST to report retrieval
using the FastAPI TestClient, covering the complete operator workflow:
  1. POST /api/run/start with a valid scenario + mode → 200 + run_id
  2. GET /api/run/status → state=complete after run
  3. GET /api/run/report/json → JSON report with steps + summary
  4. GET /api/run/report/markdown → Markdown report with heading
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make web_ui importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import testing_backend as tb
from testing_backend import app

client = TestClient(app)

_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
        {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.12},
        {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.22},
    ]
}


def test_e2e_full_run_returns_200_with_run_id():
    """Operator posts a scenario and gets a run_id back."""
    resp = client.post("/api/run/start", json={"mode": 0, "scenario": _SCENARIO})
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data


def test_e2e_status_complete_after_run():
    """Status endpoint reports complete after a successful run."""
    client.post("/api/run/start", json={"mode": 0, "scenario": _SCENARIO})
    resp = client.get("/api/run/status")
    assert resp.status_code == 200
    assert resp.json()["state"] == "complete"


def test_e2e_json_report_accessible_after_run():
    """JSON report is accessible after a run and contains steps + summary."""
    client.post("/api/run/start", json={"mode": 1, "scenario": _SCENARIO})
    resp = client.get("/api/run/report/json")
    assert resp.status_code == 200
    data = resp.json()
    assert "steps" in data
    assert "summary" in data


def test_e2e_markdown_report_accessible_after_run():
    """Markdown report is accessible after a run and contains a heading."""
    client.post("/api/run/start", json={"mode": 2, "scenario": _SCENARIO})
    resp = client.get("/api/run/report/markdown")
    assert resp.status_code == 200
    text = resp.text
    assert "#" in text


def test_e2e_all_four_modes_complete_successfully():
    """All four modes can be run end-to-end without error."""
    for mode in range(4):
        resp = client.post("/api/run/start", json={"mode": mode, "scenario": _SCENARIO})
        assert resp.status_code == 200, f"mode={mode} failed"
        status = client.get("/api/run/status").json()
        assert status["state"] == "complete", f"mode={mode} did not complete"


def test_e2e_report_not_available_before_any_run():
    """Before any run, JSON report returns 404."""
    tb._current_run_result = None
    fresh_client = TestClient(app)
    resp = fresh_client.get("/api/run/report/json")
    assert resp.status_code == 404


def test_e2e_json_report_summary_mode_matches_requested():
    """The JSON report summary mode matches the mode that was run."""
    client.post("/api/run/start", json={"mode": 3, "scenario": _SCENARIO})
    data = client.get("/api/run/report/json").json()
    assert data["summary"]["mode"] == "overlap_zone_wait"
