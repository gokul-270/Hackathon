# January 1st Week Field Trial Plan (2026)

**Target Date:** January 7-8, 2026 (CONFIRMED)  
**Deadline for Prep:** January 6, 2026  
**Created:** November 26, 2025  
**Last Updated:** January 22, 2026
**Overall Oversight:** Manohar  
**Platform:** Raspberry Pi 4B

---

## Executive Summary

Prepare the Pragati cotton-picking robot for its first comprehensive field trial. This plan addresses mechanical, electrical, electronics, and software readiness across all subsystems.

**SCOPE DECISION:** 2 arms + vehicle with **new MG6010 motors** (replacing ODrive due to expo demo issues). **Vehicle will operate with 2 working drive motors (back wheels) in degraded mode - system configured to handle this.**

---

## High-Level Task Overview

### Dec 15, 2025 Review Addendum (New/Updated Critical Tasks)
These items were added/clarified during the Dec 15 review and are considered field-critical unless marked otherwise.

- Vehicle: 45° slope test (plan + execute), off-ground test SOP (stands/rollers), 6-motor full-load test, battery peak/steady current measurement, electrical E-STOP test, motor failure recovery drill (software + electrical), steering mechanical stopper, 500kbps validation with real wire lengths + new connectors, MCB ordering (2x) + temporary reuse from expo, final vehicle QC signoff.
- Arm/EE: L5 end-effector support sheet follow-up for corrected CG arm (mounting readiness), 8–10hr camera+detection soak (no arm motion), 8–10hr arm motion + reaching-point accuracy soak.
- Detection: Fix misleading coordinate axis labels in logs/comments (FLU vs left/right/up/down/depth) to prevent “negative depth” confusion; confirm coordinate conventions end-to-end; confirm field model selection after retraining.
- Pneumatics/Collection: Generator↔compressor power compatibility test, handheld pressure spec/options, bucket+L4 collection concept.

### Dec 29, 2025 Updates (Latest)
- ✅ **YOLOv11 timing issue RESOLVED**: Intermittent 0 detections were timeout-related; fixed by increasing timeout values
- ✅ **Camera USB 3.0 FIXED**: Two boards now working with proper USB 3.0 (good for each arm)
- ✅ **Camera post-reboot reliability**: Improved with latest software updates
- ⚠️ **Vehicle Drive Motor Issue**: One drive motor not powering on properly; will use 2 working back wheel motors for field trial

### Critical Blockers (Must Fix First)
| Task | Owner | Deadline | Status |
|------|-------|----------|--------|
| H-Bridge Current Limit | Joel | Dec 12 | 🟢 FIX CONFIRMED (2.6A limit, boards being made) |
| E-STOP Not Working | Joel + Gokul | - | 🟡 NICE-TO-HAVE |

### Recently Completed (moved from blockers)
- ✅ pigpiod Auto-Start (Dec 2)
- ✅ First Trigger After Reboot (Dec 2)
- ✅ Temperature Monitoring - camera & motor (Dec 5)
- ✅ WiFi Auto-Reconnect (Dec 10)
- ✅ **Unified Build System (RPi + Local)** (Dec 12)
- ✅ **Workspace Cleanup & Archiving** (Dec 12)

### Mechanical Tasks (Owner: Dhinesh)
| Task | Status | Deadline |
|------|--------|----------|
| Height Adjustment (5ft) | ✅ DONE | - |
| **L3 CG Temp Fix (expo arm)** | ✅ READY for testing | - |
| L3 CG Proper Fix + 2 NEW arms | 🔴 PENDING | **Dec 26** |
| Arms placement in machine | 🔴 PENDING | **Dec 26** |
| ~~L4 Belt Issue~~ | ✅ Will be fixed in new arms | Dec 26 |
| URDF Correction (2 ARM) | ✅ VALIDATED | - |
| Joint3 Thermal Fix | Deferred (after CG) | Dec 23 |

### Electrical/Electronics Tasks (Owner: Joel)
| Task | Status | Deadline |
|------|--------|----------|
| IO Boards (H-bridge patched) | 🟢 FIX CONFIRMED, 4 boards tested and ready | Dec 12 |
| GPIO Pins Validation | ✅ DONE | - |
| ADC for Joystick (basic) | ✅ WORKING (🟡 nice-to-have for field) | - |
| RTC for Clock Sync | 🟡 PARTIAL | Dec 19 |

### Software & AI Tasks (Owner: Uday)
| Task | Status | Deadline |
|------|--------|----------|
| CAN Baud Rate 500kbps Upgrade | ✅ Vehicle + arm tested (table-top, 1hr stable w/ feedback) | Dec 15 |
| Error Handling Enhancement | 🟢 LOW (placeholders) | Post-trial |
| AI Model YOLOv8 → v11 | 🟡 Soak test in progress; intermittent 0-detection issue under debug | Dec 26 |
| Camera 3.0 + 1hr Test | ✅ DONE (Dec 4) | - |
| Camera USB3 link (new boards) | 🔴 USB3 showing as USB2 on most boards (needs bring-up/debug) | Dec 18 |
| Camera post-reboot launch reliability | 🔴 Camera shows in `lsusb` but sometimes not accessible when launching our code | Dec 18 |
| SSD-Based Logging | ✅ DONE (SSD in use) | - |
| Smart Polling Validation | ✅ IMPLEMENTED | - |
| Vehicle Control Code | ✅ COMPLETE (Dec 5) | - |

### Vehicle Integration Tasks (Owner: Gokul)
| Task | Status | Deadline |
|------|--------|----------|
| **6-Motor Vehicle Test (standalone)** | ✅ DONE (Dec 8) | - |
| **Vehicle CAN + Table Top Tuning** | ✅ DONE (Dec 9, Gokul) | - |
| **6-Motor ROS2 Motor Node Test** | ✅ DONE (table-top, Dec 12) | - |
| **Motor Full-Load Bench Test** | 🟡 Check with Dhinesh/Nadimuthu | Dec 12-15 |
| **Joint4 Drift Test (ARM)** | ✅ RESOLVED (hardware - shaft coupling tightened) | Dec 10 |
| Vehicle with new motors assembled | ✅ Received at office (Dec 16) | Dec 16 |
| **Off-ground test SOP (stands/rollers)** | ✅ DONE (rollers/stands received Dec 16) | Dec 16 |
| **Steering Wheel Limit Integration** | 🔴 PENDING | Dec 18 |
| ~~Motor Controller Architecture~~ | ✅ DECIDED (Hybrid) | - |
| Start & Shutdown Testing | ✅ DONE (ARM_client MQTT Dec 2) | - |
| Joystick 45-Degree Issue | 🟡 NICE-TO-HAVE for field | - |
| E-STOP Integration | 🟡 NICE-TO-HAVE for field | - |
| Arm-Vehicle MQTT Coordination | ✅ TESTED (Dec 2) | - |
| ~~IMU Integration~~ | ❌ NOT IN THIS TRIAL | - |

