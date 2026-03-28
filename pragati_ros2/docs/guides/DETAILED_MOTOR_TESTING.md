# Detailed Motor Testing and Evaluation Guide

## Overview

This guide provides step-by-step procedures for testing individual motors in isolation, verifying motor configuration, and diagnosing issues with specific joints. This is specifically tailored for the current 2-motor setup (joint3 and joint5).

**Current System Configuration:**
- Motor 1: CAN ID 141, Node ID 1 → Joint 3 (rotation)
- Motor 2: CAN ID 143, Node ID 3 → Joint 5 (linear extension)

---

## Prerequisites

### 1. Hardware Setup
```bash
# Verify CAN interface is up
ip link show can0

# If not up, configure it
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Verify CAN state
ip -details link show can0
# Should show: state UP, CAN state ERROR-ACTIVE
```

### 2. Workspace Setup
```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash
```

---

## Test Procedure Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Individual Motor Hardware Tests (Raw CAN)         │
│   → Test each motor independently using mg6010_test_node    │
│   → Verify basic communication, status, movement            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: ROS2 Controller Integration Tests                  │
│   → Test motors through mg6010_controller_node              │
│   → Verify joint_states publishing                          │
│   → Verify position commands work correctly                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: Full System Integration Tests                      │
│   → Test with yanthra_move integration                      │
│   → Verify end-to-end cotton detection → motor movement     │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Individual Motor Hardware Tests

These tests use `mg6010_test_node` to directly control motors via CAN, bypassing all higher-level control systems.

### Test 1.1: Motor 1 (Joint 3) - Basic Validation

**Terminal 1: Run Motor Test Node**
```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash

ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p can_id:=141 -p node_id:=1
```

**Terminal 2: Execute Test Commands**

#### Step 1: Check Motor Status
```bash
source install/setup.bash
ros2 service call /mg6010_test/read_status std_srvs/srv/Trigger
```

**Expected Output:**
```
success: True
message: 'Temperature: XX.X°C, Voltage: 48.X V, Error Code: 0x00'
```

**✅ Pass Criteria:**
- Service returns success
- Temperature reading between 25-50°C
- Voltage reading ~48V
- Error code 0x00 (no errors)

**❌ If Failed:**
- Check CAN interface is UP
- Verify motor power supply is ON
- Check CAN ID matches motor configuration
- Run `candump can0` to see if motor responds

---

#### Step 2: Read Encoder Position
```bash
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger
```

**Expected Output:**
```
success: True
message: 'Multi-turn angle: X.XX rad'
```

**✅ Pass Criteria:**
- Service returns success
- Reading shows actual motor position in radians

**❌ If Failed:**
- Motor encoder may be faulty
- Check CAN communication with candump

---

#### Step 3: Enable Motor
```bash
ros2 service call /mg6010_test/motor_on std_srvs/srv/Trigger
```

**Expected Output:**
```
success: True
message: 'Motor enabled successfully'
```

**Physical Check:**
- Motor should hold position (slight resistance if you try to move it manually)

---

#### Step 4: Test Position Control
```bash
# Move to +1.0 radian
ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
  "{position_rad: 1.0, max_speed_rpm: 100}"

# Wait 5 seconds, then check position
sleep 5
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger
```

**Expected Output:**
- Motor should physically MOVE
- Encoder reading should be close to 1.0 rad (±0.05 rad tolerance)

**✅ Pass Criteria:**
- Motor moves visibly
- Final position within ±0.05 rad of target
- No error messages

**❌ If Failed - Motor doesn't move:**
- Check motor power
- Verify motor is enabled (motor_on was successful)
- Check CAN bus for errors: `ip -details link show can0`
- Try manual CAN command: `cansend can0 141#8800000000000000` (motor on)

**❌ If Failed - Motor moves but wrong position:**
- Check transmission_factor in config
- Verify direction_inverted setting

---

#### Step 5: Test Different Positions
```bash
# Move to -0.5 radian
ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
  "{position_rad: -0.5, max_speed_rpm: 100}"

sleep 5
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger

# Move back to 0.0 (home)
ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
  "{position_rad: 0.0, max_speed_rpm: 100}"

sleep 5
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger
```

