# Polar vs Cylindrical Coordinate System Validation

**Document Type:** Analysis & Validation  
**Date:** 2025-11-05  
**Critical Issue:** Possible coordinate system mismatch between documentation and implementation  
**Status:** Investigation Required

---

## 🚨 Critical Question

**Your friend's observation:** The system was **incorrectly documented** as using "polar coordinates" in ROS1, but it should actually use **cylindrical coordinates**. During ROS1→ROS2 migration, the comments may have caused incorrect implementation of true polar/spherical coordinates instead of cylindrical.

---

## 📐 Coordinate Systems: Definitions

### **Cylindrical Coordinates (ρ, φ, z)**
```
Given Cartesian point (x, y, z):

ρ (rho)   = sqrt(x² + y²)        // Horizontal radius (projection onto XY plane)
φ (phi)   = atan2(y, x)          // Azimuth angle (rotation around Z-axis)
z         = z                     // Vertical height (unchanged)

Inverse (cylindrical → Cartesian):
x = ρ · cos(φ)
y = ρ · sin(φ)
z = z
```

**Use case:** Robots with vertical prismatic joint + rotating base + horizontal extension
- Joint2 (prismatic Z): z
- Joint3 (revolute Z): φ
- Joint5 (prismatic X): ρ (after joint4 rotation)

### **Polar/Spherical Coordinates (r, θ, φ)**
```
Given Cartesian point (x, y, z):

r         = sqrt(x² + y² + z²)   // 3D radial distance from origin
θ (theta) = atan2(y, x)          // Azimuth angle (horizontal rotation)
φ (phi)   = atan2(z, sqrt(x²+y²)) // Elevation angle (vertical angle from XY plane)

Inverse (spherical → Cartesian):
x = r · cos(φ) · cos(θ)
y = r · cos(φ) · sin(θ)
z = r · sin(φ)
```

**Use case:** Spherical robots, satellites, radar systems

---

## 🔍 Current ROS2 Implementation Analysis

### **Function Name Suggests Polar**
```cpp
// From coordinate_transforms.cpp:33-37
void convertXYZToPolarFLUROSCoordinates(double x, double y, double z, 
                                        double* r, double* theta, double* phi) {
    *r = sqrt(x*x + y*y + z*z);           // ❌ SPHERICAL: 3D distance
    *theta = atan2(y, x);                  // ✅ Both use this
    *phi = atan2(z, sqrt(x*x + y*y));     // ❌ SPHERICAL: elevation angle
}
```

### **What Cylindrical Should Be**
```cpp
void convertXYZToCylindricalFLUROSCoordinates(double x, double y, double z,
                                               double* rho, double* phi, double* z_out) {
    *rho = sqrt(x*x + y*y);               // ✅ CYLINDRICAL: horizontal radius
    *phi = atan2(y, x);                    // ✅ Same: azimuth angle
    *z_out = z;                            // ✅ CYLINDRICAL: vertical unchanged
}
```

---

## 🤖 Robot Kinematic Structure Analysis

Looking at the URDF:

```xml
Joint2: prismatic, axis=[0,0,1]  → Controls Z (height)
Joint3: revolute,  axis=[0,0,1]  → Controls φ (base rotation around Z)
Joint4: revolute,  axis=[0,1,0]  → Controls θ (elbow pitch)
Joint5: prismatic, axis=[1,0,0]  → Controls ρ (radial extension in XY plane)
```

### **Kinematic Chain Interpretation**

**If using CYLINDRICAL (ρ, φ, z):**
1. Joint2 moves to height `z`
2. Joint3 rotates base to angle `φ`
3. Joint4 tilts arm (for vertical reach within that φ slice)
4. Joint5 extends horizontally to radius `ρ`

**If using SPHERICAL (r, θ, φ):**
1. Must compute 3D distance `r` from origin
2. Joint3 rotates to `θ` (azimuth)
3. Joint4 rotates to match elevation `φ`
4. Joint5 extends to `r` (but this couples with elevation!)

---

## ⚠️ The Problem with Current Implementation

### **Current Code (Lines 33-36 in coordinate_transforms.cpp)**
```cpp
*r = sqrt(x*x + y*y + z*z);           // 3D spherical distance
*theta = atan2(y, x);                  // Azimuth (correct for both)
*phi = atan2(z, sqrt(x*x + y*y));     // Elevation angle from XY plane
```

