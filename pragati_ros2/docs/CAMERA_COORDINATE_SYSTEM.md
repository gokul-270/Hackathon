# Camera Coordinate System - OAK-D Lite

> **📍 MOVED:** This content has been consolidated into the Camera Setup and Diagnostics Guide.
> 
> **New Location:** [guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md](guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md#coordinate-system)
> 
> This file is preserved for historical reference. For current documentation, please refer to the consolidated guide above.

---

**Date:** November 1, 2025  
**Camera:** OAK-D Lite  
**Detection System:** C++ DepthAI Direct Integration

---

## 📐 Coordinate Frame Convention

The OAK-D Lite camera uses a **right-handed coordinate system** with the following conventions:

```
        Z (depth, forward)
        ↑
        |
        |
        o----→ X (right)
       /
      ↙
     Y (down)
```

### Axis Definitions

| Axis | Direction | Range | Notes |
|------|-----------|-------|-------|
| **X** | Right (+) / Left (-) | -300mm to +300mm typical | Horizontal displacement |
| **Y** | Down (+) / Up (-) | -300mm to +300mm typical | Vertical displacement |
| **Z** | Forward (+) / Backward (-) | 200mm to 2000mm | Depth from camera |

---

## 🎯 Detection Coordinate System

When the detection system reports coordinates like `(X=-90, Y=145, Z=657)`:

- **X = -90mm**: Object is **90mm to the LEFT** of camera center
- **Y = 145mm**: Object is **145mm BELOW** camera center  
- **Z = 657mm**: Object is **657mm FORWARD** from camera (depth)

### Coordinate Origin

The origin `(0, 0, Z)` is located at:
- **Center of the camera's field of view** (horizontal center)
- **Camera optical axis** (vertical center)
- **At the camera's image sensor plane** (Z=0)

---

## 🔄 Transformation to Robot Frame

If you need to transform camera coordinates to robot base frame, apply the following:

### Option 1: Static Transform in Launch File

```xml
<node pkg="tf2_ros" exec="static_transform_publisher" 
      args="0 0 0.5 0 0 0 base_link camera_link"/>
```

### Option 2: Coordinate Mapping

```python
# Camera frame to robot frame
robot_x = camera_z  # Forward in camera = forward in robot
robot_y = -camera_x # Left in camera = left in robot  
robot_z = -camera_y # Down in camera = up in robot
```

---

## 🧪 Validation Examples

### Example 1: Object to the Right
```
Camera Output: (X=+150, Y=0, Z=800)
Interpretation: Object 150mm RIGHT, centered vertically, 800mm forward
```

### Example 2: Object Above and Left
```
Camera Output: (X=-90, Y=-100, Z=650)
Interpretation: Object 90mm LEFT, 100mm ABOVE center, 650mm forward
```

### Example 3: Object Below and Right
```
Camera Output: (X=+120, Y=+80, Z=750)
Interpretation: Object 120mm RIGHT, 80mm BELOW center, 750mm forward
```

---

## 📊 Observed Behavior (Nov 1, 2025)

From recent testing logs:

```
Detection Result:
  X: -90mm  (90mm to the LEFT)
  Y: 145mm  (145mm BELOW center)
  Z: 657mm  (657mm forward)
```

This is **correct behavior** - negative X values indicate left displacement, which is expected when objects are positioned to the left of the camera center.

---

## ⚠️ Common Misconceptions

### ❌ "Negative X is wrong"
**Incorrect.** Negative X is expected for objects to the left of center.

### ❌ "Coordinates should always be positive"
**Incorrect.** Only Z (depth) is typically positive. X and Y can be negative depending on object position.

### ✅ Correct Understanding
The coordinate system uses **signed values** to indicate direction relative to the camera's optical center.

---

## 🔗 Frame ID in ROS2 Messages

The detection messages use:
- **Frame ID**: `oak_rgb_camera_optical_frame`
- **Message Type**: `vision_msgs/msg/Detection3DArray`
- **Coordinate Units**: Meters (m) in ROS2 messages, millimeters (mm) in logs

---

## 🛠️ Debugging Coordinate Issues

If you suspect coordinate frame issues:

1. **Verify Camera Mounting**: Ensure camera is mounted level and facing forward
2. **Check Transform Tree**: `ros2 run tf2_tools view_frames`
3. **Test Known Positions**: Place object at known location and verify coordinates
4. **Visualize in RViz**: Use RViz to display detection results in 3D

---

## 📚 References

- **DepthAI Spatial Coordinates**: [docs.luxonis.com](https://docs.luxonis.com/projects/api/en/latest/tutorials/spatial_coordinates/)
- **ROS REP 103**: Standard coordinate frames for mobile platforms
- **OAK-D Lite Specs**: Baseline 7.5cm, FOV 81° (H) x 55° (V)

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-01  
**Status:** Active