**✅ Pass Criteria:**
- Motor reaches all positions accurately
- Movement is smooth
- No mechanical binding or unusual sounds

---

#### Step 6: Disable Motor
```bash
ros2 service call /mg6010_test/motor_off std_srvs/srv/Trigger
```

**Physical Check:**
- Motor should be free to move manually (no holding torque)

---

### Test 1.2: Motor 2 (Joint 5) - Basic Validation

Repeat the exact same procedure as Test 1.1, but with different parameters:

**Terminal 1:**
```bash
ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p can_id:=143 -p node_id:=3
```

Then execute all 6 steps from Test 1.1 in Terminal 2.

**Key Difference:**
- Joint 5 is linear, so position changes might be harder to see visually
- Monitor encoder feedback closely

---

### Test 1.3: Quick Automated Test Script

For rapid validation of both motors:

**Create test script:**
```bash
cat > ~/Downloads/pragati_ros2/test_individual_motors.sh << 'EOF'
#!/bin/bash

set -e

source ~/Downloads/pragati_ros2/install/setup.bash

echo "======================================"
echo "Testing Motor 1 (Joint 3) - CAN ID 141"
echo "======================================"

# Start test node in background
ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p can_id:=141 -p node_id:=1 &
TEST_NODE_PID=$!

sleep 3

echo "1. Reading motor status..."
ros2 service call /mg6010_test/read_status std_srvs/srv/Trigger

echo "2. Reading encoder..."
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger

echo "3. Enabling motor..."
ros2 service call /mg6010_test/motor_on std_srvs/srv/Trigger

sleep 1

echo "4. Testing position +1.0 rad..."
ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
  "{position_rad: 1.0, max_speed_rpm: 100}"

sleep 5

echo "5. Reading final position..."
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger

echo "6. Disabling motor..."
ros2 service call /mg6010_test/motor_off std_srvs/srv/Trigger

# Kill test node
kill $TEST_NODE_PID
sleep 2

echo ""
echo "======================================"
echo "Testing Motor 2 (Joint 5) - CAN ID 143"
echo "======================================"

# Start test node in background
ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p can_id:=143 -p node_id:=3 &
TEST_NODE_PID=$!

sleep 3

echo "1. Reading motor status..."
ros2 service call /mg6010_test/read_status std_srvs/srv/Trigger

echo "2. Reading encoder..."
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger

echo "3. Enabling motor..."
ros2 service call /mg6010_test/motor_on std_srvs/srv/Trigger

sleep 1

echo "4. Testing position +1.0 rad..."
ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
  "{position_rad: 1.0, max_speed_rpm: 100}"

sleep 5

echo "5. Reading final position..."
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger

echo "6. Disabling motor..."
ros2 service call /mg6010_test/motor_off std_srvs/srv/Trigger

# Kill test node
kill $TEST_NODE_PID

echo ""
echo "======================================"
echo "Motor Testing Complete!"
echo "======================================"
EOF

chmod +x ~/Downloads/pragati_ros2/test_individual_motors.sh
```

**Run automated test:**
```bash
~/Downloads/pragati_ros2/test_individual_motors.sh
```

---

## Phase 2: ROS2 Controller Integration Tests

Now test motors through the full ROS2 control stack.

### Test 2.1: Motor Controller Node - Joint States Publishing

**Terminal 1: Start Motor Controller**
```bash
cd ~/Downloads/pragati_ros2
source install/setup.bash

ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args --params-file src/motor_control_ros2/config/mg6010_two_motors.yaml
```

**Expected Output:**
```
[mg6010_controller_node] Initializing with 2 motors
[mg6010_controller_node] Motor 0: CAN ID 141, Joint: joint3
[mg6010_controller_node] Motor 1: CAN ID 143, Joint: joint5
[mg6010_controller_node] All motors initialized successfully
```

**Terminal 2: Monitor Joint States**
```bash
source install/setup.bash
ros2 topic echo /joint_states
```

