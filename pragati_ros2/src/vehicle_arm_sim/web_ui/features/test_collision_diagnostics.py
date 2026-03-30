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
import math
import sys
from pathlib import Path

import pytest

# Ensure web_ui source is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collision_diagnostics import MODE1_ADJ, diagnose_collision
from fk_chain import camera_to_arm, phi_compensation, polar_decompose
from smart_reorder_scheduler import FK_OFFSET, SmartReorderScheduler


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


from conftest import _csv_paths, _test_options

_FEATURES_DIR = Path(__file__).parent
_ARM1_POINTS = _load_csv(
    Path(_csv_paths["arm1"]) if _csv_paths["arm1"] else _FEATURES_DIR / "arm1.csv"
)
_ARM2_POINTS = _load_csv(
    Path(_csv_paths["arm2"]) if _csv_paths["arm2"] else _FEATURES_DIR / "arm2.csv"
)


# ── Build scenario lists ──────────────────────────────────────────────────

if _test_options["cartesian"]:
    # Exhaustive: every arm1 row × every arm2 row
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
    # Solo: all arm1 and all arm2 points run solo
    _ARM1_SOLO = [("arm1_solo", a1, None) for a1 in _ARM1_POINTS]
    _ARM1_SOLO_IDS = [
        f"a1[{a1[0]:.3f},{a1[1]:.3f},{a1[2]:.3f}]_solo"
        for _, a1, _ in _ARM1_SOLO
    ]
    _ARM2_SOLO = [("arm2_solo", None, a2) for a2 in _ARM2_POINTS]
    _ARM2_SOLO_IDS = [
        f"a2[{a2[0]:.3f},{a2[1]:.3f},{a2[2]:.3f}]_solo"
        for _, _, a2 in _ARM2_SOLO
    ]
else:
    # Default: sequential 1-to-1 (arm1[i] ↔ arm2[i])
    _paired_count = min(len(_ARM1_POINTS), len(_ARM2_POINTS))
    _PAIRED = [
        ("paired", _ARM1_POINTS[i], _ARM2_POINTS[i])
        for i in range(_paired_count)
    ]
    _PAIRED_IDS = [
        f"a1[{a1[0]:.3f},{a1[1]:.3f},{a1[2]:.3f}]"
        f"_seq_"
        f"a2[{a2[0]:.3f},{a2[1]:.3f},{a2[2]:.3f}]"
        for _, a1, a2 in _PAIRED
    ]
    # Solo: arm1 tail (if arm1 is longer) and arm2 tail (if arm2 is longer)
    _ARM1_SOLO = [("arm1_solo", a1, None) for a1 in _ARM1_POINTS[_paired_count:]]
    _ARM1_SOLO_IDS = [
        f"a1[{a1[0]:.3f},{a1[1]:.3f},{a1[2]:.3f}]_solo"
        for _, a1, _ in _ARM1_SOLO
    ]
    _ARM2_SOLO = [("arm2_solo", None, a2) for a2 in _ARM2_POINTS[_paired_count:]]
    _ARM2_SOLO_IDS = [
        f"a2[{a2[0]:.3f},{a2[1]:.3f},{a2[2]:.3f}]_solo"
        for _, _, a2 in _ARM2_SOLO
    ]

SCENARIOS = _PAIRED + _ARM1_SOLO + _ARM2_SOLO
_IDS = _PAIRED_IDS + _ARM1_SOLO_IDS + _ARM2_SOLO_IDS

# ── Mode 1 per-arm solo scenarios (all arm1 + all arm2, unpaired) ─────────
# Mode 1's cosine j5 limit only uses the arm's own j3/j5; the peer is only a
# gate (no peer → skip). Running Mode 1 as individual-arm solo tests ensures
# every arm point is exercised independently of pairing order or CSV length.
_MODE1_SOLO_SCENARIOS = (
    [("arm1_solo", a1, None) for a1 in _ARM1_POINTS]
    + [("arm2_solo", None, a2) for a2 in _ARM2_POINTS]
)
_MODE1_SOLO_IDS = (
    [f"a1[{a[0]:.3f},{a[1]:.3f},{a[2]:.3f}]_m1solo" for a in _ARM1_POINTS]
    + [f"a2[{a[0]:.3f},{a[1]:.3f},{a[2]:.3f}]_m1solo" for a in _ARM2_POINTS]
)


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


