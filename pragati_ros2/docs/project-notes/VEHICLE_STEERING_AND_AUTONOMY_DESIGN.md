# Vehicle Steering Control and Autonomy Design

**Date:** January 28, 2026
**Status:** 🟡 Design Phase
**Owner:** Uday, Vasanth

---

## 1. Executive Summary

### Current State
- **Ackermann steering geometry:** ✅ Implemented (calculates correct wheel ANGLES)
- **Drive velocity control:** ❌ Same speed for all wheels (causes scrubbing)
- **Autonomy:** ❌ Not implemented (manual joystick only)

### Required Improvements
1. **Differential wheel velocities** for proper turning (ICR-based)
2. **Velocity-based kinematic model** (v, ω) instead of steering-only
3. **Autonomous navigation** sensors and software (Phase 4+)

---

## 2. Current Steering Implementation

### 2.1 Ackermann Geometry (Working)
**Location:** `src/vehicle_control/hardware/advanced_steering.py`

```python
# Current: Correctly computes ANGLES
def calculate_ackermann_angles(self, input_rotation):
    # ✅ Inside wheel angle (sharper)
    inside_wheel_angle = math.degrees(
        math.atan(wheelbase / abs(R - track_width/2))
    )
    # ✅ Outside wheel angle (gentler)
    outside_wheel_angle = math.degrees(
        math.atan(wheelbase / (R + track_width/2))
    )
```

### 2.2 Drive Velocity Problem (ISSUE)
**Location:** `src/vehicle_control/integration/vehicle_control_node.py`

```python
# Current: Same velocity to ALL drive wheels ❌
def _send_drive_velocity(self, velocity):
    wheel_rad_s = velocity_to_rad_s(velocity)
    
    # PROBLEM: All wheels get same speed!
    publish('/drive_front/command', wheel_rad_s)
    publish('/drive_left_back/command', wheel_rad_s)    # Should be different!
    publish('/drive_right_back/command', wheel_rad_s)   # Should be different!
```

### 2.3 The Problem Visualized

```
         CURRENT (WRONG)                    REQUIRED (CORRECT)
         
    All wheels: same speed                Inner: slower, Outer: faster
    
         ↑ v                                    ↑ v_outer
    ┌────┴────┐                           ┌────┴────┐
    │    L    │                           │    L    │
    │ ←─ ─ →  │  Wheels fight             │ ←─ ─ →  │  Smooth turn
    │    R    │  each other               │    R    │  around ICR
    └────┬────┘                           └────┬────┘
         ↑ v                                    ↑ v_inner
         
    Result: Wheel scrubbing,              Result: Accurate turning,
            poor accuracy                         no scrubbing
```

---

## 3. Proposed Solution: Velocity-Based Kinematic Model

### 3.1 Theory: Instantaneous Center of Rotation (ICR)

For a vehicle turning with steering angle θ:

```
                    ICR (Instantaneous Center of Rotation)
                      ●
                     /│\
                    / │ \
                   /  │  \
              R_in│  R│   │R_out
                   \  │  /
                    \ │ /
           ┌─────────┼─────────┐
           │    L    │    R    │ ← Rear wheels
           └─────────┴─────────┘
                  wheelbase
                     │
           ┌─────────┴─────────┐
           │       FRONT       │ ← Front wheel (steered)
           └───────────────────┘
                     θ
```

**Key Equations:**
```
R = wheelbase / tan(θ)              # Turn radius from steering angle

R_inner = R - track_width/2         # Inner wheel radius
R_outer = R + track_width/2         # Outer wheel radius

ω = v / R                           # Angular velocity around ICR

v_inner = ω × R_inner               # Inner wheel linear velocity
v_outer = ω × R_outer               # Outer wheel linear velocity
```

### 3.2 Implementation

**New function for `vehicle_control_node.py`:**

