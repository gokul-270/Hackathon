#!/usr/bin/env python3
"""
Joystick Teleoperation Node for vehicle_control Robot

This node converts joystick inputs to Twist messages for robot control.
Supports standard game controllers (Xbox, PS4, Logitech, etc.)

Button Layout (Xbox-style):
  - Left Stick Y-axis: Forward/Backward (linear.x)
  - Right Stick X-axis: Rotate Left/Right (angular.z)
  - Button A (0): Enable turbo mode (2x speed)
  - Button B (1): Emergency stop
  
Dependencies: ros2-joy package
  sudo apt install ros-${ROS_DISTRO}-joy

Launch joy node first:
  ros2 run joy joy_node

Author: vehicle_control Package
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from geometry_msgs.msg import Twist


class JoyTeleop(Node):
    """Convert joystick inputs to velocity commands."""

    def __init__(self):
        super().__init__('joy_teleop')
        
        # Declare parameters
        self.setup_parameters()
        self.load_parameters()
        
        # Create subscriber for joystick
        self.joy_sub = self.create_subscription(
            Joy,
            '/joy',
            self.joy_callback,
            10
        )
        
        # Create publisher for velocity commands
        self.cmd_vel_pub = self.create_publisher(
            Twist,
            '/cmd_vel',
            10
        )
        
        # State variables
        self.turbo_enabled = False
        self.last_turbo_button = 0
        
        self.get_logger().info('=' * 60)
        self.get_logger().info('JOYSTICK TELEOP NODE STARTED')
        self.get_logger().info('=' * 60)
        self.get_logger().info('Controls:')
        self.get_logger().info(f'  Left Stick Y (Axis {self.axis_linear}): Forward/Backward')
        self.get_logger().info(f'  Right Stick X (Axis {self.axis_angular}): Rotate Left/Right')
        self.get_logger().info(f'  Button {self.button_turbo}: Toggle Turbo Mode (2x speed)')
        self.get_logger().info(f'  Button {self.button_stop}: Emergency Stop')
        self.get_logger().info('')
        self.get_logger().info('Speed Settings:')
        self.get_logger().info(f'  Normal: {self.max_linear_speed:.2f} m/s linear, {self.max_angular_speed:.2f} rad/s angular')
        self.get_logger().info(f'  Turbo:  {self.max_linear_speed*2:.2f} m/s linear, {self.max_angular_speed*2:.2f} rad/s angular')
        self.get_logger().info('=' * 60)
        self.get_logger().info('Waiting for joystick input on /joy...')

    def setup_parameters(self):
        """Declare all parameters with defaults."""
        # Axis mappings (Xbox controller default)
        self.declare_parameter('axis_linear', 1)   # Left stick Y-axis
        self.declare_parameter('axis_angular', 3)  # Right stick X-axis
        
        # Button mappings (Xbox controller default)
        self.declare_parameter('button_turbo', 0)  # A button
        self.declare_parameter('button_stop', 1)   # B button
        
        # Speed limits
        self.declare_parameter('max_linear_speed', 0.5)   # m/s
        self.declare_parameter('max_angular_speed', 1.0)  # rad/s
        
        # Deadzone to prevent drift
        self.declare_parameter('deadzone', 0.1)

    def load_parameters(self):
        """Load parameters from parameter server."""
        self.axis_linear = self.get_parameter('axis_linear').value
        self.axis_angular = self.get_parameter('axis_angular').value
        self.button_turbo = self.get_parameter('button_turbo').value
        self.button_stop = self.get_parameter('button_stop').value
        self.max_linear_speed = self.get_parameter('max_linear_speed').value
        self.max_angular_speed = self.get_parameter('max_angular_speed').value
        self.deadzone = self.get_parameter('deadzone').value

    def apply_deadzone(self, value: float) -> float:
        """Apply deadzone to joystick value."""
        if abs(value) < self.deadzone:
            return 0.0
        # Scale value to maintain smooth transition
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - self.deadzone) / (1.0 - self.deadzone)

    def joy_callback(self, msg: Joy):
        """Process joystick input and publish velocity command."""
        # Check for valid input
        if len(msg.axes) <= max(self.axis_linear, self.axis_angular):
            self.get_logger().warn('Not enough joystick axes!')
            return
        if len(msg.buttons) <= max(self.button_turbo, self.button_stop):
            self.get_logger().warn('Not enough joystick buttons!')
            return
        
        # Handle emergency stop button
        if msg.buttons[self.button_stop] == 1:
            twist = Twist()  # All zeros
            self.cmd_vel_pub.publish(twist)
            self.get_logger().info('EMERGENCY STOP ACTIVATED!')
            return
        
        # Handle turbo button (toggle on press)
        if msg.buttons[self.button_turbo] == 1 and self.last_turbo_button == 0:
            self.turbo_enabled = not self.turbo_enabled
            mode = "ENABLED" if self.turbo_enabled else "DISABLED"
            self.get_logger().info(f'Turbo Mode {mode}')
        self.last_turbo_button = msg.buttons[self.button_turbo]
        
        # Read joystick axes and apply deadzone
        linear_raw = self.apply_deadzone(msg.axes[self.axis_linear])
        angular_raw = self.apply_deadzone(msg.axes[self.axis_angular])
        
        # Calculate speed multiplier
        speed_multiplier = 2.0 if self.turbo_enabled else 1.0
        
        # Create velocity command
        twist = Twist()
        twist.linear.x = linear_raw * self.max_linear_speed * speed_multiplier
        twist.angular.z = angular_raw * self.max_angular_speed * speed_multiplier
        
        # Publish command
        self.cmd_vel_pub.publish(twist)
        
        # Log significant commands
        if abs(linear_raw) > 0.01 or abs(angular_raw) > 0.01:
            turbo_str = " [TURBO]" if self.turbo_enabled else ""
            self.get_logger().info(
                f'cmd_vel: linear={twist.linear.x:.3f} m/s, '
                f'angular={twist.angular.z:.3f} rad/s{turbo_str}',
                throttle_duration_sec=0.5  # Throttle logging to 2Hz
            )


def main(args=None):
    rclpy.init(args=args)
    node = JoyTeleop()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Send stop command on exit
        twist = Twist()
        node.cmd_vel_pub.publish(twist)
        node.get_logger().info('Shutting down - sent stop command')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