### **How It's Used (motion_controller.cpp:271-313)**
```cpp
// Convert to "polar" (actually spherical)
yanthra_move::coordinate_transforms::convertXYZToPolarFLUROSCoordinates(
    position.x, position.y, position.z, &r, &theta, &phi);

// Command motors
joint_move_3_->move_joint(phi, false);    // ❌ phi = elevation (wrong!)
// joint4 is missing entirely
joint_move_5_->move_joint(r - LINK5_MIN_LENGTH, false);  // ❌ r = 3D distance (wrong!)
```

### **Why This is Wrong for the Robot**

1. **`phi` is elevation, not base rotation angle:**
   - Current: `phi = atan2(z, sqrt(x²+y²))` — vertical angle
   - Correct for Joint3 (base rotation): should be `atan2(y, x)` — horizontal angle

2. **`r` is 3D distance, not horizontal radius:**
   - Current: `r = sqrt(x²+y²+z²)` — includes vertical component
   - Correct for Joint5 (horizontal extension): should be `sqrt(x²+y²)` — XY plane only

3. **`theta` is computed but unused:**
   - This IS the correct angle for Joint3 base rotation!
   - But it's thrown away because variable names are swapped

---

## 🎯 Correct Cylindrical Mapping for This Robot

### **What SHOULD Happen:**

```cpp
// 1. Convert Cartesian to Cylindrical
double rho = sqrt(x*x + y*y);          // Horizontal radius → Joint5 target
double phi = atan2(y, x);              // Base rotation → Joint3 target
double z_target = z;                    // Vertical height → Joint2 target (if used)

// 2. Command joints
joint_move_2_->move_joint(z_target);              // Height (if implemented)
joint_move_3_->move_joint(phi, false);            // Base rotation (azimuth)
joint_move_4_->move_joint(theta_arm, false);      // Arm pitch (for vertical reach)
joint_move_5_->move_joint(rho - offset, false);   // Horizontal extension
```

### **Joint4 (Arm Pitch) Calculation:**
```cpp
// Joint4 should control the arm's tilt to reach the vertical height z
// while extending horizontally to rho
//
// Simplified (assuming no joint2 vertical movement):
double theta_arm = atan2(z, rho);  // Angle to tilt arm upward
```

---

## 🧪 Validation Tests

### **Test 1: Origin Point (0, 0, 0.5)**
Expected (not reachable, but shows calculation):
```
Cylindrical:
  rho = 0
  phi = undefined (x=y=0)
  z   = 0.5

Current Polar/Spherical:
  r     = 0.5
  theta = undefined
  phi   = π/2 (90°, pointing straight up)
```

**Problem:** Current code would set Joint3 to 90° (pointing up), but Joint3 is a **horizontal rotation**, not tilt!

### **Test 2: Horizontal Point (0.5, 0, 0)**
Expected:
```
Cylindrical:
  rho = 0.5 m     → Joint5 = 0.5 m horizontal extension
  phi = 0°        → Joint3 = 0° (forward)
  z   = 0         → Joint2 = 0 (no height change)

Current Polar/Spherical:
  r     = 0.5 m
  theta = 0°
  phi   = 0°      → Joint3 = 0° (happens to work)
```

**Coincidence:** Works here because z=0, so elevation angle is zero.

### **Test 3: Diagonal Point (0.3, 0.2, 0.4)**
Expected cylindrical:
```
  rho = sqrt(0.3² + 0.2²) = 0.361 m  → Joint5 horizontal
  phi = atan2(0.2, 0.3) = 0.588 rad (33.7°) → Joint3 base rotation
  z   = 0.4 m                        → Joint2 height (or Joint4 compensates)
```

Current polar/spherical:
```
  r     = sqrt(0.3² + 0.2² + 0.4²) = 0.538 m  ❌ Too long! (includes z)
  theta = atan2(0.2, 0.3) = 0.588 rad (33.7°)  ✅ Correct (but unused!)
  phi   = atan2(0.4, 0.361) = 0.833 rad (47.7°)  ❌ Wrong! (elevation, not rotation)
```

**Result:** 
- Joint3 would rotate to 47.7° (wrong angle)
- Joint5 would extend to 0.538m - offset (includes vertical component, too long!)
- Joint4 is never commanded (missing entirely)

---

## 📊 Side-by-Side Comparison

