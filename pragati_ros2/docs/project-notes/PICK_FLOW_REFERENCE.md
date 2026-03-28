# Cotton Pick Flow - Complete Reference

**Date:** 2026-02-11
**Status:** Current (reflects commits up to f433a45)
**Scope:** End-to-end pick flow with multi-position J4 scanning, coordinate transforms, motor commands, and timing

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Phase 0: Startup and Homing](#2-phase-0-startup-and-homing)
3. [Phase 1: Wait for START_SWITCH](#3-phase-1-wait-for-start_switch)
4. [Phase 2: Multi-Position J4 Scanning](#4-phase-2-multi-position-j4-scanning)
5. [Phase 2a: Detection Pipeline at Each Position](#5-phase-2a-detection-pipeline-at-each-position)
6. [Phase 2b: Coordinate Transforms (with sample numbers)](#6-phase-2b-coordinate-transforms-with-sample-numbers)
7. [Phase 3: Pick Sequence Per Cotton](#7-phase-3-pick-sequence-per-cotton)
8. [End-to-End Data Transform Example](#8-end-to-end-data-transform-example)
9. [Complete Timeline Example](#9-complete-timeline-example)
10. [FAQ - Common Questions](#10-faq---common-questions)
11. [Key Source Files](#11-key-source-files)
12. [Configuration Reference](#12-configuration-reference)
13. [Recent Changes (Feb 2026)](#13-recent-changes-feb-2026)

---

## 1. System Overview

Three ROS2 nodes work together to detect and pick cotton:

```
┌──────────────────────────┐
│     yanthra_move          │   Orchestrates the entire pick cycle
│  (YanthraMoveSystem +     │   Owns state machine, triggers detection,
│   MotionController)       │   commands joints, controls end-effector
└────────┬─────────┬────────┘
         │         │
   service call    │  joint commands (Float64 topics)
   + topic sub     │
         │         │
         ▼         ▼
┌────────────────┐ ┌─────────────────────┐
│ cotton_detect  │ │  motor_control_ros2  │
│ _ion_ros2      │ │                     │
│                │ │  3x MG6010-i6 motors │
│ OAK-D Lite     │ │  via CAN bus (can0)  │
│ YOLOv11 on VPU │ │  + GPIO end-effector │
│ Stereo depth   │ │  + GPIO compressor   │
└────────────────┘ └─────────────────────┘
```

### Joint Layout

| Joint | Role            | Units     | Limits              | CAN ID | Motor              |
|-------|-----------------|-----------|----------------------|--------|--------------------|
| J3    | Tilt / rotation | rotations | [-0.2, 0.0] rot     | 2      | MG6010-i6, trans=1.0  |
| J4    | Left / right    | meters    | [-0.125, +0.175] m  | 3      | MG6010-i6, trans=12.74 |
| J5    | Extension       | meters    | [0.0, 0.35] m       | 1      | MG6010-i6, trans=12.74 |

All motors: internal gear ratio = 6.0, direction = -1.

---

## 2. Phase 0: Startup and Homing

```
motor_control_ros2:
  1. Open CAN socket (can0, 500kbps)
  2. Motor ON command [0x88] to CAN IDs 1, 2, 3
  3. Home each motor to 0.0
     J5 (CAN 1) → 0.0m
     J3 (CAN 2) → 0.0 rot
     J4 (CAN 3) → 0.0m

cotton_detection_ros2:
  4. Build DepthAI pipeline:
     ColorCamera (1920x1080 @ 30fps)
       → ImageManip (416x416, keepAspectRatio=false)
       → YOLOv11 SpatialDetection (2 classes: cotton, not_pickable)
     MonoLeft (400p) + MonoRight (400p)
       → StereoDepth → feeds SpatialNN for 3D coordinates

yanthra_move:
  5. performInitializationAndHoming()
  6. Camera warm-up: sends 1 dummy detect_command=1
  7. arm_status = "ready"
```

**Code:** `yanthra_move_system_operation.cpp` `runMainOperationLoop()` lines 207-240

---

## 3. Phase 1: Wait for START_SWITCH

```
Operator presses START button (GPIO 3, debounced: 5+ consecutive HIGH readings)
  │
  ▼
motor_control publishes START_SWITCH topic
  │
  ▼
yanthra_move receives START_SWITCH
  → Clear stale detection buffer
  → arm_status = "busy"
  → Enter Phase 2
```

**Code:** `yanthra_move_system_operation.cpp` lines 243-290

---

## 4. Phase 2: Multi-Position J4 Scanning

The arm scans 5 lateral positions to maximize camera detection coverage. This was added in Feb 2026 to recover cotton bolls that were being lost at the camera FOV edges (16 lost in Jan 2026 field trial).

### J4 Positions

```
◄──── LEFT                                         RIGHT ────►

  Pos 0        Pos 1       Pos 2       Pos 3       Pos 4
 -100mm       -50mm        0mm        +50mm       +100mm
    ·────────────·───────────·───────────·────────────·
                        (home)
```

**Scan strategy:** `left_to_right` (sorted ascending).

### Key Behavior: J4 Does NOT Return Home Between Positions

**J4 moves DIRECTLY from one position to the next.** When scanning from -100mm to -50mm, the arm does NOT go back to 0mm first. It moves straight to the next absolute position.

```
J4 movement path during scan:

  -100mm ──► -50mm ──► 0mm ──► +50mm ──► +100mm ──► 0mm (home)
    │          │        │         │          │          │
   scan      scan     scan      scan       scan     return
   detect    detect   detect    detect     detect    home
   (pick?)   (pick?)  (pick?)   (pick?)    (pick?)
```

**Code evidence:** `motion_controller.cpp` lines 377-426 — the for loop simply commands `j4_absolute = homing_position + offset` at each iteration, with no intermediate home command.

### Scan Loop Detail

```
FOR EACH of the 5 J4 positions:
  1. Validate position against limits [-0.125m, +0.175m]
  2. Move J4 to absolute position → BLOCKING
     (sleeps: distance/0.3 + 1.0s, capped at 3s)
  3. Camera settling: sleep 200ms (ensures 6+ fresh frames at 30fps)
  4. Trigger fresh detection (see Phase 2a)
  5. If cotton found → pick ALL cotton at this position (Phase 3)
     - After picking last cotton, J3 and J4 are homed
  6. If no cotton → log and continue to next position
     (no early exit — all 5 positions always scanned)

AFTER all 5 positions:
  7. Return J4 to home (0.0m) — explicit blocking move
  8. Mandatory end-of-cycle homing: moveToPackingPosition()
     → J5 → 0.0m, J3 → 0.0 rot, J4 → 0.0m (safety net)
```

**Code:** `motion_controller.cpp` lines 377-520 (scan loop), lines 512-520 (J4 return home), lines 581-592 (mandatory end-of-cycle homing)

### After Scan Completes: Full Homing Then Wait

After all 5 positions are scanned and any cotton is picked:
1. J4 is returned to home (inside scan loop, line 517)
2. `moveToPackingPosition()` runs (line 588): homes J5 → J3 → J4 in sequence
3. `arm_status = "ready"` (in `yanthra_move_system_operation.cpp` line 427)
4. System **waits for the next START_SWITCH** button press
5. On next button press, the **entire 5-position scan repeats from scratch**

Even in `continuous_operation=true` mode, the system waits for a new START_SWITCH before each cycle.

---

## 5. Phase 2a: Detection Pipeline at Each Position

### Trigger Flow

```
yanthra_move                          cotton_detection_ros2
─────────────                         ──────────────────────

trigger_time = now()
    │
    ├── srv call: detect_command=1 ──►│
    │                                  ▼
    │                            Flush all queues
    │                            (discard stale frames)
    │                                  │
    │                                  ▼
    │                            getDetections(500ms timeout)
    │                                  │
    │                                  ▼
    │                     ┌─────────────────────────┐
    │                     │  OAK-D Myriad X VPU:    │
    │                     │  YOLOv11 on 416x416     │
    │                     │  + StereoDepth for 3D   │
    │                     └────────────┬────────────┘
    │                                  │
    │                                  ▼
    │                     ┌─────────────────────────┐
    │                     │  Filtering Pipeline:     │
    │                     │  1. Class: label 0       │
    │                     │     (cotton) only        │
    │                     │     label 1 (not_pick-   │
    │                     │     able) rejected       │
    │                     │  2. Confidence >= 0.5    │
    │                     │     (device) >= 0.7      │
    │                     │     (node)               │
    │                     │  3. Border: skip if      │
    │                     │     within 5% of edge    │
    │                     └────────────┬────────────┘
    │                                  │
    │                                  ▼
    │                     Coordinate conversion:
    │                       RUF (mm) → FLU (meters)
    │                                  │
    │                                  ▼
    │                     Publish on /cotton_detection/results
    │                       DetectionResult msg with
    │                       CottonPosition[] array
    │                                  │
◄───┼── topic callback ───────────────┘
    │
Poll loop (10ms intervals, 1500ms timeout):
  unlock mutex → spin_some() → relock
  check: has_detection_ && last_detection_time_ > trigger_time
    │
    ▼
Return cotton positions to MotionController
```

### RUF to FLU Coordinate Conversion

DepthAI outputs spatial coordinates in RUF (Right-Up-Forward) in millimeters. The node converts to FLU (Forward-Left-Up) in meters:

```
X_flu =  Z_ruf / 1000    (Forward = DepthAI Forward)
Y_flu = -X_ruf / 1000    (Left    = negative DepthAI Right)
Z_flu =  Y_ruf / 1000    (Up      = DepthAI Up)
```

**Code:** `cotton_detection_node_depthai.cpp` lines 368-370

### Detection Synchronization (Fixed Feb 2026)

The system uses **timestamp-based freshness validation** to ensure only fresh detection data is used:
- Before triggering, record `trigger_time = now()`
- After receiving data, verify `last_detection_time_ > trigger_time`
- This eliminates stale data from previous triggers

**Code:** `yanthra_move_system_operation.cpp` `getDetectionTriggerCallback()` lines 476-550

---

## 6. Phase 2b: Coordinate Transforms (with sample numbers)

### Sample: Cotton A detected at J4 = +50mm position

#### Step 1: DepthAI Raw Output (RUF, millimeters)

```
spatial_x = +120mm  (Right of camera center)
spatial_y = -180mm  (Below camera center)
spatial_z = +450mm  (Forward from camera)
confidence = 0.85
```

#### Step 2: RUF to FLU Conversion (meters, camera_link frame)

```
X_flu =  450 / 1000 = +0.450m  (forward)
Y_flu = -120 / 1000 = -0.120m  (right of center, negative = right in FLU)
Z_flu = -180 / 1000 = -0.180m  (below camera)
```

#### Step 3: TF Transform (camera_link → yanthra_link)

The URDF defines the static transform between camera and arm base. After TF:

```
X' = +0.420m  (forward from arm base)
Y' = -0.120m  (right)
Z' = -0.310m  (below arm base)
```

#### Step 4: Cartesian to Polar Conversion

```
r     = sqrt(X'² + Z'²)
      = sqrt(0.420² + 0.310²)
      = sqrt(0.2725)
      = 0.522m

theta = Y'  (DIRECT passthrough — NOT an angle!)
      = -0.120m

phi   = asin(Z' / sqrt(Z'² + X'²))
      = asin(-0.310 / 0.522)
      = -0.636 rad  (-36.4°)
```

**Important:** `theta` is NOT an angle. It is the raw Y-coordinate in meters, passed directly to J4. The system uses NO inverse kinematics — it is a direct polar mapping.

```
        Z (Up)
        │
        │  Cotton is below and forward
        │
────────┼──────────────── X (Forward)
        │ ╲  phi = -36.4°
        │   ╲
        │    ╲  r = 0.522m
        │     ╲
        │      ●  Cotton A
        │   (X'=0.42, Z'=-0.31)
```

**Code:** `coordinate_transforms.cpp` lines 33-49

#### Step 5: Polar to Joint Commands

```
J5 (extension)  = r - hardware_offset
                = 0.522 - 0.290
                = 0.232m
  Limits check: [0.0, 0.35] × 0.98 = [0.0, 0.343m]  --> VALID

J3 (tilt)       = (phi + phi_compensation) × RAD_TO_ROT
  phi = -0.636 rad = -36.4°
  Phi compensation (Zone 1: 0°-50.5°):
    base = +0.014 rot (+5°)
    L5 scale = 1 + 0.5 × (0.232 / 0.35) = 1.331
    compensation = 0.014 × 1.331 = 0.01864 rot
    compensation_rad = 0.01864 × 2π = 0.117 rad
  J3 = (-0.636 + 0.117) × (1/2π)
     = -0.519 × 0.15915
     = -0.083 rot
  Limits check: [-0.2, 0.0] × 0.98 = [-0.196, 0.0]  --> VALID

J4 (left/right) = theta (direct passthrough)
                = -0.120m
  Limits check: [-0.125, 0.175] × 0.98 = [-0.1225, 0.1715]  --> VALID
```

**Code:** `motion_controller.cpp` lines 1048-1127

#### Step 6: Joint to Motor Commands (CAN bus)

```
Formula: motor_angle = joint_pos × transmission × direction × 2π × gear_ratio

J5 → CAN ID 1:
  motor = 0.232 × 12.74 × (-1) × 2π × 6.0 = -111.4 rad
  CAN frame: [0xA3, centideg_bytes(4), ...]
  centidegrees = -111.4 × (180/π) × 100 = -638,300

J3 → CAN ID 2:
  motor = -0.083 × 1.0 × (-1) × 2π × 6.0 = 3.11 rad
  centidegrees = 17,842

J4 → CAN ID 3:
  motor = -0.120 × 12.74 × (-1) × 2π × 6.0 = 57.6 rad
  centidegrees = 330,129
```

**Code:** `mg6010_controller.cpp` `joint_to_motor_position()`, `mg6010_protocol.cpp` `set_absolute_position()`

---

## 7. Phase 3: Pick Sequence Per Cotton

Cotton positions are sorted by `CottonPickingOptimizer` (default strategy: RASTER_SCAN).

### For Each Cotton:

```
┌─────────────────────────────────────────────────────────┐
│  APPROACH TRAJECTORY                                     │
│                                                          │
│  Step 1: Move J4 (left/right)     → BLOCKING            │
│          delay 0.3s (inter_joint_delay)                  │
│  Step 2: Move J3 (tilt/rotation)  → BLOCKING            │
│          delay 0.3s (inter_joint_delay)                  │
│  Step 3: Move J5 (extension)      → NON-BLOCKING        │
│          Dynamic EE monitors J5 position                 │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  END-EFFECTOR ACTIVATION (dynamic mode, position-based)  │
│                                                          │
│  J5 extending ════════════════════════►                  │
│  0.0m ────── ee_start ──────── target                   │
│                │                  │                      │
│                │                  └── cotton position     │
│                │                                         │
│                └── target - 150mm = EE START point       │
│                    GPIO 21=HIGH (Cytron motor enable)     │
│                    GPIO 13=direction                      │
│                    Mechanical grabber starts spinning     │
│                                                          │
│  J5 reaches target → COTTON GRABBED                      │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  CAPTURE SEQUENCE (currently no-op, wait = 0.0s)         │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  RETREAT TRAJECTORY                                      │
│                                                          │
│  Step 1: Retract J5 → 0.0m  (NON-BLOCKING)             │
│          EE stays ON during initial retract               │
│          EE OFF when J5 retracts past target - 150mm     │
│                                                          │
│  If NOT last cotton (optimization):                      │
│    → Skip J3/J4 homing, keep position for next pick     │
│    → Only J5 retracted                                   │
│                                                          │
│  If IS last cotton in this batch:                        │
│    → delay 0.3s → J3 → home (0.0 rot)                  │
│    → delay 0.3s → J4 → home (0.0m)                     │
│                                                          │
│  Cotton drop:                                            │
│    → settle delay 0.2s                                   │
│    → Compressor burst: GPIO 18 HIGH for 0.5s            │
│    → Pneumatic ejection into collection                  │
└─────────────────────────────────────────────────────────┘
```

**Code:** `motion_controller.cpp` `pickCottonAtPosition()` line 923, `executeApproachTrajectory()` lines 1048-1210, `executeRetreatTrajectory()` lines 1700-1920

---

## 8. End-to-End Data Transform Example

Tracing Cotton A from raw sensor output to physical picking:

```
Stage                  Format              Values
─────                  ──────              ──────
DepthAI VPU output     RUF mm              x=+120  y=-180   z=+450

RUF→FLU convert        FLU meters          x=+0.450  y=-0.120  z=-0.180
                       (camera_link)

TF transform           FLU meters          x=+0.420  y=-0.120  z=-0.310
                       (yanthra_link)

Polar conversion       r, theta, phi       r=0.522m  theta=-0.120m  phi=-0.636rad

Phi compensation       3-zone piecewise    +0.117 rad (Zone 1, L5 scaled)

Joint commands         joint units         J5=0.232m  J3=-0.083rot  J4=-0.120m

Motor commands         CAN centidegrees    CAN1=-638,300  CAN2=17,842  CAN3=330,129

Physical arm           MG6010-i6 motors    Arm extends, tilts, and shifts to cotton

End-effector           GPIO Cytron board   Grabber ON 150mm before target

Cotton ejection        GPIO compressor     0.5s pneumatic burst
```

---

## 9. Complete Timeline Example

**Scenario:** 2 cotton found at J4 position 3 (+50mm), none at other positions.

```
TIME    EVENT                                           J4      J3      J5
─────   ─────────────────────────────────────────────   ─────   ─────   ─────

 0.0s   START_SWITCH received                           0.0m    0.0r    0.0m

── SCAN POSITION 0 (-100mm) ──
 0.0s   Move J4 → -0.100m [blocking, ~2.3s]
 2.3s   Camera settle 200ms
 2.5s   Trigger detection → wait ~100ms
 2.6s   Result: 0 cotton → continue                    -0.1m   0.0r    0.0m

── SCAN POSITION 1 (-50mm) ──   ** J4 goes DIRECTLY -100→-50, no home **
 2.6s   Move J4 → -0.050m [blocking, ~1.2s]
 3.8s   Camera settle 200ms
 4.0s   Trigger detection → wait ~100ms
 4.1s   Result: 0 cotton → continue                    -0.05m  0.0r    0.0m

── SCAN POSITION 2 (0mm) ──
 4.1s   Move J4 → 0.000m [blocking, ~1.2s]
 5.3s   Camera settle 200ms
 5.5s   Trigger detection → wait ~100ms
 5.6s   Result: 0 cotton → continue                    0.0m    0.0r    0.0m

── SCAN POSITION 3 (+50mm) ──
 5.6s   Move J4 → +0.050m [blocking, ~1.2s]
 6.8s   Camera settle 200ms
 7.0s   Trigger detection → wait ~100ms
 7.1s   Result: 2 cotton found! (A & B)                +0.05m  0.0r    0.0m

── PICK COTTON A (not last → skip J3/J4 homing after retreat) ──
 7.1s   Approach: J4 → -0.120m [blocking, 1.6s]
 8.7s   delay 0.3s
 9.0s   Approach: J3 → -0.083rot [blocking, 1.3s]
10.3s   delay 0.3s
10.6s   Approach: J5 → 0.232m [non-blocking]
11.2s   J5 passes 0.082m → EE ON (grabber)
11.8s   J5 reaches 0.232m → COTTON GRABBED             -0.12m  -0.08r  0.232m
11.8s   Retreat: J5 → 0.0m [non-blocking]
12.4s   J5 passes 0.082m retracting → EE OFF
12.9s   J5 home. J3/J4 SKIPPED (not last)              -0.12m  -0.08r  0.0m
13.1s   settle 0.2s → compressor burst 0.5s
13.8s   Cotton A ejected

── PICK COTTON B (last → full homing after retreat) ──
13.8s   Approach: J4 → +0.030m [blocking, 1.5s]
15.3s   delay 0.3s
15.6s   Approach: J3 → -0.110rot [blocking, 1.1s]
16.7s   delay 0.3s
17.0s   Approach: J5 → 0.280m [non-blocking]
17.6s   J5 passes 0.130m → EE ON
18.4s   J5 reaches 0.280m → COTTON GRABBED             +0.03m  -0.11r  0.28m
18.4s   Retreat: J5 → 0.0m [non-blocking]
19.1s   J5 passes 0.130m → EE OFF
19.8s   J5 at home
20.1s   delay 0.3s → J3 → 0.0rot [1.4s]
21.8s   delay 0.3s → J4 → 0.0m [1.1s]                 0.0m    0.0r    0.0m
23.2s   settle 0.2s → compressor burst 0.5s
23.9s   Cotton B ejected

── SCAN POSITION 4 (+100mm) ──
23.9s   Move J4 → +0.100m [blocking, ~2.3s]
26.2s   Camera settle 200ms
26.4s   Trigger detection → wait ~100ms
26.5s   Result: 0 cotton → continue                    +0.1m   0.0r    0.0m

── RETURN HOME ──
26.5s   J4 → 0.0m (explicit return, inside scan loop)
28.8s   moveToPackingPosition(): J5→J3→J4 all 0.0      0.0m    0.0r    0.0m
~29s    arm_status = "ready"

── WAIT FOR NEXT CYCLE ──
~29s    System waits for next START_SWITCH press
        On press → entire 5-position scan repeats from scratch

═══════════════════════════════════════════════════════════════════
TOTAL CYCLE: ~29s  |  Cotton picked: 2  |  Positions scanned: 5
═══════════════════════════════════════════════════════════════════
```

---

## 10. FAQ - Common Questions

### Q: Does J4 go back to home between scan positions?

**No.** J4 moves DIRECTLY from one scan position to the next. For example, from -100mm it goes straight to -50mm, not -100mm → 0mm → -50mm.

Code evidence: `motion_controller.cpp` line 412-415 — the for loop simply commands `j4_absolute` at each iteration with no intermediate home command.

### Q: After picking cotton at a scan position, does J4 go home before moving to the next scan position?

**It depends.** After picking the LAST cotton at a given scan position, the retreat trajectory DOES home J3 and J4 (via `executeRetreatTrajectory(is_last_cotton=true)`). So J4 is at 0.0m when the scan loop moves to the next position.

However, if there were multiple cotton at one position, J3/J4 are NOT homed between picks (only J5 retracts). They stay near the previous cotton position for faster sequential picking.

### Q: After all 5 scan positions are done, does the arm stay there or go home?

**It goes home.** Two homing steps occur:
1. **Explicit J4 return** to home (line 517 in scan loop)
2. **Mandatory `moveToPackingPosition()`** at end-of-cycle (line 588): homes J5 → J3 → J4 in sequence as a safety net

### Q: What happens on the next START_SWITCH button press?

**The entire 5-position scan repeats from scratch**, starting from position 0 (-100mm). The system does not remember previous detections or skip positions. Every cycle is a full fresh scan.

Even in `continuous_operation=true` mode, the system waits for a new START_SWITCH before starting each cycle.

### Q: Is there inverse kinematics?

**No.** The system uses a direct polar coordinate mapping:
- `r` (radial distance in XZ plane) → J5 extension
- `theta` (Y-coordinate in meters, NOT an angle) → J4 left/right
- `phi` (elevation angle in XZ plane) → J3 tilt/rotation

There is a 3-zone piecewise phi compensation for mechanical calibration errors.

### Q: What is the "early exit" that was disabled?

Previously, if the first scan position (e.g., -100mm) found no cotton, the system would skip all remaining positions. This was disabled because cotton can be at any lateral position — the camera FOV at -100mm cannot see cotton at +100mm.

---

## 11. Key Source Files

| File | Role |
|------|------|
| `src/yanthra_move/src/core/motion_controller.cpp` | Main brain: scan loop, joint commands, pick sequences (~2778 lines) |
| `src/yanthra_move/src/yanthra_move_system_operation.cpp` | Top-level operation loop, detection triggering, START_SWITCH handling |
| `src/yanthra_move/src/coordinate_transforms.cpp` | `convertXYZToPolarFLUROSCoordinates()` function |
| `src/yanthra_move/src/joint_move.cpp` | Low-level joint command publishing (Float64 to topics) |
| `src/yanthra_move/include/yanthra_move/core/motion_controller.hpp` | MotionController class definition |
| `src/yanthra_move/include/yanthra_move/cotton_picking_optimizer.hpp` | Pick order optimization strategies |
| `src/yanthra_move/config/production.yaml` | All arm parameters |
| `src/cotton_detection_ros2/src/cotton_detection_node_depthai.cpp` | DepthAI pipeline, RUF→FLU conversion |
| `src/cotton_detection_ros2/src/cotton_detection_node_services.cpp` | Detection service handler |
| `src/cotton_detection_ros2/src/depthai_manager.cpp` | Camera pipeline builder (~2002 lines) |
| `src/motor_control_ros2/src/mg6010_controller_node.cpp` | Motor controller node (~2214 lines) |
| `src/motor_control_ros2/src/mg6010_protocol.cpp` | CAN protocol (LK-TECH V2.35) |
| `src/motor_control_ros2/src/gpio_control_functions.cpp` | GPIO: end-effector, compressor, LEDs |
| `src/motor_control_ros2/config/production.yaml` | Motor parameters, CAN IDs, limits |

---

## 12. Configuration Reference

### J4 Multi-Position Scanning (`production.yaml`)

```yaml
joint4_multiposition/enabled: true
joint4_multiposition/positions: [-0.100, -0.050, 0.000, 0.050, 0.100]
joint4_multiposition/safe_min: -0.100
joint4_multiposition/safe_max: 0.100
joint4_multiposition/scan_strategy: "left_to_right"
joint4_multiposition/j4_settling_time: 0.100       # 100ms after motor stops
joint4_multiposition/detection_settling_time: 0.200 # 200ms for camera frames
joint4_multiposition/early_exit_enabled: false       # disabled — always scan all
```

### Timing Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `inter_joint_delay` | 0.3s | Delay between sequential joint moves |
| `min_sleep_time_formotor_motion` | 0.2s | Minimum motor travel wait |
| `cotton_settle_delay` | 0.2s | Settle before compressor ejection |
| `compressor_burst_duration` | 0.5s | Pneumatic ejection duration |
| `delays/ee_start_distance` | 0.150m | EE activates 150mm before cotton |
| `delays/ee_stop_distance` | 0.150m | EE deactivates 150mm from cotton during retract |
| `delays/use_dynamic_ee_prestart` | true | Position-based EE timing enabled |

### Phi Compensation (3-Zone Piecewise)

| Zone | Angle Range | Offset (rot) | Effect |
|------|-------------|---------------|--------|
| 1 | 0° - 50.5° | +0.014 (+5°) | Arm goes below cotton, compensate UP |
| 2 | 50.5° - 60° | 0.0 | Arm correct, no compensation |
| 3 | 60° - 90° | -0.014 (-5°) | Arm goes above cotton, compensate DOWN |

L5 scaling: `factor = 1.0 + 0.5 × (j5_cmd / j5_max)`

### Motor Parameters

| Motor | CAN ID | Joint | Transmission | Gear Ratio | Direction | Position Tolerance |
|-------|--------|-------|-------------|------------|-----------|-------------------|
| MG6010-i6 | 1 | J5 (extension) | 12.74 | 6.0 | -1 | 5mm |
| MG6010-i6 | 2 | J3 (tilt) | 1.0 | 6.0 | -1 | 0.05 rot (~18°) |
| MG6010-i6 | 3 | J4 (left/right) | 12.74 | 6.0 | -1 | 5mm |

---

## 13. Recent Changes (Feb 2026)

Three commits introduced multi-position scanning and fixed critical bugs:

### `fb575a2` — Copy aligned meshes into robot_description (Feb 5)
- Replaced all STL mesh files with properly aligned, optimized versions
- Fixed URDF package references from `mg6010_description` to `robot_description`
- Ensures accurate TF transforms for camera-to-arm coordinate conversion

### `f24c09e` — Enable multi-position J4 scanning with detection synchronization fixes (Feb 10)
- **Enabled multi-position scanning** (was implemented but disabled)
- **Fixed blocking wait bug**: `joint_move.cpp` `wait` parameter was being ignored (`(void)wait`). Now sleeps for estimated travel time.
- **Fixed detection deadlock**: `getLatestCottonPositions()` was double-locking `detection_mutex_`. Added `getLatestCottonPositions_NoLock()` helper.
- **Fixed stale detection data**: Replaced clear-and-wait with timestamp-based freshness validation
- **Increased camera settling**: 50ms → 200ms (ensures 6+ fresh frames)
- **Fixed DepthAI aspect ratio**: Added `setKeepAspectRatio(false)` to prevent letterboxing distortion

### `f433a45` — Disable early exit optimization in multi-position scanning (Feb 10)
- Removed the early exit that skipped remaining scan positions when position 0 found no cotton
- All 5 positions are now always scanned — cotton at +100mm won't be missed because -100mm was empty
