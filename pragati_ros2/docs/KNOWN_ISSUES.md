# Known Issues

## DepthAI USB Warnings on Shutdown (HARMLESS)

**Status**: Known Issue - Harmless  
**Severity**: Low (cosmetic only)  
**Date**: 2025-11-02

### Symptoms

When shutting down the cotton detection node (Ctrl+C), you may see USB-related error messages:

```
F: [global] [EventRead00Thr] usbPlatformRead:999 Cannot find file descriptor by key: 55
F: [global] [Scheduler00Thr] usbPlatformWrite:1055 Cannot find file descriptor by key: 55
F: [global] [Scheduler00Thr] usbPlatformClose:893 Cannot find USB Handle by key: 55
```

### Root Cause

This is a **race condition in the DepthAI C++ library** (libdepthai) between:
1. ROS2 shutdown calling `device_->close()`
2. DepthAI's internal USB reader/scheduler threads still running

The DepthAI library's internal threads don't immediately stop when `close()` is called, and they attempt to access the already-closed USB file descriptor.

### Impact

**NONE** - These messages are harmless:
- ✅ Node exits cleanly ("process has finished cleanly")
- ✅ No resource leaks
- ✅ No crashes or hangs
- ✅ Detection functionality unaffected (3-9 detections in 128-133ms)
- ✅ Next launch works perfectly

The messages are **stderr output from DepthAI's XLink USB layer**, not errors from our code.

### Why Can't We Fix It?

The issue is **inside libdepthai.so**, which we don't control. We've implemented best-practice shutdown:
1. Drain all queues
2. Call `device_->close()`
3. Wait 200ms for threads to stop
4. Reset queue pointers
5. Reset device pointer
6. Final 100ms wait

But DepthAI's threads are not joinable/controllable from our code.

### Upstream

This is a **known issue** in the DepthAI library:
- https://github.com/luxonis/depthai-core/issues (search "shutdown")
- Related to XLink USB library thread management

### Workaround

If the stderr spam is problematic for logs, redirect stderr during shutdown:

```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py 2>/dev/null
```

But this is **not recommended** as it hides real errors.

### Recommendation

**Ignore these messages.** They are harmless library internals and don't indicate any problem with your system.

---

## Summary

| Issue | Severity | Impact | Fix Available |
|-------|----------|--------|---------------|
| DepthAI USB shutdown warnings | Low (cosmetic) | None | No (upstream library issue) |
| RPi Native Build OOM | High | Build fails | Yes (see below) |

---

## RPi Native Build Fails with OOM (Out of Memory)

**Status**: Known Issue - Workarounds Available  
**Severity**: High  
**Date**: 2025-12-31

### Symptoms

When building `cotton_detection_ros2` natively on Raspberry Pi, the build fails with:
- SSH connection drops/hangs
- `Killed` message during compilation
- `g++: fatal error: Killed signal terminated program cc1plus`
- System becomes unresponsive

### Root Cause

The `cotton_detection_ros2` package is extremely memory-intensive due to:
1. **DepthAI headers** - Heavy template metaprogramming, ~2GB RAM per compiler instance
2. **depthai_manager.cpp** - 2000 lines with complex DepthAI pipeline setup
3. **RPi 4 RAM limitations** - Only 4GB or 8GB total
4. **No swap by default** - Ubuntu on RPi often has no swap configured

### Solutions

#### Option 1: Let build.sh Setup Swap Automatically (Easiest)
Just run the build - the script will detect insufficient memory and offer to setup swap:
```bash
./build.sh arm

# Script will prompt:
# "Would you like to setup 4GB swap automatically? [y/N]:"
# Answer 'y' and it will configure swap, then continue building
```

#### Option 2: Use Cross-Compilation (Fastest)
Build on your x86 machine and deploy to RPi:
```bash
# On x86 machine
./build.sh rpi

# Deploy to RPi
rsync -avz install_rpi/ ubuntu@<RPI_IP>:~/pragati_ros2/install/
```
See [CROSS_COMPILATION_GUIDE.md](CROSS_COMPILATION_GUIDE.md) for details.

#### Option 3: Manual Swap Setup
```bash
# On RPi - create permanent 4GB swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Then build
./build.sh arm
```

### Prevention

The `build.sh` script now:
- Checks disk space and memory BEFORE building
- Requires 3GB+ available (RAM + swap), 4GB+ on RPi
- **Offers to setup swap automatically** if memory is insufficient
- Defaults to `-j1` on RPi (auto-detected)
- Use `--skip-checks` to bypass (NOT recommended - may crash)

### Build Time Expectations

| Build Method | Time | Memory Required |
|--------------|------|-----------------|
| Cross-compile (x86) | ~5 min | 8GB+ (shared) |
| Native RPi with swap | ~15-20 min | 4GB RAM + 4GB swap |
| Native RPi no swap | BLOCKED by build.sh | N/A |
