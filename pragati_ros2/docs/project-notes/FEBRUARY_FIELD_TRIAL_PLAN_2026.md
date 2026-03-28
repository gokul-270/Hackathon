# February Field Trial Plan (2026)

**Target Date:** February 25, 2026
**Deadline for Prep:** February 20, 2026
**Created:** January 28, 2026
**Last Updated:** February 26, 2026 (Added: Phase 4 field trial results from Feb 26 visit)
**Overall Oversight:** Manohar
**Platform:** Raspberry Pi 4B

---

## Executive Summary

Prepare for the second comprehensive field trial following the January 2026 visit. This plan addresses critical issues discovered during January testing and carries forward pending improvements.

**CRITICAL BLOCKERS FROM JANUARY:**
1. 🟡 **Vehicle Drive Motors BURNT** - 3 drive motors (MG6012E-i36) failed (back-EMF damage when pushed without power). Steering motors (MG6012E-i6) are FINE. **RESOLUTION IN PROGRESS:** Replacing with ODrive motors from old setup. Software changes started, table-top testing underway. 1 additional ODrive Pro board ordered (have 2), 3 regenerative boards ordered.
2. 🟡 **Camera FOV Limited** - ~~Vertical orientation restricts horizontal coverage~~ → 🔵 DEFERRED (time constraint)
3. 🟡 **Steering Accuracy** - ~~Same wheel speed causing scrubbing during turns~~ → 📋 PLANNED (docs complete)

**SCOPE:** 2 arms (working) + vehicle (pending motor resolution)

---

## Implementation Status Update (Feb 16, 2026)

### ✅ Completed Implementations (Ready for Field Testing)

**1. Joint4 Multi-Position Scanning** 🟢 (Commit e3a7916, Feb 3)
   - **Status:** Code complete, **enabled in production.yaml** (`enabled: true`, 5 positions)
   - **Impact:** 60% FOV increase, 30%+ border_skip reduction expected
   - **Action Required:** Validate in field testing
   - **Details:** See Section 2.2

**2. MQTT Reconnection & Logging** 🟢 (Commit 0c18ab9, Feb 3)
   - **Status:** Timestamped logs, reconnect tracking implemented
   - **Impact:** Fixes log overwrites, visibility of reconnections
   - **Action Required:** Monitor in field under actual disconnects
   - **Tools:** Network diagnostic script added

**3. Network Diagnostics** 🟢 (Commit 0c18ab9, Feb 3)
   - **Status:** SSH/boot reliability diagnostics complete
   - **Impact:** Systematic RPi testing, troubleshooting guide (150+ lines)
   - **Action Required:** Run diagnostics on all RPis before field

**4. Configuration System** ✅ (Commit 5072a15, Feb 4)
   - **Status:** Multi-RPi profile management complete
   - **Impact:** Simplified deployment to multiple devices
   - **Ready:** Production use

### 🟡 Partial Fixes (Monitoring Required)

**5. EE Feedback Timeout** 🟡 (Commit 1e901f7, Jan 22)
   - **Status:** Small J5 moves fixed (adaptive threshold, direction-aware checks), long-distance case observed in field
   - **Impact:** Prevents 10-15s timeouts on small moves
   - **Outstanding:** Long-distance EE timeout (6s upper bound may be too short, no field data yet to validate)
   - **Action Required:** Monitor and log long J5 moves (>200mm) in field

### ⚠️ Hardware Constraints (Not Software)

**6. Position Out of Reach** - Physical reach limit (mitigated by J4 scanning)
**7. Shell Stuck in L5** - Mechanical hardware issue (not software fixable)

### 🔵 Deferred Items

**8. Horizontal Camera Mount** - Time constraint, using Jan vertical mount configuration

### 📋 Planned (Docs Complete, Code Pending)

**9. Differential Drive Velocities** (Docs: ff87e1e, Feb 3)
   - **Status:** Comprehensive implementation plan documented
   - **Impact:** Prevents wheel scrubbing during turns
   - **Outstanding:** Code implementation not started
   - **Reference:** See Section 3.1

### 🔴 Critical Pending Issues

**10. Detection [0,0,0] Bug** - ✅ FIXED (Feb 16)
   - **Root Cause TRACED (Feb 16):** DepthAI stereo depth fails on textureless surfaces (white cotton vs white sky, sun glare) → `spatialCoordinates = {0,0,0}` → `convertDetection()` at `depthai_manager.cpp:1878` copies directly with NO zero check → TF transform converts camera-frame [0,0,0] to camera's own position in arm frame (~0.64m) → passes `checkReachability()` → arm picks at camera location → FAILED
   - **Fix Applied:** `convertDetection()` now returns `std::optional<CottonDetection>`. When `spatialCoordinates == {0,0,0}`, logs WARN and returns `std::nullopt`. Both callers check `has_value()`.
   - **Impact:** Eliminates 5.7% pick failures (58/1021 attempts in Jan trial)

**11. ARM_client Crash Handling** - ✅ FIXED (Feb 16)
   - **Root Cause:** systemd service had `Restart=no`. Process crashes left arm offline until manual restart.
   - **Fix Applied:** `systemd/arm_launch.service` updated: `Restart=on-failure`, `RestartSec=5`, `StartLimitIntervalSec=60`, `StartLimitBurst=5`
   - **Note:** Requires `systemctl daemon-reload && systemctl restart arm_launch.service` on each Pi

