# Hardware Architecture & Startup

**Part of:** [Pragati Production System Documentation](../README.md)

---

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
    │  │  - CAN 500 kbps                      │        │
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


## 🚀 Production Startup Sequence

### Step 1: System Power-On

**Hardware Initialization:**
```bash
# 1. Power on Raspberry Pi 5 / Main Computer
# System boots Ubuntu 24.04

# 2. CAN Bus Initialization (automatic via systemd)
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# 3. Motor Power Check
# Verify 24V power supply to all 5 MG6010-i6 motors
# Check: Voltage should be 22-28V
```

---

### Step 2: ROS2 System Launch

**Main Launch Command:**
```bash
cd ~/pragati_ros2
source install/setup.bash

# Launch complete robot system
ros2 launch pragati_complete.launch.py

# This starts:
# - Robot state publisher
# - Yanthra move (arm control)
# - Cotton detection node
# - Vehicle control
# - Motor controllers
# - GPIO interface
```

**What Happens During Launch:**

1. **Robot State Publisher** loads URDF model
2. **Motor Control** initializes CAN bus
3. **Motors** receive motor_on() commands
4. **Camera** initializes OAK-D Lite
5. **Services** become available
6. **Topics** start publishing

---

### Step 3: System Health Check

**Automatic Checks:**
```bash
# ROS2 performs automatic health checks:
✅ All 5 motors respond to status queries
✅ Camera detects and streams
✅ CAN bus communication < 10ms latency
✅ All ROS2 nodes running
✅ Services available
✅ Topics publishing at expected rates
```

**Manual Verification (if needed):**
```bash
# Check all nodes running
ros2 node list

# Check motor status
ros2 service call /yanthra_move/get_motor_status ...

# Check camera
ros2 topic echo /cotton_detection/camera_info

# Check CAN interface
ip -details link show can0
```

---
