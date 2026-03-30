"""
geometry_check.py — two-stage geometry collision avoidance for dual-arm cotton picker.

Stage 1: GeometryStage1Screen
    Quick end-effector distance screen.
    Uses the lateral (j4) distance as a proxy for 3D end-effector proximity.
    Threshold: 0.08 m (safe/risky split).
    - distance >= 0.08 m → "safe"  (Stage 2 skipped)
    - distance <  0.08 m → "risky" (proceed to Stage 2)

Stage 2: GeometryStage2Check
    Better geometry / link-level unsafe-case check.
    Examines both the lateral gap AND the combined j5 extension.
    Two conditions must BOTH be true for "unsafe":
      1. |j4_own - j4_peer| < 0.06 m  (laterally close)
      2. (j5_own + j5_peer)  > 0.5    (combined extension large enough to collide)
    If either condition is false → "safe".
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Stage 1 thresholds
# ---------------------------------------------------------------------------
_STAGE1_SAFE_THRESHOLD = 0.08  # m — lateral gap below this is "risky"

# ---------------------------------------------------------------------------
# Stage 2 thresholds
# ---------------------------------------------------------------------------
_STAGE2_LATERAL_UNSAFE = 0.06   # m — lateral gap must be < this to be unsafe
_STAGE2_COMBINED_J5_UNSAFE = 0.5  # — combined extension must be > this to be unsafe


class GeometryStage1Screen:
    """Quick end-effector distance screen (Stage 1).

    Classifies a dual-arm motion as "safe" or "risky" based on the lateral
    (j4) distance between the two arms' end-effectors.
    """

    def screen(self, own_joints: dict, peer_joints: dict) -> str:
        """Classify the motion geometry at Stage 1.

        Args:
            own_joints:  {"j3": float, "j4": float, "j5": float}
            peer_joints: {"j3": float, "j4": float, "j5": float}

        Returns:
            "safe"  if lateral distance >= _STAGE1_SAFE_THRESHOLD
            "risky" if lateral distance <  _STAGE1_SAFE_THRESHOLD
        """
        lateral_gap = abs(own_joints["j4"] - peer_joints["j4"])
        if lateral_gap >= _STAGE1_SAFE_THRESHOLD:
            return "safe"
        return "risky"


class GeometryStage2Check:
    """Better geometry / link-level unsafe-case check (Stage 2).

    Invoked only when Stage 1 returned "risky".  Examines the combined j5
    extension in addition to the lateral gap to detect imminent link collision.
    """

    def check(self, own_joints: dict, peer_joints: dict) -> str:
        """Perform the Stage 2 geometry check.

        Args:
            own_joints:  {"j3": float, "j4": float, "j5": float}
            peer_joints: {"j3": float, "j4": float, "j5": float}

        Returns:
            "unsafe" if the combined geometry indicates imminent collision
            "safe"   otherwise
        """
        lateral_gap = abs(own_joints["j4"] - peer_joints["j4"])
        combined_extension = own_joints["j5"] + peer_joints["j5"]

        laterally_close = lateral_gap < _STAGE2_LATERAL_UNSAFE
        over_extended = combined_extension > _STAGE2_COMBINED_J5_UNSAFE

        if laterally_close and over_extended:
            return "unsafe"
        return "safe"
