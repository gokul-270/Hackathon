"""Entity Manager — unified fleet entity discovery, polling, and REST API.

Replaces the older FleetHealthService with a more general entity model that
supports config.env parsing, mDNS discovery, per-entity polling with offline
detection, and REST/WebSocket interfaces.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .entity_model import Entity
from .ping_monitor import PingMonitor
from .service_registry import get_mqtt_status_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    YAML_AVAILABLE = False

try:
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

    ZEROCONF_AVAILABLE = True
except ImportError:
    Zeroconf = None  # type: ignore[assignment]
    ServiceBrowser = None  # type: ignore[assignment]
    ServiceStateChange = None  # type: ignore[assignment]
    ZEROCONF_AVAILABLE = False

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    PSUTIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 18  # Agent /status is slow (~8-13s) through WSL portproxy chain
AGENT_PORT = 8091
OFFLINE_THRESHOLD = 3  # consecutive failures before marking offline
MDNS_SERVICE_TYPE = "_pragati-agent._tcp.local."
MDNS_REMOVAL_GRACE_S = 300  # 5 minutes
BACKOFF_MULTIPLIER = 3
MAX_POLL_INTERVAL_S = 90  # 3x base, capped
SUSPEND_THRESHOLD = 50  # Consecutive failures before suspending polling entirely
PING_INTERVAL_S = 3.0
PING_TIMEOUT_S = 2.0
PING_FAILURE_THRESHOLD = 2
HEALTH_INTERVAL_S = 10.0
HEALTH_TIMEOUT_S = 5.0
HEALTH_FAILURE_THRESHOLD = 2

_HTTPX_NETWORK_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    OSError,
)

# Default paths (overridable for testing)
_DEFAULT_CONFIG_ENV_PATH = Path(__file__).resolve().parents[2] / "config.env"
_DEFAULT_DASHBOARD_YAML_PATH = Path(__file__).resolve().parent.parent / "config" / "dashboard.yaml"
_DEFAULT_ENTITIES_YAML_PATH = Path(__file__).resolve().parent.parent / "config" / "entities.yaml"

# ---------------------------------------------------------------------------
# IP validation helper
# ---------------------------------------------------------------------------

# Regex for IPv4 address
_IPV4_PATTERN = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


class DuplicateIPError(Exception):
    """Raised when adding an entity with an IP already in the fleet."""

    def __init__(self, message: str, existing_entity_id: str) -> None:
        super().__init__(message)
        self.existing_entity_id = existing_entity_id


class VehicleExistsError(Exception):
    """Raised when adding a vehicle entity but one already exists."""

    def __init__(self, message: str, existing_entity_id: str) -> None:
        super().__init__(message)
        self.existing_entity_id = existing_entity_id


class SlotConflictError(Exception):
    """Raised when a target group/slot is already occupied."""

    def __init__(self, message: str, existing_entity_id: str) -> None:
        super().__init__(message)
        self.existing_entity_id = existing_entity_id


def _is_valid_slot_for_type(entity_type: str, slot: str) -> bool:
    """Validate slot format for an entity type."""
    if entity_type == "vehicle":
        return slot == "vehicle"
    if entity_type == "arm":
        return re.fullmatch(r"arm-[1-9][0-9]*", slot) is not None
    return False


def _is_valid_ip(ip_str: str) -> bool:
    """Check if a string is a valid IPv4 address."""
    if not ip_str or not ip_str.strip():
        return False
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except ValueError:
        return False


def _parse_int(value: str | None) -> int | None:
    """Parse a string to int, returning None on failure."""
    if not value:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# EntityManager
# ---------------------------------------------------------------------------


class EntityManager:
    """Manage fleet entities: discovery, polling, state, and subscriptions.

    Parameters
    ----------
    config_env_path : Path | None
        Path to config.env. Defaults to repo root.
    dashboard_yaml_path : Path | None
        Path to dashboard.yaml for fallback config.
    """

    def __init__(
        self,
        config_env_path: Path | None = None,
        dashboard_yaml_path: Path | None = None,
        entities_yaml_path: Path | None = None,
    ) -> None:
        self._entities: dict[str, Entity] = {}
        self._failure_counts: dict[str, int] = {}
        self._agent_failure_counts: dict[str, int] = {}
        self._poll_intervals: dict[str, float] = {}
        self._last_polled: dict[str, float] = {}
        self._suspended: set[str] = set()
        self._subscribers: list[asyncio.Queue] = []
        self._poll_task: Optional[asyncio.Task] = None
        self._health_poll_task: Optional[asyncio.Task] = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._zeroconf: Any = None
        self._browser: Any = None
        self._mdns_departure_timers: dict[str, float] = {}
        self._ping_monitor: PingMonitor | None = None
        self._status_poll_interval_s = 30.0

        config_env = config_env_path or _DEFAULT_CONFIG_ENV_PATH
        yaml_path = dashboard_yaml_path or _DEFAULT_DASHBOARD_YAML_PATH
        self._dashboard_yaml_path = yaml_path
        self._entities_yaml_path = entities_yaml_path or _DEFAULT_ENTITIES_YAML_PATH

        # Detect local IPs for mDNS self-dedup
        self._local_ips: set[str] = self._detect_local_ips()

        # Read role from dashboard.yaml
        local_role = self._read_role_from_yaml(yaml_path)

        # Always add local entity
        self._add_local_entity(local_role)

        # Parse config.env
        found_remote = self._parse_config_env(config_env)

        # Fallback to dashboard.yaml if no remote entities from config.env
        if not found_remote and yaml_path.exists():
            self._parse_dashboard_yaml_fallback(yaml_path)

        # Overlay group/slot/name from entities.yaml (preserves config.env IPs)
        self._load_entities_yaml()

    # ------------------------------------------------------------------
    # Local identity detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_local_ips() -> set[str]:
        """Detect all IPv4 addresses on this machine for mDNS self-dedup."""
        ips: set[str] = {"127.0.0.1"}
        if PSUTIL_AVAILABLE:
            try:
                for addrs in psutil.net_if_addrs().values():
                    for addr in addrs:
                        # AF_INET = 2 (IPv4)
                        if addr.family == 2 and addr.address:
                            ips.add(addr.address)
            except Exception:
                logger.debug("Failed to detect local IPs via psutil", exc_info=True)
        else:
            # Fallback: use socket to get primary IP
            import socket

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ips.add(s.getsockname()[0])
                s.close()
            except Exception:
                pass
        return ips

    def _get_primary_local_ip(self) -> str | None:
        """Return the primary non-loopback local IP, or None."""
        for ip in self._local_ips:
            if ip != "127.0.0.1":
                return ip
        return None

    @staticmethod
    def _read_role_from_yaml(yaml_path: Path) -> str:
        """Read the 'role' field from dashboard.yaml. Defaults to 'dev'."""
        if not YAML_AVAILABLE or not yaml_path.exists():
            return "dev"
        try:
            with open(yaml_path) as f:
                config = yaml.safe_load(f) or {}
            role = config.get("role", "dev")
            if role in ("arm", "vehicle", "dev"):
                return role
            logger.warning("Unknown role '%s' in dashboard.yaml, defaulting to 'dev'", role)
            return "dev"
        except Exception:
            logger.debug("Failed to read role from dashboard.yaml", exc_info=True)
            return "dev"

    # ------------------------------------------------------------------
    # Config parsing (Task 2.2)
    # ------------------------------------------------------------------

    def _add_local_entity(self, role: str = "dev") -> None:
        """Add the local entity (always present).

        The entity_type is derived from the dashboard role:
        - 'arm' role -> entity_type 'arm'
        - 'vehicle' role -> entity_type 'vehicle'
        - 'dev' role -> entity_type 'dev' (development workstation)
        """
        entity_type = role if role in ("arm", "vehicle", "dev") else "dev"
        local_ip = self._get_primary_local_ip()
        self._entities["local"] = Entity(
            id="local",
            name="Local Machine",
            entity_type=entity_type,
            source="local",
            ip=local_ip,
        )

    def _parse_config_env(self, config_path: Path) -> bool:
        """Parse config.env for entity IPs.

        Returns True if at least one remote entity was found.
        """
        if not config_path.exists():
            logger.warning("config.env not found at %s", config_path)
            return False

        lines = config_path.read_text().splitlines()
        env_vars: dict[str, str] = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            # Strip quotes from value
            value = value.strip().strip('"').strip("'")
            env_vars[key.strip()] = value

        found_remote = False
        seen_ips: dict[str, str] = {}  # ip -> entity_id (for dup detection)

        # Collect user vars for later metadata injection
        user_vars: dict[str, str] = {}
        for key, value in env_vars.items():
            if key.endswith("_USER") and key != "RPI_USER":
                user_vars[key] = value

        # Store RPI_IP as metadata on local entity
        rpi_ip = env_vars.get("RPI_IP")
        if rpi_ip:
            self._entities["local"].metadata["rpi_ip"] = rpi_ip

        # Store RPI_USER as metadata on local entity
        rpi_user = env_vars.get("RPI_USER")
        if rpi_user:
            self._entities["local"].metadata["user"] = rpi_user

        # Parse ARM_{N}_IP and ARM{N}_IP patterns
        arm_pattern = re.compile(r"^ARM_?(\d+)_IP$")
        arm_entities_seen: dict[str, str] = {}  # entity_id -> ip

        # Parse ALL_ARMS allowlist (e.g. "arm1,arm2") — if set, only
        # listed arms are accepted.  Absent or empty means accept all.
        all_arms_raw = env_vars.get("ALL_ARMS", "").strip()
        allowed_arms: set[str] | None = None
        if all_arms_raw:
            allowed_arms = {a.strip().lower() for a in all_arms_raw.split(",") if a.strip()}

        for key, value in env_vars.items():
            match = arm_pattern.match(key)
            if match:
                arm_num = match.group(1)
                entity_id = f"arm{arm_num}"
                ip = value.strip()

                if not ip:
                    continue

                if not _is_valid_ip(ip):
                    logger.warning("Skipping %s: malformed IP '%s'", key, ip)
                    continue

                # Filter against ALL_ARMS allowlist
                if allowed_arms is not None and entity_id not in allowed_arms:
                    logger.warning(
                        "Skipping %s: %s not in ALL_ARMS (%s)",
                        key,
                        entity_id,
                        all_arms_raw,
                    )
                    continue

                # Deduplication: ARM_1_IP and ARM1_IP both -> arm1
                if entity_id in arm_entities_seen:
                    # Already seen this entity, skip duplicate key
                    continue

                # Merge into local entity if this IP is the local machine
                if ip in self._local_ips:
                    logger.info(
                        "Merging %s (%s) into local entity: " "local machine identified as %s",
                        key,
                        ip,
                        entity_id,
                    )
                    local = self._entities.get("local")
                    if local is not None:
                        local.id = entity_id
                        local.name = f"Arm {arm_num} RPi"
                        local.entity_type = "arm"
                        # Re-key: remove "local", store under entity_id
                        self._entities[entity_id] = self._entities.pop("local")
                    arm_entities_seen[entity_id] = ip
                    seen_ips[ip] = entity_id
                    found_remote = True
                    continue

                # Check for duplicate IP across different entities
                if ip in seen_ips and seen_ips[ip] != entity_id:
                    logger.warning(
                        "Duplicate IP %s: used by both '%s' and '%s'",
                        ip,
                        seen_ips[ip],
                        entity_id,
                    )

                arm_entities_seen[entity_id] = ip
                seen_ips[ip] = entity_id

                entity = Entity(
                    id=entity_id,
                    name=f"Arm {arm_num} RPi",
                    entity_type="arm",
                    source="remote",
                    ip=ip,
                    poll_host=env_vars.get(f"ARM_{arm_num}_POLL_HOST")
                    or env_vars.get(f"ARM{arm_num}_POLL_HOST"),
                    poll_port=_parse_int(
                        env_vars.get(f"ARM_{arm_num}_POLL_PORT")
                        or env_vars.get(f"ARM{arm_num}_POLL_PORT")
                    ),
                )

                # Inject user metadata
                # Check ARM{N}_USER or ARM_{N}_USER
                for ukey in [
                    f"ARM{arm_num}_USER",
                    f"ARM_{arm_num}_USER",
                ]:
                    uval = env_vars.get(ukey)
                    if uval:
                        entity.metadata["user"] = uval
                        break

                self._entities[entity_id] = entity
                found_remote = True

        # Parse VEHICLE_IP
        vehicle_ip = env_vars.get("VEHICLE_IP")
        if vehicle_ip and vehicle_ip.strip():
            ip = vehicle_ip.strip()
            if not _is_valid_ip(ip):
                logger.warning("Skipping VEHICLE_IP: malformed IP '%s'", ip)
            elif ip in self._local_ips:
                logger.info("Skipping VEHICLE_IP (%s): matches local machine IP", ip)
            else:
                entity_id = "vehicle"

                if ip in seen_ips and seen_ips[ip] != entity_id:
                    logger.warning(
                        "Duplicate IP %s: used by both '%s' and '%s'",
                        ip,
                        seen_ips[ip],
                        entity_id,
                    )

                seen_ips[ip] = entity_id
                self._entities[entity_id] = Entity(
                    id=entity_id,
                    name="Vehicle RPi",
                    entity_type="vehicle",
                    source="remote",
                    ip=ip,
                    poll_host=env_vars.get("VEHICLE_POLL_HOST"),
                    poll_port=_parse_int(env_vars.get("VEHICLE_POLL_PORT")),
                )
                found_remote = True

        return found_remote

    # ------------------------------------------------------------------
    # dashboard.yaml fallback (Task 2.9)
    # ------------------------------------------------------------------

    def _parse_dashboard_yaml_fallback(self, yaml_path: Path) -> None:
        """Parse fleet section from dashboard.yaml as fallback."""
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not available, cannot fall back to dashboard.yaml")
            return

        try:
            with open(yaml_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            logger.warning("Failed to read dashboard.yaml at %s", yaml_path, exc_info=True)
            return

        fleet = config.get("fleet")
        if not fleet:
            return

        logger.warning(
            "Falling back to dashboard.yaml fleet config. "
            "This is deprecated -- please configure entities in config.env"
        )

        # Parse vehicle
        vehicle = fleet.get("vehicle")
        if vehicle and isinstance(vehicle, dict):
            ip = vehicle.get("ip", "")
            if ip and _is_valid_ip(ip) and ip not in self._local_ips:
                self._entities["vehicle"] = Entity(
                    id="vehicle",
                    name=vehicle.get("name", "Vehicle RPi"),
                    entity_type="vehicle",
                    source="remote",
                    ip=ip,
                )

        # Parse arms
        arms = fleet.get("arms") or []
        for i, arm in enumerate(arms):
            if not isinstance(arm, dict):
                continue
            ip = arm.get("ip", "")
            if not ip or not _is_valid_ip(ip):
                continue
            if ip in self._local_ips:
                continue

            # Derive entity ID from name (e.g. "arm1-rpi" -> "arm1")
            name = arm.get("name", f"arm{i + 1}-rpi")
            entity_id = re.sub(r"[^a-z0-9]", "", name.lower().split("-")[0])
            if not entity_id:
                entity_id = f"arm{i + 1}"

            self._entities[entity_id] = Entity(
                id=entity_id,
                name=name,
                entity_type="arm",
                source="remote",
                ip=ip,
            )

    # ------------------------------------------------------------------
    # entities.yaml persistence (group/slot/name overlay)
    # ------------------------------------------------------------------

    def _load_entities_yaml(self) -> None:
        """Load entities from entities.yaml.

        Two modes:
        - **Overlay**: if the entity already exists (from config.env), merge
          group/slot/name/membership_state fields.
        - **Create**: if the entity does NOT exist but has an IP in the YAML,
          create it as a remote entity.  This ensures entities added via the
          dashboard UI (which saves to entities.yaml) survive restarts even
          if they are not listed in config.env / ALL_ARMS.
        """
        if not YAML_AVAILABLE:
            logger.debug("PyYAML not installed — skipping entities.yaml load")
            return

        path = self._entities_yaml_path
        if not path.exists():
            logger.debug("entities.yaml not found at %s — nothing to overlay", path)
            return

        try:
            data = yaml.safe_load(path.read_text())  # type: ignore[union-attr]
        except Exception:
            logger.warning("Failed to parse entities.yaml", exc_info=True)
            return

        if not isinstance(data, dict):
            logger.warning("entities.yaml root is not a mapping — skipping")
            return

        entities_list = data.get("entities")
        if not isinstance(entities_list, list):
            logger.debug("No 'entities' list in entities.yaml — nothing to overlay")
            return

        created = 0
        overlaid = 0
        for entry in entities_list:
            if not isinstance(entry, dict):
                continue
            eid = entry.get("id")
            if not eid:
                continue

            if eid in self._entities:
                # Overlay onto existing entity
                entity = self._entities[eid]
                if "group_id" in entry and entry["group_id"]:
                    entity.group_id = str(entry["group_id"])
                if "slot" in entry and entry["slot"]:
                    entity.slot = str(entry["slot"])
                if "name" in entry and entry["name"]:
                    entity.name = str(entry["name"])
                if "membership_state" in entry and entry["membership_state"]:
                    entity.membership_state = str(entry["membership_state"])
                # Overlay poll_host/poll_port if present and entity
                # doesn't already have them (config.env takes priority)
                if entry.get("poll_host") and not entity.poll_host:
                    entity.poll_host = str(entry["poll_host"])
                if entry.get("poll_port") and entity.poll_port is None:
                    try:
                        entity.poll_port = int(entry["poll_port"])
                    except (ValueError, TypeError):
                        pass
                overlaid += 1
            else:
                # Create new entity from YAML (dashboard-added entity)
                ip = entry.get("ip")
                entity_type = entry.get("entity_type")
                if not ip or not entity_type:
                    logger.debug(
                        "Skipping entities.yaml entry '%s': missing ip or entity_type",
                        eid,
                    )
                    continue
                # Parse poll_port safely
                _yaml_poll_port = None
                if entry.get("poll_port") is not None:
                    try:
                        _yaml_poll_port = int(entry["poll_port"])
                    except (ValueError, TypeError):
                        pass
                self._entities[eid] = Entity(
                    id=eid,
                    name=entry.get("name", eid),
                    entity_type=entity_type,
                    source="remote",
                    ip=ip,
                    port=entry.get("port"),
                    poll_host=entry.get("poll_host"),
                    poll_port=_yaml_poll_port,
                    network_context=entry.get("network_context"),
                    group_id=entry.get("group_id"),
                    slot=entry.get("slot"),
                    membership_state=entry.get("membership_state", "approved"),
                )
                created += 1

        logger.info(
            "Loaded entities.yaml: %d overlaid, %d created from %s",
            overlaid,
            created,
            path,
        )

    def _save_entities_yaml(self) -> None:
        """Persist group/slot/name for all remote entities to entities.yaml.

        Called after every mutation (add/edit/remove) to ensure group/slot/name
        data survives dashboard restarts. Only saves remote entities that have
        group_id set (entities without group assignment don't need overlay).
        """
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not installed — cannot save entities.yaml")
            return

        entries = []
        for entity in self._entities.values():
            if entity.source not in ("remote",) or not entity.group_id:
                continue
            entries.append(
                {
                    "id": entity.id,
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "ip": entity.ip,
                    "port": entity.port,
                    "poll_host": entity.poll_host,
                    "poll_port": entity.poll_port,
                    "network_context": entity.network_context,
                    "group_id": entity.group_id,
                    "slot": entity.slot,
                    "membership_state": entity.membership_state,
                }
            )

        data = {"entities": entries}

        try:
            path = self._entities_yaml_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.dump(data, default_flow_style=False, sort_keys=False)  # type: ignore[union-attr]
            )
            logger.debug("Saved entities.yaml with %d entries", len(entries))
        except Exception:
            logger.warning("Failed to save entities.yaml", exc_info=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_entities(self) -> list[Entity]:
        """Return all entities (configured + discovered)."""
        return list(self._entities.values())

    def get_entity(self, entity_id: str) -> Entity | None:
        """Return a single entity by ID, or None."""
        return self._entities.get(entity_id)

    def entity_to_api_dict(self, entity: Entity) -> dict:
        """Serialize entity for API response, including manager-level state."""
        d = entity.to_dict()
        d["polling_suspended"] = entity.id in self._suspended
        return d

    # ------------------------------------------------------------------
    # Add entity by IP (manual add)
    # ------------------------------------------------------------------

    def _next_arm_id(self) -> tuple[str, str]:
        """Return (entity_id, default_name) for the next arm."""
        existing_nums: list[int] = []
        for e in self._entities.values():
            if e.entity_type == "arm" and e.id.startswith("arm"):
                try:
                    existing_nums.append(int(e.id[3:]))
                except ValueError:
                    pass
        next_num = max(existing_nums, default=0) + 1
        return f"arm{next_num}", f"Arm {next_num} RPi"

    async def _verify_agent_reachable(self, ip: str) -> bool:
        """Check if the agent at ip:AGENT_PORT is reachable via GET /health."""
        url = f"http://{ip}:{AGENT_PORT}/health"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except _HTTPX_NETWORK_ERRORS:
            return False

    async def _poll_agent_health(self, entity: Entity) -> None:
        """Poll a single entity's fast /health endpoint."""
        if entity.source == "local":
            entity.update_health(agent="local", agent_warnings=[])
            self.notify_change()
            return

        url = f"{entity.agent_base_url(AGENT_PORT)}/health"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(HEALTH_TIMEOUT_S)) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                data = resp.json()
                for key in entity.system_metrics:
                    if key in data:
                        entity.system_metrics[key] = data[key]
                entity.last_seen = datetime.now(timezone.utc)
                entity.update_health(
                    agent="alive",
                    agent_warnings=list(data.get("warnings") or []),
                )
                if entity.health.get("network") == "unreachable":
                    entity.update_health(network="reachable")
                self._agent_failure_counts[entity.id] = 0
                self.notify_change()
                return

            self._record_agent_failure(entity)
        except _HTTPX_NETWORK_ERRORS:
            self._record_agent_failure(entity)
        except Exception:
            logger.debug("Unexpected error polling /health for %s", entity.id, exc_info=True)
            self._record_agent_failure(entity)

    def _record_agent_failure(self, entity: Entity) -> None:
        count = self._agent_failure_counts.get(entity.id, 0) + 1
        self._agent_failure_counts[entity.id] = count
        entity.update_health(
            agent=("down" if count >= HEALTH_FAILURE_THRESHOLD else "degraded"),
            agent_warnings=[],
        )
        self.notify_change()

    async def add_entity_by_ip(
        self,
        ip: str,
        entity_type: str,
        group_id: str,
        slot: str,
        name: str | None = None,
        network_context: str | None = None,
        port: int | None = None,
        config_env_path: Path | None = None,
    ) -> Entity:
        """Add a new entity by IP address.

        Validates IP, checks for duplicates, verifies agent reachability,
        creates the entity, persists to config.env, and broadcasts.

        Raises
        ------
        ValueError
            If IP is invalid, entity_type is invalid, or agent unreachable.
        DuplicateIPError
            If IP is already used by an existing entity.
        VehicleExistsError
            If entity_type is 'vehicle' and one already exists.
        """
        # Validate IP
        if not _is_valid_ip(ip):
            raise ValueError(f"Invalid IPv4 address: {ip}")

        # Validate entity_type
        if entity_type not in ("arm", "vehicle"):
            raise ValueError("entity_type must be 'arm' or 'vehicle'")

        if not group_id or not group_id.strip():
            raise ValueError("group_id is required")
        if not slot or not slot.strip():
            raise ValueError("slot is required")

        # Check duplicate IP
        for e in self._entities.values():
            if e.ip == ip:
                raise DuplicateIPError(
                    f"Entity with IP {ip} already exists",
                    existing_entity_id=e.id,
                )

        target_group = group_id.strip()
        target_slot = slot.strip()
        if not _is_valid_slot_for_type(entity_type, target_slot):
            raise ValueError(f"Invalid slot '{target_slot}' for entity_type '{entity_type}'")

        for e in self._entities.values():
            if (
                e.membership_state == "approved"
                and e.group_id == target_group
                and e.slot == target_slot
            ):
                raise SlotConflictError(
                    f"Slot {target_group}/{target_slot} is already occupied",
                    existing_entity_id=e.id,
                )

        # Skip reachability check: entities may be added before agent is
        # deployed (user provisions via sync/operations afterwards).  The
        # health poller will detect the agent once it comes online.

        # Generate ID and name
        if entity_type == "arm":
            entity_id, default_name = self._next_arm_id()
        else:
            entity_id = "vehicle"
            default_name = "Vehicle RPi"

        entity_name = name.strip() if name else default_name

        # Create entity
        entity = Entity(
            id=entity_id,
            name=entity_name,
            entity_type=entity_type,
            source="remote",
            ip=ip,
            port=port,
            network_context=(network_context.strip() if network_context else None),
            group_id=target_group,
            slot=target_slot,
            membership_state="approved",
        )
        self._entities[entity_id] = entity
        self._suspended.discard(entity_id)
        if self._ping_monitor is not None:
            self._ping_monitor.add_entity(entity)

        # Persist to config.env
        self._persist_entity_to_config_env(entity, config_env_path)

        # Persist group/slot/name to entities.yaml
        self._save_entities_yaml()

        # Broadcast WebSocket notification
        self.notify_entity_added(entity)

        logger.info("Added entity %s (%s) at %s", entity_id, entity_name, ip)
        return entity

    def _persist_entity_to_config_env(
        self,
        entity: Entity,
        config_env_path: Path | None = None,
    ) -> None:
        """Append entity IP to config.env (with dedup)."""
        env_path = config_env_path or _DEFAULT_CONFIG_ENV_PATH
        if not entity.ip or not env_path.exists():
            return

        try:
            existing_content = env_path.read_text()

            # Skip if IP already in config.env
            if f"={entity.ip}" in existing_content:
                logger.info("IP %s already in config.env — skipping", entity.ip)
                return

            # Determine config key
            if entity.entity_type == "vehicle":
                key = "VEHICLE_IP"
            else:
                # Use the entity id to derive key: arm3 -> ARM_3_IP
                num = entity.id[3:] if entity.id.startswith("arm") else "1"
                key = f"ARM_{num}_IP"

            # Skip if key already exists
            if f"{key}=" in existing_content:
                logger.info("Key %s already in config.env — skipping", key)
                return

            with open(env_path, "a") as f:
                f.write(f"\n{key}={entity.ip}\n")
            logger.info("Added %s=%s to config.env", key, entity.ip)
        except Exception:
            logger.warning("Failed to persist entity to config.env", exc_info=True)

    # ------------------------------------------------------------------
    # WebSocket subscription (Task 2.7)
    # ------------------------------------------------------------------

    def subscribe_changes(self) -> asyncio.Queue:
        """Subscribe to entity state change events.

        Returns an asyncio.Queue that receives dict payloads whenever
        entity state changes after a poll cycle.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def notify_change(self) -> None:
        """Notify all subscribers that entity state changed."""
        payload = {
            "type": "entity_state_changed",
            "entities": [e.to_dict() for e in self._entities.values()],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for queue in self._subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.debug("Subscriber queue full, skipping notification")

    def notify_entity_added(self, entity: Entity) -> None:
        """Notify all subscribers that a new entity was added."""
        payload = {
            "type": "entity_added",
            "entity": entity.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for queue in self._subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.debug("Subscriber queue full, skipping entity_added")

    def notify_entity_updated(self, entity: Entity) -> None:
        """Notify all subscribers that an entity was updated."""
        payload = {
            "type": "entity_updated",
            "entity": entity.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for queue in self._subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.debug("Subscriber queue full, skipping entity_updated")

    def notify_entity_removed(self, entity_id: str) -> None:
        """Notify all subscribers that an entity was removed."""
        payload = {
            "type": "entity_removed",
            "entity_id": entity_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for queue in self._subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.debug("Subscriber queue full, skipping entity_removed")

    # ------------------------------------------------------------------
    # Entity Update / Remove
    # ------------------------------------------------------------------

    async def update_entity(
        self,
        entity_id: str,
        ip: str | None = None,
        name: str | None = None,
        group_id: str | None = None,
        slot: str | None = None,
        network_context: str | None = None,
        port: int | None = None,
        config_env_path: Path | None = None,
    ) -> Entity:
        """Update an existing entity fields.

        If the IP is changed, verifies reachability of the new IP and updates config.env.
        Broadcasts an update event.
        """
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(f"Entity '{entity_id}' not found")

        if entity_id == "local":
            raise ValueError("Cannot edit local entity")

        if entity.source != "remote":
            raise ValueError("Can only edit remotely configured entities")

        old_ip = entity.ip
        ip_changed = ip is not None and ip != old_ip
        group_changed = group_id is not None and group_id.strip() != (entity.group_id or "")
        slot_changed = slot is not None and slot.strip() != (entity.slot or "")
        target_group = group_id.strip() if group_id is not None else entity.group_id
        target_slot = slot.strip() if slot is not None else entity.slot

        if ip_changed:
            if not _is_valid_ip(ip):  # type: ignore
                raise ValueError(f"Invalid IPv4 address: {ip}")

            # Check duplicate IP
            for e in self._entities.values():
                if e.id != entity_id and e.ip == ip:
                    raise DuplicateIPError(
                        f"Entity with IP {ip} already exists",
                        existing_entity_id=e.id,
                    )

            # Skip reachability check: agent may not be deployed at new IP yet.

        if (group_changed and not target_group) or (slot_changed and not target_slot):
            raise ValueError("group_id and slot must both be provided when reassigning")

        if (group_changed or slot_changed) and target_slot is not None:
            if not _is_valid_slot_for_type(entity.entity_type, target_slot):
                raise ValueError(
                    f"Invalid slot '{target_slot}' for entity_type '{entity.entity_type}'"
                )

        if group_changed or slot_changed:
            for e in self._entities.values():
                if (
                    e.id != entity_id
                    and e.membership_state == "approved"
                    and e.group_id == target_group
                    and e.slot == target_slot
                ):
                    raise SlotConflictError(
                        f"Slot {target_group}/{target_slot} is already occupied",
                        existing_entity_id=e.id,
                    )

        # Update fields
        if name is not None and name.strip():
            entity.name = name.strip()
        if ip_changed and ip is not None:
            entity.ip = ip
            self._suspended.discard(entity_id)
            self._failure_counts[entity_id] = 0
            self._poll_intervals[entity_id] = self._status_poll_interval_s
            if self._ping_monitor is not None:
                self._ping_monitor.update_entity(entity)
        if group_changed:
            entity.group_id = target_group
        if slot_changed:
            entity.slot = target_slot
        if network_context is not None:
            entity.network_context = network_context.strip() if network_context.strip() else None
        if port is not None:
            entity.port = port

        # Persist to config.env if IP changed
        if ip_changed and ip is not None:
            self._update_ip_in_config_env(
                entity_id, entity.entity_type, old_ip, str(ip), config_env_path
            )

        # Persist group/slot/name to entities.yaml
        self._save_entities_yaml()

        self.notify_entity_updated(entity)
        logger.info(
            "Updated entity %s (name=%s, ip=%s, group=%s, slot=%s)",
            entity_id,
            entity.name,
            entity.ip,
            entity.group_id,
            entity.slot,
        )
        return entity

    async def remove_entity(self, entity_id: str, config_env_path: Path | None = None) -> None:
        """Remove a remote entity from the fleet and from config.env."""
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(f"Entity '{entity_id}' not found")

        if entity_id == "local":
            raise ValueError("Cannot remove local entity")

        if entity.source != "remote":
            raise ValueError("Can only remove remotely configured entities")

        if self._ping_monitor is not None:
            await self._ping_monitor.remove_entity(entity_id)

        # Remove from state
        del self._entities[entity_id]

        # Remove from config.env
        self._remove_from_config_env(entity_id, entity.entity_type, config_env_path)

        # Update entities.yaml (removed entity no longer in list)
        self._save_entities_yaml()

        # Broadcast removal
        self.notify_entity_removed(entity_id)
        logger.info("Removed entity %s", entity_id)

    def _update_ip_in_config_env(
        self,
        entity_id: str,
        entity_type: str,
        old_ip: str | None,
        new_ip: str,
        config_env_path: Path | None = None,
    ) -> None:
        env_path = config_env_path or _DEFAULT_CONFIG_ENV_PATH
        if not env_path.exists():
            return

        key_to_match = (
            "VEHICLE_IP"
            if entity_type == "vehicle"
            else f"ARM_{entity_id[3:] if entity_id.startswith('arm') else '1'}_IP"
        )
        alt_key_to_match = (
            "VEHICLE_IP"
            if entity_type == "vehicle"
            else f"ARM{entity_id[3:] if entity_id.startswith('arm') else '1'}_IP"
        )

        try:
            lines = env_path.read_text().splitlines()
            new_lines = []
            replaced = False
            for line in lines:
                if "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip()
                    if k in (key_to_match, alt_key_to_match):
                        new_lines.append(f"{k}={new_ip}")
                        replaced = True
                        continue
                new_lines.append(line)

            if not replaced:
                # If for some reason the key wasn't found, append it
                new_lines.append(f"{key_to_match}={new_ip}")

            env_path.write_text("\n".join(new_lines) + "\n")
            logger.info("Updated %s to %s in config.env", key_to_match, new_ip)
        except Exception:
            logger.warning("Failed to update config.env", exc_info=True)

    def _remove_from_config_env(
        self, entity_id: str, entity_type: str, config_env_path: Path | None = None
    ) -> None:
        env_path = config_env_path or _DEFAULT_CONFIG_ENV_PATH
        if not env_path.exists():
            return

        key_to_match = (
            "VEHICLE_IP"
            if entity_type == "vehicle"
            else f"ARM_{entity_id[3:] if entity_id.startswith('arm') else '1'}_IP"
        )
        alt_key_to_match = (
            "VEHICLE_IP"
            if entity_type == "vehicle"
            else f"ARM{entity_id[3:] if entity_id.startswith('arm') else '1'}_IP"
        )

        try:
            lines = env_path.read_text().splitlines()
            new_lines = []
            for line in lines:
                if "=" in line:
                    k, _, _ = line.partition("=")
                    if k.strip() in (key_to_match, alt_key_to_match):
                        continue
                new_lines.append(line)

            env_path.write_text("\n".join(new_lines) + "\n")
            logger.info("Removed %s from config.env", key_to_match)
        except Exception:
            logger.warning("Failed to remove from config.env", exc_info=True)

    # ------------------------------------------------------------------
    # Lifecycle (Task 2.4)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the polling loop and optional mDNS discovery."""
        self._running = True
        self._loop = asyncio.get_running_loop()
        ping_cfg = self._read_ping_config(self._dashboard_yaml_path)
        self._ping_monitor = PingMonitor(
            interval_s=ping_cfg["ping_interval_s"],
            timeout_s=ping_cfg["ping_timeout_s"],
            failure_threshold=ping_cfg["ping_failure_threshold"],
            on_state_change=self._handle_ping_state_change,
        )
        self._ping_monitor.start(self._entities.values())
        self._health_poll_task = asyncio.create_task(self._health_poll_loop())
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._start_mdns()
        logger.info("EntityManager started (%d entities)", len(self._entities))

    async def stop(self) -> None:
        """Stop polling and mDNS discovery."""
        self._running = False

        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._health_poll_task is not None:
            self._health_poll_task.cancel()
            try:
                await self._health_poll_task
            except asyncio.CancelledError:
                pass
            self._health_poll_task = None

        if self._ping_monitor is not None:
            await self._ping_monitor.stop()
            self._ping_monitor = None

        self._stop_mdns()
        self._loop = None
        logger.info("EntityManager stopped")

    @staticmethod
    def _read_ping_config(yaml_path: Path) -> dict[str, float | int]:
        """Read ping monitor configuration from dashboard.yaml."""
        defaults: dict[str, float | int] = {
            "ping_interval_s": PING_INTERVAL_S,
            "ping_timeout_s": PING_TIMEOUT_S,
            "ping_failure_threshold": PING_FAILURE_THRESHOLD,
        }
        if not YAML_AVAILABLE or not yaml_path.exists():
            return defaults
        try:
            with open(yaml_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            logger.debug("Failed to read ping config from dashboard.yaml", exc_info=True)
            return defaults
        ping_cfg = (config.get("health") or {}).get("ping") or {}
        return {
            "ping_interval_s": float(ping_cfg.get("ping_interval_s", PING_INTERVAL_S)),
            "ping_timeout_s": float(ping_cfg.get("ping_timeout_s", PING_TIMEOUT_S)),
            "ping_failure_threshold": int(
                ping_cfg.get("ping_failure_threshold", PING_FAILURE_THRESHOLD)
            ),
        }

    async def _handle_ping_state_change(
        self, entity: Entity, previous_state: str, current_state: str
    ) -> None:
        """React to ping state changes and fast-track recovery."""
        if current_state == "reachable" and previous_state in {"degraded", "unreachable"}:
            self._failure_counts[entity.id] = 0
            self._poll_intervals[entity.id] = self._status_poll_interval_s
            self._last_polled.pop(entity.id, None)
            if entity.id in self._suspended:
                self.resume_polling(entity.id)
                return
        self.notify_change()

    def _handle_mqtt_change(self, arm_id: str, arm_data: dict[str, Any]) -> None:
        """Apply MQTT arm-state updates to matching entities."""
        entity = self._entities.get(arm_id)
        if entity is None:
            return

        connectivity = arm_data.get("connectivity")
        state = arm_data.get("state")
        last_seen = arm_data.get("last_heartbeat")

        mqtt_state = "unknown"
        if connectivity == "connected":
            mqtt_state = "active"
        elif connectivity == "broker_down":
            mqtt_state = "broker_down"
        elif connectivity == "stale":
            mqtt_state = "stale"
        elif connectivity == "offline":
            mqtt_state = "offline"

        entity.update_health(
            mqtt=mqtt_state,
            mqtt_arm_state=state,
            mqtt_last_seen=last_seen,
        )
        self.notify_change()

    # ------------------------------------------------------------------
    # Polling loop (Task 2.4)
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Poll all remote entities at regular intervals."""
        while self._running:
            try:
                await self._poll_all()
            except Exception:
                logger.debug("Poll cycle failed", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL_S)

    async def _health_poll_loop(self) -> None:
        """Poll all entity /health endpoints independently of /status."""
        while self._running:
            try:
                tasks = [self._poll_agent_health(entity) for entity in self._entities.values()]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                logger.debug("Health poll cycle failed", exc_info=True)
            await asyncio.sleep(HEALTH_INTERVAL_S)

    async def _poll_all(self) -> None:
        """Poll all entities concurrently, respecting per-entity backoff."""
        import time

        now = time.monotonic()
        tasks = []
        for entity in self._entities.values():
            if entity.source == "local":
                tasks.append(self._poll_local(entity))
            elif entity.ip:
                if entity.id in self._suspended:
                    continue
                interval = self._poll_intervals.get(entity.id, self._status_poll_interval_s)
                last = self._last_polled.get(entity.id, 0.0)
                if now - last >= interval:
                    self._last_polled[entity.id] = now
                    tasks.append(self._poll_entity(entity))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_entity(self, entity: Entity) -> None:
        """Poll a single remote entity's status endpoint."""
        url = f"{entity.agent_base_url(AGENT_PORT)}/status"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(POLL_TIMEOUT_S)) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                data = resp.json()
                entity.status = "online"
                entity.last_seen = datetime.now(timezone.utc)

                mqtt_svc = get_mqtt_status_service()
                if mqtt_svc is None:
                    entity.update_health(mqtt="disabled")
                elif not mqtt_svc.is_connected() and entity.health.get("mqtt") == "unknown":
                    entity.update_health(mqtt="broker_down")

                # Update system metrics from nested "health" key
                health = data.get("health", {})
                for key in entity.system_metrics:
                    if key in health:
                        entity.system_metrics[key] = health[key]

                # Update ROS2 state from nested "ros2" key
                ros2 = data.get("ros2", {})
                if ros2:
                    entity.ros2_available = ros2.get("available", False)
                    entity.ros2_state = {k: v for k, v in ros2.items() if k != "available"}
                    entity.update_health(
                        ros2=("healthy" if entity.ros2_available else "down"),
                        ros2_node_count=entity.ros2_state.get("node_count"),
                    )

                # Update systemd services from "systemd" key
                systemd = data.get("systemd", [])
                if isinstance(systemd, list):
                    entity.services = systemd

                # Reset failure count and backoff on success
                self._failure_counts[entity.id] = 0
                self._poll_intervals[entity.id] = self._status_poll_interval_s
                entity.errors.clear()
                self.notify_change()
                return

            # Non-200 status code
            self._record_failure(entity)

        except _HTTPX_NETWORK_ERRORS:
            self._record_failure(entity)
        except Exception:
            logger.debug("Unexpected error polling %s", entity.id, exc_info=True)
            self._record_failure(entity)

    async def _poll_local(self, entity: Entity) -> None:
        """Poll local machine metrics via psutil."""
        if not PSUTIL_AVAILABLE:
            return

        try:
            entity.system_metrics["cpu_percent"] = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            entity.system_metrics["memory_percent"] = mem.percent
            disk = psutil.disk_usage("/")
            entity.system_metrics["disk_percent"] = disk.percent

            # Temperature (may not be available on all platforms)
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    first_sensor = list(temps.values())[0]
                    if first_sensor:
                        entity.system_metrics["temperature_c"] = first_sensor[0].current
            except (AttributeError, IndexError):
                pass

            # Uptime
            import time

            entity.system_metrics["uptime_seconds"] = int(time.time() - psutil.boot_time())

            entity.status = "online"
            entity.last_seen = datetime.now(timezone.utc)

            # Also poll local agent for ROS2 status (agent runs on same host)
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(POLL_TIMEOUT_S)) as client:
                    resp = await client.get(f"http://127.0.0.1:{AGENT_PORT}/status")
                if resp.status_code == 200:
                    data = resp.json()
                    ros2 = data.get("ros2", {})
                    if ros2:
                        entity.ros2_available = ros2.get("available", False)
                        entity.ros2_state = {k: v for k, v in ros2.items() if k != "available"}
                    systemd = data.get("systemd", [])
                    if isinstance(systemd, list):
                        entity.services = systemd
            except Exception:
                logger.debug("Local agent poll failed", exc_info=True)

            self.notify_change()
        except Exception:
            logger.debug("Local poll failed", exc_info=True)

    # ------------------------------------------------------------------
    # Offline detection (Task 2.5)
    # ------------------------------------------------------------------

    def _record_failure(self, entity: Entity) -> None:
        """Record a poll failure and mark offline after threshold."""
        count = self._failure_counts.get(entity.id, 0) + 1
        self._failure_counts[entity.id] = count

        if count >= SUSPEND_THRESHOLD:
            entity.status = "offline"
            entity.add_error(f"Polling suspended after {count} consecutive failures")
            self._suspended.add(entity.id)
            logger.info("Suspended polling for %s after %d failures", entity.id, count)
        elif count >= OFFLINE_THRESHOLD:
            entity.status = "offline"
            entity.add_error(f"Offline after {count} consecutive poll failures")
            # Apply backoff for offline entities
            self._poll_intervals[entity.id] = min(
                POLL_INTERVAL_S * BACKOFF_MULTIPLIER, MAX_POLL_INTERVAL_S
            )
        else:
            # Degraded but not yet offline
            if entity.status != "offline":
                entity.status = "degraded"

        self.notify_change()

    def resume_polling(self, entity_id: str) -> bool:
        """Resume polling for a suspended entity. Returns True if entity was suspended."""
        if entity_id not in self._entities:
            raise KeyError(f"Entity {entity_id} not found")

        was_suspended = entity_id in self._suspended
        self._suspended.discard(entity_id)
        self._failure_counts[entity_id] = 0
        self._poll_intervals[entity_id] = self._status_poll_interval_s
        self._last_polled.pop(entity_id, None)  # Force immediate poll on next cycle

        entity = self._entities[entity_id]
        # Clear suspension-related errors
        entity.errors = [e for e in entity.errors if "suspended" not in e.lower()]
        if was_suspended:
            entity.status = "unknown"
            logger.info("Resumed polling for %s", entity_id)
            self.notify_change()

        return was_suspended

    # ------------------------------------------------------------------
    # mDNS discovery (Task 2.3)
    # ------------------------------------------------------------------

    def _start_mdns(self) -> None:
        """Start mDNS service browser for Pragati agents."""
        if not ZEROCONF_AVAILABLE:
            logger.info("zeroconf not available, mDNS discovery disabled")
            return

        try:
            self._zeroconf = Zeroconf()
            self._browser = ServiceBrowser(
                self._zeroconf,
                MDNS_SERVICE_TYPE,
                handlers=[self._on_mdns_state_change],
            )
            logger.info("mDNS discovery started for %s", MDNS_SERVICE_TYPE)
        except Exception:
            logger.warning("mDNS discovery failed to start", exc_info=True)
            self._zeroconf = None
            self._browser = None

    def _stop_mdns(self) -> None:
        """Stop mDNS discovery."""
        if self._zeroconf is not None:
            try:
                self._zeroconf.close()
            except Exception:
                logger.debug("Error closing zeroconf", exc_info=True)
            self._zeroconf = None
            self._browser = None

    def _on_mdns_state_change(
        self,
        zeroconf: Any,
        service_type: str,
        name: str,
        state_change: Any,
    ) -> None:
        """Handle mDNS service state changes (thread-safe)."""
        loop = self._loop
        if loop is None:
            logger.debug("mDNS event ignored before EntityManager loop initialized")
            return

        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info and info.addresses:
                import socket

                ip = socket.inet_ntoa(info.addresses[0])
                loop.call_soon_threadsafe(self._handle_mdns_discovered, ip, name)
        elif state_change == ServiceStateChange.Removed:
            loop.call_soon_threadsafe(self._handle_mdns_removed, name)

    def _handle_mdns_discovered(self, ip: str, service_name: str) -> None:
        """Handle a newly discovered mDNS entity."""
        # Skip self-discovery: if the IP belongs to this machine, ignore it
        if ip in self._local_ips:
            logger.debug("mDNS ignoring self-discovery at %s (local IP)", ip)
            return

        # Check if IP already configured
        for entity in self._entities.values():
            if entity.ip == ip:
                logger.info(
                    "mDNS confirmed known entity %s at %s",
                    entity.id,
                    ip,
                )
                return

        # New discovered entity
        entity_id = f"discovered_{ip.replace('.', '_')}"
        logger.info("mDNS discovered new entity at %s", ip)
        self._entities[entity_id] = Entity(
            id=entity_id,
            name=f"Discovered ({ip})",
            entity_type="arm",  # default, user can change
            source="discovered",
            ip=ip,
            metadata={"mdns_name": service_name},
        )
        self.notify_change()

    def _handle_mdns_removed(self, service_name: str) -> None:
        """Handle mDNS entity departure (with grace period)."""
        import time

        now = time.time()
        # Find entity by mDNS name
        for eid, entity in list(self._entities.items()):
            if entity.metadata.get("mdns_name") == service_name:
                if entity.source == "discovered":
                    self._mdns_departure_timers[eid] = now
                    logger.info(
                        "mDNS departure for %s, grace period %ds",
                        eid,
                        MDNS_REMOVAL_GRACE_S,
                    )
                break

    # ------------------------------------------------------------------
    # Add discovered entity (Task 2.11)
    # ------------------------------------------------------------------

    def add_discovered_entity(
        self,
        entity_id: str,
        entity_type: str,
        group_id: str,
        slot: str,
        config_env_path: Path | None = None,
    ) -> Entity:
        """Transition a discovered entity to configured.

        Appends the entity IP to config.env and changes source to 'remote'.
        """
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(f"Entity '{entity_id}' not found")
        if entity.source != "discovered":
            raise ValueError(f"Entity '{entity_id}' is not discovered (source={entity.source})")

        if not group_id or not group_id.strip():
            raise ValueError("group_id is required")
        if not slot or not slot.strip():
            raise ValueError("slot is required")

        target_group = group_id.strip()
        target_slot = slot.strip()
        if not _is_valid_slot_for_type(entity_type, target_slot):
            raise ValueError(f"Invalid slot '{target_slot}' for entity_type '{entity_type}'")
        for e in self._entities.values():
            if (
                e.id != entity_id
                and e.membership_state == "approved"
                and e.group_id == target_group
                and e.slot == target_slot
            ):
                raise SlotConflictError(
                    f"Slot {target_group}/{target_slot} is already occupied",
                    existing_entity_id=e.id,
                )

        entity.source = "remote"
        entity.entity_type = entity_type
        entity.group_id = target_group
        entity.slot = target_slot
        entity.membership_state = "approved"

        # Append to config.env (with dedup — skip if IP already present)
        env_path = config_env_path or _DEFAULT_CONFIG_ENV_PATH
        if entity.ip and env_path.exists():
            try:
                existing_content = env_path.read_text()

                # Skip if this IP is already in config.env (any key)
                if f"={entity.ip}" in existing_content:
                    logger.info(
                        "IP %s already in config.env — skipping append",
                        entity.ip,
                    )
                else:
                    # Determine the config key based on type
                    if entity_type == "vehicle":
                        key = "VEHICLE_IP"
                    else:
                        # Find next arm number
                        existing_arms = [
                            e
                            for e in self._entities.values()
                            if e.entity_type == "arm" and e.source == "remote" and e.id != entity_id
                        ]
                        next_num = len(existing_arms) + 1
                        key = f"ARM_{next_num}_IP"
                        entity.id = f"arm{next_num}"
                        entity.name = f"Arm {next_num} RPi"

                    # Also skip if this exact key already exists
                    if f"{key}=" in existing_content:
                        logger.info(
                            "Key %s already in config.env — skipping append",
                            key,
                        )
                    else:
                        with open(env_path, "a") as f:
                            f.write(f"\n{key}={entity.ip}\n")
                        logger.info("Added %s=%s to config.env", key, entity.ip)
            except Exception:
                logger.warning("Failed to append to config.env", exc_info=True)

        # Persist group/slot/name to entities.yaml
        self._save_entities_yaml()

        return entity


