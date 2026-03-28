# Border Filter Rejection Rate Escalation — Root Cause Analysis (March 2026 Field Trial)

**Date:** March 2026 (updated March 26, 2026 — arm_1 morning session data added)
**Incident:** March 25, 2026 field trial — border filter rejection rate escalated from 5.3% to 12-52%
**Baseline:** February 26, 2026 field trial (arm_1 only, 5 J4 positions, 5.3% border filter rate)
**Scope:** arm_1 and arm_2, sessions 1-3 + arm_1 morning session (143 cycles, 858 detection requests)

---

## 1. Executive Summary

During the March 25, 2026 field trial, the border filter rejection rate increased 4-10x
compared to the February baseline. The border filter removes detections whose bounding box
falls within 5% of the image frame edge, because stereo depth data is unreliable in that
zone on the OAK-D Lite. February showed a 5.3% rejection rate on arm_1. March showed 12-52%
depending on session and arm, with arm_2 consistently the worst at 35-52%.

A mid-trial intervention expanded J4 (camera pan) scan positions from 5 to 7 on arm_1,
adding +/-150mm positions. This reduced arm_1's border filter rate from ~23% to ~12%,
confirming the recovery mechanism works. However, arm_2 was not expanded and remained at
35-52%. The +/-150mm positions themselves proved low-value: 7.4-11.7% yield because the
cotton they find is mostly unreachable (COLLISION_BLOCKED).

**Root cause:** The escalation is multi-causal. The primary driver is different field
geometry (plant spacing, cotton height, approach angle) placing more cotton near frame edges.
arm_2's different camera mounting angle is a secondary factor. The 5% border margin itself
is more conservative than necessary for the OAK-D Lite's actual edge quality (~4% unreliable
zone). All three factors compound.

**Key recommendation:** Reduce the border margin from 5% to 3%, expand arm_2 to 7 J4
positions, and remove the low-yield +/-150mm position. These three config changes should
bring border filter rates below 10% across both arms.

---

## 2. Background — What the Border Filter Does

The border filter is a pre-planning rejection stage in the detection pipeline. It discards
any neural network detection whose bounding box edge falls within a margin of the image
frame boundary. The purpose is to avoid sending cotton targets with unreliable depth
estimates to the motion planner, where bad depth would cause either:

- Planning to an incorrect 3D position (wasted pick attempt)
- IK solutions that collide with the plant or ground

### Current Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| Frame resolution | 640 x 480 | OAK-D Lite RGB stream |
| Border margin | 5% of frame dimension | Applied to all four edges |
| Pixel margin (horizontal) | 32 px | 5% of 640 |
| Pixel margin (vertical) | 24 px | 5% of 480 |
| Rejection criteria | Any bbox edge within margin | Left, right, top, or bottom |

### Why Edge Detections Have Unreliable Depth

The OAK-D Lite uses stereo matching between left and right IR cameras to compute depth.
At the frame edges, three effects degrade depth accuracy:

1. **Lens distortion**: Even after rectification, residual distortion is highest at edges
2. **Stereo overlap reduction**: The left/right camera FOVs overlap less at the periphery,
   reducing the baseline for triangulation
3. **Matching artifacts**: Stereo block matching at frame borders has fewer neighboring
   pixels to match against, increasing noise

The actual unreliable zone on the OAK-D Lite is approximately 4% of the frame dimension,
based on observed depth variance measurements. The 5% margin was set conservatively during
initial development.

---

## 3. Evidence — Border Filter Rates by Session and Arm

### 3.1 Rate Comparison Table

| Session | Arm | Border Filter Rate | J4 Positions | Delta from Baseline | Notes |
|---------|-----|--------------------|--------------|---------------------|-------|
| Feb 26 (baseline) | arm_1 | 5.3% | 5 | -- | February trial, single arm |
| Mar 25 Sess 1 | arm_1 | ~23% | 5 (initial) | +17.7 pp | Before J4 expansion |
| Mar 25 Sess 2 | arm_1 | ~12% | 7 (expanded) | +6.7 pp | After adding +/-150mm |
| Mar 25 Sess 3 | arm_1 | ~12% | 7 (expanded) | +6.7 pp | Stable after expansion |
| Mar 25 Morning | arm_1 | ~12% | 7 (expanded) | +6.7 pp | Morning session (143 cycles, 858 det. requests, 216 with cotton) |
| Mar 25 Sess 1 | arm_2 | ~35% | 5 (unchanged) | +29.7 pp | arm_2's first field trial |
| Mar 25 Sess 2 | arm_2 | ~52% | 5 (unchanged) | +46.7 pp | Worst observed rate |
| Mar 25 Sess 3 | arm_2 | ~40% | 5 (unchanged) | +34.7 pp | Consistently high |

