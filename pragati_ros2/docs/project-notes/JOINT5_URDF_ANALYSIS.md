# Joint5 URDF Analysis - Understanding the Kinematic Chain

## URDF Structure (MG6010_final.urdf)

### Kinematic Chain
```
base_link
  ↓ [joint2 - prismatic Z, limits: 0.1 to 0.32m]
link2
  ↓ [joint4 - prismatic -Y, limits: 0.250 to -0.350m]  ⚠️ INVERTED LIMITS!
link4
  ↓ [yanthra_link connection]
link5_origin (fixed to yanthra_link)
  ↓ [joint5 - prismatic +X, limits: 0 to 0.750m]
link5
```

### Joint5 Definition (Prismatic - Extension)
```xml
<joint type="prismatic">
  <origin xyz="0.27774 0.00375 -0.001" rpy="0 0 0" />
  <parent link="link5_origin" />
  <child link="link5" />
  <axis xyz="1 0 0" />  <!-- Moves in +X direction -->
  <limit
    lower="0"
    upper="0.750"
    effort="0"
    velocity="0" />
</joint>
```

### Critical Understanding

**Origin Offset**: `xyz="0.27774 0.00375 -0.001"`
- This means link5_origin is **0.27774 m forward** from link5_origin base
- When joint5 = 0 m, link5 is at this position (already 0.278m forward!)

**Joint5 Extension**:
- joint5 = 0.0 m → link5 is at origin offset position (0.278m from link5_origin)
- joint5 = 0.1 m → link5 moves FORWARD another 0.1m
- joint5 = 0.75 m → link5 is 0.278 + 0.75 = **1.028m forward**

## Problem in motion_controller.cpp

### Current Formula (WRONG!)
```cpp
const double BASE_REACH = 0.35;  // Approximate arm base reach
const double joint5_required = r_horiz_est - BASE_REACH;
const double joint5_cmd_meters = std::clamp(joint5_required, 0.0, 0.3);
```

**Why it fails**:
1. `BASE_REACH = 0.35m` represents the FIXED reach when joint5 = 0
2. Formula: `joint5 = target_reach - fixed_reach`
3. If target is 0.5m away: `joint5 = 0.5 - 0.35 = 0.15m` ✅ CORRECT!
4. But if target is 0.3m away: `joint5 = 0.3 - 0.35 = -0.05m` → clamped to 0 ❌

### The Real Issue

The camera targets are **TOO CLOSE** to the base:
- Camera Z ranges: 0.460m to 0.652m depth
- Camera X ranges: -0.107m to -0.020m (left of center)
- Horizontal distance: `sqrt(X² + Z²)` ≈ 0.12m to 0.65m

**Horizontal reach calculation**:
```
r_horiz_est = r * cos(phi)
```

For typical corner:
- r = 0.556m, phi = 1.353 rad (77.5°)
- r_horiz_est = 0.556 * cos(77.5°) = 0.556 * 0.215 = **0.120m**

**So**: `joint5 = 0.120 - 0.35 = -0.23m` → **ALWAYS NEGATIVE!**

## Solutions

### Option 1: Fix BASE_REACH Value
```cpp
const double BASE_REACH = 0.05;  // Much smaller base reach
```
This would make: `joint5 = 0.120 - 0.05 = 0.07m` ✅

### Option 2: Use URDF Origin Offset
```cpp
const double LINK5_ORIGIN_OFFSET = 0.27774;  // From URDF
const double joint5_required = r_horiz_est - LINK5_ORIGIN_OFFSET;
```

### Option 3: Proper Forward Kinematics
Calculate the actual forward kinematics considering all link offsets from URDF.

## Recommendation

**Start with Option 1**: Change `BASE_REACH` from `0.35` to a much smaller value based on actual arm geometry. The 0.35m value is too large for the horizontal reach component.

Try: `BASE_REACH = 0.10` or even `0.05` and observe if joint5 starts extending.

