sensor_msgs/Image:
sensor_msgs/PointCloud2:
# ROS2 Interface Specification — `cotton_detection_ros2`

**Package**: `cotton_detection_ros2`  
**Primary Node**: `cotton_detection_node` (C++)  
**Legacy Node**: `cotton_detect_ros2_wrapper` (Python)  
**Status**: ✅ **Production Ready** (Validated Nov 1, 2025)  

Updated: 2025-11-04

---

## ✅ Production Validation (Nov 1, 2025)

**Hardware:** Raspberry Pi 4 + OAK-D Lite

**Performance Metrics:**
- **Detection Latency:** 70ms (pure detection on Myriad X VPU)
- **Service Latency:** 134ms average (123-218ms range)
- **Reliability:** 100% (10/10 consecutive tests)
- **Spatial Accuracy:** ±10mm @ 0.6m
- **Build Time (RPi):** 4m 33s with -j2 (OOM fixed)
- **Thermal (Production):** 65.2°C peak - stable

**Status:** C++ node is production path. Python wrapper maintained as legacy fallback only.

---

## 1. Scope & Roles

| Node | Role | When to use |
|------|------|-------------|
| `cotton_detection_node` (C++) | Canonical implementation. Provides HSV/YOLO detection, optional DepthAI integration, diagnostics, and simulation mode. | Default choice for all deployments and testing. |
| `cotton_detect_ros2_wrapper` (Python) | Legacy subprocess wrapper around `OakDTools/CottonDetect.py`. Maintained for legacy automation workflows and as a temporary fallback. | Only when legacy automation requires it or as a fallback during hardware validation. |

The following sections document the interfaces for both nodes. Sections 2–4 cover the C++ node (primary). Appendix A captures the legacy wrapper specifics.

---

## 2. Primary Node: `cotton_detection_node`

### 2.1 Published Topics

#### `/cotton_detection/results`
- **Type**: `cotton_detection_ros2/msg/DetectionResult`
- **QoS**: Reliable, Keep Last (10)
- **Rate**: Event-driven (on camera callback or simulation tick)
- **Frame**: Frame ID stored per `CottonPosition.header.frame_id` (defaults to `cotton_camera_frame`)
- **Purpose**: Delivers detected cotton centroids with metadata

**Message Schema**:
```

  std_msgs/Header header        # Detection batch metadata
  int32 total_count             # Number of detections in this batch
  bool detection_successful     # False if pipeline failed
  float32 processing_time_ms    # Wall-clock duration
  CottonPosition[] positions    # Detected cotton targets

CottonPosition:
  std_msgs/Header header        # Timestamp + frame per target
  geometry_msgs/Point position  # Approximate XYZ in meters
  float32 confidence            # 0.0-1.0 detection score
  int32 detection_id            # Sequential identifier
```

#### `/cotton_detection/debug_image`
- **Type**: `sensor_msgs/Image` (via image_transport). Compressed topic `.../compressed` provided when `enable_debug_output=true`
- **QoS**: Best Effort, Keep Last (1)
- **Purpose**: Overlay visualisation for inspection/debugging
- **Enable via parameter**: `enable_debug_output`

#### `/camera/camera_info`
- **Type**: `sensor_msgs/CameraInfo`
- **QoS**: Reliable, Keep Last (10)
- **Purpose**: Broadcasts synthetic camera info when DepthAI enabled or when simulation publishes frames.

### 2.2 Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/camera/image_raw` (configurable) | `sensor_msgs/Image` | Main RGB stream processed by the pipeline. |
| `/camera/image_raw/compressed` (optional) | `sensor_msgs/CompressedImage` | Used when only compressed transport is available. |

The `camera_topic` parameter controls both subscriptions.

### 2.3 Services

#### `/cotton_detection/detect`
- **Type**: `cotton_detection_ros2/srv/CottonDetection`
- **Purpose**: Triggers immediate detection cycle or controls simulation runs.

Request/Response summary:
```
Request:
  int32 detect_command   # 1 = run detection, 0 = stop stream, 2 = export calibration artifacts

Response:
  int32[] data           # ASCII-encoded filesystem path when detect_command==2; empty otherwise
  bool success           # True if pipeline executed successfully
  string message         # Human-readable status (includes output path on success)
```

Behavior:
1. For live camera mode, ensures the next processed frame publishes a `DetectionResult`.
2. In simulation mode, fabricates synthetic detections.
3. Returns `success=false` if validation fails or camera data unavailable. For calibration requests (`detect_command=2`), the node saves YAML to `calibration_output_dir` (parameter) using DepthAI data when available, otherwise falls back to the bundled script.

