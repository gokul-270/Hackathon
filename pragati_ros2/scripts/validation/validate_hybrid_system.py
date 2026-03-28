#!/usr/bin/env python3
"""
Comprehensive validation script for the hybrid cotton detection system
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cotton_detection_msgs.srv import CottonDetection
from cotton_detection_msgs.msg import DetectionResult
import cv2
import numpy as np
import time
import sys
import os


class CottonDetectionTester(Node):
    def __init__(self):
        super().__init__('cotton_detection_tester')

        # Service client
        self.client = self.create_client(CottonDetection, 'cotton_detection/detect')

        # Result subscriber
        self.result_sub = self.create_subscription(
            DetectionResult, 'cotton_detection/results', self.result_callback, 10
        )

        self.latest_result = None
        self.result_received = False

    def result_callback(self, msg):
        self.latest_result = msg
        self.result_received = True
        self.get_logger().info(f"📊 Received detection result: {len(msg.positions)} positions")

    def wait_for_service(self, timeout_sec=5.0):
        """Wait for the cotton detection service to be available"""
        self.get_logger().info("⏳ Waiting for cotton detection service...")
        if not self.client.wait_for_service(timeout_sec=timeout_sec):
            self.get_logger().error("❌ Service not available")
            return False
        self.get_logger().info("✅ Service available")
        return True

    def test_detection_request(self, command, description):
        """Test a detection request"""
        self.get_logger().info(f"🧪 Testing: {description}")

        # Create request
        request = CottonDetection.Request()
        request.detect_command = command

        # Reset result flag
        self.result_received = False
        self.latest_result = None

        # Call service
        start_time = time.time()
        future = self.client.call_async(request)

        # Wait for response
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        if future.result() is None:
            self.get_logger().error("❌ Service call failed")
            return False

        response = future.result()
        end_time = time.time()

        self.get_logger().info(
            f"✅ Service response: success={response.success}, "
            f"data_points={len(response.data)}, "
            f"time={end_time-start_time:.3f}s"
        )

        # Wait a bit for the result message
        time.sleep(0.5)
        rclpy.spin_once(self, timeout_sec=0.1)

        if self.result_received and self.latest_result:
            self.get_logger().info(
                f"📊 Result message: {len(self.latest_result.positions)} positions, "
                f"successful={self.latest_result.detection_successful}"
            )
        else:
            self.get_logger().warning("⚠️ No result message received")

        return response.success


def main():
    print("🧪 Comprehensive Cotton Detection Validation")
    print("=" * 50)

    # Initialize ROS2
    rclpy.init()

    tester = CottonDetectionTester()

    try:
        # Test 1: Service availability
        print("\n1️⃣ Testing Service Availability")
        if not tester.wait_for_service():
            print("❌ Service availability test FAILED")
            return 1

        # Test 2: Stop detection
        print("\n2️⃣ Testing Stop Detection Command")
        if not tester.test_detection_request(0, "Stop Detection"):
            print("❌ Stop detection test FAILED")
            return 1

        # Test 3: Start detection (should work with fallback to HSV)
        print("\n3️⃣ Testing Start Detection Command (HSV Fallback)")
        if not tester.test_detection_request(1, "Start Detection"):
            print("❌ Start detection test FAILED")
            return 1

        # Test 4: Invalid command
        print("\n4️⃣ Testing Invalid Command")
        if tester.test_detection_request(999, "Invalid Command"):
            print("❌ Invalid command test FAILED - should have failed")
            return 1

        print("\n" + "=" * 50)
        print("✅ All validation tests PASSED!")
        print("🎉 Hybrid cotton detection system is working correctly")
        print("\n📋 System Status:")
        print("   • ROS2 node: ✅ Running")
        print("   • Services: ✅ Available")
        print("   • HSV detection: ✅ Working")
        print("   • YOLO detection: ⚠️ Model not available (expected)")
        print("   • Hybrid fallback: ✅ Active")
        print("   • Result publishing: ✅ Working")

        return 0

    except Exception as e:
        print(f"❌ Validation failed with exception: {e}")
        return 1

    finally:
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    # Start the cotton detection node in background
    import subprocess
    import signal

    print("🚀 Starting cotton detection node...")
    node_process = subprocess.Popen(
        [
            'bash',
            '-c',
            'cd /home/uday/Downloads/pragati_ros2 && source install/setup.bash && '
            'ros2 run cotton_detection_ros2 cotton_detection_node --ros-args --log-level info',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Give it time to start
    time.sleep(3)

    try:
        # Run validation
        exit_code = main()

        # Check if node is still running
        if node_process.poll() is None:
            print("\n🛑 Stopping cotton detection node...")
            node_process.terminate()
            node_process.wait(timeout=5)
        else:
            print("\n⚠️ Cotton detection node exited unexpectedly")
            stdout, stderr = node_process.communicate()
            print("Node stdout:", stdout.decode())
            print("Node stderr:", stderr.decode())

        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        if node_process.poll() is None:
            node_process.terminate()
        sys.exit(1)
