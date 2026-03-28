# J3 Phi-Angle Compensation Analysis

**Date:** 2026-02-16
**Commit under review:** `ee50158` — _feat(motion): Add phi-angle compensation for J3 positioning errors_
**Reviewer:** AI-assisted deep code review
**Cross-reference:** `docs/analysis/J3_PHI_ANGLE_ERROR_ANALYSIS.md` (original analysis, Jan 12, 2026)
**Files changed:** `motion_controller.cpp`, `motion_controller.hpp`, `yanthra_move_system_parameters.cpp`, `production.yaml` (both yanthra_move and motor_control)

---

## 1. Summary

J3 (elevation/phi angle) exhibits angle-dependent positioning errors: the arm goes below cotton at low phi, is correct at mid phi, and goes above cotton at high phi. J5 (radial extension) is accurate at all angles. A zone-based phi compensation was added as a field workaround. The original analysis attributes this to camera pitch angle error in the URDF (45° declared vs actual unknown). This review finds the original analysis is **partially correct** but **mathematically incomplete** — a pure camera pitch error produces a **constant** phi offset, not an angle-dependent one. The observed angle-dependent pattern likely involves additional mechanical factors.

---

## 2. The Compensation Mechanism

### What was added (commit `ee50158`)

```cpp
// Zone-based phi compensation in executeApproachTrajectory()
double phi_compensation = 0.0;
if (phi_compensation_enable_) {
    // Determine zone by phi angle
    if (phi_deg <= zone1_max)      { slope = zone1_slope; offset = zone1_offset; }  // 0-50°
    else if (phi_deg <= zone2_max) { slope = zone2_slope; offset = zone2_offset; }  // 50-60°
    else                           { slope = zone3_slope; offset = zone3_offset; }  // 60-90°

    base_compensation = slope * (phi_deg / 90) + offset;
    l5_scale_factor = 1.0 + l5_scale * (l5_extension / l5_max);
    phi_compensation = base_compensation * l5_scale_factor * 2π;  // rotations → radians
}
const double joint3_cmd = (phi + phi_compensation) * RAD_TO_ROT;
```

### Production tuning values

| Zone | Phi Range | Offset (rotations) | Offset (degrees) | Observed Error |
|------|-----------|---------------------|-------------------|----------------|
| Zone 1 | 0–50° | +0.014 | +5.04° | Arm goes BELOW cotton |
| Zone 2 | 50–60° | 0.0 | 0° | Arm is correct |
| Zone 3 | 60–90° | -0.014 | -5.04° | Arm goes ABOVE cotton |
| L5 scale | — | 0.5 | — | Error increases 50% at full extension |

---

## 3. Kinematic Chain

### URDF camera mounting — two branches from link4

```
link4
  ├── [joint 7, FIXED, pitch=45°] ─→ link7
  │    └── [camera_mount_joint, FIXED] ─→ camera_mount_link    ◄── Physical mount (ABOVE J3)
  │
  └── [joint 3, REVOLUTE, -Y axis] ─→ link3
       └── [yantra_joint, FIXED] ─→ yanthra_link
            ├── [camera_link_joint, FIXED, roll=90°, pitch=45°] ─→ camera_link   ◄── TF frame (BELOW J3)
            └── link5_origin ─→ joint5 ─→ link5 ─→ ee_link
```

**Critical structural fact:** `camera_link` is a **fixed child** of `yanthra_link` (both below J3). The `camera_mount_link` is on a separate branch directly on `link4` (above J3). The code uses `camera_link`, not `camera_mount_link`.

The TF lookup `camera_link → yanthra_link` is a **single fixed-joint inversion** — it is constant regardless of J3 position.

### URDF camera_link_joint parameters

```xml
<joint name="camera_link_joint" type="fixed">
  <origin xyz="0.016845 0.100461 -0.077129"
          rpy="1.5708 0.785398 0" />  <!-- roll=90°, pitch=45°, yaw=0° -->
  <parent link="yanthra_link" />
  <child link="camera_link" />
</joint>
```

The 45° pitch comes from the **SolidWorks URDF export** (commit `2cad9f9`, Jan 4, 2026) and has **never been physically measured or calibrated**.

