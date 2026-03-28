# Camera Coordinate System Investigation - Complete Findings

**Date:** November 16, 2025  
**Investigation Focus:** DepthAI camera coordinate system and ROS frame setup

---

## TL;DR - Key Findings

1. **DepthAI outputs:** RUF (Right-Up-Forward) - Y-axis points UP
2. **ROS standard (REP-103):** RDF (Right-Down-Forward) - Y-axis points DOWN
3. **Current system:** No optical frames, ambiguous coordinate system
4. **Solution:** Use `oak_d_lite_camera.xacro` + negate Y in code

---

## Question 1: What coordinate system does DepthAI use?

### Investigation Method:
- Examined `/home/uday/Downloads/pragati_ros2/src/cotton_detection_ros2/include/cotton_detection_ros2/depthai_manager.hpp`
- Analyzed code comments in struct `CottonDetection`

### Finding:

**DepthAI uses RUF (Right-Up-Forward) coordinate system:**

```cpp
struct CottonDetection {
    // Spatial coordinates (millimeters)
    float spatial_x;  // Left(-) / Right(+) from camera center
    float spatial_y;  // Down(-) / Up(+) from camera center    ← UP is positive!
    float spatial_z;  // Distance from camera
};
```

**Coordinate System:**
- **X-axis:** Right (+), Left (-)
- **Y-axis:** **Up (+)**, Down (-)  ← NOT standard!
- **Z-axis:** Forward (+), Backward (-)

**This is RUF, not RDF!**

---

## Question 2: Are we using the depthai-ros driver?

### Investigation Method:
- Checked `package.xml` dependencies
- Analyzed source code imports

### Finding:

**NO - We are using DepthAI C++ API directly**

**Evidence:**
1. `package.xml` shows:
   ```xml
   <exec_depend>depthai</exec_depend>         <!-- C++ library -->
   <exec_depend>depthai_bridge</exec_depend>  <!-- For conversions -->
   ```

2. Code uses `dai::` namespace directly:
   ```cpp
   std::unique_ptr<dai::Device> device_;
   std::shared_ptr<dai::Pipeline> pipeline_;
   std::shared_ptr<dai::DataOutputQueue> detection_queue_;
   ```

**We are NOT using:**
- ❌ `depthai-ros` ROS2 wrapper package
- ❌ `depthai_ros_driver` node
- ❌ Pre-built camera publishers

**We ARE using:**
- ✅ DepthAI C++ API directly (`libdepthai`)
- ✅ Custom integration in `depthai_manager.cpp`
- ✅ Manual ROS message publishing

**Implications:**
- We control the coordinate system conversion
- We publish to custom frame_id ("camera_link")
- We need to handle coordinate transforms ourselves
- No automatic optical frame publishing from depthai-ros

---

## Question 3: What URDF camera setup do we have?

### Investigation Method:
- Compared ROS1 vs ROS2 URDF files
- Analyzed frame hierarchy

### Finding:

**ROS2 LOST optical frames that existed in ROS1!**

#### ROS1 Setup (`/home/uday/Downloads/pragati/src/robo_description/urdf/URDF`):
```
camera_link
  ├─ camera_depth_frame
  │   └─ camera_depth_optical_frame (rpy="0 0 0" - wrong!)
  └─ camera_color_frame
      └─ camera_color_optical_frame (rpy="0 0 0" - wrong!)
```
- ✅ Had optical frames
- ❌ Wrong rotation (not REP-103 compliant)
- 8 total frames

#### ROS2 Current (`/home/uday/Downloads/pragati_ros2/src/robot_description/urdf/MG6010_final.urdf`):
```
camera_mount_link
  └─ camera_link
      [NO OPTICAL FRAMES]
```
- ❌ No optical frames at all
- ❌ Coordinate system completely undefined
- 2 total frames
- **REGRESSION from ROS1**

---

## Question 4: What is the oak_d_lite_camera.xacro file?

### Investigation Method:
- Examined file contents and comments
- Checked git history and documentation

### Finding:

**A proper REP-103 compliant OAK-D Lite camera model**

**Created:** November 9, 2024  
**Purpose:** Replace incorrect RealSense references with proper OAK-D Lite specs  
**Status:** ❌ Exists but NOT currently used in MG6010_final.urdf

**What it provides:**
```
oak_camera_link (physical body: X=forward, Y=left, Z=up)
  ├─ oak_rgb_camera_frame
  │   └─ oak_rgb_camera_optical_frame (rpy="-90° 0 -90°") ✅ CORRECT!
  ├─ oak_left_camera_frame
  │   └─ oak_left_camera_optical_frame (rpy="-90° 0 -90°")
  ├─ oak_right_camera_frame
  │   └─ oak_right_camera_optical_frame (rpy="-90° 0 -90°")
  └─ oak_depth_frame
      └─ oak_depth_optical_frame
```

