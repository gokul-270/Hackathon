# Pragati ROS2 - Systemd Services

This directory contains systemd service files for auto-starting required system daemons on boot.

## Available Services

### 1. pigpiod.service - GPIO Daemon

**Purpose**: Starts the pigpiod daemon for GPIO operations (end effector, compressor, LEDs, switches, sensors).

**Required for**: Raspberry Pi hardware GPIO control

**Features**:
- ✅ Auto-starts on boot
- ✅ Runs as root (required for GPIO access)
- ✅ Allows non-root ROS2 nodes to control GPIO via daemon
- ✅ Auto-restarts on failure
- ✅ Portable (no hardcoded usernames or paths)

### 2. can-watchdog@.service - CAN Bus Watchdog

**Purpose**: Monitors and auto-recovers CAN bus interfaces for motor communication.

**Required for**: MG6010 motor control via CAN bus

**Features**:
- ✅ Automatically recovers from CAN bus errors
- ✅ Parameterized service (supports multiple CAN interfaces)
- ✅ Resource-limited (minimal CPU/memory usage)
- ✅ Comprehensive logging

---

## Quick Installation (Recommended)

For pigpiod service, you can use the automated installation script:

```bash
cd /path/to/pragati_ros2/systemd
sudo ./install_pigpiod_service.sh
```

This script will:
- ✅ Check and install pigpiod if needed
- ✅ Copy service file to system location
- ✅ Enable and start the service
- ✅ Verify installation and show status

**Or follow manual installation steps below.**

---

## Manual Installation Instructions

### Installing pigpiod Service

#### Step 1: Copy Service File
```bash
# From the systemd directory:
cd /path/to/pragati_ros2/systemd
sudo cp pigpiod.service /etc/systemd/system/

# Or use absolute path from anywhere:
sudo cp /path/to/pragati_ros2/systemd/pigpiod.service /etc/systemd/system/
```

#### Step 2: Reload Systemd
```bash
sudo systemctl daemon-reload
```

#### Step 3: Enable Auto-Start on Boot
```bash
sudo systemctl enable pigpiod.service
```

#### Step 4: Start Service Immediately
```bash
sudo systemctl start pigpiod.service
```

#### Step 5: Verify Service is Running
```bash
sudo systemctl status pigpiod.service
```

Expected output:
```
● pigpiod.service - pigpiod daemon for GPIO operations
     Loaded: loaded (/etc/systemd/system/pigpiod.service; enabled; vendor preset: enabled)
     Active: active (running) since ...
```

---

### Installing CAN Watchdog Service

#### Prerequisites
The CAN watchdog requires the watchdog script to be installed system-wide:

```bash
# Copy watchdog script to system location
sudo cp /path/to/can_watchdog.sh /usr/local/sbin/
sudo chmod +x /usr/local/sbin/can_watchdog.sh
```

#### Step 1: Copy Service File
```bash
# From the systemd directory:
cd /path/to/pragati_ros2/systemd
sudo cp can-watchdog@.service /etc/systemd/system/
```

#### Step 2: Reload Systemd
```bash
sudo systemctl daemon-reload
```

#### Step 3: Enable for Specific CAN Interface (e.g., can0)
```bash
sudo systemctl enable can-watchdog@can0.service
```

#### Step 4: Start Service
```bash
sudo systemctl start can-watchdog@can0.service
```

#### Step 5: Verify Service is Running
```bash
sudo systemctl status can-watchdog@can0.service
```

---

## Managing Services

### Check Service Status
```bash
# Check pigpiod
sudo systemctl status pigpiod.service

# Check CAN watchdog
sudo systemctl status can-watchdog@can0.service
```

### View Service Logs
```bash
# pigpiod logs
sudo journalctl -u pigpiod.service -f

# CAN watchdog logs
sudo journalctl -u can-watchdog@can0.service -f
```

### Stop Services
```bash
# Stop pigpiod
sudo systemctl stop pigpiod.service

# Stop CAN watchdog
sudo systemctl stop can-watchdog@can0.service
```

