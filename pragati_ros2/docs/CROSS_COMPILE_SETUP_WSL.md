# Cross-Compilation Setup for WSL - Quick Start

**Date:** 2026-02-04
**Status:** ✅ Fully tested and working!
**Time Required:** ~45-60 minutes (mostly waiting for rsync)

---

## 🎯 What You'll Get

After setup:
- **Fast builds:** 2-4× faster than building on RPi
- **No thermal throttling:** Use your powerful laptop CPU
- **Easy deployment:** Pre-compiled ARM binaries ready to deploy

---

## ✅ Prerequisites (Already Done!)

- [x] WSL Ubuntu 24.04 configured
- [x] ROS2 Jazzy installed
- [x] Cross-compiler installed (`aarch64-linux-gnu-gcc 13.3.0`)
- [x] Toolchain file present (`cmake/toolchains/rpi-aarch64.cmake`)
- [x] Setup script created (`scripts/setup_cross_compile.sh`)
- [x] CycloneDDS installed on RPi (`ros-jazzy-rmw-cyclonedds-cpp`) -- sysroot must include it

**You're 95% ready! Only need sysroot from RPi.**

---

## 🚀 Setup Steps (When RPi is Available)

### Important: Proven Workflow

The cross-compilation system is **fully tested and working**! Below is the proven workflow we successfully used:

**What we tested:**
- ✅ Synced complete sysroot (13GB) from RPi to `~/rpi-sysroot`
- ✅ Applied CMake patches + created dynamic linker symlink
- ✅ Cross-compiled all 7 packages (robot_description, motor_control_ros2, etc.)
- ✅ Deployed ARM64 binaries to RPi using Windows SSH bridge
- ✅ Verified execution on RPi - all nodes started successfully!

**Build performance:** 3-4× faster than native RPi builds (4.5 min vs 15-20 min for motor_control_ros2)

### Step 1: Power On RPi and Verify Network

```bash
# From Windows PowerShell:
ping 192.168.137.238

# Expected: Replies from 192.168.137.238
```

### Step 2: Setup SSH Key (One Time)

```bash
# From Windows PowerShell:
ssh-copy-id ubuntu@192.168.137.238

# Enter RPi password when prompted
# This enables passwordless SSH for future operations
```

### Step 3: Run Automated Setup

```bash
# From WSL, in the workspace root:
./scripts/setup_cross_compile.sh --setup --rpi-ip=192.168.137.238
```

**What this does:**
1. ✅ Checks toolchain (already installed)
2. ✅ Tests SSH to RPi
3. ✅ Creates sysroot directory (`/media/rpi-sysroot`)
4. ⏳ Syncs RPi filesystem (~30-60 min, 13GB total)
   - `/opt/ros/jazzy` (~2-3GB)
   - `/usr` (~8-10GB)
   - `/lib` (~1-2GB)
5. ✅ Patches CMake files automatically
6. ✅ Runs smoke test build

**Progress:** You'll see rsync progress bars. Grab coffee! ☕

### Step 4: Verify Setup

```bash
# After setup completes:
./scripts/setup_cross_compile.sh --doctor

# Expected: All ✅ green checkmarks
```

---

## 🔨 Using Cross-Compilation

### Build for RPi (Fast!)

```bash
# Set sysroot location (add to ~/.bashrc for persistence)
export RPI_SYSROOT=~/rpi-sysroot

# Build all packages for ARM64
./build.sh rpi

# Build specific package
./build.sh rpi -p yanthra_move

# Clean build
./build.sh --clean rpi
```

**Build times (tested on WSL):**
- motor_control_ros2: ~4.5 minutes (vs ~15-20 min on RPi)
- Full workspace: ~10-15 minutes (vs ~30-40 min on RPi)
- **3-4× faster** than native RPi builds!

**Verify ARM64 output:**
```bash
file install_rpi/lib/libmotor_control_ros2_mg6010.so
# Should show: ELF 64-bit LSB shared object, ARM aarch64
```

### Deploy to RPi

**WSL Note:** sync.sh automatically detects WSL + Windows hotspot setup and uses Windows SSH bridge. No manual activation needed!

```bash
# Deploy cross-compiled binaries (recommended)
./sync.sh --deploy-cross

# You'll see: "WSL detected: Using Windows SSH for hotspot connectivity"
# Deployment takes ~30 seconds
```

### Verify on RPi

```bash
# SSH to RPi
ssh ubuntu@192.168.137.238

# Check packages
cd ~/pragati_ros2
source install/setup.bash
ros2 pkg list | grep yanthra

# Launch
ros2 launch yanthra_move pragati_complete.launch.py
```

---

## 🔄 Workflow Comparison

### Before Cross-Compilation (Native Build)
```bash
# On WSL:
./sync.sh --build              # Sync code
# Wait ~15-20 minutes for RPi to build

# On RPi (after SSH):
cd ~/pragati_ros2
source install/setup.bash
ros2 launch ...
```

