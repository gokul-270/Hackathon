## ADDED Requirements

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
