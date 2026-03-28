"""Data decimation for chart rendering (Task 8.1).

Reduces high-density time-series data to a target number of buckets,
preserving min/max extremes for accurate chart rendering on constrained
clients (RPi 4B browser).
"""

import time
from typing import Dict, List

from fastapi import APIRouter, Query

decimation_router = APIRouter()


def decimate_metrics(metrics: List[Dict], target_points: int) -> List[Dict]:
    """Reduce *metrics* to at most *target_points* time-bucketed summaries.

    Each bucket contains: timestamp (midpoint), value_avg, value_min,
    value_max, count.  Empty buckets (gaps) are omitted.
    """
    if not metrics:
        return []

    # Sort by timestamp ascending
    sorted_m = sorted(metrics, key=lambda m: m["timestamp"])

    t_min = sorted_m[0]["timestamp"]
    t_max = sorted_m[-1]["timestamp"]
    span = t_max - t_min

    # If all points have the same timestamp or only one point, return single bucket
    if span == 0 or len(sorted_m) <= 1:
        values = [m["value"] for m in sorted_m]
        return [
            {
                "timestamp": t_min,
                "value_avg": sum(values) / len(values),
                "value_min": min(values),
                "value_max": max(values),
                "count": len(sorted_m),
            }
        ]

    # If fewer points than target, each point becomes its own bucket
    actual_buckets = min(target_points, len(sorted_m))
    bucket_width = span / actual_buckets

    # Accumulate into buckets
    buckets: Dict[int, List[float]] = {}
    bucket_ts: Dict[int, List[float]] = {}

    for m in sorted_m:
        idx = int((m["timestamp"] - t_min) / bucket_width)
        # Clamp last-edge point into final bucket
        if idx >= actual_buckets:
            idx = actual_buckets - 1
        buckets.setdefault(idx, []).append(m["value"])
        bucket_ts.setdefault(idx, []).append(m["timestamp"])

    # Build result — skip empty buckets
    result = []
    for idx in sorted(buckets.keys()):
        vals = buckets[idx]
        ts_list = bucket_ts[idx]
        result.append(
            {
                "timestamp": sum(ts_list) / len(ts_list),
                "value_avg": sum(vals) / len(vals),
                "value_min": min(vals),
                "value_max": max(vals),
                "count": len(vals),
            }
        )

    return result


@decimation_router.get("/api/history/decimated")
async def get_decimated_history(
    points: int = Query(default=500, ge=1, le=10000),
    hours: int = Query(default=168, ge=1, le=8760),
):
    """Return decimated historical metrics for chart rendering."""
    # Try to fetch from HistoricalDataService if available
    raw_metrics: List[Dict] = []
    try:
        from backend.historical_data_service import get_historical_data

        svc = get_historical_data()
        start_time = time.time() - (hours * 3600)
        raw_metrics = svc.query_metrics(start_time=start_time, limit=50000)
    except Exception:
        pass

    decimated = decimate_metrics(raw_metrics, target_points=points)

    return {
        "points": points,
        "hours": hours,
        "metrics": decimated,
    }
