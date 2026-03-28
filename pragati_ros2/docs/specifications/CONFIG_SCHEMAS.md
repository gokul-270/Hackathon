# Pragati Configuration Schemas

**Document Version:** 1.0  
**Date:** 2026-01-02  
**Status:** Active  
**Purpose:** Document YAML configuration file schemas for all packages

---

## Overview

This document defines the schema for each configuration file used in the Pragati system. Use this as a reference when modifying configurations or troubleshooting parameter issues.

**Configuration Locations:**
- `src/<package>/config/*.yaml` - Package-specific configs
- Launch files can override any parameter via arguments

---

## 1. Motor Control Configuration

### 1.1 mg6010_test.yaml

**Location:** `src/motor_control_ros2/config/mg6010_test.yaml`  
**Purpose:** MG6010-i6 motor testing and validation

#### Schema

```yaml
mg6010_test_node:
  ros__parameters:
    # CAN Interface (REQUIRED)
    interface_name: string    # CAN interface name (default: "can0")
    baud_rate: int            # CAN bitrate: 500000 (default), 1000000, 125000
    
    # Motor Identification (REQUIRED)
    node_id: int              # Motor ID 1-32
    can_id: hex               # CAN ID = 0x140 + node_id (e.g., 0x141)
    
    # Test Mode (REQUIRED)
    mode: string              # "status", "position", "velocity", "torque", "on_off", "angle"

motor_specifications:
  ros__parameters:
    # Electrical (for reference/validation)
    rated_voltage: float      # 24.0 V nominal
    voltage_min: float        # 7.4 V minimum
    voltage_max: float        # 32.0 V maximum
    rated_current: float      # 5.5 A
    max_current: float        # 33.0 A
    
    # Mechanical
    rated_torque: float       # 5.0 N.m
    max_torque: float         # 10.0 N.m
    gear_ratio: float         # 6.0 (i6 = 1:6)

safety_limits:
  ros__parameters:
    # Position Limits (CRITICAL)
    position_limit_min: float # -6.28318 rad (default)
    position_limit_max: float # 6.28318 rad (default)
    
    # Velocity Limits
    velocity_limit: float     # 5.0 rad/s (safe)
    velocity_limit_max: float # 10.0 rad/s (absolute max)
    
    # Temperature (CRITICAL for safety)
    temperature_warning: float  # 65.0 °C
    temperature_critical: float # 70.0 °C (E-stop threshold)
    temperature_max: float      # 80.0 °C
```

#### Key Parameters

| Parameter | Default | Range | Impact |
|-----------|---------|-------|--------|
| `baud_rate` | 500000 | 125k-1M | **Must match motor config** |
| `temperature_critical` | 70.0 | 60-80 | Triggers E-stop |
| `velocity_limit` | 5.0 | 0-10 | Affects pick speed |

---

### 1.2 production.yaml (Motor Control)

**Location:** `src/motor_control_ros2/config/production.yaml`  
**Purpose:** Production motor configuration for arm joints

#### Schema

```yaml
motor_controller:
  ros__parameters:
    # Joint Configuration (REQUIRED for each joint)
    joints:
      joint3:          # Base rotation joint
        type: string   # "mg6010" (required)
        can_id: hex    # Motor CAN ID (e.g., 0x141)
        direction: int # 1 or -1 (motor direction)
        offset: float  # Position offset in rad
        
      joint5:          # End effector joint
        type: string
        can_id: hex
        direction: int
        offset: float
    
    # Safety Monitor
    safety:
      enable: bool
      position_limits: [min, max]  # Per joint
      velocity_limit: float
      temperature_warning: float
      temperature_critical: float
    
    # CAN Interface
    can:
      interface: string  # "can0"
      bitrate: int       # 500000
```

---

## 2. Cotton Detection Configuration

### 2.1 production.yaml (Cotton Detection)

**Location:** `src/cotton_detection_ros2/config/production.yaml`  
**Purpose:** Production cotton detection settings

#### Schema

```yaml
cotton_detection_node:
  ros__parameters:
    # Detection Settings (REQUIRED)
    detection_confidence_threshold: float  # 0.0-1.0 (default: 0.7)
    max_cotton_detections: int             # Max per frame (default: 50)
    detection_mode: string                 # "depthai_direct" (only supported)
    
    # Debug (disable for production)
    enable_debug_output: bool              # false for production
    
    # DepthAI Configuration (CRITICAL)
    depthai:
      enable: bool                         # true to use camera
      model_path: string                   # Path to .blob file (REQUIRED)
      num_classes: int                     # 1 or 2 depending on model
      
      # Camera Settings
      camera_width: int                    # 416 (model input size)
      camera_height: int                   # 416 (model input size)
      camera_fps: int                      # 30 (reduce if thermal issues)
      
      # Detection
      confidence_threshold: float          # 0.0-1.0 (default: 0.3)
      
      # Depth
      enable_depth: bool                   # true for spatial detection
      depth_min_mm: float                  # 100.0 mm
      depth_max_mm: float                  # 5000.0 mm
      
      # Device
      device_id: string                    # "" = first available
      
      # Thermal Management (IMPORTANT)
      thermal:
        enable: bool                       # true
        warning_temp_c: float              # 70.0
        throttle_temp_c: float             # 80.0
        critical_temp_c: float             # 90.0
        throttle_fps: int                  # 15 (reduced FPS)
      
      # Exposure
      exposure:
        mode: string                       # "auto" or "manual"
        time_us: int                       # Manual exposure time
        iso: int                           # Manual ISO
    
    # Performance
    performance:
      max_processing_fps: float            # 30.0
      processing_timeout_ms: int           # 1000
      enable_monitoring: bool              # true
      detailed_logging: bool               # false for production
    
    # Workspace Bounds (meters)
    workspace:
      max_x: float                         # 2.0 m
      max_y: float                         # 1.5 m
      max_z: float                         # 3.0 m
      min_z: float                         # 0.0 m
    
    # Simulation
    simulation_mode: bool                  # false for production
```

