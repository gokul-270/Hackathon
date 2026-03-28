"""Service Type introspection API (Task 3.1).

Provides an endpoint to query the request/response field structure of a
ROS2 service type without calling the service itself.  Useful for building
dynamic service-call UIs in the dashboard.

The heavy lifting (rosidl type lookup) is isolated in ``introspect_service_type``
so it can be mocked in tests that run without a live ROS2 graph.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

service_type_router = APIRouter()

# ---------------------------------------------------------------------------
# rosidl helpers -- may not be available outside a sourced ROS2 workspace
# ---------------------------------------------------------------------------

try:
    from rosidl_runtime_py.utilities import get_service

    _ROSIDL_AVAILABLE = True
except ImportError:
    _ROSIDL_AVAILABLE = False


def _ros2_field_type_to_str(field_type) -> str:
    """Convert a rosidl field type object to a human-readable string."""
    # rosidl_parser NamespacedType / BasicType / etc.
    if hasattr(field_type, "name"):
        return str(field_type.name)
    return str(field_type)


def _get_field_default(field_type_str: str) -> Any:
    """Return a sensible JSON-safe default for a primitive type string."""
    defaults = {
        "bool": False,
        "boolean": False,
        "int8": 0,
        "uint8": 0,
        "int16": 0,
        "uint16": 0,
        "int32": 0,
        "uint32": 0,
        "int64": 0,
        "uint64": 0,
        "float32": 0.0,
        "float64": 0.0,
        "float": 0.0,
        "double": 0.0,
        "string": "",
    }
    return defaults.get(field_type_str.lower(), None)


def _introspect_message_fields(msg_class) -> List[Dict[str, Any]]:
    """Recursively introspect fields of a ROS2 message class.

    Returns a list of dicts with keys: name, type, default, and optionally
    ``fields`` for nested message types.
    """
    fields: List[Dict[str, Any]] = []

    slot_names = getattr(msg_class, "__slots__", [])
    slot_types = getattr(msg_class, "SLOT_TYPES", [])

    # Clean slot names (strip leading underscore added by rosidl codegen)
    clean_names = [n.lstrip("_") for n in slot_names]

    for name, slot_type in zip(clean_names, slot_types):
        type_str = _ros2_field_type_to_str(slot_type)
        field_info: Dict[str, Any] = {
            "name": name,
            "type": type_str,
            "default": _get_field_default(type_str),
        }

        # Check for nested message type (has its own __slots__)
        if hasattr(slot_type, "value_type"):
            # Array / sequence of messages
            pass
        if hasattr(slot_type, "SLOT_TYPES"):
            sub_fields = _introspect_message_fields(slot_type)
            if sub_fields:
                field_info["fields"] = sub_fields

        fields.append(field_info)

    return fields


def _lookup_service_type(service_name: str) -> Optional[str]:
    """Look up the type string for a service using system_state.

    Previously used ``ros2 service type`` subprocess which was expensive.
    Now reads from the shared system_state populated by ROS2Monitor.
    """
    try:
        from backend.ros2_monitor import system_state

        services = system_state.get("services", {})
        svc_info = services.get(service_name)
        if svc_info and isinstance(svc_info, dict):
            svc_type = svc_info.get("type")
            if svc_type and svc_type != "unknown":
                return svc_type
    except ImportError:
        pass
    return None


def introspect_service_type(
    service_name: str,
) -> Optional[Dict[str, Any]]:
    """Return the full type info dict for *service_name*, or ``None``.

    This is the function mocked in tests.
    """
    if not _ROSIDL_AVAILABLE:
        return None

    type_str = _lookup_service_type(service_name)
    if not type_str:
        return None

    try:
        srv_class = get_service(type_str)
    except Exception:
        return None

    request_cls = srv_class.Request
    response_cls = srv_class.Response

    return {
        "service_name": service_name,
        "service_type": type_str,
        "request": {"fields": _introspect_message_fields(request_cls)},
        "response": {"fields": _introspect_message_fields(response_cls)},
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@service_type_router.get("/api/services/{service_name:path}/type")
async def get_service_type(service_name: str):
    """Return the request/response field structure of a ROS2 service type."""
    # Normalise: ensure leading slash
    if not service_name.startswith("/"):
        service_name = "/" + service_name

    result = introspect_service_type(service_name)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Service not found or type unavailable: {service_name}",
        )
    return result
