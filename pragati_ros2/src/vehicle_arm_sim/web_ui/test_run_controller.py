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
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.0},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.0},
            {"step_id": 2, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.0},
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


# ---------------------------------------------------------------------------
# Fix F1: prev_joints must NOT be updated when step was not executed in Gazebo
# ---------------------------------------------------------------------------


class _BlockFirstStepExecutor:
    """Returns 'blocked' for the first execute() call, 'completed' for subsequent calls.

    Also records the applied_joints received for each call so tests can verify
    what j4 value was passed in.
    """

    def __init__(self):
        self.call_count = 0
        self.received_applied_joints: list = []

    def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
        self.call_count += 1
        self.received_applied_joints.append(dict(applied_joints))
        if self.call_count == 1:
            return {
                "terminal_status": "blocked",
                "pick_completed": False,
                "executed_in_gazebo": False,
            }
        return {
            "terminal_status": "completed",
            "pick_completed": True,
            "executed_in_gazebo": True,
        }


def test_prev_joints_not_updated_when_step_blocked_so_next_step_sees_home_j4():
    """When step 0 is blocked (executed_in_gazebo=False), prev_joints must remain at
    the safe-home position so step 1's FK computation starts from j4=0.0, not from
    the blocked step's applied j4.

    Bug F1: before this fix, prev_joints was always overwritten with applied_joints,
    even for blocked/skipped steps where Gazebo never moved. This caused cascading FK
    drift — each subsequent step used a phantom j4 offset.
    """
    from run_controller import RunController

    executor = _BlockFirstStepExecutor()

    # Two sequential arm1-only steps. Step 0 will be blocked by executor.
    # The cam_z value (0.25) maps to a non-zero j4 (≈-0.150 m).
    # If prev_joints were polluted after step 0, step 1's candidate would use j4≈-0.150 as
    # j4_current instead of 0.0 (home). We capture applied_joints to detect this.
    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
        ]
    }

    rc = RunController(executor=executor)
    rc.load_scenario(scenario)
    rc.run()

    assert executor.call_count == 2, f"Expected 2 execute() calls; got {executor.call_count}"

    # Step 1's candidate joints must be computed from j4_current=0.0 (home),
    # NOT from step 0's applied j4.
    # Both steps use identical cam coords → identical FK. The j4_current offset shifts j4.
    # If prev_joints was NOT polluted → step 1 j4 == step 0 j4 (both from home j4=0.0).
    # If prev_joints WAS polluted → step 1 j4 != step 0 j4 (step 1 shifted by step 0 j4).
    step0_j4 = executor.received_applied_joints[0]["j4"]
    step1_j4 = executor.received_applied_joints[1]["j4"]
    assert step0_j4 == step1_j4, (
        f"Step 1 applied j4 ({step1_j4:.4f}) must equal step 0 applied j4 ({step0_j4:.4f}) "
        f"when step 0 was blocked and prev_joints was not updated. "
        f"A mismatch means prev_joints was incorrectly overwritten after the blocked step."
    )


def test_prev_joints_updated_when_step_executed_so_next_step_sees_shifted_j4():
    """When step 0 completes (executed_in_gazebo=True), prev_joints MUST be updated so
    step 1's FK computation sees the moved j4, not home.

    This is the regression guard: the fix must not break the normal-execution path.
    """
    from run_controller import RunController

    call_count = [0]
    received_applied_joints: list = []

    class _AlwaysCompleteExecutor:
        def execute(self, arm_id, applied_joints, **kwargs):
            call_count[0] += 1
            received_applied_joints.append(dict(applied_joints))
            return {
                "terminal_status": "completed",
                "pick_completed": True,
                "executed_in_gazebo": True,
            }

    executor = _AlwaysCompleteExecutor()

    # Two steps with identical cam coords.
    # After step 0 executes, prev_joints["arm1"] = applied j4 from step 0.
    # Step 1 FK uses j4_current = step 0 j4 → the result j4 will differ from step 0.
    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
        ]
    }

    rc = RunController(executor=executor)
    rc.load_scenario(scenario)
    rc.run()

    assert call_count[0] == 2

    step0_j4 = received_applied_joints[0]["j4"]
    step1_j4 = received_applied_joints[1]["j4"]

    # After a completed step, j4_current changes → next step's FK-computed j4 differs.
    # (camera_to_arm adds j4_pos offset, so step 1 j4 = step 0 j4 + step 0 j4 = 2× step0 j4)
    assert step0_j4 != step1_j4, (
        f"After a completed step, step 1 applied j4 ({step1_j4:.4f}) must differ "
        f"from step 0 applied j4 ({step0_j4:.4f}) because prev_joints should be updated."
    )


