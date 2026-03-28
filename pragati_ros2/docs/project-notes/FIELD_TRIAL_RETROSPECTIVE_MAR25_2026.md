# Pragati Field Trial Retrospective — March 25, 2026

**Scope:** February 26 → March 25, 2026 (one development cycle, 28 days)
**Participants:** [Team to fill in]
**Date:** March 25, 2026

---

## Executive Summary

This retrospective covers one full development cycle between the February 26 and March 25
field trials. The cycle shipped 112 OpenSpec changes across 28 days (4.0/day), targeting
every major failure mode identified in the February trial report. The headline result:
**pick success rate nearly doubled** (26.7% to 52.9%), **vehicle crashes dropped from 9
to zero**, and **two arms operated simultaneously for the first time**. However, new issues
emerged (encoder zero shift, border filter regression, J4 action rejections) and the #1
bottleneck — workspace reachability — remains unsolved at 46.2% of failures.

The system is transitioning from "can it work at all?" to "can it work reliably?" This
retrospective documents every dimension of that transition with specific log evidence.

> **Clock Drift Note:** Afternoon session timestamps are ~85 min behind actual IST due to
> `fake-hwclock` restoring stale time after lunch reboot (no re-provision for NTP sync).
> Morning timestamps are accurate. Within-session durations are unaffected.

---

## 1. The Numbers: Feb 26 → Mar 25 Side-by-Side

### 1.1 Overall Trial Comparison

| Metric | Feb 26 | Mar 25 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| Arms tested | 1 | 2 | +1 arm | IMPROVED |
| Active picking time | ~158 min | ~442 min | +180% | IMPROVED |
| ROS2 sessions (vehicle) | 9 (all crash-restarts) | 4 (3 clean + 1 E-stop, CAN dead) | -56% | MAJOR IMPROVEMENT |
| ROS2 sessions (arm) | 9 (6 operational) | 11 across 2 arms (all operational) | All productive | IMPROVED |
| Total data collected | ~200 MB est. | 1,154 MB | ~5x more | IMPROVED |
| Wall clock duration | ~4.5 hours | ~6 hours (field) + 6 min (lab) | +33% | More productive |

**Analysis:** The February trial was dominated by firefighting — 9 vehicle crash-restarts
meant the team spent more time recovering than picking. March ran ~33% longer (field time)
with zero vehicle crashes and all arm sessions productive. The 5x increase in data collection
reflects both longer runtime and the new monitoring infrastructure (can_stats,
process_memory, disk_monitor) that did not exist in February.

The shift from 1-arm to 2-arm operation is a milestone: it validates the distributed
architecture (dedicated RPi per arm, MQTT coordination, block-and-skip collision
avoidance) under real field conditions.

### 1.2 Pick Performance Evolution

| Metric | Feb 26 | Mar 25 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| Total pick attempts | 1,181 | 930 | -21% | BETTER (fewer wasted) |
| Cotton picked | 315 | 492 | +56% | IMPROVED |
| Pick success rate | 26.7% | 52.9% | +26.2 pp | MAJOR IMPROVEMENT |
| Success when reachable | Unknown | 98.4% | New metric | EXCELLENT |
| Cycle time avg | ~1,800 ms | ~1,800 ms | Same | STABLE |
| Peak throughput | 1,272 picks/hr | TBD | — | — |
| Consecutive failure chains (3+) | 104 | Fewer (more reachable cotton) | Reduced | IMPROVED |
| Eject operations | 314 | ~492 | +57% | Matches picks |

**Analysis:** The 21% reduction in pick attempts alongside a 56% increase in cotton picked
is the clearest evidence that the system is making smarter decisions. February's strategy
was "attempt everything, succeed rarely." March's strategy is "attempt selectively, succeed
often."

The new "success when reachable" metric (98.4%) is the most important number in this table.
It proves that **the picking mechanism itself is essentially solved** — when the arm can
physically reach the cotton, it picks it almost every time. The remaining problem is
entirely about getting the arm to the right place, which is a detection + workspace +
positioning problem, not a gripper problem.

Cycle time remained stable at ~1,800 ms despite the addition of workspace validation,
border filtering, and zero-coordinate filtering. The pipeline overhead of these safety
checks is negligible.

### 1.3 Failure Mode Shift

| Failure Mode | Feb 26 | Mar 25 | Delta | Verdict |
|-------------|--------|--------|-------|---------|
| Workspace rejections (% of attempts) | 73% (841/1,181) | 46.2% (430/930) | -27 pp | IMPROVED but still #1 |
| COLLISION_BLOCKED (of failures) | ~88% | 73.1% | -15 pp | IMPROVED |
| Zero spatial coords (total) | 503 (17%) | 1,024 (~17%) | Rate same | STABLE (hardware limit) |
| Zero spatial coords leaked to motors | 237 | 0 | -100% | MAJOR FIX |
| Border filter rate | 5.3% (453) | 12–52% | +7–47 pp | REGRESSED |
| Wasted detection rate | 79.6% | 48.9–57.3% | -22–31 pp | IMPROVED |
| Stale detections (>2s) | 19.6% (232) | TBD | — | — |
| J4 action rejections | Not measured | 89 | New issue | NEW ISSUE |

**Analysis:** The failure mode distribution shifted significantly. In February, workspace
rejections dominated at 73% — nearly three quarters of all attempts were doomed before the
arm moved. March brought this down to 46.2%, a 27 percentage point improvement driven by
better detection filtering and smarter target selection.

However, three concerning trends emerged:

