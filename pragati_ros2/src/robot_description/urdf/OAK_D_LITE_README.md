# OAK-D Lite Camera URDF Integration Guide

## Overview

This directory contains the URDF/XACRO definition for the **Luxonis OAK-D Lite** spatial AI camera, which replaces the Intel RealSense D415 references that were incorrectly introduced during the ROS2 migration.

---

## File: `oak_d_lite_camera.xacro`

### Purpose

Provides a reusable XACRO macro to add the OAK-D Lite camera to your robot URDF with correct:
- Physical dimensions and mass
- TF frames for RGB, stereo (left/right), and depth
- REP-103 compliant optical frame conventions
- Stereo baseline (75mm) for accurate depth calculations

---

## Quick Start

### 1. Include in Your URDF

Add to your main robot URDF or XACRO file:

```xml
<?xml version="1.0"?>
<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="pragati_robot">
  
  <!-- Include OAK-D Lite camera definition -->
  <xacro:include filename="$(find robo_description)/urdf/oak_d_lite_camera.xacro"/>
  
  <!-- Your robot links and joints here -->
  <link name="camera_mount_link">
    <!-- Your camera mount definition -->
  </link>
  
  <!-- Instantiate OAK-D Lite camera -->
  <xacro:oak_d_lite_camera parent="camera_mount_link" name="oak">
    <origin xyz="0.02 0 0.01" rpy="0 0 0"/>  <!-- Adjust position as needed -->
  </xacro:oak_d_lite_camera>
  
</robot>
```

### 2. Verify TF Frames

After including the camera, you'll have these TF frames:

```
oak_camera_link                      # Physical camera body
├── oak_rgb_camera_frame             # RGB camera frame
│   └── oak_rgb_camera_optical_frame # RGB optical frame (Z forward, X right, Y down)
├── oak_left_camera_frame            # Left mono camera frame
│   └── oak_left_camera_optical_frame
├── oak_right_camera_frame           # Right mono camera frame  
│   └── oak_right_camera_optical_frame
└── oak_depth_frame                  # Depth frame (aligned to RGB)
    └── oak_depth_optical_frame
```

### 3. View in RViz

```bash
# Launch robot state publisher with your URDF
ros2 launch robo_description display.launch.py

# In RViz, add:
# - RobotModel display
# - TF display
# - Set Fixed Frame to: base_link (or your robot base)
```

---

## Macro Parameters

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `parent` | string | Parent link name to attach camera to |

### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | `oak` | Prefix for all camera frames |
| `origin` | block | `xyz="0 0 0" rpy="0 0 0"` | Camera position and orientation relative to parent |

### Example with Custom Parameters

```xml
<xacro:oak_d_lite_camera parent="end_effector_link" name="gripper_cam">
  <!-- Position: 5cm forward, rotated 45 degrees down -->
  <origin xyz="0.05 0 0" rpy="0 0.785 0"/>
</xacro:oak_d_lite_camera>
```

---

## Physical Specifications

### Luxonis OAK-D Lite

| Specification | Value |
|---------------|-------|
| **Dimensions** | 90mm (W) × 27mm (H) × 18.5mm (D) |
| **Mass** | 64g (0.064 kg) |
| **Stereo Baseline** | 75mm (left-right separation) |
| **RGB Sensor** | 4MP (IMX214), outputs 1920×1080 |
| **Mono Sensors** | 1MP (OV9282), outputs 400P for stereo |
| **Depth Range** | 0.2m - 10m (configurable) |
| **Interface** | USB 2.0 / USB 3.0 |
| **Power** | USB powered (5V) |

### Comparison with RealSense D415 (Replaced)

| Feature | OAK-D Lite | RealSense D415 (Old) |
|---------|-----------|----------------------|
| Stereo Baseline | 75mm | 55mm |
| On-Device AI | ✅ Yes (Myriad X VPU) | ❌ No |
| USB2 Mode | ✅ Stable | ⚠️ Limited |
| Mass | 64g | 72g |
| Cost | ~$150 | ~$180 |

---

## Frame Conventions

### REP-103 Compliance

All optical frames follow ROS REP-103 standard:
- **X**: Right
- **Y**: Down  
- **Z**: Forward (camera view direction)

### Frame Hierarchy

```
camera_mount_link (your robot)
  └─ oak_camera_link (camera body, X forward, Y left, Z up)
      ├─ oak_rgb_camera_frame (RGB sensor)
      │   └─ oak_rgb_camera_optical_frame (optical: Z forward)
      ├─ oak_left_camera_frame (left mono, +37.5mm Y)
      │   └─ oak_left_camera_optical_frame
      ├─ oak_right_camera_frame (right mono, -37.5mm Y)
      │   └─ oak_right_camera_optical_frame
      └─ oak_depth_frame (aligned to RGB)
          └─ oak_depth_optical_frame
```

---

## ROS2 Integration

### Camera Info Topics

When using the Phase 1/2 wrapper node:

