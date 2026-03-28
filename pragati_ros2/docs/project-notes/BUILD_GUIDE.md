# Pragati ROS2 - Build Guide & Troubleshooting
**Last Updated**: 2025-11-17  
**For**: Development Team  
**Status**: Builds are working correctly, this guide helps understand expected behavior

---

## Quick Reference

### Expected Build Times

| Environment | Full Workspace | motor_control | cotton_detection | yanthra_move |
|-------------|----------------|---------------|------------------|--------------|
| **x86_64 Desktop** | ~11 min | 3min 39s | 4min 1s (2min in incremental) | 3min 20s (1min 28s incremental) |
| **Raspberry Pi 4** | ~16 min | 8min 28s | 4-5min | 4min 45s |

### Quick Build Commands

```bash
# Full clean build (use sparingly - breaks ccache benefits)
./build.sh fast

# Incremental build (preferred for development)
colcon build --parallel-workers 4

# Single package rebuild (fastest for iteration)
./build.sh pkg <package_name>
# or
colcon build --packages-select <package_name>

# Fast development build (no optimization, faster)
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug
```

---

## Understanding ROS2 Build Times

### Why ROS2 Builds Take Longer Than ROS1

**Short Answer**: ROS2 generates 5 typesupport variants for each custom message/service to support multi-language, multi-DDS interoperability.

**For motor_control_ros2** (6 services):
- 6 services × 12 files per service = **72 generated files**
- **82% of build time** is ROS IDL generation (**unavoidable**)
- Only 18% is actual C++ compilation

**What gets generated per service/message**:
1. **C typesupport** - Core ROS2/DDS interface
2. **C++ typesupport** - Application code APIs
3. **Python typesupport** - CLI tools (`ros2 topic echo`, `ros2 bag`)
4. **FastRTPS typesupport** - Network serialization
5. **Introspection typesupport** - Runtime type inspection for debugging

**Can you disable any?** 
- Theoretically: Introspection (saves 10-15%)
- **NOT RECOMMENDED** - Breaks `ros2 topic echo`, `ros2 bag record`, debugging tools

---

## Build Modes Explained

### Production Build (Default)
```bash
colcon build
```
- Optimization: `-O3 -march=native` (x86_64) or `-O2` (RPi)
- DepthAI: Enabled
- Legacy detection: Disabled (HSV/YOLO off)
- Tests: Unit tests built, test nodes OFF
- **Use for**: Final builds, deployment

### Development Build (Faster)
```bash
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug
```
- Optimization: `-Og -g3` (debug symbols)
- Build time: **30-40% faster**
- Runtime: Slower (not optimized)
- **Use for**: Active development, debugging

### Package-Specific Build
```bash
# Using existing build.sh script
./build.sh pkg yanthra_move

# Or directly with colcon
colcon build --packages-select yanthra_move --parallel-workers 4
```
- Rebuilds only specified package
- **90% faster** than full workspace
- **Use for**: Iterating on single package

---

## Configuration Options

### DepthAI (Camera) Configuration

**Current Status**: ✅ Enabled by default (as requested)

```cmake
# To disable DepthAI (NOT recommended for production):
colcon build --cmake-args -DHAS_DEPTHAI=OFF
```

**Impact**:
- Disabling saves ~2-3 minutes build time
- **Don't disable** - Camera is core functionality

### Legacy Detection (HSV/YOLO)

**Current Status**: ✅ Disabled by default (optimal)

```cmake
# To enable legacy detection for development/debugging:
colcon build --packages-select cotton_detection_ros2 \
  --cmake-args -DENABLE_LEGACY_DETECTION=ON
```

**Impact**:
- Enabling adds ~6-7 minutes to cotton_detection build
- Only enable if you need HSV or YOLO detection modes
- Production uses DepthAI direct mode exclusively

### Test Building

**Current Status**: Unit tests ON, test nodes OFF

```cmake
# Disable all tests (saves ~1 minute):
colcon build --cmake-args -DBUILD_TESTING=OFF

# Enable test node executables (adds ~2 minutes):
colcon build --packages-select motor_control_ros2 \
  --cmake-args -DBUILD_TEST_NODES=ON
```

