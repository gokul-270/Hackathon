"""
Fingerprint-based issue deduplication.

Groups issues by (motor_id, error_type, timestamp within 5s window) and
merges duplicates — retaining the earliest timestamp, highest severity,
and combined evidence from all matchers.

A second pass groups issues whose messages differ only by numeric values
(e.g. "4.1%" vs "9.8%") and collapses large groups into a single
representative issue showing the value range.
"""

from __future__ import annotations

import re
from collections import defaultdict as _defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..analyzer import Issue

# Severity ordering: lower = more severe
_SEVERITY_RANK: Dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

# Regex to extract a motor/joint identifier from issue titles or descriptions
_RE_MOTOR_ID = re.compile(
    r"(?:motor|joint|Motor|Joint)\s*(\d+)", re.IGNORECASE
)

# Timestamp window for considering issues as the same root cause (seconds)
_DEDUP_WINDOW_S = 5.0

# Regex matching integers, floats, and percentage values (e.g. "4.1%", "57", "3.14")
_RE_NUMERIC = re.compile(r"\d+\.?\d*%?")

# Minimum group size before numeric-similarity collapsing kicks in
_NUMERIC_GROUP_MIN = 4


def _normalize_numerics(text: str) -> str:
    """Replace all numeric tokens in *text* with ``<NUM>``."""
    return _RE_NUMERIC.sub("<NUM>", text)


def _extract_numerics(text: str) -> List[str]:
    """Return all numeric tokens found in *text*."""
    return _RE_NUMERIC.findall(text)


def _numeric_sort_key(token: str) -> float:
    """Parse a numeric token (possibly ending with '%') to a float for sorting."""
    try:
        return float(token.rstrip("%"))
    except ValueError:
        return 0.0


def _extract_motor_id(issue: "Issue") -> Optional[str]:
    """Extract motor/joint id from issue title or description."""
    for text in (issue.title, issue.description):
        m = _RE_MOTOR_ID.search(text)
        if m:
            return m.group(1)
    return None


