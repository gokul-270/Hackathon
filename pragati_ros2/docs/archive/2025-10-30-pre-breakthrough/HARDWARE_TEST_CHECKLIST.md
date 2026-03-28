# Hardware Test Checklist - Motor Commanding

**Time Required:** 5-10 minutes  
**Status:** Ready for testing

---

## Pre-Test: Deploy Code (1 minute)

```bash
# From development machine:
rsync -avz /home/uday/Downloads/pragati_ros2/install/yanthra_move/ \
    ubuntu@192.168.137.253:~/pragati_ros2/install/yanthra_move/
```

---

## Test 1: Quick Validation (2 minutes)

**Goal:** Verify motors move with cotton detection

```bash
# On RPi:
cd ~/pragati_ros2
./test_motor_commanding.sh
```

**Watch for:**
- ✅ System launches without errors
- ✅ Motor controller initializes
- ✅ Cotton detection received
- ✅ START signal processed
- ✅ **Motors physically move**

**If motors don't move:**
- Check: `tail -f /tmp/motor_commanding_test.log`
- Look for: "🚀 Commanding motors" messages

---

## Test 2: Monitor Commands (3 minutes)

**Goal:** Verify commands are being published

```bash
# Terminal 1 - Watch joint3 commands:
ros2 topic echo /joint3_position_controller/command

# Terminal 2 - Watch joint5 commands:
ros2 topic echo /joint5_position_controller/command

# Terminal 3 - Watch encoder feedback:
ros2 topic echo /joint_states
```

**Expected:**
- joint3 receives phi angles (radians)
- joint5 receives r distances (meters)
- joint_states shows position changing

---

## Test 3: Full Sequence (5 minutes)

**Goal:** Verify complete picking motion

### Run test and observe:

1. **Approach** ✅
   - Log: `🎯 Executing approach trajectory`
   - Motor: joint3 and joint5 move to cotton position

2. **Capture** ⚠️
   - Log: `Executing cotton capture sequence`
   - Motor: No movement (just waits - vacuum TODO)

3. **Retreat** ✅
   - Log: `🔙 Executing retreat trajectory`
   - Motor: joint5 retracts to homing position

4. **Home** ✅
   - Log: `🏠 Moving arm to home position`
   - Motor: Both joints move to homing positions

5. **Parking** ✅
   - Log: `🅿️ Moving arm to parking position`
   - Motor: Both joints move to parking positions

---

## Success Criteria

### ✅ Pass if:
1. Motors receive commands (seen in topic echo)
2. Motors physically move to approach position
3. Motors retract after capture wait
4. Motors move to home position
5. Motors move to parking position
6. No crashes or errors in logs

### ❌ Fail if:
1. Motors don't move at all
2. Motor controller crashes
3. Commands not published to topics
4. System hangs or times out

---

## Troubleshooting

### Problem: No motor movement

**Check 1:** Are commands being sent?
```bash
ros2 topic echo /joint3_position_controller/command
ros2 topic echo /joint5_position_controller/command
```

**Check 2:** Is motor controller running?
```bash
ros2 node list | grep mg6010
```

**Check 3:** Is CAN interface up?
```bash
ip link show can0
```

**Check 4:** Are motors initialized?
```bash
# In logs, look for:
# "✅ Initialized X / X motors successfully"
tail -f /tmp/motor_commanding_test.log | grep Initialized
```

### Problem: Commands sent but motors don't move

**Check:** Motor config file
```bash
cat ~/pragati_ros2/install/motor_control_ros2/share/motor_control_ros2/config/motors.yaml
```

Should have 2 motors configured (joint3 and joint5)

**Check:** Transmission ratios
- Verify commands are scaled correctly by transmission factors
- Check: gear_ratio in motor config

### Problem: System crashes

**Check:** Logs for stack trace
```bash
tail -100 /tmp/motor_commanding_test.log
```

Common causes:
- NULL pointer (joint_move not initialized)
- Parameter not loaded (joint init params)
- CAN bus communication error

---

## Log Markers to Watch For

### ✅ Good Signs
```
✅ Motion Controller initialized with joint3 and joint5 controllers
🎯 Executing approach trajectory to cotton at [X, Y, Z] meters
📐 Polar coordinates: r=X.XXX m, theta=X.XXX rad, phi=X.XXX rad
🚀 Commanding motors: joint3 (phi) = X.XXX rad, joint5 (r) = X.XXX m
✅ Approach trajectory completed
🔙 Executing retreat trajectory - retracting arm with cotton
✅ Retreat trajectory completed - arm retracted
🏠 Moving arm to home position (cotton drop location)
✅ Arm moved to home position
🅿️  Moving arm to parking position (safe storage)
✅ Arm moved to parking position
```

### ❌ Bad Signs
```
❌ MotionController initialized with NULL joint pointers!
❌ Position is out of reach! Skipping this cotton.
❌ Cannot initialize MotionController: joint controllers not ready
ERROR: Failed to execute approach trajectory
ERROR: Motor controller not found
```

---

## Quick Commands Reference

```bash
# List all nodes
ros2 node list

# List all topics
ros2 topic list

# Echo a topic
ros2 topic echo /topic_name

# Check parameter
ros2 param get /node_name parameter_name

# Kill test
pkill -9 -f "test_motor"
pkill -9 -f "ros2 launch"

# View logs
tail -f /tmp/motor_commanding_test.log

# Check CAN
candump can0
```

---

## Next Steps After Success

1. ✅ Document actual motor positions reached
2. ✅ Measure accuracy (commanded vs actual position)
3. ✅ Test with real cotton detection (camera)
4. ⚠️ Implement GPIO for vacuum pump
5. ⚠️ Implement GPIO for end-effector
6. ⚠️ Implement cotton drop mechanism
7. ✅ Test multiple cotton picking cycles

---

## Estimated Timeline

- **Deploy:** 1 min
- **Quick test:** 2 min
- **Monitor commands:** 3 min
- **Full sequence:** 5 min
- **Total:** ~10 minutes

**Result:** Confirmation that motors respond to cotton detection and execute full picking sequence.
