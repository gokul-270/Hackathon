"""
ROS2 Monitor — ROS2 node for monitoring system state via native rclpy APIs.

Extracted from dashboard_server.py as part of the backend restructure.
Uses rclpy graph introspection APIs instead of subprocess calls.

Also contains shared system_state dict and utility functions for system
resource monitoring and dashboard internal filtering.

NOTE (Phase 3, Task 3.3 — entity scoping): This module provides ROS2
introspection for the LOCAL entity only. It does NOT aggregate data from
remote RPi entities. Remote entity ROS2 state is fetched via the
entity_proxy routes which proxy to the lightweight RPi agent (port 8091).
The system_state dict exposed here represents the local machine's ROS2
graph and should not be treated as fleet-wide state.
"""

import asyncio
import threading
from datetime import datetime
from typing import Any, Dict, Optional

import psutil

# ROS2 imports
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import Bool
    from sensor_msgs.msg import JointState

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    Node = object
    print("Warning: ROS2 not available, ROS2Monitor will not function")

# ---------------------------------------------------------------------------
# Shared system state — single source of truth, mutated in-place by
# ROS2Monitor and read by dashboard endpoint handlers.
# ---------------------------------------------------------------------------

system_state: Dict[str, Any] = {
    "ros2_available": False,
    "nodes": {},
    "topics": {},
    "services": {},
    "parameters": {},
    "system_health": "unknown",
    "pragati_status": {
        "arm_position": "unknown",
        "homing_status": "unknown",
        "cotton_detection": "idle",
        "operation_mode": "unknown",
        "initialization_progress": 0,
        "last_cycle_time": None,
        "error_count": 0,
    },
    "logs": [],
    "last_update": None,
}

# Runtime override for dashboard internal visibility (None = use config).
# Mutable module-level variable; dashboard_server.py writes to this via
# ``ros2_monitor.hide_dashboard_internals_override = <value>``.
hide_dashboard_internals_override: Optional[bool] = None


# ---------------------------------------------------------------------------
# Lazy accessor for alert engine (avoids import-time circular deps)
# ---------------------------------------------------------------------------


def _get_alert_engine_lazy():
    """Return the alert engine instance, or None if unavailable."""
    try:
        from backend.service_registry import (
            ENHANCED_SERVICES_AVAILABLE,
            get_alert_engine,
        )

        if ENHANCED_SERVICES_AVAILABLE and get_alert_engine:
            return get_alert_engine()
    except ImportError:
        pass
    return None


# ---------------------------------------------------------------------------
# Utility functions (extracted from dashboard_server.py)
# ---------------------------------------------------------------------------


def _get_capabilities_manager_lazy():
    """Return the capabilities manager instance, or None if unavailable."""
    try:
        from backend.service_registry import get_capabilities_manager

        return get_capabilities_manager()
    except ImportError:
        return None


def should_hide_dashboard_internal(name: str) -> bool:
    """Check if a node/topic/service should be hidden as dashboard internal."""
    caps = _get_capabilities_manager_lazy()
    if not caps:
        return False

    global hide_dashboard_internals_override
    if hide_dashboard_internals_override is not None:
        hide_internals = hide_dashboard_internals_override
    else:
        hide_internals = caps.get_server_config("hide_dashboard_internals", True)
    if not hide_internals:
        return False

    dashboard_patterns = ["web_dashboard_", "/web_dashboard"]
    for pattern in dashboard_patterns:
        if pattern in name:
            return True
    return False


def filter_dashboard_internals(data_dict: dict) -> dict:
    """Filter out dashboard internal nodes/topics/services."""
    return {k: v for k, v in data_dict.items() if not should_hide_dashboard_internal(k)}


