# Performance Optimization Guide

**Last Updated:** 2025-11-04  
**Consolidated From:** PERFORMANCE_CHECKLIST.md, PERFORMANCE_OPTIMIZATION_IMPLEMENTATION.md, COTTON_DETECTION_OOM_FIX_PLAN.md, THERMAL_OPTIMIZATION_SUMMARY.md, THERMAL_SOLUTION_SUMMARY.md  
**Status:** Production Ready (as of 2025-11-01)

---

## Overview

This guide consolidates tactical quick-wins and strategic implementation details for optimizing the Pragati ROS2 system. Focus areas include build performance, control loop timing, vision pipeline throughput, and memory efficiency.

---

## Quick Wins (< 1 hour each)

### Build System

- [x] **Enable ccache** - 98% faster rebuilds
  ```bash
  sudo apt install ccache
  export CC="/usr/bin/ccache gcc"
  export CXX="/usr/bin/ccache g++"
  colcon build
  ```
- [ ] **Parallel builds** - Use all cores
  ```bash
  colcon build --parallel-workers $(nproc)
  ```
- [ ] **Link-time optimization** - Add `-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON`

### Logging

- [ ] **Remove debug logs from hot paths** - Check detection loop, control loop
- [ ] **Use RCLCPP_DEBUG_THROTTLE** instead of RCLCPP_DEBUG in loops
- [ ] **Disable console output** in production: `output="log"` in launch files

### Memory Allocation

- [ ] **Pre-allocate message buffers**
  ```cpp
  // Instead of creating new messages in callback
  detection_msg_.detections.reserve(100);
  detection_msg_.detections.clear();  // Reuse buffer
  ```
- [ ] **Reuse cv::Mat** - Avoid reallocating image buffers
  ```cpp
  cv::Mat image_buffer_;  // Member variable
  // Reuse in callback instead of creating new
  ```

### ROS2 Middleware

- [ ] **Switch to CycloneDDS** - Lower latency than FastDDS
  ```bash
  sudo apt install ros-humble-rmw-cyclonedds-cpp
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  ```
- [ ] **Configure QoS properly**
  ```cpp
  auto qos = rclcpp::QoS(rclcpp::KeepLast(1))
             .best_effort()  // For sensors
             .durability_volatile();
  ```

---

## CycloneDDS Configuration (Detailed)

### Why CycloneDDS?

Superior performance compared to FastRTPS:
- Lower latency (50-70% reduction in many scenarios)
- Higher throughput
- Better real-time characteristics
- More efficient memory usage

### Implementation Steps

#### Install CycloneDDS

```bash
sudo apt-get update
sudo apt-get install ros-humble-rmw-cyclonedds-cpp
```

#### Create CycloneDDS Configuration

Create `cyclonedds_config.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CycloneDDS xmlns="https://cdds.io/config" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="https://cdds.io/config https://raw.githubusercontent.com/eclipse-cyclonedds/cyclonedds/master/etc/cyclonedds.xsd">
  <Domain id="any">
    <General>
      <NetworkInterfaceAddress>auto</NetworkInterfaceAddress>
      <AllowMulticast>true</AllowMulticast>
      <MaxMessageSize>65500B</MaxMessageSize>
    </General>
    <Internal>
      <MinimumSocketReceiveBufferSize>10MB</MinimumSocketReceiveBufferSize>
      <MinimumSocketSendBufferSize>10MB</MinimumSocketSendBufferSize>
    </Internal>
    <Tracing>
      <Verbosity>warning</Verbosity>
      <OutputFile>cyclonedds.log</OutputFile>
    </Tracing>
  </Domain>
</CycloneDDS>
```

#### Configure Environment

Add to your `.bashrc` or launch file:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///path/to/cyclonedds_config.xml
```

#### Verification

```bash
# Check active RMW
ros2 doctor --report | grep middleware

