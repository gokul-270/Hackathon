# Field Trial Command Cheatsheet 🌾

**For:** March 2026 Field Trial
**Platform:** Raspberry Pi 4B (Ubuntu 24.04, ROS2 Jazzy)
**Last Updated:** March 6, 2026

---

## 🔨 Build Commands

### 1. Cross-Compilation (For RPi Deployment)
**Use this on your dev workstation to build for the Raspberry Pi.**

```bash
# Build EVERYTHING for RPi (ARM + Vehicle + Robot Description)
./build.sh rpi

# Clean build for RPi (removes build_rpi/ and install_rpi/)
./build.sh --clean rpi

# Build ONLY a specific package for RPi
# NOTE: ./build.sh rpi pkg <name> does NOT work (pkg overwrites BUILD_MODE from rpi)
# Use PACKAGE_NAME env var instead:
PACKAGE_NAME=yanthra_move ./build.sh rpi

# Build arm-role packages only (clean)
./build.sh --clean arm
```

### 2. Local Build (For Dev Workstation Testing)
```bash
# Build ARM packages locally
./build.sh arm

# Build Vehicle packages locally
./build.sh vehicle

# Build single package locally
./build.sh pkg yanthra_move

# Fast dev build (tests disabled, symlink install)
./build.sh fast

# Clean arm or vehicle packages only (removes from build/ and install/)
./build.sh clean arm
./build.sh clean vehicle
```

### 3. Deployment (sync.sh)
**Always use `./sync.sh` -- never raw `rsync` or `scp`.**

```bash
# Deploy cross-compiled ARM binaries to a single RPi
./sync.sh --deploy-cross --ip 192.168.1.100

# Deploy to ALL saved arms in parallel (reads ALL_ARMS from config.env)
# NOTE: --all-arms is legacy/deprecated — prefer --all-targets or --ips
./sync.sh --deploy-cross --all-arms

# Deploy to vehicle + ALL arms in one command (reads config.env)
./sync.sh --deploy-cross --all-targets

# Deploy to specific targets (comma-separated names or IPs)
./sync.sh --deploy-cross --ips arm1,arm2

# Force sequential execution (parallel is the default for multi-IP)
./sync.sh --deploy-cross --all-targets --sequential

# Deploy + restart services in one command
./sync.sh --deploy-cross --ip 192.168.1.100 --restart

# Use rsync checksum mode (catches bit-rot, slower)
./sync.sh --deploy-cross --ip 192.168.1.100 --checksum

# Dry-run: preview what would be deployed without actually deploying
./sync.sh --deploy-cross --ip 192.168.1.100 --dry-run

# Verify RPi health (read-only check of fixes, services, deploy)
./sync.sh --verify --ip 192.168.1.100

# Sync source and trigger native build on RPi
./sync.sh --build --ip 192.168.1.100

# Provision RPi (OS fixes + install services + arm identity + clock sync)
# Vehicle:
./sync.sh --provision --ip 192.168.1.100 --role vehicle
# Arm (sets MQTT_ADDRESS to vehicle IP):
./sync.sh --provision --ip 192.168.1.107 --role arm --arm-id arm1 --mqtt-address 192.168.1.100

# NOTE: --provision preserves existing MQTT_ADDRESS on re-provision.
# Only pass --mqtt-address if you need to CHANGE it.

# Collect field trial logs from RPi
./sync.sh --collect-logs --ip 192.168.1.100

# Collect logs from all hosts, reuse previous session (incremental)
./sync.sh --collect-logs --continue

# Name the session directory (instead of auto-generated timestamp)
./sync.sh --collect-logs --session-name trial-01

# Test MQTT connectivity between vehicle and all arms
./sync.sh --test-mqtt

# Save target for --all-arms resolution
./sync.sh --save-target arm1 --ip 192.168.1.107

# See all options
./sync.sh --help

# --- Profiles (alternative to --ip/--ips) ---
# Deploy using a named profile from config.env
./sync.sh --deploy-cross --profile rpi1

# Deploy to all configured profiles
./sync.sh --deploy-cross --all-profiles

# Provision all profiles
./sync.sh --provision --all-profiles
```

### After Build - Source Environment
**On Dev Workstation:**
```bash
source install/setup.bash
```

**On RPi (auto-sourced by arm_launch.service, but for manual SSH):**
```bash
source ~/pragati_ros2/install/setup.bash
```

---

## 🚀 Quick Start (Copy-Paste Ready)

### ARM RPi: Start via systemd (Recommended)
The arm system starts automatically via `arm_launch.service`. To manually manage:
```bash
# Check service status
sudo systemctl status arm_launch.service

# Restart service (after deploying new code)
sudo systemctl restart arm_launch.service

# Stop service
sudo systemctl stop arm_launch.service

# View live logs
journalctl -u arm_launch.service -f

# View last 200 lines of logs
journalctl -u arm_launch.service -n 200 --no-pager
```

### ARM RPi: Start manually (debugging)
```bash
# Stop the service first
sudo systemctl stop arm_launch.service

# Source workspace
source ~/pragati_ros2/install/setup.bash

# IMPORTANT: source arm identity for correct ROS_DOMAIN_ID
source /etc/default/pragati-arm

# Launch complete arm system (hardware mode)
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true
```

### Start Vehicle System
```bash
ros2 launch vehicle_control vehicle_complete.launch.py
```

### Start Motor Controller Only
```bash
ros2 launch motor_control_ros2 mg6010_controller.launch.py
```

---

## 🚀 Field Trial Deployment Sequence (Feb 25, 2026)

### Network Setup
```
Vehicle RPi:  192.168.1.100 (mosquitto broker, vehicle_control, vehicle_mqtt_bridge)
Arm 1 RPi:    192.168.1.107 (arm1, ROS_DOMAIN_ID=1)
Arm 2 RPi:    192.168.1.106 (arm2, ROS_DOMAIN_ID=2)
Dev Workstation: any IP on 192.168.1.x subnet
```

### Step 1: Build on Dev Workstation
```bash
# Full cross-compile for RPi (ARM64)
./build.sh rpi

# If OOM on low-memory machine, use single worker:
# COLCON_PARALLEL_WORKERS=1 ./build.sh rpi

# Single-package rebuild (if only one package changed):
# PACKAGE_NAME=vehicle_control ./build.sh rpi
```

### Step 2: Provision All RPis (First Time or After Re-flash)
```bash
# Vehicle (installs mosquitto broker, vehicle_launch.service, syncs clock)
./sync.sh --provision --ip 192.168.1.100 --role vehicle

# Arm 1 (sets MQTT_ADDRESS to vehicle, installs arm_launch.service, syncs clock)
./sync.sh --provision --ip 192.168.1.107 --role arm --arm-id arm1 --mqtt-address 192.168.1.100

# Arm 2
./sync.sh --provision --ip 192.168.1.106 --role arm --arm-id arm2 --mqtt-address 192.168.1.100

# NOTE: Re-provisioning is idempotent — already-applied steps are skipped.
# Only clock sync re-applies if drift > 5s (RPi has no RTC).
# Only pass --mqtt-address if you need to CHANGE it (preserves existing on re-provision).

# Save targets for --all-arms (do this once after provisioning)
./sync.sh --save-target arm1 --ip 192.168.1.107
./sync.sh --save-target arm2 --ip 192.168.1.106
```

