## ADDED Requirements

### Requirement: Cam-coord entry table
The testing UI SHALL provide a Cotton Position Sequence panel containing a table where testers can add rows, each row holding three numeric inputs: `cam_x`, `cam_y`, `cam_z` (in metres, camera frame). The panel SHALL be visually distinct from the existing Custom Joint Sequence panel.

#### Scenario: Add a row
- **WHEN** the tester clicks "Add Position"
- **THEN** a new row is appended to the table with empty `cam_x`, `cam_y`, `cam_z` input fields and a "Remove" button

#### Scenario: Remove a row
- **WHEN** the tester clicks "Remove" on a row
- **THEN** that row is deleted from the table

### Requirement: TF static transform subscription
The UI SHALL subscribe to `/tf_static` via roslib on page load and extract the 4×4 homogeneous transform matrix from `camera_link` to `arm_yanthra_link`. The matrix SHALL be updated whenever `/tf_static` publishes new data.

#### Scenario: TF transform available
- **WHEN** `/tf_static` publishes a transform from `camera_link` to `arm_yanthra_link`
- **THEN** the UI stores the 4×4 matrix and marks TF as ready

#### Scenario: TF transform not yet available
- **WHEN** the tester attempts to place markers or run the sequence before TF data has arrived
- **THEN** the UI displays an error message "TF not ready" and does not proceed

### Requirement: Cam-to-joint conversion
The UI SHALL convert each (cam_x, cam_y, cam_z) entry to (J3, J4, J5) joint values using the following simulation-correct math:
1. Apply the `camera_link → arm_yanthra_link` TF matrix to obtain arm-frame coordinates (ax, ay, az).
2. `r = sqrt(ax² + az²)`
3. `J3 = asin(az / r)` (radians — Gazebo revolute joint)
4. `J4 = ay` (metres, direct passthrough)
5. `J5 = r − 0.320` (metres; 0.320 m is the simulation pick-path offset)

#### Scenario: Valid coordinate conversion
- **WHEN** a valid (cam_x, cam_y, cam_z) is supplied with TF ready
- **THEN** the computed J3 is in radians within [−0.9, 0.0], J4 within [−0.250, 0.350] m, and J5 within [0.0, 0.450] m

#### Scenario: Out-of-range result
- **WHEN** the computed J3, J4, or J5 is outside its respective joint limit
- **THEN** the UI highlights the offending row in red and prevents that position from being executed

### Requirement: Static Gazebo marker placement
The UI SHALL send `POST /api/cam_markers/place` for each position in the sequence (after conversion). The backend SHALL compute the world-frame XYZ via FK and spawn a static SDF sphere marker in the Gazebo world using `gz service /world/empty/create`.

#### Scenario: Marker placed for valid position
- **WHEN** `POST /api/cam_markers/place` is called with (cam_x, cam_y, cam_z)
- **THEN** the backend computes world-frame (wx, wy, wz) via FK, spawns a uniquely named sphere SDF at that location in Gazebo, and returns HTTP 200 with the marker name

#### Scenario: Markers persist when arm moves
- **WHEN** the arm joints move after markers are placed
- **THEN** the markers remain at their original world-frame positions (they are static Gazebo models, not attached to any link)

### Requirement: Clear markers
The UI SHALL provide a "Clear Markers" button that sends `POST /api/cam_markers/clear`. The backend SHALL delete all previously spawned marker models from the Gazebo world.

#### Scenario: Clear all markers
- **WHEN** `POST /api/cam_markers/clear` is called
- **THEN** all marker models spawned by previous `/api/cam_markers/place` calls are deleted from the Gazebo world and the backend returns HTTP 200

#### Scenario: Clear with no markers present
- **WHEN** `POST /api/cam_markers/clear` is called when no markers have been spawned
- **THEN** the backend returns HTTP 200 without error

### Requirement: Sequence execution
The UI SHALL execute the sequence by iterating through each row in order: computing joint values, sending them to the joint command topics, waiting for the configured dwell time, then moving to the next position. The sequence SHALL stop immediately if any position is out-of-range or if a stop is requested.

#### Scenario: Successful sequence run
- **WHEN** the tester clicks "Run Sequence" with all rows valid and TF ready
- **THEN** the arm moves to each position in order, the active row is highlighted, and the UI shows "Done" after the last position

#### Scenario: Stop mid-sequence
- **WHEN** the tester clicks "Stop" during sequence execution
- **THEN** the current joint command is not sent (or the loop is aborted after the current move) and the UI returns to idle state

#### Scenario: Empty sequence
- **WHEN** the tester clicks "Run Sequence" with no rows in the table
- **THEN** the UI shows a warning "No positions in sequence" and does not send any commands

### Requirement: Compute Candidate Joints In Arm Nodes

The camera-coordinate sequence flow SHALL compute candidate joints inside each arm node at runtime
from camera/cotton points.

#### Scenario: Arm node computes runtime candidate joints
- **WHEN** an arm receives its active target point
- **THEN** it computes its own candidate `j4`, `j3`, and `j5` values