### Testing & Validation Tasks
| Task | Status | Deadline |
|------|--------|----------|
| ROS1 vs ROS2 Code Review | ✅ DONE (docs exist) | - |
| **Pre-deployment Validation Script** | ✅ CREATED (Dec 10) | - |
| Two-Arm Testing | 🔴 REQUIRED | Dec 29 |
| ROS2 Latency Testing | 🔴 REQUIRED | Dec 23 |
| **Long-Run Validation Tests** | 🟡 IN PROGRESS (1 of several tests done) | Dec 29-30 |
| Unit Tests (bottom-up) | 🟡 RUN EXISTING | Dec 15 |

---

## Current Status (January 2, 2026)

**Summary:** All critical long-run tests PASSED. YOLOv11 timing fixed, Camera USB 3.0 working. **5 days to field trial (Jan 7-8).** Main remaining item: **Two-arm integration test.**

**Open Issues / Risks:**
- ✅ **YOLOv11 timing issue RESOLVED** - Fixed by increasing timeout values
- ✅ **Camera USB 3.0 FIXED** - Two boards now working with proper USB 3.0
- ✅ **Camera post-reboot reliability IMPROVED** - Latest software updates resolved accessibility issues
- ⚠️ **Vehicle Drive Motor**: One motor not powering on; will operate in degraded mode with 2 back wheel motors (system already configured for this)
- ⚠️ Uncommitted changes in vehicle motor configs (transmission factors, directions updated)

**Pending Hardware Validation / Integration:**
- ⚠️ Motor/joint operation - re-validate on assembled vehicle (6-motor ROS2 node)
- ⚠️ Spatial accuracy - needs field validation
- ⚠️ 2-arm integration (Dec 29)
- ⚠️ Vehicle + arm integrated testing (vehicle received at office)

**Recent Completions (Dec 23-29):**
- ✅ Extended OAK-D diagnostics (CPU/memory/XLink error tracking)
- ✅ Improved cotton detection shutdown (reduced from 2.5s to 0.7s)
- ✅ Dynamic EE prestart mode with 5+ hour endurance testing (2246 cycles)
- ✅ Auto-configure RPi bashrc with ROS2 sourcing on sync
- ✅ Vehicle transmission factors updated and single steering changes
- ✅ Build timestamps added to vehicle control node
- ✅ Motion controller improvements for EE timing coordination
- ✅ **YOLOv11 timing issue RESOLVED** - No more intermittent 0 detections
- ✅ **Camera USB 3.0 FIXED** - Two boards working properly for arm deployment
- ✅ **Long-Run Test #1 PASSED** - Software endurance test, 5+ hours, 966 cycles (Dec 29)
- ✅ **Long-Run Test #2 PASSED** - 7-8hr camera+detection soak (Jan 2)
- ✅ **Long-Run Test #3 PASSED** - 7-8hr arm motion soak (Jan 2)

*See Appendix A for detailed completion history*

---

## Section 1: Mechanical (Owner: Dhinesh)

### 1.1 Height Adjustment - ✅ DONE
### 1.3 L4 Belt Issue - ✅ Will be fixed in new arms (Dec 26)
### 1.4 URDF Correction (2 ARM) - ✅ VALIDATED

### 1.2 L3 CG Issue (Heat Problem) - 🔴 TWO-PHASE FIX
- **Issue:** L3 Center of Gravity not maintained → causing heat issue
- **Phase 1 (Temporary):** ✅ Quick CG fix on existing arm - READY for testing
- **Phase 2 (Proper):** Full CG fix on 2 NEW arms by **Dec 26**
- **Owner:** Dhinesh

### 1.5 Joint3 Thermal Fix - 🟡 DEFERRED
- **Issue:** Joint3 overheating at certain park positions
- **Status:** Deferred pending CG fix
- **Deadline:** Dec 24

---

## Section 2: Electrical/Electronics (Owner: Joel)

### 2.2 All GPIO Pins Validation - ✅ DONE (Dec 4)
### 2.3 ADC for Joystick - ✅ BASIC WORKING (fine-tuning if needed)

### 2.1 IO Board on RPi - H-Bridge Fix - 🟢 FIX CONFIRMED
- **Issue:** H-bridge tripping at low current → end effector not running
- **H-Bridge Fix (Dec 10):**
  - Electronics team confirmed fix working
  - Current limit: trips at 3A, safe up to 2.6A (sufficient for end effector)
  - Board 1: Fix applied, being dispatched
  - Board 2: Same fix being applied
- **Action:** Install boards when received, test end effector
- **Deadline:** Dec 12

### 2.4 RTC for Clock Sync - 🟡 PARTIAL
- **Issue:** Can READ but CANNOT SET time on RTC
- **Action:** Debug RTC write issue
- **Deadline:** Dec 19

---

## Section 3: Collection & Pneumatics

### 3.1 Collection System - 🟡 CONCEPTS & TESTING
- **Action:** Cotton collection concepts and tests
- **Deadline:** Dec 23

### 3.2 Compressor - 🔴 PENDING
- **Test command:** `pigs w 18 1` (ON) / `pigs w 18 0` (OFF)
- **Deadline:** Dec 15

### 3.3 End Effector - ✅ LOAD TESTED
- **Status:** Verified by Gokul: no tripping up to ~3.5A
- **Next:** Integrate with corrected-CG arm and collection flow
- **Deadline:** Dec 18

---

## Section 4: Software & AI (Owner: Uday)

### Completed ✅
- 4.1 Error Handling - ✅ LOW PRIORITY (post-trial)
- 4.3 Camera 3.0 Testing - ✅ DONE (Dec 10, 4/4 tests passed)
- 4.4 SSD-Based Logging - ✅ DONE (232GB SSD)
- 4.5 Smart Polling - ✅ IMPLEMENTED
- 4.7 CAN 500kbps - ✅ Vehicle + arm tested (table-top 1hr stable w/ feedback) (Dec 17)
- 4.8 Unified Build System - ✅ DONE (Dec 12)