### 2.4 Parameters

Parameters are declared under a flat namespace with dot-delimited groups. The default YAML reference is `config/cotton_detection_cpp.yaml`.

| Group | Parameter | Type/Default | Notes |
|-------|-----------|--------------|-------|
| General | `camera_topic` | string `/camera/image_raw` | Input topic |
| General | `debug_image_topic` | string `/cotton_detection/debug_image/compressed` | Advertised when debug enabled |
| General | `enable_debug_output` | bool `false` | Publishes debug overlays |
| General | `simulation_mode` | bool `false` | Enables deterministic synthetic detections |
| General | `use_depthai` | bool `true` | Governs DepthAI pipeline utilisation (requires build flag) |
| Detection | `detection_confidence_threshold` | double `0.7` | Applied after fusion |
| Detection | `max_cotton_detections` | int `50` | Upper bound on results |
| Detection | `detection_mode` | string `hybrid_fallback` | Options: `hsv_only`, `yolo_only`, `hybrid_voting`, `hybrid_merge`, `hybrid_fallback`, `depthai_direct` |
| HSV | `cotton_detection.hsv_lower_bound` | `int[3]` `[0,0,180]` | Hue/Sat/Value minimums |
| HSV | `cotton_detection.hsv_upper_bound` | `int[3]` `[180,40,255]` | Hue/Sat/Value maximums |
| HSV | `cotton_detection.min_contour_area` | double `50.0` | Pixels |
| HSV | `cotton_detection.max_contour_area` | double `5000.0` | Pixels |
| HSV | `cotton_detection.morphology_kernel_size` | int `5` | Must be odd |
| HSV | `cotton_detection.gaussian_blur_size` | int `3` | Must be odd |
| HSV | `cotton_detection.nms_overlap_threshold` | double `0.3` | Non-max suppression |
| Preprocessing | `image_preprocessing.enable_denoising` | bool `true` | Bilateral filter |
| Preprocessing | `image_preprocessing.enable_histogram_equalization` | bool `false` | Contrast normalization |
| Preprocessing | `image_preprocessing.enable_sharpening` | bool `false` | Laplacian sharpening |
| Preprocessing | `image_preprocessing.contrast_alpha` | double `1.0` | Contrast gain |
| Preprocessing | `image_preprocessing.brightness_beta` | int `0` | Bias |
| Preprocessing | `image_preprocessing.gamma_correction` | double `1.0` | Gamma |
| Preprocessing | `image_preprocessing.denoise_h` | double `10.0` | Denoise strength |
| Preprocessing | `image_preprocessing.sharpen_amount` | double `1.0` | Sharpening gain |
| Coordinate | `coordinate_transform.pixel_to_meter_scale_x` | double `0.001` | Pixel → meter scaling |
| Coordinate | `coordinate_transform.pixel_to_meter_scale_y` | double `0.001` | |
| Coordinate | `coordinate_transform.assumed_depth_m` | double `0.5` | Used when depth absent |
| YOLO | `yolo_enabled` | bool `true` | Toggle YOLO fusion |
| YOLO | `yolo_model_path` | string `/opt/models/cotton_yolov8.onnx` | ONNX model |
| YOLO | `yolo_config_path` | string `` | Optional config |
| YOLO | `yolo_confidence_threshold` | double `0.5` | |
| YOLO | `yolo_nms_threshold` | double `0.4` | |
| YOLO | `yolo_input_width/height` | int `640` | Preprocess size |
| Performance | `performance.max_processing_fps` | double `30.0` | FPS throttle |
| Performance | `performance.processing_timeout_ms` | int `1000` | Watchdog |
| Performance | `performance.enable_monitoring` | bool `true` | Diagnostics toggles |
| Performance | `performance.detailed_logging` | bool `false` | Verbose logs |
| Performance | `performance.max_recent_measurements` | int `100` | Buffer length |

#### DepthAI-Specific Parameters (only when built with `-DHAS_DEPTHAI=ON`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `depthai.enable` | `false` | Enables direct OAK-D Lite handling inside the C++ node. |
| `depthai.model_path` | `scripts/OakDTools/yolov8v2.blob` | Path to compiled blob. |
| `depthai.camera_width` / `depthai.camera_height` | `416` | Input resolution. |
| `depthai.camera_fps` | `30` | DepthAI pipeline FPS. |
| `depthai.confidence_threshold` | `0.5` | DepthAI detection confidence. |
| `depthai.depth_min_mm` / `depthai.depth_max_mm` | `100.0` / `5000.0` | Depth range in millimetres. |
| `depthai.enable_depth` | `true` | Enable depth stream. |
| `depthai.device_id` | `` | Restrict to a specific device. |

