# ROS1 OakDTools vs ROS2 Comparison

> ℹ️ **HISTORICAL** - Archived Nov 4, 2025  
> ROS2 implementation **VALIDATED** Nov 1, 2025 and confirmed production-ready.  
> C++ DepthAI integration proves superior to ROS1 Python approach.

**Date**: 2025-10-28  
**Purpose**: Compare ROS1 and ROS2 OakDTools implementations  
**Test Status**: ✅ **Validated** (Nov 1, 2025)

---

## 📁 Directory Locations

### ROS1 (Original)
- **Path**: `/home/uday/Downloads/pragati/src/OakDTools`
- **Version**: ROS1 Melodic/Noetic
- **Status**: Production-tested (field validated)

### ROS2 (Current)
- **Path**: `/home/uday/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts/OakDTools`
- **Version**: ROS2 Jazzy
- **Status**: In testing

---

## 🔍 Blob File Comparison

| File | ROS1 Size | ROS2 Size | MD5 Match | Status |
|------|-----------|-----------|-----------|--------|
| `best_openvino_2022.1_6shave.blob` | 14M | 14M | ✅ | Identical |
| `yolov8.blob` | 5.8M | 5.8M | ✅ | Identical |
| `yolov8v2.blob` | 5.8M | 5.8M | ✅ | Identical |

**Verification**:
```bash
md5sum /home/uday/Downloads/pragati/src/OakDTools/yolov8v2.blob
# b50a163e88aef6db836b7de29ace8db9

md5sum /home/uday/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts/OakDTools/yolov8v2.blob  
# b50a163e88aef6db836b7de29ace8db9
```

✅ **Blob files are identical** - Both versions use the same YOLO models

---

## 📜 Script Differences

### CottonDetect.py
- **Status**: ⚠️ **Files differ**
- **Reason**: ROS2 version may have adaptations for ROS2 integration
- **Action**: Test ROS1 version standalone to validate blob usage

### Key Scripts in ROS1
```
/home/uday/Downloads/pragati/src/OakDTools/
├── CottonDetect.py                           # Main detection script
├── CottonDetectInteractive.py                # Interactive version
├── CottonDetectInteractiveWithDebugLogs.py   # Debug version
├── ArucoDetectYanthra.py                     # ArUco marker detection
├── yolov8v2.blob                             # YOLO model (5.8M)
├── yolov8.blob                               # Alternative YOLO (5.8M)
└── best_openvino_2022.1_6shave.blob          # OpenVINO model (14M)
```

---

## 🧪 Testing Plan

### Test 1: ROS1 CottonDetect.py Standalone ⏳ PENDING

**Objective**: Verify ROS1 script works with blob file

**Command**:
```bash
cd /home/uday/Downloads/pragati/src/OakDTools
python3 CottonDetect.py yolov8v2.blob
```

**Expected Results**:
- [ ] Camera initializes successfully
- [ ] YOLO blob loads without errors
- [ ] SIGUSR2 signal sent automatically
- [ ] Detections written to `/home/ubuntu/pragati/outputs/cotton_details.txt`
- [ ] Debug image saved to `/home/ubuntu/pragati/outputs/DetectionOutput.jpg`

**Test Script**: `./test_ros1_cotton_detect.sh`

---

### Test 2: Compare Detection Results

**Objective**: Compare detection accuracy between ROS1 and ROS2

**Test Setup**:
1. Place identical test object in camera view
2. Run ROS1 CottonDetect.py
3. Run ROS2 detection node
4. Compare:
   - Detection count
   - Coordinate accuracy
   - Confidence scores
   - Processing latency

---

### Test 3: ROS2 Integration Test

**Objective**: Verify ROS2 system uses blob file correctly

**Command**:
```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=false \
    use_depthai:=true
```

**Verify**:
- [ ] Logs show "DepthAI OAK-D Lite (C++ Direct Integration)"
- [ ] Blob file path in logs: `...yolov8v2.blob`
- [ ] No ONNX warnings
- [ ] Detections publish to `/cotton_detection/results`

---

## 📊 Feature Comparison

