# Offline Testing Guide

> **⚠️ IMPORTANT:** Production mode (DepthAI direct) runs inference ON the camera hardware.
> The `test_with_images.py` script is NOT compatible with DepthAI direct mode.
> 
> **For offline testing:**
> - Use simulation_mode:=true with synthetic detections
>
> **TODO:** Implement CPU-based YOLO inference for true offline image testing.

**Quick Links:**
- [Complete Testing Guide](../../docs/guides/TESTING_AND_OFFLINE_OPERATION.md)

---

## Legacy Content (For Reference - HSV mode only)

Test the cotton detection system without a live camera using saved images!

## Quick Start

### 1. Start the Detection Node

```bash
# Terminal 1: Start the C++ detection node
cd ~/Downloads/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false
```

> ℹ️ The detection pipeline runs in C++, but the helper script below is Python-based to make it easy to publish test images into the node.

### 2. Test with Your Images

```bash
# Terminal 2: Test with images
cd ~/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts

# Single image
python3 test_with_images.py --image /path/to/cotton.jpg --visualize

# Directory of images
python3 test_with_images.py --dir /path/to/images/ --visualize --output results.json
```

## Usage Examples

### Test Single Image
```bash
python3 test_with_images.py --image cotton_sample.jpg --visualize
```
- Publishes image to `/camera/image_raw`
- Waits for detection results
- Shows bounding boxes and confidence scores

### Test Multiple Images
```bash
python3 test_with_images.py --dir test_images/ --output results.json
```
- Tests all images in directory (jpg, png, bmp, tiff)
- Saves results to JSON file
- Prints summary statistics

### Batch Testing with Visualization
```bash
python3 test_with_images.py --dir test_images/ --visualize --display-time 3000
```
- Shows each detection for 3 seconds
- Green boxes = detected cotton
- Confidence scores displayed

### Custom Timeout
```bash
python3 test_with_images.py --image slow_test.jpg --timeout 10.0
```
- Waits up to 10 seconds for detection
- Useful for complex images or slow processing

## Alternative Methods

### Method 1: Use ROS2 Image Tools
```bash
# Install image_tools if not available
sudo apt install ros-jazzy-image-tools

# Publish single image (loop mode)
ros2 run image_tools cam2image --ros-args \
    -p filename:=/path/to/image.jpg \
    -r image:=/camera/image_raw

# Detection node will process it continuously
```

### Method 2: Use image_publisher
```bash
# Install image_publisher
sudo apt install ros-jazzy-image-publisher

# Publish image at 10 Hz
ros2 run image_publisher image_publisher_node /path/to/image.jpg \
    --ros-args -r image_raw:=/camera/image_raw -p frequency:=10.0
```

### Method 3: Play from ROS Bag
```bash
# Record a bag with camera images
ros2 bag record /camera/image_raw

# Play back later for testing
ros2 bag play your_bag.db3
```

### Method 4: Video File Testing
```bash
# Use video_file node (if available)
ros2 run image_tools video_file_publisher --ros-args \
    -p filename:=/path/to/video.mp4 \
    -r image:=/camera/image_raw
```

## Output Format

### Console Output
```
Found 5 image(s) to test

[1/5] Testing: cotton_001.jpg
Publishing image: cotton_001.jpg (640x480)
Received 3 detections for cotton_001.jpg
  Detection 0: confidence=0.87, pos=(320, 240)

...

============================================================
TEST SUMMARY
============================================================
Total images tested: 5
Images with detections: 4 (80.0%)
Total detections: 12
Average detections per image: 2.40
============================================================

Per-Image Results:
  ✓ cotton_001.jpg: 3 detection(s)
  ✓ cotton_002.jpg: 2 detection(s)
  ✗ cotton_003.jpg: 0 detection(s)
  ✓ cotton_004.jpg: 4 detection(s)
  ✓ cotton_005.jpg: 3 detection(s)
```

### JSON Output (results.json)
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

## Creating Test Images

### From Existing Camera
```bash
# Capture images from camera
ros2 run image_view image_saver --ros-args \
    -r image:=/camera/image_raw

# Or use OpenCV
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
cv2.imwrite('test_cotton.jpg', frame)
cap.release()
"
```

