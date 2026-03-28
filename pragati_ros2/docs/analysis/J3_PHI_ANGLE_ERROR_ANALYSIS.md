# J3 Phi-Angle Dependent Positioning Error Analysis

**Date:** January 12, 2026  
**Status:** Investigation Complete - Pending Physical Verification  
**Related Code:** `motion_controller.cpp`, `coordinate_transforms.cpp`, `MG6010_FLU.urdf`

---

## 1. Observed Problem

During cotton picking operations, the arm exhibits a **phi-angle dependent vertical positioning error**:

| Phi Angle Range | Observed Behavior | Error Direction |
|-----------------|-------------------|-----------------|
| 0° - 50° (lower range) | Arm goes **below** the cotton | Negative Z error |
| 50° - 60° (mid range) | Arm is **correct** | Minimal error |
| 60° - 90° (upper range) | Arm goes **above** the cotton | Positive Z error |

### Key Diagnostic Observation

**J5 (extension) is accurate at all angles, only J3 (phi/rotation) is wrong.**

This is critical because:
- J5 uses `r = √(x² + z²)` - the radial distance
- J3 uses `phi = asin(z / √(x² + z²))` - the elevation angle

---

## 2. Coordinate Transform Chain

```
Camera Detection (OAK-D Lite)
    ↓
camera_link (optical frame: Z forward, X right, Y down)
    ↓ [TF Transform via URDF]
yanthra_link (FLU: X forward, Y left, Z up)
    ↓ [convertXYZToPolarFLUROSCoordinates()]
Polar coordinates (r, theta, phi)
    ↓
Joint commands (J3=phi, J4=theta, J5=r)
```

### URDF Transform (camera_link_joint)

```xml
<joint name="camera_link_joint" type="fixed">
  <origin xyz="0.016845 0.100461 -0.077129"
          rpy="1.5708 0.785398 0" />
  <parent link="yanthra_link" />
  <child link="camera_link" />
</joint>
```

- **Position:** X=16.8mm, Y=100.5mm, Z=-77.1mm (below yanthra_link origin)
- **Orientation:** Roll=90°, **Pitch=45°**, Yaw=0°

---

## 3. Potential Causes Analysis

### 3.1 Depth Camera Measurement Errors

**Hypothesis:** OAK-D Lite stereo depth has distance-dependent errors that cause position inaccuracies.

| Factor | Analysis |
|--------|----------|
| Typical depth error | ±2-5% at 500-800mm range |
| Error pattern | Proportional - affects both X and Z |
| Effect on J5 (r) | Would cause errors |
| Effect on J3 (phi) | Would cause errors |

**Verdict: ❌ RULED OUT**

**Reasoning:** If depth errors were the cause, they would affect X and Z proportionally. This would cause errors in **both** J5 and J3. However, we observe J5 is accurate while only J3 is wrong. This rules out general depth camera errors.

---

### 3.2 Camera Z Offset Error in URDF

**Hypothesis:** The vertical position of camera_link relative to yanthra_link is wrong in the URDF.

| Factor | Analysis |
|--------|----------|
| URDF value | Z = -77.129mm (camera below arm origin) |
| Physical measurement | **Matches** - RGB center is ~77mm below arm axis |
| Effect on J5 (r) | Minimal (offset is perpendicular to extension) |
| Effect on J3 (phi) | Would cause consistent bias, not angle-dependent |

**Verdict: ❌ RULED OUT**

**Reasoning:** A constant Z offset would cause a **constant** phi error at all angles. We observe the error **changes direction** based on phi (below at 0°, above at 90°). Also, physical measurement confirms the 77mm offset is correct.

---

### 3.3 Camera Pitch Angle Error in URDF

**Hypothesis:** The actual camera tilt angle doesn't match the URDF value of 45° (0.785398 rad).

