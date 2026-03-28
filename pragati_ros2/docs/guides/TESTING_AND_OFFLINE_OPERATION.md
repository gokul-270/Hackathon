# Testing and Offline Operation Guide

**Last Updated:** 2025-11-04  
**Consolidated From:** OFFLINE_TESTING.md, TEST_WITHOUT_CAMERA.md, SIMULATION_MODE_GUIDE.md  
**Status:** ✅ Production Ready (Nov 1, 2025)

---

## Overview

This comprehensive guide covers all methods for testing the Pragati cotton detection system without hardware, including:
- **Offline Testing:** Using saved images without a camera
- **Simulation Mode:** Running complete system with simulated detections
- **Continuous Testing:** Testing the full picking workflow

All methods support the validated production system (134ms service latency, 100% reliability).

---

## Quick Start

### Option 1: Offline Testing with Saved Images (Recommended for Development)

**Use when:** Testing detection algorithms, tuning parameters, CI/CD

```bash
# Terminal 1: Start detection node (simulation mode)
cd ~/Downloads/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false

# Terminal 2: Test with images
cd src/cotton_detection_ros2/scripts
python3 test_with_images.py --image /path/to/cotton.jpg --visualize
```

### Option 2: Complete System Simulation (Recommended for Integration Testing)

**Use when:** Testing full picking workflow, validating ROS2 integration

```bash
# Terminal 1: Start fake cotton detection publisher
python3 publish_fake_cotton.py

# Terminal 2: Launch main system
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true

# Terminal 3: Trigger picking cycle
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "{data: true}"
```

### Option 3: C++ Node Simulation (Recommended for Node Testing)

**Use when:** Testing cotton detection node independently

```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true \
    use_depthai:=false \
    publish_debug_image:=false
```

---

## Part 1: Offline Testing with Saved Images

### Benefits
✅ **No Hardware Required** - Test without OAK-D Lite camera  
✅ **Reproducible Results** - Same images every time  
✅ **Faster Development** - Quick iteration cycles  
✅ **Regression Detection** - Compare against baseline  
✅ **Dataset Benchmarking** - Test against standard datasets

### Prerequisites

```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash
```

### Single Image Testing

```bash
# Terminal 1: Start detection node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false

# Terminal 2: Test with single image
cd src/cotton_detection_ros2/scripts
python3 test_with_images.py --image cotton_sample.jpg --visualize
```

**Expected Output:**
- Image published to `/camera/image_raw`
- Detection results received
- Bounding boxes and confidence scores displayed

### Batch Testing Multiple Images

```bash
# Test entire directory
python3 test_with_images.py --dir test_images/ --output results.json

# With visualization
python3 test_with_images.py --dir test_images/ --visualize --display-time 3000
```

**Output Format:**
```json
{
  "cotton_001.jpg": {
    "num_detections": 3,
    "detections": [
      {
        "confidence": 0.87,
        "bbox": {"center_x": 320.0, "center_y": 240.0, "size_x": 80.0, "size_y": 60.0},
        "position_3d": {"x": 0.32, "y": -0.15, "z": 0.5}
      }
    ],
    "timestamp": 1696789234.567
  }
}
```

### Custom Timeout

```bash
# Wait up to 10 seconds for detection
python3 test_with_images.py --image slow_test.jpg --timeout 10.0
```

### Alternative Methods

#### Method 1: ROS2 Image Tools
```bash
sudo apt install ros-jazzy-image-tools

# Publish single image in loop
ros2 run image_tools cam2image --ros-args \
    -p filename:=/path/to/image.jpg \
    -r image:=/camera/image_raw
```

#### Method 2: Image Publisher
```bash
sudo apt install ros-jazzy-image-publisher

# Publish image at 10 Hz
ros2 run image_publisher image_publisher_node /path/to/image.jpg \
    --ros-args -r image_raw:=/camera/image_raw -p frequency:=10.0
```

#### Method 3: ROS Bag Playback
```bash
# Record a bag with camera images
ros2 bag record /camera/image_raw

# Play back later for testing
ros2 bag play your_bag.db3
```

### Creating Test Images

#### From Existing Camera
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

#### From Simulation
```bash
# Generate test data from simulation
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true publish_debug_images:=true

# Subscribe to debug images
ros2 run image_view image_saver --ros-args \
    -r image:=/cotton_detection/debug_image
```

### Regression Testing

#### Create Baseline Results
```bash
# Test with known good images
python3 test_with_images.py --dir baseline_images/ --output baseline_results.json
```

#### Compare After Changes
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

---

## Part 2: Complete System Simulation

### System Flow
```
1. Start fake cotton detection publisher (continuously publishes)
   ↓
2. Launch main system (yanthra_move)
   ↓
3. System initializes and waits for START_SWITCH
   ↓
4. Send START_SWITCH signal
   ↓
5. System reads cotton detections from fake publisher
   ↓
6. System performs picking operation
   ↓
7. System returns to waiting (loop continues)
```

