# Testing and Validation Plan - OAK-D Lite Cotton Detection System

ℹ️ **HISTORICAL DOCUMENT - Archived Nov 4, 2025**

**Original Date:** October 2025  
**Status at Time:** Pre-Hardware Testing Plan  
**Superseded By:** [TESTING_AND_OFFLINE_OPERATION.md](../../../guides/TESTING_AND_OFFLINE_OPERATION.md)

**Historical Context:**  
This document outlined the comprehensive testing plan for OAK-D Lite cotton detection system validation. It defined test phases from pre-hardware (complete) through hardware validation, integration, and performance testing. The plan was successfully executed, culminating in Nov 1, 2025 production validation with 134ms service latency, 100% reliability, and ±10mm spatial accuracy @ 0.6m.

**Outcome:** ✅ All Phase 1-3 tests passed, system validated Nov 1, 2025  
**Current Status:** Production Ready - Testing methods consolidated

---

**Project**: Pragati Cotton Picking Robot - ROS2 Migration  
**Component**: Cotton Detection System with OAK-D Lite Camera  
**Phase**: Phase 1 (Python Wrapper) Testing  
**Original Planning Date**: October 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Test Environment Setup](#test-environment-setup)
3. [Pre-Hardware Testing](#pre-hardware-testing)
4. [Hardware Testing](#hardware-testing)
5. [Integration Testing](#integration-testing)
6. [Performance Testing](#performance-testing)
7. [Acceptance Criteria](#acceptance-criteria)
8. [Test Reports](#test-reports)

---

## Overview

### Test Objectives

1. ✅ **Build Validation**: Ensure system builds successfully
2. ⏳ **Hardware Integration**: Validate OAK-D Lite camera connectivity
3. ⏳ **Detection Accuracy**: Verify cotton detection spatial accuracy
4. ⏳ **ROS2 Integration**: Test service/topic interfaces
5. ⏳ **Performance**: Measure latency and throughput
6. ⏳ **Stability**: Multi-hour runtime testing

### Testing Phases

| Phase | Status | Duration | Prerequisites |
|-------|--------|----------|---------------|
| **Phase 0: Pre-Hardware** | ✅ Complete | 3 days | None |
| **Phase 1: Hardware Basic** | ⏳ Pending | 2-4 hours | OAK-D Lite camera |
| **Phase 2: Integration** | ⏳ Pending | 4-6 hours | Phase 1 complete |
| **Phase 3: Performance** | ⏳ Pending | 8-12 hours | Phase 2 complete |
| **Phase 4: Production** | ⏳ Pending | Multi-day | All phases complete |

---

## Test Environment Setup

### Hardware Requirements

#### Required Hardware ✅
- **OAK-D Lite Camera** (Luxonis DM9095)
- **USB Cable** (USB 2.0/3.0, recommend USB 2.0 for stability)
- **Host Computer** (Ubuntu 24.04, ROS2 Jazzy)
- **Cotton Target Objects** (real cotton bolls or white objects for testing)

#### Optional Hardware 📋
- **Measurement Tools** (ruler/tape measure for distance validation)
- **Calibration Targets** (ArUco markers, checkerboard)
- **Testing Rig** (fixed mount for repeatable tests)

### Software Environment

#### Operating System
```bash
Ubuntu 24.04 LTS (Noble Numbat)
Linux kernel: 6.8+
Architecture: x86_64 or ARM64
```

#### ROS2 Installation
```bash
ROS_DISTRO=jazzy
ROS2 Jazzy Desktop (full installation)
```

#### Dependencies
```bash
# ROS2 packages
ros-jazzy-vision-msgs
ros-jazzy-sensor-msgs
ros-jazzy-image-transport
ros-jazzy-cv-bridge

# Python packages (in venv)
depthai==3.0.0
opencv-python
numpy
open3d (optional, for PCD visualization)
```

### Workspace Setup

```bash
# Clone/navigate to workspace
cd /home/uday/Downloads/pragati_ros2

# Source ROS2
source /opt/ros/jazzy/setup.bash

# Build workspace
colcon build

# Source workspace
source install/setup.bash

# Activate Python venv
source venv/bin/activate
```

---

## Pre-Hardware Testing

### Phase 0: Build and Static Analysis ✅

#### Test 0.1: Clean Build ✅
**Status**: ✅ PASS

**Procedure**:
```bash
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select cotton_detection_ros2
```

**Expected Results**:
- ✅ Build completes without errors
- ✅ All packages build successfully
- ✅ Python scripts installed correctly
- ✅ YOLO blobs installed correctly

**Actual Results** (Phase 1 Day 3):
- Build time: ~1min 33s
- Warnings: Expected (DepthAI C++ not needed for Phase 1)
- Errors: None
- **Result**: ✅ PASS

---

#### Test 0.2: File Installation Verification ✅
**Status**: ✅ PASS

**Procedure**:
```bash
# Check wrapper script
ls -l install/lib/cotton_detection_ros2/cotton_detect_ros2_wrapper.py

# Check OakDTools scripts
ls -l install/lib/cotton_detection_ros2/OakDTools/CottonDetect.py
find install/lib/cotton_detection_ros2/OakDTools -name "*.py" | wc -l

# Check YOLO blobs
ls -l install/share/cotton_detection_ros2/models/*.blob
```

**Expected Results**:
- Wrapper script executable and present
- All 38 OakDTools Python scripts present
- All 3 YOLO blobs present

**Actual Results**:
- ✅ Wrapper script: Present and executable
- ✅ OakDTools scripts: All 38 files present
- ✅ YOLO blobs: All 3 files present
- **Result**: ✅ PASS

---

#### Test 0.3: ROS2 Package Discovery ✅
**Status**: ✅ PASS

**Procedure**:
```bash
source install/setup.bash
ros2 pkg list | grep cotton_detection
ros2 interface list | grep cotton_detection
```

**Expected Results**:
- Package `cotton_detection_ros2` listed
- Service interfaces listed:
  - `cotton_detection_ros2/srv/CottonDetection`
  - `cotton_detection_ros2/srv/DetectCotton`

**Result**: ✅ PASS (verified in Phase 1 Day 3)

---

#### Test 0.4: Python Syntax Validation ✅
**Status**: ✅ PASS

**Procedure**:
```bash
python3 -m py_compile src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py
```

**Expected Results**:
- No syntax errors
- Compiles successfully

**Result**: ✅ PASS

---

#### Test 0.5: Launch File Validation ✅
**Status**: ✅ PASS

**Procedure**:
```bash
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py --show-args
```

**Expected Results**:
- Launch file loads without errors
- All parameters listed:
  - `usb_mode`, `confidence_threshold`, `blob_path`, etc.

**Result**: ✅ PASS (8 launch arguments verified)

---

## Hardware Testing

### Phase 1: Basic Hardware Validation ⏳

#### Test 1.1: Camera Detection ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
# Check USB device
lsusb | grep "03e7:2485"

# Test DepthAI connectivity
python3 << EOF
import depthai as dai
devices = dai.Device.getAllAvailableDevices()
print(f"Found {len(devices)} OAK device(s)")
for dev in devices:
    print(f"  - MxID: {dev.getMxId()}")
EOF
```

**Expected Results**:
- USB device detected with VID:PID `03e7:2485`
- DepthAI SDK finds 1 OAK-D Lite device
- Device MXID printed

**Acceptance Criteria**:
- [ ] Camera detected via USB
- [ ] DepthAI SDK recognizes device
- [ ] Device MXID retrieved successfully

---

#### Test 1.2: Camera Calibration Export ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
cd src/cotton_detection_ros2/config/cameras/oak_d_lite
source ../../../../../venv/bin/activate
python3 export_calibration.py
```

**Expected Results**:
- Calibration export completes without errors
- 4 YAML files created:
  - `rgb_camera_info.yaml`
  - `left_camera_info.yaml`
  - `right_camera_info.yaml`
  - `stereo_params.yaml`
- Baseline distance reported (expected: ~7.5 cm)

**Acceptance Criteria**:
- [ ] Calibration export succeeds
- [ ] All YAML files created
- [ ] Intrinsics and distortion parameters populated
- [ ] Baseline within expected range (7-8 cm)

---

#### Test 1.3: CottonDetect.py Standalone Test ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
cd install/lib/cotton_detection_ros2/OakDTools
source ../../../../../venv/bin/activate

# Run standalone detection script
python3 CottonDetect.py

# Check outputs
ls -l cotton_details.txt
ls -l img100.jpg
ls -l DetectionOutput.jpg
```

**Expected Results**:
- Script runs without errors
- `cotton_details.txt` created with detection coordinates
- `img100.jpg` captured (1920x1080 RGB)
- `DetectionOutput.jpg` with annotations

**Acceptance Criteria**:
- [ ] Script completes successfully
- [ ] Output files created
- [ ] Detection coordinates formatted correctly
- [ ] No DepthAI pipeline errors

---

#### Test 1.4: USB2 Mode Stability ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
# Run CottonDetect.py with USB2 mode for 10 iterations
for i in {1..10}; do
    echo "Iteration $i"
    python3 CottonDetect.py
    sleep 2
done
```

**Expected Results**:
- All 10 iterations complete successfully
- No USB disconnections
- No pipeline errors
- Consistent frame capture

**Acceptance Criteria**:
- [ ] 10/10 iterations succeed
- [ ] No USB errors in dmesg
- [ ] Frame capture time consistent (±10%)
- [ ] No memory leaks

---

### Phase 2: ROS2 Wrapper Integration ⏳

#### Test 2.1: Wrapper Node Launch ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
# Terminal 1: Launch wrapper
source install/setup.bash
source venv/bin/activate
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py
```

**Expected Results**:
- Node launches without errors
- Parameters loaded correctly
- ROS2 services advertised:
  - `/cotton_detection/detect`
  - `/cotton_detection/calibrate` (when enabled)
- Topics created (if enabled):
  - `/cotton_detection/results`
  - `/cotton_detection/debug_image`

**Acceptance Criteria**:
- [ ] Node launches successfully
- [ ] All parameters initialized
- [ ] Services advertised
- [ ] No Python exceptions

---

#### Test 2.2: Detection Service Call ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
# Terminal 2: Call detection service
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Expected Results**:
- Service call completes within 10 seconds
- Response received:
  - `success: true`
  - `message: "Detected N cottons"`
  - `detection_count: N` (where N >= 0)

**Acceptance Criteria**:
- [ ] Service responds within timeout
- [ ] Response success=true (if cotton present)
- [ ] Detection count matches cotton_details.txt
- [ ] No wrapper errors

---

#### Test 2.3: Detection Topic Publishing ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
# Terminal 3: Monitor topic
ros2 topic echo /cotton_detection/results

# Terminal 2: Trigger detection
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Expected Results**:
- Topic message published after service call
- Message type: `vision_msgs/Detection3DArray`
- Detection array populated with:
  - Header with correct timestamp and frame_id
  - Detection positions (x, y, z in meters)
  - Confidence scores
  - Bounding boxes

**Acceptance Criteria**:
- [ ] Message published within 2 seconds of service call
- [ ] Message format correct (vision_msgs/Detection3DArray)
- [ ] Frame ID = `camera_rgb_optical_frame`
- [ ] Coordinates in meters (z > 0)
- [ ] Detection count matches service response

---

#### Test 2.4: Parameter Configuration ⏳
**Status**: ⏳ Pending (awaiting camera)

**Procedure**:
```bash
# Launch with custom parameters
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    usb_mode:=usb3 \
    confidence_threshold:=0.7 \
    blob_path:=yolov8.blob \
    publish_debug_images:=true
```

**Expected Results**:
- Parameters applied correctly
- Detection runs with new settings
- Debug images published (if enabled)

**Acceptance Criteria**:
- [ ] Parameters override defaults
- [ ] Confidence threshold affects results
- [ ] Different blob loads successfully
- [ ] Debug images published when enabled

---

## Integration Testing

### Phase 3: System Integration ⏳

#### Test 3.1: TF Frame Validation ⏳
**Status**: ⏳ Pending (awaiting camera + URDF integration)

**Procedure**:
```bash
# Check TF tree
ros2 run tf2_tools view_frames

# Check specific transforms
ros2 run tf2_ros tf2_echo base_link camera_rgb_optical_frame
```

**Expected Results**:
- TF tree includes camera frames:
  - `camera_link`
  - `camera_rgb_frame`
  - `camera_rgb_optical_frame`
  - `camera_left_optical_frame`
  - `camera_right_optical_frame`
- Transform from `base_link` to camera frames available

**Acceptance Criteria**:
- [ ] All camera frames in TF tree
- [ ] Transforms published
- [ ] Frame naming follows REP-103

---

#### Test 3.2: Detection Coordinate Transform ⏳
**Status**: ⏳ Pending

**Procedure**:
```bash
# Place cotton target at known distance (e.g., 1.0m)
# Trigger detection
# Transform detection coordinates to base_link frame
```

**Expected Results**:
- Detection coordinates transform correctly
- Transformed coordinates match physical measurement

**Acceptance Criteria**:
- [ ] Coordinates transform without errors
- [ ] Spatial accuracy within ±5cm at 1.0-1.5m
- [ ] Multiple detections transform consistently

---

#### Test 3.3: Multi-Robot Integration ⏳
**Status**: ⏳ Pending (requires yanthra_move integration)

**Procedure**:
```bash
# Launch full robot stack
ros2 launch robo_bringup robot.launch.py

# Verify cotton detection service available
ros2 service list | grep cotton_detection

# Call detection from arm control node
# (Manual integration test)
```

**Expected Results**:
- All nodes launch successfully
- Cotton detection service available
- Arm control can call detection service
- Detection coordinates used for motion planning

**Acceptance Criteria**:
- [ ] Full stack launches
- [ ] Inter-node communication works
- [ ] Detection triggers arm motion
- [ ] No namespace conflicts

---

## Performance Testing

### Phase 4: Performance Validation ⏳

#### Test 4.1: Detection Latency ⏳
**Status**: ⏳ Pending

**Procedure**:
```bash
# Measure end-to-end latency (service call to response)
# Run 50 iterations, measure each

# Script:
#!/bin/bash
for i in {1..50}; do
    start=$(date +%s%N)
    ros2 service call /cotton_detection/detect \
        cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" > /dev/null
    end=$(date +%s%N)
    latency=$((($end - $start) / 1000000))  # Convert to milliseconds
    echo "$latency" >> latency_results.txt
done

# Calculate statistics
cat latency_results.txt | awk '{sum+=$1; sumsq+=$1*$1} END {print "Mean:", sum/NR, "ms"; print "StdDev:", sqrt(sumsq/NR - (sum/NR)^2), "ms"}'
```

**Expected Results** (Phase 1 Targets):
- Mean latency: < 2000 ms (2 seconds)
- Standard deviation: < 500 ms
- No outliers > 5000 ms

**Acceptance Criteria**:
- [ ] Mean latency < 2 seconds
- [ ] 95th percentile < 3 seconds
- [ ] No timeouts
- [ ] Latency consistent across 50 iterations

---

#### Test 4.2: Detection Accuracy ⏳
**Status**: ⏳ Pending

**Procedure**:
```bash
# Place cotton targets at known positions
# Positions: (x=0.2m, y=0m, z=1.0m), (x=-0.1m, y=0.1m, z=1.2m), etc.
# Run detection 10 times for each position
# Compare detected vs actual positions
```

**Expected Results**:
- Spatial accuracy: ±5cm at 1.0-1.5m distance
- Detection repeatability: ±2cm for same target
- Confidence scores: > 0.5 for cotton

**Acceptance Criteria**:
- [ ] X/Y accuracy: ±5cm
- [ ] Z (depth) accuracy: ±10cm
- [ ] Repeatability: ±2cm standard deviation
- [ ] No false positives in empty scenes

---

#### Test 4.3: Multi-Hour Stability ⏳
**Status**: ⏳ Pending

**Procedure**:
```bash
# Run continuous detection for 4 hours
# Trigger detection every 30 seconds
# Monitor for crashes, memory leaks, USB disconnections

# Script:
#!/bin/bash
start_time=$(date +%s)
count=0
errors=0

while [ $(($(date +%s) - start_time)) -lt 14400 ]; do  # 4 hours
    count=$((count + 1))
    echo "Iteration $count at $(date)"
    
    if ros2 service call /cotton_detection/detect \
        cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" > /dev/null 2>&1; then
        echo "  Success"
    else
        errors=$((errors + 1))
        echo "  ERROR"
    fi
    
    sleep 30
done

echo "Total iterations: $count"
echo "Total errors: $errors"
echo "Success rate: $(echo "scale=2; 100 * (1 - $errors / $count)" | bc)%"
```

**Expected Results**:
- Success rate: > 99% (< 5 errors in 480 iterations)
- No crashes or hangs
- Memory usage stable (< 10% growth)
- No USB disconnections

**Acceptance Criteria**:
- [ ] Success rate > 99%
- [ ] Node stays running entire duration
- [ ] Memory usage stable
- [ ] No USB errors in system logs

---

#### Test 4.4: USB2 vs USB3 Comparison ⏳
**Status**: ⏳ Pending

**Procedure**:
```bash
# Run same test with USB2 and USB3 modes
# Compare latency, frame rate, stability

# USB2 test
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb2
# Run performance tests

# USB3 test
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb3
# Run performance tests
```

**Expected Results**:
- USB2 mode: Stable, slightly lower frame rate
- USB3 mode: Higher frame rate, may have bandwidth issues with long cables

**Acceptance Criteria**:
- [ ] Both modes function correctly
- [ ] USB2 mode stable over long cables
- [ ] Performance difference documented

---

## Acceptance Criteria

### Phase 1 Acceptance (Minimum Viable)

✅ **Build System**:
- [x] Clean build without errors
- [x] All files installed correctly
- [x] ROS2 package discoverable

⏳ **Hardware Integration**:
- [ ] Camera detected and recognized
- [ ] Factory calibration readable
- [ ] CottonDetect.py runs successfully

⏳ **ROS2 Integration**:
- [ ] Wrapper node launches
- [ ] Services respond correctly
- [ ] Topics publish valid messages

⏳ **Functional Requirements**:
- [ ] Cotton detection works
- [ ] Spatial coordinates accurate (±5cm at 1.0-1.5m)
- [ ] USB2 mode stable

### Phase 2 Acceptance (Production Ready)

⏳ **Performance**:
- [ ] Detection latency < 2 seconds (Phase 1) or < 200ms (Phase 2)
- [ ] Multi-hour stability (> 99% success rate)
- [ ] No memory leaks or crashes

⏳ **Integration**:
- [ ] TF frames correct
- [ ] Coordinate transforms accurate
- [ ] Works with full robot stack

⏳ **Documentation**:
- [ ] All tests documented
- [ ] Test results recorded
- [ ] Known issues documented

---

## Test Reports

### Test Report Template

```markdown
# Test Report: [Test Name]

**Date**: YYYY-MM-DD
**Tester**: [Name]
**Environment**: [Hardware/Software details]

## Test Configuration
- Camera: OAK-D Lite (MxID: [ID])
- USB Mode: [usb2/usb3]
- ROS2 Version: Jazzy
- Blob: [yolov8v2.blob]

## Test Procedure
[Steps taken]

## Results
[Detailed results]

## Pass/Fail
[✅ PASS / ❌ FAIL]

## Notes
[Any observations, issues, recommendations]
```

### Test Log Location

All test logs should be saved to:
```
/home/uday/Downloads/pragati_ros2/test_output/integration/
├── build_tests/
├── hardware_tests/
├── integration_tests/
├── performance_tests/
└── test_output/regression/
```

---

## Automated Testing

### Future Automated Tests

**Unit Tests** (Phase 2+):
```bash
# Python unit tests for wrapper node
pytest src/cotton_detection_ros2/test/
```

**ROS2 Launch Tests**:
```bash
# Launch test framework
colcon test --packages-select cotton_detection_ros2
colcon test-result --verbose
```

**CI/CD Integration**:
- GitHub Actions workflow
- Automated build testing
- Linting and static analysis

---

## Troubleshooting Guide

### Common Issues

#### Camera Not Detected
**Symptoms**: `lsusb` doesn't show OAK-D Lite
**Solutions**:
1. Check USB cable connection
2. Try different USB port
3. Check dmesg for USB errors: `dmesg | tail -50`
4. Verify udev rules for DepthAI

#### Service Call Timeout
**Symptoms**: Service call hangs or times out
**Solutions**:
1. Check if CottonDetect.py is running
2. Verify output directory permissions
3. Check cotton_details.txt creation
4. Increase `detection_timeout` parameter

#### Incorrect Spatial Coordinates
**Symptoms**: Detected positions don't match reality
**Solutions**:
1. Verify camera calibration
2. Check TF frame transforms
3. Ensure camera mounted correctly
4. Re-run calibration export

---

**Document Version**: 1.0  
**Status**: Ready for Hardware Testing  
**Next Update**: After Phase 1 hardware tests complete
