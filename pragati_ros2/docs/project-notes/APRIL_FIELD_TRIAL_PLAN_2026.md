# April Field Trial Plan (2026)

**Target Date:** TBD April 2026 (pending team review of March 25 findings)
**Prep Deadline:** TBD (1 week before trial date)
**Created:** March 25, 2026
**Last Updated:** March 26, 2026 (log audit: V13-V15, A29-A30, S17-S20, R11-R14 added)
**Project Owner:** Manohar
**Execution Lead:** Udayakumar
**Scope:** 2 arms + vehicle, single row of cotton plants
**Focus:** Improve pick success rate past 70% by addressing reachability, detection model, and motor reliability

---

## Executive Summary

The April 2026 field trial builds on the March 25 trial results (52.9% pick success rate,
46.2% workspace rejections, zero vehicle crashes). March demonstrated a **26.2 percentage point
improvement** in pick success rate over February, validated two-arm operation, and eliminated
vehicle crashes entirely. However, three categories of problems now dominate:

1. **Reachability limits** — COLLISION_BLOCKED accounts for 73.1% of planning failures
   (315/431 events), J4 lateral over-reach for 23.9% (103 events). Log-verified: blocking
   occurs at J3 −34° to −57° (never at J3=0°), arm-frame x-boundary is ~0.55–0.60m.
   Clearance=0.20m is derived from D≈1.02m **estimated, not measured** — measuring actual D
   is the single highest-leverage pre-April action. A 5cm clearance increase (D≈1.10m) would
   unblock 59% of collision-blocked events (186/315). Ref: §17 PICK_REJECTION_BOTTLENECK_ANALYSIS.
2. **Detection model trade-off** — YOLOv11 misses cotton in field lighting; YOLOv5 picks
   shells. Neither model alone is sufficient. A resolved detection model is the highest-impact
   decision for April.
3. **Motor reliability** — Hardware E-stop was activated during the trial; motors were UNAVAILABLE for 30 min in Session 4. E-stop event may relate to encoder zero shift.
   Software detection of drift
   at startup is mandatory before the next trial.

Additionally, border filtering jumped from 5.3% to 23-52%, the +150mm J4 scan position
yields only 7.4-11.7%, and memory leak source identified: `dashboard_server` (uvicorn) at ~22MB/hr. `rpi_agent` has +61.6MB initialization spike. Both arms affected. These are all
addressable with targeted fixes.

### March 25 Baseline Metrics

| Metric | Feb 26 | Mar 25 | Change |
|--------|--------|--------|--------|
| Arms tested | 1 | 2 | +1 arm |
| Total pick attempts | 1,181 | 930 | -21.2% (quality over quantity) |
| Cotton picked | 315 | 492 | +56.2% |
| Pick success rate | 26.7% | 52.9% | +26.2pp |
| Workspace rejections | 73% | 46.2% | -26.8pp |
| Zero spatial coords rate | 17% | ~15-20% (1,024 filtered OK) | Filtering working |
| Vehicle crashes | 9 | 0 (1 E-stop event, Session 4 CAN bus dead) | Eliminated |
| Border filter rate | 5.3% | 23-52% | Much higher (over-aggressive) |
| MQTT uptime | 97.7% | ~98.0% | Improved |
| Pick cycle time (success) | ~6,400ms | ~6,100ms | Marginal improvement |
| CAN RX errors (vehicle) | N/A | 1.59M (~220/sec) | New measurement |
| Stall events (vehicle) | 9 crashes | 42 stalls across 4 sessions (0 crashes, 1 E-stop). Peak currents: front 17.11A, left 12.20A, right 12.94A (threshold 6.40A) | No crashes but stall cascade |

### April 2026 Trial Targets

| Metric | Mar 25 Actual | April Target | Rationale |
|--------|---------------|--------------|-----------|
| Pick success rate | 52.9% | >70% | Reachability improvements on 52.9% base |
| Workspace rejections | 46.2% | <25% | Collision margin tuning + workspace extension |
| Border filter rate | 23-52% | <10% | Reduce margin from 5% to 3%, validate |
| Wasted detection rate | ~45% | <35% | Better model + border filter fix |
| Zero spatial coords | ~15-20% | <15% | Unchanged hardware limit, maintain filtering |
| Vehicle encoder shifts | 1 (front) | 0 | Startup verification catches drift |
| Vehicle stalls | 17 | <5 total | Stall escalation limit (auto-disable after 3) |
| Detection model | v11 (misses) / v5 (shells) | Single resolved model | Either retrained v11 or v5+2class |
| J4 scan positions | 5-pos (S1-4 arm_2) / 7-pos (S2-3 arm_1, S5-6 arm_2) | Committed 7-pos ±150mm/50mm; evaluate removing ±150mm | Both arms ran 7-pos mid-trial, now in production.yaml |
| Pick cycle time (success) | ~6,100ms | <5,000ms | J4 optimization + fewer wasted scans |
| CAN RX errors (vehicle) | ~220/sec | <50/sec | CAN bus investigation + mitigation |

---

## Section 1: Arm Tasks

> **Status:** ⬜ Not started · 🔧 In progress · ✅ Done · ⏸️ Blocked

### 1.1 Critical (Before Next Trial)

These three items are mandatory before any April field trial. Do not schedule a trial date
until all three are resolved or have a verified mitigation.

| # | Task | Owner | Priority | Est. Effort | Status |
|---|------|-------|----------|-------------|--------|
| A1 | **Startup zero-position verification for steering motors** — After homing, check idle current. If >0.5A at "zero", flag ZERO_POSITION_SUSPECT. Command +/-5 degree test movement, verify position delta matches expected. This catches encoder drift before thermal damage. Ref: ENCODER_ZERO_SHIFT_ANALYSIS_2026-03.md | TBD | CRITICAL | 1-2 days | ⬜ |
| A2 | **Stall escalation limit** — After 3 consecutive stalls within 5 minutes on the same motor, auto-disable it and raise MOTOR_DISABLED alarm. Current system allowed 17 stalls + thermal runaway to 80 degrees C before manual intervention. Must apply to all MG6010 and MG6012 motors. Ref: FIELD_TRIAL_REPORT_MAR25_2026.md, Section 4.1 | TBD | CRITICAL | 1 day | ⬜ |
| A3 | **Resolve detection model trade-off** — Current state: YOLOv11 misses cotton in field lighting conditions, YOLOv5 picks shells instead of cotton. Three options under consideration: (A) Retrain v11 with more field lighting data to improve sensitivity, (B) Retrain v5 with 2 classes adding shell class back, (C) Train new model specifically for field conditions. Decision requires team discussion with training data review. Ref: DETECTION_MODEL_TRADEOFF_ANALYSIS_2026-03.md. Fallback: If retraining not complete 1 week before trial, implement confidence gating heuristic on v5 as bridge (see A18). | TBD | CRITICAL | 1-2 weeks | ⬜ |
| A29 | **Re-enable or formally document J3-J4 collision interlock** — disabled on both arms for entire trial. Safety risk for two-arm operation. | TBD | HIGH | 1 day | ⬜ |
| A30 | **Fix J3 position clamping on arm_2** — 278 events where planner commands -0.180 but limit is -0.166. Either widen limit or fix workspace model. | TBD | HIGH | 1 day | ⬜ |

