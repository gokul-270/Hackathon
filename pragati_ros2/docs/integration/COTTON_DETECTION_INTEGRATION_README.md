# Cotton Detection ROS2 Integration

## Overview

This document describes the **modern ROS2 topic-based cotton detection integration** for the Yanthra robotic arm system.

## Architecture

### Data Flow
```
cotton_detection_ros2 Node
    ↓ publishes to
/cotton_detection/results (DetectionResult message)
    ↓ subscribes
YanthraMoveSystem
    ↓ buffers (thread-safe)
Cotton Position Provider (callback)
    ↓ injects
MotionController
    ↓ consumes
executeOperationalCycle()
```

## Quick Start

### Launch Complete System (Recommended)

**Simulation Mode (Testing):**
```bash
# Single-cycle simulation (default)
ros2 launch yanthra_move pragati_complete.launch.py

# Continuous operation simulation
ros2 launch yanthra_move pragati_complete.launch.py continuous_operation:=true
```

**Hardware Mode (Production):**
```bash
# Single-cycle with hardware
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false

# Continuous operation with hardware
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true

# Hardware mode without ARM client
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false enable_arm_client:=false

# Custom MQTT broker
ros2 launch yanthra_move pragati_complete.launch.py mqtt_address:=192.168.1.100

# Continuous with infinite runtime (testing/development)
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true max_runtime_minutes:=-1

# Custom timeout (e.g., 2 hours)
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true max_runtime_minutes:=120

# Skip start switch for automated testing/CI
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false start_switch.enable_wait:=false
```

**Launch Parameters:**

*Operation Mode:*
- `use_simulation` - Use simulation mode instead of hardware (default: `true`)
- `continuous_operation` - Enable continuous operation (default: `false` = single cycle)
- `max_runtime_minutes` - Safety timeout in minutes (default: `0` = auto, `-1` = infinite)
  - `0` = Auto timeout (1min single-cycle, 30min continuous)
  - `-1` = Infinite (no timeout, for testing only)
  - `>0` = Custom timeout in minutes

*Start Switch Configuration:*
- `start_switch.enable_wait` - Wait for physical start switch (default: `true`, disable for CI/testing)
- `start_switch.timeout_sec` - Start switch timeout in seconds (default: `5.0`)
- `start_switch.prefer_topic` - Use ROS topic over GPIO (default: `true`)

*System Configuration:*
- `enable_arm_client` - Enable ARM MQTT bridge (default: `true`)
- `mqtt_address` - MQTT broker IP address (default: `10.42.0.10`)
- `use_sim_time` - Use Gazebo simulation clock (default: `false`)
- `output_log` - Log output: `screen` or `log` (default: `screen`)

### Launch Cotton Detection Standalone (Optional)

If you need to run cotton detection separately:

```bash
# Camera mode (live detection)
ros2 run cotton_detection_ros2 cotton_detection_node

# Offline mode (trigger via service)
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args -p offline_mode:=true

# Trigger detection manually
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

### Monitor Detection Results
```bash
# View live detection messages
ros2 topic echo /cotton_detection/results

# Check detection rate
ros2 topic hz /cotton_detection/results

# View single message
ros2 topic echo /cotton_detection/results --once
```

## Parameters

### YanthraMoveSystem Parameters

**Launch File Parameters (pragati_complete.launch.py):**
- `use_simulation` (bool) - Enable simulation mode (default: `true`)
- `continuous_operation` (bool) - Enable continuous operation loop (default: `false`)
- `enable_arm_client` (bool) - Launch ARM MQTT bridge (default: `true`)
- `mqtt_address` (string) - MQTT broker IP (default: `10.42.0.10`)
- `use_sim_time` (bool) - Use simulation clock (default: `false`)
- `output_log` (string) - Output: `screen` or `log` (default: `screen`)

All existing yanthra_move runtime parameters remain unchanged. Cotton detection integration is automatic via topic subscription.

### Cotton Detection Node Parameters

**Runtime Parameters:**
- `offline_mode` (bool) - Disable camera, use service triggers only (default: `false`)
- `camera_topic` (string) - Image source topic (default: `/camera/image_raw`)
- `detection_confidence_threshold` (float) - Minimum confidence 0.0-1.0 (default: `0.7`)
- `max_cotton_detections` (int) - Maximum detections per frame (default: `50`)
- `enable_debug_output` (bool) - Publish debug images (default: `false`)
- `detection_mode` (string) - Algorithm: `depthai_direct` (default), `hsv_only`, `yolo_only`, `hybrid_fallback`

**Performance Parameters:**
- `performance.verbose_timing` (bool) - Show detailed timing breakdown (default: `false`)
- `depthai.flush_before_read` (bool) - Use old flush+sleep behavior vs smart drain (default: `false`)
- `depthai.max_queue_drain` (int) - Max frames to drain for freshness (default: `10`)
- `depthai.warmup_seconds` (int) - Pipeline warm-up time (default: `3`)
- `save_input_image` (bool) - Save raw camera frames (default: `false`)
- `save_output_image` (bool) - Save annotated detections (default: `false`)

**Usage Examples:**
```bash
# Camera mode (default)
ros2 run cotton_detection_ros2 cotton_detection_node

