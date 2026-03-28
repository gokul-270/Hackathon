# Camera Diagnostics Enhancements

> **📍 MOVED:** This content has been consolidated into the Camera Setup and Diagnostics Guide.
> 
> **New Location:** [guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md](guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md#camera-diagnostics)
> 
> This file is preserved for historical reference. For current documentation, please refer to the consolidated guide above.

---

## Overview

Enhanced the cotton detection system to display comprehensive camera information at launch and monitor camera temperature before each detection trigger. This provides better visibility into camera health and operational status.

## Changes Made

### 1. Launch-Time Camera Information Display

When the DepthAI camera initializes, the system now displays:

**Camera Specifications:**
- RGB Camera: 4MP (1920x1080 native resolution)
- Stereo Cameras: 400p mono cameras for depth computation
- Neural Network Input: Configurable (default 416x416, resized from native resolution)
- Depth Processing: Status (Enabled/Disabled)

**Available Sensors:**
- ✅ RGB Camera (4MP color sensor)
- ✅ Stereo Cameras (Left + Right mono for depth)
- ✅ Temperature Sensor (on-chip thermal monitoring)
- ✅ USB Speed Detection (USB 2.0 vs 3.0)
- ❌ IMU (Not available on OAK-D Lite - only on OAK-D Pro)

**Example Output:**
```
[INFO] [cotton_detection_node]: 📋 Camera Specifications:
[INFO] [cotton_detection_node]:    RGB Camera: 4MP (1920x1080 native)
[INFO] [cotton_detection_node]:    Stereo Cameras: 400p mono (for depth)
[INFO] [cotton_detection_node]:    NN Input: 416x416 (resized for YOLO)
[INFO] [cotton_detection_node]:    Depth: Enabled

[INFO] [cotton_detection_node]: 📡 Available Sensors:
[INFO] [cotton_detection_node]:    ✅ RGB Camera
[INFO] [cotton_detection_node]:    ✅ Stereo Cameras (Left + Right)
[INFO] [cotton_detection_node]:    ✅ Temperature Sensor (on-chip)
[INFO] [cotton_detection_node]:    ✅ USB Speed Detection
[INFO] [cotton_detection_node]:    ❌ IMU (Not available on OAK-D Lite)
```

### 2. Pre-Capture Camera Status Monitoring

Before each detection request, the system now displays:

**Camera Status Metrics:**
- 🌡️ Temperature: Current chip temperature in Celsius (when hardware available)
- 📊 FPS: Actual frames per second being processed
- 🖼️ Frames Processed: Total frames since initialization
- 🎯 Total Detections: Cumulative detection count
- ⏱️ Avg Latency: Average detection latency in milliseconds
- ⏰ Uptime: Time since camera initialization in seconds

**Example Output:**
```
[INFO] [cotton_detection_node]: 
[INFO] [cotton_detection_node]: 📸 Pre-Capture Camera Status:
[INFO] [cotton_detection_node]:    🌡️  Temperature: 42.3°C
[INFO] [cotton_detection_node]:    📊 FPS: 29.8
[INFO] [cotton_detection_node]:    🖼️  Frames Processed: 1247
[INFO] [cotton_detection_node]:    🎯 Total Detections: 38
[INFO] [cotton_detection_node]:    ⏱️  Avg Latency: 45 ms
[INFO] [cotton_detection_node]:    ⏰ Uptime: 42.3 s
```

### 3. Temperature Sensor Implementation

**Hardware Support:**
- OAK-D Lite includes on-chip temperature sensor
- Accessed via `device->getChipTemperature()` DepthAI API
- Returns average chip temperature in Celsius

**Implementation Details:**
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

**Fallback Behavior:**
- If hardware is not available: displays "Not available (requires hardware)"
- If temperature reading fails: returns 0.0°C (silent failure)
- Temperature is diagnostic information, not critical for operation

## Benefits

### 1. **Operational Visibility**
- Immediate feedback on camera capabilities at launch
- Clear indication of what sensors are available
- No confusion about OAK-D Lite vs OAK-D Pro features

### 2. **Thermal Monitoring**
- Early warning if camera is overheating
- Track thermal performance over extended operation
- Useful for outdoor deployments in varying temperatures

### 3. **Performance Diagnostics**
- Real-time FPS monitoring
- Latency tracking for performance optimization
- Frame count for verifying continuous operation

### 4. **Production Readiness**
- Better logging for troubleshooting
- Health monitoring for preventive maintenance
- Audit trail for system diagnostics

## Default Resolution

**Native Camera Resolution:**
- RGB Camera: 1920x1080 (1080p) at up to 60 FPS
- Stereo Cameras: 640x400 (400p) at up to 60 FPS

**Neural Network Input Resolution:**
- Default: 416x416 pixels (configurable)
- Resized from native 1920x1080 for YOLO processing
- Trade-off: Higher resolution = better accuracy but slower processing

**Configuration:**
```yaml
depthai:
  camera_width: 416    # NN input width (not native camera resolution)
  camera_height: 416   # NN input height
  camera_fps: 30       # Frame rate
```

## Usage

### Testing Camera Information Display

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

# Terminal 2: Trigger detection (this will show pre-capture status)
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

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

## Temperature Thresholds

**Typical Operating Range:**
- Normal: 35-55°C
- Warning: 55-70°C (reduced performance possible)
- Critical: >70°C (risk of thermal throttling)

**Recommendations:**
- Monitor temperature in prolonged operations
- Ensure adequate ventilation for camera
- Consider active cooling for outdoor summer deployment

## Files Modified

1. **src/cotton_detection_ros2/src/cotton_detection_node.cpp**
   - Added camera specifications display at launch
   - Added pre-capture status monitoring
   - Enhanced diagnostic output

2. **src/cotton_detection_ros2/src/depthai_manager.cpp**
   - Enabled actual temperature reading from hardware
   - Implemented graceful fallback for unavailable sensors

## Testing Checklist

- [x] Camera info displays at launch
- [x] Temperature reading implementation (requires hardware)
- [x] Pre-capture status before each detection
- [x] Graceful handling when hardware unavailable
- [x] Documentation updated

## Future Enhancements

1. **Temperature Alerts:**
   - Add ROS2 diagnostic messages for temperature warnings
   - Publish temperature on dedicated topic
   - Automatic throttling if temperature exceeds threshold

2. **Extended Diagnostics:**
   - USB power consumption monitoring
   - Pipeline queue depths
   - Memory usage tracking

3. **Historical Tracking:**
   - Log temperature trends to CSV
   - Generate thermal performance reports
   - Correlate temperature with detection accuracy

## Related Documentation

- [CAMERA_INTEGRATION_GUIDE.md](guides/CAMERA_INTEGRATION_GUIDE.md) - Camera setup
- [depthai_manager.hpp](../src/cotton_detection_ros2/include/cotton_detection_ros2/depthai_manager.hpp) - API reference
- OAK-D Lite Datasheet: https://docs.luxonis.com/projects/hardware/en/latest/pages/DM9095/

---

**Status**: ✅ Implemented and Ready for Testing  
**Requires**: OAK-D Lite hardware for full functionality  
**Priority**: Medium (Diagnostic/Quality of Life improvement)
