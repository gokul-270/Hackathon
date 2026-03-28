# PID Tuning Visualization Guide

## Overview

Real-time visualization tool for tuning PID parameters on MG6010 motors. Displays step response, error, velocity, control output, and calculates performance metrics automatically.

> **Note:** In the web dashboard, the PID tuning page is now part of the **Motor Config**
> section (sidebar: "Motor Config"). The charts panel is shared below all Motor Config tabs,
> not just the PID tab. See [Motor Tuning Guide](MOTOR_TUNING_GUIDE.md) for the full Motor
> Config tab overview.

## Features

✨ **Real-time Plots:**
- Step response (setpoint vs actual position)
- Position error over time
- Velocity profile
- Control output/effort

📊 **Performance Metrics:**
- Rise time (10% → 90%)
- Settling time (2% criterion)
- Overshoot percentage
- Steady-state error
- Integral metrics (IAE, ISE, ITSE)
- Total control effort

💾 **Data Export:**
- Save all data to JSON
- CSV export from web dashboard charts
- Timestamped exports
- Multiple motor support

📸 **Snapshot & Overlay:**
- Capture chart snapshots at any point
- Overlay multiple snapshots for comparison
- Current mode toggle (torque vs phase currents)
- Configurable time window (10s/30s/60s/120s)

## Quick Start

### 1. Start the Motor System

```bash
# Terminal 1: Launch motor control
ros2 launch motor_control_ros2 mg6010_controller.launch.py
```

### 2. Run the Visualizer

```bash
# Terminal 2: Monitor single motor
cd ~/Downloads/pragati_ros2
python3 scripts/testing/motor/pid_tuning_visualizer.py --motor-id 2

# OR monitor all motors
python3 scripts/testing/motor/pid_tuning_visualizer.py --all-motors
```

### 3. Send Test Commands

```bash
# Terminal 3: Send position commands to test step response
ros2 topic pub /joint_command std_msgs/msg/Float64MultiArray \
  "data: [0.0, 1.0, 0.0, 0.0, 0.0]" --once

# Wait for settling, then change position
ros2 topic pub /joint_command std_msgs/msg/Float64MultiArray \
  "data: [0.0, 2.0, 0.0, 0.0, 0.0]" --once
```

## Usage Examples

### Monitor Specific Motor

```bash
# Monitor motor 2 for 30 seconds
python3 scripts/testing/motor/pid_tuning_visualizer.py \
  --motor-id 2 \
  --duration 30

# Monitor motor 3 and export data
python3 scripts/testing/motor/pid_tuning_visualizer.py \
  --motor-id 3 \
  --export tuning_data_motor3.json
```

### Monitor All Motors

```bash
# Opens 4 separate windows (motors 2-5)
python3 scripts/testing/motor/pid_tuning_visualizer.py \
  --all-motors \
  --export complete_tuning_session.json
```

## Understanding the Plots

### 1. Step Response (Top)
- **Red dashed line:** Setpoint (command)
- **Blue solid line:** Actual position
- **Good tuning:** Position tracks setpoint smoothly without oscillation

### 2. Position Error (Middle Left)
- Shows difference between setpoint and actual position
- Should converge to near-zero
- Oscillations indicate too much gain

### 3. Velocity (Middle Right)
- Motor velocity during movement
- Smooth curves indicate good tuning
- Spikes/oscillations suggest instability

### 4. Control Output (Bottom Left)
- Motor control effort (torque/current)
- Excessive oscillation indicates aggressive tuning
- Should be smooth and reasonable

### 5. Performance Metrics (Bottom Right)
Real-time calculated metrics:
- **Rise Time:** Speed of response
- **Settling Time:** Time to reach stability
- **Overshoot:** How much it exceeds target
- **SS Error:** Final position accuracy

## PID Tuning Workflow

### Step 1: Start Conservative
```bash
# Set conservative PID values (note: angle_kp replaces position_kp, etc.)
ros2 service call /motor_control/write_pid_ram motor_control_ros2/srv/WritePID \
  "{motor_id: 2, angle_kp: 10.0, angle_ki: 0.0, position_kd: 0.0}"

# Start visualizer
python3 scripts/testing/motor/pid_tuning_visualizer.py --motor-id 2
```

### Step 2: Increase Kp
- Increase Kp gradually (10 → 15 → 20 → 30)
- Watch for oscillations in error plot
- Stop when response is fast but stable

```bash
# Example: Try Kp=20
ros2 service call /motor_control/write_pid_ram motor_control_ros2/srv/WritePID \
  "{motor_id: 2, angle_kp: 20.0, angle_ki: 0.0, position_kd: 0.0}"
```

### Step 3: Add Ki
- Add small Ki to eliminate steady-state error
- Start with Kp/10
- Watch for integral windup

```bash
ros2 service call /motor_control/write_pid_ram motor_control_ros2/srv/WritePID \
  "{motor_id: 2, angle_kp: 20.0, angle_ki: 2.0, position_kd: 0.0}"
```

### Step 4: Add Kd (if needed)
- Add Kd to reduce overshoot
- Start with Kp/8
- May cause noise amplification

```bash
ros2 service call /motor_control/write_pid_ram motor_control_ros2/srv/WritePID \
  "{motor_id: 2, angle_kp: 20.0, angle_ki: 2.0, position_kd: 2.5}"
```