**12. Field Trial Logging Script** - ✅ CREATED (Feb 16)
   - **Status:** `scripts/field_trial_logging.sh` created (~205 lines)
   - **Features:** Session directory with collision detection, ARM_client log capture via `tee` (visible in terminal), network monitor (ping + WiFi signal), system log collection (syslog, journalctl, dmesg), tar.gz archive, per-file size summary
   - **Usage:** `./field_trial_logging.sh [PING_TARGET] [MONITOR_INTERVAL]`

**13. Config Contradictions** - ✅ PARTIALLY FIXED (Feb 16)
   - `publish_fallback_on_zero`: **FIXED** — removed override from `arm_launcher.sh` line 33 AND from `cotton_detection_cpp.launch.py` parameter dict. `production.yaml` value (`true`) is now authoritative.
   - `hardware_offset`: 🟡 Three different values still exist (290mm, 320mm, 277.74mm) — needs physical measurement to resolve

**Software Completion:** 9/13 software tasks completed (69%)
**Field Testing Ready:** J4 multi-position, MQTT logging, network diagnostics, [0,0,0] fix, ARM_client watchdog, logging script, config fix

---

## Status Carried Forward from January 2026

### ✅ Working Systems
| System | Status | Notes |
|--------|--------|-------|
| Left Arm | ✅ Operational | 230 detection images captured |
| Right Arm | ✅ Operational | 344ms detection latency, 45-52°C temp |
| Cotton Detection (YOLOv11) | ✅ Working | `yolov112.blob` model deployed |
| Camera USB 3.0 | ✅ Working | 5Gbps connection stable |
| MQTT Coordination | ✅ Working | Arm-vehicle communication tested |

### 🔴 Critical Issues to Resolve
| Issue | Owner | Deadline | Status |
|-------|-------|----------|--------|
| **3 drive motors burnt** (MG6012E-i36; steering MG6012E-i6 fine) | Gokul | Feb 15 | 🟡 REPLACING WITH ODRIVE - software changes in progress, table-top testing underway |
| **Motor protection circuit** | Gokul/Joel | Feb 15 | 🟡 3 regenerative boards ordered |
| **Motor alternatives sourced** | Gokul | Feb 10 | ✅ Using ODrive motors from old setup; 1 additional ODrive Pro board ordered |
| **Detection returning [0,0,0]** | Uday | Feb 10 | ✅ FIXED (Feb 16) - `convertDetection()` returns `std::optional`, skips zero coords |

### 🟡 High Priority Improvements
| Issue | Owner | Deadline | Status |
|-------|-------|----------|--------|
| Camera horizontal mount | Swetha | Feb 15 | 🔵 DEFERRED (time constraint, using Jan vertical mount) |
| Joint4 multi-position picking | Uday | Feb 20 | 🟢 IMPL DONE (e3a7916 Feb 3) - field test pending |
| Differential drive velocities | Vasanth | Feb 20 | 📋 DOCS DONE (ff87e1e) - code pending |
| Position out of reach handling | Uday | Feb 15 | ⚠️ HARDWARE LIMIT - mitigated by J4 scanning |
| Border/edge cotton recovery | Uday | Feb 20 | 🟢 IMPL DONE (via J4 multi-pos) - field test pending |
| ARM_client crash handling | Uday | Feb 15 | ✅ FIXED (Feb 16) - systemd `Restart=on-failure` + rate limiting |
| Segmentation model POC | Vasanth | Feb 15 | 🟡 SAM POC done |

### 🟠 Additional Issues from January Field Trial
*(From JANUARY_FIELD_TRIAL_PLAN_2026.md Section A1-A6)*

| Issue | Owner | Deadline | Status | Source |
|-------|-------|----------|--------|--------|
| **L5 reach +10mm offset validation** | Uday | Feb 15 | ⬜ | A2 - offset added in field, needs validation |
| **EE feedback timeout** | Uday | Feb 15 | 🟡 PARTIAL FIX (1e901f7) - long distance needs monitoring | A2 - Small J5 moves fixed, long distance case observed in field without data |
| **Shell stuck in L5 handling** | Uday | Feb 15 | ⚠️ HARDWARE/MECHANICAL ISSUE | A2 - blocks subsequent picks (mechanical problem) |
| **Compressor restart-under-pressure** | Gokul | Feb 15 | ⬜ | A3 - failed at 6 bar, overloaded generator |
| **12V compressor alternative** | Amirthavarshini | Feb 10 | ⬜ | Eliminate generator - see COMPRESSOR_ALTERNATIVES_ANALYSIS.md |
| **MQTT reconnect logic** | Uday | Feb 15 | 🟢 IMPL DONE (0c18ab9 Feb 3) - field test pending | A5 - Logging + reconnect tracking implemented |
| **Boot-to-trigger reliability** | Uday | Feb 10 | 🟢 DIAGNOSTICS DONE (0c18ab9) - monitor in field | A5 - Network diagnostics + troubleshooting guide added |
| **Sun reflection false positives** | Swetha | Feb 15 | ⬜ | A4 - detected as cotton |
| **Steering angle verification** | Gokul | Feb 15 | ⬜ | A1 - not exactly 90° |
| **SSH connectivity issues** | Uday | Feb 10 | 🟢 DIAGNOSTICS DONE (0c18ab9) - monitor in field | A5 - Network stability script + troubleshooting added |
| **Power box push button faulty** | Gokul | Feb 20 | ⬜ | MCB-style push button was faulty — once closed, could not be opened again. Needs replacement or repair before field trial |
| **E-Stop button placement** | Gokul | Feb 20 | ⬜ | E-Stop was NOT placed in its dedicated panel location — kept in another spot where accidental presses occurred. Needs proper dedicated placement on panel |
| **Steering mechanical stopper** | Gokul | - | ✅ DONE | A1 - mechanical stopper was placed during Jan field trial |

