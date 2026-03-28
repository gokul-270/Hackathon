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
