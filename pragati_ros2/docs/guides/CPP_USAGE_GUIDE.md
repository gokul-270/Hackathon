# Cotton Detection C++ Node - Usage Guide

**Status:** ✅ Production Ready (Validated Nov 1, 2025)  
**Last Updated:** 2025-11-04  
**Maintained:** See [CONTRIBUTING_DOCS.md](CONTRIBUTING_DOCS.md) for update guidelines

## Performance (Validated Nov 1, 2025)
- **Detection Latency:** 70ms (pure detection on RPi + OAK-D Lite)
- **Service Latency:** 134ms average (123-218ms range)
- **Reliability:** 100% (10/10 consecutive tests)
- **Spatial Accuracy:** ±10mm @ 0.6m
- **Build Time (RPi):** 4m 33s with -j2
- **Thermal (Production):** 65.2°C peak - stable

Overview
- This is the C++ implementation of the cotton detection node with optional DepthAI (OAK-D) integration.
- It supports two detection paths:
  1) DepthAI Direct (hardware spatial detections)
  2) Image-based (HSV/YOLO, fallback)

Quick Start (with DepthAI camera)
- Build:
  colcon build --packages-select cotton_detection_ros2 --cmake-args -DHAS_DEPTHAI=ON
- Run (DepthAI enabled by default in YAML):
  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

Quick Start (without camera)
- Run in image mode (set depthai.enable=false):
  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false

Configuration
- Default YAML: share/cotton_detection_ros2/config/cotton_detection_cpp.yaml
- Key parameters:
  - detection_mode: hsv_only | yolo_only | hybrid_voting | hybrid_merge | hybrid_fallback | depthai_direct
  - depthai.enable: true/false (auto-switch to depthai_direct on success)
  - depthai.model_path: path/to/yolov8v2.blob
  - camera_topic: /camera/image_raw

Diagnostics
- Enabled (updated every 1s). View with:
  ros2 topic echo /diagnostics
- Cotton Detection Status:
  - Detection Active, Image Available, Detection Mode, YOLO Status, Performance Monitoring
- DepthAI Camera Status (if enabled):
  - FPS, Frames Processed, Total Detections, Avg Latency (ms), Uptime (s), Temperature (C), Device Info, Model Path

TF and Camera Info
- Static TF published: base_link -> camera_link (default: x=0.1m, z=0.3m)
- CameraInfo topic: /camera/camera_info (default 416x416, placeholder intrinsics)
- Will be updated using real calibration in Phase 2.3

DepthAI Path
- Enable via: depthai.enable=true
- Auto-switches node to DEPTHAI_DIRECT mode on successful initialization
- Produces spatial detections (x, y, z in meters)
- Confidence scores taken from DepthAI detections

Image-based Path
- Detection modes: hsv_only, yolo_only, hybrid_voting, hybrid_merge, hybrid_fallback
- Positions computed from pixel coordinates using scaling and assumed depth

Outputs
- Topic: /cotton_detection/results (DetectionResult)
- Each CottonPosition includes:
  - position (geometry_msgs/Point)
  - confidence (float32)
  - detection_id (int32)

Note on Hardware Absence
- DepthAI initialization will block if depthai.enable=true and no camera is present.
- Workaround: set depthai.enable=false when developing without hardware.

Launch Examples
- Default:
  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
- Custom config file:
  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    config_file:=/path/to/custom.yaml
- Verbose logs:
  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py log_level:=debug

Troubleshooting
- If node hangs at startup, set depthai.enable=false and re-run.
- If YOLO ONNX errors appear, either provide a valid ONNX or disable YOLO.

Production Notes
- ✅ Hardware validated on Raspberry Pi 4 + OAK-D Lite
- ✅ Thermal performance stable (65.2°C peak)
- ✅ Service latency: 134ms avg (production-ready)
- 🔄 Python wrapper now legacy (C++ is primary path)
- 🔄 Calibration export available via service (detect_command: 2)
