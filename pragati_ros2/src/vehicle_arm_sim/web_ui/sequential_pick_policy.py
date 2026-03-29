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
"""


class SequentialPickPolicy:
    """Alternating-turn contention arbitration for sequential pick mode."""

    CONTENTION_THRESHOLD = 0.10

    def __init__(self) -> None:
        self._turn: int = 0  # 0 = arm1's turn, 1 = arm2's turn
        self._current_step_id: int | None = None
        self._step_turn: int = 0  # the locked turn for the current step

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

        # Contention detected — lock turn for this step_id
        if self._current_step_id != step_id:
            self._current_step_id = step_id
            self._step_turn = self._turn

        winner_arm = "arm1" if self._step_turn == 0 else "arm2"
        is_winner = arm_id == winner_arm

        if is_winner:
            # Advance turn for next step
            self._turn = 1 - self._step_turn

        return (own_joints, False, True, is_winner)


# Backward-compatible alias for existing imports
WaitModePolicy = SequentialPickPolicy
