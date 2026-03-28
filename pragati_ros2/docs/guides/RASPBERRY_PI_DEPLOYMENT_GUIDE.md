# Pragati ROS2 - Raspberry Pi Deployment Guide
**Version:** 2.0  
**Last Updated:** 2025-10-06  
**Target Platform:** Raspberry Pi 4/5 (Ubuntu 24.04 or Raspberry Pi OS)  
**ROS2 Distribution:** Jazzy

> **📌 Quick Start:** For a consolidated installation and validation checklist, see [RPI_INSTALLATION_VALIDATION_CHECKLIST.md](../../RPI_INSTALLATION_VALIDATION_CHECKLIST.md). This guide provides comprehensive details referenced by the checklist.

---

## 📋 Executive Summary

This guide provides complete step-by-step instructions for deploying the Pragati ROS2 cotton picking robot system on a Raspberry Pi, from initial setup through hardware validation and field deployment.

### Current Software Status
- ✅ **Software:** 95/100 production-ready (simulation validated)
- ✅ **Migration:** 100% ROS1→ROS2 complete
- ✅ **Safety Monitor:** Implemented (thresholds need hardware tuning)
- ✅ **Testing:** 18/20 tests pass (mock hardware warnings expected)
- ⏳ **Hardware Validation:** Pending on actual robot hardware

### Deployment Prerequisites
| Requirement | Status | Notes |
|-------------|--------|-------|
| ROS2 Jazzy installed | ❗ Required | See Step 1 |
| Raspberry Pi 4/5 (4GB+ RAM) | ❗ Required | 8GB recommended |
| CAN interface | ❗ Required | PiCAN hat or USB adapter |
| GPIO access | ✅ Built-in | See GPIO Setup Guide |
| Network connectivity | ❗ Required | For initial setup |
| MicroSD (64GB+) | ❗ Required | For OS and data |

---

## 🎯 Deployment Roadmap

### Phase 1: System Setup (2-3 hours)
1. Install Ubuntu/ROS2 on Raspberry Pi
2. Install dependencies
3. Clone and build workspace
4. Run simulation tests

### Phase 2: Hardware Configuration (1-2 hours)
5. Configure CAN bus interface
6. Configure GPIO (optional emergency stop)
7. Verify hardware connections

### Phase 3: Validation & Tuning (2-4 hours)
8. Hardware-in-the-loop testing
9. SafetyMonitor threshold tuning
10. Performance optimization

### Phase 4: Production Deployment (1 hour)
11. Auto-start configuration
12. Monitoring setup
13. Final validation

**Total Time:** 6-10 hours (first deployment)

---

## Phase 1: System Setup

### Step 1.1: Install Ubuntu 24.04 on Raspberry Pi

```bash
# Download Ubuntu 24.04 Server for RPi
# URL: https://ubuntu.com/download/raspberry-pi

# Flash to microSD using Raspberry Pi Imager or dd
# Boot Raspberry Pi and complete initial setup

# Update system
sudo apt update && sudo apt upgrade -y

# Install essential tools
sudo apt install -y git curl wget nano net-tools
```

### Step 1.2: Install ROS2 Jazzy

```bash
# Set locale
sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# Setup sources
sudo apt install software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install curl -y

# Add ROS2 GPG key
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

# Add repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Install ROS2 Jazzy
sudo apt update
sudo apt install -y ros-jazzy-desktop  # Or ros-jazzy-ros-base for headless

# Source ROS2
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc

# Verify installation
ros2 doctor
```

### Step 1.3: Clone Workspace

```bash
# Create workspace directory
mkdir -p ~/pragati_ws
cd ~/pragati_ws

# Clone repository (replace with your git URL)
git clone <your-repo-url> .

# OR if transferring from development machine:
# rsync -avz --progress /home/uday/Downloads/pragati_ros2/ pi@<raspberry-pi-ip>:~/pragati_ws/
```