### Step 3: Deploy Code to All RPis
```bash
# Deploy to vehicle + ALL arms (reads config.env — recommended)
./sync.sh --deploy-cross --all-targets

# Deploy to ALL saved arms only (no vehicle)
./sync.sh --deploy-cross --all-arms

# Deploy to specific targets (comma-separated names or IPs)
./sync.sh --deploy-cross --ips arm1,arm2

# Deploy to a single target
./sync.sh --deploy-cross --ip 192.168.1.107

# Force sequential execution (parallel is the default for multi-IP)
./sync.sh --deploy-cross --all-targets --sequential

# Use rsync checksum mode (slower but catches bit-rot)
./sync.sh --deploy-cross --all-arms --checksum

# Restart services (use -t for sudo tty allocation)
ssh -t ubuntu@192.168.1.100 'sudo systemctl restart vehicle_launch.service'
ssh -t ubuntu@192.168.1.107 'sudo systemctl restart arm_launch.service'
ssh -t ubuntu@192.168.1.106 'sudo systemctl restart arm_launch.service'
```

### Step 4: Verify MQTT Connectivity
```bash
# End-to-end MQTT test (vehicle broker -> each arm)
./sync.sh --test-mqtt

# Manual verification (from vehicle RPi):
ssh ubuntu@192.168.1.100 'mosquitto_pub -t topic/mqtt_test -m "hello"'
# On arm RPi, should see the message:
ssh ubuntu@192.168.1.107 'timeout 5 mosquitto_sub -t topic/mqtt_test -C 1'
```

### Step 5: Verify Services Running
```bash
# Vehicle
ssh ubuntu@192.168.1.100 'systemctl status vehicle_launch.service --no-pager -l'
ssh ubuntu@192.168.1.100 'systemctl status mosquitto --no-pager'
ssh ubuntu@192.168.1.100 'ps aux | grep vehicle_mqtt_bridge'
ssh ubuntu@192.168.1.100 'tail -3 $(ls -t ~/pragati_ros2/logs/vehicle_mqtt_bridge_*.log | head -1)'

# Arm 1 (check MQTT connection and health)
ssh ubuntu@192.168.1.107 'systemctl status arm_launch.service --no-pager -l'
ssh ubuntu@192.168.1.107 'tail -3 $(ls -t ~/pragati_ros2/logs/arm_client_*.log | head -1)'
# Should show: Health: mqtt=connected status=ready svc_ok

# Arm 2
ssh ubuntu@192.168.1.106 'systemctl status arm_launch.service --no-pager -l'
ssh ubuntu@192.168.1.106 'tail -3 $(ls -t ~/pragati_ros2/logs/arm_client_*.log | head -1)'
```

### Step 6: Test Signal Chain
```bash
# Press physical START button on vehicle, then check:

# Vehicle logs (hops 1-3)
ssh ubuntu@192.168.1.100 'journalctl -u vehicle_launch.service --since "2 minutes ago" --no-pager | grep SIGNAL_CHAIN'

# Arm logs (hops 6-8)
ssh ubuntu@192.168.1.107 'journalctl -u arm_launch.service --since "2 minutes ago" --no-pager | grep SIGNAL_CHAIN'
```

### Step 7: Collect Logs After Trial
```bash
# Collect from all hosts (vehicle + arms, reads config.env)
./sync.sh --collect-logs

# Single target
./sync.sh --collect-logs --ip 192.168.1.100

# Incremental collection (reuse latest session dir, skip already-collected files)
./sync.sh --collect-logs --continue

# Collect last 7 days of logs
./sync.sh --collect-logs --date last-week

# Logs saved to collected_logs/<timestamp>/<target>/
```

### Known Gotchas
- **RPi clock drifts** on power cycle (no RTC). `--provision` and `--deploy-cross` both
  sync clock automatically (if drift > 5s). Requires passwordless sudo for `date`/`hwclock`.
- **`--all-arms` needs config.env**: Ensure `ALL_ARMS=arm1,arm2` and `ARM_1_IP`, `ARM_2_IP`
  etc. are set in `config.env`. Use `--all-targets` to include the vehicle too.
- **Parallel is the default**: Multi-target commands (`--ips`, `--all-arms`, `--all-targets`)
  run in parallel by default. Use `--sequential` for one-at-a-time execution with
  real-time per-target output.
- **MQTT default is 10.42.0.10** (USB tethering). Field trial uses **192.168.1.100** (LAN).
  Verify with: `ssh ubuntu@<arm_ip> 'cat /etc/default/pragati-arm | grep MQTT'`.
- **Build single RPi package**: Use `PACKAGE_NAME=<pkg> ./build.sh rpi`, NOT `./build.sh rpi pkg <pkg>`.
- **CMake cache staleness**: If CMakeLists.txt changed, delete `build_rpi/<pkg>/` before rebuild.
- **Symlink-vs-directory conflict**: If build fails with "cannot overwrite directory with symlink",
  run `rm -rf build/<pkg>/ament_cmake_python/<pkg>/<pkg>` and rebuild.
- **ARM_client heartbeat**: ARM_client re-publishes its status every 30s. If the vehicle
  bridge shows `offline` for an arm, wait up to 30s for the next heartbeat. If still offline
  after 60s, the arm's MQTT connection is truly broken.
- **ARM_client health logs**: ARM_client logs `Health: mqtt=... status=... svc_ok` every 10s.
  If the log file stops growing, the process is frozen/crashed -- restart the service.
- **Dual network interfaces**: RPi may have both WiFi and Ethernet connected to the same
  router (different IPs). MQTT connects outbound on whichever interface the OS routes
  through -- this is fine. SSH works via either IP.
- **Retained MQTT LWT**: After ungraceful arm shutdown (power cut), the broker retains
  `offline` on `topic/ArmStatus_<arm_id>`. The vehicle bridge clears these on startup,
  but if you see stale `offline`, manually clear with:
  `mosquitto_pub -t 'topic/ArmStatus_arm1' -r -n` (on vehicle RPi).

---

## 🌐 Multi-Arm Domain IDs (CRITICAL)

Each arm gets its own `ROS_DOMAIN_ID` to prevent cross-arm topic interference.
The systemd service reads this from `/etc/default/pragati-arm` automatically.

| RPi | ARM_ID | ROS_DOMAIN_ID | IP |
|-----|--------|---------------|--------------|
| Vehicle | - | 0 | 192.168.1.100 |
| Arm 1 | arm1 | 1 | 192.168.1.107 |
| Arm 2 | arm2 | 2 | 192.168.1.106 |

**When SSH'd to an RPi, you MUST match the domain ID or `ros2 topic` commands won't reach nodes:**
```bash
# Check current identity
cat /etc/default/pragati-arm

# If ~/.bashrc is patched (sync.sh --provision does this), domain is auto-set.
# Otherwise, manually export before using ros2 CLI:
export ROS_DOMAIN_ID=2          # Must match the arm's domain
export ROS_LOCALHOST_ONLY=1
```

**Symptom of mismatch:** `ros2 topic pub` appears to work but nothing happens.
`ros2 node list` shows nothing even though the service is running.

---

## 🔧 Pre-Flight Checks

### 1. Check CAN Interface
```bash
# Verify CAN is UP
ip link show can0

# Should show: can0: <NOARP,UP,LOWER_UP,ECHO>

# If DOWN, bring up manually (standard Pragati config: 500kbps + auto-recovery):
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on

# Check CAN watchdog service
systemctl status can-watchdog@can0
```

### 2. Check GPIO (pigpiod)
```bash
# Verify pigpiod is running
systemctl status pigpiod

# If not running:
sudo systemctl start pigpiod

# Quick GPIO test (toggle pin 18 = compressor)
pigs w 18 1   # ON
pigs w 18 0   # OFF
```

### 3. Check Camera
```bash
# Verify camera connected
lsusb | grep Luxonis

# Test DepthAI
python3 -c "import depthai as dai; print(dai.Device.getAllAvailableDevices())"
```

### 4. Check ROS2 Environment
```bash
# On RPi -- source workspace + arm identity
source ~/pragati_ros2/install/setup.bash
source /etc/default/pragati-arm   # Sets ROS_DOMAIN_ID

ros2 node list  # Should show nodes when system is running
```

