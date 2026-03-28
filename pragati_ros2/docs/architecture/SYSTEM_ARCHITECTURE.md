# System Architecture - Pragati ROS2

**Last Updated:** 2025-10-15  
**Phase:** Phase 1 (Stop-and-Go Multi-Cotton)  
**Status:** Software Complete, Hardware Pending

---

## Overview

Pragati is a distributed cotton-picking robot system with:
- **4 independent picking arms** (Raspberry Pi 4 each)
- **1 vehicle controller** (Raspberry Pi 4)
- **MQTT inter-controller communication**
- **ROS2 Jazzy intra-controller communication**

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Pragati Robot System                        │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐│
│  │   Arm 1    │  │   Arm 2    │  │   Arm 3    │  │   Arm 4    ││
│  │   (RPi4)   │  │   (RPi4)   │  │   (RPi4)   │  │   (RPi4)   ││
│  │            │  │            │  │            │  │            ││
│  │  + Camera  │  │  + Camera  │  │  + Camera  │  │  + Camera  ││
│  │  + Motors  │  │  + Motors  │  │  + Motors  │  │  + Motors  ││
│  │  + Vacuum  │  │  + Vacuum  │  │  + Vacuum  │  │  + Vacuum  ││
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘│
│        │                │                │                │      │
│        └────────────────┴────────────────┴────────────────┘      │
│                                │                                 │
│                           MQTT Bridge                            │
│                                │                                 │
│                      ┌─────────┴──────────┐                      │
│                      │  Vehicle Controller│                      │
│                      │      (RPi4)        │                      │
│                      │                    │                      │
│                      │  + Drivetrain      │                      │
│                      │  + Coordination    │                      │
│                      │  + Navigation      │                      │
│                      └────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Arm Controller Architecture

Each arm is an autonomous picking unit:

```
┌───────────────────────── Arm Controller (ROS2) ─────────────────────┐
│                                                                      │
│  ┌─────────────────────┐         ┌──────────────────────┐          │
│  │ Cotton Detection    │         │  Motor Control       │          │
│  │ - OAK-D Lite Camera │         │  - MG6010 Motors (3) │          │
│  │ - YOLOv8 + HSV      │────────▶│  - CAN Interface     │          │
│  │ - 3D Coordinates    │         │  - Safety Monitor    │          │
│  └─────────────────────┘         └──────────────────────┘          │
│            │                                │                       │
│            │        ┌───────────────────────┘                       │
│            │        │                                               │
│            ▼        ▼                                               │
│  ┌────────────────────────────┐                                    │
│  │   Yanthra Move             │                                    │
│  │   - Motion Planning        │                                    │
│  │   - Trajectory Execution   │                                    │
│  │   - Vacuum Control (GPIO)  │                                    │
│  │   - LED Control (GPIO)     │                                    │
│  └────────────────────────────┘                                    │
│            │                                                        │
│            ▼                                                        │
│  ┌────────────────────────────┐                                    │
│  │   MQTT Bridge              │                                    │
│  │   - Status reporting       │                                    │
│  │   - Coordination messages  │                                    │
│  └────────────────────────────┘                                    │
└──────────────────────────────────────────────────────────────────-─┘
```

---

## Data Flow Diagram

### Phase 1: Stop-and-Go Cotton Picking

```
1. Vehicle Stops
      │
      ▼
2. Cotton Detection (All 4 Arms)
   ┌──────────────────────────────────┐
   │ OAK-D Camera → YOLOv8 + HSV      │
   │ Output: List of cotton (X,Y,Z)   │
   │ Classification: PICKABLE / NOT   │
   └──────────┬───────────────────────┘
              │
              ▼
3. Sequential Processing (per arm)
   ┌────────────────────────────────┐
   │ For each PICKABLE cotton:      │
   │   1. Request next target       │
   │   2. Compute IK                │
   │   3. Move arm                  │
   │   4. Activate vacuum           │
   │   5. Retract                   │
   │   6. Deposit                   │
   │   7. Release vacuum            │
   └────────┬───────────────────────┘
            │
            ▼
4. All Arms Complete
      │
      ▼
5. Vehicle Moves Forward
      │
      └──▶ Repeat from Step 1
```

---

## Component Interaction

### Cotton Detection → Motor Control

```
┌─────────────────┐
│ Cotton Detector │
│  (C++ Node)     │
└────────┬────────┘
         │ Publish: /cotton_detections
         │          (DetectionArray)
         │
         │ Service: /next_target
         │          (Trigger)
         ▼
┌─────────────────┐
│  Yanthra Move   │
│  (Coordinates)  │
└────────┬────────┘
         │ Compute: Inverse Kinematics
         │          (X,Y,Z → Joint Angles)
         │
         │ Publish: /joint_commands
         │          (Float64MultiArray)
         ▼
┌─────────────────┐
│ Motor Control   │
│  (Hardware IF)  │
└────────┬────────┘
         │ CAN Bus: Position Commands
         │          (500 kbps)
         ▼
┌─────────────────┐
│ MG6010 Motors   │
│  (3 per arm)    │
└─────────────────┘
```

