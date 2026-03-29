#!/usr/bin/env python3
"""Tests for LocalPeerTransport — in-process peer-state mailbox."""

import pytest

from arm_runtime import ArmRuntime, PeerStatePacket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_packet(arm_id: str = "arm1", step_id: int = 0) -> PeerStatePacket:
    """Build a minimal PeerStatePacket for a given arm_id."""
    rt = ArmRuntime(arm_id)
    return rt.build_peer_state(
        step_id=step_id,
        status="ready",
        current_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
        candidate_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
    )


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

def test_local_peer_transport_can_be_imported():
    """LocalPeerTransport can be imported from peer_transport module."""
    from peer_transport import LocalPeerTransport  # noqa: F401


# ---------------------------------------------------------------------------
# publish / receive tests
# ---------------------------------------------------------------------------

def test_receive_returns_none_when_no_packet_published():
    """receive returns None when no packet has been published for an arm_id."""
    from peer_transport import LocalPeerTransport

    transport = LocalPeerTransport()
    assert transport.receive("arm1") is None


def test_receive_returns_packet_after_publish():
    """receive returns the packet that was published for the matching arm_id."""
    from peer_transport import LocalPeerTransport

    transport = LocalPeerTransport()
    packet = _make_packet("arm1", step_id=0)
    transport.publish(packet)
    result = transport.receive("arm1")
    assert result is packet


def test_receive_returns_none_for_different_arm_id():
    """receive returns None when queried for an arm_id that has no published packet."""
    from peer_transport import LocalPeerTransport

    transport = LocalPeerTransport()
    packet = _make_packet("arm1", step_id=0)
    transport.publish(packet)
    assert transport.receive("arm2") is None


def test_publish_second_packet_replaces_first_for_same_arm_id():
    """Publishing a second packet for the same arm_id replaces the first (mailbox semantics)."""
    from peer_transport import LocalPeerTransport

    transport = LocalPeerTransport()
    first = _make_packet("arm1", step_id=0)
    second = _make_packet("arm1", step_id=1)
    transport.publish(first)
    transport.publish(second)
    result = transport.receive("arm1")
    assert result is second


def test_publish_packets_for_two_arms_stored_independently():
    """Packets for arm1 and arm2 are stored independently."""
    from peer_transport import LocalPeerTransport

    transport = LocalPeerTransport()
    p1 = _make_packet("arm1", step_id=0)
    p2 = _make_packet("arm2", step_id=0)
    transport.publish(p1)
    transport.publish(p2)
    assert transport.receive("arm1") is p1
    assert transport.receive("arm2") is p2


# ---------------------------------------------------------------------------
# RunController integration test
# ---------------------------------------------------------------------------

def test_run_controller_has_transport_attribute():
    """RunController exposes a _transport attribute after construction."""
    from run_controller import RunController

    ctrl = RunController()
    assert hasattr(ctrl, "_transport")


def test_run_controller_transport_is_local_peer_transport():
    """RunController._transport is a LocalPeerTransport instance."""
    from peer_transport import LocalPeerTransport
    from run_controller import RunController

    ctrl = RunController()
    assert isinstance(ctrl._transport, LocalPeerTransport)


# ---------------------------------------------------------------------------
# Issue 1: reset() must reset transport
# ---------------------------------------------------------------------------

def test_run_controller_reset_clears_transport():
    """reset() replaces _transport with a fresh LocalPeerTransport (no stale packets)."""
    from peer_transport import LocalPeerTransport
    from run_controller import RunController

    ctrl = RunController()
    # Manually publish a packet so the transport has state
    ctrl._transport.publish(_make_packet("arm1", step_id=0))
    assert ctrl._transport.receive("arm1") is not None

    ctrl.reset()

    # After reset, the transport must be fresh — no previously published packet
    assert ctrl._transport.receive("arm1") is None


# ---------------------------------------------------------------------------
# Issue 2: solo-step arms must also publish to transport
# ---------------------------------------------------------------------------

def test_solo_step_arm_publishes_to_transport():
    """An arm active at a solo step (no peer) still publishes its state to the transport."""
    from baseline_mode import BaselineMode
    from peer_transport import LocalPeerTransport
    from run_controller import RunController

    ctrl = RunController(mode=BaselineMode.UNRESTRICTED)
    ctrl.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    })
    ctrl.run()

    # arm1 ran solo — it must have published its state
    assert ctrl._transport.receive("arm1") is not None


# ---------------------------------------------------------------------------
# Issue 3: routing test — transport is actually used during a paired run
# ---------------------------------------------------------------------------

def test_run_controller_uses_transport_for_paired_step():
    """After a paired run, the transport holds at least one arm's published packet."""
    from arm_runtime import PeerStatePacket
    from baseline_mode import BaselineMode
    from run_controller import RunController

    ctrl = RunController(mode=BaselineMode.UNRESTRICTED)
    ctrl.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    })
    ctrl.run()

    arm1_packet = ctrl._transport.receive("arm1")
    arm2_packet = ctrl._transport.receive("arm2")
    # At least one arm must have published a PeerStatePacket
    assert isinstance(arm1_packet, PeerStatePacket) or isinstance(arm2_packet, PeerStatePacket)


# ---------------------------------------------------------------------------
# Issue 4: LocalPeerTransport.reset() clears all packets
# ---------------------------------------------------------------------------

def test_transport_reset_clears_all_packets():
    """reset() removes all previously published packets from the mailbox."""
    from peer_transport import LocalPeerTransport

    transport = LocalPeerTransport()
    transport.publish(_make_packet("arm1", step_id=0))
    transport.publish(_make_packet("arm2", step_id=0))
    assert transport.receive("arm1") is not None
    assert transport.receive("arm2") is not None

    transport.reset()

    assert transport.receive("arm1") is None
    assert transport.receive("arm2") is None


# ---------------------------------------------------------------------------
# Group 4 — Thread-safety
# ---------------------------------------------------------------------------


def test_peer_transport_is_thread_safe():
    """Two threads simultaneously publishing 1000 times each must not corrupt data."""
    import threading
    from peer_transport import LocalPeerTransport

    transport = LocalPeerTransport()
    errors = []

    def worker(arm_id):
        for i in range(1000):
            try:
                transport.publish(_make_packet(arm_id, step_id=i))
                _ = transport.receive(arm_id)
            except Exception as exc:
                errors.append(exc)

    t1 = threading.Thread(target=worker, args=("arm1",))
    t2 = threading.Thread(target=worker, args=("arm2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Thread safety errors in LocalPeerTransport: {errors}"
    # After all publishes, both arm_ids must have their latest packet
    assert transport.receive("arm1") is not None
    assert transport.receive("arm2") is not None
