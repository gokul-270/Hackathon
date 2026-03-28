#!/usr/bin/env python3
"""
ROS2 Message Drop Rate Tester

Tests message delivery rate between cotton_detection publisher → yanthra_move subscriber.
Publishes N test messages and monitors how many are received to calculate drop rate.

Usage:
    # Full 10,000 message test (takes ~2.8 hours at 1 Hz)
    ./test_message_drop_rate.py

    # Quick smoke test with 100 messages
    ./test_message_drop_rate.py -n 100

    # Custom test with faster rate
    ./test_message_drop_rate.py -n 1000 -r 2.0

Prerequisites:
    1. Start yanthra_move node first:
       ros2 launch yanthra_move pragati_complete.launch.py

    2. Verify subscriber is active:
       ros2 topic info /cotton_detection/results
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from cotton_detection_msgs.msg import DetectionResult, CottonPosition
from geometry_msgs.msg import Point
from std_msgs.msg import Header
import argparse
import time
import os
import csv
from datetime import datetime
from pathlib import Path


class MessageDropRateTester(Node):
    def __init__(
        self,
        num_messages=10000,
        rate_hz=1.0,
        progress_interval=100,
        grace_seconds=2.0,
        log_dir=None,
        qos_depth=100,
    ):
        super().__init__('message_drop_rate_tester')

        self.num_messages = num_messages
        self.rate_hz = rate_hz
        self.progress_interval = progress_interval
        self.grace_seconds = grace_seconds
        self.qos_depth = qos_depth

        # Data tracking
        self.seq_counter = 0
        self.published = {}  # seq -> {stamp, wall_time, x, y, z, confidence}
        self.published_by_stamp = {}  # (sec, nanosec) -> seq
        self.received = {}  # seq -> {recv_wall_time, stamp}
        self.test_started = False
        self.test_finished = False

        # Setup logging directory
        if log_dir is None:
            log_dir = os.path.expanduser('~/pragati_ros2/logs/message_drop')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_path = Path(log_dir) / timestamp
        self.log_path.mkdir(parents=True, exist_ok=True)

        # QoS Profile - Reliable delivery
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=qos_depth
        )

        # Create publisher
        self.publisher = self.create_publisher(
            DetectionResult, '/cotton_detection/results', qos_profile
        )

        # Create monitor subscriber (same topic)
        self.subscription = self.create_subscription(
            DetectionResult, '/cotton_detection/results', self.monitor_callback, qos_profile
        )

        self.get_logger().info('=' * 70)
        self.get_logger().info('🧪 ROS2 Message Drop Rate Tester')
        self.get_logger().info('=' * 70)
        self.get_logger().info(f'Configuration:')
        self.get_logger().info(f'  Messages to publish: {num_messages}')
        self.get_logger().info(f'  Publishing rate: {rate_hz} Hz')
        self.get_logger().info(f'  Progress interval: every {progress_interval} messages')
        self.get_logger().info(f'  Grace period: {grace_seconds} seconds')
        self.get_logger().info(f'  QoS depth: {qos_depth}')
        self.get_logger().info(f'  QoS reliability: RELIABLE')
        self.get_logger().info(f'  Log directory: {self.log_path}')
        self.get_logger().info(f'  Estimated runtime: ~{int(num_messages / rate_hz / 60)} minutes')
        self.get_logger().info('')

        # Timer will be created after subscriber check
        self.publish_timer = None
        self.grace_timer = None

    def wait_for_subscriber(self, timeout_sec=60):
        """Wait for yanthra_move subscriber to be ready"""
        self.get_logger().info('⏳ Waiting for yanthra_move subscriber...')

        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            # Get subscriber count
            sub_count = self.count_subscribers('/cotton_detection/results')

            if sub_count > 0:
                # Check if it's yanthra (try to get node names)
                self.get_logger().info(
                    f'✅ Found {sub_count} subscriber(s) on /cotton_detection/results'
                )

                # Get topic info
                topic_names_and_types = self.get_topic_names_and_types()
                for name, types in topic_names_and_types:
                    if name == '/cotton_detection/results':
                        self.get_logger().info(f'   Topic type: {types}')

                return True

            time.sleep(0.5)
            rclpy.spin_once(self, timeout_sec=0.1)

        self.get_logger().error('❌ ERROR: No subscriber detected on /cotton_detection/results')
        self.get_logger().error('')
        self.get_logger().error('Please start yanthra_move first:')
        self.get_logger().error('  ros2 launch yanthra_move pragati_complete.launch.py')
        self.get_logger().error('')
        return False

    def start_test(self):
        """Start the publishing test"""
        if self.test_started:
            return

        self.test_started = True
        self.start_time = time.time()

        self.get_logger().info('=' * 70)
        self.get_logger().info('🚀 Starting Message Drop Rate Test')
        self.get_logger().info('=' * 70)
        self.get_logger().info('')

        # Create timer for publishing
        timer_period = 1.0 / self.rate_hz
        self.publish_timer = self.create_timer(timer_period, self.publish_test_message)

    def publish_test_message(self):
        """Publish a single test message"""
        if self.seq_counter >= self.num_messages:
            # Stop publishing and start grace period
            if self.publish_timer:
                self.publish_timer.cancel()
                self.publish_timer = None

            if not self.grace_timer:
                self.get_logger().info('')
                self.get_logger().info(f'✅ Published all {self.num_messages} messages')
                self.get_logger().info(
                    f'⏳ Grace period: waiting {self.grace_seconds}s for late arrivals...'
                )
                self.grace_timer = self.create_timer(self.grace_seconds, self.finalize_test)
            return

        # Increment sequence counter
        self.seq_counter += 1
        seq = self.seq_counter

        # Create message
        msg = DetectionResult()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_link'

        # Add test cotton position
        cotton_pos = CottonPosition()
        cotton_pos.position = Point(x=0.3, y=0.1, z=0.5)
        cotton_pos.confidence = 1.0
        cotton_pos.detection_id = seq
        msg.positions.append(cotton_pos)

        msg.total_count = 1
        msg.detection_successful = True
        msg.processing_time_ms = 10.0

        # Record publication
        stamp_key = (msg.header.stamp.sec, msg.header.stamp.nanosec)
        wall_time = time.time()

        self.published[seq] = {
            'stamp': stamp_key,
            'wall_time': wall_time,
            'x': 0.3,
            'y': 0.1,
            'z': 0.5,
            'confidence': 1.0,
        }
        self.published_by_stamp[stamp_key] = seq

        # Publish
        self.publisher.publish(msg)

        # Progress reporting
        if seq % self.progress_interval == 0 or seq == 1:
            received_count = len(self.received)
            drops = seq - received_count
            drop_rate = (drops / seq) * 100.0 if seq > 0 else 0.0
            elapsed = time.time() - self.start_time

            self.get_logger().info(
                f'📊 Progress: {seq}/{self.num_messages} | '
                f'Received: {received_count} | '
                f'Drops: {drops} ({drop_rate:.2f}%) | '
                f'Elapsed: {int(elapsed)}s'
            )

    def monitor_callback(self, msg):
        """Monitor callback - tracks messages that come through"""
        if not self.test_started or self.test_finished:
            return

        # Extract stamp key
        stamp_key = (msg.header.stamp.sec, msg.header.stamp.nanosec)

        # Check if this is one of our published messages
        seq = self.published_by_stamp.get(stamp_key)
        if seq is None:
            # Not our message, ignore
            return

        # Check if already received (deduplicate)
        if seq in self.received:
            return

        # Record reception
        recv_wall_time = time.time()
        self.received[seq] = {'recv_wall_time': recv_wall_time, 'stamp': stamp_key}

    def finalize_test(self):
        """Finalize test and generate reports"""
        if self.test_finished:
            return

        self.test_finished = True

        # Stop grace timer
        if self.grace_timer:
            self.grace_timer.cancel()
            self.grace_timer = None

        # Calculate statistics
        total_published = self.num_messages
        total_received = len(self.received)
        drops = sorted([seq for seq in self.published.keys() if seq not in self.received])
        drop_count = len(drops)
        drop_rate = (drop_count / total_published) * 100.0 if total_published > 0 else 0.0

        # Calculate latency stats
        latencies = []
        for seq, recv_info in self.received.items():
            if seq in self.published:
                latency_ms = (
                    recv_info['recv_wall_time'] - self.published[seq]['wall_time']
                ) * 1000.0
                latencies.append(latency_ms)

        latencies.sort()
        latency_stats = {}
        if latencies:
            latency_stats['min'] = latencies[0]
            latency_stats['max'] = latencies[-1]
            latency_stats['avg'] = sum(latencies) / len(latencies)
            latency_stats['p95'] = (
                latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
            )

        # Print summary
        self.get_logger().info('')
        self.get_logger().info('=' * 70)
        self.get_logger().info('📈 TEST RESULTS')
        self.get_logger().info('=' * 70)
        self.get_logger().info(f'Total Published:  {total_published}')
        self.get_logger().info(f'Total Received:   {total_received}')
        self.get_logger().info(f'Dropped Messages: {drop_count} ({drop_rate:.2f}%)')
        self.get_logger().info('')

        if drop_count > 0:
            self.get_logger().info(f'❌ Dropped message sequence numbers:')
            # Print in chunks of 20
            for i in range(0, len(drops), 20):
                chunk = drops[i : i + 20]
                self.get_logger().info(f'   {chunk}')
            self.get_logger().info('')
        else:
            self.get_logger().info('✅ No messages dropped!')
            self.get_logger().info('')

        if latency_stats:
            self.get_logger().info('⏱️  Latency Statistics:')
            self.get_logger().info(f'   Min:  {latency_stats["min"]:.2f} ms')
            self.get_logger().info(f'   Avg:  {latency_stats["avg"]:.2f} ms')
            self.get_logger().info(f'   P95:  {latency_stats["p95"]:.2f} ms')
            self.get_logger().info(f'   Max:  {latency_stats["max"]:.2f} ms')
            self.get_logger().info('')

        # Write log files
        self.write_logs(
            total_published, total_received, drop_count, drop_rate, drops, latency_stats
        )

        self.get_logger().info(f'📁 Detailed logs saved to: {self.log_path}')
        self.get_logger().info('=' * 70)

        # Shutdown
        self.get_logger().info('✅ Test complete. Shutting down...')
        rclpy.shutdown()

    def write_logs(self, total_pub, total_recv, drop_count, drop_rate, drops, latency_stats):
        """Write detailed log files"""

        # Summary file
        with open(self.log_path / 'summary.txt', 'w') as f:
            f.write('ROS2 Message Drop Rate Test Results\n')
            f.write('=' * 50 + '\n')
            f.write(f'Test Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Total Published: {total_pub}\n')
            f.write(f'Total Received: {total_recv}\n')
            f.write(f'Dropped: {drop_count} ({drop_rate:.2f}%)\n')
            f.write(f'Grace Period: {self.grace_seconds} seconds\n')
            f.write(f'Publishing Rate: {self.rate_hz} Hz\n')
            f.write(f'QoS Depth: {self.qos_depth}\n')
            f.write('\n')

            if latency_stats:
                f.write('Latency Statistics (ms):\n')
                f.write(f'  Min: {latency_stats["min"]:.2f}\n')
                f.write(f'  Avg: {latency_stats["avg"]:.2f}\n')
                f.write(f'  P95: {latency_stats["p95"]:.2f}\n')
                f.write(f'  Max: {latency_stats["max"]:.2f}\n')
                f.write('\n')

            if drops:
                f.write('Dropped Message Sequence Numbers:\n')
                f.write(f'{drops}\n')

        # Published messages CSV
        with open(self.log_path / 'published.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(
                ['seq', 'pub_sec', 'pub_nanosec', 'pub_wall_time', 'x', 'y', 'z', 'confidence']
            )
            for seq in sorted(self.published.keys()):
                data = self.published[seq]
                writer.writerow(
                    [
                        seq,
                        data['stamp'][0],
                        data['stamp'][1],
                        f"{data['wall_time']:.6f}",
                        data['x'],
                        data['y'],
                        data['z'],
                        data['confidence'],
                    ]
                )

        # Received messages CSV
        with open(self.log_path / 'received.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['seq', 'recv_wall_time', 'pub_sec', 'pub_nanosec', 'latency_ms'])
            for seq in sorted(self.received.keys()):
                recv_data = self.received[seq]
                pub_data = self.published[seq]
                latency_ms = (recv_data['recv_wall_time'] - pub_data['wall_time']) * 1000.0
                writer.writerow(
                    [
                        seq,
                        f"{recv_data['recv_wall_time']:.6f}",
                        recv_data['stamp'][0],
                        recv_data['stamp'][1],
                        f"{latency_ms:.2f}",
                    ]
                )

        # Dropped messages CSV
        with open(self.log_path / 'dropped.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['seq', 'pub_sec', 'pub_nanosec', 'pub_wall_time'])
            for seq in drops:
                data = self.published[seq]
                writer.writerow(
                    [seq, data['stamp'][0], data['stamp'][1], f"{data['wall_time']:.6f}"]
                )


def main():
    parser = argparse.ArgumentParser(
        description='Test ROS2 message drop rate between publisher and subscriber',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full 10,000 message test (default)
  ./test_message_drop_rate.py

  # Quick test with 100 messages
  ./test_message_drop_rate.py -n 100

  # Fast test: 1000 messages at 10 Hz
  ./test_message_drop_rate.py -n 1000 -r 10.0
        """,
    )
    parser.add_argument(
        '-n',
        '--num-messages',
        type=int,
        default=10000,
        help='Number of messages to publish (default: 10000)',
    )
    parser.add_argument(
        '-r', '--rate-hz', type=float, default=1.0, help='Publishing rate in Hz (default: 1.0)'
    )
    parser.add_argument(
        '--progress-interval',
        type=int,
        default=100,
        help='Print progress every N messages (default: 100)',
    )
    parser.add_argument(
        '--grace-seconds',
        type=float,
        default=2.0,
        help='Grace period after publishing for late arrivals (default: 2.0)',
    )
    parser.add_argument(
        '--log-dir',
        type=str,
        default=None,
        help='Log directory (default: ~/pragati_ros2/logs/message_drop)',
    )
    parser.add_argument(
        '--qos-depth',
        type=int,
        default=100,
        help='QoS depth for publisher/subscriber (default: 100)',
    )

    args = parser.parse_args()

    # Validate imports
    try:
        from cotton_detection_msgs.msg import DetectionResult, CottonPosition
    except ImportError as e:
        print('❌ ERROR: Cannot import cotton_detection_msgs messages')
        print('   Make sure your ROS2 workspace is built and sourced:')
        print('   source /opt/ros/jazzy/setup.bash')
        print('   source ~/pragati_ros2/install/setup.bash')
        print(f'   Error: {e}')
        return 1

    # Initialize ROS2
    rclpy.init()

    try:
        # Create node
        tester = MessageDropRateTester(
            num_messages=args.num_messages,
            rate_hz=args.rate_hz,
            progress_interval=args.progress_interval,
            grace_seconds=args.grace_seconds,
            log_dir=args.log_dir,
            qos_depth=args.qos_depth,
        )

        # Wait for subscriber
        if not tester.wait_for_subscriber():
            tester.destroy_node()
            rclpy.shutdown()
            return 1

        # Start test
        tester.start_test()

        # Spin
        rclpy.spin(tester)

    except KeyboardInterrupt:
        print('\n\n⚠️  Test interrupted by user (Ctrl+C)')
        if tester and not tester.test_finished:
            print('   Finalizing with partial results...')
            tester.finalize_test()
    except Exception as e:
        print(f'\n❌ ERROR: {e}')
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if rclpy.ok():
            rclpy.shutdown()

    return 0


if __name__ == '__main__':
    exit(main())