### 🟠 Carry-Forward from January (Not Previously Tracked)
| Issue | Owner | Deadline | Status | Source |
|-------|-------|----------|--------|--------|
| **Emergency procedures documentation** | All | Feb 20 | ⬜ | Jan motors burnt with no documented recovery steps. Need written procedures for motor failure, electrical trip, CAN bus-off, compressor failure, RPi crash for ODrive setup |
| **Vehicle failure recovery drill (ODrive)** | Gokul | Feb 22 | ⬜ | Old drill was for MG6010/MG6012. Need to practice ODrive fault clearing, re-init, partial motor loss, regen board trip recovery. Depends on ODrive integration completion |
| **45-degree slope test (ODrive)** | Gokul | Feb 22 | ⬜ | Original test was for old motors. Need to verify ODrive motors hold position, drive uphill, brake downhill on field terrain. Depends on ODrive vehicle integration |
| **RTC clock sync** | Uday | Feb 20 | ⬜ | RPi RTC can READ but cannot SET time. Multiple RPis get different timestamps on boot without internet, makes cross-device log correlation difficult |
| **Run unit tests (129 existing)** | Uday | Feb 20 | ⬜ | Multiple commits since Jan trial (ODrive, [0,0,0] fix, config, watchdog, logging). No evidence tests have been run recently |
| **ROS2 latency testing** | Uday | Feb 20 | ⬜ | Jan requirement: no hop >100ms, end-to-end detection-to-pick <3s. ODrive adds new nodes/topics. May be partially covered by new timing instrumentation |
| **Power supply stable under load** | Gokul | Feb 22 | ⬜ | Verify battery sustains all systems simultaneously — 2 arms (3 motors each), vehicle (ODrive motors), 3 RPis, 2 cameras, compressor. Jan had generator overload at 6 bar compressor restart |

### 🔴 Unresolved Technical Issues (Root Cause Unknown)
| Issue | Owner | Deadline | Status | Notes |
|-------|-------|----------|--------|-------|
| **Phi compensation - root cause** | Swetha/Dhinesh | Feb 10 | ⬜ | Measure camera pitch angle (URDF says 45°) - see Section 9 |
| **L3 PID tuning** | Gokul | Feb 15 | ⬜ | Characterize response, tune for accuracy - see Section 9 |
| **L5 +10mm offset - why needed?** | Dhinesh/Gokul | Feb 10 | ⬜ | Measure hardware_offset (currently 290mm) - see Section 9 |

---

## Section 1: Vehicle Motors (CRITICAL PATH)

### 1.1 Motor Replacement Plan — ODrive Migration
**Owner:** Gokul
**Status:** 🟡 IN PROGRESS

Replacing burnt MG6012E-i36 drive motors with ODrive motors from old setup. Steering motors (MG6012E-i6) are unaffected and remain in use.

| Item | Status | Notes |
|------|--------|-------|
| ODrive motors (from old setup) | ✅ Available | Reusing existing hardware |
| ODrive Pro boards (existing) | ✅ Have 2 | Sufficient for initial table-top testing |
| ODrive Pro board (additional) | 🟡 Ordered | 1 more board ordered, awaiting delivery |
| Regenerative boards | 🟡 Ordered | 3 boards ordered, awaiting delivery |
| Software changes for ODrive | 🟡 In Progress | Adapting vehicle control code for ODrive interface |
| Table-top testing | 🟡 In Progress | Testing with existing 2 boards before full hardware arrives |
| Vehicle integration | ⬜ Pending | After boards arrive and software is validated |

### 1.2 Back-EMF Protection (MANDATORY)
**Owner:** Joel/Gokul
**Deadline:** February 15, 2026
**STATUS:** 🟡 Regenerative boards ordered (3x) — should handle back-EMF for ODrive setup

Previously planned TVS/flyback diode protection circuit (~$50 BOM) is superseded by regenerative boards for ODrive setup.

| Component | Qty | Status |
|-----------|-----|--------|
| Regenerative boards | 3 | 🟡 Ordered |

**Reference:** `docs/project-notes/VEHICLE_MOTOR_ALTERNATIVES_AND_PROTECTION.md`

---

## Section 2: FOV Improvements

### 2.1 Horizontal Camera Mount
**Owner:** Swetha
**Deadline:** February 15, 2026
**STATUS:** 🔵 DEFERRED - Time constraint prevents hardware modification. Using existing vertical mount from Jan field trial.

