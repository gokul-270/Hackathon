# Testing Checklist - 2025-11-07
**Phase 1 Fix Testing**

---

## Quick Start

```bash
# 1. On RPi
ssh ubuntu@192.168.137.253
cd ~/pragati_ros2

# 2. Build (if copying files manually)
colcon build --packages-select yanthra_move
source install/setup.bash

# 3. Run test
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true
```

---

## What to Watch For

### ✅ GOOD Signs:
- `Motor rotation estimates <5` 
- `Safety check passed`
- joint3 commands in radians (like `-0.2 rad`)
- joint4/5 commands reasonable (<0.35m)
- Timing shows realistic values (2-5 seconds per joint)

### ⚠️ BAD Signs:
- `WARNING: Motor rotation estimates >5!`
- Motors hitting limits
- Mechanical grinding sounds
- joint3 barely moving (units wrong)
- Picks failing

---

## Critical Tests

### Test 1: joint3 Units (5 min)
```bash
# Test BEFORE running full cycle!
ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "{data: -0.4}"
```
**Should rotate ~23°** (if radians are correct)  
**If barely moves** → Units still wrong, STOP testing

### Test 2: Full Pick Cycle (2 min)
Run launch command above, watch logs

### Test 3: Log Analysis
Check for:
- All motor estimates <5 ✓
- Picks succeeded 4/4 ✓
- No warnings ✓

---

## Expected Log Output

```
🎯 Executing approach trajectory...
   📐 Polar: r=0.546 m, theta=-2.329 rad (-133.5°)
   ⚙️  joint3: clamped=-0.900 rad (-51.6°)
   ⚙️  joint4: z_est=0.524 m, cmd=0.062 m
   ⚙️  joint5: r_horiz_est=0.154 m, cmd=0.000 m
🚀 Motor commands:
   joint3: -0.9000 rad → est. -0.86 motor rotations
   joint4: 0.0620 m → est. 0.79 motor rotations
   joint5: 0.0000 m → est. 0.00 motor rotations
✅ Safety check passed
   → Moving joint3...
      ✓ completed in 2134 ms
   📊 Timing: total=4112ms
✅ Approach completed in 4215 ms
```

---

## If Something Goes Wrong

### joint3 doesn't move correctly
```bash
# Rollback
cd ~/pragati_ros2/src/yanthra_move/src/core
cp motion_controller.cpp.before_phase1_fix motion_controller.cpp
cd ~/pragati_ros2
colcon build --packages-select yanthra_move
```

### Motor estimates >5
Check logs for which joint, may need calibration adjustment

### Picks fail
Compare with old behavior - might be improvement area for Phase 2

---

## Data to Collect

- [ ] Screenshot of logs showing motor estimates
- [ ] Video of actual motor movements
- [ ] Pick success rate (X/4)
- [ ] Individual joint timing values
- [ ] Any warnings or errors
- [ ] Motor rotation estimates vs actual behavior

---

## Success = Ready for Phase 2

If all checks pass:
1. ✅ Measurements for Z_AT_MIN, Z_AT_MAX, BASE_REACH
2. ✅ Position feedback implementation
3. ✅ GPIO end-effector testing
4. ✅ Parallel movement optimization

---

**Estimated testing time**: 15-20 minutes  
**Critical**: Test joint3 units FIRST before full cycle!
