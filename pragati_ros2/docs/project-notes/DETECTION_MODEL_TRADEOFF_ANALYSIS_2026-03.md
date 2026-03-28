# Detection Model Trade-Off Analysis — Root Cause and Resolution Path

**Date:** March 25, 2026 (updated March 26 — arm_1 morning session data added)
**Trigger:** March 25 field trial — neither detection model is production-ready
**Author:** Post-trial analysis
**Status:** Open — awaiting team decision on retraining path
**Related:** FIELD_TRIAL_REPORT_MAR25_2026.md (sections 3.4, 3.5, 5.3)

---

## 1. Executive Summary

The March 25, 2026 field trial exposed a fundamental trade-off between the two available
detection models. **YOLOv11** (2-class: cotton + not-pickable) filters empty cotton shells
but misses real cotton under field lighting conditions. **YOLOv5** (1-class: cotton only)
detects more cotton but cannot distinguish cotton from empty shells, inflating detection
counts with false positives that waste arm movements.

Operators switched from v11 to v5 mid-trial on arm_2 to increase detection volume. This
improved raw detection numbers but increased the wasted detection rate from 48.9% to 57.3%.
Neither model is satisfactory for production use.

**Root cause:** This is a training data and model architecture gap, not a software bug.
Both models were trained on datasets that do not adequately represent the target field
(Manivel's field, Nedungur) conditions. v11 is undertrained for field lighting. v5 lacks
the class structure to reject shells.

**Recommendation:** Retrain v11 with augmented field data (Option A) as the primary path,
with a confidence-gating heuristic (Option D) as a short-term workaround.

---

## 2. Background

### 2.1 Model Specifications

| Property | YOLOv11 (v11) | YOLOv5 (v5) |
|----------|---------------|-------------|
| Blob file | `yolov112.blob` | `best_openvino_2022.1_6shave.blob` |
| Architecture | YOLOv11 (Ultralytics) | YOLOv5 (Ultralytics) |
| Classes | 2: `cotton` (label 0), `not-pickable` (label 1) | 1: `cotton` (label 0) |
| License | AGPL-3.0 | GPL-3.0 |
| DepthAI integration | YoloSpatialDetectionNetwork | YoloSpatialDetectionNetwork |
| Deployment | Both arms, primary model | Backup model, loaded mid-trial |

The `not-pickable` class in v11 was specifically added to filter empty cotton shells — bolls
where the cotton fiber has already fallen out, been picked, or never fully developed. These
shells are structurally similar to cotton bolls (same shape, similar size) but contain no
harvestable material. Sending the arm to pick an empty shell wastes a full pick cycle
(3-4 seconds) and contributes to the wasted detection rate.

### 2.2 Trial Context

The March 25 trial was the second field trial with the full system (vehicle + 2 arms).
Stop-and-pick mode: the vehicle drives to a position, stops, both arms scan and pick,
then the vehicle advances. Four vehicle sessions were run across approximately 7.5 hours
(Session 4 was post-E-stop with CAN bus dead — no picking operation).

---

## 3. Evidence from March 25 Field Data

### 3.1 Model Performance Comparison

| Metric | YOLOv11 (2-class) | YOLOv5 (1-class) |
|--------|-------------------|-------------------|
| Arm assignment | arm_1 (all day) | arm_2 (Sessions 3-5) |
| Detection rate | 14.8-15.8% | 21.5-28.7% |
| Average confidence | 0.680 | 0.729 |
| Not-pickable filter | 20.8% of raw detections filtered | 0% — no shell class |
| Inference latency | 72ms avg | 66ms avg |
| Wasted detection rate | 48.9% | 57.3% |
| False positive type | Fewer — shells filtered by 2nd class | More — shells detected as cotton |
| Pick success rate | 52.5% (214/408 attempts) | 53.3% (278/522 attempts) |
| When cotton IS reachable | 98.4% success | 98.4% success |

The "when cotton is reachable" rate is identical for both models. The difference in overall
pick success is driven entirely by how many non-cotton or unreachable targets each model
sends to the arm.

### 3.2 Detection Funnel Comparison

**arm_1 (v11, all sessions including morning):**

```
Raw NN detections:          ~N (100%)
  Zero-spatial filtered:    ~13% (stereo depth failure)
  Border filtered:          12.0-52.0% (varies by J4 config)
  Not-pickable filtered:    20.8% (empty shells, label=1)
  Accepted (label=0):       408 → 214 picked (47.5% wasted)
```

**arm_2 (v5, Sessions 3-5):**

```
Raw NN detections:          ~N (100%)
  Zero-spatial filtered:    ~13% (stereo depth failure)
  Border filtered:          1.0% (much lower — single class, broader acceptance)
  Not-pickable filtered:    0% (no shell class)
  Accepted:                 651 → 278 picked (57.3% wasted)
```

v5 accepted nearly 1.6x more detections (651 vs 408), but only produced 1.3x more picks
(278 vs 214). The gap is the shell false positive overhead: v5's extra detections include
empty shells that pass all filters but produce no cotton when picked.

### 3.3 Wasted Detection Breakdown

"Wasted detections" include all accepted detections that did not result in a successful
pick. The sources of waste differ between models:

| Waste Source | v11 (arm_1) | v5 (arm_2) | Notes |
|-------------|-------------|------------|-------|
| Workspace rejections (unreachable) | Primary source | Primary source | Both arms share this limitation |
| Border filter (edge detections) | Significant (12-52%) | Low (1%) | v11 more aggressive filtering |
| Zero spatial coordinates | ~13% | ~13% | Stereo depth failure, equal for both |
| Shell false positives | Near zero | Unknown % | v5-specific; these waste full pick cycles |
| Total wasted | 47.5% | 57.3% | +9.8pp gap attributable to shell FPs |

The 9.8 percentage point difference in wasted detections (57.3% vs 47.5%) between v5 and
v11 is a direct measure of the shell false positive problem. This represents arm movements
to empty positions — each wasting approximately 3.4 seconds of cycle time.

### 3.4 Model Switch Timeline

| Time (IST) | Event | Model | Notes |
|------------|-------|-------|-------|
| 10:44 | Trial start | v11 on both arms | Both arms operational |
| 10:49 | arm_2 Session 1 starts | v11 | 20 cycles, 12 attempts, 6 picked (50%) |
| ~11:08 | Operators note low detection on arm_2 | v11 | Field lighting suspected |
| 11:10 | arm_2 Session 2: switch to v5 | v5 (misconfigured) | Set `classes=2` instead of 1 |
| 11:10 | 0 detections in 65 seconds | v5 (broken) | Wrong class count kills detection |
| 11:10 | Session killed | — | Operator intervenes |
| 11:12 | arm_2 Session 3: v5 corrected | v5 (`classes=1`) | 119 cycles, 205 attempts, 124 picked |
| 11:12-18:11 | v5 runs for rest of day on arm_2 | v5 | Sessions 3-5 stable |
| All day | arm_1 stays on v11 | v11 | 319 cycles, 408 attempts, 214 picked |

The misconfiguration in Session 2 (setting `classes=2` for a 1-class model) is a secondary
finding. It indicates that the model-switching procedure lacks validation — the system
accepted an impossible class count without error and silently produced zero detections.

---

## 4. Root Cause Analysis

This is **not a software bug**. The detection pipeline, filtering logic, and pick execution
all function correctly. The problem is a gap between the training data distribution and the
operational environment.

### 4.1 Why v11 Misses Cotton in Field Conditions

The v11 model was trained on a dataset that does not fully represent field lighting. Specific
failure modes observed or inferred:

1. **Direct sunlight and glare.** White cotton fiber is highly reflective. Direct sunlight
   creates specular highlights that alter the appearance of cotton bolls compared to
   controlled-lighting training images. The model may classify sun-lit cotton as background
   or as not-pickable due to altered color/texture features.

2. **Shadow patterns.** Field conditions produce complex shadow patterns from leaves, stems,
   and adjacent plants. Cotton in deep shadow or partial shadow looks different from the
   uniform backgrounds in training data.

3. **Bloom stage variation.** Cotton bolls at different maturity stages (tight, partially
   open, fully open, over-mature) have significantly different visual characteristics. If
   the training set over-represents one bloom stage, the model will underperform on others.

4. **Confidence threshold interaction.** The 2-class model must discriminate between cotton
   and not-pickable with sufficient confidence. In ambiguous lighting, the model's confidence
   may drop below the detection threshold even for real cotton — effectively choosing
   "uncertain" over "wrong class." This is a correct failure mode for classification but
   results in missed detections.

5. **Training set composition.** The 2-class model requires negative examples (shells) that
   are visually distinct from positive examples (cotton). If the training set's shell images
   were collected in controlled conditions, the model may have learned lighting-dependent
   features rather than structural features for discrimination.

### 4.2 Why v5 Produces Shell False Positives

The v5 model has a structural limitation that no amount of training data can fix within its
current 1-class architecture:

1. **No negative class.** With only the `cotton` class, v5 can either detect something as
   cotton or not detect it at all. It has no concept of "this looks like a cotton boll but
   is empty." Empty shells share the same shape, size, and growth position as cotton bolls.

2. **Visual similarity.** Empty cotton shells (tan/brown open boll structures) occupy the
   same bounding box profile as cotton-filled bolls. The distinguishing feature — the
   presence of white fiber inside the boll — requires the model to attend to fine internal
   texture, which a 1-class object detector is not trained to evaluate.

3. **No negative training examples.** v5 was trained without explicit negative examples of
   shells. The model learned "boll shape = cotton" rather than "boll shape with white fiber
   = cotton."

4. **Architectural limitation.** This is not fixable by retraining v5 with more data while
   keeping 1 class. Regardless of training diversity, a 1-class model cannot output "not
   cotton" for a detection — it can only suppress the detection entirely, which requires
   the shell to look sufficiently unlike anything in the training set. Since shells look
   very much like cotton bolls, suppression does not reliably occur.

### 4.3 Why Both Models Are Unsatisfactory

```
                        Detects real cotton    Rejects empty shells
                        in field lighting?     (false positive control)?
                        ─────────────────      ──────────────────────
    YOLOv11 (2-class)         NO                      YES
    YOLOv5 (1-class)          YES                     NO
    Production need           YES                     YES
```

Neither model meets both requirements. The production system needs a model that detects
real cotton reliably under field lighting conditions AND rejects empty shells to avoid
wasting arm cycles.

### 4.4 Contributing Factor: No Field-Specific Training Data

Both models were trained on datasets that predate field deployment. The target field
(Manivel's field, Nedungur) has specific characteristics — soil color, row spacing, weed
density, typical lighting angles — that are not represented in the training data. This is
a common gap in agricultural robotics: lab-to-field transfer performance consistently
underperforms expectations.

The March 25 trial cameras saved images throughout the day. These images constitute the
first large-scale field dataset from the actual deployment environment and are the critical
input for any retraining effort.

---

## 5. Options for Resolution

### 5.1 Option A: Retrain v11 with Field Data (Recommended)

**Approach:** Collect images from March 25 trial (cameras save every frame). Annotate with
2 classes (cotton, not-pickable) under field conditions. Augment the existing v11 training
dataset with this field data. Retrain and validate.

**What this fixes:**
- v11's field lighting sensitivity (root cause: insufficient training diversity)
- Preserves the shell filtering capability (2-class architecture retained)
- Uses the proven DepthAI integration (YoloSpatialDetectionNetwork, no pipeline changes)

**What this does NOT fix:**
- Licensing risk (AGPL-3.0 remains; see YOLOX_VS_YOLOV11_COMPARISON.md)
- Edge cases not present in March 25 data (different weather, time of year)

**Effort estimate:**
- Image extraction from trial logs: 1-2 days
- Annotation (2-class labeling): 3-5 days depending on dataset size and tooling
- Training and hyperparameter tuning: 1-2 days
- Validation on held-out field images: 1 day
- Deployment and smoke test: 0.5 days
- **Total: 1-2 weeks**

**Risk:** Medium. The retrained model may not fully close the lab-to-field gap if March 25
conditions are not representative of all future field conditions (e.g., different time of
day, overcast vs. sunny, wet cotton after rain). Iterative retraining across multiple field
trials may be necessary.

### 5.2 Option B: Retrain v5 with 2 Classes

**Approach:** Take the YOLOv5 architecture and retrain with 2 classes (cotton + not-pickable)
using the same augmented field dataset.

**What this fixes:**
- v5's shell false positive problem (adds the not-pickable class)
- Leverages v5's demonstrated better raw detection in field conditions

**What this does NOT fix:**
- Licensing risk (GPL-3.0, similar restrictions to AGPL-3.0)
- Unknown whether v5 architecture can discriminate 2 classes as well as v11

**Effort estimate:** 1-2 weeks (same as Option A — the annotation work is identical).

**Risk:** Medium. v5's architecture is older and may have lower 2-class discrimination
accuracy than v11. The "better field detection" of v5 may partly be an artifact of its
lower discrimination bar (1 class = easier to detect something), which would diminish with
2 classes. This is an untested combination.

### 5.3 Option C: Train New Model (YOLOX) for Field Conditions

**Approach:** Start fresh with YOLOX (Apache 2.0 license), which was evaluated in
YOLOX_VS_YOLOV11_COMPARISON.md and validated for DepthAI pipeline compatibility
(NeuralNetwork + SpatialLocationCalculator node, host-side NMS confirmed < 1ms by
Shwetha/Arun).

**What this fixes:**
- Licensing risk (Apache 2.0 — free for commercial use, no source disclosure)
- Can design class structure from scratch (cotton, not-pickable, potentially sun_glare)
- Clean training pipeline with all field data from the start

**What this does NOT fix:**
- Requires full DepthAI pipeline migration (YoloSpatialDetectionNetwork is incompatible
  with YOLOX output format — confirmed in March 06 Go/No-Go Decision 1)
- Unproven accuracy and latency on RPi 4B hardware
- Significant engineering effort beyond just model training

**Effort estimate:**
- Pipeline migration (NeuralNetwork + SpatialLocationCalculator): 3-5 days
- Training pipeline setup (COCO JSON annotation format, different from YOLO txt): 2-3 days
- Training and tuning: 2-3 days
- Integration testing on RPi: 2-3 days
- **Total: 2-4 weeks**

**Risk:** High. YOLOX migration was explicitly deferred at the March 06 Go/No-Go decision
because accuracy and latency were unproven on field hardware. The pipeline change
(NeuralNetwork + SpatialLocationCalculator instead of YoloSpatialDetectionNetwork) touches
the core detection pipeline and requires thorough validation. See YOLOX_VALIDATION_RUNBOOK.md
for the validation procedure.

**Note:** Option C remains the right long-term path for commercial deployment due to
licensing. The question is timing — should it be done now (blocking the next trial) or
after resolving the immediate detection gap with Option A?

### 5.4 Option D: Confidence Gating Heuristic (Short-Term Workaround)

**Approach:** Continue using v5 but add post-detection heuristics to reject likely shells:
- Confidence threshold tuning: shells may cluster at lower confidence than real cotton
- Bounding box size filtering: empty shells may have different aspect ratios
- Depth profile analysis: shells at certain depths may correlate with empty positions

**What this fixes:**
- Reduces (but does not eliminate) shell false positives without retraining
- Can be deployed immediately for the next trial

**What this does NOT fix:**
- Fundamentally heuristic — cannot match the discrimination of a 2-class model
- May reject valid cotton detections along with shells (precision/recall trade-off)
- Does not address v11's field lighting sensitivity
- Not a permanent solution

**Effort estimate:** 1-3 days (confidence threshold tuning + basic filtering logic).

**Risk:** Low effort but low ceiling. The heuristic may reduce shell false positives by
20-40% at best, and any threshold aggressive enough to reject most shells will also reject
some real cotton. This is a band-aid, not a fix.

---

## 6. Analysis: Why Option A is Recommended

### 6.1 Decision Matrix

| Criterion | Weight | A: Retrain v11 | B: Retrain v5 | C: YOLOX | D: Heuristic |
|-----------|--------|----------------|---------------|----------|-------------|
| Fixes field lighting gap | High | Yes | Likely | Yes | No |
| Preserves shell filtering | High | Yes | Likely | Yes | Partial |
| Effort to deploy | Medium | 1-2 wk | 1-2 wk | 2-4 wk | 1-3 days |
| Pipeline risk | High | None | None | High | Low |
| Licensing risk | Low (near-term) | AGPL remains | GPL remains | Resolved | GPL remains |
| Proven architecture | Medium | Yes | Untested 2-class | Untested | N/A |
| Long-term viability | Medium | Medium | Low | High | None |

### 6.2 Rationale

1. **Option A addresses the root cause directly.** The problem is training data, not
   architecture. v11 has the correct class structure (cotton + not-pickable). Adding field
   images to the training set targets the specific gap identified on March 25.

2. **Zero pipeline risk.** v11 runs on YoloSpatialDetectionNetwork, the same DepthAI
   integration used in both field trials. No code changes to the detection pipeline. No
   integration risk.

3. **Option D as a bridge.** If v11 retraining is not complete before the next trial,
   Option D can be deployed in 1-3 days to partially mitigate v5's shell false positives.
   This is not a replacement for retraining but buys time.

4. **Option C deferred, not abandoned.** YOLOX remains the correct long-term choice for
   commercial licensing. But the immediate priority is a working detection model for the
   next field trial. Retraining v11 (Option A) is the fastest path to a model that both
   detects cotton in field conditions and rejects shells.

5. **Option B is the weakest choice.** It combines the unproven (v5 with 2 classes has
   never been tested) with the same licensing problem. If the annotation work is being done
   anyway, that effort is better spent on v11 (proven 2-class architecture) or YOLOX
   (better licensing).

---

## 7. Decisions Needed

| # | Decision | Owner | Deadline | Notes |
|---|----------|-------|----------|-------|
| 1 | Who extracts and annotates field images from March 25? | Shwetha / Arun | TBD | Images saved by cameras on both arms. Annotation tooling (CVAT, Roboflow, or similar) needs to be selected. |
| 2 | Retraining timeline — can v11 be retrained before the April trial? | Shwetha / Arun | TBD | Depends on annotation volume and training infrastructure availability. |
| 3 | Should Option D (confidence gating) be implemented as a bridge? | Udayakumar | TBD | Only needed if retraining will not complete before next trial. |
| 4 | Should YOLOX migration (Option C) be elevated to active or remain deferred? | Team | TBD | See YOLOX_VS_YOLOV11_COMPARISON.md and March 06 Decision 1. Licensing risk grows with each deployed unit. |
| 5 | Should a model-switching validation check be added to the detection node? | Udayakumar | TBD | Session 2 misconfiguration (`classes=2` for a 1-class model) silently produced 0 detections. A startup check could validate class count against the loaded blob. |

---

## 8. Metrics for Success

A resolved detection model must meet all of the following before being declared
production-ready:

| Metric | Target | Current (v11) | Current (v5) | Rationale |
|--------|--------|---------------|-------------|-----------|
| Detection rate (field conditions) | >= 20% | 14.8-15.8% | 21.5-28.7% (inflated) | Must match or exceed v5 without shell inflation |
| Wasted detection rate | < 40% | 47.5% | 57.3% | Down from both current values |
| Shell false positive rate | < 5% | ~0% (shells filtered) | Unknown (no measurement) | Must actively reject shells |
| Inference latency (RPi 4B) | < 80ms | 72ms | 66ms | No regression from current |
| Confidence average | > 0.65 | 0.680 | 0.729 | Maintain discrimination quality |
| Pick success rate (overall) | > 60% | 52.5% | 53.3% | Regression from v11 baseline with more data |
| Pick success rate (reachable) | > 95% | 98.4% | 98.4% | Maintain current mechanical excellence |

**Validation method:** Run the retrained model on a held-out set of March 25 field images
with ground-truth annotations. Measure detection rate, shell rejection rate, and confidence
distribution. Then validate on-hardware with a short field test before committing to a full
trial.

---

## 9. Secondary Finding: Model Switch Procedure Gap

The Session 2 misconfiguration (v5 loaded with `classes=2`) reveals a procedural gap. The
detection node accepts any `classes` parameter without validating it against the loaded
model's actual output shape. This allowed a silent failure: zero detections with no error
or warning in logs.

**Recommendation:** Add a startup validation check in the detection node that:
1. Loads the model blob
2. Inspects the output tensor shape to determine the actual class count
3. Compares against the configured `classes` parameter
4. Logs an ERROR and refuses to start if they mismatch

This is a low-effort defensive improvement (estimated 1-2 hours) that prevents a class of
field configuration errors.

---

## 10. Reference Documents

| Document | Relevance |
|----------|-----------|
| FIELD_TRIAL_REPORT_MAR25_2026.md, sections 3.4, 3.5, 5.3 | Primary data source for model comparison |
| PICK_REJECTION_BOTTLENECK_ANALYSIS_2026-03.md | Workspace reachability analysis (the other major waste source) |
| ZERO_SPATIAL_COORDINATE_ANALYSIS_2026-03.md | Stereo depth failure analysis (contributes to wasted detections) |
| YOLOX_VS_YOLOV11_COMPARISON.md | YOLOX evaluation for commercial licensing |
| YOLOX_VALIDATION_RUNBOOK.md | Validation procedure if YOLOX is chosen (Option C) |
| MARCH_FIELD_TRIAL_PLAN_2026.md, Decision 1 | March 06 Go/No-Go decision that deferred YOLOX |
| FEBRUARY_FIELD_TRIAL_PLAN_2026.md | Prior trial context |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Cotton boll** | The protective capsule around cotton fibers on the plant. When mature, it opens to expose the white cotton. |
| **Empty shell** | A cotton boll structure where the cotton fiber has already fallen out, been picked, or failed to develop. Visually similar to a cotton boll but contains no harvestable material. Also referred to as "not-pickable." |
| **Wasted detection** | Any detection accepted by the filtering pipeline that does not result in a successful pick. Includes workspace rejections, border-filtered re-detections, zero-spatial failures, and shell false positives. |
| **Detection rate** | Percentage of camera frames that contain at least one accepted detection. |
| **YoloSpatialDetectionNetwork** | DepthAI node that runs YOLO inference on the OAK-D Lite and computes spatial (XYZ) coordinates using stereo depth. Used by both v11 and v5. |
| **NeuralNetwork + SpatialLocationCalculator** | Alternative DepthAI pipeline required for YOLOX (output tensor format incompatible with YoloSpatialDetectionNetwork). Validated by Shwetha/Arun in March 2026. |

## Appendix B: Raw Detection Statistics (March 25)

### arm_1 (YOLOv11 all day)

| Metric | Session 1 | Session 2 | Morning | Total |
|--------|-----------|-----------|---------|-------|
| Operational cycles | 88 | 88 | 143 | 319 |
| Pick attempts | 98 | 87 | 223 | 408 |
| Successful picks | 74 | 40 | 100 | 214 |
| Pick success rate | 75.5% | 46.0% | 44.8% | 52.5% |
| Accepted detections | — | — | 216 (with cotton) | 408 |
| Wasted detections | — | — | — | 194 (47.5%) |
| Detection requests (morning) | — | — | 858 | — |

Note: arm_1 success rate degraded from Session 1 (75.5%) to Session 2 (46.0%) to Morning
(44.8%). This was driven by COLLISION_BLOCKED surge when 7-position J4 scanning was enabled
mid-trial — the denser scan found more cotton at workspace boundaries, increasing planning
failures. The morning session added 81 COLLISION_BLOCKED and 36 OUT_OF_REACH failures.
This is a workspace geometry issue, not a detection model issue.

### arm_2 (v11 Session 1, v5 Sessions 3-5)

| Metric | S1 (v11) | S2 (v5, broken) | S3 (v5) | S4 (v5) | S5 (v5) | S6 (v5) | S7 (v5) | Total |
|--------|----------|-----------------|---------|---------|---------|---------|---------|-------|
| Cycles | 20 | 2 | 119 | 85 | 90 | 1 | ~10 min | 317 |
| Attempts | 12 | 0 | 205 | 146 | 159 | 0 | 0 | 522 |
| Picked | 6 | 0 | 124 | 67 | 81 | 0 | 0 | 278 |
| Success | 50.0% | N/A | 60.5% | 45.9% | 50.9% | N/A | N/A | 53.3% |

Note: Session 2 is excluded from analysis (misconfigured, 65 seconds, zero detections).
Session 6 (evening, 6 minutes, 1 cycle, 0 picks) and Session 7 (14:55, ~10 minutes,
7-position J4 scan, v5 model, 0 cotton found) are also excluded as non-representative.
Pick totals are unchanged (278 successful picks) since Sessions 6-7 produced zero picks.