# Run performance test
ros2 run performance_test perf_test --topic test_topic --msg sensor_msgs/msg/Image --rate 30
```

### Expected Performance Improvements

| Metric | FastRTPS | CycloneDDS | Improvement |
|--------|----------|------------|-------------|
| Latency (avg) | 5-8 ms | 2-3 ms | 60-70% |
| Throughput | 50 MB/s | 80-100 MB/s | 60-100% |
| CPU usage | 15-20% | 10-12% | 30-40% |
| Memory | 150 MB | 100 MB | 33% |

---

## Control Loop Optimization (1-2 hours)

### Timing Measurement

- [ ] **Measure actual loop rate**
  ```cpp
  auto start = std::chrono::high_resolution_clock::now();
  // ... control loop work ...
  auto duration = std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::high_resolution_clock::now() - start
  );
  if (duration.count() > 5000) {  // 5ms threshold
      RCLCPP_WARN_THROTTLE(logger_, clock_, 1000, 
                          "Control loop slow: %ldµs", duration.count());
  }
  ```

- [ ] **Separate computation from I/O**
  ```cpp
  // Bad: Compute and send in same function
  void control_loop() {
      compute_control();  // CPU intensive
      send_can_messages();  // I/O bound
  }
  
  // Good: Pipeline computation and I/O
  void control_loop() {
      // Send results from previous iteration (async)
      send_previous_results();
      
      // Compute current iteration
      compute_control();
  }
  ```

### Real-Time Performance

- [ ] **Enable real-time priority** (requires RT kernel)
  ```cpp
  sched_param param;
  param.sched_priority = 80;  // 1-99, higher = more priority
  pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
  ```

- [ ] **Lock memory** - Prevent page faults
  ```cpp
  mlockall(MCL_CURRENT | MCL_FUTURE);
  ```

- [ ] **Use stack for hot-path allocations**
  ```cpp
  // Instead of: std::vector<double> values;
  std::array<double, 10> values;  // Fixed size, stack allocated
  ```

### Benchmarking Infrastructure

```cpp
// control_loop_benchmark.hpp
class ControlLoopBenchmark {
public:
    struct LoopStatistics {
        double mean_cycle_time_ms;
        double std_dev_ms;
        double min_cycle_time_ms;
        double max_cycle_time_ms;
        double target_frequency_hz;
        double actual_frequency_hz;
        size_t missed_deadlines;
        size_t total_cycles;
    };
    
    void record_cycle(std::chrono::microseconds duration);
    LoopStatistics compute_statistics() const;
};
```

---

## Vision Pipeline Optimization (2-3 hours)

### YOLO Inference

- [ ] **Warmup model** - Run inference on dummy image at startup
  ```cpp
  cv::Mat dummy_image(640, 640, CV_8UC3);
  yolo_detector_->detect(dummy_image);  // Warmup
  ```

- [ ] **Enable GPU acceleration**
  ```cpp
  // Check ONNX Runtime providers
  Ort::SessionOptions session_options;
  session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
  
  // Try CUDA provider first
  OrtCUDAProviderOptions cuda_options;
  session_options.AppendExecutionProvider_CUDA(cuda_options);
  ```

- [ ] **Reduce input resolution** - 416x416 instead of 640x640 for 2.4x speedup
  ```yaml
  input_width: 416
  input_height: 416
  ```

### Asynchronous YOLO Inference

#### Problem
Synchronous YOLO inference blocks the main control loop, causing:
- Missed control cycles
- Increased latency
- Reduced system responsiveness

#### Solution Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Camera    │────────>│ Frame Buffer │────────>│ Main Thread │
│  Callback   │         │   (Queue)    │         │   (Control) │
└─────────────┘         └──────────────┘         └─────────────┘
                               │
                               │ async
                               ▼
                        ┌──────────────┐
                        │ YOLO Inference│
                        │    Thread     │
                        └──────────────┘
                               │
                               │ results
                               ▼
                        ┌──────────────┐
                        │Result Queue  │────────> Detection Callback
                        └──────────────┘
```

#### Implementation

```cpp
// async_yolo_detector.hpp
class AsyncYOLODetector {
public:
    AsyncYOLODetector(std::shared_ptr<YOLODetector> detector);
    ~AsyncYOLODetector();
    
    // Non-blocking detection request
    void detect_async(const cv::Mat& image, 
                     std::function<void(std::vector<Detection>)> callback);
    
    // Check if detector is busy
    bool is_busy() const;
    
    // Get pending request count
    size_t pending_requests() const;
    
private:
    void worker_thread();
    
    std::shared_ptr<YOLODetector> detector_;
    std::thread worker_;
    std::atomic<bool> running_;
    
    // Thread-safe queue
    std::queue<AsyncRequest> request_queue_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
};
```

#### Usage in Cotton Detection Node