| Task | Status | Notes |
|------|--------|-------|
| Design mount bracket modification | 🔵 DEFERRED | Using Jan configuration |
| Fabricate/modify bracket | 🔵 DEFERRED | |
| Install in lab | 🔵 DEFERRED | |
| Update URDF orientation | 🔵 N/A | No change needed |
| Recalibrate camera | 🔵 N/A | Using existing calibration |
| Test detection accuracy | 🔵 N/A | Existing performance known |

### 2.2 Joint4 Multi-Position Picking
**Owner:** Uday
**Deadline:** February 20, 2026
**STATUS:** 🟢 Implementation Complete (Commit e3a7916, Feb 3 2026) - Field Testing Required

| Task | Status | Notes |
|------|--------|-------|
| Verify safe clearance at ±100mm | ✅ DONE | Multi-layer validation in code |
| Implement multi_position_picking() | ✅ DONE | `src/yanthra_move/src/core/motion_controller.cpp` |
| Add safety checks for extreme positions | ✅ DONE | Config limits + motor limits validation |
| Test cycle time impact | ⬜ FIELD TEST | Lab estimate: 4-6s vs 2.4s baseline |
| Validate coverage improvement | ⬜ FIELD TEST | Target: 60% FOV increase, 30%+ border_skip reduction |

**Implementation Details (Commit e3a7916, Feb 3 2026):**
- **Location:** `src/yanthra_move/src/core/motion_controller.cpp`
- **Configuration:** `src/yanthra_move/config/production.yaml`
  ```yaml
  joint4_multiposition:
    enabled: true  # Enabled for field testing (updated Feb 16)
    positions: [-0.100, -0.050, 0.000, 0.050, 0.100]  # 5 positions in meters
    scan_strategy: "left_to_right"  # or "right_to_left", "as_configured"
    settling_time_j4_ms: 100
    settling_time_detection_ms: 50
    enable_early_exit: true
  ```
- **Scan Process:** At each J4 position: move → settle TF → trigger detection → pick all visible cotton → move to next
- **Safety Features:** Multi-layer validation, graceful degradation, skip invalid positions
- **Statistics:** Per-position effectiveness tracking, early exit count, J4 movement failure tracking

**Expected Results:**
- 60% FOV coverage increase
- 10-20% pick success rate improvement
- 30%+ border_skip reduction (16 cotton rejected in Jan trial)
- Cycle time: 4-6s (vs 2.4s baseline) - acceptable for coverage gain

**Field Testing TODO:**
- [x] Enable `joint4_multiposition.enabled: true` in production.yaml (done, already enabled)
- [ ] Run test cycles to measure actual cycle time
- [ ] Track border_skip reduction
- [ ] Validate FOV coverage improvement
- [ ] Monitor J4 movement failures
- [ ] Review per-position statistics

**Reference:** `docs/project-notes/FOV_IMPROVEMENT_TASKS.md`, `docs/project-notes/FOV_IMPROVEMENT_IMPLEMENTATION_PLAN.md`

---

## Section 3: Steering & Vehicle Autonomy

### 3.1 Differential Wheel Velocities
**Owner:** Vasanth
**Deadline:** February 20, 2026
**STATUS:** 📋 Implementation Plan Complete (Commit ff87e1e, Feb 3 2026) - Code NOT Implemented

| Task | Status | Notes |
|------|--------|-------|
| Implement `calculate_differential_velocities()` | ⬜ PENDING | ICR-based model - see implementation checklist |
| Update `_send_drive_velocity()` | ⬜ PENDING | Use per-wheel speeds |
| Add unit tests | ⬜ PENDING | Straight, left, right turns |
| Test in simulation | ⬜ PENDING | Before hardware |
| Test with actual motors | ⬜ PENDING | When available |

**Planning Complete (Commit ff87e1e, Feb 3 2026):**
- Comprehensive implementation checklist: `docs/project-notes/VELOCITY_BASED_STEERING_IMPLEMENTATION_CHECKLIST.md`
- Design analysis: `docs/project-notes/VELOCITY_BASED_STEERING_ANALYSIS_2026-02.md`
- Day-by-day implementation plan (Week 1: Feb 3-9, Week 2: Feb 10-16, Week 3: Feb 17-23)
- Code structure defined, file locations specified
- Configuration examples provided

**Code Implementation Still Required** - Documentation phase complete, coding phase not started.

**Reference:**
- Implementation Checklist: `docs/project-notes/VELOCITY_BASED_STEERING_IMPLEMENTATION_CHECKLIST.md`
- Design Doc: `docs/project-notes/VEHICLE_STEERING_AND_AUTONOMY_DESIGN.md`
- Analysis: `docs/project-notes/VELOCITY_BASED_STEERING_ANALYSIS_2026-02.md`

### 3.2 Autonomy Preparation (Future)
| Sensor | Status | Notes |
|--------|--------|-------|
| RTK GPS | ⬜ Not purchased | Need budget approval |
| IMU | ⬜ Not integrated | Check if available |
| Wheel encoders | ⬜ Unknown | Check vehicle hardware |

**Decision:** Autonomy sensors deferred to future phase

---

## Section 4: Detection Improvements

### 4.1 Segmentation Model
**Owner:** Vasanth
**Status:** 🟡 POC completed with SAM

