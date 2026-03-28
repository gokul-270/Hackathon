# Automated Regression Test Suite

## Overview

The `automated_regression_test.sh` script provides comprehensive automated testing for the Pragati ROS2 workspace with detailed reporting, CI/CD integration, and multiple output formats.

**Location:** `scripts/automated_regression_test.sh`

---

## Features

✅ **Automated Build & Test** - Builds workspace and runs all test suites  
✅ **Multiple Report Formats** - JSON, HTML, JUnit XML  
✅ **Coverage Reports** - Optional lcov coverage generation  
✅ **CI/CD Ready** - GitHub Actions output markers  
✅ **Fail-Fast Mode** - Stop on first failure for CI pipelines  
✅ **Package Filtering** - Test specific packages only  
✅ **Verbose Mode** - Detailed output for debugging  
✅ **Test Statistics** - Total tests, pass/fail counts, duration  

---

## Quick Start

### Run All Tests
```bash
./scripts/automated_regression_test.sh
```

### Run with HTML Report
```bash
./scripts/automated_regression_test.sh --html
```

### CI Mode (Fast Fail)
```bash
./scripts/automated_regression_test.sh --ci
```

---

## Usage

```
./automated_regression_test.sh [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--packages PKG1,PKG2` | Run tests for specific packages only |
| `--verbose` | Show detailed test output |
| `--junit` | Generate JUnit XML reports |
| `--coverage` | Generate coverage reports (requires lcov) |
| `--html` | Generate HTML test report |
| `--ci` | CI mode: fail fast, minimal output |
| `--help` | Show help message |

---

## Examples

### Test Specific Package
```bash
./scripts/automated_regression_test.sh --packages motor_control_ros2
```

### Generate All Reports
```bash
./scripts/automated_regression_test.sh --html --junit --coverage
```

### Verbose Testing
```bash
./scripts/automated_regression_test.sh --verbose --packages motor_control_ros2
```

### Multiple Packages
```bash
./scripts/automated_regression_test.sh --packages motor_control_ros2,cotton_detection_ros2
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All tests passed |
| `1` | One or more tests failed |
| `2` | Build failed |
| `3` | Invalid arguments |

---

## Output

### Default Output
- Colored console output with test results
- Summary statistics (total tests, passed, failed, duration)
- Report directory location

### Generated Files

All reports are saved to `test_output/regression/regression_TIMESTAMP/`:

| File | Description |
|------|-------------|
| `regression_test.log` | Complete test execution log |
| `test_results.json` | Machine-readable JSON test results |
| `test_report.html` | Human-readable HTML report |
| `junit/*.xml` | JUnit XML reports (with `--junit`) |
| `coverage_html/index.html` | Coverage report (with `--coverage`) |
| `*_test_output.txt` | Individual package test output |

---

## Test Suites

The script automatically runs tests for:

1. **motor_control_ros2**
   - Protocol encoding/decoding tests (34 tests)
   - Safety monitor tests (14 tests)
   - Parameter validation tests (12 tests)
   - CAN communication tests (28 tests)

2. **cotton_detection_ros2**
   - Detection pipeline tests
   - Image processing tests
   - YOLO detector tests

3. **yanthra_move**
   - Movement coordination tests
   - Calibration tests
   - Integration tests

**Total:** 88+ unit tests, 7 integration tests, 106 static analysis tests

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Regression Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup ROS2
        uses: ros-tooling/setup-ros@v0.6
        with:
          required-ros-distributions: humble
      
      - name: Build workspace
        run: colcon build
      
      - name: Run regression tests
        run: ./scripts/automated_regression_test.sh --ci --html --junit
      
      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-reports
          path: test_output/regression/
      
      - name: Publish test results
        if: always()
        uses: EnricoMi/publish-unit-test-result-action@v2
        with:
          files: test_output/regression/**/junit/*.xml
```

### GitLab CI Example

```yaml
test:
  stage: test
  script:
    - source /opt/ros/humble/setup.bash
    - colcon build
    - ./scripts/automated_regression_test.sh --ci --junit
  artifacts:
    when: always
    reports:
      junit: test_output/regression/**/junit/*.xml
    paths:
      - test_output/regression/
```

---

## Coverage Reports

### Prerequisites

Install lcov:
```bash
sudo apt-get install lcov
```

### Generate Coverage

```bash
./scripts/automated_regression_test.sh --coverage --html
```

View HTML coverage report:
```bash
xdg-open test_output/regression/regression_*/coverage_html/index.html
```

---

## Troubleshooting

### Build Failures

If the build fails, check:
1. All dependencies installed
2. Workspace is sourced: `source install/setup.bash`
3. Build log at: `test_output/regression/regression_*/regression_test.log`

### Test Failures

For test failures:
1. Use `--verbose` to see detailed output
2. Check individual test output in `test_output/regression/regression_*/*_test_output.txt`
3. Review JUnit reports for specific failure details

### Coverage Not Generated

If coverage isn't generated:
1. Install lcov: `sudo apt-get install lcov`
2. Rebuild with coverage: `colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="--coverage"`
3. Use `--coverage` flag

---

## Performance

Typical execution times:

| Scope | Build | Test | Total |
|-------|-------|------|-------|
| Single package (motor_control_ros2) | ~11s | ~5s | ~16s |
| All packages | ~25s | ~12s | ~37s |
| With coverage | ~30s | ~15s | ~45s |

---

## Best Practices

### Local Development
```bash
# Quick test during development
./scripts/automated_regression_test.sh --packages motor_control_ros2

# Full test before commit
./scripts/automated_regression_test.sh --html
```

### Continuous Integration
```bash
# CI pipeline
./scripts/automated_regression_test.sh --ci --junit --html
```

### Coverage Analysis
```bash
# Weekly coverage check
./scripts/automated_regression_test.sh --coverage --html
```

---

## Maintenance

### Adding New Tests

1. Add test files to `src/PACKAGE/test/`
2. Update `CMakeLists.txt` to include new tests
3. Run script to verify: `./scripts/automated_regression_test.sh --packages PACKAGE`

### Modifying Test Packages

Edit the `test_packages` array in the script:

```bash
local test_packages=(
    "motor_control_ros2"
    "cotton_detection_ros2"
    "yanthra_move"
    "your_new_package"  # Add here
)
```

---

## Test Results History

### October 21, 2025
- **Total Tests:** 88 unit tests + 7 integration tests
- **Pass Rate:** 100%
- **Duration:** 3.73s (unit tests)
- **Status:** ✅ All tests passing

---

## Related Documentation

- [CONSOLIDATED_ROADMAP.md](../docs/CONSOLIDATED_ROADMAP.md) - Project roadmap
- [TESTING_SPRINT_SUMMARY.md](../docs/archive/2025-10-21/TESTING_SPRINT_SUMMARY.md) - Sprint details
- [UNIT_TEST_GUIDE.md](../docs/guides/UNIT_TEST_GUIDE.md) - Writing unit tests

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review test output in `test_output/regression/`
3. Check individual test files in `src/*/test/`
4. Review build logs in `test_output/regression/*/regression_test.log`

---

**Last Updated:** October 21, 2025  
**Status:** Production Ready ✅  
**Version:** 1.0.0
