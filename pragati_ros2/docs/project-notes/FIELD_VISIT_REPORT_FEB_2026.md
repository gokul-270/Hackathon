# Field Visit Report - February 2026

**Visit Date:** February 26, 2026
**Location:** Field Site
**Code Version:** Feb 25 build, commit `fcadd3b3` (whitespace fix only, no new features vs previous build)
**Test Mode:** Stop-and-pick (drive to spot, stop, arm picks, drive to next)
**Duration:** ~12:00-16:30 IST (RPi log timestamps 12:01-15:10, clocks drifted ~1.5h behind due to morning-only NTP sync, no internet at field)
**Rows Tested:** 1-2 cotton rows
**Analysis Method:** `scripts/log_analyzer.py` (automated) + manual log review + team field observations

---

## Executive Summary

### Key Findings
| System | Status | Issues |
|--------|--------|--------|
| **Vehicle (ODrive drive)** | ⚠️ UNSTABLE | Massive stall errors, 9 crashes, intermittent driving |
| **Vehicle (MG6012-i6 steering)** | ⚠️ DEGRADED | ALL 3 motors error code 8, peaks 73-80C |
| **Arm1 pick system** | ✅ OPERATIONAL | 151 cycles, 1,181 attempts, 315 picks |
| **Arm1 detection** | ✅ WORKING | 1,528 accepted detections, 34-93ms avg latency |
| **Arm1 mechanical** | ⚠️ ISSUES | J5 belt broken (field-repaired), L5 home offset, L3 FOV blocking |
| **End effector** | ⚠️ RUNAWAY | EE ran continuously once, required shutdown topic to stop |
| **MQTT communication** | ✅ SOLID | Vehicle: 97.7% uptime; Arm: 2 disconnects but both explained (see 2.10) |
| **Arm2** | ❌ NOT TESTED | Hardware unavailable |

### Critical Issue: Workspace Reachability + Calibration Errors
**Root Cause (Revised):** Combination of (1) cotton plant growth since January, (2) possible J3 offset error causing arm to reach below target positions, and (3) vehicle unable to position close enough due to ODrive stalls.
**Impact:** 73% of pick attempts (841/1,181) rejected as workspace violations. Pick success rate dropped from 85% (Jan) to 26.7%.
**Important:** The J3 offset error (arm going below cotton position, observed visually in field) may be a significant contributor — not just plant growth. Needs workshop verification.

### Critical Issue: ODrive Drive Motor Stalls
**Root Cause:** Stall detection thresholds not calibrated for field terrain conditions.
**Impact:** All 3 drive motors stall continuously (1,000-1,800+ error events/session). Vehicle crashed 9 times. drive_left_back physically stuck in some sessions.
**Action Required:** ODrive stall threshold tuning + field-specific configuration.

---

## 1. Vehicle System Analysis

### 1.1 Overview
- **Hostname:** pragati11, **IP:** 192.168.1.100, **Role:** vehicle
- **ROS2 sessions:** 9 (all restarts due to ODrive errors causing crashes)
- **Nodes:** mg6010_controller_node (3 steering MG6012-i6 CAN motors), odrive_service_node (3 ODrive drive motors), vehicle_mqtt_bridge (python3), vehicle_control_node (python3)
- **START button presses:** ~158 across all sessions

### 1.2 Provisioning
- **Result:** FAILED 11/12 steps
- **Detail:** Provision step failure details not captured (log records "FAILED 1 step", not which step)
- **Provision log:** `collected_logs/2026-02-26_16-21/target/provision_logs/provision_20260226_114920.log`

### 1.3 ODrive Drive Motors (CRITICAL)

All 3 ODrive drive motors (front, left_back, right_back) show persistent stall detection across ALL 9 sessions.

| Motor | Error Codes | Pattern | Events/Session |
|-------|-------------|---------|----------------|
| drive_front | 0x04000000 / 0x00000100 | Stall -> recovery -> CLOSED_LOOP -> re-stall | 1,000-1,800+ |
| drive_left_back | 0x04000000 / 0x00000100 | Same + position_change=0.000m (physically stuck) | 1,000-1,800+ |
| drive_right_back | 0x04000000 / 0x00000100 | Same | 1,000-1,800+ |

**Behaviour:** Auto-recovery triggers -> motor enters CLOSED_LOOP -> immediately re-stalls. Vehicle was still able to drive intermittently between stalls but crashed 9 times total.

**Detailed error counts (from log analyzer):**
- ODrive ERROR events: 1,183
- Communication timeouts (position wait): 2,177
- Fallback to position tolerance mode: 146 events (drive_left_back traj_done stuck)
- Drive stop service call timeouts: 29
- Log gaps >30s: 72 (largest gap: 465s)

**Note:** This is the first field trial with ODrive motors (replaced burnt MG6012 motors from January). Possible causes:
- Incorrect stall detection thresholds for field terrain
- Mechanical load higher than expected on uneven ground
- ODrive configuration needs field-specific tuning
- Physical obstruction or binding on drive_left_back specifically

### 1.4 MG6012-i6 Steering Motors

| Motor | CAN ID | Init | Homing | Health | Avg Temp | Peak Temp | Error Flags | Issues |
|-------|--------|------|--------|--------|----------|-----------|-------------|--------|
| steering_front | 0x1 | ✅ | ✅ | 1.0 | 38.3C | 80C | 0x8 | Thermal + error code 8 |
| steering_left | 0x3 | ✅ | ✅ | 0.6 | 37.0C | 80C | 0x8 | Thermal + error code 8, sluggish, 26.7% timeout rate |
| steering_right | 0x5 | ✅ | ✅ | 1.0 | 38.8C | 73C | 0x8 | Thermal |

