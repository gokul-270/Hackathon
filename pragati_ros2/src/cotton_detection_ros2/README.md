# Cotton Detection ROS2 Package (C++ Primary)

**Last Updated:** 2026-03-12
**Status:** ✅ **PRODUCTION READY** - Hardware Validated + Service Latency Confirmed
**Validation:** Software [yes], Sim [yes], Bench [**COMPLETE Oct 30**], Extended [**Oct 31**], Service [**Nov 1**], Field [recommended]
**Hardware:** OAK-D Lite camera (DepthAI), USB 3.0 connection
**Primary Implementation:** C++ ROS2 node with DepthAI direct integration
**Performance:** **134ms avg service latency** (123-218ms range), neural detection ~130ms on Myriad X VPU
**Test Coverage:** 191 unit tests + hardware validation + sustained operation test + service latency testing

> **Note:** Message and service definitions (`DetectionResult`, `CottonPosition`, `PerformanceMetrics`, `CottonDetection`) have been moved to the **`cotton_detection_msgs`** package. Update your imports from `cotton_detection_ros2.msg` / `cotton_detection_ros2.srv` to `cotton_detection_msgs.msg` / `cotton_detection_msgs.srv`, and C++ includes from `cotton_detection_ros2/msg/` / `cotton_detection_ros2/srv/` to `cotton_detection_msgs/msg/` / `cotton_detection_msgs/srv/`.

## Reality Snapshot

### ✅ PRODUCTION READY (Nov 1, 2025)

**SERVICE LATENCY VALIDATION (Nov 1):**
- ✅ **Service Latency:** 134ms average (123-218ms range)
- ✅ **Neural Detection:** ~130ms on Myriad X VPU
- ✅ **Reliability:** 100% success rate (10/10 consecutive tests)
- ✅ **Test Method:** Persistent client eliminates ROS2 CLI overhead (~6s tool issue)
- ✅ **Production Status:** Service latency validated, exceeds <500ms target
- 📋 **Details:** See [SYSTEM_VALIDATION_SUMMARY_2025-11-01.md](../../docs/project-notes/SYSTEM_VALIDATION_SUMMARY_2025-11-01.md)

**CRITICAL BUG FIX (Oct 31):**
- ✅ **Fixed:** Deterministic hang after 15-16 detection requests
- ✅ **Root Cause:** Infinite blocking in DepthAI queue polling (replaced `get()` with `tryGet()` + timeout loop)
- ✅ **Validation:** 36 consecutive detections over 3 minutes, temperature 62-79°C, 100% success rate
- 📋 **Details:** See [BUGFIX_DEPTHAI_QUEUE_HANG_2025-10-31.md](../../docs/archive/2025-11-consolidation/bugfixes/BUGFIX_DEPTHAI_QUEUE_HANG_2025-10-31.md)

**Hardware Validation COMPLETE:**
- ✅ **Service Latency:** 134ms avg (was 7-8 seconds with Python wrapper) - **50-60x faster!**
- ✅ **Reliability:** 100% success rate (10/10 consecutive tests)
- ✅ **Spatial Accuracy:** ±10mm at 0.6m distance (exceeds ±20mm target)
- ✅ **Frame Rate:** 30 FPS sustained on Myriad X VPU
- ✅ **System Stability:** Zero crashes, memory leaks, or degradation

**Implementation:**
- ✅ C++ DepthAI direct integration (eliminates Python wrapper bottleneck)
- ✅ On-device YOLO inference on Intel Movidius Myriad X VPU
- ✅ Queue optimization: maxSize=4, blocking=true (eliminates errors)
- ✅ Detection mode: Auto-switches to DEPTHAI_DIRECT
- ✅ **191 unit tests** + hardware validation evidence

**Evidence:**
- Hardware Validation: `docs/archive/2025-11-consolidation/validation-reports/FINAL_VALIDATION_REPORT_2025-10-30.md`
- Bug Fix & Extended Test: `docs/archive/2025-11-consolidation/bugfixes/BUGFIX_DEPTHAI_QUEUE_HANG_2025-10-31.md`
- Service Latency Validation: `docs/project-notes/SYSTEM_VALIDATION_SUMMARY_2025-11-01.md`

See the [Status Tracker](../../docs/status/STATUS_TRACKER.md) for live accuracy tracking.

## When to Use Which Path?

