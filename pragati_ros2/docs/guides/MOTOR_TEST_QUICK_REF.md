# Motor Controller Test - Quick Reference

## 🚀 Quick Start (4 Terminals)

### Terminal 1: Motor Controller (REAL HARDWARE)
```bash
cd ~/rasfiles/pragati_ros2
source install/setup.bash
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on && sudo ip link set can0 up
ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args --params-file src/motor_control_ros2/config/mg6010_three_motors.yaml
```
**What it does:** Controls real MG6010 motors via CAN bus

---

### Terminal 2: Yanthra Move (Main Software)
```bash
cd ~/rasfiles/pragati_ros2
source install/setup.bash
ros2 launch yanthra_move yanthra_move_launch.py simulation_mode:=true
```
**Wait for:** `⏳ Waiting for START_SWITCH signal...`

---

### Terminal 3: START Switch
```bash
cd ~/rasfiles/pragati_ros2
source install/setup.bash
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
```
**What it does:** Triggers the picking cycle

---

### Terminal 4: Cotton Detection (Fake Data)
```bash
cd ~/rasfiles/pragati_ros2
source install/setup.bash
./test_cotton_detection_publisher.py --single --count 1
```
**What it does:** Publishes fake cotton position to trigger motor movement

---

## 📊 What to Monitor

### Check Motor Movement
```bash
# Watch motor positions in real-time
ros2 topic echo /joint_states

# Watch commands being sent
ros2 topic echo /joint3_position_controller/command
ros2 topic echo /joint4_position_controller/command
ros2 topic echo /joint5_position_controller/command
```

### Expected Physical Behavior
1. ✅ Motors should **MOVE** when detection is published
2. ✅ Arm should execute: **approach → capture → retreat → park**
3. ✅ Final parking position: **1700, 1700, 1700**

---

## 🔍 Validation Checklist

- [ ] CAN interface is UP (`ip link show can0`)
- [ ] Motor controller node started successfully
- [ ] Yanthra_move initialized without errors
- [ ] Cotton detection message published
- [ ] Joint commands appear on topics
- [ ] **MOTORS PHYSICALLY MOVE** ← KEY!
- [ ] Joint states feedback shows encoder positions
- [ ] Motors return to parking position (1700)

---

## 🐛 Common Issues

### Motors Not Moving?
```bash
# Check CAN interface
ip link show can0

# Check for CAN errors
candump can0

# Verify motor controller is receiving commands
ros2 topic echo /joint3_position_controller/command
```

### No Cotton Detection?
```bash
# Verify topic exists
ros2 topic list | grep cotton

# Check if yanthra_move is subscribed
ros2 topic info /cotton_detection/results
```

### Forgot START_SWITCH?
```bash
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
```

---

## 📝 Test Modes

### Single Detection
```bash
./test_cotton_detection_publisher.py --single --count 1
```

### Multiple Targets
```bash
./test_cotton_detection_publisher.py --single --count 3
```

### Continuous Mode
```bash
./test_cotton_detection_publisher.py --continuous --rate 0.5
```

### Custom Position
```bash
./test_cotton_detection_publisher.py --custom 0.4 0.0 0.6
```

---

## ✅ Success Criteria

**Test PASSES if:**
1. ✅ Yanthra_move receives cotton detection
2. ✅ Joint commands published to motor topics
3. ✅ mg6010_controller_node receives commands
4. ✅ **REAL MOTORS PHYSICALLY MOVE**
5. ✅ Encoder feedback published to /joint_states
6. ✅ Motors return to parking (1700, 1700, 1700)

---

## 🎯 Data Flow Summary

```
Cotton Detection → yanthra_move → mg6010_test_node → CAN → Motors
     (fake)       (trajectory)   (conversion)      (bus)  (move!)
```

---

## 📚 Full Guide

See `MOTOR_CONTROLLER_TEST_GUIDE.md` for complete documentation.
