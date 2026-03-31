"""
Tests for GeometryStage2Check — better geometry/link-level unsafe-case check.

Stage 2 is invoked only when Stage 1 classified the motion as "risky".
It performs a more thorough geometry and link-level analysis.
If it determines the motion is unsafe, the pick is blocked immediately.

Design contract
---------------
GeometryStage2Check.check(own_joints, peer_joints) -> "safe" | "unsafe"
  own_joints  : {"j3": float, "j4": float, "j5": float}
  peer_joints : {"j3": float, "j4": float, "j5": float}

Link-level check logic:
  Consider both j4 lateral gap AND j5 extension of both arms.
  The combined reach of two arms' j5 extensions creates a "collision envelope".

  Unsafe when:
    lateral_gap = j4_collision_gap(j4_own, j4_peer) < 0.06 m
    AND combined_extension = (j5_own + j5_peer) > 0.5
    (i.e., both arms are extended AND laterally close → imminent collision)

  Safe otherwise.
"""
import pytest

from geometry_check import GeometryStage2Check


# ---------------------------------------------------------------------------
# unsafe cases
# ---------------------------------------------------------------------------

def test_stage2_check_returns_unsafe_when_laterally_close_and_both_arms_extended():
    """Arms close laterally and both extended → unsafe."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.4}
    peer = {"j3": 0.0, "j4": -0.34, "j5": 0.3}
    # gap(0.30, -0.34) = |0.30 + (-0.34)| = 0.04 < 0.06, j5 sum = 0.7 > 0.5 → unsafe
    assert check.check(own, peer) == "unsafe"


def test_stage2_check_returns_unsafe_when_j4_gap_at_boundary_and_combined_extension_exceeded():
    """j4 gap just below threshold and large combined extension → unsafe."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.00, "j5": 0.4}
    peer = {"j3": 0.0, "j4": -0.059, "j5": 0.2}
    # gap(0.00, -0.059) = |0.00 + (-0.059)| = 0.059 < 0.06, j5 sum = 0.6 > 0.5 → unsafe
    assert check.check(own, peer) == "unsafe"


# ---------------------------------------------------------------------------
# safe cases — lateral gap is large enough (passes even with high extension)
# ---------------------------------------------------------------------------

def test_stage2_check_returns_safe_when_j4_gap_equals_threshold():
    """j4 gap at exactly Stage 2 threshold → safe (boundary inclusive)."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.00, "j5": 0.8}
    peer = {"j3": 0.0, "j4": -0.06, "j5": 0.8}
    # gap(0.00, -0.06) = |0.00 + (-0.06)| = 0.06 >= 0.06, combined j5 = 1.6 → safe
    assert check.check(own, peer) == "safe"


def test_stage2_check_returns_safe_when_j4_gap_clearly_above_threshold():
    """Arms far apart laterally → safe regardless of extension."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.10, "j5": 0.9}
    peer = {"j3": 0.0, "j4": -0.40, "j5": 0.9}
    # gap(0.10, -0.40) = |0.10 + (-0.40)| = 0.30 >= 0.06 → safe
    assert check.check(own, peer) == "safe"


# ---------------------------------------------------------------------------
# safe cases — combined extension is small (arms not extended enough to collide)
# ---------------------------------------------------------------------------

def test_stage2_check_returns_safe_when_laterally_close_but_combined_extension_small():
    """Arms are close laterally but neither is significantly extended → safe."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.1}
    peer = {"j3": 0.0, "j4": -0.33, "j5": 0.2}
    # gap(0.30, -0.33) = |0.30 + (-0.33)| = 0.03 < 0.06, but j5 sum = 0.3 <= 0.5 → safe
    assert check.check(own, peer) == "safe"


def test_stage2_check_returns_safe_when_combined_extension_at_boundary():
    """Combined extension exactly at boundary value → safe."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.25}
    peer = {"j3": 0.0, "j4": -0.33, "j5": 0.25}
    # gap(0.30, -0.33) = |0.30 + (-0.33)| = 0.03 < 0.06, j5 sum = 0.5 → safe (boundary)
    assert check.check(own, peer) == "safe"


# ---------------------------------------------------------------------------
# symmetric — order should not matter
# ---------------------------------------------------------------------------

def test_stage2_check_result_is_symmetric_unsafe():
    """Swapping own/peer does not change unsafe result."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.4}
    peer = {"j3": 0.0, "j4": -0.34, "j5": 0.3}
    assert check.check(own, peer) == check.check(peer, own)


def test_stage2_check_result_is_symmetric_safe():
    """Swapping own/peer does not change safe result."""
    check = GeometryStage2Check()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.1}
    peer = {"j3": 0.0, "j4": -0.33, "j5": 0.2}
    assert check.check(own, peer) == check.check(peer, own)
