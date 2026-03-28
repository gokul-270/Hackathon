# Build Optimization Guide

This guide explains how to use the optimized build system for the Pragati ROS2 workspace.

## Quick Start

### For Daily Development (Recommended)
```bash
./build.sh fast
```
This is the **fastest** build mode with tests disabled. Perfect for routine development work.

### For Testing and CI
```bash
./build.sh full
```
This enables all tests and examples for comprehensive validation.

### For Single Package Builds
```bash
./build.sh pkg <package_name>
```
Example: `./build.sh pkg odrive_control_ros2`

## Build Modes

| Mode | Tests | Examples | Use Case | Speed |
|------|-------|----------|----------|-------|
| `fast` | ❌ OFF | ❌ OFF | Daily development | **Fastest** |
| `full` | ✅ ON | ✅ ON | CI, testing, validation | Slower |
| `pkg <name>` | ❌ OFF | ❌ OFF | Single package dev | Fast |
| `audit` | N/A | N/A | Analyze CMake config | Instant |

## Running the Audit

To analyze your CMakeLists.txt configuration and find optimization opportunities:

```bash
./build.sh audit
```

This generates reports in `log/cmake_audit/` showing:
- Test executables outside BUILD_TESTING guards
- Optional features defaulting to ON
- Build time estimates
- Recommendations

## Enabling Specific Features

### Enable DepthAI Camera Support
```bash
./build.sh fast --cmake-args "-DHAS_DEPTHAI=ON"
```

### Enable ODrive Test Nodes
```bash
./build.sh --cmake-args "-DODRIVE_BUILD_TEST_NODES=ON"
```

### Enable All Features
```bash
./build.sh full
```

### Multiple Options
```bash
./build.sh fast --cmake-args "-DHAS_DEPTHAI=ON -DODRIVE_BUILD_TEST_NODES=ON"
```

## Build Flags Reference

### Cotton Detection (cotton_detection_ros2)
- `HAS_DEPTHAI` (default: OFF)
  - Enable OAK-D Lite camera support with DepthAI library
  - Turn OFF for faster builds when camera not needed

### ODrive Control (odrive_control_ros2)
- `BUILD_TESTING` (default: OFF)
  - Enable unit tests and gtests
- `ODRIVE_BUILD_TEST_NODES` (default: OFF)
  - Build test/debug executables (11 test nodes)
- `ODRIVE_BUILD_EXAMPLES` (default: OFF)
  - Build example code
- `BUILD_ODRIVE_LEGACY` (default: OFF)
  - Build ODrive legacy hardware support
- `ENABLE_GPIO` (default: ON)
  - Enable GPIO interface (usually needed for production)

### Global Flags (All Packages)
- `BUILD_TESTING` (default: OFF in fast mode, ON in full mode)
- `BUILD_EXAMPLES` (default: OFF in fast mode, ON in full mode)
- `BUILD_TOOLS` (default: OFF in fast mode, ON in full mode)

## Performance Optimizations

### Quick Install (Recommended)
The `install_deps.sh` script now includes ccache and ninja automatically:
```bash
./install_deps.sh
```

### Manual Install
If you prefer to install manually or already ran install_deps.sh before:

#### ccache (Highly Recommended)
```bash
sudo apt install ccache
ccache --set-config=max_size=5G
```
- **98% faster incremental rebuilds** (5.7s vs 4-5min)
- Automatically detected and enabled by build.sh
- Cache stored in `~/.ccache/` directory

#### Ninja (Recommended)
```bash
sudo apt install ninja-build
```
- **10-15% faster builds**
- Better incremental rebuild performance and parallelism
- Automatically detected and used by build.sh

## Raspberry Pi 4 Build Benchmarks (2025-10-06 Snapshot)

> These measurements come from the restoration analysis (`.restored/8ac7d2e/BUILD_OPTIMIZATION.md`) and remain the reference point until we capture a new run. They assume a Raspberry Pi 4B (4 GB RAM) running ROS 2 Jazzy.

### First Build vs Incremental

| Scenario | Command | Typical Duration | Notes |
|----------|---------|------------------|-------|
| Clean build (all packages, `-j 2`) | `./build_rpi.sh` | ~13–20 min | Heavy C++ packages dominate: `cotton_detection_ros2` (5–7 min), `odrive_control_ros2` (7–10 min), `yanthra_move` (3–5 min). |
| Incremental build (single change) | `colcon build --symlink-install --parallel-workers 2` | ~18 s | Python changes are instant with symlink install; single C++ change ~45 s. |

**Why ROS 2 feels slower at first:** ROSIDL code generation, DDS layers, and stricter C++17 builds add overhead compared to ROS 1. The payoff is dramatically faster incremental builds when you avoid `--clean`.