### 1.2 High Priority

| # | Task | Owner | Priority | Est. Effort | Status |
|---|------|-------|----------|-------------|--------|
|| A4 | **Measure base-to-base separation D and recalibrate clearance** — Log analysis (§17 PICK_REJECTION_BOTTLENECK_ANALYSIS) confirmed: 315 COLLISION_BLOCKED events at J3 −34° to −57° (mean −40°), never at J3=0°. Actual arm-frame x-boundary is ~0.55–0.60m, not 0.49m. Current clearance=0.20m is derived from D≈1.02m **estimated** from a single collision observation. Sensitivity: D=1.06m → clearance=0.23m → 36% of blocks removed; D=1.10m → clearance=0.25m → 59% removed. Action: (1) physically measure both arms' base-to-base distance, (2) update `j5_collision_avoidance/clearance` in production.yaml, (3) lab-validate no actual collision at new clearance. Full failure table: `docs/reports/reachability_failure_table_2026-03-25.md`. | TBD | HIGH | 1 day meas. + 1 day lab | ⬜ |
|| A5 | **Evaluate removing ±150mm J4 positions** — Log analysis shows J4 lateral failures (103 events, 24.0% of rejects) are disproportionately from ±150mm scan positions where cotton appears at the image edge and theta > ±0.1715m. Only 7.4–11.7% pick yield at +150mm. Consider capping at ±100mm (6-pos: −100,−67,−33,0,+33,+67,+100 or 5-pos within ±100mm). Note: arm_2 7-pos (±150mm at 50mm increments) is now committed to production.yaml — this task is about whether to shrink the range, not expand. | TBD | HIGH | 0.5 day | ⬜ |
| A6 | **Reduce border filter margin from 5% to 3%** — Border filter rate jumped from 5.3% (Feb) to 12-52% (Mar). Filter is too aggressive — many edge detections have valid depth data. Reducing the margin should recover a significant number of valid detections. Validate that reduced margin does not increase false picks (picks on leaves, stems, or background). Ref: BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md. Prerequisite: Complete A19 (depth quality verification in 3-5% zone) before deploying 3% margin. If depth variance is high in that zone, consider 4% as a safer intermediate step. | TBD | HIGH | 0.5 day | ⬜ |
| A7 | **Investigate J4 action rejection pattern** — 89 failures with feedback_samples=0 suggest timing/state-machine bug in the J4 action server. Not a motor fault — action server rejects before any motion begins. Self-recovering but wastes pick cycles. Root-cause the rejection trigger (race condition in goal acceptance, premature timeout, or state machine transition error). | TBD | HIGH | 1-2 days | ⬜ |
| A8 | **Dynamic picking preparation** — Deferred from March plan (was A26). Review March 25 field data for in-motion picking feasibility. Determine vehicle speed limits for dynamic picking vs. stop-and-pick. Define ROS2 interface between vehicle odometry and arm motion planner. This is exploratory work for future trials, not required for April trial execution. | Navneeth | HIGH | Ongoing | ⬜ |
| A13 | **L3 camera offset correction** — Verify camera pitch angle alignment relative to L3 joint. Camera-workspace mismatch contributes to detection of unreachable cotton. Carried from March A2. | TBD | HIGH | TBD | ⬜ |
| A14 | **L5 depth control investigation** — Investigate L5 end-effector depth accuracy during pick approach. Never started in March cycle. Carried from March A4. | TBD | HIGH | TBD | ⬜ |
|| A15 | ~~**Expand arm_2 to 7-position J4 scan**~~ **✅ DONE (committed to source)** — Log analysis of March 25 sessions proves both arms ran 7-pos (−150,−100,−50,0,+50,+100,+150mm) from mid-trial onward: arm_1 from S2 (13:40), arm_2 from S5 (13:37). The 7-pos config was deployed to RPis mid-trial but never committed back to source. This is now committed in `production.yaml` (joint4_multiposition/positions). Remaining decision: whether to shrink ±150mm range (see A5). Ref: PICK_REJECTION_BOTTLENECK_ANALYSIS_2026-03.md §17. | TBD | HIGH | ~~15 min~~ Done | ✅ |
| A16 | **Model class count startup validation** — Detection node accepts mismatched `classes` parameter without error. v5 with classes=2 silently produced 0 detections for 65s. Add startup check: validate class count matches model output tensor dimensions. Abort with clear error if mismatch. Ref: DETECTION_MODEL_TRADEOFF_ANALYSIS_2026-03.md §9. | TBD | HIGH | 1-2 hours | ⬜ |
| A17 | **Implement checkReachability()** — Function is a placeholder in motor controller. Should pre-check if a target position is reachable before attempting motion planning. Reduces wasted pick cycles. Ref: Retrospective §3.1, §4.4. | TBD | HIGH | 2-3 days | ⬜ |

### 1.3 Medium Priority

