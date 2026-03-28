"""Operational API routes — alerts, sessions, graph, search, and visibility."""

from datetime import datetime

from fastapi import APIRouter, Request

import backend.ros2_monitor as _ros2_monitor_mod
from backend.service_registry import (
    ENHANCED_SERVICES_AVAILABLE,
    AlertRule,
    get_alert_engine,
    get_session_stats_service,
    reload_capabilities,
)

router = APIRouter()

# Dependencies injected at startup
_system_state = None
_capabilities_manager = None


def init_operations_deps(system_state, capabilities_manager=None):
    """Inject shared dependencies used by operational endpoint handlers."""
    global _system_state, _capabilities_manager
    _system_state = system_state
    _capabilities_manager = capabilities_manager


# ---------------------------------------------------------------------------
# Alerts API Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/alerts/active")
async def get_active_alerts():
    """Get all active alerts."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"alerts": [], "error": "Enhanced services not available"}
    try:
        alert_engine = get_alert_engine()
        return {
            "alerts": alert_engine.get_active_alerts(),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"alerts": [], "error": str(e)}


@router.get("/api/alerts/history")
async def get_alerts_history(limit: int = 100):
    """Get alert history."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"alerts": [], "error": "Enhanced services not available"}
    try:
        alert_engine = get_alert_engine()
        return {
            "alerts": alert_engine.get_alert_history(limit),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"alerts": [], "error": str(e)}


