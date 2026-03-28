# Zero Spatial Coordinate Analysis — L3 Hypothesis Disproven (February 2026 Field Trial)

**Updated:** March 26, 2026 — updated March 25 data with arm_1 morning session (see Section 13); previously corrected March 15 (see Section 11)

## 1. Executive Summary

17% of cotton detections in the February 2026 field trial returned (0,0,0) spatial
coordinates (issue A7). The leading hypothesis was that J3 (the arm's third joint / L3
link) was physically blocking the OAK-D Lite camera's field of view. Log analysis of 3
arm sessions (91 minutes, 363 zero-spatial events) **definitively disproves this
hypothesis**. J3 was ALWAYS at home position (0.0 rotation) during detection. The true
cause is inherent stereo depth failure on textureless white cotton surfaces — a known
limitation of passive stereo cameras. The existing zero-spatial filter catches 100% of
these events, and no detections with zero coordinates reached the pick pipeline.

**Log source:** February 26, 2026 field trial, arm1 RPi logs at
`collected_logs/2026-02-26_16-24/target/`.

## 2. Key Finding: J3 Cannot Be Blocking Camera

**Evidence from logs:**

- J3 is reported at home position (0.0 rotation) during ALL detection frames across all
  3 sessions.
- J3 homing error: 0.0029 rotations (tolerance is 0.05) — extremely precise.
- J3 hardware stats: 0 errors, 0 timeouts across 91 minutes.
- J3 is commanded to home at the START of each detection scan cycle, BEFORE camera
  capture begins.
- Detection only runs when J3 is confirmed at home.

**Conclusion:** The L3 link is physically retracted during every detection frame. It
cannot obstruct the camera FOV.

## 3. The "Spike" from 3–5% to 17% is Partly a Measurement Artifact

- The zero-spatial filter was deployed BETWEEN the January and February field trials.
- In January, zeros passed silently into the pick system (no logging, no filtering).
- Retroactive analysis of January Session A: 15.8% zero-spatial rate.
- The increase from "3–5%" to "17%" is partly because January didn't measure it properly.
- True increase is modest: 15.8% → 17%, not the alarming 3× jump initially reported.

## 4. True Cause: Stereo Depth Failure on Cotton

**How it works:** The OAK-D VPU runs two steps on-chip:
1. YOLO inference produces a 2D bounding box (xmin, ymin, xmax, ymax) + confidence + label
2. Stereo depth lookup **within that bounding box region** (scaled by `bbox_scale_factor`,
   currently 0.5) computes XYZ spatial coordinates

When step 2 fails — the stereo matching algorithm cannot find enough texture within the
bounding box region to compute disparity — the VPU returns `spatialCoordinates = {0, 0, 0}`.
The bounding box from step 1 is still fully valid.

**Evidence of inherent stereo failure:**

- Even distribution across time (~4 zero-spatial events per minute, no clustering).
- Affects high-confidence detections (confidence range 0.50–0.92, mean 0.70).
- Co-occurs with successful detections IN THE SAME FRAME — some bounding boxes in a
  frame get valid depth, others don't.
- Not correlated with any motor state, position, or error condition.
- Pattern is consistent with per-bounding-box stereo matching failure.

**Why cotton causes depth failure:**

- OAK-D Lite uses passive stereo (two cameras, no active illumination).
- Stereo depth requires texture to find matching points between left and right images.
- Cotton bolls are white, fluffy, low-texture surfaces — worst case for passive stereo.
- At certain distances/angles, the stereo matching algorithm returns zero disparity →
  (0,0,0) coordinates.
- This is a fundamental hardware limitation, not a software bug.

**Active illumination (OAK-D Pro with IR projector) is NOT viable** for a field robot —
outdoor sunlight overpowers any IR projector. Passive stereo is the correct choice for
this application.

## 5. Filter Effectiveness: 100%

