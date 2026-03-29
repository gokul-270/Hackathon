## Why

The current dual-arm run is step-synchronized: both arms must finish each step_id before either can advance, arm cotton colours are identical (white), all cottons spawn sequentially before any motion begins, and arm animation is slow (~5.5 s per pick). This makes the simulation hard to visualise, slow to iterate, and unrealistic for asymmetric field layouts where arms have different cotton counts.

## What Changes

- **BREAKING** `RunController.run()` replaced: step-synchronized loop → two fully independent per-arm threads, each processing its own step list without waiting for the peer.
- `LocalPeerTransport` made thread-safe (Lock on publish/receive) so independent arm threads can share peer state safely.
- `JsonReporter.add_step()` made thread-safe (Lock) for concurrent writes from two arm threads.
- `_COTTON_SDF_TEMPLATE` in `testing_backend.py` parameterised with `{ambient}` / `{diffuse}` so arm1 cottons spawn red and arm2 cottons spawn blue.
- Upfront cotton spawn loop parallelised with `ThreadPoolExecutor` (all cottons spawned concurrently, not sequentially).
- Animation timing constants in `run_step_executor.py` halved (~2.75 s per pick vs 5.5 s).
- Triple-publish inter-attempt delay reduced 150 ms → 50 ms.
- `geometry_pack.json` and `contention_pack.json` replaced with asymmetric scenarios: arm1 has 3 cottons, arm2 has 5, mixing colliding (close arm_y / j4) and safe (far arm_y / j4) positions.

## Capabilities

### New Capabilities

- `independent-arm-execution`: Two arm threads run their pick sequences without step synchronisation; each arm advances as soon as its own pick animation finishes, regardless of peer progress.
- `per-arm-cotton-colour`: Cotton ball colour at spawn time is determined by arm identity (arm1=red, arm2=blue) for visual disambiguation in Gazebo.
- `parallel-cotton-spawn`: All run cottons are spawned concurrently at run start, reducing wall-clock latency before first arm motion.
- `faster-pick-animation`: Reduced sleep constants and publish-retry delay make each pick complete in ~2.75 s instead of ~5.5 s.

### Modified Capabilities

- `dual-arm-run-orchestration`: Execution model changes from step-synchronized to per-arm-independent; truth monitor observation and step reporting now happen per-arm asynchronously.
- `gazebo-scenario-execution`: Scenario files change from paired (same step_id for both arms) to asymmetric (different step counts per arm, colliding and safe positions mixed).

## Impact

- `run_controller.py` — core execution loop rewritten (independent threads)
- `peer_transport.py` — Lock added for thread safety
- `json_reporter.py` — Lock added for thread safety
- `testing_backend.py` — `_COTTON_SDF_TEMPLATE` colour params; parallel spawn; publish-retry delay
- `run_step_executor.py` — timing constants halved
- `scenarios/geometry_pack.json` — replaced
- `scenarios/contention_pack.json` — replaced
- Tests: `test_run_controller.py`, `test_motion_backed_e2e.py` updated; new unit tests for thread safety
- No changes to API endpoints, Gazebo topics, URDF, launch files, or frontend
