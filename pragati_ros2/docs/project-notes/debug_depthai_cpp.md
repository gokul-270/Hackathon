# DepthAI C++ Detection Debug Report

## Problem Summary
Cotton detection C++ node repeatedly fails with X_LINK_ERROR when reading detections stream.

## Root Cause Found

### Hardware Status ✓
- **Camera**: OAK-D Lite properly connected on RPi (MxID: 18443010513F671200)
- **USB**: USB 3.0 (SUPER speed) ✓
- **DepthAI Library**: v2.28.0.0 installed ✓
- **Blob Model**: `/home/ubuntu/pragati_ros2/data/models/yolov8v2.blob` (5.8MB) ✓

### Pipeline Errors Identified

When testing the detection pipeline with Python, two critical errors occur:

1. **Invalid ROI Rectangles**:
   ```
   [SpatialDetectionNetwork(4)] [warning] ROI x:... y:... width:0 height:0 is not a valid rectangle.
   ```

2. **Metadata Overflow**:
   ```
   [XLinkOut(6)] [error] Message has too much metadata (116396B) to serialize. 
   Maximum is 51200B. Dropping message
   ```

### C++ Code Issues

**File**: `src/cotton_detection_ros2/src/depthai_manager.cpp`

**Line 826**: Uses `YoloSpatialDetectionNetwork` 
**Lines 903-908**: YOLO configuration with anchors:
```cpp
spatialNN->setNumClasses(1);  // Only cotton class
spatialNN->setCoordinateSize(4);
spatialNN->setIouThreshold(0.5);
// YOLOv8 anchors
spatialNN->setAnchors({10,13, 16,30, 33,23, 30,61, 62,45, 59,119, 116,90, 156,198, 373,326});
spatialNN->setAnchorMasks({{"side52", {0,1,2}}, {"side26", {3,4,5}}, {"side13", {6,7,8}}});
```

### The Problem

1. **Wrong Network Type**: `YoloSpatialDetectionNetwork` expects **YOLOv3/v4** format with anchor-based detection
2. **YOLOv8 Uses Anchor-Free Detection**: The blob file is YOLOv8 which doesn't use anchors
3. **Metadata Explosion**: Anchor masks generate excessive detection candidates (116KB+ metadata)
4. **Invalid ROIs**: Anchor-free model output parsed as anchor-based results in 0x0 bounding boxes

## Solution

### Option 1: Use MobileNetSpatialDetectionNetwork (Recommended)

`MobileNetSpatialDetectionNetwork` works with YOLOv8 anchor-free models:

```cpp
// Line 826: Change from YoloSpatialDetectionNetwork to MobileNetSpatialDetectionNetwork
auto spatialNN = pipeline_->create<dai::node::MobileNetSpatialDetectionNetwork>();

// Lines 896-913: Simplified configuration (REMOVE anchor settings)
spatialNN->setBlobPath(model_path_);
spatialNN->setConfidenceThreshold(config_.confidence_threshold);
spatialNN->input.setBlocking(false);
spatialNN->setBoundingBoxScaleFactor(0.5);

if (config_.enable_depth) {
    spatialNN->setDepthLowerThreshold(config_.depth_min_mm);
    spatialNN->setDepthUpperThreshold(config_.depth_max_mm);
}
// REMOVE: setNumClasses, setCoordinateSize, setAnchors, setAnchorMasks, setIouThreshold
```

### Option 2: Convert blob to YOLOv3/v4 format

This requires retraining/converting the model, not recommended.

### Option 3: Use non-spatial YOLO network

Less accurate for 3D positioning, not recommended for this application.

## Testing Commands

### Test on RPi with Python (verified working):
```bash
ssh ubuntu@192.168.137.253
python3 /home/ubuntu/pragati_ros2/test_depthai_python.py
```

### After applying fix, test C++ node:
```bash
ssh ubuntu@192.168.137.253
cd /home/ubuntu/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=false use_depthai:=true
```

## Expected Behavior After Fix

- ✓ No X_LINK_ERROR messages
- ✓ Detections successfully retrieved from stream
- ✓ Metadata size < 51KB
- ✓ Valid bounding boxes (width > 0, height > 0)
- ✓ Detection latency ~120ms (as before)
- ✓ FPS ~0.13 (detection trigger rate, normal for service-based detection)

## Implementation Priority

**CRITICAL** - This blocks all cotton detection functionality in hardware mode.

Apply Option 1 (MobileNetSpatialDetectionNetwork) immediately.