### After Cross-Compilation (Faster!)
```bash
# On WSL:
./build.sh rpi                 # Build on WSL (8-12 min)
./sync.sh --deploy-cross       # Deploy binaries (30 sec)

# On RPi (after SSH):
cd ~/pragati_ros2
source install/setup.bash
ros2 launch ...                # Already built, just launch!
```

**Time saved:** ~7-10 minutes per build cycle!

---

## 🛠️ Maintenance

### Keep Sysroot Updated

When you install new packages on RPi:

```bash
# On RPi:
sudo apt install ros-jazzy-new-package

# On WSL:
./scripts/setup_cross_compile.sh --resync --rpi-ip=192.168.137.238
```

> **Note:** The toolchain requires CycloneDDS and iceoryx in the sysroot. These are
> pulled in by `ros-jazzy-rmw-cyclonedds-cpp` (installed by `setup_raspberry_pi.sh`).
> If you build a fresh sysroot, verify that package is installed on the RPi first.

### Check Setup Health

```bash
./scripts/setup_cross_compile.sh --doctor
```

### Re-apply Patches Only

```bash
./scripts/setup_cross_compile.sh --patch
```

---

## 📊 Disk Space Requirements

| Location | Size | Note |
|----------|------|------|
| `/media/rpi-sysroot` | ~13GB | RPi filesystem mirror |
| `install_rpi/` | ~500MB | Cross-compiled output |
| Total | ~13.5GB | One-time cost |

**Check available space:**
```bash
df -h /media
```

If `/media` doesn't have enough space, use custom location:
```bash
export RPI_SYSROOT=~/rpi-sysroot
./scripts/setup_cross_compile.sh --setup --rpi-ip=192.168.137.238 --sysroot=~/rpi-sysroot

# Add to ~/.bashrc for persistence:
echo 'export RPI_SYSROOT=~/rpi-sysroot' >> ~/.bashrc
```

---

## 🔧 WSL-Specific Notes

### Sysroot Location
We use `~/rpi-sysroot` instead of `/media/rpi-sysroot` for better space availability:

```bash
# Add to ~/.bashrc for persistence:
echo 'export RPI_SYSROOT=~/rpi-sysroot' >> ~/.bashrc
source ~/.bashrc
```

### Windows SSH Bridge (Automatic)
When RPi is on Windows Mobile Hotspot (192.168.137.x), WSL cannot directly reach it. Our scripts now auto-detect this and use Windows SSH:

- **sync.sh:** Automatically uses `/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe` when needed
- **Visual confirmation:** Shows "WSL detected: Using Windows SSH for hotspot connectivity"
- **No manual activation required!**

### Network Topology
```
Windows Host:    192.168.1.x (main LAN) + 192.168.137.1 (hotspot gateway)
WSL Ubuntu:      192.168.1.68 (mirrored network mode)
Raspberry Pi:    192.168.137.238 (on Windows Mobile Hotspot)
```

Native WSL SSH can't reach 192.168.137.x subnet, but Windows SSH can!

---

## ⚠️ Troubleshooting

### WSL + Windows Hotspot Networking

**Issue:** RPi is on Windows Mobile Hotspot (192.168.137.x) but WSL is on main network (192.168.1.x), so native SSH from WSL cannot reach RPi.

**Solution (Automatic):** sync.sh now auto-detects this situation and uses Windows SSH:
```bash
# Just run normally - auto-detection works!
./sync.sh --deploy-cross

# You'll see: "WSL detected: Using Windows SSH for hotspot connectivity"
```

**Manual verification:**
```bash
# Test connection from WSL using Windows SSH:
/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe ubuntu@192.168.137.238 "echo OK"
```

### "ModuleNotFoundError: No module named 'ament_package'"

**Issue:** CMake can't find ROS2 Python packages during cross-compilation configuration.

**Solution:** Already fixed in `build.sh` (lines 1020-1030). The script now sources ROS2 environment before cross-compiling:
```bash
source /opt/ros/jazzy/setup.bash
export PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH:-}"
```

If you still see this error, make sure you're using the latest build.sh.

### "cannot find /lib/ld-linux-aarch64.so.1 inside sysroot"

**Issue:** Dynamic linker symlink is missing in sysroot.

**Solution:** Now automatically created by `scripts/patch_sysroot_cmake.sh`. If you get this error:
```bash
# Run the patching script:
export RPI_SYSROOT=~/rpi-sysroot
./scripts/patch_sysroot_cmake.sh

# Or create manually:
cd ~/rpi-sysroot/lib
ln -s aarch64-linux-gnu/ld-linux-aarch64.so.1 ld-linux-aarch64.so.1
```

### "Cannot connect to RPi"
**Solution:**
1. Check RPi is on: `ping 192.168.137.238` from Windows
2. Test Windows SSH works: `ssh ubuntu@192.168.137.238` from Windows PowerShell
3. Setup SSH key: `ssh-copy-id ubuntu@192.168.137.238` from Windows PowerShell
4. sync.sh automatically uses Windows SSH bridge when it detects WSL + hotspot IP

### "Not enough disk space"
**Solution:**
```bash
# Use the home directory (has more space)
./scripts/setup_cross_compile.sh --setup --rpi-ip=192.168.137.238 --sysroot=~/rpi-sysroot
```

