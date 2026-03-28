# Phase 2 Implementation Plan

**Phase**: Phase 2 - Enhanced Direct DepthAI Integration  
**Goal**: Replace file-based communication with direct DepthAI pipeline integration  
**Status**: Planning Complete - Ready to Implement

---

## Overview

Phase 2 enhances the Phase 1 wrapper by integrating the DepthAI pipeline directly into the ROS2 node, eliminating file-based communication and enabling real-time camera streaming and detection.

### Key Objectives

1. **Direct DepthAI Integration**: Embed DepthAI pipeline directly in wrapper node
2. **Real-Time Operation**: Continuous camera streaming and on-demand detection
3. **Enhanced Publishing**: Add RGB image, depth map, and camera_info topics
4. **Service-Triggered Detection**: Maintain service interface, add continuous mode
5. **Remove File Dependencies**: Eliminate cotton_details.txt file-based communication
6. **PointCloud Publishing**: Optional PointCloud2 generation from depth data

---

## Architecture Changes

### Phase 1 (Current)
```
┌─────────────────────────────────────┐
│  ROS2 Wrapper Node                  │
│  - Exposes services/topics          │
│  - Reads cotton_details.txt         │
└──────────┬──────────────────────────┘
           │ File I/O
┌──────────▼──────────────────────────┐
│  CottonDetect.py (Standalone)       │
│  - Runs DepthAI pipeline            │
│  - Writes cotton_details.txt        │
│  - Signal-based (SIGUSR1/SIGUSR2)   │
└─────────────────────────────────────┘
```

### Phase 2 (Target)
```
┌──────────────────────────────────────────────────────┐
│  Enhanced ROS2 Wrapper Node                          │
│  ┌────────────────────────────────────────────────┐  │
│  │  DepthAI Pipeline (Embedded)                   │  │
│  │  - ColorCamera (1080p)                         │  │
│  │  - MonoLeft + MonoRight (400p)                 │  │
│  │  - StereoDepth (HIGH_ACCURACY)                 │  │
│  │  - YoloSpatialDetectionNetwork (yolov8v2.blob) │  │
│  │  - USB2 Mode                                   │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  ROS2 Interfaces:                                    │
│  - Services: /cotton_detection/detect                │
│  - Topics:                                            │
│    • /oak/rgb/image_raw (sensor_msgs/Image)          │
│    • /oak/rgb/camera_info (sensor_msgs/CameraInfo)   │
│    • /oak/stereo/depth (sensor_msgs/Image)           │
│    • /cotton_detection/results (Detection3DArray)    │
│    • /cotton_detection/pointcloud (PointCloud2)      │
└───────────────────────────────────────────────────────┘
```

---

## Implementation Tasks

### Task 1: Enhance Wrapper Node with Direct DepthAI Pipeline
**File**: `scripts/cotton_detect_ros2_wrapper_enhanced.py`

**Sub-tasks**:
1. Import DepthAI pipeline construction from CottonDetect.py
2. Initialize pipeline in node `__init__`
3. Add device management (connect/disconnect)
4. Configure pipeline with ROS2 parameters
5. Add continuous streaming mode
6. Add service-triggered detection mode

**Code Structure**:
```python
class EnhancedCottonDetectWrapper(Node):
    def __init__(self):
        # Initialize ROS2 node
        # Declare parameters
        # Create publishers (RGB, depth, detections, etc.)
        # Create services
        # Initialize DepthAI pipeline
        # Start camera thread
    
    def _initialize_depthai_pipeline(self):
        # Create pipeline matching CottonDetect.py
        # Configure ColorCamera, MonoCamera, StereoDepth
        # Configure YoloSpatialDetectionNetwork
        # Apply ROS2 parameters
    
    def _camera_streaming_thread(self):
        # Continuous loop fetching frames
        # Publish RGB images
        # Publish depth maps
        # Publish camera_info
    
    def _process_detections(self, detections, frame):
        # Convert DepthAI detections to Detection3DArray
        # Publish to /cotton_detection/results
        # Optionally publish debug image
```

**Dependencies**:
- `depthai` (already installed in venv)
- ROS1 `CottonDetect.py` as reference
- `cv_bridge` for image conversion

---

### Task 2: Add Real-Time Topic Publishing
**New Topics**:

1. **RGB Camera Stream**:
   ```
   Topic: /oak/rgb/image_raw
   Type: sensor_msgs/Image
   Rate: 30 Hz (configurable)
   Encoding: bgr8
   ```

2. **Camera Info**:
   ```
   Topic: /oak/rgb/camera_info
   Type: sensor_msgs/CameraInfo
   Rate: 30 Hz
   Intrinsics: From device calibration
   ```

