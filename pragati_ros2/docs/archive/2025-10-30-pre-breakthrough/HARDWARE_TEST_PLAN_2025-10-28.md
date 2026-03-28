# Hardware Testing Plan - 2025-10-29
**Prepared**: 2025-10-29 Evening  
**Test Date**: Tomorrow (2025-10-30)  
**Duration**: Maximum 4 hours  
**Hardware**: RPi4 + 3x MG6010 Motors + OAK-D Lite Camera  
**Critical Fix**: Enable C++ DepthAI integration on RPi

---

## 🚨 CRITICAL FIX REQUIRED BEFORE TESTING

### Issue Identified (2025-10-29)
**Problem**: Detection taking 7-8 seconds (Python wrapper overhead)  
**Root Cause**: DepthAI C++ library not installed on RPi  
**Impact**: C++ node falls back to waiting for `/camera/image_raw` (never arrives)  

### Solution - Install on RPi FIRST:
```bash
# On Raspberry Pi
sudo apt update
sudo apt install ros-jazzy-depthai ros-jazzy-depthai-bridge

# Rebuild with DepthAI support
cd ~/pragati_ros2
colcon build --packages-select cotton_detection_ros2 \
    --cmake-args -DHAS_DEPTHAI=ON \
    --allow-overriding cotton_detection_ros2

# Source workspace
source install/setup.bash
```

### Expected Performance Improvement:
- **Current (Python wrapper)**: 7-8 seconds per detection ❌
- **Target (C++ DepthAI)**: 100-150ms per detection ✅
- **Speedup**: 50-80x faster!

### Verification:
```bash
# Check DepthAI installation
dpkg -l | grep depthai

# Should see:
# ii  ros-jazzy-depthai
# ii  ros-jazzy-depthai-bridge

# Test DepthAI manager
ros2 run cotton_detection_ros2 depthai_manager_hardware_test
```

---

## 📊 Current Status Review

### ✅ What's Already Tested & Working
1. **Camera Hardware Detection** (Phase 0-1 Complete - 7/7 tests passed)
   - USB device recognition ✅
   - DepthAI device enumeration ✅
   - Camera initialization ✅
   - C++ node launch ✅
   - Service availability ✅
   - Full system integration ✅
   - Camera details: MxId `18443010513F671200`, Bus 001 Device 058

2. **Motor Control (Partial)**
   - System launch successful ✅
   - Homing completed for joint3, joint4, joint5 ✅
   - START_SWITCH integration working ✅

### ⏳ What Needs Hardware Testing (50+ tests pending)

Based on review of:
- `docs/PENDING_HARDWARE_TESTS.md` (17 pending tests)
- `docs/HARDWARE_TEST_CHECKLIST.md` (50+ test scenarios)
- `docs/TODO_MASTER.md` (hardware-dependent tasks)

---

## 🎯 Tomorrow's Testing Strategy

### Time Allocation (4 hours max)
| Session | Duration | Focus | Priority |
|---------|----------|-------|----------|
| Session 1 | 60 min | Critical Detection Tests | 🔴 HIGH |
| Session 2 | 60 min | Motor Control Validation | 🔴 HIGH |
| Session 3 | 60 min | Integration & Accuracy | 🟡 MEDIUM |
| Session 4 | 60 min | Stress & Performance | 🟢 LOW |

### Break Strategy
- 10 min break after Session 1
- 10 min break after Session 2
- 15 min break after Session 3

---

## 📋 SESSION 1: Critical Detection Tests (60 min)

**Goal**: Validate core cotton detection functionality with real hardware

### 1.1 Service Call & Detection Test (15 min) 🔴 CRITICAL

**Pre-check**:
```bash
# Verify system is sourced
source ~/Downloads/pragati_ros2/install/setup.bash

# Check services available
ros2 service list | grep cotton_detection
```

