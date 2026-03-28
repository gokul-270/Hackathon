# Cotton Detection Fixes - October 31, 2025

## Issues Fixed

### 1. ❌ **Hardcoded absolute paths** → ✅ Portable HOME-based paths
**Problem**: Config file had hardcoded `/home/ubuntu/pragati_ros2/data/...` paths that failed when code was copied to different machines.

**Solution**: 
- Modified `src/cotton_detection_ros2/config/cotton_detection_cpp.yaml`
- Changed `input_dir` and `output_dir` from hardcoded paths to empty strings (`""`)
- Node now uses C++ defaults: `$HOME/pragati_ros2/data/inputs` and `$HOME/pragati_ros2/data/outputs`
- Works automatically on any machine without code changes!

### 2. ❌ **Stale/cached images** → ✅ Fresh frame guarantee
**Problem**: Service calls used whatever image was in the buffer, causing delayed/stale detections. If you removed cotton between calls, it would still detect the old scene.

**Solution**:
- Added `latest_image_stamp_` member variable to track image timestamps
- Modified image callbacks to store frame timestamps
- Service handler now waits up to 1.5 seconds for a fresh frame (captured after the service call)
- Logs show: "⏳ Waiting for fresh camera frame..." and "✅ Got fresh frame (captured X ms after request)"

**Files Changed**:
- `src/cotton_detection_ros2/include/cotton_detection_ros2/cotton_detection_node.hpp`
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp` (callbacks and service handler)

### 3. ❌ **Input images not saved when no detection** → ✅ Always save inputs
**Problem**: When no cotton was detected, neither input nor output images were saved, making debugging difficult.

**Solution**:
- Image-based detection path: Added input image saving at the start (before detection runs)
- DepthAI detection path: Modified to save input always, output only when detections exist
- **Input images**: Always saved as `img100.jpg` (even when no detections)
- **Output images**: Only saved as `DetectionOutput.jpg` when cotton is detected

**File Changed**:
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp`

---

## Testing Instructions

### Quick Test
```bash
# Run the test script
cd /home/uday/Downloads/pragati_ros2
./test_cotton_detection_fixes.sh
```

### Manual Testing

**Terminal 1 - Launch Node:**
```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

**Terminal 2 - Run Tests:**

**Test 1: Portable Paths**
```bash
# After running the node, verify directories are created:
ls -ld ~/pragati_ros2/data/inputs
ls -ld ~/pragati_ros2/data/outputs
# Should work on both your dev PC (/home/uday/) and Raspberry Pi (/home/ubuntu/)
```

**Test 2: Fresh Frames (No Stale Images)**
```bash
# Place cotton in camera view
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
# Output: Shows detections

# Remove cotton from view
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
# Output: Should show NO detections (not stale results)
# Logs: Look for "⏳ Waiting for fresh camera frame..." and "✅ Got fresh frame"
```

**Test 3: Always Save Input Images**
```bash
# Make sure NO cotton is visible
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Check input image was saved (even with no detections):
ls -lh ~/pragati_ros2/data/inputs/
# Should see: img100.jpg

# Check NO output image was saved:
ls -lh ~/pragati_ros2/data/outputs/
# Should be empty or not exist (since no detections)
```

---

## Expected Behavior Summary

✅ **Directories**: Auto-created at `$HOME/pragati_ros2/data/inputs` and `outputs`  
✅ **Fresh Frames**: Service waits for new frame after request (logs show timing)  
✅ **Input Images**: ALWAYS saved as `img100.jpg`  
✅ **Output Images**: ONLY saved as `DetectionOutput.jpg` when cotton detected  

---

## Files Modified

1. `src/cotton_detection_ros2/config/cotton_detection_cpp.yaml`
   - Lines 138-139: Set `input_dir` and `output_dir` to `""`

2. `src/cotton_detection_ros2/include/cotton_detection_ros2/cotton_detection_node.hpp`
   - Line 143: Added `rclcpp::Time latest_image_stamp_`

3. `src/cotton_detection_ros2/src/cotton_detection_node.cpp`
   - Lines 894, 911: Store timestamp in image callbacks
   - Lines 947-984: Wait for fresh frame in service handler
   - Lines 1264-1267: Always save input image in image-based path
   - Lines 1212-1215: Only save output when detections exist in DepthAI path

---

## Build Commands

```bash
cd /home/uday/Downloads/pragati_ros2
rm -rf build/cotton_detection_ros2 install/cotton_detection_ros2
colcon build --packages-select cotton_detection_ros2 --symlink-install
source install/setup.bash
```

---

## Deployment to Raspberry Pi

1. Copy the entire `pragati_ros2` directory to Raspberry Pi
2. Build on Raspberry Pi:
   ```bash
   cd ~/pragati_ros2
   colcon build --packages-select cotton_detection_ros2 --symlink-install
   source install/setup.bash
   ```
3. Paths will automatically resolve to `/home/ubuntu/pragati_ros2/data/`
4. No code or config changes needed!

---

## Notes

- **Backward Compatible**: All changes are backward compatible
- **Performance**: Fresh frame wait adds ~30-100ms latency (acceptable for service-based detection)
- **Storage**: Input images overwrite each other (`img100.jpg`), so only the latest is kept
- **Debugging**: Can now debug "no detection" cases by examining saved input images

---

*Fixes implemented: October 31, 2025*  
*Tested on: Ubuntu (development PC)*  
*Ready for: Raspberry Pi deployment*
