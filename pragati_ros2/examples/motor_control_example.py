#!/usr/bin/env python3
"""
Motor Control Example - Pragati ROS2

Demonstrates basic motor control operations:
- Publishing joint commands
- Reading joint states
- Using motor services
- Monitoring diagnostics

Prerequisites:
- Motor control node running
- Motors initialized and ready

Usage:
    python3 motor_control_example.py
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from diagnostic_msgs.msg import DiagnosticArray
import time


class MotorControlExample(Node):
    def __init__(self):
        super().__init__('motor_control_example')
        
        # Publisher for joint commands
        self.cmd_pub = self.create_publisher(
            Float64MultiArray,
            '/joint_commands',
            10
        )
        
        # Subscriber for joint states
        self.state_sub = self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_state_callback,
            10
        )
        
        # Subscriber for diagnostics
        self.diag_sub = self.create_subscription(
            DiagnosticArray,
            '/diagnostics',
            self.diagnostics_callback,
            10
        )
        
        self.current_positions = []
        self.get_logger().info('Motor Control Example Node Started')
    
    def joint_state_callback(self, msg):
        """Callback for joint state updates."""
        self.current_positions = msg.position
        
        # Print current joint positions (limited rate)
        if hasattr(self, '_last_print'):
            if time.time() - self._last_print < 1.0:
                return
        
        self._last_print = time.time()
        self.get_logger().info(f'Current positions: {[f"{p:.3f}" for p in msg.position]}')
    
    def diagnostics_callback(self, msg):
        """Callback for diagnostics updates."""
        for status in msg.status:
            if status.level > 0:  # Warning or error
                self.get_logger().warn(f'{status.name}: {status.message}')
    
    def send_position_command(self, positions):
        """Send position command to motors.
        
        Args:
            positions: List of target positions (radians) for each joint
        """
        msg = Float64MultiArray()
        msg.data = positions
        self.cmd_pub.publish(msg)
        self.get_logger().info(f'Sent command: {[f"{p:.3f}" for p in positions]}')
    
    def wait_for_position(self, target_positions, tolerance=0.05, timeout=10.0):
        """Wait until motors reach target positions.
        
        Args:
            target_positions: Target positions to reach
            tolerance: Acceptable position error (radians)
            timeout: Maximum time to wait (seconds)
        
        Returns:
            True if reached, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if not self.current_positions:
                rclpy.spin_once(self, timeout_sec=0.1)
                continue
            
            # Check if all joints within tolerance
            errors = [abs(t - c) for t, c in zip(target_positions, self.current_positions)]
            
            if all(e < tolerance for e in errors):
                self.get_logger().info(f'Reached target! Errors: {[f"{e:.4f}" for e in errors]}')
                return True
            
            rclpy.spin_once(self, timeout_sec=0.1)
        
        self.get_logger().warn('Timeout waiting for position')
        return False


def main():
    rclpy.init()
    node = MotorControlExample()
    
    try:
        # Wait for first joint state
        node.get_logger().info('Waiting for joint states...')
        while not node.current_positions:
            rclpy.spin_once(node, timeout_sec=0.1)
        
        node.get_logger().info(f'Initial position: {node.current_positions}')
        
        # Example 1: Simple position command
        node.get_logger().info('\n=== Example 1: Single Position Command ===')
        target = [0.0, 0.5, -0.5]  # Example for 3-joint arm
        node.send_position_command(target)
        node.wait_for_position(target)
        time.sleep(1.0)
        
        # Example 2: Sequence of movements
        node.get_logger().info('\n=== Example 2: Movement Sequence ===')
        waypoints = [
            [0.0, 0.0, 0.0],
            [0.5, 0.5, 0.5],
            [1.0, 0.5, 0.0],
            [0.0, 0.0, 0.0]
        ]
        
        for i, waypoint in enumerate(waypoints):
            node.get_logger().info(f'Moving to waypoint {i+1}/{len(waypoints)}')
            node.send_position_command(waypoint)
            node.wait_for_position(waypoint)
            time.sleep(0.5)
        
        # Example 3: Smooth trajectory
        node.get_logger().info('\n=== Example 3: Smooth Sinusoidal Motion ===')
        import math
        duration = 5.0  # seconds
        frequency = 0.5  # Hz
        amplitude = 0.3  # radians
        
        start_time = time.time()
        rate = node.create_rate(20)  # 20 Hz control loop
        
        while time.time() - start_time < duration:
            t = time.time() - start_time
            angle = amplitude * math.sin(2 * math.pi * frequency * t)
            
            # Send sinusoidal command to first joint
            target = [angle, 0.0, 0.0]
            node.send_position_command(target)
            
            rate.sleep()
        
        # Return to home
        node.get_logger().info('\n=== Returning to Home Position ===')
        home = [0.0, 0.0, 0.0]
        node.send_position_command(home)
        node.wait_for_position(home)
        
        node.get_logger().info('\n=== Examples Complete ===')
        
    except KeyboardInterrupt:
        node.get_logger().info('Interrupted by user')
    
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
