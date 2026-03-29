#!/usr/bin/env python3
"""Group 2 – Controller and backend execution wiring tests (TDD Red phase).

Tests that:
2.1  RunController.run() invokes the executor for each allowed arm-step.
2.2  POST /api/run/start triggers motion-backed execution through the controller.
2.3  Paired step: controller does not advance until both active arm outcomes are terminal.
2.4  Solo-tail step: controller advances after the single active arm reaches terminal outcome.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paired_scenario():
    """Both arms at step_id 0."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
        ]
    }


def _make_solo_tail_scenario():
    """arm1 has steps 0+1; arm2 only step 0 → solo tail for arm1 at step 1."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.12},
        ]
    }


def _make_multi_step_scenario():
    """Two paired steps (step_id 0 and 1)."""
    return {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
            {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.12},
            {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.22},
        ]
    }


# ---------------------------------------------------------------------------
# 2.1 RunController invokes executor during run()
# ---------------------------------------------------------------------------


def test_run_controller_invokes_executor_for_each_arm_step_during_run():
    """run() must invoke the executor once per active arm-step in the scenario."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    mock_executor = MagicMock()
    mock_executor.execute.return_value = {
        "terminal_status": "completed",
        "pick_completed": True,
        "executed_in_gazebo": True,
    }

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=mock_executor)
    rc.load_scenario(_make_paired_scenario())
    rc.run()

    # paired scenario has 2 arm-steps → executor called twice
    assert mock_executor.execute.call_count == 2


def test_run_controller_executor_receives_arm_id_and_applied_joints():
    """run() must pass arm_id and applied_joints to the executor for each step."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    captured_calls = []

    class CapturingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            captured_calls.append({"arm_id": arm_id, "applied_joints": applied_joints})
            return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=CapturingExecutor())
    rc.load_scenario(_make_paired_scenario())
    rc.run()

    arm_ids = {c["arm_id"] for c in captured_calls}
    assert "arm1" in arm_ids
    assert "arm2" in arm_ids
    for c in captured_calls:
        assert "j3" in c["applied_joints"]
        assert "j4" in c["applied_joints"]
        assert "j5" in c["applied_joints"]


def test_run_controller_passes_blocked_true_when_mode_blocks_step():
    """run() passes blocked=True to executor when mode logic results in a blocked step."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    blocked_calls = []

    class TrackingExecutor:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            blocked_calls.append(blocked)
            return {
                "terminal_status": "blocked" if blocked else "completed",
                "pick_completed": not blocked,
                "executed_in_gazebo": not blocked,
            }

    # Use a scenario with close j4 values so baseline mode blocks j5
    close_j4_scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
        ]
    }

    rc = RunController(mode=BaselineMode.BASELINE_J5_BLOCK_SKIP, executor=TrackingExecutor())
    rc.load_scenario(close_j4_scenario)
    rc.run()

    # At least one call must have blocked=True
    assert any(blocked_calls)


# ---------------------------------------------------------------------------
# 2.2 Backend /api/run/start triggers motion-backed execution
# ---------------------------------------------------------------------------


def test_run_start_triggers_executor_calls_through_controller():
    """POST /api/run/start must call the executor at least once for a non-empty scenario."""
    from fastapi.testclient import TestClient
    import testing_backend as tb

    publish_calls = []

    def mock_run(cmd, **kwargs):
        if len(cmd) >= 8 and cmd[0] == "gz" and cmd[1] == "topic":
            topic = cmd[3]
            val_str = cmd[7].replace("data: ", "")
            publish_calls.append((topic, float(val_str)))
        return type("CompletedProcess", (), {"returncode": 0})()

    # Patch subprocess.run + spawn/sleep so no real Gazebo I/O occurs
    with (
        patch("testing_backend.subprocess.run", side_effect=mock_run),
        patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
        patch("testing_backend._run_remove_cotton"),
        patch("testing_backend._run_sleep", side_effect=lambda s: None),
        patch("testing_backend.time.sleep", side_effect=lambda s: None),
    ):
        fresh_client = TestClient(tb.app)
        resp = fresh_client.post(
            "/api/run/start",
            json={
                "mode": 0,
                "scenario": {
                    "steps": [
                        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
                        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
                    ]
                },
            },
        )

    assert resp.status_code == 200
    # The executor must have published at least one joint command
    assert len(publish_calls) > 0


