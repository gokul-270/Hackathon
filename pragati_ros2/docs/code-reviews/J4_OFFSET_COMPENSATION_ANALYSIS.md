# J4 Offset Compensation Analysis

**Date:** 2026-02-16
**Commit under review:** `d9893c1` — _Add J4 offset compensation for multi-position scanning_
**Reviewer:** AI-assisted deep code review
**Files changed:** `motion_controller.cpp`, `motion_controller.hpp`, `production.yaml`

---

## 1. Summary

When multi-position scanning moves J4 to non-home offsets, the cotton detection pipeline returns `theta` (Y-coordinate) **relative to the camera's current position**, not as an absolute base-frame coordinate. The fix adds `current_j4_scan_offset_` to theta before commanding J4, converting the relative displacement into the absolute motor position.

```cpp
// Before (bug):
const double joint4_cmd = theta;

// After (fix):
const double joint4_cmd = theta + current_j4_scan_offset_;
```

---

## 2. Kinematic Chain

```
base_link (FIXED - world frame)
  └─ joint2 [prismatic Z] ─→ link2
       └─ joint4 [prismatic Y] ─→ link4     ◄── J4 SLIDES EVERYTHING BELOW
            ├─ joint3 [revolute -Y] ─→ link3
            │    └─ yantra_joint [fixed] ─→ yanthra_link   ◄── TF TARGET FRAME
            │         ├─ camera_link_joint [fixed] ─→ camera_link   ◄── TF SOURCE FRAME
            │         └─ link5_origin → joint5 → link5 → ee_link
            └─ joint7 [fixed] ─→ link7 ─→ camera_mount_link
```

**Critical fact:** Both `camera_link` and `yanthra_link` are children of `link4`, connected only through **fixed joints**. When J4 slides, they move together as one rigid body. The TF transform between them is **constant** — it encodes camera mounting geometry, not J4's position.

---

## 3. Detection Data Flow

```
OAK-D Camera (YOLO detection)
    │  Raw spatial coords in RUF (mm) → converted to FLU (m)
    │  Published on /cotton_detection/results, frame_id = "camera_link"
    ▼
TF lookupTransform("yanthra_link", "camera_link")
    │  *** THIS IS A CONSTANT TRANSFORM ***
    │  Both frames ride on J4's carriage — transform never changes
    ▼
convertXYZToPolarFLUROSCoordinates()
    │  theta = Y-coordinate in yanthra_link frame
    │  theta is RELATIVE to J4's current position
    ▼
joint4_cmd = theta + j4_offset   (absolute motor command)
```

### Why the TF Transform Is Constant

The code in `executeApproachTrajectory()` performs:

```cpp
auto transform = tf_buffer_->lookupTransform(
    "yanthra_link",    // target frame
    "camera_link",     // source frame
    tf2::TimePointZero
);
```

Since `camera_link → (fixed joints) → yanthra_link`, this transform is **constant** regardless of J4 position. It converts the camera's spatial detection into the arm's reference frame, but both frames have already moved with J4.

The polar coordinate conversion then extracts:

```cpp
*theta = y;  // Y-coordinate in yanthra_link frame — direct passthrough
```

This Y-coordinate is relative to yanthra_link, which is relative to J4's current position.

---

## 4. The Bug: Worked at Home, Failed at Offsets

| Scenario | J4 Position | theta (relative) | joint4_cmd (old) | Cotton Actual | Error |
|----------|-------------|-------------------|------------------|---------------|-------|
| Single-position (J4 at home) | 0.000m | +0.020m | +0.020m | +0.020m | **0mm** |
| Multi-pos (J4 at -50mm) | -0.050m | +0.020m | +0.020m | -0.030m | **50mm** |
| Multi-pos (J4 at +80mm) | +0.080m | -0.010m | -0.010m | +0.070m | **80mm** |

**Pattern:** The miss distance always equals the J4 scan offset. When J4 is at home (offset = 0), relative = absolute and the bug is invisible.

### Concrete Example

1. J4 slides to -50mm for multi-position scan
2. Camera (now at -50mm) detects cotton at Y = +20mm in camera frame
3. TF transform to yanthra_link: theta ≈ +20mm (constant transform)
4. **Without fix:** `joint4_cmd = +0.020m` — arm goes to +20mm absolute
5. **Cotton is actually at:** -0.050 + 0.020 = **-0.030m** in base frame
6. **With fix:** `joint4_cmd = 0.020 + (-0.050) = -0.030m` — correct

---

## 5. Why This Was Not Caught in the Original Implementation

### 5.1 Timeline

| Date | Event |
|------|-------|
| Jan 5, 2026 | Original `motion_controller.cpp` — J4 always at home. `joint4_cmd = theta` works. |
| Jan 28 | FOV analysis documents. Section 6.3 incorrectly claims: _"TF transform ALREADY accounts for current J4 position. No manual offset needed."_ |
| Feb 3 | Multi-position scanning implemented. Commit echoes: _"TF transforms handled automatically by ROS2 (no manual offset calculation)"_ |
| Feb 10 | Feature enabled in production. |
| Feb 13 | **Fix committed** — `joint4_cmd = theta + current_j4_scan_offset_` |

### 5.2 The Incorrect Assumption

The FOV improvement documentation (Section 6.3) stated:

> _"TF2 looks up: camera_link → yanthra_link transform. This transform ALREADY accounts for current J4 position! No manual offset calculation needed."_

This confused two different transforms:

| Transform | Changes with J4? | Why? |
|-----------|-------------------|------|
| `camera_link → base_link` | **YES** | J4 joint is between them in the kinematic chain |
| `camera_link → yanthra_link` | **NO** | Both frames are downstream of J4, connected by fixed joints only |

