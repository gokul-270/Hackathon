#!/usr/bin/env python3
"""Group 3 – Per-arm outcome reporting tests (TDD).

Tests that:
3.1  JsonReporter step reports include terminal_status and pick_completed fields.
3.2  RunController emits correct completed, blocked, and skipped outcomes.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from json_reporter import StepReport, JsonReporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_step(
    step_id=1,
    arm_id="arm1",
    terminal_status="completed",
    pick_completed=True,
    executed_in_gazebo=True,
    j5_blocked=False,
    skipped=False,
):
    return StepReport(
        step_id=step_id,
        arm_id=arm_id,
        mode="unrestricted",
        candidate_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        j5_blocked=j5_blocked,
        near_collision=False,
        collision=False,
        min_j4_distance=None,
        skipped=skipped,
        terminal_status=terminal_status,
        pick_completed=pick_completed,
        executed_in_gazebo=executed_in_gazebo,
    )


# ---------------------------------------------------------------------------
# 3.1 JsonReporter includes terminal_status and pick_completed in step reports
# ---------------------------------------------------------------------------


def test_json_reporter_step_report_includes_terminal_status_field():
    """step_reports in the JSON summary must include terminal_status for each step."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(terminal_status="completed"))
    summary = reporter.build_run_summary("unrestricted", total_steps=1)
    assert "terminal_status" in summary["step_reports"][0]
    assert summary["step_reports"][0]["terminal_status"] == "completed"


def test_json_reporter_step_report_includes_pick_completed_field():
    """step_reports in the JSON summary must include pick_completed for each step."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(pick_completed=True))
    summary = reporter.build_run_summary("unrestricted", total_steps=1)
    assert "pick_completed" in summary["step_reports"][0]
    assert summary["step_reports"][0]["pick_completed"] is True


def test_json_reporter_step_report_blocked_has_pick_completed_false():
    """A blocked step report must have pick_completed=False."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(terminal_status="blocked", pick_completed=False, j5_blocked=True))
    summary = reporter.build_run_summary("baseline_j5_block_skip", total_steps=1)
    assert summary["step_reports"][0]["pick_completed"] is False
    assert summary["step_reports"][0]["terminal_status"] == "blocked"


def test_json_reporter_step_report_skipped_has_terminal_status_skipped():
    """A skipped step report must have terminal_status='skipped'."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(terminal_status="skipped", pick_completed=False, skipped=True))
    summary = reporter.build_run_summary("sequential_pick", total_steps=1)
    assert summary["step_reports"][0]["terminal_status"] == "skipped"
    assert summary["step_reports"][0]["pick_completed"] is False


def test_json_reporter_step_report_includes_executed_in_gazebo_field():
    """step_reports must include executed_in_gazebo field."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(executed_in_gazebo=True))
    summary = reporter.build_run_summary("unrestricted", total_steps=1)
    assert "executed_in_gazebo" in summary["step_reports"][0]
    assert summary["step_reports"][0]["executed_in_gazebo"] is True


# ---------------------------------------------------------------------------
# 3.2 RunController emits correct completed, blocked, and skipped outcomes
# ---------------------------------------------------------------------------


def test_run_controller_emits_completed_outcome_for_unrestricted_step():
    """In unrestricted mode, all steps should have terminal_status='completed'."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    mock_executor = MagicMock()
    mock_executor.execute.return_value = {
        "terminal_status": "completed",
        "pick_completed": True,
        "executed_in_gazebo": True,
    }

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=mock_executor)
    rc.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
        ]
    })
    summary = rc.run()
    for r in summary["step_reports"]:
        assert r["terminal_status"] == "completed"
        assert r["pick_completed"] is True


def test_run_controller_emits_blocked_outcome_when_mode_blocks_step():
    """RunController must emit blocked outcome via executor when mode blocks a step."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    outcomes = []

    class TrackingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            if blocked:
                outcomes.append("blocked")
                return {"terminal_status": "blocked", "pick_completed": False, "executed_in_gazebo": False}
            outcomes.append("completed")
            return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}

    close_j4_scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
        ]
    }
    rc = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP, executor=TrackingExecutor())
    rc.load_scenario(close_j4_scenario)
    summary = rc.run()

    blocked_reports = [r for r in summary["step_reports"] if r["terminal_status"] == "blocked"]
    assert len(blocked_reports) > 0
    for r in blocked_reports:
        assert r["pick_completed"] is False


def test_run_controller_step_reports_include_terminal_status_for_all_arms():
    """All step_reports in the summary must include terminal_status field."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    mock_executor = MagicMock()
    mock_executor.execute.return_value = {
        "terminal_status": "completed",
        "pick_completed": True,
        "executed_in_gazebo": True,
    }

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=mock_executor)
    rc.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.12},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.22},
        ]
    })
    summary = rc.run()

    for r in summary["step_reports"]:
        assert "terminal_status" in r
        assert "pick_completed" in r
        assert "executed_in_gazebo" in r


# ---------------------------------------------------------------------------
# S1 fix: StepReport.pick_completed must default to False (fail-safe)
# ---------------------------------------------------------------------------


def test_step_report_default_pick_completed_is_false():
    """StepReport.pick_completed must default to False, not True.

    A StepReport created without an explicit pick_completed value should
    default to False (fail-safe) rather than True (fail-open), to prevent
    future code that forgets to wire the executor from silently over-counting
    completed picks.
    """
    report = StepReport(
        step_id=1,
        arm_id="arm1",
        mode="unrestricted",
        candidate_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        j5_blocked=False,
        near_collision=False,
        collision=False,
        min_j4_distance=None,
    )
    assert report.pick_completed is False, (
        "StepReport.pick_completed must default to False (fail-safe)"
    )
