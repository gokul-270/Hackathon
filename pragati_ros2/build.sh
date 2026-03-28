#!/bin/bash

################################################################################
# Pragati ROS2 Build Script
#
# This script builds the ROS2 workspace using colcon build
################################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color
DIM='\033[2m'

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$SCRIPT_DIR"
CLEAN_BUILD=false
FAST_MODE=false
PACKAGE_NAME=""
BUILD_MODE="standard"  # standard, fast, full, audit, arm, vehicle
BUILD_START_TIME=$(date +%s)

# Watchdog configuration
# Defaults: overall=20min, per-package=10min, inactivity=5min
# All can be overridden by env vars or CLI flags (CLI takes precedence)
WATCHDOG_ENABLED=true
OVERALL_TIMEOUT="${BUILD_TIMEOUT_SECS:-1200}"
PKG_TIMEOUT="${PKG_TIMEOUT_SECS:-600}"
INACTIVITY_TIMEOUT="${INACTIVITY_TIMEOUT_SECS:-300}"

# Memory floor: 512MB on 8GB+ systems, 256MB on <8GB (auto-detected later)
MEM_FLOOR_MB="${MEM_FLOOR_MB:-auto}"

# Watchdog event log (temp file for summary report)
WATCHDOG_LOG=""
WATCHDOG_PIDS_STOPPED=()  # PIDs currently SIGSTOPped by memory watchdog
MEMORY_MONITOR_PID=""      # PID of the background memory monitor

# ============================================================================
# Load Configuration
# ============================================================================

CONFIG_FILE="$WORKSPACE_ROOT/config.env"
PROFILE_NAME=""

# Load config.env if it exists
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# Helper function to load profile settings
load_profile() {
    local profile="$1"
    if [ -z "$profile" ]; then
        return 0
    fi

    local profile_upper=$(echo "$profile" | tr '[:lower:]' '[:upper:]')

    # Load profile-specific variables
    local ip_var="${profile_upper}_IP"
    local user_var="${profile_upper}_USER"
    local dir_var="${profile_upper}_TARGET_DIR"
    local key_var="${profile_upper}_SSH_KEY"
    local sysroot_var="${profile_upper}_SYSROOT"

    # Override defaults with profile values if they exist
    if [ -n "${!ip_var}" ]; then
        export RPI_IP="${!ip_var}"
    fi
    if [ -n "${!user_var}" ]; then
        export RPI_USER="${!user_var}"
    fi
    if [ -n "${!dir_var}" ]; then
        export RPI_TARGET_DIR="${!dir_var}"
    fi
    if [ -n "${!key_var}" ]; then
        export RPI_SSH_KEY="${!key_var}"
    fi
    if [ -n "${!sysroot_var}" ]; then
        export RPI_SYSROOT="${!sysroot_var}"
    fi
}

# Apply config defaults (can be overridden by environment or command line)
RPI_SYSROOT="${RPI_SYSROOT:-$HOME/rpi-sysroot}"
BUILD_PACKAGES="${BUILD_PACKAGES:-}"

# Auto-detect platform and set parallel workers
# Rule: Use (nproc - 2) to leave cores for OS, with minimum of 2
# Also consider RAM: ~1.5GB per compiler process is safe
# Note: PARALLEL_WORKERS controls BOTH colcon --parallel-workers AND
# CMAKE_BUILD_PARALLEL_LEVEL (per-package -j), so total max compilers
# is PARALLEL_WORKERS² in the worst case.
if [[ $(uname -m) == "aarch64" ]] && grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    PARALLEL_WORKERS=1  # RPi: safest default, avoids OOM / SSH hangs
    IS_RPI=true
else
    # Desktop/WSL: Calculate based on cores and RAM
    TOTAL_CORES=$(nproc)
    TOTAL_RAM_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)

    # Workers based on cores: nproc - 2 (leave 2 for system), minimum 2
    WORKERS_BY_CORES=$((TOTAL_CORES - 2))
    [[ $WORKERS_BY_CORES -lt 2 ]] && WORKERS_BY_CORES=2

    # Workers based on RAM: ~1.5GB per compiler process.
    # With PARALLEL_WORKERS² worst-case compilers, we solve for
    # W where W² × 1.5 ≤ available_RAM_GB. For 8GB: sqrt(8/1.5) ≈ 2.3 → 2.
    # But in practice packages rarely all compile simultaneously, so we
    # use a linear estimate of RAM_GB / 2 (assumes ~2GB per effective slot)
    # and cap at 4 to stay safe on ≤8GB systems (4²=16 worst-case × 0.5GB avg ≈ 8GB).
    WORKERS_BY_RAM=$((TOTAL_RAM_GB / 2))
    [[ $WORKERS_BY_RAM -lt 2 ]] && WORKERS_BY_RAM=2
    [[ $WORKERS_BY_RAM -gt 4 ]] && WORKERS_BY_RAM=4  # cap at 4 for ≤8GB safety

    # Use the smaller of the two
    if [[ $WORKERS_BY_CORES -lt $WORKERS_BY_RAM ]]; then
        PARALLEL_WORKERS=$WORKERS_BY_CORES
    else
        PARALLEL_WORKERS=$WORKERS_BY_RAM
    fi

    IS_RPI=false
fi

# Function to print formatted messages
print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "${CYAN}🚀 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${PURPLE}ℹ️  $1${NC}"
}

# Timestamp prefixer for build output.
# Prefixes every line with [HH:MM:SS +Δs] so you can see exactly when each
# compiler command runs, which file is stuck, and how long each step takes.
timestamp_prefix() {
    local start_ts=$(date +%s)
    awk -v start="$start_ts" '
    {
        cmd = "date +%H:%M:%S"
        cmd | getline ts
        close(cmd)

        # Compute elapsed seconds since build start
        cmd2 = "date +%s"
        cmd2 | getline now
        close(cmd2)
        elapsed = now - start

        # Format elapsed as M:SS
        mins = int(elapsed / 60)
        secs = elapsed % 60
        printf "[%s +%d:%02d] %s\n", ts, mins, secs, $0
        fflush()
    }'
}

# ============================================================================
# Build Watchdog System
# ============================================================================
# Monitors build processes for timeouts, inactivity, and memory pressure.
# Prevents OS crashes from OOM by throttling/killing builds before the
# kernel OOM killer fires (which often freezes the system entirely).
#
# Three timeout mechanisms:
#   1. Overall build timeout (default 20min)
#   2. Per-package timeout (default 10min) — NOT enforced via this watchdog
#      because colcon manages package scheduling internally; we rely on
#      overall + inactivity timeouts to catch stuck packages.
#   3. Inactivity timeout (default 5min) — kills if no output for N seconds
#
# Memory protection:
#   - Polls /proc/meminfo every 5 seconds
#   - SIGSTOP compiler processes when available < floor
#   - SIGCONT when available > 1.5x floor
#   - SIGKILL (abort build) when available < 50% floor

# Emit a structured watchdog log entry to stderr and append to log file
watchdog_log() {
    local event_type="$1"
    shift
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local msg="[BUILD-WATCHDOG] $timestamp $event_type $*"
    echo "$msg" >&2
    if [ -n "$WATCHDOG_LOG" ]; then
        echo "$msg" >> "$WATCHDOG_LOG"
    fi
}

# Initialize the watchdog system
watchdog_init() {
    if [ "$WATCHDOG_ENABLED" != true ]; then
        return 0
    fi

    # Create temp file for watchdog event log
    WATCHDOG_LOG=$(mktemp /tmp/build-watchdog-XXXXXX.log 2>/dev/null || echo "")

    # Auto-detect memory floor if set to "auto"
    if [ "$MEM_FLOOR_MB" = "auto" ]; then
        local total_ram_mb
        total_ram_mb=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")
        if [ "$total_ram_mb" -ge 16384 ]; then
            MEM_FLOOR_MB=256
        elif [ "$total_ram_mb" -ge 8192 ]; then
            MEM_FLOOR_MB=64
        else
            MEM_FLOOR_MB=64
        fi
    fi

    # Ensure numeric values
    MEM_FLOOR_MB=${MEM_FLOOR_MB:-64}
}

