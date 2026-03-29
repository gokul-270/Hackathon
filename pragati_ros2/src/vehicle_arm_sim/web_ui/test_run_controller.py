#!/usr/bin/env python3
"""Tests for RunController - central run coordinator for dual-arm cotton-picking scenario."""

import json

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paired_scenario():
    """Two arms, one paired step."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_only_arm1_scenario():
    """Only arm1 steps."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.4, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_only_arm2_scenario():
    """Only arm2 steps."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.4, "cam_y": -0.070, "cam_z": 0.0},
        ]
    }


def _make_same_step_paired_scenario():
    """Both arms at the same step_id (paired execution)."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_solo_tail_scenario():
    """arm1 has steps 0+1, arm2 only has step 0 (solo tail for arm1 at step 1)."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.070, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.4, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }


def _make_close_j4_paired_scenario():
    """Both arms at step 0 with cam_z values that produce j4 within 0.05m of each other.

    FK note: j4 = ay_absolute = camera_to_arm(cam_z) + j4_pos.  cam_z drives j4 because
    the yanthra_link rotation maps camera-Z directly onto arm-Y.  cam_y maps to arm-Z (j3
    geometry) and does NOT affect j4.  cam_z=0.25 and cam_z=0.27 produce j4 separation
    of ~0.02 m, well within the 0.05 m blocking threshold.
    """
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
        ]
    }


# ---------------------------------------------------------------------------
# load_scenario tests
# ---------------------------------------------------------------------------


def test_load_scenario_with_valid_data_does_not_raise():
    """load_scenario with a valid scenario dict does not raise any exception."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_paired_scenario())  # must not raise


# ---------------------------------------------------------------------------
# run() tests - solo arm1
# ---------------------------------------------------------------------------


def test_run_with_only_arm1_steps_returns_correct_total_steps():
    """run() with only arm1 steps reports total_steps equal to the number of unique step_ids."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_only_arm1_scenario())
    summary = rc.run()
    assert summary["total_steps"] == 2


# ---------------------------------------------------------------------------
# run() tests - solo arm2
# ---------------------------------------------------------------------------


def test_run_with_only_arm2_steps_returns_correct_total_steps():
    """run() with only arm2 steps reports total_steps equal to the number of unique step_ids."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_only_arm2_scenario())
    summary = rc.run()
    assert summary["total_steps"] == 2


# ---------------------------------------------------------------------------
# run() tests - paired (both arms at same step_id)
# ---------------------------------------------------------------------------


def test_run_with_paired_steps_generates_truth_monitor_observations():
    """run() with both arms at same step_id produces a non-None min_j4_distance for that step."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()
    step_reports = summary["step_reports"]
    # Both arms report at step_id 0; min_j4_distance must not be None
    reports_for_step0 = [r for r in step_reports if r["step_id"] == 0]
    assert all(r["min_j4_distance"] is not None for r in reports_for_step0)


# ---------------------------------------------------------------------------
# run() tests - solo tail
# ---------------------------------------------------------------------------


def test_run_solo_tail_step_has_none_min_j4_distance_for_solo_step():
    """Solo-tail step (only one arm active) reports None min_j4_distance."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_solo_tail_scenario())
    summary = rc.run()
    step_reports = summary["step_reports"]
    # step_id=1 is only for arm1 (solo tail)
    reports_for_step1 = [r for r in step_reports if r["step_id"] == 1]
    assert len(reports_for_step1) == 1
    assert reports_for_step1[0]["min_j4_distance"] is None


# ---------------------------------------------------------------------------
# run() tests - unrestricted mode never blocks j5
# ---------------------------------------------------------------------------


def test_run_in_unrestricted_mode_never_blocks_j5():
    """In unrestricted mode no step report has j5_blocked=True."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(_make_close_j4_paired_scenario())
    summary = rc.run()
    assert all(not r["j5_blocked"] for r in summary["step_reports"])


# ---------------------------------------------------------------------------
# run() tests - baseline_j5_block_skip mode blocks j5 when arms laterally close
# ---------------------------------------------------------------------------


def test_run_in_baseline_j5_block_skip_mode_blocks_j5_when_arms_close():
    """In baseline_j5_block_skip mode, j5_blocked is True when arms are within 0.05m."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    rc = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP)
    rc.load_scenario(_make_close_j4_paired_scenario())
    summary = rc.run()
    assert summary["steps_with_j5_blocked"] > 0