### 2.5 Frames & TF

The node broadcasts static transforms (via `tf2_ros::StaticTransformBroadcaster`) when available:
- `base_link` → `cotton_camera_link`
- `cotton_camera_link` → `cotton_camera_optical_frame`

Customize via launch to align with the robot’s URDF if different.

### 2.6 Diagnostics & Logging

- Uses `diagnostic_updater`. Enable verbose metrics with `performance.detailed_logging=true`.
- Diagnostic tasks: `Cotton Detection Status` (always) and `DepthAI Camera Status` (when DepthAI compiled).
- Warning states propagated via `/diagnostics` topic.

---

## 3. Legacy Wrapper: `cotton_detect_ros2_wrapper`

### 3.1 Published Topics

| Topic | Type | Notes |
|-------|------|-------|
| `/cotton_detection/results` | `vision_msgs/Detection3DArray` | Derived from file-parsed outputs; includes bounding boxes + 3D points from DepthAI stereo. |
| `/cotton_detection/debug_image` | `sensor_msgs/Image` | Annotated DepthAI frame; enable with launch parameter `publish_debug_image`. |

### 3.2 Services

| Service | Type | Description |
|---------|------|-------------|
| `/cotton_detection/detect` | `cotton_detection_ros2/CottonDetection` | Starts a one-shot detection (uses detect_command=1). |
| `/cotton_detection/calibrate` | `cotton_detection_ros2/CottonDetection` | Exports calibration files from the OAK-D Lite EEPROM. |

> **Note:** The C++ node now handles calibration export directly (service command `detect_command=2`). The legacy `/cotton_detection/detect_cotton` trigger was retired in October 2025—update any scripts still referencing it.

### 3.3 Key Parameters

Legacy launch parameters (see `cotton_detection_wrapper.launch.py`):

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `simulation_mode` | `false` | Generates synthetic detections.* |
| `usb_mode` | `usb2` | Configures DepthAI USB bandwidth. |
| `output_dir` | `/home/ubuntu/pragati/outputs` | File output destination. |
| `input_dir` | `/home/ubuntu/pragati/inputs` | Capture directory. |
| `confidence_threshold` | `0.5` | YOLO detection threshold inside Python script. |
| `publish_debug_image` | `true` | Publish annotated frames. |

> *Wrapper simulation mode mimics detection without launching DepthAI.

### 3.4 File Outputs

- `cotton_details.txt` — detection results parsed into ROS messages. Format: `636 0 x y z confidence` per line.
- `DetectionOutput.jpg` — annotated RGB image.
- `calibration/` — directory written by calibration service (`calibration.json`, intrinsics, baseline files).

### 3.5 Limitations

- Relies on signals (SIGUSR1/SIGUSR2) and filesystem polling; higher latency than C++. 
- Single-threaded; heavy detection can block ROS callbacks.
- Planned for deprecation once calibration export and stereo depth move into the C++ pipeline.

---

## 4. Feature Parity & Gaps

| Capability | C++ Node | Python Wrapper |
|------------|---------|----------------|
| Continuous detection stream | ✅ (`detection_mode=depthai_direct` / hybrid) | ⚠️ Trigger-only |
| Simulation mode | ✅ (`simulation_mode`) | ✅ |
| Calibration export | ✅ (ASCII path via `/cotton_detection/detect`, command=2) | ✅ (legacy `/cotton_detection/calibrate`) |
| DepthAI direct pipeline | ✅ (requires `-DHAS_DEPTHAI=ON`, alpha) | ✅ (primary) |
| Diagnostics | ✅ (`diagnostic_updater`) | ⚠️ Logging only |
| Detection message | `DetectionResult` | `Detection3DArray` |

Outstanding tasks are tracked in `docs/STATUS_REALITY_MATRIX.md` and `MIGRATION_GUIDE.md`.

---

## 5. Validation Hooks

- `scripts/test_cotton_detection.py` — exercises results topic (accepts either message type based on mode).
- `scripts/performance_benchmark.py` — measures latency (requires hardware).
- `test/cotton_detector_test.cpp` / `test/yolo_detector_test.cpp` — unit tests for internal components (colcon test).

---

## Appendix A — Message & Service Definitions

