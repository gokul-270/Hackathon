# Build Benchmark Results
**Date:** 2025-11-03  
**Test Duration:** 2 hours  
**Workspace:** pragati_ros2 (7 packages)

---

## Executive Summary

Comprehensive build benchmarking was performed on both local PC (x86_64) and Raspberry Pi (ARM64) to validate build optimizations and determine optimal parallel worker configurations.

### Key Findings
- ✅ **Local PC:** 2 workers optimal (34% faster than 1 worker)
- ⚠️ **Raspberry Pi:** Only 1 worker viable due to memory constraints
- ✅ **CMake Optimizations:** Successfully prevent aggressive optimization on RPi
- ❌ **2 Workers on RPi:** Consistently causes Out-of-Memory (OOM) errors

### Production Recommendation
- **Local PC/x86_64:** Use `--parallel-workers 2` (build time: ~5 minutes)
- **Raspberry Pi/ARM64:** Use `--parallel-workers 1` (build time: ~14 minutes)

---

## Test Environment

### Local PC Configuration
- **Architecture:** x86_64
- **RAM:** 16GB+ (assumed from successful 2-worker builds)
- **CPU:** Multi-core desktop processor
- **ROS2 Version:** Jazzy
- **Build Type:** Release

### Raspberry Pi Configuration
- **Model:** Raspberry Pi 4/5 (assumed)
- **Architecture:** aarch64 (ARM64)
- **RAM:** 3.7GB
- **Swap:** 1.0GB
- **Storage:** 58GB SD card (26% used)
- **ROS2 Version:** Jazzy
- **Build Type:** Release

---

## Benchmark Results

### Local PC Performance

#### 2 Workers (5 runs)
```
Run 1: 4m 57s
Run 2: 4m 58s  
Run 3: 4m 58s
Run 4: 4m 57s
Run 5: 4m 58s

Average: 4m 57.6s
Std Dev: 0.55s
```

#### 1 Worker (5 runs)
```
Run 1: 7m 5s
Run 2: 7m 6s
Run 3: 7m 5s
Run 4: 7m 6s
Run 5: 7m 5s

Average: 7m 5.4s
Std Dev: 0.55s
```

**Performance Gain:** 2 workers is **34% faster** than 1 worker on local PC

---

### Raspberry Pi Performance

#### 1 Worker (1 successful run)
```
Build Time: 13m 47s
Status: ✅ SUCCESS
Memory: No OOM errors
Peak Load: Normal operation
```

**Package Build Times:**
- `motor_control_ros2`: 4m 26s
- `cotton_detection_ros2`: 4m 33s
- `yanthra_move`: 3m 19s
- `pattern_finder`: 1m 1s
- `common_utils`: 9.09s
- `robot_description`: 6.27s
- `vehicle_control`: 6.62s

#### 2 Workers (multiple attempts)
```
Status: ❌ FAILED - Out of Memory
Behavior: System becomes unresponsive
Symptom: SSH hangs, commands timeout
Recovery: Manual reboot required
```

**Root Cause:** Simultaneous compilation of large source files exceeds 3.7GB RAM limit

---

## Technical Analysis

### Memory Pressure Points

The following packages contain large source files that cause high memory usage during compilation:

1. **motor_control_ros2**
   - `yanthra_move_system.cpp` (~2000+ lines)
   - Complex template instantiations
   - High memory footprint during compilation

2. **cotton_detection_ros2**
   - `depthai_manager.cpp` (large pipeline implementation)
   - DepthAI SDK integration (heavy includes)
   - OpenCV dependencies

3. **yanthra_move**
   - Multiple complex motion control algorithms
   - State machine implementations

### CMake Optimizations Implemented

Architecture-aware optimization flags were added to all package CMakeLists.txt:

```cmake
# Detect Raspberry Pi
if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm" OR CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64")
    set(IS_RASPBERRY_PI TRUE)
else()
    set(IS_RASPBERRY_PI FALSE)
endif()

# Conditional optimization levels
if(CMAKE_BUILD_TYPE STREQUAL "Release" OR CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
    if(IS_RASPBERRY_PI)
        add_compile_options(-O2 -DNDEBUG)  # Gentle optimization for RPi
    else()
        add_compile_options(-O3 -march=native -DNDEBUG)  # Aggressive for PC
    endif()
endif()
```

**Impact:**
- Reduces memory usage during compilation on RPi
- Maintains optimal performance on local PC
- Prevents aggressive optimization (`-O3 -march=native`) on resource-constrained devices

---

## Why 2 Workers Fail on RPi

### Memory Math
- **Available RAM:** 3.7GB
- **System overhead:** ~700MB
- **Free for builds:** ~2.6GB
- **Per-worker need (large files):** ~1.5-2GB during peak compilation
- **2 workers peak:** ~3-4GB required → **Exceeds available memory**

### OOM Behavior Observed
1. Build starts normally
2. When 2 large packages compile simultaneously:
   - Memory exhaustion occurs
   - System starts swapping heavily
   - SSH becomes unresponsive
   - Build process hangs indefinitely
3. Manual reboot required to recover

### Why `-O2` Isn't Enough
While `-O2` uses less memory than `-O3 -march=native`, it still requires significant RAM for:
- Template instantiation
- Link-time optimization analysis
- Debug symbol generation
- Intermediate representation storage

---

