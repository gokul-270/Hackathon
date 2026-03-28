#!/usr/bin/env python3
"""
Cycle Time Degradation Root Cause Analysis — February 2026 Field Trial
Benchmark A13: 21.8%/hour pick cycle time degradation

Analyzes:
1. Hourly cycle time breakdown (approach vs retreat)
2. Motor temperature trend (J3/J4/J5)
3. Motor current trend
4. Joint limit violation trend
5. Detection age trend
6. Session gap analysis
7. Throughput trend (cycle time vs detection frequency)
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# --- Configuration ---
YANTHRA_LOG = Path(
    "/home/udayakumar/pragati_ros2/collected_logs/2026-02-26_16-24/target/"
    "ros2_logs/arm1/2026-02-26-14-05-12-596425-ubuntu-desktop-2176/"
    "yanthra_move_node_2390_1772094927831.log"
)
MOTOR_LOG = Path(
    "/home/udayakumar/pragati_ros2/collected_logs/2026-02-26_16-24/target/"
    "ros2_logs/arm1/2026-02-26-14-05-12-596425-ubuntu-desktop-2176/"
    "mg6010_controller_node_2271_1772094921220.log"
)

BUCKET_MINUTES = 10  # 10-minute buckets


def extract_json_events(log_path, event_type):
    """Extract JSON events of a given type from a log file."""
    events = []
    pattern = re.compile(r'\{.*"event"\s*:\s*"' + event_type + r'".*\}')
    with open(log_path, "r") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                try:
                    data = json.loads(m.group(0))
                    events.append(data)
                except json.JSONDecodeError:
                    pass
    return events


def percentile(sorted_vals, p):
    """Compute percentile from a sorted list."""
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_vals) else f
    d = k - f
    return sorted_vals[f] + d * (sorted_vals[c] - sorted_vals[f])


def stats(values):
    """Compute basic stats from a list of numbers."""
    if not values:
        return {"n": 0, "mean": 0, "median": 0, "p95": 0, "min": 0, "max": 0, "std": 0}
    s = sorted(values)
    n = len(s)
    mean = sum(s) / n
    variance = sum((x - mean) ** 2 for x in s) / n if n > 1 else 0
    return {
        "n": n,
        "mean": round(mean, 1),
        "median": round(percentile(s, 50), 1),
        "p95": round(percentile(s, 95), 1),
        "min": round(s[0], 1),
        "max": round(s[-1], 1),
        "std": round(variance**0.5, 1),
    }


def main():
    print("=" * 80)
    print("CYCLE TIME DEGRADATION ROOT CAUSE ANALYSIS")
    print("February 26, 2026 Field Trial — Benchmark A13")
    print("Reported: 21.8%/hour degradation")
    print("=" * 80)

    # --- Extract events ---
    pick_events = extract_json_events(YANTHRA_LOG, "pick_complete")
    motor_events = extract_json_events(MOTOR_LOG, "motor_health")
    cycle_events = extract_json_events(YANTHRA_LOG, "cycle_complete")

    print(
        f"\nData loaded: {len(pick_events)} pick_complete, "
        f"{len(motor_events)} motor_health, {len(cycle_events)} cycle_complete"
    )

    if not pick_events:
        print("ERROR: No pick_complete events found!")
        sys.exit(1)

    # --- Separate real picks from instant rejections ---
    real_picks = [e for e in pick_events if e.get("total_ms", 0) > 100]
    instant_rejections = [e for e in pick_events if e.get("total_ms", 0) <= 100]
    successful = [e for e in pick_events if e.get("success")]
    failed = [e for e in pick_events if not e.get("success")]

    print(f"\nPick breakdown:")
    print(f"  Total pick_complete events: {len(pick_events)}")
    print(f"  Real picks (total_ms > 100): {len(real_picks)}")
    print(f"  Instant rejections (total_ms <= 100): {len(instant_rejections)}")
    print(f"  Successful: {len(successful)}")
    print(f"  Failed: {len(failed)}")
    print(f"  Success rate (all): {len(successful)/len(pick_events)*100:.1f}%")
    if real_picks:
        real_success = [e for e in real_picks if e.get("success")]
        print(f"  Success rate (real picks only): {len(real_success)/len(real_picks)*100:.1f}%")

    # --- Time range ---
    ts_first = pick_events[0]["ts"]
    ts_last = pick_events[-1]["ts"]
    session_duration_min = (ts_last - ts_first) / 60000
    print(f"\nSession: {session_duration_min:.1f} minutes " f"({ts_first} to {ts_last})")

    # =====================================================================
    # ANALYSIS 1: Per-10-minute-bucket cycle time breakdown
    # =====================================================================
    print("\n" + "=" * 80)
    print("ANALYSIS 1: Cycle Time by 10-Minute Bucket")
    print("=" * 80)

    buckets = defaultdict(list)
    for e in pick_events:
        bucket = int((e["ts"] - ts_first) / (BUCKET_MINUTES * 60000))
        buckets[bucket].append(e)

    print(
        f"\n{'Bucket':>6} | {'Time':>8} | {'Count':>5} | {'Succ':>4} | {'Rate':>5} | "
        f"{'AvgTotal':>8} | {'AvgAppr':>7} | {'AvgRetr':>7} | {'AvgConf':>7} | "
        f"{'AvgDetAge':>9} | {'RealPicks':>9}"
    )
    print("-" * 110)

    bucket_stats = []
    for b in sorted(buckets.keys()):
        events = buckets[b]
        t_min = b * BUCKET_MINUTES
        count = len(events)
        successes = sum(1 for e in events if e.get("success"))
        rate = successes / count * 100 if count else 0

        totals = [e["total_ms"] for e in events]
        approaches = [e["approach_ms"] for e in events if e["total_ms"] > 100]
        retreats = [e["retreat_ms"] for e in events if e["total_ms"] > 100]
        confidences = [e["confidence"] for e in events]
        det_ages = [e["detection_age_ms"] for e in events if e.get("detection_age_ms", 0) > 0]
        real = [e for e in events if e["total_ms"] > 100]

        avg_total = sum(totals) / count if count else 0
        avg_approach = sum(approaches) / len(approaches) if approaches else 0
        avg_retreat = sum(retreats) / len(retreats) if retreats else 0
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        avg_det_age = sum(det_ages) / len(det_ages) if det_ages else 0

        bucket_stats.append(
            {
                "bucket": b,
                "time_min": t_min,
                "count": count,
                "successes": successes,
                "rate": rate,
                "avg_total": avg_total,
                "avg_approach": avg_approach,
                "avg_retreat": avg_retreat,
                "avg_conf": avg_conf,
                "avg_det_age": avg_det_age,
                "real_count": len(real),
            }
        )

        print(
            f"{b:>6} | {t_min:>5}min | {count:>5} | {successes:>4} | {rate:>4.1f}% | "
            f"{avg_total:>7.0f}ms | {avg_approach:>6.0f}ms | {avg_retreat:>6.0f}ms | "
            f"{avg_conf:>6.3f} | {avg_det_age:>8.0f}ms | {len(real):>9}"
        )

    # --- Compute hourly aggregates for approach/retreat ---
    print("\n--- Hourly Phase Breakdown (real picks only, total_ms > 100) ---")
    hourly_buckets = defaultdict(list)
    for e in real_picks:
        hour = int((e["ts"] - ts_first) / 3600000)
        hourly_buckets[hour].append(e)

    print(
        f"\n{'Hour':>4} | {'Count':>5} | {'AvgTotal':>8} | {'AvgAppr':>7} | "
        f"{'AvgRetr':>7} | {'AvgEE':>6} | {'MedTotal':>8} | {'P95Total':>8}"
    )
    print("-" * 80)

    hourly_stats = {}
    for h in sorted(hourly_buckets.keys()):
        events = hourly_buckets[h]
        totals = sorted([e["total_ms"] for e in events])
        approaches = sorted([e["approach_ms"] for e in events])
        retreats = sorted([e["retreat_ms"] for e in events])
        ee_times = sorted([e["ee_on_ms"] for e in events])

        n = len(events)
        avg_t = sum(totals) / n
        avg_a = sum(approaches) / n
        avg_r = sum(retreats) / n
        avg_ee = sum(ee_times) / n
        med_t = percentile(totals, 50)
        p95_t = percentile(totals, 95)

        hourly_stats[h] = {
            "count": n,
            "avg_total": avg_t,
            "avg_approach": avg_a,
            "avg_retreat": avg_r,
            "avg_ee": avg_ee,
            "med_total": med_t,
            "p95_total": p95_t,
        }

        print(
            f"{h:>4} | {n:>5} | {avg_t:>7.0f}ms | {avg_a:>6.0f}ms | "
            f"{avg_r:>6.0f}ms | {avg_ee:>5.0f}ms | {med_t:>7.0f}ms | {p95_t:>7.0f}ms"
        )

    # Degradation calculation
    if len(hourly_stats) >= 2:
        hours = sorted(hourly_stats.keys())
        first_h = hours[0]
        last_h = hours[-1]
        if hourly_stats[first_h]["avg_total"] > 0:
            total_change = (
                (hourly_stats[last_h]["avg_total"] - hourly_stats[first_h]["avg_total"])
                / hourly_stats[first_h]["avg_total"]
                * 100
            )
            approach_change = (
                (
                    (hourly_stats[last_h]["avg_approach"] - hourly_stats[first_h]["avg_approach"])
                    / hourly_stats[first_h]["avg_approach"]
                    * 100
                )
                if hourly_stats[first_h]["avg_approach"] > 0
                else 0
            )
            retreat_change = (
                (
                    (hourly_stats[last_h]["avg_retreat"] - hourly_stats[first_h]["avg_retreat"])
                    / hourly_stats[first_h]["avg_retreat"]
                    * 100
                )
                if hourly_stats[first_h]["avg_retreat"] > 0
                else 0
            )

            print(f"\n  Degradation Hour {first_h} → Hour {last_h}:")
            print(f"    Total:    {total_change:+.1f}%")
            print(f"    Approach: {approach_change:+.1f}%")
            print(f"    Retreat:  {retreat_change:+.1f}%")

    # =====================================================================
    # ANALYSIS 2: Motor Temperature Trend
    # =====================================================================
    print("\n" + "=" * 80)
    print("ANALYSIS 2: Motor Temperature Trend")
    print("=" * 80)

    if motor_events:
        motor_ts_first = motor_events[0]["ts"]
        print(
            f"\n{'MinInto':>7} | {'J3_Temp':>7} | {'J4_Temp':>7} | {'J5_Temp':>7} | "
            f"{'J3_Curr':>7} | {'J4_Curr':>7} | {'J5_Curr':>7} | {'Vbus':>5}"
        )
        print("-" * 75)

        temp_data = {"joint3": [], "joint4": [], "joint5": []}
        curr_data = {"joint3": [], "joint4": [], "joint5": []}

        for ev in motor_events:
            t_min = (ev["ts"] - motor_ts_first) / 60000
            motors = {m["joint"]: m for m in ev["motors"]}
            j3 = motors.get("joint3", {})
            j4 = motors.get("joint4", {})
            j5 = motors.get("joint5", {})

            for joint, m in [("joint3", j3), ("joint4", j4), ("joint5", j5)]:
                if m:
                    temp_data[joint].append((t_min, m.get("temp_c", 0)))
                    curr_data[joint].append((t_min, m.get("current_a", 0)))

            # Print every 5th event (~2.5 min intervals for 30s reports)
            idx = motor_events.index(ev)
            if idx % 5 == 0:
                print(
                    f"{t_min:>6.1f}m | {j3.get('temp_c', '?'):>6}C | "
                    f"{j4.get('temp_c', '?'):>6}C | {j5.get('temp_c', '?'):>6}C | "
                    f"{j3.get('current_a', 0):>6.2f}A | {j4.get('current_a', 0):>6.2f}A | "
                    f"{j5.get('current_a', 0):>6.2f}A | {ev.get('vbus_v', 0):>5.1f}"
                )

        # Temperature trend summary
        print("\n--- Temperature Summary ---")
        for joint in ["joint3", "joint4", "joint5"]:
            temps = [t for _, t in temp_data[joint]]
            if temps:
                first_5 = temps[:5]
                last_5 = temps[-5:]
                print(
                    f"  {joint}: Start avg={sum(first_5)/len(first_5):.1f}C, "
                    f"End avg={sum(last_5)/len(last_5):.1f}C, "
                    f"Max={max(temps)}C, "
                    f"Delta={sum(last_5)/len(last_5) - sum(first_5)/len(first_5):+.1f}C"
                )

        # =====================================================================
        # ANALYSIS 3: Motor Current Trend
        # =====================================================================
        print("\n" + "=" * 80)
        print("ANALYSIS 3: Motor Current Trend (Mechanical Resistance)")
        print("=" * 80)

        # Split motor events into first half and second half
        mid = len(motor_events) // 2
        for joint in ["joint3", "joint4", "joint5"]:
            first_half_curr = [abs(c) for _, c in curr_data[joint][:mid]]
            second_half_curr = [abs(c) for _, c in curr_data[joint][mid:]]
            if first_half_curr and second_half_curr:
                avg_first = sum(first_half_curr) / len(first_half_curr)
                avg_second = sum(second_half_curr) / len(second_half_curr)
                change = (avg_second - avg_first) / avg_first * 100 if avg_first > 0 else 0
                print(
                    f"  {joint}: First half avg={avg_first:.3f}A, "
                    f"Second half avg={avg_second:.3f}A, Change={change:+.1f}%"
                )
    else:
        print("  No motor_health events found in motor log.")

    # =====================================================================
    # ANALYSIS 4: Joint Limit Violation Trend
    # =====================================================================
    print("\n" + "=" * 80)
    print("ANALYSIS 4: Joint Limit Violation Trend")
    print("=" * 80)

    # Count instant rejections (total_ms <= 1 => workspace violation) by bucket
    rejection_by_bucket = defaultdict(int)
    total_by_bucket = defaultdict(int)
    for e in pick_events:
        bucket = int((e["ts"] - ts_first) / (BUCKET_MINUTES * 60000))
        total_by_bucket[bucket] += 1
        if e["total_ms"] <= 1 and not e.get("success"):
            rejection_by_bucket[bucket] += 1

    print(f"\n{'Bucket':>6} | {'Time':>8} | {'Total':>5} | {'Rejections':>10} | {'Rate':>6}")
    print("-" * 50)
    for b in sorted(total_by_bucket.keys()):
        t_min = b * BUCKET_MINUTES
        total = total_by_bucket[b]
        rej = rejection_by_bucket[b]
        rate = rej / total * 100 if total else 0
        print(f"{b:>6} | {t_min:>5}min | {total:>5} | {rej:>10} | {rate:>5.1f}%")

    # Hourly rejection trend
    hourly_rej = defaultdict(lambda: {"total": 0, "rej": 0})
    for e in pick_events:
        h = int((e["ts"] - ts_first) / 3600000)
        hourly_rej[h]["total"] += 1
        if e["total_ms"] <= 1 and not e.get("success"):
            hourly_rej[h]["rej"] += 1

    print("\n--- Hourly Rejection Rate ---")
    for h in sorted(hourly_rej.keys()):
        d = hourly_rej[h]
        rate = d["rej"] / d["total"] * 100 if d["total"] else 0
        print(f"  Hour {h}: {d['rej']}/{d['total']} = {rate:.1f}% instant rejections")

    # =====================================================================
    # ANALYSIS 5: Detection Age Trend
    # =====================================================================
    print("\n" + "=" * 80)
    print("ANALYSIS 5: Detection Age Trend")
    print("=" * 80)

    det_age_by_bucket = defaultdict(list)
    for e in pick_events:
        if e.get("detection_age_ms", 0) > 0:
            bucket = int((e["ts"] - ts_first) / (BUCKET_MINUTES * 60000))
            det_age_by_bucket[bucket].append(e["detection_age_ms"])

    print(
        f"\n{'Bucket':>6} | {'Time':>8} | {'Count':>5} | {'AvgAge':>8} | "
        f"{'MedAge':>8} | {'MaxAge':>8}"
    )
    print("-" * 60)
    for b in sorted(det_age_by_bucket.keys()):
        ages = det_age_by_bucket[b]
        t_min = b * BUCKET_MINUTES
        avg_age = sum(ages) / len(ages) if ages else 0
        med_age = percentile(sorted(ages), 50) if ages else 0
        max_age = max(ages) if ages else 0
        print(
            f"{b:>6} | {t_min:>5}min | {len(ages):>5} | {avg_age:>7.0f}ms | "
            f"{med_age:>7.0f}ms | {max_age:>7.0f}ms"
        )

    # =====================================================================
    # ANALYSIS 6: Session Gap Analysis
    # =====================================================================
    print("\n" + "=" * 80)
    print("ANALYSIS 6: Session Gap Analysis")
    print("=" * 80)

    # Find gaps > 30 seconds between consecutive pick events
    gaps = []
    for i in range(1, len(pick_events)):
        delta_ms = pick_events[i]["ts"] - pick_events[i - 1]["ts"]
        if delta_ms > 30000:  # > 30 seconds
            gaps.append(
                {
                    "idx": i,
                    "ts_before": pick_events[i - 1]["ts"],
                    "ts_after": pick_events[i]["ts"],
                    "gap_s": delta_ms / 1000,
                    "total_ms_before": pick_events[i - 1]["total_ms"],
                    "total_ms_after": pick_events[i]["total_ms"],
                }
            )

    if gaps:
        print(f"\nFound {len(gaps)} gaps > 30 seconds:")
        for g in gaps:
            t_before_min = (g["ts_before"] - ts_first) / 60000
            t_after_min = (g["ts_after"] - ts_first) / 60000
            print(
                f"\n  Gap at {t_before_min:.1f}min → {t_after_min:.1f}min "
                f"({g['gap_s']:.1f}s = {g['gap_s']/60:.1f}min)"
            )

            # Get 5 picks before and after gap
            idx = g["idx"]
            before = [e for e in pick_events[max(0, idx - 5) : idx] if e["total_ms"] > 100]
            after = [
                e for e in pick_events[idx : min(len(pick_events), idx + 5)] if e["total_ms"] > 100
            ]

            if before:
                avg_before = sum(e["total_ms"] for e in before) / len(before)
                print(f"    5 real picks BEFORE gap: avg total_ms = {avg_before:.0f}ms")
            if after:
                avg_after = sum(e["total_ms"] for e in after) / len(after)
                print(f"    5 real picks AFTER gap:  avg total_ms = {avg_after:.0f}ms")
            if before and after:
                change = (avg_after - avg_before) / avg_before * 100
                print(f"    Change: {change:+.1f}%")
    else:
        print("  No significant gaps (>30s) found.")

    # =====================================================================
    # ANALYSIS 7: Throughput Trend (picks/10min vs cycle time)
    # =====================================================================
    print("\n" + "=" * 80)
    print("ANALYSIS 7: Throughput Trend — Cycle Time vs Pick Frequency")
    print("=" * 80)

    print(
        f"\n{'Bucket':>6} | {'Time':>8} | {'AllPicks':>8} | {'RealPicks':>9} | "
        f"{'Success':>7} | {'AvgCycleMs':>10} | {'Picks/hr':>8} | {'SuccPicks/hr':>12}"
    )
    print("-" * 100)

    for bs in bucket_stats:
        b = bs["bucket"]
        t_min = bs["time_min"]
        # Extrapolate to picks per hour (from 10-min bucket)
        picks_per_hr = bs["real_count"] * (60 / BUCKET_MINUTES)
        succ_per_hr = bs["successes"] * (60 / BUCKET_MINUTES)
        print(
            f"{b:>6} | {t_min:>5}min | {bs['count']:>8} | {bs['real_count']:>9} | "
            f"{bs['successes']:>7} | {bs['avg_total']:>9.0f}ms | "
            f"{picks_per_hr:>7.0f} | {succ_per_hr:>12.0f}"
        )

    # =====================================================================
    # ANALYSIS 8: Correlation Matrix — What Changes Together?
    # =====================================================================
    print("\n" + "=" * 80)
    print("ANALYSIS 8: Per-Pick Time Series (real picks, chronological)")
    print("=" * 80)

    print(
        f"\n{'Pick#':>5} | {'MinInto':>7} | {'Total':>7} | {'Approach':>8} | "
        f"{'Retreat':>7} | {'EE_on':>6} | {'Conf':>6} | {'DetAge':>7} | {'Succ':>4} | {'X':>6}"
    )
    print("-" * 95)

    for i, e in enumerate(real_picks):
        t_min = (e["ts"] - ts_first) / 60000
        print(
            f"{i:>5} | {t_min:>6.1f}m | {e['total_ms']:>6}ms | "
            f"{e['approach_ms']:>7}ms | {e['retreat_ms']:>6}ms | "
            f"{e['ee_on_ms']:>5}ms | {e['confidence']:>5.3f} | "
            f"{e.get('detection_age_ms', 0):>6}ms | "
            f"{'Y' if e.get('success') else 'N':>4} | "
            f"{e['position']['x']:>5.3f}"
        )

    # =====================================================================
    # SYNTHESIS: Root Cause Determination
    # =====================================================================
    print("\n" + "=" * 80)
    print("SYNTHESIS: Root Cause Determination")
    print("=" * 80)

    # Compute overall stats
    real_totals = [e["total_ms"] for e in real_picks]
    real_approaches = [e["approach_ms"] for e in real_picks]
    real_retreats = [e["retreat_ms"] for e in real_picks]

    print(f"\n--- Overall Real Pick Stats ---")
    print(f"  Total:    {stats(real_totals)}")
    print(f"  Approach: {stats(real_approaches)}")
    print(f"  Retreat:  {stats(real_retreats)}")

    # Compute linear regression on total_ms vs time
    if len(real_picks) >= 2:
        xs = [(e["ts"] - ts_first) / 3600000 for e in real_picks]  # hours
        ys = [e["total_ms"] for e in real_picks]
        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)

        denom = n * sum_x2 - sum_x * sum_x
        if denom != 0:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            # R² calculation
            y_mean = sum_y / n
            ss_tot = sum((y - y_mean) ** 2 for y in ys)
            ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            print(f"\n--- Linear Regression: total_ms vs hours ---")
            print(f"  Slope:     {slope:.1f} ms/hour")
            print(f"  Intercept: {intercept:.1f} ms (predicted at t=0)")
            print(f"  R²:        {r_squared:.4f}")
            print(f"  Degradation rate: {slope/intercept*100:.1f}%/hour" if intercept > 0 else "")

        # Same for approach
        ys_a = [e["approach_ms"] for e in real_picks]
        sum_ya = sum(ys_a)
        sum_xya = sum(x * y for x, y in zip(xs, ys_a))
        denom_a = n * sum_x2 - sum_x * sum_x
        if denom_a != 0:
            slope_a = (n * sum_xya - sum_x * sum_ya) / denom_a
            intercept_a = (sum_ya - slope_a * sum_x) / n
            print(f"\n--- Linear Regression: approach_ms vs hours ---")
            print(f"  Slope:     {slope_a:.1f} ms/hour")
            print(f"  Intercept: {intercept_a:.1f} ms")
            if intercept_a > 0:
                print(f"  Degradation rate: {slope_a/intercept_a*100:.1f}%/hour")

        # Same for retreat
        ys_r = [e["retreat_ms"] for e in real_picks]
        sum_yr = sum(ys_r)
        sum_xyr = sum(x * y for x, y in zip(xs, ys_r))
        if denom != 0:
            slope_r = (n * sum_xyr - sum_x * sum_yr) / denom
            intercept_r = (sum_yr - slope_r * sum_x) / n
            print(f"\n--- Linear Regression: retreat_ms vs hours ---")
            print(f"  Slope:     {slope_r:.1f} ms/hour")
            print(f"  Intercept: {intercept_r:.1f} ms")
            if intercept_r > 0:
                print(f"  Degradation rate: {slope_r/intercept_r*100:.1f}%/hour")

        # Detection age regression
        real_with_age = [(e, x) for e, x in zip(real_picks, xs) if e.get("detection_age_ms", 0) > 0]
        if len(real_with_age) >= 2:
            xs_d = [x for _, x in real_with_age]
            ys_d = [e["detection_age_ms"] for e, _ in real_with_age]
            n_d = len(xs_d)
            sum_xd = sum(xs_d)
            sum_yd = sum(ys_d)
            sum_xyd = sum(x * y for x, y in zip(xs_d, ys_d))
            sum_x2d = sum(x * x for x in xs_d)
            denom_d = n_d * sum_x2d - sum_xd * sum_xd
            if denom_d != 0:
                slope_d = (n_d * sum_xyd - sum_xd * sum_yd) / denom_d
                intercept_d = (sum_yd - slope_d * sum_xd) / n_d
                print(f"\n--- Linear Regression: detection_age_ms vs hours ---")
                print(f"  Slope:     {slope_d:.1f} ms/hour")
                print(f"  Intercept: {intercept_d:.1f} ms")

    # --- Confidence trend ---
    if len(real_picks) >= 2:
        confs = [e["confidence"] for e in real_picks]
        first_quarter = confs[: len(confs) // 4]
        last_quarter = confs[3 * len(confs) // 4 :]
        if first_quarter and last_quarter:
            print(f"\n--- Confidence Trend ---")
            print(f"  First quarter avg: {sum(first_quarter)/len(first_quarter):.4f}")
            print(f"  Last quarter avg:  {sum(last_quarter)/len(last_quarter):.4f}")

    # --- X position trend (are later picks reaching further?) ---
    if len(real_picks) >= 2:
        x_positions = [e["position"]["x"] for e in real_picks]
        first_q = x_positions[: len(x_positions) // 4]
        last_q = x_positions[3 * len(x_positions) // 4 :]
        if first_q and last_q:
            print(f"\n--- Target X Position Trend ---")
            print(f"  First quarter avg X: {sum(first_q)/len(first_q):.4f}m")
            print(f"  Last quarter avg X:  {sum(last_q)/len(last_q):.4f}m")
            print(f"  (Further X = further reach = longer approach)")

    print("\n" + "=" * 80)
    print("END OF ANALYSIS")
    print("=" * 80)


if __name__ == "__main__":
    main()
