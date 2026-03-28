# MQTT Vehicle-ARM Integration Guide

**Date:** December 30, 2025  
**System:** Pragati ROS2 - Vehicle and ARM Communication  
**Author:** gokul

---

## Overview

This document describes the MQTT-based communication system between the Vehicle Raspberry Pi and ARM Raspberry Pi(s) in the Pragati cotton picking robot system. The integration allows the vehicle to send start/shutdown commands to remote ARM units and receive status updates.

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Vehicle Raspberry Pi                         │
│                      (172.24.146.32)                            │
│                                                                 │
│  ┌──────────────────┐    ┌────────────────────┐               │
│  │ vehicle_control  │───▶│ vehicle_mqtt_bridge│               │
│  │   (GPIO reads)   │    │   (ROS2→MQTT)      │               │
│  └──────────────────┘    └─────────┬──────────┘               │
│                                     │                           │
│                           ┌─────────▼──────────┐               │
│                           │ Mosquitto Broker   │               │
│                           │  (port 1883)       │               │
│                           └─────────┬──────────┘               │
└───────────────────────────────────┼─────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │         MQTT Topics           │
                    │  topic/start_switch_input_    │
                    │  topic/shutdown_switch_input  │
                    │  topic/ArmStatus_arm1         │
                    │  topic/ArmStatus_arm2         │
                    └───────────────┬───────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼──────────┐        ┌───────▼──────────┐              │
│  ARM RPi #1      │        │  ARM RPi #2      │              │
│ (172.24.146.49)  │        │  (TBD IP)        │              │
│                  │        │                  │              │
│ ┌──────────────┐ │        │ ┌──────────────┐ │              │
│ │ ARM_client.py│ │        │ │ ARM_client.py│ │              │
│ │ client_id:   │ │        │ │ client_id:   │ │              │
│ │   "arm1"     │ │        │ │   "arm2"     │ │              │
│ └──────┬───────┘ │        │ └──────┬───────┘ │              │
│        │         │        │        │         │              │
│ ┌──────▼───────┐ │        │ ┌──────▼───────┐ │              │
│ │ yanthra_move │ │        │ │ yanthra_move │ │              │
│ │   (ROS2)     │ │        │ │   (ROS2)     │ │              │
│ └──────────────┘ │        │ └──────────────┘ │              │
└──────────────────┘        └──────────────────┘              │
```

---

## Prerequisites

### Hardware Requirements
- **Vehicle RPi:** Raspberry Pi 4 (ubuntu@172.24.146.32)
- **ARM RPi(s):** One or more Raspberry Pi 4 units
- Network connectivity between all units

### Software Requirements
- ROS2 Jazzy installed on all RPis
- Python 3.10+
- `paho-mqtt` Python package

---

## Installation & Setup

### 1. MQTT Broker Setup (Vehicle RPi Only)

The vehicle Raspberry Pi hosts the MQTT broker that all ARM units connect to.

```bash
# SSH to vehicle RPi
ssh ubuntu@172.24.146.32

# Install Mosquitto MQTT broker
sudo apt update
sudo apt install -y mosquitto mosquitto-clients

# Configure broker to listen on all interfaces
sudo nano /etc/mosquitto/mosquitto.conf

# Add these lines at the end:
listener 1883
allow_anonymous true

# Save and exit (Ctrl+X, Y, Enter)

# Enable and start the broker
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

# Verify broker is running and listening on all interfaces
sudo systemctl status mosquitto
sudo netstat -tulpn | grep 1883
# Should show: tcp  0  0  0.0.0.0:1883  0.0.0.0:*  LISTEN
```

### 2. Install Python MQTT Library (All RPis)

```bash
# On vehicle RPi and all ARM RPis
pip3 install paho-mqtt
```

### 3. Vehicle MQTT Bridge Setup

The `vehicle_mqtt_bridge.py` script runs on the vehicle RPi and bridges ROS2 topics to MQTT.

**File Location:** `~/pragati_ros2/scripts/vehicle_mqtt_bridge.py`

**Key Configuration:**
```python
# MQTT Configuration
MQTT_BROKER = 'localhost'  # Broker runs locally on vehicle
MQTT_PORT = 1883
CLIENT_ID = 'vehicle_mqtt_bridge'