3. **Depth Map**:
   ```
   Topic: /oak/stereo/depth
   Type: sensor_msgs/Image
   Rate: 30 Hz (configurable)
   Encoding: 16UC1 (millimeters)
   ```

4. **Detection Results** (Enhanced):
   ```
   Topic: /cotton_detection/results
   Type: vision_msgs/Detection3DArray
   Rate: On-demand or continuous
   Frame: oak_rgb_camera_optical_frame
   ```

5. **PointCloud** (Optional):
   ```
   Topic: /cotton_detection/pointcloud
   Type: sensor_msgs/PointCloud2
   Rate: On-demand
   Format: XYZ + RGB
   ```

---

### Task 3: Service Enhancements
**Enhanced Service Behavior**:

```python
# /cotton_detection/detect service
Request:
    int32 detect_command
        0 = stop continuous detection
        1 = single-shot detection
        2 = start continuous detection
        3 = calibrate (future)

Response:
    int32[] data              # Spatial coordinates (mm)
    bool success              # Operation status
    string message            # Status message
    int32 num_detections      # Number of detections
```

**Operating Modes**:
- **Single-Shot**: Capture one frame, detect, publish, return
- **Continuous**: Start detection loop, publish on every frame
- **On-Demand**: Stream camera, detect only when service called

---

### Task 4: Parameter Integration
**Additional Parameters** (matching CottonDetect.py):

```python
# Detection parameters
'detection_mode': 'on_demand'  # 'on_demand', 'continuous', 'single_shot'
'publish_rate_hz': 30.0        # Camera publishing rate

# Spatial detection parameters
'bbox_scale_factor': 0.5       # Bounding box scale
'depth_lower_threshold': 100   # mm
'depth_upper_threshold': 5000  # mm

# Coordinate transformation
'y_multiplication_factor': -1  # Frame transformation (ROS1 compatibility)

# Publishing control
'publish_rgb_stream': True     # Enable RGB publishing
'publish_depth_stream': True   # Enable depth publishing
'publish_camera_info': True    # Enable camera_info publishing
```

---

### Task 5: PointCloud Generation
**Implementation**:

Based on ROS1 `projector_device.py`:
```python
class PointCloudGenerator:
    def __init__(self, camera_intrinsics, width, height):
        self.intrinsics = camera_intrinsics
        self.width = width
        self.height = height
    
    def rgbd_to_pointcloud2(self, depth_frame, rgb_frame, header):
        # Convert depth + RGB to PointCloud2
        # Use camera intrinsics for projection
        # Return sensor_msgs/PointCloud2
```

**Features**:
- XYZ coordinates from depth
- RGB color from camera
- Downsample option for performance
- Optional PCD file export (backward compatibility)

---

