"""
End-to-end tests for geometry_block mode (Release 2 integration).

These tests verify the full stack integration:
  - RunController accepts mode=2 (GEOMETRY_BLOCK)
  - geometry_block mode blocks more motions than unrestricted on overlap-heavy scenarios
  - The mode name in reports is "geometry_block"
  - Three-mode comparison (unrestricted, baseline, geometry_block) produces valid Markdown

These tests fail until:
  1. BaselineMode gains GEOMETRY_BLOCK = 2 and apply() dispatches to geometry logic
  2. RunController registers "geometry_block" in _MODE_NAMES
  3. RunController correctly tracks j5_blocked for geometry_block mode
  4. MarkdownReporter accepts run summaries from all three modes
"""
import json
import os
from pathlib import Path

import pytest

from run_controller import RunController
from baseline_mode import BaselineMode
from markdown_reporter import MarkdownReporter

_SCENARIO_PATH = os.path.join(
    str(Path(__file__).resolve().parent.parent.parent), "scenarios", "geometry_pack.json"
)


def _load_geometry_scenario() -> dict:
    import json
    with open(_SCENARIO_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Mode constant
# ---------------------------------------------------------------------------

def test_baseline_mode_has_geometry_block_constant():
    """BaselineMode must expose GEOMETRY_BLOCK = 2."""
    assert hasattr(BaselineMode, "GEOMETRY_BLOCK")
    assert BaselineMode.GEOMETRY_BLOCK == 2


# ---------------------------------------------------------------------------
# RunController accepts geometry_block mode
# ---------------------------------------------------------------------------

def test_run_controller_accepts_geometry_block_mode():
    """RunController must accept mode=2 without raising."""
    rc = RunController(mode=BaselineMode.GEOMETRY_BLOCK)
    rc.load_scenario(_load_geometry_scenario())
    summary = rc.run()
    assert summary["mode"] == "geometry_block"


def test_run_controller_geometry_block_reports_motion_blocked():
    """geometry_block mode must block at least one step on the overlap-heavy scenario."""
    rc = RunController(mode=BaselineMode.GEOMETRY_BLOCK)
    rc.load_scenario(_load_geometry_scenario())
    summary = rc.run()
    assert summary["steps_with_motion_blocked"] > 0, (
        "Expected geometry_block to block at least one motion on the overlap-heavy scenario"
    )


def test_run_controller_geometry_block_blocks_more_than_unrestricted():
    """geometry_block must block more motions than unrestricted on the overlap-heavy scenario."""
    scenario = _load_geometry_scenario()

    rc_unr = RunController(mode=BaselineMode.UNRESTRICTED)
    rc_unr.load_scenario(scenario)
    unr_summary = rc_unr.run()

    rc_geo = RunController(mode=BaselineMode.GEOMETRY_BLOCK)
    rc_geo.load_scenario(scenario)
    geo_summary = rc_geo.run()

    assert geo_summary["steps_with_motion_blocked"] > unr_summary["steps_with_motion_blocked"]


def test_run_controller_geometry_block_json_report_has_correct_mode_name():
    """JSON report for geometry_block must have mode='geometry_block'."""
    rc = RunController(mode=BaselineMode.GEOMETRY_BLOCK)
    rc.load_scenario(_load_geometry_scenario())
    rc.run()
    report = json.loads(rc.get_json_report())
    assert report["mode"] == "geometry_block"


# ---------------------------------------------------------------------------
# Three-mode comparison
# ---------------------------------------------------------------------------

def test_three_mode_comparison_produces_markdown():
    """Running all three modes and feeding summaries to MarkdownReporter produces Markdown."""
    scenario = _load_geometry_scenario()

    rc_unr = RunController(mode=BaselineMode.UNRESTRICTED)
    rc_unr.load_scenario(scenario)
    unr_summary = rc_unr.run()

    rc_base = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP)
    rc_base.load_scenario(scenario)
    base_summary = rc_base.run()

    rc_geo = RunController(mode=BaselineMode.GEOMETRY_BLOCK)
    rc_geo.load_scenario(scenario)
    geo_summary = rc_geo.run()

    reporter = MarkdownReporter()
    md = reporter.generate([unr_summary, base_summary, geo_summary])
    assert "## Three-Mode Collision Comparison Report" in md
    assert "geometry_block" in md
    assert "unrestricted" in md
    assert "baseline_j5_block_skip" in md


def test_three_mode_comparison_step_reports_have_correct_modes():
    """Each mode's step_reports must contain the correct mode string."""
    scenario = _load_geometry_scenario()

    for mode_int, mode_str in [
        (BaselineMode.UNRESTRICTED, "unrestricted"),
        (BaselineMode.BASELINE_J5_BLOCK_SKIP, "baseline_j5_block_skip"),
        (BaselineMode.GEOMETRY_BLOCK, "geometry_block"),
    ]:
        rc = RunController(mode=mode_int)
        rc.load_scenario(scenario)
        summary = rc.run()
        for step_report in summary["step_reports"]:
            assert step_report["mode"] == mode_str, (
                f"Expected mode={mode_str!r}, got {step_report['mode']!r}"
            )
