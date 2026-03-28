"""
Issue detection, cross-correlation and session health analysis.

Groups 10-14 of the vehicle-log-analyzer change:
  10 — Vehicle-specific issue detection
  11 — Arm JSON issue detection
  12 — Cross-correlation: picks <-> vehicle state
  13 — Failure chains
  14 — Session health analysis

All detector submodules self-register with the central registry on import.
"""

# Import registry first so it is available to submodules
from . import registry  # noqa: F401

# Import submodules — each registers its detectors at import time
from .arm import detect_arm_json_issues, detect_zero_joint_movement
from .build_provenance import (
    detect_dirty_builds,
    detect_stale_builds,
    extract_build_provenance,
)
from .camera_thermal import (
    analyze_camera_thermal,
    detect_confidence_discrepancy,
)
from .motor_current import analyze_motor_current
from .motor_telemetry import analyze_motor_telemetry
from .motor_trending import analyze_motor_trending
from .session_lifecycle import analyze_session_lifecycle
from .correlation import (
    correlate_motor_commands_with_picking,
    correlate_picks_with_vehicle_state,
    detect_cross_log_correlations,
)
from .deduplication import deduplicate_issues
from .detection import (
    detect_border_skip_rate,
    detect_high_detection_age,
    detect_high_frame_drop_rate,
    detect_low_cache_hit_rate,
    detect_scan_dead_zones,
    detect_stale_detection_rate,
)
from .failure_analysis import (
    analyze_session_health,
    detect_failure_chains,
    detect_launch_crashes,
)
from .hardware import (
    detect_camera_frame_wait_degradation,
    detect_compressor_dominance,
    detect_ee_timeout_rate,
    detect_homing_failures,
    detect_joint_limit_pattern,
)
from .vehicle import detect_vehicle_issues

# Import remaining submodules that are not directly used in analyzer.py
# but should register their detectors
from . import camera_health  # noqa: F401
from . import timing  # noqa: F401

__all__ = [
    "registry",
    "detect_vehicle_issues",
    "detect_arm_json_issues",
    "detect_zero_joint_movement",
    "correlate_motor_commands_with_picking",
    "correlate_picks_with_vehicle_state",
    "detect_cross_log_correlations",
    "detect_failure_chains",
    "detect_launch_crashes",
    "analyze_session_health",
    "detect_ee_timeout_rate",
    "detect_joint_limit_pattern",
    "detect_camera_frame_wait_degradation",
    "detect_homing_failures",
    "detect_compressor_dominance",
    "detect_stale_detection_rate",
    "detect_scan_dead_zones",
    "detect_border_skip_rate",
    "detect_high_frame_drop_rate",
    "detect_high_detection_age",
    "detect_low_cache_hit_rate",
    "deduplicate_issues",
    "extract_build_provenance",
    "detect_stale_builds",
    "detect_dirty_builds",
    "analyze_motor_trending",
    "analyze_camera_thermal",
    "detect_confidence_discrepancy",
    "analyze_motor_current",
    "analyze_motor_telemetry",
    "analyze_session_lifecycle",
]
