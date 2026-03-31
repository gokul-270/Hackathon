## MODIFIED Requirements

### Requirement: Truth monitor computes collision distance
The truth monitor SHALL compute lateral collision distance using `j4_collision_gap(j4_arm1, j4_arm2)` from `collision_math` instead of inline `abs(j4_arm1 - j4_arm2)`.

#### Scenario: Distance computed with opposite-facing formula
- **WHEN** truth monitor receives J4 values for both arms
- **THEN** it SHALL compute distance as `j4_collision_gap(j4_arm1, j4_arm2)` which returns `abs(j4_arm1 + j4_arm2)`

#### Scenario: Collision detected correctly for converging arms
- **WHEN** arm1 j4=0.05 and arm2 j4=-0.02 (arms converging)
- **THEN** distance SHALL be abs(0.05 + (-0.02)) = 0.03
