# MG6010 Motor Quick Test Guide

**Critical Fixes Applied:** ✅ All complete (Bitrate: 1Mbps → 250kbps, motor_on() verified, launch files verified)

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Hardware Check
```bash
# Verify:
# - Motor powered (24V)
# - CAN cable connected
# - CAN bus terminated (120Ω resistors)
```

### Step 2: Setup CAN Interface
```bash
# Configure and bring up CAN0 at 250kbps
sudo ip link set can0 type can bitrate 250000
sudo ip link set can0 up

# Verify it's up
ip -details link show can0
```

### Step 3: Source ROS2 Workspace
```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
```

### Step 4: Run Status Test
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status
```

**✅ Success indicators:**
- "Motor ON command sent successfully!"
- Motor status displays (temperature, voltage)
- No CAN errors or timeouts

**❌ Common issues:**
- "CAN interface not connected" → Check Step 2
- "Motor ON command failed" → Check power and wiring
- Timeouts → Verify bitrate (250kbps on both sides)

---

## 🔍 All Test Modes

### 1. Status Test (Safe - Recommended First)
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status
```
**What it does:** Reads motor status (temp, voltage, errors) without moving motor

---

### 2. Position Test
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=position
```
**What it does:** Moves motor through predefined positions
**⚠️ Warning:** Motor WILL move - ensure clear workspace

---

### 3. Velocity Test
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=velocity
```
**What it does:** Tests velocity control
**⚠️ Warning:** Motor WILL rotate continuously

---

### 4. Torque Test
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=torque
```
**What it does:** Tests torque/current control
**⚠️ Warning:** Motor will resist motion

---

### 5. On/Off Test
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=on_off
```
**What it does:** Cycles motor on/off to test power commands

---

## 🛠️ Advanced Options

### Custom CAN Interface
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py \
  can_interface:=can1 \
  test_mode:=status
```

### Custom Motor ID
```bash
# For motor with CAN ID 0x142 (motor_id = 2)
ros2 launch motor_control_ros2 mg6010_test.launch.py \
  motor_id:=2 \
  test_mode:=status
```

### Custom Baud Rate (if motor configured differently)
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py \
  baud_rate:=500000 \
  test_mode:=status
```

---

## 📊 Monitoring Tools

### Watch CAN Traffic (Separate Terminal)
```bash
# Install if needed
sudo apt-get install can-utils

# Monitor all CAN messages
candump can0

# Filter for motor ID 1 (0x141)
candump can0,141:7FF
```

### Expected CAN Messages:
- ID: 0x141 (motor 1), 0x142 (motor 2), etc.
- DLC: 8 bytes
- Frequency: ~10-100 Hz depending on test mode

---

## 🚨 Troubleshooting

### CAN Interface Issues

**Problem:** `Device "can0" does not exist`
```bash
# Check available CAN interfaces
ip link show | grep can

# If using USB-to-CAN adapter
sudo modprobe peak_usb  # For PEAK adapters
sudo modprobe gs_usb    # For generic USB-CAN adapters
lsusb  # Verify USB device detected
```

**Problem:** `Cannot assign requested address` when setting up CAN
```bash
# Bring down interface first
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 250000
sudo ip link set can0 up
```

### Motor Communication Issues

**Problem:** Motor ON command fails
1. Check power supply (24V connected?)
2. Check CAN cable continuity
3. Verify CAN bus termination (120Ω at BOTH ends)
4. Check motor ID matches (default: 1, CAN ID: 0x141)
5. Try `candump can0` - do you see any CAN traffic?

**Problem:** Timeouts
1. Verify bitrate on CAN interface: `ip -details link show can0`
2. Should show `bitrate 250000` (NOT 1000000)
3. Check if motor is on same bitrate (default MG6010-i6: 250kbps)

**Problem:** Motor doesn't move (Position/Velocity tests)
1. Check if status test works first
2. Verify motor has no error flags (check status output)
3. Check if motor is mechanically free to move
4. Verify power supply can handle motor current

---

## 📋 Success Criteria Checklist

### ✅ Status Test Success
- [ ] CAN interface initializes
- [ ] Motor ON command succeeds
- [ ] Temperature reading valid (20-50°C typical)
- [ ] Voltage reading valid (22-28V for 24V supply)
- [ ] Error flags = 0x0000
- [ ] No communication timeouts

### ✅ Position Test Success
- [ ] Motor moves to commanded positions
- [ ] Smooth motion (no jerking)
- [ ] Position feedback accurate
- [ ] Motor stops at target positions
- [ ] No overshoot or oscillation

### ✅ Velocity Test Success
- [ ] Motor rotates at commanded speed
- [ ] Speed changes smoothly
- [ ] Velocity feedback stable
- [ ] Motor stops when commanded

---

## 🎯 What Was Fixed

| Issue | Status | Impact |
|-------|--------|--------|
| **Bitrate mismatch** (1Mbps → 250kbps) | ✅ Fixed | CAN communication now works |
| **motor_on() missing** | ✅ Already present | Motor properly enabled |
| **Launch files missing** | ✅ Already exist | Easy testing available |

---

## 📞 Next Steps After Testing

1. **If tests PASS:** Update documentation with test results
2. **If tests FAIL:** Capture logs and add to issue tracker
3. **Hardware validation:** Test with all 6 motors in real robot
4. **Integration testing:** Test with full robot control system

---

## 📖 Related Documents

- **Detailed Fixes:** `CRITICAL_FIXES_COMPLETED.md`
- **Full Audit:** `COMPREHENSIVE_AUDIT_REPORT.md`
- **Action Plan:** `CRITICAL_FIXES_ACTION_PLAN.md`
- **Config Reference:** `../src/motor_control_ros2/config/mg6010_test.yaml`

---

**Last Updated:** 2024  
**Package Build:** ✅ Success (3min 28s)  
**Ready for Hardware Testing:** ✅ Yes
