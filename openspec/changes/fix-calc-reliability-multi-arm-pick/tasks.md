## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1. Fix JS camera-to-arm transform | — | 2, 3 |
| 2. Reliable joint publishing | — | 1, 3 |
| 3. Cotton persistence after pick | — | 1, 2 |
| 4. Per-arm pick state | 2, 3 | — |
| 5. Multi-arm pick-all | 4 | — |
| 6. Frontend updates | 1, 4, 5 | — |
| 7. Update existing tests | 4, 5 | 6 |

## 1. Fix JS camera-to-arm transform [PARALLEL with 2, 3]

- [x] 1.1 Write JS test: `initCameraToArmTransform` produces forward transform matrix matching Python `_T_CAM_TO_ARM` values for URDF xyz/rpy
- [x] 1.2 Rewrite `initCameraToArmTransform()` in `testing_ui.js` to use forward URDF transform (`arm_xyz = R @ cam_xyz + t`) instead of inverse (`R^T`, `-R^T·t`)
- [x] 1.3 Write JS test: `camToJoint` returns null when `r < 1e-6` (degenerate radius)
- [x] 1.4 Add `r < 1e-6` guard in JS `camToJoint`, returning null with error
- [x] 1.5 Write JS test: `camToJoint` r threshold uses `1e-6` (not `1e-9`)
- [x] 1.6 Change JS `camToJoint` r threshold from `1e-9` to `1e-6`
- [x] 1.7 Write JS test: `camToJoint` matches Python `camera_to_arm` + `polar_decompose` output for all 5 real arm log data points
- [x] 1.8 Verify all 5 log data points pass in JS (green)
- [x] 1.9 Refactor: extract shared constants (threshold, HARDWARE_OFFSET) into a JS config object

## 2. Reliable joint publishing [PARALLEL with 1, 3]

- [x] 2.1 Write Python test: `_publish_joint_gz` returns True when first subprocess succeeds (returncode 0)
- [x] 2.2 Write Python test: `_publish_joint_gz` retries on first failure, returns True on second success
- [x] 2.3 Write Python test: `_publish_joint_gz` returns False after 3 consecutive failures
- [x] 2.4 Write Python test: `_publish_joint_gz` handles subprocess timeout (kills process, retries)
- [x] 2.5 Rewrite `_publish_joint_gz` with retry loop: up to 3 attempts, `Popen.wait(timeout=2)`, returncode check, 200ms delay between retries
- [x] 2.6 Write Python test: `_publish_joint_gz` logs warning on failed attempt with topic, value, attempt number
- [x] 2.7 Write Python test: `_publish_joint_gz` logs error when all 3 attempts fail
- [x] 2.8 Add logging to `_publish_joint_gz`: DEBUG on success, WARNING on retry, ERROR on total failure
- [x] 2.9 Write Python test: per-arm joint lock serializes concurrent publishes on same arm
- [x] 2.10 Write Python test: per-arm joint lock allows concurrent publishes on different arms
- [x] 2.11 Add `_arm_joint_locks: dict[str, threading.Lock]` initialized for all 3 arms, acquire in `_publish_joint_gz`
- [x] 2.12 Refactor: extract retry constants (MAX_RETRIES=3, RETRY_DELAY=0.2, PUBLISH_TIMEOUT=2) to module-level

## 3. Cotton persistence after pick [PARALLEL with 1, 2]

- [x] 3.1 Write Python test: `_execute_pick_sequence` sets cotton status to "picked" after animation completes
- [x] 3.2 Write Python test: `_execute_pick_sequence` does NOT call `_gz_remove_model`
- [x] 3.3 Remove `_gz_remove_model` call from `_execute_pick_sequence` (lines 1023-1027), set `cotton.status = "picked"` instead
- [x] 3.4 Write Python test: `_execute_pick_all_sequence` sets each cotton status to "picked" without calling `_gz_remove_model`
- [x] 3.5 Remove `_gz_remove_model` call from `_execute_pick_all_sequence` (lines 1182-1184), keep `cotton.status = "picked"`
- [x] 3.6 Write Python test: after single pick, `GET /api/cotton/list` shows cotton with status "picked" (not removed from collection)
- [x] 3.7 Remove `_cotton_spawned = False` reset from single pick path (model still exists)
- [x] 3.8 Write Python test: `POST /api/cotton/remove` still deletes Gazebo model for a "picked" cotton
- [x] 3.9 Write Python test: `POST /api/cotton/remove-all` still deletes all Gazebo models regardless of status
- [x] 3.10 Verify existing remove/remove-all tests still pass (green)

