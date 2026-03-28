# Hardware Test Results - 2025-10-30

**Date**: October 30, 2025  
**Test Duration**: ~3 hours  
**Goal**: Enable DepthAI C++ for < 2.5s detection cycle time

---

## ✅ SETUP PHASE - COMPLETE

### Installation (15 min target → 45 min actual)

**Completed:**
- [x] DepthAI C++ packages installed (`ros-jazzy-depthai`, `ros-jazzy-depthai-bridge`)
- [x] Built with `HAS_DEPTHAI=ON`
- [x] Library verified: `libdepthai_manager.so` exists
- [x] YOLO models present: `yolov8v2.blob` in correct location
- [x] Camera detected: `lsusb | grep 03e7` → Intel Movidius MyriadX

**Issues Fixed:**
1. ❌ Pipeline error: "StereoDepth input 'left' must be connected"
   - ✅ Fixed: Added mono camera nodes and linked to stereo depth
2. ❌ Model path incorrect (using local PC path instead of RPi)
   - ✅ Fixed: Updated to `/home/ubuntu/pragati_ros2/install/.../models/yolov8v2.blob`
3. ❌ Fallback to Python wrapper causing confusion
   - ✅ Fixed: Removed fallback, node now crashes if DepthAI fails

---

## 📊 SESSION 1: Detection Validation - PARTIAL

### Test 1.1: Basic Detection

**Status**: ⚠️ DepthAI initializes but detection slow

```bash
# System Launch
ros2 launch yanthra_move pragati_complete.launch.py
```

**Results:**
- [x] DepthAI C++ initializes successfully
- [x] Pipeline builds: `Pipeline build SUCCESS`
- [x] Device connects: `Device MxID: 18443010513F671200, USB 3.0 (5Gbps)`
- [x] Mode: `DEPTHAI_DIRECT (using C++ DepthAI pipeline)`
- [ ] ❌ **Detection time: 6.3-6.5s** (Target: < 200ms)
- [ ] ❌ **Detection fails** (no cotton in view)

**Logs Confirm:**
```
[DepthAIManager::Impl] Pipeline build SUCCESS
[DepthAIManager] Device connected
[DepthAIManager] Initialization successful
✅ DepthAI initialization SUCCESS
🔀 Detection mode: DEPTHAI_DIRECT
```

### Test 1.2: Performance Timing
**Status**: ❌ NOT TESTED - Detection too slow to proceed

### Test 1.3: End-to-End Timing
**Status**: ❌ NOT TESTED

---

## 🔍 CURRENT ISSUES

### Issue #1: Slow Detection Performance ⚠️ CRITICAL

**Expected**: 100-150ms  
**Actual**: 6,300-6,500ms (~6.3s)  
**Gap**: **40-65x slower than target**

**Symptoms:**
- DepthAI initializes correctly
- Pipeline builds successfully
- Device connects properly
- But detection service takes 6.3s to respond

**Hypothesis:**
- DepthAI is initialized but detection logic may not be using the fast path
- Possible timeout/waiting in detection service handler
- May be processing frames sequentially instead of using on-device YOLO

**Next Steps:**
1. Add detailed timing logs in `handle_detection_request()`
2. Verify DepthAI `getDetections()` is being called
3. Check if node is waiting for image topics instead of using DepthAI direct
4. Profile the detection service execution path

### Issue #2: No Cotton Detections

**Status**: Expected - no cotton in camera view  
**Action**: Need to place cotton sample for testing

---

## 📈 PERFORMANCE METRICS

### Detection Latency
- **Measured**: 6,350ms average (3 samples)
- **Target**: < 200ms
- **Status**: ❌ **FAILED** (31x slower than target)

### Motor Response
- **Status**: Not tested yet

### Total Cycle Time  
- **Status**: Not measured yet (detection blocking)

---

## ✅ SUCCESS CRITERIA STATUS

### Must Pass:
- [x] ✅ DepthAI C++ integration working on RPi
- [ ] ❌ Detection time < 200ms (currently 6,350ms)
- [ ] ⏸️ Motor response < 50ms (not tested)
- [ ] ⏸️ Complete pick cycle < 2.5s per cotton (not tested)
- [ ] ⏸️ 10 consecutive picks succeed (not tested)

### Nice to Have:
- [ ] ⏸️ Detection accuracy ±5cm at 1m
- [ ] ⏸️ 50 rapid detections without failure
- [ ] ⏸️ Debug images published correctly
- [ ] ⏸️ Calibration export working

---

## 🔧 CHANGES MADE

### Code Changes:
1. **depthai_manager.cpp**
   - Added mono camera nodes (left/right)
   - Connected mono cameras to stereo depth node
   - Fixed pipeline configuration

2. **cotton_detection_node.cpp**
   - Removed Python wrapper fallback
   - Made DepthAI failure fatal (node crashes)
   - Forces DEPTHAI_DIRECT mode

3. **cotton_detection_cpp.yaml**
   - Set `detection_mode: "depthai_direct"` as default
   - Fixed model path to absolute RPi path

4. **pragati_complete.launch.py**
   - Changed to use `cotton_detection_cpp.launch.py`
   - Uses C++ DepthAI instead of Python wrapper

5. **test_full_pipeline.sh**
   - Updated to 1 cycle only
   - Fixed camera ready detection (looks for DepthAI SUCCESS)

---

## 📝 RECOMMENDATIONS

### Immediate (Debug Performance):
1. **Add timing instrumentation**
   - Log timestamps at each step in detection handler
   - Measure `depthai_manager_->getDetections()` call time
   - Check if waiting on topics/services

2. **Verify fast path is used**
   - Confirm `DEPTHAI_DIRECT` mode is active during detection
   - Check that image topic subscriptions are not blocking
   - Verify YOLO runs on Myriad X chip, not CPU

3. **Test with cotton sample**
   - Place cotton in view to verify actual detections work
   - Measure detection time with real objects

### Next Session:
1. Continue once detection performance is optimized to < 200ms
2. Then proceed with motor integration tests
3. Then full system validation

---

## 🎯 OVERALL STATUS

**Progress**: 30% Complete

**What Works:**
- ✅ DepthAI C++ installation
- ✅ Pipeline configuration
- ✅ Device initialization
- ✅ No fallback confusion
- ✅ Camera detection

**What Needs Work:**
- ❌ Detection performance (6.3s → need < 200ms)
- ⏸️ Motor integration testing
- ⏸️ End-to-end validation
- ⏸️ Performance benchmarking

**Estimated Time to Complete:**
- Fix detection performance: 2-4 hours
- Complete remaining tests: 2-3 hours
- **Total**: 4-7 hours additional work

---

## 📅 NEXT STEPS

1. **Debug detection slowness** (HIGH PRIORITY)
   - Add detailed logging
   - Profile detection service
   - Verify DepthAI fast path

2. **Test with cotton sample**
   - Validate actual detections work
   - Measure with real objects

3. **Resume test checklist**
   - Once detection < 200ms
   - Continue with Session 2-4

**Status**: Paused at Session 1.1 - awaiting performance fix