```python
def calculate_differential_velocities(
    self,
    linear_velocity: float,    # m/s
    steering_angle: float      # radians
) -> dict:
    """
    Calculate per-wheel velocities for proper ICR-based turning.
    
    Args:
        linear_velocity: Desired vehicle center velocity (m/s)
        steering_angle: Front wheel steering angle (radians)
    
    Returns:
        Dict with velocity for each drive wheel (rad/s)
    """
    # Vehicle geometry
    wheelbase = 1.5       # meters (1500mm)
    track_width = 1.8     # meters (1800mm)
    wheel_radius = 0.305  # meters (24" diameter / 2)
    
    # Handle straight driving
    if abs(steering_angle) < 0.01:  # ~0.5 degrees
        wheel_angular_vel = linear_velocity / wheel_radius
        return {
            'drive_front': wheel_angular_vel,
            'drive_left_back': wheel_angular_vel,
            'drive_right_back': wheel_angular_vel
        }
    
    # Calculate turn radius from steering angle
    R = wheelbase / math.tan(steering_angle)
    
    # Angular velocity of vehicle around ICR
    omega = linear_velocity / R
    
    # Radius for each rear wheel
    R_left = R - track_width / 2     # Negative R means left turn
    R_right = R + track_width / 2
    
    # Linear velocities for each wheel
    v_left = omega * R_left
    v_right = omega * R_right
    v_front = linear_velocity  # Front wheel at vehicle center velocity
    
    # Convert to angular velocity (rad/s)
    return {
        'drive_front': v_front / wheel_radius,
        'drive_left_back': v_left / wheel_radius,
        'drive_right_back': v_right / wheel_radius
    }
```

**Updated drive command function:**

```python
def _send_drive_velocity_differential(self, linear_cmd: float, steering_angle: float):
    """Send differential velocities to drive motors."""
    
    # Calculate per-wheel velocities
    velocities = self.calculate_differential_velocities(linear_cmd, steering_angle)
    
    # Publish to each motor
    self._publish_velocity('drive_front', velocities['drive_front'])
    self._publish_velocity('drive_left_back', velocities['drive_left_back'])
    self._publish_velocity('drive_right_back', velocities['drive_right_back'])
    
    self.logger.debug(
        f"Differential drive: L={velocities['drive_left_back']:.2f}, "
        f"R={velocities['drive_right_back']:.2f}, F={velocities['drive_front']:.2f} rad/s"
    )
```

### 3.3 Example Calculation

**Scenario:** Turn right at 1 m/s with 30° steering angle

```
Input:
  linear_velocity = 1.0 m/s
  steering_angle = 30° = 0.524 rad
  wheelbase = 1.5 m
  track_width = 1.8 m
  wheel_radius = 0.305 m

Calculation:
  R = 1.5 / tan(0.524) = 1.5 / 0.577 = 2.60 m
  omega = 1.0 / 2.60 = 0.385 rad/s

  R_left = 2.60 - 0.9 = 1.70 m    (inner wheel)
  R_right = 2.60 + 0.9 = 3.50 m   (outer wheel)

  v_left = 0.385 × 1.70 = 0.65 m/s
  v_right = 0.385 × 3.50 = 1.35 m/s

Result:
  Left wheel (inner): 0.65 m/s → 2.13 rad/s
  Right wheel (outer): 1.35 m/s → 4.43 rad/s
  Ratio: outer/inner = 2.08x
```

---

## 4. Three-Wheel Kinematics

Since the vehicle has **steering on all 3 wheels**, the kinematics are more complex.

### 4.1 Current Three-Wheel Ackermann
```python
# From advanced_steering.py
def calculate_three_wheel_ackermann_angles(self, input_rotation):
    # Rear left and right: Standard Ackermann
    angles = self.calculate_ackermann_angles(input_rotation)
    
    # Front wheel: Average of rear angles with opposite sign
    rear_wheel_angle = (abs(left_angle) + abs(right_angle)) / 2
    front_rotation = ±(rear_wheel_angle / 360) * GEAR_RATIO
```

### 4.2 Full Differential Drive for 3-Wheel