1. **Border filter regression** is the most problematic new issue. The rate jumped from
   5.3% to 12–52% depending on the session. The 5% margin was designed as conservative
   safety, but field data shows it is rejecting valid detections that are near frame edges
   but within the workspace. This is a tuning problem, not an architecture problem.

2. **J4 action rejections** (89 occurrences) are a new failure mode not present in
   February. These manifest as feedback_samples=0 responses, indicating a timing or
   state-machine bug in the J4 motor controller. They self-recover but waste pick cycles.

3. **Zero-coordinate rate unchanged at ~17%** — this is a fundamental limitation of
   passive stereo depth on white cotton against bright sky backgrounds. No software fix
   is possible. The critical improvement is that all 1,024 zero-coord detections were
   filtered before reaching motors (vs. 237 leaked in February).

### 1.4 Vehicle Stability

| Metric | Feb 26 | Mar 25 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| Vehicle crashes | 9 | 0 | -100% | ELIMINATED |
| ODrive stall events/session | 1,000–1,800+ | Session 2 errors only | Isolated | MAJOR IMPROVEMENT |
| Steering peak temps | 73–80 C (all 3 motors) | 80 C (front only, encoder shift) | Isolated to 1 motor | IMPROVED |
| Steering health scores | 0.6–1.0 | 1.0 (when encoder correct) | Healthy | IMPROVED |
| CAN errors (vehicle) | CAN setup error on every launch | 1.59M RX errors Session 2 | Different problem | MIXED |
| Self-test result | 4/5 passed | Not in Mar logs | — | — |
| Joystick integration | Manual | Active (joystick deactivates drive_stop) | Working | NEW |

**Analysis:** Vehicle stability is the single biggest transformation between trials. The
February trial was defined by a vicious cycle: ODrive stall → crash → restart → stall again.
The team spent more time restarting the vehicle than picking cotton.

The changes that fixed this span multiple OpenSpec changes:
- `2026-02-16-odrive-vehicle-drive-integration`: PID tuning and error recovery
- `2026-03-02-field-trial-readiness-fixes`: Launch and configuration hardening
- `2026-03-06-motor-control-safety`: Safety limits and watchdogs

March's vehicle ran three clean sessions with zero crashes, plus one session where the
E-stop was activated (between Sessions 3 and 4), leaving the CAN bus dead and all motors
UNAVAILABLE for approximately 30 minutes. The E-stop event was operator-initiated, not a
software failure. The only other vehicle issue was an encoder zero shift on the front
steering motor, which caused 42 stalls and a thermal cascade to 80 C over 4 hours. This
is a hardware failure mode that the software did not detect — a gap addressed in Section 6.

The 1.59M CAN RX errors in Session 2 are a separate issue from February's CAN setup errors.
The February problem was a configuration bug (CAN interface not initializing). The March
problem is a hardware throughput limitation of the MCP2515 SPI-to-CAN bridge under high
bus load. Different root cause, different fix path.

### 1.5 Detection System

| Metric | Feb 26 | Mar 25 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| Model | YOLOv11 2-class (fallback) | v11 2-class + v5 1-class (mixed) | More complex | MIXED |
| Model deployed correctly | NO (fallback 9 times) | Mostly (v11 on arm_1, v5 switched on arm_2) | Better | IMPROVED |
| Detection latency | 34–93 ms | ~72 ms avg | Similar | STABLE |
| Camera temp | 51–63 C (mean 60.1 C) | 35–50 C (lower) | Cooler | IMPROVED |
| Images saved | 1,708 | 3,266 | +91% | More data |
| USB errors | 0 | 0 | Clean | STABLE |

**Analysis:** The detection story is mixed. On the positive side: model deployment mostly
worked (February fell back to the wrong model 9 times), camera temperatures dropped
significantly (cooler ambient or better thermal management), latency remained stable, and
we collected nearly twice as many images for future training.

On the negative side: the team ran two different models across two arms, switched models
mid-trial on arm_2, and still has no clear winner. YOLOv11 2-class filters shells but
misses cotton in certain field lighting conditions. YOLOv5 1-class detects more cotton but
includes shell false positives. This indecision needs resolution before the April trial.

The 72 ms average detection latency is well within the ~1,800 ms pick cycle budget.
Detection speed is not a bottleneck.

### 1.6 Infrastructure and Reliability

| Metric | Feb 26 | Mar 25 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| MQTT uptime | 97.7% | ~98.0% | +0.3 pp | IMPROVED |
| MQTT disconnects | 2 unexpected | 5 unexpected (all session boundaries) | Similar | STABLE |
| Provisioning vehicle | FAILED 11/12 | PASSED 12/12 | FIXED | MAJOR FIX |
| Provisioning arm | FAILED 8/9 | PASSED 12/12 | FIXED | MAJOR FIX |
| CAN bus (arms) | 0 errors | 0 errors | Clean | STABLE |
| Network monitor data | 0 rows (broken) | 0 rows on arm_2, working on arm_1 | Partially fixed | PARTIAL |
| RTC drift | ~1.5 hours | ~85 min (post-reboot, no re-provision) | Similar | SAME |
| DDS discovery | Not tested | No issues | Working | GOOD |

**Analysis:** Infrastructure reliability improved across the board. The most impactful fix
was provisioning: February's script failed 8–11 out of 12 checks because it required
internet access that was unavailable in the field. Changes `2026-02-18-sync-provision-flag`
and `2026-02-19-field-ops-deployment-hardening` rewrote provisioning to work fully offline.
March passed all 24 checks (12 vehicle + 12 arm) with zero failures.

