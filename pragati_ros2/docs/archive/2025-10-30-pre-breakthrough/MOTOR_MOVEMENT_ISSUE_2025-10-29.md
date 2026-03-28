# Motor Movement Failure After Detection - Diagnostic

**Date**: 2025-10-29  
**Issue**: Motors receive commands but don't move in integrated pipeline  
**Impact**: CRITICAL - Blocks entire pick & place workflow

---

## 🚨 Problem Summary

**What Works:**
- ✅ CAN communication (telemetry reading)
- ✅ Motor status reading (temp, voltage, position)
- ✅ Detection system (5-8s, needs C++ fix)
- ✅ Coordinate transformation

**What Doesn't Work:**
- ❌ Motor position commands are sent but **motors don't move**
- ❌ Encoder feedback returns EMPTY
- ❌ Script thinks it succeeded (false positive)

---

## 📊 Evidence from Test Log

```bash
Moving to Cotton #1:
  Target: J3=0.019 J4=0.014 J5=0.061 rad

  [1/3] Moving Joint3 to 0.019 rad...
        Encoder feedback:  rad          # ← EMPTY!
  [2/3] Moving Joint4 to 0.014 rad...
        Encoder feedback:  rad          # ← EMPTY!
  [3/3] Moving Joint5 to 0.061 rad...
        Encoder feedback:  rad          # ← EMPTY!
  ✓ All motors commanded and verified  # ← FALSE POSITIVE!
```

**Expected:** Encoder feedback should show actual position (e.g., "32734 counts" or "0.019 rad")  
**Actual:** Empty string - motor position not being read

---

## 🔍 Root Cause Analysis

### Hypothesis 1: Position Control Mode Not Enabled
**Problem:** Motors may be in wrong control mode (velocity/torque instead of position)

**Check:**
```bash
# On RPi, check motor control mode
ros2 service call /motor_control/get_status motor_control_ros2/srv/MotorStatus "{motor_id: 1}"

# Look for: control_mode field
# Should be: POSITION_CONTROL (mode 3)
# Might be: VELOCITY_CONTROL or TORQUE_CONTROL
```

**Fix if needed:**
```bash
# Set to position control mode
ros2 service call /motor_control/set_mode motor_control_ros2/srv/SetControlMode \
    "{motor_id: 1, mode: 3}"  # 3 = POSITION_CONTROL
```

---

### Hypothesis 2: Position Commands Not Reaching Motors
**Problem:** Service call succeeds but CAN message never sent

**Check:**
```bash
# Monitor CAN bus during movement command
candump can0 &

# Then trigger movement
ros2 service call /motor_control/move_joint ...

# Look for: 0x7E1, 0x7E2, 0x7E3 (motor IDs)
# Should see: Position command frames (0x602 or similar)
```

**What to look for:**
- No CAN traffic = service not sending commands
- CAN traffic but motors don't respond = motor firmware issue
- Wrong CAN message format = protocol mismatch

---

### Hypothesis 3: Motor Enable State Lost
**Problem:** Motors were enabled for test but disabled in integrated system

**Check:**
```bash
# Check if motors are enabled
ros2 topic echo /motor_status

# Look for: motor_enabled: true
# If false, motors won't respond to position commands
```

**Fix:**
```bash
# Enable motors
ros2 service call /motor_control/enable motor_control_ros2/srv/EnableMotor \
    "{motor_id: 1, enable: true}"
```

---

### Hypothesis 4: Encoder Reading Service Not Working
**Problem:** Position commands work but encoder feedback not being read

**Check:**
```bash
# Manually read encoder
ros2 service call /motor_control/read_encoder motor_control_ros2/srv/ReadEncoder \
    "{motor_id: 1}"

# Should return: position (in counts or radians)
# If empty/error: Encoder reading broken
```

---

### Hypothesis 5: Wrong Service/Topic Being Called
**Problem:** Script calls service that doesn't actually control motors

**Check test_full_pipeline.sh:**
```bash
# Find what service/topic it's using for movement
grep -n "ros2.*service.*move" test_full_pipeline.sh
grep -n "ros2.*topic.*pub.*position" test_full_pipeline.sh
```

**Common issues:**
- Calling wrong service name
- Using test service instead of production service
- Topic vs service mismatch

---

## 🔧 Diagnostic Steps for Tomorrow

### Step 1: Verify Motor Enable State (2 min)
```bash
# Launch system
ros2 launch yanthra_move pragati_complete.launch.py

# Wait for homing to complete
# Then check motor status
ros2 service call /motor_status motor_control_ros2/srv/MotorStatus "{motor_id: 1}"
ros2 service call /motor_status motor_control_ros2/srv/MotorStatus "{motor_id: 2}"
ros2 service call /motor_status motor_control_ros2/srv/MotorStatus "{motor_id: 3}"

# Verify:
# - motor_enabled: true
# - control_mode: POSITION_CONTROL (or mode 3)
# - error_flags: 0x00
```

---

