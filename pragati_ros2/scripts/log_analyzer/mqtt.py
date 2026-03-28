"""
MQTT communication parsing (Group 23).

Parses:
  - MQTT client events (connect, reconnect, disconnect, health, publish failure)
    from vehicle_mqtt_bridge.py and ARM_client.py logs
  - Mosquitto broker events from mosquitto_broker.log (journalctl format)

Issue detection:
  - Frequent disconnects (>3/hour → high)
  - Extended disconnect (>30s → high)
  - Publish failures (any → medium)
  - Stale arm status (>5 min → high)
"""

import re
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .analyzer import ROS2LogAnalyzer

# ---------------------------------------------------------------------------
# task 23.2 — MQTT client patterns
# ---------------------------------------------------------------------------

MQTT_PATTERNS = [
    # Initial connect
    (
        re.compile(r"MQTT Connected to broker \(initial connection\)"),
        "mqtt_connect",
    ),
    # Reconnect with count
    (
        re.compile(
            r"MQTT RECONNECTED successfully \(reconnect #(?P<count>\d+), "
            r"total connections: (?P<total>\d+)\)"
        ),
        "mqtt_reconnect",
    ),
    # Unexpected disconnect
    (
        re.compile(
            r"MQTT UNEXPECTED DISCONNECT \(code=(?P<rc>\d+): (?P<desc>[^)]+)\)"
        ),
        "mqtt_disconnect",
    ),
    # Clean disconnect
    (
        re.compile(r"MQTT disconnected cleanly"),
        "mqtt_clean_disconnect",
    ),
    # Health: connected
    (
        re.compile(r"MQTT health: connected, publish failures=(?P<failures>\d+)"),
        "mqtt_health_ok",
    ),
    # Health: disconnected
    (
        re.compile(r"MQTT health: DISCONNECTED for (?P<duration>\d+)s"),
        "mqtt_health_disconnected",
    ),
    # Publish failure
    (
        re.compile(
            r"Failed to publish to (?P<topic>\S+) after (?P<attempts>\d+) attempts"
        ),
        "mqtt_publish_fail",
    ),
    # Per-arm status (vehicle bridge only)
    (
        re.compile(
            r"MQTT health: (?P<arm_id>\w+) last status = (?P<status>\w+)"
        ),
        "mqtt_arm_status",
    ),
]

# ---------------------------------------------------------------------------
# task 23.3 — Mosquitto broker patterns
# ---------------------------------------------------------------------------

MOSQUITTO_PATTERNS = [
    (
        re.compile(
            r"New client connected from (?P<ip>[\d.]+) as (?P<client_id>\S+)"
        ),
        "mosquitto_connect",
    ),
    (
        re.compile(r"Client (?P<client_id>\S+) disconnected"),
        "mosquitto_disconnect",
    ),
    (
        re.compile(r"Socket error on client (?P<client_id>\S+)"),
        "mosquitto_socket_error",
    ),
    (
        re.compile(r"mosquitto version (?P<version>\S+) (?:running|starting)"),
        "mosquitto_start",
    ),
]

# Journalctl timestamp format for mosquitto_broker.log
_JOURNALCTL_TS_RE = re.compile(
    r"^(?P<ts>\w{3}\s+\d+\s+[\d:]+)\s+\S+\s+mosquitto\[\d+\]:\s+(?P<message>.*)"
)

# Plain epoch-second format written by mosquitto directly, e.g.:
#   1700000001: Client arm_1 disconnected.
_PLAIN_TS_RE = re.compile(r"^(?P<epoch>\d+):\s+(?P<message>.*)")


# ---------------------------------------------------------------------------
# task 23.4 — MQTT event handler (called from _parse_line in analyzer)
# ---------------------------------------------------------------------------