```
# cotton_detection_ros2/msg/DetectionResult.msg
CottonPosition[] positions
int32 total_count
bool detection_successful
float32 processing_time_ms
std_msgs/Header header

# cotton_detection_ros2/msg/CottonPosition.msg
geometry_msgs/Point position
float32 confidence
int32 detection_id
std_msgs/Header header

# cotton_detection_ros2/srv/CottonDetection.srv
int32 detect_command
---
int32[] data
bool success
string message


---

## Appendix B — Launch Files

- `launch/cotton_detection_cpp.launch.py`
  - Parameters: `params_file`, `use_depthai`, `simulation_mode`, `namespace`, etc.
  - Includes `cotton_detection_cpp.yaml` by default.
- `launch/cotton_detection_wrapper.launch.py`
  - Parameters: `simulation_mode`, `usb_mode`, `publish_debug_image`, path overrides.
  - Spawns Python executable via `ament_python` entry point.

Refer to launch files for full argument lists and defaults.
#### `enable_calibration_service`
- **Type**: `bool`
- **Default**: `true`
- **Description**: Enable `/cotton_detection/calibrate` service
- **Purpose**: Export camera calibration data from OAK-D EEPROM

---

## File-Based Integration (Phase 1)

### Subprocess Management

The Phase 1 wrapper uses **subprocess-based architecture** where `CottonDetect.py` runs as a managed child process:

#### Process Lifecycle
1. **Startup**: Wrapper launches `CottonDetect.py` via `subprocess.Popen()`
2. **Initialization**: Child process sends `SIGUSR2` to parent when camera is ready
3. **Detection**: Parent sends `SIGUSR1` to child to trigger detection
4. **Output**: Child writes results to files, parent reads and publishes
5. **Shutdown**: Parent sends `SIGTERM` (graceful) or `SIGKILL` (forceful) to child

#### Signal Communication

**`SIGUSR2` (Camera Ready Signal)**
- **Direction**: Child → Parent (CottonDetect.py → wrapper)
- **Purpose**: Indicates OAK-D camera initialized successfully
- **Timing**: Sent once during startup after DepthAI pipeline creation
- **Handler**: Registered in wrapper's `_setup_signal_handlers()`
- **Timeout**: 30 seconds (configurable via `startup_timeout` parameter)

**`SIGUSR1` (Detection Trigger Signal)**
- **Direction**: Parent → Child (wrapper → CottonDetect.py)
- **Purpose**: Triggers a single detection cycle
- **Timing**: Sent when `/cotton_detection/detect` service is called
- **Handler**: Implemented in CottonDetect.py (line 391)
- **Response**: Child writes `cotton_details.txt` and `DetectionOutput.jpg`

**`SIGTERM` (Graceful Shutdown Signal)**
- **Direction**: Parent → Child (wrapper → CottonDetect.py)
- **Purpose**: Request graceful process termination
- **Timeout**: 5 seconds before escalating to SIGKILL
- **Handler**: Default Python handler (cleanup and exit)

#### Process Monitoring

- **Monitor Thread**: Background thread checks subprocess health every 1 second
- **Crash Detection**: Detects unexpected process termination
- **Restart Policy**: Manual restart required (no automatic restart in Phase 1)
- **Logging**: STDOUT/STDERR captured for debugging

### Input Files (Read by Wrapper)

#### `cotton_details.txt`
- **Location**: `{output_directory}/cotton_details.txt` (default: `/home/ubuntu/pragati/outputs/`)
- **Format**: Plain text, one detection per line
- **Line Format**: `636 0 <x> <y> <z>` (legacy format from ROS1)
- **Example**:
  ```
  636 0 0.234 -0.045 1.250
  636 0 0.156 0.123 1.180
  ```
- **Coordinate System**: Camera-relative (meters)
- **Parsing**: Wrapper reads file, skips first two fields, extracts x/y/z
- **Cleanup**: Old file removed before each detection trigger
- **Removal**: Phase 2 will replace with direct pipeline integration

#### `img100.jpg`
- **Location**: `{output_directory}/img100.jpg`
- **Purpose**: Raw captured RGB frame (for debugging)

#### `DetectionOutput.jpg`
- **Location**: `{output_directory}/DetectionOutput.jpg`
- **Purpose**: Annotated image with bounding boxes
- **Published to**: `/cotton_detection/debug_image` if parameter enabled

#### `output.pcd`
- **Location**: `{output_directory}/output.pcd`
- **Purpose**: Point cloud file in PCD format
- **Optional**: Only created if DepthAI pipeline exports it

---

## TF Frame Conventions

### Required Frames

```
robot_base_link
    └── camera_link (camera physical mounting)
         ├── camera_rgb_frame (RGB sensor frame)
         │    └── camera_rgb_optical_frame (optical: Z forward, X right, Y down)
         └── camera_depth_frame (stereo depth frame)
              ├── camera_depth_optical_frame (optical: Z forward)
              ├── camera_left_frame (left mono camera)
              │    └── camera_left_optical_frame
              └── camera_right_frame (right mono camera)
                   └── camera_right_optical_frame