### 4.2 AI Model YOLOv8 → v11 - ✅ COMPLETED
- **Status:** ✅ **RESOLVED** - Timing issue identified and fixed by increasing timeout values
- **Validation:** No more intermittent 0 detections; stable performance confirmed
- **Sub-owner:** Shwetha
- **Full integration deadline:** Dec 26 ✅ **COMPLETED EARLY**

### 4.2B Shwetha - Detection Tasks - ✅ CORE COMPLETE
||| Task | Status |
|||------|---------|
||| YOLOv8 → v11 upgrade | ✅ DONE (timing issue fixed) |
||| 7-8hr camera-only soak | ✅ PASSED (Jan 2) |
||| 7-8hr arm motion soak | ✅ PASSED (Jan 2) |
||| Non-pickable detection | 🟡 Validate in field |
||| Camera FOV validation | 🟡 Validate in field |

### 4.6 Joint4 Drift Test - ✅ RESOLVED (Dec 10)
- **Resolution:** Hardware fix - shaft coupling tightened
- **Status:** Ready for pick cycle testing

### 4.9 Camera USB3 link (new boards) - ✅ RESOLVED
- **Status:** ✅ **FIXED** - Two boards now working with proper USB 3.0 enumeration
- **Impact:** Good for each arm deployment
- **Resolution:** Hardware/board-specific issue resolved

---

## Section 4B: Production Issues to Fix

### Completed ✅
- 4B.1 First Trigger After Reboot - ✅ FIXED (Dec 2)
- 4B.2 Temperature Monitoring - ✅ DONE (Dec 5, camera + motor)
- 4B.3 pigpiod Auto-Start - ✅ DONE (Dec 2)
- 4B.4 WiFi Auto-Reconnect - ✅ FIXED (Dec 10)
- 4B.5 Camera Exposure Tuning - ✅ DONE
- 4B.6 Duplicate Cotton Positions - ❌ DEFERRED (post-trial)

### 4B.7 Thermal Overheating (Joint3) - 🔴 CRITICAL
- **Issue:** Joint3 overheats in 10-15min (fighting gravity)
- **Root cause:** Arm weight imbalance (L3 CG fix needed)
- **Short-term:** Add active cooling fan
- **Demo protocol:** 10min operation + 5min cooldown
- **Deadline:** Dec 20

---

## Section 4C: Arm-Side Requirements

### 4C.0 L5 End Effector Support Sheet (Corrected CG Arm) - 🔴 REQUIRED
- **Action:** Finalize L5 end-effector support sheet and confirm mounting readiness on corrected-CG arm
- **Owner:** Nadimuthu | **Deadline:** Dec 18


### Completed ✅
- 4C.3 URDF Validation - ✅ DONE (TF tree validated)

### 4C.1 Camera FOV Validation - 🔴 REQUIRED
- **Action:** Verify FOV coverage at 5ft height, check blind spots
- **Owner:** Shwetha | **Deadline:** Dec 15-18

### 4C.2 Joints Calibration - 🔴 REQUIRED
- **Action:** Fine-tune PID parameters, verify trajectories
- **Owner:** Gokul | **Deadline:** Dec 23-24

### 4C.4 Cotton Position Accuracy - 🔴 REQUIRED
- **Action:** Measure accuracy at various heights/distances
- **Target:** <10mm error | **Deadline:** Dec 25

### 4C.5 Joint Movement & Timing - 🟡 TUNING
- **Items:** Compressor timing, EE timing, joint speeds
- **Config:** `src/yanthra_move/config/production.yaml`
- **Deadline:** Dec 23

---

## Section 5: Vehicle Integration (Owner: Gokul)

### Completed ✅
- 5.0 Table Top 6-Motor Setup - ✅ Standalone tested (Dec 8), ROS2 node ✅ DONE (Dec 12)
- 5.1 Vehicle Motors Software - ✅ COMPLETE + HW TESTED (Dec 9)
- 5.2 Start & Shutdown Testing - ✅ DONE (Dec 2, MQTT)
- 5.6 Arm-Vehicle MQTT - ✅ TESTED (Dec 2, field validation Dec 22)
- 5.7 Motor Controller Architecture - ✅ DECIDED (Hybrid C++/Python)
- 5.5 IMU/Navigation - ❌ NOT IN THIS TRIAL

### 5.0B Motor Full-Load Bench Test - 🔴 REQUIRED
- **Add-on:** Capture battery peak current and steady draw during this test
- **Note:** One drive motor not powering on; will test with 2 working back wheel motors
- **Degraded Mode:** System configured with min_drive_motors: 2 - can operate normally with 2/3 drive motors

### 5.0C 45-Degree Slope Test - 🔴 REQUIRED
- **Action:** Define fixture + safety SOP, then execute 45° slope validation
- **Owner:** Dhinesh + Nadimuthu (mechanism) + Gokul (test) | **Deadline:** Dec 21

### 5.0D Vehicle Failure Recovery Drill - 🔴 REQUIRED
- **Action:** Define and practice recovery steps for motor failures (software reset/degraded mode) and electrical trips (MCB)
- **Owner:** Uday + Joel + Gokul | **Deadline:** Dec 20
- **Note:** System has degraded mode capability for motor failures - can continue with 2/3 drive motors
- **Action:** Define and practice recovery steps for motor failures (software reset/degraded mode) and electrical trips (MCB)
- **Owner:** Uday + Joel + Gokul | **Deadline:** Dec 20

- **Action:** Test 6 motors with full load, 30+ min continuous
- **Pass criteria:** Temp <70°C, no CAN bus-off
- **Deadline:** Dec 12-15

### 5.4B Steering Wheel Limit Integration - 🔴 PENDING
- **Action:** Integrate limit sensors to prevent over-rotation
- **Owner:** Gokul + Joel | **Deadline:** Dec 18

### 5.3 Joystick 45-Degree Issue - 🟡 NICE-TO-HAVE
### 5.4 E-STOP - 🟡 NICE-TO-HAVE

---

## Section 6: Code Review & Testing Requirements

### Completed ✅
- 6.1 ROS1 vs ROS2 Code Review - ✅ DONE (docs exist)
- 6.5 Pre-Deployment Validation Script - ✅ CREATED (Dec 10)

### 6.3 Two-Arm Testing - 🔴 REQUIRED
- **Action:** Run both arms simultaneously, check CAN conflicts
- **Deadline:** Dec 29

### 6.4 Unit Tests - 🟡 RUN EXISTING (129 tests)
- **Deadline:** Dec 19

