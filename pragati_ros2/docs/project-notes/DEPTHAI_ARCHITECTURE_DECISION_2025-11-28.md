# DepthAI Architecture Decision: Custom vs depthai_ros_driver

**Created:** 2025-11-28  
**Status:** ANALYSIS COMPLETE  
**Decision Required:** Choose between current custom approach or migrate to depthai_ros_driver

---

## Executive Summary

This document provides a **fact-based** analysis comparing our current custom DepthAI C++ integration with the official `depthai_ros_driver` package.

### Critical Correction

**The previous evaluation (DEPTHAI_ROS_DRIVER_EVALUATION.md) was based on INCORRECT information:**

❌ **Wrong:** "depthai_ros_driver doesn't support on-device neural networks"  
✅ **Correct:** depthai_ros_driver **DOES support** on-device YOLO/MobileNet/Segmentation with spatial detection

### Key Findings

| Capability | Custom Approach | depthai_ros_driver |
|------------|-----------------|-------------------|
| On-device YOLO | ✅ Yes | ✅ Yes |
| Spatial (3D) detection | ✅ Yes | ✅ Yes (via `camera.i_nn_type: spatial`) |
| Custom .blob models | ✅ Yes | ✅ Yes (via JSON config) |
| YOLOv8 support | ✅ Yes* | ✅ Yes (via JSON config) |
| Stop/start services | ❌ Must rebuild pipeline | ✅ Built-in (`~/stop`, `~/start`) |
| Standard TF frames | ❌ Missing optical frame | ✅ REP-103 compliant |
| RViz visualization | ❌ Not published | ✅ Standard topics |
| Power management | ❌ Full reinit (~4-5s) | ✅ Stop service removes pipeline |
| Maintenance | Manual | Community/Luxonis |

*Note: Current code uses `YoloSpatialDetectionNetwork` which works for YOLOv8 anchor-free models.

---

## Verified Facts from Official Documentation

### depthai_ros_driver Capabilities (Confirmed)

**Source:** https://docs.luxonis.com/software/ros/depthai-ros/driver/

1. **Neural Network Support:**
   > "Currently we provide options to load MobileNet, Yolo and Segmentation (not in spatial) models."
   
   - `nn.i_nn_config_path`: Path to JSON config for NN parameters
   - `camera.i_nn_type`: `none`, `rgb`, or `spatial` (for 3D detections)

2. **Spatial NN:**
   > "You can also set up spatial NN for Stereo node"
   
   - `stereo.i_enable_spatial_nn`: Enable spatial NN on stereo
   - Default mode is already `spatial` for NN

3. **Power Saving:**
   > "Stopping camera also can be used for power saving, as pipeline is removed from the device."
   
   - `~/stop` service: Removes pipeline from device
   - `~/start` service: Recreates pipeline
   - Topics are removed when stopped

4. **Custom Model Config (JSON format):**
```json
{
    "model": {
        "model_name": "your_model_name",
        "zoo": "depthai_examples"
    },
    "nn_config": {
        "output_format": "detection",
        "NN_family": "YOLO",
        "NN_specific_metadata": {
            "classes": 1,
            "coordinates": 4,
            "anchors": [...],
            "anchor_masks": {...},
            "iou_threshold": 0.5,
            "confidence_threshold": 0.5
        }
    },
    "mappings": {
        "labels": ["cotton"]
    }
}
```

---

## Current Implementation Analysis

### File: `src/cotton_detection_ros2/src/depthai_manager.cpp` (~905 lines)

**Pipeline Structure:**
```
ColorCamera (1920x1080) → ImageManip (416x416) → YoloSpatialNN → XLinkOut
      │                                               │
MonoLeft/Right (400p) → StereoDepth ────────────────┘
```

**Key Configuration:**
- Resolution: 1920x1080 sensor, 416x416 NN input
- FPS: Configurable (default 15)
- Model: `yolov8v2.blob` (YOLOv8 anchor-free model)
- Network Type: `YoloSpatialDetectionNetwork` (but configured without anchors for YOLOv8)
- Depth: Optional, disabled saves ~31°C thermal

