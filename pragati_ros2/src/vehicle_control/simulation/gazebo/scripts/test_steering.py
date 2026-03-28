#!/usr/bin/env python3
"""
Test script for vehicle_control steering kinematics.
Tests various movement patterns to verify proper steering behavior.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import time


class SteeringTester(Node):
    def __init__(self):
        super().__init__('steering_tester')
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.get_logger().info('Steering tester initialized')

    def send_cmd(self, vx=0.0, vy=0.0, omega=0.0, duration=3.0):
        """Send velocity command for specified duration"""
        twist = Twist()
        twist.linear.x = vx
        twist.linear.y = vy
        twist.angular.z = omega

        self.get_logger().info(f'Sending: vx={vx:.2f}, vy={vy:.2f}, omega={omega:.2f} for {duration}s')

        start_time = time.time()
        while (time.time() - start_time) < duration:
            self.publisher.publish(twist)
            time.sleep(0.05)

    def stop(self):
        """Send stop command"""
        twist = Twist()
        self.publisher.publish(twist)
        self.get_logger().info('STOPPED')


def main():
    rclpy.init()
    tester = SteeringTester()

    try:
        tester.get_logger().info("=== VEH1 STEERING TEST SEQUENCE ===")

        # Test 1: Forward motion
        tester.get_logger().info("Test 1: Forward motion (should drive straight)")
        tester.send_cmd(vx=0.5, duration=3.0)
        tester.stop()
        time.sleep(2.0)

        # Test 2: Turn in place (rotation only)
        tester.get_logger().info(
            "Test 2: Turn in place (rear wheels should pivot)"
        )
        tester.send_cmd(omega=0.3, duration=3.0)
        tester.stop()
        time.sleep(2.0)

        # Test 3: Forward + turn (ackermann steering)
        tester.get_logger().info(
            "Test 3: Forward + turn left (ackermann steering)"
        )
        tester.send_cmd(vx=0.5, omega=0.3, duration=3.0)
        tester.stop()
        time.sleep(2.0)

        # Test 4: Lateral motion
        tester.get_logger().info("Test 4: Lateral motion (crab walk)")
        tester.send_cmd(vy=0.3, duration=3.0)
        tester.stop()
        time.sleep(2.0)

        # Test 5: Diagonal motion
        tester.get_logger().info("Test 5: Diagonal motion")
        tester.send_cmd(vx=0.3, vy=0.3, duration=3.0)
        tester.stop()

        tester.get_logger().info("=== TEST SEQUENCE COMPLETE ===")

    except KeyboardInterrupt:
        tester.get_logger().warn("Test interrupted")
    finally:
        tester.stop()
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
