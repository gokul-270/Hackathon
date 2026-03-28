# YOLOX Validation Runbook

**For:** Shwetha / Arun
**Purpose:** Step-by-step checklist to validate YOLOX migration feasibility
**Deadline:** March 06, 2026 (bring completed runbook to Go/No-Go meeting)
**Companion:** [YOLOX vs YOLOv11 Comparison](YOLOX_VS_YOLOV11_COMPARISON.md)

---

## How to Use This Runbook

1. Work through sections **in order** (they are dependency-ordered)
2. Fill in the `[ ]` checkboxes and `**RESULT:**` fields as you go
3. If any **BLOCKER** step fails, **STOP** and report immediately to Udayakumar
4. Record actual commands, output snippets, and error messages — not just pass/fail
5. Bring completed runbook (or partial, with blocker explanation) to the Mar 06 meeting
6. Estimated total time: 8-12 hours (V1-V2 can be done in 2-4 hours for quick Go/No-Go signal)

---

## Pre-Requisites

Before starting, ensure you have:

- [ ] YOLOX repository cloned: `git clone https://github.com/Megvii-BaseDetection/YOLOX.git`
- [ ] YOLOX dependencies installed: `pip install -r requirements.txt` (from YOLOX repo)
- [ ] YOLOX-Tiny pre-trained weights downloaded: `yolox_tiny.pth` from YOLOX releases
- [ ] OpenVINO toolkit installed (for ONNX -> IR conversion)
- [ ] `blobconverter` installed: `pip install blobconverter`
- [ ] OAK-D Lite camera available (USB connected to dev machine)
- [ ] DepthAI Python SDK installed: `pip install depthai`
- [ ] Access to our cotton training dataset (annotations + images)
- [ ] Current YOLOv11 baseline metrics recorded (from `docs/guides/YOLO_MODELS.md`)

**RESULT — Pre-requisites status:** Most pre-requisites met. YOLOX repo cloned, blob conversion working, OAK-D Lite available. Cotton dataset accessible externally.

---

## V1: DepthAI YOLOX Node Compatibility (BLOCKER)

**Priority:** Do this FIRST. This determines the entire migration scope.
**Time estimate:** 2-4 hours
**Question:** Can YOLOX run inside DepthAI's `YoloSpatialDetectionNetwork` node?

### Step 1.1: Export YOLOX-Tiny to ONNX

```bash
# From YOLOX repo directory
python tools/export_onnx.py \
    --output-name yolox_tiny.onnx \
    -n yolox-tiny \
    -c yolox_tiny.pth \
    --input 416 416 \
    --decode_in_inference
```

- [ ] ONNX export completed without errors
- [ ] Output file: `yolox_tiny.onnx`

**GOTCHA:** The `--decode_in_inference` flag is CRITICAL. It bakes the decoding logic into
the ONNX graph. Try BOTH with and without this flag — the DepthAI node may need one
specific format.

**RESULT — ONNX export:**
- File size: _____ MB
- Export command used: _____________________________
- `--decode_in_inference` used: YES / NO
- Any warnings/errors: ____________________________

### Step 1.2: Convert ONNX to OpenVINO IR

```bash
mo --input_model yolox_tiny.onnx \
   --input_shape [1,3,416,416] \
   --data_type FP16 \
   --output_dir yolox_ir/
```

- [ ] OpenVINO IR conversion completed
- [ ] Output files: `yolox_tiny.xml` + `yolox_tiny.bin`

**GOTCHA:** Use `--data_type FP16` — Myriad X requires FP16.

**RESULT — IR conversion:**
- XML + BIN file sizes: _____ MB
- Any conversion warnings: ____________________________

### Step 1.3: Convert IR to .blob

```bash
blobconverter --openvino-xml yolox_ir/yolox_tiny.xml \
              --openvino-bin yolox_ir/yolox_tiny.bin \
              --shaves 6
```

OR use the online BlobConverter: https://blobconverter.luxonis.com/

- [ ] Blob conversion completed
- [ ] Output file: `yolox_tiny.blob`

**RESULT — Blob conversion:**
- Blob file size: _____ MB
- Shaves used: _____
- Any errors: ____________________________

### Step 1.4: Test with YoloSpatialDetectionNetwork

Write a minimal Python test script (or use `scripts/testv11.py` as template):