### Step 2: Test Manual Position Command (5 min)
```bash
# Try moving Joint3 by 0.01 rad manually
ros2 service call /motor_control/move_joint motor_control_ros2/srv/MoveJoint \
    "{joint_id: 3, target_position: 0.01, max_velocity: 0.1}"

# Observe:
# - Does motor actually move?
# - Does encoder position change?
# - Any error messages in logs?
```

---

### Step 3: Monitor CAN Bus During Command (5 min)
```bash
# Terminal 1: Monitor CAN
candump can0

# Terminal 2: Send movement command
ros2 service call /motor_control/move_joint motor_control_ros2/srv/MoveJoint \
    "{joint_id: 3, target_position: 0.01}"

# Check Terminal 1:
# - Do you see CAN frames with motor ID?
# - Format: can0  7E3  [8]  AA BB CC DD EE FF GG HH
# - If YES: Motor firmware issue
# - If NO: ROS2 service not sending CAN commands
```

---

### Step 4: Check Service Implementation (10 min)
```bash
# Find which node provides the move_joint service
ros2 service list | grep move

# Check which node owns it
ros2 service info /motor_control/move_joint

# Verify that node is running
ros2 node list | grep motor

# Check node logs for errors
ros2 log view <motor_control_node_name>
```

---

### Step 5: Compare Test vs Integrated Launch (15 min)

**Test launch that WORKED:**
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py
# This read motor status successfully
```

**Integrated launch that FAILED:**
```bash
ros2 launch yanthra_move pragati_complete.launch.py
# Motors don't respond to movement commands
```

**Check differences:**
```bash
# Compare what nodes are launched
diff \
  <(ros2 launch motor_control_ros2 mg6010_test.launch.py --show-args) \
  <(ros2 launch yanthra_move pragati_complete.launch.py --show-args)

# Look for:
# - Different motor control node
# - Missing parameters
# - Different CAN configuration
```

---

## 🎯 Quick Fixes to Try

### Fix 1: Ensure Motors Are Enabled
```bash
# After system launch, explicitly enable all motors
ros2 service call /motor_control/enable "{motor_id: 1, enable: true}"
ros2 service call /motor_control/enable "{motor_id: 2, enable: true}"
ros2 service call /motor_control/enable "{motor_id: 3, enable: true}"
```

### Fix 2: Set Position Control Mode
```bash
# Force position control mode
ros2 service call /motor_control/set_mode "{motor_id: 1, mode: 3}"
ros2 service call /motor_control/set_mode "{motor_id: 2, mode: 3}"
ros2 service call /motor_control/set_mode "{motor_id: 3, mode: 3}"
```

### Fix 3: Use Correct Service Name
Check `test_full_pipeline.sh` and ensure it's calling the right service:
```bash
# Might be calling:
/motor_control/move_joint           # ❌ Wrong?
/yanthra_move/move_joint           # ✅ Correct?
/joint_command                      # ❓ Alternative?
```

---

## 📋 Information Needed

To diagnose further, collect:

1. **Service list during integrated launch:**
   ```bash
   ros2 service list | grep -E "(motor|joint|move)"
   ```

2. **Node list:**
   ```bash
   ros2 node list
   ```

3. **Motor control node logs:**
   ```bash
   ros2 log view motor_control_node > motor_logs.txt
   ```

4. **CAN traffic capture:**
   ```bash
   candump can0 -L > can_traffic.log
   # (during movement attempt)
   ```

5. **Service call that test script uses:**
   ```bash
   grep -A5 "Moving Joint" test_full_pipeline.sh
   ```

---

## 💡 Most Likely Causes (Ranked)

1. **Motors not in position control mode** (80% likely)
   - Test node uses different mode
   - Integrated system doesn't set mode properly

2. **Wrong service being called** (15% likely)
   - Script calls non-existent or wrong service
   - Service exists but doesn't control motors

3. **Motor enable state lost after homing** (3% likely)
   - Motors enabled for homing
   - Disabled after homing completes
   - Movement commands ignored

4. **CAN bus configuration issue** (2% likely)
   - Works for reading but not writing
   - Unlikely since test worked

---

## ✅ Success Criteria

Tomorrow's test is successful when:
- [ ] Manual position command makes motor actually move
- [ ] Encoder feedback shows non-empty position
- [ ] Integrated pipeline moves motors after detection
- [ ] Movement completes in ~1s per cotton (not 75s timeout)

---

## 🔗 Related Files

- Test script: `test_full_pipeline.sh`
- Motor test launch: `motor_control_ros2/launch/mg6010_test.launch.py`
- Integrated launch: `yanthra_move/launch/pragati_complete.launch.py`
- Test results: `HARDWARE_TEST_RESULTS_2025-10-29.md`

---

**Priority**: 🔴 **CRITICAL** - Must fix before cotton picking can work  
**Estimated Debug Time**: 30-60 minutes  
**Complexity**: Medium (service/parameter configuration issue, not hardware)
