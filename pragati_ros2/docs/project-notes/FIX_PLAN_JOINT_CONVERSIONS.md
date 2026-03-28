# Fix Plan: Joint Unit Conversions
**Date**: 2025-11-06  
**Status**: Ready to implement  
**Goal**: Fix joint4 and joint5 extreme commands, validate joint3

---

## What We Know For Sure

### Motor Validation Results ✅

**joint4** (Linear actuator):
```bash
Command: 0.01 → Moves 10mm (0.01m) ✓
Units: METERS (confirmed)
Range: -0.15m to +0.2m
```

**joint5** (Radial extension):
```bash
Command: 0.05 → Moves 50mm (0.05m) ✓
Units: METERS (confirmed)
Range: 0.0m to 0.35m (0.0 = fully retracted)
```

**joint3** (Base rotation):
```bash
Units: ROTATIONS (assumed, needs validation)
Range: 0.0 to 0.25 rotations (0 to 90°)
transmission_factor: 1.0
gear_ratio: 6.0
```

### What's Wrong

**Current code** (`motion_controller.cpp` lines 316-329):
```cpp
// joint4: Treating elevation angle as linear displacement
const double phi_ratio = phi_normalized / (M_PI / 2.0);
const double joint4_cmd_meters = joint4_min + (phi_ratio * joint4_range);
// Result: Commands like 0.0952m which becomes 7.277 motor rotations!

// joint5: Subtracting a "minimum length" from radial distance
const double joint5_cmd_meters = r - LINK5_MIN_LENGTH;
// Result: Commands 0.35m which becomes -26.754 motor rotations!
```

**Problem**: No inverse kinematics - just naive angle scaling

---

## The Fix Strategy

### Core Issue

The code is treating the arm as if:
- `phi` (elevation angle) directly maps to joint4 extension
- `r` (radial distance) directly maps to joint5 extension

**Reality**: This is a 3-DOF robotic arm with linkage geometry. Need proper inverse kinematics.

### What We Need

1. **Arm geometry parameters** (link lengths, offsets)
2. **Frame transformation** (camera_link → robot base frame)
3. **Inverse kinematics solver** (target position → joint positions)

---

## Fix #1: joint3 (Validation + Potential Fix)

### Current Code ✅ (Looks Correct)

```cpp
// motion_controller.cpp lines 310-314
const double theta_normalized = std::fmod(theta + M_PI + joint3_base_offset_rad, 2.0 * M_PI);
const double joint3_cmd_rotations = theta_normalized / (2.0 * M_PI);
```

**Math check**:
- Input: `theta = -2.331 rad` (azimuth angle from camera)
- Normalize: `(-2.331 + 3.142) % 6.283 = 0.811 rad`
- Convert: `0.811 / 6.283 = 0.1291 rotations` ✓
- Motor: `0.1291 × 6.0 gear = 0.774 motor rotations` ✓

**This looks reasonable IF**:
- `theta` is already in the correct frame
- Base offset is correct
- Motors accept rotations as units

### Validation Test for joint3

```bash
# SSH to RPi
ssh ubuntu@192.168.137.253

# Test 1: Command 0.1 rotations (36°)
ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "{data: 0.1}"

# Observe:
# - Does motor rotate?
# - Does it rotate ~36° (0.1 × 360°)?
# - How long does it take?

# Test 2: Command 0.2 rotations (72°)
ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "{data: 0.2}"

# Observe:
# - Does it rotate ~72° from previous position?
# - Is movement smooth?
```

**Expected behavior**:
- ✅ Motor rotates approximately commanded angle
- ✅ Takes 2-5 seconds to complete
- ✅ Final position matches command

**If this works**: joint3 code is correct, just needs frame transformation fix

**If this doesn't work**: Units might be radians, not rotations

### Potential Fix (If Units Are Radians)

```cpp
// If joint3 actually expects RADIANS, not rotations:
const double joint3_cmd_radians = theta_normalized;  // Already in radians
// Don't divide by 2π
```

---

## Fix #2: joint4 (Linear Actuator - CRITICAL)

### Problem Analysis

**Current approach**: Scale elevation angle linearly to actuator range
```cpp
phi = 1.284 rad (73.6° elevation)
phi_ratio = 1.284 / 1.571 = 0.817
joint4_cmd = -0.15 + (0.817 × 0.30) = 0.0952m
```

**Why this is wrong**:
- `phi` is an ANGLE in camera frame
- `joint4` is LINEAR DISPLACEMENT in robot frame
- No kinematic relationship!

### What We Need to Know

**Critical questions**:
1. What is the actual mechanical linkage geometry?
2. Does joint4 control Z-height (vertical) or something else?
3. What are the link lengths and pivot points?

