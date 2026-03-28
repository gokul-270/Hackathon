# Field Visit Report - January 2026

**Visit Dates:** January 7-12, 2026 (Vehicle), January 11-12, 2026 (Left Arm), January 20, 2026 (Right Arm)
**Location:** Field Site (pragati11)
**Next Visit:** February 25, 2026

---

## Executive Summary

### Key Findings
| System | Status | Issues |
|--------|--------|--------|
| **Vehicle Motors** | ❌ FAILED | All 6 motors UNAVAILABLE - suspected back-EMF damage |
| **Left Arm** | ✅ OPERATIONAL | 230 detection images captured |
| **Right Arm** | ✅ OPERATIONAL | Tested Jan 20, working |
| **Cotton Detection** | ✅ WORKING | YOLOv11 detection functioning |

### Critical Issue: Vehicle Drive Motors Burnt
**Root Cause:** Motors damaged when vehicle was moved manually without power (back-EMF damage)
**Impact:** Vehicle is non-operational; no replacement motors available
**Action Required:** Find motor alternatives + implement protection for future

---

## 1. Vehicle System Analysis

### 1.1 Log Analysis Summary

**Total Vehicle Logs Analyzed:** 14 sessions across Jan 7, 2026

| Session Time | Motors Initialized | Status |
|--------------|-------------------|--------|
| 00:19:22 | 0/6 | ❌ All UNAVAILABLE |
| 01:08:04 | 0/6 | ❌ All UNAVAILABLE |
| 02:02:18 | 0/6 | ❌ All UNAVAILABLE |
| 06:25:53 | 0/6 | ❌ All UNAVAILABLE |
| 06:35:51 | 0/6 | ❌ All UNAVAILABLE |
| 06:39:01 | 0/6 | ❌ All UNAVAILABLE |
| 12:37:25 | 0/6 | ❌ All UNAVAILABLE |
| 15:04:35 | 0/6 | ❌ All UNAVAILABLE |
| 17:13:36 | 0/6 | ❌ All UNAVAILABLE |
| 17:20:41 | 0/6 | ❌ All UNAVAILABLE |
| 17:41:16 | 0/6 | ❌ All UNAVAILABLE |
| 19:50:51 | 0/6 | ❌ All UNAVAILABLE |
| 22:35:07 | 0/6 | ❌ All UNAVAILABLE |
| 23:21:16 | 0/6 | ❌ All UNAVAILABLE |

**Key Observation:** Motors were already damaged from the FIRST log entry, suggesting damage occurred before software testing began (likely during transport or manual movement).

### 1.2 Error Messages from Logs
```
❌ Failed to initialize motor 3 (steering_left)
❌ Failed to initialize motor 5 (steering_right)
❌ Failed to initialize motor 1 (steering_front)
❌ Failed to initialize motor 2 (drive_front)
❌ Failed to initialize motor 4 (drive_left_back)
❌ Failed to initialize motor 6 (drive_right_back)
❌ Cannot operate: Too many init failures: 6 > 1
⚠️ ROS 2 interface ready but NO MOTORS available
```

### 1.3 Vehicle Configuration (from logs)
```yaml
CAN Interface: can0
CAN Bitrate: 500000
Motor Count: 6
Control Frequency: 50.0 Hz
Smart Polling: enabled
Motion Feedback: enabled, poll_hz=5.00

Steering Motors (MG6010-i6):
  - transmission: 50.0 (external gear)
  - internal_gear: 6.0
  - direction: 1

Drive Motors (MG6012-i36):
  - transmission: 5.0 (external gear)
  - internal_gear: 36.0
  - direction: -1 (reversed)
```

---

## 2. Arm System Analysis

### 2.1 Left Arm Performance
**Session Date:** January 11-12, 2026

| Metric | Value |
|--------|-------|
| Detection Images Captured | 230 |
| Detection Sessions | 6+ log sessions |
| System Health | ✅ Operational |

**Detection Output Sample (from output.txt):**
```
636 0 0.0345 0.0316 0.6711
636 0 0.1406 0.1391 0.7197
```
Format: `image_id class x_center y_center confidence`