**Current Limitations:**
1. No pause/resume without full pipeline rebuild
2. Reinitialize takes ~4-5 seconds
3. No standard TF frames published
4. No RGB/depth topic publication for debugging
5. Manual coordinate handling (RUF → FLU conversion)

### File: `src/cotton_detection_ros2/src/cotton_detection_node_depthai.cpp`

**Coordinate Conversion:**
```cpp
// RUF (DepthAI) → FLU (ROS/Arm)
result.position.x = det.spatial_z / 1000.0;   // Forward
result.position.y = -det.spatial_x / 1000.0;  // Left
result.position.z = det.spatial_y / 1000.0;   // Up
```

---

## depthai_ros_driver Migration Analysis

### What We Would Get

1. **Built-in stop/start services** - Exact use case we need
2. **Standard ROS topics:**
   - `/camera/color/image_raw`
   - `/camera/depth/image_rect`
   - `/camera/nn/detections` (vision_msgs/Detection3DArray)
   - `/camera/nn/spatial_detections`
3. **REP-103 TF frames:**
   - `oak_rgb_camera_optical_frame`
   - `oak_depth_optical_frame`
4. **RViz compatibility** - Debug without custom code
5. **Diagnostic publishing** - Health monitoring

### What We Need to Create

1. **YOLO JSON config for our model:**
```json
{
    "model": {
        "model_path": "/path/to/yolov8v2.blob"
    },
    "nn_config": {
        "output_format": "detection",
        "NN_family": "YOLO",
        "NN_specific_metadata": {
            "classes": 1,
            "coordinates": 4,
            "anchors": [],
            "anchor_masks": {},
            "iou_threshold": 0.5,
            "confidence_threshold": 0.5
        }
    },
    "mappings": {
        "labels": ["cotton"]
    }
}
```

2. **Launch file configuration:**
```yaml
camera:
  i_pipeline_type: "RGBD"
  i_nn_type: "spatial"
  i_mx_id: ""  # Auto-detect
  
nn:
  i_nn_config_path: "config/cotton_yolo.json"
  
rgb:
  i_resolution: "1080P"
  i_fps: 15
  i_preview_size: 416
  
stereo:
  i_enable_depth: true  # or false for thermal savings
```

3. **Node to convert detections:**
   - Subscribe to `/camera/nn/spatial_detections`
   - Convert to our `CottonDetection.srv` format
   - Publish to existing service interface

### Migration Effort Estimate

| Task | Estimated Time |
|------|----------------|
| Create YOLO JSON config | 30 min |
| Create launch file with params | 1 hour |
| Create detection subscriber node | 2-3 hours |
| Test spatial detection output | 2 hours |
| Integrate with existing service | 2 hours |
| Test power management (stop/start) | 1 hour |
| Update URDF for TF frames | 1 hour |
| Documentation updates | 1 hour |
| **Total** | **~1-2 days** |

### What We Would Lose

1. **Direct C++ API access** - Less control over pipeline details
2. **Custom queue management** - Driver handles queues
3. **~900 lines of tested code** - Risk of new bugs
4. **Build time savings** - Additional depthai_ros dependency

### What We Would Gain

1. **Power management** - Stop/start services out of the box
2. **Standard interfaces** - Works with ROS tools
3. **Maintainability** - Community/Luxonis maintains driver
4. **Debugging** - RViz visualization, standard topics
5. **Future compatibility** - Updates via apt

---

## Thermal Considerations

### Current Thermal Performance (from OAKD_Pipeline_DeepDive.md)

| Config | Peak Temp | Notes |
|--------|-----------|-------|
| 15 FPS + Depth | 96.6°C | CRITICAL - thermal throttling |
| 15 FPS - Depth | 65.2°C | **31°C savings**, stable |

### depthai_ros_driver Thermal

The stop/start services would help with thermal management:
- Stop: Pipeline removed from device → camera idles → temp drops
- Start: Pipeline recreated on demand

This matches our use case:
1. Vehicle arrives at position
2. Start camera
3. Single detection
4. Stop camera
5. Arm picks cotton

