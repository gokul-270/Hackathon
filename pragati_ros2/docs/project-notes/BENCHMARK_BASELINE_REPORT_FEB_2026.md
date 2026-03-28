# Benchmark Baseline Report — February 2026 Field Trial

**Date:** March 17, 2026
**Data source:** Collected logs from Feb 26, 2026 field trial
**Log location:** `collected_logs/2026-02-26_16-24/target/`
**Analysis tool:** `scripts/log_analyzer/ --field-summary`
**Session duration:** 2 hours 46 minutes (9 sessions, 133 log files, 95,575 lines)
**Software version:** Commit `fcadd3b3` on `pragati_ros2` branch (built Feb 25, 2026)
**Configuration:** Single arm (arm1), YOLOv11 detection model

---

## Purpose

This document captures quantitative baselines from the February 2026 field trial for
benchmarks A9–A13 defined in the March Field Trial Plan. These serve as the reference
point for measuring improvement in the March 25, 2026 field trial.

Since February, 30+ OpenSpec changes have been implemented addressing the issues
identified here (zero spatial filtering, workspace pre-filtering, position feedback,
motor hardening, eject sequence, logging gaps, etc.). The March trial will show the
impact of these changes.

---

## A9: Detection Accuracy

**Benchmark objective:** Measure precision/recall/F1 with known cotton positions.

### What we have (proxy metrics from field data)

No ground-truth labels exist in field logs, so classical precision/recall/F1 cannot
be computed. The following proxy metrics characterize detection performance:

#### Detection Funnel

| Stage | Count | % of Raw |
|-------|------:|----------|
| NN detections (total) | 3,441 | 100% |
| Depth survived (stereo OK) | 2,938 | 85.4% |
| Accepted (post-filter) | 1,544 | 52.6% of survived |
| Pick attempts | 1,181 | 76.5% of accepted |
| **Successful picks** | **315** | **26.7% of attempts** |
| **End-to-end conversion** | — | **9.2%** (NN → pick) |

- **Stereo depth failure rate:** 14.6% (503/3,441) — OAK-D Lite passive stereo fails
  on textureless white cotton
- **Rejection breakdown** (of 2,938 depth-survived detections):
  - Border-filtered: 5.3% (156) — detections at image edges
  - Not-pickable: 9.3% (273) — outside arm reach (specific rejection category)
  - Other filters: 32.9% (965) — workspace, geometric, duplicate rejection
  - **Total rejected:** 47.4% (1,394) → 1,544 accepted
- **Frame detection rate:** 75.5% of frames had at least 1 cotton detected (688/911)
- **Per-frame density:** mean 3.23 raw / 1.69 accepted per frame
- **Stale frame flush:** avg 6.0 stale frames flushed per request
- **Frame wait time:** avg 47.5ms

#### Detection Confidence

| Stat | Value |
|------|------:|
| Mean | 0.744 |
| Median (p50) | 0.773 |
| P25 | 0.650 |
| P75 | 0.844 |
| P90 | 0.883 |
| Range | 0.500 – 0.933 |

Distribution: 36.0% in [0.8–0.9), 24.9% in [0.7–0.8), 4.5% reach 0.9+.

#### Pick Success by Confidence Band

| Confidence Band | Total Picks | Succeeded | Success Rate |
|-----------------|------------:|----------:|----------:|
| [0.5–0.6) | 195 | 51 | 26.2% |
| [0.6–0.7) | 213 | 58 | 27.2% |
| [0.7–0.8) | 292 | 65 | 22.3% |
| [0.8–0.9) | 433 | 122 | 28.2% |
| [0.9–1.0) | 48 | 19 | **39.6%** |

**Key finding:** Confidence is NOT a strong predictor of pick success. Successful
picks (mean conf 0.751) vs failed picks (mean conf 0.741) are nearly identical.
The failure mode is primarily spatial/mechanical (workspace violations), not
detection quality.

#### Inference Timing

| Metric | Value |
|--------|------:|
| NN inference | 47.7ms mean, 42ms median, 95ms p95 |
| Frame capture | 1.4ms mean |
| Image save | 15.2ms mean |
| Total processing | 65.3ms mean, 58ms median |
| Effective FPS | ~30 FPS |
| Camera temperature | 60.1°C mean, 63°C max (stable, +0.02°C/min) |

#### Per-Session Detection Stats

| Session | Frames | Accepted | Picks | Successes | Rate |
|---------|-------:|----------:|------:|----------:|-----:|
| 12:01 | 37 | 59 | 43 | 20 | 47% |
| 12:10 | 55 | 106 | 83 | 15 | 18% |
| 12:30 | 217 | 463 | 353 | 74 | 21% |
| 13:04 | 247 | 473 | 371 | 102 | 27% |
| 13:45 | 81 | 119 | 89 | 22 | 25% |
| 14:05 | 271 | 316 | 242 | 82 | 34% |

