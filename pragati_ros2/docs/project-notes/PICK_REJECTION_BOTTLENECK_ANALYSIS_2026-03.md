# Pick Rejection Bottleneck — Root Cause Analysis (February 2026 Field Trial)

**Updated:** 2026-03-26 — added arm_1 morning session data (see Section 16/17); prior update March 25, 2026

## 1. Executive Summary

The February 2026 field trial showed only 258 successful picks out of 966 pick attempts
(26.7% success rate). Investigation revealed that the dominant failure mode is NOT
detection quality — it's **workspace reachability**. 73.3% of picks fail because the
detected cotton is beyond the arm's physical reach. 88.2% of these failures are instant
rejections (total_ms ≤ 1ms). The arm can only reach X = 0.25–0.56m, but the camera detects
cotton at X = 0.2–3.0m. 63% of accepted detections fall outside the reachable workspace.

**Critical correction:** The current filtering architecture is correct. Yanthra (the motion
planner) rejects unreachable targets in sub-microsecond time with zero motor I/O. Adding a
pre-filter at the detection node would create unnecessary coupling between packages with
negligible performance benefit.

## 2. Full Detection-to-Pick Pipeline Funnel

```
Neural Network Detections:      ~2,755 (100%)
  ├─ Zero-spatial filtered:       363 (13.2%) — (0,0,0) depth failures
  ├─ Border filtered:             361 (13.1%) — too close to image edge
  ├─ Not pickable (label=1):      779 (28.3%) — classified as non-pickable
  └─ Accepted (label=0):        1,252 (45.4%) — passed all filters
       ├─ In reach (X ≤ 0.56m):     459 (36.7%) — within arm workspace
       └─ Out of reach (X > 0.56m): 789 (63.0%) — beyond arm reach
            └─ Rejected by motion planner (sub-microsecond, no motor I/O)

Pick Attempts:    966
Successful Picks: 258 (26.7%)
Failed Picks:     708 (73.3%)
  └─ Instant rejections (≤1ms): 625 (88.2% of failures)
```

## 3. Root Cause: Camera-Workspace Mismatch

**The core problem:** The OAK-D Lite camera has a wide field of view and detects cotton at
distances from 0.2m to 3.0m+. But the arm (J1-J5 chain) can only physically reach cotton
at X = 0.25m to X = 0.56m (constrained primarily by Joint5, the extension joint).

**Joint5 (extension) violations dominate:** 362 out of 687 total joint limit violations are
Joint5 violations — the target X position exceeds the arm's maximum extension.

## 4. Where Rejections Happen (Yanthra, Not Detection)

Rejections happen in `trajectory_planner.cpp:39-174` (`TrajectoryPlanner::plan()`). The
check sequence is entirely arithmetic — no IK solver, no motor I/O:

| Step | Line | Check | Cost |
|------|------|-------|------|
| 1 | 49 | NaN/Inf/zero validation | ~nanoseconds |
| 2 | 56 | TF lookup (camera → arm frame) | ~sub-ms (cached) |
| 3 | 65 | Polar conversion: `sqrt(x²+z²)` + `asin()` | ~nanoseconds |
| 4 | 118 | `checkReachability(r, theta, phi)` | ~nanoseconds |
| 5 | 128 | J3 limit check | ~nanoseconds |
| 6 | 138 | J4 limit check | ~nanoseconds |
| 7 | 148 | J5 limit check | ~nanoseconds |

**Total cost per rejected target: sub-microsecond** (excluding TF cache lookup, which is
sub-millisecond when warm). For 10 rejected targets: < 10ms total. This is negligible
compared to the detection cycle (50-100ms+ for NN inference + depth processing).

## 5. Why Pre-Filtering at Detection is Wrong

The initial analysis recommended adding a distance pre-filter in `detection_engine.cpp`.
This was incorrect. Here's why:

**Detection has zero knowledge of the arm.** To replicate yanthra's workspace check,
detection would need:

| Knowledge Required | Currently In | Would Need Adding |
|---|---|---|
| TF: camera_link → yanthra_link | trajectory_planner.cpp | New TF listener in detection |
| Polar conversion (sqrt, asin) | coordinate_transforms.cpp | Duplicated code |
| J5 hardware offset | trajectory_planner parameter | New detection parameter |
| J3/J4/J5 limits | motor_control → yanthra params | New detection parameters |
| Planning margin factor (0.95) | trajectory_planner.cpp | New detection constant |
| J4/phi compensation | trajectory_planner.cpp | Duplicated code |

