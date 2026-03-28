"""
WebSocket Handlers — WebSocket connection management, message dispatch, broadcast.

Extracted from dashboard_server.py as part of the backend restructure.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


# WebSocket connections with client tracking
websocket_connections: Dict[str, WebSocket] = {}  # client_id -> websocket

# Arms-status WebSocket connections (for MQTT bridge broadcast)
_arms_ws_connections: Dict[str, WebSocket] = {}


async def broadcast(message_type: str, data: dict):
    """Broadcast a typed message to all connected WebSocket clients.

    Wraps *data* in a ``{"type": ..., "data": ...}`` envelope before
    sending to every connected client.
    """
    envelope = {"type": message_type, "data": data}
    for client_id, ws in list(websocket_connections.items()):
        try:
            await ws.send_json(envelope)
        except Exception:
            # Client disconnected — will be cleaned up on next iteration
            pass


async def broadcast_to_arms_ws(event: dict):
    """Broadcast an event to all /ws/arms/status WebSocket clients."""
    for client_id, ws in list(_arms_ws_connections.items()):
        try:
            await ws.send_json(event)
        except Exception:
            pass


async def mqtt_ws_bridge_loop(get_mqtt_status_service):
    """Drain the MqttStatusService WS queue and broadcast (task 2.3).

    This coroutine runs as a background task started during server startup.
    It reads events from the service's asyncio.Queue and fans them out to
    all connected /ws/arms/status clients.
    """
    while True:
        svc = get_mqtt_status_service()
        if svc is None:
            await asyncio.sleep(1.0)
            continue

        try:
            event = await svc.ws_queue.get()
            await broadcast_to_arms_ws(event)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.1)


async def handle_main_websocket(
    websocket: WebSocket,
    system_state: dict,
    capabilities_manager,
    message_envelope,
    reload_capabilities,
    get_topic_echo_service,
    get_performance_monitor,
    get_health_monitor,
    get_alert_engine,
    enhanced_services_available: bool,
    safety_manager=None,
):
    """Handle the main /ws WebSocket endpoint with capability negotiation.

    This is the core WebSocket loop extracted from dashboard_server.py.
    """
    await websocket.accept()
    client_id = str(uuid.uuid4())
    websocket_connections[client_id] = websocket

    try:
        # Send handshake with capabilities
        if message_envelope:
            handshake = message_envelope.create_handshake()
        else:
            handshake = {
                "status": "connected",
                "message": "Pragati ROS2 Dashboard ready (basic mode)",
                "capabilities": [],
            }
        await websocket.send_json(handshake)

        # Get update rate from capabilities
        if capabilities_manager:
            update_rate = capabilities_manager.get_server_config(
                "websocket_rate_hz", 1.0
            )
        else:
            update_rate = 1.0

        sleep_interval = 1.0 / update_rate if update_rate > 0 else 1.0
        hidden_sleep_interval = 10.0  # 0.1 Hz for hidden clients
        client_hidden = False

        # Track last-sent hashes for change detection (Task 1.3)
        _last_sent_hash: Dict[str, str] = {}

        while True:
            # Check for incoming messages from client (non-blocking)
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.01)
                if isinstance(msg, dict) and msg.get("type") == "visibility":
                    client_hidden = msg.get("state") == "hidden"
                elif isinstance(msg, dict) and msg.get("type") == "estop":
                    if safety_manager is not None:
                        safety_manager.activate_estop()
                        estop_status = safety_manager.get_status()
                        await broadcast("estop_activated", estop_status)
                elif isinstance(msg, dict) and msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif isinstance(msg, dict) and msg.get("type") == "refresh":
                    # Send current state for all categories (Task 1.2)
                    # System state
                    if capabilities_manager and message_envelope:
                        refresh_sys = message_envelope.create_envelope(
                            "system_update", system_state
                        )
                    else:
                        refresh_sys = system_state
                    await websocket.send_json(refresh_sys)

                    # Performance, health, alerts
                    if enhanced_services_available:
                        try:
                            perf_data = get_performance_monitor().get_summary()
                            if message_envelope:
                                perf_msg = message_envelope.create_envelope(
                                    "performance_update", perf_data
                                )
                            else:
                                perf_msg = {
                                    "type": "performance_update",
                                    "data": perf_data,
                                }
                            await websocket.send_json(perf_msg)
                        except Exception:
                            logger.warning(
                                "Failed to send performance data " "on refresh",
                                exc_info=True,
                            )

                        try:
                            health_data = get_health_monitor().get_system_health()
                            if message_envelope:
                                health_msg = message_envelope.create_envelope(
                                    "health_update", health_data
                                )
                            else:
                                health_msg = {
                                    "type": "health_update",
                                    "data": health_data,
                                }
                            await websocket.send_json(health_msg)
                        except Exception:
                            logger.warning(
                                "Failed to send health data on refresh",
                                exc_info=True,
                            )

                        try:
                            alert_engine = get_alert_engine()
                            alerts_data = {
                                "alerts": (alert_engine.get_active_alerts()),
                                "timestamp": (datetime.now().isoformat()),
                            }
                            if message_envelope:
                                alerts_msg = message_envelope.create_envelope(
                                    "alerts_update", alerts_data
                                )
                            else:
                                alerts_msg = {
                                    "type": "alerts_update",
                                    "data": alerts_data,
                                }
                            await websocket.send_json(alerts_msg)
                        except Exception:
                            logger.warning(
                                "Failed to send alerts data on refresh",
                                exc_info=True,
                            )
            except asyncio.TimeoutError:
                pass
            except RuntimeError:
                # Client disconnected — "Cannot call 'receive' once a
                # disconnect message has been received."  Break the loop
                # instead of logging the same error every iteration.
                break
            except Exception:
                logger.warning(
                    "Error receiving WebSocket message",
                    exc_info=True,
                )

            # Reload capabilities if changed
            if reload_capabilities:
                reload_capabilities()

            # Send periodic updates
            if capabilities_manager and message_envelope:
                data = message_envelope.create_envelope("system_update", system_state)
                if capabilities_manager.is_enabled("topic_stats"):
                    if get_topic_echo_service:
                        try:
                            topic_echo_service = await get_topic_echo_service()
                            all_stats = {}
                            for (
                                key,
                                subscription,
                            ) in topic_echo_service.subscriptions.items():
                                topic_name = subscription.topic_name
                                if topic_name not in all_stats:
                                    all_stats[topic_name] = (
                                        subscription.get_statistics()
                                    )
                            data["meta"]["topic_stats"] = all_stats
                        except Exception:
                            logger.warning(
                                "Failed to collect topic stats",
                                exc_info=True,
                            )
            else:
                data = system_state

            # Change detection: only send if data changed (Task 1.3)
            data_json = json.dumps(data, sort_keys=True, default=str)
            data_hash = hashlib.md5(data_json.encode()).hexdigest()
            if _last_sent_hash.get("system_state") != data_hash:
                await websocket.send_json(data)
                _last_sent_hash["system_state"] = data_hash

            # Push performance, health, and alerts data
            if enhanced_services_available:
                try:
                    perf_data = get_performance_monitor().get_summary()
                    if message_envelope:
                        perf_msg = message_envelope.create_envelope(
                            "performance_update", perf_data
                        )
                    else:
                        perf_msg = {
                            "type": "performance_update",
                            "data": perf_data,
                        }
                    perf_json = json.dumps(perf_msg, sort_keys=True, default=str)
                    perf_hash = hashlib.md5(perf_json.encode()).hexdigest()
                    if _last_sent_hash.get("performance") != perf_hash:
                        await websocket.send_json(perf_msg)
                        _last_sent_hash["performance"] = perf_hash
                except Exception:
                    logger.warning(
                        "Failed to send performance data",
                        exc_info=True,
                    )

                try:
                    health_data = get_health_monitor().get_system_health()
                    if message_envelope:
                        health_msg = message_envelope.create_envelope(
                            "health_update", health_data
                        )
                    else:
                        health_msg = {
                            "type": "health_update",
                            "data": health_data,
                        }
                    health_json = json.dumps(health_msg, sort_keys=True, default=str)
                    health_hash = hashlib.md5(health_json.encode()).hexdigest()
                    if _last_sent_hash.get("health") != health_hash:
                        await websocket.send_json(health_msg)
                        _last_sent_hash["health"] = health_hash
                except Exception:
                    logger.warning(
                        "Failed to send health data",
                        exc_info=True,
                    )

                try:
                    alert_engine = get_alert_engine()
                    alerts_data = {
                        "alerts": alert_engine.get_active_alerts(),
                        "timestamp": datetime.now().isoformat(),
                    }
                    if message_envelope:
                        alerts_msg = message_envelope.create_envelope(
                            "alerts_update", alerts_data
                        )
                    else:
                        alerts_msg = {
                            "type": "alerts_update",
                            "data": alerts_data,
                        }
                    alerts_json = json.dumps(alerts_msg, sort_keys=True, default=str)
                    alerts_hash = hashlib.md5(alerts_json.encode()).hexdigest()
                    if _last_sent_hash.get("alerts") != alerts_hash:
                        await websocket.send_json(alerts_msg)
                        _last_sent_hash["alerts"] = alerts_hash
                except Exception:
                    logger.warning(
                        "Failed to send alerts data",
                        exc_info=True,
                    )

            await asyncio.sleep(
                hidden_sleep_interval if client_hidden else sleep_interval
            )

    except Exception:
        logger.warning(
            "WebSocket connection error for client %s",
            client_id,
            exc_info=True,
        )
    finally:
        if client_id in websocket_connections:
            del websocket_connections[client_id]

        if get_topic_echo_service:
            try:
                topic_echo_service = await get_topic_echo_service()
                await topic_echo_service.cleanup_client(client_id)
            except Exception:
                pass


async def handle_launch_output(
    websocket: WebSocket,
    role: str,
    get_process_manager,
):
    """Stream launch process output over WebSocket."""
    if role not in ("arm", "vehicle"):
        await websocket.close(
            code=4000,
            reason="Invalid role. Use 'arm' or 'vehicle'.",
        )
        return

    await websocket.accept()
    _process_manager = get_process_manager()

    if _process_manager is None:
        await websocket.send_json({"error": "ProcessManager not initialized"})
        await websocket.close(code=4003)
        return

    queue: asyncio.Queue = asyncio.Queue()

    async def _on_line(msg) -> None:
        await queue.put(msg)

    try:
        buffered = await _process_manager.get_buffered_output(role)
        for line in buffered:
            if isinstance(line, dict):
                line["role"] = role
                await websocket.send_json(line)
            else:
                await websocket.send_json(
                    {"type": "output", "data": line, "role": role}
                )
    except Exception:
        pass

    _process_manager.subscribe(role, _on_line)
    try:
        while True:
            msg = await queue.get()
            if isinstance(msg, dict):
                msg["role"] = role
                await websocket.send_json(msg)
            else:
                await websocket.send_json({"type": "output", "data": msg, "role": role})
    except Exception:
        pass
    finally:
        _process_manager.unsubscribe(role, _on_line)


async def handle_arms_status(
    websocket: WebSocket,
    get_mqtt_status_service,
):
    """Stream arm status changes over WebSocket."""
    await websocket.accept()
    client_id = str(uuid.uuid4())
    _mqtt_status = get_mqtt_status_service()

    if _mqtt_status is None:
        # No MQTT service — send empty fleet state and keep connection open
        await websocket.send_json(
            {"type": "snapshot", "arms": {}, "broker_connected": False}
        )
        # Keep connection open, send periodic heartbeat
        try:
            while True:
                await asyncio.sleep(10)
                await websocket.send_json(
                    {"type": "snapshot", "arms": {}, "broker_connected": False}
                )
        except Exception:
            pass
        return

    # Register for broadcast (task 2.3)
    _arms_ws_connections[client_id] = websocket

    queue: asyncio.Queue = asyncio.Queue()

    def _on_change(arm_id: str, arm_data: dict) -> None:
        try:
            queue.put_nowait({"arm_id": arm_id, "data": arm_data})
        except asyncio.QueueFull:
            pass

    try:
        all_arms = _mqtt_status.get_all_arms()
        await websocket.send_json({"type": "snapshot", "arms": all_arms})
    except Exception:
        pass

    _mqtt_status.subscribe_changes(_on_change)
    try:
        while True:
            change = await queue.get()
            await websocket.send_json(
                {
                    "type": "change",
                    "arm_id": change["arm_id"],
                    "data": change["data"],
                }
            )
    except Exception:
        pass
    finally:
        _mqtt_status.unsubscribe_changes(_on_change)
        _arms_ws_connections.pop(client_id, None)


async def handle_sync_output(
    websocket: WebSocket,
    get_sync_manager,
):
    """Stream sync operation output over WebSocket."""
    await websocket.accept()
    sync_mgr = get_sync_manager() if get_sync_manager else None

    if sync_mgr is None:
        await websocket.send_json({"error": "SyncManager not initialized"})
        await websocket.close(code=4003)
        return

    queue: asyncio.Queue = asyncio.Queue()

    async def _on_line(line: str) -> None:
        try:
            queue.put_nowait(line)
        except asyncio.QueueFull:
            pass

    sync_mgr.subscribe_output(_on_line)
    try:
        while True:
            line = await queue.get()
            await websocket.send_json({"line": line})
    except Exception:
        pass
    finally:
        sync_mgr.unsubscribe_output(_on_line)