---

## 4. Mathematical Analysis: Camera Pitch Error Propagation

### 4a. Setup

Let the URDF declare camera pitch = α₀ = 45°. Let the true physical pitch = α₀ + δ (error of δ radians). The TF system uses α₀ to transform coordinates, producing a spurious rotation of δ in the XZ plane:

```
x_measured = x_true · cos(δ) + z_true · sin(δ)
z_measured = -x_true · sin(δ) + z_true · cos(δ)
y_measured = y_true   (Y is the rotation axis, unaffected)
```

### 4b. Proof: r is exactly invariant (mathematical necessity)

```
r_measured² = x_measured² + z_measured²
            = (x_true·cosδ + z_true·sinδ)² + (-x_true·sinδ + z_true·cosδ)²
```

Expanding and using cos²δ + sin²δ = 1:

```
            = x_true²·(cos²δ + sin²δ) + z_true²·(sin²δ + cos²δ)
              + 2·x_true·z_true·(cosδ·sinδ - sinδ·cosδ)
            = x_true² + z_true² + 0
            = r_true²
```

**r_measured = r_true. QED.** Rotations preserve Euclidean norms. This is why J5 (extension) is perfectly accurate regardless of any camera pitch error. This is an exact result, not an approximation.

### 4c. Proof: phi error is CONSTANT (not angle-dependent)

Express the true position in polar form: `x_true = r·cos(φ_true)`, `z_true = r·sin(φ_true)`.

```
z_measured = -r·cos(φ_true)·sin(δ) + r·sin(φ_true)·cos(δ)
           = r · sin(φ_true - δ)              [sine subtraction identity]
```

Therefore:

```
φ_measured = asin(z_measured / r) = asin(sin(φ_true - δ)) = φ_true - δ
```

**The phi error from a pure camera pitch error is exactly -δ at ALL angles.**

This is the **sine subtraction identity** — it is an exact result, not a small-angle approximation. It means a camera pitch error of δ produces a constant phi offset of -δ, independent of the target's angular position.

### 4d. The critical contradiction

| What pure camera pitch error predicts | What was observed in the field |
|---------------------------------------|-------------------------------|
| Constant phi offset at all angles | Error direction FLIPS between low and high phi |
| Same magnitude at all angles | Error is zero at mid phi (~50-60°) |
| Same direction at all angles | +5° at low phi, -5° at high phi (opposite signs) |

**A pure camera pitch angle error CANNOT explain the observed behavior.** The zone-based compensation with opposite signs in Zone 1 vs Zone 3 is compensating for something else — or for multiple compounding effects.

---

## 5. What Is Actually Causing the Angle-Dependent Error?

The mathematical proof above rules out camera pitch error as the sole cause of the **angle-dependent** pattern. The actual error is likely a combination of:

### 5.1 Camera pitch error (constant component)

A constant offset δ almost certainly exists — the 45° pitch has never been physically verified. But this component would be the same at all phi angles. It may be partially absorbed into the zone-based offsets.

### 5.2 Gravity-induced arm deflection (MOST LIKELY angle-dependent component)

**Evidence strongly supports this:**

| Factor | Analysis |
|--------|----------|
| Thermal docs | L3 "continuously fights gravity" and overheats in 10-15 minutes |
| PID tuning | L3 PID is documented as "default values, no field-specific tuning" (`UNRESOLVED_TECHNICAL_ISSUES.md`) |
| L5 scaling | The compensation explicitly includes L5 extension scaling (0.5) — longer reach = more gravity torque = more deflection |
| CG imbalance | Documented as causing "excessive motor effort" |

**Mechanism:**
- At low phi (0-50°, near horizontal): Maximum gravitational torque on the arm. The arm **sags downward** due to gravity. J3 motor holds a steady-state error under load. Arm goes below target.
- At mid phi (50-60°): Gravity torque matches the deflection characteristics of the system. This is the "sweet spot" where the arm's natural sag happens to be close to zero error.
- At high phi (60-90°, near vertical): Gravity now acts along the arm axis, not perpendicular. Minimal bending torque. But if the motor overshoots or if there is a bias in the PID, the arm ends up above target.

