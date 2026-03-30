"""
Tests for MarkdownReporter — three-mode Markdown comparison output.

The MarkdownReporter produces a Markdown report comparing three run modes:
  - unrestricted
  - baseline_j5_block_skip
  - geometry_block

Design contract
---------------
MarkdownReporter.generate(runs: list[dict]) -> str
  runs: list of 3 run-summary dicts (from RunController.run() / JsonReporter.build_run_summary())
        Each dict must contain:
          - "mode": str
          - "total_steps": int
          - "steps_with_near_collision": int
          - "steps_with_collision": int
          - "steps_with_j5_blocked": int / "steps_with_motion_blocked": int

  Returns a Markdown string containing:
    - A heading: "## Three-Mode Collision Comparison Report"
    - A Markdown table with one row per mode
    - Table columns: Mode | Total Steps | Near-Collision Steps | Collision Steps | Blocked Steps
    - A "Recommendation" section explaining which mode performs best

Validation rules:
  - Raises ValueError if runs has fewer than 3 entries
  - Raises ValueError if any run dict is missing required keys
"""
import pytest

from markdown_reporter import MarkdownReporter


def _make_run(mode, total_steps=5, near=0, collision=0, blocked=0):
    return {
        "mode": mode,
        "total_steps": total_steps,
        "steps_with_near_collision": near,
        "steps_with_collision": collision,
        "steps_with_motion_blocked": blocked,
    }


# ---------------------------------------------------------------------------
# Heading and structure
# ---------------------------------------------------------------------------

def test_markdown_report_contains_heading():
    """Report must include the three-mode heading."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted"),
        _make_run("baseline_j5_block_skip"),
        _make_run("geometry_block"),
    ]
    md = reporter.generate(runs)
    assert "## Three-Mode Collision Comparison Report" in md


def test_markdown_report_contains_table_header():
    """Report must include a Markdown table header row."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted"),
        _make_run("baseline_j5_block_skip"),
        _make_run("geometry_block"),
    ]
    md = reporter.generate(runs)
    assert "| Mode |" in md
    assert "| --- |" in md or "|---|" in md or "| :---" in md


def test_markdown_report_contains_recommendation_section():
    """Report must include a Recommendation section."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted"),
        _make_run("baseline_j5_block_skip"),
        _make_run("geometry_block"),
    ]
    md = reporter.generate(runs)
    assert "Recommendation" in md or "recommendation" in md


# ---------------------------------------------------------------------------
# Mode names appear in the table
# ---------------------------------------------------------------------------

def test_markdown_report_contains_unrestricted_row():
    """Report must include a row for the unrestricted mode."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted", near=3, collision=1, blocked=0),
        _make_run("baseline_j5_block_skip", near=1, collision=0, blocked=2),
        _make_run("geometry_block", near=0, collision=0, blocked=1),
    ]
    md = reporter.generate(runs)
    assert "unrestricted" in md


def test_markdown_report_contains_baseline_row():
    """Report must include a row for the baseline_j5_block_skip mode."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted"),
        _make_run("baseline_j5_block_skip"),
        _make_run("geometry_block"),
    ]
    md = reporter.generate(runs)
    assert "baseline_j5_block_skip" in md


def test_markdown_report_contains_geometry_block_row():
    """Report must include a row for the geometry_block mode."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted"),
        _make_run("baseline_j5_block_skip"),
        _make_run("geometry_block"),
    ]
    md = reporter.generate(runs)
    assert "geometry_block" in md


# ---------------------------------------------------------------------------
# Numbers appear in the table
# ---------------------------------------------------------------------------

