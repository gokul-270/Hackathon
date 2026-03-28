"""
ROS2LogAnalyzer — main orchestrator class.

Wires together all parser, detector, system-log, report, exporter and MQTT
submodules.  The class preserves the existing public interface of the original
single-file analyzer (same __init__ signature, same analyze() return type).

Groups covered here:
  2.4  — Initialize EventStore / MQTTMetrics in __init__
  3.2  — _parse_line: call _try_parse_json_event and dispatch
  3.3  — fallback for bare [TIMING] lines (shutdown_timing via print())
  3.4  — JSONDecodeError handling → _parse_timing_text
  23.4 — MQTT pattern matching inside _parse_line
  23.9 — Wire _parse_mosquitto_log into analyze()
"""

import gzip
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .models import BuildProvenance, EventStore, FieldSummary, MQTTMetrics, NetworkMetrics

# ---------------------------------------------------------------------------
# Re-export legacy types so cli.py can import them from a single place
# ---------------------------------------------------------------------------
from .models import EventStore  # noqa: F811 (explicit re-export)

# ---------------------------------------------------------------------------
# ANSI colours (identical to original log_analyzer.py so output is unchanged)
# ---------------------------------------------------------------------------


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


# ---------------------------------------------------------------------------
# Session topology  (tasks 1.1-1.7)
# ---------------------------------------------------------------------------


class SessionTopologyMode(Enum):
    """Mode of a log session directory layout."""

    MULTI_ROLE = "MULTI_ROLE"
    SINGLE_ARM = "SINGLE_ARM"
    SINGLE_VEHICLE = "SINGLE_VEHICLE"


@dataclass
class SessionTopology:
    """Detected topology for a session log directory."""

    mode: SessionTopologyMode
    vehicle_dir: Optional[Path]
    arm_dirs: List[Path]


# ---------------------------------------------------------------------------
# Data structures carried over from the original file
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """Represents a single log entry."""

    timestamp: float
    level: str
    node: str
    message: str
    file: str
    line_number: int
    raw_line: str


@dataclass
class Issue:
    """Represents a detected issue."""

    severity: str  # critical, high, medium, low, info
    category: str
    title: str
    description: str
    occurrences: int = 1
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    affected_nodes: List[str] = field(default_factory=list)
    sample_messages: List[str] = field(default_factory=list)
    recommendation: str = ""
    subcategory: Optional[str] = None
    # task 1.8 — source file tracking for cross-file timestamp annotation
    first_seen_file: Optional[str] = None
    last_seen_file: Optional[str] = None


@dataclass
class PerformanceMetric:
    """Performance metrics from logs."""

    name: str
    values: List[float] = field(default_factory=list)
    unit: str = "ms"

    @property
    def avg(self) -> float:
        return sum(self.values) / len(self.values) if self.values else 0

    @property
    def max_val(self) -> float:
        return max(self.values) if self.values else 0

    @property
    def min_val(self) -> float:
        return min(self.values) if self.values else 0


@dataclass
class AnalysisReport:
    """Complete analysis report."""

    log_directory: str
    analysis_time: str
    total_files: int
    total_lines: int
    total_size_bytes: int
    duration_seconds: float

    # Counts by level
    level_counts: Dict[str, int] = field(default_factory=dict)

    # Issues found
    issues: List[Issue] = field(default_factory=list)

    # Per-node statistics
    node_stats: Dict[str, Dict] = field(default_factory=dict)

    # Performance metrics
    performance: Dict[str, Dict] = field(default_factory=dict)

    # Timeline of significant events
    timeline: List[Dict] = field(default_factory=list)

    # Raw errors/warnings for reference
    errors: List[Dict] = field(default_factory=list)
    warnings: List[Dict] = field(default_factory=list)

    # Truncation counts (task 1.5) — how many entries were omitted
    timeline_truncated: int = 0
    errors_truncated: int = 0
    warnings_truncated: int = 0

    # task 15.1 — per-source-category time ranges and operational duration
    source_durations: Dict[str, Dict] = field(default_factory=dict)
    operational_duration_seconds: float = 0.0

    # task 16.1 — executive summary (one-line overview of the session)
    executive_summary: str = ""

    # task 14.1 — test mode awareness
    session_mode: str = ""
    session_mode_source: str = ""


# ---------------------------------------------------------------------------
# Formatting helpers (identical to original)
# ---------------------------------------------------------------------------


def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_duration(seconds: float) -> str:
    """Human-readable duration: ``Xh Ym Zs``, zero components omitted.

    Delegates to :func:`utils.format_duration`.
    """
    from .utils import format_duration as _fmt_dur

    return _fmt_dur(seconds)


def format_timestamp(epoch: float, include_date: bool = True) -> str:
    try:
        dt = datetime.fromtimestamp(epoch)
        if include_date:
            return dt.strftime("%Y-%m-%d %H:%M:%S") + f".{int((epoch % 1) * 1000):03d}"
        else:
            return dt.strftime("%H:%M:%S") + f".{int((epoch % 1) * 1000):03d}"
    except (ValueError, OSError, OverflowError):
        return f"{epoch:.3f}"


def _file_basename(path: Optional[str]) -> str:
    """Extract basename without extension from a file path."""
    if not path:
        return ""
    return Path(path).stem


def annotate_issue_timestamps(issue: "Issue") -> None:
    """Annotate issue first_seen/last_seen with source file suffix.

    Only annotates when first_seen_file and last_seen_file differ
    (indicating different epoch bases). Modifies the issue in-place.
    """
    first_file = issue.first_seen_file
    last_file = issue.last_seen_file

    if not first_file or not last_file:
        return
    if first_file == last_file:
        return

    first_base = _file_basename(first_file)
    last_base = _file_basename(last_file)

    if first_base == last_base:
        return

    # Annotate timestamps with source file suffix
    if issue.first_seen and "[" not in issue.first_seen:
        issue.first_seen = f"{issue.first_seen} [{first_base}]"
    if issue.last_seen and "[" not in issue.last_seen:
        issue.last_seen = f"{issue.last_seen} [{last_base}]"


# ---------------------------------------------------------------------------
# Arm-id inference from filename (task 1.4)
# ---------------------------------------------------------------------------

_RE_ARM_ID_FILENAME = re.compile(r"arm_client_arm(\d+)")


def _infer_arm_id_from_filename(path: Path) -> Optional[str]:
    """Infer arm_id from log filename pattern arm_client_armN."""
    m = _RE_ARM_ID_FILENAME.search(path.stem)
    return f"arm_{m.group(1)}" if m else None


# ---------------------------------------------------------------------------
# Progress indication (task 6.3)
# ---------------------------------------------------------------------------


def _progress_tracker(total: int) -> "ProgressTracker":
    """Create a :class:`utils.ProgressTracker` for *total* files."""
    from .utils import ProgressTracker

    return ProgressTracker(total)


# ---------------------------------------------------------------------------
# ROS2LogAnalyzer
# ---------------------------------------------------------------------------


def _strip_emoji_prefix(text: str) -> str:
    """Strip leading emoji characters and whitespace from a log message.

    Production logs use emoji prefixes (🔙, 🎯, ❌, 📊, ⏱️, 📸, etc.) before
    bracket tags like [TIMING] and [EE].  Stripping once at the dispatch site
    is simpler than making 30+ regexes emoji-tolerant.
    """
    i = 0
    while i < len(text):
        cp = ord(text[i])
        # Skip whitespace
        if text[i] in " \t":
            i += 1
            continue
        # Skip characters in common emoji / symbol ranges
        if (
            cp > 0x2000  # General punctuation, symbols, dingbats, etc.
            or 0xFE00 <= cp <= 0xFE0F  # Variation selectors
            or 0x200D == cp  # Zero-width joiner
        ):
            i += 1
            continue
        break
    return text[i:]