MQTT maintained its rock-solid performance at ~98.0% uptime. The 5 unexpected disconnects
all occurred at session boundaries (operator restarts), not during active picking. Auto-
reconnection worked every time.

The network_monitor remains partially broken — working on arm_1 and vehicle but producing
0 data rows on arm_2. This is a deployment or configuration issue, not an architectural one.

RTC drift did NOT improve from February. Morning timestamps were accurate because NTP
synchronization ran during initial provisioning. However, after the lunch shutdown at
~12:40 IST and reboot at ~14:05 IST, devices were not re-provisioned, so `fake-hwclock`
restored the stale 12:40 time — producing ~85 minutes of clock drift on all 3 devices
for the entire afternoon. All afternoon session timestamps are ~85 min behind actual IST.
This is the same class of problem as February's ~1.5-hour drift: no battery-backed RTC
and no automatic clock sync on reboot. Within-session durations are unaffected (both
start and end drifted equally), but absolute timestamps and cross-session gaps are wrong
in the raw logs. Accurate timestamps remain critical for cross-node log correlation, and
this problem will recur on every reboot until an automatic NTP or PTP sync is added to
the boot sequence.

### 1.7 Data Collection and Tooling

| Metric | Feb 26 | Mar 25 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| Total log volume | ~200 MB est. | 1,154 MB | ~5x | Much more data |
| Working monitoring tools | Partial | 5/8 tools working | Better | IMPROVED |
| can_stats | Not present | Working | NEW | GOOD |
| process_memory | Not present | Working (24 MB/hr leak found) | NEW | GOOD |
| disk_monitor | Not present | Working | NEW | GOOD |
| field_trial_manager | New | 6 sessions recorded | Working | GOOD |
| network_monitor | Broken (0 rows) | Broken on arm_2, working elsewhere | Partially fixed | PARTIAL |
| log_analyzer.py | Basic | --field-summary --verbose mode | Enhanced | IMPROVED |

**Analysis:** The monitoring infrastructure expansion is one of the most strategically
valuable improvements of the cycle. Five new monitoring tools were deployed, and every one
of them produced actionable data:

- **can_stats** confirmed 0 CAN errors on arm buses and quantified the 1.59M RX error
  problem on vehicle CAN.
- **process_memory** caught the 24 MB/hr memory leak on arm_2's python3 process — this
  would have caused an OOM crash on a long run.
- **disk_monitor** confirmed sufficient disk space throughout the trial.
- **field_trial_manager** recorded all 6 sessions with start/stop timestamps, enabling
  precise session-level analysis.
- **log_analyzer.py** enhancements (--field-summary, --verbose) made post-trial analysis
  significantly faster.

The 5x increase in data volume (200 MB to 1,154 MB) reflects both longer runtime and more
comprehensive instrumentation. This data is the foundation for every improvement in this
document.

### 1.8 Deployment and Operations

| Metric | Feb 26 | Mar 25 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| Manual interventions | 9 vehicle restarts + J5 belt repair + EE runaway | Power cycle (encoder fix) + model switch + coordinated restart | Fewer, less severe | IMPROVED |
| Boot to ready time | Unknown | Arms ~30s, Vehicle ~53s | Fast | GOOD |
| Provisioning | Script failed (no internet) | All passed | FIXED | MAJOR FIX |
| Deploy process | Unknown issues | No deploy errors in logs | Clean | GOOD |
| Operator knowledge | First field trial | Second trial, operators knew common issues | Better | IMPROVED |

**Analysis:** Operational maturity improved significantly. February required 9 manual vehicle
restarts, a J5 belt repair, and an end-effector runaway recovery. March's interventions
were planned and less disruptive: one power cycle to attempt encoder correction, one
deliberate model switch on arm_2, and coordinated session restarts.

Boot times are fast and predictable: arms operational in ~30 seconds, vehicle in ~53 seconds.
This means a restart penalty is under 1 minute, which is acceptable for field operations.

The provisioning fix is arguably the highest-ROI change of the cycle. February's provisioning
failures meant the team spent the first hour of the trial debugging deployment issues.
March's team arrived, ran provisioning, got 24/24 green checks, and started picking.

---

## 2. What Went Well (Continue These)

### 2.1 Pick success rate doubled

26.7% to 52.9% (+26.2 pp). This is the single most important metric improvement. When
cotton IS within reach, the arm picks it 98.4% of the time. The picking mechanism — gripper
actuation, vacuum, eject cycle — is essentially solved. Every remaining improvement comes
from getting the arm to the right place, not from improving what happens when it gets there.

**Evidence:** 492 successful picks from 930 attempts (Mar) vs. 315 from 1,181 (Feb).
Fewer attempts, more picks. The system wastes less time on unreachable targets.

### 2.2 Vehicle stability transformed

9 crashes to 0. The ODrive PID tuning, error recovery, and safety limit changes
(`2026-02-16-odrive-vehicle-drive-integration`, `2026-03-02-field-trial-readiness-fixes`,
`2026-03-06-motor-control-safety`) eliminated the stall-crash-restart cycle that defined
the February trial.

**Evidence:** 3 clean vehicle sessions + 1 E-stop session (CAN bus dead). Zero unplanned restarts. ODrive errors isolated to
Session 2 only (encoder-related), not systemic.

### 2.3 Zero-coordinate filtering works 100%

February leaked 237 zero-coord detections to the motor subsystem, causing the arm to move
to nonsensical positions. March filtered all 1,024 zero-coord detections before they
reached motors. The fix from `2026-02-17-fix-zero-coordinate-detections` is rock solid.

