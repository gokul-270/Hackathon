# Pragati ROS2 Quick Reference

## 🔧 Build
```bash
./build.sh                          # Full workspace
./build.sh --clean                  # Clean build
./build.sh --package yanthra_move   # Single package
./build.sh --fast                   # Interactive picker
./build.sh --jobs 8                 # Parallel build
```

## 🧪 Test
```bash
./test.sh --quick                   # Quick tests
./test.sh --complete                # Full suite
./test_suite/run_tests.sh 2              # Specific phase
```

## 🚀 Launch

### Complete System Launch
```bash
# Simulation mode (default)
ros2 launch yanthra_move pragati_complete.launch.py

# Hardware mode with continuous operation
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true

# Without ARM client
ros2 launch yanthra_move pragati_complete.launch.py enable_arm_client:=false

# Custom MQTT broker
ros2 launch yanthra_move pragati_complete.launch.py mqtt_address:=192.168.1.100

# Infinite runtime (testing only)
ros2 launch yanthra_move pragati_complete.launch.py continuous_operation:=true max_runtime_minutes:=-1

# Custom timeout (2 hours)
ros2 launch yanthra_move pragati_complete.launch.py continuous_operation:=true max_runtime_minutes:=120

# Skip start switch (CI/automated testing)
ros2 launch yanthra_move pragati_complete.launch.py start_switch.enable_wait:=false

# Full custom config
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=false \
  continuous_operation:=true \
  max_runtime_minutes:=120 \
  start_switch.enable_wait:=true \
  start_switch.timeout_sec:=10.0 \
  mqtt_address:=192.168.1.100
```

### Launch Parameters
**Main System (pragati_complete.launch.py):**

*Operation Mode:*
- `use_simulation:=<true|false>` - Simulation vs hardware (default: `true`)
- `continuous_operation:=<true|false>` - Continuous loop (default: `false`)
- `max_runtime_minutes:=<int>` - Timeout: `0`=auto, `-1`=infinite, `>0`=custom (default: `0`)

*Start Switch:*
- `start_switch.enable_wait:=<true|false>` - Wait for start switch (default: `true`)
- `start_switch.timeout_sec:=<float>` - Timeout in seconds (default: `5.0`)
- `start_switch.prefer_topic:=<true|false>` - Use ROS topic vs GPIO (default: `true`)

*System:*
- `enable_arm_client:=<true|false>` - ARM MQTT bridge (default: `true`)
- `mqtt_address:=<IP>` - MQTT broker IP (default: `10.42.0.10`)
- `use_sim_time:=<true|false>` - Gazebo clock (default: `false`)
- `output_log:=<screen|log>` - Output destination (default: `screen`)

### Cotton Detection Standalone
```bash
# Camera mode (live detection)
ros2 run cotton_detection_ros2 cotton_detection_node

# Offline mode (service-triggered)
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args -p offline_mode:=true

# Custom camera with lower threshold
ros2 run cotton_detection_ros2 cotton_detection_node --ros-args \
  -p camera_topic:=/usb_cam/image_raw \
  -p detection_confidence_threshold:=0.5
```

**Cotton Detection Parameters:**
- `-p offline_mode:=<true|false>` - Disable camera (default: `false`)
- `-p camera_topic:=<topic>` - Camera source (default: `/camera/image_raw`)
- `-p detection_confidence_threshold:=<0.0-1.0>` - Min confidence (default: `0.7`)
- `-p max_cotton_detections:=<int>` - Max per frame (default: `50`)
- `-p enable_debug_output:=<true|false>` - Debug images (default: `false`)
- `-p detection_mode:=<mode>` - Algorithm: `hsv_only`, `yolo_only`, `hybrid_fallback` (default: `hybrid_fallback`)

### Legacy Scripts (Deprecated)
```bash
# Old launch scripts (if present)
./scripts/launch/launch.sh
./scripts/launch/launch_production.sh
./scripts/launch/launch_minimal.sh
./scripts/launch/launch_robust.sh
```

## 🧹 Logs
```bash
# Simple cleanup
./scripts/monitoring/cleanup_logs.sh

# Advanced
./scripts/monitoring/clean_logs.sh status
./scripts/monitoring/clean_logs.sh clean --days 7
```

## ✅ Validation
```bash
# Quick check
./scripts/validation/quick_validation.sh

# End-to-end
./scripts/validation/end_to_end_validation.sh

# Parameters
./scripts/validation/comprehensive_parameter_validation.py
```

## 📦 Package
```bash
./scripts/build/create_upload_package.sh
```

## 📚 Documentation
- **Complete Guide**: `SCRIPTS_GUIDE.md`
- **Build Scripts**: `./build.sh --help`
- **Launch Variants**: `scripts/launch/LAUNCH_GUIDE.md`
- **Log Management**: `scripts/monitoring/LOG_MANAGEMENT_README.md`
- **Validation**: `scripts/validation/VALIDATION_GUIDE.md`
- **Test Infrastructure**: `./test.sh --help`

## 🔄 Backward Compatibility
All old script paths still work via symlinks!

## 🗄️ Archive
Original scripts: `archive/scripts_consolidated_20250930_100349/`