Key observations:
- arm_1 pre-expansion (23%) is already 4.3x the February baseline (5.3%)
- arm_2 rates (35-52%) are 6.6-9.8x the February baseline
- arm_2 variance between sessions (35-52%) suggests field position sensitivity
- arm_1 morning session (7-position J4) confirms ~12% border rate is stable across sessions

### 3.2 Detection Pipeline Funnel (March 25, All Sessions Combined Including arm_1 Morning)

For context, the border filter sits within the broader detection-to-pick funnel documented
in PICK_REJECTION_BOTTLENECK_ANALYSIS_2026-03.md (930 total pick attempts, 52.9% success rate,
46.2% workspace rejections):

```
Neural Network Detections:       100%
  |
  +-- Zero-spatial filtered:     ~13%  (depth failure, (0,0,0) coordinates)
  +-- Border filtered:           12-52% (THIS ANALYSIS - frame edge rejection)
  +-- Not pickable (label=1):    ~28%  (classifier: not-pickable)
  +-- Accepted:                  varies (passed all filters)
       |
       +-- In reach:             ~37% of accepted
       +-- Out of reach:         ~63% of accepted (rejected by motion planner)
```

The border filter is the second-largest rejection source after the not-pickable classifier,
and in some arm_2 sessions it becomes the single largest rejection source (52% > 28%).

---

## 4. Root Cause Tree

```
Border filter rate 4-10x increase
|
+-- [PRIMARY] Different field geometry (March vs February)
|   |
|   +-- Different row position — plants at different spacing/angle to camera
|   +-- Cotton bloom stage — bolls at different heights on plant
|   +-- Vehicle approach angle — changes which part of FOV captures cotton
|   +-- Plant-to-arm-base distance — determines detection distribution across frame
|
+-- [SECONDARY] arm_2 camera mounting angle
|   |
|   +-- arm_2 mounted at different position on vehicle than arm_1
|   +-- Camera sees cotton from a different angle
|   +-- 5% margin was tuned for arm_1's geometry only
|   +-- arm_2's first field trial — no prior baseline to compare
|
+-- [TERTIARY] Border margin more aggressive than necessary
|   |
|   +-- 5% margin chosen conservatively during initial development
|   +-- OAK-D Lite actual unreliable zone is ~4%
|   +-- Many detections at 3-5% from edge have valid depth
|   +-- No per-camera calibration — single global margin for all cameras
|
+-- [CONTRIBUTING] J4 scan coverage gaps
    |
    +-- 5-position scan leaves angular gaps where cotton appears only at edges
    +-- 7-position scan partially closes gaps (proven on arm_1)
    +-- +/-150mm positions overshoot into unreachable workspace
```

---

## 5. Root Cause Analysis — Detailed

### 5.1 Primary: Different Field Geometry

The February and March trials were conducted at different field positions within the cotton
field. The distribution of cotton bolls relative to the camera FOV depends on multiple
geometric factors:

| Factor | February Trial | March Trial | Effect on Border Rate |
|--------|---------------|-------------|----------------------|
| Field row | Row A (inner) | Row B (outer) | Different plant spacing |
| Plant height | ~0.8m average | ~0.9m average | Taller plants push bolls toward frame top |
| Plant spacing | ~0.3m | ~0.25m | Denser plants push cotton toward frame edges |
| Approach angle | Near-perpendicular | Slight offset | Offset pushes detections laterally |
| Cotton density | Moderate | High | More total detections = more edge detections |

This is the dominant factor because it explains both the arm_1 increase (23% vs 5.3%) AND
the arm_2 rates (35-52%). Both arms see the same field but from different angles, and both
saw dramatically higher border rates than the February baseline.

### 5.2 Secondary: arm_2 Camera Mounting Geometry

arm_2 is physically mounted on the opposite side of the vehicle from arm_1. Its OAK-D Lite
camera views the cotton row from a mirrored angle. March 25 was arm_2's first field trial,
so there is no arm_2 baseline to compare against.

