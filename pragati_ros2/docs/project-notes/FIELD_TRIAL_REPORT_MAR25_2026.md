# Field Trial Report - March 25, 2026

**Trial Date:** March 25, 2026
**Location:** Field Site
**Code Version:** Mar 24 build, commit `75763004` (arm nodes), commit `f7a205db` (vehicle nodes) — both [DIRTY]
**Test Mode:** Stop-and-pick (drive to spot, stop, both arms pick, drive to next)
**Duration:** ~10:44–16:40 IST field time (~6 hours), plus 18:05–18:11 lab test | ~7.4 hours active picking
**Rows Tested:** Cotton rows (both arms operational)
**Devices:** 3 RPi 4B — arm_1 (192.168.1.102), arm_2 (192.168.1.103), vehicle (192.168.1.100)
**Analysis Method:** `scripts/log_analyzer.py --field-summary --verbose` (automated) + manual log review + team field observations

> **Clock Drift Notice:** Afternoon session timestamps (after lunch reboot at ~14:05 actual)
> are **~85 minutes behind actual IST**. The RPis were not re-provisioned after reboot, so
> `fake-hwclock` restored the 12:40 shutdown time instead of actual ~14:05. Morning timestamps
> (10:44–12:40) are accurate. Within-session durations are unaffected (both endpoints share
> the same drift). The 18:05–18:11 arm_2 session was a lab sanity test after field wrap-up
> at ~16:40, with NTP-corrected timestamps. See Section 8 for log analyzer caveats.

---

## Executive Summary

### Key Findings
| System | Status | Issues |
|--------|--------|--------|
| **Vehicle (MG6010 steering)** | ⚠️ DEGRADED (Sessions 1-2) ✅ FIXED (Session 3) | Front wheel encoder zero shifted ~90°, thermal cascade to 80°C. Power cycle + manual reposition fixed it. |
| **Vehicle (ODrive drive)** | ⚠️ UNSTABLE (Session 2) ✅ OK (Session 3) | 29,950 WARN/ERROR lines in Session 2 (CAN-related watchdog timeouts). Clean in Session 3. Session 4: CAN bus dead, motors UNAVAILABLE for 30 min after E-stop |
| **Vehicle (MQTT bridge)** | ✅ SOLID | ~98.0% uptime, arm status flowing correctly all day |
| **Arm1 pick system** | ✅ OPERATIONAL | 319 cycles, 408 attempts, 214 picked (52.5% success) |
| **Arm2 pick system** | ✅ OPERATIONAL | 317 cycles, 522 attempts, 278 picked (53.3% success) |
| **Arm1 detection (YOLOv11, 2 classes)** | ✅ WORKING | 439 accepted detections (216 morning + 223 afternoon), 72ms avg latency |
| **Arm2 detection (YOLOv5, 1 class)** | ⚠️ FALSE POSITIVES | Higher detection rate but detects empty cotton shells as pickable — inflated numbers |
| **Arm motors (both)** | ✅ HEALTHY | All motors health=1.0, err_flags=0x0, temps 35-50°C |
| **CAN bus (arms)** | ✅ CLEAN | 0 errors, 0 drops both arms |
| **CAN bus (vehicle)** | ⚠️ HIGH RX ERRORS | 1.59M RX errors in Session 2 (~220/sec), MCP2515 limitation |
| **MQTT communication** | ✅ SOLID | Both arms connected on first attempt every session |
| **Network/WiFi** | ✅ STABLE | 0 ethernet errors, 0 link changes across all devices |
| **Arm2** | ✅ TESTED | First trial with both arms operational |

### Comparison: Feb 26 → Mar 25

