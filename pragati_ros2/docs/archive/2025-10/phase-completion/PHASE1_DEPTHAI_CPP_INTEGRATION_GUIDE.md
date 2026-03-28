# Phase 1: DepthAI C++ Integration Guide

**Date:** October 8, 2025  
**Status:** 🚀 Ready to Start  
**DepthAI Version:** 2.30.0 (ROS Jazzy package)

---

## Executive Summary

We successfully installed the pre-built `ros-jazzy-depthai` package (v2.30.0) which includes:
- ✅ depthai-core C++ library headers in `/opt/ros/jazzy/include/depthai/`
- ✅ depthai-bridge ROS2 integration utilities
- ✅ All necessary dependencies (no 82-package build needed!)

This Phase 1 guide covers integrating the DepthAI C++ API into our `CottonDetectionNode`.

---

## Installation Summary

### What Was Installed
```bash
# Installed packages:
ros-jazzy-depthai                      # Core C++ library (24.9 MB)
ros-jazzy-depthai-bridge              # ROS2 integration utilities
ros-jazzy-depthai-ros-msgs            # ROS2 message definitions
ros-jazzy-camera-info-manager         # Camera calibration support
```

### Key Locations
- **Headers:** `/opt/ros/jazzy/include/depthai/`
- **Libraries:** `/opt/ros/jazzy/lib/libdepthai-core.so`
- **CMake Config:** `/opt/ros/jazzy/share/depthai/cmake/`

---

## DepthAI C++ API Overview

### Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Your Application                         │
│                  (CottonDetectionNode)                       │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │   dai::Device         │  ← Represents OAK-D camera
         │                       │
         │  Methods:             │
         │  - startPipeline()    │
         │  - getOutputQueue()   │
         │  - getInputQueue()    │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │   dai::Pipeline       │  ← Defines processing graph
         │                       │
         │  Methods:             │
         │  - create<NodeType>() │
         │  - link(out, in)      │
         └───────────┬───────────┘
                     │
    ┌────────────────┴─────────────────┐
    │                                   │
┌───▼──────────┐              ┌────────▼────────┐
│ ColorCamera  │              │ SpatialDetection │
│              │              │ Network          │
│ - setResolution()          │ - setBlobPath()  │
│ - setFps()                 │ - setConfidence()│
│ - video → (link)           │ - out → detections
└──────────────┘              └──────────────────┘
```

### Key Classes

#### 1. `dai::Pipeline`
Defines the processing graph.
```cpp
dai::Pipeline pipeline;
auto colorCam = pipeline.create<dai::node::ColorCamera>();
auto spatialNN = pipeline.create<dai::node::YoloSpatialDetectionNetwork>();
```

#### 2. `dai::Device`
Represents the physical OAK-D camera.
```cpp
dai::Device device(pipeline);
device.startPipeline();
```

#### 3. `dai::node::ColorCamera`
Camera configuration node.
```cpp
colorCam->setResolution(dai::ColorCameraProperties::SensorResolution::THE_1080_P);
colorCam->setFps(30);
colorCam->setInterleaved(false);
```

#### 4. `dai::node::YoloSpatialDetectionNetwork`
YOLO with depth integration.
```cpp
spatialNN->setBlobPath("/path/to/model.blob");
spatialNN->setConfidenceThreshold(0.5f);
spatialNN->setDepthLowerThreshold(100);    // mm
spatialNN->setDepthUpperThreshold(5000);   // mm
```

#### 5. `dai::DataOutputQueue`
Receives detection results.
```cpp
auto detectionQueue = device.getOutputQueue("detections", 8, false);
auto detections = detectionQueue->get<dai::SpatialImgDetections>();
```

---

## Typical Usage Pattern

### Minimal Spatial Detection Example

```cpp
#include <depthai/depthai.hpp>