| # | Task | Owner | Priority | Est. Effort | Status |
|---|------|-------|----------|-------------|--------|
| A9 | **Detection accuracy benchmark with ground truth** — Carried from March (was A9). Still needed: controlled test with known cotton positions to compute true precision/recall/F1. Field proxy metrics are insufficient. Must include comparison of v11 vs. v5 vs. retrained model. Specific acceptance thresholds from Detection Model RCA §8: detection rate >=20%, wasted detection rate <40%, shell false-positive rate <5%, latency <80ms, confidence >0.65. Retrained model must meet these before deployment. | Shwetha / Arun | MEDIUM | 2-3 days | ⬜ |
| A10 | **Root-cause left-right pick yield asymmetry** — Carried from March (was A10). Feb data showed 4.6x difference at -150mm vs +150mm. March data available to confirm or refute. Determine if mounting asymmetry, J3-related, or camera FOV issue. | Shwetha | MEDIUM | 1-2 days | ⬜ |
| A11 | **Per-joint timing optimization plan** — Carried from March (was A11). March data now has per-joint timing (j3_ms, j4_ms, j5_ms populated). Analyze to identify which phases can be parallelized or shortened to approach the 2-second pick cycle target. J5 is still hardcoded 200ms sleep — verify if this can be reduced with position feedback. | Gokul | MEDIUM | 1-2 days | ⬜ |
| A12 | **EE motor evaluation** — Carried from March (was A14-A16). Confirm replacement motor performance. Validate that roller pin sizing fix prevents seed jamming under sustained operation (100+ picks). | Joel / Dhinesh | MEDIUM | 1-2 days | ⬜ |
| A18 | **Confidence gating heuristic as model fallback** — If A3 retraining not complete 1 week before trial, implement post-detection heuristics on v5 to reject likely shells (confidence threshold, bbox size, depth profile). Bridge solution. Ref: DETECTION_MODEL_TRADEOFF_ANALYSIS_2026-03.md §5.4, Option D. | TBD | MEDIUM | 1-3 days | ⬜ |
| A19 | **Depth quality verification before border margin change** — Before deploying 3% margin (A6), analyze March 25 data to verify depth variance in the 3-5% border zone. If variance is high, 4% may be safer than 3%. Prerequisite for A6 deployment. Ref: BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md §10 Q4. | TBD | MEDIUM | 0.5 day | ⬜ |
| A20 | **Camera-specific border margin calibration** — Per-camera depth reliability measurement instead of global margin. Each OAK-D Lite may have different lens/calibration characteristics. Ref: BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md R4. | TBD | MEDIUM | 1-2 days | ⬜ |
| A21 | **Camera depth sanity check at startup** — Verify depth values are in expected range before picking starts. Catches corrupted calibration or degraded stereo quality. Ref: Retrospective §6.1. | TBD | MEDIUM | 0.5 day | ⬜ |
| A22 | **Verify arm_2 camera calibration** — Has arm_2's OAK-D Lite been calibrated with same procedure as arm_1? If calibration is worse, explains arm_2's 3-4x higher border filter rate. Quick check. Ref: BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md §10 Q1. | TBD | MEDIUM | 0.5 day | ⬜ |
| A23 | **Model validation protocol** — Establish a repeatable validation protocol for model selection decisions. Prevent ad-hoc mid-trial model switching under field pressure. Define test conditions, metrics, pass/fail criteria, and sign-off process. Ref: Retrospective §3.2. | TBD | MEDIUM | 1 day | ⬜ |
| A24 | **Stale detection handling** — 11.9% (arm_1) and 13.2% (arm_2) of picks used stale detections (>2s old). Add configurable max detection age, reject picks with stale data. Ref: FIELD_TRIAL_REPORT_MAR25_2026.md §2.6, §3.8. | TBD | LOW | 0.5 day | ⬜ |
| A25 | **Adaptive border filtering (depth-confidence-based)** — Accept edge detections with high stereo confidence instead of hard margin rejection. Depth confidence available from OAK-D but not propagated. Long-term improvement. Ref: BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md R5, Retrospective Decision 5. | TBD | LOW | 1-2 weeks | ⬜ |
| A26 | **Adaptive J4 position selection** — Replace fixed J4 positions with algorithm that selects next scan position based on previous border detection results. Reduces scan time. Long-term. Ref: BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md R6. | TBD | LOW | 1-2 weeks | ⬜ |
| A27 | **Border detection edge distribution analysis** — Analyze March data: are border-filtered detections clustered on a specific image edge (L/R/T/B)? Clustering indicates camera alignment vs random geometry. Informs A13. Ref: BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md §10 Q3. | TBD | LOW | 0.5 day | ⬜ |
| A28 | **Investigate arm_1 Session 3 zero-detection anomaly** — 0 cotton detected at any J4 position in Session 3 despite model fallback warning present. Determine if model path issue caused complete detection failure. Ref: FIELD_TRIAL_REPORT_MAR25_2026.md §2.6. | TBD | LOW | 0.5 day | ⬜ |

---

## Section 2: Vehicle Tasks

### 2.1 Vehicle Reliability

| # | Task | Owner | Priority | Est. Effort | Status |
|---|------|-------|----------|-------------|--------|
| V1 | **Deploy can_watchdog.service** — Missing from arm_2 and vehicle RPis. Must be deployed and verified on all RPis before next trial. Currently only running on arm_1. | TBD | MEDIUM | 0.5 day | ⬜ |
| V2 | **Investigate CAN RX error rate** — 1.59M RX errors in Session 2 (~220/sec). MCP2515 SPI limitation contributing to ODrive cascading failures (29,950 WARN/ERROR lines in vehicle logs). Determine if this is a hardware limitation requiring CAN controller upgrade or if SPI clock/buffer tuning can reduce the rate. Ref: FIELD_TRIAL_REPORT_MAR25_2026.md. Decision gate: If investigation confirms MCP2515 hardware limitation with no software mitigation, proceed to V11 (MCP2518FD upgrade evaluation). | TBD | MEDIUM | 2-3 days | ⬜ |
| V3 | **Vehicle RPi thermal management** — March 24 pre-field test showed CPU hitting 83.8 degrees C (thermal throttling territory). Install heat sink or fan before April trial. Verify thermal profile stays below 75 degrees C under sustained operation. | TBD | MEDIUM | 0.5 day | ⬜ |
| V4 | **ODrive error pattern analysis** — March showed 29,491 ODrive errors across 8 error codes. Includes 0x42000000 (OVERTEMP on drive_left_back), 0x00000200 (DC_BUS_OVER_REGEN_CURRENT from E-stop), 643 ERRORs/min peak density. Determine root cause: current limit configuration, encoder errors, or terrain-induced load spikes. Tune ODrive config to reduce error rate. | Gokul | MEDIUM | 1-2 days | ⬜ |
| V8 | **E-stop field validation** — Hardware E-stop was activated during March 25 trial (Session 3→4 transition), successfully cutting motor power. But NO logging captured the event. Session 4: all motors UNAVAILABLE for 30 min. Hardware GPIO button: see V12. Carried from March V12. | TBD | MEDIUM | TBD | ⬜ |
| V9 | **ODrive drive motor temperature monitoring** — ODrive CAN protocol supports FET and motor thermistor temperature reads, but odrive_service_node does not request or publish this data. Add temperature monitoring to catch thermal issues before damage. Carried from March V16. | TBD | MEDIUM | TBD | ⬜ |
| V10 | **Automatic clock sync on RPi boot** — Install chrony or configure systemd-timesyncd with local NTP server (laptop or field router). Ensure clock correction runs on every boot without manual provisioning. March 25 had ~85 min drift after lunch reboot. Phase 3/4 have verification gates but no implementation task. CRITICAL for data integrity. Ref: Clock Drift investigation, Retrospective §1.6. | TBD | HIGH | 1 day | ⬜ |
| V13 | **Add E-stop event logging** — structured log for motor power loss detection (vbus→0, CAN silence). Currently no log captures E-stop activation. | TBD | HIGH | 1 day | ⬜ |
| V14 | **Add vbus voltage monitoring** — log vbus transitions, alert on drop to 0V while node running. | TBD | HIGH | 0.5 day | ⬜ |
| V15 | **Fix mg6010 silent CAN failure** — controller silently drops per-motor data when CAN communication fails. Add explicit "CAN read timeout" error logging. | TBD | HIGH | 1 day | ⬜ |

