"""
Tests for GeometryStage1Screen — quick end-effector distance screen.

Stage 1 is a fast safe/risky split based on the 3D distance between
the two arms' end-effectors.  If the distance is large enough the motion
is immediately classified as SAFE and Stage 2 is skipped.  If the distance
is too small the motion is RISKY and Stage 2 must be consulted.

Design contract
---------------
GeometryStage1Screen.screen(own_joints, peer_joints) -> "safe" | "risky"
  own_joints  : {"j3": float, "j4": float, "j5": float}
  peer_joints : {"j3": float, "j4": float, "j5": float}

The screen uses the lateral gap j4_collision_gap(j4_own, j4_peer)
as the end-effector proxy.  The Stage 1 threshold is 0.08 m.
  distance < 0.08  → "risky"
  distance >= 0.08 → "safe"
"""
import pytest

from geometry_check import GeometryStage1Screen

THRESHOLD = 0.08  # Stage 1 screen threshold


# ---------------------------------------------------------------------------
# safe cases — distance clearly exceeds threshold
# ---------------------------------------------------------------------------

def test_stage1_screen_returns_safe_when_j4_distance_clearly_above_threshold():
    """End-effectors far apart → safe."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.10, "j5": 0.5}
    peer = {"j3": 0.0, "j4": -0.50, "j5": 0.5}
    # gap(0.10, -0.50) = |0.10 + (-0.50)| = 0.40 >= 0.08 → safe
    assert screen.screen(own, peer) == "safe"


def test_stage1_screen_returns_safe_when_j4_distance_equals_threshold():
    """Distance exactly at threshold → safe (boundary is inclusive on safe side)."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.00, "j5": 0.3}
    peer = {"j3": 0.0, "j4": -0.08, "j5": 0.3}
    # gap(0.00, -0.08) = |0.00 + (-0.08)| = 0.08 >= 0.08 → safe
    assert screen.screen(own, peer) == "safe"


# ---------------------------------------------------------------------------
# risky cases — distance below threshold
# ---------------------------------------------------------------------------

def test_stage1_screen_returns_risky_when_j4_distance_below_threshold():
    """End-effectors close together → risky."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.5}
    peer = {"j3": 0.0, "j4": -0.35, "j5": 0.5}
    # gap(0.30, -0.35) = |0.30 + (-0.35)| = 0.05 < 0.08 → risky
    assert screen.screen(own, peer) == "risky"


def test_stage1_screen_returns_risky_when_j4_distance_is_zero():
    """Arms at identical lateral position → risky."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.25, "j5": 0.4}
    peer = {"j3": 0.0, "j4": -0.25, "j5": 0.4}
    assert screen.screen(own, peer) == "risky"


def test_stage1_screen_returns_risky_when_j4_distance_just_below_threshold():
    """Distance just under threshold → risky (boundary exclusive on risky side)."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.000, "j5": 0.3}
    peer = {"j3": 0.0, "j4": -0.079, "j5": 0.3}
    # gap(0.000, -0.079) = |0.000 + (-0.079)| = 0.079 < 0.08 → risky
    assert screen.screen(own, peer) == "risky"


# ---------------------------------------------------------------------------
# symmetric — order of arms should not matter
# ---------------------------------------------------------------------------

def test_stage1_screen_result_is_symmetric_when_arms_swapped_safe():
    """Swapping own/peer does not change safe result."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.10, "j5": 0.5}
    peer = {"j3": 0.0, "j4": -0.50, "j5": 0.5}
    assert screen.screen(own, peer) == screen.screen(peer, own)


def test_stage1_screen_result_is_symmetric_when_arms_swapped_risky():
    """Swapping own/peer does not change risky result."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.5}
    peer = {"j3": 0.0, "j4": -0.35, "j5": 0.5}
    assert screen.screen(own, peer) == screen.screen(peer, own)


# ---------------------------------------------------------------------------
# threshold value — must be 0.08 m
# ---------------------------------------------------------------------------

def test_stage1_safe_threshold_constant_is_008m():
    """Stage 1 safe threshold must be 0.08 m."""
    from geometry_check import _STAGE1_SAFE_THRESHOLD
    assert _STAGE1_SAFE_THRESHOLD == 0.08


def test_stage1_screen_returns_safe_when_j4_distance_equals_008m():
    """Distance exactly at 0.08 m → safe (boundary inclusive on safe side)."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.00, "j5": 0.3}
    peer = {"j3": 0.0, "j4": -0.08, "j5": 0.3}
    # gap(0.00, -0.08) = |0.00 + (-0.08)| = 0.08 >= 0.08 → safe
    assert screen.screen(own, peer) == "safe"


def test_stage1_screen_returns_risky_when_j4_distance_just_below_008m():
    """Distance just under 0.08 m → risky."""
    screen = GeometryStage1Screen()
    own = {"j3": 0.0, "j4": 0.000, "j5": 0.3}
    peer = {"j3": 0.0, "j4": -0.079, "j5": 0.3}
    # gap(0.000, -0.079) = |0.000 + (-0.079)| = 0.079 < 0.08 → risky
    assert screen.screen(own, peer) == "risky"
