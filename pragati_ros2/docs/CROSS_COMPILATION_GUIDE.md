# Cross-Compilation Setup Guide for Raspberry Pi

**Status**: ✅ WORKING (Tested on WSL 2026-02-04)
**Last Updated**: February 4, 2026
**Target**: Raspberry Pi 4B (aarch64) running Ubuntu 24.04 + ROS2 Jazzy

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start (After Setup)](#quick-start-after-setup)
3. [New Developer Setup](#new-developer-setup)
4. [Preflight Checks](#preflight-checks)
5. [Replicating for a Different RPi](#replicating-for-a-different-rpi)
6. [Keeping Sysroot Updated](#keeping-sysroot-updated)
7. [Troubleshooting](#troubleshooting)
8. [How It Works](#how-it-works)
9. [Future: Automated Setup Script](#future-automated-setup-script)

---

## Overview

Cross-compilation allows you to build ARM64 binaries on your x86 laptop, which is significantly faster than building directly on the RPi and avoids thermal throttling issues.

**Performance**: Expect roughly 2–4× faster builds than native on the RPi 4B; exact times vary by host CPU, SSD, and which packages are being built.

**Requirements**:
- **Host PC**: Ubuntu 22.04+ (x86_64) with ROS2 Jazzy installed
- **Target RPi**: Raspberry Pi 4B running Ubuntu 24.04 + ROS2 Jazzy
- **Network**: SSH access between host PC and RPi
- **Disk Space**: ~15GB for sysroot on host PC

---

## Quick Start (After Setup)

Once your machine is set up, cross-compilation is simple:

```bash
# Build all packages for RPi
./build.sh rpi

# Build specific package for RPi
./build.sh rpi -p yanthra_move

# Clean build for RPi
./build.sh --clean rpi

# Deploy to RPi
rsync -avz --delete install_rpi/ ubuntu@<RPI_IP>:~/pragati_ros2/install/
```

---

## New Developer Setup

Follow these steps in order on a fresh Ubuntu machine.

### Step 0: Prerequisites

Before starting, ensure you have:

**On your Host PC (laptop/desktop):**
```bash
# 1. Ubuntu 22.04 or 24.04 (x86_64)
lsb_release -a

# 2. ROS2 Jazzy installed (needed for build tools like colcon)
# If not installed, follow: https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html
ros2 --version

# 3. Git and basic build tools
sudo apt-get install -y git build-essential cmake python3-colcon-common-extensions

# 4. Clone the pragati_ros2 repository (if not already done)
cd ~/Downloads
git clone <repository-url> pragati_ros2
cd pragati_ros2
```

**On the Raspberry Pi:**
- Ubuntu 24.04 Server (aarch64) installed
- ROS2 Jazzy installed
- CycloneDDS RMW installed (`sudo apt install ros-jazzy-rmw-cyclonedds-cpp`) -- required before sysroot sync so CycloneDDS/iceoryx libraries and cmake files are captured
- Network connection (same network as your PC, or direct Ethernet)
- SSH enabled (usually default on Ubuntu Server)

**Find your RPi's IP address:**
```bash
# Option 1: On the RPi itself
hostname -I

# Option 2: From your PC (if RPi hostname is "ubuntu")
ping ubuntu.local

# Option 3: Check your router's connected devices list
```

**Set up SSH key (recommended - avoids password prompts):**
```bash
# Generate SSH key if you don't have one
test -f ~/.ssh/id_rsa || ssh-keygen -t rsa -b 4096

# Copy key to RPi (enter RPi password once)
ssh-copy-id ubuntu@<RPI_IP>

# Test passwordless login
ssh ubuntu@<RPI_IP> "echo 'SSH key setup successful!'"
```

### WSL-Specific Setup

If you're using **WSL (Windows Subsystem for Linux)**, there are additional considerations:

#### Sysroot Location
Use a dedicated directory for better space management:
```bash
# Use home directory
export RPI_SYSROOT=~/rpi-sysroot
mkdir -p ~/rpi-sysroot

# Add to ~/.bashrc for persistence:
echo 'export RPI_SYSROOT=~/rpi-sysroot' >> ~/.bashrc
source ~/.bashrc
```

#### WSL + Windows Hotspot Networking
If your RPi is connected to Windows Mobile Hotspot (192.168.137.x subnet) while WSL is on the main network (192.168.1.x), native WSL SSH cannot reach the RPi.

**Network topology:**
```
Windows Host:    192.168.1.x (main LAN) + 192.168.137.1 (hotspot gateway)
WSL Ubuntu:      192.168.1.68 (mirrored network mode)
Raspberry Pi:    192.168.137.238 (on Windows Mobile Hotspot)
```

**Solution:** Our scripts (`sync.sh`) now auto-detect this situation and use Windows SSH:
- Windows SSH can reach both networks
- Auto-detection looks for WSL + 192.168.137.x IP pattern
- Uses `/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe` automatically
- No manual intervention needed!

**Manual SSH from WSL (if needed):**
```bash
# Use Windows SSH directly:
/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe ubuntu@192.168.137.238 "echo OK"

# Or create wrapper for convenience (optional):
source scripts/rpi-wsl-bridge.sh
create_rpi_ssh_wrappers
```

**For sysroot sync on WSL:**
When running rsync commands manually, use Windows SSH with the `-e` flag:
```bash
rsync -avz -e "/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe" \
    ubuntu@192.168.137.238:/opt/ros/jazzy/ \
    ~/rpi-sysroot/opt/ros/jazzy/
```

However, `sync.sh --deploy-cross` handles this automatically!

#### Build Script Compatibility
The `build.sh` script is fully compatible with WSL. It automatically sources ROS2 environment when cross-compiling:
```bash
source /opt/ros/jazzy/setup.bash
export PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH:-}"
```

This fixes the "ModuleNotFoundError: No module named 'ament_package'" that can occur during CMake configuration.

### Step 1: Install Cross-Compiler Toolchain

```bash
sudo apt-get update
sudo apt-get install -y \
    gcc-aarch64-linux-gnu \
    g++-aarch64-linux-gnu \
    binutils-aarch64-linux-gnu
```

Verify installation:
```bash
aarch64-linux-gnu-gcc --version
# Should show: aarch64-linux-gnu-gcc (Ubuntu ...) ...
```

### Step 2: Create Sysroot Directory

The sysroot contains a copy of the RPi's libraries and headers. Default location: `/media/rpi-sysroot`

```bash
sudo mkdir -p /media/rpi-sysroot
sudo chown $USER:$USER /media/rpi-sysroot
```

### Step 3: Sync Sysroot from RPi

SSH into your RPi first to ensure it's accessible, then sync:

```bash
# Replace <RPI_IP> with your RPi's IP address (e.g., 192.168.137.203)
RPI_IP=<RPI_IP>

# Sync ROS2 Jazzy installation (~2-3 GB)
rsync -avz --progress ubuntu@$RPI_IP:/opt/ros/jazzy/ /media/rpi-sysroot/opt/ros/jazzy/

# Sync system libraries (~8-10 GB)
rsync -avz --progress ubuntu@$RPI_IP:/usr/ /media/rpi-sysroot/usr/

# Sync lib directory
rsync -avz --progress ubuntu@$RPI_IP:/lib/ /media/rpi-sysroot/lib/
```

**Note:** First sync takes 30-60 minutes depending on network speed. Total sysroot size is ~13GB.

### Step 4: Patch CMake Configs and Create Linker Symlink

Some ROS2 CMake files have hardcoded absolute paths that break cross-compilation. Additionally, a dynamic linker symlink must be created.

**Automated method (recommended):**
```bash
# Use the patching script (handles both CMake patches and linker symlink)
export RPI_SYSROOT=~/rpi-sysroot  # Or your sysroot location
./scripts/patch_sysroot_cmake.sh
```

**Manual method:**
```bash
# Use your sysroot location (adjust if different)
SYSROOT=${RPI_SYSROOT:-/media/rpi-sysroot}

# Fix hardware_interface paths
sed -i 's|/opt/ros/jazzy/include|${_IMPORT_PREFIX}/include|g' \
    $SYSROOT/opt/ros/jazzy/share/hardware_interface/cmake/export_hardware_interfaceExport.cmake
sed -i 's|/opt/ros/jazzy/lib|${_IMPORT_PREFIX}/lib|g' \
    $SYSROOT/opt/ros/jazzy/share/hardware_interface/cmake/export_hardware_interfaceExport.cmake

# Fix geometric_shapes paths (if present)
if [ -f $SYSROOT/opt/ros/jazzy/share/geometric_shapes/cmake/export_geometric_shapesExport.cmake ]; then
    sed -i 's|/opt/ros/jazzy/include|${_IMPORT_PREFIX}/include|g' \
        $SYSROOT/opt/ros/jazzy/share/geometric_shapes/cmake/export_geometric_shapesExport.cmake
    sed -i 's|/opt/ros/jazzy/lib|${_IMPORT_PREFIX}/lib|g' \
        $SYSROOT/opt/ros/jazzy/share/geometric_shapes/cmake/export_geometric_shapesExport.cmake
fi

# Create dynamic linker symlink (CRITICAL for linking to succeed)
cd $SYSROOT/lib
ln -s aarch64-linux-gnu/ld-linux-aarch64.so.1 ld-linux-aarch64.so.1
```

**Why the linker symlink is needed:**
During the linking phase, the cross-compiler looks for `/lib/ld-linux-aarch64.so.1` inside the sysroot. On the RPi, this exists as a symlink. We need to recreate it in the sysroot or linking will fail with:
```
cannot find /lib/ld-linux-aarch64.so.1 inside ~/rpi-sysroot
```

### Step 5: Verify Setup

Run the preflight checks (see next section), then test:

```bash
# Test cross-compilation
cd ~/Downloads/pragati_ros2
./build.sh rpi -p motor_control_ros2

# Verify ARM64 binary was produced
file install_rpi/lib/libmotor_control_ros2*.so
# Should show: ELF 64-bit LSB shared object, ARM aarch64
```

---

## Preflight Checks

Run these checks on a new laptop before the first cross-build to catch missing pieces quickly.

### Check 1: Toolchain Installed

```bash
# Verify cross-compiler is available
which aarch64-linux-gnu-gcc && which aarch64-linux-gnu-g++
aarch64-linux-gnu-gcc --version
```

**Expected**: Shows compiler version (e.g., `aarch64-linux-gnu-gcc (Ubuntu 13.2.0-23ubuntu4) 13.2.0`)

**If missing**: Install the toolchain:
```bash
sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu
```

### Check 2: Sysroot Present and Complete

```bash
# Check sysroot directories exist (adjust path if using custom RPI_SYSROOT)
SYSROOT=${RPI_SYSROOT:-/media/rpi-sysroot}

test -d "$SYSROOT/opt/ros/jazzy" && echo "✅ ROS in sysroot: OK" || echo "❌ Missing: /opt/ros/jazzy"
test -d "$SYSROOT/usr/lib" && echo "✅ /usr/lib in sysroot: OK" || echo "❌ Missing: /usr/lib"
test -d "$SYSROOT/usr/include" && echo "✅ /usr/include in sysroot: OK" || echo "❌ Missing: /usr/include"
test -d "$SYSROOT/lib" && echo "✅ /lib in sysroot: OK" || echo "❌ Missing: /lib"

# CycloneDDS and iceoryx (required for cross-compilation with CycloneDDS RMW)
test -d "$SYSROOT/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/CycloneDDS" \
  && echo "✅ CycloneDDS cmake in sysroot: OK" \
  || echo "❌ Missing: CycloneDDS cmake (install ros-jazzy-rmw-cyclonedds-cpp on RPi and resync)"
test -d "$SYSROOT/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/iceoryx_hoofs" \
  && echo "✅ iceoryx in sysroot: OK" \
  || echo "❌ Missing: iceoryx cmake (install ros-jazzy-rmw-cyclonedds-cpp on RPi and resync)"
```

**If missing**: Sync from RPi (see Step 3 above). If CycloneDDS/iceoryx checks fail,
ensure `ros-jazzy-rmw-cyclonedds-cpp` is installed on the RPi first, then resync.

### Check 3: CMake Patches Applied

```bash
# Check if hardware_interface export is patched
SYSROOT=${RPI_SYSROOT:-/media/rpi-sysroot}
FILE="$SYSROOT/opt/ros/jazzy/share/hardware_interface/cmake/export_hardware_interfaceExport.cmake"

if grep -q '_IMPORT_PREFIX' "$FILE" 2>/dev/null; then
    echo "✅ hardware_interface patched: OK"
else
    echo "❌ hardware_interface needs patching (see Step 4)"
fi
```

### Check 4: Dynamic Linker Symlink

```bash
# Check if linker symlink exists
SYSROOT=${RPI_SYSROOT:-/media/rpi-sysroot}
LINKER="$SYSROOT/lib/ld-linux-aarch64.so.1"

if [ -L "$LINKER" ] && [ -f "$LINKER" ]; then
    echo "✅ Dynamic linker symlink: OK"
else
    echo "❌ Dynamic linker symlink missing (see Step 4)"
    echo "   Create with: cd $SYSROOT/lib && ln -s aarch64-linux-gnu/ld-linux-aarch64.so.1 ld-linux-aarch64.so.1"
fi
```

**Why this matters:** Without this symlink, the linker will fail during cross-compilation with "cannot find /lib/ld-linux-aarch64.so.1 inside sysroot".
```

**If not patched**: Run the sed commands from Step 4.

### Check 4: Toolchain File Present

```bash
test -f cmake/toolchains/rpi-aarch64.cmake && echo "✅ Toolchain file: OK" || echo "❌ Missing toolchain file"
```

### Check 5: Smoke Test Build

```bash
# Build a small package and verify output is ARM64
./build.sh rpi -p motor_control_ros2
file install_rpi/lib/libmotor_control_ros2*.so | grep -q 'ARM aarch64' && echo "✅ ARM64 output: OK" || echo "❌ Not ARM64 binary"
```

### All-in-One Preflight Script

Copy and run this entire block to check everything at once:

```bash
echo "=== Cross-Compilation Preflight Checks ==="
SYSROOT=${RPI_SYSROOT:-/media/rpi-sysroot}
ERRORS=0
WARNINGS=0

# Check 1: Toolchain
if which aarch64-linux-gnu-gcc > /dev/null 2>&1; then
    echo "✅ Toolchain installed"
else
    echo "❌ Toolchain missing - run: sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu"
    ERRORS=$((ERRORS+1))
fi

# Check 2: Sysroot directories
for dir in "$SYSROOT/opt/ros/jazzy" "$SYSROOT/usr/lib" "$SYSROOT/usr/include" "$SYSROOT/lib"; do
    if [ -d "$dir" ]; then
        echo "✅ Found: $dir"
    else
        echo "❌ Missing: $dir"
        ERRORS=$((ERRORS+1))
    fi
done

# Check 2b: CycloneDDS/iceoryx in sysroot (required for cross-build)
for dir in "$SYSROOT/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/CycloneDDS" \
           "$SYSROOT/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/iceoryx_hoofs" \
           "$SYSROOT/opt/ros/jazzy/share/rmw_cyclonedds_cpp"; do
    if [ -d "$dir" ]; then
        echo "✅ Found: $dir"
    else
        echo "⚠️  Missing: $dir (install ros-jazzy-rmw-cyclonedds-cpp on RPi and resync)"
        WARNINGS=$((WARNINGS+1))
    fi
done

# Check 3: CMake patches
HW_FILE="$SYSROOT/opt/ros/jazzy/share/hardware_interface/cmake/export_hardware_interfaceExport.cmake"
if [ -f "$HW_FILE" ] && grep -q '_IMPORT_PREFIX' "$HW_FILE"; then
    echo "✅ hardware_interface patched"
else
    echo "❌ hardware_interface needs patching"
    ERRORS=$((ERRORS+1))
fi

# Check 4: Toolchain file
if [ -f "cmake/toolchains/rpi-aarch64.cmake" ]; then
    echo "✅ Toolchain file present"
else
    echo "❌ Toolchain file missing"
    ERRORS=$((ERRORS+1))
fi

echo "==========================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "All checks passed! Ready for cross-compilation."
elif [ $ERRORS -eq 0 ]; then
    echo "$WARNINGS warning(s). Build may work but check sysroot completeness."
else
    echo "$ERRORS issue(s) found. Fix them before building."
fi
```

---

## Replicating for a Different RPi

To set up cross-compilation for a different Raspberry Pi (e.g., a teammate's RPi or a new device):

### Option A: Fresh Sysroot (Recommended)

If the new RPi has a different software configuration:

```bash
# Clear old sysroot (optional, if switching RPis)
rm -rf /media/rpi-sysroot/*

# Sync from new RPi
NEW_RPI_IP=192.168.x.x  # Replace with new RPi's IP

rsync -avz --progress ubuntu@$NEW_RPI_IP:/opt/ros/jazzy/ /media/rpi-sysroot/opt/ros/jazzy/
rsync -avz --progress ubuntu@$NEW_RPI_IP:/usr/ /media/rpi-sysroot/usr/
rsync -avz --progress ubuntu@$NEW_RPI_IP:/lib/ /media/rpi-sysroot/lib/

# Re-apply CMake patches (Step 4)
```

### Option B: Reuse Existing Sysroot

If both RPis have identical Ubuntu + ROS2 installations, you can reuse the sysroot. Just deploy to the new RPi:

```bash
rsync -avz --delete install_rpi/ ubuntu@<NEW_RPI_IP>:~/pragati_ros2/install/
```

### Important Notes

- **OS/ROS versions must match**: If the new RPi has different Ubuntu or ROS2 versions, you'll get "library not found" errors. Always sync sysroot from the actual target RPi.
- **Different RPi model**: RPi 3 and RPi 4 both use aarch64, so the same sysroot works. RPi Zero/1/2 use armhf (32-bit) which requires a different toolchain.

---

## Using a Custom Sysroot Location

If you can't use `/media/rpi-sysroot`, set the `RPI_SYSROOT` environment variable:

```bash
export RPI_SYSROOT=/path/to/your/sysroot
./build.sh rpi
```

Or add to your `~/.bashrc`:
```bash
echo 'export RPI_SYSROOT=/path/to/your/sysroot' >> ~/.bashrc
source ~/.bashrc
```

---

## Deployment to RPi

After cross-compiling:

```bash
# Deploy all packages
rsync -avz --delete install_rpi/ ubuntu@<RPI_IP>:~/pragati_ros2/install/

# Test on RPi
ssh ubuntu@<RPI_IP> "cd ~/pragati_ros2 && source install/setup.bash && ros2 pkg list"
```

**Note:** The `--delete` flag removes files on RPi that don't exist locally. Remove it if you want to preserve extra files on RPi.

### End-to-End Verification

After deployment, verify everything works on the RPi:

```bash
# SSH into RPi
ssh ubuntu@<RPI_IP>

# Navigate to workspace
cd ~/pragati_ros2

# Source the workspace
source install/setup.bash

# Verify packages are installed
ros2 pkg list | grep -E "yanthra|motor|cotton"
# Should show: yanthra_move, motor_control_ros2, cotton_detection_ros2, etc.

# Quick node test (should start without errors, Ctrl+C to stop)
ros2 run motor_control_ros2 motor_control_node --ros-args -p test_mode:=true
```

If any step fails, check the [Troubleshooting](#troubleshooting) section.

---

## Keeping Sysroot Updated

If you install new packages on the RPi, resync the sysroot:

```bash
# Quick resync (only changed files)
rsync -avz ubuntu@<RPI_IP>:/opt/ros/jazzy/ /media/rpi-sysroot/opt/ros/jazzy/
rsync -avz ubuntu@<RPI_IP>:/usr/lib/ /media/rpi-sysroot/usr/lib/
rsync -avz ubuntu@<RPI_IP>:/usr/include/ /media/rpi-sysroot/usr/include/
```

**Important:** The cross-build toolchain expects CycloneDDS and iceoryx cmake files
in the sysroot. These come from `ros-jazzy-rmw-cyclonedds-cpp` (installed by
`setup_raspberry_pi.sh`). If you rebuild a sysroot from scratch, ensure that package
is installed on the RPi before syncing.

---

## Troubleshooting

### WSL: Cannot SSH to RPi on Windows Hotspot

**Symptom**: Native SSH from WSL fails with "No route to host" or times out when RPi is on 192.168.137.x subnet.

**Cause**: RPi is connected to Windows Mobile Hotspot (192.168.137.x), but WSL is on the main network (192.168.1.x). They're on different subnets.

**Fix**: Use Windows SSH instead of native WSL SSH:
```bash
# Manual SSH using Windows SSH:
/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe ubuntu@192.168.137.238 "echo OK"

# Or use our scripts - they auto-detect and use Windows SSH:
./sync.sh --deploy-cross  # Automatically uses Windows SSH
```

The `sync.sh` script now automatically detects WSL + hotspot subnet and uses Windows SSH. No manual activation needed!

### "ModuleNotFoundError: No module named 'ament_package'"

**Symptom**: CMake configuration fails with Python module not found errors during cross-compilation.

**Cause**: CMake subprocess needs access to ROS2 Python packages during configuration.

**Fix**: Already fixed in `build.sh`. The script now sources ROS2 environment before cross-compiling:
```bash
source /opt/ros/jazzy/setup.bash
export PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH:-}"
```

If you still see this, make sure you're using the latest `build.sh`.

### "cannot find /lib/ld-linux-aarch64.so.1 inside sysroot"

**Symptom**: Linker fails during cross-compilation with message about missing dynamic linker.

**Cause**: Dynamic linker symlink is missing in sysroot's `/lib` directory.

**Fix**: Create the symlink:
```bash
SYSROOT=${RPI_SYSROOT:-/media/rpi-sysroot}
cd $SYSROOT/lib
ln -s aarch64-linux-gnu/ld-linux-aarch64.so.1 ld-linux-aarch64.so.1
```

Or run the patching script which now handles this automatically:
```bash
./scripts/patch_sysroot_cmake.sh
```

### "Cannot find package X"

**Cause**: Package not in sysroot.

**Fix**: Install on RPi, then resync:
```bash
# On RPi:
sudo apt install ros-jazzy-<package-name>

# On host PC:
rsync -avz ubuntu@<RPI_IP>:/opt/ros/jazzy/ /media/rpi-sysroot/opt/ros/jazzy/
```

### "CycloneDDS::idlc" or "iceoryx_posh::iox-roudi" not found

**Cause**: CycloneDDS/iceoryx binaries or cmake files missing from sysroot. The toolchain
uses CycloneDDS as the default RMW, so cmake validates that all CycloneDDS imported targets
(including executables like `idlc` and `iox-roudi`) exist in the sysroot.

**Fix**:
```bash
# Ensure CycloneDDS is installed on the RPi:
ssh ubuntu@<RPI_IP> "sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp"

# Resync the sysroot (captures CycloneDDS, iceoryx, and all transitive deps):
rsync -avz ubuntu@<RPI_IP>:/opt/ros/jazzy/ /media/rpi-sysroot/opt/ros/jazzy/

# Verify the key files exist:
ls /media/rpi-sysroot/opt/ros/jazzy/bin/idlc
ls /media/rpi-sysroot/opt/ros/jazzy/bin/iox-roudi
ls /media/rpi-sysroot/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/CycloneDDS/

# Then clean-build:
./build.sh --clean rpi
```

### "Library not found" during linking

**Cause**: Library exists on RPi but not synced to sysroot.

**Fix**:
```bash
# Find where it should be
find /media/rpi-sysroot -name "libmissing*"

# If not found, check on RPi:
ssh ubuntu@<RPI_IP> "find /usr -name 'libmissing*'"

# Install on RPi if needed, then resync /usr:
sudo apt install libmissing-dev  # on RPi
rsync -avz ubuntu@<RPI_IP>:/usr/ /media/rpi-sysroot/usr/  # on host PC
```

### Build uses x86 instead of ARM

**Cause**: Toolchain file not being used.

**Fix**: Verify toolchain is applied:
```bash
grep CMAKE_SYSTEM_PROCESSOR build_rpi/*/CMakeCache.txt
# Should show: CMAKE_SYSTEM_PROCESSOR:INTERNAL=aarch64

# If not, clean and rebuild:
./build.sh --clean rpi
./build.sh rpi
```

### Hardcoded path errors

**Cause**: CMake export files contain absolute paths like `/opt/ros/jazzy/...`.

**Fix**: Patch them (see Step 4), or find and fix:
```bash
# Find files with hardcoded paths
grep -r '"/opt/ros' /media/rpi-sysroot/opt/ros/jazzy/share/*/cmake/*.cmake | head

# Patch similar to hardware_interface
sed -i 's|/opt/ros/jazzy/include|${_IMPORT_PREFIX}/include|g' <file>
sed -i 's|/opt/ros/jazzy/lib|${_IMPORT_PREFIX}/lib|g' <file>
```

### SSH connection issues during rsync

**Cause**: SSH keys not set up or RPi not reachable.

**Fix**:
```bash
# Test SSH first
ssh ubuntu@<RPI_IP> "echo Connected"

# If password prompts are annoying, set up SSH key:
ssh-copy-id ubuntu@<RPI_IP>
```

### Sysroot takes too much disk space

**Tip**: You can exclude some large directories that aren't needed:
```bash
# Exclude documentation and some dev files (saves ~2GB)
rsync -avz --exclude='share/doc' --exclude='share/man' ubuntu@<RPI_IP>:/usr/ /media/rpi-sysroot/usr/
```

---

## How It Works

### Toolchain File
`cmake/toolchains/rpi-aarch64.cmake` configures CMake for cross-compilation:
- Sets compiler to `aarch64-linux-gnu-gcc/g++`
- Points to sysroot for headers and libraries
- Configures library search paths

### Build Script Integration
`./build.sh rpi` automatically:
- Passes the toolchain file to CMake
- Uses `build_rpi/` and `install_rpi/` directories
- Sources native ROS2 for build tools (ament, colcon)

### What Gets Built
- `robot_description` - URDF files
- `common_utils` - Shared utilities
- `motor_control_ros2` - CAN motor control
- `cotton_detection_ros2` - Camera + YOLOv11
- `yanthra_move` - Main arm control
- `vehicle_control` - Vehicle control
- `pattern_finder` - ArUco detection

---

## Future: Automated Setup Script

The setup process documented above could be automated in the future. Below is a specification for a potential `setup_cross_compile.sh` script:

### Proposed Features

1. **Preflight checks**: Verify host PC has required packages
2. **Toolchain installation**: Auto-install cross-compiler if missing
3. **Sysroot sync**: Interactive prompts for RPi IP, handles rsync
4. **CMake patching**: Auto-detect and patch hardcoded paths
5. **Verification**: Run smoke test build after setup
6. **Doctor mode**: `--doctor` flag to diagnose existing setup issues

### Proposed Usage

```bash
# Full setup (interactive)
./scripts/setup_cross_compile.sh --setup --rpi-ip=192.168.137.203

# Check existing setup
./scripts/setup_cross_compile.sh --doctor

# Resync sysroot only
./scripts/setup_cross_compile.sh --resync --rpi-ip=192.168.137.203

# Apply patches only
./scripts/setup_cross_compile.sh --patch
```

### Implementation Notes

- Script should be idempotent (safe to run multiple times)
- Should detect if sysroot already exists and prompt before overwriting
- Should validate RPi is accessible via SSH before starting sync
- Should estimate time remaining during rsync
- Could integrate as `./build.sh rpi --setup` to reuse existing script

**Note**: Until this script is implemented, follow the manual steps above.

---

## References

- Toolchain file: `cmake/toolchains/rpi-aarch64.cmake`
- Build script: `build.sh` (rpi mode)
- Field trial cheatsheet: `docs/FIELD_TRIAL_CHEATSHEET.md`
- Project documentation: `docs/START_HERE.md`
