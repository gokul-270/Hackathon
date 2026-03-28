# Hardware Test Checklist - 2025-11-07
**Phase 1 Unit Conversion Fix Validation**

---

## ⚡ Quick Start

### 1. Pre-Flight Checks (2 min)
```bash
# CAN bus up?
ip link show can0 | grep "state UP"

# Pull latest code
cd /home/uday/Downloads/pragati_ros2
git pull

# Source workspace
source install/setup.bash
```

### 2. Critical Test - Joint3 Units (1 min)
```bash
# Launch system first
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true \
  enable_arm_client:=false \
  enable_cotton_detection:=false &

# Wait for launch, then test joint3
ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "{data: -0.4}"
```

**Expected**: Visible rotation ~23° (about 1/4 turn)  
**If barely moves**: Radians fix didn't work → STOP, debug  
**If rotates correctly**: ✅ Proceed to full test

### 3. Full Pick Cycle Test (5 min)
Press START_SWITCH and observe logs in real-time.

---

## 🎯 What to Watch For

### ✅ GOOD Signs (Success):
```
🚀 Motor commands (Phase 1 fix applied):
   joint3: -0.900 rad → est. -0.86 motor rotations
   joint4: 0.062 m → est. 0.79 motor rotations  
   joint5: 0.000 m → est. 0.00 motor rotations
✅ Safety check passed: all motor rotations <5
```

### ❌ BAD Signs (Rollback):
```
🛑 SAFETY ABORT: joint* calculation exceeds safe limits!
⚠️ WARNING: Motor rotation estimates >5!
```

---

## 📊 Success Criteria

- [ ] joint3 actually rotates (not stuck at 0)
- [ ] Motor estimates in logs ALL <5 rotations
- [ ] No "SAFETY ABORT" messages
- [ ] At least 3/4 picks succeed
- [ ] No mechanical grinding/limit hitting
- [ ] No CAN bus errors

---

## 🚨 If Something Goes Wrong

### Immediate Rollback:
```bash
# Stop launch (Ctrl+C)

# Restore backup
cd /home/uday/Downloads/pragati_ros2/src/yanthra_move/src/core
cp motion_controller.cpp.before_phase1_fix motion_controller.cpp

# Rebuild
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select yanthra_move

# Source and retry
source install/setup.bash
```

### CAN Bus Recovery:
```bash
sudo ip link set can0 down
sleep 0.5
sudo ip link set can0 up
```

---

## 📝 Data to Collect

### Save Full Log:
```bash
# Before test
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true \
  enable_arm_client:=false \
  enable_cotton_detection:=false 2>&1 | tee test_2025-11-07.log
```

### Key Metrics to Extract:
```bash
# Motor rotation estimates
grep "Motor commands" test_2025-11-07.log

# Safety checks
grep "Safety check" test_2025-11-07.log

# Timing
grep "Sequential motion timing" test_2025-11-07.log

# Any errors
grep -i "error\|abort\|fail" test_2025-11-07.log
```

---

## ✅ If Test Succeeds

Deploy optimizations in this order:

### 1. ArUco Optimization (Biggest Win)
See: `ARUCO_OPTIMIZATION.md`  
Impact: 8s → 3-4s detection time

### 2. QoS Tuning (Reliability Fix)
See: `QOS_OPTIMIZATION.md`  
Impact: Faster, more reliable commands

### 3. Position Feedback (Foundation)
See: `POSITION_FEEDBACK_DESIGN.md`  
Impact: Real validation, no more fake success

---

## 📞 Help

If issues arise, share:
1. Full log: `test_2025-11-07.log`
2. CAN bus state: `ip link show can0`
3. Error messages from grep commands above

**All documentation in**:
- `ANSWERS_AND_IMPROVEMENTS_2025-11-06.md` - Full Q&A
- `PHASE1_DEPLOYED_2025-11-06.md` - Technical details
- `TESTING_CHECKLIST.md` - Detailed test procedures

---

**Good luck with the test!** 🚀