### Disable Auto-Start
```bash
# Disable pigpiod
sudo systemctl disable pigpiod.service

# Disable CAN watchdog
sudo systemctl disable can-watchdog@can0.service
```

### Restart Services
```bash
# Restart pigpiod
sudo systemctl restart pigpiod.service

# Restart CAN watchdog
sudo systemctl restart can-watchdog@can0.service
```

---

## Verification & Testing

### Verify pigpiod is Running
```bash
# Check process
ps aux | grep pigpiod

# Test GPIO access from regular user (non-root)
python3 -c "import pigpio; pi=pigpio.pi(); print('Connected:', pi.connected)"
```

Expected output: `Connected: True`

### Verify CAN Interface is Up
```bash
# Check CAN interface status
ip link show can0

# Monitor CAN traffic (requires can-utils)
candump can0
```

### Test After Reboot
```bash
# Reboot system
sudo reboot

# After reboot, verify services auto-started
sudo systemctl status pigpiod.service
sudo systemctl status can-watchdog@can0.service
```

---

## Troubleshooting

### pigpiod Service Issues

**Problem**: Service fails to start
```bash
# Check detailed logs
sudo journalctl -u pigpiod.service -n 50

# Check if pigpiod binary exists
which pigpiod

# Install pigpio if missing
sudo apt-get install pigpio
```

**Problem**: "Connection refused" when ROS2 nodes try to connect
```bash
# Verify pigpiod is listening
sudo netstat -tlnp | grep pigpiod

# Check if firewall is blocking (default port: 8888)
sudo ufw status
```

**Problem**: Permission denied errors
- pigpiod must run as root
- Service file should NOT have `User=` directive
- Clients (ROS2 nodes) run as regular users

### CAN Watchdog Issues

**Problem**: Service fails to start
```bash
# Check if watchdog script exists
ls -l /usr/local/sbin/can_watchdog.sh

# Check if CAN modules are loaded
lsmod | grep can

# Load CAN modules manually
sudo modprobe can
sudo modprobe can_raw
sudo modprobe can_dev
```

**Problem**: CAN interface not recovering
```bash
# Check watchdog logs
sudo journalctl -u can-watchdog@can0.service -f

# Manually test CAN setup
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up
ip link show can0
```

---

## Uninstallation

### Remove pigpiod Service
```bash
# Stop and disable service
sudo systemctl stop pigpiod.service
sudo systemctl disable pigpiod.service

# Remove service file
sudo rm /etc/systemd/system/pigpiod.service

# Reload systemd
sudo systemctl daemon-reload
```

### Remove CAN Watchdog Service
```bash
# Stop and disable service
sudo systemctl stop can-watchdog@can0.service
sudo systemctl disable can-watchdog@can0.service

# Remove service file
sudo rm /etc/systemd/system/can-watchdog@.service

# Remove watchdog script
sudo rm /usr/local/sbin/can_watchdog.sh

# Reload systemd
sudo systemctl daemon-reload
```

---

## Portable Design Notes

Both services are designed to be **user-agnostic** and **path-agnostic**:

- ✅ No hardcoded usernames (pigpiod runs as root, clients connect as any user)
- ✅ No hardcoded workspace paths (uses system-wide binaries in `/usr/bin/` and `/usr/local/sbin/`)
- ✅ Services work on any Raspberry Pi or compatible Linux system
- ✅ Configuration via environment files: `/etc/default/pigpiod` (optional)

This ensures the services work across different deployment environments without modification.

---

## References

- **pigpiod documentation**: http://abyz.me.uk/rpi/pigpio/pigpiod.html
- **systemd service documentation**: `man systemd.service`
- **CAN bus setup**: See `/home/uday/Downloads/pragati_ros2/docs/guides/CAN_AUTO_RECOVERY.md`
- **GPIO architecture**: See `/home/uday/Downloads/pragati_ros2/GPIO_ARCHITECTURE.md`
