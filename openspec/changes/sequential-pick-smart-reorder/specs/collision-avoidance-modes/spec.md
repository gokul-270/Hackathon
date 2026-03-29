## REMOVED Requirements

### Requirement: Provide Overlap Wait As Improved Strategy

**Reason**: Replaced by Sequential Pick (Mode 3) which dispatches winner then loser instead of skipping.
**Migration**: All references to `overlap_zone_wait` become `sequential_pick`. Mode integer 3 is reused.

### Requirement: Use Alternating-Turn Arbitration With Timeout

**Reason**: The timeout-and-skip mechanism is replaced by two-phase sequential dispatch. Turn alternation is preserved but timeout/skip behavior is removed.
**Migration**: `WaitModePolicy` replaced by `SequentialPickPolicy`. The `skipped` flag is no longer set by Mode 3 (both arms always execute).

## ADDED Requirements

### Requirement: Provide Sequential Pick As Mode 3 Strategy

The system SHALL provide `sequential_pick` as a switchable mode (constant `SEQUENTIAL_PICK = 3`) replacing the former `overlap_zone_wait`.

#### Scenario: Sequential pick available as mode

- **WHEN** the operator selects mode 3
- **THEN** the run executes using the sequential pick strategy
- **AND** the mode name in reports is `sequential_pick`

#### Scenario: Mode constant is SEQUENTIAL_PICK equals 3

- **WHEN** code references `BaselineMode.SEQUENTIAL_PICK`
- **THEN** its integer value is 3

### Requirement: Provide Smart Reorder As Mode 4 Strategy

The system SHALL provide `smart_reorder` as a switchable mode (constant `SMART_REORDER = 4`) for pre-run cotton target reordering.

#### Scenario: Smart reorder available as mode

- **WHEN** the operator selects mode 4
- **THEN** the run executes using the smart reorder strategy
- **AND** the mode name in reports is `smart_reorder`

#### Scenario: Mode constant is SMART_REORDER equals 4

- **WHEN** code references `BaselineMode.SMART_REORDER`
- **THEN** its integer value is 4

### Requirement: Dispatch Sequential Pick Via Apply With Skip

The `apply_with_skip` method SHALL dispatch to sequential pick logic when mode equals `SEQUENTIAL_PICK`. The sequential pick policy SHALL be used for contention detection and turn alternation.

#### Scenario: Apply with skip delegates to sequential pick

- **GIVEN** mode is set to SEQUENTIAL_PICK
- **WHEN** `apply_with_skip` is called
- **THEN** it delegates to the sequential pick policy for contention detection and turn resolution

### Requirement: Dispatch Smart Reorder Via Apply With Skip

The `apply_with_skip` method SHALL pass joints through unchanged when mode equals `SMART_REORDER`, since reordering happens before the step loop, not during per-step mode application.

#### Scenario: Apply with skip passes through for smart reorder

- **GIVEN** mode is set to SMART_REORDER
- **WHEN** `apply_with_skip` is called
- **THEN** joints are returned unchanged with skipped equal to False