**Evidence:** 1,024 zero-coord detections logged, 0 leaked to motor commands. 100%
filtering rate.

### 2.4 Provisioning completely fixed

From failing 8–11 out of 12 checks (Feb) to passing all 24 checks across vehicle and both
arms (Mar). Changes `2026-02-18-sync-provision-flag` and
`2026-02-19-field-ops-deployment-hardening` rewrote the provisioning system to work without
internet access.

**Evidence:** 12/12 vehicle checks passed. 12/12 arm checks passed. Zero provisioning
failures.

### 2.5 Two-arm operation validated

First time both arms ran simultaneously in the field. Block-and-skip collision avoidance
worked correctly. No inter-arm conflicts, no shared-resource contention, no DDS discovery
issues.

**Evidence:** 11 arm sessions across 2 arms, all operational. Both arms picked cotton
concurrently. MQTT arm status flowing correctly throughout.

### 2.6 MQTT rock solid

~98.0% uptime with auto-reconnection working correctly. Arm status, trial session commands,
and monitoring data all flowed reliably. The 5 unexpected disconnects were all at session
boundaries, not during active picking.

**Evidence:** ~98.0% uptime (up from 97.7%). 5 disconnects, all at session boundaries.
Zero data loss during active picking.

### 2.7 Monitoring infrastructure expanded

Five new monitoring tools deployed, all producing useful data. The process_memory monitor
caught a 24 MB/hr memory leak on its first deployment. The can_stats monitor quantified
the vehicle CAN error problem. Investment in observability is paying immediate dividends.

**Evidence:** can_stats, process_memory, disk_monitor, ethtool_stats, fix_verification all
produced actionable data. 5/8 monitoring tools working.

### 2.8 Boot times fast

Arms operational in ~30 seconds, vehicle in ~53 seconds. No boot delays, no initialization
failures. The systemd service configuration and ROS2 launch sequence are stable.

**Evidence:** Consistent boot times across all 15 sessions (11 arm + 4 vehicle).

### 2.9 Data collection comprehensive

1,154 MB of structured data vs. ~200 MB in February. Images (3,266), ROS bags, field trial
sessions, CAN statistics, process memory profiles, and disk usage all captured. This data
enables the detailed analysis in this document.

**Evidence:** 1,154 MB total. 3,266 images saved (vs. 1,708 in Feb). 6 field trial sessions
recorded by field_trial_manager.

### 2.10 Development velocity

112 OpenSpec changes shipped in 28 days (4.0/day). Changes ranged from critical safety fixes
(9 completed) to dashboard redesign to motor control decomposition. The OpenSpec workflow
enabled parallel development with full traceability.

**Evidence:** 112 changes in openspec/archive. 5 plans written. 3 RCA documents. 13+
packages modified.

---

## 3. What Went Wrong (Fix These)

### 3.1 Encoder zero shift undetected

The front wheel encoder latched 90 degrees off at some point during operation. The system
allowed 42 stalls and a thermal cascade to 80 C over 4 hours before operators noticed. No
software detection exists for this failure mode. The motor protection system treated each
stall as an isolated event rather than recognizing the pattern.

**Impact:** ~4 hours of degraded vehicle operation. Potential motor damage from sustained
thermal stress. Operator had to visually identify the problem.

**Root cause:** No startup hardware validation. No stall-rate escalation detection. The
`checkReachability()` function is still a placeholder.

### 3.2 Detection model confusion

Two models in the field (v11 on arm_1, v5 on arm_2). Mid-trial model switch on arm_2. No
clear winner: v11 filters shells but misses cotton in field lighting; v5 detects more but
includes shells. The team made a real-time model decision under field pressure, which is
not a reliable process.

**Impact:** Inconsistent data across arms. Cannot compare arm_1 and arm_2 pick rates
directly. No baseline for model evaluation.

**Root cause:** No model validation protocol. No decision framework for model selection
before field day.

### 3.3 Border filter rate exploded

5.3% (Feb) to 12–52% (Mar). The 5% margin was designed as conservative safety but is
rejecting valid detections near frame edges. The filter does not account for detection size
or confidence — a high-confidence detection touching the 5% border zone is rejected
identically to a low-confidence fragment.

**Impact:** Rejecting 12–52% of detections means throwing away significant picking
opportunities. At 52%, more than half of all detections are discarded before workspace
evaluation.

**Root cause:** Fixed percentage margin too aggressive for the OAK-D Lite's field of view.
No adaptive filtering based on detection properties.

### 3.4 +150mm J4 position nearly useless

The +150mm J4 scan position yielded only 7.4–11.7% pick success. It finds cotton
(detections are valid) but almost all targets at this extension are beyond the arm's
reachable workspace, resulting in COLLISION_BLOCKED rejections.

**Impact:** Every scan cycle that includes +150mm wastes time that could be spent on
positions with higher yield. At ~1,800 ms per cycle, this adds up.

**Root cause:** The +150mm position extends the camera field of view beyond the arm's
physical workspace. Detection without reachability is waste.

### 3.5 Vehicle CAN RX errors

1.59M RX errors in Session 2 (~220/sec sustained). The MCP2515 SPI-to-CAN bridge cannot
keep up with the bus traffic volume when ODrive error recovery generates burst traffic.
This caused cascading ODrive communication failures: 29,950 WARN/ERROR lines in Session 2
logs.

**Impact:** ODrive command reliability degraded during Session 2. Motor responses became
unpredictable during error bursts.

**Root cause:** MCP2515 hardware SPI throughput limitation. Not a software bug.