```

### Frame Naming Convention (REP-103)

- **Suffix `_frame`**: Physical frame (X forward, Y left, Z up)
- **Suffix `_optical_frame`**: Optical frame (Z forward, X right, Y down)
- **Prefix `camera_`**: All camera-related frames

### Detection Frame

All detections are published in **`camera_rgb_optical_frame`** by default:
- **+X**: Right
- **+Y**: Down
- **+Z**: Forward (distance from camera)

---

## Data Flow Diagram

### Phase 1 (Current Implementation)

```
┌─────────────────────────────────────────────────────────┐
│ ROS2 Service Call: /cotton_detection/detect            │
│ ├─ cotton_detection_ros2/srv/CottonDetection           │
│ └─ Request: {detect_command: 1}                         │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ cotton_detect_ros2_wrapper.py (ROS2 Python Node)       │
│ ├─ Reads parameters (blob_path, thresholds, usb_mode)  │
│ ├─ Executes: python3 CottonDetect.py                   │
│ └─ Waits for file output                               │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ CottonDetect.py (ROS1 Python - Unmodified)             │
│ ├─ Initializes DepthAI pipeline                        │
│ │   ├─ ColorCamera(1920x1080)                          │
│ │   ├─ MonoLeft + MonoRight(400p)                      │
│ │   ├─ StereoDepth(HIGH_ACCURACY, 7x7, conf=255)       │
│ │   └─ YoloSpatialDetectionNetwork(yolov8v2.blob)      │
│ ├─ Captures frame and runs detection                   │
│ └─ Writes outputs:                                      │
│     ├─ cotton_details.txt (spatial coordinates)        │
│     ├─ img100.jpg (raw frame)                          │
│     └─ DetectionOutput.jpg (annotated)                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ cotton_detect_ros2_wrapper.py (Continued)              │
│ ├─ Reads cotton_details.txt                            │
│ ├─ Parses detection coordinates                        │
│ ├─ Constructs vision_msgs/Detection3DArray             │
│ ├─ Publishes to /cotton_detection/results              │
│ ├─ Optionally publishes debug_image                    │
│ └─ Returns service response                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ ROS2 Service Response                                   │
│ ├─ success: true                                        │
│ ├─ message: "Detected N cottons"                       │
│ └─ detection_count: N                                   │
└─────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ ROS2 Topic Publish: /cotton_detection/results          │
│ └─ vision_msgs/Detection3DArray (N detections)         │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 2 Target Architecture

### Direct DepthAI Integration (No File I/O)

```
┌─────────────────────────────────────────────────────────┐
│ cotton_detect_ros2_pipeline.py (ROS2 Python Node)      │
│                                                          │
│ DepthAI Pipeline (Embedded):                            │
│ ├─ ColorCamera ─────► RGB Stream ─────► Topic Publish  │
│ ├─ MonoLeft/Right ──► Stereo Depth ──► Topic Publish   │
│ ├─ StereoDepth ─────► Depth Map ──────► Topic Publish  │
│ └─ YoloSpatialNet ──► Detections ─────► Topic Publish  │
│                                                          │
│ ROS2 Publishers:                                         │
│ ├─ /oak/rgb/image_raw                                  │
│ ├─ /oak/rgb/camera_info                                │
│ ├─ /oak/stereo/depth                                   │
│ ├─ /oak/stereo/camera_info                             │
│ └─ /cotton_detection/results (continuous)              │
│                                                          │
│ Services:                                                │
│ ├─ /cotton_detection/detect (trigger)                  │
│ └─ /cotton_detection/set_roi (ROI selection)           │
└─────────────────────────────────────────────────────────┘
```

**Phase 2 Benefits**:
- ✅ Real-time streaming (30 Hz RGB/depth)
- ✅ Continuous detection mode
- ✅ Camera_info publishing
- ✅ Zero file I/O overhead
- ✅ Lower latency
- ✅ Better ROS2 integration

---

## Usage Examples

### Basic Detection

```bash
# Terminal 1: Launch wrapper node
source install/setup.bash
source venv/bin/activate
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# Terminal 2: Trigger detection
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Terminal 3: Monitor results
ros2 topic echo /cotton_detection/results
```

### Custom Configuration