def test_markdown_report_includes_collision_counts():
    """Report must include the collision and near-collision counts from the runs."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted", near=4, collision=2, blocked=0),
        _make_run("baseline_j5_block_skip", near=2, collision=0, blocked=3),
        _make_run("geometry_block", near=1, collision=0, blocked=1),
    ]
    md = reporter.generate(runs)
    assert "4" in md
    assert "2" in md
    assert "3" in md


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_markdown_report_raises_value_error_when_fewer_than_3_runs():
    """generate() must raise ValueError if fewer than 3 run dicts are supplied."""
    reporter = MarkdownReporter()
    with pytest.raises(ValueError):
        reporter.generate([_make_run("unrestricted"), _make_run("baseline_j5_block_skip")])


def test_markdown_report_raises_value_error_when_run_missing_mode_key():
    """generate() must raise ValueError if a run dict is missing the 'mode' key."""
    reporter = MarkdownReporter()
    bad = {"total_steps": 5, "steps_with_near_collision": 0,
           "steps_with_collision": 0, "steps_with_motion_blocked": 0}
    with pytest.raises(ValueError):
        reporter.generate([bad, _make_run("baseline_j5_block_skip"), _make_run("geometry_block")])


# ---------------------------------------------------------------------------
# Group 3 (Phase 2): recommendation text names the ACTUAL winning mode
# ---------------------------------------------------------------------------


def test_recommendation_text_names_actual_winning_mode_not_hardcoded_string():
    """The recommendation section must reference the ACTUAL best mode name, not a
    hardcoded string like 'geometry-aware strategy'.

    When the winner is 'sequential_pick', the recommendation text must contain
    'sequential_pick'.  When the winner is 'baseline_j5_block_skip', the
    recommendation text must contain 'baseline_j5_block_skip'.
    """
    reporter = MarkdownReporter()
    # sequential_pick is the winner: zero collisions with fewest blocked
    runs = [
        _make_run("unrestricted", collision=3, near=4, blocked=0),
        _make_run("baseline_j5_block_skip", collision=1, near=2, blocked=2),
        _make_run("sequential_pick", collision=0, near=1, blocked=1),
    ]
    md = reporter.generate(runs)
    # Must name the actual winner
    assert "sequential_pick" in md
    # Must NOT use a hardcoded label for a mode that didn't win
    assert "geometry-aware strategy" not in md


def test_recommendation_text_names_baseline_mode_when_it_wins():
    """When baseline_j5_block_skip is the best mode, recommendation must name it."""
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted", collision=3, near=4, blocked=0),
        _make_run("baseline_j5_block_skip", collision=0, near=2, blocked=2),
        _make_run("geometry_block", collision=0, near=1, blocked=3),
    ]
    md = reporter.generate(runs)
    # geometry_block has more blocked — baseline wins on success_count
    assert "baseline_j5_block_skip" in md
    assert "geometry-aware strategy" not in md


def test_recommendation_avoidance_count_names_worst_mode_correctly():
    """The avoidance count line must reference the actual worst mode, not a
    hardcoded 'geometry-aware strategy' phrase.
    """
    reporter = MarkdownReporter()
    runs = [
        _make_run("unrestricted", collision=5, near=6, blocked=0),
        _make_run("baseline_j5_block_skip", collision=0, near=1, blocked=2),
        _make_run("geometry_block", collision=0, near=0, blocked=1),
    ]
    md = reporter.generate(runs)
    # geometry_block wins; the avoidance line should NOT say "geometry-aware strategy"
    assert "geometry-aware strategy" not in md


# ---------------------------------------------------------------------------
# Group 6: Five-mode report support
# ---------------------------------------------------------------------------

_FIVE_MODES = [
    "unrestricted",
    "baseline_j5_block_skip",
    "geometry_block",
    "sequential_pick",
    "smart_reorder",
]


def _make_run_with_blocked_or_skipped(
    mode, total_steps=5, near=0, collision=0, blocked=0, blocked_or_skipped=0
):
    return {
        "mode": mode,
        "total_steps": total_steps,
        "steps_with_near_collision": near,
        "steps_with_collision": collision,
        "steps_with_motion_blocked": blocked,
        "steps_with_blocked_or_skipped": blocked_or_skipped,
    }


def test_five_mode_heading_when_five_runs():
    """Report with 5 runs must include 'Five-Mode' in heading."""
    reporter = MarkdownReporter()
    runs = [_make_run(mode) for mode in _FIVE_MODES]
    md = reporter.generate(runs)
    assert "## Five-Mode Collision Comparison Report" in md


def test_four_mode_heading_still_works_with_four_runs():
    """Report with exactly 4 runs must still produce 'Four-Mode' heading."""
    reporter = MarkdownReporter()
    runs = [_make_run(mode) for mode in _FIVE_MODES[:4]]
    md = reporter.generate(runs)
    assert "## Four-Mode Collision Comparison Report" in md


def test_five_mode_table_has_blocked_skipped_column():
    """Five-mode table must include a 'Blocked+Skipped' column header."""
    reporter = MarkdownReporter()
    runs = [_make_run(mode) for mode in _FIVE_MODES]
    md = reporter.generate(runs)
    assert "Blocked+Skipped" in md


def test_five_mode_all_mode_names_appear():
    """All 5 mode names must appear in the generated report."""
    reporter = MarkdownReporter()
    runs = [_make_run(mode) for mode in _FIVE_MODES]
    md = reporter.generate(runs)
    for mode in _FIVE_MODES:
        assert mode in md, f"Mode '{mode}' not found in report"


def test_five_mode_recommendation_works():
    """Five-mode report must contain a Recommendation section picking the best mode."""
    reporter = MarkdownReporter()
    runs = [
        _make_run_with_blocked_or_skipped("unrestricted", collision=5, near=6, blocked=0, blocked_or_skipped=0),
        _make_run_with_blocked_or_skipped("baseline_j5_block_skip", collision=2, near=3, blocked=1, blocked_or_skipped=1),
        _make_run_with_blocked_or_skipped("geometry_block", collision=1, near=2, blocked=2, blocked_or_skipped=2),
        _make_run_with_blocked_or_skipped("sequential_pick", collision=0, near=1, blocked=1, blocked_or_skipped=1),
        _make_run_with_blocked_or_skipped("smart_reorder", collision=0, near=0, blocked=0, blocked_or_skipped=0),
    ]
    md = reporter.generate(runs)
    assert "Recommendation" in md
    assert "smart_reorder" in md
