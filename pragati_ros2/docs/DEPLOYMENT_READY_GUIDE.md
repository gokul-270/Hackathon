# 🚀 Ready to Deploy! - Quick Start Guide

**Date:** 2026-02-03
**Status:** ✅ Build working, ready for RPi deployment

---

## ✅ What's Working Now

### Your WSL Ubuntu Development Environment
- **Location:** `~/pragati_ros2`
- **ROS2 Jazzy:** Installed and working
- **All packages:** Built successfully (native x86_64)
- **Build time:** ~10 minutes first build, incremental builds faster
- **Deployment tool:** `sync.sh` ready to use

### Packages Built
```
✅ common_utils
✅ cotton_detection_ros2
✅ motor_control_ros2
✅ pattern_finder
✅ robot_description
✅ vehicle_control
✅ yanthra_move
```

---

## 🎯 How to Deploy to Your Raspberry Pi

### Prerequisites Check

**1. Ensure RPi is powered on and connected:**
```bash
# From Windows PowerShell or CMD
ping 192.168.137.238

# Expected: Replies from 192.168.137.238
```

**2. Ensure SSH works from Windows:**
```bash
# From Windows (PowerShell/CMD)
ssh ubuntu@192.168.137.238
# Enter password when prompted
# You should get Ubuntu prompt
```

---

## 📦 Deployment Steps

### Method 1: Using sync.sh (Recommended)

#### **Option A: Sync + Build on RPi** (Simplest)

```bash
# From WSL, in ~/pragati_ros2:

# 1. Configure deployment target (one time only)
./sync.sh --ip 192.168.137.238 --user ubuntu --save

# 2. Deploy and build
./sync.sh --build

# What this does:
# - Syncs source code to RPi via Windows SSH
# - Triggers build on RPi (takes ~15-20 min first time)
# - Future builds are incremental (~2-3 min)
```

#### **Option B: Sync Only** (Build Manually on RPi)

```bash
# From WSL:
./sync.sh --ip 192.168.137.238 --user ubuntu

# Then SSH to RPi and build manually:
# (See "Manual Deployment" section below)
```

---

### Method 2: Manual Deployment (If sync.sh has issues)

#### **From Windows (PowerShell/CMD):**

```powershell
# 1. Navigate to project
cd D:\pragati_ros2

# 2. Sync code to RPi using Windows rsync (if installed)
# or use scp to copy specific directories

# 3. SSH to RPi
ssh ubuntu@192.168.137.238
```

#### **On Raspberry Pi:**

```bash
# 1. Navigate to workspace
cd ~/pragati_ros2

# 2. Source ROS2
source /opt/ros/jazzy/setup.bash

# 3. Build workspace
colcon build --symlink-install --cmake-args -DBUILD_TESTING=OFF

# 4. Source built workspace
source install/setup.bash

# 5. Test if packages are available
ros2 pkg list | grep yanthra
```

---

## 🧪 Testing After Deployment

### On Raspberry Pi

#### **1. Verify Installation**

```bash
# SSH to RPi
ssh ubuntu@192.168.137.238

# Check workspace
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# List packages
ros2 pkg list | grep -E "(yanthra|motor|cotton|vehicle)"

# Expected output:
# cotton_detection_ros2
# motor_control_ros2
# vehicle_control
# yanthra_move
```

#### **2. Test Individual Nodes**

```bash
# Test yanthra_move node
ros2 run yanthra_move yanthra_move_node

# In another terminal (new SSH session):
# Check if node is running
ros2 node list

# Check topics
ros2 topic list
```

#### **3. Launch Full System**

```bash
# Launch complete system
ros2 launch yanthra_move pragati_complete.launch.py

# Or check available launch files
ros2 launch yanthra_move --show-args
```

---

## ⚠️ Network Considerations

### Current Setup
- **WSL IP:** 192.168.1.68 (on main network)
- **RPi IP:** 192.168.137.238 (on Windows Mobile Hotspot)
- **Different subnets:** WSL cannot directly reach RPi

### Why sync.sh Uses Windows SSH
The `sync.sh` script is configured to use Windows SSH as a bridge:
```bash
# Inside sync.sh, it detects WSL and uses:
/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe ubuntu@192.168.137.238
```

This works because:
1. Windows can reach both networks (main + hotspot)
2. WSL mounts Windows at `/mnt/c`
3. sync.sh automatically uses Windows SSH when on WSL

### If Deployment Fails

**Symptom:** "No route to host" or "Connection refused"

**Solutions:**

1. **Use Windows directly for deployment:**
   ```bash
   # From Windows PowerShell in D:\pragati_ros2
   # Manually rsync or copy files to RPi
   ```

2. **Bridge the network:**
   ```bash
   # Source the bridge helper (already done in your setup)
   source scripts/rpi-wsl-bridge.sh
   create_rpi_ssh_wrappers

   # Now SSH works via Windows
   ssh rpi  # This becomes: /mnt/c/WINDOWS/System32/OpenSSH/ssh.exe ubuntu@192.168.137.238
   ```

3. **Connect RPi to main network:**
   - Connect RPi to same network as WSL (192.168.1.x)
   - Then direct SSH will work
   - Update sync.sh config with new IP

