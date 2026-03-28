# Power Budget Analysis — Pragati Cotton Picking Robot

**Configuration:** March 2026 Field Trial (2 arms + 1 vehicle)
**Date:** March 8, 2026 (original), **Updated March 27, 2026** with March 25 field data
**Target Runtime:** 4 hours minimum (OP-PWR-002), 8 hours goal (TSD)

---

## 1. Per-Subsystem Power Table

### Arm RPi (x2 for March trial)

| Subsystem | Qty/Arm | Idle (W) | Mean (W) | Peak (W) | Source |
|-----------|---------|----------|----------|----------|--------|
| MG6010 J3 (shoulder lift) | 1 | ~2 | **93** | 203 | Mar 25 field data (1,103 readings, 4.7hr) |
| MG6010 J4 (elbow) | 1 | ~1 | **12** | 58 | Mar 25 field data |
| MG6010 J5 (wrist) | 1 | ~1 | **11** | 82 | Mar 25 field data |
| End effector M1 (cotton grab) | 1 | 0 | ~10* | ~20* | *Estimated -- GAP-EE-002 |
| End effector M2 (cotton eject) | 1 | 0 | ~10* | ~20* | *Estimated -- GAP-EE-002 |
| OAK-D Lite camera | 1 | 2.5 | **2.5** | 3 | TSD (VERIFY) |
| Raspberry Pi 4B | 1 | 3 | **5.5** | 7 | Typical under ROS2 load |
| CAN transceiver (USB-CAN) | 1 | 0.5 | **0.5** | 0.5 | Standard |
| LEDs (green + red) | 2 | 0 | **0.2** | 0.4 | Negligible |
| **Per-Arm Total** | | **~10** | **~145** | **~394** | |

> J3 dominates arm power at ~64% of MG6010 draw. J4 and J5 are significantly higher than
> Feb estimates (+730% and +133% respectively) due to more active picking in March trial.

#### Feb → March Motor Data Comparison (per arm, MG6010 only)

| Joint | Feb Mean (W) | Mar Mean (W) | Change | Feb Peak (W) | Mar Peak (W) | Change |
|-------|-------------|-------------|--------|-------------|-------------|--------|
| J3 | 84 | **93** | +11% | 207 | 203 | -2% |
| J4 | 1.4 | **12** | **+730%** | 28 | **58** | +107% |
| J5 | 4.8 | **11** | **+133%** | 52 | **82** | +57% |
| **Total MG6010** | **90** | **116** | **+29%** | **287** | **343** | +20% |

> The large J4/J5 increases reflect higher picking duty cycle in March (930 attempts over
> 4.7 hours vs shorter sequences in February). J3 mean increased modestly since it runs
> continuously regardless of duty cycle. March data is more representative of operational
> power draw than February estimates.

### Vehicle RPi (x1)

| Subsystem | Qty | Idle (W) | Mean (W) | Peak (W) | Source |
|-----------|-----|----------|----------|----------|--------|
| ODrive drive motors (3-wheel) | 3 | ~5 | ~150* | ~600* | *Estimated -- ODrive telemetry not captured Mar 25 |
| MG6012-i6 steering motors | 3 | ~3 | **32** | 1,115 | Mar 25 field data (504 readings, excl. stall bug elevated draw) |
| Raspberry Pi 4B | 1 | 3 | **5.5** | 7 | Typical |
| CAN transceiver (USB-CAN) | 1 | 0.5 | **0.5** | 0.5 | Standard |
| LEDs (green + yellow + red) | 3 | 0 | **0.3** | 0.6 | Negligible |
| **Vehicle Total** | | **~12** | **~188** | **~1,723** | |

> Steering draw 2.3x higher than Feb estimate (32W vs 14W mean). steering_front drew
> elevated current (0.71A mean vs 0.19A for others) due to encoder zero shift causing
> persistent stalling. With bug fixed, steering total is ~32W (each motor ~10.5W mean).
> steering_front and steering_right hit 80C thermal limit during stall condition.

#### Vehicle Steering Thermal Data (March 25)

| Motor | Mean T (C) | Peak T (C) | Notes |
|-------|-----------|-----------|-------|
| steering_front | 51.8 | **80.0** | Hit derating limit — encoder shift bug |
| steering_left | 46.0 | 67.0 | Elevated but safe |
| steering_right | 48.7 | **80.0** | Hit limit in Session 2 |

### Shared / External

| Subsystem | Qty | Idle (W) | Mean (W) | Peak (W) | Source |
|-----------|-----|----------|----------|----------|--------|
| MQTT WiFi router | 1 | 3 | **5** | 8 | Typical |
| **Shared Total** | | **~3** | **~5** | **~8** | |

> **UPDATE (Mar 27):** Compressor and vacuum pump rows removed. The robot uses NO
> pneumatic/compressor mechanism — cotton eject is via M2 roller motor + gravity only.
> This significantly reduces system power draw and eliminates the AC vs DC compressor
> design decision.

---

## 2. Total System Power — March 2-Arm Configuration (Updated)