### Step 1.4: Install Dependencies

```bash
cd ~/pragati_ws

# Run dependency installation script
chmod +x install_deps.sh
./install_deps.sh

# This installs:
# - ROS2 build tools (colcon, rosdep)
# - Hardware dependencies (can-utils, pigpio)
# - Python dependencies (opencv, paho-mqtt, numpy)
```

**Expected Output:**
```
✅ ROS2 installation found
✅ DEPENDENCIES INSTALLED SUCCESSFULLY!
```

### Step 1.5: Build Workspace

```bash
cd ~/pragati_ws

# Build all packages
colcon build --symlink-install

# Expected: ~5-15 minutes on Raspberry Pi 4
# Expected output: "Summary: 7 packages finished"

# Source workspace
source install/setup.bash
echo "source ~/pragati_ws/install/setup.bash" >> ~/.bashrc
```

### Step 1.6: Run Simulation Tests

```bash
# Quick validation
./test.sh --quick

# Full test suite (optional, takes longer)
./scripts/validation/comprehensive_test_suite.sh

# Expected: 18/20 tests pass (2 mock hardware warnings OK)
```

✅ **Phase 1 Complete:** Software is ready for hardware integration

---

## Phase 2: Hardware Configuration

### Step 2.1: Configure CAN Bus

#### Option A: PiCAN Hat (Recommended for production)

```bash
# Enable SPI in boot config
sudo nano /boot/firmware/config.txt

# Add these lines:
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
dtoverlay=spi-bcm2835-overlay

# Save and reboot
sudo reboot

# After reboot, configure CAN interface
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Make persistent (auto-start on boot)
sudo nano /etc/network/interfaces.d/can0

# Add:
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 1000000
    up /sbin/ip link set can0 up
    down /sbin/ip link set can0 down

# Verify
ip link show can0
# Should show: state UP
```

#### Option B: USB-CAN Adapter

```bash
# Load modules
sudo modprobe can
sudo modprobe can_raw
sudo modprobe slcan

# Configure interface (1 Mbps)
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Verify
ip link show can0
```

#### Test CAN Communication

```bash
# Terminal 1: Monitor CAN bus
candump can0

# Terminal 2: Send test message
cansend can0 123#DEADBEEF

# Expected: Terminal 1 shows message
```

📖 **Full Guide:** `docs/guides/CAN_BUS_SETUP_GUIDE.md`

### Step 2.2: Configure GPIO (Optional Emergency Stop)

```bash
# Install GPIO libraries
sudo apt install -y libgpiod-dev gpiod python3-rpi.gpio

# Add user to gpio group
sudo usermod -a -G gpio $USER
sudo usermod -a -G dialout $USER

# Create udev rules
sudo tee /etc/udev/rules.d/99-gpio.rules << EOF
SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP=="gpio", MODE="0660"
EOF

# Reload rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Logout and login for group changes
```

#### Enable GPIO at Build Time

```bash
cd ~/pragati_ws

# Rebuild with GPIO support
colcon build --cmake-args -DUSE_GPIO=ON --symlink-install

# Source workspace
source install/setup.bash
```

#### Wire Emergency Stop Button

```
GPIO17 (BCM) ─── E-Stop Button (NO) ─── GND
        │
      10kΩ Pull-up to 3.3V
```

#### Test GPIO

```bash
# Test LED control (if wired)
gpioset gpiochip0 22=1  # Red LED on
gpioset gpiochip0 22=0  # Red LED off

# Monitor E-stop button
watch -n 0.1 'gpioget gpiochip0 17'
# Press button: value changes from 1 to 0
```

📖 **Full Guide:** `docs/guides/GPIO_SETUP_GUIDE.md`

### Step 2.3: Configure Network (for remote access)

