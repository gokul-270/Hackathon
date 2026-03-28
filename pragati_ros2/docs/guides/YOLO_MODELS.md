# YOLO Model Blobs for Cotton Detection

## Available Models

### 1. yolov11v2.blob ✅ **Current Production (Jan 2026)**

- **Size**: ~6 MB
- **Architecture**: YOLOv11 (anchor-free)
- **Input**: 416x416
- **Classes**: 2 (cotton, not_pickable)
- **Performance**: 69ms p50, 103ms p90 (measured Jan 2026 field trial)
- **Accuracy**: High - distinguishes cotton from sun reflections/leaves
- **Status**: ✅ Production

**Usage**:
```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    depthai_model_path:=/path/to/yolov11v2.blob \
    depthai_num_classes:=2
```

### 2. yolov112.blob

- **Size**: ~6 MB
- **Architecture**: YOLOv11
- **Input**: 416x416
- **Classes**: 2 (cotton, not_pickable)
- **Performance**: Similar to yolov11v2
- **Status**: ✅ Alternative YOLOv11

### 3. yolov8v2.blob (Legacy)

- **Size**: 6.07 MB
- **Architecture**: YOLOv8 (anchor-based)
- **Input**: 416x416
- **Classes**: 1 (cotton only)
- **Performance**: ~100-200ms per frame
- **Status**: 🟡 Legacy - use YOLOv11 for better false positive rejection

### 4. yolov8.blob (Legacy)

- **Size**: 6.07 MB
- **Architecture**: YOLOv8 original
- **Input**: 416x416
- **Classes**: 1 (cotton)
- **Status**: 🟡 Legacy

### 5. best_openvino_2022.1_6shave.blob (Legacy)

- **Size**: 14.11 MB
- **Architecture**: Legacy (pre-YOLOv8)
- **Input**: 416x416
- **Classes**: 1 (cotton)
- **Status**: ⚠️ Deprecated - backup only

## Model Comparison

| Model | Classes | Speed | FP Rejection | Recommended |
|-------|---------|-------|--------------|-------------|
| yolov11v2.blob | 2 | 69ms p50 | ✅ Yes (not_pickable class) | ✅ **Production** |
| yolov112.blob | 2 | ~70ms | ✅ Yes | ✅ Alternative |
| yolov8v2.blob | 1 | ~100ms | ❌ No | 🟡 Legacy |
| yolov8.blob | 1 | ~100ms | ❌ No | 🟡 Legacy |
| best_openvino_*.blob | 1 | ~200ms | ❌ No | ⚠️ Deprecated |

---

## YOLOv11 Model Variant Analysis (Jan 2026)

### Why Detection Model (Not Segmentation/Pose/OBB)?

YOLOv11 offers multiple model variants. Here's why **Detection** is optimal for Pragati:

| Model Type | Task | Use Case | Pragati Recommendation |
|------------|------|----------|------------------------|
| **Detection** | Bounding boxes + spatial coords | Cotton localization for picking | ✅ **Use this** |
| **Segmentation** | Pixel-level masks | Precise boundaries, volume estimation | ⚠️ Overkill - adds 20-50ms latency |
| **Pose** | Keypoint detection | Human/animal tracking | ❌ Not relevant |
| **OBB** | Oriented bounding boxes | Angled object detection | 🤔 Maybe for tilted bolls, but complex |

### Analysis Details

**Detection is optimal because:**

1. **Speed**: 69ms p50 latency already meets <100ms target
2. **Spatial Coordinates**: Pipeline needs X,Y,Z for arm IK, not pixel masks
3. **Myriad X Optimization**: Detection models run efficiently on OAK-D Lite VPU
4. **Pipeline Fit**: `detect → select → IK → pick` only needs bounding box center

**Segmentation would add:**
- +20-50ms latency (more computation on Myriad X)
- Pixel-level boundaries (not needed - we pick at bbox center)
- Useful only if calculating cotton volume/quality (future feature)

**OBB (Oriented Bounding Box) considerations:**
- Could help if cotton bolls appear at extreme angles
- Adds model complexity and may not work well on Myriad X
- Current bbox approach is sufficient for field conditions

### Field Trial Issues Analysis (Jan 2026)

**Two main detection concerns from field trial:**

1. **Sun Reflections (False Positives)** 
   - Problem: Bright sun reflections detected as cotton
   - Solution: YOLOv11 `not_pickable` class (class 1) now filters these
   - Status: ✅ **Addressed by 2-class model**