| Factor | Analysis |
|--------|----------|
| URDF pitch value | 45° (0.785398 rad) |
| Physical measurement | **NOT YET VERIFIED** |
| Effect on J5 (r) | **None** - r = √(x² + z²) is rotation invariant |
| Effect on J3 (phi) | **Significant** - phi depends on z/x ratio which changes with rotation |

**Verdict: ✅ MOST LIKELY CAUSE**

**Reasoning:**

1. **Why J5 is unaffected:**
   ```
   r = √(x² + z²)
   ```
   This is the Euclidean distance in the XZ plane. Rotating the coordinate frame doesn't change distances - only the individual x and z components change, but their combined magnitude stays the same.

2. **Why J3 is affected:**
   ```
   phi = asin(z / √(x² + z²))
   ```
   This depends on the **ratio** of z to r. A rotation error changes how z_camera maps to z_yanthra:
   ```
   z_yanthra = -x_cam * sin(pitch) + z_cam * cos(pitch)
   ```
   If pitch is wrong by δ degrees, z_yanthra is wrong, but r stays correct.

3. **Why error direction flips with phi:**
   
   Consider a pitch error where actual = 43° but URDF says 45° (2° error):
   
   - **At phi=0°** (horizontal target): Camera is looking down at target. The 2° pitch error makes z_yanthra too small → phi calculated too low → arm goes below cotton.
   
   - **At phi=45°** (diagonal target): Camera optical axis aligns with target direction. Pitch error has minimal effect here.
   
   - **At phi=90°** (vertical target): Camera is looking nearly horizontal at target. The 2° pitch error makes z_yanthra too large → phi calculated too high → arm goes above cotton.

---

### 3.4 Coordinate Transform Calculation Errors

**Hypothesis:** The `convertXYZToPolarFLUROSCoordinates()` function has incorrect math.

```cpp
void convertXYZToPolarFLUROSCoordinates(double x, double y, double z, 
                                         double* r, double* theta, double* phi) {
    *r = sqrt(x*x + z*z);
    *theta = y;
    *phi = asin(z / sqrt(z*z + x*x));
}
```

| Factor | Analysis |
|--------|----------|
| r calculation | Correct - radial distance in XZ plane |
| theta calculation | Correct - Y value for lateral movement |
| phi calculation | Correct - elevation angle using asin |

**Verdict: ❌ RULED OUT**

**Reasoning:** The math is standard spherical/polar coordinate conversion. The formulas are correct for the FLU (Forward-Left-Up) frame convention used by yanthra_link.

---

### 3.5 RGB-to-Depth Alignment (Parallax)

**Hypothesis:** Detection uses RGB camera but depth comes from stereo cameras, causing parallax.

| Factor | Analysis |
|--------|----------|
| OAK-D Lite baseline | 75mm between stereo cameras |
| RGB position | Center, between stereo cameras |
| Depth alignment | OAK-D can align depth to RGB frame |

**Verdict: ⚠️ POSSIBLE MINOR CONTRIBUTOR**

**Reasoning:** If depth is not properly aligned to RGB, there could be a small horizontal offset. However, this would cause **consistent** errors, not phi-dependent errors. The DepthAI SDK should handle RGB-depth alignment automatically when configured correctly.

---

## 4. Conclusion

### Root Cause (High Confidence)

**The camera pitch angle in the URDF (45°) likely doesn't match the physical camera mounting angle.**

This explains:
- ✅ Why J5 is correct (rotation-invariant)
- ✅ Why J3 is wrong (rotation-sensitive)
- ✅ Why error direction depends on phi (geometric relationship)
- ✅ Why error is minimal around 45° phi (camera aligns with arm)

### Supporting Evidence

| Observation | Explained by Pitch Error? |
|-------------|---------------------------|
| J5 accurate at all angles | ✅ Yes - r is rotation invariant |
| J3 error at 0-30° (below) | ✅ Yes - pitch error reduces z_yanthra |
| J3 correct at 30-60° | ✅ Yes - near camera alignment angle |
| J3 error at 60-90° (above) | ✅ Yes - pitch error increases z_yanthra |

