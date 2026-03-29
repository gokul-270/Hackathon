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
    """publish_fn is called with Gazebo topic names from ARM_CONFIGS and joint values."""
    from run_step_executor import RunStepExecutor

    calls_made = []

    def record_publish(topic, value):
        calls_made.append((topic, value))

    executor = RunStepExecutor(
        publish_fn=record_publish,
        spawn_fn=lambda *a: "",
        remove_fn=lambda n: None,
        sleep_fn=lambda s: None,
    )
    applied_joints = {"j3": 0.15, "j4": 0.25, "j5": 0.35}

    executor.execute(arm_id="arm1", applied_joints=applied_joints, blocked=False)

    # All topics must be arm1's Gazebo topics from ARM_CONFIGS
    topics = {t for t, _ in calls_made}
    assert "/joint3_cmd" in topics
    assert "/joint4_cmd" in topics
    assert "/joint5_cmd" in topics

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
    # Find first non-zero publish for each joint (use "joint3"/"joint4"/"joint5")
    j4_idx = next(i for i, t in enumerate(topics_in_order) if "joint4" in t and publish_calls[i][1] != 0.0)
    j3_idx = next(i for i, t in enumerate(topics_in_order) if "joint3" in t and publish_calls[i][1] != 0.0)
    j5_idx = next(i for i, t in enumerate(topics_in_order) if "joint5" in t and publish_calls[i][1] != 0.0)

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
    # Check j5 retract to 0.0 exists (use "joint5")
    j5_retracts = [v for t, v in topics_values if "joint5" in t and v == 0.0]
    assert len(j5_retracts) >= 1, "Expected j5 retract to 0.0"

    # Check j3 home to 0.0 exists
    j3_homes = [v for t, v in topics_values if "joint3" in t and v == 0.0]
    assert len(j3_homes) >= 1, "Expected j3 home to 0.0"

    # Check j4 home to 0.0 exists
    j4_homes = [v for t, v in topics_values if "joint4" in t and v == 0.0]
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


# ---------------------------------------------------------------------------
# Bug fix: executor must use real Gazebo topic names from ARM_CONFIGS
# ---------------------------------------------------------------------------


def test_executor_arm1_publishes_to_joint3_cmd_topic():
    """arm1 must publish to /joint3_cmd, not /arm1/j3_cmd."""
    from run_step_executor import RunStepExecutor

    publish_calls = []

    executor = RunStepExecutor(
        publish_fn=lambda t, v: publish_calls.append((t, v)),
        spawn_fn=lambda *a: "c0",
        remove_fn=lambda n: None,
        sleep_fn=lambda s: None,
    )

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        blocked=False,
    )

    j3_topics = [t for t, _ in publish_calls if "joint3" in t]
    assert len(j3_topics) > 0, f"No joint3 topics. All: {publish_calls}"
    for topic in j3_topics:
        assert topic == "/joint3_cmd", f"Expected /joint3_cmd, got {topic}"


def test_executor_arm1_publishes_to_joint4_cmd_topic():
    """arm1 must publish to /joint4_cmd, not /arm1/j4_cmd."""
    from run_step_executor import RunStepExecutor

    publish_calls = []

    executor = RunStepExecutor(
        publish_fn=lambda t, v: publish_calls.append((t, v)),
        spawn_fn=lambda *a: "c0",
        remove_fn=lambda n: None,
        sleep_fn=lambda s: None,
    )

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        blocked=False,
    )

    j4_topics = [t for t, _ in publish_calls if "joint4" in t]
    assert len(j4_topics) > 0, f"No joint4 topics. All: {publish_calls}"
    for topic in j4_topics:
        assert topic == "/joint4_cmd", f"Expected /joint4_cmd, got {topic}"


