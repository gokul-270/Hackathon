# Performance Optimization Checklist

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

## Control Loop Optimization (1-2 hours)

### Timing
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

- [ ] **Async inference** with worker thread
  ```cpp
  std::future<DetectionResult> inference_future_;
  
  void on_image_received(const sensor_msgs::msg::Image::SharedPtr msg) {
      if (inference_future_.valid() && 
          inference_future_.wait_for(std::chrono::milliseconds(0)) == std::future_status::ready) {
          auto result = inference_future_.get();
          publish_detections(result);
      }
      
      // Start new inference asynchronously
      inference_future_ = std::async(std::launch::async, 
                                    [this, msg]() { return run_inference(msg); });
  }
  ```

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

## Memory Optimization (1-2 hours)

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

- [ ] **Reserve vector capacity** upfront
  ```cpp
  detections.reserve(100);  // Avoid reallocations
  ```

- [ ] **Use move semantics**
  ```cpp
  return std::move(large_object);  // Avoid copy
  ```

---

## Network Optimization (1 hour)

### DDS Tuning
```xml
<!-- cyclonedds.xml -->
<CycloneDDS>
  <Domain>
    <General>
      <NetworkInterfaceAddress>lo</NetworkInterfaceAddress>  <!-- Localhost only -->
    </General>
    <Internal>
      <SocketReceiveBufferSize min="10MB"/>
      <SocketSendBufferSize>1MB</SocketSendBufferSize>
    </Internal>
  </Domain>
</CycloneDDS>
```

```bash
export CYCLONEDDS_URI=file:///path/to/cyclonedds.xml
```

### Message Size
- [ ] **Compress large messages** (images, point clouds)
- [ ] **Reduce publish rate** for non-critical data
- [ ] **Use intra-process communication** for same-node pub/sub

---

## Benchmarking Tools

### Built-in ROS2 Tools
```bash
# Profile topic throughput
ros2 topic hz /camera/image_raw

# Check topic bandwidth
ros2 topic bw /camera/image_raw

# Monitor CPU/memory
ros2 run rqt_top rqt_top
```

### Custom Benchmarks
```cpp
#include <chrono>

class PerformanceTimer {
    std::chrono::high_resolution_clock::time_point start_;
public:
    PerformanceTimer() : start_(std::chrono::high_resolution_clock::now()) {}
    
    double elapsed_ms() {
        auto end = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<double, std::milli>(end - start_).count();
    }
};

// Usage
PerformanceTimer timer;
expensive_operation();
RCLCPP_INFO(logger_, "Operation took %.2fms", timer.elapsed_ms());
```

---

## Performance Targets

### Control Loop
- **Target:** < 1ms per iteration
- **Acceptable:** < 5ms
- **Critical:** > 10ms (investigate immediately)

### Vision Pipeline
- **Target:** 30 FPS (33ms per frame)
- **Acceptable:** 15 FPS (66ms per frame)
- **Degraded:** < 10 FPS

### CAN Communication
- **Target:** < 1ms latency per message
- **Acceptable:** < 5ms
- **Critical:** > 10ms

---

## Measurement Commands

### Before Optimization
```bash
# Baseline measurements
ros2 topic hz /detections --window 100
ros2 topic hz /joint_states --window 100
ros2 topic bw /camera/image_raw

# Save baseline
ros2 bag record -a -o baseline_performance
```

### After Optimization
```bash
# Compare with baseline
ros2 bag play baseline_performance
# Run measurements again, compare numbers
```

---

## Checklist Summary

**Quick Wins (< 2 hours total):**
- [x] ccache enabled
- [ ] CycloneDDS configured
- [ ] Debug logs removed from hot paths
- [ ] Message buffers pre-allocated

**Medium Effort (2-4 hours total):**
- [ ] YOLO model warmup
- [ ] Async inference pipeline
- [ ] Control loop timing measured
- [ ] Real-time priority enabled

**Long Term (> 4 hours):**
- [ ] Full memory profiling with valgrind
- [ ] Custom object pool implementation
- [ ] GPU acceleration verified
- [ ] Complete real-time kernel setup

---

## Expected Improvements

| Optimization | Expected Speedup |
|--------------|------------------|
| ccache | 98% faster rebuilds |
| CycloneDDS | 20-30% lower latency |
| GPU YOLO | 3-5x faster inference |
| Async inference | 40-60% higher throughput |
| Pre-allocation | 10-20% less CPU/memory |
| Real-time kernel | Deterministic timing |

**Last Updated:** 2025-10-21
