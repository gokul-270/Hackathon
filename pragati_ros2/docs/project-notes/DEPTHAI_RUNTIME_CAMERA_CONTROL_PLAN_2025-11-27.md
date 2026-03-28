# DepthAI Runtime Camera Control Implementation

**Created:** 2025-11-27  
**Status:** ✅ IMPLEMENTED (2025-11-28)  
**Goal:** Add runtime camera pause/resume without pipeline reinitialization

> ✅ **Implementation Complete (2025-11-28)**
>
> Pause/resume functionality has been added to `DepthAIManager`:
>
> **New API methods:**
> - `pauseCamera()` - Pauses ALL 3 cameras (Color + MonoLeft + MonoRight)
> - `resumeCamera()` - Resumes ALL 3 cameras
> - `isCameraPaused()` - Check current pause state
>
> **Implementation details:**
> - XLinkIn nodes added for runtime camera control
> - Uses `dai::CameraControl::setStopStreaming()` / `setStartStreaming()`
> - Thread-safe with mutex protection
> - Properly cleans up in `shutdown()`
>
> **Files modified:**
> - `include/cotton_detection_ros2/depthai_manager.hpp` - Added method declarations
> - `src/depthai_manager.cpp` - Added XLinkIn nodes, control queues, and implementations
> - `src/cotton_detection_node_services.cpp` - Updated camera control & thermal callbacks
>
> **All phases complete!** Hardware testing needed to verify thermal improvement.

## Problem Statement

**Current behavior:**
- To pause camera (thermal management): `shutdown()` + `initialize()` = **~4-5 seconds**
- Full pipeline rebuild, model re-upload to VPU
- Causes thermal spike during reinit
- Slow response time for camera control service

**Desired behavior:**
- Pause/resume camera in **~10ms**
- Keep NN model loaded on Myriad X VPU
- Only stop/start camera sensor streaming
- Instant thermal management response

## Technical Research

### DepthAI CameraControl API

From DepthAI documentation:
- `CameraControl.setStopStreaming()` - Stop camera sensor from capturing frames
- `CameraControl.setStartStreaming()` - Resume camera sensor capturing
- Sent via XLinkIn node linked to camera's `inputControl`

### Required Pipeline Changes

Need to add XLinkIn node during pipeline build:

```cpp
auto camControl = pipeline_->create<dai::node::XLinkIn>();
camControl->setStreamName("camControl");
camControl->out.link(colorCam->inputControl);
```

And get input queue after device connection:

```cpp
cam_control_queue_ = device_->getInputQueue("camControl");
```

## Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OAK-D Lite Pipeline                       │
│                                                              │
│  ColorCamera ──► ImageManip ──► YoloSpatialNN ──► XLinkOut  │
│       │                              │                       │
│       └──────── StereoDepth ─────────┘                       │
│                                                              │
│  NO runtime control - must rebuild entire pipeline           │
└─────────────────────────────────────────────────────────────┘
```

## Proposed Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    OAK-D Lite Pipeline                            │
│                                                                   │
│  XLinkIn(colorCamControl) ──► ColorCamera.inputControl            │
│  XLinkIn(monoLeftControl) ──► MonoLeft.inputControl               │
│  XLinkIn(monoRightControl) ─► MonoRight.inputControl              │
│                                                                   │
│  ColorCamera ──► ImageManip ──► YoloSpatialNN ──► XLinkOut         │
│       │                              │                             │
│  MonoLeft ───┐                       │                             │
│             ├──► StereoDepth ────────┘                             │
│  MonoRight ─┘                                                     │
│                                                                   │
│  Host can send CameraControl to ALL 3 cameras at runtime!         │
└──────────────────────────────────────────────────────────────────────┘
```

**IMPORTANT:** Must pause ALL 3 cameras (Color + MonoLeft + MonoRight) to stop StereoDepth processing and get thermal relief.

## Implementation Plan

### Phase 1: Modify Pipeline Build

**File:** `src/depthai_manager.cpp` - `buildPipeline()` method

**Changes:**
1. Create XLinkIn nodes for ALL camera controls
2. Link to ColorCamera, MonoLeft, and MonoRight inputControl

