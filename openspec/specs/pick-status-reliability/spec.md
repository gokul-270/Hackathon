## ADDED Requirements

### Requirement: Single poll interval per pick

The frontend `pollPickStatus()` function SHALL maintain at most one active `setInterval` at any time. A module-level variable SHALL track the current interval ID. Before creating a new interval, any existing interval MUST be cleared.

#### Scenario: Rapid button clicks do not stack intervals

- **WHEN** the user clicks the pick button twice within 500ms
- **THEN** only one `setInterval` poll loop is active
- **AND** the first interval is cleared before the second is created

#### Scenario: Single completion message per pick

- **WHEN** a pick animation completes (backend returns `status: "done"`)
- **THEN** the frontend logs exactly one "Pick sequence complete" message
- **AND** the poll interval is cleared immediately

### Requirement: Backend status reset between picks

The backend SHALL reset the per-arm `ArmPickState.status` to `"idle"` at the start of each `POST /api/cotton/pick` request for the relevant arm, before spawning the pick thread.

#### Scenario: Status is idle before new pick starts

- **WHEN** a previous pick on arm1 has completed (`arm1.status == "done"`) and a new pick on arm1 is initiated
- **THEN** `arm1.status` is set to `"idle"` before the pick thread fires
- **AND** a poll during the reset window returns arm1 status as `"idle"`, not `"done"`

### Requirement: Thread-safe pick status access

The backend SHALL protect each `ArmPickState`'s `in_progress` and `status` with the arm's own `threading.Lock`. Both the status endpoint and the pick thread callbacks MUST acquire the arm's lock before reading or writing that arm's state. Different arms' locks are independent.

#### Scenario: Concurrent status read during pick update

- **WHEN** a pick thread is updating arm1's status from `"j4_lateral"` to `"j3_tilt"`
- **AND** the status endpoint is called simultaneously
- **THEN** the endpoint returns a consistent snapshot for arm1 (either the old or new state, never a mix)

#### Scenario: Lock does not cause deadlock with pick thread

- **WHEN** a pick animation is in progress on arm1 with multiple steps
- **THEN** each step acquires and releases arm1's lock without blocking subsequent steps
- **AND** the pick completes within the expected 5.5s window (+/-0.5s tolerance)

#### Scenario: Arm locks are independent

- **WHEN** arm1's lock is held by a pick thread
- **AND** the status endpoint queries arm2's state
- **THEN** arm2's state is returned immediately without waiting for arm1's lock
