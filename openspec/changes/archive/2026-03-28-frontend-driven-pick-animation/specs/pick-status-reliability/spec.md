## REMOVED Requirements

### Requirement: Single poll interval per pick
**Reason**: Frontend now drives the pick animation directly via async/await. There is no backend status to poll — the frontend knows its own animation state at each step. The `pollPickStatus()` function and `_pickPollInterval` variable are removed entirely.
**Migration**: Frontend `cottonPick()` calls `executePickAnimation()` directly after receiving compute-only response from `POST /api/cotton/pick`. Status display is updated inline at each animation step.

### Requirement: Backend status reset between picks
**Reason**: The `ArmPickState` class and `_arm_pick_state` dictionary are removed. The backend no longer tracks per-arm animation status because it no longer runs animations. The `/api/cotton/pick` endpoint is compute-only — it returns joint values and exits immediately.
**Migration**: No migration needed. Frontend animation state is managed by module-level `pickRunning`/`pickAborted` booleans that reset naturally between picks.

### Requirement: Thread-safe pick status access
**Reason**: No background pick threads exist. The backend no longer spawns `threading.Thread` for pick animations, so there is no concurrent state to protect. The `_arm_joint_locks` dictionary and per-arm `threading.Lock` instances are removed.
**Migration**: The `POST /api/cotton/{name}/mark-picked` endpoint is a simple synchronous status update — no locking needed as FastAPI handles request serialization within a single event loop.
