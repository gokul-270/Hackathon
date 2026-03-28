#!/usr/bin/env python3
"""
Direct test of steering topics - manually publish angles to see which wheels respond
"""
import math
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64


class SteeringTester(Node):
    def __init__(self):
        super().__init__("steering_tester")

        self.front_pub = self.create_publisher(Float64, "/steering/front", 10)
        self.left_pub = self.create_publisher(Float64, "/steering/left", 10)
        self.right_pub = self.create_publisher(Float64, "/steering/right", 10)

        self.get_logger().info("Steering tester ready")

    def test_all_wheels(self, angle_deg):
        """Send same angle to all wheels"""
        angle_rad = math.radians(angle_deg)

        msg = Float64()
        msg.data = angle_rad

        self.get_logger().info(f"\n=== Testing all wheels at {angle_deg}° ===")
        self.front_pub.publish(msg)
        self.left_pub.publish(msg)
        self.right_pub.publish(msg)
        self.get_logger().info(f"Published {angle_deg}° to front, left, and right")


def main():
    rclpy.init()
    tester = SteeringTester()

    time.sleep(2)

    # Test sequence
    tester.get_logger().info("Starting steering test in 2 seconds...")
    time.sleep(2)

    # Test 1: All wheels to +45°
    tester.test_all_wheels(45.0)
    time.sleep(3)

    # Test 2: All wheels to -45°
    tester.test_all_wheels(-45.0)
    time.sleep(3)

    # Test 3: All wheels to 0°
    tester.test_all_wheels(0.0)
    time.sleep(2)

    tester.get_logger().info("Test complete - check which wheels moved in Gazebo")

    tester.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
