## ADDED Requirements

### Requirement: Per-arm pick state

The backend SHALL maintain a per-arm `ArmPickState` dataclass with fields: `lock` (threading.Lock), `in_progress` (bool), `status` (str), `current` (Optional[str]), `progress` (tuple[int, int]). A dict `_arm_pick_state` keyed by arm name SHALL replace the global `_pick_lock`, `_pick_in_progress`, `_pick_status`, `_pick_current`, and `_pick_progress` variables.

#### Scenario: Two arms pick simultaneously

- **WHEN** `POST /api/cotton/pick` is called for a cotton on arm1
- **AND** `POST /api/cotton/pick` is called for a cotton on arm2 while arm1 is still picking
- **THEN** both pick sequences run concurrently in separate threads
- **AND** `arm1.in_progress` and `arm2.in_progress` are both `True`

#### Scenario: Same arm rejects concurrent pick

- **WHEN** a pick sequence is in progress on arm1
- **AND** `POST /api/cotton/pick` is called for another cotton on arm1
- **THEN** the endpoint returns HTTP 409 with `{"error": "Arm arm1 is already picking"}`

#### Scenario: Idle arm accepts pick during other arm's pick

- **WHEN** arm1 is picking and arm3 is idle
- **AND** `POST /api/cotton/pick` is called for a cotton on arm3
- **THEN** the pick starts immediately on arm3

### Requirement: Pick-all groups by arm

The `POST /api/cotton/pick-all` endpoint SHALL group all cottons with status `"spawned"` by their `arm` field. For each arm group, it SHALL spawn a separate `threading.Thread` that picks that arm's cottons sequentially. All arm threads run in parallel.

#### Scenario: 4 cottons across 2 arms

- **WHEN** cotton_0 and cotton_1 are on arm1, cotton_2 and cotton_3 are on arm2
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** arm1 picks cotton_0 then cotton_1 (sequentially)
- **AND** arm2 picks cotton_2 then cotton_3 (sequentially)
- **AND** arm1 and arm2 operate in parallel

#### Scenario: All cottons on same arm

- **WHEN** all 3 cottons are on arm1
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** all 3 are picked sequentially on arm1 (no parallelism)

#### Scenario: Pick-all with no spawned cottons

- **WHEN** all cottons have status `"picked"` or no cottons exist
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** the endpoint returns `{"status": "nothing_to_pick"}`

### Requirement: Per-arm status endpoint

The `GET /api/cotton/pick/status` endpoint SHALL return per-arm state in the format `{"arms": {"arm1": {"status": str, "current": str|null, "progress": [int, int]}, ...}}`. Each arm's state SHALL reflect that arm's independent pick progress.

#### Scenario: One arm picking, others idle

- **WHEN** arm1 is on its second cotton of three and arm2/arm3 are idle
- **THEN** the endpoint returns `{"arms": {"arm1": {"status": "j3_tilt", "current": "cotton_1", "progress": [2, 3]}, "arm2": {"status": "idle", "current": null, "progress": [0, 0]}, "arm3": {"status": "idle", "current": null, "progress": [0, 0]}}}`

#### Scenario: Two arms picking simultaneously

- **WHEN** arm1 is picking cotton_0 and arm2 is picking cotton_2
- **THEN** the endpoint returns both arms with their respective status, current cotton, and progress

#### Scenario: All arms idle

- **WHEN** no pick is in progress
- **THEN** all arms report `{"status": "idle", "current": null, "progress": [0, 0]}`