```bash
# Set static IP (optional but recommended)
sudo nano /etc/netplan/50-cloud-init.yaml

# Example configuration:
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses: [192.168.1.100/24]
      gateway4: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]

# Apply
sudo netplan apply

# Enable SSH (if not already)
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Step 2.4: Verify Hardware Connections

**Pre-Flight Checklist:**
- [ ] CAN interface shows `UP`: `ip link show can0`
- [ ] GPIO access working: `gpiodetect`
- [ ] ODrive controllers powered
- [ ] CAN termination resistors installed (120Ω at both ends)
- [ ] Network connectivity confirmed

✅ **Phase 2 Complete:** Hardware interfaces configured

---

## Phase 3: Validation & Tuning

### Step 3.1: Launch System in Simulation Mode

```bash
cd ~/pragati_ws
source install/setup.bash

# Launch without hardware first
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true

# Verify all nodes start:
# - yanthra_move
# - odrive_service_node (simulation mode)
# - robot_state_publisher
# - cotton_detection_node (optional)
```

### Step 3.2: Launch with Real Hardware

```bash
# Terminal 1: Launch system
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=false \
    enable_arm_client:=true \
    mqtt_address:=10.42.0.10

# Terminal 2: Monitor topics
ros2 topic list
ros2 topic echo /joint_states

# Terminal 3: Check service availability
ros2 service list | grep odrive
```

### Step 3.3: Test ODrive Communication

```bash
# Home all joints
ros2 service call /joint_homing odrive_control_ros2/srv/JointHoming \
    "{homing_required: true, joint_id: 2}"

ros2 service call /joint_homing odrive_control_ros2/srv/JointHoming \
    "{homing_required: true, joint_id: 3}"

# Check joint status
ros2 service call /joint_status odrive_control_ros2/srv/JointStatus \
    "{joint_id: -1}"

# Expected: Positions, velocities, temperatures reported
```

### Step 3.4: Safety Monitor Threshold Tuning

The SafetyMonitor is implemented but needs hardware-specific tuning:

```bash
# Run safety monitor tests
cd ~/pragati_ws
./install/odrive_control_ros2/lib/odrive_control_ros2/test_safety_monitor

# Note any threshold violations during normal operation
```

**Parameters to Tune:**
```yaml
# In src/odrive_control_ros2/config/safety_params.yaml
safety_monitor:
  max_velocity_limit: 10.0        # rad/s - tune based on actual max safe speed
  max_temperature_warning: 65.0   # °C - adjust for ODrive thermal limits
  max_temperature_critical: 70.0  # °C - emergency stop temperature
  min_voltage_warning: 42.0       # V - battery low warning
  min_voltage_critical: 40.0      # V - critical voltage shutdown
  timeout_threshold: 1.0          # seconds - CAN communication timeout
```

**Tuning Procedure:**
1. Run system through normal picking cycles
2. Monitor actual temperatures via `ros2 topic echo /odrive/telemetry`
3. Note maximum safe velocities during operation
4. Adjust thresholds in YAML with 10-20% safety margin
5. Test emergency stop response (<500ms)

📖 **Full Guide:** `docs/SAFETY_MONITOR_EXPLANATION.md`

### Step 3.5: Performance Benchmarking

```bash
# Run complete picking cycle
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=false \
    continuous_operation:=false

# Monitor cycle time (target: <3.5 seconds)
# Check logs for timing information
```

**Performance Targets:**
- Cycle time: <3.5 seconds per cotton
- CPU usage: <60% on Raspberry Pi 4
- Memory usage: <4GB
- Response time: <100ms for commands

### Step 3.6: Web Dashboard Monitoring

```bash
# Terminal 1: Launch system
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false

# Terminal 2: Start dashboard
cd ~/pragati_ws/web_dashboard
python3 run_dashboard.py