async def get_system_resources() -> dict:
    """Get real system CPU, memory, and disk usage."""
    try:
        cpu_percent = await asyncio.to_thread(psutil.cpu_percent, interval=1)
        cpu_count = await asyncio.to_thread(psutil.cpu_count)
        cpu_freq = await asyncio.to_thread(psutil.cpu_freq)
        memory = await asyncio.to_thread(psutil.virtual_memory)
        swap = await asyncio.to_thread(psutil.swap_memory)
        disk = await asyncio.to_thread(psutil.disk_usage, "/")
        network = await asyncio.to_thread(psutil.net_io_counters)

        alert_engine = _get_alert_engine_lazy()
        if alert_engine:
            try:
                alert_engine.check_metric("cpu_percent", cpu_percent)
                alert_engine.check_metric("memory_percent", memory.percent)
            except Exception:
                pass

        return {
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
                "frequency_mhz": cpu_freq.current if cpu_freq else 0,
            },
            "memory": {
                "total_mb": round(memory.total / (1024 * 1024), 2),
                "available_mb": round(memory.available / (1024 * 1024), 2),
                "used_mb": round(memory.used / (1024 * 1024), 2),
                "percent": memory.percent,
            },
            "swap": {
                "total_mb": round(swap.total / (1024 * 1024), 2),
                "used_mb": round(swap.used / (1024 * 1024), 2),
                "percent": swap.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024 * 1024 * 1024), 2),
                "used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
                "free_gb": round(disk.free / (1024 * 1024 * 1024), 2),
                "percent": round((disk.used / disk.total) * 100, 2),
            },
            "network": {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv,
            },
        }
    except Exception as e:
        return {"error": f"Failed to get system resources: {e}"}


def get_node_resources(node_name: str) -> dict:
    """Get CPU and memory usage for a specific ROS2 node process."""
    try:
        matching_processes = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["cmdline"] and any(node_name in arg for arg in proc.info["cmdline"]):
                    matching_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not matching_processes:
            return {
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "status": "not_found",
            }

        total_cpu = 0.0
        total_memory = 0.0
        for proc in matching_processes:
            try:
                cpu_percent = proc.cpu_percent()
                memory_mb = proc.memory_info().rss / (1024 * 1024)
                total_cpu += cpu_percent
                total_memory += memory_mb
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return {
            "cpu_percent": round(total_cpu, 2),
            "memory_mb": round(total_memory, 2),
            "process_count": len(matching_processes),
            "status": "active",
        }
    except Exception as e:
        return {
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "error": str(e),
            "status": "error",
        }


# ---------------------------------------------------------------------------
# ROS2 Monitor Node
# ---------------------------------------------------------------------------


