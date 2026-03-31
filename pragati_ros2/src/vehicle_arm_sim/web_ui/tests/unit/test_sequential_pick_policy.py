"""Tests for SequentialPickPolicy — Mode 3 sequential pick."""

import pytest
from sequential_pick_policy import SequentialPickPolicy

# ---------------------------------------------------------------------------
# Helper joint dicts
# ---------------------------------------------------------------------------

# Both arms at j4=0.0, both extending (j5 > 0) → contention (gap 0.0 < 0.110)
OWN_CONTENTION = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_CONTENTION = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}

# Far apart: |0.0 + (-0.20)| = 0.20 >= 0.110 → no contention
OWN_FAR = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_FAR = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.20, "j5": 1.0}

# Peer not extending (j5 == 0) → no contention even when gap < 0.110
PEER_J5_ZERO = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 0.0}

# Own not extending (j5 == 0) → no contention even when gap < 0.110
OWN_J5_ZERO = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 0.0}

# Boundary: gap exactly 0.110 → NOT contention (strictly less than)
OWN_BOUNDARY = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_BOUNDARY_AT = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.110, "j5": 1.0}

# Boundary: gap 0.109 → IS contention
PEER_BOUNDARY_BELOW = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.109, "j5": 1.0}


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
    """When |j4_own - j4_peer| >= 0.110, returns no contention."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0, arm_id="arm1", own_joints=OWN_FAR, peer_joints=PEER_FAR
    )
    assert result == (OWN_FAR, False, False, False)


# ---------------------------------------------------------------------------
# Test 3: peer j5 == 0 → no contention
# ---------------------------------------------------------------------------


def test_peer_j5_zero_no_contention():
    """When gap < 0.110 but peer j5 == 0, returns no contention."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0, arm_id="arm1", own_joints=OWN_CONTENTION, peer_joints=PEER_J5_ZERO
    )
    assert result == (OWN_CONTENTION, False, False, False)


# ---------------------------------------------------------------------------
# Test 4: own j5 == 0 → no contention
# ---------------------------------------------------------------------------


def test_own_j5_zero_no_contention():
    """When gap < 0.110 but own j5 == 0, returns no contention."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0, arm_id="arm1", own_joints=OWN_J5_ZERO, peer_joints=PEER_CONTENTION
    )
    assert result == (OWN_J5_ZERO, False, False, False)


# ---------------------------------------------------------------------------
# Test 5: contention detected, arm1 wins first (turn=0)
# ---------------------------------------------------------------------------


def test_contention_detected_arm1_wins_first():
    """Gap < 0.110, both j5 > 0, arm1 called first → contention, is_winner."""
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
    peer = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.05, "j5": 1.0}

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
    peer_arm2 = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.02, "j5": 1.0}

    # arm1 goes first to claim the win
    policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints={"j1": 0, "j2": 0, "j3": 0, "j4": -0.02, "j5": 1.0},
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
# Test 11: contention threshold boundary at 0.110 (NOT contention)
# ---------------------------------------------------------------------------


def test_contention_threshold_boundary_at_0110():
    """Gap of exactly 0.110 is NOT contention (strictly less than)."""
    policy = SequentialPickPolicy()
    result = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_BOUNDARY,
        peer_joints=PEER_BOUNDARY_AT,
    )
    assert result == (OWN_BOUNDARY, False, False, False)


# ---------------------------------------------------------------------------
# Test 12: contention threshold boundary below 0.110 (IS contention)
# ---------------------------------------------------------------------------


def test_contention_threshold_boundary_below_0110():
    """Gap of 0.109 IS contention."""
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


# ---------------------------------------------------------------------------
# Test 13: non-default arm IDs (arm2 + arm3) — winner must be one of them
# ---------------------------------------------------------------------------


def test_contention_with_arm2_arm3_pair_produces_a_winner():
    """When arm_ids are arm2 and arm3, exactly one must be winner per step.

    Regression: SequentialPickPolicy hardcoded winner_arm as 'arm1'/'arm2',
    so arm2+arm3 pairs always got is_winner=False for both arms — causing
    next(a for a in arm_execute_args if winner_flags[a]) to raise StopIteration
    in RunController, hanging the run permanently.
    """
    policy = SequentialPickPolicy()
    result2 = policy.apply(
        step_id=1,
        arm_id="arm2",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    result3 = policy.apply(
        step_id=1,
        arm_id="arm3",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    _, _, is_contention2, is_winner2 = result2
    _, _, is_contention3, is_winner3 = result3

    assert is_contention2 is True, "arm2 must detect contention"
    assert is_contention3 is True, "arm3 must detect contention"
    # Exactly one of the two arms must be winner — never both False
    assert is_winner2 or is_winner3, (
        "At least one arm must be winner; got is_winner2=%s is_winner3=%s "
        "(regression: hardcoded 'arm1'/'arm2' IDs caused both to be False)" % (
            is_winner2, is_winner3
        )
    )
    assert not (is_winner2 and is_winner3), "Both arms cannot be winners simultaneously"


def test_second_contention_step_does_not_crash_when_peer_skipped_at_first_contention_step():
    """No IndexError when the peer arm was skipped (unreachable) at the first contention step.

    Regression: if arm1 enters contention at step 0 but arm2 is skipped (unreachable),
    _arm_slots ends up with only ["arm1"]. On the next contention step _turn=1, which
    causes _arm_slots[1] IndexError.
    """
    p = SequentialPickPolicy()

    # Step 0: arm1 enters contention, arm2 is unreachable and NEVER calls apply().
    # arm1 wins, _turn advances to 1, _arm_slots = ["arm1"].
    p.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )

    # Step 1: both arms call apply() — _turn=1, _arm_slots still only has "arm1".
    # Must not raise IndexError.
    result1 = p.apply(
        step_id=1,
        arm_id="arm1",
        own_joints=OWN_CONTENTION,
        peer_joints=PEER_CONTENTION,
    )
    result2 = p.apply(
        step_id=1,
        arm_id="arm2",
        own_joints=PEER_CONTENTION,
        peer_joints=OWN_CONTENTION,
    )

    _, _, is_contention1, is_winner1 = result1
    _, _, is_contention2, is_winner2 = result2
    assert is_contention1 is True
    assert is_contention2 is True
    # Exactly one winner
    assert is_winner1 or is_winner2, "At least one arm must be winner at step 1"
    assert not (is_winner1 and is_winner2), "Both arms cannot be winners simultaneously"


# ---------------------------------------------------------------------------
# Test 14: CONTENTION_THRESHOLD must be 0.110 m
# ---------------------------------------------------------------------------


def test_contention_threshold_constant_is_0110m():
    """CONTENTION_THRESHOLD must be 0.110 m."""
    assert SequentialPickPolicy.CONTENTION_THRESHOLD == 0.110


def test_contention_threshold_boundary_at_0110():
    """Gap of exactly 0.110 is NOT contention (strictly less than)."""
    policy = SequentialPickPolicy()
    own = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
    peer = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.110, "j5": 1.0}
    result = policy.apply(step_id=0, arm_id="arm1", own_joints=own, peer_joints=peer)
    assert result == (own, False, False, False)


def test_contention_threshold_boundary_below_0110():
    """Gap of 0.109 IS contention."""
    policy = SequentialPickPolicy()
    own = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
    peer = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.109, "j5": 1.0}
    result = policy.apply(step_id=0, arm_id="arm1", own_joints=own, peer_joints=peer)
    applied, skipped, is_contention, is_winner = result
    assert is_contention is True
    assert is_winner is True
