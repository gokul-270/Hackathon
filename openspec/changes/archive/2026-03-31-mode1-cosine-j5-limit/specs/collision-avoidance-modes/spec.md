## ADDED Requirements

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
