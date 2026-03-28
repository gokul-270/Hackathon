#!/usr/bin/env python3
"""
Cotton Detection Example - Pragati ROS2

Demonstrates cotton detection operations:
- Starting/stopping detection
- Subscribing to detection results
- Processing cotton coordinates
- Handling pickability classification

Prerequisites:
- Cotton detection node running (offline or with camera)

Usage:
    python3 cotton_detection_example.py
"""

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger, SetBool
from geometry_msgs.msg import Point
import time


class CottonDetectionExample(Node):
    def __init__(self):
        super().__init__('cotton_detection_example')
        
        # Service clients
        self.start_client = self.create_client(Trigger, '/cotton_detection/start')
        self.stop_client = self.create_client(Trigger, '/cotton_detection/stop')
        self.next_client = self.create_client(Trigger, '/cotton_detection/next_target')
        
        # Wait for services
        self.get_logger().info('Waiting for cotton detection services...')
        self.start_client.wait_for_service(timeout_sec=5.0)
        
        # Subscriber for detection results (adjust topic name as needed)
        # Note: Actual topic name may vary based on implementation
        self.detection_sub = self.create_subscription(
            Point,  # Or custom message type
            '/cotton_detection/target',
            self.detection_callback,
            10
        )
        
        self.latest_detection = None
        self.get_logger().info('Cotton Detection Example Node Started')
    
    def detection_callback(self, msg):
        """Callback for cotton detection results."""
        self.latest_detection = msg
        self.get_logger().info(
            f'Detected cotton at: X={msg.x:.3f}, Y={msg.y:.3f}, Z={msg.z:.3f}'
        )
    
    def call_service(self, client, request):
        """Generic service call helper.
        
        Args:
            client: Service client
            request: Service request message
        
        Returns:
            Service response or None if failed
        """
        if not client.wait_for_service(timeout_sec=1.0):
            self.get_logger().error(f'Service {client.srv_name} not available')
            return None
        
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        
        if future.result() is not None:
            return future.result()
        else:
            self.get_logger().error(f'Service call failed: {client.srv_name}')
            return None
    
    def start_detection(self):
        """Start cotton detection."""
        self.get_logger().info('Starting detection...')
        response = self.call_service(self.start_client, Trigger.Request())
        
        if response and response.success:
            self.get_logger().info(f'Detection started: {response.message}')
            return True
        return False
    
    def stop_detection(self):
        """Stop cotton detection."""
        self.get_logger().info('Stopping detection...')
        response = self.call_service(self.stop_client, Trigger.Request())
        
        if response and response.success:
            self.get_logger().info(f'Detection stopped: {response.message}')
            return True
        return False
    
    def get_next_target(self):
        """Request next cotton target."""
        self.get_logger().info('Requesting next target...')
        response = self.call_service(self.next_client, Trigger.Request())
        
        if response and response.success:
            self.get_logger().info(f'Next target: {response.message}')
            return True
        else:
            self.get_logger().warn('No more targets available')
            return False
    
    def wait_for_detection(self, timeout=5.0):
        """Wait for a detection result.
        
        Args:
            timeout: Maximum time to wait (seconds)
        
        Returns:
            Detection message or None if timeout
        """
        self.latest_detection = None
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.latest_detection is not None:
                return self.latest_detection
        
        self.get_logger().warn('Timeout waiting for detection')
        return None


def main():
    rclpy.init()
    node = CottonDetectionExample()
    
    try:
        # Example 1: Start detection and get first target
        node.get_logger().info('\n=== Example 1: Start Detection ===')
        if not node.start_detection():
            node.get_logger().error('Failed to start detection')
            return
        
        # Wait for first detection
        detection = node.wait_for_detection(timeout=10.0)
        if detection:
            node.get_logger().info(
                f'First cotton detected at ({detection.x:.3f}, '
                f'{detection.y:.3f}, {detection.z:.3f})'
            )
        
        time.sleep(1.0)
        
        # Example 2: Sequential picking workflow
        node.get_logger().info('\n=== Example 2: Sequential Picking ===')
        
        cotton_count = 0
        max_cotton = 5  # Process up to 5 cotton bolls
        
        while cotton_count < max_cotton:
            # Get next target
            if not node.get_next_target():
                node.get_logger().info('No more cotton targets')
                break
            
            # Wait for detection result
            detection = node.wait_for_detection(timeout=5.0)
            if not detection:
                node.get_logger().warn('Detection timeout')
                break
            
            cotton_count += 1
            node.get_logger().info(
                f'Cotton #{cotton_count}: ({detection.x:.3f}, '
                f'{detection.y:.3f}, {detection.z:.3f})'
            )
            
            # Simulate pick operation
            node.get_logger().info('  -> Moving to target...')
            time.sleep(0.5)
            node.get_logger().info('  -> Activating vacuum...')
            time.sleep(0.3)
            node.get_logger().info('  -> Picked!')
            
            time.sleep(0.5)
        
        node.get_logger().info(f'Total cotton processed: {cotton_count}')
        
        # Example 3: Monitor continuous detection
        node.get_logger().info('\n=== Example 3: Continuous Monitoring (10s) ===')
        
        detection_count = 0
        start_time = time.time()
        duration = 10.0  # seconds
        
        while time.time() - start_time < duration:
            rclpy.spin_once(node, timeout_sec=0.1)
            
            if node.latest_detection is not None:
                detection_count += 1
                node.latest_detection = None  # Reset for next detection
        
        node.get_logger().info(
            f'Detected {detection_count} updates in {duration:.1f} seconds '
            f'({detection_count/duration:.1f} Hz)'
        )
        
        # Stop detection
        node.get_logger().info('\n=== Stopping Detection ===')
        node.stop_detection()
        
        node.get_logger().info('\n=== Examples Complete ===')
        
    except KeyboardInterrupt:
        node.get_logger().info('Interrupted by user')
        node.stop_detection()
    
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