def test_run_start_does_not_publish_for_blocked_steps():
    """POST /api/run/start must NOT call publish for steps blocked by mode logic."""
    from fastapi.testclient import TestClient
    import testing_backend as tb

    publish_calls = []

    def mock_run(cmd, **kwargs):
        if len(cmd) >= 8 and cmd[0] == "gz" and cmd[1] == "topic":
            topic = cmd[3]
            val_str = cmd[7].replace("data: ", "")
            publish_calls.append((topic, float(val_str)))
        return type("CompletedProcess", (), {"returncode": 0})()

    # Close j4 scenario under baseline mode → j5 blocked → executor should not publish
    close_j4_blocked_scenario = {
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
        ]
    }

    with (
        patch("testing_backend.subprocess.run", side_effect=mock_run),
        patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
        patch("testing_backend._run_remove_cotton"),
        patch("testing_backend._run_sleep", side_effect=lambda s: None),
        patch("testing_backend.time.sleep", side_effect=lambda s: None),
    ):
        fresh_client = TestClient(tb.app)
        resp = fresh_client.post(
            "/api/run/start",
            json={"mode": 1, "scenario": close_j4_blocked_scenario},
        )

    assert resp.status_code == 200
    # Blocked steps should not result in publish calls
    # (at minimum, no j5_cmd publish since j5 is zeroed for blocked steps)
    j5_publishes = [v for topic, v in publish_calls if "j5" in topic and v > 0]
    assert len(j5_publishes) == 0


# ---------------------------------------------------------------------------
# 2.3 Paired step: both arm outcomes must be terminal before advancing
# ---------------------------------------------------------------------------


def test_run_controller_executes_both_arms_in_paired_step():
    """For a paired step_id, the controller executes BOTH arm1 and arm2 before advancing."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    execution_order = []

    class OrderTracker:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            execution_order.append(arm_id)
            return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=OrderTracker())
    rc.load_scenario(_make_paired_scenario())
    rc.run()

    # Both arm1 and arm2 must have been executed for step 0
    assert "arm1" in execution_order
    assert "arm2" in execution_order


def test_run_controller_step_reports_include_outcome_for_paired_step():
    """step_reports for a paired step must include outcome fields for both arms."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    mock_executor = MagicMock()
    mock_executor.execute.return_value = {
        "terminal_status": "completed",
        "pick_completed": True,
        "executed_in_gazebo": True,
    }

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=mock_executor)
    rc.load_scenario(_make_paired_scenario())
    summary = rc.run()

    step_reports = summary["step_reports"]
    step0_reports = [r for r in step_reports if r["step_id"] == 0]
    assert len(step0_reports) == 2
    for r in step0_reports:
        assert r["terminal_status"] == "completed"
        assert r["pick_completed"] is True


# ---------------------------------------------------------------------------
# 2.4 Solo-tail step: advances after single active arm reaches terminal outcome
# ---------------------------------------------------------------------------


def test_run_controller_executes_solo_tail_step_after_paired_step():
    """For a solo-tail step, the controller executes the single active arm."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    executed_arms_per_step = {}

    class StepTracker:
        def execute(self, arm_id, applied_joints, blocked=False, skipped=False, **kwargs):
            # We can't get step_id here; just track all calls
            executed_arms_per_step.setdefault(arm_id, 0)
            executed_arms_per_step[arm_id] += 1
            return {"terminal_status": "completed", "pick_completed": True, "executed_in_gazebo": True}

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=StepTracker())
    rc.load_scenario(_make_solo_tail_scenario())
    summary = rc.run()

    # arm1 has 2 steps (step 0 + step 1), arm2 has 1 step (step 0 only)
    assert executed_arms_per_step.get("arm1", 0) == 2
    assert executed_arms_per_step.get("arm2", 0) == 1


def test_run_controller_solo_tail_step_report_has_terminal_outcome():
    """The step report for a solo-tail step must include a terminal outcome."""
    from run_controller import RunController
    from baseline_mode import BaselineMode

    mock_executor = MagicMock()
    mock_executor.execute.return_value = {
        "terminal_status": "completed",
        "pick_completed": True,
        "executed_in_gazebo": True,
    }

    rc = RunController(mode=BaselineMode.UNRESTRICTED, executor=mock_executor)
    rc.load_scenario(_make_solo_tail_scenario())
    summary = rc.run()

    step_reports = summary["step_reports"]
    step1_reports = [r for r in step_reports if r["step_id"] == 1]
    assert len(step1_reports) == 1
    assert step1_reports[0]["arm_id"] == "arm1"
    assert step1_reports[0]["terminal_status"] == "completed"
