## Context

The cotton placement system in `vehicle_arm_sim/web_ui/` was ported from `yanthra_move` in Phase 1 (12 tasks, commits `a0fba97`–`a760e73`). Real testing revealed three remaining issues:

1. **Pick poll stacking** — `pollPickStatus()` creates a local `setInterval`; no guard prevents multiple intervals from stacking. Backend `_pick_status` is never reset between picks, and globals are accessed without a lock.
2. **Transform bug** (FIXED in commit `1a10ee8`) — `camera_to_arm()` used `np.linalg.inv()` instead of the forward transform. Now validated against 5-point real arm log data.
3. **Single-cotton limit** — singleton globals (`_cotton_spawned`, `_cotton_name`, `_last_cotton_cam`) allow only one cotton at a time.

Backend uses FastAPI HTTP endpoints (not ROS2 topics) for all cotton operations. Frontend communicates via `fetch()` calls.

## Goals / Non-Goals

**Goals:**
- Fix pick status reliability so exactly one "pick complete" event fires per pick
- Reject unreachable targets with a clear error message at the API level
- Support spawning N cottons, each persisting in Gazebo with its own marker
- Sequential pick: arm picks cottons one-by-one in spawn order, returns home after last
- "Remove All" button to clear all cottons from Gazebo
- Maintain TDD discipline — every change has tests first

**Non-Goals:**
- Parallel multi-arm picking (only one arm at a time)
- Camera auto-detection of cotton positions (coordinates are manually entered)
- Gazebo physics-based cotton removal (we delete/spawn models via Gazebo service)
- Changing the pick animation timing (stays at 5.5s total)
- Supporting arm2/arm3 for cotton operations (arm1 only, matching yanthra_move)

## Decisions

### D1: Threading lock for pick status

**Decision:** Add a single `threading.Lock` around `_pick_in_progress` and `_pick_status` reads/writes.

**Rationale:** The pick animation runs in a background `threading.Timer` chain. The `/api/cotton/pick-status` endpoint reads both variables from the main thread. Without a lock, the endpoint can read `_pick_in_progress=False` but `_pick_status` hasn't been updated yet, causing inconsistent state. A single lock is simpler than `asyncio` coordination and matches the existing `threading.Timer` pattern.

**Alternative considered:** Use `asyncio.Queue` — rejected because the backend already uses synchronous threading for pick animation timers.

### D2: Module-level poll guard (frontend)

**Decision:** Replace the local `setInterval` variable in `pollPickStatus()` with a module-level `_pickPollInterval` variable. Before starting a new interval, check and clear any existing one.

**Rationale:** The root cause of 6-12x "complete" messages is multiple stacking intervals. A module-level variable ensures only one poll loop exists at any time. Combined with backend status reset (D3), this eliminates duplicate completions.

### D3: Backend status reset before each pick

**Decision:** Set `_pick_status = "idle"` at the start of `POST /api/cotton/pick` before spawning the timer chain.

**Rationale:** After a pick completes, `_pick_status` stays `"done"` indefinitely. If the frontend polls before the next pick's first timer fires, it sees "done" from the previous pick. Resetting to "idle" at pick start ensures clean state.

### D4: CottonState dataclass for collection

**Decision:** Replace singleton globals with:
```python
@dataclass
class CottonState:
    name: str           # Gazebo model name (e.g. "cotton_0")
    cam_coords: tuple   # (cam_x, cam_y, cam_z)
    arm_coords: tuple   # (ax, ay, az) from camera_to_arm
    joint_values: dict   # {j3, j4, j5} from polar_decompose
    status: str         # "spawned" | "picking" | "picked"

_cottons: dict[str, CottonState] = {}  # keyed by cotton name, insertion-ordered (Python 3.7+)
_cotton_counter: int = 0               # monotonic counter for unique names
```

**Rationale:** A dict preserves spawn order (Python 3.7+ guarantees insertion order) which is needed for sequential pick. Each cotton stores its own coordinates and joint values computed at spawn time, so they don't need to be recomputed at pick time. The `status` field tracks pick progress per cotton.

**Alternative considered:** List of tuples — rejected because lookup by name (for remove/status) requires linear scan. Dict gives O(1) lookup.

### D5: Sequential pick via recursive timer chain

**Decision:** `POST /api/cotton/pick-all` iterates `_cottons` in insertion order. For each cotton with status `"spawned"`, it runs the existing 5.5s pick animation, then advances to the next. After the last cotton, the arm returns home.

**Rationale:** Reuses the existing `_schedule_pick_step()` timer chain. Each cotton's pick completes before the next starts. The frontend polls `/api/cotton/pick-status` which now returns `{"status": "picking", "current": "cotton_2", "progress": "3/5"}` during the sequence.

**Alternative considered:** Single `POST /api/cotton/pick` with cotton name parameter — rejected because the user wants "pick all in order" as one action, not manual per-cotton picking.

### D6: Error response for unreachable targets

**Decision:** `/api/cotton/spawn` computes `polar_decompose()` at spawn time. If `reachable=False`, return HTTP 400 with `{"error": "Target unreachable", "reason": "<specific reason>"}`. The cotton is NOT spawned in Gazebo.

**Rationale:** Catching unreachability at spawn time (rather than pick time) prevents spawning cottons that can never be picked. The specific reason (e.g., "J3 out of range: target above arm" or "J5 out of range: target too close") helps the user adjust coordinates.

**Alternative considered:** Allow spawn but block pick — rejected because it creates confusing UX where a visible cotton can never be picked.

### D7: Clear stale state on remove

**Decision:** `POST /api/cotton/remove` and `POST /api/cotton/remove-all` delete the cotton(s) from `_cottons` dict AND from Gazebo. No stale references remain.

**Rationale:** With D4's collection design, removing from the dict is sufficient — there's no separate `_last_cotton_cam` to forget about. The latent bug (stale `_last_cotton_cam` after remove) is eliminated by design.

## Risks / Trade-offs

**[Risk] Sequential pick takes N × 5.5s for N cottons** → Acceptable for testing workflow. No user expectation of fast batch picking. The sequential animation is the point — it validates arm motion for each target.

**[Risk] No cancellation mid-sequence** → If user wants to abort a multi-pick, they must wait for the current cotton's animation to finish. Mitigation: add cancellation in a future change if needed; current scope keeps it simple.

**[Risk] Thread safety with collection mutations** → The `_cottons` dict is modified by spawn/remove (main thread) and read by pick animation (background thread). Mitigation: extend the existing `threading.Lock` (D1) to also protect `_cottons` access.

**[Risk] Gazebo model name collisions** → Using a monotonic counter (`cotton_0`, `cotton_1`, ...) prevents collisions even across remove/re-spawn cycles. Counter never resets during a session.