# Offline mode (service-triggered only)
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args -p offline_mode:=true

# Custom camera topic
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args -p camera_topic:=/usb_cam/image_raw

# Lower confidence threshold
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args -p detection_confidence_threshold:=0.5

# Enable debug output
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args -p enable_debug_output:=true
```

See `cotton_detection_ros2/config/cotton_detection_params.yaml` for full configuration list.

## Topic Interface

### `/cotton_detection/results`
**Type:** `cotton_detection_ros2/msg/DetectionResult`

**QoS:**
- Reliability: Reliable
- History: KeepLast(10)
- Durability: Volatile

**Message Structure:**
```
std_msgs/Header header
CottonPosition[] positions  # Array of detected cotton positions
int32 total_count           # Number of detections
bool detection_successful   # Detection status
float64 processing_time_ms  # Processing duration
```

**CottonPosition Structure:**
```
std_msgs/Header header
geometry_msgs/Point position  # 3D position (x, y, z)
float32 confidence            # Detection confidence (0.0-1.0)
int32 detection_id            # Unique detection ID
```

## Service Interface (Optional)

### `/cotton_detection/detect`
**Type:** `cotton_detection_ros2/srv/CottonDetection`

Manually trigger detection. Results are published to `/cotton_detection/results` topic automatically.

```bash
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect: 1}"
```

## Breaking Changes

### Removed Components
1. **File-based detection**: `get_cotton_coordinates()` stub removed
2. **Service client**: `robust_cotton_detection_client.cpp` archived  
3. **Bridge script**: `cotton_detection_bridge.py` deprecated

### Migration Guide

**Old Approach:**
```cpp
// Legacy file-based detection
std::vector<geometry_msgs::msg::Point> positions;
get_cotton_coordinates(&positions);
```

**New Approach:**
```cpp
// Modern provider callback
auto provider = system->getCottonPositionProvider();
auto positions_opt = provider();
if (positions_opt) {
    auto positions = positions_opt.value();
    // Use positions...
}
```

## Troubleshooting

### No Detections Received
```bash
# Check if cotton_detection_ros2 is running
ros2 node list | grep cotton_detection

# Check topic publication
ros2 topic hz /cotton_detection/results

# Check for messages
ros2 topic echo /cotton_detection/results --once
```

### Build Issues
```bash
# Clean build
rm -rf build/ install/ log/
colcon build --packages-select cotton_detection_ros2 yanthra_move

# Source workspace
source install/setup.bash
```

### QoS Mismatch
If yanthra_move can't receive messages, check QoS compatibility:
```bash
ros2 topic info /cotton_detection/results --verbose
```

Both publisher and subscriber must use Reliable reliability.

## Development

### Add Custom Detection Logic
Modify `cotton_detection_ros2/src/cotton_detection_node.cpp`:
- `detect_cotton_in_image()`: Detection algorithm
- `publish_detection_result()`: Result publishing

### Access Detections in Custom Tools
```cpp
// Get reference to YanthraMoveSystem
auto cotton_provider = yanthra_system->getCottonPositionProvider();

