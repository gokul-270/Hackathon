# Motor Controller Integration Test Guide

This guide explains how to test and validate the motor_controller integration with yanthra_move without a camera.

## Overview

The complete system flow with **REAL MOTORS**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. test_cotton_detection_publisher.py                              │
│     Publishes fake cotton positions                                 │
│     Topic: /cotton_detection/results                                │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. yanthra_move (main software)                                    │
│     - Receives cotton positions                                     │
│     - Motion controller calculates trajectory                       │
│     - Publishes joint commands                                      │
│     Topics: /joint3_position_controller/command                     │
│            /joint4_position_controller/command                      │
│            /joint5_position_controller/command                      │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. mg6010_controller_node (motor controller)                  │
│     - Subscribes to joint commands                                  │
│     - Applies transmission factors & directions                     │
│     - Converts radians → motor angles                               │
│     - Sends CAN commands to motors                                  │
│     - Publishes joint states feedback                               │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. MG6010 Motors (real hardware via CAN bus)                       │
│     - Receive position commands                                     │
│     - Execute motion: pick → retreat → park (1700, 1700, 1700)      │
│     - Return encoder feedback                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

1. Build the workspace:
```bash
cd ~/rasfiles/pragati_ros2
colcon build --packages-select yanthra_move motor_control_ros2 cotton_detection_ros2
source install/setup.bash
```

2. Verify the test publisher script is executable:
```bash
chmod +x test_cotton_detection_publisher.py
```

---

## Test Procedures

### Test 1: Basic Single Detection Test

**Terminal 1 - Start motor controller (real motors):**
```bash
source ~/rasfiles/pragati_ros2/install/setup.bash

# Setup CAN interface first (if not already done)
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Launch motor controller node (multi-motor config with homing)
ros2 run motor_control_ros2 mg6010_controller_node --ros-args --params-file src/motor_control_ros2/config/mg6010_three_motors.yaml
```

This node:
- Initializes motors with the config from YAML (motor IDs, transmission factors, directions)
- Subscribes to joint position commands from yanthra_move
- Publishes joint states
- Controls the actual MG6010 motors via CAN

**Terminal 2 - Start yanthra_move:**
```bash
source ~/rasfiles/pragati_ros2/install/setup.bash
ros2 launch yanthra_move yanthra_move_launch.py simulation_mode:=true
```

Wait for yanthra_move to complete initialization and show:
```
⏳ Waiting for START_SWITCH signal to begin cotton detection process...
```

**Terminal 3 - Send START_SWITCH:**
```bash
source ~/rasfiles/pragati_ros2/install/setup.bash
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
```

**Terminal 4 - Publish fake cotton detection:**
```bash
source ~/rasfiles/pragati_ros2/install/setup.bash
./test_cotton_detection_publisher.py --single --count 1
```

**Expected behavior:**
- Yanthra_move receives cotton position
- MotionController executes picking sequence:
  1. Approach trajectory to cotton position
  2. Capture sequence
  3. Retreat trajectory
  4. Move to parking position (1700, 1700, 1700)

---

### Test 2: Multiple Cotton Positions

Test picking multiple cotton pieces in sequence:

```bash
# Terminal 4
./test_cotton_detection_publisher.py --single --count 3
```

**Expected behavior:**
- Picks 3 cotton positions sequentially
- Returns to parking after all picks complete

---

### Test 3: Continuous Detection Mode

Simulates continuous operation with new detections:

**Terminal 4:**
```bash
./test_cotton_detection_publisher.py --continuous --count 2 --rate 0.5
```

This publishes 2 cotton positions every 2 seconds (0.5 Hz).

**Expected behavior:**
- Yanthra_move picks cotton, returns to parking
- Waits for START_SWITCH again (if continuous_operation=true in config)
- Receives new detection, repeats cycle

---

### Test 4: Custom Position Test

Test specific motor positions:

```bash
# Terminal 4 - Custom position (X Y Z in meters)
./test_cotton_detection_publisher.py --custom 0.4 0.0 0.6
```

---

## Monitoring and Validation

### Check Topics
```bash
# Monitor cotton detection topic
ros2 topic echo /cotton_detection/results

# Monitor joint commands FROM yanthra_move
ros2 topic echo /joint3_position_controller/command
ros2 topic echo /joint4_position_controller/command
ros2 topic echo /joint5_position_controller/command

# Monitor ACTUAL motor positions (feedback from motors)
ros2 topic echo /joint_states

# Monitor START_SWITCH
ros2 topic echo /start_switch/command
```

### Validate Motor Response

**Expected sequence when you publish cotton detection:**