```cpp
// In cotton_detection_node.cpp

void CottonDetectionNode::image_callback(const sensor_msgs::msg::Image::SharedPtr msg)
{
    cv::Mat image = cv_bridge::toCvCopy(msg, "bgr8")->image;
    
    // Non-blocking async detection
    async_detector_->detect_async(image, 
        [this](std::vector<YOLODetector::DetectedCotton> detections) {
            this->handle_detections(detections);
        });
    
    // Control loop continues immediately
}
```

#### Frame Dropping Strategy

```cpp
// Drop frames if queue is too long
if (async_detector_->pending_requests() > max_queue_depth_) {
    RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 1000,
                        "Dropping frame: inference queue full");
    return;
}
```

#### Expected Performance

- **Control loop frequency**: 50 Hz → 100 Hz
- **Detection latency**: +10-20 ms (acceptable)
- **System responsiveness**: Significantly improved
- **Frame drop rate**: <5% under normal conditions

### Image Processing

- [ ] **Skip frame processing** - Process every Nth frame
  ```cpp
  if (++frame_count_ % frame_skip_ != 0) return;
  ```

- [ ] **Downsample before processing**
  ```cpp
  cv::resize(input, input, cv::Size(), 0.5, 0.5, cv::INTER_AREA);
  ```

- [ ] **Use ROI** - Process only region of interest
  ```cpp
  cv::Rect roi(x, y, width, height);
  cv::Mat roi_image = full_image(roi);
  ```

---

## Memory Optimization

### Overview
Memory optimization is critical for Raspberry Pi deployment. This section covers monitoring, build-time fixes, and runtime optimizations.

### RPi Build OOM Prevention (✅ IMPLEMENTED)

**Problem:** Cotton detection node failed to build on RPi with `-j2` due to OOM errors.

**Root Cause:**
- Large template-heavy library headers in `.hpp` files
- `#include <depthai/depthai.hpp>` (DepthAI SDK - very large)
- `#include <opencv2/opencv.hpp>` (OpenCV - large templates)
- Every `.cpp` including these headers bloated compilation memory

**Solution Implemented (Nov 2024):**

#### Phase 1: Move Heavy Includes to .cpp Files ⭐

**Files Modified:**
- `depthai_manager.hpp` - Removed `#include <depthai/depthai.hpp>`
- `cotton_detection_node.hpp` - Removed `#include <opencv2/opencv.hpp>`
- Used forward declarations in headers
- Moved actual includes to corresponding `.cpp` files

**Before (causes bloat):**
```cpp
// depthai_manager.hpp
#include <depthai/depthai.hpp>  // HUGE library
#include <opencv2/opencv.hpp>   // HUGE library

class DepthAIManager {
    std::shared_ptr<dai::Device> device_;
    std::shared_ptr<dai::DataOutputQueue> queue_;
};
```

**After (forward declarations):**
```cpp
// depthai_manager.hpp
namespace dai {
    class Device;
    class DataOutputQueue;
    class Pipeline;
}

namespace cv {
    class Mat;
}

class DepthAIManager {
    std::shared_ptr<dai::Device> device_;
    std::shared_ptr<dai::DataOutputQueue> queue_;
};
```

```cpp
// depthai_manager.cpp
#include "cotton_detection_ros2/depthai_manager.hpp"

// NOW include the heavy libraries (only in .cpp)
#include <depthai/depthai.hpp>
#include <opencv2/opencv.hpp>

// Rest of implementation...
```

#### Phase 2: File Splitting ⭐

**Split `cotton_detection_node.cpp` (2,189 lines) into 5 files:**
- `cotton_detection_node.cpp` (1,053 lines) - Core node logic
- `cotton_detection_parameters.cpp` (585 lines) - Parameter management
- `cotton_detection_init.cpp` (170 lines) - Initialization
- `cotton_detection_callbacks.cpp` (126 lines) - ROS callbacks
- `cotton_detection_services.cpp` (317 lines) - Service handlers

**Benefits:**
- Reduced per-file memory footprint
- Parallel compilation viable
- Better code organization
- Each compilation unit has minimal header dependencies

**Results:**
- ✅ **Build time (RPi):** 4m 33s with `-j2` (was OOM crashing)
- ✅ **Build time (PC):** 11.2s
- ✅ **Memory per worker:** ~70% reduction
- ✅ **`-j2` on RPi:** Works reliably
- ✅ **Risk:** Low (same pattern as yanthra_move)

