# Encoder Zero Shift — Root Cause Analysis (March 25, 2026 Field Trial)

**Date:** March 2026
**Incident:** Mar 25, 2026 field trial — front wheel MG6010 absolute encoder latched ~90 degrees offset
**Log source:** `collected_logs/2026-03-25/machine-1/vehicle/` (vehicle RPi pragati11)
**Related:** [Steering Thermal Cascade Analysis](STEERING_THERMAL_CASCADE_ANALYSIS_2026-03.md) (different root cause, same thermal symptom)

---

## 1. Executive Summary

During the March 25 field trial, the front wheel steering motor (steering_front, MG6010)
operated for approximately 4 hours with its absolute encoder latched roughly 90 degrees
from the true mechanical zero. The motor drew 1.84-1.92A at idle (normal: 0.05-0.15A),
fighting the mechanical misalignment continuously. This produced 42 stall events and a
thermal cascade to 80 degrees C across Sessions 1-2 (10:44-14:54).

Between Sessions 2 and 3, operators power-cycled the vehicle and manually repositioned
the front wheel. On power-up, the encoder re-latched at the correct zero. Session 3
(15:24-18:11) operated normally with zero stalls and nominal idle current.

**This is a distinct failure mode from the February thermal cascade** analyzed in
STEERING_THERMAL_CASCADE_ANALYSIS_2026-03.md. That analysis covers software bugs (init
sequence, no motor_stop on timeout) causing thermal runaway even with a correctly-zeroed
encoder. This document covers a hardware/firmware condition — encoder zero reference loss
— that causes thermal runaway regardless of software correctness. Both failure modes
produce the same downstream symptom (sustained high current leading to thermal cascade)
but require different mitigations.

---

## 2. Timeline

### Session 1 (10:44 - 12:42, ~2 hours)

| Metric | Value | Normal Reference |
|--------|-------|------------------|
| steering_front idle current | 1.84-1.92A | 0.05-0.15A |
| Current multiplier vs normal | 12-38x | 1x |
| steering_front stall events | 29 | 0 |
| steering_front peak temp | 80 degrees C | 35-45 degrees C |
| Other steering motors | Normal current, no stalls | -- |
| Battery voltage | 52.5-52.8V | Normal |

The vehicle started normally. The operator likely did not immediately notice the front
wheel misalignment because the steering mechanism has limited visual feedback from the
driver's seat. The system accepted commands and appeared responsive — the motor was
actively trying to steer — but every position command was offset by approximately 90
degrees from the intended target.

The motor repeatedly hit mechanical limits (steering linkage end-stops) or torque limits
as it attempted to reach positions that were physically unreachable given the offset.
Each stall event produced a burst of high current, and the sustained idle current of
1.84-1.92A added continuous baseline heat between stalls.

### Session 2 (12:43 - 14:54, ~2 hours 11 minutes)

| Metric | Value |
|--------|-------|
| steering_front stall events | 13 (cumulative: 42) |
| steering_front thermal events | 4 (all 3 motors affected) |
| Thermal cascade | Front motor heat conducted to chassis, affecting left/right motors |
| ODrive drive motors | 29,950 WARN/ERROR lines (CAN-related, separate issue) |

Session 2 inherited the offset state. The motor continued operating with the shifted
encoder reference. By this point, the front motor had been running at 12-38x normal
idle current for over 2 hours, and the thermal cascade had spread to affect all three
steering motors through chassis heat conduction.

### Operator Intervention (between Session 2 and Session 3)

Operators identified the front wheel misalignment through visual inspection. The
correction procedure was:

1. Power off the vehicle completely (kill switch)
2. Manually rotate the front wheel to its expected center position
3. Power the vehicle back on

On power-up, the MG6010 absolute encoder re-established its magnetic zero reference
from the current rotor position. With the wheel manually placed near true center, the
encoder latched at (or very near) the correct zero.

### Session 3 (15:24 - 18:11, ~2 hours 47 minutes)

| Metric | Value | Comparison to Sessions 1-2 |
|--------|-------|---------------------------|
| steering_front idle current | 0.05-0.15A (normal) | Down from 1.84-1.92A |
| steering_front stall events | 0 | Down from 42 |
| steering_front peak temp | Normal range | Down from 80 degrees C |
| Vehicle driveability | Normal — steering responsive, accurate | Previously fighting offset |
| Pick operations | Both arms operational, 55.4% success rate | Arms were unaffected throughout |