```python
import depthai as dai

pipeline = dai.Pipeline()

# Camera
cam = pipeline.create(dai.node.ColorCamera)
cam.setPreviewSize(416, 416)
cam.setInterleaved(False)
cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)

# Stereo
mono_left = pipeline.create(dai.node.MonoCamera)
mono_right = pipeline.create(dai.node.MonoCamera)
stereo = pipeline.create(dai.node.StereoDepth)
mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
mono_left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
mono_right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
mono_left.out.link(stereo.left)
mono_right.out.link(stereo.right)

# YOLOX as YoloSpatialDetectionNetwork
nn = pipeline.create(dai.node.YoloSpatialDetectionNetwork)
nn.setBlobPath("yolox_tiny.blob")
nn.setConfidenceThreshold(0.3)
nn.setNumClasses(2)          # Start with 2 for comparison
nn.setCoordinateSize(4)
nn.setIouThreshold(0.5)
# Do NOT set anchors (YOLOX is anchor-free, like YOLOv11)

# Depth integration
stereo.depth.link(nn.inputDepth)
nn.setDepthLowerThreshold(100)
nn.setDepthUpperThreshold(5000)
nn.setBoundingBoxScaleFactor(0.5)

# Links
cam.preview.link(nn.input)
xout = pipeline.create(dai.node.XLinkOut)
xout.setStreamName("detections")
nn.out.link(xout.input)

# Run
with dai.Device(pipeline) as device:
    q = device.getOutputQueue("detections", 4, False)
    for i in range(20):
        det = q.get()
        detections = det.detections
        print(f"Frame {i}: {len(detections)} detections")
        for d in detections:
            print(f"  label={d.label} conf={d.confidence:.3f} "
                  f"spatial=({d.spatialCoordinates.x:.0f}, "
                  f"{d.spatialCoordinates.y:.0f}, "
                  f"{d.spatialCoordinates.z:.0f})mm")
```

- [x] Script runs without crash
- [x] **DOES NOT WORK** — YOLOX output tensor format is incompatible with YoloSpatialDetectionNetwork. The node expects YOLO-style anchor-based output layout; YOLOX uses a different anchor-free output format that cannot be parsed by the on-VPU decoder.

**If DOES NOT WORK**, record the error:
```
YOLOX output tensor format incompatible with YoloSpatialDetectionNetwork on-VPU decoder.
Tested by Shwetha — blob loads but detections are garbage/absent due to output format mismatch.
```

**If DOES NOT WORK**, try without `--decode_in_inference` in Step 1.1 and repeat.

**If STILL DOES NOT WORK**, proceed to V1-ALT below.

### V1-ALT: NeuralNetwork Node Fallback Test (only if V1.4 fails)

If `YoloSpatialDetectionNetwork` doesn't work, test with generic `NeuralNetwork` node:

```python
nn = pipeline.create(dai.node.NeuralNetwork)
nn.setBlobPath("yolox_tiny.blob")
# No YOLO-specific params available
# No depth input available

cam.preview.link(nn.input)
xout = pipeline.create(dai.node.XLinkOut)
xout.setStreamName("nn_out")
nn.out.link(xout.input)

with dai.Device(pipeline) as device:
    q = device.getOutputQueue("nn_out", 4, False)
    data = q.get()
    # Print raw tensor shapes
    for tensor_name in data.getAllLayerNames():
        tensor = data.getTensor(tensor_name)
        print(f"Tensor '{tensor_name}': shape={tensor.shape}, dtype={tensor.dtype}")
```

- [x] NeuralNetwork node loads the blob successfully
- [x] Raw output tensors are accessible
- [x] Record ALL tensor names and shapes

**RESULT — NeuralNetwork fallback:**
Tested by Shwetha/Arun using standalone script with NeuralNetwork + SpatialLocationCalculator.
- NeuralNetwork node runs YOLOX inference on VPU successfully
- Host performs NMS (< 1 ms) then sends bounding boxes back to VPU via SpatialLocationCalculator for depth
- Tested with custom YOLOX model (50 epochs) at 640x640 — WORKS
- Tested at 416x416 (production input size) — WORKS
- Pipeline: VPU (inference) → Host (NMS, < 1 ms) → VPU (depth via SpatialLocationCalculator)

**Architecture comparison:**
- `YoloSpatialDetectionNetwork` — VPU handles everything (inference + NMS + depth)
- `NeuralNetwork + SpatialLocationCalculator` — VPU runs inference, host does NMS (< 1 ms), then sends boxes back to VPU for depth

