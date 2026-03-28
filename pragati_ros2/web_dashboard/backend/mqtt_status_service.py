"""MQTT-based multi-arm status tracking service.

Subscribes to arm and vehicle status topics on the MQTT broker (star
topology: vehicle hub + arm spokes), maintains an in-memory state map,
and exposes an asyncio.Queue for WebSocket bridging.

The paho-mqtt dependency is optional — if missing, the service operates
in offline mode (no real MQTT connection, ``is_connected()`` returns False).
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional paho-mqtt import
# ---------------------------------------------------------------------------
try:
    import paho.mqtt.client as paho_mqtt

    PAHO_AVAILABLE = True
except ImportError:
    paho_mqtt = None  # type: ignore[assignment]
    PAHO_AVAILABLE = False
    logger.warning("paho-mqtt not installed — MQTT service runs in offline mode")

# ---------------------------------------------------------------------------
# Heartbeat connectivity states
# ---------------------------------------------------------------------------
CONN_CONNECTED = "connected"
CONN_STALE = "stale"
CONN_OFFLINE = "offline"


class MqttStatusService:
    """Track arm/vehicle status over MQTT with star topology.

    Parameters
    ----------
    broker_host:
        MQTT broker hostname (default ``"localhost"``).
    broker_port:
        MQTT broker port (default ``1883``).
    heartbeat_timeout:
        Seconds without a heartbeat before an arm is marked stale.
        Offline threshold is 2x this value.
    event_loop:
        The asyncio event loop to use for the outbound queue.
        If ``None``, the queue is created without a loop reference.
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        heartbeat_timeout: float = 5.0,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._heartbeat_timeout = heartbeat_timeout
        self._event_loop = event_loop

        # State map: arm entries keyed by arm_id, plus "vehicle" key
        self._arms: Dict[str, Dict[str, Any]] = {}
        self._vehicle: Dict[str, Any] = {
            "state": "unknown",
            "mode": None,
            "uptime": None,
            "error": None,
            "broker_connected": False,
            "connected_arm_count": 0,
            "total_arm_count": 0,
            "last_status": {},
        }
        self._lock = threading.Lock()

        self._connected = False
        self._connect_time: Optional[float] = None
        self._connect_time_iso: Optional[str] = None
        self._reconnect_attempts = 0

        self._change_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._callbacks_lock = threading.Lock()

        # Outbound queue for WebSocket bridge (task 2.1)
        self._ws_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # MQTT client — may be replaced in tests
        self._mqtt_client: Any = None
        self._running = False

        # Heartbeat checker task
        self._heartbeat_task: Optional[asyncio.Task] = None

        if PAHO_AVAILABLE and paho_mqtt is not None:
            self._mqtt_client = paho_mqtt.Client()
            self._mqtt_client.on_connect = self._on_connect
            self._mqtt_client.on_disconnect = self._on_disconnect
            self._mqtt_client.on_message = self._on_message

    # ------------------------------------------------------------------
    # Lifecycle (tasks 1.1, 1.2, 1.3)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Connect to the MQTT broker and begin listening."""
        if self._mqtt_client is None:
            logger.warning("No MQTT client available — cannot start")
            return
        self._running = True
        try:
            self._mqtt_client.connect(self._broker_host, self._broker_port)
            self._mqtt_client.loop_start()
            logger.info(
                "MqttStatusService started (broker=%s:%d)",
                self._broker_host,
                self._broker_port,
            )
        except Exception:
            logger.exception("Failed to connect to MQTT broker")

    def stop(self) -> None:
        """Disconnect cleanly from the MQTT broker (3s timeout)."""
        self._running = False

        # Cancel heartbeat checker
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                logger.exception("Error stopping MQTT client")
        self._connected = False
        self._connect_time = None

        # Broadcast disconnection via queue
        self._enqueue_ws_event(
            {
                "type": "mqtt_status",
                "mqtt_connected": False,
                "broker": self._broker_host,
            }
        )

    def start_heartbeat_checker(self) -> None:
        """Start the 1 Hz periodic heartbeat timeout checker (task 5.2).

        Must be called from an asyncio context (after server startup).
        """
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_check_loop())

    # ------------------------------------------------------------------
    # Query methods (task 1.4)
    # ------------------------------------------------------------------

    def get_all_arms(self) -> Dict[str, Dict[str, Any]]:
        """Return a deep copy of all tracked arm states."""
        with self._lock:
            return copy.deepcopy(self._arms)

    def get_arm(self, arm_id: str) -> Optional[Dict[str, Any]]:
        """Return a copy of a single arm's state, or ``None``."""
        with self._lock:
            data = self._arms.get(arm_id)
            if data is None:
                return None
            return copy.deepcopy(data)

    def get_vehicle(self) -> Dict[str, Any]:
        """Return a copy of the vehicle hub state."""
        with self._lock:
            return copy.deepcopy(self._vehicle)

    def is_connected(self) -> bool:
        """Return ``True`` if the MQTT client is currently connected."""
        return self._connected

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive MQTT status for the /api/mqtt/status endpoint."""
        with self._lock:
            vehicle = copy.deepcopy(self._vehicle)
        result: Dict[str, Any] = {
            "connected": self._connected,
            "broker": self._broker_host,
        }
        if self._connected and self._connect_time is not None:
            result["uptime_s"] = round(time.monotonic() - self._connect_time, 1)
        elif not self._connected and self._connect_time_iso is not None:
            result["last_connected"] = self._connect_time_iso
        result["vehicle"] = vehicle
        return result

    @property
    def ws_queue(self) -> asyncio.Queue:
        """The outbound asyncio.Queue for WebSocket bridging."""
        return self._ws_queue

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def send_command(self, arm_id: str, command: str) -> None:
        """Publish a command to ``pragati/arm/{arm_id}/command``.

        Raises :class:`ConnectionError` if not connected.
        """
        if not self._connected:
            raise ConnectionError("MQTT client is not connected")
        topic = f"pragati/arm/{arm_id}/command"
        payload = json.dumps({"action": command})
        self._mqtt_client.publish(topic, payload)

    # ------------------------------------------------------------------
    # Change subscription
    # ------------------------------------------------------------------

    def subscribe_changes(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register a callback ``(arm_id, arm_data)`` for state changes."""
        with self._callbacks_lock:
            self._change_callbacks.append(callback)

    def unsubscribe_changes(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Remove a previously registered callback."""
        with self._callbacks_lock:
            try:
                self._change_callbacks.remove(callback)
            except ValueError:
                pass

    def _notify_change(self, arm_id: str, arm_data: Dict[str, Any]) -> None:
        with self._callbacks_lock:
            callbacks = list(self._change_callbacks)
        for cb in callbacks:
            try:
                cb(arm_id, copy.deepcopy(arm_data))
            except Exception:
                logger.exception("Error in change callback")

    # ------------------------------------------------------------------
    # WebSocket queue bridge (tasks 2.1, 2.2, 2.4)
    # ------------------------------------------------------------------

    def _enqueue_ws_event(self, event: Dict[str, Any]) -> None:
        """Put an event on the WS queue, dropping oldest on overflow."""
        try:
            self._ws_queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest and retry
            try:
                self._ws_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._ws_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("WS event queue overflow — dropping event")

    # ------------------------------------------------------------------
    # Heartbeat timeout (tasks 5.1-5.5)
    # ------------------------------------------------------------------

    def check_heartbeat_timeouts(self) -> None:
        """Check all arms for heartbeat timeout transitions.

        State machine:
        - connected: heartbeat within timeout
        - stale: heartbeat age > timeout
        - offline: heartbeat age > 2 * timeout
        - recovery: new heartbeat received -> connected
        """
        now = time.monotonic()
        transitions: List[tuple] = []

        with self._lock:
            for arm_id, arm in self._arms.items():
                hb = arm.get("last_heartbeat_monotonic")
                if hb is None:
                    continue

                age = now - hb
                old_connectivity = arm.get("connectivity", CONN_CONNECTED)

                if age > 2 * self._heartbeat_timeout:
                    new_connectivity = CONN_OFFLINE
                elif age > self._heartbeat_timeout:
                    new_connectivity = CONN_STALE
                else:
                    new_connectivity = CONN_CONNECTED

                if new_connectivity != old_connectivity:
                    arm["connectivity"] = new_connectivity
                    arm["connected"] = new_connectivity == CONN_CONNECTED
                    snapshot = copy.deepcopy(arm)
                    transitions.append((arm_id, snapshot))

        # Update vehicle arm counts after transitions
        if transitions:
            with self._lock:
                self._update_arm_count()

        # Notify outside the lock
        for arm_id, snapshot in transitions:
            self._notify_change(arm_id, snapshot)
            # Broadcast via WS queue (task 5.5)
            self._enqueue_ws_event(
                {
                    "type": "arm_status",
                    "arm_id": arm_id,
                    **self._arm_to_ws_payload(snapshot),
                }
            )

    async def _heartbeat_check_loop(self) -> None:
        """Run heartbeat timeout checks at 1 Hz."""
        while True:
            await asyncio.sleep(1.0)
            try:
                self.check_heartbeat_timeouts()
            except Exception:
                logger.debug("Heartbeat check error", exc_info=True)

    # ------------------------------------------------------------------
    # Reconnection backoff
    # ------------------------------------------------------------------

    def _calculate_backoff(self, attempt: int) -> float:
        """Exponential backoff: 1, 2, 4, 8, ... capped at 30 s."""
        return min(2**attempt, 30.0)

    # ------------------------------------------------------------------
    # paho-mqtt callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        self._connected = True
        self._connect_time = time.monotonic()
        self._connect_time_iso = datetime.now(timezone.utc).isoformat()
        self._reconnect_attempts = 0
        logger.info("MQTT connected (rc=%s)", rc)

        # Update vehicle broker status
        with self._lock:
            self._vehicle["broker_connected"] = True

        # Subscribe to arm and vehicle topics (task 3.3)
        if client is not None:
            try:
                client.subscribe("topic/+")
                client.subscribe("pragati/arm/+/cotton_count")
                client.subscribe("pragati/arm/+/error")
                client.subscribe("pragati/vehicle/status")
            except Exception:
                logger.exception("Failed to subscribe to topics")

        # Broadcast connection event via WS queue (task 2.4)
        self._enqueue_ws_event(
            {
                "type": "mqtt_status",
                "mqtt_connected": True,
                "broker": self._broker_host,
            }
        )

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        self._connected = False
        logger.warning("MQTT disconnected (rc=%s)", rc)

        # Update vehicle broker status
        with self._lock:
            self._vehicle["broker_connected"] = False

        # Broadcast disconnection event via WS queue (task 2.4)
        self._enqueue_ws_event(
            {
                "type": "mqtt_status",
                "mqtt_connected": False,
                "broker": self._broker_host,
            }
        )

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Route incoming MQTT messages to handlers."""
        topic: str = msg.topic
        payload: str = msg.payload.decode("utf-8", errors="replace")

        if topic.startswith("topic/ArmStatus_"):
            arm_id = topic.removeprefix("topic/ArmStatus_")
            self._on_status_message(arm_id, payload)
            return

        parts = topic.split("/")
        # pragati/arm/{arm_id}/{type} or pragati/vehicle/status
        if len(parts) < 3 or parts[0] != "pragati":
            return

        if parts[1] == "vehicle" and len(parts) == 3:
            msg_type = parts[2]
            if msg_type == "status":
                self._on_vehicle_status(payload)
            return

        if parts[1] == "arm" and len(parts) == 4:
            arm_id = parts[2]
            msg_type = parts[3]

            if msg_type == "status":
                self._on_status_message(arm_id, payload)
            elif msg_type == "heartbeat":
                self._on_heartbeat(arm_id)
            elif msg_type == "cotton_count":
                self._on_cotton_count(arm_id, payload)
            elif msg_type == "error":
                self._on_arm_error(arm_id, payload)

    # ------------------------------------------------------------------
    # Internal message handlers
    # ------------------------------------------------------------------

    def _arm_to_ws_payload(self, arm: Dict[str, Any]) -> Dict[str, Any]:
        """Convert internal arm state to WS-friendly payload."""
        return {
            "state": arm.get("state", "unknown"),
            "cotton_count": arm.get("cotton_count", 0),
            "temperature_c": arm.get("temperature_c"),
            "connectivity": arm.get("connectivity", CONN_CONNECTED),
            "connected": arm.get("connected", False),
            "last_heartbeat": arm.get("last_heartbeat"),
        }

    def _on_status_message(self, arm_id: str, payload: str) -> None:
        """Process a status message for an arm (task 5.1: also updates heartbeat)."""
        normalized = payload.strip()
        if not normalized:
            logger.debug("Ignoring empty arm status payload for %s", arm_id)
            return

        plain_map = {
            "ready": "ready",
            "busy": "busy",
            "ack": "ready",
            "error": "error",
            "uninitialised": "initializing",
            "offline": "offline",
        }
        mapped_state = plain_map.get(normalized.lower())
        if mapped_state is None:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                logger.debug("Ignoring unknown arm status payload for %s: %s", arm_id, payload)
                return
            state = data.get("state", "unknown")
        else:
            data = {"state": mapped_state}
            state = mapped_state

        now_mono = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()
        connectivity = CONN_OFFLINE if state == "offline" else CONN_CONNECTED
        connected = connectivity == CONN_CONNECTED

        with self._lock:
            if arm_id not in self._arms:
                self._arms[arm_id] = {
                    "state": state,
                    "last_heartbeat": now_iso,
                    "last_heartbeat_monotonic": now_mono,
                    "connected": connected,
                    "connectivity": connectivity,
                    "cotton_count": data.get("cotton_count", 0),
                    "temperature_c": data.get("temperature_c"),
                    "last_status": data,
                    "last_error": None,
                }
            else:
                arm = self._arms[arm_id]
                arm["state"] = state
                arm["connected"] = connected
                arm["connectivity"] = connectivity
                arm["last_heartbeat"] = now_iso
                arm["last_heartbeat_monotonic"] = now_mono
                arm["last_status"] = data
                if "cotton_count" in data:
                    arm["cotton_count"] = data["cotton_count"]
                if "temperature_c" in data:
                    arm["temperature_c"] = data["temperature_c"]

            arm_snapshot = copy.deepcopy(self._arms[arm_id])
            self._update_arm_count()

        self._notify_change(arm_id, arm_snapshot)

        # Enqueue for WebSocket bridge (task 2.2)
        self._enqueue_ws_event(
            {
                "type": "arm_status",
                "arm_id": arm_id,
                **self._arm_to_ws_payload(arm_snapshot),
            }
        )

    def _on_heartbeat(self, arm_id: str) -> None:
        """Process a heartbeat for an arm."""
        now_mono = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            if arm_id in self._arms:
                arm = self._arms[arm_id]
                arm["last_heartbeat"] = now_iso
                arm["last_heartbeat_monotonic"] = now_mono
                arm["connected"] = True
                arm["connectivity"] = CONN_CONNECTED
            else:
                self._arms[arm_id] = {
                    "state": "unknown",
                    "last_heartbeat": now_iso,
                    "last_heartbeat_monotonic": now_mono,
                    "connected": True,
                    "connectivity": CONN_CONNECTED,
                    "cotton_count": 0,
                    "temperature_c": None,
                    "last_status": {},
                    "last_error": None,
                }

    def _on_cotton_count(self, arm_id: str, payload: str) -> None:
        """Process a cotton count update for an arm."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in cotton_count for %s", arm_id)
            return

        count = data.get("count", data.get("cotton_count", 0))
        with self._lock:
            if arm_id in self._arms:
                self._arms[arm_id]["cotton_count"] = count
                arm_snapshot = copy.deepcopy(self._arms[arm_id])
            else:
                return

        self._notify_change(arm_id, arm_snapshot)
        self._enqueue_ws_event(
            {
                "type": "arm_status",
                "arm_id": arm_id,
                **self._arm_to_ws_payload(arm_snapshot),
            }
        )

    def _on_arm_error(self, arm_id: str, payload: str) -> None:
        """Process an error message for an arm."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in error for %s", arm_id)
            return

        with self._lock:
            if arm_id in self._arms:
                self._arms[arm_id]["last_error"] = data
                self._arms[arm_id]["state"] = "error"
                arm_snapshot = copy.deepcopy(self._arms[arm_id])
            else:
                return

        self._notify_change(arm_id, arm_snapshot)
        self._enqueue_ws_event(
            {
                "type": "arm_status",
                "arm_id": arm_id,
                **self._arm_to_ws_payload(arm_snapshot),
            }
        )

    # ------------------------------------------------------------------
    # Vehicle status (tasks 4.1, 4.2, 4.3)
    # ------------------------------------------------------------------

    def _on_vehicle_status(self, payload: str) -> None:
        """Process vehicle status from /pragati/vehicle/status."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in vehicle status")
            return

        with self._lock:
            self._vehicle["state"] = data.get("state", "unknown")
            self._vehicle["mode"] = data.get("mode")
            self._vehicle["uptime"] = data.get("uptime")
            self._vehicle["error"] = data.get("error")
            self._vehicle["last_status"] = data
            vehicle_snapshot = copy.deepcopy(self._vehicle)

        self._enqueue_ws_event(
            {
                "type": "vehicle_status",
                **vehicle_snapshot,
            }
        )

    def _update_arm_count(self) -> None:
        """Update connected/total arm count in vehicle state (task 4.3).

        Must be called with self._lock held.
        """
        total = len(self._arms)
        connected = sum(
            1
            for a in self._arms.values()
            if a.get("connectivity", CONN_CONNECTED) == CONN_CONNECTED
        )
        self._vehicle["connected_arm_count"] = connected
        self._vehicle["total_arm_count"] = total
