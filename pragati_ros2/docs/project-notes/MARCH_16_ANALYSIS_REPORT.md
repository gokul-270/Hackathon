# March 16, 2026 — Field Trial Analysis Report

| Field       | Value                                                      |
|-------------|------------------------------------------------------------|
| Date        | March 16, 2026                                             |
| Author      | Pragati Engineering Team                                   |
| Trial Type  | Hardware bring-up / 3-RPi integration test                 |
| Location    | Field site                                                 |
| RPis Active | arm_1, arm_2, vehicle                                      |
| Baseline    | February 26, 2026 field trial                              |
| Purpose     | Validate 108 OpenSpec software changes deployed Feb 26–Mar 15 |

---

## 1. Executive Summary

March 16 was a **3-RPi integration test** (arm_1, arm_2, vehicle), not a picking trial.
The session achieved **0 picks** — entirely blocked by CAN bus hardware failures on all
three RPis. The team spent approximately **5.5 hours across 28 restart sessions** debugging
hardware connectivity issues before concluding that the problems were not software-related.

Between February 26 and March 15, the team shipped **108 OpenSpec software changes**
addressing every critical issue from the February field trial. None of these fixes could
be field-validated on March 16 because the system never progressed past CAN initialization.

The primary takeaway: software readiness is high, hardware readiness is unknown, and the
absence of a pre-flight hardware validation script cost the team an entire field day.

---

## 2. March 16 Root Cause Analysis

Three independent CAN bus failures prevented any motor operation:

### Vehicle RPi — No CAN HAT Configured

The MCP2515 CAN HAT was either not physically connected or its device tree overlay was
not configured. `dmesg` showed no CAN controller initialization at all. Both
`vehicle_control_node` and `mg6010_controller_node` crash-looped repeatedly attempting
to open `can0`, which did not exist as a network interface.

### Arm_1 RPi — CAN Interface Up, Zero Traffic

The MCP2515 driver loaded successfully and the `can0` interface came up at the kernel
level. However, packet counters showed **0 RX packets and 0 TX success**. This indicates
a physical-layer problem: disconnected wiring, motor power supply not on, or missing CAN
bus termination resistors. Software detected a timeout on every motor command sent.

### Arm_2 RPi — Double Hardware Failure

Same as vehicle (no CAN HAT at kernel level) **plus** the OAK-D Lite camera was not
detected (USB enumeration failure). With neither CAN nor camera functional, arm_2
generated **846 cascading service failure events** as nodes repeatedly attempted to
start without any connected hardware.

---

## 3. February 26 Baseline Metrics

Reference values from the last trial where the system was operational:

| Metric                     | Feb 26 Value                  |
|----------------------------|-------------------------------|
| Pick attempts              | 1,181                         |
| Pick success rate          | 26.7% (315 / 1,181)          |
| Workspace violations       | 73% of attempts               |
| ODrive crashes             | 9 sessions                    |
| Steering error code 8      | All 3 motors affected         |
| Steering thermal peaks     | 73–80 C                       |
| Zero spatial detections    | 17% (503 events)              |
| Wasted detection rate      | 79.6%                         |
| Stale pick rate            | 19.6%                         |
| Communication timeouts     | 327                           |
| MQTT uptime                | 97.7% (vehicle)               |
| Detection latency          | 34–93 ms average              |
| Service discovery timeouts | 126                           |
| Pick cycle degradation     | 21.8% / hour                  |

---

## 4. Issues Fixed by Software Changes

20 February issues addressed by the 108 OpenSpec changes shipped between Feb 26 and Mar 15.

### Confirmed Fixed (15)

1. **Steering error code 8** — Init sequence rewritten: motor_stop, clear_errors,
   verify_clean, motor_on, verify_active. Eliminates the stuck-error-code loop that
   affected all 3 steering motors. *(motor-control-hardening, Mar 15)*

2. **ODrive stall-recovery-restall loop** — 1,183 errors in Feb eliminated by async
   recovery with exponential backoff replacing the synchronous recover-then-immediately-
   restall pattern. *(field-trial-readiness-fixes, Mar 02)*

3. **ODrive idle timeout** — Motors failing after idle periods now kept alive with
   periodic keepalive commands. *(field-trial-readiness-fixes, Mar 02)*

4. **Drive stop service timeouts** — 29 timeouts in Feb fixed by non-blocking service
   implementation. *(field-trial-readiness-fixes, Mar 02)*

5. **End-effector runaway** — Watchdog timer added in background executor with 600 s
   default timeout. Catches runaway pick operations and forces safe stop.
   *(yanthra-safety-and-resilience, Mar 02)*