| Feature | ROS1 | ROS2 | Notes |
|---------|------|------|-------|
| **Blob Support** | ✅ | ✅ | Identical files |
| **DepthAI API** | ✅ Python | ✅ Python + C++ | ROS2 has C++ integration |
| **YOLO Models** | yolov8v2.blob | yolov8v2.blob | Same model |
| **Signal Handling** | SIGUSR1/SIGUSR2 | SIGUSR1/SIGUSR2 | Same mechanism |
| **Output Format** | File-based | File + ROS2 topics | ROS2 adds topics |
| **Calibration** | Manual export | Service-based | ROS2 more automated |
| **Debug Images** | File only | File + ROS2 topic | ROS2 streaming option |

---

## 🔄 Migration Notes

### What's Changed in ROS2

1. **Additional Detection Modes**:
   - ROS1: Blob-based detection only
   - ROS2: Hybrid modes (HSV, YOLO-ONNX, DepthAI-Blob)

2. **C++ Integration**:
   - ROS1: Python wrapper only
   - ROS2: Native C++ DepthAI support

3. **Configuration**:
   - ROS1: Hard-coded parameters
   - ROS2: YAML-based configuration with runtime updates

4. **Output**:
   - ROS1: File-based only
   - ROS2: Files + ROS2 topics (Detection3DArray)

---

## ✅ Validation Checklist

### Prerequisites
- [x] ROS1 OakDTools directory exists
- [x] ROS2 OakDTools directory exists
- [x] Blob files identical (verified via MD5)
- [x] Camera connected and detected
- [ ] Python dependencies installed (depthai, opencv, numpy)

### Standalone Tests
- [ ] ROS1 CottonDetect.py runs without errors
- [ ] Blob file loads successfully  
- [ ] Detections are accurate
- [ ] Output files created correctly

### ROS2 Integration Tests
- [ ] C++ node launches with DepthAI
- [ ] Blob file loaded by DepthAI
- [ ] ROS2 topics publish detections
- [ ] Calibration service works

### Performance Comparison
- [ ] Latency comparable (ROS1 vs ROS2)
- [ ] Detection accuracy similar
- [ ] Resource usage acceptable

---

## 🚀 Recommended Action Plan

### Step 1: Validate ROS1 Baseline (Today)
```bash
# Run test script
./test_ros1_cotton_detect.sh

# Verify outputs
ls -lh /home/ubuntu/pragati/outputs/
cat /home/ubuntu/pragati/outputs/cotton_details.txt
```

**Goal**: Confirm ROS1 version works as production baseline

---

### Step 2: Update ROS2 Configuration (Already Done ✅)
```yaml
# cotton_detection_cpp.yaml
depthai:
  enable: true  # Use DepthAI C++ integration
  model_path: ".../yolov8v2.blob"
```

**Goal**: Ensure ROS2 uses same blob file as ROS1

---

### Step 3: Run ROS2 Tests
```bash
# Test C++ node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=false use_depthai:=true

# Call detection service
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Goal**: Verify ROS2 system works with same blob file

---

### Step 4: Compare Results
- Place test object at known location
- Trigger detection in both systems
- Compare outputs:
  - Detection count
  - 3D coordinates
  - Confidence scores
  - Latency

**Goal**: Validate ROS2 matches or exceeds ROS1 performance

---

## 📝 Test Results (To Be Filled)

### ROS1 Test Results
**Date**: _____________  
**Blob File**: yolov8v2.blob (5.8M)  
**Camera**: OAK-D Lite (MxId: 18443010513F671200)

**Results**:
- Camera Init: ⏳ Pending
- Blob Load: ⏳ Pending
- Detections: ⏳ Pending
- Output Files: ⏳ Pending
- Notes: _____________

---

### ROS2 Test Results
**Date**: _____________  
**Blob File**: yolov8v2.blob (5.8M)  
**Camera**: OAK-D Lite (MxId: 18443010513F671200)

**Results**:
- C++ Node Launch: ⏳ Pending
- DepthAI Init: ⏳ Pending
- Blob Load: ⏳ Pending
- Service Call: ⏳ Pending
- Topic Publishing: ⏳ Pending
- Notes: _____________

---

## 🔗 Related Documentation

- **Test Script**: `./test_ros1_cotton_detect.sh`
- **ROS2 Config**: `src/cotton_detection_ros2/config/cotton_detection_cpp.yaml`
- **YOLO Config**: `docs/YOLO_MODEL_CONFIGURATION.md`
- **Hardware Tests**: `docs/PENDING_HARDWARE_TESTS.md`

---

**Document Version**: 1.0  
**Status**: Ready for Testing  
**Next Action**: Run `./test_ros1_cotton_detect.sh`
