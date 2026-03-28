# EMERGENCY PROCEDURES — Pragati Cotton Picking Robot

**For:** March 2026 Field Trial
**Print this document and bring to field.**
**Last Updated:** March 8, 2026

---

## TABLE OF CONTENTS

1. [QUICK REFERENCE — EMERGENCY STOP](#1-quick-reference--emergency-stop)
2. [Safety System Overview](#2-safety-system-overview)
3. [Emergency: Motor Failure](#3-emergency-motor-failure)
4. [Emergency: CAN Bus-Off](#4-emergency-can-bus-off)
5. [Emergency: RPi Crash](#5-emergency-rpi-crash)
6. [Emergency: ODrive Stall](#6-emergency-odrive-stall)
7. [Emergency: E-Stop Recovery](#7-emergency-e-stop-recovery)
8. [Emergency: Battery Low](#8-emergency-battery-low)
9. [Emergency: Overheating](#9-emergency-overheating)
10. [Normal Startup Procedure](#10-normal-startup-procedure)
11. [Normal Shutdown Procedure](#11-normal-shutdown-procedure)
12. [Pre-Flight Checklist](#12-pre-flight-checklist)
13. [Network Reference](#13-network-reference)
14. [Physical Safety Warnings](#14-physical-safety-warnings)
15. [Contact Information](#15-contact-information)

---

## 1. QUICK REFERENCE — EMERGENCY STOP

> **If anything goes wrong, do the FIRST thing on this list that you can do.**

| Priority | Action | When to Use |
|----------|--------|-------------|
| **1. PHYSICAL** | **Disconnect CAN cable** from the arm/vehicle | Robot moving unexpectedly, person in danger |
| **2. SCRIPT** | `~/pragati_ros2/emergency_motor_stop.sh` | SSH access available, need to stop all motors |
| **3. SOFTWARE** | `ros2 service call /safety/trigger_emergency_stop std_srvs/srv/Trigger "{}"` | ROS2 still running, need orderly shutdown |
| **4. SERVICE** | `sudo systemctl stop arm_launch.service` | Need to stop all ROS2 nodes cleanly |
| **5. KILL** | `pkill -9 -f ros2 && pkill -9 -f yanthra && pkill -9 -f motor_control` | Nothing else works |
| **6. POWER** | **Disconnect battery** | Last resort — all other methods failed |

### Emergency Stop Script (PRIMARY METHOD)

```bash
# SSH into the RPi, then:
~/pragati_ros2/emergency_motor_stop.sh
```

This script performs a **5-step shutdown sequence**:
1. Kills ROS2 processes (SIGINT to launch, yanthra_move, mg6010, odrive)
2. Sends IDLE commands to all joints (via `/joint_idle` service, joints 0-3)
3. Sends stop commands via joint position topics
4. Hardware-level CAN commands: MG6010 motor OFF (0x80) to CAN IDs 0x141-0x144, ODrive ESTOP to nodes 0-2
5. GPIO cleanup: BCM pins 21, 13, 12, 20, 18 driven LOW (end-effector + compressor OFF)
6. Force-kills remaining processes, stops ROS2 daemon

### Other E-Stop Methods

```bash
# Via ROS2 service (if ROS2 is responsive):
ros2 service call /safety/trigger_emergency_stop std_srvs/srv/Trigger "{}"

# Via ROS2 topic:
ros2 topic pub --once /emergency_stop std_msgs/msg/Bool "data: true"

# Via web dashboard (if running):
curl -X POST http://<RPi_IP>:8090/api/estop

# Disable motors only (keeps ROS2 running):
ros2 service call /disable_motors std_srvs/srv/Trigger "{}"

# Kill everything forcefully:
sudo systemctl stop arm_launch.service
pkill -9 -f ros2; pkill -9 -f yanthra; pkill -9 -f cotton_detection; pkill -9 -f motor_control
```

---

## 2. Safety System Overview

### Safety State Machine

The Safety Monitor node runs continuously and manages the system through these states:

```
UNKNOWN → INITIALIZING → SAFE ↔ WARNING → CRITICAL → EMERGENCY
```

- **SAFE:** Normal operation allowed
- **WARNING:** Operation continues with alerts (e.g., temp 65-70°C, voltage 40-42V)
- **CRITICAL:** System degraded, approaching limits
- **EMERGENCY:** All motors stopped, manual reset required — **no auto-recovery**

### Automatic Safety Triggers

The Safety Monitor automatically triggers EMERGENCY shutdown for:

| Check | Warning Threshold | Emergency Threshold | Check Frequency |
|-------|------------------|---------------------|-----------------|
| Motor temperature | 65°C | 70°C | Every 10 cycles |
| Bus voltage (low) | < 42V | < 40V | Every 20 cycles |
| Bus voltage (high) | — | > 60V | Every 20 cycles |
| Joint velocity | — | > 10.0 rad/s | Every cycle |
| Joint position | — | ±90° (J2-J4), ±180° (J5) | Every cycle |
| Communication timeout | telemetry timeout | joint state timeout | Every 5 cycles |
| Motor error flags | — | Error codes 0x00F2 | Every cycle |

### What Happens During Emergency Shutdown

When the Safety Monitor triggers EMERGENCY:
1. Calls `emergency_stop()` on ALL registered motor controllers (fire-all-then-verify)
2. Disables all GPIO outputs (vacuum, compressor, LEDs)
3. Activates error LED (red)
4. Publishes to `/safety/emergency_stop` topic (latched — new subscribers get it)
5. System stays in EMERGENCY until manually reset

### Stall Detection (MG6010 Motors)

Built-in stall protection activates when:
- Motor current > 80% of rated current AND
- Position change < 0.5° AND
- Duration > 500ms

Result: Motor current set to zero, enters stall protection state.

### Thermal Derating (MG6010 Motors)

- Derating onset: 65°C (current linearly reduced)
- Derating limit: 85°C (firmware trips — zero current)
- Recovery hysteresis: 5°C (must cool to 80°C before re-enabling)

---

## 3. Emergency: Motor Failure

### Symptoms
- Motor not responding to commands
- Unexpected motor position or movement
- Motor error flags in logs (error code 0x00F2 = SYSTEM_ERROR, BAD_CONFIG, DRV_FAULT, MISSING_INPUT, VOLTAGE_ERROR)
- Safety Monitor reports EMERGENCY state
- Stall detection triggered (high current, no movement)

### Immediate Response

```
1. RUN emergency stop script:
   ~/pragati_ros2/emergency_motor_stop.sh

2. VERIFY all motors are stopped:
   - Listen for motor noise — should be silent
   - Check GPIO pins are LOW (no air pressure, no vacuum)

3. CHECK motor status (after system is stopped):
   for id in 1 2 3 4; do
     ros2 run motor_control_ros2 mg6010_test_node --ros-args \
       -p interface_name:=can0 -p node_id:=$id -p mode:=status
   done
   # Look for: temperature, voltage, error flags
```

### Recovery

```
1. IDENTIFY the failed motor from logs:
   journalctl -u arm_launch.service --since "5 minutes ago" --no-pager | grep -i "error\|fault\|stall"

2. CHECK motor temperature:
   - If temp > 50°C: WAIT for cooldown (at least 10 minutes)
   - If temp < 50°C: proceed to step 3

3. CHECK CAN bus health:
   ip -d link show can0 | grep -E "state|bitrate"
   ip -s link show can0 | grep -E "TX|RX"
   # State should be ERROR-ACTIVE, not BUS-OFF

4. CLEAR motor errors (auto-recovery is enabled):
   # The system will attempt: clear errors → reboot motor → verify
   # If auto-recovery fails, power cycle the motor (disconnect/reconnect CAN)

5. RESTART the arm service:
   sudo systemctl restart arm_launch.service

6. VERIFY motors are functional:
   ros2 service call /enable_motors std_srvs/srv/Trigger "{}"
   # Test with small movements:
   ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "data: 0.0"

7. RESET safety monitor (if in EMERGENCY state):
   ros2 service call /safety/reset std_srvs/srv/Trigger "{}"
   # NOTE: Reset is REJECTED if fault condition persists
```

### If Motor is Physically Damaged
- Do NOT attempt to operate the arm
- Document the failure (photo, logs)
- Collect logs: `./sync.sh --collect-logs --ip <IP>`
- Contact hardware lead (Gokul/Rajesh)

---

## 4. Emergency: CAN Bus-Off

### Symptoms
- Motors not responding to any commands
- Log messages: "CAN bus-off detected", "TX timeout", "CAN controller error"
- `ip link show can0` shows state: BUS-OFF or DOWN
- `ip -s link show can0` shows increasing TX/RX error counts

### Immediate Response

```
1. RUN emergency stop script:
   ~/pragati_ros2/emergency_motor_stop.sh

2. CHECK CAN bus state:
   ip -d link show can0 | grep state
   # Should say "ERROR-ACTIVE". If "BUS-OFF" or "DOWN" → proceed to recovery.

3. CHECK error counts:
   ip -s link show can0 | grep -E "TX|RX"
```

### Recovery

```
1. RESTART the CAN interface:
   sudo ip link set can0 down
   sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on

2. VERIFY CAN is back up:
   ip -d link show can0 | grep state
   # Must show ERROR-ACTIVE

3. RESTART the CAN watchdog:
   sudo systemctl restart can-watchdog@can0

4. RESTART the arm service:
   sudo systemctl restart arm_launch.service

5. VERIFY motors are reachable:
   for id in 1 2 3 4; do
     ros2 run motor_control_ros2 mg6010_test_node --ros-args \
       -p interface_name:=can0 -p node_id:=$id -p mode:=status
   done
```

### If CAN Bus Keeps Failing
- Check physical CAN cable connections (loose connectors, damaged wires)
- Check CAN termination resistors
- Check for CAN ID conflicts (each motor must have unique ID)
- Try a different CAN cable
- Check CAN HAT SPI connection: `ls /dev/spidev0.1` (should exist)
- Last resort: `sudo reboot` (full RPi reboot resets CAN hardware)

### CAN Watchdog Service

The CAN watchdog (`can-watchdog@can0.service`) automatically monitors and recovers the CAN bus:
- Runs continuously as a systemd service
- Detects bus-off and error conditions
- Automatically restarts the CAN interface
- Logs to: `journalctl -u can-watchdog-can0 --no-pager -n 50`

```bash
# Check watchdog status:
systemctl status can-watchdog@can0

# Restart watchdog:
sudo systemctl restart can-watchdog@can0

# View watchdog logs:
journalctl -u can-watchdog-can0 --since "10 minutes ago" --no-pager
```

---

## 5. Emergency: RPi Crash

### Symptoms
- SSH connection lost
- No heartbeat from arm (vehicle dashboard shows arm "offline")
- Arm completely unresponsive
- LEDs may go dark or freeze

### Immediate Response

```
1. PHYSICAL SAFETY: If arm was in motion, it will stop (motors lose CAN commands).
   Verify the arm has stopped moving before approaching.

2. TRY SSH ping:
   ping <RPi_IP>
   # If no response → RPi may need power cycle

3. TRY SSH connection:
   ssh ubuntu@<RPi_IP>
   # If connection refused or timeout → proceed to power cycle
```

### Recovery — SSH Still Works

```
1. CHECK what happened:
   journalctl -u arm_launch.service --since "10 minutes ago" --no-pager | tail -50

2. CHECK system resources:
   free -h          # Memory usage
   df -h            # Disk space
   uptime           # Load average
   cat /sys/class/thermal/thermal_zone0/temp  # CPU temp (divide by 1000)

3. RESTART the arm service:
   sudo systemctl restart arm_launch.service

4. VERIFY service started:
   systemctl status arm_launch.service --no-pager -l
```

### Recovery — RPi Unresponsive (Need Power Cycle)

```
1. DISCONNECT the battery or power supply to the RPi.
   Wait 10 seconds.

2. RECONNECT power.

3. WAIT 60-90 seconds for boot (RPi 4B boot time with services).

4. SSH in and verify:
   ssh ubuntu@<RPi_IP>
   systemctl status arm_launch.service --no-pager -l
   # arm_launch.service should auto-start on boot

5. CHECK CAN bus (may need manual restart after power cycle):
   ip -d link show can0 | grep state
   # If DOWN: sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on

6. CHECK clock (RPi has no RTC — clock drifts on power loss):
   date
   # If wrong: sudo date -u -s "$(date -u)"
   # Or re-provision: ./sync.sh --provision --ip <IP>  (syncs clock if drift > 5s)

7. VERIFY motors:
   for id in 1 2 3 4; do
     ros2 run motor_control_ros2 mg6010_test_node --ros-args \
       -p interface_name:=can0 -p node_id:=$id -p mode:=status
   done
```

### Preventing RPi Crashes
- Monitor CPU temperature: should be < 70°C (throttling starts at 80°C)
- Ensure adequate ventilation / heatsink on RPi
- Check SD card health: `dmesg | grep -i "mmc\|error"`
- ARM_client has restart protection: 5 restarts per 60s, then stops (prevents restart loops)

### Clearing Stale MQTT Status After Crash

After ungraceful arm shutdown (power cut), the MQTT broker retains the "offline" status:
```bash
# On vehicle RPi — clear retained message:
mosquitto_pub -t 'topic/ArmStatus_arm1' -r -n
# Replace arm1 with the affected arm ID
```

---

## 6. Emergency: ODrive Stall

### Symptoms
- Vehicle drive or steering motors locked up
- ODrive error flags non-zero
- Log messages about ODrive stall or error
- Vehicle not moving despite commands
- **February trial:** 9 vehicle crashes from ODrive stall loops (fixed in V2, March 05)

### Immediate Response

```
1. RUN emergency stop (on vehicle RPi):
   ~/pragati_ros2/emergency_motor_stop.sh
   # This sends ODrive ESTOP to nodes 0-2

2. CHECK ODrive status:
   odrive_can_tool --if can0 --nodes 3,4,5 --checks heartbeat,error,temp,bus,encoder
   # Look for: error flags, FET temperature, bus voltage
```

### Recovery

```
1. CLEAR ODrive errors:
   # ODrive errors must be cleared before re-enabling
   # The emergency_motor_stop.sh already sends ESTOP which clears errors

2. RESTART vehicle service:
   sudo systemctl restart vehicle_launch.service

3. VERIFY ODrive health:
   odrive_can_tool --if can0 --nodes 3,4,5 --checks heartbeat,error,temp,bus,encoder
   # All checks should PASS

4. TEST with small movement before resuming operations
```

### If ODrive Keeps Stalling
- Check motor wiring (loose phase wires cause DRV_FAULT)
- Check encoder connections
- Check bus voltage (ODrive needs stable 24V nominal)
- Check motor temperature — no temp sensors on ODrive (known gap GAP-DRV-001)
- Let motors cool for 10 minutes if they've been running hard
- Power cycle the ODrive (disconnect/reconnect power)

---

## 7. Emergency: E-Stop Recovery

### Context

After an emergency stop (triggered by script, Safety Monitor, or manual), the system is in EMERGENCY state. All motors are stopped and the Safety Monitor blocks all commands until manually reset.

### Recovery Procedure

```
1. IDENTIFY what caused the E-stop:
   journalctl -u arm_launch.service --since "10 minutes ago" --no-pager | grep -i "emergency\|safety\|error\|fault"

2. FIX the underlying cause:
   - If temperature: wait for cooldown (see Section 9)
   - If voltage: check/charge battery (see Section 8)
   - If motor error: check motor (see Section 3)
   - If CAN bus: fix CAN (see Section 4)
   - If joint limit violation: manually reposition arm to safe range

3. VERIFY the fault condition is cleared:
   # Check motor temps (must be < 50°C to restart safely):
   for id in 1 2 3 4; do
     ros2 run motor_control_ros2 mg6010_test_node --ros-args \
       -p interface_name:=can0 -p node_id:=$id -p mode:=status
   done

4. RESET the Safety Monitor:
   ros2 service call /safety/reset std_srvs/srv/Trigger "{}"
   # NOTE: This is REJECTED if the fault condition still exists
   # The Safety Monitor checks: temperature, voltage, motor errors before allowing reset

5. RE-ENABLE motors:
   ros2 service call /enable_motors std_srvs/srv/Trigger "{}"

6. TEST with small movements before resuming full operation:
   ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "data: 0.0"
```

### If Safety Reset is Rejected

The Safety Monitor rejects reset if the original fault condition persists. Check:
- Motor temperatures (must be below 65°C warning threshold)
- Bus voltage (must be 40-60V)
- Motor error flags (must be cleared)
- Joint positions (must be within limits)

If you cannot clear the fault:
1. Stop the arm service: `sudo systemctl stop arm_launch.service`
2. Fix the hardware issue
3. Restart: `sudo systemctl start arm_launch.service`
4. The Safety Monitor starts fresh in INITIALIZING → SAFE

---

## 8. Emergency: Battery Low

### Symptoms
- Safety Monitor WARNING at bus voltage < 42V
- Safety Monitor EMERGENCY at bus voltage < 40V
- Motors losing power or behaving erratically
- Dashboard/logs showing low voltage warnings
- **Nominal voltage:** 24V for ODrive, 36-52V for MG6010 bus

### Immediate Response

```
1. STOP all operations immediately:
   ~/pragati_ros2/emergency_motor_stop.sh

2. CHECK bus voltage:
   # On arm RPi:
   for id in 1 2 3 4; do
     ros2 run motor_control_ros2 mg6010_test_node --ros-args \
       -p interface_name:=can0 -p node_id:=$id -p mode:=status
   done
   # Look at voltage reading

   # On vehicle RPi:
   odrive_can_tool --if can0 --nodes 3,4,5 --checks bus
```

### Recovery

```
1. If voltage < 40V (EMERGENCY threshold):
   - STOP all operations
   - DISCONNECT motors from power (prevent deep discharge)
   - CHARGE or REPLACE battery

2. If voltage 40-42V (WARNING range):
   - Reduce operations (fewer pick cycles, shorter runs)
   - Plan to swap battery soon
   - Monitor voltage closely

3. After battery is charged/replaced:
   - Verify voltage > 42V before restarting
   - Follow normal startup procedure (Section 10)
```

### Red Flag at Startup
- **Do NOT start** if bus voltage < 22V at startup (indicates nearly dead battery)
- Nominal is 24V for ODrive bus

---

## 9. Emergency: Overheating

### Symptoms
- Safety Monitor WARNING at motor temp 65°C
- Safety Monitor EMERGENCY at motor temp 70°C
- Thermal derating kicks in at 65°C (reduced motor current)
- **Joint3 (MG6010)** is the most prone to overheating — overheats after ~10-15 minutes continuous operation
- Steering motors on vehicle peaked at 73-80°C in February trial

### Immediate Response

```
1. STOP all operations:
   ~/pragati_ros2/emergency_motor_stop.sh

2. DISABLE motors (if ROS2 still running):
   ros2 service call /disable_motors std_srvs/srv/Trigger "{}"
```

### Recovery

```
1. WAIT for cooldown:
   - Minimum: 10 minutes after EMERGENCY shutdown
   - Minimum: 5 minutes after WARNING

2. CHECK temperatures before restarting:
   for id in 1 2 3 4; do
     ros2 run motor_control_ros2 mg6010_test_node --ros-args \
       -p interface_name:=can0 -p node_id:=$id -p mode:=status
   done
   # Motor temp must be < 50°C before restarting

3. RESTART service:
   sudo systemctl restart arm_launch.service

4. RESET safety if needed:
   ros2 service call /safety/reset std_srvs/srv/Trigger "{}"
```

### Thermal Protocol (FOLLOW THIS TO PREVENT OVERHEATING)

| Parameter | Value |
|-----------|-------|
| Maximum continuous run time | 10 minutes |
| Minimum cooldown between runs | 5 minutes |
| Do not start if motor temp > | 50°C |
| Safety warning threshold | 65°C |
| Safety emergency threshold | 70°C |
| Firmware trip (hard shutdown) | 85°C |

**Rule of thumb:** Run 10 minutes, cool 5 minutes. Repeat.

---

## 10. Normal Startup Procedure

### Step 1: Power On
1. Connect battery to robot
2. Power on all RPis (vehicle + arms)
3. Wait 60-90 seconds for boot

### Step 2: Verify Network
```bash
# From dev workstation:
ping 192.168.1.100   # Vehicle
ping 192.168.1.107   # Arm 1
ping 192.168.1.106   # Arm 2
```

### Step 3: Verify Services Running
```bash
# Services auto-start on boot. Check status:
ssh ubuntu@192.168.1.100 'systemctl status vehicle_launch.service --no-pager -l'
ssh ubuntu@192.168.1.107 'systemctl status arm_launch.service --no-pager -l'
ssh ubuntu@192.168.1.106 'systemctl status arm_launch.service --no-pager -l'
```

### Step 4: Pre-Session Health Check
Run the pre-flight checklist (Section 12) before EVERY test session.

### Step 5: Verify MQTT
```bash
./sync.sh --test-mqtt
```

### Step 6: Enable Motors and Test
```bash
# On each arm RPi:
source ~/pragati_ros2/install/setup.bash
source /etc/default/pragati-arm

ros2 service call /enable_motors std_srvs/srv/Trigger "{}"

# Small test movement:
ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "data: 0.0"
```

---

## 11. Normal Shutdown Procedure

### Graceful Shutdown (Preferred)

```bash
# 1. Trigger shutdown switch (initiates parking sequence):
ros2 topic pub --once /shutdown_switch/command std_msgs/msg/Bool "data: true"
# Parking sequence: J5 → J3 (homing) → J4 → J3 (packing at -0.25 rot)
# Takes ~12 seconds

# 2. Stop the service (after parking completes):
sudo systemctl stop arm_launch.service
# Service has 15s timeout before SIGKILL

# 3. GPIO cleanup happens automatically via ExecStopPost:
#    Compressor (BCM18), Vacuum (BCM24), EE pins (BCM21/12/13/20) → all LOW
```

### Quick Shutdown (Skip Parking)

```bash
# Stop service immediately (SIGTERM → 15s → SIGKILL):
sudo systemctl stop arm_launch.service

# Or kill everything:
~/pragati_ros2/emergency_motor_stop.sh
```

### Power Off

```bash
# After service is stopped:
sudo shutdown now
# Wait for RPi activity LED to stop, then disconnect power
```

---

## 12. Pre-Flight Checklist

**Run this checklist before EVERY test session. Do NOT start if any check fails.**

### Hardware Checks
- [ ] Battery voltage > 22V (nominal 24V)
- [ ] CAN cables securely connected
- [ ] Camera (OAK-D Lite) USB cable connected
- [ ] Arm mechanical connections tight
- [ ] No visible damage to wiring or connectors
- [ ] Adequate ventilation around RPi (heatsink not blocked)
- [ ] End-effector hoses connected (vacuum + compressor)

### Software Checks (on each RPi)
```bash
# CAN bus healthy (should show ERROR-ACTIVE, 0 errors):
ip -d link show can0 | grep -E "state|bitrate"
ip -s link show can0 | grep -E "TX|RX"

# Motor temperatures ambient (~25-35°C, must be < 50°C):
for id in 1 2 3 4; do
  ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 -p node_id:=$id -p mode:=status
done

# Motor positions at expected home:
for id in 1 2 3 4; do
  ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 -p node_id:=$id -p mode:=angle
done

# GPIO daemon running:
systemctl status pigpiod

# Camera detected:
lsusb | grep Luxonis

# CPU temperature < 60°C at idle:
cat /sys/class/thermal/thermal_zone0/temp
# Divide by 1000 for Celsius

# Arm service running:
systemctl status arm_launch.service --no-pager -l
```

### Vehicle-Specific Checks
```bash
# ODrive health (all checks must PASS):
odrive_can_tool --if can0 --nodes 3,4,5 --checks heartbeat,error,temp,bus,encoder

# Steering motor health:
for id in 1 2 3; do
  ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 -p node_id:=$id -p mode:=status
done
# Steering motors are a thermal risk (Feb peak: 73-80°C)

# Mosquitto broker running:
systemctl status mosquitto --no-pager
```

### Red Flags — DO NOT START if:
- Motor temperature > 50°C at startup (residual heat)
- CAN bus state not ERROR-ACTIVE
- ODrive error flags non-zero
- Bus voltage < 22V
- Motor position significantly different from expected home

---

## 13. Network Reference

### IP Addresses

| Device | IP Address | Role | ROS_DOMAIN_ID |
|--------|-----------|------|---------------|
| Vehicle RPi | 192.168.1.100 | Mosquitto broker, vehicle_control, vehicle_mqtt_bridge | 0 |
| Arm 1 RPi | 192.168.1.107 | arm1, cotton picking | 1 |
| Arm 2 RPi | 192.168.1.106 | arm2, cotton picking | 2 |
| Dev Workstation | any on 192.168.1.x | Monitoring, deployment | — |

### SSH Access
```bash
ssh ubuntu@192.168.1.100   # Vehicle
ssh ubuntu@192.168.1.107   # Arm 1
ssh ubuntu@192.168.1.106   # Arm 2
# Username: ubuntu
```

### Key Services (systemd)

| Service | RPi | Purpose |
|---------|-----|---------|
| `arm_launch.service` | Arm RPis | ROS2 arm control (auto-starts on boot) |
| `vehicle_launch.service` | Vehicle RPi | ROS2 vehicle control (auto-starts on boot) |
| `pigpiod.service` | All RPis | GPIO daemon (required for motor/EE control) |
| `can-watchdog@can0.service` | All RPis | CAN bus auto-recovery watchdog |
| `field-monitor.service` | All RPis | Field monitoring |

### Key ROS2 Services

| Service | Type | Purpose |
|---------|------|---------|
| `/safety/trigger_emergency_stop` | std_srvs/Trigger | Trigger emergency shutdown |
| `/safety/reset` | std_srvs/Trigger | Reset from EMERGENCY state |
| `/enable_motors` | std_srvs/Trigger | Enable motor control |
| `/disable_motors` | std_srvs/Trigger | Disable motors (safe stop) |

### Key ROS2 Topics

| Topic | Type | Purpose |
|-------|------|---------|
| `/emergency_stop` | std_msgs/Bool | Emergency stop trigger |
| `/safety/emergency_stop` | — | Latched emergency stop status |
| `/joint_states` | sensor_msgs/JointState | Motor positions/velocities (~10Hz) |
| `/start_switch/command` | std_msgs/Bool | Start picking cycle |
| `/shutdown_switch/command` | std_msgs/Bool | Trigger graceful shutdown/parking |

### Log Locations (on RPi)

```
journalctl -u arm_launch.service          # Primary log source
journalctl -u can-watchdog-can0           # CAN watchdog logs
~/.ros/log/                               # ROS2 log files
~/pragati_ros2/logs/arm_client_*.log      # ARM client MQTT logs
~/pragati_ros2/logs/boot_timing_*.json    # Boot timing data
```

### Collecting Logs from Dev Workstation
```bash
./sync.sh --collect-logs --ip 192.168.1.107   # Arm 1
./sync.sh --collect-logs --ip 192.168.1.106   # Arm 2
./sync.sh --collect-logs --ip 192.168.1.100   # Vehicle
# Logs saved to: collected_logs/<timestamp>/
```

---

## 14. Physical Safety Warnings

### DANGER — Moving Parts
- The robot arm can move unexpectedly if software malfunctions
- **NEVER** place hands or body parts near arm joints during operation
- **ALWAYS** ensure the emergency stop procedure is accessible before starting
- Keep a **minimum 1-meter distance** from the arm during operation
- The end-effector has vacuum suction and a compressor — keep fingers clear

### Electrical Safety
- Battery voltage up to 52V — risk of electrical shock
- Do NOT touch exposed CAN bus wires while system is powered
- Do NOT disconnect/reconnect motors while system is running
- Disconnect battery before working on any electrical connections

### CAN Cable as Emergency Stop
- If all software methods fail, **physically disconnecting the CAN cable** immediately stops all motor communication
- Motors will hold position briefly then release (no CAN commands = no torque)
- This is safe but may cause the arm to drop under gravity — ensure nothing is underneath

### Environmental
- Do NOT operate in rain or wet conditions (electronics not waterproof)
- Ensure adequate shade for RPi to prevent CPU overheating (throttles at 80°C)
- Cotton field dust may affect camera and CAN connectors — inspect periodically

### GPIO Pin Safety
- BCM 18: Compressor — HIGH = pressurized air ON
- BCM 24: Vacuum Motor — HIGH = suction ON
- BCM 21: End-Effector Motor 1 Enable
- BCM 12: End-Effector Motor 2 Drop Enable
- **After E-stop:** All these pins are driven LOW (safe state)
- **After service stop:** ExecStopPost in systemd drives pins LOW automatically

---

## 15. Contact Information

| Role | Name | Contact |
|------|------|---------|
| Project Lead | Udayakumar | ___________________ |
| Hardware Lead (Electrical) | Gokul | ___________________ |
| Hardware Lead (Mechanical) | Rajesh | ___________________ |
| Software Lead | Udayakumar | ___________________ |

**Fill in phone numbers before printing for field use.**

### Emergency Communication
- **Primary:** Direct voice communication (field is small enough)
- **Secondary:** MQTT between arms — `{"action": "estop"}` to `/pragati/arm{N}/command`
- **Tertiary:** SSH from dev workstation to any RPi

---

## APPENDIX A: Decision Tree — Something Went Wrong

```
Is anyone in danger?
├── YES → Disconnect CAN cable or battery IMMEDIATELY
│         Then follow Section 1 (E-Stop)
│
└── NO → Can you SSH into the RPi?
         ├── YES → Run: ~/pragati_ros2/emergency_motor_stop.sh
         │         Then identify the problem:
         │         ├── Motor not moving → Section 3
         │         ├── CAN errors in log → Section 4
         │         ├── ODrive errors → Section 6
         │         ├── High temperature → Section 9
         │         ├── Low voltage → Section 8
         │         └── Unknown → Check logs:
         │             journalctl -u arm_launch.service --since "5 min ago" --no-pager | tail -50
         │
         └── NO → RPi crashed → Section 5
                  (Power cycle RPi, then restart)
```

---

## APPENDIX B: Quick Command Reference Card

**CUT THIS OUT AND TAPE TO ROBOT**

```
╔══════════════════════════════════════════════════════╗
║             PRAGATI EMERGENCY COMMANDS               ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  E-STOP:  ~/pragati_ros2/emergency_motor_stop.sh     ║
║                                                      ║
║  STOP SERVICE:  sudo systemctl stop arm_launch       ║
║                                                      ║
║  RESTART:  sudo systemctl restart arm_launch         ║
║                                                      ║
║  CAN FIX:  sudo ip link set can0 down               ║
║    sudo ip link set can0 up type can bitrate 500000  ║
║    restart-ms 100 berr-reporting on                  ║
║                                                      ║
║  RESET SAFETY:                                       ║
║    ros2 service call /safety/reset                   ║
║    std_srvs/srv/Trigger "{}"                         ║
║                                                      ║
║  ENABLE MOTORS:                                      ║
║    ros2 service call /enable_motors                  ║
║    std_srvs/srv/Trigger "{}"                         ║
║                                                      ║
║  PHYSICAL E-STOP: Disconnect CAN cable               ║
║  LAST RESORT: Disconnect battery                     ║
║                                                      ║
║  Vehicle: 192.168.1.100  Arm1: 192.168.1.107        ║
║  Arm2: 192.168.1.106     User: ubuntu                ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```

---

*Document generated from codebase analysis. Sources: emergency_motor_stop.sh, safety_monitor.cpp, safety_monitor.hpp, production.yaml, mg6010_can_interface.cpp, FIELD_TRIAL_CHEATSHEET.md, MARCH_FIELD_TRIAL_PLAN_2026.md, arm_launch.service, can-watchdog@.service, gpio_control_functions.hpp, GAP_TRACKING.md, TECHNICAL_SPECIFICATION_DOCUMENT.md*
