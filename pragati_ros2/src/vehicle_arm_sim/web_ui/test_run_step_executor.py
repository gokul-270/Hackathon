#!/usr/bin/env python3
"""Tests for RunStepExecutor - Gazebo motion execution seam (TDD Red phase).

RunStepExecutor accepts an arm_id, applied_joints dict, and a publish_fn callable.
- For allowed (non-blocked) arm-steps it calls publish_fn with the joint values.
- For blocked arm-steps it does NOT call publish_fn.
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