**All 3 steering motors** had error code 0x8 and exceeded thermal thresholds (>55C). steering_left was worst with 26.7% command timeout rate, health dropped to 0.6, and current draw increased 3,318% over the session (0.002A early to 0.079A late).

**Motor current spikes detected** (analyzer):
| Motor | Mean Current | Max Current | Spikes (>2.5x mean) | Health |
|-------|-------------|-------------|---------------------|--------|
| steering_front | 0.093A | 5.672A | 27 | ALERT |
| steering_left | 0.040A | 4.044A | 39 | ALERT |
| steering_right | -0.127A | 4.044A | 4 | ALERT |

All steering motors initialized and homed successfully on each launch.

### 1.5 CAN Interface
- Setup failed on every launch: `RTNETLINK answers: Operation not supported`
- CAN was already up from previous session/watchdog, so operations continued normally

### 1.6 Self-Test Results
- Passed 4/5 tests
- Joint states WAITING at startup (normal behaviour)

### 1.7 What Worked Well
- MQTT communication chain rock solid (vehicle -> MQTT -> arm)
- Signal chain logging (`[SIGNAL_CHAIN]`) present and useful for debugging
- vehicle_mqtt_bridge healthy throughout all 9 sessions
- GPIO manager, motor services, configuration all passed self-tests
- Mosquitto broker active and healthy

### 1.8 MQTT Bridge
- **Log files:** 10
- **MQTT uptime:** 97.7%
- **Connects:** 10
- **Disconnects:** 9 (1 unexpected — keepalive timeout/network failure)
- **MTBF:** 2,609s between failures
- **Publish failures:** 0
- **Arm status messages received:** 931

| Arm Status | Count |
|------------|-------|
| ready | 498 |
| busy | 264 |
| ACK | 151 |
| UNINITIALISED | 9 |
| offline | 9 |

---

## 2. Arm1 System Analysis

### 2.1 Overview
- **Hostname:** ubuntu-desktop, **IP:** 192.168.1.102, **Role:** arm
- **ROS2 sessions:** 9 (6 with operational cycles, 3 startup-only)
- **Field trial sessions:** 6

### 2.2 Provisioning
- **Result:** FAILED 8/9 steps
- **Provision log:** `collected_logs/2026-02-26_16-24/target/provision_logs/provision_20260226_115932.log`

### 2.3 Session Breakdown

Log timestamps are ~1.5h behind real time due to RTC drift.

| Session | Log Time | Cycles | Log Lines | Notes |
|---------|----------|--------|-----------|-------|
| 1 | 12:01 | 6 | 2,638 | Initial testing |
| 2 | 12:10 | 9 | 3,939 | |
| 3 | 12:22 | 0 | 213 | Startup only |
| 4 | 12:27 | 0 | 158 | Startup only |
| 5 | 12:30 | 36 | 15,885 | Heavy use |
| 6 | 13:04 | 41 | 17,846 | Heaviest session |
| 7 | 13:45 | 14 | 5,034 | |
| 8 | 14:02 | 0 | 144 | Startup only |
| 9 | 14:05 | 45 | 15,453 | Most cycles |

### 2.4 Pick Performance

| Metric | Value |
|--------|-------|
| Operational cycles | 151 |
| Total pick attempts | 1,181 |
| Successful picks | 315 |
| **Pick success rate** | **26.7%** |
| Failed picks | 866 |
| Eject operations | 314 (matches successes) |
| Dynamic EE activations | 315 |
| Approach trajectories | 1,181 |

### 2.5 Failure Breakdown

| Failure Type | Count | % of Failures |
|-------------|-------|---------------|
| **Workspace violations (total)** | **841** | **97.1%** |
| - TOO FAR from base | 460 | 53.1% |
| - Too far RIGHT (Y+) | 286 | 33.0% |
| - Too far LEFT (Y-) | 62 | 7.2% |
| - Angle too negative | ~33 | ~3.8% |
| - TOO CLOSE | 1 | 0.1% |
| Other failures | ~25 | ~2.9% |

The median approach time of 1ms and median EE activation of 0ms for many "attempts" confirms that most failures were instant workspace rejections -- detected, coordinates computed, found out of bounds, rejected immediately without moving the arm.

### 2.6 Detection Performance

| Metric | Value |
|--------|-------|
| Detection stat blocks (30s intervals) | 310 |
| Raw detections | 2,938 |
| Accepted detections | 1,544 |
| Acceptance rate | 52.6% |
| Border filtered | 453 (5.3%) |
| Not pickable (label=1) | 919 (9.3%) |
| **Zero spatial coordinates** | **503** |
| Camera temp range | 51.1-63.0C (mean 60.1C, rate +0.02C/min) |
| Time to critical (85C) | 1,258 min (~21 hours) |
| Detection latency avg | 34-93ms (varies by session) |
| Detection latency max | 333.8ms |
| XLink errors | 0 |
| USB reconnects | 0 |
| USB speed | 3.0 (5Gbps) consistent |
| Stale frames flushed/request | 6.0 avg |
| Frame wait time | 47.5ms avg |
| Wasted detections | 79.6% (1,229/1,544 accepted did not lead to successful pick) |

**Zero coordinate issue:** 503 zero spatial coordinate events (17% of raw detections). The `std::optional` fix in `convertDetection()` is deployed and filtering these: 503 caught at detection level, 237 reached yanthra_move (also filtered there). Rate is significantly higher than January (3-5%). Warrants investigation into camera calibration drift or changed plant background conditions.

### 2.7 Pick Timing

