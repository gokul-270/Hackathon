#!/usr/bin/env python3
"""
Cross-session cycle time degradation analysis.
Analyzes ALL sessions to verify the 21.8%/hour claim and find true root cause.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(
    "/home/udayakumar/pragati_ros2/collected_logs/2026-02-26_16-24/target/" "ros2_logs/arm1"
)

SESSIONS = [
    ("S1-12:01", "2026-02-26-12-01-15-306448-ubuntu-desktop-6468"),
    ("S2-12:10", "2026-02-26-12-10-13-974347-ubuntu-desktop-2188"),
    ("S3-12:22", "2026-02-26-12-22-31-169623-ubuntu-desktop-2128"),
    ("S4-12:27", "2026-02-26-12-27-34-954940-ubuntu-desktop-2196"),
    ("S5-12:30", "2026-02-26-12-30-45-230216-ubuntu-desktop-2190"),
    ("S6-13:04", "2026-02-26-13-04-59-539737-ubuntu-desktop-2192"),
    ("S7-13:45", "2026-02-26-13-45-49-241079-ubuntu-desktop-11341"),
    ("S8-14:02", "2026-02-26-14-02-08-443716-ubuntu-desktop-15114"),
    ("S9-14:05", "2026-02-26-14-05-12-596425-ubuntu-desktop-2176"),
]


def extract_events(log_path, event_type):
    events = []
    pattern = re.compile(r'\{.*"event"\s*:\s*"' + event_type + r'".*\}')
    try:
        with open(log_path, "r") as f:
            for line in f:
                m = pattern.search(line)
                if m:
                    try:
                        events.append(json.loads(m.group(0)))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return events


def main():
    print("=" * 90)
    print("CROSS-SESSION DEGRADATION ANALYSIS")
    print("=" * 90)

    all_picks = []
    global_ts_first = None

    for name, sdir in SESSIONS:
        session_dir = BASE / sdir
        ylog = list(session_dir.glob("yanthra_move_node_*.log"))
        if not ylog:
            continue
        picks = extract_events(ylog[0], "pick_complete")
        if not picks:
            print(f"  {name}: 0 picks (skipped)")
            continue

        real = [p for p in picks if p["total_ms"] > 100]
        succ = [p for p in picks if p.get("success")]
        instant_rej = [p for p in picks if p["total_ms"] <= 1 and not p.get("success")]

        ts_min = picks[0]["ts"]
        ts_max = picks[-1]["ts"]
        dur_min = (ts_max - ts_min) / 60000

        if global_ts_first is None:
            global_ts_first = ts_min

        for p in picks:
            p["_session"] = name
            p["_global_hour"] = (p["ts"] - global_ts_first) / 3600000
        all_picks.extend(picks)

        real_totals = [p["total_ms"] for p in real]
        avg_total = sum(real_totals) / len(real_totals) if real_totals else 0
        real_approaches = [p["approach_ms"] for p in real]
        avg_approach = sum(real_approaches) / len(real_approaches) if real_approaches else 0
        real_retreats = [p["retreat_ms"] for p in real]
        avg_retreat = sum(real_retreats) / len(real_retreats) if real_retreats else 0

        print(
            f"  {name}: {len(picks)} picks ({len(real)} real, {len(instant_rej)} rej), "
            f"{len(succ)} succ ({len(succ)/len(picks)*100:.0f}%), "
            f"dur={dur_min:.1f}min, "
            f"avg_total={avg_total:.0f}ms, avg_approach={avg_approach:.0f}ms, "
            f"avg_retreat={avg_retreat:.0f}ms"
        )

    print(f"\nTotal across all sessions: {len(all_picks)} pick_complete events")

    # --- Global hourly analysis ---
    print("\n" + "=" * 90)
    print("GLOBAL HOURLY ANALYSIS (time since first pick across all sessions)")
    print("=" * 90)

    hourly = defaultdict(list)
    for p in all_picks:
        h = int(p["_global_hour"])
        hourly[h].append(p)

    print(
        f"\n{'Hour':>4} | {'Total':>5} | {'Real':>4} | {'Succ':>4} | {'Rate':>5} | "
        f"{'AvgTotalAll':>11} | {'AvgTotalReal':>12} | {'AvgApprReal':>11} | "
        f"{'AvgRetrReal':>11} | {'InstRej':>7} | {'InstRejRate':>11}"
    )
    print("-" * 115)

    hour_data = {}
    for h in sorted(hourly.keys()):
        events = hourly[h]
        total = len(events)
        real = [e for e in events if e["total_ms"] > 100]
        succ = [e for e in events if e.get("success")]
        instant = [e for e in events if e["total_ms"] <= 1 and not e.get("success")]
        rate = len(succ) / total * 100 if total else 0
        rej_rate = len(instant) / total * 100 if total else 0

        all_totals = [e["total_ms"] for e in events]
        avg_all = sum(all_totals) / total if total else 0
        real_totals = [e["total_ms"] for e in real]
        avg_real = sum(real_totals) / len(real) if real else 0
        real_app = [e["approach_ms"] for e in real]
        avg_app = sum(real_app) / len(real_app) if real_app else 0
        real_ret = [e["retreat_ms"] for e in real]
        avg_ret = sum(real_ret) / len(real_ret) if real_ret else 0

        hour_data[h] = {
            "total": total,
            "real": len(real),
            "succ": len(succ),
            "rate": rate,
            "avg_all": avg_all,
            "avg_real": avg_real,
            "avg_app": avg_app,
            "avg_ret": avg_ret,
            "rej_count": len(instant),
            "rej_rate": rej_rate,
        }

        print(
            f"{h:>4} | {total:>5} | {len(real):>4} | {len(succ):>4} | {rate:>4.1f}% | "
            f"{avg_all:>10.0f}ms | {avg_real:>11.0f}ms | {avg_app:>10.0f}ms | "
            f"{avg_ret:>10.0f}ms | {len(instant):>7} | {rej_rate:>10.1f}%"
        )

    # Compute degradation
    hours = sorted(hour_data.keys())
    if len(hours) >= 2:
        h0, h_last = hours[0], hours[-1]
        d0, dl = hour_data[h0], hour_data[h_last]

        print(f"\n--- Degradation from Hour {h0} to Hour {h_last} ---")
        if d0["avg_all"] > 0:
            total_deg = (dl["avg_all"] - d0["avg_all"]) / d0["avg_all"] * 100
            n_hours = h_last - h0 if h_last > h0 else 1
            per_hour = total_deg / n_hours
            print(
                f"  avg_total_ms (all events): {d0['avg_all']:.0f} → {dl['avg_all']:.0f} "
                f"({total_deg:+.1f}% total, {per_hour:+.1f}%/hour)"
            )
        if d0["avg_real"] > 0:
            real_deg = (dl["avg_real"] - d0["avg_real"]) / d0["avg_real"] * 100
            print(
                f"  avg_total_ms (real picks): {d0['avg_real']:.0f} → {dl['avg_real']:.0f} "
                f"({real_deg:+.1f}%)"
            )
        print(f"  Rejection rate: {d0['rej_rate']:.1f}% → {dl['rej_rate']:.1f}%")
        print(f"  Throughput: {d0['total']} → {dl['total']} picks/hour")
        print(f"  Success rate: {d0['rate']:.1f}% → {dl['rate']:.1f}%")

    # --- 15-minute bucket analysis across all sessions ---
    print("\n" + "=" * 90)
    print("15-MINUTE BUCKET ANALYSIS (all sessions, rejection rate over time)")
    print("=" * 90)

    buckets_15 = defaultdict(list)
    for p in all_picks:
        b = int((p["ts"] - global_ts_first) / (15 * 60000))
        buckets_15[b].append(p)

    print(
        f"\n{'Bucket':>6} | {'Min':>4} | {'Total':>5} | {'Real':>4} | {'Succ':>4} | "
        f"{'RejRate':>7} | {'AvgTotReal':>10} | {'AvgAppr':>7} | {'AvgRetr':>7} | "
        f"{'RealPicks/hr':>12}"
    )
    print("-" * 100)

    for b in sorted(buckets_15.keys()):
        events = buckets_15[b]
        t_min = b * 15
        total = len(events)
        real = [e for e in events if e["total_ms"] > 100]
        succ = [e for e in events if e.get("success")]
        instant = [e for e in events if e["total_ms"] <= 1 and not e.get("success")]
        rej_rate = len(instant) / total * 100 if total else 0

        real_totals = [e["total_ms"] for e in real]
        avg_real = sum(real_totals) / len(real) if real else 0
        real_app = [e["approach_ms"] for e in real]
        avg_app = sum(real_app) / len(real_app) if real_app else 0
        real_ret = [e["retreat_ms"] for e in real]
        avg_ret = sum(real_ret) / len(real_ret) if real_ret else 0
        throughput = len(real) * 4  # extrapolate to per hour

        print(
            f"{b:>6} | {t_min:>3}m | {total:>5} | {len(real):>4} | {len(succ):>4} | "
            f"{rej_rate:>6.1f}% | {avg_real:>9.0f}ms | {avg_app:>6.0f}ms | "
            f"{avg_ret:>6.0f}ms | {throughput:>12}"
        )

    # --- Success rate hourly (the metric the log analyzer used) ---
    print("\n" + "=" * 90)
    print("SUCCESS RATE vs HOURLY (matches log analyzer reported rates)")
    print("=" * 90)

    for h in sorted(hourly.keys()):
        events = hourly[h]
        total = len(events)
        succ = sum(1 for e in events if e.get("success"))
        rate = succ / total * 100 if total else 0
        real = [e for e in events if e["total_ms"] > 100]
        real_succ = sum(1 for e in real if e.get("success"))
        real_rate = real_succ / len(real) * 100 if real else 0
        print(
            f"  Hour {h}: {rate:.1f}% overall ({succ}/{total}), "
            f"{real_rate:.1f}% real picks ({real_succ}/{len(real)})"
        )

    # --- The key question: is cycle time increasing, or rejection ratio? ---
    print("\n" + "=" * 90)
    print(
        "KEY QUESTION: Are REAL pick cycle times increasing, or is the rejection RATIO increasing?"
    )
    print("=" * 90)

    # Linear regression on real picks across ALL sessions
    real_all = [p for p in all_picks if p["total_ms"] > 100]
    if len(real_all) >= 2:
        xs = [p["_global_hour"] for p in real_all]
        ys = [p["total_ms"] for p in real_all]
        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)
        denom = n * sum_x2 - sum_x * sum_x
        if denom != 0:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            y_mean = sum_y / n
            ss_tot = sum((y - y_mean) ** 2 for y in ys)
            ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            print(f"\n  Real pick total_ms regression (all sessions, n={n}):")
            print(f"    Slope:     {slope:.1f} ms/hour")
            print(f"    Intercept: {intercept:.1f} ms")
            print(f"    R²:        {r2:.4f}")
            if intercept > 0:
                print(f"    Rate:      {slope/intercept*100:.1f}%/hour")

    # Now regression on approach and retreat separately
    if len(real_all) >= 2:
        for phase_name, field in [("approach_ms", "approach_ms"), ("retreat_ms", "retreat_ms")]:
            ys_p = [p[field] for p in real_all]
            sum_yp = sum(ys_p)
            sum_xyp = sum(x * y for x, y in zip(xs, ys_p))
            if denom != 0:
                slope_p = (n * sum_xyp - sum_x * sum_yp) / denom
                intercept_p = (sum_yp - slope_p * sum_x) / n
                print(f"\n  {phase_name} regression:")
                print(f"    Slope:     {slope_p:.1f} ms/hour")
                print(f"    Intercept: {intercept_p:.1f} ms")
                if intercept_p > 0:
                    print(f"    Rate:      {slope_p/intercept_p*100:.1f}%/hour")

    # --- Detection frequency (picks per 10 min) vs rejection ratio ---
    print("\n" + "=" * 90)
    print("DETECTION FREQUENCY vs CYCLE TIME OVER TIME")
    print("=" * 90)

    buckets_10 = defaultdict(list)
    for p in all_picks:
        b = int((p["ts"] - global_ts_first) / (10 * 60000))
        buckets_10[b].append(p)

    print(
        f"\n{'Bucket':>6} | {'Min':>4} | {'Total':>5} | {'Real':>4} | {'RealHz':>6} | "
        f"{'AvgCycle':>8} | {'RejRatio':>8}"
    )
    print("-" * 65)
    for b in sorted(buckets_10.keys()):
        events = buckets_10[b]
        t_min = b * 10
        total = len(events)
        real = [e for e in events if e["total_ms"] > 100]
        rej = [e for e in events if e["total_ms"] <= 1 and not e.get("success")]
        real_hz = len(real) / 600  # picks per second in 10 min window
        real_totals = [e["total_ms"] for e in real]
        avg_cycle = sum(real_totals) / len(real) if real else 0
        rej_ratio = len(rej) / total * 100 if total else 0

        print(
            f"{b:>6} | {t_min:>3}m | {total:>5} | {len(real):>4} | {real_hz:>5.3f} | "
            f"{avg_cycle:>7.0f}ms | {rej_ratio:>7.1f}%"
        )

    # --- Bimodal distribution check ---
    print("\n" + "=" * 90)
    print("BIMODAL DISTRIBUTION CHECK")
    print("=" * 90)

    # The "real picks" seem to cluster around 1200ms and 5500-7500ms
    ranges = {
        "0-500ms": (0, 500),
        "500-2000ms": (500, 2000),
        "2000-5000ms": (2000, 5000),
        "5000-7000ms": (5000, 7000),
        "7000-8000ms": (7000, 8000),
        "8000+ms": (8000, 100000),
    }
    for label, (lo, hi) in ranges.items():
        count = sum(1 for p in all_picks if lo <= p["total_ms"] < hi)
        real_in_range = [p for p in all_picks if lo <= p["total_ms"] < hi and p["total_ms"] > 100]
        succ = sum(1 for p in real_in_range if p.get("success"))
        print(f"  {label:>12}: {count:>4} events " f"({succ} successful)")

    # Check ~1200ms cluster
    around_1200 = [p for p in all_picks if 1100 <= p["total_ms"] <= 1300]
    if around_1200:
        succ_1200 = sum(1 for p in around_1200 if p.get("success"))
        print(f"\n  ~1200ms cluster: {len(around_1200)} events, {succ_1200} successful")
        print(f"    These are: approach_ms=0-1, retreat_ms=0 → NOT real picks")
        print(f"    They have total_ms=~1206ms but approach=0, retreat=0")
        print(f"    This is the 'delayed rejection' pattern — IK check passed but")
        print(f"    something else rejected after a ~1.2s delay")
        # Check what these look like
        for p in around_1200[:3]:
            print(
                f"    Example: total={p['total_ms']}ms, approach={p['approach_ms']}ms, "
                f"retreat={p['retreat_ms']}ms, success={p.get('success')}, "
                f"x={p['position']['x']:.3f}"
            )

    print("\n" + "=" * 90)
    print("FINAL SYNTHESIS")
    print("=" * 90)


if __name__ == "__main__":
    main()
