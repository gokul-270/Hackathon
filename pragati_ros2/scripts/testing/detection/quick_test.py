#!/usr/bin/env python3
"""Quick test client for cotton detection service - measures actual latency"""

import rclpy
from rclpy.node import Node
from cotton_detection_msgs.srv import CottonDetection
import time


class QuickDetectionTest(Node):
    def __init__(self):
        super().__init__('quick_detection_test')
        self.client = self.create_client(CottonDetection, '/cotton_detection/detect')

    def test_detection(self):
        if not self.client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('Service not available')
            return None

        request = CottonDetection.Request()
        request.detect_command = 1

        start = time.time()
        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=15.0)
        end = time.time()

        if future.result() is not None:
            response = future.result()
            latency_ms = (end - start) * 1000
            self.get_logger().info(f'✅ Detection completed in {latency_ms:.1f} ms')
            self.get_logger().info(f'   Success: {response.success}')
            self.get_logger().info(f'   Data points: {len(response.data)}')
            self.get_logger().info(f'   Message: {response.message}')
            return latency_ms
        else:
            self.get_logger().error('Service call failed')
            return None


def main():
    rclpy.init()
    node = QuickDetectionTest()

    print('\n=== Quick Detection Latency Test ===\n')

    # Run 3 tests
    latencies = []
    for i in range(3):
        print(f'Test {i+1}/3...')
        latency = node.test_detection()
        if latency:
            latencies.append(latency)
        time.sleep(0.5)

    if latencies:
        print(f'\n=== Results ===')
        print(f'Average latency: {sum(latencies)/len(latencies):.1f} ms')
        print(f'Min: {min(latencies):.1f} ms, Max: {max(latencies):.1f} ms')

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
