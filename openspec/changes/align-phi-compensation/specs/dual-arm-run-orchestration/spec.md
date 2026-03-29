## MODIFIED Requirements

### Requirement: Dual-arm run applies phi compensation

The dual-arm run path SHALL apply phi compensation to J3 values computed by
`ArmRuntime.compute_candidate_joints()`. The `RunStartRequest` model SHALL
include an `enable_phi_compensation: bool = True` field. When enabled,
`phi_compensation(j3, j5)` SHALL be called on the candidate joints before
they are passed to mode logic and execution.

#### Scenario: Dual-arm run uses compensated J3 by default

- **GIVEN** a dual-arm run is started via `POST /api/run/start` without
  specifying `enable_phi_compensation`
- **WHEN** `ArmRuntime.compute_candidate_joints()` returns raw joints
- **THEN** `phi_compensation(j3, j5)` is applied to the j3 value
- **AND** the compensated j3 is used for mode logic and published to `/joint3_cmd`

#### Scenario: Compensation disabled via request parameter

- **GIVEN** a dual-arm run is started with `enable_phi_compensation: false`
- **WHEN** joints are computed for each step
- **THEN** the raw j3 from `polar_decompose()` is used without compensation

#### Scenario: UI passes phi compensation state to run endpoint

- **GIVEN** the user has the "Phi Compensation" checkbox checked in the UI
- **WHEN** the user starts a dual-arm run
- **THEN** the `POST /api/run/start` request body includes
  `enable_phi_compensation: true`

#### Scenario: Phi compensation checkbox default matches endpoint default

- **GIVEN** the testing UI is loaded fresh
- **WHEN** the user inspects the "Phi Compensation" checkbox
- **THEN** it is checked by default (matching the endpoint default of `true`)
