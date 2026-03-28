# Manual Motor Testing Steps (Run on Raspberry Pi)

## Setup

SSH to Raspberry Pi and run these commands in separate terminals:

```bash
ssh ubuntu@192.168.137.253
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

---

## Phase 2: Test with Motor Controller Node

Since `mg6010_test_node` isn't available, we'll test directly with the controller node.

### Terminal 1: Start Motor Controller

```bash
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args --params-file src/motor_control_ros2/config/mg6010_two_motors.yaml
```

**Watch for:**
- `[mg6010_controller_node] Initializing with 2 motors`
- `[mg6010_controller_node] Motor 0: CAN ID 141, Joint: joint3`
- `[mg6010_controller_node] Motor 1: CAN ID 143, Joint: joint5`
- `[mg6010_controller_node] All motors initialized successfully`

**If fails:** Check error messages, CAN interface, motor power

---

### Terminal 2: Monitor Joint States

```bash
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 topic echo /joint_states
```

**Expected output (updating continuously):**
```yaml
name:
- joint3
- joint5
position:
- X.XXX  # joint3 position
- X.XXX  # joint5 position
```

**✅ PASS if:** Both joints appear and positions update  
**❌ FAIL if:** joint_states not publishing or missing joints

---

### Terminal 3: Test Joint 3 (Motor 1)

```bash
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Command joint3 to move to 1.0 rad
ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 "{data: 1.0}"
```

**Watch Terminal 1 for:**
```
[mg6010_controller_node] Received position command for joint3: 1.000 rad
```

**Watch Terminal 2 (/joint_states) for:**
- position[0] (joint3) should change toward 1.0

**Physical Check:**
- ✅ Motor 1 should PHYSICALLY MOVE
- ✅ You should hear/see the motor rotating

**Test returning to zero:**
```bash
ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 "{data: 0.0}"
```

---

### Terminal 3: Test Joint 5 (Motor 2)

```bash
# Command joint5 to move to 0.5 rad
ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.5}"
```

**Watch Terminal 1 for:**
```
[mg6010_controller_node] Received position command for joint5: 0.500 rad
```

**Watch Terminal 2 (/joint_states) for:**
- position[1] (joint5) should change toward 0.5

**Physical Check:**
- ✅ Motor 2 should PHYSICALLY MOVE
- ✅ You should hear/see the motor moving

**❌ IF JOINT 5 DOESN'T MOVE:**
This confirms the issue we're investigating!

**Test returning to zero:**
```bash
ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.0}"
```

---

## Diagnostic Commands

### Check CAN Traffic

Open another terminal and monitor CAN bus:

```bash
candump can0
```

**When you send joint5 command, look for:**
```
can0  143  [8]  A4 XX XX XX XX XX XX XX  # Position command to motor 2
can0  143  [8]  9C XX XX XX XX XX XX XX  # Response from motor 2
```

**If no traffic for CAN ID 143:** Motor controller isn't sending commands  
**If traffic but no response:** Motor 2 hardware issue

---

### Check Motor Controller Logs

In Terminal 1 (mg6010_controller_node), watch for:

```
[mg6010_controller_node] Received position command for joint5: X.XXX rad
[mg6010_controller_node] Sending CAN command to motor ID 143
```

**If you see "Received" but not "Sending":** Issue in motor controller code  
**If you don't see "Received":** Commands aren't reaching the node

---

### Check Configuration

```bash
cat ~/pragati_ros2/src/motor_control_ros2/config/mg6010_two_motors.yaml
```

**Verify:**
- `motor_count: 2`
- `motor_ids: [141, 143]`
- `node_ids: [1, 3]`
- `joint_names: ["joint3", "joint5"]`

---

## Test Results Template

Fill this out as you test:

```
## Phase 2 Results - [DATE/TIME]

### Motor Controller Initialization
- [ ] Node started successfully
- [ ] Initialized with 2 motors
- [ ] No initialization errors
- Notes: ___

### Joint States Publishing
- [ ] /joint_states topic publishing
- [ ] Both joint3 and joint5 in name array
- [ ] Position values updating
- Notes: ___

### Joint 3 (Motor 1, CAN 141) Testing
- [ ] Received command logged in Terminal 1
- [ ] Motor physically moved
- [ ] Joint states updated
- [ ] Encoder feedback accurate
- Notes: ___

### Joint 5 (Motor 2, CAN 143) Testing
- [ ] Received command logged in Terminal 1
- [ ] Motor physically moved  ← KEY TEST!
- [ ] Joint states updated
- [ ] Encoder feedback accurate
- Notes: ___

### CAN Traffic (candump)
- [ ] Traffic seen for CAN ID 141 (joint3)
- [ ] Traffic seen for CAN ID 143 (joint5)
- [ ] Responses received from both motors
- Notes: ___

## Summary
- Motor 1 (joint3): PASS / FAIL
- Motor 2 (joint5): PASS / FAIL

Issue identified: ___
```

---

## What to Report Back

Please report:

1. **Did joint3 (motor 1) move?** YES / NO
2. **Did joint5 (motor 2) move?** YES / NO
3. **Did you see "Received position command for joint5" in Terminal 1?** YES / NO
4. **Did position[1] update in /joint_states?** YES / NO
5. **Did you see CAN traffic for ID 143 in candump?** YES / NO
6. **Any error messages?** (paste them)

This will tell us exactly where the problem is!
