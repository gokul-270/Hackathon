"""
Tests for the contention scenario pack — designed to make overlap-zone contention visible.

The contention scenario pack lives at:
  scenarios/contention_pack.json

It must contain scenarios where both arms target cotton in the overlap zone
simultaneously, causing contention in overlap_zone_wait mode and collisions in
unrestricted mode.

Design contract
---------------
The file scenarios/contention_pack.json must:
  1. Be valid JSON (loadable without error).
  2. Have at least 4 step_ids where BOTH arm1 and arm2 are present (dual-arm steps).
  3. When run with UNRESTRICTED mode, produce at least 1 step with collision
     (|j4_arm1 - j4_arm2| < 0.05 m).
  4. Have varied cam_z values across steps (not all identical) — scenario diversity.

These tests fail until the scenario file is created.
"""
import json
import os
import sys

import pytest

# Add web_ui to path so we can import fk_chain, run_controller, baseline_mode
_WEB_UI = os.path.dirname(__file__)
if _WEB_UI not in sys.path:
    sys.path.insert(0, _WEB_UI)

from baseline_mode import BaselineMode
from run_controller import RunController

_SCENARIO_PATH = os.path.join(
    os.path.dirname(__file__), "scenarios", "contention_pack.json"
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def contention_pack():
    """Load the contention scenario pack file."""
    with open(_SCENARIO_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Test 1: File is valid JSON
# ---------------------------------------------------------------------------


def test_contention_pack_file_is_valid_json():
    """The contention_pack.json file must exist and load without error."""
    assert os.path.exists(_SCENARIO_PATH), (
        f"contention_pack.json not found at {_SCENARIO_PATH}"
    )
    with open(_SCENARIO_PATH) as f:
        data = json.load(f)
    assert "steps" in data, "contention_pack.json must have a 'steps' key"


# ---------------------------------------------------------------------------
# Test 2: At least 4 dual-arm step_ids
# ---------------------------------------------------------------------------


def test_contention_pack_has_at_least_4_dual_arm_steps(contention_pack):
    """The pack must have at least 4 step_ids where both arm1 and arm2 are present."""
    step_map: dict[int, set] = {}
    for step in contention_pack["steps"]:
        step_map.setdefault(step["step_id"], set()).add(step["arm_id"])

    dual_arm_steps = [sid for sid, arms in step_map.items() if len(arms) == 2]
    assert len(dual_arm_steps) >= 4, (
        f"Expected >= 4 dual-arm step_ids (both arm1 and arm2), "
        f"got {len(dual_arm_steps)}: {dual_arm_steps}"
    )


# ---------------------------------------------------------------------------
# Test 3: UNRESTRICTED mode produces at least 1 collision
# ---------------------------------------------------------------------------


def test_contention_pack_unrestricted_run_produces_collisions():
    """Running with UNRESTRICTED mode must produce at least 1 collision step."""
    with open(_SCENARIO_PATH) as f:
        data = json.load(f)

    controller = RunController(mode=BaselineMode.UNRESTRICTED)
    controller.load_scenario(data)
    summary = controller.run()

    steps_with_collision = summary.get("steps_with_collision", 0)
    assert steps_with_collision >= 1, (
        f"Expected >= 1 collision step in UNRESTRICTED mode, got {steps_with_collision}. "
        f"Summary: {summary}"
    )


# ---------------------------------------------------------------------------
# Test 4: Varied cam_z values (scenario diversity)
# ---------------------------------------------------------------------------


def test_contention_pack_scenario_has_varied_cam_values(contention_pack):
    """Not all steps should have identical cam_z values — scenario must be diverse."""
    cam_z_values = {step["cam_z"] for step in contention_pack["steps"]}
    assert len(cam_z_values) >= 2, (
        f"Expected at least 2 distinct cam_z values for scenario diversity, "
        f"got {len(cam_z_values)}: {cam_z_values}"
    )