class ROS2Monitor(Node):
    """ROS2 node for monitoring system state using native graph APIs."""

    def __init__(self, system_state: dict):
        super().__init__("web_dashboard_monitor")
        self._system_state = system_state

        # Subscribers for Pragati-specific monitoring
        self.arm_status_sub = None
        self.joint_state_sub = None
        self.start_switch_sub = None

        # Setup subscribers if topics exist
        self.setup_subscribers()

        # Timer for periodic updates (10s to reduce CPU on RPi 4)
        self.timer = self.create_timer(10.0, self.update_system_state)

        self.get_logger().info("Dashboard monitor node initialized")

    def setup_subscribers(self):
        """Setup subscribers for available topics."""
        try:
            self.joint_state_sub = self.create_subscription(
                JointState, "/joint_states", self.joint_state_callback, 10
            )
            self.start_switch_sub = self.create_subscription(
                Bool, "/start_switch/state", self.start_switch_callback, 10
            )
        except Exception as e:
            self.get_logger().warn(f"Could not setup all subscribers: {e}")

    def joint_state_callback(self, msg):
        """Handle joint state updates."""
        try:
            positions = dict(zip(msg.name, msg.position))
            self._system_state["pragati_status"]["arm_position"] = positions
            self._system_state["pragati_status"]["last_update"] = datetime.now().isoformat()
        except Exception as e:
            self.get_logger().error(f"Error processing joint state: {e}")

    def start_switch_callback(self, msg):
        """Handle start switch updates."""
        try:
            self._system_state["pragati_status"]["start_switch"] = msg.data
            if msg.data:
                self._system_state["pragati_status"]["operation_mode"] = "active"
            else:
                self._system_state["pragati_status"]["operation_mode"] = "waiting"
        except Exception as e:
            self.get_logger().error(f"Error processing start switch: {e}")

    def update_system_state(self):
        """Periodic update of system state using native rclpy APIs."""
        try:
            self.update_nodes()
            self.update_topics()
            self.update_services()
            self.update_parameters()
            self.assess_system_health()
            self._system_state["ros2_available"] = True
            self._system_state["last_update"] = datetime.now().isoformat()

            # Update enhanced performance monitor if available
            try:
                from backend.performance_service import (
                    get_performance_monitor,
                )

                perf_monitor = get_performance_monitor()
                if perf_monitor and perf_monitor.running:
                    perf_monitor.update_from_system_state(self._system_state["nodes"])
            except Exception:
                pass  # Don't fail main update if enhanced monitoring fails
        except Exception as e:
            self.get_logger().error(f"Error updating system state: {e}")

    def update_nodes(self):
        """Update node status using rclpy graph introspection."""
        try:
            node_names_and_ns = self.get_node_names_and_namespaces()
            current_nodes: Dict[str, Any] = {}

            for name, namespace in node_names_and_ns:
                full_name = f"{namespace}/{name}" if namespace != "/" else f"/{name}"
                current_nodes[full_name] = {
                    "status": "active",
                    "last_seen": datetime.now().isoformat(),
                    "info_available": True,
                    "subscribers": [],
                    "publishers": [],
                    "services": [],
                }

            self._system_state["nodes"] = current_nodes
            self.get_logger().debug(f"Updated {len(current_nodes)} nodes")
        except Exception as e:
            self.get_logger().error(f"Error updating nodes: {e}")

    def update_topics(self):
        """Update topic status using rclpy graph introspection.

        NOTE: Per-topic get_publishers_info_by_topic / get_subscriptions_info_by_topic
        calls are extremely expensive (~2 DDS graph queries per topic).  With 42 topics
        that's 84 calls per cycle — enough to pin a RPi 4 core.  We skip them in the
        periodic update and set counts to 0; the frontend can fetch detailed info
        on-demand via the topic detail API.
        """
        try:
            topic_names_and_types = self.get_topic_names_and_types()
            current_topics: Dict[str, Any] = {}

            for topic_name, topic_types in topic_names_and_types:
                topic_type = topic_types[0] if topic_types else "unknown"

                current_topics[topic_name] = {
                    "type": topic_type,
                    "publishers": 0,
                    "subscribers": 0,
                    "last_message": None,
                    "rate": 0.0,
                }

            self._system_state["topics"] = current_topics
            self.get_logger().debug(f"Updated {len(current_topics)} topics")
        except Exception as e:
            self.get_logger().error(f"Error updating topics: {e}")

    def update_services(self):
        """Update service status using rclpy graph introspection."""
        try:
            service_names_and_types = self.get_service_names_and_types()
            current_services: Dict[str, Any] = {}

            for service_name, service_types in service_names_and_types:
                service_type = service_types[0] if service_types else "unknown"
                current_services[service_name] = {
                    "type": service_type,
                    "available": True,
                    "last_called": None,
                }

            self._system_state["services"] = current_services
            self.get_logger().debug(f"Updated {len(current_services)} services")
        except Exception as e:
            self.get_logger().error(f"Error updating services: {e}")

    def update_parameters(self):
        """Update parameter information.

        Note: Parameter listing still requires per-node queries. We use
        rclpy service calls internally when available, but this is
        inherently slower than graph introspection. Keep it lightweight.
        """
        try:
            current_parameters: Dict[str, Any] = {}
            # Parameter introspection via rclpy is complex (requires service
            # calls to each node). For now, keep the parameter dict populated
            # from node names only — detailed param values are fetched on
            # demand via the parameter_api.py router.
            self._system_state["parameters"] = current_parameters
        except Exception as e:
            self.get_logger().error(f"Error updating parameters: {e}")

    def assess_system_health(self):
        """Assess overall system health."""
        try:
            health_score = 0
            max_score = 0

            critical_nodes = [
                "yanthra_move",
                "robot_state_publisher",
                "odrive_service_node",
            ]
            for node in critical_nodes:
                max_score += 1
                if any(node in n for n in self._system_state["nodes"].keys()):
                    health_score += 1

            critical_topics = [
                "/joint_states",
                "/joint2_position_controller/command",
            ]
            for topic in critical_topics:
                max_score += 1
                if topic in self._system_state["topics"]:
                    health_score += 1

            critical_services = ["/joint_homing", "/joint_status"]
            for service in critical_services:
                max_score += 1
                if service in self._system_state["services"]:
                    health_score += 1

            if max_score > 0:
                health_percentage = (health_score / max_score) * 100
                if health_percentage >= 90:
                    self._system_state["system_health"] = "excellent"
                elif health_percentage >= 75:
                    self._system_state["system_health"] = "good"
                elif health_percentage >= 50:
                    self._system_state["system_health"] = "fair"
                else:
                    self._system_state["system_health"] = "poor"
            else:
                self._system_state["system_health"] = "unknown"
        except Exception as e:
            self.get_logger().error(f"Error assessing system health: {e}")
            self._system_state["system_health"] = "error"