---

## Motor Control Detailed

```
┌────────────────────────── motor_control_ros2 ─────────────────────────┐
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ GenericHardwareInterface (ros2_control)                      │    │
│  │  - Manages joint states                                      │    │
│  │  - Routes commands to motor controllers                      │    │
│  └────────┬─────────────────────────────────────────────────────┘    │
│           │                                                            │
│           ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ MG6010MotorController (per motor)                            │    │
│  │  - Protocol: LK-TECH CAN V2.35                               │    │
│  │  - Modes: Position / Velocity / Torque                       │    │
│  │  - PID Control (configurable)                                │    │
│  └────────┬─────────────────────────────────────────────────────┘    │
│           │                                                            │
│           ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ CANInterface (SocketCAN)                                     │
│  │  - Bitrate: 500 kbps                                         │
│  │  - Read/Write CAN frames                                     │    │
│  └────────┬─────────────────────────────────────────────────────┘    │
│           │                                                            │
│  ┌────────▼────────┐                                                  │
│  │ Safety Monitor  │──────────────────┐                              │
│  │  - Position     │                  │                              │
│  │  - Velocity     │                  │                              │
│  │  - Temperature  │                  │                              │
│  │  - Voltage      │                  │                              │
│  │  - Comm Timeout │                  │                              │
│  │  - E-STOP (GPIO)│                  │                              │
│  └─────────────────┘                  │                              │
│                                        ▼                              │
│                              ┌──────────────────┐                     │
│                              │ Emergency Actions│                     │
│                              │  - Stop motors   │                     │
│                              │  - LED signal    │                     │
│                              │  - Log event     │                     │
│                              └──────────────────┘                     │
└────────────────────────────────────────────────────────────────────-──┘
```

---

## Cotton Detection Pipeline

```
┌────────────── Cotton Detection Pipeline ──────────────────┐
│                                                            │
│  OAK-D Lite Camera                                         │
│       │                                                    │
│       ├──▶ RGB Stream (1920x1080 @ 30 Hz)                 │
│       │       │                                            │
│       │       ▼                                            │
│       │  ┌──────────────────┐                             │
│       │  │ HSV Detection    │                             │
│       │  │  - Color filter  │                             │
│       │  │  - Contours      │                             │
│       │  │  - Bounding boxes│                             │
│       │  └────────┬─────────┘                             │
│       │           │                                        │
│       ├──▶ Depth Stream (Stereo)                          │
│       │       │                                            │
│       │       ▼                                            │
│       │  ┌──────────────────┐                             │
│       │  │ Spatial XYZ      │                             │
│       │  │  - Disparity map │                             │
│       │  │  - Depth → 3D    │                             │
│       │  │  - Calibration   │                             │
│       │  └────────┬─────────┘                             │
│       │           │                                        │
│       └──▶ NN Engine (YOLOv8n)                            │
│               │                                            │
│               ▼                                            │
│          ┌──────────────────┐                             │
│          │ YOLO Detection   │                             │
│          │  - Object class  │                             │
│          │  - Confidence    │                             │
│          │  - Bounding box  │                             │
│          └────────┬─────────┘                             │
│                   │                                        │
│      ┌────────────┴────────────┐                          │
│      │   Fusion & Classification│                         │
│      │    - Combine HSV + YOLO │                          │
│      │    - Size/shape check   │                          │
│      │    - PICKABLE logic     │                          │
│      └────────┬────────────────┘                          │
│               │                                            │
│               ▼                                            │
│      ┌──────────────────────┐                             │
│      │ Detection Results    │                             │
│      │  - ID, X, Y, Z       │                             │
│      │  - Confidence        │                             │
│      │  - Pickability       │                             │
│      └──────────────────────┘                             │
│               │                                            │
│               ▼                                            │
│      ROS2 Topic: /cotton_detections                       │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## Network Architecture

### Phase 1: Stop-and-Go (Current)

```
┌─────────────────────────────────────────────────────┐
│                  WiFi / Ethernet                    │
└──┬────────┬────────┬────────┬────────┬─────────────┘
   │        │        │        │        │
┌──▼───┐ ┌─▼───┐ ┌──▼───┐ ┌─▼───┐ ┌──▼────┐
│ Arm1 │ │Arm2 │ │ Arm3 │ │Arm4 │ │Vehicle│
│ RPi4 │ │RPi4 │ │ RPi4 │ │RPi4 │ │ RPi4  │
└──────┘ └─────┘ └──────┘ └─────┘ └───────┘
   │        │        │        │        │
   └────────┴────────┴────────┴────────┘
              MQTT Broker
         (Topic: /pragati/...)
