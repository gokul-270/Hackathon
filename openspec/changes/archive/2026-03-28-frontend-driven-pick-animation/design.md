## Context

The vehicle_arm_sim web UI has two pathways for moving arm joints:

1. **Frontend pathway (reliable)**: `publishArmJoint()` → rosbridge WebSocket (port 9090) → ROS2 topic → parameter_bridge → Gazebo. Used by sliders, cosine test, custom sequence, cotton sequence. Sliders visually track position via `updateSliderUI()`.

2. **Backend pathway (unreliable)**: `_publish_joint_gz()` → `subprocess.Popen("gz topic ...")` → Gazebo transport directly (bypasses ROS2). Used by the pick animation. Sliders do NOT move during pick. The `gz topic` CLI subprocess is fundamentally unreliable — sometimes commands don't take effect even with 3-retry logic added in the previous change.

The pick animation is the only arm movement that uses the backend pathway. All other movements (sliders, cosine test, custom sequence, cotton sequence) use the frontend pathway successfully. This change unifies all arm movement through the frontend pathway.

**Constraints**: FastAPI HTTP endpoints for all cotton features. TDD mandatory (red-green-refactor). Python 3 on Ubuntu 24.04. Three arms with different topic naming conventions. Frontend uses vanilla JS (no frameworks).

## Goals / Non-Goals

**Goals:**
- Pick animation uses `publishArmJoint()` + `updateSliderUI()` — same pathway as sliders and sequence players
- Sliders visually move during pick animation
- Triple-publish (3x, 500ms gaps) per joint command for reliable delivery
- Multi-arm pick-all runs parallel async animations per arm via `Promise.all()`
- Backend marks cotton "picked" via dedicated endpoint called by frontend after J5-extend
- Remove all backend animation code (`_publish_joint_gz`, `_execute_pick_sequence`, etc.)
- Remove frontend polling (`pollPickStatus`, `pollPickAllStatus`)

**Non-Goals:**
- Changing the URDF kinematic chain or joint limits
- Changing the 6-step pick sequence order (J4→J3→J5→retract→home)
- Adding new UI panels or pages
- Changing the cotton spawn/remove workflow
- Supporting more than 3 arms

## Decisions

### D1: Frontend-driven animation via publishArmJoint

**Choice**: The backend `/api/cotton/pick` endpoint becomes compute-only — it calculates j3/j4/j5 via `camera_to_arm()` + `polar_decompose()` + `phi_compensation()` and returns them immediately. The frontend runs the 6-step timed animation using `publishArmJoint()` + `updateSliderUI()`, following the same `async/await` + `sleep()` pattern as `runCosineTest()`.

**Alternatives considered**:
- *Backend publishes via rosbridge WebSocket (Python client)*: Would add a rosbridge client dependency to the backend. Sliders still wouldn't move. Rejected.
- *Keep gz topic subprocess + sync sliders via WebSocket*: Keeps the unreliable pathway, just masks it with UI sync. Rejected.

### D2: Triple-publish for reliability (3x, 500ms gaps)

**Choice**: Each joint command in the pick animation is published 3 times with 500ms gaps between publishes, matching `runCosineTest()`'s homing pattern. A helper function `triplePublish(topic, value)` encapsulates this. `updateSliderUI()` is called once after the triple-publish completes (before the hold delay).

**Timing per step**: ~1s (triple-publish) + hold delay = ~1.8s per step vs ~0.8s previously.
**Total animation**: ~11.5s per cotton vs ~5.5s. 2x slower but reliable.

**Alternatives considered**:
- *Single publish (like `runCottonSequence()`)*: Faster but less reliable. Rejected per user preference.

### D3: Parallel async animations for pick-all

**Choice**: `cottonPickAll()` receives per-arm grouped cotton data from the backend, then launches concurrent async functions via `Promise.all()`. Each arm's function picks its cottons sequentially (one full 6-step animation per cotton). All arms animate simultaneously since they publish to independent ROS2 topics and update independent slider DOM elements.