# Module-level state for the monitor
_ros2_monitor = None
_ros2_executor = None
_ros2_thread = None


def setup_ros2_monitoring(system_state: dict):
    """Setup ROS2 monitoring in a separate thread.

    Args:
        system_state: Shared dict that the monitor updates in-place.
    """
    global _ros2_monitor, _ros2_executor, _ros2_thread

    if not ROS2_AVAILABLE:
        system_state["ros2_available"] = False
        print("ROS2 not available, monitoring disabled")
        return

    def ros2_monitor_thread():
        global _ros2_monitor, _ros2_executor
        try:
            try:
                rclpy.init()
            except RuntimeError:
                pass  # Already initialized
            _ros2_monitor = ROS2Monitor(system_state)
            _ros2_executor = SingleThreadedExecutor()
            _ros2_executor.add_node(_ros2_monitor)
            _ros2_executor.spin()
        except Exception as e:
            print(f"Error in ROS2 monitor thread: {e}")
        finally:
            if _ros2_monitor:
                _ros2_monitor.destroy_node()
            rclpy.shutdown()

    _ros2_thread = threading.Thread(target=ros2_monitor_thread, daemon=True)
    _ros2_thread.start()


def get_ros2_monitor():
    """Return the ROS2Monitor instance (may be None if not started)."""
    return _ros2_monitor


def get_ros2_executor():
    """Return the SingleThreadedExecutor (may be None if not started)."""
    return _ros2_executor


# ---------------------------------------------------------------------------
# Callable functions for entity_ros2_router (Task 2.9)
#
# These functions provide direct access to local ROS2 data without going
# through HTTP.  They read from the shared ``system_state`` dict (populated
# by ROS2Monitor) or use the rclpy node for graph introspection.
# ---------------------------------------------------------------------------

# Valid lifecycle transitions (lifecycle_msgs/msg/Transition constants)
_VALID_LIFECYCLE_TRANSITIONS = {
    "configure",
    "cleanup",
    "activate",
    "deactivate",
    "shutdown",
}


def _require_monitor() -> Any:
    """Return the ROS2Monitor node, raising if unavailable.

    Raises:
        RuntimeError: If ROS2 is not installed or monitor is not running.
    """
    if not ROS2_AVAILABLE:
        raise RuntimeError("ROS2 is not available")
    monitor = get_ros2_monitor()
    if monitor is None:
        raise RuntimeError("ROS2 monitor is not running")
    return monitor


def _parse_node_full_name(full_name: str) -> tuple:
    """Parse '/ns/node_name' into (namespace, short_name).

    Examples:
        '/yanthra_move'       -> ('/', 'yanthra_move')
        '/ns1/ns2/deep_node'  -> ('/ns1/ns2', 'deep_node')
    """
    parts = full_name.rsplit("/", 1)
    if len(parts) == 2:
        namespace = parts[0] if parts[0] else "/"
        name = parts[1]
    else:
        namespace = "/"
        name = full_name.lstrip("/")
    return namespace, name


def get_topics() -> list:
    """Return topics from system_state as a list of dicts.

    Format: [{"name": "/topic", "type": "msg/Type",
              "publisher_count": N, "subscriber_count": N}]
    """
    filtered = filter_dashboard_internals(system_state.get("topics", {}))
    result = []
    for topic_name, info in filtered.items():
        result.append(
            {
                "name": topic_name,
                "type": info.get("type", "unknown"),
                "publisher_count": info.get("publishers", 0),
                "subscriber_count": info.get("subscribers", 0),
            }
        )
    return result


def get_services() -> list:
    """Return services from system_state as a list of dicts.

    Format: [{"name": "/service", "type": "srv/Type"}]
    """
    filtered = filter_dashboard_internals(system_state.get("services", {}))
    result = []
    for service_name, info in filtered.items():
        result.append(
            {
                "name": service_name,
                "type": info.get("type", "unknown"),
            }
        )
    return result


def get_nodes() -> list:
    """Return nodes from system_state as a list of dicts.

    Format: [{"name": "node_name", "namespace": "/ns",
              "lifecycle_state": null}]
    """
    filtered = filter_dashboard_internals(system_state.get("nodes", {}))
    result = []
    for full_name in filtered:
        namespace, short_name = _parse_node_full_name(full_name)
        result.append(
            {
                "name": short_name,
                "namespace": namespace,
                "lifecycle_state": None,
            }
        )
    return result