int main() {
    // 1. Create pipeline
    dai::Pipeline pipeline;
    
    // 2. Define nodes
    auto colorCam = pipeline.create<dai::node::ColorCamera>();
    auto stereo = pipeline.create<dai::node::StereoDepth>();
    auto spatialNN = pipeline.create<dai::node::YoloSpatialDetectionNetwork>();
    auto xoutRgb = pipeline.create<dai::node::XLinkOut>();
    auto xoutNN = pipeline.create<dai::node::XLinkOut>();
    auto xoutDepth = pipeline.create<dai::node::XLinkOut>();
    
    xoutRgb->setStreamName("rgb");
    xoutNN->setStreamName("detections");
    xoutDepth->setStreamName("depth");
    
    // 3. Configure camera
    colorCam->setPreviewSize(416, 416);
    colorCam->setResolution(dai::ColorCameraProperties::SensorResolution::THE_1080_P);
    colorCam->setInterleaved(false);
    colorCam->setColorOrder(dai::ColorCameraProperties::ColorOrder::BGR);
    colorCam->setFps(30);
    
    // 4. Configure stereo depth
    stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::HIGH_DENSITY);
    stereo->setDepthAlign(dai::CameraBoardSocket::RGB);
    
    // 5. Configure spatial detection network
    spatialNN->setBlobPath("/path/to/yolo.blob");
    spatialNN->setConfidenceThreshold(0.5f);
    spatialNN->setDepthLowerThreshold(100);
    spatialNN->setDepthUpperThreshold(5000);
    spatialNN->input.setBlocking(false);
    spatialNN->setBoundingBoxScaleFactor(0.5);
    
    // 6. Link nodes
    colorCam->preview.link(spatialNN->input);
    spatialNN->passthrough.link(xoutRgb->input);
    spatialNN->out.link(xoutNN->input);
    stereo->depth.link(spatialNN->inputDepth);
    spatialNN->passthroughDepth.link(xoutDepth->input);
    
    // 7. Connect to device
    dai::Device device(pipeline);
    
    // 8. Get output queues
    auto qRgb = device.getOutputQueue("rgb", 4, false);
    auto qDet = device.getOutputQueue("detections", 4, false);
    auto qDepth = device.getOutputQueue("depth", 4, false);
    
    // 9. Main loop
    while(true) {
        auto detections = qDet->get<dai::SpatialImgDetections>();
        
        for(const auto& detection : detections->detections) {
            std::cout << "Label: " << detection.label << std::endl;
            std::cout << "Confidence: " << detection.confidence << std::endl;
            std::cout << "X: " << detection.spatialCoordinates.x << " mm" << std::endl;
            std::cout << "Y: " << detection.spatialCoordinates.y << " mm" << std::endl;
            std::cout << "Z: " << detection.spatialCoordinates.z << " mm" << std::endl;
        }
    }
    
    return 0;
}
```

---

## Detection Data Structure

### `dai::SpatialImgDetections`
```cpp
struct SpatialImgDetection {
    uint32_t label;                    // Class ID
    float confidence;                  // 0.0 to 1.0
    float xmin, ymin, xmax, ymax;     // Normalized bounding box [0, 1]
    
    // Spatial coordinates (in millimeters)
    struct {
        float x;  // Left(-) / Right(+) from camera center
        float y;  // Down(-) / Up(+) from camera center
        float z;  // Distance from camera
    } spatialCoordinates;
};
```

---

## Design: DepthAIManager Class

### Class Responsibilities

```cpp
class DepthAIManager {
public:
    // Lifecycle
    bool initialize(const std::string& model_path, const CameraConfig& config);
    void shutdown();
    bool isHealthy() const;
    
    // Detection
    std::vector<CottonDetection> getDetections(double timeout_sec = 1.0);
    
    // Configuration
    void setConfidenceThreshold(float threshold);
    void setDepthRange(float min_mm, float max_mm);
    void setFPS(int fps);
    
    // Diagnostics
    CameraStats getStats() const;
    std::string getDeviceInfo() const;
    
private:
    std::unique_ptr<dai::Device> device_;
    std::shared_ptr<dai::Pipeline> pipeline_;
    std::shared_ptr<dai::DataOutputQueue> detection_queue_;
    std::shared_ptr<dai::DataOutputQueue> rgb_queue_;
    std::shared_ptr<dai::DataOutputQueue> depth_queue_;
    
    // Configuration
    std::string model_path_;
    float confidence_threshold_{0.5f};
    float depth_min_mm_{100.0f};
    float depth_max_mm_{5000.0f};
    int fps_{30};
    
    // Thread safety
    mutable std::mutex mutex_;
    
    // Helper methods
    void buildPipeline();
    CottonDetection convertDetection(const dai::SpatialImgDetection& det);
};
```

### Integration Points

```
┌──────────────────────────────────────────────────────────────┐
│          CottonDetectionNode (existing ROS2 node)            │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Before (Python wrapper):                    After (C++):    │
│  ┌─────────────────────┐          ┌──────────────────────┐  │
│  │ subprocess.Popen()  │   -->    │ DepthAIManager       │  │
│  │   CottonDetect.py   │          │   (native C++)       │  │
│  │   (Python script)   │          │                      │  │
│  │                     │          │ - No subprocess      │  │
│  │ - Uses DepthAI SDK  │          │ - Direct API calls   │  │
│  │ - File-based IPC    │          │ - In-process         │  │
│  │ - Fragile           │          │ - Fast & robust      │  │
│  └─────────────────────┘          └──────────────────────┘  │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Header File Structure

### Proposed File: `include/cotton_detection_ros2/depthai_manager.hpp`