| Metric | Value |
|--------|-------|
| cycle_ms avg | 1,800ms |
| cycle_ms p50 | 1ms (instant workspace rejections) |
| cycle_ms p95 | 7,263ms |
| cycle_ms max | 8,041ms |
| approach_ms avg | 849ms |
| retreat_ms avg | 862ms |
| ee_on_ms p50 | 1,254ms |
| ee_on_ms p95 | 1,460ms |
| total_ms avg per pick | 2,589ms |
| total_ms max | 38,739ms |
| detection_age_ms avg | 1,076ms |
| detection_age_ms max | 19,572ms |
| Stale detections (>2s age) | 232 (19.6%) |
| Severely stale (>10s age) | 69 |
| Wasted detections | 79.6% (accepted but no successful pick) |

### 2.8 J4 Multi-Position Scanning

- **Active** with 5 positions: -150mm, -75mm, 0mm, +75mm, +150mm
- **Strategy:** left_to_right
- **Position scan markers:** 755
- Despite scanning, cotton was beyond arm's maximum radial reach

### 2.9 Motor Health

| Joint | Avg Temp | Max Temp | Voltage | Mean Current | Max Current | Health | Spikes |
|-------|----------|----------|---------|-------------|-------------|--------|--------|
| joint3 | 44.2C | 47C | 56.2V | 1.502A | 3.674A | 100% | 5 (ALERT) |
| joint4 | 41.0C | 42C | 55.7V | -0.026A | 0.500A | 100% | 32 (ALERT) |
| joint5 | 41.0C | 42C | 56.2V | 0.085A | 0.918A | 100% | 49 (ALERT) |

- CAN bus: 0 errors, 0 drops, 0 collisions (~5K packets/min)
- No motor control errors in any session
- **J5 current spikes** (49 events) are consistent with belt damage causing irregular mechanical load
- **J4 current spikes** (32 events) warrant investigation — may indicate intermittent binding

### 2.10 ARM_client / MQTT Communication

- All 9 log files show healthy MQTT connection to broker at 192.168.1.100:1883
- Connection succeeded on attempt 1 every time
- **2 unexpected MQTT disconnects** (keepalive timeout/network failure) — auto-reconnected
- Status flow: `UNINITIALISED -> ready -> start_switch -> ACK -> busy -> ready`
- One sequence gap detected (seq expected=25, received=1, missed=-24) indicating vehicle-side restart
- Multiple silence watchdog warnings (120s without start_switch) — normal during vehicle idle/drive periods
- **126 service discovery timeouts** (arm_status service not found)
- **7 service failure diagnostics** (service not in ROS2 graph — 5 consecutive failures, 45.6s since last success)
- **4 rcl context invalid errors** (ROS2 node context crashed)
- A few unexpected arm crashes occurred (ROS2 launch crashes, not MQTT issues)

**Arm state time (from analyzer):**
| State | Duration |
|-------|----------|
| ready | 6,160s (102 min) |
| busy | 3,383s (56 min) |

### 2.11 Images Captured

| Type | Count |
|------|-------|
| Input images | 904 |
| Output (detected) images | 804 |
| Difference | 100 (frames with no detections) |

### 2.12 Throughput Analysis (from log analyzer)

| Metric | Value |
|--------|-------|
| Overall throughput | 426.3 picks/hour |
| Peak 5-min window | 1,272 picks/hour |
| Lowest 5-min window | 24 picks/hour |
| EE duty cycle | 3.6% |
| Pick cycle time trend | Increasing 21.8%/hour (1,610ms -> 2,312ms) |

**Hourly breakdown:**
| Hour | Picks | Successes | Success Rate | Avg Cycle |
|------|-------|-----------|-------------|-----------|
| 0 | 479 | 109 | 22.8% | 1,610ms |
| 1 | 460 | 124 | 27.0% | 1,729ms |
| 2 | 242 | 82 | 33.9% | 2,312ms |

**Trend:** Pick success rate improved over the session (23.1% first quarter -> 32.2% last quarter), while cycle time increased. Possible explanation: as session progressed, vehicle positioned better or operator learned better patterns, but motor/system degradation slowed cycle times.

### 2.13 J4 Scan Position Effectiveness (from log analyzer)

| J4 Offset | Scans | Found | Picked | Yield |
|-----------|-------|-------|--------|-------|
| -150mm | 151 | 347 | 137 | 39.5% |
| -75mm | 151 | 249 | 82 | 32.9% |
| 0mm | 151 | 252 | 63 | 25.0% |
| +75mm | 151 | 191 | 21 | 11.0% |
| +150mm | 151 | 142 | 12 | 8.5% |
| **Best:** -150mm | | | | **39.5%** |
| **Worst:** +150mm | | | | **8.5%** |

Strong left-bias in pick success (4.6x yield difference between -150mm and +150mm). This could indicate: asymmetric mounting, J3 offset affecting one side more, or plant geometry favoring one direction.

### 2.14 Per-Joint Timing Analysis (from log analyzer)

**Approach timing:**
| Joint | p50 | p95 | max | Note |
|-------|-----|-----|-----|------|
| J3 | 816ms | 1,024ms | 1,129ms | |
| J4 | 818ms | 1,178ms | 1,329ms | |
| J5+EE | 1,170ms | 1,363ms | 1,460ms | **Bottleneck** |

**J5+EE breakdown:**
| Phase | p50 | p95 |
|-------|-----|-----|
| J5 travel | 1,069ms | 1,263ms |
| EE pre-travel (J5 before EE ON) | 637ms | 836ms |
| EE overlap (EE ON while J5 moving) | 402ms | 602ms |
| EE dwell (at cotton before retreat) | 100ms | 101ms |

