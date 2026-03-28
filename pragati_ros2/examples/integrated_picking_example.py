#!/usr/bin/env python3
"""
Integrated Picking Example - Pragati ROS2

Demonstrates end-to-end cotton picking workflow:
- Cotton detection
- Coordinate transformation
- Arm movement
- Pick operation
- Sequential multi-cotton picking

Prerequisites:
- Motor control node running
- Cotton detection node running
- Yanthra move node running (if applicable)

Usage:
    python3 integrated_picking_example.py
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from geometry_msgs.msg import Point, Pose
from std_srvs.srv import Trigger
from std_msgs.msg import Float64MultiArray
import time
import math


class IntegratedPickingExample(Node):
    def __init__(self):
        super().__init__('integrated_picking_example')
        
        # Publishers
        self.joint_cmd_pub = self.create_publisher(
            Float64MultiArray,
            '/joint_commands',
            10
        )
        
        # Subscribers
        self.joint_state_sub = self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_state_callback,
            10
        )
        
        self.detection_sub = self.create_subscription(
            Point,
            '/cotton_detection/target',
            self.detection_callback,
            10
        )
        
        # Service clients
        self.start_detection_client = self.create_client(
            Trigger, '/cotton_detection/start'
        )
        self.next_target_client = self.create_client(
            Trigger, '/cotton_detection/next_target'
        )
        self.vacuum_on_client = self.create_client(
            Trigger, '/yanthra_move/vacuum_on'
        )
        self.vacuum_off_client = self.create_client(
            Trigger, '/yanthra_move/vacuum_off'
        )
        
        # State variables
        self.current_joint_positions = []
        self.current_cotton_target = None
        self.picking_stats = {
            'attempted': 0,
            'successful': 0,
            'failed': 0
        }
        
        self.get_logger().info('Integrated Picking Example Node Started')
    
    def joint_state_callback(self, msg):
        """Update current joint positions."""
        self.current_joint_positions = list(msg.position)
    
    def detection_callback(self, msg):
        """Update current cotton target."""
        self.current_cotton_target = msg
    
    def call_service(self, client, request):
        """Generic service call helper."""
        if not client.wait_for_service(timeout_sec=2.0):
            self.get_logger().error(f'Service {client.srv_name} not available')
            return None
        
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        return future.result()
    
    def send_joint_command(self, positions):
        """Send joint position command."""
        msg = Float64MultiArray()
        msg.data = positions
        self.joint_cmd_pub.publish(msg)
    
    def wait_for_position(self, target, tolerance=0.05, timeout=10.0):
        """Wait for joints to reach target position."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if not self.current_joint_positions:
                rclpy.spin_once(self, timeout_sec=0.1)
                continue
            
            errors = [
                abs(t - c) 
                for t, c in zip(target, self.current_joint_positions)
            ]
            
            if all(e < tolerance for e in errors):
                return True
            
            rclpy.spin_once(self, timeout_sec=0.1)
        
        return False
    
    def cotton_to_joint_positions(self, cotton_point):
        """Convert cotton coordinates to joint positions.
        
        This is a simplified example. Real implementation would use
        inverse kinematics or the yanthra_move service.
        
        Args:
            cotton_point: Point message with X, Y, Z coordinates
        
        Returns:
            List of joint positions (radians)
        """
        # Simple geometric IK (example only - not accurate)
        x, y, z = cotton_point.x, cotton_point.y, cotton_point.z
        
        # Calculate joint angles (simplified)
        # This would be replaced with proper IK
        joint1 = math.atan2(y, x)  # Base rotation
        reach = math.sqrt(x**2 + y**2)
        joint2 = math.atan2(z, reach)  # Shoulder
        joint3 = -joint2  # Elbow (simplified)
        
        return [joint1, joint2, joint3]
    
    def execute_pick(self, cotton_point):
        """Execute complete pick operation.
        
        Args:
            cotton_point: Target cotton coordinates
        
        Returns:
            True if successful, False otherwise
        """
        self.picking_stats['attempted'] += 1
        
        try:
            # Step 1: Convert to joint positions
            self.get_logger().info(
                f'Target: ({cotton_point.x:.3f}, {cotton_point.y:.3f}, '
                f'{cotton_point.z:.3f})'
            )
            
            target_joints = self.cotton_to_joint_positions(cotton_point)
            self.get_logger().info(
                f'Computed joint angles: {[f"{j:.3f}" for j in target_joints]}'
            )
            
            # Step 2: Move to approach position (above target)
            self.get_logger().info('  -> Moving to approach position')
            approach_joints = target_joints.copy()
            approach_joints[2] += 0.2  # Offset for approach
            
            self.send_joint_command(approach_joints)
            if not self.wait_for_position(approach_joints, timeout=5.0):
                self.get_logger().error('Failed to reach approach position')
                self.picking_stats['failed'] += 1
                return False
            
            time.sleep(0.5)
            
            # Step 3: Move to pick position
            self.get_logger().info('  -> Moving to pick position')
            self.send_joint_command(target_joints)
            if not self.wait_for_position(target_joints, timeout=5.0):
                self.get_logger().error('Failed to reach pick position')
                self.picking_stats['failed'] += 1
                return False
            
            time.sleep(0.3)
            
            # Step 4: Activate vacuum
            self.get_logger().info('  -> Activating vacuum')
            response = self.call_service(
                self.vacuum_on_client, Trigger.Request()
            )
            if not response or not response.success:
                self.get_logger().warn('Vacuum activation failed (may not be implemented)')
            
            time.sleep(0.5)
            
            # Step 5: Retract to approach position
            self.get_logger().info('  -> Retracting')
            self.send_joint_command(approach_joints)
            self.wait_for_position(approach_joints, timeout=5.0)
            
            time.sleep(0.3)
            
            # Step 6: Move to deposit position
            self.get_logger().info('  -> Moving to deposit')
            deposit_joints = [0.0, -0.5, 0.5]  # Example deposit position
            self.send_joint_command(deposit_joints)
            self.wait_for_position(deposit_joints, timeout=5.0)
            
            time.sleep(0.3)
            
            # Step 7: Release vacuum
            self.get_logger().info('  -> Releasing')
            response = self.call_service(
                self.vacuum_off_client, Trigger.Request()
            )
            
            time.sleep(0.3)
            
            # Step 8: Return to home
            self.get_logger().info('  -> Returning home')
            home_joints = [0.0, 0.0, 0.0]
            self.send_joint_command(home_joints)
            self.wait_for_position(home_joints, timeout=5.0)
            
            self.get_logger().info('  -> Pick complete!')
            self.picking_stats['successful'] += 1
            return True
            
        except Exception as e:
            self.get_logger().error(f'Pick operation failed: {e}')
            self.picking_stats['failed'] += 1
            return False
    
    def run_picking_cycle(self, max_cotton=10):
        """Run complete picking cycle.
        
        Args:
            max_cotton: Maximum number of cotton to pick
        """
        self.get_logger().info(f'\n=== Starting Picking Cycle (max {max_cotton}) ===\n')
        
        # Start detection
        response = self.call_service(
            self.start_detection_client, Trigger.Request()
        )
        if not response or not response.success:
            self.get_logger().error('Failed to start detection')
            return
        
        time.sleep(1.0)
        
        # Process cotton sequentially
        for i in range(max_cotton):
            # Get next target
            response = self.call_service(
                self.next_target_client, Trigger.Request()
            )
            
            if not response or not response.success:
                self.get_logger().info('No more cotton targets available')
                break
            
            # Wait for detection result
            self.current_cotton_target = None
            start_time = time.time()
            
            while time.time() - start_time < 5.0:
                rclpy.spin_once(self, timeout_sec=0.1)
                if self.current_cotton_target is not None:
                    break
            
            if self.current_cotton_target is None:
                self.get_logger().warn('Detection timeout')
                continue
            
            # Execute pick
            self.get_logger().info(f'\n--- Cotton {i+1}/{max_cotton} ---')
            self.execute_pick(self.current_cotton_target)
            
            time.sleep(0.5)
        
        # Print statistics
        self.get_logger().info('\n=== Picking Cycle Complete ===')
        self.get_logger().info(f'Attempted: {self.picking_stats["attempted"]}')
        self.get_logger().info(f'Successful: {self.picking_stats["successful"]}')
        self.get_logger().info(f'Failed: {self.picking_stats["failed"]}')
        
        success_rate = (
            100.0 * self.picking_stats['successful'] / 
            self.picking_stats['attempted']
            if self.picking_stats['attempted'] > 0 else 0
        )
        self.get_logger().info(f'Success Rate: {success_rate:.1f}%')


def main():
    rclpy.init()
    node = IntegratedPickingExample()
    
    try:
        # Wait for initialization
        node.get_logger().info('Waiting for system initialization...')
        time.sleep(2.0)
        
        # Run picking cycle
        node.run_picking_cycle(max_cotton=5)
        
    except KeyboardInterrupt:
        node.get_logger().info('Interrupted by user')
    
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
