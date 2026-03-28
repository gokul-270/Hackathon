# YOLOX vs YOLOv11 Comparison — Pragati Cotton Picking Robot

**Task:** A5 from March 2026 Field Trial Plan
**Owners:** Shwetha / Arun
**Decision Deadline:** March 06, 2026 (Go/No-Go)
**Companion Document:** [YOLOX Validation Runbook](YOLOX_VALIDATION_RUNBOOK.md)

---

## 1. Executive Summary

YOLOX (Apache 2.0) eliminates the AGPL-3.0 licensing risk of YOLOv11 (Ultralytics) for
commercial deployment. Performance-wise, YOLOX-Tiny is comparable to our current YOLOv11
model in parameter count and theoretical FLOPs, but **zero actual measurements exist on our
hardware**. The single biggest technical risk is whether YOLOX's output tensor format works
with DepthAI's built-in `YoloSpatialDetectionNetwork` node — if incompatible, migration
effort jumps from ~2 days to ~1-2 weeks due to host-side NMS and spatial depth
reimplementation.

**Recommendation:** Proceed to validation (companion runbook) with YOLOX-Tiny. The blocker
test (V1 in the runbook) can be completed in 2-4 hours and determines the entire migration
scope.

---

## 2. Licensing

| Aspect | YOLOv11 (Ultralytics) | YOLOX (Megvii) |
|--------|----------------------|----------------|
| License | AGPL-3.0 | Apache 2.0 |
| Commercial use | Requires Ultralytics Enterprise License (no public pricing, typically $1K-5K+/yr) | Free, unrestricted |
| Trained model license | Inherits AGPL per Ultralytics FAQ — trained weights are derivative works | No restrictions — trained weights are yours |
| Current exposure | `yolov112.blob` on every RPi is an AGPL artifact | N/A |
| Source disclosure | AGPL requires source disclosure for networked services | No requirement |

**Bottom line:** YOLOX is the clear winner for commercial deployment. The current YOLOv11
deployment carries legal risk that grows with each unit deployed.

---

## 3. Architecture Comparison

| Feature | YOLOv11 | YOLOX |
|---------|---------|-------|
| Anchors | Anchor-free | Anchor-free |
| Detection head | Unified head | Decoupled head (separate cls/reg/obj branches) |
| Confidence score | Single class probability | objectness x class_probability (two-stage) |
| NMS | Standard | Standard (same algorithm, different confidence semantics) |
| Backbone | CSPDarknet (Ultralytics variant) | Modified CSPDarknet |
| Neck | C2f + PAN-FPN | FPN + PAN |
| Built-in augmentation | Mosaic, MixUp, copy-paste | Mosaic, MixUp (built into training pipeline) |
| Training framework | Ultralytics CLI (`yolo train`) | Custom Exp class (Python) |
| Annotation format | YOLO txt (`class cx cy w h`) | COCO JSON (`instances.json`) |

### Key Architectural Difference: Decoupled Head

YOLOX's decoupled head produces **three separate output branches** (classification,
regression, objectness) vs YOLOv11's unified output. This means:

1. The output tensor layout is different
2. Confidence = objectness x class_prob (not single score)
3. DepthAI's `YoloSpatialDetectionNetwork` may or may not handle this natively

This is explored in detail in Section 6.

---

## 4. Model Variants for Myriad X VPU

| Model | Params | FLOPs | Input Size | COCO mAP | Notes |
|-------|--------|-------|-----------|----------|-------|
| **Current YOLOv11** | ~2.6M | ~6.5G | 416x416 | N/A (custom) | Production: 69ms p50 on OAK-D Lite |
| **YOLOX-Tiny** | 5.06M | 6.45G | 416x416 | 32.8% | Primary candidate — similar FLOPs |
| **YOLOX-Nano** | 0.91M | 1.08G | 416x416 | 25.8% | Backup if Tiny too slow |
| **YOLOX-S** | 9.0M | 26.8G | 640x640 | 40.5% | Too heavy for Myriad X |

**Recommendation:** Start with YOLOX-Tiny (closest to current model in FLOPs). Fall back
to YOLOX-Nano if latency exceeds 100ms target on Myriad X.

---

## 5. Performance Estimates

### Current YOLOv11 Baseline (measured, Feb 2026 field trial)