```python
def calculate_three_wheel_differential(
    self,
    linear_velocity: float,
    angular_velocity: float  # rad/s (positive = turn left)
) -> dict:
    """
    Full (v, ω) kinematic model for 3-wheel omnidirectional steering.
    
    Args:
        linear_velocity: Forward velocity (m/s)
        angular_velocity: Rotational velocity (rad/s)
    
    Returns:
        Dict with steering angles and velocities for all wheels
    """
    # If no rotation, go straight
    if abs(angular_velocity) < 0.001:
        wheel_vel = linear_velocity / self.wheel_radius
        return {
            'steering_left': 0.0,
            'steering_right': 0.0,
            'steering_front': 0.0,
            'drive_left': wheel_vel,
            'drive_right': wheel_vel,
            'drive_front': wheel_vel
        }
    
    # Calculate ICR from (v, omega)
    R = linear_velocity / angular_velocity  # Turn radius
    
    # Wheel positions relative to vehicle center
    # (assuming standard tricycle layout)
    rear_left_pos = (-self.track_width/2, -self.wheelbase/2)
    rear_right_pos = (self.track_width/2, -self.wheelbase/2)
    front_pos = (0, self.wheelbase/2)
    
    # Calculate for each wheel
    results = {}
    for name, (wx, wy) in [
        ('left', rear_left_pos),
        ('right', rear_right_pos),
        ('front', front_pos)
    ]:
        # Vector from ICR to wheel
        dx = wx - (-R if angular_velocity > 0 else R)  # ICR position
        dy = wy
        
        # Distance from ICR
        r_wheel = math.sqrt(dx*dx + dy*dy)
        
        # Wheel velocity (perpendicular to ICR vector)
        v_wheel = angular_velocity * r_wheel
        
        # Steering angle (tangent to turn circle)
        steering = math.atan2(dy, dx) + math.pi/2
        
        results[f'steering_{name}'] = steering
        results[f'drive_{name}'] = v_wheel / self.wheel_radius
    
    return results
```

---

## 5. Vehicle Autonomy Roadmap

### 5.1 Sensor Requirements (Phase 4+)

| Sensor | Purpose | Priority | Cost | Status |
|--------|---------|----------|------|--------|
| **RTK GPS** | ±2cm positioning | CRITICAL | $500-2000 | ⬜ Not purchased |
| **IMU** | Orientation, tilt | CRITICAL | $50-500 | ⬜ Not integrated |
| **Wheel Encoders** | Odometry | CRITICAL | $100-300 | ⬜ Check if available |
| **Navigation Camera** | Row following | CRITICAL | $200-1000 | ⬜ Separate from cotton cam |
| **Ultrasonic** | Obstacle detection | HIGH | $50-200 | ⬜ |
| **2D LiDAR** | Safety/mapping | MEDIUM | $300-1500 | ⬜ |

### 5.2 Software Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AUTONOMY STACK                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   RTK GPS    │  │     IMU      │  │   Encoders   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                  │
│                  ┌────────▼────────┐                        │
│                  │   LOCALIZATION  │                        │
│                  │  (EKF Fusion)   │                        │
│                  └────────┬────────┘                        │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐              │
│         │                 │                 │              │
│  ┌──────▼──────┐  ┌───────▼───────┐  ┌─────▼─────┐       │
│  │    PATH     │  │     ROW       │  │ OBSTACLE  │       │
│  │  PLANNING   │  │  FOLLOWING    │  │ AVOIDANCE │       │
│  └──────┬──────┘  └───────┬───────┘  └─────┬─────┘       │
│         │                 │                 │              │
│         └─────────────────┼─────────────────┘              │
│                           │                                  │
│                  ┌────────▼────────┐                        │
│                  │  MOTION CONTROL │                        │
│                  │   (v, ω) cmd    │                        │
│                  └────────┬────────┘                        │
│                           │                                  │
│                  ┌────────▼────────┐                        │
│                  │ DIFFERENTIAL    │                        │
│                  │ DRIVE CONTROL   │                        │
│                  └────────┬────────┘                        │
│                           │                                  │
│         ┌─────────────────┼─────────────────┐              │
│         │                 │                 │              │
│  ┌──────▼──────┐  ┌───────▼───────┐  ┌─────▼─────┐       │
│  │  STEERING   │  │    DRIVE      │  │  SAFETY   │       │
│  │   MOTORS    │  │   MOTORS      │  │  MONITOR  │       │
│  └─────────────┘  └───────────────┘  └───────────┘       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 ROS 2 Node Structure

