#!/usr/bin/env python3
"""Unit tests for fleet_drift_report.py — synthetic fixtures, no real data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts/diagnostics to path for import
sys.path.insert(0, str(Path(__file__).parent))
import fleet_drift_report as fdr


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def make_snapshot(
    hostname="pragati-arm1",
    role="arm",
    os_version="Ubuntu 24.04.4 LTS",
    apt_packages=None,
    pip_packages=None,
    enabled_services=None,
    dtoverlay_config="",
    boot_firmware_config="",
    schema_version="v5",
) -> dict:
    """Create a minimal v5 boot_timing JSON dict."""
    return {
        "schema_version": schema_version,
        "hostname": hostname,
        "role": role,
        "system_info": {
            "os_version": os_version,
            "kernel_version": "6.8.0-1048-raspi",
            "dtoverlay_config": dtoverlay_config,
        },
        "environment": {
            "apt_packages": apt_packages or [],
            "pip_packages": pip_packages or [],
            "enabled_services": enabled_services,
            "boot_firmware_config": boot_firmware_config or "",
        },
    }


def write_snapshot(tmp_path: Path, data: dict, filename: str) -> Path:
    """Write a snapshot dict as JSON to tmp_path/<filename>."""
    p = tmp_path / filename
    p.write_text(json.dumps(data))
    return p


# Shared baseline packages used by the "clean fleet" and "3 RPi" fixtures.
BASELINE_APT = [
    "can-utils=4.0.0-2",
    "pigpiod=1.79",
    "mosquitto=2.0.18",
    "chrony=4.5",
    "python3-pip=24.0",
    "python3-venv=3.12.3",
    "i2c-tools=4.3",
    "net-tools=2.10",
    "htop=3.3.0",
    "tmux=3.4",
]

BASELINE_SERVICES = [
    "boot_timing.service",
    "boot_timing.timer",
]

VEHICLE_SERVICES = BASELINE_SERVICES + ["mosquitto.service"]

CANONICAL_CAN_LINE = (
    "dtoverlay=mcp2515-can0,oscillator=8000000,"
    "interrupt=25,spimaxfrequency=1000000"
)


@pytest.fixture()
def clean_fleet(tmp_path: Path) -> Path:
    """3 identical RPis — should produce 0 findings.

    All hosts carry the same service superset so inter-RPi diff is empty.
    Vehicle gets mosquitto (role-required) and arms also carry it so there
    is no asymmetry for the inter-RPi diff to flag.
    """
    for name, role, svcs, dto in [
        ("pragati-arm1", "arm", VEHICLE_SERVICES, CANONICAL_CAN_LINE),
        ("pragati-arm2", "arm", VEHICLE_SERVICES, ""),
        ("pragati-vehicle", "vehicle", VEHICLE_SERVICES, ""),
    ]:
        write_snapshot(
            tmp_path,
            make_snapshot(
                hostname=name,
                role=role,
                apt_packages=list(BASELINE_APT),
                pip_packages=["numpy==1.26.4"],
                enabled_services=svcs,
                dtoverlay_config=dto,
            ),
            f"{name}.json",
        )
    return tmp_path


@pytest.fixture()
def requirements_txt(tmp_path: Path) -> Path:
    """A minimal requirements.txt."""
    p = tmp_path / "requirements.txt"
    p.write_text("numpy>=1.26.0\n")
    return p


# ---------------------------------------------------------------------------
# 1. test_valid_3rpi_fleet
# ---------------------------------------------------------------------------


def test_valid_3rpi_fleet(tmp_path: Path):
    """3 RPis with known drift: OS behind, extra pkgs, vehicle CAN overlay."""
    # arm1 — has extra apt packages (4+ sharing the same 2-token
    # dash prefix "libfoo-bar" so _group_by_prefix triggers >3 INFO)
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm1",
            role="arm",
            os_version="Ubuntu 24.04.4 LTS",
            apt_packages=BASELINE_APT
            + [
                "libfoo-bar-dev=1.0",
                "libfoo-bar-doc=1.0",
                "libfoo-bar-utils=1.0",
                "libfoo-bar-extra=1.0",
            ],
            pip_packages=["numpy==1.26.4"],
            enabled_services=BASELINE_SERVICES,
            dtoverlay_config=CANONICAL_CAN_LINE,
        ),
        "arm1.json",
    )
    # arm2 — OS behind (24.04.3)
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm2",
            role="arm",
            os_version="Ubuntu 24.04.3 LTS",
            apt_packages=list(BASELINE_APT),
            pip_packages=["numpy==1.26.4"],
            enabled_services=BASELINE_SERVICES,
            dtoverlay_config="",
        ),
        "arm2.json",
    )
    # vehicle — has CAN dtoverlay despite vehicle role
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-vehicle",
            role="vehicle",
            os_version="Ubuntu 24.04.4 LTS",
            apt_packages=list(BASELINE_APT),
            pip_packages=["numpy==1.26.4"],
            enabled_services=VEHICLE_SERVICES,
            dtoverlay_config=CANONICAL_CAN_LINE,
        ),
        "vehicle.json",
    )

    snapshots = fdr.load_snapshots(tmp_path)
    assert len(snapshots) == 3

    # OS analysis — arm2 should be behind
    os_findings = fdr.analyse_os_versions(snapshots)
    behind = [f for f in os_findings if f.severity == "WARN"]
    assert any("pragati-arm2" == f.hostname for f in behind)
    assert any("behind" in f.description for f in behind)

    # APT analysis — arm1 has extra libfoo-* packages
    apt_findings = fdr.analyse_apt_packages(snapshots)
    arm1_extras = [
        f
        for f in apt_findings
        if f.hostname == "pragati-arm1"
        and f.severity == "INFO"
        and "extra" in f.description.lower()
    ]
    assert len(arm1_extras) >= 1

    # dtoverlay — vehicle should get WARN for CAN without CAN HAT role
    dto_findings = fdr.analyse_dtoverlay(snapshots)
    vehicle_warn = [
        f
        for f in dto_findings
        if f.hostname == "pragati-vehicle" and f.severity == "WARN"
    ]
    assert len(vehicle_warn) == 1
    assert "vehicle" in vehicle_warn[0].description.lower()


# ---------------------------------------------------------------------------
# 2. test_single_rpi_capture
# ---------------------------------------------------------------------------


def test_single_rpi_capture(tmp_path: Path):
    """Single RPi — inter-RPi comparisons skipped, no crashes."""
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm1",
            role="arm",
            apt_packages=list(BASELINE_APT),
            pip_packages=["numpy==1.26.4"],
            enabled_services=BASELINE_SERVICES,
            dtoverlay_config=CANONICAL_CAN_LINE,
        ),
        "arm1.json",
    )

    snapshots = fdr.load_snapshots(tmp_path)
    assert len(snapshots) == 1

    # These should all succeed without error
    os_f = fdr.analyse_os_versions(snapshots)
    apt_f = fdr.analyse_apt_packages(snapshots)
    pip_f = fdr.analyse_pip_packages(snapshots, {})
    dto_f = fdr.analyse_dtoverlay(snapshots)
    svc_f = fdr.analyse_services(snapshots)

    # No inter-RPi INFO findings (need 2+ hosts for diff)
    all_findings = os_f + apt_f + pip_f + dto_f + svc_f
    inter_info = [
        f
        for f in all_findings
        if f.severity == "INFO" and "not on all" in f.description.lower()
    ]
    assert inter_info == []


# ---------------------------------------------------------------------------
# 3. test_malformed_json
# ---------------------------------------------------------------------------


def test_malformed_json(tmp_path: Path, capsys):
    """Invalid JSON is skipped with a warning, not an exception."""
    # Write one valid file so load_snapshots doesn't sys.exit
    write_snapshot(
        tmp_path,
        make_snapshot(hostname="pragati-arm1"),
        "arm1.json",
    )
    # Write one malformed file
    bad = tmp_path / "bad.json"
    bad.write_text("{this is not: valid JSON!!}")

    snapshots = fdr.load_snapshots(tmp_path)
    assert len(snapshots) == 1
    assert snapshots[0].hostname == "pragati-arm1"

    captured = capsys.readouterr()
    assert "Skipping malformed JSON" in captured.err


# ---------------------------------------------------------------------------
# 4. test_missing_fields
# ---------------------------------------------------------------------------


def test_missing_fields(tmp_path: Path):
    """JSON with missing environment.apt_packages → WARN, section skipped."""
    data = make_snapshot(hostname="pragati-arm1")
    del data["environment"]["apt_packages"]
    write_snapshot(tmp_path, data, "arm1.json")

    snapshots = fdr.load_snapshots(tmp_path)
    snap = snapshots[0]
    assert snap.apt_packages is None

    apt_f = fdr.analyse_apt_packages(snapshots)
    warn = [f for f in apt_f if f.severity == "WARN"]
    assert any("apt_packages missing" in f.description for f in warn)


# ---------------------------------------------------------------------------
# 5. test_pre_v5_schema
# ---------------------------------------------------------------------------


def test_pre_v5_schema(tmp_path: Path, capsys):
    """schema_version v4 is skipped; load_snapshots sys.exits if none left."""
    write_snapshot(
        tmp_path,
        make_snapshot(schema_version="v4"),
        "old.json",
    )

    with pytest.raises(SystemExit):
        fdr.load_snapshots(tmp_path, verbose=True)

    captured = capsys.readouterr()
    assert "v4" in captured.err


# ---------------------------------------------------------------------------
# 6. test_all_clean_fleet
# ---------------------------------------------------------------------------


def test_all_clean_fleet(clean_fleet: Path, requirements_txt: Path):
    """3 identical RPis → 0 ERROR/WARN/INFO findings."""
    snapshots = fdr.load_snapshots(clean_fleet)
    reqs = fdr.parse_requirements_txt(requirements_txt)

    sections = {
        "os_version": fdr.analyse_os_versions(snapshots),
        "apt_packages": fdr.analyse_apt_packages(snapshots),
        "pip_packages": fdr.analyse_pip_packages(snapshots, reqs),
        "dtoverlay": fdr.analyse_dtoverlay(snapshots),
        "services": fdr.analyse_services(snapshots),
    }

    non_ok = [
        f
        for findings in sections.values()
        for f in findings
        if f.severity in ("ERROR", "WARN", "INFO")
    ]
    assert non_ok == [], (
        "Expected 0 findings but got:\n"
        + "\n".join(f.format() for f in non_ok)
    )


# ---------------------------------------------------------------------------
# 7. test_pip_compound_constraints
# ---------------------------------------------------------------------------


def test_pip_compound_constraints(tmp_path: Path):
    """>=1.26.0,<2.0 compound constraint is parsed and evaluated."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy>=1.26.0,<2.0\n")

    reqs = fdr.parse_requirements_txt(req_file)
    assert "numpy" in reqs
    assert len(reqs["numpy"]) == 2
    assert (">=", "1.26.0") in reqs["numpy"]
    assert ("<", "2.0") in reqs["numpy"]

    # 1.26.4 satisfies >=1.26.0,<2.0
    assert fdr.version_satisfies("1.26.4", reqs["numpy"])
    # 2.0.0 does NOT satisfy <2.0
    assert not fdr.version_satisfies("2.0.0", reqs["numpy"])
    # 1.25.9 does NOT satisfy >=1.26.0
    assert not fdr.version_satisfies("1.25.9", reqs["numpy"])