1. **Joint commands published** (from yanthra_move):
```bash
# You should see position commands like:
/joint3_position_controller/command: 2.5  # radians
/joint4_position_controller/command: 1.8  # radians
/joint5_position_controller/command: 0.4  # meters
```

2. **Motor controller receives and converts:**
```
[mg6010_controller_node] Received position command for joint3: 2.500 rad
[mg6010_controller_node] Converting to motor angle with transmission_factor=...
[mg6010_controller_node] Sending CAN command to motor ID 0
```

3. **Real motors move** - You should:
   - **HEAR** motors moving
   - **SEE** physical arm movement
   - **OBSERVE** in logs: "Motor position: X.XX rad"

4. **Joint states feedback published:**
```bash
ros2 topic echo /joint_states
# Output shows actual motor encoder positions:
name: ['joint3', 'joint4', 'joint5']
position: [2.48, 1.79, 0.39]  # Close to commanded values
velocity: [0.0, 0.0, 0.0]
effort: [0.0, 0.0, 0.0]
```

5. **Return to parking:**
```
[yanthra_move] Moving arm to parking position
# Commands should go to 1700.0 for all joints
/joint3_position_controller/command: 1700.0
/joint4_position_controller/command: 1700.0  
/joint5_position_controller/command: 1700.0
```

### Check Logs
Look for these log messages in yanthra_move output:

1. **Cotton detection received:**
   ```
   🌱 Received cotton detection: 3 positions
   ```

2. **Motion controller executing:**
   ```
   🔄 Starting operational cycle #1
   Found 3 cotton positions for picking
   🎯 Starting cotton picking sequence for 3 positions
   ```

3. **Picking sequence:**
   ```
   Executing approach trajectory to [0.300, 0.100, 0.500]
   Executing cotton capture sequence
   Executing retreat trajectory
   ✅ Successfully picked cotton #1
   ```

4. **Return to parking:**
   ```
   Moving arm to parking position
   Arm moved to parking position
   ✅ Cycle #1 completed
   ```

---

## Configuration Parameters

Edit `src/yanthra_move/config/production.yaml`:

### Important parameters for testing:

```yaml
# Enable continuous operation (keep running after one cycle)
continuous_operation: true

# Infinite wait for START_SWITCH (or set timeout in seconds)
start_switch.timeout_sec: -1.0
start_switch.enable_wait: true
start_switch.prefer_topic: true  # Use topic instead of GPIO

# Static parking positions (CANNOT be changed at runtime)
joint3_init/park_position: 1700.0
joint4_init/park_position: 1700.0
joint5_init/park_position: 1700.0

# Simulation mode (skip real hardware checks)
simulation_mode: true
```

---

## Troubleshooting

### Issue: No cotton detection received
**Check:**
```bash
ros2 topic list | grep cotton
ros2 topic info /cotton_detection/results
```

**Solution:** Make sure test publisher is running and yanthra_move is subscribed.

---

### Issue: Motors not moving
**Check logs for:**
- "Motion Controller not initialized"
- "No cotton detection data available"

**Solution:** 
1. Verify yanthra_move completed initialization
2. Publish detection after START_SWITCH is triggered

---

### Issue: Stuck waiting for START_SWITCH
**Publish START signal:**
```bash
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
```

Or disable START_SWITCH wait in config:
```yaml
start_switch.enable_wait: false
```

---

## Success Criteria

✅ **Test passes if:**
1. Yanthra_move receives cotton detection messages
2. MotionController triggers picking sequence
3. Motors execute approach → capture → retreat → parking
4. System logs show complete cycle execution
5. Returns to parking position (1700, 1700, 1700) after each cycle

---

## Next Steps

After validation:
1. Test with real motor hardware (set `simulation_mode: false`)
2. Integrate with actual camera and cotton_detection_ros2
3. Validate full end-to-end system
4. Fine-tune timing parameters based on real hardware response

---

## Quick Test Commands Summary

```bash
# Terminal 1: Start motor controller (REAL MOTORS)
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on && sudo ip link set can0 up
ros2 run motor_control_ros2 mg6010_controller_node --ros-args --params-file src/motor_control_ros2/config/mg6010_three_motors.yaml

# Terminal 2: Start yanthra_move
ros2 launch yanthra_move yanthra_move_launch.py simulation_mode:=true

# Terminal 3: Trigger START_SWITCH
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"

# Terminal 4: Publish fake detection
./test_cotton_detection_publisher.py --single --count 1

# Monitor (Terminal 5)
ros2 topic echo /joint_states  # See real motor positions
ros2 topic echo /cotton_detection/results
```