**Test Commands**:
```bash
# Terminal 1: Monitor detection results
ros2 topic echo /cotton_detection/results

# Terminal 2: Trigger detection
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Success Criteria**:
- [ ] Service returns `success: true`
- [ ] Detections published to `/cotton_detection/results`
- [ ] **Response time < 200ms** (was 7-8s, target 100-150ms with C++ DepthAI)
- [ ] No exceptions in logs
- [ ] Log shows "Using DepthAI C++ direct detection" (not "waiting for camera")

**Expected Output Location**: `~/pragati_test_output/integration/<timestamp>/cotton_detection_cpp/`

**Troubleshooting**:
- Check logs: `ros2 log list` and `ros2 log view cotton_detection_node`
- Verify camera still connected: `lsusb | grep 03e7`

---

### 1.2 Calibration Export Test (10 min) 🔴 CRITICAL

**Test Command**:
```bash
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"
```

**Success Criteria**:
- [ ] Service returns success
- [ ] YAML file created with calibration data
- [ ] File path returned in response
- [ ] Calibration data contains intrinsics and extrinsics

**Expected Output**: 
- Check response message for file path
- Typical location: `~/pragati/outputs/calibration/` or `/home/ubuntu/pragati/outputs/`

---

### 1.3 Standalone CottonDetect.py Test (20 min) 🔴 CRITICAL

**Purpose**: Validate detection script works independently before ROS2 integration

**Commands**:
```bash
cd ~/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts/OakDTools

# Check blob file exists
ls -lh yolov8v2.blob

# Run standalone script
python3 CottonDetect.py yolov8v2.blob
```

**Success Criteria**:
- [ ] Script launches without errors
- [ ] SIGUSR2 signal sent (camera ready)
- [ ] Can trigger with SIGUSR1: `kill -USR1 <PID>`
- [ ] Output files created: `cotton_details.txt`, `DetectionOutput.jpg`
- [ ] Script responds to Ctrl+C gracefully

**Monitoring**:
```bash
# In another terminal, watch for output files
watch -n 1 "ls -lth ~/pragati/outputs/ | head -n 10"
```

---

### 1.4 Topic Publishing Verification (15 min) 🟡 MEDIUM

**Commands**:
```bash
# Check topic structure
ros2 topic info /cotton_detection/results

# Echo once to verify message format
ros2 topic echo /cotton_detection/results --once

# Check topic rate
ros2 topic hz /cotton_detection/results
```

**Success Criteria**:
- [ ] Topic type is `vision_msgs/msg/Detection3DArray`
- [ ] Frame ID is correct: `oak_rgb_camera_optical_frame`
- [ ] Coordinates in reasonable range (0.5-2.0m depth)
- [ ] Class ID is "cotton"
- [ ] Timestamps are current

---

## 📋 SESSION 2: Motor Control Validation (60 min)

**Goal**: Validate motor communication, control, and safety systems

### 2.1 Motor Status & Communication (15 min) 🔴 CRITICAL

**Pre-check**:
```bash
# Check CAN interface
ip link show can0

# Should show: state UP, bitrate 250000 (or 500000)
```

**Test Commands**:
```bash
# Use existing detailed status script
./scripts/detailed_motor_status.sh

# Or manual check
ros2 service call /motor_status motor_control_ros2/srv/MotorStatus
```

**Success Criteria**:
- [ ] All 3 motors respond
- [ ] Status shows: enabled, homed, no errors
- [ ] Position values within expected range
- [ ] Temperature readings present
- [ ] Voltage readings present

---

### 2.2 Motor Movement Test (20 min) 🔴 CRITICAL

**SAFETY FIRST**: Ensure emergency stop is ready and motors have clear movement range

**Commands**:
```bash
# Small test movement (joint 3)
ros2 service call /move_joint motor_control_ros2/srv/MoveJoint \
    "{joint_name: 'joint3', target_position: 0.1, velocity: 0.1}"

# Wait for completion (5-10 seconds)

# Return to zero
ros2 service call /move_joint motor_control_ros2/srv/MoveJoint \
    "{joint_name: 'joint3', target_position: 0.0, velocity: 0.1}"
```

**Success Criteria**:
- [ ] Motor moves smoothly without jerking
- [ ] Reaches target position accurately (±0.01 rad)
- [ ] No error messages
- [ ] Movement completes within expected time
- [ ] Can return to zero position

**Monitor during movement**:
```bash
# In another terminal
./scripts/utils/monitor_motor_positions.sh
```

---

### 2.3 Safety System Validation (15 min) 🔴 CRITICAL

**Test 1: Emergency Stop**
```bash
# Trigger emergency stop
ros2 service call /emergency_stop std_srvs/srv/Trigger

# Or use script
./emergency_motor_stop.sh