### 6.6 Long-Run Validation - ✅ CORE TESTS COMPLETE

**Test #1: Software Endurance (Dec 29) - ✅ PASSED**
- **Duration:** 5 hours, 23 minutes (05:23:00 runtime)
- **Cycles Completed:** 966 operational cycles
- **Cotton Positions Processed:** 3,864 synthetic positions
- **System Health:** ✅ Excellent (62.8°C RPi temp, stable memory/CPU)
- **Detection Performance:** 100% success rate, 56.5ms avg latency
- **Issues Found:** None critical - DepthAI temp warnings (70-75°C, normal), motor unavailability (expected)
- **Result:** ✅ **PASS**
- **Documentation:** See `docs/LONG_RUN_TEST_ANALYSIS.md` for detailed analysis

**Test #2: Camera+Detection Soak (Jan 2) - ✅ PASSED**
- **Duration:** 7-8 hours
- **Configuration:** Camera and detection running continuously (no arm motion)
- **Result:** ✅ **PASS**

**Test #3: Arm Motion Soak (Jan 2) - ✅ PASSED**
- **Duration:** 7-8 hours
- **Configuration:** Arm motion + reaching-point accuracy
- **Result:** ✅ **PASS**

**Remaining Tests:**
- 🔴 Two-arm integration test (CRITICAL - required before field trial)
- 🟡 Full system integration long-run (if time permits)

**Optional Enhancement (if time permits):**
- 🟡 EE encoder feedback integration - See `docs/hardware/EE_MOTOR_ENCODER_ANALYSIS.md`
  - **Effort:** 2-3 days (mostly software)
  - **Benefits:** Motor running verification, stall detection, cotton capture confirmation
  - **Requirements:** GPIO pin verification on Robotics Board V1.2

### 6.7 ROS2 Latency Testing - 🔴 REQUIRED
- **Pass criteria:** No single hop >100ms, end-to-end <3s
- **Deadline:** Dec 23

---

## Section 7: Infrastructure & Build System

### 7.1 Cross-Compilation - ✅ DONE (Dec 12)
- **Solution:** Implemented `./build.sh rpi` mode using `cmake/toolchains/rpi-aarch64.cmake`.
- **Status:** Verified and merged.

### 7.2 RPi5 Option - 🟡 EVALUATE (Dec 15)
- **Status:** Pending hardware availability.

### 7.3 Build Distribution - 🟡 IN PROGRESS
- **Mechanism:** Single-node build/deploy is ready (`./build.sh rpi` + `install_rpi/`).
- **Gap:** Need strategy for multi-RPi setup (1 Vehicle RPi + N Arm RPis).
- **Next Step:** Reuse/extend an existing script in `scripts/deployment/` (instead of adding a new script) to handle multiple targets (e.g., `--vehicle`, `--arm-left`).
- **Deadline:** Dec 23

---

## Section 8: Installation Validation

### 8.1 Setup Script Issues - ✅ DONE (Dec 2-3, 2025)
- **Issue:** Current `setup_raspberry_pi.sh` missing some tools that were manually installed
- **Script location:** `setup_raspberry_pi.sh`
- **Major Updates Applied:**
  - ✅ SSH server auto-install if not present
  - ✅ Create system groups (gpio, spi, i2c) before adding user
  - ✅ Keep ros-jazzy-desktop (avoid missing packages)
  - ✅ Check if pigpiod already installed before source build
  - ✅ Create pigpiod systemd service if built from source
  - ✅ Skip DepthAI C++ source build (30+ min) - use apt packages instead
  - ✅ Add MCP2515 CAN HAT dtoverlay config (12MHz oscillator)
  - ✅ Create /etc/network/interfaces.d/ if missing (Ubuntu 24.04 netplan)
  - ✅ Use 'ip link' instead of deprecated 'ifconfig'
  - ✅ Auto-install CAN watchdog service
- **Commit:** c4eba101
- **Validation (Dec 3):**
  - ✅ Tested on separate RPi - installation successful
  - ✅ All services start correctly
  - 🟡 TODO: Test on additional SD cards for consistency

### 8.2 Known Missing Tools (to add to script)
**System tools:**
- `htop`, `iotop` - System monitoring
- `tmux` / `screen` - Session management
- `vim` / `nano` - Text editors
- `git-lfs` - Large file support
- `rsync` - File sync for deployment

**ROS2 tools:**
- `ros-jazzy-rqt*` - GUI tools
- `ros-jazzy-rviz2` - Visualization
- `ros-jazzy-tf2-tools` - TF debugging
- `ros-jazzy-ros2bag` - Data recording

**Development:**
- `gdb` - Debugging
- `valgrind` - Memory debugging
- `strace` - System call tracing

**Network:**
- `nmap` - Network scanning
- `iperf3` - Bandwidth testing
- `mtr` - Network diagnostics

---

## Section 9: Toolkit & Spare Parts

### 9.1 Vehicle Toolkit
**Hardware:**
- Spare MG6010 motors (3x total for arm/steering - shared pool)
- ⚠️ **NO spare drive motors** - handle with care
- Motor cables and connectors
- CAN bus terminators
- Joystick spare

**Tools:**
- Multimeter
- CAN bus analyzer (optional)
- Wire strippers, crimpers
- Allen keys (motor mounting)

### 9.2 Arm Mechanical Toolkit
**Hardware:**
- Spare belts (L3, L4)
- Spare bearings
- Motor mounting bolts
- End effector spare parts

**Tools:**
- Torque wrench
- Allen key set
- Grease/lubricant
- Measuring tape

### 9.3 Electrical Toolkit
**Hardware:**
- H-bridge driver spares
- GPIO cables
- Power connectors
- Fuses and fuse holders
- Relay modules

**Tools:**
- Soldering iron + solder
- Heat shrink tubing
- Electrical tape
- Wire crimpers
- Power supply tester

### 9.4 Infrastructure/Software Toolkit
**Hardware:**
- Spare RPi 4/5
- SD cards (32GB+, multiple)
- SSD drives
- USB 2.0 hubs
- USB cables (camera, serial)
- RTC module spare
- Ethernet cables
- WiFi router/hotspot

**Software (pre-loaded on SD):**
- Ubuntu 24.04 image
- ROS2 Jazzy pre-installed
- Pragati workspace built

---

## Section 10: Pre-Trial Checklist (Before Dec 30)

