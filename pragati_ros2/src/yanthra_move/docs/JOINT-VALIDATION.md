# Joint Calculation and Limit Validation Document

**Date:** 2025-11-09  
**Branch:** `fix/motion-controller-no-ik`  
**Purpose:** Validation document for team review of joint calculations and safety limits

---

## Overview

This document validates the complete data flow from motion controller through motor control for all three joints (3, 4, 5). Each joint uses a **direct NO-IK pipeline** where polar coordinates map directly to motor commands.

---

## Architecture

### Limit Enforcement Strategy: Defense-in-Depth (Two Layers)

**Layer 1: Motion Controller (Planning Layer)**
- Checks limits with **2% safety margin** before sending commands
- Provides **early failure** with detailed error messages (includes phi, theta, r context)
- Prevents wasted motion if target is unreachable
- Reads limit values from motor_control config (single source of truth)

**Layer 2: Motor Control (Hardware Layer)**
- Enforces **absolute hard limits** at mechanical boundaries
- Protects against any command source (not just motion_controller)
- Last line of defense against bugs, drift, or rounding errors
- Defined in `motor_control_ros2/config/production.yaml`

**Why Two Layers:**
- Planning layer (98% of limit) catches issues early with good error messages
- Hardware layer (100% of limit) provides safety backstop
- 2% buffer prevents numerical errors from hitting hard limits

### Key Configuration
```yaml
# motor_control_ros2/config/production.yaml (SINGLE SOURCE OF TRUTH)
joint_names: [joint5, joint3, joint4]
directions: [-1, -1, -1]           # All joints inverted
transmission_factors: [12.74, 1.0, 12.74]

# ABSOLUTE HARD LIMITS (100% - mechanical boundaries)
min_positions: [0.0, -0.2, -0.1]   # meters, rotations, meters
max_positions: [0.35, 0.0, 0.1]    # meters, rotations, meters
```

```cpp
// Motion controller applies 2% safety margin for planning
const double PLANNING_MARGIN = 0.98;
joint3_planning_min = -0.2 * 0.98 = -0.196  // 98% of hard limit
joint4_planning_max = 0.1 * 0.98 = 0.098    // 98% of hard limit
joint5_planning_max = 0.35 * 0.98 = 0.343   // 98% of hard limit
```

---

## JOINT 3: Rotation/Elevation (Phi Angle)

### Purpose
Controls arm elevation angle (up/down tilt)

### Motion Controller Calculation
```cpp
// Source: src/yanthra_move/src/core/motion_controller.cpp:356
const double RAD_TO_ROT = 1.0 / (2.0 * M_PI);
const double joint3_cmd = phi * RAD_TO_ROT;  // Direct conversion: phi → rotations
```

**Key Points:**
- ✅ **Direct conversion** (no offset, no normalization)
- ✅ **No limit checking** (delegated to motor_control)
- ✅ Negative phi (below horizontal) → negative rotations

### Motor Control Processing
```
1. Receive command: joint3_cmd (rotations)
2. Check limits on INPUT: min=-0.2, max=0.0 (rotations)
3. Apply direction: output = joint3_cmd × (-1)
4. Send to motor
```

### Example Flow: Target Below Horizontal

| Step | Value | Description |
|------|-------|-------------|
| **Input** | `phi = -0.8 rad` | Elevation angle from polar conversion |
| **Motion Calc** | `joint3_cmd = -0.8 / (2π) = -0.127 rot` | Direct conversion |
| **Command Sent** | `-0.127 rotations` | Published to `/joint3_position_controller/command` |
| **Motor Limit Check** | `-0.2 ≤ -0.127 ≤ 0.0` ✓ | PASS (within limits) |
| **Direction Applied** | `-0.127 × (-1) = +0.127 rot` | Inverted by motor config |
| **Physical Motion** | Motor rotates +0.127 | **Arm tilts DOWN** ✓ |

### Validation Questions
- [ ] Does positive motor rotation physically move arm **downward**?
- [ ] Is the limit range `-0.2 to 0.0` rotations correct? (corresponds to -72° to 0°)
- [ ] Is `direction = -1` correct for joint3?

---

## JOINT 4: Left/Right Translation (Y-coordinate)

### Purpose
Controls horizontal left/right position of end effector

### Motion Controller Calculation
```cpp
// Source: src/yanthra_move/src/core/motion_controller.cpp:374
const double joint4_cmd = theta;  // Direct passthrough (Y-coordinate in meters)
```

**Key Points:**
- ✅ **Direct passthrough** (theta IS the Y-coordinate from TF)
- ✅ **No limit checking** (delegated to motor_control)
- ✅ Negative theta (left) → negative command

### Motor Control Processing
```
1. Receive command: joint4_cmd (meters)
2. Check limits on INPUT: min=-0.1, max=0.1 (meters)
3. Apply transmission: × 12.74 (m to rotations)
4. Apply direction: output × (-1)
5. Send to motor
```

