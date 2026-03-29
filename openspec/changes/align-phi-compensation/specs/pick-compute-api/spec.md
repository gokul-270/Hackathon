## MODIFIED Requirements

### Requirement: Phi compensation formula matches C++ trajectory planner

The `phi_compensation()` function in `fk_chain.py` SHALL use the same formula as
`trajectory_planner.cpp`: `base = slope × (phi_deg / 90) + offset`. The constants
SHALL match `production.yaml` values:

| Constant | Value | Unit |
|---|---|---|
| `PHI_ZONE1_MAX_DEG` | 50.5 | degrees |
| `PHI_ZONE2_MAX_DEG` | 60.0 | degrees |
| `PHI_ZONE1_SLOPE` | 0.0 | rotations per normalized angle |
| `PHI_ZONE1_OFFSET` | 0.014 | rotations |
| `PHI_ZONE2_SLOPE` | 0.0 | rotations per normalized angle |
| `PHI_ZONE2_OFFSET` | 0.0 | rotations |
| `PHI_ZONE3_SLOPE` | 0.0 | rotations per normalized angle |
| `PHI_ZONE3_OFFSET` | -0.014 | rotations |
| `PHI_L5_SCALE` | 0.5 | dimensionless |
| `JOINT5_MAX` | 0.6 | metres (for L5 normalization) |

#### Scenario: Slope term included in compensation calculation

- **GIVEN** `phi_compensation(j3, j5)` is called with j3=-0.5 rad, j5=0.1 m
- **WHEN** the compensation is computed
- **THEN** the base compensation uses `slope * (phi_deg / 90) + offset`
  where `phi_deg = abs(degrees(j3))`
- **AND** the result matches the C++ `trajectory_planner.cpp` output for the same inputs

#### Scenario: Nonzero slope produces different compensation

- **GIVEN** `PHI_ZONE1_SLOPE` is patched to 0.1 (for testing purposes)
- **AND** j3=-0.3 rad (17.2°, Zone 1), j5=0.0 m
- **WHEN** `phi_compensation(j3, j5)` is called
- **THEN** the base compensation includes the slope contribution:
  `base = 0.1 * (17.2 / 90) + 0.014 = 0.0331 rotations`
- **AND** the returned j3 differs from the offset-only result

Note: The full compensation pipeline (zone selection → base computation →
L5 scaling → rotation-to-radian conversion → addition to j3) remains unchanged;
only the zone-selection base computation gains the slope term.

#### Scenario: Zone 2 applies zero compensation (unchanged)

- **GIVEN** j3=-0.92 rad (52.7°, Zone 2)
- **WHEN** `phi_compensation(j3, j5)` is called
- **THEN** the returned value equals the input j3 (zone2 offset and slope are both 0.0)

### Requirement: enable_phi_compensation defaults to true

All Pydantic request models (`CottonComputeRequest`, `CottonPickRequest`,
`CottonPickAllRequest`) SHALL set `enable_phi_compensation: bool = True`
(changed from `False`).

#### Scenario: Compute endpoint applies compensation by default

- **WHEN** `POST /api/cotton/compute` is called without specifying `enable_phi_compensation`
- **THEN** phi compensation is applied to the returned j3 value

#### Scenario: Pick endpoint applies compensation by default

- **WHEN** `POST /api/cotton/pick` is called without specifying `enable_phi_compensation`
- **THEN** the returned j3 value has phi compensation applied

#### Scenario: Pick-all endpoint applies compensation by default

- **WHEN** `POST /api/cotton/pick-all` is called without specifying `enable_phi_compensation`
- **THEN** all returned j3 values have phi compensation applied

#### Scenario: Caller can disable compensation explicitly

- **WHEN** `POST /api/cotton/compute` is called with `enable_phi_compensation: false`
- **THEN** the returned j3 equals the raw phi from `polar_decompose()`
