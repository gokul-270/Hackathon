#!/bin/bash
# Pragati ROS2 Project Status Script

# Resolve repo root relative to this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Pragati ROS2 Project Status ==="
echo
echo "Project Root: $REPO_ROOT"
echo "ROS Log Directory: $ROS_LOG_DIR"
echo "Current Directory: $(pwd)"
echo

# Show workspace status
echo "=== Workspace Status ==="
if [ -f "$REPO_ROOT/install/setup.bash" ]; then
    echo "✅ Workspace built (install/setup.bash exists)"
else
    echo "❌ Workspace not built (run: colcon build)"
fi

# Show log status
"$REPO_ROOT/scripts/monitoring/clean_logs.sh" status

# Show running ROS2 processes
echo
echo "=== Active ROS2 Processes ==="
if pgrep -f "ros2" > /dev/null; then
    echo "✅ ROS2 processes running:"
    pgrep -af "ros2" | head -5
else
    echo "❌ No ROS2 processes running"
fi

# Show recent activity
echo
echo "=== Recent Activity ==="
if [ -d "$REPO_ROOT/logs" ]; then
    recent_logs=$(find "$REPO_ROOT/logs" -name "*.log" -mtime -1 2>/dev/null | wc -l)
    echo "Recent log files (last 24h): $recent_logs"
else
    echo "No recent activity"
fi
