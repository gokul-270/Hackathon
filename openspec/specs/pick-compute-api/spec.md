## ADDED Requirements

### Requirement: Compute-only single pick endpoint

The `POST /api/cotton/pick` endpoint SHALL compute joint values (j3, j4, j5) for the selected cotton using `camera_to_arm()` + `polar_decompose()` + `phi_compensation()` and return them immediately without launching any background thread or animation. The response SHALL include `status: "ready"`, the computed `j3`, `j4`, `j5` values, the assigned `arm`, the `cotton_name`, and a `reachable` boolean.

#### Scenario: Successful compute for reachable cotton

- **WHEN** `POST /api/cotton/pick` is called with a spawned cotton that maps to a reachable target
- **THEN** the response is `{"status": "ready", "j3": <float>, "j4": <float>, "j5": <float>, "arm": "<armN>", "cotton_name": "<name>", "reachable": true}`
- **AND** no background thread is spawned
- **AND** the cotton's status remains `"spawned"` (not changed to `"picking"`)

#### Scenario: Compute for unreachable cotton

- **WHEN** `POST /api/cotton/pick` is called with a cotton whose coordinates are outside joint limits
- **THEN** the response includes `"reachable": false`
- **AND** the response includes a `"reason"` field explaining which limit is exceeded
- **AND** no animation is started

#### Scenario: No cotton to pick

- **WHEN** `POST /api/cotton/pick` is called with no spawned cottons (all picked or none exist)
- **THEN** the response is `{"status": "error", "message": "No spawned cotton available"}`

### Requirement: Compute-only pick-all endpoint

The `POST /api/cotton/pick-all` endpoint SHALL compute joint values for all cottons with status `"spawned"`, group them by arm, and return the grouped data immediately without spawning threads. The response SHALL include `status: "ready"` and an `arms` object keyed by arm name, where each value is an array of `{name, j3, j4, j5}` objects.

#### Scenario: Multiple cottons across multiple arms

- **WHEN** 3 cottons are spawned — cotton_0 on arm1, cotton_1 on arm1, cotton_2 on arm3
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** the response is:
  ```json
  {
    "status": "ready",
    "arms": {
      "arm1": [
        {"name": "cotton_0", "j3": <float>, "j4": <float>, "j5": <float>},
        {"name": "cotton_1", "j3": <float>, "j4": <float>, "j5": <float>}
      ],
      "arm3": [
        {"name": "cotton_2", "j3": <float>, "j4": <float>, "j5": <float>}
      ]
    }
  }
  ```
- **AND** no background threads are spawned
- **AND** no cotton status is changed

#### Scenario: Nothing to pick

- **WHEN** all cottons have status `"picked"` or no cottons exist
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** the response is `{"status": "nothing_to_pick"}`

#### Scenario: Unreachable cottons excluded with warning

- **WHEN** cotton_0 is reachable and cotton_1 is unreachable
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** cotton_0 appears in the `arms` response
- **AND** cotton_1 is excluded from `arms`
- **AND** the response includes a `"warnings"` array noting which cottons were skipped and why

### Requirement: Mark cotton as picked endpoint

The `POST /api/cotton/{name}/mark-picked` endpoint SHALL set the specified cotton's status from `"spawned"` to `"picked"` and return `{"status": "ok"}`. The endpoint SHALL return 404 if the cotton does not exist, and 409 if the cotton is already picked.

#### Scenario: Successfully mark cotton as picked

- **WHEN** cotton_0 exists with status `"spawned"`
- **AND** `POST /api/cotton/cotton_0/mark-picked` is called
- **THEN** the response is `{"status": "ok"}`
- **AND** `GET /api/cotton/list` shows cotton_0 with status `"picked"`

#### Scenario: Cotton not found

- **WHEN** `POST /api/cotton/nonexistent/mark-picked` is called
- **THEN** the response status code is 404
- **AND** the body is `{"error": "Cotton 'nonexistent' not found"}`

#### Scenario: Cotton already picked

- **WHEN** cotton_0 has status `"picked"`
- **AND** `POST /api/cotton/cotton_0/mark-picked` is called
- **THEN** the response status code is 409
- **AND** the body is `{"error": "Cotton 'cotton_0' already picked"}`

### Requirement: Remove backend animation code

The following backend code SHALL be removed entirely: `_publish_joint_gz()` function, `_execute_pick_sequence()` function, `_execute_pick_all_sequence()` function, `ArmPickState` class, `_arm_pick_state` dictionary, `_arm_joint_locks` dictionary, and all retry/timing constants associated with the gz topic subprocess pathway (`MAX_RETRIES`, `RETRY_DELAY`, `GZ_PUBLISH_TIMEOUT` if they exist solely for pick animation).