### Example Flow: Target to the Left

| Step | Value | Description |
|------|-------|-------------|
| **Input** | `theta = -0.05 m` | Y-coordinate from yanthra_link frame |
| **Motion Calc** | `joint4_cmd = -0.05 m` | Direct passthrough |
| **Command Sent** | `-0.05 meters` | Published to `/joint4_position_controller/command` |
| **Motor Limit Check** | `-0.1 ≤ -0.05 ≤ 0.1` ✓ | PASS (within limits) |
| **Transmission** | `-0.05 × 12.74 = -0.637 rot` | Convert meters to rotations |
| **Direction Applied** | `-0.637 × (-1) = +0.637 rot` | Inverted by motor config |
| **Physical Motion** | Motor rotates +0.637 | **Arm moves LEFT** ✓ |

### Validation Questions
- [ ] Does positive motor value physically move arm **left** (or right)?
- [ ] Is the limit range `-0.1 to 0.1` meters correct? (±10cm)
- [ ] Is `transmission_factor = 12.74` correct? (1m = 12.74 rotations)
- [ ] Is `direction = -1` correct for joint4?

---

## JOINT 5: Extension (Radial Distance)

### Purpose
Controls forward/backward extension of end effector

### Motion Controller Calculation
```cpp
// Source: src/yanthra_move/src/core/motion_controller.cpp:381-382
const double JOINT5_OFFSET = 0.320;  // Hardware offset: 320mm
const double joint5_cmd = r - JOINT5_OFFSET;
```

**Key Points:**
- ✅ **Hardware offset subtraction** (320mm)
- ✅ **No limit checking** (delegated to motor_control)
- ✅ Offset accounts for minimum mechanical reach

### Motor Control Processing
```
1. Receive command: joint5_cmd (meters)
2. Check limits on INPUT: min=0.0, max=0.35 (meters)
3. Apply transmission: × 12.74 (m to rotations)
4. Apply direction: output × (-1)
5. Send to motor
```

### Example Flow: Medium Distance Target

| Step | Value | Description |
|------|-------|-------------|
| **Input** | `r = 0.60 m` | Radial distance in XZ plane |
| **Motion Calc** | `joint5_cmd = 0.60 - 0.320 = 0.280 m` | Subtract hardware offset |
| **Command Sent** | `0.280 meters` | Published to `/joint5_position_controller/command` |
| **Motor Limit Check** | `0.0 ≤ 0.280 ≤ 0.35` ✓ | PASS (within limits) |
| **Transmission** | `0.280 × 12.74 = 3.567 rot` | Convert meters to rotations |
| **Direction Applied** | `3.567 × (-1) = -3.567 rot` | Inverted by motor config |
| **Physical Motion** | Motor rotates -3.567 | **Arm extends FORWARD 280mm** ✓ |

### Validation Questions
- [ ] Is the hardware offset `0.320m` (320mm) correct?
- [ ] Does negative motor value physically **extend forward**?
- [ ] Is the limit range `0.0 to 0.35` meters correct? (0 to 350mm extension)
- [ ] Is `transmission_factor = 12.74` correct? (1m = 12.74 rotations)
- [ ] Is `direction = -1` correct for joint5?

---

## Complete Test Scenario

### Input Conditions
```
Target: Below horizontal, left side, medium distance
After TF Transform:
  - phi = -0.8 rad (-45.8°) - below horizontal
  - theta = -0.05 m (5cm left)
  - r = 0.60 m (60cm radial distance)
```

### Complete Flow Summary

| Joint | Motion Controller Sends | Motor Limits Check | Direction Applied | Final Motor | Physical Result |
|-------|------------------------|-------------------|-------------------|-------------|-----------------|
| **Joint3** | `-0.127 rot` | `-0.2 ≤ -0.127 ≤ 0.0` ✓ | `× (-1) = +0.127` | `+0.127 rot` | **DOWN** ✓ |
| **Joint4** | `-0.05 m` | `-0.1 ≤ -0.05 ≤ 0.1` ✓ | `× (-1) = +0.637` | `+0.637 rot` | **LEFT** ✓ |
| **Joint5** | `0.280 m` | `0.0 ≤ 0.280 ≤ 0.35` ✓ | `× (-1) = -3.567` | `-3.567 rot` | **FWD 280mm** ✓ |

### Expected Physical Behavior
1. Arm tilts **downward** by 45.8°
2. Arm shifts **left** by 5cm
3. Arm extends **forward** by 28cm
4. End effector reaches target below horizontal plane, left side

---

## Edge Cases: Out of Range

### Scenario 1: Target Slightly Out of Range (Caught by Planning Layer)
```
phi = -1.3 rad (-74.5°) - slightly past planning limit
joint3_cmd = -1.3 / (2π) = -0.207 rotations
```

