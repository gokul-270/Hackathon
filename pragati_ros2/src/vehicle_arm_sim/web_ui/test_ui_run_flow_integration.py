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
import threading
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
        patch(
            "testing_backend.subprocess.run",
            return_value=type("CompletedProcess", (), {"returncode": 0})(),
        ),
        patch("testing_backend.time.sleep", side_effect=lambda s: None),
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
        3: "sequential_pick",
        4: "smart_reorder",
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


# ---------------------------------------------------------------------------
# SSE lifecycle — second-run regression tests
# ---------------------------------------------------------------------------

def _collect_sse_events(sse_client, path: str, stop_on_run_complete: bool = True) -> list:
    """Open SSE stream and collect all events until run_complete or stream closes."""
    events = []
    try:
        with sse_client.stream("GET", path) as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    evt = json.loads(line[len("data:"):].strip())
                    events.append(evt)
                    if stop_on_run_complete and evt.get("type") == "run_complete":
                        break
    except Exception:
        pass
    return events


def test_second_run_sse_receives_events():
    """GET /api/run/events on a closed bus must reset and deliver new events.

    This exercises the fix directly: the SSE endpoint must call reset() before
    subscribe() so that the subscriber is not returned immediately on a closed bus.
    """
    import time as _time

    # Simulate end-of-run-1 state: bus is closed
    tb._event_bus.close()
    assert tb._event_bus._closed, "precondition: bus must be closed to exercise the bug"

    run2_events = []
    sse_connected = threading.Event()
    sse_done = threading.Event()

    def emit_run2_events():
        # Wait for SSE to connect (endpoint resets and subscribes)
        sse_connected.wait(timeout=2.0)
        _time.sleep(0.05)  # let subscribe() block in the generator
        tb._event_bus.emit({"type": "step_start", "step_id": 0, "arm_id": "arm1"})
        tb._event_bus.emit({"type": "run_complete", "run_id": "run2"})
        tb._event_bus.close()

    emitter = threading.Thread(target=emit_run2_events)
    emitter.start()

    import json as _json
    with TestClient(app) as sse_client:
        with sse_client.stream("GET", "/api/run/events") as resp:
            sse_connected.set()
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    evt = _json.loads(line[len("data:"):].strip())
                    run2_events.append(evt)
                    if evt.get("type") == "run_complete":
                        break

    sse_done.set()
    emitter.join(timeout=3.0)

    assert any(e.get("type") == "run_complete" for e in run2_events), (
        f"Second-run SSE received no run_complete (second-run freeze!); got: {run2_events}"
    )


def test_start_fires_before_sse_opens():
    """If run/start fires before SSE opens (no reset before subscribe), bus must still work.

    Defensive scenario: /api/run/start calls reset() as a guard. If the SSE handler
    also calls reset(), the subscriber should still receive events emitted after the
    SSE opens (even if an earlier reset cleared old queued events).
    """
    import time as _time

    # Start from clean state
    tb._event_bus.reset()

    received = []
    subscriber_started = threading.Event()
    subscriber_done = threading.Event()

    def sse_consumer():
        tb._event_bus.reset()  # SSE handler calls reset() first (the fix)
        gen = tb._event_bus.subscribe()
        subscriber_started.set()
        for evt in gen:
            received.append(evt)
        subscriber_done.set()

    # Emit run_complete BEFORE SSE opens (simulates start firing before SSE opens)
    tb._event_bus.emit({"type": "run_complete", "run_id": "pre-sse"})
    tb._event_bus.close()

    # Now SSE opens — reset() clears old events, subscriber waits for new ones
    t = threading.Thread(target=sse_consumer)
    t.start()
    subscriber_started.wait(timeout=1.0)
    _time.sleep(0.02)

    # Emit a new event after SSE opens
    tb._event_bus.emit({"type": "run_complete", "run_id": "post-sse"})
    tb._event_bus.close()

    subscriber_done.wait(timeout=2.0)
    t.join(timeout=2.0)

    # Must not hang, and must receive the post-open event
    assert not t.is_alive(), "SSE consumer hung when run/start fired before SSE opened"
    assert any(e.get("run_id") == "post-sse" for e in received), (
        f"SSE consumer did not receive post-open event; got: {received}"
    )
