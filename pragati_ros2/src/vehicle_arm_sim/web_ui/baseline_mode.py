"""
baseline_mode.py – collision avoidance mode logic for dual-arm cotton-picking robot.

Modes
-----
0  UNRESTRICTED           : pass joints through unchanged.
1  BASELINE_J5_BLOCK_SKIP : zero out j5 (extension) when peer arm is active at
                            this step AND the lateral gap |j4_own - j4_peer| < 0.05 m.
2  GEOMETRY_BLOCK         : two-stage geometry check.  Stage 1 screens on lateral
                            distance (< 0.12 m → risky).  Stage 2 checks the
                            combined j5 extension (> 0.5) AND close lateral gap
                            (< 0.06 m) → unsafe → zero out j5.
3  SEQUENTIAL_PICK        : sequential two-phase dispatch.  When both arms contend
                             at the same step (|j4_gap| < 0.10 m and both extending),
                             the winner arm is dispatched first, waits for completion,
                             then the loser arm is dispatched.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from geometry_check import GeometryStage1Screen, GeometryStage2Check
from sequential_pick_policy import SequentialPickPolicy

if TYPE_CHECKING:  # pragma: no cover
    from arm_runtime import PeerStatePacket

_stage1 = GeometryStage1Screen()
_stage2 = GeometryStage2Check()


class BaselineMode:
    UNRESTRICTED = 0
    BASELINE_J5_BLOCK_SKIP = 1
    GEOMETRY_BLOCK = 2
    SEQUENTIAL_PICK = 3

    def __init__(self) -> None:
        self._wait_policy = SequentialPickPolicy()

    def apply(
        self,
        mode: int,
        own_joints: dict,
        peer_state: "PeerStatePacket | None",
    ) -> dict:
        """Apply mode logic to joints.

        Args:
            mode: 0=unrestricted, 1=baseline_j5_block_skip, 2=geometry_block,
                  3=sequential_pick
            own_joints: {"j3": float, "j4": float, "j5": float}
            peer_state: peer arm's PeerStatePacket or None

        Returns:
            Modified joints dict (may be same or different from own_joints).
            For sequential_pick use apply_with_skip() to also get the skipped flag.
        """
        joints, _ = self.apply_with_skip(mode, own_joints, peer_state)
        return joints

    def apply_with_skip(
        self,
        mode: int,
        own_joints: dict,
        peer_state: "PeerStatePacket | None",
        step_id: int = 0,
        arm_id: str = "arm1",
    ) -> tuple[dict, bool]:
        """Apply mode logic and return (applied_joints, skipped).

        Args:
            mode: 0=unrestricted, 1=baseline_j5_block_skip, 2=geometry_block,
                  3=sequential_pick
            own_joints: {"j3": float, "j4": float, "j5": float}
            peer_state: peer arm's PeerStatePacket or None
            step_id: current step identifier (used by sequential_pick)
            arm_id: "arm1" or "arm2" (used by sequential_pick)

        Returns:
            (applied_joints, skipped) where skipped is True only when
            sequential_pick times out and skips a pick.
        """
        if mode == self.UNRESTRICTED:
            return own_joints, False

        if mode == self.BASELINE_J5_BLOCK_SKIP:
            return self._apply_baseline_j5_block_skip(own_joints, peer_state), False

        if mode == self.GEOMETRY_BLOCK:
            return self._apply_geometry_block(own_joints, peer_state), False

        if mode == self.SEQUENTIAL_PICK:
            return self._apply_overlap_zone_wait(own_joints, peer_state, step_id, arm_id)

        raise ValueError(f"Unknown mode: {mode!r}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_baseline_j5_block_skip(
        self,
        own_joints: dict,
        peer_state: "PeerStatePacket | None",
    ) -> dict:
        """Block j5 if peer is active and laterally close (|j4_own - j4_peer| < 0.05)."""
        if peer_state is None:
            return own_joints

        peer_joints = peer_state.candidate_joints
        if peer_joints is None:
            # Peer is idle at this step – no collision risk.
            return own_joints

        lateral_gap = abs(own_joints["j4"] - peer_joints["j4"])
        if lateral_gap < 0.05:
            # Collision risk: suppress extension.
            return {**own_joints, "j5": 0.0}

        return own_joints

    def _apply_geometry_block(
        self,
        own_joints: dict,
        peer_state: "PeerStatePacket | None",
    ) -> dict:
        """Two-stage geometry check.

        Stage 1: quick lateral-distance screen (threshold 0.12 m).
          → "safe"  : return joints unchanged.
          → "risky" : proceed to Stage 2.

        Stage 2: link-level check (lateral gap < 0.06 m AND combined j5 > 0.5).
          → "safe"   : return joints unchanged.
          → "unsafe" : zero out j5 (block the pick immediately).
        """
        if peer_state is None:
            return own_joints

        peer_joints = peer_state.candidate_joints
        if peer_joints is None:
            # Peer is idle at this step – no collision risk.
            return own_joints

        stage1_result = _stage1.screen(own_joints, peer_joints)
        if stage1_result == "safe":
            return own_joints

        # Stage 1 flagged risky – consult Stage 2.
        stage2_result = _stage2.check(own_joints, peer_joints)
        if stage2_result == "unsafe":
            return {**own_joints, "j5": 0.0}

        return own_joints

    def _apply_overlap_zone_wait(
        self,
        own_joints: dict,
        peer_state: "PeerStatePacket | None",
        step_id: int,
        arm_id: str,
    ) -> tuple[dict, bool]:
        """Overlap-zone wait arbitration (Mode 3).

        Delegates to SequentialPickPolicy which tracks turn state.
        Returns (applied_joints, skipped).
        """
        peer_joints = None
        if peer_state is not None:
            peer_joints = peer_state.candidate_joints
        applied, skipped, _is_contention, _is_winner = self._wait_policy.apply(
            step_id, arm_id, own_joints, peer_joints
        )
        return applied, skipped
