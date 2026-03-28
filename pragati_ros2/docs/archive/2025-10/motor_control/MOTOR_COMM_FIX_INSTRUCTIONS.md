# MG6010 Motor Communication - Fix Instructions

## Problem Identified

The CAN interface on your Raspberry Pi exists but is **DOWN** (not configured). This is why you can't communicate with the motor.

**Current Status:**
- ✅ CAN hardware detected (MCP2515 on SPI)
- ✅ Kernel modules loaded
- ❌ **CAN interface is DOWN** - needs to be brought UP
- ❌ Bitrate not configured

## Quick Fix

### Step 1: SSH into Raspberry Pi
```bash
ssh ubuntu@192.168.137.253
```

### Step 2: Run the diagnostic script
```bash
cd ~/pragati_ws
sudo bash scripts/maintenance/can/diagnose_motor_communication.sh
```

This script will:
1. Check CAN hardware (MCP2515 controller)
2. Verify kernel modules
3. Check SPI interface
4. **Bring UP the CAN interface with correct bitrate**
5. Test communication with motor
6. Show you how to make it persistent

### Step 3: Monitor CAN traffic
```bash
# In another terminal window
ssh ubuntu@192.168.137.253
candump can0
```

### Step 4: Test motor communication

**Make sure your motor is:**
- ✅ Powered ON
- ✅ Connected to CAN bus (CAN-H, CAN-L, GND)
- ✅ Has 120Ω termination resistors at both ends of CAN bus

Then test:
```bash
# Send a status request to Motor ID 1
cansend can0 141#9A
```

If motor responds, you'll see messages in the `candump` window!

## What the Windows Software Was Doing Differently

Your Windows laptop with the custom software was:
1. ✅ Using a USB-to-CAN adapter
2. ✅ Automatically configuring the CAN interface
3. ✅ Using the correct bitrate (1 Mbps for MG6010)
4. ✅ Sending proper CAN commands

**On Linux/RPi, you need to manually:**
1. Bring UP the CAN interface
2. Set the bitrate
3. Then you can communicate

## Understanding the Issue

### CAN Interface States:
- **DOWN**: Interface exists but not configured (your current state)
- **STOPPED**: Interface configured but not transmitting
- **UP**: Interface ready for communication ✅ (what you need)

### Your Configuration:
```
Hardware: MCP2515 CAN Controller
Connection: SPI (spidev0.1)
Oscillator: 12 MHz
Bitrate: 1 Mbps (1000000 bps) - standard for MG6010
```

## Making It Persistent (Auto-start on boot)

After confirming communication works, make it auto-start:

```bash
sudo tee /etc/network/interfaces.d/can0 << 'EOF'
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 1000000
    up /sbin/ip link set can0 up
    down /sbin/ip link set can0 down
EOF
```

## Troubleshooting

### If motor still doesn't respond:

1. **Check power:**
   ```bash
   # Motor should be powered (check LED if it has one)
   ```

2. **Check wiring:**
   - CAN-H (usually yellow/white-orange)
   - CAN-L (usually green/white-green)
   - GND (common ground between RPi and motor)

3. **Check termination:**
   - Need 120Ω resistors at BOTH ends of CAN bus
   - Without termination, communication is unreliable

4. **Try different bitrates:**
   ```bash
   # Try 500 kbps
   sudo ip link set can0 down
   sudo ip link set can0 type can bitrate 500000
   sudo ip link set can0 up
   
   # Try 250 kbps
   sudo ip link set can0 down
   sudo ip link set can0 type can bitrate 250000
   sudo ip link set can0 up
   ```

5. **Check motor Node ID:**
   - Default is usually 1 (arbitration ID 0x141)
   - Try IDs 1-5: `cansend can0 141#9A` through `cansend can0 145#9A`

6. **Monitor for errors:**
   ```bash
   ip -statistics link show can0
   ```

## Testing with ROS2

Once CAN interface is UP and working, you can test with your ROS2 MG6010 test node:

```bash
cd ~/pragati_ws
source install/setup.bash

# Read motor status
ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 \
  -p baud_rate:=1000000 \
  -p node_id:=1 \
  -p mode:=status

# Read motor angle
ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 \
  -p baud_rate:=1000000 \
  -p node_id:=1 \
  -p mode:=angle
```

## Why This Wasn't Obvious

The error message "cannot communicate with motor" doesn't say "CAN interface is DOWN" - it just says communication failed. This is because:

1. The CAN hardware exists (`can0` device)
2. The kernel modules are loaded
3. But the interface wasn't brought UP with a bitrate
4. So any attempt to send/receive fails silently

It's like having a network card installed but not configured with an IP address!

## Summary

**The Fix:** Just run `sudo bash scripts/maintenance/can/diagnose_motor_communication.sh` on the RPi!

This will:
- ✅ Bring UP the CAN interface
- ✅ Configure 1 Mbps bitrate
- ✅ Test motor communication
- ✅ Show you how to make it permanent

Then you should be able to communicate with your MG6010 motor just like the Windows software does!

---

**Quick Reference:**
```bash
# On RPi - Configure CAN
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Monitor traffic
candump can0

# Test motor (ID 1)
cansend can0 141#9A
```