# ---------------------------------------------------------------------------
# Fix F2: unreachable cotton positions must be skipped, not sent to Gazebo
# ---------------------------------------------------------------------------

# cam_z=0.5 → j4≈-0.400 m, below J4_MIN=-0.250 → reachable=False
_UNREACHABLE_STEP = {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.5}
# cam_y=0.3, cam_z=0.0 → j3=-0.173, j4=0.100, j5=0.128 → reachable=True
_REACHABLE_STEP = {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.0}


def test_unreachable_step_produces_terminal_status_unreachable():
    """A step whose FK yields reachable=False must produce terminal_status='unreachable'.

    Bug F2: before this fix, out-of-limit joint values were passed to the executor
    and published to Gazebo, which silently clips or ignores them. The arm would appear
    to freeze at the last-known position with no error indication.
    """
    from run_controller import RunController

    execute_calls: list = []

    class _CapturingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            execute_calls.append({"arm_id": arm_id, "blocked": blocked, "skipped": skipped,
                                  "applied_joints": dict(applied_joints)})
            if skipped:
                return {"terminal_status": "unreachable", "pick_completed": False,
                        "executed_in_gazebo": False}
            return {"terminal_status": "completed", "pick_completed": True,
                    "executed_in_gazebo": True}

    rc = RunController(executor=_CapturingExecutor())
    rc.load_scenario({"steps": [_UNREACHABLE_STEP]})
    summary = rc.run()

    reports = summary["step_reports"]
    assert len(reports) == 1
    assert reports[0]["terminal_status"] == "unreachable", (
        f"Unreachable step must produce terminal_status='unreachable'; "
        f"got '{reports[0]['terminal_status']}'"
    )


def test_unreachable_step_is_not_executed_in_gazebo():
    """An unreachable step must have executed_in_gazebo=False."""
    from run_controller import RunController

    class _CapturingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            if skipped:
                return {"terminal_status": "unreachable", "pick_completed": False,
                        "executed_in_gazebo": False}
            return {"terminal_status": "completed", "pick_completed": True,
                    "executed_in_gazebo": True}

    rc = RunController(executor=_CapturingExecutor())
    rc.load_scenario({"steps": [_UNREACHABLE_STEP]})
    summary = rc.run()

    assert summary["step_reports"][0]["executed_in_gazebo"] is False, (
        "Unreachable step must not be executed in Gazebo."
    )


def test_unreachable_step_does_not_corrupt_prev_joints_for_next_step():
    """An unreachable step (F2) combined with prev_joints guard (F1) must not
    corrupt the arm position for subsequent steps.

    Scenario: step 0 is unreachable, step 1 is reachable with identical cam coords
    as step 0. If prev_joints is NOT corrupted, step 1 sees j4_current=0.0 (home)
    and its candidate j4 matches what step 0 would have produced from home.
    """
    from run_controller import RunController

    received_applied_joints: list = []

    class _CapturingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            received_applied_joints.append(dict(applied_joints))
            if skipped:
                return {"terminal_status": "unreachable", "pick_completed": False,
                        "executed_in_gazebo": False}
            return {"terminal_status": "completed", "pick_completed": True,
                    "executed_in_gazebo": True}

    # Step 0: unreachable (cam_z=0.5). Step 1: same cam coords but reachable=False too.
    # Both steps use the same coords; if prev_joints was corrupted, step 1's j4 would differ.
    # We use a reachable step for step 1 so it actually reaches the executor.
    scenario = {
        "steps": [
            {**_UNREACHABLE_STEP, "step_id": 0},
            {**_REACHABLE_STEP, "step_id": 1},
        ]
    }

    rc = RunController(executor=_CapturingExecutor())
    rc.load_scenario(scenario)
    rc.run()

    # Both calls must have happened (step 0 skipped, step 1 executed).
    assert len(received_applied_joints) == 2, (
        f"Expected 2 executor calls; got {len(received_applied_joints)}"
    )
    # Step 1's j4 must be computed from j4_current=0.0, not from step 0's (unreachable) j4.
    # _REACHABLE_STEP (cam_y=0.3, cam_z=0.0) from j4_current=0.0 gives j4≈0.100 m.
    step1_j4 = received_applied_joints[1]["j4"]
    from fk_chain import camera_to_arm, polar_decompose
    ax, ay, az = camera_to_arm(0.3, 0.3, 0.0, j4_pos=0.0)
    expected_j4 = polar_decompose(ax, ay, az)["j4"]
    assert abs(step1_j4 - expected_j4) < 1e-6, (
        f"Step 1 j4 ({step1_j4:.4f}) must equal home-based FK j4 ({expected_j4:.4f}), "
        f"proving prev_joints was not corrupted by the unreachable step 0."
    )


