# Offline Testing - Quick Start Guide

**You're right!** The system already has full offline testing capabilities. No DepthAI hardware needed!

---

## 🚀 Quick Start (30 seconds)

### Terminal 1: Start Detection Node
```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false
```

### Terminal 2: Test with Your Images
```bash
cd ~/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts
python3 test_with_images.py --image /path/to/your/cotton_image.jpg --visualize
```

That's it! ✅

---

## 📁 What's Already Available

### ✅ Offline Detection Modes
1. **HSV-based detection** - Color segmentation (no ML model needed)
2. **YOLO detection** - Using OpenCV DNN (no DepthAI hardware)
3. **Hybrid mode** - Combines both methods

### ✅ Testing Tools
- **test_with_images.py** - Main testing script
- **test_cotton_detection.py** - Additional test utilities
- **OFFLINE_TESTING.md** - Complete documentation

### ✅ Launch Options
```bash
# Image-based detection (no hardware)
use_depthai:=false

# Simulation mode (synthetic detections)
simulation_mode:=true

# Debug visualization
debug_output:=true
```

---

## 💡 Common Use Cases

### 1. Test Single Image with Visualization
```bash
python3 test_with_images.py \
    --image cotton_sample.jpg \
    --visualize
```
**Output:** Shows detections with green bounding boxes and confidence scores

### 2. Batch Test Directory
```bash
python3 test_with_images.py \
    --dir test_images/ \
    --output results.json
```
**Output:** JSON file with all detection results + summary statistics

### 3. Regression Testing
```bash
# Create baseline
python3 test_with_images.py --dir baseline/ --output baseline.json

# Test after changes
python3 test_with_images.py --dir baseline/ --output new.json

# Compare (shows any differences)
diff baseline.json new.json
```

### 4. Performance Benchmarking
```bash
python3 test_with_images.py \
    --dir large_dataset/ \
    --output timing.json \
    --timeout 10.0
```

---

## 🎯 Detection Modes Explained

### HSV-Only Mode (No ML needed)
```yaml
# config/cotton_detection_cpp.yaml
cotton_detection:
  detection_mode: "hsv_only"
  hsv_lower_bound: [0, 50, 50]    # H,S,V lower threshold
  hsv_upper_bound: [180, 255, 255] # H,S,V upper threshold
```
**Best for:** Fast detection, known lighting conditions, simple backgrounds

### YOLO-Only Mode (OpenCV DNN)
```yaml
cotton_detection:
  detection_mode: "yolo_only"
  yolo_confidence_threshold: 0.5
```
**Best for:** Complex backgrounds, varying lighting, ML-trained accuracy

### Hybrid Fallback (Recommended)
```yaml
cotton_detection:
  detection_mode: "hybrid_fallback"
```
**Best for:** Robust detection - tries YOLO first, falls back to HSV

---

## 📊 Expected Output

### Console Output Example
```
[INFO] [cotton_detection_node]: Detection node initialized
[INFO] [cotton_detection_node]: Using detection mode: hybrid_fallback
[INFO] [image_test_publisher]: Publishing image: cotton_001.jpg (640x480)
[INFO] [cotton_detection_node]: Processing frame...
[INFO] [cotton_detection_node]: Found 3 detections (YOLO)
[INFO] [image_test_publisher]: Received 3 detections for cotton_001.jpg
[INFO] [image_test_publisher]:   Detection 0: confidence=0.87, pos=(320, 240)

============================================================
TEST SUMMARY
============================================================
Total images tested: 5
Images with detections: 4 (80.0%)
Total detections: 12
Average detections per image: 2.40
============================================================
```

### JSON Output Example
```json
{
  "cotton_001.jpg": {
    "num_detections": 3,
    "detections": [
      {
        "confidence": 0.87,
        "bbox": {
          "center_x": 320.0,
          "center_y": 240.0,
          "size_x": 80.0,
          "size_y": 60.0
        },
        "position_3d": {
          "x": 0.32,
          "y": -0.15,
          "z": 0.5
        }
      }
    ],
    "timestamp": 1696789234.567
  }
}
```

