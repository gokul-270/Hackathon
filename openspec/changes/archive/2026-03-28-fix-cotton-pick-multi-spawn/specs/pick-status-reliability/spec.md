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

The backend SHALL reset `_pick_status` to `"idle"` at the start of each `POST /api/cotton/pick` request, before spawning the timer chain.

#### Scenario: Status is idle before new pick starts

- **WHEN** a previous pick has completed (`_pick_status == "done"`) and a new pick is initiated
- **THEN** `_pick_status` is set to `"idle"` before any timers fire
- **AND** a poll during the reset window returns `{"status": "idle"}`, not `"done"`

### Requirement: Thread-safe pick status access

The backend SHALL protect `_pick_in_progress` and `_pick_status` with a `threading.Lock`. Both the status endpoint and the timer callbacks MUST acquire the lock before reading or writing these variables.

#### Scenario: Concurrent status read during timer update

- **WHEN** a timer callback is updating `_pick_status` from `"moving_j4"` to `"moving_j3"`
- **AND** the status endpoint is called simultaneously
- **THEN** the endpoint returns a consistent snapshot (either the old or new state, never a mix)

#### Scenario: Lock does not cause deadlock with timer chain

- **WHEN** a pick animation is in progress with 6 chained timers
- **THEN** each timer acquires and releases the lock without blocking subsequent timers
- **AND** the pick completes within the expected 5.5s window (±0.5s tolerance)
