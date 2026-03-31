## MODIFIED Requirements

### Requirement: Reorder optimizer uses opposite-facing J4 formula
The smart reorder scheduler SHALL compute minimum J4 gap using `j4_collision_gap(arm1_j4, arm2_j4)` from `collision_math` instead of inline `abs(arm1_j4 - arm2_j4)`.

#### Scenario: Min gap computed with opposite-facing formula
- **WHEN** the scheduler evaluates step permutations for collision risk
- **THEN** it SHALL use `j4_collision_gap(arm1_j4s[i], arm2_j4s[perm[i]])` for each step pair

#### Scenario: FK-derived J4 values produce correct gap
- **WHEN** J4 values are computed via FK as `j4 = 0.1005 - cam_z` producing negative values
- **THEN** gap SHALL be `abs(j4_a + j4_b)` with correct arithmetic on negative inputs
