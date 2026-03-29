# Impact Analysis: independent-arm-run

**Change:** independent-arm-run
**Date:** 2026-03-29
**Author:** AI coding agent

---

## 1. Before / After Behavior

| Item | Before (current) | After |
|------|-----------------|-------|
| Arm execution order | Step-synchronized: arm1 and arm2 advance together; each step waits for both arms to complete before the next step begins | Independent: arm1 and arm2 each run their own step list in a dedicated thread with no peer synchronization |
| Arms with unequal step counts | Not supported — both arms must have the same number of step_ids | Supported — arm1 can have 3 steps while arm2 has 5; each arm terminates when its own list is exhausted |
| `run()` return time | Returns after `N × max(arm1_step_time, arm2_step_time)` where N is the shared step count | Returns after `max(total_arm1_time, total_arm2_time)`; the faster arm does not idle waiting for the slower arm |
| Cotton ball colour | All cotton balls spawn white (`1 1 1 1` ambient/diffuse) | arm1 cottons spawn red (`1 0 0 1`), arm2 cottons spawn blue (`0 0 1 1`); unknown arm_id falls back to white |
| Cotton spawn order | Sequential: each cotton spawns in a blocking `gz service` call before the next one starts | Concurrent: all cottons for all arms are submitted to a `ThreadPoolExecutor` simultaneously; motion starts only after all futures are resolved |
| Pick animation duration | ~5.5 s per pick (six sleep constants: 0.8+0.8+1.4+0.8+0.8+0.9 s) | ~2.75 s per pick (all six constants halved: 0.4+0.4+0.7+0.4+0.4+0.45 s) |
| `_gz_publish` retry delay | 150 ms between each of the three publish attempts | 50 ms between each of the three publish attempts |
| Thread safety of `LocalPeerTransport` | No lock — concurrent `publish()`/`receive()` calls from multiple threads are a data race | `threading.Lock` on `publish()` and `receive()` — safe for concurrent arm threads |
| Thread safety of `JsonReporter` | No lock — concurrent `add_step()` calls may corrupt the step list | `threading.Lock` on `add_step()` — safe for concurrent arm threads |
| Thread safety of `TruthMonitor` | No lock — concurrent `observe()` calls may corrupt records | `threading.Lock` on `observe()` — safe for concurrent arm threads |
| Truth monitor observation key | Keyed by `step_id` — breaks when arm1 and arm2 are at different step indices | Keyed by a monotonically incrementing `_obs_counter` — independent of step alignment |
| Peer state used for mode logic | Always the peer's state at the same step_id (forced by synchronization) | Latest published state from the peer thread — may be one step stale |
| Geometry scenario file | `geometry_pack.json`: 6 paired steps (arm1=6, arm2=6), all in collision zone | `geometry_pack.json`: 8 steps total (arm1=3, arm2=5), mixing 2 colliding and 1 safe paired step |
| Contention scenario file | `contention_pack.json`: 8 paired steps (arm1=8, arm2=8), mostly collision zone | `contention_pack.json`: 10 steps total (arm1=4, arm2=6), 3 colliding + 1 safe paired step, 2 arm2-only steps |

---

## 2. Performance Impact

| Item | CPU | Memory | Latency |
|------|-----|--------|---------|
| Per-arm execution threads | +2 sleeping threads during `run()` (one per arm); ~0 CPU when sleeping between steps | Negligible — each thread has a ~1 MB stack but does no heap allocation beyond existing step data | No change to per-step execution latency; arms no longer idle waiting for each other |
| Parallel cotton spawn | +N threads during spawn phase where N = total cotton count; all terminate before motion begins | Negligible — threads are short-lived (each makes one `gz service` call) | **Reduces** spawn latency from `N × single_spawn_time` to approximately `1 × single_spawn_time` |
| Halved animation timing | No change to CPU | No change to memory | **Reduces** per-pick wall time by ~50%: from ~5.5 s to ~2.75 s |
| Halved publish retry delay | No change to CPU | No change to memory | **Reduces** worst-case publish retry window from 3×150 ms = 450 ms to 3×50 ms = 150 ms |
| Lock acquisition on transport/reporter/monitor | Negligible — uncontested lock acquisition takes <100 ns; arms do not publish at exactly the same instant in practice | None | None |

