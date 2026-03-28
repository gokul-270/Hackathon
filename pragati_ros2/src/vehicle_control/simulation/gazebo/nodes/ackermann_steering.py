#!/usr/bin/env python3
"""
Ackermann Steering Controller for vehicle_control Three-Wheeled Robot

Implements Ackermann geometry steering:
- Rear wheels: TRUE Ackermann geometry (inside/outside wheel angles)
- Front wheel: AVERAGE of rear wheel angles (simplified)

Alternative to velocity-based kinematics (kinematics_node.py).
Use: ros2 launch vehicle_control gazebo.launch.py ackermann:=true
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float64
import math
from dataclasses import dataclass


@dataclass
class SteeringAngles:
    """Container for calculated steering angles"""
    left: float
    right: float
    front: float = 0.0


class AckermannSteeringController(Node):
    """
    Ackermann steering controller for vehicle_control.
    
    Rear wheels: True Ackermann (inside/outside geometry)
    Front wheel: Average of rear angles
    
    Subscribes to: /cmd_vel (Twist)
    Publishes to: /steering/* and /wheel/*/velocity
    """

    def __init__(self):
        super().__init__('ackermann_steering')
        
        # Setup parameters
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
        
        # Create publishers for steering (Float64 for Gazebo direct control)
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
        
        # Store last steering angles for rate limiting
        self.last_steering = {
            'front': 0.0,
            'left': 0.0,
            'right': 0.0
        }
        
        # Maximum steering angular velocity (rad/s)
        self.max_steering_rate = 2.0  # rad/s (~115°/s)
        
        # Create timer for periodic publishing at fixed rate
        self.control_rate = 50.0  # Hz
        self.dt = 1.0 / self.control_rate
        
        # Store target steering angles
        self.target_steering = {
            'front': 0.0,
            'left': 0.0,
            'right': 0.0
        }
        
        # Store target wheel speeds
        self.target_speeds = {
            'front': 0.0,
            'left': 0.0,
            'right': 0.0
        }
        
        # Create timer for smooth control loop
        self.timer = self.create_timer(self.dt, self.control_loop)
        
        self.get_logger().info('vehicle_control Ackermann Steering Controller initialized!')
        self.get_logger().info('Using Ackermann geometry (Rear=true Ackermann, Front=average)')
        self.get_logger().info(f'Control rate: {self.control_rate} Hz')
        self.get_logger().info(f'Max steering rate: {math.degrees(self.max_steering_rate):.1f}°/s')
        self.get_logger().info('Waiting for /cmd_vel commands...')

    def setup_parameters(self):
        """Declare all ROS2 parameters."""
        self.declare_parameter('wheel_radius', 0.2875)  # Measured from STL mesh (575mm diameter)
        self.declare_parameter('wheel_base', 1.5)       # Distance front to rear (from URDF: 1.3+0.105+0.105)
        self.declare_parameter('wheel_tread', 1.8)      # Distance left to right (from URDF)
        self.declare_parameter('max_steering_angle', 1.570796)  # 90 degrees
        self.declare_parameter('max_wheel_speed', 20.0)
        self.declare_parameter('max_steering_rate', 2.0)  # rad/s

    def load_parameters(self):
        """Load parameters from ROS2 parameter server."""
        self.wheel_radius = self.get_parameter('wheel_radius').value
        self.wheel_base = self.get_parameter('wheel_base').value
        self.wheel_tread = self.get_parameter('wheel_tread').value
        self.wheel_center_distance = self.wheel_tread / 2  # Half track width
        
        self.max_steering_angle = self.get_parameter('max_steering_angle').value
        self.max_wheel_speed = self.get_parameter('max_wheel_speed').value
        self.max_steering_rate = self.get_parameter('max_steering_rate').value

    def print_configuration(self):
        """Print the robot configuration."""
        self.get_logger().info('=' * 50)
        self.get_logger().info('VEH1 ACKERMANN STEERING CONFIGURATION')
        self.get_logger().info('=' * 50)
        self.get_logger().info(f'Wheel radius: {self.wheel_radius} m')
        self.get_logger().info(f'Wheel base: {self.wheel_base} m')
        self.get_logger().info(f'Wheel tread: {self.wheel_tread} m')
        self.get_logger().info(f'Center distance: {self.wheel_center_distance} m')
        self.get_logger().info('=' * 50)

    def calculate_ackermann_angles(self, input_angle: float) -> SteeringAngles:
        """
        Calculate Ackermann steering angles for REAR wheels.
        
        radius_of_curvature = wheel_base / tan(input_angle)
        outside_wheel_angle = atan(wheel_base / (radius + center_distance))
        inside_wheel_angle = atan(wheel_base / (radius - center_distance))
        
        Args:
            input_angle: Desired steering angle in radians
            
        Returns:
            SteeringAngles with calculated left and right wheel angles
        """
        if abs(input_angle) < 0.001:  # Essentially straight
            return SteeringAngles(left=0.0, right=0.0)
        
        try:
            # Calculate radius of curvature
            radius_of_curvature = abs(self.wheel_base / math.tan(input_angle))
            
            # Calculate outside and inside wheel angles using Ackermann geometry
            outside_wheel_angle = math.atan(
                self.wheel_base / (radius_of_curvature + self.wheel_center_distance)
            )
            inside_wheel_angle = math.atan(
                self.wheel_base / abs(radius_of_curvature - self.wheel_center_distance)
            )
            
            # Determine which wheel is inside/outside based on turn direction
            if input_angle > 0:  # Left turn (positive angle)
                left_angle = inside_wheel_angle    # Left wheel is inside
                right_angle = outside_wheel_angle  # Right wheel is outside
            else:  # Right turn (negative angle)
                left_angle = -outside_wheel_angle  # Left wheel is outside
                right_angle = -inside_wheel_angle  # Right wheel is inside
            
            return SteeringAngles(left=left_angle, right=right_angle)
            
        except (ValueError, ZeroDivisionError) as e:
            self.get_logger().error(f'Ackermann calculation failed: {e}')
            return SteeringAngles(left=0.0, right=0.0)

    def calculate_three_wheel_ackermann_angles(self, input_angle: float) -> SteeringAngles:
        """
        Calculate three-wheel Ackermann steering angles.
        
        - First calculate standard Ackermann for rear wheels
        - Front wheel angle = AVERAGE of |left| and |right| angles
        
        Args:
            input_angle: Desired steering angle in radians
            
        Returns:
            SteeringAngles with left, right, and front wheel angles
        """
        if abs(input_angle) < 0.001:  # Essentially straight
            return SteeringAngles(left=0.0, right=0.0, front=0.0)
        
        try:
            # First calculate standard Ackermann angles for rear wheels
            angles = self.calculate_ackermann_angles(input_angle)
            
            # Calculate front wheel angle as AVERAGE of rear angles
            front_wheel_angle = (abs(angles.left) + abs(angles.right)) / 2
            
            # Apply correct sign based on turn direction
            if input_angle > 0:  # Left turn
                front_angle = -front_wheel_angle  # Front points right
            else:  # Right turn
                front_angle = front_wheel_angle   # Front points left
            
            return SteeringAngles(
                left=angles.left,
                right=angles.right,
                front=front_angle
            )
            
        except Exception as e:
            self.get_logger().error(f'Three-wheel Ackermann calculation failed: {e}')
            return SteeringAngles(left=0.0, right=0.0, front=0.0)

    def calculate_wheel_speeds(self, vx: float, omega: float, angles: SteeringAngles) -> dict:
        """
        Calculate wheel speeds based on turn radius.
        
        Args:
            vx: Linear velocity (m/s)
            omega: Angular velocity (rad/s)
            angles: Calculated steering angles
            
        Returns:
            Dictionary with wheel speeds (rad/s)
        """
        base_speed = vx / self.wheel_radius
        
        if abs(omega) < 0.001:
            return {
                'front': base_speed,
                'rear_left': base_speed,
                'rear_right': base_speed
            }
        
        # Calculate turn radius
        turn_radius = vx / omega if abs(omega) > 0.001 else float('inf')
        
        if abs(turn_radius) > 1000:
            return {
                'front': base_speed,
                'rear_left': base_speed,
                'rear_right': base_speed
            }
        
        # Calculate individual wheel radii
        left_radius = abs(turn_radius - self.wheel_center_distance)
        right_radius = abs(turn_radius + self.wheel_center_distance)
        ref_radius = abs(turn_radius)
        
        # Speed ratios
        if ref_radius > 0.01:
            left_ratio = left_radius / ref_radius
            right_ratio = right_radius / ref_radius
        else:
            left_ratio = right_ratio = 1.0
        
        return {
            'front': base_speed,
            'rear_left': base_speed * left_ratio,
            'rear_right': base_speed * right_ratio
        }

    def control_loop(self):
        """
        Smooth control loop with rate limiting to prevent oscillation.
        Gradually moves steering angles toward targets.
        """
        # Calculate maximum allowed change per timestep
        max_change = self.max_steering_rate * self.dt
        
        # Smoothly approach target steering angles
        for wheel in ['front', 'left', 'right']:
            target = self.target_steering[wheel]
            current = self.last_steering[wheel]
            
            # Calculate error with angle wrapping to avoid 360° slewing at ±pi boundary
            error = math.atan2(math.sin(target - current), math.cos(target - current))
            
            # Limit rate of change
            if abs(error) > max_change:
                change = max_change if error > 0 else -max_change
                new_angle = current + change
            else:
                new_angle = target
            
            # Update last steering angle
            self.last_steering[wheel] = new_angle
        
        # Publish steering commands with rate limiting
        front_steer_msg = Float64()
        front_steer_msg.data = self.last_steering['front']
        self.front_steer_pub.publish(front_steer_msg)
        
        # Publish left and right directly — negate left for inverted URDF joint axis
        left_steer_msg = Float64()
        left_steer_msg.data = -self.last_steering['left']  # Negate for inverted joint axis
        self.left_steer_pub.publish(left_steer_msg)
        
        right_steer_msg = Float64()
        right_steer_msg.data = self.last_steering['right']
        self.right_steer_pub.publish(right_steer_msg)
        
        # Publish wheel speeds (no rate limiting needed)
        front_drive_msg = Float64()
        front_drive_msg.data = self.target_speeds['front']
        self.front_drive_pub.publish(front_drive_msg)
        
        # Publish left and right directly (no swap)
        left_drive_msg = Float64()
        left_drive_msg.data = self.target_speeds['left']
        self.left_drive_pub.publish(left_drive_msg)
        
        right_drive_msg = Float64()
        right_drive_msg.data = self.target_speeds['right']
        self.right_drive_pub.publish(right_drive_msg)

    def cmd_vel_callback(self, msg: Twist):
        """
        Handle incoming velocity commands using Ackermann steering.
        """
        original_vx = msg.linear.x
        omega = msg.angular.z
        
        # Convert omega to steering angle (bicycle model)
        if abs(original_vx) > 0.01:
            input_angle = math.atan(self.wheel_base * omega / original_vx)
        elif abs(omega) > 0.001:
            # Pure rotation - max steering
            input_angle = self.max_steering_angle if omega > 0 else -self.max_steering_angle
        else:
            input_angle = 0.0
        
        # Clamp input angle
        input_angle = max(-self.max_steering_angle, min(self.max_steering_angle, input_angle))
        
        # Speed reduction for sharp turns
        max_steering = abs(input_angle)
        if max_steering > 0.4:  # ~23 degrees threshold
            speed_factor = max(0.4, 1.0 - (max_steering - 0.4) * 0.6)
            vx = original_vx * speed_factor
            if abs(vx - self.last_vx) > 0.01:
                self.get_logger().info(f'Sharp turn {math.degrees(max_steering):.1f}°, reducing speed to {speed_factor*100:.0f}%')
        else:
            vx = original_vx
        
        # Log command if changed
        if abs(vx - self.last_vx) > 0.01 or abs(omega - self.last_omega) > 0.01:
            self.get_logger().info(f'[ACKERMANN] cmd_vel: vx={vx:.3f} m/s, omega={omega:.3f} rad/s')
            self.last_vx = vx
            self.last_omega = omega
        
        # Calculate three-wheel Ackermann angles
        angles = self.calculate_three_wheel_ackermann_angles(input_angle)
        
        # Calculate wheel speeds
        speeds = self.calculate_wheel_speeds(vx, omega, angles)
        
        # Update target steering angles
        self.target_steering['front'] = angles.front
        self.target_steering['left'] = angles.left
        self.target_steering['right'] = angles.right
        
        # Update target wheel speeds
        self.target_speeds['front'] = speeds['front']
        self.target_speeds['left'] = speeds['rear_left']
        self.target_speeds['right'] = speeds['rear_right']
        
        # Log steering angles (only on significant change)
        if abs(input_angle) > 0.01:
            self.get_logger().info(
                f'  Steering: RearL={math.degrees(angles.left):.1f}°, '
                f'RearR={math.degrees(angles.right):.1f}°, '
                f'Front={math.degrees(angles.front):.1f}° (avg)'
            )


def main(args=None):
    rclpy.init(args=args)
    node = AckermannSteeringController()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