| Aspect | Current (Spherical) | Correct (Cylindrical) |
|--------|---------------------|------------------------|
| **Horizontal radius** | `r = sqrt(x²+y²+z²)` ❌ | `ρ = sqrt(x²+y²)` ✅ |
| **Base rotation** | `phi = atan2(z, sqrt(x²+y²))` ❌ | `φ = atan2(y, x)` ✅ |
| **Vertical** | Mixed into `r` and `phi` ❌ | `z` separate ✅ |
| **Joint3 command** | Receives `phi` (elevation) ❌ | Should receive `φ` (azimuth) ✅ |
| **Joint5 command** | Receives `r` (3D) ❌ | Should receive `ρ` (2D) ✅ |
| **Joint4 usage** | Not commanded ❌ | Controls arm pitch ✅ |
| **Variable names** | Misleading (theta unused, phi wrong) ❌ | Clear ✅ |

---

## 🔬 How to Validate

### **Method 1: Test with Known Position**

Place a test marker at **(0.5m, 0m, 0.3m)** from base:
```
Expected cylindrical:
  Joint3 (φ) = atan2(0, 0.5) = 0° (straight ahead)
  Joint5 (ρ) = 0.5m (horizontal extension)
  Joint2/4 handles z = 0.3m (height)

Current spherical:
  Joint3 (phi) = atan2(0.3, 0.5) = 0.540 rad (31°) ❌ WRONG!
  Joint5 (r) = sqrt(0.5²+0.3²) = 0.583m ❌ TOO LONG!
```

**If arm misses the target by ~31° rotation and extends too far, confirms spherical bug.**

### **Method 2: Check ROS1 Actual Implementation**

**CRITICAL FINDING FROM ROS1 CODE:**

```cpp
// From /home/uday/Downloads/pragati/src/yanthra_move/include/yanthra_move/yanthra_move.h:137-147
void ConvertXYZToPolarFLUROSCoordinates(double x, double y, double z, 
                                        double* r, double* theta, double* phi)
{
    // Comment says "This is very specific to FLU coordinate system"
    *r = sqrt(x*x + z*z);      // ❗ Uses X and Z only (XZ plane projection!)
    *phi = asin( z/ sqrt(x*x + z*z ));  // Angle in XZ plane
    *theta = y;                // ❗ Y is LINEAR, not angular!
}
```

**THIS IS THE KEY!** ROS1 uses a **custom coordinate system**:
- `r` = projection onto XZ plane (forward-vertical)
- `phi` = vertical angle in XZ plane
- `theta` = **LINEAR Y displacement** (left-right)

### **Method 3: Compare ROS1 vs ROS2 Formulas**

| Variable | ROS1 (Working) | ROS2 (Current) | Correct? |
|----------|----------------|----------------|----------|
| **r** | `sqrt(x² + z²)` | `sqrt(x² + y² + z²)` | ❌ ROS2 is 3D spherical |
| **theta** | `y` (linear!) | `atan2(y, x)` | ❌ ROS2 made it angular |
| **phi** | `asin(z / sqrt(x² + z²))` | `atan2(z, sqrt(x² + y²))` | ❌ Different planes! |

---

## 🎯 The REAL Problem: Misinterpretation During Migration

### **What ROS1 Actually Did (Lines 137-147)**

ROS1 used a **non-standard coordinate system** specific to this robot's geometry:

```
Input: Cartesian (x, y, z) in FLU frame
  x = Forward
  y = Left
  z = Up

Output:
  r     = sqrt(x² + z²)     // Distance in forward-vertical (XZ) plane
  phi   = asin(z / sqrt(x² + z²))  // Vertical tilt angle in XZ plane  
  theta = y                  // LINEAR left-right displacement (meters!)
```

**Joint Mapping in ROS1:**
- Joint3 (base rotation Z): Receives `joint3_pose + phiLink3` (where phiLink3 comes from Link3 frame)
- Joint4 (elbow rotation Y): Receives `thetaLink4` (computed from Link4 frame)
- Joint5 (extension X): Receives `rLink5_origin` (computed from Link5_origin frame)

### **What ROS2 Does (Lines 33-37 in coordinate_transforms.cpp)**

ROS2 implemented **true spherical coordinates** based on the "Polar" name:

```
Input: Cartesian (x, y, z)

Output:
  r     = sqrt(x² + y² + z²)       // TRUE 3D spherical radius
  theta = atan2(y, x)              // Azimuth in XY plane (ANGULAR!)
  phi   = atan2(z, sqrt(x² + y²))  // Elevation from XY plane
```

**Problem:** These formulas are mathematically correct for spherical coordinates, but **don't match the robot's kinematics** or ROS1's custom system!

---

## ✅ ROOT CAUSE IDENTIFIED

Your friend is **partially correct** but not in the way you'd expect:

1. **ROS1 wasn't using polar (spherical) OR cylindrical** — it used a **custom hybrid** system:
   - `r` in XZ plane (not XY, not 3D)
   - `phi` as vertical angle in XZ plane
   - `theta` as **linear Y displacement**, not an angle!