# Display watchdog configuration in build header
watchdog_display_config() {
    if [ "$WATCHDOG_ENABLED" != true ]; then
        print_info "Watchdog: disabled"
        return 0
    fi

    local inactivity_str="${INACTIVITY_TIMEOUT}s"
    if [ "$INACTIVITY_TIMEOUT" = "0" ]; then
        inactivity_str="off"
    fi
    print_info "Watchdog: overall=${OVERALL_TIMEOUT}s pkg=${PKG_TIMEOUT}s inactivity=${inactivity_str}"

    # Display memory info
    local total_mb avail_mb
    total_mb=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")
    avail_mb=$(awk '/MemAvailable/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")
    local total_gb avail_gb
    total_gb=$(awk "BEGIN {printf \"%.1f\", $total_mb/1024}")
    avail_gb=$(awk "BEGIN {printf \"%.1f\", $avail_mb/1024}")
    print_info "Memory: ${total_gb}GB total, ${avail_gb}GB available, floor=${MEM_FLOOR_MB}MB"

    # Warn if memory is already low (available < 2x floor)
    local low_threshold=$((MEM_FLOOR_MB * 2))
    if [ "$avail_mb" -lt "$low_threshold" ]; then
        watchdog_log "WARNING" "Low memory at build start (${avail_mb}MB available). Consider closing applications or reducing parallelism."
    fi
}

# Pre-build resource validation (warnings only, non-blocking)
watchdog_pre_build_validate() {
    if [ "$WATCHDOG_ENABLED" != true ]; then
        return 0
    fi

    local avail_mb
    avail_mb=$(awk '/MemAvailable/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")

    # Check if parallelism might exceed available memory
    # Estimate: 1.5GB per compiler on x86_64, 0.8GB on aarch64
    local per_compiler_mb=1536
    if [[ $(uname -m) == "aarch64" ]]; then
        per_compiler_mb=819
    fi

    local estimated_mb=$((PARALLEL_WORKERS * per_compiler_mb))
    local avail_80=$((avail_mb * 80 / 100))

    if [ "$estimated_mb" -gt "$avail_80" ]; then
        # Calculate recommended workers
        local recommended=$((avail_80 / per_compiler_mb))
        [ "$recommended" -lt 1 ] && recommended=1
        local est_gb
        est_gb=$(awk "BEGIN {printf \"%.1f\", $estimated_mb/1024}")
        local avail_gb
        avail_gb=$(awk "BEGIN {printf \"%.1f\", $avail_mb/1024}")
        print_warning "WARNING: -j${PARALLEL_WORKERS} may use ~${est_gb}GB but only ${avail_gb}GB available. Recommended: -j${recommended}"
    fi

    # Check disk space
    local disk_free_mb
    disk_free_mb=$(df -m "$WORKSPACE_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$disk_free_mb" ] && [ "$disk_free_mb" -lt 2048 ]; then
        local disk_mount
        disk_mount=$(df "$WORKSPACE_ROOT" 2>/dev/null | awk 'NR==2 {print $6}')
        local disk_gb
        disk_gb=$(awk "BEGIN {printf \"%.1f\", $disk_free_mb/1024}")
        print_warning "WARNING: Only ${disk_gb}GB free on ${disk_mount}. Builds may fail or corrupt."
    fi

    # Check swap on low-memory systems
    local total_ram_mb
    total_ram_mb=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")
    if [ "$total_ram_mb" -lt 4096 ] || [ "$BUILD_MODE" = "rpi" ]; then
        local swap_total
        swap_total=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
        if [ "${swap_total:-0}" -eq 0 ]; then
            print_warning "WARNING: No swap configured on low-memory system. Builds may crash the OS."
        fi
    fi
}

# Get available memory in MB from /proc/meminfo
get_available_memory_mb() {
    awk '/MemAvailable/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0"
}

# Find compiler processes belonging to a process group
# Returns PIDs of cc1, cc1plus, as, ld processes
find_compiler_pids() {
    local pgid="$1"
    # Find compiler/linker processes in the process group
    # Use ps to find processes whose PGID matches, filtering for compiler names
    ps -eo pid,pgid,comm 2>/dev/null | awk -v pgid="$pgid" '
        $2 == pgid && ($3 == "cc1" || $3 == "cc1plus" || $3 == "as" || $3 == "ld" || $3 == "collect2" || $3 == "ninja" || $3 == "make") {
            print $1
        }
    '
}

# Memory monitor background process
# Runs in a loop, polling /proc/meminfo and throttling/killing as needed
memory_monitor_loop() {
    local build_pgid="$1"
    local floor_mb="$2"
    local resume_mb=$(( floor_mb * 3 / 2 ))  # 1.5x floor
    local critical_mb=$(( floor_mb / 2 ))      # 50% of floor
    local stopped_pids=()

    while true; do
        sleep 5

        # Check if build process group still exists
        if ! kill -0 "-$build_pgid" 2>/dev/null; then
            # Build is done, resume any stopped processes and exit
            for pid in "${stopped_pids[@]}"; do
                kill -CONT "$pid" 2>/dev/null || true
            done
            break
        fi

        local avail_mb
        avail_mb=$(get_available_memory_mb)

        # Critical: below 50% of floor — abort immediately
        if [ "$avail_mb" -lt "$critical_mb" ]; then
            watchdog_log "MEM-CRITICAL" "available=${avail_mb}MB floor=${floor_mb}MB action=abort"
            # Resume stopped processes first so they can be killed cleanly
            for pid in "${stopped_pids[@]}"; do
                kill -CONT "$pid" 2>/dev/null || true
            done
            stopped_pids=()
            # Kill the build process group
            kill -TERM "-$build_pgid" 2>/dev/null || true
            sleep 2
            kill -KILL "-$build_pgid" 2>/dev/null || true
            break
        fi

        # Below floor: throttle by stopping compiler processes
        if [ "$avail_mb" -lt "$floor_mb" ] && [ ${#stopped_pids[@]} -eq 0 ]; then
            local compiler_pids
            compiler_pids=$(find_compiler_pids "$build_pgid")
            if [ -n "$compiler_pids" ]; then
                local count=0
                for pid in $compiler_pids; do
                    kill -STOP "$pid" 2>/dev/null && {
                        stopped_pids+=("$pid")
                        count=$((count + 1))
                    }
                done
                if [ "$count" -gt 0 ]; then
                    watchdog_log "MEM-PRESSURE" "available=${avail_mb}MB floor=${floor_mb}MB action=throttle paused=${count}_processes"
                fi
            fi
        fi

        # Above resume threshold: resume stopped processes
        if [ "$avail_mb" -gt "$resume_mb" ] && [ ${#stopped_pids[@]} -gt 0 ]; then
            local count=0
            for pid in "${stopped_pids[@]}"; do
                kill -CONT "$pid" 2>/dev/null && count=$((count + 1))
            done
            watchdog_log "MEM-RESUME" "available=${avail_mb}MB floor=${floor_mb}MB action=resume resumed=${count}_processes"
            stopped_pids=()
        fi
    done
}

# Start the memory monitor in the background
start_memory_monitor() {
    local build_pgid="$1"
    if [ "$WATCHDOG_ENABLED" != true ]; then
        return 0
    fi
    # Run memory monitor as a background subshell
    memory_monitor_loop "$build_pgid" "$MEM_FLOOR_MB" &
    MEMORY_MONITOR_PID=$!
}

# Stop the memory monitor
stop_memory_monitor() {
    if [ -n "$MEMORY_MONITOR_PID" ]; then
        kill "$MEMORY_MONITOR_PID" 2>/dev/null || true
        wait "$MEMORY_MONITOR_PID" 2>/dev/null || true
        MEMORY_MONITOR_PID=""
    fi
}

# Kill a process group with SIGTERM then SIGKILL escalation
kill_process_group() {
    local pgid="$1"
    local grace_secs="${2:-10}"

    # Send SIGTERM to process group
    kill -TERM "-$pgid" 2>/dev/null || return 0

    # Wait for grace period
    local waited=0
    while [ "$waited" -lt "$grace_secs" ]; do
        sleep 1
        waited=$((waited + 1))
        if ! kill -0 "-$pgid" 2>/dev/null; then
            return 0  # All processes exited
        fi
    done

    # Escalate to SIGKILL
    watchdog_log "ESCALATION" "SIGTERM grace period expired (${grace_secs}s), sending SIGKILL"
    kill -KILL "-$pgid" 2>/dev/null || true
    sleep 1
}

# Print watchdog summary if any events occurred
watchdog_print_summary() {
    if [ "$WATCHDOG_ENABLED" != true ]; then
        return 0
    fi
    if [ -z "$WATCHDOG_LOG" ] || [ ! -s "$WATCHDOG_LOG" ]; then
        # No events — omit summary section entirely
        return 0
    fi

    echo ""
    print_header "Build Watchdog Summary"
    while IFS= read -r line; do
        echo "  $line"
    done < "$WATCHDOG_LOG"
    echo ""
}

# Cleanup watchdog temp files
watchdog_cleanup() {
    stop_memory_monitor
    if [ -n "$WATCHDOG_LOG" ] && [ -f "$WATCHDOG_LOG" ]; then
        rm -f "$WATCHDOG_LOG"
    fi
}

# Run a build command with watchdog monitoring.
# This replaces run_build_with_timestamps when the watchdog is enabled.
# It monitors:
#   1. Overall elapsed time (kills if exceeded)
#   2. Output inactivity (kills if no output for N seconds)
#   3. Memory pressure (via background memory_monitor_loop)
#
# Usage: run_build_with_watchdog "colcon build ..."
# Returns: exit code of the build command (137 for memory kill)
run_build_with_watchdog() {
    local cmd="$1"

    if [ "$WATCHDOG_ENABLED" != true ]; then
        # Fall through to simple timestamped build
        run_build_with_timestamps "$cmd"
        return $?
    fi

    print_info "Build output is timestamped: [HH:MM:SS +M:SS] per line"
    print_info "Watchdog is active (Ctrl+C to abort)"
    echo ""

    # Create a named pipe for output monitoring
    local output_pipe
    output_pipe=$(mktemp -u /tmp/build-output-XXXXXX)
    mkfifo "$output_pipe" 2>/dev/null || {
        # If mkfifo fails, fall back to simple build
        print_warning "Watchdog: cannot create FIFO, falling back to simple build"
        run_build_with_timestamps "$cmd"
        return $?
    }

    # Track the last output timestamp for inactivity detection
    local last_output_file
    last_output_file=$(mktemp /tmp/build-lastout-XXXXXX 2>/dev/null)
    date +%s > "$last_output_file"

    # Start the build in a new process group (setsid)
    # Redirect both stdout and stderr to the pipe
    setsid bash -c "$cmd" > "$output_pipe" 2>&1 &
    local build_pid=$!
    local build_pgid=$build_pid  # setsid makes it its own process group leader

    # Start memory monitor
    start_memory_monitor "$build_pgid"

    # Reader process: reads from pipe, timestamps, updates last-output time
    local reader_exit_code=0
    (
        local start_ts
        start_ts=$(date +%s)
        while IFS= read -r line; do
            local ts elapsed now mins secs
            ts=$(date +%H:%M:%S)
            now=$(date +%s)
            elapsed=$((now - start_ts))
            mins=$((elapsed / 60))
            secs=$((elapsed % 60))
            printf "[%s +%d:%02d] %s\n" "$ts" "$mins" "$secs" "$line"
            # Update last output timestamp (atomic: write to tmp then mv)
            echo "$now" > "${last_output_file}.tmp" && mv -f "${last_output_file}.tmp" "$last_output_file"
        done < "$output_pipe"
    ) &
    local reader_pid=$!

    # Main watchdog loop: check timeouts
    local build_start
    build_start=$(date +%s)
    local exit_code=0
    local killed_by=""

    while true; do
        # Check if build has finished
        if ! kill -0 "$build_pid" 2>/dev/null; then
            wait "$build_pid" 2>/dev/null
            exit_code=$?
            break
        fi

        local now elapsed
        now=$(date +%s)
        elapsed=$((now - build_start))

        # 1. Overall timeout check
        if [ "$elapsed" -ge "$OVERALL_TIMEOUT" ]; then
            killed_by="overall"
            watchdog_log "TIMEOUT" "type=overall elapsed=${elapsed}s limit=${OVERALL_TIMEOUT}s mode=$BUILD_MODE package=unknown"
            kill_process_group "$build_pgid"
            exit_code=124  # Same as timeout(1) exit code
            break
        fi

        # 2. Inactivity timeout check
        if [ "$INACTIVITY_TIMEOUT" -gt 0 ] && [ -f "$last_output_file" ]; then
            local last_output
            last_output=$(cat "$last_output_file" 2>/dev/null || echo "")
            # Validate: must be a non-empty integer >= build_start
            if ! [[ "$last_output" =~ ^[0-9]+$ ]] || [ "$last_output" -lt "$build_start" ]; then
                last_output="$build_start"
            fi
            local silent=$((now - last_output))
            if [ "$silent" -ge "$INACTIVITY_TIMEOUT" ]; then
                killed_by="inactivity"
                watchdog_log "TIMEOUT" "type=inactivity silent=${silent}s limit=${INACTIVITY_TIMEOUT}s mode=$BUILD_MODE package=unknown"
                kill_process_group "$build_pgid"
                exit_code=124
                break
            fi
        fi

        # Sleep briefly between checks (1 second resolution)
        sleep 1
    done

    # Wait for reader to finish draining the pipe
    wait "$reader_pid" 2>/dev/null || true

    # Stop memory monitor
    stop_memory_monitor

    # Cleanup
    rm -f "$output_pipe" "$last_output_file" "${last_output_file}.tmp"

    # Check if build was killed by memory monitor (exit code from SIGKILL = 137)
    if [ "$exit_code" -eq 137 ] && [ -z "$killed_by" ]; then
        killed_by="memory"
    fi

    return $exit_code
}

# Run a build command with timestamped output.
# Usage: run_build_with_timestamps "colcon build ..."
run_build_with_timestamps() {
    local cmd="$1"

    print_info "Build output is timestamped: [HH:MM:SS +M:SS] per line"
    echo ""

    # Run command, pipe both stdout and stderr through timestamper.
    # Use pipefail so we get the colcon exit code, not awk's.
    set -o pipefail
    eval "$cmd" 2>&1 | timestamp_prefix
    local exit_code=$?
    set +o pipefail
    return $exit_code
}

# Function to show help
show_help() {
    cat << EOF
$(print_header "Pragati ROS2 Build Script")

DESCRIPTION:
    Builds the Pragati ROS2 workspace using colcon build.

USAGE:
    $0 [MODE] [OPTIONS]

MODES:
    audit               Run CMake configuration audit (no build)
    fast                Fast build with tests/examples disabled (default for dev)
    full                Full build with tests enabled (for CI/testing)
    pkg <NAME>          Build specific package with fast options
    arm                 Build ARM packages only (${ARM_PACKAGES[*]})
    vehicle             Build Vehicle packages only (${VEHICLE_PACKAGES[*]})
    rpi                 Cross-compile all packages for Raspberry Pi (${RPI_PACKAGES[*]})
    (no mode)           Interactive mode or standard build

OPTIONS:
    -h, --help              Show this help message
    -c, --clean             Clean build (removes build/install, rotates old logs)
    -j, --jobs NUM          Number of parallel jobs (default: $PARALLEL_WORKERS on this platform)
                            Auto-detected: 1 for RPi (reliable), 4 for desktop
    -p, --package PKG       Build only the specified package
    -f, --fast              Fast build mode with interactive package selection (legacy)
    --profile PROFILE       Use configuration profile (e.g., rpi1, rpi2, vehicle1)
    --cmake-args ARGS       Additional CMake arguments
    --symlink-install       Use symlink install (faster for development)
    --skip-checks           Skip disk space and memory checks before build
    --no-log                Disable colcon per-package log files (default for fast/pkg modes)

WATCHDOG OPTIONS:
    --no-watchdog           Disable all watchdog timeouts and memory monitoring
    --build-timeout SECS    Overall build timeout (default: 1200s / 20min)
    --pkg-timeout SECS      Per-package timeout (default: 600s / 10min)
    --inactivity-timeout S  Inactivity timeout, 0 to disable (default: 300s / 5min)
    --mem-floor MB          Memory floor in MB for OOM protection (default: auto)

    Environment variables: BUILD_TIMEOUT_SECS, PKG_TIMEOUT_SECS,
                          INACTIVITY_TIMEOUT_SECS, MEM_FLOOR_MB

RASPBERRY PI:
    On RPi, build.sh automatically ensures 2GB swap is available for reliable builds.
    This prevents OOM crashes during cotton_detection_ros2 compilation.
    The swap is made permanent in /etc/fstab.

EXAMPLES:
    $0 audit                # Run CMake audit and generate report
    $0 fast                 # Fast build (tests OFF, ccache enabled)
    $0 full                 # Full build (tests ON)
    $0 pkg yanthra_move     # Build only yanthra_move with fast options
    $0 arm                  # Build ARM packages (for arm RPi)
    $0 vehicle              # Build Vehicle packages (for vehicle RPi)
    $0 rpi -p motor_control_ros2  # Cross-compile for RPi
    $0 rpi --profile rpi1   # Cross-compile using rpi1 profile settings
    $0 --clean arm          # Clean + build ARM packages
    $0 --clean fast         # Clean + fast build
    $0 -j 8 fast            # Fast build with 8 parallel jobs

OPTIMIZATIONS:
    - ccache: Automatically enabled if installed
    - Ninja: Automatically used if installed
    - Fast mode disables: BUILD_TESTING, BUILD_EXAMPLES, BUILD_TOOLS (DepthAI stays ON)

EOF
}

# ---------------------------------------------------------------------------
# Centralized package lists (single source of truth)
# Used by build_arm, build_vehicle, build_rpi, --clean, help text, print_info
# ---------------------------------------------------------------------------
readonly ARM_PACKAGES=(
    common_utils
    motor_control_ros2
    cotton_detection_ros2
    yanthra_move
    robot_description
    motor_control_msgs
)

readonly VEHICLE_PACKAGES=(
    common_utils
    motor_control_ros2
    odrive_control_ros2
    vehicle_control
    robot_description
    motor_control_msgs
)

readonly RPI_PACKAGES=(
    common_utils
    motor_control_ros2
    odrive_control_ros2
    cotton_detection_ros2
    yanthra_move
    vehicle_control
    robot_description
    pattern_finder
    motor_control_msgs
)

# Parse command line arguments
CMAKE_ARGS=""
SYMLINK_INSTALL=false
SKIP_CHECKS=false
COLCON_LOG=""  # empty = use mode default; --no-log sets false

# Parse all arguments - options and mode can be in any order
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--clean)
            CLEAN_BUILD=true
            shift
            ;;
        -j|--jobs)
            PARALLEL_WORKERS="$2"
            shift 2
            ;;
        -p|--package)
            PACKAGE_NAME="$2"
            shift 2
            ;;
        -f|--fast)
            FAST_MODE=true
            shift
            ;;
        --cmake-args)
            CMAKE_ARGS="$2"
            shift 2
            ;;
        --symlink-install)
            SYMLINK_INSTALL=true
            shift
            ;;
        --skip-checks)
            SKIP_CHECKS=true
            shift
            ;;
        --no-log)
            COLCON_LOG=false
            shift
            ;;
        --no-watchdog)
            WATCHDOG_ENABLED=false
            shift
            ;;
        --build-timeout)
            OVERALL_TIMEOUT="$2"
            shift 2
            ;;
        --pkg-timeout)
            PKG_TIMEOUT="$2"
            shift 2
            ;;
        --inactivity-timeout)
            INACTIVITY_TIMEOUT="$2"
            shift 2
            ;;
        --mem-floor)
            MEM_FLOOR_MB="$2"
            shift 2
            ;;
        --profile)
            PROFILE_NAME="$2"
            load_profile "$PROFILE_NAME"
            shift 2
            ;;
        # Modes (can appear anywhere in arguments)
        audit)
            BUILD_MODE="audit"
            shift
            ;;
        fast)
            BUILD_MODE="fast"
            shift
            ;;
        full)
            BUILD_MODE="full"
            shift
            ;;
        pkg)
            BUILD_MODE="pkg"
            if [[ $# -lt 2 ]]; then
                print_error "pkg mode requires package name"
                echo "Usage: $0 pkg <package_name>"
                exit 1
            fi
            PACKAGE_NAME="$2"
            shift 2
            ;;
        arm)
            BUILD_MODE="arm"
            shift
            ;;
        vehicle)
            BUILD_MODE="vehicle"
            shift
            ;;
        rpi)
            BUILD_MODE="rpi"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Function to setup build environment optimizations
