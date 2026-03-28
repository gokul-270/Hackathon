#!/bin/bash
# ============================================
# Vehicle + Arm Sim — URDF Editor + Gazebo Launch Script
# ============================================
#
# Starts Gazebo simulation (vehicle_arm_sim), then the FastAPI-based
# URDF editor backend (which serves the web UI on port 8080).
#
# Usage:
#   ./launch_web_ui.sh                  # Start Gazebo + Web UI
#   ./launch_web_ui.sh --no-gazebo      # Web UI only (Gazebo already running)
#   ./launch_web_ui.sh --headless       # Gazebo server only (no GUI window)
#
# Access from browser:
#   1. Find IP:  hostname -I | awk '{print $1}'
#   2. Open: http://<IP>:8080
#
# Ports:
#   8080 — FastAPI backend (URDF editor web UI + REST API)
#
# To stop: Ctrl+C (kills all child processes)
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$PKG_DIR/../.." && pwd)"
HTTP_PORT="${HTTP_PORT:-8080}"
NO_GAZEBO=false
HEADLESS=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --no-gazebo) NO_GAZEBO=true ;;
        --headless)  HEADLESS=true ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Vehicle + Arm Sim — URDF Editor${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ---- Kill any existing processes first ----
echo -e "${CYAN}Cleaning up any existing processes...${NC}"
KILLED_ANY=false
pkill -9 -f "gz sim" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing Gazebo processes${NC}" || true
pkill -9 -f "ros2 launch.*vehicle_arm_sim" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing vehicle_arm_sim launch${NC}" || true
pkill -9 -f "parameter_bridge" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing parameter bridge${NC}" || true
pkill -9 -f "robot_state_publisher" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing robot_state_publisher${NC}" || true
pkill -9 -f "editor_backend" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing editor backend${NC}" || true
pkill -9 -f "uvicorn.*editor" 2>/dev/null && KILLED_ANY=true || true
if [ "$KILLED_ANY" = true ]; then
    echo -e "${YELLOW}  Waiting for processes to terminate...${NC}"
    sleep 3
else
    echo -e "${GREEN}  No existing processes found${NC}"
fi
echo ""

# ---- Check Python dependencies ----
echo -e "${CYAN}Checking Python dependencies...${NC}"
DEPS_OK=true

# Activate venv if present
if [ -f "$WORKSPACE_ROOT/venv/bin/activate" ]; then
    source "$WORKSPACE_ROOT/venv/bin/activate"
    echo -e "${GREEN}  Activated venv${NC}"
fi

for pkg in fastapi uvicorn multipart; do
    if ! python3 -c "import $pkg" 2>/dev/null; then
        echo -e "${YELLOW}WARNING: Python package '$pkg' not found${NC}"
        DEPS_OK=false
    fi
done
if [ "$DEPS_OK" = false ]; then
    echo -e "${YELLOW}Install with: pip install fastapi uvicorn[standard] python-multipart${NC}"
    echo -e "${YELLOW}Continuing anyway...${NC}"
else
    echo -e "${GREEN}  All Python dependencies found${NC}"
fi
echo ""

# Get IP for display
WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$WSL_IP" ]; then
    WSL_IP="localhost"
fi

# Track PIDs for cleanup
PIDS=()
GAZEBO_PID=""
BACKEND_PID=""

# ---- Cleanup on Ctrl+C ----
cleanup() {
    echo ""
    echo -e "${CYAN}Shutting down all processes...${NC}"

    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            local label="Process $pid"
            if [ "$pid" = "$GAZEBO_PID" ]; then label="Gazebo ($pid)"; fi
            if [ "$pid" = "$BACKEND_PID" ]; then label="URDF Editor backend ($pid)"; fi
            echo -e "${YELLOW}  Stopping $label...${NC}"
            kill -SIGTERM "$pid" 2>/dev/null
        fi
    done

    # Grace period
    local grace=5
    for pid in "${PIDS[@]}"; do
        local waited=0
        while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$grace" ]; do
            sleep 1
            waited=$((waited + 1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${RED}  Force-killing PID $pid...${NC}"
            kill -SIGKILL "$pid" 2>/dev/null
        fi
        wait "$pid" 2>/dev/null
    done

    # Kill any remaining child processes
    pkill -9 -f "gz sim" 2>/dev/null || true
    pkill -9 -f "parameter_bridge" 2>/dev/null || true
    pkill -9 -f "robot_state_publisher" 2>/dev/null || true

    echo -e "${GREEN}All processes stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ---- Source ROS2 environment ----
ROS_SOURCED=false
if [ -z "$ROS_DISTRO" ]; then
    if [ -f /opt/ros/jazzy/setup.bash ]; then
        source /opt/ros/jazzy/setup.bash
        echo -e "${GREEN}Sourced ROS2 Jazzy${NC}"
        ROS_SOURCED=true
    else
        echo -e "${YELLOW}WARNING: ROS2 not found at /opt/ros/jazzy/setup.bash${NC}"
    fi
else
    ROS_SOURCED=true
fi

# Source workspace install if available
WORKSPACE_SETUP="$WORKSPACE_ROOT/install/setup.bash"
if [ -f "$WORKSPACE_SETUP" ]; then
    source "$WORKSPACE_SETUP" 2>/dev/null
    echo -e "${GREEN}Sourced workspace: $WORKSPACE_SETUP${NC}"
fi
echo ""

# ---- Launch Gazebo simulation ----
if [ "$NO_GAZEBO" = true ]; then
    echo -e "${YELLOW}Skipping Gazebo (--no-gazebo flag set)${NC}"
    echo ""
elif [ "$ROS_SOURCED" = false ]; then
    echo -e "${YELLOW}WARNING: ROS2 not available — skipping Gazebo launch${NC}"
    echo ""
else
    echo -e "${CYAN}Launching Gazebo simulation (vehicle + arm)...${NC}"

    HEADLESS_ARG="false"
    if [ "$HEADLESS" = true ]; then
        HEADLESS_ARG="true"
        echo -e "${YELLOW}  Running headless (no GUI window)${NC}"
    fi

    # Detect latest saved URDF from editor (session file or source saved/ dir)
    URDF_OVERRIDE=""
    SESSION_URDF="$HOME/.vehicle_arm_sim/latest_editor.urdf"
    if [ -f "$SESSION_URDF" ]; then
        URDF_OVERRIDE="$SESSION_URDF"
        echo -e "${GREEN}  Using editor session URDF: $SESSION_URDF${NC}"
    else
        LATEST_SAVED=$(ls -t "$PKG_DIR/urdf/saved/"*.urdf 2>/dev/null | head -1)
        if [ -n "$LATEST_SAVED" ]; then
            URDF_OVERRIDE="$LATEST_SAVED"
            echo -e "${GREEN}  Using saved URDF: $LATEST_SAVED${NC}"
        fi
    fi

    # Export for the launch file to pick up (works with updated launch file)
    if [ -n "$URDF_OVERRIDE" ]; then
        export VEHICLE_ARM_URDF_FILE="$URDF_OVERRIDE"

        # Also copy the URDF into the install tree's saved/ directory so the
        # launch file's built-in saved-dir detection finds it (works even if
        # the launch file hasn't been rebuilt with the env-var code).
        INSTALL_PKG_SHARE="$WORKSPACE_ROOT/install/vehicle_arm_sim/share/vehicle_arm_sim"
        if [ -d "$INSTALL_PKG_SHARE" ]; then
            INSTALL_SAVED="$INSTALL_PKG_SHARE/urdf/saved"
            mkdir -p "$INSTALL_SAVED"
            cp -f "$URDF_OVERRIDE" "$INSTALL_SAVED/editor_latest.urdf"
            # Touch so it's newest
            touch "$INSTALL_SAVED/editor_latest.urdf"
            echo -e "${GREEN}  Copied URDF to install tree for Gazebo${NC}"
        fi
    fi

    ros2 launch vehicle_arm_sim vehicle_arm.launch.py \
        headless:="$HEADLESS_ARG" \
        > /tmp/vehicle_arm_gazebo.log 2>&1 &
    GAZEBO_PID=$!
    PIDS+=($GAZEBO_PID)
    echo -e "${GREEN}  Gazebo launch PID: ${GAZEBO_PID}${NC}"

    # Wait for Gazebo readiness
    GAZEBO_TIMEOUT=45
    GAZEBO_READY=false
    echo -ne "${CYAN}  Waiting for Gazebo readiness "
    for ((i=1; i<=GAZEBO_TIMEOUT; i++)); do
        if ! kill -0 "$GAZEBO_PID" 2>/dev/null; then
            echo -e "${NC}"
            echo -e "${RED}  Gazebo process exited unexpectedly!${NC}"
            echo -e "${RED}  Check log: /tmp/vehicle_arm_gazebo.log${NC}"
            break
        fi
        # Check for gz sim server process
        if pgrep -f "gz sim" >/dev/null 2>&1; then
            GAZEBO_READY=true
            echo -e "${NC}"
            echo -e "${GREEN}  Gazebo is ready (took ${i}s)${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
    if [ "$GAZEBO_READY" = false ] && kill -0 "$GAZEBO_PID" 2>/dev/null; then
        echo -e "${NC}"
        echo -e "${YELLOW}  WARNING: Gazebo did not become ready within ${GAZEBO_TIMEOUT}s${NC}"
        echo -e "${YELLOW}  Continuing anyway — check /tmp/vehicle_arm_gazebo.log${NC}"
    fi
    echo ""
fi

# ---- Start URDF Editor FastAPI backend ----
echo -e "${CYAN}Starting URDF Editor backend on port ${HTTP_PORT}...${NC}"
python3 "$SCRIPT_DIR/editor_backend.py" --port "$HTTP_PORT" \
    > /tmp/urdf_editor_backend.log 2>&1 &
BACKEND_PID=$!
PIDS+=($BACKEND_PID)

# Wait briefly for backend to start
sleep 2
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo -e "${RED}  Backend failed to start! Check /tmp/urdf_editor_backend.log${NC}"
else
    echo -e "${GREEN}  URDF Editor PID: ${BACKEND_PID}${NC}"
fi
echo ""

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} URDF Editor: http://${WSL_IP}:${HTTP_PORT}${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}Logs:${NC}"
echo -e "${YELLOW}  Backend: /tmp/urdf_editor_backend.log${NC}"
if [ "$NO_GAZEBO" = false ] && [ "$ROS_SOURCED" = true ]; then
    echo -e "${YELLOW}  Gazebo:  /tmp/vehicle_arm_gazebo.log${NC}"
fi
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all processes.${NC}"
echo ""

# Wait for any child process to exit
wait