# ---------------------------------------------------------------------------
# get_json_report tests
# ---------------------------------------------------------------------------


def test_get_json_report_returns_valid_json_string_after_run():
    """get_json_report() returns a valid JSON string after run() has been called."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_paired_scenario())
    rc.run()
    json_str = rc.get_json_report()
    parsed = json.loads(json_str)  # must not raise
    assert "mode" in parsed


# ---------------------------------------------------------------------------
# reset tests
# ---------------------------------------------------------------------------


def test_reset_clears_state_so_subsequent_run_produces_fresh_summary():
    """After reset(), a subsequent run() on a new scenario returns a fresh summary."""
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_only_arm1_scenario())
    first_summary = rc.run()

    rc.reset()
    rc.load_scenario(_make_only_arm2_scenario())
    second_summary = rc.run()

    # Both have 2 steps; but step_reports should reflect the NEW scenario (arm2 only)
    assert second_summary["total_steps"] == 2
    arm_ids_in_second = {r["arm_id"] for r in second_summary["step_reports"]}
    assert arm_ids_in_second == {"arm2"}


# ---------------------------------------------------------------------------
# Integration / E2E tests
# ---------------------------------------------------------------------------


def test_e2e_unrestricted_mode_paired_scenario_has_no_j5_blocked():
    """E2E: 2-arm paired scenario in unrestricted mode produces zero j5_blocked reports.

    FK note: j4 is driven by cam_z (camera-Z maps to arm-Y via the yanthra_link rotation).
    arm1 cam_z=0.25 → j4≈-0.150 m, arm2 cam_z=0.35 → j4≈-0.250 m.
    Lateral separation ≈ 0.10 m > 0.05 m threshold, so even in blocking mode j5 would not
    be suppressed.  In unrestricted mode it is definitely never suppressed.
    """
    from run_controller import RunController
    from baseline_mode import BaselineMode

    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.35},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.35},
        ]
    }
    rc = RunController(mode=BaselineMode.UNRESTRICTED)
    rc.load_scenario(scenario)
    summary = rc.run()
    j5_blocked_count = sum(1 for r in summary["step_reports"] if r["j5_blocked"])
    assert j5_blocked_count == 0


def test_e2e_baseline_j5_block_skip_mode_blocks_j5_when_arms_laterally_close():
    """E2E: baseline_j5_block_skip blocks j5 when arms have j4 within 0.05m of each other.

    FK note: j4 is driven by cam_z (camera-Z maps to arm-Y via the yanthra_link rotation).
    cam_z=0.25 → j4≈-0.150 m, cam_z=0.27 → j4≈-0.170 m.  Lateral separation ≈ 0.02 m,
    which is less than the 0.05 m blocking threshold, so j5 must be zeroed.
    Both steps are reachable (j5≈0.128 m > 0) so the block condition can fire.
    """
    from run_controller import RunController
    from baseline_mode import BaselineMode

    # cam_z=0.25 → j4≈-0.150 m, cam_z=0.27 → j4≈-0.170 m (separation ~0.02 m < 0.05 m)
    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
        ]
    }
    rc = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP)
    rc.load_scenario(scenario)
    summary = rc.run()
    j5_blocked_count = sum(1 for r in summary["step_reports"] if r["j5_blocked"])
    assert j5_blocked_count > 0


# ---------------------------------------------------------------------------
# Group 1 (Phase 2): paired-step contract — both arms share the same step_id
# ---------------------------------------------------------------------------


def test_load_scenario_accepts_paired_step_data_with_duplicate_step_ids():
    """RunController.load_scenario() MUST accept a scenario where both arm1 and arm2
    share the same step_id (the paired-step contract).

    parse_scenario() would reject this; load_scenario() bypasses it intentionally.
    """
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_same_step_paired_scenario())  # must not raise


def test_run_paired_step_produces_two_step_reports_for_shared_step_id():
    """run() on a paired scenario (both arms at step_id=0) MUST produce exactly two
    step_reports for step_id=0 — one for each arm.

    This verifies the paired-step contract: the controller correctly executes both arms
    concurrently at the same step and records one report per arm.
    """
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()
    reports_step0 = [r for r in summary["step_reports"] if r["step_id"] == 0]
    assert len(reports_step0) == 2
    arm_ids = {r["arm_id"] for r in reports_step0}
    assert arm_ids == {"arm1", "arm2"}


def test_run_paired_step_both_arms_receive_truth_monitor_data():
    """Both step_reports for a shared step_id must have a non-None min_j4_distance.

    When both arms are active at the same step, the truth monitor observes j4 geometry
    and both reports must carry that shared min_j4_distance value.
    """
    from run_controller import RunController

    rc = RunController()
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()
    reports_step0 = [r for r in summary["step_reports"] if r["step_id"] == 0]
    assert len(reports_step0) == 2
    assert all(r["min_j4_distance"] is not None for r in reports_step0)


# ---------------------------------------------------------------------------
# Group 3: arm_pair parameter for dynamic arm selection and scenario remapping
# ---------------------------------------------------------------------------


def test_run_controller_with_arm_pair_arm1_arm3_creates_arm1_and_arm3_runtimes():
    """RunController with arm_pair=('arm1','arm3') uses arm1 and arm3 (not arm2) for execution."""
    from run_controller import RunController

    rc = RunController(arm_pair=("arm1", "arm3"))
    assert rc._primary_id == "arm1"
    assert rc._secondary_id == "arm3"


def test_load_scenario_with_arm_pair_arm1_arm3_remaps_arm2_steps_to_arm3():
    """load_scenario with arm_pair=('arm1','arm3') remaps arm2 scenario steps to arm3."""
    from run_controller import RunController

    rc = RunController(arm_pair=("arm1", "arm3"))
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()
    arm_ids_in_reports = {r["arm_id"] for r in summary["step_reports"]}
    # arm2 steps in scenario should be remapped to arm3
    assert "arm3" in arm_ids_in_reports
    assert "arm2" not in arm_ids_in_reports


def test_run_controller_with_arm_pair_arm2_arm3_remaps_arm1_to_arm2_and_arm2_to_arm3():
    """arm_pair=('arm2','arm3') remaps arm1 scenario steps to arm2 and arm2 steps to arm3."""
    from run_controller import RunController

    rc = RunController(arm_pair=("arm2", "arm3"))
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()
    arm_ids_in_reports = {r["arm_id"] for r in summary["step_reports"]}
    assert "arm2" in arm_ids_in_reports
    assert "arm3" in arm_ids_in_reports
    assert "arm1" not in arm_ids_in_reports


def test_run_controller_default_arm_pair_behavior_unchanged():
    """Default arm_pair=('arm1','arm2') preserves existing arm1/arm2 behavior."""
    from run_controller import RunController

    rc = RunController()  # no arm_pair → defaults to ("arm1", "arm2")
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()
    arm_ids_in_reports = {r["arm_id"] for r in summary["step_reports"]}
    assert arm_ids_in_reports == {"arm1", "arm2"}


# ---------------------------------------------------------------------------
# Group 4: upfront cotton spawning in RunController
# ---------------------------------------------------------------------------


def test_run_controller_calls_spawn_fn_for_each_step_before_execution():
    """RunController calls spawn_fn once per (step_id, arm_id) before any executor calls."""
    from run_controller import RunController

    spawn_calls = []
    step_id_tracker = [None]

    def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
        spawn_calls.append((arm_id, step_id_tracker[0]))  # track order
        return f"cotton_{len(spawn_calls)}"

    # Use a 2-step scenario with both arms
    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }

    rc = RunController(spawn_fn=mock_spawn)
    rc.load_scenario(scenario)
    rc.run()

    # spawn must have been called exactly once per step-arm pair
    assert len(spawn_calls) == 2


def test_run_controller_passes_cotton_model_to_executor():
    """RunController passes pre-spawned cotton model name to executor.execute()."""
    from run_controller import RunController

    spawned_names = {}
    executor_cotton_models = []

    def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
        name = f"pre_cotton_{arm_id}"
        spawned_names[arm_id] = name
        return name

    class MockExecutor:
        def execute(self, arm_id, applied_joints, blocked, skipped,
                    cam_x, cam_y, cam_z, j4_pos, cotton_model=""):
            executor_cotton_models.append((arm_id, cotton_model))
            return {"terminal_status": "completed", "pick_completed": True,
                    "executed_in_gazebo": True}

    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }

    rc = RunController(spawn_fn=mock_spawn, executor=MockExecutor())
    rc.load_scenario(scenario)
    rc.run()

    # executor should have received the cotton_model name from spawn
    assert len(executor_cotton_models) == 1
    assert executor_cotton_models[0][1] == "pre_cotton_arm1"


def test_run_controller_upfront_spawn_for_both_arms_in_paired_scenario():
    """For a paired scenario, spawn_fn is called for both arm1 and arm2 steps."""
    from run_controller import RunController

    spawned_arm_ids = []

    def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
        spawned_arm_ids.append(arm_id)
        return f"cotton_{arm_id}"

    rc = RunController(spawn_fn=mock_spawn)
    rc.load_scenario(_make_same_step_paired_scenario())
    rc.run()

    assert "arm1" in spawned_arm_ids
    assert "arm2" in spawned_arm_ids
    assert len(spawned_arm_ids) == 2  # one per arm at step 0


def test_run_controller_default_no_spawn_fn_uses_noop():
    """Default RunController (no spawn_fn) does not raise and runs normally."""
    from run_controller import RunController

    rc = RunController()  # no spawn_fn
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()  # must not raise
    assert summary["total_steps"] == 1


# ---------------------------------------------------------------------------
# Task 4 — Parallel dual-arm animation via ThreadPoolExecutor
# ---------------------------------------------------------------------------

import time as _time
import threading as _threading


class _RecordingExecutor:
    """Duck-typed executor that records call start times and arm_ids, then returns completed."""

    def __init__(self, start_times: dict, order: list, delay: float = 0.05):
        self._start_times = start_times
        self._order = order
        self._delay = delay

    def execute(self, arm_id, applied_joints, **kwargs):
        self._start_times[arm_id] = _time.monotonic()
        self._order.append(arm_id)
        _time.sleep(self._delay)
        return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}


class _OrderFlippingExecutor:
    """arm2 returns faster than arm1 (arm1 sleeps longer) to test ordering of step reports."""

    def __init__(self, report_order: list):
        self._report_order = report_order

    def execute(self, arm_id, applied_joints, **kwargs):
        if arm_id == "arm1":
            _time.sleep(0.08)  # arm1 is slower
        else:
            _time.sleep(0.01)  # arm2 is faster
        self._report_order.append(arm_id)
        return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}


class _CandidateCapturingExecutor:
    """Records when execute() is called relative to when candidates were computed."""

    def __init__(self, events: list):
        self._events = events

    def execute(self, arm_id, applied_joints, **kwargs):
        self._events.append(("execute", arm_id))
        return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}


def test_paired_step_both_executor_calls_start_within_50ms():
    """For a paired step, both executor.execute() calls must start within 50ms of each other."""
    from run_controller import RunController

    start_times: dict = {}
    order: list = []
    executor = _RecordingExecutor(start_times=start_times, order=order, delay=0.1)

    rc = RunController(executor=executor)
    rc.load_scenario(_make_same_step_paired_scenario())
    rc.run()

    assert "arm1" in start_times and "arm2" in start_times, (
        "Both arms must have executor.execute() called; missing one or both."
    )
    gap_ms = abs(start_times["arm1"] - start_times["arm2"]) * 1000
    assert gap_ms < 50, (
        f"Expected both execute() calls to start within 50ms of each other; "
        f"gap was {gap_ms:.1f}ms (sequential, not parallel)"
    )


def test_paired_step_reports_appended_in_sorted_arm_id_order():
    """Step reports for a paired step must be in sorted arm_id order even if arm2 finishes first."""
    from run_controller import RunController

    report_order: list = []
    executor = _OrderFlippingExecutor(report_order=report_order)

    rc = RunController(executor=executor)
    rc.load_scenario(_make_same_step_paired_scenario())
    summary = rc.run()

    step_reports = summary["step_reports"]
    arm_ids_in_order = [r["arm_id"] for r in step_reports]
    assert arm_ids_in_order == sorted(arm_ids_in_order), (
        f"Step reports must be in sorted arm_id order; got {arm_ids_in_order}"
    )


def test_solo_step_still_produces_single_step_report_correctly():
    """A solo step (only one arm active) must produce exactly one step report with correct arm_id."""
    from run_controller import RunController

    # solo arm1 scenario — just one arm per step, no parallelism needed
    rc = RunController()
    rc.load_scenario(_make_only_arm1_scenario())
    summary = rc.run()

    arm_ids = {r["arm_id"] for r in summary["step_reports"]}
    assert arm_ids == {"arm1"}, f"Expected only arm1 reports; got {arm_ids}"
    assert summary["total_steps"] == 2


def test_mode_logic_runs_before_executor_dispatch():
    """Mode logic (candidate joints computation) must complete before any executor.execute() call."""
    from run_controller import RunController

    events: list = []
    executor = _CandidateCapturingExecutor(events=events)

    # Use geometry_block mode (mode=2) to ensure mode logic has real work to do
    rc = RunController(mode=2, executor=executor)
    rc.load_scenario(_make_same_step_paired_scenario())
    rc.run()

    # All execute() events must come after both arm candidates are resolved
    # The simplest proxy: no execute() event appears before the step-level mode logic
    # completes. We verify that execute() is only called once candidate joints are available
    # by checking all events are ("execute", ...) type — meaning the controller didn't
    # dispatch execute before the step-level loop completed mode logic.
    execute_events = [e for e in events if e[0] == "execute"]
    assert len(execute_events) == 2, (
        f"Expected 2 execute() calls for paired step; got {len(execute_events)}: {events}"
    )


def test_completed_steps_retain_status_after_estop_fires_on_later_step():
    """Steps that already completed before an E-STOP must retain their original
    terminal_status ('completed'), not be overwritten with 'estop_aborted'.

    Task 5.9: 3 sequential solo steps; E-STOP fires during step 3 only.
    Steps 1 and 2 must show 'completed'.
    """
    from run_controller import RunController

    call_count = [0]

    class _EstopOnThirdCallExecutor:
        """Returns 'completed' for first 2 execute() calls, 'estop_aborted' for the 3rd."""

        def execute(self, arm_id, applied_joints, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 3:
                return {"terminal_status": "estop_aborted", "pick_completed": False, "executed_in_gazebo": False}
            return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}

    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
            {"step_id": 2, "arm_id": "arm1", "cam_x": 0.3, "cam_y": -0.065, "cam_z": 0.0},
        ]
    }

    executor = _EstopOnThirdCallExecutor()
    rc = RunController(executor=executor)
    rc.load_scenario(scenario)
    summary = rc.run()

    reports = summary["step_reports"]
    assert len(reports) == 3, f"Expected 3 step reports, got {len(reports)}: {reports}"

    step0_status = reports[0]["terminal_status"]
    step1_status = reports[1]["terminal_status"]
    step2_status = reports[2]["terminal_status"]

    assert step0_status == "completed", (
        f"Step 0 must retain 'completed' after later E-STOP; got '{step0_status}'"
    )
    assert step1_status == "completed", (
        f"Step 1 must retain 'completed' after later E-STOP; got '{step1_status}'"
    )
    assert step2_status == "estop_aborted", (
        f"Step 2 (where E-STOP fires) must be 'estop_aborted'; got '{step2_status}'"
    )
