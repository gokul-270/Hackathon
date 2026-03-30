"""Parametrized collision diagnostic test.

For any set of camera points (cam_z) and j5 extensions, runs all 5 collision
avoidance modes and prints a detailed report explaining:
  - Which point pairs collide
  - WHY they collide (which threshold was violated)
  - HOW each mode avoids or handles the collision

Usage:
    python3 -m pytest features/test_collision_diagnostics.py -s -v

The -s flag is essential — it lets print() reach the terminal.
Add new scenarios by appending rows to SCENARIOS below.
"""
import sys
from pathlib import Path

import pytest

# Ensure web_ui source is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collision_diagnostics import diagnose_collision

# ── Scenarios: (label, arm1_cam_z, arm1_j5, arm2_cam_z, arm2_j5) ──────────
SCENARIOS = [
    ("identical positions — worst case", 0.10, 0.3, 0.10, 0.3),
    ("well separated arms", 0.10, 0.3, 0.02, 0.3),
    ("one arm retracted (j5=0)", 0.10, 0.0, 0.10, 0.3),
    ("close but above mode-1 threshold", 0.055, 0.3, 0.05, 0.3),
    ("inside mode-2 stage-2 zone, low j5", 0.07, 0.2, 0.065, 0.2),
    ("inside mode-3 zone, one arm retracted", 0.08, 0.5, 0.075, 0.0),
    ("boundary: exactly at mode-1 threshold", 0.10, 0.3, 0.05, 0.3),
    ("both arms at cam_z=0, max j4", 0.0, 0.5, 0.0, 0.5),
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