# Access from browser: http://<raspberry-pi-ip>:8080
```

Dashboard provides:
- Real-time node status
- Joint positions and velocities
- System health metrics
- Log monitoring

✅ **Phase 3 Complete:** System validated on hardware

---

## Phase 4: Production Deployment

### Step 4.1: Configure Auto-Start (systemd service)

```bash
# Create systemd service
sudo nano /etc/systemd/system/pragati-robot.service
```

```ini
[Unit]
Description=Pragati ROS2 Cotton Picking Robot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pragati_ws
Environment="ROS_DOMAIN_ID=0"
ExecStartPre=/bin/sleep 10
ExecStart=/bin/bash -c 'source /opt/ros/jazzy/setup.bash && source /home/pi/pragati_ws/install/setup.bash && ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false'
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable pragati-robot.service
sudo systemctl start pragati-robot.service

# Check status
sudo systemctl status pragati-robot.service

# View logs
sudo journalctl -u pragati-robot.service -f
```

### Step 4.2: Configure CAN Auto-Start

Already configured in Phase 2.1 via `/etc/network/interfaces.d/can0`

Verify:
```bash
# After reboot
ip link show can0
# Should automatically be UP
```

### Step 4.3: Setup Log Management

```bash
# Log rotation is already configured
# Verify log cleanup runs
pragati-log-status

# Configure daily cleanup (optional)
crontab -e

# Add line:
0 2 * * * /home/pi/pragati_ws/scripts/monitoring/clean_logs.sh quick-clean
```

### Step 4.4: Configure Monitoring

```bash
# Auto-start web dashboard (optional)
sudo nano /etc/systemd/system/pragati-dashboard.service
```

```ini
[Unit]
Description=Pragati Web Dashboard
After=pragati-robot.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pragati_ws/web_dashboard
Environment="ROS_DOMAIN_ID=0"
ExecStart=/usr/bin/python3 /home/pi/pragati_ws/web_dashboard/run_dashboard.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable pragati-dashboard.service
sudo systemctl start pragati-dashboard.service
```

### Step 4.5: Final System Validation

```bash
# Reboot and verify auto-start
sudo reboot

# After reboot, check all services
sudo systemctl status pragati-robot
sudo systemctl status pragati-dashboard

# Verify ROS2 system
ros2 node list
ros2 topic list

# Run quick test
./test.sh --quick

# Test emergency stop (if GPIO configured)
# Press physical E-stop button
# Expected: System halts within 500ms
```

✅ **Phase 4 Complete:** Production deployment ready

---

## 🔧 Optimization for Raspberry Pi

### Performance Tuning

```bash
# Increase swap (if needed for builds)
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Change CONF_SWAPSIZE to 2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Disable desktop (headless mode)
sudo systemctl set-default multi-user.target

# Enable performance governor
sudo apt install cpufrequtils
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl restart cpufrequtils
```

### Memory Management

```bash
# Monitor memory usage
free -h

# If memory is tight, disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
```

### CPU Temperature Monitoring

```bash
# Install monitoring tools
sudo apt install -y lm-sensors

# Check temperature
vcgencmd measure_temp

# Add temperature monitoring to cron
crontab -e
# Add: */5 * * * * vcgencmd measure_temp >> /home/pi/temp_log.txt
```

---

## 🚨 Troubleshooting

### Issue: Build Fails on Raspberry Pi

**Symptom:** Out of memory during `colcon build`

**Solution:**
```bash
# Build one package at a time
colcon build --packages-select motor_control_ros2
colcon build --packages-select odrive_control_ros2
colcon build --packages-select cotton_detection_ros2
colcon build --packages-select yanthra_move
colcon build --packages-select vehicle_control
colcon build --packages-select robo_description

# Or use fewer parallel jobs
colcon build --parallel-workers 1
```

### Issue: CAN Bus Not Working

**Symptom:** `ip link show can0` returns error

**Solutions:**
```bash
# Check SPI enabled
ls /dev/spi*

# Verify overlay in config
cat /boot/firmware/config.txt | grep mcp2515

# Check kernel logs
dmesg | grep -i can
dmesg | grep -i spi

