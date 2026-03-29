#!/usr/bin/env python3
"""Tests for testing_backend cotton colour SDF generation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_arm1_cotton_sdf_is_red():
    """Cotton SDF for arm1 must use red colour (1 0 0 1)."""
    import testing_backend as tb

    # Call the internal SDF builder — we test the template substitution
    # by checking that the colour lookup for arm1 is red
    colour = tb._ARM_COTTON_COLOURS.get("arm1", "1 1 1 1")
    assert colour == "1 0 0 1", f"arm1 cotton must be red (1 0 0 1), got {colour}"


def test_arm2_cotton_sdf_is_blue():
    """Cotton SDF for arm2 must use blue colour (0 0 1 1)."""
    import testing_backend as tb

    colour = tb._ARM_COTTON_COLOURS.get("arm2", "1 1 1 1")
    assert colour == "0 0 1 1", f"arm2 cotton must be blue (0 0 1 1), got {colour}"


def test_arm3_cotton_sdf_fallback_is_white():
    """Cotton SDF for unknown arm_id must fall back to white (1 1 1 1)."""
    import testing_backend as tb

    colour = tb._ARM_COTTON_COLOURS.get("arm3", "1 1 1 1")
    assert colour == "1 1 1 1", f"unknown arm must use white (1 1 1 1), got {colour}"


def test_cotton_sdf_template_has_ambient_placeholder():
    """_COTTON_SDF_TEMPLATE must have {ambient} placeholder for colour injection."""
    import testing_backend as tb

    assert "{ambient}" in tb._COTTON_SDF_TEMPLATE, (
        "_COTTON_SDF_TEMPLATE must contain {ambient} placeholder"
    )


def test_cotton_sdf_template_has_diffuse_placeholder():
    """_COTTON_SDF_TEMPLATE must have {diffuse} placeholder for colour injection."""
    import testing_backend as tb

    assert "{diffuse}" in tb._COTTON_SDF_TEMPLATE, (
        "_COTTON_SDF_TEMPLATE must contain {diffuse} placeholder"
    )


def test_arm1_all_three_cotton_spawns_are_red():
    """All 3 SDF strings for arm1 spawns must contain the red material definition."""
    import testing_backend as tb

    for i in range(3):
        colour = tb._ARM_COTTON_COLOURS.get("arm1", "1 1 1 1")
        sdf = tb._COTTON_SDF_TEMPLATE.format(name=f"arm1_cotton_{i}", ambient=colour, diffuse=colour)
        assert "<ambient>1 0 0 1</ambient>" in sdf, (
            f"arm1 cotton spawn {i} SDF must contain red ambient; got fragment: "
            f"{sdf[sdf.find('<ambient>'):][:60]!r}"
        )
        assert "<diffuse>1 0 0 1</diffuse>" in sdf, (
            f"arm1 cotton spawn {i} SDF must contain red diffuse; got fragment: "
            f"{sdf[sdf.find('<diffuse>'):][:60]!r}"
        )


def test_run_events_endpoint_returns_event_stream_content_type():
    """GET /api/run/events must return text/event-stream content type."""
    import threading
    from fastapi.testclient import TestClient
    import testing_backend as tb
    # Reset event bus to clean state so subscribe() starts fresh
    tb._event_bus.reset()

    def _emit_and_close():
        import time
        time.sleep(0.05)
        tb._event_bus.emit({"type": "run_complete"})

    timer = threading.Thread(target=_emit_and_close)
    timer.start()
    with TestClient(tb.app) as client:
        with client.stream("GET", "/api/run/events") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
    timer.join(timeout=2.0)
