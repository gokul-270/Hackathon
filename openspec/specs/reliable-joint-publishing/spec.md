## ADDED Requirements

### Requirement: Retry-based joint publishing

The `_publish_joint_gz` function SHALL attempt to publish each joint command up to 3 times. Each attempt SHALL use `subprocess.Popen` with `Popen.wait(timeout=2)` and check `returncode == 0`. On success, the function SHALL return `True` immediately without further retries. Between failed attempts, the function SHALL wait 200ms.

#### Scenario: First attempt succeeds

- **WHEN** `_publish_joint_gz` is called and the first `gz topic` subprocess exits with returncode 0
- **THEN** the function returns `True`
- **AND** no retry is attempted

#### Scenario: First attempt fails, second succeeds

- **WHEN** the first `gz topic` subprocess exits with returncode != 0
- **AND** the second attempt exits with returncode 0
- **THEN** the function returns `True` after the second attempt
- **AND** a warning is logged for the first failure

#### Scenario: All 3 attempts fail

- **WHEN** all 3 `gz topic` subprocess attempts exit with returncode != 0
- **THEN** the function returns `False`
- **AND** an error is logged with the topic name, value, and all 3 return codes

#### Scenario: Subprocess times out

- **WHEN** a `gz topic` subprocess does not complete within 2 seconds
- **THEN** the process is killed
- **AND** the attempt is counted as a failure
- **AND** the next retry is attempted (if retries remain)

### Requirement: Observable publishing failures

The `_publish_joint_gz` function SHALL log all failures using Python's `logging` module. Successful publishes SHALL be logged at DEBUG level. Failed attempts SHALL be logged at WARNING level. Complete failure (all retries exhausted) SHALL be logged at ERROR level.

#### Scenario: Failure log contains diagnostic info

- **WHEN** a publish attempt fails
- **THEN** the log message includes the topic name, the target value, the attempt number (1/3, 2/3, 3/3), and the subprocess return code or timeout indication

### Requirement: Per-arm joint publishing mutex

A per-arm `threading.Lock` SHALL prevent concurrent `gz topic` commands on the same arm. The lock SHALL be keyed by arm name (e.g., `"arm1"`, `"arm2"`, `"arm3"`). Different arms MAY publish simultaneously.

#### Scenario: Pick animation and slider do not race on same arm

- **WHEN** a pick animation is publishing J3 on arm1
- **AND** another code path attempts to publish J4 on arm1
- **THEN** the second publish waits until the first completes (serialized by the arm1 lock)

#### Scenario: Different arms publish simultaneously

- **WHEN** arm1 is publishing J3 and arm2 is publishing J4
- **THEN** both publish calls proceed without blocking each other
