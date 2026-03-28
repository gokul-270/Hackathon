## Context

The testing UI (`testing_ui.html` / `testing_ui.js` / `testing_backend.py`) runs on port 8081 and is used to exercise the arm simulation in Gazebo. It already has a Custom Joint Sequence player that sends raw J3/J4/J5 values. Testers need to enter pick positions in the natural camera frame, not in raw joint space. The arm-sim bridge (`arm_sim_bridge.py`, port 8889) already has the cam→joint conversion and Gazebo marker logic, but that server is a ROS2 node and mixing two backends in one test session is fragile. The correct approach is to replicate the conversion math in the testing UI stack.

Key constraints (locked from codebase exploration):
- TF frame: `camera_link → arm_yanthra_link`
- J3 unit: **radians** (Gazebo revolute joint, no ÷2π)
- J5 offset: **0.320 m** (matches `arm_sim_bridge.py` pick path and C++ default)
- Phi compensation: **disabled** (simulation.yaml)
- Joint limits — J3: [−0.9, 0.0] rad, J4: [−0.250, 0.350] m, J5: [0.0, 0.450] m
- Marker spawning: `gz service /world/empty/create` (already used in `testing_backend.py`)

## Goals / Non-Goals

**Goals:**
- Add a self-contained Cotton Position Sequence panel to the existing testing UI
- Convert cam-frame coordinates to joint values entirely in JavaScript (no new ROS2 node needed)
- Spawn/clear static Gazebo sphere markers from the FastAPI backend
- Execute sequences through the existing joint command topics (`/joint3_cmd`, etc.)
- All new code covered by tests before implementation (red-green-refactor)

**Non-Goals:**
- Live TF lookup (we use `/tf_static` which is stable for a given launch)
- Support for hardware (production) mode — this panel is simulation-only
- Modifying the existing Custom Joint Sequence panel
- Re-implementing `arm_sim_bridge.py`; the testing UI has its own simpler backend

## Decisions

### 1. Cam→joint math lives in JavaScript, not the backend

**Decision**: The polar-decomposition math (TF apply + r/J3/J4/J5) runs in `testing_ui.js` via a roslib `/tf_static` subscription.

**Rationale**: The backend already has no TF knowledge; adding TF2 Python bindings to a FastAPI process that is not a ROS2 node would require `rclpy.init()` and a spin loop, adding significant complexity. JavaScript with a roslib subscriber is the same pattern used by `arm_sim_bridge`'s companion web UI and keeps the math co-located with the validation UX.

**Alternatives considered**:
- Backend-side TF lookup via rclpy — rejected (requires rclpy in FastAPI process, non-trivial)
- Static config file for the TF matrix — rejected (fragile if URDF changes)

### 2. World-frame FK for markers computed in the backend

**Decision**: `POST /api/cam_markers/place` receives cam-frame (cam_x, cam_y, cam_z) and the backend computes world-frame XYZ using a hard-coded FK chain derived from the URDF (fixed joint offsets only; no live joint state needed for world-Z of the base, which is constant in sim).

**Rationale**: The marker spawn call needs a world-frame pose. The base of the arm is at a fixed world position in the Gazebo sim (link offsets from the URDF). Because the sim world is static (vehicle doesn't move), the FK from camera → world can be pre-computed from URDF constants rather than a live joint-state query, keeping the backend stateless.

**Alternatives considered**:
- Pass world-frame from the JS side — rejected (JS already computes arm-frame coords; asking it to also do full world FK duplicates backend knowledge)
- Live joint-state query in backend — rejected (overkill; arm base is at fixed world origin in sim)

### 3. Marker naming convention enables selective clear

**Decision**: Each spawned marker is named `cam_marker_<uuid4_short>`. The backend keeps an in-memory list of spawned marker names for the lifetime of the server process. `POST /api/cam_markers/clear` iterates the list, calls `gz service /world/empty/remove` for each, then clears the list.

**Rationale**: Gazebo's `gz service` API requires model names for deletion. Using a process-level list is the simplest approach given the testing-only context (server restarts reset state, which is acceptable).

**Alternatives considered**:
- Prefix-based discovery via `gz model --list` — rejected (adds a subprocess round-trip per clear; prefix parsing is fragile)

### 4. Sequence runner is entirely client-side (JS)

**Decision**: The JS loop sends joint commands sequentially using `fetch` to the existing `/api/joint_command` endpoint with an `await sleep(dwellMs)` between steps.

**Rationale**: Keeps sequence state in the browser where it can be cancelled by the user without a backend abort mechanism. Matches the pattern of the existing Custom Joint Sequence runner.

### 5. No new ROS2 package or node

**Decision**: All code additions are to the three existing files (`testing_ui.html`, `testing_ui.js`, `testing_backend.py`) and their CSS.

**Rationale**: Minimises review surface and keeps the change self-contained. The testing stack is not production code.

## Risks / Trade-offs

- **TF not published at page load time** → Mitigation: UI shows a clear "TF not ready" banner; "Run Sequence" and "Place Markers" buttons are disabled until TF data arrives.
- **FK constants in backend drift from URDF** → Mitigation: constants are extracted from `vehicle_arm_merged.urdf` and committed alongside a comment pointing at the URDF; a test asserts expected values.
- **Marker list lost on backend restart** → Acceptable trade-off for testing context; document in UI ("Markers may persist in Gazebo after backend restart — use Gazebo GUI to remove manually").
- **`gz service` CLI not on PATH** → Mitigation: existing `testing_backend.py` already calls `gz service`; if it works for existing endpoints it will work here.

## Migration Plan

No migration required. This is a purely additive change to files that are not versioned or deployed to production hardware. Testers update by pulling the branch and relaunching `launch_testing_ui.sh`.

## Open Questions

- None — all design decisions resolved during codebase exploration.
