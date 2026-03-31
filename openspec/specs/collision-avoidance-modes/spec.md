# Spec: Collision Avoidance Modes

## Purpose

Defines the switchable collision avoidance modes available for dual-arm pick operations, including geometry-based blocking, sequential pick, and smart reorder strategies.
## Requirements
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

### Requirement: Mode 1 uses cosine-derived horizontal reach as blocking criterion

Mode 1 (`BASELINE_J5_BLOCK_SKIP`) SHALL block the arm's j5 extension when the peer arm is
active AND the arm's candidate j5 exceeds `0.20 / cos(|j3_own|)`. This replaces the former
lateral j4 gap threshold of 0.05 m. The blocking action (zero j5) and peer-presence guard
(no peer or idle peer → safe) are unchanged.

#### Scenario: Mode 1 blocks j5 via cosine reach limit

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints with j3=0.0 and j5 > 0.20
- **AND** peer arm is active
- **WHEN** the algorithm is applied
- **THEN** j5 is zeroed

#### Scenario: Mode 1 does not use j4 gap as blocking criterion

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.300 j5=0.19
- **AND** arm2 has joints j3=0.0 j4=0.310 j5=0.4
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is not zeroed

### Requirement: Mode 1 Baseline J5 Block Uses Cosine Of Compensated Phi

The Mode 1 j5 limit formula SHALL use the compensated phi angle as the input
to the cosine function.  The compensated phi is the value produced by
`phi_compensation(raw_phi, j5)` from `fk_chain`.  The raw geometric phi from
`polar_decompose()` SHALL NOT be used directly in the cosine formula.

The formula is:
```
theta       = abs(compensated_j3)
cos_theta   = cos(theta)
j5_limit    = 0.20 / cos_theta   if cos_theta > 0.1   else inf
```

#### Scenario: Runtime Mode 1 uses compensated phi

- **GIVEN** `ArmRuntime.compute_candidate_joints()` applies `phi_compensation` to j3
- **WHEN** `BaselineMode.apply_with_skip(mode=1, own_joints, peer_state)` is called
- **THEN** `own_joints["j3"]` is the compensated phi
- **AND** the cosine formula operates on the compensated value

#### Scenario: Diagnostic Mode 1 uses compensated phi

- **GIVEN** `collision_diagnostics._cam_to_joints()` is called with camera coordinates
- **WHEN** those coordinates produce raw phi `r` and extension `e`
- **THEN** `result["j3"]` SHALL equal `phi_compensation(r, e)`
- **AND** the Mode 1 j5_limit calculation in `_diagnose_paired` SHALL use that
  compensated j3

### Requirement: Geometry Stage 1 lateral gap screen
The geometry check Stage 1 SHALL compute lateral gap using `j4_collision_gap(own_j4, peer_j4)` from `collision_math` instead of inline `abs(own_j4 - peer_j4)`.

#### Scenario: Stage 1 gap computed with opposite-facing formula
- **WHEN** geometry Stage 1 evaluates own_j4 and peer_j4
- **THEN** lateral_gap SHALL be `j4_collision_gap(own_j4, peer_j4)` which returns `abs(own_j4 + peer_j4)`

### Requirement: Geometry Stage 2 lateral plus extension check
The geometry check Stage 2 SHALL compute lateral gap using `j4_collision_gap(own_j4, peer_j4)` from `collision_math` instead of inline `abs(own_j4 - peer_j4)`.

#### Scenario: Stage 2 gap computed with opposite-facing formula
- **WHEN** geometry Stage 2 evaluates own_j4 and peer_j4
- **THEN** lateral_gap SHALL be `j4_collision_gap(own_j4, peer_j4)` which returns `abs(own_j4 + peer_j4)`

### Requirement: Overlap zone detection uses opposite-facing formula
The overlap zone state detector SHALL compute lateral gap using `j4_collision_gap(own_j4, peer_j4)` from `collision_math` instead of inline `abs(own_j4 - peer_j4)`.

#### Scenario: Overlap zone gap computed with opposite-facing formula
- **WHEN** overlap zone evaluates own_j4 and peer_j4
- **THEN** gap SHALL be `j4_collision_gap(own_j4, peer_j4)` which returns `abs(own_j4 + peer_j4)`

### Requirement: Collision diagnostics uses opposite-facing formula
The collision diagnostics engine SHALL compute J4 gap using `j4_collision_gap(fk1_j4, fk2_j4)` from `collision_math` instead of inline `abs(fk1_j4 - fk2_j4)`.

#### Scenario: Diagnostics gap computed with opposite-facing formula
- **WHEN** diagnostics evaluates FK-derived J4 values for both arms
- **THEN** j4_gap SHALL be `j4_collision_gap(fk1_j4, fk2_j4)` which returns `abs(fk1_j4 + fk2_j4)`

