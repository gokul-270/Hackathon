#!/usr/bin/env python3
"""Fleet Drift Report — compare boot-timing JSON snapshots across RPis.

Loads boot_timing_capture v5+ JSON files from a directory, compares OS versions,
apt/pip packages, dtoverlay config, and enabled services across all RPis in the
fleet. Produces a plain-text drift report with severity-tagged findings and
suggested fix commands.

Usage:
    fleet_drift_report.py --input-dir <dir> [--requirements <file>] \
                          [--output <file>] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Inline baseline constants
# ---------------------------------------------------------------------------

EXPECTED_OS_VERSION = "24.04"  # base; point release baseline from fleet newest

EXPECTED_APT_PACKAGES: list[str] = [
    "can-utils",
    "pigpiod",
    "mosquitto",
    "chrony",
    "python3-pip",
    "python3-venv",
    "i2c-tools",
    "net-tools",
    "htop",
    "tmux",
]

EXPECTED_SERVICES: dict[str, list[str]] = {
    "all": ["boot_timing.service", "boot_timing.timer"],
    "vehicle": ["mosquitto.service"],
    "arm": [],
}

CAN_HAT_HOSTS: set[str] = {"pragati-arm1"}  # RPis with CAN HAT (update when new arms join fleet)

CANONICAL_CAN_DTOVERLAY = (
    "dtoverlay=mcp2515-can0,oscillator=8000000,"
    "interrupt=25,spimaxfrequency=1000000"
)

MIN_SCHEMA_VERSION = "v5"

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2, "OK": 3}


class Finding:
    """A single drift finding attached to a hostname."""

    __slots__ = ("hostname", "severity", "description", "fix")

    def __init__(
        self,
        hostname: str,
        severity: str,
        description: str,
        fix: str | None = None,
    ) -> None:
        self.hostname = hostname
        self.severity = severity
        self.description = description
        self.fix = fix

    def format(self) -> str:
        tag = f"[{self.severity}]"
        line = f"  {tag} {self.hostname}: {self.description}"
        if self.fix:
            line += f"\n    Fix: {self.fix}"
        return line


class RpiSnapshot:
    """Parsed subset of a boot-timing JSON snapshot."""

    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self.path = path
        self.raw = data
        self.hostname: str = data.get("hostname", "unknown")
        self.role: str = data.get("role", "unknown")
        self.schema_version: str = data.get("schema_version", "")

        si = data.get("system_info") or {}
        self.os_version: str | None = si.get("os_version")
        self.kernel_version: str | None = si.get("kernel_version")
        self.dtoverlay_config: str | None = si.get("dtoverlay_config")

        env = data.get("environment") or {}
        self.apt_packages: list[str] | None = env.get("apt_packages")
        self.pip_packages: list[str] | None = env.get("pip_packages")
        self.enabled_services: list[str] | None = env.get(
            "enabled_services"
        )


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version_tuple(ver: str) -> tuple[int, ...]:
    """Turn '1.26.4' into (1, 26, 4). Returns () on failure."""
    m = _VERSION_RE.search(ver)
    if not m:
        return ()
    return tuple(int(x) for x in m.group(1).split("."))


def version_satisfies(
    installed: str,
    constraints: list[tuple[str, str]],
) -> bool:
    """Check *installed* version against parsed constraints."""
    iv = parse_version_tuple(installed)
    if not iv:
        return False
    for op, ver_str in constraints:
        cv = parse_version_tuple(ver_str)
        if not cv:
            continue
        if op == "==" and iv != cv:
            return False
        if op == ">=" and iv < cv:
            return False
        if op == "<=" and iv > cv:
            return False
        if op == ">" and iv <= cv:
            return False
        if op == "<" and iv >= cv:
            return False
        if op == "!=" and iv == cv:
            return False
    return True


_CONSTRAINT_RE = re.compile(
    r"(==|>=|<=|!=|<|>)\s*"
    r"(\d+(?:\.\d+)*(?:\.\d+)*(?:\.\d+)*)"
)

_SKIP_MARKERS = re.compile(r"(\d+!|\.dev\d|\.post\d|\+)")


def parse_requirements_txt(
    path: Path,
) -> dict[str, list[tuple[str, str]]]:
    """Parse requirements.txt → {normalised_name: [(op, ver), ...]}."""
    reqs: dict[str, list[tuple[str, str]]] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # strip inline comment
        if " #" in line:
            line = line[: line.index(" #")].strip()
        # skip options lines (-r, --extra-index-url, etc.)
        if line.startswith("-"):
            continue
        # split on first constraint operator
        split_idx = None
        for i, ch in enumerate(line):
            if ch in ("=", "<", ">", "!"):
                split_idx = i
                break
        if split_idx is None:
            # bare package name, no constraint
            pkg_name = _normalise_pkg(line)
            reqs[pkg_name] = []
            continue
        pkg_name = _normalise_pkg(line[:split_idx])
        constraint_str = line[split_idx:]
        if _SKIP_MARKERS.search(constraint_str):
            print(
                f"  [WARN] Skipping complex constraint: {raw_line.strip()}",
                file=sys.stderr,
            )
            continue
        pairs: list[tuple[str, str]] = _CONSTRAINT_RE.findall(
            constraint_str
        )
        reqs[pkg_name] = pairs
    return reqs


def _normalise_pkg(name: str) -> str:
    """PEP 503 normalisation: lowercase, underscores → hyphens."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


