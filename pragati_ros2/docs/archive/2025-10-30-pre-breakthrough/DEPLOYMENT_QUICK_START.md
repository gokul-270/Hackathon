# Deployment Quick Start Guide

**Last Updated:** October 29, 2025

---

## Overview

This guide explains how to deploy from your local PC (amd64) to Raspberry Pi (ARM64) efficiently.

**Key Points:**
- ✅ Deploy only source code + configs (not binaries due to architecture difference)
- ✅ RPi builds packages for ARM64 on first deployment
- ✅ Incremental builds on RPi are fast (~18 seconds)
- ✅ Python changes don't require rebuild

---

## Prerequisites

### On Local PC
- ✅ ROS2 Jazzy installed
- ✅ SSH keys configured for RPi: `ssh-copy-id ubuntu@192.168.137.253`
- ✅ All packages built locally (optional but recommended for validation)

### On Raspberry Pi
- ✅ ROS2 Jazzy installed
- ✅ SSH access enabled
- ✅ Basic dependencies: `colcon`, `can-utils`, `python3-opencv`

---

## Deployment Workflow

### **Step 1: Deploy from Local PC**

```bash
# From your local PC workspace
cd ~/Downloads/pragati_ros2

# Simple deployment (just source + configs)
./sync.sh --build

# Or with local validation build first
./sync.sh --build --build

# Or clean build + deploy
./sync.sh --build --clean --build
```

**What gets deployed:**
- ✅ All source code (`src/`)
- ✅ Configuration files (`config/`)
- ✅ Launch files (`launch/`)
- ✅ Scripts (`scripts/`, `build_rpi.sh`, etc.)
- ❌ NOT deployed: `build/`, `install/`, `log/`, `.git/`, test artifacts

**Time:** ~30 seconds (depends on network speed)

---

### **Step 2: Build on Raspberry Pi**

```bash
# SSH to RPi
ssh ubuntu@192.168.137.253

# Navigate to workspace
cd ~/pragati_ros2

# (Optional) Verify setup
./rpi_verify_setup.sh

# Source ROS2
source /opt/ros/jazzy/setup.bash

# Build for ARM64
./build_rpi.sh

# Time: 
#   - First build: 15-20 minutes (clean)
#   - Incremental: ~18 seconds (after code changes)
```

---

### **Step 3: Run on Raspberry Pi**

```bash
# Source the workspace
source install/setup.bash

# Launch the system
ros2 launch yanthra_move pragati_complete.launch.py

# Or run specific nodes for testing
ros2 run motor_control_ros2 mg6010_controller_node
```

---

## Fast Iteration Workflow

### For Python-Only Changes

```bash
# On Local PC: Edit Python code
# Example: src/vehicle_control/vehicle_control/some_node.py

# Deploy changes
./sync.sh --build

# On RPi: NO REBUILD NEEDED! Just restart
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py
```

**Time:** ~30 seconds (deploy only)

---

### For C++ Changes

```bash
# On Local PC: Edit C++ code
# Example: src/motor_control_ros2/src/mg6010_controller.cpp

# Deploy changes
./sync.sh --build

# On RPi: Rebuild only changed package
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
colcon build --packages-select motor_control_ros2  # Fast!
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py
```

**Time:** ~30 seconds (deploy) + ~2-5 minutes (incremental build)

---

## Troubleshooting

### Issue: "Cannot connect to Raspberry Pi"

**Solution:**
```bash
# Test SSH
ssh ubuntu@192.168.137.253

# If fails, setup SSH keys
ssh-copy-id ubuntu@192.168.137.253
```

---

### Issue: Build fails on RPi with "Out of memory"

**Solution:**
```bash
# Use fewer parallel workers
./build_rpi.sh -j 1

# Or build packages sequentially
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
colcon build --packages-select robot_description
colcon build --packages-select common_utils
colcon build --packages-select motor_control_ros2
colcon build --packages-select vehicle_control
colcon build --packages-select pattern_finder
colcon build --packages-select cotton_detection_ros2
colcon build --packages-select yanthra_move
```

---

### Issue: Nodes fail with "package not found"

**Solution:**
```bash
# On RPi, verify build
cd ~/pragati_ros2
source install/setup.bash
ros2 pkg list | grep -E "motor_control|cotton|yanthra"

# If missing, rebuild
./build_rpi.sh
```

---

### Issue: CAN interface not working

**Solution:**
```bash
# On RPi, check CAN interface
ip link show can0

# If missing, configure
sudo ip link set can0 up type can bitrate 1000000

# For persistent setup, check /boot/firmware/config.txt
```

---

## Verification

### After Deployment (on RPi)

```bash
# Run verification script
cd ~/pragati_ros2
./rpi_verify_setup.sh

# Should show:
# ✓ ROS2 Jazzy installed
# ✓ Source directory exists
# ✓ Found 7 packages
# ✓ Build script exists
# etc.
```

### After Build (on RPi)

```bash
# Check built packages
source install/setup.bash
ros2 pkg list | grep -E "motor_control|cotton|yanthra|vehicle|robot_description"

# Should show:
# motor_control_ros2
# cotton_detection_ros2
# yanthra_move
# vehicle_control
# robot_description
# pattern_finder
# common_utils
```

---

## Performance Tips

### 1. Use `--symlink-install` (already in `build_rpi.sh`)
- Python files are symlinked, not copied
- Changes take effect immediately without rebuild

### 2. Build only changed packages
```bash
# Instead of full rebuild
colcon build --packages-select motor_control_ros2
```

### 3. Use ccache (if available)
```bash
# Install on RPi
sudo apt install ccache

# Will be used automatically by build_rpi.sh
```

### 4. Clean builds only when needed
```bash
# Avoid unless necessary
rm -rf build/ install/ log/
./build_rpi.sh
```

---

## Multi-RPi Deployment

For deploying to multiple Raspberry Pis:

```bash
# Edit deploy_to_rpi.sh or set environment variables

# Deploy to RPi #1
RPI_IP=192.168.137.101 ./sync.sh --build

# Deploy to RPi #2
RPI_IP=192.168.137.102 ./sync.sh --build

# Deploy to RPi #3
RPI_IP=192.168.137.103 ./sync.sh --build
```

Or use a loop:
```bash
for ip in 192.168.137.{101..104}; do
  echo "Deploying to $ip..."
  RPI_IP=$ip ./sync.sh --build
done
```

---

## Summary

| Task | Command | Time |
|------|---------|------|
| Deploy to RPi | `./sync.sh --build` | ~30s |
| First build on RPi | `./build_rpi.sh` | 15-20min |
| Incremental build | `./build_rpi.sh` | ~18s |
| Python changes | Deploy only (no rebuild) | ~30s |
| C++ changes | Deploy + rebuild package | ~2-5min |

**Key Insight:** After initial setup, development iteration is fast!

---

## Next Steps

After successful deployment and build:

1. **Hardware Testing:**
   - `scripts/validation/motor/quick_motor_test.sh`
   - `scripts/hardware_integration_test.sh`

2. **System Launch:**
   - `ros2 launch yanthra_move pragati_complete.launch.py`

3. **Monitoring:**
   - `ros2 node list`
   - `ros2 topic list`
   - `ros2 topic echo /motor_state`

---

**Questions?** Check:
- `deploy_to_rpi.sh --help`
- `rpi_verify_setup.sh`
- `docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md`