Session 3 confirmed the diagnosis. With the encoder correctly zeroed, all steering
parameters returned to baseline. The vehicle operated for nearly 3 hours with zero
steering anomalies.

---

## 3. Evidence Chain

The diagnosis rests on five mutually reinforcing pieces of evidence:

### 3.1 Idle Current Anomaly (Primary Evidence)

The idle current of 1.84-1.92A at the encoder's reported "zero position" is the
definitive indicator. When a motor is correctly zeroed and commanded to hold center,
it draws minimal current (0.05-0.15A) because the mechanical position matches the
commanded position — the PID error signal is near zero. A 12-38x increase in holding
current means the PID is fighting a large position error, which is exactly what a 90
degree encoder offset would produce: the motor "thinks" it is at center but is
physically 90 degrees away, and the PID continuously outputs high current trying to
close the gap.

This is not consistent with other failure modes:
- **Mechanical binding** would show variable current depending on position, not a
  constant high baseline at "zero."
- **PID tuning issues** would show oscillation, not sustained DC current.
- **Motor winding damage** would show current anomalies regardless of position and
  would not resolve on power cycle.
- **CAN communication errors** would show command drops or garbled positions, not a
  clean constant offset.

### 3.2 Stall Event Pattern (Corroborating Evidence)

All 42 stall events occurred exclusively on steering_front. The other two steering
motors (steering_left, steering_right) operated normally throughout Sessions 1-2. If
the failure were systemic (software bug, power issue, CAN bus), all three motors would
be affected. An isolated single-motor failure points to a motor-specific condition,
consistent with encoder zero shift on that specific motor.

The stall events were the motor hitting torque limits or physical end-stops as it
attempted to reach positions that the 90 degree offset made unreachable. For example,
if the encoder shifted such that true mechanical 0 degrees reads as 90 degrees, a
command to steer 45 degrees right would target true mechanical 135 degrees — likely
beyond the steering linkage's range of motion.

### 3.3 Thermal Profile (Consequential Evidence)

The thermal cascade from ambient to 80 degrees C is the direct thermodynamic
consequence of sustained 1.84-1.92A draw. Using the MG6010 winding resistance
(approximately 0.5 ohms per phase), the continuous power dissipation was roughly
1.7-1.85W — enough to raise motor temperature from 40 degrees C to 80 degrees C
over a 2-hour period given the motor's thermal mass and limited convective cooling in
a field enclosure.

This thermal profile matches the February incident in magnitude but differs in pattern.
The February cascade affected all three steering motors from software bugs (init
sequence, no motor_stop on timeout). The March cascade started with one motor and
spread through chassis conduction, consistent with a single-motor hardware fault.

### 3.4 Power Cycle Resolution (Confirmatory Evidence)

The fact that a power cycle plus manual wheel repositioning fully resolved the issue
is the strongest evidence for transient encoder state loss. If the cause were:

- **Permanent encoder damage:** Would not resolve on power cycle.
- **Magnetic ring mechanical slip:** Would recur on next power cycle (or shift to a
  different offset). A single successful re-latch does not rule this out entirely,
  but the clean 3-hour Session 3 suggests the encoder hardware is functional.
- **Motor winding fault:** Would not resolve on power cycle.
- **Software bug:** Would reproduce with the same code (same build ran Session 3
  without issue).

### 3.5 Cross-Session Behavioral Contrast

The before/after comparison across sessions is unambiguous:

| Parameter | Sessions 1-2 (shifted) | Session 3 (corrected) |
|-----------|----------------------|----------------------|
| Idle current | 1.84-1.92A | 0.05-0.15A |
| Stall events | 42 | 0 |
| Peak temperature | 80 degrees C | Normal |
| Steering accuracy | Offset ~90 degrees | Correct |
| Code version | Identical | Identical |
| Hardware | Identical (same motor, same encoder) | Identical |

The only variable that changed between Sessions 1-2 and Session 3 was the encoder's
zero reference, established during the power cycle.

### Session 4 (Post E-Stop — CAN Bus Dead)

Between Sessions 3 and 4, the hardware E-stop was activated. Session 4 showed the CAN
bus completely dead, with all motors reporting UNAVAILABLE. No steering or drive
operation was possible.