setup_build_environment() {
    # Ensure cross-compile sysroot is on ext4, not NTFS (20x I/O difference)
    if [ "$BUILD_MODE" = "rpi" ]; then
        local ext4_sysroot="$HOME/rpi-sysroot"
        if [ -d "$ext4_sysroot" ] && [ "$RPI_SYSROOT" != "$ext4_sysroot" ]; then
            print_warning "Overriding RPI_SYSROOT from '$RPI_SYSROOT' to ext4: '$ext4_sysroot'"
            export RPI_SYSROOT="$ext4_sysroot"
        fi
    fi

    # ccache support
    # Uses system default cache dir (~/.cache/ccache on ext4) for best I/O performance.
    # Do NOT set CCACHE_DIR to workspace — 9p/drvfs filesystems kill cache performance.
    # Configure via ~/.config/ccache/ccache.conf for ROS2-optimized settings.
    if command -v ccache &> /dev/null; then
        export CMAKE_C_COMPILER_LAUNCHER=ccache
        export CMAKE_CXX_COMPILER_LAUNCHER=ccache

        # Separate ccache dirs for native vs cross-compile to avoid hash collisions
        # and allow independent cache management
        if [ "$BUILD_MODE" = "rpi" ]; then
            export CCACHE_DIR="$HOME/.cache/ccache-aarch64"
            mkdir -p "$CCACHE_DIR"
        fi

        local ccache_dir
        ccache_dir=$(ccache -k cache_dir 2>/dev/null || echo "~/.cache/ccache")
        print_info "ccache enabled (cache dir: $ccache_dir)"

        # Show ccache stats if available
        if ccache -s &> /dev/null; then
            local hit_rate=$(ccache -s 2>/dev/null | grep "cache hit rate" | awk '{print $4}')
            if [ -n "$hit_rate" ]; then
                print_info "  ccache hit rate: $hit_rate"
            fi
        fi
    else
        print_warning "ccache not found - install for faster rebuilds: sudo apt install ccache"
    fi

    # Ninja support — skip on low-RAM systems (<8GB) because Ninja launches
    # all independent build steps (including link steps) simultaneously, which
    # can exhaust memory. Make serializes link steps, which is safer.
    local total_ram_mb
    total_ram_mb=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")
    if command -v ninja &> /dev/null; then
        if [ "$total_ram_mb" -ge 8192 ]; then
            export CMAKE_GENERATOR="Ninja"
            print_info "Ninja generator enabled"
        else
            print_info "Ninja available but skipped (${total_ram_mb}MB RAM < 8GB threshold — Make serializes link steps better)"
        fi
    fi

    # Per-package build parallelism (Ninja/Make internal -j).
    # This is INDEPENDENT of --parallel-workers (which controls how many
    # packages build concurrently). Total max compilers ≈ workers × pkg_jobs.
    # Compute based on available RAM: ~1.5GB per compiler process, divided
    # by the number of parallel workers to stay within memory budget.
    local avail_ram_mb pkg_parallel_jobs
    avail_ram_mb=$(awk '/MemAvailable/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "4096")
    # Budget: (available_RAM + swap_free × 0.5) / (workers × 1GB_per_compiler)
    # Count half of free swap as usable headroom for burst memory demand.
    # 1GB per compiler is conservative — most IDL/C files use <500MB,
    # only large C++ files (motion_controller.cpp) hit ~1.5GB.
    local swap_free_mb
    swap_free_mb=$(awk '/SwapFree/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "0")
    local effective_mb=$(( avail_ram_mb + swap_free_mb / 2 ))
    pkg_parallel_jobs=$(( effective_mb / (PARALLEL_WORKERS * 1000) ))
    [[ $pkg_parallel_jobs -lt 1 ]] && pkg_parallel_jobs=1
    # Cap at nproc (no point exceeding CPU cores)
    local max_cores
    max_cores=$(nproc)
    [[ $pkg_parallel_jobs -gt $max_cores ]] && pkg_parallel_jobs=$max_cores
    export CMAKE_BUILD_PARALLEL_LEVEL="$pkg_parallel_jobs"
    print_info "Per-package parallelism: $pkg_parallel_jobs jobs (workers=$PARALLEL_WORKERS, ram=${avail_ram_mb}MB+swap=${swap_free_mb}MB)"

    # mold linker: 2-5x faster than GNU ld for shared library linking.
    # Only used for native builds — cross-compile uses the sysroot's linker.
    # Sets CMAKE_EXE_LINKER_FLAGS and CMAKE_SHARED_LINKER_FLAGS via env vars
    # that CMake picks up. Also stored in MOLD_CMAKE_ARGS for injection via
    # --cmake-args in colcon commands.
    MOLD_CMAKE_ARGS=""
    if [ "$BUILD_MODE" != "rpi" ] && command -v mold &> /dev/null; then
        MOLD_CMAKE_ARGS="-DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=mold -DCMAKE_SHARED_LINKER_FLAGS=-fuse-ld=mold"
        print_info "mold linker enabled (faster linking)"
    fi
}

# Function to clean up colcon/ament prefix paths before building.
# Removes:
#   1. Nonexistent directories (stale paths from previously deleted install/).
#   2. Workspace-local install paths (install/ and install_rpi/) so that colcon
#      does not see packages from a previous build as an underlay. This prevents
#      the "Some selected packages are already built in one or more underlay
#      workspaces" warning when ~/.bashrc sources install/setup.bash.
sanitize_prefix_path_var() {
    local var_name="$1"
    local value="${!var_name}"

    if [ -z "$value" ]; then
        return 0
    fi

    local install_dir="$WORKSPACE_ROOT/install"
    local install_rpi_dir="$WORKSPACE_ROOT/install_rpi"
    local cleaned=""
    local removed=0

    IFS=':' read -ra parts <<< "$value"
    for p in "${parts[@]}"; do
        [ -z "$p" ] && continue
        # Skip nonexistent directories
        if [ ! -d "$p" ]; then
            removed=$((removed + 1))
            continue
        fi
        # Skip workspace-local install paths (avoids overlay/underlay conflicts)
        # Also skip other workspace install paths (e.g., $HOME/pragati_ros2/install/*)
        # that leak in via sourced setup.bash from a different workspace.
        case "$p" in
            "$install_dir"|"$install_dir/"*)
                removed=$((removed + 1))
                continue
                ;;
            "$install_rpi_dir"|"$install_rpi_dir/"*)
                removed=$((removed + 1))
                continue
                ;;
            */pragati_ros2/install|*/pragati_ros2/install/*)
                removed=$((removed + 1))
                continue
                ;;
        esac
        if [ -z "$cleaned" ]; then
            cleaned="$p"
        else
            cleaned="$cleaned:$p"
        fi
    done

    if [ "$removed" -gt 0 ]; then
        export "$var_name=$cleaned"
    fi
}

sanitize_colcon_prefix_paths() {
    sanitize_prefix_path_var AMENT_PREFIX_PATH
    sanitize_prefix_path_var CMAKE_PREFIX_PATH
    sanitize_prefix_path_var COLCON_PREFIX_PATH
    sanitize_prefix_path_var LD_LIBRARY_PATH
    sanitize_prefix_path_var PYTHONPATH
    sanitize_prefix_path_var PATH
}

# Function to fix build directory permissions (common issue after running sudo)
fix_build_permissions() {
    local dirs_to_check=("build" "install" "log")
    local needs_fix=false

    for dir in "${dirs_to_check[@]}"; do
        if [ -d "$WORKSPACE_ROOT/$dir" ]; then
            local owner=$(stat -c '%U' "$WORKSPACE_ROOT/$dir" 2>/dev/null)
            if [ "$owner" = "root" ] && [ "$(id -u)" != "0" ]; then
                needs_fix=true
                break
            fi
        fi
    done

    if [ "$needs_fix" = true ]; then
        print_warning "Detected root-owned build directories (from previous sudo run)"
        print_step "Fixing permissions..."

        for dir in "${dirs_to_check[@]}"; do
            if [ -d "$WORKSPACE_ROOT/$dir" ]; then
                if sudo -n chown -R "$USER:$USER" "$WORKSPACE_ROOT/$dir" 2>/dev/null; then
                    print_info "Fixed $dir/ ownership"
                else
                    print_error "Cannot fix $dir/ permissions - need sudo"
                    print_info "Run manually: sudo chown -R $USER:$USER $WORKSPACE_ROOT/$dir"
                    return 1
                fi
            fi
        done
        print_success "Build directory permissions fixed"
    fi
    return 0
}

# Function to check for install folder type conflicts (symlink vs merged)
check_install_folder_type() {
    local install_dir="$WORKSPACE_ROOT/install"

    # Skip if install doesn't exist or is empty
    if [ ! -d "$install_dir" ] || [ -z "$(ls -A "$install_dir" 2>/dev/null)" ]; then
        return 0
    fi

    # Check if this is a merged install (has lib/, share/ at top level)
    # vs isolated install (has package_name/ directories)
    local has_lib_at_root=false
    local has_pkg_dirs=false

    if [ -d "$install_dir/lib" ] || [ -d "$install_dir/share" ]; then
        has_lib_at_root=true
    fi

    # Check for package directories (indicates isolated install)
    for pkg_dir in "$install_dir"/*/; do
        local pkg_name=$(basename "$pkg_dir")
        if [ -d "$pkg_dir/lib" ] || [ -d "$pkg_dir/share" ]; then
            has_pkg_dirs=true
            break
        fi
    done

    # If using --symlink-install (isolated) but install is merged, warn
    if [ "$SYMLINK_INSTALL" = true ] && [ "$has_lib_at_root" = true ] && [ "$has_pkg_dirs" = false ]; then
        print_warning "Install folder appears to be from --merge-install build"
        print_warning "Current build uses --symlink-install (isolated)"
        print_info "This may cause conflicts. Consider: rm -rf install/"
        echo ""
        read -p "Continue anyway? [y/N]: " response
        case "$response" in
            [yY][eE][sS]|[yY])
                return 0
                ;;
            *)
                print_info "Aborting. Clean install folder and retry."
                exit 1
                ;;
        esac
    fi

    return 0
}

