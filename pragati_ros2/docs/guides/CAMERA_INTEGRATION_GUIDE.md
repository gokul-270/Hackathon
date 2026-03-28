# Camera Integration Guide

> **⚠️ DEPRECATED:** This generic camera guide has been replaced with OAK-D Lite specific documentation.
> 
> **New Location:** [hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md](hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md)
> 
> This file is preserved for historical reference but is NO LONGER MAINTAINED. The Pragati system uses **Luxonis OAK-D Lite**, not generic USB cameras or RealSense.

---

**Version**: 2.0 (OAK-D Lite Migration Edition) - **DEPRECATED**  
**Last Updated**: December 2025  
**Target**: Cotton Detection Vision System with Luxonis OAK-D Lite

---

> ⚠️ **CRITICAL UPDATE: OAK-D LITE CAMERA MIGRATION IN PROGRESS**
> 
> **THIS GUIDE IS BEING REPLACED WITH OAK-D LITE SPECIFIC DOCUMENTATION**
> 
> **Current Migration Status (Phase 1 - Active):**
> - **Original ROS1**: Luxonis OAK-D Lite camera via DepthAI Python SDK (38 Python scripts)
> - **ROS2 (Incorrect)**: Generic USB/RealSense camera references (THIS GUIDE - being deprecated)
> - **ROS2 (Target)**: Luxonis OAK-D Lite via DepthAI SDK (restoring original functionality)
> 
> **Action Required:**
> - Phase 1 is restoring OAK-D Lite functionality via Python wrapper node
> - The camera recommendations below (USB webcam, RealSense, etc.) **DO NOT APPLY** to the actual Pragati system
> - The actual camera is **Luxonis OAK-D Lite** with on-device spatial YOLO detection
> - Use DepthAI SDK (not usb_cam, v4l2_camera, or librealsense2)
> 
> **See Correct Documentation:**
> - `/home/uday/Downloads/pragati_ros2/docs/OAK_D_LITE_MIGRATION_ANALYSIS.md`
> - `/home/uday/Downloads/pragati_ros2/docs/OAK_D_LITE_HYBRID_MIGRATION_PLAN.md`
> - ROS1 Python scripts: `/home/uday/Downloads/pragati/src_archive/cotton_detect/` (38 files)

## Overview

This guide covers camera integration for the Pragati ROS2 cotton picking robot vision system, including hardware setup, ROS2 camera drivers, and integration with the cotton detection node.

### Current Status

- 🟡 **Camera Hardware**: OAK-D Lite migration in progress (Phase 1: Python wrapper)
- ✅ **Cotton Detection**: 100% complete with topic-based integration
- ⚠️ **This Guide**: DEPRECATED - being replaced with OAK-D Lite specific guide

---

## Hardware Requirements

### Supported Cameras

> ⚠️ **DEPRECATED TABLE - NOT APPLICABLE TO PRAGATI SYSTEM**
> 
> The actual camera for the Pragati system is **Luxonis OAK-D Lite**.
> The table below is generic guidance and does not reflect the actual hardware.

| Camera Type | Resolution | FPS | Interface | Cost | Status for Pragati |
|-------------|-----------|-----|-----------|------|--------------------|
| **Luxonis OAK-D Lite** | 1920x1080 (RGB) + depth | 30-60 | USB 2.0 | $150 | ✅ **ACTUAL CAMERA** |
| **USB Webcam** | 640x480 - 1920x1080 | 30 | USB 2.0/3.0 | $20-50 | ❌ Not used |
| **Raspberry Pi Camera v2** | 3280x2464 (8MP) | 30 | CSI | $25 | ❌ Not used |
| **Intel RealSense D435** | 1920x1080 (RGB) | 30 | USB 3.0 | $180 | ❌ Incorrectly referenced in ROS2 |
| **USB Industrial Camera** | 1920x1080+ | 60+ | USB 3.0 | $100+ | ❌ Not used |

### Required Components