**Specifications:**
- ✅ 9 frames with proper optical frame hierarchy
- ✅ REP-103 compliant rotation: rpy="-1.5708 0 -1.5708"
- ✅ Accurate mass: 64g (matches OAK-D Lite)
- ✅ Accurate dimensions: 90mm × 27mm × 18.5mm
- ✅ Stereo baseline: 75mm
- ✅ Reusable parameterized macro

---

## The Complete Picture

### Current System Flow:

```
DepthAI Camera (hardware)
  ↓ (outputs RUF coordinates)
dai::SpatialImgDetection
  ↓ (no conversion)
CottonDetection struct
  spatial_x = det.spatialCoordinates.x  // Right
  spatial_y = det.spatialCoordinates.y  // UP (not standard!)
  spatial_z = det.spatialCoordinates.z  // Forward
  ↓ (published to)
"camera_link" frame (no optical frame, undefined coordinate system)
```

**Problems:**
1. DepthAI outputs RUF, but standard is RDF
2. No optical frame to define coordinate system
3. Code publishes to "camera_link" with ambiguous meaning
4. Lost optical frames that ROS1 had

---

## Solution: Two Changes Required

### Change 1: Fix Code (depthai_manager.cpp)

**Negate Y coordinate to convert RUF → RDF:**

```cpp
// In depthai_manager.cpp, line ~1010-1012
result.spatial_x = det.spatialCoordinates.x;     // Right (matches RDF)
result.spatial_y = -det.spatialCoordinates.y;    // Down = -Up (FIX!)
result.spatial_z = det.spatialCoordinates.z;     // Forward (matches RDF)
```

**Reason:** DepthAI outputs Y-up, but REP-103 optical frames expect Y-down

### Change 2: Fix URDF (MG6010_final.urdf)

**Use oak_d_lite_camera.xacro:**

```xml
<!-- In MG6010_final.urdf, replace camera_mount_link/camera_link with: -->

<xacro:include filename="$(find robot_description)/urdf/oak_d_lite_camera.xacro"/>

<xacro:oak_d_lite_camera parent="link7" name="oak">
  <origin xyz="-0.066 0 0.0175" rpy="-1.5708 0 -1.5708"/>
</xacro:oak_d_lite_camera>
```

**Then update code to use optical frame:**

```cpp
// In cotton_detection_node_publishing.cpp
result_msg.header.frame_id = "oak_rgb_camera_optical_frame";  // Was "camera_link"
transform.child_frame_id = "oak_rgb_camera_optical_frame";
```

**Reason:** Provides proper REP-103 compliant optical frame with RDF coordinate system

---

## REP-103 Standard

**REP-103 defines coordinate frames for mobile robots:**

### Body Frame (camera_link):
- **X:** Forward (camera viewing direction)
- **Y:** Left
- **Z:** Up

### Optical Frame (camera_optical_frame):
- **X:** Right (+X points right when looking through camera)
- **Y:** Down (+Y points down when looking through camera)
- **Z:** Forward (+Z points in viewing direction)

### Rotation from Body to Optical:
```
rpy = "-1.5708 0 -1.5708"  (Roll=-90°, Pitch=0°, Yaw=-90°)
```

**This creates the RDF (Right-Down-Forward) coordinate system**

---

## Historical Context

### ROS1 Era:
- ✅ Had optical frames (camera_depth_optical_frame, camera_color_optical_frame)
- ❌ But rotation was wrong: rpy="0 0 0" (not REP-103 compliant)
- Camera: Likely Intel RealSense D415

### ROS1 → ROS2 Migration:
- ❌ Removed all optical frames (regression!)
- ❌ Didn't fix REP-103 compliance
- ❌ Changed to OAK-D Lite but didn't update URDF properly
- ⚠️ Changed camera offset from xyz="-0.066, 0, 0.0175" to xyz="0, 0, 0.0175"

### Current ROS2:
- ❌ No optical frames at all
- ❌ Ambiguous coordinate system
- ❌ Using DepthAI C++ API directly with custom integration
- Result: Worse than ROS1 in frame structure

---

## Recommendation Summary

| What | Why | Priority |
|------|-----|----------|
| **Negate Y in code** | Convert RUF → RDF | ✅ REQUIRED |
| **Use oak_d_lite_camera.xacro** | Restore optical frames, REP-103 compliance | ✅ REQUIRED |
| **Update frame_id** | Use "oak_rgb_camera_optical_frame" | ✅ REQUIRED |
| **Restore X offset** | Match ROS1 calibration (-0.066m) | ⚠️ VERIFY NEEDED |

**Estimated Effort:** 2-3 hours  
**Risk Level:** Low (can keep old frames temporarily during migration)

---

