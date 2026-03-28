#!/bin/bash
# ============================================
# Pragati Robot — Web UI Launch Script
# ============================================
#
# Starts the FastAPI backend (serves web UI + REST API),
# optionally starts rosbridge_server and Gazebo simulation.
#
# Usage:
#   ./launch_web_ui.sh                        # Start Gazebo + rosbridge + FastAPI
#   ./launch_web_ui.sh --no-bridge            # Skip rosbridge (running elsewhere)
#   ./launch_web_ui.sh --no-gazebo            # Skip Gazebo (running elsewhere)
#   ./launch_web_ui.sh --no-bridge --no-gazebo  # FastAPI backend only
#
# Prerequisites:
#   - Python: pip install fastapi uvicorn[standard]
#   - For rosbridge: sudo apt install ros-jazzy-rosbridge-suite
#   - ROS2 Jazzy sourced (auto-detected)
#
# Access from Windows browser:
#   1. Find WSL IP:  hostname -I | awk '{print $1}'
#   2. Open browser: http://<WSL_IP>:8888
#   3. The UI will auto-connect to ws://<WSL_IP>:9090 for rosbridge
#
# Ports:
#   8888 — FastAPI backend (web UI + REST API)
#   9090 — WebSocket rosbridge_server
#
# To stop: Ctrl+C (kills all child processes)
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTTP_PORT="${HTTP_PORT:-8888}"
ROSBRIDGE_PORT="${ROSBRIDGE_PORT:-9090}"
NO_BRIDGE=false
NO_GAZEBO=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --no-bridge) NO_BRIDGE=true ;;
        --no-gazebo) NO_GAZEBO=true ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Pragati Robot — Web UI${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ---- Kill any existing processes first ----
echo -e "${CYAN}Cleaning up any existing processes...${NC}"
KILLED_ANY=false
# Kill Gazebo simulation processes
pkill -9 -f "gz sim" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing Gazebo processes${NC}" || true
# Kill ROS2 launch processes (covers gazebo_sensors.launch.py and rosbridge)
pkill -9 -f "ros2 launch" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing ROS2 launch processes${NC}" || true
# Kill parameter bridge (Gazebo <-> ROS2 bridge)
pkill -9 -f "parameter_bridge" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing parameter bridge processes${NC}" || true
# Kill rosbridge WebSocket server
pkill -9 -f "rosbridge" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing rosbridge processes${NC}" || true
# Kill kinematics node
pkill -9 -f "kinematics_node" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing kinematics node processes${NC}" || true
# Kill robot_state_publisher
pkill -9 -f "robot_state_publisher" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing robot_state_publisher processes${NC}" || true
# Kill FastAPI backend
pkill -9 -f "uvicorn.*backend" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed existing FastAPI backend processes${NC}" || true
pkill -9 -f "backend\.py" 2>/dev/null && KILLED_ANY=true || true
if [ "$KILLED_ANY" = true ]; then
    echo -e "${YELLOW}  Waiting for processes to terminate...${NC}"
    sleep 3
else
    echo -e "${GREEN}  No existing processes found${NC}"
fi
echo ""

# ---- Task 40 (9.4): pip dependency check ----
echo -e "${CYAN}Checking Python dependencies...${NC}"
DEPS_OK=true
for pkg in fastapi uvicorn; do
    if ! python3 -c "import $pkg" 2>/dev/null; then
        echo -e "${YELLOW}WARNING: Python package '$pkg' not found${NC}"
        DEPS_OK=false
    fi
done
if [ "$DEPS_OK" = false ]; then
    echo -e "${YELLOW}Install missing packages with: pip install fastapi uvicorn[standard]${NC}"
    echo -e "${YELLOW}Continuing anyway (packages may be installed but not in current PATH)...${NC}"
else
    echo -e "${GREEN}  All Python dependencies found${NC}"
fi
echo ""

# Get WSL IP for display
WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$WSL_IP" ]; then
    WSL_IP="localhost"
fi

# Track PIDs for cleanup
PIDS=()
GAZEBO_PID=""
ROSBRIDGE_PID=""
BACKEND_PID=""

# ---- Task 39 (9.3): Ctrl+C cleanup ----
cleanup() {
    echo ""
    echo -e "${CYAN}Shutting down all processes...${NC}"

    # Send SIGTERM to all tracked processes
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            local label="Process $pid"
            if [ "$pid" = "$GAZEBO_PID" ]; then label="Gazebo ($pid)"; fi
            if [ "$pid" = "$ROSBRIDGE_PID" ]; then label="Rosbridge ($pid)"; fi
            if [ "$pid" = "$BACKEND_PID" ]; then label="FastAPI backend ($pid)"; fi
            echo -e "${YELLOW}  Stopping $label...${NC}"
            kill -SIGTERM "$pid" 2>/dev/null
        fi
    done

    # Grace period — wait up to 5 seconds for clean exit
    local grace=5
    for pid in "${PIDS[@]}"; do
        local waited=0
        while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$grace" ]; do
            sleep 1
            waited=$((waited + 1))
        done
        # Force kill if still alive
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${RED}  Force-killing PID $pid...${NC}"
            kill -SIGKILL "$pid" 2>/dev/null
        fi
        wait "$pid" 2>/dev/null
    done

    # Also kill any remaining child processes by pattern (catches Gazebo subprocesses)
    pkill -9 -f "gz sim" 2>/dev/null || true
    pkill -9 -f "parameter_bridge" 2>/dev/null || true
    pkill -9 -f "kinematics_node" 2>/dev/null || true
    pkill -9 -f "robot_state_publisher" 2>/dev/null || true

    echo -e "${GREEN}All processes stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ---- Source ROS2 environment ----
# Needed for Gazebo and rosbridge; do it early so both can use it
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

# Source workspace if available
WORKSPACE_SETUP="$(dirname "$SCRIPT_DIR")/../../../../install/setup.bash"
if [ -f "$WORKSPACE_SETUP" ]; then
    source "$WORKSPACE_SETUP" 2>/dev/null
    echo -e "${GREEN}Sourced workspace${NC}"
fi
echo ""

# ---- Task 37 (9.1): Launch Gazebo + wait for readiness ----
if [ "$NO_GAZEBO" = true ]; then
    echo -e "${YELLOW}Skipping Gazebo (--no-gazebo flag set)${NC}"
    echo -e "${YELLOW}Make sure Gazebo is running separately if needed${NC}"
    echo ""
elif [ "$ROS_SOURCED" = false ]; then
    echo -e "${YELLOW}WARNING: ROS2 not available — skipping Gazebo launch${NC}"
    echo ""
else
    echo -e "${CYAN}Launching Gazebo simulation (with sensors)...${NC}"
    ros2 launch vehicle_control gazebo_sensors.launch.py \
        > /tmp/gazebo_ros2.log 2>&1 &
    GAZEBO_PID=$!
    PIDS+=($GAZEBO_PID)
    echo -e "${GREEN}  Gazebo PID: ${GAZEBO_PID}${NC}"

    # Wait for Gazebo readiness by checking for gz sim processes
    # NOTE: We avoid ros2 topic list here because DDS discovery can hang in WSL
    GAZEBO_TIMEOUT=30
    GAZEBO_READY=false
    echo -ne "${CYAN}  Waiting for Gazebo readiness "
    for ((i=1; i<=GAZEBO_TIMEOUT; i++)); do
        # Check if Gazebo process is still alive
        if ! kill -0 "$GAZEBO_PID" 2>/dev/null; then
            echo -e "${NC}"
            echo -e "${RED}  Gazebo process exited unexpectedly (check /tmp/gazebo.log)${NC}"
            break
        fi
        # Check if gz sim server process has started (indicates Gazebo is running)
        if pgrep -f "gz sim server" >/dev/null 2>&1; then
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
        echo -e "${YELLOW}  Continuing anyway — check /tmp/gazebo.log for details${NC}"
    fi
    echo ""
fi

# ---- Task 38 (9.2): Start rosbridge ----
if [ "$NO_BRIDGE" = true ]; then
    echo -e "${YELLOW}Skipping rosbridge (--no-bridge flag set)${NC}"
    echo -e "${YELLOW}Make sure rosbridge_server is running separately on port ${ROSBRIDGE_PORT}${NC}"
elif [ "$ROS_SOURCED" = false ]; then
    echo -e "${YELLOW}WARNING: ROS2 not available — skipping rosbridge${NC}"
    echo -e "${YELLOW}The web UI will load but won't connect to ROS2${NC}"
else
    # Check rosbridge availability
    # NOTE: We avoid `ros2 pkg prefix` here because it triggers DDS discovery
    # which can hang indefinitely in WSL/network-constrained environments.
    # Instead, check for the launch file directly.
    ROSBRIDGE_AVAILABLE=false
    ROSBRIDGE_LAUNCH="/opt/ros/${ROS_DISTRO}/share/rosbridge_server/launch/rosbridge_websocket_launch.xml"
    if [ -f "$ROSBRIDGE_LAUNCH" ]; then
        ROSBRIDGE_AVAILABLE=true
    fi

    if [ "$ROSBRIDGE_AVAILABLE" = true ]; then
        echo -e "${CYAN}Starting rosbridge_server on port ${ROSBRIDGE_PORT}...${NC}"
        ros2 launch rosbridge_server rosbridge_websocket_launch.xml \
            port:="${ROSBRIDGE_PORT}" \
            address:="0.0.0.0" \
            > /tmp/rosbridge.log 2>&1 &
        ROSBRIDGE_PID=$!
        PIDS+=($ROSBRIDGE_PID)
        echo -e "${GREEN}  Rosbridge PID: ${ROSBRIDGE_PID}${NC}"
        echo -e "${GREEN}  WebSocket: ws://${WSL_IP}:${ROSBRIDGE_PORT}${NC}"
    else
        echo -e "${YELLOW}WARNING: rosbridge_server not installed${NC}"
        echo -e "${YELLOW}Install with: sudo apt install ros-jazzy-rosbridge-suite${NC}"
        echo -e "${YELLOW}The web UI will load but won't connect to ROS2 topics${NC}"
    fi
fi
echo ""

# ---- Task 38 (9.2): Start FastAPI backend ----
echo -e "${CYAN}Starting FastAPI backend on port ${HTTP_PORT}...${NC}"
python3 "$SCRIPT_DIR/backend.py" \
    > /tmp/web_ui_backend.log 2>&1 &
BACKEND_PID=$!
PIDS+=($BACKEND_PID)
echo -e "${GREEN}  FastAPI backend PID: ${BACKEND_PID}${NC}"
echo -e "${GREEN}  URL: http://${WSL_IP}:${HTTP_PORT}${NC}"
echo ""

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} Web UI ready: http://${WSL_IP}:${HTTP_PORT}${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "${YELLOW}Logs:${NC}"
echo -e "${YELLOW}  Backend:   /tmp/web_ui_backend.log${NC}"
if [ "$NO_BRIDGE" = false ]; then
    echo -e "${YELLOW}  Rosbridge: /tmp/rosbridge.log${NC}"
fi
if [ "$NO_GAZEBO" = false ]; then
    echo -e "${YELLOW}  Gazebo:    /tmp/gazebo.log${NC}"
fi
echo -e "${YELLOW}Press Ctrl+C to stop all processes.${NC}"
echo ""

# Wait for any child process to exit
wait
