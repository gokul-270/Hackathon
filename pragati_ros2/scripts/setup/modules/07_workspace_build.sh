#!/bin/bash
################################################################################
# Module 07: Workspace Build
# Builds the ROS2 workspace
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
source "${SCRIPT_DIR}/../common.sh"

log_step "Building ROS2 workspace"

cd "$PROJECT_ROOT"

# Source ROS2
if [ -f "/opt/ros/jazzy/setup.bash" ]; then
    source /opt/ros/jazzy/setup.bash
else
    log_error "ROS2 not found, cannot build workspace"
    exit 1
fi

# Install dependencies
log_step "Installing ROS dependencies"
rosdep install --from-paths src --ignore-src -r -y || log_warn "Some rosdep packages not found (may be expected)"

# Build — capture output so we can detect silent package failures
log_install "ROS2 workspace (colcon build)" "colcon"
COLCON_OUT="/tmp/colcon_out_$$.txt"
colcon build --symlink-install 2>&1 | tee "$COLCON_OUT"
COLCON_EXIT="${PIPESTATUS[0]}"

# colcon exits 0 even when individual packages fail — check output too
if grep -q "packages failed\|Failed   <<<" "$COLCON_OUT" || [ "$COLCON_EXIT" -ne 0 ]; then
    rm -f "$COLCON_OUT"
    log_fail "workspace build" "packages failed — see output above"
    exit 1
fi

# Extract per-package build timings from colcon output (e.g. "Finished <<< pkg [12.3s]")
if [ -n "${TIMING_FILE:-}" ]; then
    grep "^Finished <<< " "$COLCON_OUT" \
        | sed 's/^Finished <<< \([^ ]*\) \[\(.*\)\]/PKGTIME|\1|\2/' \
        >> "$TIMING_FILE" || true
fi

rm -f "$COLCON_OUT"
log_success "workspace build" "all packages built"
log_info "Source the workspace: source install/setup.bash"
