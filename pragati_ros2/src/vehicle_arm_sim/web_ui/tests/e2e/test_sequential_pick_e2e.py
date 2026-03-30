"""
End-to-end tests for Mode 3 (sequential_pick) behavior.

These tests verify the new sequential pick behavior introduced in the
five-mode migration:
  - Mode 3 runs complete without errors on contention scenarios
  - Mode 3 produces no more skipped steps than unrestricted mode
  - Contention steps are handled (no worse collision rate than unrestricted)

The existing test_overlap_zone_wait_e2e.py covers the original four-mode
integration tests (mode constant, reports, four-mode comparison). This file
adds tests specifically for the sequential_pick policy behavior observable
through RunController end-to-end.
"""
import json
import os
from pathlib import Path

import pytest

from baseline_mode import BaselineMode
from run_controller import RunController

_CONTENTION_SCENARIO_PATH = os.path.join(
    str(Path(__file__).resolve().parent.parent.parent), "scenarios", "contention_pack.json"
)


def _load_scenario(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Test 1: Mode 3 runs complete without errors on contention scenario
# ---------------------------------------------------------------------------


def test_sequential_pick_e2e_run_completes_without_errors():
    """Mode 3 (SEQUENTIAL_PICK) must run the contention scenario to completion
    and return a valid summary dict with all required keys."""
    scenario = _load_scenario(_CONTENTION_SCENARIO_PATH)
    rc = RunController(mode=BaselineMode.SEQUENTIAL_PICK)
    rc.load_scenario(scenario)
    summary = rc.run()

    assert isinstance(summary, dict)
    assert summary["mode"] == "sequential_pick"
    assert summary["total_steps"] > 0
    assert "step_reports" in summary
    assert len(summary["step_reports"]) > 0


# ---------------------------------------------------------------------------
# Test 2: Mode 3 skipped count does not exceed unrestricted mode
# ---------------------------------------------------------------------------


def test_sequential_pick_e2e_skipped_count_bounded_by_unrestricted():
    """Sequential pick mode must not produce MORE skipped steps than unrestricted mode.

    The SequentialPickPolicy alternates which arm picks at contention points.
    The skipped count for sequential_pick should be <= that of unrestricted
    (both can have skipped steps depending on RunController dispatch logic).
    """
    scenario = _load_scenario(_CONTENTION_SCENARIO_PATH)

    rc_seq = RunController(mode=BaselineMode.SEQUENTIAL_PICK)
    rc_seq.load_scenario(scenario)
    seq_summary = rc_seq.run()

    rc_unr = RunController(mode=BaselineMode.UNRESTRICTED)
    rc_unr.load_scenario(scenario)
    unr_summary = rc_unr.run()

    assert seq_summary["steps_with_skipped"] <= unr_summary["steps_with_skipped"], (
        f"Sequential pick must not produce more skipped steps than unrestricted; "
        f"got seq={seq_summary['steps_with_skipped']} vs unr={unr_summary['steps_with_skipped']}"
    )


# ---------------------------------------------------------------------------
# Test 3: Contention steps are handled (collisions <= unrestricted)
# ---------------------------------------------------------------------------


def test_sequential_pick_e2e_collisions_not_worse_than_unrestricted():
    """At contention points, sequential pick mode must not produce MORE
    collisions than unrestricted mode.

    Collisions are detected by the truth monitor (j4 distance) independently
    of the policy. Sequential pick arbitrates dispatch order, which may or may
    not reduce the measured collision count depending on arm geometry.
    """
    scenario = _load_scenario(_CONTENTION_SCENARIO_PATH)

    rc_seq = RunController(mode=BaselineMode.SEQUENTIAL_PICK)
    rc_seq.load_scenario(scenario)
    seq_summary = rc_seq.run()

    rc_unr = RunController(mode=BaselineMode.UNRESTRICTED)
    rc_unr.load_scenario(scenario)
    unr_summary = rc_unr.run()

    assert seq_summary["steps_with_collision"] <= unr_summary["steps_with_collision"], (
        f"Sequential pick must not produce more collisions than unrestricted; "
        f"got seq={seq_summary['steps_with_collision']} vs unr={unr_summary['steps_with_collision']}"
    )
