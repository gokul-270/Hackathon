# ODrive CAN Test Tool

A standalone C++ utility for verifying CAN communication with ODrive Pro boards (CANSimple 0.6.x protocol).

**This tool does NOT require ROS2** and can be used for hardware bring-up, debugging, and production testing.

---

## Features

### Safe Protocol Testing (Default)
- ✅ Heartbeat monitoring (alive detection, axis_state, axis_error)
- ✅ Version information (firmware + hardware version)
- ✅ Error status (active_errors, disarm_reason)
- ✅ Encoder estimates (position, velocity)
- ✅ IQ values (setpoint, measured)
- ✅ Temperature (FET + motor)
- ✅ Bus voltage/current
- ✅ Torques (target, estimate)
- ✅ Powers (electrical, mechanical)

### Dangerous Actions (Opt-in with `--allow-dangerous`)
- ⚠️ Clear errors
- ⚠️ Reboot
- ⚠️ Emergency stop

### Intentionally Excluded (Safety)
- 🚫 DFU mode (firmware update should be done via USB)
- 🚫 SET_AXIS_NODE_ID (node ID changes should be done via USB with odrivetool)

---

## Building

The tool is built automatically with the ROS2 package:

```bash
cd /home/gokul/rasfiles/pragati_ros2
colcon build --packages-select odrive_control_ros2
```

The executable will be at:
```
install/odrive_control_ros2/lib/odrive_control_ros2/odrive_can_tool
```

---

## Usage

### Basic Syntax

```bash
odrive_can_tool --if <interface> --nodes <id1,id2,...> [OPTIONS]
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--if <interface>` | CAN interface name | `can0` |
| `--nodes <ids>` | Comma-separated ODrive node IDs (required) | - |
| `--wait-heartbeat-ms <ms>` | Timeout waiting for initial heartbeat | `2000` |
| `--timeout-ms <ms>` | Timeout for RTR replies | `500` |
| `--max-hb-age-ms <ms>` | Maximum acceptable heartbeat age | `100` |
| `--checks <list>` | Checks to run (comma-separated) | all safe checks |
| `--watch` | Continuous monitoring mode | off (test-and-exit) |
| `--allow-dangerous` | Enable dangerous actions | off |
| `--help` | Show help message | - |

### Available Checks

- `heartbeat` - Monitor heartbeat freshness and decode axis_state/axis_error
- `version` - Request and verify firmware/hardware version
- `error` - Request and verify error status
- `encoder` - Request and verify encoder position/velocity
- `iq` - Request and verify IQ setpoint/measured
- `temp` - Request and verify FET/motor temperature
- `bus` - Request and verify bus voltage/current
- `torques` - Request and verify torque target/estimate
- `powers` - Request and verify electrical/mechanical power

---

## Examples

### 1. Basic Sanity Check (All Safe Checks)

Test all ODrive nodes with default checks:

```bash
odrive_can_tool --if can0 --nodes 3,4,5
```

**What it does:**
- Waits for heartbeat from each node (max 2 seconds)
- Sends RTR requests for version, error, encoder, IQ, temp, bus, torques, powers
- Verifies each reply arrives within 500ms
- Prints PASS/FAIL for each check
- Exits with code 0 if all passed, non-zero if any failed

**Expected output:**
```
========================================
ODrive CAN Communication Test Tool
========================================
Interface: can0
Node IDs: 3, 4, 5
Checks: heartbeat,version,error,encoder,iq,temp,bus,torques,powers
...
[PASS] Node 3: Heartbeat received
[PASS] Node 4: Heartbeat received
[PASS] Node 5: Heartbeat received

[INFO] All nodes are alive!

========================================
Testing Node 3
========================================
[PASS] Node 3: Heartbeat fresh (age=12 ms)
       axis_state=1 axis_error=0x0 procedure_result=0 traj_done=1
[PASS] Node 3: Version received
       FW v0.6.10
       HW v3.6.56
[PASS] Node 3: Error status received
       active_errors=0x0 disarm_reason=0x0
[PASS] Node 3: Encoder estimates received
       pos=0.1234 turns, vel=0.0000 turns/s
...

Result: ALL CHECKS PASSED
```

---

### 2. Quick Heartbeat Check

Only verify nodes are alive and responding:

```bash
odrive_can_tool --if can0 --nodes 3 --checks heartbeat
```

---

### 3. Continuous Monitoring (Watch Mode)

Monitor live telemetry from nodes (useful for debugging):

```bash
odrive_can_tool --if can0 --nodes 3,4,5 --watch
```

**What it does:**
- Prints live status every second
- Shows heartbeat age, axis_state, axis_error
- Shows encoder position/velocity (if available)
- Shows errors, temperature, bus voltage/current (if available)
- Press Ctrl+C to exit

**Expected output:**
```
[INFO] Entering watch mode (Ctrl+C to exit)...

========================================
Status @ 1707848123456789
========================================
Node 3:
  Heartbeat: age=8ms state=8 error=0x0 traj_done=1
  Encoder: pos=10.2345 turns, vel=0.0000 turns/s
  Errors: active=0x0 disarm=0x0
  Temp: FET=32.5°C Motor=28.3°C
  Bus: 24.12V 0.45A

Node 4:
  Heartbeat: age=11ms state=1 error=0x0 traj_done=1
  ...
```

---

### 4. Test Specific Checks

Only run encoder and error checks:

```bash
odrive_can_tool --if can0 --nodes 3 --checks encoder,error
```

