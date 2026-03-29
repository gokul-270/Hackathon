#!/usr/bin/env python3
"""End-to-end architecture alignment tests for the dual-arm phase-3 runtime.

Covers:
  - Runtime separation: each ArmRuntime is a self-contained, independent unit.
  - Peer transport: state flows through LocalPeerTransport between arms.
  - Launch registry: get_runtime_manifest() is coherent with ARM_RUNTIME_IDS and
    HACKATHON_BACKEND_PORT.
  - Full flow: RunController orchestrates all 5 modes and produces step reports.
"""

import pytest

from arm_runtime import ArmRuntime, PeerStatePacket
from arm_runtime_registry import ARM_RUNTIME_IDS, HACKATHON_BACKEND_PORT, get_runtime_manifest
from baseline_mode import BaselineMode
from peer_transport import LocalPeerTransport
from run_controller import RunController
from scenario_json import ScenarioStep  # noqa: F401 — imported for type clarity

# ---------------------------------------------------------------------------
# Shared scenario fixture
# ---------------------------------------------------------------------------

_PAIRED_SCENARIO = {
    "steps": [
        {"step_id": 1, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.0, "cam_z": 0.5},
        {"step_id": 1, "arm_id": "arm2", "cam_x": -0.3, "cam_y": 0.0, "cam_z": 0.5},
        {"step_id": 2, "arm_id": "arm1", "cam_x": 0.4, "cam_y": 0.1, "cam_z": 0.4},
        {"step_id": 2, "arm_id": "arm2", "cam_x": -0.4, "cam_y": 0.1, "cam_z": 0.4},
    ]
}


def _make_scenario_steps(scenario: dict) -> list:
    """Convert raw scenario dict into ScenarioStep objects."""
    return [
        ScenarioStep(
            step_id=int(r["step_id"]),
            arm_id=str(r["arm_id"]),
            cam_x=float(r["cam_x"]),
            cam_y=float(r["cam_y"]),
            cam_z=float(r["cam_z"]),
        )
        for r in scenario["steps"]
    ]


# ===========================================================================
# Architecture shape tests (runtime separation)
# ===========================================================================


def test_e2e_each_arm_runtime_has_independent_step_list():
    """Two ArmRuntime instances loaded with a dual-arm scenario each own only their steps."""
    steps = _make_scenario_steps(_PAIRED_SCENARIO)

    arm1 = ArmRuntime("arm1")
    arm2 = ArmRuntime("arm2")
    arm1.load_scenario(steps)
    arm2.load_scenario(steps)

    arm1_step_ids = {s.step_id for s in arm1.get_own_steps()}
    arm2_step_ids = {s.step_id for s in arm2.get_own_steps()}
    arm1_arm_ids = {s.arm_id for s in arm1.get_own_steps()}
    arm2_arm_ids = {s.arm_id for s in arm2.get_own_steps()}

    assert arm1_arm_ids == {"arm1"}, (
        f"arm1 runtime should only contain arm1 steps, got arm_ids={arm1_arm_ids}"
    )
    assert arm2_arm_ids == {"arm2"}, (
        f"arm2 runtime should only contain arm2 steps, got arm_ids={arm2_arm_ids}"
    )
    assert arm1_step_ids == {1, 2}
    assert arm2_step_ids == {1, 2}


def test_e2e_arm_runtime_run_step_is_self_contained():
    """ArmRuntime.run_step() can be called directly without a RunController."""
    steps = _make_scenario_steps(_PAIRED_SCENARIO)

    arm1 = ArmRuntime("arm1")
    arm1.load_scenario(steps)

    baseline = BaselineMode()
    current_joints = {"j3": 0.0, "j4": 0.0, "j5": 0.0}

    result = arm1.run_step(
        step_id=1,
        peer_state=None,
        mode=BaselineMode.UNRESTRICTED,
        baseline_mode_obj=baseline,
        current_joints=current_joints,
    )

    assert isinstance(result, tuple), "run_step must return a tuple"
    assert len(result) == 3, "run_step must return a 3-tuple (applied, skipped, candidate)"
    applied_joints, skipped, candidate_joints = result
    assert isinstance(applied_joints, dict), "applied_joints must be a dict"
    assert isinstance(skipped, bool), "skipped must be a bool"
    assert isinstance(candidate_joints, dict), "candidate_joints must be a dict"
    assert "j3" in applied_joints and "j4" in applied_joints and "j5" in applied_joints


def test_e2e_run_controller_manages_two_distinct_arm_runtime_units():
    """RunController has _arm1 and _arm2 attributes that are distinct ArmRuntime instances."""
    rc = RunController()

    assert hasattr(rc, "_arm1"), "RunController must have _arm1 attribute"
    assert hasattr(rc, "_arm2"), "RunController must have _arm2 attribute"
    assert isinstance(rc._arm1, ArmRuntime), "_arm1 must be an ArmRuntime instance"
    assert isinstance(rc._arm2, ArmRuntime), "_arm2 must be an ArmRuntime instance"
    assert rc._arm1 is not rc._arm2, "_arm1 and _arm2 must be distinct objects"
    assert rc._arm1._arm_id != rc._arm2._arm_id, (
        f"_arm1 and _arm2 must have different arm_ids, "
        f"got {rc._arm1._arm_id!r} and {rc._arm2._arm_id!r}"
    )
    assert rc._arm1._arm_id == "arm1"
    assert rc._arm2._arm_id == "arm2"