### 3.6 J4 action rejections

89 failures with feedback_samples=0 across the trial. The J4 motor controller occasionally
returns zero feedback samples, indicating either a timing race in the state machine or a
communication dropout. The system self-recovers (next attempt succeeds) but each failure
wastes a pick cycle.

**Impact:** 89 wasted pick cycles. At ~1,800 ms each, approximately 160 seconds of lost
picking time.

**Root cause:** Timing or state-machine bug in J4 motor controller. Not investigated yet.

### 3.7 network_monitor still broken on arm_2

The network monitor produced 0 data rows on arm_2 despite running. It works correctly on
arm_1 and the vehicle. This is a deployment or configuration issue specific to arm_2.

**Impact:** No network health data for arm_2. Cannot diagnose network issues on that node
after the fact.

**Root cause:** Not investigated. Likely a missing configuration or permission issue.

### 3.8 E-stop used but not instrumented

The hardware E-stop was physically activated during the trial (between Sessions 3 and 4).
It successfully cut motor power — Session 4 showed CAN bus dead with all motors reporting
UNAVAILABLE status for approximately 30 minutes. However, NO logging or instrumentation
captured the E-stop event itself. There are no structured log entries for motor power loss,
no vbus voltage transition records, and no CAN read timeout errors logged (the mg6010
driver fails silently when CAN reads time out).

**Impact:** Safety mechanism works mechanically but is invisible to software. Post-incident
analysis required manual log correlation to infer that the E-stop was activated. In a
multi-arm scenario, operators would have no dashboard indication that an E-stop fired.

**Root cause:** No structured E-stop event logging exists. No vbus voltage monitoring. CAN
read timeout errors in the mg6010 driver are silently swallowed rather than logged.

### 3.9 Detection log severity wrong

The detection_summary JSON is logged at ERROR level instead of INFO. This inflates error
counts in log analysis and makes it harder to distinguish real errors from routine
operational data.

**Impact:** Log analysis noise. Every detection summary appears as an error, obscuring
actual error conditions.

**Root cause:** Logging level misconfigured in detection node. Simple fix, not yet applied.

### 3.10 Memory leak on both arms

The process_memory monitor detected 24 MB/hr growth in python3 on arm_2. On a Raspberry
Pi 4B with 4–8 GB RAM, this will cause an OOM crash in ~20–30 hours of continuous operation.
Current trials run 4–8 hours, so this has not manifested as a crash yet, but it will on
longer runs.

The primary leaker is `dashboard_server` (uvicorn) at ~22 MB/hr. `rpi_agent` shows a
+61.6 MB initialization spike followed by ~1.9 MB/hr steady-state growth. arm_1 also
exhibits memory growth (13 MB → 174 MB over the trial), confirming this is not arm_2-
specific. Neither `dashboard_server` nor `rpi_agent` restarts between ROS2 sessions,
so memory accumulates across the entire trial day.

**Impact:** Time bomb on both arms. Will crash on any run longer than ~20 hours.

**Root cause:** `dashboard_server` (uvicorn) is the primary leaker. Likely unclosed
connections, growing response caches, or WebSocket session accumulation. `rpi_agent`
initialization spike suggests large data structures loaded once and never released.

### 3.11 Collision interlock disabled on both arms

J3-J4 collision interlock was DISABLED via parameter in every session on both arms. Every
motor controller startup logged: `collision_interlock_disabled: J3-J4 collision interlock
is DISABLED via parameter`. This safety feature was intentionally disabled for the field
trial but was not documented or reviewed. If both arms had been in close proximity, this
could have resulted in mechanical collision.

### 3.12 J3 position clamping (arm_2)

278 events where the motion planner commanded J3 to -0.180 but the configured limit is
-0.166, resulting in automatic clamping. Distribution: S1=6, S3=124, S4=67, S5=81. This
systematic 8.4% overshoot suggests the planner's workspace model and the motor
controller's joint limits are miscalibrated.

### 3.13 Boot reliability issues (both arms)

Both arms experienced kernel-level issues during boot: RCU preempt stalls (6 on arm_1 S2,
4+ on arm_2), corrupted journal files requiring rename, and
NetworkManager-wait-online.service failures (arm_2 Boot 1). arm_2's first boot didn't
complete after 80s with 3 blocking jobs remaining. Vehicle RPi hit a **CPU thermal CRITICAL
at 80.8°C** within 6 minutes of Session 1 boot — all nodes starting simultaneously plus
ODrive polling saturated the CPU. These issues indicate CPU contention from all services
starting simultaneously on RPi 4B's 4 cores. Consider staggered node startup.

---

## 4. What Stayed the Same (Unresolved)

### 4.1 Workspace reachability is STILL the #1 bottleneck

Dropped from 73% to 46.2% of pick failures but still accounts for nearly half of all
rejections. The COLLISION_BLOCKED threshold at x > 0.49m has not changed. The arm's physical
reach (0.25–0.56 m) cannot be extended by software.

**Why it persists:** This is fundamentally a geometry problem. The camera sees cotton at
0.2–3.0 m depth, but the arm can only reach 0.25–0.56 m. No amount of software filtering
will change the physical workspace. The only solutions are mechanical (longer arm, different
mounting) or operational (better vehicle positioning, multiple passes).

**Impact on next trial:** If workspace reachability stays at 46.2%, the theoretical ceiling
on pick success rate is ~54% (all reachable cotton picked perfectly). Reaching 80%+ success
rate requires solving this.

### 4.2 Camera-workspace mismatch is STILL architectural

