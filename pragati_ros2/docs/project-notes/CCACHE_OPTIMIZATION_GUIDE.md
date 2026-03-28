# ccache Optimization Guide - Pragati ROS2
**Last Updated**: 2025-11-17  
**Current Hit Rate**: 29.66% (as of last analysis)  
**Target Hit Rate**: >60% (achievable with better workflow)

---

## Current Status

```bash
$ ccache -s
Cacheable calls:   290 / 306 (94.77%)
  Hits:             86 / 290 (29.66%) ⚠️ LOW
  Misses:          204 / 290 (70.34%)
Cache size (GB):  0.0 / 5.0 ( 0.42%)
```

**Diagnosis**: Low hit rate indicates team is doing frequent clean builds or cache invalidation.

---

## What is ccache?

ccache (Compiler Cache) speeds up rebuilds by caching compilation results. When you recompile the same source file with the same compiler flags, ccache returns the cached result instantly instead of recompiling.

**Expected Performance**:
- **First build**: No benefit (cold cache)
- **Second build**: 60-90% faster (warm cache)
- **Incremental changes**: 80-95% faster (hot cache)

**Current workspace**: Only achieving 29.66% hit rate - room for significant improvement!

---

## Why is Our Hit Rate Low?

### Root Causes

1. **Frequent clean builds** (`rm -rf build/`)
   - Invalidates CMake cache
   - Forces full recompilation
   - ccache can't help if files are "new" from CMake's perspective

2. **Build script variations**
   - Different CMAKE_ARGS between builds
   - Switching between Debug/Release modes
   - Changing optimization flags

3. **Timestamp changes**
   - Git operations (checkout, rebase) change file timestamps
   - ccache invalidates on timestamp changes

4. **Low build count**
   - Only 290 compilations total
   - Indicates team hasn't done many incremental builds yet

---

## How to Improve Hit Rate

### ✅ DO THIS (Best Practices)

#### 1. **Avoid Clean Builds Unless Necessary**

```bash
# ❌ BAD - Wipes cache benefit
rm -rf build/ install/
./build.sh fast

# ✅ GOOD - Preserves CMake and ccache state
./build.sh fast

# ✅ GOOD - Only clean if CMake is broken
colcon build --cmake-clean-cache
```

**When DO you need clean builds?**
- Switching between branches with different dependencies
- CMake cache is corrupted (weird errors)
- Testing fresh CI build

**When DON'T you need clean builds?**
- Normal code changes (99% of development)
- Adding/modifying functions
- Fixing bugs

#### 2. **Use Package-Specific Rebuilds**

```bash
# ❌ SLOW - Rebuilds everything
colcon build

# ✅ FAST - Only rebuilds what changed
./build.sh pkg yanthra_move

# ✅ FAST - Direct colcon package selection
colcon build --packages-select yanthra_move
```

**Impact**: 90% faster iteration for single-package changes

#### 3. **Keep Build Mode Consistent**

```bash
# ❌ BAD - Different flags invalidate cache
./build.sh fast         # Today
./build.sh full         # Tomorrow (different CMAKE_ARGS)

# ✅ GOOD - Stick to one mode during development
./build.sh fast         # Always use fast during iteration
./build.sh full         # Only for final testing
```

**Tip**: Use `fast` mode for development, `full` mode only before committing.

#### 4. **Preserve Workspace State**

```bash
# ❌ BAD - Nukes everything
git checkout feature-branch
rm -rf build/ install/  # <-- Unnecessary!

# ✅ GOOD - Let colcon handle rebuilds
git checkout feature-branch
./build.sh pkg <changed_package>  # Only rebuild affected packages
```

---

### Current Workspace Configuration

The workspace already has optimal ccache setup:

```bash
# From build.sh (already configured)
export CMAKE_C_COMPILER_LAUNCHER=ccache
export CMAKE_CXX_COMPILER_LAUNCHER=ccache
export CCACHE_DIR="$WORKSPACE_ROOT/.ccache"
```

**Status**: ✅ Correctly configured, just need better workflow

---

## Team Workflow Recommendations

### Daily Development Workflow

```bash
# Morning: Pull latest changes
git pull origin main

# Incremental build (preserves ccache)
./build.sh fast

# Iterate on your package
vim src/yanthra_move/src/some_file.cpp
./build.sh pkg yanthra_move  # <-- FAST with ccache

# Test your changes
source install/setup.bash
ros2 launch ...

# More iterations
vim src/yanthra_move/src/another_file.cpp
./build.sh pkg yanthra_move  # <-- Even FASTER (cache hit)
```

### Before Committing