This matches the observed pattern perfectly — including the sign reversal.

### 5.3 J3 motor PID steady-state error

The MG6010 motor PID is documented as untuned. Under varying gravity loads at different angles, the steady-state position error varies. This compounds with the gravity deflection effect.

### 5.4 Structural compliance

The link4 → link3 → yanthra_link → link5 chain has bolts, bearings, and structural elements whose flex varies with pose. At different J3 angles, different members bear load, causing pose-dependent compliance.

### 5.5 Potential URDF modeling discrepancy

The physical camera is mounted on `link4` (via `joint 7`, above J3), but `camera_link` is modeled as a child of `yanthra_link` (below J3, via a fixed joint). If the camera_link_joint transform was computed for a specific J3 position (e.g., J3 = 0), it would only be perfectly accurate at that angle. At other J3 angles, the actual relative position between the physical camera and yanthra_link changes because J3 has rotated the arm but not the camera bracket.

**However:** Both `camera_link` and `yanthra_link` are below J3 in the URDF. If the physical camera truly moves with the arm (both rotate together via J3), then the fixed transform is correct at all angles. The discrepancy only matters if the camera is physically fixed to link4 (above J3) while the URDF models it below J3.

---

## 6. Assessment of the Existing Root Cause Analysis

The original analysis (`docs/analysis/J3_PHI_ANGLE_ERROR_ANALYSIS.md`) is **well-structured and methodical** but contains a mathematical error in Section 3.3:

### What the analysis gets right

- Correctly identifies that `r = √(x² + z²)` is rotation-invariant (Section 3.1-3.3)
- Correctly rules out depth camera errors (would affect both r and phi)
- Correctly rules out camera Z offset (would cause constant, not angle-dependent error)
- Correctly rules out coordinate transform math errors (formulas are correct)
- Correctly identifies that camera pitch is not physically verified

### What the analysis gets wrong

**Section 3.3 (lines 126-134):** The qualitative explanation of why the error "flips direction" is physically intuitive but mathematically incorrect. The analysis argues:

> "At phi=0° (horizontal target): The 2° pitch error makes z_yanthra too small → phi calculated too low"
> "At phi=90° (vertical target): The 2° pitch error makes z_yanthra too large → phi calculated too high"

The mathematical proof in Section 4c above shows this is wrong. A pure pitch error of δ produces `φ_measured = φ_true - δ` at ALL angles. The z/x ratio changes at different angles, but the net effect on phi is always the same constant offset. The "flipping" described in the analysis does not occur with a pure rotation error.

The analysis was a reasonable hypothesis that was never verified mathematically before being implemented as a field workaround.

---

## 7. Is the Zone-Based Compensation a Correct Fix or a Workaround?

**It is definitively a workaround, not a correct fix.** The codebase itself acknowledges this:

| Source | Statement |
|--------|-----------|
| Commit `ee50158` message | "Camera pitch calibration pending physical verification" |
| Analysis doc Section 9 | All 4 action items unchecked (physical measurement not done) |
| `UNRESOLVED_TECHNICAL_ISSUES.md` | Classified as "Not Root Caused" |
| Analysis doc Section 6 | Lists "Fix URDF" as "Permanent Solution" vs compensation as workaround |
| `FEBRUARY_FIELD_TRIAL_PLAN_2026.md` | "Zone-based compensation implemented but root cause not physically verified" |

### Structural problems with the zone-based approach

1. **Discontinuous jumps:** At 50° and 60° boundaries, compensation jumps by ±5°. A physical error curve would be smooth.

2. **All slopes are zero:** The infrastructure supports linear interpolation (`slope * phi_normalized + offset`) but all slopes = 0. Only step-function constants are used.

3. **Symmetric offsets (+0.014, -0.014):** Exactly opposite values suggest quick empirical tuning rather than systematic measurement.

4. **Masks multiple issues:** The single compensation system absorbs camera pitch error, gravity deflection, PID error, and structural compliance into one empirical correction. If any hardware changes, all parameters need re-tuning.

---

## 8. Timeline

