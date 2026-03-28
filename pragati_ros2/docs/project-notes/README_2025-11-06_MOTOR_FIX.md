# Motor Unit Conversion Fix - 2025-11-06
**Problem**: Extreme motor commands (7-26 rotations) despite 100% pick success  
**Root Cause**: Missing coordinate transform + inverse kinematics  
**Status**: Ready to implement (need hardware access)

---

## TL;DR

✅ **Motors work correctly** - joint4/5 accept METERS (empirically validated)  
✅ **URDF has all geometry** - link lengths, offsets, joint types  
⚠️ **CRITICAL: joint3 is REVOLUTE** - expects RADIANS, not rotations!  
❌ **Code calculates in wrong frame** - camera frame instead of base frame  
❌ **No inverse kinematics** - treats angles as linear distances  
✅ **Limits saved hardware** - MG6010 clamps extreme commands internally

**After fix**: Motor commands will be <5 rotations, precision positioning possible

---

## Problem Summary

### Test Results
- **8/8 picks successful** with ArUco detection
- **joint4**: Commanded 0.0952m → 7.277 motor rotations (2619°)
- **joint5**: Commanded 0.35m → -26.754 motor rotations (-9631°)
- **joint3**: Working after theta normalization fix

### Why It "Works" Despite Being Wrong
MG6010 controller has internal safety limits that clamp extreme commands. Motors move to max/min position instead of commanded value, which happens to be "close enough" for cotton picking with vacuum end-effector.

**This is dangerous**: Relying on undefined behavior, no precision, risk of damage.

---

## Motor Validation (Empirical Testing)

**joint4** (Linear actuator):
```bash
Command: 0.01 → Moved 10mm ✓ (Units = METERS confirmed)
Command: 0.05 → Moved 50mm ✓
Physical limit at +0.2m (hits barrier)
```

**joint5** (Radial extension):
```bash  
Command: 0.05 → Moved 50mm ✓ (Units = METERS confirmed)
Range: 0.0m (fully retracted) to 0.35m (max extension)
```

**joint3** (Base rotation):
```bash
Units: RADIANS (from URDF - needs validation test)
Range: -0.9 to 0.0 rad (-51.6° to 0°)
```

---

## URDF Analysis (MG6010_final.urdf)

### Critical Discovery: joint3 is REVOLUTE!

```xml
<joint name="joint 3" type="revolute">
  <axis xyz="0 -1 0"/>  <!-- Rotates around Y-axis -->
  <limit lower="-0.9" upper="0.0" />  <!-- RADIANS, not rotations! -->
</joint>
```

**Your code divides by 2π (converts radians → rotations) - WRONG!**

Should send RADIANS directly to joint3.

### Link Geometry from URDF

```
base_link (0, 0, 0)
    ↓ +459mm Z
joint2 origin (0, 0, 0.45922)
    ↓ +334mm Y  
link4 origin (0, 0.33411, 0)
    ↓ -127mm Z, -67mm X
joint3 origin (-0.0675, 0.042, -0.127)
    ↓ -82mm Y
yanthra_link (0, -0.082, 0)
    ↓ +278mm X (link5 minimum length)
link5_origin (0.27774, 0.00375, -0.001)
    ↓ extends +X (0 to 0.75m)
link5 (prismatic joint)
```

### Joint Types

| Joint | Type | Axis | Limits | Units |
|-------|------|------|--------|-------|
| joint2 | prismatic | Z | 0.1-0.32m | meters |
| joint3 | **revolute** | Y | -0.9-0.0 | **radians** |
| joint4 | prismatic | -Y | inverted! | meters |
| joint5 | prismatic | X | 0-0.75m | meters |

---

## Root Cause: Three Issues

### Issue 1: No Coordinate Transform
Code calculates in **camera frame**, but needs **robot base frame**.

```cpp
// CURRENT (WRONG):
position.x, position.y, position.z  // Camera frame
cartesianToPolar(x, y, z, &r, &theta, &phi);  // Wrong frame!

// NEEDED:
tf_buffer_->transform(camera_point, "yanthra_origin");  // Transform first!
```

### Issue 2: Missing Inverse Kinematics  
Code treats elevation angle `phi` (radians) as if it's linear displacement (meters).

```cpp
// CURRENT (WRONG):
joint4_cmd = -0.15 + (phi/1.571 * 0.30);  // Angle → distance mapping invalid!

// NEEDED:
[j3, j4, j5] = inverse_kinematics(target_base, link_params);  // Proper IK
```

### Issue 3: No Position Validation
System waits only 100ms after commanding motors, declares "success" without checking if target reached.

```cpp
// joint_move.cpp line 125:
if (wait) {
    rclcpp::sleep_for(std::chrono::milliseconds(100));  // Only 100ms!
}
// Then returns immediately - NO position feedback!
```

---

## Questions Answered

### Q: Don't we get linkage data from URDF?
**A: YES!** Your friend is correct. All dimensions in `MG6010_final.urdf`:
- Link offsets: 459mm, 334mm, 127mm, 82mm, 278mm
- Joint types: revolute vs prismatic
- Joint limits: -0.9-0.0 rad, 0-0.75m, etc.

### Q: Will fixes work for cotton detection or only ArUco?
**A: BOTH!** Motion controller fix is detection-agnostic. Works for:
- ✅ ArUco marker detection
- ✅ Cotton detection (YOLO/ML)
- ✅ Manual position commands
- ✅ Any future vision system

