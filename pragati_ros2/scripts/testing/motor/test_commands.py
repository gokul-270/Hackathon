#!/usr/bin/env python3
"""Test motor commands with proper ROS2 context management"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
from std_srvs.srv import Trigger
import time

class MotorCommandTester(Node):
    def __init__(self):
        super().__init__('motor_command_tester')
        
        # Create publishers for all joints
        self.pub_j3 = self.create_publisher(Float64, '/joint3_position_controller/command', 10)
        self.pub_j4 = self.create_publisher(Float64, '/joint4_position_controller/command', 10)
        self.pub_j5 = self.create_publisher(Float64, '/joint5_position_controller/command', 10)
        
        # Create service client for enabling motors
        self.enable_motors_cli = self.create_client(Trigger, '/enable_motors')
        
        # Wait for publishers to connect
        time.sleep(0.5)
        
        self.get_logger().info('Motor command tester ready')
    
    def enable_motors(self):
        """Enable all motors via service call"""
        self.get_logger().info('Waiting for enable_motors service...')
        while not self.enable_motors_cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Service not available, waiting...')
        
        request = Trigger.Request()
        future = self.enable_motors_cli.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        
        if future.result() is not None:
            response = future.result()
            if response.success:
                self.get_logger().info('✅ Motors enabled successfully')
                return True
            else:
                self.get_logger().error(f'Failed to enable motors: {response.message}')
                return False
        else:
            self.get_logger().error('Service call failed')
            return False
    
    def send_command(self, joint_name, value):
        """Send position command to specified joint"""
        msg = Float64()
        msg.data = value
        
        timestamp = time.strftime('%H:%M:%S')
        self.get_logger().info(f'[{timestamp}] Commanding {joint_name} to {value} rad')
        
        if joint_name == 'joint3':
            self.pub_j3.publish(msg)
        elif joint_name == 'joint4':
            self.pub_j4.publish(msg)
        elif joint_name == 'joint5':
            self.pub_j5.publish(msg)
        
        # Give time for command to be sent
        time.sleep(0.1)

def main():
    rclpy.init()
    
    node = MotorCommandTester()
    
    print("\n" + "="*50)
    print("MOTOR COMMAND TEST")
    print("Testing all 3 joints with 0.1 rad")
    print("="*50 + "\n")
    
    try:
        # First, enable motors
        print("[0/3] Enabling motors...")
        if not node.enable_motors():
            print("ERROR: Failed to enable motors. Exiting.")
            return
        print("")
        
        # Test all joints with same value
        test_value = 0.1
        
        print(f"[1/3] Sending Joint3 command: {test_value} rad")
        node.send_command('joint3', test_value)
        print("  Waiting 4s for movement...")
        time.sleep(4)
        
        print(f"\n[2/3] Sending Joint4 command: {test_value} rad")
        node.send_command('joint4', test_value)
        print("  Waiting 4s for movement...")
        time.sleep(4)
        
        print(f"\n[3/3] Sending Joint5 command: {test_value} rad")
        node.send_command('joint5', test_value)
        print("  Waiting 4s for movement...")
        time.sleep(4)
        
        print("\n" + "="*50)
        print("All commands sent successfully!")
        print("="*50 + "\n")
        
    except KeyboardInterrupt:
        print("\nTest interrupted")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