**Retreat timing:**
| Phase | p50 | max |
|-------|-----|-----|
| Compressor | 1,002ms | 1,015ms |
| J3 | 1,261ms | 1,672ms |
| J5 | 1,116ms | 1,709ms |

**EE retract distance: near-zero for all picks** — confirms J5 was not extending properly (consistent with J5 belt breakage observation).

### 2.15 Motor Position Trending (from log analyzer)

| Joint | Events | Mean Error | Max Error | StdDev | Trend |
|-------|--------|-----------|-----------|--------|-------|
| joint3 | 9 | 0.0033 | 0.0055 | 0.0010 | ↑ degrading |
| joint4 | 9 | 0.0000 | 0.0001 | 0.0000 | ↑ degrading |
| joint5 | 6 | 0.0000 | 0.0000 | 0.0000 | ↔ stable |

**J3 position precision is degrading** — mean homing error of 0.0033 with max 0.0055. This is consistent with the team's field observation that J3 offset may be wrong.

### 2.16 Motor Current Draw (from log analyzer)

| Joint | Samples | Mean | Max | StdDev | Spikes | Health |
|-------|---------|------|-----|--------|--------|--------|
| joint3 | 300 | 1.502A | 3.674A | 0.659 | 5 | ALERT |
| joint4 | 300 | -0.026A | 0.500A | 0.183 | 32 | ALERT |
| joint5 | 300 | 0.085A | 0.918A | 0.268 | 49 | ALERT |

J4 and J5 have frequent current spikes relative to their mean — J5 with 49 spikes is noteworthy given the belt breakage.

### 2.17 Joint Limit Violations (from log analyzer)

| Category | Count |
|----------|-------|
| Total violations | 809 (68.5% of picks) |
| Joint4 violations | 348 |
| Joint5 violations | 461 |
| By direction: extension | 461 |
| By direction: left | 62 |
| By direction: right | 286 |
| Max overshoot | 1.272m |

### 2.18 Detection Quality (from log analyzer)

| Metric | Value |
|--------|-------|
| Total requests | 911 |
| Total raw detections | 2,938 |
| Total accepted | 1,544 |
| Acceptance rate | 52.6% |
| Border skip rate | 5.3% |
| Not-pickable rate | 9.3% |
| Avg stale frames flushed/request | 6.0 |
| Avg frame wait | 47.5ms |
| Model file | Fallback default (yolov112.blob not found on RPi, 9 occurrences) |

### 2.19 Instrumentation Gaps (from log analyzer)

| Gap | Detail |
|-----|--------|
| **JSON pick timing zeroed** | All 1,181 pick_complete JSON events report j3_ms=0, j4_ms=0, j5_ms=0, but text [TIMING] logs show non-zero values. JSON timing fields not being populated. |
| **100% zero capture time** | All picks report capture_ms=0. Compressor/vacuum capture phase not instrumented. |
| **ArUco detection** | Not instrumented (Gap 20) |
| **Position tracking** | Not instrumented (Gap 22) |

---

## 3. Comparison: January 2026 vs February 2026

| Metric | Jan 2026 (Left Arm) | Feb 2026 (Arm1) | Trend |
|--------|---------------------|-----------------|-------|
| Sessions with picks | 34 | 6 active sessions | |
| Total pick attempts | 766 | 1,181 | +54% |
| Pick success rate | 85% | 26.7% | ⬇️ Workspace-limited |
| Throughput | Unknown | 426 picks/hr (peak 1,272) | |
| Workspace violations | 10% | 68.5% (809) | ⬆️ J3 offset + plant growth |
| [0,0,0] detection bug | 3% (30) | ~17% (503 zero spatials) | ⬆️ L3 blocking + depth |
| Detection acceptance rate | Unknown | 52.6% (1,544/2,938) | |
| Wasted detections | Unknown | 79.6% | |
| Border skip | 57 | 453 | ⬆️ |
| Camera temp range | 45-61C | 51-63C (mean 60.1C) | Slightly higher |
| Detection latency p50 | 69ms | 34-93ms avg | Comparable |
| ARM_client crashes | Unknown (no logs) | 4 rcl context errors | Now captured |
| Service timeouts | Unknown | 126 discovery + 7 failures | Now captured |
| MQTT (vehicle) | Untested/broken | 97.7% uptime, 1 unexpected disconnect | ✅ Working |
| MQTT (arm) | Unknown | 2 unexpected disconnects | Mostly stable |
| Vehicle drive motors | 3 MG6012 drive motors burnt (3/3 dead; 3 MG6012-i6 steering motors were fine) | ODrive stalling (1,183 errors) | ⚠️ Different failure mode |
| Vehicle steering motors | Unknown | ALL 3 error code 8, 73-80C peaks | ⚠️ Thermal |
| Arm motor current spikes | Unknown | J3:5, J4:32, J5:49 | Now monitored |
| Arms tested | 2 (left + right) | 1 (arm2 hardware unavailable) | |
| Data quality | Missing ARM_client/system/network logs | Comprehensive capture | ✅ Major improvement |

---

## 4. Root Cause Analysis

### 4.1 Why 26.7% Success Rate (vs 85% in January)?

**Primary causes (revised after field team debrief):**
1. **J3 offset likely wrong:** Team observed the arm consistently reaching below the cotton position. A systematic J3 offset error shifts the entire workspace envelope downward, causing targets to appear "too far" when they may actually be reachable with correct calibration. **Needs workshop verification — software offset vs mechanical home.**
2. **Cotton plant growth:** Bolls at greater heights and distances than January.
3. **Vehicle positioning:** ODrive stall errors prevented reliable close positioning to cotton rows.

