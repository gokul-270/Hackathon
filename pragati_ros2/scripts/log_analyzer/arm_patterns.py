"""
Arm-side plain text diagnostic patterns (Group 22).

Parses [TIMING] lines that fail JSON decode and other arm C++/Python
text-format log lines for:
  - Pick failure phase/reason/recovery
  - ARM STATUS transitions
  - Motor failure structured text
  - Motion feedback (reached / timeout)
  - Recovery timing
  - Emergency shutdown
  - GPIO failures
  - Camera reconnection events
  - EE position monitoring (tasks 14.1-14.3)
  - Joint limit violations (tasks 16.1-16.2)
  - Camera stats blocks (task 17.1)
  - Scan position results (tasks 18.1-18.2)
  - Motor homing sequences (task 19.1)
  - Per-joint timing (tasks 20.1-20.3)
  - Detection quality (tasks 21.1-21.3)
  - EE start distance (task 17.1-17.3)
  - Start switch events (task 17.2)
"""

import re
import statistics as _statistics
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .analyzer import ROS2LogAnalyzer

# ---------------------------------------------------------------------------
# task 22.1 — compiled regex patterns
# ---------------------------------------------------------------------------

# Maximum number of failure detail records stored per motor
_MAX_MOTOR_FAILURE_DETAILS = 20