| Metric | Value | Source |
|--------|-------|--------|
| Inference p50 | 69ms | YOLO_MODELS.md |
| Inference p95 | 85ms | YOLO_MODELS.md |
| Detection latency avg | 34-93ms (varies by session) | Field Visit Report Feb 2026 |
| Detection latency max | 333.8ms | Field Visit Report Feb 2026 |
| Camera thermal | 51-63C (mean 60.1C) | Field Visit Report Feb 2026 |
| Classes | 2 (cotton, not_pickable) | production.yaml |

### YOLOX Estimates (NO actual measurements exist)

| Metric | Estimate | Basis |
|--------|----------|-------|
| YOLOX-Tiny inference | 60-120ms | Extrapolated from COCO FLOPs comparison — **not measured** |
| YOLOX-Nano inference | 30-60ms | Extrapolated — **not measured** |
| Accuracy vs YOLOv11 | Unknown | Depends on cotton-specific training |
| Thermal impact | Unknown | Different model may generate different heat profile |

**WARNING:** All YOLOX numbers are estimates from COCO benchmarks on different hardware.
The validation runbook (V3) requires measuring actual latency on our OAK-D Lite before
the Go/No-Go decision.

---

## 6. DepthAI Integration — Critical Blocker

### 6.1 Current Pipeline Architecture

```
ColorCamera(1080p) --> ImageManip(416x416) --> YoloSpatialDetectionNetwork --> XLinkOut
MonoLeft(400p)  --> StereoDepth ------------->        ^                    --> XLinkOut
MonoRight(400p) ----^                          (depth input)                  (depth)
```

The `YoloSpatialDetectionNetwork` node (`depthai_manager.cpp:1725`) is a DepthAI built-in
that performs **on-VPU**:
- YOLO output tensor decoding (grid-based)
- NMS (Non-Maximum Suppression)
- Confidence thresholding
- Spatial depth calculation (using stereo depth + bounding box ROI)

### 6.2 YOLOX Compatibility Question

The `YoloSpatialDetectionNetwork` node expects YOLO-family output tensors. Key question:
**Does it support YOLOX's decoupled-head output format?**

**If YES (low-effort migration):**
- The existing YOLOv11 anchor-free code path (`depthai_manager.cpp:1847-1850`) would work
- Changes needed: blob path, num_classes, confidence threshold tuning
- Estimated effort: 1-2 days

**If NO (high-effort migration):**
- Must replace `YoloSpatialDetectionNetwork` with generic `NeuralNetwork` node
- Must reimplement on host (RPi 4B CPU):
  - YOLOX output decoding (stride-based coordinate decode)
  - objectness x class_prob confidence computation
  - NMS (~5-10ms on ARM)
  - Spatial depth computation using `SpatialLocationCalculator` or manual depth map sampling
- Lose built-in depth params: `setDepthLowerThreshold`, `setDepthUpperThreshold`,
  `setBoundingBoxScaleFactor`
- Estimated effort: 1-2 weeks
- ~200-400 lines of new C++ code
- Performance regression: ~5-20ms additional latency per frame

**Alternative path:** Export YOLOX with SSD-format output layer appended (`[1,1,N,7]`
format), then use `SpatialDetectionNetwork` (MobileNet-style) instead. This preserves
on-device depth integration but requires custom ONNX graph surgery.

### 6.3 Current YOLO Parameters Set on the Node

| Parameter | Value | Line | Configurable? |
|-----------|-------|------|---------------|
| `setNumClasses()` | `config_.num_classes` (2) | 1838 | Yes (config) |
| `setCoordinateSize()` | `4` | 1839 | **No (hardcoded)** |
| `setIouThreshold()` | `0.5` | 1840 | **No (hardcoded)** |
| `setBoundingBoxScaleFactor()` | `0.5` | 1835 | **No (hardcoded)** |
| `setConfidenceThreshold()` | `config_.confidence_threshold` (0.3) | 1827 | Yes (config) |
| `setDepthLowerThreshold()` | `config_.depth_min_mm` (100) | 1853 | Yes (config) |
| `setDepthUpperThreshold()` | `config_.depth_max_mm` (5000) | 1854 | Yes (config) |
| Anchors (YOLOv8 only) | 9 anchors, 3 masks | 1845-1846 | **No (hardcoded)** |

### 6.4 Architecture Detection Bug

The code uses `num_classes == 1` as a proxy for "YOLOv8" to decide whether to set anchors
(`depthai_manager.cpp:1843`). This is fragile — a YOLOX model trained with 1 class would
incorrectly trigger the YOLOv8 anchor path. The migration should add an explicit
`model_architecture` parameter (e.g., `yolov8` / `yolov11` / `yolox`).