### Download Sample Dataset
```bash
# Example: Download cotton detection dataset
mkdir -p test_images
cd test_images

# Add your own images or download from dataset
# wget https://example.com/cotton_dataset.zip
# unzip cotton_dataset.zip
```

### Create Synthetic Test Images
```bash
# Use simulation mode to generate test data
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true publish_debug_images:=true

# Subscribe to debug images
ros2 run image_view image_saver --ros-args \
    -r image:=/cotton_detection/debug_image
```

## Regression Testing

### Create Baseline Results
```bash
# Test with known good images
python3 test_with_images.py --dir baseline_images/ --output baseline_results.json

# This becomes your "ground truth"
```

### Compare After Changes
```bash
# Test after code changes
python3 test_with_images.py --dir baseline_images/ --output new_results.json

# Compare results
python3 -c "
import json

with open('baseline_results.json') as f:
    baseline = json.load(f)
with open('new_results.json') as f:
    new = json.load(f)

for img in baseline:
    if img in new:
        b_count = baseline[img]['num_detections']
        n_count = new[img]['num_detections']
        if b_count != n_count:
            print(f'CHANGED: {img}: {b_count} -> {n_count}')
"
```

## Performance Testing

### Measure Detection Latency
```bash
# Add timing information
python3 test_with_images.py --dir test_images/ --output timing.json

# Calculate average latency
python3 -c "
import json
with open('timing.json') as f:
    results = json.load(f)
    
latencies = []
for img, data in results.items():
    if 'timestamp' in data:
        # Add latency calculation if needed
        pass
        
print(f'Average latency: {sum(latencies)/len(latencies):.3f}s')
"
```

### Test with Different Image Sizes
```bash
# Create different resolution versions
for size in 320x240 640x480 1280x720 1920x1080; do
    mkdir -p test_${size}
    for img in test_images/*.jpg; do
        convert $img -resize $size test_${size}/$(basename $img)
    done
    
    echo "Testing $size..."
    python3 test_with_images.py --dir test_${size}/ --output results_${size}.json
done
```

## Troubleshooting

### No Detections Received
```bash
# 1. Check detection node is running
ros2 node list | grep cotton_detection

# 2. Check topics
ros2 topic list | grep cotton

# 3. Monitor image publishing
ros2 topic hz /camera/image_raw

# 4. Check detection results
ros2 topic echo /cotton_detection/results --once

# 5. Increase timeout
python3 test_with_images.py --image test.jpg --timeout 10.0
```

### Image Format Issues
```bash
# Convert image to supported format
convert input.webp output.jpg

# Ensure RGB/BGR format
python3 -c "
import cv2
img = cv2.imread('test.jpg')
cv2.imwrite('test_bgr.jpg', img)
"
```

### Low Detection Accuracy
```bash
# 1. Check HSV thresholds in config
ros2 param get /cotton_detection_node cotton_detection.hsv_lower_bound
ros2 param get /cotton_detection_node cotton_detection.hsv_upper_bound

# 2. Test with visualization to see what's being detected
python3 test_with_images.py --image test.jpg --visualize

# 3. Try different detection modes
# Edit config/production.yaml:
#   detection_mode: "hsv_only"  # or "yolo_only", "hybrid_fallback"
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Detection Tests

on: [push, pull_request]

jobs:
  test-detection:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build ROS2 workspace
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon build --packages-select cotton_detection_ros2
      
      - name: Run offline tests
        run: |
          source install/setup.bash
          ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false &
          sleep 5
          python3 src/cotton_detection_ros2/test/test_with_images.py \
            --dir test_images/ --output results.json
          
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: test-results
          path: results.json
```

## Benefits of Offline Testing

✅ **No Hardware Required**
- Test without OAK-D Lite camera
- Develop on any machine
- CI/CD pipeline integration

✅ **Reproducible Results**
- Same images every time
- Consistent test conditions
- Track performance over time

✅ **Faster Development**
- No hardware setup time
- Quick iteration cycles
- Parallel testing possible

✅ **Regression Detection**
- Compare against baseline
- Catch performance regressions
- Validate bug fixes

✅ **Dataset Benchmarking**
- Test against standard datasets
- Compare with other methods
- Publish research results

---

**Ready to test?** Just run:
```bash
python3 test_with_images.py --image your_cotton_image.jpg --visualize
```
