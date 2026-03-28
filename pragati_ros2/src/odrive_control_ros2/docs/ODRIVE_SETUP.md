# ODrive Pro Setup Guide for CANSimple

This guide covers the initial setup of ODrive Pro motors for use with the `odrive_control_ros2` package.

## Prerequisites

- ODrive Pro with firmware 0.6.x installed
- USB connection to ODrive
- Python 3 with odrivetool installed: `pip install odrive`

## 1. Initial Configuration via USB

### Connect to ODrive
```bash
odrivetool
```

You should see output like:
```
Connected to ODrive ... as odrv0
```

### Set CAN Node ID

Each ODrive on the CAN bus needs a unique node ID (0-63):

```python
# For the first ODrive (joint3)
odrv0.can.config.node_id = 0

# For the second ODrive (joint4)
odrv0.can.config.node_id = 1

# For the third ODrive (joint5)
odrv0.can.config.node_id = 2
```

### Enable CANSimple Protocol

```python
# Set CAN baud rate to 500 kbps
odrv0.can.config.baud_rate = 500000

# Save configuration
odrv0.save_configuration()
odrv0.reboot()
```

Reconnect after reboot:
```bash
odrivetool
```

## 2. Motor Calibration

### Run Full Calibration
```python
# Put motor in calibration mode
odrv0.axis0.requested_state = AXIS_STATE_FULL_CALIBRATION_SEQUENCE

# Wait for calibration to complete
# Motor will spin and make sounds - this is normal
```

Check for errors:
```python
dump_errors(odrv0)
```

If calibration succeeded:
```python
# Skip calibration on startup (since we'll save the calibration)
odrv0.axis0.config.startup_encoder_offset_calibration = False
odrv0.axis0.config.startup_motor_calibration = False

# Pre-calibrated flag
odrv0.axis0.motor.config.pre_calibrated = True
odrv0.axis0.encoder.config.pre_calibrated = True
```

## 3. Configure PID Gains

Tune these values based on your motor and load characteristics:

```python
# Position control gains
odrv0.axis0.controller.config.pos_gain = 20.0

# Velocity control gains
odrv0.axis0.controller.config.vel_gain = 0.16
odrv0.axis0.controller.config.vel_integrator_gain = 0.32

# Anti-cogging (optional, for smooth motion)
odrv0.axis0.controller.config.enable_anticogging = False
```

### Tuning Tips:
- Start with low gains and increase gradually
- If motor oscillates, reduce `pos_gain`
- If response is sluggish, increase `vel_gain`
- For position tracking, tune `pos_gain` higher

## 4. Configure Trajectory Limits

These limits are used when `input_mode = TRAP_TRAJ`:

```python
# Velocity limit (turns/s)
odrv0.axis0.trap_traj.config.vel_limit = 2.0

# Acceleration limit (turns/s²)
odrv0.axis0.trap_traj.config.accel_limit = 5.0

# Deceleration limit (turns/s²)
odrv0.axis0.trap_traj.config.decel_limit = 5.0
```

### Recommended Values by Joint Type:

**Revolute Joints (joint3):**
```python
odrv0.axis0.trap_traj.config.vel_limit = 2.0      # 2 turns/s
odrv0.axis0.trap_traj.config.accel_limit = 5.0    # 5 turns/s²
odrv0.axis0.trap_traj.config.decel_limit = 5.0
```

**Prismatic Joints (joint4, joint5):**
```python
odrv0.axis0.trap_traj.config.vel_limit = 1.0      # ~0.08 m/s (if 12.74 turns/m)
odrv0.axis0.trap_traj.config.accel_limit = 3.0    # ~0.24 m/s²
odrv0.axis0.trap_traj.config.decel_limit = 3.0
```

## 5. Configure Control Mode

Set the default control mode to position control:

```python
# Control mode: POSITION_CONTROL
odrv0.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL

# Input mode: TRAP_TRAJ (trapezoidal trajectory planner)
odrv0.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ
```

## 6. Set Motor Limits