### Simplified Fix (Temporary - Needs Validation)

**Assumption**: joint4 controls elevation, approximately linear with height

```cpp
// Step 1: Transform target from camera frame to base frame
geometry_msgs::msg::PointStamped target_camera;
target_camera.header.frame_id = "camera_link";
target_camera.header.stamp = node_->now();
target_camera.point.x = position.x;
target_camera.point.y = position.y;
target_camera.point.z = position.z;

geometry_msgs::msg::PointStamped target_base;
try {
    tf_buffer_->transform(target_camera, target_base, "yanthra_origin", tf2::durationFromSec(1.0));
} catch (tf2::TransformException &ex) {
    RCLCPP_ERROR(node_->get_logger(), "TF transform failed: %s", ex.what());
    return false;
}

// Step 2: Use Z-height directly (simplified IK)
// Assume: joint4 controls Z-height with approximate linear relationship
const double z_target = target_base.point.z;  // Height in base frame

// Map Z-height to joint4 range
// Need calibration: measure Z-height at joint4 = -0.15m and joint4 = +0.2m
const double Z_AT_MIN = 0.1;   // Z-height when joint4 = -0.15m (MEASURE THIS!)
const double Z_AT_MAX = 0.8;   // Z-height when joint4 = +0.2m (MEASURE THIS!)

// Linear interpolation
const double z_ratio = (z_target - Z_AT_MIN) / (Z_AT_MAX - Z_AT_MIN);
const double joint4_cmd_meters = -0.15 + (z_ratio * 0.35);  // 0.35 = range

// Clamp to safe limits
const double joint4_cmd = std::clamp(joint4_cmd_meters, -0.15, 0.2);
```

**This is still simplified** but better than using elevation angle directly.

### Proper Fix (Needs Link Geometry)

```cpp
// With actual link parameters:
struct LinkParameters {
    double link3_height;      // Height of joint3 above base
    double link4_pivot_z;     // Z-offset of joint4 pivot
    double link4_length_min;  // Length at -0.15m extension
    double link4_length_max;  // Length at +0.2m extension
    double link5_min_length;  // Minimum radial length
};

// Inverse kinematics for 2-link planar arm (in YZ plane after joint3 rotation)
bool solveIK_2Link(
    double r_horizontal,  // Horizontal distance from joint3 axis
    double z_target,      // Target Z-height
    const LinkParameters& params,
    double& joint4_extension,
    double& joint5_extension
) {
    // 2-link IK equations
    // Link 4 + Link 5 must reach (r_horizontal, z_target)
    
    double total_reach = sqrt(r_horizontal*r_horizontal + z_target*z_target);
    double link4_effective = params.link4_length_min + joint4_extension;
    double link5_effective = params.link5_min_length + joint5_extension;
    
    // Standard 2-link IK (law of cosines)
    // ... (need actual geometry to implement)
    
    return true;
}
```

---

## Fix #3: joint5 (Radial Extension - CRITICAL)

### Problem Analysis

**Current approach**: Subtract minimum length from radial distance
```cpp
r = 0.546m (radial distance from camera)
LINK5_MIN_LENGTH = 0.162m
joint5_cmd = 0.546 - 0.162 = 0.384m → clamped to 0.35m
```

**Why this is wrong**:
- `r` is total distance from camera origin
- Doesn't account for joint3 height, joint4 position
- Not the actual reach distance for joint5

### Simplified Fix (Temporary)

```cpp
// After transforming to base frame and accounting for joint3/joint4:
const double r_xy = sqrt(target_base.point.x * target_base.point.x + 
                         target_base.point.y * target_base.point.y);  // Horizontal reach

// Account for the base height and joint4 contribution
const double joint3_height = 0.2;  // Height of joint3 above base (MEASURE THIS!)
const double joint4_horizontal_reach = 0.15;  // Horizontal reach from joint4 (MEASURE THIS!)

// Required extension for joint5
const double joint5_required = r_xy - joint4_horizontal_reach;

// Clamp to safe limits
const double joint5_cmd = std::clamp(joint5_required, 0.0, 0.35);
```

### Proper Fix (With Full IK)

```cpp
// joint5 extension comes from solving 2-link IK together with joint4
// Can't compute joint5 independently - must solve as coupled system

auto [joint4_ext, joint5_ext] = solve_2link_ik(
    r_horizontal,
    z_target,
    link_params
);

const double joint4_cmd = -0.15 + joint4_ext;  // Convert extension to position
const double joint5_cmd = joint5_ext;          // Already in meters
```

---

## Implementation Plan

### Phase 1: Quick Fix (Can Deploy Today)

**Goal**: Stop extreme motor commands immediately

**File**: `motion_controller.cpp`

**Changes**:

1. **Add TF transform** (lines 272-290):
```cpp
bool MotionController::executeApproachTrajectory(const geometry_msgs::msg::Point& position) {
    RCLCPP_INFO(node_->get_logger(), "🎯 Executing approach trajectory to cotton at [%.3f, %.3f, %.3f] meters (camera frame)",
                position.x, position.y, position.z);
    
    // CRITICAL FIX: Transform from camera frame to base frame FIRST
    geometry_msgs::msg::PointStamped target_camera;
    target_camera.header.frame_id = "camera_link";
    target_camera.header.stamp = node_->now();
    target_camera.point = position;
    
    geometry_msgs::msg::PointStamped target_base;
    try {
        target_base = tf_buffer_->transform(target_camera, "yanthra_origin", tf2::durationFromSec(1.0));
        RCLCPP_INFO(node_->get_logger(), "   📍 Transformed to base frame: [%.3f, %.3f, %.3f]",
                    target_base.point.x, target_base.point.y, target_base.point.z);
    } catch (const tf2::TransformException& ex) {
        RCLCPP_ERROR(node_->get_logger(), "❌ TF transform failed: %s", ex.what());
        return false;
    }
    
    // Now work in base frame
    const double x_base = target_base.point.x;
    const double y_base = target_base.point.y;
    const double z_base = target_base.point.z;
```

2. **Fix joint4 calculation** (replace lines 316-325):
```cpp
    // joint4: Use Z-height in base frame (simplified IK)
    // TODO: Replace with proper 2-link IK solver
    const double Z_AT_JOINT4_MIN = 0.1;   // Calibrate: Z when joint4=-0.15m
    const double Z_AT_JOINT4_MAX = 0.8;   // Calibrate: Z when joint4=+0.2m
    
    const double z_ratio = std::clamp(
        (z_base - Z_AT_JOINT4_MIN) / (Z_AT_JOINT4_MAX - Z_AT_JOINT4_MIN),
        0.0, 1.0
    );
    
    const double joint4_cmd_meters = -0.15 + (z_ratio * 0.35);  // 0.35 = total range
    
    RCLCPP_INFO(node_->get_logger(), "   joint4: z_base=%.3f → z_ratio=%.3f → cmd=%.3f m",
                z_base, z_ratio, joint4_cmd_meters);
```

3. **Fix joint5 calculation** (replace lines 327-329):
```cpp
    // joint5: Horizontal reach in base frame
    const double r_horizontal = sqrt(x_base*x_base + y_base*y_base);
    
    // Subtract contributions from base and joint4
    const double JOINT3_HEIGHT = 0.2;           // Calibrate!
    const double JOINT4_BASE_REACH = 0.15;      // Calibrate!
    
    const double joint5_required = r_horizontal - JOINT4_BASE_REACH;
    const double joint5_cmd_meters = std::clamp(joint5_required, 0.0, 0.35);
    
    RCLCPP_INFO(node_->get_logger(), "   joint5: r_horiz=%.3f → required=%.3f → cmd=%.3f m",
                r_horizontal, joint5_required, joint5_cmd_meters);
```

4. **Fix joint3 calculation** (replace lines 310-314):
```cpp
    // joint3: Base rotation to point at target (azimuth in base frame)
    const double theta_base = atan2(y_base, x_base);
    
    // Normalize to [0, 2π] then convert to rotations [0, 1]
    const double theta_normalized = std::fmod(theta_base + 2.0*M_PI, 2.0*M_PI);
    const double joint3_cmd_rotations = theta_normalized / (2.0 * M_PI);
    
    RCLCPP_INFO(node_->get_logger(), "   joint3: theta_base=%.3f rad → cmd=%.4f rot",
                theta_base, joint3_cmd_rotations);
```

5. **Remove old polar conversion** (delete lines 276-283):
```cpp
    // DELETE THIS - we calculate angles in base frame now
    // double r = 0.0, theta = 0.0, phi = 0.0;
    // yanthra_move::coordinate_transforms::convertXYZToPolarFLUROSCoordinates(...)
```

### Phase 2: Calibration (Before Next Test)

**Measure these physical parameters**:

1. **Joint3 height**: Height of joint3 rotation axis above base
2. **Z-height at joint4 limits**: 
   - Command joint4 to -0.15m, measure Z-height with ruler
   - Command joint4 to +0.2m, measure Z-height
3. **Horizontal reach at joint5 limits**:
   - Command joint5 to 0.0m (retracted), measure horizontal reach
   - Command joint5 to 0.35m (extended), measure horizontal reach
4. **Base frame origin**: Where is "yanthra_origin" physically located?

### Phase 3: Proper IK (Next Sprint)

**Create new file**: `inverse_kinematics.cpp`

