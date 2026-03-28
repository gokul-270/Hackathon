# January Field Trial - Testing Matrix

**Created:** December 9, 2025
**Updated:** January 2, 2026
**Purpose:** Day-by-day testing checklist for Vehicle, ARM, and Multi-ARM combinations
**Field Trial:** January 7-8, 2026 (CONFIRMED)
**Related:** [JANUARY_FIELD_TRIAL_PLAN_2026.md](JANUARY_FIELD_TRIAL_PLAN_2026.md)

---

## System Architecture

```
VEHICLE (1 RPi):
├── 3 wheels × (1 drive + 1 steering) = 6 motors total
├── CAN bus @ 500kbps
└── MQTT → sends start_switch, shutdown to ARMs

EACH ARM (independent RPi per arm):
├── 3 motors (J3, J4, J5) via CAN
├── 1 camera (OAK-D)
├── MQTT ← receives start_switch, shutdown from Vehicle
└── MQTT → publishes ArmStatus (ready/ACK/busy) to Vehicle

Vehicle must wait for ARM status = "ready" before sending start command.
```

---

## Testing Phases Overview

```
Phase 0: PRE-HARDWARE (Now)        → Software tests on single RPi (no motor HW needed)
Phase 1: SINGLE ARM (Dec 9-15)     → Validate arm mechanics + software
Phase 2: VEHICLE ONLY (Dec 16-19)  → Validate vehicle mechanics + software  
Phase 3: VEHICLE + 1 ARM (Dec 22-24) → Integrated testing (MQTT bridge)
Phase 4: VEHICLE + 2 ARMS (Dec 29-31) → Full system validation
```

---

## Phase 0: PRE-HARDWARE Tests (Run NOW - Single RPi + Camera)

**Hardware available:** 1 RPi + Camera + SSD (no motors, no cotton)
**Goal:** Validate software before hardware arrives, reduce risk

### ✅ Phase 0 Tests Complete (Dec 10, 2025)

**Summary:** 17/18 tests PASSED (1 requires manual testing)

**Vehicle Tests (13/13 PASSED):**
- ✅ Infrastructure: All 5 tests passing (CAN DOWN expected without motors)
- ✅ Vehicle Node: All 8 tests passing including new motor validation features
- ✅ **New Features Validated:**
  - Health score correctly reports 20/100 with 0 available motors (was incorrectly 80/100)
  - Motor availability service reports actual motor status (0/6 available)
  - Test motors service validates actual position changes (0/6 passed correctly)
  - False positive test fixes prevent reporting motors as working when they're not

**Camera Tests (4/4 PASSED):**
- ✅ Camera launches and connects to OAK-D Lite (USB 3.0, 5Gbps)
- ✅ Detection service responds correctly with empty scene (0 detections)
- ✅ No-cotton behavior: Node stable, no crashes with empty detections
- ✅ Auto-reconnect: USB unplug/replug test PASSED (Dec 10 - 9s recovery)

**ARM Tests:** 
- ⬜ Deferred - Require either motors or pure simulation mode without motor_control node

**Key Validation:** System now accurately detects motor failures instead of giving false confidence.

### Infrastructure (Run NOW)

| # | Test | Command | Pass Criteria | Previously | Status |
|---|------|---------|---------------|------------|--------|
| 0.1 | pigpiod service | `systemctl status pigpiod` | Active | ✅ Done | ✅ PASS (Dec 9) |
| 0.2 | SSD mounted | `df -h` (check SSD) | SSD visible | ✅ Done | ✅ PASS (Dec 9) |
| 0.3 | ROS2 Jazzy | `ros2 topic list` | Responds | ✅ Done | ✅ PASS (Dec 9) |
| 0.4 | Workspace build | Check install/ dir | All packages | ✅ Done | ✅ PASS (Dec 9) |
| 0.5 | CAN interface | `ip link show can0` | UP/DOWN | ✅ Done | ⚠️ DOWN (no motors) |

### Vehicle Node - Simulation Mode (Run NOW) 🆕 Changed Dec 9

