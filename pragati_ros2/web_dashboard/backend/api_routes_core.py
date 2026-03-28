"""
API Routes — Core ROS2 data-plane endpoints.

Logging, basic ROS2 state queries (nodes/topics/services/parameters),
service invocation, and node lifecycle management.

Split from api_routes.py to reduce module size.
"""

import asyncio
import re
import subprocess
from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.ros2_monitor import ROS2_AVAILABLE, filter_dashboard_internals
from backend.service_registry import (
    get_log_aggregation_service,
    get_node_lifecycle_service,
)

router = APIRouter()

# Dependencies injected at startup
_system_state = None
_capabilities_manager = None
_message_envelope = None


def init_core_deps(system_state, capabilities_manager, message_envelope):
    """Inject shared dependencies used by core endpoint handlers."""
    global _system_state, _capabilities_manager, _message_envelope
    _system_state = system_state
    _capabilities_manager = capabilities_manager
    _message_envelope = message_envelope


# Advanced Logging API Endpoints
@router.get("/api/logs")
async def get_logs(
    limit: int = 100,
    offset: int = 0,
    levels: str = None,
    nodes: str = None,
    message_pattern: str = None,
):
    """Get filtered logs with pagination."""
    if not get_log_aggregation_service:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["ros2", "topic", "echo", "/rosout", "--once"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            logs = []
            if result.returncode == 0:
                logs.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "level": "info",
                        "message": "ROS2 system active",
                        "node_name": "dashboard",
                    }
                )
            return {
                "logs": logs[-limit:],
                "total": len(logs),
                "enhanced": False,
            }
        except Exception as e:
            return {
                "logs": [
                    {
                        "timestamp": datetime.now().isoformat(),
                        "level": "error",
                        "message": f"Error getting logs: {e}",
                        "node_name": "dashboard",
                    }
                ],
                "total": 1,
                "enhanced": False,
            }

    try:
        log_service = await get_log_aggregation_service()
        filters = {}
        if levels:
            filters["levels"] = [
                level.strip().upper() for level in levels.split(",")
            ]
        if nodes:
            filters["nodes"] = [n.strip() for n in nodes.split(",")]
        if message_pattern:
            filters["message_pattern"] = message_pattern
        result = await log_service.get_logs(filters, limit, offset)
        result["enhanced"] = True
        return result
    except Exception as e:
        return {
            "logs": [],
            "total": 0,
            "error": str(e),
            "enhanced": False,
        }


@router.get("/api/logs/statistics")
async def get_log_statistics():
    """Get log aggregation statistics."""
    if not get_log_aggregation_service:
        return {"error": "Advanced logging not available"}
    try:
        log_service = await get_log_aggregation_service()
        return await log_service.get_statistics()
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/logs/metadata")
async def get_log_metadata():
    """Get available log levels and nodes."""
    if not get_log_aggregation_service:
        return {
            "levels": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
            "nodes": [],
            "export_formats": [],
        }
    try:
        log_service = await get_log_aggregation_service()
        return await log_service.get_metadata()
    except Exception as e:
        return {"levels": [], "nodes": [], "error": str(e)}


@router.post("/api/logs/export")
async def export_logs(request: dict):
    """Export logs in specified format."""
    if not get_log_aggregation_service:
        raise HTTPException(
            status_code=503, detail="Advanced logging not available"
        )
    try:
        log_service = await get_log_aggregation_service()
        format = request.get("format", "json")
        filters = request.get("filters", {})
        result = await log_service.export_logs(format, filters)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Export failed: {str(e)}"
        )


@router.post("/api/logs/clear")
async def clear_logs(request: dict = None):
    """Clear logs with optional filters."""
    if not get_log_aggregation_service:
        raise HTTPException(
            status_code=503, detail="Advanced logging not available"
        )
    try:
        log_service = await get_log_aggregation_service()
        filters = request.get("filters") if request else None
        result = await log_service.clear_logs(filters)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Clear failed: {str(e)}"
        )


@router.get("/api/nodes")
async def get_nodes():
    """Get node information."""
    nodes = _system_state["nodes"]
    return filter_dashboard_internals(nodes)


@router.get("/api/topics")
async def get_topics():
    """Get topic information."""
    topics = _system_state["topics"]
    return filter_dashboard_internals(topics)


@router.get("/api/services")
async def get_services():
    """Get service information."""
    services = _system_state["services"]
    return filter_dashboard_internals(services)


@router.get("/api/parameters")
async def get_parameters():
    """Get parameter information."""
    return _system_state["parameters"]


@router.get("/api/pragati")
async def get_pragati_status():
    """Get Pragati-specific status."""
    return _system_state["pragati_status"]


@router.post("/api/service/{service_name}/call")
async def call_service(service_name: str, data: dict = None):
    """Call a ROS2 service."""
    if not re.match(r"^[a-zA-Z0-9_/]+$", service_name):
        raise HTTPException(status_code=400, detail="Invalid service name")
    try:
        if not ROS2_AVAILABLE:
            raise HTTPException(
                status_code=503, detail="ROS2 not available"
            )
        cmd = [
            "ros2",
            "service",
            "call",
            service_name,
            "std_srvs/srv/Trigger",
        ]
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=10
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Node Lifecycle Management API Endpoints
@router.get("/api/nodes/lifecycle")
async def get_nodes_lifecycle():
    """Get enhanced node information with lifecycle data."""
    if not get_node_lifecycle_service:
        return _system_state["nodes"]
    try:
        lifecycle_service = await get_node_lifecycle_service()
        result = await lifecycle_service.get_nodes()
        return result
    except Exception as e:
        return {"nodes": {}, "error": str(e)}