class ROS2LogAnalyzer:
    """Main analyzer class for ROS2 logs — extended with vehicle + arm analysis."""

    # ROS2 log level pattern (unchanged from original)
    LOG_PATTERN = re.compile(
        r"\[(?P<level>DEBUG|INFO|WARN|ERROR|FATAL)\]\s*"
        r"\[(?P<timestamp>[\d.]+)\]\s*"
        r"\[(?P<node>[^\]]+)\]:\s*"
        r"(?P<message>.*)"
    )

    # Python logging format (e.g. arm_client Python logs)
    PYTHON_LOG_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
        r" \[(?P<level>\w+)\] (?P<message>.*)"
    )

    # Python logging level -> ROS2 level mapping
    _PYTHON_LEVEL_MAP = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARN",
        "ERROR": "ERROR",
        "CRITICAL": "FATAL",
    }

    # journalctl syslog prefix (strip to get inner log content)
    JOURNALCTL_PREFIX = re.compile(
        r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}" r"\s+\S+\s+\S+\[\d+\]:\s*(.*)"
    )

    # OAK-D Lite camera thermal thresholds (safe operating limit: 105°C)
    CAMERA_THERMAL_WARNING_C = 85.0  # OAK-D Lite safe to 105°C
    CAMERA_THERMAL_CRITICAL_C = 95.0  # Approaching thermal limit

    # Regex for extracting temperature values from log messages
    _RE_TEMPERATURE_VALUE = re.compile(r"(\d+\.?\d*)\s*(?:°C|C\b|degrees)", re.IGNORECASE)

    # Known issue patterns
    ISSUE_PATTERNS = [
        {
            "pattern": r"(Segmentation fault|SIGSEGV|core dumped)",
            "severity": "critical",
            "category": "crash",
            "title": "Segmentation Fault Detected",
            "recommendation": (
                "Check for null pointer dereferences, buffer overflows, or invalid memory"
                " access. Run with gdb for backtrace."
            ),
        },
        {
            "pattern": r"(killed|OOM|Out of memory|Cannot allocate)",
            "severity": "critical",
            "category": "memory",
            "title": "Out of Memory / Process Killed",
            "recommendation": (
                "Monitor memory usage, check for memory leaks, consider reducing buffer"
                " sizes or image resolution."
            ),
        },
        {
            "pattern": r"(Device disconnected|USB device removed|device not found)",
            "severity": "critical",
            "category": "hardware",
            "title": "Device Disconnected",
            "recommendation": (
                "Check USB connections, cable quality, and hub power. Consider using"
                " powered USB hub."
            ),
        },
        {
            "pattern": r"(timeout|timed out|Timeout)",
            "severity": "high",
            "category": "communication",
            "title": "Communication Timeout",
            "_handler": "_handle_timeout_pattern",
            "recommendation": (
                "Check network/serial connections, increase timeout values if"
                " appropriate, verify device responsiveness."
            ),
        },
        {
            "pattern": r"(CAN bus error|CAN timeout|motor.*error)",
            "severity": "high",
            "category": "motor",
            "title": "Motor/CAN Communication Error",
            "recommendation": (
                "Check CAN bus connections, verify motor power, check for bus collisions."
            ),
        },
        {
            "pattern": r"(transform.*extrapolat|TF.*future|lookup.*failed)",
            "severity": "high",
            "category": "tf",
            "title": "TF Transform Issues",
            "recommendation": (
                "Check clock synchronization, verify transform publishers are running,"
                " check frame rates."
            ),
        },
        {
            "pattern": r"(queue.*full|dropping.*message|message.*dropped)",
            "severity": "high",
            "category": "performance",
            "title": "Message Queue Overflow",
            "recommendation": (
                "Increase queue sizes, optimize subscriber callbacks, or reduce" " publisher rates."
            ),
        },
        {
            "pattern": r"(USB 2\.0|480Mbps)",
            "severity": "medium",
            "category": "hardware",
            "title": "USB 2.0 Speed Detected",
            "recommendation": (
                "Use USB 3.0 port for better camera performance. Check cable and port"
                " compatibility."
            ),
        },
        {
            "pattern": r"(calibration.*fail|not calibrated)",
            "severity": "medium",
            "category": "calibration",
            "title": "Calibration Issues",
            "recommendation": (
                "Run calibration procedure, check calibration files exist and are valid."
            ),
        },
        {
            "pattern": r"(service.*not available|waiting for service)",
            "severity": "medium",
            "category": "ros",
            "title": "Service Not Available",
            "recommendation": (
                "Ensure required nodes are launched, check node dependencies and launch" " order."
            ),
        },
        {
            "pattern": r"(parameter.*not.*set|using default)",
            "severity": "low",
            "category": "config",
            "title": "Using Default Parameters",
            "recommendation": ("Review and set parameters explicitly in config files if needed."),
        },
        {
            "pattern": r"(deprecated|will be removed)",
            "severity": "low",
            "category": "deprecation",
            "title": "Deprecated API Usage",
            "recommendation": "Update code to use new API before next major version.",
        },
        {
            "pattern": r"(fallback|fall back|falling back)",
            "severity": "info",
            "category": "config",
            "title": "Using Fallback Configuration",
            "recommendation": "Review if primary configuration should be fixed.",
        },
        {
            "pattern": r"(latency.*>|delay.*\d+\s*ms|slow)",
            "severity": "medium",
            "category": "performance",
            "title": "Long Cycle Duration",
            "recommendation": (
                "Profile code, check for blocking operations, consider async" " processing."
            ),
            "_handler": "_handle_latency_pattern",
        },
        {
            "pattern": r"(temperature|thermal|overheat|throttl)",
            "severity": "medium",
            "category": "thermal",
            "title": "Thermal Warning",
            "recommendation": ("Improve cooling, reduce processing load, or add heat sinks."),
            "_handler": "_handle_thermal_pattern",
        },
        {
            "pattern": r"(no.*detection|zero.*cotton|0\s+positions)",
            "severity": "info",
            "category": "detection",
            "title": "No Detections in Frame",
            "recommendation": ("Check camera view, lighting conditions, and confidence threshold."),
        },
        {
            "pattern": r"(model.*not found|blob.*not found)",
            "severity": "high",
            "category": "config",
            "title": "Model File Not Found",
            "recommendation": ("Verify model path in parameters, ensure model files are deployed."),
        },
    ]

    # Metric units map (task 1.3 — applied in _extract_performance)
    METRIC_UNITS: Dict[str, str] = {
        "fps": "fps",
        "temperature": "°C",
        "detection_confidence": "",
    }

    # Performance extraction patterns (unchanged from original)
    PERF_PATTERNS = [
        (r"detect=(\d+)ms", "detection_time"),
        (r"total=(\d+)ms", "total_processing_time"),
        (r"frame=(\d+)ms", "frame_time"),
        (r"(\d+)\s*FPS", "fps"),
        (r"latency[:\s]*(\d+\.?\d*)\s*ms", "latency"),
        (r"temperature[:\s]*(\d+\.?\d*)", "temperature"),
        (r"approach=(\d+)ms", "approach_time"),
        (r"capture=(\d+)ms", "capture_time"),
        (r"retreat=(\d+)ms", "retreat_time"),
        (r"delay=(\d+)ms", "inter_pick_delay"),
        (r"J3=(\d+)ms", "j3_time"),
        (r"J4=(\d+)ms", "j4_time"),
        (r"J5=(\d+)ms", "j5_time"),
        (r"EE_off=(\d+)ms", "ee_off_time"),
        (r"conf=(\d+\.?\d*)", "detection_confidence"),
        (r"detection_age=(\d+)ms", "detection_age"),
        (r"ee_on=(\d+)ms", "ee_on_time"),
    ]

    def __init__(self, log_dir: str, verbose: bool = False):
        self.log_dir = Path(log_dir)
        self.verbose = verbose

        # Configurable output limits (task 1.4)
        self.max_timeline: int = 200
        self.max_errors: int = 500
        self.max_warnings: int = 500

        # Legacy fields (unchanged public interface)
        self.entries: List[LogEntry] = []
        self.issues: Dict[str, Issue] = {}
        self.performance: Dict[str, PerformanceMetric] = {}
        self.node_stats: Dict[str, Dict] = defaultdict(
            lambda: {"total": 0, "debug": 0, "info": 0, "warn": 0, "error": 0, "fatal": 0}
        )
        self.level_counts = defaultdict(int)
        self.total_lines = 0
        self.total_size = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        # Per-file time ranges for accurate duration (avoids cross-file
        # timezone/epoch mismatches, e.g. ARM_client Python logs vs ROS2 logs)
        self._file_time_ranges: Dict[str, list] = {}  # file -> [min_ts, max_ts]

        # task 15.1 — per-source-category time ranges for session duration accuracy
        # Maps source category to [min_ts, max_ts]
        self._source_category_ranges: Dict[str, list] = {}  # category -> [min_ts, max_ts]

        # task 2.4 — new structured event storage
        self.events: EventStore = EventStore()

        # task 23.4 — MQTT metrics storage
        self.mqtt: MQTTMetrics = MQTTMetrics()

        # Network metrics (populated by system_logs._parse_network_monitor)
        self.network: NetworkMetrics = NetworkMetrics()

        # Field summary (populated on demand by reports._generate_field_summary)
        self.field_summary: Optional[FieldSummary] = None

        # task 2.1 — build provenance data (populated in analyze())
        self.build_provenances: List[BuildProvenance] = []

        # task 2.3 — stale binary detection threshold (set from CLI)
        self.stale_threshold_hours: float = 1.0

        # Incremented when [TIMING] text lines fail JSON parse and have no
        # matching arm text pattern (truly unrecognised)
        self._json_skip_count: int = 0

        # task 8.3 — detector filter (set from CLI --filter detector:name)
        self.detector_filter: Optional[set] = None

        # task 2.1 — arm_id for current file being parsed (set per file in MULTI_ROLE)
        self._current_arm_id: Optional[str] = None

        # task 1.1 — session topology (set during analyze())
        self.topology: Optional[SessionTopology] = None

        # task 14.1 — test mode override (set from CLI --mode flag)
        self.session_mode: Optional[str] = None

    def _detector_enabled(self, name: str) -> bool:
        """Return True if detector *name* should run given the active filter."""
        if self.detector_filter is None:
            return True
        return name in self.detector_filter

    def _detect_session_mode(self) -> tuple:
        """task 14.1 — Detect session mode from log content.

        Returns (mode, source) where mode is "bench", "field", or
        "integration" and source is "auto" or "user".

        If ``self.session_mode`` was set via the CLI ``--mode`` flag the
        user-provided value is returned directly.  Otherwise the mode is
        inferred from log content:
          - Has vehicle data: topology is MULTI_ROLE / SINGLE_VEHICLE,
            or state_transitions / drive_commands are non-empty.
          - Has MQTT data: arm_client_mqtt_events are non-empty, or
            broker-side connects exist in ``self.mqtt``.
          - bench: no vehicle AND no MQTT
          - field: vehicle AND MQTT
          - integration: one but not the other (mixed signals)
        """
        if self.session_mode is not None:
            return (self.session_mode, "user")

        has_vehicle = False
        if self.topology and self.topology.mode in (
            SessionTopologyMode.MULTI_ROLE,
            SessionTopologyMode.SINGLE_VEHICLE,
        ):
            has_vehicle = True
        if self.events.state_transitions or self.events.drive_commands:
            has_vehicle = True

        has_mqtt = bool(
            self.events.arm_client_mqtt_events or self.mqtt.connects or self.mqtt.broker_connects
        )

        if has_vehicle and has_mqtt:
            mode = "field"
        elif not has_vehicle and not has_mqtt:
            mode = "bench"
        else:
            mode = "integration"

        return (mode, "auto")

    # -----------------------------------------------------------------------
    # Public entry-point
    # -----------------------------------------------------------------------

    def analyze(self) -> "AnalysisReport":
        """Run full analysis on log directory."""
        from . import parser as _parser
        from . import arm_patterns as _arm
        from . import mqtt as _mqtt
        from . import detectors as _det
        from . import system_logs as _sys
        from .arm_patterns import reset_parser_state

        # task 5.2 — reset module-level mutable state between runs
        reset_parser_state()

        # task 1.3 — detect topology and branch
        self.topology = self._detect_topology(self.log_dir)
        total_files_count = 0

        if self.topology.mode == SessionTopologyMode.MULTI_ROLE:
            # task 1.6 — collect files per role dir with arm_id
            role_files: List[tuple] = []  # (path, arm_id)
            for arm_dir in self.topology.arm_dirs:
                for f in self._find_log_files_in(arm_dir):
                    role_files.append((f, arm_dir.name))
            if self.topology.vehicle_dir:
                for f in self._find_log_files_in(self.topology.vehicle_dir):
                    role_files.append((f, "vehicle"))

            if not role_files:
                print(f"{Colors.RED}No log files found in {self.log_dir}{Colors.RESET}")
                sys.exit(1)

            total_files_count = len(role_files)
            progress = _progress_tracker(total_files_count)
            for log_file, arm_id in role_files:
                self._parse_log_file(log_file, arm_id=arm_id)
                progress.update()
            progress.finish()

            # task 1.7 — resolve vehicle log paths from vehicle_dir in MULTI_ROLE
            vehicle_base = self.topology.vehicle_dir or self.log_dir
            _mqtt.parse_mosquitto_log(self, vehicle_base / "mosquitto_broker.log")
            _sys.parse_dmesg_log(self, vehicle_base / "dmesg_network.log")
            _sys.parse_network_monitor(self, vehicle_base / "network_monitor.log")
            # task 13.2 — parse launch.log from vehicle_dir in MULTI_ROLE
            self._parse_launch_log(vehicle_base / "launch.log")
            # task 12.1 — also discover launch_*.log files
            for lf in sorted(vehicle_base.glob("launch_*.log")):
                self._parse_launch_log(lf)
        else:
            # Single-role path (SINGLE_ARM or SINGLE_VEHICLE) — unchanged behaviour
            log_files = self._find_log_files()

            if not log_files:
                print(f"{Colors.RED}No log files found in {self.log_dir}{Colors.RESET}")
                sys.exit(1)

            total_files_count = len(log_files)
            progress = _progress_tracker(total_files_count)
            for log_file in log_files:
                self._parse_log_file(log_file)
                progress.update()
            progress.finish()

            # task 23.9 — parse mosquitto_broker.log (vehicle role only, skip if absent)
            _mqtt.parse_mosquitto_log(self, self.log_dir / "mosquitto_broker.log")

            # System-log parsers (group 15)
            _sys.parse_dmesg_log(self, self.log_dir / "dmesg_network.log")
            _sys.parse_network_monitor(self, self.log_dir / "network_monitor.log")
            # task 13.2 — parse launch.log in single-role mode
            self._parse_launch_log(self.log_dir / "launch.log")
            # task 12.1 — also discover launch_*.log files
            for lf in sorted(self.log_dir.glob("launch_*.log")):
                self._parse_launch_log(lf)

        # task 19.1 — flush any incomplete homing record after all parsing completes
        from . import arm_patterns as _arm_flush

        _arm_flush._flush_pending_homing(self)

        # task 14.1 — detect session mode after parsing, before detectors
        self._session_mode, self._session_mode_source = self._detect_session_mode()

        # tasks 2.3-2.4 — build provenance extraction and issue detection
        from .detectors.build_provenance import (
            detect_dirty_builds,
            detect_stale_builds,
            extract_build_provenance,
        )

        if self._detector_enabled("extract_build_provenance"):
            self.build_provenances = extract_build_provenance(
                self.entries,
                self.node_stats,
            )
        if self._detector_enabled("detect_stale_builds"):
            for issue in detect_stale_builds(
                self.build_provenances,
                self.stale_threshold_hours,
            ):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue["node"],
                    timestamp=issue["timestamp"],
                    message=issue["message"],
                    recommendation=issue["recommendation"],
                )
        if self._detector_enabled("detect_dirty_builds"):
            for issue in detect_dirty_builds(self.build_provenances):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue["node"],
                    timestamp=issue["timestamp"],
                    message=issue["message"],
                    recommendation=issue["recommendation"],
                )

        # task 4.12 — camera thermal trending
        from .detectors.camera_thermal import (
            analyze_camera_thermal,
            detect_confidence_discrepancy,
        )

        if self._detector_enabled("analyze_camera_thermal"):
            thermal_result = analyze_camera_thermal(self.events)
            for issue in thermal_result.get("issues", []):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue["node"],
                    timestamp=issue["timestamp"],
                    message=issue["message"],
                    recommendation=issue["recommendation"],
                )
        else:
            thermal_result = {}

        # task 4.14 — confidence threshold discrepancy
        if self._detector_enabled("detect_confidence_discrepancy"):
            for issue in detect_confidence_discrepancy(self):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue["node"],
                    timestamp=issue["timestamp"],
                    message=issue["message"],
                    recommendation=issue["recommendation"],
                )

        # task 4.17 — motor current draw analysis
        from .detectors.motor_current import (
            analyze_motor_current,
            detect_cross_joint_current_anomalies,
        )

        if self._detector_enabled("analyze_motor_current"):
            current_result = analyze_motor_current(self.events)
            for issue in current_result.get("issues", []):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue["node"],
                    timestamp=issue["timestamp"],
                    message=issue["message"],
                    recommendation=issue["recommendation"],
                )
        else:
            current_result = {}

        # Cross-joint current comparison (task 4.2)
        if self._detector_enabled("detect_cross_joint_current_anomalies"):
            for issue in detect_cross_joint_current_anomalies(current_result):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue["node"],
                    timestamp=issue["timestamp"],
                    message=issue["message"],
                    recommendation=issue["recommendation"],
                )

        # tasks 4.1, 4.3, 4.15 — motor position trending
        from .detectors.motor_trending import analyze_motor_trending

        if self._detector_enabled("analyze_motor_trending"):
            joint_tolerances = getattr(self, "joint_tolerances", None)
            if joint_tolerances is not None:
                trending_result = analyze_motor_trending(
                    self.events,
                    joint_tolerances=joint_tolerances,
                )
            else:
                trending_result = analyze_motor_trending(self.events)
            self._motor_trending_result = trending_result
            for issue in trending_result.get("issues", []):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue["node"],
                    timestamp=issue["timestamp"],
                    message=issue["message"],
                    recommendation=issue["recommendation"],
                )
        else:
            trending_result = {}

        # Position-error to current-draw correlation (task 4.3)
        self._correlate_motor_data(current_result, trending_result)

        # Issue detection
        self._detect_issues()

        # Vehicle-specific issue detection (group 10)
        if self._detector_enabled("detect_vehicle_issues"):
            _det.detect_vehicle_issues(self)

        # Arm JSON issue detection (group 11)
        if self._detector_enabled("detect_arm_json_issues"):
            _det.detect_arm_json_issues(self)

        # Arm text-pattern issue detection (task 22.12)
        _arm.detect_arm_text_issues(self)

        # ARM_client pattern-based issue detection
        if self._detector_enabled("generate_arm_client_issues"):
            from .detectors.arm import generate_arm_client_issues

            for issue in generate_arm_client_issues(self.events):
                self._add_issue(
                    severity=issue.get("severity", "MEDIUM").lower(),
                    category=issue.get("category", "arm_client").lower(),
                    title=issue.get("description", "ARM_client issue"),
                    description=issue.get("description", ""),
                    node="arm_client",
                    timestamp=0,
                    message=issue.get("description", ""),
                )

        # MQTT issue detection (task 23.6)
        _mqtt.detect_mqtt_issues(self)

        # Motor-command cross-correlation (task 11.4)
        if self._detector_enabled("correlate_motor_commands_with_picking"):
            for issue in _det.correlate_motor_commands_with_picking(self.events):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue.get("node", "arm_control"),
                    timestamp=issue.get("timestamp", 0),
                    message=issue["message"],
                    recommendation=issue.get("recommendation", ""),
                )

        # Launch crash detection (task 13.4)
        if self._detector_enabled("detect_launch_crashes"):
            _det.detect_launch_crashes(self)

        # New field diagnostics detectors (tasks 14-21)
        if self._detector_enabled("detect_ee_timeout_rate"):
            for issue in _det.detect_ee_timeout_rate(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_stale_detection_rate"):
            for issue in _det.detect_stale_detection_rate(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_joint_limit_pattern"):
            for issue in _det.detect_joint_limit_pattern(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_camera_frame_wait_degradation"):
            for issue in _det.detect_camera_frame_wait_degradation(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_scan_dead_zones"):
            for issue in _det.detect_scan_dead_zones(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_homing_failures"):
            for issue in _det.detect_homing_failures(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_compressor_dominance"):
            for issue in _det.detect_compressor_dominance(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_border_skip_rate"):
            for issue in _det.detect_border_skip_rate(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_high_frame_drop_rate"):
            for issue in _det.detect_high_frame_drop_rate(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_high_detection_age"):
            for issue in _det.detect_high_detection_age(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})
        if self._detector_enabled("detect_low_cache_hit_rate"):
            for issue in _det.detect_low_cache_hit_rate(self.events):
                self._add_issue(**{k: v for k, v in issue.items() if k != "arm_id"})

        # Zero-timing cross-reference (task 13.1) — run BEFORE
        # detect_zero_joint_movement so the more-informative cross-reference
        # finding suppresses the duplicate generic finding.
        self._check_zero_timing()
        _zero_timing_key = "instrumentation:JSON pick timing zeroed but text logs show motion"

        # Zero-joint-movement detection (production-log-fixes task 5.2)
        # Suppressed when _check_zero_timing already identified the same
        # root cause with better diagnostic evidence.
        if (
            self._detector_enabled("detect_zero_joint_movement")
            and _zero_timing_key not in self.issues
        ):
            _add_issue_keys = {
                "severity",
                "category",
                "title",
                "description",
                "node",
                "timestamp",
                "message",
                "recommendation",
            }
            for issue in _det.detect_zero_joint_movement(
                self.events,
                verbose=self.verbose,
            ):
                self._add_issue(**{k: v for k, v in issue.items() if k in _add_issue_keys})

        # Cross-correlation (groups 12-13)
        if self._detector_enabled("correlate_picks_with_vehicle_state"):
            _det.correlate_picks_with_vehicle_state(self)
        if self._detector_enabled("detect_failure_chains"):
            _det.detect_failure_chains(self)

        # Session health (group 14)
        if self._detector_enabled("analyze_session_health"):
            _det.analyze_session_health(self)

        # Session lifecycle analysis (task 12.2-12.5)
        if self._detector_enabled("analyze_session_lifecycle"):
            from .detectors.session_lifecycle import analyze_session_lifecycle

            lifecycle_result = analyze_session_lifecycle(self)
            for issue in lifecycle_result.get("issues", []):
                self._add_issue(
                    severity=issue["severity"],
                    category=issue["category"],
                    title=issue["title"],
                    description=issue["description"],
                    node=issue.get("node", "launch"),
                    timestamp=issue.get("timestamp", 0),
                    message=issue.get("message", ""),
                    recommendation=issue.get("recommendation", ""),
                )

        # Cross-log correlation (post-parse pass, tasks 4.1-4.5)
        if self._detector_enabled("detect_cross_log_correlations"):
            for issue in _det.detect_cross_log_correlations(self):
                self._add_issue(
                    severity=issue["severity"].lower(),
                    category=issue["category"].lower(),
                    title=issue["title"],
                    description=issue["description"],
                    node=issue.get("node", "correlation"),
                    timestamp=issue.get("timestamp", 0),
                    message=issue.get("description", ""),
                    recommendation=issue.get("recommendation", ""),
                )

        # task 1.7 — deduplicate issues after all detectors complete
        # task 11.3 — skip dedup when --no-dedup flag is set
        if not getattr(self, "skip_dedup", False):
            if self._detector_enabled("deduplicate_issues"):
                self.issues = _det.deduplicate_issues(self.issues)

        # task 1.8 — annotate timestamps with source file when epoch bases differ
        for issue in self.issues.values():
            annotate_issue_timestamps(issue)

        # Build timeline (existing logic unchanged)
        timeline, timeline_truncated = self._build_timeline()

        # Calculate duration using per-file time ranges to avoid cross-file
        # timezone/epoch mismatch.  Group files by parent directory (session
        # subdirectory) so that multi-session directories sum each session's
        # wall-clock span instead of reporting only the longest single file.
        duration = 0.0
        if self._file_time_ranges:
            groups: Dict[str, list] = defaultdict(list)
            for fpath, (lo, hi) in self._file_time_ranges.items():
                parent = str(Path(fpath).parent)
                groups[parent].append((lo, hi))
            duration = sum(
                max(h for _, h in spans) - min(l for l, _ in spans) for spans in groups.values()
            )

        # Prepare errors and warnings (task 1.4 — configurable limits)
        all_errors = [
            {
                "timestamp": e.timestamp,
                "timestamp_human": format_timestamp(e.timestamp),
                "node": e.node,
                "message": e.message[:500],
                "file": e.file,
            }
            for e in self.entries
            if e.level == "ERROR"
        ]
        errors = all_errors if self.max_errors == 0 else all_errors[: self.max_errors]
        errors_truncated = max(0, len(all_errors) - len(errors))

        all_warnings = [
            {
                "timestamp": e.timestamp,
                "timestamp_human": format_timestamp(e.timestamp),
                "node": e.node,
                "message": e.message[:500],
                "file": e.file,
            }
            for e in self.entries
            if e.level == "WARN"
        ]
        warnings = all_warnings if self.max_warnings == 0 else all_warnings[: self.max_warnings]
        warnings_truncated = max(0, len(all_warnings) - len(warnings))

        report = AnalysisReport(
            log_directory=str(self.log_dir),
            analysis_time=datetime.now().isoformat(),
            total_files=total_files_count,
            total_lines=self.total_lines,
            total_size_bytes=self.total_size,
            duration_seconds=duration,
            level_counts=dict(self.level_counts),
            issues=list(self.issues.values()),
            node_stats=dict(self.node_stats),
            performance={
                name: {
                    "avg": m.avg,
                    "min": m.min_val,
                    "max": m.max_val,
                    "samples": len(m.values),
                    "unit": m.unit,
                }
                for name, m in self.performance.items()
            },
            timeline=timeline,
            errors=errors,
            warnings=warnings,
            timeline_truncated=timeline_truncated,
            errors_truncated=errors_truncated,
            warnings_truncated=warnings_truncated,
        )

        # task 15.1 — build source_durations from per-category time ranges
        source_durations: Dict[str, Dict] = {}
        for cat, (lo, hi) in self._source_category_ranges.items():
            source_durations[cat] = {"start": lo, "end": hi}
        report.source_durations = source_durations

        # Compute operational duration from ROS2 source window (primary)
        if "ros2" in source_durations:
            report.operational_duration_seconds = (
                source_durations["ros2"]["end"] - source_durations["ros2"]["start"]
            )
        else:
            report.operational_duration_seconds = duration

        # task 16.1 — compute executive summary after all analysis
        report.executive_summary = self._compute_executive_summary(report)

        # task 14.1 — set session mode on report
        report.session_mode = self._session_mode
        report.session_mode_source = self._session_mode_source

        return report

    # -----------------------------------------------------------------------
    # File discovery
    # -----------------------------------------------------------------------

    def _detect_topology(self, path: Path) -> "SessionTopology":
        """task 1.2 — inspect directory to detect session layout.

        Detection order:
          1. File path → SINGLE_ARM legacy (direct file analysis)
          2. Subdirs matching arm_[0-9]+ or named 'vehicle' → MULTI_ROLE
             - Degenerate: arm_dirs=[] (vehicle-only) → SINGLE_VEHICLE
          3. arm_client.log / yanthra_move.log directly present → SINGLE_ARM
          4. vehicle_control.log / mosquitto_broker.log directly present → SINGLE_VEHICLE
          5. Fallback → SINGLE_ARM legacy
        """
        if path.is_file():
            return SessionTopology(
                mode=SessionTopologyMode.SINGLE_ARM,
                vehicle_dir=None,
                arm_dirs=[],
            )

        import re as _re

        # Match arm_0, arm_1, ... AND named dirs like left_arm, right_arm
        arm_pattern = _re.compile(r"^(arm_[0-9]+|[a-z]+_arm)$")
        subdirs = [d for d in path.iterdir() if d.is_dir()]
        arm_dirs = sorted([d for d in subdirs if arm_pattern.match(d.name)])
        vehicle_dir = next((d for d in subdirs if d.name == "vehicle"), None)

        if arm_dirs or vehicle_dir:
            if not arm_dirs:
                # vehicle-only layout → treat as SINGLE_VEHICLE
                return SessionTopology(
                    mode=SessionTopologyMode.SINGLE_VEHICLE,
                    vehicle_dir=vehicle_dir,
                    arm_dirs=[],
                )
            return SessionTopology(
                mode=SessionTopologyMode.MULTI_ROLE,
                vehicle_dir=vehicle_dir,
                arm_dirs=arm_dirs,
            )

        # Check for direct log files indicating role
        direct_files = {f.name for f in path.iterdir() if f.is_file()}
        if direct_files & {"arm_client.log", "yanthra_move.log"}:
            return SessionTopology(
                mode=SessionTopologyMode.SINGLE_ARM,
                vehicle_dir=None,
                arm_dirs=[],
            )
        if direct_files & {"vehicle_control.log", "mosquitto_broker.log"}:
            return SessionTopology(
                mode=SessionTopologyMode.SINGLE_VEHICLE,
                vehicle_dir=None,
                arm_dirs=[],
            )

        # Fallback
        return SessionTopology(
            mode=SessionTopologyMode.SINGLE_ARM,
            vehicle_dir=None,
            arm_dirs=[],
        )

    def _find_log_files(self) -> List[Path]:
        """Find log files in self.log_dir (single-role path)."""
        return self._find_log_files_in(self.log_dir)

    def _find_log_files_in(self, directory: Path) -> List[Path]:
        """task 1.6 — find log files in an explicit directory (recursive)."""
        if directory.is_file():
            return [directory]
        log_files = []
        for pattern in ["*.log", "*.log.gz"]:
            log_files.extend(directory.rglob(pattern))
        return sorted(log_files)

    # -----------------------------------------------------------------------
    # Source classification (task 15.1)
    # -----------------------------------------------------------------------

    _RE_ARM_CLIENT_FILE = re.compile(r"ARM_client|arm_client", re.IGNORECASE)
    _RE_LAUNCH_LOG_FILE = re.compile(r"^launch(?:_\w+)?\.log$")

    def _classify_source(self, filepath: Path) -> str:
        """Classify a log file into a source category.

        Categories:
          - "arm_client" : ARM_client_*.log files
          - "launch"     : launch.log or launch_*.log
          - "dmesg"      : dmesg files
          - "ros2"       : files with ROS2 log format (default for .log files)
        """
        name = filepath.name
        if self._RE_ARM_CLIENT_FILE.search(name):
            return "arm_client"
        if self._RE_LAUNCH_LOG_FILE.match(name):
            return "launch"
        if "dmesg" in name.lower():
            return "dmesg"
        return "ros2"

    def _record_source_timestamp(self, filepath: Path, timestamp: float) -> None:
        """Record a timestamp for source category tracking."""
        category = self._classify_source(filepath)
        if category in self._source_category_ranges:
            rng = self._source_category_ranges[category]
            if timestamp < rng[0]:
                rng[0] = timestamp
            if timestamp > rng[1]:
                rng[1] = timestamp
        else:
            self._source_category_ranges[category] = [timestamp, timestamp]

    # -----------------------------------------------------------------------
    # File parsing
    # -----------------------------------------------------------------------

    def _parse_log_file(self, log_file: Path, arm_id: Optional[str] = None) -> None:
        """task 2.2 — parse a single log file; set _current_arm_id for arm_id injection."""
        # Directory-based arm_id takes precedence; fall back to filename inference
        if arm_id is None:
            arm_id = _infer_arm_id_from_filename(log_file)
        self._current_arm_id = arm_id
        self.total_size += log_file.stat().st_size
        open_func = gzip.open if log_file.suffix == ".gz" else open
        mode = "rt" if log_file.suffix == ".gz" else "r"
        try:
            with open_func(log_file, mode, errors="replace") as fh:
                for line_num, line in enumerate(fh, 1):
                    self.total_lines += 1
                    self._parse_line(str(line), str(log_file), line_num)
        except Exception as exc:
            print(f"{Colors.YELLOW}Warning: Could not parse {log_file}: {exc}{Colors.RESET}")

    # -----------------------------------------------------------------------
    # Line parsing  (tasks 3.2, 3.3, 3.4, 23.4)
    # -----------------------------------------------------------------------

    def _parse_line(
        self, line: str, file: str, line_num: int, _from_journalctl: bool = False
    ) -> None:
        from . import parser as _parser
        from . import arm_patterns as _arm
        from . import mqtt as _mqtt

        line = line.strip()
        if not line:
            return

        match = self.LOG_PATTERN.match(line)
        if match:
            level = match.group("level")
            timestamp = float(match.group("timestamp"))
            node = match.group("node")
            message = match.group("message")

            self._dispatch_parsed_line(
                level,
                timestamp,
                node,
                message,
                file,
                line_num,
                line,
                _parser,
                _arm,
                _mqtt,
            )
            return

        # task 1.1 — try Python logging format
        py_match = self.PYTHON_LOG_PATTERN.match(line)
        if py_match:
            ts_str = py_match.group("timestamp")
            timestamp = datetime.strptime(
                ts_str.replace(",", "."), "%Y-%m-%d %H:%M:%S.%f"
            ).timestamp()
            raw_level = py_match.group("level").upper()
            level = self._PYTHON_LEVEL_MAP.get(raw_level, "INFO")
            message = py_match.group("message")
            node = "arm_client"

            self._dispatch_parsed_line(
                level,
                timestamp,
                node,
                message,
                file,
                line_num,
                line,
                _parser,
                _arm,
                _mqtt,
            )
            return

        # task 1.2 — try journalctl syslog prefix (strip and retry)
        if not _from_journalctl:
            jctl_match = self.JOURNALCTL_PREFIX.match(line)
            if jctl_match:
                inner = jctl_match.group(1)
                if inner:
                    self._parse_line(inner, file, line_num, _from_journalctl=True)
                return

        # Fall through to bare text handling
        # task 3.3 — handle bare [TIMING] lines (shutdown_timing via print())
        if line.startswith("[TIMING]"):
            try:
                payload = line[len("[TIMING]") :].strip()
                data = json.loads(payload)
                if isinstance(data, dict) and "event" in data:
                    from . import parser as _p

                    _p.handle_json_event(self, data, None, None)
                    return
            except json.JSONDecodeError:
                pass
            # Non-JSON bare [TIMING] line — try arm text patterns
            from . import arm_patterns as _arm2

            _arm2.parse_timing_text(self, line, None)

        else:
            # Bare line that doesn't start with [TIMING] — might still
            # contain arm events with emoji prefixes or other text patterns
            stripped = _strip_emoji_prefix(line)
            if stripped:
                from . import arm_patterns as _arm3

                _arm3.parse_timing_text(self, stripped, None)

    def _dispatch_parsed_line(
        self,
        level,
        timestamp,
        node,
        message,
        file,
        line_num,
        raw_line,
        _parser,
        _arm,
        _mqtt,
    ) -> None:
        """Common dispatch logic for a successfully parsed log line."""
        entry = LogEntry(
            timestamp=timestamp,
            level=level,
            node=node,
            message=message,
            file=file,
            line_number=line_num,
            raw_line=raw_line,
        )
        self.entries.append(entry)
        self.level_counts[level] += 1
        self.node_stats[node][level.lower()] += 1
        self.node_stats[node]["total"] += 1

        # Track time range (global — for backward compat)
        if self.start_time is None or timestamp < self.start_time:
            self.start_time = timestamp
        if self.end_time is None or timestamp > self.end_time:
            self.end_time = timestamp

        # Track per-file time range (avoids cross-file epoch mismatch)
        if file in self._file_time_ranges:
            ftr = self._file_time_ranges[file]
            if timestamp < ftr[0]:
                ftr[0] = timestamp
            if timestamp > ftr[1]:
                ftr[1] = timestamp
        else:
            self._file_time_ranges[file] = [timestamp, timestamp]

        # task 15.1 — track per-source-category time range
        self._record_source_timestamp(Path(file), timestamp)

        # Extract legacy performance metrics
        self._extract_performance(message)

        # task 3.2 — try JSON event dispatch
        try:
            event = _parser.try_parse_json_event(message)
            if event is not None:
                _parser.handle_json_event(self, event, timestamp, node)
                return  # JSON handled — skip MQTT and arm text
        except json.JSONDecodeError:
            # task 3.4 — [TIMING] line that is not JSON → try arm text patterns
            _arm.parse_timing_text(self, message, timestamp)
            return

        # task 23.4 — check MQTT patterns on the message
        for pattern, event_type in _mqtt.MQTT_PATTERNS:
            m = pattern.search(message)
            if m:
                _mqtt.handle_mqtt_event(self, event_type, m, timestamp)
                break

        # task 20.4 — track ArUco mentions
        if "aruco" in message.lower():
            self.events.aruco_mention_count += 1

        # Catch-all: route unhandled text lines through arm text patterns.
        # Lines with emoji prefixes or non-[TIMING] arm events (e.g. [EE],
        # joint limit, camera stats) previously fell through without being
        # parsed.  parse_timing_text() uses targeted regexes and will
        # short-circuit on non-matching lines.
        stripped = _strip_emoji_prefix(message)
        _arm.parse_timing_text(self, stripped, timestamp)

        # Route ARM_client lines through ARM_client pattern detector
        if node == "arm_client":
            from .detectors.arm import check_arm_client_line

            check_arm_client_line(
                message,
                timestamp,
                self._current_arm_id or "unknown",
                self.events,
            )

    # -----------------------------------------------------------------------
    # Performance extraction (task 1.4 — applies METRIC_UNITS)
    # -----------------------------------------------------------------------

    def _extract_performance(self, message: str) -> None:
        for pattern, metric_name in self.PERF_PATTERNS:
            m = re.search(pattern, message, re.IGNORECASE)
            if m:
                try:
                    value = float(m.group(1))
                    if metric_name not in self.performance:
                        unit = self.METRIC_UNITS.get(metric_name, "ms")
                        self.performance[metric_name] = PerformanceMetric(
                            name=metric_name, unit=unit
                        )
                    self.performance[metric_name].values.append(value)
                except ValueError:
                    pass

    # -----------------------------------------------------------------------
    # Issue detection (legacy patterns — unchanged)
    # -----------------------------------------------------------------------

    def _detect_issues(self) -> None:
        for entry in self.entries:
            if entry.level in ("ERROR", "FATAL"):
                self._add_issue(
                    severity="high" if entry.level == "ERROR" else "critical",
                    category="error",
                    title=f"{entry.level} in {entry.node}",
                    description=entry.message[:200],
                    node=entry.node,
                    timestamp=entry.timestamp,
                    message=entry.message,
                    source_file=entry.file,
                )
            for issue_def in self.ISSUE_PATTERNS:
                if re.search(issue_def["pattern"], entry.message, re.IGNORECASE):
                    handler_name = issue_def.get("_handler")
                    if handler_name:
                        handler = getattr(self, handler_name)
                        handler(entry, issue_def)
                    else:
                        self._add_issue(
                            severity=issue_def["severity"],
                            category=issue_def["category"],
                            title=issue_def["title"],
                            description=entry.message[:200],
                            node=entry.node,
                            timestamp=entry.timestamp,
                            message=entry.message,
                            recommendation=issue_def.get("recommendation", ""),
                            source_file=entry.file,
                        )

    def _handle_thermal_pattern(self, entry: "LogEntry", issue_def: dict) -> None:
        """Temperature-aware thermal detection for OAK-D Lite cameras.

        Below CAMERA_THERMAL_WARNING_C (85°C): suppress (log in verbose mode).
        85-94°C: MEDIUM severity.
        95°C+: HIGH severity.
        Non-camera thermal messages (no extractable temp): default MEDIUM.
        """
        temp_match = self._RE_TEMPERATURE_VALUE.search(entry.message)
        if temp_match:
            temp_c = float(temp_match.group(1))
            if temp_c < self.CAMERA_THERMAL_WARNING_C:
                # Normal operating temperature — suppress
                if self.verbose:
                    self.events.suppressed_findings.append(
                        {
                            "type": "thermal_below_threshold",
                            "temp_c": temp_c,
                            "threshold_c": self.CAMERA_THERMAL_WARNING_C,
                            "message": entry.message[:200],
                            "node": entry.node,
                            "timestamp": entry.timestamp,
                            "reason": (
                                f"Temperature {temp_c:.1f}°C is within normal"
                                f" range (OAK-D Lite safe to 105°C)"
                            ),
                        }
                    )
                return
            elif temp_c < self.CAMERA_THERMAL_CRITICAL_C:
                severity = "medium"
                desc = (
                    f"Camera temperature {temp_c:.1f}°C exceeds warning"
                    f" threshold {self.CAMERA_THERMAL_WARNING_C}°C"
                    f" (OAK-D Lite safe to 105°C)"
                )
            else:
                severity = "high"
                desc = (
                    f"Camera temperature {temp_c:.1f}°C approaching"
                    f" thermal limit"
                    f" (OAK-D Lite safe to 105°C)"
                )
            self._add_issue(
                severity=severity,
                category=issue_def["category"],
                title=issue_def["title"],
                description=desc,
                node=entry.node,
                timestamp=entry.timestamp,
                message=entry.message,
                recommendation=issue_def.get("recommendation", ""),
            )
        else:
            # No extractable temperature — use default severity
            self._add_issue(
                severity=issue_def["severity"],
                category=issue_def["category"],
                title=issue_def["title"],
                description=entry.message[:200],
                node=entry.node,
                timestamp=entry.timestamp,
                message=entry.message,
                recommendation=issue_def.get("recommendation", ""),
            )

    # Pick-cycle related keywords for latency reclassification
    _PICK_CYCLE_KEYWORDS = re.compile(
        r"(pick|cycle|approach|retreat|j[345]|ee_on|ee_off)",
        re.IGNORECASE,
    )

    # Timeout subcategory classification patterns
    _TIMEOUT_MQTT_RE = re.compile(
        r"mqtt",
        re.IGNORECASE,
    )
    _TIMEOUT_SERVICE_RE = re.compile(
        r"(service|discovery|endpoint|waiting\s+for\s+service)",
        re.IGNORECASE,
    )
    _TIMEOUT_SENSOR_RE = re.compile(
        r"(sensor|camera|imu|oak|frame|image|depth)",
        re.IGNORECASE,
    )
    # Skip log lines where "timeout" appears as a data field value,
    # config parameter, or counter rather than an actual timeout event.
    # Matches: "timeout":0, timeout=30s, 0 timeout, (no timeout),
    #          _timeouts=0/3, _timeout=
    _NON_EVENT_TIMEOUT_RE = re.compile(
        r'("timeout"\s*:\s*\d'  # JSON field "timeout":0
        r"|_timeouts?="  # field names like det_timeouts=
        r"|\btimeout\s*=\s*[\d.]"  # config params timeout=30
        r"|\d+\s+timeout\s*\|"  # stats counters "0 timeout |"
        r"|\(no\s+timeout\)"  # explicit "no timeout"
        r")",
        re.IGNORECASE,
    )

    def _handle_timeout_pattern(self, entry: "LogEntry", issue_def: dict) -> None:
        """Classify timeout issues into subcategories based on log message.

        Subcategories:
          mqtt_timeout             — MQTT broker/network timeouts
          service_discovery_timeout — ROS2 service/endpoint discovery
          sensor_timeout           — camera/IMU/sensor wait timeouts
          general_timeout          — anything else
        """
        msg = entry.message

        # Skip lines where "timeout" is a data value, not an event
        if self._NON_EVENT_TIMEOUT_RE.search(msg):
            return

        if self._TIMEOUT_MQTT_RE.search(msg):
            subcategory = "mqtt_timeout"
            title = "MQTT Timeout"
            recommendation = (
                "Check MQTT broker connectivity, verify network between arms,"
                " increase MQTT keepalive/timeout settings."
            )
        elif self._TIMEOUT_SERVICE_RE.search(msg):
            subcategory = "service_discovery_timeout"
            title = "Service Discovery Timeout"
            recommendation = (
                "Check ROS2 daemon status, verify DDS discovery settings,"
                " ensure service nodes are running."
            )
        elif self._TIMEOUT_SENSOR_RE.search(msg):
            subcategory = "sensor_timeout"
            title = "Sensor Timeout"
            recommendation = (
                "Check sensor connections and power, verify USB bandwidth,"
                " check camera/IMU driver status."
            )
        else:
            subcategory = "general_timeout"
            title = issue_def["title"]
            recommendation = issue_def.get("recommendation", "")

        self._add_issue(
            severity=issue_def["severity"],
            category=issue_def["category"],
            title=title,
            description=entry.message[:200],
            node=entry.node,
            timestamp=entry.timestamp,
            message=entry.message,
            recommendation=recommendation,
            source_file=entry.file,
            subcategory=subcategory,
        )

    def _handle_latency_pattern(self, entry: "LogEntry", issue_def: dict) -> None:
        """Reclassify latency findings in pick-cycle context.

        ~6s durations are normal pick cycle times on the arm side, not
        network latency.  When the message or node indicates pick-cycle
        context, downgrade to INFO severity.
        """
        is_arm_node = "arm" in entry.node.lower()
        has_cycle_keyword = bool(self._PICK_CYCLE_KEYWORDS.search(entry.message))
        if is_arm_node or has_cycle_keyword:
            severity = "info"
        else:
            severity = issue_def["severity"]

        self._add_issue(
            severity=severity,
            category=issue_def["category"],
            title=issue_def["title"],
            description=entry.message[:200],
            node=entry.node,
            timestamp=entry.timestamp,
            message=entry.message,
            recommendation=issue_def.get("recommendation", ""),
        )

    def _add_issue(
        self,
        severity: str,
        category: str,
        title: str,
        description: str,
        node: str,
        timestamp: float,
        message: str,
        recommendation: str = "",
        source_file: str = "",
        subcategory: Optional[str] = None,
    ) -> None:
        severity = severity.lower()
        category = category.lower()
        key = f"{category}:{title}"
        ts_str = format_timestamp(timestamp, include_date=False) if timestamp else "N/A"
        if key not in self.issues:
            self.issues[key] = Issue(
                severity=severity,
                category=category,
                title=title,
                description=description,
                occurrences=1,
                first_seen=ts_str,
                last_seen=ts_str,
                affected_nodes=[node],
                sample_messages=[message[:300]],
                recommendation=recommendation,
                subcategory=subcategory,
                first_seen_file=source_file or None,
                last_seen_file=source_file or None,
            )
        else:
            issue = self.issues[key]
            issue.occurrences += 1
            issue.last_seen = ts_str
            if source_file:
                issue.last_seen_file = source_file
            if node not in issue.affected_nodes:
                issue.affected_nodes.append(node)
            if len(issue.sample_messages) < 3 and message[:300] not in issue.sample_messages:
                issue.sample_messages.append(message[:300])

    # -----------------------------------------------------------------------
    # Zero-timing cross-reference (task 13.1)
    # -----------------------------------------------------------------------

    def _check_zero_timing(self) -> None:
        """Cross-reference JSON pick_complete timing with text log timing.

        When all pick_complete JSON events report j3_ms=0, j4_ms=0, j5_ms=0,
        check whether corresponding text log lines (per_joint_timings,
        retreat_breakdowns) contain non-zero joint movement times.

        - Text counterparts found with non-zero times -> HIGH severity
          (JSON timing data zeroed out but text logs show actual motion).
        - No text logs available for verification -> MEDIUM severity
          (JSON timing data may be unreliable).
        - JSON values non-zero for at least one entry -> no issue.
        """
        picks = self.events.picks
        if not picks:
            return

        # Check whether ALL picks have zeroed-out joint timing
        all_zero = all(
            (p.get("j3_ms") or 0) == 0 and (p.get("j4_ms") or 0) == 0 and (p.get("j5_ms") or 0) == 0
            for p in picks
        )
        if not all_zero:
            return  # At least one pick has non-zero joint timing — normal

        # All JSON picks have zeroed joint times; cross-reference text logs
        text_has_nonzero = False

        # Check per_joint_timings (approach records for j3/j4/j5)
        for t in self.events.per_joint_timings:
            joint = t.get("joint", "")
            if joint in ("j3", "j4", "j5", "j5_ee"):
                if (t.get("duration_ms") or 0) > 0:
                    text_has_nonzero = True
                    break

        # Check retreat_breakdowns (j3_ms, j4_ms, j5_ms fields)
        if not text_has_nonzero:
            for rb in self.events.retreat_breakdowns:
                if (
                    (rb.get("j3_ms") or 0) > 0
                    or (rb.get("j4_ms") or 0) > 0
                    or (rb.get("j5_ms") or 0) > 0
                ):
                    text_has_nonzero = True
                    break

        text_available = bool(self.events.per_joint_timings or self.events.retreat_breakdowns)

        if text_has_nonzero:
            self._add_issue(
                severity="high",
                category="instrumentation",
                title="JSON pick timing zeroed but text logs show motion",
                description=(
                    f"All {len(picks)} pick_complete JSON events report"
                    f" j3_ms=0, j4_ms=0, j5_ms=0, but text log [TIMING]"
                    f" lines contain non-zero joint movement times."
                    f" JSON timing data is not being populated correctly."
                ),
                node="arm_control",
                timestamp=0,
                message=(
                    f"All {len(picks)} pick_complete events have zeroed"
                    f" joint timing; text logs show actual motion"
                ),
                recommendation=(
                    "Verify that the JSON serialization path for"
                    " pick_complete events includes the per-joint timing"
                    " fields (j3_ms, j4_ms, j5_ms). The text [TIMING]"
                    " lines show correct values — the JSON path is likely"
                    " missing the assignment."
                ),
            )
        elif not text_available:
            self._add_issue(
                severity="medium",
                category="instrumentation",
                title="JSON pick timing all zeros — no text logs to verify",
                description=(
                    f"All {len(picks)} pick_complete JSON events report"
                    f" j3_ms=0, j4_ms=0, j5_ms=0 and no text-based"
                    f" [TIMING] joint records are available for"
                    f" cross-verification."
                ),
                node="arm_control",
                timestamp=0,
                message=(
                    f"All {len(picks)} pick_complete events have zeroed"
                    f" joint timing; no text timing logs for verification"
                ),
                recommendation=(
                    "Check whether per-joint timing text logs are being"
                    " emitted. If both JSON and text paths report zero,"
                    " the joints may genuinely not be moving, or timing"
                    " instrumentation is disabled."
                ),
            )
        # else: text_available but all text values also zero — no issue
        # (consistent zero across both sources; the existing
        # detect_zero_joint_movement detector handles that case)

    # -----------------------------------------------------------------------
    # Timeline (unchanged)
    # -----------------------------------------------------------------------

    def _build_timeline(self) -> tuple:
        """Build timeline of significant events.

        Returns (timeline_list, truncated_count).
        """
        significant_entries = [
            e
            for e in self.entries
            if e.level in ("ERROR", "FATAL", "WARN")
            or "start" in e.message.lower()
            or "ready" in e.message.lower()
            or "shutdown" in e.message.lower()
        ]
        significant_entries = sorted(significant_entries, key=lambda x: x.timestamp)
        total_significant = len(significant_entries)
        if self.max_timeline > 0:
            significant_entries = significant_entries[: self.max_timeline]
        truncated = max(0, total_significant - len(significant_entries))
        timeline = [
            {
                "timestamp": e.timestamp,
                "timestamp_human": format_timestamp(e.timestamp),
                "level": e.level,
                "node": e.node,
                "event": e.message[:100],
            }
            for e in significant_entries
        ]
        return timeline, truncated

    # -----------------------------------------------------------------------
    # Delegated handler methods — called by parser.py via getattr
    # (tasks 4.1–9.5, wired through _EVENT_HANDLERS in parser.py)
    # -----------------------------------------------------------------------

    def _handle_startup_timing(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_startup_timing(self, event)

    def _handle_shutdown_timing(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_shutdown_timing(self, event)

    def _handle_state_transition(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_state_transition(self, event)

    def _handle_steering_command(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_steering_command(self, event)

    def _handle_steering_settle(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_steering_settle(self, event)

    def _handle_drive_command(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_drive_command(self, event)

    def _handle_cmd_vel_latency(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_cmd_vel_latency(self, event)

    def _handle_control_loop_health(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_control_loop_health(self, event)

    def _handle_motor_health(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_motor_health(self, event)

    def _handle_arm_coordination(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_arm_coordination(self, event)

    def _handle_auto_mode_session(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_auto_mode_session(self, event)

    def _handle_motor_command(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_motor_command(self, event)

    def _handle_pick_complete(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_pick_complete(self, event)

    def _handle_cycle_complete(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_cycle_complete(self, event)

    def _handle_detection_summary(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_detection_summary(self, event)

    def _handle_detection_frame(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_detection_frame(self, event)

    def _handle_motor_alert(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_motor_alert(self, event)

    def _handle_detection_idle(self, event: dict) -> None:
        from . import parser as _p

        _p.handle_detection_idle(self, event)

    # -----------------------------------------------------------------------
    # Position-error to current-draw correlation (task 4.3)
    # -----------------------------------------------------------------------

    def _correlate_motor_data(
        self,
        current_result: dict,
        trending_result: dict,
    ) -> None:
        """Post-analysis pass: correlate position error with current draw.

        For each joint present in both motor_current and motor_trending
        results, compute Pearson correlation coefficient between the
        per-sample current readings and position error readings.  A
        high positive correlation (r > 0.7) with both trends increasing
        suggests mechanical degradation where the motor draws more
        current as position error grows.

        Issues are added directly via ``_add_issue()``.
        """
        current_joints = current_result.get("joints", {})
        trending_joints = trending_result.get("joints", {})

        if not current_joints or not trending_joints:
            return

        # Collect raw per-sample data from EventStore for paired analysis
        # Current readings: from motor_health_arm events
        current_by_joint: Dict[str, List[float]] = {}
        for ev in self.events.motor_health_arm:
            motors = ev.get("motors", [])
            if not isinstance(motors, list):
                continue
            for motor in motors:
                if not isinstance(motor, dict):
                    continue
                jid = motor.get("joint") or motor.get("id", "unknown")
                cur = motor.get("current_a")
                if cur is not None:
                    current_by_joint.setdefault(jid, []).append(float(cur))

        # Position error readings: from homing_events
        error_by_joint: Dict[str, List[float]] = {}
        for ev in self.events.homing_events:
            jid = ev.get("joint") or ev.get("id", "unknown")
            pos_err = ev.get("position_error")
            if pos_err is not None:
                error_by_joint.setdefault(jid, []).append(float(pos_err))

        # Find joints present in both detectors' results AND raw data
        common_joints = (
            set(current_joints) & set(trending_joints) & set(current_by_joint) & set(error_by_joint)
        )

        _MIN_PAIRED_SAMPLES = 5

        for joint_id in sorted(common_joints):
            currents = current_by_joint[joint_id]
            errors = error_by_joint[joint_id]

            # Pair samples — use the shorter length
            n = min(len(currents), len(errors))
            if n < _MIN_PAIRED_SAMPLES:
                continue

            x = currents[:n]
            y = errors[:n]

            # Pearson correlation coefficient
            mean_x = statistics.mean(x)
            mean_y = statistics.mean(y)

            numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
            sum_sq_x = sum((xi - mean_x) ** 2 for xi in x)
            sum_sq_y = sum((yi - mean_y) ** 2 for yi in y)

            denom = math.sqrt(sum_sq_x * sum_sq_y)
            if denom == 0:
                continue

            r = numerator / denom

            # Check both trends are positive (increasing)
            current_trend = current_joints[joint_id].get("health_indicator", "")
            error_trend = trending_joints[joint_id].get("trend_direction", "")

            # Current is "trending up" if late-session mean > early
            # (health_indicator WATCH or ALERT), error is "increasing"
            current_increasing = current_trend in ("WATCH", "ALERT")
            error_increasing = error_trend == "increasing"

            if r > 0.7 and current_increasing and error_increasing:
                self._add_issue(
                    severity="high",
                    category="motor",
                    title="Position Error-Current Correlation",
                    description=(
                        f"Joint '{joint_id}' shows strong"
                        f" positive correlation (r={r:.2f})"
                        f" between current draw and position"
                        f" error across {n} paired samples."
                        f" Both trends are increasing,"
                        f" suggesting progressive mechanical"
                        f" degradation."
                    ),
                    node="arm",
                    timestamp=0,
                    message=(f"Motor correlation: {joint_id}" f" r={r:.2f} (current up, error up)"),
                    recommendation=(
                        "Inspect joint mechanical components"
                        " (bearings, gears, belt tension)."
                        " Increasing current with growing"
                        " position error indicates wear or"
                        " binding that will worsen over time."
                    ),
                )

    # -----------------------------------------------------------------------
    # Executive summary (task 16.1, 16.2)
    # -----------------------------------------------------------------------

    def _compute_executive_summary(self, report: "AnalysisReport") -> str:
        """Build a one-line executive summary for the analysis report.

        Template: "{duration} {mode} test: {pick_count} picks, {key_findings}"
        Example:  "2h 15m field test: 42 picks, 85% success rate, 3 motor current alerts"

        The mode comes from task 14.1 auto-detection (stored on self._session_mode).

        Key findings are context-sensitive (task 16.2):
          - bench mode: motor health, joint limits, current spikes, temperature
          - field mode: success rate, throughput, cotton harvested, camera reliability
        """
        # Duration — prefer operational (ROS2 window) over total log span
        op_dur = report.operational_duration_seconds
        dur_str = format_duration(op_dur if op_dur > 0 else report.duration_seconds)

        # Mode from task 14.1 detection (already computed before this call)
        mode = getattr(self, "_session_mode", "bench")

        # Pick count
        pick_count = len(self.events.picks)

        # Collect key findings (up to 3)
        findings = self._collect_key_findings(report, mode)

        # Build summary string
        parts = [f"{dur_str} {mode} test: {pick_count} picks"]
        if findings:
            parts.append(", ".join(findings))

        return ", ".join(parts)

    def _collect_key_findings(
        self,
        report: "AnalysisReport",
        mode: str,
    ) -> list:
        """Select up to 3 key findings for the executive summary.

        Mixes critical/high issues with positive signals. Context-sensitive:
          - bench: motor health, joint limits, current spikes, temperature
          - field: success rate, throughput, camera reliability
        """
        findings: list = []

        # --- Positive signals and key metrics ---
        picks = self.events.picks
        if picks:
            succeeded = sum(1 for p in picks if p.get("success") or p.get("result") == "success")
            total = len(picks)
            if total > 0:
                rate = round(100.0 * succeeded / total, 1)
                findings.append(f"{rate}% success rate")

        if mode == "field":
            # Throughput (picks per hour)
            if picks and report.duration_seconds > 0:
                pph = round(len(picks) / (report.duration_seconds / 3600), 1)
                findings.append(f"{pph} picks/hr")

            # Camera reliability
            reconn_count = len(self.events.camera_reconnections)
            if reconn_count == 0:
                findings.append("no camera reconnections")
            elif reconn_count > 0:
                findings.append(f"{reconn_count} camera reconnections")

        elif mode == "bench":
            # Motor current alerts
            current_alerts = sum(
                1
                for i in report.issues
                if i.category == "motor" and i.severity in ("critical", "high")
            )
            if current_alerts == 0:
                findings.append("no motor current alerts")
            else:
                findings.append(f"{current_alerts} motor current alerts")

            # Joint limit violations
            jl_count = self.events._joint_limit_total
            if jl_count > 0:
                findings.append(f"{jl_count} joint limit violations")
            else:
                findings.append("no joint limit violations")

            # Temperature
            temp_issues = sum(
                1
                for i in report.issues
                if i.category == "thermal" and i.severity in ("critical", "high", "medium")
            )
            if temp_issues == 0:
                findings.append("stable temperatures")
            else:
                findings.append(f"{temp_issues} thermal warnings")

        # --- Critical/high issues as override findings ---
        critical_high = [i for i in report.issues if i.severity in ("critical", "high")]
        # Insert critical issues at the front if they aren't already covered
        for issue in sorted(
            critical_high,
            key=lambda x: (0 if x.severity == "critical" else 1),
        ):
            # Avoid duplicating motor/thermal findings already added
            issue_str = f"{issue.occurrences}x {issue.title}"
            already_covered = any(
                issue.category in f.lower() or issue.title.lower() in f.lower() for f in findings
            )
            if not already_covered and len(findings) < 5:
                findings.insert(min(1, len(findings)), issue_str)

        # Trim to 3 findings max
        return findings[:3]

    # -----------------------------------------------------------------------
    # task 13.1 — Launch log parser
    # -----------------------------------------------------------------------

    def _parse_launch_log(self, path: "Path") -> None:
        """Parse a ros2-launch format launch.log file.

        Extracts process start, crash, shutdown, and user interrupt events.
        Stores all to EventStore.launch_events.
        Classifies exit signals for shutdown type detection (task 12.4).
        """
        import re as _re

        if not path.exists():
            return  # task 13.2 — absent → skip silently

        _RE_START = _re.compile(r"\[launch\]\s.*?process started \[pid (\d+), .*?cmd '([^']+)'")
        _RE_STARTED_SIMPLE = _re.compile(r"process started \[pid (\d+),.*?\]")
        _RE_DIED = _re.compile(r"process has died \[pid (\d+), exit code (-?\d+), cmd '([^']*)'")
        _RE_SIGINT = _re.compile(r"sending SIGINT|signal_handler|ShutdownRequested")
        _RE_INTERRUPT = _re.compile(r"user interrupt|KeyboardInterrupt")
        # Extract process name from cmd path — last path component without extension
        _RE_CMD_NAME = _re.compile(r"(?:^|/)([^/\s]+?)(?:\.py|\.so|$)")
        _RE_TIMESTAMP = _re.compile(r"^\[([0-9]+\.[0-9]+)\]")
        _RE_USER_HINT = _re.compile(
            r"\[launch\.user\].*?check\s+(\S+)\s+for details", _re.IGNORECASE
        )

        # task 12.1 — also match simple process lifecycle lines
        # e.g. "[INFO] [launch]: process started [node_name-PID]"
        _RE_INFO_START = _re.compile(
            r"\[INFO\]\s*\[launch\]:\s*process started" r"\s*\[(\S+)-(\d+)\]"
        )
        _RE_INFO_DIED = _re.compile(
            r"\[INFO\]\s*\[launch\]:\s*process has died" r"\s*\[(\S+)-(\d+)\]"
        )

        # Signal classification mapping (task 12.4)
        # On Linux, negative exit codes = -signal_number
        _SIGNAL_MAP = {
            -2: "SIGINT",
            -6: "SIGABRT",
            -9: "SIGKILL",
            -11: "SIGSEGV",
            -15: "SIGTERM",
            # Some launch implementations report 128+signal
            130: "SIGINT",  # 128 + 2
            134: "SIGABRT",  # 128 + 6
            137: "SIGKILL",  # 128 + 9
            139: "SIGSEGV",  # 128 + 11
            143: "SIGTERM",  # 128 + 15
        }

        # Track started processes: pid → {name, pid, start_ts}
        started: dict = {}
        # Track user hints by process name
        name_hints: dict = {}
        session_events = []
        first_ts = None
        last_ts = None
        shutdown_ts = None

        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            return

        for line in lines:
            ts_m = _RE_TIMESTAMP.match(line)
            ts = float(ts_m.group(1)) if ts_m else None
            if ts is not None:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            # User hint lines (before crash matching so we can attach hint)
            hint_m = _RE_USER_HINT.search(line)
            if hint_m:
                hint_path = hint_m.group(1)
                # Attach to all recent processes that don't yet have a hint
                for pid_key, proc in started.items():
                    if not proc.get("external_log_hint"):
                        proc["external_log_hint"] = hint_path
                # Also store by context for later matching
                for ev in session_events:
                    if not ev.get("external_log_hint") and ev.get("type") == "crash":
                        ev["external_log_hint"] = hint_path

            # Process started
            m = _RE_START.search(line)
            if m:
                pid = int(m.group(1))
                cmd = m.group(2).strip()
                name_m = _RE_CMD_NAME.search(cmd)
                name = name_m.group(1) if name_m else cmd
                started[pid] = {
                    "name": name,
                    "pid": pid,
                    "start_ts": ts,
                    "cmd": cmd,
                    "external_log_hint": None,
                }
                session_events.append(
                    {
                        "type": "start",
                        "name": name,
                        "pid": pid,
                        "start_ts": ts,
                        "cmd": cmd,
                        "arm_id": self._current_arm_id,
                    }
                )
                continue

            # Process died
            m = _RE_DIED.search(line)
            if m:
                pid = int(m.group(1))
                exit_code = int(m.group(2))
                cmd = m.group(3).strip()
                name_m = _RE_CMD_NAME.search(cmd)
                name = name_m.group(1) if name_m else cmd

                start_info = started.get(pid, {})
                start_ts = start_info.get("start_ts")
                lifetime_s = (ts - start_ts) if (ts is not None and start_ts is not None) else None
                hint = start_info.get("external_log_hint") or name_hints.get(name)

                # task 13.5 — check for per-node ROS2 log file by PID
                ros2_log_found = self._find_ros2_log_by_pid(pid)

                # task 12.4 — classify exit signal and shutdown type
                exit_signal = _SIGNAL_MAP.get(exit_code)
                if exit_signal in ("SIGINT", "SIGTERM"):
                    shutdown_type = "clean"
                elif exit_signal in ("SIGSEGV", "SIGABRT"):
                    shutdown_type = "crash"
                elif exit_signal == "SIGKILL":
                    shutdown_type = "kill"
                elif exit_code == 0:
                    shutdown_type = "clean"
                else:
                    shutdown_type = "unknown"

                ev = {
                    "type": "crash",
                    "name": name,
                    "pid": pid,
                    "exit_code": exit_code,
                    "exit_signal": exit_signal,
                    "shutdown_type": shutdown_type,
                    "cmd": cmd,
                    "start_ts": start_ts,
                    "crash_ts": ts,
                    "lifetime_s": lifetime_s,
                    "external_log_hint": hint,
                    "has_ros2_log": ros2_log_found,
                    "arm_id": self._current_arm_id,
                }
                session_events.append(ev)
                # Remove from started (no longer running)
                started.pop(pid, None)
                continue

            # task 12.1 — simple [INFO] format: process started [node_name-PID]
            m = _RE_INFO_START.search(line)
            if m:
                name = m.group(1)
                pid = int(m.group(2))
                started[pid] = {
                    "name": name,
                    "pid": pid,
                    "start_ts": ts,
                    "cmd": name,
                    "external_log_hint": None,
                }
                session_events.append(
                    {
                        "type": "start",
                        "name": name,
                        "pid": pid,
                        "start_ts": ts,
                        "cmd": name,
                        "arm_id": self._current_arm_id,
                    }
                )
                continue

            # task 12.1 — simple [INFO] format: process has died [node_name-PID]
            m = _RE_INFO_DIED.search(line)
            if m:
                name = m.group(1)
                pid = int(m.group(2))
                start_info = started.get(pid, {})
                start_ts = start_info.get("start_ts")
                lifetime_s = (ts - start_ts) if (ts is not None and start_ts is not None) else None
                ros2_log_found = self._find_ros2_log_by_pid(pid)
                ev = {
                    "type": "crash",
                    "name": name,
                    "pid": pid,
                    "exit_code": None,
                    "exit_signal": None,
                    "shutdown_type": "unknown",
                    "cmd": start_info.get("cmd", name),
                    "start_ts": start_ts,
                    "crash_ts": ts,
                    "lifetime_s": lifetime_s,
                    "external_log_hint": start_info.get("external_log_hint"),
                    "has_ros2_log": ros2_log_found,
                    "arm_id": self._current_arm_id,
                }
                session_events.append(ev)
                started.pop(pid, None)
                continue

            # Shutdown / interrupt
            if _RE_SIGINT.search(line) or _RE_INTERRUPT.search(line):
                if shutdown_ts is None:
                    shutdown_ts = ts
                session_events.append(
                    {
                        "type": "shutdown",
                        "ts": ts,
                        "arm_id": self._current_arm_id,
                    }
                )

        # Mark any still-running processes as "still_running"
        for pid, info in started.items():
            session_events.append(
                {
                    "type": "still_running",
                    "name": info["name"],
                    "pid": pid,
                    "start_ts": info.get("start_ts"),
                    "cmd": info.get("cmd"),
                    "arm_id": self._current_arm_id,
                }
            )

        # Attach session-level timing metadata
        if session_events:
            session_events[0]["_session_first_ts"] = first_ts
            session_events[0]["_session_last_ts"] = last_ts or shutdown_ts

        self.events.launch_events.extend(session_events)

    def _find_ros2_log_by_pid(self, pid: int) -> bool:
        """task 13.5 — check if a per-node ROS2 log file exists for this PID."""
        import glob as _glob

        pattern = str(self.log_dir / f"**/*{pid}*")
        matches = _glob.glob(pattern, recursive=True)
        return bool(matches)
