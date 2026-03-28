# USB2 Mode Configuration and Validation Guide

ℹ️ **HISTORICAL DOCUMENT - Archived Nov 4, 2025**

**Original Date:** October 2025  
**Status at Time:** Configuration validated  
**Superseded By:** [CAMERA_SETUP_AND_DIAGNOSTICS.md](../../../guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md)

**Historical Context:**  
This document explained the rationale for using USB 2.0 mode with OAK-D Lite cameras and validated the configuration across all code locations. The USB2 configuration was successfully deployed and validated in production on Nov 1, 2025. The system achieved 134ms service latency and 100% reliability running in USB2 mode on Raspberry Pi.

**Outcome:** ✅ USB2 configuration validated, production-ready Nov 1, 2025  
**Current Status:** USB2 mode proven stable - see CAMERA_SETUP_AND_DIAGNOSTICS.md

---

**Component**: OAK-D Lite Camera System  
**Configuration**: USB 2.0 Mode  
**Reason**: Bandwidth stability, long cable support, field reliability  
**Original Documentation Date**: October 2025

---

## Overview

The OAK-D Lite camera system is configured to operate in **USB 2.0 mode** by default for maximum stability and reliability in field conditions. This document details the USB2 configuration, validation procedures, and troubleshooting.

---

## Why USB2 Mode?

### Advantages of USB2 Mode ✅

1. **Cable Length Tolerance**
   - USB2: Stable up to 5 meters (standard cables)
   - USB2 with active extension: Up to 15-20 meters
   - USB3: Degraded performance beyond 3 meters

2. **Bandwidth Stability**
   - USB2: Consistent 480 Mbps
   - USB3: Susceptible to interference, especially outdoors
   - USB2: More reliable in agricultural/field environments

3. **Power Draw**
   - USB2: Lower power consumption
   - USB3: Higher power, potential voltage drops over long cables
   - USB2: Better for battery-powered robots

4. **Compatibility**
   - USB2: Works with any USB port (2.0, 3.0, 3.1, 3.2)
   - USB3: Requires USB 3.x port with good signal integrity
   - USB2: Universal compatibility

### Trade-offs ⚠️

1. **Lower Frame Rate**
   - USB2: ~15-20 FPS for 1080p RGB + depth
   - USB3: ~30 FPS possible
   - **For cotton picking**: 15-20 FPS is sufficient (detection is triggered, not continuous)

2. **Higher Latency**
   - USB2: Slightly higher latency (~50-100ms additional)
   - USB3: Lower latency
   - **For cotton picking**: Acceptable for service-triggered detection

### Decision: USB2 is Optimal ✅

For the Pragati cotton picking robot:
- **Field deployment**: USB2's reliability outweighs USB3's speed
- **Long cables**: Robot arm movement requires cable flexibility
- **Triggered detection**: Not continuous streaming, frame rate less critical
- **ROS1 proven**: Original system used USB2 successfully

---

## USB2 Configuration Locations

### 1. CottonDetect.py (ROS1 Script) ✅

**File**: `scripts/OakDTools/CottonDetect.py`

**Line 316-317**:
```python
#Forcing Usb Connection to USB2MODE
    with dai.Device(pipeline ,usb2Mode=True) as device:
```

**Status**: ✅ **USB2 mode explicitly enabled**

**Comment on line 319-320**:
```python
#By Deafault the connection is in USB3.0
#  with dai.Device(pipeline) as device:
```

**Verification**: USB2 mode is **forced** and not relying on defaults.

---

### 2. ROS2 Wrapper Node ✅

**File**: `scripts/cotton_detect_ros2_wrapper.py`

**Line 94**:
```python
('usb_mode', 'usb2'),  # USB mode: usb2 or usb3
```

**Parameter Declaration**:
- **Name**: `usb_mode`
- **Type**: `string`
- **Default**: `"usb2"`
- **Options**: `"usb2"` or `"usb3"`
- **Description**: USB bandwidth mode for OAK-D Lite

