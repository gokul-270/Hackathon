#!/usr/bin/env python3
"""Tests for scenario_json module -- shared scenario JSON contract for dual-arm system."""

import pytest


# ---------------------------------------------------------------------------
# Helper: import the module under test
# ---------------------------------------------------------------------------

def _import_parse():
    from scenario_json import parse_scenario
    return parse_scenario


# ---------------------------------------------------------------------------
# Valid scenario
# ---------------------------------------------------------------------------

def test_parse_scenario_valid_input_returns_steps():
    """parse_scenario returns a list of ScenarioStep for a well-formed dict."""
    parse_scenario = _import_parse()
    data = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.01, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.25, "cam_y": 0.02, "cam_z": -0.005},
        ]
    }
    steps = parse_scenario(data)
    assert len(steps) == 2


# ---------------------------------------------------------------------------
# Empty steps list
# ---------------------------------------------------------------------------

def test_parse_scenario_empty_steps_raises_value_error():
    """parse_scenario raises ValueError when steps list is empty."""
    parse_scenario = _import_parse()
    data = {"steps": []}
    with pytest.raises(ValueError):
        parse_scenario(data)


# ---------------------------------------------------------------------------
# Duplicate step_ids
# ---------------------------------------------------------------------------

def test_parse_scenario_duplicate_step_ids_raises_value_error():
    """parse_scenario raises ValueError when two steps share the same step_id."""
    parse_scenario = _import_parse()
    data = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.0, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.25, "cam_y": 0.0, "cam_z": 0.0},
        ]
    }
    with pytest.raises(ValueError):
        parse_scenario(data)


# ---------------------------------------------------------------------------
# Invalid arm_id
# ---------------------------------------------------------------------------

def test_parse_scenario_invalid_arm_id_raises_value_error():
    """parse_scenario raises ValueError when arm_id is not 'arm1' or 'arm2'."""
    parse_scenario = _import_parse()
    data = {
        "steps": [
            {"step_id": 0, "arm_id": "arm99", "cam_x": 0.3, "cam_y": 0.0, "cam_z": 0.0},
        ]
    }
    with pytest.raises(ValueError):
        parse_scenario(data)


# ---------------------------------------------------------------------------
# Missing cam_x field
# ---------------------------------------------------------------------------

def test_parse_scenario_missing_cam_x_raises_value_error():
    """parse_scenario raises ValueError when cam_x is absent from a step."""
    parse_scenario = _import_parse()
    data = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_y": 0.0, "cam_z": 0.0},
        ]
    }
    with pytest.raises(ValueError):
        parse_scenario(data)


# ---------------------------------------------------------------------------
# Non-numeric cam_z
# ---------------------------------------------------------------------------

def test_parse_scenario_nonnumeric_cam_z_raises_value_error():
    """parse_scenario raises ValueError when cam_z is not a number."""
    parse_scenario = _import_parse()
    data = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.0, "cam_z": "bad"},
        ]
    }
    with pytest.raises(ValueError):
        parse_scenario(data)


# ---------------------------------------------------------------------------
# Zero steps (missing key)
# ---------------------------------------------------------------------------

def test_parse_scenario_missing_steps_key_raises_value_error():
    """parse_scenario raises ValueError when 'steps' key is absent (zero steps)."""
    parse_scenario = _import_parse()
    data = {}
    with pytest.raises(ValueError):
        parse_scenario(data)


# ---------------------------------------------------------------------------
# Group 1 (Phase 2): parse_scenario rejects paired-step data (by design)
# ---------------------------------------------------------------------------

def test_parse_scenario_rejects_paired_step_data_because_duplicate_step_ids():
    """parse_scenario is a single-arm sequential validator; it MUST reject paired-step
    data (two entries with the same step_id for different arms) with ValueError.

    This is the documented contract: RunController.load_scenario() constructs steps
    directly, bypassing this function, precisely because paired steps share a step_id.
    """
    parse_scenario = _import_parse()
    data = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.0, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.0, "cam_z": 0.0},
        ]
    }
    with pytest.raises(ValueError, match="duplicate step_id"):
        parse_scenario(data)


# ---------------------------------------------------------------------------
# Group 1: arm3 is a valid arm_id
# ---------------------------------------------------------------------------

def test_parse_scenario_arm3_is_valid():
    """parse_scenario accepts arm_id='arm3' without raising."""
    parse_scenario = _import_parse()
    data = {
        "steps": [
            {"step_id": 0, "arm_id": "arm3", "cam_x": 0.1, "cam_y": 0.2, "cam_z": 0.3},
        ]
    }
    steps = parse_scenario(data)
    assert len(steps) == 1
    assert steps[0].arm_id == "arm3"