# Function to get CMake args based on build mode
get_cmake_args_for_mode() {
    local mode="$1"
    local args=""

    case $mode in
        fast|pkg|arm|vehicle)
            # Fast/targeted modes: keep builds lean by disabling tests
            args="-DBUILD_TESTING=OFF"
            # On RPi, add memory-saving flags
            if [ "${IS_RPI:-false}" = true ]; then
                args="$args -DCMAKE_BUILD_TYPE=Release"
                args="$args '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG -ftemplate-depth=256'"
            fi
            ;;
        rpi)
            # RPi Cross-compilation mode
            args="-DCMAKE_TOOLCHAIN_FILE=$WORKSPACE_ROOT/cmake/toolchains/rpi-aarch64.cmake"
            args="$args -DBUILD_TESTING=OFF"
            ;;
        full)
            # Full mode: enable tests
            args="-DBUILD_TESTING=ON"
            ;;
        standard)
            # Standard mode: minimal flags
            args="-DBUILD_TESTING=OFF"
            ;;
    esac

    # Add Ninja generator if available
    if [ -n "$CMAKE_GENERATOR" ]; then
        args="$args -G Ninja"
    fi

    echo "$args"
}

# ============================================================================
# Phase-Level Timing Summary
# ============================================================================
# Parses colcon's events.log to show per-package Configure/Compile/Install times.
# This answers "which package/phase is the bottleneck?" at a glance.
#
# events.log format:
#   [timestamp] (pkg) JobStarted: {...}
#   [timestamp] (pkg) JobProgress: {'progress': 'cmake'}   <- configure starts
#   [timestamp] (pkg) JobProgress: {'progress': 'build'}   <- compile starts
#   [timestamp] (pkg) JobProgress: {'progress': 'install'} <- install starts
#   [timestamp] (pkg) JobEnded: {'rc': N}                  <- done
#
# Phase durations:
#   Configure = build_time - cmake_time
#   Compile   = install_time - build_time
#   Install   = ended_time - install_time
#   Total     = ended_time - started_time