# ARM Configuration - List of all ARM client IDs
ARM_CLIENT_IDS = ['arm1', 'arm2']  # Add more as needed
```

**Topics Handled:**
- **Subscribe (ROS2):**
  - `/vehicle/start_switch_command` (Bool) - from vehicle_control GPIO
  - `/vehicle/shutdown_switch_command` (Bool) - from vehicle_control GPIO
  
- **Publish (MQTT):**
  - `topic/start_switch_input_` - to ARM(s)
  - `topic/shutdown_switch_input` - to ARM(s)

- **Subscribe (MQTT):**
  - `topic/ArmStatus_arm1` - from ARM #1
  - `topic/ArmStatus_arm2` - from ARM #2
  
- **Publish (ROS2):**
  - `/vehicle/arm_status` (String) - format: "arm1:ready"

### 4. ARM Client Setup

The `ARM_client.py` script runs on each ARM Raspberry Pi.

**File Location:** `~/pragati_ros2/launch/ARM_client.py`

**Key Configuration:**
```python
# MQTT Configuration
MQTT_ADDRESS = '172.24.146.32'  # Vehicle RPi IP address
CONNECTION_TIMEOUT = 300
status_publish_rate = 1  # Hz

# Client ID - MUST BE UNIQUE for each ARM
client_id = "arm1"  # Change to "arm2", "arm3", etc. for other ARMs
```

**Topics Handled:**
- **Subscribe (MQTT):**
  - `topic/start_switch_input_` - from vehicle
  - `topic/shutdown_switch_input` - from vehicle

- **Publish (MQTT):**
  - `topic/ArmStatus_arm1` - to vehicle (status updates)

- **Publish (ROS2):**
  - `/start_switch/command` (Bool) - to yanthra_move
  - `/shutdown_switch/command` (Bool) - to yanthra_move

- **Service Client (ROS2):**
  - `/yanthra_move/current_arm_status` - polls ARM status

---

## Configuration for Multiple ARMs

### Adding a Second ARM

1. **On Vehicle RPi - Update vehicle_mqtt_bridge.py:**
   ```python
   # Edit ~/pragati_ros2/scripts/vehicle_mqtt_bridge.py
   ARM_CLIENT_IDS = ['arm1', 'arm2']  # Add arm2
   ```

2. **On ARM RPi #2 - Configure ARM_client.py:**
   ```python
   # Edit ~/pragati_ros2/launch/ARM_client.py
   MQTT_ADDRESS = '172.24.146.32'  # Vehicle IP
   client_id = "arm2"  # UNIQUE ID for second ARM
   ```

3. **Copy files:**
   ```bash
   # From development machine to vehicle
   rsync -avz ~/pragati_ros2/scripts/vehicle_mqtt_bridge.py ubuntu@172.24.146.32:~/pragati_ros2/scripts/

   # From development machine to ARM #2
   rsync -avz ~/pragati_ros2/launch/ARM_client.py ubuntu@<ARM2_IP>:~/pragati_ros2/launch/
   ```

**Important:** Each ARM must have a unique `client_id`. The vehicle bridge will automatically subscribe to status from all configured ARMs.

---

## Testing Procedures

### Test 1: MQTT Broker Functionality

**Purpose:** Verify MQTT broker is running and accepting messages

**On Vehicle RPi:**
```bash
# Terminal 1 - Subscriber (keep running)
mosquitto_sub -h localhost -t 'test/topic' -v

# Terminal 2 - Publisher
mosquitto_pub -h localhost -t 'test/topic' -m 'Hello MQTT!'
```

**Expected Result:** Terminal 1 shows: `test/topic Hello MQTT!`

### Test 2: MQTT Network Connectivity

**Purpose:** Verify ARM can connect to vehicle's MQTT broker

**Vehicle RPi Terminal 1:**
```bash
# Subscribe to all topics
mosquitto_sub -h localhost -t 'topic/#' -v
```

**ARM RPi Terminal:**
```bash
# Publish test message to vehicle broker
mosquitto_pub -h 172.24.146.32 -t 'topic/test_from_arm' -m 'Hello from ARM!'
```

**Expected Result:** Vehicle subscriber shows: `topic/test_from_arm Hello from ARM!`

### Test 3: ROS2 to MQTT Bridge

**Purpose:** Verify vehicle_mqtt_bridge forwards ROS2 messages to MQTT

**Setup:**
```bash
# Terminal 1 - Vehicle RPi - Monitor MQTT
mosquitto_sub -h localhost -t 'topic/#' -v

