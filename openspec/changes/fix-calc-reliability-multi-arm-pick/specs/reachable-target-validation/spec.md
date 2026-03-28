## MODIFIED Requirements

### Requirement: Reject unreachable targets at spawn time

The `POST /api/cotton/spawn` endpoint SHALL compute `polar_decompose()` on the camera coordinates at spawn time. If `reachable` is `False`, the endpoint MUST return HTTP 400 with a JSON body containing `"error"` and `"reason"` fields. The cotton MUST NOT be spawned in Gazebo.

The JS frontend `camToJoint` function SHALL apply the same reachability check as the Python backend: if `r < 1e-6` or `r > 0.1` (too close for meaningful arm motion), the function SHALL return `null` and display an error message. The JS camera-to-arm transform SHALL use the forward URDF transform (matching `fk_chain.py:camera_to_arm()`), not the inverse.

#### Scenario: Target above arm (J3 out of range)

- **WHEN** the user submits camera coordinates that produce `phi > 0` (positive, meaning above the arm plane)
- **THEN** the endpoint returns `400 {"error": "Target unreachable", "reason": "J3 out of range: target above arm (phi=+X.X deg)"}`
- **AND** no Gazebo model is created

#### Scenario: Target too close (J5 out of range)

- **WHEN** the user submits camera coordinates where radial distance `r < HARDWARE_OFFSET` (0.320m)
- **THEN** the endpoint returns `400 {"error": "Target unreachable", "reason": "J5 out of range: target too close (r=X.XXXm < 0.320m)"}`
- **AND** no Gazebo model is created

#### Scenario: Target beyond arm reach (J5 exceeds max)

- **WHEN** the user submits camera coordinates where `r - HARDWARE_OFFSET > 0.450`
- **THEN** the endpoint returns `400 {"error": "Target unreachable", "reason": "J5 out of range: target too far (j5=X.XXXm > 0.450m)"}`
- **AND** no Gazebo model is created

#### Scenario: Reachable target spawns normally

- **WHEN** the user submits camera coordinates that produce `reachable=True`
- **THEN** the endpoint returns `200` with the cotton name and computed joint values
- **AND** the cotton model is spawned in Gazebo

#### Scenario: JS camToJoint uses forward transform

- **WHEN** the JS `initCameraToArmTransform()` function initializes the transform matrix
- **THEN** it uses the forward URDF transform `arm_xyz = R @ cam_xyz + t` (not the inverse `R^T @ cam_xyz + (-R^T @ t)`)
- **AND** the resulting arm-frame coordinates match `fk_chain.py:camera_to_arm()` for the same input

#### Scenario: JS camToJoint rejects unreachable coordinates

- **WHEN** JS `camToJoint` is called with camera coordinates that produce `r < 1e-6`
- **THEN** the function returns `null`
- **AND** the UI displays an error message indicating the target is unreachable

#### Scenario: JS r threshold matches Python

- **WHEN** JS `camToJoint` computes polar decomposition
- **THEN** it uses `r < 1e-6` as the degenerate-radius threshold (matching Python, not `1e-9`)

### Requirement: Frontend displays unreachable error

The frontend SHALL display the error reason from a failed spawn as a visible status message in the Cotton Placement panel.

#### Scenario: Error toast on unreachable spawn

- **WHEN** the `/api/cotton/spawn` endpoint returns HTTP 400
- **THEN** the frontend displays the `reason` text in the status area with error styling (red)
- **AND** the input fields remain populated so the user can adjust coordinates

### Requirement: Clear stale cotton references on remove

The `POST /api/cotton/remove` endpoint SHALL delete the cotton from the internal collection AND from Gazebo. No stale reference to removed cotton coordinates SHALL remain in any backend variable.

#### Scenario: Pick after remove is rejected

- **WHEN** a cotton is spawned, then removed via `POST /api/cotton/remove`, then a pick is attempted
- **THEN** the pick endpoint returns an error indicating no cottons are available to pick
- **AND** no arm motion occurs