```bash
# USB3 mode with higher confidence
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    usb_mode:=usb3 \
    confidence_threshold:=0.7 \
    publish_debug_images:=true

# Different model blob
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    blob_path:=yolov8n.blob \
    output_dir:=/home/uday/detections
```

### Visualization

```bash
# View debug images in RViz2
ros2 run rviz2 rviz2

# Or use rqt_image_view
ros2 run rqt_image_view rqt_image_view \
    /cotton_detection/debug_image
```

---

## Compatibility

### ROS1 Interface Mapping

| ROS1 Interface | ROS2 Equivalent | Notes |
|----------------|-----------------|-------|
| Signal: `SIGUSR1` | Service: `/cotton_detection/detect` | Trigger detection |
| File: `cotton_details.txt` | Topic: `/cotton_detection/results` | Detection output |
| File: `DetectionOutput.jpg` | Topic: `/cotton_detection/debug_image` | Annotated image |
| File: `output.pcd` | Topic: `/cotton_detection/pointcloud` | Point cloud |
| Python script call | ROS2 service call | Standard ROS2 pattern |

### Migration Path

- **Phase 1** (Current): File-based communication preserved
- **Phase 2** (Next): Direct DepthAI pipeline, remove files
- **Phase 3** (Future): Pure C++ with depthai-core

---

## Performance Expectations

### Phase 1 Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Detection Latency | <2 seconds | From service call to topic publish |
| Detection Accuracy | ±5cm at 1.0-1.5m | Spatial accuracy |
| Service Response Time | <0.5 seconds | Service call overhead |
| USB2 Stability | No dropouts | Multi-hour operation |

### Phase 2 Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Detection Latency | <200ms | Direct pipeline, no file I/O |
| RGB Stream Rate | 30 Hz | Continuous publishing |
| Depth Stream Rate | 30 Hz | Aligned to RGB |
| Continuous Detection | 15-30 Hz | Configurable |

---

## Validation Checklist

### Interface Validation
- [x] All topics defined with correct message types
- [x] All services defined with correct srv types
- [x] All parameters declared with types and defaults
- [x] Frame IDs follow REP-103 conventions
- [x] Coordinate systems documented

### Implementation Validation
- [x] Wrapper node implements all interfaces
- [x] Services return correct responses
- [x] Topics publish valid messages
- [x] Parameters are validated
- [x] Subprocess management implemented
- [x] Signal handlers implemented (SIGUSR1, SIGUSR2)
- [x] File I/O parsing implemented
- [x] Calibration service implemented
- [x] Simulation mode implemented
- [x] Process monitoring thread implemented
- [ ] Hardware testing (pending camera)

### Documentation Validation
- [x] All interfaces documented
- [x] Usage examples provided
- [x] Data flow diagram complete
- [x] Migration path clear
- [x] Compatibility matrix complete

---

## References

- **REP-103**: Standard Units of Measure and Coordinate Conventions
- **REP-105**: Coordinate Frames for Mobile Platforms
- **vision_msgs**: ROS2 vision message package
- **DepthAI Documentation**: https://docs.luxonis.com/
- **OAK-D Lite Datasheet**: https://docs.luxonis.com/projects/hardware/en/latest/pages/DM9095/

---

## Phase 1 Limitations and Caveats

### Known Limitations

1. **File I/O Overhead**: Detection latency includes file write/read operations (~100-200ms overhead)
2. **Hardcoded Paths**: CottonDetect.py uses hardcoded `/home/ubuntu/pragati/` paths (cannot be overridden via environment)
3. **Single Detection Mode**: Only triggered detection supported (no continuous mode)
4. **Subprocess Restart**: No automatic restart on crash (requires node restart)
5. **Signal Dependencies**: Relies on POSIX signals (Linux/Unix only, not Windows-compatible)
6. **File Format**: Legacy `636 0 x y z` format from ROS1 preserved
7. **No Camera Info**: Camera intrinsics not published (use calibration service to export)
8. **USB2 Only**: USB3 mode untested with long cables (stability concerns)

### Error Conditions

#### Startup Failures
- **Camera Not Found**: Process exits immediately with stderr containing "DepthAI device not found"
- **Blob File Missing**: Process exits with "YOLO blob not found" error
- **Permissions Error**: Cannot create output directories (falls back to /tmp)
- **SIGUSR2 Timeout**: Camera initialization exceeds 30 seconds (process terminated)

#### Runtime Failures
- **Detection Timeout**: No output file after 10 seconds (detection aborted, service returns failure)
- **Process Crash**: Monitor thread logs crash, service calls fail until node restart
- **File Parse Error**: Invalid format in cotton_details.txt (detection skipped, logged as warning)
- **Signal Error**: SIGUSR1 send failure (detection aborted)