**Decision: Proceed with NeuralNetwork + SpatialLocationCalculator approach.**

---

## V2: Blob Conversion Pipeline Verification

**Time estimate:** 1-2 hours
**Purpose:** Confirm the full training-to-blob pipeline works end-to-end.

### Step 2.1: Verify blob loads on actual OAK-D Lite

- [ ] The blob from V1 loads on OAK-D Lite (not just any OAK-D model)
- [ ] No USB bandwidth errors
- [ ] Camera preview appears (passthrough works)

**RESULT — OAK-D Lite loading:**
- USB speed detected: _____ (should be 3.0 / 5Gbps)
- Any device errors: ____________________________

### Step 2.2: Compare blob sizes

| Model | Blob Size | Notes |
|-------|----------|-------|
| yolov112.blob (current production) | 5.5 MB | Baseline |
| yolox_tiny.blob (new) | _____ MB | Record |

**GOTCHA:** If YOLOX blob is significantly larger (>10MB), it may impact loading time and
VPU memory. The Myriad X has limited on-chip memory.

### Step 2.3: Document the exact conversion commands

Record the EXACT commands that worked (including all flags) so we can reproduce:

```bash
# Step 1: PyTorch -> ONNX
_____________________________________________

# Step 2: ONNX -> OpenVINO IR
_____________________________________________

# Step 3: OpenVINO IR -> .blob
_____________________________________________
```

---

## V3: Inference Latency on OAK-D Lite

**Time estimate:** 1-2 hours
**Prerequisite:** V1 passed (blob loads and produces detections)
**Target:** p50 < 100ms (from March plan). Ideal: p50 < 80ms.

### Step 3.1: Run 100 inference cycles

Use the test script from V1.4 or adapt `scripts/testing/detection/quick_test.py`:

- Point camera at a scene with some objects (cotton samples if available, or any objects)
- Record inference time for 100 frames (exclude first 10 as warm-up)
- Compute: min, p50, p95, p99, max

**GOTCHA:** First 5-10 inferences are warm-up (model loading, cache filling). Exclude them.

**RESULT — YOLOX-Tiny latency (100 frames, warm-up excluded):**

| Metric | YOLOX-Tiny | YOLOv11 Baseline |
|--------|-----------|-----------------|
| Min | _____ ms | — |
| p50 | _____ ms | 69 ms |
| p95 | _____ ms | 85 ms |
| p99 | _____ ms | — |
| Max | _____ ms | — |

- [ ] **PASS:** p50 < 100ms
- [ ] **IDEAL:** p50 < 80ms
- [ ] **FAIL:** p50 >= 100ms (try YOLOX-Nano as fallback)

### Step 3.2: Thermal observation (15-minute run)

Run the model continuously for 15 minutes and record OAK-D Lite temperature:

**RESULT — Thermal:**
- Start temp: _____ C
- End temp (15 min): _____ C
- Rate: _____ C/min
- YOLOv11 baseline: 51-63C range, +0.02C/min

### Step 3.3: (If V3.1 FAILS) Test YOLOX-Nano

Repeat V1 + V2 + V3 with YOLOX-Nano (`yolox_nano.pth`, 0.91M params, 1.08G FLOPs).

**RESULT — YOLOX-Nano latency:** p50 = _____ ms

---

## V4: Detection Accuracy on Cotton Dataset

**Time estimate:** 4-6 hours (including training)
**Prerequisite:** V1 passed, V3 latency acceptable
**Target:** mAP >= YOLOv11 on existing cotton test set. Overall accuracy 90-95%.

### Step 4.1: Annotation format conversion

Convert existing cotton annotations from YOLO txt format to COCO JSON format.

Tools:
- `pylabel`: `pip install pylabel`
- Or manual conversion script
- Or re-export from labeling tool (Roboflow/CVAT/LabelStudio)

- [ ] Converted annotations to COCO JSON format
- [ ] Verified conversion: spot-checked 10 images, bounding boxes match originals
- [ ] Class mapping preserved: 0=cotton, 1=not_pickable

**GOTCHA:** YOLO txt uses normalized coordinates (`cx cy w h` in 0-1 range). COCO JSON
uses absolute pixel coordinates (`x y w h` in pixels). Verify the conversion handles this.

**RESULT — Annotation conversion:**
- Tool used: _____________________________
- Total images: _____
- Total annotations: _____
- Classes in converted dataset: _____________________________

### Step 4.2: Create YOLOX experiment config