@router.post("/api/nodes/{node_name}/start")
async def start_node(node_name: str, request: dict = None):
    """Start a specific node."""
    if not get_node_lifecycle_service:
        raise HTTPException(
            status_code=503,
            detail="Node lifecycle management not available",
        )
    try:
        lifecycle_service = await get_node_lifecycle_service()
        launch_command = request.get("launch_command") if request else None
        working_dir = request.get("working_dir") if request else None
        result = await lifecycle_service.start_node(
            node_name, launch_command, working_dir
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error starting node: {str(e)}",
        )


@router.post("/api/nodes/{node_name}/stop")
async def stop_node(node_name: str, request: dict = None):
    """Stop a specific node."""
    if not get_node_lifecycle_service:
        raise HTTPException(
            status_code=503,
            detail="Node lifecycle management not available",
        )
    try:
        lifecycle_service = await get_node_lifecycle_service()
        force = request.get("force", False) if request else False
        result = await lifecycle_service.stop_node(node_name, force)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error stopping node: {str(e)}",
        )


@router.post("/api/nodes/{node_name}/restart")
async def restart_node(node_name: str, request: dict = None):
    """Restart a specific node."""
    if not get_node_lifecycle_service:
        raise HTTPException(
            status_code=503,
            detail="Node lifecycle management not available",
        )
    try:
        lifecycle_service = await get_node_lifecycle_service()
        launch_command = request.get("launch_command") if request else None
        working_dir = request.get("working_dir") if request else None
        result = await lifecycle_service.restart_node(
            node_name, launch_command, working_dir
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error restarting node: {str(e)}",
        )


@router.get("/api/nodes/{node_name}/parameters")
async def get_node_parameters(node_name: str):
    """Get parameters for a specific node."""
    if not get_node_lifecycle_service:
        raise HTTPException(
            status_code=503,
            detail="Node lifecycle management not available",
        )
    try:
        lifecycle_service = await get_node_lifecycle_service()
        result = await lifecycle_service.get_node_parameters(node_name)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting node parameters: {str(e)}",
        )


@router.post("/api/nodes/{node_name}/parameters/{param_name}")
async def set_node_parameter(
    node_name: str, param_name: str, request: dict
):
    """Set a parameter for a specific node."""
    if not get_node_lifecycle_service:
        raise HTTPException(
            status_code=503,
            detail="Node lifecycle management not available",
        )
    try:
        lifecycle_service = await get_node_lifecycle_service()
        param_value = request.get("value")
        if param_value is None:
            raise HTTPException(
                status_code=400, detail="Parameter value required"
            )
        result = await lifecycle_service.set_node_parameter(
            node_name, param_name, param_value
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error setting node parameter: {str(e)}",
        )


@router.get("/api/nodes/operations")
async def get_node_operations():
    """Get all node lifecycle operations and their status."""
    if not get_node_lifecycle_service:
        return {
            "operations": {},
            "error": "Node lifecycle management not available",
        }
    try:
        lifecycle_service = await get_node_lifecycle_service()
        result = await lifecycle_service.get_operations()
        return result
    except Exception as e:
        return {"operations": {}, "error": str(e)}


@router.get("/api/nodes/dependencies")
async def get_node_dependencies():
    """Get node dependency information."""
    if not get_node_lifecycle_service:
        return {
            "dependencies": {},
            "error": "Node lifecycle management not available",
        }
    try:
        lifecycle_service = await get_node_lifecycle_service()
        result = await lifecycle_service.get_node_dependencies()
        return result
    except Exception as e:
        return {"dependencies": {}, "error": str(e)}


@router.get("/api/nodes/{node_name}/health")
async def get_node_health(node_name: str):
    """Get health information for a specific node."""
    if not get_node_lifecycle_service:
        raise HTTPException(
            status_code=503,
            detail="Node lifecycle management not available",
        )
    try:
        lifecycle_service = await get_node_lifecycle_service()
        nodes_result = await lifecycle_service.get_nodes()
        if "error" in nodes_result:
            raise HTTPException(
                status_code=500, detail=nodes_result["error"]
            )
        nodes_data = nodes_result.get("nodes", {})
        if node_name not in nodes_data:
            raise HTTPException(
                status_code=404, detail=f"Node {node_name} not found"
            )
        node_data = nodes_data[node_name]
        health_data = node_data.get("health", {"status": "unknown"})
        return {
            "node_name": node_name,
            "health": health_data,
            "status": node_data.get("status", "unknown"),
            "cpu_percent": node_data.get("cpu_percent", 0.0),
            "memory_mb": node_data.get("memory_mb", 0.0),
            "uptime_seconds": node_data.get("uptime_seconds", 0.0),
            "restart_count": node_data.get("restart_count", 0),
            "last_seen": node_data.get("last_seen"),
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting node health: {str(e)}",
        )