### 5. Pre-Session Baseline Capture (Before Every Test Session)

Capture motor and system health **before** starting a test session. This gives you a
reference point for diagnosing any failures that occur during the session.

**On each ARM RPi (before launching ROS2 nodes):**
```bash
# 1. Check boot_timing_capture ran at boot (OS-level baseline — automatic)
ls -la ~/pragati_ros2/logs/boot_timing_*.json | tail -1
# Should show today's date. If missing: sudo /usr/local/sbin/boot_timing_capture.sh

# 2. CAN bus health (should be ERROR-ACTIVE, 0 errors)
ip -d link show can0 | grep -E "state|bitrate"
ip -s link show can0 | grep -E "TX|RX"

# 3. Motor temperatures and voltage (all 4 arm joints, no ROS2 needed)
#    Each motor responds on CAN ID 0x140 + motor_id
#    Command 0x9A = read status (temp, voltage, error flags)
for id in 1 2 3 4; do
  echo "--- Motor $id ---"
  ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 -p node_id:=$id -p mode:=status
done
# Record: temp (should be ambient ~25-35C), voltage (~24V), error flags (should be 0x00)

# 4. Motor positions (check for mechanical drift since last session)
for id in 1 2 3 4; do
  echo "--- Motor $id ---"
  ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 -p node_id:=$id -p mode:=angle
done
# Record: multi-turn angle should match expected home position

# 5. CPU temperature (should be <60C at idle)
cat /sys/class/thermal/thermal_zone0/temp
# Divide by 1000 for Celsius
```

**On Vehicle RPi (before launching ROS2 nodes):**
```bash
# 1-2. Same boot_timing + CAN checks as above

# 3. ODrive health (drive + steering motors, no ROS2 needed)
odrive_can_tool --if can0 --nodes 3,4,5 --checks heartbeat,error,temp,bus,encoder
# All checks should PASS. Record: FET temp, bus voltage, encoder positions, error state.

# 4. Steering motor health (MG6010 on vehicle CAN)
for id in 1 2 3; do
  echo "--- Steering Motor $id ---"
  ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 -p node_id:=$id -p mode:=status
done
# Record: temp (steering motors are thermal risk — Feb peak was 73-80C)
```

**What to look for (red flags — do NOT start test if any of these):**
- Motor temperature >50C at startup (residual heat from previous run)
- CAN bus state not ERROR-ACTIVE (indicates bus problems)
- ODrive error flags non-zero (motor in error state)
- Bus voltage <22V (low battery — nominal is 24V)
- Motor position significantly different from expected home

---

## 🎮 Trigger Commands

### Trigger Start Switch (via ROS2 topic)
```bash
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "data: true"
```

### Trigger Shutdown
```bash
ros2 topic pub --once /shutdown_switch/command std_msgs/msg/Bool "data: true"
```

### Manual Detection Request
```bash
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

---

## 📊 Monitoring Commands

### Watch Joint States
```bash
ros2 topic echo /joint_states
```

### Watch Detection Results
```bash
ros2 topic echo /cotton_detection/results
```

### Check Arm Status
```bash
ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}"
```

### Monitor Topic Rates
```bash
ros2 topic hz /joint_states          # Should be ~10Hz
ros2 topic hz /cotton_detection/results
```

### List All Active Nodes
```bash
ros2 node list
```

### List All Topics
```bash
ros2 topic list
```

---

## 🔴 Emergency Commands

### Emergency Stop (Software)
```bash
ros2 topic pub --once /emergency_stop std_msgs/msg/Bool "data: true"
```

### Emergency Motor Stop Script
```bash
# Run from repo root on RPi -- stops all motors even if ROS2 is broken
~/pragati_ros2/emergency_motor_stop.sh
```

### Stop All Motors Immediately
```bash
ros2 service call /motor_control/disable_motors std_srvs/srv/Trigger "{}"
```

### Kill All ROS2 Nodes
```bash
# Stop the systemd service (cleanest)
sudo systemctl stop arm_launch.service

# Or kill everything forcefully
pkill -9 -f ros2
pkill -9 -f yanthra
pkill -9 -f cotton_detection
pkill -9 -f motor_control
```

### Hardware E-STOP
- Physical E-STOP button (if wiring fixed)
- Disconnect CAN cable as last resort

---

## 🛠️ Motor Control Commands

### Enable / Disable Motors (required before joint movement)
```bash
# Primary (matches motor_control_ros2 mg6010_controller_node)
ros2 service call /enable_motors std_srvs/srv/Trigger "{}"
ros2 service call /disable_motors std_srvs/srv/Trigger "{}"

# If your launch/namespacing remaps services under a namespace, try:
# ros2 service call /motor_control/enable_motors std_srvs/srv/Trigger "{}"
# ros2 service call /motor_control/disable_motors std_srvs/srv/Trigger "{}"
```

### Direct Joint Jog (debugging / quick trial)
These are the simplest “does the motor move?” commands.

```bash
# Publish a single position command (Float64) for an arm joint
ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "data: 0.0"
ros2 topic pub --once /joint4_position_controller/command std_msgs/msg/Float64 "data: 0.0"
ros2 topic pub --once /joint5_position_controller/command std_msgs/msg/Float64 "data: 0.0"

# Watch commands / feedback
ros2 topic echo /joint3_position_controller/command
ros2 topic echo /joint4_position_controller/command
ros2 topic echo /joint5_position_controller/command
ros2 topic echo /joint_states
```

Notes:
- Units depend on configuration (see `motor_control_ros2/config/production.yaml`).
  - `joint3` is revolute (rotations)
  - `joint4` / `joint5` are prismatic (meters)
- If commands are being published but the motor doesn’t move, first confirm motors are enabled and CAN is healthy.

### Convenience Wrapper (ROS1-style)
If you prefer a ROS1-like helper, this repo already has one:
```bash
./scripts/essential/pragati_commands.sh move_joint 3 0.0
./scripts/essential/pragati_commands.sh move_joint 4 0.0
./scripts/essential/pragati_commands.sh move_joint 5 0.0
```

### (Optional / Legacy) Service-based joint commands
Some older docs mention service-based joint commands under `/motor_control/...`.
If you see those in a deployment, use `ros2 service list | grep motor_control` to confirm what’s actually available.

---
## 📊 Understanding Log Statistics

### START_SWITCH Trigger Counts
The periodic stats log shows trigger tracking:
```
🎯 Triggers: 15 total | 12 effective | 2 coalesced | 1 during-cycle
```

| Counter | When it increments | What happens |
|---------|-------------------|--------------|
| **total** | Every START_SWITCH message received | Always counted |
| **effective** | `total - coalesced - during-cycle` | These triggers actually started picking cycles |
| **coalesced** | Trigger arrives while previous trigger still pending (flag already set) | Lost/merged - only one cycle starts |
| **during-cycle** | Trigger arrives while arm is actively moving | Ignored - arm can't stop mid-motion |

**Example scenario:**
- Trigger 1 → **effective** (starts cycle)
- Trigger 2 arrives 5ms later, flag still set → **coalesced** (lost)
- Arm starts moving...
- Trigger 3 during arm motion → **during-cycle** (ignored)
- Cycle ends
- Trigger 4 → **effective** (starts next cycle)

### Cotton Detection Stats
```
🌱 Detection: 15 requests | 14 ok | 0 stale | 1 timeout | last_age=45 ms
```

| Stat | Meaning |
|------|---------|
| **requests** | Total detection requests sent to cotton_detection node |
| **ok** | Successful detections with fresh data received |
| **stale** | Detections filtered out because data was too old |
| **timeout** | Detection requests that didn't get a response in time (200ms) |
| **last_age** | Age of the most recent detection data in milliseconds |

### OAK-D Camera Stats
```
📹 OAK-D: CSS=48.0% MSS=54.9% | DDR: 221.2/333.3 MB | CMX: 2532.0/2560.0 KB
```

| Stat | Meaning | Healthy Range |
|------|---------|---------------|
| **CSS** | Chip Shading Subsystem - Color ISP utilization | < 80% |
| **MSS** | Media Subsystem - Video/stereo processing utilization | < 80% |
| **DDR** | Double Data Rate memory - Used/Total RAM on OAK-D chip | < 300 MB |
| **CMX** | Connection Matrix - On-chip SRAM for neural network | ≤ 2560 KB |

**Warning signs:**
- CSS/MSS > 80% → Pipeline may drop frames
- DDR approaching 333 MB → Memory pressure, possible crashes
- CMX at 2560/2560 → Model using all SRAM (normal for YOLO)

### Memory Stats
```
💾 Memory: 36 MB | Status: ready
```
- **Memory**: Process RSS (Resident Set Size) in MB - actual RAM usage
- **Status**: Current arm state (`ready`, `busy`, `error`, `homing`)

Stable memory indicates no memory leaks. Expect ~35-40 MB for yanthra_move.

---
## 🚗 Vehicle Motor Commands

### Motor Names
- **Steering:** `steering_left`, `steering_right`, `steering_front`
- **Drive:** `drive_front`, `drive_left_back`, `drive_right_back`

### Position Commands (Individual Motors)
**⚠️ IMPORTANT:** Do NOT run `vehicle_complete.launch.py` when using these commands. The vehicle controller will overwrite your commands instantly. Launch ONLY `mg6010_controller.launch.py`.

```bash
# Steering motor position (rotations)
ros2 topic pub --once /steering_left_position_controller/command std_msgs/Float64 "data: 0.5"
ros2 topic pub --once /steering_right_position_controller/command std_msgs/Float64 "data: 0.5"
ros2 topic pub --once /steering_front_position_controller/command std_msgs/Float64 "data: 0.0"

