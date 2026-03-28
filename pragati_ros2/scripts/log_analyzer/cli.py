"""
CLI entry-point for the log_analyzer package.

Groups covered:
  18.1-18.8 — new --csv, --html, --compare, --analyze flags (implemented via
              exporters.py and reports.py); --field-summary flag
  Existing  — --json, --summary, --verbose, --watch, --timeline, --output
              (behaviour identical to the original log_analyzer.py main())
"""

import argparse
import io
import json
import os
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .analyzer import (
    AnalysisReport,
    Colors,
    ROS2LogAnalyzer,
    format_bytes,
    format_duration,
    format_timestamp,
)


# ---------------------------------------------------------------------------
# Terminal output helpers (ported unchanged from original log_analyzer.py)
# ---------------------------------------------------------------------------


def print_report(report: AnalysisReport, summary_only: bool = False) -> None:
    """Print formatted report to terminal."""

    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}  ROS2 Log Analysis Report{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    # task 16.3 — executive summary as first bold line
    if report.executive_summary:
        print(f"  {Colors.BOLD}{report.executive_summary}{Colors.RESET}\n")

    # task 14.4 — mode indicator in report header
    if report.session_mode:
        source_label = (
            "auto-detected"
            if report.session_mode_source == "auto"
            else "user override"
        )
        print(f"   Mode: {report.session_mode} ({source_label})\n")

    # In summary mode, the executive summary is the primary output
    if summary_only and report.executive_summary:
        pass  # continue to show overview + issues below

    # Overview
    print(f"{Colors.BOLD}Overview{Colors.RESET}")
    print(f"   Directory: {report.log_directory}")
    print(f"   Files analyzed: {report.total_files}")
    print(f"   Total lines: {report.total_lines:,}")
    print(f"   Total size: {format_bytes(report.total_size_bytes)}")
    op_dur = getattr(report, "operational_duration_seconds", 0)
    dur = op_dur if op_dur > 0 else report.duration_seconds
    print(f"   Log duration: {format_duration(dur)}")
    print()

    # Level summary
    print(f"{Colors.BOLD}Log Level Distribution{Colors.RESET}")
    level_colors = {
        "FATAL": Colors.RED + Colors.BOLD,
        "ERROR": Colors.RED,
        "WARN": Colors.YELLOW,
        "INFO": Colors.GREEN,
        "DEBUG": Colors.GRAY,
    }

    for level in ["FATAL", "ERROR", "WARN", "INFO", "DEBUG"]:
        count = report.level_counts.get(level, 0)
        color = level_colors.get(level, "")
        bar = "█" * min(count // 100, 30) if count > 0 else ""
        print(f"   {color}{level:6}{Colors.RESET}: {count:>8,}  {bar}")
    print()

    # Issues
    if report.issues:
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        sorted_issues = sorted(
            report.issues,
            key=lambda x: (severity_order.get(x.severity, 5), -x.occurrences),
        )
        severity_counts: dict = defaultdict(int)
        for issue in sorted_issues:
            severity_counts[issue.severity] += 1

        print(f"{Colors.BOLD}Issues Found ({len(sorted_issues)} unique){Colors.RESET}")
        print(
            f"   Critical: {severity_counts['critical']}  "
            f"High: {severity_counts['high']}  "
            f"Medium: {severity_counts['medium']}  "
            f"Low: {severity_counts['low']}"
        )
        print()

        if not summary_only:
            severity_icons = {
                "critical": "[CRIT]",
                "high": "[HIGH]",
                "medium": "[MED] ",
                "low": "[LOW] ",
                "info": "[INFO]",
            }
            for issue in sorted_issues[:20]:
                icon = severity_icons.get(issue.severity, "[?]  ")
                print(f"   {icon} {issue.title}")
                print(f"      Category: {issue.category} | Occurrences: {issue.occurrences}")
                print(f"      First seen: {issue.first_seen} | Last seen: {issue.last_seen}")
                print(f"      Nodes: {', '.join(issue.affected_nodes[:3])}")
                if issue.recommendation:
                    print(f"      {Colors.CYAN}{issue.recommendation}{Colors.RESET}")
                if issue.sample_messages:
                    print(
                        f"      {Colors.GRAY}Sample: {issue.sample_messages[0][:80]}...{Colors.RESET}"
                    )
                print()
    else:
        print(f"{Colors.GREEN}No significant issues detected!{Colors.RESET}\n")

    # Performance metrics
    if report.performance and not summary_only:
        print(f"{Colors.BOLD}Performance Metrics{Colors.RESET}")
        for name, metrics in report.performance.items():
            print(
                f"   {name}:\n"
                f"      Avg: {metrics['avg']:.1f} {metrics['unit']}  "
                f"Min: {metrics['min']:.1f}  Max: {metrics['max']:.1f}  "
                f"(n={metrics['samples']})"
            )
        print()

    # Node statistics
    if report.node_stats and not summary_only:
        print(f"{Colors.BOLD}Node Statistics{Colors.RESET}")
        for node, stats in sorted(
            report.node_stats.items(), key=lambda x: x[1]["total"], reverse=True
        )[:10]:
            error_warn = stats["error"] + stats["warn"] + stats["fatal"]
            status = "[OK]" if error_warn == 0 else ("[WARN]" if stats["fatal"] == 0 else "[ERR]")
            print(
                f"   {status} {node}\n"
                f"      Total: {stats['total']:,} | "
                f"Errors: {stats['error']} | Warnings: {stats['warn']}"
            )
        print()

    # Quick recommendations
    print(f"{Colors.BOLD}Quick Recommendations{Colors.RESET}")
    recommendations = []

    if report.level_counts.get("FATAL", 0) > 0:
        recommendations.append("CRITICAL: Fatal errors detected - investigate immediately!")

    if report.level_counts.get("ERROR", 0) > 10:
        recommendations.append("HIGH: Multiple errors occurred - review error logs")

    if any(i.category == "hardware" for i in report.issues):
        recommendations.append("Check hardware connections (USB, CAN, sensors)")

    if any(i.category == "performance" for i in report.issues):
        recommendations.append("Performance issues detected - consider profiling")

    if any("USB 2.0" in i.title for i in report.issues):
        recommendations.append("Camera running at USB 2.0 - use USB 3.0 port")

    perf = report.performance
    if perf.get("detection_time", {}).get("avg", 0) > 50:
        recommendations.append(
            "Detection is slow - consider reducing resolution or model complexity"
        )

    if not recommendations:
        recommendations.append("System appears healthy - no immediate actions needed")

    for rec in recommendations:
        print(f"   {rec}")

    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}\n")


def print_json_report(
    report: AnalysisReport,
    args: argparse.Namespace,
    analyzer: "ROS2LogAnalyzer | None" = None,
) -> None:
    """Print report as JSON, respecting --max-* CLI flags."""
    max_tl = getattr(args, "max_timeline", 200)
    max_err = getattr(args, "max_errors", 500)
    max_warn = getattr(args, "max_warnings", 500)

    all_timeline = report.timeline
    all_errors = report.errors
    all_warnings = report.warnings

    shown_timeline = all_timeline if max_tl == 0 else all_timeline[:max_tl]
    shown_errors = all_errors if max_err == 0 else all_errors[:max_err]
    shown_warnings = all_warnings if max_warn == 0 else all_warnings[:max_warn]

    output = {
        "log_directory": report.log_directory,
        "analysis_time": report.analysis_time,
        "executive_summary": report.executive_summary,
        "session_mode": report.session_mode,
        "summary": {
            "total_files": report.total_files,
            "total_lines": report.total_lines,
            "total_size_bytes": report.total_size_bytes,
            "duration_seconds": report.duration_seconds,
        },
        "level_counts": report.level_counts,
        "issues": [asdict(i) for i in report.issues],
        "node_stats": report.node_stats,
        "performance": report.performance,
        "timeline": shown_timeline,
        "errors": shown_errors,
        "warnings": shown_warnings,
        "truncated": {
            "timeline": {
                "total": len(all_timeline),
                "shown": len(shown_timeline),
            },
            "errors": {
                "total": len(all_errors),
                "shown": len(shown_errors),
            },
            "warnings": {
                "total": len(all_warnings),
                "shown": len(shown_warnings),
            },
        },
    }

    # Include field_summary when --field-summary was also passed
    if analyzer is not None and getattr(analyzer, "field_summary", None) is not None:
        output["field_summary"] = asdict(analyzer.field_summary)

    print(json.dumps(output, indent=2, default=str))


def print_timeline(report: AnalysisReport) -> None:
    """Print a chronological event timeline with human-readable timestamps."""
    print("\n" + "=" * 80)
    print("EVENT TIMELINE")
    print("=" * 80)

    timeline = report.timeline
    if not timeline:
        print("  No events found in logs.")
        return

    for event in timeline:
        ts = event.get("timestamp", 0)
        ts_human = event.get("timestamp_human", format_timestamp(ts))
        node = event.get("node", "unknown")
        level = event.get("level", "INFO")
        message = event.get("event", "") or event.get("message", "")

        msg_lower = message.lower()
        if level == "ERROR":
            event_type = "error"
        elif level == "WARN":
            event_type = "warning"
        elif any(k in msg_lower for k in ("motor", "can", "joint")):
            event_type = "motor"
        elif any(k in msg_lower for k in ("camera", "oak", "depthai")):
            event_type = "camera"
        elif any(k in msg_lower for k in ("detect", "cotton", "yolo")):
            event_type = "detection"
        elif any(k in msg_lower for k in ("start", "ready", "init")):
            event_type = "startup"
        else:
            event_type = "info"

        color = {
            "startup": "\033[92m",
            "error": "\033[91m",
            "warning": "\033[93m",
            "motor": "\033[94m",
            "camera": "\033[95m",
            "detection": "\033[96m",
            "info": "\033[0m",
        }.get(event_type, "\033[0m")
        reset = "\033[0m"

        time_only = ts_human.split(" ")[-1] if " " in ts_human else ts_human

        if len(message) > 60:
            message = message[:57] + "..."

        print(f"  {time_only}  {color}[{node:20s}]{reset} {message}")

    print()
    print(f"  Total events: {len(timeline)}")
    if report.timeline_truncated > 0:
        print(
            f"  ({report.timeline_truncated} entries truncated"
            f" — use --max-timeline to adjust)"
        )
    print()


def watch_logs(log_dir: str, interval: int = 5, analyze: bool = False) -> None:
    """Watch logs in real-time with recursive directory monitoring.

    If *analyze* is True, print rolling analysis stats after each poll cycle
    (task 18.8 --analyze flag).

    Enhancements (tasks 6.4, 6.5):
    - Recursively monitors subdirectories and detects newly created ones.
    - Processes ``.log.gz`` files transparently, skipping unmodified ones.
    """
    import gzip
    import time

    print(
        f"{Colors.CYAN}Watching logs in {log_dir} "
        f"(recursive, Ctrl+C to stop)...{Colors.RESET}\n"
    )

    # Track last-seen sizes for plain .log files (incremental tail)
    last_sizes: dict[str, int] = {}
    # Track last-seen mtime for .gz files (reprocess on change)
    gz_mtimes: dict[str, float] = {}
    # Track already-processed .gz file contents (skip if unchanged)
    gz_processed: set[str] = set()

    def _discover_files(root: Path) -> tuple[list[Path], list[Path]]:
        """Discover .log and .log.gz files recursively."""
        log_files: list[Path] = []
        gz_files: list[Path] = []
        for f in sorted(root.rglob("*.log")):
            log_files.append(f)
        for f in sorted(root.rglob("*.log.gz")):
            gz_files.append(f)
        return log_files, gz_files

    def _print_line(line: str) -> None:
        """Print a log line with level-based colouring.

        Detects JSON-structured lines (starting with '{'), parses them
        for level/msg fields, and falls back to plain-text bracket
        matching for non-JSON or malformed input.
        """
        level = None
        display = line

        if line.startswith("{"):
            try:
                obj = json.loads(line)
                # Common structured log fields
                level = (
                    obj.get("level")
                    or obj.get("severity")
                    or obj.get("log_level")
                    or ""
                ).upper()
                msg = (
                    obj.get("msg")
                    or obj.get("message")
                    or obj.get("text")
                    or ""
                )
                name = obj.get("name") or obj.get("node") or ""
                ts = (
                    obj.get("timestamp")
                    or obj.get("ts")
                    or obj.get("time")
                    or ""
                )
                if msg:
                    parts: list[str] = []
                    if ts:
                        parts.append(str(ts))
                    if name:
                        parts.append(f"[{name}]")
                    if level:
                        parts.append(f"[{level}]")
                    parts.append(str(msg))
                    display = " ".join(parts)
            except (json.JSONDecodeError, TypeError, AttributeError):
                # Malformed JSON — fall through to plain-text path
                pass

        # Determine level from plain text if not already set from JSON
        if level is None:
            if "[ERROR]" in line or "[FATAL]" in line:
                level = "ERROR"
            elif "[WARN]" in line:
                level = "WARN"

        # Colorize based on level
        if level in ("ERROR", "FATAL", "CRIT", "CRITICAL"):
            print(f"{Colors.RED}{display}{Colors.RESET}")
        elif level in ("WARN", "WARNING"):
            print(f"{Colors.YELLOW}{display}{Colors.RESET}")
        elif level in ("DEBUG",):
            print(f"{Colors.GRAY}{display}{Colors.RESET}")
        else:
            # JSON lines are always printed (they're structured events)
            if line.startswith("{"):
                print(display)

    try:
        while True:
            log_path = Path(log_dir)

            # task 6.4 — recursive file discovery (picks up new subdirs)
            plain_files, gz_files = _discover_files(log_path)

            # Process plain .log files (incremental tail)
            for log_file in plain_files:
                try:
                    current_size = log_file.stat().st_size
                except OSError:
                    continue
                last_size = last_sizes.get(str(log_file), 0)

                if current_size > last_size:
                    try:
                        with open(
                            log_file, "r", errors="replace"
                        ) as fh:
                            fh.seek(last_size)
                            for line in fh.read().splitlines():
                                _print_line(line)
                    except OSError:
                        continue

                    last_sizes[str(log_file)] = current_size

            # task 6.5 — process .log.gz files (detect new / modified)
            for gz_file in gz_files:
                fkey = str(gz_file)
                try:
                    mtime = gz_file.stat().st_mtime
                except OSError:
                    continue

                prev_mtime = gz_mtimes.get(fkey)
                if prev_mtime is not None and mtime == prev_mtime:
                    # Already processed and file hasn't changed
                    continue

                # New or modified .gz file — process it
                gz_mtimes[fkey] = mtime
                if fkey not in gz_processed:
                    try:
                        with gzip.open(gz_file, "rt", errors="replace") as fh:
                            for line in fh:
                                _print_line(line.rstrip("\n"))
                    except (OSError, gzip.BadGzipFile):
                        continue
                    gz_processed.add(fkey)
                else:
                    # File was modified since last processing — re-scan
                    try:
                        with gzip.open(gz_file, "rt", errors="replace") as fh:
                            for line in fh:
                                _print_line(line.rstrip("\n"))
                    except (OSError, gzip.BadGzipFile):
                        continue

            # task 18.8 — rolling analysis
            if analyze:
                from . import exporters

                analyzer = ROS2LogAnalyzer(log_dir)
                analyzer.analyze()
                exporters.print_rolling_analysis(analyzer)

            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n{Colors.CYAN}Stopped watching.{Colors.RESET}")


# ---------------------------------------------------------------------------
# Filter parsing helper (task 8.5)
# ---------------------------------------------------------------------------


def _parse_filters(raw: list[str]) -> dict[str, set[str]]:
    """Parse ``--filter KEY:VALUE`` arguments into ``{key: {values}}`` dict.

    Valid keys: ``detector``, ``joint``, ``severity``.
    Calls ``sys.exit(1)`` on invalid keys or format.
    """
    valid_keys = {"detector", "joint", "severity"}
    result: dict[str, set[str]] = {}
    for item in raw:
        if ":" not in item:
            print(
                f"{Colors.RED}Error: invalid filter '{item}' — "
                f"expected KEY:VALUE format{Colors.RESET}"
            )
            print(f"  Valid keys: {', '.join(sorted(valid_keys))}")
            sys.exit(1)
        key, value = item.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key not in valid_keys:
            print(
                f"{Colors.RED}Error: invalid filter key '{key}'{Colors.RESET}"
            )
            print(f"  Valid keys: {', '.join(sorted(valid_keys))}")
            sys.exit(1)
        result.setdefault(key, set()).add(value)
    return result


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> None:
    """Parse arguments and run the log analyzer."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ROS2 Log Analyzer - Analyze robot logs for issues and insights",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/logs                                      # Full analysis with terminal output
  %(prog)s /path/to/logs --summary                           # Quick summary only
  %(prog)s /path/to/logs --json                              # JSON output for scripting
  %(prog)s /path/to/logs --json > report.json                # Save to file
  %(prog)s /path/to/logs --watch                             # Watch mode for live logs
  %(prog)s /path/to/logs --timeline                          # Show event timeline
  %(prog)s /path/to/logs --field-summary                     # Field-trial summary report
  %(prog)s ./collected_logs/session_2026-01-15_09-30 --field-summary  # Multi-role session
  %(prog)s /path/to/logs --csv events                        # Export events to CSV
  %(prog)s /path/to/logs --csv metrics                       # Export metrics to CSV
  %(prog)s /path/to/logs --html                              # Export self-contained HTML report
  %(prog)s /path/to/logs --compare /other                    # Compare two sessions
  %(prog)s /path/to/logs --watch --analyze                   # Watch with rolling analysis
  %(prog)s --list-detectors                                  # List all registered detectors
  %(prog)s /path/to/logs --filter detector:detect_vehicle_issues  # Run single detector
  %(prog)s /path/to/logs --filter severity:critical          # Show only critical issues
        """,
    )

    # Positional
    parser.add_argument(
        "log_directory",
        nargs="?",
        default=None,
        help="Path to log directory or log file",
    )

    # Existing flags (unchanged behaviour)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--summary", action="store_true", help="Show summary only")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Include all details"
    )
    parser.add_argument(
        "--watch", "-w", action="store_true", help="Watch mode for live logs"
    )
    parser.add_argument(
        "--timeline",
        "-t",
        action="store_true",
        help="Show event timeline with human-readable timestamps",
    )
    parser.add_argument("--output", "-o", help="Output file path")

    # New flags (tasks 18.1-18.8)
    parser.add_argument(
        "--field-summary",
        action="store_true",
        help="Print field-trial summary report (pick performance, vehicle, network, etc.)",
    )
    parser.add_argument(
        "--csv",
        choices=["events", "metrics"],
        metavar="{events,metrics}",
        help="Export to CSV: 'events' (one row per event) or 'metrics' (hourly buckets)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Export self-contained HTML report (inline CSS, no JS)",
    )
    parser.add_argument(
        "--compare",
        metavar="DIR",
        help="Compare current session with another log directory",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Print rolling analysis stats when used with --watch",
    )

    # --- log-analyzer-enhancements Phase 1 flags ---
    parser.add_argument(
        "--ros-log-dir",
        nargs="?",
        const="",
        default=None,
        metavar="PREFIX",
        help=(
            "Resolve ROS2 log directory. No argument: use ~/.ros/log/latest. "
            "With a prefix (e.g. 2026-01-15): match session dirs. "
            "Honors ROS_LOG_DIR env var."
        ),
    )
    parser.add_argument(
        "--max-timeline",
        type=int,
        default=200,
        metavar="N",
        help="Max timeline entries in output (0=unlimited, default: 200)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=500,
        metavar="N",
        help="Max error entries in output (0=unlimited, default: 500)",
    )
    parser.add_argument(
        "--max-warnings",
        type=int,
        default=500,
        metavar="N",
        help="Max warning entries in output (0=unlimited, default: 500)",
    )
    parser.add_argument(
        "--stale-threshold-hours",
        type=float,
        default=1.0,
        metavar="H",
        help=(
            "Hours threshold for stale binary detection"
            " (default: 1.0)"
        ),
    )
    parser.add_argument(
        "--joint-tolerance",
        type=str,
        default=None,
        metavar="JOINT=VALUE,...",
        help=(
            "Per-joint position error thresholds for motor"
            " trending (e.g., '3=0.080,5=0.020')."
            " Overrides default per-joint tolerances."
        ),
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable issue deduplication (show all raw issues)",
    )

    # --- log-analyzer-deep-analysis Phase 8 flags ---
    parser.add_argument(
        "--list-detectors",
        action="store_true",
        help="List all registered detectors and exit",
    )
    parser.add_argument(
        "--filter",
        action="append",
        metavar="KEY:VALUE",
        help=(
            "Filter results by KEY:VALUE pair. Valid keys: "
            "detector (run only named detector), joint (show only joint N), "
            "severity (show only given severity). "
            "Repeat for multiple filters: "
            "--filter detector:detect_vehicle_issues --filter severity:critical"
        ),
    )
    # task 14.2 — test mode override flag
    parser.add_argument(
        "--mode",
        choices=["bench", "field", "integration"],
        metavar="MODE",
        help=(
            "Force session mode (bench|field|integration). "
            "Overrides auto-detection."
        ),
    )

    args = parser.parse_args(argv)

    # --ros-log-dir resolution (task 1.1)
    if args.ros_log_dir is not None:
        ros_log_root = Path(
            os.environ.get("ROS_LOG_DIR", os.path.expanduser("~/.ros/log"))
        )
        if args.ros_log_dir == "":
            # No prefix: resolve ~/.ros/log/latest symlink
            latest = ros_log_root / "latest"
            if not latest.exists():
                print(
                    f"{Colors.RED}Error: {latest} does not exist{Colors.RESET}"
                )
                sys.exit(1)
            args.log_directory = str(latest.resolve())
        else:
            # Prefix matching: find session dirs matching the prefix
            prefix = args.ros_log_dir
            if not ros_log_root.is_dir():
                print(
                    f"{Colors.RED}Error: ROS log root {ros_log_root}"
                    f" does not exist{Colors.RESET}"
                )
                sys.exit(1)
            matches = sorted(
                d
                for d in ros_log_root.iterdir()
                if d.is_dir() and d.name.startswith(prefix)
            )
            if len(matches) == 0:
                print(
                    f"{Colors.RED}Error: no session directories matching"
                    f" '{prefix}*' in {ros_log_root}{Colors.RESET}"
                )
                sys.exit(1)
            elif len(matches) == 1:
                args.log_directory = str(matches[0])
            else:
                print(
                    f"{Colors.RED}Error: multiple sessions match"
                    f" '{prefix}*':{Colors.RESET}"
                )
                for m in matches:
                    print(f"  {m.name}")
                print("Please be more specific.")
                sys.exit(1)

    # task 8.4 — --list-detectors: print registry and exit (no log_directory needed)
    if args.list_detectors:
        from .detectors import registry

        detectors = registry.get_all()
        if not detectors:
            print("No detectors registered.")
            sys.exit(0)

        # Compute column widths
        name_w = max(len(d["name"]) for d in detectors)
        cat_w = max(len(d["category"]) for d in detectors)
        name_w = max(name_w, 4)  # min header width
        cat_w = max(cat_w, 8)

        print(f"\n{Colors.BOLD}Registered Detectors{Colors.RESET}")
        print("=" * (name_w + cat_w + 20))
        print()
        hdr = f"  {'Name':<{name_w}}  {'Category':<{cat_w}}  Description"
        print(hdr)
        print(
            f"  {'-'*name_w}  {'-'*cat_w}  {'-'*11}"
        )
        for d in detectors:
            print(
                f"  {d['name']:<{name_w}}  "
                f"{d['category']:<{cat_w}}  "
                f"{d['description']}"
            )
        print()
        sys.exit(0)

    # Require log_directory (either positional or via --ros-log-dir)
    if args.log_directory is None:
        parser.error(
            "log_directory is required (provide a path or use --ros-log-dir)"
        )

    # Validate log directory
    if not os.path.exists(args.log_directory):
        print(f"{Colors.RED}Error: {args.log_directory} does not exist{Colors.RESET}")
        sys.exit(1)

    # --watch mode (task 18.8: --analyze flag feeds rolling stats)
    # task 1.5 — detect topology mismatch for --watch on multi-role session root
    if args.watch:
        from .analyzer import ROS2LogAnalyzer as _A, SessionTopologyMode as _STM

        log_path = Path(args.log_directory)
        if log_path.is_dir():
            _probe = _A(args.log_directory)
            _topo = _probe._detect_topology(log_path)
            if _topo.mode == _STM.MULTI_ROLE:
                print(
                    f"{Colors.RED}Use a role subdirectory with --watch "
                    f"(multi-role roots are not supported){Colors.RESET}"
                )
                sys.exit(1)
        watch_logs(args.log_directory, analyze=args.analyze)
        return

    # Run analysis
    analyzer = ROS2LogAnalyzer(args.log_directory, verbose=args.verbose)
    analyzer.max_timeline = args.max_timeline
    analyzer.max_errors = args.max_errors
    analyzer.max_warnings = args.max_warnings
    analyzer.stale_threshold_hours = args.stale_threshold_hours

    # task 14.2 — pass --mode flag to analyzer for session mode override
    if args.mode:
        analyzer.session_mode = args.mode

    # task 11.3 — pass --no-dedup flag to analyzer
    if args.no_dedup:
        analyzer.skip_dedup = True

    # task 8.5 — parse and apply --filter flags
    parsed_filters: dict[str, set[str]] = {}
    if args.filter:
        parsed_filters = _parse_filters(args.filter)
        if "detector" in parsed_filters:
            analyzer.detector_filter = parsed_filters["detector"]

    # task 4.16 — parse --joint-tolerance flag
    if args.joint_tolerance:
        jt: dict = {}
        for pair in args.joint_tolerance.split(","):
            pair = pair.strip()
            if "=" not in pair:
                continue
            jname, jval = pair.split("=", 1)
            jname = jname.strip()
            # Accept bare number (e.g. "3") or "Joint3" form
            if jname.isdigit():
                jname = f"Joint{jname}"
            jt[jname] = float(jval.strip())
        analyzer.joint_tolerances = jt

    report = analyzer.analyze()

    # task 8.5 — apply joint/severity output filters
    if parsed_filters.get("severity"):
        allowed_sev = parsed_filters["severity"]
        report.issues = [i for i in report.issues if i.severity in allowed_sev]
    if parsed_filters.get("joint"):
        allowed_joints = parsed_filters["joint"]
        # Normalize: accept "3" or "Joint3"
        normalized_joints: set[str] = set()
        for j in allowed_joints:
            normalized_joints.add(j)
            if j.isdigit():
                normalized_joints.add(f"Joint{j}")
            elif j.startswith("Joint") and j[5:].isdigit():
                normalized_joints.add(j[5:])
        report.issues = [
            i
            for i in report.issues
            if not i.affected_nodes
            or any(n in normalized_joints for n in i.affected_nodes)
            or i.category not in ("motor", "arm", "hardware")
        ]

    # task 16.3 — store report reference for executive summary access
    analyzer._last_report = report

    # --field-summary (new, groups 16-17, 20, 24)
    if args.field_summary:
        from . import reports

        if args.json:
            # When both --json and --field-summary are set, generate the
            # field summary data and fold it into the JSON report instead
            # of printing the human-readable version.
            analyzer.field_summary = reports.generate_field_summary(
                analyzer, verbose=args.verbose,
            )
            # Fall through to the --json handler below
        else:
            reports.print_field_summary(
                analyzer, verbose=args.verbose,
            )
            return

    # --csv (tasks 18.1-18.3)
    if args.csv:
        import csv as _csv_mod  # noqa: F401 — lazy import verified present

        from . import exporters

        out_dir = Path(args.output) if args.output else Path(args.log_directory)
        # If --output looks like a file (has .csv suffix), use parent dir
        if out_dir.suffix.lower() == ".csv":
            out_dir = out_dir.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.csv == "events":
            path = exporters.export_csv_events(analyzer, out_dir)
            print(f"CSV events written to {path}")
        else:
            path = exporters.export_csv_metrics(analyzer, out_dir)
            print(f"CSV metrics written to {path}")
        return

    # --html (tasks 18.4-18.5)
    if args.html:
        import html as _html_mod  # noqa: F401 — lazy import verified present

        from . import exporters

        out_path = Path(args.output) if args.output else Path(args.log_directory) / "report.html"
        exporters.export_html(analyzer, out_path)
        print(f"HTML report written to {out_path}")
        return

    # --compare (tasks 18.6-18.7)
    if args.compare:
        if not os.path.exists(args.compare):
            print(f"{Colors.RED}Error: compare directory {args.compare} does not exist{Colors.RESET}")
            sys.exit(1)
        from . import exporters

        exporters.compare_sessions(analyzer, args.compare)
        return

    # Default output modes (unchanged behaviour)
    if args.json:
        if args.output:
            from dataclasses import asdict as _asdict

            with open(args.output, "w") as fh:
                json.dump(_asdict(report), fh, indent=2, default=str)
            print(f"Report saved to {args.output}")
        else:
            print_json_report(report, args, analyzer=analyzer)
    else:
        if args.timeline:
            print_timeline(report)
        else:
            print_report(report, summary_only=args.summary)

        if args.output:
            with open(args.output, "w") as fh:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    if args.timeline:
                        print_timeline(report)
                    else:
                        print_report(report, summary_only=args.summary)
                fh.write(buf.getvalue())
            print(f"Report saved to {args.output}")