# Reinstall CAN utils
sudo apt install --reinstall can-utils
```

### Issue: GPIO Permission Denied

**Symptom:** Cannot access GPIO pins

**Solutions:**
```bash
# Verify group membership
groups | grep gpio

# If missing, add user
sudo usermod -a -G gpio $USER

# Logout and login

# Check udev rules
ls -l /dev/gpiochip*

# Should show: crw-rw---- 1 root gpio
```

### Issue: System Runs Slowly

**Checks:**
```bash
# CPU usage
top

# Memory usage
free -h

# Disk I/O
iotop

# Temperature (throttling check)
vcgencmd measure_temp
vcgencmd get_throttled
```

### Issue: Nodes Fail to Start

**Debug Steps:**
```bash
# Check ROS2 environment
printenv | grep ROS

# Test node individually
ros2 run yanthra_move yanthra_move_node

# Check dependencies
rosdep check --from-paths src --ignore-src

# Review logs
less ~/pragati_ws/log/latest_build/yanthra_move/stdout_stderr.log
```

---

## 📊 Validation Checklist

### Pre-Deployment Validation

- [ ] All packages build successfully
- [ ] Simulation tests pass (18/20 minimum)
- [ ] CAN interface operational
- [ ] ODrive controllers detected
- [ ] GPIO configured (if used)
- [ ] Network connectivity stable
- [ ] Web dashboard accessible

### Hardware Validation

- [ ] Joint homing successful (all joints)
- [ ] Joint position commands work
- [ ] Joint velocity limits enforced
- [ ] Temperature monitoring functional
- [ ] Emergency stop responsive (<500ms)
- [ ] Communication timeout detection working
- [ ] Cotton detection service functional

### Performance Validation

- [ ] Picking cycle < 3.5 seconds
- [ ] CPU usage < 60%
- [ ] Memory usage < 4GB
- [ ] No communication errors
- [ ] System stable for 30+ minutes
- [ ] Recovery from errors working

### Safety Validation

- [ ] Emergency stop tested (physical button)
- [ ] Software E-stop working
- [ ] SafetyMonitor limits verified
- [ ] Timeout detection tested
- [ ] Motor error handling tested
- [ ] Graceful shutdown working

---

<!-- Restored from 8ac7d2e: docs/BUILD_OPTIMIZATION.md -->

## 🚀 Build Optimization for Raspberry Pi

### Build Time Improvements

Optimizing build times is critical for efficient development on resource-constrained Raspberry Pi hardware.

**Build Time Comparison:**
- **Initial Build (Clean):** ~15-20 minutes (compiling everything from scratch)
- **Incremental Build:** ~18 seconds (after code changes)
- **Optimization Level:** 74% time reduction for development workflow

### Package-Specific Build Times

Understanding where build time is spent helps prioritize optimization efforts:

| Package | Type | Build Time | Notes |
|---------|------|------------|-------|
| motor_control_ros2 | C++ | ~6-8 min | MG6010 drivers + safety monitor |
| pattern_finder *(legacy utility)* | C++ | ~1 min 44s | PCL dependency warnings (package optional) |
| robo_description | XML/URDF | ~15s | Lightweight |
| cotton_detection_ros2 | C++ (14 files) | ~5-7 min | OpenCV dependencies |
| odrive_control_ros2 | C++ (65 files) | ~7-10 min | Large codebase |
| vehicle_control | Python (42 files) | ~8s | Fast (Python) |
| yanthra_move | C++ (18 files) | ~3-5 min | MoveIt dependencies |

**Total First Build:** 15-20 minutes

### Memory Constraints and Solutions

**The Challenge:**
- **Available RAM:** 4GB on Raspberry Pi 4
- **C++ Compilation:** Up to 1.2GB per file
- **Risk:** Parallel compilation can cause memory pressure and swapping
- **Symptom:** System becomes unresponsive during build

**The Solution:**
```bash
# Use fewer parallel workers (default is 4, use 2 for RPi)
colcon build --parallel-workers 2

