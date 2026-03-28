# Operator Guide & Maintenance

**Part of:** [Pragati Production System Documentation](../README.md)

---

## 📊 Performance Monitoring

### Real-Time Metrics

**Motor Performance:**
```
Position accuracy: ±0.01° (encoder resolution)
Response time: <0.25ms (CAN protocol)
Command frequency: 50-100 Hz
Motion smoothness: Jerk-limited trajectories
```

**Cotton Detection:**
```
Detection accuracy: ~90% (Phase 1, needs validation)
False positive rate: <5% (target)
Detection time: ~0.5 seconds per image
Processing rate: 10 Hz
```

**Pick-and-Place Cycle:**
```
Total cycle time: ~2.8 seconds
  - Detection: ~0.5s
  - Approach: ~0.8s
  - Grasp: ~0.5s
  - Return: ~0.8s
  - Release: ~0.2s

Success rate: 90-95% (target, needs validation)
Picks per hour: ~1,200 (theoretical max)
```

---

## 🎛️ Operator Interface

### Startup Checklist

**Pre-Operation:**
```
□ Power on main computer
□ Power on 24V motor supply (verify 22-28V)
□ Power on camera
□ Verify CAN bus (candump can0 shows traffic)
□ Check emergency stop button
□ Clear workspace area
```

**Launch System:**
```bash
# Terminal 1: Main system
cd ~/pragati_ros2
source install/setup.bash
ros2 launch pragati_complete.launch.py

# Wait for: "All systems initialized"

# Terminal 2: Monitoring (optional)
ros2 topic echo /joint_states
ros2 topic echo /cotton_detection/results
```

**Test Sequence:**
```bash
# 1. Home position
ros2 service call /yanthra_move/home_arm

# 2. Test detection
ros2 service call /cotton_detection/trigger

# 3. Manual pick test (if cotton detected)
ros2 service call /yanthra_move/pick_detected_cotton

# 4. Monitor during operation
ros2 topic hz /joint_states  # Should show ~50 Hz
```

---

## 🔧 Maintenance

### Daily Checks
```
□ Visual inspection of motors (no damage)
□ Check CAN cable connections
□ Verify camera lens is clean
□ Test emergency stop button
□ Check gripper operation
```

### Weekly Maintenance
```
□ Clean camera lens
□ Lubricate gripper mechanism
□ Check motor temperatures during operation
□ Verify all bolts tight
□ Backup logs and data
```

### Motor Status Check
```bash
# Get detailed motor status
ros2 service call /yanthra_move/get_motor_status \
  yanthra_move_interfaces/srv/GetMotorStatus \
  "{motor_ids: [1, 2, 3, 4, 5]}"

# Response includes:
# - Position
# - Velocity
# - Temperature
# - Voltage
# - Error flags
# - Operating hours
```

---
---