The camera FOV covers 0.2–3.0 m depth. The arm workspace covers 0.25–0.56 m. This means
the camera sees approximately 10x more volume than the arm can reach. Every detection
outside the arm's workspace is wasted computation and a wasted pick cycle if it passes
filters.

**Why it persists:** The OAK-D Lite is mounted on the arm with a fixed geometry that
cannot be changed without mechanical redesign. The L3 camera offset and L5 depth control
parameters were scheduled for March investigation but never started.

### 4.3 Zero-spatial coordinate rate unchanged at ~17%

~17% of detections have (0, 0, 0) spatial coordinates in both February and March. This is
a fundamental limitation of passive stereo depth estimation on white cotton against bright
sky backgrounds. The stereo matching algorithm cannot find correspondences on textureless
white surfaces.

**Why it persists:** Hardware limitation of passive stereo. Active IR stereo (structured
light) or LiDAR fusion would address this, but neither is in the current hardware design.

**Mitigation:** The filtering fix means these detections no longer cause harm (0 leaked to
motors in March), but they still consume 17% of the detection pipeline's throughput.

### 4.4 No pre-flight hardware validation

There is still no automated check that catches hardware anomalies before operation begins.
The encoder zero shift (Section 3.1) ran undetected for 4 hours. The `checkReachability()`
function remains a placeholder. No motor health baseline is established at startup.

**Why it persists:** Pre-flight validation was not in any of the 112 OpenSpec changes.
It was identified as a gap in the February report but deprioritized in favor of
higher-impact fixes.

### 4.5 L3 camera offset and L5 depth control never investigated

Both were listed in the March field trial plan as investigation items. Neither was started.
Camera pitch angle was never verified. L5 depth control was never tested. These parameters
directly affect the camera-workspace alignment problem (Section 4.2).

**Why they persist:** Deprioritized in favor of safety fixes and vehicle stability work.
The 112 changes shipped were necessary, but these investigation items fell off the backlog.

---

## 5. What to Continue

### 5.1 OpenSpec change management

112 changes tracked with full artifact chains (proposal, specs, design, tasks). This
enabled parallel development across multiple workstreams, provided traceability from
requirement to implementation, and made it possible to write this retrospective with
specific change references. The workflow overhead is justified by the coordination value.

### 5.2 Log-driven development

The cycle that produced the 26.2 pp pick rate improvement was: field logs from February
trial → root cause analysis documents → targeted OpenSpec changes → March trial validation.
Every fix was informed by specific log evidence, not guesswork. Continue this cycle.

### 5.3 Monitoring infrastructure investment

Each new monitor immediately found issues. process_memory found the 24 MB/hr leak.
can_stats quantified the 1.59M RX error problem. The ROI on monitoring tools is
consistently high because they surface problems that would otherwise require hours of
manual log analysis.

### 5.4 Provisioning validation

The provision check script now catches deployment issues before they waste field time.
February lost approximately 1 hour to provisioning failures. March lost 0 minutes.
Running provisioning checks should be a mandatory pre-field gate.

### 5.5 Block-and-skip collision avoidance

Simple, effective, zero collisions between arms. The algorithm avoids over-engineering:
it does not try to coordinate arm movements in real time; it simply skips targets that
another arm has claimed. Right level of complexity for the current stage.

### 5.6 Stop-and-pick operational mode

Proven at scale: 930 picks across 2 arms over ~442 minutes. The vehicle stops, arms pick,
vehicle moves. This mode eliminates the complexity of picking while moving and is the
correct operational mode until the pick mechanism is optimized for speed.

### 5.7 Field trial documentation

Comprehensive reports (February field trial report, March field trial report, RCA
documents, analysis notes) enable data-driven decisions. The February report directly
informed all 112 March changes. This retrospective is itself a product of the
documentation practice.

### 5.8 Pre-field testing

The March 24 pre-field test caught issues before the March 25 field day. This practice
should be mandatory: every field trial should be preceded by a controlled pre-field test
at least 24 hours before.

---

## 6. What to Change

### 6.1 Add startup hardware validation

**Priority: CRITICAL**

The system must detect encoder shifts, motor anomalies, and camera calibration issues
BEFORE picking starts. Current system trusts all hardware blindly. Specific requirements:

- Motor position self-test at startup (compare encoder reading to expected home position)
- Stall-rate escalation detection (3 stalls in 5 minutes → auto-disable motor, alert
  operator)
- Camera intrinsic/extrinsic sanity check (verify depth values are in expected range)
- `checkReachability()` must be implemented, not a placeholder

### 6.2 Resolve detection model before next trial

**Priority: HIGH**

No more mid-trial model switches. The team must decide on one validated model and deploy it
to all arms before the trial. Options:

- Retrain YOLOv11 with March field images (3,266 available)
- Retrain YOLOv5 2-class with March field images
- Evaluate YOLOX (deferred twice already)
- Implement confidence gating (run both models, accept only high-confidence intersections)

The decision must be made and validated on bench before April trial.

### 6.3 Reduce border filter margin (5% to 3%)

**Priority: HIGH**

Data shows the 5% margin is too aggressive, rejecting 12–52% of detections. Defense-in-depth
means rejected edge detections will still fail at the workspace check if they are truly
unreachable. Reducing to 3% recovers valid detections while maintaining safety. Consider
adaptive filtering that accounts for detection size and confidence.

### 6.4 Remove +150mm J4 position

**Priority: MEDIUM**

