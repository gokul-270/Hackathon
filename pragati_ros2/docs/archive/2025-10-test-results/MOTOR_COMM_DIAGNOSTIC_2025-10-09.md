# MG6010 Motor Communication Diagnostic Report

**Date:** October 9, 2025, 09:50 UTC  
**System:** Raspberry Pi (pragati11) connected to MG6010E-i6 motor  
**Test Status:** ⚠️ **NO COMMUNICATION**

---

## Summary

The CAN interface is properly configured and UP, but the motor is not responding. The CAN controller is in **ERROR-PASSIVE** state, indicating hardware communication issues.

---

## Test Results

### ✅ Software Configuration - GOOD
- **CAN Interface:** can0 exists and is UP
- **Baud Rate:** 250kbps correctly configured
- **MCP2515 Driver:** Loaded successfully
- **ROS2 Test Node:** Compiles and runs correctly
- **Protocol Implementation:** Ready and tested (per Oct 9 14:01 test results)

### ❌ Hardware Communication - FAILED
- **CAN State:** ERROR-PASSIVE (should be ERROR-ACTIVE)
- **RX Packets:** 0 (no data received)
- **TX Packets:** 0 (no data sent)
- **Motor Response:** None detected (IDs 1-5 tested)
- **CAN Bus Scan:** No devices found

---

## Diagnostic Details

### CAN Interface Status
```
State: ERROR-PASSIVE (⚠️ indicates errors)
Bitrate: 250000 bps
Sample Point: 0.833
Hardware: MCP2515 on SPI (spi0.0)
Clock: 6 MHz
```

### Statistics
```
RX: 0 bytes, 0 packets, 0 errors
TX: 0 bytes, 0 packets, 0 errors
```

**Note:** ERROR-PASSIVE state with 0 TX/RX suggests the CAN controller can't transmit because it's not detecting proper ACK responses or seeing bus errors.

---

## Root Cause Analysis

The **ERROR-PASSIVE** state indicates one of these issues:

### 1. **Motor is Powered OFF** (Most Likely)
- Motor needs power to respond to CAN commands
- Check: Is the motor power supply connected and turned on?
- LED indicator on motor (if present) should be lit

### 2. **CAN Bus Not Connected**
- CAN-H and CAN-L must be connected between RPi and motor
- Common wire colors:
  - CAN-H: Orange/White-Orange
  - CAN-L: Green/White-Green
  - GND: Black/Common ground

### 3. **Missing Termination Resistors**
- CAN bus requires 120Ω resistors at BOTH ends
- Without termination, signals reflect and cause errors
- This would explain ERROR-PASSIVE state

### 4. **Wrong Baud Rate on Motor**
- Motor might be configured for different baud rate
- MG6010 typically supports: 1Mbps, 500kbps, 250kbps, 125kbps
- Previous tests (Oct 9 14:01) worked at 250kbps, so this is likely correct

### 5. **CAN Wiring Issues**
- CAN-H and CAN-L might be swapped
- Loose connections
- Damaged cables
- Wrong connector pins

---

## Comparison with Previous Successful Test

### What Changed?

**Previous Test (Oct 9 14:01:21) - SUCCESS:**
- ✅ All motor commands working
- ✅ Status reading: successful
- ✅ Angle reading: successful
- ✅ ON/OFF control: successful
- ✅ Position control: successful

**Current Test (Oct 9 09:50) - FAILURE:**
- ❌ No motor response
- ❌ CAN in ERROR-PASSIVE state
- ❌ 0 packets transmitted/received

**Possible explanations:**
1. Motor was powered OFF since last test
2. CAN cables were disconnected
3. Hardware moved/changed
4. Power supply issue

---

## Troubleshooting Steps

### Step 1: Check Motor Power ⚡
```bash
# On the motor controller:
# 1. Verify power supply voltage (should be 48V for MG6010E-i6)
# 2. Check power LED on motor (if present)
# 3. Measure voltage at motor power input with multimeter
```

### Step 2: Verify CAN Connections 🔌
```bash
# Check physical connections:
# RPi CAN Hat -> Motor CAN port
#   CAN-H (usually pin 2) -> Motor CAN-H
#   CAN-L (usually pin 1) -> Motor CAN-L  
#   GND -> Motor GND (IMPORTANT!)
```