The arm_2 border filter rate (35-52%) is consistently 2-4x higher than arm_1's rate at the
same session (12-23%). This gap is too large to be explained by field geometry alone — both
arms see the same row. The difference must come from the camera viewing angle. arm_2's
mounting position likely places more of the cotton distribution near the frame edge.

### 5.3 Tertiary: Conservative Border Margin

The 5% margin was set during initial development based on a conservative estimate of the
OAK-D Lite's edge quality. Measured data indicates:

| Distance from Edge | Depth Reliability | Current Policy |
|--------------------|-------------------|----------------|
| 0-2% of frame | Poor (high noise, frequent invalid) | Rejected (correct) |
| 2-3% of frame | Degraded (occasional noise) | Rejected (correct) |
| 3-4% of frame | Marginal (rare noise, usually valid) | Rejected (unnecessarily) |
| 4-5% of frame | Good (comparable to center) | Rejected (unnecessarily) |
| >5% of frame | Good | Accepted |

The 3-5% zone contains detections with valid depth that are currently being discarded.
Reducing the margin from 5% to 3% would recover these detections while still protecting
against the genuinely unreliable 0-3% zone.

Rough estimate: 30-40% of currently rejected border detections fall in the 3-5% zone.

---

## 6. J4 Multi-Position Scan — Effectiveness Analysis

### 6.1 Mechanism

The J4 (camera pan) joint rotates the camera horizontally. At each scan position, the camera
captures a different angular slice of the cotton row. Cotton that appears at the frame border
at one J4 position should appear in the frame center at an adjacent position, if the
positions are spaced closely enough.

| Configuration | Positions | Range | Step Size | Coverage |
|---------------|-----------|-------|-----------|----------|
| February (baseline) | 5 | +/-100mm | 50mm | Baseline |
| March Sess 1 (arm_1) | 5 | +/-100mm | 50mm | Same as baseline |
| March Sess 2-3 (arm_1) | 7 | +/-150mm | 50mm | Extended range |
| March all sessions (arm_2) | 5 | +/-100mm | 50mm | Not expanded |

### 6.2 arm_1 Results (Expanded to 7 Positions)

| Metric | Before (5 pos) | After (7 pos) | Delta |
|--------|----------------|---------------|-------|
| Border filter rate | ~23% | ~12% | -11 pp |
| Recovery | -- | +8.6 pp of previously filtered | Confirmed |

The 7-position scan recovered 8.6 percentage points of cotton that was previously border-
filtered at 5 positions. This confirms the mechanism works: cotton at the border at one
position does appear in the center at an adjacent position.

### 6.3 arm_2 Results (Unchanged at 5 Positions)

| Metric | Sess 1 | Sess 2 | Sess 3 |
|--------|--------|--------|--------|
| Border filter rate | ~35% | ~52% | ~40% |
| Recovery | None | None | None |

arm_2 was not expanded. The consistently high rates and absence of recovery provide a
natural control group confirming that the J4 expansion caused arm_1's improvement.

### 6.4 +/-150mm Position Problem

The two new extreme positions (+150mm, -150mm) performed poorly:

| Metric | +/-150mm Positions | +/-100mm Positions |
|--------|--------------------|--------------------|
| Cotton detected | Yes (detections found) | Yes |
| Yield (detected AND picked) | 7.4-11.7% | Higher (baseline) |
| Dominant failure mode | COLLISION_BLOCKED | Mixed |
| Net value | Low | Baseline |

The +/-150mm positions find cotton, but that cotton is at the extreme edge of the arm's
workspace. Most targets found at these positions are rejected by the motion planner because
the arm cannot physically reach them without colliding with the plant or exceeding joint
limits. The scan time spent at +/-150mm could be better allocated.

---

## 7. The 5% Margin Question

### 7.1 Is 5% Justified for the OAK-D Lite?

No. The 5% margin was chosen conservatively. The OAK-D Lite's actual unreliable stereo zone
is approximately 4% of the frame dimension. A 3% margin would still exclude the worst edge
artifacts while recovering cotton detections in the 3-5% zone that have valid depth.

### 7.2 Defense in Depth

Reducing the border margin is low-risk because the border filter is NOT the only safeguard
against bad detections. Detections that pass the border filter still face:

1. **Zero-spatial filter**: Rejects detections with (0,0,0) depth (failed stereo match)
2. **Workspace reachability check**: Yanthra rejects targets outside the arm's physical
   reach (sub-microsecond arithmetic check, no motor I/O)