def get_node_detail(node_name: str) -> Optional[dict]:
    """Return detailed info for a single node.

    Searches system_state for a node matching *node_name* (short name).
    If the ROS2 monitor is running, uses rclpy graph introspection for
    publishers, subscribers, services, and parameters.

    Returns None if the node is not found.
    """
    # Find the matching full-name in system_state
    nodes = system_state.get("nodes", {})
    matched_full_name = None
    for full_name in nodes:
        ns, short = _parse_node_full_name(full_name)
        if short == node_name:
            matched_full_name = full_name
            break

    if matched_full_name is None:
        return None

    namespace, short_name = _parse_node_full_name(matched_full_name)

    # Try rclpy introspection if monitor is available
    monitor = get_ros2_monitor()
    if monitor is not None:
        try:
            pubs_raw = monitor.get_publisher_names_and_types_by_node(short_name, namespace)
            subs_raw = monitor.get_subscriber_names_and_types_by_node(short_name, namespace)
            srvs_raw = monitor.get_service_names_and_types_by_node(short_name, namespace)
            publishers = [{"name": n, "type": t[0] if t else "unknown"} for n, t in pubs_raw]
            subscribers = [{"name": n, "type": t[0] if t else "unknown"} for n, t in subs_raw]
            services = [{"name": n, "type": t[0] if t else "unknown"} for n, t in srvs_raw]
        except Exception:
            # Fallback to system_state data
            node_info = nodes.get(matched_full_name, {})
            publishers = node_info.get("publishers", [])
            subscribers = node_info.get("subscribers", [])
            services = node_info.get("services", [])
    else:
        node_info = nodes.get(matched_full_name, {})
        publishers = node_info.get("publishers", [])
        subscribers = node_info.get("subscribers", [])
        services = node_info.get("services", [])

    return {
        "name": short_name,
        "namespace": namespace,
        "publishers": publishers,
        "subscribers": subscribers,
        "services": services,
        "parameters": [],
    }


def get_parameters() -> dict:
    """Return parameters grouped by node.

    Format: {"nodes": [{"name": "/node",
              "parameters": [{"name": "p", "type": "double", "value": 1.0}]}]}
    """
    params_data = system_state.get("parameters", {})
    nodes_data = system_state.get("nodes", {})

    # Merge: use all nodes, attach parameters where available
    all_node_names = set(nodes_data.keys()) | set(params_data.keys())
    filtered_names = {n for n in all_node_names if not should_hide_dashboard_internal(n)}

    result_nodes = []
    for full_name in sorted(filtered_names):
        node_params = params_data.get(full_name, {})
        param_list = []
        for p_name, p_info in node_params.items():
            if isinstance(p_info, dict):
                param_list.append(
                    {
                        "name": p_name,
                        "type": p_info.get("type", "unknown"),
                        "value": p_info.get("value"),
                    }
                )
        result_nodes.append(
            {
                "name": full_name,
                "parameters": param_list,
            }
        )

    return {"nodes": result_nodes}


def set_parameter(node_name: str, param_name: str, value: Any) -> dict:
    """Set a parameter on a ROS2 node via the parameter set service.

    Args:
        node_name: Full node name (e.g. '/yanthra_move').
        param_name: Parameter name.
        value: New value to set.

    Returns:
        {"success": True, "name": param_name, "value": value}

    Raises:
        RuntimeError: If ROS2 is not available or monitor not running.
    """
    monitor = _require_monitor()

    try:
        from rcl_interfaces.srv import SetParameters
        from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
    except ImportError:
        # In test environments these may not exist; handled by mocks
        pass

    service_name = f"{node_name}/set_parameters"
    client = monitor.create_client(SetParameters, service_name)

    try:
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"Service {service_name} not available within timeout")

        # Build the parameter value
        param_value = ParameterValue()
        if isinstance(value, bool):
            param_value.type = ParameterType.PARAMETER_BOOL
            param_value.bool_value = value
        elif isinstance(value, int):
            param_value.type = ParameterType.PARAMETER_INTEGER
            param_value.integer_value = value
        elif isinstance(value, float):
            param_value.type = ParameterType.PARAMETER_DOUBLE
            param_value.double_value = value
        elif isinstance(value, str):
            param_value.type = ParameterType.PARAMETER_STRING
            param_value.string_value = value
        else:
            param_value.type = ParameterType.PARAMETER_STRING
            param_value.string_value = str(value)

        param = Parameter()
        param.name = param_name
        param.value = param_value

        request = SetParameters.Request()
        request.parameters = [param]

        future = client.call_async(request)
        rclpy.spin_until_future_complete(monitor, future, timeout_sec=5.0)

        result = future.result()
        if result is None:
            raise RuntimeError("Service call timed out")

        if result.results and result.results[0].successful:
            return {"success": True, "name": param_name, "value": value}
        else:
            reason = result.results[0].reason if result.results else "unknown error"
            return {"success": False, "name": param_name, "error": reason}
    finally:
        monitor.destroy_client(client)


