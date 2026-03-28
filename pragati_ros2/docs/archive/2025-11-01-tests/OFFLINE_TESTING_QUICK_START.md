# Offline Image Testing - Quick Start

Test cotton detection with saved images **without any hardware**! 🎉

## TL;DR

```bash
# Terminal 1: Start detection (simulation mode)
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false

# Terminal 2: Test images
./test_offline_images.sh my_image.jpg --visualize
```

---

## Why Offline Testing?

- ✅ **No hardware needed** - Test anytime, anywhere
- ✅ **Fast iteration** - Test detection logic changes instantly
- ✅ **Regression testing** - Verify changes don't break existing behavior
- ✅ **Benchmarking** - Compare performance across different images
- ✅ **Debugging** - Isolate detection issues without hardware variables

---

## Setup (One Time)

The scripts are already in place! Just make sure you have:

1. **ROS2 workspace built:**
   ```bash
   cd ~/Downloads/pragati_ros2
   colcon build --packages-select cotton_detection_ros2
   source install/setup.bash
   ```

2. **Test images ready** (any of these formats):
   - JPG/JPEG
   - PNG
   - BMP
   - TIFF

---

## Usage Examples

### 1. Test Single Image

```bash
# Start detection node (Terminal 1)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false

# Test image with visualization (Terminal 2)
./test_offline_images.sh cotton_sample.jpg --visualize
```

**Output:**
- Shows image with green bounding boxes around detected cotton
- Displays confidence scores
- Prints detection count

### 2. Test Directory of Images

```bash
# Test all images in a folder
./test_offline_images.sh test_images/ --visualize

# Save results to JSON file
./test_offline_images.sh test_images/ --output results.json
```

**Output:**
```
Testing 12 images from: test_images/
✓ Detection node is running

[1/12] Testing: cotton_001.jpg
Publishing image: cotton_001.jpg (640x480)
Received 3 detections for cotton_001.jpg
...

============================================================
TEST SUMMARY
============================================================
Total images tested: 12
Images with detections: 10 (83.3%)
Total detections: 28
Average detections per image: 2.33
============================================================
```

### 3. Advanced Options

```bash
# Custom display time (3 seconds per image)
./test_offline_images.sh images/ --visualize --display-time 3000

# Longer timeout for slow processing
./test_offline_images.sh complex_image.jpg --timeout 10.0

# Add delay between images
./test_offline_images.sh images/ --visualize --delay 1.0
```

---

## Direct Script Usage

For more control, use the Python script directly:

```bash
cd src/cotton_detection_ros2/scripts

# Single image
python3 test_with_images.py --image /path/to/image.jpg --visualize

# Directory with custom options
python3 test_with_images.py \
    --dir test_images/ \
    --output results.json \
    --visualize \
    --display-time 2000 \
    --timeout 5.0 \
    --delay 0.5
```

**Options:**
- `--image` / `-i` : Single image file
- `--dir` / `-d` : Directory of images
- `--output` / `-o` : Save results to JSON
- `--visualize` / `-v` : Show detection boxes
- `--display-time` : Milliseconds to show each image (0 = wait for key)
- `--timeout` : Seconds to wait for detection
- `--delay` : Seconds between images

---

## Troubleshooting

### "Cotton detection node not running!"

**Solution:** Start the detection node first:
```bash
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false
```

### "No images found"

**Solution:** Check image format and path:
```bash
# List supported formats
ls *.jpg *.jpeg *.png *.bmp

# Use absolute path if relative doesn't work
./test_offline_images.sh /absolute/path/to/images/
```

### "Timeout waiting for detection result"

**Solution:** Increase timeout:
```bash
./test_offline_images.sh image.jpg --timeout 10.0
```

Or check if detection node is actually running:
```bash
ros2 node list | grep cotton_detection
```

### No detections on known cotton images