# ---------------------------------------------------------------------------
# JSON loader (task 1.2)
# ---------------------------------------------------------------------------


def load_snapshots(
    input_dir: Path, verbose: bool = False
) -> list[RpiSnapshot]:
    """Discover and load valid v5+ JSON snapshots from *input_dir*."""
    json_files = sorted(input_dir.rglob("*.json"))
    if not json_files:
        print(
            f"ERROR: No *.json files found in {input_dir}", file=sys.stderr
        )
        sys.exit(1)

    snapshots: list[RpiSnapshot] = []
    for jp in json_files:
        try:
            data = json.loads(jp.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"  [WARN] Skipping malformed JSON: {jp} ({exc})",
                file=sys.stderr,
            )
            continue

        sv = data.get("schema_version", "")
        if not sv or sv < MIN_SCHEMA_VERSION:
            if verbose:
                print(
                    f"  [INFO] Skipping {jp.name}: "
                    f"schema_version={sv!r} < {MIN_SCHEMA_VERSION}",
                    file=sys.stderr,
                )
            continue

        snap = RpiSnapshot(jp, data)
        if verbose:
            print(
                f"  Loaded {jp.name}: "
                f"hostname={snap.hostname}, role={snap.role}",
                file=sys.stderr,
            )
        snapshots.append(snap)

    if not snapshots:
        print(
            "ERROR: No valid v5+ snapshots found in input directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    return snapshots


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

_POINT_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def _extract_point_release(os_ver: str) -> str | None:
    """'Ubuntu 24.04.4 LTS' → '24.04.4'."""
    m = _POINT_RE.search(os_ver)
    return m.group(1) if m else None


def analyse_os_versions(
    snapshots: list[RpiSnapshot],
) -> list[Finding]:
    """Task 1.3 — OS version comparison."""
    findings: list[Finding] = []
    versions: dict[str, str] = {}  # hostname → point release

    for snap in snapshots:
        if not snap.os_version:
            findings.append(
                Finding(
                    snap.hostname,
                    "WARN",
                    "system_info.os_version missing",
                )
            )
            continue
        pr = _extract_point_release(snap.os_version)
        if not pr:
            findings.append(
                Finding(
                    snap.hostname,
                    "WARN",
                    f"Cannot parse OS version: {snap.os_version}",
                )
            )
            continue
        versions[snap.hostname] = pr

    if not versions:
        return findings

    # Determine baseline
    if len(versions) >= 2:
        newest = max(versions.values(), key=parse_version_tuple)
    else:
        newest = list(versions.values())[0]
        # For single RPi, compare against expected constant base
        if not newest.startswith(EXPECTED_OS_VERSION):
            findings.append(
                Finding(
                    list(versions.keys())[0],
                    "WARN",
                    f"OS version {newest} does not match "
                    f"expected base {EXPECTED_OS_VERSION}",
                    "sudo apt update && sudo apt full-upgrade",
                )
            )
            return findings

    for hostname, pr in sorted(versions.items()):
        snap_os = next(
            s.os_version
            for s in snapshots
            if s.hostname == hostname
        )
        if parse_version_tuple(pr) < parse_version_tuple(newest):
            findings.append(
                Finding(
                    hostname,
                    "WARN",
                    f"{snap_os} (behind fleet newest {newest})",
                    "sudo apt update && sudo apt full-upgrade",
                )
            )
        else:
            findings.append(
                Finding(hostname, "OK", f"{snap_os}")
            )

    return findings


def analyse_apt_packages(
    snapshots: list[RpiSnapshot],
    verbose: bool = False,
) -> list[Finding]:
    """Task 1.4 — apt package inter-RPi diff + baseline check."""
    findings: list[Finding] = []

    # Parse per-host package sets
    host_pkgs: dict[str, dict[str, str]] = {}  # host → {name: ver}
    for snap in snapshots:
        if snap.apt_packages is None:
            findings.append(
                Finding(
                    snap.hostname,
                    "WARN",
                    "environment.apt_packages missing",
                )
            )
            continue
        pkgs: dict[str, str] = {}
        for entry in snap.apt_packages:
            parts = entry.split("=", 1)
            name = parts[0]
            ver = parts[1] if len(parts) > 1 else "unknown"
            pkgs[name] = ver
        host_pkgs[snap.hostname] = pkgs

    # Baseline check — expected packages
    for hostname, pkgs in sorted(host_pkgs.items()):
        for expected in EXPECTED_APT_PACKAGES:
            if expected not in pkgs:
                findings.append(
                    Finding(
                        hostname,
                        "WARN",
                        f"Missing expected apt package: {expected}",
                        f"sudo apt install {expected}",
                    )
                )

    # Inter-RPi diff (only for 2+ hosts)
    if len(host_pkgs) < 2:
        return findings

    all_hosts = sorted(host_pkgs.keys())
    all_pkg_names: set[str] = set()
    for pkgs in host_pkgs.values():
        all_pkg_names.update(pkgs.keys())

    # Find packages not present on all hosts
    extra_by_host: dict[str, list[str]] = defaultdict(list)
    for pkg in sorted(all_pkg_names):
        present_on = [h for h in all_hosts if pkg in host_pkgs[h]]
        if len(present_on) != len(all_hosts):
            for h in present_on:
                if len(present_on) < len(all_hosts):
                    missing_on = [
                        x for x in all_hosts if x not in present_on
                    ]
                    extra_by_host[h].append(pkg)

    # Group extras by prefix pattern for concise reporting
    for hostname in all_hosts:
        extras = extra_by_host.get(hostname, [])
        if not extras:
            continue
        groups = _group_by_prefix(extras)
        for prefix, members in sorted(groups.items()):
            if len(members) > 3:
                findings.append(
                    Finding(
                        hostname,
                        "INFO",
                        f"Has {len(members)} extra pkgs matching "
                        f"'{prefix}*' not on all RPis",
                    )
                )
            elif verbose:
                for pkg in members:
                    findings.append(
                        Finding(
                            hostname,
                            "INFO",
                            f"Extra apt package not on all RPis: {pkg}",
                        )
                    )

    return findings


def _group_by_prefix(names: list[str]) -> dict[str, list[str]]:
    """Group package names by longest common dash-separated prefix."""
    groups: dict[str, list[str]] = defaultdict(list)
    for name in names:
        parts = name.split("-")
        # Use first two dash-separated tokens as group prefix
        if len(parts) >= 2:
            prefix = "-".join(parts[:2])
        else:
            prefix = parts[0]
        groups[prefix].append(name)
    return dict(groups)


def analyse_pip_packages(
    snapshots: list[RpiSnapshot],
    requirements: dict[str, list[tuple[str, str]]],
    verbose: bool = False,
) -> list[Finding]:
    """Task 1.5 — pip version validation against requirements.txt."""
    findings: list[Finding] = []

    host_pips: dict[str, dict[str, str]] = {}  # host → {norm_name: ver}
    for snap in snapshots:
        if snap.pip_packages is None:
            findings.append(
                Finding(
                    snap.hostname,
                    "WARN",
                    "environment.pip_packages missing",
                )
            )
            continue
        pkgs: dict[str, str] = {}
        for entry in snap.pip_packages:
            parts = entry.split("==", 1)
            name = _normalise_pkg(parts[0])
            ver = parts[1] if len(parts) > 1 else "unknown"
            pkgs[name] = ver
        host_pips[snap.hostname] = pkgs

    # Validate against requirements
    for hostname, pkgs in sorted(host_pips.items()):
        for req_name, constraints in requirements.items():
            installed_ver = pkgs.get(req_name)
            if installed_ver is None:
                findings.append(
                    Finding(
                        hostname,
                        "WARN",
                        f"Required pip package not installed: {req_name}",
                        f"pip3 install {req_name}",
                    )
                )
                continue
            if not constraints:
                continue  # bare requirement, no version constraint
            if not version_satisfies(installed_ver, constraints):
                constraint_str = ",".join(
                    f"{op}{v}" for op, v in constraints
                )
                findings.append(
                    Finding(
                        hostname,
                        "WARN",
                        f"pip {req_name}=={installed_ver} "
                        f"does not satisfy {constraint_str}",
                        f"pip3 install '{req_name}{constraint_str}'",
                    )
                )

    # Inter-RPi pip diff (2+ hosts)
    if len(host_pips) >= 2:
        all_hosts = sorted(host_pips.keys())
        all_names: set[str] = set()
        for pkgs in host_pips.values():
            all_names.update(pkgs.keys())

        for pkg in sorted(all_names):
            ver_map: dict[str, str] = {}
            for h in all_hosts:
                v = host_pips[h].get(pkg)
                if v is not None:
                    ver_map[h] = v
            if len(ver_map) < 2:
                continue
            unique_vers = set(ver_map.values())
            if len(unique_vers) > 1:
                detail = ", ".join(
                    f"{h}={v}" for h, v in sorted(ver_map.items())
                )
                findings.append(
                    Finding(
                        all_hosts[0],
                        "INFO",
                        f"pip {pkg} version differs: {detail}",
                    )
                )

    return findings


def analyse_dtoverlay(
    snapshots: list[RpiSnapshot],
) -> list[Finding]:
    """Task 1.6 — config.txt dtoverlay validation."""
    findings: list[Finding] = []

    # Parse canonical overlay params
    canonical_params = _parse_dtoverlay_params(CANONICAL_CAN_DTOVERLAY)

    for snap in snapshots:
        if snap.dtoverlay_config is None:
            findings.append(
                Finding(
                    snap.hostname,
                    "WARN",
                    "system_info.dtoverlay_config missing",
                )
            )
            continue

        # Find CAN overlay lines
        can_lines = [
            line.strip()
            for line in snap.dtoverlay_config.splitlines()
            if "dtoverlay=mcp2515-can0" in line
        ]
        has_can = len(can_lines) > 0

        # Determine expectation
        expects_can = (
            snap.role == "arm"
            and snap.hostname in CAN_HAT_HOSTS
        )
        is_vehicle = snap.role == "vehicle"

        if has_can and not expects_can:
            if is_vehicle:
                findings.append(
                    Finding(
                        snap.hostname,
                        "WARN",
                        "CAN dtoverlay present but role is vehicle",
                        "Remove mcp2515-can0 dtoverlay from "
                        "/boot/firmware/config.txt",
                    )
                )
            else:
                findings.append(
                    Finding(
                        snap.hostname,
                        "WARN",
                        "CAN dtoverlay present but host not in "
                        "CAN_HAT_HOSTS",
                        "Remove mcp2515-can0 dtoverlay from "
                        "/boot/firmware/config.txt "
                        "(or add host to CAN_HAT_HOSTS if HAT "
                        "is installed)",
                    )
                )
        elif not has_can and expects_can:
            findings.append(
                Finding(
                    snap.hostname,
                    "ERROR",
                    "CAN dtoverlay missing but expected "
                    "(host in CAN_HAT_HOSTS)",
                    f"Add to /boot/firmware/config.txt:\n"
                    f"    {CANONICAL_CAN_DTOVERLAY}",
                )
            )
        elif has_can and expects_can:
            # Validate parameters
            for can_line in can_lines:
                actual_params = _parse_dtoverlay_params(can_line)
                param_ok = True
                for key, expected_val in canonical_params.items():
                    if key == "dtoverlay":
                        continue  # skip the overlay name itself
                    actual_val = actual_params.get(key)
                    if actual_val is None:
                        findings.append(
                            Finding(
                                snap.hostname,
                                "ERROR",
                                f"CAN dtoverlay missing param "
                                f"{key}={expected_val}",
                                f"Update /boot/firmware/config.txt "
                                f"to: {CANONICAL_CAN_DTOVERLAY}",
                            )
                        )
                        param_ok = False
                    elif actual_val != expected_val:
                        findings.append(
                            Finding(
                                snap.hostname,
                                "ERROR",
                                f"CAN dtoverlay param {key}="
                                f"{actual_val} (expected "
                                f"{expected_val})",
                                f"Update /boot/firmware/config.txt "
                                f"to: {CANONICAL_CAN_DTOVERLAY}",
                            )
                        )
                        param_ok = False
                if param_ok:
                    findings.append(
                        Finding(
                            snap.hostname,
                            "OK",
                            "CAN dtoverlay present with correct "
                            "parameters",
                        )
                    )
        else:
            # No CAN, not expected — OK
            findings.append(
                Finding(
                    snap.hostname,
                    "OK",
                    "No CAN dtoverlay (not expected for this host)",
                )
            )

    return findings


def _parse_dtoverlay_params(line: str) -> dict[str, str]:
    """Parse 'dtoverlay=mcp2515-can0,k=v,k2=v2' → {k: v, ...}."""
    params: dict[str, str] = {}
    # Strip 'dtoverlay=' prefix
    stripped = line.strip()
    if stripped.startswith("dtoverlay="):
        stripped = stripped[len("dtoverlay="):]
    parts = stripped.split(",")
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.strip()] = v.strip()
        else:
            params["dtoverlay"] = part.strip()
    return params


