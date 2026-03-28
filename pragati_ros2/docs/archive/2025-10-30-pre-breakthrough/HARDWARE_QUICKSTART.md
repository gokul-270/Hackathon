# Hardware Testing Quick Start

**Status**: Hardware now connected (RPi4 + 3 motors + OAK-D Lite camera)  
**Goal**: Systematically test hardware without wasting time  
**Max Time**: 90 minutes with strict limits per section

---

## 🚀 Quick Commands

### Run All Tests (90 min max)
```bash
cd ~/Downloads/pragati_ros2
./scripts/hardware_integration_test.sh all
```

### Run Individual Sections
```bash
# Motors only (15 min max)
./scripts/hardware_integration_test.sh motors

# Camera only (20 min max)  
./scripts/hardware_integration_test.sh camera

# Integration test (30 min max)
./scripts/hardware_integration_test.sh integration
```

---

## 📋 What Gets Tested

### 1. Motor Tests (15 minutes)
- ✅ CAN bus interface check
- ✅ Motor control node launch
- ✅ Service availability (/motor_status, /enable_motors, /home_motors)
- ✅ Motor status check
- ✅ Small movement test (optional, requires confirmation)

### 2. Camera Tests (20 minutes)
- ✅ USB device detection (OAK-D Lite)
- ✅ DepthAI library verification
- ✅ C++ cotton detection node launch (PRIMARY)
- ✅ Detection service check
- ✅ Cotton detection trigger test
- ⊘ Python wrapper (skipped - DEPRECATED)

### 3. Integration Tests (30 minutes)
- ✅ Full system launch (motors + camera)
- ✅ Node health check
- ✅ Topic data flow verification
- ⊘ Workflow test (manual validation only)

---

## 🎯 Time Management

| Section | Max Time | Key Focus |
|---------|----------|-----------|
| Prerequisites | 5 min | Setup verification |
| Motor Tests | 15 min | CAN + basic movement |
| Camera Tests | 20 min | Detection service |
| Integration | 30 min | Full system |
| **TOTAL** | **~70 min** | Leaves 20 min buffer |

**The script will automatically stop sections that exceed time limits.**

---

## 📁 Test Outputs

All logs saved to:
```
test_output/hardware_tests/YYYYMMDD_HHMMSS/
├── motor_node.log
├── motor_status.txt
├── movement_test.txt
├── camera_cpp_node.log
├── depthai_check.txt
├── detection_result.txt
└── full_system.log
```

---

## 🔧 Prerequisites

Before running tests, ensure:

1. **ROS2 sourced**:
   ```bash
   source /opt/ros/jazzy/setup.bash
   ```

2. **Workspace built**:
   ```bash
   cd ~/Downloads/pragati_ros2
   colcon build
   source install/setup.bash
   ```

3. **CAN interface configured** (for motors):
   ```bash
   sudo ip link add dev can0 type can
   sudo ip link set can0 up type can bitrate 500000
   ```

4. **USB permissions** (for camera):
   ```bash
   sudo usermod -aG plugdev $USER
   # Log out and back in
   ```

5. **Hardware connected**:
   - 3x MG6010 motors on CAN bus
   - OAK-D Lite camera on USB
   - RPi powered and accessible

---

## 🐛 Troubleshooting

### Motor Tests Fail

**CAN interface not found:**
```bash
sudo ip link add dev can0 type can
sudo ip link set can0 up type can bitrate 500000
```

**Motor node crashes:**
- Check CAN cable connections
- Verify motor power supply
- Review logs in `test_output/hardware_tests/.../motor_node.log`

### Camera Tests Fail

**Camera not detected:**
```bash
# Check USB connection
lsusb | grep 03e7

# Try different USB port
# Ensure USB2 mode (more stable than USB3)
```

**DepthAI import error:**
```bash
python3 -m pip install --upgrade depthai
```

**C++ node fails:**
- Ensure workspace built with DepthAI: `colcon build --cmake-args -DHAS_DEPTHAI=ON`
- Check logs in `test_output/hardware_tests/.../camera_cpp_node.log`

### Integration Test Fails

**Full system won't launch:**
- Run motor and camera tests individually first
- Check that both subsystems work in isolation
- Review `full_system.log` for specific errors

---

## 📝 After Testing

### If Tests Pass
1. ✅ Document which cotton detection code is working (mention it's the older wrapper)
2. ✅ Note any parameter tuning needed (HSV thresholds, motor limits, etc.)
3. ✅ Save working configurations

### If Tests Fail
1. ❌ Review logs in `test_output/hardware_tests/.../`
2. ❌ Fix one issue at a time (don't try to fix everything at once)
3. ❌ Re-run specific section: `./scripts/hardware_integration_test.sh [section]`
4. ❌ Document blockers and ask for help if stuck >30 minutes

---

## 🔄 Reusing Existing Scripts

This consolidated test **reuses** your existing infrastructure:

- **Motor control**: Uses `motor_control_ros2` launch files
- **Camera detection**: Uses C++ node (primary) and Python wrapper (legacy backup)
- **Integration**: Uses `pragati_complete.launch.py`

**No new infrastructure created** - just organized testing with time limits.

---

## 💡 Tips

1. **Start with individual sections** before running full integration
2. **Monitor time** - if stuck >10 min on one test, skip and move on
3. **Log everything** - all test outputs are automatically saved
4. **Use Ctrl+C safely** - script handles cleanup properly
5. **Focus on what works** - you mentioned cotton wrapper was working, stick with it

---

## 🎯 Today's Goal

**Minimum viable outcome (70 min)**:
- ✅ Verify 3 motors respond to commands
- ✅ Verify camera detects cotton (using working wrapper)
- ✅ Document current state accurately

**Stretch goal (+20 min)**:
- ✅ Full integration test (motors + camera together)
- ✅ End-to-end workflow (detect → move)

---

**Remember: The goal is to validate hardware works, not to build new features.**

Stop wasting time debugging offline detection - stick with what works (cotton wrapper).
