#!/usr/bin/env python3
"""Motion-backed execution adapter between RunController and Gazebo.

Accepts an arm_id, applied_joints, and callable dependencies, then:
- For allowed (non-blocked, non-skipped) arm-steps:
    1. Calls spawn_fn to spawn a cotton model at the cam position.
    2. Runs the timed pick animation: j4 → j3 → j5 → retract → home,
       using sleep_fn for delays (injectable for fast tests).
    3. Calls remove_fn to remove the cotton model after animation completes.
    4. Returns a 'completed' terminal outcome with pick_completed=True.
- For blocked arm-steps: records 'blocked' without spawning, publishing, or removing.
- For skipped arm-steps: records 'skipped' without spawning, publishing, or removing.

Callable signatures:
    publish_fn(topic: str, value: float) -> None
        Topic names: /arm1/j3_cmd, /arm1/j4_cmd, /arm1/j5_cmd (and /arm2/...)
    spawn_fn(arm_id: str, cam_x: float, cam_y: float, cam_z: float, j4_pos: float) -> str
        Returns the Gazebo model name that was spawned.
    remove_fn(model_name: str) -> None
    sleep_fn(seconds: float) -> None
        Defaults to time.sleep; inject a no-op for fast unit tests.
"""

from __future__ import annotations

import time
from typing import Callable, Optional


# Terminal status constants
COMPLETED = "completed"
BLOCKED = "blocked"
SKIPPED = "skipped"

# Pick animation timing (seconds) — matches _execute_pick_sequence in testing_backend
_T_J4 = 0.8
_T_J3 = 0.8
_T_J5_EXTEND = 1.4
_T_J5_RETRACT = 0.8
_T_J3_HOME = 0.8
_T_J4_HOME = 0.9


def _noop_spawn(arm_id: str, cam_x: float, cam_y: float, cam_z: float, j4_pos: float) -> str:
    """No-op spawn used when no spawn_fn is provided (backward-compat)."""
    return ""


def _noop_remove(model_name: str) -> None:
    """No-op remove used when no remove_fn is provided (backward-compat)."""


class RunStepExecutor:
    """Executes a single arm-step by spawning cotton and running a timed Gazebo animation.

    The executor is a thin adapter: it knows arm topic naming conventions and
    terminal outcome semantics, but delegates all I/O to the injected callables.
    This keeps RunController and testing_backend testable without a live Gazebo.
    """

    def __init__(
        self,
        publish_fn: Callable[[str, float], None],
        spawn_fn: Optional[Callable[[str, float, float, float, float], str]] = None,
        remove_fn: Optional[Callable[[str], None]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Args:
            publish_fn: Callable(topic, value) that issues the Gazebo joint command.
            spawn_fn:   Callable(arm_id, cam_x, cam_y, cam_z, j4_pos) -> model_name.
                        Spawns a cotton model at the target position before the animation.
                        Defaults to a no-op (backward-compatible with old callers).
            remove_fn:  Callable(model_name) that removes the cotton model after animation.
                        Defaults to a no-op.
            sleep_fn:   Callable(seconds) used between animation steps.
                        Defaults to time.sleep; inject a no-op for fast unit tests.
        """
        self._publish_fn = publish_fn
        self._spawn_fn = spawn_fn if spawn_fn is not None else _noop_spawn
        self._remove_fn = remove_fn if remove_fn is not None else _noop_remove
        self._sleep_fn = sleep_fn if sleep_fn is not None else time.sleep

    def execute(
        self,
        arm_id: str,
        applied_joints: dict,
        blocked: bool = False,
        skipped: bool = False,
        cam_x: float = 0.0,
        cam_y: float = 0.0,
        cam_z: float = 0.0,
        j4_pos: float = 0.0,
    ) -> dict:
        """Execute a single arm-step and return a terminal outcome dict.

        Args:
            arm_id:         "arm1" or "arm2"
            applied_joints: {"j3": float, "j4": float, "j5": float}
            blocked:        True when the active mode blocks this arm-step.
            skipped:        True when overlap-zone wait times out.
            cam_x, cam_y, cam_z: Camera-frame position used to spawn cotton.
            j4_pos:         Current j4 position used for cotton spawn placement.

        Returns:
            dict with keys:
              - terminal_status:    "completed" | "blocked" | "skipped"
              - pick_completed:     bool
              - executed_in_gazebo: bool
        """
        if blocked:
            return {
                "terminal_status": BLOCKED,
                "pick_completed": False,
                "executed_in_gazebo": False,
            }

        if skipped:
            return {
                "terminal_status": SKIPPED,
                "pick_completed": False,
                "executed_in_gazebo": False,
            }

        j3_topic = f"/{arm_id}/j3_cmd"
        j4_topic = f"/{arm_id}/j4_cmd"
        j5_topic = f"/{arm_id}/j5_cmd"

        # 1. Spawn cotton at the cam position
        model_name = self._spawn_fn(arm_id, cam_x, cam_y, cam_z, j4_pos)

        # 2. Run timed pick animation: j4 → j3 → j5 → retract → home
        self._publish_fn(j4_topic, applied_joints["j4"])
        self._sleep_fn(_T_J4)

        self._publish_fn(j3_topic, applied_joints["j3"])
        self._sleep_fn(_T_J3)

        self._publish_fn(j5_topic, applied_joints["j5"])
        self._sleep_fn(_T_J5_EXTEND)

        self._publish_fn(j5_topic, 0.0)
        self._sleep_fn(_T_J5_RETRACT)

        self._publish_fn(j3_topic, 0.0)
        self._sleep_fn(_T_J3_HOME)

        self._publish_fn(j4_topic, 0.0)
        self._sleep_fn(_T_J4_HOME)

        # 3. Remove cotton after animation completes
        self._remove_fn(model_name)

        return {
            "terminal_status": COMPLETED,
            "pick_completed": True,
            "executed_in_gazebo": True,
        }