---

## Recommendation

### Option A: Stay with Custom Approach + Add Pause/Resume

**Effort:** ~2 hours (per DEPTHAI_RUNTIME_CAMERA_CONTROL_PLAN)
**Risk:** Low
**Benefit:** Fast pause/resume (~10ms), keep existing tested code

**Implementation:**
- Add XLinkIn node for camera control
- Implement `pauseCamera()` / `resumeCamera()` methods
- Use `setStopStreaming()` / `setStartStreaming()`

**Downside:** Still no standard TF, no RViz debugging, manual maintenance

### Option B: Migrate to depthai_ros_driver

**Effort:** ~1-2 days
**Risk:** Medium (new code, testing needed)
**Benefit:** 
- Power management built-in
- Standard ROS interface
- Community maintenance
- Better debugging tools

**Implementation:**
- Create YOLO JSON config
- Write launch file
- Create thin subscriber node
- Remove custom depthai_manager.cpp

### Recommendation: Option B (Migrate to depthai_ros_driver)

**Rationale:**
1. **Fact:** depthai_ros_driver supports everything we need (on-device YOLO spatial)
2. **Fact:** Built-in stop/start services solve our power management use case
3. **Fact:** Standard interfaces reduce future maintenance burden
4. **Fact:** The ~2 day migration is comparable to implementing pause/resume properly

**Caveats:**
- Need to verify YOLOv8 anchor-free model works with driver's JSON config
- Test actual spatial detection accuracy matches current implementation
- Confirm stop/start latency is acceptable for our use case

---

## Next Steps

### Before Final Decision

1. **Install depthai_ros_driver:**
   ```bash
   sudo apt install ros-jazzy-depthai-ros
   # OR build from source for latest
   ```

2. **Quick test with example YOLO:**
   ```bash
   ros2 launch depthai_ros_driver camera.launch.py \
     camera.i_nn_type:=spatial
   ```

3. **Verify spatial detections publish:**
   ```bash
   ros2 topic echo /oak/nn/spatial_detections
   ```

4. **Test stop/start services:**
   ```bash
   ros2 service call /oak/stop std_srvs/srv/Trigger
   # Verify temp drops
   ros2 service call /oak/start std_srvs/srv/Trigger
   ```

5. **Test with custom blob:**
   - Create cotton_yolo.json with our model path
   - Verify detections work

### If Tests Pass: Proceed with Migration

Create migration TODO list:
1. Create `config/depthai/cotton_yolo.json`
2. Create `launch/cotton_detection_driver.launch.py`
3. Create `src/cotton_detection_subscriber.cpp`
4. Update `CottonDetectionNode` to use subscriber
5. Remove `depthai_manager.cpp` and related files
6. Update URDF for standard TF frames
7. Update documentation

---

## Critical Q&A (2025-11-28)

These questions were raised during evaluation and answered with verified facts:

### Q1: Stop/Start Service - Does reloading the pipeline take significant time?

**Answer: YES, ~1-2 seconds to restart.**

**Evidence:** From GitHub issue #657 logs:
- "USB SPEED: HIGH" → "Finished setting up pipeline" → "Camera ready!" spans ~1.1 second
- This is full pipeline removal and reload to device

**Comparison:**
| Method | Time | What Happens |
|--------|------|-------------|
| depthai_ros_driver stop/start | ~1-2 sec | Full pipeline removed from device, reloaded |
| Our current shutdown()/initialize() | ~4-5 sec | Same + USB reconnection |
| Proposed setStopStreaming() | ~10ms | Only camera sensor stops, pipeline stays loaded |

**Conclusion:** depthai_ros_driver's stop/start is NOT fast pause - it's full pipeline reload.

---

### Q2: Does depthai_ros_driver allow custom model loading?

**Answer: YES, via JSON config file.**

**Evidence:** From official docs:
> "nn.i_nn_config_path represents path to JSON that contains information on what type of NN to load, and what parameters to use."

