"""Fleet Health Service — HTTP health polling + MQTT status tracking.

Polls each fleet member's /health endpoint over HTTP and subscribes
to MQTT topics for real-time operational state and pick count updates.

This is a SEPARATE service from MqttStatusService — it is a passive
observer for the fleet hub view (dev dashboard only).
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Pre-import httpx exception classes so they are available even if
# tests patch the httpx module reference.
_HTTPX_NETWORK_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    OSError,
)

# ---------------------------------------------------------------------------
# Optional paho-mqtt import
# ---------------------------------------------------------------------------
try:
    import paho.mqtt.client as paho_mqtt

    PAHO_AVAILABLE = True
except ImportError:
    paho_mqtt = None  # type: ignore[assignment]
    PAHO_AVAILABLE = False
    logger.warning("paho-mqtt not installed — FleetHealthService runs HTTP-only")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 5
HEALTH_PORT = 8090


class FleetHealthService:
    """Track fleet member health via HTTP polling and MQTT events.

    Parameters
    ----------
    fleet_config:
        The ``fleet`` section from dashboard.yaml. May be ``None`` or
        empty dict if no fleet is configured.
    """

    def __init__(self, fleet_config: Optional[Dict[str, Any]]) -> None:
        self._members: List[Dict[str, Any]] = []
        self._members_by_name: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._mqtt_client: Any = None
        self._broker_ip: Optional[str] = None

        self._parse_config(fleet_config)

    # ------------------------------------------------------------------
    # Config parsing
    # ------------------------------------------------------------------

    def _parse_config(self, fleet_config: Optional[Dict[str, Any]]) -> None:
        """Parse fleet config into member list."""
        if not fleet_config:
            return

        vehicle = fleet_config.get("vehicle")
        arms = fleet_config.get("arms") or []

        # Add vehicle if it has a valid IP
        if vehicle and isinstance(vehicle, dict):
            ip = vehicle.get("ip", "")
            if ip and ip.strip():
                member = self._make_member(
                    name=vehicle.get("name", "vehicle"),
                    ip=ip.strip(),
                    role=vehicle.get("role", "vehicle"),
                )
                self._members.append(member)
                self._members_by_name[member["name"]] = member
                self._broker_ip = ip.strip()

        # Add arms
        for arm in arms:
            if not isinstance(arm, dict):
                continue
            ip = arm.get("ip", "")
            if ip and ip.strip():
                member = self._make_member(
                    name=arm.get("name", "arm"),
                    ip=ip.strip(),
                    role=arm.get("role", "arm"),
                )
                self._members.append(member)
                self._members_by_name[member["name"]] = member

    @staticmethod
    def _make_member(name: str, ip: str, role: str) -> Dict[str, Any]:
        """Create a member dict with default values."""
        return {
            "name": name,
            "ip": ip,
            "role": role,
            "status": "unknown",
            "cpu_percent": None,
            "memory_percent": None,
            "last_seen": None,
            "operational_state": "UNKNOWN",
            "pick_count": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_fleet_status(self) -> List[Dict[str, Any]]:
        """Return a deep copy of all fleet member statuses."""
        with self._lock:
            return copy.deepcopy(self._members)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the health polling loop and MQTT client."""
        self._running = True
        self._start_mqtt()
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("FleetHealthService started (%d members)", len(self._members))

    async def stop(self) -> None:
        """Stop the health polling loop and MQTT client."""
        self._running = False

        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        self._stop_mqtt()
        logger.info("FleetHealthService stopped")

    # ------------------------------------------------------------------
    # HTTP health polling (Task 4.1)
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Poll all members every POLL_INTERVAL_S seconds."""
        while self._running:
            try:
                await self._poll_all_members()
            except Exception:
                logger.debug("Fleet health poll cycle failed", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL_S)

    async def _poll_all_members(self) -> None:
        """Poll all members concurrently."""
        if not self._members:
            return

        tasks = [self._poll_member_health(member) for member in self._members]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_member_health(self, member: Dict[str, Any]) -> None:
        """Poll a single member's health endpoint."""
        url = f"http://{member['ip']}:{HEALTH_PORT}/health"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(POLL_TIMEOUT_S)
            ) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                data = resp.json()
                now_iso = datetime.now(timezone.utc).isoformat()
                with self._lock:
                    member["status"] = "online"
                    member["cpu_percent"] = data.get("cpu_percent")
                    member["memory_percent"] = data.get("memory_percent")
                    member["last_seen"] = now_iso
            else:
                with self._lock:
                    member["status"] = "offline"

        except _HTTPX_NETWORK_ERRORS:
            with self._lock:
                member["status"] = "offline"
        except Exception:
            logger.debug("Unexpected error polling %s", member["name"], exc_info=True)
            with self._lock:
                member["status"] = "offline"

    # ------------------------------------------------------------------
    # MQTT integration (Task 4.2)
    # ------------------------------------------------------------------

    def _start_mqtt(self) -> None:
        """Connect MQTT client to vehicle broker (if available)."""
        if not PAHO_AVAILABLE or paho_mqtt is None:
            logger.info("FleetHealthService MQTT: paho-mqtt not available, HTTP-only")
            return

        if not self._broker_ip:
            logger.info("FleetHealthService MQTT: no broker IP, HTTP-only")
            return

        try:
            self._mqtt_client = paho_mqtt.Client()
            self._mqtt_client.on_connect = self._on_mqtt_connect
            self._mqtt_client.on_message = self._on_mqtt_raw_message
            self._mqtt_client.connect(self._broker_ip, 1883)
            self._mqtt_client.loop_start()
            logger.info("FleetHealthService MQTT connected to %s", self._broker_ip)
        except Exception:
            logger.warning(
                "FleetHealthService MQTT: broker unreachable at %s, "
                "continuing HTTP-only",
                self._broker_ip,
                exc_info=True,
            )
            self._mqtt_client = None

    def _stop_mqtt(self) -> None:
        """Disconnect MQTT client."""
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                logger.debug("Error stopping fleet MQTT client", exc_info=True)
            self._mqtt_client = None

    def _on_mqtt_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        """Subscribe to fleet topics on connect."""
        if client is not None:
            try:
                client.subscribe("pragati/+/status")
                client.subscribe("pragati/+/pick_start")
                client.subscribe("pragati/vehicle/shutdown")
                logger.info("FleetHealthService MQTT subscribed to topics")
            except Exception:
                logger.warning(
                    "FleetHealthService MQTT: subscribe failed", exc_info=True
                )

    def _on_mqtt_raw_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Route raw paho message to internal handler."""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8", errors="replace")
            self._on_mqtt_message(topic, payload)
        except Exception:
            logger.debug("FleetHealthService MQTT message error", exc_info=True)

    def _on_mqtt_message(self, topic: str, payload: str) -> None:
        """Process an MQTT message by topic.

        Topics:
        - pragati/<name>/status -> update operational_state
        - pragati/<name>/pick_start -> increment pick_count
        - pragati/vehicle/shutdown -> log warning
        """
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != "pragati":
            return

        member_name = parts[1]
        msg_type = parts[2]

        if msg_type == "shutdown" and member_name == "vehicle":
            logger.warning("Fleet: vehicle shutdown message received")
            return

        if msg_type == "status":
            self._handle_status_message(member_name, payload)
        elif msg_type == "pick_start":
            self._handle_pick_start(member_name)

    def _handle_status_message(self, member_name: str, payload: str) -> None:
        """Update member operational_state from MQTT status."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "FleetHealthService: invalid JSON in status for %s",
                member_name,
            )
            return

        state = data.get("state", "UNKNOWN")

        with self._lock:
            member = self._members_by_name.get(member_name)
            if member is not None:
                member["operational_state"] = state

    def _handle_pick_start(self, member_name: str) -> None:
        """Increment pick_count for the named member."""
        with self._lock:
            member = self._members_by_name.get(member_name)
            if member is not None:
                member["pick_count"] = member.get("pick_count", 0) + 1