### 2.2 Right Arm Performance
**Session Date:** January 20, 2026
**Sessions:** 2 log sessions (14:39, 15:28)
**Images Captured:** 229 detected, 269 input

**Configuration Verified:**
- Joint3 (rotation): [-0.200, 0.000] rotations (-72.0° to 0.0°)
- Joint4 (left/right): [-0.125, 0.175] meters
- Joint5 (extension): [0.000, 0.350] meters
- PHI compensation: ENABLED
- Cotton detection subscription: `/cotton_detection/results`

**Detection Metrics (Session A - Large Run):**
| Metric | Value |
|--------|-------|
| Model | YOLOv11 (`yolov112.blob`, 2 classes) |
| Detection Requests | 159 |
| Detection Latency | p50: 69ms, p90: 103ms, max: 120ms |
| Camera Connection | USB 3.0 (5Gbps) |
| Camera Temperature | 45.7°C - 52.5°C |
| XLink Errors | 0 |
| Reconnects | 0 |

**Detection Classification (Session A):**
| Category | Count | % of Raw |
|----------|-------|----------|
| **Raw detections** | 312 | 100% |
| cotton_accepted | 144 | 46.2% |
| border_skip | 57 | 18.3% |
| not_pickable | 111 | 35.6% |
| Frames with border_skip | 49/160 | **30.6%** |

**Pick Attempt Results (Session A - 133 attempts):**
| Outcome | Count | % |
|---------|-------|---|
| ✅ **Picked** | 29 | **21.8%** |
| ❌ out_of_reach_joint4 | 57 | 42.9% |
| ❌ out_of_reach_joint5 | 26 | 19.5% |
| ❌ failed_pick | 15 | 11.3% |
| ❌ approach_failed | 6 | 4.5% |

**Critical Finding:** 21/133 attempts (15.8%) had invalid target `[0,0,0]` - accounts for ALL failed_pick + approach_failed.

**Radial Reachability (r in meters):**
| Stat | Value | Notes |
|------|-------|-------|
| min | 0.079 | Too close |
| p50 | 0.748 | Too far |
| p90 | 1.284 | Too far |
| max | 1.440 | Too far |
| Reachable range | [0.320, 0.670] | Per Joint5 limits |
| Too far | 73/133 (54.9%) | Main failure mode |
| Too close | 21/133 (15.8%) | Secondary failure |

**Session B (High Success Baseline):**
| Metric | Value |
|--------|-------|
| Attempts | 17 |
| Picked | 16 (94.1%) |
| out_of_reach_joint4 | 1 |
| Invalid [0,0,0] targets | 0 |
| r range | 0.361 - 0.521 (all within reachable) |

**Key Inference:** Dominant failure mode is **reachability** (Joint4/Joint5 limits), NOT detection.

**Status:** ✅ Detection working | ⚠️ Reachability needs improvement

---

## 3. Issues Identified

### 3.1 Critical Issues
| Issue | Impact | Priority |
|-------|--------|----------|
| **Drive motors burnt** | Vehicle non-operational | 🔴 CRITICAL |
| **No replacement motors** | Blocked on alternatives | 🔴 CRITICAL |
| **Detection returning [0,0,0]** | Pick fails at invalid coordinates | 🔴 CRITICAL |
| **Position out of reach errors** | Cotton unreachable, pick fails | 🟡 HIGH |
| **Camera FOV (vertical)** | Limited coverage area | 🟡 HIGH |
| **Steering - same wheel speed** | Poor turning accuracy | 🟡 HIGH |
| **ARM_client crash (exit code 2)** | System restart required | 🟡 HIGH |

### 3.2 Detection Issues (from Log Analysis)
| Issue | Count | Example | Impact |
|-------|-------|---------|--------|
| **border_skip** | 6 | Cotton at image edges | Missed picks |
| **not_pickable** | 10 | bbox at x > 0.77 (right edge) | Missed picks |
| **Total rejected** | 16 | | ~10-15% of detections |

**Not-pickable pattern observed (right arm logs):**
```
🚫 not_pickable: conf=0.70 bbox(0.77, 0.88, 0.89, 1.00)  ← RIGHT EDGE
🚫 not_pickable: conf=0.74 bbox(0.84, 0.40, 0.91, 0.48)  ← RIGHT EDGE
```
Most not-pickable detections are at **x > 0.77** (right 23% of image) - confirms Joint4 movement can help re-center these.

