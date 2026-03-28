# Pending Hardware Tests - TODO List

**Date Created**: 2025-10-28  
**Last Updated**: 2025-11-01  
**Status**: Ready for Execution  
**Completed**: 9/9 (Phase 0-1) + Detection Latency Validation  
**Remaining**: ~14 tests (3 HIGH, 4 MEDIUM, 7 LOW priority)

---

## ✅ Completed Tests (Phase 0-1)

- [x] Pre-Test Setup (Hardware & Software)
- [x] USB Device Recognition
- [x] DepthAI Device Enumeration  
- [x] Camera Initialization
- [x] C++ Node Launch
- [x] Service Availability
- [x] Full System Integration
- [x] **NEW (Nov 1):** Detection Latency Validation (134ms avg, production-ready)
- [x] **NEW (Nov 1):** C++ DepthAI Direct Integration (replaced Python wrapper)

---

## 📋 Pending Tests by Priority

### 🔴 **HIGH PRIORITY - Critical Functional Tests**

#### Test 0.2: Service Call & Calibration Export (C++ Node)
**Status**: ⏳ PENDING  
**Prerequisites**: C++ node running  
**Commands**:
```bash
# Trigger detection
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Trigger calibration export
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"
```

**Expected Results**:
- [ ] `detect_command:1` returns `success: true`
- [ ] Detections emitted on `/cotton_detection/results`
- [ ] `detect_command:2` exports calibration YAML
- [ ] Responses logged correctly

**Why Critical**: Validates core detection service functionality with real hardware

---

#### Test 3.2: Service Interface Test (C++ Node)
**Status**: ✅ **VALIDATED (Nov 1, 2025)**  
**Results**: 134ms average latency, production-ready  
**Prerequisites**: C++ node running  
**Commands**:
```bash
# Monitor topic
ros2 topic echo /cotton_detection/results &

# Call service
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Expected Results**:
- [ ] Service returns success
- [ ] Detection count accurate
- [ ] Coordinates published to topic
- [ ] Completes within 10 seconds

**Why Critical**: Validates end-to-end ROS2 detection workflow

**✅ COMPLETED Nov 1, 2025:**
- Service call latency: **134ms average** (123-218ms range)
- Detection time: ~130ms (neural network inference)
- System stable, 100% success rate over 10 consecutive calls
- **Note:** `ros2 service call` CLI shows ~6s due to tool overhead, use persistent client for true latency

---

#### Test 4.1: Calibration Export
**Status**: ⏳ PENDING  
**Prerequisites**: Calibration service available  
**Commands**:
```bash
ros2 service call /cotton_detection/calibrate \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 0}"

ls -lh /home/ubuntu/pragati/outputs/calibration/
```

**Expected Results**:
- [ ] Service returns success
- [ ] Calibration directory created
- [ ] JSON file with valid camera matrices
- [ ] Intrinsic parameters reasonable
- [ ] Baseline ~7.5cm (OAK-D Lite spec)

**Why Critical**: Camera calibration essential for accurate 3D detection

---

### 🟡 **MEDIUM PRIORITY - Functional Validation**

#### Test 2.2: ~~Signal Communication Test~~ (OBSOLETE)
**Status**: ❌ **NOT APPLICABLE**  
**Reason**: C++ DepthAI direct integration replaced Python wrapper (no signals needed)  
**Migration**: ROS2 service calls replace signal-based communication

---

#### Test 3.3: Topic Publishing Test
**Status**: ⏳ PENDING  
**Estimated Time**: 5 minutes  
**Prerequisites**: Detection service working

**Validates**:
- [ ] Detection3DArray message structure
- [ ] Correct frame_id
- [ ] Reasonable coordinate ranges (0.5-2.0m depth)
- [ ] Class ID = "cotton"
- [ ] Current timestamps

---

#### Test 3.4: Debug Image Publishing
**Status**: ⏳ PENDING  
**Estimated Time**: 10 minutes  
**Prerequisites**: rqt_image_view installed

**Validates**:
- [ ] Debug image publishes to `/cotton_detection/debug_image`
- [ ] Bounding boxes visible
- [ ] Confidence scores displayed
- [ ] Spatial coordinates labeled
- [ ] Image encoding = `bgr8`

---

#### Test 8.2: Detection Accuracy Test
**Status**: ⏳ PENDING (REQUIRES PHYSICAL TEST SETUP)  
**Estimated Time**: 30 minutes  
**Prerequisites**: Test object at known distance

**Test Setup**:
1. Place test object at exactly 1.0m distance
2. Trigger 10 detections
3. Measure reported Z coordinate
4. Compare with actual distance

**Acceptance Criteria**:
- [ ] Depth accuracy within ±5cm at 1.0m
- [ ] Lateral accuracy (X/Y) within ±3cm
- [ ] Consistent results (low variance)
- [ ] No wild outliers

**Why Important**: Validates core detection accuracy requirement

---

### 🟢 **LOW PRIORITY - Stress & Edge Cases**

#### Test 5.1: Repeated Detection Test
**Status**: ⏳ PENDING  
**Estimated Time**: 15 minutes  
**Commands**:
```bash
for i in {1..20}; do
  echo "Detection $i"
  ros2 service call /cotton_detection/detect \
      cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
  sleep 2