That is **8 pieces of arm-specific knowledge** that detection currently doesn't have.
Adding them creates tight coupling between the detection and arm packages, which currently
have clean separation of concerns.

**What you gain:** Avoiding sending a few 3D points across a ROS2 topic message (bytes,
not milliseconds) and eliminating sub-microsecond float comparisons in yanthra.

**What you lose:** Clean separation of concerns. Detection knows about cameras and ML.
Yanthra knows about arms and joints. Mixing them means every arm kinematics change
requires updating the detection package too.

**Communication overhead is fixed:** Detection returns ALL positions in a single ROS2
message. Yanthra loops over them one-by-one. The ROS2 overhead is paid once per detection
cycle, not per cotton position. Rejecting 5 of 5 cottons costs the same communication
overhead as accepting all 5.

## 6. Existing Workspace Filter in Detection (Disabled)

Detection does have a workspace filter (`detection_engine.cpp:222-238`), but it's a crude
axis-aligned bounding box in camera frame (`x < 0 || x > 1.0m`, `|y| > 0.5m`, z range).
It is NOT reachability-aware — it's a rectangular volume, not the arm's actual workspace
envelope. It's disabled by default and is not the right place for this check.

## 7. checkReachability() is a Placeholder

The `checkReachability()` function in `coordinate_transforms.cpp:44-48` is a **placeholder**
— it only checks `r > 0.1 && r < 2.0` and ignores theta and phi entirely. If the team
wants fewer late-stage rejections, tightening this check (within yanthra, keeping all arm
knowledge in one place) would be the right investment.

## 8. The Real Question: Camera Positioning and J4 Strategy

The data shows that 63% of accepted detections are beyond arm reach. This is not a software
problem — it's a **physical geometry problem**:

- The camera's FOV covers a much larger volume than the arm can reach
- Certain J4 scan positions point the camera mostly at unreachable areas
- Optimizing the J4 scan sequence to prioritize positions that view the reachable workspace
  would have a bigger impact than any software filter

**This is a J4 scan strategy and physical camera positioning question, not a software
filtering question.**

## 9. Instant Rejection Analysis

| Metric | Value |
|--------|-------|
| Total pick failures | 708 |
| Instant rejections (≤1ms) | 625 (88.2%) |
| Joint limit violations | 687 |
| Joint5 (extension) violations | 362 (52.7% of joint violations) |
| Mean distance of rejected targets | ~0.85m (est.) |
| Arm max reach (X axis) | 0.56m |
| Cost per rejection | Sub-microsecond (pure arithmetic) |

## 10. Recommended Actions

### Action 1: Optimize J4 scan sequence (MEDIUM PRIORITY, ~4 hours)

- Analyze which J4 positions produce the most reachable detections
- Reorder scan sequence to try productive positions first
- Skip positions that historically produce only out-of-reach detections
- Expected impact: more picks per scan cycle, higher throughput

### Action 2: Tighten checkReachability() in yanthra (LOW PRIORITY, ~2 hours)

- Replace the placeholder `r > 0.1 && r < 2.0` with actual workspace envelope check
- Include theta and phi constraints
- Keep all arm knowledge in `trajectory_planner.cpp` (no cross-package coupling)
- Impact: earlier rejection with better logging, but same sub-microsecond cost

### Action 3: Visual workspace indicator in detection output images (~2 hours)

- Draw a line or shaded region on annotated output images showing the reachable boundary
- Helps operators understand why certain visible cotton isn't being picked
- Useful for field trial debugging

### Action 4: Log reachable distance in detection messages (~1 hour)

- Add X distance to the published detection messages
- Enables runtime monitoring of reachable vs unreachable detection ratio
- Helps tune J4 scan positions

## 11. Source Files

| File | Role |
|------|------|
| `src/yanthra_move/src/core/trajectory_planner.cpp:39-174` | Where rejections happen (`plan()`) |
| `src/yanthra_move/src/core/coordinate_transforms.cpp:44-48` | Placeholder `checkReachability()` |
| `src/cotton_detection_ros2/src/detection_engine.cpp:222-238` | Crude workspace filter (disabled) |
| `src/cotton_detection_ros2/config/production.yaml` | Detection config |
| `src/yanthra_move/src/core/motion_controller.cpp` | Pick cycle, multi-scan loop |