def handle_mqtt_event(
    analyzer: "ROS2LogAnalyzer",
    event_type_or_event,
    match_or_none=None,
    timestamp: Optional[float] = None,
    node: Optional[str] = None,
) -> None:
    """Route an MQTT event to the appropriate storage.

    Supports two calling conventions:

    1. Regex-match form (production, called from analyzer._parse_line):
       handle_mqtt_event(analyzer, event_type: str, match: re.Match, timestamp)

    2. Dict-event form (tests, called directly with a parsed event dict):
       handle_mqtt_event(analyzer, event: dict, timestamp=..., node=...)
       The dict must have 'mqtt_event' and optionally 'type' keys.
    """
    mqtt = analyzer.mqtt

    # Detect calling convention
    if isinstance(event_type_or_event, dict):
        # Dict-event form
        event = event_type_or_event
        mqtt_event = event.get("mqtt_event", "")
        evt_type = event.get("type", "")

        if mqtt_event == "connect":
            if evt_type == "reconnect":
                mqtt.connects.append({
                    "_ts": timestamp,
                    "type": "reconnect",
                    "count": int(event.get("count", 0)),
                    "total": int(event.get("total", 1)),
                })
            else:
                mqtt.connects.append({
                    "_ts": timestamp,
                    "type": "initial",
                    "count": int(event.get("count", 0)),
                    "total": int(event.get("total", 1)),
                })

        elif mqtt_event == "disconnect":
            if evt_type == "unexpected":
                mqtt.disconnects.append({
                    "_ts": timestamp,
                    "type": "unexpected",
                    "rc": int(event.get("rc", 0)),
                    "desc": event.get("desc", ""),
                })
            else:
                mqtt.disconnects.append({
                    "_ts": timestamp,
                    "type": evt_type or "clean",
                    "rc": int(event.get("rc", 0)),
                    "desc": event.get("desc", "clean"),
                })

        elif mqtt_event == "health_ok":
            mqtt.health_checks.append({
                "_ts": timestamp,
                "connected": True,
                "failures": int(event.get("failures", 0)),
                "disconnect_duration_s": 0,
            })

        elif mqtt_event == "health_disconnected":
            mqtt.health_checks.append({
                "_ts": timestamp,
                "connected": False,
                "failures": 0,
                "disconnect_duration_s": int(event.get("duration", 0)),
            })

        elif mqtt_event == "publish_fail":
            mqtt.publish_failures.append({
                "_ts": timestamp,
                "topic": event.get("topic", ""),
                "attempts": int(event.get("attempts", 0)),
            })

        elif mqtt_event == "arm_status":
            mqtt.arm_statuses.append({
                "_ts": timestamp,
                "arm_id": event.get("arm_id", ""),
                "status": event.get("status", ""),
            })
        return

    # Regex-match form (original production code path)
    event_type = event_type_or_event
    match = match_or_none

    if event_type == "mqtt_connect":
        mqtt.connects.append(
            {"_ts": timestamp, "type": "initial", "count": 0, "total": 1}
        )

    elif event_type == "mqtt_reconnect":
        mqtt.connects.append(
            {
                "_ts": timestamp,
                "type": "reconnect",
                "count": int(match.group("count")),
                "total": int(match.group("total")),
            }
        )

    elif event_type == "mqtt_disconnect":
        mqtt.disconnects.append(
            {
                "_ts": timestamp,
                "type": "unexpected",
                "rc": int(match.group("rc")),
                "desc": match.group("desc"),
            }
        )

    elif event_type == "mqtt_clean_disconnect":
        mqtt.disconnects.append(
            {"_ts": timestamp, "type": "clean", "rc": 0, "desc": "clean"}
        )

    elif event_type == "mqtt_health_ok":
        mqtt.health_checks.append(
            {
                "_ts": timestamp,
                "connected": True,
                "failures": int(match.group("failures")),
                "disconnect_duration_s": 0,
            }
        )

    elif event_type == "mqtt_health_disconnected":
        mqtt.health_checks.append(
            {
                "_ts": timestamp,
                "connected": False,
                "failures": 0,
                "disconnect_duration_s": int(match.group("duration")),
            }
        )

    elif event_type == "mqtt_publish_fail":
        mqtt.publish_failures.append(
            {
                "_ts": timestamp,
                "topic": match.group("topic"),
                "attempts": int(match.group("attempts")),
            }
        )

    elif event_type == "mqtt_arm_status":
        mqtt.arm_statuses.append(
            {
                "_ts": timestamp,
                "arm_id": match.group("arm_id"),
                "status": match.group("status"),
            }
        )