### Runtime Memory Optimization (1-2 hours)

### Monitor Memory Usage

```bash
# Watch ROS2 nodes
watch -n 1 'ps aux | grep ros2 | head -10'

# Detailed memory profiling
valgrind --tool=massif ros2 run motor_control_ros2 motor_control_node

# Analyze with
ms_print massif.out.*
```

### Reduce Allocations

- [ ] **Object pooling** for frequently created objects
  ```cpp
  template<typename T>
  class ObjectPool {
      std::vector<std::unique_ptr<T>> pool_;
      std::queue<T*> available_;
  public:
      T* acquire() {
          if (available_.empty()) {
              pool_.push_back(std::make_unique<T>());
              return pool_.back().get();
          }
          T* obj = available_.front();
          available_.pop();
          return obj;
      }
      void release(T* obj) {
          available_.push(obj);
      }
  };
  ```

---

## Thermal Management

### Overview
OAK-D Lite camera thermal management is critical for system reliability and longevity.

### Thermal Issue History

**Original Problem (Oct 2025):**
- Peak temperature: **96.6°C** (critical, thermal protection triggered)
- Thermal throttling after 90 seconds
- Detection service timeouts
- System unusable for production

**Root Cause:**
- ROS2 used `HIGH_DENSITY` stereo preset vs ROS1's `HIGH_ACCURACY`
- StereoDepth pipeline running continuously at 30 FPS
- 35% of thermal load from stereo depth processing

### Solution Implemented ✅

#### Option 1: Stereo Preset Optimization (Initial Fix)

**Changed stereo configuration to match ROS1:**
```cpp
// File: src/cotton_detection_ros2/src/depthai_manager.cpp

// OLD (ROS2 - caused overheating):
stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::HIGH_DENSITY);

// NEW (Matching ROS1 - reduced heat):
stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::HIGH_ACCURACY);
stereo->setLeftRightCheck(true);
stereo->setSubpixel(false);
stereo->setExtendedDisparity(true);
stereo->initialConfig.setConfidenceThreshold(255);
stereo->initialConfig.setMedianFilter(dai::MedianFilter::KERNEL_7x7);
```

**Results:**
- Temperature reduction: 10-15°C
- Target: 65-70°C (from 81-83°C)

#### Option 2: Depth Disabled (Production Solution - Nov 2025)

**Configuration change:**
```yaml
# File: src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
enable_depth: false  # Changed from true
```

**Code update:**
- Made StereoDepth node creation conditional
- Mono cameras only created when `enable_depth: true`
- Pipeline validates correctly with depth disabled

**Test Results:**

| Scenario | Configuration | Peak Temp | Improvement | Status |
|----------|--------------|-----------|-------------|--------|
| Baseline | 15 FPS, depth ON | **96.6°C** | - | ❌ CRITICAL |
| Optimized Preset | 15 FPS, HIGH_ACCURACY | **~70°C** | 27°C | ⚠️ Acceptable |
| Depth Disabled | 15 FPS, depth OFF | **65.2°C** | **31.4°C** | ✅ **PRODUCTION** |

**Production Status:**
- ✅ Deployed Nov 2025
- ✅ Temperature stable < 70°C
- ✅ No thermal throttling
- ✅ 100% detection reliability
- ✅ System validated for 1+ hour continuous operation

### Temperature Zones Reference

| Zone | Range | Status | Action |
|------|-------|--------|--------|
| Normal | 40-75°C | ✅ Safe | None required |
| Warning | 75-80°C | ⚠️ Degraded | Monitor, consider optimization |
| Throttling | 80-85°C | 🔴 Active reduction | Immediate action required |
| Critical | 85-95°C | 🔴🔴 Risk | Stop operation |
| Shutdown | >95°C | 🚨 Protection | Hardware safety engaged |

### Thermal Sources Breakdown

| Component | Contribution | Always-On? | Can Disable? | Status |
|-----------|--------------|------------|--------------|--------|
| **StereoDepth** | **35%** | ✅ Yes | ✅ **YES** | ✅ **Disabled in production** |
| ISP @ 1080p | 25% | ✅ Yes | ⚠️ Could optimize | Active |
| Color Sensor | 15% | ✅ Yes | ⚠️ Via still-capture | Active |
| Mono Sensors (2x) | 10% | ✅ Yes | ✅ Yes | ✅ Auto-disabled with stereo |
| YOLO NN | 10% | ❌ No | ✅ Already on-demand | On-demand only |
| USB/XLink | 5% | ✅ Yes | - | Active |

