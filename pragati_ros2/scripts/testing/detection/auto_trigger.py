#!/usr/bin/env python3
"""
Auto Detection Trigger - Periodically trigger cotton detection
Useful for thermal testing and stress testing the camera
"""

import rclpy
from rclpy.node import Node
from cotton_detection_msgs.srv import CottonDetection
import signal
import sys
from datetime import datetime
import time


class AutoTrigger(Node):
    def __init__(self, interval=30, count=None, timeout=25.0):
        super().__init__('auto_trigger')

        self.interval = interval  # seconds between triggers
        self.max_count = count  # None = infinite
        self.timeout = timeout  # service call timeout in seconds
        self.trigger_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.timeout_count = 0
        self.pending_future = None  # Track pending request

        # Create service client
        self.client = self.create_client(CottonDetection, '/cotton_detection/detect')

        # Wait for service
        self.get_logger().info('🔍 Waiting for cotton detection service...')
        while not self.client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('   Service not available, waiting...')

        self.get_logger().info('✅ Connected to detection service')

        # Create timer for periodic triggers
        self.timer = self.create_timer(self.interval, self.trigger_detection)

        # Setup signal handler
        signal.signal(signal.SIGINT, self.signal_handler)

        self.get_logger().info(f'🎯 Auto-trigger started:')
        self.get_logger().info(f'   Interval: {self.interval} seconds')
        self.get_logger().info(f'   Timeout: {self.timeout} seconds')
        if self.max_count:
            self.get_logger().info(f'   Max triggers: {self.max_count}')
        else:
            self.get_logger().info(f'   Max triggers: Unlimited (Ctrl+C to stop)')
        self.get_logger().info('')

    def signal_handler(self, sig, frame):
        self.get_logger().info('\n🛑 Stopping auto-trigger...')
        self.print_summary()
        sys.exit(0)

    def trigger_detection(self):
        # Check if we've reached max count
        if self.max_count and self.trigger_count >= self.max_count:
            self.get_logger().info(f'✅ Reached max trigger count ({self.max_count})')
            self.print_summary()
            sys.exit(0)

        # Check if previous request is still pending
        if self.pending_future is not None and not self.pending_future.done():
            self.get_logger().warn(f'⚠️  Previous request still pending, cancelling...')
            self.pending_future.cancel()
            self.timeout_count += 1

        self.trigger_count += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.get_logger().info(f'🎯 Trigger #{self.trigger_count} at {timestamp}')

        # Create request
        request = CottonDetection.Request()
        request.detect_command = 1  # Start detection

        # Call service asynchronously with timeout tracking
        try:
            self.pending_future = self.client.call_async(request)
            self.pending_future.add_done_callback(self.detection_callback)

            # Create a timeout checker
            self.create_timer(
                self.timeout, lambda: self.check_timeout(self.pending_future), callback_group=None
            )
        except Exception as e:
            self.get_logger().error(f'❌ Failed to call service: {e}')
            self.fail_count += 1
            self.pending_future = None

    def check_timeout(self, future):
        """Check if a service call has timed out"""
        if future is not None and not future.done():
            self.get_logger().warn(f'⏱️  Service call timed out after {self.timeout}s')
            future.cancel()
            self.timeout_count += 1
            self.pending_future = None

    def detection_callback(self, future):
        """Handle detection response"""
        # Clear pending future
        if self.pending_future == future:
            self.pending_future = None

        try:
            # Check if future was cancelled
            if future.cancelled():
                self.get_logger().warn(f'   ⏱️  Request was cancelled (timeout)')
                return

            response = future.result()  # Get result

            if response.success:
                self.success_count += 1
                num_detections = len(response.data) // 3  # x,y,z triplets
                self.get_logger().info(f'   ✅ Success: {num_detections} cotton(s) detected')
            else:
                self.fail_count += 1
                self.get_logger().info(f'   ❌ Failed: {response.message}')

        except Exception as e:
            self.fail_count += 1
            self.get_logger().error(f'   ❌ Exception: {e}')

        # Print running stats every 5 triggers
        if self.trigger_count % 5 == 0:
            self.get_logger().info('')
            self.get_logger().info(
                f'📊 Stats: {self.trigger_count} triggers | '
                f'{self.success_count} success | '
                f'{self.fail_count} failed | '
                f'{self.timeout_count} timeouts'
            )
            self.get_logger().info('')

    def print_summary(self):
        self.get_logger().info('')
        self.get_logger().info('=' * 60)
        self.get_logger().info('📊 Auto-Trigger Summary')
        self.get_logger().info('=' * 60)
        self.get_logger().info(f'  Total triggers:    {self.trigger_count}')
        self.get_logger().info(f'  Successful:        {self.success_count}')
        self.get_logger().info(f'  Failed:            {self.fail_count}')
        self.get_logger().info(f'  Timeouts:          {self.timeout_count}')
        if self.trigger_count > 0:
            success_rate = (self.success_count / self.trigger_count) * 100
            self.get_logger().info(f'  Success rate:      {success_rate:.1f}%')
        self.get_logger().info('=' * 60)
        self.get_logger().info('')


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Automatically trigger cotton detection at regular intervals',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Trigger every 30 seconds indefinitely
  ./auto_trigger_detections.py

  # Trigger every 60 seconds
  ./auto_trigger_detections.py -i 60

  # Trigger 20 times then stop
  ./auto_trigger_detections.py -c 20

  # Trigger every 15 seconds, 40 times (10 minutes of testing)
  ./auto_trigger_detections.py -i 15 -c 40
        ''',
    )

    parser.add_argument(
        '-i',
        '--interval',
        type=int,
        default=30,
        help='Seconds between detection triggers (default: 30)',
    )
    parser.add_argument(
        '-c',
        '--count',
        type=int,
        default=None,
        help='Maximum number of triggers (default: unlimited)',
    )
    parser.add_argument(
        '-t',
        '--timeout',
        type=float,
        default=25.0,
        help='Service call timeout in seconds (default: 25.0)',
    )

    args = parser.parse_args()

    rclpy.init()

    try:
        node = AutoTrigger(interval=args.interval, count=args.count, timeout=args.timeout)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
