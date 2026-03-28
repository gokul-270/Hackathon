# Pragati Cotton Picking Robot
## Technical Specification Document (TSD)

**Document Version:** 1.1 (Draft)
**Date:** 2025-12-16
**Status:** Draft - Hardware & Performance Specs Updated
**Last Updated:** 2025-12-16
**Owner:** Pragati Robotics Engineering Team

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | System | Initial consolidated technical specification |
| 1.1 | 2025-12-16 | System + User | Updated hardware (RPi 4B, 3-wheel, motors with specs), CAN 500kbps default, continuous operation required, performance targets, field trial details |

**Review & Approval:**
- [ ] Lead Engineer Review
- [ ] Software Architecture Review
- [ ] Hardware Engineering Review
- [ ] Quality Assurance Review

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Architecture](#2-system-architecture)
3. [Hardware Specifications](#3-hardware-specifications)
4. [Software Architecture](#4-software-architecture)
5. [Component Specifications](#5-component-specifications)
6. [Interface Specifications](#6-interface-specifications)
7. [Communication Protocols](#7-communication-protocols)
8. [Data Structures & Algorithms](#8-data-structures--algorithms)
9. [Safety & Monitoring Systems](#9-safety--monitoring-systems)
10. [Configuration Management](#10-configuration-management)
11. [Build & Deployment](#11-build--deployment)
12. [Testing & Validation](#12-testing--validation)
13. [Performance Optimization](#13-performance-optimization)
14. [Troubleshooting & Diagnostics](#14-troubleshooting--diagnostics)
15. [Appendices](#15-appendices)

---

## 1. Introduction

### 1.1 Purpose

This Technical Specification Document (TSD) provides comprehensive technical details for the Pragati Cotton Picking Robot system. It is intended for:

- **Software Engineers:** Implementation details, APIs, data structures
- **Hardware Engineers:** Component specs, electrical interfaces, mechanical design
- **System Integrators:** Assembly procedures, calibration, testing
- **QA Engineers:** Test specifications, validation procedures
- **Maintenance Personnel:** Diagnostics, troubleshooting, repair

### 1.2 Scope

This document covers:
- Complete system architecture (hardware + software)
- Detailed component specifications
- Interface definitions and protocols
- Configuration and deployment procedures
- Testing and validation procedures

### 1.3 Related Documents

- **Product Requirements Document (PRD):** High-level requirements and success criteria
- **System Architecture:** `docs/architecture/SYSTEM_ARCHITECTURE.md`
- **ROS2 Interface Spec:** `docs/ROS2_INTERFACE_SPECIFICATION.md`
- **Package READMEs:** Individual package documentation in `src/*/README.md`

### 1.4 Document Conventions

**Status Indicators:**
- ✅ **VALIDATED:** Tested and verified working
- 🚧 **IMPLEMENTED:** Code exists but needs validation
- 📝 **PLANNED:** Specified but not yet implemented
- ⚠️ **NEEDS VERIFICATION:** Information may be outdated or incomplete
- ⚠️ **NEEDS SPECIFICATION:** Information missing, to be determined

---

## 2. System Architecture

### 2.1 Overall System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Pragati Robot System                           │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │         Central Control (Main Computer)                     │  │
│  │         - Vehicle Navigation & Planning                     │  │
│  │         - Multi-Arm Coordination (MQTT Broker)              │  │
│  │         - Mission Management                                │  │
│  │         - Web Dashboard Server                              │  │
│  │         - Data Aggregation & Logging                        │  │
│  └────┬───────────┬───────────┬───────────┬──────────────────┘  │
│       │           │           │           │                      │
│       │  Ethernet / WiFi Network                                 │
│       │           │           │           │                      │
│  ┌────▼────┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐                  │
│  │ ARM 1   │ │ ARM 2  │ │ ARM 3  │ │ ARM 4  │  (5, 6 planned)  │
│  │ Node    │ │ Node   │ │ Node   │ │ Node   │                  │
│  │ (RPi 4B)│ │(RPi 4B)│ │(RPi 4B)│ │(RPi 4B)│                  │
│  └────┬────┘ └───┬────┘ └───┬────┘ └───┬────┘                  │
│       │          │          │          │                         │
└───────┼──────────┼──────────┼──────────┼─────────────────────────┘
        │          │          │          │
    ┌───▼──┐   ┌──▼──┐   ┌──▼──┐   ┌──▼──┐
    │Camera│   │ Cam │   │ Cam │   │ Cam │  OAK-D Lite
    └──────┘   └─────┘   └─────┘   └─────┘
    ┌───▼──────────────────────────────┐
    │ 3× MG6010E-i6 Motors (CAN Bus)   │
    │ + End Effector (Vacuum, GPIO)    │
    └──────────────────────────────────┘
```

### 2.2 Distributed Architecture

**Design Philosophy:**
- **Autonomy:** Each arm is self-contained with local compute and sensors
- **Scalability:** Add arms without redesigning core architecture
- **Fault Tolerance:** Failure of one arm doesn't stop others
- **Load Distribution:** Processing distributed across multiple Raspberry Pis

**Communication Layers:**
1. **Intra-Arm (ROS2):** Components within one arm communicate via ROS2 topics/services
2. **Inter-Arm (MQTT):** Arms coordinate via lightweight MQTT messages
3. **External (REST/WebSocket):** Dashboard and monitoring via HTTP/WebSocket

### 2.3 Compute Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Each Arm Node (Raspberry Pi 4B, 4GB RAM)               │
│                                                          │
│  Operating System: Ubuntu 24.04 (ARM64)                 │
│  ROS2: Jazzy                                             │
│  Middleware: Cyclone DDS                                │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  ROS2 Workspace: /home/ubuntu/pragati_ros2        │  │
│  │                                                     │  │
│  │  Packages:                                         │  │
│  │  - cotton_detection_ros2  (C++ node)              │  │
│  │  - motor_control_ros2     (C++ controllers)       │  │
│  │  - yanthra_move           (C++ motion planning)   │  │
│  │  - robot_description      (URDF, RViz)            │  │
│  │  - vehicle_control        (C++ navigation)        │  │
│  │  - common_utils           (Shared libraries)      │  │
│  │  - pattern_finder         (ArUco detection)       │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Hardware Interfaces:                             │  │
│  │  - USB: OAK-D Lite Camera                         │  │
│  │  - CAN: SocketCAN (can0) → 3× Motors             │  │
│  │  - GPIO: End effector, LEDs, E-stop              │  │
│  │  - Network: Eth0/WiFi → MQTT + Dashboard         │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.4 Software Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Operating System** | Ubuntu 24.04 (ARM64) | Base OS |
| **ROS Framework** | ROS2 Jazzy | Robot middleware |
| **DDS Middleware** | Cyclone DDS | Message transport |
| **Build System** | colcon + CMake | Package building |
| **Vision SDK** | DepthAI C++ SDK | Camera interface |
| **Neural Network** | YOLOv8n (DepthAI NN) | Object detection |
| **Control Framework** | ros2_control | Motor control abstraction |
| **Messaging** | MQTT (Mosquitto) | Inter-arm coordination |
| **Monitoring** | diagnostic_updater | System diagnostics |
| **Logging** | ROS2 logging + syslog | Event logging |

---

## 3. Hardware Specifications

### 3.1 Compute Hardware

#### Raspberry Pi 4B (4GB RAM) - Per Arm Node & Vehicle

**Specifications:**
- **SoC:** Broadcom BCM2711 (ARM Cortex-A72)
- **CPU:** Quad-core 1.8 GHz (can be overclocked)
- **RAM:** 4GB LPDDR4-3200
- **Storage:** 64GB+ microSD card (⚠️ VERIFY capacity per node)
- **USB:** 2× USB 3.0, 2× USB 2.0
- **Network:** Gigabit Ethernet + WiFi 802.11ac
- **GPIO:** 40-pin header
- **Power:** 5V 3A via USB-C (official requirement)

**Operating Temperature:**
- Rated: -20°C to 70°C
- Recommended: 0°C to 50°C with passive cooling
- Thermal throttling: Begins at 80°C

**Cooling:**
- Heatsink required for continuous operation
- Passive cooling via aluminum heatsink (recommended)
- ⚠️ NEEDS SPECIFICATION: Verify actual cooling solution used

**System Configuration:**
- **7× Raspberry Pi 4B total:**
  - 6× for arm nodes (one per arm)
  - 1× for vehicle controller

#### Vehicle Controller (Raspberry Pi 4B)

**Role:** Central coordination and vehicle control
- **MQTT Broker:** Runs Mosquitto for arm coordination
- **Vehicle Navigation:** Autonomous row navigation
- **Arm Coordination:** arm_client node for multi-arm coordination
- **Operator Interface:** Button-based start/stop control
- **Data Logging:** Aggregates telemetry from all arms
- **Network Hub:** Central networking point

### 3.2 Vision System

#### OAK-D Lite Camera (1 per arm)

**Vendor:** Luxonis
**Model:** OAK-D Lite
**Status:** ✅ VALIDATED (Nov 1, 2025)

**Specifications:**
- **RGB Camera:**
  - Sensor: 4MP (⚠️ VERIFY exact sensor model)
  - Resolution: 1920×1080 @ 30 FPS
  - FOV: 73° DFOV (⚠️ VERIFY)
  - Autofocus: Fixed focus (⚠️ VERIFY)

- **Stereo Cameras:**
  - Sensor: 2× Global Shutter mono cameras
  - Resolution: 640×400 (⚠️ VERIFY)
  - Baseline: ~75mm (⚠️ VERIFY)
  - Depth range: 0.3m - 5m (configurable)

- **AI Processor:**
  - Intel Myriad X VPU
  - 4 TOPS (Tera Operations Per Second)
  - On-device neural network inference

- **Interface:**
  - USB 3.0 (USB 2.0 fallback mode supported)
  - Bandwidth: ~50 MB/s (USB 2.0), ~150 MB/s (USB 3.0)

- **Power:**
  - USB bus-powered
  - Typical: 2.5W (⚠️ VERIFY)

- **Operating Conditions:**
  - Temperature: 0°C to 50°C (⚠️ VERIFY)
  - Validated: 65.2°C peak during continuous operation

**Depth Performance:**
- Accuracy: ±2% of distance (manufacturer spec)
- Measured: ±10mm @ 0.6m ✅
- Confidence threshold: Configurable (default 255/255)

**Mounting:**
- ⚠️ NEEDS SPECIFICATION: Camera mounting bracket design
- ⚠️ NEEDS SPECIFICATION: Viewing angle relative to arm

### 3.3 Actuation System

#### MG6010E-i6 V3 Integrated Servo Motor (Arm Joints + Vehicle Steering)

**Vendor:** Shanghai LingKong Technology Co., Ltd (LK-TECH)
**Model:** MG6010E-i6 V3 (Version 3 with dual encoder)
**Quantity:** 21 total (18 arm joints + 3 vehicle steering)
**Status:** ✅ CAN Protocol Validated @ 500 kbps (Dec 2025)

**Electrical Specifications:**
- **Voltage:** 24V DC nominal (12-60V operating range per driver)
- **Driver:** DG80R/C7
  - Normal Current: 10A
  - Peak Current: 20A (for 10 seconds duration)
  - Input Voltage: 12-60V DC
- **Power:** ~24W rated (calculated from 1 N.m @ rated conditions)

**Mechanical Specifications:**
- **Rated Torque:** 1 N.m
- **Max Torque:** 2.5 N.m (burst)
- **Maximum Speed:** 320 rpm @ 24V (33.5 rad/s)
- **Gear Ratio:** 1:6 (integrated, fixed)
- **Encoder:** Dual encoder system (motor + reducer)
  - Type: 18-bit absolute position
  - Resolution: 262,144 positions per revolution
  - Accuracy: < 1mm effective at end effector ✅

**Communication:**
- **Protocol:** LK-TECH CAN V2.35
- **Interface:** CAN 2.0B
- **Bitrate:** **500 kbps (default, validated Dec 2025)** ✅
- **Supported Rates:** 125, 250, 500 kbps, 1 Mbps
- **CAN ID:** Configurable per motor (e.g., 0x141, 0x142, 0x143)
- **Response Time:** < 5ms ✅

**Control Loops:**
- **Torque Loop:** 32 KHz PWM frequency
- **Speed Loop:** 8 KHz
- **Position Loop:** 8 KHz
- **Bandwidth:** 0.4-2.8 KHz (motor/torque dependent)

**Control Modes:**
- Position mode (primary for picking operations)
- Velocity mode (supported)
- Torque mode (supported)

**Safety Features:**
- Over-temperature protection (built-in sensor)
- Over-voltage protection (12-60V operating range)
- Over-current protection (20A peak limit)
- Encoder fault detection (dual encoder system)
- Short circuit protection

**Temperature Monitoring:**
- **Built-in:** Motor temperature sensor with real-time monitoring
- **Warning Threshold:** 65°C (software configured)
- **Critical Threshold:** 70°C (software configured)
- **Hardware Protection:** Automatic shutdown on critical over-temp
- **Operating Range:** ⚠️ VERIFY (-20°C to 60°C estimated)

#### MG6012E-i36 V3 Integrated Servo Motor (Vehicle Drive)

**Vendor:** Shanghai LingKong Technology Co., Ltd (LK-TECH)
**Model:** MG6012E-i36 V3 (Version 3 with dual encoder)
**Quantity:** 3 total (one per wheel for 3-wheel vehicle)
**Status:** ✅ CAN Protocol Validated @ 500 kbps (Dec 2025)

**Electrical Specifications:**
- **Voltage:** 24V DC nominal (12-60V operating range per driver)
- **Driver:** DG80R/C7 (same as MG6010E-i6 V3)
  - Normal Current: 10A
  - Peak Current: 20A (for 10 seconds duration)
  - Input Voltage: 12-60V DC
- **Power:** ~216W rated (calculated from 9 N.m @ rated conditions)

**Mechanical Specifications:**
- **Rated Torque:** 9 N.m (9× higher than MG6010E-i6 V3)
- **Max Torque:** 18 N.m (burst)
- **Gear Ratio:** 1:36 (integrated, fixed) - Higher reduction for vehicle propulsion
- **Encoder:** Dual encoder system (motor + reducer)
  - Type: 18-bit absolute position
  - Resolution: 262,144 positions per revolution
  - V3 feature: Reducer end encoder with power-off memory

**Communication:**
- **Protocol:** LK-TECH CAN V2.35
- **Interface:** CAN 2.0B
- **Bitrate:** **500 kbps (default, validated Dec 2025)** ✅
- **Supported Rates:** 125, 250, 500 kbps, 1 Mbps
- **CAN ID:** Configurable per motor
- **Response Time:** < 5ms ✅

**Control Loops:**
- **Torque Loop:** 32 KHz PWM frequency
- **Speed Loop:** 8 KHz
- **Position Loop:** 8 KHz
- **Bandwidth:** 0.4-2.8 KHz (motor/torque dependent)

**Control Modes:**
- Velocity mode (primary for vehicle drive)
- Position mode (supported for precise positioning)
- Torque mode (supported for traction control)

**Safety Features:**
- Over-temperature protection (built-in sensor)
- Over-voltage protection (12-60V operating range)
- Over-current protection (20A peak limit)
- Encoder fault detection (dual encoder system)
- Short circuit protection

**Temperature Monitoring:**
- **Built-in:** Motor temperature sensor with real-time monitoring
- **Warning Threshold:** 65°C (software configured)
- **Critical Threshold:** 70°C (software configured)
- **Hardware Protection:** Automatic shutdown on critical over-temp
- **Operating Range:** ⚠️ VERIFY (-20°C to 60°C estimated)

**Application:** Higher torque for vehicle propulsion on agricultural terrain.

### 3.4 End Effector

#### Vacuum-Based Cotton Gripper

**Type:** Vacuum suction cup
**Status:** 🚧 IMPLEMENTED (NEEDS DETAILED SPEC)

**Components:**
- **Suction Cup:** ⚠️ NEEDS SPECIFICATION (diameter, material)
- **Vacuum Pump:** ⚠️ NEEDS SPECIFICATION (model, power)
- **Pressure Sensor:** ⚠️ VERIFY if implemented
- **Tubing:** ⚠️ NEEDS SPECIFICATION (diameter, length)
- **Valve:** ⚠️ NEEDS SPECIFICATION (solenoid type)

**Control:**
- Interface: GPIO (Raspberry Pi)
- Pin: GPIO 18 (⚠️ VERIFY)
- Activation: Software-controlled via ROS2 service
- Response time: < 200ms (target)

**Performance:**
- Grasp success rate: > 90% (target)
- Hold force: ⚠️ NEEDS SPECIFICATION
- Operating pressure: ⚠️ NEEDS SPECIFICATION (kPa)

### 3.5 Vehicle Platform

**Status:** ⚠️ NEEDS COMPREHENSIVE SPECIFICATION

**Configuration:**
- **3-wheel drive system** with independent steering per wheel
- **Motors:**
  - Drive: 3× MG6012E-i36 V3 (9 N.m rated, 18 N.m max, 1:36 gear ratio)
  - Steering: 3× MG6010E-i6 V3 (1 N.m rated, 2.5 N.m max, 1:6 gear ratio)
- **Total: 6 motors for vehicle locomotion**
- Payload capacity: ⚠️ NEEDS SPECIFICATION (must support 6 arms + cotton basket)
- Ground clearance: ⚠️ NEEDS SPECIFICATION
- Wheelbase: ⚠️ NEEDS SPECIFICATION
- Track width: ⚠️ NEEDS SPECIFICATION
- Maximum speed: ⚠️ NEEDS SPECIFICATION (optimized for continuous picking)
- Battery system: ⚠️ NEEDS SPECIFICATION

### 3.6 Power System

**Status:** ⚠️ NEEDS COMPREHENSIVE SPECIFICATION

**System Voltage Levels:**
- 24V DC: Motor power (24 motors total: 18 arm + 3 steering + 3 drive)
- 5V DC: Raspberry Pi 4B (USB-C, 3A per unit, 7 units total = 21A)
- 12V DC: ⚠️ VERIFY if needed for other components (cameras, sensors)

**Battery:**
- Type: ⚠️ NEEDS SPECIFICATION (LiFePO4? Li-ion?)
- Capacity: ⚠️ NEEDS SPECIFICATION (Ah)
- Voltage: ⚠️ NEEDS SPECIFICATION
- Runtime: Target 8 hours (⚠️ NEEDS VALIDATION)
- Charging: ⚠️ NEEDS SPECIFICATION

**Power Distribution:**
- Main power switch
- Per-arm circuit protection
- Emergency stop power cutoff (⚠️ VERIFY hardwired)

### 3.7 Electrical Interfaces

#### CAN Bus Interface

**Per Arm Node:**
- Interface: SocketCAN via USB-to-CAN adapter (⚠️ VERIFY model) or HAT
- **Bitrate: 500 kbps (default, validated Dec 2025)** ✅
- Supported rates: 125, 250, 500 kbps, 1 Mbps
- Termination: 120Ω resistors at bus ends
- Cabling: Twisted pair, shielded
- Maximum length: ~100m @ 500 kbps (typical for CAN)

**CAN Topology:**
- Each Raspberry Pi has independent CAN bus
- Each bus connects to 3 motors (one arm)
- No cross-arm CAN communication (uses MQTT instead)

#### GPIO Assignments (Per Arm)

Source of truth: `src/yanthra_move/include/yanthra_move/gpio_control_functions.hpp`

| BCM Pin | Function | Direction | Notes |
|---------|----------|-----------|-------|
| GPIO 2 | Shutdown Switch | Input | Active-low with pull-up |
| GPIO 3 | Start Switch | Input | Active-low with pull-up |
| GPIO 4 | Green LED | Output | System ready indicator |
| GPIO 12 | End Effector Drop ON (M2 Enable) / Cotton Drop Servo | Output | Motor 2 enable |
| GPIO 13 | End Effector Direction | Output | Motor direction control |
| GPIO 14 | Transport Servo | Output | Servo PWM |
| GPIO 15 | Red LED | Output | Error/status indicator |
| GPIO 17 | Camera LED | Output | Illumination control |
| GPIO 18 | Compressor | Output | Pneumatic compressor relay |
| GPIO 20 | End Effector Drop Direction (M2 Direction) | Output | Motor 2 direction |
| GPIO 21 | End Effector ON (M1 Enable) | Output | Motor 1 enable |
| GPIO 24 | Vacuum Motor ON | Output | Vacuum control relay |

> **Note:** Earlier revisions of this document listed limit switch pins (GPIO 5, 16, 20, 26)
> and a status LED on GPIO 25. Those assignments came from an archived prototype config
> and are not present in the current firmware. Hardware E-stop pin remains unassigned
> (see GAP-ELEC-002 in `GAP_TRACKING.md`).

---

## 4. Software Architecture

### 4.1 ROS2 Package Structure

```
pragati_ros2/
├── src/
│   ├── common_utils/              # Shared utility libraries
│   │   ├── include/               # Header files
│   │   └── src/                   # Implementation
│   │
│   ├── cotton_detection_ros2/     # Computer vision package
│   │   ├── include/               # Headers
│   │   ├── src/                   # C++ nodes
│   │   ├── launch/                # Launch files
│   │   ├── config/                # YAML parameters
│   │   ├── msg/                   # Custom messages
│   │   ├── srv/                   # Custom services
│   │   └── test/                  # Unit tests
│   │
│   ├── motor_control_ros2/        # Motor control package
│   │   ├── include/               # Headers
│   │   ├── src/                   # Motor controllers
│   │   ├── config/                # Motor configurations
│   │   ├── launch/                # Launch files
│   │   └── test/                  # Tests
│   │
│   ├── yanthra_move/              # Arm manipulation package
│   │   ├── include/               # Headers
│   │   ├── src/                   # Motion planning nodes
│   │   ├── config/                # Arm parameters
│   │   ├── launch/                # Launch files
│   │   └── test/                  # Tests
│   │
│   ├── vehicle_control/           # Vehicle navigation
│   │   ├── include/               # Headers
│   │   ├── src/                   # Navigation nodes
│   │   ├── config/                # Vehicle parameters
│   │   └── launch/                # Launch files
│   │
│   ├── robot_description/         # Robot models
│   │   ├── urdf/                  # URDF files
│   │   ├── meshes/                # 3D models
│   │   ├── config/                # RViz configs
│   │   └── launch/                # Visualization
│   │
│   └── pattern_finder/            # ArUco detection
│       ├── src/                   # Detection nodes
│       └── config/                # Parameters
│
├── launch/                        # Top-level launches
├── config/                        # System-wide configs
├── scripts/                       # Utility scripts
│   ├── testing/                   # Test scripts
│   ├── utils/                     # Helper scripts
│   └── validation/                # Validation suite
│
├── docs/                          # Documentation
├── test_results/                  # Test outputs
├── build/                         # Build artifacts
├── install/                       # Install space
└── log/                           # ROS logs
```

### 4.2 Node Architecture

#### Per-Arm Node Graph

```
┌─────────────────────────────────────────────────────────┐
│  Arm Node (e.g., Arm 1)                                 │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │  cotton_detection_node (C++)                   │    │
│  │  - Interfaces with OAK-D Lite                  │    │
│  │  - Publishes: /cotton_detection/results        │    │
│  │  - Services: /cotton_detection/detect          │    │
│  └────────┬───────────────────────────────────────┘    │
│           │ DetectionResult                             │
│           ▼                                              │
│  ┌────────────────────────────────────────────────┐    │
│  │  yanthra_move_node (C++)                       │    │
│  │  - Motion planning & execution                 │    │
│  │  - Subscribes: /cotton_detection/results       │    │
│  │  - Publishes: /joint_commands                  │    │
│  │  - Services: /yanthra_move/pick_cotton         │    │
│  └────────┬───────────────────────────────────────┘    │
│           │ JointCommands                               │
│           ▼                                              │
│  ┌────────────────────────────────────────────────┐    │
│  │  motor_controller (C++)                        │    │
│  │  - Interfaces with CAN bus                     │    │
│  │  - Subscribes: /joint_commands                 │    │
│  │  - Publishes: /joint_states                    │    │
│  └────────┬───────────────────────────────────────┘    │
│           │ CAN frames                                  │
│           ▼                                              │
│       [CAN Bus → Motors]                                │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │  safety_monitor (C++)                          │    │
│  │  - 100 Hz monitoring                           │    │
│  │  - Publishes: /diagnostics                     │    │
│  │  - Can trigger emergency stop                  │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │  mqtt_bridge (Python/C++)                      │    │
│  │  - Status publishing to broker                 │    │
│  │  - Subscribes to coordination messages         │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 4.3 State Machine Architecture

#### Arm Control State Machine (yanthra_move)

```
        ┌─────────┐
        │  INIT   │
        └────┬────┘
             │
             ▼
        ┌─────────┐
    ┌──▶│  IDLE   │◀──────────────┐
    │   └────┬────┘               │
    │        │ /start             │
    │        ▼                    │
    │   ┌─────────────┐           │
    │   │ DETECTING   │           │
    │   └────┬────────┘           │
    │        │ cotton found       │
    │        ▼                    │
    │   ┌─────────────┐           │
    │   │  PLANNING   │           │
    │   └────┬────────┘           │
    │        │ trajectory ready   │
    │        ▼                    │
    │   ┌─────────────┐           │
    │   │ APPROACHING │           │
    │   └────┬────────┘           │
    │        │ target reached     │
    │        ▼                    │
    │   ┌─────────────┐           │
    │   │  GRASPING   │           │
    │   └────┬────────┘           │
    │        │ vacuum activated   │
    │        ▼                    │
    │   ┌─────────────┐           │
    │   │ RETRACTING  │           │
    │   └────┬────────┘           │
    │        │ safe position      │
    │        ▼                    │
    │   ┌─────────────┐           │
    │   │ DEPOSITING  │           │
    │   └────┬────────┘           │
    │        │ cotton released    │
    │        └────────────────────┘
    │             │ more cotton
    └─────────────┘

    Any state → ERROR on fault
    ERROR → RECOVERY → IDLE
```

### 4.4 Threading Model

**cotton_detection_node:**
- Main thread: ROS2 event loop
- Camera callback thread: DepthAI pipeline callbacks
- Service handler threads: Detection triggers

**motor_control:**
- Main thread: ROS2 event loop
- CAN receive thread: Asynchronous CAN frame reception
- Safety monitor thread: 100Hz dedicated safety checking

**yanthra_move:**
- Main thread: ROS2 event loop
- Trajectory execution thread: Real-time trajectory following
- Coordination thread: MQTT message handling

---

## 5. Component Specifications

### 5.1 Cotton Detection Component

#### Algorithm Architecture

**Detection Pipeline:**

```
Camera Frame (1920×1080 RGB)
    │
    ├──▶ [HSV Detection Path]
    │    │
    │    ├─▶ Color space conversion (RGB → HSV)
    │    ├─▶ Threshold (white/light colors)
    │    ├─▶ Morphological operations (noise reduction)
    │    ├─▶ Contour detection
    │    ├─▶ Bounding box extraction
    │    └─▶ HSV Detections
    │
    ├──▶ [YOLO Detection Path]
    │    │
    │    ├─▶ Resize to 416×416
    │    ├─▶ YOLOv8n inference (on Myriad X VPU)
    │    ├─▶ Non-max suppression
    │    ├─▶ Confidence filtering (> 0.5)
    │    └─▶ YOLO Detections
    │
    └──▶ [Spatial Localization]
         │
         ├─▶ Stereo depth map (from depth cameras)
         ├─▶ Map 2D bounding box → 3D point
         ├─▶ Camera intrinsic calibration
         └─▶ 3D Coordinates (X, Y, Z)
              │
              ▼
         [Fusion & Classification]
              │
              ├─▶ Match HSV and YOLO detections
              ├─▶ Merge overlapping detections
              ├─▶ Classify PICKABLE / NOT_PICKABLE
              ├─▶ Assign confidence scores
              └─▶ Output: DetectionResult message
```

#### Detection Modes

| Mode | Description | Use Case | Performance |
|------|-------------|----------|-------------|
| `hsv_only` | HSV color-based only | High-contrast environments | Fast, lower accuracy |
| `yolo_only` | Neural network only | Low-light or complex scenes | Slower, higher accuracy |
| `hybrid_voting` | Both must agree | High precision required | Most conservative |
| `hybrid_merge` | Union of both | Maximum recall | May include false positives |
| `hybrid_fallback` | YOLO primary, HSV backup | Balanced (default) | ✅ Recommended |
| `depthai_direct` | Pure DepthAI pipeline | Lowest latency | Phase 2 |

#### HSV Detection Parameters

```yaml
# config/cotton_detection_cpp.yaml

cotton_detection:
  hsv_lower_bound: [0, 0, 180]      # [H, S, V] minimum
  hsv_upper_bound: [180, 40, 255]   # [H, S, V] maximum

  min_contour_area: 50.0             # pixels²
  max_contour_area: 5000.0           # pixels²

  morphology_kernel_size: 5          # Must be odd
  gaussian_blur_size: 3              # Must be odd

  nms_overlap_threshold: 0.3         # Non-max suppression
```

**Tuning Guide:**
- Increase `hsv_lower_bound[2]` (V) if picking up dark backgrounds
- Decrease `hsv_upper_bound[1]` (S) if picking up colored objects
- Adjust contour area for different cotton sizes

#### YOLO Detection Parameters

```yaml
yolo_enabled: true
yolo_model_path: "/opt/models/cotton_yolov8.onnx"
yolo_confidence_threshold: 0.5
yolo_nms_threshold: 0.4
yolo_input_width: 640
yolo_input_height: 640
```

**Model Information:**
- Architecture: YOLOv8n (nano - smallest/fastest)
- Input: 640×640 RGB (⚠️ VERIFY if different for DepthAI blob)
- Output: Bounding boxes + confidence + class
- Classes: ⚠️ NEEDS DOCUMENTATION (cotton, cotton_boll, etc.)
- Training: ⚠️ NEEDS DOCUMENTATION (dataset, augmentation)

#### DepthAI Pipeline Configuration

```yaml
depthai:
  enable: true
  model_path: "scripts/OakDTools/yolov8v2.blob"
  camera_width: 416
  camera_height: 416
  camera_fps: 30
  confidence_threshold: 0.5

  # Depth estimation
  enable_depth: true
  depth_min_mm: 100.0
  depth_max_mm: 5000.0

  # Device selection
  device_id: ""  # Empty = auto-select first device
```

**DepthAI Nodes:**
- `ColorCamera`: RGB image acquisition
- `MonoLeft/MonoRight`: Stereo pair
- `StereoDepth`: Depth map computation
- `NeuralNetwork`: YOLOv8 inference on VPU
- `SpatialLocationCalculator`: 3D coordinate extraction

#### Coordinate Transformation

**Camera Coordinate System (REP-103):**
```
camera_optical_frame:
  X: Right
  Y: Down
  Z: Forward (depth)
```

**Transformation to Robot Base:**
```
Detection in camera_optical_frame (x_c, y_c, z_c)
    │
    ▼
TF lookup: camera_optical_frame → base_link
    │
    ▼
Position in base_link (x_b, y_b, z_b)
    │
    ▼
Used for motion planning
```

**Configuration:**
```yaml
# Static transform (in launch file or URDF)
- parent: base_link
  child: camera_link
  x: 0.0  # ⚠️ NEEDS CALIBRATION
  y: 0.0
  z: 0.5  # ⚠️ NEEDS CALIBRATION
  roll: 0.0
  pitch: 0.0
  yaw: 0.0
```

#### Performance Characteristics

**Latency Breakdown:**
- Camera capture: ~33ms (30 FPS)
- YOLOv8 inference: ~30-40ms (Myriad X VPU)
- HSV processing: ~5-10ms (CPU)
- Fusion & post-processing: ~5ms
- Message publish: ~2ms
- **Total:** 70-80ms ✅

**Throughput:**
- Continuous mode: 15-30 FPS (configurable)
- On-demand mode: Single frame per service call

**Resource Usage:**
- CPU: ~25% of one Raspberry Pi 4B core (1.8 GHz ARM Cortex-A72)
- Memory: ~200MB (⚠️ VERIFY)
- USB bandwidth: ~50 MB/s (USB 2.0 mode)

### 5.2 Motor Control Component

#### MG6010 CAN Protocol

**Protocol:** LK-TECH CAN V2.35
**Status:** ✅ Implemented and validated (Oct 30, 2025)

**Message Structure:**

```
CAN Frame Format:
- CAN ID: 11-bit identifier
- DLC: 8 bytes
- Data: Command-specific payload
```

**Command Types:**

| Command | CAN ID | Function | Frequency |
|---------|--------|----------|-----------|
| `motor_on()` | 0x88 | Enable motor | Once at startup |
| `motor_off()` | 0x80 | Disable motor | Shutdown/emergency |
| `motor_stop()` | 0x81 | Stop motion | On demand |
| `set_origin()` | 0x95 | Set current position as zero | Calibration |
| `position_closed_loop_1()` | 0xA4 | Position command | 100-200 Hz |
| `read_encoder()` | 0x60 | Query position | 100-200 Hz |
| `read_status_1()` | 0x9A | Query temp, voltage, error | 10 Hz |
| `read_status_2()` | 0x9C | Query current, speed | 10 Hz |

**Position Control Command (0xA4):**
```
Byte 0-1: Position angle (int16, 0.01° per LSB)
Byte 2-3: Max speed (uint16, 1 dps per LSB)
Byte 4-5: Torque limit (uint16, implementation-specific)
Byte 6-7: Reserved
```

**Position Response:**
```
Byte 0-1: Current angle (int16, 0.01° per LSB)
Byte 2-3: Current speed (int16, 1 dps per LSB)
Byte 4-5: Current torque (int16, implementation-specific)
Byte 6-7: Reserved
```

**Status Response (0x9A):**
```
Byte 0: Temperature (int8, °C)
Byte 1: Reserved
Byte 2-3: Voltage (uint16, 0.01V per LSB)
Byte 4-5: Error code (uint16)
Byte 6-7: Reserved
```

#### Motor Controller Software Architecture

```cpp
// Simplified class structure

class MG6010MotorController : public MotorControllerInterface {
public:
    // Configuration
    void initialize(const MotorConfig& config);

    // Motion commands
    void setPosition(double angle_rad);
    void setVelocity(double velocity_rad_s);
    void setTorque(double torque_nm);

    // State queries
    MotorState getState();
    MotorDiagnostics getDiagnostics();

    // Safety
    void emergencyStop();
    void reset();

private:
    // CAN communication
    CANInterface can_interface_;
    void sendCANFrame(uint32_t id, const std::vector<uint8_t>& data);
    void receiveCANFrame();

    // State tracking
    MotorState current_state_;
    std::chrono::steady_clock::time_point last_response_;

    // Configuration
    MotorConfig config_;
};
```

**Configuration Structure:**
```yaml
# config/motors_production.yaml

motors:
  joint1_base:
    type: mg6010
    can_id: 0x141
    direction: 1           # 1 or -1
    position_offset: 0.0   # radians
    velocity_limit: 5.0    # rad/s
    torque_limit: 10.0     # Nm (⚠️ VERIFY)
    temperature_warning: 65.0   # °C
    temperature_critical: 70.0  # °C

  joint2_middle:
    type: mg6010
    can_id: 0x142
    # ... (similar structure)

  joint3_end:
    type: mg6010
    can_id: 0x143
    # ... (similar structure)
```

#### Control Loop Timing

```
Control Loop (100-200 Hz):
┌─────────────────────────────────────────┐
│                                         │
│  ┌──────────────────────────────────┐  │
│  │ 1. Read joint commands           │  │
│  │    (from /joint_commands topic)  │  │
│  └────────┬─────────────────────────┘  │
│           │ < 1ms                       │
│           ▼                             │
│  ┌──────────────────────────────────┐  │
│  │ 2. Send position commands        │  │
│  │    (CAN frames to motors)        │  │
│  └────────┬─────────────────────────┘  │
│           │ < 2ms                       │
│           ▼                             │
│  ┌──────────────────────────────────┐  │
│  │ 3. Read motor responses          │  │
│  │    (position, velocity, status)  │  │
│  └────────┬─────────────────────────┘  │
│           │ < 3ms                       │
│           ▼                             │
│  ┌──────────────────────────────────┐  │
│  │ 4. Update joint states           │  │
│  │    (publish /joint_states)       │  │
│  └────────┬─────────────────────────┘  │
│           │ < 1ms                       │
│           ▼                             │
│  ┌──────────────────────────────────┐  │
│  │ 5. Safety monitor checks         │  │
│  │    (limits, temperature, etc.)   │  │
│  └──────────────────────────────────┘  │
│                                         │
│  Total: ~7-10ms per cycle              │
│  Frequency: 100-150 Hz achievable      │
└─────────────────────────────────────────┘
```

### 5.3 Motion Planning Component (yanthra_move)

#### Inverse Kinematics

**Problem:** Convert target position (X, Y, Z) to joint angles (θ₁, θ₂, θ₃)

**Arm Configuration:**
- 3-DOF arm (Joint 1: base rotation, Joint 2: middle, Joint 3: end)
- Kinematic chain: Base → Link1 → Link2 → End Effector

**IK Solver Type:**
- ⚠️ NEEDS DOCUMENTATION: Analytical vs. Numerical?
- ⚠️ NEEDS DOCUMENTATION: Kinematic parameters (link lengths, offsets)

**Code Structure:**
```cpp
class InverseKinematics {
public:
    struct Solution {
        std::array<double, 3> joint_angles;  // radians
        bool valid;
        double error;  // position error (meters)
    };

    Solution solve(const Eigen::Vector3d& target_position);
    bool isReachable(const Eigen::Vector3d& position);

private:
    KinematicParameters params_;
};
```

**Workspace:**
- ⚠️ NEEDS SPECIFICATION: Reachable workspace envelope
- ⚠️ NEEDS SPECIFICATION: Singularity regions to avoid

#### Trajectory Planning

**Trajectory Types:**
1. **Point-to-Point:** Direct motion to target
2. **Cartesian Path:** Straight-line in task space
3. **Joint Space:** Smooth joint interpolation

**Trajectory Generation:**
```cpp
struct Trajectory {
    std::vector<TrajectoryPoint> points;
    double total_duration;
};

struct TrajectoryPoint {
    double time;  // seconds from start
    std::array<double, 3> positions;   // radians
    std::array<double, 3> velocities;  // rad/s
    std::array<double, 3> accelerations; // rad/s²
};

Trajectory generateTrajectory(
    const std::array<double, 3>& start,
    const std::array<double, 3>& goal,
    double max_velocity,
    double max_acceleration
);
```

**Trajectory Constraints:**
- Maximum velocity: 5.0 rad/s (configurable per joint)
- Maximum acceleration: ⚠️ NEEDS SPECIFICATION
- Maximum jerk: ⚠️ NEEDS SPECIFICATION

**Trajectory Execution:**
- Frequency: 100-200 Hz
- Interpolation: Cubic spline (⚠️ VERIFY)
- Real-time adjustment: ⚠️ NEEDS IMPLEMENTATION (Phase 2)

#### Pick Sequence Logic

```python
# Simplified pseudocode

def pick_cotton_sequence(detection_result):
    """Complete pick cycle for one cotton boll."""

    # 1. Planning phase
    target_position = detection_result.position

    # Check reachability
    if not is_reachable(target_position):
        return PickResult.UNREACHABLE

    # Compute IK solution
    joint_angles = inverse_kinematics(target_position)
    if not joint_angles.valid:
        return PickResult.IK_FAILED

    # Generate approach trajectory
    current_position = get_current_joint_positions()
    approach_traj = plan_trajectory(current_position, joint_angles)

    # 2. Execution phase
    # Move to approach position
    execute_trajectory(approach_traj)
    wait_for_completion()

    # 3. Grasping phase
    activate_vacuum()
    wait(0.2)  # seconds, allow vacuum to stabilize

    # Verify grasp (if pressure sensor available)
    if not verify_grasp():
        deactivate_vacuum()
        return PickResult.GRASP_FAILED

    # 4. Retract phase
    retract_traj = plan_retract_trajectory()
    execute_trajectory(retract_traj)
    wait_for_completion()

    # 5. Deposit phase
    deposit_traj = plan_trajectory(current, deposit_position)
    execute_trajectory(deposit_traj)
    wait_for_completion()

    # 6. Release
    deactivate_vacuum()
    wait(0.2)

    # 7. Return home
    home_traj = plan_trajectory(current, home_position)
    execute_trajectory(home_traj)

    return PickResult.SUCCESS
```

**Timing:**
- Planning: < 200ms
- Approach: 500-800ms
- Grasp: 200-500ms
- Retract: 500-600ms
- Deposit: 300-400ms
- Home: 300-400ms
- **Total:** 2.0-3.0 seconds (target)

---

## 6. Interface Specifications

### 6.1 ROS2 Topics

#### Published Topics

| Topic | Message Type | Publisher | Rate | QoS | Description |
|-------|-------------|-----------|------|-----|-------------|
| `/cotton_detection/results` | `cotton_detection_ros2/DetectionResult` | cotton_detection_node | Event | Reliable | Detection results with spatial coords |
| `/cotton_detection/debug_image/compressed` | `sensor_msgs/CompressedImage` | cotton_detection_node | 10 Hz | Best Effort | Annotated debug visualization |
| `/camera/camera_info` | `sensor_msgs/CameraInfo` | cotton_detection_node | 30 Hz | Reliable | Camera calibration parameters |
| `/joint_states` | `sensor_msgs/JointState` | motor_control | 100 Hz | Best Effort | Current joint positions/velocities |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | safety_monitor | 10 Hz | Reliable | System health diagnostics |
| `/joint_commands` | `std_msgs/Float64MultiArray` | yanthra_move | 100 Hz | Reliable | Commanded joint positions |

#### Subscribed Topics

| Topic | Message Type | Subscriber | Description |
|-------|-------------|-----------|-------------|
| `/cotton_detection/results` | `cotton_detection_ros2/DetectionResult` | yanthra_move | Receive detections for picking |
| `/joint_commands` | `std_msgs/Float64MultiArray` | motor_control | Receive position commands |
| `/start_switch/state` | `std_msgs/Bool` | yanthra_move | System start trigger |

### 6.2 ROS2 Services

#### Detection Services

**`/cotton_detection/detect`**
```
Service Type: cotton_detection_ros2/srv/CottonDetection

Request:
  int32 detect_command
    # 0 = stop detection
    # 1 = trigger detection
    # 2 = export calibration

Response:
  int32[] data         # ASCII-encoded path for calibration export
  bool success         # True if operation succeeded
  string message       # Human-readable status
```

**Usage:**
```bash
# Trigger detection
ros2 service call /cotton_detection/detect \
  cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Export calibration
ros2 service call /cotton_detection/detect \
  cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"
```

#### Manipulation Services

**`/yanthra_move/pick_cotton`**
```
Service Type: std_srvs/srv/Trigger (⚠️ VERIFY - may be custom)

Request:
  # Empty or contains detection ID

Response:
  bool success
  string message  # "Picked N cotton" or error description
```

**`/yanthra_move/get_motor_status`**
```
Service Type: ⚠️ NEEDS DOCUMENTATION

Request:
  # Joint IDs or empty for all

Response:
  # Motor status information
```

### 6.3 ROS2 Parameters

Parameters are organized hierarchically and declared in YAML files.

#### Cotton Detection Parameters

**File:** `config/cotton_detection_cpp.yaml`

```yaml
cotton_detection_node:
  ros__parameters:
    # General
    camera_topic: "/camera/image_raw"
    debug_image_topic: "/cotton_detection/debug_image/compressed"
    enable_debug_output: false
    simulation_mode: false
    use_depthai: true

    # Detection
    detection_confidence_threshold: 0.7
    max_cotton_detections: 50
    detection_mode: "hybrid_fallback"

    # HSV thresholds
    cotton_detection:
      hsv_lower_bound: [0, 0, 180]
      hsv_upper_bound: [180, 40, 255]
      min_contour_area: 50.0
      max_contour_area: 5000.0
      morphology_kernel_size: 5
      gaussian_blur_size: 3
      nms_overlap_threshold: 0.3

    # Coordinate transform
    coordinate_transform:
      pixel_to_meter_scale_x: 0.001
      pixel_to_meter_scale_y: 0.001
      assumed_depth_m: 0.5

    # YOLO
    yolo_enabled: true
    yolo_model_path: "/opt/models/cotton_yolov8.onnx"
    yolo_confidence_threshold: 0.5
    yolo_nms_threshold: 0.4
    yolo_input_width: 640
    yolo_input_height: 640

    # DepthAI
    depthai:
      enable: false  # Usually controlled by use_depthai launch param
      model_path: "scripts/OakDTools/yolov8v2.blob"
      camera_width: 416
      camera_height: 416
      camera_fps: 30
      confidence_threshold: 0.5
      enable_depth: true
      depth_min_mm: 100.0
      depth_max_mm: 5000.0

    # Performance
    performance:
      max_processing_fps: 30.0
      processing_timeout_ms: 1000
      enable_monitoring: true
      detailed_logging: false
```

#### Motor Control Parameters

**File:** `config/motors_production.yaml`

```yaml
motor_control:
  ros__parameters:
    # CAN interface
    can_interface: "can0"
    can_bitrate: 500000

    # Control loop
    control_frequency: 100.0  # Hz

    # Motors
    motors:
      joint1_base:
        type: "mg6010"
        can_id: 0x141
        direction: 1
        position_offset: 0.0
        velocity_limit: 5.0
        torque_limit: 10.0  # ⚠️ VERIFY
        temperature_warning: 65.0
        temperature_critical: 70.0
        position_min: -3.14  # radians
        position_max: 3.14

      joint2_middle:
        type: "mg6010"
        can_id: 0x142
        direction: 1
        position_offset: 0.0
        velocity_limit: 5.0
        torque_limit: 10.0
        temperature_warning: 65.0
        temperature_critical: 70.0
        position_min: -1.57
        position_max: 1.57

      joint3_end:
        type: "mg6010"
        can_id: 0x143
        direction: 1
        position_offset: 0.0
        velocity_limit: 5.0
        torque_limit: 10.0
        temperature_warning: 65.0
        temperature_critical: 70.0
        position_min: -1.57
        position_max: 1.57

    # Safety
    safety_monitor:
      enable: true
      check_frequency: 100.0  # Hz
      communication_timeout_ms: 500
      enable_gpio_estop: true
      estop_gpio_pin: 27  # ⚠️ VERIFY
```

### 6.4 Custom Message Definitions

#### DetectionResult.msg

```
# File: cotton_detection_ros2/msg/DetectionResult.msg

std_msgs/Header header          # Timestamp and frame_id
int32 total_count               # Number of detections
bool detection_successful       # False if pipeline failed
float32 processing_time_ms      # Latency measurement
CottonPosition[] positions      # Array of detected cotton
```

#### CottonPosition.msg

```
# File: cotton_detection_ros2/msg/CottonPosition.msg

std_msgs/Header header               # Timestamp and frame_id
geometry_msgs/Point position         # 3D position (X, Y, Z) in meters
float32 confidence                   # Detection confidence (0.0-1.0)
int32 detection_id                   # Unique identifier
```

### 6.5 TF Frame Conventions

**Frame Hierarchy:**
```
base_link (robot base)
  ├── camera_link (camera mount)
  │    └── camera_optical_frame (REP-103 optical frame)
  ├── joint1 (base rotation)
  │    └── link1
  │         └── joint2 (middle joint)
  │              └── link2
  │                   └── joint3 (end joint)
  │                        └── end_effector
  └── (other components)
```

**Key Frames:**
- `base_link`: Robot base, fixed to vehicle
- `camera_optical_frame`: Camera optical center (Z forward, X right, Y down)
- `end_effector`: Gripper/vacuum tool center point

**Static Transforms:**
Configured in launch files or URDF:
```xml
<!-- Example static transform -->
<node pkg="tf2_ros" exec="static_transform_publisher"
      args="0 0 0.5 0 0 0 base_link camera_link"/>
      <!-- x y z roll pitch yaw parent child -->
```

**⚠️ NEEDS CALIBRATION:** All transform values must be measured on physical robot.

---

## 7. Communication Protocols

### 7.1 CAN Bus Protocol

**Overview:**
- Standard: CAN 2.0B
- **Bitrate: 500 kbps (default, validated Dec 2025)** ✅
- Supported rates: 125, 250, 500 kbps, 1 Mbps
- Physical: Twisted pair, 120Ω termination at both ends
- Topology: Linear bus (per arm + vehicle)

**Frame Format:**
- Standard 11-bit identifier
- Data length: 0-8 bytes
- No extended frames used

**Error Handling:**
- CAN automatic retransmission enabled
- Application-level timeout: 500ms
- Error counters monitored

**SocketCAN Configuration:**
```bash
# Initialize CAN interface (done automatically by systemd)
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Verify status
ip -details link show can0

# Monitor CAN traffic (debugging)
candump can0

# Send test frame (debugging)
cansend can0 141#8800000000000000  # motor_on to ID 0x141
```

**Software Interface (C++):**
```cpp
#include <linux/can.h>
#include <linux/can/raw.h>

class CANInterface {
public:
    bool initialize(const std::string& interface_name);
    bool sendFrame(uint32_t can_id, const std::vector<uint8_t>& data);
    bool receiveFrame(can_frame& frame, int timeout_ms);
    void close();

private:
    int socket_fd_;
};
```

### 7.2 MQTT Protocol

**Purpose:** Inter-arm coordination and status reporting

**Broker:**
- Software: Eclipse Mosquitto
- Location: Central controller
- Default IP: 10.42.0.10 (⚠️ VERIFY)
- Port: 1883 (standard MQTT)

**Topic Structure:**
```
/pragati/
    ├── arm1/
    │   ├── status          (arm state, health)
    │   ├── cotton_count    (picks completed)
    │   └── error           (error messages)
    ├── arm2/
    │   └── ...
    ├── arm3/
    │   └── ...
    ├── arm4/
    │   └── ...
    └── vehicle/
        ├── command         (movement commands)
        ├── position        (odometry)
        └── status          (vehicle state)
```

**Message Format (JSON):**
```json
// /pragati/arm1/status
{
  "timestamp": 1234567890,
  "arm_id": 1,
  "state": "PICKING",
  "current_cotton": 5,
  "total_picked": 127,
  "battery_level": 85,
  "temperature": {
    "motor1": 45.2,
    "motor2": 48.1,
    "motor3": 43.8,
    "camera": 52.3
  },
  "errors": []
}
```

**QoS Levels:**
- Status messages: QoS 0 (at most once)
- Command messages: QoS 1 (at least once)
- Critical alerts: QoS 2 (exactly once) - ⚠️ VERIFY if used

**Client Libraries:**
- C++: Eclipse Paho MQTT C++ (⚠️ VERIFY)
- Python: paho-mqtt

**Configuration:**
```yaml
# MQTT client configuration
mqtt:
  broker_address: "10.42.0.10"
  broker_port: 1883
  client_id: "pragati_arm1"  # Unique per arm
  keepalive: 60
  qos: 0
  status_publish_rate: 1.0  # Hz
```

### 7.3 ROS2 DDS Configuration

**Middleware:** Cyclone DDS (recommended)

**Configuration File:** `cyclonedds.xml`
```xml
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain>
    <General>
      <NetworkInterfaceAddress>auto</NetworkInterfaceAddress>
      <AllowMulticast>true</AllowMulticast>
    </General>
    <Discovery>
      <ParticipantIndex>auto</ParticipantIndex>
    </Discovery>
  </Domain>
</CycloneDDS>
```

**Environment Setup:**
```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///path/to/cyclonedds.xml
```

**QoS Profiles:**

| Profile | Reliability | Durability | History | Use Case |
|---------|-------------|-----------|---------|----------|
| Sensor Data | Best Effort | Volatile | Keep Last (1) | Camera images, joint states |
| Commands | Reliable | Volatile | Keep Last (10) | Motor commands |
| Status | Reliable | Transient Local | Keep Last (10) | Diagnostics, system state |
| Parameters | Reliable | Transient Local | Keep All | Configuration data |

---

## 8. Data Structures & Algorithms

### 8.1 Detection Data Structure

```cpp
// Internal representation (C++)

struct Detection {
    // Identification
    int id;                          // Unique detection ID
    std::chrono::steady_clock::time_point timestamp;

    // 2D Information (pixels)
    cv::Rect bounding_box;           // (x, y, width, height)
    cv::Point2f center_2d;           // (x, y) pixel coordinates

    // 3D Information (meters)
    Eigen::Vector3d position_3d;     // (x, y, z) in camera frame
    float depth;                      // Distance from camera

    // Quality metrics
    float confidence;                 // 0.0 to 1.0
    float spatial_confidence;         // Depth map quality

    // Classification
    enum class DetectionSource {
        HSV_ONLY,
        YOLO_ONLY,
        FUSION
    } source;

    enum class Pickability {
        PICKABLE,
        NOT_PICKABLE,
        UNKNOWN
    } pickability;

    // Additional metadata
    std::string frame_id;             // TF frame
    bool has_depth;                   // Depth valid?
};
```

### 8.2 Detection Fusion Algorithm

```cpp
std::vector<Detection> fuseDetections(
    const std::vector<Detection>& hsv_detections,
    const std::vector<Detection>& yolo_detections,
    FusionMode mode)
{
    std::vector<Detection> fused;

    switch (mode) {
    case FusionMode::HYBRID_FALLBACK:
        // Primary: YOLO
        // Fallback: HSV if YOLO finds nothing
        if (!yolo_detections.empty()) {
            fused = yolo_detections;
        } else {
            fused = hsv_detections;
        }
        break;

    case FusionMode::HYBRID_VOTING:
        // Only keep detections agreed by both methods
        fused = findOverlappingDetections(hsv_detections, yolo_detections);
        break;

    case FusionMode::HYBRID_MERGE:
        // Union of both methods
        fused = mergeDetectionLists(hsv_detections, yolo_detections);
        break;

    // ... other modes
    }

    // Post-processing
    fused = removeDuplicates(fused);
    fused = classifyPickability(fused);
    fused = sortByConfidence(fused);

    return fused;
}
```

**Overlap Criteria:**
```cpp
bool detectionsOverlap(const Detection& d1, const Detection& d2) {
    // Compute IoU (Intersection over Union) of bounding boxes
    float iou = computeIoU(d1.bounding_box, d2.bounding_box);

    // Threshold for considering same detection
    const float IOU_THRESHOLD = 0.3;

    return iou > IOU_THRESHOLD;
}
```

### 8.3 Inverse Kinematics Algorithm

⚠️ **NEEDS DETAILED DOCUMENTATION**

**Current Implementation:**
- Package: `yanthra_move`
- Files: `src/yanthra_move/inverse_kinematics.cpp` (⚠️ VERIFY path)

**Skeleton:**
```cpp
struct IKSolution {
    std::array<double, 3> joint_angles;  // radians
    bool valid;
    double position_error;  // meters
};

IKSolution solveIK(const Eigen::Vector3d& target_position) {
    IKSolution solution;

    // ⚠️ NEEDS DOCUMENTATION: Algorithm details
    // - Analytical solution using trigonometry?
    // - Numerical optimization (Jacobian-based)?
    // - Library (KDL, TRAC-IK, etc.)?

    // Pseudocode:
    // 1. Check if target is within workspace
    // 2. Solve for joint angles
    // 3. Check joint limits
    // 4. Compute forward kinematics to verify
    // 5. Return solution

    return solution;
}
```

### 8.4 Trajectory Generation Algorithm

⚠️ **NEEDS DETAILED DOCUMENTATION**

**Likely Implementation:** Cubic polynomial interpolation

```cpp
Trajectory generateCubicTrajectory(
    const std::array<double, 3>& q_start,
    const std::array<double, 3>& q_goal,
    double duration)
{
    Trajectory traj;
    traj.total_duration = duration;

    // For each joint, compute cubic polynomial coefficients
    for (int i = 0; i < 3; i++) {
        // Boundary conditions:
        // q(0) = q_start[i], q(T) = q_goal[i]
        // v(0) = 0, v(T) = 0 (start and end at rest)

        double a0 = q_start[i];
        double a1 = 0.0;  // initial velocity = 0
        double a2 = 3.0 / (duration * duration) * (q_goal[i] - q_start[i]);
        double a3 = -2.0 / (duration * duration * duration) * (q_goal[i] - q_start[i]);

        // Sample trajectory at control frequency
        double dt = 1.0 / CONTROL_FREQUENCY;
        for (double t = 0; t <= duration; t += dt) {
            TrajectoryPoint point;
            point.time = t;
            point.positions[i] = a0 + a1*t + a2*t*t + a3*t*t*t;
            point.velocities[i] = a1 + 2*a2*t + 3*a3*t*t;
            point.accelerations[i] = 2*a2 + 6*a3*t;

            traj.points.push_back(point);
        }
    }

    return traj;
}
```

---

## 9. Safety & Monitoring Systems

### 9.1 Safety Monitor Architecture

**Implementation:** `motor_control_ros2/src/safety_monitor.cpp`

**Monitoring Frequency:** 100 Hz (10ms loop)

**Monitored Parameters:**

| Parameter | Source | Threshold | Action |
|-----------|--------|-----------|--------|
| Joint Position | Motor feedback | Configured limits | Stop + Alert |
| Joint Velocity | Motor feedback | 5.0 rad/s default | Stop + Alert |
| Motor Temperature | Motor status | 70°C warning, 80°C critical | Warning / Stop |
| Motor Voltage | Motor status | 36-52V range | Alert |
| CAN Timeout | Communication | 500ms | Stop + Alert |
| GPIO E-Stop | Direct read | LOW = pressed | Immediate stop |

**Safety Monitor Loop:**
```cpp
class SafetyMonitor {
public:
    void run() {
        rclcpp::Rate rate(100);  // 100 Hz

        while (rclcpp::ok()) {
            // 1. Read current state
            auto joint_states = readJointStates();
            auto motor_statuses = readMotorStatuses();
            bool estop_pressed = readEStopGPIO();

            // 2. Check all safety conditions
            std::vector<SafetyViolation> violations;

            violations.push_back(checkPositionLimits(joint_states));
            violations.push_back(checkVelocityLimits(joint_states));
            violations.push_back(checkTemperatures(motor_statuses));
            violations.push_back(checkVoltages(motor_statuses));
            violations.push_back(checkCommunication());

            if (estop_pressed) {
                violations.push_back(SafetyViolation::ESTOP_PRESSED);
            }

            // 3. Handle violations
            if (!violations.empty()) {
                handleSafetyViolations(violations);
            }

            // 4. Publish diagnostics
            publishDiagnostics(violations);

            rate.sleep();
        }
    }

private:
    void handleSafetyViolations(const std::vector<SafetyViolation>& violations) {
        // Immediate actions
        stopAllMotors();

        // Log all violations
        for (const auto& v : violations) {
            RCLCPP_ERROR(get_logger(), "Safety violation: %s", v.description.c_str());
        }

        // Publish diagnostic error
        auto diag_msg = createDiagnosticMessage(violations);
        diag_msg.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
        diagnostics_pub_->publish(diag_msg);

        // Flash error LED
        setErrorLED(true);

        // Enter safe state
        state_ = State::SAFETY_STOP;
    }

    void stopAllMotors() {
        // Send stop command to all motors via CAN
        for (const auto& motor : motors_) {
            motor->emergencyStop();
        }
    }
};
```

**Recovery Procedure:**
```cpp
bool SafetyMonitor::attemptRecovery() {
    // 1. Wait for conditions to clear
    if (violationsStillPresent()) {
        return false;
    }

    // 2. Verify E-stop released
    if (readEStopGPIO()) {
        return false;
    }

    // 3. Re-initialize motors
    for (auto& motor : motors_) {
        if (!motor->initialize()) {
            return false;
        }
    }

    // 4. Clear error state
    state_ = State::IDLE;
    setErrorLED(false);

    RCLCPP_INFO(get_logger(), "Safety recovery successful");
    return true;
}
```

**Manual Reset Service:**
```cpp
// Service: /safety_monitor/reset
void resetCallback(
    const std_srvs::srv::Trigger::Request::SharedPtr request,
    std_srvs::srv::Trigger::Response::SharedPtr response)
{
    if (attemptRecovery()) {
        response->success = true;
        response->message = "Safety system reset successful";
    } else {
        response->success = false;
        response->message = "Cannot reset: violations still present or E-stop active";
    }
}
```

### 9.2 Diagnostics Framework

**ROS2 Package:** `diagnostic_updater`

**Diagnostic Tasks:**

```cpp
void setupDiagnostics() {
    diagnostic_updater_ = std::make_shared<diagnostic_updater::Updater>(this);

    // System-level status
    diagnostic_updater_->add("System Status", this, &Node::diagnosticSystem);

    // Per-component status
    diagnostic_updater_->add("Motor Controller", this, &Node::diagnosticMotors);
    diagnostic_updater_->add("Camera Status", this, &Node::diagnosticCamera);
    diagnostic_updater_->add("CAN Bus Status", this, &Node::diagnosticCAN);

    // Performance metrics
    diagnostic_updater_->add("Performance Metrics", this, &Node::diagnosticPerformance);

    // Set update frequency
    diagnostic_updater_->setHardwareID("Pragati Arm 1");
    diagnostic_updater_->force_update();  // Initial update
}

void diagnosticMotors(diagnostic_updater::DiagnosticStatusWrapper& stat) {
    // Check all motors
    bool all_ok = true;
    for (const auto& motor : motors_) {
        if (motor->hasError()) {
            all_ok = false;
            stat.add(motor->getName() + " Status", "ERROR");
            stat.add(motor->getName() + " Error", motor->getErrorString());
        } else {
            stat.add(motor->getName() + " Temperature", motor->getTemperature());
            stat.add(motor->getName() + " Voltage", motor->getVoltage());
        }
    }

    if (all_ok) {
        stat.summary(diagnostic_msgs::msg::DiagnosticStatus::OK, "All motors operational");
    } else {
        stat.summary(diagnostic_msgs::msg::DiagnosticStatus::ERROR, "Motor errors detected");
    }
}
```

**Diagnostic Levels:**
- **OK:** Normal operation
- **WARN:** Non-critical issue (e.g., temperature approaching limit)
- **ERROR:** Critical issue (e.g., motor fault, communication timeout)
- **STALE:** No recent updates

**Viewing Diagnostics:**
```bash
# Command line
ros2 topic echo /diagnostics

# RQT GUI
ros2 run rqt_robot_monitor rqt_robot_monitor
```

### 9.3 Emergency Stop Implementation

**Hardware E-Stop:**
- Physical button connected to GPIO
- ⚠️ VERIFY: Also hardwired to motor power relay?

**GPIO Monitoring:**
```cpp
class EmergencyStopMonitor {
public:
    void initialize(int gpio_pin) {
        gpio_pin_ = gpio_pin;

        // Setup GPIO (using libgpiod or similar)
        // ⚠️ NEEDS IMPLEMENTATION DETAILS

        // Start monitoring thread
        monitoring_thread_ = std::thread(&EmergencyStopMonitor::monitorLoop, this);
    }

private:
    void monitorLoop() {
        while (running_) {
            bool estop_pressed = readGPIO(gpio_pin_);

            if (estop_pressed && !estop_pressed_) {
                // Rising edge - E-stop just pressed
                triggerEmergencyStop();
            }

            estop_pressed_ = estop_pressed;

            std::this_thread::sleep_for(std::chrono::milliseconds(10));  // 100 Hz
        }
    }

    void triggerEmergencyStop() {
        RCLCPP_ERROR(rclcpp::get_logger("estop"), "EMERGENCY STOP ACTIVATED");

        // Notify safety monitor
        safety_monitor_->handleEmergencyStop();

        // Publish alert
        publishEmergencyStopAlert();
    }

    int gpio_pin_;
    bool estop_pressed_ = false;
    bool running_ = true;
    std::thread monitoring_thread_;
};
```

---

## 10. Configuration Management

### 10.1 YAML Configuration Files

**Location:** `<package>/config/*.yaml`

**Loading in Launch Files:**
```python
from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    # Find config file
    config_file = os.path.join(
        get_package_share_directory('cotton_detection_ros2'),
        'config',
        'cotton_detection_cpp.yaml'
    )

    return LaunchDescription([
        Node(
            package='cotton_detection_ros2',
            executable='cotton_detection_node',
            name='cotton_detection_node',
            parameters=[config_file],
            output='screen'
        )
    ])
```

**Runtime Parameter Access:**
```bash
# List all parameters
ros2 param list /cotton_detection_node

# Get specific parameter
ros2 param get /cotton_detection_node detection_confidence_threshold

# Set parameter
ros2 param set /cotton_detection_node detection_confidence_threshold 0.8
```

**Parameter Validation:**
```cpp
// Declare parameter with validation
this->declare_parameter<double>(
    "detection_confidence_threshold",
    0.7,  // default value
    rcl_interfaces::msg::ParameterDescriptor()
        .set__description("Detection confidence threshold")
        .set__additional_constraints("Must be between 0.0 and 1.0")
        .set__read_only(false)
);

// Add parameter callback for validation
auto param_callback = [this](const std::vector<rclcpp::Parameter>& parameters) {
    for (const auto& param : parameters) {
        if (param.get_name() == "detection_confidence_threshold") {
            double value = param.as_double();
            if (value < 0.0 || value > 1.0) {
                RCLCPP_ERROR(get_logger(), "Invalid threshold: must be 0.0-1.0");
                return rcl_interfaces::msg::SetParametersResult()
                    .set__successful(false)
                    .set__reason("Value out of range");
            }
        }
    }
    return rcl_interfaces::msg::SetParametersResult().set__successful(true);
};

this->add_on_set_parameters_callback(param_callback);
```

### 10.2 Build Configuration

**Build System:** colcon + CMake

**Build Types:**
```bash
# Fast build (no tests, optimization)
./build.sh fast

# Full build (all features, tests)
./build.sh full

# Single package
./build.sh pkg cotton_detection_ros2

# Debug build
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug
```

**CMake Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `CMAKE_BUILD_TYPE` | `RelWithDebInfo` | Release, Debug, RelWithDebInfo |
| `HAS_DEPTHAI` | `ON` | Enable DepthAI camera support |
| `ENABLE_GPIO` | `ON` | Enable GPIO interface |
| `BUILD_TEST_NODES` | `OFF` | Build test executables |
| `BUILD_TESTING` | `ON` | Build unit tests |

**Example:**
```bash
colcon build --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DHAS_DEPTHAI=ON \
    -DENABLE_GPIO=OFF \
    -DBUILD_TESTING=OFF
```

**Build Optimization:**
- **ccache:** Compiler cache (30-50% faster rebuilds)
- **Ninja:** Fast build system (vs Make)
- **Parallel jobs:** `-j$(nproc)` flag

**Build Time:**
- Development machine: ~3-5 minutes (full build)
- Optimized: ~2 minutes 55 seconds ✅
- Raspberry Pi 4B: ~10-15 minutes (⚠️ VERIFY, may be longer than RPi 5)

### 10.3 Environment Setup

**Workspace Setup:**
```bash
cd /home/ubuntu/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Optional: Add to ~/.bashrc
echo "source /home/ubuntu/pragati_ros2/install/setup.bash" >> ~/.bashrc
```

**Environment Variables:**
```bash
# ROS2 domain ID (isolate from other robots)
export ROS_DOMAIN_ID=42

# DDS middleware
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///path/to/cyclonedds.xml

# Logging
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}]: {message}"
export RCUTILS_COLORIZED_OUTPUT=1

# Hardware detection
export HAS_DEPTHAI=1  # Enable OAK-D camera
export ENABLE_GPIO=1  # Enable GPIO interface
```

---

## 11. Build & Deployment

### 11.1 Development Workflow

**1. Setup Development Environment:**
```bash
# Install ROS2 Jazzy
# Install dependencies
sudo apt install python3-colcon-common-extensions
sudo apt install python3-rosdep

# Clone repository
cd ~
git clone <repository-url> pragati_ros2
cd pragati_ros2

# Install dependencies
rosdep install --from-paths src --ignore-src -r -y

# Or use provided script
./install_deps.sh
```

**2. Build Workspace:**
```bash
# Fast build (development)
./build.sh fast

# Or manual
colcon build --symlink-install \
    --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

**3. Run Tests:**
```bash
# Unit tests
colcon test --packages-select cotton_detection_ros2

# Integration tests
./scripts/validation/comprehensive_test_suite.sh

# View test results
colcon test-result --verbose
```

**4. Launch System:**
```bash
source install/setup.bash

# Simulation mode (no hardware)
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true

# Hardware mode
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false
```

### 11.2 Raspberry Pi Deployment

**Target Platform:**
- Hardware: Raspberry Pi 4B (4GB RAM)
- OS: Ubuntu 24.04 Server (ARM64)
- ROS2: Jazzy

**Installation Steps:**

```bash
# 1. Flash Ubuntu 24.04 to SD card
#    (Use Raspberry Pi Imager or similar)

# 2. Boot and initial setup
sudo apt update && sudo apt upgrade -y
sudo apt install git vim htop

# 3. Install ROS2 Jazzy
# Follow official ROS2 installation guide for Ubuntu 24.04

# 4. Clone workspace
cd ~
git clone <repository-url> pragati_ros2
cd pragati_ros2

# 5. Install dependencies
./install_deps.sh

# 6. Build (use -j2 to avoid OOM)
colcon build --parallel-workers 2 \
    --cmake-args -DCMAKE_BUILD_TYPE=Release -DHAS_DEPTHAI=ON

# 7. Setup CAN interface
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# 8. Test system
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py
```

**Build Time on RPi 4B:**
- With `-j2`: ~4 minutes 33 seconds ✅
- With `-j4`: May trigger OOM on 4GB RAM (⚠️ NOT RECOMMENDED)

**Systemd Service (Auto-start):**
```ini
# /etc/systemd/system/pragati-arm.service

[Unit]
Description=Pragati Arm Control Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/pragati_ros2
ExecStart=/bin/bash -c 'source /opt/ros/jazzy/setup.bash && source install/setup.bash && ros2 launch yanthra_move pragati_complete.launch.py'
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

```bash
# Enable service
sudo systemctl daemon-reload
sudo systemctl enable pragati-arm.service
sudo systemctl start pragati-arm.service

# Check status
sudo systemctl status pragati-arm.service

# View logs
journalctl -u pragati-arm.service -f
```

### 11.3 Cross-Compilation

⚠️ **STATUS:** Documented in `docs/CROSS_COMPILATION_GUIDE.md` but NOT TESTED

**Purpose:** Build for Raspberry Pi on faster development machine

**Advantages:**
- Faster build times (minutes vs 10+ minutes)
- Development without tying up RPi
- CI/CD integration

**Status:** Guide exists but needs validation

---

## 12. Testing & Validation

### 12.1 Unit Testing

**Framework:** Google Test (gtest) via `ament_cmake_gtest`

**Test Coverage:**

| Package | Tests | Pass Rate | Coverage |
|---------|-------|-----------|----------|
| motor_control_ros2 | 70 | 100% | 29% |
| cotton_detection_ros2 | 86 | 100% | ⚠️ TBD |
| yanthra_move | 17 | 100% | ⚠️ TBD |
| common_utils | ⚠️ TBD | - | - |
| **TOTAL** | 218 | 100% | - |

**Running Tests:**
```bash
# Build tests
colcon build --cmake-args -DBUILD_TESTING=ON

# Run all tests
colcon test

# Run specific package tests
colcon test --packages-select cotton_detection_ros2

# View results
colcon test-result --verbose

# View detailed output
cat log/latest_test/cotton_detection_ros2/stdout_stderr.log
```

**Writing Tests:**
```cpp
// test/test_detection.cpp

#include <gtest/gtest.h>
#include "cotton_detection_ros2/detector.hpp"

TEST(DetectionTest, BasicDetection) {
    CottonDetector detector;

    // Setup test image
    cv::Mat test_image = cv::imread("test_data/cotton_sample.jpg");
    ASSERT_FALSE(test_image.empty());

    // Run detection
    auto results = detector.detect(test_image);

    // Assertions
    EXPECT_GT(results.size(), 0) << "Should detect at least one cotton";
    EXPECT_LT(results[0].confidence, 1.0);
    EXPECT_GT(results[0].confidence, 0.0);
}

TEST(DetectionTest, EmptyImage) {
    CottonDetector detector;

    cv::Mat empty_image;
    auto results = detector.detect(empty_image);

    EXPECT_EQ(results.size(), 0) << "Empty image should return no detections";
}
```

### 12.2 Integration Testing

**Test Suite:** `scripts/validation/comprehensive_test_suite.sh`

**Test Categories:**
1. **ROS2 System Tests:**
   - Node launching
   - Topic communication
   - Service calls
   - Parameter loading

2. **Hardware Interface Tests:**
   - CAN bus communication (mock in sim)
   - GPIO interface (mock in sim)
   - Camera detection (mock in sim)

3. **Component Integration:**
   - Detection → Planning → Control flow
   - Multi-node coordination
   - Error handling and recovery

**Running Integration Tests:**
```bash
# Full suite (simulation mode)
./scripts/validation/comprehensive_test_suite.sh

# View report
firefox ~/pragati_test_results/comprehensive_test_*/test_report.html
```

**Latest Results (⚠️ Oct 14, 2025):**
- ✅ 18 tests passed
- ⚠️ 2 warnings (expected with mock hardware)
- ❌ 0 tests failed
- ⏱️ Duration: ~45 seconds

### 12.3 Hardware Validation

**Checklist:** `docs/HARDWARE_TEST_CHECKLIST.md`

**Required Hardware Tests:**

1. **Motor Calibration & Tuning**
   - CAN communication validation
   - Position control accuracy
   - Velocity control validation
   - PID tuning (⚠️ NEEDS EXECUTION)

2. **Camera Validation**
   - Spatial accuracy measurement
   - Detection with real cotton (⚠️ NEEDS EXECUTION)
   - Lighting condition testing
   - Thermal stability validation (✅ 65.2°C peak)

3. **End Effector Testing**
   - Vacuum pressure verification
   - Grasp success rate measurement
   - Different cotton conditions

4. **Full System Integration**
   - Complete pick cycles
   - Multi-arm coordination
   - Field environment testing
   - Long-duration reliability (24+ hours)

**Status:** Most hardware tests pending field access

### 12.4 Performance Benchmarking

**Benchmark Scripts:**
- `scripts/testing/performance_benchmark.py`
- `scripts/testing/latency_measurement.py`

**Measured Metrics:**

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Detection latency | < 100ms | 70ms | ✅ |
| Service latency | < 200ms | 134ms avg | ✅ |
| Spatial accuracy @ 0.6m | ±20mm | ±10mm | ✅ |
| Motor response | < 50ms | < 5ms | ✅ |
| Pick cycle time | < 3.0s | ⚠️ TBD | Pending |
| System uptime | > 95% | ⚠️ TBD | Pending |

---

## 13. Performance Optimization

### 13.1 Build Optimization

**Implemented Optimizations:**

1. **Compiler Cache (ccache):**
   ```bash
   # Auto-detected and used if available
   # Provides 50-80% faster rebuilds
   which ccache && echo "ccache available"
   ```

2. **Ninja Build System:**
   ```bash
   # Faster than GNU Make
   # Better incremental builds
   colcon build --cmake-args -G Ninja
   ```

3. **Parallel Compilation:**
   ```bash
   # Use all CPU cores
   colcon build --parallel-workers $(nproc)

   # Or for limited memory (RPi)
   colcon build --parallel-workers 2
   ```

4. **Selective Building:**
   ```bash
   # Build only changed packages
   colcon build --packages-up-to yanthra_move

   # Skip tests during development
   colcon build --cmake-args -DBUILD_TESTING=OFF
   ```

**Results:**
- Development machine: 2min 55s ✅ (30-40% improvement)
- Raspberry Pi 4B: 4min 33s ✅ (with -j2, OOM fixed)

### 13.2 Runtime Optimization

**Detection Performance:**

1. **YOLOv8n (Nano) Model:**
   - Smallest YOLO variant
   - Trades accuracy for speed
   - Inference: ~30-40ms on Myriad X VPU

2. **DepthAI Pipeline:**
   - On-device neural network execution
   - Reduces USB bandwidth
   - Offloads CPU processing

3. **Image Resolution:**
   - RGB: 1920×1080 (capture)
   - NN Input: 416×416 (resize on device)
   - Depth: 640×400 (⚠️ VERIFY)

4. **Detection Mode:**
   - `hybrid_fallback` recommended (balanced)
   - `depthai_direct` for lowest latency (Phase 2)

**Motor Control Performance:**

1. **CAN Bitrate:**
   - **500 kbps is default (validated Dec 2025)**
   - Provides excellent bandwidth for 24 motors across 7 CAN buses
   - Lower rates (e.g., 125 kbps) are possible but not recommended

2. **Control Frequency:**
   - Current: 100-200 Hz
   - Target: Maintain 100 Hz minimum
   - 500 kbps provides headroom for increased frequency if needed

3. **Message Optimization:**
   - Batch status queries when possible
   - Don't poll faster than necessary

### 13.3 Memory Optimization

**Detection Node:**
- Avoid memory leaks in camera callbacks
- Limit detection history buffer size
- Use efficient image storage (shared_ptr)

**Motor Control:**
- Pre-allocate CAN frame buffers
- Limit trajectory point count
- Clear old diagnostic data

**Raspberry Pi Considerations:**
- 8GB RAM recommended (4GB may work with tuning)
- Swap file for emergency (not for runtime)
- Monitor with `htop` or `free -h`

**OOM Fixes Implemented:**
- Build with `-j2` instead of `-j4` ✅
- Reduced parallel workers during build ✅

---

## 14. Troubleshooting & Diagnostics

### 14.1 Common Issues

#### Issue: Camera Not Detected

**Symptoms:**
- "DepthAI device not found" error
- Detection node fails to start

**Diagnosis:**
```bash
# Check USB devices
lsusb | grep 03e7  # Luxonis vendor ID

# Check DepthAI devices
python3 -c "import depthai as dai; print(dai.Device.getAllAvailableDevices())"
```

**Solutions:**
1. Check USB connection
2. Try different USB port (prefer USB 3.0)
3. Check USB power supply (may need powered hub)
4. Verify user permissions (`sudo usermod -a -G plugdev $USER`)
5. Try USB 2.0 fallback mode

#### Issue: CAN Bus Communication Failure

**Symptoms:**
- Motor commands not working
- "CAN send failed" errors
- Communication timeout warnings

**Diagnosis:**
```bash
# Check CAN interface status
ip -details link show can0

# Monitor CAN traffic
candump can0

# Send test frame
cansend can0 141#8800000000000000
```

**Solutions:**
1. Verify bitrate: `sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on`
2. Check termination resistors (120Ω at both ends)
3. Verify wiring (CAN_H and CAN_L not swapped)
4. Check motor power supply (24V)
5. Try lower bitrate if communication unstable

#### Issue: High CPU Usage

**Symptoms:**
- System sluggish
- Frame rate drops
- Detection latency increases

**Diagnosis:**
```bash
# Monitor CPU usage
htop

# Check per-node CPU usage
ros2 run ros2_profiling profile
```

**Solutions:**
1. Reduce camera frame rate
2. Disable debug image publishing
3. Optimize detection mode (use `yolo_only`)
4. Check for infinite loops or busy-waiting
5. Verify DDS middleware configuration

#### Issue: Safety Monitor False Triggers

**Symptoms:**
- Unexpected emergency stops
- "Joint limit exceeded" but position looks valid

**Diagnosis:**
```bash
# Check joint states
ros2 topic echo /joint_states

# Check diagnostics
ros2 topic echo /diagnostics
```

**Solutions:**
1. Verify joint limit configuration in YAML
2. Check for sensor noise in position feedback
3. Adjust safety thresholds
4. Verify coordinate transforms (units in radians?)

### 14.2 Diagnostic Tools

**ROS2 Tools:**
```bash
# List nodes
ros2 node list

# Node info
ros2 node info /cotton_detection_node

# Topic info
ros2 topic info /cotton_detection/results
ros2 topic hz /cotton_detection/results  # Measure rate
ros2 topic bw /cotton_detection/results  # Bandwidth

# Service test
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Parameter check
ros2 param list /motor_control
ros2 param get /motor_control control_frequency
```

**System Monitoring:**
```bash
# CPU and memory
htop

# Temperature (Raspberry Pi)
vcgencmd measure_temp

# Disk usage
df -h

# Network traffic
iftop

# CAN bus
candump can0 | grep 141  # Filter by CAN ID
```

**Log Analysis:**
```bash
# ROS logs
cd ~/pragati_ros2/log/latest
grep ERROR *

# System logs
journalctl -u pragati-arm.service -n 100

# Kernel messages (CAN errors)
dmesg | grep can
```

### 14.3 Recovery Procedures

#### Soft Reset (Node Restart)

```bash
# Kill specific node
ros2 node list
pkill -f cotton_detection_node

# Restart node
ros2 run cotton_detection_ros2 cotton_detection_node
```

#### Full System Restart

```bash
# Stop all ROS processes
pkill -9 ros

# Restart via systemd (if configured)
sudo systemctl restart pragati-arm.service

# Or manual restart
cd ~/pragati_ros2
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py
```

#### Hardware Reset

```bash
# Reset CAN interface
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Power cycle motors (if relay control available)
# ⚠️ NEEDS IMPLEMENTATION

# Camera reset (replug USB or reboot)
```

#### Emergency Recovery

1. **Press E-Stop Button:** Immediate hardware stop
2. **Call Safety Reset Service:**
   ```bash
   ros2 service call /safety_monitor/reset std_srvs/srv/Trigger
   ```
3. **If unresponsive:** Power cycle entire system

---

## 15. Appendices

### Appendix A: Acronyms & Abbreviations

| Acronym | Definition |
|---------|------------|
| **API** | Application Programming Interface |
| **CAN** | Controller Area Network |
| **CPU** | Central Processing Unit |
| **DDS** | Data Distribution Service |
| **DOF** | Degrees of Freedom |
| **DPS** | Degrees Per Second |
| **FPS** | Frames Per Second |
| **GPIO** | General Purpose Input/Output |
| **HSV** | Hue, Saturation, Value (color space) |
| **IK** | Inverse Kinematics |
| **IoU** | Intersection over Union |
| **LED** | Light Emitting Diode |
| **LSB** | Least Significant Bit |
| **MQTT** | Message Queuing Telemetry Transport |
| **NN** | Neural Network |
| **NMS** | Non-Maximum Suppression |
| **OOM** | Out of Memory |
| **PRD** | Product Requirements Document |
| **QoS** | Quality of Service |
| **RGB** | Red, Green, Blue (color space) |
| **ROS** | Robot Operating System |
| **RPi** | Raspberry Pi |
| **TF** | Transform (coordinate frame library) |
| **TSD** | Technical Specification Document |
| **URDF** | Unified Robot Description Format |
| **USB** | Universal Serial Bus |
| **VPU** | Vision Processing Unit |
| **YAML** | YAML Ain't Markup Language |
| **YOLO** | You Only Look Once (object detection) |

### Appendix B: File Structure Reference

```
pragati_ros2/
├── src/                       # ROS2 packages
│   ├── cotton_detection_ros2/
│   │   ├── include/cotton_detection_ros2/
│   │   │   ├── detector.hpp
│   │   │   ├── yolo_detector.hpp
│   │   │   └── hsv_detector.hpp
│   │   ├── src/
│   │   │   ├── cotton_detection_node.cpp
│   │   │   ├── detector.cpp
│   │   │   └── ...
│   │   ├── launch/
│   │   │   └── cotton_detection_cpp.launch.py
│   │   ├── config/
│   │   │   └── cotton_detection_cpp.yaml
│   │   ├── msg/
│   │   │   ├── DetectionResult.msg
│   │   │   └── CottonPosition.msg
│   │   ├── srv/
│   │   │   └── CottonDetection.srv
│   │   ├── test/
│   │   │   └── test_detection.cpp
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   │
│   ├── motor_control_ros2/
│   ├── yanthra_move/
│   ├── vehicle_control/
│   ├── robot_description/
│   ├── common_utils/
│   └── pattern_finder/
│
├── docs/                      # Documentation
│   ├── specifications/        # THIS DOCUMENT
│   ├── architecture/
│   ├── guides/
│   ├── requirements/
│   └── ...
│
├── scripts/                   # Utility scripts
│   ├── testing/
│   ├── validation/
│   └── utils/
│
├── launch/                    # System-level launches
├── config/                    # System configurations
├── build/                     # Build artifacts (gitignored)
├── install/                   # Install space (gitignored)
├── log/                       # ROS logs (gitignored)
│
├── CMakeLists.txt            # Workspace CMake (if used)
├── package.xml               # Workspace package (if used)
├── colcon.meta               # Colcon configuration
├── build.sh                  # Build helper script
├── install_deps.sh           # Dependency installer
└── README.md                 # Project README
```

### Appendix C: Reference Commands

**Essential ROS2 Commands:**
```bash
# Environment
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Build
colcon build [--packages-select <pkg>]
colcon test
colcon test-result --verbose

# Run
ros2 launch <package> <launch_file>
ros2 run <package> <executable>

# Introspection
ros2 node list
ros2 topic list
ros2 service list
ros2 param list

# Communication
ros2 topic echo <topic>
ros2 topic hz <topic>
ros2 service call <service> <type> <args>

# Debugging
ros2 doctor
ros2 wtf  # What's the failure?
```

**CAN Bus Commands:**
```bash
# Setup
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up
sudo ip link set can0 down

# Monitor
candump can0
candump can0 -x  # Extended format
cansniffer can0  # Interactive viewer

# Test
cansend can0 <id>#<data>
```

**System Commands:**
```bash
# Temperature
vcgencmd measure_temp  # Raspberry Pi

# Process management
ps aux | grep ros
pkill -f <node_name>

# Logs
journalctl -u pragati-arm.service -f
tail -f ~/pragati_ros2/log/latest/<node>/stdout_stderr.log

# Network
ping 10.42.0.10  # MQTT broker
mosquitto_sub -h 10.42.0.10 -t /pragati/#
```

### Appendix D: Hardware Pinout

**Raspberry Pi 4B GPIO (40-pin header) — Arm Role Annotations:**

Source of truth: `src/yanthra_move/include/yanthra_move/gpio_control_functions.hpp`

```
     3V3  (1) (2)  5V
   GPIO2  (3) (4)  5V            [Shutdown Switch - Input]
   GPIO3  (5) (6)  GND           [Start Switch - Input]
   GPIO4  (7) (8)  GPIO14        [Green LED - Output] / [Transport Servo - Output]
     GND  (9) (10) GPIO15        [Red LED - Output]
  GPIO17 (11) (12) GPIO18        [Camera LED - Output] / [Compressor - Output]
  GPIO27 (13) (14) GND
  GPIO22 (15) (16) GPIO23
     3V3 (17) (18) GPIO24        [Vacuum Motor ON - Output]
  GPIO10 (19) (20) GND           (SPI MOSI)
   GPIO9 (21) (22) GPIO25        (SPI MISO)
  GPIO11 (23) (24) GPIO8         (SPI SCLK) / (SPI CE0)
     GND (25) (26) GPIO7         (SPI CE1)
   GPIO0 (27) (28) GPIO1         (I2C ID EEPROM)
   GPIO5 (29) (30) GND
   GPIO6 (31) (32) GPIO12        [EE Drop ON / Cotton Drop Servo - Output]
  GPIO13 (33) (34) GND           [EE Direction - Output]
  GPIO19 (35) (36) GPIO16
  GPIO26 (37) (38) GPIO20        [EE Drop Direction (M2 Dir) - Output]
     GND (39) (40) GPIO21        [EE ON (M1 Enable) - Output]
```

> **Note:** Annotations show arm-role pin assignments. Vehicle-role uses a different
> pin map — see `docs/guides/GPIO_PIN_MAP.md` for the consolidated reference covering
> both roles. Pins without annotations are unassigned in the arm role.

### Appendix E: Maintenance Schedule

**Daily (Field Operation):**
- Visual inspection (damage, loose connections)
- Camera lens cleaning
- Check error logs
- Verify pick counts

**Weekly:**
- Check motor temperatures during operation
- Inspect CAN bus connectors
- Test emergency stop
- Backup configuration files

**Monthly:**
- Full system test (all functions)
- Software updates check
- Battery health check (⚠️ WHEN SPECIFIED)
- Calibration verification

**Quarterly:**
- Deep clean (camera, sensors)
- Motor lubrication (⚠️ IF REQUIRED)
- Replace consumables (filters, etc.)
- Documentation review

**Annually:**
- Complete system calibration
- Hardware inspection (mechanical wear)
- Update training materials
- Performance baseline measurement

---

### Appendix F: Document Changelog

**Version History:**

- **2025-12-16 (v1.0):** Initial consolidated technical specification from existing documentation
- **2025-12-16 (v1.1):** **MAJOR HARDWARE & PERFORMANCE UPDATES:**
  - **Hardware Platform:** Updated all "Raspberry Pi 5" → "Raspberry Pi 4B (4GB RAM)"
  - **Vehicle Configuration:** Updated "4-wheel" → "3-wheel" with independent steering
  - **Motor Specifications (COMPLETE):**
    - MG6010E-i6 V3: 1 N.m rated, 2.5 N.m max, 320 rpm @ 24V, 1:6 gear ratio
      - 21 total (18 arm joints + 3 vehicle steering)
      - Driver: DG80R/C7, 18-bit encoder, 32 KHz torque loop
    - MG6012E-i36 V3: 9 N.m rated, 18 N.m max, 1:36 gear ratio
      - 3 total (vehicle drive)
      - Same driver and encoder as MG6010E-i6 V3
  - **CAN Bus:** **500 kbps is the DEFAULT**
    - Validated for both arm and vehicle CAN buses (Dec 2025)
    - Updated throughout document: interface specs, protocol section, performance notes
  - **System Configuration:** 7× Raspberry Pi 4B total (6 arms + 1 vehicle)
  - **Vehicle Controller Role:** Runs MQTT broker, arm_client, navigation
  - **Power System:** Updated for 7× RPi 4B (21A @ 5V) + 24 motors (24V)
  - **Temperature Monitoring:** Added motor temp thresholds (65°C warning, 70°C critical)
  - **Performance Targets:** 2 sec/boll, 250kg/day, 1 acre/day
  - **Continuous Operation:** Production requirement (not optional)
  - **Build Times:** Updated for RPi 4B platform
- **[NEXT]:** Field trial results integration (January 2026)
- **[FUTURE]:** Battery specifications, vehicle dimensions, continuous operation algorithms

---

**END OF TECHNICAL SPECIFICATION DOCUMENT**

**Document Owner:** Pragati Robotics Engineering Team
**Next Review Date:** [TO BE SCHEDULED]
**Distribution:** Engineering Team, QA, Operations

---

*This document is a living technical reference. Engineers are encouraged to update it as the system evolves.*

⚠️ **IMPORTANT:** Many sections marked with ⚠️ need verification, measurement, or completion. These should be addressed during field validation and hardware testing phases.
