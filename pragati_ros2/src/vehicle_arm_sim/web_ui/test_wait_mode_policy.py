"""Tests for WaitModePolicy — Mode 3: OVERLAP_ZONE_WAIT."""

import pytest
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
    applied, skipped = policy.apply(step_id=0, arm_id="arm1", own_joints=joints_in, peer_joints=None)
    assert applied == joints_in
    assert skipped is False


# ---------------------------------------------------------------------------
# Test 2: outside overlap zone → pass-through unchanged
# ---------------------------------------------------------------------------


def test_wait_mode_policy_outside_overlap_zone_passes_through():
    policy = WaitModePolicy()
    # |own j4 0.0 - peer j4 0.20| = 0.20 >= OVERLAP_THRESHOLD (0.10)
    applied, skipped = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_OUTSIDE,
        peer_joints=PEER_OUTSIDE,
    )
    assert applied == OWN_OUTSIDE
    assert skipped is False


# ---------------------------------------------------------------------------
# Test 3: in overlap zone but peer j5 == 0 → no contention, pass-through
# ---------------------------------------------------------------------------


def test_wait_mode_policy_overlap_zone_no_contention_passes_through():
    policy = WaitModePolicy()
    applied, skipped = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_NOT_EXTENDING,
    )
    assert applied == OWN_IN_OVERLAP
    assert skipped is False


# ---------------------------------------------------------------------------
# Test 4: arm1 wins on its turn (turn=0) when contention is detected
# ---------------------------------------------------------------------------


def test_wait_mode_policy_arm1_wins_on_its_turn_on_contention():
    """turn=0 means arm1's turn; arm1 should pass through unchanged, not skipped."""
    policy = WaitModePolicy()  # turn starts at 0 → arm1's turn
    applied, skipped = policy.apply(
        step_id=0,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert applied["j5"] == OWN_IN_OVERLAP["j5"]  # j5 unchanged
    assert applied == OWN_IN_OVERLAP
    assert skipped is False


# ---------------------------------------------------------------------------
# Test 5: arm2 blocked when it's arm1's turn (wait count not yet at timeout)
# ---------------------------------------------------------------------------


def test_wait_mode_policy_arm2_blocked_when_arm1_turn():
    """turn=0 (arm1's turn); arm2 contends → arm2 j5 zeroed, skipped=False (still waiting)."""
    policy = WaitModePolicy(timeout_steps=2)  # timeout=2 so one wait does not skip
    applied, skipped = policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert applied["j5"] == 0
    assert skipped is False


# ---------------------------------------------------------------------------
# Test 6: arm2 skipped after timeout (timeout_steps=1)
# ---------------------------------------------------------------------------


def test_wait_mode_policy_arm2_skipped_after_timeout():
    """With timeout_steps=1: first call increments wait_count to 1; second call
    triggers skip (wait_count >= timeout_steps)."""
    policy = WaitModePolicy(timeout_steps=1)

    # First block: wait_count becomes 1
    applied1, skipped1 = policy.apply(
        step_id=0,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert applied1["j5"] == 0
    assert skipped1 is False

    # Second block: wait_count(1) >= timeout_steps(1) → skip
    applied2, skipped2 = policy.apply(
        step_id=1,
        arm_id="arm2",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert applied2["j5"] == 0
    assert skipped2 is True


# ---------------------------------------------------------------------------
# Test 7: turn advances after arm1 wins (contention detected)
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

    # Now turn=1 → arm2's turn; arm1 should be blocked
    applied, skipped = policy.apply(
        step_id=1,
        arm_id="arm1",
        own_joints=OWN_IN_OVERLAP,
        peer_joints=PEER_IN_OVERLAP,
    )
    assert applied["j5"] == 0  # arm1 now blocked (it's arm2's turn)
    assert skipped is False
