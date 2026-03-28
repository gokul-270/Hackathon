"""Performance, Health, and History API routes."""

import asyncio
from datetime import datetime

import psutil
from fastapi import APIRouter, Response

from backend.ros2_monitor import (
    filter_dashboard_internals,
    get_node_resources,
    get_system_resources,
)
from backend.service_registry import (
    ENHANCED_SERVICES_AVAILABLE,
    get_alert_engine,
    get_health_monitor,
    get_historical_data,
    get_performance_monitor,
    get_performance_service,
)

router = APIRouter()

# Dependencies injected at startup
_system_state = None
_capabilities_manager = None


def init_performance_deps(system_state, capabilities_manager=None):
    """Inject shared dependencies used by performance endpoint handlers."""
    global _system_state, _capabilities_manager
    _system_state = system_state
    _capabilities_manager = capabilities_manager


# Basic Performance Monitoring
@router.get("/api/performance")
async def get_performance_overview():
    """Get performance overview with real system and node metrics."""
    try:
        system_resources = await get_system_resources()
        performance_data = {}
        nodes = filter_dashboard_internals(
            _system_state.get("nodes", {})
        )
        for node_name, node_info in nodes.items():
            node_resources = await asyncio.to_thread(
                get_node_resources, node_name
            )
            performance_data[node_name] = {
                "status": node_info.get("status", "unknown"),
                "cpu_percent": node_resources.get("cpu_percent", 0.0),
                "memory_mb": node_resources.get("memory_mb", 0.0),
                "process_count": node_resources.get("process_count", 0),
                "last_seen": node_info.get("last_seen"),
                "resource_status": node_resources.get("status", "unknown"),
            }
        return {
            "nodes": performance_data,
            "system": system_resources,
            "system_health": _system_state.get("system_health", "unknown"),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "error": f"Performance monitoring error: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


# Phase 3: Performance Monitoring API Endpoints (deprecated)
@router.get("/api/performance/current")
async def get_current_performance(response: Response):
    """Get current performance metrics."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = (
        '</api/performance/summary>; rel="successor-version"'
    )
    if not get_performance_service:
        return {
            "error": "Performance monitoring not available",
            "timestamp": datetime.now().isoformat(),
        }
    try:
        performance_service = await get_performance_service()
        result = await performance_service.get_current_metrics()
        return result
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/api/performance/history")
async def get_performance_history(response: Response, minutes: int = 60):
    """Get historical performance metrics."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = (
        '</api/history/metrics>; rel="successor-version"'
    )
    if not get_performance_service:
        return {
            "error": "Performance monitoring not available",
            "timestamp": datetime.now().isoformat(),
        }
    try:
        performance_service = await get_performance_service()
        result = await performance_service.get_historical_metrics(minutes)
        return result
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/api/performance/legacy_summary")
async def get_performance_summary_legacy(response: Response):
    """Get performance summary from old service (legacy)."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = (
        '</api/performance/summary>; rel="successor-version"'
    )
    if not get_performance_service:
        return {
            "error": "Performance monitoring not available",
            "timestamp": datetime.now().isoformat(),
        }
    try:
        performance_service = await get_performance_service()
        result = await performance_service.get_performance_summary()
        return result
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/api/performance/alerts")
async def get_performance_alerts(minutes: int = 1440):
    """Get performance alerts."""
    if not get_performance_service:
        return {
            "alerts": [],
            "error": "Performance monitoring not available",
        }
    try:
        performance_service = await get_performance_service()
        result = await performance_service.get_performance_alerts(minutes)
        return result
    except Exception as e:
        return {"alerts": [], "error": str(e)}


@router.post("/api/performance/alerts/{alert_id}/acknowledge")
async def acknowledge_performance_alert(alert_id: str):
    """Acknowledge a performance alert."""
    if not get_performance_service:
        return {
            "success": False,
            "error": "Performance monitoring not available",
        }
    try:
        performance_service = await get_performance_service()
        result = await performance_service.acknowledge_alert(alert_id)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/performance/system")
async def get_system_performance(response: Response):
    """Get detailed system performance metrics."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = (
        '</api/performance/summary>; rel="successor-version"'
    )
    if not get_performance_service:
        return {"error": "Performance monitoring not available"}
    try:
        performance_service = await get_performance_service()
        current_metrics = await performance_service.get_current_metrics()
        if "system" in current_metrics:
            return {
                "metrics": current_metrics["system"],
                "timestamp": current_metrics.get("timestamp"),
            }
        else:
            return {"error": "System metrics not available"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/performance/network")
async def get_network_performance(response: Response):
    """Get detailed network performance metrics."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = (
        '</api/performance/summary>; rel="successor-version"'
    )
    if not get_performance_service:
        return {"error": "Performance monitoring not available"}
    try:
        performance_service = await get_performance_service()
        current_metrics = await performance_service.get_current_metrics()
        if "network" in current_metrics:
            return {
                "metrics": current_metrics["network"],
                "timestamp": current_metrics.get("timestamp"),
            }
        else:
            return {"error": "Network metrics not available"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/performance/ros2")
async def get_ros2_performance(response: Response):
    """Get detailed ROS2 performance metrics."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = (
        '</api/performance/summary>; rel="successor-version"'
    )
    if not get_performance_service:
        return {"error": "Performance monitoring not available"}
    try:
        performance_service = await get_performance_service()
        current_metrics = await performance_service.get_current_metrics()
        if "ros2" in current_metrics:
            return {
                "metrics": current_metrics["ros2"],
                "timestamp": current_metrics.get("timestamp"),
            }
        else:
            return {"error": "ROS2 metrics not available"}
    except Exception as e:
        return {"error": str(e)}


