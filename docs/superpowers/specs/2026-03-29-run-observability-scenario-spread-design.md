# Run Observability & Scenario Spread — Design

**Date:** 2026-03-29
**Status:** Approved

---

## Goal

Three improvements to the cotton-picking simulation:

- **A. Spread cotton positions** — widen cam_z values in scenario files so all 8-10
  cottons are visually distinguishable in Gazebo (≥5 cm world-space separation per arm).
- **B. Real-time SSE logging** — stream per-step log events (spawn, motion, outcome) to
  the frontend log panel during a run.
- **C. Camera coords in StepReport** — add `cam_x`/`cam_y`/`cam_z` to `StepReport` so
  JSON reports include the original cotton position for traceability.

---

## Part A: Spread Out Cotton Positions

### Problem

In `geometry_pack.json` and `contention_pack.json`, cam_z values cluster in the
0.050–0.095 m range. The FK chain (`camera_to_world_fk`) maps small cam_z differences to
millimetre-scale world position differences, so all cottons spawn within a few centimetres
of each other and appear as one overlapping cluster in Gazebo.

### Solution

Replace cam_z values with a wider spread (~0.050–0.300 m) that produces ≥5 cm
world-space separation between any two cotton positions on the same arm.

### Constraints (from existing tests — must be preserved)

| File | Constraint |
|---|---|
| geometry_pack.json | arm1 = exactly 3 steps, arm2 = exactly 5 steps |
| geometry_pack.json | ≥ 3 step_ids that have both arm1 and arm2 entries |
| geometry_pack.json | ≥ 2 paired steps with j4 gap < 0.12 (overlap-heavy) |
| geometry_pack.json | ≥ 1 paired step with j4 gap < 0.05 (colliding) |
| geometry_pack.json | ≥ 1 paired step with j4 gap > 0.08 (safe) |
| contention_pack.json | arm1 = exactly 4 steps, arm2 = exactly 6 steps |
| contention_pack.json | ≥ 4 step_ids with both arms |
| contention_pack.json | ≥ 1 paired step with j4 gap < 0.05 (colliding) |
| contention_pack.json | ≥ 1 paired step with j4 gap > 0.08 (safe) |
| contention_pack.json | UNRESTRICTED run produces ≥ 1 collision |
| contention_pack.json | ≥ 2 distinct cam_z values |

### Approach

New cam_z values will be verified numerically during implementation by calling
`camera_to_arm` + `polar_decompose` and checking:

1. All j4 values within J4_MIN=−0.250 and J4_MAX=0.350 (reachability).
2. Pairwise world-space separation ≥ 5 cm per arm.
3. Required colliding/safe paired-step gaps still satisfied.

New test `test_geometry_pack_cotton_positions_are_visually_spread` and
`test_contention_pack_cotton_positions_are_visually_spread` assert ≥5 cm pairwise
separation per arm (computed via `camera_to_world_fk`).

---

## Part B: Real-Time SSE Logging

### Problem

The run flow has zero log output. The frontend shows "Starting run…" then jumps to
"Run complete" with no per-step visibility.

### Architecture

Three layers: event bus (backend), SSE transport (FastAPI), frontend consumer.

### B1: RunEventBus (`run_event_bus.py`, new)

Thread-safe in-memory event bus. Uses `threading.Condition` + `collections.deque`.

**API:**

```python
class RunEventBus:
    def emit(self, event: dict) -> None: ...
    def subscribe(self) -> Generator[dict, None, None]: ...
    def close(self) -> None: ...   # signals subscribe() to stop yielding
    def reset(self) -> None: ...   # clears events, re-arms for next run
```

**Event types:**

| `type` | Fields | Source |
|---|---|---|
| `cotton_spawn` | `arm_id, step_id, cam_x, cam_y, cam_z, world_x, world_y, world_z, model_name` | `_run_spawn_cotton` |
| `step_start` | `arm_id, step_id, target_j3, target_j4, target_j5, mode` | `RunController.run()` before executor dispatch |
| `step_complete` | `arm_id, step_id, terminal_status, pick_completed, collision, near_collision, skipped` | `RunController.run()` after executor returns |
| `run_complete` | `run_id, total_steps, collisions, completed_picks` | `RunController.run()` after step loop |

### B2: SSE Endpoint (`GET /api/run/events`)

New endpoint in `testing_backend.py`:

```python
@app.get("/api/run/events")
async def run_events():
    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

`_sse_generator()` yields `data: {json}\n\n` per SSE spec from `_event_bus.subscribe()`.
Closes when `run_complete` event is received.

The existing `POST /api/run/start` remains **blocking** (no change to run duration or
arm behavior). The SSE stream carries live events alongside the blocking POST.

### B3: Event Emission Points

- `_run_spawn_cotton` (testing_backend.py): after `_gz_spawn_model`, emit `cotton_spawn`
  with both cam coords and world coords (`wx, wy, wz` already computed on line 990).
  The function accepts an optional `event_bus` parameter; if None, no event is emitted
  (preserves testability without a live bus).
- `RunController.__init__`: accepts optional `event_bus: RunEventBus = None`.
- `RunController.run()`: emits `step_start` before executor dispatch, `step_complete`
  after executor returns (per arm, per step), and `run_complete` after the step loop.
- `run_start` endpoint: creates `RunEventBus`, stores it as `_event_bus` module-level,
  passes it to `RunController`.

### B4: Frontend Consumer (`testing_ui.js`)

In `setupRunFlow()`, before `fetch('/api/run/start')`:

1. Open `new EventSource('/api/run/events')`.
2. `evtSource.onmessage`: parse JSON, call `log()` with formatted text and CSS class:
   - `cotton_spawn` → `"Spawn: arm1 step0 cam(0.65,-0.001,0.150) → world(0.34,1.40,0.15)"` (success)
   - `step_start` → `"Step: arm1 step0 → j3=-0.12 j4=0.15 j5=0.08 [geometry_block]"` (info)
   - `step_complete` completed/pick=true → `"Done: arm1 step0 completed pick=true"` (success)
   - `step_complete` blocked/skipped → `"Done: arm2 step1 blocked pick=false"` (warn)
   - `run_complete` → `"Run complete: 8 steps, 0 collisions, 6 picks"` (success)
3. Close EventSource after receiving `run_complete` or on error.

---

## Part C: Camera Coordinates in StepReport

### Problem

`StepReport` records `candidate_joints` and `applied_joints` but not the original camera
coordinates. JSON reports lack position traceability.

### Solution

Add three optional fields to `StepReport`:

```python
cam_x: Optional[float] = None
cam_y: Optional[float] = None
cam_z: Optional[float] = None
```

Optional defaults preserve backward compatibility with all existing tests that construct
`StepReport` without cam coords. `dataclasses.asdict()` serializes them automatically —
no `JsonReporter` changes needed.

**Emission**: `RunController.run()` passes `step.cam_x`, `step.cam_y`, `step.cam_z`
when constructing `StepReport` (line 329 area).

---

## Files Changed

| File | Change |
|---|---|
| `scenarios/geometry_pack.json` | Widen cam_z values |
| `scenarios/contention_pack.json` | Widen cam_z values |
| `run_event_bus.py` (new) | Thread-safe event bus |
| `test_run_event_bus.py` (new) | Event bus unit tests |
| `testing_backend.py` | SSE endpoint, emit cotton_spawn, wire event bus |
| `run_controller.py` | Accept event_bus, emit step events, pass cam coords to StepReport |
| `json_reporter.py` | Add cam_x/cam_y/cam_z optional fields to StepReport |
| `test_json_reporter.py` | Test cam coords appear in serialized output |
| `test_geometry_scenario_pack.py` | Add world-spread test |
| `test_contention_scenario_pack.py` | Add world-spread test |
| `testing_ui.js` | EventSource consumer in setupRunFlow() |

---

## Testing Strategy

- **Part A**: Existing tests validate structural constraints. New tests assert ≥5 cm
  pairwise world-position separation per arm (computed via `camera_to_world_fk`).
- **Part B**: Unit tests for `RunEventBus` (emit/subscribe/close/reset, thread safety,
  close unblocks subscribers). Integration test that `RunController` emits the expected
  event sequence. No Playwright E2E needed — SSE endpoint is covered by unit tests.
- **Part C**: Test that `StepReport` with cam coords serializes correctly via `asdict()`.
  Test that `RunController` populates cam coords in step reports.

---

## Commit Plan

1. `feat: add cam_x/cam_y/cam_z fields to StepReport and wire in RunController` (Part C)
2. `feat: spread cam_z values for visual cotton separation in scenario files` (Part A)
3. `feat: add RunEventBus, SSE endpoint, and per-step run logging` (Part B)