**Relevance to encoder zero shift:** The E-stop cuts motor power while the vehicle
remains physically accessible. If the front wheel was manually moved while motor power
was cut (E-stop engaged), the encoder would latch the wrong zero on power restore —
the same failure mode observed in Sessions 1-2. This is a plausible re-trigger
mechanism for encoder zero shift: any E-stop event followed by physical wheel
disturbance (e.g., pushing the vehicle, terrain settling, manual repositioning) creates
the conditions for Mechanism A (power-up during/after motion). The startup zero-position
verification (R1) would catch this on the next power cycle, but operators should be
aware that E-stop recovery requires the same wheel-centering procedure used between
Sessions 2 and 3.

---

## 4. Root Cause Analysis

### 4.1 How MG6010 Absolute Encoders Establish Zero

The MG6010 motor uses a magnetic absolute encoder consisting of a diametrically
magnetized ring attached to the rotor and a hall-effect sensor array on the stator.
On power-up, the sensor array reads the magnetic field orientation and computes the
rotor's absolute angular position. This position becomes the reference for all
subsequent motion commands.

The "absolute" designation means the encoder can determine position without a homing
sequence — unlike incremental encoders that require rotation to an index pulse. However,
"absolute" does not mean "infallible." The position reading depends on:

1. The magnetic ring being rigidly fixed to the rotor
2. The hall sensor array being rigidly fixed to the stator
3. Clean power-up with stable supply voltage
4. No strong external magnetic fields interfering with the reading

### 4.2 Failure Mode: Zero Reference Shift

The encoder's reported zero can diverge from mechanical zero through several mechanisms:

**Mechanism A: Power-up during vibration or motion.**
If the motor is powered on while the vehicle is in transport, on rough terrain, or with
the engine running, mechanical vibration can cause the rotor to oscillate during the
sensor's initialization window. The sensor may latch a position reading that is offset
from the rotor's resting position by the amplitude of the vibration. For the MG6010
gearbox with a 1:300 ratio, even a small rotor oscillation maps to a measurable output
shaft offset.

**Mechanism B: Brown-out or voltage sag during initialization.**
If the power supply voltage dips during the encoder's initialization sequence (e.g., from
inrush current of other motors starting simultaneously), the sensor's ADC may produce an
incorrect reading. The MG6010 firmware does not appear to verify the zero reading against
any external reference before accepting it.

**Mechanism C: Magnetic ring slip.**
Over time, the adhesive or press fit securing the magnetic ring to the rotor shaft can
loosen due to thermal cycling, vibration, or mechanical shock. If the ring rotates
relative to the rotor, the encoder's absolute reference shifts permanently (until the
ring is re-secured). This mechanism would produce a consistent offset across power
cycles — the March 25 incident resolved on power cycle, so this is less likely but
cannot be ruled out from a single data point.

**Mechanism D: External magnetic interference.**
Strong external magnetic fields (from DC motors, solenoids, or magnetized tools near
the motor) can influence the hall sensor reading during initialization. This is unlikely
in the Pragati field environment but worth noting for completeness.

**Assessment for March 25:** Mechanisms A and B are the most probable causes. The
vehicle was transported to the field site before Session 1, and the power-up likely
occurred with other systems also initializing (ODrive motors, RPis, CAN transceivers).
The fact that a clean power cycle resolved the issue suggests a transient initialization
error rather than permanent mechanical slip.

### 4.3 Software Gap: No Encoder Verification

The current software stack has zero defenses against encoder zero shift. This is the
core finding of this analysis. Specifically:

**No idle current check after power-up.** After the motor initializes and reports its
position, the software does not verify that the motor can actually hold that position
with nominal current. A simple 2-second current reading after initialization would
have caught the 1.84A anomaly immediately.

**No movement verification.** The software does not perform a small test movement
(e.g., command +5 degrees, verify position delta is approximately 5 degrees) to
confirm that the encoder's reported position corresponds to physical reality.

**No stall escalation limit.** The system permitted 42 consecutive stalls on the same
motor without taking corrective action. There is no policy that says "after N stalls
in M minutes, disable this motor and alert the operator."

**No idle current health monitoring.** During operation, idle current is not compared
against a baseline. Even if the startup check were missed, continuous monitoring would
detect the anomaly within seconds of the motor settling at any position.

**Trust model is implicit.** The software treats the encoder's reported position as
ground truth. There is no concept of "encoder health" or "position confidence." For a
lab robot, this is acceptable. For a field robot experiencing vibration, transport,
power cycles, dust, and temperature extremes, it is a significant reliability gap.

### 4.4 Root Cause Tree

