## ADDED Requirements

### Requirement: Verified Against Real Cam-Point Data
The scheduler SHALL be exercised in an end-to-end test using real cam-point data from
`arm1.csv` and `arm2.csv` (the same files used by `test_collision_diagnostics.py`),
confirming that the gap improvement guarantee holds on field-representative data and not
only on synthetic unit-test inputs.

#### Scenario: Real CSV data produces non-degraded min gap
- **WHEN** `SmartReorderScheduler.reorder()` is called with a step_map built from
  `arm1.csv` and `arm2.csv` cam_z values
- **THEN** the minimum j4 gap of the reordered result is >= the minimum j4 gap of the
  original sequential pairing