done
```

**Validates**:
- [ ] 20 consecutive detections succeed
- [ ] No subprocess crashes
- [ ] No memory leaks
- [ ] Consistent latency
- [ ] No file corruption

---

#### Test 5.2: Long-Duration Stability Test
**Status**: ⏳ PENDING  
**Estimated Time**: 30+ minutes  
**Prerequisites**: System idle

**Validates**:
- [ ] Runs 30+ minutes without crash
- [ ] Stable memory usage (<500MB)
- [ ] CPU usage reasonable (<50% avg)
- [ ] No USB disconnections
- [ ] Consistent detection latency

---

#### Test 5.3: USB Cable Length Test
**Status**: ⏳ PENDING  
**Estimated Time**: 20 minutes  
**Prerequisites**: Multiple cable lengths (1m, 3m, 5m)

**Validates**:
- [ ] Stable with 1m cable
- [ ] Stable with 3m cable
- [ ] Stable with 5m cable (USB2 mode)
- [ ] No bandwidth errors

---

#### Test 6.1: Subprocess Crash Recovery
**Status**: ⏳ PENDING  
**Estimated Time**: 10 minutes  

**Test Steps**:
1. Launch wrapper
2. Kill subprocess: `kill -9 <PID>`
3. Attempt detection service call

**Validates**:
- [ ] Wrapper detects crash
- [ ] Error logged clearly
- [ ] Service returns failure gracefully
- [ ] Node remains responsive

---

#### Test 6.2: Camera Disconnect Test
**Status**: ⏳ PENDING  
**Estimated Time**: 5 minutes  

**Test Steps**:
1. Launch wrapper
2. Physically disconnect USB cable
3. Check error handling

**Validates**:
- [ ] Wrapper detects disconnection
- [ ] Subprocess exits with error
- [ ] Clear error logging
- [ ] Clean node shutdown

---

#### Test 6.3: Timeout Test
**Status**: ⏳ PENDING  
**Estimated Time**: 10 minutes  

**Validates**:
- [ ] Service fails after timeout
- [ ] Clear timeout error message
- [ ] Wrapper remains functional
- [ ] Next detection succeeds

---

#### Test 7.1: Simulation Mode Test
**Status**: ⏳ PENDING  
**Estimated Time**: 5 minutes  

**Validates**:
- [ ] Launches without camera
- [ ] No subprocess spawned
- [ ] Synthetic detections (3 test points)
- [ ] Service calls succeed
- [ ] No camera init errors

---

#### Test 8.1: Detection Latency Measurement
**Status**: ⏳ PENDING  
**Estimated Time**: 15 minutes  
**Prerequisites**: Performance benchmark script

**Target Metrics**:
- [ ] Service call latency: <500ms
- [ ] Detection processing: <2 seconds
- [ ] File I/O overhead: <200ms
- [ ] Total end-to-end: <2.5 seconds

---

#### Test 9.1: Integration Test Suite
**Status**: ⏳ PENDING  
**Estimated Time**: 10 minutes  
**Prerequisites**: Test scripts available

**Validates**:
- [ ] Subprocess management tests pass
- [ ] Signal communication tests pass
- [ ] File I/O tests pass
- [ ] Error handling tests pass

---

## 📊 Test Summary Statistics

| Priority | Category | Tests | Completed | Pending | Estimate |
|----------|----------|-------|-----------|---------|----------|
| 🔴 HIGH | Critical Functional | 4 | 0 | 4 | 60 min |
| 🟡 MEDIUM | Functional Validation | 4 | 0 | 4 | 55 min |
| 🟢 LOW | Stress & Edge Cases | 9 | 0 | 9 | 150 min |
| **TOTAL** | | **17** | **0** | **17** | **~4.5 hrs** |

---

## 🎯 Recommended Test Execution Plan

### Session 1: Core Functionality (60 minutes)
1. Test 0.2: Service Call & Calibration Export
2. Test 2.1: CottonDetect.py Standalone
3. Test 3.2: Service Interface Test
4. Test 4.1: Calibration Export

**Goal**: Validate core detection and calibration functionality

---

### Session 2: Validation & Accuracy (55 minutes)
1. Test 2.2: Signal Communication
2. Test 3.3: Topic Publishing
3. Test 3.4: Debug Image Publishing
4. Test 8.2: Detection Accuracy *(requires physical setup)*

**Goal**: Validate ROS2 integration and accuracy

---

### Session 3: Stress & Robustness (150 minutes)
1. Test 5.1: Repeated Detection (20x)
2. Test 5.2: Long-Duration Stability (30+ min)
3. Test 5.3: USB Cable Length
4. Test 6.1: Subprocess Crash Recovery
5. Test 6.2: Camera Disconnect
6. Test 6.3: Timeout Test
7. Test 7.1: Simulation Mode
8. Test 8.1: Latency Measurement
9. Test 9.1: Integration Test Suite

**Goal**: Validate system robustness and edge cases

---

## 🚨 Blockers & Dependencies

### Missing Items
- [ ] Physical test objects for accuracy validation (Test 8.2)
- [ ] Multiple USB cable lengths: 1m, 3m, 5m (Test 5.3)
- [ ] YOLO model: `/opt/models/cotton_yolov8.onnx` (optional enhancement)

### Prerequisites
- [ ] Performance benchmark script exists and is executable
- [ ] Integration test suite exists and is configured
- [ ] rqt_image_view installed for debug image viewing

---

## 📝 Test Execution Notes

### Before Starting Tests
1. Ensure camera is connected and recognized
2. Source ROS2 environment: `source install/setup.bash`
3. Verify output directories exist and are writable
4. Check available disk space for logs/outputs

### During Testing
- Document any unexpected behavior
- Capture logs for failed tests
- Note performance metrics (CPU, memory, latency)
- Take screenshots of visual outputs (debug images)

### After Testing
- Update this document with results
- Mark completed tests in HARDWARE_TEST_CHECKLIST.md
- Document any issues in GitHub or issue tracker
- Update HARDWARE_TEST_RESULTS document

---

## 🔗 Related Documents

- `docs/HARDWARE_TEST_CHECKLIST.md` - Detailed test procedures
- `docs/HARDWARE_TEST_RESULTS_2025-10-28.md` - Completed test results
- `docs/TEST_COMPLETION_SUMMARY_2025-10-28.md` - Overall test status
- `src/cotton_detection_ros2/README.md` - Detection system documentation

---

**Document Version**: 1.0  
**Created**: 2025-10-28  
**Status**: Active - Ready for Test Execution  
**Next Review**: After completion of HIGH priority tests
