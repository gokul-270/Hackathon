"""
baseline_mode.py – collision avoidance mode logic for dual-arm cotton-picking robot.

Modes
-----
0  UNRESTRICTED           : pass joints through unchanged.
1  BASELINE_J5_BLOCK_SKIP : zero out j5 (extension) when peer arm is active at
                            this step AND the lateral gap |j4_own - j4_peer| < 0.05 m.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from arm_runtime import PeerStatePacket


class BaselineMode:
    UNRESTRICTED = 0
    BASELINE_J5_BLOCK_SKIP = 1

    def apply(
        self,
        mode: int,
        own_joints: dict,
        peer_state: "PeerStatePacket | None",
    ) -> dict:
        """Apply mode logic to joints.

        Args:
            mode: 0=unrestricted, 1=baseline_j5_block_skip
            own_joints: {"j3": float, "j4": float, "j5": float}
            peer_state: peer arm's PeerStatePacket or None

        Returns:
            Modified joints dict (may be same or different from own_joints)
        """
        if mode == self.UNRESTRICTED:
            return own_joints

        if mode == self.BASELINE_J5_BLOCK_SKIP:
            return self._apply_baseline_j5_block_skip(own_joints, peer_state)

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