**Expected Output (should update continuously):**
```yaml
header:
  stamp:
    sec: XXXXX
    nanosec: XXXXX
  frame_id: ''
name:
- joint3
- joint5
position:
- X.XXX  # Current position of joint3 in radians
- X.XXX  # Current position of joint5 in radians
velocity: [0.0, 0.0]
effort: [0.0, 0.0]
```

**✅ Pass Criteria:**
- /joint_states topic publishes at ~10 Hz
- Both joint3 and joint5 appear in name array
- Position values update when motors move

**❌ If Failed:**
- Check Terminal 1 for initialization errors
- Verify YAML config has correct motor count
- Check CAN communication with `candump can0`

---

### Test 2.2: Command Individual Joints via Topics

**Terminal 1: Keep mg6010_controller_node running**

**Terminal 2: Command Joint 3**
```bash
source install/setup.bash

# Command joint3 to position 1.0 rad
ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 "{data: 1.0}"
```

**Watch for:**
- Terminal 1 should show: "Received position command for joint3: 1.000 rad"
- Motor 1 should physically MOVE
- /joint_states should show joint3 position approaching 1.0

**Terminal 3: Monitor Joint States**
```bash
ros2 topic echo /joint_states --field position
```

**Watch position[0] (joint3) change to ~1.0**

---

**Terminal 2: Command Joint 5**
```bash
# Command joint5 to position 0.5 rad
ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.5}"
```

**Watch for:**
- Terminal 1 should show: "Received position command for joint5: 0.500 rad"
- Motor 2 should physically MOVE
- /joint_states should show joint5 position approaching 0.5

---

### Test 2.3: Verify Each Joint Independently

Create a test to verify each joint responds correctly:

**Test Joint 3 Only:**
```bash
# Terminal 2: Command joint3 through full range
for pos in 0.0 0.5 1.0 0.5 0.0; do
  echo "Moving joint3 to $pos rad"
  ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 "{data: $pos}"
  sleep 5
done
```