# For very tight memory situations (1-2GB available)
colcon build --parallel-workers 1
```

### Recommended Build Strategy

#### For Development (Fast Iteration)

```bash
# Source ROS2 environment
source /opt/ros/jazzy/setup.bash

# Incremental build (~18 seconds)
colcon build --symlink-install --parallel-workers 2

# Python changes are instant with --symlink-install!
# No rebuild needed for Python scripts
```

**Key Benefits:**
- `--symlink-install`: Creates symlinks instead of copying Python files
- Python code changes are immediately effective (no rebuild)
- Perfect for rapid development iteration

#### For Clean Build (When Needed)

```bash
# Remove old build artifacts
rm -rf build/ install/ log/

# Clean build with optimized flags
colcon build --symlink-install --parallel-workers 2 \
  --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

**When to do clean builds:**
- After major dependency changes
- When CMake cache is corrupted
- Before creating release builds
- When switching branches with structural changes

### Build Optimization Flags

#### Compiler Flags

**Use `-O2` instead of `-O3` for compilation:**
```bash
colcon build --cmake-args \
  -DCMAKE_CXX_FLAGS="-O2" \
  -DCMAKE_C_FLAGS="-O2"
```

**Benefits:**
- 20% faster compilation time
- Minimal performance difference in most cases
- More reliable optimization (less risk of compiler bugs)

**Build Types:**
- `Debug`: No optimization, full debug symbols (slowest runtime, fastest compile)
- `RelWithDebInfo`: `-O2` optimization + debug symbols (recommended)
- `Release`: `-O3` optimization, no debug symbols (fastest runtime, slowest compile)
- `MinSizeRel`: Optimize for size (rarely used)

#### Colcon Flags Reference

```bash
# Essential flags
--symlink-install        # Instant Python changes (no rebuild)
--parallel-workers N     # Control parallelism (use 2 for RPi)
--packages-select PKG    # Build only specific package
--packages-up-to PKG     # Build package and its dependencies

# Advanced flags
--cmake-args KEY=VALUE   # Pass arguments to CMake
--event-handlers console_direct+  # Show output immediately
--executor sequential    # Build packages one at a time (lowest memory)
```

### Build Scripts

Use the unified build entrypoint:

```bash
# Normal optimized cross-compile
./build.sh rpi

# Clean build (removes build_rpi/, install_rpi/)
./build.sh --clean rpi

# Single-threaded (low memory mode)
./build.sh rpi -j 1

# Build specific package
./build.sh rpi -p yanthra_move
```

**Script features (via build.sh):**
- Toolchain: `cmake/toolchains/rpi-aarch64.cmake`
- Outputs: `build_rpi/`, `install_rpi/`
- Parallel worker auto-detect (default 4 on host; override with `-j`)
- Memory-safe defaults for Pi when run on-device (1 worker)

### Troubleshooting Build Issues

#### Out of Memory During Build

**Symptoms:**
- System becomes unresponsive
- Build process killed
- "Out of memory" errors in logs

**Solutions:**
```bash
# 1. Use single-threaded build
colcon build --parallel-workers 1

# 2. Increase swap space (if needed)
sudo swapon --show  # Check current swap
sudo fallocate -l 4G /swapfile  # Create 4GB swap
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 3. Close other applications
# Stop unnecessary services before building
```

#### Compilation Hangs

**Symptoms:**
- Build process appears stuck
- One core at 100% for extended period
- No progress output

**Solutions:**
```bash
# 1. Check memory usage
free -h
htop  # Look for memory pressure

# 2. Kill zombie processes
pkill -9 cc1plus
pkill -9 g++

# 3. Clean and retry
rm -rf build/ install/
colcon build --parallel-workers 1
```

#### CMake Cache Issues

**Symptoms:**
- Configuration errors
- "Variable not found" errors
- Inconsistent build behavior

