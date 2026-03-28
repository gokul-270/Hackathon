# Transmission Factor Fix Summary

## Problems Fixed:

### 1. ❌ Double Gear Compensation (Joint3)
**OLD:**
```yaml
transmission_factors: [6.0, ...]
homing_positions: [4200.0, ...]  # Already × 6!
```
Result: `4200° × 6 = 25,200°` motor angle (70 rotations!)

**NEW:**
```yaml
transmission_factors: [6.0, ...]
homing_positions: [180.0, ...]  # Output shaft angle
```
Result: `180° × 6 = 1,080°` motor angle (3 rotations) ✅

---

### 2. ❌ Wrong Transmission Factor (Joint4 & Joint5)
**OLD:**
```yaml
transmission_factors: [6.0, 480.1, 480.1]
```
Result: Motors rotate 480 times for simple movements!

**NEW:**
```yaml
transmission_factors: [6.0, 12.7, 12.7]
```
Result: Motors rotate 12.7 times (correct gear ratio) ✅

---

## Complete Configuration:

```yaml
# mg6010_three_motors.yaml

transmission_factors:
  - 6.0      # joint3 (rotational: 1:6 gear)
  - 12.7     # joint4 (prismatic: 12.7:1 gear ratio)
  - 12.7     # joint5 (prismatic: 12.7:1 gear ratio)

homing_positions:
  - 180.0    # joint3: 180° output × 6.0 = 1080° motor (3 rotations)
  - 360.0    # joint4: 360° output × 12.7 = 4572° motor (12.7 rotations)
  - 360.0    # joint5: 360° output × 12.7 = 4572° motor (12.7 rotations)
```

---

## Motor Movement Comparison:

| Joint | OLD Movement | NEW Movement | Improvement |
|-------|--------------|--------------|-------------|
| **joint3** | 70 rotations | 3 rotations | **23× less!** |
| **joint4** | 172,800° | 4572° | **38× less!** |
| **joint5** | 115,200° | 4572° | **25× less!** |

---

## How to Apply:

```bash
cd ~/pragati_ros2

# The fix is already applied to the source file
# Just rebuild:
colcon build --packages-select motor_control_ros2 --symlink-install

# Source the environment
source install/setup.bash

# Test with reduced movements
ros2 launch yanthra_move pragati_complete.launch.py
```

---

## Expected Behavior After Fix:

✅ **Smooth homing:** Motors move directly to home position with minimal rotation
✅ **Correct compensation:** Gear ratio applied only once (by controller)
✅ **Reasonable values:** 180°-360° output positions = 3-13 motor rotations
✅ **No vigorous movements:** Controlled, predictable motor motion

---

## Technical Details:

### Position Calculation Flow (CORRECTED):

```
YAML Config (output angle)
    ↓
180.0° (joint3 output)
    ↓
Convert to radians: 3.142 rad
    ↓
Controller applies transmission: 3.142 × 6.0 = 18.85 rad
    ↓
Motor moves to: 18.85 rad = 1080° = 3 rotations ✅
```

### Why 12.7 for Joint4/5?

- Joint4 and Joint5 are **linear actuators** with **rack-and-pinion** mechanism
- Gear ratio: **12.7:1** (motor shaft : output shaft)
- One full rotation of output (360°) = 12.7 rotations of motor
- This is the **correct mechanical gear ratio** for your robot

### Why 6.0 for Joint3?

- Joint3 is a **rotational joint** (base rotation)
- Internal motor gear: **6:1** (motor : output)
- One full rotation of output (360°) = 6 rotations of motor

---

## Verification:

After launching, check the logs:
```
[mg6010_controller]: joint3: transmission_factor=6.000, direction=1
[mg6010_controller]: joint4: transmission_factor=12.700, direction=1
[mg6010_controller]: joint5: transmission_factor=12.700, direction=1
[mg6010_controller]: [4/4] Moving to arm homing position: 180.0°
```

✅ Should see "180.0°" not "4200.0°"
✅ Should see "transmission_factor=12.700" not "480.100"