---

## 5. Verification Steps

### 5.1 Physical Measurement Required

1. **Set J3 to 0°** (arm horizontal/forward)
2. **Measure the actual camera optical axis angle** relative to horizontal
3. **Compare to URDF value** of 45°

### 5.2 Expected Results

| Measurement | Implication |
|-------------|-------------|
| Actual = 45° | Pitch is correct, investigate other causes |
| Actual = 43° | Explains "arm below" at low phi |
| Actual = 47° | Would cause opposite pattern (not our case) |

### 5.3 How to Measure Camera Pitch

Options:
1. **Spirit level + protractor:** Place level on arm, measure camera angle relative to it
2. **Laser pointer:** Attach to camera, see where beam hits at known distance
3. **Visual target:** Place target at known height, check camera center point

---

## 6. Remediation Options

### Option A: Fix URDF (Permanent Solution)

If physical measurement shows pitch is X° instead of 45°, update:

```xml
<!-- In MG6010_FLU.urdf, line 314 -->
<origin xyz="0.016845 0.100461 -0.077129"
        rpy="1.5708 [NEW_PITCH_VALUE] 0" />
```

**Pros:** Fixes root cause, no runtime overhead  
**Cons:** Requires accurate physical measurement

### Option B: Phi Compensation (Current Implementation)

Apply angle-dependent offset as currently implemented in `motion_controller.cpp`.

**Pros:** Works without knowing exact pitch error, tunable in field  
**Cons:** Empirical workaround, may need re-tuning if hardware changes

### Option C: Runtime Calibration

Add a calibration routine that measures error at multiple phi angles and computes the pitch correction automatically.

**Pros:** Self-calibrating, adapts to hardware variations  
**Cons:** More complex implementation, requires calibration targets

---

## 7. Current Mitigation

A zone-based phi compensation system has been implemented:

```yaml
# production.yaml
phi_compensation:
  enabled: true
  zone1_max_phi: 0.87        # 50° (0-50° range)
  zone1_offset: 0.014        # Positive offset - arm was going below, so raise it
  zone1_slope: 0.0
  zone2_max_phi: 1.05        # 60° (50-60° range - reference zone)
  zone2_offset: 0.0          # Reference zone (correct)
  zone2_slope: 0.0
  zone3_offset: -0.014       # Negative offset - arm was going above, so lower it
  zone3_slope: 0.0
```

### Compensation Values Explanation

| Zone | Phi Range | Offset | Reasoning |
|------|-----------|--------|-----------|
| Zone 1 | 0° - 50° | +0.014 rad (+0.8°) | Arm was going **below** cotton, add positive offset to raise |
| Zone 2 | 50° - 60° | 0.0 | Reference zone, arm is accurate here |
| Zone 3 | 60° - 90° | -0.014 rad (-0.8°) | Arm was going **above** cotton, add negative offset to lower |

This allows field tuning without code changes.

---

## 8. References

- [MG6010_FLU.urdf](../src/robot_description/urdf/MG6010_FLU.urdf) - Robot URDF with camera transform
- [coordinate_transforms.cpp](../src/yanthra_move/src/coordinate_transforms.cpp) - Polar conversion code
- [motion_controller.cpp](../src/yanthra_move/src/motion_controller.cpp) - Phi compensation implementation
- [CAMERA_COORDINATE_SYSTEM.md](CAMERA_COORDINATE_SYSTEM.md) - Camera frame conventions

---

## 9. Action Items

- [ ] **Physical Measurement:** Measure actual camera pitch angle
- [ ] **Compare:** Check against URDF value of 45°
- [ ] **Decision:** If different, update URDF; if same, tune compensation parameters
- [ ] **Validate:** Test picking accuracy across all phi angles after fix
