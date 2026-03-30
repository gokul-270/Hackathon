## ADDED Requirements

### Requirement: Mode 1 blocks j5 when horizontal reach exceeds cosine limit

Mode 1 (`BASELINE_J5_BLOCK_SKIP`) SHALL compute a dynamic J5 limit from the arm's tilt
angle using `J5_limit = 0.20 / cos(|j3_own|)` and zero j5 when the candidate j5 exceeds
that limit and a peer arm is active. The constant 0.20 m is the fixed safe horizontal reach
boundary (`adj`). j3 and j4 are never modified.

#### Scenario: j5 blocked when arm is vertical and extension exceeds 0.20m

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.100 j5=0.25
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is zeroed
- **AND** j3 is unchanged
- **AND** j4 is unchanged

#### Scenario: j5 safe when arm is vertical and extension is within 0.20m

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.100 j5=0.19
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is not zeroed

#### Scenario: j5 blocked when tilt raises limit but extension still exceeds it

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=-0.5236 j4=0.100 j5=0.24
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is zeroed

#### Scenario: j5 safe when tilt raises limit above extension

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=-0.5236 j4=0.100 j5=0.22
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is not zeroed

#### Scenario: j5 safe at boundary when extension equals limit exactly

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.100 j5=0.20
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is not zeroed

#### Scenario: j5 safe when no peer is active

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.100 j5=0.45
- **AND** no peer arm is active
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is not zeroed

#### Scenario: j5 safe when peer is present but idle

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.100 j5=0.45
- **AND** peer arm is present but idle
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is not zeroed

#### Scenario: j5 safe at near-vertical tilt where cos approaches zero

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=-0.89 j4=0.100 j5=0.30
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is not zeroed

#### Scenario: large j5 is zeroed when horizontal reach exceeds limit

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.100 j5=0.45
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is zeroed

#### Scenario: j5 already zero remains zero

- **GIVEN** mode is 1 (baseline_j5_block_skip)
- **AND** arm1 has joints j3=0.0 j4=0.100 j5=0.0
- **AND** arm2 is active with any joints
- **WHEN** the algorithm is applied for arm1
- **THEN** j5 is zeroed