**Watch Terminal 3 (/joint_states) to confirm:**
- position[0] (joint3) follows commands
- position[1] (joint5) stays constant (doesn't move)

---

**Test Joint 5 Only:**
```bash
# Terminal 2: Command joint5 through range
for pos in 0.0 0.3 0.6 0.3 0.0; do
  echo "Moving joint5 to $pos rad"
  ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 "{data: $pos}"
  sleep 5
done
```

**Watch Terminal 3 (/joint_states) to confirm:**
- position[1] (joint5) follows commands
- position[0] (joint3) stays constant (doesn't move)

---

### Test 2.4: Configuration Verification

**Verify motor configuration matches reality:**

```bash
# Check current config
cat ~/Downloads/pragati_ros2/src/motor_control_ros2/config/mg6010_two_motors.yaml
```

**Key parameters to verify:**

```yaml
mg6010_controller_node:
  ros__parameters:
    motor_count: 2  # MUST BE 2

    # Motor 1 → Joint 3
    motor_ids: [141, 143]
    node_ids: [1, 3]
    joint_names: ["joint3", "joint5"]
    
    # Transmission factors (ratio between motor and joint)
    # Check these match your mechanical setup
    transmission_factors: [1.0, 1.0]  # Adjust if needed
    
    # Direction inversion
    direction_inverted: [false, false]  # Flip if motor goes wrong direction
```

**Test direction inversion if needed:**
If motor goes opposite direction than expected:

1. Edit config:
```yaml
direction_inverted: [true, false]  # Invert joint3
```

2. Rebuild and test:
```bash
colcon build --packages-select motor_control_ros2
source install/setup.bash
# Re-run test
```

---

## Phase 3: Full System Integration Tests

Test motors with yanthra_move integration.

### Test 3.1: System Launch with Motor Controller

**Terminal 1: Motor Controller**
```bash
source install/setup.bash
ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args --params-file src/motor_control_ros2/config/mg6010_two_motors.yaml
```

**Terminal 2: Yanthra Move**
```bash
source install/setup.bash
ros2 launch yanthra_move yanthra_move_launch.py simulation_mode:=true
```

**Terminal 3: Monitor Joint States**
```bash
source install/setup.bash
ros2 topic echo /joint_states --field position
```

**Terminal 4: Trigger START and Detection**
```bash
source install/setup.bash

# Send start signal
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"

# Wait for "Waiting for cotton detection" message, then:
./test_cotton_detection_publisher.py --single --count 1
```

**Expected Behavior:**
1. Yanthra_move processes cotton detection
2. Publishes joint commands to /joint3_position_controller/command and /joint5_position_controller/command
3. Motor controller receives commands
4. **Both motors physically move** through pick sequence
5. Motors return to parking positions
6. /joint_states updates throughout

**✅ Pass Criteria:**
- Both joint3 AND joint5 move during pick sequence
- Joint states update throughout motion
- System completes pick cycle without errors

**❌ If One Motor Doesn't Move:**
- Check which joint isn't moving in /joint_states
- Verify that joint receives commands: `ros2 topic echo /jointX_position_controller/command`
- Check motor controller logs for that specific motor

---

## Diagnostic Procedures

### Issue: Joint 5 Not Moving

**Step 1: Verify Motor Hardware**
```bash
# Test motor 2 independently
ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p can_id:=143 -p node_id:=3

# In another terminal:
ros2 service call /mg6010_test/motor_on std_srvs/srv/Trigger
ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
  "{position_rad: 0.5, max_speed_rpm: 100}"
```

**If motor moves:** Hardware is OK, issue is in ROS2 integration  
**If motor doesn't move:** Hardware issue (check power, CAN, mechanical binding)

---

**Step 2: Verify Commands Reach Motor Controller**
```bash
# Monitor joint5 commands
ros2 topic echo /joint5_position_controller/command
```

**Trigger a detection and check if commands appear**

**If commands appear:** Motor controller is receiving them  
**If no commands:** Yanthra_move isn't sending commands (check config)

---

**Step 3: Check Motor Controller Processing**
```bash
# Run motor controller with debug logging
ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args --params-file src/motor_control_ros2/config/mg6010_two_motors.yaml \
  --log-level debug
```

Look for lines like:
```
[mg6010_controller_node] Received position command for joint5: X.XXX rad
[mg6010_controller_node] Sending CAN command to motor ID 143
```

**If you see "Received" but not "Sending":** Issue in motor controller node  
**If you see both:** CAN issue or motor hardware issue

---

**Step 4: Check CAN Traffic**
```bash
candump can0
```

**Trigger joint5 command and watch for:**
```
can0  143  [8]  A4 XX XX XX XX XX XX XX  # Position command to motor 2
can0  143  [8]  9C XX XX XX XX XX XX XX  # Response from motor 2
```

**If no traffic for CAN ID 143:** Motor controller not sending, or wrong CAN ID  
**If traffic but no response:** Motor hardware issue

---

### Issue: Encoder Feedback Not Updating

**Symptom:** /joint_states shows constant values even when motors move

**Step 1: Check Encoder Reading Directly**
```bash
# Test with mg6010_test_node
ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p can_id:=143 -p node_id:=3

# Read encoder
ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger
```

**If encoder reads correctly:** Issue in motor controller node feedback loop  
**If encoder doesn't read:** Motor encoder hardware issue

---

**Step 2: Verify Motor Controller Reads Encoders**

Check motor controller node logs for encoder reading messages:
```
[mg6010_controller_node] Publishing joint states: joint3=X.XX, joint5=Y.YY
```

**If missing:** joint_states publishing is broken (check recent fix)  
**If present but not updating:** Encoder commands not being sent

---

## Success Criteria Summary

### Phase 1: Individual Motor Tests
- [ ] Motor 1 (CAN 141) status reading works
- [ ] Motor 1 encoder reading works
- [ ] Motor 1 moves to commanded positions
- [ ] Motor 2 (CAN 143) status reading works
- [ ] Motor 2 encoder reading works
- [ ] Motor 2 moves to commanded positions

### Phase 2: ROS2 Integration Tests
- [ ] Motor controller node initializes with 2 motors
- [ ] /joint_states publishes continuously
- [ ] /joint_states includes both joint3 and joint5
- [ ] Joint3 moves when commanded via topic
- [ ] Joint5 moves when commanded via topic
- [ ] Encoder feedback updates in /joint_states

### Phase 3: Full System Tests
- [ ] Yanthra_move launches successfully
- [ ] Cotton detection triggers motion sequence
- [ ] Both joint3 and joint5 move during pick sequence
- [ ] Motors return to parking positions
- [ ] Full cycle completes without errors

---

## Test Result Template

Use this template to document your test results:

```markdown
# Motor Test Results - [DATE]

## System Info
- ROS2 Distribution: Jazzy
- Workspace: ~/Downloads/pragati_ros2
- CAN Bitrate: 500000
- Motor Count: 2

## Phase 1: Individual Motor Tests

### Motor 1 (Joint 3 - CAN ID 141)
- [ ] Status reading: PASS/FAIL - Notes: ___
- [ ] Encoder reading: PASS/FAIL - Notes: ___
- [ ] Motor enable: PASS/FAIL - Notes: ___
- [ ] Position +1.0 rad: PASS/FAIL - Actual: ___ - Notes: ___
- [ ] Position -0.5 rad: PASS/FAIL - Actual: ___ - Notes: ___
- [ ] Position 0.0 rad: PASS/FAIL - Actual: ___ - Notes: ___

### Motor 2 (Joint 5 - CAN ID 143)
- [ ] Status reading: PASS/FAIL - Notes: ___
- [ ] Encoder reading: PASS/FAIL - Notes: ___
- [ ] Motor enable: PASS/FAIL - Notes: ___
- [ ] Position +1.0 rad: PASS/FAIL - Actual: ___ - Notes: ___
- [ ] Position -0.5 rad: PASS/FAIL - Actual: ___ - Notes: ___
- [ ] Position 0.0 rad: PASS/FAIL - Actual: ___ - Notes: ___

## Phase 2: ROS2 Integration Tests
- [ ] Controller node initialization: PASS/FAIL - Notes: ___
- [ ] /joint_states publishing: PASS/FAIL - Rate: ___ Hz
- [ ] Joint3 command response: PASS/FAIL - Notes: ___
- [ ] Joint5 command response: PASS/FAIL - Notes: ___
- [ ] Encoder feedback accuracy: PASS/FAIL - Notes: ___

## Phase 3: Full System Integration
- [ ] Yanthra_move launch: PASS/FAIL - Notes: ___
- [ ] Motion sequence execution: PASS/FAIL - Notes: ___
- [ ] Joint3 movement: PASS/FAIL - Notes: ___
- [ ] Joint5 movement: PASS/FAIL - Notes: ___
- [ ] Return to parking: PASS/FAIL - Notes: ___

## Issues Found
1. ___
2. ___

## Next Steps
1. ___
2. ___
```

---

## Related Documentation

- **Motor Controller Test Guide:** `docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md`
- **Quick Reference:** `docs/guides/MOTOR_TEST_QUICK_REF.md`
- **Configuration Guide:** `docs/guides/THREE_MOTOR_SETUP_GUIDE.md` (adapt for 2 motors)
- **Troubleshooting:** `docs/guides/TROUBLESHOOTING.md`

---

## Appendix: Useful Commands

### CAN Bus Management
```bash
# Check CAN interface status
ip -details link show can0

# Reset CAN interface
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Monitor CAN traffic
candump can0

# Send raw CAN command (motor on for CAN ID 141)
cansend can0 141#8800000000000000

# CAN statistics
ip -statistics link show can0
```

### ROS2 Debugging
```bash
# List all topics
ros2 topic list

# Check topic info (subscribers/publishers)
ros2 topic info /joint_states

# Echo topic with specific field
ros2 topic echo /joint_states --field position

# Check node info
ros2 node info /mg6010_controller_node

# List parameters
ros2 param list /mg6010_controller_node

# Get specific parameter
ros2 param get /mg6010_controller_node motor_count
```

### System Monitoring
```bash
# Monitor CPU usage
htop

# Monitor ROS2 nodes
ros2 node list

# Check ROS2 daemon
ros2 daemon status

# Restart daemon if needed
ros2 daemon stop
ros2 daemon start
```

