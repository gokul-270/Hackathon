## Why

The pick animation uses backend `subprocess.Popen("gz topic ...")` to move arm joints — a fundamentally unreliable pathway that bypasses ROS2 and rosbridge. Meanwhile, sliders, cosine test, and all sequence players use the frontend's `publishArmJoint()` via rosbridge WebSocket, which is reliable. The arm sliders also don't move during backend-driven picks, giving no visual feedback. Moving the pick animation to the frontend pathway eliminates the unreliable subprocess mechanism and unifies all arm movement through a single, proven code path.

## What Changes

- **BREAKING**: `/api/cotton/pick` becomes compute-only — returns j3/j4/j5 values with `status: "ready"` instead of launching a background animation thread
- **BREAKING**: `/api/cotton/pick-all` becomes compute-only — returns per-arm grouped j3/j4/j5 computations instead of spawning threads
- **BREAKING**: `GET /api/cotton/pick/status` endpoint removed — frontend knows its own animation state
- New `POST /api/cotton/{name}/mark-picked` endpoint — frontend calls this after J5-extend to mark cotton as picked
- New frontend `executePickAnimation()` async function — runs the 6-step pick animation using `publishArmJoint()` + `updateSliderUI()`, with triple-publish (3x, 500ms gaps) per joint command for reliability
- Pick-all launches parallel async animations per arm via `Promise.all()` — cottons sequential within each arm, arms simultaneous
- Remove backend animation code: `_publish_joint_gz()`, `_execute_pick_sequence()`, `_execute_pick_all_sequence()`, `ArmPickState`, `_arm_pick_state`, `_arm_joint_locks`, retry constants
- Remove frontend polling: `pollPickStatus()`, `pollPickAllStatus()`, poll interval variables
- Arm sliders now visually move during pick animation (via `updateSliderUI()` at each step)

## Capabilities

### New Capabilities

- `frontend-pick-animation`: The frontend-driven pick animation system — `executePickAnimation()`, `triplePublish()`, abort/E-STOP handling, status UI updates, and the `cottonPick()`/`cottonPickAll()` refactored flow
- `pick-compute-api`: The compute-only backend API — `/api/cotton/pick` and `/api/cotton/pick-all` return joint values without animation, plus new `/api/cotton/{name}/mark-picked` endpoint

### Modified Capabilities

- `pick-status-reliability`: Poll-based status tracking is removed entirely — frontend drives animation state directly, no polling needed
- `multi-cotton-management`: Cotton status transitions change — "picked" is set via explicit `mark-picked` endpoint call from frontend (not by backend animation thread)

## Impact

- **Backend** (`testing_backend.py`): ~120 lines removed (animation functions, publish helpers, state tracking). ~40 lines added (compute-only responses, mark-picked endpoint). Net reduction.
- **Frontend** (`testing_ui.js`): ~80 lines removed (polling functions). ~100 lines added (executePickAnimation, triplePublish, parallel pick-all). Net similar.
- **API**: 3 breaking endpoint changes, 1 new endpoint. Frontend is the only client — updated in the same change.
- **Tests**: Backend animation/publish tests replaced with compute-only + mark-picked tests. New JS tests for animation step ordering and abort handling.
- **Animation timing**: ~11.5s per cotton (triple-publish) vs ~5.5s (single publish). 2x slower but reliable.