# Terminal 2 - Vehicle RPi - Run bridge
source /opt/ros/jazzy/setup.bash
python3 ~/pragati_ros2/scripts/vehicle_mqtt_bridge.py

# Terminal 3 - Vehicle RPi - Send ROS2 command
source /opt/ros/jazzy/setup.bash
ros2 topic pub --once /vehicle/start_switch_command std_msgs/msg/Bool "{data: true}"
```

**Expected Flow:**
1. Terminal 3 publishes to ROS2 topic
2. Terminal 2 (bridge) logs: "🟢 START switch pressed - forwarding to ARM via MQTT"
3. Terminal 1 shows: `topic/start_switch_input_ True`

### Test 4: End-to-End Integration

**Purpose:** Test complete flow from vehicle GPIO to ARM ROS2

**Vehicle RPi Setup:**
```bash
# Terminal 1 - Monitor MQTT
mosquitto_sub -h localhost -t 'topic/#' -v

# Terminal 2 - Run vehicle_mqtt_bridge
source /opt/ros/jazzy/setup.bash
python3 ~/pragati_ros2/scripts/vehicle_mqtt_bridge.py

# Terminal 3 - Run vehicle_control (if testing with actual GPIO)
cd ~/pragati_ros2
source install/setup.bash
ros2 launch vehicle_control vehicle.launch.py
```

**ARM RPi Setup:**
```bash
# Terminal 1 - Launch yanthra_move
source /opt/ros/jazzy/setup.bash
source ~/pragati_ros2/install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true

# Terminal 2 - Run ARM_client
source /opt/ros/jazzy/setup.bash
source ~/pragati_ros2/install/setup.bash
python3 ~/pragati_ros2/launch/ARM_client.py

# Terminal 3 - Monitor ROS2 topic (verify commands received)
ros2 topic echo /start_switch/command
```

**Test Action:**
Press the start button (GPIO6) on vehicle, or send manual command:
```bash
ros2 topic pub --once /vehicle/start_switch_command std_msgs/msg/Bool "{data: true}"
```

**Expected Results:**
1. Vehicle MQTT monitor shows: `topic/start_switch_input_ True`
2. ARM_client logs: "Received MQTT message", "Published START command to ROS-2"
3. ARM ROS2 monitor shows: `data: true`
4. ARM publishes status: `topic/ArmStatus_arm1 ACK` (if arm was ready)
5. Vehicle receives status update: "📥 MQTT received: topic/ArmStatus_arm1 = ACK"

### Test 5: ARM Status Updates

**Purpose:** Verify ARM status flows back to vehicle

**Vehicle RPi:**
```bash
# Monitor MQTT status updates
mosquitto_sub -h localhost -t 'topic/ArmStatus_arm1' -v
```

**Expected:** See status transitions like:
- `UNINITIALISED` → `ready` → `ACK` → `busy` → `ready`

---

## Message Formats

### MQTT Messages

| Topic | Direction | Payload | Description |
|-------|-----------|---------|-------------|
| `topic/start_switch_input_` | Vehicle → ARM | `'True'` or `'False'` | Start command trigger |
| `topic/shutdown_switch_input` | Vehicle → ARM | `'True'` or `'False'` | Shutdown command trigger |
| `topic/ArmStatus_arm1` | ARM → Vehicle | `'UNINITIALISED'`, `'ACK'`, `'busy'`, `'ready'`, `'error'` | ARM state |

### ROS2 Messages

| Topic | Type | Direction | Description |
|-------|------|-----------|-------------|
| `/vehicle/start_switch_command` | `std_msgs/Bool` | vehicle_control → bridge | GPIO start button |
| `/vehicle/shutdown_switch_command` | `std_msgs/Bool` | vehicle_control → bridge | GPIO shutdown button |
| `/vehicle/arm_status` | `std_msgs/String` | bridge → vehicle | ARM status (format: "arm1:ready") |
| `/start_switch/command` | `std_msgs/Bool` | ARM_client → yanthra_move | Start trigger on ARM |
| `/shutdown_switch/command` | `std_msgs/Bool` | ARM_client → yanthra_move | Shutdown trigger on ARM |

---

## Troubleshooting

### MQTT Broker Not Accessible from ARM

**Symptoms:** ARM can't connect, vehicle MQTT monitor doesn't see ARM messages

**Checks:**
```bash
# On vehicle RPi
sudo netstat -tulpn | grep 1883
# Should show: 0.0.0.0:1883 (not 127.0.0.1:1883)