| # | Test | Command | Pass Criteria | Previously | Status |
|---|------|---------|---------------|------------|--------|
| 0.6 | Vehicle node launch | `ros2 launch vehicle_control vehicle_complete.launch.py` | Node starts | 🆕 Changed | ✅ PASS (Dec 9) |
| 0.7 | Self-test service | `ros2 service call /vehicle/vehicle_control/self_test std_srvs/srv/Trigger` | Returns result | 🆕 New | ✅ PASS (Dec 9) |
| 0.8 | Diagnostics service | `ros2 service call /vehicle/vehicle_control/diagnostics std_srvs/srv/Trigger` | Returns health 20/100 | 🆕 New | ✅ PASS (Dec 9) |
| 0.9 | Status topic | `ros2 topic hz /vehicle/status_detailed` | Publishing | 🆕 New | ✅ PASS (Dec 9) |
| 0.10 | Enable motors (sim) | `ros2 service call /vehicle/vehicle_control/enable_motors std_srvs/srv/SetBool "{data: true}"` | Responds | 🆕 Changed | ✅ PASS (Dec 9) |
| 0.11 | All 11 services exist | `ros2 service list | grep vehicle_control/` | 11+ services | 🆕 New | ✅ PASS (Dec 9) |
| 0.11a | Motor availability | `ros2 service call /vehicle/get_motor_availability std_srvs/srv/Trigger` | Reports 0/6 | 🆕 New | ✅ PASS (Dec 9) |
| 0.11b | Test motors service | `ros2 service call /vehicle/vehicle_control/test_motors std_srvs/srv/SetBool "{data: true}"` | Reports 0/6 passed | 🆕 New | ✅ PASS (Dec 9) |

### Camera Tests (Run NOW - No cotton needed)

**Add-on (Dec 15 review):** 8–10hr camera+detection soak (no arm motion) before full arm long-run.

| # | Test | Command | Pass Criteria | Previously | Status |
|---|------|---------|---------------|------------|--------|
| 0.12 | Camera launch | `ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py` | Connects | ✅ Done | ✅ PASS (Dec 9) |
| 0.13 | Detection service | `ros2 service call /cotton_detection/detect ...` | Responds (0 detections OK) | ✅ Done | ✅ PASS (Dec 9) |
| 0.14 | Camera auto-reconnect | Unplug USB, wait 5s, replug | Auto-recovers | ✅ Done | ✅ PASS (Dec 10) |
| 0.15 | No-cotton behavior | Trigger with empty scene | No crash, returns 0 | Untested | ✅ PASS (Dec 9) |

### MQTT Tests (Run NOW - localhost)

| # | Test | Command | Pass Criteria | Previously | Status |
|---|------|---------|---------------|------------|--------|
| 0.16 | MQTT broker | `sudo apt install mosquitto && systemctl status mosquitto` | Running | Untested | ⬜ NEW |
| 0.17 | MQTT pub/sub | `mosquitto_pub -t test -m "hello"` / `mosquitto_sub -t test` | Message received | Untested | ⬜ NEW |
| 0.18 | ARM_client.py | `python3 launch/ARM_client.py` (localhost) | Connects to broker | ✅ Done | ⬜ Re-test |

### Arm Node - Simulation Mode (Deferred - Need Pure Sim Mode)

| # | Test | Command | Pass Criteria | Previously | Status |
|---|------|---------|---------------|------------|--------|
| 0.19 | Arm launch (sim) | `ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true` | Starts | ✅ Done | ⬜ Needs motors or stub |
| 0.20 | TF tree | `ros2 run tf2_tools view_frames` | Valid tree | ✅ Done | ⬜ Needs 0.19 |
| 0.21 | Arm status service | `ros2 service call /yanthra_move/current_arm_status` | Returns status | ✅ Done | ⬜ Needs 0.19 |

**Note:** Current use_simulation:=true still tries to initialize motor_control which requires CAN. Need to either:
1. Wait for motors to arrive, OR
2. Implement pure simulation mode that bypasses motor_control node

**✅ COMPLETED:** All vehicle tests (0.6-0.11b) validated Dec 9, 2025

