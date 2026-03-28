"""Detection quality detectors (stale detection, scan dead zones, border skip)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import EventStore


# ---------------------------------------------------------------------------
# task 15.1 — Stale detection rate detector
# ---------------------------------------------------------------------------

_STALE_DETECTION_AGE_MS = 2000


def detect_stale_detection_rate(events: "EventStore") -> list:
    """task 15.1 — Critical/High issue for picks with stale detection data."""

    # Group picks by arm_id
    arm_picks: dict = {}
    for p in events.picks:
        age = p.get("detection_age_ms")
        if age is None or age <= 0:
            continue
        aid = p.get("arm_id")
        key = aid if aid is not None else "__single__"
        arm_picks.setdefault(key, []).append(p)

    issues = []
    for arm_key, picks in arm_picks.items():
        valid = len(picks)
        if valid < 5:
            continue
        stale = sum(
            1 for p in picks if (p.get("detection_age_ms") or 0) > _STALE_DETECTION_AGE_MS
        )
        rate = stale / valid
        arm_label = f"arm_id={arm_key}" if arm_key != "__single__" else "arm"
        if rate > 0.8:
            severity = "critical"
        elif rate > 0.5:
            severity = "high"
        else:
            continue
        issues.append(
            {
                "severity": severity,
                "category": "detection",
                "title": (
                    f"{stale}/{valid} picks ({rate * 100:.0f}%) used stale detection "
                    f"data ({arm_label})"
                ),
                "description": (
                    f"{stale}/{valid} picks ({rate * 100:.0f}%) used stale detection data "
                    f"(age > {_STALE_DETECTION_AGE_MS}ms) — arm may be picking at outdated"
                    f" positions"
                ),
                "node": "cotton_detection",
                "timestamp": picks[0].get("_ts") or 0,
                "message": (
                    f"{stale}/{valid} picks used stale detection data "
                    f"(age > {_STALE_DETECTION_AGE_MS}ms)"
                ),
                "recommendation": (
                    "Verify detection pipeline latency; check OAK-D frame rate and "
                    "processing throughput"
                ),
                "arm_id": arm_key if arm_key != "__single__" else None,
            }
        )
    return issues


# ---------------------------------------------------------------------------
# task 18.3 — Scan dead zone detector
# ---------------------------------------------------------------------------


def detect_scan_dead_zones(events: "EventStore") -> list:
    """task 18.3 — Low issue for J4 positions with 0 cotton found while others > 0."""

    results = events.scan_position_results
    if not results:
        return []

    # Aggregate cotton_found per j4_offset_m (round to 3 dp to group)
    offset_cotton: dict = {}
    offset_count: dict = {}
    for r in results:
        key = round(r.get("j4_offset_m", 0.0), 3)
        found = r.get("cotton_found", 0)
        offset_cotton[key] = offset_cotton.get(key, 0) + found
        offset_count[key] = offset_count.get(key, 0) + 1

    if not offset_cotton:
        return []

    total_offsets = len(offset_cotton)
    if total_offsets < 2:
        return []  # nothing to compare

    # Offsets with any cotton
    has_cotton = {k: v for k, v in offset_cotton.items() if v > 0}
    if not has_cotton:
        return []  # no positions found cotton — not a dead-zone issue

    other_avg = sum(has_cotton.values()) / len(has_cotton)
    issues = []

    for offset, total_found in offset_cotton.items():
        if total_found == 0:
            n_scans = offset_count.get(offset, 1)
            issues.append(
                {
                    "severity": "low",
                    "category": "configuration",
                    "title": f"Scan dead zone at J4={offset}m",
                    "description": (
                        f"J4 offset {offset}m found 0 cotton across {n_scans} scan(s) "
                        f"while other positions averaged {other_avg:.1f} — "
                        f"consider removing this position to save cycle time"
                    ),
                    "node": "arm_control",
                    "timestamp": 0,
                    "message": (
                        f"J4 offset {offset}m found 0 cotton across {n_scans} scan(s)"
                    ),
                    "recommendation": (
                        "Remove this J4 position from the scan profile to reduce cycle time"
                    ),
                    "arm_id": None,
                }
            )
    return issues


# ---------------------------------------------------------------------------
# task 21.4 — Border skip rate detector
# ---------------------------------------------------------------------------


def detect_border_skip_rate(events: "EventStore") -> list:
    """task 21.4 — Medium issue when border skip rate > 30% and raw_total >= 10."""

    quality_events = events.detection_quality_events
    if not quality_events:
        return []

    raw_total = sum(e.get("raw", 0) for e in quality_events)
    border_total = max(
        (e.get("border_skip_total", 0) for e in quality_events), default=0
    )

    if raw_total < 10:
        return []

    rate = border_total / raw_total
    if rate > 0.30:
        pct = round(rate * 100, 1)
        return [
            {
                "severity": "medium",
                "category": "configuration",
                "title": f"{pct}% of raw detections were border-skipped",
                "description": (
                    f"{pct}% of raw detections were border-skipped — camera FOV may include "
                    f"too much non-pickable area, consider adjusting border filter"
                ),
                "node": "cotton_detection",
                "timestamp": quality_events[0].get("_ts") or 0,
                "message": (
                    f"border_skip_rate={pct}% ({border_total}/{raw_total} raw detections)"
                ),
                "recommendation": (
                    "Adjust border filter margins in detection configuration"
                ),
                "arm_id": None,
            }
        ]
    return []


# ---------------------------------------------------------------------------
# task 6.1 — Workspace rejection rate detector
# ---------------------------------------------------------------------------


def detect_workspace_reject_rate(events: "EventStore") -> list:
    """task 6.1 — Medium issue when workspace reject rate > 30% and raw >= 10."""

    quality_events = events.detection_quality_events
    if not quality_events:
        return []

    raw_total = sum(e.get("raw", 0) for e in quality_events)
    ws_total = max(
        (e.get("workspace_reject_total", 0) for e in quality_events),
        default=0,
    )

    if raw_total < 10:
        return []

    rate = ws_total / raw_total
    if rate > 0.30:
        pct = round(rate * 100, 1)
        return [
            {
                "severity": "medium",
                "category": "configuration",
                "title": (
                    f"{pct}% of raw detections were"
                    f" workspace-rejected"
                ),
                "description": (
                    f"{pct}% of raw detections were rejected by"
                    f" workspace filter — arm workspace bounds may"
                    f" be too restrictive or camera FOV includes"
                    f" unreachable areas"
                ),
                "node": "cotton_detection",
                "timestamp": (
                    quality_events[0].get("_ts") or 0
                ),
                "message": (
                    f"workspace_reject_rate={pct}%"
                    f" ({ws_total}/{raw_total} raw detections)"
                ),
                "recommendation": (
                    "Review workspace boundary configuration and"
                    " camera mounting angle"
                ),
                "arm_id": None,
            }
        ]
    return []


# ---------------------------------------------------------------------------
# task 7.9 — High frame drop rate detector
# ---------------------------------------------------------------------------


def detect_high_frame_drop_rate(events: "EventStore") -> list:
    """task 7.9 — Medium issue when avg frame drop rate > 5%."""

    summaries = events.detection_summaries
    if not summaries:
        return []

    vals = [
        float(s.get("frames_drop_rate_pct"))
        for s in summaries
        if s.get("frames_drop_rate_pct") is not None
    ]
    if not vals:
        return []

    avg_rate = sum(vals) / len(vals)
    if avg_rate <= 5.0:
        return []

    return [
        {
            "severity": "medium",
            "category": "camera",
            "title": (
                f"High frame drop rate: {avg_rate:.1f}% average"
            ),
            "description": (
                f"Average frame drop rate across {len(vals)}"
                f" summary periods is {avg_rate:.1f}%"
                f" (threshold 5%) — detection pipeline may"
                f" be overloaded"
            ),
            "node": "cotton_detection",
            "timestamp": summaries[0].get("_ts") or 0,
            "message": (
                f"avg_frame_drop_rate={avg_rate:.1f}%"
                f" across {len(vals)} periods"
            ),
            "recommendation": (
                "Check OAK-D USB bandwidth and host CPU"
                " load; consider reducing frame rate or"
                " detection resolution"
            ),
            "arm_id": None,
        }
    ]


# ---------------------------------------------------------------------------
# task 7.9 — High detection age detector
# ---------------------------------------------------------------------------


def detect_high_detection_age(events: "EventStore") -> list:
    """task 7.9 — Medium issue when avg detection_age_ms > 200ms."""

    s = events.detection_frames_summary
    count = s.get("detection_age_count", 0)
    if count == 0:
        return []

    avg_age = s["total_detection_age_ms"] / count
    if avg_age <= 200.0:
        return []

    return [
        {
            "severity": "medium",
            "category": "camera",
            "title": (
                f"High detection age: {avg_age:.0f}ms average"
            ),
            "description": (
                f"Average detection age across {count} frames"
                f" is {avg_age:.0f}ms (threshold 200ms) —"
                f" detections may be stale by the time the"
                f" arm acts"
            ),
            "node": "cotton_detection",
            "timestamp": 0,
            "message": (
                f"avg_detection_age={avg_age:.0f}ms"
                f" across {count} frames"
            ),
            "recommendation": (
                "Check detection pipeline latency; verify"
                " OAK-D NN inference time and host-side"
                " post-processing"
            ),
            "arm_id": None,
        }
    ]


# ---------------------------------------------------------------------------
# task 7.9 — Low cache hit rate detector
# ---------------------------------------------------------------------------


def detect_low_cache_hit_rate(events: "EventStore") -> list:
    """task 7.9 — Low issue when cache hit rate < 50%."""

    summaries = events.detection_summaries
    if not summaries:
        return []

    total_hits = sum(
        s.get("cache_hits", 0) or 0 for s in summaries
    )
    total_misses = sum(
        s.get("cache_misses", 0) or 0 for s in summaries
    )
    total = total_hits + total_misses
    if total == 0:
        return []

    hit_rate = 100.0 * total_hits / total
    if hit_rate >= 50.0:
        return []

    return [
        {
            "severity": "low",
            "category": "camera",
            "title": (
                f"Low detection cache hit rate:"
                f" {hit_rate:.1f}%"
            ),
            "description": (
                f"Detection cache hit rate is {hit_rate:.1f}%"
                f" ({total_hits}/{total}) — most requests"
                f" trigger fresh inference, increasing"
                f" latency"
            ),
            "node": "cotton_detection",
            "timestamp": summaries[0].get("_ts") or 0,
            "message": (
                f"cache_hit_rate={hit_rate:.1f}%"
                f" ({total_hits}/{total})"
            ),
            "recommendation": (
                "Review detection request frequency and"
                " cache TTL configuration"
            ),
            "arm_id": None,
        }
    ]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "detect_stale_detection_rate", detect_stale_detection_rate,
    category="camera",
    description="Flag picks using stale (>2s old) detection data.",
)
_register(
    "detect_scan_dead_zones", detect_scan_dead_zones,
    category="camera",
    description="Identify spatial regions with zero cotton detections.",
)
_register(
    "detect_border_skip_rate", detect_border_skip_rate,
    category="camera",
    description="Check if border-filter is rejecting too many raw detections.",
)
_register(
    "detect_workspace_reject_rate", detect_workspace_reject_rate,
    category="camera",
    description="Check if workspace filter is rejecting too many raw detections.",
)
_register(
    "detect_high_frame_drop_rate", detect_high_frame_drop_rate,
    category="camera",
    description="Flag high frame drop rates in detection pipeline.",
)
_register(
    "detect_high_detection_age", detect_high_detection_age,
    category="camera",
    description="Flag high average detection age across frames.",
)
_register(
    "detect_low_cache_hit_rate", detect_low_cache_hit_rate,
    category="camera",
    description="Flag low detection cache hit rates.",
)