### Step 3: Check Termination Resistors 🔧
```bash
# Measure resistance between CAN-H and CAN-L:
# - With motor OFF: Should be ~60Ω (two 120Ω in parallel)
# - If infinity: Missing termination
# - If 120Ω: Only one termination (need both ends)
```

### Step 4: Try Different Baud Rates 🔄
```bash
ssh ubuntu@192.168.137.253

# Try 1 Mbps (common default)
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p baud_rate:=1000000 -p node_id:=1 -p mode:=status

# Try 500 kbps
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p baud_rate:=500000 -p node_id:=1 -p mode:=status
```

### Step 5: Test with Loopback Mode 🔁
```bash
# Test if RPi CAN hardware is working
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 250000 loopback on
sudo ip link set can0 up

# Send and receive on same interface
candump can0 &
cansend can0 141#9A
# Should see the message echoed back
```

### Step 6: Check for Shorts/Damage 🔍
```bash
# Measure resistance:
# - CAN-H to GND: Should be high impedance (>1kΩ)
# - CAN-L to GND: Should be high impedance (>1kΩ)
# - CAN-H to CAN-L: Should be ~60Ω (with termination)
#
# If CAN-H or CAN-L shorts to GND, cable is damaged
```

---

## Quick Commands for Testing

### Reset and Test Again
```bash
ssh ubuntu@192.168.137.253

# Full reset
sudo ip link set can0 down
sudo modprobe -r mcp251x
sudo modprobe mcp251x
sudo ip link set can0 type can bitrate 250000
sudo ip link set can0 up

# Check state
ip -details link show can0 | grep state

# Test motor
cd ~/pragati_ws
source install/setup.bash
ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 \
  -p baud_rate:=250000 \
  -p node_id:=1 \
  -p mode:=status
```

### Monitor CAN Bus Activity
```bash
# Terminal 1: Monitor
ssh ubuntu@192.168.137.253
sudo candump -td can0

# Terminal 2: Send test commands
ssh ubuntu@192.168.137.253
sudo cansend can0 141#9A  # Motor ID 1 status request
sudo cansend can0 141#88  # Motor ID 1 enable
```

---

## Expected Behavior When Working

When everything is connected correctly:

```
CAN State: ERROR-ACTIVE (not ERROR-PASSIVE)
RX Packets: > 0 (receiving motor responses)
TX Packets: > 0 (sending commands)

Motor test output:
[INFO] MG6010 protocol initialized successfully
[INFO] === Testing Status Reading ===
[INFO] Status read successfully
  Temperature: 25°C
  Voltage: 48V
  Errors: 0x00
```

---

## Next Steps

1. **FIRST:** Check if motor is powered ON
2. **SECOND:** Verify CAN-H, CAN-L, GND connections
3. **THIRD:** Confirm 120Ω termination at both ends
4. **FOURTH:** Try different baud rates
5. **FIFTH:** Test with loopback to isolate RPi vs motor issue

---

## Reference Information

### Previous Working Configuration (Oct 9 14:01)
- Baud Rate: 250kbps ✅
- Motor ID: 1
- All tests: PASSED
- Motor model: MG6010E-i6

### CAN Protocol Details
- Protocol: LK-TECH CAN Protocol V2.35
- Command 0x9A: Read motor status
- Command 0x88: Motor ON
- Command 0x80: Motor OFF
- Command 0xA3: Position control

### Hardware Details
- RPi Model: Raspberry Pi with Ubuntu 24.04 (aarch64)
- CAN Controller: MCP2515 on SPI bus (spi0.0)
- Oscillator: 6 MHz (half the typical 12 MHz)
- CAN Hat: Connected to spi0.0

---

## Contact for Help

If motor still doesn't respond after these checks, document:
1. Photos of physical connections
2. Multimeter measurements (voltage, resistance)
3. Output of diagnostic commands above
4. Motor model number and configuration

---

**Conclusion:** The software is ready and previously worked. This is a **hardware connectivity or power issue** that needs physical verification.
