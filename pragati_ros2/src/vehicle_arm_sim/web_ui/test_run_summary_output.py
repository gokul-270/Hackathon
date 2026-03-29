#!/usr/bin/env python3
"""Group 4 – Run summary output tests (TDD).

Tests that:
4.1  JsonReporter summary includes completed-pick totals.
4.2  GET /api/run/report/markdown includes completed-pick summary text.
4.3  blocked and skipped remain combined while completed picks are summarized separately.
"""

import sys
from pathlib import Path

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
        executed_in_gazebo=pick_completed,
    )


# ---------------------------------------------------------------------------
# 4.1 JSON summary includes completed-pick totals
# ---------------------------------------------------------------------------


def test_run_summary_includes_completed_picks_key():
    """build_run_summary() must include 'completed_picks' in the summary dict."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(pick_completed=True))
    reporter.add_step(_make_step(step_id=2, pick_completed=True))
    summary = reporter.build_run_summary("unrestricted", total_steps=2)
    assert "completed_picks" in summary


def test_run_summary_completed_picks_counts_only_pick_completed_true():
    """completed_picks counts exactly the steps where pick_completed=True."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(step_id=1, pick_completed=True))
    reporter.add_step(_make_step(step_id=2, pick_completed=False, j5_blocked=True, terminal_status="blocked"))
    reporter.add_step(_make_step(step_id=3, pick_completed=True))
    summary = reporter.build_run_summary("baseline_j5_block_skip", total_steps=3)
    assert summary["completed_picks"] == 2


def test_run_summary_completed_picks_is_zero_when_all_blocked():
    """completed_picks is 0 when all steps are blocked."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(step_id=1, pick_completed=False, j5_blocked=True, terminal_status="blocked"))
    reporter.add_step(_make_step(step_id=2, pick_completed=False, j5_blocked=True, terminal_status="blocked"))
    summary = reporter.build_run_summary("baseline_j5_block_skip", total_steps=2)
    assert summary["completed_picks"] == 0


# ---------------------------------------------------------------------------
# 4.2 Markdown report includes completed-pick totals
# ---------------------------------------------------------------------------


def test_run_report_markdown_includes_completed_picks_text():
    """GET /api/run/report/markdown must include 'Completed picks' text."""
    from fastapi.testclient import TestClient
    import testing_backend as tb

    tb._current_run_result = None
    fresh_client = TestClient(tb.app)
    resp = fresh_client.post(
        "/api/run/start",
        json={
            "mode": 0,
            "scenario": {
                "steps": [
                    {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                    {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
                ]
            },
        },
    )
    assert resp.status_code == 200
    md_resp = fresh_client.get("/api/run/report/markdown")
    assert md_resp.status_code == 200
    md_text = md_resp.text
    # Must include completed picks in the markdown output
    assert "Completed picks" in md_text or "completed_picks" in md_text or "completed pick" in md_text.lower()


def test_run_report_json_summary_includes_completed_picks():
    """GET /api/run/report/json summary must include 'completed_picks'."""
    from fastapi.testclient import TestClient
    import testing_backend as tb

    tb._current_run_result = None
    fresh_client = TestClient(tb.app)
    fresh_client.post(
        "/api/run/start",
        json={
            "mode": 0,
            "scenario": {
                "steps": [
                    {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                    {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
                ]
            },
        },
    )
    data = fresh_client.get("/api/run/report/json").json()
    assert "completed_picks" in data["summary"]


# ---------------------------------------------------------------------------
# 4.3 blocked and skipped remain combined; completed picks are separate
# ---------------------------------------------------------------------------


def test_run_summary_blocked_or_skipped_combined_not_separately():
    """steps_with_blocked_or_skipped must equal j5_blocked + skipped combined."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(step_id=1, pick_completed=False, j5_blocked=True, terminal_status="blocked"))
    reporter.add_step(_make_step(step_id=2, pick_completed=False, skipped=True, terminal_status="skipped"))
    reporter.add_step(_make_step(step_id=3, pick_completed=True, terminal_status="completed"))
    summary = reporter.build_run_summary("sequential_pick", total_steps=3)

    # combined count = 1 blocked + 1 skipped = 2
    assert summary["steps_with_blocked_or_skipped"] == 2
    # completed picks counted separately
    assert summary["completed_picks"] == 1


def test_run_summary_completed_picks_separate_from_blocked_or_skipped():
    """completed_picks and steps_with_blocked_or_skipped are mutually exclusive."""
    reporter = JsonReporter()
    reporter.add_step(_make_step(step_id=1, pick_completed=True, terminal_status="completed"))
    reporter.add_step(_make_step(step_id=2, pick_completed=True, terminal_status="completed"))
    reporter.add_step(_make_step(step_id=3, pick_completed=False, j5_blocked=True, terminal_status="blocked"))
    reporter.add_step(_make_step(step_id=4, pick_completed=False, skipped=True, terminal_status="skipped"))

    summary = reporter.build_run_summary("baseline_j5_block_skip", total_steps=4)

    assert summary["completed_picks"] == 2
    assert summary["steps_with_blocked_or_skipped"] == 2
    # No overlap: total should be equal to total arm steps
    assert summary["completed_picks"] + summary["steps_with_blocked_or_skipped"] == len(
        summary["step_reports"]
    )


# ---------------------------------------------------------------------------
# W1 fix: Markdown per-run report must show blocked+skipped as ONE combined row
# ---------------------------------------------------------------------------


def test_run_report_markdown_does_not_have_separate_blocked_and_skipped_rows():
    """Per-run Markdown report must NOT have separate 'Blocked steps' and 'Skipped steps' rows.

    The collision-comparison-reporting spec requires blocked and skipped to appear
    as ONE combined summary count in the high-level report output.
    """
    from fastapi.testclient import TestClient
    import testing_backend as tb

    tb._current_run_result = None
    fresh_client = TestClient(tb.app)
    fresh_client.post(
        "/api/run/start",
        json={
            "mode": 0,
            "scenario": {
                "steps": [
                    {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                    {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
                ]
            },
        },
    )
    md_text = fresh_client.get("/api/run/report/markdown").text
    # Must NOT have two separate rows
    assert "| Blocked steps |" not in md_text, (
        "Markdown must not show 'Blocked steps' as a separate row"
    )
    assert "| Skipped steps |" not in md_text, (
        "Markdown must not show 'Skipped steps' as a separate row"
    )


def test_run_report_markdown_has_combined_blocked_or_skipped_row():
    """Per-run Markdown report must show a single 'Blocked or skipped' combined row."""
    from fastapi.testclient import TestClient
    import testing_backend as tb

    tb._current_run_result = None
    fresh_client = TestClient(tb.app)
    fresh_client.post(
        "/api/run/start",
        json={
            "mode": 0,
            "scenario": {
                "steps": [
                    {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                    {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
                ]
            },
        },
    )
    md_text = fresh_client.get("/api/run/report/markdown").text
    # Must have one combined row
    assert "Blocked or skipped" in md_text, (
        "Markdown must contain a 'Blocked or skipped' combined row"
    )