---

## 7. Spatial Depth Calculation Impact

If `YoloSpatialDetectionNetwork` is NOT compatible with YOLOX:

| Capability | Current (built-in) | Replacement (host-side) |
|-----------|-------------------|------------------------|
| Depth ROI sampling | `setBoundingBoxScaleFactor(0.5)` — central 50% of bbox | Manual depth map sampling with camera intrinsics |
| Depth range filtering | `setDepthLowerThreshold/Upper` (100-5000mm) | Manual range check on computed depth |
| Coordinate frame | DepthAI outputs RUF (Right-Up-Forward) in mm | Same, if using `SpatialLocationCalculator` node |
| Latency overhead | ~0ms (on VPU) | ~5-15ms on RPi 4B ARM CPU |

The coordinate conversion code (`cotton_detection_node_depthai.cpp:369-371`) converts
DepthAI RUF to ROS FLU:
```
position.x = spatial_z / 1000.0  (Forward)
position.y = -spatial_x / 1000.0 (Left)
position.z = spatial_y / 1000.0  (Up)
```
This stays the same regardless of which NN node type is used — it only depends on how
spatial coordinates are computed.

---

## 8. Post-Processing & Label Filtering

### 8.1 Current Class Filtering Logic

**Two-stage filtering:**

1. **Stage 1** (`cotton_detection_node_depthai.cpp:392-404`):
   ```
   if num_classes > 1:
       label 0 -> "cotton"
       label != 0 -> "not_pickable"  (increments not_pickable_count)
   else:
       all detections -> "cotton"
   ```

2. **Stage 2** (`cotton_detection_node_detection.cpp:120-126`):
   ```
   if num_classes > 1 AND label != 0:
       skip detection (continue)
   ```

**For YOLOX with 3 classes** (cotton=0, not_pickable=1, sun_glare=2): The existing
`label != 0` filter correctly blocks both not_pickable and sun_glare. Only label naming
in Stage 1 needs updating to distinguish not_pickable vs sun_glare for logging.

### 8.2 Confidence Threshold Chain

Confidence is filtered at THREE levels with DIFFERENT thresholds:

| Stage | Where | Threshold | Configurable? |
|-------|-------|-----------|---------------|
| On-device (VPU) | `depthai_manager.cpp:1827` | 0.3 | Yes (production.yaml) |
| Post-detection | `cotton_detection_node_detection.cpp` | 0.7 | Yes (production.yaml) |
| Downstream (yanthra_move) | `yanthra_move_system_operation.cpp` | 0.55 | Yes (yanthra config) |

**YOLOX concern:** YOLOX confidence = objectness x class_prob. If DepthAI's YOLO decoder
doesn't handle the two-stage multiplication, the `det.confidence` value might be raw
class_prob (without objectness). This would inflate confidence scores and pass more
false positives through the 0.3 on-device threshold. The 0.7 post-detection threshold
provides a safety net but may need re-tuning.

Also note: DepthAI can return confidence > 1.0 — the code has a `std::clamp(0.0, 1.0)`
guard at `cotton_detection_node_depthai.cpp:373`.

### 8.3 Other Filters

| Filter | Location | Status |
|--------|----------|--------|
| Zero spatial filter | `depthai_manager.cpp:1889-1893` | Active — drops (0,0,0) detections |
| Border filter | `cotton_detection_node_detection.cpp:129-141` | Active — margin=1% (production) |
| Detection cache | `cotton_detection_node_services.cpp:106-127` | Active — 100ms validity |
| Stale detection | `yanthra_move_system_operation.cpp:531` | Active — downstream age check |
| Bounding box size | N/A | **Does not exist** — needed for boll-size filtering (Task A6) |
| ROI/region filter | N/A | Only border filter exists |

### 8.4 Dead Code: `swap_class_labels`

The `swap_class_labels` parameter is declared (`cotton_detection_node_parameters.cpp:68`)
and set in `production.yaml:40` (`false`) but is **never loaded or used** anywhere in the
codebase. This is dead code — likely an unfinished feature for swapping class 0/1 mapping
if a model was trained with reversed labels. Should be either implemented or removed
during migration.

---

## 9. Training Pipeline

### 9.1 Current Workflow

