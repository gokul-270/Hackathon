## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1. Backend: Remove animation code | — | 2 |
| 2. Backend: Compute-only endpoints | — | 1 |
| 3. Backend: Mark-picked endpoint | 1, 2 | — |
| 4. Backend: Remove status endpoint & tests | 3 | — |
| 5. Frontend: triplePublish + executePickAnimation | 4 | — |
| 6. Frontend: Refactored cottonPick/cottonPickAll | 5 | — |
| 7. Frontend: Remove polling code | 6 | — |
| 8. Integration verification | 7 | — |

## 1. Backend: Remove animation code [PARALLEL with 2]

- [x] 1.1 Write tests asserting `_publish_joint_gz`, `_execute_pick_sequence`, `_execute_pick_all_sequence` functions do not exist (RED)
- [x] 1.2 Write tests asserting `ArmPickState` class, `_arm_pick_state` dict, `_arm_joint_locks` dict do not exist (RED)
- [x] 1.3 Write tests asserting no `subprocess.Popen` with `"gz topic"` exists in backend (RED)
- [x] 1.4 Remove `ArmPickState` class and `_arm_pick_state` dict from testing_backend.py (GREEN)
- [x] 1.5 Remove `_arm_joint_locks` dict and retry/timing constants (`MAX_RETRIES`, `RETRY_DELAY`, `GZ_PUBLISH_TIMEOUT`) from testing_backend.py (GREEN)
- [x] 1.6 Remove `_publish_joint_gz()` function from testing_backend.py (GREEN)
- [x] 1.7 Remove `_execute_pick_sequence()` function from testing_backend.py (GREEN)
- [x] 1.8 Remove `_execute_pick_all_sequence()` function from testing_backend.py (GREEN)
- [x] 1.9 Remove any existing tests that test the removed animation functions — update test_cam_markers_backend.py (REFACTOR)
- [x] 1.10 Run full test suite, confirm all pass (GREEN gate)

## 2. Backend: Compute-only endpoints [PARALLEL with 1]

- [x] 2.1 Write test: `POST /api/cotton/pick` returns `{status: "ready", j3, j4, j5, arm, cotton_name, reachable: true}` for reachable cotton (RED)
- [x] 2.2 Write test: `POST /api/cotton/pick` returns `reachable: false` with `reason` for unreachable cotton (RED)
- [x] 2.3 Write test: `POST /api/cotton/pick` returns error when no spawned cotton available (RED)
- [x] 2.4 Write test: `POST /api/cotton/pick` does NOT spawn a background thread (RED)
- [x] 2.5 Modify `/api/cotton/pick` to return compute-only response — no thread, no animation (GREEN for 2.1–2.4)
- [x] 2.6 Write test: `POST /api/cotton/pick-all` returns `{status: "ready", arms: {arm1: [...], arm3: [...]}}` grouped by arm (RED)
- [x] 2.7 Write test: `POST /api/cotton/pick-all` returns `{status: "nothing_to_pick"}` when all picked (RED)
- [x] 2.8 Write test: `POST /api/cotton/pick-all` excludes unreachable cottons with `warnings` array (RED)
- [x] 2.9 Write test: `POST /api/cotton/pick-all` does NOT spawn background threads (RED)
- [x] 2.10 Modify `/api/cotton/pick-all` to return compute-only grouped response — no threads (GREEN for 2.6–2.9)
- [x] 2.11 Run full test suite, confirm all pass (GREEN gate)

## 3. Backend: Mark-picked endpoint [SEQUENTIAL]

- [x] 3.1 Write test: `POST /api/cotton/{name}/mark-picked` returns `{status: "ok"}` and sets status to "picked" (RED)
- [x] 3.2 Write test: `POST /api/cotton/{name}/mark-picked` returns 404 for nonexistent cotton (RED)
- [x] 3.3 Write test: `POST /api/cotton/{name}/mark-picked` returns 409 for already-picked cotton (RED)
- [x] 3.4 Implement `POST /api/cotton/{name}/mark-picked` endpoint in testing_backend.py (GREEN)
- [x] 3.5 Run full test suite, confirm all pass (GREEN gate)