| Task | Status | Notes |
|------|--------|-------|
| SAM POC | ✅ Done | Proof of concept completed |
| Create labeled dataset | ⬜ | Need train/test/val split |
| Train YOLOv11-seg | ⬜ | For on-device deployment |
| Export to OAK-D blob | ⬜ | Same as current YOLOv11 |
| Compare accuracy vs bbox | ⬜ | Measure improvement |

**Benefits of Segmentation:**
- Exact cotton pixels (not bounding box)
- Background removal (leaves, sky)
- Better handling of touching/merged cotton
- Reduced reflection errors

### 4.2 Current Model Performance (from Jan 2026)
| Metric | Value |
|--------|-------|
| Model | YOLOv11 (`yolov112.blob`) |
| Detection Latency | p50: 69ms, p90: 103ms, max: 120ms |
| Camera Temperature | 45-52°C |
| XLink Errors | 0 |

### 4.3 Picking Performance Analysis (from Jan 2026 Logs)
**Session A (159 detection requests, 133 pick attempts):**
| Outcome | Count | % |
|---------|-------|---|
| ✅ Picked | 29 | **21.8%** |
| ❌ out_of_reach_joint4 | 57 | 42.9% |
| ❌ out_of_reach_joint5 | 26 | 19.5% |
| ❌ failed_pick ([0,0,0] bug) | 15 | 11.3% |
| ❌ approach_failed | 6 | 4.5% |

**Detection Classification:**
- Raw: 312 → Accepted: 144 (46%) + border_skip: 57 (18%) + not_pickable: 111 (36%)
- 30.6% of frames had border_skip

**Key Finding:** **Reachability is the dominant failure mode**, not detection.
- 54.9% targets too far (radial > 0.670m)
- 15.8% targets too close (radial < 0.320m)
- Fix: Joint4 multi-position + better FOV should recover many of these

---

## Section 5: Testing Matrix

### Phase 1: Pre-Hardware (Feb 1-10)
| Test | Owner | Status |
|------|-------|--------|
| ODrive software changes | Gokul | 🟡 In Progress |
| ODrive table-top testing | Gokul | 🟡 In Progress |
| Protection circuit design | Joel | ✅ Regen boards ordered |
| Horizontal mount design | Swetha | 🔵 DEFERRED |
| Differential drive code | Vasanth | ⬜ |
| Joint4 multi-position code | Uday | ✅ Done (e3a7916) |

### Phase 2: Lab Testing (Feb 11-20)
| Test | Owner | Status |
|------|-------|--------|
| ODrive vehicle integration | Gokul | ⬜ (after boards arrive) |
| Regen board install | Joel/Gokul | ⬜ (after boards arrive) |
| Horizontal camera test | Swetha | 🔵 DEFERRED |
| Arm + camera integration | Uday | ⬜ |
| Vehicle bench test (ODrive) | Gokul | ⬜ |

### Phase 3: Pre-Field (Feb 21-24)
| Test | Owner | Status |
|------|-------|--------|
| Full system integration | All | ⬜ |
| 2-hour endurance test | Uday | ⬜ |
| Vehicle + arm coordination | Gokul | ⬜ |
| ODrive 45-degree slope test | Gokul | ⬜ |
| ODrive failure recovery drill | Gokul | ⬜ |
| Power supply full-load test | Gokul | ⬜ |
| Pack for transport | All | ⬜ |

### Phase 4: Field Trial (Feb 26)
| Test | Owner | Status |
|------|-------|--------|
| Hardware setup | All | ✅ Done (arm1 only, arm2 hardware unavailable) |
| Camera FOV validation | Swetha | ✅ J4 scanning active (5 positions), camera working at 51-63C |
| Detection accuracy | Uday | ✅ Detection working (avg 34-93ms latency), 503 zero spatial coords (17%) |
| Picking success rate | Uday | ⚠️ 26.7% (315/1181) - 97% failures from workspace violations (cotton too far) |
| Vehicle operation (if ready) | Gokul | ❌ ODrive stall errors caused 9 crashes, steering_left overheated (76C) |

---

## Section 6: Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ODrive boards not arrived by Feb 25 | MEDIUM | Vehicle limited to 2-board testing | Software dev can proceed on 2 existing boards; prioritize arm testing |
| ODrive software integration issues | MEDIUM | Vehicle delayed | Table-top testing in progress to catch issues early |
| Horizontal mount affects accuracy | MEDIUM | Detection degraded | DEFERRED — using Jan vertical mount |
| Joint4 collision at ±100mm | MEDIUM | Arm damage | Implement safety checks; verify clearance |
| Weather issues | LOW | Field access limited | Have backup indoor test plan |

---

## Section 7: Decision Points

### February 5: Motor Decision
- [x] ~~Repair feasible?~~ → Not pursued
- [x] ~~Replacement needed?~~ → **DECIDED: Using ODrive motors from old setup** (software changes in progress, table-top testing underway)
- [x] 1 additional ODrive Pro board + 3 regenerative boards ordered

### February 15: Go/No-Go for Vehicle
- [ ] ODrive software changes complete?
- [ ] All boards arrived? (1 ODrive Pro + 3 regen)
- [ ] Table-top testing passed? → Proceed to vehicle integration
- [ ] Motors not ready? → Vehicle deferred; arm-only testing

