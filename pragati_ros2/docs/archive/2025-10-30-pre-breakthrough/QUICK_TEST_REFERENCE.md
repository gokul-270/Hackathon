# Quick Test Reference Card
**For**: Hardware Testing Session Tomorrow  
**Keep this open in a separate terminal**

---

## 🚀 Essential Setup (Run First)

```bash
# Source environment
source /opt/ros/jazzy/setup.bash
source ~/Downloads/pragati_ros2/install/setup.bash

# Create test output directory
mkdir -p ~/test_results_$(date +%Y%m%d)
cd ~/test_results_$(date +%Y%m%d)

# Quick hardware check
lsusb | grep 03e7          # Camera (should show ID 03e7:2485)
ip link show can0           # CAN (should show UP)
```

---

## 🔍 Quick Diagnostics

```bash
# Check what's running
ros2 node list

# List all services
ros2 service list

# List all topics
ros2 topic list

# Check if system is responsive
ros2 topic hz /rosout
```

---

## 📷 Cotton Detection Quick Tests

### Start Detection Node
```bash
# C++ node (primary)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=true simulation_mode:=false

# Python wrapper (backup)
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py
```

### Trigger Detection
```bash
# Detect cotton
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Export calibration
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"
```

### Monitor Results
```bash
# Watch detection results
ros2 topic echo /cotton_detection/results

# Check detection rate
ros2 topic hz /cotton_detection/results

# View debug image (if available)
ros2 run rqt_image_view rqt_image_view
```

---

## ⚙️ Motor Control Quick Tests

### Motor Status
```bash
# Quick status check
./scripts/detailed_motor_status.sh

# Or manual
ros2 service call /motor_status motor_control_ros2/srv/MotorStatus
```

### Motor Movement
```bash
# Move one joint (SAFE: small movement)
ros2 service call /move_joint motor_control_ros2/srv/MoveJoint \
    "{joint_name: 'joint3', target_position: 0.1, velocity: 0.1}"

# Return to zero
ros2 service call /move_joint motor_control_ros2/srv/MoveJoint \
    "{joint_name: 'joint3', target_position: 0.0, velocity: 0.1}"

# Monitor positions
./scripts/utils/monitor_motor_positions.sh
```

### Emergency Stop
```bash
# EMERGENCY STOP
./emergency_motor_stop.sh

# Or manual
ros2 service call /emergency_stop std_srvs/srv/Trigger

# Re-enable motors
ros2 service call /enable_motors std_srvs/srv/Trigger
```

---

## 🏥 Health Monitoring

### CPU/Memory
```bash
htop                        # Interactive monitor (press q to quit)
free -h                     # Memory usage
df -h                       # Disk space
```

### USB Stability
```bash
dmesg -w                    # Watch kernel messages (Ctrl+C to stop)
lsusb                       # List USB devices
```

### Process Monitoring
```bash
ps aux | grep cotton        # Cotton detection processes
ps aux | grep motor         # Motor control processes
```

---

## 📊 Performance Testing

### Detection Latency
```bash
# Simple timing loop
for i in {1..10}; do
  start=$(date +%s%N)
  ros2 service call /cotton_detection/detect \
      cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" > /dev/null 2>&1
  end=$(date +%s%N)
  echo "Detection $i: $(( (end - start) / 1000000 ))ms"
done
```

### Repeated Test
```bash
# 20 detections with 2s delay
for i in {1..20}; do
  echo "Detection $i"
  ros2 service call /cotton_detection/detect \
      cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" --timeout 15
  sleep 2
done
```

---

## 🧹 Cleanup Commands

### Stop All ROS2
```bash
# Kill all ROS2 processes
killall -9 ros2

# Or use cleanup script
./scripts/essential/cleanup_ros2.sh
```

### Restart Camera
```bash
# Kill detection node
ros2 node kill /cotton_detection_node

# Check if camera still detected
lsusb | grep 03e7

# Replug USB if needed, then restart node
```

### Clear Logs
```bash
# Clean old logs
./scripts/monitoring/clean_logs.sh

# Or manual
rm -rf ~/.ros/log/*
```

---

## 📝 Data Collection

### Save Terminal Output
```bash
# Pipe command output to file
<command> | tee output.log

# Example
ros2 topic echo /cotton_detection/results | tee detections.log
```

### Save Continuous Monitoring
```bash
# Monitor and save
htop > system_metrics.txt &
HTOP_PID=$!

# ... run tests ...

# Stop monitoring
kill $HTOP_PID
```

---

## 🚨 Emergency Reference

### If Motor Won't Stop
```bash
./emergency_motor_stop.sh
# If that fails: PHYSICAL POWER OFF
```

### If Camera Freezes
```bash
ros2 node kill /cotton_detection_node
# Replug USB
# Check: lsusb | grep 03e7
```

### If System Unresponsive
```bash
killall -9 ros2
./scripts/essential/cleanup_ros2.sh
# Reboot if needed: sudo reboot
```

---

## 📋 Quick Checklist Template

Copy this for each test:

```
Test: _________________
Time: _________________
Status: [ ] PASS  [ ] FAIL  [ ] SKIP
Notes:
- 
- 
- 
Issues:
- 
- 
```

---

## 🔗 Full Documentation

See `HARDWARE_TEST_PLAN_2025-10-28.md` for:
- Detailed test procedures
- Success criteria
- Troubleshooting guides
- Time management rules

---

## ⏱️ Time Tracking

```
Session 1 (Detection):   [____________________] 60 min
Break:                   [__________] 10 min

Session 2 (Motors):      [____________________] 60 min
Break:                   [__________] 10 min

Session 3 (Integration): [____________________] 60 min
Break:                   [_______________] 15 min

Session 4 (Stress):      [____________________] 60 min

TOTAL: ~4 hours
```

---

**Pro Tips**:
- Set phone timer for each session
- If stuck >10 min, skip and move on
- Document even simple successes
- Take breaks - they're mandatory!
- Stop at time limits

**Good luck! 🚀**