### Step 5: Save Good Values
```bash
# Once satisfied, save to ROM
ros2 service call /motor_control/write_pid_rom motor_control_ros2/srv/WritePID \
  "{motor_id: 2, angle_kp: 20.0, angle_ki: 2.0, position_kd: 2.5}"
```

## Interpreting Metrics

### Good Tuning Targets
| Metric | Target | Notes |
|--------|--------|-------|
| Rise Time | < 0.5s | Fast response |
| Settling Time | < 1.0s | Quick stabilization |
| Overshoot | < 10% | Minimal overshoot |
| SS Error | < 0.01 rad | Good accuracy |
| IAE | Minimal | Low cumulative error |

### Common Issues

**High Overshoot (>20%)**
- **Cause:** Kp too high
- **Solution:** Reduce Kp by 20-30%, add Kd

**Oscillations in Error Plot**
- **Cause:** Kp or Ki too aggressive
- **Solution:** Reduce gains incrementally

**Slow Response (Rise time >1s)**
- **Cause:** Kp too low
- **Solution:** Increase Kp gradually

**Large Steady-State Error**
- **Cause:** No Ki term, or Ki too small
- **Solution:** Add or increase Ki

**Control Output Chattering**
- **Cause:** Kd amplifying noise
- **Solution:** Reduce Kd or add filtering

## Data Export Format

Exported JSON contains:
```json
{
  "motor_2": {
    "time": [0.0, 0.01, 0.02, ...],
    "setpoint": [0.0, 0.0, 1.0, ...],
    "position": [0.0, 0.05, 0.15, ...],
    "velocity": [0.0, 5.0, 8.0, ...],
    "error": [0.0, -0.05, -0.15, ...],
    "control_output": [0.0, 10.0, 15.0, ...],
    "metrics": {
      "rise_time": 0.234,
      "settling_time": 0.891,
      "overshoot_percent": 8.5,
      "steady_state_error": 0.0023,
      "iae": 0.145,
      "ise": 0.034
    }
  }
}
```

## Advanced Features

### Compare Multiple Tuning Attempts
```bash
# Session 1: Conservative tuning
python3 scripts/testing/motor/pid_tuning_visualizer.py \
  --motor-id 2 --export attempt1.json

# Session 2: Aggressive tuning
python3 scripts/testing/motor/pid_tuning_visualizer.py \
  --motor-id 2 --export attempt2.json

# Compare metrics in exported files
```

### Custom Duration
```bash
# Monitor for 2 minutes
python3 scripts/testing/motor/pid_tuning_visualizer.py \
  --motor-id 2 --duration 120
```

## Troubleshooting

**No data showing:**
- Check motor is running: `ros2 topic echo /joint_states`
- Verify motor ID is correct
- Ensure motor is homed: `ros2 service call /joint_homing ...`

**Plots not updating:**
- Matplotlib backend issue
- Try: `export MPLBACKEND=TkAgg` before running

**High CPU usage:**
- Reduce update interval in code (line 383)
- Monitor fewer motors

**Missing matplotlib:**
```bash
pip3 install matplotlib numpy
```

## Integration with Tuning Guide

This tool complements the [Motor Tuning Guide](MOTOR_TUNING_GUIDE.md):
1. Follow tuning guide procedures
2. Use this visualizer to see real-time effects
3. Export data for documentation
4. Compare before/after tuning

## Tips for Best Results

1. **Start with small step commands** (0.5-1.0 rad)
2. **Wait for full settling** before next command
3. **Monitor temperature** during extended tuning
4. **Save good parameters immediately**
5. **Test under load** conditions when possible
6. **Export data** for future reference

## Web Dashboard Visualization (Primary)

The charts panel in the web dashboard (`http://<robot-ip>:8080`, **Motor Config** section)
provides real-time visualization. The charts are displayed as a **shared panel below all
Motor Config tabs** — they remain visible whether you are on the PID, Commands, Limits,
Encoder, or State tab.

- Rolling position/velocity/current charts via WebSocket (`/api/motor/ws/state`)
- Step response plots (setpoint vs actual, error, velocity, current)
- Performance metrics with pass/fail color coding
- **Snapshot capture/overlay** for comparing multiple step test results
- **CSV export** of chart data
- **Current mode toggle** — switch between torque current and phase currents (A/B/C)
- **Time window selector** — 10s, 30s, 60s, or 120s rolling window
- Zoom/pan via chartjs-plugin-zoom

> The old WebSocket endpoint `/api/pid/ws/motor_state` still works for backward
> compatibility. New integrations should use `/api/motor/ws/state`.

This is the recommended tool for interactive PID tuning sessions.

## Matplotlib Tool (Alternative)

The standalone matplotlib-based visualization script remains available for:
- Offline analysis of saved step response data
- Custom plotting configurations
- Headless (SSH) environments where a browser is not available

## See Also

- [Motor Tuning Guide](MOTOR_TUNING_GUIDE.md) - Manual tuning procedures
- [Three Motor Setup Guide](THREE_MOTOR_SETUP_GUIDE.md) - Multi-motor configuration
- [Hardware Testing Quickstart](hardware/HARDWARE_TESTING_QUICKSTART.md) - Hardware setup

---
**Created:** 2025-11-04 | **Updated:** 2026-03-06
**Tool Location:** `scripts/testing/motor/pid_tuning_visualizer.py`