### February 20: Final Readiness
- [ ] All lab tests passed?
- [ ] Protection circuits installed?
- [ ] Camera mount tested?
- [ ] Joint4 multi-position validated?
- [ ] Power box push button fixed/replaced?
- [ ] E-Stop button placed in dedicated panel location?
- [ ] Emergency procedures documented?
- [ ] Unit tests (129) passing?
- [ ] ROS2 latency within limits?
- [ ] RTC clock sync working on all RPis?
- [ ] Power supply stable under full load?

---

## Section 8: Logistics

### Equipment Checklist
- [ ] 2x Raspberry Pi 4B (arms)
- [ ] 1x Raspberry Pi 4B (vehicle - if motors ready)
- [ ] 2x OAK-D Lite cameras
- [ ] 2x IO boards
- [ ] Power supplies and batteries
- [ ] Power box — verify push button replaced/fixed (was faulty in Jan, stuck after closing)
- [ ] E-Stop button — verify mounted in dedicated panel location (was misplaced in Jan, caused accidental presses)
- [ ] CAN cables
- [ ] Tools for field adjustments
- [ ] Spare parts (diodes, fuses)

### Documentation to Bring
- [ ] This plan (printed)
- [ ] Motor protection guide
- [ ] Troubleshooting guide
- [ ] Quick reference for ROS2 commands

### Data Collection Requirements for February Trial

**CRITICAL:** January trial had MISSING data that prevented root cause analysis of several issues. February trial MUST capture the following:

#### 🟢 Well-Logged in January (Continue)
1. **ROS2 Node Logs** - All nodes logging to timestamped files
   - `yanthra_move_node_*.log` - Pick attempts, success/failure, coordinates
   - `cotton_detection_node_*.log` - Detection latency, temperatures
   - `mg6010_controller_node_*.log` - Motor commands
   - `launch.log` - Session startup info

2. **Detection Images** - Timestamped with detections drawn
   - `detected_imgs/` - Visual record of what YOLO detected
   - `input_imgs/` - Raw camera frames

3. **Pick Performance Metrics** - Auto-logged by yanthra_move
   - Success rate, failure reasons, coordinates
   - Joint limit failures (J4, J5)
   - [0,0,0] bug occurrences

4. **Temperature Monitoring** - Logged every 30s
   - Camera temps (validated: 45-61°C range)
   - Motor temps (if available via CAN)

#### 🔴 MISSING in January (CRITICAL to Add)

5. **ARM_client / MQTT Communication Logs**
   - START logging ARM_client stdout/stderr to file
   - Log all MQTT publish/subscribe events with timestamps
   - Log connection/disconnection events
   - Log message payloads (arm status, vehicle commands)
   - **Why:** ARM_client crashed (exit code 2) - NO logs to diagnose

6. **System-Level Logs**
   - `/var/log/syslog` - Copy to session directory at end
   - `journalctl -u ssh.service` - SSH service events
   - `dmesg` - Kernel messages (USB, network issues)
   - **Why:** Right Arm SSH issues - NO system logs captured

7. **Network Connectivity Logs**
   - WiFi signal strength over time (`iwconfig wlan0` every 30s)
   - Ping RTT to vehicle/laptop (`ping -i 30`)
   - SSH connection attempts (success/failure)
   - **Why:** Right Arm had connectivity problems - NO diagnostic data

8. **EE Activation Duration Logs**
   - Log GPIO activation timestamp + duration for EACH pick
   - Log EE timeout events (>1s is abnormal)
   - **Why:** Field notes mention "10-15s timeouts" - NO duration logs to validate

9. **Compressor Pressure/State Logs**
   - Log compressor GPIO state changes with timestamps
   - Log pressure sensor readings (if available)
   - **Why:** EE timeouts may correlate with pressure drops - NO data

10. **Pre-Failure Baselines**
    - Capture system logs BEFORE testing starts
    - Log motor temperatures at startup
    - Log initial calibration checks
    - **Why:** Vehicle motors burnt - NO pre-failure data to analyze

#### 📋 Automated Data Collection Script Needed

Create `scripts/field_trial_logging.sh`:
```bash
# Run alongside ROS2 launch
# - Tail ARM_client logs
# - Monitor network (ping, iwconfig)
# - Collect system logs at end
# - Package all logs into timestamped archive
```

**Owner:** Uday
**Deadline:** February 20 (before field trial)

#### 📊 Post-Trial Data Validation Checklist

Before leaving field site, verify ALL data collected:
- [ ] ROS2 logs present for all sessions
- [ ] Images captured (input + detected)
- [ ] ARM_client logs exist and non-empty
- [ ] System logs copied from /var/log
- [ ] Network diagnostic logs present
- [ ] All logs archived with timestamps
- [ ] Backup copy created on separate device

---

## Appendix A: January 2026 Field Visit Summary

**Dates:** January 7-12, 2026 (Vehicle), January 11-12, 2026 (Left Arm), January 20, 2026 (Right Arm)

**Data Collected:** 125 MB, 1,593 files across 92 sessions (59 left arm, 19 right arm, 14 vehicle)

### Overall Performance Statistics (Comprehensive Analysis - Feb 4, 2026)