**Possible causes:**
1. **Threshold too high** - Adjust confidence threshold in config
2. **Wrong color space** - Verify HSV parameters for your lighting
3. **Image quality** - Check resolution and clarity
4. **Model mismatch** - Ensure using correct detection model

**Debug:**
```bash
# Check detection parameters
ros2 param list /cotton_detection_node

# Get current threshold
ros2 param get /cotton_detection_node confidence_threshold
```

---

## Output Format

### Console Output
```
Found 3 image(s) to test

[1/3] Testing: cotton_001.jpg
Publishing image: cotton_001.jpg (640x480)
Received 2 detections for cotton_001.jpg
  Detection 0: confidence=0.87, pos=(320, 240)

...

============================================================
TEST SUMMARY
============================================================
Total images tested: 3
Images with detections: 2 (66.7%)
Total detections: 5
Average detections per image: 1.67
============================================================
```

### JSON Output (results.json)
```json
{
  "cotton_001.jpg": {
    "num_detections": 2,
    "detections": [
      {
        "confidence": 0.87,
        "bbox": {
          "center_x": 320.0,
          "center_y": 240.0,
          "size_x": 80.0,
          "size_y": 60.0
        },
        "position_3d": null
      }
    ],
    "timestamp": 1730308765.123
  }
}
```

---

## Use Cases

### 1. **Development Workflow**
```bash
# Make code changes to detection algorithm
nano src/cotton_detection_ros2/src/cotton_detection_node.cpp

# Rebuild
colcon build --packages-select cotton_detection_ros2

# Test immediately
./test_offline_images.sh test_set/ --output before.json

# Compare results
diff before.json after.json
```

### 2. **Regression Testing**
```bash
# Create test suite
mkdir -p test_images/
# Add known good images with expected detection counts

# Run tests
./test_offline_images.sh test_images/ --output baseline.json

# After changes, compare
./test_offline_images.sh test_images/ --output current.json
diff baseline.json current.json
```

### 3. **Performance Benchmarking**
```bash
# Test with increasing complexity
for dir in easy medium hard; do
    echo "Testing $dir..."
    time ./test_offline_images.sh test_images/$dir/ --output ${dir}_results.json
done
```

### 4. **Dataset Validation**
```bash
# Test entire dataset
./test_offline_images.sh cotton_dataset/ --output dataset_results.json

# Analyze results
python3 -c "
import json
with open('dataset_results.json') as f:
    results = json.load(f)
    
# Calculate statistics
total = len(results)
detected = sum(1 for r in results.values() if r['num_detections'] > 0)
print(f'Detection rate: {detected/total*100:.1f}%')
"
```

---

## Alternative Methods

### Using ROS2 Tools Directly

```bash
# Method 1: image_publisher
sudo apt install ros-jazzy-image-publisher
ros2 run image_publisher image_publisher_node /path/to/image.jpg \
    --ros-args -r image_raw:=/camera/image_raw -p frequency:=1.0

# Method 2: ROS bag playback
ros2 bag record /camera/image_raw  # Record first
ros2 bag play your_bag.db3         # Play back later
```

---

## Next Steps

1. **Add your test images** to a dedicated folder
2. **Run baseline tests** to establish current performance
3. **Iterate on detection** - tweak parameters, test, repeat
4. **Document results** - keep JSON outputs for comparison
5. **Graduate to hardware** - deploy when offline tests pass

---

## Full Documentation

For comprehensive testing options and internals:
- 📖 [OFFLINE_TESTING.md](src/cotton_detection_ros2/OFFLINE_TESTING.md) - Complete guide
- 📖 [test_with_images.py](src/cotton_detection_ros2/scripts/test_with_images.py) - Script source
- 📖 [Cotton Detection README](src/cotton_detection_ros2/README.md) - Module docs

---

**🎯 Bottom Line:** Offline testing lets you validate detection logic without hardware. Use it extensively during development, then graduate to hardware validation when ready!
