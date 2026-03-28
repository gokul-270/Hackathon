# Frame Reference Guide: base_link vs yanthra_link

**Date:** 2025-11-15  
**Purpose:** Clarify which reference frame is used for coordinate transformations

---

## 🎯 **Quick Answer**

**We use `yanthra_link` frame** for all calculations and motor commands.

- **Primary frame:** `yanthra_link` (computational reference)
- **Fallback frame:** `base_link` (if yanthra_link doesn't exist)
- **Physical base:** `base_link` (robot base on the ground)

---

## 📐 **URDF Frame Hierarchy**

From `MG6010_final.urdf`:

```
base_link (robot base, fixed to ground)
  ↓ [joint2 - prismatic Z, +0.45922m]
link2
  ↓ [joint4 - prismatic +Y, +0.33411m]
link4
  ↓ [joint3 - revolute -Y axis, offset -0.0675, 0.042, -0.127]
link3
  ↓ [yantra_joint - FIXED, offset 0, -0.082, 0]
yanthra_link  ← THIS IS THE WORKING FRAME!
  ↓ (fixed)
link5_origin
  ↓ [joint5 - prismatic +X]
link5
  ↓ (chain continues to camera_link via link7)
camera_link
```

---

## 🔍 **Why yanthra_link and NOT base_link?**

### **1. Historical Reason**
From ROS1 legacy code - `yanthra_link` was established as the computational reference frame where:
- Joint angles are measured relative to this frame
- Polar coordinates are calculated in this frame
- Forward kinematics chain starts here

### **2. URDF Structure**
- `base_link` is the **physical base** (on the ground)
- `yanthra_link` is a **computational reference** frame positioned at the rotating platform after joint3
- `yanthra_link` is **fixed relative to link3** (via `yantra_joint` - note the typo in URDF!)

### **3. Code Evidence**

**Primary Usage** (`motion_controller.cpp:363`):
```cpp
auto transform = tf_buffer_->lookupTransform(
    "yanthra_link",      // ← Target frame (WE USE THIS!)
    "camera_link",       // ← Source frame
    tf2::TimePointZero,
    tf2::durationFromSec(0.5)
);
```

**Fallback Logic** (`coordinate_transforms.cpp:51-58`):
```cpp
// Try yanthra_link first, fallback to base_link if not available
try {
    transform = tf_buffer.lookupTransform("yanthra_link", "camera_link", ...);
    LOG_DEBUG("Transform lookup successful: camera_link -> yanthra_link");
} catch (tf2::TransformException &ex1) {
    // Fallback to base_link if yanthra_link doesn't exist
    transform = tf_buffer.lookupTransform("base_link", "camera_link", ...);
    LOG_DEBUG("Transform lookup successful (fallback): camera_link -> base_link");
}
```

---

## 🧭 **Coordinate Frame Properties**

### **yanthra_link Frame Axes:**
- **X:** Forward (radial extension direction for joint5)
- **Y:** Left/right (lateral movement for joint4)
- **Z:** Up (vertical)

### **Relationship to base_link:**
```
yanthra_link origin = base_link origin + transformations through:
  - joint2 (height adjustment, Z-axis)
  - joint4 (lateral position, Y-axis)
  - joint3 (rotation about -Y axis)
  - Fixed offset from link3 (-82mm in Y)
```

---

## 📊 **Transform Flow in Code**

### **Forward Flow (Camera → Motors):**

```
camera_link coordinates (X, Y, Z from ArUco/HSV)
         ↓
   [TF Transform]
         ↓
yanthra_link coordinates (X, Y, Z)  ← WORKING FRAME
         ↓
   [Polar Conversion]
         ↓
Polar (r, theta, phi) in yanthra_link
         ↓
   [Direct Mapping - NO IK]
         ↓
Joint commands (joint3, joint4, joint5)
         ↓
   [Motor Conversion]
         ↓
Motor angles → CAN messages
```

### **Key Code Locations:**

1. **TF Transform** (`motion_controller.cpp:362-370`):
   ```cpp
   transform = tf_buffer_->lookupTransform("yanthra_link", "camera_link", ...);
   tf2::doTransform(target_camera, target_base, transform);
   // target_base is now in yanthra_link frame!
   ```

2. **Polar Conversion** (`motion_controller.cpp:390-394`):
   ```cpp
   // Uses yanthra_link coordinates!
   yanthra_move::coordinate_transforms::convertXYZToPolarFLUROSCoordinates(
       target_base.point.x,    // X in yanthra_link
       target_base.point.y,    // Y in yanthra_link  
       target_base.point.z,    // Z in yanthra_link
       &r, &theta, &phi
   );
   ```

3. **Joint Commands** (`motion_controller.cpp:410-467`):
   ```cpp
   joint3_cmd = phi * RAD_TO_ROT;     // phi relative to yanthra_link
   joint4_cmd = theta;                 // Y-coordinate in yanthra_link
   joint5_cmd = r - offset;            // Radial in yanthra_link
   ```

---

## ❓ **Common Questions**

### **Q: Why not just use base_link for everything?**
**A:** Historical convention + code structure. The system was designed with `yanthra_link` as the reference frame for joint calculations. Using `base_link` would require:
- Recalculating all polar conversions
- Adjusting joint offset assumptions
- Validating against existing calibration data
- Risk of breaking working pick sequences

### **Q: What if yanthra_link doesn't exist in my TF tree?**
**A:** The code has a fallback to `base_link` (see `coordinate_transforms.cpp:58`). However, calculations may be incorrect if frame conventions differ.

### **Q: How do I verify which frame is being used?**
**A:** Check the logs during a pick operation:
```bash
# Look for this line:
[motion_controller]: ✅ TF transform successful: camera_link → yanthra_link
```

Or manually query TF:
```bash
ros2 run tf2_ros tf2_echo yanthra_link camera_link
```

---

## 🔧 **For Forward Kinematics (Reverse Flow)**

When computing **joint positions → camera coordinates**:

1. Start with joint values
2. Build FK chain from `base_link` through the URDF structure
3. Compute `T_base_camera` (camera pose in base frame)
4. Extract camera position: `p_camera = T_base_camera[:3, 3]`

**Note:** Even though runtime calculations use `yanthra_link`, FK must start from `base_link` because URDF defines all links relative to the base.

---

## ✅ **Summary Table**

| Aspect | base_link | yanthra_link |
|--------|-----------|--------------|
| **Physical meaning** | Robot base on ground | Rotating platform after joint3 |
| **URDF parent** | Root of tree | Child of link3 |
| **Used for runtime** | Fallback only | **Primary working frame** ✅ |
| **Polar coords calculated in** | No | **Yes** ✅ |
| **Joint commands relative to** | No | **Yes** ✅ |
| **FK starts from** | **Yes** (URDF root) ✅ | No |
| **Code references** | 2 fallback cases | **20+ primary uses** ✅ |

---

## 🎓 **Best Practice**

**Always use `yanthra_link` for runtime calculations:**
- TF lookups: `lookupTransform("yanthra_link", "camera_link", ...)`
- Polar conversions: In `yanthra_link` frame
- Joint commands: Relative to `yanthra_link`

**Use `base_link` only for:**
- URDF visualization (rviz)
- Forward kinematics from scratch
- Documentation of physical robot structure

---

**Related Files:**
- `src/yanthra_move/src/core/motion_controller.cpp:363`
- `src/yanthra_move/src/coordinate_transforms.cpp:54`
- `src/robot_description/urdf/MG6010_final.urdf:381-430`