### Hardware
- [ ] 6 motors communicating per arm (MG6010)
- [ ] 2 cameras detecting cotton (>90% accuracy)
- [ ] Vehicle 6 motors working
- [ ] GPIO controls (compressor, E-stop, LEDs)
- [ ] End effector running (H-bridge ✅)
- [ ] Complete pick cycle (<3s)
- [ ] 30-min continuous without CAN errors

### Software
- [ ] Build on RPi (aarch64)
- [ ] Detection returns valid positions
- [ ] Joint states @ 10Hz
- [x] SSD logging ✅
- [ ] RTC clock sync

### Field Readiness
- [ ] Power supply stable under load
- [ ] Spare parts kit assembled
- [ ] Emergency procedures documented

---

## Testing Sequence (IMPORTANT)

**Integration order - each phase must pass before next:**
```
1. ARM TESTING (Dec 9-12, Dec 15)
   └── Expo arm with L3 CG temp fix → Joint4 drift → Pick cycles

2. VEHICLE TESTING (Dec 16-19)
   └── Vehicle with new motors assembled → Motor tests → Driving tests

3. VEHICLE + SINGLE ARM (Dec 22-24)
   └── Mount expo arm on vehicle → Integrated testing

4. VEHICLE + 2 ARMS (Dec 26, Dec 29-31)
   └── 2 new arms with proper CG fix → Full system testing
```

---

## Timeline Summary (Revised Dec 10)

**Note:** Weekends (Sat/Sun) are HOLIDAYS. Other holiday: Dec 25 (Christmas)

**Key Dates:**
- Dec 10: H-Bridge fix CONFIRMED (boards being dispatched)
- Dec 12: Farm visit dates must be finalized
- Dec 16: Vehicle with new motors assembled
- Dec 26: 2 new arms ready + proper CG fix + arms placement finalized

---

### Week 1: Dec 1-12 (Working days: Mon-Fri only)
**Theme:** Arm Testing Setup + Critical Blockers

| Day | Date | Gokul | Shwetha | Dhinesh | Joel | Uday |
|-----|------|-------|---------|---------|------|------|
| Thu | Dec 4 | 6-motor setup | ✅ Camera 1hr test | CG assessment | - | ✅ Motor arch, timing |
| Fri | Dec 5 | 6-motor setup | YOLOv8/v11 | CG temp fix | - | Code improvements |
| ~~Sat~~ | ~~Dec 6~~ | - | - | - | - | - | (Holiday) |
| ~~Sun~~ | ~~Dec 7~~ | - | - | - | - | - | (Holiday) |
| Mon | Dec 8 | ✅ 6-motor standalone | YOLOv8/v11 compare | ✅ CG temp fix DONE | - | Code fixes |
| Tue | Dec 9 | **Joint4 drift (ARM)** | YOLOv11 final checks | - | Board prep | ROS2 motor test |
| Wed | Dec 10 | ROS2 motor node test | Camera FOV validation | - | ✅ H-Bridge fix confirmed | Support |
| Thu | Dec 11 | Motor load test prep | Detection accuracy start | 2-arm prep | IO Board install | Arm testing |
| Fri | Dec 12 | Motor load test | Detection wrap-up | 2-arm prep | IO Board install | **Farm dates finalize** |

**Week 1 Remaining (Dec 10-12):**
- ⬜ 6-motor ROS2 motor node integration test (on assembled vehicle)
- ⬜ YOLOv11 final checks + non-pickable (Shwetha)
- ⬜ IO Boards dispatch + install
- ⬜ **Farm visit dates finalized (by Dec 12)**

---

### Week 2: Dec 15-19 (Working days: Mon-Fri)
**Theme:** Arm Pick Cycles + Motor Full-Load Test + Vehicle Assembly

| Day | Date | Gokul | Shwetha | Dhinesh | Joel | Uday |
|-----|------|-------|---------|---------|------|------|
| ~~Sat~~ | ~~Dec 13~~ | - | - | - | - | - | (Holiday) |
| ~~Sun~~ | ~~Dec 14~~ | - | - | - | - | - | (Holiday) |
| Mon | Dec 15 | Motor load test | Integration support | CG proper start | End effector test | Pick cycle test |
| **Tue** | **Dec 16** | **Vehicle assembled** | Integration support | 2-arm assembly | - | **ARM long-run test** |
| Wed | Dec 17 | Vehicle motor test | Integration support | 2-arm assembly | - | Vehicle integration |
| Thu | Dec 18 | Vehicle driving test | Integration support | 2-arm assembly | - | CAN 500kbps |
| Fri | Dec 19 | Vehicle driving test | Integration support | 2-arm assembly | - | Vehicle+arm prep |

**Week 2 Deliverables:**
- IO Boards installed, end effector working
- Pick cycle validated on expo arm
- Motor full-load bench test passed
- ARM long-run test (Dec 16)
- Vehicle with new motors assembled (Dec 16)

---

### Week 3: Dec 22-26 (Working days: Mon-Wed, Fri)
**Theme:** Vehicle + Single Arm Integration

| Day | Date | Gokul | Shwetha | Dhinesh | Joel | Uday |
|-----|------|-------|---------|---------|------|------|
| ~~Sat~~ | ~~Dec 20~~ | - | - | - | - | - | (Holiday) |
| ~~Sun~~ | ~~Dec 21~~ | - | - | - | - | - | (Holiday) |
| Mon | Dec 22 | **Vehicle+1 arm mount** | Integration support | 2-arm assembly | - | Vehicle+arm test |
| Tue | Dec 23 | Vehicle+arm test | Integration support | 2-arm assembly | - | Integration |
| Wed | Dec 24 | Joints calibration | Integration support | 2-arm assembly | - | Integration |
| ~~Thu~~ | ~~Dec 25~~ | 🎄 **CHRISTMAS** | - | - | - | - | (Holiday) |
| **Fri** | **Dec 26** | **2 new arms ready** | - | **Arms + CG fix DONE** | - | Arms placement |

**Week 3 Deliverables:**
- Vehicle driving tests passed (Dec 18-19)
- Vehicle + single arm integrated (Dec 22)
- Joints calibration started (Dec 24)
- 2 new arms with proper CG fix ready (Dec 26)

---

### Week 4: Dec 29-31 (Working days: Mon-Wed)
**Theme:** Long-Run Tests + Final Prep

| Day | Date | Activity | Notes |
|-----|------|----------|-------|
| ~~Sat~~ | ~~Dec 27~~ | (Holiday) | - |
| ~~Sun~~ | ~~Dec 28~~ | (Holiday) | - |
| Mon | Dec 29 | Vehicle + 2 arms mount + **Software long-run test #1 COMPLETED** | All hands |
| Tue | Dec 30 | Remaining long-run tests + Bug fixes | All hands |
| Wed | Dec 31 | Final system check, spare parts, pack | All hands |