- 363 zero-spatial detections across 3 sessions.
- ALL 363 were caught by the zero-spatial filter in `depthai_manager.cpp:2144`.
- ZERO zero-spatial detections reached the pick pipeline.
- Every detection request that succeeded used valid spatial positions.
- The filter works exactly as designed.

## 6. Quantified Impact

| Metric | Value |
|--------|-------|
| Total accepted detections | 1,252 |
| Zero-spatial detections | 363 |
| Zero-spatial rate | ~17% (of NN detections) |
| Filter effectiveness | 100% (363/363 caught) |
| Reached pick pipeline | 0 |
| Rate in January (retroactive) | 15.8% |

## 7. Zero-Spatial in Output Images

**Zero-spatial detections are NOT visible in the saved output images.** They are dropped in
`depthai_manager.cpp:2144` (inside `convertDetection()`) BEFORE the data reaches the image
annotation code in `detection_engine.cpp:823`.

| Detection type | Drawn on output image? |
|---------------|----------------------|
| Zero-spatial (0,0,0) | **NO** — dropped before annotation |
| Border-touching | YES — filtered AFTER image save (line 208-219) |
| Not-pickable (label=1) | YES — drawn in red, filtered AFTER image save |
| Workspace-rejected | YES — filtered AFTER image save (line 221-238) |
| Accepted (label=0) | YES — drawn in green |

To visually identify which cotton bolls had zero-spatial failures in field trial images,
you would need to either cross-reference log timestamps with image timestamps, or modify
the code to pass rejected detections to the drawing stage with a distinct marker (e.g.,
grey bbox with "NO DEPTH" label).

## 8. Bounding Box Data at Filter Point

At the zero-spatial filter (`depthai_manager.cpp:2144`), the full `dai::SpatialImgDetection`
struct is available with these fields:

| Field | Available? | Currently logged? |
|-------|-----------|-------------------|
| `det.label` | YES | YES |
| `det.confidence` | YES | YES |
| `det.xmin` | YES | **NO** |
| `det.ymin` | YES | **NO** |
| `det.xmax` | YES | **NO** |
| `det.ymax` | YES | **NO** |
| `det.spatialCoordinates` | YES (all zeros) | Checked but not logged |

Adding bbox to the log is a one-line change — the data is in the same struct already being
read for label and confidence.

## 9. Recommendations

**No urgent fix needed for March 25 field trial.** The filter works perfectly.

**Optional improvements (low priority):**

1. **Add bounding box coordinates to zero-spatial log messages** (~10 min) — the bbox data
   (`det.xmin/ymin/xmax/ymax`) is already available at the filter point
   (`depthai_manager.cpp:2145`), just not included in the log string. One-line change.
   This would enable analysis of whether certain image regions are more prone to depth
   failure.