```cpp
// Add after creating camera nodes, before linking
auto colorCamControl = pipeline_->create<dai::node::XLinkIn>();
colorCamControl->setStreamName("colorCamControl");
colorCamControl->out.link(colorCam->inputControl);

if (config_.enable_depth) {
    auto monoLeftControl = pipeline_->create<dai::node::XLinkIn>();
    monoLeftControl->setStreamName("monoLeftControl");
    monoLeftControl->out.link(monoLeft->inputControl);
    
    auto monoRightControl = pipeline_->create<dai::node::XLinkIn>();
    monoRightControl->setStreamName("monoRightControl");
    monoRightControl->out.link(monoRight->inputControl);
}
```

**Lines affected:** ~717-850 (buildPipeline function)

### Phase 2: Add Control Queues

**File:** `src/depthai_manager.cpp` - Impl class

**Add members:**
```cpp
// In Impl class
std::shared_ptr<dai::DataInputQueue> color_control_queue_;
std::shared_ptr<dai::DataInputQueue> mono_left_control_queue_;
std::shared_ptr<dai::DataInputQueue> mono_right_control_queue_;
bool camera_paused_{false};
```

**File:** `src/depthai_manager.cpp` - `initialize()` method

**Get input queues after device connection:**
```cpp
// After device_ = std::make_unique<dai::Device>(...)
pImpl_->color_control_queue_ = pImpl_->device_->getInputQueue("colorCamControl");
if (config.enable_depth) {
    pImpl_->mono_left_control_queue_ = pImpl_->device_->getInputQueue("monoLeftControl");
    pImpl_->mono_right_control_queue_ = pImpl_->device_->getInputQueue("monoRightControl");
}
```

**Lines affected:** ~84-146 (initialize function), ~22-58 (Impl class)

### Phase 3: Add Pause/Resume Methods

**File:** `include/cotton_detection_ros2/depthai_manager.hpp`

**Add declarations:**
```cpp
bool pauseCamera();   // Stop streaming ALL cameras, keep pipeline
bool resumeCamera();  // Resume streaming ALL cameras
bool isCameraPaused() const;
```

**File:** `src/depthai_manager.cpp`

**Add implementations (pause ALL cameras):**
```cpp
bool DepthAIManager::pauseCamera() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    if (!pImpl_->initialized_ || !pImpl_->color_control_queue_) {
        return false;
    }
    
    dai::CameraControl ctrl;
    ctrl.setStopStreaming();
    
    // Stop ALL cameras for maximum thermal relief
    pImpl_->color_control_queue_->send(ctrl);
    if (pImpl_->mono_left_control_queue_) {
        pImpl_->mono_left_control_queue_->send(ctrl);
    }
    if (pImpl_->mono_right_control_queue_) {
        pImpl_->mono_right_control_queue_->send(ctrl);
    }
    
    pImpl_->camera_paused_ = true;
    std::cout << "[DepthAIManager] All cameras paused" << std::endl;
    return true;
}

bool DepthAIManager::resumeCamera() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    if (!pImpl_->initialized_ || !pImpl_->color_control_queue_) {
        return false;
    }
    
    dai::CameraControl ctrl;
    ctrl.setStartStreaming();
    
    // Resume ALL cameras
    pImpl_->color_control_queue_->send(ctrl);
    if (pImpl_->mono_left_control_queue_) {
        pImpl_->mono_left_control_queue_->send(ctrl);
    }
    if (pImpl_->mono_right_control_queue_) {
        pImpl_->mono_right_control_queue_->send(ctrl);
    }
    
    pImpl_->camera_paused_ = false;
    std::cout << "[DepthAIManager] All cameras resumed" << std::endl;
    return true;
}

bool DepthAIManager::isCameraPaused() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    return pImpl_->camera_paused_;
}
```

### Phase 4: Update Camera Control Service

**File:** `src/cotton_detection_node_depthai.cpp` or relevant service handler

**Changes:**
1. Replace `shutdown()`/`initialize()` calls with `pauseCamera()`/`resumeCamera()`
2. Keep existing service interface (`/cotton_detection/camera_control`)

**Current code (slow):**
```cpp
if (!enable) {
    depthai_manager_->shutdown();
} else {
    depthai_manager_->initialize(model_path_, config_);
}
```

**New code (fast):**
```cpp
if (!enable) {
    depthai_manager_->pauseCamera();
} else {
    depthai_manager_->resumeCamera();
}
```

### Phase 5: Update Thermal Management

**File:** `src/cotton_detection_node_depthai.cpp` - thermal callback

**Changes:**
- Use `pauseCamera()` instead of `shutdown()` when temperature high
- Use `resumeCamera()` instead of `initialize()` when temperature drops
- Much faster thermal response

## Testing Plan

1. **Build test:** Compile successfully on x86_64

