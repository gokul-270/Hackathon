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
        Topic names are looked up from ARM_CONFIGS in fk_chain.py
        (e.g. /joint3_cmd for arm1, /joint3_copy_cmd for arm2).
    spawn_fn(arm_id: str, cam_x: float, cam_y: float, cam_z: float, j4_pos: float) -> str
        Returns the Gazebo model name that was spawned.
    remove_fn(model_name: str) -> None
    sleep_fn(seconds: float) -> None
        Defaults to time.sleep; inject a no-op for fast unit tests.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from fk_chain import ARM_CONFIGS


# Terminal status constants
COMPLETED = "completed"
BLOCKED = "blocked"
SKIPPED = "skipped"
ESTOP_ABORTED = "estop_aborted"

# Pick animation timing (seconds) — matches _execute_pick_sequence in testing_backend
_T_J4 = 0.4
_T_J3 = 0.4
_T_J5_EXTEND = 0.7
_T_J5_RETRACT = 0.4
_T_J3_HOME = 0.4
_T_J4_HOME = 0.45


def _noop_spawn(arm_id: str, cam_x: float, cam_y: float, cam_z: float, j4_pos: float, step_id: int = -1) -> str:
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
        estop_check: Optional[Callable[[], bool]] = None,
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
            estop_check: Optional callable() -> bool. If provided, checked after each
                        sleep_fn call. When it returns True, zeros are published to all
                        3 arm topics and execute() returns estop_aborted immediately.
        """
        self._publish_fn = publish_fn
        self._spawn_fn = spawn_fn if spawn_fn is not None else _noop_spawn
        self._remove_fn = remove_fn if remove_fn is not None else _noop_remove
        self._sleep_fn = sleep_fn if sleep_fn is not None else time.sleep
        self._estop_check = estop_check

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
        cotton_model: str = "",
    ) -> dict:
        """Execute a single arm-step and return a terminal outcome dict.

        Args:
            arm_id:         "arm1" or "arm2"
            applied_joints: {"j3": float, "j4": float, "j5": float}
            blocked:        True when the active mode blocks this arm-step.
            skipped:        True when overlap-zone wait times out.
            cam_x, cam_y, cam_z: Camera-frame position used to spawn cotton.
            j4_pos:         Current j4 position used for cotton spawn placement.
            cotton_model:   Name of a pre-spawned cotton model. When non-empty,
                            spawn_fn is skipped and this name is used directly.

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

        arm_cfg = ARM_CONFIGS[arm_id]
        j3_topic = arm_cfg["j3_topic"]
        j4_topic = arm_cfg["j4_topic"]
        j5_topic = arm_cfg["j5_topic"]

        def _estop_abort_result():
            """Publish zeros to all 3 arm topics and return estop_aborted outcome."""
            self._publish_fn(j3_topic, 0.0)
            self._publish_fn(j4_topic, 0.0)
            self._publish_fn(j5_topic, 0.0)
            return {
                "terminal_status": ESTOP_ABORTED,
                "pick_completed": False,
                "executed_in_gazebo": False,
            }

        def _sleep_and_check(duration: float):
            """Sleep and return estop abort dict if E-STOP fired, else None."""
            self._sleep_fn(duration)
            if self._estop_check is not None and self._estop_check():
                return _estop_abort_result()
            return None

        # 1. Spawn cotton at the cam position (or use pre-spawned model)
        if cotton_model:
            model_name = cotton_model
        else:
            model_name = self._spawn_fn(arm_id, cam_x, cam_y, cam_z, j4_pos)

        # 2. Run timed pick animation: j4 → j3 → j5 → retract → home
        self._publish_fn(j4_topic, applied_joints["j4"])
        result = _sleep_and_check(_T_J4)
        if result is not None:
            return result

        self._publish_fn(j3_topic, applied_joints["j3"])
        result = _sleep_and_check(_T_J3)
        if result is not None:
            return result

        self._publish_fn(j5_topic, applied_joints["j5"])
        result = _sleep_and_check(_T_J5_EXTEND)
        if result is not None:
            return result

        self._publish_fn(j5_topic, 0.0)
        result = _sleep_and_check(_T_J5_RETRACT)
        if result is not None:
            return result

        self._publish_fn(j3_topic, 0.0)
        result = _sleep_and_check(_T_J3_HOME)
        if result is not None:
            return result

        self._publish_fn(j4_topic, 0.0)
        result = _sleep_and_check(_T_J4_HOME)
        if result is not None:
            return result

        # 3. Remove cotton after animation completes
        self._remove_fn(model_name)

        return {
            "terminal_status": COMPLETED,
            "pick_completed": True,
            "executed_in_gazebo": True,
        }