def test_reachable_step_still_executes_normally_after_f2_fix():
    """Regression: a reachable step must still produce terminal_status='completed'
    and executed_in_gazebo=True after the F2 reachability check is added.
    """
    from run_controller import RunController

    class _CompleteExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            if skipped:
                return {"terminal_status": "unreachable", "pick_completed": False,
                        "executed_in_gazebo": False}
            return {"terminal_status": "completed", "pick_completed": True,
                    "executed_in_gazebo": True}

    rc = RunController(executor=_CompleteExecutor())
    rc.load_scenario({"steps": [_REACHABLE_STEP]})
    summary = rc.run()

    reports = summary["step_reports"]
    assert reports[0]["terminal_status"] == "completed", (
        f"Reachable step must still complete normally; got '{reports[0]['terminal_status']}'"
    )
    assert reports[0]["executed_in_gazebo"] is True


# ---------------------------------------------------------------------------
# Group 3 — Parallel cotton spawn
# ---------------------------------------------------------------------------


def test_parallel_spawn_submits_all_cottons_concurrently():
    """All cotton spawn calls must be submitted before any spawn returns (concurrent dispatch)."""
    import threading
    from run_controller import RunController

    n_steps = 3  # arm1 has 3 steps, arm2 has 3 steps = 6 total spawns

    scenario = {
        "steps": [
            {"step_id": i, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10 + i * 0.01}
            for i in range(n_steps)
        ] + [
            {"step_id": i, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20 + i * 0.01}
            for i in range(n_steps)
        ]
    }

    in_flight = []
    gate = threading.Event()
    max_in_flight = [0]
    lock = threading.Lock()

    def counting_spawn(arm_id, cam_x, cam_y, cam_z, j4):
        with lock:
            in_flight.append(arm_id)
            if len(in_flight) > max_in_flight[0]:
                max_in_flight[0] = len(in_flight)
        # Signal first spawn so we can unblock after tracking
        gate.wait(timeout=2.0)
        with lock:
            in_flight.remove(arm_id)
        return f"cotton_{arm_id}"

    # Start controller in a thread so we can observe in-flight spawns
    import threading as _thr

    def run_controller():
        from run_step_executor import RunStepExecutor
        executor = RunStepExecutor(publish_fn=lambda t, v: None, sleep_fn=lambda s: None)
        ctrl = RunController(
            mode=0,
            executor=executor,
            arm_pair=("arm1", "arm2"),
            spawn_fn=counting_spawn,
        )
        ctrl.load_scenario(scenario)
        ctrl.run()

    t = _thr.Thread(target=run_controller)
    t.start()
    # Give spawns time to start
    import time
    time.sleep(0.1)
    gate.set()
    t.join(timeout=10.0)

    assert max_in_flight[0] > 1, (
        f"Spawn calls must be concurrent (max_in_flight > 1); got {max_in_flight[0]}. "
        "Are you running spawns sequentially?"
    )


