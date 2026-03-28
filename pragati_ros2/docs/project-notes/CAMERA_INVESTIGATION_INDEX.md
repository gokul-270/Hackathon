# Camera Coordinate System Investigation - Document Index

**Investigation Date:** November 16, 2025  
**Topic:** DepthAI camera coordinate system, ROS frame setup, and ROS1→ROS2 migration analysis

---

## Quick Answer

**Q: What coordinate system does DepthAI output?**  
**A:** RUF (Right-Up-Forward) - Y-axis points UP, not DOWN like REP-103 standard requires.

**Q: What do we need to fix?**  
**A:** Two things:
1. Negate Y coordinate in code: `spatial_y = -det.spatialCoordinates.y`
2. Use `oak_d_lite_camera.xacro` to add proper optical frames

---

## Investigation Documents

### 1. **CAMERA_COORDINATE_SYSTEM_FINDINGS.md** ⭐ START HERE
**Purpose:** Complete findings summary answering all investigation questions

**Contents:**
- DepthAI coordinate system (RUF vs RDF)
- Whether we use depthai-ros driver (NO - direct C++ API)
- Current URDF setup analysis
- Complete solution with code examples
- Verification checklist

**Best for:** Understanding the complete picture and implementation steps

---

### 2. **CAMERA_SETUP_COMPARISON.md**
**Purpose:** Detailed technical comparison of camera setups

**Contents:**
- Executive summary table
- Frame hierarchy comparison (Current 2 frames vs xacro 9 frames)
- Coordinate system analysis
- Physical properties comparison
- REP-103 compliance analysis
- Code integration impact
- Migration complexity assessment

**Best for:** Technical deep-dive, understanding why oak_d_lite_camera.xacro is better

---

### 3. **ROS1_VS_ROS2_CAMERA_ANALYSIS.md**
**Purpose:** Historical analysis of ROS1→ROS2 migration

**Contents:**
- Complete ROS1 URDF camera setup
- What was lost in migration (6 frames!)
- Side-by-side comparison table
- Root cause analysis
- Migration timeline
- Restoration plan

**Best for:** Understanding how we got here, historical context

---

## Key Findings Summary

### Current Problems:
1. ❌ **No optical frames** in ROS2 (lost during migration from ROS1)
2. ❌ **Ambiguous coordinate system** (no frame definition)
3. ❌ **DepthAI outputs RUF** but standard is RDF
4. ❌ **Wrong mass** (104g vs 64g actual)
5. ❌ **No stereo baseline** defined

### Solution:
✅ **Use oak_d_lite_camera.xacro** + **Negate Y in code**

### Impact:
- Restores 7 lost frames (9 total vs current 2)
- Adds REP-103 compliant optical frames
- Fixes coordinate system ambiguity
- Matches OAK-D Lite hardware specs
- Enables proper debugging via TF tree

---

## Implementation Checklist

### Code Changes:

**File:** `src/cotton_detection_ros2/src/depthai_manager.cpp`
```cpp
// Line ~1010-1012, change from:
result.spatial_y = det.spatialCoordinates.y;

// To:
result.spatial_y = -det.spatialCoordinates.y;  // Convert RUF → RDF
```

**File:** `src/cotton_detection_ros2/src/cotton_detection_node_publishing.cpp`
```cpp
// Change frame_id from:
result_msg.header.frame_id = "camera_link";

// To:
result_msg.header.frame_id = "oak_rgb_camera_optical_frame";
```

### URDF Changes:

**File:** `src/robot_description/urdf/MG6010_final.urdf`

**Step 1 - Add include (near top):**
```xml
<xacro:include filename="$(find robot_description)/urdf/oak_d_lite_camera.xacro"/>
```

**Step 2 - Replace camera links:**
Remove:
```xml
<link name="camera_mount_link">...</link>
<joint name="camera_mount_joint">...</joint>
<link name="camera_link">...</link>
<joint name="camera_link_joint">...</joint>
```

Add:
```xml
<xacro:oak_d_lite_camera parent="link7" name="oak">
  <origin xyz="-0.066 0 0.0175" rpy="-1.5708 0 -1.5708"/>
</xacro:oak_d_lite_camera>
```

**Note:** Consider verifying the X offset (-0.066m from ROS1 vs 0m in current ROS2)

---

## Testing & Verification

After making changes:

```bash
# 1. Build
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select robot_description cotton_detection_ros2

# 2. Source
source install/setup.bash

# 3. Launch system
ros2 launch yanthra_move pragati_complete.launch.py

# 4. View TF tree (in new terminal)
ros2 run tf2_tools view_frames
# Should show 9 oak_* frames now (not 2)

# 5. Check frames in RViz
# Add TF display, should see:
# - oak_camera_link
# - oak_rgb_camera_optical_frame
# - oak_left_camera_optical_frame
# - oak_right_camera_optical_frame
# - oak_depth_optical_frame
# (and intermediate frames)

# 6. Verify coordinates
# Y-down should now be positive (cotton below camera has +Y)
```

---

## References

- **REP-103 Standard:** https://www.ros.org/reps/rep-0103.html
- **DepthAI C++ API:** https://docs.luxonis.com/software/depthai/
- **OAK-D Lite Specs:** https://docs.luxonis.com/hardware/products/oakd-lite/
- **ROS TF Tutorial:** https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Introduction-To-Tf2.html

---

## Document Creation Timeline

1. **Initial question:** "What coordinate system does DepthAI use?"
2. **Investigation:** Code analysis, URDF comparison, ROS1 vs ROS2
3. **Discovery:** ROS2 lost optical frames that ROS1 had
4. **Solution:** Two-part fix (code + URDF)
5. **Documentation:** Three comprehensive analysis documents

---

**For questions or clarifications, refer to the detailed documents above.**

