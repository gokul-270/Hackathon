#!/usr/bin/env python3
"""DDS localhost pub-sub latency benchmark for Pragati RPi 4B.

Measures round-trip latency from publish() to subscription callback delivery
on the same machine, isolating DDS transport + executor overhead from
application logic.

Tests both Reliable and BestEffort QoS, and both SingleThreadedExecutor and
MultiThreadedExecutor configurations.

Usage (on RPi or dev workstation):
    # Source ROS2 + workspace first
    source /opt/ros/jazzy/setup.bash
    source ~/pragati_ros2/install/setup.bash

    # Use the same DDS config as production
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export CYCLONEDDS_URI=file://$HOME/pragati_ros2/config/cyclonedds.xml
    export ROS_DOMAIN_ID=1
    export ROS_LOCALHOST_ONLY=1

    python3 dds_localhost_latency.py

    # Optional: specify message count and output format
    python3 dds_localhost_latency.py --count 100 --json

Baseline results (2026-03-17, RPi 4B, Ubuntu 24.04, CycloneDDS 0.10.5):
    iceoryx shared memory DISABLED (loopback UDP), ROS_LOCALHOST_ONLY=1

    SingleThreadedExecutor + Reliable QoS (50 msgs):
        Min: 0.7ms, P50: 1.0ms, P95: 1.3ms, Max: 1.7ms, Mean: 1.0ms

    SingleThreadedExecutor + BestEffort QoS (50 msgs):
        Min: 0.6ms, P50: 0.6ms, P95: 0.8ms, Max: 1.0ms, Mean: 0.6ms

    MultiThreadedExecutor(2) + Reliable QoS (50 msgs):
        Min: 1.4ms, P50: 2.1ms, P95: 2.6ms, Max: 2.9ms, Mean: 2.1ms

    Conclusion: DDS localhost transport is ~1-2ms. Any observed latency
    significantly above this (e.g., 50-120ms in detection pipeline) is
    executor starvation or application-level contention, not DDS overhead.

Context: This benchmark was created during investigation of detection timing
in the cotton picking pipeline (trigger → detection result → yanthra_move).
Field measurements showed 50-120ms for the DDS delivery component, but this
benchmark proved the DDS layer itself is ~1ms — the delay was executor
starvation in yanthra_move's SingleThreadedExecutor (7-9 callbacks competing
for one thread).
"""

import argparse
import json as json_lib
import statistics
import sys
import threading
import time

import rclpy
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import String


class LatencyTester(Node):
    """Pub-sub latency tester using String messages with sequence numbers."""

    def __init__(self):
        super().__init__("dds_latency_tester")
        self.results_reliable = []
        self.results_besteffort = []
        self.send_times = {}
        self.received = threading.Event()

        # Reliable QoS (matches cotton_detection publisher config)
        self.qos_reliable = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            durability=DurabilityPolicy.VOLATILE,
        )

        # BestEffort QoS (lower overhead alternative)
        self.qos_besteffort = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            durability=DurabilityPolicy.VOLATILE,
        )

        # Create pub/sub pairs for both QoS profiles
        self.pub_rel = self.create_publisher(String, "/latency_test_reliable", self.qos_reliable)
        self.sub_rel = self.create_subscription(
            String, "/latency_test_reliable", self._cb_reliable, self.qos_reliable
        )

        self.pub_be = self.create_publisher(String, "/latency_test_besteffort", self.qos_besteffort)
        self.sub_be = self.create_subscription(
            String, "/latency_test_besteffort", self._cb_besteffort, self.qos_besteffort
        )

    def _cb_reliable(self, msg):
        recv_ns = time.monotonic_ns()
        seq = int(msg.data)
        if seq in self.send_times:
            lat_us = (recv_ns - self.send_times[seq]) / 1000
            self.results_reliable.append(lat_us)
            self.received.set()

    def _cb_besteffort(self, msg):
        recv_ns = time.monotonic_ns()
        seq = int(msg.data)
        if seq in self.send_times:
            lat_us = (recv_ns - self.send_times[seq]) / 1000
            self.results_besteffort.append(lat_us)
            self.received.set()

    def run_test(self, mode, count=50):
        """Run a latency test with the given QoS mode.

        Args:
            mode: 'reliable' or 'besteffort'
            count: Number of messages to send

        Returns:
            List of latency measurements in microseconds.
        """
        pub = self.pub_rel if mode == "reliable" else self.pub_be
        results = self.results_reliable if mode == "reliable" else self.results_besteffort
        results.clear()
        self.send_times.clear()

        # Warm up DDS discovery
        time.sleep(0.5)
        for i in range(5):
            msg = String()
            msg.data = str(-1)
            pub.publish(msg)
            time.sleep(0.05)
        time.sleep(0.5)

        for i in range(count):
            self.received.clear()
            msg = String()
            msg.data = str(i)
            self.send_times[i] = time.monotonic_ns()
            pub.publish(msg)
            self.received.wait(timeout=1.0)
            time.sleep(0.02)  # 20ms between sends

        return list(results)