#### Recovery Procedures
- **Camera Not Found**: Check USB connection, verify `lsusb` shows OAK-D device
- **Subprocess Crash**: Restart wrapper node with `ros2 launch`
- **Permission Denied**: Run node as correct user or adjust directory permissions
- **Timeout Errors**: Increase `detection_timeout` or `startup_timeout` parameters

### Migration from ROS1

**Breaking Changes from ROS1 Interface**:
- Signal triggering replaced with ROS2 service calls
- `cotton_details.txt` format unchanged but now internal implementation detail
- Topic types changed from custom msgs to `vision_msgs/Detection3DArray`
- Frame IDs follow REP-103 conventions (optical frames)
- File paths configurable via parameters (with fallback)

**Preserved from ROS1**:
- Core detection algorithm unchanged (CottonDetect.py)
- DepthAI pipeline configuration identical
- Spatial coordinate system unchanged
- Detection accuracy and performance equivalent

---

## Error Handling Specification

### Service Error Responses

#### `/cotton_detection/detect` Service

| Error Condition | `success` | `message` | `data` | Recovery |
|-----------------|-----------|-----------|--------|----------|
| Detection successful | `true` | "Detected N cottons" | Empty | - |
| Camera not initialized | `false` | "Camera not ready" | Empty | Wait for initialization |
| Detection timeout | `false` | "Detection timeout" | Empty | Retry or restart node |
| No detections found | `true` | "No cotton detected" | Empty | Normal (not an error) |
| Pipeline error | `false` | "Pipeline error: <details>" | Empty | Restart node |
| Invalid command | `false` | "Invalid detect_command" | Empty | Use valid command (1, 2) |

#### `/cotton_detection/calibrate` Service (detect_command=2)

| Error Condition | `success` | `message` | `data` | Recovery |
|-----------------|-----------|-----------|--------|----------|
| Calibration exported | `true` | Path to calibration files | ASCII path | - |
| Camera not available | `false` | "No DepthAI device" | Empty | Connect camera |
| Export failed | `false` | "Calibration export failed" | Empty | Check permissions |
| Script not found | `false` | "Calibration script missing" | Empty | Verify installation |

### State Machine

#### Cotton Detection Node States

```
┌─────────────────────────────────────────────────────────────┐
│                    Node State Machine                        │
│                                                              │
│  ┌────────────┐                                             │
│  │ UNINIT     │──────────► Node not yet started             │
│  └─────┬──────┘                                             │
│        │ on_configure()                                      │
│        ▼                                                     │
│  ┌────────────┐                                             │
│  │ CONFIGURING│──────────► Loading parameters               │
│  └─────┬──────┘            Initializing DepthAI             │
│        │ success                                             │
│        ▼                                                     │
│  ┌────────────┐                                             │
│  │ IDLE       │──────────► Ready for service calls          │
│  └─────┬──────┘                                             │
│        │ detect_command=1                                    │
│        ▼                                                     │
│  ┌────────────┐                                             │
│  │ DETECTING  │──────────► Processing frame                 │
│  └─────┬──────┘            Running inference                │
│        │ complete                                            │
│        ▼                                                     │
│  ┌────────────┐                                             │
│  │ PUBLISHING │──────────► Publishing results               │
│  └─────┬──────┘                                             │
│        │                                                     │
│        └───────────────────► Return to IDLE                 │
│                                                              │
│  Error States:                                               │
│  ┌────────────┐                                             │
│  │ ERROR      │──────────► Recoverable error                │
│  └────────────┘            Returns to IDLE on next call     │
│                                                              │
│  ┌────────────┐                                             │
│  │ FATAL      │──────────► Unrecoverable error              │
│  └────────────┘            Requires node restart            │
└─────────────────────────────────────────────────────────────┘
```

#### Valid State Transitions

| From State | To State | Trigger | Notes |
|------------|----------|---------|-------|
| UNINIT | CONFIGURING | `on_configure()` | Lifecycle transition |
| CONFIGURING | IDLE | Success | Camera initialized |
| CONFIGURING | FATAL | Failure | Camera not found |
| IDLE | DETECTING | Service call | `detect_command=1` |
| IDLE | IDLE | Service call | `detect_command=2` (calibration) |
| DETECTING | PUBLISHING | Complete | Detection finished |
| DETECTING | ERROR | Timeout | Detection timeout |
| PUBLISHING | IDLE | Complete | Results published |
| ERROR | IDLE | Recovery | Auto-recovery |
| ERROR | FATAL | Repeated errors | Max retries exceeded |

