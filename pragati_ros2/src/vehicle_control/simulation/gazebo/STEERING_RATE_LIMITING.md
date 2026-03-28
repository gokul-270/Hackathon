# Steering Rate Limiting - Preventing Oscillation

## Problem: Oscillation and Jittering

When sudden steering commands are sent (e.g., target changes from 0° to 45° instantly), the Gazebo PID controller tries to reach the target as fast as possible, causing:
- **Oscillation** - wheel overshoots and bounces around target
- **Jittering** - rapid back-and-forth motion
- **Unrealistic behavior** - real vehicles can't steer infinitely fast

## Solution: Steering Rate Limiting

Added a **maximum steering angular velocity** to control how fast steering angles can change.

### How It Works

```
Target: 45° (0.785 rad)
Current: 0° (0 rad)
Max rate: 2.0 rad/s (~115°/s)
Update rate: 50 Hz (every 0.02s)

Iteration 1: 0° + (2.0 * 0.02) = 0° + 2.29° = 2.29°
Iteration 2: 2.29° + 2.29° = 4.58°
...
Iteration ~20: Reaches 45°
```

Instead of jumping to 45° instantly, the steering **smoothly ramps** to the target over ~0.4 seconds.

## Implementation

### 1. Unified Control Loop (50 Hz)
```python
self.timer = self.create_timer(1/50.0, self.control_loop)
```
Runs at fixed 50 Hz to publish **both steering angles and drive speeds** together. Previously, drive speeds were published immediately in `cmd_vel_callback` while steering was rate-limited separately — this caused timing mismatches. Now the control loop is the single publish point.

### 2. Rate Limiting Logic with Angle Wrapping
```python
error = math.atan2(math.sin(target - current), math.cos(target - current))
max_change = self.max_steering_rate * self.dt  # 2.0 rad/s * 0.02s = 0.04 rad
if abs(error) > max_change:
    change = max_change if error > 0 else -max_change
    new_angle = current + change
else:
    new_angle = target  # Directly reach if close
```

The `atan2(sin, cos)` wrapping ensures errors are always computed in the shortest angular direction, preventing the limiter from taking the long way around when angles cross ±π.

### 3. Unified Drive and Steering Publish
Both steering angles and drive speeds are published together in the control loop at 50 Hz. Drive speeds are published at full commanded speed — no progress-based scaling. Testing showed that scaling drive by steering progress made movement sluggish; the rate-limited steering is smooth enough on its own.

### 4. Zero-Velocity Behavior: Hold Last Angle
When velocity drops to zero, the steering angles **hold their last commanded position** instead of snapping to 0°. This prevents wheels from jerking back to center when the robot stops mid-turn.

## Parameters

Adjustable in [kinematics_node.py](../vehicle_control/kinematics_node.py):

```python
self.max_steering_rate = 2.0  # rad/s (~115°/s)
self.control_rate = 50.0      # Hz
```

### Tuning Guide

**max_steering_rate (rad/s)**:
- **Higher (e.g., 5.0)**: Faster response, but may still oscillate
- **Lower (e.g., 1.0)**: Smoother, but slower turns
- **Recommended**: 1.5 - 3.0 rad/s

**control_rate (Hz)**:
- **Higher (e.g., 100 Hz)**: Smoother interpolation, more CPU
- **Lower (e.g., 20 Hz)**: Less smooth, less CPU
- **Recommended**: 30 - 50 Hz

## Comparison

### Before (No Rate Limiting)
```
Time: 0.00s → Steering: 0°
Time: 0.02s → Steering: 45° ← INSTANT JUMP!
Result: PID controller oscillates trying to reach 45°
```

### After (With Rate Limiting)
```
Time: 0.00s → Steering: 0°
Time: 0.02s → Steering: 2.3°
Time: 0.04s → Steering: 4.6°
Time: 0.06s → Steering: 6.9°
...
Time: 0.40s → Steering: 45° ← SMOOTH RAMP!
Result: Smooth, stable steering motion
```

## Testing

Restart the kinematics node and test:

```bash
# Terminal 2
source ~/steering\ control/install/setup.bash
ros2 run vehicle_control kinematics_node.py
```

You should see:
```
[INFO] [vehicle_control_kinematics]: Control rate: 50.0 Hz
[INFO] [vehicle_control_kinematics]: Max steering rate: 114.6°/s
```

Try sharp turns - the steering should now be **smooth without oscillation**!

## Advanced: Adaptive Rate Limiting

For even better performance, you could make the rate adaptive:
- **Fast motions**: Higher rate limit
- **Slow motions**: Lower rate limit for precision
- **Near target**: Very low rate to avoid overshoot

```python
# Adaptive rate based on distance to target
if abs(error) > 0.5:  # Far from target
    rate = 3.0  # rad/s - fast
elif abs(error) > 0.1:  # Medium distance
    rate = 1.5  # rad/s - moderate
else:  # Very close
    rate = 0.5  # rad/s - slow and precise
```

This is left as an exercise for optimization!