| Use Case | Recommended Node | Launch Entry Point |
|----------|------------------|--------------------|
| Standard deployments, DepthAI neural detection | **C++ node (primary)** | `ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py` |
| Development without DepthAI hardware | **C++ node (simulation)** | `ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true` |

> **Note:** The Python wrapper (`cotton_detection_wrapper.launch.py`) is archived in `launch/archive/phase1/`. Use C++ node for all new work.

## Building & Enabling DepthAI

```bash
colcon build --packages-select cotton_detection_ros2 \
    --cmake-args -DHAS_DEPTHAI=ON
```

- `HAS_DEPTHAI=ON` is the default and required — the build will `FATAL_ERROR` if DepthAI is not found.
- Ensure DepthAI SDK dependencies are installed (see [Camera Integration Guide](../../docs/guides/CAMERA_INTEGRATION_GUIDE.md)).

## Launching the C++ Node

```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=true \
    params_file:=share/cotton_detection_ros2/config/production.yaml
```

### Key Parameters (`production.yaml`)

- `simulation_mode` (bool, default `false`)
- `use_depthai` (bool, default `true` when compiled with DepthAI)
- `detection_mode` (`depthai_direct` — only supported mode)
- `enable_debug_output` (bool, default `false`) — publishes debug overlay images
- `detection_confidence_threshold` (double, default `0.5`)
- `depthai.model_path` (string, defaults to `models/yolov112.blob` in package share)
- `depthai.num_classes` (int, `1` for YOLOv8, `2` for YOLOv11)

See [`config/production.yaml`](config/production.yaml) for the full matrix.

### Topics & Services (C++)

**Topics:**
- Publishes `cotton_detection_msgs/DetectionResult` on `/cotton_detection/results` (single message carrying array of cotton positions).
- Publishes optional debug overlay images on `/cotton_detection/debug_image`.
- Emits diagnostics via `/diagnostics` when enabled.

**Services:**
- `/cotton_detection/detect` - Main detection service (commands: 0=stop, 1=detect, 2=calibrate)
- `/cotton_detection/camera_control` - Camera power control for thermal management (std_srvs/SetBool)

### Camera Power Management (Thermal Control)

To reduce thermal load during idle periods, you can start/stop the camera:

```bash
# Stop camera (reduces heat during arm movement)
ros2 service call /cotton_detection/camera_control std_srvs/srv/SetBool "{data: false}"

# Start camera (before detection)
ros2 service call /cotton_detection/camera_control std_srvs/srv/SetBool "{data: true}"
```

**Typical workflow:**
1. Camera ON → Detection → Camera OFF
2. Arm movement (camera stays off)
3. Camera ON → Verification → Camera OFF

This reduces camera duty cycle from 100% to ~15%, significantly lowering thermal load.

### Current Limitations (C++)

- DepthAI runtime reconfiguration (confidence, ROI) still TODO (see `CameraManager` / `PipelineBuilder`).
- Calibration export available via C++ service (returns filesystem path encoded in response data).
- Extended duration testing (30+ minutes) recommended before production deployment.
- Field validation runs needed to confirm detection accuracy with actual cotton.

## Legacy Python Wrapper (Archived)

> **The Python wrapper has been archived.** Launch file is in `launch/archive/phase1/`.
> The wrapper scripts have been removed. All production and development work uses the C++ node.

Historical notes (for reference only):
- The wrapper used subprocess + file I/O + SIGUSR1/SIGUSR2 signal-based detection.
- It was replaced by the C++ node in Phase 2 (Oct 2025) for performance and reliability.

## Simulation & Testing

| Scenario | Command |
|----------|---------|
| Simulate detections w/out hardware | `ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true` |
| Manual detection trigger | `ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection "{detect_command: 1}"` |

Unit tests are located in `test/` and run via `colcon test --packages-select cotton_detection_ros2` (191 tests across 7 test files).

### Offline Testing

**Test without hardware using saved images!** See **[OFFLINE_TESTING.md](OFFLINE_TESTING.md)** for complete guide.

**Quick start:**
```bash
# Start detection node in simulation mode
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true

# Trigger a detection
ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection "{detect_command: 1}"
```

Offline testing enables:
- Development without OAK-D Lite camera
- Reproducible regression testing
- CI/CD integration
- Dataset benchmarking

## Integration Touchpoints

