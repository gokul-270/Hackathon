# OAK-D Lite Camera Calibration

## Overview

The Luxonis OAK-D Lite camera includes **factory calibration** stored on the device's EEPROM. This calibration is automatically loaded by the DepthAI SDK and does not need to be provided externally in most cases.

## Factory Calibration

### What's Included
- **RGB Camera**: Intrinsics (focal length, principal point) and distortion coefficients
- **Stereo Cameras**: Left and right mono camera intrinsics
- **Stereo Baseline**: Precise distance between left/right mono cameras  
- **Extrinsics**: Transformations between RGB and stereo cameras
- **Depth Calibration**: Stereo matching parameters

### Accessing Factory Calibration

The DepthAI Python SDK automatically reads factory calibration:

```python
import depthai as dai

with dai.Device() as device:
    calib = device.readCalibration()
    
    # RGB camera intrinsics
    rgb_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.RGB)
    print(f"RGB Focal Length: fx={rgb_intrinsics[0][0]}, fy={rgb_intrinsics[1][1]}")
    print(f"RGB Principal Point: cx={rgb_intrinsics[0][2]}, cy={rgb_intrinsics[1][2]}")
    
    # Stereo baseline
    baseline = calib.getBaselineDistance()
    print(f"Stereo Baseline: {baseline} cm")
    
    # Left mono intrinsics
    left_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.LEFT)
    
    # RGB distortion
    rgb_distortion = calib.getDistortionCoefficients(dai.CameraBoardSocket.RGB)
```

## Exporting Calibration for ROS2

### Option 1: Use Device Factory Calibration (Recommended)

**Phase 1** (Current): The wrapper node reads calibration from the device at runtime.

**Phase 2** (Enhanced): The DepthAI pipeline node will publish `camera_info` messages with factory calibration automatically.

### Option 2: Export and Pin Calibration

For reproducibility across multiple robots or offline testing, you can export calibration to YAML files:

#### Export Script

Create a script to export calibration when hardware is available:

```python
#!/usr/bin/env python3
"""
Export OAK-D Lite factory calibration to ROS2-compatible YAML files.
Run this script once with the camera connected to generate calibration files.
"""

import depthai as dai
import yaml
import numpy as np
from datetime import datetime

def export_calibration():
    with dai.Device() as device:
        calib = device.readCalibration()
        
        # Get camera intrinsics
        rgb_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.RGB, 1920, 1080)
        left_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.LEFT, 640, 400)
        right_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.RIGHT, 640, 400)
        
        # Get distortion coefficients
        rgb_dist = calib.getDistortionCoefficients(dai.CameraBoardSocket.RGB)
        left_dist = calib.getDistortionCoefficients(dai.CameraBoardSocket.LEFT)
        right_dist = calib.getDistortionCoefficients(dai.CameraBoardSocket.RIGHT)
        
        # Get extrinsics (camera-to-camera transforms)
        baseline = calib.getBaselineDistance()  # cm
        
        # Create RGB camera_info
        rgb_info = {
            'image_width': 1920,
            'image_height': 1080,
            'camera_name': 'oak_d_lite_rgb',
            'distortion_model': 'plumb_bob',
            'distortion_coefficients': {
                'rows': 1,
                'cols': 5,
                'data': rgb_dist.tolist()
            },
            'camera_matrix': {
                'rows': 3,
                'cols': 3,
                'data': rgb_intrinsics.flatten().tolist()
            },
            'rectification_matrix': {
                'rows': 3,
                'cols': 3,
                'data': np.eye(3).flatten().tolist()
            },
            'projection_matrix': {
                'rows': 3,
                'cols': 4,
                'data': np.hstack([rgb_intrinsics, [[0], [0], [0]]]).flatten().tolist()
            }
        }
        
        # Create left mono camera_info
        left_info = {
            'image_width': 640,
            'image_height': 400,
            'camera_name': 'oak_d_lite_left',
            'distortion_model': 'plumb_bob',
            'distortion_coefficients': {
                'rows': 1,
                'cols': 5,
                'data': left_dist.tolist()
            },
            'camera_matrix': {
                'rows': 3,
                'cols': 3,
                'data': left_intrinsics.flatten().tolist()
            },
            'rectification_matrix': {
                'rows': 3,
                'cols': 3,
                'data': np.eye(3).flatten().tolist()
            },
            'projection_matrix': {
                'rows': 3,
                'cols': 4,
                'data': np.hstack([left_intrinsics, [[0], [0], [0]]]).flatten().tolist()
            }
        }
        
        # Create right mono camera_info
        right_info = {
            'image_width': 640,
            'image_height': 400,
            'camera_name': 'oak_d_lite_right',
            'distortion_model': 'plumb_bob',
            'distortion_coefficients': {
                'rows': 1,
                'cols': 5,
                'data': right_dist.tolist()
            },
            'camera_matrix': {
                'rows': 3,
                'cols': 3,
                'data': right_intrinsics.flatten().tolist()
            },
            'rectification_matrix': {
                'rows': 3,
                'cols': 3,
                'data': np.eye(3).flatten().tolist()
            },
            'projection_matrix': {
                'rows': 3,
                'cols': 4,
                'data': np.hstack([right_intrinsics, [[0], [0], [0]]]).flatten().tolist()
            }
        }
        
        # Save to YAML files
        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        
        with open(f'rgb_camera_info_{timestamp}.yaml', 'w') as f:
            yaml.dump(rgb_info, f, default_flow_style=False)
        
        with open(f'left_camera_info_{timestamp}.yaml', 'w') as f:
            yaml.dump(left_info, f, default_flow_style=False)
        
        with open(f'right_camera_info_{timestamp}.yaml', 'w') as f:
            yaml.dump(right_info, f, default_flow_style=False)
        
        # Save stereo parameters
        stereo_params = {
            'baseline_cm': float(baseline),
            'baseline_m': float(baseline / 100.0),
            'export_date': timestamp,
            'device_mxid': device.getMxId()
        }
        
        with open(f'stereo_params_{timestamp}.yaml', 'w') as f:
            yaml.dump(stereo_params, f, default_flow_style=False)
        
        print(f"✅ Calibration exported successfully!")
        print(f"   - RGB: rgb_camera_info_{timestamp}.yaml")
        print(f"   - Left: left_camera_info_{timestamp}.yaml")
        print(f"   - Right: right_camera_info_{timestamp}.yaml")
        print(f"   - Stereo: stereo_params_{timestamp}.yaml")
        print(f"\nBaseline: {baseline:.2f} cm ({baseline/100.0:.4f} m)")
        print(f"Device MXID: {device.getMxId()}")

if __name__ == "__main__":
    export_calibration()
```

