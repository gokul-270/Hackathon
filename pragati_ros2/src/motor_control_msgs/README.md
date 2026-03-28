# motor_control_msgs

ROS2 service and action definitions for the Pragati cotton-picking robot motor control system.

**18 services, 3 actions** across 6 functional areas.

## Motor Control

| Interface | Type | Description |
|-----------|------|-------------|
| `MotorCommand.srv` | Service | Send motor control commands (torque, speed, angle, increment modes) |
| `MotorLifecycle.srv` | Service | Motor lifecycle operations (on, off, stop, reboot, save to ROM) |
| `EmergencyStop.srv` | Service | Activate/deactivate emergency stop for all motors |
| `DriveStop.srv` | Service | Stop/resume drive motors, clearing queued commands |

## Encoder / Angle Reading

| Interface | Type | Description |
|-----------|------|-------------|
| `ReadEncoder.srv` | Service | Read raw encoder value, offset, and original value |
| `ReadMotorAngles.srv` | Service | Read multi-turn and single-turn angles (radians) |
| `WriteEncoderZero.srv` | Service | Set encoder zero position (specific value or current position) |

## PID Tuning

| Interface | Type | Description |
|-----------|------|-------------|
| `ReadPID.srv` | Service | Read PID parameters (angle, speed, current loops) |
| `WritePID.srv` | Service | Write PID parameters to RAM (volatile, lost on power cycle) |
| `WritePIDToROM.srv` | Service | Write PID parameters to ROM (persistent across power cycles) |
| `StepResponseTest.action` | Action | Execute step response test with time-series recording for PID analysis |

PID gain fields use the canonical names: `angle_kp`, `angle_ki`, `speed_kp`, `speed_ki`, `current_kp`, `current_ki`. All gains are `uint8` (0-255).

## Homing / Positioning

| Interface | Type | Description |
|-----------|------|-------------|
| `JointHoming.srv` | Service | Simple homing/idle trigger for a single joint |
| `JointHoming.action` | Action | Full homing sequence with progress feedback (preferred over srv) |
| `JointPositionCommand.srv` | Service | Move joint to target position with optional blocking wait |
| `JointPositionCommand.action` | Action | Move joint with continuous feedback and cancellation (preferred over srv) |
| `SetAxisState.srv` | Service | Set ODrive axis state (joint_id=-1 for all joints) |

## Diagnostics / State

| Interface | Type | Description |
|-----------|------|-------------|
| `ReadMotorState.srv` | Service | Read temperature, voltage, current, speed, encoder, phase currents, error flags |
| `JointStatus.srv` | Service | Get joint positions, velocities, efforts, temperatures (joint_id=-1 for all) |
| `ClearMotorErrors.srv` | Service | Clear motor error flags |

## Motor Limits

| Interface | Type | Description |
|-----------|------|-------------|
| `ReadMotorLimits.srv` | Service | Read max torque ratio and acceleration limits |
| `WriteMotorLimits.srv` | Service | Write torque/acceleration limits with per-field write flags |

## Design Notes

- **srv vs action pairs**: `JointHoming` and `JointPositionCommand` each exist as both service (synchronous) and action (async with feedback/cancellation). Prefer the action variants for new code.
- **RAM vs ROM writes**: PID parameters have separate `WritePID` (volatile) and `WritePIDToROM` (persistent) services.
- **Broadcast addressing**: `JointStatus` and `SetAxisState` accept `joint_id = -1` to target all joints.
