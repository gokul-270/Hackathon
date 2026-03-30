#!/usr/bin/env python3
"""
Backend tests for the 'Run All Modes' dry-run comparison feature.

Tests the FastAPI backend for:
  - POST /api/run/start-all-modes  → dry-runs modes 0-4, returns comparison
  - GET  /api/run/report/all-modes/json     → download JSON summaries
  - GET  /api/run/report/all-modes/markdown  → download comparison markdown
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Make web_ui importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from testing_backend import app  # noqa: E402

client = TestClient(app)

# Valid 5-mode names
_ALL_MODE_NAMES = {
    "unrestricted",
    "baseline_j5_block_skip",
    "geometry_block",
    "sequential_pick",
    "smart_reorder",
}

# Minimal valid scenario with paired steps
_VALID_PAYLOAD = {
    "scenario": {
        "steps": [
            {
                "step_id": 0,
                "arm_id": "arm1",
                "cam_x": 0.65,
                "cam_y": 0.0,
                "cam_z": 0.10,
            },
            {
                "step_id": 0,
                "arm_id": "arm2",
                "cam_x": 0.65,
                "cam_y": 0.0,
                "cam_z": 0.20,
            },
        ]
    },
}


@pytest.fixture(autouse=True)
def _no_gz_side_effects():
    """Suppress Gazebo side-effects so tests stay fast."""
    with (
        patch(
            "testing_backend._run_sleep", side_effect=lambda s: None
        ),
        patch(
            "testing_backend._run_spawn_cotton",
            return_value="mock_cotton",
        ),
        patch("testing_backend._run_remove_cotton"),
        patch(
            "testing_backend.subprocess.run",
            return_value=type(
                "CompletedProcess", (), {"returncode": 0}
            )(),
        ),
        patch(
            "testing_backend.time.sleep", side_effect=lambda s: None
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _reset_all_modes_result():
    """Clear global all-modes result before each test."""
    import testing_backend as tb

    tb._current_all_modes_result = None
    yield


# -------------------------------------------------------------------
# POST /api/run/start-all-modes
# -------------------------------------------------------------------


def test_start_all_modes_returns_200():
    """POST /api/run/start-all-modes returns HTTP 200."""
    resp = client.post(
        "/api/run/start-all-modes", json=_VALID_PAYLOAD
    )
    assert resp.status_code == 200


def test_start_all_modes_status_complete():
    """Response contains status: 'complete'."""
    resp = client.post(
        "/api/run/start-all-modes", json=_VALID_PAYLOAD
    )
    data = resp.json()
    assert data["status"] == "complete"


def test_start_all_modes_five_summaries():
    """Response contains summaries list with exactly 5 entries."""
    resp = client.post(
        "/api/run/start-all-modes", json=_VALID_PAYLOAD
    )
    data = resp.json()
    assert len(data["summaries"]) == 5


def test_start_all_modes_covers_all_mode_names():
    """Summary mode names cover all 5 modes."""
    resp = client.post(
        "/api/run/start-all-modes", json=_VALID_PAYLOAD
    )
    data = resp.json()
    mode_names = {s["mode"] for s in data["summaries"]}
    assert mode_names == _ALL_MODE_NAMES


def test_start_all_modes_comparison_markdown():
    """Response contains comparison_markdown with 'Comparison Report'."""
    resp = client.post(
        "/api/run/start-all-modes", json=_VALID_PAYLOAD
    )
    data = resp.json()
    assert "Comparison Report" in data["comparison_markdown"]


def test_start_all_modes_recommendation_valid_mode():
    """Response contains recommendation naming a valid mode."""
    resp = client.post(
        "/api/run/start-all-modes", json=_VALID_PAYLOAD
    )
    data = resp.json()
    assert data["recommendation"] in _ALL_MODE_NAMES


def test_start_all_modes_invalid_arm_pair_422():
    """Invalid arm_pair returns HTTP 422."""
    payload = {
        **_VALID_PAYLOAD,
        "arm_pair": ["arm1", "arm99"],
    }
    resp = client.post(
        "/api/run/start-all-modes", json=payload
    )
    assert resp.status_code == 422


# -------------------------------------------------------------------
# GET /api/run/report/all-modes/json
# -------------------------------------------------------------------


def test_report_json_returns_200_after_run():
    """GET all-modes/json returns 200 after a completed run."""
    client.post("/api/run/start-all-modes", json=_VALID_PAYLOAD)
    resp = client.get("/api/run/report/all-modes/json")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["summaries"]) == 5


def test_report_json_returns_404_before_run():
    """GET all-modes/json returns 404 before any run."""
    resp = client.get("/api/run/report/all-modes/json")
    assert resp.status_code == 404


# -------------------------------------------------------------------
# GET /api/run/report/all-modes/markdown
# -------------------------------------------------------------------


def test_report_markdown_returns_200_after_run():
    """GET all-modes/markdown returns 200 with comparison content."""
    client.post("/api/run/start-all-modes", json=_VALID_PAYLOAD)
    resp = client.get("/api/run/report/all-modes/markdown")
    assert resp.status_code == 200
    body = resp.text
    assert "Comparison Report" in body
    assert "Recommendation" in body


# -------------------------------------------------------------------
# Preset scenario integration
# -------------------------------------------------------------------

# The frontend presetMap maps select values to scenario URLs.
# These must match the actual files served by the backend.
_PRESET_MAP = {
    "contention": "/scenarios/contention_pack.json",
    "geometry": "/scenarios/geometry_pack.json",
}


@pytest.mark.parametrize("preset_key", _PRESET_MAP.keys())
def test_all_modes_with_preset_scenario(preset_key):
    """Loading a preset and running all-modes succeeds end-to-end.

    This mirrors the frontend flow:
      1. fetch(presetMap[key])  → get scenario JSON
      2. POST /api/run/start-all-modes with that scenario
    If the preset URL mapping is wrong, step 1 returns 404.
    """
    url = _PRESET_MAP[preset_key]
    load_resp = client.get(url)
    assert load_resp.status_code == 200, (
        f"Preset {preset_key!r} → {url} returned "
        f"{load_resp.status_code}"
    )
    scenario = load_resp.json()
    resp = client.post(
        "/api/run/start-all-modes",
        json={"scenario": scenario},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["summaries"]) == 5
    assert data["recommendation"] in _ALL_MODE_NAMES