```bash
# Full build to verify everything works
./build.sh full

# Run tests
colcon test

# Commit changes
git add ...
git commit -m "..."
```

### CI/Testing Builds Only

```bash
# Clean build (CI simulation)
rm -rf build/ install/ log/
./build.sh full
colcon test
```

---

## Monitoring ccache Performance

### Check Current Status

```bash
ccache -s
```

**What to look for**:
- **Hit rate**: Should be >60% after first few builds
- **Cache size**: Should grow to 0.5-1.0 GB for this workspace
- **Misses**: High on first build, should drop on subsequent builds

### Reset Statistics (Fresh Start)

```bash
ccache -z  # Zero statistics (doesn't delete cache)
```

Then rebuild and check:
```bash
./build.sh fast
ccache -s  # Should show baseline
./build.sh fast  # Rebuild without changes
ccache -s  # Should show 80%+ hit rate
```

### Clear Cache (Troubleshooting)

```bash
ccache -C  # Clear entire cache (last resort)
```

Only do this if:
- Cache is corrupted
- Disk space issues
- Starting fresh measurement

---

## Advanced Optimizations (Optional)

### 1. Increase Cache Size

Default is 5GB (currently using 0.42%). Can increase if needed:

```bash
# Set to 10GB
ccache --max-size=10G
```

**Not needed yet** - current usage is low.

### 2. Shared Team Cache (Advanced)

For teams sharing development machines or Docker containers:

```bash
# Set shared cache directory
export CCACHE_DIR=/shared/pragati_ros2/.ccache
chmod 777 /shared/pragati_ros2/.ccache  # Team write access
```

**Pros**: Team members share cache hits  
**Cons**: Requires shared filesystem, can have permission issues

### 3. Compression (Already Enabled)

Modern ccache enables compression by default. Verify:

```bash
ccache --show-config | grep compression
# Should show: compression = true
```

---

## Expected Results After Workflow Improvements

### Before (Current)
```
Build 1 (clean):  11 minutes
Build 2 (clean):  11 minutes  ⚠️ No benefit
Hit rate:         29.66%
```

### After (Optimized Workflow)
```
Build 1 (clean):   11 minutes
Build 2 (no changes): 2-3 minutes  ✅ 70-80% faster!
Build 3 (small change): 30 seconds  ✅ 95% faster!
Hit rate:          70%+
```

**Key Insight**: The difference is workflow, not configuration.

---

## Troubleshooting

### Q: Hit rate is still low after following guide

**A**: Check if compiler flags are changing:
```bash
# Enable debug logging
export CCACHE_DEBUG=1
./build.sh pkg yanthra_move 2>&1 | grep ccache
```

Look for "cache miss" reasons in output.

### Q: Build is slow even with high hit rate

**A**: Check what percentage of build is ccache-able:
```bash
ccache -s | grep "Cacheable calls"
```

If <90%, might have large code generation (like ROS2 IDL) that ccache can't help with.

### Q: Cache size keeps growing

**A**: Old cache entries aren't being cleaned. Check:
```bash
ccache -C  # Clear all
ccache -c  # Clean old entries (automatic cleanup)
```

---

## Quick Reference

| Task | Command | Hit Rate Impact |
|------|---------|-----------------|
| **Normal build** | `./build.sh fast` | ✅ High (preserves cache) |
| **Package rebuild** | `./build.sh pkg <name>` | ✅ Very high |
| **Clean build** | `rm -rf build/ && ./build.sh` | ❌ Zero (avoid!) |
| **Check stats** | `ccache -s` | - |
| **Reset stats** | `ccache -z` | - |
| **Clear cache** | `ccache -C` | - |

---

## Summary

### Current State
- ✅ ccache is installed and configured correctly
- ⚠️ Hit rate is low (29.66%) due to workflow
- ⚠️ Team doing too many clean builds

### Action Items

1. **Stop doing clean builds** unless absolutely necessary
2. **Use package-specific rebuilds** (`./build.sh pkg <name>`)
3. **Stick to one build mode** during development (use `fast`)
4. **Check ccache stats** weekly to ensure improvement

### Expected Improvement

Following these practices should increase hit rate from **29.66% → 70%+**, resulting in:
- **Incremental builds**: 11 min → 2-3 min (70-80% faster)
- **Single package**: 4 min → 30 sec (87% faster)
- **Small changes**: 11 min → 15 sec (98% faster)

**Bottom line**: The build system is already optimized. Focus on preserving incremental state rather than wiping it with clean builds.

---

**Document prepared**: 2025-11-17  
**ccache configuration**: ✅ Optimal  
**Improvement needed**: Workflow (not configuration)
