# Configuration & Parameters

**Part of:** [Pragati Production System Documentation](../README.md)

---

## ⚙️ Configuration Management

### YAML Configuration Files

**Motor Configuration (`config/production.yaml`):**
```yaml
motor_control_ros2:
  ros__parameters:
    # Per-Arm Configuration (example for Arm 1)
    # Each Raspberry Pi runs this config locally
    
    # Motor 1: Base/Rotation Joint
    joint_1:
      motor_type: mg6010e    # MG6010E-i6 (Enhanced model)
      can_id: 1              # CAN ID: 0x141
      direction: 1           # 1 or -1
      transmission_factor: 6.0  # 6:1 internal gear ratio (i6 model)
      joint_offset: 0.0      # Calibration offset (from homing)
      
      # Control gains (uint8_t, 0-255)
      p_gain: 50
      v_gain: 20
      v_int_gain: 0
      
      # Safety limits
      position_min: -3.14159  # -180°
      position_max: 3.14159   # +180°
      velocity_limit: 5.0     # rad/s
      current_limit: 15.0     # Amperes (MG6010E max: 33A)
      
      # Temperature limits
      temperature_warning: 65.0   # °C
      temperature_critical: 70.0  # °C
    
    # Motor 2: Middle Segment Joint
    joint_2:
      motor_type: mg6010e
      can_id: 2              # CAN ID: 0x142
      # ... similar config ...
    
    # Motor 3: End Effector Joint
    joint_3:
      motor_type: mg6010e
      can_id: 3              # CAN ID: 0x143
      # ... similar config ...

# CAN Bus Configuration
can_interface:
  ros__parameters:
    interface_name: "can0"
    bitrate: 500000  # 500 kbps (CRITICAL: must match motor)
    timeout_ms: 10
    retry_count: 3
```

**Camera Configuration (`config/cotton_detection_cpp.yaml`):**
```yaml
cotton_detection:
  ros__parameters:
    # OAK-D Lite Camera settings
    camera:
      width: 416                    # Neural network input resolution
      height: 416
      fps: 30                       # Camera frame rate
      color_order: "BGR"            # OpenCV compatible
      enable_depth: true            # Enable stereo depth calculation
      device_id: ""                 # Empty = auto-detect first camera
    
    # Stereo Depth settings
    depth:
      min_mm: 100.0                 # Minimum depth: 10cm
      max_mm: 5000.0                # Maximum depth: 5 meters
      median_filter: 7              # Median filter kernel (reduce noise)
      confidence_threshold: 200     # Depth confidence (0-255)
    
    # Detection parameters
    confidence_threshold: 0.5       # YOLO confidence threshold
    min_cotton_size: 20             # Minimum bounding box size (pixels)
    max_cotton_size: 400            # Maximum bounding box size (pixels)
    
    # Model paths (DepthAI blob format)
    model_path: "/home/ubuntu/pragati/models/yolov8_cotton.blob"
    # Note: .blob files compiled for Myriad X VPU using blobconverter
    
    # Processing
    detection_mode: "continuous"    # continuous | on_demand
    max_detections: 10              # Max cotton per frame
    publish_debug_image: false      # Save bandwidth in production

---