**Key Insight:** Queue-based frame dropping does NOT reduce thermal load!
- Sensors, ISP, and StereoDepth run continuously at configured FPS
- Dropping frames happens AFTER all processing
- Only the NN compute is truly on-demand

### Additional Thermal Optimization Options

**If temps approach 70°C in field conditions:**

1. **Lower ISP Resolution** (Est. 5-8°C savings)
   ```cpp
   // Modify depthai_manager.cpp:
   colorCam->setPreviewSize(1280, 720);  // 720p instead of 1080p
   colorCam->setResolution(dai::ColorCameraProperties::SensorResolution::THE_720_P);
   ```

2. **Reduce FPS** (Est. 3-5°C savings per 5 FPS reduction)
   ```yaml
   fps: 10  # Down from 15
   ```

3. **Still-Capture Mode** (Est. 40-50°C savings idle)
   - Sensors powered off between captures
   - Requires pipeline redesign
   - See `OAKD_Pipeline_DeepDive.md` for implementation

### Thermal Monitoring

**During development:**
```bash
# Monitor camera temperature
ros2 topic echo /cotton_detection/diagnostics | grep -i temperature

# Run thermal soak test (1 hour)
./validated_thermal_test.sh 60 production_soak

# Check results
tail -f production_soak_ros2_*.log | grep -i temperature
```

**Success criteria:**
- Peak temperature < 75°C after 1 hour
- No thermal warnings or throttling
- Detection success rate > 95%
- No service timeouts

### Rollback Plan

**If depth must be re-enabled:**
```bash
cd /home/ubuntu/pragati_ros2
sed -i 's/enable_depth: false/enable_depth: true/' \
  src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

**⚠️ Warning:** This will reintroduce thermal issues! Only enable if:
- 3D coordinates absolutely required
- External cooling solution implemented
- Operating in cooler environment
- Willing to accept reduced duty cycle

### Trade-offs

**With depth disabled:**
- ✅ **Keep:** Fast detection, simple architecture, on-demand service, thermal stability
- ❌ **Lose:** Spatial (3D) coordinates for cotton detections
- ⚠️ **Mitigation options:**
  - Still-capture mode (sensor-off between captures)
  - External depth sensor (Intel RealSense)
  - Run stereo only during critical operations with cooldown periods

---

## Optimization Priorities

### Phase 1: Foundation (Week 1)
1. Enable CycloneDDS
2. Configure QoS properly
3. Enable ccache and parallel builds
4. Remove debug logs from hot paths

### Phase 2: Control Loop (Week 2)
1. Add timing measurement
2. Separate computation from I/O
3. Enable real-time priority (if RT kernel available)
4. Implement benchmarking infrastructure

### Phase 3: Vision Pipeline (Week 3-4)
1. Implement async YOLO inference
2. Add frame dropping logic
3. Enable GPU acceleration
4. Optimize input resolution

### Phase 4: Memory & Polish (Week 5)
1. Implement object pooling
2. Profile memory usage
3. Pre-allocate buffers
4. Final benchmarking and validation

---

## Validation

After each optimization phase:

```bash
# Benchmark control loop
ros2 run yanthra_move benchmark_control_loop

# Measure detection latency
ros2 topic hz /cotton_detection/results
ros2 topic delay /cotton_detection/results

# Memory profiling
valgrind --leak-check=full ros2 launch yanthra_move pragati_complete.launch.py

# CPU profiling
perf record -g ros2 run cotton_detection_ros2 cotton_detection_node
perf report
```

---

## References

- **CycloneDDS Documentation:** https://cyclonedds.io/docs/
- **ROS2 QoS Guide:** https://docs.ros.org/en/humble/Concepts/About-Quality-of-Service-Settings.html
- **ONNX Runtime Performance Tuning:** https://onnxruntime.ai/docs/performance/tune-performance.html
- **Real-Time Programming:** https://design.ros2.org/articles/realtime_background.html

---

**Consolidated:** October 21, 2025  
**Archival Note:** Original guides moved to `docs/archive/2025-10-phase2/`
