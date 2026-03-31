## ADDED Requirements

### Requirement: Contention detection uses opposite-facing J4 formula
The sequential pick policy SHALL compute J4 gap for contention detection using `j4_collision_gap(own_j4, peer_j4)` from `collision_math` instead of inline `abs(own_j4 - peer_j4)`.

#### Scenario: Contention gap computed with opposite-facing formula
- **WHEN** sequential pick policy evaluates own and peer J4 for contention
- **THEN** gap SHALL be `j4_collision_gap(own_j4, peer_j4)` which returns `abs(own_j4 + peer_j4)`

#### Scenario: No contention when arms are far apart
- **WHEN** own_j4=0.0 and peer_j4=-0.20 (arms far apart in world frame)
- **THEN** gap SHALL be abs(0.0 + (-0.20)) = 0.20 which exceeds the contention threshold