2. **Depth Accuracy**
   - Measured: ±10mm spatial coordinates at 0.6m (lab conditions)
   - Field conditions: Not formally measured
   - Impact: Affects pick precision, but reachability is larger issue
   - Status: ⚠️ **Needs field validation**

**Root causes of 21.8% pick success (NOT model-related):**

| Issue | Cause | Model Impact |
|-------|-------|--------------|
| 62.4% out of reach | Joint4/Joint5 limits, camera FOV | ❌ Not model-related |
| 15.8% [0,0,0] bug | Software bug in coordinate pipeline | ❌ Not model-related |
| 30.6% border_skip | Camera orientation (vertical) | ❌ Not model-related |
| Sun reflections | Filtered by `not_pickable` class | ✅ YOLOv11 2-class helps |

**Conclusion**: YOLOv11 Detection with 2 classes is the right choice. Sun reflections are now filtered. Focus remaining improvements on FOV, reachability, [0,0,0] bug fix, and field depth accuracy validation.

---

## Pick Cycle Timing Analysis

*Source: January 2026 field trial logs (both arms), 117 successful picks analyzed*

### Measured Pick Cycle Statistics (Jan 2026 Field Trial)

| Metric | Left Arm | Right Arm | Combined |
|--------|----------|-----------|----------|
| **Successful picks** | 29 | 88 | **117** |
| **Average** | 4463ms | 4493ms | **4486ms (4.5s)** |
| **Min** | 2974ms | 2515ms | **2515ms** |
| **Max** | 5458ms | 13217ms | **13217ms** |
| **Median (p50)** | 4304ms | 4013ms | **4165ms** |
| **p90** | 5380ms | 5160ms | **5356ms** |

### Distribution (pre-fix data, combined)

| Category | Count | % | Notes |
|----------|-------|---|-------|
| **Fast (<5s)** | 98 | 83.8% | Normal operation |
| **Medium (5-10s)** | 14 | 12.0% | Long reach distance |
| **Slow (>10s)** | 5 | 4.3% | Bug - right arm only (now fixed) |

*Note: Logs from RPi without proper RTC - dates may be unreliable. Timeout bug only affected right arm. Bug was fixed Jan 22 2026.*

### Detailed Phase Breakdown (Measured from 117 picks)

| Phase | p50 | p90 | Max | Notes |
|-------|-----|-----|-----|-------|
| **Detection** | 65ms | 104ms | 123ms | YOLOv11 inference + frame wait |
| **TF Transform** | <5ms | <5ms | <5ms | Static TF cached |
| **Approach (j4→j3→j5+EE)** | 1633ms | 1872ms | 11036ms* | Sequential joint moves |
| **Retreat+drop** | 2483ms | 3357ms | 3595ms | J5 retract + compressor |
| **Inter-pick delay** | 200ms | 200ms | 200ms | Configured delay |

*Max 11036ms was timeout bug (now fixed)

### Approach Phase Sub-timing

| Step | Duration | Type |
|------|----------|------|
| J4 move (lateral) | ~300ms | Variable (motor) |
| inter_joint_delay | 300ms | **Fixed config** |
| J3 move (rotation) | ~200ms | Variable (motor) |
| inter_joint_delay | 300ms | **Fixed config** |
| J5 move + EE start | ~500ms | Variable (motor + EE) |

### Retreat+Drop Phase Sub-timing

| Step | Duration | Type |
|------|----------|------|
| J5 retract | ~1000ms | Variable (distance) |
| EE off + settle | 200ms | **Fixed config** |
| cotton_settle_delay | 200ms | **Fixed config** |
| compressor_burst | 500ms | **Fixed config** |
| J3/J4 home | ~500ms | Variable (motor) |

### Fixed Delays Summary

| Delay | Duration | Purpose | Optimization Potential |
|-------|----------|---------|------------------------|
| inter_joint_delay (x2) | 600ms | Safety between J4→J3→J5 | 🟡 Use motor_control feedback to skip early |
| ee_post_joint5_delay | 300ms | Wait before EE start | ✅ Not used (dynamic EE active) |
| cotton_settle_delay | 200ms | Cotton stabilization | 🟢 Test reducing to 100ms |
| compressor_burst | 500ms | Drop cotton | 🟢 Test reducing to 300ms |
| picking_delay | 200ms | Between picks | ✅ Already minimal |
| joint3_wait (homing) | 300ms | J3 safety | 🟡 Use motor_control feedback to skip early |
| **TOTAL FIXED** | **~1600ms** | | **38% of pick time!** |