```bash
/oak/rgb/camera_info           # RGB camera intrinsics
/oak/left/camera_info          # Left mono intrinsics (Phase 2+)
/oak/right/camera_info         # Right mono intrinsics (Phase 2+)
```

### Image Topics

```bash
/oak/rgb/image_raw             # RGB camera stream
/oak/stereo/depth              # Depth map (aligned to RGB)
/oak/left/image_rect           # Left mono image (Phase 2+)
/oak/right/image_rect          # Right mono image (Phase 2+)
```

### Detection Topics

```bash
/cotton_detection/results      # Cotton detections (Detection3DArray)
                               # Frame: oak_rgb_camera_optical_frame
```

---

## Calibration

### Factory Calibration

OAK-D Lite comes with factory calibration that includes:
- RGB camera intrinsics (fx, fy, cx, cy, distortion)
- Stereo camera intrinsics (left/right)
- Stereo extrinsics (baseline, rotation)

### Using Factory Calibration

The DepthAI SDK automatically reads and applies factory calibration. No manual calibration files needed for basic operation.

### Custom Calibration (Optional)

If you need custom calibration:

```bash
# 1. Export factory calibration
python3 -m depthai_sdk.calibration.reader \
    --device <device_id> \
    --export calibration.json

# 2. Modify as needed, then:
# Place in: src/cotton_detection_ros2/config/cameras/oak_d_lite/

# 3. Update launch file to load custom calibration
```

---

## Migration from RealSense

### Step 1: Update URDF References

**OLD (RealSense)**:
```xml
<link name="camera_link">
  <!-- RealSense D415 dimensions: 99×20×23mm -->
</link>
<link name="camera_color_optical_frame"/>
<link name="camera_depth_optical_frame"/>
```

**NEW (OAK-D Lite)**:
```xml
<xacro:include filename="$(find robo_description)/urdf/oak_d_lite_camera.xacro"/>
<xacro:oak_d_lite_camera parent="camera_mount_link" name="oak">
  <origin xyz="0 0 0" rpy="0 0 0"/>
</xacro:oak_d_lite_camera>
```

### Step 2: Update Frame References in Code

| Old Frame (RealSense) | New Frame (OAK-D Lite) |
|-----------------------|------------------------|
| `camera_color_optical_frame` | `oak_rgb_camera_optical_frame` |
| `camera_depth_optical_frame` | `oak_depth_optical_frame` |
| `camera_link` | `oak_camera_link` |

### Step 3: Update Launch Files

Update any hardcoded frame names in launch files:

```python
# Before
'camera_frame': 'camera_color_optical_frame'

# After  
'camera_frame': 'oak_rgb_camera_optical_frame'
```

---

## Testing

### Check URDF

```bash
# Check for XACRO errors
check_urdf <(xacro your_robot.urdf.xacro)

# View TF tree
ros2 run rqt_tf_tree rqt_tf_tree

# Visualize in RViz
ros2 launch robo_description display.launch.py
```

### Expected Output

```
URDF: OK
TF Tree should show:
  - oak_camera_link
  - oak_rgb_camera_optical_frame
  - oak_left_camera_optical_frame
  - oak_right_camera_optical_frame
  - oak_depth_optical_frame
```

---

## Troubleshooting

### Issue: "xacro: error: expected exactly one input file"

**Solution**: Make sure you're including the file correctly:
```xml
<xacro:include filename="$(find robo_description)/urdf/oak_d_lite_camera.xacro"/>
```

### Issue: TF frames not showing in RViz

**Solution**: 
1. Check robot_state_publisher is running
2. Verify URDF loaded correctly: `ros2 param get /robot_state_publisher robot_description`
3. Check for URDF errors: `check_urdf <(xacro your_robot.urdf.xacro)`

### Issue: Depth not aligned to RGB

**Solution**: 
- OAK-D Lite with `stereo.setDepthAlign(dai.CameraBoardSocket.RGB)` ensures alignment
- Check wrapper node has depth alignment enabled (default in Phase 1/2)

### Issue: Wrong stereo baseline

**Solution**:
- OAK-D Lite baseline is 75mm (factory calibrated)
- If using custom calibration, verify baseline in calibration file

---

## Additional Resources

- **Luxonis Docs**: https://docs.luxonis.com/projects/hardware/en/latest/pages/DM9095/
- **DepthAI Python API**: https://docs.luxonis.com/projects/api/en/latest/
- **REP-103 (Frames)**: https://www.ros.org/reps/rep-0103.html
- **Migration Docs**: See `/home/uday/Downloads/pragati_ros2/docs/OAK_D_LITE_HYBRID_MIGRATION_PLAN.md`

---

## Support

For issues or questions:
1. Check Phase 1-3 progress reports in `docs/`
2. Review `OAK_D_LITE_MIGRATION_ANALYSIS.md`
3. Test with camera hardware to validate TF frames

**Created**: October 2025  
**Phase**: 1-2 (Python Wrapper)  
**Status**: Production Ready