**Test Evidence:**
- Launch log: `/tmp/test_nocache.log` on RPi
- Commit: `9972339b` - "Fix false positive motor tests and health score reporting"
- Files changed: test_motors.sh, hardware_integration_test.sh, mg6010_controller_node.cpp, vehicle_control_node.py, vehicle_motors.yaml

---

## Phase 1: SINGLE ARM Testing (Dec 9-15)

**Add-on (Dec 15 review):** URDF validation for new arm design generation (Owner: Shwetha).

### Dec 9-10: Joint Drift Test (CRITICAL BLOCKER)
**Hardware:** Expo arm on table-top setup (L4 tuned, L3 reduced)
**Software:** ROS2 motor_control node
**Mode:** WITHOUT camera - motor-only drift confirmation

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 1.1 | Motor CAN communication | `ros2 launch motor_control_ros2 mg6010_controller.launch.py` | All 3 motors (J3, J4, J5) respond | ⬜ |
| 1.2 | Joint homing | `ros2 service call /motor_control/joint_homing std_srvs/srv/Trigger` | All joints home successfully | ⬜ |
| 1.3 | Joint drift test (10 cycles) | Run 10 move cycles WITHOUT camera, measure home position | Drift < 5mm after 10 cycles | ⬜ |
| 1.4 | Temperature monitoring | Check motor temps after 10 cycles | All motors < 60°C | ⬜ |
| 1.5 | CAN bus stability | Monitor `candump can0` during cycles | No bus-off errors | ⬜ |
| 1.6 | **PID tuning (if drift)** | Use `docs/guides/MOTOR_TUNING_GUIDE.md` | Smooth movement, no oscillation | ⬜ |

**Blocker:** If drift > 5mm, STOP → check PID tuning → debug before proceeding.
**Reference:** [MOTOR_TUNING_GUIDE.md](../guides/MOTOR_TUNING_GUIDE.md), [PID_VISUALIZATION_GUIDE.md](../guides/PID_VISUALIZATION_GUIDE.md)

---

### Dec 11-12: End Effector Test (After IO Board)
**Hardware:** IO Board with H-bridge fix (arriving Dec 10)
**Software:** GPIO + end effector control

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 2.1 | Compressor GPIO | `pigs w 18 1` (ON) / `pigs w 18 0` (OFF) | Compressor activates | ⬜ |
| 2.2 | End effector GPIO | Test EE on/off | EE responds | ⬜ |
| 2.3 | End effector suction | Test with paper/cotton | Holds object | ⬜ |
| 2.4 | EE timing sequence | Run with `ee_post_joint5_delay: 0.5` | Proper timing | ⬜ |

---

### Dec 15-16: Single ARM Pick Cycle + Long-Run
**Hardware:** Expo arm with camera
**Software:** Full yanthra_move stack

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 3.1 | pigpiod running | `systemctl status pigpiod` | Active | ⬜ |
| 3.2 | Camera detection | `ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py` | Detections published | ⬜ |
| 3.3 | Camera auto-reconnect | Unplug/replug USB | Camera recovers | ⬜ |
| 3.4 | Transform chain | `ros2 run tf2_tools view_frames` | Camera→yanthra_link valid | ⬜ |
| 3.5 | No cotton behavior | Trigger with no cotton visible | Handles gracefully, no crash | ⬜ |
| 3.6 | Single pick cycle | Trigger via `/start_switch/command` | Completes in <3s | ⬜ |
| 3.7 | 10 consecutive picks | Run 10 cycles | 100% success rate | ⬜ |
| 3.8 | **ARM Long-run (2hr)** | Continuous operation | No drift, temps <70°C | ⬜ |
| 3.9 | Motor temperature | Check after long-run | Joint3 <70°C | ⬜ |
| 3.10 | CAN bus health | `ip -s link show can0` | 0 TX/RX errors | ⬜ |
| 3.11 | SSD logging | Check `/var/log/ros2/` | Logs written | ⬜ |

**ARM Long-Run Test Protocol:**
```
Duration: 2 hours
Cycles: Every 30 seconds trigger pick
Monitor: Temperature, drift, CAN errors
Pass: No failures, temp <70°C, drift <5mm
```

---