**JSON format for custom YOLO:**
```json
{
    "model": {
        "model_path": "/path/to/yolov8v2.blob"
    },
    "nn_config": {
        "NN_family": "YOLO",
        "NN_specific_metadata": {
            "classes": 1,
            "anchors": [],
            "anchor_masks": {}
        }
    }
}
```

**Caveat:** "Currently we provide options to load MobileNet, Yolo and Segmentation (not in spatial) models." - YOLOv8 anchor-free needs verification.

---

### Q3: Is depthai_ros_driver Python only or C++ too?

**Answer: C++ is the core implementation.**

**Evidence:** 
- Package description: "DepthAI core is a C++ library which comes with firmware and an API to interact with OAK Platform"
- Source code uses `rclcpp` and C++ DepthAI API
- Example: `dai::rosBridge::SpatialDetectionConverter detConverter(...)`

---

### Q4: Does depthai_ros_driver support ROS2 Jazzy?

**Answer: YES - Available via apt!**

**Evidence:** `apt-cache search ros-jazzy-depthai` returns:
```
ros-jazzy-depthai-ros-driver - Depthai ROS Monolithic node.
ros-jazzy-depthai-ros - The depthai-ros package
ros-jazzy-depthai-bridge - The depthai_bridge package
ros-jazzy-depthai-ros-msgs - Package to keep interface independent of the driver
```

**Install:** `sudo apt install ros-jazzy-depthai-ros`

---

### Q5: How does coordinate handling work? Can we get same RUF→FLU conversion?

**Answer: depthai_ros_driver publishes in RDF optical frame, NOT RUF.**

**Evidence:** Example code shows:
```cpp
SpatialDetectionConverter detConverter(tfPrefix + "_rgb_camera_optical_frame", 416, 416, false);
```

**Coordinate comparison:**
| Source | Format | X | Y | Z |
|--------|--------|---|---|---|
| DepthAI raw | RUF | Right | Up | Forward |
| depthai_ros_driver | RDF (optical) | Right | Down | Forward |
| Our arm needs | FLU | Forward | Left | Up |

**Current conversion (RUF → FLU):**
```cpp
result.position.x = det.spatial_z / 1000.0;   // Forward (from Z)
result.position.y = -det.spatial_x / 1000.0;  // Left (from -X)
result.position.z = det.spatial_y / 1000.0;   // Up (from Y)
```

**If using driver (RDF → FLU):**
```cpp
result.position.x = det.position.z;   // Forward (from Z)
result.position.y = -det.position.x;  // Left (from -X_right)
result.position.z = -det.position.y;  // Up (from -Y_down)
```

**Conclusion:** Would need to redo coordinate conversion if switching.

---

### Q6: What if we don't have optical frame in URDF/TF?

**Answer: Two options available.**

**Option A - Let driver publish its own TF:**
```yaml
camera:
  i_publish_tf_from_calibration: true
  i_tf_parent_frame: "camera_link"  # Your existing frame
```

**Option B - Use custom URDF:**
```yaml
camera:
  i_tf_custom_urdf_location: "/path/to/oak_d_lite.xacro"
```

**Note:** Would need to add optical frame transformation (`-pi/2, 0, -pi/2` rotation) to URDF.

---

### Q7: Re-verification after each pick - Does it take time?

**Answer: Depends on mode.**

| Mode | Verification Time | Use Case |
|------|-------------------|----------|
| Continuous running | ~30-60ms (next frame) | During picking sequence |
| depthai_ros_driver stop/start | ~1-2 sec | NOT suitable for quick verify |
| Our proposed pause/resume | ~10-100ms | Ideal for verify after pick |

**Recommendation:** Keep pipeline running during picking sequence (READY mode), use `setStartStreaming()` for quick verify, only full shutdown during longer idle (between rows).

---

### Q8: Continuous running - Will there be issues?

**Answer: Known stability issues with long-running + stop/start cycles.**

**Evidence:** GitHub issue #657:
> "Oak-D-Lite crashed and taking 100% CPU after 23 hours operation"

**Key points:**
- Issue was with repeated stop/start cycles, not pure continuous operation
- Thermal is main concern for continuous: 96°C with depth, 65°C without
- depthai_ros_driver doesn't add/solve thermal - same underlying hardware

