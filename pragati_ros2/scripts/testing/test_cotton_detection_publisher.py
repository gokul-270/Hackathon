#!/usr/bin/env python3
"""
Test script to publish fake cotton detection points to yanthra_move.
This validates the motor_controller integration without needing a camera.

Usage:
    python3 test_cotton_detection_publisher.py --single    # Publish one detection
    python3 test_cotton_detection_publisher.py --continuous # Publish continuously
    python3 test_cotton_detection_publisher.py --custom x y z  # Custom position
"""

import rclpy
from rclpy.node import Node
from cotton_detection_msgs.msg import DetectionResult, CottonPosition
from geometry_msgs.msg import Point
from std_msgs.msg import Header
import argparse
import time


class CottonDetectionPublisher(Node):
    def __init__(self):
        super().__init__('cotton_detection_test_publisher')

        # Publisher to the topic that yanthra_move subscribes to
        self.publisher = self.create_publisher(DetectionResult, '/cotton_detection/results', 10)

        self.get_logger().info('🌱 Cotton Detection Test Publisher initialized')
        self.get_logger().info('   Publishing to: /cotton_detection/results')

    def publish_detection(self, positions_list):
        """
        Publish a detection result with the given positions.

        Args:
            positions_list: List of (x, y, z) tuples representing cotton positions
        """
        msg = DetectionResult()

        # Set header with current timestamp
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_link'

        # Add cotton positions
        for x, y, z in positions_list:
            cotton_pos = CottonPosition()
            cotton_pos.position = Point(x=float(x), y=float(y), z=float(z))
            cotton_pos.confidence = 0.95  # High confidence
            msg.positions.append(cotton_pos)

        msg.total_count = len(msg.positions)
        msg.detection_successful = True
        msg.processing_time_ms = 2.0  # Fake processing time

        # Publish the message
        self.publisher.publish(msg)

        self.get_logger().info(
            f'📤 Published detection with {len(positions_list)} cotton position(s):'
        )
        for i, (x, y, z) in enumerate(positions_list):
            self.get_logger().info(f'   Cotton[{i}]: ({x:.3f}, {y:.3f}, {z:.3f})')


def main():
    parser = argparse.ArgumentParser(description='Publish fake cotton detection for testing')
    parser.add_argument('--single', action='store_true', help='Publish a single detection and exit')
    parser.add_argument(
        '--continuous', action='store_true', help='Publish continuously every 2 seconds'
    )
    parser.add_argument(
        '--custom',
        nargs=3,
        type=float,
        metavar=('X', 'Y', 'Z'),
        help='Publish custom position (X Y Z in meters)',
    )
    parser.add_argument(
        '--count', type=int, default=3, help='Number of cotton positions to publish (default: 3)'
    )
    parser.add_argument(
        '--rate',
        type=float,
        default=2.0,
        help='Publishing rate in Hz for continuous mode (default: 2.0)',
    )

    args = parser.parse_args()

    rclpy.init()
    node = CottonDetectionPublisher()

    try:
        # Define some test positions (in camera frame, meters)
        # These are realistic positions for cotton picking
        test_positions = [
            (0.3, 0.1, 0.5),  # Cotton 1: 30cm forward, 10cm right, 50cm up
            (0.25, -0.05, 0.45),  # Cotton 2: 25cm forward, 5cm left, 45cm up
            (0.35, 0.0, 0.55),  # Cotton 3: 35cm forward, center, 55cm up
        ]

        if args.custom:
            # Custom single position
            positions = [(args.custom[0], args.custom[1], args.custom[2])]
            node.get_logger().info('🎯 Publishing custom position')
            node.publish_detection(positions)
            time.sleep(0.5)  # Give time for message to be sent

        elif args.single:
            # Single detection with multiple cotton positions
            positions = test_positions[: args.count]
            node.get_logger().info(
                f'🎯 Publishing single detection with {len(positions)} positions'
            )
            node.publish_detection(positions)
            time.sleep(0.5)  # Give time for message to be sent

        elif args.continuous:
            # Continuous publishing
            node.get_logger().info(f'🔄 Starting continuous publishing at {args.rate} Hz')
            node.get_logger().info('   Press Ctrl+C to stop')

            rate = node.create_rate(args.rate)

            while rclpy.ok():
                positions = test_positions[: args.count]
                node.publish_detection(positions)
                rate.sleep()
        else:
            # Default: publish once
            node.get_logger().info(
                '🎯 No mode specified, publishing single detection (use --help for options)'
            )
            positions = test_positions[: args.count]
            node.publish_detection(positions)
            time.sleep(0.5)

    except KeyboardInterrupt:
        node.get_logger().info('🛑 Interrupted by user')
    finally:
        node.destroy_node()
        rclpy.shutdown()
        print('✅ Publisher shutdown complete')


if __name__ == '__main__':
    main()
