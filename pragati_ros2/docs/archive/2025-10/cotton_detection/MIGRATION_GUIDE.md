# Cotton Detection ROS2 - Migration Guide

**Document Version:** 1.1  
**Last Updated:** 2025-10-13  
**Target Audience:** Teams completing the move from the Python wrapper to the C++ node

---

## Table of Contents

1. [Overview](#overview)
2. [Migration Timeline](#migration-timeline)
3. [Key Differences](#key-differences)
4. [Step-by-Step Migration](#step-by-step-migration)
5. [Parameter Mapping](#parameter-mapping)
6. [Launch File Changes](#launch-file-changes)
7. [Code Migration Examples](#code-migration-examples)
8. [Testing Strategy](#testing-strategy)
9. [Troubleshooting](#troubleshooting)
10. [Rollback Plan](#rollback-plan)

---

## Overview

This guide helps you complete the migration from the **legacy Python wrapper** to the **production C++ implementation** of the cotton detection system.

### Why Migrate?

**Benefits of the C++ Implementation (current reality):**
- ✅ **Production Default**: `cotton_detection_node` is the shipping configuration in October 2025.
- ✅ **Better Performance**: No subprocess/file I/O bottlenecks.
- ✅ **DepthAI Enablement**: Native pipeline available when built with `-DHAS_DEPTHAI=ON` (alpha).
- ✅ **Enhanced Features**: Parameter validation, diagnostics, simulation hooks.
- ✅ **Continuous Detection**: Supports hybrid and depthai_direct streaming modes.
- ✅ **Improved Reliability**: Graceful error handling and QoS-aware publishing.

**Deprecation Notice:**
> ⚠️ The Python wrapper (`cotton_detect_ros2_wrapper.py`) is legacy. Calibration export now ships with the C++ node; wrapper removal awaits hardware validation and legacy automation migration. Track progress in `docs/STATUS_REALITY_MATRIX.md`.

---

## Migration Timeline

| Phase | Status (Oct 2025) | Description | Notes |
|-------|------------------|-------------|-------|
| **Phase 1** | ✅ Completed | Python wrapper foundation (legacy) | Retained for legacy automation + optional fallback. |
| **Phase 2** | ✅ Completed | C++ node operational alongside wrapper | Default launch path in main robot bring-up. |
| **Phase 3** | 🔄 Ongoing | DepthAI runtime parity & lifecycle hardening | Remaining tasks tracked in backlog; wrapper retained until validation + automation updates finish. |
| **Phase 4** | 📋 Planned | Wrapper deprecation & doc sunset | Target after hardware validation confirms C++ path + legacy automation is migrated. |
| **Phase 5** | 📋 Planned | Wrapper removal | Pending Phase 3 close-out + sign-off. |

**Action Today:** Treat C++ node as required baseline; limit wrapper usage to legacy automation or contingency cases and document any dependencies.

---

## Key Differences

### Architecture Changes

#### Python Wrapper (Phase 1)
```
ROS2 Wrapper Node
    ↓ subprocess
    ├─→ CottonDetect.py
    │   ├─→ SIGUSR1/SIGUSR2 signals
    │   └─→ File I/O (cotton_details.txt)
    ↓
Parse file → Publish to topic
```

#### C++ Node (Phase 2+)
```
ROS2 C++ Node
    ├─→ Image Subscriber (/camera/image_raw)
    ├─→ Detection Pipeline (HSV/YOLO)
    ├─→ DepthAI Manager (optional)
    └─→ Direct topic publishing
```

### Communication Changes

| Aspect | Python Wrapper | C++ Node |
|--------|---------------|----------|
| **Detection Trigger** | Signal-based (SIGUSR1) | Image callback |
| **Result Output** | File I/O parsing | Direct in-memory |
| **Camera Integration** | Subprocess script | DepthAI C++ library |
| **Detection Mode** | Trigger-on-demand | Continuous stream |
| **Configuration** | Launch args | ROS2 parameters |

---

## Step-by-Step Migration

### Step 1: Verify Prerequisites

```bash
# Check C++ node builds successfully
cd ~/Downloads/pragati_ros2
colcon build --packages-select cotton_detection_ros2

# Verify dependencies
ros2 pkg list | grep cotton_detection_ros2
ros2 interface list | grep cotton_detection
```

### Step 2: Test in Simulation Mode

```bash
# Test C++ node without hardware
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true \
    use_depthai:=false

# Verify simulation output
ros2 topic echo /cotton_detection/results
```

### Step 3: Update Configuration Files

Create a new config file for the C++ node:

```yaml
# config/cotton_detection_cpp.yaml
cotton_detection_node:
  ros__parameters:
    # Simulation and Testing
    simulation_mode: false
    
    # Camera Configuration
    camera_topic: "/camera/image_raw"
    publish_debug_images: true
    
    # Detection Mode
    detection_mode: "hybrid_fallback"  # hsv_only, yolo_only, hybrid_*
    
    # HSV Color Detection
    cotton_detection:
      hsv_lower_bound: [0, 0, 180]
      hsv_upper_bound: [180, 40, 255]
      min_contour_area: 50.0
      max_contour_area: 5000.0
      morphology_kernel_size: 5
      gaussian_blur_size: 3
    
    # YOLO Detection (optional)
    yolo_enabled: true
    yolo_model_path: "/opt/models/cotton_yolov8.onnx"
    yolo_confidence_threshold: 0.5
    
    # DepthAI Configuration
    depthai:
      enable: true
      model_path: "/path/to/yolov8v2.blob"
      confidence_threshold: 0.5
    
    # Performance
    performance:
      max_processing_fps: 30.0
      enable_monitoring: true
```

### Step 4: Update Launch Files

Replace Python wrapper launch with C++ node:

**Old (Python wrapper):**
```python
from launch_ros.actions import Node

cotton_node = Node(
    package='cotton_detection_ros2',
    executable='cotton_detect_ros2_wrapper.py',
    parameters=[{'simulation_mode': simulation_mode}]
)
```

**New (C++ node):**
```python
cotton_node = Node(
    package='cotton_detection_ros2',
    executable='cotton_detection_node',
    parameters=[config_file]  # Use YAML config
)
```

### Step 5: Test with Hardware

```bash
# Test with OAK-D Lite camera
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=true

# Monitor detection results
ros2 topic hz /cotton_detection/results
ros2 topic echo /cotton_detection/results

# Check diagnostics
ros2 topic echo /diagnostics
```

### Step 6: Update Integration Points

Update any code that interfaces with cotton detection:

```cpp
// Before (Python wrapper)
auto subscriber = node->create_subscription<cotton_detection_ros2::msg::Detection3DArray>(
    "/cotton_detection/results", 10, callback);

// After (C++ node) - Same interface!
auto subscriber = node->create_subscription<cotton_detection_ros2::msg::DetectionResult>(
    "/cotton_detection/results", 10, callback);
```

### Step 7: Validate and Monitor

```bash
# Run integration tests
python3 scripts/test_wrapper_integration.py

# Performance benchmark
python3 scripts/performance_benchmark.py

# Check for parameter validation errors
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args --log-level debug
```

---

## Parameter Mapping

### Launch Arguments

| Python Wrapper Parameter | C++ Node Parameter | Notes |
|-------------------------|-------------------|-------|
| `simulation_mode` | `simulation_mode` | ✅ Same |
| `usb_mode` | `depthai.usb_mode` | Now in depthai namespace |
| `confidence_threshold` | `yolo_confidence_threshold` | More specific naming |
| `blob_path` | `depthai.model_path` | Now in depthai namespace |
| `output_dir` | *(removed)* | No longer needed (no file I/O) |
| `input_dir` | *(removed)* | No longer needed (no file I/O) |
| `publish_debug_image` | `publish_debug_images` | Plural form |

### Configuration Parameters

#### Python Wrapper (Launch Args)
```bash
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    simulation_mode:=true \
    confidence_threshold:=0.7 \
    usb_mode:=usb3
```

#### C++ Node (YAML Config)
```yaml
cotton_detection_node:
  ros__parameters:
    simulation_mode: true
    yolo_confidence_threshold: 0.7
    depthai:
      usb_mode: "usb3"
```

---

## Launch File Changes

### Before: Python Wrapper

```python
#!/usr/bin/env python3
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='cotton_detection_ros2',
            executable='cotton_detect_ros2_wrapper.py',
            name='cotton_detection',
            output='screen',
            parameters=[{
                'simulation_mode': False,
                'confidence_threshold': 0.5,
            }]
        )
    ])
```

### After: C++ Node

```python
#!/usr/bin/env python3
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    config_file = PathJoinSubstitution([
        FindPackageShare('cotton_detection_ros2'),
        'config',
        'cotton_detection_cpp.yaml'
    ])
    
    return LaunchDescription([
        DeclareLaunchArgument(
            'simulation_mode',
            default_value='false',
            description='Run in simulation mode'
        ),
        
        Node(
            package='cotton_detection_ros2',
            executable='cotton_detection_node',
            name='cotton_detection_node',
            output='screen',
            parameters=[
                config_file,
                {'simulation_mode': LaunchConfiguration('simulation_mode')}
            ]
        )
    ])
```

---

## Code Migration Examples

### Example 1: Service Call

**No changes needed!** The service interface remains the same.

```python
# Works with both Python wrapper and C++ node
from cotton_detection_ros2.srv import CottonDetection

client = node.create_client(CottonDetection, '/cotton_detection/detect')
request = CottonDetection.Request()
request.detect_command = 1
future = client.call_async(request)
```

### Example 2: Topic Subscription

**Interface changed**: `Detection3DArray` → `DetectionResult`

**Before:**
```python
from cotton_detection_ros2.msg import Detection3DArray

def callback(msg):
    for detection in msg.detections:
        print(f"Cotton at: {detection.position}")

subscription = node.create_subscription(
    Detection3DArray,
    '/cotton_detection/results',
    callback,
    10
)
```

**After:**
```python
from cotton_detection_ros2.msg import DetectionResult

def callback(msg):
    for detection in msg.detections:
        print(f"Cotton at: {detection.position}")
        print(f"Confidence: {detection.confidence}")  # New field!

subscription = node.create_subscription(
    DetectionResult,
    '/cotton_detection/results',
    callback,
    10
)
```

### Example 3: TF Frames

**Frame names changed** for consistency:

| Python Wrapper | C++ Node |
|---------------|----------|
| `oak_camera_link` | `camera_link` |
| `oak_rgb_camera_optical_frame` | `camera_optical_frame` |

Update your TF listener code accordingly:

```cpp
// Before
transform = tf_buffer->lookupTransform("base_link", "oak_camera_link", tf2::TimePointZero);

// After
transform = tf_buffer->lookupTransform("base_link", "camera_link", tf2::TimePointZero);
```

---

## Testing Strategy

### Phase 1: Parallel Testing

Run both implementations side-by-side:

```bash
# Terminal 1: Python wrapper
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# Terminal 2: C++ node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Terminal 3: Compare outputs
ros2 topic echo /cotton_detection/results
```

### Phase 2: A/B Testing

Alternate between implementations and measure:
- Detection accuracy
- Processing latency
- CPU/memory usage
- Frame rate

```bash
# Benchmark script
python3 scripts/performance_benchmark.py --compare-implementations
```

### Phase 3: Staged Rollout

1. **Week 1**: Deploy to development environment
2. **Week 2**: Deploy to test robot
3. **Week 3**: Monitor and collect metrics
4. **Week 4**: Deploy to production if metrics are good

---

## Troubleshooting

### Issue: "No detections in C++ node but Python wrapper works"

**Possible Causes:**
1. Camera topic mismatch
2. HSV threshold differences
3. Image encoding issues

**Solution:**
```bash
# Check camera topic
ros2 topic list | grep camera

# Verify image encoding
ros2 topic echo /camera/image_raw --field encoding

# Compare HSV parameters
ros2 param get /cotton_detection_node cotton_detection.hsv_lower_bound
```

### Issue: "Parameter validation failed"

**Cause:** Invalid configuration values

**Solution:**
```bash
# Check parameter validity
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args --log-level info

# Use test config to identify bad parameters
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    config_file:=/path/to/test_config.yaml
```

### Issue: "DepthAI initialization failed"

**Possible Causes:**
1. Camera not connected
2. USB mode mismatch
3. Model blob file missing

**Solution:**
```bash
# Test DepthAI connectivity
python3 -c "import depthai as dai; print(dai.Device.getAllAvailableDevices())"

# Check USB mode
lsusb | grep 03e7

# Verify model path
ls -lh /path/to/yolov8v2.blob
```

### Issue: "High CPU usage"

**Possible Causes:**
1. Processing FPS too high
2. Debug images enabled
3. Too many preprocessing steps

**Solution:**
```yaml
# Adjust in config file
performance:
  max_processing_fps: 15.0  # Reduce from 30

publish_debug_images: false  # Disable debug output

image_preprocessing:
  enable_denoising: false
  enable_sharpening: false
```

---

## Rollback Plan

If you encounter critical issues, you can quickly rollback to the Python wrapper:

### Emergency Rollback (5 minutes)

```bash
# Stop C++ node
ros2 lifecycle set /cotton_detection_node shutdown

# Start Python wrapper
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py
```

### Launch File Rollback

```python
# Add fallback option to your launch file
use_cpp_node = LaunchConfiguration('use_cpp_node', default='false')

node = Node(
    package='cotton_detection_ros2',
    executable=IfCondition(use_cpp_node, 'cotton_detection_node', 'cotton_detect_ros2_wrapper.py'),
    # ...
)
```

### Version Pinning

```bash
# Pin to Python wrapper version in package.xml
git checkout tags/v1.0.0-python-wrapper
colcon build --packages-select cotton_detection_ros2
```

---

## Deprecation Warnings

The C++ node automatically logs deprecation warnings if you're still using Python wrapper:

```python
# In your Python code, add migration notice
import warnings
warnings.warn(
    "cotton_detect_ros2_wrapper.py is deprecated and will be removed in Phase 5. "
    "Please migrate to cotton_detection_node (C++ implementation).",
    DeprecationWarning,
    stacklevel=2
)
```

---

## Additional Resources

### Documentation
- **ROS2 Interface Spec**: `docs/ROS2_INTERFACE_SPECIFICATION.md`
- **Hardware Test Checklist**: `docs/HARDWARE_TEST_CHECKLIST.md`
- **Phase 2 Implementation Plan**: `docs/PHASE2_IMPLEMENTATION_PLAN.md`

### Support
- **GitHub Issues**: Report migration problems
- **Migration Support**: Contact development team
- **Migration Timeline**: See project roadmap

### Tools
- **Migration validator**: `scripts/validate_migration.py`
- **Config converter**: `scripts/convert_config_to_yaml.py`
- **Performance comparison**: `scripts/compare_implementations.py`

---

## Summary Checklist

Before completing your migration, verify:

- [ ] C++ node builds successfully
- [ ] Simulation mode works
- [ ] Hardware detection tested
- [ ] Launch files updated
- [ ] Config files created
- [ ] Integration tests pass
- [ ] Performance benchmarks meet requirements
- [ ] TF frames updated
- [ ] Monitoring/diagnostics configured
- [ ] Rollback plan documented
- [ ] Team trained on new system

---

**Need Help?** Contact the cotton detection development team or open an issue on GitHub.

**Good luck with your migration!** 🚀