---

## Troubleshooting Common Issues

### "Build is Stuck" - How to Tell if Build is Actually Working

**Signs build is working correctly**:
- Periodic output like `[Processing: package_name]`
- For motor_control: Can take **3-8 minutes** without output (ROS IDL generation)
- CPU usage at 80-100% (check with `htop`)

**Signs build is actually stuck**:
- No output for >10 minutes
- CPU usage near 0%
- Disk I/O at 0%

**What to do**:
```bash
# If truly stuck, kill and restart:
killall colcon
./build.sh fast
```

### Build Failures - Common Causes

#### 1. Missing pigpio Headers

**Error**: `/usr/include/pigpiod_if2.h:31:10: fatal error: pigpio.h: No such file or directory`

**Fix**:
```bash
sudo apt-get install libpigpio-dev
colcon build --packages-select yanthra_move
```

#### 2. Symlink Creation Failures

**Error**: `failed to create symbolic link: existing path cannot be removed: Is a directory`

**Fix**:
```bash
# Clean affected package
rm -rf build/motor_control_ros2 install/motor_control_ros2
colcon build --packages-select motor_control_ros2
```

#### 3. Conditional Compilation Errors

**Error**: `'YOLODetector' has not been declared`

**Status**: ✅ Fixed as of 2025-11-17

**If you see this**: Your codebase may be out of date. Pull latest changes.

#### 4. Out of Memory (OOM) on Raspberry Pi

**Symptoms**: Build killed without error message

**Fix**:
```bash
# Reduce parallel workers
colcon build --parallel-workers 2

# Or use swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## Using ccache Effectively

### What is ccache?

Compiler cache that speeds up rebuilds by caching compilation results.

### Current Status
```bash
ccache -s
# Check hit rate - should be >60% after initial builds
```

### How to Maximize ccache Benefits

**✅ DO THIS**:
```bash
# Incremental builds (preserves cache)
colcon build

# Package-specific rebuilds
./build.sh pkg motor_control_ros2
```

**❌ DON'T DO THIS** (unless necessary):
```bash
# Clean builds (nukes ccache benefits)
rm -rf build/ install/
colcon build
```

### Best Practices

1. **Avoid `rm -rf build/`** unless absolutely necessary
2. **Use `--cmake-clean-cache`** instead for CMake issues:
   ```bash
   colcon build --cmake-clean-cache
   ```
3. **Share ccache** across team (optional):
   ```bash
   export CCACHE_DIR=/shared/ccache
   ```

---

## Optimization History

### Recent Improvements (2025-11)

| Optimization | Benefit | Status |
|--------------|---------|--------|
| **Legacy detection made optional** | -6min cotton_detection | ✅ Applied |
| **Removed MoveIt from yanthra_move** | -30s yanthra_move | ✅ Applied Nov 17 |
| **Fixed unused parameter warning** | Cleaner build output | ✅ Applied Nov 17 |
| **Modularized yanthra_move** | -84% incremental builds | ✅ Applied (prior) |

### Build Time Trend

- **Before optimizations**: 18-20 minutes (RPi)
- **After legacy detection OFF**: 15-16 minutes (RPi)
- **After MoveIt removal**: ~15 minutes (RPi), ~10-11 minutes (x86_64)

---

## Incremental Build Performance

### yanthra_move Example

| Build Type | Before Modularization | After Modularization |
|------------|----------------------|----------------------|
| **Clean build** | ~5 minutes | ~3-4 minutes |
| **Incremental** | ~90 seconds | ~14 seconds ✅ |
| **Improvement** | - | **84% faster** |

**Lesson**: Modular code = faster iteration!

---

## When to Use Clean Builds

### ✅ Clean Build Needed When:
- Switching between branches with different dependencies
- CMake cache is corrupted (weird errors)
- Testing fresh build for CI/release

### ❌ Clean Build NOT Needed When:
- Changing source code (.cpp, .py files)
- Adding/modifying functions in existing files
- Tweaking parameters or config files
- Most normal development work

**Rule of Thumb**: If in doubt, try incremental build first. Only clean if that fails.

---

## Build Performance Comparison

### motor_control_ros2 Breakdown

| Component | Time | % of Total | Can Optimize? |
|-----------|------|------------|---------------|
| **ROS2 IDL generation** | ~3 minutes | 82% | ❌ NO - Fundamental to ROS2 |
| **C++ compilation** | ~30 seconds | 14% | ⚠️ MAYBE - Use ccache |
| **Linking** | ~10 seconds | 4% | ✅ YES - Already optimal |

**Conclusion**: 82% of motor_control build time is unavoidable ROS2 overhead.

---

## Team Workflow Recommendations

### For Active Development

```bash
# 1. First build of the day (if code pulled)
colcon build --parallel-workers 4

