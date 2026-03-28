#!/usr/bin/env python3
"""
Fake Cotton Detection Publisher
Publishes synthetic cotton detections for testing without camera
Run this BEFORE launching the main system or in parallel
"""

import rclpy
from rclpy.node import Node
from cotton_detection_msgs.msg import DetectionResult, CottonPosition
from geometry_msgs.msg import Point
from std_msgs.msg import Header


class FakeCottonPublisher(Node):
    def __init__(self):
        super().__init__('fake_cotton_publisher')

        self.publisher = self.create_publisher(DetectionResult, '/cotton_detection/results', 10)

        # Publish at 1 Hz (continuous)
        self.timer = self.create_timer(1.0, self.publish_detection)

        self.get_logger().info('Fake cotton detection publisher started')
        self.get_logger().info('Publishing to: /cotton_detection/results at 1 Hz')
        self.get_logger().info('Press Ctrl+C to stop')

    def publish_detection(self):
        """Publish a fake cotton detection"""
        msg = DetectionResult()

        # Header with current time
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_link'

        # Create cotton position in reachable workspace
        # X: forward (0.3m), Y: sideways (0.0m), Z: height (0.5m)
        cotton = CottonPosition()
        cotton.position = Point()
        cotton.position.x = 0.3  # 30cm forward
        cotton.position.y = 0.0  # Centered
        cotton.position.z = 0.5  # 50cm height
        cotton.confidence = 0.95
        cotton.detection_id = 1
        cotton.header = msg.header

        # Build message
        msg.positions = [cotton]
        msg.total_count = 1
        msg.detection_successful = True
        msg.processing_time_ms = 10.0

        # Publish
        self.publisher.publish(msg)
        self.get_logger().info(
            f'Published cotton at ({cotton.position.x:.2f}, {cotton.position.y:.2f}, {cotton.position.z:.2f})'
        )


def main(args=None):
    rclpy.init(args=args)

    print("=" * 60)
    print("Fake Cotton Detection Publisher")
    print("=" * 60)
    print("")
    print("This will continuously publish fake cotton detections")
    print("at position (0.3, 0.0, 0.5) meters")
    print("")
    print("Flow:")
    print("  1. This script publishes detections continuously")
    print("  2. Launch main system in another terminal")
    print("  3. System waits for start switch")
    print("  4. Send start switch signal")
    print("  5. System reads these detections and picks cotton")
    print("")
    print("=" * 60)
    print("")

    node = FakeCottonPublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\nStopping fake cotton publisher...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
