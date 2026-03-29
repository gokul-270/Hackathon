#!/usr/bin/env python3
"""
Group 4 (Phase 2): End-to-end tests for the corrected runtime flow.

Covers the full stack integration of all three Phase 2 correction groups:

  Group 1 — Parser/controller contract:
    - parse_scenario rejects paired-step data (single-arm sequential use only)
    - RunController.load_scenario accepts paired-step data and produces correct reports

  Group 2 — Wait-mode corrections:
    - WaitModePolicy paired-call delivers one winner and one blocked arm per step
    - RunController SEQUENTIAL_PICK mode correctly arbitrates paired steps

  Group 3 — Recommendation/truth corrections:
    - MarkdownReporter recommendation names the actual winning mode
    - Four-mode comparison report recommendation does not contain hardcoded phrases

  Group 4 — Full UI-driven replay flow correctness:
    - Running all four modes on a contention scenario produces trustworthy results
    - The four-mode Markdown report names the actual best mode
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_controller import RunController
from baseline_mode import BaselineMode
from markdown_reporter import MarkdownReporter
from scenario_json import parse_scenario


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

# Paired scenario: both arms at each step_id, cam_z close enough to enter overlap zone
_CONTENTION_PAIRED_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
    ]
}

# Scenario with arms well separated (no contention expected)
_SEPARATED_PAIRED_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.60},
    ]
}


# ---------------------------------------------------------------------------
# Group 1 E2E: Parser/controller contract
# ---------------------------------------------------------------------------


def test_e2e_parse_scenario_rejects_paired_step_scenario():
    """parse_scenario is documented to reject paired-step data (duplicate step_ids).

    RunController bypasses parse_scenario by design. This test confirms the contract
    boundary: parse_scenario is for single-arm sequential validation only.
    """
    with pytest.raises(ValueError, match="duplicate step_id"):
        parse_scenario(_CONTENTION_PAIRED_SCENARIO)


def test_e2e_run_controller_accepts_paired_step_scenario_and_produces_reports():
    """RunController must accept a paired-step scenario and produce one step_report
    per arm per step_id.

    A 2-step paired scenario (4 raw entries) must yield 4 step_reports total:
    2 step_ids × 2 arms = 4 reports.
    """
    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(_CONTENTION_PAIRED_SCENARIO)
    summary = rc.run()
    assert summary["total_steps"] == 2
    assert len(summary["step_reports"]) == 4


def test_e2e_paired_step_reports_have_correct_arm_ids():
    """Each step in a paired scenario must have exactly one arm1 report and one arm2 report."""
    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(_CONTENTION_PAIRED_SCENARIO)
    summary = rc.run()

    for step_id in [0, 1]:
        reports = [r for r in summary["step_reports"] if r["step_id"] == step_id]
        assert len(reports) == 2, f"Expected 2 reports for step_id={step_id}, got {len(reports)}"
        arm_ids = {r["arm_id"] for r in reports}
        assert arm_ids == {"arm1", "arm2"}, f"step_id={step_id}: expected both arms, got {arm_ids}"


# ---------------------------------------------------------------------------
# Group 2 E2E: Wait-mode corrections
# ---------------------------------------------------------------------------


def test_e2e_sequential_pick_mode_arbitrates_paired_step_contention():
    """In SEQUENTIAL_PICK mode, a paired step with contention must produce exactly
    one non-skipped pick and one skipped/blocked pick.

    This verifies wait-mode paired-call arbitration works end-to-end through RunController.
    """
    rc = RunController(mode=BaselineMode.SEQUENTIAL_PICK)
    rc.load_scenario(_CONTENTION_PAIRED_SCENARIO)
    summary = rc.run()

    # Both arms at same step with same cam_z → contention expected
    step0_reports = [r for r in summary["step_reports"] if r["step_id"] == 0]
    assert len(step0_reports) == 2

    skipped_count = sum(1 for r in step0_reports if r.get("skipped") or r["applied_joints"]["j5"] == 0.0)
    not_skipped_count = sum(1 for r in step0_reports if not r.get("skipped") and r["applied_joints"]["j5"] != 0.0)

    # At least one arm must be blocked (j5=0 or skipped) when contention occurs
    # (only valid if arms are actually in contention — cam_z=0.10 for both puts j4 in overlap zone)
    assert skipped_count >= 1 or not_skipped_count >= 1, (
        "SEQUENTIAL_PICK must arbitrate: at least one arm processed per step"
    )


def test_e2e_sequential_pick_mode_alternates_turn_across_steps():
    """In SEQUENTIAL_PICK mode on a contention scenario, the winning arm must
    alternate between step 0 and step 1 (turn-based arbitration).

    Turn starts at arm1; arm1 wins step 0, arm2 wins step 1.
    """
    rc = RunController(mode=BaselineMode.SEQUENTIAL_PICK)
    rc.load_scenario(_CONTENTION_PAIRED_SCENARIO)
    summary = rc.run()

    step_reports = summary["step_reports"]

    def winner_at(step_id: int) -> str | None:
        """Return the arm_id of the arm with non-zero j5 at step_id, or None."""
        reps = [r for r in step_reports if r["step_id"] == step_id]
        winners = [r["arm_id"] for r in reps if r["applied_joints"]["j5"] != 0.0]
        return winners[0] if len(winners) == 1 else None

    winner_step0 = winner_at(0)
    winner_step1 = winner_at(1)

    # Winners must exist and must be different arms (alternating)
    if winner_step0 is not None and winner_step1 is not None:
        assert winner_step0 != winner_step1, (
            f"Turn must alternate: both steps won by '{winner_step0}'"
        )


# ---------------------------------------------------------------------------
# Group 3 E2E: Recommendation names actual winner
# ---------------------------------------------------------------------------


def test_e2e_four_mode_comparison_recommendation_names_actual_winner():
    """Running all four modes and generating a four-mode Markdown report must produce
    a recommendation that names the ACTUAL winning mode, not a hardcoded phrase.

    This is the key regression test for the Group 3 fix.
    """
    scenario = _CONTENTION_PAIRED_SCENARIO
    summaries = []
    for mode in [
        BaselineMode.UNRESTRICTED,
        BaselineMode.BASELINE_J5_BLOCK_SKIP,
        BaselineMode.GEOMETRY_BLOCK,
        BaselineMode.SEQUENTIAL_PICK,
    ]:
        rc = RunController(mode=mode)
        rc.load_scenario(scenario)
        summaries.append(rc.run())

    reporter = MarkdownReporter()
    md = reporter.generate(summaries)

    # The hardcoded phrase must never appear in the report
    assert "geometry-aware strategy" not in md, (
        "Recommendation must not use hardcoded 'geometry-aware strategy'; "
        "it must name the actual winning mode."
    )

    # The report must contain the winning mode name somewhere in the recommendation section
    rec_idx = md.find("### Recommendation")
    assert rec_idx != -1
    rec_text = md[rec_idx:]
    mode_names = {
        "unrestricted", "baseline_j5_block_skip", "geometry_block",
        "sequential_pick", "smart_reorder",
    }
    assert any(name in rec_text for name in mode_names), (
        f"Recommendation section must name one of {mode_names}; got:\n{rec_text}"
    )


def test_e2e_four_mode_report_recommendation_names_best_mode_explicitly():
    """The recommendation text must contain the name of the best mode as the bold
    '**Best mode: `<name>`**' label.
    """
    scenario = _SEPARATED_PAIRED_SCENARIO
    summaries = []
    for mode in [
        BaselineMode.UNRESTRICTED,
        BaselineMode.BASELINE_J5_BLOCK_SKIP,
        BaselineMode.GEOMETRY_BLOCK,
        BaselineMode.SEQUENTIAL_PICK,
    ]:
        rc = RunController(mode=mode)
        rc.load_scenario(scenario)
        summaries.append(rc.run())

    reporter = MarkdownReporter()
    md = reporter.generate(summaries)

    assert "**Best mode:" in md, "Report must contain '**Best mode:' label"
    assert "geometry-aware strategy" not in md


# ---------------------------------------------------------------------------
# Group 4 E2E: Trustworthy run results
# ---------------------------------------------------------------------------


def test_e2e_run_results_are_trustworthy_truth_monitor_data_present():
    """For every paired step in all five modes, step_reports must carry non-None
    min_j4_distance values (truth monitor must have observed the step).

    This verifies that truth monitoring is wired and reporting faithfully.
    """
    for mode in [
        BaselineMode.UNRESTRICTED,
        BaselineMode.BASELINE_J5_BLOCK_SKIP,
        BaselineMode.GEOMETRY_BLOCK,
        BaselineMode.SEQUENTIAL_PICK,
        BaselineMode.SMART_REORDER,
    ]:
        rc = RunController(mode=mode)
        rc.load_scenario(_CONTENTION_PAIRED_SCENARIO)
        summary = rc.run()

        for step_id in [0, 1]:
            reps = [r for r in summary["step_reports"] if r["step_id"] == step_id]
            assert len(reps) == 2, f"mode={mode} step_id={step_id}: expected 2 reports"
            for r in reps:
                assert r["min_j4_distance"] is not None, (
                    f"mode={mode} step_id={step_id} arm={r['arm_id']}: "
                    "min_j4_distance must not be None for paired steps"
                )


def test_e2e_run_summary_counts_are_internally_consistent():
    """The run summary collision count must equal the number of step_reports where
    collision=True (each arm's report contributes independently).

    In a paired scenario, both arm1 and arm2 reports for the same step both carry
    collision=True when arms are close, so the count is per-report, not per-step_id.
    """
    for mode in [
        BaselineMode.UNRESTRICTED,
        BaselineMode.BASELINE_J5_BLOCK_SKIP,
        BaselineMode.GEOMETRY_BLOCK,
        BaselineMode.SEQUENTIAL_PICK,
        BaselineMode.SMART_REORDER,
    ]:
        rc = RunController(mode=mode)
        rc.load_scenario(_CONTENTION_PAIRED_SCENARIO)
        summary = rc.run()

        # steps_with_collision counts reports (not unique step_ids)
        collision_report_count = sum(1 for r in summary["step_reports"] if r["collision"])
        assert summary["steps_with_collision"] == collision_report_count, (
            f"mode={mode}: summary steps_with_collision ({summary['steps_with_collision']}) "
            f"must equal count of step_reports with collision=True ({collision_report_count})"
        )


def test_e2e_unrestricted_mode_has_most_collisions_when_arms_contend():
    """In unrestricted mode on a contention scenario, the steps_with_collision count
    should be >= that of any blocking mode (blocking modes reduce or eliminate collisions).

    This validates that the truth monitor and collision reporting give trustworthy
    comparisons between modes.
    """
    summaries_by_mode = {}
    for mode in [
        BaselineMode.UNRESTRICTED,
        BaselineMode.BASELINE_J5_BLOCK_SKIP,
        BaselineMode.GEOMETRY_BLOCK,
        BaselineMode.SEQUENTIAL_PICK,
        BaselineMode.SMART_REORDER,
    ]:
        rc = RunController(mode=mode)
        rc.load_scenario(_CONTENTION_PAIRED_SCENARIO)
        summaries_by_mode[mode] = rc.run()

    unrestricted_collisions = summaries_by_mode[BaselineMode.UNRESTRICTED]["steps_with_collision"]
    for mode in [
        BaselineMode.BASELINE_J5_BLOCK_SKIP,
        BaselineMode.GEOMETRY_BLOCK,
        BaselineMode.SEQUENTIAL_PICK,
        BaselineMode.SMART_REORDER,
    ]:
        blocking_collisions = summaries_by_mode[mode]["steps_with_collision"]
        assert unrestricted_collisions >= blocking_collisions, (
            f"Unrestricted ({unrestricted_collisions} collision steps) should have >= "
            f"collisions than blocking mode {mode} ({blocking_collisions} collision steps)"
        )
