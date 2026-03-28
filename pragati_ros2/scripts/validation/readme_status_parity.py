#!/usr/bin/env python3
"""Ensure the top-level README status table stays in sync with the Status Reality Matrix."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
MATRIX = ROOT / "docs" / "STATUS_REALITY_MATRIX.md"


def extract_marked_name(cell: str) -> str:
    """Return the primary name highlighted in a Markdown table cell."""
    cell = cell.strip()
    match = re.search(r"\*\*(.+?)\*\*", cell)
    if match:
        return match.group(1).strip()
    return cell


def canonicalise(label: str) -> str:
    label = re.sub(r"\(.*?\)", "", label)
    label = label.replace("/", " ")
    label = re.sub(r"[^a-z0-9]+", " ", label.lower())
    return re.sub(r"\s+", " ", label).strip()


MATRIX_ALIASES = {
    "navigation vehicle control": "vehicle control",
    "vehicle control arm integration": "vehicle control",
    "motor control mg6010 primary": "motor control",
    "motor can bitrate": "motor control",
    "yanthra move manipulation": "yanthra move",
    "cotton detection primary implementation": "cotton detection",
    "pattern finder": "pattern finder",
    "pattern finder aruco utility": "pattern finder",
    "robot description urdf": "robot description",
}


def parse_readme_modules() -> set[str]:
    modules: set[str] = set()
    if not README.exists():
        raise FileNotFoundError(f"README not found at {README}")

    in_table = False
    for line in README.read_text().splitlines():
        if line.startswith("| Module"):
            in_table = True
            continue
        if in_table:
            if not line.strip():
                break
            if line.startswith("|-"):
                continue
            if line.count("|") < 3:
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if not cells:
                continue
            modules.add(canonicalise(extract_marked_name(cells[0])))
    return modules


def parse_matrix_capabilities() -> set[str]:
    capabilities: set[str] = set()
    if not MATRIX.exists():
        raise FileNotFoundError(f"Status matrix not found at {MATRIX}")

    in_table = False
    for line in MATRIX.read_text().splitlines():
        if line.startswith("| Capability / Claim"):
            in_table = True
            continue
        if in_table:
            if not line.strip():
                break
            if line.startswith("|-"):
                continue
            if line.count("|") < 5:
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if not cells:
                continue
            name = canonicalise(extract_marked_name(cells[0]))
            mapped = MATRIX_ALIASES.get(name)
            if mapped:
                capabilities.add(mapped)
    return capabilities


def main() -> int:
    readme_modules = parse_readme_modules()
    matrix_capabilities = parse_matrix_capabilities()

    missing_in_readme = sorted(matrix_capabilities - readme_modules)
    missing_in_matrix = sorted(readme_modules - matrix_capabilities)

    if missing_in_readme or missing_in_matrix:
        if missing_in_readme:
            print("[readme-status-parity] Modules missing from README table:")
            for name in missing_in_readme:
                print(f"  - {name.title()}")
        if missing_in_matrix:
            print("[readme-status-parity] Modules missing from Status Reality Matrix:")
            for name in missing_in_matrix:
                print(f"  - {name.title()}")
        print("[readme-status-parity] Update README.md and docs/STATUS_REALITY_MATRIX.md to cover the same modules.")
        return 1

    print("[readme-status-parity] README module table matches Status Reality Matrix entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