# Drive motor position
ros2 topic pub --once /drive_front_position_controller/command std_msgs/Float64 "data: 10.0"
ros2 topic pub --once /drive_left_back_position_controller/command std_msgs/Float64 "data: 10.0"
ros2 topic pub --once /drive_right_back_position_controller/command std_msgs/Float64 "data: 10.0"
```

### Velocity Commands (Individual Motors)
```bash
# Drive motors at velocity (rad/s)
ros2 topic pub /drive_front_velocity_controller/command std_msgs/Float64 "data: 1.0"
ros2 topic pub /drive_left_back_velocity_controller/command std_msgs/Float64 "data: 1.0"
ros2 topic pub /drive_right_back_velocity_controller/command std_msgs/Float64 "data: 1.0"

# Stop drive motors
ros2 topic pub /drive_front_velocity_controller/command std_msgs/Float64 "data: 0.0"
ros2 topic pub /drive_left_back_velocity_controller/command std_msgs/Float64 "data: 0.0"
ros2 topic pub /drive_right_back_velocity_controller/command std_msgs/Float64 "data: 0.0"
```

### Enable/Disable Vehicle Motors
```bash
# Enable all vehicle motors
ros2 service call /enable_motors std_srvs/Trigger

# Disable all vehicle motors
ros2 service call /disable_motors std_srvs/Trigger
```

### Monitor Vehicle Motor States
```bash
ros2 topic echo /joint_states  # Shows all motor positions/velocities
```

---

## ⚠️ Degraded Mode (Motor Failure Handling)

### Skip a Failed Motor at Startup
Edit `vehicle_motors.yaml` before launching:
```yaml
# Skip a known-bad motor (prevents init failure)
skip_motors: ["drive_left_back"]  # Skip this motor
```

### Or Use Launch Override
```bash
# Skip motor via command line (no YAML edit needed)
ros2 launch motor_control_ros2 mg6010_controller.launch.py \
  skip_motors:="['drive_left_back']"
```

### Degraded Mode Behavior
- System continues with 2/3 drive motors (minimum required)
- System continues with 2/3 steering motors (minimum required)
- Log shows: `⚠️ DEGRADED MODE: X motor(s) failed, continuing with Y available`
- Commands to unavailable motors are ignored (not errors)

### Check Motor Availability
```bash
# Motor stats show unavailable motors
ros2 topic echo /joint_states --once
# Unavailable motors show position=0, velocity=0, effort=0
```

---

## 🏥 Runtime Health Monitoring (Field Bypass)

### Reset Disabled Motors (Re-enable after auto-disable)
```bash
# Re-enable ALL motors that were auto-disabled
ros2 service call /reset_motor std_srvs/srv/SetBool "{data: true}"
```

### Disable Health Monitoring (Stop Auto-Disabling)
```bash
# Turn off health monitoring completely (emergency field bypass)
ros2 param set /vehicle/vehicle_motor_control health_monitoring.enabled false
```

### Log-Only Mode (Monitor but Never Disable)
```bash
# Keep monitoring but never auto-disable motors
ros2 param set /vehicle/vehicle_motor_control health_monitoring.log_only_mode true
```

### Change Failure Threshold
```bash
# Increase threshold to allow more failures before action
ros2 param set /vehicle/vehicle_motor_control health_monitoring.consecutive_failure_threshold 10
```

### Health Monitoring Log Format
When motor failures occur, logs show:
```
MOTOR_FAILURE | motor=drive_left_back | cmd=velocity | target=1.50 | error=CAN_COMMAND_FAILED | failures=2/3 | action=FAILURE_COUNTED | func=velocity_command_callback
```
- **motor**: Which motor failed
- **cmd**: position or velocity command
- **target**: The commanded value
- **error**: Why it failed
- **failures**: Current count / threshold
- **action**: FAILURE_COUNTED, LOGGED_ONLY, or MOTOR_DISABLED
- **func**: Where in code it happened

---

## 🔌 GPIO Control (Direct)

**Source of truth:** `motor_control_ros2/include/.../gpio_control_functions.hpp` (arm),
`vehicle_control/config/constants.py` (vehicle). Arm and vehicle run on **separate RPis**.

> ⚠️ **Known issues:** yanthra_move_system.hpp has dead/stale pin defaults that disagree
> with motor_control_ros2 — ignore them. GPIO Setup Guide and TSD pin tables are outdated.
> See GAP-GPIO-001 in GAP_TRACKING.md.

### ARM RPi — Full Pin Map (BCM numbering, hardcoded in C++)

| BCM | Name | Dir | `pigs` command | Notes |
|-----|------|-----|---------------|-------|
| 2 | Shutdown Switch | IN | `pigs r 2` | Shared with I2C1 SDA |
| 3 | Start Switch | IN | `pigs r 3` | Shared with I2C1 SCL |
| 4 | Green LED | OUT | `pigs w 4 1/0` | |
| 12 | M2 Drop Enable | OUT | `pigs w 12 1/0` | Also aliased as COTTON_DROP_SERVO (not used in production) |
| 13 | EE M1 Direction | OUT | `pigs w 13 1/0` | 1=CW, 0=CCW |
| 14 | Transport Servo | OUT | `pigs w 14 <pos>` | PWM servo |
| 15 | Red LED | OUT | `pigs w 15 1/0` | |
| 17 | Camera LED | OUT | `pigs w 17 1/0` | |
| 18 | Compressor | OUT | `pigs w 18 1/0` | Solenoid valve (2s burst after L5 home) |
| 21 | EE M1 Enable | OUT | `pigs w 21 1/0` | Cytron board |
| 24 | Vacuum Motor | OUT | `pigs w 24 1/0` | |
| 20 | M2 Drop Direction | OUT | `pigs w 20 1/0` | 1=forward, 0=reverse (Cytron M2 polarity) |

### ARM RPi — Quick Test Commands
```bash
# Compressor burst (2 seconds)
pigs w 18 1 && sleep 2 && pigs w 18 0

