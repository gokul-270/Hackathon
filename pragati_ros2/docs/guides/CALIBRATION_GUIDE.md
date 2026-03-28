# Pragati Robot Calibration Guide

**Version:** 1.0  
**Date:** October 8, 2025  
**Target System:** Pragati ROS2 Cotton-Picking Robot  
**Tier:** 2.2 - Unified Calibration Documentation

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start Checklist](#quick-start-checklist)
3. [Motor & Encoder Calibration](#1-motor--encoder-calibration)
4. [Camera Intrinsic Calibration](#2-camera-intrinsic-calibration)
5. [Hand-Eye Extrinsic Calibration](#3-hand-eye-extrinsic-calibration)
6. [System Validation](#4-system-validation)
7. [Troubleshooting](#troubleshooting)
8. [Maintenance Schedule](#maintenance-schedule)

---

## Prerequisites

### Hardware Requirements
- ✅ Pragati robot powered and connected
- ✅ All motors responsive (test with `ros2 topic echo /joint_states`)
- ✅ OAK-D Lite camera connected via USB
- ✅ Emergency stop button accessible
- ✅ Clear workspace (minimum 2m x 2m)
- ✅ ArUco calibration board (if performing hand-eye calibration)

### Software Requirements
- ✅ ROS2 environment sourced:
  ```bash
  source ~/Downloads/pragati_ros2/install/setup.bash
  ```
- ✅ All packages built:
  ```bash
  cd ~/Downloads/pragati_ros2
  ./build.sh
  ```
- ✅ Sufficient disk space (check with disk monitor):
  ```bash
  ros2 topic echo /system/disk_usage --once
  # Should show > 2GB free
  ```

### Safety Checklist
- ⚠️ Ensure no obstructions in robot workspace
- ⚠️ Emergency stop within arm's reach
- ⚠️ Motors start at reduced speed/torque limits
- ⚠️ Safety monitor enabled (default in pragati_complete.launch.py)

---

## Quick Start Checklist

For routine recalibration (e.g., after transport or maintenance):

- [ ] **Step 1:** Home all joints → [Section 1.1](#11-joint-homing)
- [ ] **Step 2:** Verify encoder zeros → [Section 1.2](#12-encoder-calibration)
- [ ] **Step 3:** Check camera intrinsics → [Section 2.1](#21-verify-camera-eeprom-data)
- [ ] **Step 4:** Validate transforms → [Section 3.3](#33-tf-validation)
- [ ] **Step 5:** Run system validation → [Section 4](#4-system-validation)

**Estimated Time:** 15-20 minutes for routine recalibration

---

## 1. Motor & Encoder Calibration

### 1.1 Joint Homing

**Purpose:** Establish mechanical zero positions for all joints

**Procedure:**

1. **Launch motor control system:**
   ```bash
   ros2 launch yanthra_move pragati_complete.launch.py
   ```

2. **Home individual joints:**
   ```bash
   # Home joint 2 (vertical prismatic)
   ros2 service call /motor/home_joint motor_control_ros2/srv/JointHoming \
     "{homing_required: true, joint_id: 2}"
   
   # Home joint 3 (first rotation)
   ros2 service call /motor/home_joint motor_control_ros2/srv/JointHoming \
     "{homing_required: true, joint_id: 3}"
   
   # Home joint 4 (horizontal prismatic)
   ros2 service call /motor/home_joint motor_control_ros2/srv/JointHoming \
     "{homing_required: true, joint_id: 4}"
   
   # Home joint 5 (end effector rotation)
   ros2 service call /motor/home_joint motor_control_ros2/srv/JointHoming \
     "{homing_required: true, joint_id: 5}"
   ```

3. **Verify joint positions:**
   ```bash
   ros2 topic echo /joint_states --once
   ```
   
   **Expected:** All positions should be at or near 0.0 after homing

**Troubleshooting:**
- If homing fails, check motor enable status
- Ensure no mechanical obstructions
- Verify limit switches are functioning (if equipped)

---

### 1.2 Encoder Calibration

**Purpose:** Set encoder offsets for accurate position feedback

**When to perform:**
- After motor replacement
- After encoder replacement  
- If position drift is observed (>5mm over 1 hour)

**Procedure:**

1. **Move joint to known mechanical position** (e.g., against hard stop or marked position)

2. **Set encoder zero at current position:**
   ```bash
   # Example for joint 2
   ros2 service call /motor/encoder_calibrate motor_control_ros2/srv/EncoderCalibration \
     "{joint_id: 2, index_search: false, timeout: 10.0}"
   ```

3. **For motors with index pulse (optional - more accurate):**
   ```bash
   ros2 service call /motor/encoder_calibrate motor_control_ros2/srv/EncoderCalibration \
     "{joint_id: 2, index_search: true, timeout: 20.0}"
   ```

4. **Verify encoder reading:**
   ```bash
   ros2 topic echo /joint_states
   ```

**Note:** For joints without absolute encoders, this calibration must be performed each power cycle.

---

### 1.3 Save Motor Calibration

**Purpose:** Persist calibration data for future sessions

**Procedure:**

1. **Save all calibration parameters:**
   ```bash
   ros2 param dump /motor_controller \
     --output-dir ~/.ros/config/calibration/ \
     --print motor_calibration_$(date +%Y%m%d).yaml
   ```

2. **Verify saved parameters:**
   ```bash
   cat ~/.ros/config/calibration/motor_calibration_*.yaml
   ```

3. **Load calibration on next boot** (add to launch file or load manually):
   ```bash
   ros2 param load /motor_controller \
     ~/.ros/config/calibration/motor_calibration_YYYYMMDD.yaml
   ```

**Best Practice:** Create dated backups of calibration files

---

## 2. Camera Intrinsic Calibration

The OAK-D Lite camera ships with factory calibration stored in EEPROM. Typically, you only need to verify this data, not recalibrate.

### 2.1 Verify Camera EEPROM Data

**Procedure:**

1. **Check camera is detected:**
   ```bash
   # List USB devices
   lsusb | grep "Luxonis"
   ```
   
   **Expected output:** `Luxonis Device` should appear

2. **Export calibration from EEPROM** (if cotton_detection supports calibration export):
   ```bash
   ros2 service call /cotton_detection/calibrate \
     cotton_detection_ros2/srv/CottonDetection \
     "{detect_command: 2}"
   ```

3. **Inspect calibration file:**
   ```bash
   cat ~/.ros/camera_calibration.json
   ```

### 2.2 Validate Intrinsic Parameters

**Check the following values:**

| Parameter | Expected Range | Notes |
|-----------|---------------|-------|
| Focal length (fx, fy) | ~850-900 pixels | For 1080p RGB camera |
| Principal point (cx, cy) | Near image center | Should be ~540, ~960 |
| Distortion (k1, k2) | < 0.05 absolute value | Lens distortion coefficients |
| Matrix rank | Full rank (3) | Matrix must be non-singular |

**Example good calibration:**
```json
{
  "fx": 880.5,
  "fy": 881.2,
  "cx": 964.3,
  "cy": 538.1,
  "k1": -0.027,
  "k2": 0.013
}
```

**When to recalibrate:**
- Values outside expected ranges
- Physical damage to camera lens
- Fogging or condensation inside lens housing

**Recalibration procedure:** Contact Luxonis support or use their calibration tool (not covered in this guide).

---

## 3. Hand-Eye Extrinsic Calibration

**Purpose:** Determine the precise transform between robot base and camera frame

**Frequency:** 
- After camera mount changes
- After base/frame realignment
- If pick accuracy degrades beyond ±10mm

### 3.1 ArUco Board Capture

**Setup:**

1. **Print ArUco calibration board:**
   - Pattern: 6x6 ArUco markers
   - Marker size: 50mm
   - Spacing: 10mm
   - Board size: ~400mm x 400mm
   - Mount on rigid flat surface

2. **Place board in workspace:**
   - Fixed position relative to robot base
   - Within camera field of view (0.3m - 1.5m distance)
   - Good lighting (avoid shadows and glare)

**Capture Procedure:**

1. **Launch calibration mode:**
   ```bash
   ros2 launch yanthra_move pragati_complete.launch.py \
     bringup_calibration:=true
   ```
   
   **Note:** This launches only camera and robot_state_publisher, not full system

2. **Run ArUco detection script:**
   ```bash
   # Navigate to OakDTools directory
   cd ~/Downloads/pragati_ros2/install/cotton_detection_ros2/lib/cotton_detection_ros2/OakDTools
   
   # Run ArUco detection
   python3 ArucoDetectYanthra.py
   ```

3. **Capture multiple poses:**
   - Move robot arm to various positions (at least 15-20 poses)
   - Keep ArUco board visible in camera at all poses
   - Vary orientation and distance
   - Script automatically saves pose data

4. **Review captured data:**
   ```bash
   ls ~/.ros/calibration/aruco_poses_*.yaml
   ```

**Quality Check:**
- Minimum 15 successful poses captured
- Poses span full workspace volume
- Reprojection error < 2 pixels per pose

---

### 3.2 Compute Hand-Eye Transform

**Using captured data to calculate camera-to-base transform:**

**Option A: Automated (if available):**
```bash
ros2 run pattern_finder hand_eye_calibration \
  --input ~/.ros/calibration/aruco_poses_*.yaml \
  --output ~/.ros/calibration/hand_eye_transform.yaml
```

**Option B: External tool (easy_handeye or similar):**
```bash
# Install if not present
pip3 install easy-handeye

# Run calibration
rosrun easy_handeye calibrate \
  --planning_group manipulator \
  --eye_on_base \
  --tracking_marker aruco_marker_6x6
```

**Output:** Transform from `base_link` to `camera_link`

Example result:
```yaml
translation:
  x: 0.285
  y: -0.410
  z: 0.385
rotation:
  x: 0.0
  y: 0.7071
  z: 0.0
  w: 0.7071
```

---

### 3.3 Update URDF

**Apply calibrated transform to robot description:**

1. **Locate current URDF:**
   ```bash
   cd ~/Downloads/pragati_ros2/src/robo_description/urdf
   
   # Find active URDF (check launch file or use MASTERCOPY)
   ls -lh URDF_REP103_EYETOHAND_MASTERCOPY*.urdf
   ```

2. **Backup current URDF:**
   ```bash
   cp URDF ~/Downloads/pragati_ros2/src/robo_description/urdf/calibrated_urdf/URDF_backup_$(date +%Y%m%d).urdf
   ```

3. **Edit camera joint transform:**
   
   Find the `camera_link_joint` or similar joint in URDF:
   ```xml
   <joint name="camera_link_joint" type="fixed">
     <origin xyz="0.285 -0.410 0.385" rpy="0 1.5708 0"/>
     <parent link="base_link"/>
     <child link="camera_link"/>
   </joint>
   ```
   
   Update `xyz` and `rpy` with calibrated values:
   - `xyz`: Translation from calibration
   - `rpy`: Convert quaternion to roll-pitch-yaw (use online calculator or Python)

4. **Save with calibration date:**
   ```bash
   cp URDF ~/Downloads/pragati_ros2/src/robo_description/urdf/calibrated_urdf/URDF_REP103_Calibrated_$(date +%d%b%Y).urdf
   ```

5. **Update symlink or launch file to use new URDF:**
   ```bash
   # If using symlink
   ln -sf calibrated_urdf/URDF_REP103_Calibrated_08Oct2025.urdf URDF
   ```

---

### 3.4 TF Validation

**Verify the calibrated transform is correct:**

1. **Launch full system:**
   ```bash
   ros2 launch yanthra_move pragati_complete.launch.py
   ```

2. **Check transform chain:**
   ```bash
   # Generate TF tree
   ros2 run tf2_tools view_frames
   
   # Open generated PDF
   evince frames.pdf
   ```
   
   **Expected chain:**
   ```
   world → base_link → camera_link → camera_color_optical_frame
   ```

3. **Echo specific transform:**
   ```bash
   ros2 run tf2_ros tf2_echo base_link camera_link
   ```
   
   **Check:**
   - Translation matches calibrated values (±5mm tolerance)
   - Rotation matches expected orientation
   - Transform is static (doesn't change over time)

4. **Physical validation:**
   - Place object at known base_link coordinates
   - Check camera detects object at same coordinates
   - Error should be < 10mm for good calibration

---

## 4. System Validation

**Final checks before operational use:**

### 4.1 Joint Position Accuracy

```bash
# Test each joint individually
ros2 service call /motor/move_joint motor_control_ros2/srv/JointPositionCommand \
  "{joint_id: 2, target_position: 0.5, max_velocity: 0.5}"

# Check actual vs commanded position
ros2 topic echo /joint_states
```

**Acceptance Criteria:**
- Position error < 0.5° for rotary joints
- Position error < 0.5mm for prismatic joints
- Settling time < 1.0s
- No oscillation

---

### 4.2 Camera Detection Test

```bash
# Place test cotton target in workspace
# Trigger detection
ros2 service call /cotton_detection/detect \
  cotton_detection_ros2/srv/CottonDetection \
  "{detect_command: 1}"

# Check detection results
ros2 topic echo /cotton_detection/results --once
```

**Expected:**
- Target detected with confidence > 0.80
- 3D position within ±10mm of actual position
- Detection latency < 200ms

---

### 4.3 Coordinated Pick Test

```bash
# This requires manual test with cotton target
# Place target at known position
# Command pick operation via yanthra_move
# Measure pick success rate

# Target: 95% pick success rate for targets in optimal zone
```

---

### 4.4 System Health Check

```bash
# Check disk space
ros2 topic echo /system/disk_usage --once
# Should show > 2GB free

# Check log rotation is active
ls -lh ~/.ros/logs/
# Should see *.log and *.log.1, *.log.2 files

# Check all nodes running
ros2 node list
```

**Expected nodes:**
- `/robot_state_publisher`
- `/joint_state_publisher`
- `/motor_controller` or `/odrive_service_node`
- `/yanthra_move`
- `/disk_space_monitor`
- (optional) `/cotton_detect_ros2_wrapper`

---

## Troubleshooting

### Issue: Joint Won't Home

**Symptoms:** Homing service returns `success: false`

**Possible Causes:**
1. Motor not enabled
2. Mechanical obstruction
3. Encoder not connected
4. Limit switch failure

**Solutions:**
```bash
# Check motor enable status
ros2 topic echo /joint_states
# Look for "effort" field - should be non-zero if enabled

# Try manual enable
ros2 service call /motor/enable motor_control_ros2/srv/MotorCalibration \
  "{joint_id: 2, full_calibration: false, timeout: 5.0}"

# Check for errors
ros2 topic echo /diagnostics
```

---

### Issue: Camera Not Detected

**Symptoms:** `lsusb` doesn't show Luxonis device

**Solutions:**
1. **Check USB connection:**
   ```bash
   # Try different USB port
   # Use USB 2.0 port (NOT USB 3.0 - known issue)
   ```

2. **Check USB permissions:**
   ```bash
   # Add udev rule
   echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | \
     sudo tee /etc/udev/rules.d/80-movidius.rules
   sudo udevadm control --reload-rules
   ```

3. **Restart camera node:**
   ```bash
   ros2 node kill /cotton_detect_ros2_wrapper
   # It should auto-restart in launch file
   ```

---

### Issue: Large Position Errors After Calibration

**Symptoms:** Pick attempts consistently miss by > 20mm

**Root Causes:**
- Insufficient ArUco poses captured
- Camera mount moved since calibration
- URDF not updated correctly
- Mechanical play in joints

**Diagnostic:**
```bash
# Check TF is correct
ros2 run tf2_ros tf2_echo base_link camera_link

# Manually measure camera position relative to base
# Compare with TF output

# Check for mechanical play
# Manually move joints - should have minimal backlash
```

**Solution:** Re-run hand-eye calibration with more poses (25-30)

---

### Issue: Encoder Drift Over Time

**Symptoms:** Position error increases during operation

**Solutions:**
1. **Check encoder connections:**
   - Loose connector
   - Damaged cable
   - EMI interference

2. **Recalibrate more frequently:**
   - Daily calibration for critical operations
   - Use absolute encoders if possible

3. **Enable automatic recalibration:**
   - Add periodic homing to operation loop
   - Check encoder health in diagnostics

---

## Maintenance Schedule

### Daily (Production Use)
- [ ] Visual inspection of robot and camera
- [ ] Verify joint positions match commanded (quick check)
- [ ] Check disk space: `ros2 topic echo /system/disk_usage`

### Weekly
- [ ] Full joint homing sequence
- [ ] Verify encoder calibration (check for drift)
- [ ] Clean camera lens
- [ ] Check mechanical tightness (bolts, mounts)

### Monthly
- [ ] Full calibration validation
- [ ] Review and archive old logs
- [ ] Backup calibration files
- [ ] Update URDF if needed

### After Maintenance/Transport
- [ ] Complete full calibration (Section 1-3)
- [ ] System validation (Section 4)
- [ ] Document any changes in calibration log

---

## Calibration Log Template

Keep a record of all calibrations:

```
Date: ____________
Operator: ____________
Reason: [ ] Routine [ ] After maintenance [ ] Position errors [ ] Other: ______

Motor Calibration:
- Joint 2: [ ] Homed [ ] Encoder calibrated [ ] Saved
- Joint 3: [ ] Homed [ ] Encoder calibrated [ ] Saved
- Joint 4: [ ] Homed [ ] Encoder calibrated [ ] Saved
- Joint 5: [ ] Homed [ ] Encoder calibrated [ ] Saved

Camera Calibration:
- Intrinsics verified: [ ] Yes [ ] No
- ArUco poses captured: _______ (minimum 15)
- Hand-eye computed: [ ] Yes [ ] No
- URDF updated: [ ] Yes [ ] No

Validation Results:
- Joint position error: _______ mm/degrees (< 0.5 acceptable)
- Detection accuracy: _______ mm (< 10mm acceptable)
- Pick success rate: _______ % (> 95% target)

Notes:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

Sign-off: ____________
```

---

## References

### Service Definitions
- `motor_control_ros2/srv/JointHoming`
- `motor_control_ros2/srv/MotorCalibration`
- `motor_control_ros2/srv/EncoderCalibration`
- `cotton_detection_ros2/srv/CottonDetection`

### Related Documentation
- `docs/IMPLEMENTATION_PLAN_OCT2025.md` - Overall system refactoring plan
- `src/motor_control_ros2/README.md` - Motor control package details
- `src/cotton_detection_ros2/README.md` - Camera detection details
- `src/robo_description/urdf/` - Robot URDF files

### External Resources
- [ROS2 TF2 Tutorial](https://docs.ros.org/en/humble/Tutorials/Intermediate/Tf2/Tf2-Main.html)
- [ArUco Markers](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html)
- [Hand-Eye Calibration Theory](http://arxiv.org/abs/1808.03816)

---

**Document Version History:**
- v1.0 (Oct 8, 2025): Initial comprehensive guide (Tier 2.2)

**Maintained by:** Pragati Robotics Team