---

### 5. Custom Timeouts

For slower/noisy CAN buses:

```bash
odrive_can_tool --if can0 --nodes 3 --wait-heartbeat-ms 5000 --timeout-ms 1000
```

---

## Debugging CAN Issues

### No Heartbeat Received

**Symptom:**
```
[ERROR] Heartbeat timeout
  Node 3: NO HEARTBEAT
```

**Possible causes:**
1. **Wrong CAN interface** - Check `ip link show` and use correct interface name
2. **Wrong bitrate** - ODrive uses 1 Mbps by default. Set with `sudo ip link set can0 type can bitrate 1000000`
3. **CAN interface down** - Bring up with `sudo ip link set can0 up`
4. **Wrong node_id** - ODrive node ID must match what you configured via USB
5. **Wiring/termination** - Check CAN High/Low connections and 120Ω termination resistors
6. **ODrive not powered** - Check power supply

**Debug steps:**
```bash
# 1. Check CAN interface status
ip -details link show can0

# 2. Check for any CAN traffic (from any node)
candump can0

# 3. Check for error frames
candump -e can0

# 4. If you see error frames like "errorframe", check bitrate/wiring/termination
```

---

### RTR Timeout

**Symptom:**
```
[PASS] Node 3: Heartbeat received
[FAIL] Node 3: GET_VERSION timeout
```

**Possible causes:**
1. **ODrive firmware version mismatch** - Tool expects 0.6.x; older firmware may not support all RTR requests
2. **Node in error state** - Check `axis_error` in heartbeat output
3. **CAN bus errors** - Use `candump -e can0` to check for bus errors

**Debug steps:**
```bash
# Check raw CAN traffic
candump can0

# You should see:
# - Heartbeat every ~10ms: CAN ID = (node_id << 5) | 0x01
# - RTR requests: frames with RTR flag
# - RTR replies: matching CAN ID with data
```

---

### Stale Heartbeat

**Symptom:**
```
[FAIL] Node 3: Heartbeat stale (age=523 ms)
```

**Possible causes:**
1. **Node rebooted/crashed** - Check for error codes
2. **CAN bus congestion** - Too much traffic causing delays
3. **System CPU overload** - Check system load

---

## Integration with Hardware Testing

### Use in Production Test Scripts

The tool exits with code 0 on success, non-zero on failure:

```bash
#!/bin/bash
# Production test script

# Test ODrive node 3
if odrive_can_tool --if can0 --nodes 3 --checks heartbeat,version,encoder; then
    echo "✅ ODrive node 3 PASSED"
else
    echo "❌ ODrive node 3 FAILED"
    exit 1
fi
```

---

### Use with Multiple Boards

Test different boards on different CAN interfaces:

```bash
# Board 1 on can0
odrive_can_tool --if can0 --nodes 0,1

# Board 2 on can1
odrive_can_tool --if can1 --nodes 0,1
```

---

## Comparison with ROS2 Node

| Feature | `odrive_can_tool` | `odrive_service_node` |
|---------|-------------------|----------------------|
| ROS2 required | ❌ No | ✅ Yes |
| Startup time | Fast (~1s) | Slower (ROS2 init) |
| Use case | Hardware testing, debugging | Robot runtime control |
| Configuration | CLI arguments | YAML config file |
| Output | Terminal (PASS/FAIL) | ROS2 topics/services |
| Joint transforms | No | Yes (joint units ↔ motor turns) |
| Homing sequences | No | Yes |

**Recommendation:** Use `odrive_can_tool` for initial hardware bring-up and CAN debugging. Once CAN communication is confirmed, switch to `odrive_service_node` for robot integration.

---

## Troubleshooting

### Permission Denied

```bash
# Add user to dialout group for CAN access
sudo usermod -aG dialout $USER
# Log out and back in
```

### CAN Interface Not Found

```bash
# Install can-utils
sudo apt install can-utils

# Load kernel modules
sudo modprobe can
sudo modprobe can_raw

# Bring up CAN interface (example for 1 Mbps)
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

---

## Technical Details

### Message Verification Method

For each RTR check (e.g., `GET_VERSION`):

1. Read baseline timestamp from driver's cached state
2. Send RTR frame with matching CAN ID
3. Poll driver's cached state in a loop (5ms intervals)
4. Compare new timestamp with baseline
5. If timestamp updated within timeout → PASS
6. If timeout exceeded → FAIL

This approach is reliable because:
- ODrive sends replies immediately (~1-2ms typical)
- Timestamp updates prove the specific node replied
- No false positives from stale/cached data

### Heartbeat Monitoring

ODrive Pro sends heartbeat every ~10ms (100 Hz). The tool:
- Waits for initial heartbeat (proves node is alive)
- Checks heartbeat age < 100ms (proves ongoing communication)
- Decodes `axis_state`, `axis_error`, `procedure_result`, `traj_done`

---

## Safety Notes

1. **This tool does NOT move motors** in default mode
2. **`--allow-dangerous` flag** is required for any actions that could affect motor state
3. **DFU mode is excluded** to prevent accidental firmware corruption
4. **Node ID changes are excluded** to prevent accidental renumbering
5. **Always test with motors disconnected first** when using a new board

---

## Support

For issues:
1. Check this documentation's "Debugging CAN Issues" section
2. Use `candump can0` to verify CAN bus traffic
3. Check ODrive documentation for firmware-specific details
4. Verify node IDs match your USB configuration

---

## License

Copyright 2025 Pragati Robotics