```
SYMPTOM: 42 stalls, 80 degrees C thermal, 4 hours lost operation
|
+-- PROXIMATE CAUSE: Motor fighting ~90 degree encoder offset continuously
|   |
|   +-- HARDWARE CAUSE: Encoder zero reference shifted on power-up
|   |   |
|   |   +-- Probable: Power-up during vibration (transport/engine)
|   |   +-- Probable: Voltage sag during initialization (inrush)
|   |   +-- Possible: Magnetic ring mechanical slip (less likely given power-cycle fix)
|   |
|   +-- SOFTWARE CAUSE: No detection or mitigation of encoder offset
|       |
|       +-- No idle current threshold check after homing
|       +-- No movement verification after initialization
|       +-- No stall count escalation limit (allowed 42 without disable)
|       +-- No continuous idle current health monitoring
|
+-- AGGRAVATING FACTOR: Software bugs from February analysis still present
    |
    +-- No motor_stop on position timeout (RC-2 from thermal cascade analysis)
    +-- Init sequence sends motor_on before clear_errors (RC-3)
    +-- No command deduplication (RC-5)
```

---

## 5. Relationship to February Thermal Cascade

The February and March incidents share the same downstream symptom — steering motor
thermal cascade — but have fundamentally different root causes. Understanding the
distinction is important for prioritizing fixes.

| Dimension | Feb 26 (Thermal Cascade) | Mar 25 (Encoder Shift) |
|-----------|-------------------------|----------------------|
| Root cause | Software bugs in init/timeout/dedup | Encoder zero reference shift |
| Trigger | Any motor command under normal operation | Power-up conditions (vibration, voltage) |
| Motors affected | All 3 steering (software is shared) | Front only (hardware-specific) |
| Reproducibility | Deterministic (same bugs, same result) | Probabilistic (depends on power-up conditions) |
| Fix category | Software-only | Software detection + optional hardware reference |
| Interaction | Feb bugs make the situation WORSE but are not the cause | Encoder shift triggers thermal cascade even without Feb bugs |

**The fixes are complementary, not redundant.** Fixing the February software bugs
(init sequence, motor_stop on timeout) reduces thermal damage from any stall scenario.
Fixing the encoder zero shift detection prevents the stall scenario from occurring in
the first place. Both are needed for robust field operation.

If the February software fixes had been deployed on March 25:
- The stall escalation would still have occurred (encoder offset causes stalls regardless)
- The thermal cascade would have been somewhat mitigated (motor_stop on timeout prevents
  indefinite current draw after each stall)
- The 4 hours of lost operation would NOT have been prevented (motor would still be
  steering 90 degrees off, just with slightly less thermal damage)

Only the encoder verification check (Recommendation 1 below) would have caught the
problem at startup and prevented the entire incident.

---

## 6. Impact Assessment

### Operational Impact
- Lost approximately 4 hours of productive vehicle operation (Sessions 1-2)
- Operator time spent diagnosing and correcting the issue
- Reduced data collection opportunity for the field trial
- Vehicle steering was non-functional for pick operations during Sessions 1-2

### Hardware Risk
- Motor operated at 80 degrees C for extended periods (rated thermal limit is 85 degrees C
  for the MG6010 housing)
- Repeated thermal cycling accelerates bearing wear, winding insulation degradation, and
  magnetic ring adhesive weakening — potentially increasing future encoder shift probability
- No permanent damage was confirmed from this single incident, but cumulative thermal
  stress is a concern for motor longevity

### Safety Considerations
- In the current stop-and-pick operating mode, a steering offset is a functional issue,
  not a safety issue (vehicle speed is low, operator is present)
- In future autonomous modes, a 90 degree steering offset at speed would be a serious
  safety risk — the vehicle would veer perpendicular to the intended path
- Stall escalation limits are a safety-relevant mitigation regardless of operating mode

### Blast Radius
- Arms were completely unaffected (separate RPis, separate CAN buses, no shared state)
- Drive motors (ODrive) were unaffected by the encoder issue (Session 2 ODrive errors
  were a separate CAN-related issue)
- Vehicle MQTT bridge operated normally throughout
- No data loss or corruption occurred

---

## 7. Recommendations

### R1: Startup Zero-Position Verification (CRITICAL, ~1-2 days)

**What:** After motor initialization and homing, perform a two-stage verification:

1. **Idle current check:** Command the motor to its reported zero position and
   measure average current over 2 seconds. If average exceeds 0.5A, flag the motor
   as `ZERO_POSITION_SUSPECT`.