# Verify firewall (if enabled)
sudo ufw status
sudo ufw allow 1883/tcp

# Test from ARM
ping 172.24.146.32
telnet 172.24.146.32 1883
```

**Fix:** Ensure `/etc/mosquitto/mosquitto.conf` has:
```
listener 1883
allow_anonymous true
```

### ARM_client Stuck "Waiting for service"

**Symptoms:** ARM_client doesn't connect to MQTT, logs show waiting for yanthra_move service

**Cause:** yanthra_move isn't running

**Fix:**
```bash
# Launch yanthra_move first (on ARM RPi)
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true
```

### Messages Published But Not Received

**Symptoms:** mosquitto_pub succeeds but mosquitto_sub doesn't show message

**Cause:** Subscriber must be running BEFORE publisher sends message (MQTT doesn't queue unless retained)

**Fix:**
1. Start subscriber FIRST and keep it running
2. Then publish messages
3. Or use retained messages: `mosquitto_pub -r -h localhost -t 'topic' -m 'msg'`

### Wrong MQTT Broker Address

**Symptoms:** ARM_client can't connect, connection timeout

**Check ARM_client.py configuration:**
```python
MQTT_ADDRESS = '172.24.146.32'  # Must be vehicle RPi IP, NOT localhost
```

**Check vehicle_mqtt_bridge.py configuration:**
```python
MQTT_BROKER = 'localhost'  # Must be localhost (broker runs locally)
```

---

## Network Configuration

### IP Addresses
- **Vehicle RPi:** `172.24.146.32` (hosts MQTT broker)
- **ARM RPi #1:** `172.24.146.49` (client_id: "arm1")
- **ARM RPi #2:** `<TBD>` (client_id: "arm2")

### Ports
- **MQTT:** 1883 (TCP)

### Firewall Rules (if enabled)
```bash
# On vehicle RPi
sudo ufw allow 1883/tcp
sudo ufw status
```

---

## Production Deployment

### Systemd Services (Optional)

For automatic startup, create systemd services:

**Vehicle RPi - vehicle_mqtt_bridge.service:**
```ini
[Unit]
Description=Vehicle MQTT Bridge
After=network.target mosquitto.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/pragati_ros2
Environment="ROS_DOMAIN_ID=0"
ExecStart=/bin/bash -c 'source /opt/ros/jazzy/setup.bash && python3 /home/ubuntu/pragati_ros2/scripts/vehicle_mqtt_bridge.py'
Restart=always

[Install]
WantedBy=multi-user.target
```

**ARM RPi - arm_mqtt_client.service:**
```ini
[Unit]
Description=ARM MQTT Client
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/pragati_ros2
Environment="ROS_DOMAIN_ID=0"
ExecStart=/bin/bash -c 'source /opt/ros/jazzy/setup.bash && source /home/ubuntu/pragati_ros2/install/setup.bash && python3 /home/ubuntu/pragati_ros2/launch/ARM_client.py'
Restart=always

[Install]
WantedBy=multi-user.target
```

**Installation:**
```bash
# Copy service file
sudo cp <service_file> /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable <service_name>
sudo systemctl start <service_name>
```

---

## Quick Reference Commands

### Vehicle RPi
```bash
# Start MQTT broker
sudo systemctl start mosquitto

# Run vehicle MQTT bridge
python3 ~/pragati_ros2/scripts/vehicle_mqtt_bridge.py

