# Build System Documentation

## Overview

The pragati_ros2 build system is configured for production robotics deployment with optimized compilation flags, flexible configuration presets, and comprehensive testing support.

## Quick Start

### Production Build (Recommended for Deployment)
```bash
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release -DHAS_DEPTHAI=ON
```

### Simulation Build (No Hardware)
```bash
colcon build --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DHAS_DEPTHAI=OFF -DENABLE_GPIO=OFF
```

### Debug Build (Development)
```bash
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug -DBUILD_TEST_NODES=ON
```

## CMake Presets

The project includes `CMakePresets.json` for standardized build configurations:

### Available Presets

1. **production** - Optimized for deployment
   - Release build (-O3 -march=native)
   - DepthAI and GPIO enabled
   - Tests disabled

2. **simulation** - For testing without hardware
   - RelWithDebInfo build
   - Hardware features disabled
   - Unit tests enabled

3. **debug** - Full debugging support
   - Debug build (-Og -g3)
   - All test nodes enabled
   - Hardware features disabled

4. **testing** - Comprehensive testing
   - RelWithDebInfo build
   - All tests and test nodes enabled
   - All hardware features enabled

### Using Presets (with CMake 3.23+)
```bash
# Configure with preset
cmake --preset production

# Build with preset
cmake --build --preset production

# Run tests
ctest --preset testing
```

## Build Configuration Options

### Core Options

| Option | Default | Description |
|--------|---------|-------------|
| `CMAKE_BUILD_TYPE` | `RelWithDebInfo` | Build type: Release, RelWithDebInfo, Debug |
| `HAS_DEPTHAI` | `ON` | Enable OAK-D Lite camera support |
| `ENABLE_GPIO` | `ON` | Enable GPIO support (pigpio/sysfs) |
| `BUILD_TESTING` | `ON` | Build unit tests |
| `BUILD_TEST_NODES` | `OFF` | Build test executables |

### Optimization Flags

**Release/RelWithDebInfo builds automatically enable:**
- `-O3` - Maximum optimization
- `-march=native` - CPU-specific optimizations
- `-DNDEBUG` - Disable assertions

**Debug builds enable:**
- `-Og` - Debug-friendly optimization
- `-g3` - Maximum debug symbols

## Package-Specific Features

### motor_control_ros2

**GPIO Support Options:**
```bash
# With pigpio (Raspberry Pi)
colcon build --cmake-args -DENABLE_GPIO=ON

# Without GPIO (development)
colcon build --cmake-args -DENABLE_GPIO=OFF
```

**GPIO Fallback Chain:**
1. `pigpio` library (best - hardware PWM)
2. `pigpiod_if2` daemon interface
3. `sysfs` (fallback - standard Linux)

**Test Nodes:**
```bash
# Enable all test executables
colcon build --cmake-args -DBUILD_TEST_NODES=ON
```

### cotton_detection_ros2

**DepthAI Configuration:**
```bash
# With OAK-D Lite camera
colcon build --cmake-args -DHAS_DEPTHAI=ON

# Without camera (simulation)
colcon build --cmake-args -DHAS_DEPTHAI=OFF
```

**Model Installation:**
Models are installed from `data/models/`:
- `yolov8v2.blob` (primary)
- `yolov8.blob` (fallback)
- `best_openvino_2022.1_6shave.blob` (legacy)

### yanthra_move

**pigpio Support:**
```bash
# Enable pigpio for GPIO control
colcon build --cmake-args -DENABLE_PIGPIO=ON
```

## Testing

### Running Unit Tests
```bash
# Build with tests
colcon build --cmake-args -DBUILD_TESTING=ON

# Run all tests
colcon test

# Run specific package tests
colcon test --packages-select motor_control_ros2

# View test results
colcon test-result --verbose
```

### Available Test Suites

#### motor_control_ros2
- `motor_control_protocol_tests` - CAN protocol encoding/decoding
- `motor_control_safety_tests` - Safety monitor validation
- `motor_control_parameter_tests` - Parameter validation
- `motor_control_can_tests` - CAN interface tests

#### cotton_detection_ros2
- `cotton_detection_unit_tests` - Detection pipeline tests

#### yanthra_move
- `yanthra_move_coordinate_tests` - Coordinate transformation tests

### Test Executables (Development Only)

Enable with `-DBUILD_TEST_NODES=ON`:
- `basic_service_test` - ROS2 service fundamentals
- `gpio_test` - GPIO functionality
- `test_safety_monitor` - Safety system validation
- `mg6010_test_node` - Motor controller testing

