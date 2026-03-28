# CAN Bus Setup Guide

**Version**: 1.0  
**Last Updated**: September 30, 2025  
**Target**: ODrive Motor Controller Communication

---

## Overview

This guide covers CAN (Controller Area Network) bus configuration for communication between the Pragati ROS2 system and ODrive motor controllers.

### Current Status

- ⚠️ **Simulation Mode**: System runs without hardware CAN bus
- ✅ **Service Layer**: ODrive control via ROS2 services functional
- 📋 **This Guide**: For enabling hardware CAN when motors are deployed

---

## Hardware Requirements

### CAN Interface Options

| Option | Interface | Speed | Cost | Difficulty | Recommended |
|--------|-----------|-------|------|------------|-------------|
| **USB-CAN Adapter** | USB 2.0 | Up to 1 Mbps | $30-50 | ⭐ Easy | ✅ Best for development |
| **PiCAN Hat** | SPI (RPi) | Up to 1 Mbps | $40-60 | ⭐⭐ Medium | ✅ Best for deployment |
| **Jetson CAN** | Native CAN | Up to 1 Mbps | Included | ⭐⭐⭐ Advanced | For Jetson boards |

### Required Components

1. **CAN Transceiver/Adapter**
   - Recommended: PEAK PCAN-USB or CANable USB adapter
   - Alternative: Waveshare RS485 CAN Hat for Raspberry Pi
   - Must support SocketCAN interface

2. **CAN Cable**
   - Twisted pair cable (e.g., CAT5e repurposed)
   - Shielded recommended for noise immunity
   - Length: Keep under 40m for 1 Mbps operation

3. **Termination Resistors**
   - 120Ω resistors at both ends of CAN bus
   - Critical for signal integrity
   - Some ODrive boards have built-in termination

4. **ODrive Motor Controllers**
   - ODrive v3.6 or newer
   - CAN interface configured (default disabled)
   - Unique CAN IDs assigned to each axis

---

## CAN Bus Topology

### Network Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    CAN Bus Topology                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  120Ω                                                 120Ω  │
│  Term    ┌────────┐    ┌────────┐    ┌────────┐    Term   │
│   │      │ODrive  │    │ODrive  │    │ODrive  │      │    │
│   ├──────┤ Axis 0 ├────┤ Axis 1 ├────┤ Axis 2 ├──────┤    │
│   │      │ID: 0   │    │ID: 1   │    │ID: 2   │      │    │
│   │      └────────┘    └────────┘    └────────┘      │    │
│   │                                                    │    │
│   │    CAN-H (Yellow/White-Orange)                    │    │
│   ├────────────────────────────────────────────────────┤    │
│   │    CAN-L (Green/White-Green)                      │    │
│   └────────────────────────────────────────────────────┘    │
│                                                             │
│  Raspberry Pi / Jetson with CAN Interface                   │
│  (USB-CAN Adapter or Native CAN)                            │
└─────────────────────────────────────────────────────────────┘
```

### Wiring Specifications

| Signal | Wire Color (CAT5e) | Pin | Function |
|--------|-------------------|-----|----------|
| CAN-H | White-Orange (or Yellow) | CAN_H | Data High |
| CAN-L | White-Green (or Green) | CAN_L | Data Low |
| GND | Blue | GND | Common Ground |
| +12V/+24V | Brown (optional) | VBUS | Power (if needed) |

**Important**: 
- CAN-H and CAN-L must be twisted pair
- Termination resistors only at endpoints
- Keep cable runs short and direct

---

## Software Configuration

### Step 1: Install SocketCAN Utilities

```bash
# Install CAN utilities
sudo apt-get update
sudo apt-get install -y can-utils iproute2

# For Python CAN support (if needed)
pip3 install python-can

# Verify installation
candump --help
```

### Step 2: Configure CAN Interface

#### For USB-CAN Adapter

```bash
# Load SocketCAN modules
sudo modprobe can
sudo modprobe can_raw
sudo modprobe slcan

# Identify USB CAN device
lsusb | grep -i can

# Bring up CAN interface (1 Mbps bitrate)
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Verify interface is up
ip -details link show can0
```

#### For PiCAN Hat (Raspberry Pi)

```bash
# Enable SPI and CAN overlay
sudo tee -a /boot/config.txt << EOF
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
dtoverlay=spi-bcm2835-overlay
EOF

# Reboot to apply
sudo reboot

# After reboot, configure interface
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Make persistent (auto-start on boot)
sudo tee /etc/network/interfaces.d/can0 << EOF
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 1000000
    up /sbin/ip link set can0 up
    down /sbin/ip link set can0 down
EOF
```

#### For NVIDIA Jetson (Native CAN)

```bash
# Configure native CAN
sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan

# Bring up interface
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Check status
dmesg | grep can
```

### Step 3: Verify CAN Communication

```bash
# Terminal 1: Monitor all CAN messages
candump can0

