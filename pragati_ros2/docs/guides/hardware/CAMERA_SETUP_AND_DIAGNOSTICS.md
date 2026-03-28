# OAK-D Lite Camera Setup and Diagnostics

**Last Updated:** 2025-11-04  
**Camera:** Luxonis OAK-D Lite  
**Status:** Production Ready (as of 2025-11-01)

---

## Overview

This guide covers the Luxonis OAK-D Lite camera used in the Pragati cotton detection system, including coordinate systems, diagnostics, pipeline architecture, and troubleshooting.

---

## Table of Contents

1. [Hardware Specifications](#hardware-specifications)
2. [Coordinate System](#coordinate-system)
3. [Camera Diagnostics](#camera-diagnostics)
4. [Pipeline Architecture](#pipeline-architecture)
5. [Configuration](#configuration)
6. [Troubleshooting](#troubleshooting)

---

## Hardware Specifications

### OAK-D Lite Technical Specs

| Specification | Value | Notes |
|--------------|-------|-------|
| **RGB Camera** | IMX214 4MP (4208×3120) | Fixed focus |
| **Stereo Cameras** | 2× OV7251 (640×480) | Mono, 400p mode |
| **Baseline** | 7.5cm | Stereo separation |
| **FOV** | 81° (H) × 55° (V) | Horizontal × Vertical |
| **Interface** | USB 2.0/3.0 | USB-C connector |
| **Sensors** | Temperature, accelerometer (basic) | No IMU on Lite model |
| **Focus** | Fixed | No autofocus mechanism |
| **Native Resolution** | 1920×1080 @ 60 FPS | RGB camera |
| **NN Input** | 416×416 (configurable) | Resized from native |

### Device Information

**Production Device:**
- Device ID: `18443010513F671200`
- Model: OAK-D Lite
- Sensors: RGB (4MP) + 2× Mono (400p) + Temperature

**Limitations vs OAK-D Pro:**
- ❌ No IMU (inertial measurement unit)
- ❌ No autofocus
- ✅ Lower cost
- ✅ Lower power consumption
- ✅ Sufficient for cotton detection

---

## Coordinate System

### Frame Convention

The OAK-D Lite uses a **right-handed coordinate system**:

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
| **X** | Right (+) / Left (-) | -300mm to +300mm | Horizontal displacement |
| **Y** | Down (+) / Up (-) | -300mm to +300mm | Vertical displacement |
| **Z** | Forward (+) / Backward (-) | 200mm to 2000mm | Depth from camera |

### Coordinate Origin

The origin `(0, 0, Z)` is located at:
- **Center of the camera's field of view** (horizontal center)
- **Camera optical axis** (vertical center)
- **At the camera's image sensor plane** (Z=0)

### Example Interpretations

**Example 1: Detection at (X=-90, Y=145, Z=657)**
- X = -90mm: Object is **90mm to the LEFT** of camera center
- Y = 145mm: Object is **145mm BELOW** camera center
- Z = 657mm: Object is **657mm FORWARD** from camera (depth)

**Example 2: Detection at (X=+150, Y=0, Z=800)**
- X = +150mm: Object **150mm RIGHT** of center
- Y = 0mm: **Centered vertically**
- Z = 800mm: **800mm forward**

### ROS2 Frame IDs

**Detection messages use:**
- Frame ID: `oak_rgb_camera_optical_frame`
- Message Type: `vision_msgs/msg/Detection3DArray`
- Coordinate Units: Meters (m) in messages, millimeters (mm) in logs

### Transform to Robot Frame

**Option 1: Static Transform**
```xml
<node pkg="tf2_ros" exec="static_transform_publisher" 
      args="0 0 0.5 0 0 0 base_link camera_link"/>
```

**Option 2: Coordinate Mapping**
```python
# Camera frame to robot frame
robot_x = camera_z   # Forward in camera = forward in robot
robot_y = -camera_x  # Left in camera = left in robot  
robot_z = -camera_y  # Down in camera = up in robot
```

### Common Misconceptions

❌ **"Negative X is wrong"**  
Incorrect. Negative X is expected for objects to the left of center.

❌ **"Coordinates should always be positive"**  
Incorrect. Only Z (depth) is typically positive. X and Y can be negative.

✅ **Correct Understanding**  
The coordinate system uses **signed values** to indicate direction relative to the camera's optical center.

---

## Camera Diagnostics

### Launch-Time Information Display

When the DepthAI camera initializes, the system displays:

**Camera Specifications:**
```
[INFO] [cotton_detection_node]: 📋 Camera Specifications:
[INFO] [cotton_detection_node]:    RGB Camera: 4MP (1920x1080 native)
[INFO] [cotton_detection_node]:    Stereo Cameras: 400p mono (for depth)
[INFO] [cotton_detection_node]:    NN Input: 416x416 (resized for YOLO)
[INFO] [cotton_detection_node]:    Depth: Enabled/Disabled
```

**Available Sensors:**
```
[INFO] [cotton_detection_node]: 📡 Available Sensors:
[INFO] [cotton_detection_node]:    ✅ RGB Camera
[INFO] [cotton_detection_node]:    ✅ Stereo Cameras (Left + Right)
[INFO] [cotton_detection_node]:    ✅ Temperature Sensor (on-chip)
[INFO] [cotton_detection_node]:    ✅ USB Speed Detection
[INFO] [cotton_detection_node]:    ❌ IMU (Not available on OAK-D Lite)
```

### Pre-Capture Status Monitoring

Before each detection request:

```
[INFO] [cotton_detection_node]: 📸 Pre-Capture Camera Status:
[INFO] [cotton_detection_node]:    🌡️  Temperature: 42.3°C
[INFO] [cotton_detection_node]:    📊 FPS: 29.8
[INFO] [cotton_detection_node]:    🖼️  Frames Processed: 1247
[INFO] [cotton_detection_node]:    🎯 Total Detections: 38
[INFO] [cotton_detection_node]:    ⏱️  Avg Latency: 45 ms
[INFO] [cotton_detection_node]:    ⏰ Uptime: 42.3 s
```

### Temperature Monitoring

**Hardware Support:**
- OAK-D Lite includes on-chip temperature sensor
- Accessed via `device->getChipTemperature()` DepthAI API
- Returns average chip temperature in Celsius

**Implementation:**
```cpp
// In depthai_manager.cpp
try {
    if (pImpl_->device_) {
        auto chipTemp = pImpl_->device_->getChipTemperature();
        stats.temperature_celsius = chipTemp.average;
    }
} catch (const std::exception& e) {
    stats.temperature_celsius = 0.0;  // Graceful fallback
}
```

**Temperature Thresholds:**

| Zone | Range | Status | Action |
|------|-------|--------|--------|
| Normal | 40-75°C | ✅ Safe | None required |
| Warning | 75-80°C | ⚠️ Degraded | Monitor, consider optimization |
| Throttling | 80-85°C | 🔴 Active reduction | Immediate action required |
| Critical | 85-95°C | 🔴🔴 Risk | Stop operation |
| Shutdown | >95°C | 🚨 Protection | Hardware safety engaged |

**Current Production Status (Nov 2025):**
- ✅ Temperature: **65.2°C peak** (depth disabled)
- ✅ Stable operation < 70°C
- ✅ No thermal throttling
- ✅ 100% detection reliability

**See:** [docs/guides/PERFORMANCE_OPTIMIZATION.md#thermal-management](../PERFORMANCE_OPTIMIZATION.md#thermal-management) for thermal optimization details.

### Testing Camera Information

```bash
# Launch with DepthAI enabled
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Check logs for camera specifications at startup
# Look for "📋 Camera Specifications:" section
```

### Monitoring Temperature During Operation

```bash
# Terminal 1: Launch detection node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Terminal 2: Trigger detection (shows pre-capture status)
ros2 service call /cotton_detection/detect \
  cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Watch logs for "📸 Pre-Capture Camera Status:" with temperature
```

### Accessing Temperature Programmatically

```cpp
// In your C++ code
#include "cotton_detection_ros2/depthai_manager.hpp"

auto stats = depthai_manager->getStats();
if (stats.temperature_celsius > 0.0) {
    RCLCPP_INFO(logger, "Camera temp: %.1f°C", stats.temperature_celsius);
}
```

---

## Pipeline Architecture

### Production Pipeline (ROS2 - Depth Disabled)

**Current configuration (Nov 2025):**

```
Sensor Layer @ 15 FPS:
┌──────────────────────────────────────────┐
│  IMX214 (4208x3120) → ISP → 1920x1080   │ ← Active
│  OV7251 Left/Right → DISABLED           │ ← Powered down
└──────────────────────────────────────────┘
         ↓
    ColorCam @ 15 FPS
         ↓
    ImageManip (resize 416x416)
         ↓
    YoloSpatialNN (no depth input)
         ↓
    XLinkOut
         ↓
    ROS2 Service: /cotton_detection/detect
```

**Benefits:**
- ✅ Thermal stability (65.2°C peak vs 96.6°C with depth)
- ✅ Lower power consumption
- ✅ Simpler pipeline
- ✅ Faster processing (no stereo computation)
- ❌ No 3D spatial coordinates (2D detections only)

### Alternative: Depth Enabled (Not Recommended)

**With depth enabled:**

```
Sensor Layer @ 15 FPS:
┌──────────────────────────────────────────┐
│  IMX214 (4208x3120) → ISP → 1920x1080   │
│  OV7251 Left → 640x400                  │  
│  OV7251 Right → 640x400                 │
└──────────────────────────────────────────┘
         ↓                ↓           ↓
    ColorCam        MonoLeft    MonoRight
         ↓                ↓           ↓
         ↓                └─StereoDepth─┘
         ↓                      ↓
         ↓                      ↓ depth map
    ImageManip ───────────────→ │
    (resize 416x416)            ↓
         ↓                      ↓
    YoloSpatialNN ←─────────────┘
         ↓
    XLinkOut
```

**Drawbacks:**
- ❌ Thermal issues (96.6°C peak, throttling)
- ❌ Higher power consumption
- ❌ More complex pipeline
- ✅ 3D spatial coordinates available

**Only enable if:**
- 3D coordinates absolutely required
- External cooling solution implemented
- Operating in cooler environment
- Willing to accept reduced duty cycle

### Pipeline Configuration

**File:** `src/cotton_detection_ros2/config/cotton_detection_cpp.yaml`

```yaml
depthai:
  # Resolution and FPS
  camera_width: 416      # NN input (not native resolution)
  camera_height: 416
  camera_fps: 15         # Lower = less heat
  
  # Depth configuration
  enable_depth: false    # Production: disabled for thermal stability
  
  # Stereo configuration (only if depth enabled)
  stereo_preset: "HIGH_ACCURACY"  # vs "HIGH_DENSITY" (40% more heat)
  left_right_check: true
  extended_disparity: true
  median_filter: "KERNEL_7x7"
```

### Thermal Management

**Key Insight:** Queue-based frame dropping does NOT reduce thermal load!
- Sensors, ISP, and StereoDepth run continuously at configured FPS
- Dropping frames happens AFTER all processing
- Only the NN compute is truly on-demand

**Thermal source breakdown:**

| Component | Contribution | Can Disable? | Production Status |
|-----------|--------------|--------------|-------------------|
| **StereoDepth** | **35%** | ✅ YES | ✅ **Disabled** |
| ISP @ 1080p | 25% | ⚠️ Could optimize | Active |
| Color Sensor | 15% | ⚠️ Via still-capture | Active |
| Mono Sensors (2x) | 10% | ✅ Yes | ✅ Auto-disabled |
| YOLO NN | 10% | ✅ On-demand | On-demand only |
| USB/XLink | 5% | - | Active |

---

## Configuration

### Default Configuration (Production)

**File:** `src/cotton_detection_ros2/config/cotton_detection_cpp.yaml`

```yaml
# DepthAI Configuration
depthai:
  # Camera settings
  camera_width: 416
  camera_height: 416
  camera_fps: 15                    # Lower FPS = less heat
  
  # Depth settings (DISABLED for thermal stability)
  enable_depth: false               # ✅ Production setting
  depth_align: "RGB"
  
  # Stereo configuration (if depth enabled)
  stereo_preset: "HIGH_ACCURACY"    # NOT "HIGH_DENSITY" (causes overheating)
  confidence_threshold: 255
  left_right_check: true
  subpixel: false
  extended_disparity: true
  median_filter: "KERNEL_7x7"
  
  # Performance settings
  flush_before_read: false          # Smart drain vs old flush+sleep
  max_queue_drain: 10               # Frame freshness control
  warmup_seconds: 3                 # Pipeline initialization time
  
  # Image saving (disabled for performance)
  save_input_image: false           # Saves 10-50ms per frame
  save_output_image: false

# YOLO Configuration  
yolo:
  model_path: "src/cotton_detection_ros2/models/yolov8v2.blob"
  confidence_threshold: 0.5
  iou_threshold: 0.4
  
# Detection Configuration
detection:
  offline_mode: false               # Use camera (not file-based)
  detection_mode: "depthai_direct"  # On-device YOLO
```

### Camera Resolution Options

**Native camera resolution:**
- RGB Camera: 1920×1080 (1080p) at up to 60 FPS
- Stereo Cameras: 640×400 (400p) at up to 60 FPS

**Neural Network input resolution:**
- Default: 416×416 pixels (configurable)
- Resized from native 1920×1080 for YOLO processing
- Trade-off: Higher resolution = better accuracy but slower processing

**To change NN resolution:**
```yaml
depthai:
  camera_width: 640      # Increase for better accuracy
  camera_height: 640     # Decrease for faster processing
```

---

## Troubleshooting

### Camera Not Detected

**Symptoms:**
- Node fails to start
- "Device not found" error

**Solutions:**
```bash
# Check USB connection
lsusb | grep -i luxonis

# Check dmesg for USB errors
dmesg | tail -20

# Try different USB port (preferably USB 3.0)

# Reset USB device
sudo usb_modeswitch -v 0x03e7 -p 0x2485 --reset-usb

# Check permissions
sudo usermod -aG plugdev $USER
# Logout and login again
```

### High Temperature

**Symptoms:**
- Temperature > 75°C
- Thermal throttling warnings
- Detection timeouts

**Solutions:**
1. **Check depth configuration** (most common)
   ```bash
   # Verify depth is disabled
   grep "enable_depth" src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
   # Should show: enable_depth: false
   ```

2. **Lower FPS if needed**
   ```yaml
   depthai:
     camera_fps: 10  # Down from 15
   ```

3. **Check stereo preset** (if depth enabled)
   ```yaml
   depthai:
     stereo_preset: "HIGH_ACCURACY"  # NOT "HIGH_DENSITY"
   ```

4. **Improve airflow**
   - Ensure camera has ventilation
   - Add heatsink if needed
   - Consider active cooling for extended operation

**See:** [PERFORMANCE_OPTIMIZATION.md#thermal-management](../PERFORMANCE_OPTIMIZATION.md#thermal-management) for detailed thermal solutions.

### Poor Detection Accuracy

**Symptoms:**
- Low confidence scores
- Missed detections
- False positives

**Solutions:**
1. **Check lighting conditions**
   - Ensure adequate lighting
   - Avoid direct sunlight
   - Use diffused LED lighting

2. **Adjust confidence threshold**
   ```yaml
   yolo:
     confidence_threshold: 0.4  # Lower if missing detections
   ```

3. **Verify camera focus**
   - OAK-D Lite has fixed focus
   - Optimal distance: 20cm to 2m
   - Object must be in focus range

4. **Check NN input resolution**
   ```yaml
   depthai:
     camera_width: 640   # Increase from 416
     camera_height: 640
   ```

### Low FPS / High Latency

**Symptoms:**
- FPS < 10
- Detection latency > 100ms
- Sluggish response

**Solutions:**
1. **Check temperature** (thermal throttling)
   ```bash
   ros2 topic echo /cotton_detection/diagnostics | grep -i temperature
   ```

2. **Verify USB speed**
   ```bash
   lsusb -t | grep -A 5 Luxonis
   # Should show: 5000M (USB 3.0) or 480M (USB 2.0)
   ```

3. **Lower resolution if needed**
   ```yaml
   depthai:
     camera_width: 416   # Lower = faster
     camera_height: 416
   ```

4. **Check CPU usage**
   ```bash
   top -p $(pgrep -f cotton_detection_node)
   ```

### Frame Queue Issues

**Symptoms:**
- Stale frames
- Detection lag
- Queue overflow warnings

**Solutions:**
1. **Enable smart queue draining** (should be default)
   ```yaml
   depthai:
     flush_before_read: false  # Use smart drain
     max_queue_drain: 10       # Drain up to 10 frames
   ```

2. **Reduce queue size if needed**
   ```cpp
   // In depthai_manager.cpp
   queue->setMaxSize(2);  // Smaller buffer = fresher frames
   ```

### Coordinate Frame Issues

**Symptoms:**
- Incorrect spatial coordinates
- Unexpected negative values
- Objects detected in wrong direction

**Solutions:**
1. **Verify camera mounting**
   - Camera must be level
   - Camera must face forward
   - No rotation or tilt

2. **Check transform tree**
   ```bash
   ros2 run tf2_tools view_frames
   # Check for: oak_rgb_camera_optical_frame
   ```

3. **Test with known positions**
   - Place object at known location
   - Verify coordinates match expectations
   - Remember: negative X = left, negative Y = up

4. **Visualize in RViz**
   ```bash
   rviz2
   # Add: TF display + Detection markers
   ```

### References

- **DepthAI Documentation:** https://docs.luxonis.com
- **Spatial Coordinates:** https://docs.luxonis.com/projects/api/en/latest/tutorials/spatial_coordinates/
- **ROS REP 103:** Standard coordinate frames for mobile platforms
- **OAK-D Lite Specs:** https://shop.luxonis.com/products/oak-d-lite-1

---

**Last Updated:** 2025-11-04  
**Status:** Production Ready  
**Camera:** Luxonis OAK-D Lite  
**System:** Pragati Cotton Detection ROS2