@pytest.mark.parametrize(
    "scenario",
    _MODE1_SOLO_SCENARIOS,
    ids=_MODE1_SOLO_IDS,
)
def test_mode1_per_arm_solo(scenario):
    """Mode 1 cosine j5 limit check — one arm at a time, no peer.

    Mode 1's formula only depends on the arm's own j3/j5.  The peer is only
    used as a gate: when there is no peer the check is skipped and the arm
    runs freely.  This test exercises every arm1 and arm2 point individually,
    verifying that Mode 1 reports SAFE (no peer → skip) for each solo point.
    """
    kind, arm1_cam, arm2_cam = scenario
    report = _get_report(arm1_cam, arm2_cam)

    assert report["solo"] is True
    mr = report["modes"]["mode_1"]
    assert mr["verdict"] == "SAFE", (
        f"Mode 1 solo expected SAFE (no peer → skip), got {mr['verdict']}: "
        f"{mr['reason']}"
    )
    assert mr["intervention"] == "none", (
        f"Mode 1 solo expected intervention=none, got {mr['intervention']}"
    )

    # Print diagnostic (visible with -s)
    _print_mode_diagnostic(report, "mode_1", 1, kind, arm1_cam, arm2_cam)

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
        arm1_j3 = report["arm1_joints"]["j3"]
        theta1 = abs(arm1_j3)
        cos_theta1 = math.cos(theta1)
        j5_limit1 = MODE1_ADJ / cos_theta1 if cos_theta1 > 0.1 else float("inf")
        arm1_j5_val = report["arm1_joints"]["j5"]
        if arm1_j5_val > j5_limit1:
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


# ── Mode 4 helpers ────────────────────────────────────────────────────────


def _compute_min_gap(step_map: dict, paired_count: int) -> float:
    """Return the minimum j4 gap across paired steps only (ignores solo tail)."""
    gaps = []
    for i in range(paired_count):
        row = step_map.get(i, {})
        if "arm1" in row and "arm2" in row:
            j4_a1 = FK_OFFSET - row["arm1"]["cam_z"]
            j4_a2 = FK_OFFSET - row["arm2"]["cam_z"]
            gaps.append(abs(j4_a1 - j4_a2))
    return min(gaps) if gaps else 0.0


def _print_reorder_table(title: str, step_map: dict, paired_count: int) -> None:
    """Print a fixed-width before/after table for the reorder diagnostic."""
    w = 72
    hdr = (
        f"{'Step':>4}  {'arm1 cam_z':>10}  {'arm1 j4':>8}  "
        f"{'arm2 cam_z':>10}  {'arm2 j4':>8}  {'j4 gap':>8}"
    )
    print(f"\n── Mode 4: Smart Reorder – {title} {'─' * (w - 28 - len(title))}")
    print(f" {hdr}")
    print(f" {'─'*4}  {'─'*10}  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*8}")

    total_steps = max(step_map.keys()) + 1 if step_map else 0
    gaps = []
    for i in range(total_steps):
        row = step_map.get(i, {})
        has_a1 = "arm1" in row
        has_a2 = "arm2" in row

        if has_a1:
            cz1 = row["arm1"]["cam_z"]
            j4_1 = FK_OFFSET - cz1
            s_cz1 = f"{cz1:>10.4f}"
            s_j4_1 = f"{j4_1:>8.4f}"
        else:
            s_cz1 = f"{'---':>10}"
            s_j4_1 = f"{'---':>8}"

        if has_a2:
            cz2 = row["arm2"]["cam_z"]
            j4_2 = FK_OFFSET - cz2
            s_cz2 = f"{cz2:>10.4f}"
            s_j4_2 = f"{j4_2:>8.4f}"
        else:
            s_cz2 = f"{'---':>10}"
            s_j4_2 = f"{'---':>8}"

        if has_a1 and has_a2 and i < paired_count:
            gap = abs((FK_OFFSET - cz1) - (FK_OFFSET - cz2))
            gaps.append(gap)
            s_gap = f"{gap:>8.4f}"
            label = ""
        elif has_a1 and not has_a2:
            s_gap = f"{'---':>8}"
            label = "  (solo arm1)"
        elif has_a2 and not has_a1:
            s_gap = f"{'---':>8}"
            label = "  (solo arm2)"
        else:
            s_gap = f"{'---':>8}"
            label = ""

        print(f" {i:>4}  {s_cz1}  {s_j4_1}  {s_cz2}  {s_j4_2}  {s_gap}{label}")

    min_gap = min(gaps) if gaps else 0.0
    print(f"  {'─'*w}")
    print(f"  min paired gap: {min_gap:.4f} m\n")


def test_diagnostic_j3_uses_compensated_phi():
    """collision_diagnostics._cam_to_joints must apply phi_compensation to j3.

    At runtime, ArmRuntime.compute_candidate_joints() calls phi_compensation()
    on j3 before passing joints to BaselineMode.  The diagnostics engine must
    do the same so Mode 1 verdicts are consistent with the real run.

    Uses the first arm1 CSV point as a concrete example.
    """
    cam_x, cam_y, cam_z = _ARM1_POINTS[0]
    ax, ay, az = camera_to_arm(cam_x, cam_y, cam_z, j4_pos=0.0)
    raw = polar_decompose(ax, ay, az)
    expected_j3 = phi_compensation(raw["j3"], raw["j5"])

    report = _get_report((cam_x, cam_y, cam_z), None)  # solo arm1
    actual_j3 = report["arm1_joints"]["j3"]

    assert actual_j3 == pytest.approx(expected_j3, abs=1e-9), (
        f"Diagnostic j3 {actual_j3:.6f} != compensated phi {expected_j3:.6f} "
        f"(raw={raw['j3']:.6f}). "
        f"collision_diagnostics._cam_to_joints() must call phi_compensation()."
    )


