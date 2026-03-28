#!/usr/bin/env python3
"""
Performance Monitoring Service for Pragati ROS2 Dashboard
=========================================================

Provides comprehensive performance monitoring including:
- System resource monitoring (CPU, memory, disk, network)
- ROS2 performance metrics collection
- Network latency measurement and analysis
- Historical performance data storage
- Performance alerting and threshold monitoring
- Real-time performance analytics

This service extends the dashboard with Phase 3 capabilities.
"""

import asyncio
import logging
import time
import threading
import psutil
import subprocess
import json
import statistics
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml
import socket
import traceback

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from std_msgs.msg import Header
    from geometry_msgs.msg import Twist

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


def _get_system_state() -> dict:
    """Lazy accessor for ros2_monitor system_state (avoids circular imports)."""
    try:
        from backend.ros2_monitor import system_state

        return system_state
    except ImportError:
        return {}


@dataclass
class SystemMetrics:
    """System resource metrics"""

    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_percent: float
    disk_gb: float
    network_bytes_sent: int
    network_bytes_recv: int
    load_average: Tuple[float, float, float]
    uptime_seconds: float
    temperature_celsius: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ROS2Metrics:
    """ROS2 system performance metrics"""

    timestamp: str
    node_count: int
    topic_count: int
    service_count: int
    parameter_count: int
    active_subscriptions: int
    active_publishers: int
    message_rates: Dict[str, float]  # topic -> messages/sec
    message_latencies: Dict[str, float]  # topic -> avg latency ms
    node_cpu_usage: Dict[str, float]  # node -> cpu %
    node_memory_usage: Dict[str, float]  # node -> memory MB

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NetworkMetrics:
    """Network performance metrics"""

    timestamp: str
    ping_latency_ms: float
    dns_resolution_ms: float
    tcp_connect_ms: float
    packet_loss_percent: float
    bandwidth_mbps: float
    ros2_discovery_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceAlert:
    """Performance alert"""

    alert_id: str
    timestamp: str
    severity: str  # low, medium, high, critical
    category: str  # system, ros2, network
    metric: str
    current_value: float
    threshold_value: float
    message: str
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PerformanceDataStore:
    """In-memory time-series data storage for performance metrics"""

    def __init__(self, max_points: int = 1000):
        self.max_points = max_points
        self.system_metrics: deque = deque(maxlen=max_points)
        self.ros2_metrics: deque = deque(maxlen=max_points)
        self.network_metrics: deque = deque(maxlen=max_points)
        self.alerts: deque = deque(maxlen=100)  # Keep last 100 alerts

    def add_system_metrics(self, metrics: SystemMetrics):
        """Add system metrics data point"""
        self.system_metrics.append(metrics)

    def add_ros2_metrics(self, metrics: ROS2Metrics):
        """Add ROS2 metrics data point"""
        self.ros2_metrics.append(metrics)

    def add_network_metrics(self, metrics: NetworkMetrics):
        """Add network metrics data point"""
        self.network_metrics.append(metrics)

    def add_alert(self, alert: PerformanceAlert):
        """Add performance alert"""
        self.alerts.append(alert)

    def get_recent_system_metrics(self, minutes: int = 60) -> List[SystemMetrics]:
        """Get system metrics from last N minutes"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        return [
            metric
            for metric in self.system_metrics
            if datetime.fromisoformat(metric.timestamp.replace('Z', '+00:00')) >= cutoff_time
        ]

    def get_recent_ros2_metrics(self, minutes: int = 60) -> List[ROS2Metrics]:
        """Get ROS2 metrics from last N minutes"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        return [
            metric
            for metric in self.ros2_metrics
            if datetime.fromisoformat(metric.timestamp.replace('Z', '+00:00')) >= cutoff_time
        ]

    def get_recent_network_metrics(self, minutes: int = 60) -> List[NetworkMetrics]:
        """Get network metrics from last N minutes"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        return [
            metric
            for metric in self.network_metrics
            if datetime.fromisoformat(metric.timestamp.replace('Z', '+00:00')) >= cutoff_time
        ]

    def get_recent_alerts(self, minutes: int = 1440) -> List[PerformanceAlert]:  # 24 hours default
        """Get alerts from last N minutes"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        return [
            alert
            for alert in self.alerts
            if datetime.fromisoformat(alert.timestamp.replace('Z', '+00:00')) >= cutoff_time
        ]