- Subscribed by `yanthra_move` at `src/yanthra_move/src/yanthra_move_system.cpp` (lines 340-382).
- Launch orchestration via `src/yanthra_move/launch/pragati_complete.launch.py` (use `cotton_detection_cpp.launch.py` include).
- Simulation toggles propagate from top-level launch through `use_depthai` + `simulation_mode` parameters.

---

## Migration from Python Wrapper

### Overview

This guide helps teams complete the migration from the **legacy Python wrapper** to the **production C++ implementation**.

#### Why Migrate?

**Benefits of C++ Implementation:**
- ✅ **Production Default**: `cotton_detection_node` is the shipping configuration (Oct 2025)
- ✅ **Better Performance**: No subprocess/file I/O bottlenecks
- ✅ **DepthAI Enablement**: Native pipeline with `-DHAS_DEPTHAI=ON`
- ✅ **Enhanced Features**: Parameter validation, diagnostics, simulation hooks
- ✅ **Continuous Detection**: Supports depthai_direct streaming mode
- ✅ **Improved Reliability**: Graceful error handling and QoS-aware publishing

**Deprecation Notice:**
> ⚠️ The Python wrapper (`cotton_detect_ros2_wrapper.py`) has been archived. The C++ node is the sole production implementation. See `launch/archive/phase1/` for the historical wrapper launch file.

### Migration Timeline

| Phase | Status (Oct 2025) | Description |
|-------|------------------|-------------|
| **Phase 1** | ✅ Completed | Python wrapper foundation (legacy) - retained for legacy automation |
| **Phase 2** | ✅ Completed | C++ node operational - default launch path |
| **Phase 3** | 🔄 Ongoing | DepthAI runtime parity & lifecycle hardening |
| **Phase 4** | 📋 Planned | Wrapper deprecation & doc sunset |
| **Phase 5** | 📋 Planned | Wrapper removal |

**Action Today:** Treat C++ node as required baseline; limit wrapper usage to legacy automation or contingency cases.

### Key Architecture Differences

**Python Wrapper (Phase 1):**
```
ROS2 Wrapper Node → subprocess → CottonDetect.py → SIGUSR1/SIGUSR2 signals
                                              → File I/O (cotton_details.txt)
                                              → Parse file → Publish to topic
```

**C++ Node (Current — post-decomposition):**
```
ROS2 C++ Node → Image Subscriber (/camera/image_raw)
             → YOLO Neural Detection (YOLOv8/v11 on Myriad X VPU)
             → CameraManager (camera lifecycle, restart logic)
                 ├── PipelineBuilder (DepthAI pipeline construction)
                 ├── DeviceConnection (USB connection, boot/crash detection)
                 ├── ThermalGuard (thermal monitoring & throttling)
                 └── DiagnosticsCollector (health metrics aggregation)
             → Direct topic publishing
```

**Source File Layout:**

| File | Role |
|------|------|
| `cotton_detection_node.cpp` | Node constructor/destructor, callbacks, publishing |
| `cotton_detection_node_init.cpp` | Interface initialization, component wiring |
| `cotton_detection_node_parameters.cpp` | Parameter declaration, loading, validation |
| `cotton_detection_node_main.cpp` | Entry point, executor setup |
| `detection_engine.cpp/.hpp` | Detection orchestration, DepthAI inference, caching, image save/draw |
| `service_handler.cpp/.hpp` | ROS2 service request processing, calibration, camera control |
| `camera_manager.cpp/.hpp` | Camera lifecycle state machine, restart logic |
| `device_connection.cpp/.hpp` | USB connection, boot/crash detection, reconnection |
| `thermal_guard.cpp/.hpp` | Thermal monitoring, throttle decisions |
| `diagnostics_collector.cpp/.hpp` | Health metrics aggregation |
| `pipeline_builder.cpp/.hpp` | DepthAI pipeline construction |
| `performance_monitor.cpp/.hpp` | Latency tracking, percentile stats |
| `async_image_saver.cpp/.hpp` | Non-blocking background image I/O |

**Communication Changes:**

| Aspect | Python Wrapper | C++ Node |
|--------|---------------|----------|
| **Detection Trigger** | Signal-based (SIGUSR1) | Image callback |
| **Result Output** | File I/O parsing | Direct in-memory |
| **Camera Integration** | Subprocess script | Modular DepthAI C++ classes (CameraManager, DeviceConnection, PipelineBuilder) |
| **Detection Mode** | Trigger-on-demand | Continuous stream |
| **Configuration** | Launch args | ROS2 parameters |

