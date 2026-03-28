# VEH1: Velocity Kinematics Origin Fix

## Problem: Rear Wheels Not Steering

### Root Cause
The URDF had `base-v1` (origin) positioned at the **rear axle center**, which placed both rear wheels at **x=0.0**. 

In velocity kinematics:
```
viy = omega * wheel_x
```

When `wheel_x = 0`, then `viy = 0` for all commands, which means:
```
steering_angle = atan2(0, vix) = 0°
```

The rear wheels could only do **differential drive** (different speeds) but never **steer**.

---

## Solution: Move Origin to Robot Center

Changed origin from **rear axle** to **geometric center** of robot.

### Old Configuration (BROKEN)
```
Origin: Rear axle center
Front:  x=+1.300, y=+0.000  ← Only this wheel steered
Left:   x=+0.000, y=+0.900  ← Never steered (x=0!)
Right:  x=+0.000, y=-0.900  ← Never steered (x=0!)
```

### New Configuration (FIXED)
```
Origin: Robot geometric center
Front:  x=+0.755, y=+0.010  ✓ Steers
Left:   x=-0.755, y=+0.910  ✓ Steers (x≠0!)
Right:  x=-0.755, y=-0.910  ✓ Steers (x≠0!)
```

---

## Test Results Comparison

### Command: vx=0.4 m/s, omega=0.2 rad/s

**OLD (broken):**
```
Front: steer=+33.02° ✓
Left:  steer= +0.00° ✗ (no steering!)
Right: steer= +0.00° ✗ (no steering!)
```

**NEW (fixed):**
```
Front: steer=+20.78° ✓
Left:  steer=-34.71° ✓ (NOW STEERS!)
Right: steer=-14.54° ✓ (NOW STEERS!)
```

---

## Changes Made

### 1. URDF Changes ([vehicle_control/urdf/vehicle.urdf](../urdf/vehicle.urdf))

Shifted all `base-v1_Rigid-*` joint origins by (-0.650, -0.900):

```xml
<!-- OLD -->
<joint name="base-v1_Rigid-11" type="fixed">
    <origin xyz="1.3 0 0.9" .../>  <!-- Front -->
    
<joint name="base-v1_Rigid-12" type="fixed">
    <origin xyz="0 0 0" .../>  <!-- Right -->
    
<joint name="base-v1_Rigid-13" type="fixed">
    <origin xyz="0 0 1.8" .../>  <!-- Left -->

<!-- NEW -->
<joint name="base-v1_Rigid-11" type="fixed">
    <origin xyz="0.65 0 0.01" .../>  <!-- Front -->
    
<joint name="base-v1_Rigid-12" type="fixed">
    <origin xyz="-0.65 0 -0.9" .../>  <!-- Right -->
    
<joint name="base-v1_Rigid-13" type="fixed">
    <origin xyz="-0.65 0 0.91" .../>  <!-- Left -->
```

### 2. Kinematics Node Changes ([vehicle_control/vehicle_control/kinematics_node.py](../vehicle_control/kinematics_node.py))

Updated wheel position parameters:

```python
# OLD
self.declare_parameter('front_wheel_position', [1.3, 0.0])
self.declare_parameter('left_wheel_position', [0.0, 0.9])
self.declare_parameter('right_wheel_position', [0.0, -0.9])

# NEW
self.declare_parameter('front_wheel_position', [0.755, 0.010])
self.declare_parameter('left_wheel_position', [-0.755, 0.910])
self.declare_parameter('right_wheel_position', [-0.755, -0.910])
```

---

## Algorithm Validation

The velocity kinematics algorithm was **ALWAYS CORRECT**:

```python
vix = vx - omega * wheel_y
viy = omega * wheel_x
steering_angle = atan2(viy, vix)
```

**This is the same algorithm used by `triwheel_robot`** which works perfectly.

The issue was purely **geometric configuration** - the URDF origin placement prevented rear wheels from having non-zero x-coordinates.

---

## Why This Matters

### Differential Drive vs Full Velocity Kinematics

**Differential Drive** (old config with x=0 rear wheels):
- Front wheel: steers + drives
- Rear wheels: only drive (differential speeds create rotation)
- Like a car with Ackermann front steering + fixed rear axle

**Full Velocity Kinematics** (new config with all x≠0):
- ALL wheels: steer + drive independently
- True omni-directional capability
- Each wheel follows the instantaneous velocity field
- Much better maneuverability

---

## Verification

Run the test script:
```bash
cd ~/steering\ control/vehicle_control
./scripts/test_3wheel_steering.sh
```

Watch for:
1. **Logs show non-zero steering for all 3 wheels**
2. **In Gazebo, all 3 wheels physically rotate** when turning
3. **Smoother, more coordinated motion** during complex maneuvers

---

## Triwheel Robot Reference

The `triwheel_robot` package uses these positions:
```python
front:      x=+0.35, y=+0.05
rear_left:  x=-0.25, y=+0.22
rear_right: x=-0.20, y=-0.25
```

Notice **ALL wheels have non-zero x**! This is why triwheel worked perfectly even with a "dummy URDF" - the kinematics were configured correctly from the start.

---

## Summary

✅ **Origin moved** from rear axle to robot center  
✅ **All wheels now have x≠0** → all can steer  
✅ **Algorithm unchanged** - it was always correct  
✅ **Matches triwheel_robot** velocity kinematics approach  
✅ **True 3-wheel independent steering** now active