class SystemMonitor:
    """System resource monitoring"""

    def __init__(self):
        self.initial_network_stats = psutil.net_io_counters()
        self.last_network_check = time.time()

    def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1.0)

            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_mb = memory.used / (1024 * 1024)

            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            disk_gb = disk.free / (1024 * 1024 * 1024)

            # Network metrics
            network = psutil.net_io_counters()

            # Load average
            load_avg = psutil.getloadavg()

            # System uptime
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time

            # Temperature (if available)
            temperature = None
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    # Get first available temperature
                    for name, entries in temps.items():
                        if entries:
                            temperature = entries[0].current
                            break
            except (AttributeError, OSError):
                pass

            return SystemMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_mb=memory_mb,
                disk_percent=disk_percent,
                disk_gb=disk_gb,
                network_bytes_sent=network.bytes_sent,
                network_bytes_recv=network.bytes_recv,
                load_average=load_avg,
                uptime_seconds=uptime_seconds,
                temperature_celsius=temperature,
            )

        except Exception as e:
            # Return basic metrics if detailed collection fails
            return SystemMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                cpu_percent=psutil.cpu_percent(),
                memory_percent=psutil.virtual_memory().percent,
                memory_mb=psutil.virtual_memory().used / (1024 * 1024),
                disk_percent=0.0,
                disk_gb=0.0,
                network_bytes_sent=0,
                network_bytes_recv=0,
                load_average=(0.0, 0.0, 0.0),
                uptime_seconds=0.0,
                temperature_celsius=None,
            )


class NetworkMonitor:
    """Network performance monitoring"""

    def __init__(self):
        self.ping_hosts = ['8.8.8.8', '1.1.1.1']  # Google DNS, Cloudflare DNS
        self.test_domains = ['google.com', 'github.com']

    def collect_network_metrics(self) -> NetworkMetrics:
        """Collect network performance metrics"""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Ping latency measurement
        ping_latencies = []
        for host in self.ping_hosts:
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '2', host], capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    # Parse ping output to get time
                    for line in result.stdout.split('\n'):
                        if 'time=' in line:
                            time_part = line.split('time=')[1].split()[0]
                            latency_ms = float(time_part)
                            ping_latencies.append(latency_ms)
                            break
            except Exception:
                pass

        avg_ping_latency = statistics.mean(ping_latencies) if ping_latencies else 999.0

        # DNS resolution time
        dns_times = []
        for domain in self.test_domains:
            try:
                start_time = time.time()
                socket.gethostbyname(domain)
                dns_time = (time.time() - start_time) * 1000  # Convert to ms
                dns_times.append(dns_time)
            except Exception:
                pass

        avg_dns_time = statistics.mean(dns_times) if dns_times else 999.0

        # TCP connection time (simplified)
        tcp_connect_time = 0.0
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(('8.8.8.8', 53))
            tcp_connect_time = (time.time() - start_time) * 1000
            sock.close()
        except Exception:
            tcp_connect_time = 999.0

        # ROS2 discovery time (mock for now)
        ros2_discovery_time = self._measure_ros2_discovery_time()

        return NetworkMetrics(
            timestamp=timestamp,
            ping_latency_ms=avg_ping_latency,
            dns_resolution_ms=avg_dns_time,
            tcp_connect_ms=tcp_connect_time,
            packet_loss_percent=0.0,  # Would need more sophisticated measurement
            bandwidth_mbps=0.0,  # Would need bandwidth test
            ros2_discovery_time_ms=ros2_discovery_time,
        )

    def _measure_ros2_discovery_time(self) -> float:
        """Measure ROS2 node discovery time.

        Returns 0.0 when nodes are already discovered via rclpy graph
        introspection (system_state), avoiding a heavyweight subprocess.
        """
        if not ROS2_AVAILABLE:
            return 0.0

        try:
            state = _get_system_state()
            nodes = state.get("nodes", {})
            # Nodes already discovered by ros2_monitor — no subprocess needed.
            if nodes:
                return 0.0
            # No nodes known yet — report as unavailable.
            return 999.0
        except Exception:
            return 999.0