1. **Camera Hardware**
   - Resolution: Minimum 640x480, recommended 1920x1080
   - Frame rate: Minimum 15 FPS, recommended 30 FPS
   - Lens: Appropriate field of view for cotton detection
   - Mounting: Stable mount with adjustable angle

2. **Lighting** (Important for detection accuracy)
   - LED ring light or panel
   - Diffused white light recommended
   - Adjustable brightness
   - Consider: Wavelength for cotton contrast

3. **Cables and Mounts**
   - USB cable (appropriate length and spec)
   - CSI ribbon cable (for Raspberry Pi camera)
   - Camera mount/bracket
   - Cable management clips

---

## Camera Selection Guide

### For Cotton Detection Requirements

**Critical Factors**:
1. **Resolution**: 1920x1080 recommended for accurate detection
2. **Frame Rate**: 30 FPS sufficient for picking operations
3. **Color Accuracy**: Important for cotton vs background contrast
4. **Lighting Conditions**: Indoor vs outdoor determines camera specs
5. **Field of View**: Must cover picking area

**Recommended Configuration**:
- **Indoor/Controlled**: Logitech C920 or similar USB webcam
- **Outdoor/Variable Light**: Industrial camera with auto-exposure
- **Raspberry Pi**: Official Camera Module v2 or HQ Camera

---

## Software Installation

### Step 1: Install Camera Drivers

#### For USB Cameras (UVC - USB Video Class)

```bash
# Install v4l-utils for USB cameras
sudo apt-get update
sudo apt-get install -y v4l-utils

# List connected cameras
v4l2-ctl --list-devices

# Check camera capabilities
v4l2-ctl --device=/dev/video0 --all

# Test camera with simple capture
ffmpeg -f v4l2 -i /dev/video0 -frames 1 test.jpg
```

#### For Raspberry Pi Camera

```bash
# Enable camera interface
sudo raspi-config
# Navigate to: Interface Options -> Camera -> Enable

# Install camera utilities
sudo apt-get install -y libraspberrypi-bin

# Test camera
raspistill -o test.jpg -t 1000

# For video
raspivid -o test.h264 -t 10000
```

### Step 2: Install ROS2 Camera Packages

```bash
cd /home/uday/Downloads/pragati_ros2

# Install usb_cam (for USB cameras)
sudo apt-get install -y ros-${ROS_DISTRO}-usb-cam

# Install image_transport
sudo apt-get install -y ros-${ROS_DISTRO}-image-transport-plugins

# Install camera_calibration tools
sudo apt-get install -y ros-${ROS_DISTRO}-camera-calibration

# For Raspberry Pi camera
sudo apt-get install -y ros-${ROS_DISTRO}-v4l2-camera

# Verify installation
ros2 pkg list | grep -E "usb_cam|v4l2_camera|camera_calibration"
```

### Step 3: Configure Camera Parameters

**File**: `src/cotton_detection_ros2/config/camera_config.yaml`

```yaml
camera:
  # Camera device
  video_device: "/dev/video0"
  
  # Image format
  image_width: 1920
  image_height: 1080
  pixel_format: "yuyv"  # or "mjpeg" for compressed
  framerate: 30
  
  # Camera parameters
  camera_name: "cotton_camera"
  camera_info_url: "file:///home/uday/.ros/camera_info/cotton_camera.yaml"
  
  # Auto-exposure and white balance
  auto_exposure: true
  auto_white_balance: true
  brightness: 128  # 0-255
  contrast: 32     # 0-255
  saturation: 32   # 0-255
  
  # Topic names
  image_topic: "/camera/image_raw"
  camera_info_topic: "/camera/camera_info"
```

---

## ROS2 Camera Node Setup

### Option 1: USB Camera with usb_cam

**Launch File**: `src/cotton_detection_ros2/launch/camera_usb.launch.py`