## Phase 2: VEHICLE Testing (Dec 16-19)

### Dec 16: Vehicle Assembly Validation
**Hardware:** Vehicle with 6 MG6010 motors (3 drive + 3 steering, one per wheel)
**Software:** vehicle_control node
**⚠️ CAUTION:** No spare drive motors - handle carefully

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 4.1 | Vehicle CAN communication | `ros2 launch vehicle_control vehicle_complete.launch.py` | All 6 motors respond | ⬜ |
| 4.2 | Motor enable | `ros2 service call /vehicle/vehicle_control/enable_motors std_srvs/srv/SetBool "{data: true}"` | All motors enabled | ⬜ |
| 4.3 | Motor disable | `ros2 service call /vehicle/vehicle_control/enable_motors std_srvs/srv/SetBool "{data: false}"` | All motors disabled | ⬜ |
| 4.4 | Vehicle self-test | `ros2 service call /vehicle/vehicle_control/self_test std_srvs/srv/Trigger` | 5/5 tests pass | ⬜ |
| 4.5 | Diagnostics service | `ros2 service call /vehicle/vehicle_control/diagnostics std_srvs/srv/Trigger` | Health score >80 | ⬜ |
| 4.6 | Status topic | `ros2 topic echo /vehicle/status_detailed` | JSON status at 5Hz | ⬜ |

---

### Dec 17: Vehicle Motor Tests
**Hardware:** Vehicle with wheels (can be on jacks)
**Software:** vehicle_control + joystick

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 5.1 | Drive motor forward | Joystick forward | All 3 drive motors spin | ⬜ |
| 5.2 | Drive motor reverse | Joystick backward | All 3 drive motors spin | ⬜ |
| 5.3 | Steering left | Joystick left | All 3 steering motors respond | ⬜ |
| 5.4 | Steering right | Joystick right | All 3 steering motors respond | ⬜ |
| 5.5 | Steering limits | Test full range | Limits respected | ⬜ |
| 5.6 | Emergency stop | E-STOP button (if working) | All motors stop (🟡 nice-to-have) | ⬜ |
| 5.7 | Motor temperature | After 10min operation | All motors <60°C | ⬜ |

---

### Dec 18-19: Vehicle Driving Tests
**Add-on Safety/Field Tests (Dec 15 review):**
- 45° slope test (fixture + safety SOP + execute)
- Battery peak/steady current capture under load
- Electrical E-STOP verification under load
- Failure recovery drill (software + electrical)

**Hardware:** Vehicle on ground
**Software:** Full vehicle stack

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 6.1 | Forward drive (slow) | Joystick 25% | Moves forward straight | ⬜ |
| 6.2 | Forward drive (full) | Joystick 100% | Max speed achieved | ⬜ |
| 6.3 | Reverse drive | Joystick back | Moves backward | ⬜ |
| 6.4 | Turn left | Steer + drive | Vehicle turns left | ⬜ |
| 6.5 | Turn right | Steer + drive | Vehicle turns right | ⬜ |
| 6.6 | Pivot mode | Both steer 90° | Vehicle pivots in place | ⬜ |
| 6.7 | Figure-8 pattern | Drive figure-8 | Smooth steering | ⬜ |
| 6.8 | **30min continuous** | Drive for 30min | No failures | ⬜ |
| 6.9 | CAN 500kbps validation | Monitor during drive | No bus errors | ⬜ |

---

## Phase 3: VEHICLE + 1 ARM Integration (Dec 22-24)

### Dec 22: Mount & Initial Integration
**Hardware:** Vehicle + expo arm mounted
**Software:** Full system (vehicle + arm + camera)

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 7.1 | ARM mount verification | Physical inspection | Arm secure, aligned | ⬜ |
| 7.2 | Network between RPis | Ping ARM RPi from Vehicle RPi | <10ms latency | ⬜ |
| 7.3 | MQTT broker | `systemctl status mosquitto` on broker | Running | ⬜ |
| 7.4 | MQTT bridge | `python3 launch/ARM_client.py` | Vehicle↔Arm MQTT working | ⬜ |
| 7.5 | Arm status to vehicle | `topic/ArmStatus_arm5` | Vehicle receives ready/busy | ⬜ |
| 7.6 | Start switch from vehicle | `topic/start_switch_input_` | Arm receives, publishes ACK | ⬜ |
| 7.7 | Shutdown from vehicle | `topic/shutdown_switch_input` | Arm shuts down gracefully | ⬜ |
| 7.8 | Vehicle waits for ready | Check arm status before start | No start if arm busy | ⬜ |