# ---------------------------------------------------------------------------
# FastAPI Router (Task 2.6)
# ---------------------------------------------------------------------------

entity_router = APIRouter(prefix="/api/entities", tags=["entities"])


class AddDiscoveredRequest(BaseModel):
    """Request body for adding a discovered entity."""

    entity_type: str  # "arm" | "vehicle"
    group_id: str
    slot: str


class AddEntityByIPRequest(BaseModel):
    """Request body for adding an entity by IP address."""

    ip: str
    entity_type: str  # "arm" | "vehicle"
    group_id: str
    slot: str
    name: str | None = None
    network_context: str | None = None
    port: int | None = None


class UpdateEntityRequest(BaseModel):
    """Request body for updating an entity."""

    ip: str | None = None
    name: str | None = None
    group_id: str | None = None
    slot: str | None = None
    network_context: str | None = None
    port: int | None = None


class ScanSubnetRequest(BaseModel):
    """Request body for scanning a subnet for pragati agents."""

    subnet: str  # e.g. "192.168.137" (/24) or "192.168" (/16)
    timeout: float = 2.0  # per-host connect timeout in seconds
    concurrency: int = 100  # max concurrent probes


def _get_mgr() -> EntityManager:
    """Get the entity manager, raising 503 if not initialized."""
    mgr = get_entity_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EntityManager not initialized")
    return mgr