// Get latest positions
auto positions = cotton_provider();
if (positions.has_value()) {
    for (const auto& pos : positions.value()) {
        // Process position...
    }
}
```

## Testing

### Unit Tests
```bash
colcon test --packages-select cotton_detection_ros2 yanthra_move
colcon test-result --verbose
```

### Integration Test
```bash
# Terminal 1: Launch cotton detection
ros2 launch cotton_detection_ros2 cotton_detection.launch.py

# Terminal 2: Publish test image
ros2 run image_publisher image_publisher_node <test_image.jpg>

# Terminal 3: Monitor results
ros2 topic echo /cotton_detection/results

# Terminal 4: Launch yanthra_move  
ros2 launch yanthra_move yanthra_move.launch.py
```

## Performance

### Expected Performance (Validated on RPi + OAK-D Lite)
- **Detection Latency**: 70ms (pure detection, no image saving)
- **Detection Rate**: ~14 Hz (70ms per detection)
- **With Image Saving**: 114ms total (70ms detection + 44ms I/O)
- **Throughput**: Reliable delivery, no message loss
- **Hardware**: Raspberry Pi 4 with OAK-D Lite camera
- **Confidence**: 0.79 typical @ 0.46m depth

### Monitor Performance
```bash
# Topic statistics
ros2 topic hz /cotton_detection/results
ros2 topic bw /cotton_detection/results

# Node CPU/memory
top -p $(pgrep -f cotton_detection_node)
```

## References

- [ROS2 QoS Settings](https://docs.ros.org/en/humble/Concepts/About-Quality-of-Service-Settings.html)
- [ROS2 Topics](https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics/Understanding-ROS2-Topics.html)
- Cotton Detection Messages: `cotton_detection_ros2/msg/`

## Support

For issues, questions, or contributions:
- Check existing documentation
- Review code comments  
- Contact: System Architect

---

## APPENDIX A: Implementation History

### Integration Completion Status

**Date:** 2025-11-04 (Updated)  
**Status:** 🟢 **ALL TASKS COMPLETE** (15/15) + **REFACTORING COMPLETE**  
**Build:** ✅ **SUCCESS** (11.2s PC, 4m 33s RPi)  
**Performance:** ✅ **VALIDATED** (70ms detection @ RPi)

### Major Milestones

#### Phase 1: Core Architecture (Complete ✅)
- Topic-based publisher-subscriber architecture
- Single subscription locus in YanthraMoveSystem
- Thread-safe buffer with mutex protection
- Dependency injection via provider callback
- QoS: Reliable, KeepLast(10), Volatile

#### Phase 2: Legacy Code Removal (Complete ✅)
- Removed file-based detection (`get_cotton_coordinates()`)
- Archived service client (`robust_cotton_detection_client.cpp`)
- Deprecated bridge script (`cotton_detection_bridge.py`)
- Cleaned up CMakeLists.txt references

#### Phase 3: Node Refactoring (Complete ✅ - Nov 2024)
- Fixed RPi OOM build errors (now 4m 33s with -j2)
- Performance optimization: 70ms detection (58% faster)
- Split 2,189 lines → 5 modular files
- Added 13 major improvements (caching, runtime config, bug fixes)
- Validated on RPi 4 + OAK-D Lite

### Implementation Details

#### Data Flow Architecture
```
┌─────────────────────────────┐
│  cotton_detection_ros2      │
│  Node                        │
└──────────┬──────────────────┘
           │ publishes
           ↓
┌─────────────────────────────┐
│ /cotton_detection/results   │
│ Topic (DetectionResult msg) │
│ QoS: Reliable, KeepLast(10) │
└──────────┬──────────────────┘
           │ subscribes
           ↓
┌─────────────────────────────┐
│  YanthraMoveSystem          │
│  - initializeCottonDetection│
│  - Thread-safe buffer       │
│  - getCottonPositionProvider│
└──────────┬──────────────────┘
           │ provider callback
           ↓
