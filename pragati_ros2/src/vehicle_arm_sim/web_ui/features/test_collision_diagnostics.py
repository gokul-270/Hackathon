"""Parametrized collision diagnostic test.

For any set of camera points (cam_z) and j5 extensions, runs all 5 collision
avoidance modes and prints a detailed report explaining:
  - Which point pairs collide
  - WHY they collide (which threshold was violated)
  - HOW each mode avoids or handles the collision

Usage:
    python3 -m pytest features/test_collision_diagnostics.py -s -v

The -s flag is essential — it lets print() reach the terminal.

To change test inputs, edit test_scenarios.json in this directory.
Each object needs: label, arm1_cam_z, arm1_j5, arm2_cam_z, arm2_j5.
"""
import json
import sys
from pathlib import Path

import pytest

# Ensure web_ui source is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collision_diagnostics import diagnose_collision

# ── Load scenarios from JSON file ──────────────────────────────────────────
_SCENARIO_FILE = Path(__file__).parent / "test_scenarios.json"

if not _SCENARIO_FILE.exists():
    raise FileNotFoundError(
        f"Scenario file not found: {_SCENARIO_FILE}\n"
        f"Create it with an array of objects, each having: "
        f"label, arm1_cam_z, arm1_j5, arm2_cam_z, arm2_j5"
    )

with open(_SCENARIO_FILE) as _f:
    _raw = json.load(_f)

SCENARIOS = [
    (s["label"], s["arm1_cam_z"], s["arm1_j5"], s["arm2_cam_z"], s["arm2_j5"])
    for s in _raw
]


@pytest.fixture(params=SCENARIOS, ids=[s[0] for s in SCENARIOS])
def scenario_data(request):
    """Yield (label, arm1_cam_z, arm1_j5, arm2_cam_z, arm2_j5)."""
    return request.param


def test_collision_diagnostic(scenario_data, capsys):
    """Run all 5 modes on a single cam-point pair and print diagnostics."""
    label, arm1_cam_z, arm1_j5, arm2_cam_z, arm2_j5 = scenario_data

    report = diagnose_collision(
        arm1_cam_z=arm1_cam_z,
        arm1_j5=arm1_j5,
        arm2_cam_z=arm2_cam_z,
        arm2_j5=arm2_j5,
    )

    # ── Structure assertions ──────────────────────────────────────────
    assert report["arm1_j4"] == pytest.approx(0.1005 - arm1_cam_z, abs=1e-9)
    assert report["arm2_j4"] == pytest.approx(0.1005 - arm2_cam_z, abs=1e-9)
    assert report["j4_gap"] == pytest.approx(
        abs(report["arm1_j4"] - report["arm2_j4"]), abs=1e-9
    )
    assert report["combined_j5"] == pytest.approx(arm1_j5 + arm2_j5, abs=1e-9)

    # Every mode must be present
    for mode_id in range(5):
        mode_key = f"mode_{mode_id}"
        assert mode_key in report["modes"], f"Missing {mode_key}"
        mode_report = report["modes"][mode_key]
        assert "verdict" in mode_report
        assert "reason" in mode_report
        assert "intervention" in mode_report

    # ── Per-mode correctness assertions ───────────────────────────────
    gap = report["j4_gap"]
    cj5 = report["combined_j5"]
    m = report["modes"]

    # Mode 0: always SAFE, passthrough
    assert m["mode_0"]["verdict"] == "NO_CHECK"

    # Mode 1: gap < 0.05 → COLLISION, else SAFE
    if gap < 0.05:
        assert m["mode_1"]["verdict"] == "COLLISION"
        assert m["mode_1"]["intervention"] == "j5_zeroed"
    else:
        assert m["mode_1"]["verdict"] == "SAFE"
        assert m["mode_1"]["intervention"] == "none"

    # Mode 2: two-stage
    if gap >= 0.12:
        assert m["mode_2"]["verdict"] == "SAFE"
    elif gap < 0.06 and cj5 > 0.5:
        assert m["mode_2"]["verdict"] == "COLLISION"
        assert m["mode_2"]["intervention"] == "j5_zeroed"
    else:
        assert m["mode_2"]["verdict"] == "SAFE"

    # Mode 3: gap < 0.10 AND both j5 > 0 → CONTENTION
    if gap < 0.10 and arm1_j5 > 0 and arm2_j5 > 0:
        assert m["mode_3"]["verdict"] == "CONTENTION"
        assert m["mode_3"]["intervention"] == "sequenced"
    else:
        assert m["mode_3"]["verdict"] == "SAFE"
        assert m["mode_3"]["intervention"] == "none"

    # Mode 4: per-step passthrough
    assert m["mode_4"]["verdict"] == "REORDER_CANDIDATE"

    # ── Print human-readable diagnostic ───────────────────────────────
    print(report["formatted_output"])