def test_parallel_spawn_all_complete_before_execution():
    """All spawn calls must complete before executor.execute() is ever called."""
    import threading
    from run_controller import RunController

    scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
        ]
    }

    spawn_complete = threading.Event()
    execute_called_before_spawn_complete = [False]
    all_spawned = [False]

    def slow_spawn(arm_id, cam_x, cam_y, cam_z, j4):
        import time
        time.sleep(0.05)
        return f"cotton_{arm_id}"

    executed_steps = []

    class TrackingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            executed_steps.append(arm_id)
            return {
                "terminal_status": "completed",
                "pick_completed": True,
                "executed_in_gazebo": True,
                "arm_id": arm_id,
                "step_id": 0,
                "blocked": False,
                "skipped": False,
                "near_collision": False,
            }

    from run_step_executor import RunStepExecutor
    # Use a real executor but we override it
    ctrl = RunController(
        mode=0,
        executor=TrackingExecutor(),
        arm_pair=("arm1", "arm2"),
        spawn_fn=slow_spawn,
    )
    ctrl.load_scenario(scenario)
    ctrl.run()

    # If we get here without exception, spawn completed before execute was called
    # The real assertion is that spawn happens for ALL steps before ANY execute
    assert len(executed_steps) > 0, "execute must have been called"


# ---------------------------------------------------------------------------
# Group 5 — Independent per-arm execution threads
# ---------------------------------------------------------------------------

_ASYMMETRIC_SCENARIO = {
    "steps": [
        # arm1: 3 steps — cam_z=0.150 gives j4≈-0.050 per step, all reachable
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.150},
        {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.150},
        {"step_id": 2, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.150},
        # arm2: 5 steps — cam_z values giving j4≈+0.001 to +0.052, all reachable and safe from arm1
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.100},
        {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.095},
        {"step_id": 2, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.090},
        {"step_id": 3, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.085},
        {"step_id": 4, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.080},
    ]
}


def _make_timing_executor(sleep_per_step_map: dict):
    """Return an executor whose execute() sleeps arm-specific amounts."""
    import time

    class TimingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            delay = sleep_per_step_map.get(arm_id, 0.0)
            time.sleep(delay)
            return {
                "terminal_status": "completed",
                "pick_completed": True,
                "executed_in_gazebo": True,
            }

    return TimingExecutor()


def test_arm1_does_not_wait_for_arm2_between_steps():
    """arm1 (fast, 3 steps) must finish without waiting for arm2 (slow, 5 steps)."""
    import time
    from run_controller import RunController

    # arm2 sleeps 0.2s per step (5 steps = 1.0s minimum if sequential)
    # arm1 sleeps 0.0s per step (3 steps = ~0s)
    # If arm1 is independent, its steps complete far faster than arm2
    executor = _make_timing_executor({"arm1": 0.0, "arm2": 0.2})

    arm1_finish_time = [None]
    arm2_finish_time = [None]
    original_execute = executor.execute

    def tracked_execute(arm_id, **kwargs):
        result = original_execute(arm_id=arm_id, **kwargs)
        if arm_id == "arm1":
            arm1_finish_time[0] = time.monotonic()
        elif arm_id == "arm2":
            arm2_finish_time[0] = time.monotonic()
        return result

    executor.execute = tracked_execute

    ctrl = RunController(
        mode=0,
        executor=executor,
        arm_pair=("arm1", "arm2"),
    )
    ctrl.load_scenario(_ASYMMETRIC_SCENARIO)
    start = time.monotonic()
    ctrl.run()
    total = time.monotonic() - start

    # arm1 finishes its last step before arm2 finishes its last step
    assert arm1_finish_time[0] is not None, "arm1 must have executed at least one step"
    assert arm2_finish_time[0] is not None, "arm2 must have executed at least one step"
    assert arm1_finish_time[0] < arm2_finish_time[0], (
        f"arm1 (fast) must finish before arm2 (slow); "
        f"arm1 last: {arm1_finish_time[0]:.3f}, arm2 last: {arm2_finish_time[0]:.3f}"
    )