| Component | Feb Est. Mean (W) | Mar Actual Mean (W) | Mar Peak (W) |
|-----------|------------------|---------------------|--------------|
| Arm 1 | 119 | **145** | 394 |
| Arm 2 | 119 | **145** | 394 |
| Vehicle | 170 | **188** | 1,723 |
| Shared | 55 | **5** | 8 |
| **System Total** | **~463** | **~483 W** | **~2,519 W** |

> System mean power is +4% higher than Feb estimate for the robot subsystems, but
> significantly lower overall because the compressor/vacuum (350-2400W) has been
> eliminated from the design. **The system power budget is now dominated by the
> vehicle drive motors (ODrive, still estimated) and arm J3 gravity-holding load.**

### Projected 4-Arm Configuration (April target)

| Component | Mean (W) | Peak (W) |
|-----------|----------|----------|
| Arm 1-4 (x4) | 580 | 1,576 |
| Vehicle | 188 | 1,723 |
| Shared | 5 | 8 |
| **System Total** | **~773 W** | **~3,307 W** |

---

## 3. Battery Endurance Estimate (Updated)

**Known:** Bus voltage mean 55.0V (Mar 25 field measured, range 51.5-57.5V), safety cutoff at 40V.

Battery specs remain **unknown** (GAP-PWR-001/002/003).

### 2-Arm Configuration (483W mean draw, no compressor)

| Battery Capacity | Voltage | Energy (Wh) | Est. Runtime | Meets 4hr? |
|-----------------|---------|-------------|--------------|------------|
| 20 Ah | 48V | 960 | **1.6 hrs** | NO |
| 40 Ah | 48V | 1,920 | **3.2 hrs** | NO |
| 60 Ah | 48V | 2,880 | **4.8 hrs** | YES |
| 80 Ah | 48V | 3,840 | **6.4 hrs** | YES |
| 100 Ah | 48V | 4,800 | **7.9 hrs** | YES (8hr goal) |

### 4-Arm Configuration (773W mean draw, no compressor)

| Battery Capacity | Voltage | Energy (Wh) | Est. Runtime | Meets 4hr? |
|-----------------|---------|-------------|--------------|------------|
| 40 Ah | 48V | 1,920 | **2.0 hrs** | NO |
| 60 Ah | 48V | 2,880 | **3.0 hrs** | NO |
| 80 Ah | 48V | 3,840 | **4.0 hrs** | MARGINAL |
| 100 Ah | 48V | 4,800 | **5.0 hrs** | YES |
| 120 Ah | 48V | 5,760 | **6.0 hrs** | YES |

> With no compressor, 60 Ah at 48V meets 4-hour target for 2-arm. For 4-arm April
> configuration, need **80-100 Ah** minimum. ODrive draw is still estimated and could
> push these numbers higher.

**Assumptions:**
- 80% depth of discharge (typical for LiFePO4, conservative for Li-ion)
- No regenerative braking energy recovery
- Mar 25 mean draw includes actual picking duty cycle (~930 picks over 4.7 hours)
- ODrive draw estimated at 150W mean -- actual may be higher or lower

---

## 4. Key Unknowns Blocking Accurate Budget

| Gap ID | What's Missing | Impact | Priority | Status |
|--------|---------------|--------|----------|--------|
| **GAP-PWR-001** | Battery type (LiFePO4 vs Li-ion) | Affects voltage curve, depth of discharge, cycle life | CRITICAL | OPEN |
| **GAP-PWR-002** | Battery capacity (Ah) | Cannot calculate runtime without this | CRITICAL | OPEN |
| **GAP-PWR-003** | Battery voltage (48V nominal assumed) | Affects all power calculations | HIGH | PARTIALLY RESOLVED — bus voltage measured at 51.5-57.5V (mean 55V) |
| **GAP-PWR-004** | No system-level power measurement | All numbers are per-motor, not system-level | HIGH | OPEN — not captured Mar 25 |
| **GAP-EE-002** | EE motor model/power unknown | ~20W estimated but could be higher | MEDIUM | OPEN — M1/M2 not in motor_health logs |
| (none) | ODrive drive motor power | ~150W estimated per motor but unvalidated | HIGH | OPEN — ODrive velocity logged but no current/power telemetry |
| ~~(none)~~ | ~~Compressor decision (AC vs DC)~~ | ~~2x difference in battery draw~~ | ~~HIGH~~ | **RESOLVED — no compressor. M2 roller + gravity only.** |

---

## 5. Measurements Captured vs Planned (March 25 Field Trial)

### Must-Have Results

| Measurement | Planned | Captured? | Result |
|-------------|---------|-----------|--------|
| Total battery current draw (clamp meter) | Every 5 min | **NO** | Not captured — no system-level measurement |
| Battery voltage under load | Start/end of each hour | **PARTIAL** | Bus voltage via CAN: 51.5-57.5V (mean 55V), but not battery terminal voltage |
| ODrive power | `electrical_power` CAN telemetry | **NO** | ODrive logs have position/velocity only, no current/power |
| Compressor configuration | Document which used | **N/A** | No compressor in system (design change) |

### Nice-to-Have Results