# Terminal 2: Send test message
cansend can0 123#DEADBEEF

# Expected: Terminal 1 shows received message
# can0  123   [4]  DE AD BE EF

# Check for errors
ip -details -statistics link show can0
```

---

## ODrive Configuration

### Step 1: Configure ODrive CAN Interface

Connect to ODrive via USB and configure:

```python
# Connect via odrivetool
odrivetool

# In odrivetool shell:

# Enable CAN on axis0 (adjust for your setup)
odrv0.axis0.config.can.node_id = 0
odrv0.can.config.baud_rate = 1000000  # 1 Mbps

# Set CAN protocol
odrv0.axis0.config.enable_step_dir = False
odrv0.axis0.config.enable_watchdog = True
odrv0.axis0.config.watchdog_timeout = 1.0  # seconds

# Save configuration
odrv0.save_configuration()
odrv0.reboot()

# Repeat for other axes with unique node IDs
# odrv0.axis1.config.can.node_id = 1
# etc.
```

### Step 2: Test ODrive CAN Messages

```bash
# Monitor ODrive heartbeat messages
candump can0 | grep "arbitration_id"

# Expected: Regular heartbeat messages from each ODrive
# can0  700   [8]  ...  (node_id 0)
# can0  701   [8]  ...  (node_id 1)

# Send position command to axis 0 (example)
# Command format: 0x00C + node_id for set input position
cansend can0 00C#00000000  # Position 0

# Monitor feedback
candump can0 -L
```

---

## ROS2 Integration

### CAN Driver Package

**File**: `src/odrive_control_ros2/config/can_config.yaml`

```yaml
can_interface:
  interface_name: "can0"
  bitrate: 1000000
  timeout_ms: 100
  
odrive_nodes:
  - node_id: 0
    axis_name: "joint_1"
    feedback_rate_hz: 50
  - node_id: 1
    axis_name: "joint_2"
    feedback_rate_hz: 50
  - node_id: 2
    axis_name: "joint_3"
    feedback_rate_hz: 50
```

### CAN Manager Implementation

**File**: `src/odrive_control_ros2/include/odrive_control_ros2/can_manager.hpp`

```cpp
#pragma once

#include <rclcpp/rclcpp.hpp>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <memory>
#include <thread>

namespace odrive_control_ros2 {

class CANManager {
public:
    explicit CANManager(rclcpp::Node* node);
    ~CANManager();
    
    bool initialize(const std::string& interface = "can0");
    void shutdown();
    
    // Send/receive CAN frames
    bool sendFrame(uint32_t arbitration_id, const uint8_t* data, uint8_t length);
    bool receiveFrame(struct can_frame& frame, int timeout_ms = 100);
    
    // ODrive-specific commands
    bool setAxisState(uint8_t node_id, uint8_t state);
    bool setInputPosition(uint8_t node_id, float position, int16_t velocity_ff = 0, int16_t torque_ff = 0);
    bool requestFeedback(uint8_t node_id);
    
private:
    rclcpp::Node* node_;
    int can_socket_;
    bool is_initialized_;
    
    std::thread receive_thread_;
    std::atomic<bool> running_;
    
    void receiveLoop();
    uint32_t getCommandId(uint8_t node_id, uint8_t cmd);
};

} // namespace odrive_control_ros2
```

### Usage Example

```cpp
// In ODrive control node
auto can_manager = std::make_shared<CANManager>(node);

if (!can_manager->initialize("can0")) {
    RCLCPP_ERROR(node->get_logger(), "Failed to initialize CAN");
    return;
}

// Set axis to closed loop control
can_manager->setAxisState(0, 8);  // AXIS_STATE_CLOSED_LOOP_CONTROL

// Command position
float target_position = 10.0;  // revolutions
can_manager->setInputPosition(0, target_position);

// Request feedback
can_manager->requestFeedback(0);
```

---

## Testing and Validation

### Pre-Test Checklist

- [ ] CAN interface installed and recognized
- [ ] SocketCAN utilities installed
- [ ] CAN bus wired correctly (CAN-H, CAN-L, GND)
- [ ] 120Ω termination resistors at both ends
- [ ] ODrive CAN configured with unique node IDs
- [ ] Bitrate matches (1 Mbps recommended)

### Test 1: CAN Interface

```bash
# Check interface exists
ip link show can0

# Bring up interface
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Verify no errors
ip -s -d link show can0
# Should show: state UP, no TX/RX errors
```

### Test 2: ODrive Detection

```bash
# Monitor CAN bus for ODrive heartbeats
timeout 5 candump can0

# Expected output (every ~10ms per axis):
# can0  700   [8]  01 00 08 00 00 00 00 00
# can0  701   [8]  01 00 08 00 00 00 00 00