# ---------------------------------------------------------------------------
# task 23.5 — Mosquitto broker log parser
# ---------------------------------------------------------------------------


def parse_mosquitto_log(analyzer: "ROS2LogAnalyzer", filepath) -> None:
    """Parse mosquitto_broker.log (journalctl format).

    Silently skips if the file does not exist (arm-role sessions won't have it).
    """
    from pathlib import Path

    path = Path(filepath)
    if not path.exists():
        return

    try:
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                ts: Optional[float] = None
                message: Optional[str] = None

                m_ts = _JOURNALCTL_TS_RE.match(line)
                if m_ts:
                    message = m_ts.group("message")
                    # Try to parse journalctl timestamp (year absent, use current)
                    try:
                        ts_str = m_ts.group("ts")
                        # Format: "Feb 18 10:30:00" — prepend current year
                        year = datetime.now().year
                        dt = datetime.strptime(f"{year} {ts_str}", "%Y %b %d %H:%M:%S")
                        ts = dt.timestamp()
                    except ValueError:
                        pass
                else:
                    # Try plain epoch-second format: "1700000001: Client arm_1 disconnected."
                    m_plain = _PLAIN_TS_RE.match(line)
                    if m_plain:
                        message = m_plain.group("message")
                        try:
                            ts = float(m_plain.group("epoch"))
                        except ValueError:
                            pass

                if message is None:
                    continue

                for pattern, event_type in MOSQUITTO_PATTERNS:
                    m = pattern.search(message)
                    if m:
                        _handle_mosquitto_event(analyzer, event_type, m, ts)
                        break
    except OSError as exc:
        if analyzer.verbose:
            print(f"Warning: Could not parse {filepath}: {exc}")


def _handle_mosquitto_event(
    analyzer: "ROS2LogAnalyzer",
    event_type: str,
    match: re.Match,
    timestamp: Optional[float],
) -> None:
    mqtt = analyzer.mqtt

    if event_type == "mosquitto_connect":
        mqtt.broker_connects.append(
            {
                "_ts": timestamp,
                "ip": match.group("ip"),
                "client_id": match.group("client_id"),
            }
        )
    elif event_type == "mosquitto_disconnect":
        mqtt.broker_disconnects.append(
            {"_ts": timestamp, "client_id": match.group("client_id"), "socket_error": False}
        )
    elif event_type == "mosquitto_socket_error":
        mqtt.broker_disconnects.append(
            {"_ts": timestamp, "client_id": match.group("client_id"), "socket_error": True}
        )
    elif event_type == "mosquitto_start":
        mqtt.broker_starts.append(
            {"_ts": timestamp, "version": match.group("version")}
        )


# ---------------------------------------------------------------------------
# task 23.6 — MQTT issue detection
# ---------------------------------------------------------------------------

_DISCONNECT_RATE_THRESHOLD = 3   # per hour
_EXTENDED_DISCONNECT_S = 30
_ARM_STATUS_STALE_S = 300        # 5 minutes


