# Motor Tuning Guide

## Quick Reference
- **Start Conservative:** Kp=10, Ki=5, Kd=0
- **Tune Position Loop First:** Then velocity, then torque
- **Test Incrementally:** Small changes, test after each
- **Monitor Temperature:** Stop if motor exceeds 70°C

## PID Parameter Ranges (MG6010)
| Parameter | Range | Default | Notes |
|-----------|-------|---------|-------|
| Angle Kp | 0-255 | 30 | Primary position gain |
| Angle Ki | 0-255 | 10 | Reduces steady-state error |
| Velocity Kp | 0-255 | 25 | Speed control responsiveness |
| Velocity Ki | 0-255 | 8 | Speed steady-state |
| Current Kp | 0-255 | 20 | Current loop control |
| Current Ki | 0-255 | 5 | Current loop accuracy |

> **Field name change:** `position_kp`/`position_ki` have been renamed to `angle_kp`/`angle_ki`,
> and `torque_kp`/`torque_ki` to `current_kp`/`current_ki`. The old names are still accepted
> by the API for backward compatibility.

## Tuning Procedure

### 1. Calibration (Required First)
```bash
# Calibrate encoder
ros2 service call /motor_control/calibrate_encoder motor_control_ros2/srv/EncoderCalibration "{motor_id: 1}"

# Home motor
ros2 service call /joint_homing motor_control_ros2/srv/JointHoming "{joint_id: 1}"
```

### 2. Position Tuning
```bash
# Read current PID
ros2 service call /motor_control/read_pid motor_control_ros2/srv/ReadPID "{motor_id: 1}"

# Start conservative
# Set Kp=10, observe response
# If underdamped (oscillates): decrease Kp
# If overdamped (sluggish): increase Kp
# Add Ki=5 to eliminate steady-state error

# Write PID to RAM (test)
ros2 service call /motor_control/write_pid_ram motor_control_ros2/srv/WritePID "{motor_id: 1, position_kp: 15, position_ki: 7, ...}"

# If stable, write to ROM (permanent)
ros2 service call /motor_control/write_pid_rom motor_control_ros2/srv/WritePID "{...}"
```

### 3. Common Issues

**Motor Oscillates**
- Decrease Kp by 20-30%
- Ensure mechanical system is rigid
- Check for loose couplings

**Slow Response**
- Increase Kp incrementally
- Check max_velocity limit isn't constraining
- Verify motor current limit is adequate

**Position Error**
- Add Ki term (start with Kp/2)
- Check encoder resolution
- Verify no mechanical backlash

**Unstable at Speed**
- Reduce velocity Kp
- Add acceleration limits
- Check EMI/noise on encoder

## Safety Limits
```yaml
# config/motor_config.yaml
motor_limits:
  max_velocity: 10.0  # rad/s
  max_acceleration: 5.0  # rad/s²
  max_current: 30.0  # Amps
  max_temperature: 75.0  # °C
```

## Diagnostic Commands
```bash
# Monitor motor status
ros2 topic echo /motor_status

# Check temperature
ros2 service call /motor_control/read_status motor_control_ros2/srv/ReadStatus "{motor_id: 1}"

# Clear errors
ros2 service call /motor_control/clear_errors motor_control_ros2/srv/ClearErrors "{motor_id: 1}"
```

## Advanced Tuning

### Feed-Forward
For faster tracking, add velocity feed-forward:
```yaml
velocity_ff: 0.1  # Start small, increase if tracking lag persists
```

### Acceleration Limits
```bash
ros2 service call /motor_control/set_acceleration motor_control_ros2/srv/SetAcceleration "{motor_id: 1, accel: 5.0}"
```

### Multi-Turn vs Single-Turn
- **Multi-turn:** For continuous rotation (base joint)
- **Single-turn:** For limited range joints (0-360°)

## Web Dashboard Motor Config (Recommended)

The web dashboard provides a comprehensive **Motor Config** interface accessible from any
browser on the same network as the robot. This replaces the previous "PID Tuning" section
with a full tabbed interface covering PID gains, motor commands, limits, encoder calibration,
and live state monitoring.

### Accessing Motor Config