2. **During ROS1→ROS2 migration:**
   - Someone saw "Polar" in the function name
   - Implemented **textbook spherical coordinates** (mathematically correct)
   - But this doesn't match ROS1's behavior OR the robot's actual kinematics!

3. **The REAL issue:** 
   - ROS1 computed coordinates in **multiple frames** (Link3, Link4, Link5, Link5_origin)
   - Each frame has its own X,Y,Z that relate differently to joints
   - ROS2 only computes in one frame (yanthra_origin)
   - **Joint4 was used** in ROS1 but is now missing in ROS2

---

## 🛠️ What Should Actually Be Done

### **Option 1: Match ROS1 Exactly (Conservative)**

Restore ROS1's custom formula:
```cpp
void convertXYZToCustomRobotCoordinates(double x, double y, double z,
                                        double* r, double* theta, double* phi) {
    *r = sqrt(x*x + z*z);              // XZ plane projection
    *phi = asin(z / sqrt(x*x + z*z));  // Vertical angle
    *theta = y;                         // LINEAR (not angular!)
}
```

**But this still won't work properly** because ROS1 computed this **separately for each link frame**!

### **Option 2: Use Proper Inverse Kinematics (Correct)**

Given the robot structure:
- Joint2: Z-axis prismatic (height)
- Joint3: Z-axis revolute (base rotation)
- Joint4: Y-axis revolute (elbow pitch)
- Joint5: X-axis prismatic (extension)

The correct approach:

```cpp
void computeJointTargets(double x, double y, double z,
                        double* joint2, double* joint3, 
                        double* joint4, double* joint5) {
    // 1. Base rotation (Joint3) - angle to target in XY plane
    *joint3 = atan2(y, x);
    
    // 2. Horizontal reach in XY plane
    double rho_xy = sqrt(x*x + y*y);
    
    // 3. Arm pitch (Joint4) - angle to reach height z at distance rho_xy
    *joint4 = atan2(z, rho_xy);
    
    // 4. Extension (Joint5) - actual arm length needed
    *joint5 = rho_xy / cos(*joint4);  // Compensate for pitch
    
    // 5. Height (Joint2) - if vertical prismatic is used
    *joint2 = z - (*joint5) * sin(*joint4);  // Remaining height
}
```

---

## 📋 Validation Steps

### **Step 1: Verify ROS1 Behavior**

1. Find a working ROS1 system or logs
2. Command position (0.5m, 0.2m, 0.3m)
3. Record actual joint angles:
   - What does Joint3 move to?
   - What does Joint4 move to?
   - What does Joint5 extend to?

### **Step 2: Test ROS2 Current Behavior**

1. Command same position (0.5m, 0.2m, 0.3m)
2. Predict what ROS2 will do:
   ```
   r = sqrt(0.5² + 0.2² + 0.3²) = 0.616m
   theta = atan2(0.2, 0.5) = 0.380 rad (21.8°)
   phi = atan2(0.3, 0.539) = 0.489 rad (28.0°)
   
   Joint3 → 28.0° (wrong! should be 21.8° for base rotation)
   Joint4 → not commanded
   Joint5 → 0.616m - offset (wrong! too long)
   ```
3. Observe if end effector misses by these amounts

### **Step 3: Implement Correct IK**

1. Add proper inverse kinematics as shown in Option 2
2. Test same position
3. Verify end effector reaches within ±2cm

---

## 🔚 Conclusion

Your friend's observation is **insightful but incomplete**:

✅ **Correct:** There WAS a coordinate system mismatch during migration  
✅ **Correct:** ROS2's "polar" implementation doesn't match ROS1  
❌ **Incomplete:** It's not about polar vs cylindrical — ROS1 used a **custom hybrid**  
❌ **Incomplete:** The real issue is **missing Joint4** + **single-frame computation**  

**The fix requires:**
1. Add Joint4 back (already documented in COMPLETE_COTTON_POSITION_TO_MOTOR_FLOW.md)
2. Either:
   - Restore ROS1's multi-frame computation (complex)
   - Implement proper inverse kinematics (better long-term)
3. Test extensively with known positions

---

**Next Steps:**
1. Validate findings with hardware tests
2. Decide on Option 1 (conservative) vs Option 2 (correct IK)
3. Implement chosen solution
4. Add unit tests for coordinate transformations

---

**Document Version:** 1.0  
**Related:** See docs/COMPLETE_COTTON_POSITION_TO_MOTOR_FLOW.md for Joint4 fix details
