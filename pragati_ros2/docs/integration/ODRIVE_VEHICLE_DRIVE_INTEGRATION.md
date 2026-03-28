# ODrive Vehicle Drive Integration

## Overview

The Pragati vehicle has **two independent motor controller systems** sharing a single CAN bus (`can0` at 500 kbps):

| System | Motors | Controller | Protocol | CAN ID Range |
|--------|--------|-----------|----------|--------------|
| **Steering** | 3x MG6010E-i6 | `motor_control_ros2` | MG6010 proprietary | `0x140`-`0x240` |
| **Drive** | 3x ODrive Pro | `odrive_control_ros2` | ODrive CANSimple v0.6 | `0x000`-`0x05F` |

The two controllers are **fault-isolated**: if one crashes or fails to start, the other continues operating independently.

```
                        ┌─────────────────────────────────────────────────┐
                        │              vehicle_complete.launch.py          │
                        └───────┬──────────────────┬──────────────────┬───┘
                                │ t+0.3s           │ t+0.5s           │ t+25s
                                ▼                  ▼                  ▼
                     ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
                     │ mg6010_controller │  │ odrive_service   │  │ vehicle_control  │
                     │ _node             │  │ _node            │  │ _node            │
                     │ (steering)        │  │ (drive)          │  │ (state machine)  │
                     └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
                              │                     │                     │
                              │ CAN TX/RX           │ CAN TX/RX          │ ROS2 topics
                              │ 0x141,0x143,0x145   │ 0x000-0x05F        │ /vehicle/*
                              │                     │                     │
                              └──────────┬──────────┘                     │
                                         ▼                                │
                              ┌──────────────────┐                        │
                              │    can0 bus       │                        │
                              │   500 kbps        │◄─────────────────────-─┘
                              └──────────────────┘         (via topics)
                                         │
                    ┌────────────────────┬┴───────────────────┐
                    ▼                    ▼                    ▼
              ┌──────────┐        ┌──────────┐        ┌──────────┐
              │ MG6010x3 │        │ ODrive x3│        │          │
              │ steer_*  │        │ drive_*  │        │ (future) │
              └──────────┘        └──────────┘        └──────────┘
```

---

## 1. CAN Bus Architecture

### 1.1 Arbitration ID Scheme

The two protocols use **non-overlapping CAN ID ranges**, so they coexist on the same bus without hardware filtering:

**ODrive CANSimple:**
```
arb_id = (node_id << 5) | cmd_id

Node 0: 0x000-0x01F  (drive_front)
Node 1: 0x020-0x03F  (drive_left_back)
Node 2: 0x040-0x05F  (drive_right_back)
```

**MG6010:**
```
arb_id = 0x140 + motor_id

Motor 1: 0x141  (steer_front)
Motor 3: 0x143  (steer_left_back)
Motor 5: 0x145  (steer_right_back)
```

No overlap exists between `0x000-0x05F` and `0x140+`.

### 1.2 CAN Frame Filtering

Each controller filters out the other's frames to prevent parse errors:

| Controller | Filter Method | Location |
|-----------|---------------|----------|
| ODrive node | **Kernel-level** `SO_CAN_FILTER` (mask `0x7E0`) on socket | `socketcan_interface.cpp` |
| MG6010 node | **Software-level** range check in `receive_message()` — discards frames with `arb_id < 0x140` or `arb_id > 0x240` | `mg6010_can_interface.cpp:184-189` |

### 1.3 CAN Bus Setup

The launcher script (`scripts/launch/launcher.sh`) configures:
```bash
sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 txqueuelen 1000
```

- `restart-ms 100`: Auto-recover from bus-off within 100ms
- `berr-reporting on`: Enable bus error reporting for diagnostics
- `txqueuelen 1000`: Large TX queue for 6 motors at 50Hz

---

## 2. ODrive Service Node (`odrive_service_node.cpp`)

**Package:** `odrive_control_ros2`
**Executable:** `odrive_service_node`
**Launch name:** `vehicle_drive_control` (namespace: `/vehicle`)

### 2.1 Control Modes

The node supports two **mutually exclusive** modes, selected by the `control_mode` parameter:

