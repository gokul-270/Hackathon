# Raspberry Pi Benchmark Guide

## Setup Instructions

### 1. Copy Files to RPi

From your local PC, run:

```bash
# Replace with your RPi's IP and user
RPI_USER=pragati
RPI_IP=192.168.x.x
RPI_PATH=/home/pragati/pragati_ros2

# Copy benchmark script
scp benchmark_multi.sh ${RPI_USER}@${RPI_IP}:${RPI_PATH}/

# Optional: Copy entire workspace if not already there
# rsync -avz --exclude 'build' --exclude 'install' --exclude 'log' \
#   /home/uday/Downloads/pragati_ros2/ ${RPI_USER}@${RPI_IP}:${RPI_PATH}/
```

### 2. SSH into RPi

```bash
ssh ${RPI_USER}@${RPI_IP}
cd ${RPI_PATH}
```

### 3. Verify CMakeLists Changes

Check that RPi optimization detection is present:

```bash
grep -A 5 "Detect Raspberry Pi" src/cotton_detection_ros2/CMakeLists.txt
```

Should show:
```cmake
# Detect Raspberry Pi architecture
if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm" OR CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64")
    set(IS_RASPBERRY_PI TRUE)
```

### 4. Run Benchmarks

#### Test 1: Single Worker (Should Always Work)

```bash
# Make script executable
chmod +x benchmark_multi.sh

# Verify it's set to 1 worker
grep "WORKER_CONFIGS" benchmark_multi.sh
# Should show: WORKER_CONFIGS=(1)

# Run benchmark (takes ~40-60 minutes)
./benchmark_multi.sh 2>&1 | tee benchmark_rpi_1worker.log
```

**Expected Result:**
- ✅ All 5 builds should succeed
- Build time: ~6-10 minutes per build
- Should see: "✅ RPi optimizations enabled (-O2, no -march=native)"

#### Test 2: Two Workers (THE CRITICAL TEST!)

This tests if our `-O2` optimization fix prevents out-of-memory errors:

```bash
# Edit script to use 2 workers
sed -i 's/WORKER_CONFIGS=(1)/WORKER_CONFIGS=(2)/' benchmark_multi.sh

# Verify change
grep "WORKER_CONFIGS" benchmark_multi.sh
# Should show: WORKER_CONFIGS=(2)

# Run benchmark (takes ~40-60 minutes)
./benchmark_multi.sh 2>&1 | tee benchmark_rpi_2workers.log
```

**Expected Results (if our fix works):**
- ✅ All 5 builds should succeed
- Build time: ~5-8 minutes per build (faster than 1 worker)
- Memory usage should stay under 3.5GB

**If builds fail with OOM:**
- ❌ Our `-O2` fix wasn't enough
- Need to proceed with code refactoring

### 5. Monitor Progress

While benchmarks are running, you can monitor in another SSH session:

```bash
# Watch progress
tail -f benchmark_rpi_*.log

# Monitor memory usage
watch -n 5 free -h

# Check if still running
ps aux | grep benchmark_multi
```

### 6. Collect Results

After benchmarks complete:

```bash
# View summary
cat benchmarks/multi_run/SUMMARY_*.md

# Copy results back to local PC
# From local PC:
scp ${RPI_USER}@${RPI_IP}:${RPI_PATH}/benchmarks/multi_run/*.md ./benchmarks/rpi/
scp ${RPI_USER}@${RPI_IP}:${RPI_PATH}/benchmarks/multi_run/*.csv ./benchmarks/rpi/
scp ${RPI_USER}@${RPI_IP}:${RPI_PATH}/benchmark_rpi_*.log ./benchmarks/rpi/
```

## Expected Timing Ranges

Based on local PC results and RPi slower CPU:

### RPi 1 Worker (Baseline)
- Estimated: 8-12 minutes per build
- Total for 5 runs: ~50-70 minutes

### RPi 2 Workers (If Our Fix Works)
- Estimated: 6-10 minutes per build  
- Total for 5 runs: ~40-60 minutes
- **Key metric**: Should be 20-30% faster than 1 worker

### RPi 2 Workers (If Fix Doesn't Work)
- ❌ Builds will fail with OOM errors
- Will see: "c++: fatal error: Killed signal terminated program cc1plus"
- Memory will spike to 100%

## Troubleshooting

### Out of Memory During Build

If you see OOM kills even with 1 worker:

```bash
# Check swap
free -h

# Add temporary swap (2GB)
sudo dd if=/dev/zero of=/swapfile bs=1G count=2
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Verify
free -h

# Try benchmark again
```

### Build Takes Too Long

If a single build exceeds 20 minutes, something is wrong:

```bash
# Check CPU throttling
vcgencmd measure_temp
vcgencmd get_throttled

# Check if thermal throttling
# 0x0 = good, anything else = throttled
```

### Verify Optimizations Are Applied

```bash
# Check build log for optimization flags
grep "RPi optimizations\|Production optimizations" benchmark_rpi_*.log | head -5

# Should see on RPi:
# ✅ RPi optimizations enabled (-O2, no -march=native)

# Should NOT see:
# ✅ Production optimizations enabled (-O3 -march=native)
```

## Success Criteria

### ✅ Fix Is Working If:
1. 1 worker builds: All 5 succeed (expected)
2. 2 worker builds: **All 5 succeed** (this is the key test!)
3. 2 workers is 20-30% faster than 1 worker
4. Memory stays under 3.5GB during builds

### ❌ Fix Needs More Work If:
1. 2 worker builds: Any builds fail with OOM
2. Need to proceed with code refactoring (split large files)

## Next Steps After Benchmarks

Once you have results:

1. **If 2 workers succeed**: 
   - ✅ No refactoring needed!
   - Document recommended build settings
   - Update build scripts

2. **If 2 workers fail**:
   - ⚠️ Proceed with refactoring plan
   - Split `yanthra_move_system.cpp` (2,456 lines)
   - Split `cotton_detection_node.cpp` (2,182 lines)

---

## Quick Reference

```bash
# On local PC - copy to RPi
scp benchmark_multi.sh ${RPI_USER}@${RPI_IP}:${RPI_PATH}/

# On RPi - run benchmarks
cd ${RPI_PATH}
./benchmark_multi.sh  # 1 worker
sed -i 's/WORKER_CONFIGS=(1)/WORKER_CONFIGS=(2)/' benchmark_multi.sh
./benchmark_multi.sh  # 2 workers

# On local PC - get results
mkdir -p benchmarks/rpi
scp ${RPI_USER}@${RPI_IP}:${RPI_PATH}/benchmarks/multi_run/* ./benchmarks/rpi/
```