**LEFT ARM (Primary Test Platform - 59 sessions)**
- **Sessions with picks:** 34 sessions
- **Total attempts:** 766
- **Success rate:** 85% (655 picked)
- **[0,0,0] bug:** 3% (30 occurrences)
- **Reachability failures:** 10% (78 combined J4+J5 limits)
- **Testing conditions:** Controlled/closer cotton placement (hypothesis)

**RIGHT ARM (Limited Testing - 19 sessions)**
- **Sessions with picks:** 9 sessions
- **Total attempts:** 255
- **Success rate:** 34% (88 picked)
- **[0,0,0] bug:** 10% (28 occurrences)
- **Reachability failures:** 54% (139 combined J4+J5 limits)
- **Testing conditions:** SSH/MQTT connectivity issues limited testing; team focused on left arm
- **Root Cause of Poor Performance:** Network connectivity problems (SSH drops, MQTT disconnections), NOT calibration or mechanical issues

**COMBINED (Both Arms)**
- **Total attempts:** 1,021
- **Overall success rate:** 73% (743 picked)
- **[0,0,0] bug rate:** 5.7% (58 occurrences)
- **Reachability failures:** 21% (217 occurrences)

**CRITICAL INSIGHT:** LEFT ARM shows 3x better performance than RIGHT ARM. Root cause identified:
1. RIGHT ARM suffered from SSH/MQTT connectivity issues — team focused testing on left arm
2. LEFT ARM was tested more extensively in controlled positions
3. Right arm's poor performance is NOT a calibration or mechanical issue

**Session A (documented in Jan Plan):** Represents WORST-CASE field conditions (21.8% success, 11.3% [0,0,0] bug in that session, 62.4% reachability failures). Overall [0,0,0] rate across all sessions: 5.7%.

### Temperature Validation
- **Camera:** 45.8°C → 61.3°C over 1.4 hours (logged every 30s)
- Validates field notes claim of ~59°C
- No thermal shutdowns observed

### Issues Discovered from Log Analysis
- ✅ **Detection [0,0,0] bug:** 5.7% overall (3-15% depending on conditions) - ROOT CAUSE TRACED (Feb 16): DepthAI stereo failure → unvalidated zero coords → TF transform to valid-looking position. FIXED: `depthai_manager.cpp:convertDetection()` returns `std::optional`, skips zero coords.
- ❌ **Position out of reach:** 21% of attempts (dominant failure mode on RIGHT ARM: 54%)
- ❌ **ARM_client crashed** with exit code 2 - NO LOGS to diagnose
- ⚠️ **border_skip:** 6 cotton rejected at image edges
- ⚠️ **not_pickable:** 10 cotton (mostly at right edge x > 0.77)
- ⚠️ **Right Arm SSH/MQTT issues:** Testing stopped early - NO system logs

### Data Quality Assessment
**✅ Well Logged:**
- ROS2 node logs (all sessions)
- Detection images (1,016 files with timestamps)
- Pick performance metrics (success/failure/reasons)
- Temperature monitoring (camera)
- EE activation counts

**🔴 MISSING (Critical Gaps):**
- ARM_client / MQTT communication logs
- System logs (/var/log/syslog, journalctl, dmesg)
- Network connectivity logs (WiFi signal, ping, SSH events)
- EE activation duration logs (no way to validate "10-15s timeout" claim)
- Compressor pressure/state logs
- Pre-failure vehicle motor data

**Full Analysis:** `docs/project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md` (lines 843-872 for Session A)
**Data Location:** `/mnt/c/Users/udayakumar/Downloads/jan_fieldtrial/jan_fieldtrial/`

---

## Appendix B: Reference Documents

| Document | Purpose |
|----------|---------|
| `FIELD_VISIT_REPORT_JAN_2026.md` | January visit analysis |
| `VEHICLE_MOTOR_ALTERNATIVES_AND_PROTECTION.md` | Motor solutions |
| `FOV_IMPROVEMENT_TASKS.md` | Camera/Joint4 improvements |
| `VEHICLE_STEERING_AND_AUTONOMY_DESIGN.md` | Differential drive design |

---

## Section 9: Unresolved Technical Issues - Root Cause Analysis

### 9.1 Joint3 Phi Compensation - Root Cause Not Verified

**Current State:** Zone-based compensation implemented but root cause not physically verified.

**Observed Problem:**
| Phi Angle Range | Observed Behavior | Current Compensation |
|-----------------|-------------------|----------------------|
| 0° - 50° | Arm goes **BELOW** cotton | +0.014 rot (+5°) |
| 50° - 60° | Arm is **CORRECT** | 0.0 |
| 60° - 90° | Arm goes **ABOVE** cotton | -0.014 rot (-5°) |

**Hypothesized Root Cause:** Camera pitch angle in URDF (45°) doesn't match actual physical mounting.
- J5 (radial distance) is accurate at all angles → rotation-invariant
- Only J3 (phi/rotation) is wrong → rotation-sensitive
- Error direction flips based on phi angle → matches pitch error geometry

**How to Verify:**
1. Set J3 to 0° (arm horizontal)
2. Use spirit level + protractor on camera mount
3. Compare measured angle to URDF value (45° = 0.785398 rad)
4. If different → Update URDF, may remove need for compensation

**Reference:** `docs/analysis/J3_PHI_ANGLE_ERROR_ANALYSIS.md`