## Code Quality

### clang-tidy Integration

The project includes `.clang-tidy` configuration:

```bash
# Generate compile_commands.json
colcon build --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Run clang-tidy on specific file
clang-tidy -p build/compile_commands.json src/path/to/file.cpp

# Run on entire package
find src/motor_control_ros2/src -name "*.cpp" -exec clang-tidy -p build {} \;
```

**Enabled Checks:**
- `bugprone-*` - Bug detection
- `performance-*` - Performance optimizations
- `readability-*` - Code readability
- `modernize-*` - Modern C++ features
- `cppcoreguidelines-*` - Core Guidelines

## Installation Layout

### Headers
```
install/
  <package>/
    include/
      <package>/
        *.hpp
```

### Libraries
```
install/
  <package>/
    lib/
      lib<package>*.so
```

### Executables
```
install/
  <package>/
    lib/<package>/
      <executable>
```

### Configuration
```
install/
  <package>/
    share/<package>/
      config/
      launch/
      models/  (cotton_detection only)
```

## Build System Architecture

### Packages Overview

```
pragati_ros2/
├── common_utils/          # Shared Python utilities
├── cotton_detection_ros2/ # Vision system (C++/Python)
├── motor_control_ros2/    # Motor control (C++/Python)
├── pattern_finder/        # ArUco detection (C++)
├── robot_description/     # URDF and meshes
├── vehicle_control/       # Navigation (Python)
└── yanthra_move/          # Motion planning (C++)
```

### Dependencies Graph

```
yanthra_move
├── motor_control_ros2
├── cotton_detection_ros2
└── robot_description

cotton_detection_ros2
├── depthai (optional)
└── OpenCV

motor_control_ros2
└── pigpio (optional)
```

## Performance Considerations

### Optimization Impact

| Build Type | Optimization | Binary Size | Performance | Debug |
|------------|--------------|-------------|-------------|-------|
| Release | -O3 -march=native | Smaller | ~30% faster | No |
| RelWithDebInfo | -O3 -march=native -g | Larger | ~30% faster | Yes |
| Debug | -Og -g3 | Larger | Baseline | Full |

### Hardware-Specific Optimizations

`-march=native` enables CPU-specific instructions:
- SIMD vectorization (SSE, AVX)
- Hardware accelerated operations
- Better instruction pipelining

**Note:** Binaries are **not portable** across different CPU architectures.

### Cross-Compilation

For deployment on different hardware:
```bash
# Remove -march=native for portability
colcon build --cmake-args \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-O3 -DNDEBUG"
```

## Troubleshooting

### Common Build Issues

#### DepthAI Not Found
```bash
# Install DepthAI
sudo apt install ros-humble-depthai ros-humble-depthai-bridge

# Or disable for simulation
colcon build --cmake-args -DHAS_DEPTHAI=OFF
```

#### GPIO Library Missing
```bash
# Install pigpio
sudo apt install libpigpio-dev pigpio

# Or use sysfs fallback (automatic)
```

#### GTest Not Found
```bash
# Install GTest
sudo apt install libgtest-dev

# Or disable tests
colcon build --cmake-args -DBUILD_TESTING=OFF
```

### Build Warnings

Most warnings are suppressed for legacy code integration. To see all warnings:
```bash
export COLCON_LOG_LEVEL=warning
colcon build 2>&1 | grep "warning:"
```

## Migration Notes

### From ROS1 to ROS2
- All packages migrated to ament_cmake
- Service interfaces regenerated for ROS2
- Legacy lint suites disabled (marked with FOUND=TRUE)

### Build System Evolution
- **Phase 1 (Complete):** Optimization flags, header installation
- **Phase 2 (Future):** CMake modularization, config consolidation
- **Phase 3 (Complete):** CMakePresets.json, clang-tidy integration

## References

- [ROS2 Build System](https://docs.ros.org/en/humble/Tutorials/Beginner-Client-Libraries/Colcon-Tutorial.html)
- [CMake Presets](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html)
- [ament_cmake Documentation](https://docs.ros.org/en/humble/How-To-Guides/Ament-CMake-Documentation.html)
- [GCC Optimization Options](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html)

## Change Log

### 2025-11-01
- ✅ Added optimization flags to all CMakeLists.txt
- ✅ Added header installation rules
- ✅ Created CMakePresets.json
- ✅ Added .clang-tidy configuration
- ✅ Verified DepthAI dependency configuration
- ✅ Completed production build verification

---

*Last updated: 2025-11-01*
*Build system version: 2.0*