```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='usb_cam',
            executable='usb_cam_node_exe',
            name='usb_cam',
            namespace='camera',
            parameters=[{
                'video_device': '/dev/video0',
                'image_width': 1920,
                'image_height': 1080,
                'pixel_format': 'yuyv',
                'camera_frame_id': 'camera_link',
                'io_method': 'mmap',
                'framerate': 30.0,
            }],
            remappings=[
                ('/camera/image_raw', '/camera/image_raw'),
                ('/camera/camera_info', '/camera/camera_info'),
            ]
        )
    ])
```

### Option 2: Raspberry Pi Camera

**Launch File**: `src/cotton_detection_ros2/launch/camera_picam.launch.py`

```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='v4l2_camera',
            executable='v4l2_camera_node',
            name='v4l2_camera',
            namespace='camera',
            parameters=[{
                'video_device': '/dev/video0',
                'image_size': [1920, 1080],
                'camera_frame_id': 'camera_link',
                'output_encoding': 'yuv422',
                'time_per_frame': [1, 30],  # 30 FPS
            }]
        )
    ])
```

---

## Cotton Detection Integration

### Current Architecture

```
┌──────────────────────────────────────────────────┐
│            Cotton Detection System               │
├──────────────────────────────────────────────────┤
│                                                  │
│  Camera Node                                     │
│     ↓ /camera/image_raw                          │
│  Cotton Detection Node                           │
│     ↓ /cotton_detection/results                  │
│  YanthraMoveSystem (buffer)                      │
│     ↓ internal API                               │
│  MotionController                                │
│                                                  │
└──────────────────────────────────────────────────┘
```

### Configuration for Camera Mode

**File**: `src/cotton_detection_ros2/config/cotton_detection_params.yaml`

```yaml
cotton_detection:
  ros__parameters:
    # Mode selection
    mode: "camera"  # Options: "camera" or "offline"
    
    # Camera mode parameters
    camera_topic: "/camera/image_raw"
    subscribe_compressed: false  # Set true for /image_raw/compressed
    
    # Offline mode parameters (when mode: "offline")
    image_directory: "/home/uday/Downloads/pragati_ros2/data/images"
    image_file_pattern: "*.jpg"
    offline_rate_hz: 1.0
    
    # Detection parameters
    detection_confidence_threshold: 0.7
    max_detections_per_frame: 10
    
    # Publishing
    publish_annotated_image: true
    annotated_image_topic: "/cotton_detection/annotated_image"
```

### Switching Between Modes

```bash
# Launch with camera mode
ros2 launch cotton_detection_ros2 cotton_detection.launch.py \
    mode:=camera \
    camera_topic:=/camera/image_raw

# Launch with offline mode (pre-recorded images)
ros2 launch cotton_detection_ros2 cotton_detection.launch.py \
    mode:=offline \
    image_directory:=/path/to/images

# Launch with compressed images (saves bandwidth)
ros2 launch cotton_detection_ros2 cotton_detection.launch.py \
    mode:=camera \
    camera_topic:=/camera/image_raw/compressed \
    subscribe_compressed:=true
```

---

## Camera Calibration

### Why Calibrate?

Camera calibration corrects for:
- Lens distortion (barrel/pincushion)
- Perspective transformation
- Accurate 3D position estimation

### Calibration Procedure

```bash
# Print calibration checkerboard
# Download from: https://calib.io/pages/camera-calibration-pattern-generator
# Settings: 8x6 checkerboard, 25mm square size

# Launch camera
ros2 launch cotton_detection_ros2 camera_usb.launch.py

# Terminal 2: Run calibration tool
ros2 run camera_calibration cameracalibrator \
    --size 8x6 \
    --square 0.025 \
    image:=/camera/image_raw \
    camera:=/camera

# Follow on-screen instructions:
# 1. Move checkerboard around in camera view
# 2. Different angles and distances
# 3. X, Y, Size, Skew bars should all turn green
# 4. Click "Calibrate"
# 5. Click "Save" to write calibration file

# Calibration saved to: ~/.ros/camera_info/cotton_camera.yaml
```

### Using Calibration

The camera_info is automatically published by the camera node when calibration file exists:

```bash
# Verify calibration is loaded
ros2 topic echo /camera/camera_info --once
```