**Contributing factors:**
1. **L3 not returning home during multi-scan (intermittent):** L3 stayed extended after a pick, blocking the camera FOV. This caused detection failures in subsequent scan positions — the camera sees the arm instead of cotton. Partially explains the 17% zero-coordinate detection spike.
2. **Row geometry:** Vehicle couldn't get close enough even when driving was working.
3. **J5 belt broken / L5 home offset:** J5 came out of home position due to broken belt. Field-repaired by cutting damaged portion, but still had issues after fix. L5 was slightly forward of true home/0 position. Both affect end-effector positioning accuracy.
4. **Combined effect:** 460 attempts failed as "TOO FAR" (beyond reach), 286 as "too far RIGHT", 62 as "too far LEFT"

### 4.2 Zero Coordinate Issue ([0,0,0])

503 zero spatial coordinate events in detection (17% of raw detections). The `std::optional` fix in `convertDetection()` is deployed (part of the active build), so these are being filtered correctly. However, the rate is significantly higher than January (3-5%).

**Revised analysis:** L3 intermittently not returning to home during multi-scan likely contributed to this spike. When L3 stays extended, it blocks the camera FOV — stereo depth returns zeros because it sees the arm, not a cotton boll at distance. This is distinct from the DepthAI textureless-surface failure.

Morning had normal lighting, afternoon slightly cloudy — not extreme glare. Investigation should separate L3-blocking cases from genuine depth failures.

### 4.3 ODrive Motor Stalls

All 3 ODrive drive motors show persistent stall detection with error codes `0x04000000` and `0x00000100`. The system attempts auto-recovery but motors re-stall immediately. This is the first field trial with ODrive motors (replaced burnt MG6012 motors from January).

Possible causes:
- Incorrect stall detection thresholds for field terrain
- Mechanical load higher than expected on uneven ground
- ODrive configuration needs field-specific tuning
- Physical obstruction or binding on drive_left_back specifically

---

## 5. Issues Identified

### 5.1 Critical Issues
| Issue | Impact | Priority |
|-------|--------|----------|
| **ODrive stall loop** | Vehicle crashes 9 times, intermittent driving | CRITICAL |
| **J3 offset error** | Arm reaching below target; major contributor to 73% workspace violations | CRITICAL |
| **L3 not returning home (multi-scan)** | Blocks camera FOV intermittently, causing detection failures | CRITICAL |
| **EE runaway (ran continuously)** | Safety hazard; required shutdown topic to stop, restart didn't help | CRITICAL |

### 5.2 High Priority Issues
| Issue | Impact | Priority |
|-------|--------|----------|
| **J5 belt broken** | J5 out of home position; field-repaired but still had issues | HIGH |
| **L5 home offset** | L5 not reaching full 0 position, affects reach accuracy | HIGH |
| **Arm reach vs plant height** | 73% workspace violations (partially J3, partially plant growth) | HIGH |
| **Zero coordinate rate 17%** | Higher than Jan (3%); partially L3 blocking, partially depth failure | HIGH |
| **Drop/throw inconsistency** | Cotton overshooting and undershooting collection box (both directions) | HIGH |
| **Arm targeting leaves** | Detection or depth resolving on leaves instead of cotton bolls | HIGH |
| **steering_left error code 8** | ALL 3 steering motors have error code 8; steering_left worst: 26.7% timeout, health 0.6 | HIGH |
| **Provision failures** | Vehicle 11/12, Arm 8/9 steps failed | HIGH |
| **RTC drift ~1.5h** | Log timestamps unreliable | HIGH |
| **Arm2 hardware** | Cannot test 2-arm operation | HIGH |
| **L5 depth control** | L5 sometimes going too deep (possible collisions with plants) | HIGH |

### 5.3 Medium Priority Issues
| Issue | Detail |
|-------|--------|
| **Vehicle movement not smooth** | Even when driving, motion was jerky/uneven |
| **Arm crashes (ROS2 launch)** | A few unexpected crashes during sessions (not MQTT) |
| **Collection box hit by arm** | L5 struck collection box when extended (before belt fix) |

### 5.4 Instrumentation Issues (from log analyzer)
| Issue | Detail |
|-------|--------|
| JSON pick timing zeroed | j3_ms/j4_ms/j5_ms=0 in all JSON events but non-zero in text [TIMING] logs |
| 100% zero capture time | capture_ms=0 for all picks — compressor/vacuum not instrumented |
| Model file not found | yolov112.blob missing on RPi — falling back to default model every session (9x) |
| ArUco detection gap | Not instrumented (Gap 20) |
| Position tracking gap | Not instrumented (Gap 22) |

### 5.5 Observations
| Issue | Detail |
|-------|--------|
| 126 service discovery timeouts | arm_status service not found in ROS2 graph (arm side) |
| 4 rcl context invalid errors | ARM_client ROS2 node context crashed |
| 29 drive stop service timeouts | Vehicle control couldn't call drive stop service |
| J3 position degrading | Mean homing error 0.0033, trending upward |
| J5 current spikes | 49 spikes (>2.5x mean) — belt damage causing irregular load |
| Pick cycle time increasing | 21.8%/hour degradation (1,610ms -> 2,312ms) |
| CAN interface setup error | `RTNETLINK answers: Operation not supported` on every launch (non-blocking) |
| Stale detections | 232 picks attempted on detections >2s old (19.6% stale rate) |
| 69 severely stale picks | Detection age >10s |
| Network monitor empty | Monitor running but no data rows collected (headers only) |
| ARM_client memory growth | Slight growth 73-77MB across sessions |
| 104 consecutive failure chains | 3+ consecutive pick failures (workspace rejections) |

---

## 6. Key Decisions Needed