#### Key Parameters

| Parameter | Default | Range | Impact |
|-----------|---------|-------|--------|
| `depthai.model_path` | - | valid path | **Must point to valid .blob** |
| `depthai.camera_fps` | 30 | 15-30 | Lower if overheating |
| `detection_confidence_threshold` | 0.7 | 0.3-0.9 | Affects false positive rate |
| `thermal.throttle_temp_c` | 80.0 | 70-90 | Auto-throttle trigger |

---

## 3. Yanthra Move Configuration

### 3.1 production.yaml (Yanthra Move)

**Location:** `src/yanthra_move/config/production.yaml`  
**Purpose:** Motion planning and arm control parameters

#### Schema

```yaml
yanthra_move:
  ros__parameters:
    # Operation Mode (CRITICAL)
    continuous_operation: bool             # true = loop, false = single run
    max_runtime_minutes: int               # -1 = infinite, 0 = defaults, >0 = custom
    
    # Start Switch
    start_switch.timeout_sec: float        # -1.0 = infinite wait
    start_switch.enable_wait: bool         # true for production
    start_switch.prefer_topic: bool        # true = topic, false = GPIO
    
    # Joint Configuration (REQUIRED)
    joint3_init/homing_position: float     # Home position (rotations)
    joint4_init/homing_position: float     # Home position (meters)
    joint5_init/homing_position: float     # Home position (meters)
    joint5_init/hardware_offset: float     # Physical offset (meters)
    joint5_init/gear_ratio: float          # 20.943951
    
    # Timing Parameters (CRITICAL for cycle time)
    min_sleep_time_formotor_motion: float  # 0.2 s (CAN latency)
    inter_joint_delay: float               # 0.3 s (between joints)
    cotton_settle_delay: float             # 0.2 s (before compressor)
    
    # End Effector Timing
    delays/EERunTimeDuringL5ForwardMovement: float  # 0.8 s grab time
    delays/ee_post_joint5_delay: float              # 0.3 s stability
    compressor_burst_duration: float                # 0.5 s drop time
    
    # Hardware Control
    global_vaccum_motor: bool              # true
    end_effector_enable: bool              # true
    enable_gpio: bool                      # true for hardware
    
    # Simulation
    simulation_mode: bool                  # false for production
    use_simulation: bool                   # false for production
```

#### Key Parameters

| Parameter | Default | Impact |
|-----------|---------|--------|
| `continuous_operation` | true | Loop vs single cycle |
| `inter_joint_delay` | 0.3 | Affects cycle time |
| `delays/EERunTimeDuringL5ForwardMovement` | 0.8 | Grasp duration |
| `simulation_mode` | false | **Must be false for hardware** |

---

## 4. Vehicle Control Configuration

### 4.1 production.yaml (Vehicle Control)

**Location:** `src/vehicle_control/config/production.yaml`  
**Purpose:** Vehicle navigation and drive motor settings

#### Schema

```yaml
vehicle_control:
  ros__parameters:
    # Motor Configuration
    drive_motors:
      can_interface: string                # "can0"
      bitrate: int                         # 500000
      motor_ids: [int, int, int]           # 3 drive motor IDs
    
    steering_motors:
      motor_ids: [int, int, int]           # 3 steering motor IDs
    
    # Physical Parameters
    wheel_diameter: float                  # meters
    wheelbase: float                       # meters
    track_width: float                     # meters
    
    # Control Parameters
    max_linear_velocity: float             # m/s
    max_angular_velocity: float            # rad/s
    
    # Safety
    enable_collision_avoidance: bool
    obstacle_stop_distance: float          # meters
```

---

## 5. Configuration Validation

### Pre-Flight Checklist

Before deploying, verify:

- [ ] **CAN bitrate** matches across all motor configs (500 kbps default)
- [ ] **Model path** (`depthai.model_path`) points to valid .blob file
- [ ] **simulation_mode** is `false` for hardware deployment
- [ ] **Temperature thresholds** are appropriate for environment
- [ ] **Joint limits** match physical hardware
- [ ] **Hardware offsets** are calibrated

### Common Configuration Errors

| Error | Cause | Fix |
|-------|-------|-----|
| No motor response | Bitrate mismatch | Verify `baud_rate: 500000` |
| Detection timeout | Wrong model path | Check `model_path` exists |
| Camera overheat | FPS too high | Reduce `camera_fps` to 15-20 |
| Joint limit error | Wrong offsets | Recalibrate `homing_position` |
| Pick cycle too slow | Long delays | Reduce timing parameters |

---

## 6. Parameter Override Examples

### Override via Launch

```bash
# Override detection confidence
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
  detection_confidence_threshold:=0.5

# Override simulation mode
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=true
```

### Override via Command Line

```bash
ros2 run cotton_detection_ros2 cotton_detection_node \
  --ros-args -p depthai.camera_fps:=20
```

### Check Current Parameters

```bash
# List all parameters
ros2 param list /cotton_detection_node

# Get specific parameter
ros2 param get /cotton_detection_node depthai.camera_fps

# Set parameter at runtime
ros2 param set /cotton_detection_node depthai.camera_fps 20
```

---

## Update History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-02 | System | Initial schema documentation |

---

**Next Update:** After configuration changes or new parameters  
**Owner:** Engineering Team
