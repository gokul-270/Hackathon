# Cotton Detection Build Optimization Analysis
**Date:** 2025-11-27
**Package:** cotton_detection_ros2
**Build Log:** BUILD_LOG_COTTON_DETECTION_2025-11-27.txt

## Current Build Time
- **Total:** ~3min 20s (x86_64 dev machine)
- **Note:** RPi builds are significantly slower due to limited RAM and CPU

## O2 vs O3 Optimization Levels
| Flag | Description | Trade-off |
|------|-------------|-----------|
| `-O2` | Standard optimization | Faster compile, good runtime performance |
| `-O3` | Aggressive optimization | Slower compile, max runtime performance |

Current CMakeLists uses `-O3` for Release builds. For RPi with limited resources, `-O2` may be better.

## Per-File Compile Time Analysis

### Slowest Files (Wall Clock)
| File | Time | Memory | Issue |
|------|------|--------|-------|
| `depthai_manager.cpp` | 26.09s | 1896MB | Heavy DepthAI + OpenCV headers |
| `cotton_detection_node_parameters.cpp` | 33.08s | 1499MB | Heavy template instantiation |
| `performance_monitor.cpp` | 15.28s | 863MB | ROS2 templates |
| `cotton_detection_node_callbacks.cpp` | 14.29s | 860MB | OpenCV + ROS2 headers |
| `cotton_detection_node_detection.cpp` | 14.21s | 840MB | DepthAI types |
| `cotton_detection_node_publishing.cpp` | 14.07s | 906MB | ROS2 message types |
| `cotton_detection_node.cpp` | 11.87s | 708MB | Base node includes |
| `cotton_detection_node_main.cpp` | 11.22s | 835MB | Entry point |

### Fast Files (< 5s)
- `async_image_saver.cpp`: 4.84s
- ROSIDL generated files: 0.1-3s each

## Key Bottlenecks

1. **Template Instantiation** (35-55% of compile time)
   - ROS2 node templates
   - DepthAI queue types
   - OpenCV operations

2. **Header Parsing** (50-75% of total time)
   - `depthai/depthai.hpp` (umbrella header)
   - `opencv2/opencv.hpp` (umbrella header)
   - `rclcpp/rclcpp.hpp`

3. **Memory Usage**
   - Peak: ~1.9GB for depthai_manager.cpp
   - RPi4 (4GB) struggles with this

## Optimization Recommendations

### Quick Wins (Low Risk)
1. **Use Ninja + ccache locally**
   ```bash
   colcon build --cmake-args -GNinja -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
   ```

2. **Reduce optimization for dev builds**
   ```bash
   colcon build --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo
   ```

### Medium Effort
3. **Narrow includes in depthai_manager.cpp**
   - Replace `#include <depthai/depthai.hpp>` with specific headers
   - Replace `#include <opencv2/opencv.hpp>` with needed modules only

4. **Add Precompiled Headers (PCH)**
   ```cmake
   target_precompile_headers(cotton_detection_node PRIVATE
     <rclcpp/rclcpp.hpp>
     <opencv2/core.hpp>
   )
   ```

### For RPi Builds
5. **Limit parallel jobs**
   ```bash
   colcon build --parallel-workers 1 --executor sequential
   ```

6. **Use swap space** if memory runs out

7. **Cross-compile on x86** and deploy to RPi

## Files Already Optimized
- Forward declarations for OpenCV types in `cotton_detection_node.hpp`
- PIMPL pattern in `DepthAIManager` to hide heavy includes
- Split node into multiple .cpp files for parallel compilation

## Future TODO
- [ ] Implement PCH for common headers
- [ ] Narrow umbrella includes in source files
- [ ] Test build on RPi and document actual times
- [ ] Consider cross-compilation setup