1. **J3 offset verification:** Is this a software calibration offset or mechanical home position error? Workshop test needed before next field visit.
2. **L3 multi-scan return logic:** Why does L3 intermittently fail to return to home between scan positions? Code investigation needed.
3. **EE safety watchdog:** End effector ran continuously and didn't stop on service restart. Need a hardware or software watchdog/timeout to prevent runaway EE.
4. **ODrive tuning:** Stall detection thresholds need calibration for field conditions. Current auto-recovery + re-stall loop is not viable.
5. **J5 belt repair:** Belt was field-fixed but still had issues. Proper replacement or tensioning needed in workshop.
6. **L5 home calibration:** L5 not reaching full 0 position — recalibrate after J5 belt is properly fixed.
7. **Drop trajectory tuning:** Cotton missing collection box in both directions. Need consistent throw angle/velocity.
8. **Depth inconsistency / L5 depth control:** L5 going too deep on some picks. Need to investigate depth estimation to L5 travel mapping.
9. **Detection filtering:** Arm occasionally targeting leaves instead of cotton — model retraining or depth-based filtering needed.
10. **Arm reach strategy:** For remaining workspace violations after J3 fix. Options:
    - Better vehicle positioning (once ODrive is fixed)
    - Longer arm linkage (hardware change)
    - Camera tilt adjustment to detect closer cotton preferentially
    - Planting row spacing that matches arm reach
11. **steering_left motor:** Error code 8 investigation — may need replacement or repair, temperature management
12. **Provision failures:** Need to identify which specific steps failed on both RPis and fix
13. **Time sync:** RTC drift is a recurring issue. RPi needs internet or hardware RTC fix for field conditions
14. **Arm2 hardware:** Need to get arm2 operational for 2-arm testing
15. **L3 weight re-tuning:** L3 motor PID/position control needs re-tuning after EE mechanical changes altered payload weight. Position accuracy test needed. Owner: Arul.
16. **YOLOX migration + 3-class model:** Migrate detection model from YOLOv11 to YOLOX (licensing concerns) and add sun_glare as 3rd class (cotton, not-pickable, sun_glare). Requires collecting sun glare training images.
17. **Drive motor temperature monitoring:** ODrive drive motors lack temperature sensors. Add as hardware gap — thermal state is completely unmonitored unlike steering motors.
18. **Encoder configuration audit:** Verify encoder setup for both MG6012-i6 steering and ODrive drive motors — single vs dual channel, Channel A & B reading, quadrature decoding correctness.
19. **Pose estimation research:** Explore 3D pose estimation of cotton bolls for optimized approach angles. Future research item.
20. **Image saving optimization:** Evaluate saving input images only with detection metadata for post-hoc overlay, to reduce disk usage when scaling to multi-arm operation. Low priority — current disk impact is minimal.
21. **Collection box stabilization:** Fix collection box swinging during operation (rigid mounting or damping). Current dimensions: wheel 250mm, box width 180mm. Mech team to propose redesign.
22. **Arm profile / shrouding:** Address arm backside catching on plants in dense rows. Consider streamlined arm profile or protective shrouding.
23. **EE roller seed jamming:** Investigate cotton seed jamming in roller mechanism (pin size ~13mm). Assess if pin spacing needs modification for seed clearance.
24. **Small boll handling:** Address combined detection + mechanical limitation for small cotton bolls. Model needs size-based pickability; EE design may need modification for smaller bolls.

---

## 7. Data Collection Assessment

### 7.1 Significantly Improved Over January

| Data Category | Jan 2026 | Feb 2026 |
|---------------|----------|----------|
| ARM_client MQTT logs | MISSING | ✅ Captured |
| System logs | Partial | ✅ Captured via field_trial_logging.sh |
| Process memory | Not captured | ✅ Captured (73-77MB ARM_client) |
| CAN statistics | Not captured | ✅ Captured (0 errors) |
| Disk monitoring | Not captured | ✅ Captured (58GB, 39-40% used, stable) |
| Detection images | 230 (left arm) | 1,708 (904 input + 804 output) |

### 7.2 Still Missing or Incomplete

- Network monitor data rows empty (monitor running but no data collected)
- No pressure/compressor logs
- Provision step failure details (just "FAILED 1 step", not which step)
- JSON pick timing fields zeroed (j3_ms/j4_ms/j5_ms=0 despite text logs showing values)
- Capture phase (capture_ms) always 0 — not instrumented
- Model file yolov112.blob not deployed to RPi (using fallback model)

---

## 8. Lessons Learned

### 8.1 Vehicle Positioning is Critical
With working motors, vehicle positioning relative to cotton rows directly determines pick success. The arm's 670mm reach requires the vehicle to be within ~0.5m of targets. ODrive reliability must be solved before arm performance can be meaningfully evaluated.

### 8.2 Plant Growth Must Be Tracked
Cotton plant dimensions change between visits. Future visits should measure and record plant height and row-to-row distance to predict workspace viability before testing.

### 8.3 Provisioning Needs Offline Resilience
Both RPis failed most provision steps, likely because provision scripts assume network/internet access. Field site has no internet. Provision scripts should be validated for offline operation.

### 8.4 RTC Drift is a Recurring Problem
RPi has no hardware RTC. NTP sync only worked in the morning (before leaving for field). By afternoon, clocks had drifted ~1.5h. Either install a hardware RTC module or implement peer-to-peer time sync between RPis.

### 8.5 Mechanical Failures Compound Software Issues
J5 belt breakage and L5 home offset cascaded into positioning errors that look like software failures in the logs. Future field visits should include a pre-test mechanical checklist (belt tension, home positions, collection box clearance).