### Step-by-Step Migration

#### Step 1: Verify Prerequisites

```bash
# Check C++ node builds successfully
cd ~/pragati_ros2
colcon build --packages-select cotton_detection_ros2

# Verify dependencies
ros2 pkg list | grep cotton_detection_ros2
ros2 interface list | grep cotton_detection
```

#### Step 2: Test in Simulation Mode

```bash
# Test C++ node without hardware
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true \
    use_depthai:=false

# Verify simulation output
ros2 topic echo /cotton_detection/results
```

#### Step 3: Update Launch Files

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

#### Step 4: Update Configuration

See `config/production.yaml` for complete configuration options. Key parameters:
- `simulation_mode` - Enable/disable simulation
- `detection_mode` - Only `depthai_direct` is supported
- `depthai.enable` - Enable DepthAI pipeline
- `enable_debug_output` - Debug image visualization

#### Step 5: Test with Hardware

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

### Parameter Mapping

| Python Wrapper Parameter | C++ Node Parameter | Notes |
|-------------------------|-------------------|-------|
| `simulation_mode` | `simulation_mode` | Same |
| `confidence_threshold` | `detection_confidence_threshold` | More specific naming |
| `blob_path` | `depthai.model_path` | Now in depthai namespace |
| `output_dir` | *(removed)* | No longer needed (no file I/O) |
| `input_dir` | *(removed)* | No longer needed (no file I/O) |
| `publish_debug_image` | `enable_debug_output` | Renamed |

### Code Migration Examples

**Topic Subscription (Interface Changed):**

```python
# Before (Python wrapper)
from cotton_detection_msgs.msg import Detection3DArray

def callback(msg):
    for detection in msg.detections:
        print(f"Cotton at: {detection.position}")

subscription = node.create_subscription(
    Detection3DArray,
    '/cotton_detection/results',
    callback, 10
)

# After (C++ node)
from cotton_detection_msgs.msg import DetectionResult

def callback(msg):
    for detection in msg.detections:
        print(f"Cotton at: {detection.position}")
        print(f"Confidence: {detection.confidence}")  # New field!

subscription = node.create_subscription(
    DetectionResult,
    '/cotton_detection/results',
    callback, 10
)
```

**TF Frame Names:**

| Python Wrapper | C++ Node |
|---------------|----------|
| `oak_camera_link` | `camera_link` |
| `oak_rgb_camera_optical_frame` | `camera_optical_frame` |

### Troubleshooting Migration Issues

**No detections in C++ node but Python wrapper works:**
```bash
# Check camera topic
ros2 topic list | grep camera

# Verify image encoding
ros2 topic echo /camera/image_raw --field encoding

# Check detection confidence threshold
ros2 param get /cotton_detection_node detection_confidence_threshold
```

**Parameter validation failed:**
```bash
# Check parameter validity
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args --log-level info

# Use test config to identify bad parameters
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    config_file:=/path/to/test_config.yaml
```

**DepthAI initialization failed:**
```bash
# Test DepthAI connectivity
python3 -c "import depthai as dai; print(dai.Device.getAllAvailableDevices())"

# Check USB mode
lsusb | grep 03e7

# Verify model path exists
ros2 pkg prefix cotton_detection_ros2 && ls -lh $(ros2 pkg prefix cotton_detection_ros2)/share/cotton_detection_ros2/models/
```

### Rollback Plan

If you encounter critical issues, restart the node or use simulation mode:

```bash
# Kill and restart in simulation mode
ros2 service call /cotton_detection/camera_control std_srvs/srv/SetBool "{data: false}"
# Or restart with simulation
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true
```

For detailed migration history and complete examples, see archived `docs/archive/2025-10/cotton_detection/MIGRATION_GUIDE.md`.

---

## Documentation Map

