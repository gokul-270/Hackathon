"""Parameter aggregation API.

Provides GET /api/parameters/all to fetch parameters from all known
ROS2 nodes and return them as a single aggregated dict.
"""

from typing import Any, Dict, List

from fastapi import APIRouter

parameter_router = APIRouter()


# -----------------------------------------------------------------
# Dependency functions (can be patched in tests)
# -----------------------------------------------------------------


def list_known_nodes() -> List[str]:
    """Return a list of currently known ROS2 node names.

    Reads from the shared system_state populated by ROS2Monitor
    (rclpy graph introspection). No subprocess spawning.
    """
    try:
        from backend.ros2_monitor import system_state

        nodes = system_state.get("nodes", {})
        return list(nodes.keys())
    except ImportError:
        return []


async def get_node_parameters(node_name: str) -> Dict[str, Any]:
    """Fetch parameters for a single node.

    Returns parameters from the shared system_state dict populated by
    ROS2Monitor. Detailed per-parameter values are not available via
    graph introspection (they require service calls), so this returns
    the parameter set known to the monitor.

    Previously this spawned multiple ros2 CLI subprocesses per node
    which was extremely expensive on RPi 4.
    """
    try:
        from backend.ros2_monitor import system_state

        # Check parameters dict first (may have detailed data)
        params_data = system_state.get("parameters", {})
        node_params = params_data.get(node_name, {})

        if node_params:
            parameters = {}
            for p_name, p_info in node_params.items():
                if isinstance(p_info, dict):
                    parameters[p_name] = p_info.get("value", "?")
                else:
                    parameters[p_name] = p_info
            return {
                "node_name": node_name,
                "parameters": parameters,
                "parameter_count": len(parameters),
            }

        # No detailed parameters available — return empty
        # (parameter introspection via rclpy requires service calls
        # to each node which is complex; the dashboard shows basic
        # parameter info from system_state when available)
        return {
            "node_name": node_name,
            "parameters": {},
            "parameter_count": 0,
            "note": "Detailed parameters available on demand",
        }
    except Exception as exc:
        return {
            "node_name": node_name,
            "parameters": {},
            "parameter_count": 0,
            "error": str(exc),
        }


# -----------------------------------------------------------------
# Route
# -----------------------------------------------------------------


@parameter_router.get("/api/parameters/all")
async def get_all_parameters():
    """Aggregate parameters from every known ROS2 node.

    Returns ``{node_name: {parameters, parameter_count, ...}, ...}``.
    Unreachable nodes get an ``error`` field but do not cause a 500.
    """
    nodes = list_known_nodes()
    result: Dict[str, Any] = {}

    for node_name in nodes:
        try:
            node_data = await get_node_parameters(node_name)
            result[node_name] = node_data
        except Exception as exc:
            result[node_name] = {
                "node_name": node_name,
                "parameters": {},
                "parameter_count": 0,
                "error": str(exc),
            }

    return result