### 3.3 Software Errors (from Log Analysis)
| Error | Location | Details |
|-------|----------|--------|
| **Position out of reach** | Right arm | Target [0.588, -0.106, 0.118] unreachable |
| **[0,0,0] coordinates** | Right arm | Detection returned invalid position |
| **ARM_client died** | Left arm | Process exit code 2 |

**Sample error from logs:**
```
⚠️ Position out of reach: target=[0.588, -0.106, 0.118], joint_pos=[...]
❌ Failed pick at [0.000, -0.000, -0.000]
```

### 3.4 Observations for Improvement
1. **FOV:** Vertical camera orientation limits horizontal coverage
2. **Joint4 range:** Currently fixed at center, limiting effective FOV
3. **Border handling:** 16 cotton rejected at image edges - Joint4 shift can recover
4. **Detection model:** Bounding boxes causing merged detection issues
5. **Steering:** Need differential wheel velocities for accurate turning
6. **Error handling:** ARM_client needs restart logic or watchdog

---

## 4. Action Items for Next Visit (Feb 25, 2026)

### 4.1 Before Visit
- [ ] **CRITICAL:** Source alternative motors or repair existing
- [ ] Implement back-EMF protection circuit
- [ ] Test horizontal camera mount in lab
- [ ] Train YOLOv11-seg model on segmentation dataset
- [ ] Implement differential drive velocity calculations

### 4.2 Hardware Tasks
- [ ] Install protection diodes on motor power lines
- [ ] Create "NO MANUAL MOVEMENT" warning labels
- [ ] Test camera in horizontal orientation
- [ ] Verify CAN bus integrity

### 4.3 Software Tasks
- [ ] Update Joint4 range to ±100mm for wider FOV
- [ ] Implement differential wheel velocity control
- [ ] Integrate segmentation model output
- [ ] Add motor damage detection/alerts

---

## 5. Lessons Learned

### 5.1 Motor Protection
**CRITICAL SOP:** Never move vehicle manually when power is OFF
- Motors act as generators when back-driven
- Generated voltage can damage motor windings/controllers
- Need hardware protection (flyback diodes, TVS, brake resistors)

### 5.2 Pre-Visit Checklist
- [ ] Verify all motors respond before transport
- [ ] Lock wheels or disconnect motors before manual movement
- [ ] Check CAN communication after any physical handling

---

## Appendix: Log File Inventory

### Vehicle Logs
```
/home/uday/Downloads/Zoho WorkDrive/vehicle/logs/
├── 2026-01-07-00-19-22-756335-pragati11-2039/
├── 2026-01-07-01-08-04-692542-pragati11-2065/
├── 2026-01-07-02-02-18-111405-pragati11-2040/
├── 2026-01-07-06-25-53-565574-pragati11-2056/
├── 2026-01-07-06-35-51-885099-pragati11-2051/
├── 2026-01-07-06-39-01-808199-pragati11-2065/
├── 2026-01-07-12-37-25-425365-pragati11-2044/
├── 2026-01-07-15-04-35-889981-pragati11-2060/
├── 2026-01-07-17-13-36-548132-pragati11-2272/
├── 2026-01-07-17-20-41-803028-pragati11-2064/
├── 2026-01-07-17-41-16-196436-pragati11-2043/
├── 2026-01-07-19-50-51-434581-pragati11-2050/
├── 2026-01-07-22-35-07-792271-pragati11-2048/
└── 2026-01-07-23-21-16-877460-pragati11-2044/
```

### Left Arm Data
```
/home/uday/Downloads/Zoho WorkDrive/left_arm/
├── detected_imgs/    (230 images)
├── input_imgs/
└── logs/             (6 sessions from Jan 11-12)
```

### Right Arm Data
```
/home/uday/Downloads/Zoho WorkDrive/right_arm/
└── logs/             (2 sessions from Jan 20)
```

---

**Report Generated:** January 28, 2026
**Author:** Automated Analysis
**Review Status:** Pending team review