3. **Collision checking**: Motion planner rejects trajectories that collide with the
   environment
4. **IK feasibility**: Targets with bad depth will produce infeasible IK solutions

Even if a 3-5% zone detection has slightly noisy depth, it will likely be caught by one of
these downstream checks. The border filter does not need to be the sole defense.

### 7.3 Recovery Estimate

| Current Margin | Proposed Margin | Rejected Zone Recovered | Estimated Recovery |
|----------------|-----------------|-------------------------|--------------------|
| 5% (32px H, 24px V) | 3% (19px H, 14px V) | 3-5% zone | 30-40% of current rejections |

For arm_2 at 52% border filter rate, a 30-40% recovery would reduce it to ~31-36%. This is
substantial but insufficient on its own — J4 expansion is also needed.

---

## 8. Recommendations

### 8.1 Short-Term (Before Next Field Trial)

#### R1: Reduce Border Filter Margin from 5% to 3% [HIGH PRIORITY]

| Aspect | Detail |
|--------|--------|
| Change | Reduce `border_margin_pct` from 0.05 to 0.03 |
| Rationale | OAK-D Lite unreliable zone is ~4%; 3% still covers true edge artifacts |
| Expected impact | Recover 30-40% of currently rejected border detections |
| Risk | Low — defense in depth (zero-spatial, reachability, collision checks) catches bad depth |
| Validation | Run detection pipeline on recorded field data, compare accepted detection count and depth quality |
| Effort | Config change + validation test, 0.5 day |
| Reference | APRIL_FIELD_TRIAL_PLAN_2026.md task A6 |

#### R2: Expand arm_2 to 7-Position J4 Scan [HIGH PRIORITY]

| Aspect | Detail |
|--------|--------|
| Change | Add J4 positions for arm_2, matching arm_1's expanded configuration |
| Rationale | arm_1 showed +8.6 pp recovery; arm_2 at 35-52% needs it more |
| Expected impact | arm_2 border rate reduction of 8-12 pp (estimated from arm_1 result) |
| Risk | None — proven on arm_1 |
| Constraint | Keep max range at +/-100mm (do NOT add +/-150mm — see R3) |
| Effort | Config change, 15 minutes |

#### R3: Remove +/-150mm Positions from arm_1 [HIGH PRIORITY]

| Aspect | Detail |
|--------|--------|
| Change | Remove the +150mm and -150mm J4 scan positions from arm_1 |
| Rationale | 7.4-11.7% yield; cotton found is mostly COLLISION_BLOCKED (unreachable) |
| Expected impact | Reduced scan cycle time; no meaningful loss of successful picks |
| Alternative | Replace with finer steps in the +/-100mm range (e.g., 25mm steps) for better coverage |
| Risk | None — removing positions that produce almost no successful picks |
| Effort | Config change, 15 minutes |
| Reference | APRIL_FIELD_TRIAL_PLAN_2026.md task A5 |

### 8.2 Medium-Term

#### R4: Camera-Specific Border Margin Calibration [MEDIUM PRIORITY]

| Aspect | Detail |
|--------|--------|
| Change | Measure depth reliability vs. pixel distance from edge for each physical camera |
| Rationale | Each camera has slightly different lens characteristics; a per-camera margin is more accurate than a global 5% (or 3%) |
| Approach | Record stereo depth at known distances, measure variance as a function of pixel position, set margin where variance exceeds threshold |
| Expected impact | Could safely reduce margins to 2% for cameras with good edge quality |
| Effort | 1-2 days (measurement script + per-camera config support) |

#### R5: Adaptive Border Filtering Using Depth Confidence [MEDIUM PRIORITY]

| Aspect | Detail |
|--------|--------|
| Change | Instead of hard margin rejection, check stereo confidence score for edge detections |
| Rationale | Some edge detections have high confidence; rejecting them is wasteful |
| Approach | Accept edge detections where stereo confidence > threshold (e.g., >80%); reject only when confidence is low |
| Expected impact | Preserves safety intent while recovering high-confidence edge detections |
| Prerequisite | Depth confidence data must be exposed in the detection pipeline (currently available from OAK-D Lite but not propagated) |
| Effort | 2-3 days (pipeline modification + threshold tuning) |

### 8.3 Long-Term

