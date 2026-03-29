# Impact Analysis: reliable-dual-arm-publish

## 1. Before / After Behavior

| Item | Before (current) | After |
|---|---|---|
| Joint command publish count | 1× per command (`subprocess.Popen`, fire-and-forget) | 3× per command (`subprocess.run`, blocking, 150ms gaps) |
| `_gz_publish` subprocess type | `Popen` (non-blocking, orphaned processes possible) | `run` (blocking, process exits before sleep) |
| Dual-arm step duration | ~11 s (arm1 then arm2, sequential) | ~7.3 s (arm1 and arm2 concurrently) |
| Single-arm step duration | ~5.5 s | ~7.3 s (triple-publish adds ~1.8s overhead) |
| Event loop during `/api/run/start` | Blocked for full run duration | Free (run executes in worker thread via `asyncio.to_thread`) |
| `/api/estop` during a run | Queued by OS, received only after run completes | Received immediately; sets server-side flag |
| E-STOP effect on in-progress run | None (run continues regardless) | Aborts at next animation phase boundary (~0–1.4s latency) |
| Step terminal statuses | `completed`, `blocked`, `skipped` | `completed`, `blocked`, `skipped`, `estop_aborted` (new) |
| E-STOP zero-publish | Only rclpy/fallback burst at end of run | Immediate per-arm zero-publish at phase boundary |
| Parallel animation implementation | Sequential loop over arm_steps | `ThreadPoolExecutor(max_workers=2)`, results collected in sorted arm-id order |
| Step report arm ordering in paired steps | Deterministic only by coincidence (loop order) | Explicitly sorted by arm_id before reporting |

## 2. Performance Impact

| Item | CPU | Memory | Latency |
|---|---|---|---|
| Triple-publish (3× `subprocess.run`) | +2× subprocess invocations per joint command; negligible CPU (local IPC) | No change; processes are synchronous and exit before next sleep | +1.8s per arm-step (3 publishes × 150ms gaps = 300ms gaps + subprocess overhead) |
| `asyncio.to_thread()` | +1 sleeping thread per active run (idle when sleeping between phases) | +1 thread stack (~8MB default) during run | No additional latency; run starts immediately in worker |
| `threading.Event` E-STOP flag | Negligible (single `is_set()` check per animation phase, 6 per step) | +1 `threading.Event` object (~64 bytes) | None when not set; abort latency 0–1.4s (depends on which phase) |
| `ThreadPoolExecutor(max_workers=2)` | +1 thread per paired step (2 threads total during paired animation) | +2 thread stacks during paired step execution only | Reduces paired-step wall time from ~14.6s (2×7.3s) to ~7.3s |

## 3. Unchanged Behavior

- `/api/run/start` request shape: `mode`, `scenario`, `arm_pair` fields — **no change**
- `/api/run/start` response shape: same `steps`, `markdown`, `run_id` fields — `terminal_status` gains new value but field name is unchanged
- `/api/estop` response shape: `{"status": "ok"|"partial", "message": "..."}` — **no change**
- All other API endpoints: `/api/run/status`, `/api/joints/`, `/api/scenario/`, etc. — **no change**
- Gazebo topic names: `/joint3_cmd`, `/joint4_cmd`, `/joint5_cmd`, `/joint3_copy_cmd`, etc. — **no change**
- ROS2 topics and services — **no change**
- Cotton spawn/remove behaviour — **no change**
- Mode logic (unrestricted, baseline_j5_block_skip, geometry_block, overlap_zone_wait) — **no change**
- Truth monitor observations — **no change**
- Scenario JSON format — **no change**
- Frontend manual-pick path (ROSLIB.js triple-publish) — **no change**
- Launch files, config files, `dashboard.yaml` — **no change**
- `RunController.load_scenario()`, `reset()`, `get_json_report()` — **no change**
- All existing `completed`, `blocked`, `skipped` terminal statuses — **no change**

## 4. Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| `subprocess.run` blocks for > 150ms under Gazebo load, causing animation phase drift | Low (local IPC, typical < 5ms) | If observed: add `timeout=1.0` to `subprocess.run` and log slow publishes |
| Worker thread exception from `asyncio.to_thread` is swallowed | Low | `await asyncio.to_thread(...)` re-raises exceptions in the event loop; FastAPI returns 500 |
| ThreadPoolExecutor future exception from one arm is silently dropped | Low | `future.result()` re-raises; wrap in try/except and surface as `estop_aborted` or log |
| E-STOP check after sleep races with simultaneous E-STOP publish (both arms) | Negligible | CPython GIL ensures `threading.Event.is_set()` is atomic; both arms detect flag independently |
| `_estop_event` not cleared before second run if first run errored mid-`to_thread` | Low | `_estop_event.clear()` is called at the very start of `/api/run/start`, before any executor creation |
| Orphaned threads if worker raises before both futures complete | Low | `executor.shutdown(wait=True)` is implicit when exiting the `with ThreadPoolExecutor(...)` block |
| Triple-publish increases sim wall-clock time for single-arm runs | Accepted | Per proposal: 5.5s → 7.3s. Not a regression — reliability > raw speed for this use case |

## 5. Blast Radius

| Item | Details |
|---|---|
| Packages modified | `vehicle_arm_sim` only |
| Files touched | `testing_backend.py`, `run_step_executor.py`, `run_controller.py` |
| Test files touched | `test_run_step_executor.py`, `test_run_controller.py`, `test_motion_backed_e2e.py` |
| Approximate lines changed | ~20 lines implementation, ~60 lines new tests |
| Breaking changes | None — `estop_aborted` is additive; existing consumers filtering `completed` are unaffected |
| Config / launch file changes | None |
| ROS2 interface changes | None |