# ===========================================================================
# Peer transport tests (explicit transport path)
# ===========================================================================


def test_e2e_peer_state_flows_through_transport_during_run():
    """After a run with a paired scenario, the transport contains at least one packet."""
    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(_PAIRED_SCENARIO)
    rc.run()

    assert hasattr(rc, "_transport"), "RunController must expose _transport"
    # The transport mailbox should have packets for the last published step
    transport: LocalPeerTransport = rc._transport
    packet_arm1 = transport.receive("arm1")
    packet_arm2 = transport.receive("arm2")
    assert packet_arm1 is not None or packet_arm2 is not None, (
        "Transport must hold at least one peer-state packet after a run"
    )


def test_e2e_transport_reset_clears_peer_state_between_runs():
    """After rc.reset(), the transport is empty — no stale peer state crosses runs."""
    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(_PAIRED_SCENARIO)
    rc.run()

    # Confirm something was published
    assert rc._transport.receive("arm1") is not None or rc._transport.receive("arm2") is not None

    rc.reset()

    assert rc._transport.receive("arm1") is None, (
        "Transport must be empty after reset — arm1 packet should be gone"
    )
    assert rc._transport.receive("arm2") is None, (
        "Transport must be empty after reset — arm2 packet should be gone"
    )


def test_e2e_peer_transport_publish_receive_roundtrip():
    """LocalPeerTransport preserves candidate_joints through a publish/receive cycle."""
    transport = LocalPeerTransport()
    candidate = {"j3": 1.23, "j4": 0.45, "j5": 0.67, "reachable": True}
    packet = PeerStatePacket(
        arm_id="arm1",
        step_id=5,
        status="ready",
        timestamp=0.0,
        current_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
        candidate_joints=candidate,
    )

    transport.publish(packet)
    received = transport.receive("arm1")

    assert received is not None, "receive() must return the published packet"
    assert received.arm_id == "arm1"
    assert received.step_id == 5
    assert received.candidate_joints == candidate, (
        f"candidate_joints must be preserved intact, "
        f"expected {candidate!r}, got {received.candidate_joints!r}"
    )


# ===========================================================================
# Launch registry tests
# ===========================================================================


def test_e2e_runtime_manifest_covers_all_arm_ids():
    """get_runtime_manifest() arm_ids exactly match ARM_RUNTIME_IDS."""
    manifest = get_runtime_manifest()
    manifest_arm_ids = {d.arm_id for d in manifest}

    assert manifest_arm_ids == set(ARM_RUNTIME_IDS), (
        f"Manifest arm_ids {manifest_arm_ids!r} do not match "
        f"ARM_RUNTIME_IDS {set(ARM_RUNTIME_IDS)!r}"
    )


def test_e2e_runtime_manifest_port_matches_backend_constant():
    """Every descriptor in the manifest uses HACKATHON_BACKEND_PORT."""
    manifest = get_runtime_manifest()

    for descriptor in manifest:
        assert descriptor.port == HACKATHON_BACKEND_PORT, (
            f"Descriptor for {descriptor.arm_id!r} has port={descriptor.port}, "
            f"expected HACKATHON_BACKEND_PORT={HACKATHON_BACKEND_PORT}"
        )


# ===========================================================================
# Full flow integration
# ===========================================================================


def test_e2e_full_architecture_run_produces_reports_for_all_modes():
    """Running a paired scenario through all 5 modes produces non-empty step reports."""
    modes = [
        BaselineMode.UNRESTRICTED,
        BaselineMode.BASELINE_J5_BLOCK_SKIP,
        BaselineMode.GEOMETRY_BLOCK,
        BaselineMode.SEQUENTIAL_PICK,
        BaselineMode.SMART_REORDER,
    ]

    for mode in modes:
        rc = RunController(mode=mode)
        rc.load_scenario(_PAIRED_SCENARIO)
        summary = rc.run()

        assert isinstance(summary, dict), f"run() must return a dict for mode={mode}"
        step_reports = summary.get("step_reports", [])
        assert len(step_reports) > 0, (
            f"Mode {mode}: run() produced zero step reports — expected non-empty step_reports"
        )


def test_e2e_architecture_transport_and_registry_coherent():
    """Manifest arm count equals the number of distinct ArmRuntime instances in RunController."""
    manifest = get_runtime_manifest()
    rc = RunController()

    manifest_count = len(manifest)
    # RunController holds exactly one ArmRuntime per arm in the registry
    runtime_arm_ids = {rc._arm1._arm_id, rc._arm2._arm_id, rc._arm3._arm_id}

    assert manifest_count == len(runtime_arm_ids), (
        f"Registry lists {manifest_count} arms but RunController has "
        f"{len(runtime_arm_ids)} distinct arm runtimes"
    )
    assert runtime_arm_ids == set(ARM_RUNTIME_IDS), (
        f"RunController arm IDs {runtime_arm_ids!r} do not match "
        f"ARM_RUNTIME_IDS {set(ARM_RUNTIME_IDS)!r}"
    )