| Mode | Use Case | Control Mode | Input Mode | Config File |
|------|---------|-------------|-----------|-------------|
| `"position"` (default) | Arm joints (joint3/4/5) | `POSITION_CONTROL` | `TRAP_TRAJ` | `production.yaml` |
| `"velocity"` | Drive wheels | `VELOCITY_CONTROL` | `VEL_RAMP` | `vehicle_drive.yaml` |

For vehicle drive, only **velocity mode** is used.

### 2.2 Startup Sequence (Velocity Mode)

```
t=0.0s   Node starts, opens CAN socket, starts RX thread
t=0.0s   Declares velocity command subscribers, e-stop subscriber, watchdog timer
t=1.0s   One-shot timer fires velocity_mode_init():
           For each axis:
             1. Check heartbeat received (skip if not)
             2. Send SET_CONTROLLER_MODE(VELOCITY_CONTROL, VEL_RAMP)
             3. Wait 50ms
             4. Send SET_AXIS_STATE(CLOSED_LOOP_CONTROL)
             5. Wait up to init_timeout (10s) for heartbeat to confirm state
             6. Mark axis_ready = true
```

If an axis fails to initialize, the node continues with the remaining axes (**partial operation**). Failed axes will be re-initialized automatically when the next velocity command arrives.

### 2.3 ROS2 Interface (Velocity Mode)

#### Topics Subscribed

| Topic | Type | Purpose |
|-------|------|---------|
| `/drive_front_velocity_controller/command` | `std_msgs/Float64` | Velocity command for front drive motor |
| `/drive_left_back_velocity_controller/command` | `std_msgs/Float64` | Velocity command for left-back drive motor |
| `/drive_right_back_velocity_controller/command` | `std_msgs/Float64` | Velocity command for right-back drive motor |
| `/vehicle/emergency_stop_cmd` | `std_msgs/Float64` | E-stop signal (>0.5 = activate, <0.5 = clear) |

#### Topics Published

| Topic | Type | Rate | Purpose |
|-------|------|------|---------|
| `/vehicle/joint_states` | `sensor_msgs/JointState` | 50 Hz | Position (rad) and velocity (rad/s) for all 3 drive joints |

#### Services (Position Mode Only)

In velocity mode, the following services are **NOT created** since homing/idle/status are meaningless for drive wheels:
- `/joint_homing`
- `/joint_idle`
- `/joint_status`

### 2.4 Parameters

All parameters are under the `odrive_service_node` namespace in `vehicle_drive.yaml`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `interface_name` | string | `"can0"` | CAN interface name |
| `control_mode` | string | `"velocity"` | `"velocity"` or `"position"` |
| `joint_names` | string[] | `["drive_front", "drive_left_back", "drive_right_back"]` | Joint names matching topic pattern |
| `node_ids` | int[] | `[0, 1, 2]` | ODrive CAN node IDs (set via odrivetool, saved to NVM) |
| `directions` | float[] | `[-1.0, -1.0, -1.0]` | Motor direction multiplier |
| `transmission_factors` | float[] | `[1.0, 1.0, 1.0]` | Joint velocity -> motor turns/s. **DEPLOYMENT BLOCKER: placeholder** |
| `watchdog_timeout` | float | `0.5` | Seconds before zero-velocity on command loss. 0 = disabled |
| `init_timeout` | float | `10.0` | Seconds to wait for axis to enter CLOSED_LOOP_CONTROL |
| `joint_states_rate` | float | `50.0` | JointState publish rate (Hz) |
| `encoder_request_rate` | float | `50.0` | Encoder RTR request rate (Hz) |

### 2.5 Velocity Command Flow

```
ROS2 topic msg (Float64: velocity in joint units)
  │
  ▼
handle_velocity_command(node_id, velocity)
  │
  ├── If e_stopped_ → reject, log warning (throttled 2s)
  │
  ├── If !axis_ready && axis is IDLE && !e_stopped_ → reinit_axis()
  │     └── clear_errors → set mode → CLOSED_LOOP_CONTROL → wait 5s
  │
  ├── Scale: velocity_turns = velocity * transmission_factor * direction
  │
  ├── CAN TX: SET_INPUT_VEL (cmd 0x0D)
  │     arb_id = (node_id << 5) | 0x0D
  │     payload = [float32 velocity_turns, float32 torque_ff=0.0]
  │
  └── Update watchdog: last_velocity_command_time = now()
```

### 2.6 Command Watchdog