**Week 4 Deliverables:**
- Vehicle + 2 arms integrated (Dec 29)
- ✅ **Software endurance test #1 PASSED** (Dec 29, 5+ hours)
- 🔴 Additional long-run tests (Dec 30)
- All bugs fixed (Dec 30)
- System packed for field (Dec 31)

---

### Field Trial: January 7-8, 2026 (CONFIRMED)
**Duration:** 2 days

| Day | Date | Activity |
|-----|------|----------|
| Tue | Jan 6 | Final prep + Travel |
| Wed | Jan 7 | Field testing Day 1 |
| Thu | Jan 8 | Field testing Day 2 |

### Critical Path
```
┌─────────────────────────────────────────────────────────────────────────┐
│ PARALLEL TRACKS (Dec 4-10)                                              │
├─────────────────────────────────────────────────────────────────────────┤
│ Track 1: Gokul    │ 6-Motor Setup → Joint4 Drift Test                   │
│ Track 2: Shwetha  │ Camera Validation → YOLOv8/v11 → Accuracy Baseline  │
│ Track 3: Dhinesh  │ L3 CG Temp Fix (1 arm)                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ H-Bridge Board (Dec 10) → Install (Dec 11-12) → End Effector (Dec 13)   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Pick Cycle Test (Dec 15) - requires: Joint4 OK + CG fixed + H-bridge    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Dhinesh: 2 NEW arms assembly (Dec 16-26, L4 belt fixed in new arms)     │
│ Gokul: Vehicle MG6010 integration (Dec 16-19)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ CAN 500kbps (Dec 18) → Joints Calibration (Dec 24) → Two-Arm (Dec 29)       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ Long-Run Tests (Dec 29-30) → Final Validation (Dec 30-31)               │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
                    Field Trial (Jan 5-9 or Jan 18+)
```

---

## Owners Summary

| Area | Owner | Items |
|------|-------|-------|
| Mechanical | **Dhinesh** | L3 CG, 2 new arms (L4 belt fixed), height |
| Electrical/Electronics | **Joel** | H-bridge, GPIO, RTC, IO board |
| Software & AI | **Uday** | All software, code review, testing, infra, integration |
| - Camera/Detection | Shwetha (sub) | YOLOv8/v11, camera testing (Uday backup) |
| - Vehicle/Navigation | Gokul (sub) | MG6010 motors, joystick ADC |
| **Overall Oversight** | **Manohar** | Review & approval |

---

## Key Decisions

1. **2 arms** for field trial (not 4)
2. **MG6010 motors** for vehicle (replacing ODrive)
3. **SSD logging** (not SD) for storage space
4. **YOLOv11 exploration** alongside v8
5. **Motor Controller Architecture** - ✅ DECIDED: Hybrid (C++ low-level + Python high-level)

---

## Risk Mitigation

1. **CAN Bus Saturation:** Smart polling implemented, upgrade to 500kbps REQUIRED for 2-arm operation
2. **Motor Overheating:** Temperature monitoring in place (max 70°C), L3 CG fix pending
3. **Detection Accuracy:** Testing YOLOv11 as potential upgrade from v8
4. **H-Bridge Current:** ✅ RESOLVED - Fix confirmed (2.6A safe, boards being made)
5. **ODrive Issues:** Mitigated by switching to MG6010 for vehicle
6. **Power Issues:** Ensure adequate battery/generator capacity for field operation

---

## Quick Reference Documents

| Document | Location | Purpose |
|----------|----------|--------|
| **Field Trial Cheatsheet** | `docs/FIELD_TRIAL_CHEATSHEET.md` | All launch/debug/trigger commands |
| **Long-Run Test Analysis** | `docs/LONG_RUN_TEST_ANALYSIS.md` | 5+ hour endurance test results & analysis |
| **Vehicle Control Comparison** | `docs/project-notes/VEHICLE_CONTROL_FUNCTIONALITY_COMPARISON.md` | ROS1→ROS2 comparison (merged Dec 5) |
| **Vehicle Motors Config** | `src/motor_control_ros2/config/vehicle_motors.yaml` | 6 vehicle motor setup + health monitoring |
| **Arm Motors Config** | `src/motor_control_ros2/config/production.yaml` | 3 arm motor setup |
| **Health Monitoring Bypass** | See `FIELD_TRIAL_CHEATSHEET.md` Section "🏥 Runtime Health Monitoring" | Field bypass commands |

---

## Addendum: Field Visit Notes (January 21, 2026)
These notes are based on the field visit performed on **January 21, 2026**, and are intended to feed into the next trial’s fixes + test plan.

**Overall summary (from discussion):**
- 5-hour run completed; camera and motor temperatures were reported stable (camera ~59°C, motors ~37–45°C).
- Electronics (CAN, EE, H-bridge) reported stable; no HW failures observed during the run (unlike the previous field visit).
- Picking performance/accuracy was still lower than the earlier “Nannilam” visit; many failures were due to FOV/non-pickable constraints and extraction issues.
- Collection performance was better than anticipated (in-built collection inside arm).

### A1) Vehicle / Drive
**Observation:** Before the trial, the team tried moving the vehicle on-road. It was slow, then the system was powered off and the vehicle was pushed manually. After that, the drive motors stopped movement and later were found burnt.

**Notes / hypotheses to validate (battery was disconnected):**
- If the wheels/motors were back-driven while motor leads remained connected to the driver/wiring, the motor can behave as a generator. Depending on the driver topology, this can:
  - create unexpected braking/drag, and/or
  - inject voltage/current into the driver/DC bus through internal diodes, and/or
  - create heating in motor windings if a low-impedance path exists (brake/short/fault condition).
- Independent of back-drive effects, “slow on road” can indicate high torque demand and sustained over-current (stall/near-stall) leading to thermal failure.

**Action items (next test):**
- Define a safe “push procedure”:
  - Validate free-wheel behavior with power removed (lift one wheel and spin test).
  - Confirm the motor/driver state when unpowered is truly high-impedance/coast (not brake/short).
  - If free-wheeling is not guaranteed, do not push with motor leads connected (or add an explicit disconnect strategy).
- Re-run vehicle drive test off-ground and on-ground with current/temperature monitoring and clear stop limits.