---

## 🔄 Daily Workflow After Initial Setup

### Development Cycle

```bash
# 1. Edit code in WSL (VSCode, vim, etc.)
vim src/yanthra_move/src/yanthra_move_node.cpp

# 2. Build locally for quick syntax check (optional)
./build.sh fast

# 3. Deploy to RPi when ready
./sync.sh --build

# 4. SSH to RPi and test
ssh ubuntu@192.168.137.238
cd ~/pragati_ros2
source install/setup.bash
ros2 launch ...
```

### Quick Update (No Rebuild)

```bash
# If you only changed Python or config files:
./sync.sh  # Sync without building
```

---

## 📊 Build Times Reference

| Build Type | Time (First) | Time (Incremental) |
|------------|--------------|-------------------|
| WSL native build | ~10 min | ~2-3 min |
| RPi native build | ~15-20 min | ~3-5 min |
| Cross-compile (not setup) | N/A | N/A |

**Tip:** Python files don't need rebuild - just rsync and relaunch!

---

## 🎓 Quick Command Reference

### Build Commands
```bash
./build.sh              # Standard build
./build.sh fast         # Fast build (no tests)
./build.sh pkg yanthra_move  # Build single package
./build.sh --clean      # Clean build
```

### Deployment Commands
```bash
./sync.sh --ip <IP> --save      # Configure target (once)
./sync.sh                       # Sync code
./sync.sh --build               # Sync + build on RPi
./sync.sh --dry-run             # Preview changes
./sync.sh --verbose             # Show rsync details
```

### Testing on RPi
```bash
# After SSH to RPi:
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch yanthra_move pragati_complete.launch.py
ros2 run yanthra_move yanthra_move_node
ros2 topic list
ros2 node list
```

---

## ❓ Troubleshooting

### "No route to host" when deploying
- Check RPi is powered on: `ping 192.168.137.238` from Windows
- Verify Windows SSH works: `ssh ubuntu@192.168.137.238` from Windows
- sync.sh should auto-detect WSL and use Windows SSH

### "colcon: command not found" on RPi
- RPi needs ROS2 Jazzy installed
- Run `./setup_raspberry_pi.sh` on RPi first
- Or manually: `sudo apt install ros-jazzy-desktop`

### Build fails on RPi
- Check available disk space: `df -h`
- Check memory: `free -h`
- RPi needs 2GB swap for cotton_detection build
- `./build.sh` on RPi auto-configures swap

### Deployment is slow
- Normal! Syncing over WiFi takes time
- First deploy: ~2-5 minutes (copies everything)
- Incremental: ~30-60 seconds (only changed files)
- Consider wired Ethernet for faster speeds

---

## 🎉 Success Criteria

After deployment, you should have:

- [x] Code synced to RPi at `~/pragati_ros2`
- [x] Workspace built: `install/` directory exists
- [x] All packages visible: `ros2 pkg list | grep yanthra`
- [x] Nodes can launch: `ros2 run yanthra_move yanthra_move_node`
- [x] Launch files work: `ros2 launch yanthra_move ...`

---

## 📝 Next Steps After Successful Deployment

1. **Test individual nodes** - Verify each component works
2. **Test full system** - Launch complete.launch.py
3. **Check hardware interfaces** - CAN bus, GPIO, camera
4. **Calibrate system** - Follow hardware setup guides
5. **Field testing** - Real-world cotton picking tests

---

## 📚 Related Documentation

- **Setup guides:**
  - `setup_ubuntu_dev.sh` - WSL setup (already done)
  - `setup_raspberry_pi.sh` - RPi initial setup
  - `docs/UBUNTU_SETUP_GUIDE.md` - Detailed WSL guide

- **Deployment:**
  - `sync.sh --help` - All sync options
  - `docs/MIGRATION_deploy_to_rpi.md` - Migration guide
  - `scripts/testing/QUICK_REFERENCE.md` - Testing commands

- **Network:**
  - `docs/WSL_NETWORKING_SETUP.md` - WSL mirrored networking
  - `scripts/rpi-wsl-bridge.sh` - SSH bridge helper

- **Troubleshooting:**
  - `docs/guides/TROUBLESHOOTING.md` - Common issues
  - `docs/guides/FAQ.md` - Frequently asked questions

---

## 💡 Tips for Smooth Deployment

1. **First deployment takes longest** - Be patient (15-20 min build on RPi)
2. **Use `--dry-run` first** - Preview what will be synced
3. **Check RPi resources** - Disk space and memory before building
4. **Incremental builds are fast** - After first build, only ~3-5 min
5. **Python changes don't need rebuild** - Just sync and relaunch
6. **Use tmux on RPi** - Keep sessions alive during long builds

---

**You're ready to deploy!** Start with:

```bash
# Step 1: Configure target
./sync.sh --ip 192.168.137.238 --user ubuntu --save

# Step 2: Deploy and build
./sync.sh --build

# Step 3: SSH and test
ssh ubuntu@192.168.137.238
cd ~/pragati_ros2
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py
```

Good luck! 🚀