class ROS2PerformanceMonitor:
    """ROS2 system performance monitoring"""

    def __init__(self, node: Optional[Node] = None):
        self.node = node
        self.topic_rates: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self.last_topic_check = time.time()

    def collect_ros2_metrics(self) -> ROS2Metrics:
        """Collect ROS2 performance metrics"""
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            # Basic ROS2 system info
            node_count = len(self._get_node_list())
            topic_count = len(self._get_topic_list())
            service_count = len(self._get_service_list())

            # Message rates (simplified)
            message_rates = self._calculate_message_rates()

            # Node resource usage (would need more sophisticated monitoring)
            node_cpu_usage = self._get_node_cpu_usage()
            node_memory_usage = self._get_node_memory_usage()

            return ROS2Metrics(
                timestamp=timestamp,
                node_count=node_count,
                topic_count=topic_count,
                service_count=service_count,
                parameter_count=0,  # Would need parameter counting
                active_subscriptions=0,  # Would need subscription counting
                active_publishers=0,  # Would need publisher counting
                message_rates=message_rates,
                message_latencies={},  # Would need latency measurement
                node_cpu_usage=node_cpu_usage,
                node_memory_usage=node_memory_usage,
            )

        except Exception as e:
            # Return basic metrics if collection fails
            return ROS2Metrics(
                timestamp=timestamp,
                node_count=0,
                topic_count=0,
                service_count=0,
                parameter_count=0,
                active_subscriptions=0,
                active_publishers=0,
                message_rates={},
                message_latencies={},
                node_cpu_usage={},
                node_memory_usage={},
            )

    def _get_node_list(self) -> List[str]:
        """Get list of ROS2 nodes"""
        try:
            if self.node:
                return self.node.get_node_names()
            else:
                state = _get_system_state()
                nodes = state.get("nodes", {})
                if nodes:
                    return list(nodes.keys())
        except Exception:
            pass
        return []

    def _get_topic_list(self) -> List[str]:
        """Get list of ROS2 topics"""
        try:
            state = _get_system_state()
            topics = state.get("topics", {})
            if topics:
                return list(topics.keys())
        except Exception:
            pass
        return []

    def _get_service_list(self) -> List[str]:
        """Get list of ROS2 services"""
        try:
            state = _get_system_state()
            services = state.get("services", {})
            if services:
                return list(services.keys())
        except Exception:
            pass
        return []

    def _calculate_message_rates(self) -> Dict[str, float]:
        """Calculate message rates for topics"""
        # This is a simplified implementation
        # In a real implementation, you'd subscribe to topics and measure rates
        return {}

    def _get_node_cpu_usage(self) -> Dict[str, float]:
        """Get CPU usage for ROS2 nodes"""
        node_cpu = {}
        try:
            # Find ROS2 processes and get their CPU usage
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    proc_info = proc.info
                    if 'ros2' in proc_info['name'].lower() or any(
                        ros_name in proc_info['name'].lower()
                        for ros_name in ['rviz', 'rqt', 'gazebo']
                    ):
                        node_cpu[proc_info['name']] = proc_info['cpu_percent']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return node_cpu

    def _get_node_memory_usage(self) -> Dict[str, float]:
        """Get memory usage for ROS2 nodes"""
        node_memory = {}
        try:
            # Find ROS2 processes and get their memory usage
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    proc_info = proc.info
                    if 'ros2' in proc_info['name'].lower() or any(
                        ros_name in proc_info['name'].lower()
                        for ros_name in ['rviz', 'rqt', 'gazebo']
                    ):
                        memory_mb = proc_info['memory_info'].rss / (1024 * 1024)
                        node_memory[proc_info['name']] = memory_mb
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return node_memory