| Date | Commit | Event |
|------|--------|-------|
| Jan 4, 2026 | `2cad9f9` | URDF created from SolidWorks export. Camera pitch = 45° (CAD value). |
| Jan 5, 2026 | `84198af` | Original motion_controller.cpp. `joint3_cmd = phi * RAD_TO_ROT`. No compensation. |
| Jan 12, 2026 | `ee50158` | Phi compensation added. Analysis doc created. Physical verification pending. |
| Jan 28, 2026 | `493044e` | Unresolved issues doc lists camera pitch measurement as "NOT DONE". |
| Jan 28, 2026 | `87b39b5` | Feb field trial plan: camera pitch measurement assigned, unchecked. |
| Feb 5, 2026 | `fb575a2` | URDF package renamed. Camera angles unchanged. |
| Feb 16, 2026 | — | This review: physical measurement still not done. |

**The 45° camera pitch has been in use for 43 days without physical verification.**

---

## 9. Comparison with J4 Offset Compensation

| Aspect | J4 Offset (d9893c1) | J3 Phi Compensation (ee50158) |
|--------|----------------------|-------------------------------|
| **Root cause** | TF frame mismatch (constant transform between sibling frames) | Unknown — attributed to camera pitch but math contradicts this |
| **Fix type** | Architecturally correct | Empirical workaround |
| **Mathematically proven?** | Yes — `j4_cmd = theta + offset` is exactly correct | No — zone-based step function approximates unknown smooth error |
| **Confidence in root cause** | High — kinematic chain analysis proves it | Low — primary hypothesis (camera pitch) produces constant error, not angle-dependent |
| **Physical verification** | Not needed (provable from URDF structure) | Needed but never done |
| **Risk** | Minimal | Moderate — masks multiple issues, discontinuous at zone boundaries |

---

## 10. The Proper Fix

### Step 1: Physical Measurement (CRITICAL, still pending)

Measure the actual camera pitch angle relative to the arm (procedure in `J3_PHI_ANGLE_ERROR_ANALYSIS.md` Section 5). If it differs from 45°, update the URDF:

```xml
<!-- MG6010_FLU.urdf, line 314 -->
<origin xyz="0.016845 0.100461 -0.077129"
        rpy="1.5708 [MEASURED_PITCH_RADIANS] 0" />
```

This eliminates the constant component of the error at zero runtime cost.

### Step 2: J3 PID Tuning

Tune the L3 motor PID to minimize steady-state error under gravity load. This addresses the angle-dependent mechanical component.

### Step 3: Systematic Error Characterization

After Steps 1 and 2, measure residual phi error at 5-10 degree increments across the full range. If residual angle-dependent error remains:
- Fit a smooth function (polynomial or sinusoidal) instead of step-function zones
- Characterize L5 extension coupling independently

### Step 4: Validate

Test picking accuracy across the full phi range after corrections.

---

## 11. Lessons Learned

1. **Qualitative geometric reasoning can mislead.** The original analysis's intuitive explanation of "error direction flipping" seemed plausible but is mathematically incorrect. A pure rotation error produces a constant offset, not an angle-dependent one. Mathematical proof should precede empirical workarounds.

2. **Empirical workarounds absorb multiple error sources.** The zone-based compensation conflates camera pitch error (constant), gravity deflection (angle-dependent), PID error (load-dependent), and structural compliance into one set of tuning parameters. This makes it fragile to hardware changes and difficult to diagnose further.

3. **"Pending physical verification" should be a blocker, not a footnote.** The camera pitch measurement has been pending for 43 days across multiple planning documents. Without it, the fundamental question — "is the URDF angle wrong?" — remains unanswered.

4. **The URDF camera pitch (45°) has never been calibrated.** It comes from a SolidWorks CAD export. CAD models represent design intent, not as-built reality. Manufacturing tolerances, assembly alignment, and field adjustments can all introduce discrepancies.

5. **r's immunity to rotation errors is a mathematical certainty, not a coincidence.** This key diagnostic observation (J5 correct, J3 wrong) correctly ruled out many hypotheses but was then attached to a root cause hypothesis that doesn't fully explain the angle-dependent pattern.