---

## Testing and Validation

### Pre-Test Checklist

- [ ] Camera physically installed and focused
- [ ] Lighting adequate and consistent
- [ ] Camera driver installed
- [ ] ROS2 camera packages installed
- [ ] Camera parameters configured
- [ ] Calibration completed (optional but recommended)

### Test 1: Camera Device Detection

```bash
# List video devices
ls -l /dev/video*

# Check device capabilities
v4l2-ctl --device=/dev/video0 --all

# Test still image capture
ffmpeg -f v4l2 -i /dev/video0 -frames 1 /tmp/test.jpg && xdg-open /tmp/test.jpg
```

### Test 2: ROS2 Camera Node

```bash
# Terminal 1: Launch camera node
ros2 launch cotton_detection_ros2 camera_usb.launch.py

# Terminal 2: Check topics
ros2 topic list | grep camera

# Expected topics:
# /camera/camera_info
# /camera/image_raw
# /camera/image_raw/compressed (if enabled)

# Terminal 3: Check image publication rate
ros2 topic hz /camera/image_raw

# Expected: ~30 Hz (or configured framerate)
```

### Test 3: View Camera Feed

```bash
# Install rqt_image_view if not already installed
sudo apt-get install -y ros-${ROS_DISTRO}-rqt-image-view

# View camera feed
ros2 run rqt_image_view rqt_image_view /camera/image_raw

# Or use rviz2
rviz2
# Add -> By Topic -> /camera/image_raw -> Image
```

### Test 4: Cotton Detection with Camera

```bash
# Terminal 1: Launch camera
ros2 launch cotton_detection_ros2 camera_usb.launch.py

# Terminal 2: Launch cotton detection in camera mode
ros2 launch cotton_detection_ros2 cotton_detection.launch.py mode:=camera

# Terminal 3: Monitor detection results
ros2 topic echo /cotton_detection/results

# Terminal 4: View annotated image
ros2 run rqt_image_view rqt_image_view /cotton_detection/annotated_image
```

### Test 5: Full System Integration

```bash
# Launch complete system with camera
ros2 launch yanthra_move yanthra_move_with_camera.launch.py

# Monitor:
# - Camera feed publishing
# - Cotton detection results
# - YanthraMoveSystem receiving positions
# - Motion execution

# Check system logs
ros2 topic echo /yanthra_move/status
```

---

## Troubleshooting

### Camera Not Detected

**Symptom**: `/dev/video0` doesn't exist

**Solutions**:
```bash
# Check USB connection
lsusb | grep -i camera

# Check kernel messages
dmesg | tail -20

# For Raspberry Pi camera, verify enabled
vcgencmd get_camera
# Should show: supported=1 detected=1

# Reload v4l2 driver
sudo modprobe -r uvcvideo
sudo modprobe uvcvideo
```

### Permission Denied

**Symptom**: Cannot open `/dev/video0`

**Solution**:
```bash
# Add user to video group
sudo usermod -a -G video $USER

# Check permissions
ls -l /dev/video0
# Should show: crw-rw----+ 1 root video

# Reboot or logout/login for group change
```

### Low Frame Rate

**Symptom**: Camera running slower than expected

**Checks**:
1. **USB bandwidth**: USB 2.0 limited to ~35 MB/s
2. **Resolution too high**: Reduce to 1280x720 or 640x480
3. **CPU overload**: Check `top` or `htop`
4. **USB hub**: Connect directly to computer

**Solutions**:
```bash
# Use MJPEG compression instead of raw
v4l2-ctl --device=/dev/video0 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG

# Or in ROS2 parameters:
pixel_format: "mjpeg"  # Instead of "yuyv"

# Reduce resolution
image_width: 1280
image_height: 720
```

### Image Quality Issues

**Problem**: Blurry, dark, or washed-out images