### "Sync is very slow"
**This is normal!** First sync transfers ~13GB over WiFi:
- **WiFi:** 30-60 minutes
- **Ethernet:** 15-30 minutes

**Tip:** Run overnight, or during a long lunch!

### "Build fails with missing library"
**Cause:** Library on RPi but not in sysroot

**Solution:**
```bash
# Install missing package on RPi first:
ssh ubuntu@192.168.137.238 "sudo apt install <package>"

# Then resync:
./scripts/setup_cross_compile.sh --resync --rpi-ip=192.168.137.238
```

### "CycloneDDS::idlc" or "iceoryx" not found
**Cause:** CycloneDDS/iceoryx missing from sysroot. The toolchain uses CycloneDDS as the
default RMW, so cmake requires CycloneDDS and iceoryx cmake files and binaries in the sysroot.

**Solution:**
```bash
# Ensure CycloneDDS is installed on RPi:
ssh.exe ubuntu@192.168.137.238 "sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp"

# Resync sysroot:
./scripts/setup_cross_compile.sh --resync --rpi-ip=192.168.137.238

# Clean-build:
./build.sh --clean rpi
```

### "Binaries are x86, not ARM"
**Cause:** Toolchain not being used

**Solution:**
```bash
# Clean and rebuild
./build.sh --clean rpi
./build.sh rpi

# Verify output
file install_rpi/lib/*.so | grep "ARM aarch64"
```

---

## 🎓 Quick Command Reference

```bash
# Setup sysroot location (one time)
echo 'export RPI_SYSROOT=~/rpi-sysroot' >> ~/.bashrc
source ~/.bashrc

# Setup cross-compilation (one time)
./scripts/setup_cross_compile.sh --setup --rpi-ip=192.168.137.238

# Or use manual setup with patching script:
./scripts/patch_sysroot_cmake.sh  # Patches CMake + creates linker symlink

# Check health
./scripts/setup_cross_compile.sh --doctor

# Build for RPi
export RPI_SYSROOT=~/rpi-sysroot  # Or add to ~/.bashrc
./build.sh rpi

# Build specific package
./build.sh rpi -p motor_control_ros2

# Verify ARM64 output
file install_rpi/lib/*.so | grep "ARM aarch64"

# Deploy binaries (auto-detects WSL + uses Windows SSH)
./sync.sh --deploy-cross

# Update sysroot (after installing packages on RPi)
./scripts/setup_cross_compile.sh --resync --rpi-ip=192.168.137.238

# Apply patches only (includes linker symlink)
./scripts/patch_sysroot_cmake.sh
```

---

## 📚 Documentation References

- **Complete guide:** `docs/CROSS_COMPILATION_GUIDE.md`
- **Toolchain file:** `cmake/toolchains/rpi-aarch64.cmake`
- **Build script:** `build.sh` (rpi mode)
- **Setup script:** `scripts/setup_cross_compile.sh`

---

## ✅ Success Criteria

After setup, you should have:

- [x] Sysroot synced to `/media/rpi-sysroot` (~13GB)
- [x] CMake patches applied
- [x] Smoke test passed (motor_control_ros2 built for ARM64)
- [x] `./scripts/setup_cross_compile.sh --doctor` shows all green ✅

Then you can:
- ✅ Build with `./build.sh rpi` (creates ARM64 binaries)
- ✅ Deploy with `./sync.sh --deploy-cross`
- ✅ Launch on RPi instantly (already compiled!)

---

## 🎉 Next Steps After Setup

1. **Build your first cross-compiled package:**
   ```bash
   ./build.sh rpi -p yanthra_move
   ```

2. **Deploy to RPi:**
   ```bash
   ./sync.sh --deploy-cross
   ```

3. **Test on RPi:**
   ```bash
   ssh ubuntu@192.168.137.238
   cd ~/pragati_ros2
   source install/setup.bash
   ros2 run yanthra_move yanthra_move_node
   ```

4. **Enjoy faster development cycle!** 🚀

---

## 💡 Pro Tips

1. **Keep sysroot updated:** Resync monthly or after major RPi updates
2. **Use incremental builds:** Only rebuild changed packages
3. **Combine with ccache:** Already enabled in build.sh for even faster builds
4. **Build during breaks:** Start `./build.sh rpi`, grab coffee, come back to ready binaries
5. **Deploy is fast:** Binary deployment takes ~30 seconds vs ~15 min native build

---

## 🆘 Need Help?

1. **Check doctor:** `./scripts/setup_cross_compile.sh --doctor`
2. **Read full guide:** `docs/CROSS_COMPILATION_GUIDE.md`
3. **Check build logs:** `log/` directory
4. **Ask team:** Share error messages for debugging

---

**Ready to set up cross-compilation?**

1. Make sure RPi is powered on and reachable
2. Run: `./scripts/setup_cross_compile.sh --setup --rpi-ip=192.168.137.238`
3. Wait for sync to complete (~45-60 min)
4. Start building faster! 🚀