#### Scenario: No gz topic subprocess calls

- **WHEN** the backend codebase is inspected
- **THEN** no function calls `subprocess.Popen` with `"gz topic"` arguments
- **AND** no function named `_publish_joint_gz` exists

#### Scenario: No background pick threads

- **WHEN** `POST /api/cotton/pick` or `POST /api/cotton/pick-all` is called
- **THEN** no `threading.Thread` targeting a pick animation function is created or started

#### Scenario: No ArmPickState class

- **WHEN** the backend codebase is inspected
- **THEN** no class named `ArmPickState` exists
- **AND** no dictionary named `_arm_pick_state` exists

### Requirement: Remove pick status endpoint

The `GET /api/cotton/pick/status` endpoint SHALL be removed from the backend. Any request to this URL SHALL return 404 (default FastAPI behavior for undefined routes).

#### Scenario: Status endpoint returns 404

- **WHEN** `GET /api/cotton/pick/status` is called
- **THEN** the response status code is 404

### Requirement: Phi compensation formula matches C++ trajectory planner

The `phi_compensation()` function in `fk_chain.py` SHALL use the same formula as
`trajectory_planner.cpp`: `base = slope × (phi_deg / 90) + offset`. The constants
SHALL match `production.yaml` values:

| Constant | Value | Unit |
|---|---|---|
| `PHI_ZONE1_MAX_DEG` | 50.5 | degrees |
| `PHI_ZONE2_MAX_DEG` | 60.0 | degrees |
| `PHI_ZONE1_SLOPE` | 0.0 | rotations per normalized angle |
| `PHI_ZONE1_OFFSET` | 0.014 | rotations |
| `PHI_ZONE2_SLOPE` | 0.0 | rotations per normalized angle |
| `PHI_ZONE2_OFFSET` | 0.0 | rotations |
| `PHI_ZONE3_SLOPE` | 0.0 | rotations per normalized angle |
| `PHI_ZONE3_OFFSET` | -0.014 | rotations |
| `PHI_L5_SCALE` | 0.5 | dimensionless |
| `JOINT5_MAX` | 0.6 | metres (for L5 normalization) |

#### Scenario: Slope term included in compensation calculation

- **GIVEN** `phi_compensation(j3, j5)` is called with j3=-0.5 rad, j5=0.1 m
- **WHEN** the compensation is computed
- **THEN** the base compensation uses `slope * (phi_deg / 90) + offset`
  where `phi_deg = abs(degrees(j3))`
- **AND** the result matches the C++ `trajectory_planner.cpp` output for the same inputs

#### Scenario: Nonzero slope produces different compensation

- **GIVEN** `PHI_ZONE1_SLOPE` is patched to 0.1 (for testing purposes)
- **AND** j3=-0.3 rad (17.2°, Zone 1), j5=0.0 m
- **WHEN** `phi_compensation(j3, j5)` is called
- **THEN** the base compensation includes the slope contribution:
  `base = 0.1 * (17.2 / 90) + 0.014 = 0.0331 rotations`
- **AND** the returned j3 differs from the offset-only result

#### Scenario: Zone 2 applies zero compensation (unchanged)

- **GIVEN** j3=-0.92 rad (52.7°, Zone 2)
- **WHEN** `phi_compensation(j3, j5)` is called
- **THEN** the returned value equals the input j3 (zone2 offset and slope are both 0.0)

### Requirement: enable_phi_compensation defaults to true

All Pydantic request models (`CottonComputeRequest`, `CottonPickRequest`,
`CottonPickAllRequest`) SHALL set `enable_phi_compensation: bool = True`
(changed from `False`).

#### Scenario: Compute endpoint applies compensation by default

- **WHEN** `POST /api/cotton/compute` is called without specifying `enable_phi_compensation`
- **THEN** phi compensation is applied to the returned j3 value

#### Scenario: Pick endpoint applies compensation by default

- **WHEN** `POST /api/cotton/pick` is called without specifying `enable_phi_compensation`
- **THEN** the returned j3 value has phi compensation applied

#### Scenario: Pick-all endpoint applies compensation by default

- **WHEN** `POST /api/cotton/pick-all` is called without specifying `enable_phi_compensation`
- **THEN** all returned j3 values have phi compensation applied

#### Scenario: Caller can disable compensation explicitly

- **WHEN** `POST /api/cotton/compute` is called with `enable_phi_compensation: false`
- **THEN** the returned j3 equals the raw phi from `polar_decompose()`