# End effector ON (clockwise)
pigs w 13 1 && pigs w 21 1
# End effector OFF
pigs w 21 0

# Vacuum ON/OFF
pigs w 24 1   # ON
pigs w 24 0   # OFF

# Read switches
pigs r 3      # Start switch
pigs r 2      # Shutdown switch

# LEDs
pigs w 4 0    # Green LED ON  (active low)
pigs w 4 1    # Green LED OFF
pigs w 15 0   # Red LED ON (active low)
pigs w 15 1   # Red LED OFF
```

### Vehicle RPi — Pin Map (BCM numbering, from constants.py)

| BCM | Name | Dir | Notes |
|-----|------|-----|-------|
| 4 | System Reset | IN | Reboot button |
| 5 | Shutdown Switch | IN | Hold 0.5s |
| 6 | Start Switch | IN | |
| 7 | ADC Enable | OUT | SPI chip select |
| 8 | CAN Enable | OUT | CAN bus enable |
| 16 | Direction Left | IN | |
| 17 | RPi LED (Red) | OUT | |
| 20 | Auto/Manual Switch | IN | |
| 21 | Direction Right | IN | |
| 22 | Software Status (Green) | OUT | |
| 23 | Error LED | OUT | Unused |
| 24 | Fan | OUT | Unused |
| 27 | Yellow LED | OUT | |

> Note: Vehicle YAML (`production.yaml`) has partial pin overrides for switches that
> may not match constants.py — known issue, tracked for future cleanup.

---

## 📷 Camera & Detection Commands

### Start Detection Node Only
```bash
ros2 run cotton_detection_ros2 cotton_detection_node

# Or with launch file (recommended)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

### Switch Detection Model
```bash
# Available models:
# 1. yolov8v2.blob (default, 5.8M)
# 2. yolov8.blob (original, 5.8M)
# 3. best_openvino_2022.1_6shave.blob (larger, 14M)

# Tip: list installed models
ls $(ros2 pkg prefix cotton_detection_ros2)/share/cotton_detection_ros2/models

# Use yolov8.blob
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
  depthai_model_path:=$(ros2 pkg prefix cotton_detection_ros2)/share/cotton_detection_ros2/models/yolov8.blob

# Use best_openvino model
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
  depthai_model_path:=$(ros2 pkg prefix cotton_detection_ros2)/share/cotton_detection_ros2/models/best_openvino_2022.1_6shave.blob

# Check logs to confirm which model is loaded:
# Look for: 📦 Model path parameter: ...
#           ✅ Using CUSTOM model: ...
#           🎯 Initializing DepthAI with model: ...
```

### Manual Detection Request
```bash
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

### Check Camera Temperature
```bash
# Temperature is logged in detection node output
# Look for: 🌡️ Temp: XX.X°C
```

### View Camera Stream (if display available)
```bash
ros2 run rqt_image_view rqt_image_view
```

---

## 🚗 Vehicle Commands

### Start Vehicle Control
```bash
ros2 launch vehicle_control vehicle_complete.launch.py
```

### Start Vehicle Motors Only
```bash
ros2 launch motor_control_ros2 vehicle_motors.launch.py
```

### High-Level Vehicle Services
```bash
# Stop vehicle (enable motors + set velocity to 0)
ros2 service call /vehicle/vehicle_control/stop std_srvs/srv/Trigger "{}"

# Set vehicle to idle (disable all motors)
ros2 service call /vehicle/vehicle_control/idle std_srvs/srv/Trigger "{}"

# Straighten all steering wheels to 0°
ros2 service call /vehicle/vehicle_control/straighten_steering std_srvs/srv/Trigger "{}"
```

### Steering Modes
```bash
# Switch to Ackermann steering (proper 2-wheel geometry)
ros2 service call /vehicle/vehicle_control/set_ackermann_mode std_srvs/srv/SetBool "{data: true}"

# Switch back to front-only steering (default, simpler)
ros2 service call /vehicle/vehicle_control/set_ackermann_mode std_srvs/srv/SetBool "{data: false}"
```

### Pivot Mode (for tight turns)
```bash
# Activate pivot left (rotates in place)
ros2 service call /vehicle/vehicle_control/pivot_left std_srvs/srv/Trigger "{}"

# Activate pivot right
ros2 service call /vehicle/vehicle_control/pivot_right std_srvs/srv/Trigger "{}"

# Cancel pivot mode (back to normal)
ros2 service call /vehicle/vehicle_control/pivot_cancel std_srvs/srv/Trigger "{}"
```

### 🔍 Diagnostics & Debugging
```bash
# Get comprehensive system diagnostics (JSON output)
ros2 service call /vehicle/vehicle_control/diagnostics std_srvs/srv/Trigger "{}"

# Run motor quick test (small wiggle on all motors)
ros2 service call /vehicle/vehicle_control/test_motors std_srvs/srv/SetBool "{data: true}"

# Get motor status (without running test)
ros2 service call /vehicle/vehicle_control/test_motors std_srvs/srv/SetBool "{data: false}"

# Re-run startup self-test
ros2 service call /vehicle/vehicle_control/self_test std_srvs/srv/Trigger "{}"

# Enable motors via vehicle_control (with state tracking)
ros2 service call /vehicle/vehicle_control/enable_motors std_srvs/srv/SetBool "{data: true}"

# Disable motors via vehicle_control
ros2 service call /vehicle/vehicle_control/enable_motors std_srvs/srv/SetBool "{data: false}"

# Direct motor enable/disable (bypasses vehicle_control state - from motor_control_ros2)
ros2 service call /vehicle/enable_motors std_srvs/srv/Trigger "{}"
ros2 service call /vehicle/disable_motors std_srvs/srv/Trigger "{}"
```

### Monitor Detailed Status (Real-Time)
```bash
# Watch detailed JSON status (5Hz)
ros2 topic echo /vehicle/status_detailed

# Watch all commands being sent (debug)
ros2 topic echo /vehicle/command_echo
```

### Continuous Motion (cmd_vel)
```bash
# Move forward at 0.5 m/s
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.5}, angular: {z: 0.0}}"

# Turn while moving
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.5}}"

# Stop all motion
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.0}}"
```

---

## 🐛 Debug Commands

### Check CAN Traffic
```bash
candump can0
```

### Send CAN Test Message
```bash
# Don't use this with motors running - can interfere!
cansend can0 141#0200000000000000
```

### CAN Bus Debug Procedure (If Motors Not Responding)
```bash
# 1. Check CAN interface status
ip link show can0
# Should show: <NOARP,UP,LOWER_UP,ECHO>

# 2. Check CAN error stats
ip -s link show can0
# Look for TX/RX errors (should be 0)

# 3. Restart CAN if needed
sudo ip link set can0 down
sleep 1
sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on

# 4. Test CAN communication
candump can0 &
cansend can0 141#0200000000000000   # Test message to motor ID 141
# Should see response on candump

# 5. Check CAN watchdog service
systemctl status can-watchdog@can0

# 6. Restart CAN watchdog if needed
sudo systemctl restart can-watchdog@can0

# 7. Re-apply standard Pragati CAN config (500kbps + auto-recovery)
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up
```

### Check ROS2 Logs
```bash
# Real-time logs
ros2 run rqt_console rqt_console