```

**MQTT Topics:**
- `/pragati/arm{1-4}/status` - Arm state
- `/pragati/arm{1-4}/cotton_count` - Pick statistics
- `/pragati/vehicle/command` - Movement commands
- `/pragati/vehicle/position` - Vehicle location

---

## Configuration Management

```
Config Files Location:
  src/<package>/config/

Motor Control:
  - motors_production.yaml    # MG6010 parameters
  - motors_test.yaml           # Safe test values
  - hardware_interface.yaml   # ros2_control config

Cotton Detection:
  - cotton_detection.yaml     # HSV thresholds, YOLO model
  - camera_calibration.yaml   # Intrinsics, extrinsics

Yanthra Move:
  - yanthra.yaml              # Joint limits, IK params
  - picking_sequence.yaml     # Pick-place trajectories
```

---

## Timing and Performance

### Control Loop Frequencies

| Component | Frequency | Latency | Notes |
|-----------|-----------|---------|-------|
| Motor Control Loop | 100-200 Hz | < 10 ms | PID update rate |
| Cotton Detection | 10-30 Hz | 30-100 ms | YOLOv8 inference |
| Yanthra Move Planning | 50 Hz | < 20 ms | Trajectory generation |
| MQTT Status Updates | 1 Hz | 100-200 ms | Inter-controller |
| Safety Monitor | 100 Hz | < 5 ms | Critical checks |

### Pick Cycle Timing (Estimated)

| Step | Duration | Notes |
|------|----------|-------|
| Detect cotton | 1-3 sec | All arms parallel |
| Move to approach | 0.5-1 sec | Per cotton |
| Move to pick | 0.3-0.5 sec | |
| Activate vacuum | 0.2 sec | |
| Retract | 0.5-1 sec | |
| Move to deposit | 1-2 sec | |
| Release | 0.2 sec | |
| Return to home | 1-2 sec | |
| **Total per cotton** | **4-8 sec** | |
| **Throughput (4 arms, 3 cotton/stop)** | **600-900 picks/hour** | Phase 1 target |

---

## Safety Architecture

```
┌──────────────────── Safety System ────────────────────┐
│                                                        │
│  Hardware Layer                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │ Emergency Stop Button (GPIO)                 │    │
│  │   - Hardwired to motor power relay           │    │
│  │   - Software monitoring (redundant)          │    │
│  └────────────────┬─────────────────────────────┘    │
│                   │                                    │
│  Software Layer   ▼                                    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Safety Monitor Node (100 Hz)                 │    │
│  │  - Position limits: Joint-specific           │    │
│  │  - Velocity limits: Configurable             │    │
│  │  - Temperature: < 80°C                       │    │
│  │  - Voltage: 36-52V                           │    │
│  │  - Comm timeout: < 500 ms                    │    │
│  │  - GPIO E-STOP: Polled at 100 Hz             │    │
│  └────────────────┬─────────────────────────────┘    │
│                   │                                    │
│  Action Layer     ▼                                    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Emergency Response                           │    │
│  │  1. Halt all motor commands (immediate)      │    │
│  │  2. Publish /diagnostics ERROR               │    │
│  │  3. Flash error LED                          │    │
│  │  4. Log event with timestamp                 │    │
│  │  5. Require manual reset (service call)      │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## Scalability (Phase 2)

### Continuous Operation Architecture (Future)

```
Enhancements for Phase 2:
- Vehicle moves continuously (no stops)
- Predictive cotton positioning
- Real-time camera streaming @ 30 Hz
- Multi-arm parallel picking
- Dynamic trajectory planning

Target: 1,800-2,000 picks/hour (8-10× improvement)
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **OS** | Ubuntu 22.04 (ARM64) |
| **ROS** | ROS2 Jazzy |
| **Middleware** | Cyclone DDS (recommended) |
| **Motor Protocol** | LK-TECH CAN V2.35 |
| **Camera API** | DepthAI C++ SDK |
| **Vision** | YOLOv8n (OpenCV DNN / DepthAI NN) |
| **Control** | ros2_control framework |
| **IPC** | MQTT (Eclipse Mosquitto) |
| **Build** | colcon |
| **Language** | C++ (core), Python (tools) |

---

## Related Documentation

- **Package READMEs:**
  - [motor_control_ros2](../../src/motor_control_ros2/README.md)
  - [cotton_detection_ros2](../../src/cotton_detection_ros2/README.md)
  - [yanthra_move](../../src/yanthra_move/README.md)
- **Guides:**
  - [Motor Tuning](../guides/MOTOR_TUNING_GUIDE.md)
  - [Troubleshooting](../guides/TROUBLESHOOTING.md)
- **Status:**
  - [Status Tracker](../status/STATUS_TRACKER.md)
  - [TODO Master](../TODO_MASTER.md)

---

**Version:** 1.0  
**Phase:** 1 (Stop-and-Go)  
**Last Updated:** 2025-10-15
