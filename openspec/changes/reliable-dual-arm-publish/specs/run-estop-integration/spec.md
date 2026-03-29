## ADDED Requirements

### Requirement: Server-side E-STOP flag

The system SHALL maintain a module-level `threading.Event` (`_estop_event`) in `testing_backend.py`. The `/api/estop` endpoint SHALL call `_estop_event.set()` in addition to its existing zero-publish behaviour. Each call to `/api/run/start` SHALL call `_estop_event.clear()` before starting the run.

#### Scenario: E-STOP flag is clear at run start

- **WHEN** `/api/run/start` is called
- **THEN** `_estop_event` is cleared before `controller.run()` is invoked
- **AND** any prior E-STOP state does not affect the new run

#### Scenario: E-STOP flag is set when endpoint is called during a run

- **WHEN** `/api/estop` is posted while a run is in progress
- **THEN** `_estop_event.is_set()` returns `True` in the worker thread
- **AND** the endpoint response is not blocked by the running scenario

### Requirement: Interruptible animation phases

`RunStepExecutor.execute()` SHALL check the `estop_check` callable (injected at construction time, defaults to `lambda: False`) after each `sleep_fn` call. If `estop_check()` returns `True`, the executor SHALL immediately publish zero to all three joints for the arm, stop the animation sequence, and return an `estop_aborted` outcome.

#### Scenario: E-STOP fires between animation phases

- **WHEN** `_estop_event` is set while the executor is sleeping between j4 and j3 publish
- **THEN** the executor detects the flag after the sleep completes
- **AND** publishes zeros to j3, j4, j5 for the affected arm
- **AND** returns `{"terminal_status": "estop_aborted", "pick_completed": False, "executed_in_gazebo": False}`

#### Scenario: E-STOP check is injected as a callable

- **WHEN** `RunStepExecutor` is constructed with `estop_check=lambda: flag.is_set()`
- **THEN** the executor calls that callable after each sleep
- **AND** constructing without `estop_check` defaults to never aborting

#### Scenario: E-STOP zero-publish covers all three joints

- **WHEN** E-STOP fires mid-animation on arm2
- **THEN** the executor publishes 0.0 to `/joint3_copy_cmd`, `/joint4_copy_cmd`, `/joint5_copy_cmd`
- **AND** does not publish further motion commands

### Requirement: E-STOP aborted terminal status

The system SHALL recognise `"estop_aborted"` as a valid terminal outcome alongside `"completed"`, `"blocked"`, and `"skipped"`. Steps with `estop_aborted` status SHALL have `pick_completed = False` and `executed_in_gazebo = False`. The run report SHALL include these steps in `step_reports`.

#### Scenario: estop_aborted appears in run report

- **WHEN** a run is aborted mid-step by E-STOP
- **THEN** the `/api/run/start` response includes at least one step with `terminal_status = "estop_aborted"`
- **AND** `pick_completed` is `False` for those steps

#### Scenario: Completed steps before E-STOP are preserved

- **WHEN** E-STOP fires at step 3 of a 5-step run
- **THEN** steps 1 and 2 retain their original terminal statuses (`completed`, `blocked`, etc.)
- **AND** step 3 and any partially-started steps show `estop_aborted`

### Requirement: Async run execution

The `/api/run/start` handler SHALL execute `controller.run()` via `asyncio.to_thread()` so that the FastAPI event loop remains free to handle `/api/estop` and `/api/run/status` requests during a run.

#### Scenario: E-STOP request is accepted during a run

- **WHEN** a scenario run is in progress
- **THEN** a concurrent POST to `/api/estop` receives an HTTP response within 1 second
- **AND** the E-STOP flag is set so the worker thread detects it at the next phase check

#### Scenario: Status request is accepted during a run

- **WHEN** a scenario run is in progress
- **THEN** a GET to `/api/run/status` returns `{"status": "running"}` without waiting for the run to finish
