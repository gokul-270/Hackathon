#!/usr/bin/env python3
"""Generate a lightweight documentation inventory report.

Usage examples:

    python3 scripts/doc_inventory.py docs --table
    python3 scripts/doc_inventory.py docs --snapshot docs/doc_inventory_snapshot.json
    python3 scripts/doc_inventory.py docs --verify docs/doc_inventory_snapshot.json

The script walks each provided directory, aggregates file counts and sizes by
extension, and emits either JSON (default) or a simple human-friendly table.
When --snapshot is supplied the JSON payload is written to the given file; when
--verify is supplied the generated payload is compared against the snapshot and
an error is raised if they differ.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple


@dataclass
class ExtensionStats:
    count: int = 0
    bytes: int = 0

    def update(self, size: int) -> None:
        self.count += 1
        self.bytes += size


@dataclass
class DirectoryStats:
    label: str
    total_files: int
    total_bytes: int
    extensions: Dict[str, ExtensionStats]

    def to_serialisable(self) -> Dict[str, object]:
        return {
            "path": self.label,
            "total_files": self.total_files,
            "total_bytes": self.total_bytes,
            "extensions": {
                ext: asdict(stats) for ext, stats in sorted(self.extensions.items())
            },
        }


def _human_size(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.1f}{unit}" if unit != "B" else f"{num_bytes}B"
        num_bytes /= 1024
    return f"{num_bytes}B"


def collect_directory_stats(
    root: Path,
    label: str,
    include_hidden: bool = False,
    exclude: Sequence[Path] | None = None,
) -> DirectoryStats:
    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {root}")

    root = root.resolve()
    exclude_set: Set[Path] = {p.resolve() for p in (exclude or [])}

    ext_stats: Dict[str, ExtensionStats] = {}
    total_files = 0
    total_bytes = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in exclude_set:
            continue
        if not include_hidden and any(part.startswith(".") for part in path.relative_to(root).parts):
            continue

        ext = resolved.suffix.lower() or "<no_ext>"
        stats = ext_stats.setdefault(ext, ExtensionStats())
        try:
            size = resolved.stat().st_size
        except OSError:
            size = 0
        stats.update(size)
        total_files += 1
        total_bytes += size

    return DirectoryStats(
        label=label,
        total_files=total_files,
        total_bytes=total_bytes,
        extensions=ext_stats,
    )


def render_table(stats: Iterable[DirectoryStats]) -> str:
    lines: List[str] = []
    for directory in stats:
        lines.append(f"Directory: {directory.label}")
        lines.append(f"  Total files: {directory.total_files}")
        lines.append(f"  Total size:  {_human_size(directory.total_bytes)}")
        lines.append("  By extension:")
        if not directory.extensions:
            lines.append("    <no files>")
        else:
            for ext, ext_stats in sorted(directory.extensions.items(), key=lambda item: item[0]):
                lines.append(
                    f"    {ext:>10} — {ext_stats.count:5d} files, {_human_size(ext_stats.bytes):>8}"
                )
        lines.append("")
    return "\n".join(lines).rstrip()


def generate_report(
    directories: Iterable[Path],
    include_hidden: bool = False,
    exclude: Sequence[Path] | None = None,
) -> Tuple[Dict[str, object], List[DirectoryStats]]:
    dir_stats = [
        collect_directory_stats(path.resolve(), label=str(path), include_hidden=include_hidden, exclude=exclude)
        for path in directories
    ]
    payload = {
        "generated_at": _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "include_hidden": include_hidden,
        "roots": [stats.to_serialisable() for stats in dir_stats],
    }
    return payload, dir_stats


def compare_snapshots(new: Dict[str, object], reference: Dict[str, object]) -> List[str]:
    problems: List[str] = []
    if reference.get("include_hidden") != new.get("include_hidden"):
        problems.append("include_hidden flag differs between snapshot and current run")

    ref_roots = reference.get("roots", [])
    new_roots = new.get("roots", [])
    if len(ref_roots) != len(new_roots):
        problems.append("number of tracked directories has changed")
    else:
        for ref, cur in zip(ref_roots, new_roots):
            if ref.get("path") != cur.get("path"):
                problems.append(f"directory order/path mismatch: {ref.get('path')} vs {cur.get('path')}")
                continue
            if ref != cur:
                problems.append(f"inventory drift detected for {ref['path']}")
    return problems


def load_snapshot(path: Path) -> Dict[str, object]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(f"Snapshot file not found: {path}")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate documentation inventory data")
    parser.add_argument("directories", nargs="+", type=Path, help="Directories to scan")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden files and directories")
    parser.add_argument("--table", action="store_true", help="Render a human-friendly table")
    parser.add_argument("--snapshot", type=Path, help="Write JSON payload to the provided path")
    parser.add_argument("--verify", type=Path, help="Compare against an existing snapshot and fail on drift")
    parser.add_argument(
        "--exclude",
        action="append",
        type=Path,
        default=[],
        help="Paths to exclude from the inventory (can be provided multiple times)",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    exclude_paths: List[Path] = list(args.exclude)
    if args.snapshot:
        exclude_paths.append(args.snapshot)
    if args.verify:
        exclude_paths.append(args.verify)

    payload, stats = generate_report(
        args.directories,
        include_hidden=args.include_hidden,
        exclude=exclude_paths,
    )

    if args.snapshot:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps(payload, indent=2) + "\n")

    if args.verify:
        reference = load_snapshot(args.verify)
        problems = compare_snapshots(payload, reference)
        if problems:
            for problem in problems:
                print(f"[doc-inventory] {problem}", file=sys.stderr)
            return 1

    if args.table:
        print(render_table(stats))
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