# Verify motors disabled
ros2 service call /motor_status motor_control_ros2/srv/MotorStatus
```

**Success Criteria**:
- [ ] All motors stop immediately
- [ ] Motors report disabled state
- [ ] Can re-enable after clearing: `ros2 service call /enable_motors`

**Test 2: Safety Limits**
```bash
# Try to move beyond limit (should be rejected)
ros2 service call /move_joint motor_control_ros2/srv/MoveJoint \
    "{joint_name: 'joint3', target_position: 99.0, velocity: 0.1}"
```

**Expected**: Service should reject with error message about safety limits

---

### 2.4 Multi-Motor Coordination (10 min) 🟡 MEDIUM

**Commands**:
```bash
# Use existing complete system test
./test_complete_system.sh

# Or manual multi-joint movement
ros2 service call /move_joints motor_control_ros2/srv/MoveJoints \
    "{joint_names: ['joint3', 'joint4', 'joint5'], \
      positions: [0.1, 0.1, 0.1], \
      velocities: [0.1, 0.1, 0.1]}"
```

**Success Criteria**:
- [ ] All motors move simultaneously
- [ ] Coordination is smooth
- [ ] All reach targets within tolerance
- [ ] No interference between motors

---

## 📋 SESSION 3: Integration & Accuracy (60 min)

**Goal**: Validate detection accuracy and motor-camera coordination

### 3.1 Detection Accuracy Test (25 min) 🟡 MEDIUM

**Setup Required**:
- Place test object (cotton or white object) at known distance
- Measure actual distance with ruler/tape measure
- Test at: 0.5m, 1.0m, 1.5m distances

**Test Procedure**:
```bash
# Place object at 1.0m distance
# Launch detection
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=true simulation_mode:=false

# Trigger 10 detections
for i in {1..10}; do
  echo "Detection $i"
  ros2 service call /cotton_detection/detect \
      cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
  sleep 2
done
```

**Record Results**:
- [ ] Depth accuracy within ±5cm at 1.0m
- [ ] Lateral accuracy (X/Y) within ±3cm
- [ ] Consistent results across 10 detections
- [ ] No wild outliers

**Data Collection**:
```bash
# Save topic output to file
ros2 topic echo /cotton_detection/results > detection_accuracy_test.txt
```

---

### 3.2 End-to-End Workflow Test (25 min) 🟡 MEDIUM

**Full Cotton Picking Workflow**:
1. Detect cotton
2. Get coordinates
3. Move arm to position
4. Confirm position reached

**Commands**:
```bash
# Launch full system
ros2 launch <your_complete_launch_file>

# Monitor workflow
# Terminal 1: Watch detections
ros2 topic echo /cotton_detection/results

# Terminal 2: Watch motor positions
./scripts/utils/monitor_motor_positions.sh

# Terminal 3: Trigger workflow
ros2 service call /start_picking std_srvs/srv/Trigger
```

**Success Criteria**:
- [ ] Detection completes successfully
- [ ] Coordinates correctly published
- [ ] Arm moves to target position
- [ ] Position reached within tolerance
- [ ] Complete workflow < 10 seconds

---

### 3.3 Coordinate Transformation Test (10 min) 🟡 MEDIUM

**Verify camera-to-base coordinate transformation**:

```bash
# Check TF tree
ros2 run tf2_tools view_frames

# Check specific transform
ros2 run tf2_ros tf2_echo base_link oak_rgb_camera_optical_frame

# Test coordinate transformation
ros2 topic echo /cotton_detection/results
# Note the coordinates in camera frame

# Verify they make sense relative to robot base
```

**Success Criteria**:
- [ ] TF tree is complete (no missing transforms)
- [ ] Transform base→camera is reasonable
- [ ] Detected coordinates align with physical setup

---

## 📋 SESSION 4: Stress & Performance (60 min)

**Goal**: Test system stability and performance limits

### 4.1 Repeated Detection Test (15 min) 🟢 LOW

**Using existing test script**:
```bash
# 20 consecutive detections
for i in {1..20}; do
  echo "Detection $i"
  ros2 service call /cotton_detection/detect \
      cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" \
      --timeout 15
  sleep 2