Data proves it wastes time: 7.4–11.7% yield vs. 55%+ for other positions. Reallocate scan
time to finer steps within the effective range (0 to +100 mm). This is a configuration
change, not a code change.

### 6.5 Add stall escalation limit

**Priority: CRITICAL**

3 stalls in 5 minutes → auto-disable affected motor, alert operator. No more 42-stall
thermal cascades running undetected for 4 hours. This is a safety requirement. The current
per-stall recovery treats each event independently and has no concept of "this motor is
failing repeatedly."

### 6.6 Add E-stop instrumentation and logging

**Priority: HIGH**

The E-stop was used during the March trial and successfully cut motor power, but no
instrumented logging captured the event. The focus shifts from testing the E-stop to
ensuring it is observable:

1. Add vbus voltage transition logging — log voltage drop from nominal to zero with
   timestamp when motor power is lost
2. Add structured "MOTOR_POWER_LOST" event logging — a single high-severity log entry
   when all motors transition to UNAVAILABLE simultaneously
3. Add mg6010 CAN read timeout error logging — currently the driver silently swallows
   CAN read timeouts, making it impossible to distinguish "E-stop fired" from "CAN bus
   failure" without manual log correlation
4. Every trial should still include a deliberate E-stop test before picking begins (add
   to pre-trial checklist)

### 6.7 Fix monitoring gaps

**Priority: MEDIUM**

- Fix network_monitor on arm_2 (0 data rows)
- Fix detection log severity (ERROR → INFO for detection_summary)
- Fix model path warning (log correct model name, not fallback path)

### 6.8 Profile and fix memory leak

**Priority: HIGH**

Primary leaker identified: `dashboard_server` (uvicorn) at ~22 MB/hr on arm_2. Secondary
contributor: `rpi_agent` with a +61.6 MB initialization spike then ~1.9 MB/hr steady-state
growth. arm_1 is also affected (13 MB → 174 MB), confirming this is systemic, not
arm_2-specific. Vehicle's `vehicle_control_node` also grew 20% (136 MB → 163 MB) over 2 hours.

Recommended actions:
- Run `tracemalloc` on `dashboard_server` to identify the leaking allocation site
- Check for unclosed WebSocket connections or HTTP response objects in uvicorn
- Check for growing caches (detection history, session state) that are never pruned
- Investigate `rpi_agent` initialization spike — large data structures loaded once and
  never released
- Consider adding periodic process restart between ROS2 sessions (neither process currently
  restarts between sessions)

### 6.9 Add ODrive temperature monitoring

**Priority: MEDIUM**

Drive motors have no temperature data in logs. Cannot detect thermal issues before failure.
ODrive firmware supports temperature readout — add it to the CAN polling loop and log it
alongside motor position and velocity.

### 6.10 Validate L3 offset and L5 depth

**Priority: HIGH**

Two March plan items that never got done. Camera-workspace alignment is directly related
to the #1 bottleneck (workspace reachability at 46.2%). Measuring and correcting the L3
camera pitch offset could shift detections toward the reachable workspace, reducing
COLLISION_BLOCKED rejections.

---

## 7. Key Decisions for April

| # | Decision | Options | Data Point | Recommendation |
|---|----------|---------|------------|----------------|
| 1 | Detection model | A. Retrain v11 with Mar data / B. Retrain v5 2-class / C. Evaluate YOLOX / D. Confidence gating | v11 misses cotton in field lighting; v5 detects shells | A or B — retrain with 3,266 new field images |
| 2 | YOLOX migration | A. Start now / B. Defer to May | Deferred twice (from Jan, then Mar). Licensing risk remains with YOLO. | B — defer again; retrain existing model with new data first |
| 3 | Collision margin tuning | A. Conservative (current) / B. Reduce by 5 cm / C. Reduce by 10 cm | 73.1% of failures are COLLISION_BLOCKED at x > 0.49 m | B — reduce by 5 cm with data validation |
| 4 | Hardware E-stop | A. Software-only / B. Add GPIO button / C. Add commercial E-stop | No hardware E-stop on arms. Safety concern for multi-arm operation. | B — GPIO button is fast to implement |
| 5 | Border filter margin | A. Keep 5% / B. Reduce to 3% / C. Adaptive per-detection | 5.3% to 12–52% escalation between trials | C — adaptive is best, B as quick fix |
| 6 | J4 scan configuration | A. Keep 7-position / B. Remove +150 mm / C. Adaptive based on yield | +150 mm = 7–11% yield vs. 55%+ for other positions | B — remove +150 mm, add finer steps in effective range |
| 7 | Vehicle CAN upgrade | A. Keep MCP2515 / B. Upgrade to MCP2518FD / C. SPI tuning | 1.59M RX errors from MCP2515 SPI limitation | B — MCP2518FD supports higher throughput and FD frames |
| 8 | Collision interlock | A. Re-enable J3-J4 interlock / B. Formally document risk acceptance | Interlock disabled on both arms for entire trial without review | A — re-enable for two-arm operation safety |
| 9 | Boot reliability | A. Stagger node startup / B. Move to performance CPU governor / C. Both | RCU stalls, journal corruption, 80s+ boot on arm_2 | C — stagger startup AND performance governor on RPi 4B |
| 10 | E-stop instrumentation | A. Add structured logging only / B. Add logging + vbus monitoring / C. Full CAN failure detection | E-stop used but invisible to software; CAN timeouts silently swallowed | B — structured logging + vbus monitoring as minimum |

---

## 8. Scorecard: Development Cycle Effectiveness

### 8.1 Component Grades

