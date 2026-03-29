#!/usr/bin/env python3
"""Shared scenario JSON contract for the dual-arm cotton-picking robot.

Provides ScenarioStep dataclass and parse_scenario() validator used by both arm nodes
to load a scenario file at run start.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


_VALID_ARM_IDS = {"arm1", "arm2", "arm3"}
_CAM_FIELDS = ("cam_x", "cam_y", "cam_z")


@dataclass
class ScenarioStep:
    """One step in a picking scenario."""

    step_id: int
    arm_id: str
    cam_x: float
    cam_y: float
    cam_z: float


def parse_scenario(data: dict) -> List[ScenarioStep]:
    """Parse and validate a scenario dict, returning a list of ScenarioStep.

    Args:
        data: Raw dict (e.g. loaded from JSON) with a 'steps' key.

    Returns:
        List of validated ScenarioStep objects, in input order.

    Raises:
        ValueError: If any validation rule is violated.
    """
    if "steps" not in data:
        raise ValueError("Scenario dict is missing required 'steps' key.")

    raw_steps = data["steps"]

    if len(raw_steps) == 0:
        raise ValueError("Scenario must contain at least one step; got empty list.")

    seen_ids: set = set()
    steps: List[ScenarioStep] = []

    for idx, raw in enumerate(raw_steps):
        # --- step_id ---
        if "step_id" not in raw:
            raise ValueError(f"Step {idx}: missing required field 'step_id'.")
        step_id = raw["step_id"]
        if not isinstance(step_id, int) or step_id < 0:
            raise ValueError(
                f"Step {idx}: 'step_id' must be a non-negative integer, got {step_id!r}."
            )
        if step_id in seen_ids:
            raise ValueError(f"Step {idx}: duplicate step_id={step_id}.")
        seen_ids.add(step_id)

        # --- arm_id ---
        if "arm_id" not in raw:
            raise ValueError(f"Step {idx}: missing required field 'arm_id'.")
        arm_id = raw["arm_id"]
        if arm_id not in _VALID_ARM_IDS:
            raise ValueError(
                f"Step {idx}: 'arm_id' must be one of {sorted(_VALID_ARM_IDS)}, got {arm_id!r}."
            )

        # --- cam_x / cam_y / cam_z ---
        cam_values: dict = {}
        for field in _CAM_FIELDS:
            if field not in raw:
                raise ValueError(f"Step {idx}: missing required field '{field}'.")
            val = raw[field]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(
                    f"Step {idx}: '{field}' must be a number, got {val!r}."
                )
            cam_values[field] = float(val)

        steps.append(
            ScenarioStep(
                step_id=step_id,
                arm_id=arm_id,
                cam_x=cam_values["cam_x"],
                cam_y=cam_values["cam_y"],
                cam_z=cam_values["cam_z"],
            )
        )

    return steps