The code uses the second transform. A misleading comment in the code even says "Transform from camera_link to base_link" but the actual target frame is `yanthra_link`.

### 5.3 Contributing Factors

1. **Correct temporal analysis masked incorrect spatial analysis.** The documentation showed deep understanding of temporal staleness (must re-detect after J4 moves, TF settling times). This sophisticated analysis created false confidence that the spatial coordinate math was correct.

2. **Center position (0mm offset) always works.** Default scan positions include 0mm. Cotton found at center passes correctly, making the bug intermittent at non-center positions.

3. **Feature disabled for 7 days.** Implemented Feb 3, enabled Feb 10. Initial testing likely used single-position mode only.

4. **Hidden assumption never documented.** The original design `joint4_cmd = theta` silently assumed J4 = 0, so yanthra_link Y = absolute Y. This assumption was never stated explicitly, so it was never questioned when multi-position scanning broke it.

---

## 6. Why the Fix Is Architecturally Correct

The robot decomposes control into three independent joint commands:

| Joint | Coordinate | Computed in Frame | Motor Expects | Frame Match? |
|-------|-----------|-------------------|---------------|--------------|
| J3 (tilt) | phi (angle) | yanthra_link | Relative angle from arm pivot | Yes |
| J5 (extend) | r (distance) | yanthra_link | Relative distance from arm | Yes |
| J4 (slide) | theta (Y) | yanthra_link | **Absolute Y position** | **No — needs offset** |

J3 and J5 are naturally computed in `yanthra_link` frame (the arm's "shoulder"). Their motor commands are relative to the arm's current position, which is exactly what yanthra_link provides.

J4 is the exception — it is a **base-frame translation** that accumulates with its own position. The offset compensation correctly bridges this gap:

```
j4_target_absolute = theta_relative_to_arm + j4_current_offset
```

### Why Not Transform to base_link Instead?

Transforming from `camera_link` to `base_link` would give absolute coordinates, eliminating the need for manual offset correction. However:

1. It would break J3 and J5 calculations, which depend on yanthra_link-frame coordinates (arm-relative angles and distances).
2. It would require `robot_state_publisher` to know J4's actual position — currently blocked by a **joint name mismatch** (URDF uses `"joint 4"` with space, motor controller publishes `"joint4"` without space).
3. The polar decomposition (r, theta, phi) is most natural in the arm's own shoulder frame, not the base frame.

The offset compensation is therefore the **correct architectural solution** — not a workaround.

---

## 7. Mathematical Proof

Defining frames:
- `B` = base_link (fixed world frame)
- `L4` = link4 (moves with J4)
- `Y` = yanthra_link (fixed offset from L4)

For the Y-component:

```
P_B.y = j4_position + P_Y.y + structural_constants
```

The structural constants (URDF offsets from link2 to yanthra_link in Y) are absorbed into J4's zero/home calibration. What remains:

```
j4_target = theta + j4_scan_offset
```

Where:
- `theta` = P_Y.y = Y-coordinate of cotton in yanthra_link frame (relative to arm)
- `j4_scan_offset` = current J4 displacement from home position
- `j4_target` = absolute motor command

---

## 8. Additional Finding: URDF Joint Name Mismatch

| URDF Name | Motor Controller Name | Matched by robot_state_publisher? |
|-----------|----------------------|-----------------------------------|
| `"joint 2"` | N/A | N/A |
| `"joint 3"` | `"joint3"` | **NO** (space mismatch) |
| `"joint 4"` | `"joint4"` | **NO** (space mismatch) |
| `"joint 5"` | `"joint5"` | **NO** (space mismatch) |

`robot_state_publisher` matches `/joint_states` messages to URDF joints by name. The name mismatch means the TF tree **never reflects actual joint positions** — it always uses default values. This does not affect the current pipeline (which uses the constant `camera_link → yanthra_link` transform) but would break any future code relying on `base_link → camera_link` transforms or RViz visualization.

---

## 9. Root Cause Classification

| Aspect | Assessment |
|--------|------------|
| **Bug type** | Specification-level design oversight |
| **Not an implementation bug** | Code was built exactly to spec — the spec was wrong |
| **Not a missing requirement** | Multi-position accuracy was implicitly required |
| **Root cause** | Incorrect reasoning about TF transforms in FOV design documents |
| **Hidden assumption** | `joint4_cmd = theta` assumed J4 = 0 (yanthra_link Y ≡ absolute Y) |
| **When exposed** | As soon as J4 moved to non-zero offsets during multi-position scanning |
| **Fix correctness** | Architecturally correct — bridges arm-frame detection to base-frame motor commands |

---

## 10. Lessons Learned

1. **Fixed transforms between sibling frames don't encode joint motion.** When camera and target frame are both downstream of a joint, TF between them is constant. Only transforms that cross the joint in the kinematic chain reflect its motion.

2. **"TF handles it automatically" needs verification, not assumption.** The design documents stated this without tracing through the actual kinematic chain. A simple mental exercise — "if I move J4 by 50mm, does the `camera_link → yanthra_link` transform change?" — would have revealed the issue.

3. **Designs that work at zero don't necessarily generalize.** `theta = absolute_position` is only true when `offset = 0`. The original design was correct but fragile — it relied on a coincidence (J4 at home) that was never documented as an assumption.

4. **Misleading comments compound errors.** A code comment said "Transform from camera_link to base_link" but the actual target was `yanthra_link`. This may have reinforced the incorrect belief that the transform accounted for J4.

5. **Temporal correctness ≠ spatial correctness.** The team correctly identified the temporal staleness problem (must re-detect after J4 moves) but missed the spatial reference frame problem. Sophisticated analysis in one dimension can create false confidence in another.