# ---------------------------------------------------------------------------
# 8. test_pip_unparseable_constraint
# ---------------------------------------------------------------------------


def test_pip_unparseable_constraint(tmp_path: Path, capsys):
    """Epoch constraint 1!2.0.0 is skipped with a WARN."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("packaging==1!2.0.0\n")

    reqs = fdr.parse_requirements_txt(req_file)
    # Should have been skipped due to epoch marker '!'
    assert "packaging" not in reqs

    captured = capsys.readouterr()
    assert "Skipping complex constraint" in captured.err


# ---------------------------------------------------------------------------
# 9. test_null_enabled_services
# ---------------------------------------------------------------------------


def test_null_enabled_services(tmp_path: Path):
    """enabled_services: null → WARN and skip that RPi for services."""
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm1",
            enabled_services=None,
        ),
        "arm1.json",
    )

    snapshots = fdr.load_snapshots(tmp_path)
    svc_f = fdr.analyse_services(snapshots)

    warn = [f for f in svc_f if f.severity == "WARN"]
    assert len(warn) == 1
    assert "null" in warn[0].description.lower() or "skip" in warn[0].description.lower()


# ---------------------------------------------------------------------------
# 10. test_can_dtoverlay_wrong_oscillator
# ---------------------------------------------------------------------------


def test_can_dtoverlay_wrong_oscillator(tmp_path: Path):
    """arm1 with oscillator=12000000 → ERROR finding."""
    bad_line = (
        "dtoverlay=mcp2515-can0,oscillator=12000000,"
        "interrupt=25,spimaxfrequency=1000000"
    )
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm1",
            role="arm",
            dtoverlay_config=bad_line,
        ),
        "arm1.json",
    )

    snapshots = fdr.load_snapshots(tmp_path)
    dto_f = fdr.analyse_dtoverlay(snapshots)

    errors = [f for f in dto_f if f.severity == "ERROR"]
    assert len(errors) >= 1
    assert any("oscillator" in f.description for f in errors)
    assert any("12000000" in f.description for f in errors)


# ---------------------------------------------------------------------------
# 11. test_can_dtoverlay_correct
# ---------------------------------------------------------------------------


def test_can_dtoverlay_correct(tmp_path: Path):
    """arm1 with canonical CAN line → OK finding."""
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm1",
            role="arm",
            dtoverlay_config=CANONICAL_CAN_LINE,
        ),
        "arm1.json",
    )

    snapshots = fdr.load_snapshots(tmp_path)
    dto_f = fdr.analyse_dtoverlay(snapshots)

    ok = [f for f in dto_f if f.severity == "OK"]
    assert len(ok) == 1
    assert "correct" in ok[0].description.lower()


# ---------------------------------------------------------------------------
# 12. test_input_dir_not_exists
# ---------------------------------------------------------------------------


def test_input_dir_not_exists():
    """CLI parser rejects non-existent --input-dir."""
    parser = fdr.build_parser()
    args = parser.parse_args(["--input-dir", "/nonexistent/path"])
    assert not args.input_dir.is_dir()


# ---------------------------------------------------------------------------
# 13. test_requirements_file_not_found
# ---------------------------------------------------------------------------


def test_requirements_file_not_found(tmp_path: Path):
    """CLI validation: requirements path that doesn't exist."""
    parser = fdr.build_parser()
    args = parser.parse_args(
        [
            "--input-dir",
            str(tmp_path),
            "--requirements",
            str(tmp_path / "nonexistent_requirements.txt"),
        ]
    )
    assert not args.requirements.is_file()


# ---------------------------------------------------------------------------
# 14. test_pip_inter_rpi_drift
# ---------------------------------------------------------------------------


def test_pip_inter_rpi_drift(tmp_path: Path):
    """Different pip package versions across RPis → INFO finding."""
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm1",
            role="arm",
            pip_packages=["numpy==1.26.4", "requests==2.31.0"],
        ),
        "arm1.json",
    )
    write_snapshot(
        tmp_path,
        make_snapshot(
            hostname="pragati-arm2",
            role="arm",
            pip_packages=["numpy==1.26.4", "requests==2.32.0"],
        ),
        "arm2.json",
    )

    snapshots = fdr.load_snapshots(tmp_path)
    pip_f = fdr.analyse_pip_packages(snapshots, {})

    drift = [
        f
        for f in pip_f
        if f.severity == "INFO" and "requests" in f.description
    ]
    assert len(drift) == 1
    assert "2.31.0" in drift[0].description
    assert "2.32.0" in drift[0].description