Training is **entirely external** to this repository. No training scripts, dataset configs,
annotation files, or `.pt`/`.onnx` files exist in the repo. Only final `.blob` files are
committed.

**Documented (but not automated) pipeline:**
```
Ultralytics CLI: yolo train data=cotton.yaml model=yolov11n.pt
     -> best.pt
Ultralytics CLI: yolo export model=best.pt format=onnx
     -> best.onnx
OpenVINO Model Optimizer
     -> best.xml + best.bin (OpenVINO IR)
blobconverter (Luxonis tool, installed on RPi)
     -> best.blob (Myriad X 6-shave)
```

### 9.2 YOLOX Training Differences

| Aspect | YOLOv11 (current) | YOLOX |
|--------|-------------------|-------|
| Framework | Ultralytics CLI | YOLOX repo + custom `Exp` class |
| Training command | `yolo train data=cotton.yaml` | `python tools/train.py -f exps/cotton_exp.py` |
| Annotation format | YOLO txt (`class cx cy w h`) | **COCO JSON** (`instances.json`) |
| Export command | `yolo export format=onnx` | `python tools/export_onnx.py --decode_in_inference` |
| Augmentation config | Built-in defaults | `Exp` class Python methods |
| Pre-trained weights | `yolov11n.pt` from Ultralytics | `yolox_tiny.pth` from Megvii |

**Critical:** The `--decode_in_inference` flag during YOLOX ONNX export determines whether
NMS/decoding is baked into the graph. This directly affects DepthAI compatibility (Section 6).

### 9.3 Annotation Format Conversion

Current annotations are in YOLO txt format. YOLOX requires COCO JSON. **No conversion tool
exists in the repo.** Options:
- Use `pylabel`, `roboflow`, or custom Python script to convert
- Re-export from labeling tool (Roboflow/CVAT/LabelStudio) in COCO format
- Build a one-time converter script

---

## 10. Codebase Impact Assessment

### Files That MUST Change

| # | File | Change | Risk |
|---|------|--------|------|
| 1 | `src/cotton_detection_ros2/models/` | Add YOLOX .blob file | LOW |
| 2 | `src/cotton_detection_ros2/config/production.yaml` | `num_classes: 3`, model_path, confidence | LOW |
| 3 | `src/cotton_detection_ros2/src/depthai_manager.cpp` | Anchor logic, possibly NeuralNetwork node | **HIGH** |
| 4 | `src/cotton_detection_ros2/src/cotton_detection_node_depthai.cpp` | Class label mapping (add sun_glare) | LOW |
| 5 | `src/cotton_detection_ros2/src/cotton_detection_node_detection.cpp` | Verify 3-class filtering | LOW |
| 6 | `src/cotton_detection_ros2/src/cotton_detection_node_parameters.cpp` | Default blob name fallback | LOW |
| 7 | `src/cotton_detection_ros2/src/cotton_detection_node_utils.cpp` | Add sun_glare label | LOW |
| 8 | `src/cotton_detection_ros2/include/cotton_detection_ros2/camera_config.hpp` | Default num_classes comment | LOW |
| 9 | `src/cotton_detection_ros2/launch/cotton_detection_cpp.launch.py` | Default blob and class count | LOW |
| 10 | `scripts/launch/arm_launcher.sh` | **Hardcoded blob path** and num_classes | MEDIUM |

### Files That SHOULD Change (cleanup/correctness)

| # | File | Change |
|---|------|--------|
| 11 | `scripts/testing/detection/test_model_switching.sh` | Add YOLOX blob to test matrix |
| 12 | `scripts/testv11.py` | Update label map and class count |
| 13 | `scripts/testing/camera/test_still_capture_thermal.py` | Fix hardcoded path |
| 14 | `docs/guides/YOLO_MODELS.md` | Add YOLOX entry |
| 15 | `docs/YOLO_MODEL_CONFIGURATION.md` | Update conversion docs |

### Conditional Changes (only if YoloSpatialDetectionNetwork incompatible)

| # | File | Change | LOC Estimate |
|---|------|--------|-------------|
| C1 | `depthai_manager.cpp` | Replace YoloSpatialDetectionNetwork with NeuralNetwork | ~100 |
| C2 | `depthai_manager.cpp` | Add host-side YOLOX decoder + NMS | ~150 |
| C3 | `depthai_manager.cpp` | Add SpatialLocationCalculator or manual depth | ~100 |
| C4 | `depthai_manager.cpp` | Change output queue types (SpatialImgDetections -> NNData) | ~50 |
| C5 | `cotton_detection_node_depthai.cpp` | Update convertDetection() for NNData | ~50 |