**Status**: ✅ **USB2 is the default**

---

### 3. Launch File ✅

**File**: `launch/cotton_detection_wrapper.launch.py`

**Lines 35-38**:
```python
DeclareLaunchArgument(
    'usb_mode',
    default_value='usb2',
    description='USB mode: usb2 or usb3 (usb2 recommended for stability)'
),
```

**Launch Argument**:
- **Name**: `usb_mode`
- **Default**: `usb2`
- **Override**: `ros2 launch ... usb_mode:=usb3` (if needed)

**Status**: ✅ **USB2 is the default, with clear recommendation**

---

## Validation Procedures

### Pre-Hardware Validation ✅ (Completed)

#### Check 1: CottonDetect.py USB2 Configuration ✅
```bash
grep -n "usb2Mode" scripts/OakDTools/CottonDetect.py
```

**Expected**: Line 317: `with dai.Device(pipeline ,usb2Mode=True) as device:`

**Result**: ✅ **PASS** - USB2 mode is explicitly set

---

#### Check 2: Wrapper Node Default Parameter ✅
```bash
grep -n "usb_mode" scripts/cotton_detect_ros2_wrapper.py
```

**Expected**: Default value is `"usb2"`

**Result**: ✅ **PASS** - USB2 is the default

---

#### Check 3: Launch File Default ✅
```bash
grep -A2 "usb_mode" launch/cotton_detection_wrapper.launch.py
```

**Expected**: `default_value='usb2'`

**Result**: ✅ **PASS** - USB2 is the default

---

### Hardware Validation ⏳ (Pending Camera)

#### Test 1: Verify USB2 Connection ⏳

**Procedure**:
```bash
# Connect OAK-D Lite camera

# Check USB bus speed
lsusb -t | grep -A5 "03e7:2485"

# Expected output should show "480M" (USB 2.0) not "5000M" (USB 3.0)
```

**Expected Result**:
```
/:  Bus 01.Port 1: Dev 1, Class=root_hub, Driver=xhci_hcd/14p, 480M
    |__ Port 5: Dev 2, If 0, Class=..., Driver=..., 480M
```

**Acceptance Criteria**:
- [ ] Device shows 480M speed (USB 2.0)
- [ ] Not showing 5000M (USB 3.0)
- [ ] Camera functional at 480M

---

#### Test 2: USB2 Mode Runtime Verification ⏳

**Procedure**:
```python
#!/usr/bin/env python3
import depthai as dai

# Test USB2 mode detection
with dai.Device() as device:
    usb_speed = device.getUsbSpeed()
    print(f"USB Speed: {usb_speed}")
    
    # Check expected speed
    if usb_speed == dai.UsbSpeed.HIGH:  # USB 2.0
        print("✅ Camera is in USB 2.0 mode (480 Mbps)")
    elif usb_speed == dai.UsbSpeed.SUPER:  # USB 3.0
        print("⚠️ Camera is in USB 3.0 mode (5 Gbps)")
    elif usb_speed == dai.UsbSpeed.SUPER_PLUS:  # USB 3.1+
        print("⚠️ Camera is in USB 3.1+ mode (10+ Gbps)")
    else:
        print(f"❌ Unknown USB speed: {usb_speed}")
```

**Expected Result**: ✅ "Camera is in USB 2.0 mode (480 Mbps)"

**Acceptance Criteria**:
- [ ] USB speed reports HIGH (USB 2.0)
- [ ] Camera initializes successfully
- [ ] No bandwidth warnings in logs

---

#### Test 3: USB2 Long Cable Stability ⏳

