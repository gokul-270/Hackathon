# Motion Controller: No-IK Pipeline

## Overview
The Yanthra motion controller uses a **direct polar-to-motor** mapping with NO inverse kinematics calculations. After TF transformation, polar coordinates are sent directly to motors with only unit conversions.

## Pipeline Flow
```
Camera (XYZ) → TF Transform → Polar (r, θ, φ) → Direct Motor Commands
```

1. **Camera Input** (`camera_link` frame): X, Y, Z coordinates
2. **TF Transform** → `yanthra_link` frame
3. **Polar Conversion:**
   - `r = sqrt(x² + z²)` - radial distance in XZ plane
   - `theta = y` - direct Y passthrough (left/right)
   - `phi = asin(z / sqrt(x² + z²))` - elevation angle
4. **Motor Commands** (NO IK!):
   - Joint 3: `phi → rotations`
   - Joint 4: `theta` (direct meters)
   - Joint 5: `r - 0.275m` (direct with offset)

## Joint Command Specifications

### Joint 3 (Rotation - Base Azimuth)
- **Input:** `phi` (elevation angle, radians)
- **Conversion:** `phi / (2π)` → rotations (DIRECT, no offset)
- **Limits:** `-0.2` to `0.0` rotations (enforced by motor_control)
- **Motor Direction:** `-1` (configured in YAML) - inverts sign at motor level
- **Error Handling:** Limits checked by motor_control node, rejected if out of range
- **Note:** Negative phi (below horizontal) → negative rotations → motor inverts to positive → downward motion

### Joint 4 (Left/Right - Linear Translation)
- **Input:** `theta` (Y-coordinate from yanthra_link, meters)
- **Conversion:** None - direct passthrough
- **Limits:** `-0.1` to `0.1` meters (enforced by motor_control)
- **Error Handling:** Limits checked by motor_control node

### Joint 5 (Extension - Radial Distance)
- **Input:** `r` (radial distance in XZ plane, meters)
- **Hardware Offset:** `0.320m` (320mm)
- **Calculation:** `joint5_cmd = r - 0.320`
- **Limits:** `0.0` to `0.35` meters (enforced by motor_control)
- **Error Handling:** Limits checked by motor_control node

## Constants

```cpp
JOINT5_OFFSET = 0.320  // meters (320mm hardware offset)

// Limits enforced by motor_control node (production.yaml)
// Joint 3: -0.2 to 0.0 rotations
// Joint 4: -0.1 to 0.1 meters
// Joint 5: 0.0 to 0.35 meters
```

## Key Principles

1. **NO Inverse Kinematics:** Polar values map directly to joints
2. **Two-Layer Safety (Defense-in-Depth):**
   - **Layer 1 (Planning):** Motion controller checks with 2% margin, detailed errors
   - **Layer 2 (Hardware):** Motor control enforces absolute hard limits
3. **Single Source of Truth:** Limits defined in `production.yaml`
4. **NO BASE_REACH/r_horizontal calculations:** Joint5 uses direct `r` value
5. **Motor Direction in Config:** Motor `direction=-1` handled in YAML, not code

## Example Calculation

For a target at `phi = -0.8 rad, theta = 0.05 m, r = 0.60 m`:

```
joint3_cmd = -0.8 / (2π) = -0.127 rotations  ✓ within [-0.2, 0.0]
joint4_cmd = 0.05 m                           ✓ within [-0.1, 0.1]
joint5_cmd = 0.60 - 0.320 = 0.280 m          ✓ within [0.0, 0.35]
```

All values within limits → Motor control accepts → Motion proceeds

For an out-of-range target `phi = -1.5 rad`:
```
joint3_cmd = -1.5 / (2π) = -0.239 rotations  ✗ outside [-0.2, 0.0]
→ Motor control rejects command → Motion aborted
```

## Files Modified (Nov 2025)
- `src/core/motion_controller.cpp` - Restored from `backup_before_expand_limits`, fixed all joint calculations
- `src/coordinate_transforms.cpp` - Already correct (direct Y passthrough)
- Archived 20+ backup files to `docs/archive_backups/`

## Git History
Branch: `fix/motion-controller-no-ik`
Tag: `rpi_nov_reconciled_no_ik`
