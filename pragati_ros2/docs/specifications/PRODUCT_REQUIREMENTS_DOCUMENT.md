# Pragati Cotton Picking Robot
## Product Requirements Document (PRD)

**Document Version:** 1.2 (Draft)  
**Date:** 2025-12-16  
**Status:** Draft - Continuous Operation Requirement Added  
**Last Updated:** 2025-12-16  
**Owner:** Pragati Robotics Team

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | System | Initial consolidated document from existing specs |
| 1.1 | 2025-12-16 | System + User | Updated hardware specs, timeline, performance targets |
| 1.2 | 2025-12-16 | System + User | **CRITICAL:** Continuous operation now REQUIRED (not optional); Field trial details added (2 arms on 1 row from each side); Motor specs extracted and added; **CAN 500kbps now DEFAULT** for both arm and vehicle |

**Review & Approval:**
- [ ] Technical Team Review
- [ ] Product Management Approval
- [ ] Operations Team Review
- [ ] Executive Approval

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Overview](#2-product-overview)
3. [Market & Use Cases](#3-market--use-cases)
4. [Functional Requirements](#4-functional-requirements)
5. [Performance Requirements](#5-performance-requirements)
6. [Operational Requirements](#6-operational-requirements)
7. [Safety & Compliance](#7-safety--compliance)
8. [Quality & Success Metrics](#8-quality--success-metrics)
9. [Development Phases](#9-development-phases)
10. [Constraints & Assumptions](#10-constraints--assumptions)
11. [Appendices](#11-appendices)

---

## 1. Executive Summary

### 1.1 Product Vision

The Pragati Cotton Picking Robot is an **autonomous agricultural robot system** designed to revolutionize cotton harvesting through advanced robotics, computer vision, and distributed computing. The system autonomously navigates cotton fields, detects ripe cotton bolls, and picks them using coordinated multi-arm manipulation.

### 1.2 Business Objectives

**Primary Goals:**
- Reduce labor dependency in cotton harvesting
- Increase harvesting efficiency and throughput
- Achieve **250 kg cotton per day, 1 acre coverage**
- Maintain >95% picking success rate with minimal damage
- Operate autonomously in field conditions
- Scale from expo demo (1 arm) → field trial (2 arms) → production (6 arms)

**Market Impact:**
- Address labor shortage in agriculture
- Target deployment: **November 2026 in customer fields**
- Improve harvest quality and timing
- Enable consistent, reliable picking regardless of labor availability

### 1.3 Key Differentiators

- **Scalable Multi-Arm Architecture:** 1-6 independent arms working in parallel
- **Fast Pick Cycles:** 2 seconds per cotton boll (target)
- **Real-Time Computer Vision:** OAK-D Lite cameras with on-device AI inference
- **Precision Manipulation:** ±10mm spatial accuracy at 0.6m (validated)
- **Production-Ready Software:** ROS2 Jazzy with comprehensive testing (218 unit tests)
- **Field-Hardened Design:** Validated thermal stability, reliability tested

### 1.4 Current Status

**Current Phase: Expo Demo (1 Arm) - Core Technology Validated ✅**
- Status: Core components validated November 2025
- Detection latency: 70ms (Raspberry Pi 4B + OAK-D Lite)
- Service latency: 134ms average
- Reliability: 100% (10/10 consecutive tests)
- Spatial accuracy: ±10mm @ 0.6m
- Configuration: 1 arm + 3-wheel vehicle

**Next: Field Trial (2 Arms) - Planning 🚧**
- Configuration: 2 arms + vehicle
- Target: Early 2026
- Validate multi-arm coordination
- Measure actual field performance

**Production Target (6 Arms) - November 2026 🎯**
- Configuration: 6 arms + vehicle
- Deployment: Customer fields
- Performance: 250 kg/day, 1 acre/day
- Pick cycle: 2 seconds per boll

---

## 2. Product Overview

### 2.1 Product Description

The Pragati robot is a **mobile field robot** with the following components:

**Hardware Platform:**
- **Mobile Base:** 3-wheel drive vehicle with independent drive and steering per wheel
- **Robotic Arms:** Scalable from 1 to 6 independent 3-DOF arms
  - Current (Expo): 1 arm
  - Field Trial: 2 arms
  - Production: 6 arms
- **Vision System:** 1 OAK-D Lite camera per arm (1-6 total)
- **Compute:** Raspberry Pi 4B (4GB RAM) per arm + vehicle controller (1 RPi 4B)
- **Arm Actuation:** MG6010E-i6 V3 integrated servo motors (3 per arm)
- **Vehicle Actuation:**
  - Drive: MG6012E-i36 V3 motors (3 total, one per wheel)
  - Steering: MG6010E-i6 V3 motors (3 total, one per wheel)
- **Communication:** CAN bus (500 kbps default), Ethernet, WiFi, MQTT

**Software Stack:**
- **Framework:** ROS2 Jazzy (Ubuntu 24.04)
- **Computer Vision:** YOLOv8n + HSV detection + DepthAI pipeline
- **Control:** ros2_control framework with custom motor controllers
- **Coordination:** MQTT-based multi-arm coordination
- **Build System:** colcon with ccache optimization (30-40% faster builds)

### 2.2 System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│         Vehicle Controller (Raspberry Pi 4B)                      │
│         - 3-Wheel Navigation (3× Drive + 3× Steering motors)     │
│         - MQTT Broker (Arm Coordination)                          │
│         - Button Control Interface                                │
│         - Start Switch Signal via arm_client                      │
└───────┬────────────┬────────────┬────────────┬───────────────────┘
        │            │            │            │
   MQTT │ Network    │            │            │
        │            │            │            │
   ┌────▼───┐   ┌───▼────┐   ┌──▼─────┐  ... ┌──▼─────┐
   │ ARM 1  │   │ ARM 2  │   │ ARM 3  │      │ ARM 6  │
   │ RPi 4B │   │ RPi 4B │   │ RPi 4B │      │ RPi 4B │
   │ 4GB    │   │ 4GB    │   │ 4GB    │      │ 4GB    │
   │        │   │        │   │        │      │        │
   │ +OAK-D │   │ +OAK-D │   │ +OAK-D │      │ +OAK-D │
   │ +3 Arm │   │ +3 Arm │   │ +3 Arm │      │ +3 Arm │
   │ Motors │   │ Motors │   │ Motors │      │ Motors │
   └────────┘   └────────┘   └────────┘      └────────┘

   Current: 1 arm (Expo)
   Field Trial: 2 arms
   Production: 6 arms
```

**Key Architecture Features:**
- **Distributed Processing:** Each arm has dedicated compute and sensors
- **Independent Operation:** Arms can operate autonomously or coordinated
- **Scalable Design:** Architecture supports 1-6 arms without redesign
- **MQTT Coordination:** Vehicle RPi 4B runs broker, sends start signals to arms
- **Fail-Safe:** Individual arm failure doesn't stop entire system

### 2.3 Core Capabilities

| Capability | Description | Status |
|------------|-------------|--------|
| **Autonomous Navigation** | 3-wheel vehicle navigation | 🚧 In Development |
| **Cotton Detection** | Real-time detection with spatial coordinates | ✅ Validated |
| **Precision Manipulation** | 3-DOF arm with ±10mm accuracy | ✅ Validated |
| **Fast Pick Cycles** | 2 seconds per boll target | 🎯 Target |
| **Multi-Arm Coordination** | Parallel operation of up to 6 arms | 🚧 2-arm field trial planned |
| **Button Control Interface** | Operator control from vehicle controller | ✅ Implemented |
| **MQTT Communication** | Arm-to-vehicle coordination | ✅ Implemented |
| **Safety Systems** | Emergency stop, limit checking, diagnostics | ✅ Implemented |

---

## 3. Market & Use Cases

### 3.1 Target Market

**Primary Market:**
- Commercial cotton farms (100+ acres)
- Geographic focus: Cotton belt regions (⚠️ NEEDS SPECIFICATION)
- Farm size: Medium to large operations

**Secondary Markets:**
- Research institutions
- Agricultural technology development
- Contract harvesting services

### 3.2 Use Cases

#### UC-1: Autonomous Field Harvesting (Phase 1)
**Description:** Robot stops at each plant, detects cotton, picks all reachable bolls, then moves to next plant.

**Actors:** Robot system, Field operator (supervision)

**Preconditions:**
- Field planted in rows with spacing compatible with robot
- Cotton bolls are ripe and ready for harvest
- Weather conditions within operational limits

**Flow:**
1. Operator positions robot at field start
2. Robot navigates to first plant and stops
3. All arms simultaneously scan for cotton
4. Arms pick detected cotton sequentially (per arm)
5. Robot moves to next plant
6. Repeat until row complete
7. Operator manually repositions for next row (⚠️ VERIFY)

**Success Criteria:**
- >85% pick success rate
- **<2 seconds per cotton boll**
- Minimal plant damage

#### UC-2: Continuous Picking Operation (REQUIRED for Production)
**Description:** Robot moves continuously while arms pick cotton on-the-fly.

**Status:** 🎯 REQUIRED FOR NOVEMBER 2026 DEPLOYMENT  
**Rationale:** Stop-and-go operation wastes ~40% time in idle motion. Continuous operation is MANDATORY to achieve 250kg/day production goal.

**Flow:**
1. Robot moves at constant speed through row (⚠️ NEEDS SPECIFICATION: TBD km/h)
2. All 6 cameras continuously detect cotton
3. System predicts cotton position compensating for vehicle motion
4. Arms pick cotton on-the-fly while vehicle moves
5. Multi-arm coordination prevents collisions
6. No stopping between picks

**Success Criteria:**
- >95% pick success rate during motion
- 250 kg/day throughput (vs. ~150 kg/day with stop-and-go)
- 2 seconds per boll maintained during motion
- Safe 6-arm parallel operation
- Vehicle speed optimized for pick success vs. throughput

#### UC-3: Operator Control via Button Interface
**Description:** Operator controls robot start/stop and monitors status via vehicle controller.

**Actors:** Field operator

**Capabilities:**
- Button-based start/stop control on vehicle RPi 4B
- MQTT-based start switch signal to arms via arm_client
- Basic status indication (LEDs, display)
- Emergency stop button
- System ready/error indication

**Status:** ✅ Implemented

**Note:** Web dashboard exists as POC only, not production-ready

#### UC-4: Manual Intervention & Recovery
**Description:** Operator handles edge cases and system recovery.

**Scenarios:**
- Emergency stop activation
- Obstacle in path
- System error recovery
- End of row repositioning
- Bin full notification

---

## 4. Functional Requirements

### 4.1 Cotton Detection (FR-DET)

#### FR-DET-001: Real-Time Detection
**Priority:** P0 (Critical)  
**Status:** ✅ VALIDATED (Nov 1, 2025)

The system SHALL detect cotton bolls in real-time using computer vision with the following requirements:

- **Detection Algorithm:** Hybrid HSV + YOLOv8n fusion
- **Detection Latency:** < 100ms per frame (Achieved: 70ms)
- **Frame Rate:** 15-30 FPS continuous operation
- **Detection Confidence:** Minimum 0.5 threshold (configurable)
- **Maximum Detections:** 50 cotton bolls per frame
- **Detection Range:** 0.3m to 2.0m from camera (⚠️ VERIFY range limits)

**Acceptance Criteria:**
- Detection latency measured < 100ms on target hardware
- False positive rate < 5%
- False negative rate < 10%
- Consistent performance over 1-hour continuous operation

#### FR-DET-002: Spatial Localization
**Priority:** P0 (Critical)  
**Status:** ✅ VALIDATED

The system SHALL provide 3D spatial coordinates for each detected cotton boll:

- **Coordinate System:** Camera optical frame (REP-103 compliant)
- **Spatial Accuracy:** ±10mm at 0.6m distance (Validated)
- **Accuracy Degradation:** ±20mm at 1.5m distance (⚠️ NEEDS VALIDATION)
- **Coordinate Output:** (X, Y, Z) in meters relative to camera
- **Coordinate Frame:** Transformable to robot base_link via TF2

**Acceptance Criteria:**
- Spatial accuracy verified with physical measurements
- TF transformations validated in simulation and hardware
- Position accuracy maintained across camera temperature range

#### FR-DET-003: Pickability Classification
**Priority:** P1 (High)  
**Status:** 🚧 PARTIALLY IMPLEMENTED

The system SHALL classify detected cotton as PICKABLE or NOT_PICKABLE based on:

- **Size Criteria:** Minimum/maximum bounding box dimensions
- **Occlusion Assessment:** Visibility and accessibility score
- **Reachability Check:** Within arm workspace (⚠️ NEEDS IMPLEMENTATION)
- **Quality Assessment:** Cotton boll maturity/quality indicators

**Acceptance Criteria:**
- Classification accuracy > 90%
- Reduces failed pick attempts by > 50%

#### FR-DET-004: Multi-Camera Fusion (Phase 2)
**Priority:** P2 (Medium)  
**Status:** 📝 PLANNED

The system SHALL fuse detections from multiple cameras:

- Eliminate duplicate detections across cameras
- Provide global cotton map in vehicle frame
- Update map in real-time during motion
- Support 4-6 camera inputs simultaneously

### 4.2 Robotic Manipulation (FR-ARM)

#### FR-ARM-001: 3-DOF Arm Control
**Priority:** P0 (Critical)  
**Status:** ✅ IMPLEMENTED

Each robotic arm SHALL have 3 degrees of freedom:

- **Joint 1 (Base):** Rotation/swivel motion
- **Joint 2 (Middle):** Elevation/reach motion  
- **Joint 3 (End Effector):** Extension/grasp motion

**Motion Specifications:**
- **Joint Limits:** Configured per joint in YAML (⚠️ NEEDS DOCUMENTATION)
- **Velocity Limits:** Configurable, safety-monitored
- **Position Resolution:** < 1mm effective at end effector
- **Control Frequency:** 100-200 Hz

**Acceptance Criteria:**
- All joints respond to position commands
- Joint limits enforced by safety monitor
- Smooth trajectory execution without oscillation

#### FR-ARM-002: Inverse Kinematics
**Priority:** P0 (Critical)  
**Status:** ✅ IMPLEMENTED

The system SHALL compute inverse kinematics to convert target (X,Y,Z) to joint angles:

- **IK Solver:** Analytical or numerical solver
- **Solution Time:** < 10ms per target
- **Reachability Check:** Validate target is within workspace
- **Multiple Solutions:** Select optimal configuration

**Acceptance Criteria:**
- IK solutions accurate within ±5mm
- Handles edge cases (singularities, unreachable points)
- Consistent solution selection

#### FR-ARM-003: Trajectory Planning
**Priority:** P0 (Critical)  
**Status:** ✅ IMPLEMENTED

The system SHALL plan collision-free trajectories:

- **Approach Phase:** Safe path to cotton location
- **Grasp Phase:** Final precise positioning
- **Retract Phase:** Safe withdrawal after pick
- **Home Phase:** Return to ready position

**Trajectory Specifications:**
- **Acceleration Limits:** Prevent excessive forces (⚠️ NEEDS SPECIFICATION)
- **Jerk Limits:** Smooth motion (⚠️ NEEDS SPECIFICATION)
- **Obstacle Avoidance:** Avoid self-collision and plant branches

**Acceptance Criteria:**
- Trajectories execute without violating joint limits
- Motion is smooth and predictable
- Pick cycle completes in < 3 seconds (Phase 1)

#### FR-ARM-004: End Effector Control
**Priority:** P0 (Critical)  
**Status:** ✅ IMPLEMENTED

The system SHALL control vacuum-based end effector:

- **Activation:** GPIO-controlled vacuum pump
- **Grasp Verification:** Pressure sensor feedback (⚠️ VERIFY if implemented)
- **Release Control:** Controlled vacuum release
- **Status Monitoring:** Detect grasp success/failure

**Acceptance Criteria:**
- Vacuum activates within 200ms
- Grasp success rate > 90%
- No damage to cotton during grasp

#### FR-ARM-005: Multi-Arm Coordination (Phase 2)
**Priority:** P1 (High)  
**Status:** 📝 PLANNED

The system SHALL coordinate multiple arms to avoid collisions:

- **Workspace Partitioning:** Assign zones to each arm
- **Motion Scheduling:** Sequence arm movements when zones overlap
- **Collision Detection:** Real-time monitoring during motion
- **Emergency Stopping:** Stop all arms if collision imminent

### 4.3 Vehicle Navigation (FR-NAV)

#### FR-NAV-001: Row Following (Phase 1)
**Priority:** P1 (High)  
**Status:** 📝 NEEDS VALIDATION

The system SHALL navigate along crop rows:

- **Navigation Mode:** Manual positioning between plants (Phase 1)
- **Movement:** Forward movement with stop-and-go operation
- **Positioning Accuracy:** ±10cm relative to row center (⚠️ NEEDS SPECIFICATION)

**Acceptance Criteria:**
- Robot stops at commanded positions
- Movement does not damage plants
- Positioning repeatable

#### FR-NAV-002: Autonomous Row Navigation (Phase 2)
**Priority:** P2 (Medium)  
**Status:** 📝 PLANNED

The system SHALL autonomously navigate field rows:

- **Speed:** Configurable, 0.1-1.0 m/s (⚠️ NEEDS SPECIFICATION)
- **Row Detection:** Vision-based or GPS-based
- **Obstacle Detection:** Stop/avoid obstacles in path
- **End-of-Row:** Detect and signal operator

#### FR-NAV-003: Odometry & Localization
**Priority:** P1 (High)  
**Status:** 🚧 PARTIALLY IMPLEMENTED

The system SHALL track its position in the field:

- **Odometry Source:** Wheel encoders + IMU (⚠️ VERIFY)
- **Localization:** Relative to field start position
- **Accuracy:** ±50cm over 100m travel (⚠️ NEEDS VALIDATION)
- **Frame:** Published as TF transform

### 4.4 Communication & Coordination (FR-COM)

#### FR-COM-001: ROS2 Communication
**Priority:** P0 (Critical)  
**Status:** ✅ IMPLEMENTED

Within each arm node, components SHALL communicate via ROS2:

- **Middleware:** Cyclone DDS
- **QoS:** Configured per topic (reliable/best-effort)
- **Discovery:** Automatic node discovery
- **Latency:** Topic publish latency < 10ms

#### FR-COM-002: MQTT Inter-Arm Communication
**Priority:** P1 (High)  
**Status:** 🚧 IMPLEMENTED (NEEDS VALIDATION)

Arms SHALL coordinate via MQTT broker:

- **Broker:** Eclipse Mosquitto on central controller
- **Topics:** `/pragati/arm{1-4}/status`, `/pragati/vehicle/command`
- **Message Rate:** 1 Hz status updates
- **Latency:** < 200ms message delivery

**Status Information:**
- Arm state (IDLE, DETECTING, PICKING, ERROR)
- Cotton count picked
- System health metrics
- Error conditions

#### FR-COM-003: Status Monitoring
**Priority:** P2 (Medium)  
**Status:** 🚧 BASIC IMPLEMENTATION

The system SHALL provide basic status monitoring:

- **Button Interface:** Start/stop control on vehicle controller RPi 4B
- **MQTT Status:** Arm status messages published to vehicle
- **LED Indicators:** System ready, error conditions
- **ROS Diagnostics:** `/diagnostics` topic for system health
- **Logs:** System logs accessible via SSH

**Note:** Web dashboard exists as POC only, not production-ready for field deployment

### 4.5 Data Management (FR-DATA)

#### FR-DATA-001: Data Logging
**Priority:** P1 (High)  
**Status:** ✅ IMPLEMENTED

The system SHALL log operational data:

- **Log Location:** `/pragati_ros2/log/` (project-contained)
- **Log Retention:** 7 days default, configurable
- **Log Cleanup:** Automatic age and size-based cleanup
- **Log Types:** ROS logs, detection results, pick statistics

#### FR-DATA-002: Pick Statistics
**Priority:** P2 (Medium)  
**Status:** 🚧 PARTIALLY IMPLEMENTED

The system SHALL track and report statistics:

- Total cotton detected per session
- Total cotton picked per arm
- Pick success rate per arm
- Average cycle time per pick
- System uptime and utilization

**Acceptance Criteria:**
- Statistics accessible via ROS service or topics
- Data exportable for analysis (CSV, JSON)
- Basic display via LED indicators or terminal output

---

## 5. Performance Requirements

### 5.1 Detection Performance (PERF-DET)

#### PERF-DET-001: Detection Latency ✅
**Requirement:** Detection SHALL complete within 100ms
**Measured:** 70ms average on Raspberry Pi 4 + OAK-D Lite
**Status:** EXCEEDS REQUIREMENT

#### PERF-DET-002: Service Latency ✅
**Requirement:** End-to-end service call SHALL complete within 200ms
**Measured:** 134ms average (123-218ms range)
**Status:** MEETS REQUIREMENT

#### PERF-DET-003: Detection Accuracy ✅
**Requirement:** Spatial accuracy ±20mm at 0.6m
**Measured:** ±10mm at 0.6m (validated Nov 1, 2025)
**Status:** EXCEEDS REQUIREMENT

#### PERF-DET-004: False Positive Rate
**Requirement:** < 5% false positive rate
**Measured:** ⚠️ NEEDS FIELD VALIDATION
**Status:** NOT VALIDATED

#### PERF-DET-005: False Negative Rate
**Requirement:** < 10% false negative rate
**Measured:** ⚠️ NEEDS FIELD VALIDATION
**Status:** NOT VALIDATED

### 5.2 Manipulation Performance (PERF-ARM)

#### PERF-ARM-001: Pick Cycle Time
**Requirement:** Complete pick cycle in **2.0 seconds per cotton boll** 🎯
**Measured:** ⚠️ NEEDS FIELD MEASUREMENT
**Status:** NOT VALIDATED (CRITICAL TARGET)

**Cycle Breakdown (Target):**
- Detection: < 100ms (validated: 70ms)
- Motion planning: < 150ms
- Arm approach: < 700ms
- End effector grasp: < 400ms
- Retract: < 350ms
- Home + drop: < 300ms
- **Total:** 2,000ms (2.0 seconds)

**Rationale:** 2 sec/boll × 6 arms parallel = ~4.5 hours for 250kg (50,000 bolls @ 5g each)

#### PERF-ARM-002: Pick Success Rate (Phase 1)
**Requirement:** > 85% pick success rate (minimum viable)
**Target:** > 95% pick success rate
**Measured:** ⚠️ NEEDS FIELD VALIDATION
**Status:** NOT VALIDATED

#### PERF-ARM-003: Position Repeatability
**Requirement:** Return to same position within ±2mm
**Measured:** ⚠️ NEEDS MEASUREMENT
**Status:** NOT VALIDATED

#### PERF-ARM-004: Motor Response Time
**Requirement:** Motor response to command < 50ms
**Measured:** < 5ms (validated Oct 30, 2025)
**Status:** EXCEEDS REQUIREMENT

### 5.3 System Performance (PERF-SYS)

#### PERF-SYS-001: Daily Throughput Target 🎯
**Requirement:** **250 kg cotton per day, 1 acre coverage**
**Measured:** ⚠️ NEEDS FIELD VALIDATION
**Status:** NOT VALIDATED (PRIMARY GOAL)

**Configuration:** 6 arms operating in parallel (production)

**Calculation:**
- Target: 250 kg/day
- Estimated: ~50,000 bolls @ 5g per boll
- At 2 sec/boll with 6 arms parallel: 50,000 ÷ 6 ÷ 1800 = 4.6 hours picking time
- Plus navigation overhead → **~8-10 hour workday achievable**

**Current Development:**
- Expo (1 arm): Technology validation
- Field Trial (2 arms): Multi-arm coordination, performance measurement
- Production (6 arms): November 2026 deployment target

#### PERF-SYS-002: Hourly Throughput (Production)
**Requirement:** Sustain 250kg / 8 hours = **31.25 kg/hour**
**Equivalent:** ~6,250 bolls/hour = **1,042 bolls/hour per arm** (@ 6 arms)
**Per Arm:** 1,042 bolls/hour ÷ 3600 = 1 boll every 3.5 seconds (includes navigation)
**Status:** 📝 TO BE MEASURED in field trial

#### PERF-SYS-003: System Reliability
**Requirement:** 100% uptime during 8-hour operation
**Measured:** ⚠️ NEEDS LONG-DURATION TEST
**Status:** NOT VALIDATED

**Acceptance Criteria:**
- No system crashes during operation
- Automatic recovery from transient errors
- Graceful degradation (continue with fewer arms if one fails)

#### PERF-SYS-004: Build Time (Development)
**Requirement:** Full build < 5 minutes on development machine
**Measured:** 2 min 55s with optimization (Nov 27, 2025)
**Status:** EXCEEDS REQUIREMENT

**Build Optimizations Applied:**
- ccache compiler cache
- Ninja build system
- Parallel compilation (-j flag)

#### PERF-SYS-005: Thermal Stability
**Requirement:** All components operate < 80°C
**Measured:** 
- OAK-D Lite: 65.2°C peak (validated Nov 1, 2025)
- Raspberry Pi: ⚠️ NEEDS CONTINUOUS MONITORING
- Motors: < 80°C limit specified by safety monitor
**Status:** PARTIALLY VALIDATED

### 5.4 Communication Performance (PERF-COM)

#### PERF-COM-001: ROS2 Topic Latency
**Requirement:** < 10ms topic publish latency
**Measured:** ⚠️ NEEDS SYSTEMATIC MEASUREMENT
**Status:** ASSUMED MET

#### PERF-COM-002: CAN Bus Communication
**Requirement:** CAN communication < 10ms round-trip
**Measured:** Stable at 500 kbps bitrate (tested and validated Dec 2025)
**Status:** VALIDATED (Oct 30, 2025)

#### PERF-COM-003: MQTT Message Delivery
**Requirement:** < 200ms message delivery time
**Measured:** ⚠️ NEEDS MEASUREMENT
**Status:** NOT VALIDATED

---

## 6. Operational Requirements

### 6.1 Environmental Conditions (OP-ENV)

#### OP-ENV-001: Operating Temperature
**Requirement:** System SHALL operate in 5°C to 45°C ambient
**Status:** ⚠️ NEEDS FIELD VALIDATION

**Component Limits:**
- Raspberry Pi 4B: -20°C to 70°C (rated, with proper cooling)
- OAK-D Lite: 0°C to 50°C (⚠️ VERIFY spec)
- MG6010E-i6 V3 Motors (arm + steering):
  - Operating: ⚠️ VERIFY (likely -20°C to 60°C)
  - Built-in temperature monitoring and protection
  - Warning threshold: 65°C (software configured)
  - Critical threshold: 70°C (software configured)
- MG6012E-i36 V3 Motors (drive): Same as MG6010E-i6 V3
- Battery/Power: ⚠️ NEEDS SPECIFICATION

#### OP-ENV-002: Weather Resistance
**Requirement:** System SHALL operate in light rain
**Status:** ⚠️ NEEDS SPECIFICATION AND VALIDATION

**Protection Level:**
- Electronics: IP54 minimum (⚠️ VERIFY enclosures)
- Cameras: Weather housing required
- Motors: Sealed/protected housings

#### OP-ENV-003: Lighting Conditions
**Requirement:** System SHALL operate in daylight conditions
**Status:** ⚠️ NEEDS VALIDATION

- Minimum illumination: 1000 lux (⚠️ NEEDS SPECIFICATION)
- Maximum illumination: Direct sunlight
- Night operation: Not required (Phase 1)

#### OP-ENV-004: Field Conditions
**Requirement:** System SHALL operate on typical cotton field terrain

- Soil types: Loam, clay, sandy (⚠️ NEEDS SPECIFICATION)
- Slope: < 5 degrees (⚠️ NEEDS SPECIFICATION)
- Ground clearance: ⚠️ NEEDS SPECIFICATION
- Obstacle handling: Avoid large obstacles > 10cm height

### 6.2 Power Management (OP-PWR)

#### OP-PWR-001: Power Source
**Requirement:** System SHALL operate on battery power
**Status:** ⚠️ NEEDS SPECIFICATION

- Battery type: ⚠️ NEEDS SPECIFICATION (LiFePO4, Li-ion?)
- Voltage: 24V DC system (motors), 5V (Raspberry Pi)
- Capacity: ⚠️ NEEDS SPECIFICATION (Ah rating)

#### OP-PWR-002: Operating Duration
**Requirement:** Minimum 4 hours continuous operation on single charge
**Status:** ⚠️ NEEDS VALIDATION

- Target: 8 hours for full work day
- Power consumption: ⚠️ NEEDS MEASUREMENT

#### OP-PWR-003: Battery Management
**Requirement:** System SHALL monitor battery status

- Low battery warning at 20%
- Critical shutdown at 10%
- Safe shutdown sequence
- Battery level indicated via LED or MQTT status message

### 6.3 Maintenance (OP-MAINT)

#### OP-MAINT-001: Scheduled Maintenance
**Requirement:** System SHALL require maintenance every ⚠️ [SPECIFY interval]

**Maintenance Tasks:**
- Camera lens cleaning
- Motor inspection and lubrication (if required)
- CAN bus connector inspection
- Software updates
- Calibration verification

#### OP-MAINT-002: Consumables Replacement
**Requirement:** End effector consumables SHALL be field-replaceable

- Vacuum filters (⚠️ SPECIFY replacement interval)
- Seals and gaskets
- Tubing connections

#### OP-MAINT-003: Diagnostics & Troubleshooting
**Requirement:** System SHALL provide diagnostic information

- Built-in diagnostic tests
- Error code display
- Log file access
- Troubleshooting guides available

### 6.4 Operator Interface (OP-UI)

#### OP-UI-001: Startup Procedure
**Requirement:** System startup SHALL be simple and guided

**Startup Sequence:**
1. Power on main controller
2. Power on arm controllers (Raspberry Pis)
3. CAN bus auto-initialization
4. Motor homing sequence
5. Camera initialization
6. System ready indication

**Estimated Time:** < 2 minutes (⚠️ NEEDS MEASUREMENT)

#### OP-UI-002: Emergency Stop
**Requirement:** Easily accessible emergency stop

- Physical E-stop button on vehicle controller
- Emergency stop via button interface
- Stops all motion immediately
- Maintains power to controllers
- Requires manual reset to resume

#### OP-UI-003: Status Indicators
**Requirement:** Clear system status indication

- LED indicators on vehicle and arm controllers
- Button interface status display
- MQTT status messages to vehicle controller
- Audio alerts for critical conditions (optional)
- Error indication via LED patterns

#### OP-UI-004: Training Requirements
**Requirement:** Operator trainable in < 1 day

**Training Topics:**
- Startup and shutdown procedures
- Normal operation monitoring
- Emergency procedures
- Basic troubleshooting
- Maintenance tasks

---

## 7. Safety & Compliance

### 7.1 Safety Systems (SAFE)

#### SAFE-001: Safety Monitor
**Requirement:** System SHALL implement 100Hz safety monitoring
**Status:** ✅ IMPLEMENTED

**Monitored Parameters:**
- Joint position limits (per joint configuration)
- Joint velocity limits (configurable)
- Motor temperature < 80°C (critical threshold)
- Motor voltage 36-52V range (⚠️ VERIFY specification)
- CAN communication timeout < 500ms
- GPIO E-stop state

**Response Actions:**
- Halt all motor commands immediately
- Publish diagnostic ERROR
- Flash error LED
- Log event with timestamp
- Require manual reset

#### SAFE-002: Collision Avoidance
**Requirement:** System SHALL prevent collisions

**Collision Types:**
- Self-collision (arm segments)
- Arm-to-arm collision (multiple arms)
- Arm-to-vehicle collision
- Arm-to-plant collision (minimize)

**Status:**
- Self-collision: Via joint limits ✅
- Arm-to-arm: 📝 NEEDS IMPLEMENTATION (Phase 2)
- Others: 🚧 PARTIAL

#### SAFE-003: Emergency Stop System
**Requirement:** Independent emergency stop circuit
**Status:** ✅ IMPLEMENTED

- Hardware E-stop button (GPIO-monitored)
- Hardwired to motor power relay (⚠️ VERIFY)
- Software monitoring at 100Hz (redundant)
- Latency: < 100ms from button press to motor stop

#### SAFE-004: Fail-Safe Behavior
**Requirement:** System SHALL fail to safe state

**Failure Modes:**
- Power loss: Motors hold position or brake (⚠️ VERIFY motor behavior)
- Communication loss: Stop motion, enter safe state
- Software crash: Watchdog triggers safe shutdown
- Sensor failure: Disable affected subsystem, alert operator

### 7.2 Compliance (COMP)

#### COMP-001: Electrical Safety
**Requirement:** System SHALL comply with electrical safety standards
**Status:** ⚠️ NEEDS CERTIFICATION

- Applicable standards: ⚠️ SPECIFY (IEC 60204-1, etc.)
- Insulation requirements
- Grounding requirements
- EMC compliance

#### COMP-002: Mechanical Safety
**Requirement:** System SHALL comply with machinery safety standards
**Status:** ⚠️ NEEDS CERTIFICATION

- Applicable standards: ⚠️ SPECIFY (ISO 12100, etc.)
- Pinch point protection
- Sharp edge protection
- Guarding requirements

#### COMP-003: Agricultural Equipment Standards
**Requirement:** Compliance with agricultural machinery standards
**Status:** ⚠️ NEEDS CERTIFICATION

- Applicable standards: ⚠️ SPECIFY (ASABE, ISO 4254, etc.)
- Regional regulations
- Type approval requirements

---

## 8. Quality & Success Metrics

### 8.1 System-Level KPIs

| Metric | Phase 1 Target | Phase 2 Target | Current Status |
|--------|---------------|----------------|----------------|
| **Pick Success Rate** | > 85% | > 95% | ⚠️ Not validated |
| **Picks per Hour** | 600-900 | 1,800-2,000 | ⚠️ Not measured |
| **Position Accuracy** | ±20mm @ 0.6m | ±10mm @ 0.6m | ✅ ±10mm validated |
| **Detection Latency** | < 100ms | < 100ms | ✅ 70ms validated |
| **System Uptime** | > 95% | > 99% | ⚠️ Not validated |
| **Average Cycle Time** | < 3.0 sec | < 1.5 sec | ⚠️ Not measured |

### 8.2 Component-Level Metrics

**Detection System:**
- False positive rate: < 5%
- False negative rate: < 10%
- Detection confidence: > 0.7 average
- Camera uptime: > 99%

**Manipulation System:**
- Trajectory execution success: > 98%
- End effector grasp success: > 90%
- Motor command reliability: > 99.9%
- Safety violations: 0 per 1000 cycles

**Navigation System:**
- Row following accuracy: ±10cm
- Collision avoidance: 100% success
- Positioning repeatability: ±5cm

### 8.3 Quality Assurance

#### QA-001: Software Testing
**Requirement:** Comprehensive test coverage
**Status:** ✅ 218 unit tests, 100% pass rate (Oct 21, 2025)

- Unit tests: 218 tests across packages
- Integration tests: Comprehensive test suite
- Simulation tests: Hardware-free validation
- Hardware tests: Pending field validation

**Test Coverage:**
- motor_control_ros2: 70 tests
- cotton_detection_ros2: 86 tests (54 baseline + 32 edge cases)
- yanthra_move: 17 tests
- Coverage percentage: 29% (motor_control_ros2), improving

#### QA-002: Hardware Validation
**Requirement:** Systematic hardware testing before deployment
**Status:** 🚧 IN PROGRESS

See: `docs/HARDWARE_TEST_CHECKLIST.md`

**Required Tests:**
- Motor calibration and tuning
- Camera accuracy validation with real cotton
- Multi-arm coordination
- Field environment validation
- Long-duration reliability test (24+ hours)

#### QA-003: Documentation Quality
**Requirement:** Comprehensive and accurate documentation
**Status:** ✅ EXTENSIVE DOCUMENTATION

- 150+ active markdown files
- API documentation generation
- User guides and operator manuals
- Troubleshooting guides
- Regular documentation audits

---

## 9. Development Phases

### 9.1 Expo Demo (1 Arm) - CURRENT ✅

**Status:** Core Technology Validated  
**Timeline:** Completed November 2025  
**Configuration:** 1 arm + 3-wheel vehicle

**Validated Capabilities:**
- ✅ Cotton detection (70ms latency, ±10mm @ 0.6m accuracy)
- ✅ 3-DOF arm manipulation  
- ✅ MG6010E-i6 V3 motor control via CAN bus (500 kbps)
- ✅ OAK-D Lite camera integration
- ✅ ROS2 Jazzy software stack
- ✅ Safety systems (emergency stop, limit checking)
- ✅ MQTT communication architecture
- ✅ Simulation mode for testing

**Achievement:**
- Technology demonstration successful
- Core components validated individually
- Software architecture proven
- Ready for multi-arm scaling

**Next Steps:**
- Measure actual pick cycle time (2 sec target)
- Validate end-to-end pick sequence with real cotton
- Prepare for 2-arm field trial

---

### 9.2 Field Trial (2 Arms) - JANUARY 2026 🚧

**Status:** 📝 Planned  
**Target Date:** January 5-9, 2026 OR after January 18, 2026 (1-2 days)  
**Prep Deadline:** December 31, 2025  
**Configuration:** 2 arms + 3-wheel vehicle working on **ONE ROW from EACH SIDE**

**Critical Configuration Detail:**
- Both arms operate on **ONE ROW in PARALLEL**
- One arm approaches from left side, one from right side
- Tests multi-arm coordination on same cotton plants
- Validates collision avoidance and workspace management
- Simulates production 6-arm scenario at smaller scale

**Objectives:**
1. **Validate Multi-Arm Coordination**
   - Test MQTT-based arm coordination (arm_client)
   - Validate parallel operation on same row without conflicts
   - Measure interference, workspace overlap handling
   - Test start switch signal from vehicle to arms

2. **Measure Field Performance**
   - **Actual pick cycle time** (2 sec target) with real cotton
   - Pick success rate with real cotton plants in field
   - Cotton detection accuracy in sun/field conditions
   - Battery life and power consumption measurement
   - Thermal performance (motors and camera) in outdoor conditions

3. **Test Vehicle Navigation**
   - 3-wheel mobility in actual field rows
   - Row-to-row transitions and positioning
   - Obstacle handling (plants, ground irregularities)
   - Steering and drive motor performance on soil

4. **Validate System Reliability**
   - 4-8 hour continuous operation tests
   - Error recovery procedures and fault handling
- CAN bus stability at 500 kbps (validated)
   - Camera auto-reconnect in field conditions
   - WiFi connectivity stability

**Pre-Trial Validation (Dec 2025):**
- ✅ Camera auto-reconnect: 9 sec recovery validated
- ✅ WiFi auto-reconnect: Fixed
- ✅ Vehicle CAN @ 500 kbps: Table-top validated
- ✅ H-bridge fix: 2.6A limit confirmed, boards ready
- 🚧 L3 CG fix: Temporary fix ready, proper fix + 2 new arms by Dec 26
- 🚧 2-arm integration: Required by Dec 29

**Key Deliverables:**
- Field-validated pick cycle time measurement
- Multi-arm coordination algorithms tested in real scenario
- Performance data for 6-arm system extrapolation
- Identified mechanical/electrical/software issues and fixes
- Battery runtime and power consumption data
- Field documentation and lessons learned

**Success Criteria:**
- 2 arms working in parallel on one row without conflicts
- Pick cycle time measured: target <2.5 sec (2 sec goal)
- System runs reliably for minimum 4-hour sessions
- Pick success rate >80% in field conditions
- No critical failures or safety incidents
- Motor temperatures <70°C during operation
- CAN bus @ 500 kbps: 0 errors during 4-hour run

**References:**
- Detailed plan: `docs/project-notes/JANUARY_FIELD_TRIAL_PLAN_2025.md`
- Testing matrix: `docs/project-notes/JANUARY_FIELD_TRIAL_TESTING_MATRIX.md`

---

### 9.3 Production Deployment (6 Arms) - NOVEMBER 2026 🎯

**Status:** 📝 Target  
**Deployment Date:** **November 2026 in customer fields**  
**Configuration:** 6 arms + 3-wheel vehicle

**Primary Goal:**
- **250 kg cotton per day**
- **1 acre coverage per day**
- **2 seconds per boll pick cycle**

**Required Capabilities:**
- ✅ **Continuous operation** (vehicle moves while picking) - MANDATORY
- ✅ 6 arms operating in parallel
- ✅ Motion compensation for vehicle movement
- ✅ Full autonomous navigation
- ✅ Multi-arm collision avoidance
- ✅ Robust error recovery
- ✅ 8-10 hour daily operation
- ✅ Field-proven reliability

**Why Continuous Operation is Required:**
- Stop-and-go wastes ~40% time in idle/repositioning
- Continuous operation increases throughput from ~150 kg/day → 250 kg/day
- Production goal (250kg/day, 1 acre) CANNOT be met with stop-and-go

**Production Milestones:**

| Milestone | Target Date | Description |
|-----------|-------------|-------------|
| Field Trial Complete | Q1 2026 | 2-arm system validated |
| 6-Arm Integration | Q2 2026 | Scale to full system |
| Pre-Production Testing | Q3 2026 | Extended reliability testing |
| Customer Deployment | Nov 2026 | Deploy in customer fields |

**Performance Targets:**
- Pick success rate: > 95%
- System uptime: > 95% during operation
- Spatial accuracy: ±10mm maintained
- Detection latency: < 100ms maintained
- Pick cycle: 2 seconds per boll

**Deployment Readiness Checklist:**
- [ ] 6 arms coordinated successfully
- [ ] 250 kg/day validated in test field
- [ ] Long-duration reliability (24+ hours)
- [ ] All safety systems certified
- [ ] Operator training materials complete
- [ ] Maintenance procedures documented
- [ ] Customer site preparation complete

---

## 10. Constraints & Assumptions

### 10.1 Technical Constraints

**Hardware Constraints:**
- Raspberry Pi 4B (4GB RAM) computational limits
- OAK-D Lite camera limitations (resolution, FPS, range)
- **MG6010E-i6 V3 motors:** Arm joints + vehicle steering (3 per arm × 6 arms = 18, plus 3 steering = 21 total)
  - **Rated Torque:** 1 N.m
  - **Max Torque:** 2.5 N.m (burst)
  - **Maximum Speed:** 320 rpm @ 24V
  - **Gear Ratio:** 1:6 (integrated)
  - Driver: DG80R/C7 (12-60V, 10A normal, 20A peak for 10s)
  - Encoder: 18-bit absolute position
  - Control loops: 32 KHz torque, 8 KHz speed/position
  - Source: `/home/uday/Downloads/MG60/MG_motors.pdf`
- **MG6012E-i36 V3 motors:** Vehicle drive (3 total, one per wheel)
  - **Rated Torque:** 9 N.m
  - **Max Torque:** 18 N.m (burst)
  - **Gear Ratio:** 1:36 (integrated)
  - Same driver and encoder as MG6010E-i6 V3
  - Higher torque for vehicle propulsion
  - Source: `/home/uday/Downloads/MG60/MG_motors.pdf`
- **CAN bus (SocketCAN):**
  - **Default: 500 kbps** (tested and validated for both arm and vehicle, Dec 2025)
  - Supported rates: 125, 250, 500 kbps, 1 Mbps
  - Protocol: LK-TECH CAN V2.35
  - Physical: Twisted pair, 120Ω termination at both ends
- 3-wheel vehicle payload capacity (⚠️ NEEDS SPECIFICATION)

**Software Constraints:**
- ROS2 Jazzy compatibility requirements
- Real-time control loop frequency limits
- Memory limitations on embedded systems
- Network latency in distributed system

**Environmental Constraints:**
- Daylight operation only (Phase 1)
- Dry weather conditions preferred
- Flat to gently sloped terrain
- Row-planted fields required

### 10.2 Design Assumptions

**Plant & Field Assumptions:**
- Cotton planted in straight rows with consistent spacing
- Row spacing: ⚠️ NEEDS SPECIFICATION (e.g., 0.75-1.0m)
- Plant height: ⚠️ NEEDS SPECIFICATION (e.g., 0.8-1.5m)
- Cotton boll size: ⚠️ NEEDS SPECIFICATION (e.g., 3-6cm diameter)
- Boll maturity: Ripe cotton ready for mechanical picking
- Field surface: Traversable by wheeled vehicle

**Operational Assumptions:**
- Single field operator supervising robot
- Operator trained in basic operation and troubleshooting
- Access to power for battery charging
- Maintenance performed per schedule
- Software updates applied regularly

**System Assumptions:**
- CAN bus provides reliable motor communication
- OAK-D Lite spatial accuracy sufficient for picking
- ROS2 provides adequate real-time performance
- Vacuum end effector suitable for cotton picking
- 3-DOF arm provides sufficient workspace coverage

### 10.3 Risk Assumptions

**Technical Risks:**
- Camera performance degrades in bright sunlight → Mitigation: Testing & shading
- Motor overheating during continuous operation → Mitigation: Thermal monitoring
- CAN bus communication errors → Mitigation: Auto-recovery implemented
- Software bugs in field deployment → Mitigation: Comprehensive testing

**Operational Risks:**
- Weather disrupts harvesting schedule → Mitigation: Weather monitoring
- Battery capacity insufficient → Mitigation: Runtime testing & spare batteries
- Operator error causes system damage → Mitigation: Training & safety systems
- Mechanical failures in field → Mitigation: Preventive maintenance

**Market Risks:**
- Cotton prices affect ROI → Outside system control
- Competing solutions emerge → Continuous improvement
- Regulatory changes → Compliance monitoring

---

## 11. Appendices

### Appendix A: Glossary

| Term | Definition |
|------|------------|
| **3-DOF** | Three Degrees of Freedom - three independent axes of motion |
| **CAN** | Controller Area Network - industrial communication protocol |
| **DepthAI** | Luxonis depth and AI camera SDK |
| **HSV** | Hue, Saturation, Value - color space for image processing |
| **IK** | Inverse Kinematics - converting target position to joint angles |
| **MQTT** | Message Queuing Telemetry Transport - lightweight messaging protocol |
| **OAK-D Lite** | Luxonis OpenCV AI Kit Depth Lite camera |
| **Pick Cycle** | Complete sequence: detect → approach → grasp → retract → deposit |
| **ROS2** | Robot Operating System 2 - robotics middleware framework |
| **TF / TF2** | Transform library for coordinate frame management |
| **YOLOv8** | You Only Look Once version 8 - object detection neural network |

### Appendix B: Referenced Documents

- `docs/architecture/SYSTEM_ARCHITECTURE.md` - System architecture details
- `docs/ROS2_INTERFACE_SPECIFICATION.md` - ROS2 interfaces
- `docs/requirements/COTTON_PICKING_POSITION_ACCURACY_REQUIREMENTS.md` - Position accuracy analysis
- `docs/HARDWARE_TEST_CHECKLIST.md` - Hardware validation procedures
- `docs/INDEX.md` - Documentation navigation
- `README.md` - Project overview

### Appendix C: Validation Status Summary

| Requirement Category | Total Requirements | Validated | Needs Validation | Not Implemented |
|---------------------|-------------------|-----------|------------------|-----------------|
| **Detection** | 4 | 2 | 1 | 1 |
| **Manipulation** | 5 | 3 | 2 | 0 |
| **Navigation** | 3 | 0 | 2 | 1 |
| **Communication** | 3 | 2 | 1 | 0 |
| **Performance** | 15 | 5 | 9 | 1 |
| **Operational** | 12 | 2 | 9 | 1 |
| **Safety** | 4 | 3 | 1 | 0 |
| **TOTAL** | 46 | 17 (37%) | 25 (54%) | 4 (9%) |

### Appendix D: Change Log

All changes to this document will be tracked here:

- **2025-12-16 (v1.0):** Initial draft consolidating existing specifications
- **2025-12-16 (v1.1):** Major updates based on current hardware and timeline:
  - Updated all "Raspberry Pi 5" → "Raspberry Pi 4B (4GB RAM)"
  - Updated "4-wheel" → "3-wheel vehicle"
  - Added motor specifications: MG6010E-i6 V3 (arm/steering), MG6012E-i36 V3 (drive)
  - Updated performance targets: 2 sec/boll, 250kg/day, 1 acre/day
  - Rewrote Development Phases: Expo (1 arm) → Field Trial (2 arms) → Production (6 arms, Nov 2026)
  - Updated MQTT architecture: vehicle RPi runs broker, arm_client coordination
  - Removed web dashboard as production feature (POC only)
  - Updated business objectives with concrete deployment timeline
- **2025-12-16 (v1.2):** **CRITICAL CLARIFICATIONS:**
  - **Continuous operation is REQUIRED for production** (not optional)
  - Rationale: Stop-and-go wastes ~40% time, cannot achieve 250kg/day goal
  - Field trial details: 2 arms work on ONE ROW from EACH SIDE in parallel
  - January field trial: Jan 5-9, 2026 OR after Jan 18, detailed plan referenced
  - **Motor specifications extracted from PDFs:**
    - MG6010E-i6 V3: 1 N.m rated, 2.5 N.m max, 320 rpm @ 24V
    - MG6012E-i36 V3: 9 N.m rated, 18 N.m max, 1:36 gear ratio
  - **CAN bus default: 500 kbps** (tested and validated for BOTH arm and vehicle)
  - Added pre-trial validation status from December 2025 testing
- **[NEXT]:** Final review, then update TSD with same specifications
- **[FUTURE]:** Updates after field validation and measurements (Jan 2026)

### Appendix E: Document Improvement Plan

**Known Gaps to Address:**
1. ⚠️ Specify exact motor torque and speed limits
2. ⚠️ Measure actual pick cycle time in field conditions
3. ⚠️ Validate detection accuracy with real cotton (not test objects)
4. ⚠️ Specify vehicle dimensions, weight, payload
5. ⚠️ Define row spacing and plant height requirements
6. ⚠️ Measure power consumption and battery runtime
7. ⚠️ Complete long-duration reliability testing
8. ⚠️ Validate MQTT communication latency
9. ⚠️ Specify compliance standards and certification plan
10. ⚠️ Document Phase 2 detailed implementation plan

**Review Schedule:**
- Monthly review during active development
- Quarterly review during maintenance
- Update after major milestones or field deployments

---

**END OF DOCUMENT**

**Document Owner:** Pragati Robotics Team  
**Next Review Date:** [TO BE SCHEDULED]  
**Distribution:** Internal Team, Stakeholders

---

*This is a living document. All team members are encouraged to propose improvements and corrections.*
