"""
Build provenance extraction and stale/dirty build detection.

Phase 2 of log-analyzer-enhancements:
  2.1 — Extract Built: banners from first 10 lines of each node's log output
  2.3 — Stale binary detection (build time >threshold from newest)
  2.4 — Dirty build detection (git hash ends with -dirty)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..models import BuildProvenance

# Regex for Built: banners in C++ node startup output.
# Matches both legacy and enhanced formats:
#   Built: Feb 19 2026 10:06:05
#   Built: Feb 19 2026 10:06:05 (abc1234 on main)
#   Built: Feb 19 2026 10:06:05 (abc1234-dirty on feature/x)
_RE_BUILT = re.compile(
    r"Built:\s+(\w+ \d{1,2} \d{4})\s+(\d{2}:\d{2}:\d{2})"
    r"(?:\s+\((\S+)\s+on\s+(\S+)\))?"
)

# Maximum number of lines to scan per node for Built: banner.
# Some nodes (e.g. yanthra_move) emit the Built: line after extensive
# init logging (~100+ lines), so we scan generously.
_MAX_SCAN_LINES = 200


def _parse_build_timestamp(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse 'Mon DD YYYY' + 'HH:MM:SS' into a datetime."""
    try:
        return datetime.strptime(
            f"{date_str} {time_str}", "%b %d %Y %H:%M:%S"
        )
    except ValueError:
        return None


def extract_build_provenance(
    entries: list,
    node_stats: dict,
) -> List["BuildProvenance"]:
    """Extract BuildProvenance from log entries.

    Scans the first _MAX_SCAN_LINES of each node's log output for
    Built: banners. Returns one BuildProvenance per node that has a
    matching banner.

    Args:
        entries: List of LogEntry objects (analyzer.entries).
        node_stats: Dict of node names (analyzer.node_stats).

    Returns:
        List of BuildProvenance dataclasses.
    """
    from ..models import BuildProvenance

    # Track how many lines we've seen per node
    node_line_counts: Dict[str, int] = {}
    # Track which nodes already have a BuildProvenance
    node_provenance: Dict[str, "BuildProvenance"] = {}

    for entry in entries:
        node = entry.node
        if node in node_provenance:
            continue  # already found for this node

        count = node_line_counts.get(node, 0)
        if count >= _MAX_SCAN_LINES:
            continue  # past the scan window

        node_line_counts[node] = count + 1

        m = _RE_BUILT.search(entry.message)
        if not m:
            # Also check raw_line in case message was truncated
            m = _RE_BUILT.search(entry.raw_line)
        if not m:
            continue

        date_str = m.group(1)
        time_str = m.group(2)
        git_hash = m.group(3)  # may be None
        git_branch = m.group(4)  # may be None

        build_ts = _parse_build_timestamp(date_str, time_str)
        if build_ts is None:
            continue

        # Check for dirty build
        is_dirty = False
        if git_hash and git_hash.endswith("-dirty"):
            is_dirty = True
            # Strip -dirty suffix for clean hash storage
            git_hash = git_hash[:-6]

        node_provenance[node] = BuildProvenance(
            node_name=node,
            build_timestamp=build_ts,
            git_hash=git_hash,
            git_branch=git_branch,
            is_dirty=is_dirty,
        )

    return list(node_provenance.values())


def detect_stale_builds(
    provenances: List["BuildProvenance"],
    stale_threshold_hours: float = 1.0,
) -> List[dict]:
    """Detect stale binaries by comparing build timestamps.

    Compares all node build timestamps. Any node with a build time
    more than stale_threshold_hours older than the newest build is
    flagged as stale.

    Args:
        provenances: List of BuildProvenance from extract_build_provenance.
        stale_threshold_hours: Hours threshold for staleness (default 1.0).

    Returns:
        List of issue dicts suitable for _add_issue().
    """
    if len(provenances) < 2:
        return []

    # Find the newest build timestamp
    newest_ts = max(p.build_timestamp for p in provenances)
    threshold_seconds = stale_threshold_hours * 3600.0

    issues = []
    for p in provenances:
        delta = (newest_ts - p.build_timestamp).total_seconds()
        if delta > threshold_seconds:
            hours_behind = delta / 3600.0
            issues.append({
                "severity": "medium",
                "category": "build",
                "title": "Stale Binary Detected",
                "description": (
                    f"Node '{p.node_name}' was built"
                    f" {hours_behind:.1f}h before the newest"
                    f" binary. Build time:"
                    f" {p.build_timestamp.strftime('%b %d %Y %H:%M:%S')},"
                    f" newest:"
                    f" {newest_ts.strftime('%b %d %Y %H:%M:%S')}."
                    f" Threshold: {stale_threshold_hours}h."
                ),
                "node": p.node_name,
                "timestamp": 0,
                "message": (
                    f"Stale binary: {p.node_name} built"
                    f" {hours_behind:.1f}h behind newest"
                ),
                "recommendation": (
                    "Rebuild all packages to ensure consistent"
                    " binaries across nodes."
                ),
            })

    return issues


def detect_dirty_builds(
    provenances: List["BuildProvenance"],
) -> List[dict]:
    """Detect dirty builds (uncommitted changes at build time).

    Args:
        provenances: List of BuildProvenance from extract_build_provenance.

    Returns:
        List of issue dicts suitable for _add_issue().
    """
    issues = []
    for p in provenances:
        if p.is_dirty:
            issues.append({
                "severity": "low",
                "category": "build",
                "title": "Dirty Build Detected",
                "description": (
                    f"Node '{p.node_name}' was built with"
                    f" uncommitted changes (git hash:"
                    f" {p.git_hash}-dirty"
                    f" on branch {p.git_branch or 'unknown'})."
                ),
                "node": p.node_name,
                "timestamp": 0,
                "message": (
                    f"Dirty build: {p.node_name} built with"
                    f" uncommitted changes"
                ),
                "recommendation": (
                    "Commit all changes before building for"
                    " field deployment to ensure reproducibility."
                ),
            })

    return issues


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "extract_build_provenance", extract_build_provenance,
    category="system",
    description="Extract build provenance banners from node startup output.",
)
_register(
    "detect_stale_builds", detect_stale_builds,
    category="system",
    description="Detect binaries built too far before the newest in the session.",
)
_register(
    "detect_dirty_builds", detect_dirty_builds,
    category="system",
    description="Detect binaries built from uncommitted (dirty) git state.",
)
