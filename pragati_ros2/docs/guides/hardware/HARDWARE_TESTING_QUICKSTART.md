# Hardware Testing Quick Start Guide

**Camera Status:** ✅ OAK-D Lite connected to Raspberry Pi  
**Setup:** Desktop testing (will mount on robot later)  
**Focus:** Cotton detection testing

---

## 🎯 Priority Testing Tasks (Today)

### Phase 1: Basic Camera & Detection (2-3 hours)

#### Task 1.1: Verify Camera Connection (15 min)
```bash
# SSH to Raspberry Pi
ssh ubuntu@<rpi-ip>

# Check if camera is detected
python3 -c "import depthai as dai; print(dai.Device.getAllAvailableDevices())"

# Should show: [<DeviceInfo ...>]
# If empty: camera not detected, check USB connection
```

#### Task 1.2: Test Python Wrapper (30 min)
```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash

# Start Python wrapper with OAK-D Lite
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# In another terminal, trigger detection
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Monitor results
ros2 topic echo /cotton_detection/results
```

**Expected Output:**
- Camera initializes successfully
- Detection service responds
- Results published to topic (may be empty if no cotton visible)

#### Task 1.3: Test C++ Node with DepthAI (30 min)
```bash
# Start C++ node with DepthAI enabled
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=true

# Check if camera initializes
# Look for: "DepthAI camera initialized successfully"

# Monitor detection results
ros2 topic echo /cotton_detection/results
```

**Troubleshooting:**
- If camera fails: Check USB3 vs USB2 mode
- If no detections: HSV thresholds may need tuning (see Task 2.1)

#### Task 1.4: Visual Verification (15 min)
```bash
# View camera stream
ros2 run rqt_image_view rqt_image_view

# Select topic: /oak/rgb/image_raw or /camera/image_raw

# Point camera at cotton
# Verify image quality, lighting, focus
```

#### Task 1.5: Spatial Coordinates Test (30 min)
```bash
# Place object at known distance (e.g., 50cm)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=true

# Trigger detection
ros2 topic echo /cotton_detection/results

# Check position_3d values:
#   - z should be ~0.5m (depth)
#   - x, y are lateral position
```

**Validation:**
- Measure actual distance with ruler/tape
- Compare with reported z-value
- Acceptable error: ±5cm for distances up to 1m

---

### Phase 2: HSV Threshold Tuning (1 hour)

#### Task 2.1: Check Current HSV Settings
```bash
# Get current thresholds
ros2 param get /cotton_detection_node cotton_detection.hsv_lower_bound
ros2 param get /cotton_detection_node cotton_detection.hsv_upper_bound

# Default: [0, 0, 180] to [180, 40, 255]
# These are for WHITE cotton detection
```

#### Task 2.2: Interactive HSV Tuning (if needed)
```bash
# Use the existing HSV tuning script
cd ~/Downloads/pragati_ros2/src/cotton_detection_ros2/scripts/OakDTools

# Run HSV calibration tool
python3 hsv_tuner.py  # If available

# Or create simple tuner:
python3 -c "
import cv2
import depthai as dai

# Create pipeline
pipeline = dai.Pipeline()
cam_rgb = pipeline.create(dai.node.ColorCamera)
xout_rgb = pipeline.create(dai.node.XLinkOut)
xout_rgb.setStreamName('rgb')
cam_rgb.preview.link(xout_rgb.input)

# Connect and display
with dai.Device(pipeline) as device:
    queue = device.getOutputQueue('rgb', maxSize=4, blocking=False)
    
    while True:
        frame = queue.get().getCvFrame()
        
        # Show original
        cv2.imshow('RGB', frame)
        
        # Convert to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Apply threshold (adjust these values)
        lower = (0, 0, 180)
        upper = (180, 40, 255)
        mask = cv2.inRange(hsv, lower, upper)
        
        cv2.imshow('Mask', mask)
        
        if cv2.waitKey(1) == ord('q'):
            break
"
```

#### Task 2.3: Update Config with Tuned Values
```bash
# Edit config file
nano ~/Downloads/pragati_ros2/src/cotton_detection_ros2/config/cotton_detection_cpp.yaml

# Update HSV values:
cotton_detection:
  hsv_lower_bound: [H_min, S_min, V_min]
  hsv_upper_bound: [H_max, S_max, V_max]

# Rebuild and test
colcon build --packages-select cotton_detection_ros2
source install/setup.bash
```

---

### Phase 3: Performance & Accuracy Testing (1 hour)

#### Task 3.1: Detection Rate Test
```bash
# Place cotton in view
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=true

# Monitor detection rate
ros2 topic hz /cotton_detection/results

# Expected: ~10-30 Hz depending on mode
```

#### Task 3.2: False Positive/Negative Test
```bash
# Test with:
# 1. Cotton present -> Should detect
# 2. No cotton -> Should not detect
# 3. White paper -> Should not detect (if tuned properly)
# 4. Cotton at different angles
# 5. Cotton at different distances (20cm - 100cm)

# Record results for each scenario
```

