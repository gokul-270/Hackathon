## Context

The vehicle_arm_sim web UI controls a 3-arm cotton-picking robot via a FastAPI backend (`testing_backend.py`) and browser frontend (`testing_ui.js`). The camera-to-arm coordinate transform, pick animation, cotton lifecycle, and pick concurrency were ported from the single-arm `yanthra_move` project in Phases 1-2. Real-arm testing exposed four issues:

1. The JS frontend computes the **inverse** of the URDF camera-to-arm transform, while the Python backend uses the correct **forward** transform — yielding different arm-frame coordinates for the same camera input.
2. `_publish_joint_gz` fires a single `subprocess.Popen("gz topic ...")` with stdout/stderr to DEVNULL and no return-code check — joints move unreliably.
3. Pick sequences call `_gz_remove_model` which deletes the cotton model from Gazebo — the user wants cotton to persist until manual removal.
4. A single global `_pick_lock` + `_pick_in_progress` prevents more than one arm from picking at a time.

**Constraints**: FastAPI HTTP endpoints (not ROS2 topics) for all cotton features. TDD mandatory (red-green-refactor). Python 3 on Ubuntu 24.04. Three arms with different topic naming conventions.

## Goals / Non-Goals

**Goals:**
- JS and Python camera-to-arm transforms produce identical results for any camera coordinate
- Joint publishing succeeds reliably (≥99% of attempts) with observable failure logging
- Cotton models persist in Gazebo after pick, removable only via explicit user action
- Multiple arms can execute pick sequences simultaneously without blocking each other
- All changes covered by failing-first tests (TDD)

**Non-Goals:**
- Changing the URDF kinematic chain or joint limits
- Adding new UI pages or restructuring the HTML layout
- Implementing ROS2-native joint trajectory controllers (we stay with `gz topic` CLI)
- Changing the pick animation timing or step sequence
- Supporting more than 3 arms (current ARM_CONFIGS is sufficient)

## Decisions

### D1: Forward transform in JS (not inverse)

**Choice**: Rewrite `initCameraToArmTransform()` to use the forward URDF transform (same as `fk_chain.py:_T_CAM_TO_ARM`), computing `arm_xyz = R @ cam_xyz + t` instead of the current `R^T @ cam_xyz + (-R^T @ t)`.

**Alternatives considered**:
- *Keep inverse in JS, invert in Python*: Would require changing the validated Python code that matches real arm log data. Rejected — Python is proven correct.
- *Send camera coords to backend for all transforms*: Would add latency to every UI interaction and complicate the frontend. Rejected.

**Also**: Unify `r` threshold to `1e-6` (currently JS uses `1e-9`) and add `r > 0.1` reachability guard in JS `camToJoint`.

### D2: Retry-based `_publish_joint_gz` with `Popen.wait()`

**Choice**: Publish each joint command up to 3 times with 200ms delay between attempts. Each attempt uses `Popen.wait(timeout=2)` and checks `returncode == 0`. Log on failure. Accept on first success.

**Alternatives considered**:
- *Use rosbridge WebSocket from backend*: Would require a WebSocket client in the backend, adding complexity. The frontend already uses rosbridge for sliders, but the backend's subprocess approach is simpler for fire-and-wait. Rejected.
- *Single publish with longer timeout*: Doesn't address the fundamental unreliability of single-fire CLI commands. Rejected.
- *Publish 3x unconditionally (like frontend)*: Wastes resources when first publish succeeds (majority case). Retry-on-failure is more efficient. Chosen.

**Also**: Add a per-arm `threading.Lock` (`_arm_joint_lock[arm_name]`) to prevent concurrent `gz topic` commands on the same arm from the pick animation thread and any other code path.

### D3: Status-only cotton pick (no model deletion)

**Choice**: Remove `_gz_remove_model(...)` calls from `_execute_pick_sequence` (line 1023-1027) and `_execute_pick_all_sequence` (line 1182-1184). Instead, set `cotton.status = "picked"`. The existing `/api/cotton/remove` and `/api/cotton/remove-all` endpoints remain the only way to delete Gazebo models.

**Alternatives considered**:
- *Add a config flag to toggle deletion*: Over-engineering for a clear user requirement. Rejected.
- *Move model to a "picked" position instead of deleting*: Interesting but scope creep. Rejected.

**Also**: In single-pick, set `cotton.status = "picked"` (currently missing — only pick-all sets it). Remove the `_cotton_spawned = False` reset since the model still exists.

### D4: Per-arm `ArmPickState` dataclass

**Choice**: Replace global `_pick_lock`, `_pick_in_progress`, `_pick_status`, `_pick_current`, `_pick_progress` with a dict `_arm_pick_state: dict[str, ArmPickState]` keyed by arm name. Each `ArmPickState` has its own `threading.Lock`, `in_progress: bool`, `status: str`, `current: Optional[str]`, `progress: tuple[int, int]`.

```python
@dataclasses.dataclass
class ArmPickState:
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    in_progress: bool = False
    status: str = "idle"
    current: Optional[str] = None
    progress: tuple[int, int] = (0, 0)
```

**Alternatives considered**:
- *Keep global lock, queue picks per arm*: Still serializes all picks. Rejected.
- *Use asyncio instead of threads*: Would require rewriting the entire pick animation from `time.sleep()` to `asyncio.sleep()` and changing all the subprocess calls. Too invasive. Rejected.

### D5: Pick-all groups by arm, dispatches parallel threads

**Choice**: `_execute_pick_all_sequence` groups pending cottons by `cotton.arm`, spawns one `threading.Thread` per arm group, each running `_execute_pick_sequence` for its arm's cottons sequentially. This allows Arm 1 and Arm 2 to pick simultaneously while each arm processes its own cottons one at a time.

**Alternatives considered**:
- *Pick all cottons sequentially (current behavior but with per-arm state)*: Doesn't leverage multi-arm capability. Rejected.
- *Fully parallel across all cottons regardless of arm*: Would send conflicting joint commands to the same arm simultaneously. Rejected.

### D6: Status endpoint returns per-arm state (BREAKING)

**Choice**: `GET /api/cotton/pick/status` response changes from:
```json
{"status": "j3_tilt", "current": "cotton_1", "progress": [1, 3]}
```
to:
```json
{
  "arms": {
    "arm1": {"status": "j3_tilt", "current": "cotton_1", "progress": [1, 3]},
    "arm2": {"status": "idle", "current": null, "progress": [0, 0]},
    "arm3": {"status": "idle", "current": null, "progress": [0, 0]}
  }
}
```

Frontend `pollPickStatus` and `pollPickAllStatus` updated to read from `arms[selectedArm]` or aggregate across all arms.

## Risks / Trade-offs

- **[BREAKING API]** Status endpoint shape change breaks any client polling the old format. → Mitigation: Frontend is the only client; updated in the same change.
- **[Retry latency]** 3 retries × 200ms delay adds up to 600ms worst-case per joint command. → Mitigation: First attempt succeeds in most cases; 200ms delay is negligible vs. 5.5s total pick duration.
- **[Thread safety]** Per-arm threads running simultaneously increases concurrency complexity. → Mitigation: Each arm has its own lock; no shared mutable state between arms except `_cottons` dict (read-only during pick; status updates are per-cotton, no cross-arm writes).
- **[Cotton accumulation]** Not auto-deleting cottons means Gazebo scene accumulates models. → Mitigation: "Remove All" button exists and is accessible. Users are expected to clean up manually.