1. Start the web dashboard: `ros2 launch web_dashboard dashboard.launch.py`
2. Open `http://<robot-ip>:8080` in a browser
3. Click **"Motor Config"** in the sidebar navigation

### Motor Config Tabs

#### PID Tab
Read/write PID gains with safety-limited sliders. Field names now use `angle_kp`/`angle_ki`
(position loop) and `current_kp`/`current_ki` (current loop). Step response testing,
auto-tune suggestions (Ziegler-Nichols), profile management, guided tuning wizard, and
oscillation detection are all available here.

#### Commands Tab
Send direct motor commands in 8 control modes: Torque, Speed, Multi-Angle (1 & 2),
Single-Angle (1 & 2), Increment (1 & 2). Includes lifecycle controls (Motor On/Off/Stop/
Reboot), a motor state badge (OFF/RUNNING/STOPPED/ERROR/UNKNOWN), command history
(last 20), and step increment buttons.

#### Limits Tab
Configure motor limits in RAM. Set max torque current (0-2000) and acceleration with a
dual-unit display (dps/s and rad/s²). Limits auto-load when a motor is selected.

#### Encoder Tab
Encoder calibration tools: read encoder values (raw, offset, original), set zero offset
to RAM with "Use Current Value" prefill, and save position as zero to ROM. Includes
before/after comparison display.

> **WARNING — ROM writes are permanent.** The "Save Position as Zero (ROM)" operation
> writes to non-volatile memory and cannot be undone without physical recalibration.
> A strong confirmation dialog is shown before any ROM write. A 30-second repeat-write
> guard and motion-check blocking prevent accidental writes.

#### State Tab
Live motor telemetry: power (voltage with 36-52V range bar, temperature with 70/80°C
thresholds), motion (speed, torque current, multi/single turn angles), phase currents
(A/B/C), and 8 error flags with indicators. Includes a "Clear Errors" button.

#### Charts (Shared Panel)
A shared charts panel is displayed below all tabs showing position, velocity, and current
charts. Features include snapshot capture/overlay, CSV export, current mode toggle (torque
vs phase), and a time window selector (10s/30s/60s/120s). See the
[PID Visualization Guide](PID_VISUALIZATION_GUIDE.md) for details.

### API Endpoints

Motor Config uses REST endpoints under `/api/motor/`:
- `POST /{motor_id}/command` — send motor commands
- `POST /{motor_id}/lifecycle` — motor on/off/stop/reboot
- `GET/PUT /{motor_id}/limits/...` — read/write limits
- `GET /{motor_id}/encoder` — read encoder values
- `POST /{motor_id}/encoder/zero` — set encoder zero
- `GET /{motor_id}/angles` — read angle values
- `GET /{motor_id}/state` — read motor state
- `POST /{motor_id}/errors/clear` — clear error flags
- `GET /validation_ranges` — get valid parameter ranges

WebSocket: `/api/motor/ws/state` (the old `/api/pid/ws/motor_state` endpoint still works).

PID endpoints at `/api/pid/*` continue to work with both old and new field names.

### Quick PID Tuning Workflow

1. Select a motor from the dropdown
2. Go to the **PID** tab and click "Read PID" to load current gains
3. Run a step response test (default: 10 degrees, 5 seconds)
4. Click "Auto-Suggest Gains" to get Ziegler-Nichols recommendations
5. Apply suggested gains to RAM and run another step test to verify
6. Check the **Charts** panel below to evaluate the response
7. When satisfied, save to ROM and save a profile

## Troubleshooting Matrix

| Symptom | Probable Cause | Solution |
|---------|----------------|----------|
| Oscillation | Kp too high | Reduce Kp 20% |
| Slow settling | Ki too low | Increase Ki |
| Overshoot | Kp too high, no Kd | Add Kd=Kp/8 |
| Steady-state error | Ki too low | Increase Ki |
| Chattering | Current loop unstable | Reduce current Kp |
| Motor heating | Excessive current | Lower max_current |
| CAN errors | Baud rate mismatch | Verify 500kbps |
| No response | Not homed | Call homing service |

**Last Updated:** 2026-03-06