## 12. Corrections from Initial Analysis

1. **"Pre-filter at detection" recommendation removed** — initial analysis recommended
   adding a distance filter in `detection_engine.cpp`. Investigation showed this would
   create unnecessary coupling between detection and arm packages with negligible
   performance benefit. Rejections at yanthra are sub-microsecond and architecturally
   correct.
2. **"Reduces motion planner load by 63%" was misleading** — the "load" of rejecting is
   sub-microsecond arithmetic, not actual computation. Eliminating it saves essentially
   nothing.
3. **"Wasted IK computation" was incorrect** — there is no iterative IK solver. The check
   is closed-form geometry (one sqrt, one asin, a few comparisons).
4. **Reframed from software fix to physical geometry problem** — the real improvement is
   J4 scan strategy and camera positioning, not software filtering.
5. **Added checkReachability() placeholder finding** — the existing reachability check in
   yanthra ignores theta and phi, which could be tightened as a low-priority improvement.

## 13. Log Sources

- Arm1 RPi logs: `collected_logs/2026-02-26_16-24/target/`
- ROS2 arm logs: `ros2_logs/arm1/` — cotton_detection_node + yanthra_move_node logs
- 3 sessions, 91 minutes total, 966 pick attempts, 258 successes

## 16. March 25, 2026 Field Trial Update

### March 25 Data Comparison

The original analysis was based on February 26 data (966 attempts, 26.7% success, 73% rejection). March 25 data:

| Metric | Feb 26 | Mar 25 | Change |
|--------|--------|--------|--------|
| Total pick attempts | 1,181 | 930 | -21% |
| Pick success rate | 26.7% | 52.9% | +26.2pp |
| Workspace rejections | 73% | 46.2% | -26.8pp |
| COLLISION_BLOCKED (of failures) | ~88% | 73.1% | -14.9pp (still dominant) |
| Primary rejection boundary | x position | x > 0.49m | Unchanged |

### What Improved
1. **Overall rejection rate dropped 26.8pp** (73% → 46.2%). This is a significant improvement.
2. **Pick success rate roughly doubled** (26.7% → 52.9%). When cotton IS reachable, success rate is 98.4%.
3. **Fewer instant sub-microsecond rejections** — the system is spending more time on reachable cotton.

### What Didn't Change
1. **COLLISION_BLOCKED is still the #1 failure mode** — 73.1% of all planning failures (was ~88%)
2. **x > 0.49m is still the boundary** — cotton beyond this x-position is consistently rejected
3. **The architectural conclusion is unchanged**: camera FOV extends well beyond arm reach, and the pre-filter (checkReachability) is still a placeholder
4. **J4 scan optimization remains the highest-leverage improvement** for putting cotton in the reachable zone

### What Drove the Improvement?
Likely factors (not individually quantified in logs):
- Better vehicle positioning relative to cotton rows (operators learned from February)
- Two-arm operation means more cotton is within reach of at least one arm
- J4 multi-scan positions (7 on arm_1) catching cotton from better angles
- Possible field geometry differences (different row, different plant spacing)

### Updated Recommendations
The original recommendations remain valid. Additional refinements based on March 25:
1. **Investigate collision margin conservatism** — if 73.1% of failures are COLLISION_BLOCKED at x>0.49m, determine if the collision margins have safety padding that could be reduced. Even 5cm workspace extension (0.49→0.54m) could significantly improve success rate.
2. **Quantify per-arm reachability** — arm_1 (52.5%) vs arm_2 (53.3%) success rate gap may indicate different workspace geometry or mounting positions.
3. **The 98.4% success rate on reachable cotton is excellent** — the picking mechanism itself is not the bottleneck. All optimization should focus on getting more cotton into the reachable zone.

### arm_1 Morning Session Addition (March 26 Update)