### Step-by-Step Procedure

#### Terminal 1: Start Fake Cotton Publisher

```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash
python3 publish_fake_cotton.py
```

**Expected Output:**
```
============================================================
Fake Cotton Detection Publisher
============================================================

Publishing cotton at position (0.3, 0.0, 0.5) meters

[INFO] [fake_cotton_publisher]: Publishing to /cotton_detection/results at 1 Hz
[INFO] [fake_cotton_publisher]: Published cotton at (0.30, 0.00, 0.50)
```

**Leave this running!** It continuously publishes detections at 1 Hz.

#### Terminal 2: Launch Main System

```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true
```

**Wait for initialization** (15-20 seconds). Look for:
```
[INFO] [yanthra_move]: ⏳ Waiting for START_SWITCH signal...
[INFO] [yanthra_move]: ⏳ Waiting infinitely for START_SWITCH (timeout disabled)
```

#### Terminal 3: Send Start Switch Signal

```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "{data: true}"
```

**Expected Behavior:**
1. System receives START_SWITCH signal
2. System reads cotton detection from publisher
3. System performs picking operation
4. System completes cycle and waits for START_SWITCH again

#### Trigger Another Cycle

```bash
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "{data: true}"
```

### Verification Commands

```bash
# Check cotton detections are published
ros2 topic echo /cotton_detection/results

# Check system topics
ros2 topic list | grep start_switch

# Monitor detection rate
ros2 topic hz /cotton_detection/results
```

### Customizing Cotton Position

Edit `publish_fake_cotton.py`:
```python
cotton.position.x = 0.3  # forward distance (meters)
cotton.position.y = 0.0  # sideways offset (meters)  
cotton.position.z = 0.5  # height (meters)
cotton.confidence = 0.95  # detection confidence
```

---

## Part 3: C++ Node Simulation Mode

### Why Use C++ Node Simulation?

Use when:
- Testing cotton detection node independently
- Validating ROS2 interfaces and parameters
- CI/CD pipeline smoke tests
- Development without hardware

### Launch Options

#### Pure Simulation (No DepthAI)
```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true \
    use_depthai:=false \
    publish_debug_image:=false
```

**What Happens:**
- Publishes deterministic synthetic detections
- Skips DepthAI device enumeration
- Keeps diagnostics and TF publishers alive

#### Test Service Contract
```bash
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

Verify with:
```bash
ros2 topic echo /cotton_detection/results --once
```

### Build for Simulation

```bash
# Build without DepthAI (simulation friendly)
colcon build --packages-select cotton_detection_ros2 yanthra_move \
    --cmake-args -DHAS_DEPTHAI=OFF

source install/setup.bash
```

### Parameters Available

```bash
# Runtime parameters
simulation_mode: true          # Enable simulation
use_depthai: false            # Disable camera hardware
offline_mode: true            # Service-triggered only
detection_confidence_threshold: 0.7
max_cotton_detections: 50
enable_debug_output: false
```

---

## Part 4: Legacy Python Wrapper (Optional)

**Status:** Legacy - Use C++ node for new work

### When to Use
- Validating historical automation flows
- Regression testing legacy scripts

### Launch
```bash
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    simulation_mode:=true \
    trigger_on_start:=true
```

**Behavior:**
- Generates three canonical synthetic cotton boll coordinates
- Emits `/cotton_detection/results` (Detection3DArray)
- Honors service calls without camera

---

## Part 5: Integration with Yanthra Move

### Launch Complete Workflow

```bash
# Terminal 1: Cotton detection
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true use_depthai:=false

# Terminal 2: Yanthra move manipulator
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=true \
    continuous_operation:=false \
    enable_arm_client:=false
```

### Monitor Integration

```bash
# Check detection results
ros2 topic hz /cotton_detection/results

# Check arm status
ros2 topic echo /yanthra_move/arm_status --once

# Monitor full system
ros2 node list
ros2 topic list
```

### Without Web Dashboard

Remember to trigger start switch manually:
```bash
ros2 topic pub /start_switch/state std_msgs/Bool "data: true" --once
```

---

## Part 6: Automated Smoke Testing

### CI/CD Integration Script

```bash
#!/usr/bin/env bash
set -euo pipefail
source install/setup.bash

# Start detection node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true use_depthai:=false &
DET_PID=$!
trap "kill $DET_PID" EXIT

sleep 3

# Test service call
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Verify topic output
ros2 topic echo /cotton_detection/results --once --timeout 5

# Cleanup
kill $DET_PID
wait $DET_PID 2>/dev/null || true
```

### Comprehensive Validation Suite

```bash
# Run full simulation suite
./scripts/validation/comprehensive_test_suite.sh

# Results saved to
~/pragati_test_output/integration/comprehensive_test_YYYYMMDD_HHMMSS/
```

### Enable Strict Hardware Checks (Optional)

```bash
# For hardware validation
export SIMULATION_EXPECTS_MG6010=1
./scripts/validation/comprehensive_test_suite.sh