def test_executor_arm1_publishes_to_joint5_cmd_topic():
    """arm1 must publish to /joint5_cmd, not /arm1/j5_cmd."""
    from run_step_executor import RunStepExecutor

    publish_calls = []

    executor = RunStepExecutor(
        publish_fn=lambda t, v: publish_calls.append((t, v)),
        spawn_fn=lambda *a: "c0",
        remove_fn=lambda n: None,
        sleep_fn=lambda s: None,
    )

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        blocked=False,
    )

    j5_topics = [t for t, _ in publish_calls if "joint5" in t]
    assert len(j5_topics) > 0, f"No joint5 topics. All: {publish_calls}"
    for topic in j5_topics:
        assert topic == "/joint5_cmd", f"Expected /joint5_cmd, got {topic}"


def test_executor_arm2_publishes_to_joint3_copy_cmd_topic():
    """arm2 must publish to /joint3_copy_cmd, not /arm2/j3_cmd."""
    from run_step_executor import RunStepExecutor

    publish_calls = []

    executor = RunStepExecutor(
        publish_fn=lambda t, v: publish_calls.append((t, v)),
        spawn_fn=lambda *a: "c0",
        remove_fn=lambda n: None,
        sleep_fn=lambda s: None,
    )

    executor.execute(
        arm_id="arm2",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        blocked=False,
    )

    j3_topics = [t for t, _ in publish_calls if "joint3" in t]
    assert len(j3_topics) > 0, f"No joint3 topics. All: {publish_calls}"
    for topic in j3_topics:
        assert topic == "/joint3_copy_cmd", f"Expected /joint3_copy_cmd, got {topic}"


def test_executor_arm2_publishes_to_joint4_copy_cmd_topic():
    """arm2 must publish to /joint4_copy_cmd, not /arm2/j4_cmd."""
    from run_step_executor import RunStepExecutor

    publish_calls = []

    executor = RunStepExecutor(
        publish_fn=lambda t, v: publish_calls.append((t, v)),
        spawn_fn=lambda *a: "c0",
        remove_fn=lambda n: None,
        sleep_fn=lambda s: None,
    )

    executor.execute(
        arm_id="arm2",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        blocked=False,
    )

    j4_topics = [t for t, _ in publish_calls if "joint4" in t]
    assert len(j4_topics) > 0, f"No joint4 topics. All: {publish_calls}"
    for topic in j4_topics:
        assert topic == "/joint4_copy_cmd", f"Expected /joint4_copy_cmd, got {topic}"


def test_executor_arm2_publishes_to_joint5_copy_cmd_topic():
    """arm2 must publish to /joint5_copy_cmd, not /arm2/j5_cmd."""
    from run_step_executor import RunStepExecutor

    publish_calls = []

    executor = RunStepExecutor(
        publish_fn=lambda t, v: publish_calls.append((t, v)),
        spawn_fn=lambda *a: "c0",
        remove_fn=lambda n: None,
        sleep_fn=lambda s: None,
    )

    executor.execute(
        arm_id="arm2",
        applied_joints={"j3": 0.15, "j4": 0.25, "j5": 0.35},
        blocked=False,
    )

    j5_topics = [t for t, _ in publish_calls if "joint5" in t]
    assert len(j5_topics) > 0, f"No joint5 topics. All: {publish_calls}"
    for topic in j5_topics:
        assert topic == "/joint5_copy_cmd", f"Expected /joint5_copy_cmd, got {topic}"


# ---------------------------------------------------------------------------
# Group 2: cotton_model parameter
# ---------------------------------------------------------------------------


def test_executor_with_cotton_model_skips_spawn_fn():
    """When cotton_model is provided, spawn_fn must NOT be called."""
    spawn_calls = []
    executor = _make_executor(spawn_calls=spawn_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        cotton_model="pre_cotton_5",
        blocked=False,
    )

    assert spawn_calls == []


def test_executor_with_cotton_model_calls_remove_with_provided_name():
    """When cotton_model is provided, remove_fn must be called with that model name."""
    remove_calls = []
    executor = _make_executor(remove_calls=remove_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        cotton_model="pre_cotton_5",
        blocked=False,
    )

    assert remove_calls == ["pre_cotton_5"]


