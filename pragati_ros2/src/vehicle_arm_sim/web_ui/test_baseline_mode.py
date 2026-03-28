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


def test_baselinemode_baseline_j5_block_skip_blocks_j5_when_peer_active_and_j4_within_0_05m():
    """Mode 1 must zero j5 when peer has candidate joints and |j4_own - j4_peer| < 0.05."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.300, "j5": 0.5}
    peer = PeerStatePacket(candidate_joints={"j3": 0.8, "j4": 0.340, "j5": 0.4})
    # |0.300 - 0.340| = 0.040 < 0.05 → should block
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.0
    assert result["j3"] == own["j3"]
    assert result["j4"] == own["j4"]


def test_baselinemode_baseline_j5_block_skip_does_not_block_j5_when_j4_difference_exceeds_0_05m():
    """Mode 1 must leave j5 unchanged when |j4_own - j4_peer| >= 0.05."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.300, "j5": 0.5}
    peer = PeerStatePacket(candidate_joints={"j3": 0.8, "j4": 0.360, "j5": 0.4})
    # |0.300 - 0.360| = 0.060 >= 0.05 → should not block
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.5


def test_baselinemode_baseline_j5_block_skip_does_not_block_j5_when_peer_candidate_joints_is_none():
    """Mode 1 must leave j5 unchanged when peer's candidate_joints is None (peer idle)."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.300, "j5": 0.5}
    peer = PeerStatePacket(candidate_joints=None)
    result = mode.apply(BaselineMode.BASELINE_J5_BLOCK_SKIP, own, peer_state=peer)
    assert result["j5"] == 0.5


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_baselinemode_apply_raises_valueerror_for_unknown_mode_number():
    """apply() must raise ValueError when given an unrecognised mode number."""
    mode = BaselineMode()
    own = {"j3": 1.0, "j4": 0.3, "j5": 0.5}
    with pytest.raises(ValueError):
        mode.apply(99, own, peer_state=None)