A 10 Hz timer (`watchdog_check()`) monitors each axis. If no velocity command arrives within `watchdog_timeout` (default 0.5s):

1. Send `SET_INPUT_VEL(0.0)` — zero velocity
2. Send `SET_AXIS_STATE(IDLE)` — secondary safety
3. Mark `axis_ready = false`
4. Log warning (throttled 2s)

The axis will automatically re-initialize on the **next velocity command** via `reinit_axis()`.

### 2.7 E-Stop Flow

```
User/System calls SetBool service at /vehicle/emergency_stop
  │
  ▼
vehicle_control_node.py (SetBool callback)
  ├── Publishes Float64(1.0) to /vehicle/emergency_stop_cmd  [activate]
  └── Publishes Float64(0.0) to /vehicle/emergency_stop_cmd  [clear]
        │
        ▼
odrive_service_node (subscriber callback)
  │
  ├── ACTIVATE (data > 0.5):
  │     ├── Set e_stopped_ = true
  │     ├── For each axis: send ESTOP CAN cmd (0x02, empty payload)
  │     │     └── ODrive latches a fault — requires CLEAR_ERRORS to recover
  │     ├── Mark all axes: axis_ready = false
  │     └── Log ERROR "E-STOP ACTIVATED"
  │
  └── CLEAR (data < 0.5):
        ├── Set e_stopped_ = false
        ├── Axes remain IDLE (no automatic re-arm)
        ├── Next velocity command triggers reinit_axis():
        │     1. CLEAR_ERRORS (cmd 0x18) — clears estop fault
        │     2. SET_CONTROLLER_MODE(VELOCITY_CONTROL, VEL_RAMP)
        │     3. SET_AXIS_STATE(CLOSED_LOOP_CONTROL)
        │     4. Wait up to 5s for confirmation
        └── Log INFO "E-STOP CLEARED — axes require re-enable"
```

**Design rationale:** Float64 topic (not service) is used because ROS2 services are request-response and cannot broadcast to multiple subscribers. The vehicle_control_node bridges the gap between its SetBool service and the ODrive node's topic subscriber.

### 2.8 CAN RX Thread

A dedicated thread (`can_rx_thread()`) runs continuously, receiving CAN frames and updating state:

| CMD ID | Name | Decoded Data | Action |
|--------|------|-------------|--------|
| `0x01` | `HEARTBEAT` | axis_state, axis_error, procedure_result | Update heartbeat state, manage axis_ready flag |
| `0x03` | `GET_ERROR` | active_errors, disarm_reason | Store error status |
| `0x09` | `GET_ENCODER_ESTIMATES` | pos_estimate (turns), vel_estimate (turns/s) | Store encoder data for JointState publishing |

### 2.9 Encoder Request

A periodic timer at `encoder_request_rate` (50 Hz) sends RTR (Remote Transmission Request) frames to each axis:
```
arb_id = (node_id << 5) | 0x09   (GET_ENCODER_ESTIMATES)
payload = empty, RTR flag set
```

The ODrive responds with encoder position and velocity, which the RX thread decodes.

### 2.10 Thread Safety

- All state access protected by `state_mutex_` (`std::mutex`)
- Velocity command handler uses `std::unique_lock` (not `lock_guard`) because `reinit_axis()` is a blocking call that must release the lock
- CAN RX thread uses `std::lock_guard` for state updates
- Watchdog timer uses `std::lock_guard`

---

## 3. CAN Bus Coexistence with MG6010

### 3.1 MG6010 Frame Filter

In `mg6010_can_interface.cpp:184-189`:
```cpp
uint32_t arb_id = frame.can_id & CAN_EFF_MASK;
if (arb_id < 0x140 || arb_id > 0x240) {
    return false;  // silently discard non-MG6010 frame
}
```

This silently drops all ODrive frames (range `0x000-0x05F`) without logging errors or warnings. Before this filter was added, ODrive heartbeat frames would reach the MG6010 protocol parser and cause spurious error logs.

### 3.2 ODrive Kernel Filter

In `socketcan_interface.cpp`, the socket is configured with `setsockopt(SO_CAN_FILTER)`:
```
mask = 0x7E0  (bits 5-10)
match = node_id << 5
```

This means the kernel only delivers frames whose bits 5-10 match the configured node_id, filtering at the OS level before the frame reaches userspace.

