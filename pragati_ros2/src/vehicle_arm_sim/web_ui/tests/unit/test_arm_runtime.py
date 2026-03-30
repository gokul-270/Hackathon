#!/usr/bin/env python3
"""Tests for arm_runtime module -- distributed arm runtime for dual-arm scenario."""

# ScenarioStep may not exist yet (parallel agent task). Define a minimal local version
# for testing purposes; import the real one if available.
try:
    from scenario_json import ScenarioStep
except ImportError:
    from dataclasses import dataclass

    @dataclass
    class ScenarioStep:
        step_id: int
        arm_id: str
        cam_x: float
        cam_y: float
        cam_z: float


# ---------------------------------------------------------------------------
# load_scenario tests
# ---------------------------------------------------------------------------


def test_load_scenario_filters_steps_to_own_arm_id():
    """load_scenario keeps only steps whose arm_id matches the runtime's arm_id."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    steps = [
        ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.1, cam_y=0.0, cam_z=0.02),
        ScenarioStep(step_id=2, arm_id="arm2", cam_x=0.2, cam_y=0.0, cam_z=0.03),
        ScenarioStep(step_id=3, arm_id="arm1", cam_x=0.3, cam_y=0.0, cam_z=0.01),
    ]
    rt.load_scenario(steps)
    own = rt.get_own_steps()
    assert len(own) == 2
    assert all(s.arm_id == "arm1" for s in own), (
        f"Expected only arm1 steps, got arm_ids={[s.arm_id for s in own]!r}"
    )
    got_ids = {s.step_id for s in own}
    assert got_ids == {1, 3}, f"Expected step_ids {{1, 3}}, got {got_ids!r}"


def test_load_scenario_with_wrong_arm_id_keeps_zero_steps():
    """load_scenario stores zero steps when no step matches the runtime's arm_id."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    steps = [
        ScenarioStep(step_id=1, arm_id="arm2", cam_x=0.1, cam_y=0.0, cam_z=0.02),
        ScenarioStep(step_id=2, arm_id="arm2", cam_x=0.2, cam_y=0.0, cam_z=0.03),
    ]
    rt.load_scenario(steps)
    assert len(rt.get_own_steps()) == 0


# ---------------------------------------------------------------------------
# get_own_steps tests
# ---------------------------------------------------------------------------


def test_get_own_steps_returns_empty_list_when_no_steps_for_arm():
    """get_own_steps returns an empty list when load_scenario has not been called."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm2")
    assert rt.get_own_steps() == []


# ---------------------------------------------------------------------------
# compute_candidate_joints tests
# ---------------------------------------------------------------------------


def test_compute_candidate_joints_returns_j3_key():
    """compute_candidate_joints result contains j3 with a finite float value."""
    import math
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "j3" in result
    assert isinstance(result["j3"], float), f"j3 must be float, got {type(result['j3'])}"
    assert math.isfinite(result["j3"]), f"j3 must be finite, got {result['j3']}"


def test_compute_candidate_joints_returns_j4_key():
    """compute_candidate_joints result contains j4 with a finite float value."""
    import math
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "j4" in result
    assert isinstance(result["j4"], float), f"j4 must be float, got {type(result['j4'])}"
    assert math.isfinite(result["j4"]), f"j4 must be finite, got {result['j4']}"


def test_compute_candidate_joints_returns_j5_key():
    """compute_candidate_joints result contains j5 with a finite float value."""
    import math
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "j5" in result
    assert isinstance(result["j5"], float), f"j5 must be float, got {type(result['j5'])}"
    assert math.isfinite(result["j5"]), f"j5 must be finite, got {result['j5']}"


def test_compute_candidate_joints_result_has_reachable_key():
    """compute_candidate_joints result contains reachable as a bool with correct value."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "reachable" in result
    assert isinstance(result["reachable"], bool), (
        f"reachable must be bool, got {type(result['reachable'])}"
    )
    assert result["reachable"] is True, (
        f"Known-good cam coords should be reachable, got reachable={result['reachable']}"
    )


# ---------------------------------------------------------------------------
# build_peer_state tests
# ---------------------------------------------------------------------------


