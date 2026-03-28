# Camera-Only Tests - No Motors Required

**Purpose:** Validate cotton detection system without motor hardware  
**Hardware Needed:** OAK-D Lite camera only  
**Estimated Time:** 1-4 hours depending on tests selected

---

## Quick Setup

```bash
cd ~/pragati_ros2
source install/setup.bash

# Check camera is connected
lsusb | grep -i "03e7"
# Expected: Bus XXX Device XXX: ID 03e7:2485 Intel Movidius MyriadX
```

---

## Test 1: Debug Image Publishing (15 min)

**Purpose:** Verify detection overlays and image freshness

```bash
# Terminal 1: Launch with debug images
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=false \
    publish_debug_image:=true

# Terminal 2: View debug image
ros2 run rqt_image_view rqt_image_view /cotton_detection/debug_image

# Terminal 3: Trigger detection
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Check:**
- [ ] Debug image appears in viewer
- [ ] Bounding boxes drawn on cotton
- [ ] Confidence scores visible
- [ ] Spatial coordinates (X,Y,Z) labeled
- [ ] Image not frozen/stale

---

## Test 2: Calibration Export (10 min)

**Purpose:** Verify camera calibration can be exported

```bash
# Terminal 1: Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Terminal 2: Export calibration
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"

# Check output
ls -lh ~/pragati_ros2/data/outputs/calibration/
cat ~/pragati_ros2/data/outputs/calibration/*.yaml
```

**Expected Files:**
- [ ] Calibration YAML exists
- [ ] Contains camera matrix (3x3)
- [ ] Contains distortion coefficients
- [ ] Contains resolution (width, height)
- [ ] Baseline distance ~7.5cm (OAK-D Lite spec)

---

## Test 3: Detection Latency Measurement (20 min)

**Purpose:** Measure timing from service call to result

```bash
# Terminal 1: Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Terminal 2: Measure latency (run 10 times)
for i in {1..10}; do
    echo "=== Test $i ==="
    time ros2 service call /cotton_detection/detect \
        cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
    sleep 2
done
```

**Record:**
- [ ] Min latency: _____ms
- [ ] Max latency: _____ms
- [ ] Average latency: _____ms
- [ ] Current baseline: ~1500-1700ms (includes fresh frame wait)
- [ ] Target after fixes: <200ms

---

## Test 4: Detection Accuracy (30 min)

**Purpose:** Validate spatial accuracy at different distances

**Setup:**
1. Mark distances: 0.5m, 1.0m, 1.5m from camera
2. Place cotton sample at each distance
3. Measure reported coordinates

```bash
# Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Monitor results
ros2 topic echo /cotton_detection/results

# Trigger detection at each distance
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Record Table:**

| Distance (actual) | Reported X | Reported Y | Reported Z | Error (mm) |
|-------------------|------------|------------|------------|------------|
| 0.5m              |            |            |            |            |
| 1.0m              |            |            |            |            |
| 1.5m              |            |            |            |            |

**Acceptance:** Error < ±50mm at all distances

---

## Test 5: Thermal Monitoring (1 hour)

**Purpose:** Check camera temperature under continuous load

```bash
# Terminal 1: Monitor temperature
watch -n 5 'echo "=== $(date) ==="; vcgencmd measure_temp'

# Terminal 2: Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Terminal 3: Continuous detection (every 5 seconds for 1 hour)
for i in {1..720}; do
    echo "Detection $i at $(date)"
    ros2 service call /cotton_detection/detect \
        cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
    sleep 5
done
```

**Record:**
- [ ] Starting temp: _____°C
- [ ] Peak temp: _____°C
- [ ] Final temp: _____°C
- [ ] Thermal throttling observed? Yes/No
- [ ] Performance degradation? Yes/No

**Warning Levels:**
- < 70°C: Normal
- 70-85°C: Warm (acceptable)
- > 85°C: Hot (consider cooling)

---

## Test 6: Hang Detection & Recovery (30 min)

**Purpose:** Test node resilience to failures

### Test 6A: Cover Lens Test
```bash
# Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Start detection
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# MANUALLY: Cover camera lens for 10 seconds
# THEN: Uncover and trigger again

ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Check:**
- [ ] Node responds after lens uncovered
- [ ] No manual restart needed
- [ ] Error logged clearly
- [ ] Detection resumes normally

### Test 6B: USB Disconnect Simulation
```bash
# Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# MANUALLY: Briefly disconnect USB cable (2 seconds)
# THEN: Reconnect and check logs

# Try detection again
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Check:**
- [ ] Node detects disconnect
- [ ] Error logged clearly
- [ ] Node recovers OR exits cleanly
- [ ] No zombie processes

---

## Test 7: Frame Rate Sweep (30 min)

**Purpose:** Find optimal FPS for stability vs performance

```bash
# Test at 15 FPS
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py fps:=15
# Run 20 detections, monitor CPU

# Test at 20 FPS
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py fps:=20
# Run 20 detections, monitor CPU

# Test at 30 FPS
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py fps:=30
# Run 20 detections, monitor CPU
```

**Record:**

| FPS | Avg CPU% | Avg Latency | Hangs? | Notes |
|-----|----------|-------------|--------|-------|
| 15  |          |             |        |       |
| 20  |          |             |        |       |
| 30  |          |             |        |       |

**Recommendation:** Choose lowest FPS that meets latency requirements

---

## Test 8: Long-Duration Stability (2+ hours)

**Purpose:** Validate extended operation without manual intervention

```bash
# Terminal 1: Launch node with respawn
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Terminal 2: Log monitoring
tail -f ~/.ros/log/latest/cotton_detection_node*.log

# Terminal 3: Continuous detection (2 hours)
for i in {1..720}; do
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] Detection $i"
    
    ros2 service call /cotton_detection/detect \
        cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" \
        > /dev/null 2>&1
    
    if [ $? -ne 0 ]; then
        echo "[$timestamp] ❌ Detection $i FAILED"
    fi
    
    sleep 10
done | tee ~/stability_test_$(date +%Y%m%d_%H%M%S).log
```

**Check:**
- [ ] No crashes (check rosout)
- [ ] No manual restarts needed
- [ ] No memory leaks (check `top`)
- [ ] Consistent latency (no degradation)
- [ ] Stable temperature

**Acceptance:**
- Success rate > 95%
- Zero manual interventions
- Memory stable (< 500MB)

---

## Test 9: Low Light Performance (20 min)

**Purpose:** Verify detection in varying lighting

```bash
# Launch node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Test sequence:
# 1. Normal lighting (baseline)
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# 2. MANUALLY: Dim lights to 50%
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# 3. MANUALLY: Dim lights to 25%
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# 4. MANUALLY: Restore normal lighting
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

**Record:**
- [ ] Normal light: Detection works? Yes/No
- [ ] 50% dim: Detection works? Yes/No
- [ ] 25% dim: Detection works? Yes/No
- [ ] Exposure auto-adjusts correctly? Yes/No
- [ ] No stale frames after lighting change? Yes/No

---

## Quick Win: USB Autosuspend Fix

**Run this BEFORE testing to prevent USB suspend issues:**

```bash
# Create udev rule
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", ATTRS{idProduct}=="2485", ATTR{power/autosuspend}="-1"' | \
    sudo tee /etc/udev/rules.d/99-oakd-lite.rules

# Reload udev
sudo udevadm control --reload-rules
sudo udevadm trigger

# Verify (should show -1 or disabled)
cat /sys/bus/usb/devices/*/power/autosuspend | grep -v "0"
```

---

## Results Summary Template

**Date:** ___________  
**Tester:** ___________  
**Hardware:** OAK-D Lite (MxID: __________)  
**Software Version:** (commit hash: __________)

| Test | Status | Notes |
|------|--------|-------|
| 1. Debug Image | ⬜ Pass / ⬜ Fail | |
| 2. Calibration Export | ⬜ Pass / ⬜ Fail | |
| 3. Latency Measurement | ⬜ Pass / ⬜ Fail | Avg: ___ms |
| 4. Detection Accuracy | ⬜ Pass / ⬜ Fail | Error: ±___mm |
| 5. Thermal Monitoring | ⬜ Pass / ⬜ Fail | Peak: ___°C |
| 6. Hang Recovery | ⬜ Pass / ⬜ Fail | |
| 7. Frame Rate Sweep | ⬜ Pass / ⬜ Fail | Optimal: ___fps |
| 8. Long Stability | ⬜ Pass / ⬜ Fail | Success: ___%  |
| 9. Low Light | ⬜ Pass / ⬜ Fail | |

**Issues Found:**
1. 
2. 
3. 

**Recommendations:**
1. 
2. 
3. 

---

**Next Steps:**
- [ ] Fix identified issues
- [ ] Retest failed tests
- [ ] Update code based on findings
- [ ] Document results in test report
