# System Overview

**Part of:** [Pragati Production System Documentation](../README.md)

**Version:** 4.2.0 | **Date:** 2025-10-10

---

# Pragati Cotton Picking Robot - Production System Documentation

**Date:** 2025-10-10  
**Audience:** Developers, Operators, Stakeholders  
**System Version:** 4.2.0

---

## 🎯 System Overview

The Pragati robot is an **autonomous cotton picking system** with a distributed multi-arm architecture.

### Current Implementation Status

⚠️ **CURRENT STATE (Phase 1 - NOT Production Ready):**
- **Operation Mode:** Stop-and-Go (vehicle stops before picking)
- **Camera Mode:** On-demand triggered capture (not continuous)
- **Vehicle Control:** Manual control only
- **Picking Strategy:** Single cotton per detection
- **Status:** Working but has performance and quality issues

🎯 **REQUIRED FOR PRODUCTION (Phase 2 - In Development):**
- **Operation Mode:** Continuous motion (pick while moving)
- **Camera Mode:** Continuous streaming and detection
- **Vehicle Control:** Autonomous with manual override capability
- **Picking Strategy:** Multi-cotton detection with pickability classification
- **Timeline:** Must be completed ASAP for production readiness

---

### Hardware Architecture
- **4 Independent Arms** (current deployment, scalable to 6)
  - Each arm: 3-DOF (3 joints/movements)
  - Each arm controlled by dedicated **Raspberry Pi 5**
  - Motors: **MG6010E-i6** integrated servos (3 per arm × 4 arms = 12 motors)
  - Camera: **Luxonis OAK-D Lite** (1 per arm)
  - Communication: CAN bus (250 kbps) per Raspberry Pi

- **Vehicle mobility** (4 wheels with steering)
- **Computer vision** (OAK-D Lite cameras with DepthAI SDK)
- **Motor control** (MG6010E-i6 integrated servos via CAN bus)

**Mission:** Autonomously navigate cotton fields, detect ripe cotton using multiple cameras, and pick it using coordinated robotic arms.

**Scalability:** Architecture designed for 6-arm configuration (Phase 2 expansion).



## 🏗️ System Architecture

### Multi-Arm Distributed Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│              Central Control (Main Computer)                      │
│               - Vehicle Navigation                                │
│               - Arm Coordination                                  │
│               - ROS2 Master                                       │
└───────┬────────────┬────────────┬────────────┬───────────────────┘
        │            │            │            │
        │            │            │            │
   ┌────▼───┐   ┌───▼────┐   ┌──▼─────┐   ┌──▼─────┐
   │ ARM 1  │   │ ARM 2  │   │ ARM 3  │   │ ARM 4  │  (+ ARM 5, 6 planned)
   │ RPi 5  │   │ RPi 5  │   │ RPi 5  │   │ RPi 5  │
   └────┬───┘   └───┬────┘   └──┬─────┘   └──┬─────┘
        │            │            │            │
    ┌───▼────────────▼────────────▼────────────▼──────┐
    │                                                   │
    │  Each Arm Node (Raspberry Pi 5):                 │
    │                                                   │
    │  ┌──────────────────────────────────────┐        │
    │  │  Cotton Detection (C++ DepthAI)      │        │
    │  │  - OAK-D Lite Camera                 │        │
    │  │  - Direct DepthAI integration        │        │
    │  │  - YOLO inference on Myriad X VPU    │        │
    │  └──────────┬───────────────────────────┘        │
    │             │                                     │
    │  ┌──────────▼───────────────────────────┐        │
    │  │  Motor Control (CAN Bus)             │        │
    │  │  - 3x MG6010E-i6 motors              │        │
    │  │  - CAN 250 kbps                      │        │
    │  │  - Joint 1: Base/Rotation            │        │
    │  │  - Joint 2: Middle segment           │        │
    │  │  - Joint 3: End effector             │        │
    │  └──────────────────────────────────────┘        │
    │                                                   │
    └───────────────────────────────────────────────────┘

**Key Architecture Points:**
- Each arm is **autonomous** with its own RPi, camera, and motors
- **Distributed processing**: Detection happens on each arm's RPi
- **CAN bus per arm**: Each RPi controls 3 motors via local CAN interface
- **Centralized coordination**: Main computer manages arm cooperation
- **Scalable**: Currently 4 arms, designed for 6 arms total
```


