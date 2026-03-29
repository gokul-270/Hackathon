### Requirement: Provide Geometry Block As Improved Strategy

The system SHALL provide `geometry_block` as a switchable mode on top of the working replay
platform.

#### Scenario: Geometry block available as mode
- **WHEN** the operator selects `geometry_block`
- **THEN** the run executes using the geometry-aware blocking strategy

### Requirement: Use Two-Stage Geometry Evaluation

The geometry mode SHALL use a quick screen first and a better geometry check second.

#### Scenario: Unsafe geometry blocks motion
- **WHEN** the second-stage geometry check determines the candidate motion is unsafe
- **THEN** the pick is blocked immediately

### Requirement: Provide Overlap Wait As Improved Strategy

The system SHALL provide `overlap_zone_wait` as a switchable strategy on top of the working replay
platform.

#### Scenario: Overlap wait available as mode
- **WHEN** the operator selects `overlap_zone_wait`
- **THEN** the run executes using overlap-aware waiting behavior

### Requirement: Use Alternating-Turn Arbitration With Timeout

The overlap wait mode SHALL resolve overlap contention by alternating turns and SHALL skip a pick if
the configured wait timeout expires.

#### Scenario: Timed-out wait causes skip
- **WHEN** overlap contention persists beyond the configured timeout
- **THEN** that pick is marked skipped and the run continues
