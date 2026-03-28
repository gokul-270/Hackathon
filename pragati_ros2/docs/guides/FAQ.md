# Frequently Asked Questions (FAQ)

## Table of Contents
- [General](#general)
- [Motor Control](#motor-control)
- [Cotton Detection](#cotton-detection)
- [Motion Planning](#motion-planning)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

---

## General

### Q: What is Pragati ROS2?
**A:** Pragati is a ROS2-based robotic system for automated cotton harvesting. It integrates computer vision (YOLO-based detection), motion planning (MoveIt2), and motor control (MG6010/ODrive) into a coordinated system.

### Q: What ROS2 version is required?
**A:** ROS2 Humble (Ubuntu 22.04) is the primary supported version. Other distributions may work but are not officially tested.

### Q: Can I run Pragati in simulation mode?
**A:** Yes! Set `simulation_mode:=true` in launch files to run without hardware. Motor commands will be logged but not executed, and vision can use recorded data.

### Q: What are the hardware requirements?
**A:** 
- **Motors:** MG6010-i6 motors (primary) or ODrive motors (legacy support)
- **Vision:** Intel RealSense D435/D455 camera
- **Compute:** x86_64 Linux system (tested on Ubuntu 22.04)
- **CAN:** CAN interface (for MG6010 motors)

---

## Motor Control

### Q: How do I switch between MG6010 and ODrive motors?
**A:** Pragati primarily supports MG6010 motors via the `motor_control_ros2` package. ODrive support is legacy. To configure:
1. Edit `config/motor_config.yaml`
2. Set `motor_type: mg6010` or `motor_type: odrive`
3. Adjust parameters for your motor model

### Q: What CAN baud rate should I use for MG6010 motors?
**A:** Pragati is configured for **500 kbps** on the CAN bus. Keep the CAN interface and motor settings aligned (bitrate mismatch will cause timeouts and BUS-OFF).

### Q: How do I calibrate motors?
**A:** 
```bash
ros2 service call /motor_control/calibrate_motor motor_control_ros2/srv/MotorCalibration "{motor_id: 1}"
```
See `docs/MOTOR_TUNING_GUIDE.md` for detailed calibration procedures.

### Q: Motors won't move - what should I check?
**A:**
1. **CAN connection:** `candump can0` - verify CAN traffic
2. **Motor power:** Check VBus voltage (should be 24-48V depending on system)
3. **Homing:** Motors must be homed before motion: `ros2 service call /joint_homing ...`
4. **Safety:** Check E-stop status and safety monitor logs
5. **Logs:** `ros2 topic echo /diagnostics` for error messages

### Q: How do I tune PID parameters?
**A:** See `docs/MOTOR_TUNING_GUIDE.md` for comprehensive tuning guide. Quick summary:
- Start with conservative values (Kp=10, Ki=5)
- Increase Kp for faster response
- Add Ki to eliminate steady-state error
- Use Kd sparingly (start with 0)

---

## Cotton Detection

### Q: Which YOLO model does Pragati use?
**A:** YOLOv8n (nano) for speed, trained on custom cotton dataset. Model file: `models/cotton_yolo.onnx`. You can swap models by updating `config/detection_config.yaml`.

### Q: How do I train a custom model?
**A:** 
1. Collect and label cotton images (YOLO format)
2. Train using Ultralytics YOLOv8: `yolo train data=cotton.yaml model=yolov8n.pt`
3. Export to ONNX: `yolo export model=best.pt format=onnx`
4. Update config to point to new model

### Q: Detection is slow - how do I improve performance?
**A:**
- **Use smaller model:** YOLOv8n is fastest (current default)
- **Reduce resolution:** Set `input_width: 416` and `input_height: 416` in config
- **Enable async inference:** Set `async_inference: true` (experimental)
- **GPU acceleration:** Ensure ONNX Runtime has CUDA provider

### Q: How do I adjust detection confidence threshold?
**A:** Edit `config/detection_config.yaml`:
```yaml
confidence_threshold: 0.5  # Lower = more detections (more false positives)
nms_threshold: 0.4        # Non-max suppression threshold
```

---

## Motion Planning

### Q: How do I adjust arm reach limits?
**A:** Edit `config/yanthra_move_config.yaml`:
```yaml
workspace_limits:
  x_min: 0.1
  x_max: 2.0
  y_min: -1.5
  y_max: 1.5
  z_min: -0.5
  z_max: 1.5
```

### Q: Motion planning fails frequently - what's wrong?
**A:**
- **Check reachability:** Target may be outside workspace
- **Collision avoidance:** Ensure `self_collision_checking: true` in MoveIt config
- **Planning time:** Increase `planning_time: 10.0` in config
- **Start state:** Verify robot starts from valid joint configuration

### Q: How do I home the robot arm?
**A:**
```bash
ros2 service call /yanthra_move/home_all std_srvs/srv/Trigger
```
Or individual joints:
```bash
ros2 service call /joint_homing motor_control_ros2/srv/JointHoming "{joint_id: 1}"
```

---

## Troubleshooting

### Q: CAN interface shows "No buffer space available"
**A:** CAN buffer overflow. Solutions:
1. Reduce CAN traffic frequency
2. Increase buffer: `sudo ip link set can0 txqueuelen 1000`
3. Check for CAN bus errors: `ip -s -d link show can0`

### Q: Camera not detected
**A:**
1. Check USB connection: `lsusb | grep Intel`
2. Install RealSense SDK: `sudo apt install ros-humble-realsense2-camera`
3. Launch camera node separately to test: `ros2 launch realsense2_camera rs_launch.py`

### Q: "Transform timeout" errors
**A:** TF tree is incomplete:
1. Check TF tree: `ros2 run tf2_tools view_frames`
2. Verify robot_state_publisher is running: `ros2 node list | grep robot_state`
3. Launch URDF: `ros2 launch robo_description display.launch.py`

### Q: Build fails with missing dependencies
**A:**
```bash
rosdep install --from-paths src --ignore-src -r -y
```
If specific package missing:
```bash
sudo apt install ros-humble-<package-name>
```

### Q: High CPU usage from YOLO detection
**A:**
- Reduce camera framerate: `fps: 15` in camera config
- Skip frames: `process_every_n_frames: 2` in detection config  
- Use smaller model: YOLOv8n instead of YOLOv8s
- Enable GPU acceleration

---

## Development

### Q: How do I run unit tests?
**A:**
```bash
colcon test --packages-select motor_control_ros2
colcon test-result --verbose
```

### Q: How do I generate coverage reports?
**A:**
```bash
# Build with coverage
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="--coverage"

# Run tests
colcon test

# Generate report
gcovr -r . --html --html-details -o coverage.html
```

### Q: How do I add a new motor controller?
**A:**
1. Implement `MotorControllerInterface` (see `include/motor_control_ros2/motor_abstraction.hpp`)
2. Add controller class inheriting from interface
3. Register in `motor_abstraction.cpp` factory
4. Update config to support new motor type

### Q: How do I contribute?
**A:** See `CONTRIBUTING.md` for guidelines:
1. Fork repository
2. Create feature branch
3. Write tests for new code
4. Submit pull request with clear description
5. Ensure CI passes (build, tests, linting)

### Q: Code style and formatting?
**A:**
- **C++:** Follow ROS2 style guide, use clang-format
- **Python:** PEP8, use black formatter
- **Pre-commit:** Run `scripts/validation/format_code.sh` before commit

### Q: How do I enable debug logging?
**A:**
Set log level in launch file:
```xml
<node pkg="motor_control_ros2" exec="motor_control_node" output="screen">
  <param name="log_level" value="DEBUG"/>
</node>
```
Or via command line:
```bash
ros2 run motor_control_ros2 motor_control_node --ros-args --log-level DEBUG
```

---

## Hardware-Specific

### Q: MG6010 motor IDs - how are they assigned?
**A:** Motor IDs (1-32) are set via DIP switches on motor controller or software configuration. Default arbitration ID = `0x140 + motor_id`.

### Q: Safe voltage ranges for MG6010 motors?
**A:**
- **24V system:** 22-26V safe range
- **48V system:** 44-52V safe range  
Below minimum: brownout protection triggers. Above maximum: overvoltage fault.

### Q: How often should I calibrate encoders?
**A:** 
- **Initial setup:** Always calibrate
- **After maintenance:** Recalibrate if motor dismounted
- **Periodic:** Every 6 months or if drift observed
- **After crash:** Immediately recalibrate

---

## Performance Optimization

### Q: How can I reduce system latency?
**A:**
1. **Use cyclonedds:** `export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`
2. **Real-time kernel:** Install `linux-image-rt` for deterministic timing
3. **CPU isolation:** Reserve cores for critical nodes using `isolcpus`
4. **Network tuning:** Increase UDP buffer sizes

### Q: Recommended launch sequence?
**A:**
```bash
# 1. Hardware interfaces first
ros2 launch motor_control_ros2 motor_control.launch.py

# 2. Wait for motors to initialize (5 seconds)
sleep 5

# 3. Vision system
ros2 launch cotton_detection_ros2 detection.launch.py

# 4. Motion planning
ros2 launch yanthra_move yanthra_move.launch.py

# 5. High-level control
ros2 launch vehicle_control vehicle_control.launch.py
```

---

## Getting More Help

- **Documentation:** `docs/` directory
- **Examples:** `scripts/validation/` directory
- **Issues:** GitHub issue tracker
- **Logs:** Check `~/.ros/log/` for detailed logs

**Last Updated:** 2025-10-21