---

## 11. February Field Failures as Benchmark Criteria

The February 2026 field trial revealed specific detection failures. YOLOX must be evaluated
against these:

### Quantitative Baselines

| Metric | Feb 2026 Value | March Target | YOLOX Must Beat |
|--------|---------------|-------------|-----------------|
| Pick success rate | 26.7% (315/1,181) | >60% | Improve detection -> improve picks |
| Zero spatial coordinates | 17% (503 events) | <5% | Not model-dependent (stereo depth issue) |
| Wasted detections | 79.6% (1,229/1,544) | <40% | Better class discrimination |
| Stale detections | 19.6% (>2s old) | <5%, max 2s, 0% >10s | Faster inference helps |
| Detection acceptance rate | 52.6% (1,544/2,938) | Higher | Fewer false positives |
| Border-filtered | 5.3% (453 events) | Lower | Not model-dependent |

### Qualitative Failure Modes

1. **Leaves detected as cotton** — arm targets leaf surface, not boll behind it
2. **Depth resolves on leaf, not cotton** — stereo depth ambiguity between overlapping surfaces
3. **Small bolls not pickable** — no size-based classification exists
4. **No sun glare handling** — field conditions include direct sunlight on camera
5. **Background cotton (out of reach)** — detected but beyond workspace

### What YOLOX Should Improve

- Items 1, 3, 4: Model retraining with better classes (not_pickable, sun_glare, size-aware)
- Item 2: Not model-dependent (stereo depth limitation)
- Item 5: Not model-dependent (addressed by workspace distance filter in `cotton-detection-reliability` change)

---

## 12. Boll-Size Filtering (Task A6)

The March plan requires evaluating boll-size filtering. Two approaches:

### Option A: 4th Detection Class

Add a `small_boll` class to the model (4 classes total: cotton, not_pickable, sun_glare,
small_boll). Training-time approach — model learns to classify by size.

**Pros:** Single inference, no additional processing
**Cons:** Needs labeled small-boll training data, increases model complexity

### Option B: Post-Detection Size Threshold

Keep 3 classes. After detection, filter by bounding box area:
```
bbox_area = (x_max - x_min) * (y_max - y_min)  // normalized 0-1
if bbox_area < min_boll_threshold:
    skip detection
```

**Pros:** Simple, configurable, no retraining needed
**Cons:** Bounding box area is view-dependent (distance affects apparent size)

**Note:** No bounding box size filtering exists anywhere in the current pipeline (confirmed
by deep code review). Either approach requires new code.

**PRD reference:** GAP-ENV-003 flags cotton boll size specification as OPEN — PRD notes
boll diameter 3-6cm (PRD line 1173).

---

## 13. PRD/TSD Requirement Mapping

| Requirement ID | Description | Current Status | YOLOX Impact |
|---------------|-------------|----------------|-------------|
| FR-DET-001 | Detect cotton bolls using OAK-D Lite camera | Implemented (YOLOv11) | Model swap, must maintain |
| FR-DET-002 | Classify cotton as pickable/not-pickable | Implemented (2 classes) | Expand to 3 classes |
| FR-DET-003 | Provide 3D spatial coordinates for each detection | Implemented (stereo depth) | At risk if NeuralNetwork node needed |
| PERF-DET-001 | Detection latency <100ms on Myriad X | Validated: 69ms p50 | **Must re-validate for YOLOX** |
| PERF-DET-004 | False positive rate <5% | **NOT VALIDATED** (GAP-PERF-003) | Must benchmark |
| PERF-DET-005 | False negative rate <10% | **NOT VALIDATED** (GAP-PERF-003) | Must benchmark |

---

## 14. Test Infrastructure

### Current State

- **Zero unit tests** for `cotton_detection_ros2` — `test/` directory does not exist
- `test_model_switching.sh` tests 3 legacy blobs (`yolov8.blob`, `yolov8v2.blob`,
  `best_openvino_2022.1_6shave.blob`) but **NOT the production model** (`yolov112.blob`)
- Latency tests exist but are model-agnostic (test whatever is loaded)
- No accuracy/precision/recall testing exists
- No spatial coordinate accuracy testing exists

### What Needs Updating for YOLOX