def test_build_peer_state_returns_packet_with_correct_arm_id():
    """build_peer_state packet arm_id matches the runtime's arm_id."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    packet = rt.build_peer_state(
        step_id=1,
        status="idle",
        current_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
        candidate_joints=None,
    )
    assert packet.arm_id == "arm1"


def test_build_peer_state_sets_timestamp_as_float():
    """build_peer_state packet timestamp is a recent wall-clock time (not hardcoded 0.0)."""
    import time
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm2")
    before = time.time()
    packet = rt.build_peer_state(
        step_id=2,
        status="computing",
        current_joints={"j3": -0.3, "j4": 0.1, "j5": 0.05},
        candidate_joints={"j3": -0.4, "j4": 0.12, "j5": 0.08},
    )
    after = time.time()
    assert isinstance(packet.timestamp, float)
    assert before <= packet.timestamp <= after, (
        f"timestamp={packet.timestamp} must be between {before} and {after} "
        "(must use time.time(), not a hardcoded constant)"
    )


# ---------------------------------------------------------------------------
# run_step tests
# ---------------------------------------------------------------------------


def test_run_step_method_exists_on_arm_runtime():
    """ArmRuntime exposes a run_step method that accepts the expected signature."""
    from arm_runtime import ArmRuntime
    from baseline_mode import BaselineMode

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    rt.load_scenario([step])
    # Not just callable: must actually execute without error and return a tuple
    result = rt.run_step(
        step_id=1,
        peer_state=None,
        mode=BaselineMode.UNRESTRICTED,
        baseline_mode_obj=BaselineMode(),
        current_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
    )
    assert isinstance(result, tuple), f"run_step must return a tuple, got {type(result)}"


def test_run_step_returns_three_tuple():
    """run_step returns a 3-tuple (applied_joints dict, skipped bool, candidate_joints dict)."""
    from arm_runtime import ArmRuntime
    from baseline_mode import BaselineMode

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    rt.load_scenario([step])
    baseline = BaselineMode()

    result = rt.run_step(
        step_id=1,
        peer_state=None,
        mode=BaselineMode.UNRESTRICTED,
        baseline_mode_obj=baseline,
        current_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
    )

    assert isinstance(result, tuple)
    assert len(result) == 3
    applied_joints, skipped, candidate_joints = result
    assert isinstance(applied_joints, dict), (
        f"applied_joints must be a dict, got {type(applied_joints)}"
    )
    assert isinstance(skipped, bool), (
        f"skipped must be a bool, got {type(skipped)}"
    )
    assert isinstance(candidate_joints, dict), (
        f"candidate_joints must be a dict, got {type(candidate_joints)}"
    )
    assert "j3" in applied_joints and "j4" in applied_joints and "j5" in applied_joints


def test_run_step_unrestricted_no_peer_returns_candidate_as_applied():
    """run_step with UNRESTRICTED mode and no peer returns candidate_joints as applied_joints."""
    from arm_runtime import ArmRuntime
    from baseline_mode import BaselineMode

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    rt.load_scenario([step])
    baseline = BaselineMode()

    applied_joints, skipped, candidate_joints = rt.run_step(
        step_id=1,
        peer_state=None,
        mode=BaselineMode.UNRESTRICTED,
        baseline_mode_obj=baseline,
        current_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
    )

    assert applied_joints == candidate_joints
    assert skipped is False


def test_run_step_baseline_j5_block_skip_close_peer_zeroes_j5():
    """run_step with BASELINE_J5_BLOCK_SKIP and a laterally-close peer sets j5=0 in applied."""
    from arm_runtime import ArmRuntime, PeerStatePacket
    from baseline_mode import BaselineMode

    rt = ArmRuntime("arm1")
    # cam point that produces a non-zero j5 candidate
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    rt.load_scenario([step])
    baseline = BaselineMode()

    # Compute candidate so we can place peer j4 within 0.05 m of own j4
    own_cand = rt.compute_candidate_joints(step)
    own_j4 = own_cand["j4"]

    peer_state = PeerStatePacket(
        arm_id="arm2",
        step_id=1,
        status="ready",
        timestamp=0.0,
        current_joints={"j3": 0.0, "j4": own_j4, "j5": 0.0},
        candidate_joints={"j3": 0.0, "j4": own_j4, "j5": 0.3},  # same j4 → gap = 0
    )

    applied_joints, skipped, candidate_joints = rt.run_step(
        step_id=1,
        peer_state=peer_state,
        mode=BaselineMode.BASELINE_J5_BLOCK_SKIP,
        baseline_mode_obj=baseline,
        current_joints={"j3": 0.0, "j4": 0.0, "j5": 0.0},
    )

    assert applied_joints["j5"] == 0.0
    assert skipped is False


# ---------------------------------------------------------------------------
# phi compensation in compute_candidate_joints
# ---------------------------------------------------------------------------


def test_compute_candidate_joints_applies_phi_compensation():
    """compute_candidate_joints with enable_phi_compensation=True
    returns a different j3 than raw polar_decompose."""
    from arm_runtime import ArmRuntime
    from fk_chain import camera_to_arm, polar_decompose

    rt = ArmRuntime("arm1")
    step = ScenarioStep(
        step_id=1, arm_id="arm1",
        cam_x=0.494, cam_y=-0.001, cam_z=0.004,
    )
    # Raw result (no compensation)
    ax, ay, az = camera_to_arm(
        step.cam_x, step.cam_y, step.cam_z, j4_pos=0.0,
    )
    raw = polar_decompose(ax, ay, az)

    # Compensated result
    result = rt.compute_candidate_joints(
        step, j4_current=0.0, enable_phi_compensation=True,
    )

    # j3 should differ from the raw value (compensation applied)
    assert result["j3"] != raw["j3"], (
        "Compensated j3 should differ from raw polar_decompose j3"
    )
    # j4, j5 should be unchanged
    assert result["j4"] == raw["j4"]
    assert result["j5"] == raw["j5"]


def test_compute_candidate_joints_skips_compensation_when_disabled():
    """compute_candidate_joints with enable_phi_compensation=False
    returns raw polar_decompose result (j3 unchanged)."""
    from arm_runtime import ArmRuntime
    from fk_chain import camera_to_arm, polar_decompose

    rt = ArmRuntime("arm1")
    step = ScenarioStep(
        step_id=1, arm_id="arm1",
        cam_x=0.494, cam_y=-0.001, cam_z=0.004,
    )
    ax, ay, az = camera_to_arm(
        step.cam_x, step.cam_y, step.cam_z, j4_pos=0.0,
    )
    raw = polar_decompose(ax, ay, az)

    result = rt.compute_candidate_joints(
        step, j4_current=0.0, enable_phi_compensation=False,
    )

    assert result["j3"] == raw["j3"]
