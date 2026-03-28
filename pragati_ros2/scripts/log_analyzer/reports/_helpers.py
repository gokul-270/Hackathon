"""
Shared constants and helper functions for field summary reports.

Split from the monolithic reports.py — this module holds all helpers
that sections, trends, and printing submodules depend on.
"""

from __future__ import annotations

import math  # noqa: F401 — kept for downstream compatibility
from collections import defaultdict  # noqa: F401
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple  # noqa: F401

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer
    from ..models import FieldSummary

# ---------------------------------------------------------------------------
# Group 20 — Constants / helpers
# ---------------------------------------------------------------------------

# task 20.2 — MG6010 CAN error flag bit meanings
MG6010_ERROR_FLAGS: Dict[int, str] = {
    0: "overcurrent",
    1: "overvoltage",
    2: "undervoltage",
    3: "overtemperature",
    4: "magnetic encoder error",
    5: "CAN timeout",
    6: "motor stall",
    7: "hall sensor error",
}


def decode_error_flags(err_flags: int) -> str:
    """Return a human-readable description of MG6010 CAN error flags."""
    if err_flags == 0:
        return "none"
    parts = []
    for bit, name in MG6010_ERROR_FLAGS.items():
        if err_flags & (1 << bit):
            parts.append(name)
    # Report unknown bits as hex
    known_mask = sum(1 << b for b in MG6010_ERROR_FLAGS)
    unknown = err_flags & ~known_mask
    if unknown:
        parts.append(f"unknown=0x{unknown:02x}")
    return ", ".join(parts) if parts else f"0x{err_flags:02x}"


def _safe_pct(num: float, denom: float) -> float:
    return round(100.0 * num / denom, 1) if denom else 0.0


def _group_by_arm(records: list) -> dict:
    """task 3.1 — Group records by arm_id field; returns {arm_id: [events]}."""
    groups: dict = {}
    for r in records:
        aid = r.get("arm_id")
        groups.setdefault(aid, []).append(r)
    return groups


def _is_multi_arm(groups: dict) -> bool:
    """task 3.2 — True when 2+ distinct arm_id keys exist (regardless of None keys)."""
    return len(groups) >= 2


def _stats(values: List[float]) -> Dict[str, float]:
    """Return basic statistics dict for a list of floats.

    None values are silently filtered out to avoid TypeError on mixed lists.
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0, "p95": 0.0}
    sorted_vals = sorted(clean)
    n = len(sorted_vals)
    return {
        "count": n,
        "avg": round(sum(sorted_vals) / n, 2),
        "min": round(sorted_vals[0], 2),
        "max": round(sorted_vals[-1], 2),
        "p50": round(sorted_vals[n // 2], 2),
        "p95": round(sorted_vals[min(int(n * 0.95), n - 1)], 2),
    }


def _hour_bucket(ts: Optional[float], session_start: float) -> int:
    """Return hour-of-session index (0-based) for a timestamp."""
    if ts is None:
        return 0
    return max(0, int((ts - session_start) / 3600))
