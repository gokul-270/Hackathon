## Why

Four production-blocking issues were discovered during real-arm testing of the vehicle_arm_sim cotton pick system: (1) the JS frontend computes an **inverse** camera-to-arm transform while the Python backend uses the correct **forward** transform, causing wrong J3/J5 values for some camera coordinates; (2) `_publish_joint_gz` fires a single `gz topic` subprocess with no error checking, making arm movement unreliable; (3) cotton models are deleted from Gazebo during pick sequences, but the user wants them to persist until manually removed; and (4) a single global pick lock prevents multiple arms from picking simultaneously. These must be fixed before multi-arm field deployment.

## What Changes

- **Fix JS camera-to-arm transform**: Replace the inverse transform computation in `testing_ui.js:initCameraToArmTransform()` with the forward URDF transform (matching `fk_chain.py:camera_to_arm()`). Unify the `r` threshold to `1e-6` across JS and Python. Add the missing `r > 0.1` reachability guard in JS `camToJoint`.
- **Fix arm movement reliability**: Replace single-fire `subprocess.Popen` in `_publish_joint_gz` with retry-based publishing (up to 3 attempts with `Popen.wait()` and return-code checking). Log failures. Add a mutex to prevent frontend slider commands and backend pick animation from racing on the same joints.
- **Stop deleting cotton after pick**: Remove `_gz_remove_model` calls from `_execute_pick_sequence` and `_execute_pick_all_sequence`. Update cotton status to `"picked"` instead. Keep manual remove endpoints (`/api/cotton/remove`, `/api/cotton/remove-all`) as the only way to delete cotton models.
- **Enable multi-arm simultaneous pick**: Replace the global `_pick_lock`/`_pick_in_progress`/`_pick_status` with per-arm `ArmPickState` (own lock, status, thread per arm). Update `pick-all` to group cottons by their stored `arm` field and dispatch parallel pick threads per arm. Update status endpoint to return per-arm state.

## Capabilities

### New Capabilities
- `reliable-joint-publishing`: Retry-based Gazebo joint publishing with error detection, return-code checking, and race-condition protection between frontend sliders and backend pick animation.
- `multi-arm-simultaneous-pick`: Per-arm pick state management allowing multiple arms to execute pick sequences concurrently, with per-arm status tracking and pick-all auto-grouping by arm.

### Modified Capabilities
- `reachable-target-validation`: JS frontend currently lacks the `r > 0.1` reachability guard and uses a different transform direction than the backend. The JS transform must be corrected to forward (matching Python) and the reachability check must be added.
- `multi-cotton-management`: Cotton models must NOT be deleted during pick. Pick sequences change cotton status to `"picked"` instead of removing the Gazebo model. Manual remove endpoints remain the only deletion path.
- `pick-status-reliability`: Status endpoint must support per-arm state (not a single global status). Pick-all must dispatch per-arm threads and report per-arm progress.

## Impact

- **Backend** (`testing_backend.py`): `_publish_joint_gz` rewritten with retry logic; `_execute_pick_sequence` and `_execute_pick_all_sequence` modified to stop deleting models; global pick state replaced with per-arm `ArmPickState` dataclass; status endpoint returns per-arm data.
- **Frontend** (`testing_ui.js`): `initCameraToArmTransform` rewritten to use forward transform; `camToJoint` gains reachability guard; `pollPickStatus`/`pollPickAllStatus` updated for per-arm status responses; pick UI shows per-arm progress.
- **APIs**: `GET /api/cotton/pick/status` response shape changes from `{status, current, progress}` to `{arms: {arm1: {status, current, progress}, ...}}` — **BREAKING** for any client polling the old shape.
- **Tests**: New tests for retry publishing, per-arm pick state, forward transform in JS, cotton persistence after pick. Existing tests updated for new status response shape.
- **No URDF changes**. No new dependencies. No ROS2 node changes.
