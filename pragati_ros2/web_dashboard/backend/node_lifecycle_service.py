#!/usr/bin/env python3
"""
Node Lifecycle Management Service for Pragati ROS2 Dashboard
============================================================

Provides comprehensive node lifecycle management including:
- Starting and stopping nodes safely
- Parameter management with validation
- Health monitoring and crash detection
- Dependency tracking and startup ordering
- Resource usage monitoring

This service extends the dashboard with Phase 2 capabilities.
"""

import asyncio
import subprocess
import json
import time
import threading
import signal
import os
import psutil
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import yaml
import traceback

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.parameter import Parameter
    from rcl_interfaces.msg import ParameterDescriptor
    from rcl_interfaces.srv import GetParameters, SetParameters, ListParameters, DescribeParameters
    from std_msgs.msg import String

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


@dataclass
class NodeInfo:
    """Information about a ROS2 node"""

    name: str
    namespace: str = "/"
    pid: Optional[int] = None
    status: str = "unknown"  # running, stopped, crashed, starting, stopping
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    uptime_seconds: float = 0.0
    restart_count: int = 0
    last_seen: Optional[str] = None
    publishers: List[str] = None
    subscribers: List[str] = None
    services: List[str] = None
    parameters: Dict[str, Any] = None
    launch_command: Optional[str] = None
    working_directory: Optional[str] = None

    def __post_init__(self):
        if self.publishers is None:
            self.publishers = []
        if self.subscribers is None:
            self.subscribers = []
        if self.services is None:
            self.services = []
        if self.parameters is None:
            self.parameters = {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NodeOperation:
    """Represents a node lifecycle operation"""

    operation_id: str
    node_name: str
    operation_type: str  # start, stop, restart, set_parameter
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NodeHealthMonitor:
    """Monitors node health and performance metrics"""

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.health_history: deque = deque(maxlen=100)
        self.last_check = 0.0
        self.consecutive_failures = 0
        self.total_restarts = 0

    def update_health(
        self, is_healthy: bool, cpu_percent: float = 0.0, memory_mb: float = 0.0
    ) -> Dict[str, Any]:
        """Update health metrics"""
        current_time = time.time()

        if not is_healthy:
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        health_data = {
            "timestamp": current_time,
            "healthy": is_healthy,
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
            "consecutive_failures": self.consecutive_failures,
        }

        self.health_history.append(health_data)
        self.last_check = current_time

        return health_data

    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary"""
        if not self.health_history:
            return {"status": "unknown", "last_check": None}

        recent_health = list(self.health_history)[-10:]  # Last 10 checks
        healthy_count = sum(1 for h in recent_health if h["healthy"])

        avg_cpu = sum(h["cpu_percent"] for h in recent_health) / len(recent_health)
        avg_memory = sum(h["memory_mb"] for h in recent_health) / len(recent_health)

        health_percentage = (healthy_count / len(recent_health)) * 100

        if health_percentage >= 90:
            status = "excellent"
        elif health_percentage >= 70:
            status = "good"
        elif health_percentage >= 50:
            status = "fair"
        else:
            status = "poor"

        return {
            "status": status,
            "health_percentage": health_percentage,
            "consecutive_failures": self.consecutive_failures,
            "total_restarts": self.total_restarts,
            "avg_cpu_percent": avg_cpu,
            "avg_memory_mb": avg_memory,
            "last_check": self.last_check,
            "uptime_hours": (
                (time.time() - recent_health[0]["timestamp"]) / 3600 if recent_health else 0
            ),
        }


class NodeLifecycleService:
    """Service for managing ROS2 node lifecycles"""

    def __init__(self):
        self.node: Optional[Node] = None
        self.executor = None
        self.executor_thread = None
        self.running = False

        # Node tracking
        self.nodes: Dict[str, NodeInfo] = {}
        self.node_processes: Dict[str, subprocess.Popen] = {}
        self.health_monitors: Dict[str, NodeHealthMonitor] = {}
        self.operations: Dict[str, NodeOperation] = {}

        # Monitoring
        self.monitoring_thread = None
        self.last_discovery_time = 0.0
        self.discovery_interval = 5.0  # seconds

        # Configuration
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration"""
        config_path = Path(__file__).parent.parent / "config" / "dashboard.yaml"
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    return config.get('pragati', {})
        except Exception:
            pass
        return {}

    async def initialize(self):
        """Initialize the node lifecycle service"""
        try:
            if not rclpy.ok():
                rclpy.init()

            self.node = Node('web_dashboard_lifecycle')
            self.executor = MultiThreadedExecutor(num_threads=2)
            self.executor.add_node(self.node)

            # Start executor in separate thread
            self.executor_thread = threading.Thread(target=self._run_executor, daemon=True)
            self.running = True
            self.executor_thread.start()

            # Start monitoring thread
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()

            # Initial node discovery
            await self._discover_nodes()

            self.node.get_logger().info("Node lifecycle service initialized")

        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Failed to initialize Node Lifecycle Service: {e}")
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
                current_time = time.time()

                # Periodic node discovery
                if current_time - self.last_discovery_time > self.discovery_interval:
                    # Run discovery in a new event loop for this thread
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self._discover_nodes())
                        loop.close()
                    except Exception as e:
                        if self.node:
                            self.node.get_logger().error(f"Discovery error: {e}")
                    finally:
                        self.last_discovery_time = current_time

                # Update node health
                self._update_node_health()

                # Clean up completed operations
                self._cleanup_operations()

                time.sleep(
                    1.0
                )  # BLOCKING_SLEEP_OK: node lifecycle monitor — dedicated thread — reviewed 2026-03-14

            except Exception as e:
                if self.node:
                    self.node.get_logger().error(f"Monitoring loop error: {e}")
                time.sleep(
                    5.0
                )  # BLOCKING_SLEEP_OK: node lifecycle monitor — dedicated thread — reviewed 2026-03-14

    async def _discover_nodes(self):
        """Discover running ROS2 nodes"""
        try:
            if not self.node:
                return

            # Get current node list
            node_names = self.node.get_node_names()
            current_nodes = set()

            for node_name in node_names:
                current_nodes.add(node_name)

                if node_name not in self.nodes:
                    # New node discovered
                    node_info = NodeInfo(
                        name=node_name,
                        status="running",
                        last_seen=datetime.now(timezone.utc).isoformat(),
                    )

                    # Get detailed node information
                    await self._get_node_details(node_info)

                    self.nodes[node_name] = node_info
                    self.health_monitors[node_name] = NodeHealthMonitor(node_name)

                    if self.node:
                        self.node.get_logger().info(f"Discovered new node: {node_name}")
                else:
                    # Update existing node
                    self.nodes[node_name].last_seen = datetime.now(timezone.utc).isoformat()
                    self.nodes[node_name].status = "running"

            # Mark missing nodes as stopped
            for node_name in list(self.nodes.keys()):
                if node_name not in current_nodes:
                    self.nodes[node_name].status = "stopped"

        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Node discovery error: {e}")

    async def _get_node_details(self, node_info: NodeInfo):
        """Get detailed information about a node using rclpy introspection."""
        try:
            if not self.node:
                return

            # Parse namespace and bare name from node_info.name
            # e.g. "/ns/node" -> namespace="/ns", name="node"
            # e.g. "node" or "/node" -> namespace="/", name="node"
            name = node_info.name
            namespace = "/"
            if "/" in name and name != "/":
                parts = name.rsplit("/", 1)
                if len(parts) == 2 and parts[0]:
                    namespace = parts[0]
                    name = parts[1]
                elif len(parts) == 2 and not parts[0]:
                    # "/node_name" case
                    name = parts[1]

            try:
                pubs = self.node.get_publisher_names_and_types_by_node(name, namespace)
                node_info.publishers = [p[0] for p in pubs]
            except Exception:
                node_info.publishers = []

            try:
                subs = self.node.get_subscriber_names_and_types_by_node(name, namespace)
                node_info.subscribers = [s[0] for s in subs]
            except Exception:
                node_info.subscribers = []

            try:
                srvs = self.node.get_service_names_and_types_by_node(name, namespace)
                node_info.services = [s[0] for s in srvs]
            except Exception:
                node_info.services = []

        except Exception as e:
            if self.node:
                self.node.get_logger().warn(f"Could not get details for node {node_info.name}: {e}")

    def _update_node_health(self):
        """Update health metrics for all nodes"""
        try:
            for node_name, node_info in self.nodes.items():
                if node_name not in self.health_monitors:
                    self.health_monitors[node_name] = NodeHealthMonitor(node_name)

                monitor = self.health_monitors[node_name]

                # Check if node is still running
                is_healthy = node_info.status == "running"

                # Get process metrics if available
                cpu_percent = 0.0
                memory_mb = 0.0

                if node_info.pid:
                    try:
                        process = psutil.Process(node_info.pid)
                        cpu_percent = process.cpu_percent()
                        memory_mb = process.memory_info().rss / 1024 / 1024
                        node_info.cpu_percent = cpu_percent
                        node_info.memory_mb = memory_mb
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # Process no longer exists
                        is_healthy = False
                        node_info.status = "stopped"
                        node_info.pid = None

                monitor.update_health(is_healthy, cpu_percent, memory_mb)

        except Exception as e:
            if self.node:
                self.node.get_logger().error(f"Health update error: {e}")

    def _cleanup_operations(self):
        """Clean up completed operations"""
        current_time = time.time()
        completed_operations = []

        for op_id, operation in self.operations.items():
            if operation.status in ["completed", "failed"]:
                # Keep operations for 5 minutes after completion
                if operation.completed_at:
                    completed_time = datetime.fromisoformat(
                        operation.completed_at.replace('Z', '+00:00')
                    ).timestamp()
                    if current_time - completed_time > 300:  # 5 minutes
                        completed_operations.append(op_id)

        for op_id in completed_operations:
            del self.operations[op_id]

    async def start_node(
        self,
        node_name: str,
        launch_command: Optional[str] = None,
        working_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a ROS2 node"""
        operation_id = f"start_{node_name}_{int(time.time())}"

        try:
            operation = NodeOperation(
                operation_id=operation_id,
                node_name=node_name,
                operation_type="start",
                status="running",
                details={"launch_command": launch_command, "working_dir": working_dir},
            )

            self.operations[operation_id] = operation

            # Check if node is already running
            if node_name in self.nodes and self.nodes[node_name].status == "running":
                operation.status = "failed"
                operation.error_message = f"Node {node_name} is already running"
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                return {
                    "success": False,
                    "operation_id": operation_id,
                    "error": operation.error_message,
                }

            # Default launch command if not provided
            if not launch_command:
                launch_command = f"ros2 run {node_name} {node_name}"

            # Start the process
            process = await asyncio.create_subprocess_shell(
                launch_command,
                cwd=working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait a moment to see if process starts successfully
            await asyncio.sleep(1.0)

            if process.returncode is None:  # Process is still running
                # Create node info
                node_info = NodeInfo(
                    name=node_name,
                    status="running",
                    pid=process.pid,
                    launch_command=launch_command,
                    working_directory=working_dir,
                    last_seen=datetime.now(timezone.utc).isoformat(),
                )

                self.nodes[node_name] = node_info
                self.node_processes[node_name] = process

                if node_name not in self.health_monitors:
                    self.health_monitors[node_name] = NodeHealthMonitor(node_name)

                operation.status = "completed"
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                if self.node:
                    self.node.get_logger().info(f"Successfully started node: {node_name}")

                return {
                    "success": True,
                    "operation_id": operation_id,
                    "node_name": node_name,
                    "pid": process.pid,
                }
            else:
                # Process failed to start
                stdout, stderr = await process.communicate()
                error_msg = (
                    f"Failed to start node: {stderr.decode() if stderr else 'Unknown error'}"
                )

                operation.status = "failed"
                operation.error_message = error_msg
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                return {"success": False, "operation_id": operation_id, "error": error_msg}

        except Exception as e:
            error_msg = f"Exception starting node {node_name}: {str(e)}"

            if operation_id in self.operations:
                self.operations[operation_id].status = "failed"
                self.operations[operation_id].error_message = error_msg
                self.operations[operation_id].completed_at = datetime.now(timezone.utc).isoformat()

            if self.node:
                self.node.get_logger().error(error_msg)

            return {"success": False, "operation_id": operation_id, "error": error_msg}

    async def stop_node(self, node_name: str, force: bool = False) -> Dict[str, Any]:
        """Stop a ROS2 node"""
        operation_id = f"stop_{node_name}_{int(time.time())}"

        try:
            operation = NodeOperation(
                operation_id=operation_id,
                node_name=node_name,
                operation_type="stop",
                status="running",
                details={"force": force},
            )

            self.operations[operation_id] = operation

            # Check if we have the process
            if node_name in self.node_processes:
                process = self.node_processes[node_name]

                try:
                    if force:
                        process.kill()
                    else:
                        process.terminate()

                    # Wait for process to exit
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        if not force:
                            process.kill()
                            await process.wait()

                    # Clean up
                    del self.node_processes[node_name]

                    if node_name in self.nodes:
                        self.nodes[node_name].status = "stopped"
                        self.nodes[node_name].pid = None

                    operation.status = "completed"
                    operation.completed_at = datetime.now(timezone.utc).isoformat()

                    if self.node:
                        self.node.get_logger().info(f"Successfully stopped node: {node_name}")

                    return {"success": True, "operation_id": operation_id, "node_name": node_name}

                except Exception as e:
                    error_msg = f"Error stopping process for node {node_name}: {e}"
                    operation.status = "failed"
                    operation.error_message = error_msg
                    operation.completed_at = datetime.now(timezone.utc).isoformat()

                    return {"success": False, "operation_id": operation_id, "error": error_msg}
            else:
                # Try to find and stop by name using system commands
                try:
                    result = subprocess.run(
                        ['pkill', '-f', node_name], capture_output=True, text=True, timeout=10
                    )

                    if node_name in self.nodes:
                        self.nodes[node_name].status = "stopped"
                        self.nodes[node_name].pid = None

                    operation.status = "completed"
                    operation.completed_at = datetime.now(timezone.utc).isoformat()

                    return {
                        "success": True,
                        "operation_id": operation_id,
                        "node_name": node_name,
                        "method": "system_kill",
                    }

                except Exception as e:
                    error_msg = f"Could not stop node {node_name}: {e}"
                    operation.status = "failed"
                    operation.error_message = error_msg
                    operation.completed_at = datetime.now(timezone.utc).isoformat()

                    return {"success": False, "operation_id": operation_id, "error": error_msg}

        except Exception as e:
            error_msg = f"Exception stopping node {node_name}: {str(e)}"

            if operation_id in self.operations:
                self.operations[operation_id].status = "failed"
                self.operations[operation_id].error_message = error_msg
                self.operations[operation_id].completed_at = datetime.now(timezone.utc).isoformat()

            if self.node:
                self.node.get_logger().error(error_msg)

            return {"success": False, "operation_id": operation_id, "error": error_msg}

    async def restart_node(
        self,
        node_name: str,
        launch_command: Optional[str] = None,
        working_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Restart a ROS2 node"""
        operation_id = f"restart_{node_name}_{int(time.time())}"

        try:
            operation = NodeOperation(
                operation_id=operation_id,
                node_name=node_name,
                operation_type="restart",
                status="running",
            )

            self.operations[operation_id] = operation

            # Increment restart count
            if node_name in self.health_monitors:
                self.health_monitors[node_name].total_restarts += 1

            # Stop the node first
            stop_result = await self.stop_node(node_name, force=False)

            if not stop_result["success"]:
                operation.status = "failed"
                operation.error_message = (
                    f"Failed to stop node during restart: {stop_result.get('error')}"
                )
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                return {
                    "success": False,
                    "operation_id": operation_id,
                    "error": operation.error_message,
                }

            # Wait a moment
            await asyncio.sleep(2.0)

            # Start the node
            if not launch_command and node_name in self.nodes:
                launch_command = self.nodes[node_name].launch_command

            if not working_dir and node_name in self.nodes:
                working_dir = self.nodes[node_name].working_directory

            start_result = await self.start_node(node_name, launch_command, working_dir)

            if start_result["success"]:
                operation.status = "completed"
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                return {
                    "success": True,
                    "operation_id": operation_id,
                    "node_name": node_name,
                    "stop_operation": stop_result,
                    "start_operation": start_result,
                }
            else:
                operation.status = "failed"
                operation.error_message = (
                    f"Failed to start node during restart: {start_result.get('error')}"
                )
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                return {
                    "success": False,
                    "operation_id": operation_id,
                    "error": operation.error_message,
                }

        except Exception as e:
            error_msg = f"Exception restarting node {node_name}: {str(e)}"

            if operation_id in self.operations:
                self.operations[operation_id].status = "failed"
                self.operations[operation_id].error_message = error_msg
                self.operations[operation_id].completed_at = datetime.now(timezone.utc).isoformat()

            return {"success": False, "operation_id": operation_id, "error": error_msg}

    async def get_nodes(self) -> Dict[str, Any]:
        """Get list of all nodes with their information"""
        try:
            # Trigger fresh discovery
            await self._discover_nodes()

            nodes_data = {}
            for node_name, node_info in self.nodes.items():
                node_dict = node_info.to_dict()

                # Add health information
                if node_name in self.health_monitors:
                    health_summary = self.health_monitors[node_name].get_health_summary()
                    node_dict["health"] = health_summary

                nodes_data[node_name] = node_dict

            return {
                "nodes": nodes_data,
                "total_nodes": len(nodes_data),
                "running_nodes": len([n for n in nodes_data.values() if n["status"] == "running"]),
                "stopped_nodes": len([n for n in nodes_data.values() if n["status"] == "stopped"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            error_msg = f"Error getting nodes: {str(e)}"
            if self.node:
                self.node.get_logger().error(error_msg)

            return {
                "nodes": {},
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def get_node_parameters(self, node_name: str) -> Dict[str, Any]:
        """Get parameters for a specific node"""
        try:
            if not self.node:
                return {"parameters": {}, "error": "Service not initialized"}

            # Use ROS2 command to get parameters
            result = subprocess.run(
                ['ros2', 'param', 'list', node_name], capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                return {
                    "parameters": {},
                    "error": f"Could not list parameters for {node_name}: {result.stderr}",
                }

            param_names = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
            parameters = {}

            for param_name in param_names:
                try:
                    # Get parameter value
                    param_result = subprocess.run(
                        ['ros2', 'param', 'get', node_name, param_name],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )

                    if param_result.returncode == 0:
                        # Parse parameter value (this is a simple parser)
                        param_output = param_result.stdout.strip()
                        if param_output.startswith('Parameter value is: '):
                            param_value = param_output[20:]  # Remove prefix

                            # Try to parse as JSON
                            try:
                                parameters[param_name] = json.loads(param_value)
                            except json.JSONDecodeError:
                                parameters[param_name] = param_value
                        else:
                            parameters[param_name] = param_output

                except subprocess.TimeoutExpired:
                    parameters[param_name] = {"error": "timeout"}
                except Exception as e:
                    parameters[param_name] = {"error": str(e)}

            return {
                "node_name": node_name,
                "parameters": parameters,
                "parameter_count": len(parameters),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            error_msg = f"Error getting parameters for {node_name}: {str(e)}"
            if self.node:
                self.node.get_logger().error(error_msg)

            return {
                "parameters": {},
                "error": error_msg,
                "node_name": node_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def set_node_parameter(
        self, node_name: str, param_name: str, param_value: Any
    ) -> Dict[str, Any]:
        """Set a parameter for a specific node"""
        operation_id = f"set_param_{node_name}_{param_name}_{int(time.time())}"

        try:
            operation = NodeOperation(
                operation_id=operation_id,
                node_name=node_name,
                operation_type="set_parameter",
                status="running",
                details={"parameter": param_name, "value": param_value},
            )

            self.operations[operation_id] = operation

            # Format parameter value for ROS2 command
            if isinstance(param_value, (dict, list)):
                param_str = json.dumps(param_value)
            else:
                param_str = str(param_value)

            # Set parameter using ROS2 command
            result = subprocess.run(
                ['ros2', 'param', 'set', node_name, param_name, param_str],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                operation.status = "completed"
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                return {
                    "success": True,
                    "operation_id": operation_id,
                    "node_name": node_name,
                    "parameter": param_name,
                    "value": param_value,
                    "message": result.stdout.strip(),
                }
            else:
                error_msg = f"Failed to set parameter: {result.stderr.strip()}"
                operation.status = "failed"
                operation.error_message = error_msg
                operation.completed_at = datetime.now(timezone.utc).isoformat()

                return {"success": False, "operation_id": operation_id, "error": error_msg}

        except Exception as e:
            error_msg = f"Exception setting parameter {param_name} for {node_name}: {str(e)}"

            if operation_id in self.operations:
                self.operations[operation_id].status = "failed"
                self.operations[operation_id].error_message = error_msg
                self.operations[operation_id].completed_at = datetime.now(timezone.utc).isoformat()

            return {"success": False, "operation_id": operation_id, "error": error_msg}

    async def get_operations(self) -> Dict[str, Any]:
        """Get all operations and their status"""
        try:
            operations_data = {}
            for op_id, operation in self.operations.items():
                operations_data[op_id] = operation.to_dict()

            return {
                "operations": operations_data,
                "total_operations": len(operations_data),
                "pending": len(
                    [op for op in operations_data.values() if op["status"] == "pending"]
                ),
                "running": len(
                    [op for op in operations_data.values() if op["status"] == "running"]
                ),
                "completed": len(
                    [op for op in operations_data.values() if op["status"] == "completed"]
                ),
                "failed": len([op for op in operations_data.values() if op["status"] == "failed"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            error_msg = f"Error getting operations: {str(e)}"
            return {
                "operations": {},
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def get_node_dependencies(self) -> Dict[str, Any]:
        """Get node dependency information"""
        try:
            dependencies = {}

            # Build dependency graph based on topics and services
            for node_name, node_info in self.nodes.items():
                node_deps = {
                    "subscribes_to": [],
                    "publishes_to": [],
                    "service_clients": [],
                    "service_servers": [],
                    "depends_on_nodes": set(),
                    "depended_on_by": set(),
                }

                # Add topic subscriptions
                for topic in node_info.subscribers:
                    node_deps["subscribes_to"].append(topic)

                    # Find publishers of this topic
                    for other_name, other_info in self.nodes.items():
                        if other_name != node_name and topic in other_info.publishers:
                            node_deps["depends_on_nodes"].add(other_name)

                # Add topic publications
                for topic in node_info.publishers:
                    node_deps["publishes_to"].append(topic)

                    # Find subscribers of this topic
                    for other_name, other_info in self.nodes.items():
                        if other_name != node_name and topic in other_info.subscribers:
                            node_deps["depended_on_by"].add(other_name)

                # Convert sets to lists for JSON serialization
                node_deps["depends_on_nodes"] = list(node_deps["depends_on_nodes"])
                node_deps["depended_on_by"] = list(node_deps["depended_on_by"])

                dependencies[node_name] = node_deps

            return {
                "dependencies": dependencies,
                "nodes_analyzed": len(dependencies),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            error_msg = f"Error analyzing node dependencies: {str(e)}"
            if self.node:
                self.node.get_logger().error(error_msg)

            return {
                "dependencies": {},
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def shutdown(self):
        """Shutdown the service"""
        try:
            self.running = False

            # Stop all managed processes
            for node_name, process in self.node_processes.items():
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

            self.node_processes.clear()

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
            print(f"Error during node lifecycle service shutdown: {e}")


# Global service instance
node_lifecycle_service = NodeLifecycleService()


async def get_node_lifecycle_service() -> NodeLifecycleService:
    """Get the global node lifecycle service instance"""
    if not node_lifecycle_service.node:
        await node_lifecycle_service.initialize()
    return node_lifecycle_service
