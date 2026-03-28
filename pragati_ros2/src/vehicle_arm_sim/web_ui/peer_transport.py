#!/usr/bin/env python3
"""In-process peer-state transport for dual-arm coordination.

Provides an explicit transport abstraction that arms publish to and receive from.
The current implementation is a local in-process mailbox (no network, no threads),
swappable later for MQTT or ROS2 transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arm_runtime import PeerStatePacket


class LocalPeerTransport:
    """In-process mailbox transport for peer-state packets.

    Each arm publishes its latest PeerStatePacket here; the peer arm receives it.
    Publishing a second packet for the same arm_id replaces the first.
    """

    def __init__(self) -> None:
        self._mailbox: dict[str, "PeerStatePacket"] = {}

    def publish(self, packet: "PeerStatePacket") -> None:
        """Store the packet keyed by its arm_id, replacing any previous packet.

        Args:
            packet: The PeerStatePacket to store.
        """
        self._mailbox[packet.arm_id] = packet

    def receive(self, arm_id: str) -> "PeerStatePacket | None":
        """Return the latest packet published for the given arm_id, or None.

        Args:
            arm_id: The arm whose latest packet to retrieve.

        Returns:
            The most recently published PeerStatePacket for that arm, or None if
            no packet has been published yet.
        """
        return self._mailbox.get(arm_id)

    def reset(self) -> None:
        """Clear all stored packets, returning the transport to its initial state."""
        self._mailbox.clear()
