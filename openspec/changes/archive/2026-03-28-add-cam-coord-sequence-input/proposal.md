## Why

The existing Custom Joint Sequence player requires testers to manually compute J3/J4/J5 joint values from camera-frame coordinates, which is error-prone and slows iteration. A dedicated Cotton Position Sequence Player that accepts camera-frame coordinates (cam_x, cam_y, cam_z), auto-converts them to joint values using the sim-correct polar math and TF transform, and visualises each target as a static Gazebo marker will let testers describe pick positions in the natural coordinate frame and verify them visually before execution.

## What Changes

- Add a new **Cotton Position Sequence** panel to `testing_ui.html` (separate from the existing Custom Joint Sequence table)
- Add TF static-transform subscriber in `testing_ui.js` (`/tf_static` via roslib) to obtain the `camera_link → yanthra_link` 4×4 matrix
- Add cam → joint conversion math in `testing_ui.js`: polar decomposition (J3 in radians, J4 direct, J5 = r − 0.320 m)
- Add `POST /api/cam_markers/place` endpoint to `testing_backend.py` that accepts world-frame XYZ and spawns a static SDF sphere marker in Gazebo via `gz service /world/empty/create`
- Add `POST /api/cam_markers/clear` endpoint to `testing_backend.py` that removes all spawned markers
- Add FK chain computation in `testing_backend.py` to convert cam coords → world frame for marker placement
- Add styles for the new panel in `testing_ui.css`

## Capabilities

### New Capabilities

- `cam-coord-sequence-player`: UI panel that accepts a sequence of camera-frame (cam_x, cam_y, cam_z) positions, converts them to J3/J4/J5 joint commands using sim-correct math, spawns static visual markers in Gazebo at each world-frame target, and executes the sequence step-by-step through the existing joint command topics.

### Modified Capabilities

<!-- No existing specs change requirements -->

## Impact

- **`pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.html`** — new section markup
- **`pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.css`** — new section styles
- **`pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.js`** — TF subscriber, cam→joint math, sequence runner, marker API calls
- **`pragati_ros2/src/vehicle_arm_sim/web_ui/testing_backend.py`** — two new HTTP endpoints + FK world-frame math
- No changes to ROS2 node launch files, URDF, or joint controller configuration
- No changes to the existing Custom Joint Sequence panel or its backend endpoints
- Depends on: roslib (already loaded), `gz service` CLI (already used in `testing_backend.py`), `/tf_static` topic (published by the sim stack)