**Additional vehicle notes (from discussion):**
- Steering was not exactly 90°; steering angle/geometry needs verification. On loose soil, vehicle may “dig in” / drift into rows.
- Between-row spacing in field was inconsistent (reported ~800–900mm). Vehicle movement strategy needs to handle variability.
- Vehicle movement impacted the backside row (clearance/trajectory issue); review vehicle width vs row placement.
- One pin was found inside a roller (mechanical issue to inspect/root-cause).

### A2) Arm / End-Effector (EE)
**Observation:** Steering felt OK during manual pushing but not thoroughly tested.

**Observation:** L5 was not reaching cotton in some places; a +10mm offset was added on field to improve reach (not thoroughly validated).

**Observation:** EE sometimes ran for ~10–15 seconds. Hypothesis is that feedback was not received and it kept running until a timeout.

**Observation:** When cotton was close to arm/camera end-effector, EE did not run; start distance was reduced.

**Additional EE / extraction notes (from discussion):**
- Cotton size smaller than shell: in some cases the cotton is less than shell size, and the EE does not pick reliably.
- Cotton sticking to shell: EE is not able to completely extract cotton in one attempt.
- Shell stuck inside L5: shell can remain inside L5 and block subsequent cycles/picks until cleared.

**Action items (next test):**
- Re-validate reachability with the +10mm offset: pick success vs collisions vs “false reach”.
- Verify EE feedback/timeout logic: log “why EE is running” on every cycle (commanded start, expected stop condition, feedback received/timeout).
- Re-check start-distance and FOV constraints together: ensure “close cotton” still triggers EE when safe and visible.
- Add “shell jam” detection/handling to the test procedure (manual clearing step + log/jam counter).

### A3) Pneumatics / Collection (Compressor)
**Hardware used:** Dongcheng DEQ1200X2 / 50L.

**Observation:** In lab: compressor worked with generator at ~6 bar (start) → ~8 bar (stop).

**Observation:** On field: when pressure dropped below ~6 bar it attempted to start but failed, and generator showed overload. After fully releasing air to ~0 bar, it was able to start.

**Notes / hypotheses to validate:**
- Likely “restart under load/head pressure” issue (unloader/check valve/pressure switch behavior) + generator droop.
- Pressure switch screw adjustments may have impacted cut-in/cut-out and/or unloading behavior.

**Action items (next test):**
- Verify unloader function at cut-out (listen/confirm pressure release at stop).
- Repeat controlled test: stop at 8 bar, then attempt restart at 6 bar and record generator voltage/current behavior.
- Document pressure switch settings before/after field changes.

**Observation:** When shell entered inside arm, even at high pressure it stuck inside and did not push cotton out.

**Action items (next test):**
- Determine whether issue is pneumatic impulse/flow (valve Cv, hose restriction, local accumulator) vs mechanical jamming/adhesion.
- Add logging/measurement for solenoid open time and actual pressure at the end effector (if sensor exists).

### A4) Perception / Planning / Picking Performance
**Observation:** Many cotton positions were outside FOV / non-pickable / non-reachable; overall pick percentage was low.

**Observation:** Plants were overgrown with many leaves/branches and stem obstruction.

**Additional perception notes (from discussion):**
- False positives: sun reflections detected as cotton.
- Non-pickable classification: if stem is in front/occluding cotton, it often becomes non-pickable.
- FOV is a major limiter from images: cotton often needs to be manually pulled into FOV to attempt picking.
- Within FOV: picking is more reliable when cotton is well inside FOV; cotton near FOV border is frequently not picked.

**Evidence (logs/images to include in field-trial review):**
- Artifact set: `.../Downloads/Zoho WorkDrive/right_arm/`
- Note: These artifacts have timestamps around **January 20, 2026** (e.g., `DetectionOutput_2026-01-20_15-40-04.jpg`). Confirm whether this was pre-field testing or the same field visit timeline.

**FOV border / filtering effect (example):**
- Image: `.../right_arm/detected_imgs/DetectionOutput_2026-01-20_15-42-00.jpg`
- Cotton detection logs for the same timestamp show `border_skip` incrementing and `cotton_accepted=0` (i.e., detections exist but are skipped by the border filter). This supports the observation that cotton near the image border is frequently not picked.

**Reachability / Joint4 left-right limit (example):**
- Image: `.../right_arm/detected_imgs/DetectionOutput_2026-01-20_15-40-04.jpg` (detections present)
- Yanthra move log (same right_arm session): `.../right_arm/logs/2026-01-20-15-28-55-785713-ubuntu-desktop-2039/yanthra_move_node_2268_1768903151495.log`
  - Shows cam→arm transform producing arm-frame Y values `y=0.327` and `y=0.481` (positive).
  - Joint4 limits enforced as `[-0.125, 0.175]` meters.
  - Results in repeated `Joint4 (left/right) limit exceeded → Target too far RIGHT (Y positive)` and pick failures.

**Deep-dive quantitative analysis (right_arm logs, Jan 20 sessions):**
These metrics are extracted from the right_arm logs to understand *why* pick % is low (and what to optimize first).

**Session A (large run):** `.../right_arm/logs/2026-01-20-15-28-55-785713-ubuntu-desktop-2039/`
- Detection requests completed: **159**
- Detection latency (ms): p50 **69**, p90 **103**, max **120**
- Positions per request: 0-pos **79**, 1-pos **36**, 2-pos **28**, 3-pos **14**, 4-pos **1**, 5-pos **1**
- Detection classification totals (sum over frames): raw **312** = accepted **144** + border_skip **57** + not_pickable **111**
  - border_skip present in **49/160** frames (**30.6%**)
- Yanthra_move cycles: **148** cycle reports
  - cycles with no attempts (0 positions): **75**
  - cycles that failed with no motion (attempts>0 but motion=NO): **49**
  - cycles with motion and at least one success: **24**
- Pick attempts (per-cotton) parsed from yanthra_move: **133** attempts
  - picked: **29** (**21.8%**)
  - out_of_reach_joint4: **57** (**42.9%**)
  - out_of_reach_joint5: **26** (**19.5%**)
  - failed_pick: **15** (**11.3%**)
  - approach_failed: **6** (**4.5%**)
- Invalid/degenerate targets: **21/133** attempts had cam target exactly `[0.000,0.000,-0.000]`.
  - These account for **all** `failed_pick` (15) + `approach_failed` (6) in this session.
- Radial reachability (from `Polar: r=...` logs):
  - r stats: min **0.079**, p50 **0.748**, p90 **1.284**, max **1.440**
  - Using the reported reachable radial range (example in log: `[0.320, 0.670]` m), **73/133 (54.9%)** targets are *too far* and **21/133 (15.8%)** are *too close*.