def format_results(label, results, count):
    """Format test results as a dict."""
    if not results:
        return {"label": label, "sent": count, "received": 0, "error": "No messages received"}
    sorted_r = sorted(results)
    return {
        "label": label,
        "sent": count,
        "received": len(results),
        "min_us": round(min(results)),
        "p50_us": round(statistics.median(results)),
        "p95_us": round(sorted_r[int(len(sorted_r) * 0.95)]),
        "max_us": round(max(results)),
        "mean_us": round(statistics.mean(results)),
        "min_ms": round(min(results) / 1000, 1),
        "p50_ms": round(statistics.median(results) / 1000, 1),
        "p95_ms": round(sorted_r[int(len(sorted_r) * 0.95)] / 1000, 1),
        "max_ms": round(max(results) / 1000, 1),
        "mean_ms": round(statistics.mean(results) / 1000, 1),
    }


def print_results(r):
    """Print a results dict in human-readable format."""
    if "error" in r:
        print(f"  {r['error']}")
        return
    print(f"  Received: {r['received']}/{r['sent']}")
    print(f"  Min:  {r['min_us']} us ({r['min_ms']} ms)")
    print(f"  P50:  {r['p50_us']} us ({r['p50_ms']} ms)")
    print(f"  P95:  {r['p95_us']} us ({r['p95_ms']} ms)")
    print(f"  Max:  {r['max_us']} us ({r['max_ms']} ms)")
    print(f"  Mean: {r['mean_us']} us ({r['mean_ms']} ms)")


def run_with_executor(executor_cls, executor_kwargs, count, label_prefix):
    """Run all QoS tests with a given executor type."""
    rclpy.init()
    node = LatencyTester()

    if executor_kwargs:
        executor = executor_cls(**executor_kwargs)
        executor.add_node(node)
        spin_thread = threading.Thread(target=executor.spin, daemon=True)
    else:
        executor = None
        spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)

    spin_thread.start()
    time.sleep(1.0)  # Let DDS discovery settle

    all_results = []

    # Test Reliable
    label = f"{label_prefix} + Reliable"
    rel = node.run_test("reliable", count)
    all_results.append(format_results(label, rel, count))

    # Test BestEffort
    label = f"{label_prefix} + BestEffort"
    be = node.run_test("besteffort", count)
    all_results.append(format_results(label, be, count))

    if executor:
        executor.shutdown()
    node.destroy_node()
    rclpy.shutdown()

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="DDS localhost pub-sub latency benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--count", type=int, default=50, help="Number of messages per test (default: 50)"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    all_results = []

    # --- SingleThreadedExecutor ---
    results = run_with_executor(None, None, args.count, "SingleThreadedExecutor")
    all_results.extend(results)

    # --- MultiThreadedExecutor(2) ---
    results = run_with_executor(
        MultiThreadedExecutor, {"num_threads": 2}, args.count, "MultiThreadedExecutor(2)"
    )
    all_results.extend(results)

    if args.json:
        output = {
            "benchmark": "dds_localhost_latency",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "rmw": "rmw_cyclonedds_cpp",
            "messages_per_test": args.count,
            "results": all_results,
        }
        print(json_lib.dumps(output, indent=2))
    else:
        print()
        print("=" * 60)
        print("DDS Localhost Latency Benchmark")
        print("=" * 60)
        try:
            rclpy.init()
            rmw = rclpy.get_rmw_implementation_identifier()
            rclpy.shutdown()
        except Exception:
            rmw = "unknown"
        print(f"RMW: {rmw}")
        print(f"Messages per test: {args.count}")
        print()

        for r in all_results:
            print(f"--- {r['label']} ---")
            print_results(r)
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