6. **Consecutive failure chains** — 104 events in Feb addressed with per-joint failure
   counters, escalation ladder (warn, throttle, disable, safe mode), and automatic
   safe mode entry. *(yanthra-safety-and-resilience, Mar 02)*

7. **JSON pick timing fields** — j3_ms, j4_ms, j5_ms now populated correctly. Additional
   fields added: polar coordinates, plan_status, delay_ms, position feedback,
   throttle/pause indicators. *(field-trial-readiness-fixes Mar 02 +
   field-trial-logging-gaps Mar 15)*

8. **capture_ms instrumentation** — Was always 0 in Feb logs. Now measured as a separate
   timing span in the detection pipeline. *(field-trial-readiness-fixes, Mar 02)*

9. **7 critical safety bugs** — Across 5 packages: unguarded motor commands, missing
   bounds checks, unsafe shutdown sequences. All resolved.
   *(phase-1-critical-fixes, Mar 11)*

10. **Blocking motor service removed** — `wait_for_completion=true` now returns a
    deprecation error. 3 threading locks added protecting 17+ shared attributes in
    `vehicle_control_node.py`. *(phase-2-critical-fixes, Mar 11)*

11. **Motor init/shutdown hardening** — Proper init sequence with verification gates,
    timeout-stop when position commands exceed deadline, command deduplication eliminating
    ~96% of redundant CAN traffic. *(motor-control-hardening, Mar 15)*

12. **Stale detection handling** — Configurable `cache_validity_ms` parameter,
    `detection_age_ms` field in JSON output, cache hit/miss counters for monitoring.
    *(cotton-detection-reliability, Mar 06)*

13. **GPIO pin conflicts** — 14 conflicts across packages eliminated by consolidated
    pin assignment table. *(gpio-pin-consolidation, Mar 08)*

14. **CAN fault detection** — CAN bus error frames and fault counters wired into the
    safety monitor for automatic response. *(motor-control-safety, archived)*

15. **E-stop enforcement** — Safety monitor enforces emergency stop commands across all
    motor controllers. *(safety-monitor-enforcement, archived)*

### Mitigated (2)

16. **Steering thermal peaks (73–80 C)** — Timeout-stop prevents indefinite motor push
    and command deduplication eliminates ~96% of redundant CAN traffic, reducing heat
    generation. Hardware cooling (heatsinks, forced air) still recommended for sustained
    operation. *(motor-control-hardening, Mar 15)*

17. **Service discovery timeouts (126 in Feb)** — Pre-call readiness check, configurable
    timeout, and periodic health probing reduce occurrence. Underlying DDS discovery
    root cause not addressed. *(yanthra-safety-and-resilience, Mar 02)*

### Need Field Validation (3)

18. **Zero spatial coordinates (17% in Feb)** — Diagnostics deployed (bounding box
    logging, image annotations) plus 5 stereo depth parameters now runtime-configurable.
    Actual rate reduction requires field tuning with real cotton plants.

19. **Wasted detection rate (79.6% in Feb)** — Multiple detection pipeline improvements
    (stale cache handling, configurable thresholds, age tracking) but no field measurement
    of the new rate yet.

20. **Pick cycle time degradation (21.8%/hour in Feb)** — No direct fix implemented.
    Instrumentation improved (per-joint timing, throttle indicators) to diagnose root
    cause during next field trial.

---

## 5. New Issues from March 16

### Regressions and Failures

1. **FATAL crash on CAN failure** — Newer code exits immediately on CAN init failure
   instead of degrading gracefully. Likely a consequence of motor-control-hardening's
   stricter init sequence (verify_clean / verify_active gates). In February, CAN was
   already up so this code path was never exercised.

2. **Camera temperature elevated** — Arm_1 OAK-D reached 74.2 C vs 63 C peak in Feb.
   Detection was running without picking load. May indicate thermal regression in
   detection pipeline or higher ambient temperature.

3. **Stale vehicle binaries** — Vehicle RPi had binaries **116.9 hours behind** arm_1.
   The cross-compile and deploy step was missed for the vehicle RPi. No automated
   freshness check exists.

4. **Arm_2 cascading service failures** — 846 service failure events as nodes repeatedly
   tried to start without hardware. No circuit breaker or backoff to stop retry storms.

5. **OAK-D camera not detected on arm_2** — USB enumeration failure. Either a hardware
   fault (cable, port, camera) or USB power budget exceeded on the RPi.

6. **No pre-flight CAN validation** — 5.5 hours wasted because there was no automated
   check that CAN hardware was functional before launching ROS2 nodes. A 30-second
   script running `ip link show can0` and `cansend can0 000#00` would have caught all
   three failures immediately.

7. **Model file not deployed** — `yolov112.blob` not at expected path on arm RPis.
   Falls back to default model. Non-blocking but degrades detection accuracy.

### Positive Observations

