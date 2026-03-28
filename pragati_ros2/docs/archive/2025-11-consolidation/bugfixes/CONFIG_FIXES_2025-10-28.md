# Configuration Fixes - 2025-10-28

> ℹ️ **HISTORICAL** - Archived Nov 4, 2025  
> These configuration fixes were **VALIDATED** by Nov 1, 2025 testing.  
> All issues resolved and system now production-ready.

## Issues Fixed

### Issue 1: Output Directory Outside Workspace ❌→✅
**Problem**: System was creating `/home/ubuntu/pragati/` directory outside the workspace  
**Root Cause**: Hardcoded path in `cotton_detection_node.cpp` line 343  
**Fix**: Changed to `~/pragati_ros2/outputs/calibration`  

**Before**:
```cpp
calibration_output_dir_ = std::string(home_env) + "/pragati/outputs/calibration";
```

**After**:
```cpp
calibration_output_dir_ = std::string(home_env) + "/pragati_ros2/outputs/calibration";
```

---

### Issue 2: ONNX Model Loading Instead of Blob ❌→✅
**Problem**: Node was trying to load `/opt/models/cotton_yolov8.onnx` (not found)  
**Root Cause**: `yolo_enabled: true` in config and ONNX path configured  
**Fix**: Disabled ONNX YOLO since DepthAI uses blob

**Config Change**:
```yaml
# Before
yolo_enabled: true
yolo_model_path: "/opt/models/cotton_yolov8.onnx"

# After  
yolo_enabled: false  # Disable ONNX YOLO (using DepthAI blob instead)
yolo_model_path: "/opt/models/cotton_yolov8.onnx"  # Not used when DepthAI enabled
```

---

### Issue 3: DepthAI Not Enabled by Default ❌→✅
**Problem**: DepthAI C++ integration disabled, falling back to Python wrapper  
**Root Cause**: `depthai.enable` defaulted to `false` in code (line 286)  
**Fix**: Changed default to `true` and updated blob path

**Code Change**:
```cpp
// Before
this->declare_parameter("depthai.enable", false);
this->declare_parameter("depthai.model_path", 
    "/home/uday/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts/OakDTools/yolov8v2.blob");

// After
this->declare_parameter("depthai.enable", true);  // ✅ Enable by default
this->declare_parameter("depthai.model_path", 
    "~/pragati_ros2/install/cotton_detection_ros2/lib/cotton_detection_ros2/OakDTools/yolov8v2.blob");
```

**Config Change**:
```yaml
depthai:
  enable: true  # ✅ Already set in previous commit
  model_path: "~/pragati_ros2/install/cotton_detection_ros2/lib/cotton_detection_ros2/OakDTools/yolov8v2.blob"
```

---

## Impact

### ✅ Benefits
1. **No confusion** - All outputs stay within workspace
2. **No ONNX warning** - Disabled when not needed
3. **Hardware acceleration** - DepthAI C++ enabled by default
4. **Portable paths** - Works on dev machine and RPi

### 📂 Directory Structure (After Fix)
```
~/pragati_ros2/
├── src/
├── build/
├── install/
│   └── cotton_detection_ros2/
│       └── lib/cotton_detection_ros2/OakDTools/
│           └── yolov8v2.blob  ← Blob file location
└── outputs/  ← ✅ Now created here
    └── calibration/
```

---

## Files Changed

1. **src/cotton_detection_ros2/src/cotton_detection_node.cpp**
   - Line 286: `depthai.enable` default = `true`
   - Line 288: Blob path = install directory
   - Line 343: Output path = `~/pragati_ros2/outputs/`

2. **src/cotton_detection_ros2/config/cotton_detection_cpp.yaml**
   - Line 65: `yolo_enabled: false`
   - Line 85: Blob path = install directory

---

## Testing Required

After these fixes, rebuild and test:

```bash
# Rebuild (clean build recommended)
cd ~/pragati_ros2
colcon build --packages-select cotton_detection_ros2

# Test launch
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=false use_depthai:=true

# Expected logs:
# ✅ No "/home/ubuntu/pragati/outputs" path
# ✅ No ONNX model warning  
# ✅ "Camera: Using DepthAI OAK-D Lite (C++ Direct Integration)"
# ✅ Blob file loaded from install directory
```

---

## Verification Checklist

- [ ] Rebuild completed without errors
- [ ] Launch shows DepthAI C++ integration active
- [ ] No ONNX model warnings
- [ ] Output directory created in `~/pragati_ros2/outputs/`
- [ ] Blob file loads from install directory
- [ ] Service calls work correctly

---

**Date**: 2025-10-28  
**Status**: Fixes Applied - Ready for Rebuild  
**Next**: Rebuild and test on RPi