# Or watch terminal output directly
```

### TF Tree (Transform Debug)
```bash
ros2 run tf2_tools view_frames
# Creates frames.pdf showing transform tree
```

### Check Parameters
```bash
ros2 param list /yanthra_move_system
ros2 param get /yanthra_move_system <param_name>
```

---

## 🔗 Vehicle-to-Arm Signal Chain

When you press the physical START button on the vehicle, the signal travels through
8 hops before the arm starts picking. If the arm doesn't respond, trace through
each hop in order. Every hop emits a `[SIGNAL_CHAIN]` log message.

### The 8 Hops

| Hop | Component | What Happens | Log Message to Find |
|-----|-----------|-------------|---------------------|
| 1 | **GPIO6 button** | Physical button press on vehicle RPi | `🟢 START button pressed (GPIO6)` |
| 2 | **vehicle_control_node** | Publishes `/start_switch_command` (Bool) | `[SIGNAL_CHAIN] vehicle_control_node: Published start_switch_command \| source=GPIO6 dest=/start_switch_command` |
| 3 | **vehicle_mqtt_bridge** | Subscribes `/start_switch_command`, publishes to MQTT `topic/start_switch_input_all` | `[SIGNAL_CHAIN] vehicle_mqtt_bridge: Published to MQTT \| source=/start_switch_command dest=topic/start_switch_input_all` |
| 4 | **mosquitto broker** | Routes MQTT message on vehicle RPi | Check broker is running: `systemctl status mosquitto` |
| 5 | **Network** | Ethernet between vehicle RPi and arm RPi | `ping <arm_ip>` from vehicle RPi |
| 6 | **ARM_client** | Subscribes MQTT `topic/start_switch_input_all` | `[SIGNAL_CHAIN] ARM_client: Received start_switch from MQTT \| source=topic/start_switch_input_all dest=/start_switch/command` |
| 7 | **ARM_client** | Publishes `/start_switch/command` (Bool) to ROS2 | `[SIGNAL_CHAIN] ARM_client: Published start_switch to ROS2 \| source=MQTT dest=/start_switch/command` |
| 8 | **yanthra_move** | Receives `/start_switch/command`, starts pick cycle | `[SIGNAL_CHAIN] yanthra_move: Received start_switch command \| source=/start_switch/command dest=pick_cycle` |

**How to trace:** Search the vehicle logs for hops 1-3, then search arm logs for hops 6-8.
The first hop that is missing tells you where the break is.

```bash
# On vehicle RPi -- check hops 1-3
journalctl -u vehicle_launch.service --since "5 minutes ago" | grep "SIGNAL_CHAIN"

# On arm RPi -- check hops 6-8
journalctl -u arm_launch.service --since "5 minutes ago" | grep "SIGNAL_CHAIN"
```

### MQTT Diagnostics

```bash
# Check mosquitto broker status (on vehicle RPi)
systemctl status mosquitto

# How many MQTT clients connected to broker?
sudo mosquitto_sub -t '$SYS/broker/clients/connected' -C 1 -W 3
# Expected: 1 (vehicle_mqtt_bridge) + 1 per connected arm

# Check if arm is publishing (wait up to 60s for heartbeat)
mosquitto_sub -t 'topic/ArmStatus_arm1' -C 1 -W 60 -v
# Should show: topic/ArmStatus_arm1 ready

# See ALL MQTT traffic (useful for debugging)
mosquitto_sub -t 'topic/#' -W 30 -v

# Check TCP connections to MQTT broker
ss -tn | grep :1883
# Should show ESTAB connections from each arm IP

# Clear stale retained message
mosquitto_pub -t 'topic/ArmStatus_arm1' -r -n

# Manual publish test (verify broker accepts messages)
mosquitto_pub -t topic/mqtt_test -m test

# Check ARM_client MQTT connectivity (in arm logs, look for address source)
# ARM_client logs: "MQTT broker address: <IP> (source: launch_arg|env|default)"
journalctl -u arm_launch.service | grep "MQTT broker address"

# Check ARM_client health (on arm RPi)
tail -5 $(ls -t ~/pragati_ros2/logs/arm_client_*.log | head -1)
# Should show "Health: mqtt=connected status=ready svc_ok" every 10s

# Check vehicle bridge health (on vehicle RPi)
tail -5 $(ls -t ~/pragati_ros2/logs/vehicle_mqtt_bridge_*.log | head -1)
# Should show "arm1 last status = ready"
```

### Failure Point Checklist

Ordered by probability. Check from top to bottom:

| # | Failure Point | Check Command |
|---|--------------|---------------|
| 1 | **vehicle_mqtt_bridge not running** | `ps aux \| grep vehicle_mqtt_bridge` — also check vehicle launch logs for path resolution errors |
| 2 | **MQTT broker not running** | `systemctl status mosquitto` — should be `active (running)` |
| 3 | **ARM_client wrong MQTT address** | `journalctl -u arm_launch.service \| grep "MQTT broker address"` — verify IP matches vehicle RPi |
| 4 | **ARM_client MQTT disconnected** | `tail -5 $(ls -t ~/pragati_ros2/logs/arm_client_*.log \| head -1)` — look for `mqtt=connected` in Health line. If `DISCONNECTED`, check network |
| 5 | **Stale retained offline on broker** | `mosquitto_sub -t 'topic/ArmStatus_arm1' -C 1 -W 5 -v` — if shows `offline`, wait 30s for heartbeat or clear with `mosquitto_pub -t 'topic/ArmStatus_arm1' -r -n` |
| 6 | **Network connectivity** | `ping <vehicle_ip>` from arm RPi, `ping <arm_ip>` from vehicle RPi |
| 7 | **Start switch timeout too short** | Launch with `continuous_operation:=true` to wait indefinitely for start switch |
| 8 | **ARM_client crashed and not restarted** | `journalctl -u arm_launch.service -n 100 \| grep -i "exit\|restart\|crash"` |
| 9 | **yanthra_move not ready for start switch** | `ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}"` — must be `ready` |
| 10 | **GPIO wiring issue** | `pigs r 6` on vehicle RPi — returns 1 when button pressed, 0 when released |

### MQTT Connectivity Test

```bash
# Run end-to-end MQTT connectivity test from dev workstation
./sync.sh --test-mqtt

# What it tests:
#   - Connects to mosquitto broker on vehicle RPi
#   - Publishes test message to each arm's MQTT topic
#   - Verifies each arm's ARM_client receives and responds
#   - Prints PASS/FAIL table for each arm

# Reading results:
#   PASS = full round-trip from vehicle broker to arm and back
#   FAIL = break somewhere in the MQTT path (check Failure Point Checklist above)

# Prerequisites:
#   - mosquitto-clients must be installed on all RPis
#     (sync.sh --provision installs this automatically)
#   - Vehicle RPi mosquitto broker must be running
#   - All arm RPis must be network-reachable from vehicle RPi
```

---

## 📦 Log Collection & Analysis

### Collect Logs from RPi
```bash
# Default: collect today's logs from a single host
./sync.sh --collect-logs --ip 192.168.1.107

# All hosts (vehicle + arms, reads config.env)
./sync.sh --collect-logs

# Incremental: reuse latest session, skip already-collected files
./sync.sh --collect-logs --continue

# All logs (no date filter):
./sync.sh --collect-logs --ip 192.168.1.107 --date all

# Specific date:
./sync.sh --collect-logs --ip 192.168.1.107 --date 2026-02-25

# Yesterday only:
./sync.sh --collect-logs --ip 192.168.1.107 --date yesterday

# Dry run (preview rsync commands without executing):
./sync.sh --collect-logs --ip 192.168.1.107 --dry-run

# Logs collected include: journalctl, dmesg, ROS logs, system stats
# Output structure: collected_logs/<timestamp>/<target>/
```

### Analyze Logs
```bash
# Field summary (quick overview of a trial session)
python3 -m scripts.log_analyzer collected_logs/2026-02-23_12-21/ --field-summary

# Full analysis
python3 -m scripts.log_analyzer collected_logs/2026-02-23_12-21/
```

