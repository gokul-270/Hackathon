# Performance Optimization Implementation Guide

## Overview

This guide provides implementation details for performance optimizations identified during the software sprint. These optimizations target real-time performance, throughput, and latency reduction.

## 1. CycloneDDS Configuration

### Why CycloneDDS?

CycloneDDS provides superior performance compared to FastRTPS:
- Lower latency (50-70% reduction in many scenarios)
- Higher throughput
- Better real-time characteristics
- More efficient memory usage

### Implementation Steps

#### 1.1 Install CycloneDDS

```bash
sudo apt-get update
sudo apt-get install ros-humble-rmw-cyclonedds-cpp
```

#### 1.2 Create CycloneDDS Configuration

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

#### 1.3 Configure Environment

Add to your `.bashrc` or launch file:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///path/to/cyclonedds_config.xml
```

#### 1.4 Verification

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

## 2. Asynchronous YOLO Inference

### Problem

Synchronous YOLO inference blocks the main control loop, causing:
- Missed control cycles
- Increased latency
- Reduced system responsiveness

### Solution Architecture

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

### Implementation

#### 2.1 Create Async Wrapper

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

#### 2.2 Usage in Cotton Detection Node

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

#### 2.3 Frame Dropping Strategy

```cpp
// Drop frames if queue is too long
if (async_detector_->pending_requests() > max_queue_depth_) {
    RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 1000,
                        "Dropping frame: inference queue full");
    return;
}
```

### Expected Performance

- **Control loop frequency**: 50 Hz → 100 Hz
- **Detection latency**: +10-20 ms (acceptable)
- **System responsiveness**: Significantly improved
- **Frame drop rate**: <5% under normal conditions

## 3. Control Loop Benchmarking

### Implementation

#### 3.1 Benchmark Class

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
    
    void start_cycle();
    void end_cycle();
    LoopStatistics get_statistics() const;
    void reset();
    
private:
    std::vector<double> cycle_times_;
    std::chrono::steady_clock::time_point cycle_start_;
    size_t missed_deadlines_{0};
    double target_cycle_time_ms_;
};
```

#### 3.2 Integration

```cpp
// In motor control loop
void MotorController::control_loop() {
    ControlLoopBenchmark benchmark;
    benchmark.set_target_frequency(100.0); // 100 Hz
    
    while (rclcpp::ok()) {
        benchmark.start_cycle();
        
        // Control logic
        read_encoders();
        compute_control();
        send_commands();
        
        benchmark.end_cycle();
        
        // Log statistics periodically
        if (cycle_count_ % 1000 == 0) {
            auto stats = benchmark.get_statistics();
            RCLCPP_INFO(get_logger(), 
                       "Control loop: %.2f Hz (target: %.2f Hz), "
                       "latency: %.2f ± %.2f ms, missed: %zu",
                       stats.actual_frequency_hz,
                       stats.target_frequency_hz,
                       stats.mean_cycle_time_ms,
                       stats.std_dev_ms,
                       stats.missed_deadlines);
        }
        
        wait_for_next_cycle();
    }
}
```

### Performance Targets

| Component | Target Frequency | Max Latency | Jitter |
|-----------|------------------|-------------|--------|
| Motor Control | 100 Hz | 5 ms | < 1 ms |
| Safety Monitor | 50 Hz | 10 ms | < 2 ms |
| Vision Processing | 30 Hz | 20 ms | < 5 ms |
| Path Planning | 10 Hz | 50 ms | < 10 ms |

## 4. Memory Optimization

### Pre-allocation

```cpp
// Pre-allocate buffers
class ImageProcessor {
public:
    ImageProcessor() {
        // Pre-allocate common image sizes
        preallocated_buffer_.reserve(1920 * 1080 * 3);
        detection_results_.reserve(100); // Max detections
    }
    
private:
    std::vector<uint8_t> preallocated_buffer_;
    std::vector<Detection> detection_results_;
};
```

### Object Pooling

```cpp
// Reuse message objects
class MessagePool {
public:
    template<typename MsgType>
    std::shared_ptr<MsgType> acquire() {
        // Return from pool or create new
    }
    
    template<typename MsgType>
    void release(std::shared_ptr<MsgType> msg) {
        // Return to pool
    }
};
```

## 5. Network Optimization

### QoS Configuration

```cpp
// Low latency QoS profile
auto qos = rclcpp::QoS(rclcpp::KeepLast(1))
    .best_effort()
    .durability_volatile()
    .liveliness(rclcpp::LivelinessPolicy::Automatic)
    .deadline(std::chrono::milliseconds(20));

image_subscriber_ = create_subscription<sensor_msgs::msg::Image>(
    "/camera/image_raw", qos, callback);
```

### Zero-Copy Transport

```cpp
// Use intra-process communication
auto options = rclcpp::NodeOptions()
    .use_intra_process_comms(true);

auto node = std::make_shared<MyNode>(options);
```

## Implementation Priority

1. **CycloneDDS** (High priority, easy): Immediate 60% latency reduction
2. **Async YOLO** (High priority, medium difficulty): Unblocks control loop
3. **Control Loop Benchmarks** (Medium priority, easy): Monitoring & validation
4. **Memory Optimization** (Low priority, easy): Incremental improvements
5. **Zero-Copy** (Low priority, medium): Requires intra-process nodes

## Validation

### Performance Test Suite

```bash
# Run benchmark suite
ros2 run pragati_benchmarks control_loop_benchmark
ros2 run pragati_benchmarks vision_pipeline_benchmark
ros2 run pragati_benchmarks end_to_end_latency_test
```

### Success Criteria (Deferred to Hardware Phase)

Validation of performance targets requires hardware:
- Control loop maintains 100 Hz ± 5%
- Vision processing at 30 Hz without frame drops
- End-to-end latency < 100 ms (camera to motor command)
- CPU usage < 60% under full load
- Memory usage < 2 GB

## Monitoring

### Real-time Dashboard

Use `rqt_plot` to monitor:
- Control loop frequency
- Vision processing latency
- CPU/memory usage
- Message queue depths

```bash
rqt_plot /diagnostics/control_loop_freq /diagnostics/vision_latency
```

## References

- [CycloneDDS Documentation](https://github.com/eclipse-cyclonedds/cyclonedds)
- [ROS2 Performance Best Practices](https://docs.ros.org/en/humble/How-To-Guides/DDS-tuning.html)
- [Real-time Programming with ROS2](https://design.ros2.org/articles/realtime_background.html)

---

**Last Updated:** 2025-10-21