**Note on position feedback architecture:**
- **motor_control (mg6010)**: Position feedback IS enabled (`motion_feedback.enabled: true`), polls at 5Hz, logs "✅ Reached target" when joints arrive
- **yanthra_move**: Currently uses fixed delays instead of waiting for motor_control's feedback
- **Optimization**: yanthra_move could subscribe to motor_control's position feedback to skip delays when joints reach target early

### Bug: >10 Second Pick Cycles (FIXED)

**Root Cause:** When cotton is very close (J5 target < 30mm), the position monitoring loop timed out after 10 seconds because monitoring started after the short move completed.

**Pattern observed (before fix):**
```
⚙️  Joints: j3=-0.114rot j4=0.145m j5=0.001m    ← J5 very small (1mm)
[EE] Dynamic: J5 at 0.000m, starting EE (0.6mm from cotton)
[EE] Dynamic: Position monitoring TIMEOUT! loops=813, last_pos=0.001m   ← 10s timeout
🦾 Approach: 11036ms (j4→j3→j5+EE)              ← Result: 11 seconds!
```

**Affected cases from field trial (pre-fix logs):**
| J5 Target | Distance to Cotton | Result |
|-----------|-------------------|--------|
| 0.001m | 0.6mm | 11036ms timeout |
| 0.003m | 1.1mm | 11036ms timeout |
| 0.018m | 1.9mm | 11036ms timeout |
| 0.027m | 2.5mm | 11030ms timeout |

**Impact:** 5.7% of picks (5/88) were affected by this bug

**Fix (commit 1e901f79, Jan 22 2026):**
- Capture pre-command J5 position as monitoring baseline
- Use adaptive movement threshold for short moves
- Bound dynamic monitoring timeout to expected travel time (2-6s)

**Status:** ✅ FIXED - no longer affects picks

### Optimization Recommendations (Next Steps)

| Priority | Optimization | Potential Savings | Effort | Risk |
|----------|--------------|-------------------|--------|------|
| 🟢 Easy | Reduce compressor_burst 500→300ms | 200ms/pick | Low | Low |
| 🟢 Easy | Reduce cotton_settle 200→100ms | 100ms/pick | Low | Low |
| 🟡 Medium | Reduce inter_joint_delay 300→150ms | 300ms/pick | Medium | Medium |
| 🟡 Medium | Use motor_control feedback in yanthra_move | 300-600ms/pick | Medium | Low |
| ❌ N/A | Parallel J4+J3 motion | - | - | **Plant collision** |
| ✅ Done | Fix "too close" timeout bug | 10s on 4.3% | - | - |
| ✅ Done | Dynamic EE timing | ~500ms/pick | - | - |

**Quick wins (🟢 Easy):** Could save ~300ms per pick with config changes only.

**Medium effort (🟡):** motor_control already has position feedback running (`motion_feedback.enabled: true`). yanthra_move could use this feedback to skip delays when joints reach target early instead of waiting fixed times.

**Not feasible:** Parallel J4+J3 motion would risk hitting plants - joints must move sequentially.

**Total potential:** From current 4.2s median to ~3.5-3.8s with safe optimizations.

## Hardware Compatibility

All models are compatible with:
- ✅ OAK-D Lite
- ✅ OAK-D
- ✅ OAK-D Pro
- ✅ OAK-1

**Note**: Optimized for OAK-D Lite in USB2 mode.

## Model Generation

These models were generated using:
1. YOLOv8 training on custom cotton dataset
2. OpenVINO Model Optimizer for Intel Myriad X
3. blobconverter for DepthAI format

For model retraining, see training documentation (if available).

## Testing

Test different models:

```bash
# Test yolov8v2 (default)
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Test yolov8 original
ros2 param set /cotton_detect_wrapper blob_path yolov8.blob
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Test legacy model
ros2 param set /cotton_detect_wrapper blob_path best_openvino_2022.1_6shave.blob
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

## Known Issues

- **USB2 Bandwidth**: Large models may have bandwidth issues in USB2 mode
- **Inference Time**: Varies based on number of detections
- **Memory**: OAK-D Lite has limited onboard memory

## Future Work

- [ ] Quantized models for faster inference
- [x] ~~Multi-class detection (cotton + other crops)~~ → Done with YOLOv11 (cotton + not_pickable)
- [ ] Dynamic model switching at runtime
- [ ] Model performance benchmarking with different lighting conditions
- [ ] Segmentation model evaluation for cotton quality assessment (future)

---

**Last Updated**: January 28, 2026  
**Maintained By**: Pragati ROS2 Team