### Current Documentation
- **[OFFLINE_TESTING.md](OFFLINE_TESTING.md)** — Test without hardware using saved images
- **[../../docs/CONSOLIDATED_ROADMAP.md](../../docs/CONSOLIDATED_ROADMAP.md)** — Project-wide roadmap
- **[../../docs/project-notes/ARM_NODE_REFACTORING_ROADMAP_2026-03-10.md](../../docs/project-notes/ARM_NODE_REFACTORING_ROADMAP_2026-03-10.md)** — Arm node refactoring plan
- **[../../docs/status/STATUS_TRACKER.md](../../docs/status/STATUS_TRACKER.md)** — Project status tracking
- **[../../docs/ROS2_INTERFACE_SPECIFICATION.md](../../docs/ROS2_INTERFACE_SPECIFICATION.md)** — Complete interface reference

### Hardware & Setup
- **[../../docs/guides/CAMERA_INTEGRATION_GUIDE.md](../../docs/guides/CAMERA_INTEGRATION_GUIDE.md)** — Camera setup and hardware enablement guide

### Historical
- **[../../docs/archive/2025-10/cotton_detection/](../../docs/archive/2025-10/cotton_detection/)** — Archived migration docs

## Outstanding Work

**Hardware Validation (Priority: HIGH):**
- Validate calibration export on hardware
- Capture real hardware validation logs (DepthAI field tests)
- Test spatial coordinate extraction with OAK-D Lite
- Performance benchmarking with actual cotton samples

**Software Enhancements (Priority: MEDIUM):**
- ~~Decompose DepthAIManager into focused classes~~ **Done** (Mar 2026 — CameraManager, DeviceConnection, ThermalGuard, DiagnosticsCollector, PipelineBuilder)
- Implement runtime reconfiguration in PipelineBuilder (confidence, ROI, FPS) with pipeline rebuild via CameraManager
- Complete lifecycle node implementation (Step 7)
- ~~Fix signal handler safety~~ **Done** — uses `pragati::install_signal_handlers()` atomic flag pattern (Step 8)
- Consolidate partial-class file split into per-component files (Step 9)
- Expand unit test coverage for decomposed classes
- Add integration tests with Yanthra system

**See [ARM_NODE_REFACTORING_ROADMAP](../../docs/project-notes/ARM_NODE_REFACTORING_ROADMAP_2026-03-10.md) Steps 7-9 for remaining cotton detection improvements.**

## License

Proprietary


## FAQ (Quick Reference)

### Q: Getting 'No camera found' errors?
A:
1. Check USB connection: `lsusb | grep Intel` (should show OAK-D device)
2. Verify DepthAI permissions: `sudo udevadm control --reload-rules`
3. Try simulation mode: `use_depthai:=false simulation_mode:=true`
4. Check USB3 connection (USB2 may have bandwidth issues)

### Q: Detection accuracy is poor?
A:
- Lighting conditions: Cotton detection works best in bright, even lighting
- Camera calibration: Run calibration service if not done recently
- Confidence threshold: Adjust `detection_confidence_threshold` parameter (default 0.5)
- Distance: OAK-D Lite depth accuracy is 0.5-5m range

### Q: Should I use C++ node or Python wrapper?
A: **Use C++ node** (`cotton_detection_cpp.launch.py`) - it's the production default. Only use Python wrapper for legacy automation scripts.

### Q: How do I test without camera hardware?
A: Use simulation mode:
```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true
```
See OFFLINE_TESTING.md for details.

### Q: Debug images not publishing?
A: Enable in launch or config: `enable_debug_output: true` and check topic: `ros2 topic echo /cotton_detection/debug_image/compressed`

### Q: What detection mode does this node use?
A:
- **depthai_direct**: YOLO neural detection running on the OAK-D Lite's Myriad X VPU. This is the only supported mode.
- Models: YOLOv8 (1-class) or YOLOv11 (2-class: cotton + not_pickable). Configured via `depthai.num_classes`.
- HSV detection was a legacy approach and has been removed.

### Q: Getting DepthAI build errors?
A: Ensure DepthAI SDK is installed:
```bash
pip3 install depthai
# DepthAI is required — the build will fail without it.
# At runtime, use simulation_mode:=true to test without camera hardware.
```

### Q: How to improve detection speed?
A:
- Detection runs on the Myriad X VPU (~130ms per frame) — this is hardware-limited
- Lower YOLO confidence threshold to reduce NMS post-processing
- Reduce image resolution in camera config
- Use `depthai.auto_pause_after_detection` to reduce thermal throttling

**More FAQ:** See main FAQ.md in docs/guides/ for system-wide questions.