### 2.2 Vehicle Hardware Improvements

| # | Task | Owner | Priority | Est. Effort | Status |
|---|------|-------|----------|-------------|--------|
| V5 | **Add physical homing reference for front wheel** — Limit switch or index pulse. Only truly robust solution for encoder drift. Software detection (A1) is a mitigation, not a fix. Hardware mod required. | TBD | LOW | TBD | ⬜ |
| V6 | **Three-wheel steering integration** — Carried from March (was V5). Verify steering angle accuracy for 90-degree turns. Status from March unclear — confirm current state before adding to April scope. | Vasanth / Arvind | MEDIUM | TBD | ⬜ |
| V7 | **IMU + RTK GPS integration** — Carried from March (was V8, V9). First-version sensor data collection. Not required for April trial execution but valuable for autonomous navigation development. | Vasanth / Arvind | LOW | TBD | ⬜ |
| V11 | **MCP2518FD CAN controller upgrade path** — If V2 confirms MCP2515 is a hardware limitation (220/sec RX errors), evaluate and procure MCP2518FD replacement. Conditional on V2 findings. Ref: Retrospective Decision 7. | TBD | MEDIUM | 1-2 days HW + 1 day SW | ⬜ |
| V12 | **Hardware E-stop GPIO button for arms** — Physical emergency stop button fabrication and GPIO integration. Software E-stop (V8) requires SSH/laptop. Physical button is faster in emergencies. Separate from V8 software validation. Ref: Retrospective §6.6, Decision 4. | TBD | MEDIUM | 1-2 days | ⬜ |

---

## Section 3: Software Tasks

| # | Task | Owner | Priority | Est. Effort | Status |
|---|------|-------|----------|-------------|--------|
| S1 | **Fix model path warning** — Deploy yolov112.blob to data/models/ on arm_1 RPi. Eliminates fallback warning logged every session. Trivial deployment fix. | TBD | MEDIUM | 15 min | ⬜ |
| S2 | **Fix network_monitor script** — Not collecting data on arm_2 (empty logs). Diagnose whether script fails to start, starts but crashes, or runs but cannot access network interfaces. | TBD | MEDIUM | 0.5 day | ⬜ |
| S3 | **Profile python3 memory leak** — Source identified: `dashboard_server` (uvicorn) at ~22MB/hr, `rpi_agent` +61.6MB at init. Both arms affected. Profile with tracemalloc. | TBD | MEDIUM | 1-2 days | ⬜ |
| S4 | **Fix detection log severity** — detection_summary JSON logged at ERROR level inflates error counts in log analyzer output. Change to INFO or DEBUG level. Trivial code change. | TBD | MEDIUM | 15 min | ⬜ |
| S5 | **Monitor J3 position drift on arm_2** — arm_2 J3 showing degrading trend (small but non-zero). Add J3 position error to health monitoring dashboard. If drift exceeds threshold after March data analysis, escalate to HIGH priority. | TBD | MEDIUM | 0.5 day | ⬜ |
| S6 | **Investigate detection age increase** — arm_2 detection age increasing at 90ms/hour. Over a 4-hour session this means detections arrive ~360ms later than at session start. Possible causes: memory pressure (S3), pipeline queue growth, or camera thermal throttling. | TBD | MEDIUM | 1 day | ⬜ |
| S7 | **Add idle current monitoring** — Ongoing health metric for all MG6010 motors. Baseline idle current at startup, alert if deviation exceeds threshold (indicates mechanical binding, encoder misalignment, or bearing wear). Feeds into startup verification (A1). Implement continuous baseline comparison per encoder RCA R3: establish per-motor baseline at startup, sliding window average, alert if idle current exceeds 2x baseline for >30 seconds. This provides defense-in-depth — catches encoder drift that develops mid-operation, not just at startup (A1). | TBD | MEDIUM | 1-2 days | ⬜ |
| S8 | **Pre-flight hardware validation script** — Carried from March (was V20). Automated CAN bus, camera, motor power, network, and binary freshness checks. Must run on all RPis before every test session. March 16 lost 5.5 hours to CAN failures that a 30-second pre-flight would have caught. If already implemented for March 25, verify it covers all check items. Additional checks beyond CAN/camera/motors/network: (a) camera depth sanity check (see A21), (b) motor position self-test for all joints (not just steering — A1 covers steering only), (c) clock sync verification (see V10). | TBD | HIGH | 1 day | ⬜ |
| S9 | **ArUco detection instrumentation** — Carried from March (was A24, Gap 20). ArUco detection events not instrumented in JSON logging. Add timing, success/failure, and marker ID to structured logs. | TBD | LOW | 0.5 day | ⬜ |
| S10 | **RPi re-provisioning protocol and automation** — After any mid-session reboot, clock and config must be re-synced. Options: (a) add clock sync to boot sequence (see V10), (b) document manual re-provision protocol for field ops, (c) add `sync.sh --time-sync` to systemd boot targets. Operational + software. Ref: Clock Drift investigation. | TBD | HIGH | 0.5 day | ⬜ |
| S11 | **Fix February software bugs (init sequence, timeout, dedup)** — Encoder RCA §4.4 notes: no motor_stop on position timeout (RC-2), init sends motor_on before clear_errors (RC-3), no command deduplication (RC-5). These amplify thermal damage from any stall. Ref: ENCODER_ZERO_SHIFT_ANALYSIS_2026-03.md §4.4, STEERING_THERMAL_CASCADE_ANALYSIS. | TBD | MEDIUM | 1-2 days | ⬜ |
| S12 | **Encoder health tracking (raw zero reference logging)** — Log raw encoder zero reference on each power-up. Track drift between sessions for predictive maintenance. Simple logging addition. Ref: ENCODER_ZERO_SHIFT_ANALYSIS_2026-03.md R5. | TBD | LOW | 0.5 day | ⬜ |
| S13 | **Encoder power-up sequence investigation** — Investigate exact power-up sequence: engine running? Multiple motors initializing simultaneously? Determine if delayed/sequenced initialization prevents encoder shifts. Ref: ENCODER_ZERO_SHIFT_ANALYSIS_2026-03.md §10 Q1-Q3. | TBD | LOW | 0.5 day | ⬜ |
| S14 | **MG6010 gear ratio self-locking verification** — Determine if 1:300 gear ratio is self-locking. Affects A1 implementation: if not self-locking, disabling a steering motor could cause uncontrolled wheel movement. Safety check. Ref: ENCODER_ZERO_SHIFT_ANALYSIS_2026-03.md §10 Q4. | TBD | LOW | 0.5 day | ⬜ |
| S15 | **Investigate J3 drift root cause on arm_2** — S5 adds monitoring, but no task investigates WHY J3 is degrading (mechanical wear? calibration? bearing?). Ref: FIELD_TRIAL_REPORT_MAR25_2026.md §3.9. | TBD | LOW | 0.5 day | ⬜ |
| S16 | **Fix NetworkManager-wait-online.service boot failure** — Failed during arm_2 Session 4 boot. Could cause timing-dependent startup failures. One-line systemd fix. Ref: FIELD_TRIAL_REPORT_MAR25_2026.md §3.2. | TBD | LOW | 15 min | ⬜ |
| S17 | **Fix boot reliability** — RCU stalls and journal corruption on both arms during boot. Stagger node startup or switch to performance CPU governor. | TBD | MEDIUM | 1 day | ⬜ |
| S18 | **Monitor disk usage** — 150MB/hr growth on arm_2. Add disk space alerting. | TBD | MEDIUM | 0.5 day | ⬜ |
| S19 | **Evaluate DepthAI shave configuration** — model compiled for 6 shaves, runtime uses 4, 9 available. Benchmark inference speed at different shave counts. | TBD | LOW | 1 day | ⬜ |
| S20 | **Migrate from ROS_LOCALHOST_ONLY** — deprecated, switch to ROS_AUTOMATIC_DISCOVERY_RANGE and ROS_STATIC_PEERS. | TBD | LOW | 0.5 day | ⬜ |