### Live Log Monitoring on RPi
```bash
# Watch arm service logs in real time
journalctl -u arm_launch.service -f

# Watch last N lines
journalctl -u arm_launch.service -n 500 --no-pager

# Filter by time range
journalctl -u arm_launch.service --since "10 minutes ago"

# Check all pragati-related services
systemctl status arm_launch.service pigpiod can-watchdog@can0 field-monitor.service
```

---

## 🔄 System Restart Procedures

### Restart ARM System
```bash
# Via systemd (recommended)
sudo systemctl restart arm_launch.service

# Or manually
pkill -f yanthra_move
sleep 2
source ~/pragati_ros2/install/setup.bash
source /etc/default/pragati-arm
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true
```

### Restart CAN Interface
```bash
sudo ip link set can0 down
sleep 1
sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on
```

### Full System Restart
```bash
# Stop everything
sudo systemctl stop arm_launch.service
sudo systemctl restart pigpiod
sudo ip link set can0 down
sleep 2
sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on

# Restart service
sudo systemctl start arm_launch.service

# Or restart manually
source ~/pragati_ros2/install/setup.bash
source /etc/default/pragati-arm
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true
```

---

## 📋 Launch File Parameters

### pragati_complete.launch.py
```bash
# Launch arguments supported by pragati_complete.launch.py:
output_log:=<screen|log>               # Default: screen
use_sim_time:=<true|false>             # Default: false
use_simulation:=<true|false>           # Default: false
continuous_operation:=<true|false>     # Default: true

enable_arm_client:=<true|false>        # MQTT bridge (default: true)
enable_cotton_detection:=<true|false>  # Starts cotton_detection_cpp.launch.py (default: true)
use_preloaded_centroids:=<true|false>  # Only used when enable_cotton_detection:=false (default: false)
mqtt_address:=<IP>                     # Default: 10.42.0.10
arm_id:=<arm1|arm2|...>               # Default: arm1

can_interface:=<name>                  # Default: can0
can_bitrate:=<int>                     # Default: 500000

offline_mode:=<true|false>             # Default: false
offline_image_path:=<path>             # Default: ''
use_dynamic_ee_prestart:=<true|false>  # Dynamic end-effector pre-start (default: true)

urdf_path:=<path>                      # Default: robot_description/urdf/MG6010_FLU.urdf
log_directory:=<path>                  # Default: ~/.ros/logs

# NOTE:
# - pragati_complete.launch.py includes cotton_detection_cpp.launch.py when enable_cotton_detection:=true.
# - ROS2 launch arguments are global across included launch files.
#   So you *can* pass cotton detection args (e.g., depthai_model_path, confidence_threshold, detection_mode,
#   use_depthai, debug_output, ...) directly to pragati_complete.launch.py.
# - If enable_cotton_detection:=false, those args have no effect.
```

### cotton_detection_cpp.launch.py
```bash
# All available parameters:
depthai_model_path:=<path>             # Model blob path (default: yolov8v2.blob)
confidence_threshold:=<0.0-1.0>        # Detection confidence (default: 0.5)
use_depthai:=<true|false>              # Enable DepthAI (default: true)
simulation_mode:=<true|false>          # Simulation mode (default: false)
debug_output:=<true|false>             # Debug images (default: false)
detection_mode:=<mode>                 # Detection mode (default: depthai_direct)
camera_topic:=<topic>                  # Input topic (default: /camera/image_raw)
depthai_num_classes:=<int>             # Number of detection classes (default: 1)
log_level:=<debug|info|warn|error>     # Log level (default: info)
auto_pause:=<true|false>              # Auto-pause detection (default: false)
```

### Example Configurations
```bash
# Field trial (with MQTT, continuous)
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true \
  mqtt_address:=192.168.1.100

# Testing (no MQTT, single cycle)
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  enable_arm_client:=false \
  continuous_operation:=false

# With custom detection model (single command)
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true \
  depthai_model_path:=$(ros2 pkg prefix cotton_detection_ros2)/share/cotton_detection_ros2/models/best_openvino_2022.1_6shave.blob

# Alternative (advanced): if you want to restart only cotton detection without restarting the full system
# 1) Start main system but do NOT auto-launch cotton detection
#    ros2 launch yanthra_move pragati_complete.launch.py enable_cotton_detection:=false ...
# 2) Launch cotton detection separately with the desired model
#    ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py depthai_model_path:=...
```

---

## 📝 Parameter Naming Convention

**Important:** ROS2 uses different naming for launch arguments vs config files:

### Launch Arguments (use underscore)
```bash
# Command line uses underscores:
depthai_model_path:=/path/to/model.blob
```

### Config File Parameters (use dot notation)
```yaml
# YAML config uses nested structure:
depthai:
  model_path: ""
```

### How They Map
- Launch argument `depthai_model_path` → ROS2 parameter `depthai.model_path`
- Launch argument `confidence_threshold` → ROS2 parameter `depthai.confidence_threshold`
- This is standard ROS2 convention (underscore for CLI, dot for namespacing)

---

## 🌡️ Thermal Protocol

**Warning:** Joint3 overheats after ~10-15 minutes of continuous operation.

### Recommended Cycle
- **Run:** 10 minutes max
- **Cool:** 5 minutes minimum
- **Monitor:** Watch for motor temp warnings in logs

### If Overheating
1. Stop operation immediately
2. Disable motors: `ros2 service call /motor_control/disable_motors std_srvs/srv/Trigger "{}"`
3. Wait 10 minutes for cooldown
4. Resume operation

---

## 📁 Important File Locations

### On RPi
```
Config Files:
  ~/pragati_ros2/src/yanthra_move/config/production.yaml
  ~/pragati_ros2/src/motor_control_ros2/config/mg6010_config.yaml
  ~/pragati_ros2/src/cotton_detection_ros2/config/cotton_detection_cpp.yaml

Arm Identity:
  /etc/default/pragati-arm          # ARM_ID, ROS_DOMAIN_ID, MQTT_ADDRESS

Service Files:
  /etc/systemd/system/arm_launch.service
  /etc/systemd/system/pigpiod.service
  /etc/systemd/system/can-watchdog@.service
  /etc/systemd/system/field-monitor.service

Logs:
  journalctl -u arm_launch.service  # Primary log source
  ~/.ros/log/
```

### On Dev Workstation
```
Config Files:
  src/yanthra_move/config/production.yaml
  src/motor_control_ros2/config/mg6010_config.yaml
  src/cotton_detection_ros2/config/cotton_detection_cpp.yaml

Launch Files:
  src/yanthra_move/launch/
  src/motor_control_ros2/launch/

Cross-Compiled Artifacts:
  install_rpi/                      # Ready for deploy via sync.sh

Collected Logs:
  collected_logs/<timestamp>/       # From sync.sh --collect-logs
```

---

