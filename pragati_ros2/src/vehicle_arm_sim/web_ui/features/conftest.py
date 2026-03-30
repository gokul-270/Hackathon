"""conftest.py — shared fixtures and step definitions for BDD algorithm tests.

Provides common Given/When/Then steps used across all mode feature files.
"""
import dataclasses
import sys
from pathlib import Path
from typing import Optional

import pytest
from pytest_bdd import given, parsers, then, when

# Ensure the web_ui source is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baseline_mode import BaselineMode
from sequential_pick_policy import SequentialPickPolicy
from smart_reorder_scheduler import SmartReorderScheduler


# ---------------------------------------------------------------------------
# CSV path overrides (populated by pytest_configure from --arm1-csv/--arm2-csv)
# ---------------------------------------------------------------------------
_csv_paths: dict[str, str | None] = {"arm1": None, "arm2": None}


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --arm1-csv and --arm2-csv CLI options."""
    parser.addoption(
        "--arm1-csv",
        default=None,
        metavar="PATH",
        help="Path to arm1 CSV file (overrides default features/arm1.csv)",
    )
    parser.addoption(
        "--arm2-csv",
        default=None,
        metavar="PATH",
        help="Path to arm2 CSV file (overrides default features/arm2.csv)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Store resolved CSV paths so test modules can read them at import time."""
    try:
        _csv_paths["arm1"] = config.getoption("--arm1-csv")
        _csv_paths["arm2"] = config.getoption("--arm2-csv")
    except ValueError:
        pass  # option not registered (e.g. running via collect-only without plugin)


# ---------------------------------------------------------------------------
# Minimal PeerStatePacket for testing (avoids importing arm_runtime)
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class PeerStatePacket:
    """Minimal stand-in for the PeerStatePacket that arm_runtime.py provides."""

    candidate_joints: Optional[dict]


# ---------------------------------------------------------------------------
# Shared test context
# ---------------------------------------------------------------------------
@pytest.fixture
def ctx():
    """Mutable context dict shared across Given/When/Then steps."""
    return {
        "mode_num": None,
        "mode": BaselineMode(),
        "arm1_joints": None,
        "arm2_joints": None,
        "peer_state": "NOT_SET",  # sentinel: distinguish None from not-set
        "result_joints": None,
        "result_skipped": None,
        "result_contention": None,
        "result_winner": None,
        "policy": None,
        "scheduler": None,
        "error": None,
        # For multi-arm policy evaluation
        "arm_results": {},
    }


# ===================================================================
# GIVEN steps — mode selection
# ===================================================================

@given(parsers.re(r'the collision avoidance mode is (?P<mode>\d+) \(.*\)'))
def given_mode(ctx, mode):
    ctx["mode_num"] = int(mode)


# ===================================================================
# GIVEN steps — arm joints
# ===================================================================

@given(parsers.re(
    r'arm1 has joints j3=(?P<j3>[\d.]+) j4=(?P<j4>[\d.]+) j5=(?P<j5>[\d.]+)'
))
def given_arm1_joints(ctx, j3, j4, j5):
    ctx["arm1_joints"] = {"j3": float(j3), "j4": float(j4), "j5": float(j5)}


@given(parsers.re(
    r'arm2 has joints j3=(?P<j3>[\d.]+) j4=(?P<j4>[\d.]+) j5=(?P<j5>[\d.]+)'
))
def given_arm2_joints(ctx, j3, j4, j5):
    ctx["arm2_joints"] = {"j3": float(j3), "j4": float(j4), "j5": float(j5)}


# ===================================================================
# GIVEN steps — peer state
# ===================================================================

@given("no peer arm is active")
def given_no_peer(ctx):
    ctx["peer_state"] = None


@given("the peer arm is present but idle")
def given_peer_idle(ctx):
    ctx["peer_state"] = PeerStatePacket(candidate_joints=None)


# ===================================================================
# GIVEN steps — policies and schedulers
# ===================================================================

@given("a fresh sequential pick policy")
def given_fresh_policy(ctx):
    ctx["policy"] = SequentialPickPolicy()


@given("a smart reorder scheduler")
def given_scheduler(ctx):
    ctx["scheduler"] = SmartReorderScheduler()


# ===================================================================
# WHEN steps — apply algorithm
# ===================================================================

@when("the algorithm is applied for arm1")
def when_apply_for_arm1(ctx):
    peer = ctx["peer_state"]
    if peer == "NOT_SET" and ctx["arm2_joints"] is not None:
        peer = PeerStatePacket(candidate_joints=ctx["arm2_joints"])

    joints, skipped = ctx["mode"].apply_with_skip(
        ctx["mode_num"],
        ctx["arm1_joints"],
        peer,
    )
    ctx["result_joints"] = joints
    ctx["result_skipped"] = skipped


@when("the algorithm is applied and an error is expected")
def when_apply_expect_error(ctx):
    peer = ctx["peer_state"]
    if peer == "NOT_SET":
        peer = None
    try:
        ctx["mode"].apply_with_skip(ctx["mode_num"], ctx["arm1_joints"], peer)
    except ValueError as exc:
        ctx["error"] = exc


# ===================================================================
# THEN steps — joint assertions
# ===================================================================

@then(parsers.re(
    r'the returned joints are j3=(?P<j3>[\d.]+) j4=(?P<j4>[\d.]+) j5=(?P<j5>[\d.]+)'
))
def then_returned_joints(ctx, j3, j4, j5):
    assert ctx["result_joints"]["j3"] == pytest.approx(float(j3))
    assert ctx["result_joints"]["j4"] == pytest.approx(float(j4))
    assert ctx["result_joints"]["j5"] == pytest.approx(float(j5))


@then("j5 is zeroed")
def then_j5_zeroed(ctx):
    assert ctx["result_joints"]["j5"] == 0.0


@then("j5 is not zeroed")
def then_j5_not_zeroed(ctx):
    assert ctx["result_joints"]["j5"] != 0.0 or ctx["arm1_joints"]["j5"] == 0.0


@then(parsers.re(r'j3 is unchanged at (?P<val>[\d.]+)'))
def then_j3_unchanged(ctx, val):
    assert ctx["result_joints"]["j3"] == pytest.approx(float(val))


@then(parsers.re(r'j4 is unchanged at (?P<val>[\d.]+)'))
def then_j4_unchanged(ctx, val):
    assert ctx["result_joints"]["j4"] == pytest.approx(float(val))


@then(parsers.re(r'the returned j5 is (?P<val>[\d.]+)'))
def then_returned_j5(ctx, val):
    assert ctx["result_joints"]["j5"] == pytest.approx(float(val))


@then("skipped is false")
def then_skipped_false(ctx):
    assert ctx["result_skipped"] is False


@then("joints are returned unchanged")
def then_joints_unchanged(ctx):
    # The result should match the original arm1 joints (or whichever arm was evaluated)
    if ctx["result_joints"] is not None and ctx["arm1_joints"] is not None:
        assert ctx["result_joints"] == ctx["arm1_joints"]


# ===================================================================
# THEN steps — error assertions
# ===================================================================

@then(parsers.re(r'a ValueError is raised with message containing "(?P<msg>[^"]+)"'))
def then_value_error(ctx, msg):
    assert ctx["error"] is not None, "Expected ValueError but none was raised"
    assert msg in str(ctx["error"])