```cpp
#pragma once

#include <depthai/depthai.hpp>
#include <memory>
#include <vector>
#include <string>
#include <mutex>
#include <optional>

namespace cotton_detection {

struct CameraConfig {
    int width{416};
    int height{416};
    int fps{30};
    float confidence_threshold{0.5f};
    float depth_min_mm{100.0f};
    float depth_max_mm{5000.0f};
    std::string color_order{"BGR"};
};

struct CottonDetection {
    uint32_t label;
    float confidence;
    float x_min, y_min, x_max, y_max;  // Normalized [0, 1]
    
    // Spatial coordinates (mm)
    float spatial_x;
    float spatial_y;
    float spatial_z;
    
    // Timestamp
    std::chrono::steady_clock::time_point timestamp;
};

struct CameraStats {
    double fps;
    double temperature_celsius;
    uint64_t frames_processed;
    std::chrono::milliseconds uptime;
};

class DepthAIManager {
public:
    DepthAIManager();
    ~DepthAIManager();
    
    // Non-copyable, movable
    DepthAIManager(const DepthAIManager&) = delete;
    DepthAIManager& operator=(const DepthAIManager&) = delete;
    DepthAIManager(DepthAIManager&&) noexcept;
    DepthAIManager& operator=(DepthAIManager&&) noexcept;
    
    // Lifecycle management
    bool initialize(const std::string& model_path, const CameraConfig& config);
    void shutdown();
    bool isInitialized() const;
    bool isHealthy() const;
    
    // Detection retrieval (blocking with timeout)
    std::optional<std::vector<CottonDetection>> 
        getDetections(std::chrono::milliseconds timeout);
    
    // Non-blocking detection check
    bool hasDetections() const;
    
    // Runtime configuration
    void setConfidenceThreshold(float threshold);
    void setDepthRange(float min_mm, float max_mm);
    void setFPS(int fps);
    
    // Diagnostics
    CameraStats getStats() const;
    std::string getDeviceInfo() const;
    std::vector<std::string> getAvailableDevices() const;
    
private:
    class Impl;
    std::unique_ptr<Impl> pImpl_;
};

}  // namespace cotton_detection
```

---

## CMakeLists.txt Integration

### Add to `src/cotton_detection_ros2/CMakeLists.txt`:

```cmake
# Find DepthAI
find_package(depthai REQUIRED)

# Add DepthAI manager library
add_library(depthai_manager
  src/depthai_manager.cpp
)

target_include_directories(depthai_manager PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

target_link_libraries(depthai_manager
  depthai::core
  ${rclcpp_LIBRARIES}
)

# Link to main node
target_link_libraries(cotton_detection_node
  depthai_manager
  # ... existing libraries
)
```

---

## Implementation Plan

### Phase 1.1: Basic Integration (Week 1)
- [x] Install ros-jazzy-depthai package
- [ ] Create `depthai_manager.hpp` header
- [ ] Implement `DepthAIManager::initialize()`
- [ ] Implement `DepthAIManager::getDetections()`
- [ ] Basic pipeline: Camera → YOLO → Spatial Detection
- [ ] Unit tests for initialization

### Phase 1.2: CottonDetectionNode Integration (Week 2)
- [ ] Replace subprocess logic with DepthAIManager
- [ ] Update `perform_detection()` to use C++ API
- [ ] Remove file-based IPC
- [ ] Update launch files
- [ ] Integration tests

### Phase 1.3: Advanced Features (Week 3)
- [ ] Runtime configuration (confidence, depth range)
- [ ] Health monitoring
- [ ] Temperature monitoring
- [ ] Performance metrics (FPS, latency)
- [ ] Error recovery

---

## Key Advantages Over Python Wrapper

| Aspect | Python Wrapper | C++ Integration |
|--------|----------------|-----------------|
| **Process** | Subprocess (separate) | In-process (same) |
| **IPC** | File-based (slow) | Memory (fast) |
| **Startup** | ~3-5 seconds | <1 second |
| **Latency** | 200-500ms | <50ms |
| **Reliability** | Prone to deadlocks | Robust |
| **Debugging** | Difficult (2 processes) | Easy (1 process) |
| **Memory** | 2× overhead | Efficient |
| **Errors** | Silent failures | Exceptions/logging |

---

## Next Steps

1. **Review this guide** - Understand the DepthAI C++ API structure
2. **Create header file** - Define `DepthAIManager` interface
3. **Implement skeleton** - Basic initialize/shutdown
4. **Test with hardware** - Verify camera detection
5. **Integrate into node** - Replace subprocess logic

---

## Resources

### Installed Files
```bash
# View all depthai headers
ls -R /opt/ros/jazzy/include/depthai/

# Check library
ls -la /opt/ros/jazzy/lib/libdepthai-core.so

# CMake config
ls /opt/ros/jazzy/share/depthai/cmake/
```

### Official Documentation
- DepthAI C++ API: https://docs.luxonis.com/projects/api/en/latest/
- OAK-D Lite specs: https://docs.luxonis.com/projects/hardware/en/latest/
- ROS2 depthai-ros: https://github.com/luxonis/depthai-ros

### Example Code
- Browse `/opt/ros/jazzy/include/depthai/` for API patterns
- Check `ros-jazzy-depthai-bridge` source for ROS2 integration examples

---

## Summary

✅ **Status:** DepthAI C++ library successfully installed via ROS package  
🎯 **Next:** Design and implement `DepthAIManager` class  
⏱️ **ETA:** 3 weeks to full C++ integration  
🚀 **Benefit:** 5-10× faster, more reliable, easier to debug

Ready to start Phase 1.1: Create the `DepthAIManager` header file!
