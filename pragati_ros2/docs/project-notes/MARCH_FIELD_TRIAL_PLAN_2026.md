# March Field Trial Plan (2026)

**Target Date:** March 25, 2026
**Prep Deadline:** March 20, 2026 (lab testing complete)
**Created:** March 03, 2026
**Last Updated:** March 24, 2026 (March 24 pre-field test results added — last session: 272 picks, 32.0% success rate, both arms + vehicle MQTT trigger working. COLLISION_BLOCKED is dominant failure mode (87.6% of failures). See Section 4B.) · 2026-03-25 — Post-trial closure with field results
**Project Owner:** Manohar
**Execution Lead:** Udayakumar
**Scope:** 2 arms + vehicle, single row of cotton plants
**Focus:** Two-arm picking operation on a single row

---

## Executive Summary

The March 2026 field trial builds on the February 26 trial results (26.7% pick success rate, 73% workspace violations, ODrive stall loops). This trial upgrades from single-arm to **two-arm operation** on a single row of cotton plants. Key focus areas:

1. **Arm reliability** — Fix L3 offset/tuning, improve detection accuracy (YOLOX migration), benchmark all arm subsystems
2. **Vehicle stability** — ODrive PID tuning, error recovery, three-wheel steering integration
3. **Two-arm coordination** — Collision avoidance, independent arm operation
4. **New integrations** — IMU + RTK GPS (first version), improved logging across all nodes

**New field site required** — The February field may not be suitable (2.75ft row spacing too dense). A new field must be identified and prepared. **Owner: Amirtha.**

### February 2026 Trial Key Metrics (Baseline)

| Metric | Value |
|--------|-------|
| Pick success rate | 26.7% (315/1,181) |
| Workspace violations | 73% of attempts |
| Arms tested | 1 (arm2 hardware unavailable) |
| ODrive crashes | 9 sessions (stall loop) |
| Steering motors | All 3 error code 8, peaks 73-80C |
| Detection acceptance rate | 52.6% |
| Zero spatial coordinates | 17% (503 events) |
| Pick cycle time avg | 1,800ms |

### March 2026 Trial Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| Pick success rate | >60% | Realistic given workspace + calibration fixes |
| Detection accuracy | 90-95% | YOLOX 3-class model with sun glare filtering |
| Pick cycle time | <2,000ms (target 2,000ms) | Benchmark and optimize joint timings |
| Workspace violations | <30% | L3 offset correction + better vehicle positioning |
| Arms operational | 2 | Two-arm coordination validated |
| Zero spatial coordinates | <5% | Depth reliability improvements — diagnostics now available (bbox logging + image annotation), 5 stereo depth params configurable for field tuning |
| Wasted detection rate | <40% | Was 79.6% in Feb — most accepted detections failed to produce a pick |

### Software Progress Summary (Mar 03–15)

108 OpenSpec changes archived total (32 Feb + 75 Mar + 1 undated). Key completions by area:

| Area | Changes | Highlights |
|------|---------|------------|
| Software Hardening (U1) | 9/9 ✅ + 1 phase-2 ✅ + 2 Mar 15 ✅ | Safety, resilience, MQTT, e-stop enforcement, CAN fault detection, **phase-1-critical-fixes** ✅ Mar 11 (f1685f2c) — 7 critical safety bugs fixed. **phase-2-critical-fixes** ✅ Mar 11 (d3e0885c) — blocking motor service removed (wait_for_completion=true returns deprecation error) + 3 threading locks added to vehicle_control_node.py (17+ shared attrs protected). **motor-control-hardening** ✅ Mar 15 (35ab4be22) — motor init/shutdown hardening, timeout stop fix, command dedup, shutdown handler improvements (34 tests). All 9/9 critical safety items now resolved. |
| Dashboard | 26 archived ✅ | Backend restructure, Preact migration, UX overhaul, PID tuning, motor config, foundation-fix ✅, tab-wiring-fix ✅, fleet-hub ✅. **Dashboard redesign** ✅ — entity-centric architecture fully implemented: entity-core (67/67), motor-rosbag (38/38), operations (25/25), ros2-subtabs (56/56). All 4 redesign changes + 8 follow-up fixes archived. |
| Motor Control | 4 ✅ | Async commands, protocol fixes, safety monitor wired to motors |
| Testing / Simulation (U8) | 4 ✅ | Mock CAN simulator, motor sim mode, arm simulation testing, E2E pipeline test. **~2,129 tests**: 512+ C++ gtest, 672+ dashboard pytest, 326+ scripts pytest, 382+ src pytest (107 new tests from motor-control-hardening, detection-zero-spatial-diagnostics, stereo depth params, field-trial-logging-gaps) |
| Arm / Motion | 4 ✅ | Eject sequence, J4 parking, EE flush |
| Cotton Detection | 1 ✅ + 2 Mar 15 ✅ | Workspace filter, stereo tuning, telemetry. **detection-zero-spatial-diagnostics** ✅ Mar 15 (e0b006d56) — bbox logging in zero-spatial WARN messages + red "DEPTH FAIL" image annotations (18 tests). **Stereo depth param configurability** ✅ Mar 15 (0c15e3ad0) — 5 hardcoded stereo depth params exposed as configurable ROS2 parameters (23 tests). Defaults unchanged — ready for field experimentation. |
| Build / Deploy | 3 ✅ | sync.sh/build.sh fixes, fleet audit, log date filter |
| Logging / Instrumentation | 3 ✅ | Boot timing, unified JSON logging, **field-trial-logging-gaps** ✅ Mar 15 (b65e189bc) — 5 JSON logging gaps fixed: polar coords, plan_status, delay_ms, position feedback, detection throttle/pause (32 tests) |
| GPIO / Hardware | 1 ✅ | gpio-pin-consolidation — implemented and archived (545d1ff3, Mar 08). 14 GPIO pin conflicts eliminated (GAP-GPIO-001 resolved). Physical verification pending (`docs/project-notes/GPIO_PIN_REVIEW.md`) |

**Active:** None — all dashboard redesign changes archived (entity-core 67/67, motor-rosbag 38/38, operations 25/25, ros2-subtabs 56/56)
**Parked:** commercial-licensing-compliance, log-analyzer-improvements, requirements-audit-jan-2026

---

## Field Site Preparation

**Field Site:** Manivel's field, Nedungur (found by Amirtha)

| Parameter | Measured Value |
|-----------|---------------|
| Row-to-row spacing | 3 ft (~0.91 m) — meets ≥3 ft requirement |
| Cotton average height | <3 ft (<0.91 m) |
| Cotton maximum height | 4 ft (~1.22 m) |
| Plant total height (stems + branches) | 4-5 ft (1.2-1.5 m) |
| Cotton boll size | Not yet measured |

| Task | Owner | Deadline | Status |
|------|-------|----------|--------|
| Identify new field site suitable for vehicle + 2-arm operation | Amirtha | Mar 10 | ✅ Mar 05 — Manivel's field, Nedungur |
| Verify row spacing >3 feet (vehicle + arm clearance) | Amirtha | Mar 10 | ✅ Mar 05 — 3 ft confirmed, sufficient |
| Arrange field access and logistics for Mar 25 | Amirtha | Mar 17 | ⬜ |
| E-way bill and transportation permits for field trial | Amirtha / Nadimuthu | Mar 20 | ⬜ |
| Pre-visit field measurement (row spacing, plant height, boll size) | Amirtha | Mar 20 | 🔧 Row spacing + heights measured; boll size pending |

---

## Hardware Preparation

### Arms

5 arms + 1 set of backup components planned:

| # | Allocation | Owner | Deadline | Status |
|---|-----------|-------|----------|--------|
| 1-2 | Mounted on vehicle (field trial) | Dhinesh | Mar 17 | ⬜ |
| 3 | Standalone software testing | Dhinesh | Mar 10 | ⬜ |
| 4 | Electrical / Electronics / Mechanical testing | Dhinesh | Mar 14 | ⬜ |
| 5 | Zoho team standalone testing | Dhinesh | Mar 17 | ⬜ |
| +1 | Backup components (spare motors, belts, joints) | Dhinesh | Mar 20 | ⬜ |

Camera position remains same (not switching to horizontal) — Decided.

### Arm Team

| Role | Owner |
|------|-------|
| Mechanical | Dhinesh |
| Electronics | Gokul / Joel |
| Electrical | Rajesh |

---

## Section 1: Arm Tasks

> **Status:** ⬜ Not started · 🔧 In progress · ✅ Done (date, commit) · ⏸️ Blocked

### 1.1 Calibration & Tuning (CRITICAL)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A1 | **L3 PID/position re-tuning** for new EE payload weight | Gokul | Mar 12 | HIGH | ✅ Done (Mar 25) — resolved based on field performance (52.9% pick success) |
| A2 | **L3 offset correction** — error calculation and corrections. Physically verify camera pitch angle (spirit level + protractor) against URDF 45° assumption. | Shwetha | Mar 17 | HIGH | ⬜ |
| A3 | **L5 home recalibration** — verify L5 reaches full 0/home after J5 belt repair | Dhinesh / Gokul | Mar 10 | MEDIUM | ✅ Done (Mar 25) — resolved |
| A4 | **L5 depth control investigation** — determine if depth issue is detection error or yanthra_move calculation error | Shwetha | Mar 17 | MEDIUM | ⬜ |