### 8.6 EE Safety Needs a Watchdog
End effector running continuously is a safety hazard (can damage motors, plants, or collection box). A timeout/watchdog is needed at both software and ideally hardware level.

### 8.7 L3 Return-to-Home is Critical for Multi-Scan
When L3 doesn't return to home between scan positions, the camera FOV is blocked, invalidating detections for remaining positions. This single bug may account for a significant portion of the zero-coordinate detection spike.

### 8.8 Row Spacing Constrains Both Vehicle and Arm

Measured field row spacing of 2.75 feet (~0.84m) is tight for vehicle passage and arm operation. Arm backside getting caught in plants and collection box swinging are symptoms of operating in dense rows. Future field trials should measure row spacing before testing, and arm/vehicle envelope should be validated against actual row geometry.

### 8.9 Arm Reachability is a Compound Problem

The 73% workspace violation rate is driven by the combination of: arm mounting height, arm linkage length, and vehicle positioning distance. Solving only the J3 calibration offset will improve but not eliminate the reachability gap. System-level workspace analysis considering all three factors is needed before the next field trial.

---

## 9. Team Field Observations (Post-Log Debrief)

The following issues were observed by the field team but are not fully captured in log data. Recorded during post-visit debrief on Feb 26, 2026. Additional observations may be added after the Feb 27 team review session.

### 9.1 Mechanical / Hardware Issues

| # | Issue | Severity | Detail | Resolution |
|---|-------|----------|--------|------------|
| H1 | **J5 belt broken** | Critical | J5 came out of home position. After opening, belt was found broken. | Field-repaired by cutting damaged portion. Still had issues after fix. Proper repair needed in workshop. |
| H2 | **L5 not reaching full home** | High | L5 was slightly forward of 0/home position, not fully retracting. | Related to belt damage or L5 mechanism. Needs recalibration after J5 belt is properly fixed. |
| H3 | **Collection box hit by arm** | High | When L5 was extended (before belt fix in morning), arm struck the collection box/provision. | Safety concern. Box positioning or arm limits need adjustment. |

### 9.2 Calibration / Software Issues

| # | Issue | Severity | Detail |
|---|-------|----------|--------|
| S1 | **J3 offset likely wrong** | Critical | Arm consistently going below cotton position. Multiple team members observed this. Cause TBD: software calibration offset vs mechanical home position error. Workshop verification needed. |
| S2 | **Depth inconsistent / L5 going too deep** | High | L5 sometimes extending too far into the plant on approach. Unclear if specific to certain plant sizes or random. May be depth estimation error or L5 travel mapping issue. |
| S3 | **Arm targeting leaves instead of cotton** | Medium | Detection or depth occasionally resolving on leaves rather than cotton bolls. Could be model confidence issue or depth ambiguity between overlapping leaves and bolls. |
| S4 | **L3 not returning home during multi-scan** | Critical | After a pick, L3 intermittently stayed extended instead of returning to home position. This blocked the camera FOV, causing subsequent scan positions to fail detection. Likely a significant contributor to the 17% zero-coordinate spike. |
| S5 | **Drop/throw angle inconsistent** | High | Cotton not landing reliably in collection box. Throws go both too far and too short (inconsistent in both directions). Trajectory tuning needed. |
| S6 | **EE ran continuously (runaway)** | Critical | End effector started running and would not stop. Service restart did not help. Only the shutdown topic stopped it. After RPi restart, worked normally. Happened in afternoon session. **Safety issue** — needs watchdog/timeout. |

### 9.3 Vehicle Issues

| # | Issue | Severity | Detail |
|---|-------|----------|--------|
| V1 | **Vehicle not moving intermittently** | Critical | Required multiple restarts. Would work after restart, then same issue returned. Consistent with ODrive stall loop pattern in logs (9 sessions = 9 restarts). |
| V2 | **Vehicle movement not smooth** | Medium | Even when driving, motion was jerky/uneven. Could be ODrive PID tuning, mechanical, or terrain-related. |

### 9.4 Cross-Reference: Observations vs Log Data

| Observation | Log Evidence | Gap |
|---|---|---|
| J5 belt broken | Motor health 100%, CAN 0 errors | Mechanical failures invisible to motor controller — need mechanical checklist |
| J3 offset wrong | 460 TOO FAR + 286 too far RIGHT violations | Consistent with systematic offset error shifting workspace envelope |
| L3 blocking FOV | 755 multi-scan events logged | No explicit "L3 failed to home" log entry — need to add this telemetry |
| EE runaway | Late sessions (7-9) | Need to search EE motor commands in session 7-9 logs for anomalies |
| Depth/L5 deep | L5 travel data in pick logs | Need to correlate L5 extension distance with depth estimates |
| Throw inconsistency | No throw telemetry | No drop/eject trajectory data logged — need to add this |
| Leaves not cotton | Detection confidence data | Need to check if low-confidence detections correlate with leaf targeting |

### 9.5 Team Review Feedback — Arm & Detection (Mar 03, 2026)

