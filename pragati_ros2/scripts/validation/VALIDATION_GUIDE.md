# Validation Scripts Guide

## Quick Reference

### Parameter Validation
```bash
# Comprehensive parameter checks
./scripts/validation/comprehensive_parameter_validation.py

# Runtime verification
./scripts/validation/runtime_parameter_verification.py

# YAML validation
./scripts/validation/verify_yaml_parameters.py
./scripts/validation/test_yaml_loading.py
```

### Service Validation
```bash
# Functional tests
./scripts/validation/comprehensive_service_validation.py

# Stress testing
./scripts/validation/robust_service_stress_test.py
```

### System Validation
```bash
# Full system verification
./scripts/validation/comprehensive_system_verification.py

# Integration checks
./scripts/validation/critical_integration_validation.py

# Flow verification
./scripts/validation/prove_complete_flow.py
./scripts/validation/corrected_flow_validation.py
```

### Quick Validation
```bash
# Fast sanity check
./scripts/validation/quick_validation.sh

# End-to-end test
./scripts/validation/end_to_end_validation.sh
```

## When to Use Each

**Before Commit**: `quick_validation.sh`
**Before Deploy**: `end_to_end_validation.sh`
**Parameter Changes**: `comprehensive_parameter_validation.py`
**Service Issues**: `comprehensive_service_validation.py`
**System Integration**: `comprehensive_system_verification.py`
**Stress Testing**: `robust_service_stress_test.py`

## Test Infrastructure

Primary entry point: `./test.sh`
```bash
./test.sh --quick      # Quick tests
./test.sh --complete   # Full suite
```

Phase-based testing: `./test_suite/run_tests.sh`
```bash
./test_suite/run_tests.sh 1     # Run Phase 1 tests
./test_suite/run_tests.sh all   # Run all phases
```