2. **Basic pause/resume test:**
   ```bash
   # Start node
   ros2 run cotton_detection_ros2 cotton_detection_node
   
   # Pause camera
   ros2 service call /cotton_detection/camera_control std_srvs/srv/SetBool "{data: false}"
   # Verify no frames coming (check logs)
   
   # Resume camera  
   ros2 service call /cotton_detection/camera_control std_srvs/srv/SetBool "{data: true}"
   
   # Verify detections work
   ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{command: 1}"
   ```

3. **Timing test:** Measure pause/resume latency (target: <100ms)

4. **Thermal test:** Verify camera stops generating heat when paused

## Critical Clarifications (2025-11-28)

### Q: Do we need to ADD XLinkIn node?
**YES.** Currently our pipeline has only XLinkOut (output) nodes for reading frames.
We have NO XLinkIn (input) node to send runtime commands to the camera.

**Current code has:**
- `XLinkOut("detections")` - read detections
- `XLinkOut("rgb")` - read RGB frames  
- `XLinkOut("depth")` - read depth frames

**We need to ADD:**
- `XLinkIn("camControl")` → linked to `ColorCamera.inputControl`

### Q: How much thermal improvement?
**Partial improvement - VPU stays powered:**

| State | Expected Temp | Notes |
|-------|---------------|-------|
| ACTIVE (depth ON) | ~96°C | Current - CRITICAL thermal throttling |
| PAUSED | ~75-80°C? | VPU idle, all sensors stopped - **NEEDS TESTING** |
| SHUTDOWN | ~ambient | Full power off |

Pause stops frame flow (sensor → ISP → NN) but Myriad X VPU remains powered and warm.

**Why pause still helps:** At ~96°C we're at thermal limit. Even 15-20°C savings during pause prevents throttling.

### Q: Can we monitor temperature while paused?
**YES.** `device_->getChipTemperature()` works as long as device is connected.
Temperature monitoring is independent of camera streaming state.

### Q: How long can we pause?
**Indefinitely.** The ~10ms timing is for RESUME (sending `setStartStreaming()` + getting first frame).
Pause can last as long as needed (arm movement, between picks, etc.).

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| setStopStreaming may not fully stop VPU processing | Test thermal - VPU idle still uses some power |
| Queue may fill up while paused | Queues are non-blocking, old frames dropped |
| Not all DepthAI versions support this | Check dai::CameraControl has methods at compile time |
| Thermal savings less than expected | Full shutdown fallback for long idle periods |
| MonoCameras don't pause correctly | Implementation pauses ALL 3 cameras together |

## Estimated Effort

- Phase 1-2: 30 minutes (pipeline changes)
- Phase 3: 30 minutes (new methods)
- Phase 4-5: 30 minutes (integrate with services)
- Testing: 30 minutes
- **Total: ~2 hours**

## Operational Modes (Updated Based on Use Case)

### Realistic Cotton Picking Workflow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                 COTTON PICKING CYCLE                              │
│                                                                    │
│  1. START Signal (button press / yanthra_move request)            │
│     └─► Camera: RESUME (~10ms)                                    │
│                                                                    │
│  2. Detection (~100-150ms)                                         │
│     └─► Get cotton 3D position (X, Y, Z)                          │
│     └─► Send position to yanthra_move                             │
│     └─► Camera: PAUSE ───────────────────────────────────────┐   │
│                                                           │   │
│  3. Arm Movement (~1.5-2 sec)                             │   │
│     └─► All joints move to cotton position     PAUSED ────┤   │
│     └─► No camera needed during movement     (cooling)   │   │
│                                                           │   │
│  4. End Effector Activation                               │   │
│     └─► Cotton pickup operation               PAUSED ────┤   │
│     └─► Camera: RESUME (~10ms) ────────────────────────┘   │
│                                                                    │
│  5. Verify Pick (Optional, ~100ms)                                 │
│     └─► Quick image to verify cotton collected                    │
│     └─► Camera: PAUSE                                             │
│                                                                    │
│  6. Compressor Collection (~1-2 sec)                               │
│     └─► Transfer cotton to collection bin      PAUSED             │
│     └─► No camera needed                      (cooling)           │
│                                                                    │
│  7. Return to Home / Next Position                                 │
│     └─► Ready for next cycle                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Thermal Duty Cycle Analysis

**Target cycle time: 2.5 seconds per cotton boll (including pick + collection)**