---

## 4. Launch Architecture

### 4.1 Startup Timing

`vehicle_complete.launch.py` sequences the nodes:

```
t=0.0s   Launch starts, cleanup_previous_instances() runs
t=0.3s   MG6010 steering controller starts (TimerAction)
t=0.5s   ODrive drive controller starts (TimerAction)
t=1.5s   ODrive velocity_mode_init() fires (internal 1s timer)
t=5.0s   Vehicle MQTT bridge starts (TimerAction)
t=25.0s  Vehicle control node starts (OpaqueFunction + configurable delay)
```

The 25s delay for `vehicle_control_node` allows both motor controllers to complete initialization before the state machine begins issuing commands.

### 4.2 Process Cleanup

`cleanup_previous_instances()` kills old processes by pattern before launching:
```python
long_processes = [
    'lib/vehicle_control/vehicle_control_node',
    'lib/motor_control_ros2/mg6010_controller_node',
    'lib/odrive_control_ros2/odrive_service_node',
]
```

### 4.3 Launch Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `can_interface` | `can0` | CAN bus interface name (forwarded to both motor controllers) |
| `use_sim_time` | `false` | Use simulation clock |
| `vehicle_control_delay` | `25.0` | Seconds to delay vehicle_control_node startup |
| `enable_vehicle_mqtt_bridge` | `true` | Enable/disable MQTT bridge |
| `output_log` | `screen` | Log output target |

---

## 5. Emergency Motor Stop Script

`emergency_motor_stop.sh` performs a 5-step shutdown sequence:

1. **Stop ROS2 processes** — `pkill -INT` for launch, mg6010, odrive
2. **Service-level IDLE** — Call `/joint_idle` for arm joints (if available)
3. **Topic-level stop** — Publish zero to position controller topics
4. **Hardware CAN stop** — Direct CAN frames:
   - MG6010: `cansend can0 ${id}#8000000000000000` (Motor OFF, IDs 0x141-0x144)
   - ODrive: `cansend can0 ${id}#` (ESTOP, empty payload, IDs 0x002, 0x022, 0x042)
5. **Force kill** — `pkill -9` remaining processes, stop ROS2 daemon

ODrive ESTOP CAN IDs:
```
Node 0: (0 << 5) | 0x02 = 0x002
Node 1: (1 << 5) | 0x02 = 0x022
Node 2: (2 << 5) | 0x02 = 0x042
```

---

## 6. Build System

### 6.1 Package Structure

```
src/odrive_control_ros2/
├── CMakeLists.txt          # Builds odrive_service_node, installs config/
├── package.xml             # Depends on: rclcpp, sensor_msgs, std_msgs, motor_control_ros2
├── config/
│   ├── production.yaml     # Position mode (arm joints)
│   └── vehicle_drive.yaml  # Velocity mode (drive wheels)
├── include/odrive_control_ros2/
│   ├── odrive_cansimple_protocol.hpp   # CAN protocol constants/encoders/decoders
│   └── socketcan_interface.hpp         # SocketCAN wrapper
└── src/
    ├── odrive_service_node.cpp         # Main ROS2 node (~1100 lines)
    └── socketcan_interface.cpp         # CAN socket with kernel filters
```

### 6.2 Build Modes

In `build.sh`, the `vehicle` build mode includes `odrive_control_ros2`:
```bash
# Vehicle packages (RPi vehicle controller)
colcon build --packages-select motor_control_ros2 vehicle_control odrive_control_ros2
```

The `rpi` build mode also includes it for Raspberry Pi deployment.

### 6.3 Sync & Deploy

`sync.sh` syncs the entire `src/` directory to the RPi, so `odrive_control_ros2` is included automatically without any changes needed.

---

## 7. Configuration Split

Drive motors were **removed from MG6010 config** (`vehicle_motors.yaml`) and placed in the new ODrive config (`vehicle_drive.yaml`):

**Before (MG6010 managed all 6 motors):**
```yaml
joint_names: [steer_front, steer_left_back, steer_right_back,
              drive_front, drive_left_back, drive_right_back]
```

**After (MG6010 manages 3 steering only):**
```yaml
# vehicle_motors.yaml (MG6010)
joint_names: [steer_front, steer_left_back, steer_right_back]

# vehicle_drive.yaml (ODrive)
joint_names: [drive_front, drive_left_back, drive_right_back]
```

