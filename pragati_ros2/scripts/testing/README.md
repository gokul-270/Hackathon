# Testing Scripts

This directory contains testing and validation scripts for the Pragati robotics system.

## Simulated Camera Testing

Test yanthra arm node with simulated cotton detection data (no camera required).

### Quick Start

```bash
# Single detection (3 positions)
./simulate_cotton_detection.sh

# Continuous publishing at 2 Hz
./simulate_cotton_detection.sh continuous

# Continuous at custom rate
./simulate_cotton_detection.sh continuous 5

# Custom position
./simulate_cotton_detection.sh custom 0.3 0.0 0.5
```

### Test Scenarios

Run predefined test scenarios to validate arm behavior:

```bash
# Run all scenarios
python3 test_detection_scenarios.py

# Run specific scenario
python3 test_detection_scenarios.py progressive  # Progressive load test
python3 test_detection_scenarios.py boundaries   # Workspace boundaries
python3 test_detection_scenarios.py confidence   # Confidence variation
python3 test_detection_scenarios.py empty        # Empty detections
python3 test_detection_scenarios.py circular     # Circular pattern
python3 test_detection_scenarios.py grid         # Grid pattern
python3 test_detection_scenarios.py alternating  # Dense/sparse alternating
python3 test_detection_scenarios.py rapid        # Rapid fire detections
```

**Available Scenarios:**
1. **Progressive Load** - Test with 1, 3, 5, 10 cotton positions
2. **Workspace Boundaries** - Test at edges of workspace (near/far, left/right, high/low)
3. **Confidence Variation** - Test different detection confidence levels
4. **Empty Detections** - Test zero-detection behavior
5. **Circular Pattern** - Cotton arranged in circle
6. **Grid Pattern** - Cotton arranged in 3x3 grid
7. **Alternating Density** - Switch between dense and sparse
8. **Rapid Fire** - Quick consecutive detections

### Detailed Documentation

See [SIMULATED_CAMERA_TESTING.md](../../docs/guides/SIMULATED_CAMERA_TESTING.md) for:
- Complete API documentation
- Coordinate system reference
- Advanced testing patterns
- Troubleshooting guide
- Integration with Phase 0 testing

## Motor Testing

### Individual Motor Tests

Test individual motors with encoder validation:

```bash
./motor/test_motors.sh
```

### Hardware Integration Tests

Full system integration testing:

```bash
../hardware_integration_test.sh
```

## Related Documentation

- **Simulated Testing Guide:** `docs/guides/SIMULATED_CAMERA_TESTING.md`
- **Camera Integration:** `docs/guides/CAMERA_INTEGRATION_GUIDE.md`
- **Testing Matrix:** `docs/project-notes/JANUARY_FIELD_TRIAL_TESTING_MATRIX.md`
