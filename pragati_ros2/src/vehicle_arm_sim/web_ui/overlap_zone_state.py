"""Overlap zone state model for contention detection."""


class OverlapZoneState:
    """Tracks which arm currently occupies the overlap zone and detects contention."""

    OVERLAP_THRESHOLD = 0.10  # meters, |j4_own - j4_peer| < this means overlap zone

    def is_in_overlap_zone(self, own_joints: dict, peer_joints: dict) -> bool:
        """Returns True if both arms are within the overlap zone."""
        return abs(own_joints["j4"] - peer_joints["j4"]) < self.OVERLAP_THRESHOLD

    def detect_contention(self, own_joints: dict, peer_joints: dict) -> bool:
        """Returns True if both arms have non-zero j5 (extension) in the overlap zone."""
        return (
            self.is_in_overlap_zone(own_joints, peer_joints)
            and own_joints["j5"] > 0
            and peer_joints["j5"] > 0
        )
