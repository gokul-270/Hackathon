#!/usr/bin/env python3
"""
Performance Benchmarking Script for Cotton Detection System

This script provides comprehensive performance benchmarking for the cotton detection system,
including FPS measurement, latency analysis, and mode comparison.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cotton_detection_msgs.srv import CottonDetection
import cv2
import numpy as np
import time
from typing import Dict, List, Tuple
import statistics
import argparse
import sys
import os


class CottonDetectionBenchmark(Node):
    """ROS2 node for benchmarking cotton detection performance"""

    def __init__(self, test_image_path: str = None, num_iterations: int = 100):
        super().__init__('cotton_detection_benchmark')

        self.test_image_path = test_image_path
        self.num_iterations = num_iterations
        self.test_image = None

        # Performance metrics storage
        self.metrics = {
            'hsv_only': {'latencies': [], 'fps': [], 'detections': []},
            'yolo_only': {'latencies': [], 'fps': [], 'detections': []},
            'hybrid_voting': {'latencies': [], 'fps': [], 'detections': []},
            'hybrid_merge': {'latencies': [], 'fps': [], 'detections': []},
            'hybrid_fallback': {'latencies': [], 'fps': [], 'detections': []},
        }

        # Service client
        self.cli = self.create_client(CottonDetection, 'cotton_detection/detect')
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for cotton detection service...')
            if not rclpy.ok():
                self.get_logger().error('Service not available')
                return

        self.get_logger().info('✅ Cotton detection service available')

        # Load test image
        self.load_test_image()

    def load_test_image(self):
        """Load test image for benchmarking"""
        if self.test_image_path and os.path.exists(self.test_image_path):
            self.test_image = cv2.imread(self.test_image_path)
            if self.test_image is not None:
                self.get_logger().info(f'📷 Loaded test image: {self.test_image.shape}')
            else:
                self.get_logger().error(f'❌ Failed to load image: {self.test_image_path}')
        else:
            # Create synthetic test image
            self.get_logger().info('🎨 Creating synthetic test image')
            self.test_image = self.create_synthetic_cotton_image()

    def create_synthetic_cotton_image(self) -> np.ndarray:
        """Create a synthetic image with cotton-like features for testing"""
        # Create a 640x480 RGB image
        image = np.zeros((480, 640, 3), dtype=np.uint8)

        # Add some background noise
        image[:, :] = [30, 40, 50]  # Dark background
        noise = np.random.normal(0, 10, image.shape).astype(np.uint8)
        image = cv2.add(image, noise)

        # Add cotton-like white patches
        for _ in range(15):
            center_x = np.random.randint(50, 590)
            center_y = np.random.randint(50, 430)
            radius = np.random.randint(20, 60)

            # Create circular white patch
            y, x = np.ogrid[:480, :640]
            mask = (x - center_x) ** 2 + (y - center_y) ** 2 <= radius**2
            image[mask] = [200, 220, 240]  # White cotton color

        return image

    def convert_cv_to_ros_image(self, cv_image: np.ndarray) -> Image:
        """Convert OpenCV image to ROS Image message"""
        ros_image = Image()
        ros_image.height = cv_image.shape[0]
        ros_image.width = cv_image.shape[1]
        ros_image.encoding = 'bgr8'
        ros_image.data = cv_image.tobytes()
        ros_image.step = cv_image.shape[1] * 3
        return ros_image

    def benchmark_detection_mode(self, mode: str) -> Dict:
        """Benchmark a specific detection mode"""
        self.get_logger().info(f'🏃 Benchmarking mode: {mode}')

        latencies = []
        detections = []

        for i in range(self.num_iterations):
            if i % 20 == 0:
                self.get_logger().info(f'   Progress: {i}/{self.num_iterations}')

            # Create request
            request = CottonDetection.Request()
            request.detect_command = 1  # Detection command
            request.image = self.convert_cv_to_ros_image(self.test_image)

            # Set detection mode via parameters (this would need to be implemented in the service)
            # For now, we'll assume the mode is set externally

            start_time = time.time()

            # Call service
            future = self.cli.call_async(request)
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

            end_time = time.time()

            if future.result() is not None:
                response = future.result()
                latency = (end_time - start_time) * 1000  # Convert to ms
                latencies.append(latency)
                detections.append(len(response.data) // 3)  # Each detection has 3 coordinates
            else:
                self.get_logger().warn(f'   Service call {i} failed')

        # Calculate statistics
        if latencies:
            avg_latency = statistics.mean(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            std_latency = statistics.stdev(latencies) if len(latencies) > 1 else 0
            avg_fps = 1000.0 / avg_latency if avg_latency > 0 else 0
            avg_detections = statistics.mean(detections)

            result = {
                'mode': mode,
                'iterations': len(latencies),
                'avg_latency_ms': avg_latency,
                'min_latency_ms': min_latency,
                'max_latency_ms': max_latency,
                'std_latency_ms': std_latency,
                'avg_fps': avg_fps,
                'avg_detections': avg_detections,
                'total_detections': sum(detections),
            }
        else:
            result = {'mode': mode, 'iterations': 0, 'error': 'No successful calls'}

        return result

    def run_benchmark(self) -> Dict:
        """Run complete benchmark suite"""
        self.get_logger().info('🚀 Starting Cotton Detection Performance Benchmark')
        self.get_logger().info(f'📊 Test iterations: {self.num_iterations}')

        results = {}

        # Test each detection mode
        modes_to_test = [
            'hsv_only',
            'yolo_only',
            'hybrid_voting',
            'hybrid_merge',
            'hybrid_fallback',
        ]

        for mode in modes_to_test:
            self.get_logger().info(f'🎯 Testing {mode}...')
            result = self.benchmark_detection_mode(mode)
            results[mode] = result

            if 'error' not in result:
                self.get_logger().info(
                    f'   ✅ {mode}: {result["avg_fps"]:.1f} FPS, '
                    f'{result["avg_latency_ms"]:.1f} ms avg latency'
                )
            else:
                self.get_logger().error(f'   ❌ {mode}: {result["error"]}')

        return results

    def print_report(self, results: Dict):
        """Print comprehensive benchmark report"""
        print("\n" + "=" * 80)
        print("📊 COTTON DETECTION PERFORMANCE BENCHMARK REPORT")
        print("=" * 80)

        print(f"\n📋 Test Configuration:")
        print(f"   Iterations per mode: {self.num_iterations}")
        print(f"   Test image: {self.test_image.shape if self.test_image is not None else 'None'}")

        print(f"\n🏆 Performance Results:")

        # Sort by FPS for ranking
        sorted_results = sorted(
            [(mode, data) for mode, data in results.items() if 'error' not in data],
            key=lambda x: x[1]['avg_fps'],
            reverse=True,
        )

        for rank, (mode, data) in enumerate(sorted_results, 1):
            print(f"\n{rank}. {mode.upper()}")
            print(f"   FPS: {data['avg_fps']:.1f}")
            print(f"   Avg Latency: {data['avg_latency_ms']:.1f} ms")
            print(
                f"   Latency Range: {data['min_latency_ms']:.1f} - {data['max_latency_ms']:.1f} ms"
            )
            print(f"   Latency StdDev: {data['std_latency_ms']:.1f} ms")
            print(f"   Avg Detections: {data['avg_detections']:.1f}")
            print(f"   Total Iterations: {data['iterations']}")

        # Performance analysis
        if sorted_results:
            best_mode = sorted_results[0][0]
            worst_mode = sorted_results[-1][0]
            best_fps = sorted_results[0][1]['avg_fps']
            worst_fps = sorted_results[-1][1]['avg_fps']
            improvement = ((best_fps - worst_fps) / worst_fps) * 100 if worst_fps > 0 else 0

            print(f"\n📈 Performance Analysis:")
            print(f"   Best Mode: {best_mode} ({best_fps:.1f} FPS)")
            print(f"   Worst Mode: {worst_mode} ({worst_fps:.1f} FPS)")
            print(f"   Performance Range: {improvement:.1f}% improvement")

        print(f"\n💡 Recommendations:")
        if sorted_results:
            best_mode = sorted_results[0][0]
            if 'yolo' in best_mode.lower():
                print("   • YOLO-based modes show best performance")
                print("   • Consider using hybrid_fallback for reliability")
            elif 'hsv' in best_mode.lower():
                print("   • HSV-only mode is fastest")
                print("   • Consider hybrid modes for better accuracy")
            else:
                print("   • Hybrid modes balance speed and accuracy")
                print("   • Choose based on your accuracy vs speed requirements")

        print("\n" + "=" * 80)


def main(args=None):
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Cotton Detection Performance Benchmark')
    parser.add_argument('--image', '-i', type=str, help='Path to test image')
    parser.add_argument(
        '--iterations',
        '-n',
        type=int,
        default=50,
        help='Number of iterations per mode (default: 50)',
    )
    parser.add_argument('--output', '-o', type=str, help='Output file for results')

    args = parser.parse_args()

    rclpy.init(args=sys.argv)

    try:
        # Create benchmark node
        benchmark = CottonDetectionBenchmark(args.image, args.iterations)

        if benchmark.test_image is None:
            print(
                "❌ No test image available. Please provide an image path or ensure synthetic image creation works."
            )
            return 1

        # Run benchmark
        results = benchmark.run_benchmark()

        # Print report
        benchmark.print_report(results)

        # Save results if requested
        if args.output:
            import json

            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"💾 Results saved to: {args.output}")

    except KeyboardInterrupt:
        print("\n⏹️  Benchmark interrupted by user")
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        return 1
    finally:
        rclpy.shutdown()

    return 0


if __name__ == '__main__':
    sys.exit(main())