### 1.2 Detection & Model (CRITICAL)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A5 | **YOLOX vs YOLOv11 analysis** — clear comparison: licensing, accuracy, latency, pros/cons. Document before migration decision. | Udayakumar / Shwetha / Arun | Mar 06 | HIGH | ✅ Mar 04 (dd567196) |
| A6 | **YOLOX migration** — migrate from YOLOv11 to YOLOX with 3 classes: cotton, not-pickable, sun_glare. Retrain for false positives and failed cotton detections. Target: 90-95% detection accuracy. Evaluate adding boll-size filtering — either as 4th class or as post-detection size threshold based on bounding box area. **Pipeline: NeuralNetwork + SpatialLocationCalculator (YoloSpatialDetectionNetwork incompatible with YOLOX output format).** | Shwetha / Arun | Mar 18 | HIGH | 🚫 PARKED for March trial. Staying with YOLOv11. YOLOX pipeline validated (NeuralNetwork + SpatialLocationCalculator) but accuracy/timing concerns. Resume post-trial. |
| A7 | **Zero spatial coordinate fix (0,0,0 detections)** — reduce from 17% to <5%. Investigate camera calibration, L3 FOV blocking, and DepthAI depth failures. Also investigate high stale frame flush rate (6.0 avg frames flushed per detection request). | Shwetha / Arun | Mar 17 | HIGH | 🔧 Diagnostics deployed by Udayakumar: bbox logging in zero-spatial WARN messages + red "DEPTH FAIL" annotations on output images (e0b006d56, Mar 15). 5 stereo depth params now configurable for field tuning (0c15e3ad0, Mar 15). Defaults unchanged — ready for field experimentation. Rate reduction requires field testing with tuned params. Shwetha/Arun to tune params at field trial. |
| A8 | **Stale detection handling** — address 19.6% stale detection rate (>2s old). Add max detection age threshold or re-detection before pick. Target: <5% stale rate, max 2s age, 0% severely stale (>10s). | Udayakumar | Mar 17 | MEDIUM | ✅ Mar 06 (cotton-detection-reliability: configurable cache_validity_ms, detection_capture_time, cache hit/miss counters, detection_age_ms in JSON) |

### 1.3 Benchmarking (HIGH)

All benchmarks must include **current draw measurement** (per-joint and total arm) in addition to the primary metric. YOLOv11 baseline timing: ~69ms p50 inference (from `YOLO_MODELS.md`).