print_phase_timing_summary() {
    local events_log="$WORKSPACE_ROOT/log/latest_build/events.log"
    if [ ! -f "$events_log" ]; then
        return 0  # silently skip if no log
    fi

    # Extract timing data using awk — one pass through the file.
    # Uses field-splitting ($1/$2/$3) instead of match() capture groups
    # to avoid gawk bugs with 3-arg match() corrupting stored references.
    #
    # CRITICAL: pkg_count must be initialized in BEGIN{} — gawk treats
    # uninitialized variables as "" (empty string) for array indices,
    # so order[pkg_count] becomes order[""] instead of order[0].
    local timing_data
    timing_data=$(awk '
    BEGIN { pkg_count = 0 }

    # Skip TimerEvent lines (heartbeats) for performance
    /TimerEvent/ { next }

    # Match only Job events
    /Job(Started|Progress|Ended)/ {
        # Parse: [timestamp] (package) EventType: ...
        ts = substr($1, 2) + 0        # strip leading [, force numeric
        pkg = substr($2, 2, length($2) - 2)  # strip ( and )
        evt = substr($3, 1, length($3) - 1)  # strip trailing :

        if (evt == "JobStarted") {
            started[pkg] = ts
            if (!(pkg in order_idx)) {
                order_idx[pkg] = pkg_count
                order[pkg_count] = pkg
                pkg_count++
            }
        } else if (evt == "JobProgress") {
            # Use index() for phase detection — no capture groups needed
            if (index($0, "'"'"'cmake'"'"'") > 0)   cmake_ts[pkg] = ts
            if (index($0, "'"'"'build'"'"'") > 0)   build_ts[pkg] = ts
            if (index($0, "'"'"'install'"'"'") > 0)  install_ts[pkg] = ts
        } else if (evt == "JobEnded") {
            ended[pkg] = ts
            # Extract return code using index + substr (avoid 3-arg match)
            idx = index($0, "'"'"'rc'"'"'")
            if (idx > 0) {
                rest = substr($0, idx)
                rc[pkg] = 0
                for (ci = 1; ci <= length(rest); ci++) {
                    c = substr(rest, ci, 1)
                    if (c >= "0" && c <= "9") {
                        rc[pkg] = substr(rest, ci, 1) + 0
                        break
                    }
                }
            } else {
                rc[pkg] = 0
            }
        }
    }

    END {
        if (pkg_count == 0) exit

        # Compute phase durations and find maximums for highlighting
        max_cfg = 0; max_bld = 0; max_inst = 0; max_total = 0

        for (i = 0; i < pkg_count; i++) {
            p = order[i]

            # Configure = build_start - cmake_start
            if (p in cmake_ts && p in build_ts)
                cfg[p] = build_ts[p] - cmake_ts[p]
            else
                cfg[p] = -1

            # Compile = install_start - build_start
            if (p in build_ts && p in install_ts)
                bld[p] = install_ts[p] - build_ts[p]
            else
                bld[p] = -1

            # Install = ended - install_start
            if (p in install_ts && p in ended)
                inst[p] = ended[p] - install_ts[p]
            else
                inst[p] = -1

            # Total = ended - started
            if (p in started && p in ended)
                tot[p] = ended[p] - started[p]
            else
                tot[p] = -1

            if (cfg[p] > max_cfg)   max_cfg = cfg[p]
            if (bld[p] > max_bld)   max_bld = bld[p]
            if (inst[p] > max_inst) max_inst = inst[p]
            if (tot[p] > max_total) max_total = tot[p]
        }

        # Per-pkg: PKG|CONFIGURE|COMPILE|INSTALL|OVERHEAD|TOTAL|RC|IS_MAX_CFG|IS_MAX_BLD|IS_MAX_TOTAL
        # TOTAL row: TOTAL|SUM_CFG|SUM_BLD|SUM_INST|SUM_OVH|SUM_CPU|WALL|0|0|0|0
        sum_cfg = 0; sum_bld = 0; sum_inst = 0; sum_ovh = 0
        for (i = 0; i < pkg_count; i++) {
            p = order[i]
            is_max_cfg   = (cfg[p] == max_cfg && max_cfg > 5) ? 1 : 0
            is_max_bld   = (bld[p] == max_bld && max_bld > 5) ? 1 : 0
            is_max_total = (tot[p] == max_total && max_total > 5) ? 1 : 0

            # Overhead = Total - (Configure + Compile + Install)
            if (tot[p] >= 0 && cfg[p] >= 0 && bld[p] >= 0 && inst[p] >= 0)
                ovh[p] = tot[p] - cfg[p] - bld[p] - inst[p]
            else
                ovh[p] = -1
            if (ovh[p] < 0 && tot[p] >= 0) ovh[p] = 0

            printf "%s|%.1f|%.1f|%.1f|%.1f|%.1f|%d|%d|%d|%d\n", \
                p, cfg[p], bld[p], inst[p], ovh[p], tot[p], rc[p]+0, \
                is_max_cfg, is_max_bld, is_max_total

            if (cfg[p] > 0)  sum_cfg  += cfg[p]
            if (bld[p] > 0)  sum_bld  += bld[p]
            if (inst[p] > 0) sum_inst += inst[p]
            if (ovh[p] > 0)  sum_ovh  += ovh[p]
        }

        # Wall time = last package end - first package start
        first_start = started[order[0]]
        last_end = 0
        for (i = 0; i < pkg_count; i++) {
            p = order[i]
            if (p in ended && ended[p] > last_end) last_end = ended[p]
        }
        wall = (last_end > first_start) ? last_end - first_start : 0
        sum_cpu = sum_cfg + sum_bld + sum_inst + sum_ovh
        printf "TOTAL|%.1f|%.1f|%.1f|%.1f|%.1f|%.1f|0|0|0|0\n", sum_cfg, sum_bld, sum_inst, sum_ovh, sum_cpu, wall
    }
    ' "$events_log")

    if [ -z "$timing_data" ]; then
        return 0  # no packages found
    fi

    # Helper: format seconds as human-readable duration.
    # Uses pure bash integer arithmetic — no bc subprocesses.
    _fmt_dur() {
        local val="$1"
        # Extract integer part (truncate at decimal point)
        local int_part="${val%%.*}"
        local frac_part="${val#*.}"
        # Handle negative values
        if [ "${int_part:0:1}" = "-" ] || [ "$int_part" = "-0" ]; then
            printf "%10s" "-"
            return
        fi
        # Default empty int to 0
        : "${int_part:=0}"
        if [ "$int_part" -ge 60 ] 2>/dev/null; then
            local mins=$((int_part / 60))
            local secs=$((int_part % 60))
            printf "%dm%02ds" "$mins" "$secs"
        else
            # Keep one decimal place
            [ ${#frac_part} -gt 1 ] && frac_part="${frac_part:0:1}"
            printf "%s.%ss" "$int_part" "$frac_part"
        fi
    }

    echo ""
    # Box inner width = 90 visible characters (between ║ and ║)
    local _border="══════════════════════════════════════════════════════════════════════════════════════════"
    echo -e "${CYAN}╔${_border}╗${NC}"
    echo -e "${CYAN}║${NC}  ${WHITE}Build Phase Timing Summary${NC}                                                              ${CYAN}║${NC}"
    echo -e "${CYAN}╠${_border}╣${NC}"
    printf "${CYAN}║${NC}  %-24s %10s %10s %10s %10s %10s  %-6s ${CYAN}║${NC}\n" \
        "Package" "Configure" "Compile" "Install" "Overhead" "Total" "Status"
    echo -e "${CYAN}╠${_border}╣${NC}"

    # Pre-compute build overhead (script wall-clock minus colcon wall-clock)
    local _overhead_end_epoch _total_script_secs
    _overhead_end_epoch=$(date +%s)
    _total_script_secs=$((_overhead_end_epoch - BUILD_START_TIME))

    # Extract colcon wall-clock from TOTAL row
    # TOTAL row format: TOTAL|SUM_CFG|SUM_BLD|SUM_INST|SUM_OVH|SUM_CPU|WALL|0|0|0|0
    local total_line
    total_line=$(echo "$timing_data" | tail -1)
    local total_cfg total_bld total_inst total_ovh total_cpu total_wall
    IFS='|' read -r _ total_cfg total_bld total_inst total_ovh total_cpu total_wall _ _ _ _ <<< "$total_line"

    # Compute build overhead: script duration minus colcon wall-clock
    # Use awk for floating-point arithmetic to avoid integer truncation mismatches
    local _colcon_wall_val="${total_wall:-0}"
    local _overhead_secs _script_wall_secs
    read -r _overhead_secs _script_wall_secs <<< "$(awk -v sw="$_total_script_secs" -v cw="$_colcon_wall_val" \
        'BEGIN { oh = sw - cw; if (oh < 0) oh = 0; printf "%.1f %.1f\n", oh, sw }')"
    local _overhead_str
    _overhead_str=$(_fmt_dur "$_overhead_secs")

    local line_fields pkg cfg_val bld_val inst_val ovh_val tot_val rc_val is_max_cfg is_max_bld is_max_total
    while IFS= read -r line_fields; do
        if [[ "$line_fields" == TOTAL\|* ]]; then
            # TOTAL row has extra field: TOTAL|cfg|bld|inst|ovh|cpu_sum|wall|0|0|0|0
            IFS='|' read -r pkg cfg_val bld_val inst_val ovh_val tot_val _ _ _ _ _ <<< "$line_fields"
        else
            # Per-package: PKG|cfg|bld|inst|ovh|tot|rc|max_cfg|max_bld|max_tot
            IFS='|' read -r pkg cfg_val bld_val inst_val ovh_val tot_val rc_val is_max_cfg is_max_bld is_max_total <<< "$line_fields"
        fi
        local cfg_str bld_str inst_str ovh_str tot_str
        cfg_str=$(_fmt_dur "$cfg_val")
        bld_str=$(_fmt_dur "$bld_val")
        inst_str=$(_fmt_dur "$inst_val")
        ovh_str=$(_fmt_dur "$ovh_val")
        tot_str=$(_fmt_dur "$tot_val")

        if [ "$pkg" = "TOTAL" ]; then
            echo -e "${CYAN}╠${_border}╣${NC}"
            printf "${CYAN}║${NC}  ${WHITE}%-24s${NC} %10s %10s %10s ${DIM}%10s${NC} ${WHITE}%10s${NC}  %-6s ${CYAN}║${NC}\n" \
                "TOTAL (cpu-time)" "$cfg_str" "$bld_str" "$inst_str" "$ovh_str" "$tot_str" ""
            # Colcon wall-clock row
            local _colcon_wall_str
            _colcon_wall_str=$(_fmt_dur "$total_wall")
            printf "${CYAN}║${NC}  ${DIM}%-24s${NC} %10s %10s %10s %10s ${DIM}%10s${NC}  %-6s ${CYAN}║${NC}\n" \
                "Wall clock (colcon)" "" "" "" "" "$_colcon_wall_str" ""
            # Build overhead row (clean, env setup, toolchain checks, summary generation)
            local _script_dur_str
            _script_dur_str=$(_fmt_dur "$_script_wall_secs")
            printf "${CYAN}║${NC}  ${DIM}%-24s${NC} %10s %10s %10s %10s ${DIM}%10s${NC}  %-6s ${CYAN}║${NC}\n" \
                "Build overhead" "" "" "" "" "$_overhead_str" ""
            printf "${CYAN}║${NC}  ${WHITE}%-24s${NC} %10s %10s %10s %10s ${WHITE}%10s${NC}  %-6s ${CYAN}║${NC}\n" \
                "Wall clock (script)" "" "" "" "" "$_script_dur_str" ""
        else
            local pkg_color="${NC}"
            local cfg_color="${NC}" bld_color="${NC}" tot_color="${NC}"
            local status_str="OK" status_color="${GREEN}"

            if [ "$rc_val" != "0" ]; then
                pkg_color="${RED}"
                tot_str="FAIL"
                status_str="FAIL"
                status_color="${RED}"
            fi

            # Highlight the slowest package in each category
            [ "$is_max_cfg" = "1" ] && cfg_color="${YELLOW}"
            [ "$is_max_bld" = "1" ] && bld_color="${YELLOW}"
            [ "$is_max_total" = "1" ] && tot_color="${YELLOW}"

            printf "${CYAN}║${NC}  ${pkg_color}%-24s${NC} ${cfg_color}%10s${NC} ${bld_color}%10s${NC} %10s ${DIM}%10s${NC} ${tot_color}%10s${NC}  ${status_color}%-6s${NC} ${CYAN}║${NC}\n" \
                "$pkg" "$cfg_str" "$bld_str" "$inst_str" "$ovh_str" "$tot_str" "$status_str"
        fi
    done <<< "$timing_data"

    echo -e "${CYAN}╚${_border}╝${NC}"

    # Compare using integer parts (sufficient for bottleneck detection)
    local cfg_int="${total_cfg%%.*}" bld_int="${total_bld%%.*}" inst_int="${total_inst%%.*}"
    : "${cfg_int:=0}" "${bld_int:=0}" "${inst_int:=0}"

    local bottleneck="configure" bottleneck_int="$cfg_int"
    if [ "$bld_int" -gt "$bottleneck_int" ] 2>/dev/null; then
        bottleneck="compile"; bottleneck_int="$bld_int"
    fi
    if [ "$inst_int" -gt "$bottleneck_int" ] 2>/dev/null; then
        bottleneck="install"; bottleneck_int="$inst_int"
    fi

    local sum_int=$((cfg_int + bld_int + inst_int))
    local bottleneck_pct=0
    if [ "$sum_int" -gt 0 ] 2>/dev/null; then
        bottleneck_pct=$((bottleneck_int * 100 / sum_int))
        echo -e "  ${YELLOW}Bottleneck:${NC} ${bottleneck} phase (${bottleneck_pct}% of CPU-time)"
    fi
    echo ""

    # Write plain-text summary to a file alongside events.log for reference.
    # This survives terminal scrollback loss and tool output truncation.
    local summary_file
    summary_file="$(dirname "$events_log")/build_summary.txt"

    # --- Compute true wall-clock duration from BUILD_START_TIME (epoch) ---
    # Reuse _overhead_end_epoch and _total_script_secs computed above
    local total_duration_secs=$_total_script_secs
    local wall_dur_str
    if [ "$total_duration_secs" -ge 60 ] 2>/dev/null; then
        wall_dur_str="$((total_duration_secs / 60))min $((total_duration_secs % 60))s"
    else
        wall_dur_str="${total_duration_secs}s"
    fi

    # --- Count packages and determine overall result ---
    local pkg_count_summary=0 fail_count_summary=0
    while IFS='|' read -r _p _ _ _ _ _ _rc _ _ _; do
        [ "$_p" = "TOTAL" ] && continue
        pkg_count_summary=$((pkg_count_summary + 1))
        [ "$_rc" != "0" ] && fail_count_summary=$((fail_count_summary + 1))
    done <<< "$timing_data"
    local result_str
    if [ "$fail_count_summary" -gt 0 ]; then
        result_str="FAILED ($fail_count_summary of $pkg_count_summary packages failed)"
    else
        result_str="SUCCESS ($pkg_count_summary packages)"
    fi

    {
        # ==== Section 1: Header ====
        echo "================================================================================"
        echo "  Pragati ROS2 Build Summary"
        echo "================================================================================"
        printf "  Started:    %s\n" "$(date -d "@$BUILD_START_TIME" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')"
        printf "  Finished:   %s\n" "$(date '+%Y-%m-%d %H:%M:%S')"
        printf "  Duration:   %s\n" "$wall_dur_str"
        printf "  Result:     %s\n" "$result_str"
        echo ""

        # ==== Section 2: Build Configuration ====
        echo "Build Configuration:"
        printf "  Mode:       %s\n" "$BUILD_MODE"
        [ -n "$PACKAGE_NAME" ] && printf "  Package:    %s\n" "$PACKAGE_NAME"
        [ "$BUILD_MODE" = "rpi" ] && printf "  Toolchain:  cmake/toolchains/rpi-aarch64.cmake\n"
        printf "  Workers:    %s parallel\n" "$PARALLEL_WORKERS"
        [ -n "$CMAKE_BUILD_PARALLEL_LEVEL" ] && \
            printf "  Per-pkg -j: %s\n" "$CMAKE_BUILD_PARALLEL_LEVEL"
        printf "  Generator:  %s\n" "${CMAKE_GENERATOR:-Unix Makefiles}"
        [ "$CLEAN_BUILD" = true ] && printf "  Clean:      yes\n"
        if [ "$BUILD_MODE" = "rpi" ]; then
            printf "  Install:    merge-install\n"
        elif [ "$SYMLINK_INSTALL" = true ]; then
            printf "  Install:    symlink-install\n"
        else
            printf "  Install:    standard\n"
        fi
        [ -n "$CMAKE_ARGS" ] && printf "  CMake args: %s\n" "$CMAKE_ARGS"
        echo ""

        # ==== Section 3: System Info ====
        echo "System:"
        [ -n "$TOTAL_RAM_GB" ] && printf "  RAM:        %sGB total\n" "$TOTAL_RAM_GB"
        [ -n "$TOTAL_CORES" ] && printf "  CPU:        %s threads\n" "$TOTAL_CORES"
        # ccache — single invocation, parse all fields at once
        if command -v ccache &>/dev/null; then
            local _cc_stats _cc_hits _cc_misses _cc_rate
            _cc_stats=$(ccache -s 2>/dev/null)
            # ccache 4.x format: "  Hits:  632 / 749 (84.38%)"
            _cc_hits=$(echo "$_cc_stats" | awk '/^ *Hits:/ && !/Direct|Preprocessed/ {print $2+0; exit}')
            _cc_misses=$(echo "$_cc_stats" | awk '/^ *Misses:/ {print $2+0; exit}')
            _cc_rate=$(echo "$_cc_stats" | awk '/^ *Hits:/ && !/Direct|Preprocessed/ {for(i=1;i<=NF;i++) if($i ~ /\(.*%\)/) {gsub(/[()]/,"",$i); print $i; exit}}')
            if [ -n "$_cc_hits" ] || [ -n "$_cc_rate" ]; then
                printf "  ccache:     hits=%s misses=%s rate=%s dir=%s\n" \
                    "${_cc_hits:-?}" "${_cc_misses:-?}" "${_cc_rate:-?}" \
                    "${CCACHE_DIR:-$(ccache -p 2>/dev/null | awk '/cache_dir/ {print $NF; exit}')}"
            fi
        fi
        # Disk filesystem type
        local _fs_type
        _fs_type=$(df -T "$WORKSPACE_ROOT" 2>/dev/null | awk 'NR==2 {print $2}')
        [ -n "$_fs_type" ] && printf "  Disk:       %s (%s)\n" "$_fs_type" "$WORKSPACE_ROOT"
        echo ""

        # ==== Section 4: Phase Timing Table (existing) ====
        echo "Phase Timing:"
        printf "%-24s %10s %10s %10s %10s %10s  %s\n" \
            "Package" "Configure" "Compile" "Install" "Overhead" "Total" "Status"
        printf "%-24s %10s %10s %10s %10s %10s  %s\n" \
            "------------------------" "----------" "----------" "----------" "----------" "----------" "------"

        while IFS= read -r line_fields; do
            local pkg cfg_val bld_val inst_val ovh_val tot_val rc_val
            if [[ "$line_fields" == TOTAL\|* ]]; then
                IFS='|' read -r pkg cfg_val bld_val inst_val ovh_val tot_val _ _ _ _ _ <<< "$line_fields"
                printf "%-24s %10s %10s %10s %10s %10s\n" \
                    "------------------------" "----------" "----------" "----------" "----------" "----------"
                printf "%-24s %10s %10s %10s %10s %10s\n" \
                    "TOTAL (cpu-time)" "$(_fmt_dur "$cfg_val")" "$(_fmt_dur "$bld_val")" \
                    "$(_fmt_dur "$inst_val")" "$(_fmt_dur "$ovh_val")" "$(_fmt_dur "$tot_val")"
                # Wall clock, build overhead, and script wall clock rows
                printf "%-24s %10s %10s %10s %10s %10s\n" \
                    "Wall clock (colcon)" "" "" "" "" "$(_fmt_dur "$total_wall")"
                printf "%-24s %10s %10s %10s %10s %10s\n" \
                    "Build overhead" "" "" "" "" "$_overhead_str"
                printf "%-24s %10s %10s %10s %10s %10s\n" \
                    "Wall clock (script)" "" "" "" "" "$(_fmt_dur "$_script_wall_secs")"
            else
                IFS='|' read -r pkg cfg_val bld_val inst_val ovh_val tot_val rc_val _ _ _ <<< "$line_fields"
                local status="OK"
                [ "$rc_val" != "0" ] && status="FAIL"
                printf "%-24s %10s %10s %10s %10s %10s  %s\n" \
                    "$pkg" "$(_fmt_dur "$cfg_val")" "$(_fmt_dur "$bld_val")" \
                    "$(_fmt_dur "$inst_val")" "$(_fmt_dur "$ovh_val")" "$(_fmt_dur "$tot_val")" "$status"
            fi
        done <<< "$timing_data"

        echo ""
        if [ "$sum_int" -gt 0 ]; then
            echo "Bottleneck: ${bottleneck} phase (${bottleneck_pct}% of CPU-time)"
        fi
        echo ""

        # ==== Section 5: Build Order (parallel grouping from events.log) ====
        # Group packages that started within 2s of each other as parallel.
        local _build_order
        _build_order=$(awk '
        BEGIN { pkg_count = 0 }
        /TimerEvent/ { next }
        /JobStarted/ {
            ts = substr($1, 2) + 0
            pkg = substr($2, 2, length($2) - 2)
            if (!(pkg in seen)) {
                seen[pkg] = 1
                start_ts[pkg_count] = ts
                start_pkg[pkg_count] = pkg
                pkg_count++
            }
        }
        END {
            if (pkg_count == 0) exit
            group = 1
            group_start = start_ts[0]
            printf "%d|%s", group, start_pkg[0]
            for (i = 1; i < pkg_count; i++) {
                if (start_ts[i] - group_start > 2) {
                    printf "\n"
                    group++
                    group_start = start_ts[i]
                    printf "%d|%s", group, start_pkg[i]
                } else {
                    printf ",%s", start_pkg[i]
                }
            }
            printf "\n"
        }
        ' "$events_log" 2>/dev/null)

        if [ -n "$_build_order" ]; then
            echo "Build Order:"
            while IFS='|' read -r _grp _pkgs; do
                local _pkg_list _num_pkgs _note
                _pkg_list=$(echo "$_pkgs" | tr ',' ', ')
                _num_pkgs=$(echo "$_pkgs" | tr ',' '\n' | wc -l)
                if [ "$_num_pkgs" -gt 1 ]; then
                    _note="(parallel)"
                else
                    _note=""
                fi
                printf "  [%s] %s  %s\n" "$_grp" "$_pkg_list" "$_note"
            done <<< "$_build_order"
            echo ""
        fi

        # ==== Section 6: Warnings Count ====
        # Scan per-package build logs for cmake and compiler warnings.
        local _log_base
        _log_base="$(dirname "$events_log")"
        local _has_warnings=false
        local _total_cmake_warns=0 _total_compiler_warns=0
        local _warnings_output=""

        for _pkg_dir in "$_log_base"/*/; do
            [ -d "$_pkg_dir" ] || continue
            local _pkg_name
            _pkg_name=$(basename "$_pkg_dir")
            # Skip non-package dirs (e.g., "latest" symlink)
            [ "$_pkg_name" = "latest" ] && continue

            local _cmake_warns=0 _compiler_warns=0

            # Count warnings from stdout_stderr.log (merged output — avoids double-counting
            # since stderr.log content is already included in stdout_stderr.log)
            local _logfile="${_pkg_dir}stdout_stderr.log"
            if [ -f "$_logfile" ]; then
                local _cw _compw
                _cw=$(grep -ci 'cmake warning\|CMake Warning' "$_logfile" 2>/dev/null || true)
                _compw=$(grep -ci 'warning:' "$_logfile" 2>/dev/null || true)
                # Subtract cmake warnings from compiler count (cmake warnings also contain 'warning:')
                local _cmake_in_compw
                _cmake_in_compw=$(grep -ci 'cmake warning.*warning:\|CMake Warning' "$_logfile" 2>/dev/null || true)
                _cmake_warns=$((_cmake_warns + ${_cw:-0}))
                _compiler_warns=$((_compiler_warns + ${_compw:-0} - ${_cmake_in_compw:-0}))
            fi

            # Avoid negative counts from overlapping matches
            [ "$_compiler_warns" -lt 0 ] && _compiler_warns=0

            if [ "$_cmake_warns" -gt 0 ] || [ "$_compiler_warns" -gt 0 ]; then
                _has_warnings=true
                _total_cmake_warns=$((_total_cmake_warns + _cmake_warns))
                _total_compiler_warns=$((_total_compiler_warns + _compiler_warns))
                _warnings_output="${_warnings_output}$(printf "  %-24s %d cmake warnings, %d compiler warnings\n" \
                    "${_pkg_name}:" "$_cmake_warns" "$_compiler_warns")\n"
            fi
        done

        if [ "$_has_warnings" = true ]; then
            echo "Warnings:"
            printf "%b" "$_warnings_output"
            printf "  Total: %d cmake warnings, %d compiler warnings\n" \
                "$_total_cmake_warns" "$_total_compiler_warns"
            echo ""
        fi
    } > "$summary_file"
    echo -e "  ${PURPLE}ℹ️  Summary saved: ${summary_file}${NC}"
}


# Function for fast/targeted package build
build_package() {
    local package="$1"
    local description="${2:-$package}"

    print_step "Building $description..."

    local pkg_start=$(date +%s)

    # NOTE: Use --packages-up-to so workspace dependencies get built automatically.
    # --packages-select assumes dependencies are already available in the underlay/overlay.
    local pkg_cmd="colcon build --packages-up-to $package"
    pkg_cmd="$pkg_cmd --parallel-workers $PARALLEL_WORKERS"
    pkg_cmd="$pkg_cmd --event-handlers $COLCON_EVENT_HANDLERS"
    if [ "$SYMLINK_INSTALL" = true ]; then
        pkg_cmd="$pkg_cmd --symlink-install"
    fi
    if [ -n "$CMAKE_ARGS" ]; then
        pkg_cmd="$pkg_cmd --cmake-args $CMAKE_ARGS"
    fi

    if run_build_with_watchdog "$pkg_cmd"; then

        local pkg_end=$(date +%s)
        local duration=$((pkg_end - pkg_start))

        print_success "$description built successfully in ${duration}s"

        # Verify package is available (check install marker without sourcing
        # install/setup.bash — sourcing it mid-build pollutes AMENT_PREFIX_PATH
        # and causes colcon overlay/underlay warnings on subsequent builds)
        if [ -f "install/$package/share/$package/package.xml" ] || \
           [ -f "install/share/$package/package.xml" ]; then
            print_info "Package $package is now available"
        fi

        return 0
    else
        print_error "$description build failed"
        return 1
    fi
}

# Function for interactive fast build
fast_build_interactive() {
    print_header "Fast Build - Package Selection"

    echo ""
    print_info "Available build options:"
    echo "  1) Core packages (yanthra_move + cotton_detection_ros2)"
    echo "  2) Single package (you specify)"
    echo "  3) Quick test (lightweight package)"
    echo "  4) List all packages"
    echo ""

    read -p "Enter choice (1-4): " choice
    echo ""

    case $choice in
        1)
            print_step "Building core packages..."
            if build_package "cotton_detection_ros2" "Cotton Detection"; then
                build_package "yanthra_move" "Yanthra Move"
            fi
            ;;
        2)
            read -p "Enter package name: " pkg_name
            echo ""
            if [ -d "src/$pkg_name" ]; then
                build_package "$pkg_name"
            else
                print_error "Package '$pkg_name' not found in src/"
                print_info "Available packages:"
                ls -1 src/ | grep -v "^$"
                exit 1
            fi
            ;;
        3)
            print_step "Quick test build..."
            if [ -d "src/robot_description" ]; then
                build_package "robot_description" "Robot Description"
            elif [ -d "src/common_utils" ]; then
                build_package "common_utils" "Shared Utilities"
            else
                print_warning "No lightweight test package found"
                build_package "cotton_detection_ros2" "Cotton Detection"
            fi
            ;;
        4)
            print_info "Available packages in workspace:"
            ls -1 src/ | grep -v "^$" | sed 's/^/  • /'
            echo ""
            read -p "Enter package name to build (or Enter to exit): " pkg_name
            if [ -n "$pkg_name" ] && [ -d "src/$pkg_name" ]; then
                echo ""
                build_package "$pkg_name"
            fi
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
}

# Function to run audit
run_audit() {
    print_header "CMake Configuration Audit"

    print_step "Running CMake audit script..."

    if [ ! -f "$WORKSPACE_ROOT/scripts/cmake_audit.py" ]; then
        print_error "Audit script not found: scripts/cmake_audit.py"
        exit 1
    fi

    if python3 "$WORKSPACE_ROOT/scripts/cmake_audit.py" "$WORKSPACE_ROOT"; then
        print_success "Audit complete - reports generated in log/cmake_audit/"
        echo ""
        print_info "Review the markdown report for detailed findings"
        print_info "Latest report: $(ls -t log/cmake_audit/*.md 2>/dev/null | head -1)"
        exit 0
    else
        print_warning "Audit found issues - check log/cmake_audit/ for details"
        exit 1
    fi
}

# Function to setup swap automatically (NON-INTERACTIVE - use for reliable builds)
# This function creates/enables swap without any prompts
# Uses sudo -n (non-interactive) to avoid hanging on password prompts
setup_swap_auto() {
    local swap_size_gb="${1:-2}"
    local swapfile="/swapfile"

    # Check if we have passwordless sudo (required for non-interactive operation)
    if ! sudo -n true 2>/dev/null; then
        print_warning "Passwordless sudo not available - cannot setup swap automatically"
        print_info "Run 'sudo visudo' and add: $USER ALL=(ALL) NOPASSWD: ALL"
        print_info "Or manually setup swap: sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
        return 1
    fi

    print_step "Ensuring ${swap_size_gb}GB swap is available..."

    # Check if swapfile already exists and is active
    if [ -f "$swapfile" ] && swapon --show | grep -q "$swapfile"; then
        local current_swap_mb=$(free -m | awk '/^Swap:/{print $2}')
        local required_mb=$((swap_size_gb * 1024))
        if [ "$current_swap_mb" -ge "$required_mb" ]; then
            print_info "Swap already configured: ${current_swap_mb}MB ✓"
            return 0
        fi
        # Current swap is smaller than needed, recreate
        print_info "Increasing swap from ${current_swap_mb}MB to ${required_mb}MB..."
        sudo -n swapoff "$swapfile" 2>/dev/null || true
        sudo -n rm -f "$swapfile"
    elif [ -f "$swapfile" ]; then
        # Swapfile exists but not active, try to enable
        print_info "Enabling existing swapfile..."
        if sudo -n swapon "$swapfile" 2>/dev/null; then
            print_success "Existing swap enabled"
            return 0
        fi
        # Failed to enable, recreate
        sudo -n rm -f "$swapfile"
    fi

    # Create new swapfile
    print_info "Creating ${swap_size_gb}GB swapfile..."
    if sudo -n fallocate -l ${swap_size_gb}G "$swapfile" 2>/dev/null || \
       sudo -n dd if=/dev/zero of="$swapfile" bs=1M count=$((swap_size_gb * 1024)) status=none 2>/dev/null; then
        sudo -n chmod 600 "$swapfile"
        if sudo -n mkswap "$swapfile" >/dev/null 2>&1 && sudo -n swapon "$swapfile"; then
            local new_swap=$(free -m | awk '/^Swap:/{print $2}')
            print_success "Swap setup complete: ${new_swap}MB"

            # Make permanent if not already in fstab
            if ! grep -q "$swapfile" /etc/fstab 2>/dev/null; then
                echo "$swapfile none swap sw 0 0" | sudo -n tee -a /etc/fstab > /dev/null 2>&1 || true
                print_info "Swap added to /etc/fstab for persistence"
            fi
            return 0
        else
            print_error "Failed to initialize swap"
            sudo -n rm -f "$swapfile"
            return 1
        fi
    else
        print_error "Failed to create swapfile (disk full?)"
        return 1
    fi
}

# Function to setup swap interactively (DEPRECATED - kept for backward compatibility)
setup_swap_interactive() {
    local swap_size_gb="${1:-4}"
    local swapfile="/swapfile"

    echo ""
    print_warning "Insufficient memory for building cotton_detection_ros2"
    print_info "Would you like to setup ${swap_size_gb}GB swap automatically?"
    echo ""
    echo "  This will run:"
    echo "    sudo fallocate -l ${swap_size_gb}G $swapfile"
    echo "    sudo chmod 600 $swapfile"
    echo "    sudo mkswap $swapfile"
    echo "    sudo swapon $swapfile"
    echo ""

    read -p "Setup swap now? [y/N]: " response
    case "$response" in
        [yY][eE][sS]|[yY])
            print_step "Setting up ${swap_size_gb}GB swap..."

            # Check if swapfile already exists
            if [ -f "$swapfile" ]; then
                print_warning "Swapfile already exists at $swapfile"
                if swapon --show | grep -q "$swapfile"; then
                    print_info "Swap is already active"
                    return 0
                else
                    print_info "Enabling existing swapfile..."
                    if sudo swapon "$swapfile" 2>/dev/null; then
                        print_success "Swap enabled successfully"
                        return 0
                    else
                        print_warning "Failed to enable existing swapfile, recreating..."
                        sudo swapoff "$swapfile" 2>/dev/null || true
                        sudo rm -f "$swapfile"
                    fi
                fi
            fi

            # Create new swapfile
            if sudo fallocate -l ${swap_size_gb}G "$swapfile" 2>/dev/null || \
               sudo dd if=/dev/zero of="$swapfile" bs=1M count=$((swap_size_gb * 1024)) status=progress 2>/dev/null; then
                sudo chmod 600 "$swapfile"
                if sudo mkswap "$swapfile" && sudo swapon "$swapfile"; then
                    print_success "Swap setup complete!"

                    # Show new memory status
                    local new_swap=$(free -m | awk '/^Swap:/{print $2}')
                    print_info "New swap size: ${new_swap}MB"

                    # Ask about making it permanent
                    echo ""
                    read -p "Make swap permanent (add to /etc/fstab)? [y/N]: " perm_response
                    case "$perm_response" in
                        [yY][eE][sS]|[yY])
                            if ! grep -q "$swapfile" /etc/fstab; then
                                echo "$swapfile none swap sw 0 0" | sudo tee -a /etc/fstab > /dev/null
                                print_success "Swap added to /etc/fstab"
                            else
                                print_info "Swap already in /etc/fstab"
                            fi
                            ;;
                    esac
                    return 0
                else
                    print_error "Failed to setup swap"
                    sudo rm -f "$swapfile"
                    return 1
                fi
            else
                print_error "Failed to create swapfile (disk full?)"
                return 1
            fi
            ;;
        *)
            print_info "Swap setup skipped"
            return 1
            ;;
    esac
}

# Function to check system resources before build
check_system_resources() {
    local min_disk_mb=2000   # 2GB minimum free disk space
    local has_errors=false
    local needs_swap=false

    print_step "Checking system resources..."

    # Check disk space in workspace directory
    local disk_free_mb=$(df -m "$WORKSPACE_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$disk_free_mb" ]; then
        if [ "$disk_free_mb" -lt "$min_disk_mb" ]; then
            print_error "Insufficient disk space: ${disk_free_mb}MB available, need at least ${min_disk_mb}MB"
            print_info "Free up space with: rm -rf build/ install/ log/"
            has_errors=true
        else
            print_info "Disk space: ${disk_free_mb}MB available ✓"
        fi
    fi

    # Check available memory (RAM + swap)
    local mem_total_mb=$(free -m | awk '/^Mem:/{print $2}')
    local mem_available_mb=$(free -m | awk '/^Mem:/{print $7}')
    local swap_total_mb=$(free -m | awk '/^Swap:/{print $2}')
    local swap_free_mb=$(free -m | awk '/^Swap:/{print $4}')
    local total_available_mb=$((mem_available_mb + swap_free_mb))

    # cotton_detection_ros2 with DepthAI needs ~3GB RAM per compiler process
    local min_mem_mb=3000

    print_info "Memory: ${mem_available_mb}MB RAM available, ${swap_free_mb}MB swap free"
    print_info "Total: ${mem_total_mb}MB RAM, ${swap_total_mb}MB swap configured"

    # Determine if we need more swap
    if [ "$total_available_mb" -lt "$min_mem_mb" ]; then
        needs_swap=true
    fi

    # On RPi, be stricter and use AUTOMATIC swap (no prompts for reliable builds)
    if [ "${IS_RPI:-false}" = true ]; then
        local rpi_min_mem=4000
        local rpi_min_swap=2000  # Require ~2GB swap minimum on RPi (allow some tolerance for rounding)

        if [ "$swap_total_mb" -lt "$rpi_min_swap" ]; then
            print_warning "RPi requires minimum ${rpi_min_swap}MB swap for reliable builds"
            print_info "Current swap: ${swap_total_mb}MB"

            # On RPi, automatically setup swap without prompts for reliability
            if setup_swap_auto 2; then
                # Re-check swap after setup
                swap_total_mb=$(free -m | awk '/^Swap:/{print $2}')
                swap_free_mb=$(free -m | awk '/^Swap:/{print $4}')
                total_available_mb=$((mem_available_mb + swap_free_mb))
                print_success "Swap configured: ${swap_total_mb}MB ✓"
            else
                print_error "Failed to setup swap automatically"
                print_info "Manual setup: sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
                has_errors=true
            fi
        fi

        if [ "$total_available_mb" -lt "$rpi_min_mem" ]; then
            needs_swap=true
            min_mem_mb=$rpi_min_mem
        fi
    fi

    # If we need swap, offer to set it up
    if [ "$needs_swap" = true ]; then
        print_warning "Insufficient memory: ${total_available_mb}MB available (need ${min_mem_mb}MB)"

        # Offer to setup swap automatically
        if setup_swap_interactive 4; then
            # Re-check memory after swap setup
            swap_total_mb=$(free -m | awk '/^Swap:/{print $2}')
            swap_free_mb=$(free -m | awk '/^Swap:/{print $4}')
            total_available_mb=$((mem_available_mb + swap_free_mb))

            if [ "$total_available_mb" -ge "$min_mem_mb" ]; then
                print_success "Memory check passed after swap setup: ${total_available_mb}MB available ✓"
            else
                print_error "Still insufficient memory after swap: ${total_available_mb}MB"
                has_errors=true
            fi
        else
            # User declined swap setup
            print_error "Cannot proceed without sufficient memory"
            print_info "Either setup swap manually or use --skip-checks (build may crash)"
            has_errors=true
        fi
    else
        print_info "Total available: ${total_available_mb}MB (RAM + swap) ✓"
    fi

    echo ""

    if [ "$has_errors" = true ]; then
        print_error "System resource check FAILED"
        print_error "Use --skip-checks to bypass (NOT recommended - build may crash)"
        exit 1
    fi
}

# Main build function
main() {
    print_header "Pragati ROS2 Build Process"

    cd "$WORKSPACE_ROOT"

    # Handle audit mode first
    if [ "$BUILD_MODE" = "audit" ]; then
        run_audit
        exit 0
    fi

    # --- Mode-specific defaults (before banner so display is accurate) ---

    # Enable symlink install by default for fast, pkg, arm, vehicle modes
    if [ "$BUILD_MODE" = "fast" ] || [ "$BUILD_MODE" = "pkg" ] || [ "$BUILD_MODE" = "arm" ] || [ "$BUILD_MODE" = "vehicle" ]; then
        SYMLINK_INSTALL=true
    fi

    # Disable colcon per-package log files by default for dev modes.
    # Use --no-log explicitly for other modes, or override with COLCON_LOG=true.
    if [ -z "$COLCON_LOG" ]; then
        if [ "$BUILD_MODE" = "fast" ] || [ "$BUILD_MODE" = "pkg" ]; then
            COLCON_LOG=false
        else
            COLCON_LOG=true
        fi
    fi

    # --- Banner ---

    print_info "Workspace: $WORKSPACE_ROOT"
    print_info "Build mode: $BUILD_MODE"
    print_info "Parallel jobs: $PARALLEL_WORKERS"
    print_info "Clean build: $([ "$CLEAN_BUILD" = true ] && echo "Yes" || echo "No")"
    print_info "Symlink install: $([ "$SYMLINK_INSTALL" = true ] && echo "Yes" || echo "No")"
    if [ "$COLCON_LOG" = false ]; then
        print_info "Colcon log: Disabled (--no-log)"
    fi

    # Cross-compilation is slower — large C++ files can take >5min per file.
    # Relax watchdog timeouts before display so the header shows correct values.
    if [ "$BUILD_MODE" = "rpi" ]; then
        INACTIVITY_TIMEOUT=600
        OVERALL_TIMEOUT=2400
    fi

    # Initialize and display watchdog config
    watchdog_init
    watchdog_display_config

    # Extra hints for RPi builds
    if [ "${IS_RPI:-false}" = true ]; then
        print_info "Detected Raspberry Pi platform (aarch64)"
        if [ "$PARALLEL_WORKERS" -gt 1 ]; then
            print_warning "RPi with $PARALLEL_WORKERS workers may hit OOM; 1 worker is the safest default."
        else
            print_info "Using 1 worker for maximum reliability on RPi (use -j2 to speed up at your own risk)."
        fi
    fi
    if [ -n "$PACKAGE_NAME" ]; then
        print_info "Target package: $PACKAGE_NAME"
    elif [ "$FAST_MODE" = true ]; then
        print_info "Mode: Fast/Interactive"
    fi
    echo ""

    # Ensure dev environment: auto-install pre-commit hooks (once, silent)
    if [ -f ".pre-commit-config.yaml" ] && [ -d ".git" ] && [ ! -f ".git/hooks/pre-commit" ]; then
        if command -v pre-commit &>/dev/null; then
            pre-commit install --allow-missing-config &>/dev/null \
                && pre-commit install --hook-type pre-push --allow-missing-config &>/dev/null \
                && print_info "Pre-commit hooks installed (one-time setup)"
        else
            print_warning "pre-commit not found. Install for code quality hooks: pip install pre-commit && pre-commit install"
        fi
    fi

    # Check if this is a ROS2 workspace
    if [ ! -d "src" ]; then
        print_error "No 'src' directory found. This doesn't appear to be a ROS2 workspace."
        exit 1
    fi

    # Check for ROS2 installation
    if ! command -v colcon &> /dev/null; then
        print_error "colcon not found! Please install colcon:"
        echo "  sudo apt install python3-colcon-common-extensions"
        exit 1
    fi

    # Fix build directory permissions if needed (common after running sudo)
    if ! fix_build_permissions; then
        print_error "Cannot proceed with root-owned build directories"
        exit 1
    fi

    # Check system resources (disk space, memory) unless skipped
    if [ "$SKIP_CHECKS" = false ]; then
        check_system_resources
    else
        print_warning "Skipping system resource checks (--skip-checks)"
        echo ""
    fi

    # Setup build optimizations
    setup_build_environment
    echo ""

    # Watchdog pre-build resource validation
    watchdog_pre_build_validate

    # Ensure watchdog cleanup on exit
    trap watchdog_cleanup EXIT

    # Get CMake args based on build mode
    MODE_CMAKE_ARGS=$(get_cmake_args_for_mode "$BUILD_MODE")
    if [ -n "$MODE_CMAKE_ARGS" ]; then
        if [ -n "$CMAKE_ARGS" ]; then
            CMAKE_ARGS="$MODE_CMAKE_ARGS $CMAKE_ARGS"
        else
            CMAKE_ARGS="$MODE_CMAKE_ARGS"
        fi
    fi

    # Append mold linker flags if enabled (set by setup_build_environment)
    if [ -n "$MOLD_CMAKE_ARGS" ]; then
        CMAKE_ARGS="${CMAKE_ARGS:+$CMAKE_ARGS }$MOLD_CMAKE_ARGS"
    fi

    if [ -n "$CMAKE_ARGS" ]; then
        print_info "CMake flags: $CMAKE_ARGS"
        echo ""
    fi

    # Build the --event-handlers string.
    # colcon's log handler writes 5 files per package and flushes after every
    # output line (~3 flush syscalls per line).  For packages with 150-200
    # install status lines this adds ~45s of pure Python I/O overhead.
    # Disabling it with --no-log drops incremental builds from ~55s to ~10s
    # per heavy package.  Phase timing (events.log) is unaffected — it uses
    # the separate event_log handler.
    COLCON_EVENT_HANDLERS="console_direct+"
    if [ "$COLCON_LOG" = false ]; then
        COLCON_EVENT_HANDLERS="$COLCON_EVENT_HANDLERS log-"
    fi

    # Clean build if requested
    if [ "$CLEAN_BUILD" = true ]; then
        if [ "$BUILD_MODE" = "arm" ]; then
            print_step "Cleaning ARM package builds..."
            for pkg in "${ARM_PACKAGES[@]}"; do
                rm -rf "build/$pkg" "install/$pkg"
            done
            print_success "Cleaned ARM package directories"
        elif [ "$BUILD_MODE" = "vehicle" ]; then
            print_step "Cleaning Vehicle package builds..."
            for pkg in "${VEHICLE_PACKAGES[@]}"; do
                rm -rf "build/$pkg" "install/$pkg"
            done
            print_success "Cleaned Vehicle package directories"
        elif [ "$BUILD_MODE" = "rpi" ]; then
            print_step "Cleaning RPi Cross-Compilation builds..."
            rm -rf build_rpi/ install_rpi/
            print_success "Cleaned RPi build directories"
        elif [ "$BUILD_MODE" = "pkg" ] && [ -n "$PACKAGE_NAME" ]; then
            print_step "Cleaning $PACKAGE_NAME build..."
            rm -rf "build/$PACKAGE_NAME" "install/$PACKAGE_NAME"
            print_success "Cleaned $PACKAGE_NAME directories"
        else
            print_step "Cleaning all build directories..."
            rm -rf build/ install/
            # Rotate old build logs (keep last 10)
            if [ -d "log" ]; then
                local old_logs
                old_logs=$(ls -dt log/build_* 2>/dev/null | tail -n +11)
                if [ -n "$old_logs" ]; then
                    echo "$old_logs" | xargs rm -rf
                    print_info "Rotated old build logs (kept last 10)"
                fi
            fi
            print_success "Cleaned all build directories"
        fi
    fi

    # Remove any stale prefixes (avoids AMENT_PREFIX_PATH/CMAKE_PREFIX_PATH warnings)
    sanitize_colcon_prefix_paths

    # Check for install folder type conflicts
    check_install_folder_type

    # Handle fast mode (interactive)
    if [ "$FAST_MODE" = true ]; then
        fast_build_interactive

        local build_end=$(date +%s)
        local total_duration=$((build_end - BUILD_START_TIME))
        echo ""
        print_phase_timing_summary
        print_success "Fast build completed in ${total_duration}s"
        exit 0
    fi

    # Handle single package build
    if [ -n "$PACKAGE_NAME" ] && [ "$BUILD_MODE" != "rpi" ]; then
        if [ ! -d "src/$PACKAGE_NAME" ]; then
            print_error "Package '$PACKAGE_NAME' not found in src/"
            print_info "Available packages:"
            ls -1 src/ | grep -v "^$" | sed 's/^/  • /'
            exit 1
        fi

        if ! build_package "$PACKAGE_NAME"; then
            exit 1
        fi

        local build_end=$(date +%s)
        local total_duration=$((build_end - BUILD_START_TIME))
        echo ""
        print_phase_timing_summary
        print_success "Package build completed in ${total_duration}s"
        exit 0
    fi

    # Handle ARM packages build
    if [ "$BUILD_MODE" = "arm" ]; then
        print_header "Building ARM Packages"
        print_info "Packages: ${ARM_PACKAGES[*]}"
        echo ""

        local build_cmd="colcon build --packages-up-to ${ARM_PACKAGES[*]}"
        build_cmd="$build_cmd --parallel-workers $PARALLEL_WORKERS"
        build_cmd="$build_cmd --symlink-install"
        build_cmd="$build_cmd --event-handlers $COLCON_EVENT_HANDLERS"
        if [ -n "$CMAKE_ARGS" ]; then
            build_cmd="$build_cmd --cmake-args $CMAKE_ARGS"
        fi

        print_step "Building ARM packages..."
        print_info "Command: $build_cmd"
        echo ""

        if run_build_with_watchdog "$build_cmd"; then
            local build_end=$(date +%s)
            local total_duration=$((build_end - BUILD_START_TIME))
            echo ""
            watchdog_print_summary
            print_phase_timing_summary
            print_success "ARM packages built successfully in ${total_duration}s"
            print_info "Built: ${ARM_PACKAGES[*]}"
            exit 0
        else
            watchdog_print_summary
            print_error "ARM packages build failed!"
            exit 1
        fi
    fi

    # Handle Vehicle packages build
    if [ "$BUILD_MODE" = "vehicle" ]; then
        print_header "Building Vehicle Packages"
        print_info "Packages: ${VEHICLE_PACKAGES[*]}"
        echo ""

        local build_cmd="colcon build --packages-up-to ${VEHICLE_PACKAGES[*]}"
        build_cmd="$build_cmd --parallel-workers $PARALLEL_WORKERS"
        build_cmd="$build_cmd --symlink-install"
        build_cmd="$build_cmd --event-handlers $COLCON_EVENT_HANDLERS"
        if [ -n "$CMAKE_ARGS" ]; then
            build_cmd="$build_cmd --cmake-args $CMAKE_ARGS"
        fi

        print_step "Building Vehicle packages..."
        print_info "Command: $build_cmd"
        echo ""

        if run_build_with_watchdog "$build_cmd"; then
            local build_end=$(date +%s)
            local total_duration=$((build_end - BUILD_START_TIME))
            echo ""
            watchdog_print_summary
            print_phase_timing_summary
            print_success "Vehicle packages built successfully in ${total_duration}s"
            print_info "Built: ${VEHICLE_PACKAGES[*]}"
            exit 0
        else
            watchdog_print_summary
            print_error "Vehicle packages build failed!"
            exit 1
        fi
    fi

    # Handle RPi Cross-Compilation build
    if [ "$BUILD_MODE" = "rpi" ]; then
        # Source ROS2 environment for build tools (colcon needs ROS2 Python packages)
        if [ -f "/opt/ros/jazzy/setup.bash" ]; then
            source /opt/ros/jazzy/setup.bash
            # Ensure PYTHONPATH is explicitly set for CMake subprocess calls
            export PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH:-}"
            print_info "Sourced ROS2 Jazzy environment for build tools"
            print_info "PYTHONPATH: $PYTHONPATH"
        else
            print_error "ROS2 Jazzy not found at /opt/ros/jazzy"
            print_info "Install with: sudo apt install ros-jazzy-desktop"
            exit 1
        fi

        print_header "Building RPi Packages (Cross-Compilation)"
        print_info "Target: Raspberry Pi 4 (aarch64)"
        print_info "Toolchain: cmake/toolchains/rpi-aarch64.cmake"
        print_info "Output: build_rpi/ install_rpi/"
        echo ""

        local rpi_packages=""
        if [ -n "$PACKAGE_NAME" ]; then
            rpi_packages="$PACKAGE_NAME"
            print_info "Targeting single package: $PACKAGE_NAME"
        elif [ -n "$BUILD_PACKAGES" ]; then
            rpi_packages="$BUILD_PACKAGES"
            print_info "Targeting packages from config: $BUILD_PACKAGES"
        else
            rpi_packages="${RPI_PACKAGES[*]}"
            print_info "Targeting all RPi packages"
        fi

        local build_cmd="colcon build --packages-up-to $rpi_packages"
        build_cmd="$build_cmd --merge-install"
        build_cmd="$build_cmd --build-base build_rpi"
        build_cmd="$build_cmd --install-base install_rpi"
        build_cmd="$build_cmd --parallel-workers $PARALLEL_WORKERS"
        build_cmd="$build_cmd --event-handlers $COLCON_EVENT_HANDLERS"
        if [ -n "$CMAKE_ARGS" ]; then
            build_cmd="$build_cmd --cmake-args $CMAKE_ARGS"
        fi

        print_step "Cross-compiling packages..."
        print_info "Command: $build_cmd"
        echo ""

        if run_build_with_watchdog "$build_cmd"; then
            local build_end=$(date +%s)
            local total_duration=$((build_end - BUILD_START_TIME))
            echo ""
            watchdog_print_summary
            print_phase_timing_summary
            print_success "RPi packages cross-compiled successfully in ${total_duration}s"
            print_info "Artifacts are in 'install_rpi/'"
            print_info "Deploy with: ./sync.sh --deploy-cross --ip <RPI_IP>"
            exit 0
        else
            watchdog_print_summary
            print_error "RPi cross-compilation failed!"
            exit 1
        fi
    fi

    # Prepare build command
    local build_cmd="colcon build"
    build_cmd="$build_cmd --parallel-workers $PARALLEL_WORKERS"

    if [ "$SYMLINK_INSTALL" = true ]; then
        build_cmd="$build_cmd --symlink-install"
    fi

    if [ -n "$CMAKE_ARGS" ]; then
        build_cmd="$build_cmd --cmake-args $CMAKE_ARGS"
    fi

    # Add some common helpful flags
    build_cmd="$build_cmd --event-handlers $COLCON_EVENT_HANDLERS"

    print_step "Building workspace ($BUILD_MODE mode)..."
    print_info "Command: $build_cmd"
    echo ""

    # Run the build
    if run_build_with_watchdog "$build_cmd"; then
        echo ""
        watchdog_print_summary
        print_phase_timing_summary
        print_success "Build completed successfully!"

        # Show ccache stats if available
        if command -v ccache &> /dev/null; then
            local hit_rate=$(ccache -s 2>/dev/null | grep "cache hit rate" | awk '{print $4}')
            if [ -n "$hit_rate" ]; then
                print_info "ccache hit rate: $hit_rate"
            fi
        fi

        # Check if install directory was created
        if [ -d "install" ]; then
            print_info "Installation files created in: install/"
            print_info "Source the environment with: source install/setup.bash"
        fi

        # Show package summary
        if [ -d "build" ]; then
            local pkg_count=$(find build -maxdepth 1 -type d | wc -l)
            pkg_count=$((pkg_count - 1))  # Subtract the build directory itself
            print_info "Built $pkg_count packages"
        fi

        # Show build time
        local build_end=$(date +%s)
        local total_duration=$((build_end - BUILD_START_TIME))
        print_info "Total build time: ${total_duration}s"

        # Run tests in full mode (BUILD_TESTING=ON means tests were compiled)
        if [ "$BUILD_MODE" = "full" ]; then
            echo ""
            print_step "Running tests (full mode)..."
            if [ -f "install/setup.bash" ]; then
                source install/setup.bash
            fi
            local test_start=$(date +%s)
            if colcon test --event-handlers console_direct+ --return-code-on-test-failure; then
                local test_end=$(date +%s)
                local test_duration=$((test_end - test_start))
                print_success "All tests passed! (${test_duration}s)"
            else
                local test_end=$(date +%s)
                local test_duration=$((test_end - test_start))
                print_warning "Some tests failed (${test_duration}s)"
                print_info "Run 'colcon test-result --all --verbose' for details"
                # Don't exit 1 — build succeeded, tests are informational
                # Caller can check test results separately
            fi
        fi

        exit 0
    else
        echo ""
        watchdog_print_summary
        print_error "Build failed!"
        print_info "Check the error messages above for details"
        print_info "Common solutions:"
        echo "  • Install missing dependencies with: rosdep install --from-paths src --ignore-src -r -y"
        echo "  • Try a clean build with: $0 --clean $BUILD_MODE"
        echo "  • Check for compilation errors in the build logs"
        exit 1
    fi
}

# Execute main function
main