# Reset to simulation default
export SIMULATION_EXPECTS_MG6010=0
```

---

## Part 7: Performance Testing

### Measure Detection Latency

```bash
python3 test_with_images.py --dir test_images/ --output timing.json

# Calculate average latency
python3 -c "
import json
with open('timing.json') as f:
    results = json.load(f)
    
latencies = []
for img, data in results.items():
    if 'processing_time_ms' in data:
        latencies.append(data['processing_time_ms'])
        
if latencies:
    print(f'Average latency: {sum(latencies)/len(latencies):.3f}ms')
"
```

### Test Different Image Sizes

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

---

## Part 8: Troubleshooting

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

### System Doesn't Respond to Start Switch

```bash
# Check config
ros2 param get /yanthra_move start_switch.enable_wait

# Verify topic exists
ros2 topic list | grep start_switch

# Check logs for "Waiting for START_SWITCH"
```

### Image Format Issues

```bash
# Convert to supported format
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
# Check HSV thresholds
ros2 param get /cotton_detection_node cotton_detection.hsv_lower_bound
ros2 param get /cotton_detection_node cotton_detection.hsv_upper_bound

# Test with visualization
python3 test_with_images.py --image test.jpg --visualize

# Try different detection modes
# Edit config: detection_mode: "hsv_only" | "yolo_only" | "hybrid_fallback"
```

### Fake Publisher Not Working

```bash
# Check publisher is running
ros2 node list | grep fake_cotton

# Monitor published messages
ros2 topic echo /cotton_detection/results

# Verify topic type
ros2 topic info /cotton_detection/results
```

---

## Part 9: Configuration Reference

### Current System Configuration

From `src/yanthra_move/config/production.yaml`:
```yaml
continuous_operation: true      # Keeps running
start_switch.enable_wait: true  # Waits for start switch
start_switch.timeout_sec: -1.0  # Infinite wait
start_switch.prefer_topic: true # Uses topic
simulation_mode: true           # No hardware needed
```

### Detection Node Parameters

```yaml
offline_mode: false                    # Camera mode
camera_topic: "/camera/image_raw"
detection_confidence_threshold: 0.7
max_cotton_detections: 50
enable_debug_output: false
detection_mode: "depthai_direct"       # Production mode

# Performance
performance.verbose_timing: false
depthai.flush_before_read: false
depthai.max_queue_drain: 10
depthai.warmup_seconds: 3
save_input_image: false
save_output_image: false
```

---

## Part 10: Best Practices

### ✅ Do:
1. Use offline testing for algorithm development
2. Use simulation for integration testing
3. Create baseline datasets for regression testing
4. Archive test results with timestamps
5. Use automated smoke tests in CI/CD
6. Document test procedures and expected results
7. Test at multiple resolutions and lighting conditions

### ❌ Don't:
1. Don't rely solely on simulation - validate with hardware
2. Don't skip regression testing after changes
3. Don't ignore failed smoke tests
4. Don't modify production configs for testing
5. Don't commit test images to repository (use Git LFS)
6. Don't assume simulation matches hardware performance

---

## Summary

**Three Testing Methods:**

| Method | Use Case | Hardware Required | Setup Time |
|--------|----------|-------------------|------------|
| **Offline Testing** | Algorithm development, parameter tuning | None | 1 minute |
| **Complete Simulation** | Integration testing, workflow validation | None | 2 minutes |
| **C++ Node Simulation** | Node testing, CI/CD | None | 30 seconds |

**Key Benefits:**
- ✅ No camera required
- ✅ Reproducible results
- ✅ Fast iteration
- ✅ CI/CD ready
- ✅ Production validated (134ms latency, 100% reliability)

**Production Status:**
- ✅ System validated Nov 1, 2025
- ✅ 134ms average service latency
- ✅ 100% reliability (10/10 tests)
- ✅ Ready for field deployment

---

## Related Documentation

- **Production Status:** [PRODUCTION_READY_STATUS.md](../../PRODUCTION_READY_STATUS.md)
- **Hardware Testing:** [hardware/HARDWARE_TESTING_QUICKSTART.md](hardware/HARDWARE_TESTING_QUICKSTART.md)
- **Package README:** [src/cotton_detection_ros2/README.md](../../src/cotton_detection_ros2/README.md)
- **Integration Guide:** [../integration/COTTON_DETECTION_INTEGRATION_README.md](../integration/COTTON_DETECTION_INTEGRATION_README.md)
- **Performance Guide:** [PERFORMANCE_OPTIMIZATION.md](PERFORMANCE_OPTIMIZATION.md)

---

**Document Version:** 1.0 (Consolidated)  
**Last Updated:** 2025-11-04  
**Status:** Current - Production Ready System  
**Supersedes:** OFFLINE_TESTING.md, TEST_WITHOUT_CAMERA.md, SIMULATION_MODE_GUIDE.md (portions)
