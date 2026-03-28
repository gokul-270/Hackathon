# Enhanced Data Flow Logging - Validation Guide

## What the New Logging Shows

The system now logs **5 complete transformation steps** for each ArUco marker corner:

```
╔═══════════════════════════════════════════════════════════╗
║  VALIDATION: Camera → TF → Polar → IK → Motors           ║
╚═══════════════════════════════════════════════════════════╝
```

### [1] CAMERA INPUT (camera_link frame)
- **X**: left(-) / right(+) in meters
- **Y**: down(-) / up(+) in meters  
- **Z**: depth in meters

**Maps to joints:**
- X → joint3 (rotation angle theta)
- Y → joint4 (elevation)
- Z → joint5 (extension)

### [2] AFTER TF TRANSFORM (base_link frame)
Shows coordinates after ROS2 TF2 transform from camera to robot base.

### [3] POLAR COORDINATES
- **r (radius)**: Distance from base to target
- **theta (azimuth)**: Horizontal rotation angle for joint3
- **phi (elevation)**: Vertical angle from horizontal plane

### [4] INVERSE KINEMATICS RESULTS
- **joint3 (rotation)**: Shows clamped value vs original theta
- **joint4 (elevation)**: Linear position with z_ratio factor
- **joint5 (extension)**: Shows required vs actual (clamped) value

### [5] FINAL MOTOR COMMANDS
- Raw command → rotations → motor rotations (with 6:1 gear ratio)
- Sent to MG6010 controller

## Current Issues to Validate

### joint3: Always 0.2 rad (11.5°)
- **Why**: `std::abs()` converts all negative theta to positive, then clamps to max
- **Expected**: Should vary based on camera X position
- **Current**: ALL corners show `0.2 rad`

### joint4: Values Vary Correctly ✅
- Corner 1: ~0.0266 m
- Corner 2: ~0.0269 m
- Corner 3: ~0.0370 m
- Corner 4: ~0.0578 m

**Direction**: Now inverted to `-1` to match physical movement

### joint5: Always 0.0000 m
- **Why**: `BASE_REACH = 0.35 m` too large
- **Formula**: `joint5_required = r_horiz_est - BASE_REACH`
- **Result**: Always negative → clamped to 0.0 m
- **Fix needed**: Reduce `BASE_REACH` to ~0.15-0.20 m

## How to Use This Logging

1. **Run the system** and observe one corner's complete flow
2. **Verify camera values** match physical ArUco position
3. **Check TF transform** - should be minimal if camera is near base
4. **Validate polar conversion** - theta should vary with X position
5. **Examine IK clamping** - where is data being lost?
6. **Confirm motor commands** - do they match expected physical movement?

## Next Steps

After validation with enhanced logging:
1. Fix joint3 direction issue (needs positive/negative rotation)
2. Adjust `BASE_REACH` value for joint5
3. Verify joint4 physical movement matches Y camera coordinate

---
*Generated: 2025-11-07*
*File: src/yanthra_move/src/core/motion_controller.cpp*
*Backup: motion_controller.cpp.backup*