def _parse_timestamp_str(ts_str: Optional[str]) -> Optional[float]:
    """Parse HH:MM:SS.mmm timestamp string to seconds-of-day float.

    Returns None if the string cannot be parsed.
    """
    if not ts_str or ts_str == "N/A":
        return None
    try:
        # Handle HH:MM:SS.mmm format
        parts = ts_str.split(":")
        if len(parts) == 3:
            h, m = int(parts[0]), int(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
    except (ValueError, IndexError):
        pass
    return None


def _error_type_key(issue: "Issue") -> str:
    """Derive an error type key from issue category and title."""
    # Normalize: lowercase, strip whitespace
    return f"{issue.category.lower().strip()}:{issue.title.lower().strip()}"


def deduplicate_issues(
    issues: Dict[str, "Issue"],
) -> Dict[str, "Issue"]:
    """Deduplicate issues by fingerprint.

    Fingerprint = (motor_id, error_type, timestamp within 5s window).
    Issues without a motor_id are not merged.

    Returns a new dict of deduplicated issues.
    """
    # Build fingerprint groups
    # Key: (motor_id, error_type_key, time_bucket)
    # Value: list of (original_key, issue) pairs
    fingerprint_groups: Dict[tuple, List[tuple]] = {}
    non_motor_issues: Dict[str, "Issue"] = {}

    for key, issue in issues.items():
        motor_id = _extract_motor_id(issue)
        if motor_id is None:
            non_motor_issues[key] = issue
            continue

        error_type = _error_type_key(issue)
        ts = _parse_timestamp_str(issue.first_seen)

        # Group by motor_id + error_type; we'll merge within time
        # windows in a second pass
        group_key = (motor_id, error_type)
        if group_key not in fingerprint_groups:
            fingerprint_groups[group_key] = []
        fingerprint_groups[group_key].append((key, issue, ts))

    # Merge within time windows
    result: Dict[str, "Issue"] = dict(non_motor_issues)

    for (_motor_id, _error_type), entries in fingerprint_groups.items():
        # Sort by timestamp (None timestamps go to end)
        entries.sort(key=lambda x: x[2] if x[2] is not None else float("inf"))

        # Greedy merge: start a new cluster when timestamp gap > window
        clusters: List[List[tuple]] = []
        current_cluster: List[tuple] = []
        cluster_start_ts: Optional[float] = None

        for key, issue, ts in entries:
            if not current_cluster:
                current_cluster = [(key, issue, ts)]
                cluster_start_ts = ts
            elif (
                ts is not None
                and cluster_start_ts is not None
                and ts - cluster_start_ts <= _DEDUP_WINDOW_S
            ):
                current_cluster.append((key, issue, ts))
            else:
                clusters.append(current_cluster)
                current_cluster = [(key, issue, ts)]
                cluster_start_ts = ts

        if current_cluster:
            clusters.append(current_cluster)

        # Merge each cluster into a single issue
        for cluster in clusters:
            if len(cluster) == 1:
                key, issue, _ = cluster[0]
                result[key] = issue
                continue

            # Merge: pick best severity, earliest first_seen, latest
            # last_seen, combine nodes and messages
            merged_key = cluster[0][0]
            base = cluster[0][1]

            best_severity = base.severity
            best_rank = _SEVERITY_RANK.get(best_severity, 5)
            total_occurrences = base.occurrences
            all_nodes = list(base.affected_nodes)
            all_messages = list(base.sample_messages)
            earliest_first = base.first_seen
            latest_last = base.last_seen
            earliest_ts = _parse_timestamp_str(earliest_first)
            latest_ts = _parse_timestamp_str(latest_last)

            for _, issue, _ in cluster[1:]:
                # Severity: keep most severe
                rank = _SEVERITY_RANK.get(issue.severity, 5)
                if rank < best_rank:
                    best_severity = issue.severity
                    best_rank = rank

                # Occurrences
                total_occurrences += issue.occurrences

                # Nodes
                for n in issue.affected_nodes:
                    if n not in all_nodes:
                        all_nodes.append(n)

                # Sample messages (cap at 5)
                for msg in issue.sample_messages:
                    if len(all_messages) < 5 and msg not in all_messages:
                        all_messages.append(msg)

                # Timestamps: earliest first_seen, latest last_seen
                issue_first = _parse_timestamp_str(issue.first_seen)
                if (
                    issue_first is not None
                    and (earliest_ts is None or issue_first < earliest_ts)
                ):
                    earliest_ts = issue_first
                    earliest_first = issue.first_seen

                issue_last = _parse_timestamp_str(issue.last_seen)
                if (
                    issue_last is not None
                    and (latest_ts is None or issue_last > latest_ts)
                ):
                    latest_ts = issue_last
                    latest_last = issue.last_seen

            # Build merged issue (reuse base, update fields)
            base.severity = best_severity
            base.occurrences = total_occurrences
            base.affected_nodes = all_nodes
            base.sample_messages = all_messages
            base.first_seen = earliest_first
            base.last_seen = latest_last
            result[merged_key] = base

    # ------------------------------------------------------------------
    # Pass 2: Numeric-similarity grouping
    #
    # Group issues whose category + message normalised (numbers → <NUM>)
    # are identical.  For groups with > _NUMERIC_GROUP_MIN members,
    # collapse into a single representative issue showing the value range.
    # ------------------------------------------------------------------
    result = _collapse_numeric_groups(result)

    return result


def _collapse_numeric_groups(
    issues: Dict[str, "Issue"],
) -> Dict[str, "Issue"]:
    """Collapse issues that differ only in numeric values.

    Groups by (category, normalised description).  For groups larger than
    ``_NUMERIC_GROUP_MIN``, merges into a single representative issue that
    shows the range of numeric values and the count of collapsed issues.
    The representative retains the highest severity and earliest timestamp
    from the group.
    """
    # Build groups keyed by (category, normalised description)
    groups: Dict[Tuple[str, str], List[Tuple[str, "Issue"]]] = _defaultdict(
        list
    )
    for key, issue in issues.items():
        norm = _normalize_numerics(issue.description)
        gkey = (issue.category.lower().strip(), norm)
        groups[gkey].append((key, issue))

    collapsed: Dict[str, "Issue"] = {}
    for _gkey, members in groups.items():
        if len(members) <= _NUMERIC_GROUP_MIN - 1:
            # Group too small — keep issues unchanged
            for key, issue in members:
                collapsed[key] = issue
            continue

        # --- Collapse the group ---
        # Sort by earliest timestamp so the representative uses the
        # chronologically first issue as base.
        members.sort(
            key=lambda m: (
                _parse_timestamp_str(m[1].first_seen)
                if _parse_timestamp_str(m[1].first_seen) is not None
                else float("inf")
            )
        )

        rep_key, rep_issue = members[0]

        # Collect all numeric tokens across descriptions to derive a range
        all_nums: List[str] = []
        for _, issue in members:
            all_nums.extend(_extract_numerics(issue.description))

        # Build range string (e.g. "4.1%-9.8% across 57 frames")
        range_str = ""
        if all_nums:
            sorted_nums = sorted(set(all_nums), key=_numeric_sort_key)
            lo, hi = sorted_nums[0], sorted_nums[-1]
            range_str = f" ({lo}-{hi} across {len(members)} frames)"

        # Determine highest severity across group
        best_severity = rep_issue.severity
        best_rank = _SEVERITY_RANK.get(best_severity, 5)

        # Earliest first_seen, latest last_seen
        earliest_first = rep_issue.first_seen
        earliest_ts = _parse_timestamp_str(earliest_first)
        latest_last = rep_issue.last_seen
        latest_ts = _parse_timestamp_str(latest_last)

        total_occurrences = 0
        all_nodes: List[str] = []
        all_messages: List[str] = []

        for _, issue in members:
            # Severity
            rank = _SEVERITY_RANK.get(issue.severity, 5)
            if rank < best_rank:
                best_severity = issue.severity
                best_rank = rank

            total_occurrences += issue.occurrences

            # Nodes
            for n in issue.affected_nodes:
                if n not in all_nodes:
                    all_nodes.append(n)

            # Sample messages (cap at 5)
            for msg in issue.sample_messages:
                if len(all_messages) < 5 and msg not in all_messages:
                    all_messages.append(msg)

            # Timestamps
            issue_first = _parse_timestamp_str(issue.first_seen)
            if issue_first is not None and (
                earliest_ts is None or issue_first < earliest_ts
            ):
                earliest_ts = issue_first
                earliest_first = issue.first_seen

            issue_last = _parse_timestamp_str(issue.last_seen)
            if issue_last is not None and (
                latest_ts is None or issue_last > latest_ts
            ):
                latest_ts = issue_last
                latest_last = issue.last_seen

        # Update representative issue
        rep_issue.severity = best_severity
        rep_issue.occurrences = total_occurrences
        rep_issue.affected_nodes = all_nodes
        rep_issue.sample_messages = all_messages
        rep_issue.first_seen = earliest_first
        rep_issue.last_seen = latest_last
        rep_issue.description = (
            rep_issue.description
            + range_str
            + f" [{len(members)} issues collapsed]"
        )
        collapsed[rep_key] = rep_issue

    return collapsed


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "deduplicate_issues", deduplicate_issues,
    category="dedup",
    description="Fingerprint-based deduplication of issues (runs last).",
    order=999,
)