@entity_router.post("", status_code=201)
async def add_entity_by_ip_endpoint(body: AddEntityByIPRequest) -> dict:
    """POST /api/entities - add an entity by IP address."""
    mgr = _get_mgr()
    try:
        entity = await mgr.add_entity_by_ip(
            ip=body.ip,
            entity_type=body.entity_type,
            group_id=body.group_id,
            slot=body.slot,
            name=body.name,
            network_context=body.network_context,
            port=body.port,
        )
        return mgr.entity_to_api_dict(entity)
    except DuplicateIPError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": str(exc),
                "existing_entity_id": exc.existing_entity_id,
            },
        )
    except VehicleExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": str(exc),
                "existing_entity_id": exc.existing_entity_id,
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": str(exc)},
        )
    except SlotConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": str(exc),
                "existing_entity_id": exc.existing_entity_id,
            },
        )


@entity_router.get("")
def list_entities() -> list[dict]:
    """GET /api/entities - list all entities."""
    mgr = _get_mgr()
    return [mgr.entity_to_api_dict(e) for e in mgr.get_all_entities()]


@entity_router.post("/scan")
async def scan_subnet_endpoint(body: ScanSubnetRequest) -> dict:
    """POST /api/entities/scan - scan a subnet for pragati agents.

    Probes each IP in the subnet on AGENT_PORT (8091) via GET /health.
    Returns a list of reachable agents with their health info.
    Already-configured IPs are included but flagged as ``already_configured``.

    Subnet formats:
    - "192.168.137" -> scans 192.168.137.1 to 192.168.137.254 (253 hosts)
    - "192.168"     -> scans 192.168.0.1 to 192.168.255.254 (65,024 hosts)

    Must be registered BEFORE ``/{entity_id}`` routes so FastAPI matches the
    fixed ``/scan`` path instead of treating "scan" as an entity ID.
    """
    mgr = _get_mgr()

    # Validate subnet prefix
    parts = body.subnet.strip().split(".")
    if len(parts) not in (2, 3):
        raise HTTPException(
            status_code=400,
            detail="Subnet must be 2 or 3 octets (e.g. '192.168' or '192.168.137')",
        )
    for p in parts:
        try:
            val = int(p)
            if not (0 <= val <= 255):
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid octet in subnet: '{p}'",
            )

    # Clamp concurrency to reasonable range
    concurrency = max(10, min(body.concurrency, 500))
    timeout = max(0.5, min(body.timeout, 10.0))

    # Build list of IPs to scan
    ips_to_scan: list[str] = []
    if len(parts) == 3:
        # /24 scan: x.y.z.1 to x.y.z.254
        prefix = body.subnet.strip()
        for host in range(1, 255):
            ips_to_scan.append(f"{prefix}.{host}")
    else:
        # /16 scan: x.y.0.1 to x.y.255.254
        prefix = body.subnet.strip()
        for third in range(0, 256):
            for host in range(1, 255):
                ips_to_scan.append(f"{prefix}.{third}.{host}")

    # Get already-configured IPs
    configured_ips: set[str] = set()
    configured_ip_to_id: dict[str, str] = {}
    for entity in mgr.get_all_entities():
        if entity.ip:
            configured_ips.add(entity.ip)
            configured_ip_to_id[entity.ip] = entity.id

    results: list[dict] = []
    sem = asyncio.Semaphore(concurrency)

    async def probe(ip: str) -> dict | None:
        """Probe a single IP with two-tier detection.

        Tier 1: GET /health on AGENT_PORT (8091) — full agent info.
        Tier 2: TCP connect to SSH port (22) — host alive, no agent.
        Returns info dict or None if completely unreachable.
        """
        async with sem:
            # Tier 1: Try pragati-agent health endpoint
            url = f"http://{ip}:{AGENT_PORT}/health"
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except Exception:
                            data = {}
                        return {
                            "ip": ip,
                            "port": AGENT_PORT,
                            "hostname": data.get("hostname", ""),
                            "entity_type": data.get("entity_type", ""),
                            "status": "agent_found",
                            "health": data,
                            "already_configured": ip in configured_ips,
                            "configured_entity_id": configured_ip_to_id.get(ip),
                        }
            except _HTTPX_NETWORK_ERRORS:
                pass

            # Tier 2: TCP connect to SSH port — host alive but no agent
            try:
                _reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, 22),
                    timeout=timeout,
                )
                writer.close()
                await writer.wait_closed()
                return {
                    "ip": ip,
                    "port": None,
                    "hostname": "",
                    "entity_type": "",
                    "status": "host_found",
                    "health": {},
                    "already_configured": ip in configured_ips,
                    "configured_entity_id": configured_ip_to_id.get(ip),
                }
            except (OSError, asyncio.TimeoutError):
                pass

            return None

    # Run all probes concurrently (bounded by semaphore)
    tasks = [asyncio.ensure_future(probe(ip)) for ip in ips_to_scan]
    probe_results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in probe_results:
        if isinstance(r, dict):
            results.append(r)

    # ------------------------------------------------------------------
    # Deduplicate by hostname: merge dual-interface devices (e.g. LAN +
    # WiFi on the same subnet) into a single result with an ``ips`` list.
    #
    # Merge rules — ALL must be satisfied:
    #   1. Exactly 2 IPs share the hostname (3+ almost certainly means
    #      multiple RPis with a factory-default hostname like "ubuntu").
    #   2. Both IPs are in the same /24 subnet (dual NICs on one device
    #      are typically on the same LAN; cross-subnet merging is wrong).
    #   3. Both IPs report the same entity_type (arm+vehicle can never
    #      be the same physical device).
    #
    # Any group that fails these rules is split back into individual rows.
    # ------------------------------------------------------------------
    raw_count = len(results)
    deduped: list[dict] = []
    hostname_groups: dict[str, list[dict]] = {}
    for r in results:
        hn = r.get("hostname") or ""
        if hn:
            hostname_groups.setdefault(hn, []).append(r)
        else:
            r["ips"] = [r["ip"]]
            deduped.append(r)

    for _hn, group in hostname_groups.items():
        # Rule 1: must be exactly 2 IPs
        if len(group) != 2:
            for r in group:
                r["ips"] = [r["ip"]]
                deduped.append(r)
            continue

        a, b = group
        # Rule 2: both IPs must share the same /24 prefix
        a_prefix = ".".join(a["ip"].split(".")[:3])
        b_prefix = ".".join(b["ip"].split(".")[:3])
        if a_prefix != b_prefix:
            for r in group:
                r["ips"] = [r["ip"]]
                deduped.append(r)
            continue

        # Rule 3: both must report the same entity_type
        a_et = a.get("entity_type") or ""
        b_et = b.get("entity_type") or ""
        if a_et != b_et:
            for r in group:
                r["ips"] = [r["ip"]]
                deduped.append(r)
            continue

        # All rules passed — merge into one row with an ips dropdown
        merged = dict(a)
        merged["ips"] = [a["ip"], b["ip"]]
        merged["already_configured"] = a["already_configured"] or b["already_configured"]
        merged["configured_entity_id"] = a.get("configured_entity_id") or b.get(
            "configured_entity_id"
        )
        deduped.append(merged)

    results = deduped

    agents = [r for r in results if r.get("status") == "agent_found"]
    hosts_only = [r for r in results if r.get("status") == "host_found"]
    logger.info(
        "Subnet scan '%s': %d hosts probed, %d agents + %d hosts found (%d unique after dedup)",
        body.subnet,
        len(ips_to_scan),
        len(agents),
        len(hosts_only),
        len(results),
    )

    return {
        "subnet": body.subnet,
        "hosts_scanned": len(ips_to_scan),
        "agents_found": len(agents),
        "hosts_found": len(hosts_only),
        "results": results,
    }


