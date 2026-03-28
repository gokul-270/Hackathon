#!/usr/bin/env python3
"""Tests for RunController - central run coordinator for dual-arm cotton-picking scenario."""

import json

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paired_scenario():
    """Two arms, one paired step."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_only_arm1_scenario():
    """Only arm1 steps."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.4, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_only_arm2_scenario():
    """Only arm2 steps."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.4, "cam_y": -0.070, "cam_z": 0.0},
        ]
    }


def _make_same_step_paired_scenario():
    """Both arms at the same step_id (paired execution)."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_solo_tail_scenario():
    """arm1 has steps 0+1, arm2 only has step 0 (solo tail for arm1 at step 1)."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.070, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.4, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_close_j4_paired_scenario():
    """Both arms at step 0 with cam_z values that produce j4 within 0.05m of each other.

    FK note: j4 = ay_absolute = camera_to_arm(cam_z) + j4_pos.  cam_z drives j4 because
    the yanthra_link rotation maps camera-Z directly onto arm-Y.  cam_y maps to arm-Z (j3
    geometry) and does NOT affect j4.  cam_z=0.25 and cam_z=0.27 produce j4 separation
    of ~0.02 m, well within the 0.05 m blocking threshold.
    """
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
        ]
    }


# ---------------------------------------------------------------------------
# load_scenario tests
# ---------------------------------------------------------------------------


def test_load_scenario_with_valid_data_does_not_raise():
    """load_scenario with a valid scenario dict does not raise any exception."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_paired_scenario())  # must not raise


# ---------------------------------------------------------------------------
# run() tests - solo arm1
# ---------------------------------------------------------------------------


def test_run_with_only_arm1_steps_returns_correct_total_steps():
    """run() with only arm1 steps reports total_steps equal to the number of unique step_ids."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_only_arm1_scenario())
    summary = rc.run()
    assert summary["total_steps"] == 2


# ---------------------------------------------------------------------------
# run() tests - solo arm2
# ---------------------------------------------------------------------------


def test_run_with_only_arm2_steps_returns_correct_total_steps():
    """run() with only arm2 steps reports total_steps equal to the number of unique step_ids."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_only_arm2_scenario())
    summary = rc.run()
    assert summary["total_steps"] == 2


# ---------------------------------------------------------------------------
# run() tests - paired (both arms at same step_id)
# ---------------------------------------------------------------------------


def test_run_with_paired_steps_generates_truth_monitor_observations():
    """run() with both arms at same step_id produces a non-None min_j4_distance for that step."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()
    step_reports = summary["step_reports"]
    # Both arms report at step_id 0; min_j4_distance must not be None
    reports_for_step0 = [r for r in step_reports if r["step_id"] == 0]
    assert all(r["min_j4_distance"] is not None for r in reports_for_step0)


# ---------------------------------------------------------------------------
# run() tests - solo tail
# ---------------------------------------------------------------------------


def test_run_solo_tail_step_has_none_min_j4_distance_for_solo_step():
    """Solo-tail step (only one arm active) reports None min_j4_distance."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_solo_tail_scenario())
    summary = rc.run()
    step_reports = summary["step_reports"]
    # step_id=1 is only for arm1 (solo tail)
    reports_for_step1 = [r for r in step_reports if r["step_id"] == 1]
    assert len(reports_for_step1) == 1
    assert reports_for_step1[0]["min_j4_distance"] is None


# ---------------------------------------------------------------------------
# run() tests - unrestricted mode never blocks j5
# ---------------------------------------------------------------------------


def test_run_in_unrestricted_mode_never_blocks_j5():
    """In unrestricted mode no step report has j5_blocked=True."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(_make_close_j4_paired_scenario())
    summary = rc.run()
    assert all(not r["j5_blocked"] for r in summary["step_reports"])


# ---------------------------------------------------------------------------
# run() tests - baseline_j5_block_skip mode blocks j5 when arms laterally close
# ---------------------------------------------------------------------------


def test_run_in_baseline_j5_block_skip_mode_blocks_j5_when_arms_close():
    """In baseline_j5_block_skip mode, j5_blocked is True when arms are within 0.05m."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    rc = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP)
    rc.load_scenario(_make_close_j4_paired_scenario())
    summary = rc.run()
    assert summary["steps_with_j5_blocked"] > 0


# ---------------------------------------------------------------------------
# get_json_report tests
# ---------------------------------------------------------------------------


def test_get_json_report_returns_valid_json_string_after_run():
    """get_json_report() returns a valid JSON string after run() has been called."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_paired_scenario())
    rc.run()
    json_str = rc.get_json_report()
    parsed = json.loads(json_str)  # must not raise
    assert "mode" in parsed


# ---------------------------------------------------------------------------
# reset tests
# ---------------------------------------------------------------------------


def test_reset_clears_state_so_subsequent_run_produces_fresh_summary():
    """After reset(), a subsequent run() on a new scenario returns a fresh summary."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_only_arm1_scenario())
    first_summary = rc.run()

    rc.reset()
    rc.load_scenario(_make_only_arm2_scenario())
    second_summary = rc.run()

    # Both have 2 steps; but step_reports should reflect the NEW scenario (arm2 only)
    assert second_summary["total_steps"] == 2
    arm_ids_in_second = {r["arm_id"] for r in second_summary["step_reports"]}
    assert arm_ids_in_second == {"arm2"}


# ---------------------------------------------------------------------------
# Integration / E2E tests
# ---------------------------------------------------------------------------


def test_e2e_unrestricted_mode_paired_scenario_has_no_j5_blocked():
    """E2E: 2-arm paired scenario in unrestricted mode produces zero j5_blocked reports.

    FK note: j4 is driven by cam_z (camera-Z maps to arm-Y via the yanthra_link rotation).
    arm1 cam_z=0.25 → j4≈-0.150 m, arm2 cam_z=0.35 → j4≈-0.250 m.
    Lateral separation ≈ 0.10 m > 0.05 m threshold, so even in blocking mode j5 would not
    be suppressed.  In unrestricted mode it is definitely never suppressed.
    """
    from run_controller import RunController
    from baseline_mode import BaselineMode

    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.35},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.35},
        ]
    }
    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(scenario)
    summary = rc.run()
    j5_blocked_count = sum(1 for r in summary["step_reports"] if r["j5_blocked"])
    assert j5_blocked_count == 0


def test_e2e_baseline_j5_block_skip_mode_blocks_j5_when_arms_laterally_close():
    """E2E: baseline_j5_block_skip blocks j5 when arms have j4 within 0.05m of each other.

    FK note: j4 is driven by cam_z (camera-Z maps to arm-Y via the yanthra_link rotation).
    cam_z=0.25 → j4≈-0.150 m, cam_z=0.27 → j4≈-0.170 m.  Lateral separation ≈ 0.02 m,
    which is less than the 0.05 m blocking threshold, so j5 must be zeroed.
    Both steps are reachable (j5≈0.128 m > 0) so the block condition can fire.
    """
    from run_controller import RunController
    from baseline_mode import BaselineMode

    # cam_z=0.25 → j4≈-0.150 m, cam_z=0.27 → j4≈-0.170 m (separation ~0.02 m < 0.05 m)
    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
        ]
    }
    rc = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP)
    rc.load_scenario(scenario)
    summary = rc.run()
    j5_blocked_count = sum(1 for r in summary["step_reports"] if r["j5_blocked"])
    assert j5_blocked_count > 0