def _enhanced_services_available():
    """Check at runtime if enhanced services are available."""
    try:
        monitor = get_performance_monitor
        return monitor is not None and callable(monitor) and monitor() is not None
    except Exception:
        return False


# Enhanced Services API Endpoints
@router.get("/api/performance/summary")
async def get_enhanced_performance_summary():
    """Get enhanced performance monitoring summary.

    Always returns psutil system metrics (HTTP 200). ROS2-specific fields
    are populated when the enhanced performance monitor is running,
    otherwise they are ``null``.
    """
    # Always-available psutil metrics
    try:
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
    except Exception:
        cpu_percent = 0.0
        memory = None
        disk = None

    base_response = {
        "system": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent if memory else 0.0,
            "disk_usage_percent": round(
                (disk.used / disk.total) * 100, 2
            ) if disk else 0.0,
        },
        "ros2": {
            "node_count": None,
            "topic_count": None,
        },
        "timestamp": datetime.now().isoformat(),
    }

    # Try to enrich with enhanced monitor data at runtime
    if _enhanced_services_available():
        try:
            monitor = get_performance_monitor()
            summary = monitor.get_summary()

            # Merge enhanced system metrics into the response
            enhanced_system = summary.get("system", {})
            for key, value in enhanced_system.items():
                base_response["system"].setdefault(key, value)

            # Populate ROS2-specific fields
            ros2_data = summary.get("ros2", {})
            base_response["ros2"]["node_count"] = ros2_data.get(
                "node_count"
            )
            base_response["ros2"]["topic_count"] = ros2_data.get(
                "topic_count"
            )

            # Carry over any extra top-level keys from the monitor
            for key, value in summary.items():
                if key not in ("system", "ros2", "timestamp"):
                    base_response.setdefault(key, value)

            # Feed alert engine
            try:
                alert_engine = get_alert_engine()
                if alert_engine:
                    if "cpu_percent" in enhanced_system:
                        alert_engine.check_metric(
                            "cpu_percent",
                            enhanced_system["cpu_percent"],
                        )
                    if "memory_percent" in enhanced_system:
                        alert_engine.check_metric(
                            "memory_percent",
                            enhanced_system["memory_percent"],
                        )
            except Exception:
                pass
        except Exception:
            pass  # Fall back to base psutil-only response

    return base_response


@router.get("/api/performance/nodes/{node_name}")
async def get_node_performance(node_name: str):
    """Get performance data for a specific node."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        monitor = get_performance_monitor()
        return monitor.get_node_performance(node_name)
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/performance/topics/{topic_name}")
async def get_topic_performance(topic_name: str):
    """Get performance data for a specific topic."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        monitor = get_performance_monitor()
        return monitor.get_topic_performance(topic_name)
    except Exception as e:
        return {"error": str(e)}


# Health Endpoints
@router.get("/api/health/system")
async def get_system_health():
    """Get overall system health summary."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        health = get_health_monitor()
        return health.get_system_health()
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/api/health/motors")
async def get_motors_health():
    """Get motor health status."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        health = get_health_monitor()
        return health.get_motor_health()
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/health/can")
async def get_can_health():
    """Get CAN bus health status."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        health = get_health_monitor()
        return health.get_can_health()
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/health/safety")
async def get_safety_health():
    """Get safety system health."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        health = get_health_monitor()
        return health.get_safety_health()
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/health/detection")
async def get_detection_health():
    """Get cotton detection health."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        health = get_health_monitor()
        return health.get_detection_health()
    except Exception as e:
        return {"error": str(e)}


# History Endpoints
@router.get("/api/history/metrics")
async def get_historical_metrics(
    metric_type: str = None,
    node_name: str = None,
    start_time: float = None,
    end_time: float = None,
    limit: int = 1000,
):
    """Get historical performance metrics."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        hist_data = get_historical_data()
        return {
            "metrics": hist_data.query_metrics(
                metric_type, node_name, start_time, end_time, limit
            ),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/history/errors")
async def get_historical_errors(
    severity: str = None,
    node_name: str = None,
    start_time: float = None,
    end_time: float = None,
    limit: int = 100,
):
    """Get historical error logs."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        hist_data = get_historical_data()
        return {
            "errors": hist_data.query_errors(
                severity, node_name, start_time, end_time, limit
            ),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/history/stats")
async def get_history_stats():
    """Get historical database statistics."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        hist_data = get_historical_data()
        return hist_data.get_database_stats()
    except Exception as e:
        return {"error": str(e)}