done
```

**Monitor**:
```bash
# In another terminal, watch for issues
htop  # CPU/Memory usage
dmesg -w  # USB disconnections
```

**Success Criteria**:
- [ ] All 20 detections succeed
- [ ] No subprocess crashes
- [ ] No memory leaks (check with `htop`)
- [ ] Consistent latency
- [ ] No USB disconnections

---

### 4.2 Detection Latency Measurement (15 min) 🟢 LOW

**Create simple benchmark script**:
```bash
# Save as test_latency.sh
#!/bin/bash
echo "Testing detection latency (10 iterations)..."
for i in {1..10}; do
  start=$(date +%s%N)
  ros2 service call /cotton_detection/detect \
      cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" \
      > /dev/null 2>&1
  end=$(date +%s%N)
  latency=$(( (end - start) / 1000000 ))
  echo "Detection $i: ${latency}ms"
done
```

**Target Metrics**:
- [ ] Service call latency: < 500ms
- [ ] Detection processing: < 2 seconds
- [ ] Total end-to-end: < 2.5 seconds

---

### 4.3 Long-Duration Stability Test (20 min) 🟢 LOW

**Launch and let run**:
```bash
# Launch system
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# In another terminal, trigger detection every 30 seconds
watch -n 30 'ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"'

# Monitor for 20 minutes
```

**Monitor**:
- CPU usage: `htop`
- Memory: `watch -n 5 'ps aux | grep cotton'`
- USB: `dmesg -w`

**Success Criteria**:
- [ ] Runs for 20+ minutes without crash
- [ ] Memory usage stable (< 500MB)
- [ ] CPU usage reasonable (< 50% avg)
- [ ] No USB disconnections
- [ ] Detection latency remains consistent

---

### 4.4 Hardware Integration Test Script (10 min) 🟢 LOW

**Use existing comprehensive test**:
```bash
# Run the existing hardware integration test
./scripts/hardware_integration_test.sh all
```

**This tests**:
- CAN interface
- Motor status
- Camera detection
- Full system launch
- Node health
- Topic data flow

**Review output** in `test_output/hardware_tests/`

---

## 🔧 Pre-Flight Checklist (Run Before Starting)

```bash
# 1. Source environment
source /opt/ros/jazzy/setup.bash
source ~/Downloads/pragati_ros2/install/setup.bash

# 2. Check hardware connections
lsusb | grep 03e7  # Camera
ip link show can0   # CAN interface

# 3. Verify services
ros2 service list | grep -E "(motor|cotton)"

# 4. Check disk space
df -h | grep -E "(/$|/home)"

# 5. Check existing processes
ps aux | grep -E "(ros2|cotton|motor)" | grep -v grep

# 6. Create test output directory
mkdir -p ~/test_results_$(date +%Y%m%d)
cd ~/test_results_$(date +%Y%m%d)
```

---

## 📝 Test Execution Tracking

Use this checklist during testing:

### Session 1: Critical Detection Tests
- [ ] 1.1 Service Call & Detection (15 min)
- [ ] 1.2 Calibration Export (10 min)
- [ ] 1.3 Standalone Script (20 min)
- [ ] 1.4 Topic Publishing (15 min)

### Session 2: Motor Control
- [ ] 2.1 Motor Status (15 min)
- [ ] 2.2 Movement Test (20 min)
- [ ] 2.3 Safety Systems (15 min)
- [ ] 2.4 Multi-Motor (10 min)

### Session 3: Integration
- [ ] 3.1 Detection Accuracy (25 min)
- [ ] 3.2 End-to-End Workflow (25 min)
- [ ] 3.3 Coordinate Transform (10 min)

### Session 4: Stress Testing
- [ ] 4.1 Repeated Detection (15 min)
- [ ] 4.2 Latency Measurement (15 min)
- [ ] 4.3 Long-Duration Stability (20 min)
- [ ] 4.4 Integration Test Script (10 min)

---

## 🚨 Emergency Procedures

### If Motor Goes Out of Control
```bash
# Emergency stop script
./emergency_motor_stop.sh

# Or manual
ros2 service call /emergency_stop std_srvs/srv/Trigger

# Physical power off if needed
```

### If Camera Stops Responding
```bash
# Kill node
ros2 node kill /cotton_detection_node

# Replug USB cable
# Restart node

# Check USB
dmesg | tail -20
lsusb | grep 03e7
```

### If System Becomes Unresponsive
```bash
# Kill all ROS2 processes
killall -9 ros2

# Or use cleanup script
./scripts/essential/cleanup_ros2.sh

