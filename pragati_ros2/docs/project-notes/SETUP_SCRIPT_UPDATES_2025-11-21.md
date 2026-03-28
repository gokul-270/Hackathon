# Setup Script Updates - 2025-11-21

## Summary
Updated `setup_raspberry_pi.sh` to fix issues encountered during installation and ensure smooth deployment on new Raspberry Pi systems.

## Changes Applied

### 1. Python Dependencies (Line ~389-410)
**Added missing ROS2 build dependencies:**
- `empy` - Required for ROS2 message generation
- `catkin_pkg` - Required for ROS2 package.xml parsing
- `lark` - Required for ROS2 IDL file parsing
- `setuptools` - Required by generate-parameter-library-py
- `typeguard` - Required by generate-parameter-library-py

**Fixed numpy version constraint:**
- Changed `numpy` to `"numpy<2.0.0"` for DepthAI compatibility
- Note: OpenCV prefers numpy >= 2.0, but numpy 1.26.4 works with both

### 2. System-wide DepthAI Installation (Line ~308-316)
**Added after venv DepthAI installation:**
```bash
# Install DepthAI system-wide for scripts like aruco_finder
print_status $YELLOW "🔧 Installing DepthAI system-wide for global scripts..."
if ! sudo -H python3 -c "import depthai" 2>/dev/null; then
    sudo -H pip3 install depthai==2.30.0.0 --break-system-packages
    print_status $GREEN "✅ DepthAI installed system-wide"
else
    print_status $YELLOW "⚠️  DepthAI already installed system-wide"
fi
```

**Reason:** Scripts installed in `/usr/local/bin/` (like `aruco_finder`) use system Python, not venv Python, so they need system-wide depthai access.

### 3. System Groups Creation (Line ~429-436)
**Added group creation before usermod:**
```bash
# Create gpio and spi groups if they don't exist
sudo groupadd -f gpio
sudo groupadd -f spi

# Add user to required groups
sudo usermod -a -G dialout,gpio,i2c,spi,video,plugdev $USER
```

**Reason:** Ubuntu doesn't create gpio/spi groups by default (unlike Raspberry Pi OS), causing usermod to fail.

### 4. COLCON_IGNORE for venv (Line ~537-542)
**Added before workspace build:**
```bash
# Create COLCON_IGNORE in venv to prevent colcon from scanning it
if [ -d "venv" ]; then
    touch venv/COLCON_IGNORE
    print_status $GREEN "✅ Created COLCON_IGNORE in venv directory"
fi
```

**Reason:** Prevents colcon from scanning venv's site-packages as ROS packages, which causes ModuleNotFoundError issues.

### 5. Already Fixed Previously
- Removed `--user` flag from pip install (incompatible with venv)

## Validation
All changes have been tested and validated on:
- Raspberry Pi 4 Model B Rev 1.5
- Ubuntu 24.04 Noble
- ROS2 Jazzy
- Python 3.12

## Files Modified
- `setup_raspberry_pi.sh` - Main installation script
- Backup created: `setup_raspberry_pi.sh.backup`

## Next Steps for Fresh Installation
1. Clone repository
2. Run `./setup_raspberry_pi.sh`
3. Log out and back in (for group membership)
4. Verify with validation scripts:
   - `./scripts/deployment/rpi_verify.sh`
   - `./scripts/deployment/validate_rpi_deployment.sh`

## Notes
- CAN interface configuration is included but requires physical CAN hardware
- All changes are idempotent (safe to run multiple times)
- System reboot recommended after installation for all changes to take effect

## Update 2 - Added Additional Fixes

### 6. System Clock Synchronization (STEP 0 - Line ~99-140)
**Added before all other steps:**
```bash
# Check if time is significantly off
CURRENT_YEAR=$(date +%Y)
if [ "$CURRENT_YEAR" -lt 2025 ]; then
    # Enable and sync NTP
    sudo timedatectl set-ntp true
    sudo systemctl restart systemd-timesyncd
fi
```

**Reason:** Raspberry Pi's system clock may be incorrect (often months/years in the past) after power loss or fresh install. This causes apt to fail with "Release file is not valid yet (invalid for another XXX days)" errors. Must be fixed before running `apt update`.

### 7. ROS2 Environment Sourcing Before Build (Line ~540)
**Added before colcon build:**
```bash
# Source ROS2 environment before building
source /opt/ros/jazzy/setup.bash
```

**Reason:** Ensures ROS2 environment is properly sourced in the script context before building the workspace. Required for colcon and rosdep to find ROS2 packages.

## Final Changes Summary
Total fixes applied: **7 major fixes**
1. ✅ Python dependencies (empy, catkin_pkg, lark, setuptools, typeguard)
2. ✅ NumPy version constraint (<2.0.0)
3. ✅ System-wide DepthAI installation
4. ✅ System groups creation (gpio, spi)
5. ✅ COLCON_IGNORE for venv
6. ✅ System clock synchronization
7. ✅ ROS2 environment sourcing before build

All fixes are tested and working on Ubuntu 24.04 / ROS2 Jazzy / Raspberry Pi 4.
