# YOLO Model Configuration - ONNX vs Blob

**Date**: 2025-10-28  
**Issue**: Why does cotton detection load ONNX model when blob file exists?  
**Answer**: Two separate detection paths with different model formats

---

## 🎯 TL;DR

**Two independent detection systems:**
1. **OpenCV YOLO (ONNX)** → Software-based detection (CPU/OpenCV DNN)
2. **DepthAI YOLO (Blob)** → Hardware-accelerated detection (Myriad X chip)

---

## 📁 Model Files

### ONNX Model (OpenCV DNN)
- **Path**: `/opt/models/cotton_yolov8.onnx`
- **Format**: ONNX (Open Neural Network Exchange)
- **Used By**: OpenCV DNN module (CPU-based inference)
- **Status**: ❌ **File not found** (optional for HSV fallback)
- **Config Parameter**: `yolo_model_path`

### Blob Model (DepthAI)
- **Path**: `/home/uday/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts/OakDTools/yolov8v2.blob`
- **Format**: Blob (Myriad X compiled format)
- **Used By**: DepthAI API (hardware-accelerated on OAK-D camera)
- **Status**: ✅ **File exists** and working
- **Config Parameter**: `depthai.model_path`

---

## 🔀 Detection Modes

The node supports multiple detection modes configured via `detection_mode` parameter:

### 1. **HSV_ONLY**
- Uses color-based (HSV) detection only
- No YOLO model needed
- Fast but less accurate

### 2. **YOLO_ONLY** 
- Uses ONNX model with OpenCV DNN
- Requires `/opt/models/cotton_yolov8.onnx`
- Software-based inference

### 3. **HYBRID_FALLBACK** (Default)
- Tries YOLO first, falls back to HSV if unavailable
- Current behavior: Falls back to HSV (ONNX not found)

### 4. **DEPTHAI_DIRECT** 
- Uses DepthAI hardware acceleration
- Requires `depthai.enable: true`
- Uses blob model automatically
- **Fastest and most accurate**

---

## ⚙️ Configuration

### Current Configuration (`cotton_detection_cpp.yaml`)

```yaml
# OpenCV YOLO Configuration (Image-based detection)
yolo_enabled: true
yolo_model_path: "/opt/models/cotton_yolov8.onnx"  # ❌ Not found
detection_mode: "hybrid_fallback"  # Falls back to HSV

# DepthAI Configuration (Hardware-accelerated detection)
depthai:
  enable: true  # ✅ Now enabled to use blob file
  model_path: "/home/uday/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts/OakDTools/yolov8v2.blob"  # ✅ Exists
```

---

## 🔧 How to Fix

### Option 1: Enable DepthAI (Recommended) ✅

**Already done!** The config has been updated to:

```yaml
depthai:
  enable: true  # Use hardware-accelerated detection with blob file
```

**Result**: 
- Detection automatically uses DepthAI hardware acceleration
- Blob file is loaded from camera's Myriad X chip
- No ONNX model needed
- Faster inference (hardware accelerated)

---

### Option 2: Disable YOLO (Fallback to HSV)

If you want to use HSV-only detection without YOLO:

```yaml
detection_mode: "hsv_only"
yolo_enabled: false
```

**Result**:
- Pure color-based detection
- No model files needed
- Fast but less accurate

---

### Option 3: Provide ONNX Model (Software YOLO)

If you want to use OpenCV DNN-based detection:

1. Convert YOLOv8 model to ONNX format:
   ```bash
   # Using ultralytics
   yolo export model=yolov8n.pt format=onnx
   ```

2. Place it at `/opt/models/cotton_yolov8.onnx`

3. Verify configuration:
   ```yaml
   yolo_enabled: true
   yolo_model_path: "/opt/models/cotton_yolov8.onnx"
   detection_mode: "yolo_only"  # or "hybrid_fallback"
   ```

**Result**:
- Software-based YOLO inference
- Slower than DepthAI but works without OAK-D camera
- Good for testing/development

---

## 🚀 Recommended Setup

**For Production (OAK-D Lite available):**
```yaml
detection_mode: "hybrid_fallback"  # Auto-switches to depthai_direct
depthai:
  enable: true  # Hardware acceleration ON
  model_path: ".../yolov8v2.blob"  # ✅ Exists
yolo_enabled: false  # Don't need ONNX when using DepthAI
```

**Benefits**:
- Hardware-accelerated detection (fastest)
- Uses existing blob file
- Automatic depth estimation
- Best accuracy

---

## 📊 Performance Comparison

| Mode | Speed | Accuracy | Hardware Required |
|------|-------|----------|-------------------|
| HSV_ONLY | ⚡⚡⚡ Fast | ⭐⭐ Low | None |
| YOLO_ONLY (ONNX) | ⚡ Slow | ⭐⭐⭐ Good | None |
| HYBRID_FALLBACK | ⚡⚡ Medium | ⭐⭐⭐ Good | Optional |
| DEPTHAI_DIRECT (Blob) | ⚡⚡⚡ Very Fast | ⭐⭐⭐⭐ Best | OAK-D Camera |

---

## 🔍 Debug: Check Current Mode

To see which detection mode is active:

```bash
# Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Check logs for:
# "Detection Mode: hybrid_fallback" (or depthai_direct, etc.)
# "YOLO Enabled: yes/no"
# "Camera: Using DepthAI OAK-D Lite (C++ Direct Integration)" ← This means DepthAI active
```

---

## ✅ Resolution Summary

**What was happening:**
- `depthai.enable` was `false` in C++ node
- Node tried to use ONNX model for image-based detection
- ONNX file not found → Fell back to HSV-only
- Blob file existed but wasn't being used

**What changed:**
- Updated `depthai.enable: true` in config
- Now uses DepthAI C++ integration
- Blob file loaded by DepthAI API
- Hardware-accelerated detection active

**Current Status:** ✅ **RESOLVED**
- DepthAI enabled
- Blob file being used
- Hardware acceleration active
- No ONNX warning expected

---

## 📚 Related Files

- Config: `src/cotton_detection_ros2/config/cotton_detection_cpp.yaml`
- Node Code: `src/cotton_detection_ros2/src/cotton_detection_node.cpp` (lines 277, 286-297, 392)
- Blob Model: `src/cotton_detection_ros2/scripts/OakDTools/yolov8v2.blob`
- ONNX Model: `/opt/models/cotton_yolov8.onnx` (not required with DepthAI)

---

**Document Version**: 1.0  
**Status**: Issue Resolved  
**Last Updated**: 2025-10-28