1. Add YOLOX blob to `test_model_switching.sh` test matrix
2. Add `yolov112.blob` to test matrix (currently missing!)
3. Create accuracy regression test (run both models on labeled test images, compare mAP)
4. Create 3-class filtering unit test (verify sun_glare class is properly filtered)
5. Update all hardcoded blob paths in test scripts

---

## 15. YOLOX Project Maintenance

| Aspect | Status |
|--------|--------|
| Last release | v0.3.0 (April 2022) |
| Open issues | ~723 |
| Last commit | 2022 (maintenance mode) |
| Stars | 9.2K+ |
| Active forks | 2.3K+ |

**Assessment:** Acceptable for our use case. We only use YOLOX for **offline training** —
the model runs as a compiled .blob on DepthAI hardware at runtime. The training code is
stable and well-documented. No runtime dependency on the YOLOX repo.

---

## 16. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `YoloSpatialDetectionNetwork` incompatible with YOLOX | **HIGH** | **HIGH** | Test first (V1 in runbook). If fails, evaluate NeuralNetwork node or SSD-format export |
| YOLOX accuracy lower than YOLOv11 on cotton | MEDIUM | HIGH | Benchmark on test set before committing. Keep YOLOv11 as fallback |
| YOLOX latency exceeds 100ms on Myriad X | MEDIUM | MEDIUM | Try YOLOX-Nano as fallback. Latency mostly depends on FLOPs |
| Annotation format conversion errors | LOW | MEDIUM | Validate converted COCO JSON against originals before training |
| Confidence threshold tuning needed | **HIGH** | LOW | Two-stage confidence changes score distribution — re-tune 0.3/0.7/0.55 chain |
| YOLOX training fails to converge | LOW | HIGH | Use COCO pre-trained weights, follow YOLOX default hyperparams |
| Migration takes longer than Mar 18 deadline | MEDIUM | HIGH | **Fallback:** Stay with YOLOv11, add sun_glare as 3rd class to existing model |

---

## 17. Model Evolution in This Project

```
Legacy (pre-2025)                YOLOv8 (Oct 2025)      YOLOv11 (Dec 2025)       YOLOX (planned)
best_openvino_2022.1_6shave.blob yolov8/yolov8v2.blob   yolov112/yolov11.blob    (not started)
1 class                          1 class (cotton)        2 classes (+not_pickable) 3 classes (+sun_glare)
~200ms                           ~100ms                  69ms p50                  Target: <100ms
No depth integration             DepthAI spatial         DepthAI spatial           TBD (depends on V1)
```

**Note:** Docs reference `yolov11v2.blob` but the actual file on disk is `yolov112.blob` —
naming discrepancy that should be cleaned up.

---

## 18. Coordination with Active Changes

The `cotton-detection-reliability` OpenSpec change is currently active and addresses
overlapping concerns:

| Reliability Change Scope | YOLOX Migration Overlap |
|--------------------------|------------------------|
| Workspace distance filter (eliminate 55% wasted picks) | Independent — works with any model |
| Stereo depth tuning (reduce zero-coordinate rate) | Independent — stereo pipeline, not NN |
| Thread safety fixes | Independent — infrastructure code |
| Parameter validation (num_classes, swap_class_labels) | **Overlaps** — both touch num_classes logic |
| Border margin tuning (1% -> 5%) | Independent — post-processing filter |

**Recommendation:** Coordinate with the reliability change. The `num_classes` parameter
validation work should account for YOLOX's 3-class configuration. Do not let both changes
modify the same code independently.

---

## 19. Go/No-Go Decision Criteria

From March Field Trial Plan Section 6 (lines 343-355):

| Criterion | How to Validate | Runbook Step |
|-----------|-----------------|-------------|
| YOLOX vs YOLOv11 comparison completed | **This document** | N/A |
| Licensing confirms YOLOX suitable for commercial use | Section 2 above: **YES** (Apache 2.0) | N/A |
| YOLOX accuracy >= YOLOv11 on existing test set | Train + benchmark on cotton dataset | V4 |
| YOLOX latency on RPi acceptable (<100ms) | Measure on OAK-D Lite hardware | V3 |
| Sun glare data collection plan feasible by Mar 18 | Assess data collection timeline | V7 |

**If all YES:** Proceed with YOLOX migration (Task A6, deadline Mar 18).
**If any NO:** Stay with YOLOv11, add sun_glare as 3rd class to existing model. The
fallback still requires retraining but avoids the DepthAI integration risk.