| Metric | Feb 26 | Mar 25 | Change |
|--------|--------|--------|--------|
| Arms tested | 1 | **2** | +1 arm |
| Total pick attempts | 1,181 | **930** | -21% (but 2 arms, fewer instant rejections) |
| Cotton picked | 315 | **492** | **+56%** |
| Pick success rate | 26.7% | **52.9%** | **+26.2pp** (2x improvement) |
| Workspace rejections | 841 (73%) | 430 (46.2%) | **-27pp** (still #1 issue) |
| Zero spatial coords | 503 (17%) | 1,024 (filtered OK) | Filtering working, rate still high |
| Vehicle sessions (crashes) | 9 (all ODrive) | 4 (0 crashes, 1 E-stop) | **No crashes** |
| ODrive stall events | 1,000-1,800+/session | Session 2 errors only | **Major improvement** |
| Steering thermal peaks | 73-80°C (all 3) | 80°C (front only, encoder issue) | Isolated to encoder shift |
| MQTT uptime | 97.7% | **~98.0%** | Improved |
| Provisioning | FAILED 8-11/12 steps | **12/12 passed** (arms), 8/8 vehicle | **Fixed** |
| J4 scan positions | 5 | **5 → 7** (expanded mid-trial) | Denser scanning tested |
| Border filter rate | 5.3% | **23-52%** | Significantly higher (see §3.7) |

### Critical Issues (Priority Order)

1. **Workspace reachability remains #1 bottleneck** — 46.2% of picks fail at planning. When cotton IS reachable, success rate is 98.4%.
2. **Front wheel encoder zero shift** — MG6010 absolute encoder latched ~90° offset. No software detection exists. Caused 42 stalls + thermal damage across 4 hours.
3. **Detection model trade-off unresolved** — v11 filters shells but detects less cotton. v5 detects more but includes empty shells (false positives). Neither is satisfactory.
4. **Border filter removing 23-52% of detections** — significantly higher than Feb (5.3%). J4 multi-position scanning partially recovers this.
5. **J4 motor transient failures** — 89 action rejections across both arms (self-recovering but wastes cycles).

---

## 1. Vehicle System Analysis

### 1.1 Overview
- **Hostname:** pragati11, **IP:** 192.168.1.100, **Role:** vehicle
- **ROS2 sessions:** 4 (Session 1: 10:44, Session 2: 12:43 (actual ~14:08), Session 3: 15:00 (actual ~16:25), Session 4: 15:11 (actual ~16:36))
- **Nodes:** mg6010_controller_node (3 steering MG6010 CAN motors), odrive_service_node (3 ODrive drive motors), vehicle_mqtt_bridge (python3), vehicle_control_node (python3)
- **Build:** vehicle_motor_control Mar 23 `f7a205db` [DIRTY], vehicle_control_node Mar 23

### 1.2 Provisioning
- **Result:** 8/8 checks passed (4 applied, 4 already done)
- **Missing:** `can_watchdog.service` not deployed (CAN bus itself functioned normally)
- **Provision log:** `collected_logs/2026-03-25/machine-1/vehicle/provision_logs/provision_20260325_104310.log`

### 1.3 Session Timeline

| Session | Time (IST) | Duration | Battery V | Stalls | Thermal Events | Outcome |
|---------|-----------|----------|-----------|--------|----------------|---------|
| 1 | 10:44–12:42 | ~2h | 52.5-52.8V | 29 | 3 (front 80°C) | Front wheel stuck in stall/thermal loop |
| 2 | 12:43–14:54 (actual ~14:08–16:19) | ~2h 11m | 57.1-57.3V | 13 | 4 (all 3 motors) | Front still broken + ODrive cascade |
| 3 | 15:00–15:02+ (actual ~16:25–16:27+) | ~2m logged | 56.0-56.4V | **0** | **0** | **Post-fix. All motors healthy.** |
| 4 | 15:11–15:41 (actual ~16:36–17:06) | ~30m | — | **0** | **0** | **E-stop power cut. CAN bus UP but zero traffic. All motors UNAVAILABLE.** |

### 1.4 Front Wheel Encoder Zero Shift (CRITICAL)

**Field observation:** "Front wheel zero position got shifted — it didn't reach straight 0, instead it took horizontal 90 as zero. When we made joystick it was moving but after that was coming back to 90. Then we powered off and manually moved the wheel and then it worked."

**Log evidence confirms this.** The MG6010 `steering_front` (CAN ID 0x1) internal absolute encoder zero reference shifted ~90°. The software's homing saw `position=0.0000` and reported "Already at homing target" — but physically the wheel was at 90°.

**Smoking gun — idle current at startup (Session 1):**

| Motor | Idle Current at "Zero" | Normal Idle | Ratio |
|-------|----------------------|-------------|-------|
| steering_front | **1.84-1.92A** | 0.05-0.15A | **13-38x abnormal** |
| steering_left | 0.8-1.6A | 0.8-1.6A | Normal |
| steering_right | 0.1-0.4A | 0.1-0.4A | Normal |

**Stall and thermal escalation (Session 1):**

| Time (uptime) | Event | Current | Temperature |
|---------------|-------|---------|-------------|
| 0s (boot) | Homing "successful" | 1.92A idle | 43°C |
| 390s (6 min) | First STALL | 7.06A | 47°C |
| 1559s (26 min) | Continuous stalling | 4.38A | 54°C |
| 2009s (33 min) | Near limit | 5.59A | 70°C |
| 2039s (34 min) | THERMAL ERROR | 5.56A | **80°C** |
| 2085s | Recovery (cooled) | — | 60°C |

This thermal cycle repeated **3 times** in Session 1 and once in Session 2.

**Why software didn't catch it:** No independent position reference exists — the software trusts the MG6010's internal encoder. There is no limit switch, no external encoder, and no idle-current validation.

**Why the fix worked:** Power cycling reset the motor controller state. Manually repositioning the wheel to physical straight-ahead while powered off realigned physical zero with encoder zero.

**Likely cause:** Mechanical shock or forced wheel movement while motor was off, causing the internal gear position to shift relative to the encoder. Alternatively, motor latched its "zero" during a previous power cycle when the wheel was at an extreme position.

### 1.5 Steering Motor Health

| Motor | CAN ID | Session 1 Stalls | Session 2 Stalls | Session 3 Stalls | Peak Temp | Health (S3) |
|-------|--------|------------------|------------------|------------------|-----------|-------------|
| steering_front | 0x1 | 17 | 6 | 0 | 80°C | 1.0 |
| steering_left | 0x3 | 4 | 3 | 0 | 67°C | 1.0 |
| steering_right | 0x5 | 8 | 4 | 0 | 80°C | 1.0 |
| **Total** | | **29** | **13** | **0** | | |

STALL_PROTECTION command skips: 4,808 (S1) + 4,236 (S2) = 9,044 total.

**Actual peak stall currents (from STALL DETECTED events):**

| Motor | Peak Current | Session | Stall Threshold |
|-------|-------------|---------|-----------------|
| steering_front | **17.11A** | S2 | 6.40A (2.67x over) |
| steering_left | **12.20A** | S2 | 6.40A (1.91x over) |
| steering_right | **12.94A** | S1 | 6.40A (2.02x over) |

The log analyzer's "Max A" column (6.139A) reports the averaged maximum, not the instantaneous peak from stall events. Actual peaks were 2-2.7x the stall threshold.

**Motor current draw (log analyzer):**

| Motor | Mean A | Max A | StdDev | Spikes | Health |
|-------|--------|-------|--------|--------|--------|
| steering_front | -0.014 | 6.139 | 1.371 | 28 | ALERT |
| steering_left | 0.116 | 5.881 | 0.759 | 45 | ALERT |
| steering_right | 0.071 | 6.059 | 0.754 | 26 | ALERT |

### 1.6 ODrive Drive Motors

| Session | WARN/ERROR lines | Notable |
|---------|-----------------|---------|
| 1 | 915 | Moderate drive errors |
| 2 | **29,950** | Massive cyclic error/recovery cascade |
| 3 | 110 | Clean — normal startup noise |
| 4 | **0** | E-stop. Motors never powered on. |

Session 2 errors: `drive_right_back` 0x04000000 (WATCHDOG_TIMER_EXPIRED), `drive_left_back` 0x00000100 (MOTOR_ERROR), cyclic ERROR → CLEAR_ERRORS → IDLE → ERROR pattern. Likely **secondary to CAN bus saturation** — with ~220 RX errors/sec, ODrive nodes miss timely watchdog feeds.

**drive_left_back OVERTEMP event (Session 2):** At 14:25:44 IST, `drive_left_back` triggered error code `0x42000000` (OVERTEMP + CONTROLLER_FAILED) — 6 occurrences in a 250ms burst. This is the only thermal event on any ODrive motor across the entire trial.

**Complete ODrive error code inventory:**

| Code | Meaning | Session(s) | Motor(s) | Count |
|------|---------|-----------|----------|-------|
| 0x04000000 | WATCHDOG_TIMER_EXPIRED | S1, S2 | all 3 drive | S1: 211, S2: 4,883 |
| 0x00000100 | MOTOR_ERROR | S2 | all 3 drive | 24,099 |
| 0x42000000 | OVERTEMP + CONTROLLER_FAILED | S2 | drive_left_back | 6 |
| 0x00001000 | ENCODER_ERROR | S2 | drive_front | 37 |
| 0x00001100 | ENCODER_ERROR + MOTOR_ERROR | S2 | drive_front | 4 |
| 0x00000200 | CONTROLLER_ERROR (DC_BUS_OVER_REGEN_CURRENT) | S1, S3 | drive_front, drive_right_back | S1: 134, S3: 50 |
| 0x00000201 | CONTROLLER_ERROR + INITIALISING | S1, S3 | drive_front | S1: 19, S3: 50 |
| 0x00000001 | INITIALISING | S1 | all 3 drive | 48 |
| **Total** | | | | **29,491** |

**Per-session breakdown:** Session 1: 412 errors (4 codes, 195 drive stops, 101 ERROR_STATE transitions). Session 2: 29,029 errors (5 codes, 288 drive stops, 231 ERROR_STATE transitions — 98.4% of total). Session 3 (E-stop): 50 errors. ODrives were power-cycled between S1 and S2 (S2 encoders start at 0.0000; S1 had carried-over positions ~230-243m).

**Error density peaks (Session 2 mg6010 controller):**

| Time (IST) | ERRORs/min | Dominant Error |
|------------|-----------|----------------|
| 13:47 | **643** | steering_right AXIS_ERROR (Code: 8) |
| 14:45 | **539** | steering_left stall (12.20A) → AXIS_ERROR cascade |
| 12:49 | **333** | Motor error state (Code: 8) |

### 1.7 Hardware E-Stop Event (Session 3→4 Transition)

**Field observation:** Hardware E-stop was used to cut motor power supply during Session 3. The RPi remained powered. Motors were not re-powered before Session 4.

**Log evidence timeline:**

| Time (IST) | Event | Evidence |
|------------|-------|----------|
| 15:00:52 | Session 3 starts | All motors OK, vbus ~56V |
| 15:02:35 | **ODrive DRIVE STOP ACTIVATED** | odrive_service log |
| 15:02:38 | ODrive error cascade | `drive_front: 0x00000201` (DC_BUS_OVER_REGEN_CURRENT), `drive_right_back: 0x00000200` |
| 15:02:37–15:03:37 | CAN traffic drops to **zero** | can_stats: 759 new RX → 0 new RX |
| 15:03:37–15:09:56 | mg6010 node running but per-motor data truncated | Silent CAN read failure |
| 15:09:56 | Session 3 SIGTERM | signal_handler(signum=15) |
| ~15:10–15:11 | **E-stop window** | Motor power physically cut |
| 15:11:57 | Session 4 starts | CAN interface UP, zero bus traffic |
| 15:11:57 | All 3 motors: Motor ON failed | "Command 0x88 failed after 3 attempts (Code: 10)" |
| 15:12:28 | All motors UNAVAILABLE | vbus_v=0.0, health=0.0 for 30 minutes |

**Key evidence:**
- **ODrive `0x00000200` (DC_BUS_OVER_REGEN_CURRENT)** at 15:02:38 — fires when motor power supply is interrupted while motors are decelerating. Back-EMF has nowhere to go.
- **Session 4 CAN stats: 0 RX, 0 TX, 0 errors for 30 minutes** — CAN interface was UP but nothing on the bus. Motor controllers had no power.
- **ODrive positions reset to 0.0000** in Session 4 (was ~127m accumulated in Session 2) — power cycle wiped state.
- **Session 3 CAN error rate was ~200x higher** than Session 2's steady-state rate (24,241 errors in 2 min active vs 1,298 total in Session 2).

**Relationship to encoder zero shift:** The front wheel was at approximately zero position during Session 3, so this specific E-stop did not directly cause the encoder shift. However, if the wheel was manually moved while the E-stop was engaged (motor power off), and power was later restored with the wheel at ~90°, the encoder would latch that as the new zero — consistent with the team's description of the fix.

**Instrumentation gaps identified:**
- mg6010 controller silently stops reporting per-motor data when CAN communication fails — no explicit "CAN read timeout" error
- No structured "E-STOP DETECTED" or "MOTOR POWER LOST" event in any log
- No vbus voltage transition logging (e.g., "vbus dropped from 56V to 0V")
- `dmesg_network.log` was empty (0 bytes) for Sessions 3 and 4

### 1.8 CAN Bus

| Metric | Session 1 (end) | Session 2 (end) | Session 3 (2 min) |
|--------|-----------------|-----------------|-------------------|
| RX packets | — | 13,880,779 | 193,694 |
| RX errors | — | **1,586,986** | 13,281 |
| RX dropped | — | 123,481 | 119,092 |
| TX packets | — | 2,358,949 | 10,450 |
| TX errors | — | 0 | 0 |

CAN bus was **DOWN at boot** for Session 2 (first can_stats snapshot at 12:42:37 showed state=DOWN), came UP within 60 seconds. The first minute after CAN came up saw **92,143 dropped packets** — a burst that then stabilized (only 31K more drops over the remaining 2 hours). This initial drop burst is baseline MCP2515 SPI controller behavior under the broadcast load from 6 motors. TX is reliable. Session 3's error pattern is identical to Session 2's first minutes — confirming this is hardware baseline, not related to the encoder issue. No Session 1 CAN stats available (field_trial_logs monitoring started with Session 2).

### 1.9 MQTT Bridge

| Metric | Value |
|--------|-------|
| MQTT uptime | ~98.0% |
| Connects | 3 |
| Disconnects | 2 (unexpected — keepalive timeouts) (revised: 5 total unexpected disconnects across all devices) |
| MTBF | 15,384s |
| Publish failures | 0 |
| Broker socket errors | 0 |
| Arm status seen | arm_1: ready, arm_2: ready |

Mosquitto broker healthy throughout. Arm status cycling normally (UNINITIALISED → ready → busy → ready).

### 1.10 System Health

| Metric | Value | Status |
|--------|-------|--------|
| RAM | 3,784 MB total, ~483 MB used | ✅ |
| Disk | 58 GB total, 47-49% used | ✅ |
| CPU temp | 49-54°C steady; **CRITICAL spike to 80.8°C** at 10:50 S1 boot | ⚠️ |
| OOM events | 0 | ✅ |
| Failed systemd units | 0 | ✅ |
| vehicle_control_node memory | 136 MB → 163 MB over 2h (**+20%**) | ⚠️ |

### 1.11 Trend Alerts (log analyzer)

- Joint steering_right temperature rose 9.9°C (42.6°C → 52.5°C)
- Joint steering_front temperature rose 13.6°C (49.3°C → 62.9°C)
- steering_front health degraded to 0.6 (60%) with err_flags=20 during Sessions 1-2

---

## 2. Arm1 System Analysis

### 2.1 Overview
- **Hostname:** ubuntu-desktop, **IP:** 192.168.1.102, **Role:** arm (arm_1)
- **ROS2 sessions:** 4 (10:47 (morning, accurate clock), 12:40 (actual ~14:05), 13:40 (actual ~15:05), 14:55 (actual ~16:20))
- **Detection model:** YOLOv11 (`yolov112.blob`, 2 classes — cotton + not-pickable shells)
- **Build:** All nodes Mar 24 `75763004` [DIRTY]
- **Boot time:** ~30s both boots

### 2.2 Provisioning
- **Result:** 12/12 steps OK (4 applied, 8 already done)
- **Provision log:** `collected_logs/2026-03-25/machine-1/arm_1/provision_logs/provision_20260325_104727.log`

### 2.3 Session Breakdown

| Session | Time (IST) | Duration | Cycles | Picks | Cotton Picked | Success Rate | J4 Config | Notes |
|---------|-----------|----------|--------|-------|---------------|-------------|-----------|-------|
| 1 | 10:47–12:39 (morning, accurate clock) | ~1h 52m | 143 | 223 | 100 | 44.8% | 5-pos | Recovered morning session. Start switch at 10:49:55. Active picking ~1h 46m. Graceful MQTT shutdown at 12:39:17. |
| 2 | 12:40–13:39 (actual ~14:05–15:04) | 59 min | 87 | 77 | 51 | 66.2% | 5-pos | Steady operation |
| 3 | 13:40–14:55 (actual ~15:05–16:20) | 75 min | 88 | 108 | 63 | 58.3% | 7-pos | COLLISION_BLOCKED surged 4x |
| 4 | 14:55–~15:00 (actual ~16:20–~16:25) | ~5 min | 1 | 0 | 0 | N/A | 7-pos | No cotton detected (model warning) |
| **Total** | | **~4h 11m** | **319** | **408** | **214** | **52.5%** | | |

### 2.4 Pick Performance

| Metric | Value |
|--------|-------|
| Operational cycles | 319 |
| Total pick attempts | 408 |
| Successful picks | 214 |
| **Pick success rate** | **52.5%** |
| Failed picks | 194 |
| Throughput | 97.9 picks/hour |

> Throughput is computed from within-session durations (picks ÷ active time), which are
> unaffected by clock drift — both session start and end share the same offset.

**Cycle time:**

| Metric | Value |
|--------|-------|
| cycle_ms avg | 3,717ms |
| cycle_ms p50 | 5,061ms |
| cycle_ms p95 | 6,725ms |
| approach_ms avg | 1,735ms |
| capture_ms avg | 569ms |
| retreat_ms avg | 1,760ms |

**Per-joint timing (log analyzer):**

| Phase | p50 | p95 | max | Note |
|-------|-----|-----|-----|------|
| J5+EE approach | 648ms | 920ms | 1,023ms | Bottleneck |
| J3 retreat | 1,986ms | — | 2,522ms | Slowest retreat phase |
| EE ON duration | 1,084ms | 1,276ms | 1,357ms | |
| EE dwell at cotton | 100ms | 100ms | — | Consistent |

### 2.5 Failure Breakdown

| Failure Type | S1 (morning) | S2 | S3 | Total | % of Failures |
|-------------|-------------|-----------|-----------|-------|---------------|
| COLLISION_BLOCKED | 81 | 8 | 35 | **124** | 63.9% |
| OUT_OF_REACH | 36 | 14 | 8 | **58** | 29.9% |
| JOINT_LIMIT_EXCEEDED | 2 | 3 | 2 | **7** | 3.6% |
| success:false (other) | 0 | 1 | 0 | 1 | 0.5% |
| plan_status=OK but success:false | 4 | 0 | 0 | 4 | 2.1% |
| **Total** | **123** | **26** | **45** | **194** | 100% |

All 194 failures were **instant workspace rejections** (0-3ms approach time, no motor movement). The morning session (S1) had the highest failure count due to 5-position scanning covering the initial cotton rows. COLLISION_BLOCKED surged 4x in Session 3 (8→35), possibly due to denser cotton regions or 7-pos scanning finding more cotton at the workspace boundary.

### 2.6 Detection Performance

| Metric | Value |
|--------|-------|
| Detection model | YOLOv11 (`yolov112.blob`, 2 classes) |
| Model source | Fallback from `data/models/` to `install/share/` (WARN each session) |
| Raw detections | 3,185 (858 morning + 2,327 afternoon) |
| Accepted detections | 439 (216 morning + 223 afternoon) |
| Detection requests (morning) | 858 |
| Detections with cotton (morning) | 216 (25.2%) |
| DetectionOutput images (morning) | 853 |
| Border skip rate | **14.7%** (afternoon sessions) |
| Not-pickable rate | **20.8%** (class 1 = empty shells, intentionally filtered) |
| Zero spatial coordinates | **335** (filtered correctly, afternoon only) |
| Avg detection age | 19.0ms |
| Stale picks (>2s) | 11.9% |
| Severely stale (>10s) | 1 pick |
| Detection latency p50/p95/p99 | 72.1 / 185.6 / 215.0ms |
| Frame drop rate | 97.3% (by design — on-demand processing) |
| Camera temp range | 49.0–66.7°C (mean 62.1°C); morning peak **66.7°C** |
| Camera rate of rise | 0.02°C/min |
| Time to critical (85°C) | 1,524 min (~25 hours) |
| XLink errors | 0 |
| USB reconnects | 0 (afternoon); **1 reconnect (morning, 12.5s detection downtime, 9,236ms latency spike)** |
| USB speed | 3.0 (5Gbps) |
| Detection data timeouts (morning) | **15** (yanthra_move waiting for fresh camera data) |
| Wasted detections | 48.9% (109/223 accepted did not lead to successful pick, afternoon sessions) |

**Model note:** `yolov112.blob` path warning appeared every session — `data/models/yolov112.blob` not found, fell back to `install/share/cotton_detection_ros2/models/yolov112.blob`. Same binary, but the fallback warning clutters logs.

**Session 4 anomaly:** 0 cotton detected at any of 7 J4 positions. The model fallback warning was present. Possible contributing factor — needs investigation.

### 2.7 J4 Multi-Position Scanning

**Config change mid-trial:**

| Config | Active Sessions | Positions | Spacing | Values (mm) |
|--------|----------------|-----------|---------|-------------|
| 5-position | Sessions 1-2 | 5 | 75mm | -150, -75, 0, +75, +150 |
| 7-position | Sessions 3-4 | 7 | 50mm | -150, -100, -50, 0, +50, +100, +150 |

**Scan effectiveness (log analyzer):**

| J4 Offset | Scans | Found | Picked | Yield |
|-----------|-------|-------|--------|-------|
| 0mm | 176 | 30 | 25 | 83.3% |
| -150mm | 176 | 25 | 19 | 76.0% |
| +75mm | 87 | 21 | 18 | 85.7% |
| -100mm | 89 | 23 | 14 | 60.9% |
| -50mm | 89 | 16 | 11 | 68.8% |
| -75mm | 87 | 17 | 10 | 58.8% |
| +50mm | 89 | 15 | 9 | 60.0% |
| +100mm | 89 | 11 | 6 | 54.5% |
| +150mm | 175 | 27 | 2 | **7.4%** |

**+150mm is catastrophically bad** — 27 found but only 2 picked (7.4% yield). This position consistently finds cotton that is unreachable. **-150mm reversed from Feb** (was best at 39.5% in Feb, now 76.0% and still strong).

**Border filter impact with 7-pos:**

| J4 Config | Border Skip Rate | Recovery Rate | Net Improvement |
|-----------|-----------------|---------------|-----------------|
| 5-pos (S2) | 27.4% | 48.7% recovered | Baseline |
| 7-pos (S3) | 23.8% | **57.3% recovered** | **+8.6pp recovery** |

The 7-position config recovered 8.6pp more border-filtered cotton on arm_1. However, COLLISION_BLOCKED also increased 4x (8→35), partially negating the detection gains.

### 2.8 Motor Health

| Joint | Avg Temp | Max Temp | Voltage | Mean Current | Max Current | Health | Spikes |
|-------|----------|----------|---------|-------------|-------------|--------|--------|
| joint3 | 45.7°C | 47°C | — | 1.667A | 3.674A | 100% | 0 |
| joint4 | 42.1°C | 43°C | — | 0.027A | 1.063A | 100% | 37 (ALERT) |
| joint5 | 42.0°C | 43°C | — | 0.090A | 0.951A | 100% | 51 (ALERT) |

J4 current spikes (37) and J5 current spikes (51) are consistent with the transient J4 action failures (25 events). Motor position trending: J3 stable (mean error 0.0029), J4 stable (0.0000).

CAN bus: 0 errors, 0 drops, 0 collisions. Clean throughout.

### 2.9 MQTT Communication

| Metric | Value |
|--------|-------|
| Connects | 4 (one per session, first attempt every time) |
| Disconnects | **1 unexpected** (S4: code=7, 21s after vehicle shutdown_switch, 5 consecutive service call failures) |
| MQTT heartbeats (morning) | 1,187 (~10.6/min) |
| MQTT disconnections (morning) | 0 |
| Service discovery timeouts | 0 |
| Silence watchdog warnings | 9 (normal during vehicle idle periods) |

### 2.10 Hourly Throughput

| Hour | Picks | Successes | Rate | Avg Cycle |
|------|-------|-----------|------|-----------|
| 0 (morning S1) | 223 | 100 | 44.8% | — |
| 1 (S2) | 78 | 51 | 65.4% | 3,909ms |
| 2 (S3) | 107 | 63 | 58.9% | 3,577ms |

### 2.11 Success Rate Trend (log analyzer)

| Metric | Value |
|--------|-------|
| First-quarter rate (morning S1) | 44.8% |
| Mid-session rate (S2) | 66.2% |
| Last-quarter rate (S3) | 58.3% |
| Trend | **↑ Improving after morning, then declining in S3 (7-pos COLLISION_BLOCKED surge)** |

The morning session (S1) had the lowest success rate at 44.8%, driven by high COLLISION_BLOCKED (81) and OUT_OF_REACH (36) failures with 5-position scanning. Success improved significantly in S2 (66.2%) before degrading again in S3 (58.3%) when 7-pos scanning found more cotton at workspace boundaries.

### 2.12 Session 4 Root Cause

Session 4 produced 0 picks not because of a detection model issue (as initially suspected), but because the **vehicle sent a `shutdown_switch` command** at 15:05:22 via MQTT (`topic/shutdown_switch_input_all: True`). The arm received the command and began shutdown. 21 seconds later, MQTT disconnected (code=7, keepalive timeout), followed by 5 consecutive service call failures.

### 2.13 Safety Configuration

**J3-J4 collision interlock was DISABLED** via parameter in all 4 sessions. Every session's motor controller logged: `collision_interlock_disabled: J3-J4 collision interlock is DISABLED via parameter`. This hardware safety feature was intentionally disabled for the field trial.

### 2.14 Memory Growth

Python3 processes grew from ~13MB to ~174MB (PID 1241) and ~95MB (PID 1240) over the trial duration. Previously only arm_2's memory leak (24MB/hr) was documented — arm_1 shows a similar growth pattern.

### 2.15 Boot Issues

**S2 boot:** 6 RCU preempt stall kernel warnings during boot sequence (12:40:24 to 12:40:35) — CPU contention from all ROS2 nodes, dashboard, and system services starting simultaneously on RPi 4B's 4 cores.

**Fix verification:** 2 checks MISSING in all sessions — `can_watchdog.service` and `vehicle_launch.service`. The role detection also showed `Role: vehicle` on an arm node, suggesting a detection bug.

---

## 3. Arm2 System Analysis

### 3.1 Overview
- **Hostname:** ubuntu-desktop, **IP:** 192.168.1.103, **Role:** arm (arm_2)
- **ROS2 sessions:** 7 (10:49, 11:10, 11:12, 12:41 (actual ~14:06), 13:37 (actual ~15:02), 14:55 (actual ~16:20), 18:05 lab test with NTP-corrected clock)
- **Detection model:** YOLOv11 (Session 1) → **YOLOv5** (Sessions 2-6) — switched mid-trial
- **Build:** All nodes Mar 24 `75763004` [DIRTY]
- **Boot time:** ~30s

### 3.2 Provisioning
- **Result:** 12/12 steps OK
- **Missing:** `can_watchdog.service` not found (7/8 fix_verification checks)
- **NetworkManager-wait-online.service:** FAILED during Session 4 boot (network wasn't ready when timed out, but system operated normally afterward)

### 3.3 Session Breakdown

| Session | Time (IST) | Duration | Cycles | Picks | Cotton | Rate | Model | J4 Config | Notes |
|---------|-----------|----------|--------|-------|--------|------|-------|-----------|-------|
| 1 | 10:49–11:10 | 21 min | 20 | 12 | 6 | 50.0% | **v11** | 5-pos | Initial testing |
| 2 | 11:10–11:12 | 2 min | 2 | 0 | 0 | N/A | **v5 (wrong classes=2)** | — | Misconfigured, killed |
| 3 | 11:12–12:39 | **87 min** | **119** | **205** | **124** | **60.5%** | **v5** | 5-pos | Best session |
| 4 | 12:41–13:36 (actual ~14:06–15:01) | 55 min | 85 | 146 | 67 | 45.9% | v5 | 5-pos | Post-reboot |
| 5 | 13:37–14:55 (actual ~15:02–16:20) | 78 min | 90 | 159 | 81 | 50.9% | v5 | **7-pos** | MQTT disconnect at end |
| 5b | 14:55–~15:05 (actual ~16:20–~16:30) | ~10 min | 0 | 0 | 0 | N/A | v5 | 7-pos | yanthra_move shut down mid-session; 8 detections, 0 cotton. |
| 6 | 18:05–18:11 | 6 min | 1 | 0 | 0 | N/A | v5 | 7-pos | Lab sanity test (post-field, NTP-corrected clock); no cotton expected |
| **Total** | | **~4h 19m** | **317** | **522** | **278** | **53.3%** | | | |

> **Session 5→6 gap note:** The logged gap appears to be 14:55→18:05 (~3h 10m), but Session 5
> ended at actual ~16:20 (drifted clock). Session 6 at 18:05 used an NTP-corrected clock
> (WiFi available in lab). Real gap: ~1h 45m (field wrap-up at ~16:40 + travel to lab + setup).

### 3.4 Detection Model Switch: YOLOv11 → YOLOv5 (CRITICAL CONTEXT)

**What happened:**
- Session 1 (10:49): Started with `yolov112.blob` (YOLOv11, 2 classes — cotton + not-pickable shells)
- Session 2 (11:10): Switched to `best_openvino_2022.1_6shave.blob` (YOLOv5) but with wrong `classes=2`. Killed after 65s, 0 detections.
- Session 3 (11:12): Corrected to `classes=1`. Ran stable for rest of day.

**Why the switch:** v11 was not detecting cotton well — possibly due to field lighting conditions, model sensitivity, or other environmental factors. v5 was tried as an alternative.

**Detection rate comparison:**

| Model | Det Rate | Avg Confidence | Not-Pickable Filter |
|-------|---------|----------------|---------------------|
| YOLOv11 (arm1 all day) | 14.8-15.8% | 0.680 | **20.8% filtered (shells)** |
| YOLOv11 (arm2 S1) | 13.3% | 0.686 | Active |
| YOLOv5 (arm2 S3-S5) | 21.5-28.7% | 0.729 | **0% — no shell class** |

**IMPORTANT CAVEAT:** The v5 model's higher detection rate is **inflated by false positives**. It detects empty cotton shells (bolls without cotton) as pickable cotton and sends the arm to pick them. The v11 model's second class (`label=1`, not-pickable) was specifically added to filter these empty shells. So:
- v5's 28.7% detection rate includes shell false positives → arm moves to empty positions
- v11's 15.8% detection rate is more honest → fewer wasted arm movements
- v5's "53.3% success rate" is artificially lowered by attempting to pick empty shells
- The actual detection quality comparison requires field-truthing which images were real cotton vs shells

**Not-pickable filtering stats:**

| Arm | Model | Not-Pickable Rate | Effect |
|-----|-------|-------------------|--------|
| arm_1 | v11 | **20.8%** of raw detections filtered as shells | Prevents wasted picks |
| arm_2 | v5 | **1.0%** (only border filter, no shell class) | Shells sent to arm as cotton |

### 3.5 Pick Performance

| Metric | Value |
|--------|-------|
| Operational cycles | 317 |
| Total pick attempts | 522 |
| Successful picks | 278 |
| **Pick success rate** | **53.3%** |
| Throughput | 71.0 picks/hour |

> Throughput is computed from within-session durations, unaffected by clock drift.

**Cycle time:**

| Metric | Value |
|--------|-------|
| cycle_ms avg | 3,447ms |
| cycle_ms p50 | 4,472ms |
| cycle_ms p95 | 7,009ms |
| approach_ms avg | 1,568ms |
| capture_ms avg | 556ms |
| retreat_ms avg | 1,629ms |

**Per-joint timing (log analyzer):**

| Phase | p50 | p95 | max | Note |
|-------|-----|-----|-----|------|
| J5+EE approach | 740ms | 1,029ms | 1,169ms | Bottleneck |
| J3 retreat | 2,031ms | — | 2,521ms | Slowest retreat phase |
| EE ON duration | 1,187ms | 1,350ms | 1,367ms | |
| EE dwell at cotton | 100ms | 100ms | — | Consistent |

### 3.6 Failure Breakdown

| Failure Type | S1 | S3 | S4 | S5 | Total | % |
|-------------|----|----|----|----|-------|---|
| COLLISION_BLOCKED | 6 | 55 | 72 | 58 | **191** | 79.6% |
| OUT_OF_REACH | 0 | 23 | 5 | 17 | **45** | 18.8% |
| JOINT_LIMIT_EXCEEDED | 0 | 1 | 1 | 2 | **4** | 1.7% |
| **Total** | **6** | **79** | **78** | **77** | **240** | 100% |

**When cotton is reachable, picking works at 98.4% success rate** (492/500 that passed planning).

### 3.7 J4 Multi-Position Scanning

**Config change mid-trial (same as arm_1):**

| Config | Sessions | Positions | Values (mm) |
|--------|----------|-----------|-------------|
| 5-position | S1, S3, S4 | 5 | -150, -75, 0, +75, +150 |
| 7-position | S5, S6 | 7 | -150, -100, -50, 0, +50, +100, +150 |

**Scan effectiveness (log analyzer):**

| J4 Offset | Scans | Found | Picked | Yield |
|-----------|-------|-------|--------|-------|
| 0mm | 493 | 199 | 114 | 57.3% |
| -75mm | 311 | 106 | 74 | 69.8% |
| +75mm | 311 | 132 | 65 | 49.2% |
| -150mm | 493 | 80 | 50 | 62.5% |
| +50mm | 182 | 54 | 30 | 55.6% |
| +100mm | 182 | 52 | 28 | 53.8% |
| -50mm | 182 | 38 | 26 | 68.4% |
| -100mm | 182 | 38 | 24 | 63.2% |
| +150mm | 492 | 128 | 15 | **11.7%** |

Same pattern as arm_1: **+150mm is the worst position** (11.7% yield) — finds cotton but nearly all are unreachable. Multi-position scanning found **77% more cotton** than center-only.

**Border filter impact:**

| J4 Config | Border Skip Rate | Recovery at Other Position | Total Loss |
|-----------|-----------------|---------------------------|------------|
| 5-pos (S3) | 43.6% | 76.9% recovered | 23.1% |
| 5-pos (S4) | 34.4% | — | — |
| 7-pos (S5) | **52.0%** | 71.6% recovered | 28.4% |

**Border filter rate increased to 52% with 7-pos** — more scan positions = more frames = more edge-case detections getting filtered. Recovery rate did not improve (71.6% vs 76.9%). The 7-pos strategy did **not** help arm_2 for border recovery.

### 3.8 Detection Performance

| Metric | Value |
|--------|-------|
| Detection model | YOLOv5 (`best_openvino_2022.1_6shave.blob`, 1 class) — Sessions 3-6 |
| Raw detections | 10,845 |
| Accepted detections | 1,025 |
| Acceptance rate | 9.5% |
| Border skip rate | **12.0%** |
| Not-pickable rate | **1.0%** (no shell class in v5) |
| Zero spatial coordinates | **689** (filtered correctly) |
| Avg detection age | 20.0ms |
| Stale picks (>2s) | 13.2% |
| Severely stale (>10s) | 8 picks |
| Detection latency p50/p95/p99 | 66.3 / 245.9 / 286.6ms |
| Frame drop rate | 98.4% (by design) |
| Camera temp range | 50.1–69.6°C (mean 65.7°C) |
| XLink errors | **1** (S3 at 12:22:03 — USB disconnect triggered X_LINK_ERROR on stream 'detections') |
| USB reconnects | **1** (S3 — reconnect failed after 7,052ms, then recovered; **17.1s total detection downtime**) |
| Wasted detections | **57.3%** (373/651 accepted did not lead to successful pick) |

**Wasted detections (57.3%) are higher than arm_1 (48.9% afternoon sessions)** — consistent with v5 sending the arm to empty shells.

### 3.9 Motor Health

| Joint | Avg Temp | Max Temp | Mean Current | Max Current | Health | Spikes |
|-------|----------|----------|-------------|-------------|--------|--------|
| joint3 | 45.9°C | 50°C | 1.700A | 3.593A | 100% | 1 (ALERT) |
| joint4 | 42.1°C | 44°C | 0.091A | 1.047A | 100% | 80 (ALERT) |
| joint5 | 43.8°C | 48°C | 0.060A | 1.450A | 100% | 35 (ALERT) |

J4 spikes (80) much higher than arm_1 (37) — correlates with more J4 action failures on arm_2 (47 vs 25).

Motor position trending: **J3 degrading** (mean error 0.0031, trend ↑) — though absolute error is still very small. J4/J5 stable.

CAN bus: 0 errors, 0 drops. Clean.

### 3.10 J4 Motor Action Failures

| Issue | S3 | S4 | S5 | S6 | Total |
|-------|----|----|----|----|-------|
| J4 action failure (result=2) | 13 | 15 | 17 | 2 | **47** |
| J4 goal REJECTED | 5 | 6 | 6 | 0 | **17** |
| J4 homing failed | 0 | 2 | 1 | 1 | **4** |

Pattern: `actual=0.0000, target=<small_value>, 7-10ms, code=0, feedback_samples=0`. The action server rejects the goal before any motion occurs. Self-recovering between occurrences.

### 3.11 MQTT Communication

| Metric | Value |
|--------|-------|
| Connects | **7** (one per session) |
| Unexpected disconnects | **2** (Session 5 keepalive timeout; Session 7/lab test code=7 keepalive timeout at 18:15:29) |
| Silence watchdog warnings | 37 (idle periods) |

### 3.12 Hourly Throughput

| Hour | Picks | Successes | Rate | Avg Cycle |
|------|-------|-----------|------|-----------|
| 0 | 95 | 52 | 54.7% | 3,791ms |
| 1 | 124 | 78 | 62.9% | 3,993ms |
| 2 | 170 | 79 | 46.5% | 2,958ms |
| 3 | 133 | 69 | 51.9% | 3,318ms |

### 3.13 Trend Alerts (log analyzer)

- **Detection age increasing 90ms/hour** (337ms → 709ms) — suggests progressive detection pipeline slowdown
- Memory growth: python3 process +24MB/hour (129MB → 176MB over 2 hours) — potential memory leak

### 3.14 Success Rate Trend

| Metric | Value |
|--------|-------|
| First-quarter rate | 53.1% |
| Last-quarter rate | 52.3% |
| Trend | **↔ Stable (+0.8pp)** |

Unlike arm_1, arm_2's success rate was stable throughout — the rate was already lower due to the v5 false positive issue.

### 3.15 J3 Position Clamping (Systematic)

**278 J3 position clamping events** across all sessions: S1=6, S3=124, S4=67, S5=81. The motion planner consistently commands J3 to -0.180 but the configured limit is -0.166, resulting in automatic clamping. This 8.4% overshoot suggests either the joint limit is too conservative or the planner's workspace model is miscalibrated.

### 3.16 Safety Configuration

**J3-J4 collision interlock was DISABLED** via parameter in all 7 sessions (same as arm_1). This is a safety-relevant configuration that should be explicitly documented and reviewed.

### 3.17 Memory Leak Source Identified

The report previously noted a 24MB/hr memory leak. Process memory logs identify the source:

| Process | Start | End | Growth | Rate |
|---------|-------|-----|--------|------|
| `dashboard_server` (uvicorn, PID 1251) | 126.8MB | 172.8MB | **+46MB** | **~22MB/hr** |
| `rpi_agent` (PID 1250) | 23.4MB | 85.0MB | **+61.6MB** | +61.6MB init, then ~1.9MB/hr |
| ROS2 node processes | — | — | ~1MB/5min each | Minor |

The `dashboard_server` is the primary leaker during active operation. The `rpi_agent` has a large initialization allocation (+61.6MB) then slow growth. Neither process restarts between ROS2 sessions — they accumulate across the entire trial. At 22MB/hr, the dashboard server would consume all available RAM in ~20-30 hours of continuous operation.

### 3.18 Boot Issues

**Boot 1 (12:41):** NetworkManager-wait-online.service FAILED (60s timeout). Boot did NOT finish after 80s with 3 blocking jobs remaining. RCU preempt stall detected. Both `system.journal` and `user-1000.journal` were corrupted and had to be renamed. CPU at 1500MHz (not boosted), wlan0 DOWN.

**Boot 2 (18:05):** Cleaner — 28s total, NM-wait-online succeeded in 8.4s, but still had 4 RCU stalls and corrupted journals.

### 3.19 Camera VPU Temperature Trend

| Session | Start Temp | End Temp | Max Temp | Trend |
|---------|-----------|----------|----------|-------|
| S1 | 56.6°C | 62.5°C | 62.5°C | +5.9°C (cold start) |
| S3 | 61.2°C | 65.7°C | 66.4°C | +5.2°C |
| S4 | 54.8°C | 67.2°C | 67.7°C | +12.9°C (steepest) |
| S5 | 65.1°C | 67.8°C | **69.6°C** | +2.7°C (sustained 68-69°C) |

VPU thermal throttling was never triggered (`paused: false` in all samples), but 69.6°C is approaching limits that could cause inference degradation in longer sessions. The steep S4 climb (+12.9°C) was likely due to ambient heat accumulation from prior sessions.

### 3.20 Disk Usage Growth

Root filesystem usage crept from 65% to 66% during the monitoring window (12:41–14:51), with available space dropping from 9.9GB to 9.6GB (~300MB consumed in ~2 hours, ~150MB/hr). At this rate, the 29GB SD card could fill in days of continuous operation.

### 3.21 DepthAI Shave Configuration

Every session logged: "Network compiled for 6 shaves, maximum available 9, compiling for 4 shaves likely will yield better performance." The neural network model uses fewer shaves than compiled for — a potential tuning opportunity for inference speed.

---

## 4. Zero Spatial Coordinate Analysis

### 4.1 Counts

| Arm | Session | Zero Drops |
|-----|---------|-----------|
| arm_1 | 10:47 (morning, accurate clock) | — (not yet analyzed) |
| arm_1 | 12:40 (actual ~14:05) | 138 |
| arm_1 | 13:40 (actual ~15:05) | 197 |
| arm_2 | 10:49 | 27 |
| arm_2 | 11:12 | 261 |
| arm_2 | 12:41 (actual ~14:06) | 124 |
| arm_2 | 13:37 (actual ~15:02) | 277 |
| **Total** | | **1,024** |

### 4.2 Filtering Status: WORKING CORRECTLY

All 1,024 zero-coordinate detections were caught and dropped at the detection node level. **Zero** zero-coordinate targets were sent to motors. The `Commanding: joint3=0.000, joint4=0.000, joint5=0.000` commands (83 total) in yanthra_move logs are **homing/recovery commands** after failed picks, not zero-position targets.

### 4.3 Spatial Pattern

Zero-spatial failures concentrate at **image edges** — consistent with stereo matching failure at periphery where left-right camera overlap is weakest. Bounding boxes starting at xmin < 0.001 or ymin < 0.001 account for ~6.3% of zero drops. arm_2 has ~2x the drops (689 vs 335), suggesting worse stereo calibration or different mounting geometry.

### 4.4 Comparison to Feb

| Metric | Feb 26 | Mar 25 |
|--------|--------|--------|
| Zero spatial events | 503 (17% of raw) | 1,024 |
| Filtering | Working (503 caught at detection, 237 reached yanthra_move) | Working (1,024 caught at detection, 0 reached yanthra_move) |
| Double-filtering needed | Yes (detection + yanthra_move) | No (all caught at detection level) |

Improvement: In Feb, 237 zero-coord detections leaked through to yanthra_move. In March, **zero** leaked through — detection-level filtering is now complete.

---

## 5. Cross-System Analysis

### 5.1 Combined Pick Statistics

| Metric | Arm 1 | Arm 2 | Combined |
|--------|-------|-------|----------|
| Cycles | 319 | 317 | **636** |
| Pick attempts | 408 | 522 | **930** |
| Cotton picked | 214 | 278 | **492** |
| Success rate | 52.5% | 53.3% | **52.9%** |
| Planning failures | 194 | 240 | **430** (see note) |
| Planning failure % | 47.5% | 46.0% | **46.2%** |
| Throughput | 97.9/hr | 71.0/hr | — |

> **Note:** Some planning failure subtotals may show ±1 discrepancy due to rounding in
> individual failure categories. The morning session added 119 failures to arm_1's previous 71.
>
> Throughput values are per-arm, computed from within-session active time.
> Clock drift does not affect these figures (see Clock Drift Notice).

### 5.2 Reachability: The #1 Bottleneck

| Metric | Value |
|--------|-------|
| Total planning failures | 430 |
| COLLISION_BLOCKED | 315 (73.3%) |
| OUT_OF_REACH | 103 (24.0%) |
| JOINT_LIMIT_EXCEEDED | 11 (2.6%) |
| Other | 1 (0.2%) |
| **Pick success when reachable** | **98.4%** (492/500) |

The arm's picking mechanism works excellently. The kinematic workspace is the constraint.

### 5.3 Detection Model Trade-Off Summary

| Factor | YOLOv11 (2-class) | YOLOv5 (1-class) |
|--------|-------------------|-------------------|
| Detection rate | 14.8-15.8% | 21.5-28.7% |
| Confidence avg | 0.680 | 0.729 |
| Filters shells | ✅ Yes (20.8% filtered) | ❌ No |
| False positives | Low | **High (empty shells detected)** |
| Wasted detections | 48.9% | **57.3%** |
| Field lighting | ⚠️ May miss cotton | ✅ More sensitive |
| Inference latency | 72ms | 66ms |

**Neither model is satisfactory.** v11 misses real cotton in field lighting. v5 finds more cotton but wastes arm movements on empty shells. The +8.4pp wasted detection rate on v5 (57.3% vs 48.9%) directly shows the shell false positive problem.

### 5.4 Border Filter Analysis

| Metric | Feb 26 | Mar 25 |
|--------|--------|--------|
| Border filter rate | 5.3% | **12.0-52.0%** |
| J4 positions | 5 | 5 → 7 |
| Impact | Minor | **Major detection loss** |

The border filter rate increased dramatically. With more J4 positions (denser scanning), more edge detections are encountered. The filter operates in image-space and doesn't benefit from more positions — it just sees more frames to filter.

**7-pos verdict:**
- arm_1: **Partially helped** — recovered 8.6pp more border-filtered cotton
- arm_2: **Did not help** — recovery rate actually dropped (76.9% → 71.6%)
- Both arms: **COLLISION_BLOCKED increased** with 7-pos (arm_1: 8→35, arm_2: 72→58 — arm_2 was already high)

### 5.5 +150mm J4 Position: Remove or Keep?

| Arm | +150mm Found | +150mm Picked | Yield |
|-----|-------------|---------------|-------|
| arm_1 | 27 | 2 | **7.4%** |
| arm_2 | 128 | 15 | **11.7%** |

+150mm consistently finds cotton that is unreachable. 155 cotton found, only 17 picked (11.0%). This position wastes scan time and generates failed pick attempts. **Consider removing +150mm** or at minimum deprioritizing it.

### 5.6 Network Health

| Metric | All Devices |
|--------|-------------|
| Ethernet Rx errors | 0 |
| Ethernet Tx errors | 0 |
| Ethernet drops | 0 |
| Link state changes | 0 |
| WiFi disconnects | 0 |

Network was solid throughout the trial. No connectivity issues between devices.

### 5.7 Boot Timing

| Device | Boot Time |
|--------|-----------|
| arm_1 (session 1, morning) | ~30s (ROS2 launch est. ~10:45:27) |
| arm_1 (session 2) | 30.25s |
| arm_1 (session 4) | 29.38s |
| arm_2 | ~30s |
| vehicle | ~30s |

Consistent ~30s boot across all devices.

---

## 6. Comparison with February Benchmarks

### 6.1 Pick Funnel

| Stage | Feb 26 (Arm1 only) | Mar 25 (Both Arms) | Change |
|-------|---------------------|---------------------|--------|
| Cycles | 151 | 636 | +321% |
| Detections accepted | 1,544 | 1,464+ | -5% (but v5 inflated) |
| Pick attempts | 1,181 | 930 | -21% (fewer instant rejections) |
| Cotton picked | 315 | 492 | **+56%** |
| Success rate | 26.7% | 52.9% | **+26.2pp** |
| Workspace rejections | 73% | 46.2% | **-27pp** |

### 6.2 Motor Health

| Metric | Feb 26 | Mar 25 | Change |
|--------|--------|--------|--------|
| J3 avg temp | 44.2°C | 45.7-45.9°C | Similar |
| J4 avg temp | 41.0°C | 42.1°C | Similar |
| J5 avg temp | 41.0°C | 42.0-43.8°C | Slightly higher |
| Motor health | 100% | 100% | ✅ Same |
| CAN errors (arms) | 0 | 0 | ✅ Same |

### 6.3 Vehicle Stability

| Metric | Feb 26 | Mar 25 | Change |
|--------|--------|--------|--------|
| Sessions (crashes) | 9 (all ODrive) | 4 (0 crashes, 1 E-stop) | **Major improvement** |
| ODrive stalls/session | 1,000-1,800+ | Session 2 only | **Improved** |
| Steering thermal | All 3 motors 73-80°C | Front only (encoder issue) | **Improved** |
| Provisioning | FAILED 8-11/12 | **12/12 passed** | **Fixed** |
| MQTT uptime | 97.7% | ~98.0% | **Improved** |

### 6.4 Detection Pipeline

| Metric | Feb 26 | Mar 25 (arm1/v11) | Mar 25 (arm2/v5) |
|--------|--------|--------------------|-------------------|
| Detection latency avg | 34-93ms | 72ms p50 | 66ms p50 |
| Zero spatial rate | 17% | ~14% | ~6.3% |
| Zero coords reaching motors | 237 leaked | **0** (fully filtered) | **0** |
| Camera temp max | 63°C | 66.7°C | 69.6°C |

---

## 7. Recommendations

### 7.1 Critical (Before Next Trial)

1. **Add startup zero-position verification for steering motors**
   - After homing, check idle current. If >0.5A at "zero", flag `ZERO_POSITION_SUSPECT`.
   - Command ±5° test movement, verify position delta matches.
   - This catches encoder drift before thermal damage.

2. **Add stall escalation limit**
   - After 3 consecutive stalls within 5 minutes on the same motor, auto-disable it.
   - Current system allowed 17 stalls + thermal runaway to 80°C.

3. **Resolve detection model trade-off**
   - Option A: Retrain v11 with more field lighting data to improve sensitivity
   - Option B: Retrain v5 with 2 classes (add shell class back)
   - Option C: Train a new v8/v11 model specifically for field conditions
   - The current choice (v11 misses cotton, v5 picks shells) is not sustainable.

### 7.2 High Priority

4. **Investigate reachability boundaries**
   - COLLISION_BLOCKED at x>0.49m accounts for 75% of planning failures.
   - Determine if collision margins are overly conservative.
   - Even 5cm workspace extension would significantly improve success rate.

5. **Remove or deprioritize +150mm J4 position**
   - 7.4-11.7% yield wastes scan time. Consider capping scan range at ±100mm.

6. **Reduce border filter margin from 5% to 3%**
   - Border filter rate jumped from 5.3% (Feb) to 12-52% (Mar).
   - The filter is too aggressive — many edge detections have valid depth.

7. **Investigate J4 action rejection pattern**
   - 89 failures with `feedback_samples=0` suggest timing/state-machine bug.
   - Not a motor fault — action server rejects before motion.

8. **Add E-stop event logging and vbus monitoring**
   - Log structured events when vbus drops to 0 or motors become UNAVAILABLE while node is running.
   - Add explicit "MOTOR POWER LOST" and "E-STOP DETECTED" events to enable post-hoc analysis.

9. **Re-enable or document J3-J4 collision interlock**
   - Collision interlock was disabled on both arms for the entire trial. Either re-enable with proper testing or formally document the risk acceptance.

10. **Fix J3 position clamping on arm_2**
    - 278 events where planner commands -0.180 but limit is -0.166. Either widen the limit or fix the planner's workspace model.

### 7.3 Medium Priority

11. **Fix model path warning** — Deploy `yolov112.blob` to `data/models/` on arm_1 RPi to eliminate fallback warning every session.
12. **Deploy `can_watchdog.service`** — Missing from arm_2 and vehicle.
13. **Fix `network_monitor` script** — Not collecting data on arm_2 (empty logs).
14. **Profile python3 memory leak** — 24MB/hour growth on arm_2.
15. **Fix detection log severity** — `detection_summary` JSON logged at ERROR level inflates error counts.
16. **Investigate CAN RX error rate on vehicle** — 220 errors/sec MCP2515 limitation contributing to ODrive cascading failures.
17. **Monitor J3 position drift** — arm_2 J3 showing degrading trend (small but non-zero).
18. **Investigate detection age increase** — arm_2 detection age increasing 90ms/hour.
19. **Fix dashboard_server memory leak** — Source identified: uvicorn `dashboard_server` at ~22MB/hr on arm_2. Profile with tracemalloc. Same growth pattern on arm_1.
20. **Fix boot reliability** — RCU stalls and journal corruption on both arms. Consider staggering node startup or increasing kernel preemption settings.
21. **Monitor disk usage** — 150MB/hr growth rate on arm_2. Add disk usage alerting before SD card fills.
22. **Fix DepthAI shave configuration** — Model compiled for 6 shaves but runtime uses 4. Evaluate performance at 4 vs 6 vs 9 shaves.
23. **Migrate from ROS_LOCALHOST_ONLY** — Deprecated; switch to ROS_AUTOMATIC_DISCOVERY_RANGE and ROS_STATIC_PEERS.

### 7.4 Low Priority

24. **Add physical homing reference** for front wheel (limit switch or index pulse) — only truly robust solution for encoder drift.
25. **Consider idle current monitoring** as ongoing health metric for all MG6010 motors.

---

## 8. Log Analyzer Output Summary

The `scripts/log_analyzer.py` was run on all 3 devices with `--field-summary --verbose`.

> **Note:** Log analyzer duration figures span wall-clock time from first to last log entry,
> which includes inter-session gaps. Active picking time is shorter. Afternoon timestamps
> reflect ~85-minute clock drift (see Clock Drift Notice above). The arm_2 "7h 21m" figure
> includes the gap from drifted Session 5 end (14:55 logged) to NTP-corrected Session 6
> start (18:05 actual) — the real span is shorter.

### 8.1 Arm1 Headline
```
~4h 11m integration test: 408 picks, 52.5% success rate (includes recovered morning session)
```

> The original log analyzer headline covered only the 3 afternoon sessions (2h 19m, 185 picks,
> 61.6%). The morning session (10:47–12:39, 223 picks, 44.8%) was recovered from journal logs
> and the totals above reflect all 4 sessions.

### 8.2 Arm2 Headline
```
7h 21m 25s integration test: 522 picks, 53.3% success rate, 4x ERROR in cotton_detection_node, 313x Communication Timeout
```

### 8.3 Vehicle Headline
```
4h 19m 5s integration test: 0 picks, 3x Motor Current Spike Detected, 3x Communication Timeout, 3038x ERROR in mg6010_controller
```

### 8.4 Analyzer Gaps Identified
- Vehicle: log analyzer reports 0 picks (expected — vehicle doesn't pick)
- Vehicle: 3,038 ERRORs in mg6010_controller — all from stall detection events
- arm_2: "Communication Timeout" count (313) includes detection timeouts + stale detection warnings
- Both arms: "ArUco detection: not instrumented (Gap 20)" and "Position tracking: not instrumented (Gap 22)" — known gaps
- Vehicle coordination shows 0 cycles for both arms — arm-vehicle coordination logging not yet integrated into analyzer

---

## 9. Data Inventory

### 9.1 Log Files Collected

| Device | ROS2 Sessions | App Logs | Field Trial Sessions | Provision Logs | Total Size |
|--------|--------------|----------|---------------------|---------------|------------|
| arm_1 | 4 (incl. recovered morning) | 5 (3 client + 2 boot) | 2 | 1 | 176 MB |
| arm_2 | 7 | 8 (6 client + 2 boot) | 2 | 1 | 294 MB |
| vehicle | 4 | 5 (3 bridge + 2 boot) | 2 | 1 | 684 MB |
| **Total** | **15** | **18** | **6** | **3** | **1.15 GB** |

### 9.2 Detection Images

| Arm | Output Images | Time Range |
|-----|--------------|------------|
| arm_1 | ~150+ | 10:52–14:34 |
| arm_2 | ~150+ | 10:52–18:08 |

### 9.3 Log Locations
```
collected_logs/2026-03-25/machine-1/
├── arm_1/
│   ├── app_logs/          (arm_client logs, boot timing JSONs)
│   ├── field_trial_logs/  (2 sessions: network, CAN, disk, memory, MQTT)
│   ├── ros2_logs/arm1/    (4 ROS2 sessions incl. recovered morning, 7 nodes each)
│   ├── images/            (detection input/output images)
│   └── provision_logs/
├── arm_2/
│   ├── app_logs/          (6 arm_client logs, 2 boot timing JSONs)
│   ├── field_trial_logs/  (2 sessions)
│   ├── ros2_logs/arm2/    (7 ROS2 sessions, 7 nodes each)
│   ├── images/            (detection images)
│   └── provision_logs/
└── vehicle/
    ├── app_logs/          (3 MQTT bridge logs, 2 boot timing JSONs)
    ├── field_trial_logs/  (2 sessions + syslog)
    ├── ros2_logs/vehicle/ (4 ROS2 sessions, 5 nodes each)
    └── provision_logs/
```