---

## Section 4: Carried Forward from March 25

All 17 recommendations from FIELD_TRIAL_REPORT_MAR25_2026.md Section 7 are mapped to April
work items. The following table provides traceability from March recommendation to April task.

### 4.1 March 25 Recommendations Mapping

| # | March Recommendation | Priority | April Task | Notes |
|---|---------------------|----------|------------|-------|
| 1 | Startup zero-position verification for steering motors | CRITICAL | A1 | New task |
| 2 | Stall escalation limit | CRITICAL | A2 | New task |
| 3 | Resolve detection model trade-off | CRITICAL | A3 | New task — requires team decision |
| 4 | Investigate reachability boundaries | HIGH | A4 | New task — highest-impact for success rate |
| 5 | Remove or deprioritize +150mm J4 position | HIGH | A5 | Config change |
| 6 | Reduce border filter margin from 5% to 3% | HIGH | A6 | Config change + validation |
| 7 | Investigate J4 action rejection pattern | HIGH | A7 | New task — 89 wasted cycles |
| 8 | Fix model path warning | MEDIUM | S1 | Deployment fix (15 min) |
| 9 | Deploy can_watchdog.service | MEDIUM | V1 | Deployment fix (0.5 day) |
| 10 | Fix network_monitor script | MEDIUM | S2 | Diagnostic fix |
| 11 | Profile python3 memory leak | MEDIUM | S3 | 24MB/hour on arm_2 |
| 12 | Fix detection log severity | MEDIUM | S4 | Trivial code fix (15 min) |
| 13 | Investigate CAN RX error rate | MEDIUM | V2 | 220 errors/sec on vehicle |
| 14 | Monitor J3 position drift | MEDIUM | S5 | arm_2 J3 degrading trend |
| 15 | Investigate detection age increase | MEDIUM | S6 | 90ms/hour drift on arm_2 |
| 16 | Add physical homing reference | LOW | V5 | Hardware mod — long-term fix |
| 17 | Add idle current monitoring | LOW | S7 | Health metric |

### 4.2 Deferred Items from March Plan

| Item | March Status | April Disposition | April Task |
|------|-------------|-------------------|------------|
| YOLOX migration (March Decision 1: NO-GO) | Parked — pipeline validated but accuracy/timing unproven | Remains parked unless A3 decision selects YOLOX as the model path. YOLOX NeuralNetwork + SpatialLocationCalculator pipeline is validated. Resume only if team decides YOLOX is the right architecture. | A3 (covers model decision) |
| Dynamic picking preparation (March A26) | Covered by existing log analyzer + JSON events | Continue as exploratory work. March 25 field data available for analysis. Not required for April trial. | A8 |
| depthai_manager decomposition | Reverted March 14 — RealDevice adapter never written. 5-8 engineering day effort, HIGH risk. | Remains deferred. Monolithic depthai_manager.cpp (2,228 lines) is stable and functional. Re-decomposition is a post-trial improvement, not a field trial requirement. Ref: DEPTHAI_DECOMPOSITION_DEFER_DECISION_2026-03.md | Not scheduled |
| Three-wheel steering integration (March V5) | Status unclear from March | Carry forward — confirm current state before scoping. | V6 |
| IMU + RTK GPS integration (March V8, V9) | Not completed in March | Carry forward as LOW priority. Data collection only, not trial-critical. | V7 |
| Detection accuracy benchmark with ground truth (March A9) | Baselines extracted from Feb/Mar logs, no ground-truth test done | Carry forward. True precision/recall/F1 requires controlled test. | A9 |
| Left-right pick yield asymmetry (March A10) | Feb data showed 4.6x difference, no root cause found | Carry forward. March data available for comparison. | A10 |
| Per-joint timing optimization (March A11) | Per-joint fields now populated in March data, no optimization plan written | Carry forward. Analyze March data, write concrete plan. | A11 |

### 4.3 Additional Items from March Plan (not from field report)

| March Task | Description | April Task | Status |
|-----------|------------|-----------|--------|
| A2 | L3 camera offset correction | A13 | ⬜ Carried |
| A4 | L5 depth control investigation | A14 | ⬜ Carried |
| A27/A29/A30 | Workspace analysis + URDF limits + validation | A4 (merged) | ⬜ Scope expanded |
| V12 | E-stop field validation | V8 | ⬜ Carried |
| V16 | ODrive drive motor temperature monitoring | V9 | ⬜ Carried |

**Items resolved (not carried):**
- A1 (L3 PID tuning) — resolved, field performance confirmed adequate
- A3 (L5 home recalibration) — resolved
- A17 (Arm mechanical review) — resolved
- A18 (Collection box redesign) — resolved, worked adequately
- A20 (Drop/throw trajectory tuning) — resolved, 98.4% pick success when reachable
- A21 (Two-arm collision avoidance) — resolved, block-and-skip working
- V1 (ODrive PID tuning) — resolved, 0 crashes on March 25
- V10 (Improved vehicle logging) — resolved, comprehensive logs collected
- V11 (Static IP setup) — resolved via DHCP reservations
- V18 (ODrive slope/terrain test) — resolved, test completed

### 4.4 Gap Analysis Findings (post-report)

Cross-referencing all March 25 findings (field trial report, 3 RCA documents, retrospective)
against the initial April plan revealed 24 issues not covered and 12 partially covered tasks.
All gaps have been added as new tasks (A15-A28, V10-V12, S10-S16) or amendments to existing
tasks. Key additions:

| Category | New Tasks | Key Items |
|----------|-----------|-----------|
| Clock sync | V10, S10 | Automatic NTP on boot — prevents ~85 min drift seen March 25 |
| Detection robustness | A16, A18, A23 | Model class validation, confidence gating fallback, validation protocol |
| Border filter | A15, A19, A20, A22, A25, A26, A27 | arm_2 J4 expansion, depth verification, per-camera calibration, adaptive filtering |
| Motor reliability | S11, S12, S13, S14, S15 | Feb bug fixes, encoder health tracking, power-up investigation, gear self-lock |
| Reachability | A17 | checkReachability() implementation |
| Startup validation | A21 | Camera depth sanity check |
| Hardware | V11, V12 | CAN controller upgrade path, hardware E-stop button |
| Miscellaneous | A24, A28, S16 | Stale detection handling, zero-detection anomaly, NetworkManager fix |

---

## Section 5: Testing Phases

### Phase 1: Critical Fixes (Week 1-2 after team review)

**Goal:** Resolve all CRITICAL items. No field trial scheduling until these are done.

| Task | Owner | Acceptance Criteria | Status |
|------|-------|---------------------|--------|
| A1: Startup zero-position verification | TBD | Idle current check detects simulated encoder drift in lab. Flag raised within 5 seconds of homing completion. | ⬜ |
| A2: Stall escalation limit | TBD | Motor auto-disables after 3 consecutive stalls within 5 minutes in simulation/mock test. MOTOR_DISABLED alarm raised. | ⬜ |
| A3: Detection model decision | TBD | Team has reviewed options A/B/C. Decision documented. Training started for chosen option. | ⬜ |
| A3: Detection model training | TBD | Model trained and validated on test set. Accuracy >= 60% on field-condition images (improvement over current baseline). | ⬜ |
| S1: Model path warning fix | TBD | yolov112.blob deployed. No fallback warning in arm_1 startup logs. | ⬜ |
| S4: Detection log severity fix | TBD | detection_summary logged at INFO. Log analyzer error count drops. | ⬜ |
| S8: Pre-flight validation script | TBD | Script runs on all 3 RPis. Reports PASS/FAIL per check. Catches simulated CAN failure. | ⬜ |
| V10: Automatic clock sync on RPi boot | TBD | After simulated reboot without provisioning, clock drift <5 seconds within 60 seconds of boot. | ⬜ |
| A16: Model class count validation | TBD | Mismatched class count causes node abort with clear error message within 5 seconds of startup. | ⬜ |

### Phase 2: Lab Integration (Week 2-3)

**Goal:** HIGH-priority fixes integrated and tested in lab with both arms on vehicle.

| Task | Owner | Acceptance Criteria | Status |
|------|-------|---------------------|--------|
| A4: Reachability boundary validation | TBD | Collision envelope mapped. New margin validated with 50+ approach trajectories. Zero actual collisions. | ⬜ |
| A5: J4 scan position optimization | TBD | +150mm removed from config. Lab test shows no reduction in picks within +/-100mm range. | ⬜ |
| A6: Border filter margin reduction | TBD | 3% margin deployed. False pick rate does not increase vs. 5% margin on same test set. | ⬜ |
| A7: J4 action rejection fix | TBD | Root cause identified. Fix deployed. Zero feedback_samples=0 rejections in 100-pick lab test. | ⬜ |
| V1: can_watchdog deployment | TBD | Service running on all 3 RPis. Verified with systemctl status. | ⬜ |
| New detection model deployed | TBD | Chosen model (from A3) deployed to both arm RPis. Detection rate measured in lab. | ⬜ |
| Two-arm integration test | TBD | 100+ pick cycles. Both arms running. No inter-arm collisions. Success rate measurable. | ⬜ |
| A15: arm_2 7-position J4 scan | TBD | arm_2 border filter rate drops below arm_1's 12.1% in lab test. | ⬜ |
| A17: checkReachability() implementation | TBD | Pre-check rejects known-unreachable targets before motion planning. Reduces planning failures by measurable amount in lab. | ⬜ |
| A19: Depth quality verification | TBD | Depth variance data in 3-5% border zone analyzed. Recommended margin documented. | ⬜ |

### Phase 3: Pre-Field Validation (Week before trial)

**Goal:** Full system validation under conditions approximating field environment.

| Task | Owner | Acceptance Criteria | Status |
|------|-------|---------------------|--------|
| Full 2-arm pick cycle test (200+ cycles) | All | Success rate >65% in lab. No stall cascades. No encoder drift. | ⬜ |
| Stall escalation validated under load | TBD | Provoke stall scenario. Motor disables correctly. No thermal runaway. | ⬜ |
| Startup verification catches simulated drift | TBD | Misalign encoder by 5 degrees. System detects and flags before operation. | ⬜ |
| New detection model field-proxy test | TBD | Test with field-lighting images (outdoor, direct sun). Measure sensitivity improvement. | ⬜ |
| Vehicle steering + drive 30-minute test | Gokul | No stalls, no thermal warnings, steering angle accuracy within 5 degrees. | ⬜ |
| All RPis provisioned and clock-synced | TBD | Clock drift <1 minute over 4 hours. All provision steps pass. | ⬜ |
| Cross-compile and deploy to all RPis | All | Clean build. All nodes launch. Pre-flight validation passes. | ⬜ |
| Log collection verified from all RPis | TBD | sync.sh --collect-logs retrieves non-empty logs from all 3 RPis. | ⬜ |

### Phase 4: Field Trial

**Goal:** Two-arm single-row cotton picking, targeting >70% success rate.

| Task | Owner | Acceptance Criteria |
|------|-------|---------------------|
| Pre-flight hardware validation on all RPis | TBD | CAN, camera, motors, network, binary freshness all PASS |
| RPi clock sync verified | TBD | All RPis within 30 seconds of each other |
| Vehicle positioned close to cotton row | All | Arm reach covers majority of cotton bolls (x < 0.45m preferred) |
| Pre-test mechanical checklist | Dhinesh | All items pass — belts, home positions, EE, collection box |
| Field trial execution — single row, two arms | All | Minimum 3 hours of operation (longer session than March) |
| Monitor stall escalation in real-time | TBD | If any motor hits 3-stall limit, observe correct auto-disable |
| Post-trial log collection from all RPis | TBD | All logs collected before leaving field |
| Post-trial debrief | All | Observations recorded, issues documented |

---

## Section 6: Go/No-Go Decision Points

### Decision 1: Detection Model Choice (1 week after team review)

**Question:** Which detection model path do we take for April?

Options:
- **Option A:** Retrain YOLOv11 with additional field lighting data
- **Option B:** Retrain YOLOv5 with 2 classes (cotton + shell)
- **Option C:** Train new model specifically for field conditions
- **Option D:** Switch to YOLOX (pipeline already validated from March)