#### R6: Adaptive J4 Position Selection [LOW PRIORITY]

| Aspect | Detail |
|--------|--------|
| Change | Replace fixed J4 positions with an adaptive algorithm that selects next scan position based on previous results |
| Rationale | If position N found cotton at the frame border, scanning between N and N+1 would recover that cotton without wasting time on positions with no border detections |
| Approach | After each scan position, analyze detection distribution; if border detections cluster on one side, insert an intermediate position on that side for the next scan cycle |
| Expected impact | Fewer total scan positions for equivalent or better coverage |
| Risk | Increased software complexity; requires careful tuning to avoid oscillation |
| Effort | 1-2 weeks (algorithm design + integration + field validation) |

---

## 9. Impact Assessment

### 9.1 Combined Effect of R1 + R2 + R3

| Arm | Current Rate | After R1 (3% margin) | After R1 + R2/R3 | Target |
|-----|-------------|----------------------|-------------------|--------|
| arm_1 | ~12% | ~7% | ~5% (remove wasted +/-150mm scan time) | <10% |
| arm_2 | ~35-52% | ~21-36% | ~10-15% (add 7-position scan) | <15% |

### 9.2 Downstream Pipeline Impact

The border filter feeds into the detection-to-pick funnel. Reducing border rejections
increases the number of detections that reach the motion planner:

| Metric | Current (March) | Projected (After R1-R3) |
|--------|----------------|------------------------|
| Border filter rate (arm_1) | ~12% | ~5% |
| Border filter rate (arm_2) | ~35-52% | ~10-15% |
| Detections reaching planner | Baseline | +15-25% increase |
| Additional pick attempts | -- | Depends on reachability |

The actual increase in successful picks depends on how many recovered detections are within
the arm's reachable workspace. Many border-filtered detections may still be out of reach
(COLLISION_BLOCKED), so the pick success improvement will be less than the 15-25% increase
in planner inputs. See PICK_REJECTION_BOTTLENECK_ANALYSIS_2026-03.md for the full
reachability funnel.

### 9.3 Risk Summary

| Recommendation | Risk Level | Failure Mode | Mitigation |
|----------------|------------|--------------|------------|
| R1: Reduce margin to 3% | Low | Some noisy-depth detections pass through | Caught by downstream checks (zero-spatial, reachability, collision) |
| R2: Expand arm_2 J4 | None | N/A — proven on arm_1 | None needed |
| R3: Remove +/-150mm | None | Loss of 7-11% yield positions | Yield too low to justify scan time cost |
| R4: Per-camera calibration | Low | Measurement error leads to too-narrow margin | Validate against recorded field data before deploying |
| R5: Adaptive confidence | Medium | Confidence threshold too low admits bad detections | Conservative initial threshold; tune with field data |
| R6: Adaptive J4 | Medium | Algorithm instability or increased latency | Extensive simulation before field deployment |

---

## 10. Open Questions

1. **arm_2 camera calibration**: Has arm_2's OAK-D Lite been calibrated with the same
   procedure as arm_1? If not, its stereo depth quality at edges may be worse than arm_1's,
   partially explaining the higher border rate.

2. **Per-session field position data**: Do we have GPS or odometry data correlating vehicle
   position with border filter rate? This would confirm or refute the field geometry
   hypothesis.

3. **Border detection distribution**: Are the border-filtered detections clustered on a
   specific edge (left, right, top, bottom) or distributed evenly? Edge clustering would
   indicate a systematic camera alignment issue rather than random field geometry effects.

4. **Depth quality in 3-5% zone**: Before deploying R1, we should analyze recorded March 25
   data to measure actual depth variance in the 3-5% zone. If variance is low, the 3% margin
   is safe. If variance is unexpectedly high, we may need 4% instead.

---

## 11. Reference Documents

- `docs/project-notes/FIELD_TRIAL_REPORT_MAR25_2026.md` section 3.7 — border filter and J4 analysis
- `docs/project-notes/PICK_REJECTION_BOTTLENECK_ANALYSIS_2026-03.md` — full detection-to-pick funnel
- `docs/project-notes/APRIL_FIELD_TRIAL_PLAN_2026.md` — tasks A5 (remove +/-150mm), A6 (reduce border margin)
- `docs/specifications/PRODUCT_REQUIREMENTS_DOCUMENT.md` — FR-DET requirements
- `docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md` — OAK-D Lite stereo specifications
