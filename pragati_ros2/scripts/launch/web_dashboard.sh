#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
SCRIPT="$ROOT_DIR/web_dashboard/run_dashboard.py"

if [[ ! -f "$SCRIPT" ]]; then
  echo "[web-dashboard] Missing launcher at $SCRIPT" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[web-dashboard] python3 not found in PATH" >&2
  exit 1
fi

if [[ -z "${ROS_DISTRO:-}" ]]; then
  echo "[web-dashboard] ROS2 environment not sourced (ROS_DISTRO unset)" >&2
  echo "  source /opt/ros/jazzy/setup.bash" >&2
fi

echo "[web-dashboard] Starting dashboard via $SCRIPT"
exec python3 "$SCRIPT" "$@"