## 4. Per-arm pick state [SEQUENTIAL]

- [x] 4.1 Write Python test: `ArmPickState` dataclass has fields: lock, in_progress, status, current, progress with correct defaults
- [x] 4.2 Create `ArmPickState` dataclass in `testing_backend.py`
- [x] 4.3 Write Python test: `_arm_pick_state` dict is initialized with entries for all 3 arms from ARM_CONFIGS
- [x] 4.4 Replace global `_pick_lock`, `_pick_in_progress`, `_pick_status`, `_pick_current`, `_pick_progress` with `_arm_pick_state` dict
- [x] 4.5 Write Python test: `POST /api/cotton/pick` acquires per-arm lock and sets arm-specific state
- [x] 4.6 Update `POST /api/cotton/pick` handler to use `_arm_pick_state[arm_name]` instead of globals
- [x] 4.7 Write Python test: `POST /api/cotton/pick` returns 409 only when the SAME arm is already picking (not when a different arm is picking)
- [x] 4.8 Update pick conflict check to use per-arm `in_progress` instead of global
- [x] 4.9 Write Python test: `_execute_pick_sequence` updates per-arm state (status, current) through all animation steps
- [x] 4.10 Update `_execute_pick_sequence` to write to `_arm_pick_state[arm_name]` instead of global variables
- [x] 4.11 Write Python test: `GET /api/cotton/pick/status` returns `{"arms": {"arm1": {...}, "arm2": {...}, "arm3": {...}}}` shape
- [x] 4.12 Update status endpoint to return per-arm state from `_arm_pick_state`
- [x] 4.13 Write Python test: status endpoint returns consistent per-arm snapshot under concurrent access
- [x] 4.14 Write Python test: per-arm status resets to "idle" at start of new pick on same arm

## 5. Multi-arm pick-all [SEQUENTIAL]

- [x] 5.1 Write Python test: `POST /api/cotton/pick-all` groups cottons by `cotton.arm` field
- [x] 5.2 Write Python test: pick-all spawns one thread per arm group, threads run in parallel
- [x] 5.3 Update `_execute_pick_all_sequence` to group by arm and spawn parallel threads
- [x] 5.4 Write Python test: pick-all with 4 cottons on 2 arms completes in ~2x single-cotton time (not 4x)
- [x] 5.5 Write Python test: pick-all with all cottons on same arm runs sequentially (single thread)
- [x] 5.6 Write Python test: pick-all returns `{"status": "nothing_to_pick"}` when no spawned cottons (EXISTING)
- [x] 5.7 Write Python test: pick-all skips cottons with status "picked" (EXISTING)
- [x] 5.8 Write Python test: pick-all sets per-arm progress correctly (`[current_index, arm_total]`)
- [x] 5.9 Update pick-all handler to set per-arm progress as each arm's thread progresses
- [x] 5.10 Write Python test: pick-all returns 409 only for arms that are already picking, starts others
- [x] 5.11 Write Python test: `POST /api/cotton/remove-all` returns 400 if ANY arm is picking

## 6. Frontend updates [SEQUENTIAL]

- [x] 6.1 Write JS test: `pollPickStatus` reads per-arm status from `response.arms[selectedArm]`
- [x] 6.2 Update `pollPickStatus` in `testing_ui.js` to parse per-arm status response
- [x] 6.3 Write JS test: `pollPickAllStatus` aggregates progress across all arms
- [x] 6.4 Update `pollPickAllStatus` to aggregate per-arm progress (sum completed / sum total)
- [x] 6.5 Update cotton table status column to reflect per-arm pick progress
- [x] 6.6 Write JS test: `camToJoint` displays error in UI status area when returning null (unreachable)
- [x] 6.7 Add UI error display in `camToJoint` null path (red status message in cotton panel)
- [x] 6.8 Update pick button to use selected arm for 409 conflict check

## 7. Update existing tests for new API shape [PARALLEL with 6]

- [x] 7.1 Update Python tests that check `_pick_status` global to use `_arm_pick_state["arm1"].status`
- [x] 7.2 Update Python tests for status endpoint to expect `{"arms": {...}}` response shape
- [x] 7.3 Update Python tests for pick to expect per-arm 409 behavior (not global)
- [x] 7.4 Update Python tests for remove-all-during-pick to check any-arm-picking logic
- [x] 7.5 Run full Python test suite: `python3 -m pytest web_ui/test_fk_chain.py web_ui/test_cam_markers_backend.py -v`
- [x] 7.6 Run full JS test suite: `node --test web_ui/tests/test_cam_to_joint.js`
- [x] 7.7 Verify all tests green, commit