@entity_router.post("/resume-polling")
async def resume_polling_group_endpoint(group_id: str | None = None) -> dict:
    """Resume polling for all suspended entities, optionally filtered by group.

    Query params:
        group_id: If provided, only resume entities in this group.
    """
    mgr = _get_mgr()
    resumed = []
    for entity_id in list(mgr._suspended):
        entity = mgr._entities.get(entity_id)
        if entity and (group_id is None or entity.group_id == group_id):
            mgr.resume_polling(entity_id)
            resumed.append(entity_id)

    return {"resumed": resumed, "count": len(resumed)}


@entity_router.post("/{entity_id}/resume-polling")
async def resume_polling_endpoint(entity_id: str) -> dict:
    """Resume polling for a suspended entity."""
    mgr = _get_mgr()
    try:
        was_suspended = mgr.resume_polling(entity_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return {"entity_id": entity_id, "was_suspended": was_suspended, "status": "resumed"}


@entity_router.get("/{entity_id}")
def get_entity_endpoint(entity_id: str) -> dict:
    """GET /api/entities/{id} - get a single entity."""
    mgr = _get_mgr()
    entity = mgr.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return mgr.entity_to_api_dict(entity)


@entity_router.put("/{entity_id}")
async def update_entity_endpoint(entity_id: str, body: UpdateEntityRequest) -> dict:
    """PUT /api/entities/{id} - update an entity's name/IP."""
    mgr = _get_mgr()
    try:
        update_kwargs: dict[str, Any] = {}
        if body.ip is not None:
            update_kwargs["ip"] = body.ip
        if body.name is not None:
            update_kwargs["name"] = body.name
        if body.group_id is not None:
            update_kwargs["group_id"] = body.group_id
        if body.slot is not None:
            update_kwargs["slot"] = body.slot
        if body.network_context is not None:
            update_kwargs["network_context"] = body.network_context
        if body.port is not None:
            update_kwargs["port"] = body.port

        entity = await mgr.update_entity(entity_id, **update_kwargs)
        return mgr.entity_to_api_dict(entity)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    except DuplicateIPError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": str(exc), "existing_entity_id": exc.existing_entity_id},
        )
    except SlotConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": str(exc), "existing_entity_id": exc.existing_entity_id},
        )