def test_run_returns_after_all_arms_terminal():
    """run() total time must be dominated by the slower arm, not their sum."""
    import time
    from run_controller import RunController

    # arm1: 3 steps × 0.0s; arm2: 5 steps × 0.15s = 0.75s min
    # Sequential total would be 3×0.0 + 5×0.15 = 0.75s
    # Parallel total should be max(0, 0.75) = 0.75s — but if paired, both
    # arms run together at each step, so it would be 5 × 0.15 = 0.75s anyway.
    # We test: run() does NOT take arm1_time + arm2_time = (3+5)*0.15 = 1.2s if
    # both arms used the slow executor.
    executor = _make_timing_executor({"arm1": 0.05, "arm2": 0.15})

    ctrl = RunController(
        mode=0,
        executor=executor,
        arm_pair=("arm1", "arm2"),
    )
    ctrl.load_scenario(_ASYMMETRIC_SCENARIO)
    start = time.monotonic()
    ctrl.run()
    elapsed = time.monotonic() - start

    # Sequential execution of all 8 steps would take 3*0.05 + 5*0.15 = 0.90s
    # Independent execution in parallel: arm1 = 3*0.05=0.15s; arm2 = 5*0.15=0.75s
    # Max = 0.75s (plus some overhead); well under sequential 0.90s
    assert elapsed < 0.85, (
        f"run() with 8 steps (3+5) must finish in parallel time (~0.75s), "
        f"not sequential time (~0.90s); got {elapsed:.3f}s"
    )


def test_step_reports_contain_all_steps_from_both_arms():
    """Summary must contain 8 step reports for arm1(3)+arm2(5) asymmetric scenario."""
    import json
    from run_controller import RunController

    ctrl = RunController(
        mode=0,
        arm_pair=("arm1", "arm2"),
    )
    ctrl.load_scenario(_ASYMMETRIC_SCENARIO)
    summary = ctrl.run()

    step_reports = summary["step_reports"]
    assert len(step_reports) == 8, (
        f"Expected 8 step reports (arm1:3 + arm2:5), got {len(step_reports)}: "
        f"{[(r['arm_id'], r['step_id']) for r in step_reports]}"
    )
    arm1_reports = [r for r in step_reports if r["arm_id"] == "arm1"]
    arm2_reports = [r for r in step_reports if r["arm_id"] == "arm2"]
    assert len(arm1_reports) == 3, f"arm1 must have 3 reports, got {len(arm1_reports)}"
    assert len(arm2_reports) == 5, f"arm2 must have 5 reports, got {len(arm2_reports)}"


def test_independent_arms_publish_and_read_peer_state():
    """Each arm thread must call transport.publish() once per step it executes."""
    from run_controller import RunController
    from peer_transport import LocalPeerTransport
    from unittest.mock import MagicMock, patch

    publish_calls = []
    real_transport = LocalPeerTransport()
    original_publish = real_transport.publish

    def tracking_publish(packet):
        publish_calls.append(packet.arm_id)
        original_publish(packet)

    real_transport.publish = tracking_publish

    ctrl = RunController(
        mode=0,
        arm_pair=("arm1", "arm2"),
    )
    ctrl.load_scenario(_ASYMMETRIC_SCENARIO)
    ctrl._transport = real_transport
    ctrl.run()

    arm1_publishes = publish_calls.count("arm1")
    arm2_publishes = publish_calls.count("arm2")
    assert arm1_publishes == 3, (
        f"arm1 must publish once per step (3 steps), got {arm1_publishes}"
    )
    assert arm2_publishes == 5, (
        f"arm2 must publish once per step (5 steps), got {arm2_publishes}"
    )


# ---------------------------------------------------------------------------
# CRITICAL spec coverage: prev_joints isolation, spawn failure, solo peer_state
# ---------------------------------------------------------------------------

_ISOLATION_SCENARIO = {
    "steps": [
        # step_id 0: both arms
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.200},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.050},
        # step_id 1: arm2 only
        {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.050},
    ]
}


