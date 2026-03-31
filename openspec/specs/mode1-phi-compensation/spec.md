# mode1-phi-compensation Specification

## Purpose
TBD - created by archiving change mode1-phi-compensation-in-diagnostics. Update Purpose after archive.
## Requirements
### Requirement: Mode 1 Cosine Formula Uses Compensated Phi

The Mode 1 j5 limit formula SHALL use the compensated phi angle for `j3`, not
the raw geometric phi from `polar_decompose()`.  Compensation is applied via
`phi_compensation(j3, j5)` from `fk_chain`, matching the value that
`ArmRuntime.compute_candidate_joints()` provides to `BaselineMode` at runtime.

#### Scenario: Diagnostic j3 equals phi_compensation output

- **GIVEN** camera coordinates that produce raw phi `r` and j5 `e` via `polar_decompose()`
- **WHEN** `collision_diagnostics._cam_to_joints()` is called with those coordinates
- **THEN** the returned `j3` SHALL equal `phi_compensation(r, e)`, not `r`

#### Scenario: Diagnostic j3 differs from raw phi for Zone 1 angles

- **GIVEN** camera coordinates that produce `|phi_deg| <= 50.5°` (Zone 1)
- **WHEN** `collision_diagnostics._cam_to_joints()` is called
- **THEN** the returned `j3` SHALL differ from `result["phi"]` by approximately
  `0.014 * (1 + 0.5 * j5/0.6) * 2π` radians

#### Scenario: Raw phi still accessible via phi key

- **GIVEN** any camera coordinates
- **WHEN** `collision_diagnostics._cam_to_joints()` is called
- **THEN** `result["phi"]` SHALL still hold the raw geometric phi from `polar_decompose()`
- **AND** `result["j3"]` SHALL hold the compensated value

### Requirement: Mode 1 Diagnostic Verdict Consistent With Runtime

The Mode 1 verdict produced by `collision_diagnostics.diagnose_collision()` SHALL
be consistent with the verdict that `BaselineMode.apply_with_skip()` would produce
for the same camera coordinates at runtime, with respect to the phi value used in
the cosine formula.

#### Scenario: Diagnostic COLLISION verdict matches runtime block decision

- **GIVEN** two-arm camera coordinates where compensated j3 causes j5 to exceed
  the cosine limit
- **WHEN** `diagnose_collision()` is called for those coordinates
- **THEN** Mode 1 verdict SHALL be `COLLISION` with `intervention=j5_zeroed`
- **AND** the j5_limit SHALL be computed as `0.20 / cos(|compensated_j3|)`

#### Scenario: Diagnostic SAFE verdict matches runtime pass-through

- **GIVEN** two-arm camera coordinates where compensated j3 causes j5 to be within
  the cosine limit
- **WHEN** `diagnose_collision()` is called for those coordinates
- **THEN** Mode 1 verdict SHALL be `SAFE` with `intervention=none`