### What's still needed

1. **Controlled ground-truth test** with known cotton positions to compute true
   precision/recall/F1 (requires labeled test setup)
2. **Compare stereo depth failure rate** with new configurable stereo params
   (5 params exposed since Feb)
3. **Assess workspace pre-filtering impact** — `cotton-detection-reliability` change
   should reduce wasted detections from 47.4% to lower
4. **Current draw profiling** during detection inference cycles

---

## A10: Arm Position Accuracy

**Benchmark objective:** Measure actual vs commanded position across workspace.

### What we have

#### Homing Accuracy (9 session startups)

| Metric | Value |
|--------|------:|
| Mean error | 0.0033 joint-units |
| Std dev | 0.0010 |
| Max | 0.0055 (89% margin to 0.050 tolerance) |
| Within tolerance | 9/9 (100%) |

#### Runtime Position Accuracy — Motor Level (mg6010 controller)

348 "Reached target" events, target=0.0 (home position):

| Metric | Value |
|--------|------:|
| Mean |error| | 0.0035 joint-units |
| Median | 0.0029 |
| P95 | 0.0119 |
| P99 | 0.0155 |
| Max | 0.0173 |
| Within 0.050 | 100.0% (348/348) |
| Within 0.010 | 93.4% (325/348) |
| Within 0.005 | 89.7% (312/348) |

#### Runtime Position Accuracy — Planner Level (yanthra_move)

629 "Service confirmed" events, various commanded positions:

| Metric | Value |
|--------|------:|
| Mean |error| | 0.0169 joint-units |
| Median | 0.0141 |
| P95 | 0.0381 |
| P99 | 0.0429 |
| Max | 0.0439 |
| Within 0.050 | 100.0% (629/629) |
| Mean response time | 496ms |
| P95 response time | 974ms |

The motor-level and planner-level differ because planner includes transmission/gear
effects and measures at various commanded positions, not just home.

#### Per-Session Position Error (mg6010 motor level)

| Session | n | Mean |error| | Max |error| |
|---------|--:|-------------:|-----------:|
| 12:10 | 18 | 0.0029 | 0.0078 |
| 12:30 | 95 | 0.0036 | 0.0173 |
| 13:04 | 97 | 0.0041 | 0.0169 |
| 13:45 | 28 | 0.0028 | 0.0069 |
| 14:05 | 110 | 0.0033 | 0.0140 |

#### Scan Position Yield Asymmetry

| Position | Yield | Notes |
|----------|------:|-------|
| -150mm | 39.5% | **Best** — 4.6x better than +150mm |
| +150mm | 8.5% | **Worst** |

### What's still needed

1. **Root-cause the 4.6x left-right asymmetry** — is it mounting offset, J3-related,
   or camera FOV bias?
2. **Convert joint-units to physical degrees** using transmission ratios (J3:
   transmission=1.0, internal_gear=6.0) for meaningful physical error bounds
3. **Position accuracy across full workspace** — Feb data is mostly near home
4. **Per-joint current draw** at different workspace positions
5. **Compare with position feedback** — blind sleeps replaced since Feb

---

## A11: Joint Timings

**Benchmark objective:** Measure full cycle time and plan improvements for 2-sec target.

### What we have

#### Pick Cycle Time (real picks only, excluding IK rejections)

315 successful pick cycles (100% of real motor cycles succeeded):

| Phase | Mean | Median | P95 | Max |
|-------|-----:|-------:|----:|----:|
| **Total cycle** | ~6,434ms | ~6,500ms | ~7,600ms | 8,041ms |
| Approach | 849ms* | — | — | — |
| Capture (EE) | 0ms** | — | — | — |
| Retreat | 862ms* | — | — | — |

*Approach/retreat averages from `--field-summary` are diluted by instant rejections
(0ms events). Real approach+retreat totals are ~3,100ms + ~3,200ms from text-log analysis.
**capture_ms was hardcoded to 0 in Feb software — now fixed for March.

**Phase proportions:** ~48% approach, ~19% capture (from text logs), ~49% retreat.

Note: approach + retreat > 100% because the text-log-extracted proportions overlap
with total_ms which includes additional overhead.

#### Per-Joint Approach Timing (from motor command logs)

The structured `j3_ms`/`j4_ms`/`j5_ms` fields in `pick_complete` events were hardcoded
to 0 in the Feb software (now fixed for March). However, the log analyzer extracts
per-joint approach timing from motor command timestamps:

| Joint | P50 | P95 | Max | Notes |
|-------|----:|----:|----:|-------|
| J3 | 816ms | 1,024ms | 1,129ms | |
| J4 | 818ms | 1,178ms | 1,329ms | |
| **J5+EE** | **1,170ms** | **1,363ms** | **1,460ms** | **Bottleneck** |

#### Per-Joint Retreat Timing

| Joint | P50 | Max | Notes |
|-------|----:|----:|-------|
| Compressor | 1,002ms | 1,015ms | |
| J3 | 1,261ms | 1,672ms | Slowest retreat joint |
| J4 | 0ms | 502ms | Minimal retreat movement |
| J5 | 1,116ms | 1,709ms | |

#### J5+EE Approach Breakdown

| Phase | P50 | P95 |
|-------|----:|----:|
| J5 travel | 1,069ms | 1,263ms |
| EE pre-travel (J5 move before EE ON) | 637ms | 836ms |
| EE overlap (EE ON while J5 moving) | 402ms | 602ms |
| EE dwell (at cotton before retreat) | 100ms | 101ms |

EE ON duration: p50 1,254ms, p95 1,460ms.

#### Aggregate Session Stats

| Metric | Value |
|--------|------:|
| Total pick events | 1,181 |
| Instant IK rejections (0-1ms) | 761 (64.4%) |
| Recovery rejections (~1,206ms) | 105 (8.9%) |
| Real motor cycles | 315 (26.7%) |
| Real pick success rate | **100%** (every real cycle succeeded) |
| Throughput (all events) | 426.3 picks/hr |
| Wasted detections | 79.6% |
| Stale picks (>2s detection age) | 19.6% (69 severely stale >10s) |
| EE retract distance | Near-zero — J5 may not be extending |
| EE compressor duty cycle | 3.6% |

#### Detection-to-Pick Timing

| Metric | Value |
|--------|------:|
| Detection age (mean) | — |
| NN inference | 47.7ms mean |
| Total detection processing | 65.3ms mean |

### What's still needed

1. **Per-joint timing from structured fields** — j3_ms, j4_ms, j5_ms now populated in
   March software (the above data was extracted from motor command timestamps, not the
   structured pick_complete fields)
2. **Compare total cycle with position feedback** — blind sleeps replaced, expect
   significant reduction from 6.4s
3. **Concrete improvement plan to hit 2-sec target** — which phases can be
   parallelized, shortened, or eliminated? J5+EE approach (1,170ms) and J3 retreat
   (1,261ms) are the top targets
4. **Current draw profiles** per joint per phase
5. **Assess impact of recent changes** — J4 parking optimization, serpentine scan,
   cotton eject sequence (adds time), workspace pre-filtering (reduces wasted cycles)

### Gap to Target

| Metric | Feb Actual | Target (PERF-ARM-001) | Gap |
|--------|--------:|------:|--------:|
| Pick cycle time | ~6,434ms | 2,000ms | **3.2x slower** |
| Pick throughput | 426/hr (all) | — | — |
| Detection latency | 65ms | — | Not a bottleneck |

---

## A12: J3 Position Precision Trend

**Benchmark objective:** Investigate degrading homing error. Mechanical wear or software drift?

### Resolution: No Degradation Detected

**Status: RESOLVED from Feb log analysis (Mar 17, 2026)**

| Metric | Value |
|--------|------:|
| Motor health score | **1.0 for all 300 samples** |
| Command success rate | 993/993 (100%) |
| Timeouts | 0 |
| TX failures | 0 |
| Error flags | 0 |

#### Temperature (stable)

| Stat | Value |
|------|------:|
| Mean | 44.2°C |
| Range | 39–47°C |
| Delta over session | -0.6°C (slight decrease) |

#### Position Error Trend (no upward trend)

| Session | n | Mean |error| | Max |error| |
|---------|--:|-------------:|-----------:|
| 12:10 | 18 | 0.0029 | 0.0078 |
| 12:30 | 95 | 0.0036 | 0.0173 |
| 13:04 | 97 | 0.0041 | 0.0169 |
| 13:45 | 28 | 0.0028 | 0.0069 |
| 14:05 | 110 | 0.0033 | 0.0140 |

No monotonic increase. The dominant error is +0.0029 (steady-state offset) with
occasional overshoot to -0.0173 that doesn't increase over time.

### What's still needed

- **March trial: extended-duration validation** — Feb was 2h46m. March target is
  5+ hours. If precision degrades over longer sessions, the mechanical wear
  hypothesis returns.

---

## A13: Pick Cycle Time Degradation

**Benchmark objective:** Investigate 21.8%/hour degradation root cause.

### Resolution: Statistical Artifact

**Status: RESOLVED (Mar 17, 2026). Log analyzer bug fixed.**