def test_executor_with_cotton_model_and_blocked_does_not_call_remove():
    """When cotton_model is provided and step is blocked, remove_fn must NOT be called."""
    remove_calls = []
    executor = _make_executor(remove_calls=remove_calls)

    executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.0, "j4": 0.2, "j5": 0.0},
        cotton_model="pre_cotton_5",
        blocked=True,
    )

    assert remove_calls == []


# ---------------------------------------------------------------------------
# Task 3 — E-STOP support (estop_check param)
# ---------------------------------------------------------------------------


def test_executor_estop_check_always_true_returns_estop_aborted():
    """RunStepExecutor with estop_check=lambda: True SHALL return estop_aborted immediately."""
    from run_step_executor import RunStepExecutor

    executor = RunStepExecutor(
        publish_fn=lambda t, v: None,
        sleep_fn=lambda s: None,
        estop_check=lambda: True,
    )
    outcome = executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
    )
    assert outcome["terminal_status"] == "estop_aborted"
    assert outcome["pick_completed"] is False
    assert outcome["executed_in_gazebo"] is False


@pytest.mark.parametrize("fire_after_sleep_n", [1, 2, 3, 4, 5, 6])
def test_executor_estop_fires_at_nth_sleep_returns_estop_aborted(fire_after_sleep_n):
    """E-STOP check after the Nth sleep must return estop_aborted for all 6 phase boundaries."""
    from run_step_executor import RunStepExecutor

    sleep_count = [0]

    def counting_sleep(s):
        sleep_count[0] += 1

    def estop_check():
        return sleep_count[0] >= fire_after_sleep_n

    executor = RunStepExecutor(
        publish_fn=lambda t, v: None,
        sleep_fn=counting_sleep,
        estop_check=estop_check,
    )
    outcome = executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
    )
    assert outcome["terminal_status"] == "estop_aborted", (
        f"Expected estop_aborted when E-STOP fires after sleep {fire_after_sleep_n}, "
        f"got {outcome['terminal_status']}"
    )
    assert outcome["pick_completed"] is False
    assert outcome["executed_in_gazebo"] is False


def test_executor_estop_publishes_zeros_to_arm2_topics_on_abort():
    """When E-STOP fires mid-animation on arm2, zeros must be published to all 3 arm2 topics."""
    from run_step_executor import RunStepExecutor

    published = []
    sleep_count = [0]

    def counting_sleep(s):
        sleep_count[0] += 1

    def estop_check():
        return sleep_count[0] >= 2  # fire after 2nd sleep (mid-animation)

    executor = RunStepExecutor(
        publish_fn=lambda t, v: published.append((t, v)),
        sleep_fn=counting_sleep,
        estop_check=estop_check,
    )
    executor.execute(
        arm_id="arm2",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
    )

    arm2_zero_publishes = [
        (t, v) for t, v in published
        if t in ("/joint3_copy_cmd", "/joint4_copy_cmd", "/joint5_copy_cmd") and v == 0.0
    ]
    published_zero_topics = {t for t, v in arm2_zero_publishes}
    assert "/joint3_copy_cmd" in published_zero_topics, (
        f"Expected zero publish to /joint3_copy_cmd on E-STOP abort; got {published}"
    )
    assert "/joint4_copy_cmd" in published_zero_topics, (
        f"Expected zero publish to /joint4_copy_cmd on E-STOP abort; got {published}"
    )
    assert "/joint5_copy_cmd" in published_zero_topics, (
        f"Expected zero publish to /joint5_copy_cmd on E-STOP abort; got {published}"
    )


def test_executor_without_estop_check_completes_normally():
    """RunStepExecutor without estop_check must complete normally (backward compat)."""
    from run_step_executor import RunStepExecutor

    executor = RunStepExecutor(
        publish_fn=lambda t, v: None,
        sleep_fn=lambda s: None,
        # no estop_check
    )
    outcome = executor.execute(
        arm_id="arm1",
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
    )
    assert outcome["terminal_status"] == "completed"
    assert outcome["pick_completed"] is True
