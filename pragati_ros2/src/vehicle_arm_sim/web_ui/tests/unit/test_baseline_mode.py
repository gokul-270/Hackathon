"""
Tests for BaselineMode collision avoidance logic.

PeerStatePacket is defined locally here as a minimal dataclass for testing,
since arm_runtime.py may not exist yet.
"""
import dataclasses
from typing import Optional

import pytest

from baseline_mode import BaselineMode


@dataclasses.dataclass
class PeerStatePacket:
    """Minimal stand-in for the PeerStatePacket that arm_runtime.py will provide."""
    candidate_joints: Optional[dict]  # None means peer is idle at this step


# ---------------------------------------------------------------------------
# Mode 0: UNRESTRICTED
# ---------------------------------------------------------------------------

def test_baselinemode_unrestricted_returns_joints_unchanged():
    """Mode 0 must pass joints through without modification when peer is None."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    result = mode.apply(BaselineMode.UNRESTRICTED, own, peer_state=None)
    assert result == own


def test_baselinemode_unrestricted_returns_joints_unchanged_when_peer_is_active():
    """Mode 0 must pass joints through even when peer has active candidate joints."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    peer = PeerStatePacket(candidate_joints={"j3": 0.8, "j4": 0.31, "j5": 0.4})
    result = mode.apply(BaselineMode.UNRESTRICTED, own, peer_state=peer)
    assert result == own


# ---------------------------------------------------------------------------
# Mode 1: BASELINE_J5_BLOCK_SKIP
# ---------------------------------------------------------------------------

def test_baselinemode_baseline_j5_block_skip_no_peer_returns_joints_unchanged():
    """Mode 1 must not modify joints when peer_state is None."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=None)
    assert result == own


def test_baselinemode_baseline_j5_block_skip_blocks_j5_when_horizontal_reach_exceeds_limit():
    """Mode 1 must zero j5 when arm is vertical (j3=0) and j5=0.25 > 0.20/cos(0)=0.20."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.100, "j5": 0.25}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.200, "j5": 0.1})
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.0
    assert result["j3"] == own["j3"]
    assert result["j4"] == own["j4"]


def test_baselinemode_baseline_j5_block_skip_does_not_block_j5_when_horizontal_reach_within_limit():
    """Mode 1 must leave j5 unchanged when arm is vertical (j3=0) and j5=0.19 < 0.20."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.100, "j5": 0.19}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.110, "j5": 0.1})
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.19


def test_baselinemode_baseline_j5_block_skip_does_not_block_j5_at_exact_limit_boundary():
    """Mode 1 must leave j5 unchanged when j5 equals the limit exactly (strictly greater than)."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.100, "j5": 0.20}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.200, "j5": 0.1})
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.20


def test_baselinemode_baseline_j5_block_skip_blocks_j5_when_tilted_30deg_and_j5_exceeds_cosine_limit():
    """Mode 1 must zero j5 when j3=-0.5236rad (30°) and j5=0.24 > 0.20/cos(30°)≈0.231."""
    import math
    mode = BaselineMode()
    own = {"j3": -0.5236, "j4": 0.100, "j5": 0.24}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.200, "j5": 0.1})
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.0


def test_baselinemode_baseline_j5_block_skip_does_not_block_j5_when_tilted_30deg_and_j5_within_cosine_limit():
    """Mode 1 must leave j5 unchanged when j3=-0.5236rad (30°) and j5=0.22 < 0.20/cos(30°)≈0.231."""
    mode = BaselineMode()
    own = {"j3": -0.5236, "j4": 0.100, "j5": 0.22}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.200, "j5": 0.1})
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.22


def test_baselinemode_baseline_j5_block_skip_does_not_block_j5_at_near_vertical_tilt():
    """Mode 1 must leave j5 unchanged when j3=-0.89rad (~51°) and j5=0.30 < 0.20/cos(51°)≈0.318."""
    mode = BaselineMode()
    own = {"j3": -0.89, "j4": 0.100, "j5": 0.30}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.200, "j5": 0.1})
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.30


def test_baselinemode_baseline_j5_block_skip_guard_floor_is_0_1():
    """Mode 1 near-vertical guard: cos(|j3|) floored at 0.1, not 0.01.

    When cos(|j3|) is between 0.01 and 0.1 (theta ≈ 84-89°), the guard must
    activate (limit = inf → always safe), not apply a finite limit.

    Setup: j3 = acos(0.05) ≈ 87.1°  → cos = 0.05  (between 0.01 and 0.1)
      - floor 0.01 (wrong): cos=0.05 > 0.01 → limit = 0.20/0.05 = 4.0m → j5=5.0 BLOCKED
      - floor 0.1  (spec):  cos=0.05 < 0.1  → limit = inf             → j5=5.0 SAFE
    """
    import math
    mode = BaselineMode()
    j3_steep = math.acos(0.05)   # cos ≈ 0.05, sits between 0.01 and 0.1
    own = {"j3": j3_steep, "j4": 0.100, "j5": 5.0}   # j5 > 0.20/0.05 = 4.0m
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.200, "j5": 0.1})
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 5.0, (
        "Guard floor must be 0.1: cos(|j3|)=0.05 is below 0.1, "
        "so limit should be inf and j5 must NOT be zeroed"
    )


