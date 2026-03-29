#!/usr/bin/env python3
"""Tests for RunStepExecutor - Gazebo motion execution seam.

RunStepExecutor accepts an arm_id, applied_joints dict, and callables:
- publish_fn: publishes joint commands
- spawn_fn: spawns a cotton model at the cam position
- remove_fn: removes a cotton model
- sleep_fn: injectable time.sleep (mocked in tests for speed)

For allowed arm-steps it:
  1. Spawns cotton at the cam position
  2. Runs the timed animation sequence (j4 → j3 → j5 → retract → home)
  3. Removes cotton after the animation completes
  4. Returns pick_completed=True only after all three steps succeed

For blocked/skipped arm-steps it does NOT spawn, publish, or remove.
"""

import pytest
from unittest.mock import MagicMock, call


# ---------------------------------------------------------------------------
# Task 1.1 — Allowed arm-step publishes Gazebo motion
# ---------------------------------------------------------------------------


def test_executor_publishes_joint_commands_for_allowed_arm_step():
    """RunStepExecutor.execute() calls publish_fn for each joint when the step is allowed."""
    from run_step_executor import RunStepExecutor

    publish_fn = MagicMock()
    executor = RunStepExecutor(publish_fn=publish_fn)
    applied_joints = {"j3": 0.1, "j4": 0.2, "j5": 0.3}

    executor.execute(arm_id="arm1", applied_joints=applied_joints, blocked=False)

    # publish_fn must be called at least once (for each joint)
    assert publish_fn.called


def test_executor_returns_completed_outcome_for_allowed_arm_step():
    """RunStepExecutor.execute() returns 'completed' terminal_status for allowed step."""
    from run_step_executor import RunStepExecutor

    executor = RunStepExecutor(publish_fn=MagicMock())
    applied_joints = {"j3": 0.1, "j4": 0.2, "j5": 0.3}

    outcome = executor.execute(arm_id="arm1", applied_joints=applied_joints, blocked=False)

    assert outcome["terminal_status"] == "completed"
    assert outcome["pick_completed"] is True
    assert outcome["executed_in_gazebo"] is True


# ---------------------------------------------------------------------------
# Task 1.2 — Blocked arm-step does NOT publish Gazebo motion
# ---------------------------------------------------------------------------


def test_executor_does_not_publish_for_blocked_arm_step():
    """RunStepExecutor.execute() does NOT call publish_fn when the step is blocked."""
    from run_step_executor import RunStepExecutor

    publish_fn = MagicMock()
    executor = RunStepExecutor(publish_fn=publish_fn)
    applied_joints = {"j3": 0.0, "j4": 0.2, "j5": 0.0}

    executor.execute(arm_id="arm1", applied_joints=applied_joints, blocked=True)

    publish_fn.assert_not_called()


def test_executor_returns_blocked_outcome_for_blocked_arm_step():
    """RunStepExecutor.execute() returns 'blocked' terminal_status for blocked step."""
    from run_step_executor import RunStepExecutor

    executor = RunStepExecutor(publish_fn=MagicMock())
    applied_joints = {"j3": 0.0, "j4": 0.2, "j5": 0.0}

    outcome = executor.execute(arm_id="arm1", applied_joints=applied_joints, blocked=True)

    assert outcome["terminal_status"] == "blocked"
    assert outcome["pick_completed"] is False
    assert outcome["executed_in_gazebo"] is False


def test_executor_returns_skipped_outcome_for_skipped_arm_step():
    """RunStepExecutor.execute() returns 'skipped' terminal_status for skipped step."""
    from run_step_executor import RunStepExecutor

    publish_fn = MagicMock()
    executor = RunStepExecutor(publish_fn=publish_fn)
    applied_joints = {"j3": 0.0, "j4": 0.2, "j5": 0.0}

    outcome = executor.execute(arm_id="arm1", applied_joints=applied_joints, skipped=True)

    publish_fn.assert_not_called()
    assert outcome["terminal_status"] == "skipped"
    assert outcome["pick_completed"] is False
    assert outcome["executed_in_gazebo"] is False


