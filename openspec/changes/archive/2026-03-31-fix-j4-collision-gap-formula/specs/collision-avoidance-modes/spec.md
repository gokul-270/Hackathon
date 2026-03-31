## ADDED Requirements

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