### Recommended Workflow on Pi

```bash
# Environment
source /opt/ros/jazzy/setup.bash

# Everyday development (keeps symlinks + 2 workers)
colcon build --symlink-install --parallel-workers 2

# Clean fallback when dependency graph changes
./build_rpi.sh --clean -j 1

# Single package rebuild (e.g. debugging vehicle_control)
colcon build --packages-select vehicle_control
```

Tips:

- Prefer `--parallel-workers 2`; `-j 4` often overwhelms memory (RAM spikes >3 GB).
- If compilation fails for memory reasons, rerun with `./build_rpi.sh -j 1` or temporarily extend swap (2 GB extra is sufficient).
- Keep `--symlink-install` enabled so Python edits propagate without rebuilds.

### Memory & Swap Guidance

| Setting | Suggested Value | Command |
|---------|-----------------|---------|
| Parallel workers | 1–2 | `./build_rpi.sh -j 2` (default) |
| Swap size (if needed) | +2 GB | `sudo dd if=/dev/zero of=/swapfile bs=1G count=2 && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` |

Monitoring: `htop` or `free -h` during the build shows whether you are approaching the 4 GB RAM limit.

### Upcoming Optimizations

1. Convert `vehicle_control` to `ament_python` to avoid unnecessary CMake steps (saves a few seconds per build).
2. Investigate precompiled headers for `yanthra_move` and `cotton_detection_ros2` to reduce clean build time by ~20%.
3. Keep ccache enabled for C++ heavy packages; total rebuild time drops by up to 80% after the cache is warm.

### Combined Effect
With both ccache and ninja installed:
- Initial clean build: ~3 min
- Typical incremental rebuild: **30-60 seconds** (3-5x faster!)

## Build Options

### Clean Build
```bash
./build.sh --clean fast
```

### Parallel Jobs
```bash
./build.sh -j 8 fast    # Use 8 parallel jobs
```

### Symlink Install (Development)
```bash
./build.sh --symlink-install fast
```
Note: `fast` and `pkg` modes enable symlink install by default.

## Troubleshooting

### Build Fails with Missing Features
If you get errors about missing camera or hardware features:

```bash
# Enable the specific feature you need
./build.sh fast --cmake-args "-DHAS_DEPTHAI=ON"
```

### Test Executables Not Found
If you need test executables:

```bash
./build.sh --cmake-args "-DODRIVE_BUILD_TEST_NODES=ON"
```

Or build everything:
```bash
./build.sh full
```

### Slow Rebuilds
1. Install ccache: `sudo apt install ccache`
2. Install ninja: `sudo apt install ninja-build`
3. Run `./build.sh fast` again

### Check Build Configuration
```bash
./build.sh audit
cat log/cmake_audit/*-analysis.md
```

## Performance Metrics

### Before Optimization
- Build time: ~4-5 minutes
- Build size: 141MB (odrive + cotton)
- Test executables: 11 built unconditionally

### After Optimization (Fast Mode)
- Build time: **2min 55s (30-40% faster)**
- Build size: **60MB (36MB saved)**
- Test executables: **0** (opt-in only)

## CI/CD Integration

### For CI Pipelines
```bash
# Use full mode to run all tests
./build.sh full -j $(nproc)
```

### For Pre-commit Checks
```bash
# Fast build to check compilation
./build.sh fast
```

### For Nightly Builds
```bash
# Clean full build with all tests
./build.sh --clean full
```

## Advanced Usage

### Custom CMake Arguments
```bash
./build.sh fast --cmake-args "-DCMAKE_BUILD_TYPE=Debug -DENABLE_COVERAGE=ON"
```

### Building Specific Packages with Dependencies
```bash
# Build package and its dependencies
colcon build --packages-up-to yanthra_move --cmake-args -DBUILD_TESTING=OFF
```

### Verbose Build Output
```bash
./build.sh fast --cmake-args "-DCMAKE_VERBOSE_MAKEFILE=ON"
```

## Files and Directories

- `build.sh` - Main build script with audit/fast/full modes
- `scripts/cmake_audit.py` - CMake configuration analyzer
- `log/cmake_audit/` - Audit reports and metrics
- `.ccache/` - Compiler cache directory (if ccache installed)

## See Also

- `log/cmake_audit/optimization_comparison.md` - Detailed optimization report
- `log/cmake_audit/*-analysis.md` - Latest audit analysis
- `./build.sh --help` - Complete command line reference

## Support

For issues or questions about the build system:
1. Run `./build.sh audit` to check configuration
2. Check `log/cmake_audit/` for detailed reports
3. Review this guide for common solutions