Checklist:
- [ ] Team has reviewed DETECTION_MODEL_TRADEOFF_ANALYSIS_2026-03.md
- [ ] Training data inventory complete (number of field images, lighting conditions covered)
- [ ] Each option estimated for training time and validation effort
- [ ] Decision documented with rationale

**If no decision within 1 week:** Default to Option A (retrain v11) as lowest-risk path.

### Decision 2: Reachability Improvement Validation (pre-field)

**Question:** Are the relaxed collision margins safe for field operation?

Checklist:
- [ ] Collision envelope mapped in lab (A4 complete)
- [ ] New margins tested with 50+ approach trajectories
- [ ] Zero actual collisions with new margins
- [ ] Workspace rejection rate measured at <30% in lab test
- [ ] Two-arm collision avoidance still functions correctly with extended workspace

**If NO:** Revert to March 25 collision margins. Accept higher workspace rejection rate.
Focus on vehicle positioning to compensate.

### Decision 3: Encoder Verification Working (pre-field)

**Question:** Does the startup zero-position verification reliably detect encoder drift?

Checklist:
- [ ] A1 implemented and tested in lab
- [ ] Simulated encoder drift (5 degrees, 10 degrees, 15 degrees) detected correctly
- [ ] False positive rate <5% (does not flag correctly-homed motors)
- [ ] A2 stall escalation limit tested and verified

**If NO:** Do not proceed to field without encoder verification. Encoder drift caused the
worst single failure mode in March (17 stalls, 80 degrees C thermal runaway). If software
detection cannot be validated, consider manual verification protocol (operator checks motor
position visually after homing) as interim mitigation.

### Decision 4: Final Field Readiness (day before trial)

**Question:** Ready for field trial tomorrow?

Checklist:
- [ ] All CRITICAL items (A1, A2, A3) resolved
- [ ] All RPis provisioned and clock-synced
- [ ] Pre-flight hardware validation passes on all 3 RPis
- [ ] Cross-compiled binaries deployed
- [ ] Detection model (chosen from Decision 1) deployed and verified on both arm RPis
- [ ] Pre-field mechanical checklist passed (Dhinesh)
- [ ] Vehicle drives and steers in parking lot test
- [ ] Both arms complete pick cycles in parking lot test (>50 cycles, >60% success)
- [ ] Log collection verified from all RPis
- [ ] Emergency motor stop script tested
- [ ] Spare parts packed
- [ ] Battery fully charged
- [ ] Field site access confirmed

**If NO:** Identify specific blockers. Fix within 48 hours or postpone trial.
**If YES:** Proceed to field.

---

## Section 7: Risk Assessment

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Detection model does not improve enough with retraining | Medium | HIGH | Maintain both v11 and v5 as fallbacks. Test model in field-proxy lighting before trial. If retrained model is not clearly better, use whichever model performed best in March. Set minimum acceptance threshold: must beat 52.9% pick success rate in lab. |
| R2 | Reachability margin changes cause actual collisions | Medium | HIGH | Validate exclusively in lab first with 50+ trajectories. Start conservative (3cm relaxation), measure, then extend if safe. Keep March margins as instant rollback option. Never deploy untested margins to field. |
| R3 | Encoder zero shift recurs even with software detection (root cause is hardware) | High | MEDIUM | Software detection (A1) is a mitigation, not a root cause fix. Hardware fix (V5, limit switch) is long-term solution. For April: detection + manual verification protocol. Accept that software can only detect drift, not prevent it. Monitor for repeat occurrence. |
| R4 | Border filter reduction increases false picks | Low | MEDIUM | Validate 3% margin against 5% margin on same dataset before deployment. Measure false pick rate (picks on non-cotton objects). If false picks increase by >5pp, revert to 5% margin. |
| R5 | Two-arm collision avoidance untested with new workspace limits | Medium | HIGH | If A4 extends the workspace envelope, re-validate two-arm operation. The collision avoidance system was designed for the current workspace limits. Extended reach could create new inter-arm conflict zones. Test with both arms simultaneously in lab. |
| R6 | python3 memory leak causes arm_2 degradation during long session | Low | MEDIUM | April targets 3+ hour session (longer than March). At 24MB/hour, arm_2 consumes ~72MB extra. RPi 4B has 4GB RAM — not critical for single trial. Profile and fix (S3) if time permits. Restart arm_2 nodes at 2-hour mark as workaround if needed. |
| R7 | CAN RX errors cause ODrive cascade failures during field trial | Medium | HIGH | V2 investigation may reveal hardware limitation (MCP2515 SPI bottleneck). If so, no software fix is possible — mitigation is to reduce CAN bus traffic or upgrade CAN controller. For April: monitor CAN error rate in real-time, restart vehicle node if errors cascade. |
| R8 | Field conditions differ from lab (lighting, terrain, plant density) | High | MEDIUM | Position vehicle closer to row (primary lesson from March). Bring adjustable parameters (border filter margin, collision margins, detection thresholds) as runtime-configurable values. Tune in first 30 minutes of field session. |
| R9 | Rain or weather on trial day | Low | HIGH | Monitor forecast. Identify backup date. Electronics are not weatherproofed. |
| R10 | Model training takes longer than expected | Medium | MEDIUM | Start training immediately after Decision 1. If model is not ready 1 week before trial, use best available model from March and accept current detection performance. |
| R11 | E-stop leaves motors in unknown state | HIGH | HIGH | Session 4 showed CAN bus dead for 30 min after E-stop. No automated recovery exists. Add E-stop recovery protocol: detect power loss → alert operator → re-init motors on power restore. |
| R12 | Collision interlock disabled | MEDIUM | MEDIUM | Both arms operate without J3-J4 collision protection. Risk of mechanical collision if arms overlap. Re-enable interlock with field testing, or add minimum safe distance enforcement. |
| R13 | Boot failures on RPi 4B | LOW | LOW | RCU stalls and journal corruption observed but system eventually starts. Stagger service startup, increase kernel preemption. |
| R14 | Disk fills during long trial | MEDIUM | MEDIUM | 150MB/hr growth rate. 9.6GB available. ~64 hours to fill. Add disk monitoring with auto-rotation or alerting at 80%. |

---

## Section 8: Logistics

### Equipment Checklist

- [ ] Vehicle with 2 arms mounted
- [ ] 3 RPi 4B units (1 vehicle + 2 arm) with power supplies
- [ ] 2 OAK-D Lite cameras (tested and thermally baselined)
- [ ] Laptop for monitoring/SSH
- [ ] Ethernet cables and switch/router
- [ ] Fully charged batteries (+ spare if available)
- [ ] Spare belts for J5
- [ ] Spare EE motor assembly
- [ ] Heat sink or fan for vehicle RPi (V3)
- [ ] Basic tools (screwdrivers, Allen keys, zip ties, multimeter)
- [ ] Field trial logging script verified
- [ ] Emergency motor stop script on all RPis
- [ ] Pre-flight validation script on all RPis (S8)
- [ ] Drinking water, sun protection for team
- [ ] Printed documentation: trial plan, emergency procedures, motor protection guide

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