**Mitigation:**
- Disable depth when not needed (saves ~31°C)
- Use pause/resume instead of stop/start for frequent toggling
- Implement idle timeout for full shutdown during long breaks

**⚠️ Important Thermal Clarification:**

The `setStopStreaming()` pause does NOT achieve the same thermal savings as full shutdown:

| State | VPU | Sensors | Expected Temp | Savings |
|-------|-----|---------|---------------|--------|
| ACTIVE (depth off) | Running | Streaming | ~65°C | baseline |
| PAUSED | Idle but powered | Stopped | ~50-55°C? | ~10-15°C? |
| SHUTDOWN | Off | Off | ~ambient | ~40-50°C |

**NEEDS HARDWARE TESTING** - Pause thermal savings are estimated, not verified.

Temperature can still be monitored while paused via `device_->getChipTemperature()`.

---

## Final Decision: STAY WITH CUSTOM APPROACH + ADD PAUSE/RESUME

**Date:** 2025-11-28

### Rationale

| Requirement | Custom + Pause/Resume | depthai_ros_driver |
|-------------|----------------------|-------------------|
| Fast pause (~10ms) | ✅ Yes | ❌ No (~1-2 sec) |
| Re-verify after pick | ✅ Instant | ❌ Slow reload |
| Custom YOLOv8 model | ✅ Already working | ⚠️ Needs testing |
| Jazzy support | ✅ Already working | ✅ Available |
| RUF→FLU conversion | ✅ Already done | ⚠️ Need to redo |
| Existing tested code | ✅ Keep ~900 lines | ❌ Rewrite |
| Standard TF frames | ❌ Need to add later | ✅ Built-in |
| RViz debugging | ❌ Need to add later | ✅ Built-in |

### Why NOT depthai_ros_driver?

1. **Stop/start is too slow** - Full pipeline reload (~1-2 sec) vs our pause (~10ms)
2. **Re-verification use case** - Need instant detection after each pick
3. **Working code** - Our YOLOv8 spatial detection already works
4. **Coordinate conversion** - Already have RUF→FLU working correctly
5. **Risk** - Migration could introduce bugs in tested system

### Why Custom + Pause/Resume?

1. **Fast thermal response** - ~10ms pause vs ~4-5 sec shutdown
2. **Quick verification** - Pipeline stays warm, instant next detection
3. **Existing investment** - ~900 lines of tested, working code
4. **Lower risk** - Small addition (~50 lines) vs complete rewrite

### Implementation Plan

Proceed with `DEPTHAI_RUNTIME_CAMERA_CONTROL_PLAN_2025-11-27.md`:

1. **Add XLinkIn node** for camera control in `buildPipeline()`
2. **Add pause/resume methods** using `setStopStreaming()`/`setStartStreaming()`
3. **Update camera control service** to use new fast methods
4. **Implement operational modes:** IDLE → READY → ACTIVE → SHUTDOWN
5. **Test on hardware** - verify ~10ms pause/resume latency

**Estimated effort:** ~2 hours implementation + testing

### Future Enhancements (Optional)

If debugging becomes an issue later, we can add:
- Optional RGB/depth topic publishing for RViz
- Optical frame to URDF
- camera_info publishing

These are additive and don't require switching to depthai_ros_driver.

---

## References

- depthai_ros_driver docs: https://docs.luxonis.com/software/ros/depthai-ros/driver/
- Example YOLO JSON: https://github.com/luxonis/depthai-ros/blob/humble/depthai_ros_driver/config/nn/yolo.json
- GitHub Issue #657: https://github.com/luxonis/depthai-ros/issues/657
- Current implementation: `src/cotton_detection_ros2/src/depthai_manager.cpp`
- Runtime control plan: `docs/project-notes/DEPTHAI_RUNTIME_CAMERA_CONTROL_PLAN_2025-11-27.md`
- Thermal analysis: `docs/OAKD_Pipeline_DeepDive.md`
- DepthAI CameraControl API: https://docs.luxonis.com/projects/api/en/latest/components/messages/camera_control/