#### Service Call Preconditions

| Service | Required State | Error if Wrong State |
|---------|---------------|---------------------|
| `/cotton_detection/detect` | IDLE | "Node not ready" |
| `/cotton_detection/calibrate` | IDLE | "Node not ready" |

### Failure Modes and Recovery

#### Camera Failures

| Failure Mode | Detection | Impact | Auto-Recovery | Manual Recovery |
|--------------|-----------|--------|---------------|----------------|
| Camera disconnected | USB error | All detection fails | Yes (9s retry) | Reconnect USB |
| Camera overheat | Thermal monitor | Throttled FPS | Yes (auto-throttle) | Cool down |
| Pipeline crash | Exception | Single detection fails | Yes | - |
| Device busy | Init error | Startup fails | No | Kill other process |

#### Motor Control Failures

| Failure Mode | Detection | Impact | Auto-Recovery | Manual Recovery |
|--------------|-----------|--------|---------------|----------------|
| CAN timeout | No response | Command fails | Yes (3 retries) | Check wiring |
| Over-temperature | Temp monitor | E-stop triggered | No | Cool down + reset |
| Position error | Encoder mismatch | Movement stops | No | Recalibrate |
| Communication error | CRC fail | Command rejected | Yes (retry) | - |

#### System Failures

| Failure Mode | Detection | Impact | Auto-Recovery | Manual Recovery |
|--------------|-----------|--------|---------------|----------------|
| MQTT disconnect | Heartbeat timeout | Inter-arm comm fails | Yes (reconnect) | Check network |
| ROS2 node crash | Process monitor | Subsystem offline | No | Restart node |
| Memory exhaustion | OOM | Node killed | No | Restart system |
| GPIO error | Read failure | End effector fails | No | Check wiring |

### Error Codes

#### Detection Errors (1xx)

| Code | Name | Description | Recovery |
|------|------|-------------|----------|
| 100 | DET_SUCCESS | Detection successful | - |
| 101 | DET_NO_CAMERA | Camera not found | Connect camera |
| 102 | DET_TIMEOUT | Detection timeout | Retry |
| 103 | DET_PIPELINE_ERROR | DepthAI pipeline error | Restart node |
| 104 | DET_NO_RESULTS | No detections found | Normal |
| 105 | DET_INVALID_FRAME | Corrupted frame | Auto-retry |

#### Motor Errors (2xx)

| Code | Name | Description | Recovery |
|------|------|-------------|----------|
| 200 | MOT_SUCCESS | Command successful | - |
| 201 | MOT_CAN_TIMEOUT | CAN bus timeout | Check wiring |
| 202 | MOT_OVER_TEMP | Motor overheated | Cool down |
| 203 | MOT_OVER_VOLTAGE | Voltage too high | Check power |
| 204 | MOT_UNDER_VOLTAGE | Voltage too low | Charge battery |
| 205 | MOT_ENCODER_ERROR | Encoder fault | Recalibrate |
| 206 | MOT_LIMIT_EXCEEDED | Position/velocity limit | Check config |

#### Communication Errors (3xx)

| Code | Name | Description | Recovery |
|------|------|-------------|----------|
| 300 | COM_SUCCESS | Communication OK | - |
| 301 | COM_MQTT_DISCONNECT | MQTT broker lost | Auto-reconnect |
| 302 | COM_ROS_TIMEOUT | ROS service timeout | Retry |
| 303 | COM_NETWORK_ERROR | Network unreachable | Check WiFi |

### Diagnostic Topics

#### `/diagnostics` Message Format

```yaml
# diagnostic_msgs/DiagnosticArray
header:
  stamp: <current_time>
status:
  - level: 0  # OK=0, WARN=1, ERROR=2, STALE=3
    name: "cotton_detection: Camera Status"
    message: "Camera operational"
    hardware_id: "OAK-D-Lite-<serial>"
    values:
      - key: "temperature_c"
        value: "65.2"
      - key: "fps"
        value: "30"
      - key: "latency_ms"
        value: "70"
```

#### Diagnostic Levels

| Level | Value | Meaning | Action Required |
|-------|-------|---------|----------------|
| OK | 0 | Normal operation | None |
| WARN | 1 | Degraded performance | Monitor |
| ERROR | 2 | Component failure | Investigate |
| STALE | 3 | No recent data | Check connectivity |

---

**Document Version**: 2.1  
**Last Updated**: January 2026  
**Status**: ✅ Complete - Error Handling Added  
**Next Review**: After Phase 2 implementation