#### What the log analyzer reported

"Trend Alert: Cycle time increasing 21.8%/hour (from 1,610ms to 2,312ms)"

#### What actually happened

The analyzer computed average `total_ms` across **all** pick events, including
instant rejections:

| Hour | Total | Instant Rej (0-1ms) | Real Picks | Avg (ALL) | Avg (REAL) |
|------|------:|--------------------:|-----------:|----------:|-----------:|
| 0 | 479 | 323 (67.4%) | 109 (22.8%) | 1,610ms | 6,642ms |
| 1 | 460 | 300 (65.2%) | 124 (27.0%) | 1,729ms | 6,149ms |
| 2 | 242 | 138 (57.0%) | 82 (33.9%) | 2,312ms | 6,512ms |

The "degradation" was caused by the proportion of 0ms instant rejections
decreasing from 67.4% → 57.0%. Fewer zeros in the average → average goes up.

#### Proof: Real picks are flat

Linear regression on 315 real picks (total_ms > 1500ms):

| Metric | Slope | R² |
|--------|------:|---:|
| total_ms | +143.7 ms/hr (+2.8%/hr) | **0.002** |
| approach_ms | +83.1 ms/hr | ~0 |
| retreat_ms | +98.2 ms/hr | ~0 |

R² = 0.002 means the time trend explains 0.2% of variance. No degradation.

#### Supporting evidence

| Factor | Finding |
|--------|---------|
| J3 temperature | 43.8→45.0°C (+1.2°C) — within limits |
| J4/J5 temperature | Flat or decreasing |
| J3 current | +0.3% (noise) |
| Bus voltage | 57.3–57.5V (stable) |
| Health score | 1.0 for all joints, entire session |

#### Fix applied

`scripts/log_analyzer/reports/trends.py:_trend_pick_cycle_time` now filters out
picks with `total_ms <= 1` before computing the per-hour trend. This prevents
the false alarm from appearing in March field data.

4 regression tests added in `tests/test_reports.py::TestPickCycleTimeTrendFiltering`.

### What's still needed

- **March trial: confirm flat trend** with new software (position feedback, eject
  sequence, workspace filtering all modify cycle time composition)

---

## Summary Table

| Benchmark | Feb Baseline Available | Resolved? | Key Number | Gap to Close |
|-----------|:---------------------:|:---------:|------------|-------------|
| A9 | Proxy metrics only | No | 9.2% end-to-end conversion | Need ground-truth precision/recall/F1 |
| A10 | Position error data | No | 100% within 0.050 tolerance | Need asymmetry root-cause, physical units |
| A11 | Cycle time data | No | 6,434ms median (target: 2,000ms) | Need per-joint breakdown, improvement plan |
| A12 | **Full resolution** | **Yes** | No degradation (R²~0) | March validates over longer duration |
| A13 | **Full resolution** | **Yes** | Statistical artifact (R²=0.002) | Log analyzer fixed |

---

## How to Reproduce

Run the log analyzer on Feb collected logs:

```bash
# Full field summary
python3 scripts/log_analyzer/cli.py collected_logs/2026-02-26_16-24/target/ --field-summary

# Full analysis with issue detection
python3 scripts/log_analyzer/cli.py collected_logs/2026-02-26_16-24/target/ --analyze

# Compare with March data (after March trial)
python3 scripts/log_analyzer/cli.py collected_logs/2026-02-26_16-24/target/ --compare /path/to/march/logs/
```

---

## Comparison Framework for March

After March 25 field trial, run:

```bash
python3 scripts/log_analyzer/cli.py /path/to/march/logs/ --compare collected_logs/2026-02-26_16-24/target/
```

This will produce a side-by-side comparison of pick performance, motor health,
and detection metrics with computed deltas.

The web dashboard also supports comparison:
`GET /api/analysis/compare?a=<feb_id>&b=<march_id>`

Key metrics to compare Feb → March:

| Metric | Feb Baseline | March Target | What Changed |
|--------|-------------|-------------|-------------|
| Pick success rate | 26.7% | >60% | Workspace filtering, L3 offset, tuning |
| Real pick cycle time | ~6,434ms | <2,000ms | Position feedback (replaces blind sleep) |
| Stereo depth failure rate | 14.6% | <5% | Configurable stereo params |
| Workspace violation rate | 64.4% | <30% | Workspace pre-filtering in detection |
| J5+EE approach (p50) | 1,170ms | <500ms | Position feedback, parallelization |
| J3 retreat (p50) | 1,261ms | <400ms | Position feedback |
| Per-joint timing (structured) | Hardcoded 0 | Available | j3/j4/j5_ms logging fixed |
| End-to-end conversion | 9.2% | >20% | All above combined |
