## Before / After Behavior

| Item | Before | After |
|------|--------|-------|
| Arm execution | Both arms step-synchronized: arm1 waits for arm2 and vice versa at every step boundary | Each arm runs in its own thread, advancing immediately after its own pick completes |
| Arm1 cotton count | Must equal arm2 count (paired step_ids) | Independent: arm1 can have 3 cottons while arm2 has 5 |
| Cotton colour | All cotton balls spawn white | arm1 cottons spawn red, arm2 cottons spawn blue |
| Cotton spawn | Sequential blocking loop: N spawns × ~1 s each = N seconds before first motion | All N spawns concurrent: total spawn time ≈ 1 single spawn call |
| Per-pick wall time | ~7.3 s (5.5 s sleeps + 6 commands × 0.3 s triple-publish overhead) | ~3.35 s (2.75 s sleeps + 6 commands × 0.1 s overhead) |
| Peer state for mode logic | Guaranteed same-step_id state (step-synchronized) | Latest-published state (may be one step stale) |
| LocalPeerTransport | Not thread-safe (single-threaded loop only) | Lock-protected publish/receive |
| JsonReporter | Not thread-safe | Lock-protected add_step |
| TruthMonitor | Not thread-safe | Lock-protected observe |
| Step report ordering | Always arm1 before arm2 within each step | Interleaved by thread completion order |
| Scenario files | Both arms have equal step counts with paired step_ids | Asymmetric: arm1 has 3, arm2 has 5; mix of colliding and safe cam positions |

## Performance Impact

| Item | CPU | Memory | Latency |
|------|-----|--------|---------|
| Per-arm thread (×2) | +2 threads during run (~idle during sleep) | +~10 KB per thread stack | — |
| Parallel spawn ThreadPoolExecutor | Brief CPU spike at run start | +N thread pool workers | Spawn latency: N×1 s → ~1 s |
| Lock contention (transport, reporter, truth monitor) | Negligible — O(1) dict ops | No change | <1 µs per lock acquire |
| Halved sleep constants | No change | No change | -3.95 s per arm-step |
| 50 ms retry delay (was 150 ms) | No change | No change | -0.2 s per joint command |

## Unchanged Behavior

- `/api/run/start` and `/api/run/stop` HTTP API endpoints — signatures unchanged
- Mode logic algorithms (UNRESTRICTED, BASELINE_J5_BLOCK_SKIP, GEOMETRY_BLOCK, OVERLAP_ZONE_WAIT) — unchanged
- E-STOP detection and response — unchanged
- Joint topic names, Gazebo topic/service paths — unchanged
- URDF, joint limits, PID gains, Gazebo world physics — unchanged
- `arm_pair` selection mechanism — unchanged
- Cotton ball geometry (sphere radius 0.04 m) — unchanged
- Pick animation sequence (j4 → j3 → j5 → retract → j3 home → j4 home) — unchanged
- Reachability check (F2 fix) and prev_joints gate (F1 fix) — unchanged
- Frontend HTML/JS — no changes

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Halved sleeps cause arm to miss joint target | Low | J4/J5 p_gain=500, cmd_max=500 N; 0.4 s sufficient for typical 0.1–0.3 m travel at 0.5 m/s limit |
| Stale peer state causes incorrect mode decision | Low | j4 changes <0.05 m between steps; stale by 1 step is acceptable |
| `_cotton_counter` global in testing_backend.py has race condition | Medium | Add threading.Lock around counter increment in task 5 |
| Truth monitor step observations not meaningful for async arms | Medium | Observation key changed to monotonic counter; semantics noted in report |
| Existing tests that assert step-sync ordering break | Certain | Task 5.7 requires fixing regressions before commit |

## Blast Radius

| File | Change type | Approx. lines changed |
|------|------------|----------------------|
| `run_controller.py` | Rewrite execution loop | ~80 lines |
| `peer_transport.py` | Add Lock | ~10 lines |
| `json_reporter.py` | Add Lock | ~8 lines |
| `truth_monitor.py` | Add Lock | ~8 lines |
| `testing_backend.py` | Colour template + parallel spawn + retry delay | ~25 lines |
| `run_step_executor.py` | Timing constants | ~6 lines |
| `scenarios/geometry_pack.json` | Replaced | ~20 lines |
| `scenarios/contention_pack.json` | Replaced | ~22 lines |
| `test_run_controller.py` | New + updated tests | ~100 lines |
| `test_motion_backed_e2e.py` | New timing tests | ~20 lines |
| `test_run_step_executor.py` | Timing constant assertions | ~10 lines |
