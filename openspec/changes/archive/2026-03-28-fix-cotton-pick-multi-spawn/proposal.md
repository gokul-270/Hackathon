## Why

The Phase 1 cotton placement port (camera-to-arm calculation, Gazebo marker spawn, animated pick sequence) works end-to-end but real testing revealed three problems: (1) the pick completion status fires 6-12 times per single pick due to stacking `setInterval` polls and unreset backend state, (2) `camera_to_arm()` used the **inverse** of the camera joint transform instead of the forward transform, producing wrong arm-frame coordinates that appeared unreachable and got silently clamped to J3=0, J5=0 (fixed in commit `1a10ee8` — validated against 5-point real arm log data), and (3) only one cotton can exist at a time but users need to spawn multiple cottons and have the arm pick them sequentially.

## What Changes

- **Fix poll stacking**: Add a module-level guard in `pollPickStatus()` to prevent multiple `setInterval` instances from running simultaneously; reset `_pick_status` to `"idle"` before each new pick begins
- **Add threading safety**: Protect `_pick_in_progress` and `_pick_status` with a `threading.Lock` so the status endpoint reads a consistent snapshot
- **Fix camera_to_arm transform** (DONE — commit `1a10ee8`): `camera_to_arm()` was using `np.linalg.inv()` (inverse) of the camera joint transform instead of the forward transform, producing wrong arm-frame coordinates. Fixed to use forward transform, validated against 5-point real arm log
- **Reject unreachable targets**: For edge-case targets near the workspace boundary where `polar_decompose()` returns `reachable=False`, the `/api/cotton/pick` and `/api/cotton/compute` endpoints return an error response instead of proceeding with clamped joint values
- **Clear stale state on remove**: Clear `_last_cotton_cam` when a cotton is removed so a subsequent pick cannot target a deleted cotton
- **Replace singleton cotton state with a collection**: Convert `_cotton_spawned`, `_cotton_name`, `_last_cotton_cam` into a dict of `CottonState` objects keyed by cotton name
- **Add sequential multi-pick**: Arm picks cottons one-by-one in spawn order, returning home after the final pick completes
- **Add "Remove All" UI**: Button to remove all spawned cottons from Gazebo in one action
- **Multi-cotton table UI**: Display all spawned cottons with individual status in the Cotton Placement panel

## Capabilities

### New Capabilities

- `pick-status-reliability`: Fix the triple bug in pick status reporting -- poll interval stacking on the frontend, unreset backend status between picks, and unguarded concurrent access to status globals
- `reachable-target-validation`: Reject edge-case unreachable targets at the API level with a clear error message; clear stale cotton references on remove. (The primary transform bug is already fixed in commit `1a10ee8`.)
- `multi-cotton-management`: Spawn N cottons (each persists in Gazebo with its own marker), sequential arm pick through all cottons in order, return-home after last pick, remove-all button, collection-based backend state

### Modified Capabilities

(none -- no existing specs are affected)

## Impact

- **Backend** (`testing_backend.py`): Cotton state refactored from singleton globals to a collection; new endpoints for sequential multi-pick and remove-all; threading lock on pick status; pick/compute endpoints gain reachability validation
- **Frontend JS** (`testing_ui.js`): `pollPickStatus()` rewritten with module-level guard; multi-cotton spawn/pick/remove-all wiring; cotton table rendering
- **Frontend HTML/CSS** (`testing_ui.html`, `testing_ui.css`): Cotton table UI, remove-all button, per-cotton status indicators
- **FK module** (`fk_chain.py`): Transform bug fixed (forward instead of inverse, commit `1a10ee8`). `polar_decompose()` unchanged. Regression test added with 5-point real arm log data
- **Test files**: All 5 test files updated (`test_fk_chain.py`, `test_cam_markers_backend.py`, `test_cam_to_joint.js`, `cotton_placement.spec.js`, `cotton_sequence.spec.js`)