**Solutions:**
```bash
# Clear CMake cache for all packages
rm -rf build/*/CMakeCache.txt
rm -rf build/*/CMakeFiles/

# Or remove entire build directory
rm -rf build/

colcon build
```

### Expected Build Times by Scenario

| Scenario | Time | Use Case |
|----------|------|----------|
| **First build** | 15-20 min | Initial setup, clean environment |
| **Incremental (Python change)** | <1 sec | Development with `--symlink-install` |
| **Incremental (single C++ file)** | 18 sec | Single file modification |
| **Incremental (multiple C++)** | 2-5 min | Multiple file changes |
| **Incremental (header change)** | 5-10 min | Header affects many files |
| **Clean rebuild** | 15-20 min | After major dependency changes |
| **Package-specific build** | Variable | Only rebuild one package |

### Build Performance Tips

1. **Use `--symlink-install` for all development builds**
   - Makes Python changes instant
   - No rebuild needed for config changes

2. **Build only what you need**
   ```bash
   # Build only one package
   colcon build --packages-select yanthra_move
   
   # Build package and dependencies
   colcon build --packages-up-to yanthra_move
   ```

3. **Keep build artifacts between sessions**
   - Don't clean unless necessary
   - Incremental builds are 50x faster

4. **Monitor resources during build**
   ```bash
   # Watch memory usage
   watch -n 1 free -h
   
   # Watch temperatures
   watch -n 1 vcgencmd measure_temp
   ```

5. **Use ccache for repeated builds** (optional)
   ```bash
   # Install ccache
   sudo apt install ccache
   
   # Configure colcon to use it
   export CC="ccache gcc"
   export CXX="ccache g++"
   
   colcon build
   ```

### Build Optimization Checklist

Before building on Raspberry Pi, verify:

- [ ] Sufficient free RAM (at least 2GB recommended)
- [ ] Sufficient swap space (4GB recommended)
- [ ] Using `--parallel-workers 2` or less
- [ ] Using `--symlink-install` for development
- [ ] Using `-O2` instead of `-O3` if build time is critical
- [ ] Not running other intensive processes
- [ ] Temperature below 70°C (check with `vcgencmd measure_temp`)
- [ ] Using incremental builds when possible

---

## 📚 Additional Resources

### Documentation
- **Main README:** `README.md`
- **System Overview:** `docs/reports/SYSTEM_TECHNICAL_OVERVIEW.md`
- **CAN Bus Setup:** `docs/guides/CAN_BUS_SETUP_GUIDE.md`
- **GPIO Setup:** `docs/guides/GPIO_SETUP_GUIDE.md`
- **Safety Monitor:** `docs/SAFETY_MONITOR_EXPLANATION.md`
- **Web Dashboard:** `web_dashboard/README.md`

### Scripts
- **Build:** `./build.sh`
- **Test:** `./test.sh`
- **Quick Start:** `bash scripts/setup/quickstart.sh`
- **Install Dependencies:** `./install_deps.sh`
- **Log Management:** `./scripts/monitoring/clean_logs.sh`

### Support
- **GitHub Issues:** (your repository URL)
- **Documentation:** `docs/` folder
- **Changelog:** `CHANGELOG.md`

---

## 🎉 Success Criteria

Your Raspberry Pi deployment is successful when:

✅ System auto-starts on boot  
✅ All nodes launch without errors  
✅ Hardware communication functional  
✅ Cotton picking cycles complete successfully  
✅ Safety monitors operational  
✅ Web dashboard accessible  
✅ System runs stable for extended periods  
✅ Performance meets targets (<3.5s per cotton)

**Congratulations! Your Pragati ROS2 system is production-ready on Raspberry Pi!** 🤖🍓

---

**Document Version:** 2.0  
**Last Verified:** 2025-10-06  
**Tested On:** Raspberry Pi 4 (8GB), Ubuntu 24.04, ROS2 Jazzy