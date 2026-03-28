#!/usr/bin/env python3
"""
Test cotton detection once and display joint positions
"""

import rclpy
from rclpy.node import Node
from cotton_detection_msgs.srv import CottonDetection
from sensor_msgs.msg import JointState
import time


class DetectionJointMonitor(Node):
    def __init__(self):
        super().__init__('detection_joint_monitor')

        # Service client for cotton detection
        self.detection_client = self.create_client(CottonDetection, '/cotton_detection/detect')

        # Subscriber for joint states
        self.joint_sub = self.create_subscription(
            JointState, '/joint_states', self.joint_callback, 10
        )

        self.latest_joints = None

    def joint_callback(self, msg):
        """Store latest joint state"""
        self.latest_joints = msg

    def run_detection_and_show_joints(self):
        """Run detection once and display joint positions"""

        # Wait for joint states
        self.get_logger().info('Waiting for joint states...')
        timeout = 5.0
        start = time.time()
        while self.latest_joints is None and (time.time() - start) < timeout:
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.latest_joints is None:
            self.get_logger().error('❌ No joint states received')
            return False

        # Display initial joint positions
        print('\n' + '=' * 60)
        print('Initial Joint Positions')
        print('=' * 60)
        self._display_joints(self.latest_joints)

        # Wait for detection service
        self.get_logger().info('\nWaiting for cotton detection service...')
        if not self.detection_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('❌ Detection service not available')
            return False

        # Run detection
        print('\n' + '=' * 60)
        print('Running Cotton Detection')
        print('=' * 60)

        request = CottonDetection.Request()
        request.detect_command = 1  # Start detection

        start_time = time.time()
        future = self.detection_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=20.0)
        end_time = time.time()

        if future.result() is not None:
            response = future.result()
            latency_ms = (end_time - start_time) * 1000

            print(f'\n✅ Detection completed in {latency_ms:.1f} ms')
            print(f'   Success: {response.success}')

            if response.success:
                num_detections = len(response.data) // 3
                print(f'   Cotton detected: {num_detections}')

                # Show detected coordinates
                if num_detections > 0:
                    print('\n   Detected coordinates:')
                    for i in range(num_detections):
                        x = response.data[i * 3]
                        y = response.data[i * 3 + 1]
                        z = response.data[i * 3 + 2]
                        print(f'   Cotton {i+1}: X={x:.3f}, Y={y:.3f}, Z={z:.3f}')
            else:
                print(f'   Message: {response.message}')
        else:
            print('❌ Detection service call failed')
            return False

        # Get joint positions after detection
        print('\n' + '=' * 60)
        print('Final Joint Positions')
        print('=' * 60)

        # Spin a few times to get updated joint state
        for _ in range(10):
            rclpy.spin_once(self, timeout_sec=0.1)

        if self.latest_joints:
            self._display_joints(self.latest_joints)

        return True

    def _display_joints(self, joint_state):
        """Display joint positions in a formatted way"""
        if not joint_state.name:
            print('No joint data available')
            return

        print(f'\nNumber of joints: {len(joint_state.name)}')
        print('\nJoint Positions:')
        print('-' * 60)

        for i, name in enumerate(joint_state.name):
            pos_rad = joint_state.position[i] if i < len(joint_state.position) else 0.0
            pos_deg = pos_rad * 180.0 / 3.14159265359

            vel = joint_state.velocity[i] if i < len(joint_state.velocity) else 0.0
            effort = joint_state.effort[i] if i < len(joint_state.effort) else 0.0

            print(
                f'{name:20s}: {pos_rad:8.4f} rad ({pos_deg:7.2f}°)  '
                f'vel: {vel:7.4f}  effort: {effort:7.2f}'
            )
        print('-' * 60)


def main():
    rclpy.init()

    node = DetectionJointMonitor()

    print('\n' + '=' * 60)
    print('Cotton Detection + Joint Position Monitor')
    print('=' * 60)
    print('\nThis script will:')
    print('  1. Show initial joint positions')
    print('  2. Run cotton detection once')
    print('  3. Show joint positions after detection')
    print('')

    try:
        success = node.run_detection_and_show_joints()

        if success:
            print('\n✅ Test completed successfully')
        else:
            print('\n❌ Test failed')

    except KeyboardInterrupt:
        print('\n\n⚠️  Interrupted by user')
    except Exception as e:
        print(f'\n❌ Error: {e}')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