def test_executor_publish_fn_called_with_arm_topics_for_allowed_step():
    """publish_fn is called with arm-specific topic names (containing arm_id) and joint values."""
    from run_step_executor import RunStepExecutor

    calls_made = []

    def record_publish(topic, value):
        calls_made.append((topic, value))

    executor = RunStepExecutor(publish_fn=record_publish)
    applied_joints = {"j3": 0.15, "j4": 0.25, "j5": 0.35}

    executor.execute(arm_id="arm1", applied_joints=applied_joints, blocked=False)

    # All topics must reference arm1
    for topic, _ in calls_made:
        assert "arm1" in topic

    # All three joint values must appear
    published_values = [v for _, v in calls_made]
    assert 0.15 in published_values
    assert 0.25 in published_values
    assert 0.35 in published_values


# ---------------------------------------------------------------------------
# New behavior: spawn + timed animation + confirmed completion
# ---------------------------------------------------------------------------


def _make_executor(publish_calls=None, spawn_calls=None, remove_calls=None, sleep_calls=None,
                   spawn_return="cotton_0"):
    """Build a RunStepExecutor with all callables mocked for fast unit tests."""
    from run_step_executor import RunStepExecutor

    if publish_calls is None:
        publish_calls = []
    if spawn_calls is None:
        spawn_calls = []
    if remove_calls is None:
        remove_calls = []
    if sleep_calls is None:
        sleep_calls = []

    def mock_publish(topic, value):
        publish_calls.append((topic, value))

    def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
        spawn_calls.append((arm_id, cam_x, cam_y, cam_z, j4_pos))
        return spawn_return

    def mock_remove(model_name):
        remove_calls.append(model_name)

    def mock_sleep(seconds):
        sleep_calls.append(seconds)

    return RunStepExecutor(
        publish_fn=mock_publish,
        spawn_fn=mock_spawn,
        remove_fn=mock_remove,
        sleep_fn=mock_sleep,
    )


def test_executor_calls_spawn_fn_before_animation_for_allowed_step():
    """For an allowed step, spawn_fn must be called before any joint publishes."""
    spawn_calls = []
    publish_calls = []
    call_order = []

    def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
        call_order.append("spawn")
        spawn_calls.append((arm_id, cam_x, cam_y, cam_z, j4_pos))
        return "cotton_0"

    def mock_publish(topic, value):
        call_order.append("publish")
        publish_calls.append((topic, value))

    from run_step_executor import RunStepExecutor

    executor = RunStepExecutor(
        publish_fn=mock_publish,
        spawn_fn=mock_spawn,
        remove_fn=lambda name: None,
        sleep_fn=lambda s: None,
    )
    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.2,
        blocked=False,
    )

    assert len(spawn_calls) == 1
    assert spawn_calls[0][0] == "arm1"
    assert call_order.index("spawn") < call_order.index("publish")


def test_executor_calls_remove_fn_after_animation_for_allowed_step():
    """For an allowed step, remove_fn must be called with the cotton name returned by spawn_fn."""
    spawn_return = "cotton_42"
    removed = []
    publish_order = []
    remove_order = []

    def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
        return spawn_return

    def mock_publish(topic, value):
        publish_order.append(topic)

    def mock_remove(model_name):
        removed.append(model_name)
        remove_order.append("remove")

    from run_step_executor import RunStepExecutor

    executor = RunStepExecutor(
        publish_fn=mock_publish,
        spawn_fn=mock_spawn,
        remove_fn=mock_remove,
        sleep_fn=lambda s: None,
    )
    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.2,
        blocked=False,
    )

    assert removed == [spawn_return]
    assert len(publish_order) > 0  # publish happened before remove
    assert remove_order == ["remove"]


def test_executor_uses_sleep_fn_between_joints_for_timed_animation():
    """For an allowed step, sleep_fn must be called between joint commands."""
    sleep_calls = []
    executor = _make_executor(sleep_calls=sleep_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.2,
        blocked=False,
    )

    assert len(sleep_calls) >= 4  # at least 4 sleeps for a full pick sequence


