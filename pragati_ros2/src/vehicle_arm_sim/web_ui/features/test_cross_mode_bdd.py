"""BDD test: Cross-Mode Algorithm Comparison.

Tests that span multiple modes, verifying constants, naming, relative safety,
and threshold comparisons.
"""
import dataclasses
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest
from pytest_bdd import given, parsers, scenario, then, when

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baseline_mode import BaselineMode
from run_controller import RunController
from sequential_pick_policy import SequentialPickPolicy

FEATURE = "cross_mode_comparison.feature"


# ---------------------------------------------------------------------------
# Minimal PeerStatePacket
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class PeerStatePacket:
    candidate_joints: Optional[dict]


# ===================================================================
# Scenario bindings — constants
# ===================================================================

@scenario(FEATURE, "Mode constant UNRESTRICTED is 0")
def test_const_unrestricted():
    pass


@scenario(FEATURE, "Mode constant BASELINE_J5_BLOCK_SKIP is 1")
def test_const_baseline():
    pass


@scenario(FEATURE, "Mode constant GEOMETRY_BLOCK is 2")
def test_const_geometry():
    pass


@scenario(FEATURE, "Mode constant SEQUENTIAL_PICK is 3")
def test_const_sequential():
    pass


@scenario(FEATURE, "Mode constant SMART_REORDER is 4")
def test_const_smart_reorder():
    pass


@scenario(FEATURE, "Unknown mode raises ValueError")
def test_unknown_mode():
    pass


# ===================================================================
# Scenario bindings — full run
# ===================================================================

@scenario(FEATURE, "Mode 0 completes a full run")
def test_run_mode0():
    pass


@scenario(FEATURE, "Mode 1 completes a full run")
def test_run_mode1():
    pass


@scenario(FEATURE, "Mode 2 completes a full run")
def test_run_mode2():
    pass


@scenario(FEATURE, "Mode 3 completes a full run")
def test_run_mode3():
    pass


@scenario(FEATURE, "Mode 4 completes a full run")
def test_run_mode4():
    pass


# ===================================================================
# Scenario bindings — relative collision safety
# ===================================================================

@scenario(FEATURE, "Mode 0 has at least as many collisions as Mode 1")
def test_mode0_vs_mode1():
    pass


@scenario(FEATURE, "Mode 0 has at least as many collisions as Mode 2")
def test_mode0_vs_mode2():
    pass


@scenario(FEATURE, "Mode 0 has at least as many collisions as Mode 3")
def test_mode0_vs_mode3():
    pass


@scenario(FEATURE, "Mode 0 has at least as many collisions as Mode 4")
def test_mode0_vs_mode4():
    pass


# ===================================================================
# Scenario bindings — step reports
# ===================================================================

@scenario(FEATURE, "Each mode produces step reports for both arms")
def test_step_reports_both_arms():
    pass


# ===================================================================
# Scenario bindings — threshold comparison
# ===================================================================

@scenario(FEATURE, "Mode 1 blocks when j5 exceeds cosine limit but Mode 3 is safe (large j4 gap)")
def test_threshold_mode1_blocks_mode3_safe():
    pass


@scenario(FEATURE, "Both Mode 1 and Mode 3 trigger when j5 exceeds limit and j4 gap is small")
def test_threshold_both_trigger():
    pass


@scenario(FEATURE, "Neither Mode 1 nor Mode 3 triggers when j5 is safe and j4 gap is large")
def test_threshold_neither_triggers():
    pass


# ===================================================================
# THEN steps — constants
# ===================================================================

@then(parsers.re(r'the BaselineMode\.(?P<name>\w+) constant equals (?P<val>\d+)'))
def then_constant(name, val):
    assert getattr(BaselineMode, name) == int(val)


# ===================================================================
# GIVEN steps — run scenarios
# ===================================================================

_CONTENTION_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
    ]
}


@given(parsers.re(r'a contention scenario with both arms at cam_z (?P<cz>[\d.]+)'))
def given_contention_scenario(ctx, cz):
    cz = float(cz)
    ctx["contention_scenario"] = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": cz},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": cz},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": cz},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": cz},
        ]
    }


@given(parsers.re(r'the run mode is (?P<mode>\d+)'))
def given_run_mode(ctx, mode):
    ctx["run_mode"] = int(mode)


def _run_mode(scenario_data, mode):
    """Run a single mode and return the summary."""
    rc = RunController(mode=mode)
    rc.load_scenario(scenario_data)
    return rc.run()


# ===================================================================
# WHEN steps — full run
# ===================================================================