| # | Issue | Severity | Detail | Status |
|---|-------|----------|--------|--------|
| T1 | **Small cotton boll pick failure** | High | Cotton bolls smaller than the shell are not picked successfully. Combined issue: (1) detection model lacks size-based pickability classification for small bolls, (2) EE roller mechanism physically cannot grip undersized bolls. Needs both model improvement and EE design review. | New |
| T2 | **FOV confirmed improved** | Info | Team confirmed camera FOV has improved since January trial. Positive observation. | Noted |
| T3 | **YOLOv11 → YOLOX migration with 3 classes** | High | Current YOLOv11 model has 2 classes (cotton, not-pickable). Team recommends: (1) migrate from YOLOv11 to YOLOX due to licensing concerns for commercial use, (2) add sun_glare as a 3rd detection class to filter false positives from direct sunlight. Training data with sun glare images needed. | New |
| T4 | **Cotton behind leaves — depth inaccuracy** | High | Already documented (S3). Team re-emphasized: when cotton is behind leaves, stereo depth resolves on the leaf surface rather than the boll behind it. Confirms depth ambiguity is a significant contributor. | Already tracked |
| T5 | **EE roller — cotton seed jamming** | Medium | Cotton seeds getting stuck in EE roller mechanism. Roller pin size ~13mm. Known issue but not previously documented. Needs investigation: pin spacing vs seed size, possible design modification. | New |
| T6 | **L3 not tuned for new weight** | High | After EE mechanical changes, L3 motor PID/position control not re-tuned for updated payload weight. Position accuracy test needed. **Owner: Arul.** | New |

### 9.6 Team Review Feedback — Vehicle (Mar 03, 2026)

| # | Issue | Severity | Detail | Status |
|---|-------|----------|--------|--------|
| V3 | **Drive motors idle timeout** | High | After prolonged idle periods, ODrive drive motors fail to respond. Separate from the stall loop (V1) — this is about wake-from-idle behavior. | Needs investigation |
| V4 | **Drive motor temperature — no sensor** | High | ODrive drive motors have no temperature sensors. Unlike MG6012-i6 steering motors (which report 73-80°C), drive motor thermal state is completely unmonitored. Hardware gap. | New gap |
| V5 | **Encoder configuration investigation** | Medium | Both steering (MG6012-i6) and drive (ODrive) motor encoder setup needs verification: single vs dual channel, whether Channel A and Channel B are both being read. Quadrature decoding correctness unverified. | New investigation |
| V6 | **Field row spacing measured: 2.75 feet** | Info | Actual cotton row spacing at the field site is 2.75 feet (~0.84m). Too dense for comfortable vehicle/arm movement. Important for workspace analysis: arm reach (670mm) plus vehicle body width may exceed available inter-row space. | New measurement |

### 9.7 Team Review Feedback — Mechanical / Collection (Mar 03, 2026)

| # | Issue | Severity | Detail | Status |
|---|-------|----------|--------|--------|
| M1 | **J5 belt breakage root cause — disputed** | Medium | Team suggested belt broke because arm hit the collection box when picking low cotton positions not tested in lab. **Counter-analysis:** Lab testing showed no box collision at any tested position. Review of all field images prior to belt breakage shows the collection box never appeared in camera FOV. More likely: belt broke from fatigue or angle stress at termination point, and post-breakage the arm then reached the box due to lost position control. Root cause inconclusive — recommend belt stress analysis. | Disputed |
| M2 | **Arm backside getting stuck in plants** | High | The rear surface of the arm linkage catches on plant branches/leaves during movement, especially in dense rows (2.75ft spacing). Impedes arm motion and risks plant damage. May need arm shrouding or streamlined profile. | New |
| M3 | **Collection box swinging** | Medium | Collection box oscillates/swings during vehicle movement and arm operation. Instability affects cotton collection accuracy and may contribute to drop misses. Needs rigid mounting or damping solution. | New |
| M4 | **Collection box — current dimensions for reference** | Info | Current measurements: wheel diameter 250mm, box width 180mm. Mech team owns redesign of position and shape. These are baseline dimensions for the next iteration. | Reference |
| M5 | **Arm height compound reachability** | High | The 73% workspace violation rate is not solely an IK/calibration issue. It is a compound problem: (1) arm mounting height on vehicle may be too low for many cotton positions, (2) arm linkage length limits maximum reach, (3) vehicle unable to position close enough (ODrive issues + 2.75ft row spacing). All three factors must be addressed together — fixing only J3 offset will not resolve the full reachability gap. | New analysis |

### 9.8 Team Review Feedback — Positive Observations (Mar 03, 2026)

| # | Observation | Detail |
|---|-------------|--------|
| P1 | **Multi-position scanning effective** | J4 multi-position scanning strategy worked well. Team confirmed its value for coverage. |
| P2 | **Collection concept validated** | Cotton collection system concept is sound. Dynamic tracking during picks worked. |
| P3 | **EE picking improved** | End effector picking performance improved compared to previous trial (apart from the runaway incident). |
| P4 | **FOV improvement confirmed** | Camera field of view has improved since January trial. |

---

## Appendix A: Log File Inventory

### Vehicle Logs
```
collected_logs/2026-02-26_16-21/   (78 files)
├── target/
│   ├── provision_logs/
│   │   └── provision_20260226_114920.log
│   └── ros2_logs/          (9 sessions)
├── vehicle_mqtt_bridge/    (10 log files)
└── ...
```

### Arm1 Logs
```
collected_logs/2026-02-26_16-24/   (1,849 files)
├── target/
│   ├── provision_logs/
│   │   └── provision_20260226_115932.log
│   └── ros2_logs/          (9 sessions)
├── detection_images/
│   ├── input/              (904 images)
│   └── output/             (804 images)
└── ...
```

### Hostnames and IPs
| Host | IP | Role |
|------|----|------|
| pragati11 | 192.168.1.100 | Vehicle |
| ubuntu-desktop | 192.168.1.102 | Arm1 |

---

**Report Generated:** February 26, 2026
**Last Updated:** March 03, 2026 (v3: added team review feedback from Mar 03 session — Section 9.5-9.8, updated Section 8)
**Author:** Udayakumar (field visit, observations, review) + AI-assisted log analysis
**Review Status:** Team review completed (Mar 03, 2026)
