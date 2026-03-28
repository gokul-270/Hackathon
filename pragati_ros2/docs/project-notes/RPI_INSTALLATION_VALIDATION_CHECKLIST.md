# Pragati ROS2 Raspberry Pi Installation and Validation Checklist

**Audience:** Engineers setting up a fresh Raspberry Pi 4/5 for the Pragati ROS2 cotton picking robot  
**Last Updated:** 2025-11-04  
**Target Platform:** Raspberry Pi 4 (4-8GB) or Raspberry Pi 5  
**Operating System:** Ubuntu 24.04 LTS (Noble Numbat)  
**ROS Distribution:** ROS 2 Jazzy  
**Estimated Time:** 6-10 hours (first-time setup)

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Script Execution Order](#script-execution-order)
- [1. Pre-Installation Checklist](#1-pre-installation-checklist)
- [2. Initial System Setup](#2-initial-system-setup)
- [3. ROS2 Installation](#3-ros2-installation)
- [4. Workspace Deployment](#4-workspace-deployment)
- [5. Hardware Interface Configuration](#5-hardware-interface-configuration)
- [6. Power Management Configuration](#6-power-management-configuration)
- [7. System Validation](#7-system-validation)
- [8. Build and Test](#8-build-and-test)
- [9. Production Deployment](#9-production-deployment)
- [10. Final Validation Checklist](#10-final-validation-checklist)
- [11. Quick Reference](#11-quick-reference)
- [12. Known Issues and Solutions](#12-known-issues-and-solutions)

---

## Executive Summary

### Purpose

This checklist consolidates all installation, configuration, and validation steps required to set up a new Raspberry Pi for the Pragati ROS2 cotton-picking robot system. It references existing scripts and guides to ensure consistency and maintainability.

### System Overview

- **Target Hardware:** Raspberry Pi 4 (4-8GB RAM) or Raspberry Pi 5
- **Operating System:** Ubuntu 24.04 LTS Server for Raspberry Pi
- **ROS Distribution:** ROS 2 Jazzy
- **Motor Controllers:** MG6010-i6 via CAN bus (500 kbps bitrate)
- **Vision:** OAK-D Lite camera with DepthAI
- **Networking:** WiFi/Ethernet with power management tuning for stability

### Success Criteria

- ✅ All validation scripts pass without errors
- ✅ CAN interface operational at 500 kbps (for MG6010 motors)
- ✅ OAK-D Lite camera detected and functional
- ✅ ROS2 workspace builds successfully
- ✅ Power management configured for field operation stability
- ✅ System performance meets benchmarks (see [RPI_BENCHMARK_GUIDE.md](RPI_BENCHMARK_GUIDE.md))

### Related Documentation

- **Comprehensive Guide:** [docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md](docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md)
- **Current Deployment Status:** [RPI_DEPLOYMENT_STATUS.md](RPI_DEPLOYMENT_STATUS.md)
- **Power Management Fixes:** [docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md](docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md)
- **Benchmarking:** [RPI_BENCHMARK_GUIDE.md](RPI_BENCHMARK_GUIDE.md)

---

## Script Execution Order

<!-- Consolidation Note: This execution order ensures dependencies are met and configurations are applied correctly -->

This section provides the recommended sequence for running setup and validation scripts:

| Step | Script | Purpose | When to Run |
|------|--------|---------|-------------|
| 1 | [scripts/setup/install_deps.sh](scripts/setup/install_deps.sh) | Install ROS2 dependencies | After ROS2 install |
| 2 | [scripts/deployment/rpi_verify.sh](scripts/deployment/rpi_verify.sh) | Verify base system | After OS + ROS install |
| 3 | [sync.sh](../../sync.sh) | Deploy from dev machine | Optional (remote deployment) |
| 4 | [scripts/deployment/rpi_setup_and_test.sh](scripts/deployment/rpi_setup_and_test.sh) | Configure and test CAN | After SPI/CAN overlays |
| 5 | [scripts/deployment/rpi_setup_depthai.sh](scripts/deployment/rpi_setup_depthai.sh) | Setup OAK-D camera | After USB configuration |
| 6 | [scripts/deployment/validate_rpi_deployment.sh](scripts/deployment/validate_rpi_deployment.sh) | Full system validation | After workspace build |
| 7 | [scripts/maintenance/rpi/verify_rpi_power_management.sh](scripts/maintenance/rpi/verify_rpi_power_management.sh) | Check power settings | Anytime |
| 8 | [scripts/maintenance/rpi/fix_rpi_power_management.sh](scripts/maintenance/rpi/fix_rpi_power_management.sh) | Apply power fixes | If verify fails |
| 9 | [scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh](scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh) | SSH stability | After power fixes |

---

## 1. Pre-Installation Checklist

<!-- Source: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md Phase 1 prerequisites -->

### Hardware Requirements

- [ ] **Raspberry Pi:** RPi 4 (4-8GB RAM) or RPi 5
- [ ] **Storage:** 32-64GB U3 microSD card or NVMe (if supported)
- [ ] **Power Supply:** 5V/3A+ official or compatible PSU
- [ ] **CAN Interface:** PiCAN HAT or USB-CAN adapter
- [ ] **Camera:** OAK-D Lite (USB 3.0)
- [ ] **Cooling:** Heatsink + fan (recommended for sustained operation)
- [ ] **Networking:** WiFi adapter or Ethernet cable

### Network Requirements

- [ ] 2.4/5 GHz WiFi credentials or wired Ethernet
- [ ] Internet connectivity for package installation
- [ ] (Optional) Static IP configuration details
- [ ] SSH access enabled

### Software Downloads

- [ ] [Ubuntu 24.04 Server for Raspberry Pi](https://ubuntu.com/download/raspberry-pi)
- [ ] [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or similar tool
- [ ] SSH client (built-in on Linux/Mac, PuTTY for Windows)

### Pre-Setup Verification

Check that you have the correct Ubuntu image for your Raspberry Pi model:

```bash
# After download, verify image (optional but recommended)
sha256sum ubuntu-24.04-preinstalled-server-arm64+raspi.img.xz
```

---

## 2. Initial System Setup

<!-- Source: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md Section 1.1-1.2 -->

### 2.1 Flash Operating System

1. **Flash Ubuntu 24.04 to microSD/NVMe:**
   ```bash
   # Using Raspberry Pi Imager (recommended):
   # - Select "Ubuntu Server 24.04 LTS (64-bit)" for Raspberry Pi
   # - Configure hostname, user, WiFi, SSH in advanced options
   # - Flash to microSD card
   ```

2. **First Boot:**
   - Insert microSD into Raspberry Pi
   - Connect power and wait for boot (2-3 minutes)
   - Connect via SSH: `ssh ubuntu@<raspberry-pi-ip>`

### 2.2 System Update and Configuration

```bash
# Update system packages
sudo apt update && sudo apt full-upgrade -y

# Install essential tools
sudo apt install -y git curl wget nano net-tools build-essential

# Set timezone (adjust as needed)
sudo timedatectl set-timezone America/New_York

# Reboot to apply updates
sudo reboot
```

**Wait 30-60 seconds, then reconnect via SSH.**

### 2.3 User Permissions

Add your user to required groups for hardware access:

```bash
# Add to hardware access groups
sudo usermod -aG dialout,video,plugdev,spi,gpio,i2c $USER

# Verify group membership (logout/login required for changes to take effect)
groups

# Logout and login for changes to take effect
exit
# SSH back in
ssh ubuntu@<raspberry-pi-ip>
```

**Verification:**
```bash
groups | grep -E 'dialout|video|plugdev|spi|gpio'
# Expected: All listed groups should appear
```

### 2.4 Enable SPI for CAN Interface

Edit boot configuration:

```bash
sudo nano /boot/firmware/config.txt
```

Add the following lines at the end (adjust for your CAN HAT):

```ini
# Enable SPI
dtparam=spi=on

# MCP2515 CAN controller (adjust oscillator frequency to match your HAT)
# Common values: 8000000 (8 MHz), 16000000 (16 MHz)
dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
dtoverlay=spi-bcm2835-overlay
```

**Save and reboot:**
```bash
sudo reboot
```

**Verification after reboot:**
```bash
# Check SPI devices
ls /dev/spi*
# Expected: /dev/spidev0.0  /dev/spidev0.1

# Check boot messages for CAN
dmesg | grep -i 'mcp2515\|can'
# Expected: Lines showing MCP2515 initialization

# Check CAN interface exists
ip link show can0
# Expected: Interface can0 listed (may be DOWN, that's OK for now)
```

---

## 3. ROS2 Installation

<!-- Source: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md Section 1.2 -->

### 3.1 Install ROS 2 Jazzy

```bash
# Set locale
sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# Add ROS 2 repository
sudo apt install software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install curl -y

# Add ROS 2 GPG key
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

# Add repository to sources
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Install ROS 2 Jazzy
sudo apt update
sudo apt install -y ros-jazzy-ros-base  # Headless version (recommended for RPi)
# OR for desktop tools (requires more disk space):
# sudo apt install -y ros-jazzy-desktop

# Install development tools
sudo apt install -y python3-colcon-common-extensions python3-rosdep python3-vcstool

# Initialize rosdep
sudo rosdep init
rosdep update
```

### 3.2 Configure ROS 2 Environment

```bash
# Source ROS 2 in .bashrc for persistence
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

**Verification:**
```bash
# Check ROS 2 installation
ros2 --version
# Expected: ros2 cli version: jazzy

# Verify environment variables
printenv | grep -E 'ROS_DISTRO|ROS_VERSION|AMENT'
# Expected output:
# ROS_DISTRO=jazzy
# ROS_VERSION=2
# AMENT_PREFIX_PATH=/opt/ros/jazzy
```

---

## 4. Workspace Deployment

<!-- Source: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md Section 1.3-1.4 and sync.sh -->

### 4.1 Option A: Deploy from Development Machine (Recommended)

**On your development PC:**

```bash
# Configure sync target (first time only)
cd ~/pragati_ros2
./sync.sh --ip <raspberry-pi-ip> --user ubuntu --save

# Deploy to RPi
./sync.sh --build

# Or for faster cross-compiled deployment:
./build.sh rpi           # Cross-compile on your PC
./sync.sh --deploy-cross # Deploy pre-built binaries
```

**What this does:**
- Syncs source code (excluding build artifacts)
- Syncs configuration files
- Syncs runtime scripts
- Optionally builds on RPi or deploys cross-compiled binaries

**Expected Output:**
```
✓ SSH connection successful
✓ Source code synced
✓ Configuration and runtime files synced
✓ Build triggered on RPi (if --build used)
✓ RPi preparation complete
```

**See:** [sync.sh](../../sync.sh) for all deployment options. Run `./sync.sh --help` for details.

### 4.2 Option B: Manual Clone on Raspberry Pi

**On the Raspberry Pi:**

```bash
# Create workspace directory
mkdir -p ~/pragati_ros2
cd ~/pragati_ros2

# Clone repository
git clone <repository-url> .

# Or transfer from development machine
# rsync -avz --exclude='build' --exclude='install' --exclude='log' \
#   /home/uday/Downloads/pragati_ros2/ ubuntu@<rpi-ip>:~/pragati_ros2/
```

### 4.3 Install Dependencies

```bash
cd ~/pragati_ros2

# Run dependency installation script
bash scripts/setup/install_deps.sh
```

**Expected Output:**
```
✅ ROS2 installation found
✅ DEPENDENCIES INSTALLED SUCCESSFULLY!
```

**See:** [scripts/setup/install_deps.sh](scripts/setup/install_deps.sh) for details on what's installed.

**Verification:**
```bash
# Check key dependencies
python3 -c "import cv2; print('OpenCV:', cv2.__version__)"
python3 -c "import can; print('python-can installed')"
command -v colcon && echo "colcon installed"
```

---

## 5. Hardware Interface Configuration

<!-- Source: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md Phase 2 and scripts/deployment/rpi_setup_and_test.sh -->

### 5.1 CAN Bus Configuration

#### Configure CAN Interface

```bash
# Bring down interface (if up)
sudo ip link set can0 down 2>/dev/null || true

# Configure CAN bitrate (must match your motor configs; current repo defaults to 500 kbps)
sudo ip link set can0 type can bitrate 500000

# Bring interface up
sudo ip link set can0 up
```

**Verification:**
```bash
# Check interface status
ip -details link show can0
# Expected: 
# can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT
#     can state ERROR-ACTIVE (berr-counter tx 0 rx 0) restart-ms 0 
#     bitrate 500000 sample-point 0.875

# Monitor CAN traffic (Ctrl+C to exit)
candump can0
# Expected: CAN frames if motors are powered and transmitting
```

#### Make CAN Configuration Persistent

Create network configuration:

```bash
sudo nano /etc/network/interfaces.d/can0
```

Add:
```bash
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 500000
    up /sbin/ip link set can0 up
    down /sbin/ip link set can0 down
```

### 5.2 Run CAN Setup and Motor Test Script

```bash
cd ~/pragati_ros2
bash scripts/deployment/rpi_setup_and_test.sh
```

**What this script does:**
- Verifies CAN interface and oscillator frequency
- Checks/updates boot configuration if needed
- Configures CAN interface
- Optionally tests motor communication

**Expected Output:**
```
✓ can0 interface exists
✓ Clock is correctly set to 8 MHz
✓ CAN interface configured
✓ can-utils available
```

**See:** [scripts/deployment/rpi_setup_and_test.sh](scripts/deployment/rpi_setup_and_test.sh)

**⚠️ Important:** CAN bitrate must match across the bus (configs + OS interface). Current configs in this repo default to **500 kbps**.

### 5.3 GPIO Configuration (Optional - for Emergency Stop)

```bash
# Install GPIO libraries
sudo apt install -y libgpiod-dev gpiod python3-rpi.gpio

# Create udev rules for GPIO access
sudo tee /etc/udev/rules.d/99-gpio.rules << EOF
SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP=="gpio", MODE="0660"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

**Verification:**
```bash
# List GPIO chips
gpiodetect
# Expected: gpiochip0 [pinctrl-bcm2711] (58 lines)

# Test GPIO (example: read GPIO17)
gpioget gpiochip0 17
```

**See:** [docs/guides/GPIO_SETUP_GUIDE.md](docs/guides/GPIO_SETUP_GUIDE.md) for detailed GPIO configuration.

### 5.4 Camera (OAK-D Lite) Setup

```bash
cd ~/pragati_ros2
bash scripts/deployment/rpi_setup_depthai.sh
```

**What this script does:**
- Installs ROS 2 DepthAI packages
- Rebuilds `cotton_detection_ros2` with DepthAI support
- Verifies DepthAI libraries
- Tests hardware detection

**Expected Output:**
```
✅ DepthAI packages installed
✅ Build successful
✅ DepthAI manager library found
```

**See:** [scripts/deployment/rpi_setup_depthai.sh](scripts/deployment/rpi_setup_depthai.sh)

**Verification:**
```bash
# Check USB device (OAK-D Lite has vendor ID 03e7)
lsusb | grep 03e7
# Expected: Bus 001 Device 00X: ID 03e7:XXXX Intel Movidius MyriadX

# Test DepthAI Python API
python3 -c "import depthai as dai; print('DepthAI version:', dai.__version__)"
# Expected: DepthAI version: 2.X.X
```

---

## 6. Power Management Configuration

<!-- Source: docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md and scripts/maintenance/rpi/* -->

**⚠️ Critical for Field Operation:** Power management settings cause WiFi/USB dropouts. These fixes are required for stable operation.

### 6.1 Verify Current Power Management Settings

```bash
cd ~/pragati_ros2
bash scripts/maintenance/rpi/verify_rpi_power_management.sh
```

**Expected Issues (on fresh install):**
```
[1] WiFi Power Save Status: on ✗ FAIL
[2] NetworkManager WiFi Power Save Config: not set ✗ FAIL
[3] USB Autosuspend: 2 ✗ FAIL
[4] USB Device Power Control: some devices 'auto' ⚠ WARNING
```

**See:** [scripts/maintenance/rpi/verify_rpi_power_management.sh](scripts/maintenance/rpi/verify_rpi_power_management.sh)

### 6.2 Apply Power Management Fixes

```bash
# Fix WiFi and USB power management
sudo bash scripts/maintenance/rpi/fix_rpi_power_management.sh

# Fix SSH keepalive for connection stability
sudo bash scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh
```

**Expected Output:**
```
Step 1/5: NetworkManager WiFi power save... ✓
Step 2/5: Kernel parameter... ✓
Step 3/5: USB autosuspend... ✓
Step 4/5: USB devices power control... ✓
Step 5/5: rc.local... ✓
```

**See:**
- [scripts/maintenance/rpi/fix_rpi_power_management.sh](scripts/maintenance/rpi/fix_rpi_power_management.sh)
- [scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh](scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh)

### 6.3 Reboot and Re-verify

```bash
sudo reboot
```

**After reboot:**
```bash
cd ~/pragati_ros2
bash scripts/maintenance/rpi/verify_rpi_power_management.sh
```

**Expected (all checks should pass):**
```
[1] WiFi Power Save Status: off ✓ PASS
[2] NetworkManager WiFi Power Save Config: wifi.powersave = 2 ✓ PASS
[3] USB Autosuspend: -1 ✓ PASS
[4] USB Device Power Control: All devices 'on' ✓ PASS
[5] Kernel Parameter: present ✓ PASS
[6] rc.local Configuration: configured ✓ PASS
[7] Network Connectivity Test: reachable ✓ PASS

Results: 7 passed, 0 failed
All checks passed! Power management is correctly configured.
```

**⚠️ Warning:** Disabling power saving increases power consumption but is necessary for field operation stability.

**📝 Note:** Re-run verification after kernel/firmware updates.

---

## 7. System Validation

<!-- Source: scripts/deployment/rpi_verify.sh and scripts/deployment/validate_rpi_deployment.sh -->

### 7.1 Pre-Deployment Verification

Run basic system checks before building workspace:

```bash
cd ~/pragati_ros2
bash scripts/deployment/rpi_verify.sh
```

**What this checks:**
- ROS 2 installation and environment
- Workspace structure
- System dependencies (colcon, CAN tools, Python packages)
- Hardware interfaces (CAN, SPI, GPIO)
- System resources (RAM, disk space, temperature)
- User permissions

**Expected Output:**
```
[1] ROS2 Installation
  ✓ ROS2 Jazzy installed
  ✓ ROS2 environment sourced

[2] Workspace Structure
  ✓ Workspace directory exists
  ✓ Source directory exists
  ✓ Found 7 packages

[5] Hardware Interfaces
  ✓ CAN interface (can0) exists
  ✓ CAN interface is UP
  ✓ SPI interface available

All checks passed! Ready to build and run.
```

**See:** [scripts/deployment/rpi_verify.sh](scripts/deployment/rpi_verify.sh)

### 7.2 Post-Deployment Validation

After building the workspace, run full validation:

```bash
cd ~/pragati_ros2
bash scripts/deployment/validate_rpi_deployment.sh | tee logs/validation_$(date +%F_%H%M).log
```

**What this validates:**
- System requirements (RAM, disk, OS version)
- ROS 2 installation (jazzy, colcon, rosdep)
- Hardware interfaces (CAN, GPIO, SPI)
- Python dependencies (OpenCV, numpy, can, pigpio)
- Workspace status (built packages, executables)
- Network configuration
- Performance metrics (temperature, throttling)

**Expected Output:**
```
Phase 1: System Requirements
✅ Running on Raspberry Pi
✅ Sufficient RAM: 7850MB (>=4GB)
✅ Sufficient disk space: 45GB available

Phase 7: Performance Check
✅ CPU temperature: 42.5°C (normal)
✅ No CPU throttling detected

Validation Summary
✅ Passed:  28 checks
⚠️  Warnings: 2 checks
❌ Failed:  0 checks

🎉 PERFECT! System is fully ready for deployment!
```

**See:** [scripts/deployment/validate_rpi_deployment.sh](scripts/deployment/validate_rpi_deployment.sh)

**⚠️ If validation fails:**
- Review error messages
- Check corresponding section in this guide
- Review logs: `cat logs/validation_*.log`

---

## 8. Build and Test

<!-- Source: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md Phase 1.5-1.6 and build_rpi.sh -->

### 8.1 Build Workspace

```bash
cd ~/pragati_ros2

# Source ROS 2
source /opt/ros/jazzy/setup.bash

# Build (build.sh auto-detects RPi and uses safe defaults)
bash build.sh

# OR manual build with memory-friendly settings
# colcon build --symlink-install --parallel-workers 2 \
#   --cmake-args -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS="-O2"
```

**Expected Build Time:**
- Clean build: 15-20 minutes (Raspberry Pi 4)
- Incremental: ~18 seconds (after code changes)

**Expected Output:**
```
🔧 Building workspace...
✅ BUILD SUCCESSFUL!
   Build time: 1024s

📦 Built packages:
   • cotton_detection_ros2
   • motor_control_ros2
   • vehicle_control
   • yanthra_move
   • robo_description
   • pattern_finder
   • common_utils
```

**See:** [build.sh](build.sh) for build options.

**💡 Build Tips:**
- Use `--parallel-workers 2` to avoid out-of-memory errors
- Use `--symlink-install` for instant Python changes (no rebuild needed)
- See [RPI_BENCHMARK_GUIDE.md](RPI_BENCHMARK_GUIDE.md) for build optimization

### 8.2 Source Workspace

```bash
source install/setup.bash

# Make persistent
echo "source ~/pragati_ros2/install/setup.bash" >> ~/.bashrc
```

**Verification:**
```bash
# Check packages are available
ros2 pkg list | grep -E 'cotton|motor|yanthra|vehicle'
# Expected: Lists all project packages

# Check executables
ros2 pkg executables cotton_detection_ros2
ros2 pkg executables motor_control_ros2
```

### 8.3 Run Tests

#### Quick Validation

```bash
cd ~/pragati_ros2
./test.sh --quick
```

#### Motor/CAN Test

```bash
cd ~/pragati_ros2
bash scripts/deployment/rpi_setup_and_test.sh

# Follow prompts to test motor communication
```

#### Camera Test

With OAK-D Lite connected:

```bash
# Test DepthAI node
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

**Expected:** Node starts without errors, camera detected

#### Unit Tests (Optional)

```bash
cd ~/pragati_ros2
colcon test --packages-select motor_control_ros2 cotton_detection_ros2
colcon test-result --verbose
```

### 8.4 Performance Benchmarking

**Quick System Check:**

```bash
# CPU usage during idle
top -bn1 | grep "Cpu(s)"

# Memory usage
free -h

# Temperature
vcgencmd measure_temp

# Check for throttling (0x0 = good)
vcgencmd get_throttled
```

**Full Benchmarks:**

See [RPI_BENCHMARK_GUIDE.md](RPI_BENCHMARK_GUIDE.md) for:
- Build time benchmarks
- Runtime performance targets
- Memory usage monitoring
- Thermal testing

**Target Metrics:**
- CPU usage: <60% during operation
- Memory usage: <3.5GB (with 4GB RAM)
- Temperature: <70°C sustained
- Detection latency: ~130ms (DepthAI on Myriad X VPU)
- Motor response: <5ms

---

## 9. Production Deployment

<!-- Source: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md Phase 4 -->

### 9.1 Systemd Service Configuration (Optional)

Create a systemd service for auto-start:

```bash
sudo nano /etc/systemd/system/pragati-robot.service
```

**Service file content:**

```ini
[Unit]
Description=Pragati ROS2 Cotton Picking Robot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/pragati_ros2
Environment="ROS_DOMAIN_ID=0"
ExecStartPre=/bin/sleep 10
ExecStart=/bin/bash -c 'source /opt/ros/jazzy/setup.bash && source /home/ubuntu/pragati_ros2/install/setup.bash && ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false'
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

**Enable and start service:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable pragati-robot.service
sudo systemctl start pragati-robot.service

# Check status
sudo systemctl status pragati-robot.service

# View logs
sudo journalctl -u pragati-robot.service -f
```

### 9.2 Log Management

**Log locations:**
- ROS 2 logs: `~/.ros/log/` (if not redirected)
- System logs: `journalctl`
- Application logs: `~/pragati_ros2/log/`

**View recent logs:**
```bash
# System service logs
sudo journalctl -u pragati-robot -n 100 --no-pager

# ROS 2 logs
ls -lht ~/.ros/log/
cat ~/.ros/log/latest/pragati_robot-*.log
```

### 9.3 Monitoring and Maintenance

**System health checks:**

```bash
# Check services
systemctl status pragati-robot

# Monitor resources
htop

# Temperature monitoring
watch vcgencmd measure_temp

# CAN bus traffic
candump can0
```

**Emergency stop:**

```bash
# Stop service
sudo systemctl stop pragati-robot

# Emergency motor stop (if system has emergency_motor_stop.sh)
bash ~/pragati_ros2/emergency_motor_stop.sh
```

---

## 10. Final Validation Checklist

<!-- Comprehensive checklist linking to all relevant sections -->

Use this checklist to verify complete system setup:

### System Prerequisites
- [ ] [Raspberry Pi 4/5 with sufficient RAM (4GB+)](#1-pre-installation-checklist)
- [ ] [Ubuntu 24.04 LTS installed and updated](#2-initial-system-setup)
- [ ] [User added to required groups (dialout, gpio, spi, etc.)](#23-user-permissions)
- [ ] [SPI enabled for CAN interface](#24-enable-spi-for-can-interface)

### Software Installation
- [ ] [ROS 2 Jazzy installed](#3-ros2-installation)
- [ ] [ROS 2 environment sourced in .bashrc](#32-configure-ros-2-environment)
- [ ] [Dependencies installed (colcon, rosdep, can-utils)](#43-install-dependencies)
- [ ] [Workspace deployed to RPi](#4-workspace-deployment)
- [ ] [Workspace builds successfully](#81-build-workspace)

### Hardware Configuration
- [ ] [CAN interface configured at 500 kbps](#51-can-bus-configuration)
- [ ] [CAN interface persistent across reboots](#51-can-bus-configuration)
- [ ] [GPIO configured (if using E-stop)](#53-gpio-configuration-optional---for-emergency-stop)
- [ ] [OAK-D Lite camera detected](#54-camera-oak-d-lite-setup)
- [ ] [DepthAI libraries installed](#54-camera-oak-d-lite-setup)

### Power Management
- [ ] [Power management verified (all checks pass)](#61-verify-current-power-management-settings)
- [ ] [WiFi power save disabled](#62-apply-power-management-fixes)
- [ ] [USB autosuspend disabled](#62-apply-power-management-fixes)
- [ ] [SSH keepalive configured](#62-apply-power-management-fixes)
- [ ] [Settings persist after reboot](#63-reboot-and-re-verify)

### System Validation
- [ ] [Pre-deployment verification passed](#71-pre-deployment-verification)
- [ ] [Post-deployment validation passed](#72-post-deployment-validation)
- [ ] [CAN motor test successful](#83-run-tests)
- [ ] [Camera test successful](#83-run-tests)
- [ ] [All ROS 2 packages available](#82-source-workspace)

### Performance
- [ ] [CPU temperature <70°C under load](#84-performance-benchmarking)
- [ ] [No CPU throttling detected](#84-performance-benchmarking)
- [ ] [Memory usage appropriate (<3.5GB)](#84-performance-benchmarking)
- [ ] [Detection latency meets targets (~130ms)](#84-performance-benchmarking)

### Production Deployment
- [ ] [Systemd service configured (if applicable)](#91-systemd-service-configuration-optional)
- [ ] [Service starts on boot (if configured)](#91-systemd-service-configuration-optional)
- [ ] [Logs accessible and monitored](#92-log-management)
- [ ] [Emergency procedures documented](#93-monitoring-and-maintenance)

**✅ All checks complete!** Your Raspberry Pi is ready for field deployment.

---

## 11. Quick Reference

### Common Commands

```bash
# ROS 2
ros2 --version
ros2 pkg list
ros2 node list
ros2 topic list
ros2 service list

# CAN Bus
sudo ip link set can0 up type can bitrate 500000
ip -details link show can0
candump can0
cansend can0 123#DEADBEEF

# System
vcgencmd measure_temp
vcgencmd get_throttled
free -h
df -h

# Build
cd ~/pragati_ros2
bash build.sh
source install/setup.bash

# Services
sudo systemctl status pragati-robot
sudo systemctl start pragati-robot
sudo systemctl stop pragati-robot
sudo journalctl -u pragati-robot -f

# GPIO
gpiodetect
gpioget gpiochip0 17
gpioset gpiochip0 22=1  # Set high
```

### Configuration Locations

- **ROS 2:** `/opt/ros/jazzy/`
- **Workspace:** `~/pragati_ros2/`
- **Boot config:** `/boot/firmware/config.txt`
- **CAN network config:** `/etc/network/interfaces.d/can0`
- **Power management:** `/etc/NetworkManager/conf.d/`, `/etc/rc.local`
- **Systemd services:** `/etc/systemd/system/`

### Script Quick Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| [install_deps.sh](scripts/setup/install_deps.sh) | Install dependencies | `bash scripts/setup/install_deps.sh` |
| [build.sh](build.sh) | Build workspace | `bash build.sh [--clean] [-j N]` |
| [rpi_verify.sh](scripts/deployment/rpi_verify.sh) | Verify system | `bash scripts/deployment/rpi_verify.sh` |
| [rpi_setup_and_test.sh](scripts/deployment/rpi_setup_and_test.sh) | CAN setup/test | `bash scripts/deployment/rpi_setup_and_test.sh` |
| [rpi_setup_depthai.sh](scripts/deployment/rpi_setup_depthai.sh) | Camera setup | `bash scripts/deployment/rpi_setup_depthai.sh` |
| [validate_rpi_deployment.sh](scripts/deployment/validate_rpi_deployment.sh) | Full validation | `bash scripts/deployment/validate_rpi_deployment.sh` |
| [verify_rpi_power_management.sh](scripts/maintenance/rpi/verify_rpi_power_management.sh) | Check power settings | `bash scripts/maintenance/rpi/verify_rpi_power_management.sh` |
| [fix_rpi_power_management.sh](scripts/maintenance/rpi/fix_rpi_power_management.sh) | Fix power issues | `sudo bash scripts/maintenance/rpi/fix_rpi_power_management.sh` |

### Network Configuration

**Static IP (optional):**

Edit `/etc/netplan/50-cloud-init.yaml`:

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses: [192.168.1.100/24]
      gateway4: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

Apply: `sudo netplan apply`

### Emergency Procedures

**Stop all motors:**
```bash
# Via systemd service
sudo systemctl stop pragati-robot

# Direct CAN command (if emergency_motor_stop.sh exists)
bash ~/pragati_ros2/emergency_motor_stop.sh
```

**Reset CAN interface:**
```bash
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 500000
```

**Check system logs for errors:**
```bash
sudo journalctl -u pragati-robot -n 100 --no-pager
dmesg | tail -50
```

---

## 12. Known Issues and Solutions

### Issue: Build Fails with Out of Memory

**Symptoms:**
- Build process killed
- System becomes unresponsive
- Error: "c++: fatal error: Killed"

**Solutions:**
```bash
# 1. Use fewer parallel workers
bash build.sh -j 1

# 2. Increase swap space
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile  # Set CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# 3. Build packages sequentially
colcon build --packages-select motor_control_ros2
colcon build --packages-select cotton_detection_ros2
# ... continue for each package
```

**See:** [RPI_BENCHMARK_GUIDE.md](RPI_BENCHMARK_GUIDE.md) Section "Out of Memory During Build"

### Issue: CAN Interface Not Found

**Symptoms:**
- `ip link show can0` returns "Device not found"
- No `/dev/spi*` devices

**Solutions:**
```bash
# 1. Verify SPI enabled in boot config
cat /boot/firmware/config.txt | grep spi
# Should show: dtparam=spi=on

# 2. Check device tree overlays
dmesg | grep -i 'mcp2515\|spi'

# 3. Verify correct oscillator frequency
# Edit /boot/firmware/config.txt and match your CAN HAT specs
sudo nano /boot/firmware/config.txt
# Common values: oscillator=8000000 or oscillator=16000000

# 4. Reboot and verify
sudo reboot
```

**See:** [scripts/deployment/rpi_setup_and_test.sh](scripts/deployment/rpi_setup_and_test.sh) for automated checks

### Issue: WiFi/SSH Disconnections

**Symptoms:**
- SSH connection drops after idle time
- Ping requests timeout intermittently
- WiFi connection unstable

**Solution:**

```bash
# Run power management verification
bash scripts/maintenance/rpi/verify_rpi_power_management.sh

# If checks fail, apply fixes
sudo bash scripts/maintenance/rpi/fix_rpi_power_management.sh
sudo bash scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh

# Reboot and re-verify
sudo reboot
```

**See:** [docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md](docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md)

### Issue: Camera Not Detected

**Symptoms:**
- `lsusb` doesn't show OAK-D Lite (vendor ID 03e7)
- DepthAI import fails
- Camera node fails to start

**Solutions:**
```bash
# 1. Check USB connection
lsusb | grep 03e7
# Should show: Intel Movidius MyriadX

# 2. Try different USB port (prefer USB 3.0 ports)

# 3. Check USB power management
bash scripts/maintenance/rpi/verify_rpi_power_management.sh

# 4. Re-run DepthAI setup
bash scripts/deployment/rpi_setup_depthai.sh

# 5. Verify DepthAI installation
python3 -c "import depthai as dai; print(dai.__version__)"
```

### Issue: Motor Communication Fails

**Symptoms:**
- No CAN traffic on `candump can0`
- Motor test script reports errors
- Motors don't respond to commands

**Solutions:**
```bash
# 1. Verify CAN bitrate (MUST match your config; current repo default is 500000)
ip -details link show can0 | grep bitrate
# Expected: bitrate 500000

# 2. If wrong bitrate, reconfigure
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# 3. Check motor power
# Ensure motors are powered on and CAN bus is properly terminated (120Ω resistors)

# 4. Run motor test script
bash scripts/deployment/rpi_setup_and_test.sh
```

**⚠️ Critical:** CAN bitrate must match across the bus (configs + OS interface).

### Platform-Specific Notes

#### Raspberry Pi 4 vs Raspberry Pi 5

| Aspect | Raspberry Pi 4 | Raspberry Pi 5 |
|--------|----------------|----------------|
| **SPI overlays** | `mcp2515-can0` | May differ - check docs |
| **GPIO library** | Works with sysfs and libgpiod | Prefer libgpiod |
| **USB-C** | Power only | May support data (verify) |
| **NVMe** | Not supported | PCIe NVMe support |
| **Performance** | 1.5-1.8 GHz (4 cores) | 2.4 GHz (4 cores, faster) |

**See:** [docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md](docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md) for platform-specific details

### Performance Optimization

**Reduce temperature:**
```bash
# Check current temperature
vcgencmd measure_temp

# Add heatsink and fan
# Configure fan control in /boot/firmware/config.txt:
# dtparam=fan_temp0=50000
```

**CPU governor:**
```bash
# Set to performance mode (increase power usage)
sudo apt install cpufrequtils
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl restart cpufrequtils
```

**Disable unnecessary services:**
```bash
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
```

---

## Maintenance and Updates

### Updating This Checklist

When any referenced script changes behavior, flags, or outputs, update this checklist to reflect the changes.

**Maintainers:** Update this document when:
- Adding or modifying deployment/validation scripts
- Changing ROS 2 version (currently Jazzy on Ubuntu 24.04)
- Updating hardware requirements
- Discovering new issues or solutions

### Version Tracking

- **Current OS Target:** Ubuntu 24.04 LTS (Noble Numbat)
- **Current ROS Version:** ROS 2 Jazzy
- **Last Validated:** 2025-11-04
- **Raspberry Pi Models:** Pi 4 (4-8GB), Pi 5

### Related Documentation

For detailed information, refer to:
- [docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md](docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md) - Comprehensive deployment guide
- [RPI_DEPLOYMENT_STATUS.md](RPI_DEPLOYMENT_STATUS.md) - Current deployment status
- [RPI_BENCHMARK_GUIDE.md](RPI_BENCHMARK_GUIDE.md) - Performance benchmarking
- [docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md](docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md) - Hardware fixes
- [docs/guides/CAN_BUS_SETUP_GUIDE.md](docs/guides/CAN_BUS_SETUP_GUIDE.md) - CAN bus configuration
- [docs/guides/GPIO_SETUP_GUIDE.md](docs/guides/GPIO_SETUP_GUIDE.md) - GPIO configuration

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-04  
**Status:** Production Ready ✅