#### Task 3.3: Multi-Cotton Test
```bash
# Place 2-5 cotton pieces in view
# Should detect all visible cotton

ros2 topic echo /cotton_detection/results

# Count detections in output
# Verify all cotton pieces are detected
```

---

## 📋 Quick Testing Checklist

Use this for rapid verification:

### Basic Functionality
- [ ] Camera connects successfully
- [ ] Image stream visible in rqt_image_view
- [ ] Detection service responds
- [ ] Results published to topic
- [ ] No error messages in logs

### Detection Quality
- [ ] Detects cotton when present
- [ ] No detection when no cotton
- [ ] Correct bounding box around cotton
- [ ] Reasonable confidence scores (>0.5)
- [ ] Multiple cotton pieces detected

### Spatial Accuracy (DepthAI)
- [ ] Z-depth matches measured distance (±5cm)
- [ ] X/Y position reasonable
- [ ] Depth available (not NaN/zero)
- [ ] Consistent readings (not jumping wildly)

### Performance
- [ ] Detection latency < 100ms
- [ ] Frame rate > 10 Hz
- [ ] No memory leaks over 5 minutes
- [ ] CPU usage reasonable (<50% on one core)

---

## 🔧 Common Issues & Solutions

### Issue 1: Camera Not Detected
```bash
# Check USB connection
lsusb | grep 03e7

# Should show: "Bus XXX Device XXX: ID 03e7:XXXX Movidius Ltd."

# Try different USB port
# Try USB2 mode if USB3 fails:
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb2
```

### Issue 2: No Detections with Cotton Present
```bash
# 1. Check HSV thresholds are appropriate for your lighting
# 2. Verify image quality
ros2 run rqt_image_view rqt_image_view

# 3. Try lower confidence threshold
ros2 param set /cotton_detection_node detection_confidence_threshold 0.3

# 4. Check min/max contour area
ros2 param get /cotton_detection_node cotton_detection.min_contour_area
ros2 param get /cotton_detection_node cotton_detection.max_contour_area
```

### Issue 3: Too Many False Positives
```bash
# Increase confidence threshold
ros2 param set /cotton_detection_node detection_confidence_threshold 0.8

# Tighten HSV range (less white noise)
# Edit config to reduce saturation range

# Increase minimum contour area
ros2 param set /cotton_detection_node cotton_detection.min_contour_area 200.0
```

### Issue 4: Depth Values Incorrect
```bash
# Verify stereo calibration
ros2 service call /cotton_detection/calibrate \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"

# Check if camera is too close (<20cm) or too far (>5m)
# OAK-D Lite optimal range: 20cm - 5m

# Verify stereo depth is enabled in config
```

---

## 📊 Data Collection for Analysis

### Collect Sample Images
```bash
# Save images for offline testing
ros2 run image_view image_saver --ros-args \
    -r image:=/camera/image_raw \
    -p filename_format:="cotton_test_%04d.jpg"

# Test ~20 images in different scenarios:
# - Close (20-30cm)
# - Medium (50-70cm)  
# - Far (100cm+)
# - Different angles
# - Different lighting
```

### Collect Detection Results
```bash
# Record detection data
ros2 bag record /cotton_detection/results /camera/image_raw -o test_session_1

# Later analyze:
ros2 bag play test_session_1_0.db3
```

### Export Performance Metrics
```bash
# Monitor and save metrics
ros2 topic hz /cotton_detection/results > detection_rate.txt
ros2 topic bw /cotton_detection/results > bandwidth.txt

# Check diagnostics
ros2 topic echo /diagnostics > diagnostics.log
```

---

## 🎯 Today's Goal: Minimum Viable Testing

**Core Tests to Complete Today (3-4 hours):**

1. ✅ Camera connection verified
2. ✅ Basic detection working
3. ✅ HSV thresholds tuned for your cotton
4. ✅ Spatial coordinates validated (±5cm accuracy)
5. ✅ Multi-cotton detection working
6. ✅ False positive rate acceptable (<10%)

**If Time Permits (additional 2 hours):**

7. Performance benchmarking
8. Integration with Yanthra movement system
9. End-to-end robot testing
10. Edge case testing (occlusion, overlapping cotton, etc.)

---

## 🚀 Next Steps After Hardware Testing

1. **Document Results**: Update test report with findings
2. **Tune Parameters**: Adjust config based on test results
3. **Integration Testing**: Test with full robot system
4. **Field Testing**: Test in actual cotton field conditions
5. **Performance Optimization**: If needed based on benchmarks

---

## 📞 Quick Commands Reference

```bash
# Start Python wrapper
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# Start C++ node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=true

# Trigger detection
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# View results
ros2 topic echo /cotton_detection/results

# View camera stream
ros2 run rqt_image_view rqt_image_view

# Check detection rate
ros2 topic hz /cotton_detection/results

# View diagnostics
ros2 topic echo /diagnostics
```

---

**Ready to start testing!** 🎉

Begin with Task 1.1 to verify camera connection, then proceed through the checklist.