```
┌─────────────────────────────────────────────────────────────────────────┐
Time:    0ms        150ms                              ~2000ms      2500ms
│         │           │                                   │          │
│ [DETECT]│           │      [ARM: Move + Pick]           │[VERIFY]  │
│  ACTIVE │───────────│────── PAUSED (cooling) ───────│ ACTIVE   │
│         │           │                                   │          │
│         │           │  Arm goes to cotton, picks it,    │          │
│         │           │  returns to HOME position         │          │
│         │           │                                   │          │
│         │           │                          [COMPRESSOR STARTS]│
│         │           │                          Verify happens      │
│         │           │                          IN PARALLEL with    │
│         │           │                          compressor!         │
└─────────────────────────────────────────────────────────────────────────┘
```

| Phase | Duration | Camera State | Notes |
|-------|----------|--------------|-------|
| Detection | ~150ms | ACTIVE | Get 3D position → send to yanthra_move |
| Arm Move + Pick + Return | ~1850ms | PAUSED | Camera cooling during arm movement |
| Verify (parallel with compressor) | ~100ms | ACTIVE | Arm at HOME, compressor running |
| Compressor finishes | ~400ms | PAUSED | (remaining compressor time) |

**Duty cycle:** ~250ms active / 2500ms total = **~10% active time**

**Key insight:** Verification adds NO extra time because it runs while compressor is already collecting!

Camera is **PAUSED ~90% of the time** → significant thermal relief.

### Proposed Operational Modes

**Mode 1: IDLE (default on startup)**
- Pipeline NOT loaded
- Zero power consumption from camera
- Myriad X VPU in low-power state

**Mode 2: READY (pipeline loaded, camera paused)**
- Pipeline loaded, model on VPU
- ALL cameras paused (Color + MonoLeft + MonoRight)
- Fast response (~10ms) for next detection
- Reduced thermal load (VPU idle, sensors stopped)

**Mode 3: ACTIVE (during detection)**
- All cameras streaming
- NN processing frames
- Full power consumption (~96°C)
- Auto-transitions back to READY after detection complete

**Mode 4: SHUTDOWN (after long idle timeout)**
- After X seconds with no requests → full shutdown
- Returns to IDLE mode
- Configurable timeout (e.g., 60-120 seconds between rows)

### State Transitions

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
[IDLE] ──(first request)─► [ACTIVE] ──(detection done)─► [READY]
  ▲                           ▲                            │
  │                           │                            │
  │                           └───(next detection)────────┘
  │
  └─────────────(long idle timeout)────────────────────┘
```

### Configuration Parameters

```yaml
depthai:
  idle_timeout_seconds: 120     # Full shutdown after 2 min idle (between rows)
  auto_pause_after_detection: true  # Pause camera immediately after detection
  keep_warm: true               # Stay in READY mode during active picking
```

## Success Criteria

**Functional:**
- [x] Pause/resume works without pipeline rebuild (implemented 2025-11-28)
- [ ] Resume latency < 100ms (vs current ~4000ms) - NEEDS HARDWARE TEST
- [ ] Detections work correctly after resume - NEEDS HARDWARE TEST
- [x] All 3 cameras (Color + MonoLeft + MonoRight) pause together (implemented 2025-11-28)
- [ ] No memory leaks on repeated pause/resume cycles - NEEDS HARDWARE TEST

**Thermal (MUST TEST ON HARDWARE):**
- [ ] Measure temperature drop when paused (target: 15-20°C below active)
- [ ] Verify ~10% duty cycle keeps temp below thermal throttle (~96°C)
- [x] Temperature can be monitored while paused (getChipTemperature() works while paused)

**Integration:**
- [x] Camera control service uses fast pause/resume (implemented 2025-11-28)
- [x] Thermal management uses fast pause/resume (implemented 2025-11-28)
- [x] Auto-pause after detection completes (implemented 2025-11-28, param: `depthai.auto_pause_after_detection`)
- [x] Auto-resume before detection if camera paused (implemented 2025-11-28)
- [ ] Auto-shutdown after configurable idle timeout - OPTIONAL, can be added later
- [ ] Works with yanthra_move workflow (detect → pause → move → resume → verify) - NEEDS HARDWARE TEST

## References

- DepthAI CameraControl docs: https://docs.luxonis.com/projects/api/en/latest/components/messages/camera_control/
- XLinkIn node docs: https://docs.luxonis.com/projects/api/en/latest/components/nodes/xlink_in/
- RGB Camera Control example: https://github.com/luxonis/depthai-python/blob/main/examples/ColorCamera/rgb_camera_control.py