---

### Dec 23: Integrated Operation
**Hardware:** Vehicle + 1 arm + camera
**Software:** Full integrated stack

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 8.1 | Stationary pick | Vehicle stopped, arm picks | Pick successful | ⬜ |
| 8.2 | 5 consecutive picks | Trigger 5 times | 100% success | ⬜ |
| 8.3 | Move → stop → pick | Drive, stop, trigger pick | Sequence works | ⬜ |
| 8.4 | 10 move-pick cycles | Repeat move→stop→pick | >90% success | ⬜ |
| 8.5 | Arm-vehicle coordination | Check timing | Arm doesn't pick while moving | ⬜ |

---

### Dec 24: Joints Calibration & Tuning
**Hardware:** Vehicle + 1 arm
**Software:** Tuning parameters

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 9.1 | Joint velocity tuning | Adjust speeds in YAML | Smooth movement | ⬜ |
| 9.2 | Joint acceleration tuning | Adjust accel in YAML | No jerky motion | ⬜ |
| 9.3 | Home position fine-tune | Adjust home angles | Accurate home | ⬜ |
| 9.4 | Pick position accuracy | Measure actual vs target | Error <10mm | ⬜ |
| 9.5 | Compressor timing | Adjust delays | Proper suction | ⬜ |
| 9.6 | EE timing | Adjust `ee_post_joint5_delay` | Reliable grip | ⬜ |

---

## Phase 4: VEHICLE + 2 ARMS (Dec 29-31)

### Dec 29: 2-ARM Mount & Integration
**Hardware:** Vehicle + 2 new arms (with proper CG fix)
**Software:** Multi-arm configuration

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 10.1 | ARM1 mount verification | Physical inspection | Arm secure | ⬜ |
| 10.2 | ARM2 mount verification | Physical inspection | Arm secure | ⬜ |
| 10.3 | ARM1 RPi CAN | `candump can0` on ARM1 RPi | 3 motors respond | ⬜ |
| 10.4 | ARM2 RPi CAN | `candump can0` on ARM2 RPi | 3 motors respond | ⬜ |
| 10.5 | Vehicle RPi CAN | `candump can0` on Vehicle RPi | 6 motors respond | ⬜ |
| 10.6 | Vehicle↔ARM1 network | Ping ARM1 from Vehicle | Connected | ⬜ |
| 10.7 | Vehicle↔ARM2 network | Ping ARM2 from Vehicle | Connected | ⬜ |
| 10.8 | ARM1 MQTT bridge | ARM_client.py on ARM1 | Publishes ArmStatus | ⬜ |
| 10.9 | ARM2 MQTT bridge | ARM_client.py on ARM2 | Publishes ArmStatus | ⬜ |
| 10.10 | ARM1 independent test | Trigger ARM1 only | ARM1 picks | ⬜ |
| 10.11 | ARM2 independent test | Trigger ARM2 only | ARM2 picks | ⬜ |

---

### Dec 29-30: 2-ARM Long-Run Test (CRITICAL)
**Hardware:** Full system
**Software:** Production configuration

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 11.1 | **4-hour long-run** | Continuous operation | No failures | ⬜ |
| 11.2 | Alternating picks | ARM1 → ARM2 → ARM1... | Both arms work | ⬜ |
| 11.3 | Move-pick cycle (100x) | 100 complete cycles | >95% success | ⬜ |
| 11.4 | Temperature check | All motors | All <70°C | ⬜ |
| 11.5 | CAN bus health | After 4 hours | 0 errors | ⬜ |
| 11.6 | Memory stability | Monitor RPi memory | No leaks (<500MB) | ⬜ |
| 11.7 | CPU stability | Monitor CPU | <70% average | ⬜ |
| 11.8 | Joint drift | Measure home positions | Drift <5mm | ⬜ |