Configure current and velocity limits for safety:

```python
# Current limit (Amperes) - adjust based on your motor
odrv0.axis0.motor.config.current_lim = 15.0

# Velocity limit (turns/s) - max speed the motor can reach
odrv0.axis0.controller.config.vel_limit = 5.0
```

## 7. Save Configuration

**IMPORTANT:** Save configuration to non-volatile memory so settings persist after reboot:

```python
odrv0.save_configuration()
```

Verify settings were saved:
```python
odrv0.reboot()
# Reconnect with odrivetool
# Check that node_id, gains, and limits are still set
odrv0.can.config.node_id  # Should show your configured value
```

## 8. Verify CAN Communication

### From Linux (before starting ROS2 node):

```bash
# Bring up CAN interface
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Monitor CAN traffic
candump can0

# You should see heartbeat messages from the ODrive (every 100ms)
# Format: can0  0XX   [8]  ...
# Where XX = (node_id << 5) | 0x01
```

For node_id=0, heartbeat CAN ID = 0x01
For node_id=1, heartbeat CAN ID = 0x21
For node_id=2, heartbeat CAN ID = 0x41

## Example: Complete Setup Script

Save this as `setup_odrive.py`:

```python
#!/usr/bin/env python3
import odrive
from odrive.enums import *
import time

print("Connecting to ODrive...")
odrv0 = odrive.find_any()

print("Configuring ODrive...")

# CAN settings
odrv0.can.config.node_id = 0  # Change for each ODrive
odrv0.can.config.baud_rate = 500000

# Motor calibration (run once, then set pre_calibrated=True)
# odrv0.axis0.requested_state = AXIS_STATE_FULL_CALIBRATION_SEQUENCE
# time.sleep(15)  # Wait for calibration

# Skip calibration on startup (after first calibration)
odrv0.axis0.config.startup_encoder_offset_calibration = False
odrv0.axis0.config.startup_motor_calibration = False
odrv0.axis0.motor.config.pre_calibrated = True
odrv0.axis0.encoder.config.pre_calibrated = True

# PID gains
odrv0.axis0.controller.config.pos_gain = 20.0
odrv0.axis0.controller.config.vel_gain = 0.16
odrv0.axis0.controller.config.vel_integrator_gain = 0.32

# Trajectory limits
odrv0.axis0.trap_traj.config.vel_limit = 2.0
odrv0.axis0.trap_traj.config.accel_limit = 5.0
odrv0.axis0.trap_traj.config.decel_limit = 5.0

# Control mode
odrv0.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
odrv0.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ

# Motor limits
odrv0.axis0.motor.config.current_lim = 15.0
odrv0.axis0.controller.config.vel_limit = 5.0

# Save and reboot
print("Saving configuration...")
odrv0.save_configuration()
print("Rebooting ODrive...")
odrv0.reboot()

print("Done! ODrive configured for CAN node ID 0")
```

Run with:
```bash
python3 setup_odrive.py
```

## Troubleshooting

### Motor Vibrates or Makes Noise
- Reduce `pos_gain` and `vel_gain`
- Check mechanical coupling for backlash
- Verify encoder is securely mounted

### Position Tracking Error
- Increase `pos_gain`
- Increase trajectory `vel_limit` and `accel_limit`
- Check that load isn't exceeding `current_lim`

### CAN Communication Fails
- Verify `node_id` is unique (0-63)
- Check CAN bus termination (120Ω resistors at both ends)
- Verify baud rate matches (500 kbps)
- Check wiring: CAN_H, CAN_L, GND

### Configuration Not Saved
- Always call `odrv0.save_configuration()` after changes
- Wait for save to complete before rebooting
- Check for errors: `dump_errors(odrv0)`

## Reference

For more details on ODrive configuration:
- ODrive Documentation: https://docs.odriverobotics.com/
- CANSimple Protocol: https://docs.odriverobotics.com/v/latest/can-protocol.html
- Tuning Guide: https://docs.odriverobotics.com/v/latest/control.html
