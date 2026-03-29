## Why

The backend scenario-run path publishes each Gazebo joint command exactly once via a
fire-and-forget `subprocess.Popen` call — no retry, no error capture, no abort. The
frontend manual-pick path already uses triple-publish (3× with 500 ms gaps) as a proven
reliability workaround. Additionally, dual-arm steps animate sequentially (~11 s per
step) when they could run in parallel (~5.5 s), and the synchronous `controller.run()`
blocks the FastAPI event loop so E-STOP requests cannot even be received during a run.

## What Changes

- **Triple-publish for run-path joint commands.** `_gz_publish` in `testing_backend.py`
  publishes each command 3× with 150 ms gaps, matching the frontend reliability pattern.
- **Parallel dual-arm animation.** Within a paired step, both arms' `executor.execute()`
  calls run concurrently via `ThreadPoolExecutor`. Mode logic, peer-state exchange, and
  truth-monitor observation remain sequential (microsecond-cost, data-dependent).
- **Server-side E-STOP flag.** A `threading.Event` in `testing_backend.py` is set by
  `/api/estop` and checked between animation phases in `RunStepExecutor.execute()` and
  between step iterations in `RunController.run()`. On E-STOP the executor publishes
  zeros to all joints and returns an `estop_aborted` terminal status.
- **Async run execution.** `controller.run()` is called via `asyncio.to_thread()` so the
  FastAPI event loop stays responsive to E-STOP and status requests during a run.

## Non-goals

- Changing the frontend manual-pick publish path (already reliable).
- Adding Gazebo joint-position feedback (closed-loop control).
- Switching to sim-clock timing (wall-clock `time.sleep` is acceptable).
- Parallelizing mode logic or peer-state exchange (microsecond cost, not worth the
  synchronization complexity).

## Capabilities

### New Capabilities

- `run-estop-integration`: Server-side E-STOP flag, interruptible animation phases,
  `estop_aborted` terminal status, and async run execution so E-STOP requests are
  receivable during a run.

### Modified Capabilities

- `reliable-joint-publishing`: Existing spec covers retry-based publishing for the
  removed `_publish_joint_gz` path. This change replaces that with triple-publish in
  `_gz_publish` for the current run path.
- `gazebo-scenario-execution`: Animation timing changes (~5.5 s → ~7.3 s per pick due
  to triple-publish overhead). Paired steps animate both arms in parallel instead of
  sequentially.
- `dual-arm-run-orchestration`: Paired-step execution model changes from sequential to
  parallel animation with `ThreadPoolExecutor`. Step reports collected in deterministic
  arm-id order.

## Impact

- **Files modified:** `testing_backend.py`, `run_controller.py`, `run_step_executor.py`
- **Test files:** `test_run_step_executor.py`, `test_run_controller.py`,
  `test_motion_backed_e2e.py` (new tests only — 0 existing tests break)
- **APIs:** `/api/run/start` response may include `estop_aborted` steps when E-STOP
  fires mid-run. `/api/estop` gains server-side run-cancellation side-effect.
- **Timing:** Single-arm step ~5.5 s → ~7.3 s. Dual-arm step ~11 s → ~7.3 s (net
  faster for dual-arm runs).