@entity_router.delete("/{entity_id}")
async def delete_entity_endpoint(entity_id: str) -> dict:
    """DELETE /api/entities/{id} - remove an entity from config."""
    mgr = _get_mgr()
    try:
        await mgr.remove_entity(entity_id)
        return {"status": "success"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@entity_router.post("/discovered/{entity_id}/add")
def add_discovered_entity_endpoint(entity_id: str, body: AddDiscoveredRequest) -> dict:
    """POST /api/entities/discovered/{id}/add - configure a discovered entity."""
    mgr = _get_mgr()
    entity = mgr.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    if entity.source != "discovered":
        raise HTTPException(
            status_code=400,
            detail=f"Entity '{entity_id}' is not a discovered entity",
        )

    try:
        result = mgr.add_discovered_entity(
            entity_id,
            body.entity_type,
            body.group_id,
            body.slot,
        )
        return mgr.entity_to_api_dict(result)
    except SlotConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": str(exc), "existing_entity_id": exc.existing_entity_id},
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Module-level singleton (Task 2.8)
# ---------------------------------------------------------------------------

_entity_manager: Optional[EntityManager] = None


def get_entity_manager() -> Optional[EntityManager]:
    """Return the global EntityManager instance (or None if not started)."""
    return _entity_manager


async def init_entity_manager(
    config_env_path: Path | None = None,
    dashboard_yaml_path: Path | None = None,
) -> EntityManager:
    """Initialize and start the global EntityManager.

    Called from service_registry.init_services().
    """
    global _entity_manager
    _entity_manager = EntityManager(
        config_env_path=config_env_path,
        dashboard_yaml_path=dashboard_yaml_path,
    )
    await _entity_manager.start()
    logger.info(
        "EntityManager initialized (%d entities)",
        len(_entity_manager.get_all_entities()),
    )
    return _entity_manager


async def shutdown_entity_manager() -> None:
    """Stop and release the global EntityManager."""
    global _entity_manager
    if _entity_manager is not None:
        await _entity_manager.stop()
        _entity_manager = None
        logger.info("EntityManager shut down")
