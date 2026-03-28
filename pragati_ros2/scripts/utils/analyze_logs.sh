#!/bin/bash
# Quick wrapper for log_analyzer.py
# Usage: ./analyze_logs.sh <log_directory> [options]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZER="${SCRIPT_DIR}/../log_analyzer/"

# If no arguments, show help
if [ $# -eq 0 ]; then
    echo "ROS2 Log Analyzer - Quick Usage"
    echo "================================"
    echo ""
    echo "Usage: $0 <log_directory> [options]"
    echo ""
    echo "Options:"
    echo "  --summary    Show quick summary only"
    echo "  --json       Output as JSON"
    echo "  --watch      Watch mode (live monitoring)"
    echo "  --verbose    Include all details"
    echo ""
    echo "Examples:"
    echo "  $0 ~/Downloads/2025-12-18-09-03-56-*"
    echo "  $0 /var/log/ros2 --summary"
    echo "  $0 ~/.ros/log/latest --json > report.json"
    echo ""
    echo "Recent log directories:"
    ls -dt ~/Downloads/20*-*-*-*-ubuntu-* 2>/dev/null | head -5
    ls -dt ~/.ros/log/20*-* 2>/dev/null | head -3
    exit 0
fi

python3 "$ANALYZER" "$@"