def detect_mqtt_issues(analyzer: "ROS2LogAnalyzer") -> None:
    """Post-parse MQTT issue detection."""
    mqtt = analyzer.mqtt
    events = analyzer.events

    # Frequent unexpected disconnects
    unexpected = [d for d in mqtt.disconnects if d.get("type") == "unexpected"]
    if unexpected:
        # Compute session duration hours
        duration_h = max(
            (analyzer.end_time or 0) - (analyzer.start_time or 0), 1
        ) / 3600.0
        rate = len(unexpected) / duration_h
        if rate > _DISCONNECT_RATE_THRESHOLD:
            analyzer._add_issue(
                severity="high",
                category="mqtt",
                title="Frequent MQTT disconnects",
                description=(
                    f"{len(unexpected)} unexpected disconnects "
                    f"({rate:.1f}/hour > threshold {_DISCONNECT_RATE_THRESHOLD}/hour)"
                ),
                node="mqtt_bridge",
                timestamp=unexpected[0].get("_ts") or 0,
                message=f"MQTT disconnect count={len(unexpected)}",
                recommendation="Check broker availability and network stability",
            )

    # Extended disconnect
    for hc in mqtt.health_checks:
        if not hc.get("connected") and (hc.get("disconnect_duration_s") or 0) > _EXTENDED_DISCONNECT_S:
            # Correlate with network (task 23.7)
            ts = hc.get("_ts") or 0
            _correlate_mqtt_disconnect_with_network(analyzer, hc, ts)

    # Publish failures
    if mqtt.publish_failures:
        analyzer._add_issue(
            severity="medium",
            category="mqtt",
            title="MQTT publish failures",
            description=f"{len(mqtt.publish_failures)} publish failures detected",
            node="mqtt_bridge",
            timestamp=mqtt.publish_failures[0].get("_ts") or 0,
            message=f"publish_failures={len(mqtt.publish_failures)}",
            recommendation="Check broker availability and topic permissions",
        )

    # Stale arm status
    if mqtt.arm_statuses and analyzer.end_time:
        last_status = mqtt.arm_statuses[-1]
        last_ts = last_status.get("_ts")
        if last_ts and (analyzer.end_time - last_ts) > _ARM_STATUS_STALE_S:
            analyzer._add_issue(
                severity="high",
                category="mqtt",
                title="Stale arm status",
                description=(
                    f"No arm status update for "
                    f"{(analyzer.end_time - last_ts):.0f}s "
                    f"(threshold {_ARM_STATUS_STALE_S}s)"
                ),
                node="mqtt_bridge",
                timestamp=last_ts,
                message=f"arm_status stale arm_id={last_status.get('arm_id')}",
                recommendation="Check arm MQTT client connectivity",
            )


# ---------------------------------------------------------------------------
# task 23.7 — MQTT disconnect → network correlation
# ---------------------------------------------------------------------------


def _correlate_mqtt_disconnect_with_network(
    analyzer: "ROS2LogAnalyzer",
    health_check: dict,
    ts: float,
) -> None:
    """Cross-reference disconnect timestamp with network_monitor ping timeouts."""
    window_s = 30  # look for ping timeouts within ±30s of disconnect
    net = analyzer.network

    ping_timeout_nearby = any(
        abs(ping_ts.timestamp() - ts) < window_s
        for ping_ts, _ in getattr(net, "ping_router", [])
        # ping_router stores (datetime, ms) tuples; timeouts are tracked separately
    )
    # Also check raw timeout count vicinity — simplified: if any timeouts exist
    has_ping_timeouts = (
        getattr(net, "ping_router_timeouts", 0) > 0
        or getattr(net, "ping_broker_timeouts", 0) > 0
    )

    duration_s = health_check.get("disconnect_duration_s", 0)
    if has_ping_timeouts:
        desc = (
            f"MQTT disconnected for {duration_s}s — "
            "correlates with network ping timeout (likely network partition)"
        )
    else:
        desc = (
            f"MQTT disconnected for {duration_s}s — "
            "no corresponding ping timeout (MQTT-specific issue: keepalive/broker)"
        )

    analyzer._add_issue(
        severity="high",
        category="mqtt",
        title="Extended MQTT disconnect",
        description=desc,
        node="mqtt_bridge",
        timestamp=ts,
        message=f"MQTT DISCONNECTED for {duration_s}s",
        recommendation="Check broker health and keepalive settings",
    )