def analyse_services(
    snapshots: list[RpiSnapshot],
) -> list[Finding]:
    """Task 1.7 — enabled services comparison."""
    findings: list[Finding] = []

    host_services: dict[str, set[str]] = {}
    for snap in snapshots:
        if snap.enabled_services is None:
            findings.append(
                Finding(
                    snap.hostname,
                    "WARN",
                    "enabled_services is null — skipping",
                )
            )
            continue
        svc_set = set(snap.enabled_services)
        host_services[snap.hostname] = svc_set

        # Role-based expected services
        expected = list(EXPECTED_SERVICES["all"])
        role_specific = EXPECTED_SERVICES.get(snap.role, [])
        expected.extend(role_specific)

        for svc in expected:
            if svc not in svc_set:
                findings.append(
                    Finding(
                        snap.hostname,
                        "WARN",
                        f"Expected service not enabled: {svc}",
                        f"sudo systemctl enable {svc}",
                    )
                )

    # Inter-RPi diff (2+ hosts with valid data)
    if len(host_services) < 2:
        return findings

    all_hosts = sorted(host_services.keys())
    all_svcs: set[str] = set()
    for svcs in host_services.values():
        all_svcs.update(svcs)

    for svc in sorted(all_svcs):
        present_on = [h for h in all_hosts if svc in host_services[h]]
        if 0 < len(present_on) < len(all_hosts):
            missing_on = [
                h for h in all_hosts if h not in present_on
            ]
            findings.append(
                Finding(
                    missing_on[0],
                    "INFO",
                    f"Service {svc} enabled on "
                    f"{', '.join(present_on)} but not here",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Report formatter (task 1.8)
# ---------------------------------------------------------------------------

_SEP = "=" * 80


def format_report(
    input_dir: Path,
    snapshots: list[RpiSnapshot],
    sections: dict[str, list[Finding]],
) -> str:
    """Render the full drift report as plain text."""
    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    hostnames = sorted({s.hostname for s in snapshots})

    lines.append(_SEP)
    lines.append("Fleet Drift Report")
    lines.append(f"Generated: {now}")
    lines.append(f"Input: {input_dir}")
    lines.append(
        f"RPis analyzed: {len(hostnames)} "
        f"({', '.join(hostnames)})"
    )
    lines.append(_SEP)

    # Tally
    totals: dict[str, int] = defaultdict(int)
    for findings in sections.values():
        for f in findings:
            if f.severity in ("ERROR", "WARN", "INFO"):
                totals[f.severity] += 1

    summary = (
        f"SUMMARY: {totals.get('ERROR', 0)} ERROR, "
        f"{totals.get('WARN', 0)} WARN, "
        f"{totals.get('INFO', 0)} INFO"
    )
    lines.append("")
    lines.append(summary)

    section_titles: dict[str, str] = {
        "os_version": "OS VERSION",
        "apt_packages": "APT PACKAGES",
        "pip_packages": "PIP PACKAGES",
        "dtoverlay": "DTOVERLAY CONFIG",
        "services": "ENABLED SERVICES",
    }

    for idx, (key, title) in enumerate(section_titles.items(), 1):
        lines.append("")
        lines.append(_SEP)
        lines.append(f"{idx}. {title}")
        lines.append(_SEP)

        findings = sections.get(key, [])
        if not findings:
            lines.append("  [OK] No issues detected.")
            continue

        # Sort findings: ERROR first, then WARN, INFO, OK
        findings_sorted = sorted(
            findings,
            key=lambda f: (
                SEVERITY_ORDER.get(f.severity, 99),
                f.hostname,
            ),
        )
        for f in findings_sorted:
            lines.append(f.format())

    lines.append("")
    lines.append(_SEP)
    lines.append("END OF REPORT")
    lines.append(_SEP)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI (task 1.1)
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a fleet drift report comparing boot-timing "
            "JSON snapshots across RPis."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --input-dir ./snapshots\n"
            "  %(prog)s --input-dir ./snapshots "
            "--requirements ./requirements.txt\n"
            "  %(prog)s --input-dir ./snapshots "
            "--output report.txt --verbose\n"
        ),
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        type=Path,
        help="Directory containing boot_timing JSON files "
        "(searched recursively for *.json)",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=None,
        help="Path to requirements.txt "
        "(default: repo root requirements.txt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="File path for report copy (tee: file AND stdout)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Show extra details in report",
    )
    return parser