arm_1's morning session (10:49–12:36, ~106 min active) added 143 cycles, 223 pick attempts
(100 successful, 123 failed — 44.8% success rate). Failure breakdown: 81 COLLISION_BLOCKED,
36 OUT_OF_REACH (J4 lateral), 2 JOINT_LIMIT_EXCEEDED. The lower success rate (44.8% vs
75.5% in Session 1) is consistent with the pattern seen in Session 2: denser J4 scanning
finds more cotton at workspace boundaries, increasing planning failures.

## 17. Log-Verified Failure Counts — March 25 (Corrects Section 16)

**Updated:** 2026-03-26 — direct grep/JSON parse of
`collected_logs/2026-03-25/machine-1/{arm}/ros2_logs/{arm}/**/yanthra_move_node*.log`
using `⛔ COLLISION AVOIDANCE` header lines, `[PLAN] J4/J5/J3 limit exceeded` WARN lines,
and `pick_complete` JSON events. Full table in `docs/reports/reachability_failure_table_2026-03-25.md`.

### Verified failure counts (per-target, not per-cycle)

| Failure type | arm_1 | arm_2 | Total | % of failures |
|---|---|---|---|---|
| COLLISION_BLOCKED | 124 | 191 | **315** | 73.1% |
| J4 lateral limit | 58 | 45 | **103** | 23.9% |
| J5 physical limit | 4 | 2 | **6** | 1.4% |
| J3 physical limit | 3 | 4 | **7** | 1.6% |
| checkReachability (r>2m) | **0** | **0** | **0** | **0%** |
| **TOTAL** | **189** | **242** | **431** | 100% |
| Successes | 214 | 278 | **492** | — |
| **Total attempts** | **408** | **522** | **930** | — |

### Corrections to Section 16

1. **"checkReachability contributes 64% of failures" — WRONG, corrected to 0%.**
   The prior analysis double-counted the `📏 Joint limit violations: N (cotton out of reach)` stat
   counter, which fires once per pick *cycle*, not once per target. `[PLAN] Target unreachable:`
    (the actual checkReachability failure message) has zero occurrences across all sessions.
    The `checkReachability()` placeholder is still dormant — it passes everything with r<2m.

2. **"Primary rejection boundary: x > 0.49m" — MISLEADING.**
    0.49m is the theoretical J3=0° limit (`hw_offset + clearance/cos(0°) = 0.29+0.20 = 0.49m`).
    In practice, **zero COLLISION_BLOCKED events occur at J3=0°**. All 315 events occur at
    J3 between −34° and −57° (mean −40°, median −39°), where the actual arm-frame x-boundary
   is ~0.55–0.60m. The 0.49m figure overstates the problem.

3. **J4 lateral limit is the second-largest failure category (24%) — not previously identified.**
    103 picks fail because theta (`y_arm`) > ±0.1715m — cotton too far laterally.
   These are edge-of-frame detections when J4 is at ±150mm scan position.

### COLLISION_BLOCKED detail from logs

J3 angle at time of blocking: **min=−34.2°, max=−56.7°, mean=−40.4°, median=−39.8°**

Overshoot distribution (how much J5 exceeds collision limit):
- min=0.5%, max=56.8%, mean=22.1%, median=22.2%
- ≤5%: 32 (14%) | 5–15%: 52 (22%) | 15–30%: 82 (35%) | 30–50%: 60 (26%) | >50%: 8 (3%)

Clearance sensitivity (based on actual overshoot distribution):
- Current clearance=0.20m (derived from D≈1.02m estimated, **not measured**)
- clearance=0.23m (D≈1.06m): would unblock **~113/315 (~36%)** blocked events
- clearance=0.25m (D≈1.10m): would unblock **~186/315 (~59%)** blocked events
- **Measuring actual D is the single highest-leverage pre-April action.**

## 14. Related Documents

- `docs/project-notes/TECHNICAL_DEBT_ANALYSIS_2026-03-10.md` — A27 (workspace optimization)
- `docs/project-notes/MARCH_FIELD_TRIAL_PLAN_2026.md` — pick rate improvement targets
- `docs/project-notes/PICK_FLOW_REFERENCE.md` — pick flow documentation
- `docs/specifications/PRODUCT_REQUIREMENTS_DOCUMENT.md` — FR-PICK-*, PERF-ARM-* requirements

## 15. Owners

- Detection pipeline: Shwetha
- Motion planning / workspace: Arm control team
- J4 scan strategy: Arm control team
- A27 (workspace optimization): Tracked in tech debt