# Restart from fresh state
```

---

## 📊 Data Collection Plan

### What to Log
1. **Motor Performance**
   - Position accuracy (target vs actual)
   - Movement time
   - Safety limit triggers
   - Error messages

2. **Detection Performance**
   - Detection latency (10 samples min)
   - Accuracy at different distances (3 distances)
   - False positive/negative rate
   - Detection success rate

3. **System Performance**
   - CPU usage (average over 10 min)
   - Memory usage (check for leaks)
   - USB stability (any disconnections?)
   - Process crashes

### Where to Save
```bash
# All logs in timestamped directory
~/test_results_$(date +%Y%m%d)/
├── session1_detection.log
├── session2_motors.log
├── session3_integration.log
├── session4_stress.log
├── detection_accuracy.csv
├── motor_performance.csv
└── system_metrics.txt
```

---

## 📋 Post-Testing Review

### Immediate Actions (After Each Session)
1. Save all terminal outputs
2. Copy important logs
3. Note any anomalies
4. Update test checklist

### End of Day Review
1. Compile test results
2. Update `docs/HARDWARE_TEST_RESULTS_2025-10-28.md`
3. Update `docs/PENDING_HARDWARE_TESTS.md`
4. Document any issues found
5. Create GitHub issues for blockers

### What to Document
- ✅ What worked perfectly
- ⚠️ What worked but needs tuning
- ❌ What didn't work (with error messages)
- 💡 Observations and insights
- 📝 Parameter values that worked well

---

## 🔗 Reference Documents

Key documents reviewed in preparing this plan:

1. **Test Documentation**
   - `docs/HARDWARE_TEST_CHECKLIST.md` - Comprehensive test procedures
   - `docs/PENDING_HARDWARE_TESTS.md` - 17 pending tests identified
   - `docs/HARDWARE_TEST_RESULTS_2025-10-28.md` - Previous results (7/7 passed)
   - `docs/TESTING_AND_VALIDATION_PLAN.md` - Overall validation strategy

2. **System Documentation**
   - `docs/TODO_MASTER.md` - Hardware-dependent tasks
   - `HARDWARE_QUICKSTART.md` - Quick reference guide
   - `scripts/README.md` - Available test scripts

3. **Integration Guides**
   - `docs/guides/hardware/HARDWARE_TESTING_QUICKSTART.md`
   - `docs/integration/COTTON_DETECTION_INTEGRATION_README.md`

---

## ⏱️ Time Management Rules

1. **Session Time Limits are STRICT**
   - Use phone timer for each session
   - Stop at time limit even if not complete
   - Better to test less thoroughly than rush everything

2. **If Stuck Rule: 10 Minutes Max**
   - If stuck on one test > 10 min, skip and note as blocker
   - Move to next test
   - Come back later if time permits

3. **Break Rule: TAKE THEM**
   - Breaks are mandatory, not optional
   - Use breaks to review what worked/didn't work
   - Clear your head before next session

4. **Priority Rule**
   - 🔴 HIGH must be done
   - 🟡 MEDIUM if time permits
   - 🟢 LOW nice to have

---

## 🎯 Success Criteria for Tomorrow

**Minimum Viable Success** (Sessions 1-2 only, ~2 hours):
- ✅ Cotton detection service works with real hardware
- ✅ Calibration export functional
- ✅ All 3 motors respond to commands
- ✅ Basic movement test passes
- ✅ Safety systems functional

**Good Success** (Sessions 1-3, ~3 hours):
- All minimum criteria +
- ✅ Detection accuracy validated (±5cm)
- ✅ End-to-end workflow tested
- ✅ Multi-motor coordination working

**Excellent Success** (All sessions, ~4 hours):
- All good success criteria +
- ✅ Stress tests completed
- ✅ Performance metrics collected
- ✅ Long-duration stability confirmed

---

## 🏁 Final Notes

**Remember**:
1. You've already completed Phase 0-1 (7/7 tests passed)
2. Camera is proven working
3. Motors have been homed successfully
4. This is about systematic validation, not discovery
5. Document everything - even "it worked perfectly"

**Focus Areas**:
1. Detection accuracy with real objects
2. Motor control precision
3. System integration stability
4. Performance metrics

**Don't Waste Time On**:
1. Debugging offline detection (use what works)
2. Building new infrastructure
3. Fixing documentation during tests
4. Optimizing prematurely

---

**Plan Prepared**: 2025-10-28  
**Ready for Execution**: Tomorrow  
**Estimated Duration**: 2-4 hours (flexible)  
**Hardware Required**: RPi4 + 3 Motors + OAK-D Lite (all connected)  

**Good luck! 🚀**
