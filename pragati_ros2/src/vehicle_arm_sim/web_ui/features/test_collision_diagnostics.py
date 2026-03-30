"""Parametrized collision diagnostic test.

For any set of camera coordinates (cam_x, cam_y, cam_z) for two arms, converts
them to joint values (j3, j4, j5) using the real FK pipeline (camera_to_arm +
polar_decompose), then runs all 5 collision avoidance modes and prints a
detailed report explaining:
  - The FK conversion result (cam -> joints)
  - Which point pairs collide
  - WHY they collide (which threshold was violated)
  - HOW each mode avoids or handles the collision

Usage:
    python3 -m pytest features/test_collision_diagnostics.py -s -v

The -s flag is essential — it lets print() reach the terminal.

Input: two space-delimited CSV files in this directory:
  arm1.csv — one row per arm1 camera point (cam_x cam_y cam_z)
  arm2.csv — one row per arm2 camera point (cam_x cam_y cam_z)
No header row. Every arm1 row is tested against every arm2 row (cartesian product).
"""
import itertools
import sys
from pathlib import Path

import pytest

# Ensure web_ui source is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collision_diagnostics import diagnose_collision


# ── Load points from space-delimited CSV files ────────────────────────────


def _load_csv(path: Path) -> list[tuple[float, float, float]]:
    """Load space-delimited CSV (no header) into list of (cam_x, cam_y, cam_z)."""
    if not path.exists():
        raise FileNotFoundError(
            f"CSV file not found: {path}\n"
            f"Create it with space-delimited rows: cam_x cam_y cam_z"
        )
    points = []
    with open(path) as f:
        for line_no, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) != 3:
                raise ValueError(
                    f"{path.name}:{line_no}: expected 3 values, "
                    f"got {len(parts)}"
                )
            points.append(
                (float(parts[0]), float(parts[1]), float(parts[2]))
            )
    if not points:
        raise ValueError(f"{path.name} is empty — need at least one row")
    return points


_FEATURES_DIR = Path(__file__).parent
_ARM1_POINTS = _load_csv(_FEATURES_DIR / "arm1.csv")
_ARM2_POINTS = _load_csv(_FEATURES_DIR / "arm2.csv")

SCENARIOS = list(itertools.product(_ARM1_POINTS, _ARM2_POINTS))

_IDS = [
    f"a1[{a1[0]:.3f},{a1[1]:.3f},{a1[2]:.3f}]"
    f"_x_"
    f"a2[{a2[0]:.3f},{a2[1]:.3f},{a2[2]:.3f}]"
    for a1, a2 in SCENARIOS
]


@pytest.fixture(params=range(len(SCENARIOS)), ids=_IDS)
def scenario_data(request):
    """Yield (arm1_cam_tuple, arm2_cam_tuple)."""
    return SCENARIOS[request.param]


def test_collision_diagnostic(scenario_data):
    """Run all 5 modes on a single cam-point pair and print diagnostics."""
    arm1_cam, arm2_cam = scenario_data

    report = diagnose_collision(
        arm1_cam_x=arm1_cam[0],
        arm1_cam_y=arm1_cam[1],
        arm1_cam_z=arm1_cam[2],
        arm2_cam_x=arm2_cam[0],
        arm2_cam_y=arm2_cam[1],
        arm2_cam_z=arm2_cam[2],
    )

    # ── Structure assertions ──────────────────────────────────────────
    # FK conversion produced valid joint dicts
    assert "arm1_joints" in report
    assert "arm2_joints" in report
    for key in ("j3", "j4", "j5"):
        assert key in report["arm1_joints"]
        assert key in report["arm2_joints"]

    assert "j4_gap" in report
    assert report["j4_gap"] == pytest.approx(
        abs(report["arm1_joints"]["j4"] - report["arm2_joints"]["j4"]),
        abs=1e-9,
    )
    assert "combined_j5" in report
    assert report["combined_j5"] == pytest.approx(
        report["arm1_joints"]["j5"] + report["arm2_joints"]["j5"],
        abs=1e-9,
    )

    # Reachability flags present
    assert "arm1_reachable" in report
    assert "arm2_reachable" in report

    # Every mode must be present with required fields
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
    arm1_j5 = report["arm1_joints"]["j5"]
    arm2_j5 = report["arm2_joints"]["j5"]
    m = report["modes"]

    # Mode 0: always NO_CHECK, passthrough
    assert m["mode_0"]["verdict"] == "NO_CHECK"

    # Mode 1: gap < 0.05 -> COLLISION, else SAFE
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

    # Mode 3: gap < 0.10 AND both j5 > 0 -> CONTENTION
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