### Q: Motor movements rusty - fix later?
**A: Good plan.** Separate issues:
1. **Unit conversions** (Phase 1) - Fix first, stops extreme commands
2. **Motion smoothness** (Later) - Trajectory planning, velocity profiles

### Q: Homing happens at launch?
**A: YES!** Sequential homing:
1. joint5 (prismatic) - ODrive ID 2
2. joint3 (revolute) - ODrive ID 0
3. joint4 (prismatic) - ODrive ID 1

Takes 30-40 seconds total. Can be skipped with `skip_homing: true` parameter.

### Q: Exit doesn't do homing?
**A: Correct.** System moves to **parking position** (not homing) on exit:
- Faster than homing (no limit switch seeking)
- Safe storage position
- Next launch will re-home anyway

### Q: EE testing with erratic movements?
**A: Smart to wait!** Current extreme commands would cause unpredictable end-effector movement. Test GPIO after Phase 1 fix when movements are controlled.

### Q: Limits prevent damage?
**A: YES - Critical safety!** MG6010 clamps extreme commands to safe range. Without limits, hardware would be destroyed. **Keep limits even after fix** as safety backup.

---

## The Fix

### Phase 0: URDF Extraction (No hardware needed)
Can do right now:
1. Extract all link offsets from URDF
2. Calculate forward kinematics
3. Implement inverse kinematics solver

### Phase 1: Code Changes (Need hardware to test)

**File**: `motion_controller.cpp`

**Change 1**: Add TF transform
```cpp
// Transform from camera frame to base frame BEFORE calculations
geometry_msgs::msg::PointStamped target_camera;
target_camera.header.frame_id = "camera_link";
target_camera.point = position;

auto target_base = tf_buffer_->transform(target_camera, "yanthra_origin", tf2::durationFromSec(1.0));

const double x_base = target_base.point.x;
const double y_base = target_base.point.y;
const double z_base = target_base.point.z;
```

**Change 2**: Fix joint3 - send RADIANS not rotations
```cpp
// Calculate azimuth in base frame
const double theta_base = atan2(y_base, x_base);

// Normalize to [-π, π] → [-0.9, 0.0] range
const double theta_normalized = std::clamp(theta_base, -0.9, 0.0);

// Send RADIANS directly (joint3 is revolute!)
const double joint3_cmd = theta_normalized;  // Don't divide by 2π!
```

**Change 3**: Fix joint4/5 - use proper IK
```cpp
// Simplified IK (Phase 1) - use Z-height and horizontal reach
const double z_ratio = (z_base - Z_AT_MIN) / (Z_AT_MAX - Z_AT_MIN);
const double joint4_cmd = -0.15 + (z_ratio * 0.35);

const double r_horizontal = sqrt(x_base*x_base + y_base*y_base);
const double joint5_cmd = r_horizontal - LINK5_MIN_LENGTH;

// Clamp to safety limits
joint4_cmd = std::clamp(joint4_cmd, -0.15, 0.2);
joint5_cmd = std::clamp(joint5_cmd, 0.0, 0.35);
```

**Change 4**: Add includes
```cpp
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>
```

### Phase 2: Validation Tests (Tomorrow with hardware)

**Test 1**: Verify joint3 units
```bash
# Should rotate ~23° if units are radians
ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "{data: -0.4}"

# Should rotate ~46° if units are radians  
ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "{data: -0.8}"
```

**Test 2**: Run full pick cycle
```bash
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true
```

Watch logs for motor commands - should see values <5 rotations.

**Test 3**: Test end-effector GPIO
After confirming movements are controlled, test vacuum and EE motor.

### Phase 3: Proper IK (Next sprint)
Implement full 2-link planar IK solver using URDF link parameters.

---

## Success Criteria

**Phase 1 successful if:**
- ✅ Motor commands in safe ranges: j3[-0.9,0], j4[-0.15,0.2], j5[0,0.35]
- ✅ Motor rotations <5 for typical movements
- ✅ No extreme values in logs (no 7.x or -26.x)
- ✅ Picks still succeed (or better)
- ✅ No mechanical damage

**Current**: joint4 0.0952m → 7.277 rotations, joint5 0.35m → -26.754 rotations  
**After fix**: joint4 ~0.05m → ~0.4 rotations, joint5 ~0.25m → ~3.2 rotations

---

## Files

**Active docs (2):**
- `README_2025-11-06_MOTOR_FIX.md` - This file (problem + fix + Q&A)
- `FIX_PLAN_JOINT_CONVERSIONS.md` - Detailed implementation guide

**Archive:**
- `archive/2025-11-06-analysis/` - Original analysis docs (4 files)

**Code to modify:**
- `src/yanthra_move/src/core/motion_controller.cpp` (lines 272-346)

**URDF reference:**
- `src/robot_description/urdf/MG6010_final.urdf`

---

## Next Steps

**Today (no hardware):**
- [ ] Extract URDF link parameters programmatically
- [ ] Implement forward kinematics from URDF
- [ ] Prepare inverse kinematics solver
- [ ] Create backup of current motion_controller.cpp

**Tomorrow (with hardware):**
- [ ] Test joint3 units validation (radians vs rotations)
- [ ] Deploy Phase 1 fixes
- [ ] Run full pick cycle test
- [ ] Verify motor commands <5 rotations
- [ ] Test end-effector GPIO if movements controlled

---

**Created**: 2025-11-06  
**Hardware Access**: Tomorrow  
**Priority**: HIGH - Extreme commands risk hardware damage  
**Impact**: Enables precision positioning, safe operation