**February 2026 baselines** (extracted from 1,181 pick events across 9 sessions, 2h46m):

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A9 | **Benchmark cotton detection accuracy** — systematic test with known cotton positions, measure precision/recall/F1. Include current draw during detection cycles. **Feb baseline (proxy):** 75.5% frame detection rate, 14.6% stereo depth failure rate on white cotton, 52.6% acceptance rate post-filtering, 9.2% end-to-end conversion (NN → successful pick). Mean confidence 0.744. Confidence is NOT a strong predictor of pick success (0.5-0.6 band: 26.2% vs 0.9+ band: 39.6%) — failure mode is spatial/mechanical, not detection quality. Classical precision/recall/F1 requires ground-truth labels not present in field logs. **Still needed post-March:** (1) Controlled ground-truth test with known cotton positions to compute true precision/recall/F1. (2) Compare stereo depth failure rate with new configurable params. (3) Assess whether workspace pre-filtering (cotton-detection-reliability change) reduced wasted detections. (4) Current draw profiling during detection cycles. | Shwetha / Arun | Mar 18 | HIGH | ⬜ |
| A10 | **Benchmark arm position accuracy** — measure actual vs commanded position across workspace envelope. Investigate left-right pick yield asymmetry (4.6x difference at -150mm vs +150mm in Feb). Determine if mounting asymmetry or J3-related. Include per-joint current draw. **Feb baseline:** Motor-level mean |error| = 0.0035 (348 events, 100% within 0.050 tolerance, 93.4% within 0.010). Planner-level mean |error| = 0.0169 (629 events, 100% within 0.050). Homing accuracy: mean 0.0033, max 0.0055 (9/9 within tolerance). **Still needed post-March:** (1) Root-cause the 4.6x left-right pick yield asymmetry (mounting, J3, or camera FOV?). (2) Map joint-units to physical degrees using transmission ratios (J3: internal_gear=6.0). (3) Position accuracy across full workspace envelope (Feb data is mostly near home). (4) Per-joint current draw profiles at different positions. (5) Compare position feedback accuracy now that blind sleeps are replaced. | Shwetha | Mar 18 | HIGH | ⬜ |
| A11 | **Benchmark joint timings** — measure both full cycle time (trigger → ready-for-next-pick) and pick phase time (approach → retract) separately. Plan improvements to achieve 2-sec pick cycle target. Include per-joint current draw profiles. YOLOv11 baseline: ~69ms p50 inference. **Feb baseline:** Real pick cycle (excluding IK rejections): ~6,434ms median (~48% approach, ~19% capture, ~49% retreat). J5+EE is the bottleneck (p50 1,170ms). NN inference: 47.7ms mean, 42ms median. Total processing: 65.3ms mean. Note: per-joint timing fields (j3_ms, j4_ms, j5_ms) were hardcoded to 0 in Feb — now fixed for March. **Still needed post-March:** (1) Per-joint timing breakdown (j3_ms, j4_ms, j5_ms) — now populated, will appear in March logs. (2) Compare total cycle time with position-feedback (replaces blind sleep). (3) Concrete improvement plan to hit 2-sec target — identify which phases can be parallelized or shortened. (4) Current draw profiles per joint per phase. (5) Assess impact of J4 parking optimization and serpentine scan changes. | Gokul | Mar 18 | HIGH | ⬜ |
| A12 | **J3 position precision trend** — ~~investigate degrading homing error (mean 0.0033, trending upward). Determine if mechanical wear or software drift.~~ **RESOLVED from Feb data:** No precision degradation detected. Health score 1.0 for all 300 motor_health samples. Position errors showed no upward trend across 5 sessions over 2 hours (mean |error| range: 0.0028-0.0041 per session, no monotonic increase). Temperature stable at 44.2°C mean (delta -0.6°C). Command success 993/993 (100%). Zero timeouts, zero TX failures. **Still needed post-March:** March trial provides extended-duration validation (target: 5+ hours vs Feb's 2h46m). If precision degrades over longer sessions, mechanical wear hypothesis returns. | Gokul | Mar 12 | MEDIUM | ✅ Mar 17 (resolved from Feb log analysis) |
| A13 | **Pick cycle time degradation** — ~~investigate 21.8%/hour degradation root cause (1,610ms → 2,312ms over session).~~ **RESOLVED: The 21.8%/hour degradation was a statistical artifact.** Root cause: the log analyzer mixed three event types into one average — 64.4% instant IK rejections (0-1ms), 8.9% recovery rejections (~1,206ms), and 26.7% real picks (4,489-7,851ms). As the proportion of 0ms rejections naturally fluctuated (67.4% → 57.0%), the blended average shifted upward. **Actual real-pick cycle time is flat at ~6.4s** (R²=0.002, no trend). Motor temps stable, current draw stable, no mechanical degradation. Log analyzer trend detector fixed to exclude instant rejections (prevents false alarm in March data). **Still needed post-March:** Confirm real-pick cycle time remains flat over 5+ hour session with the new software (position feedback, eject sequence, workspace filtering all add phases). | Gokul | Mar 12 | MEDIUM | ✅ Mar 17 (statistical artifact, log analyzer fixed) |

### 1.4 End Effector (HIGH)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A14 | **EE motor tests** — new motor and setup with 0.5s-on / 0.5s-reverse test cycle | Joel / Dhinesh | Mar 17 | HIGH | ⬜ |
| A15 | **EE replacement motor evaluation** — identify and test replacement motors if current motors are insufficient | Joel / Dhinesh | Mar 18 | HIGH | 🔧 New motor identified, ordering for testing |
| A16 | **EE roller seed jamming investigation** — cotton seeds stuck in roller (pin size ~13mm). Assess pin spacing vs seed size. | Joel / Dhinesh | Mar 17 | MEDIUM | 🔧 Roller pin sizing corrected by Dhinesh, tested with no cotton/seed jams |

### 1.5 Mechanical (HIGH)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A17 | **Arm mechanical review** — prevent belt breakage (belt stress analysis), EE hitting collection box, swinging collection box | Dhinesh | Mar 17 | HIGH | ✅ Done (Mar 25) — resolved |
| A18 | **Collection box redesign/betterment** — address position, shape, stability. Current: wheel 250mm, box width 180mm. | Amirtha | Mar 18 | HIGH | ✅ Done (Mar 25) — resolved, worked adequately in field |
| A19 | **Arm profile / shrouding** — address arm backside getting stuck in plants in dense rows | Dhinesh | Mar 17 | MEDIUM | 🚫 Deferred |
| A20 | **Drop/throw trajectory tuning** — cotton overshooting and undershooting collection box. Tune angle/velocity for consistent collection. | Gokul / Shwetha | Mar 18 | MEDIUM | ✅ Done (Mar 25) — resolved (98.4% success when reachable) |
| A28 | **Power box enclosure fix** — current top cover removed, using sliding mechanism as workaround. Design and implement proper enclosure (hinged lid or secure sliding). | Dhinesh | Mar 17 | MEDIUM | ⬜ Not targeted for March field trial |

### 1.6 Two-Arm Operation (HIGH)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A21 | **Two-arm collision avoidance and planning** — software-level collision avoidance between arm1 and arm2 (alternating mode, workspace partitioning, or coordinated planning). Physical mounting geometry handled by Dhinesh. | Vasanth | Mar 17 | HIGH | ✅ Done (Mar 25) — resolved, block-and-skip implementation worked |
| A27 | **System-level workspace analysis** — model the compound workspace: arm mounting height + linkage length + vehicle-to-row positioning distance. Predict reachable workspace percentage at new field site row spacing. Compare to February 27% violation baseline. | Shwetha / Amirtha | Mar 18 | HIGH | 🔧 In progress (Shwetha/Amirtha) |
| A29 | **URDF joint limits** — define and enforce proper joint limits in URDF for all arm joints. Prevent commanded positions outside safe mechanical range. | Vasanth | Mar 14 | HIGH | ⏳ Blocked — tied to collision avoidance decision (A21) |
| A30 | **Reachability / workspace validation** — validate arm workspace envelope against URDF limits. Verify reachable volume matches expected picking zone. Flag unreachable detection targets before pick attempt. | Vasanth | Mar 17 | HIGH | ⏳ Blocked — tied to collision avoidance decision (A21) |

### 1.7 Instrumentation Fixes (MEDIUM)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A22 | **Fix JSON pick timing fields** — j3_ms/j4_ms/j5_ms hardcoded to 0 in `emit_pick_complete_json` despite values being measured in `executeApproachTrajectory()`. Propagate j3_duration/j4_duration/j5_duration to JSON. Also add retreat sub-phase timing (J5 retract, eject, J4 home) and trigger-to-cycle-start timing to JSON. | Udayakumar | Mar 17 | MEDIUM | ✅ Mar 02 (6df79bb0), logging gaps fixed Mar 15 (b65e189bc — field-trial-logging-gaps: polar coords, plan_status, delay_ms, position feedback, throttle/pause) |
| A23 | **Instrument capture phase** — capture_ms always 0; EE activation is embedded in approach trajectory, not measured separately. Also instrument return-home (J4 homing after eject) which has no timing at all. | Udayakumar | Mar 17 | MEDIUM | ✅ Mar 02 (6df79bb0) |
| A24 | **ArUco detection instrumentation** (Gap 20) | Udayakumar | Mar 18 | MEDIUM | ⬜ |
| A25 | **Position tracking instrumentation** (Gap 22) | Udayakumar | Mar 18 | MEDIUM | ✅ Mar 15 (b65e189bc — field-trial-logging-gaps Gap 4: position_feedback JSON event with per-joint ok/error fields) |

### 1.8 Dynamic Picking Preparation (April Target)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| A26 | **Dynamic picking preparation** — (a) Review arm pick cycle data and identify requirements for dynamic (in-motion) picking integration, (b) Set up development environment and basic ROS2 node skeleton, (c) Observe March 25 field trial and document dynamic picking requirements from field conditions | Navneeth | Mar 24 (a,b) / Mar 25 (c) | MEDIUM | ✅ Covered by existing log analyzer + structured JSON pick_complete events |

---

## Section 2: Vehicle Tasks

### 2.1 Drive Motors (CRITICAL)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| V1 | **ODrive PID tuning** — calibrate for field terrain conditions | Gokul | Mar 12 | HIGH | ✅ Done (Mar 25) — resolved (0 crashes on Mar 25) |
| V2 | **ODrive error recovery mechanism** — fix stall-recovery-restall loop (1,183 errors in Feb trial) | Gokul | Mar 12 | HIGH | ✅ Mar 05 (92bf70b3) |
| V3 | **Drive motor idle timeout fix** — motors fail to respond after prolonged idle periods | Gokul | Mar 19 | MEDIUM | ✅ Mar 05 (92bf70b3) |
| V4 | **Drive stop service timeout fix** — 29 timeouts in Feb trial | Gokul | Mar 19 | MEDIUM | ✅ Mar 05 (92bf70b3) |

### 2.2 Steering (HIGH)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| V5 | **Three-wheel steering code integration and testing** — Verify steering angle accuracy (90° turns). | Vasanth / Arvind | Mar 18 | HIGH | ⬜ |
| V6 | **Steering motor error code 8 investigation** — all 3 MG6012-i6 steering motors had error code 8 with thermal peaks 73-80C. steering_left worst: 26.7% timeout, health 0.6, current spike 3,318% increase. | Udayakumar | Mar 12 | HIGH | ✅ Mar 15 — Root cause: init sequence sent motor_on before clear_errors, inheriting err_flags:8 from prior session. Fixed in motor-control-hardening (e29d5be67): new sequence is motor_stop → clear_errors → verify_clean → motor_on → verify_active. |
| V7 | **Steering motor thermal management** — current spikes: front 27 (5.67A max), left 39, right 4. Investigate cooling or duty cycle limits. | Udayakumar | Mar 12 | HIGH | ✅ Mar 15 — Two software mitigations in motor-control-hardening: (1) timeout-stop sends motor_stop when position command times out, preventing indefinite push against obstruction (primary cause of 76°C peaks); (2) command dedup eliminates ~96% redundant CAN traffic from joystick polling loop. Hardware cooling still recommended but no longer critical. |

### 2.3 New Integrations (HIGH)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| V8 | **IMU integration** — first version, get data and feedback for further analysis | Vasanth / Arvind | Mar 18 | HIGH | ⬜ |
| V9 | **RTK GPS integration** — first version, get data and feedback for further analysis | Vasanth / Arvind | Mar 18 | HIGH | ⬜ |

### 2.4 Infrastructure (MEDIUM)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| V10 | **Improved logging and data capture** — bring vehicle node logging to parity with arm nodes (structured JSON, timing, health metrics) | Gokul | Mar 19 | MEDIUM | ✅ Done (Mar 25) — resolved (684MB comprehensive logs collected) |
| V11 | **IP address setup** — static IP configuration for all RPis | Gokul | Mar 10 | MEDIUM | ✅ Done (Mar 25) — resolved (DHCP reservations working: 100/101/102) |
| V12 | **E-stop integration** — hardware E-stop with proper GPIO wiring | Gokul / Rajesh | Mar 12 | HIGH | 🔧 Hardware done — E-stop cuts vehicle motor power (drive + steering ODrive supply) only. Standalone tested with multimeter. Software GPIO→motor-stop bridge deferred (acceptable for March — supervised trial). Note: arm motors have NO hardware E-stop. |
| V13 | **Sequential power-up** — avoid voltage spikes when starting multiple motors simultaneously | Rajesh | Mar 17 | HIGH | 🚫 PARKED — material mounting was difficult |
| V14 | **Encoder configuration verification** — output shaft reading only (the encoder connected to the shaft is what we read). Verify quadrature decoding correctness for MG6012-i6 steering and ODrive drive motors. | Gokul | Mar 12 | MEDIUM | 🔧 After-shaft reading confirmed sufficient for March trial. MG6012-i6 built-in 16-bit encoder (16384 counts). No additional verification needed. |
| V15 | **RTC drift fix** — RPi 4B has no battery-backed RTC. Either install hardware RTC module or implement peer-to-peer time sync. Affects log timestamp accuracy. | Gokul | Mar 19 | MEDIUM | 🔧 Mitigated — clock sync from dev machine during provision. No hardware RTC installed. |
| V16 | **Drive motor temperature monitoring** — ODrive motors have no temp sensors. Evaluate adding external temperature sensors. | Rajesh / Gokul | Mar 18 | MEDIUM | ⬜ |
| V17 | **Integration testing during Gokul/Shwetha absence** — run vehicle + arm integration tests on Mar 13, 17. Report issues for team to fix on return. | Vasanth | Mar 17 | MEDIUM | 🔧 Partially done |
| V18 | **ODrive slope/terrain test** — verify ODrive motors hold position, drive uphill, and brake downhill on simulated field terrain (ramp or slope). Test with full vehicle + 2 arms weight. | Gokul | Mar 19 | HIGH | ✅ Done (Mar 25) — resolved (done) |
| V19 | **DDS discovery test with 3 RPi nodes** — verify ROS2 service discovery works reliably across 3 RPis (vehicle + 2 arms) on same network. Monitor for discovery timeouts over 30-minute test. Test script: `scripts/diagnostics/test_dds_discovery_3node.sh`. Phase 1: shared-domain (all DOMAIN_ID=0) verifies cross-node discovery. Phase 2: production-isolation (separate DOMAIN_IDs, LOCALHOST_ONLY=1 on arms) verifies no bleed. **Result (Mar 6):** Full 30-min test PASSED — Phase 1: 30/30 discovery checks OK, Phase 2: 30/30 isolation checks OK (0 cross-domain bleed). CycloneDDS on all 3 RPis (vehicle=192.168.137.203, arm1=192.168.137.12, arm2=192.168.137.238). | Udayakumar | Mar 19 | MEDIUM | ✅ |
| V20 | **Pre-flight hardware validation script** — automated CAN bus, camera, motor power, network, and binary freshness checks. Run before every test session. **Lesson from Mar 16:** 5.5 hours wasted debugging CAN hardware that a 30-second pre-flight check would have caught. Must verify: (1) CAN HAT device tree overlay loaded, (2) can0 interface up with TX/RX, (3) OAK-D camera USB enumeration, (4) motor power supply on, (5) binary timestamp matches latest build, (6) all RPis reachable on network. Script should output clear PASS/FAIL per check. | Udayakumar / Gokul | Mar 20 | **CRITICAL** | ⬜ NEW — added after Mar 16 integration test failure |

---

## Section 3: Program Management & Software Hardening (Udayakumar)

### 3.1 Software Hardening (Ongoing)

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| U1 | **Software hardening and resilience** — OpenSpec changes: ~~cotton-detection-reliability~~ ✅, ~~cotton-eject-sequence~~ ✅, ~~eject-sequence-feedback-and-flow~~ ✅, ~~j4-parking-optimization~~ ✅, ~~launch-system-hardening~~ ✅, ~~motor-control-safety~~ ✅, ~~motor-control-runtime-hardening~~ ✅ Mar 07, ~~safety-monitor-enforcement~~ ✅ Mar 07, ~~phase-1-critical-fixes~~ ✅ Mar 11 (f1685f2c) — 7 critical safety bugs fixed across 5 packages, ~~phase-2-critical-fixes~~ ✅ Mar 11 (d3e0885c) — blocking motor service removed + vehicle thread safety locks (3 locks, 17+ attrs). ~~motor-control-hardening~~ ✅ Mar 15 (35ab4be22) — motor init/shutdown hardening, timeout stop fix, command dedup, shutdown handler improvements. ~~detection-zero-spatial-diagnostics~~ ✅ Mar 15 (e0b006d56) — bbox logging + image annotation for zero-spatial field analysis. log-analyzer-improvements parked (post-trial). 12/12 hardening changes archived. All 9/9 critical safety items resolved. | Udayakumar | Mar 24 | HIGH | ✅ 12/12 changes archived |
| U2 | **Requirements audit continuation** — requirements-audit-jan-2026 OpenSpec change. Longer-term effort, not tied to March trial deadline. | Udayakumar | Ongoing | LOW | ⬜ |
| U8 | **Unit test and integration test setup** — establish proper test infrastructure. Run existing unit tests, fix failures from recent changes. Set up integration test framework for multi-node (vehicle + 2 arms) scenarios. **Progress:** 4 OpenSpec test/sim changes archived (mock-can-motor-simulator, motor-node-simulation-mode, full-pipeline-integration-test, arm-simulation-testing). **~2,129 tests** across gtest (512+), dashboard pytest (672+), scripts pytest (326+), src pytest (382+). 107 new tests added Mar 15 (motor-control-hardening 34, detection-zero-spatial-diagnostics 18, stereo-depth-param-configurability 23, field-trial-logging-gaps 32). Remaining: multi-node integration test gaps. | Udayakumar | Mar 20 | HIGH | 🔧 Substantially complete — 4 changes archived, ~2,129 tests |
| U9 | **Power budget analysis** — measure and document per-subsystem power consumption: each arm (motors + RPi + camera), vehicle (drive motors + steering + RPi), total system. Determine battery endurance for 2-arm operation. | Udayakumar | Mar 18 | HIGH | ✅ Mar 08 (57a972af) — `docs/project-notes/POWER_BUDGET_ANALYSIS.md`. J3 dominates at 84W mean (70% arm draw). Total system ~813W (DC compressor) or ~463W (AC). Need 60-80 Ah at 48V for 4hr. **⚠️ Note:** analysis is parameterized — GAP-PWR-001/002/003 (battery type, capacity, voltage) remain OPEN. Actual battery specs needed to finalize runtime estimate. |
| U10 | **Pre-failure baseline capture protocol** — define standard pre-test data capture: motor temps at startup, calibration state, system logs snapshot, battery voltage, CAN bus health. Apply at start of every test session. | Udayakumar | Mar 12 | MEDIUM | ✅ Mar 06 — covered by existing infrastructure: `boot_timing_capture.sh` (OS/system state at every boot via systemd), `mg6010_test_node --mode=status` (motor temp/voltage/errors), `odrive_can_tool --checks` (ODrive state), `ip -s link show can0` (CAN health). Pre-session checklist added to FIELD_TRIAL_CHEATSHEET.md. No new script needed. |
| U11 | **Emergency procedures documentation** — written recovery steps for: motor failure, CAN bus-off, RPi crash, ODrive stall, E-stop recovery, battery low. Print and bring to field. | Udayakumar | Mar 20 | HIGH | ✅ Mar 08 (57a972af) — `docs/EMERGENCY_PROCEDURES.md`. 910-line printable document: 15 sections + 2 appendices, E-stop quick reference, recovery procedures, pre-flight checklist. |
| U12 | **Launch/boot time optimization** — profile and reduce node startup time. Slow boot causes long wait times at field when restarting after crash, config change, or quick check. Benchmark current launch time, identify bottlenecks, optimize. Related: launch-system-hardening OpenSpec change. | Udayakumar | Mar 20 | HIGH | ✅ Mar 05 (2feae6d2) |

### 3.2 Coordination & Review

| # | Task | Owner | Deadline | Priority | Status |
|---|------|-------|----------|----------|--------|
| U3 | **Weekly progress tracking** — track all arm/vehicle/mechanical tasks against deadlines. Unblock teams. Escalate risks. | Udayakumar | Ongoing | HIGH | 🔧 Active — weekly reviews happening |
| U4 | **Code review** — review Shwetha/Gokul/Vasanth code changes before deployment | Udayakumar | Ongoing | HIGH | 🔧 Active — systematic review of all changes before deployment |
| U5 | **Absence coverage (Mar 13-14, 16)** — cover Gokul/Shwetha tasks during AI training/hackathon absence. Integration testing, unblocking mechanical/vehicle teams. | Udayakumar | Mar 17 | HIGH | ✅ Done — Mar 13-14 covered, Mar 16 integration test attempted (CAN failures blocked all operation; see MARCH_16_ANALYSIS_REPORT.md) |
| U6 | **Go/No-Go decision facilitation** — prepare data and lead each Go/No-Go decision (Mar 06, 12, 18, 24) | Udayakumar | Mar 24 | HIGH | 🔧 3/4 done — Decision 1 (Mar 06, NO-GO YOLOX), Decision 3 (Mar 12, GO — both arms ready), Decision 4 (Mar 24, CONDITIONAL GO — see Section 4B). Decision 2 (Mar 18) skipped. |
| U7 | **Field trial logistics coordination** — coordinate with Amirtha on field site, with Dhinesh on vehicle prep, ensure checklist items are packed | Udayakumar | Mar 24 | MEDIUM | 🔧 Well underway — field site coordination with Amirtha active, vehicle prep with Dhinesh in progress |

---

## Section 4: Carried Forward from February 2026

Issues from the February 2026 field trial report (`FIELD_VISIT_REPORT_FEB_2026.md`) not explicitly covered by the tasks above. These are tracked for awareness and should be verified as resolved or deferred before the March trial.

### 4.1 Arm Issues — Resolved by yanthra-safety-and-resilience Change

These issues were fixed by the archived `yanthra-safety-and-resilience` OpenSpec change (Mar 02, 2026):

| Issue | Feb Report Ref | Resolution |
|-------|---------------|------------|
| EE runaway (ran continuously) | S6, 5.1 | ✅ EE watchdog timer in background executor (600s default timeout) |
| Consecutive failure chains (104 events) | 5.5 | ✅ Per-joint failure counters + escalation ladder + safe mode |
| Service discovery timeouts (126) | 5.5 | ✅ Resolved — pre-call readiness check, configurable timeout, periodic health probing. No issues observed in February field trial. |
| ARM_client ROS2 crashes (4 rcl context errors) | 5.5 | ✅ Resolved — crash-safe cleanup, signal handlers. No crashes observed in February field trial (only 4 rare rcl context errors, non-impacting). |

### 4.2 Arm Issues — Lower Priority / Deferred

| Issue | Feb Report Ref | Priority | Notes |
|-------|---------------|----------|-------|
| Model file yolov112.blob not found on RPi | 5.4 | LOW | CMake install rule exists; deployment step issue. YOLOX migration (A6) supersedes this. |
| ARM_client memory growth (73→77MB) | 5.5 | LOW | Minor growth over session. Monitor but no action needed. |
| CAN interface setup error on launch | 5.5 | LOW | `RTNETLINK answers: Operation not supported` — non-blocking, CAN already up. |
| J4 current spikes (32 events) | 5.5 | LOW | May indicate intermittent binding. Monitor during March benchmarking (A11). |
| Network monitor empty (no data rows) | 5.5 | LOW | Monitor running but not collecting data. Fix in field_trial_logging.sh. |
| Border-filtered detections increase (57→453) | 2.6 | LOW | 5.3% rate. May improve with YOLOX model. |
| Arm targeting leaves instead of cotton | S3, 5.2 | MEDIUM | Depth ambiguity between leaves and bolls. Partially addressed by YOLOX model + depth improvements (A7). |

### 4.3 Vehicle Issues — Lower Priority / Deferred

| Issue | Feb Report Ref | Priority | Notes |
|-------|---------------|----------|-------|
| Vehicle movement jerky/uneven | V2, 5.3 | MEDIUM | May improve with ODrive PID tuning (V1). Monitor in March. |
| Provision failures (11/12 vehicle, 8/9 arm) | 5.2 | LOW | Primary cause was RTC clock drift. Extensive provisioning fixes deployed since Feb (12+ commits). Verify during March prep. |
| 72 log gaps >30s (largest 465s) | 1.3 | LOW | Logging gaps during vehicle operation. Should improve with V10 (improved logging). |
| Steering current spikes | 1.4 | MEDIUM | ✅ Mitigated by motor-control-hardening (timeout-stop + command dedup). Hardware cooling still recommended. |

---

## Section 4A: March 16 Integration Test Results

> **Full analysis:** `docs/project-notes/MARCH_16_ANALYSIS_REPORT.md`

**Date:** March 16, 2026 | **Setup:** 3 RPis (arm_1, arm_2, vehicle) | **Result:** 0 picks — CAN failures

### What Happened

The March 16 test was a hardware bring-up / integration test, NOT a picking trial. All 3 RPis
failed at CAN initialization, preventing any motor operation. The team spent 5.5 hours (~28
restart sessions) debugging hardware connectivity without achieving a single pick.

### CAN Failures (Per RPi)

| RPi | CAN HAT | CAN Bus | Motor Response | Camera | Root Cause |
|-----|---------|---------|---------------|--------|------------|
| Vehicle | NOT DETECTED | No can0 | N/A | N/A | Missing device tree overlay or HAT not connected |
| Arm_1 | OK (MCP2515) | Up, 0 RX/TX | None | OK (74.2C) | Wiring, motor power, or termination issue |
| Arm_2 | NOT DETECTED | No can0 | N/A | NOT DETECTED | No CAN HAT + USB camera failure |

### Impact on March 25 Preparation

- **All 108 software fixes remain untested in field** — cannot claim any Feb issue is field-validated
- **Pre-flight hardware check is now CRITICAL** — added as task V20
- **Vehicle binary was 116.9 hours stale** — deploy step missed, need binary freshness check
- **MQTT improved** — 99.5% uptime (vs 97.7% in Feb), only positive field validation from Mar 16

### New Issues Identified

1. Newer code may FATAL-exit on CAN failure instead of degrading — possible regression from stricter init
2. Camera thermal higher (74.2C vs 63C Feb) — monitor
3. Arm_2 had 846 cascading service failures — no circuit breaker for retry storms
4. Model file (yolov112.blob) still not deployed to RPis

---

## Section 4B: March 24 Pre-Field Test Results (Last Session Only)

> **Log location:** `collected_logs/2026-03-24/machine-1/`
> **Note:** Analysis uses ONLY the final session for each arm (earlier sessions were setup/testing).

**Date:** March 24, 2026
**ARM1 last session:** 15:39–16:40 IST (~1 hour, 43 START_SWITCH triggers)
**ARM2 last session:** 13:47–~17:35 IST (~3 hours, 82 START_SWITCH triggers)
**Setup:** 2 arms + vehicle, MQTT start_switch triggered from vehicle start button

### Pick Performance Summary (Last Session)

| Metric | ARM1 | ARM2 | Combined |
|--------|------|------|----------|
| Total pick events | 127 | 145 | **272** |
| Successes | 40 | 47 | **87** |
| Failures | 87 | 98 | **185** |
| Success rate | 31.5% | 32.4% | **32.0%** |
| Avg pick cycle (success) | 5,717ms | 6,435ms | ~6,100ms |
| Pick cycle range (success) | 3,918–7,078ms | 5,020–7,467ms | — |

**vs Feb baseline:** 26.7% → **32.0%** (+5.3%). Target 60% NOT met. Pick cycle time flat at ~6.1s (Feb was ~6.4s). Target 2,000ms NOT met.

### Per-Joint Timing Breakdown (Successful Picks)

| Phase | ARM1 avg | ARM2 avg |
|-------|----------|----------|
| Approach total | 2,825ms | 3,193ms |
| — J3 | 727ms | 807ms |
| — J4 | 569ms | 691ms |
| — J5 | 200ms | 200ms |
| Retreat total | 2,891ms | 3,240ms |

J5 is constant 200ms (hardcoded sleep). J3 and J4 are the main variables. ARM2 is ~400ms slower overall than ARM1.

### Failure Analysis — COLLISION_BLOCKED Dominates

| Failure Reason | ARM1 | ARM2 | Total | % of failures |
|---------------|------|------|-------|---------------|
| COLLISION_BLOCKED | 83 | 79 | **162** | **87.6%** |
| OUT_OF_REACH | 3 | 17 | 20 | 10.8% |
| JOINT_LIMIT_EXCEEDED | 1 | 2 | 3 | 1.6% |

**Position analysis:**
- COLLISION_BLOCKED avg x: ARM1=0.539m, ARM2=0.545m (range 0.480–0.598m)
- OK (successful) avg x: ARM1=0.429m, ARM2=0.459m (range 0.262–0.549m)
- **Arm reach boundary is ~0.48m.** Cotton detected beyond that consistently fails.
- **Primary mitigation for field: position vehicle closer to cotton row.**

### What Worked Well

- ✅ **MQTT start_switch from vehicle → both arms** — confirmed working (43 + 82 triggers)
- ✅ **Two-arm independent operation** — no inter-arm collisions observed
- ✅ **Zero process deaths in last session** — both arms ran stably (note: earlier ARM1 sessions had crashes)
- ✅ **Motor position feedback** — all joints report feedback_ok=true, zero position errors
- ✅ **Eject sequence working** — M2 reverse + forward flush completing consistently
- ✅ **All JSON instrumentation working** — j3_ms/j4_ms/j5_ms populated (was 0 in Feb), polar coords, plan_status, retreat sub-timing all present

### Issues Found

**GAP-MAR24-1: COLLISION_BLOCKED (87.6% of failures) — CRITICAL**
Cotton at x > 0.48m consistently unreachable. For field: position vehicle closer. Verify arm reach vs URDF. May need to relax collision avoidance params.

**GAP-MAR24-2: MQTT disconnects — MEDIUM**
ARM1: 13 disconnects, 1 reconnect, 25 silence watchdog events, 1 seq gap.
ARM2: 12 disconnects, 1 reconnect, 64 silence watchdog events, 1 seq gap.
Silence watchdog fires during idle (between START_SWITCH triggers) — not during picking. Functional impact low.

**GAP-MAR24-3: Stale detections — MEDIUM**
17 (arm1) + 16 (arm2) stale detection warnings. Detection ages up to ~5.8s (threshold 2,000ms). Expected when pick cycle itself takes ~6s — detection goes stale during pick execution.

**GAP-MAR24-4: Detection timeouts — MEDIUM**
4 (arm1) + 5 (arm2) detection timeouts. Small count relative to 272 picks.

**GAP-MAR24-5: ARM2 camera degraded event — LOW**
1 event: "Camera degraded - 3 consecutive RGB timeouts, forcing reconnection." Camera recovered automatically. Monitor at field.

### Vehicle Evening Session (Manually Collected Logs)

> **Log location:** `collected_logs/2026-03-24/machine-1/testing_log/testing_log/evening/`
> **Note:** Vehicle RPi clock is ~2 days behind (shows Mar 22). Provision/RTC sync was NOT done. Uptime: ~1h29m.

**Vehicle health at session end:**
- Steering: all 3 motors 100% health, err_flags=0, temps 42–55°C
- Drive: ~548m total distance driven (all 3 wheels)
- MQTT: 0 reconnects, 5,301s continuous connection, 35 start button presses sent

**Vehicle issues:**

| Issue | Count | Severity | Detail |
|-------|-------|----------|--------|
| ODrive errors (0x04000000) | 50 | HIGH | Current limit or related — all 3 drive motors, 24 ERROR_STATE transitions, auto-recovered via CLEAR_ERRORS |
| ODrive errors (0x00001000) | 32 | HIGH | Encoder or motor error — drive_front most affected |
| CPU thermal CRITICAL (>80°C) | 30 | HIGH | Peak 83.8°C — RPi likely thermal throttling. Needs cooling at field. |
| Steering CAN ABSENT | 151 | MEDIUM | Intermittent CAN failures (left=57, right=51, front=43). Recovered via backoff. |
| Drive stop timeouts | 9 | MEDIUM | Stop command didn’t reach ODrive in time when joystick released |
| Vehicle clock not synced | 1 | HIGH | RPi date is Mar 22 instead of Mar 24. Must sync before field trial. |

### Field Trial Recommendations (for Mar 25)

1. **Position vehicle as close to cotton row as possible** — reduces COLLISION_BLOCKED (biggest impact, no code change needed)
2. **Sync vehicle RPi clock** before test — current clock is 2 days off, will break log correlation
3. **Add cooling for vehicle RPi** — CPU hit 83.8°C, likely thermal throttling. Fan or heat sink.
4. **Investigate ODrive error 0x04000000** — 82 errors across all drive motors. Check ODrive firmware config and current limits.
5. **Tune stereo depth params at field** (Shwetha/Arun) — 5 configurable params ready
6. **Run pre-flight hardware validation (V20)** before first test session
7. **Collect and verify logs from ALL RPis** including vehicle (auto-collect was broken, had to copy manually)
8. **Monitor MQTT reconnects** — if downtime > 30s, restart arm_client manually

---

## Section 5: March 25 Field Trial Results

> **Full report:** [FIELD_TRIAL_REPORT_MAR25_2026.md](FIELD_TRIAL_REPORT_MAR25_2026.md)

### Outcome vs Targets

| Metric | Target | Actual | Result |
|--------|--------|--------|--------|
| Pick success rate | >60% | **52.9%** | CLOSE — missed by 7.1pp |
| Detection accuracy | 90-95% | Not directly measured | UNCLEAR — model trade-off complicated measurement |
| Pick cycle time | <2,000ms | ~1,800ms avg | MET |
| Workspace violations | <30% | **46.2%** | MISSED — still #1 bottleneck |
| Arms operational | 2 | **2** | MET — first dual-arm field trial |
| Zero spatial coordinates | <5% | **~15-20%** | MISSED — hardware limitation, but filtering 100% effective |
| Wasted detection rate | <40% | **48.9-57.3%** | MISSED — model-dependent |

### Key Achievements
1. Pick success rate nearly doubled from 26.7% (Feb) to 52.9% (+26.2pp)
2. Vehicle: 0 crashes (was 9 in Feb)
3. Two-arm operation validated for first time
4. Provisioning: all checks passing (was failing 8-11/12 in Feb)
5. Zero-coordinate filtering: 100% effective (was leaking 237 events in Feb)
6. MQTT uptime: ~98.0% (5 disconnects; improved from 97.7%)

### Critical Issues Discovered
1. **Workspace reachability** — 46.2% of picks fail at planning. COLLISION_BLOCKED at x>0.49m = 73.1% of failures. When reachable: 98.4% success.
2. **Front wheel encoder zero shift** — MG6010 absolute encoder latched ~90° offset. 42 stalls, 80°C thermal. No software detection. Power cycle fixed it.
3. **Detection model trade-off** — v11 filters shells but misses cotton in field lighting. v5 detects more but includes empty shells.
4. **Border filter explosion** — 5.3% (Feb) → 12-52% (Mar). J4 7-pos partially recovers. +150mm position nearly useless (7-11% yield).
5. **J4 action rejections** — 89 failures with feedback_samples=0, self-recovering.

### Items Carried Forward to April
See [APRIL_FIELD_TRIAL_PLAN_2026.md](APRIL_FIELD_TRIAL_PLAN_2026.md) for the complete April plan. Items carried:
- A2: L3 offset correction (camera pitch verification)
- A4: L5 depth control investigation
- A27/A29/A30: Workspace analysis (merged into April A4: reachability investigation)
- V12: E-stop field validation (software works but untested in field)
- V16: ODrive drive motor temperature monitoring
- Plus 17 new items from March 25 findings (see April plan)

---

## Section 6: Testing Phases

### Phase 1: Component Testing (Mar 03 - Mar 10)

**Goal:** Individual subsystem verification and benchmarking.

| Task | Owner | Criteria | Status |
|------|-------|----------|--------|
| L3 tuning on standalone arm | Gokul | Position accuracy within spec | ⬜ |
| YOLOX vs YOLOv11 comparison document | Shwetha / Arun | Analysis document ready for review | ✅ Mar 04 |
| EE motor tests (0.5s on/off cycle) | Joel / Dhinesh | Motor behavior validated | ⬜ |
| ODrive bench testing with new PID params | Gokul | No stall loop in bench test | ⬜ |
| IP address scheme finalized | Gokul | All RPi IPs assigned | ⬜ |
| Standalone arm available for software testing | Dhinesh | Arm #3 operational | ⬜ |
| Standalone arm available for EE/Mech testing | Dhinesh | Arm #4 operational | ⬜ |
| Standalone arm available for Zoho team | Dhinesh | Arm #5 delivered | ⬜ |
| New field site identified | Amirtha | Location confirmed | ✅ Mar 05 |
| Encoder configuration verified | Gokul | A&B channels confirmed | ⬜ |
| Software hardening (U1) | Udayakumar | All hardening changes archived | ✅ Mar 15 (12/12 — includes phase-1-critical-fixes f1685f2c + phase-2-critical-fixes d3e0885c + motor-control-hardening 35ab4be22 + detection-zero-spatial-diagnostics e0b006d56) |
| Test infrastructure (U8) | Udayakumar | Test framework operational | ✅ Mar 15 (~2,129 tests — 107 added by motor-control-hardening, detection-zero-spatial-diagnostics, stereo depth param configurability, field-trial-logging-gaps) |
| Dashboard overhaul | Udayakumar | Dashboard restructured and usable | ✅ Mar 08–10 (26 dashboard changes archived, including full entity-centric redesign: entity-core 67/67, operations 25/25, ros2-subtabs 56/56, motor-rosbag 38/38) |

### Phase 2: Lab Integration (Mar 10 - Mar 18)

**Goal:** Subsystems integrated and tested together in lab.

| Task | Owner | Criteria | Status |
|------|-------|----------|--------|
| L3 offset correction applied and verified | Shwetha | Arm reaches correct positions | ⬜ |
| YOLOX 3-class model trained and deployed | Shwetha / Arun | 90-95% detection accuracy on test set | 🚫 PARKED — staying with YOLOv11 |
| 0,0,0 detection rate reduced | Shwetha / Arun | <5% on lab test | 🔧 Diagnostics deployed (bbox logging + image annotations). 5 stereo depth params configurable. Field tuning needed. |
| Two arms mounted on vehicle | Dhinesh | Both arms operational | ✅ Mar 12 |
| Arm spacing and clearance verified on vehicle | Dhinesh / Amirtha | No range-of-motion overlap | ⬜ |
| Three-wheel steering integrated | Vasanth / Arvind | Steering responds correctly | ⬜ |
| IMU + RTK GPS data flowing | Vasanth / Arvind | ROS2 topics publishing data | ⬜ |
| All benchmarks completed (A9-A13) | Various | Reports ready | 🔧 A12 ✅, A13 ✅ (resolved from Feb log analysis Mar 17). A9-A11 baselines extracted, need March data for comparison. |
| Collection box redesign/betterment installed | Amirtha | Box stable, no swinging | 🔧 Partial — height adjustments |
| EE replacement motor decision | Joel / Dhinesh | Motor selected or current motor confirmed | ⬜ |
| E-stop and sequential power-up tested | Rajesh / Gokul | Safe startup sequence verified | 🔧 E-stop hardware done (vehicle motors only). Sequential power-up PARKED. |
| Steering error code 8 resolved | Udayakumar | No error code 8 in lab test | ✅ Mar 15 — Init sequence fix in motor-control-hardening (e29d5be67). Needs lab verification. |
| Instrumentation fixes deployed (A22-A25) | Udayakumar | JSON timing, capture_ms populated | A22 ✅, A23 ✅, A25 ✅ (field-trial-logging-gaps b65e189bc); A24 ⬜ |
| Improved vehicle logging deployed | Gokul | Structured JSON logs from vehicle nodes | ⬜ |

### Phase 3: Pre-Field Validation (Mar 18 - Mar 24)

**Goal:** Full system validation, field readiness checks.

| Task | Owner | Criteria | Status |
|------|-------|----------|--------|
| Full 2-arm pick cycle test (>100 cycles) | All | Both arms complete cycles without collision | ✅ Mar 24 — last session: 272 pick events (87 success, 185 fail). Both arms ran independently, no inter-arm collision. See Section 4B. |
| Detection accuracy benchmark in lab conditions | Shwetha / Arun | >90% accuracy documented | ⬜ |
| Vehicle drive + steering integrated test | Gokul / Vasanth | Smooth motion, no stalls in 30-min test | ⬜ |
| Drop/throw trajectory validated | Gokul / Shwetha | >80% cotton lands in collection box | ⬜ |
| Pre-field mechanical checklist (belts, home positions, box clearance) | Dhinesh | All items pass | ⬜ |
| Cross-compile and deploy to all RPis | All | Clean build, all nodes launch | ⬜ |
| Field site walkthrough and measurement | Amirtha | Row spacing, plant height recorded | ⬜ |
| RTC sync or hardware RTC installed | Gokul | Clock drift <1 minute over 4 hours | ⬜ |
| Provision verification on all RPis | Gokul | All steps pass, including offline test (internet disconnected) | ⬜ |
| ODrive slope/terrain test | Gokul | Vehicle holds position on ramp, drives up/down without stall | ⬜ |
| DDS discovery 3-node test (30 min) | Gokul | Zero discovery timeouts across 3 RPis | ✅ Mar 06 |
| System-level workspace analysis complete | Shwetha / Amirtha | Predicted workspace coverage >70% at new field site | ⬜ |
| Power budget documented | Udayakumar | Per-subsystem power draw measured, battery endurance estimated | ✅ Mar 08 (57a972af) |
| Pre-failure baseline protocol tested | Udayakumar | Protocol executed on all RPis, data captured correctly | ✅ Mar 06 |
| Offline provision test (internet disconnected) | Gokul | All provision steps pass without internet | ⬜ |

### Phase 4: Field Trial (Mar 25, 2026)

**Goal:** Two-arm single-row cotton picking operation.

| Task | Owner | Criteria |
|------|-------|----------|
| Pre-flight hardware validation on all RPis (V20) | Gokul / Udayakumar | CAN, camera, motors, network, binary freshness all PASS |
| Pre-test mechanical checklist at field | Dhinesh | All items pass |
| Pre-test connectivity check (all RPis, MQTT, ROS2) | Gokul / Vasanth | All nodes communicating |
| Field trial execution — single row, two arms | All | Minimum 2 hours of operation |
| Post-trial log collection from all RPis | Gokul | All logs collected |
| Post-trial debrief and observation recording | All | Notes captured |
| Pre-failure baseline captured | Udayakumar | Startup state recorded before first test run |
| Emergency procedures printed and distributed | Udayakumar | All team members have recovery steps | 🔧 Document ready (docs/EMERGENCY_PROCEDURES.md); print before Mar 25 |

---

## Section 7: Go/No-Go Decision Points

### Decision 1: Model Migration (March 06)

**Question:** Proceed with YOLOX migration or stay with YOLOv11?

**Findings (as of Mar 05):**
- `YoloSpatialDetectionNetwork` does NOT work with YOLOX — output tensor format is incompatible (Shwetha verified)
- `NeuralNetwork + SpatialLocationCalculator` WORKS — tested by Shwetha/Arun with custom YOLOX model at both 640x640 (50 epochs) and 416x416 (production size), host-side NMS < 1 ms
- Architecture: VPU runs inference → host does NMS (< 1 ms) → boxes sent back to VPU for depth via SpatialLocationCalculator
- Udayakumar investigating whether `YoloSpatialDetectionNetwork` can be made to work (output format adaptation)

Checklist:
- [x] YOLOX vs YOLOv11 comparison document completed (A5) — ✅ Mar 04
- [x] Licensing analysis confirms YOLOX is suitable for commercial use — Apache 2.0
- [ ] YOLOX accuracy >= YOLOv11 accuracy on existing test set — NOT YET TESTED
- [ ] YOLOX latency on RPi is acceptable (<100ms inference) — NOT YET MEASURED
- [ ] Sun glare class data collection plan is feasible by Mar 18 — NOT YET ASSESSED

**Status (Mar 14):** NO-GO — YOLOX parked for March trial. Staying with YOLOv11. YOLOX pipeline validated (NeuralNetwork + SpatialLocationCalculator works) but accuracy/timing unproven on field hardware. YOLOv11 is proven (26.7% pick rate in Feb). YOLOX remains viable for post-trial migration.

**If NO:** Stay with YOLOv11, add sun glare as 3rd class to existing model.
**If YES:** Proceed with YOLOX migration (A6).

### Decision 2: Vehicle Go/No-Go (March 18)

**Question:** Is the vehicle reliable enough for 2-arm field trial?

Checklist:
- [x] ODrive stall loop resolved (V1, V2) — 30-min bench test with no stalls (V2 ✅ Mar 05)
- [ ] Three-wheel steering functional (V5) — all 3 steering motors responding
- [x] Steering error code 8 resolved or mitigated (V6) — init sequence fix in motor-control-hardening (Mar 15)
- [ ] E-stop functional (V12)
- [ ] Sequential power-up verified (V13)
- [ ] Vehicle drives smoothly for 10 minutes in lab

**If NO:** BLOCKER — resolve all failing items before proceeding. Vehicle is mandatory for March trial. Do not proceed until all checklist items pass.
**If YES:** Vehicle confirmed ready. Proceed to two-arm integration.

### Decision 3: Two-Arm Go/No-Go (March 12)

**Question:** Are both arms mechanically ready for field trial?

**⚠️ AT RISK (Mar 09):** Decision date is March 12. Related tasks with Mar 12 deadlines (A1, V1, ~~A12, A13~~, V12, V14, A21) show limited progress. V6/V7 software mitigations completed Mar 15 (motor-control-hardening). A12/A13 resolved Mar 17 from Feb log analysis. These are primarily hardware/lab tasks — software commits are not expected, but the plan should be updated with physical progress status before the decision date. The mounting deadline (A21, Mar 17) falls *after* this decision, creating a 5-day gap.

**Status (Mar 14):** GO — Both arms mounted on vehicle. Metal gears for pick roller, 3D printed plastic gears for collection (M2) roller. Collision analysis done (overlap at 0.25m). Global J5 limit approach under discussion.

Checklist:
- [x] Both arms mounted on vehicle (Dhinesh)
- [ ] Physical arm spacing verified — no range-of-motion overlap
- [ ] Both arms complete home sequence on vehicle
- [ ] Collection box clearance verified on both sides
- [ ] L3 offset corrected and verified (A1, A2)

**If NO:** BLOCKER — resolve all failing items. Two-arm operation is mandatory for March trial. Do not proceed until both arms pass all checklist items.
**If YES:** Both arms confirmed ready. Proceed to final readiness check.

### Decision 4: Final Field Readiness (March 24)

**Question:** Ready for field trial tomorrow?

**Status (Mar 24): CONDITIONAL GO** — Both arms and vehicle MQTT trigger validated in pre-field test (last session: 272 picks, 32.0% success rate). Proceed with field trial. Key action for field: **position vehicle closer to cotton row** to reduce COLLISION_BLOCKED failures (87.6% of all failures happen when cotton is at x > 0.48m).

Checklist:
- [ ] New field site confirmed and accessible (Amirtha)
- [ ] All RPis provisioned and clock-synced
- [ ] Cross-compiled binaries deployed to all RPis
- [ ] **Pre-flight hardware validation passes on all RPis (V20)** — CAN, camera, motors, network
- [ ] Pre-field mechanical checklist passed (Dhinesh)
- [ ] Vehicle drives and steers in parking lot test
- [x] Both arms complete pick cycles in parking lot test — ✅ Mar 24 (last session: 272 picks, 87 success)
- [x] Log collection verified from all RPis — ✅ Mar 24 (logs collected from both arms)
- [ ] Emergency motor stop script tested
- [ ] Spare parts packed (belts, connectors, tools)
- [ ] Battery fully charged

**If NO:** BLOCKER — resolve all failing items. Identify specific blockers and fix timeline. Postpone only if blockers cannot be resolved within 48 hours.
**If YES:** Proceed to field.

**Outcome (Mar 25):** CONDITIONAL GO decision was correct. Trial proceeded successfully with major improvements over February. See Section 5 for full results.

---

## Section 8: Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| New field site not found in time | Medium | HIGH | Start search immediately (Amirtha). Field site is mandatory — escalate if not identified by Mar 10. |
| YOLOX migration takes longer than expected | Medium | HIGH | Keep YOLOv11 as fallback. Model migration decision on Mar 06. |
| ODrive stalls persist after PID tuning | High | HIGH | Fallback to stop-and-pick mode. Investigate ODrive firmware settings. |
| Arm2 hardware issues (like arm2 in Feb) | Medium | HIGH | Test both arms in lab by Mar 18. Fallback to single-arm trial. |
| Collision avoidance software not ready | Medium | MEDIUM | Run arms in alternating mode (one picks while other waits). |
| Two dense rows affect vehicle/arm movement | Medium | MEDIUM | Verify row spacing at new field site >3 feet. |
| Belt breakage recurrence | Low | HIGH | Pre-test mechanical checklist. Carry spare belts. |
| EE motor failure | Medium | MEDIUM | Joel / Dhinesh testing replacement motors (A15). Carry spare EE assembly. |
| RTK GPS not ready in time | Medium | LOW | GPS is first-version data collection only. Trial proceeds without it. |
| Rain/weather on trial day | Low | HIGH | Monitor forecast. Identify backup date (Mar 26-28). |
| Power budget insufficient for 2-arm operation | Medium | HIGH | Power budget analysis (U9) by Mar 18. If insufficient, reduce to single-arm or bring generator. |
| DDS discovery failures with 3 nodes | **Low** | MEDIUM | **Mitigated (V19 PASS, Mar 6).** 30-min test: shared-domain discovery 30/30 OK, production isolation 30/30 OK. Fallback: restart nodes, use dedicated network. |
| Workspace violations persist after J3 fix | Medium | HIGH | System-level workspace analysis (A27) predicts coverage. If <60%, adjust vehicle positioning strategy. |

---

## Section 9: Logistics

### Equipment Checklist

- [ ] Vehicle with 2 arms mounted
- [ ] 3 RPi 4B units (1 vehicle + 2 arm) with power supplies
- [ ] 2 OAK-D Lite cameras (tested)
- [ ] Laptop for monitoring/SSH
- [ ] Ethernet cables and switch/router
- [ ] Fully charged batteries (+ spare if available)
- [ ] Spare belts for J5
- [ ] Spare EE motor assembly
- [ ] Basic tools (screwdrivers, Allen keys, zip ties)
- [ ] Multimeter
- [ ] Field trial logging script verified
- [ ] Emergency motor stop script on all RPis
- [ ] Drinking water, sun protection for team
- [ ] Printed documentation: trial plan, ~~emergency procedures~~ ✅ ready (`docs/EMERGENCY_PROCEDURES.md`), motor protection guide, ROS2 quick reference

### Team Roles at Field

| Role | Person |
|------|--------|
| Overall coordination / execution | Udayakumar |
| Project owner | Manohar |
| Arm mechanical | Dhinesh |
| Arm electronics | Gokul / Joel |
| Arm electrical | Rajesh |
| Arm software / detection | Shwetha / Arun |
| Vehicle | Gokul / Vasanth |
| Autonomous nav / sensors | Arvind |
| Field site / collection | Amirtha |
| Dynamic picking (observer) | Navneeth |
| Observation and documentation | All |

### Post-Trial Data Collection

- [ ] Collect logs from all RPis (`sync.sh --collect-logs`)
- [ ] Copy detection images from both arm RPis
- [ ] Record field conditions (row spacing, plant height, weather, temperature)
- [ ] Team debrief notes (all observations captured)
- [ ] Photograph any mechanical damage or issues
- [ ] Run log analyzer on collected data same day

### Post-Trial Data Validation (Before Leaving Field)

- [ ] ROS2 node logs present and non-empty on all RPis
- [ ] ARM_client / MQTT logs present on vehicle RPi
- [ ] Detection images saved on both arm RPis
- [ ] System logs (journalctl) exported from all RPis
- [ ] Temperature logs present
- [ ] Pick performance metrics (JSON events) present and parseable
- [ ] Battery voltage / power data recorded
- [ ] Backup copy of all logs to USB drive or laptop
- [ ] Quick sanity check: open one log file per RPi, verify timestamps match trial window

---

## Appendix A: February 2026 Field Visit Summary

Full details in `docs/project-notes/FIELD_VISIT_REPORT_FEB_2026.md`.

### Key Issues Driving March Plan

| Issue | Feb Impact | March Task |
|-------|-----------|------------|
| J3 offset error (arm below cotton) | 73% workspace violations | A2 (L3 offset correction) |
| L3 not returning home (multi-scan) | Camera FOV blocked, 17% zero coords | A1 (L3 tuning) |
| ODrive stall loop | 9 vehicle crashes, 1,183 errors | V1, V2 (PID + recovery) |
| Steering error code 8 + thermal | All 3 motors degraded | V6 ✅, V7 ✅ (motor-control-hardening: init fix + timeout-stop + dedup) |
| J5 belt broken | EE not extending properly | A17 (mechanical review) |
| Drop/throw inconsistent | Cotton missing collection box | A20 (trajectory tuning) |
| Detection: 17% zero spatial | 503 events vs 3% in January | A7 (0,0,0 fix) |
| Arm2 unavailable | Could not test 2-arm operation | A21 (collision avoidance), hardware prep |
| EE runaway (safety) | Required shutdown topic | ✅ Fixed (yanthra safety change) |
| Small cotton boll failure | Cannot pick undersized bolls | A16 (EE seed jam), benchmarking |
| Collection box swinging + arm stuck in plants | Mechanical interference | A17, A18, A19 |

### What Worked Well in February

- MQTT communication rock solid (97.7% vehicle uptime)
- Multi-position J4 scanning effective
- Detection latency good (34-93ms avg)
- Field trial logging and log collection functional
- Collection system concept validated
- EE picking improved vs January
- Camera FOV improved vs January

---

## Appendix B: February Issue Triage — Resolution Status

During March planning, the February 2026 field report issues were reviewed against existing fixes and the March task list. The following documents the triage outcome for issues that were questioned or investigated.

| # | Issue | Resolution | Detail |
|---|-------|-----------|--------|
| 1 | **EE runaway (ran continuously)** | ✅ Fixed | Watchdog timer in background executor added by yanthra-safety-and-resilience change (Mar 02). 600s default timeout. Background `SingleThreadedExecutor` thread guarantees watchdog fires even when main thread is blocked on motor service calls. |
| 2 | **Service discovery timeouts (126)** | 🟡 Mitigated | Pre-call `service_is_ready()` check, configurable detection service timeout (2s default), periodic health probing every 30s. Root cause (DDS/middleware level) not fixed. Not critical for March. |
| 3 | **rcl context crashes (4)** | 🟡 Partial | Not directly fixed. Indirectly improved by crash-safe cleanup (SIGSEGV/SIGABRT signal handlers, GPIO reset on SIGKILL). Rare occurrence (4 in entire trial). Low priority. |
| 4 | **Consecutive failure chains (104 events)** | ✅ Fixed | Per-joint failure counters + escalation ladder (log → retry with backoff → homing → safe mode). Configurable threshold (default 5 consecutive failures). TOCTOU race fix with `compare_exchange_strong`. |
| 5 | **Model file not found on RPi** | ℹ️ Not a code issue | CMake install rule exists and works (`models/` directory installed to ROS2 share). The "missing on RPi" was a deployment step issue — model not synced during that specific deployment. YOLOX migration (A6) supersedes this model entirely. |
| 6 | **ARM_client memory growth (73→77MB)** | ℹ️ Not addressed | Minor growth (4MB over full session). ARM_client is Python MQTT bridge, outside scope of yanthra C++ changes. Monitor but no action needed for March. |
| 7 | **Provision failures (11/12 vehicle, 8/9 arm)** | ✅ Fixed | Primary cause: no battery-backed RTC on RPi 4B → clock drift → cascading apt/SSL/systemd failures. 12+ commits between Feb 18-24 fixed: clock sync from dev machine added to provision flow, `pigpiod_custom.service` naming corrected, `can_watchdog.sh` copy added, heredoc/TTY race conditions resolved, ROS_DOMAIN_ID mismatch fixed. Vehicle has 12 provision steps vs arm's 9, explaining the different failure counts. |
| 8 | **L5 home offset + depth control** | 🔄 Needs investigation | L5 home offset likely caused by J5 belt breakage (now repaired). L5 depth control issue (going too deep) needs investigation: is the error in cotton detection depth estimation or in yanthra_move's depth-to-L5-travel calculation? Added as task A4. |

---

## Appendix C: Reference Documents

| Document | Location |
|----------|----------|
| March 16 Integration Test Analysis | `docs/project-notes/MARCH_16_ANALYSIS_REPORT.md` |
| February Field Visit Report | `docs/project-notes/FIELD_VISIT_REPORT_FEB_2026.md` |
| February Field Trial Plan | `docs/project-notes/FEBRUARY_FIELD_TRIAL_PLAN_2026.md` |
| January Field Trial Plan | `docs/project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md` |
| Gap Tracking | `docs/specifications/GAP_TRACKING.md` |
| Validation Matrix | `docs/specifications/VALIDATION_MATRIX.md` |
| Product Requirements | `docs/specifications/PRODUCT_REQUIREMENTS_DOCUMENT.md` |
| Technical Specification | `docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md` |
| Field Trial Cheatsheet | `docs/FIELD_TRIAL_CHEATSHEET.md` |
| March 25 Field Trial Report | [FIELD_TRIAL_REPORT_MAR25_2026.md](FIELD_TRIAL_REPORT_MAR25_2026.md) — Comprehensive March 25 field trial report |
| April Field Trial Plan | [APRIL_FIELD_TRIAL_PLAN_2026.md](APRIL_FIELD_TRIAL_PLAN_2026.md) — April field trial plan (carry-forward from March) |

---

**Report Created:** March 03, 2026
**Last Updated:** March 25, 2026
**Author:** Udayakumar
**Review Status:** Post-trial closure. Field trial completed March 25. See Section 5 for results. Items carried forward to April plan.
