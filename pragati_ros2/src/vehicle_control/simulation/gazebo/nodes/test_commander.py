#!/usr/bin/env python3
"""
Test Commander Node for vehicle_control Three-Wheeled Robot

Matches triwheel_robot test_commander exactly.
Provides balanced velocity commands for proper steering behavior.

Usage:
    ros2 run vehicle_control test_commander --ros-args -p test_mode:=straight
    ros2 run vehicle_control test_commander --ros-args -p test_mode:=arc
    ros2 run vehicle_control test_commander --ros-args -p test_mode:=rotate
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import math


class TestCommander(Node):
    """
    Test commander for verifying vehicle_control motion with balanced velocities.
    """

    def __init__(self):
        super().__init__('test_commander')
        
        # Declare parameters (matching triwheel_robot)
        self.declare_parameter('test_mode', 'straight')
        self.declare_parameter('duration', 10.0)
        self.declare_parameter('linear_vel', 0.3)      # Reasonable forward speed
        self.declare_parameter('angular_vel', 0.3)     # Balanced angular velocity
        
        # Get parameters
        self.test_mode = self.get_parameter('test_mode').value
        self.duration = self.get_parameter('duration').value
        self.linear_vel = self.get_parameter('linear_vel').value
        self.angular_vel = self.get_parameter('angular_vel').value
        
        # Publisher
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        
        # Timer for publishing
        self.timer = self.create_timer(0.1, self.timer_callback)
        
        # Timing
        self.start_time = self.get_clock().now()
        
        self.get_logger().info(f'🎮 Test Commander started in mode: {self.test_mode}')
        self.get_logger().info(f'⏱️  Duration: {self.duration}s')
        self.print_test_info()

    def print_test_info(self):
        """Print information about the current test."""
        self.get_logger().info('=' * 60)
        if self.test_mode == 'straight':
            self.get_logger().info('TEST: Straight line motion')
            self.get_logger().info(f'  vx = {self.linear_vel} m/s, omega = 0')
            self.get_logger().info('  Expected: Robot moves straight forward')
            self.get_logger().info('  All wheels should point forward (0°)')
            
        elif self.test_mode == 'rotate':
            self.get_logger().info('TEST: Pure rotation (spin in place)')
            self.get_logger().info(f'  vx = 0, omega = {self.angular_vel} rad/s')
            self.get_logger().info('  Expected: Robot spins in place')
            self.get_logger().info('  Wheels point tangent to rotation circle')
            
        elif self.test_mode == 'arc':
            self.get_logger().info('TEST: Arc motion (gentle turn)')
            self.get_logger().info(f'  vx = {self.linear_vel} m/s, omega = {self.angular_vel} rad/s')
            radius = self.linear_vel / self.angular_vel if self.angular_vel != 0 else float('inf')
            self.get_logger().info(f'  Turn radius: {radius:.2f} m')
            self.get_logger().info('  Each wheel will have DIFFERENT steering angle')
            
        elif self.test_mode == 'right_turn':
            self.get_logger().info('TEST: Right turn')
            self.get_logger().info(f'  vx = {self.linear_vel} m/s, omega = {-self.angular_vel} rad/s')
            self.get_logger().info('  Expected: Robot curves to the right')
            
        elif self.test_mode == 'slalom':
            self.get_logger().info('TEST: Slalom pattern (sinusoidal)')
            self.get_logger().info(f'  vx = {self.linear_vel} m/s, omega varies ±{self.angular_vel} rad/s')
            self.get_logger().info('  Expected: Snake-like motion')
            
        self.get_logger().info('=' * 60)

    def timer_callback(self):
        """Publish velocity commands based on test mode."""
        elapsed = (self.get_clock().now() - self.start_time).nanoseconds / 1e9
        
        if elapsed > self.duration:
            # Stop the robot
            msg = Twist()
            self.cmd_vel_pub.publish(msg)
            self.get_logger().info('✅ Test complete! Robot stopped.')
            self.timer.cancel()
            return
        
        msg = Twist()
        
        if self.test_mode == 'straight':
            msg.linear.x = self.linear_vel
            msg.angular.z = 0.0
            
        elif self.test_mode == 'rotate':
            msg.linear.x = 0.0
            msg.angular.z = self.angular_vel
            
        elif self.test_mode == 'arc':
            msg.linear.x = self.linear_vel
            msg.angular.z = self.angular_vel
            
        elif self.test_mode == 'right_turn':
            msg.linear.x = self.linear_vel
            msg.angular.z = -self.angular_vel
            
        elif self.test_mode == 'slalom':
            # Slalom pattern - sinusoidal steering
            msg.linear.x = self.linear_vel
            msg.angular.z = self.angular_vel * math.sin(elapsed * 2.0)
        
        self.cmd_vel_pub.publish(msg)
        
        # Log every 2 seconds
        if int(elapsed * 5) != int((elapsed - 0.1) * 5):
            self.get_logger().info(f'  Publishing: vx={msg.linear.x:.2f}, omega={msg.angular.z:.2f}')


def main(args=None):
    rclpy.init(args=args)
    node = TestCommander()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Make sure to stop the robot
        msg = Twist()
        node.cmd_vel_pub.publish(msg)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
