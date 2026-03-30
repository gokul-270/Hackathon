"""Parametrized collision diagnostic test.

For any set of camera coordinates (cam_x, cam_y, cam_z) for two arms, converts
them to joint values (j3, j4, j5) using the real FK pipeline (camera_to_arm +
polar_decompose), then evaluates collision avoidance modes and prints a
detailed report.

Each mode is a **separate test**, so you can filter by mode:

    python3 -m pytest features/test_collision_diagnostics.py -s -v -k "mode_2"
    python3 -m pytest features/test_collision_diagnostics.py -s -v -k "mode_1"
    python3 -m pytest features/test_collision_diagnostics.py -s -v -k "mode_3 and solo"

Run all modes for all scenarios:
    python3 -m pytest features/test_collision_diagnostics.py -s -v

The -s flag is essential — it lets print() reach the terminal.

Input: two space-delimited CSV files in this directory:
  arm1.csv — one row per arm1 camera point (cam_x cam_y cam_z)
  arm2.csv — one row per arm2 camera point (cam_x cam_y cam_z)
No header row. Every arm1 row is tested against every arm2 row (cartesian
product). Additionally, each arm1 point and each arm2 point is tested solo
(no peer) to cover the unpaired-step case.
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


# ── Build scenario lists ──────────────────────────────────────────────────

# Paired: every arm1 row × every arm2 row (cartesian product)
_PAIRED = [
    ("paired", a1, a2)
    for a1, a2 in itertools.product(_ARM1_POINTS, _ARM2_POINTS)
]
_PAIRED_IDS = [
    f"a1[{a1[0]:.3f},{a1[1]:.3f},{a1[2]:.3f}]"
    f"_x_"
    f"a2[{a2[0]:.3f},{a2[1]:.3f},{a2[2]:.3f}]"
    for _, a1, a2 in _PAIRED
]

# Solo arm1: arm1 has a target, arm2 has no peer
_ARM1_SOLO = [("arm1_solo", a1, None) for a1 in _ARM1_POINTS]
_ARM1_SOLO_IDS = [
    f"a1[{a1[0]:.3f},{a1[1]:.3f},{a1[2]:.3f}]_solo"
    for _, a1, _ in _ARM1_SOLO
]

# Solo arm2: arm2 has a target, arm1 has no peer
_ARM2_SOLO = [("arm2_solo", None, a2) for a2 in _ARM2_POINTS]
_ARM2_SOLO_IDS = [
    f"a2[{a2[0]:.3f},{a2[1]:.3f},{a2[2]:.3f}]_solo"
    for _, _, a2 in _ARM2_SOLO
]

SCENARIOS = _PAIRED + _ARM1_SOLO + _ARM2_SOLO
_IDS = _PAIRED_IDS + _ARM1_SOLO_IDS + _ARM2_SOLO_IDS


# ── Report cache (avoid recomputing FK 5x per scenario) ──────────────────

_REPORT_CACHE: dict[tuple, dict] = {}


def _get_report(arm1_cam, arm2_cam) -> dict:
    """Return cached diagnostic report for a given point pair."""
    cache_key = (arm1_cam, arm2_cam)
    if cache_key not in _REPORT_CACHE:
        _REPORT_CACHE[cache_key] = diagnose_collision(
            arm1_cam_x=arm1_cam[0] if arm1_cam else None,
            arm1_cam_y=arm1_cam[1] if arm1_cam else None,
            arm1_cam_z=arm1_cam[2] if arm1_cam else None,
            arm2_cam_x=arm2_cam[0] if arm2_cam else None,
            arm2_cam_y=arm2_cam[1] if arm2_cam else None,
            arm2_cam_z=arm2_cam[2] if arm2_cam else None,
        )
    return _REPORT_CACHE[cache_key]


# ── Mode labels for output ───────────────────────────────────────────────

_MODE_NAMES = {
    0: "Mode 0 (unrestricted)",
    1: "Mode 1 (baseline_j5_block)",
    2: "Mode 2 (geometry_block)",
    3: "Mode 3 (sequential_pick)",
    4: "Mode 4 (smart_reorder)",
}

_VERDICT_SYMBOLS = {
    "NO_CHECK": "  ",
    "SAFE": "\u2705",
    "COLLISION": "\u274c",
    "CONTENTION": "\u26a0\ufe0f ",
    "REORDER_CANDIDATE": "\u2194\ufe0f ",
}


# ── Test function ─────────────────────────────────────────────────────────


@pytest.fixture(params=range(len(SCENARIOS)), ids=_IDS)
def scenario_data(request):
    """Yield (kind, arm1_cam_or_None, arm2_cam_or_None)."""
    return SCENARIOS[request.param]


@pytest.mark.parametrize(
    "mode",
    [0, 1, 2, 3, 4],
    ids=[f"mode_{i}" for i in range(5)],
)
def test_collision_diagnostic(scenario_data, mode):
    """Run a single mode on a cam-point pair (or solo) and print diagnostics."""
    kind, arm1_cam, arm2_cam = scenario_data

    report = _get_report(arm1_cam, arm2_cam)

    mode_key = f"mode_{mode}"

    # ── Structure assertions ──────────────────────────────────────────
    assert mode_key in report["modes"], f"Missing {mode_key}"
    mr = report["modes"][mode_key]
    assert "verdict" in mr
    assert "reason" in mr
    assert "intervention" in mr

    if kind == "paired":
        _assert_paired_mode(report, mode_key, mode)
    else:
        _assert_solo_mode(report, mode_key, mode, kind)

    # ── Print per-mode diagnostic ─────────────────────────────────────
    _print_mode_diagnostic(report, mode_key, mode, kind, arm1_cam, arm2_cam)


# ── Per-mode assertions ──────────────────────────────────────────────────


def _assert_paired_mode(report, mode_key, mode):
    """Assertions for a specific mode in a paired scenario."""
    for arm in ("arm1_joints", "arm2_joints"):
        assert arm in report
        for key in ("j3", "j4", "j5"):
            assert key in report[arm]

    assert report["j4_gap"] == pytest.approx(
        abs(report["arm1_joints"]["j4"] - report["arm2_joints"]["j4"]),
        abs=1e-9,
    )
    assert report["combined_j5"] == pytest.approx(
        report["arm1_joints"]["j5"] + report["arm2_joints"]["j5"],
        abs=1e-9,
    )

    gap = report["j4_gap"]
    cj5 = report["combined_j5"]
    arm1_j5 = report["arm1_joints"]["j5"]
    arm2_j5 = report["arm2_joints"]["j5"]
    mr = report["modes"][mode_key]

    if mode == 0:
        assert mr["verdict"] == "NO_CHECK"
    elif mode == 1:
        if gap < 0.05:
            assert mr["verdict"] == "COLLISION"
            assert mr["intervention"] == "j5_zeroed"
        else:
            assert mr["verdict"] == "SAFE"
            assert mr["intervention"] == "none"
    elif mode == 2:
        if gap >= 0.12:
            assert mr["verdict"] == "SAFE"
        elif gap < 0.06 and cj5 > 0.5:
            assert mr["verdict"] == "COLLISION"
            assert mr["intervention"] == "j5_zeroed"
        else:
            assert mr["verdict"] == "SAFE"
    elif mode == 3:
        if gap < 0.10 and arm1_j5 > 0 and arm2_j5 > 0:
            assert mr["verdict"] == "CONTENTION"
            assert mr["intervention"] == "sequenced"
        else:
            assert mr["verdict"] == "SAFE"
            assert mr["intervention"] == "none"
    elif mode == 4:
        assert mr["verdict"] == "REORDER_CANDIDATE"


def _assert_solo_mode(report, mode_key, mode, kind):
    """Assertions for a specific mode in a solo scenario."""
    assert report["solo"] is True

    if kind == "arm1_solo":
        assert report["arm1_joints"] is not None
        assert report["arm2_joints"] is None
        for key in ("j3", "j4", "j5"):
            assert key in report["arm1_joints"]
    else:
        assert report["arm2_joints"] is not None
        assert report["arm1_joints"] is None
        for key in ("j3", "j4", "j5"):
            assert key in report["arm2_joints"]

    assert report["j4_gap"] is None
    assert report["combined_j5"] is None

    mr = report["modes"][mode_key]
    if mode == 0:
        assert mr["verdict"] == "NO_CHECK"
    else:
        assert mr["verdict"] == "SAFE"
        assert mr["intervention"] == "none"


# ── Per-mode diagnostic printer ──────────────────────────────────────────


def _print_mode_diagnostic(report, mode_key, mode, kind, arm1_cam, arm2_cam):
    """Print a concise diagnostic for a single mode."""
    mr = report["modes"][mode_key]
    sym = _VERDICT_SYMBOLS.get(mr["verdict"], "?")
    w = 72
    lines = ["-" * w]

    # FK header
    if kind == "paired":
        a1j = report["arm1_joints"]
        a2j = report["arm2_joints"]
        lines.append(
            f"  arm1: cam({arm1_cam[0]:.3f}, {arm1_cam[1]:.3f}, "
            f"{arm1_cam[2]:.3f}) -> "
            f"j3={a1j['j3']:+.4f}  j4={a1j['j4']:.4f}  "
            f"j5={a1j['j5']:.4f}"
        )
        lines.append(
            f"  arm2: cam({arm2_cam[0]:.3f}, {arm2_cam[1]:.3f}, "
            f"{arm2_cam[2]:.3f}) -> "
            f"j3={a2j['j3']:+.4f}  j4={a2j['j4']:.4f}  "
            f"j5={a2j['j5']:.4f}"
        )
        lines.append(
            f"  j4_gap={report['j4_gap']:.4f}m  "
            f"combined_j5={report['combined_j5']:.4f}m"
        )
    else:
        active = "arm1" if kind == "arm1_solo" else "arm2"
        cam = arm1_cam if kind == "arm1_solo" else arm2_cam
        joints = report[f"{active}_joints"]
        lines.append(
            f"  {active} (solo): cam({cam[0]:.3f}, {cam[1]:.3f}, "
            f"{cam[2]:.3f}) -> "
            f"j3={joints['j3']:+.4f}  j4={joints['j4']:.4f}  "
            f"j5={joints['j5']:.4f}"
        )

    # Mode verdict
    lines.append(
        f"  {sym} {_MODE_NAMES[mode]:<30s} {mr['verdict']}"
    )
    lines.append(f"     Reason:       {mr['reason']}")
    lines.append(f"     Intervention: {mr['intervention']}")
    lines.append(f"     Details:      {mr['details']}")
    lines.append("-" * w)

    print("\n".join(lines))
