#!/usr/bin/env python3
"""
Velocity-Based Kinematics Node for vehicle_control Three-Wheeled Robot

This node implements rigid-body velocity kinematics matching triwheel_robot algorithm.
Uses the same velocity-based kinematics equations.

Kinematics equations (for each wheel i at position (xi, yi) from robot center):
    vix = vx - omega * yi     (x-component of wheel velocity)
    viy = omega * xi          (y-component of wheel velocity)

    steer_angle_i = atan2(viy, vix)                        (steering angle)
    wheel_speed_i = sqrt(vix^2 + viy^2) / wheel_radius    (wheel angular velocity)

Subscribes to: /cmd_vel (geometry_msgs/Twist)
Publishes to: /steering/* (std_msgs/Float64) and /wheel/*/velocity (std_msgs/Float64)

Author: vehicle_control Package
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float64
import math


class Veh1Kinematics(Node):
    """
    Velocity-based kinematics controller for vehicle_control three-wheeled robot.
    Matches triwheel_robot algorithm exactly.
    """

    def __init__(self):
        super().__init__('vehicle_control_kinematics')

        # Declare and get parameters
        self.setup_parameters()
        self.load_parameters()

        # Print configuration
        self.print_configuration()

        # Create subscriber for velocity commands
        self.cmd_vel_sub = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        # Create publishers for steering (position control)
        self.front_steer_pub = self.create_publisher(
            Float64, '/steering/front', 10)
        self.left_steer_pub = self.create_publisher(
            Float64, '/steering/left', 10)
        self.right_steer_pub = self.create_publisher(
            Float64, '/steering/right', 10)

        # Create publishers for drive (velocity control)
        self.front_drive_pub = self.create_publisher(
            Float64, '/wheel/front/velocity', 10)
        self.left_drive_pub = self.create_publisher(
            Float64, '/wheel/left/velocity', 10)
        self.right_drive_pub = self.create_publisher(
            Float64, '/wheel/right/velocity', 10)

        # Store last command for debugging
        self.last_vx = 0.0
        self.last_omega = 0.0

        # Store last steering angles for rate limiting and filtering
        self.last_steering = {
            'front': 0.0,
            'left': 0.0,
            'right': 0.0
        }

        # ═══════════════════════════════════════════════════════════
        # Steering rate limit (prevents sudden jerks)
        # ═══════════════════════════════════════════════════════════
        # Note: max_steering_rate is loaded from ROS parameter in load_parameters() (default 2.0 rad/s)

        # Low-pass filter for steering (smooths out rapid changes)
        self.steering_filter_alpha = 0.3  # 0=no filter, 1=instant (30% new, 70% old)

        # Create timer for periodic publishing at fixed rate
        self.control_rate = 50.0  # Hz
        self.dt = 1.0 / self.control_rate

        # Store target steering angles and wheel speeds
        self.target_steering = {
            'front': 0.0,
            'left': 0.0,
            'right': 0.0
        }
        self.target_speed = {
            'front': 0.0,
            'left': 0.0,
            'right': 0.0
        }

        # Create timer for smooth control loop
        self.timer = self.create_timer(self.dt, self.control_loop)

        self.get_logger().info('vehicle_control Kinematics Node initialized!')
        self.get_logger().info(f'Control rate: {self.control_rate} Hz')
        self.get_logger().info(f'Max steering rate: {math.degrees(self.max_steering_rate):.1f}°/s')
        self.get_logger().info('Waiting for /cmd_vel commands...')

    def setup_parameters(self):
        """Declare all ROS2 parameters."""
        # Wheel radius from URDF (575mm diameter)
        self.declare_parameter('wheel_radius', 0.2875)

        # URDF wheel positions - base-v1 is AT THE RIGHT WHEEL (not rear axle center!)
        # Using rounded values for cleaner kinematics
        self.declare_parameter('front_wheel_urdf', [1.40, 0.90])    # From base-v1 + steering offset
        self.declare_parameter('left_wheel_urdf', [-0.10, 1.80])    # From base-v1 + steering offset
        self.declare_parameter('right_wheel_urdf', [-0.10, 0.00])   # From base-v1 + steering offset

        # For velocity kinematics, we need to use robot CENTER as reference
        # Robot center: midpoint of front wheel and rear axle (matches URDF origin link)
        # Front wheel: x=1.40, Rear axle center: x=-0.10 → midpoint = 0.65
        self.declare_parameter('kinematic_center_offset', [0.65, 0.90])

        self.declare_parameter('max_steering_angle', 1.570796)  # 90 degrees
        self.declare_parameter('max_wheel_speed', 20.0)  # rad/s
        self.declare_parameter('max_steering_rate', 2.0)  # rad/s - steering velocity limit

    def load_parameters(self):
        """Load parameters from ROS2 parameter server."""
        self.wheel_radius = self.get_parameter('wheel_radius').value

        # Get URDF positions (relative to base-v1 at rear axle)
        front_urdf = self.get_parameter('front_wheel_urdf').value
        left_urdf = self.get_parameter('left_wheel_urdf').value
        right_urdf = self.get_parameter('right_wheel_urdf').value

        # Get kinematic center offset
        center_offset = self.get_parameter('kinematic_center_offset').value

        # Convert URDF positions to kinematic positions (relative to robot center)
        # This is KEY: URDF stays at rear axle, but kinematics uses center reference
        self.wheels = {
            'front': {
                'x': front_urdf[0] - center_offset[0],
                'y': front_urdf[1] - center_offset[1]
            },
            'left': {
                'x': left_urdf[0] - center_offset[0],
                'y': left_urdf[1] - center_offset[1]
            },
            'right': {
                'x': right_urdf[0] - center_offset[0],
                'y': right_urdf[1] - center_offset[1]
            }
        }

        self.max_steering_angle = self.get_parameter('max_steering_angle').value
        self.max_wheel_speed = self.get_parameter('max_wheel_speed').value
        self.max_steering_rate = self.get_parameter('max_steering_rate').value

    def print_configuration(self):
        """Print the robot configuration for verification."""
        self.get_logger().info('=' * 50)
        self.get_logger().info('VEH1 ROBOT CONFIGURATION')
        self.get_logger().info('=' * 50)
        self.get_logger().info(f'Wheel radius: {self.wheel_radius} m')
        self.get_logger().info('Wheel positions for KINEMATICS (relative to CENTER):')
        for name, pos in self.wheels.items():
            self.get_logger().info(f'  {name}: x={pos["x"]:.3f}m, y={pos["y"]:.3f}m')
        self.get_logger().info('Note: URDF base-v1 remains at rear axle')
        self.get_logger().info('=' * 50)

    def compute_wheel_kinematics(self, vx: float, omega: float, wheel_x: float, wheel_y: float, wheel_name: str = ''):
        """
        Compute steering angle and wheel speed for a single wheel.

        Uses velocity-based rigid-body kinematics:
            vix = vx - omega * yi     (linear velocity x-component at wheel)
            viy = omega * xi          (linear velocity y-component at wheel)

        Args:
            vx: Linear velocity in x direction (m/s)
            omega: Angular velocity about z axis (rad/s)
            wheel_x: Wheel x position relative to robot center (m)
            wheel_y: Wheel y position relative to robot center (m)
            wheel_name: Name of the wheel (for hold-last-angle lookup)

        Returns:
            (steering_angle, wheel_speed) tuple
        """
        # Compute velocity components at wheel location
        # From rigid-body kinematics: v_wheel = v_body + omega x r
        #   omega x r = (0,0,omega) x (x,y,0) = (-omega*y, omega*x, 0)
        vix = vx - omega * wheel_y
        viy = omega * wheel_x

        if abs(vix) < 1e-6 and abs(viy) < 1e-6:
            # Near zero velocity - hold last steering angle, zero speed
            return self.last_steering.get(wheel_name, 0.0), 0.0

        # Compute raw steering angle from velocity vector
        raw_angle = math.atan2(viy, vix)

        # Compute magnitude
        linear_speed = math.sqrt(vix**2 + viy**2)
        wheel_speed = linear_speed / self.wheel_radius

        # Handle backward motion properly:
        # When the velocity vector at the wheel points predominantly backward
        # (|angle| > 90°), it's more natural to flip the steering by 180° and
        # reverse the wheel spin.  This keeps steering angles within ±90°.
        if abs(raw_angle) > math.pi / 2:
            # Flip: steer the opposite way, spin wheel backward
            if raw_angle > 0:
                raw_angle -= math.pi
            else:
                raw_angle += math.pi
            wheel_speed = -wheel_speed

        # Clamp
        steering_angle = max(-self.max_steering_angle,
                             min(self.max_steering_angle, raw_angle))
        wheel_speed = max(-self.max_wheel_speed,
                          min(self.max_wheel_speed, wheel_speed))

        return steering_angle, wheel_speed

    def _effective_steering_angle(self, vx, omega, wheel_pos):
        """
        Compute the effective steering angle after backward-flip,
        used for speed-reduction decisions.  This mirrors the logic
        in compute_wheel_kinematics so that backward motion is NOT
        mistakenly penalised as a sharp turn.
        """
        vix = vx - omega * wheel_pos['y']
        viy = omega * wheel_pos['x']
        if abs(vix) < 1e-6 and abs(viy) < 1e-6:
            return 0.0
        raw = math.atan2(viy, vix)
        # Apply the same backward-flip
        if abs(raw) > math.pi / 2:
            if raw > 0:
                raw -= math.pi
            else:
                raw += math.pi
        return abs(raw)

    def cmd_vel_callback(self, msg: Twist):
        """
        Handle incoming velocity commands.

        Uses PURE velocity kinematics with physical constraints:
        1. Speed reduction when turning sharply (based on effective steering angle)
        2. Steering rate limiting (in control_loop)
        """
        vx_raw = msg.linear.x      # Requested forward velocity (m/s)
        omega_raw = msg.angular.z   # Requested angular velocity (rad/s)

        # DEADZONE: Treat small angular velocities as zero to prevent oscillation
        if abs(omega_raw) < 0.02:  # < ~1°/s is considered straight
            omega_raw = 0.0

        # Speed reduction for sharp turns — use EFFECTIVE steering angle
        # (after backward-flip) so that pure backward is NOT treated as a turn
        max_eff_steer = 0.0
        for wheel_pos in self.wheels.values():
            eff = self._effective_steering_angle(vx_raw, omega_raw, wheel_pos)
            max_eff_steer = max(max_eff_steer, eff)

        # Reduce speed proportionally when effective steering angle is large
        if max_eff_steer > 0.4:  # ~23 degrees threshold
            speed_factor = max(0.4, 1.0 - (max_eff_steer - 0.4) * 0.6)
            vx = vx_raw * speed_factor
            omega = omega_raw * speed_factor
            if abs(vx - self.last_vx) > 0.01:
                self.get_logger().info(
                    f'Sharp turn {math.degrees(max_eff_steer):.1f}°, '
                    f'reducing speed to {speed_factor*100:.0f}%')
        else:
            vx = vx_raw
            omega = omega_raw

        # Additional speed cap proportional to turning rate
        k_turn = 2.0
        max_speed_for_turn = 1.0 / (1.0 + k_turn * abs(omega))
        if abs(vx) > max_speed_for_turn:
            vx = max_speed_for_turn if vx > 0 else -max_speed_for_turn

        # Log command if changed significantly
        if abs(vx - self.last_vx) > 0.01 or abs(omega - self.last_omega) > 0.01:
            if vx != vx_raw or omega != omega_raw:
                self.get_logger().info(
                    f'cmd_vel: vx={vx_raw:.3f}→{vx:.3f} m/s, '
                    f'omega={omega_raw:.3f}→{omega:.3f} rad/s (limited)')
            else:
                self.get_logger().info(
                    f'cmd_vel: vx={vx:.3f} m/s, omega={omega:.3f} rad/s')
            self.last_vx = vx
            self.last_omega = omega

        # ═══════════════════════════════════════════════════════════
        # PURE VELOCITY KINEMATICS: All wheels steer independently
        # ═══════════════════════════════════════════════════════════
        results = {}
        for wheel_name, wheel_pos in self.wheels.items():
            steer, speed = self.compute_wheel_kinematics(
                vx, omega, wheel_pos['x'], wheel_pos['y'], wheel_name
            )
            results[wheel_name] = {'steer': steer, 'speed': speed}

        # Update targets (will be smoothly approached in control_loop)
        self.target_steering['front'] = results['front']['steer']
        self.target_steering['left'] = results['left']['steer']
        self.target_steering['right'] = results['right']['steer']

        # Store target wheel speeds (published by control_loop alongside steering)
        self.target_speed['front'] = results['front']['speed']
        self.target_speed['left'] = results['left']['speed']
        self.target_speed['right'] = results['right']['speed']

        # Log detailed output (only when moving significantly)
        if abs(vx) > 0.05 or abs(omega) > 0.05:
            self.get_logger().info(
                f'📊 Front: {math.degrees(results["front"]["steer"]):.1f}° @ '
                f'{results["front"]["speed"]:.2f}rad/s | '
                f'Left: {math.degrees(results["left"]["steer"]):.1f}° @ '
                f'{results["left"]["speed"]:.2f}rad/s | '
                f'Right: {math.degrees(results["right"]["steer"]):.1f}° @ '
                f'{results["right"]["speed"]:.2f}rad/s')

    def control_loop(self):
        """
        Periodic control loop for smooth steering with rate limiting and filtering.
        Publishes both steering and drive commands at a fixed rate.
        """
        # Apply rate limiting + low-pass filter to each wheel's steering angle
        for wheel_name in ['front', 'left', 'right']:
            target = self.target_steering[wheel_name]
            current = self.last_steering[wheel_name]

            # Step 1: Low-pass filter (smooths rapid changes)
            filtered_target = (self.steering_filter_alpha * target +
                               (1.0 - self.steering_filter_alpha) * current)

            # Step 2: Rate limiting (prevents jerks)
            # Angle wrapping via atan2(sin,cos) to always take shortest path
            error = math.atan2(math.sin(filtered_target - current),
                               math.cos(filtered_target - current))
            max_change = self.max_steering_rate * self.dt

            if abs(error) > max_change:
                change = max_change if error > 0 else -max_change
                new_angle = current + change
            else:
                new_angle = filtered_target

            self.last_steering[wheel_name] = new_angle

        # Publish smoothed steering commands
        # Each wheel publishes its own computed values directly (no L/R swap)
        # Left steering angle is negated to compensate for inverted URDF joint axis
        front_steer_msg = Float64()
        front_steer_msg.data = self.last_steering['front']
        self.front_steer_pub.publish(front_steer_msg)

        left_steer_msg = Float64()
        left_steer_msg.data = -self.last_steering['left']  # Negate for inverted joint axis  
        self.left_steer_pub.publish(left_steer_msg)
        
        # CRITICAL DEBUG: Always log left steering to debug stuck wheel
        self.get_logger().info(
            f'🔴 LEFT WHEEL: computed={math.degrees(self.last_steering["left"]):.1f}° | '
            f'published={math.degrees(left_steer_msg.data):.1f}° | '
            f'target={math.degrees(self.target_steering["left"]):.1f}°',
            throttle_duration_sec=0.2)

        right_steer_msg = Float64()
        right_steer_msg.data = self.last_steering['right']
        self.right_steer_pub.publish(right_steer_msg)
        
        # DEBUG: Log published steering values
        if abs(self.last_vx) > 0.01 or abs(self.last_omega) > 0.01:
            self.get_logger().info(
                f'🎯 PUBLISHED: Front={math.degrees(front_steer_msg.data):.1f}° | '
                f'Left={math.degrees(left_steer_msg.data):.1f}° | '
                f'Right={math.degrees(right_steer_msg.data):.1f}°', 
                throttle_duration_sec=0.5)

        # Publish drive commands at full speed (no swap)
        # NOTE: Steering progress factor removed - original code had none,
        # and it was making movement sluggish. The rate-limited steering
        # is already smooth enough without reducing drive speed.
        front_drive_msg = Float64()
        front_drive_msg.data = self.target_speed['front']
        self.front_drive_pub.publish(front_drive_msg)

        left_drive_msg = Float64()
        left_drive_msg.data = self.target_speed['left']
        self.left_drive_pub.publish(left_drive_msg)

        right_drive_msg = Float64()
        right_drive_msg.data = self.target_speed['right']
        self.right_drive_pub.publish(right_drive_msg)


def main(args=None):
    rclpy.init(args=args)
    node = Veh1Kinematics()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
