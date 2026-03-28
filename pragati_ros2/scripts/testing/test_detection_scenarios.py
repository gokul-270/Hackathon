#!/usr/bin/env python3
"""
Test Scenarios for Simulated Cotton Detection
Demonstrates common testing patterns for yanthra_move integration
"""

import rclpy
from rclpy.node import Node
from cotton_detection_msgs.msg import DetectionResult, CottonPosition
from geometry_msgs.msg import Point
from std_msgs.msg import Header
import time
import math
import argparse


class ScenarioTester(Node):
    def __init__(self):
        super().__init__('scenario_tester')
        self.publisher = self.create_publisher(DetectionResult, '/cotton_detection/results', 10)
        self.get_logger().info('🎬 Scenario Tester initialized')

    def publish_detection(self, positions, description=""):
        """Publish a detection with given positions"""
        msg = DetectionResult()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_link'

        for x, y, z, conf in positions:
            cotton_pos = CottonPosition()
            cotton_pos.position = Point(x=float(x), y=float(y), z=float(z))
            cotton_pos.confidence = float(conf)
            msg.positions.append(cotton_pos)

        msg.total_count = len(msg.positions)
        msg.detection_successful = True
        msg.processing_time_ms = 2.0

        self.publisher.publish(msg)

        if description:
            self.get_logger().info(f'📤 {description}')
        self.get_logger().info(f'   Published {len(positions)} position(s)')
        for i, (x, y, z, conf) in enumerate(positions):
            self.get_logger().info(f'   Cotton[{i}]: ({x:.3f}, {y:.3f}, {z:.3f}) conf={conf:.2f}')

    # =========================================================================
    # SCENARIO 1: Progressive Load Test
    # =========================================================================
    def scenario_progressive_load(self):
        """Test with increasing number of cotton positions"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 1: Progressive Load Test')
        self.get_logger().info('=' * 60)

        base_pos = (0.3, 0.0, 0.5, 0.95)

        for count in [1, 3, 5, 10]:
            positions = []
            for i in range(count):
                # Spread positions in Y and Z
                offset_y = (i % 5) * 0.05 - 0.1  # -0.1 to +0.1
                offset_z = (i // 5) * 0.05
                positions.append(
                    (base_pos[0], base_pos[1] + offset_y, base_pos[2] + offset_z, base_pos[3])
                )

            self.publish_detection(positions, f'Load Test: {count} cotton positions')
            time.sleep(3)

    # =========================================================================
    # SCENARIO 2: Workspace Boundary Test
    # =========================================================================
    def scenario_workspace_boundaries(self):
        """Test positions at workspace boundaries"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 2: Workspace Boundary Test')
        self.get_logger().info('=' * 60)

        test_cases = [
            ([(0.2, 0.0, 0.4, 0.95)], "Close position"),
            ([(0.5, 0.0, 0.6, 0.95)], "Far position"),
            ([(0.3, -0.25, 0.5, 0.95)], "Far left"),
            ([(0.3, 0.25, 0.5, 0.95)], "Far right"),
            ([(0.3, 0.0, 0.35, 0.95)], "Low height"),
            ([(0.3, 0.0, 0.7, 0.95)], "High height"),
        ]

        for positions, description in test_cases:
            self.publish_detection(positions, description)
            time.sleep(3)

    # =========================================================================
    # SCENARIO 3: Confidence Variation Test
    # =========================================================================
    def scenario_confidence_variation(self):
        """Test with varying detection confidence levels"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 3: Confidence Variation Test')
        self.get_logger().info('=' * 60)

        # Same position, different confidences
        base_pos = (0.3, 0.0, 0.5)

        for confidence in [0.50, 0.70, 0.85, 0.95, 1.00]:
            positions = [(base_pos[0], base_pos[1], base_pos[2], confidence)]
            self.publish_detection(positions, f'Confidence: {confidence:.2f}')
            time.sleep(2)

    # =========================================================================
    # SCENARIO 4: Empty Detection Test
    # =========================================================================
    def scenario_empty_detections(self):
        """Test with zero detections"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 4: Empty Detection Test')
        self.get_logger().info('=' * 60)

        for i in range(3):
            self.publish_detection([], f'Empty detection #{i+1}')
            time.sleep(2)

    # =========================================================================
    # SCENARIO 5: Circular Pattern Test
    # =========================================================================
    def scenario_circular_pattern(self):
        """Test with cotton arranged in circular pattern"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 5: Circular Pattern Test')
        self.get_logger().info('=' * 60)

        radius = 0.15
        center_x = 0.3
        center_y = 0.0
        center_z = 0.5
        count = 8

        positions = []
        for i in range(count):
            angle = (2 * math.pi * i) / count
            positions.append(
                (
                    center_x,
                    center_y + radius * math.cos(angle),
                    center_z + radius * math.sin(angle),
                    0.95,
                )
            )

        self.publish_detection(positions, f'Circular pattern: {count} positions')
        time.sleep(5)

    # =========================================================================
    # SCENARIO 6: Grid Pattern Test
    # =========================================================================
    def scenario_grid_pattern(self):
        """Test with cotton arranged in grid pattern"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 6: Grid Pattern Test')
        self.get_logger().info('=' * 60)

        positions = []
        for y in [-0.1, 0.0, 0.1]:
            for z in [0.4, 0.5, 0.6]:
                positions.append((0.3, y, z, 0.95))

        self.publish_detection(positions, f'Grid pattern: {len(positions)} positions')
        time.sleep(5)

    # =========================================================================
    # SCENARIO 7: Alternating Dense/Sparse Test
    # =========================================================================
    def scenario_alternating_density(self):
        """Test alternating between dense and sparse detections"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 7: Alternating Density Test')
        self.get_logger().info('=' * 60)

        for cycle in range(3):
            # Dense
            positions = [(0.3, i * 0.03 - 0.06, 0.5 + i * 0.02, 0.95) for i in range(5)]
            self.publish_detection(positions, f'Cycle {cycle+1}: Dense (5 positions)')
            time.sleep(3)

            # Sparse
            positions = [(0.3, 0.0, 0.5, 0.95)]
            self.publish_detection(positions, f'Cycle {cycle+1}: Sparse (1 position)')
            time.sleep(3)

    # =========================================================================
    # SCENARIO 8: Rapid Fire Test
    # =========================================================================
    def scenario_rapid_fire(self):
        """Test rapid consecutive detections"""
        self.get_logger().info('\n' + '=' * 60)
        self.get_logger().info('SCENARIO 8: Rapid Fire Test')
        self.get_logger().info('=' * 60)

        positions_list = [
            [(0.25, 0.0, 0.45, 0.95)],
            [(0.30, 0.05, 0.50, 0.95)],
            [(0.35, -0.05, 0.55, 0.95)],
            [(0.28, 0.0, 0.48, 0.95)],
        ]

        for i, positions in enumerate(positions_list):
            self.publish_detection(positions, f'Rapid fire #{i+1}')
            time.sleep(0.2)  # Very short delay

        self.get_logger().info('⏳ Waiting for processing...')
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description='Run cotton detection test scenarios')
    parser.add_argument(
        'scenario',
        nargs='?',
        default='all',
        choices=[
            'all',
            'progressive',
            'boundaries',
            'confidence',
            'empty',
            'circular',
            'grid',
            'alternating',
            'rapid',
        ],
        help='Scenario to run (default: all)',
    )
    parser.add_argument(
        '--delay', type=float, default=2.0, help='Delay between scenarios in seconds (default: 2.0)'
    )

    args = parser.parse_args()

    rclpy.init()
    tester = ScenarioTester()

    try:
        tester.get_logger().info('🎬 Starting test scenarios...')
        tester.get_logger().info(f'   Publishing to: /cotton_detection/results')
        time.sleep(1)

        if args.scenario == 'all' or args.scenario == 'progressive':
            tester.scenario_progressive_load()
            time.sleep(args.delay)

        if args.scenario == 'all' or args.scenario == 'boundaries':
            tester.scenario_workspace_boundaries()
            time.sleep(args.delay)

        if args.scenario == 'all' or args.scenario == 'confidence':
            tester.scenario_confidence_variation()
            time.sleep(args.delay)

        if args.scenario == 'all' or args.scenario == 'empty':
            tester.scenario_empty_detections()
            time.sleep(args.delay)

        if args.scenario == 'all' or args.scenario == 'circular':
            tester.scenario_circular_pattern()
            time.sleep(args.delay)

        if args.scenario == 'all' or args.scenario == 'grid':
            tester.scenario_grid_pattern()
            time.sleep(args.delay)

        if args.scenario == 'all' or args.scenario == 'alternating':
            tester.scenario_alternating_density()
            time.sleep(args.delay)

        if args.scenario == 'all' or args.scenario == 'rapid':
            tester.scenario_rapid_fire()

        tester.get_logger().info('\n' + '=' * 60)
        tester.get_logger().info('✅ All scenarios completed')
        tester.get_logger().info('=' * 60)

    except KeyboardInterrupt:
        tester.get_logger().info('🛑 Interrupted by user')
    finally:
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