def test_mode1_solo_scenarios_cover_all_arm_points():
    """Mode 1 solo scenarios must cover every arm1 point and every arm2 point.

    Mode 1's cosine j5 limit only depends on the arm's own j3/j5 — the peer is
    only used as a gate (no peer → skip). Testing Mode 1 per-arm (solo) rather
    than in paired scenarios ensures every individual arm point is exercised
    regardless of pairing order or CSV length.
    """
    import test_collision_diagnostics as _mod

    expected = len(_ARM1_POINTS) + len(_ARM2_POINTS)
    assert hasattr(_mod, "_MODE1_SOLO_SCENARIOS"), (
        "_MODE1_SOLO_SCENARIOS list not found in test_collision_diagnostics"
    )
    actual = len(_mod._MODE1_SOLO_SCENARIOS)
    assert actual == expected, (
        f"_MODE1_SOLO_SCENARIOS has {actual} entries; "
        f"expected {expected} (arm1={len(_ARM1_POINTS)}, arm2={len(_ARM2_POINTS)})"
    )


def test_test_options_dict_is_importable_from_conftest():
    """Confirm conftest exposes _test_options with cartesian key."""
    from conftest import _test_options

    assert "cartesian" in _test_options
    assert isinstance(_test_options["cartesian"], bool)


def test_csv_paths_dict_is_importable_from_conftest():
    """Confirm conftest exposes _csv_paths with arm1/arm2 keys."""
    from conftest import _csv_paths

    assert "arm1" in _csv_paths
    assert "arm2" in _csv_paths


def test_mode4_reorder_improves_gap():
    """Mode 4: SmartReorderScheduler must not decrease the min j4 gap
    when applied to the real arm1.csv / arm2.csv cam points.

    Prints a before/after table (visible with -s) showing step order,
    per-arm cam_z, j4, and gap values, plus a summary delta line.
    """
    paired_count = min(len(_ARM1_POINTS), len(_ARM2_POINTS))
    if paired_count < 2:
        pytest.skip(
            f"Need at least 2 paired steps to test reorder benefit "
            f"(arm1={len(_ARM1_POINTS)}, arm2={len(_ARM2_POINTS)})"
        )

    # Build original step_map (sequential pairing: arm1[i] ↔ arm2[i])
    step_map = {
        i: {
            "arm1": {
                "cam_z": _ARM1_POINTS[i][2],
                "cam_x": _ARM1_POINTS[i][0],
                "cam_y": _ARM1_POINTS[i][1],
            },
            "arm2": {
                "cam_z": _ARM2_POINTS[i][2],
                "cam_x": _ARM2_POINTS[i][0],
                "cam_y": _ARM2_POINTS[i][1],
            },
        }
        for i in range(paired_count)
    }
    # Append solo-tail steps for whichever arm has more rows
    solo_id = paired_count
    for pt in _ARM1_POINTS[paired_count:]:
        step_map[solo_id] = {"arm1": {"cam_z": pt[2], "cam_x": pt[0], "cam_y": pt[1]}}
        solo_id += 1
    for pt in _ARM2_POINTS[paired_count:]:
        step_map[solo_id] = {"arm2": {"cam_z": pt[2], "cam_x": pt[0], "cam_y": pt[1]}}
        solo_id += 1

    arm1_steps = list(range(paired_count))
    arm2_steps = list(range(paired_count))

    original_min_gap = _compute_min_gap(step_map, paired_count)
    _print_reorder_table("BEFORE REORDER", step_map, paired_count)

    reordered = SmartReorderScheduler().reorder(step_map, arm1_steps, arm2_steps)

    reordered_min_gap = _compute_min_gap(reordered, paired_count)
    _print_reorder_table("AFTER REORDER", reordered, paired_count)

    delta = reordered_min_gap - original_min_gap
    sign = "+" if delta >= 0 else ""
    print(
        f"\n  Mode 4 reorder result:  "
        f"min_gap  {original_min_gap:.4f}m  →  {reordered_min_gap:.4f}m  "
        f"(delta: {sign}{delta:.4f}m)"
    )

    assert reordered_min_gap >= original_min_gap, (
        f"Reorder degraded min j4 gap: "
        f"before={original_min_gap:.4f}m, after={reordered_min_gap:.4f}m"
    )
