"""Wait-mode policy for Mode 3: OVERLAP_ZONE_WAIT.

Implements alternating-turn arbitration with timeout-driven skip.

Design note: RunController processes both arms sequentially within a step_id.
The policy uses a "pending turn advance" pattern to ensure the turn advances
only once per step_id (after both arms have been processed), preventing both
arms from winning in the same step.
"""

from overlap_zone_state import OverlapZoneState


class WaitModePolicy:
    """Alternating-turn wait arbitration with timeout-driven skip."""

    def __init__(self, timeout_steps: int = 1) -> None:
        self._turn: int = 0  # 0 = arm1's turn, 1 = arm2's turn
        self._timeout_steps = timeout_steps
        self._wait_counts: dict[str, int] = {"arm1": 0, "arm2": 0}
        self._overlap = OverlapZoneState()
        self._turn_map: dict[int, str] = {0: "arm1", 1: "arm2"}
        # Pending turn advance: set to new turn value at first arm, committed at second.
        # This ensures the effective turn for both arms in the same step is the same.
        self._current_step_id: int | None = None
        self._step_turn: int = 0  # the locked turn for the current step

    def apply(
        self,
        step_id: int,
        arm_id: str,
        own_joints: dict,
        peer_joints: dict | None,
    ) -> tuple[dict, bool]:
        """Apply wait-mode policy.

        Returns: (applied_joints, skipped)
            - applied_joints: joints after policy (j5 may be zeroed)
            - skipped: True if this pick was skipped due to timeout
        """
        # Lock in the turn for this step_id on the first arm processed.
        # Both arms in the same step use the same locked turn value.
        if self._current_step_id != step_id:
            self._current_step_id = step_id
            self._step_turn = self._turn

        # No peer → no contention possible, pass through
        if peer_joints is None:
            return own_joints, False

        # Not in overlap zone → pass through
        if not self._overlap.is_in_overlap_zone(own_joints, peer_joints):
            return own_joints, False

        # In overlap zone but no contention (peer j5 == 0) → pass through
        if not self._overlap.detect_contention(own_joints, peer_joints):
            return own_joints, False

        # Contention detected — apply turn-based arbitration using the locked step turn
        winner_arm = self._turn_map[self._step_turn]

        if arm_id == winner_arm:
            # This arm wins the turn — pick proceeds.
            # Advance the underlying turn so the NEXT step uses the alternated value.
            self._wait_counts[arm_id] = 0
            self._turn = 1 - self._step_turn  # advance for next step
            return own_joints, False
        else:
            # This arm must wait
            wait_count = self._wait_counts[arm_id]
            if wait_count >= self._timeout_steps:
                # Timeout: skip this pick, advance turn, reset wait count
                self._wait_counts[arm_id] = 0
                self._turn = 1 - self._step_turn
                applied = dict(own_joints)
                applied["j5"] = 0.0
                return applied, True
            else:
                # Still waiting: zero j5 but do NOT skip
                self._wait_counts[arm_id] = wait_count + 1
                applied = dict(own_joints)
                applied["j5"] = 0.0
                return applied, False