- [ ] Collect logs from all RPis (sync.sh --collect-logs)
- [ ] Copy detection images from both arm RPis
- [ ] Record field conditions (row spacing, plant height, weather, temperature)
- [ ] Team debrief notes (all observations captured)
- [ ] Photograph any mechanical damage or issues
- [ ] Run log analyzer on collected data same day
- [ ] Compare results against April targets table (Section 1)

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

## Appendix A: March 25 Field Trial Summary

Full details in `docs/project-notes/FIELD_TRIAL_REPORT_MAR25_2026.md`.

### Key Improvements Over February

| Area | February | March | Improvement |
|------|----------|-------|-------------|
| Pick success rate | 26.7% | 52.9% | +26.2pp |
| Vehicle crashes | 9 | 0 | Eliminated (ODrive error recovery working) |
| Two-arm operation | Not possible (arm2 unavailable) | Both arms operational | Validated |
| Workspace rejections | 73% | 46.2% | -26.8pp |
| MQTT uptime | 97.7% | ~98.0% | Improved |
| JSON instrumentation | j3/j4/j5_ms all zero | All fields populated | Working |
| Zero spatial filtering | 17% (unfiltered) | 1,024 filtered OK | Filtering functional |

### Key Issues Driving April Plan

| Issue | March Impact | April Task |
|-------|-------------|------------|
| COLLISION_BLOCKED at x>0.49m | 73.1% of planning failures | A4 (reachability investigation) |
| Encoder zero-position drift | 17 stalls, 80 degrees C thermal runaway | A1 (startup verification) |
| No stall escalation limit | Thermal damage before manual intervention | A2 (auto-disable after 3 stalls) |
| Detection model trade-off (v11 vs v5) | Misses cotton vs picks shells | A3 (model decision) |
| Border filter over-aggressive | 23-52% filter rate (was 5.3%) | A6 (reduce margin) |
| +150mm J4 position low yield | 7.4-11.7% yield, wastes scan time | A5 (remove position) |
| J4 action rejections | 89 wasted cycles | A7 (timing/state-machine fix) |
| python3 memory leak on arm_2 | 24MB/hour growth | S3 (profiling) |
| CAN RX errors on vehicle | 1.59M errors, 220/sec | V2 (investigation) |
| E-stop with no logging | Session 4 CAN dead 30 min, no structured log | V13, V14, V15 |
| Collision interlock disabled | Both arms, all sessions | A29 |
| J3 position clamping | 278 events on arm_2 | A30 |
| Memory leak source | dashboard_server 22MB/hr | S3 (updated) |
| Boot reliability | RCU stalls, journal corruption | S17 |

### What Worked Well in March

- Two-arm independent operation validated (no inter-arm collisions)
- Zero vehicle crashes (ODrive error recovery effective)
- MQTT start_switch trigger from vehicle to both arms reliable
- All JSON instrumentation fields populated and working
- Motor position feedback functional across all joints
- Eject sequence (M2 reverse + forward flush) completing consistently
- Zero spatial coordinate filtering preventing invalid pick attempts
- Pick cycle time stable (no degradation over session duration)

---

## Appendix B: Priority Summary

### Work Items by Priority

| Priority | Count | Items |
|----------|-------|-------|
| CRITICAL | 3 | A1 (encoder verification), A2 (stall escalation), A3 (detection model) |
| HIGH | 17 | A4 (reachability), A5 (J4 positions), A6 (border filter), A7 (J4 rejections), A13 (camera offset), A14 (depth control), A15 (arm_2 J4 7-pos), A16 (model class validation), A17 (checkReachability), A29 (collision interlock), A30 (J3 clamping), V10 (clock sync), V13 (E-stop logging), V14 (vbus monitoring), V15 (CAN failure logging), S8 (pre-flight script), S10 (re-provisioning) |
| MEDIUM | 30 | A8-A12, A18-A23, V1-V4, V6, V8-V9, V11-V12, S1-S7, S11, S17, S18 |
| LOW | 15 | A24-A28, V5, V7, S9, S12-S16, S19, S20 |
| **Total** | **65** | |

### Estimated Effort Summary

| Category | Estimated Total |
|----------|----------------|
| Critical fixes (A1, A2, A3) | 2-3 weeks (model training dominates) |
| High-priority fixes (A4-A7, A13-A17, V10, S8, S10) | 2-3 weeks |
| Medium-priority fixes | 3-4 weeks (can run parallel with critical) |
| Low-priority items | Ongoing / as-available |

---

## Appendix C: Reference Documents

| Document | Location |
|----------|----------|
| March 25 Field Trial Report | `docs/project-notes/FIELD_TRIAL_REPORT_MAR25_2026.md` |
| Encoder Zero Shift Analysis | `docs/project-notes/ENCODER_ZERO_SHIFT_ANALYSIS_2026-03.md` |
| Detection Model Tradeoff Analysis | `docs/project-notes/DETECTION_MODEL_TRADEOFF_ANALYSIS_2026-03.md` |
| Border Filter Escalation Analysis | `docs/project-notes/BORDER_FILTER_ESCALATION_ANALYSIS_2026-03.md` |
| Pick Rejection Bottleneck Analysis | `docs/project-notes/PICK_REJECTION_BOTTLENECK_ANALYSIS_2026-03.md` |
| Zero Spatial Coordinate Analysis | `docs/project-notes/ZERO_SPATIAL_COORDINATE_ANALYSIS_2026-03.md` |
| Steering Thermal Cascade Analysis | `docs/project-notes/STEERING_THERMAL_CASCADE_ANALYSIS_2026-03.md` |
| depthai_manager Decomposition Defer | `docs/project-notes/DEPTHAI_DECOMPOSITION_DEFER_DECISION_2026-03.md` |
| March Field Trial Plan | `docs/project-notes/MARCH_FIELD_TRIAL_PLAN_2026.md` |
| February Field Trial Plan | `docs/project-notes/FEBRUARY_FIELD_TRIAL_PLAN_2026.md` |
| Emergency Procedures | `docs/EMERGENCY_PROCEDURES.md` |
| Field Trial Cheatsheet | `docs/FIELD_TRIAL_CHEATSHEET.md` |
| Product Requirements Document | `docs/specifications/PRODUCT_REQUIREMENTS_DOCUMENT.md` |
| Technical Specification Document | `docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md` |

---

**Report Created:** March 25, 2026
**Last Updated:** March 26, 2026 (log audit: V13-V15, A29-A30, S17-S20, R11-R14 added)
**Author:** Udayakumar
**Review Status:** Initial draft — pending team review of March 25 findings and April trial date selection.