```javascript
// Pseudocode
var armPromises = Object.keys(data.arms).map(function(armKey) {
    return pickArmCottons(armKey, data.arms[armKey]);
});
await Promise.all(armPromises);
```

Where `pickArmCottons(armKey, cottons)` loops through cottons sequentially, calling `executePickAnimation()` for each.

**Alternatives considered**:
- *Sequential per arm*: Simpler but doesn't leverage multi-arm capability. Rejected per user preference.

### D4: Backend marks picked via POST /api/cotton/{name}/mark-picked

**Choice**: After J5-extend (step 3), the frontend calls `POST /api/cotton/{name}/mark-picked`. The backend sets `_cottons[name].status = "picked"` and returns `{"status": "ok"}`. Returns 404 if cotton not found, 409 if already picked.

This keeps the source of truth on the backend while giving the frontend control of when "picked" status is applied — cotton is only marked picked after the arm physically reaches it.

**Alternatives considered**:
- *Mark on computation (before animation starts)*: Cotton marked picked even if animation aborted. Rejected.
- *Frontend-only tracking*: Loses backend state consistency. Rejected.

### D5: Remove /api/cotton/pick/status endpoint and all polling

**Choice**: Since the frontend drives the animation, it knows the current step directly — no backend polling needed. The frontend updates the status div text at each animation step (same phase names: "j4_lateral", "j3_tilt", etc.). The pick-all aggregates status across concurrent arm animations.

This removes: `pollPickStatus()`, `pollPickAllStatus()`, `_pickPollInterval`, `_pickAllPollInterval` from frontend. Removes `GET /api/cotton/pick/status`, `ArmPickState`, `_arm_pick_state` from backend.

### D6: Abort and E-STOP handling

**Choice**: Module-level `pickRunning` and `pickAborted` booleans (same pattern as `testRunning`/`testAborted` in cosine test). Each step in `executePickAnimation()` checks `pickAborted || estopActive` before publishing. For pick-all, `pickAllAborted` stops all concurrent arm animations.

The existing Pick button is disabled during animation. No separate stop button added — E-STOP serves as the emergency stop, and `pickAborted` can be set by re-clicking the disabled button or by future UI additions.

### D7: API response format changes

**`POST /api/cotton/pick` response** (changed):
```json
{
  "status": "ready",
  "j3": -0.3, "j4": 0.1, "j5": 0.25,
  "arm": "arm1",
  "cotton_name": "cotton_1",
  "reachable": true
}
```
Previously returned `status: "picking"` and launched a background thread.

**`POST /api/cotton/pick-all` response** (changed):
```json
{
  "status": "ready",
  "arms": {
    "arm1": [{"name": "cotton_1", "j3": -0.3, "j4": 0.1, "j5": 0.25}],
    "arm3": [{"name": "cotton_3", "j3": -0.4, "j4": -0.1, "j5": 0.30}]
  }
}
```
Previously returned `status: "picking"` with `total` count and launched threads.

## Risks / Trade-offs

- **[Slower animation]** Triple-publish adds ~1s per step → ~11.5s total vs ~5.5s. → Mitigation: Acceptable trade-off for reliability. Matches cosine test behavior.
- **[Browser tab dependency]** Animation stops if user closes/refreshes the tab mid-pick. Backend-driven was resilient to this. → Mitigation: Pick button disabled during animation. Cotton stays "spawned" if interrupted — user can retry. No data loss.
- **[Parallel async complexity]** Multiple concurrent async functions publishing to different arms simultaneously. → Mitigation: Each arm has its own ROS2 topics and slider DOM elements. No shared mutable state between arms. `updateSliderUI()` targets arm-specific elements via suffix (`_copy`, `_copy1`).
- **[BREAKING API]** Three endpoint response format changes. → Mitigation: Frontend is the only client; both sides updated in the same change.
- **[Mark-picked timing]** If the `mark-picked` POST fails (network error), the cotton stays "spawned" even though the arm reached it. → Mitigation: Frontend can retry the POST. The mark-picked endpoint is idempotent-safe (409 on double-mark). User can also manually pick again.