**Implement**:
1. 2-link planar IK solver (joint4 + joint5 in vertical plane)
2. Forward kinematics for validation
3. Jacobian for trajectory planning (future)

---

## Testing Strategy

### Test 1: Validate Fixes (After Phase 1)

```bash
# On RPi after deploying fixes
ssh ubuntu@192.168.137.253
cd ~/pragati_ros2
colcon build --packages-select yanthra_move
source install/setup.bash

# Run system
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true \
  enable_arm_client:=false \
  enable_cotton_detection:=false

# Watch logs for motor commands
# Should now see:
# - joint4: commands in range -0.15 to 0.2 (not 0.09!)
# - joint5: commands in range 0.0 to 0.35 (not 0.35 always!)
# - joint3: similar commands as before (already working)
```

### Test 2: Measure Actual Movements

```bash
# Direct motor test with physical measurement
ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "{data: 0.0}"
# Measure: Height of end-effector above base

ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "{data: 0.1}"
# Measure: New height (should be higher)

ros2 topic pub --once /joint5_position_controller/command std_msgs/Float64 "{data: 0.0}"
# Measure: Horizontal distance from base

ros2 topic pub --once /joint5_position_controller/command std_msgs/Float64 "{data: 0.2}"
# Measure: New distance (should be 200mm further)
```

### Test 3: Full Pick Cycle

```bash
# Place ArUco marker, run pick cycle
# Observe:
# - Do motors move to reasonable positions?
# - Are movements smooth (not hitting limits)?
# - Do picks succeed with better accuracy?
```

---

## Expected Results After Fix

### Before (Current State)

```
Pick #1: [-0.106, -0.112, 0.524] camera frame
Commands:
  joint3: 0.1291 rot → 0.774 motor rotations
  joint4: 0.0952 m → 7.277 motor rotations ❌
  joint5: 0.3500 m → -26.754 motor rotations ❌
```

### After Phase 1 Fix

```
Pick #1: [-0.106, -0.112, 0.524] camera frame
Transformed to base: [~0.5, ~0.0, ~0.3] (approximate)
Commands:
  joint3: ~0.0 rot → 0.0 motor rotations ✓ (pointing forward)
  joint4: ~0.05 m → ~0.4 motor rotations ✓ (reasonable elevation)
  joint5: ~0.25 m → ~3.2 motor rotations ✓ (reasonable extension)
```

**Motor rotations should be <5 for all joints!**

---

## Code Changes Summary

### Files to Modify

1. **`motion_controller.cpp`** (lines 272-346)
   - Add TF transform
   - Replace polar coordinates with base frame coordinates
   - Fix joint4 calculation (use Z-height)
   - Fix joint5 calculation (use horizontal reach)
   - Update joint3 calculation (use base frame theta)

### Dependencies Needed

```cpp
// Add includes at top of motion_controller.cpp:
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>
```

### Parameters to Add (for calibration)

```yaml
# In pragati_complete.launch.py or config file:
arm_kinematics:
  joint3_height: 0.2          # Measure!
  joint4_z_at_min: 0.1        # Measure at -0.15m
  joint4_z_at_max: 0.8        # Measure at +0.2m
  joint4_horizontal_reach: 0.15  # Measure!
  joint5_min_length: 0.162    # From existing config
```

---

## Rollback Plan

**If Phase 1 fix doesn't work**:

```bash
# Revert to backup
cd ~/pragati_ros2/src/yanthra_move/src/core
cp motion_controller.cpp.before_fix motion_controller.cpp
colcon build --packages-select yanthra_move
```

**Keep backups**:
- `motion_controller.cpp.before_transform_fix` (current state)
- `motion_controller.cpp.after_transform_fix` (Phase 1)
- `motion_controller.cpp.with_proper_ik` (Phase 3)

---

## Success Criteria

**Phase 1 is successful if**:
1. ✅ Motor commands are within safe ranges:
   - joint3: 0.0 to 0.25 rotations
   - joint4: -0.15 to 0.2 meters
   - joint5: 0.0 to 0.35 meters
2. ✅ Motor rotations are reasonable (<5 rotations for typical movements)
3. ✅ No extreme values in logs (no 7.x or -26.x rotations)
4. ✅ Picks still succeed (or better success rate)
5. ✅ No mechanical damage or limit hitting

**Phase 2 is successful if**:
1. ✅ Calibration parameters measured and documented
2. ✅ Commands produce expected physical movements
3. ✅ End-effector reaches target positions within ±50mm

**Phase 3 is successful if**:
1. ✅ Proper IK implemented and validated
2. ✅ End-effector reaches target positions within ±10mm
3. ✅ Pick success rate improves to >95%

---

**Ready to implement Phase 1?** Let me know and I can create the actual code changes!