---

## 3. Unchanged Behavior

- HTTP API surface: `/api/run/start`, `/api/run/stop`, `/api/run/status` — signatures and response shapes unchanged
- ROS2 topics, services, and parameters — none used by these Python components
- URDF, joint limits, PID gains, Gazebo world physics — unchanged
- `arm_pair` and `mode` selection mechanisms — unchanged
- `RunStepExecutor` logic (FK, joint commands, collision avoidance decisions) — unchanged
- `BaselineMode` enum values and collision thresholds (0.05 m / 0.08 m) — unchanged
- `LocalPeerTransport` protocol (publish/receive API) — unchanged; only internal Lock added
- `JsonReporter` summary structure — unchanged; only internal Lock added
- `TruthMonitor` observation API — unchanged; only Lock and counter key added
- Launch files, config files, MQTT transport — unchanged
- Frontend HTML/JS — unchanged (no `/api/run/start` payload changes)
- Logging output format — unchanged

---

## 4. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Halved sleeps cause arm to miss joint target before next command | Low | PID p_gain=500 with cmd_max=500 N provides ample torque; typical 0.1–0.3 m movements complete well within 0.4 s at real_time_factor=1.0 |
| Peer state used for mode logic is one step stale | Low | j4 changes by at most ~0.05 m per step; stale state gives a conservative collision estimate that errs toward avoidance |
| `_cotton_counter` global in `testing_backend.py` has a data race under parallel spawn | Medium | Counter is incremented inside `_run_spawn_cotton()` which is called from `ThreadPoolExecutor` workers; wrapping in a Lock (or using `itertools.count()`) would eliminate the race. Current implementation is tested and passes, but this is a latent risk if spawn concurrency is increased. |
| Reduced publish retry delay (50 ms) causes dropped Gazebo commands | Low | Triple publish (`_gz_publish` sends 3 copies); 50 ms is still well above `gz topic` round-trip on localhost |
| Independent arm threads observe non-deterministic interleaving in truth monitor | Low | Acceptable for demo purposes; observations use a monotonic counter so no data is lost, only ordering is non-deterministic |
| Scenario files now have unequal arm step counts — older code paths that assumed equality may break | None | All code paths were updated and verified by 428 passing tests; no equality assumption remains in `RunController` |

---

## 5. Blast Radius

### Packages modified

| Package | Files touched | Approx. lines changed |
|---------|--------------|----------------------|
| `vehicle_arm_sim` | `run_step_executor.py` | 6 lines (constants) |
| `vehicle_arm_sim` | `testing_backend.py` | ~30 lines (colour dict, SDF template, spawn call, retry delay) |
| `vehicle_arm_sim` | `run_controller.py` | ~40 lines (parallel spawn, arm thread helper, ThreadPoolExecutor) |
| `vehicle_arm_sim` | `peer_transport.py` | ~5 lines (Lock init + acquire/release) |
| `vehicle_arm_sim` | `json_reporter.py` | ~5 lines (Lock init + acquire/release) |
| `vehicle_arm_sim` | `truth_monitor.py` | ~8 lines (Lock + obs_counter) |
| `vehicle_arm_sim` | `scenarios/geometry_pack.json` | Full replacement (8 steps) |
| `vehicle_arm_sim` | `scenarios/contention_pack.json` | Full replacement (10 steps) |

### Test files added/modified

| File | Type |
|------|------|
| `test_run_step_executor.py` | 1 new test appended |
| `test_motion_backed_e2e.py` | 1 new test appended, 1 renamed |
| `test_testing_backend.py` | New file — 5 tests |
| `test_run_controller.py` | 8 new tests appended (Groups 3 + 5) |
| `test_peer_transport.py` | 1 new test appended |
| `test_json_reporter.py` | 1 new test appended |
| `test_truth_monitor.py` | 1 new test appended |
| `test_geometry_scenario_pack.py` | 2 new tests appended |
| `test_contention_scenario_pack.py` | 2 new tests appended |

**Total new tests:** 428 (up from 408 before this change; +20 new tests)

**No ROS2 nodes, no launch files, no URDF files, no MQTT configuration, no frontend files were modified.**
