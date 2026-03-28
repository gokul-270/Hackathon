# Vehicle Control Testing Quick-Start Guide

**Audience:** Test Engineers  
**Time Required:** 30-60 minutes  
**Prerequisites:** Basic command line knowledge  
**Date:** 2025-11-04

---

## Overview

This guide helps test engineers quickly validate the ROS2 vehicle control system. You can test **WITHOUT hardware** using the simulation framework - this is a major advantage over ROS1.

---

## Prerequisites

### System Requirements
- Ubuntu 20.04+ or similar Linux
- Python 3.8+
- ROS2 installed (Humble, Iron, or Jazzy)

### Setup Environment
```bash
# Navigate to workspace
cd /home/uday/Downloads/pragati_ros2

# Source ROS2 (adjust for your ROS2 version)
source /opt/ros/humble/setup.bash  # or iron, jazzy

# Build if needed
colcon build --symlink-install --packages-select vehicle_control

# Source workspace
source install/setup.bash
```

---

## Quick Validation (10 minutes)

### 1. Run Simulation (No Hardware!)
```bash
# GUI mode - interactive
python3 src/vehicle_control/simulation/run_simulation.py --gui

# Headless mode - for automated testing
python3 src/vehicle_control/simulation/run_simulation.py --headless
```

**Expected:** Simulation window opens with vehicle visualization

**What to check:**
- Window launches without errors
- Vehicle model visible
- Control parameters displayed
- No crash for at least 30 seconds

###  2. Run Basic Demo
```bash
python3 src/vehicle_control/demo.py
```

**Expected:** Demo runs and completes successfully

**What to check:**
- No Python exceptions
- Status messages appear
- Demo completes (exit code 0)

### 3. Run Simple Test
```bash
pytest src/vehicle_control/test_ros2_nodes.py -v
```

**Expected:** Tests pass (green output)

**What to check:**
- Test discovery works
- All tests pass or skip appropriately
- No failures

---

## Comprehensive Testing (30 minutes)

### All Demo Scripts

Run each demo to see different aspects:

```bash
# Basic demo
python3 src/vehicle_control/demo.py

# Simple scenarios
python3 src/vehicle_control/simple_demo.py

# Quick validation
python3 src/vehicle_control/quick_start.py

# Full feature demonstration
python3 src/vehicle_control/demo_complete_functionality.py
```

**Expected for each:**
- Completes without errors
- Shows relevant status messages
- Exit code 0

---

### All Test Suites

```bash
# Node tests
pytest src/vehicle_control/test_ros2_nodes.py -v

# System integration tests
pytest src/vehicle_control/test_ros2_system.py -v

# Performance tests
pytest src/vehicle_control/test_performance.py -v

# Or run all at once
pytest src/vehicle_control/ -v
```

**Alternative using colcon:**
```bash
colcon test --packages-select vehicle_control
colcon test-result --verbose
```

---

### Simulation with GUI Controls

```bash
python3 src/vehicle_control/simulation/run_simulation.py --gui
```

**GUI Controls (typical):**
- **Arrow Keys:** Control vehicle movement
- **Space:** Emergency stop
- **R:** Reset simulation
- **Q/ESC:** Quit

**What to observe:**
- Vehicle responds to inputs
- Physics behaves realistically
- Status displays update
- No lag or freezing

---

## Configuration Management

### View Current Configuration
```bash
cat src/vehicle_control/config/vehicle_params.yaml
```

**Key parameters to note:**
- `joint_names`: List of controlled joints
- `control_frequency`: Control loop rate (Hz)
- `physical_params`: Vehicle dimensions and limits

### Test with Custom Config
```bash
# Copy and modify
cp src/vehicle_control/config/vehicle_params.yaml /tmp/my_config.yaml
# Edit /tmp/my_config.yaml as needed

# Run with custom config
ros2 launch vehicle_control vehicle_control_with_params.launch.py \
  config_file:=/tmp/my_config.yaml
```

---

## Hardware Testing Checklist (When Available)

### Pre-Hardware Checks
- [ ] All simulation tests pass
- [ ] All demo scripts run successfully
- [ ] Configuration reviewed and validated
- [ ] Test plan documented
- [ ] Rollback procedure prepared

### Hardware Setup
1. **Power:**
   - [ ] Battery charged
   - [ ] Power connections secure
   - [ ] Emergency stop accessible

2. **Wiring:**
   - [ ] Motor controllers connected
   - [ ] GPIO pins wired correctly
   - [ ] CAN bus @ 500 kbps
   - [ ] IMU connected

3. **Safety:**
   - [ ] E-stop tested and working
   - [ ] Clear testing area
   - [ ] Personnel briefed
   - [ ] Fire extinguisher nearby

### Hardware Test Sequence

