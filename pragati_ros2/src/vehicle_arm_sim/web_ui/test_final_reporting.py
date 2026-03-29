"""Tests for Group 3 final four-mode reporting and recommendation logic (TDD Red phase)."""
import pytest
from typing import Optional

from json_reporter import StepReport, JsonReporter
from markdown_reporter import MarkdownReporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_step(
    step_id: int = 1,
    arm_id: str = "arm_a",
    mode: str = "unrestricted",
    candidate_joints: Optional[dict] = None,
    applied_joints: Optional[dict] = None,
    j5_blocked: bool = False,
    near_collision: bool = False,
    collision: bool = False,
    min_j4_distance: Optional[float] = None,
    skipped: bool = False,
) -> StepReport:
    return StepReport(
        step_id=step_id,
        arm_id=arm_id,
        mode=mode,
        candidate_joints=candidate_joints or {"j3": 0.1, "j4": 0.2, "j5": 0.3},
        applied_joints=applied_joints or {"j3": 0.1, "j4": 0.2, "j5": 0.3},
        j5_blocked=j5_blocked,
        near_collision=near_collision,
        collision=collision,
        min_j4_distance=min_j4_distance,
        skipped=skipped,
    )


def _make_run(mode, total_steps=5, near=0, collision=0, blocked=0, skipped=0,
              blocked_or_skipped=None):
    run = {
        "mode": mode,
        "total_steps": total_steps,
        "steps_with_near_collision": near,
        "steps_with_collision": collision,
        "steps_with_motion_blocked": blocked,
        "steps_with_skipped": skipped,
    }
    if blocked_or_skipped is not None:
        run["steps_with_blocked_or_skipped"] = blocked_or_skipped
    else:
        run["steps_with_blocked_or_skipped"] = blocked + skipped
    return run


# ---------------------------------------------------------------------------
# JSON reporter tests
# ---------------------------------------------------------------------------

def test_json_reporter_step_report_has_skipped_field():
    """StepReport must have a 'skipped' field that defaults to False."""
    step = StepReport(
        step_id=1,
        arm_id="arm_a",
        mode="sequential_pick",
        candidate_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
        applied_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
        j5_blocked=False,
        near_collision=False,
        collision=False,
        min_j4_distance=None,
    )
    assert step.skipped is False


def test_json_reporter_summary_has_steps_with_skipped():
    """build_run_summary must contain a 'steps_with_skipped' key."""
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1))
    summary = reporter.build_run_summary(mode="sequential_pick", total_steps=1)
    assert "steps_with_skipped" in summary


def test_json_reporter_steps_with_skipped_counts_skipped_steps():
    """steps_with_skipped must count only steps where skipped=True."""
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1, skipped=True))
    reporter.add_step(make_step(step_id=2, skipped=False))
    reporter.add_step(make_step(step_id=3, skipped=True))
    summary = reporter.build_run_summary(mode="sequential_pick", total_steps=3)
    assert summary["steps_with_skipped"] == 2


def test_json_reporter_summary_has_steps_with_blocked_or_skipped():
    """build_run_summary must contain a 'steps_with_blocked_or_skipped' key."""
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1))
    summary = reporter.build_run_summary(mode="sequential_pick", total_steps=1)
    assert "steps_with_blocked_or_skipped" in summary


def test_json_reporter_blocked_or_skipped_combines_both():
    """steps_with_blocked_or_skipped = steps_with_j5_blocked + steps_with_skipped."""
    reporter = JsonReporter()
    # 2 blocked steps
    reporter.add_step(make_step(step_id=1, j5_blocked=True))
    reporter.add_step(make_step(step_id=2, j5_blocked=True))
    # 1 skipped step
    reporter.add_step(make_step(step_id=3, skipped=True))
    # 1 normal step
    reporter.add_step(make_step(step_id=4))
    summary = reporter.build_run_summary(mode="sequential_pick", total_steps=4)
    assert summary["steps_with_blocked_or_skipped"] == 3


# ---------------------------------------------------------------------------
# Markdown reporter tests
# ---------------------------------------------------------------------------

def test_markdown_reporter_four_runs_produces_four_mode_heading():
    """When 4 runs are supplied, heading must contain 'Four-Mode'."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted"),
        _make_run("baseline_j5_block_skip"),
        _make_run("geometry_block"),
        _make_run("sequential_pick"),
    ]
    md = reporter.generate(runs)
    assert "Four-Mode" in md


def test_markdown_reporter_three_runs_produces_three_mode_heading():
    """When 3 runs are supplied, heading must contain 'Three-Mode'."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted"),
        _make_run("baseline_j5_block_skip"),
        _make_run("geometry_block"),
    ]
    md = reporter.generate(runs)
    assert "Three-Mode" in md


def test_markdown_reporter_recommendation_prefers_zero_collision_mode():
    """Mode with 0 collisions is recommended over mode with 2 collisions."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted", total_steps=10, collision=2, blocked=0),
        _make_run("sequential_pick", total_steps=10, collision=0, blocked=2,
                  blocked_or_skipped=2),
        _make_run("baseline_j5_block_skip", total_steps=10, collision=1, blocked=1,
                  blocked_or_skipped=1),
        _make_run("geometry_block", total_steps=10, collision=3, blocked=0),
    ]
    md = reporter.generate(runs)
    assert "sequential_pick" in md
    # The zero-collision mode should be recommended
    # Check the Recommendation section contains sequential_pick
    rec_start = md.find("### Recommendation")
    assert rec_start != -1
    rec_section = md[rec_start:]
    assert "sequential_pick" in rec_section


def test_markdown_reporter_recommendation_among_zero_collision_modes_prefers_higher_success():
    """Among zero-collision modes, prefer mode with more successful picks (lower blocked_or_skipped)."""
    reporter = MarkdownReporter()
    # Both have 0 collisions, but mode_b has fewer blocked_or_skipped → more successes
    runs = [
        _make_run("mode_a", total_steps=10, collision=0, blocked=0, skipped=4,
                  blocked_or_skipped=4),
        _make_run("mode_b", total_steps=10, collision=0, blocked=0, skipped=1,
                  blocked_or_skipped=1),
        _make_run("mode_c", total_steps=10, collision=2, blocked=0),
    ]
    md = reporter.generate(runs)
    rec_start = md.find("### Recommendation")
    assert rec_start != -1
    rec_section = md[rec_start:]
    assert "mode_b" in rec_section