| Dimension | Grade | Rationale |
|-----------|-------|-----------|
| Pick success rate | A | 26.7% to 52.9% (+26.2 pp). Target was >60% — missed by 7.1 pp but trajectory is strong. |
| Vehicle stability | A | 9 crashes to 0 unplanned crashes. E-stop event between S3/S4 caused 30 min CAN-dead downtime but was operator-initiated, not a software failure. |
| Two-arm operation | A | First dual-arm field trial. Both arms productive. Zero inter-arm conflicts. |
| Zero-coord fix | A+ | 237 leaked to 0 leaked. 100% filtering. Fix is bulletproof. |
| Provisioning | A+ | 8–11 failures to 0 failures. Completely fixed. |
| Detection model | C | Unresolved trade-off. Mid-trial model switch. No clear path forward. |
| Workspace reachability | B- | 73% to 46.2% (-27 pp) but missed <30% target by 16 pp. Still #1 issue. |
| Border filter | D | 5.3% to 12–52%. Significant regression. Rejecting valid detections. |
| Hardware validation | F | No startup checks exist. Encoder shift ran undetected for 4 hours. |
| Monitoring and tooling | B+ | 5 new tools, all useful. 1 still broken. process_memory caught leak. |
| Documentation | A | Comprehensive reports, RCAs, plans. Every decision is data-backed. |
| Dev velocity | A+ | 112 OpenSpec changes in 28 days (4.0/day). 13+ packages modified. |
| **Overall** | **B+** | **Major improvements in core metrics. New issues discovered. Old issues partially addressed. System is transitioning from "can it work?" to "can it work reliably?"** |

### 8.2 Velocity Metrics

| Metric | Value |
|--------|-------|
| OpenSpec changes shipped | 112 |
| Changes per day | 4.0 |
| Plans written | 5 |
| RCA documents | 3 |
| Lines of analysis docs | ~5,000+ |
| Packages modified | 13+ |
| Critical safety fixes | 9 (all completed) |
| Days in cycle | 28 |
| Field trials conducted | 2 (1 pre-field + 1 full) |

### 8.3 Target Achievement

| Target | Goal | Actual | Met? | Gap |
|--------|------|--------|------|-----|
| Pick success rate | >60% | 52.9% | CLOSE | -7.1 pp |
| Workspace violations | <30% | 46.2% | NO | +16 pp |
| Detection accuracy | 90–95% | Not measured cleanly | UNCLEAR | No clean metric |
| Zero spatial coords | <5% | ~17% | NO | +12 pp (hardware limit) |
| Wasted detection rate | <40% | 48.9–57.3% | NO | +9–17 pp |
| Arms operational | 2 | 2 | YES | -- |
| Vehicle crashes | 0 | 0 | YES | -- |
| Provisioning pass rate | 100% | 100% | YES | -- |

### 8.4 Honest Assessment

The development cycle was highly productive by any measure: 112 changes, 26.2 pp pick rate
improvement, vehicle stability transformation, and dual-arm validation. These are real,
measurable improvements backed by field data.

However, three of six quantitative targets were missed (workspace violations, zero spatial
coords, wasted detection rate), one was close (pick success rate), and one was unmeasurable
(detection accuracy). The targets that were met (arms operational, vehicle crashes,
provisioning) were binary pass/fail goals, not continuous improvement targets.

The most concerning pattern is that **workspace reachability has been the #1 issue for two
consecutive trials** and the improvement, while meaningful (73% to 46.2%), is insufficient.
Without a step-change in how the system handles the camera-workspace geometry mismatch,
pick success rate will plateau in the 50–60% range regardless of other improvements.

The border filter regression (D grade) is a self-inflicted wound — a conservative safety
parameter that was not validated against field data before deployment. This is fixable
within a day.

The hardware validation gap (F grade) is the most serious systemic issue. The system has
no concept of "is the hardware working correctly before I start?" This must be addressed
before scaling to more arms or longer autonomous runs.

---

## Appendix: Change References

Key OpenSpec changes referenced in this document:

- `2026-02-16-odrive-vehicle-drive-integration` — ODrive PID tuning and error recovery
- `2026-02-17-fix-zero-coordinate-detections` — Zero-coordinate filtering
- `2026-02-18-sync-provision-flag` — Provisioning offline capability
- `2026-02-19-field-ops-deployment-hardening` — Deployment hardening
- `2026-03-02-field-trial-readiness-fixes` — Launch and configuration hardening
- `2026-03-06-motor-control-safety` — Safety limits and watchdogs

Related analysis documents:

- `docs/project-notes/FIELD_TRIAL_REPORT_MAR25_2026.md` — Full March trial report
- `docs/project-notes/FIELD_VISIT_REPORT_FEB_2026.md` — Full February trial report
- `docs/project-notes/ENCODER_ZERO_SHIFT_ANALYSIS_2026-03.md` — Encoder failure RCA
- `docs/project-notes/STEERING_THERMAL_CASCADE_ANALYSIS_2026-03.md` — Thermal cascade RCA
- `docs/project-notes/BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md` — Border filter analysis
- `docs/project-notes/PICK_REJECTION_BOTTLENECK_ANALYSIS_2026-03.md` — Workspace bottleneck analysis
- `docs/project-notes/DETECTION_MODEL_TRADEOFF_ANALYSIS_2026-03.md` — Model comparison
- `docs/project-notes/ZERO_SPATIAL_COORDINATE_ANALYSIS_2026-03.md` — Zero-coord deep dive
- `docs/project-notes/APRIL_FIELD_TRIAL_PLAN_2026.md` — Next trial plan
