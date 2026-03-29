#!/usr/bin/env python3
"""
Group 3 – Replay/report integration tests.

Verifies that the backend wires RunController end-to-end:
  - the run produces a JSON report with the correct mode name
  - the run produces a Markdown report
  - the run result is stored and retrievable
  - four-mode comparison scenario works from the UI path
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
import testing_backend as tb
from testing_backend import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_gz_side_effects():
    """Suppress Gazebo side-effects (sleep, spawn, remove) so tests stay fast."""
    with (
        patch("testing_backend._run_sleep", side_effect=lambda s: None),
        patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
        patch("testing_backend._run_remove_cotton"),
        patch("testing_backend._publish_joint_gz"),
    ):
        yield

_SMALL_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
        {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.12},
        {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.22},
    ]
}


def _run(mode: int) -> dict:
    resp = client.post("/api/run/start", json={"mode": mode, "scenario": _SMALL_SCENARIO})
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# RunController integration
# ---------------------------------------------------------------------------

def test_run_start_invokes_run_controller_and_stores_result():
    """POST /api/run/start stores a run result accessible via /api/run/report/json."""
    _run(0)
    resp = client.get("/api/run/report/json")
    assert resp.status_code == 200
    data = resp.json()
    assert "steps" in data


def test_json_report_mode_name_matches_requested_mode():
    """The JSON report mode_name matches the mode supplied at run start."""
    mode_names = {
        0: "unrestricted",
        1: "baseline_j5_block_skip",
        2: "geometry_block",
        3: "overlap_zone_wait",
    }
    for mode, expected_name in mode_names.items():
        _run(mode)
        resp = client.get("/api/run/report/json")
        data = resp.json()
        # Each step record has a mode field
        assert any(
            s.get("mode") == expected_name for s in data.get("steps", [])
        ), f"Expected mode '{expected_name}' in steps for mode {mode}"


def test_markdown_report_produced_after_run():
    """GET /api/run/report/markdown returns a non-empty Markdown string."""
    _run(0)
    resp = client.get("/api/run/report/markdown")
    assert resp.status_code == 200
    text = resp.text
    assert len(text) > 20
    assert "#" in text  # Markdown heading present


def test_run_summary_stored_in_last_result():
    """After a run, the backend stores the run summary dict."""
    _run(1)
    assert tb._current_run_result is not None
    assert "summary" in tb._current_run_result


def test_run_result_overwritten_on_new_run():
    """Each new POST /api/run/start replaces the previous run result."""
    _run(0)
    first_run = tb._current_run_result
    _run(1)
    second_run = tb._current_run_result
    # The run result should be from the second run (mode name differs)
    assert first_run is not second_run


def test_json_report_has_run_summary_with_mode_key():
    """GET /api/run/report/json response includes a top-level summary object."""
    _run(2)
    resp = client.get("/api/run/report/json")
    data = resp.json()
    assert "summary" in data
    assert "mode" in data["summary"]
