# CI/CD Pipeline Documentation

## Overview
Automated continuous integration pipeline for Pragati ROS2 project using GitHub Actions.

## Workflows

### Main CI Pipeline (`ci.yml`)

**Triggers:**
- Push to `master`, `pragati_ros2`
- Push to `feature/**`, `fix/**` branches  
- Pull requests to `master`, `pragati_ros2`

**Jobs:**

#### 1. Build & Test
- **Environment:** Ubuntu 22.04, ROS2 Humble
- **Steps:**
  1. Checkout code
  2. Setup ROS2 Humble
  3. Install dependencies (rosdep)
  4. Build all packages with coverage flags
  5. Run all unit tests
  6. Generate coverage reports (XML, HTML)
  7. Upload artifacts

**Coverage Threshold:** Currently informational (will enforce 70% later)

#### 2. Lint C++
- Check C++ code formatting with clang-format
- Runs on all `.cpp` and `.hpp` files

#### 3. Lint Python
- **black:** Check Python formatting
- **isort:** Check import ordering
- **flake8:** Check code style

#### 4. Pre-commit Hooks
- Run all configured pre-commit hooks
- Validates formatting before merge

#### 5. Build Status Summary
- Aggregates all job results
- Fails if build/test fails
- Warnings for lint failures (non-blocking)

---

## Viewing Results

### GitHub UI
1. Go to repository → **Actions** tab
2. Click on workflow run
3. View job details and logs
4. Download artifacts (coverage, test results)

### Coverage Reports
- Download **coverage-reports** artifact
- Open `coverage.html` in browser
- View detailed line-by-line coverage

### Test Results
- Download **test-results** artifact
- XML files compatible with test reporting tools

---

## Local Testing

### Before Pushing
```bash
# Run pre-commit hooks
pre-commit run --all-files

# Build with same flags as CI
colcon build \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_CXX_FLAGS="--coverage" \
    -DBUILD_TESTING=ON

# Run tests
colcon test --return-code-on-test-failure

# Generate coverage
gcovr -r . --filter 'src/' --html-details coverage.html
```

---

## Adding New Tests

1. Add test files in `<package>/test/`
2. Update `CMakeLists.txt` with `ament_add_gtest`
3. CI will automatically run new tests

---

## Troubleshooting

### Build Failures
- Check **Build workspace** step logs
- Look for missing dependencies or compile errors
- Test locally first

### Test Failures
- Check **Run tests** step logs
- Download test-results artifact for details
- Run locally: `colcon test --packages-select <package>`

### Lint Failures
- Run pre-commit locally to fix
- C++: `clang-format -i <file>`
- Python: `black <file>` and `isort <file>`

---

## Future Enhancements

### Planned
- [ ] Coverage threshold enforcement (70%)
- [ ] Performance benchmarking
- [ ] Docker image building
- [ ] Deployment automation

### Optional
- [ ] Multi-distro testing (Humble + Iron)
- [ ] ARM64 builds (for Raspberry Pi)
- [ ] Nightly integration tests

---

## Configuration Files

**Related files:**
- `.github/workflows/ci.yml` - Main workflow
- `.pre-commit-config.yaml` - Pre-commit hooks
- `.gitignore` - Excludes build artifacts

**Status Badges:**

Add to main README.md:
```markdown
![CI Status](https://github.com/<org>/<repo>/workflows/Pragati%20ROS2%20CI/badge.svg)
```

---

**Last Updated:** 2025-10-21  
**Maintainer:** Dev Team