---

## 8. Deployment Blockers

Before deploying to hardware, the following **must** be updated:

### 8.1 Transmission Factors

In `vehicle_drive.yaml`:
```yaml
# DEPLOYMENT BLOCKER: Must update after confirming ODrive gearbox spec.
# Incorrect values will cause wrong wheel speeds.
transmission_factors: [1.0, 1.0, 1.0]
```

This converts joint velocity units to ODrive motor turns/s. The correct value depends on the gearbox reduction ratio of the ODrive Pro + gearbox assembly. For reference, the previous MG6012-i36 value was `17.5386`.

### 8.2 Drive Motor Gear Ratio

In `constants.py`:
```python
GEAR_RATIOS.DRIVE_MOTOR = 1.0  # placeholder
```

This is used by the vehicle_control_node for kinematics calculations. Must match the actual ODrive gearbox spec.

### 8.3 ODrive Hardware Configuration

Tasks 9.1-9.6 in the OpenSpec change require physical access to ODrive controllers:
- Set CAN node IDs (0, 1, 2) via `odrivetool`
- Configure CAN baud rate to 500 kbps
- Set velocity limits, acceleration ramps, and PID gains
- Save configuration to NVM
- Verify heartbeat reception on `can0`

---

## 9. Troubleshooting

### ODrive node starts but axes don't initialize
- Check `candump can0` for heartbeat frames (cmd_id 0x01)
- If no heartbeats: verify ODrive CAN wiring, node IDs, baud rate
- If heartbeats show errors: check `axis_error` field, use `odrivetool` to diagnose
- The node logs CAN bus state at startup — look for "BUS-OFF" or "ERROR-PASSIVE"

### Velocity commands rejected
- Log says "e-stop active": clear e-stop via `/vehicle/emergency_stop` service with `data: false`
- Log says "axis not ready": axis dropped out of CLOSED_LOOP_CONTROL. Check ODrive for errors. The next command will trigger automatic re-init.

### MG6010 logging ODrive frame errors
- Should not happen after the CAN filter was added
- Verify `mg6010_can_interface.cpp` has the `0x140-0x240` range check

### Watchdog keeps triggering
- Ensure vehicle_control_node is publishing velocity commands at >2 Hz (watchdog timeout is 500ms)
- Check if vehicle_control_node has started (25s delay after launch)
- Set `watchdog_timeout: 0.0` in `vehicle_drive.yaml` to temporarily disable

### E-stop doesn't reach ODrive node
- Verify `/vehicle/emergency_stop_cmd` topic exists: `ros2 topic list | grep emergency`
- Check subscriber: `ros2 topic info /vehicle/emergency_stop_cmd`
- Verify vehicle_control_node has the `estop_cmd_pub` publisher (added in this integration)

---

## 10. Key Source Files Reference

| File | Lines | Role |
|------|-------|------|
| `src/odrive_control_ros2/src/odrive_service_node.cpp` | ~1100 | Main ODrive ROS2 node (velocity + position modes) |
| `src/odrive_control_ros2/src/socketcan_interface.cpp` | ~213 | CAN socket with kernel-level RX filtering |
| `src/odrive_control_ros2/include/.../odrive_cansimple_protocol.hpp` | ~393 | CAN protocol: 28 command IDs, encode/decode functions |
| `src/odrive_control_ros2/config/vehicle_drive.yaml` | 74 | Vehicle drive configuration (velocity mode) |
| `src/motor_control_ros2/src/mg6010_can_interface.cpp` | ~200 | MG6010 CAN interface with ODrive frame filter |
| `src/vehicle_control/launch/vehicle_complete.launch.py` | 321 | Launch: both controllers + vehicle node + MQTT |
| `src/vehicle_control/integration/vehicle_control_node.py` | ~2200 | Vehicle state machine, e-stop bridge publisher |
| `src/vehicle_control/config/constants.py` | - | GEAR_RATIOS.DRIVE_MOTOR (placeholder 1.0) |
| `emergency_motor_stop.sh` | 185 | Hardware-level shutdown for MG6010 + ODrive |
| `scripts/launch/launcher.sh` | 39 | CAN bus setup + ROS2 launch |
| `build.sh` | - | Build system (includes odrive_control_ros2 in vehicle mode) |
