#!/usr/bin/env python3
"""
Direct Python client to measure ACTUAL service latency
This eliminates CLI tool overhead
"""

import rclpy
from rclpy.node import Node
from cotton_detection_msgs.srv import CottonDetection
import time


class LatencyTester(Node):
    def __init__(self):
        super().__init__('latency_tester')
        self.client = self.create_client(CottonDetection, '/cotton_detection/detect')

        # Wait for service to be available
        print("Waiting for service...")
        if not self.client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('Service not available!')
            return
        print("✅ Service found\n")

    def test_latency(self, num_tests=5):
        print(f"Testing service latency ({num_tests} calls)...")
        print("=" * 50)

        latencies = []

        for i in range(num_tests):
            request = CottonDetection.Request()
            request.detect_command = 1

            start = time.time()
            future = self.client.call_async(request)

            # Wait for response
            rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)

            end = time.time()
            latency_ms = (end - start) * 1000

            if future.done():
                response = future.result()
                status = "✅" if response.success else "❌"
                print(f"Test {i+1}: {latency_ms:.0f}ms {status}")
                latencies.append(latency_ms)
            else:
                print(f"Test {i+1}: TIMEOUT ❌")

            time.sleep(0.5)  # Small delay between tests

        print("=" * 50)
        if latencies:
            avg = sum(latencies) / len(latencies)
            print(f"\nAverage latency: {avg:.0f}ms")
            print(f"Min: {min(latencies):.0f}ms")
            print(f"Max: {max(latencies):.0f}ms")

            if avg < 500:
                print("\n✅ EXCELLENT: Production-ready!")
            elif avg < 1000:
                print("\n✅ GOOD: Acceptable")
            elif avg < 3000:
                print("\n⚠️  MODERATE: Needs improvement")
            else:
                print("\n❌ POOR: Serious issue detected")
        else:
            print("\n❌ All tests failed!")


def main():
    rclpy.init()

    tester = LatencyTester()
    tester.test_latency(num_tests=5)

    tester.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
