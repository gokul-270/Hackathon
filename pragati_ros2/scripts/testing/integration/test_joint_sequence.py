#!/usr/bin/env python3
"""
Test script for motor sequence validation
Moves joints in two different sequences to test both directions:
  Sequence 1 (Left):  J4=+0.05, J3=-0.03, J5=0.08
  Sequence 2 (Right): J4=-0.05, J3=-0.03, J5=0.08
Useful for testing CAN bus stability and motor reliability

Usage:
    python3 scripts/test_joint_sequence.py [iterations]
    
    Default: 10 iterations
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
import time
import sys

class JointSequenceTester(Node):
    def __init__(self, iterations=10):
        super().__init__('joint_sequence_tester')
        
        # Create publishers for each joint
        self.joint4_pub = self.create_publisher(Float64, '/joint4_position_controller/command', 10)
        self.joint3_pub = self.create_publisher(Float64, '/joint3_position_controller/command', 10)
        self.joint5_pub = self.create_publisher(Float64, '/joint5_position_controller/command', 10)
        
        # Target positions (radians)
        # Sequence 1: Left side
        self.joint4_left = 0.05    # ~2.86 degrees
        # Sequence 2: Right side
        self.joint4_right = -0.05  # ~-2.86 degrees
        # Common positions
        self.joint3_target = -0.1 # ~-1.72 degrees (negative direction)
        self.joint5_target = 0.08  # ~4.58 degrees
        
        # Test configuration
        self.iterations = iterations
        self.delay_before_homing = 2.0   # seconds - wait for motors to reach target
        self.delay_after_sequence = 2.0  # seconds - wait after sequence completes
        
        self.get_logger().info('Joint Sequence Tester initialized')
        self.get_logger().info(f'Sequence 1 (Left):  J4={self.joint4_left}, J3={self.joint3_target}, J5={self.joint5_target}')
        self.get_logger().info(f'Sequence 2 (Right): J4={self.joint4_right}, J3={self.joint3_target}, J5={self.joint5_target}')
        self.get_logger().info(f'Iterations: {self.iterations}')
        self.get_logger().info(f'Delay before homing: {self.delay_before_homing}s, after sequence: {self.delay_after_sequence}s')
        self.get_logger().info('⚡ Rapid fire mode: No delay between commands!')
        
        # Wait for publishers to be ready
        time.sleep(1.0)
    
    def send_command(self, publisher, joint_name, position):
        """Send position command to a joint"""
        msg = Float64()
        msg.data = position
        publisher.publish(msg)
        self.get_logger().info(f'{joint_name}: {position:.4f} rad ({position * 57.2958:.2f}°)')
    
    def run_sequence(self):
        """Run the complete test sequence"""
        self.get_logger().info('='*60)
        self.get_logger().info('Starting Joint Sequence Test')
        self.get_logger().info('='*60)
        
        try:
            for iteration in range(1, self.iterations + 1):
                self.get_logger().info('')
                self.get_logger().info(f'>>> ITERATION {iteration}/{self.iterations} <<<')
                self.get_logger().info('='*60)
                
                # ========== SEQUENCE 1: LEFT SIDE ==========
                self.get_logger().info('[SEQUENCE 1 - LEFT] Moving to target positions...')
                self.get_logger().info('-'*60)
                
                self.send_command(self.joint4_pub, 'Joint4', self.joint4_left)
                self.send_command(self.joint3_pub, 'Joint3', self.joint3_target)
                self.send_command(self.joint5_pub, 'Joint5', self.joint5_target)
                
                # Wait for motors to reach target
                time.sleep(self.delay_before_homing)
                
                self.get_logger().info('[SEQUENCE 1 - LEFT] Returning to zero...')
                
                self.send_command(self.joint5_pub, 'Joint5', 0.0)
                self.send_command(self.joint3_pub, 'Joint3', 0.0)
                self.send_command(self.joint4_pub, 'Joint4', 0.0)
                
                # Wait after sequence completes
                time.sleep(self.delay_after_sequence)
                
                # ========== SEQUENCE 2: RIGHT SIDE ==========
                self.get_logger().info('[SEQUENCE 2 - RIGHT] Moving to target positions...')
                self.get_logger().info('-'*60)
                
                self.send_command(self.joint4_pub, 'Joint4', self.joint4_right)
                self.send_command(self.joint3_pub, 'Joint3', self.joint3_target)
                self.send_command(self.joint5_pub, 'Joint5', self.joint5_target)
                
                # Wait for motors to reach target
                time.sleep(self.delay_before_homing)
                
                self.get_logger().info('[SEQUENCE 2 - RIGHT] Returning to zero...')
                
                self.send_command(self.joint5_pub, 'Joint5', 0.0)
                self.send_command(self.joint3_pub, 'Joint3', 0.0)
                self.send_command(self.joint4_pub, 'Joint4', 0.0)
                
                # Wait after sequence completes
                time.sleep(self.delay_after_sequence)
                
                self.get_logger().info(f'✅ Iteration {iteration} complete!')
            
            self.get_logger().info('')
            self.get_logger().info('='*60)
            self.get_logger().info(f'✅ Test Complete! Successfully ran {self.iterations} iterations')
            self.get_logger().info(f'   Total commands sent: {self.iterations * 12}')
            self.get_logger().info('='*60)
            
        except KeyboardInterrupt:
            self.get_logger().warn('Test interrupted by user')
            self.get_logger().info('Returning all joints to zero...')
            self.send_command(self.joint5_pub, 'Joint5', 0.0)
            time.sleep(0.1)
            self.send_command(self.joint3_pub, 'Joint3', 0.0)
            time.sleep(0.1)
            self.send_command(self.joint4_pub, 'Joint4', 0.0)
            time.sleep(1.0)
            self.get_logger().info('Emergency stop complete')
        
        except Exception as e:
            self.get_logger().error(f'Error during test: {e}')
            raise

def main(args=None):
    # Parse command line arguments
    iterations = 10  # Default
    if len(sys.argv) > 1:
        try:
            iterations = int(sys.argv[1])
            if iterations < 1:
                print("Error: Iterations must be >= 1")
                sys.exit(1)
        except ValueError:
            print(f"Error: Invalid iterations value '{sys.argv[1]}'. Must be an integer.")
            print(f"Usage: {sys.argv[0]} [iterations]")
            sys.exit(1)
    
    rclpy.init(args=args)
    
    tester = JointSequenceTester(iterations=iterations)
    
    try:
        tester.run_sequence()
    finally:
        tester.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