┌─────────────────────────────┐
│  MotionController           │
│  - executeOperationalCycle  │
│  - cotton_position_provider_│
└─────────────────────────────┘
```

#### Key Design Principles

1. **Separation of Concerns**
   - YanthraMoveSystem: ROS2 I/O layer (owns subscription)
   - MotionController: Logic layer (ROS2-agnostic, testable)

2. **Dependency Injection**
   - MotionController receives data via `std::function` callback
   - No direct ROS2 dependencies in motion logic

3. **Thread Safety**
   - All detection data access protected by `std::mutex`
   - Type-erased storage to avoid header pollution

4. **Graceful Degradation**
   - Returns `std::optional` - empty when no data available
   - MotionController handles missing data gracefully

### Code Changes Summary

#### Modified Files
1. **`yanthra_move/src/yanthra_move_system.cpp`**
   - Added `initializeCottonDetection()` - subscription setup
   - Added `getCottonPositionProvider()` - dependency injection
   - Added `getLatestCottonPositions()` - thread-safe access
   - Removed `get_cotton_coordinates()` file stub

2. **`yanthra_move/src/core/motion_controller.cpp`**
   - Updated `initialize()` to accept provider callback
   - Updated `executeOperationalCycle()` to use provider
   - Removed extern declarations for legacy functions

3. **`cotton_detection_ros2/src/cotton_detection_node.cpp`**
   - Set explicit Reliable QoS
   - Confirmed `publish_detection_result()` after all detections

4. **`cotton_detection_ros2/CMakeLists.txt`**
   - Removed bridge from install targets

#### Archived Files
1. `yanthra_move/deprecated/robust_cotton_detection_client.cpp`
2. `cotton_detection_ros2/deprecated/cotton_detection_bridge.py`

### Build Verification

**PC Build:**
```bash
Starting >>> cotton_detection_ros2
Finished <<< cotton_detection_ros2 [6.66s]
Starting >>> yanthra_move
Finished <<< yanthra_move [3.40s]

Summary: 2 packages finished [11.2s]
```

**RPi Build:**
- Build time: 4m 33s (with -j2)
- No OOM errors (fixed via file splitting)
- Clean build, no warnings

### Performance Validation

**RPi 4 + OAK-D Lite Results:**
- Detection Latency: **70ms** (pure detection)
- Detection Rate: **~14 Hz**
- With Image Saving: 114ms total (70ms + 44ms I/O)
- Confidence: 0.79 @ 0.46m depth
- Reliability: 100% (no message loss)

**Performance Improvements:**
- Smart queue draining vs old flush+sleep: **58% faster** (70ms vs 120ms)
- Fixed frame flushing race condition
- Added result caching (100ms validity window)
- Runtime performance parameter tuning

### Migration Notes

#### Breaking Changes

1. **File-Based Detection Removed**
   ```cpp
   // OLD (deprecated)
   std::vector<geometry_msgs::msg::Point> positions;
   get_cotton_coordinates(&positions);
   
   // NEW (current)
   auto provider = system->getCottonPositionProvider();
   auto positions_opt = provider();
   if (positions_opt) {
       auto positions = positions_opt.value();
       // Use positions...
   }
   ```

2. **Service Client Removed**
   - Old: `robust_cotton_detection_client.cpp`
   - New: Subscribe to `/cotton_detection/results` topic

3. **Bridge Script Deprecated**
   - Old: `cotton_detection_bridge.py`
   - New: Direct ROS2 topic integration

#### Tools Requiring Updates

The following tools still use legacy service-based integration:
- `yanthra_move_aruco_detect.cpp`
- `yanthra_move_calibrate.cpp`

**Recommended Migration:**
Update these tools to subscribe to `/cotton_detection/results` topic instead of calling services.

### Success Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Tasks Completed | 15/15 | 15/15 | ✅ |
| Build Success | Yes | Yes (PC + RPi) | ✅ |
| Build Time PC | <60s | 11.2s | ✅ |
| Build Time RPi | <10m | 4m 33s | ✅ |
| Compilation Errors | 0 | 0 | ✅ |
| Detection Latency | ~100ms | 70ms | ✅ |
| Detection Rate | 10+ Hz | ~14 Hz | ✅ |
| Documentation | 3+ docs | 4 docs | ✅ |

### Known Limitations

1. **QoS Durability**
   - Current: Volatile (late-joining subscribers miss previous messages)
   - Consider: TransientLocal if last detection needed on late join

2. **No Timeout Warnings**
   - Should add warnings if no detections received for X seconds
   - Helps with operational visibility

3. **Testing Infrastructure**
   - No automated integration tests yet
   - Manual testing required for validation

---

## APPENDIX B: Node Refactoring Details (Nov 2024)

### Problem Statement

**OOM Build Failure on RPi:**
- Original cotton_detection_node.cpp: 2,189 lines
- Heavy includes in header: opencv.hpp, depthai.hpp
- RPi 4 (4GB RAM) OOM during compilation with -j2

**Performance Issues:**
- Frame flushing race condition
- Old flush+sleep approach: ~120ms
- Needed optimization to match ROS1 baseline

### Solution Architecture

**File Splitting Strategy:**
```
cotton_detection_node.cpp (2,189 lines)
    ↓ split into 5 files