**Session B (high success baseline):** `.../right_arm/logs/2026-01-20-14-39-11-930658-ubuntu-desktop-2043/`
- Attempts: **17** → picked **16**, out_of_reach_joint4 **1**, and **0** zero-target attempts
- r stats: min **0.361**, p50 **0.459**, max **0.521** (all within `[0.320, 0.670]` m)

**Key inference to validate:**
- The dominant limiter is *reachability*, driven mainly by radial distance `r` being out-of-range (Joint5) and left/right `θ` being out-of-range (Joint4).
- The `[0,0,0]` camera targets strongly suggest invalid depth/position outputs getting through; these should be treated as invalid detections in analysis and filtered/flagged in future work.

**Observation:** Extraction from shell was difficult; often required 2–3 triggers for same cotton.

**Observation:** Phi compensation added before the field trial improved results.

**Action items (next test):**
- Collect and review logs + captured images for non-pickable reasons (FOV vs reachability vs obstruction vs false positive).
- Add simple post-detection filters for sun glints and/or improve dataset for reflective backgrounds.
- Explicitly analyze “border-of-FOV” cases vs center-of-FOV cases; quantify failure rate by image location.
- Define a “field condition envelope” (max foliage/obstruction) where pick rate is expected to be acceptable.
- Evaluate FOV improvement concepts:
  - L4 dynamic behavior to increase usable FOV (if feasible without destabilizing picking).
  - Camera placement changes: consider camera being more independent of arm motion to preserve FOV.
- Field notes to keep in mind for next test site selection/expectations:
  - Row spacing inconsistency (~800–900mm).
  - Field visited: field/plot 659 (Swift variety was expected to have fewer branches, but it was not available for this test).

### A5) Launch / Networking / Reliability
**Observation:** Start signal was received only after some time. Team used manual triggers by logging into the RPi.

**Observation:** When auto-launched at boot using `scripts/launch/arm_launcher.sh`, the system did not receive a ROS2 topic that worked when launching manually.

**Notes / hypotheses to validate:**
- Environment mismatch between boot launch and manual shell (common culprits: `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, RMW/DDS config, missing sourcing, or network readiness at boot).
- Auto launch is via systemd (`systemd/arm_launch.service`) which does not source interactive shell profiles (e.g., `~/.bashrc`). If `ROS_DOMAIN_ID` is only set in `.bashrc`, the boot service may fall back to domain 0.
- `scripts/launch/arm_launcher.sh` currently exports `ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}` and `ROS_LOCALHOST_ONLY=1`. If the manual session uses a different domain ID (or if triggers originate from a different machine and localhost-only is enabled), topics will not match.
- `scripts/launch/arm_launcher.sh` runs `ros2 launch ...` in the foreground; any lines after that will not execute unless the launch is backgrounded.

**Action items (next test):**
- Define and run a “boot-to-trigger” validation:
  - Reboot, wait fixed time, then publish trigger topic and verify receipt.
  - Record `ROS_DOMAIN_ID`/`ROS_LOCALHOST_ONLY` for both boot and manual sessions.
  - Verify nodes/topics visibility on the same machine and from the operator machine.

**Observation:** MQTT disconnected mid-run and did not reconnect.

**Action items (next test):**
- Add explicit reconnect + resubscribe behavior and log disconnect/reconnect events with timestamps.

**Observation:** SSH did not connect to one arm even though it appeared connected to AP/router.

**Action items (next test):**
- Add a basic network health checklist: ping, ssh daemon status, IP conflict check, and a recovery path (reboot power-cycle sequence).

### A6) Next Trial Test Plan (Post-Jan-21)
Goal: convert the above observations into a small number of repeatable, measurable tests with clear pass/fail criteria.

**T0: Drive safety + thermal (must pass before field):**
- Free-wheel test with battery disconnected (lift wheel, spin) — verify no strong drag/brake.
- Short push test protocol (if push is required): confirm motor leads/driver state is safe for back-driving.
- Controlled drive test (off-ground → on-ground): log current draw and motor temps; stop if “slow but high current” persists.

**T1: Boot-to-trigger reliability (must pass before field):**
- Reboot, wait fixed time, publish start trigger, verify receipt (repeat N=10).
- Record and lock: `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, and publisher machine/location (same RPi vs operator laptop).

**T2: MQTT resilience (must pass before field):**
- Force network drop (AP reboot / wlan down-up) and verify MQTT reconnect + resubscribe within target time.
- Validate that “start” and “status” messages survive disconnect/reconnect without manual intervention.

**T3: Compressor restart-under-pressure (must pass before field):**
- Cycle test: 8→6 bar restart, repeat 3 times; record generator overload events.
- Confirm unloader/check valve behavior; revert pressure switch adjustments if unloading is impacted.

**T4: EE ejection / shell release (must pass before field):**
- Repeat ejection test across orientations; record failure rate.
- If stuck: isolate pneumatic flow vs mechanical jam (stepwise increase: impulse duration → local accumulator → valve Cv / line restriction).

**T5: Picking performance breakdown (field test):**
- For each attempted pick, log categorical outcome: not-in-FOV, not-reachable, blocked, false positive, EE failure, extraction failed, success.
- Capture representative images for false positives (sun reflections) and non-pickable cases.
- Post-run review: correlate key failure categories with evidence in logs and images:
  - `cotton_detection_node` counts: raw vs cotton_accepted vs border_skip vs not_pickable.
  - `yanthra_move` failures: joint limit exceeded / out-of-reach, approach failed, cycle completion reports.
  - Spot-check “border-of-FOV” images (e.g., `DetectionOutput_...`) against border_skip behavior.

---

## Appendix: Previously Solved Issues
- ✅ End Effector Timing - Added `ee_post_joint5_delay` parameter
- ✅ USB Speed Mode - Force USB 2.0 mode (`dai::UsbSpeed::HIGH`)
- ✅ GPIO Compressor Pin - Changed from GPIO 24 to GPIO 18
- ✅ USB 3.0 Camera SSH crash - Solved by USB 2.0 mode
- ✅ Code Simplification - GPIO, Transform, Detection cleanup done
- ✅ Vehicle motor namespace - Fixed YAML structure (Dec 5)
- ✅ Service connection timeout - Increased 2s→10s (Dec 5)
- ✅ IMU false positive - Now verifies hardware (Dec 5)
- ✅ Control loop warning spam - Changed to WARN_ONCE (Dec 5)