---

## 🔧 Configuration Files

### Main Config
`config/cotton_detection_cpp.yaml` - All detection parameters

### Key Parameters
```yaml
cotton_detection:
  # Detection mode
  detection_mode: "hybrid_fallback"  # hsv_only, yolo_only, hybrid_*
  
  # HSV thresholds (for cotton white color)
  hsv_lower_bound: [0, 0, 180]      # Very light colors
  hsv_upper_bound: [180, 50, 255]    # White-ish range
  
  # YOLO settings
  yolo_confidence_threshold: 0.5
  yolo_nms_threshold: 0.4
  
  # Morphology (noise reduction)
  morphology_kernel_size: 5
  morphology_iterations: 2
  
  # Size filtering
  min_contour_area: 100.0
  max_contour_area: 50000.0
```

---

## 🐛 Troubleshooting

### Problem: No detections received
**Solution:**
```bash
# Check node is running
ros2 node list | grep cotton_detection

# Check topics
ros2 topic list | grep cotton

# Increase timeout
python3 test_with_images.py --image test.jpg --timeout 10.0
```

### Problem: Low detection accuracy
**Solution:**
```bash
# Try different detection modes
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=false \
    detection_mode:=hsv_only  # or yolo_only, hybrid_fallback

# Adjust HSV thresholds for your lighting
# Edit config/cotton_detection_cpp.yaml
```

### Problem: Image format not supported
**Solution:**
```bash
# Convert to supported format
convert input.png output.jpg

# Supported: jpg, jpeg, png, bmp, tiff
```

---

## ✅ What This Means for Your Testing

### You Can Test Right Now!
- ✅ No DepthAI hardware needed
- ✅ No camera needed
- ✅ Works on any Linux/Mac/Windows machine
- ✅ Perfect for CI/CD pipelines
- ✅ Regression testing ready
- ✅ Dataset benchmarking ready

### Phase 1 (Hardware Integration) Can Wait
- The offline testing infrastructure is **complete**
- You can develop and test algorithms **without hardware**
- Hardware testing validates **real-world performance**, but:
  - Algorithm development ✅ Works offline
  - Parameter tuning ✅ Works offline
  - Regression testing ✅ Works offline
  - CI/CD integration ✅ Works offline

---

## 🎓 Advanced Usage

### Create Test Dataset
```bash
# Capture images from existing camera
ros2 run image_view image_saver --ros-args -r image:=/camera/image_raw

# Or use OpenCV
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
for i in range(10):
    ret, frame = cap.read()
    cv2.imwrite(f'test_{i:03d}.jpg', frame)
cap.release()
"
```

### Use ROS Bags
```bash
# Record camera data
ros2 bag record /camera/image_raw /cotton_detection/results

# Play back for testing
ros2 bag play your_recording.db3
```

### CI/CD Integration
```yaml
# .github/workflows/test.yml
- name: Test cotton detection
  run: |
    source install/setup.bash
    ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false &
    sleep 3
    python3 scripts/test_with_images.py --dir test_images/ --output results.json
```

---

## 📚 Full Documentation

For complete details, see:
- **OFFLINE_TESTING.md** - Complete offline testing guide
- **config/README.md** - Configuration reference
- **docs/COTTON_DETECTION_GUIDE.md** - Algorithm details

---

## 🎯 Summary

**You don't need hardware to start testing!**

The system already has:
- ✅ Offline detection modes (HSV + YOLO with OpenCV)
- ✅ Image testing scripts
- ✅ Batch processing
- ✅ Visualization
- ✅ JSON output
- ✅ CI/CD ready

**Just run:**
```bash
# Terminal 1
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false

# Terminal 2
python3 test_with_images.py --image your_image.jpg --visualize
```

**That's all you need!** 🚀