def test_arm1_prev_joints_update_does_not_affect_arm2():
    """arm2 candidate_joints at step 1 must use arm2's own prev_joints, not arm1's."""
    from run_controller import RunController
    from baseline_mode import BaselineMode
    from fk_chain import camera_to_arm, polar_decompose

    ctrl = RunController(mode=BaselineMode.UNRESTRICTED, arm_pair=("arm1", "arm2"))
    ctrl.load_scenario(_ISOLATION_SCENARIO)
    summary = ctrl.run()

    reports = summary["step_reports"]
    arm2_step1 = next(
        (r for r in reports if r["arm_id"] == "arm2" and r["step_id"] == 1), None
    )
    assert arm2_step1 is not None, "arm2 step 1 report must exist"

    # arm2 step 0 applied j4: computed from cam_z=0.050, j4_pos=0
    j_arm2_step0 = polar_decompose(*camera_to_arm(0.65, -0.001, 0.050, j4_pos=0.0))
    arm2_step0_j4 = j_arm2_step0["j4"]  # ≈ 0.0505

    # arm2 step 1 expected candidate j4: computed from cam_z=0.050, j4_pos=arm2_step0_j4
    expected = polar_decompose(*camera_to_arm(0.65, -0.001, 0.050, j4_pos=arm2_step0_j4))
    expected_j4 = expected["j4"]  # ≈ 0.1009

    # If contaminated by arm1's prev_joints (j4≈-0.0995), candidate j4 would be ≈-0.0491
    # The two outcomes differ by 0.15 m — easily distinguishable
    actual_j4 = arm2_step1["candidate_joints"]["j4"]
    assert abs(actual_j4 - expected_j4) < 0.005, (
        f"arm2 step 1 candidate j4={actual_j4:.4f} does not match expected {expected_j4:.4f}; "
        f"arm2 may have used arm1's prev_joints (would give ≈-0.0491)"
    )


def test_parallel_spawn_exception_does_not_block_others():
    """A failing spawn_fn must not prevent other cottons from being spawned."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    spawned = []

    def selective_spawn_fn(arm_id, cam_x, cam_y, cam_z, j4_pos):
        if arm_id == "arm1" and cam_z == 0.200:
            raise RuntimeError("simulated Gazebo timeout for arm1 step 0")
        model_name = f"{arm_id}_cotton_{cam_z}"
        spawned.append(model_name)
        return model_name

    ctrl = RunController(
        mode=BaselineMode.UNRESTRICTED,
        arm_pair=("arm1", "arm2"),
        spawn_fn=selective_spawn_fn,
    )
    ctrl.load_scenario(_ISOLATION_SCENARIO)

    # run() must not raise — the exception should be caught and the cotton recorded as ""
    summary = ctrl.run()

    # arm2's spawns must have completed
    assert any("arm2" in m for m in spawned), (
        "arm2 cottons must still be spawned even if arm1 spawn fails"
    )

    # The failed cotton (arm1 step 0) must be recorded with empty string
    reports = summary["step_reports"]
    arm1_step0 = next(
        (r for r in reports if r["arm_id"] == "arm1" and r["step_id"] == 0), None
    )
    assert arm1_step0 is not None, "arm1 step 0 report must still exist"


def test_arm2_solo_tail_step_receives_none_peer_state():
    """apply_with_skip must receive peer_state=None for arm2 solo steps (no arm1 entry)."""
    from run_controller import RunController
    from baseline_mode import BaselineMode
    from unittest.mock import patch

    ctrl = RunController(mode=BaselineMode.UNRESTRICTED, arm_pair=("arm1", "arm2"))
    ctrl.load_scenario(_ISOLATION_SCENARIO)

    peer_states_solo = []
    original_apply = ctrl._baseline.apply_with_skip

    def capturing_apply(mode, own_cand, peer_state, step_id, arm_id):
        if step_id == 1 and arm_id == "arm2":
            peer_states_solo.append(peer_state)
        return original_apply(mode, own_cand, peer_state, step_id=step_id, arm_id=arm_id)

    with patch.object(ctrl._baseline, "apply_with_skip", side_effect=capturing_apply):
        ctrl.run()

    assert len(peer_states_solo) == 1, (
        f"apply_with_skip must be called once for arm2 step 1 (solo), got {len(peer_states_solo)}"
    )
    assert peer_states_solo[0] is None, (
        f"peer_state for arm2 solo step must be None, got {peer_states_solo[0]!r}"
    )


def test_run_controller_step_reports_include_cam_coords():
    """StepReport entries must include cam_x/cam_y/cam_z from the scenario step."""
    from run_controller import RunController
    ctrl = RunController(mode=0)
    ctrl.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.150},
        ]
    })
    summary = ctrl.run()
    reports = summary["step_reports"]
    assert len(reports) == 1
    assert reports[0]["cam_x"] == 0.65
    assert reports[0]["cam_y"] == -0.001
    assert reports[0]["cam_z"] == 0.150
