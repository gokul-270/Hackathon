## Tasks

### T1: Add slope term to `fk_chain.py:phi_compensation()`
- [ ] Add `PHI_ZONE1_SLOPE`, `PHI_ZONE2_SLOPE`, `PHI_ZONE3_SLOPE` constants (all 0.0)
- [ ] Update formula: `base = slope * (phi_deg / 90) + offset`
- [ ] Write failing test: `test_phi_compensation_uses_slope_term`
- [ ] Write failing test: `test_phi_compensation_with_nonzero_slope`
- [ ] Make tests pass with updated implementation
- **Ref:** design D1, spec `pick-compute-api` slope scenario

### T2: Change `enable_phi_compensation` default to `true`
- [ ] Update `CottonComputeRequest.enable_phi_compensation` default to `True`
- [ ] Update `CottonPickRequest.enable_phi_compensation` default to `True`
- [ ] Update `CottonPickAllRequest.enable_phi_compensation` default to `True`
- [ ] Write failing test: `test_compute_applies_compensation_by_default`
- [ ] Write failing test: `test_pick_applies_compensation_by_default`
- [ ] Write failing test: `test_pick_all_applies_compensation_by_default`
- [ ] Write failing test: `test_compensation_can_be_disabled_explicitly`
- [ ] Make tests pass by changing defaults
- [ ] Update existing tests that rely on `enable_phi_compensation=False` default
- **Ref:** design D4, spec `pick-compute-api` default scenarios

### T3: Wire phi compensation into dual-arm run path
- [ ] Add `enable_phi_compensation` param to `ArmRuntime.compute_candidate_joints()`
- [ ] Import `phi_compensation` from `fk_chain` in `arm_runtime.py`
- [ ] When enabled, extract `result['j3']` and `result['j5']` from the dict,
      apply `result['j3'] = phi_compensation(result['j3'], result['j5'])`,
      and return the updated dict
- [ ] Write failing test: `test_compute_candidate_joints_applies_phi_compensation`
- [ ] Write failing test: `test_compute_candidate_joints_skips_compensation_when_disabled`
- [ ] Make tests pass
- **Ref:** design D2, spec `dual-arm-run-orchestration` compensated J3 scenario
- **Depends on:** T1

### T4: Thread `enable_phi_compensation` through RunController
- [ ] Add `enable_phi_compensation: bool = True` to `RunStartRequest`
- [ ] Pass flag to `RunController.__init__()` and store as attribute
- [ ] Forward flag to `ArmRuntime.compute_candidate_joints()` calls
- [ ] Write failing test: `test_run_controller_passes_phi_compensation_to_runtime`
- [ ] Make test pass
- **Ref:** design D3, spec `dual-arm-run-orchestration` request parameter scenario
- **Depends on:** T3

### T5: Update UI to pass phi compensation to run endpoint
- [ ] Change `cotton-phi-comp` checkbox to checked by default in `testing_ui.html`
- [ ] Update JS run start function to read and send `enable_phi_compensation`
- [ ] Write failing Playwright E2E test for checkbox default state
- [ ] Write failing test: `test_run_start_sends_phi_compensation`
- [ ] Make tests pass
- **Ref:** spec `dual-arm-run-orchestration` UI checkbox scenarios
- **Depends on:** T4