@router.get("/api/alerts/stats")
async def get_alerts_stats():
    """Get alert statistics."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        alert_engine = get_alert_engine()
        return alert_engine.get_alert_stats()
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {
            "success": False,
            "error": "Enhanced services not available",
        }
    try:
        alert_engine = get_alert_engine()
        alert_engine.acknowledge_alert(alert_id)
        return {
            "success": True,
            "message": f"Alert {alert_id} acknowledged",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/alerts/{alert_id}/clear")
async def clear_alert(alert_id: str):
    """Clear an alert."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {
            "success": False,
            "error": "Enhanced services not available",
        }
    try:
        alert_engine = get_alert_engine()
        alert_engine.clear_alert(alert_id)
        return {
            "success": True,
            "message": f"Alert {alert_id} cleared",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/alerts/rules")
async def add_alert_rules(request: Request):
    """Add or update alert threshold rules from dashboard settings."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {
            "success": False,
            "error": "Enhanced services not available",
        }
    try:
        body = await request.json()
        rules = body.get("rules", [])
        if not rules:
            return {"success": False, "error": "No rules provided"}
        alert_engine = get_alert_engine()
        added = []
        for rule_data in rules:
            name = rule_data.get("name", "")
            metric = rule_data.get("metric", "")
            threshold = rule_data.get("threshold")
            if not name or not metric or threshold is None:
                continue
            rule = AlertRule(
                name=name,
                metric=metric,
                threshold=float(threshold),
                comparison=rule_data.get("comparison", "greater_than"),
                severity=rule_data.get("severity", "warning"),
                message=rule_data.get("message", ""),
            )
            alert_engine.add_rule(rule)
            added.append(name)
        return {
            "success": True,
            "rules_added": len(added),
            "names": added,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Session Statistics API Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/session/current")
async def get_current_session():
    """Get current active session statistics."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"active": False, "error": "Enhanced services not available"}
    try:
        session_service = get_session_stats_service()
        return session_service.get_summary()
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/session/start")
async def start_session():
    """Start a new operation session."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {
            "success": False,
            "error": "Enhanced services not available",
        }
    try:
        session_service = get_session_stats_service()
        session = session_service.start_session()
        return {"success": True, "session_id": session.session_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/session/end")
async def end_session():
    """End current operation session."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {
            "success": False,
            "error": "Enhanced services not available",
        }
    try:
        session_service = get_session_stats_service()
        session = session_service.end_session()
        if session:
            return {"success": True, "stats": session.to_dict()}
        else:
            return {"success": False, "error": "No active session"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/session/history")
async def get_session_history(limit: int = 10):
    """Get recent session history."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"sessions": []}
    try:
        session_service = get_session_stats_service()
        return {"sessions": session_service.get_session_history(limit)}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@router.get("/api/session/totals")
async def get_session_totals():
    """Get lifetime totals across all sessions."""
    if not ENHANCED_SERVICES_AVAILABLE:
        return {"error": "Enhanced services not available"}
    try:
        session_service = get_session_stats_service()
        return session_service.get_totals()
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Graph Introspection API
# ---------------------------------------------------------------------------


@router.get("/api/graph/introspect")
async def get_graph_introspect():
    """Get basic ROS2 graph introspection data."""
    try:
        graph_data = {
            "nodes": {},
            "topics": {},
            "connections": [],
            "summary": {
                "node_count": 0,
                "topic_count": 0,
                "connection_count": 0,
            },
        }
        nodes = _system_state.get("nodes", {})
        for node_name, node_info in nodes.items():
            graph_data["nodes"][node_name] = {
                "name": node_name,
                "status": node_info.get("status", "unknown"),
                "publishers": node_info.get("publishers", []),
                "subscribers": node_info.get("subscribers", []),
            }
        topics = _system_state.get("topics", {})
        for topic_name, topic_info in topics.items():
            graph_data["topics"][topic_name] = {
                "name": topic_name,
                "type": topic_info.get("type", "unknown"),
                "publishers": topic_info.get("publishers", 0),
                "subscribers": topic_info.get("subscribers", 0),
            }
        graph_data["summary"]["node_count"] = len(graph_data["nodes"])
        graph_data["summary"]["topic_count"] = len(graph_data["topics"])
        return {
            "graph": graph_data,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "error": f"Graph introspection error: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/api/graph/nodes")
async def get_graph_nodes():
    """Get ROS2 graph nodes with publishers, subscribers, and services.

    Always reads from the shared system_state dict populated by ros2_monitor.
    Previous implementation optionally spawned heavyweight subprocess calls
    (ros2 node list / ros2 node info) which caused CPU spikes on RPi4.
    """
    nodes_info = {}
    for node_name, node_info in _system_state.get("nodes", {}).items():
        nodes_info[node_name] = {
            "name": node_name,
            "status": node_info.get("status", "unknown"),
            "publishers": node_info.get("publishers", []),
            "subscribers": node_info.get("subscribers", []),
            "services": node_info.get("services", []),
            "clients": node_info.get("clients", []),
        }
    return {
        "nodes": nodes_info,
        "count": len(nodes_info),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/api/graph/topics")
async def get_graph_topics():
    """Get ROS2 graph topics with publishers and subscribers.

    Always reads from the shared system_state dict populated by ros2_monitor.
    Previous implementation optionally spawned heavyweight subprocess calls
    (ros2 topic list -t / ros2 topic info) which caused CPU spikes on RPi4.
    """
    topics_info = {}
    for topic_name, topic_info in _system_state.get("topics", {}).items():
        pubs = topic_info.get("publishers", [])
        subs = topic_info.get("subscribers", [])
        topics_info[topic_name] = {
            "name": topic_name,
            "type": topic_info.get("type", "unknown"),
            "publishers": pubs,
            "subscribers": subs,
            "publisher_count": (len(pubs) if isinstance(pubs, list) else pubs),
            "subscriber_count": (len(subs) if isinstance(subs, list) else subs),
        }
    return {
        "topics": topics_info,
        "count": len(topics_info),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/api/graph/edges")
async def get_graph_edges():
    """Get ROS2 graph edges (publisher-subscriber relationships)."""
    try:
        edges = []
        topics_result = await get_graph_topics()
        if "topics" in topics_result:
            for topic_name, topic_info in topics_result["topics"].items():
                pubs = topic_info.get("publishers", [])
                subs = topic_info.get("subscribers", [])
                # Handle case where publishers/subscribers are counts (int) instead of lists
                if not isinstance(pubs, list):
                    pubs = []
                if not isinstance(subs, list):
                    subs = []
                for publisher in pubs:
                    for subscriber in subs:
                        edges.append(
                            {
                                "from": publisher,
                                "to": subscriber,
                                "topic": topic_name,
                                "message_type": topic_info.get("type", "unknown"),
                            }
                        )
        return {
            "edges": edges,
            "count": len(edges),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"edges": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Unified Search API
# ---------------------------------------------------------------------------


@router.get("/api/search")
async def search_resources(
    q: str = "",
    categories: str = "nodes,topics,services,performance,logs",
    limit: int = 20,
):
    """Unified search across all ROS2 resources."""
    if not _capabilities_manager or not _capabilities_manager.is_enabled("fuzzy_search"):
        return {"results": [], "error": "Fuzzy search not enabled"}

    try:
        if not q or not q.strip():
            return {
                "results": [],
                "query": q,
                "categories": [cat.strip() for cat in categories.split(",")],
                "count": 0,
                "message": "Empty query - provide a search term",
                "timestamp": datetime.now().isoformat(),
            }

        search_categories = [cat.strip() for cat in categories.split(",")]
        results = []
        query_lower = q.lower()

        if "nodes" in search_categories:
            nodes_data = _system_state.get("nodes", {})
            for node_name, node_info in nodes_data.items():
                if query_lower in node_name.lower():
                    results.append(
                        {
                            "type": "node",
                            "name": node_name,
                            "description": f"ROS2 Node: {node_info.get('status', 'unknown')} status",
                            "score": (1.0 if query_lower == node_name.lower() else 0.8),
                            "data": node_info,
                        }
                    )

        if "topics" in search_categories:
            topics_data = _system_state.get("topics", {})
            for topic_name, topic_info in topics_data.items():
                if query_lower in topic_name.lower():
                    results.append(
                        {
                            "type": "topic",
                            "name": topic_name,
                            "description": f"ROS2 Topic: {topic_info.get('msg_type', 'unknown')} messages",
                            "score": (1.0 if query_lower == topic_name.lower() else 0.8),
                            "data": topic_info,
                        }
                    )

        if "services" in search_categories:
            services_data = _system_state.get("services", {})
            for service_name, service_info in services_data.items():
                if query_lower in service_name.lower():
                    results.append(
                        {
                            "type": "service",
                            "name": service_name,
                            "description": f"ROS2 Service: {service_info.get('status', 'unknown')} availability",
                            "score": (1.0 if query_lower == service_name.lower() else 0.8),
                            "data": service_info,
                        }
                    )

        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:limit]

        return {
            "results": results,
            "query": q,
            "categories": search_categories,
            "count": len(results),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"results": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Dashboard Internal Visibility Control
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/internal-visibility")
async def get_internal_visibility():
    """Get current dashboard internal visibility setting."""
    effective = None
    source = "default"
    if _capabilities_manager:
        cfg_hide = _capabilities_manager.get_server_config("hide_dashboard_internals", True)
        effective = cfg_hide
        source = "config"
    if _ros2_monitor_mod.hide_dashboard_internals_override is not None:
        effective = _ros2_monitor_mod.hide_dashboard_internals_override
        source = "runtime_override"
    return {
        "hide_dashboard_internals": bool(effective),
        "source": source,
        "message": "Dashboard internals are " + ("hidden" if effective else "visible"),
    }


@router.post("/api/dashboard/internal-visibility")
async def set_internal_visibility(request: dict):
    """Toggle dashboard internal visibility (runtime override)."""
    try:
        show_internals = request.get("show_internals", False)
        hide_internals = not show_internals
        _ros2_monitor_mod.hide_dashboard_internals_override = hide_internals
        message = f"Dashboard internals now {'hidden' if hide_internals else 'visible'} (runtime)"
        return {
            "success": True,
            "hide_dashboard_internals": hide_internals,
            "show_internals": show_internals,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.post("/api/ignore/reload")
async def reload_ignore_configuration():
    """Reload ignore configuration from config files."""
    try:
        if _capabilities_manager:
            _capabilities_manager.reload_if_changed()
        if reload_capabilities:
            reload_capabilities()
        return {
            "success": True,
            "message": "Ignore configuration reloaded successfully",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