├── cotton_detection_node.cpp (1,053 lines) - Main node logic
├── cotton_detection_parameters.cpp (585 lines) - Parameter management
├── cotton_detection_init.cpp (170 lines) - Initialization
├── cotton_detection_callbacks.cpp (126 lines) - ROS callbacks
└── cotton_detection_services.cpp (317 lines) - Service handlers
```

**Benefits:**
- Reduced per-file memory footprint
- Parallel compilation viable
- Better code organization
- Moved heavy includes from .hpp to .cpp

### Performance Optimizations

#### 1. Smart Queue Draining
```cpp
// OLD: Flush + sleep (race condition prone)
queue->removeMessage();  // Flush once
std::this_thread::sleep_for(50ms);  // Hope for fresh frame
auto frame = queue->get<Frame>();  // 120ms total

// NEW: Smart drain (configurable)
auto max_drain = node->get_parameter("depthai.max_queue_drain").as_int();
int drained = 0;
while (queue->has<Frame>() && drained < max_drain) {
    queue->get<Frame>();  // Drain stale frames
    drained++;
}
auto frame = queue->get<Frame>();  // 70ms total (58% faster)
```

#### 2. Result Caching
```cpp
// Cache detection results for 100ms validity window
if (cache_valid && (now - last_detection_time_) < 100ms) {
    return cached_result_;  // Avoid redundant processing
}
```

#### 3. Runtime Performance Parameters
- `performance.verbose_timing` - Detailed timing breakdown
- `depthai.flush_before_read` - Toggle old/new flushing
- `depthai.max_queue_drain` - Configurable drain depth
- `depthai.warmup_seconds` - Pipeline warm-up time

### New Features

1. **Runtime Detection Mode Switching**
   - `depthai_direct` (default)
   - `hsv_only`
   - `yolo_only`
   - `hybrid_fallback`

2. **Position Validation**
   - Workspace bounds checking
   - Invalid coordinate filtering

3. **Enhanced Error Handling**
   - Documented error handling strategy
   - Graceful degradation paths

4. **Bug Fixes**
   - NMS safety bug (division by zero)
   - Frame flushing race condition
   - Memory management improvements

### Validation Results

**Test Environment:**
- Hardware: Raspberry Pi 4 (4GB RAM)
- Camera: OAK-D Lite
- Distance: 0.46m
- Image: 640×480

**Performance Metrics:**
```
Detection Latency: 70ms
├── YOLO inference: ~40ms
├── Depth processing: ~20ms
└── 3D coordinate transform: ~10ms

Detection Rate: ~14 Hz (70ms per detection)
With Image Saving: 114ms (70ms + 44ms I/O)
```

**Quality Metrics:**
- Confidence: 0.79 (threshold: 0.7)
- Depth: 0.46m
- Position: Valid 3D coordinates
- Reliability: 100% (10/10 tests)

### Code Quality Improvements

**Before:**
- 1 file: 2,189 lines (monolithic)
- Magic numbers hardcoded
- Heavy includes in header
- No parameter extraction

**After:**
- 5 files: Modular organization
- Parameters extracted (585-line dedicated file)
- Heavy includes moved to .cpp
- Clear separation of concerns

**Documentation:**
- Added inline comments explaining design decisions
- Documented error handling strategy
- Created parameter reference guide
- Added performance tuning guide

---

## APPENDIX C: Testing Procedures

### Build Testing

**Clean Build (PC):**
```bash
cd /home/uday/Downloads/pragati_ros2
rm -rf build/ install/ log/
colcon build --packages-select cotton_detection_ros2 yanthra_move
source install/setup.bash
```

**Clean Build (RPi):**
```bash
# Use -j2 to avoid OOM
colcon build --packages-select cotton_detection_ros2 yanthra_move \
  --parallel-workers 2 \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