Create a custom `Exp` class for cotton detection:

```python
# exps/cotton_exp.py
from yolox.exp import Exp as BaseExp

class Exp(BaseExp):
    def __init__(self):
        super().__init__()
        self.num_classes = 2  # Start with 2 (cotton, not_pickable)
        self.depth = 0.33     # Tiny depth
        self.width = 0.375    # Tiny width
        self.input_size = (416, 416)
        self.test_size = (416, 416)
        self.max_epoch = 100  # Adjust based on dataset size
        self.data_dir = "/path/to/cotton/dataset"
        self.train_ann = "instances_train.json"
        self.val_ann = "instances_val.json"
```

- [ ] Experiment config created
- [ ] Dataset path configured correctly
- [ ] Input size matches our pipeline (416x416)

### Step 4.3: Train YOLOX-Tiny on cotton dataset

```bash
python tools/train.py \
    -f exps/cotton_exp.py \
    -c yolox_tiny.pth \
    -d 1 \
    -b 16 \
    --fp16
```

- [ ] Training started successfully
- [ ] Training completed (record epochs, final loss)
- [ ] Best model checkpoint saved

**RESULT — Training:**
- Total epochs: _____
- Final training loss: _____
- Best validation mAP: _____
- Training time: _____ hours
- GPU used: _____________________________

### Step 4.4: Evaluate on validation set

```bash
python tools/eval.py \
    -f exps/cotton_exp.py \
    -c best_ckpt.pth \
    -d 1 \
    --fp16
```

- [ ] Evaluation completed

**RESULT — YOLOX accuracy:**

| Metric | YOLOX-Tiny | YOLOv11 Baseline | Pass? |
|--------|-----------|-----------------|-------|
| mAP@0.5 | _____ | _____ | _____ |
| Precision | _____ | _____ | _____ |
| Recall | _____ | _____ | _____ |
| F1 | _____ | _____ | _____ |
| Per-class AP (cotton) | _____ | _____ | _____ |
| Per-class AP (not_pickable) | _____ | _____ | _____ |

- [ ] **PASS:** YOLOX mAP >= YOLOv11 mAP
- [ ] **FAIL:** YOLOX mAP < YOLOv11 mAP (record by how much)

### Step 4.5: Convert trained model to .blob and test

Repeat V1.1 -> V1.3 with the cotton-trained model, then verify detections make sense:

- [ ] Cotton-trained YOLOX blob produces cotton detections on real cotton images
- [ ] Confidence values are reasonable for cotton (>0.5 for clear bolls)
- [ ] Not-pickable class works correctly

---

## V5: Spatial Depth Output Verification

**Time estimate:** 1-2 hours
**Prerequisite:** V1-ALT passed (using NeuralNetwork + SpatialLocationCalculator)
**Purpose:** Verify 3D spatial coordinates are correct.

### Step 5.1: Compare spatial output for same scene

Point camera at a fixed scene. Run both YOLOv11 (current blob) and YOLOX (new blob) and
compare spatial coordinates for the same detected object:

| Object | YOLOv11 (x,y,z mm) | YOLOX (x,y,z mm) | Difference |
|--------|--------------------|--------------------|------------|
| Object 1 | (___,___,___) | (___,___,___) | (___,___,___) |
| Object 2 | (___,___,___) | (___,___,___) | (___,___,___) |
| Object 3 | (___,___,___) | (___,___,___) | (___,___,___) |

- [ ] Spatial coordinates are populated (not all zeros)
- [ ] Coordinates are in reasonable range (z = 150-800mm for near objects)
- [ ] Difference between YOLOv11 and YOLOX is < 50mm for same object

**GOTCHA:** Spatial coordinates come from stereo depth, not the NN model. BUT the bounding
box from the NN determines the ROI for depth sampling. Different bounding box size/position
= different depth reading.

### Step 5.2: Zero-coordinate rate

Run 100 detections. Count how many have (0,0,0) spatial coordinates:

**RESULT:**
- Total detections: _____
- Zero spatial: _____ (_____ %)
- YOLOv11 baseline: 17%

---

## V6: Post-Processing Compatibility

**Time estimate:** 1-2 hours
**Purpose:** Verify the detection pipeline handles YOLOX output correctly.

### Step 6.1: Class ID mapping

Run YOLOX on a scene with both cotton and non-cotton objects. Verify:

- [ ] Class 0 = cotton (detected correctly)
- [ ] Class 1 = not_pickable (detected correctly)
- [ ] No unexpected class IDs appear

### Step 6.2: Confidence score distribution

Record confidence scores from 50 detections and plot distribution:

- [ ] Scores are in 0.0 - 1.0 range (DepthAI sometimes returns >1.0, verify clamping works)
- [ ] Score distribution is similar to YOLOv11 (most cotton detections > 0.5)
- [ ] The existing threshold chain makes sense:
  - 0.3 (on-device) — filters very low confidence
  - 0.7 (post-detection) — keeps only high-confidence for picking
  - 0.55 (yanthra_move) — downstream safety check

**GOTCHA:** YOLOX confidence = objectness x class_probability. If the DepthAI node doesn't
handle the two-stage multiplication internally, confidence values may be different. You
might need to re-tune the 0.3 on-device threshold. The 0.7 post-detection threshold
provides a safety buffer.

**RESULT — Confidence distribution:**
- Min confidence seen: _____
- Max confidence seen: _____
- Median confidence: _____
- % of cotton detections > 0.5: _____ %
- % of cotton detections > 0.7: _____ %
- Does existing threshold chain work well? YES / NO / NEEDS TUNING

### Step 6.3: NMS behavior

Check for duplicate/overlapping detections on the same object:

- [ ] No excessive duplicates (NMS working correctly)
- [ ] IOU threshold 0.5 is adequate

---

## V7: Sun Glare Class Feasibility

**Time estimate:** 1-2 hours (assessment only, not training)
**Purpose:** Assess feasibility of adding sun_glare as 3rd class by Mar 18.

### Step 7.1: Data collection plan

- [ ] How many sun_glare training images are needed? (estimate: _____)
- [ ] Where will images come from? (field, synthetic, internet)
- [ ] Can images be collected and annotated by Mar 14 (4 days before deadline)?
- [ ] What does sun_glare look like in OAK-D Lite images? (bright patches, washed-out areas)

### Step 7.2: 3-class model impact

- [ ] Does adding a 3rd class significantly increase model size? (check YOLOX-Tiny with 3 vs 2 classes)
- [ ] Expected latency impact of 3rd class? (typically negligible)

**RESULT — Sun glare plan:**
- Estimated images needed: _____
- Collection method: _____________________________
- Feasible by Mar 14? YES / NO
- Impact on model size/latency: _____________________________

---

## V8: Host-Side NMS (CONDITIONAL — only if V1 FAILS)

**Time estimate:** 2-4 hours
**Prerequisite:** V1 FAILED (YoloSpatialDetectionNetwork incompatible)
**Purpose:** Measure cost of doing YOLOX post-processing on RPi 4B CPU.

### Step 8.1: NMS latency on RPi 4B

If using NeuralNetwork node (V1-ALT), you need host-side:
1. Output tensor decoding (stride-based coordinate decode)
2. objectness x class_prob confidence computation
3. NMS
4. Depth sampling from stereo depth map

Measure each on RPi 4B (not dev machine):

| Operation | Latency (RPi 4B) | Notes |
|-----------|-----------------|-------|
| Tensor decode | _____ ms | |
| Confidence compute | _____ ms | |
| NMS | _____ ms | Target: < 10ms |
| Depth sampling | _____ ms | |
| **Total** | **_____ ms** | Target: < 20ms total |

### Step 8.2: CPU utilization impact

- [ ] Measure CPU utilization before (YOLOv11 with on-device processing): _____ %
- [ ] Measure CPU utilization after (YOLOX with host-side NMS): _____ %
- [ ] Remaining CPU headroom for ROS2 nodes, motor control, CAN bus: _____ %

**GOTCHA:** RPi 4B is already running ROS2 nodes, motor control, CAN bus communication.
Adding host-side NMS takes CPU budget away from these. If total CPU > 80%, this is a
concern.

---

## What You Might Miss (Common Gotchas)

These are issues discovered during deep codebase analysis that are easy to overlook:

### 1. `arm_launcher.sh` has a hardcoded blob path

`scripts/launch/arm_launcher.sh:73` has:
```
depthai_model_path=/home/ubuntu/pragati_ros2/data/models/yolov112.blob
```
This is the **actual** production launch script on RPi. Updating `production.yaml` alone
is not enough — this hardcoded path overrides it.

### 2. Three confidence thresholds, not one