**Long-Run Protocol:**
```
Duration: 4 hours
Cycle: Pick every 30s, alternating arms
Vehicle: Move every 5 picks
Monitor: Temps, CAN, drift, memory, CPU
Pass: >95% pick success, 0 CAN errors, all temps <70°C
```

---

### Dec 30-31: Final Validation & Packing
**Hardware:** Full system
**Software:** Final configuration

| # | Test | Command/Steps | Pass Criteria | Status |
|---|------|---------------|---------------|--------|
| 12.1 | Cold start test | Power off, wait 30min, restart | System boots cleanly | ⬜ |
| 12.2 | Full boot sequence | All services auto-start | Everything runs | ⬜ |
| 12.3 | Network connectivity | SSH from remote | Stable connection | ⬜ |
| 12.4 | Final 1-hour test | Full operation | 100% success | ⬜ |
| 12.5 | Shutdown procedure | Graceful shutdown | Clean exit | ⬜ |
| 12.6 | System backup | Clone SD card | Backup ready | ⬜ |
| 12.7 | Spare parts check | Inventory | All items present | ⬜ |
| 12.8 | Pack for transport | Secure all components | Ready to ship | ⬜ |

---

## Quick Reference Commands

### ARM Commands
```bash
# Launch arm motors only (for drift test without camera)
ros2 launch motor_control_ros2 mg6010_controller.launch.py

# Launch full arm system (motors + camera + control)
ros2 launch yanthra_move pragati_complete.launch.py

# Trigger pick
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"

# Check arm status
ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus
```

### Vehicle Commands
```bash
# Launch vehicle
ros2 launch vehicle_control vehicle_complete.launch.py

# Enable motors (via vehicle_control)
ros2 service call /vehicle/vehicle_control/enable_motors std_srvs/srv/SetBool "{data: true}"

# Disable motors (via vehicle_control)
ros2 service call /vehicle/vehicle_control/enable_motors std_srvs/srv/SetBool "{data: false}"

# Self-test
ros2 service call /vehicle/vehicle_control/self_test std_srvs/srv/Trigger

# Diagnostics
ros2 service call /vehicle/vehicle_control/diagnostics std_srvs/srv/Trigger
```

### Camera Commands
```bash
# Launch camera
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Trigger detection
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

### Monitoring Commands
```bash
# CAN bus monitoring
candump can0

# CAN bus stats
ip -s link show can0

# Motor temperatures (check logs)
ros2 topic echo /motor_stats

# System health
htop
```

---

## Spare Parts Inventory

| Item | Quantity | Notes |
|------|----------|-------|
| MG6010 motors (arm/steering) | 3 | Can be used for arm OR vehicle steering |
| MG6010 motors (drive) | 0 | ⚠️ NO SPARES - be careful with drive motors |
| IO Boards | 2 | With H-bridge fix |
| SD cards | Multiple | Pre-loaded with Ubuntu + ROS2 |
| USB cables | Multiple | Camera, serial |
| CAN terminators | 2 | |
| Power cables | Multiple | |

**⚠️ CRITICAL:** No spare drive motors available. Handle drive motors with extra care during testing.

---

## Test Sign-Off

| Phase | Date | Tester | Result | Notes |
|-------|------|--------|--------|-------|
| Phase 1: Single ARM | | | | |
| Phase 2: Vehicle | | | | |
| Phase 3: Vehicle + 1 ARM | | | | |
| Phase 4: Vehicle + 2 ARMs | | | | |

**Final Sign-Off:**
- [ ] All phases passed
- [ ] Long-run test completed (4hr)
- [ ] System packed for field
- [ ] Spare parts verified (3 motors for arm/steering, 0 for drive)
- [ ] Documentation complete

---

**Document Version:** 1.1
**Last Updated:** January 2, 2026
**Status:** Active - Field Trial Jan 7-8
**Related Plan:** [JANUARY_FIELD_TRIAL_PLAN_2026.md](JANUARY_FIELD_TRIAL_PLAN_2026.md)