# 2. Iterating on single package
./build.sh pkg cotton_detection_ros2

# 3. Quick test
colcon build --packages-select cotton_detection_ros2

# 4. Before committing
colcon build  # Full workspace incremental
colcon test   # Run tests
```

### For Testing/CI

```bash
# Clean build to verify from scratch
rm -rf build/ install/ log/
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release
colcon test
```

---

## FAQ

### Q: Why does motor_control take 3-8 minutes to build?

**A**: 82% of that time is ROS2 generating 72 typesupport files for 6 custom services. This is fundamental to ROS2's design and cannot be avoided.

### Q: Can I disable some typesupport variants to speed up builds?

**A**: Technically yes (introspection types), but **NOT RECOMMENDED**. You'll lose `ros2 topic echo`, `ros2 bag record`, and debugging capabilities. The 10-15% speedup isn't worth it.

### Q: Why did builds suddenly get slow?

**A**: Check if you're doing clean builds (`rm -rf build/`). This wipes ccache and makes every build slow. Use incremental builds instead.

### Q: How do I know if ccache is working?

**A**: 
```bash
ccache -s | grep "cache hit rate"
# Should show >60% after a few builds
```

### Q: Should I use Ninja or Make?

**A**: Ninja is automatically used if installed (10-20% faster). Already configured in `build.sh`.

### Q: What's the fastest way to iterate on code?

**A**: 
1. Use Debug builds during development (`-DCMAKE_BUILD_TYPE=Debug`)
2. Rebuild only the package you're changing (`./build.sh pkg <name>`)
3. Don't clean builds unless necessary

---

## Getting Help

### Build Issues Checklist

1. **Check dependencies**:
   ```bash
   rosdep install --from-paths src --ignore-src -r -y
   ```

2. **Verify pigpio installed**:
   ```bash
   dpkg -l | grep libpigpio-dev
   ```

3. **Check ccache**:
   ```bash
   ccache -s
   ```

4. **Try package-specific build**:
   ```bash
   colcon build --packages-select <failing_package>
   ```

5. **Last resort - clean build**:
   ```bash
   rm -rf build/ install/ log/
   colcon build
   ```

### Still Having Issues?

Check these documents:
- `BUILD_OPTIMIZATION_PLAN_2025-11-16.md` - Detailed build analysis
- `CLEAN_BUILD_RESULTS_2025-11-17.md` - Latest build results and analysis
- `BUILD_TIME_AUDIT_2025-11-15.md` - Why builds take the time they do

---

## Summary

### Key Takeaways

1. ✅ **Builds are working correctly** - Not bloated, times are expected for ROS2
2. ✅ **Most build time is ROS2 overhead** - 60-70% is interface generation (unavoidable)
3. ✅ **Use incremental builds** - Preserve ccache benefits
4. ✅ **Package-specific rebuilds** - 90% faster for iteration
5. ✅ **Code quality is excellent** - Only 1 warning in entire workspace

### What Changed (Nov 2025)

- ✅ Legacy detection made optional (saves 6+ minutes)
- ✅ MoveIt dependencies removed from yanthra_move (saves ~30s)
- ✅ Unused parameter warning fixed (cleaner output)
- ✅ Build system fully optimized

**Bottom Line**: Focus on features, not build optimization. The build system is already optimal for ROS2.

---

**Document prepared**: 2025-11-17  
**Build system status**: ✅ Optimal  
**Next review**: When team reports new build issues