def test_executor_does_not_spawn_for_blocked_step():
    """For a blocked step, spawn_fn must NOT be called."""
    spawn_calls = []
    executor = _make_executor(spawn_calls=spawn_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.0, "j4": 0.2, "j5": 0.0},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.2,
        blocked=True,
    )

    assert spawn_calls == []


def test_executor_does_not_remove_for_blocked_step():
    """For a blocked step, remove_fn must NOT be called."""
    remove_calls = []
    executor = _make_executor(remove_calls=remove_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.0, "j4": 0.2, "j5": 0.0},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.2,
        blocked=True,
    )

    assert remove_calls == []


def test_executor_does_not_spawn_for_skipped_step():
    """For a skipped step, spawn_fn must NOT be called."""
    spawn_calls = []
    executor = _make_executor(spawn_calls=spawn_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.0, "j4": 0.2, "j5": 0.0},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.2,
        skipped=True,
    )

    assert spawn_calls == []


def test_executor_pick_completed_true_only_after_full_animation_and_removal():
    """pick_completed must be True only after animation and cotton removal both succeed."""
    executor = _make_executor()

    outcome = executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.2,
        blocked=False,
    )

    assert outcome["pick_completed"] is True
    assert outcome["executed_in_gazebo"] is True
    assert outcome["terminal_status"] == "completed"


def test_executor_publishes_timed_sequence_j4_then_j3_then_j5():
    """The animation must publish j4 first, then j3, then j5 (matching pick animation order)."""
    publish_calls = []
    executor = _make_executor(publish_calls=publish_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.25,
        blocked=False,
    )

    topics_in_order = [t for t, _ in publish_calls]
    # Find first non-zero publish for each joint
    j4_idx = next(i for i, t in enumerate(topics_in_order) if "j4" in t and publish_calls[i][1] != 0.0)
    j3_idx = next(i for i, t in enumerate(topics_in_order) if "j3" in t and publish_calls[i][1] != 0.0)
    j5_idx = next(i for i, t in enumerate(topics_in_order) if "j5" in t and publish_calls[i][1] != 0.0)

    assert j4_idx < j3_idx < j5_idx, (
        f"Expected j4({j4_idx}) < j3({j3_idx}) < j5({j5_idx}) in publish order"
    )


def test_executor_publishes_retract_and_home_after_j5():
    """After j5 extend, the animation must retract j5 and return j3 and j4 to home (0.0)."""
    publish_calls = []
    executor = _make_executor(publish_calls=publish_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        cam_x=0.65, cam_y=0.0, cam_z=0.10, j4_pos=0.25,
        blocked=False,
    )

    topics_values = [(t, v) for t, v in publish_calls]
    # Check j5 retract to 0.0 exists
    j5_retracts = [v for t, v in topics_values if "j5" in t and v == 0.0]
    assert len(j5_retracts) >= 1, "Expected j5 retract to 0.0"

    # Check j3 home to 0.0 exists
    j3_homes = [v for t, v in topics_values if "j3" in t and v == 0.0]
    assert len(j3_homes) >= 1, "Expected j3 home to 0.0"

    # Check j4 home to 0.0 exists
    j4_homes = [v for t, v in topics_values if "j4" in t and v == 0.0]
    assert len(j4_homes) >= 1, "Expected j4 home to 0.0"


def test_executor_old_interface_still_works_with_defaults():
    """Backward compat: executor constructed with only publish_fn should use no-op spawn/remove/sleep."""
    from run_step_executor import RunStepExecutor

    publish_calls = []
    executor = RunStepExecutor(publish_fn=lambda t, v: publish_calls.append((t, v)))

    # This should not raise even when cam_x/cam_y/cam_z/j4_pos are not passed
    # (old callers may not pass them, e.g. tests that don't care about spawn)
    outcome = executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        blocked=False,
    )

    assert outcome["terminal_status"] == "completed"