Changing one threshold is not enough. The chain is:
- 0.3 on-device (VPU) → `production.yaml: depthai.confidence_threshold`
- 0.7 post-detection (host) → `production.yaml: detection_confidence_threshold`
- 0.55 downstream (yanthra_move) → `yanthra_move/config/production.yaml: YoloThreshold`

### 3. `num_classes` controls anchor behavior, not just class count

In `depthai_manager.cpp:1843`, `num_classes == 1` triggers YOLOv8 anchor path. If YOLOX
is trained with 1 class for initial testing, it would incorrectly set YOLOv8 anchors.
Always use `num_classes >= 2` during YOLOX testing.

### 4. Production model is NOT tested by existing test scripts

`test_model_switching.sh` tests `yolov8.blob`, `yolov8v2.blob`, and the legacy openvino
blob — but never `yolov112.blob` (the actual production model). Record YOLOv11 baseline
metrics BEFORE migration so we have numbers to compare against.

### 5. No training infrastructure in the repo

There are zero training scripts, zero dataset files, zero annotation files in the repo.
All training is done externally. Document your YOLOX training steps thoroughly so they
can be reproduced.

### 6. Annotation format conversion required

Current annotations: YOLO txt format (`class cx cy w h` normalized).
YOLOX requires: COCO JSON format (`instances.json` with absolute pixel coordinates).
No conversion tool exists in the repo — you need to build or find one.

### 7. `swap_class_labels` is dead code

This parameter exists in `production.yaml` and is declared in the C++ parameters, but is
never actually loaded or used. Don't waste time trying to make it work for YOLOX — it
doesn't do anything.

### 8. Launch file default is 2 generations behind

`cotton_detection_cpp.launch.py:83` defaults to `yolov8v2.blob` and `num_classes: 1`.
Production uses `yolov112.blob` and `num_classes: 2`. The launch defaults are stale but
overridden at runtime. When updating for YOLOX, update BOTH the launch defaults AND
production config.

### 9. `cotton-detection-reliability` change is active

There is an ongoing OpenSpec change (`cotton-detection-reliability`) that modifies
overlapping code (workspace filtering, `num_classes` validation, stereo depth tuning).
Check with Udayakumar on coordination — don't make conflicting changes to the same files.

### 10. Thermal throttling in field conditions

The Feb trial measured OAK-D Lite at 51-63C. The `cotton-detection-reliability` change
includes thermal shutdown logic. A different model with different FLOPs could change the
thermal profile. Run the 15-minute thermal test (V3.2) with the camera in a warm
environment if possible.

---

## Results Summary (for Go/No-Go Meeting)

Fill this table and bring to the March 06 meeting:

| Go/No-Go Criterion | Runbook Step | Result | Pass? |
|--------------------|-------------|--------|-------|
| Comparison document completed | N/A | YOLOX_VS_YOLOV11_COMPARISON.md | YES |
| Licensing suitable for commercial | N/A | Apache 2.0 | YES |
| YOLOX loads in DepthAI pipeline | V1 / V1-ALT | V1 FAIL (output format incompatible), V1-ALT PASS (NN+SLC works at 416x416, NMS <1ms) | YES (via V1-ALT) |
| YOLOX accuracy >= YOLOv11 | V4 | mAP: _________ | NOT TESTED |
| YOLOX latency < 100ms on OAK-D Lite | V3 | p50: _______ ms | NOT TESTED |
| Spatial coordinates work | V5 | _____________ | NOT TESTED |
| Sun glare data collection feasible by Mar 18 | V7 | _____________ | NOT TESTED |
| Confidence thresholds adequate | V6 | _____________ | NOT TESTED |
| Host-side NMS acceptable (if needed) | V8 | < 1 ms (Shwetha/Arun standalone test) | YES |

### Decision

- [ ] **GO** — All criteria passed. Proceed with YOLOX migration (Task A6, deadline Mar 18)
- [ ] **NO-GO** — One or more blockers. Stay with YOLOv11. Fallback: add sun_glare as 3rd
      class to existing YOLOv11 model
- [ ] **CONDITIONAL GO** — Go with caveats (document what caveats): _______________________

### Blockers Found (if any)

| Blocker | Description | Estimated Fix Time |
|---------|-------------|-------------------|
| | | |
| | | |
| | | |

### Additional Observations

(Free-form notes, unexpected findings, things to investigate further)

```
_____________________________________________________________________________
_____________________________________________________________________________
_____________________________________________________________________________
_____________________________________________________________________________
```