# Monitor all MQTT traffic
mosquitto_sub -h localhost -t 'topic/#' -v

# Test publish
ros2 topic pub --once /vehicle/start_switch_command std_msgs/msg/Bool "{data: true}"
```

### ARM RPi
```bash
# Launch yanthra_move
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true

# Run ARM client
python3 ~/pragati_ros2/launch/ARM_client.py

# Monitor start commands
ros2 topic echo /start_switch/command

# Test ARM status publish (manual)
mosquitto_pub -h 172.24.146.32 -t 'topic/ArmStatus_arm1' -m 'ready'
```

---

## Log Files & Debugging

### Log File Locations

All MQTT bridge logs are stored with timestamps to prevent overwriting across restarts.

**ARM Client Logs:**
- **Location:** `~/pragati_ros2/logs/arm_client_YYYYMMDD_HHMMSS.log`
- **Retention:** Last 10 files kept automatically
- **Contains:** 
  - MQTT connection/disconnection events
  - ROS2 service calls to yanthra_move
  - Status updates and transitions
  - Reconnection attempts with count

**Vehicle MQTT Bridge Logs:**
- **Location:** `~/pragati_ros2/logs/vehicle_mqtt_bridge_YYYYMMDD_HHMMSS.log`
- **Retention:** Last 10 files kept automatically
- **Contains:**
  - ROS2 → MQTT message forwarding
  - ARM status updates received
  - Connection health monitoring
  - Reconnection events

### Viewing Logs

```bash
# View latest ARM client log
ls -t ~/pragati_ros2/logs/arm_client_*.log | head -1 | xargs tail -f

# View latest vehicle bridge log
ls -t ~/pragati_ros2/logs/vehicle_mqtt_bridge_*.log | head -1 | xargs tail -f

# Search for errors across all logs
grep -i error ~/pragati_ros2/logs/*.log

# Search for reconnection events
grep -i "reconnect" ~/pragati_ros2/logs/*.log

# View logs from specific date
ls ~/pragati_ros2/logs/arm_client_20260203_*.log
```

### Log Rotation

Both scripts automatically maintain log rotation:
- Maximum 10 most recent log files kept
- Older files automatically deleted on startup
- Manual cleanup: `rm ~/pragati_ros2/logs/arm_client_*.log` (keeps current)

### Debugging Connection Issues

**Check MQTT reconnections:**
```bash
# Count reconnection events
grep "RECONNECTED" ~/pragati_ros2/logs/arm_client_*.log | wc -l

# See when reconnections happened
grep "RECONNECTED" ~/pragati_ros2/logs/arm_client_*.log
```

**Verify topic resubscription:**
```bash
# Check if topics were resubscribed after disconnect
grep "Resubscribed" ~/pragati_ros2/logs/arm_client_*.log
```

**Monitor connection health:**
```bash
# View connection health stats
grep "MQTT Health" ~/pragati_ros2/logs/vehicle_mqtt_bridge_*.log
```

### Common Log Patterns

**Successful startup:**
```
✅ MQTT Connected (first time)
✅ Subscribed to topic/start_switch_input_
✅ Subscribed to topic/shutdown_switch_input
```

**Network disconnect/reconnect:**
```
⚠️ MQTT disconnected unexpectedly (code 1)
🔄 MQTT RECONNECTED (count: 1)
✅ Resubscribed to topic/start_switch_input_
```

**ARM status updates:**
```
📥 MQTT received: topic/ArmStatus_arm1 = ready
📤 Published arm1 status to ROS2: ready
```

---

## References

- [MQTT Protocol Documentation](http://mqtt.org/)
- [Paho MQTT Python Client](https://pypi.org/project/paho-mqtt/)
- [ROS2 Jazzy Documentation](https://docs.ros.org/en/jazzy/)
- [Troubleshooting Guide](guides/TROUBLESHOOTING.md) - Network and connectivity issues
- Original ROS1 implementation: `~/rasfiles/ARM_Vehicle_MQTT_ROS2_Runbook.md`

---

**Document Version:** 1.1  
**Last Updated:** February 3, 2026  
**Status:** Production Ready ✅  
**Changes:** Added log file documentation and debugging guide
