"""Sequential-pick policy for Mode 3: SEQUENTIAL_PICK.

Detects contention when both arms target nearby j4 positions (gap < 0.10m)
and both are extending (j5 > 0). Alternates winner turn between arms.
Winner and loser both receive unmodified joints — RunController handles
dispatch ordering (winner first, then loser).

Returns 4-tuple: (applied_joints, skipped, is_contention, is_winner)
- applied_joints: always the unmodified own_joints
- skipped: always False (sequential pick never skips)
- is_contention: True when gap < 0.10 and both j5 > 0
- is_winner: True for the arm whose turn it is at this step

The winner is determined by a two-slot roster (_arm_slots[0] / _arm_slots[1])
built on first contention contact, rather than hardcoded "arm1"/"arm2" strings.
This makes the policy correct for any arm pair (arm1+arm2, arm2+arm3, etc.).
"""


class SequentialPickPolicy:
    """Alternating-turn contention arbitration for sequential pick mode."""

    CONTENTION_THRESHOLD = 0.10

    def __init__(self) -> None:
        self._turn: int = 0  # index into _arm_slots: 0 or 1
        self._current_step_id: int | None = None
        self._step_turn: int = 0  # the locked turn for the current step
        # Two-slot roster: populated on first contention contact.
        # Slot 0 = first arm_id seen in contention; slot 1 = the other arm.
        self._arm_slots: list[str] = []

    def apply(
        self,
        step_id: int,
        arm_id: str,
        own_joints: dict,
        peer_joints: dict | None,
    ) -> tuple[dict, bool, bool, bool]:
        """Apply sequential-pick policy.

        Returns: (applied_joints, skipped, is_contention, is_winner)
        """
        # No peer → no contention possible
        if peer_joints is None:
            return (own_joints, False, False, False)

        # Compute j4 gap
        gap = abs(own_joints["j4"] - peer_joints["j4"])

        # No contention if gap at or above threshold, or either arm not extending
        if (
            gap >= self.CONTENTION_THRESHOLD
            or own_joints["j5"] <= 0
            or peer_joints["j5"] <= 0
        ):
            return (own_joints, False, False, False)

        # Register arm_id into the two-slot roster on first contact.
        if arm_id not in self._arm_slots:
            self._arm_slots.append(arm_id)

        # Contention detected — lock turn for this step_id
        if self._current_step_id != step_id:
            self._current_step_id = step_id
            self._step_turn = self._turn

        # Winner is the arm in slot _step_turn.
        # If the roster is not yet fully populated (only one arm seen so far,
        # e.g. because the peer was skipped as unreachable at the previous step),
        # clamp _step_turn to the last valid index so we never IndexError.
        # Write the clamped value back so all calls within this step agree on
        # the same winner slot. Once the peer registers, normal alternation resumes.
        if self._arm_slots:
            self._step_turn = min(self._step_turn, len(self._arm_slots) - 1)
            winner_arm = self._arm_slots[self._step_turn]
        else:
            winner_arm = arm_id
        is_winner = arm_id == winner_arm

        if is_winner:
            # Advance turn for next step using the (possibly clamped) step_turn.
            self._turn = 1 - self._step_turn

        return (own_joints, False, True, is_winner)


# Backward-compatible alias for existing imports
WaitModePolicy = SequentialPickPolicy


# Backward-compatible alias for existing imports
WaitModePolicy = SequentialPickPolicy