**Procedure**:
```bash
# Test with different cable lengths
# 1m, 3m, 5m cables

# For each cable length:
# 1. Connect camera
# 2. Launch wrapper node
# 3. Trigger 50 detections
# 4. Monitor for USB errors

for cable in "1m" "3m" "5m"; do
    echo "Testing with $cable cable"
    # Connect camera with $cable cable
    
    ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py &
    LAUNCH_PID=$!
    sleep 5
    
    for i in {1..50}; do
        ros2 service call /cotton_detection/detect \
            cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
        sleep 1
    done
    
    # Check for USB errors
    dmesg | tail -50 | grep -i "usb"
    
    kill $LAUNCH_PID
    sleep 2
done
```

**Expected Results**:
- 1m cable: 50/50 successful detections
- 3m cable: 50/50 successful detections
- 5m cable: ≥48/50 successful detections (≥96% success rate)

**Acceptance Criteria**:
- [ ] No USB disconnections
- [ ] No "bandwidth exceeded" errors
- [ ] Consistent frame delivery
- [ ] Success rate ≥95% for all cable lengths

---

#### Test 4: USB2 vs USB3 Comparison ⏳

**Procedure**:
```bash
# Test 1: USB2 mode
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb2

# Measure: latency, frame rate, stability (run 100 detections)

# Test 2: USB3 mode
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb3

# Measure: latency, frame rate, stability (run 100 detections)

# Compare results
```

**Expected Results**:

| Metric | USB2 | USB3 | Verdict |
|--------|------|------|---------|
| Latency | ~1.5-2.0s | ~1.2-1.5s | USB3 slightly faster |
| Frame Rate | 15-20 FPS | 25-30 FPS | USB3 higher |
| Stability (100 detections) | 99-100% | 95-98% (may degrade with long cables) | USB2 more stable |
| Cable Length Tolerance | Up to 5m | Up to 3m | USB2 better |

**Acceptance Criteria**:
- [ ] Both modes functional
- [ ] USB2 stability ≥99%
- [ ] USB3 faster but less stable with long cables
- [ ] Performance difference documented

---

## Troubleshooting

### Issue 1: Camera Not Detected

**Symptoms**:
- `lsusb` doesn't show OAK-D Lite (VID:PID `03e7:2485`)
- DepthAI SDK cannot find device

**Solutions**:

1. **Check USB cable**:
   ```bash
   # Try different USB port
   # Try shorter cable (< 3m for testing)
   ```

2. **Check USB permissions**:
   ```bash
   # Check if udev rules are set
   ls -l /etc/udev/rules.d/*luxonis*
   
   # If missing, add udev rule:
   echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

3. **Check USB power**:
   ```bash
   # Ensure USB port provides enough power
   # Some USB hubs don't provide sufficient power
   # Try connecting directly to motherboard USB port
   ```

---

### Issue 2: Bandwidth Errors

**Symptoms**:
- "Insufficient USB bandwidth" errors in logs
- Frame drops or corrupted frames
- Intermittent connectivity

**Solutions**:

1. **Verify USB2 mode is set**:
   ```bash
   # Check CottonDetect.py line 317
   grep "usb2Mode=True" scripts/OakDTools/CottonDetect.py
   
   # Check launch parameter
   ros2 param get /cotton_detect_ros2_wrapper usb_mode
   ```

2. **Reduce frame rate** (if using USB3 by mistake):
   ```python
   # In DepthAI pipeline (if modified)
   camRgb.setFps(15)  # Reduce from 30 to 15 FPS
   ```

3. **Check USB controller**:
   ```bash
   # List USB controllers
   lspci | grep USB
   
   # Some USB controllers share bandwidth across ports
   # Try different USB controller/root hub
   ```

---

### Issue 3: USB Disconnections

**Symptoms**:
- Camera disconnects during operation
- "Device lost" errors
- Must replug camera to recover

**Solutions**:

1. **Check cable quality**:
   - Use high-quality USB 2.0 cable
   - Avoid cheap or damaged cables
   - Test with known-good cable

2. **Check cable length**:
   - USB 2.0: Max 5m for standard cables
   - Use active USB extension cable for longer distances
   - Avoid coiling or sharp bends

3. **Check power supply**:
   ```bash
   # Ensure robot has stable power
   # USB ports may not provide enough current under load
   # Consider powered USB hub if needed
   ```

4. **Check for EMI (Electromagnetic Interference)**:
   - Robot motors can generate EMI
   - Route USB cable away from motor cables
   - Use shielded USB cable if needed

---

### Issue 4: Slow Performance in USB2 Mode

**Symptoms**:
- Detection latency > 3 seconds
- Frame rate < 10 FPS
- System feels sluggish

**Solutions**:

1. **Verify USB2 is actually being used**:
   ```bash
   lsusb -t | grep -A5 "03e7:2485"
   # Should show 480M, not 5000M
   ```

2. **Check system load**:
   ```bash
   top
   # Ensure CPU isn't overloaded
   # Ensure sufficient RAM available
   ```

3. **Optimize detection script**:
   ```python
   # Ensure CottonDetect.py isn't doing unnecessary processing
   # Check for debug prints or logging that slow it down
   ```

4. **Consider USB3 mode** (if cables are short):
   ```bash
   # If using cables < 2m and need higher performance
   ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb3
   ```

---

## USB Mode Switching

### Switch to USB3 Mode

**When to use**:
- Short cables (< 2m)
- Benchtop testing
- Need higher frame rate
- Indoor controlled environment

**How to switch**:

```bash
# Method 1: Launch argument
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb3

