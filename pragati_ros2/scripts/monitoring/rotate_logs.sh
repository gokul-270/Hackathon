#!/bin/bash
# Log rotation script for Pragati ROS2 project

# Resolve repo root relative to this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
logrotate -s "$REPO_ROOT/logs/.logrotate_status" "$REPO_ROOT/configs/logrotate.conf" -v
