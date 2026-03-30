"""Tests for WaitModePolicy (backward-compat shim) — Mode 3: SEQUENTIAL_PICK.

These tests verify the backward-compatibility shim in wait_mode_policy.py
correctly re-exports SequentialPickPolicy. The comprehensive tests for the
new 4-tuple API live in test_sequential_pick_policy.py (Group 2).

NOTE: The new SequentialPickPolicy returns a 4-tuple
(applied_joints, skipped, is_contention, is_winner). These tests unpack
all four values. The old timeout/j5-zeroing behavior has been removed —
the policy now returns unmodified joints for both winner and loser.
"""

from wait_mode_policy import WaitModePolicy

# ---------------------------------------------------------------------------
# Helper joint dicts
# ---------------------------------------------------------------------------

# Both arms at j4=0.0 → in overlap zone (|0.0 - 0.0| = 0.0 < 0.10)
OWN_IN_OVERLAP = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_IN_OVERLAP = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}

# Arm outside the overlap zone: |0.0 - 0.20| = 0.20 >= 0.10
OWN_OUTSIDE = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
PEER_OUTSIDE = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.20, "j5": 1.0}

# Peer with j5=0 (not extending) — no contention even when in overlap zone
PEER_NOT_EXTENDING = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 0.0}


# ---------------------------------------------------------------------------
# Test 1: no peer → pass-through unchanged
# ---------------------------------------------------------------------------


def test_wait_mode_policy_no_peer_passes_through():
    policy = WaitModePolicy()
    joints_in = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}
    applied, skipped, is_contention, is_winner = policy.apply(
        step_id=0, arm_id="arm1", own_joints=joints_in, peer_joints=None
    )
    assert applied == joints_in
    assert skipped is False
    assert is_contention is False
    assert is_winner is False


# ---------------------------------------------------------------------------
# Test 2: outside overlap zone → pass-through unchanged
# ---------------------------------------------------------------------------


def test_wait_mode_policy_outside_overlap_zone_passes_through():
    policy = WaitModePolicy()
    applied, skipped, is_contention, is_winner = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_OUTSIDE,
        peer_joints=PEER_OUTSIDE,
    )
    assert applied == OWN_OUTSIDE
    assert skipped is False
    assert is_contention is False


# ---------------------------------------------------------------------------
# Test 3: in overlap zone but peer j5 == 0 → no contention, pass-through
# ---------------------------------------------------------------------------


def test_wait_mode_policy_overlap_zone_no_contention_passes_through():
    policy = WaitModePolicy()
    applied, skipped, is_contention, is_winner = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_NOT_EXTENDING,
    )
    assert applied == OWN_IN_OVERLAP
    assert skipped is False
    assert is_contention is False


# ---------------------------------------------------------------------------
# Test 4: arm1 wins on its turn (turn=0) when contention is detected
# ---------------------------------------------------------------------------


def test_wait_mode_policy_arm1_wins_on_its_turn_on_contention():
    """turn=0 means arm1's turn; arm1 should pass through unchanged, not skipped."""
    policy = WaitModePolicy()  # turn starts at 0 → arm1's turn
    applied, skipped, is_contention, is_winner = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert applied["j5"] == OWN_IN_OVERLAP["j5"]  # j5 unchanged
    assert applied == OWN_IN_OVERLAP
    assert skipped is False
    assert is_contention is True
    assert is_winner is True


# ---------------------------------------------------------------------------
# Test 5: arm2 is loser when it's arm1's turn — joints unmodified
# ---------------------------------------------------------------------------


def test_wait_mode_policy_arm2_loser_when_arm1_turn():
    """turn=0 (arm1's turn); arm2 contends → arm2 is loser but joints unmodified.
    New behavior: policy never zeroes j5 — RunController handles dispatch order."""
    policy = WaitModePolicy()
    # arm1 goes first to lock the turn
    policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    applied, skipped, is_contention, is_winner = policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert applied == OWN_IN_OVERLAP  # joints unmodified
    assert skipped is False
    assert is_contention is True
    assert is_winner is False


# ---------------------------------------------------------------------------
# Test 6: turn advances after arm1 wins (contention detected)
# ---------------------------------------------------------------------------


def test_wait_mode_policy_turn_advances_after_arm1_wins():
    """After arm1 picks in overlap zone (contention), turn should advance to 1."""
    policy = WaitModePolicy()  # turn=0 → arm1's turn

    # arm1 wins contention → turn should become 1
    policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )

    # Now turn=1 → arm2's turn; arm2 should be winner
    _, _, is_contention, is_winner = policy.apply(
        step_id=1,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert is_contention is True
    assert is_winner is True


# ---------------------------------------------------------------------------
# Group 2 (Phase 2): paired-call at the SAME step_id — only one arm wins
# ---------------------------------------------------------------------------


def test_wait_mode_policy_paired_call_only_one_arm_wins_contention():
    """When both arms are called for the SAME step_id with contention, exactly one arm
    must win and the other must be the loser.
    """
    policy = WaitModePolicy()  # turn=0 → arm1's turn

    # arm1 processed first at step_id=0
    _, _, _, is_winner_arm1 = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    # arm2 processed second, same step_id=0
    _, _, _, is_winner_arm2 = policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )

    # Exactly one arm wins
    assert is_winner_arm1 != is_winner_arm2, (
        "Exactly one arm must win; got arm1=%s arm2=%s" % (is_winner_arm1, is_winner_arm2)
    )


def test_wait_mode_policy_paired_call_winner_arm_is_turn_holder():
    """With turn=0 (arm1's turn), arm1 must win the contention when both arms are
    processed at the same step_id.
    """
    policy = WaitModePolicy()  # turn=0 → arm1's turn

    _, _, _, is_winner_arm1 = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    _, _, _, is_winner_arm2 = policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )

    assert is_winner_arm1 is True, "arm1 should win (it's arm1's turn)"
    assert is_winner_arm2 is False, "arm2 should lose (it's not arm2's turn)"


def test_wait_mode_policy_paired_call_turn_advances_after_step():
    """After a paired step where arm1 wins, the next paired step should give arm2 the turn."""
    policy = WaitModePolicy()  # turn=0 → arm1's turn

    # Step 0: arm1 wins
    policy.apply(
        step_id=0, arm_id="arm1", own_joints=OWN_IN_OVERLAP, peer_joints=PEER_IN_OVERLAP
    )
    policy.apply(
        step_id=0, arm_id="arm2", own_joints=OWN_IN_OVERLAP, peer_joints=PEER_IN_OVERLAP
    )

    # Step 1: turn should have advanced to arm2
    _, _, _, is_winner_arm1_s1 = policy.apply(
        step_id=1,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    _, _, _, is_winner_arm2_s1 = policy.apply(
        step_id=1,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )

    assert is_winner_arm2_s1 is True, "arm2 should win step 1"
    assert is_winner_arm1_s1 is False, "arm1 should lose in step 1"