```bash
# 1. Run hardware test framework
python3 src/vehicle_control/hardware/test_framework.py

# 2. Check motor communication
# (Test framework will prompt)

# 3. Test GPIO interfaces
# (Test framework will prompt)

# 4. Calibrate steering
# (Follow test framework instructions)

# 5. Run safety system tests
# (Test framework will verify e-stop, limits, etc.)
```

### Hardware Test Topics to Monitor

```bash
# In separate terminals:

# Monitor joint states
ros2 topic echo /joint_states

# Monitor vehicle status
ros2 topic echo /vehicle_status

# Check node health
ros2 node list
ros2 node info /vehicle_control_node
```

### Data Recording

```bash
# Record test run
ros2 bag record -a -o test_run_$(date +%Y%m%d_%H%M%S)

# Play back for analysis
ros2 bag play test_run_YYYYMMDD_HHMMSS
```

---

## Comparison with ROS1

### Functional Parity Check

| Feature | ROS1 | ROS2 | Status |
|---------|------|------|--------|
| Motor control | ✅ | ✅ | Verify in hardware |
| GPIO interface | ✅ | ✅ | Verify in hardware |
| Joystick input | ✅ | ✅ | Verify in hardware |
| Emergency stop | ✅ | ✅ | Verify in hardware |
| State machine | ✅ | ✅ | Verified in simulation |

### Performance Comparison

To compare with ROS1 baseline:

1. **Identify ROS1 test scenario**
2. **Reproduce in ROS2 simulation:**
   ```bash
   python3 src/vehicle_control/simulation/run_simulation.py --scenario ros1_baseline
   ```
3. **Compare logs:**
   - Control loop timing
   - Response latency
   - Error rates
4. **Validate:** ROS2 meets or exceeds ROS1 performance

---

## Troubleshooting

### Simulation Won't Start
```bash
# Check Python dependencies
pip3 install -r src/vehicle_control/requirements-simulation.txt

# Check for conflicting processes
ps aux | grep python
```

### Tests Failing
```bash
# Check environment
echo $ROS_DISTRO
echo $PYTHONPATH

# Re-source workspace
source install/setup.bash

# Run with verbose output
pytest src/vehicle_control/test_ros2_nodes.py -vv
```

### ROS2 Node Issues
```bash
# Check if node is running
ros2 node list

# Check topics
ros2 topic list

# Check parameters
ros2 param list /vehicle_control_node
```

### Hardware Connection Issues
```bash
# Check CAN interface
ip link show can0

# Check permissions
ls -l /dev/ttyUSB*
groups $USER  # Should include dialout
```

---

## Reporting Results

### What to Document

1. **Test Environment:**
   - OS version
   - ROS2 version
   - Hardware (if used)

2. **Tests Run:**
   - List of commands executed
   - Which passed/failed
   - Screenshots of key results

3. **Issues Found:**
   - Description
   - Steps to reproduce
   - Error messages/logs

4. **Comparison with ROS1:**
   - Functional differences
   - Performance differences
   - Recommendations

### Report Template

```markdown
# Vehicle Control Test Report

**Date:** YYYY-MM-DD
**Tester:** Your Name
**Environment:** Ubuntu 22.04, ROS2 Humble

## Simulation Tests
- [ ] Simulation GUI: PASS/FAIL
- [ ] Demo scripts: PASS/FAIL
- [ ] Unit tests: PASS/FAIL

## Hardware Tests (if applicable)
- [ ] Motor control: PASS/FAIL
- [ ] GPIO: PASS/FAIL
- [ ] Safety systems: PASS/FAIL

## Issues Found
1. [Description]
2. [Description]

## Recommendations
- ...
```

---

## Next Steps

### After Successful Testing

1. **Report results** to development team
2. **Provide feedback** on this guide
3. **Plan hardware testing** (if simulation passed)
4. **Schedule field validation**

### If Issues Found

1. **Document thoroughly**
2. **Check if simulation-only issue**
3. **Verify with ROS1 behavior** (if possible)
4. **Report to development team**

---

## Resources

- **Main Comparison:** [VEHICLE_CONTROL_ROS1_VS_ROS2_COMPARISON.md](../VEHICLE_CONTROL_ROS1_VS_ROS2_COMPARISON.md)
- **Metrics:** [metrics_summary.md](../reports/metrics_summary.md)
- **Package README:** [VEHICLE_CONTROL_MIGRATION_PACKAGE_README.md](../VEHICLE_CONTROL_MIGRATION_PACKAGE_README.md)

---

## Contact

**Questions?** Contact Development Team

**Issues?** Document in test report

**Suggestions?** Submit feedback on this guide

---

**Last Updated:** 2025-11-04  
**Version:** 1.0  
**Status:** Ready for Use