## 📞 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Motors not moving | Check CAN: `ip link show can0`, ensure UP |
| `ros2 topic pub` does nothing | Domain ID mismatch — `source /etc/default/pragati-arm` or `export ROS_DOMAIN_ID=N` |
| `ros2 node list` empty but service running | Domain ID mismatch — see above |
| J3/J4 service calls timeout | Ensure `motor_control_msgs` package is installed (not `motor_control_ros2/srv/`) |
| Camera not detected | Check USB: `lsusb \| grep Luxonis` |
| GPIO not working | Check pigpiod: `systemctl status pigpiod` |
| CAN bus errors | `sudo systemctl restart can-watchdog@can0` |
| Detection timeout | Check camera connection, restart detection node |
| Service won't start | `journalctl -u arm_launch.service -n 50 --no-pager` |
| Clock way off on RPi | Re-provision: `./sync.sh --provision --ip <IP>` or re-deploy: `./sync.sh --deploy-cross --ip <IP>` (both sync clock if drift > 5s). Manual: `ssh -t ubuntu@<IP> 'sudo date -u -s "$(date -u)"'` |
| Cross-compile fails (sysroot) | `ln -s /media/rpi-sysroot ~/rpi-sysroot` or set `RPI_SYSROOT` env var |
| Zombie cc1plus after build | `pkill -9 cc1plus` — WSL cross-compile can leave these |
| Vehicle shows arm `offline` | Wait 30s for heartbeat. Check arm MQTT: `tail -5 $(ls -t ~/pragati_ros2/logs/arm_client_*.log \| head -1)` — should show `Health: mqtt=connected`. If disconnected, check network and MQTT_ADDRESS in `/etc/default/pragati-arm` |
| ARM_client log not growing | Process frozen — `sudo systemctl restart arm_launch.service` |
| Stale retained MQTT `offline` | On vehicle: `mosquitto_pub -t 'topic/ArmStatus_arm1' -r -n` clears retained message. Vehicle bridge also clears on restart. |
| ARM_client 6%+ CPU but silent | Normal if healthy (service calls + sleep loop). Check log for `Health:` lines every 10s to confirm alive. |

---

## 🆕 Adding a New RPi to the Fleet

### Prerequisites

- Ubuntu 24.04.4 Server ARM64 flashed to SD card
- RPi connected to the Windows hotspot (192.168.137.x subnet)
- Note the IP address (check router or `arp -a`)

### Step 1: Initial OS-Level Setup (on the RPi)

```bash
# SSH into the new RPi
ssh ubuntu@<NEW_IP>

# Clone the repo and run the setup script
git clone <repo-url> ~/pragati_ros2
cd ~/pragati_ros2
./setup_raspberry_pi.sh

# The setup script handles: apt packages, pip packages, ROS2 Jazzy,
# CAN dtoverlay (SPI-gated — only added if CAN HAT detected),
# systemd services, hostname, timezone, NTP, SSH config, etc.
```

### Step 2: Register in Fleet Config

Add the new IP to `config.env` in the repo root:

```bash
# Example: adding arm3
ARM_3_IP=192.168.137.xxx
```

### Step 3: Provision + Set Identity

```bash
# From dev workstation — provision and assign arm identity
./sync.sh --ip <NEW_IP> --provision --role arm --arm-id arm3 \
  --mqtt-address 192.168.137.203 --save

# This applies: OS fixes, systemd services, config.txt management,
# arm identity (/etc/default/pragati-arm), clock sync
```

### Step 4: Deploy Code

```bash
# Cross-compile and deploy
./build.sh rpi
./sync.sh --ip <NEW_IP> --deploy-cross
```

### Step 5: Verify + Drift Check

```bash
# Read-only verification (runs automatically after sync, or standalone)
./sync.sh --ip <NEW_IP> --verify

# Capture boot timing snapshot (on the RPi)
ssh ubuntu@<NEW_IP> "sudo /usr/local/sbin/boot_timing_capture.sh"

# Pull the capture to dev machine
rsync -e "/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe" -avz \
  ubuntu@<NEW_IP>:/home/ubuntu/pragati_ros2/logs/boot_timing_*.json \
  collected_logs/<session>/arm_3/

# Run fleet drift report (include ALL RPis for cross-fleet comparison)
python3 scripts/diagnostics/fleet_drift_report.py \
  --input-dir collected_logs/<session> \
  --requirements requirements.txt --verbose

# Fix anything the report flags (it prints copy-pasteable commands)
```

---

## 🔍 Fleet Drift Detection & Remediation

Two complementary tools detect drift at different levels:

| Tool | Scope | When to Use |
|------|-------|-------------|
| `sync.sh --verify` | Single RPi, real-time | After every sync/provision — checks services, config.txt, OS fixes |
| `fleet_drift_report.py` | Whole fleet, offline | Periodically or before field trials — N-way cross-RPi comparison |

### Quick Drift Check (Single RPi)

```bash
# Read-only audit of one RPi
./sync.sh --ip <IP> --verify

# Output shows [OK], [WARN], [MISMATCH] for each category
# MISMATCH = needs --provision to fix
# WARN = advisory (e.g., OS version behind)
```

### Full Fleet Drift Report

```bash
# 1. Collect boot_timing captures from all RPis
#    (reboot triggers automatic capture via boot_timing.timer,
#     or run manually on each RPi):
ssh ubuntu@<IP> "sudo /usr/local/sbin/boot_timing_capture.sh"

# 2. Pull captures to dev machine
#    (--collect-logs pulls field trial logs; boot_timing needs manual pull)
for role_ip in arm_1:192.168.137.12 arm_2:192.168.137.238 vehicle:192.168.137.203; do
  role="${role_ip%%:*}"; ip="${role_ip##*:}"
  mkdir -p collected_logs/$(date +%Y-%m-%d)/$role
  rsync -e "/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe" -avz \
    ubuntu@$ip:/home/ubuntu/pragati_ros2/logs/boot_timing_*.json \
    collected_logs/$(date +%Y-%m-%d)/$role/
done

# 3. Run drift report
python3 scripts/diagnostics/fleet_drift_report.py \
  --input-dir collected_logs/$(date +%Y-%m-%d) \
  --requirements requirements.txt --verbose

# 4. Save report to file (also prints to stdout)
python3 scripts/diagnostics/fleet_drift_report.py \
  --input-dir collected_logs/$(date +%Y-%m-%d) \
  --requirements requirements.txt \
  --output drift_report_$(date +%Y-%m-%d).txt
```

### What the Drift Report Checks

| Section | Severity | What It Flags |
|---------|----------|---------------|
| OS Version | WARN | RPi behind fleet's newest point release |
| Apt Packages | WARN/INFO | Missing expected packages, extra packages not on all RPis |
| Pip Packages | WARN/INFO | Version constraint violations, inter-RPi version differences |
| CAN Dtoverlay | ERROR | Wrong oscillator/params, dtoverlay on RPi without CAN HAT |
| Enabled Services | WARN/INFO | Expected services missing, services differ across fleet |

### Common Remediation Commands

```bash
# Fix provisioning issues (services, config.txt, OS fixes)
./sync.sh --ip <IP> --provision

# Missing apt packages
ssh ubuntu@<IP> "sudo apt install <pkg1> <pkg2>"

# Pip version drift
ssh ubuntu@<IP> "pip3 install --break-system-packages <pkg>==<version>"

# OS point release upgrade (manual — requires physical access for recovery)
ssh ubuntu@<IP> "sudo apt update && sudo apt full-upgrade"

# Stale kernel cleanup (reclaim disk space)
ssh ubuntu@<IP> "sudo apt remove linux-image-6.8.0-XXXX-raspi"

# After fixes: re-capture and re-run drift report to confirm clean fleet
```

### Known Accepted Deviations

- **arm1 CAN oscillator=12000000**: arm1 has a temporary 12 MHz dev HAT (not
  the production 8 MHz HAT). The drift report flags this as ERROR — it is
  expected until the production HAT is swapped in.

---

## 🔗 Related Docs

- Full quick reference: `docs/guides/QUICK_REFERENCE.md`
- Hardware testing: `docs/guides/hardware/HARDWARE_TESTING_QUICKSTART.md`
- GPIO guide: `docs/guides/GPIO_SETUP_GUIDE.md`
- CAN guide: `docs/guides/CAN_BUS_SETUP_GUIDE.md`
- Fleet drift report: `scripts/diagnostics/README.md`
- Field trial plan: `docs/project-notes/FEBRUARY_FIELD_TRIAL_PLAN_2026.md`
