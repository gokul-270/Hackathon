"""
Tests for OverlapZoneState: overlap zone detection and contention detection.

One test per scenario (SRP). All tests must fail before overlap_zone_state.py exists.
"""

from overlap_zone_state import OverlapZoneState


# ---------------------------------------------------------------------------
# is_in_overlap_zone
# ---------------------------------------------------------------------------

def test_overlap_zone_state_arms_within_threshold_are_in_overlap_zone():
    """Arms with |j4_own - j4_peer| < 0.110 m are in the overlap zone."""
    state = OverlapZoneState()
    own = {"j4": 0.30, "j5": 0.0}
    peer = {"j4": -0.35, "j5": 0.0}
    # gap = |0.30 + (-0.35)| = 0.05 < 0.110 → in overlap zone
    assert state.is_in_overlap_zone(own, peer) is True


def test_overlap_zone_state_arms_outside_threshold_not_in_overlap_zone():
    """Arms with j4 collision gap >= 0.110 m are NOT in the overlap zone."""
    state = OverlapZoneState()
    own = {"j4": 0.20, "j5": 0.0}
    peer = {"j4": -0.35, "j5": 0.0}
    # gap = |0.20 + (-0.35)| = 0.15 >= 0.110 → not in overlap zone
    assert state.is_in_overlap_zone(own, peer) is False


def test_overlap_zone_state_threshold_boundary_exact():
    """Arms with j4 collision gap exactly equal to 0.110 are NOT in the overlap zone (strict <)."""
    state = OverlapZoneState()
    own = {"j4": 0.0, "j5": 0.0}
    peer = {"j4": -0.110, "j5": 0.0}
    # gap = |0.0 + (-0.110)| = 0.110 exactly → NOT in overlap zone (strict less-than)
    assert state.is_in_overlap_zone(own, peer) is False


# ---------------------------------------------------------------------------
# detect_contention
# ---------------------------------------------------------------------------

def test_overlap_zone_state_contention_when_both_extending_in_overlap_zone():
    """Contention: both j5 > 0 AND |j4| < 0.110 → detect_contention returns True."""
    state = OverlapZoneState()
    own = {"j4": 0.30, "j5": 0.4}
    peer = {"j4": -0.35, "j5": 0.3}
    # gap = |0.30 + (-0.35)| = 0.05 < 0.110 AND both j5 > 0 → contention
    assert state.detect_contention(own, peer) is True


def test_overlap_zone_state_no_contention_when_one_arm_not_extending():
    """No contention when one arm has j5 = 0, even if in the overlap zone."""
    state = OverlapZoneState()
    own = {"j4": 0.30, "j5": 0.4}
    peer = {"j4": -0.35, "j5": 0.0}
    # gap = |0.30 + (-0.35)| = 0.05 < 0.110 but peer j5 = 0 → no contention
    assert state.detect_contention(own, peer) is False


def test_overlap_zone_state_no_contention_when_outside_overlap_zone():
    """No contention when arms are outside the overlap zone, even if both extending."""
    state = OverlapZoneState()
    own = {"j4": 0.20, "j5": 0.4}
    peer = {"j4": -0.35, "j5": 0.3}
    # gap = |0.20 + (-0.35)| = 0.15 >= 0.110 → outside overlap zone → no contention
    assert state.detect_contention(own, peer) is False


# ---------------------------------------------------------------------------
# threshold value — must be 0.110 m
# ---------------------------------------------------------------------------

def test_overlap_zone_state_threshold_is_0110m():
    """OVERLAP_THRESHOLD must be 0.110 m."""
    assert OverlapZoneState.OVERLAP_THRESHOLD == 0.110


def test_overlap_zone_state_threshold_boundary_exact_008m():
    """Arms with |j4_own - j4_peer| exactly 0.110 are NOT in the overlap zone (strict <)."""
    state = OverlapZoneState()
    own = {"j4": 0.0, "j5": 0.0}
    peer = {"j4": -0.110, "j5": 0.0}
    # gap = |0.0 + (-0.110)| = 0.110 exactly → NOT in overlap zone
    assert state.is_in_overlap_zone(own, peer) is False


def test_overlap_zone_state_threshold_boundary_just_below_0110m():
    """Arms with |j4_own - j4_peer| = 0.109 ARE in the overlap zone."""
    state = OverlapZoneState()
    own = {"j4": 0.0, "j5": 0.0}
    peer = {"j4": -0.109, "j5": 0.0}
    assert state.is_in_overlap_zone(own, peer) is True