def _import_service_type(service_type_str: str):
    """Import a ROS2 service type from its string representation.

    E.g. 'std_srvs/srv/Trigger' -> std_srvs.srv.Trigger class

    Args:
        service_type_str: Service type string like 'pkg/srv/Type'.

    Returns:
        The service class.
    """
    import importlib

    parts = service_type_str.split("/")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid service type format: {service_type_str!r}, "
            f"expected 'package/srv/TypeName'"
        )
    package, _, type_name = parts
    module = importlib.import_module(f"{package}.srv")
    return getattr(module, type_name)


def call_service(service_name: str, service_type: str, request: dict) -> dict:
    """Call a ROS2 service and return the response.

    Args:
        service_name: Full service name (e.g. '/joint_homing').
        service_type: Service type string (e.g. 'std_srvs/srv/Trigger').
        request: Dict of request fields.

    Returns:
        {"response": {...}, "duration_ms": N}

    Raises:
        RuntimeError: If ROS2 is not available or monitor not running.
    """
    import time

    monitor = _require_monitor()
    srv_class = _import_service_type(service_type)

    client = monitor.create_client(srv_class, service_name)
    try:
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"Service {service_name} not available within timeout")

        req = srv_class.Request()
        for key, val in request.items():
            if hasattr(req, key):
                setattr(req, key, val)

        start = time.monotonic()
        future = client.call_async(req)
        rclpy.spin_until_future_complete(monitor, future, timeout_sec=5.0)
        elapsed_ms = (time.monotonic() - start) * 1000

        result = future.result()
        if result is None:
            raise RuntimeError("Service call timed out")

        # Serialize response to dict
        response_dict = {}
        try:
            fields = result.get_fields_and_field_types()
            for field_name in fields:
                response_dict[field_name] = getattr(result, field_name, None)
        except Exception:
            response_dict = {"raw": str(result)}

        return {
            "response": response_dict,
            "duration_ms": round(elapsed_ms, 2),
        }
    finally:
        monitor.destroy_client(client)


def lifecycle_transition(node_name: str, transition: str) -> dict:
    """Send a lifecycle state transition to a managed node.

    Args:
        node_name: Full node name (e.g. '/my_node').
        transition: One of 'configure', 'cleanup', 'activate',
                    'deactivate', 'shutdown'.

    Returns:
        {"success": True, "node": node_name, "transition": transition}

    Raises:
        RuntimeError: If ROS2 not available or monitor not running.
        ValueError: If transition name is invalid.
    """
    if transition not in _VALID_LIFECYCLE_TRANSITIONS:
        raise ValueError(
            f"Invalid lifecycle transition: {transition!r}. "
            f"Valid: {sorted(_VALID_LIFECYCLE_TRANSITIONS)}"
        )

    monitor = _require_monitor()

    try:
        from lifecycle_msgs.srv import ChangeState
        from lifecycle_msgs.msg import Transition
    except ImportError:
        pass

    transition_map = {
        "configure": Transition.TRANSITION_CONFIGURE,
        "cleanup": Transition.TRANSITION_CLEANUP,
        "activate": Transition.TRANSITION_ACTIVATE,
        "deactivate": Transition.TRANSITION_DEACTIVATE,
        "shutdown": Transition.TRANSITION_ACTIVE_SHUTDOWN,
    }

    service_name = f"{node_name}/change_state"
    client = monitor.create_client(ChangeState, service_name)

    try:
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"Service {service_name} not available within timeout")

        request = ChangeState.Request()
        request.transition = Transition()
        request.transition.id = transition_map[transition]

        future = client.call_async(request)
        rclpy.spin_until_future_complete(monitor, future, timeout_sec=5.0)

        result = future.result()
        if result is None:
            raise RuntimeError("Lifecycle transition timed out")

        return {
            "success": result.success,
            "node": node_name,
            "transition": transition,
        }
    finally:
        monitor.destroy_client(client)