def _find_repo_root() -> Path:
    """Walk up from this script to find the repo root (has .git/)."""
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        if (candidate / ".git").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    # Fallback: two levels up from scripts/diagnostics/
    return Path(__file__).resolve().parent.parent.parent


def main() -> None:
    """Entry point for fleet drift report generation."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate input-dir
    if not args.input_dir.is_dir():
        parser.error(
            f"--input-dir does not exist or is not a directory: "
            f"{args.input_dir}"
        )

    # Resolve requirements path
    req_path: Path
    if args.requirements is not None:
        req_path = args.requirements
    else:
        req_path = _find_repo_root() / "requirements.txt"

    if not req_path.is_file():
        parser.error(
            f"Requirements file not found: {req_path}"
        )

    # Load data
    if args.verbose:
        print("Loading snapshots...", file=sys.stderr)
    snapshots = load_snapshots(args.input_dir, verbose=args.verbose)

    if args.verbose:
        print("Parsing requirements.txt...", file=sys.stderr)
    requirements = parse_requirements_txt(req_path)

    # Run analyses
    sections: dict[str, list[Finding]] = {
        "os_version": analyse_os_versions(snapshots),
        "apt_packages": analyse_apt_packages(
            snapshots, verbose=args.verbose
        ),
        "pip_packages": analyse_pip_packages(
            snapshots, requirements, verbose=args.verbose
        ),
        "dtoverlay": analyse_dtoverlay(snapshots),
        "services": analyse_services(snapshots),
    }

    # Format report
    report = format_report(args.input_dir, snapshots, sections)

    # Output: always stdout
    print(report)

    # Tee to file if requested
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(
            f"Report written to: {args.output}",
            file=sys.stderr,
        )

    # Exit code: non-zero if any ERROR findings
    error_count = sum(
        1
        for findings in sections.values()
        for f in findings
        if f.severity == "ERROR"
    )
    if error_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