## 4. Backend: Remove status endpoint & cleanup tests [SEQUENTIAL]

- [x] 4.1 Write test: `GET /api/cotton/pick/status` returns 404 (RED)
- [x] 4.2 Remove the `GET /api/cotton/pick/status` endpoint from testing_backend.py (GREEN)
- [x] 4.3 Remove any existing tests that reference the old pick/status endpoint or old pick response formats (REFACTOR)
- [x] 4.4 Run full test suite, confirm all pass (GREEN gate)

## 5. Frontend: triplePublish + executePickAnimation [SEQUENTIAL]

- [ ] 5.1 Write JS test: `triplePublish()` calls `publishArmJoint()` 3 times with 500ms gaps (RED)
- [ ] 5.2 Implement `triplePublish(topic, value)` async function in testing_ui.js (GREEN)
- [ ] 5.3 Write JS test: `executePickAnimation()` executes 6 steps in correct order with correct topics per arm (RED)
- [ ] 5.4 Write JS test: `executePickAnimation()` calls mark-picked after step 3 (RED)
- [ ] 5.5 Write JS test: `executePickAnimation()` aborts on `pickAborted` flag — does not call mark-picked if before step 3 (RED)
- [ ] 5.6 Write JS test: `executePickAnimation()` aborts on `estopActive` flag (RED)
- [ ] 5.7 Write JS test: `pickRunning` transitions true→false across animation lifecycle (RED)
- [ ] 5.8 Implement `executePickAnimation(armKey, cottonName, j3, j4, j5)` with abort checks, mark-picked call, status UI updates (GREEN for 5.3–5.7)
- [ ] 5.9 Run JS test suite, confirm all pass (GREEN gate)

## 6. Frontend: Refactored cottonPick/cottonPickAll [SEQUENTIAL]

- [ ] 6.1 Write JS test: `cottonPick()` calls compute-only endpoint then `executePickAnimation()` (RED)
- [ ] 6.2 Write JS test: `cottonPick()` shows red toast and does not animate when `reachable: false` (RED)
- [ ] 6.3 Refactor `cottonPick()` to call compute-only endpoint + `executePickAnimation()` (GREEN)
- [ ] 6.4 Write JS test: `cottonPickAll()` launches parallel `Promise.all()` per arm, sequential within arm (RED)
- [ ] 6.5 Write JS test: `cottonPickAll()` handles `nothing_to_pick` response (RED)
- [ ] 6.6 Implement `pickArmCottons(armKey, cottons)` helper and refactor `cottonPickAll()` (GREEN)
- [ ] 6.7 Write JS test: Pick and Pick All buttons disabled during animation, re-enabled after (RED then GREEN)
- [ ] 6.8 Run JS test suite, confirm all pass (GREEN gate)

## 7. Frontend: Remove polling code [SEQUENTIAL]

- [ ] 7.1 Write JS test: no function `pollPickStatus` or `pollPickAllStatus` exists in source (RED)
- [ ] 7.2 Write JS test: no variable `_pickPollInterval` or `_pickAllPollInterval` exists in source (RED)
- [ ] 7.3 Remove `pollPickStatus()`, `pollPickAllStatus()`, `_pickPollInterval`, `_pickAllPollInterval` from testing_ui.js (GREEN)
- [ ] 7.4 Remove any references to removed polling functions from other code paths (REFACTOR)
- [ ] 7.5 Run full test suite (Python + JS), confirm all pass (GREEN gate)

## 8. Integration verification [SEQUENTIAL]

- [ ] 8.1 Run full Python test suite: `python3 -m pytest web_ui/test_fk_chain.py web_ui/test_cam_markers_backend.py -v`
- [ ] 8.2 Run full JS test suite: `node --test web_ui/tests/test_cam_to_joint.js`
- [ ] 8.3 Verify no `gz topic` subprocess calls remain in testing_backend.py
- [ ] 8.4 Verify no polling functions remain in testing_ui.js
- [ ] 8.5 Verify no `ArmPickState` or `_arm_pick_state` remain in testing_backend.py
- [ ] 8.6 Commit all changes with message `feat: frontend-driven pick animation via rosbridge`
