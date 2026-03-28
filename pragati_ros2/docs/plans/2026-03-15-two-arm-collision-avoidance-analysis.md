# Two-Arm Collision Avoidance — Workspace Reachability Analysis

**Date:** 2026-03-15
**Status:** Analysis complete, implementation pending field measurement
**Target:** March 25 field trial decision

## Problem Statement

Two arms face each other across a cotton row, with J5 (prismatic X) extending toward the
opposing arm. At J3=0 (arm horizontal) and J5=0.22m on both arms, end-effectors collide.
A blanket J5 limit of 0.22m is too restrictive — it cuts reachable cotton at other J3 angles.

## Physical Setup

```
ARM-LEFT base                                              ARM-RIGHT base
     │                                                          │
     ○────────────●════J5-L════►  ◄════J5-R════●────────────○
     │  0.29m     │   0-0.35m        0-0.35m   │   0.29m    │
     │  hw_offset │                             │  hw_offset │
     ◄──────────── D (base-to-base) ≈ 1.02m ──────────────►
```

- **J5 hardware offset:** 0.290m (link5_origin at 0.278m from yanthra_link)
- **J5 range:** 0 to 0.35m (production.yaml)
- **J3 range:** -0.2 to 0.0 rotations (-72° to 0°)
- **J4 range:** -0.175 to +0.175m
- **Base separation D:** ~1.02m (estimated from collision at J5=0.22m; **needs physical measurement**)
- **Camera:** Fixed to link4 (NOT link5), pitched 45° downward

## Key Findings

### 1. Collision Is J3-Dependent

At J3 angle θ (radians, negative = tilted down), J5 extends along a tilted axis.
Only the horizontal component contributes to collision:

```
Collision condition (both arms same J3, worst case):
  2 × (hw_offset + J5 × cos(θ)) ≥ D

Safe J5 limit per arm:
  J5_max(θ) = (D/2 - hw_offset - safety_margin) / cos(θ)
```

With D=1.02m, hw_offset=0.29m, safety_margin=0.03m (arm width):

| J3 (rotations) | J3 (degrees) | J5_max safe | Full range? |
|-----------------|--------------|-------------|-------------|
| 0.00            | 0°           | 0.19m       | No          |
| -0.05           | -18°         | 0.20m       | No          |
| -0.08           | -29°         | 0.22m       | No          |
| -0.10           | -36°         | 0.24m       | No          |
| -0.14           | -50°         | 0.30m       | Nearly      |
| -0.15           | -54°         | 0.35m       | **Yes**     |
| -0.20           | -72°         | 0.35m (cap) | **Yes**     |

**At J3 < -0.15 rotations (>54° down), full J5 range is collision-safe.**

### 2. Camera FOV Naturally Avoids the Dangerous Zone

Camera is fixed to link4 (moves with J4, not J3/J5), pitched 45° down.
At J3=0 (horizontal), the camera's maximum forward visibility:

| Camera height above cotton | Max forward visible (from link4) | Max J5 implied |
|---------------------------|----------------------------------|----------------|
| 0.10m                     | 0.13m                            | ~0 (can't see far) |
| 0.20m                     | 0.31m                            | ~0.09m         |
| 0.30m                     | 0.50m                            | ~0.28m         |
| 0.40m                     | 0.69m                            | ~0.47m         |

**When camera is <28cm above cotton, it physically cannot see targets in the collision zone.**
Cotton is always below the arm → J3 is always negative → large J5 extensions are safe.

Field observation: J5 extension at J3=0 has never been observed in practice.

### 3. J4 Provides Additional Safety Margin

J4 (prismatic Y, lateral) moves each arm's end-effector perpendicular to the collision axis.
Collision requires both X-overlap AND Y-overlap:

```
Collision requires:
  1. X: (0.29 + J5_L×cos(J3_L)) + (0.29 + J5_R×cos(J3_R)) ≥ D
  2. Y: |J4_L - J4_R| < arm_width (~8-10cm)
```

If arms are at different J4 positions (>8cm apart), **no collision regardless of J5/J3**.

With J4 multiposition scanning [-0.150, -0.075, 0.000, +0.075, +0.150]m:
- 25 possible J4 pairs (5×5)
- Only ~7 pairs have Y-overlap risk (28%)
- **72% of J4 combinations are inherently collision-safe**

**Limitation:** Exploiting J4 requires inter-arm communication (MQTT) to know the other
arm's J4 position. Without coordination, J4 benefit cannot be used.

## Implementation Options

### Option A: J3-Dependent J5 Formula (No coordination needed)

```cpp
// In trajectory_planner.cpp, after computing j3_cmd and j5_cmd:
double j3_angle_rad = j3_cmd * 2.0 * M_PI;  // rotations to radians
double cos_j3 = std::max(std::cos(j3_angle_rad), 0.1);  // prevent div-by-zero
double j5_collision_limit = std::min(
    j5_max,  // 0.35m from config
    collision_half_clearance / cos_j3  // 0.19m / cos(J3)
);
// Clamp j5_cmd to j5_collision_limit
```

- **Pros:** Zero coordination, one formula, geometrically correct, ~zero workspace loss
- **Cons:** Conservative at J3=0 (but camera doesn't command J3=0 picks)
- **Config params:** `collision_half_clearance: 0.19` (D/2 - hw_offset - margin)

### Option B: MQTT J4 Sharing + J3 Formula

Each arm publishes J4 position via MQTT. If `|my_J4 - other_J4| > 0.10m`, skip J5 limit.
Otherwise fall back to Option A formula.

- **Pros:** Maximum workspace utilization
- **Cons:** Requires MQTT infrastructure, adds latency dependency

### Option C: Coordinated J4 Scanning Patterns

Pre-assign opposite J4 scan sequences to each arm (L scans negative J4, R scans positive).
Guarantees Y separation without runtime coordination.

- **Pros:** No MQTT needed, guaranteed separation
- **Cons:** Reduces flexibility, may miss cotton on "wrong" side

### Option D: Turn-Based Full Access

Arms take turns — one picks while other is retracted. Full J5 range.

- **Pros:** Full workspace, simple logic
- **Cons:** Halves throughput

## Recommendation for March 25 Field Trial

**Option A (J3-dependent formula)** is recommended:
1. Zero coordination needed between independent RPi 4B controllers
2. Negligible workspace loss (restricted zone is invisible to camera)
3. Single config parameter (`collision_half_clearance`)
4. One-line code change in trajectory planner
5. Defense-in-depth: even if camera somehow commands J3=0 pick, formula prevents collision

**Before implementation, measure:**
- [ ] Actual base-to-base distance D (to replace estimated 1.02m)
- [ ] Link5 physical cross-section width (to refine safety margin)
- [ ] Review field trial Feb 26 logs for actual J3/J5 command distributions

**After field trial, evaluate:**
- How many targets triggered the J3-dependent limit?
- Did any cotton require J5 > limit? (log the clamp events)
- Is MQTT J4 sharing (Option B) worth adding for future trials?

## Open Questions

1. **Base separation D:** Estimated at 1.02m from collision observation. Needs physical measurement.
2. **URDF camera_link_joint:** `camera_link_joint` parent is `yanthra_link` (rotates with J3),
   but physical camera is on link7 (fixed to link4). TF tree may need correction for accurate
   camera-to-arm transforms.
3. **J3=0 + tall cotton:** Edge case where very tall cotton at arm height could produce J3≈0.
   Formula handles this safely, but worth monitoring in field data.
