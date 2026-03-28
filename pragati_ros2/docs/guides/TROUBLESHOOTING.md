# Troubleshooting Guide - Pragati ROS2

**Last Updated:** 2025-10-15  
**Status:** Active  
**Scope:** All packages (motor_control, cotton_detection, yanthra_move, vehicle_control)

---

## Quick Diagnosis

| Symptom | Likely Cause | Section |
|---------|--------------|---------|
| Node won't start | Missing dependencies, config errors | [Build & Launch](#build--launch-issues) |
| CAN communication timeout | Hardware, bitrate mismatch | [Motor Control](#motor-control-issues) |
| Camera not detected | USB connection, permissions | [Cotton Detection](#cotton-detection-issues) |
| Motors not responding | Power, CAN, safety limits | [Motor Control](#motor-control-issues) |
| Poor detection accuracy | Lighting, thresholds, model | [Cotton Detection](#cotton-detection-issues) |
| Arm won't move | Joint limits, motor state | [Yanthra Move](#yanthra-move-issues) |

---

## Build & Launch Issues

### Error: "Package not found" during build

**Symptom:**
```
CMake Error: Could not find a package configuration file provided by "..."
```

**Cause:** Missing ROS2 dependencies

**Solution:**
```bash
# Update rosdep database
rosdep update

# Install missing dependencies
cd /home/uday/Downloads/pragati_ros2
rosdep install --from-paths src --ignore-src -r -y

# Rebuild
colcon build --symlink-install
```

---

### Error: "Node not found" after build

**Symptom:**
```
Package 'motor_control_ros2' not found
```

**Cause:** Environment not sourced

**Solution:**
```bash
# Source the workspace
source /home/uday/Downloads/pragati_ros2/install/setup.bash

# Add to ~/.bashrc to make permanent
echo "source /home/uday/Downloads/pragati_ros2/install/setup.bash" >> ~/.bashrc
```

---

### Error: Launch file fails immediately

**Symptom:**
```
[ERROR] [launch]: Caught exception in launch (see debug for traceback): ...
```

**Cause:** Missing or incorrect config files

**Solution:**
```bash
# Check config file exists
ls src/motor_control_ros2/config/motors_production.yaml

# Verify YAML syntax
python3 -c "import yaml; yaml.safe_load(open('src/motor_control_ros2/config/motors_production.yaml'))"

# Check launch file syntax
ros2 launch --show-args motor_control_ros2 mg6010_test_node.launch.py
```

---

## Motor Control Issues

### Error: CAN communication timeout

**Symptom:**
```
[ERROR] [motor_controller]: CAN communication timeout for motor ID 1
```

**Possible Causes:**
1. CAN hardware not connected
2. Wrong bitrate (must be 500 kbps)
3. Motor powered off
4. CAN bus termination missing

**Diagnostic Steps:**
```bash
# Check CAN interface exists
ip link show can0

# Verify CAN bitrate
ip -details link show can0 | grep bitrate
# Should show: bitrate 500000

# Check for CAN traffic
candump can0
# Should see frames if motors are active

# Test loopback mode
sudo ip link set can0 type can bitrate 500000 loopback on
cansend can0 123#DEADBEEF
candump can0
```

**Solutions:**
```bash
# Set up CAN interface correctly
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link add can0 up

# Add termination resistor (120 Ohm) at both ends of CAN bus
# Check motor power supply (48V)
```

---

### Error: Motor oscillating or unstable

**Symptom:**
- Motor shaking or vibrating
- Position oscillating around setpoint
- Squealing noise

**Cause:** PID gains too aggressive

**Solution:**
1. Stop motor immediately (emergency stop)
2. Reduce gains in `config/motors_production.yaml`:
   ```yaml
   p_gain: 1.0  # Reduce by 50%
   i_gain: 0.0  # Set to zero
   d_gain: 0.1  # Minimal damping
   ```
3. Restart with conservative gains
4. Follow tuning procedure in [MOTOR_TUNING_GUIDE.md](MOTOR_TUNING_GUIDE.md)

---

### Error: Safety monitor triggered

**Symptom:**
```
[ERROR] [safety_monitor]: Emergency stop triggered: [reason]
```

**Reasons and Solutions:**

| Reason | Cause | Solution |
|--------|-------|----------|
| Position limit exceeded | Joint outside allowed range | Check position limits in config; verify calibration |
| Velocity limit exceeded | Motor moving too fast | Reduce velocity limits; check trajectory generation |
| Temperature too high | Motor overheating | Let cool down; check ventilation; reduce duty cycle |
| Communication timeout | CAN failure | Check CAN bus; verify connections |
| Manual ESTOP | Emergency button pressed | Release button; investigate cause |

**Reset Safety Monitor:**
```bash
# Call reset service (after addressing cause)
ros2 service call /safety_monitor/reset std_srvs/srv/Trigger
```

---

### Error: Motor not responding to commands

**Symptom:**
- Commands sent but no movement
- Position feedback unchanged

**Diagnostic Checklist:**
1. **Check motor state:**
   ```bash
   ros2 topic echo /joint_states
   # Verify position feedback is updating
   ```

2. **Check safety limits:**
   ```bash
   ros2 topic echo /diagnostics
   # Look for safety violations
   ```

3. **Check control mode:**
   - Verify motor is in correct control mode (position/velocity/torque)
   - Check `config/motors_production.yaml`

4. **Check power:**
   - Verify 48V supply connected and stable
   - Check for voltage drops under load

**Solution:**
- If position feedback frozen: Check CAN communication
- If safety triggered: Reset safety monitor after addressing issue
- If power issue: Check supply and wiring

---

## Cotton Detection Issues

### Error: Camera not detected

**Symptom:**
```
[ERROR] [cotton_detection]: Failed to initialize DepthAI device
```

**Possible Causes:**
1. USB not connected
2. USB permissions
3. Multiple cameras conflict
4. USB hub power insufficient

**Diagnostic Steps:**
```bash
# Check USB device detected
lsusb | grep -i luxonis
# Should show: "ID 03e7:.... Luxonis"

# Check dmesg for USB errors
dmesg | tail -20

# Check permissions
groups $USER
# Should include "plugdev" or similar
```

**Solutions:**
```bash
# Add USB permissions
sudo usermod -a -G plugdev $USER
# Log out and back in

# Add udev rule for DepthAI
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Use powered USB hub if needed
# Connect camera directly to USB 3.0 port
```

---

### Error: Poor detection accuracy

**Symptom:**
- Many false positives (detecting non-cotton)
- Missing actual cotton bolls
- Inconsistent detection

**Diagnostic Steps:**
```bash
# Enable debug visualization (if available)
ros2 param set /cotton_detection debug_mode true

# Check detection statistics
ros2 topic echo /cotton_detections
# Note confidence scores
```

**Solutions:**

1. **Lighting Issues:**
   - Test in different lighting conditions
   - Add consistent artificial lighting
   - Avoid direct sunlight glare

2. **Tune HSV Thresholds:**
   Edit `config/cotton_detection.yaml`:
   ```yaml
   hsv_lower: [0, 30, 100]    # Adjust based on field conditions
   hsv_upper: [20, 255, 255]
   ```

3. **YOLO Model Issues:**
   - Verify model file exists and is correct version
   - Consider retraining with local cotton images
   - Check confidence threshold (default 0.5)

4. **Camera Calibration:**
   - Verify calibration loaded correctly
   - Re-calibrate if camera moved or changed

---

### Error: Low frame rate / high latency

**Symptom:**
- Detection frequency < 10 Hz
- Significant lag between motion and detection

**Diagnostic Steps:**
```bash
# Check CPU usage
top -p $(pgrep cotton_detection)

# Check topic frequency
ros2 topic hz /cotton_detections

# Profile detection pipeline (if instrumentation added)
ros2 param get /cotton_detection profiling_enabled
```

**Solutions:**

1. **CPU Optimization:**
   - Close unnecessary processes
   - Reduce YOLO image resolution
   - Use GPU acceleration if available

2. **Pipeline Optimization:**
   - Enable camera hardware encoding
   - Reduce detection frequency if not needed at full rate
   - Consider C++ optimizations (already done)

3. **Network Issues:**
   - If using ROS2 over network, check bandwidth
   - Use efficient transport (e.g., compressed images)

---

## Yanthra Move Issues

### Error: Arm won't move / trajectory rejected

**Symptom:**
```
[ERROR] [yanthra_move]: Trajectory execution failed: [reason]
```

**Possible Reasons:**

1. **Joint Limits Exceeded:**
   - Check if target position within joint limits
   - Verify limits in `config/yanthra.yaml`
   - Solution: Adjust target position or expand limits (carefully)

2. **Motor Not Ready:**
   - Check motor controller states
   - Verify all motors initialized
   - Solution: Wait for initialization; check motor diagnostics

3. **IK Solution Failed:**
   - Target position unreachable
   - Singularity encountered
   - Solution: Choose reachable targets; avoid singularities

---

### Error: Jerky or discontinuous motion

**Symptom:**
- Arm moves in steps rather than smoothly
- Sudden accelerations or stops

**Possible Causes:**
1. Trajectory interpolation issues
2. Control frequency too low
3. Motor tuning (PID gains)

**Solutions:**
```yaml
# Increase trajectory points
trajectory_resolution: 0.01  # seconds per point

# Increase control frequency
control_frequency: 200  # Hz

# Tune motor PIDs (see MOTOR_TUNING_GUIDE.md)
```

---

### Error: End effector not actuating

**Symptom:**
- Vacuum pump not turning on
- LEDs not responding

**Cause:** GPIO not implemented (hardware TODO)

**Status:** Awaiting hardware integration

**Workaround (simulation):**
- Commands accepted but no physical action
- Monitor service responses for confirmation

---

## General ROS2 Issues

### Error: "DDS communication failure"

**Symptom:**
```
[WARN] [rcl]: Failed to publish message: DDS error
```

**Solutions:**
```bash
# Check ROS_DOMAIN_ID (avoid conflicts)
export ROS_DOMAIN_ID=42

# Use Cyclone DDS (more reliable than default)
sudo apt install ros-jazzy-rmw-cyclonedds-cpp
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Add to ~/.bashrc
```

---

### Error: "Parameter file not found"

**Symptom:**
```
[ERROR]: Failed to load parameters from file: [path]
```

**Solutions:**
```bash
# Verify file exists and path is correct
ls -l [path]

# Check YAML syntax
yamllint [path]

# Use absolute paths in launch files
config_path = os.path.join(
    get_package_share_directory('motor_control_ros2'),
    'config', 'motors_production.yaml'
)
```

---

## Error Recovery Procedures

### Soft Reset (Node Level)

```bash
# Restart specific node
ros2 lifecycle set /motor_controller shutdown
ros2 run motor_control_ros2 motor_controller

# Or use launch file
ros2 launch motor_control_ros2 [launch_file].launch.py
```

---

### Hard Reset (System Level)

```bash
# Stop all ROS2 nodes
pkill -9 -f ros2

# Reset CAN interface
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on

# Restart system
ros2 launch [your_main_launch_file].launch.py
```

---

### Emergency Stop Procedure

**Immediate Actions:**
1. Press physical emergency stop button (if available)
2. Or kill motor control node: `pkill -9 motor_controller`
3. Power off motors at supply

**After Emergency:**
1. Identify root cause
2. Address issue (mechanical, electrical, software)
3. Test in safe mode (reduced speeds/gains)
4. Reset safety monitor
5. Resume operation cautiously

---

## Diagnostic Commands Reference

```bash
# Check all nodes running
ros2 node list

# Check topics and their rates
ros2 topic list
ros2 topic hz /joint_states

# Check services available
ros2 service list

# Check parameters for a node
ros2 param list /motor_controller

# Monitor diagnostics
ros2 topic echo /diagnostics

# Check system resources
htop
iostat -x 1

# Check CAN bus
candump can0
cansend can0 [ID]#[DATA]
```

---

## Network & Connectivity Issues

### MQTT Reconnection Issues

**Symptoms:**
- Arm commands not reaching arm nodes
- Vehicle status not updating
- "Connection lost" messages in logs
- Commands work after manual restart

**Debugging Steps:**

```bash
# 1. Check MQTT connection logs (ARM_client)
tail -f /var/log/pragati_ros2/arm_client_*.log | grep -i "mqtt\|connect"

# 2. Check vehicle bridge logs
tail -f /var/log/pragati_ros2/vehicle_mqtt_bridge_*.log | grep -i "mqtt\|connect"

# 3. Look for reconnection events
grep "Reconnected" /var/log/pragati_ros2/arm_client_*.log
grep "Connection established" /var/log/pragati_ros2/vehicle_mqtt_bridge_*.log

# 4. Check MQTT broker connectivity
mosquitto_sub -h <broker_ip> -t "pragati/#" -v

# 5. Test network latency to broker
ping -c 100 <broker_ip>
```

**Solution:**
- Auto-reconnect is already implemented in ARM_client.py and vehicle_mqtt_bridge.py
- Check log files for reconnection patterns
- If no reconnections logged but commands fail, check network stability (see below)
- Verify MQTT broker is running: `systemctl status mosquitto`

**Related Documentation:**
- See `docs/MQTT_VEHICLE_ARM_INTEGRATION.md` section "Log Files & Debugging"

---

### RPi WiFi/Network Connectivity Issues

**Symptoms:**
- RPi doesn't connect to router on boot
- Intermittent SSH disconnections
- One specific RPi consistently fails to connect
- Other RPis on same router work fine

**Identifying the Problem RPi:**

```bash
# Run this test script on each RPi to identify faulty unit
# Save as: /tmp/test_network.sh

#!/bin/bash
ROUTER_IP="192.168.1.1"  # Change to your router IP
DURATION=300  # 5 minutes

echo "Testing network stability to $ROUTER_IP for $DURATION seconds..."
echo "Start time: $(date)"

ping -c 300 -i 1 $ROUTER_IP > /tmp/ping_results.txt 2>&1

PACKET_LOSS=$(grep "packet loss" /tmp/ping_results.txt | awk '{print $6}' | tr -d '%')

echo "End time: $(date)"
echo "Packet loss: ${PACKET_LOSS}%"

if (( $(echo "$PACKET_LOSS > 5" | bc -l) )); then
    echo "RESULT: HIGH PACKET LOSS - This RPi may have network issues"
else
    echo "RESULT: Network stability OK"
fi

cat /tmp/ping_results.txt
```

**Run on each RPi:**
```bash
chmod +x /tmp/test_network.sh
/tmp/test_network.sh
```

**Interpretation:**
- **< 1% loss**: Normal, RPi is fine
- **1-5% loss**: Monitor, may have minor issues
- **> 5% loss**: Problem RPi, investigate hardware/driver
- **> 20% loss**: Critical issue, likely hardware fault

**Router Configuration Checklist:**

```bash
# 1. Check WiFi power management (should be OFF)
iwconfig wlan0 | grep "Power Management"
# Should show: Power Management:off

# 2. Verify WiFi settings
iwconfig wlan0

# 3. Check network interface status
ip addr show wlan0

# 4. Review connection history
journalctl -u wpa_supplicant -b | grep wlan0

# 5. Check for errors in dmesg
dmesg | grep -i "wlan\|wifi\|firmware"
```

**Common Fixes:**

**1. Power Management (Most Common)**
```bash
# Already applied per RPi_POWER_MGMT_FIX_SUMMARY.md
# Verify it's still disabled:
cat /etc/network/interfaces.d/wlan0
# Should contain: wireless-power off

# If missing, re-apply fix:
sudo nano /etc/network/interfaces.d/wlan0
# Add line: wireless-power off
sudo systemctl restart networking
```

**2. Router-Specific Issues**
- **Frequency**: Use 2.4GHz (better range) instead of 5GHz for industrial environments
- **Channel**: Avoid crowded channels (1, 6, 11 recommended)
- **DHCP**: Reserve IP addresses for each RPi (prevents IP conflicts)
- **Signal Strength**: Check with `iwconfig wlan0 | grep Signal`

**3. Hardware Issues**
If one specific RPi consistently fails after all fixes:
```bash
# Check WiFi adapter health
lsusb  # If using USB WiFi
dmesg | grep brcmfmac  # For built-in RPi WiFi

# Test with Ethernet cable
# If Ethernet works but WiFi doesn't → WiFi hardware fault
```

**Decision Tree:**
1. Run network stability test on all RPis
2. If one RPi has >5% loss → Check power management settings
3. If power mgmt OK → Check router signal strength
4. If signal OK → Check for hardware errors in dmesg
5. If hardware errors present → Replace RPi or WiFi adapter
6. If all RPis have issues → Check router configuration

**Field Trial Context:**
- Power management fixes were applied October 2025 (`docs/guides/hardware/RPi_POWER_MGMT_FIX_SUMMARY.md`)
- Issues persisted in January 2026 field trial
- User reported: "one of the rpi was not connecting to this router also, i think this rpi has some issue particularly"
- This suggests hardware-specific fault rather than configuration issue

---

### SSH Connection Drops

**Symptoms:**
- SSH session disconnects during operation
- "Connection reset by peer" errors
- Need to reconnect frequently

**Fixes:**

```bash
# 1. Enable SSH keepalive (client side)
# Add to ~/.ssh/config on your laptop/desktop:
Host 192.168.1.*
    ServerAliveInterval 30
    ServerAliveCountMax 3
    TCPKeepAlive yes

# 2. Enable SSH keepalive (server side - on RPi)
sudo nano /etc/ssh/sshd_config
# Add/modify:
ClientAliveInterval 30
ClientAliveCountMax 3
TCPKeepAlive yes

sudo systemctl restart ssh
```

**Related to WiFi issues:** If SSH drops correlate with network packet loss, see "RPi WiFi/Network Connectivity Issues" above.

---

## Logging and Debug

### Enable Debug Logging

```bash
# Set log level for specific node
ros2 run motor_control_ros2 motor_controller --ros-args --log-level DEBUG

# Or in launch file:
Node(
    package='motor_control_ros2',
    executable='motor_controller',
    arguments=['--ros-args', '--log-level', 'DEBUG']
)
```

---

### Check Log Files

```bash
# ROS2 logs location
cd ~/.ros/log/

# View latest log
tail -f ~/.ros/log/latest/[node_name]-*.log

# Search for errors
grep ERROR ~/.ros/log/latest/*.log
```

---

## Getting Help

### Before Reporting Issues

Collect the following information:

1. **System Info:**
   ```bash
   uname -a
   ros2 --version
   lsb_release -a
   ```

2. **Error Messages:**
   - Full error output
   - Log files
   - Screenshot if relevant

3. **Configuration:**
   - Config files used
   - Launch file
   - Parameter values

4. **Reproducibility:**
   - Steps to reproduce
   - Consistent or intermittent?
   - Started when?

---

### Documentation References

- **Motor Control:** [src/motor_control_ros2/README.md](../../src/motor_control_ros2/README.md)
- **Cotton Detection:** [src/cotton_detection_ros2/README.md](../../src/cotton_detection_ros2/README.md)
- **Yanthra Move:** [src/yanthra_move/README.md](../../src/yanthra_move/README.md)
- **Tuning Guide:** [docs/guides/MOTOR_TUNING_GUIDE.md](MOTOR_TUNING_GUIDE.md)
- **TODO Master:** [docs/TODO_MASTER.md](../TODO_MASTER.md)
- **Status Tracker:** [docs/status/STATUS_TRACKER.md](../status/STATUS_TRACKER.md)

---

## Common Mistakes

1. **Not sourcing workspace** - Always `source install/setup.bash`
2. **Wrong CAN bitrate** - Must be exactly 500000 for MG6010
3. **USB permissions** - Add user to plugdev group
4. **Aggressive PID gains** - Start conservative, tune gradually
5. **Ignoring safety limits** - Never disable safety checks
6. **Poor lighting** - Causes 80%+ of detection issues
7. **Forgotten colcon build** - Rebuild after code changes

---

**Last Updated:** 2025-10-15  
**Contributions:** Submit improvements via pull request  
**Questions:** Check package READMEs first, then open issue with diagnostic info