def test_baselinemode_baseline_j5_block_skip_does_not_block_j5_when_peer_candidate_joints_is_none():
    """Mode 1 must leave j5 unchanged when peer's candidate_joints is None (peer idle)."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.300, "j5": 0.5}
    peer = PeerStatePacket(candidate_joints=None)
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.5


# ---------------------------------------------------------------------------
# Mode 2: GEOMETRY_BLOCK
# ---------------------------------------------------------------------------

def test_baselinemode_geometry_block_returns_joints_unchanged_when_peer_is_none():
    """Mode 2 must not modify joints when peer_state is None."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    result = mode.apply(BaselineMode.GEOMETRY_BLOCK, own, peer_state=None)
    assert result == own


def test_baselinemode_geometry_block_returns_joints_unchanged_when_peer_candidate_joints_is_none():
    """Mode 2 must not modify joints when peer is present but idle (candidate_joints is None)."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    peer = PeerStatePacket(candidate_joints=None)
    result = mode.apply(BaselineMode.GEOMETRY_BLOCK, own, peer_state=peer)
    assert result == own


def test_baselinemode_geometry_block_returns_joints_unchanged_when_stage1_is_safe():
    """Mode 2 must not modify joints when Stage 1 lateral gap >= 0.110 m (safe)."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.00, "j5": 0.4}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.15, "j5": 0.4})
    # |j4 gap| = 0.15 >= 0.110 → Stage 1 safe, no blocking
    result = mode.apply(BaselineMode.GEOMETRY_BLOCK, own, peer_state=peer)
    assert result["j5"] == 0.4


def test_baselinemode_geometry_block_zeros_j5_when_stage2_returns_unsafe():
    """Mode 2 must zero j5 when Stage 1 is risky and Stage 2 is unsafe."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.4}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": -0.34, "j5": 0.3})
    # j4_collision_gap(0.30, -0.34) = abs(0.30 + (-0.34)) = 0.04 < 0.110 → Stage 1 risky
    # 0.04 < 0.06 AND combined j5 = 0.7 > 0.5 → Stage 2 unsafe
    result = mode.apply(BaselineMode.GEOMETRY_BLOCK, own, peer_state=peer)
    assert result["j5"] == 0.0
    assert result["j3"] == own["j3"]
    assert result["j4"] == own["j4"]


def test_baselinemode_geometry_block_returns_joints_unchanged_when_stage2_is_safe():
    """Mode 2 must not modify joints when Stage 2 combined j5 is within limit."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.30, "j5": 0.2}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.34, "j5": 0.2})
    # |j4 gap| = 0.04 < 0.110 → Stage 1 risky
    # |j4 gap| = 0.04 < 0.06 but combined j5 = 0.4 <= 0.5 → Stage 2 safe
    result = mode.apply(BaselineMode.GEOMETRY_BLOCK, own, peer_state=peer)
    assert result["j5"] == 0.2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_baselinemode_apply_raises_valueerror_for_unknown_mode_number():
    """apply() must raise ValueError when given an unrecognised mode number."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    with pytest.raises(ValueError):
        mode.apply(99, own, peer_state=None)


# ---------------------------------------------------------------------------
# Mode 3: SEQUENTIAL_PICK — apply_with_skip returns 4-tuple via delegation
# ---------------------------------------------------------------------------

def test_baselinemode_sequential_pick_delegates_to_policy():
    """Mode 3 apply_with_skip must delegate to SequentialPickPolicy and return
    (applied_joints, skipped) — the BaselineMode adapter unpacks the 4-tuple
    from the policy into a 2-tuple for backward compat."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.0, "j5": 1.0}
    peer = PeerStatePacket(candidate_joints={"j3": 0.0, "j4": 0.0, "j5": 1.0})
    # Contention: gap 0.0 < 0.110, both j5 > 0
    applied, skipped = mode.apply_with_skip(
        BaselineMode.SEQUENTIAL_PICK, own, peer, step_id=0, arm_id="arm1"
    )
    assert applied == own
    assert skipped is False


def test_baselinemode_sequential_pick_no_peer_passes_through():
    """Mode 3 with no peer must pass through unchanged."""
    mode = BaselineMode()
    own = {"j3": 0.0, "j4": 0.0, "j5": 1.0}
    applied, skipped = mode.apply_with_skip(
        BaselineMode.SEQUENTIAL_PICK, own, None, step_id=0, arm_id="arm1"
    )
    assert applied == own
    assert skipped is False


# ---------------------------------------------------------------------------
# Mode 4: SMART_REORDER — constant and passthrough
# ---------------------------------------------------------------------------

def test_baselinemode_smart_reorder_constant_equals_four():
    """BaselineMode.SMART_REORDER must equal 4."""
    assert BaselineMode.SMART_REORDER == 4


def test_baselinemode_smart_reorder_passes_through_unchanged():
    """Mode 4 apply_with_skip must pass joints through unchanged (reorder is
    done in RunController before the step loop, not per-step)."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    peer = PeerStatePacket(candidate_joints={"j3": 0.8, "j4": 0.31, "j5": 0.4})
    applied, skipped = mode.apply_with_skip(
        BaselineMode.SMART_REORDER, own, peer, step_id=0, arm_id="arm1"
    )
    assert applied == own
    assert skipped is False


def test_baselinemode_smart_reorder_no_peer_passes_through():
    """Mode 4 with no peer must still pass through unchanged."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    applied, skipped = mode.apply_with_skip(
        BaselineMode.SMART_REORDER, own, None, step_id=0, arm_id="arm1"
    )
    assert applied == own
    assert skipped is False


def test_baselinemode_apply_smart_reorder_returns_joints():
    """Mode 4 apply() (non-skip variant) must also return joints unchanged."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    result = mode.apply(BaselineMode.SMART_REORDER, own, peer_state=None)
    assert result == own