@when("RunController executes the full run")
def when_full_run(ctx):
    summary = _run_mode(ctx["contention_scenario"], ctx["run_mode"])
    ctx["run_summary"] = summary


@when(parsers.re(r'mode (?P<m0>\d+) and mode (?P<m1>\d+) both run on the same scenario'))
def when_two_modes_run(ctx, m0, m1):
    m0, m1 = int(m0), int(m1)
    ctx[f"summary_mode_{m0}"] = _run_mode(ctx["contention_scenario"], m0)
    ctx[f"summary_mode_{m1}"] = _run_mode(ctx["contention_scenario"], m1)


@when("all five modes run on the same scenario")
def when_all_five_run(ctx):
    for m in range(5):
        ctx[f"summary_mode_{m}"] = _run_mode(ctx["contention_scenario"], m)


# ===================================================================
# THEN steps — full run
# ===================================================================

@then("the run completes without error")
def then_no_error(ctx):
    assert ctx["run_summary"] is not None
    assert "step_reports" in ctx["run_summary"]


@then(parsers.re(r'the summary mode name is "(?P<name>[^"]+)"'))
def then_mode_name(ctx, name):
    assert ctx["run_summary"]["mode"] == name


def _collision_count(summary):
    """Count step_reports where collision == True."""
    return sum(
        1 for r in summary.get("step_reports", [])
        if r.get("collision") is True
    )


@then(parsers.re(
    r'mode 0 collision count is greater than or equal to mode (?P<other>\d+)'
))
def then_mode0_gte(ctx, other):
    c0 = _collision_count(ctx["summary_mode_0"])
    cn = _collision_count(ctx[f"summary_mode_{int(other)}"])
    assert c0 >= cn, f"Mode 0 collisions ({c0}) < Mode {other} collisions ({cn})"


@then("each run has step reports for arm1 and arm2")
def then_both_arms_in_reports(ctx):
    for m in range(5):
        summary = ctx[f"summary_mode_{m}"]
        arm_ids = {r["arm_id"] for r in summary["step_reports"]}
        assert "arm1" in arm_ids, f"Mode {m} missing arm1 reports"
        assert "arm2" in arm_ids, f"Mode {m} missing arm2 reports"


# ===================================================================
# Threshold comparison steps
# ===================================================================

@given(parsers.re(
    r'arms with j3=(?P<j3a>[+-]?[\d.]+) j4=(?P<j4a>-?[\d.]+) j5=(?P<j5a>[\d.]+) '
    r'vs j3=(?P<j3b>[+-]?[\d.]+) j4=(?P<j4b>-?[\d.]+) j5=(?P<j5b>[\d.]+)'
))
def given_arms_with_joints(ctx, j3a, j4a, j5a, j3b, j4b, j5b):
    ctx["arm1_joints"] = {"j3": float(j3a), "j4": float(j4a), "j5": float(j5a)}
    ctx["arm2_joints"] = {"j3": float(j3b), "j4": float(j4b), "j5": float(j5b)}
    ctx["mode"] = BaselineMode()


@when(parsers.re(r'mode 1 and mode 3 are both applied'))
def when_mode1_and_mode3(ctx):
    peer = PeerStatePacket(candidate_joints=ctx["arm2_joints"])

    # Mode 1
    result_m1, _ = ctx["mode"].apply_with_skip(
        BaselineMode.BASELINE_J5_BLOCK_SKIP, ctx["arm1_joints"], peer,
    )
    ctx["mode1_result"] = result_m1

    # Mode 3 — needs a fresh policy
    mode3 = BaselineMode()
    _, _, is_contention, _ = SequentialPickPolicy().apply(
        0, "arm1", ctx["arm1_joints"], ctx["arm2_joints"],
    )
    ctx["mode3_contention"] = is_contention


@then(parsers.re(r'mode 1 blocks j5 \(j5 exceeds cosine limit\)'))
def then_mode1_blocks_cosine(ctx):
    assert ctx["mode1_result"]["j5"] == 0.0


@then(parsers.re(r'mode 1 does NOT block \(j5 within cosine limit\)'))
def then_mode1_no_block_cosine(ctx):
    assert ctx["mode1_result"]["j5"] == ctx["arm1_joints"]["j5"]


@then(parsers.re(r'mode 3 does NOT detect contention \(j4 gap >= 0\.10m\)'))
def then_mode3_no_contention_gap(ctx):
    assert ctx["mode3_contention"] is False


@then(parsers.re(r'mode 3 detects contention \(j4 gap < 0\.10m\)'))
def then_mode3_contention_gap(ctx):
    assert ctx["mode3_contention"] is True
