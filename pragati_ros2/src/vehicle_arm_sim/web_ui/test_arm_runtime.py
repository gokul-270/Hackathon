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
    """compute_candidate_joints result contains the j3 key."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "j3" in result


def test_compute_candidate_joints_returns_j4_key():
    """compute_candidate_joints result contains the j4 key."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "j4" in result


def test_compute_candidate_joints_returns_j5_key():
    """compute_candidate_joints result contains the j5 key."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "j5" in result


def test_compute_candidate_joints_result_has_reachable_key():
    """compute_candidate_joints result contains the reachable key."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    step = ScenarioStep(step_id=1, arm_id="arm1", cam_x=0.494, cam_y=-0.001, cam_z=0.004)
    result = rt.compute_candidate_joints(step)
    assert "reachable" in result


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
    """build_peer_state packet timestamp is a float."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm2")
    packet = rt.build_peer_state(
        step_id=2,
        status="computing",
        current_joints={"j3": -0.3, "j4": 0.1, "j5": 0.05},
        candidate_joints={"j3": -0.4, "j4": 0.12, "j5": 0.08},
    )
    assert isinstance(packet.timestamp, float)


# ---------------------------------------------------------------------------
# run_step tests
# ---------------------------------------------------------------------------


def test_run_step_method_exists_on_arm_runtime():
    """ArmRuntime exposes a run_step method."""
    from arm_runtime import ArmRuntime

    rt = ArmRuntime("arm1")
    assert callable(getattr(rt, "run_step", None))


def test_run_step_returns_three_tuple():
    """run_step returns a 3-tuple (applied_joints, skipped, candidate_joints)."""
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