Save this as `export_calibration.py` and run when the camera is available.

#### Usage

```bash
# Connect OAK-D Lite camera
# Activate venv
source venv/bin/activate

# Run export script
python3 export_calibration.py

# Files will be created in current directory
# Copy them to this config directory
```

## Calibration Files in This Directory

### Current Status
- ✅ `README.md` - This file
- ⏳ `rgb_camera_info.yaml` - Export when camera available
- ⏳ `left_camera_info.yaml` - Export when camera available
- ⏳ `right_camera_info.yaml` - Export when camera available
- ⏳ `stereo_params.yaml` - Export when camera available

### Future Files (After Hardware Testing)
- `rgb_camera_info_<timestamp>.yaml` - RGB camera calibration
- `left_camera_info_<timestamp>.yaml` - Left mono camera calibration
- `right_camera_info_<timestamp>.yaml` - Right mono camera calibration
- `stereo_params_<timestamp>.yaml` - Stereo baseline and parameters

## Using Calibration in Launch Files

### Phase 1 (Current)
The wrapper node does not publish `camera_info` - it only publishes detections.

### Phase 2 (Enhanced)
Load calibration in launch file:

```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='cotton_detection_ros2',
            executable='cotton_detect_ros2_pipeline',
            name='cotton_detection',
            parameters=[{
                'rgb_camera_info_url': 'file:///path/to/rgb_camera_info.yaml',
                'left_camera_info_url': 'file:///path/to/left_camera_info.yaml',
                'right_camera_info_url': 'file:///path/to/right_camera_info.yaml',
                'use_factory_calibration': True,  # Default: use onboard calibration
            }]
        )
    ])
```

## Verification

### Check Factory Calibration

```bash
# With camera connected
python3 << EOF
import depthai as dai
with dai.Device() as device:
    calib = device.readCalibration()
    print(f"Baseline: {calib.getBaselineDistance()} cm")
    print(f"RGB intrinsics: {calib.getCameraIntrinsics(dai.CameraBoardSocket.RGB)}")
EOF
```

### Validate Calibration Quality

1. **Stereo Alignment**: Check that depth aligns with RGB at various distances
2. **Depth Accuracy**: Measure objects at known distances (1.0m, 1.5m, 2.0m)
3. **Rectification**: Verify stereo images are properly rectified

Expected Accuracy:
- **Depth**: ±1-2% at 1.0-1.5m range
- **Spatial coordinates**: ±5cm at cotton picking distances

## Re-Calibration

OAK-D Lite cameras **rarely need re-calibration**. Factory calibration is precise and stable.

### When to Re-Calibrate
- Physical damage to camera housing
- Significant temperature changes affecting optics
- Mounting misalignment issues
- Depth accuracy degradation observed

### Re-Calibration Tools
- **Luxonis Calibration Tool**: https://docs.luxonis.com/projects/api/en/latest/tutorials/calibration/
- **OpenCV Stereo Calibration**: For custom calibration patterns

## References

- **DepthAI Calibration API**: https://docs.luxonis.com/projects/api/en/latest/references/python/#depthai.CalibrationHandler
- **ROS2 camera_info**: http://docs.ros.org/en/rolling/p/sensor_msgs/interfaces/msg/CameraInfo.html
- **OAK-D Lite Specs**: https://docs.luxonis.com/projects/hardware/en/latest/pages/DM9095/

---

**Status**: ⏳ Awaiting hardware to export calibration  
**Next Step**: Run `export_calibration.py` when camera is connected  
**Priority**: Medium (factory calibration works fine for now)