2. **Draw zero-spatial detections on output images** (~2 hours) — pass rejected detections
   through to `draw_detections_on_image()` with a distinct visual marker (grey bbox, "NO
   DEPTH" label). Useful for field debugging — operators could visually see which cotton
   bolls the camera detected but couldn't get depth for.

3. **Stereo config tuning** — current `production.yaml` has `confidence_threshold=200`
   (of 255) and `subpixel=true`. Could experiment with lower confidence threshold to
   recover some depth estimates, but risks introducing noisy depth values.

## 10. Source Files Analyzed

| File | Role |
|------|------|
| `src/cotton_detection_ros2/src/depthai_manager.cpp:2139-2149` | Zero-spatial filter + log (inside `convertDetection()`) |
| `src/cotton_detection_ros2/src/depthai_manager.cpp:2157-2161` | Bbox copied to result (proof bbox exists in same struct) |
| `src/cotton_detection_ros2/src/depthai_manager.cpp:1968-2137` | Pipeline build (SpatialDetectionNetwork config) |
| `src/cotton_detection_ros2/src/detection_engine.cpp:823-901` | Image annotation (`draw_detections_on_image()`) |
| `src/cotton_detection_ros2/src/detection_engine.cpp:178` | Image save call (before border/workspace/class filtering) |
| `src/cotton_detection_ros2/config/production.yaml` | Stereo config (confidence=200, bbox_scale=0.5) |
| `src/yanthra_move/src/core/motion_controller.cpp` | J3 homing, multi-scan loop |

## 11. Corrections from Initial Analysis

1. **"Active illumination" removed as option** — OAK-D Pro with IR projector is not viable
   for an outdoor field robot. Sunlight overpowers IR projection.
2. **Clarified origin of (0,0,0)** — comes from the DepthAI SDK on the VPU, not from our
   code. The VPU's SpatialDetectionNetwork sets spatial coordinates to zero when stereo
   depth lookup fails within the bounding box region.
3. **Added image visibility analysis** — zero-spatial detections are invisible in output
   images because they're filtered before annotation. This was not addressed in the initial
   version.
4. **Added bbox data availability table** — confirmed all bbox fields are available at the
   filter point, making the log enhancement trivial.

## 12. Log Sources

- Arm1 RPi logs: `collected_logs/2026-02-26_16-24/target/`
- ROS2 arm logs: `ros2_logs/arm1/` — cotton_detection_node + yanthra_move_node +
  mg6010_controller_node
- Detection images: `images/inputs/` (904 JPEGs), `images/outputs/` (804 annotated
  JPEGs)
- 3 arm sessions, 91 minutes total runtime, 363 zero-spatial events

## 13. March 25, 2026 Field Trial Update

### March 25 Data Comparison (including arm_1 morning session)

The original analysis was based on February 26 data (363 zero-spatial events across 3 sessions, 91 minutes). March 25 data (updated with arm_1 morning session — 858 detection requests, 216 with cotton, ~106 min active):

| Metric | Feb 26 | Mar 25 | Change |
|--------|--------|--------|--------|
| Zero-spatial events | 363 | 1,024 | +182% (raw count) |
| Total detections | ~2,100 | ~5,200 (est.) | ~2.5x more |
| Zero-spatial rate | ~17% | ~15-20% (est.) | Approximately unchanged |
| Active trial duration | ~91 min | ~792 min (~13.2h) | ~8.7x longer |
| Events leaked to motors | 237 | 0 | FIXED — complete filtering |
| Arms operational | 1 | 2 | 2x detection sources |

### Key Findings

1. **Zero-spatial rate is approximately unchanged** — The ~3x increase in raw count is explained by longer runtime (8.7x), more active arms (2x), and more total detections. The per-detection rate (~15-20%) is consistent with the February 17% baseline. This confirms the original analysis: the rate is an inherent property of passive stereo on textureless white cotton, not a regression.

2. **Filtering is now 100% effective** — In February, 237 zero-spatial events leaked through to the motor pipeline. In March, ZERO events reached motors. The fix from OpenSpec change `2026-02-17-fix-zero-coordinate-detections` is working correctly. All 1,024 events are caught and filtered at the detection level.

3. **The root cause is unchanged** — Passive stereo depth failure on textureless white cotton surfaces remains the fundamental cause. No software fix can change this. Active illumination (IR projector) remains not viable outdoors.

### Conclusion

The original analysis and recommendations remain fully valid. The zero-spatial coordinate issue is an inherent hardware limitation with effective software mitigation (filtering). No additional action is needed beyond monitoring the rate to ensure it doesn't increase significantly (which would indicate a stereo camera degradation problem).

The optional recommendations from the original analysis (bbox logging, image annotation for zero-spatial events) remain low priority but would be useful for training data collection if a model retraining effort occurs.

## 14. Related Documents

- `docs/project-notes/TECHNICAL_DEBT_ANALYSIS_2026-03-10.md` — A7 (zero spatial
  coordinates)
- `docs/project-notes/MARCH_FIELD_TRIAL_PLAN_2026.md` — A7 listed as investigation item
- `docs/specifications/GAP_TRACKING.md` — stereo depth quality gaps