# If no messages, check:
# - ODrive powered on
# - CAN enabled in ODrive config
# - Correct wiring
```

### Test 3: Command and Feedback

```bash
# Terminal 1: Monitor feedback
candump can0 -L

# Terminal 2: Send axis state command (closed loop control)
# Format: (0x007 + node_id) [4] state_id 00 00 00
cansend can0 007#08000000  # Node 0, state 8 (closed loop)

# Terminal 2: Send position command
# Format: (0x00C + node_id) [8] position_float velocity_int16 torque_int16
# Position 10.0 revolutions = 0x41200000 in float32
cansend can0 00C#0000204100000000
```

### Test 4: ROS2 Integration

```bash
# Launch ODrive control with CAN
ros2 launch odrive_control_ros2 odrive_can.launch.py

# Monitor joint states
ros2 topic echo /joint_states

# Send position command via service
ros2 service call /odrive/set_position odrive_control_ros2/srv/SetPosition "{axis_id: 0, position: 10.0}"
```

---

## Troubleshooting

### CAN Interface Not Found

**Symptom**: `ip link show can0` returns error

**Solutions**:
```bash
# Check if modules loaded
lsmod | grep can

# Load modules manually
sudo modprobe can
sudo modprobe can_raw
sudo modprobe slcan  # For USB adapters
sudo modprobe mcp2515  # For SPI adapters

# Check USB device (for USB-CAN adapters)
lsusb
dmesg | tail -50

# For PiCAN, verify SPI enabled
ls /dev/spi*
```

### No Messages on CAN Bus

**Checks**:
1. **ODrive powered?** Check LEDs
2. **CAN enabled on ODrive?** Verify via odrivetool
3. **Correct wiring?** CAN-H to CAN-H, CAN-L to CAN-L
4. **Termination resistors?** 120Ω at both ends
5. **Bitrate matches?** Both sides must use same rate

**Debug**:
```bash
# Check for bus errors
ip -s -d link show can0
# Look for error counters

# Try lower bitrate
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Monitor with verbose output
candump can0 -t a -c -e
```

### Bus-Off State

**Symptom**: CAN interface shows "state BUS-OFF"

**Cause**: Too many errors, usually wiring issue

**Solution**:
```bash
# Restart interface
sudo ip link set can0 down
sudo ip link set can0 up

# Check for hardware problems:
# - Short circuit on bus
# - Missing/wrong termination
# - Incorrect bitrate
# - Faulty transceiver

# Measure resistance between CAN-H and CAN-L
# Should be ~60Ω (two 120Ω in parallel)
```

### Intermittent Communication

**Causes**:
- Poor cable quality or too long
- EMI/noise interference
- Loose connections
- Insufficient power to ODrive

**Solutions**:
- Use shielded twisted pair cable
- Keep cable under 10m for 1 Mbps
- Add ferrite beads
- Check all connections
- Ensure stable power supply

---

## Safety Considerations

### CAN Bus Safety

1. **Watchdog Timeout**: Always enable ODrive watchdog
2. **Emergency Stop**: CAN failure should trigger safe shutdown
3. **Heartbeat Monitoring**: Detect communication loss
4. **Error Handling**: Handle bus-off and error states gracefully

### Configuration

```yaml
# In odrive_control_ros2 config
safety:
  can_timeout_ms: 500  # Trigger e-stop if no CAN for 500ms
  watchdog_enabled: true
  watchdog_timeout_sec: 1.0
  max_consecutive_errors: 10
```

---

## Performance Optimization

### Latency Reduction

```bash
# Set CAN interface to real-time priority
sudo ip link set can0 txqueuelen 1000

# Disable auto-restart on bus-off (faster recovery)
sudo ip link set can0 type can restart-ms 100
```

### Bandwidth Management

- **Typical CAN bandwidth**: 1 Mbps = ~125 KB/s
- **ODrive feedback**: ~50 Hz per axis = ~400 bytes/s per axis
- **Commands**: As needed, typically < 100 Hz
- **Total for 6 axes**: ~3-5% bus utilization (plenty of headroom)

---

## Quick Reference

### Bring Up CAN Interface
```bash
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

### Monitor CAN Bus
```bash
candump can0
```

### Send Command
```bash
cansend can0 007#08000000  # Axis 0 to closed loop
```

### Check Interface Status
```bash
ip -s -d link show can0
```

### Restart Interface
```bash
sudo ip link set can0 down && sudo ip link set can0 up
```

---

## Related Documentation

- **ODrive Documentation**: https://docs.odriverobotics.com/v/latest/can-protocol.html
- **SocketCAN**: https://www.kernel.org/doc/html/latest/networking/can.html
- **Safety Monitor Guide**: `docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md`
- **GPIO Setup**: `docs/guides/GPIO_SETUP_GUIDE.md`

---

## Revision History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-09-30 | 1.0 | Initial CAN bus setup guide | AI Assistant |