2. **Movement verification:** Command a small test movement (e.g., +5 degrees from
   current position). After the move completes, read the position delta. If the
   actual delta deviates from the commanded delta by more than 2 degrees, or if
   the move stalls, flag the motor as `ZERO_POSITION_FAILED`.

**On failure:** Disable the motor (motor_off), log a CRITICAL alert with motor ID,
measured current, expected vs actual position delta, and temperature. Require manual
re-enable after physical inspection.

**Where:** `mg6010_controller_node.cpp` initialization sequence, after the existing
init commands complete. This is shared code — both arm and vehicle motors benefit.

**Risk:** LOW. The verification adds 3-5 seconds to startup per motor. The 0.5A
threshold provides generous margin above the normal 0.05-0.15A range while catching
any significant offset. The +5 degree test movement is within the normal range of
motion for all joints.

**Impact on March 25:** Would have caught the front wheel encoder shift within the
first 5 seconds of Session 1. The motor would have been disabled immediately,
alerting the operator before any thermal damage or lost operational time.

### R2: Stall Escalation Limit (CRITICAL, ~1 day)

**What:** Track consecutive stall events per motor. If a motor accumulates more
than 3 stalls within a 5-minute window, auto-disable it.

**Implementation:**
- Add a per-motor stall counter and timestamp ring buffer (last 5 stall times)
- On each stall event, check if 3+ stalls occurred in the last 5 minutes
- If threshold exceeded: send motor_stop then motor_off, log CRITICAL alert with
  motor ID, stall count, temperature, last commanded positions
- Require explicit manual re-enable (ROS2 service call or parameter set)

**Where:** `mg6010_controller_node.cpp` stall detection logic.

**Risk:** LOW. The 3-stalls-in-5-minutes threshold is conservative — normal operation
should produce zero stalls. The auto-disable prevents unattended thermal runaway.
Manual re-enable ensures an operator confirms the motor is safe before resuming.

**Impact on March 25:** Would have disabled the front motor after the 3rd stall
(approximately 15 minutes into Session 1), preventing the remaining 39 stalls and
the thermal cascade to 80 degrees C.

### R3: Continuous Idle Current Monitoring (MEDIUM, ~1 day)

**What:** Continuously compare each motor's current draw against a per-motor
baseline when the motor is in idle (holding position, no active command). If idle
current exceeds 2x the established baseline for more than 30 seconds, log a WARNING
alert.

**Implementation:**
- Establish baseline idle current per motor during the first 10 seconds after
  initialization (assuming R1 verification passes)
- During operation, when the motor is not actively being commanded, compare
  instantaneous current against baseline
- Use a 30-second sliding window average to avoid false positives from transient
  loads (e.g., road bumps applying force to steering)
- Alert threshold: 2x baseline for 30 seconds

**Where:** `mg6010_controller_node.cpp` health monitoring loop.

**Risk:** LOW. Read-only monitoring with no automatic corrective action (alert only).
The 2x threshold with 30-second averaging provides significant noise margin.

**Value:** Catches encoder drift that develops during operation (not just on startup).
Also catches other anomalies like mechanical binding, gear wear, or linkage
obstruction that gradually increase holding current.

### R4: Physical Homing Reference (LOW priority, hardware modification)

**What:** Add a physical limit switch or index pulse to the front wheel steering
mechanism. On startup, drive the wheel to the limit switch, then set zero from the
known physical reference. This eliminates dependency on the encoder's magnetic
absolute position entirely.

**Why LOW priority:** The software mitigations (R1, R2, R3) provide adequate
protection for near-term field trials. A physical homing reference is the robust
long-term solution but requires mechanical design, fabrication, and installation.

**Considerations:**
- Limit switch placement must not interfere with steering range of motion
- Homing sequence adds startup time (wheel must physically traverse to the switch)
- Must handle the case where the wheel is already at or past the limit switch on
  power-up
- Could be implemented with a simple microswitch and one GPIO input on the RPi

### R5: Encoder Health Tracking (LOW priority, ~0.5 day)

**What:** Log the raw encoder zero reference value on each power-up. Over time,
track whether the zero reference drifts between sessions.

**Value:** If the zero reference shifts gradually across power cycles, it indicates
mechanical wear (magnetic ring loosening, bearing play). This enables predictive
maintenance — replacing the motor before a field failure rather than after.

**Implementation:** Log the encoder's absolute position reading at initialization
(before any movement) with a session-unique tag. A simple post-hoc analysis script
can compare these values across field trial sessions.

---

## 8. Implementation Priority

The recommendations are ordered by impact-to-effort ratio for the next field trial:

| Priority | Recommendation | Effort | Prevents |
|----------|---------------|--------|----------|
| 1 | R1: Startup verification | 1-2 days | Entire incident (detects at boot) |
| 2 | R2: Stall escalation limit | 1 day | Thermal cascade (limits damage) |
| 3 | R3: Idle current monitoring | 1 day | Mid-operation encoder drift |
| 4 | R5: Encoder health tracking | 0.5 day | Future failures (predictive) |
| 5 | R4: Physical homing reference | 2-3 days + hardware | Encoder dependency entirely |

R1 and R2 should be implemented before the next field trial. Together they provide
defense in depth: R1 catches the problem at startup, R2 limits damage if R1 somehow
misses it or if the encoder shifts during operation.

---

## 9. Verification Criteria

To confirm the mitigations are working correctly in future trials:

### For R1 (Startup Verification)
- **Pass case:** Motor initializes, idle current measured below 0.5A, test movement
  delta within 2 degrees of commanded — motor proceeds to normal operation.
- **Fail case (test in lab):** Manually offset the wheel by 30+ degrees before power-on.
  System should detect anomalous idle current, fail the movement test, disable the
  motor, and log CRITICAL alert within 10 seconds of boot.

### For R2 (Stall Escalation)
- **Pass case:** Normal operation produces zero stalls. Counter stays at zero.
- **Fail case (test in lab):** Mechanically block the steering linkage. Command
  repeated steering movements. After 3 stalls within 5 minutes, motor should
  auto-disable with CRITICAL log.

### For R3 (Idle Current Monitoring)
- **Pass case:** Idle current remains within 2x baseline throughout operation.
- **Alert case:** Gradually increasing idle current (e.g., from friction buildup)
  should trigger WARNING after 30 seconds above threshold.

---

## 10. Open Questions

1. **What was the exact power-up sequence on March 25?** Was the vehicle engine
   running when the RPi powered on? Were multiple motors initializing simultaneously?
   Understanding the exact conditions helps narrow down Mechanism A vs B.

2. **Has this encoder shift been observed on other MG6010 motors in the fleet?** If
   it is specific to the front wheel motor, the physical mounting or wiring may have
   a localized issue. If it has occurred (or will occur) on other motors, the
   software mitigations become even more urgent.

3. **What is the MG6010 encoder's initialization timing?** The firmware documentation
   should specify how long after power-up the encoder reading is latched and whether
   there is a "ready" signal. This informs whether a delayed initialization (wait for
   power supply to stabilize) could reduce the probability of Mechanism B.

4. **Is the 1:300 gear ratio self-locking?** (Also raised in the thermal cascade
   analysis.) This affects whether motor_off is safe after a failed verification
   (R1). If the gear is not self-locking, the wheel could swing freely after disable,
   which may be acceptable for a stopped vehicle but needs consideration.

---

## 11. Log Sources

| Source | Path |
|--------|------|
| Vehicle RPi logs | `collected_logs/2026-03-25/machine-1/vehicle/` |
| Provision log | `collected_logs/2026-03-25/machine-1/vehicle/provision_logs/provision_20260325_104310.log` |
| Log analysis output | Generated by `scripts/log_analyzer.py --field-summary --verbose` |
| Field trial report | [FIELD_TRIAL_REPORT_MAR25_2026.md](FIELD_TRIAL_REPORT_MAR25_2026.md) Section 1.3-1.5 |

---

## 12. Related Documents

- [Steering Thermal Cascade Analysis](STEERING_THERMAL_CASCADE_ANALYSIS_2026-03.md) — software-caused thermal cascade from Feb 26 data. Different root cause (init sequence bugs, no motor_stop on timeout), same thermal symptom.
- [Field Trial Report Mar 25](FIELD_TRIAL_REPORT_MAR25_2026.md) — full trial report; Section 1.4 covers this encoder issue in the vehicle analysis context.
- [Motor Control Comprehensive Analysis](MOTOR_CONTROL_COMPREHENSIVE_ANALYSIS_2025-11-28.md) — MG6010 motor firmware behavior reference.
- [Thermal Failure Analysis and Remediation Plan](THERMAL_FAILURE_ANALYSIS_AND_REMEDIATION_PLAN.md) — prior thermal analysis and remediation strategies.
- [Vehicle Motor Alternatives and Protection](VEHICLE_MOTOR_ALTERNATIVES_AND_PROTECTION.md) — motor protection strategies and motor replacement considerations.