**Solutions**:
```bash
# Check and adjust camera controls
v4l2-ctl --device=/dev/video0 --list-ctrls

# Set manual exposure
v4l2-ctl --device=/dev/video0 --set-ctrl=auto_exposure=1  # Manual
v4l2-ctl --device=/dev/video0 --set-ctrl=exposure_time_absolute=150

# Adjust brightness/contrast
v4l2-ctl --device=/dev/video0 --set-ctrl=brightness=128
v4l2-ctl --device=/dev/video0 --set-ctrl=contrast=32

# Disable auto-focus if causing issues
v4l2-ctl --device=/dev/video0 --set-ctrl=focus_auto=0
v4l2-ctl --device=/dev/video0 --set-ctrl=focus_absolute=50
```

### Detection Not Working

**Problem**: Camera running but no cotton detected

**Checks**:
1. **Lighting**: Ensure adequate, even lighting
2. **Focus**: Camera properly focused on picking area
3. **Confidence threshold**: May be too high
4. **Model trained**: Detection model appropriate for conditions

**Debug**:
```bash
# Check raw camera feed first
ros2 run rqt_image_view rqt_image_view /camera/image_raw

# Check annotated output
ros2 run rqt_image_view rqt_image_view /cotton_detection/annotated_image

# Lower confidence threshold temporarily
ros2 param set /cotton_detection detection_confidence_threshold 0.5

# Check detection logs
ros2 topic echo /cotton_detection/results
```

---

## Performance Optimization

### Bandwidth Optimization

```yaml
# Use compressed transport
camera:
  compressed:
    format: jpeg
    jpeg_quality: 80  # 0-100, lower = smaller files

  # Enable only in ROS2 parameters or remap
```

### CPU Optimization

```yaml
cotton_detection:
  ros__parameters:
    # Reduce processing rate if CPU limited
    processing_rate_hz: 10  # Process every 3rd frame at 30 FPS
    
    # Use GPU if available
    use_gpu: true
    gpu_device_id: 0
```

### Latency Reduction

```bash
# Set camera to low-latency mode
v4l2-ctl --device=/dev/video0 --set-ctrl=exposure_auto=1  # Manual exposure faster

# Use smaller images
# 640x480 processes ~4x faster than 1920x1080

# Adjust detection model
# Smaller model = faster inference, lower accuracy
```

---

## Lighting Recommendations

### Indoor/Controlled Environment

- **Type**: LED panel or ring light
- **Color Temperature**: 5000K-6500K (daylight)
- **Brightness**: 500-1000 lux at picking area
- **Diffusion**: Use diffuser to avoid hotspots

### Outdoor/Variable Light

- **Camera**: Use auto-exposure
- **Shading**: Provide consistent lighting/shading
- **Time of Day**: Consider peak sun hours

### Testing Lighting

```bash
# Capture test images under different lighting
for i in {1..10}; do
    ros2 service call /camera/save_image std_srvs/srv/Trigger
    sleep 5
done

# Review images for consistency
# Good: Even brightness, clear contrast between cotton and background
# Bad: Dark shadows, bright spots, unclear edges
```

---

## Quick Reference

### Launch Camera Node
```bash
ros2 launch cotton_detection_ros2 camera_usb.launch.py
```

### View Camera Feed
```bash
ros2 run rqt_image_view rqt_image_view /camera/image_raw
```

### Check Frame Rate
```bash
ros2 topic hz /camera/image_raw
```

### Test Detection with Camera
```bash
ros2 launch cotton_detection_ros2 cotton_detection.launch.py mode:=camera
```

### Adjust Camera Settings
```bash
v4l2-ctl --device=/dev/video0 --set-ctrl=brightness=128
```

---

## Related Documentation

- **Cotton Detection**: `src/cotton_detection_ros2/README.md`
- **Cotton Detection Status**: `docs/COTTON_DETECTION_STATUS_UPDATE.md`
- **Execution Plan**: `docs/EXECUTION_PLAN_2025-09-30.md`
- **ROS2 Camera Tutorial**: http://wiki.ros.org/usb_cam

---

## Revision History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-09-30 | 1.0 | Initial camera integration guide | AI Assistant |