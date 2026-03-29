"""Tests for SequentialPickPolicy — Mode 3 sequential pick."""

import pytest
from sequential_pick_policy import SequentialPickPolicy

# ---------------------------------------------------------------------------
# Helper joint dicts
# ---------------------------------------------------------------------------

# Both arms at j4=0.0, both extending (j5 > 0) → contention (gap 0.0 < 0.10)
OWN_CONTENTION = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_CONTENTION = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}

# Far apart: |0.0 - 0.20| = 0.20 >= 0.10 → no contention
OWN_FAR = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_FAR = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.20, "j5": 1.0}

# Peer not extending (j5 == 0) → no contention even when gap < 0.10
PEER_J5_ZERO = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 0.0}

# Own not extending (j5 == 0) → no contention even when gap < 0.10
OWN_J5_ZERO = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 0.0}

# Boundary: gap exactly 0.10 → NOT contention (strictly less than)
OWN_BOUNDARY = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_BOUNDARY_AT = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.10, "j5": 1.0}

# Boundary: gap 0.099 → IS contention
PEER_BOUNDARY_BELOW = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.099, "j5": 1.0}


# ---------------------------------------------------------------------------
# Test 1: no peer → no contention, not winner
# ---------------------------------------------------------------------------


def test_no_peer_returns_no_contention():
    """When peer_joints is None, returns (own_joints, False, False, False)."""
    policy = SequentialPickPolicy()
    own = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
    result = policy.apply(step_id=0, arm_id="arm1", own_joints=own, peer_joints=None)
    assert result == (own, False, False, False)


# ---------------------------------------------------------------------------
# Test 2: gap above threshold → no contention
# ---------------------------------------------------------------------------


def test_gap_above_threshold_no_contention():
    """When |j4_own - j4_peer| >= 0.10, returns no contention."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0, arm_id="arm1", own_joints=OWN_FAR, peer_joints=PEER_FAR
    )
    assert result == (OWN_FAR, False, False, False)


# ---------------------------------------------------------------------------
# Test 3: peer j5 == 0 → no contention
# ---------------------------------------------------------------------------


def test_peer_j5_zero_no_contention():
    """When gap < 0.10 but peer j5 == 0, returns no contention."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0, arm_id="arm1", own_joints=OWN_CONTENTION, peer_joints=PEER_J5_ZERO
    )
    assert result == (OWN_CONTENTION, False, False, False)


# ---------------------------------------------------------------------------
# Test 4: own j5 == 0 → no contention
# ---------------------------------------------------------------------------


def test_own_j5_zero_no_contention():
    """When gap < 0.10 but own j5 == 0, returns no contention."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0, arm_id="arm1", own_joints=OWN_J5_ZERO, peer_joints=PEER_CONTENTION
    )
    assert result == (OWN_J5_ZERO, False, False, False)


# ---------------------------------------------------------------------------
# Test 5: contention detected, arm1 wins first (turn=0)
# ---------------------------------------------------------------------------


def test_contention_detected_arm1_wins_first():
    """Gap < 0.10, both j5 > 0, arm1 called first → contention, is_winner."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    applied, skipped, is_contention, is_winner = result
    assert applied == OWN_CONTENTION
    assert skipped is False
    assert is_contention is True
    assert is_winner is True


# ---------------------------------------------------------------------------
# Test 6: contention detected, arm2 is loser on first step
# ---------------------------------------------------------------------------


def test_contention_detected_arm2_is_loser_first_step():
    """Same step_id, arm2 called second → contention, NOT winner."""
    policy = SequentialPickPolicy()
    # arm1 goes first in step 0
    policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    # arm2 goes second in same step 0
    result = policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    applied, skipped, is_contention, is_winner = result
    assert applied == OWN_CONTENTION
    assert skipped is False
    assert is_contention is True
    assert is_winner is False


# ---------------------------------------------------------------------------
# Test 7: turn alternates after step
# ---------------------------------------------------------------------------


def test_turn_alternates_after_step():
    """After step 0 (arm1 wins), on step 1, arm2 should win."""
    policy = SequentialPickPolicy()

    # Step 0: arm1 wins, arm2 loses
    policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )

    # Step 1: arm2 should now win
    result = policy.apply(
        step_id=1,
        arm_id="arm2",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    applied, skipped, is_contention, is_winner = result
    assert applied == OWN_CONTENTION
    assert skipped is False
    assert is_contention is True
    assert is_winner is True


# ---------------------------------------------------------------------------
# Test 8: turn locked within same step_id
# ---------------------------------------------------------------------------


def test_turn_locked_within_same_step_id():
    """Both arms in same step_id get the same turn verdict — arm1 wins both
    calls in step 0 get consistent results."""
    policy = SequentialPickPolicy()

    # arm1 in step 0 — should win (turn=0 → arm1's turn)
    r1 = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    # arm2 in step 0 — should lose (turn still locked at 0)
    r2 = policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )

    _, _, _, is_winner_arm1 = r1
    _, _, _, is_winner_arm2 = r2
    assert is_winner_arm1 is True
    assert is_winner_arm2 is False


# ---------------------------------------------------------------------------
# Test 9: winner joints unmodified
# ---------------------------------------------------------------------------


def test_winner_joints_unmodified():
    """Winner gets exact same joints passed in — no j5 zeroing."""
    policy = SequentialPickPolicy()
    own = {"j1": 10, "j2": 20, "j3": 30, "j4": 0.05, "j5": 2.5}
    peer = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.05, "j5": 1.0}

    applied, _, is_contention, is_winner = policy.apply(
        step_id=0, arm_id="arm1", own_joints=own, peer_joints=peer
    )
    assert is_contention is True
    assert is_winner is True
    assert applied is own  # exact same object, not a copy


# ---------------------------------------------------------------------------
# Test 10: loser joints unmodified
# ---------------------------------------------------------------------------


def test_loser_joints_unmodified():
    """Loser ALSO gets exact same joints — RunController handles dispatch
    ordering, policy doesn't modify joints."""
    policy = SequentialPickPolicy()
    own_arm2 = {"j1": 5, "j2": 15, "j3": 25, "j4": 0.02, "j5": 3.0}
    peer_arm2 = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.02, "j5": 1.0}

    # arm1 goes first to claim the win
    policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints={"j1": 0, "j2": 0, "j3": 0, "j4": 0.02, "j5": 1.0},
        peer_joints=own_arm2,
    )

    # arm2 is the loser
    applied, _, is_contention, is_winner = policy.apply(
        step_id=0, arm_id="arm2", own_joints=own_arm2, peer_joints=peer_arm2
    )
    assert is_contention is True
    assert is_winner is False
    assert applied is own_arm2  # exact same object, not a copy


# ---------------------------------------------------------------------------
# Test 11: contention threshold boundary at 0.10 (NOT contention)
# ---------------------------------------------------------------------------


def test_contention_threshold_boundary_at_010():
    """Gap of exactly 0.10 is NOT contention (strictly less than)."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_BOUNDARY,
        peer_joints=PEER_BOUNDARY_AT,
    )
    assert result == (OWN_BOUNDARY, False, False, False)


# ---------------------------------------------------------------------------
# Test 12: contention threshold boundary below 0.10 (IS contention)
# ---------------------------------------------------------------------------


def test_contention_threshold_boundary_below_010():
    """Gap of 0.099 IS contention."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_BOUNDARY,
        peer_joints=PEER_BOUNDARY_BELOW,
    )
    applied, skipped, is_contention, is_winner = result
    assert applied == OWN_BOUNDARY
    assert skipped is False
    assert is_contention is True
    assert is_winner is True
