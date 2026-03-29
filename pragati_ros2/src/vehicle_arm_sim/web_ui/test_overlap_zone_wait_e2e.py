"""
End-to-end tests for overlap_zone_wait mode (Release 3 integration).

These tests verify the full stack integration:
  - RunController accepts mode=3 (OVERLAP_ZONE_WAIT)
  - overlap_zone_wait mode skips picks on contention-heavy scenarios
  - The mode name in reports is "overlap_zone_wait"
  - Four-mode comparison (unrestricted, baseline, geometry_block, overlap_zone_wait)
    produces valid Markdown with "Four-Mode" heading
  - summary dict contains steps_with_skipped and steps_with_blocked_or_skipped

These tests fail until:
  1. BaselineMode gains OVERLAP_ZONE_WAIT = 3 and apply() dispatches to wait-mode logic
  2. RunController registers "overlap_zone_wait" in _MODE_NAMES
  3. RunController correctly tracks j5_blocked and skipped for overlap_zone_wait
  4. StepReport.skipped is populated by RunController
  5. MarkdownReporter accepts 4-run summaries
"""
import json
import os

import pytest

from run_controller import RunController
from baseline_mode import BaselineMode
from markdown_reporter import MarkdownReporter

_CONTENTION_SCENARIO_PATH = os.path.join(
    os.path.dirname(__file__), "scenarios", "contention_pack.json"
)

_GEOMETRY_SCENARIO_PATH = os.path.join(
    os.path.dirname(__file__), "scenarios", "geometry_pack.json"
)


def _load_scenario(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Mode constant
# ---------------------------------------------------------------------------

def test_baseline_mode_has_overlap_zone_wait_constant():
    """BaselineMode must expose OVERLAP_ZONE_WAIT = 3."""
    assert hasattr(BaselineMode, "OVERLAP_ZONE_WAIT")
    assert BaselineMode.OVERLAP_ZONE_WAIT == 3


# ---------------------------------------------------------------------------
# RunController accepts overlap_zone_wait mode
# ---------------------------------------------------------------------------

def test_run_controller_accepts_overlap_zone_wait_mode():
    """RunController must accept mode=3 without raising."""
    rc = RunController(mode=BaselineMode.OVERLAP_ZONE_WAIT)
    rc.load_scenario(_load_scenario(_CONTENTION_SCENARIO_PATH))
    summary = rc.run()
    assert summary["mode"] == "overlap_zone_wait"


def test_run_controller_overlap_zone_wait_summary_has_steps_with_skipped():
    """overlap_zone_wait run summary must contain steps_with_skipped key."""
    rc = RunController(mode=BaselineMode.OVERLAP_ZONE_WAIT)
    rc.load_scenario(_load_scenario(_CONTENTION_SCENARIO_PATH))
    summary = rc.run()
    assert "steps_with_skipped" in summary


def test_run_controller_overlap_zone_wait_summary_has_steps_with_blocked_or_skipped():
    """overlap_zone_wait run summary must contain steps_with_blocked_or_skipped key."""
    rc = RunController(mode=BaselineMode.OVERLAP_ZONE_WAIT)
    rc.load_scenario(_load_scenario(_CONTENTION_SCENARIO_PATH))
    summary = rc.run()
    assert "steps_with_blocked_or_skipped" in summary


def test_run_controller_overlap_zone_wait_skips_on_contention_heavy_scenario():
    """overlap_zone_wait must produce at least 1 skipped step on the contention-heavy scenario."""
    rc = RunController(mode=BaselineMode.OVERLAP_ZONE_WAIT)
    rc.load_scenario(_load_scenario(_CONTENTION_SCENARIO_PATH))
    summary = rc.run()
    assert summary["steps_with_skipped"] > 0, (
        "Expected overlap_zone_wait to skip at least one pick on the contention-heavy scenario"
    )


def test_run_controller_overlap_zone_wait_json_report_has_correct_mode_name():
    """JSON report for overlap_zone_wait must have mode='overlap_zone_wait'."""
    rc = RunController(mode=BaselineMode.OVERLAP_ZONE_WAIT)
    rc.load_scenario(_load_scenario(_CONTENTION_SCENARIO_PATH))
    rc.run()
    report = json.loads(rc.get_json_report())
    assert report["mode"] == "overlap_zone_wait"


def test_run_controller_overlap_zone_wait_reduces_collisions_vs_unrestricted():
    """overlap_zone_wait must produce fewer or equal collision steps than unrestricted."""
    scenario = _load_scenario(_CONTENTION_SCENARIO_PATH)

    rc_unr = RunController(mode=BaselineMode.UNRESTRICTED)
    rc_unr.load_scenario(scenario)
    unr_summary = rc_unr.run()

    rc_wait = RunController(mode=BaselineMode.OVERLAP_ZONE_WAIT)
    rc_wait.load_scenario(scenario)
    wait_summary = rc_wait.run()

    assert wait_summary["steps_with_collision"] <= unr_summary["steps_with_collision"], (
        f"overlap_zone_wait should reduce collisions: "
        f"got {wait_summary['steps_with_collision']} vs unrestricted "
        f"{unr_summary['steps_with_collision']}"
    )


# ---------------------------------------------------------------------------
# Four-mode comparison
# ---------------------------------------------------------------------------

def test_four_mode_comparison_produces_four_mode_markdown():
    """Running all four modes produces Markdown with 'Four-Mode' heading."""
    scenario = _load_scenario(_GEOMETRY_SCENARIO_PATH)

    rc_unr = RunController(mode=BaselineMode.UNRESTRICTED)
    rc_unr.load_scenario(scenario)
    unr_summary = rc_unr.run()

    rc_base = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP)
    rc_base.load_scenario(scenario)
    base_summary = rc_base.run()

    rc_geo = RunController(mode=BaselineMode.GEOMETRY_BLOCK)
    rc_geo.load_scenario(scenario)
    geo_summary = rc_geo.run()

    rc_wait = RunController(mode=BaselineMode.OVERLAP_ZONE_WAIT)
    rc_wait.load_scenario(scenario)
    wait_summary = rc_wait.run()

    reporter = MarkdownReporter()
    md = reporter.generate([unr_summary, base_summary, geo_summary, wait_summary])
    assert "## Four-Mode Collision Comparison Report" in md
    assert "overlap_zone_wait" in md
    assert "geometry_block" in md
    assert "unrestricted" in md
    assert "baseline_j5_block_skip" in md


def test_four_mode_step_reports_have_correct_mode_names():
    """Each mode's step_reports must contain the correct mode string."""
    scenario = _load_scenario(_GEOMETRY_SCENARIO_PATH)

    for mode_int, mode_str in [
        (BaselineMode.UNRESTRICTED, "unrestricted"),
        (BaselineMode.BASELINE_J5_BLOCK_SKIP, "baseline_j5_block_skip"),
        (BaselineMode.GEOMETRY_BLOCK, "geometry_block"),
        (BaselineMode.OVERLAP_ZONE_WAIT, "overlap_zone_wait"),
    ]:
        rc = RunController(mode=mode_int)
        rc.load_scenario(scenario)
        summary = rc.run()
        for step_report in summary["step_reports"]:
            assert step_report["mode"] == mode_str, (
                f"Expected mode={mode_str!r}, got {step_report['mode']!r}"
            )