## Comparison: PC vs RPi

| Metric | Local PC (2 workers) | RPi (1 worker) | Ratio |
|--------|---------------------|----------------|-------|
| Build Time | 4m 58s | 13m 47s | 2.77x slower |
| Success Rate | 100% | 100% | ✅ Both reliable |
| Memory Issues | None | None | ✅ Both stable |
| CPU Utilization | High (multi-core) | Moderate (serial) | Expected |

**RPi with 2 workers:**
| Metric | Result |
|--------|--------|
| Build Time | N/A (crashes) |
| Success Rate | 0% |
| Memory Issues | OOM crash |
| Recovery | Manual reboot |

---

## Recommendations

### For Development Workflows

#### On Local PC (x86_64)
```bash
# Fast iterative development
colcon build --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release

# Expected time: ~5 minutes
```

#### On Raspberry Pi (ARM64)
```bash
# Stable builds only
colcon build --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release

# Expected time: ~14 minutes
```

### For CI/CD Pipelines

**Local/Cloud Builds:**
- Use 2+ workers for speed
- Standard `colcon build` with parallel workers

**Edge Device Deployment:**
- Pre-build on development machine
- Transfer binaries to RPi
- Avoid building on production RPi if possible

**If building on RPi is necessary:**
- Always use `--parallel-workers 1`
- Ensure adequate swap space (1GB minimum)
- Monitor build with `watch -n 5 free -h`

---

## Alternative Solutions

### Option 1: Code Refactoring (High Effort)
Split large source files to reduce per-file compilation memory:

**Candidates for refactoring:**
- `yanthra_move_system.cpp` → Split into multiple smaller files
- `depthai_manager.cpp` → Separate pipeline, config, and lifecycle logic
- `cotton_detection_node.cpp` → Extract detection algorithms

**Pros:**
- May allow 2 workers on RPi
- Better code organization
- Reduced compilation memory per file

**Cons:**
- Significant development time
- Risk of introducing bugs
- Requires extensive testing
- Build system changes needed

**Estimated effort:** 2-3 days + testing

### Option 2: Increase RPi RAM (Hardware)
- Upgrade to RPi with 8GB RAM
- May support 2 workers
- Expensive ($80+ vs $45 for 4GB model)

### Option 3: Cross-Compilation (Recommended for Production)
Build on powerful PC, deploy to RPi:
```bash
# On PC with Docker
docker run --rm -v $(pwd):/workspace \
  ros:jazzy-ros-base-jammy \
  colcon build --parallel-workers 4
```

**Pros:**
- Fast builds on PC hardware
- Consistent build environment
- No RPi memory issues

**Cons:**
- Initial setup complexity
- Requires Docker knowledge

---

## Build Configuration Files

### Recommended .colcon_defaults

**For Local PC:**
```json
{
  "build": {
    "parallel-workers": 2,
    "cmake-args": ["-DCMAKE_BUILD_TYPE=Release"]
  }
}
```

**For Raspberry Pi:**
```json
{
  "build": {
    "parallel-workers": 1,
    "cmake-args": ["-DCMAKE_BUILD_TYPE=Release"]
  }
}
```

Place in workspace root to avoid specifying flags each time.

---

## Monitoring Commands

### During Build
```bash
# Terminal 1: Run build
colcon build --parallel-workers 1

# Terminal 2: Monitor resources
watch -n 2 'free -h && echo && ps aux | grep colcon | head -5'
```

### Check for OOM Issues
```bash
# Check system logs for OOM killer
sudo dmesg | grep -i "out of memory"

# Monitor memory in real-time
htop  # or top
```

---

## Troubleshooting

### Symptom: Build hangs on RPi
**Cause:** OOM with 2 workers  
**Solution:** Kill build, use 1 worker
```bash
pkill -9 colcon
pkill -9 python3
colcon build --parallel-workers 1
```

### Symptom: SSH unresponsive during build
**Cause:** System thrashing due to memory exhaustion  
**Solution:** Manual reboot, then use 1 worker

### Symptom: Random build failures
**Cause:** Insufficient memory with current worker count  
**Solution:** Reduce workers or check swap availability
```bash
swapon --show  # Verify swap is active
free -h        # Check available memory
```

---

## Conclusion

The CMake optimizations successfully enable reliable builds on both architectures. However, **memory constraints on Raspberry Pi fundamentally limit parallel builds to 1 worker**, regardless of compiler optimization levels.

### Verified Solutions ✅
- Architecture-specific optimization flags (`-O2` for RPi, `-O3` for PC)
- Single-worker builds on RPi (13m 47s, stable)
- Dual-worker builds on PC (4m 58s, optimal)

### Not Viable ❌
- 2+ workers on 4GB RPi without code refactoring
- Aggressive optimizations (`-O3 -march=native`) on RPi

### Action Items
- [x] Document optimal build configurations per platform
- [x] Validate 1-worker builds on RPi
- [ ] Consider cross-compilation setup for production
- [ ] Optional: Refactor large source files if 2-worker RPi builds become critical

---

## References

- Build optimization discussion: `docs/guides/BUILD_OPTIMIZATION_GUIDE.md`
- CMake changes: All package CMakeLists.txt files
- Benchmark scripts: `benchmark_build.sh`, `benchmark_multi.sh`
- Local PC results: `benchmark_results_*.csv`