class PerformanceAlertManager:
    """Performance alert management"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.thresholds = {
            'cpu_percent': config.get('cpu_threshold_percent', 80.0),
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'ping_latency_ms': 100.0,
            'node_count_min': 1,
        }
        self.alert_cooldown = {}  # Alert type -> last alert time
        self.cooldown_period = 300  # 5 minutes between same type alerts

    def check_system_alerts(self, metrics: SystemMetrics) -> List[PerformanceAlert]:
        """Check system metrics for alert conditions"""
        alerts = []
        current_time = time.time()

        # CPU usage alert
        if metrics.cpu_percent > self.thresholds['cpu_percent']:
            if self._should_send_alert('cpu_high', current_time):
                alerts.append(
                    PerformanceAlert(
                        alert_id=f"cpu_high_{int(current_time)}",
                        timestamp=metrics.timestamp,
                        severity="high" if metrics.cpu_percent > 90 else "medium",
                        category="system",
                        metric="cpu_percent",
                        current_value=metrics.cpu_percent,
                        threshold_value=self.thresholds['cpu_percent'],
                        message=f"High CPU usage: {metrics.cpu_percent:.1f}%",
                    )
                )

        # Memory usage alert
        if metrics.memory_percent > self.thresholds['memory_percent']:
            if self._should_send_alert('memory_high', current_time):
                alerts.append(
                    PerformanceAlert(
                        alert_id=f"memory_high_{int(current_time)}",
                        timestamp=metrics.timestamp,
                        severity="high" if metrics.memory_percent > 95 else "medium",
                        category="system",
                        metric="memory_percent",
                        current_value=metrics.memory_percent,
                        threshold_value=self.thresholds['memory_percent'],
                        message=f"High memory usage: {metrics.memory_percent:.1f}%",
                    )
                )

        # Disk usage alert
        if metrics.disk_percent > self.thresholds['disk_percent']:
            if self._should_send_alert('disk_high', current_time):
                alerts.append(
                    PerformanceAlert(
                        alert_id=f"disk_high_{int(current_time)}",
                        timestamp=metrics.timestamp,
                        severity="critical" if metrics.disk_percent > 95 else "high",
                        category="system",
                        metric="disk_percent",
                        current_value=metrics.disk_percent,
                        threshold_value=self.thresholds['disk_percent'],
                        message=f"High disk usage: {metrics.disk_percent:.1f}%",
                    )
                )

        return alerts

    def check_network_alerts(self, metrics: NetworkMetrics) -> List[PerformanceAlert]:
        """Check network metrics for alert conditions"""
        alerts = []
        current_time = time.time()

        # High ping latency alert
        if metrics.ping_latency_ms > self.thresholds['ping_latency_ms']:
            if self._should_send_alert('ping_high', current_time):
                alerts.append(
                    PerformanceAlert(
                        alert_id=f"ping_high_{int(current_time)}",
                        timestamp=metrics.timestamp,
                        severity="medium",
                        category="network",
                        metric="ping_latency_ms",
                        current_value=metrics.ping_latency_ms,
                        threshold_value=self.thresholds['ping_latency_ms'],
                        message=f"High network latency: {metrics.ping_latency_ms:.1f}ms",
                    )
                )

        return alerts

    def check_ros2_alerts(self, metrics: ROS2Metrics) -> List[PerformanceAlert]:
        """Check ROS2 metrics for alert conditions"""
        alerts = []
        current_time = time.time()

        # Low node count alert
        if metrics.node_count < self.thresholds['node_count_min']:
            if self._should_send_alert('nodes_low', current_time):
                alerts.append(
                    PerformanceAlert(
                        alert_id=f"nodes_low_{int(current_time)}",
                        timestamp=metrics.timestamp,
                        severity="high",
                        category="ros2",
                        metric="node_count",
                        current_value=metrics.node_count,
                        threshold_value=self.thresholds['node_count_min'],
                        message=f"Low ROS2 node count: {metrics.node_count}",
                    )
                )

        return alerts

    def _should_send_alert(self, alert_type: str, current_time: float) -> bool:
        """Check if alert should be sent based on cooldown"""
        last_alert_time = self.alert_cooldown.get(alert_type, 0)
        if current_time - last_alert_time > self.cooldown_period:
            self.alert_cooldown[alert_type] = current_time
            return True
        return False


class PerformanceService:
    """Main performance monitoring service"""

    def __init__(self):
        self.node: Optional[Node] = None
        self.executor = None
        self.executor_thread = None
        self.running = False

        # Monitoring components
        self.system_monitor = SystemMonitor()
        self.network_monitor = NetworkMonitor()
        self.ros2_monitor = None  # Initialized later with ROS2 node
        self.alert_manager = None
        self.data_store = PerformanceDataStore()

        # Configuration
        self.config = self._load_config()
        self.monitoring_thread = None
        self.update_interval = self.config.get('update_interval_seconds', 5.0)

    def _load_config(self) -> Dict[str, Any]:
        """Load performance configuration"""
        config_path = Path(__file__).parent.parent / "config" / "dashboard.yaml"
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    return config.get('performance', {})
        except Exception:
            pass
        return {}

    async def initialize(self):
        """Initialize the performance service"""
        try:
            try:
                rclpy.init()
            except RuntimeError:
                pass  # Already initialized

            self.node = Node('pragati_performance_service')
            self.executor = MultiThreadedExecutor(num_threads=2)
            self.executor.add_node(self.node)

            # Initialize ROS2 monitor with node
            self.ros2_monitor = ROS2PerformanceMonitor(self.node)

            # Initialize alert manager
            self.alert_manager = PerformanceAlertManager(self.config)

            # Start executor in separate thread
            self.executor_thread = threading.Thread(target=self._run_executor, daemon=True)
            self.running = True
            self.executor_thread.start()

            # Start monitoring thread
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()

            self.node.get_logger().info("Performance service initialized")

        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Failed to initialize Performance Service: {e}")
            raise

    def _run_executor(self):
        """Run ROS2 executor in separate thread"""
        try:
            while self.running and rclpy.ok():
                self.executor.spin_once(timeout_sec=1.0)
        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Executor error: {e}")

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Collect metrics
                system_metrics = self.system_monitor.collect_system_metrics()
                network_metrics = self.network_monitor.collect_network_metrics()

                if self.ros2_monitor:
                    ros2_metrics = self.ros2_monitor.collect_ros2_metrics()
                    self.data_store.add_ros2_metrics(ros2_metrics)

                    # Check ROS2 alerts
                    if self.alert_manager:
                        ros2_alerts = self.alert_manager.check_ros2_alerts(ros2_metrics)
                        for alert in ros2_alerts:
                            self.data_store.add_alert(alert)

                # Store metrics
                self.data_store.add_system_metrics(system_metrics)
                self.data_store.add_network_metrics(network_metrics)

                # Check alerts
                if self.alert_manager:
                    system_alerts = self.alert_manager.check_system_alerts(system_metrics)
                    network_alerts = self.alert_manager.check_network_alerts(network_metrics)

                    for alert in system_alerts + network_alerts:
                        self.data_store.add_alert(alert)

                # Wait for next collection cycle
                time.sleep(
                    self.update_interval
                )  # BLOCKING_SLEEP_OK: performance monitoring interval — dedicated thread — reviewed 2026-03-14

            except Exception as e:
                if self.node:
                    self.node.get_logger().error(f"Monitoring loop error: {e}")
                time.sleep(
                    self.update_interval
                )  # BLOCKING_SLEEP_OK: performance monitoring interval — dedicated thread — reviewed 2026-03-14

    async def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        try:
            current_time = datetime.now(timezone.utc).isoformat()

            # Get latest metrics
            system_metrics = self.system_monitor.collect_system_metrics()
            network_metrics = self.network_monitor.collect_network_metrics()

            result = {
                "timestamp": current_time,
                "system": system_metrics.to_dict(),
                "network": network_metrics.to_dict(),
            }

            if self.ros2_monitor:
                ros2_metrics = self.ros2_monitor.collect_ros2_metrics()
                result["ros2"] = ros2_metrics.to_dict()

            return result

        except Exception as e:
            error_msg = f"Error getting current metrics: {str(e)}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"error": error_msg, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def get_historical_metrics(self, minutes: int = 60) -> Dict[str, Any]:
        """Get historical performance metrics"""
        try:
            system_history = [
                m.to_dict() for m in self.data_store.get_recent_system_metrics(minutes)
            ]
            network_history = [
                m.to_dict() for m in self.data_store.get_recent_network_metrics(minutes)
            ]
            ros2_history = [m.to_dict() for m in self.data_store.get_recent_ros2_metrics(minutes)]

            return {
                "system_metrics": system_history,
                "network_metrics": network_history,
                "ros2_metrics": ros2_history,
                "data_points": len(system_history),
                "time_range_minutes": minutes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            error_msg = f"Error getting historical metrics: {str(e)}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"error": error_msg, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def get_performance_alerts(self, minutes: int = 1440) -> Dict[str, Any]:
        """Get performance alerts"""
        try:
            alerts = [a.to_dict() for a in self.data_store.get_recent_alerts(minutes)]

            # Count alerts by severity
            alert_counts = defaultdict(int)
            for alert in alerts:
                alert_counts[alert['severity']] += 1

            return {
                "alerts": alerts,
                "alert_counts": dict(alert_counts),
                "total_alerts": len(alerts),
                "time_range_minutes": minutes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            error_msg = f"Error getting alerts: {str(e)}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"error": error_msg, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def acknowledge_alert(self, alert_id: str) -> Dict[str, Any]:
        """Acknowledge a performance alert"""
        try:
            for alert in self.data_store.alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    return {"success": True, "alert_id": alert_id, "message": "Alert acknowledged"}

            return {"success": False, "error": f"Alert {alert_id} not found"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary statistics"""
        try:
            # Get recent data for summary
            recent_system = self.data_store.get_recent_system_metrics(60)  # Last hour
            recent_network = self.data_store.get_recent_network_metrics(60)
            recent_ros2 = self.data_store.get_recent_ros2_metrics(60)
            recent_alerts = self.data_store.get_recent_alerts(1440)  # Last 24 hours

            summary = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data_points": {
                    "system": len(recent_system),
                    "network": len(recent_network),
                    "ros2": len(recent_ros2),
                },
                "alerts": {
                    "total": len(recent_alerts),
                    "unacknowledged": len([a for a in recent_alerts if not a.acknowledged]),
                    "by_severity": {},
                },
                "averages": {},
                "health_score": 100,  # Will be calculated based on metrics
            }

            # Calculate averages
            if recent_system:
                avg_cpu = statistics.mean([m.cpu_percent for m in recent_system])
                avg_memory = statistics.mean([m.memory_percent for m in recent_system])
                summary["averages"]["cpu_percent"] = avg_cpu
                summary["averages"]["memory_percent"] = avg_memory

                # Simple health score calculation
                health_score = 100
                if avg_cpu > 80:
                    health_score -= 20
                elif avg_cpu > 60:
                    health_score -= 10

                if avg_memory > 80:
                    health_score -= 20
                elif avg_memory > 60:
                    health_score -= 10

                summary["health_score"] = max(0, health_score)

            if recent_network:
                avg_ping = statistics.mean([m.ping_latency_ms for m in recent_network])
                summary["averages"]["ping_latency_ms"] = avg_ping

            # Alert counts by severity
            alert_counts = defaultdict(int)
            for alert in recent_alerts:
                alert_counts[alert.severity] += 1
            summary["alerts"]["by_severity"] = dict(alert_counts)

            return summary

        except Exception as e:
            error_msg = f"Error getting performance summary: {str(e)}"
            if self.node:
                self.node.get_logger().error(error_msg)
            return {"error": error_msg, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def shutdown(self):
        """Shutdown the performance service"""
        try:
            self.running = False

            # Stop monitoring thread
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                self.monitoring_thread.join(timeout=2.0)

            # Shutdown executor
            if self.executor:
                self.executor.shutdown()

            if self.executor_thread and self.executor_thread.is_alive():
                self.executor_thread.join(timeout=2.0)

            # Destroy node
            if self.node:
                self.node.destroy_node()
                self.node = None

            if rclpy.ok():
                rclpy.shutdown()

        except Exception as e:
            print(f"Error during performance service shutdown: {e}")


# Global service instance
performance_service = PerformanceService()


async def get_performance_service() -> PerformanceService:
    """Get the global performance service instance"""
    if not performance_service.node:
        await performance_service.initialize()
    return performance_service


# ===================================================================
# Enhanced Performance Monitoring (merged from enhanced_performance_service.py)
# ===================================================================

logger = logging.getLogger(__name__)


@dataclass
class CircularBuffer:
    """Fixed-size circular buffer for time-series data"""

    max_size: int
    data: deque = field(default_factory=deque)

    def append(self, value: Tuple[float, Any]):
        """Append (timestamp, value) tuple"""
        if len(self.data) >= self.max_size:
            self.data.popleft()
        self.data.append(value)

    def get_recent(self, seconds: Optional[float] = None) -> List[Tuple[float, Any]]:
        """Get recent data within time window"""
        if seconds is None:
            return list(self.data)

        cutoff = time.time() - seconds
        return [(ts, val) for ts, val in self.data if ts >= cutoff]

    def get_latest(self) -> Optional[Tuple[float, Any]]:
        """Get most recent value"""
        return self.data[-1] if self.data else None

    def clear(self):
        """Clear all data"""
        self.data.clear()


@dataclass
class NodeResourceStats:
    """Per-node resource usage statistics"""

    node_name: str
    pid: Optional[int] = None
    cpu_percent: CircularBuffer = field(default_factory=lambda: CircularBuffer(60))
    memory_mb: CircularBuffer = field(default_factory=lambda: CircularBuffer(60))
    last_update: float = 0.0

    def update(self, cpu: float, mem_mb: float):
        """Update stats with current values"""
        now = time.time()
        self.cpu_percent.append((now, cpu))
        self.memory_mb.append((now, mem_mb))
        self.last_update = now


@dataclass
class TopicPerformanceStats:
    """Per-topic performance metrics"""

    topic_name: str
    message_count: int = 0
    last_message_time: float = 0.0
    rate_hz: CircularBuffer = field(default_factory=lambda: CircularBuffer(60))
    latency_ms: CircularBuffer = field(default_factory=lambda: CircularBuffer(100))
    size_bytes: CircularBuffer = field(default_factory=lambda: CircularBuffer(60))

    def update_rate(self, hz: float):
        """Update publication rate"""
        self.rate_hz.append((time.time(), hz))

    def record_message(
        self,
        size_bytes: Optional[int] = None,
        latency_ms: Optional[float] = None,
    ):
        """Record message reception"""
        now = time.time()
        self.message_count += 1
        self.last_message_time = now

        if size_bytes is not None:
            self.size_bytes.append((now, size_bytes))

        if latency_ms is not None:
            self.latency_ms.append((now, latency_ms))


class EnhancedPerformanceMonitor:
    """
    Enhanced performance monitoring with RPi optimization

    Features:
    - Per-node CPU/memory tracking
    - Topic rate and latency monitoring
    - System-wide resource overview
    - Circular buffers for history (fixed memory)
    - Adaptive sampling rates
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Configuration
        self.update_rate_hz = self.config.get('update_rate_hz', 1.0)
        self.critical_nodes = set(self.config.get('critical_nodes', []))
        self.sample_rate_critical = 1.0
        self.sample_rate_standard = self.config.get('sampling', {}).get('standard_topics', 0.2)

        # Storage
        self.node_stats: Dict[str, NodeResourceStats] = {}
        self.topic_stats: Dict[str, TopicPerformanceStats] = {}
        self.system_history = CircularBuffer(300)

        # Process tracking
        self.process_cache: Dict[int, psutil.Process] = {}
        self.node_pid_map: Dict[str, int] = {}

        # Monitoring control
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()

        # Delta tracking for efficient updates
        self.last_broadcast_state: Dict = {}

        logger.info("Enhanced Performance Monitor initialized")

    def start(self):
        """Start background monitoring"""
        if self.running:
            logger.warning("Monitor already running")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Performance monitoring started")

    def stop(self):
        """Stop monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        logger.info("Performance monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self._update_system_stats()
                self._update_node_stats()
                time.sleep(
                    1.0 / self.update_rate_hz
                )  # BLOCKING_SLEEP_OK: performance monitoring interval — dedicated thread — reviewed 2026-03-14
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)

    def _update_system_stats(self):
        """Update system-wide resource stats"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0)
            memory = psutil.virtual_memory()

            system_data = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_mb': round(memory.used / (1024 * 1024), 2),
                'memory_available_mb': round(memory.available / (1024 * 1024), 2),
            }

            with self.lock:
                self.system_history.append((time.time(), system_data))

        except Exception as e:
            logger.error(f"Error updating system stats: {e}")

    def _update_node_stats(self):
        """Update per-node resource usage"""
        try:
            # Get all ROS2 node processes
            ros_processes = self._find_ros_processes()

            with self.lock:
                for node_name, pid in ros_processes.items():
                    if node_name not in self.node_stats:
                        self.node_stats[node_name] = NodeResourceStats(node_name, pid)

                    # Get process object (cached)
                    proc = self._get_process(pid)
                    if proc is None:
                        continue

                    # Adaptive sampling
                    is_critical = node_name in self.critical_nodes
                    stats = self.node_stats[node_name]
                    if not is_critical and time.time() - stats.last_update < (
                        1.0 / self.sample_rate_standard
                    ):
                        continue

                    try:
                        cpu_percent = proc.cpu_percent(interval=0)
                        memory_info = proc.memory_info()
                        memory_mb = round(memory_info.rss / (1024 * 1024), 2)

                        stats.update(cpu_percent, memory_mb)

                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                    ):
                        if pid in self.process_cache:
                            del self.process_cache[pid]

        except Exception as e:
            logger.error(f"Error updating node stats: {e}")

    # Cache for ros2 node list results
    _ros_node_cache: Optional[Dict[str, int]] = None
    _ros_node_cache_time: float = 0

    def _find_ros_processes(self) -> Dict[str, int]:
        """Find ROS2 node processes using system_state from ros2_monitor.

        Reads node names from the shared ``system_state`` dict (populated
        by ``ros2_monitor`` via rclpy graph introspection), then maps each
        node name to its OS PID via process table inspection.  Results are
        cached for 5 seconds to avoid repeated process scans.
        """
        now = time.time()
        if self._ros_node_cache is not None and now - self._ros_node_cache_time < 5.0:
            return self._ros_node_cache

        ros_processes: Dict[str, int] = {}

        try:
            state = _get_system_state()
            nodes = state.get("nodes", {})
            node_names = list(nodes.keys())

            if node_names:
                short_names = {n.lstrip('/'): n for n in node_names}

                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = proc.info.get('cmdline', [])
                        if not cmdline:
                            continue
                        cmdline_str = ' '.join(cmdline)

                        for short, full in list(short_names.items()):
                            if short in cmdline_str or full in cmdline_str:
                                ros_processes[short] = proc.info['pid']
                                del short_names[short]
                                break

                        if not short_names:
                            break
                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                    ):
                        continue

        except Exception as e:
            logger.error("Error finding ROS processes: %s", e)

        self._ros_node_cache = ros_processes
        self._ros_node_cache_time = now
        return ros_processes

    def _extract_node_name(self, cmdline: List[str]) -> Optional[str]:
        """Extract node name from command line args"""
        for i, arg in enumerate(cmdline):
            if '__node:=' in arg:
                if '=' in arg:
                    name = arg.split('=', 1)[1]
                    return name if name else None
                elif i + 1 < len(cmdline):
                    return cmdline[i + 1]

            if arg == '__node' and i + 1 < len(cmdline):
                return cmdline[i + 1]

        if cmdline:
            for arg in cmdline:
                if arg in ['python3', 'python', 'ros2', 'launch']:
                    continue

                name = arg.split('/')[-1]

                if name and ('_node' in name or 'node_' in name or name.endswith('_server')):
                    return name

            name = cmdline[0].split('/')[-1]
            if name and name not in ['python3', 'python', 'ros2', 'bash', 'sh']:
                return name

        return None

    def _get_process(self, pid: int) -> Optional[psutil.Process]:
        """Get process object with caching"""
        if pid not in self.process_cache:
            try:
                self.process_cache[pid] = psutil.Process(pid)
            except psutil.NoSuchProcess:
                return None

        return self.process_cache.get(pid)

    def update_topic_rate(self, topic_name: str, rate_hz: float):
        """Update topic publication rate"""
        with self.lock:
            if topic_name not in self.topic_stats:
                self.topic_stats[topic_name] = TopicPerformanceStats(topic_name)

            self.topic_stats[topic_name].update_rate(rate_hz)

    def record_message(
        self,
        topic_name: str,
        size_bytes: Optional[int] = None,
        publish_time: Optional[float] = None,
    ):
        """Record message reception with optional latency"""
        latency_ms = None
        if publish_time is not None:
            latency_ms = (time.time() - publish_time) * 1000

        with self.lock:
            if topic_name not in self.topic_stats:
                self.topic_stats[topic_name] = TopicPerformanceStats(topic_name)

            self.topic_stats[topic_name].record_message(size_bytes, latency_ms)

    def get_node_performance(
        self,
        node_name: Optional[str] = None,
        duration_sec: int = 60,
    ) -> Dict:
        """Get node performance data"""
        with self.lock:
            if node_name:
                if node_name not in self.node_stats:
                    return {"error": f"Node {node_name} not found"}

                stats = self.node_stats[node_name]
                return {
                    "node_name": node_name,
                    "pid": stats.pid,
                    "cpu_history": (stats.cpu_percent.get_recent(duration_sec)),
                    "memory_history": (stats.memory_mb.get_recent(duration_sec)),
                    "current_cpu": (stats.cpu_percent.get_latest()),
                    "current_memory": (stats.memory_mb.get_latest()),
                }
            else:
                return {
                    node_name: {
                        "pid": stats.pid,
                        "current_cpu": (
                            stats.cpu_percent.get_latest()[1]
                            if stats.cpu_percent.get_latest()
                            else 0
                        ),
                        "current_memory": (
                            stats.memory_mb.get_latest()[1] if stats.memory_mb.get_latest() else 0
                        ),
                        "last_update": stats.last_update,
                    }
                    for node_name, stats in self.node_stats.items()
                }

    def get_topic_performance(self, topic_name: Optional[str] = None) -> Dict:
        """Get topic performance data"""
        with self.lock:
            if topic_name:
                if topic_name not in self.topic_stats:
                    return {"error": (f"Topic {topic_name} not found")}

                stats = self.topic_stats[topic_name]
                return {
                    "topic_name": topic_name,
                    "message_count": stats.message_count,
                    "current_rate": (stats.rate_hz.get_latest()),
                    "rate_history": (stats.rate_hz.get_recent(60)),
                    "latency_history": (stats.latency_ms.get_recent()),
                    "size_history": (stats.size_bytes.get_recent(60)),
                }
            else:
                return {
                    topic_name: {
                        "message_count": (stats.message_count),
                        "current_rate": (
                            stats.rate_hz.get_latest()[1] if stats.rate_hz.get_latest() else 0
                        ),
                        "last_message": (stats.last_message_time),
                    }
                    for topic_name, stats in self.topic_stats.items()
                }

    def get_system_performance(self, duration_sec: int = 300) -> Dict:
        """Get system-wide performance data"""
        with self.lock:
            history = self.system_history.get_recent(duration_sec)
            latest = self.system_history.get_latest()

            return {
                "current": latest[1] if latest else {},
                "history": history,
                "duration_sec": duration_sec,
            }

    def get_summary(self) -> Dict:
        """Get performance summary for dashboard"""
        with self.lock:
            system_latest = self.system_history.get_latest()
            system_current = system_latest[1] if system_latest else {}

            node_cpu = [
                (
                    name,
                    (stats.cpu_percent.get_latest()[1] if stats.cpu_percent.get_latest() else 0),
                )
                for name, stats in self.node_stats.items()
            ]
            top_cpu = sorted(node_cpu, key=lambda x: x[1], reverse=True)[:5]

            node_mem = [
                (
                    name,
                    (stats.memory_mb.get_latest()[1] if stats.memory_mb.get_latest() else 0),
                )
                for name, stats in self.node_stats.items()
            ]
            top_memory = sorted(node_mem, key=lambda x: x[1], reverse=True)[:5]

            active_topics = len(
                [t for t in self.topic_stats.values() if time.time() - t.last_message_time < 5.0]
            )

            return {
                "timestamp": time.time(),
                "system": system_current,
                "nodes": {
                    "total": len(self.node_stats),
                    "top_cpu": [{"name": n, "cpu": c} for n, c in top_cpu],
                    "top_memory": [{"name": n, "memory_mb": m} for n, m in top_memory],
                },
                "topics": {
                    "total": len(self.topic_stats),
                    "active": active_topics,
                },
            }

    def get_delta_update(self) -> Optional[Dict]:
        """Get delta update since last broadcast"""
        current = self.get_summary()
        # TODO: Implement proper delta detection
        return current

    def update_from_system_state(self, nodes: Dict):
        """Update node stats from dashboard system_state"""
        with self.lock:
            for node_name in nodes.keys():
                pid = self._find_pid_for_node_name(node_name)
                if pid:
                    if node_name not in self.node_stats:
                        self.node_stats[node_name] = NodeResourceStats(node_name, pid)

                    proc = self._get_process(pid)
                    if proc:
                        try:
                            cpu_percent = proc.cpu_percent(interval=0)
                            memory_info = proc.memory_info()
                            memory_mb = round(
                                memory_info.rss / (1024 * 1024),
                                2,
                            )
                            self.node_stats[node_name].update(cpu_percent, memory_mb)
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                        ):
                            pass

    def _find_pid_for_node_name(self, node_name: str) -> Optional[int]:
        """Find PID for a given ROS2 node name"""
        try:
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline:
                        cmdline_str = ' '.join(cmdline)
                        if node_name in cmdline_str:
                            return proc.info['pid']
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                ):
                    continue
        except Exception:
            pass
        return None


# Enhanced performance monitor singleton
_performance_monitor: Optional[EnhancedPerformanceMonitor] = None


def get_performance_monitor(
    config: Optional[Dict] = None,
) -> EnhancedPerformanceMonitor:
    """Get or create the performance monitor singleton"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = EnhancedPerformanceMonitor(config)
    return _performance_monitor


def initialize_performance_monitoring(
    config: Optional[Dict] = None,
):
    """Initialize and start performance monitoring"""
    monitor = get_performance_monitor(config)
    monitor.start()
    return monitor