### 9.2 L3 (Joint3) PID Tuning

**Current State:** Default PID values, no field-specific tuning.

**Observed Issues:**
- L3 overheats in 10-15 min fighting gravity
- CG imbalance causes excessive motor effort
- Oscillation/overshoot not characterized

**PID Tuning Procedure:**
1. Step response test: Command L3 from 0° to -45°
2. Measure: Rise time, overshoot, settling time, steady-state error
3. Tune: Start low P, increase until oscillation, add D to dampen, add I for steady-state
4. Repeat at multiple phi angles (0°, 30°, 60°)

### 9.3 L5 Hardware Offset - Why +10mm Needed in Field

**Observed Issue:** From Jan 2026 field notes:
> "L5 was not reaching cotton in some places; +10mm offset added on field"

**Current Config:** `joint5_init/hardware_offset: 0.290` (290mm)
**Implied Correct Value:** 300mm (if +10mm fix is right)

**Possible Causes:**
1. Hardware offset incorrect (physical measurement needed)
2. URDF kinematics error (link lengths don't match physical arm)
3. Depth camera systematic bias (~10-25mm at 500mm range)
4. Camera position in URDF doesn't match physical mounting

**How to Verify:**
1. Move L5 to motor_position = 0
2. Measure physical distance from yanthra_link origin to EE tip
3. This should equal hardware_offset (290mm or 300mm?)

---

**Document Status:** Active planning document
**Last Updated:** February 16, 2026
**Next Review:** February 20, 2026 (Final readiness check)

---

## Section 10: Field Trial Results (February 26, 2026)

**Date:** February 26, 2026
**Scope:** Arm1 only (arm2 hardware not available), stop-and-pick mode, 1-2 cotton rows
**Code:** Feb 25 build (commit fcadd3b3)
**Duration:** ~12:00-16:30 IST (RPi clocks drifted ~1.5h, logged as 12:01-15:10)
**Provisioning:** Morning only (vehicle FAILED 11/12, arm FAILED 8/9)
**Full Report:** `docs/project-notes/FIELD_VISIT_REPORT_FEB_2026.md`

### Key Results

| System | Status | Key Metric |
|--------|--------|------------|
| **Arm1 Picking** | ⚠️ LOW | 26.7% success (315/1181 attempts) |
| **Detection** | ✅ Working | 34-93ms avg latency, 0 XLink errors |
| **J4 Multi-Position** | ✅ Active | 5 positions scanned, 755 scan events |
| **Arm Motors** | ✅ Healthy | 100% health, 37-42C, 0 CAN errors |
| **MQTT Chain** | ✅ Solid | 158 starts, 931 status msgs, 0 disconnects |
| **ODrive Drive** | ❌ CRITICAL | All 3 motors stalling repeatedly, 9 crashes |
| **Steering Left** | ❌ DEGRADED | Error code 8, 76C, health=0.6, sluggish |
| **Data Collection** | ✅ Good | 1,849 arm files + 78 vehicle files captured |

### Critical Issues Found

1. **ODrive Motor Stalls (CRITICAL):** All 3 drive motors (front, left_back, right_back) show persistent STALL errors (0x04000000/0x00000100) across ALL 9 vehicle sessions. Auto-recovery → re-stall loop. drive_left_back physically stuck in some sessions. Vehicle still drove intermittently but crashed 9 times from ODrive errors.

2. **Cotton Out of Reach (HIGH):** Plants grew since January. 97% of pick failures (841/866) are workspace violations: 460 TOO FAR, 286 too far RIGHT, 62 too far LEFT. Vehicle couldn't position close enough (ODrive issues + row geometry). Pick success rate dropped from 85% (Jan left arm) to 26.7%.

3. **Steering Left Overheating (HIGH):** steering_left motor (MG6012-i6, CAN 0x3) persistent error code 8, temp peaked 76C (normal: 38-42C), health dropped to 0.6. Physically sluggish.

4. **Zero Spatial Coordinates (MEDIUM):** 503 zero spatial detections (17% of raw) vs 3% in January. Stereo depth failures elevated despite normal lighting. Fix in code catches these, but rate increase warrants investigation.

### What Worked Well
- MQTT communication chain (vehicle→arm) was rock solid
- J4 multi-position scanning operational (5 positions)
- Detection system stable (OAK-D, USB 3.0, 0 XLink errors)
- Arm motors all healthy (0 CAN errors)
- Field trial logging script captured comprehensive data
- ARM_client MQTT logs now captured (was missing in Jan)

### Comparison to January
| Metric | Jan 2026 (Left Arm) | Feb 2026 (Arm1) | Trend |
|--------|---------------------|-----------------|-------|
| Pick attempts | 766 | 1,181 | ↑ More cycles |
| Success rate | 85% | 26.7% | ↓↓ Workspace issue |
| Workspace violations | 10% | 73% | ↑↑ Cotton too far |
| [0,0,0] detections | 3% | 17% | ↑ Stereo failures |
| Border filtered | 57 | 453 | ↑ More edge cotton |
| MQTT issues | Unknown | 0 disconnects | ✅ Fixed |
| Vehicle motors | 6/6 DEAD | Stalling/degraded | Partial improvement |
| Data quality | Missing key logs | Comprehensive | ✅ Major improvement |