ARM_TEXT_PATTERNS = [
    # 22.3  Pick failure — full form with Recovery  ← [TIMING] lines that failed JSON decode
    re.compile(
        r"\[TIMING\]\s+Pick FAILED at (?P<phase>\w+) phase:\s*(?P<reason>.*?)\.\s*Recovery:\s*(?P<recovery_ms>\d+)ms",
        re.IGNORECASE,
    ),
    # 22.4  ARM STATUS
    re.compile(
        r"ARM STATUS:\s*(?P<status>UNINITIALISED|ready|busy|error|ACK)",
        re.IGNORECASE,
    ),
    # 22.5  Motor failure pipe-delimited
    re.compile(
        r"MOTOR_FAILURE\s*\|\s*motor=(?P<motor_id>\w+)\s*\|\s*cmd=(?P<cmd>\w+)"
        r"\s*\|\s*target=(?P<target>[^\s|]+)\s*\|\s*error=(?P<error>[^\s|]+)"
        r"\s*\|\s*failures=(?P<count>\d+)/(?P<max>\d+)\s*\|\s*action=(?P<action>\w+)",
    ),
    # 22.6a  Reached target
    re.compile(
        r"Reached target\s*\|\s*motor=(?P<motor_id>\w+)\s*\|\s*target=(?P<target>[^\s|]+)"
        r"\s*\|\s*actual=(?P<actual>[^\s|]+)\s*\|\s*err=(?P<err>[^\s|]+)\s*\|\s*t=(?P<time>[^\s|]+)s",
    ),
    # 22.6b  Target timeout
    re.compile(
        r"Target timeout\s*\|\s*motor=(?P<motor_id>\w+)"
        r"(?:\s*\|\s*target=(?P<target>[^\s|]+))?"
        r"(?:\s*\|\s*last=(?P<last>[^\s|]+))?"
        r"(?:\s*\|\s*err=(?P<err>[^\s|]+))?"
        r"(?:\s*\|\s*timeout=(?P<timeout>[^\s|]+?)s?)?",
    ),
    # 22.7  Recovery total
    re.compile(
        r"\[TIMING\]\s+Recovery\s+(?P<recovery_ms>\d+)ms",
        re.IGNORECASE,
    ),
    # 22.8  Emergency shutdown
    re.compile(
        r"EMERGENCY SHUTDOWN TRIGGERED:\s*(?P<reason>.*)",
        re.IGNORECASE,
    ),
    # 22.9a  GPIO write failed (no count)
    re.compile(r"GPIO write failed", re.IGNORECASE),
    # 22.9b  GPIO write_failures count
    re.compile(r"write_failures=(?P<count>\d+)", re.IGNORECASE),
    # 22.10a  XLink error
    re.compile(r"XLink error detected", re.IGNORECASE),
    # 22.10b  Camera reconnection attempt
    re.compile(r"Camera reconnection attempt", re.IGNORECASE),
    # 22.10c  Camera reconnected (success)
    re.compile(r"Camera reconnected", re.IGNORECASE),
    # 22.10d  Consecutive detection timeouts
    re.compile(r"consecutive detection timeouts.*forcing camera reconnect", re.IGNORECASE),
    # 22.3b  Pick failure — short form without Recovery suffix (e.g. "[TIMING] PICK FAILED at approach: reason")
    re.compile(
        r"PICK FAILED at (?P<phase>\w+):\s*(?P<reason>.*)",
        re.IGNORECASE,
    ),
    # 22.5b  Motor failure — simple text form (e.g. "[TIMING] Motor J2 failed: CAN timeout")
    re.compile(
        r"Motor (?P<motor_id>\w+) failed:\s*(?P<reason>.*)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# task 22.2 — _parse_timing_text dispatcher
# ---------------------------------------------------------------------------


def parse_timing_text(
    analyzer: "ROS2LogAnalyzer",
    message: str,
    timestamp: Optional[float],
    node: Optional[str] = None,
) -> None:
    """Called when a [TIMING] line (or any arm text line) fails JSON decode.

    Tries each ARM_TEXT_PATTERNS entry in order.  Multiple patterns may match
    a single line (e.g. a line could contain both a TIMING prefix and GPIO).
    The optional `node` parameter is accepted for compatibility but not used by
    the individual sub-handlers (they record timestamps only).
    """
    _try_pick_failure(analyzer, message, timestamp)
    _try_arm_status(analyzer, message, timestamp)
    _try_motor_failure(analyzer, message, timestamp)
    _try_reached_target(analyzer, message, timestamp)
    _try_target_timeout(analyzer, message, timestamp)
    _try_recovery(analyzer, message, timestamp)
    _try_emergency_shutdown(analyzer, message, timestamp)
    _try_gpio_failure(analyzer, message, timestamp)
    _try_camera_reconnection(analyzer, message, timestamp)
    _try_pick_failure_short(analyzer, message, timestamp)
    _try_motor_failure_simple(analyzer, message, timestamp)
    # tasks 14-21 — new diagnostic patterns
    _try_ee_monitoring(analyzer, message, timestamp)
    _try_joint_limit(analyzer, message, timestamp)
    _try_camera_stats_block(analyzer, message, timestamp)
    _try_scan_results(analyzer, message, timestamp)
    _try_homing(analyzer, message, timestamp)
    _try_per_joint_timing(analyzer, message, timestamp)
    _try_detection_quality(analyzer, message, timestamp)
    _try_stale_detection(analyzer, message, timestamp)
    # task 17.1-17.2 — EE start distance and start switch
    _try_ee_start_distance(analyzer, message, timestamp)
    _try_start_switch(analyzer, message, timestamp)


# ---------------------------------------------------------------------------
# Individual pattern handlers (tasks 22.3-22.10)
# ---------------------------------------------------------------------------


def _try_pick_failure(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.3"""
    m = ARM_TEXT_PATTERNS[0].search(message)
    if m:
        analyzer.events.pick_failures.append(
            {
                "phase": m.group("phase"),
                "reason": m.group("reason").strip(),
                "recovery_ms": int(m.group("recovery_ms")),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )


def _try_arm_status(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.4"""
    m = ARM_TEXT_PATTERNS[1].search(message)
    if m:
        analyzer.events.arm_status_transitions.append(
            {"status": m.group("status"), "_ts": timestamp, "arm_id": analyzer._current_arm_id}
        )


def _try_motor_failure(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.5"""
    m = ARM_TEXT_PATTERNS[2].search(message)
    if m:
        motor_id = m.group("motor_id")
        analyzer.events.motor_failure_counts[motor_id] = (
            analyzer.events.motor_failure_counts.get(motor_id, 0) + 1
        )
        if len(analyzer.events.motor_failure_details) < _MAX_MOTOR_FAILURE_DETAILS:
            analyzer.events.motor_failure_details.append(
                {
                    "motor_id": motor_id,
                    "cmd": m.group("cmd"),
                    "target": m.group("target"),
                    "error": m.group("error"),
                    "count": int(m.group("count")),
                    "max": int(m.group("max")),
                    "action": m.group("action"),
                    "_ts": timestamp,
                    "arm_id": analyzer._current_arm_id,
                }
            )


def _try_reached_target(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.6a"""
    m = ARM_TEXT_PATTERNS[3].search(message)
    if m:
        motor_id = m.group("motor_id")
        stats = analyzer.events.motor_reach_stats.setdefault(
            motor_id, {"reached": 0, "timeout": 0, "errors": []}
        )
        stats["reached"] += 1
        event: dict = {"motor_id": motor_id}
        try:
            event["target_position"] = float(m.group("target"))
        except (ValueError, IndexError):
            pass
        try:
            event["actual_position"] = float(m.group("actual"))
        except (ValueError, IndexError):
            pass
        try:
            settle = float(m.group("time"))
            event["settle_time_ms"] = settle
        except (ValueError, IndexError):
            pass
        try:
            stats["errors"].append(float(m.group("err")))
        except ValueError:
            pass
        stats.setdefault("events", []).append(event)


def _try_target_timeout(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.6b"""
    m = ARM_TEXT_PATTERNS[4].search(message)
    if m:
        motor_id = m.group("motor_id")
        stats = analyzer.events.motor_reach_stats.setdefault(
            motor_id, {"reached": 0, "timeout": 0, "errors": []}
        )
        stats["timeout"] += 1
        event: dict = {"motor_id": motor_id}
        try:
            timeout_raw = m.group("timeout")
            if timeout_raw is not None:
                timeout_s = float(timeout_raw)
                event["timeout_duration_ms"] = timeout_s * 1000.0
        except (ValueError, IndexError):
            pass
        try:
            target_raw = m.group("target")
            if target_raw is not None:
                event["target_position"] = float(target_raw)
        except (ValueError, IndexError):
            pass
        stats.setdefault("timeout_events", []).append(event)


def _try_recovery(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.7"""
    m = ARM_TEXT_PATTERNS[5].search(message)
    if m:
        analyzer.events.recovery_count += 1
        analyzer.events.recovery_total_ms += float(m.group("recovery_ms"))


def _try_emergency_shutdown(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.8"""
    m = ARM_TEXT_PATTERNS[6].search(message)
    if m:
        analyzer.events.emergency_shutdowns.append(
            {"reason": m.group("reason").strip(), "_ts": timestamp, "arm_id": analyzer._current_arm_id}
        )


def _try_gpio_failure(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.9"""
    if ARM_TEXT_PATTERNS[7].search(message):
        analyzer.events.gpio_failures += 1
        return
    m = ARM_TEXT_PATTERNS[8].search(message)
    if m:
        analyzer.events.gpio_failures += int(m.group("count"))


def _try_camera_reconnection(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 22.10"""
    if ARM_TEXT_PATTERNS[9].search(message):  # XLink error
        analyzer.events.camera_reconnections.append(
            {"type": "xlink", "_ts": timestamp, "success": False, "arm_id": analyzer._current_arm_id}
        )
    elif ARM_TEXT_PATTERNS[10].search(message):  # attempt
        analyzer.events.camera_reconnections.append(
            {"type": "attempt", "_ts": timestamp, "success": False, "arm_id": analyzer._current_arm_id}
        )
    elif ARM_TEXT_PATTERNS[11].search(message):  # reconnected (success)
        analyzer.events.camera_reconnections.append(
            {"type": "reconnected", "_ts": timestamp, "success": True, "arm_id": analyzer._current_arm_id}
        )
    elif ARM_TEXT_PATTERNS[12].search(message):  # timeout-forced
        analyzer.events.camera_reconnections.append(
            {"type": "timeout", "_ts": timestamp, "success": False, "arm_id": analyzer._current_arm_id}
        )


def _try_pick_failure_short(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """22.3b — short-form pick failure without Recovery suffix.

    Matches: "PICK FAILED at <phase>: <reason>"
    Only fires if the full-form pattern (22.3) did not already match.
    """
    # Skip if full-form already matched (full-form requires "phase" word before colon)
    if ARM_TEXT_PATTERNS[0].search(message):
        return
    m = ARM_TEXT_PATTERNS[13].search(message)
    if m:
        analyzer.events.pick_failures.append(
            {
                "phase": m.group("phase"),
                "reason": m.group("reason").strip(),
                "recovery_ms": 0,
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )


def _try_motor_failure_simple(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """22.5b — simple text-form motor failure.

    Matches: "Motor <id> failed: <reason>"
    Only fires if the pipe-delimited form (22.5) did not already match.
    """
    if ARM_TEXT_PATTERNS[2].search(message):
        return
    m = ARM_TEXT_PATTERNS[14].search(message)
    if m:
        motor_id = m.group("motor_id")
        analyzer.events.motor_failure_counts[motor_id] = (
            analyzer.events.motor_failure_counts.get(motor_id, 0) + 1
        )
        if len(analyzer.events.motor_failure_details) < _MAX_MOTOR_FAILURE_DETAILS:
            analyzer.events.motor_failure_details.append(
                {
                    "motor_id": motor_id,
                    "cmd": "",
                    "target": "",
                    "error": m.group("reason").strip(),
                    "count": 1,
                    "max": 0,
                    "action": "",
                    "_ts": timestamp,
                    "arm_id": analyzer._current_arm_id,
                }
            )


# ---------------------------------------------------------------------------
# tasks 14.1-14.3 — EE position monitoring patterns
# ---------------------------------------------------------------------------

_RE_EE_TIMEOUT = re.compile(
    r"\[EE\]\s+Dynamic:\s+Position monitoring TIMEOUT!\s+loops=(\d+),\s+last_pos=(-?[\d.]+)m",
    re.IGNORECASE,
)
_RE_EE_SUCCESS = re.compile(
    r"\[EE\]\s+Dynamic:\s+Position reached target",
    re.IGNORECASE,
)
_RE_EE_SHORT_RETRACT = re.compile(
    r"\[EE\]\s+Retreat:\s+Very short retract\s+\((-?\d+)mm\)",
    re.IGNORECASE,
)


def _try_ee_monitoring(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """tasks 14.1-14.3 — EE monitoring events."""
    m = _RE_EE_TIMEOUT.search(message)
    if m:
        analyzer.events.ee_monitoring_events.append(
            {
                "type": "timeout",
                "loops": int(m.group(1)),
                "last_pos_m": float(m.group(2)),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return
    if _RE_EE_SUCCESS.search(message):
        analyzer.events.ee_monitoring_events.append(
            {
                "type": "success",
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return
    m2 = _RE_EE_SHORT_RETRACT.search(message)
    if m2:
        analyzer.events.ee_short_retract_events.append(
            {
                "retract_mm": float(m2.group(1)),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )


# ---------------------------------------------------------------------------
# tasks 16.1-16.2 — Joint limit violation patterns
# ---------------------------------------------------------------------------

_RE_JOINT_LIMIT = re.compile(
    r"(Joint\d+)\s+\(([^)]+)\)\s+limit exceeded!",
    re.IGNORECASE,
)
_RE_JOINT_LIMIT_CALC = re.compile(
    r"Calculated:\s*([-\d.]+)\s*m,\s*Limits:\s*\[\s*([-\d.]+),\s*([-\d.]+)\s*\]\s*m",
    re.IGNORECASE,
)
_RE_JOINT_LIMIT_DIR = re.compile(
    r"Target too far\s+(LEFT|RIGHT)",
    re.IGNORECASE,
)
_RE_JOINT_LIMIT_FAILURES = re.compile(
    r"Joint limit failures so far:\s*(\d+)",
    re.IGNORECASE,
)

# State-machine accumulator: holds partial records between consecutive lines
_joint_limit_pending: dict = {}


def _try_joint_limit(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """tasks 16.1-16.2 — joint limit violation events."""
    global _joint_limit_pending

    # Running cumulative count
    m_count = _RE_JOINT_LIMIT_FAILURES.search(message)
    if m_count:
        analyzer.events._joint_limit_total = int(m_count.group(1))
        return

    m_lim = _RE_JOINT_LIMIT.search(message)
    if m_lim:
        # Start new pending record
        _joint_limit_pending = {
            "joint_name": m_lim.group(1),
            "direction": m_lim.group(2).lower(),
            "calculated_m": None,
            "limit_min_m": None,
            "limit_max_m": None,
            "overshoot_m": None,
            "_ts": timestamp,
            "arm_id": analyzer._current_arm_id,
        }
        return

    if _joint_limit_pending:
        m_calc = _RE_JOINT_LIMIT_CALC.search(message)
        if m_calc:
            calc = float(m_calc.group(1))
            lim_min = float(m_calc.group(2))
            lim_max = float(m_calc.group(3))
            _joint_limit_pending["calculated_m"] = calc
            _joint_limit_pending["limit_min_m"] = lim_min
            _joint_limit_pending["limit_max_m"] = lim_max
            # overshoot = how far beyond the violated limit
            direction = _joint_limit_pending.get("direction", "")
            if direction == "left":
                overshoot = abs(calc - lim_min) if calc < lim_min else 0.0
            else:
                overshoot = abs(calc - lim_max) if calc > lim_max else 0.0
            _joint_limit_pending["overshoot_m"] = round(overshoot, 4)
            return

        m_dir = _RE_JOINT_LIMIT_DIR.search(message)
        if m_dir:
            # Flush the pending record
            rec = dict(_joint_limit_pending)
            rec["direction"] = m_dir.group(1).lower()
            analyzer.events.joint_limit_events.append(rec)
            _joint_limit_pending = {}
            return

        # Flush if unrelated line arrives (avoid stale accumulation)
        if _joint_limit_pending.get("calculated_m") is not None:
            analyzer.events.joint_limit_events.append(dict(_joint_limit_pending))
            _joint_limit_pending = {}


# ---------------------------------------------------------------------------
# task 17.1 — Camera stats block state machine
# ---------------------------------------------------------------------------

_RE_CAMERA_SEPARATOR = re.compile(r"[═]{4,}")
_RE_CAMERA_TEMP = re.compile(r"Temp:\s*([\d.]+)\s*°C", re.IGNORECASE)
_RE_CAMERA_FRAMES = re.compile(r"Frames:\s*(\d+)", re.IGNORECASE)
_RE_CAMERA_OAKD = re.compile(
    r"OAK-D:\s*CSS=([\d.]+)%\s+MSS=([\d.]+)%", re.IGNORECASE
)
_RE_CAMERA_USB = re.compile(
    r"USB:\s*(.+?)\s*\|\s*XLink errors:\s*(\d+)", re.IGNORECASE
)
_RE_CAMERA_REQUESTS = re.compile(
    r"Requests:\s*(\d+)\s*\|\s*Success:\s*(\d+)\s*\|\s*WithCotton:\s*(\d+)\s*\(([\d.]+)%\)",
    re.IGNORECASE,
)
_RE_CAMERA_LATENCY = re.compile(
    r"Latency:\s*avg=(\d+)ms,\s*min=(\d+)ms,\s*max=(\d+)ms", re.IGNORECASE
)
_RE_CAMERA_FRAME_WAIT = re.compile(
    r"Frame wait:\s*avg=(\d+)ms,\s*max=(\d+)ms\s*\(n=(\d+)\)", re.IGNORECASE
)
_RE_CAMERA_MEMORY = re.compile(r"Memory:\s*(\d+)\s*MB", re.IGNORECASE)
_RE_CAMERA_UPTIME = re.compile(r"Uptime:\s*([\d.]+)\s*s", re.IGNORECASE)

# Per-analyzer state machine (keyed by id(analyzer))
_camera_block_pending: dict = {}
_camera_block_in_block: dict = {}


def _try_camera_stats_block(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 17.1 — camera stats block state machine."""
    key = id(analyzer)
    in_block = _camera_block_in_block.get(key, False)

    if _RE_CAMERA_SEPARATOR.search(message):
        if not in_block:
            # Enter block — start new accumulator
            _camera_block_in_block[key] = True
            _camera_block_pending[key] = {
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        else:
            # Exit block — flush accumulator
            _camera_block_in_block[key] = False
            block = _camera_block_pending.pop(key, None)
            if block:
                analyzer.events.camera_stats_blocks.append(block)
        return

    if not in_block:
        return

    block = _camera_block_pending.get(key, {})

    m = _RE_CAMERA_TEMP.search(message)
    if m:
        block["temp_c"] = float(m.group(1))
    m = _RE_CAMERA_FRAMES.search(message)
    if m:
        block["frames"] = int(m.group(1))
    m = _RE_CAMERA_OAKD.search(message)
    if m:
        block["css_pct"] = float(m.group(1))
        block["mss_pct"] = float(m.group(2))
    m = _RE_CAMERA_USB.search(message)
    if m:
        block["usb_mode"] = m.group(1).strip()
        block["xlink_errors"] = int(m.group(2))
    m = _RE_CAMERA_REQUESTS.search(message)
    if m:
        block["requests"] = int(m.group(1))
        block["success"] = int(m.group(2))
        block["with_cotton"] = int(m.group(3))
        block["with_cotton_pct"] = float(m.group(4))
    m = _RE_CAMERA_LATENCY.search(message)
    if m:
        block["latency_avg_ms"] = int(m.group(1))
        block["latency_min_ms"] = int(m.group(2))
        block["latency_max_ms"] = int(m.group(3))
    m = _RE_CAMERA_FRAME_WAIT.search(message)
    if m:
        block["frame_wait_avg_ms"] = int(m.group(1))
        block["frame_wait_max_ms"] = int(m.group(2))
        block["frame_wait_n"] = int(m.group(3))
    m = _RE_CAMERA_MEMORY.search(message)
    if m:
        block["memory_mb"] = int(m.group(1))
    m = _RE_CAMERA_UPTIME.search(message)
    if m:
        block["uptime_s"] = float(m.group(1))


# ---------------------------------------------------------------------------
# tasks 18.1-18.2 — Scan position result patterns
# ---------------------------------------------------------------------------

_RE_SCAN_POSITION = re.compile(
    r"Position\s+(\d+)/(\d+):\s+J4\s+=\s+([+-]?[\d.]+)m",
    re.IGNORECASE,
)
_RE_SCAN_FOUND = re.compile(
    r"Found\s+(\d+)\s+cotton\(s\)\s+at\s+J4=([+-]?[\d.]+)m\s+\(detection took\s+(\d+)ms\)",
    re.IGNORECASE,
)
_RE_SCAN_PICKED = re.compile(
    r"Picked\s+(\d+)/(\d+)\s+cotton\(s\)\s+at\s+J4=([+-]?[\d.]+)m\s+\(took\s+(\d+)ms\)",
    re.IGNORECASE,
)
_RE_SCAN_SUMMARY = re.compile(
    r"Cotton found:\s+center=(\d+),\s+non-center=(\d+)\s+\(([\d.]+)%\s+improvement[\w\s-]*[^)]*\)",
    re.IGNORECASE,
)
_RE_SCAN_EFFECTIVENESS = re.compile(
    r"J4 offset\s+([+-]?[\d.]+)m(?:\s*\([^)]*\))?:\s+(\d+)\s+cotton\(s\)\s+found",
    re.IGNORECASE,
)

# State for building scan position records (flushed on each "Position N/M" line)
_scan_pending: dict = {}


def _try_scan_results(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """tasks 18.1-18.2 — scan position results."""
    global _scan_pending

    # Scan summary line
    m = _RE_SCAN_SUMMARY.search(message)
    if m:
        analyzer.events.scan_summaries.append(
            {
                "center_count": int(m.group(1)),
                "non_center_count": int(m.group(2)),
                "improvement_pct": float(m.group(3)),
                "total_scans": None,
                "early_exits": None,
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return

    # Cumulative summary lines ("J4 offset +X.XXXm: N cotton(s) found")
    # emitted at end-of-session.  These duplicate data already captured
    # by the per-position flow (Position N/M → Found → Picked), so we
    # intentionally skip them to avoid double-counting.
    m = _RE_SCAN_EFFECTIVENESS.search(message)
    if m:
        return

    # Position header
    m = _RE_SCAN_POSITION.search(message)
    if m:
        # Flush previous pending if any
        if _scan_pending:
            analyzer.events.scan_position_results.append(dict(_scan_pending))
        _scan_pending = {
            "position_index": int(m.group(1)),
            "total_positions": int(m.group(2)),
            "j4_offset_m": float(m.group(3)),
            "cotton_found": 0,
            "cotton_picked": 0,
            "detection_time_ms": None,
            "pick_time_ms": None,
            "_ts": timestamp,
            "arm_id": analyzer._current_arm_id,
        }
        return

    # Found cotton
    m = _RE_SCAN_FOUND.search(message)
    if m:
        if _scan_pending:
            _scan_pending["cotton_found"] = int(m.group(1))
            _scan_pending["detection_time_ms"] = int(m.group(3))
        return

    # Picked cotton — flush record
    m = _RE_SCAN_PICKED.search(message)
    if m:
        if _scan_pending:
            _scan_pending["cotton_picked"] = int(m.group(1))
            _scan_pending["pick_time_ms"] = int(m.group(4))
            analyzer.events.scan_position_results.append(dict(_scan_pending))
            _scan_pending = {}


# ---------------------------------------------------------------------------
# task 19.1 — Motor homing state machine
# ---------------------------------------------------------------------------

_RE_HOMING_START = re.compile(r"Homing Sequence:\s+(\w+)", re.IGNORECASE)
_RE_HOMING_VERIFY = re.compile(
    r"Already at homing target\s+\(target=([-\d.]+),\s+actual=([-\d.]+),\s+err=([\d.]+),\s+tol=([\d.]+)\)",
    re.IGNORECASE,
)
_RE_HOMING_COMPLETE = re.compile(
    r"Homing sequence completed for\s+(\w+)", re.IGNORECASE
)

_homing_pending: dict = {}


def _try_homing(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 19.1 — homing sequence state machine."""
    global _homing_pending

    m = _RE_HOMING_START.search(message)
    if m:
        _homing_pending = {
            "joint": m.group(1),
            "success": False,
            "position_error": None,
            "tolerance": None,
            "_ts": timestamp,
            "arm_id": analyzer._current_arm_id,
        }
        return

    if _homing_pending:
        m = _RE_HOMING_VERIFY.search(message)
        if m:
            _homing_pending["target_position"] = float(m.group(1))
            _homing_pending["actual_position"] = float(m.group(2))
            _homing_pending["position_error"] = float(m.group(3))
            _homing_pending["tolerance"] = float(m.group(4))
            return

        m = _RE_HOMING_COMPLETE.search(message)
        if m:
            _homing_pending["joint"] = m.group(1)
            _homing_pending["success"] = True
            analyzer.events.homing_events.append(dict(_homing_pending))
            _homing_pending = {}
            return


def _flush_pending_homing(analyzer: "ROS2LogAnalyzer") -> None:
    """Flush any incomplete homing record (called at end of parse pass)."""
    global _homing_pending
    if _homing_pending:
        analyzer.events.homing_events.append(dict(_homing_pending))
        _homing_pending = {}


# ---------------------------------------------------------------------------
# tasks 20.1-20.3 — Per-joint timing patterns
# ---------------------------------------------------------------------------

_RE_JOINT_APPROACH = re.compile(
    r"\[TIMING\]\s+(J\d+(?:\+EE)?)\s+approach motion:\s*(\d+)ms",
    re.IGNORECASE,
)
_RE_RETREAT_BREAKDOWN = re.compile(
    r"\[TIMING\]\s+Retreat breakdown:\s*J5=(\d+)ms,\s*EE_off=(\d+)ms,\s*J3=(\d+)ms,\s*J4=(\d+)ms,\s*compressor=(\d+)ms",
    re.IGNORECASE,
)
_RE_EE_ON_DURATION = re.compile(
    r"\[TIMING\]\s+EE total ON duration:\s*(\d+)ms",
    re.IGNORECASE,
)
_RE_J5_EE_BREAKDOWN = re.compile(
    r"\[TIMING\]\s+J5\+EE breakdown:\s*j5_travel=(\d+)ms,\s*ee_pretravel=(\d+|n/a)ms,\s*ee_overlap=(\d+)ms,\s*ee_dwell=(\d+)ms",
    re.IGNORECASE,
)


def _try_per_joint_timing(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """tasks 20.1-20.3 — per-joint timing records."""
    m = _RE_JOINT_APPROACH.search(message)
    if m:
        joint_raw = m.group(1)
        # Normalise: J3→j3, J4→j4, J5+EE→j5_ee
        joint = joint_raw.lower().replace("+", "_")
        analyzer.events.per_joint_timings.append(
            {
                "joint": joint,
                "phase": "approach",
                "duration_ms": int(m.group(2)),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return

    m = _RE_RETREAT_BREAKDOWN.search(message)
    if m:
        analyzer.events.retreat_breakdowns.append(
            {
                "j5_ms": int(m.group(1)),
                "ee_off_ms": int(m.group(2)),
                "j3_ms": int(m.group(3)),
                "j4_ms": int(m.group(4)),
                "compressor_ms": int(m.group(5)),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return

    m = _RE_EE_ON_DURATION.search(message)
    if m:
        analyzer.events.ee_on_durations.append(
            {
                "ee_on_ms": int(m.group(1)),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return

    m = _RE_J5_EE_BREAKDOWN.search(message)
    if m:
        pre = m.group(2)
        analyzer.events.j5_ee_breakdowns.append(
            {
                "j5_travel_ms": int(m.group(1)),
                "ee_pretravel_ms": int(pre) if pre != "n/a" else None,
                "ee_overlap_ms": int(m.group(3)),
                "ee_dwell_ms": int(m.group(4)),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )


# ---------------------------------------------------------------------------
# tasks 21.1-21.3 — Detection quality patterns
# ---------------------------------------------------------------------------

_RE_DETECTIONS = re.compile(
    r"Detections:\s*raw=(\d+),\s*cotton_accepted=(\d+),"
    r"\s*border_skip=(\d+)\s*\(total:(\d+)\),"
    r"\s*not_pickable=(\d+)\s*\(total:(\d+)\)"
    r"(?:,\s*workspace_reject=(\d+)\s*\(total:(\d+)\))?",
    re.IGNORECASE,
)
_RE_FRAME_FRESHNESS = re.compile(
    r"Frame freshness:\s*flushed\s+(\d+)\s+stale.*?waited\s+(\d+)\s+ms\s+for\s+fresh\s+detection",
    re.IGNORECASE,
)
_RE_FALLBACK_POSITIONS = re.compile(
    r"Zero cotton detected\s*-\s*publishing\s+(\d+)\s+fallback positions",
    re.IGNORECASE,
)


def _try_detection_quality(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """tasks 21.1-21.3 — detection quality events."""
    m = _RE_DETECTIONS.search(message)
    if m:
        ws_reject = int(m.group(7)) if m.group(7) is not None else 0
        ws_reject_total = (
            int(m.group(8)) if m.group(8) is not None else 0
        )
        analyzer.events.detection_quality_events.append(
            {
                "raw": int(m.group(1)),
                "cotton_accepted": int(m.group(2)),
                "border_skip": int(m.group(3)),
                "border_skip_total": int(m.group(4)),
                "not_pickable": int(m.group(5)),
                "not_pickable_total": int(m.group(6)),
                "workspace_reject": ws_reject,
                "workspace_reject_total": ws_reject_total,
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return

    m = _RE_FRAME_FRESHNESS.search(message)
    if m:
        analyzer.events.frame_freshness_events.append(
            {
                "stale_flushed": int(m.group(1)),
                "wait_ms": int(m.group(2)),
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return

    m = _RE_FALLBACK_POSITIONS.search(message)
    if m:
        # Track cumulative count
        current = getattr(analyzer.events, "_fallback_position_count", 0)
        analyzer.events._fallback_position_count = current + int(m.group(1))


# ---------------------------------------------------------------------------
# task 6.4 — Stale detection warning patterns
# ---------------------------------------------------------------------------

_RE_STALE_DETECTION_DATA = re.compile(
    r"detection data is stale(?:.*?age[=:\s]*(\d+(?:\.\d+)?)\s*ms)?",
    re.IGNORECASE,
)
_RE_FRAME_AGE_EXCEEDS = re.compile(
    r"frame age exceeds threshold(?:.*?age[=:\s]*(\d+(?:\.\d+)?)\s*ms)?",
    re.IGNORECASE,
)
_RE_STALE_FRAME_DETECTED = re.compile(
    r"stale frame detected(?:.*?age[=:\s]*(\d+(?:\.\d+)?)\s*ms)?",
    re.IGNORECASE,
)


def _try_stale_detection(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 6.4 — capture stale detection warnings from C++ nodes."""
    for pattern in (
        _RE_STALE_DETECTION_DATA,
        _RE_FRAME_AGE_EXCEEDS,
        _RE_STALE_FRAME_DETECTED,
    ):
        m = pattern.search(message)
        if m:
            age_ms: Optional[float] = None
            if m.group(1):
                try:
                    age_ms = float(m.group(1))
                except ValueError:
                    pass
            analyzer.events.stale_detection_warnings.append(
                {
                    "_ts": timestamp,
                    "reported_age_ms": age_ms,
                    "source_node": analyzer._current_arm_id,
                }
            )
            return  # only first matching pattern per line


# ---------------------------------------------------------------------------
# task 17.1 — EE start distance patterns
# ---------------------------------------------------------------------------

_RE_EE_START_DISTANCE = re.compile(
    r"EE\s+(?:dynamic\s+)?start\s+distance:\s*([\d.]+)\s*mm",
    re.IGNORECASE,
)
_RE_EE_START_DISTANCE_JSON = re.compile(
    r"start_distance_mm[\"']?\s*[:=]\s*([\d.]+)",
    re.IGNORECASE,
)


def _try_ee_start_distance(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 17.1 — parse EE dynamic start distance from text or JSON-like lines."""
    m = _RE_EE_START_DISTANCE.search(message)
    if not m:
        m = _RE_EE_START_DISTANCE_JSON.search(message)
    if m:
        try:
            dist_mm = float(m.group(1))
        except ValueError:
            return
        analyzer.events.ee_start_distances.append(
            {
                "distance_mm": dist_mm,
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )


# ---------------------------------------------------------------------------
# task 17.2 — Start switch activation/deactivation patterns
# ---------------------------------------------------------------------------

_RE_START_SWITCH_ACTIVATED = re.compile(
    r"[Ss]tart\s+switch\s+(activated|pressed|triggered|ON)",
    re.IGNORECASE,
)
_RE_START_SWITCH_DEACTIVATED = re.compile(
    r"[Ss]tart\s+switch\s+(deactivated|released|OFF)",
    re.IGNORECASE,
)


def _try_start_switch(
    analyzer: "ROS2LogAnalyzer", message: str, timestamp: Optional[float]
) -> None:
    """task 17.2 — parse start switch activation/deactivation events."""
    if _RE_START_SWITCH_ACTIVATED.search(message):
        analyzer.events.start_switch_events.append(
            {
                "type": "activated",
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )
        return
    if _RE_START_SWITCH_DEACTIVATED.search(message):
        analyzer.events.start_switch_events.append(
            {
                "type": "deactivated",
                "_ts": timestamp,
                "arm_id": analyzer._current_arm_id,
            }
        )


# ---------------------------------------------------------------------------
# task 22.12 — post-parse arm text issue detection
# ---------------------------------------------------------------------------

_PHASE_FAILURE_THRESHOLD = 3   # >3 failures at same phase → issue
_MOTOR_FAILURE_RATE_THRESHOLD = 5   # >5 failures per motor → issue
_CAMERA_RECONNECT_THRESHOLD = 3  # >3 reconnects → issue
_GPIO_FAILURE_THRESHOLD = 5   # >5 cumulative GPIO failures → issue


def detect_arm_text_issues(analyzer: "ROS2LogAnalyzer") -> None:
    """task 22.12 — post-parse issue detection from text patterns."""
    events = analyzer.events

    # Frequent pick failures at same phase
    phase_counts: dict = {}
    for pf in events.pick_failures:
        phase = pf.get("phase", "unknown")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
    for phase, count in phase_counts.items():
        if count > _PHASE_FAILURE_THRESHOLD:
            analyzer._add_issue(
                severity="high",
                category="arm",
                title=f"Frequent pick failures at {phase} phase",
                description=f"{count} pick failures detected at the {phase} phase",
                node="motion_controller",
                timestamp=0,
                message=f"Pick failure phase={phase} count={count}",
                recommendation="Inspect arm mechanics and motion profile for this phase",
            )

    # Arm stuck in error state (last status is error)
    if events.arm_status_transitions:
        last_status = events.arm_status_transitions[-1].get("status", "")
        if last_status == "error":
            analyzer._add_issue(
                severity="high",
                category="arm",
                title="Arm ended session in error state",
                description="ARM STATUS: error was the last recorded arm state",
                node="arm_system",
                timestamp=0,
                message="ARM STATUS: error (session end)",
                recommendation="Review arm error recovery logic and error cause",
            )

    # High motor failure rate
    for motor_id, count in events.motor_failure_counts.items():
        if count > _MOTOR_FAILURE_RATE_THRESHOLD:
            analyzer._add_issue(
                severity="high",
                category="motor",
                title=f"High motor failure rate: {motor_id}",
                description=f"{count} command failures for motor {motor_id}",
                node="mg6010_controller",
                timestamp=0,
                message=f"MOTOR_FAILURE motor={motor_id} count={count}",
                recommendation="Check CAN bus connection and motor power for this joint",
            )

    # Motor target timeouts with duration info
    for motor_id, stats in events.motor_reach_stats.items():
        timeout_count = stats.get("timeout", 0)
        if timeout_count > 0:
            timeout_events = stats.get("timeout_events", [])
            durations = [
                e["timeout_duration_ms"]
                for e in timeout_events
                if "timeout_duration_ms" in e
            ]
            if durations:
                avg_dur = sum(durations) / len(durations)
                msg = (
                    f"Target timeout motor={motor_id} "
                    f"count={timeout_count} avg_duration={avg_dur:.0f}ms"
                )
            else:
                msg = f"Target timeout motor={motor_id} count={timeout_count}"
            analyzer._add_issue(
                severity="medium",
                category="motor",
                title=f"Motor target timeouts: {motor_id}",
                description=f"{timeout_count} target timeouts for motor {motor_id}",
                node="mg6010_controller",
                timestamp=0,
                message=msg,
                recommendation="Check motor load, PID tuning, and CAN bus latency",
            )

    # GPIO reliability
    if events.gpio_failures > _GPIO_FAILURE_THRESHOLD:
        analyzer._add_issue(
            severity="medium",
            category="hardware",
            title="GPIO reliability issues",
            description=f"{events.gpio_failures} cumulative GPIO write failures",
            node="gpio_control",
            timestamp=0,
            message=f"gpio_failures={events.gpio_failures}",
            recommendation="Check GPIO hardware and wiring",
        )

    # Camera reconnection frequency
    reconnect_events = [
        e for e in events.camera_reconnections if e.get("type") in ("reconnected",)
    ]
    if len(reconnect_events) > _CAMERA_RECONNECT_THRESHOLD:
        analyzer._add_issue(
            severity="medium",
            category="camera",
            title="Frequent camera reconnections",
            description=f"{len(reconnect_events)} camera reconnections during session",
            node="cotton_detection",
            timestamp=0,
            message=f"camera_reconnections={len(reconnect_events)}",
            recommendation="Check USB cable quality, hub power, and OAK-D thermal state",
        )

    # task 17.3 — EE start distance analysis
    _detect_ee_start_distance_issues(analyzer)


# ---------------------------------------------------------------------------
# task 17.3 — EE start distance issue detection
# ---------------------------------------------------------------------------

_EE_DIST_STDDEV_THRESHOLD_MM = 30.0   # stddev > 30mm → Low
_EE_DIST_MAX_THRESHOLD_MM = 200.0     # distance > 200mm → Medium
_EE_DIST_MIN_THRESHOLD_MM = 20.0      # distance < 20mm → Medium


def _detect_ee_start_distance_issues(analyzer: "ROS2LogAnalyzer") -> None:
    """task 17.3 — raise issues based on EE start distance statistics."""
    distances = [
        e["distance_mm"] for e in analyzer.events.ee_start_distances
        if e.get("distance_mm") is not None
    ]
    if len(distances) < 2:
        return

    mean_d = _statistics.mean(distances)
    stddev_d = _statistics.stdev(distances)
    min_d = min(distances)
    max_d = max(distances)

    if stddev_d > _EE_DIST_STDDEV_THRESHOLD_MM:
        analyzer._add_issue(
            severity="low",
            category="arm",
            title="High EE start distance variability",
            description=(
                f"EE start distance stddev={stddev_d:.1f}mm"
                f" (mean={mean_d:.1f}mm, n={len(distances)})"
                f" exceeds {_EE_DIST_STDDEV_THRESHOLD_MM}mm threshold"
            ),
            node="motion_controller",
            timestamp=0,
            message=f"ee_start_distance stddev={stddev_d:.1f}mm",
            recommendation=(
                "Investigate EE homing consistency and mechanical play"
            ),
        )

    if max_d > _EE_DIST_MAX_THRESHOLD_MM:
        analyzer._add_issue(
            severity="medium",
            category="arm",
            title="EE start distance too large",
            description=(
                f"EE start distance max={max_d:.1f}mm"
                f" exceeds {_EE_DIST_MAX_THRESHOLD_MM}mm —"
                f" EE may be starting too far from target"
            ),
            node="motion_controller",
            timestamp=0,
            message=f"ee_start_distance max={max_d:.1f}mm",
            recommendation=(
                "Check approach calibration and target distance setup"
            ),
        )

    if min_d < _EE_DIST_MIN_THRESHOLD_MM:
        analyzer._add_issue(
            severity="medium",
            category="arm",
            title="EE start distance too small",
            description=(
                f"EE start distance min={min_d:.1f}mm"
                f" is below {_EE_DIST_MIN_THRESHOLD_MM}mm —"
                f" risk of collision on approach"
            ),
            node="motion_controller",
            timestamp=0,
            message=f"ee_start_distance min={min_d:.1f}mm",
            recommendation=(
                "Check EE home position and safety margins"
            ),
        )


# ---------------------------------------------------------------------------
# task 5.1 — reset module-level mutable state between analyzer runs
# ---------------------------------------------------------------------------


def reset_parser_state() -> None:
    """Reset all module-level mutable state between analyzer runs.

    IMPORTANT: When adding new module-level state variables to this module,
    you MUST also add them to this function. Failure to do so will cause
    stale detections to leak across runs in batch analysis and test suites.
    """
    global _joint_limit_pending, _scan_pending, _homing_pending
    _joint_limit_pending = {}
    _scan_pending = {}
    _homing_pending = {}
    _camera_block_pending.clear()
    _camera_block_in_block.clear()