# Method 2: Runtime parameter (if node running)
ros2 param set /cotton_detect_ros2_wrapper usb_mode usb3
```

**Note**: ⚠️ The ROS1 CottonDetect.py script has USB2 hardcoded. Switching usb_mode parameter in ROS2 wrapper won't affect CottonDetect.py until Phase 2 (direct pipeline integration).

---

### Switch Back to USB2 Mode

**How to switch**:

```bash
# Method 1: Launch argument (default)
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb2

# Method 2: Runtime parameter
ros2 param set /cotton_detect_ros2_wrapper usb_mode usb2
```

---

## USB Configuration Summary

### Current Configuration ✅

| Component | USB Mode | Status |
|-----------|----------|--------|
| **CottonDetect.py** | USB2 (hardcoded) | ✅ Configured |
| **Wrapper Node Default** | USB2 | ✅ Configured |
| **Launch File Default** | USB2 | ✅ Configured |
| **Documentation** | USB2 recommended | ✅ Documented |

### Phase 2 Changes (Future)

In Phase 2 (direct DepthAI pipeline integration), the `usb_mode` parameter will directly control the DepthAI device:

```python
# Phase 2: Direct control
usb2_mode = self.get_parameter('usb_mode').value == 'usb2'
with dai.Device(pipeline, usb2Mode=usb2_mode) as device:
    # ...
```

---

## Best Practices

### ✅ Do:
1. Use USB 2.0 mode for field deployments
2. Use high-quality, shielded USB cables
3. Keep cables < 5m for USB 2.0
4. Route cables away from motor wires
5. Test with actual deployment cable lengths
6. Monitor USB errors in dmesg regularly

### ❌ Don't:
1. Don't use USB 3.0 mode with cables > 3m
2. Don't use cheap/damaged USB cables
3. Don't coil or sharply bend USB cables
4. Don't share USB controller with other high-bandwidth devices
5. Don't rely on USB hubs for power-hungry devices
6. Don't assume USB3 is always better (stability > speed for robots)

---

## References

- **DepthAI USB Documentation**: https://docs.luxonis.com/projects/api/en/latest/components/device/#usb-speed
- **USB 2.0 Specification**: 480 Mbps, 5m max length
- **USB 3.0 Specification**: 5 Gbps, 3m max length
- **ROS1 Configuration** (proven working): USB2 mode in production

---

**Document Version**: 1.0  
**Status**: ✅ USB2 Configuration Validated (Pre-Hardware)  
**Next Update**: After hardware testing confirms USB2 performance