8. **MQTT improved** — 99.5% uptime in March vs 97.7% in Feb. The communication layer
   is solid.

9. **Clock sync worked** — RTC drift mitigation via provision-time NTP sync appears
   effective. No timestamp anomalies in logs.

### Infrastructure Issues

10. **Vehicle node crash loop** — Both `vehicle_control_node` and
    `mg6010_controller_node` crash-looped attempting to access `can0` that did not exist
    as a network interface. No graceful fallback.

11. **No graceful degradation for missing hardware** — All nodes treat missing CAN or
    camera as fatal. For a field robot that may power on before all peripherals are ready,
    nodes should log errors and wait for hardware to become available rather than
    exit immediately.

---

## 6. Critical Actions Before March 25 Field Trial

### MUST DO (Blocking)

1. **Create pre-flight hardware validation script** — Check CAN bus (interface exists,
   driver loaded, can send/receive), camera (USB enumeration, device node present),
   motor power (CAN traffic response), and network connectivity. Run before every
   test session. Target: 30-second pass/fail.

2. **Verify CAN HATs physically installed** on all 3 RPis and device tree overlays
   (`dtoverlay=mcp2515-can0`) configured in `/boot/firmware/config.txt`.

3. **Deploy fresh cross-compiled binaries to ALL RPis** — not just arms. Add binary
   timestamp comparison to pre-flight script to catch stale deployments.

4. **Verify OAK-D cameras detected** on both arm RPis (`lsusb` shows Luxonis device,
   `/dev/video*` or depthai enumeration succeeds).

5. **Lab test: complete pick cycle** on at least one arm with March 15 software.
   Validate that the full pipeline (detect, plan, pick, retract) works end-to-end
   before going to the field.

### SHOULD DO

6. Add graceful degradation for CAN init failure — wait-and-retry loop with backoff
   instead of FATAL exit. Allow the node to start and become operational when hardware
   is connected.

7. Add circuit breaker for service retry storms — cap retry attempts, use exponential
   backoff, log a single summary instead of 846 individual failure messages.

8. Fix model file deployment — ensure `yolov112.blob` is included in the sync/deploy
   step and lands at the expected path.

9. Add camera thermal monitoring — log temperature periodically, throttle detection
   frame rate if temperature exceeds threshold.

### NICE TO HAVE

10. Automated binary freshness comparison across all RPis — `sync.sh` reports build
    timestamps from each RPi and flags any that are more than N hours behind.

11. Pre-flight script outputs a structured pass/fail dashboard — green/red per
    subsystem, suitable for quick visual confirmation before launch.

---

## 7. Software vs Hardware Readiness Assessment

| Area             | Software Readiness | Hardware Readiness | Field Validated |
|------------------|--------------------|--------------------|-----------------|
| Arm picking      | HIGH (108 changes, 2,129 tests) | UNKNOWN (never tested Mar 16) | NO |
| Vehicle steering | HIGH (init fix, thermal mitigation) | UNKNOWN (no CAN on Mar 16) | NO |
| Vehicle drive    | HIGH (ODrive recovery rewrite) | UNKNOWN (no CAN on Mar 16) | NO |
| Detection        | HIGH (diagnostics, depth params) | PARTIAL (camera works on arm_1) | NO |
| MQTT comms       | HIGH | HIGH (99.5% uptime) | YES |
| Multi-arm coord  | NOT STARTED | PARTIAL (2 arms mounted) | NO |

---

## 8. Conclusion

**Software readiness is HIGH.** 108 OpenSpec changes addressing every critical issue from
February have been implemented, tested (2,129 automated tests), and deployed. The safety
bugs, motor control failures, logging gaps, and ODrive crashes that plagued February are
resolved in code.

**Hardware readiness is UNKNOWN.** March 16 never progressed past CAN initialization on
any RPi. The physical layer — CAN HATs, wiring, termination, motor power, camera USB —
remains unvalidated with the current hardware configuration.

**The gap between software and hardware readiness is the primary risk for March 25.** The
software is ready to be tested; the hardware has not been confirmed capable of running it.

**A mandatory pre-flight hardware validation script would have saved the entire March 16
session.** The 5.5 hours spent debugging could have been reduced to 5 minutes with an
automated check of CAN interfaces, camera enumeration, and motor power before launching
any ROS2 nodes.

**Before March 25, the team MUST:**

1. Validate CAN hardware on all 3 RPis (HATs installed, overlays configured, traffic flows)
2. Deploy fresh binaries to all RPis and verify timestamps match
3. Run at least one complete pick cycle in the lab with March 15 software
4. Create and run the pre-flight validation script

Until the hardware layer is confirmed functional, the 108 software improvements remain
theoretical. March 25 must be the trial that bridges this gap.
