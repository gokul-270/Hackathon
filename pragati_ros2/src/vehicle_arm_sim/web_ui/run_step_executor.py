#!/usr/bin/env python3
"""Motion-backed execution adapter between RunController and Gazebo.

Accepts an arm_id, applied_joints, and a publish_fn callable, then:
- For allowed (non-blocked, non-skipped) arm-steps: publishes joint commands via publish_fn
  and returns a 'completed' terminal outcome.
- For blocked arm-steps: records a 'blocked' outcome without publishing.
- For skipped arm-steps: records a 'skipped' outcome without publishing.

The publish_fn signature is: publish_fn(topic: str, value: float) -> None
Topic names follow the convention: /arm1/j3_cmd, /arm1/j4_cmd, /arm1/j5_cmd
(and /arm2/... for arm2).
"""

from __future__ import annotations

from typing import Callable, Optional


# Terminal status constants
COMPLETED = "completed"
BLOCKED = "blocked"
SKIPPED = "skipped"


class RunStepExecutor:
    """Executes a single arm-step by publishing Gazebo joint commands.

    The executor is a thin adapter: it knows arm topic naming conventions and
    terminal outcome semantics, but delegates all I/O to the injected publish_fn.
    This keeps RunController and testing_backend testable without a live Gazebo.
    """

    def __init__(self, publish_fn: Callable[[str, float], None]) -> None:
        """
        Args:
            publish_fn: Callable(topic, value) that issues the Gazebo command.
                        In production this is testing_backend._publish_joint_gz.
                        In tests it is a mock.
        """
        self._publish_fn = publish_fn

    def execute(
        self,
        arm_id: str,
        applied_joints: dict,
        blocked: bool = False,
        skipped: bool = False,
    ) -> dict:
        """Execute a single arm-step and return a terminal outcome dict.

        Args:
            arm_id: "arm1" or "arm2"
            applied_joints: {"j3": float, "j4": float, "j5": float}
            blocked: True when the active mode blocks this arm-step.
            skipped: True when overlap-zone wait times out.

        Returns:
            dict with keys:
              - terminal_status: "completed" | "blocked" | "skipped"
              - pick_completed:   bool
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

        # Publish the motion sequence via the injected publish_fn
        j3_topic = f"/{arm_id}/j3_cmd"
        j4_topic = f"/{arm_id}/j4_cmd"
        j5_topic = f"/{arm_id}/j5_cmd"

        self._publish_fn(j4_topic, applied_joints["j4"])
        self._publish_fn(j3_topic, applied_joints["j3"])
        self._publish_fn(j5_topic, applied_joints["j5"])

        return {
            "terminal_status": COMPLETED,
            "pick_completed": True,
            "executed_in_gazebo": True,
        }