## Related Documents

- `CAMERA_SETUP_COMPARISON.md` - Detailed current vs xacro comparison
- `ROS1_VS_ROS2_CAMERA_ANALYSIS.md` - Complete migration analysis
- `oak_d_lite_camera.xacro` - Proper camera URDF definition
- `src/robot_description/urdf/OAK_D_LITE_README.md` - Integration guide

---

## References

- **REP-103:** https://www.ros.org/reps/rep-0103.html
- **DepthAI C++ API:** https://docs.luxonis.com/software/depthai/
- **depthai-ros (not used):** https://docs.luxonis.com/software/ros/depthai-ros/driver
- **OAK-D Lite specs:** https://docs.luxonis.com/hardware/products/oakd-lite/

---

---

## Implementation Status (Updated 2025-11-17)

### ✅ Implemented: RUF → FLU Conversion

**Location:** `src/cotton_detection_ros2/src/cotton_detection_node_depthai.cpp`  
**Function:** `get_depthai_detections()`  
**Lines:** 259-287

**What was done:**
- Added explicit coordinate conversion from DepthAI's RUF (Right-Up-Forward) to arm's FLU (Forward-Left-Up)
- Conversion happens before publishing to ROS, after receiving from DepthAI
- Raw RUF values preserved in `depthai_manager.cpp` (no changes upstream)

**Conversion Formula:**
```cpp
// DepthAI outputs (RUF):
//   spatial_x: +Right / -Left
//   spatial_y: +Up / -Down  
//   spatial_z: +Forward (distance from camera)

// Convert to FLU for arm:
result.position.x = det.spatial_z / 1000.0;   // Forward (from RUF Z) -> FLU X
result.position.y = -det.spatial_x / 1000.0;  // Left (from -RUF X) -> FLU Y
result.position.z = det.spatial_y / 1000.0;   // Up (from RUF Y) -> FLU Z
```

**Logging:**
- First log: Shows RAW DepthAI values in RUF (mm)
  ```
  🔍 RAW DepthAI (RUF): spatial_x=...mm (right), spatial_y=...mm (up), spatial_z=...mm (fwd)
  ```
- Second log: Shows RDF (REP-103 standard optical frame) for debugging (meters)
  ```
  🔧 RDF (REP-103):     x=...m (right), y=...m (down), z=...m (fwd)
  ```
- Third log: Shows CONVERTED values in FLU (meters) - **THIS IS WHAT GETS PUBLISHED**
  ```
  📍 CONVERTED (FLU):   x=...m (fwd), y=...m (left), z=...m (up), conf=...
  ```

**Benefits:**
- ✅ Explicit and well-documented conversion
- ✅ All three coordinate systems visible in logs for debugging (RUF, RDF, FLU)
- ✅ RDF values computed for easy comparison with REP-103 standard
- ✅ Easy to switch to RDF if needed (just change which values get published)
- ✅ No confusion about coordinate systems
- ✅ Easy to verify and maintain

**Status:** ✅ COMPLETE - Built and ready for testing

**How to Switch Coordinate Systems (if needed):**

If you need to switch from FLU to RDF for debugging or testing:

1. Open `src/cotton_detection_ros2/src/cotton_detection_node_depthai.cpp`
2. Find lines 270-272 (the FLU conversion)
3. Comment out the FLU lines and uncomment the RDF lines:

```cpp
// OPTION 1: FLU (Forward-Left-Up) - DEFAULT for arm
result.position.x = det.spatial_z / 1000.0;   // Forward
result.position.y = -det.spatial_x / 1000.0;  // Left
result.position.z = det.spatial_y / 1000.0;   // Up

// OPTION 2: RDF (Right-Down-Forward) - REP-103 optical frame standard
// Uncomment these lines to use RDF instead:
// result.position.x = rdf_x;  // Right
// result.position.y = rdf_y;  // Down
// result.position.z = rdf_z;  // Forward
```

4. Rebuild: `colcon build --packages-select cotton_detection_ros2 --symlink-install`
5. The logs will still show all three coordinate systems for comparison

---

## Verification Checklist

After implementing changes:

- [x] RUF → FLU conversion added in cotton_detection_node_depthai.cpp
- [x] Conversion documented with inline comments
- [x] Logging updated to show both RUF and FLU coordinates
- [x] Package rebuilt successfully
- [ ] Tested with live camera to verify coordinate behavior
- [ ] oak_d_lite_camera.xacro is included in MG6010_final.urdf
- [ ] frame_id updated to "oak_rgb_camera_optical_frame" in publishing code
- [ ] TF tree shows 9 camera frames (not 2)
- [ ] `ros2 run tf2_tools view_frames` shows optical frames
- [ ] Coordinate transforms validated in RViz
- [ ] Cotton detection still works correctly with new coordinates