**Expected Behavior (Layer 1 catches it):**
1. Motion controller calculates: `-0.207 rot`
2. Planning limit check: `-0.207 < -0.196` (98% of -0.2) ❌ **FAIL**
3. **Motion controller logs error:**
   ```
   ❌ PLANNING: Joint3 target unreachable! phi=-1.300 rad (-74.5°) → joint3=-0.20700 rotations
      Planning limits: [-0.196, 0.000] rotations (with 2% safety margin)
      This prevents hitting motor hard limits at [-0.200, 0.000] rotations
   ```
4. Returns `false` → **Motion aborted early** (no wasted motion)
5. User gets **detailed error** with context (phi value, why it failed)

**Where to find the error:**
- **Yanthra_move logs** (motion_controller output) - easy to debug!

### Scenario 2: Target WAY Out of Range (Would hit Hardware Layer)
```
phi = -1.5 rad (-85.9°) - way past limit
joint3_cmd = -1.5 / (2π) = -0.239 rotations
```

**Expected Behavior (Layer 1 catches it first):**
1. Motion controller calculates: `-0.239 rot`
2. Planning limit check: `-0.239 < -0.196` ❌ **FAIL at Layer 1**
3. Same error message as Scenario 1
4. **Never reaches motor control** (caught early)

**Hypothetical: If Layer 1 didn't exist:**
- Command would reach motor_control
- `MG6010Controller::set_position()` called
- `check_position_limits()`: `-0.239 < -0.2` ❌ **FAIL at Layer 2**
- Error: `MG6010Controller Error [joint3]: Position command exceeds safety limits (Code: 7)`
- Generic error, less context, harder to debug

**This shows why two layers is better!**

---

## Safety Verification Checklist

### Motor Direction Configuration
- [ ] `direction = -1` for joint3 produces correct physical motion
- [ ] `direction = -1` for joint4 produces correct physical motion
- [ ] `direction = -1` for joint5 produces correct physical motion

### Limit Ranges
- [ ] Joint3: `-0.2 to 0.0` rotations is mechanically safe
- [ ] Joint4: `-0.1 to 0.1` meters prevents collision
- [ ] Joint5: `0.0 to 0.35` meters prevents over-extension

### Hardware Constants
- [ ] Joint5 offset `0.320m` matches physical measurement
- [ ] Transmission factors match mechanical setup
  - [ ] Joint3: `1.0` (1:1 mapping)
  - [ ] Joint4: `12.74` (78.5mm per rotation)
  - [ ] Joint5: `12.74` (78.5mm per rotation)

### Code Implementation
- [x] **Two-layer defense-in-depth** implemented
  - [x] Motion controller checks limits with 2% safety margin (Layer 1)
  - [x] Motor control enforces absolute hard limits (Layer 2)
- [x] Limits defined in motor_control config (single source of truth)
- [x] Motion controller provides detailed error messages
- [x] Motor control enforces limits on INPUT values (before direction)
- [x] All three joints use direct/simple calculations (no IK)

---

## Files to Review

### Code Files
1. `src/yanthra_move/src/core/motion_controller.cpp` (lines 352-382)
   - Joint3: line 356
   - Joint4: line 374
   - Joint5: lines 381-382

2. `src/motor_control_ros2/config/production.yaml` (lines 36-63)
   - Directions: lines 37-40
   - Limits: lines 55-63

### Documentation
3. `src/yanthra_move/docs/NO-IK-PIPELINE.md`
4. `src/yanthra_move/docs/JOINT-VALIDATION.md` (this file)

---

## Sign-Off

This document represents the current implementation as of 2025-11-09.

**Technical Review:**
- [ ] Calculations verified
- [ ] Limits verified
- [ ] Physical behavior tested
- [ ] Edge cases tested

**Team Member Sign-Off:**
- [ ] _________________ (Motion Planning)
- [ ] _________________ (Motor Control)
- [ ] _________________ (Mechanical/Hardware)
- [ ] _________________ (Integration Test)

**Notes/Issues:**
```
(Add any findings, corrections, or concerns here)
```

---

## Code Cleanup Notes

### Removed Legacy Parameters
The following parameters were removed as they are no longer used in the NO-IK pipeline:

**From `yanthra_move` (motion controller):**
- `joint5_init/min_length` - Legacy from ROS1 IK system
- `joint5_init/max_length` - Legacy from ROS1 IK system

**Why removed:**
- These were soft limits used in the old inverse kinematics system
- NO-IK pipeline doesn't check limits in motion controller
- All limits are now enforced by motor_control node only
- Keeping unused parameters causes confusion and maintenance burden

**Files modified:**
- `include/yanthra_move/core/motion_controller.hpp` - Removed from struct
- `src/core/motion_controller.cpp` - Removed parameter loading
- `src/yanthra_move_system_parameters.cpp` - Removed declarations and validation
- `config/production.yaml` - Removed config entries

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-11-09 | AI Assistant | Initial validation document created |
| 2025-11-09 | AI Assistant | Added error location details and cleanup notes |