```yaml
Nodes:
  /localization_node:
    subscribes:
      - /gps/fix (sensor_msgs/NavSatFix)
      - /imu/data (sensor_msgs/Imu)
      - /odom (nav_msgs/Odometry)
    publishes:
      - /localization/pose (geometry_msgs/PoseStamped)
      - /localization/odom (nav_msgs/Odometry)
  
  /path_planner_node:
    subscribes:
      - /localization/pose
      - /map (nav_msgs/OccupancyGrid)
    publishes:
      - /path (nav_msgs/Path)
  
  /row_follower_node:
    subscribes:
      - /nav_camera/image_raw
      - /localization/pose
    publishes:
      - /cmd_vel (geometry_msgs/Twist)
  
  /motion_controller_node:
    subscribes:
      - /cmd_vel (geometry_msgs/Twist)
    publishes:
      - /steering_*/command (std_msgs/Float64)
      - /drive_*/command (std_msgs/Float64)
```

---

## 6. Implementation Plan

### Phase 1: Differential Drive (Before Feb 25) 🎯
- [ ] Implement `calculate_differential_velocities()`
- [ ] Update `_send_drive_velocity()` to use differential
- [ ] Test in simulation
- [ ] Test with actual motors (when available)

### Phase 2: Sensor Integration (March 2026)
- [ ] Integrate IMU for orientation
- [ ] Add wheel encoder feedback
- [ ] Implement basic odometry

### Phase 3: RTK GPS (April 2026)
- [ ] Purchase RTK GPS module
- [ ] Set up base station
- [ ] Integrate GPS node
- [ ] Implement EKF sensor fusion

### Phase 4: Row Following (May 2026)
- [ ] Add navigation camera
- [ ] Implement row detection algorithm
- [ ] Test autonomous row following

### Phase 5: Full Autonomy (June 2026+)
- [ ] Path planning
- [ ] Obstacle avoidance
- [ ] Field mapping
- [ ] Coordinated arm/vehicle operation

---

## 7. Configuration Parameters

**Add to `src/vehicle_control/config/production.yaml`:**

```yaml
differential_drive:
  enabled: true
  wheelbase: 1.5          # meters
  track_width: 1.8        # meters
  wheel_radius: 0.305     # meters
  
  # Velocity limits
  max_linear_velocity: 2.0    # m/s
  max_angular_velocity: 0.5   # rad/s
  
  # Safety
  min_turn_radius: 2.0        # meters

autonomy:
  enabled: false              # Enable when sensors ready
  
  sensors:
    rtk_gps:
      enabled: false
      topic: "/gps/fix"
    imu:
      enabled: false
      topic: "/imu/data"
    wheel_encoders:
      enabled: false
      topic: "/wheel_odom"
```

---

## 8. Testing Checklist

### Unit Tests
- [ ] `test_differential_velocities_straight()` - All wheels same speed
- [ ] `test_differential_velocities_right_turn()` - Left > Right
- [ ] `test_differential_velocities_left_turn()` - Right > Left
- [ ] `test_differential_velocities_tight_turn()` - Large ratio difference

### Integration Tests
- [ ] Joystick → differential velocities → motors
- [ ] Ackermann angles + differential velocities synchronized
- [ ] E-stop works with differential mode

### Field Tests
- [ ] Turn in place (pivot mode)
- [ ] Circle driving (constant radius)
- [ ] Figure-8 pattern
- [ ] Row following (manual)

---

## 9. References

- Existing steering code: `src/vehicle_control/hardware/advanced_steering.py`
- Vehicle control node: `src/vehicle_control/integration/vehicle_control_node.py`
- Motor config: `src/motor_control_ros2/config/vehicle_motors.yaml`
- Vehicle comparison: `docs/project-notes/VEHICLE_CONTROL_FUNCTIONALITY_COMPARISON.md`
- Joystick flow: `docs/project-notes/VEHICLE_JOYSTICK_TO_MOTOR_COMMAND_FLOW_2025-12-19.md`

---

**Document Status:** Design complete, awaiting implementation
**Last Updated:** January 28, 2026
**Discussed with:** Dinesh (confirmed same-speed issue)