```

### Runtime Testing

**Test 1: Basic Functionality**
```bash
# Terminal 1: Launch cotton detection
ros2 launch cotton_detection_ros2 cotton_detection.launch.py

# Terminal 2: Monitor results
ros2 topic echo /cotton_detection/results

# Terminal 3: Launch yanthra_move
ros2 launch yanthra_move pragati_complete.launch.py

# Verify detections flow through system
```

**Test 2: Service Trigger**
```bash
# Trigger manual detection
ros2 service call /cotton_detection/detect \
  cotton_detection_ros2/srv/CottonDetection "{detect: 1}"

# Verify result published to topic
ros2 topic echo /cotton_detection/results --once
```

**Test 3: Performance Monitoring**
```bash
# Topic statistics
ros2 topic hz /cotton_detection/results  # Expect ~14 Hz
ros2 topic bw /cotton_detection/results  # Bandwidth usage

# Node resources
top -p $(pgrep -f cotton_detection_node)
```

**Test 4: QoS Validation**
```bash
# Check QoS settings
ros2 topic info /cotton_detection/results --verbose

# Should show:
# - Reliability: RELIABLE
# - History: KEEP_LAST (depth: 10)
# - Durability: VOLATILE
```

**Test 5: Late-Join Behavior**
```bash
# Start cotton detection first
ros2 launch cotton_detection_ros2 cotton_detection.launch.py

# Wait 5 seconds, then start yanthra_move
sleep 5
ros2 launch yanthra_move pragati_complete.launch.py

# Verify yanthra_move receives new detections
# (won't receive pre-start detections due to Volatile durability)
```

### Integration Testing

**Full System Test:**
```bash
# Single-cycle simulation
ros2 launch yanthra_move pragati_complete.launch.py

# Verify:
# 1. Cotton detection node starts
# 2. Detections published to topic
# 3. YanthraMoveSystem receives detections
# 4. MotionController retrieves via provider
# 5. Robot executes picking sequence
```

**Continuous Operation Test:**
```bash
# Hardware mode with 2-hour runtime
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true \
  max_runtime_minutes:=120

# Monitor for:
# - Memory leaks (watch RSS in top)
# - Detection reliability (no dropped messages)
# - System stability over time
```

---

## APPENDIX D: Related Documentation

### Primary Documents
1. **COTTON_DETECTION_INTEGRATION_README.md** (this file)
   - User-facing documentation
   - Quick start guide
   - API reference
   - Troubleshooting

### Historical Documents (Archived)
2. **COTTON_DETECTION_INTEGRATION_COMPLETE.md**
   - Complete technical implementation details
   - Build verification logs
   - Code changes with line numbers
   - Now consolidated into Appendix A

3. **INTEGRATION_COMPLETE_FINAL_SUMMARY.md**
   - Final task completion status
   - Success metrics
   - Testing checklist
   - Now consolidated into Appendix A

4. **LEGACY_COTTON_DETECTION_DEPRECATED.md**
   - Deprecation notices
   - Migration path for legacy tools
   - Tools requiring updates
   - Content merged into Appendix A

### Package Documentation
5. **src/cotton_detection_ros2/README.md**
   - Cotton detection node specifics
   - Algorithm details
   - Performance tuning
   - Camera configuration

6. **docs/guides/TESTING_AND_OFFLINE_OPERATION.md**
   - Comprehensive testing guide
   - Offline testing procedures
   - Simulation modes
   - CI/CD integration

### Architecture Documentation
7. **docs/architecture/SYSTEM_ARCHITECTURE.md**
   - Overall system architecture
   - Component interactions
   - Design decisions

8. **docs/production-system/03-COTTON_DETECTION.md**
   - Production deployment guide
   - Hardware requirements
   - Configuration best practices

---

**Last Updated:** 2025-11-04  
**Version:** 2.0 (Consolidated)
**Status:** 🟢 **Production Ready** (as of 2025-11-01)