| Measurement | Captured? | Result |
|-------------|-----------|--------|
| Per-motor current (MG6010) | **YES** | 1,607 readings across 2 arms + vehicle. Full data above. |
| RPi power draw (USB meter) | **NO** | Not measured |
| Runtime until low-voltage | **NO** | No low-voltage warnings observed (bus stayed above 51V) |
| Thermal correlation | **PARTIAL** | Motor temps captured. No RPi CPU temps (network_monitor.log had headers only). |

### Instrumentation Gaps for April Trial

1. **Add system-level current sensing** — clamp meter or hall-effect sensor on battery output, logged to ROS2 topic
2. **Enable ODrive telemetry** — `bus_voltage` and `electrical_power` CAN reads must be captured. This is the largest remaining power unknown.
3. **Log RPi CPU temperatures** — `vcgencmd measure_temp` every 30s to a ROS2 topic or file
4. **Log M1/M2 current** — end effector motors need instrumentation (add to motor_health reporting or add separate current sensing)
5. **Battery voltage trend** — log battery terminal voltage (not just bus voltage) at regular intervals

---

## 6. Arm Motor Temperature Summary (March 25 Field Trial)

| Device | Joint | Mean (C) | Q25 (C) | Q75 (C) | Max (C) | Status |
|--------|-------|---------|---------|---------|---------|--------|
| arm_1 | J3 | 46.3 | 46.0 | 48.0 | 50.0 | Safe (well below 65C derating) |
| arm_1 | J4 | 41.9 | 42.0 | 44.0 | 44.0 | Cool |
| arm_1 | J5 | 43.2 | 42.0 | 46.0 | 47.0 | Safe |
| arm_2 | J3 | 45.1 | 43.0 | 48.0 | 50.0 | Safe |
| arm_2 | J4 | 41.4 | 40.0 | 43.0 | 44.0 | Cool |
| arm_2 | J5 | 42.9 | 41.0 | 47.0 | 48.0 | Safe |

> All arm motors stayed below 50C over 4.7 hours of operation. No thermal concerns at
> current duty cycle. Ambient field temperature estimated 33-43C (cold-start motor temps).
> **At higher duty cycles (6K-10K picks/10hr vs ~930/4.7hr), J3 temperature will increase.**
> Thermal monitoring recommended for extended reliability tests.

---

## 7. Recommendations (Updated)

1. **Resolve battery specs immediately** (GAP-PWR-001/002/003) — still the #1 blocker.
   For 4-arm April config, need minimum 80 Ah at 48V for 4-hour runtime.

2. **Enable ODrive telemetry logging** before April trial — drive motors are the largest
   remaining unknown. Budget 150W mean per motor but could be higher under field conditions
   (soft soil, slopes, payload).

3. **Target 80-100 Ah at 48V** for April trial with 4 arms — provides 4-5 hours runtime
   with margin. 60 Ah is sufficient for 2-arm only.

4. **No compressor in system** — this is a significant simplification. Previous scenarios
   assumed 350-2400W compressor draw. With M2 roller + gravity cotton eject, system power
   is 60-80% lower than original worst case.

5. **Add system-level power monitoring for April** — clamp meter on battery output logged
   to ROS2 topic. Critical for validating these estimates.

6. **Monitor J3 thermal at higher duty cycles** — current 50C max is safe, but 6K-10K
   picks/10hr tests will increase duty cycle 2-3x. J3 could approach 65C derating onset.

7. **Investigate steering encoder zero shift** — caused steering_front to hit 80C thermal
   limit. Bug was fixed mid-trial but root cause (encoder initialization) needs permanent fix.

---

## Appendix A: Power Architecture Diagram

```
[48V Battery] ──┬── [CAN Bus 48V] ──┬── Arm1 RPi + 3x MG6010 + OAK-D + EE motors
                │                    ├── Arm2 RPi + 3x MG6010 + OAK-D + EE motors
                │                    ├── (Arm3 RPi + 3x MG6010 + OAK-D + EE motors) — April
                │                    ├── (Arm4 RPi + 3x MG6010 + OAK-D + EE motors) — April
                │                    └── Vehicle RPi + 3x MG6012-i6 steering
                │
                ├── [ODrive Bus] ──── 3x Drive Motors (front + left-rear + right-rear)
                │
                └── [5V Regulator] ── RPi 4B x5 (USB-powered from 48V->5V converter)

Cotton eject: M2 roller motor (reverse belt) + gravity drop to collection box
No compressor / pneumatic / vacuum in system.
```

## Appendix B: Data Source Details (March 25 Field Trial)

| Metric | Source Files | Records | Time Range | Duration |
|--------|-------------|---------|------------|----------|
| arm_1 MG6010 | ROS2 logs + journalctl | 549 | 10:47-15:28 | 4.7 hr |
| arm_2 MG6010 | ROS2 logs + FTL | 554 | 10:50-18:11 | multi-session |
| Vehicle MG6012 | ROS2 logs | 504 | 10:44-15:02 | 4.3 hr |
| Bus voltage | CAN motor_health | 1,607 | 10:44-18:11 | — |
| Motor temperature | CAN motor_health | 1,607 | 10:44-18:11 | — |

Log location: `collected_logs/2026-03-25-field-trial-merged/`