### Task 6: URDF Camera Updates
**File**: `robo_description/urdf/camera.xacro` (or create if doesn't exist)

**OAK-D Lite Specifications**:
```xml
<!-- Physical dimensions (from Luxonis datasheet) -->
Width:  90.0 mm
Height: 27.0 mm
Depth:  18.5 mm
Mass:   ~0.064 kg

<!-- Camera baselines -->
Stereo baseline: 75 mm (left-right mono cameras)

<!-- Frame names -->
<link name="oak_camera_link"/>
<link name="oak_rgb_camera_optical_frame"/>
<link name="oak_left_camera_optical_frame"/>
<link name="oak_right_camera_optical_frame"/>
```

**Mount Transform**:
- Update robot URDF to mount OAK-D Lite at correct position
- Set optical frame transforms (REP-103 compliant)
- Remove any RealSense D415 references

---

### Task 7: Testing and Validation
**Test Plan**:

1. **Unit Tests**:
   - DepthAI pipeline initialization
   - Image publishing rate
   - Detection accuracy
   - Service response time

2. **Integration Tests**:
   - End-to-end detection pipeline
   - Topic synchronization
   - TF tree validation
   - Parameter reconfiguration

3. **Performance Tests**:
   - Latency measurement (camera → detection → publish)
   - CPU/Memory usage
   - USB2 bandwidth utilization
   - Detection FPS

4. **Functional Tests**:
   - Detection accuracy at various distances
   - USB2 mode stability
   - Continuous operation (multi-hour)
   - Recovery from camera disconnect

---

## Implementation Priority

### High Priority (Phase 2A - Core Functionality)
1. ✅ Direct DepthAI pipeline integration
2. ✅ Real-time RGB/depth publishing
3. ✅ Enhanced detection service
4. ✅ Remove file-based communication
5. ✅ Camera_info publishing

### Medium Priority (Phase 2B - Enhanced Features)
6. ⏳ PointCloud2 generation
7. ⏳ Continuous detection mode
8. ⏳ URDF camera updates
9. ⏳ Parameter reconfiguration support

### Low Priority (Phase 2C - Polish)
10. ⏳ Performance optimization
11. ⏳ Rosbag recording utilities
12. ⏳ Visualization tools
13. ⏳ Documentation updates

---

## Migration Path

### Backward Compatibility
**Phase 1 → Phase 2 Transition**:

```python
# Phase 1 (file-based) - Keep as fallback
cotton_detect_ros2_wrapper.py

# Phase 2 (direct integration) - New default
cotton_detect_ros2_wrapper_enhanced.py

# Launch file selection
ros2 launch cotton_detection_ros2 \
    cotton_detection_wrapper.launch.py mode:=enhanced
```

**Compatibility Matrix**:
| Feature | Phase 1 | Phase 2 |
|---------|---------|---------|
| Service Interface | ✅ | ✅ (Enhanced) |
| Detection3DArray Topic | ✅ | ✅ |
| RGB Image Topic | ❌ | ✅ |
| Depth Topic | ❌ | ✅ |
| Camera Info | ❌ | ✅ |
| PointCloud | ❌ | ✅ (Optional) |
| File-based I/O | ✅ | ❌ (Removed) |
| Continuous Mode | ❌ | ✅ |

---

## Risk Mitigation

### Technical Risks

1. **DepthAI Pipeline Complexity**
   - **Risk**: Direct pipeline integration may introduce bugs
   - **Mitigation**: Reuse ROS1 CottonDetect.py configuration exactly
   - **Fallback**: Keep Phase 1 wrapper as backup

2. **USB2 Bandwidth**
   - **Risk**: Simultaneous RGB + Depth + Detection may exceed bandwidth
   - **Mitigation**: Add configurable FPS limits, optional stream disabling
   - **Testing**: Validate with actual hardware in USB2 mode

3. **Performance Degradation**
   - **Risk**: Python overhead may reduce detection rate
   - **Mitigation**: Profile and optimize hot paths
   - **Fallback**: Move to Phase 3 (C++) if needed

4. **Camera Calibration**
   - **Risk**: Factory calibration may not be optimal
   - **Mitigation**: Support custom calibration YAML loading
   - **Testing**: Validate depth accuracy at known distances

### Operational Risks

1. **Hardware Failure**
   - **Mitigation**: Graceful degradation, error recovery
   - **Logging**: Comprehensive error messages

2. **Integration Issues**
   - **Mitigation**: Maintain Phase 1 as tested fallback
   - **Testing**: Extensive integration testing before deployment

---

## Success Criteria

### Phase 2A (Core) - Complete When:
- [ ] DepthAI pipeline runs in ROS2 node
- [ ] RGB images published at 30 Hz
- [ ] Depth maps published at 30 Hz
- [ ] Detection service works without files
- [ ] Camera_info published correctly
- [ ] Detection accuracy matches Phase 1
- [ ] Latency ≤ 10% over Phase 1
- [ ] No USB2 bandwidth issues
- [ ] All tests pass

### Phase 2B (Enhanced) - Complete When:
- [ ] PointCloud2 publishing works
- [ ] Continuous detection mode functional
- [ ] URDF updated with OAK-D Lite specs
- [ ] Parameter reconfiguration tested
- [ ] Multi-hour stability validated

### Phase 2C (Polish) - Complete When:
- [ ] Performance profiled and optimized
- [ ] Documentation fully updated
- [ ] User guides created
- [ ] Demos and tutorials ready

---

## Timeline Estimate

**Phase 2A (Core)**:
- Task 1 (DepthAI Integration): 4-6 hours
- Task 2 (Topic Publishing): 2-3 hours
- Task 3 (Service Enhancement): 2 hours
- Task 4 (Parameters): 1 hour
- Testing & Debug: 3-4 hours
- **Total: ~12-16 hours**

**Phase 2B (Enhanced)**:
- Task 5 (PointCloud): 3-4 hours
- Task 6 (URDF): 2 hours
- Task 7 (Testing): 4-5 hours
- **Total: ~9-11 hours**

**Phase 2C (Polish)**:
- Optimization: 2-3 hours
- Documentation: 3-4 hours
- **Total: ~5-7 hours**

**Grand Total: 26-34 hours**

---

## Next Steps

1. **Immediate**: Start Phase 2A with Task 1 (DepthAI integration)
2. **Create**: Enhanced wrapper node with embedded pipeline
3. **Test**: Validate with OAK-D Lite hardware (if available)
4. **Iterate**: Refine based on testing results
5. **Document**: Update progress reports

---

**Status**: ✅ **Ready to Begin Phase 2 Implementation**
