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
