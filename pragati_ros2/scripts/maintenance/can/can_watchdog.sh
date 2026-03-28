#!/usr/bin/env bash
#
# CAN Bus Auto-Recovery Watchdog
# ================================
# Automatically detects and recovers from CAN bus errors (BUS-OFF, ERROR-PASSIVE, DOWN)
#
# Features:
# - User-independent: works on any Linux system (PC, Raspberry Pi)
# - Minimal resource usage: ~0.01% CPU, ~2-5 MB memory
# - Configurable polling interval (default: 1.5s)
# - Safe recovery with rate limiting and exponential backoff
# - Multi-interface support (can0, can1, etc.)
# - Systemd integration with journald logging
#
# Usage:
#   ./can_watchdog.sh -i can0                    # Monitor can0
#   ./can_watchdog.sh -i can0,can1               # Monitor multiple
#   ./can_watchdog.sh -i can0 -c 2.0             # Custom check interval
#   systemctl start can-watchdog@can0.service    # Via systemd
#
# Configuration:
#   /etc/default/can-watchdog        - Global settings
#   /etc/default/can-watchdog-can0   - Per-interface settings
#

set -euo pipefail

# =============================================================================
# CONFIGURATION DEFAULTS (can be overridden via config files or CLI)
# =============================================================================

WATCHDOG_INTERFACES="${WATCHDOG_INTERFACES:-can0}"
CHECK_INTERVAL_SEC="${CHECK_INTERVAL_SEC:-1.5}"
LOG_DIR="${LOG_DIR:-/tmp}"
LOG_FILE="${LOG_FILE:-}"

# Recovery settings
# Default bitrate aligned with production configs (500 kbps). Override in /etc/default/can-watchdog-* if needed.
BITRATE_can0="${BITRATE_can0:-500000}"
RESTART_MS_can0="${RESTART_MS_can0:-100}"
COOLDOWN_MIN_MS="${COOLDOWN_MIN_MS:-500}"
MAX_RECOVERIES_PER_HOUR="${MAX_RECOVERIES_PER_HOUR:-20}"
EXP_BACKOFF_MAX_SEC="${EXP_BACKOFF_MAX_SEC:-60}"

# Error state handling
RECOVER_ON_ERROR_PASSIVE="${RECOVER_ON_ERROR_PASSIVE:-yes}"
CHRONIC_THRESHOLD="${CHRONIC_THRESHOLD:-5}"
CHRONIC_WINDOW_SEC="${CHRONIC_WINDOW_SEC:-300}"

# WARNING state monitoring (optional)
MONITOR_WARNING_STATE="${MONITOR_WARNING_STATE:-no}"
WARNING_ERROR_THRESHOLD="${WARNING_ERROR_THRESHOLD:-100}"
WARNING_LOG_INTERVAL_SEC="${WARNING_LOG_INTERVAL_SEC:-300}"

# Module and script integration
AUTO_MODPROBE="${AUTO_MODPROBE:-yes}"
USE_SETUP_CAN_SH="${USE_SETUP_CAN_SH:-auto}"
ON_RECOVERY_HOOK="${ON_RECOVERY_HOOK:-}"

# =============================================================================
# PATH DISCOVERY (User-independent, works on any system)
# =============================================================================

find_command() {
    local cmd="$1"
    command -v "$cmd" 2>/dev/null || \
    command -v "/sbin/$cmd" 2>/dev/null || \
    command -v "/usr/sbin/$cmd" 2>/dev/null || \
    command -v "/usr/local/sbin/$cmd" 2>/dev/null || \
    { echo "ERROR: $cmd not found in PATH" >&2; exit 1; }
}

IP_CMD="$(find_command ip)"
MODPROBE_CMD="$(find_command modprobe)"

# Optional: setup_can.sh discovery
SETUP_CAN_SH=""
for path in \
    "/usr/local/sbin/setup_can.sh" \
    "/home/uday/Downloads/pragati_ros2/scripts/setup_can.sh" \
    "./scripts/setup_can.sh" \
    "../setup_can.sh"; do
    if [[ -x "$path" ]]; then
        SETUP_CAN_SH="$path"
        break
    fi
done

# =============================================================================
# LOGGING (User-independent paths) - MUST BE BEFORE load_config
# =============================================================================

log() {
    local msg="$1"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    
    # Log to file if specified
    if [[ -n "$LOG_FILE" ]]; then
        echo "[$timestamp] $msg" >> "$LOG_FILE"
    fi
    
    # Always log to stdout (captured by systemd journald)
    echo "[$timestamp] $msg"
}

log_error() {
    local msg="$1"
    log "ERROR: $msg" >&2
}

log_warning() {
    local msg="$1"
    log "WARNING: $msg"
}

# =============================================================================
# LOAD CONFIGURATION FILES (System-wide, not user-specific)
# =============================================================================

load_config() {
    local config_file="$1"
    if [[ -f "$config_file" ]]; then
        # shellcheck source=/dev/null
        source "$config_file"
        log "Loaded config: $config_file"
    fi
}

# Load global config
load_config "/etc/default/can-watchdog"

# Load project config if exists (for development)
load_config "/home/uday/Downloads/pragati_ros2/config/can_watchdog.conf" 2>/dev/null || true

# =============================================================================
# STATE MANAGEMENT
# =============================================================================

declare -A RECOVERY_COUNT       # Per-interface recovery count
declare -A LAST_RECOVERY_TIME   # Timestamp of last recovery
declare -A BACKOFF_DELAY        # Current backoff delay (exponential)
declare -A CHRONIC_FAILURES     # Circular buffer for chronic detection

# Initialize history file for rate limiting
RECOVERY_HISTORY_FILE="$LOG_DIR/can_watchdog_recovery_history.txt"
touch "$RECOVERY_HISTORY_FILE" 2>/dev/null || true

# =============================================================================
# CAN INTERFACE STATE DETECTION
# =============================================================================

get_can_state() {
    local iface="$1"
    local state=""
    
    # Check if interface exists
    if ! "$IP_CMD" link show dev "$iface" &>/dev/null; then
        echo "MISSING"
        return
    fi
    
    # Get detailed state (support multiple iproute2 formats)
    local output
    output=$("$IP_CMD" -details link show dev "$iface" 2>/dev/null || echo "")
    
    # Try standard format: "state BUS-OFF"
    state=$(echo "$output" | grep -Eo 'state [A-Z-]+' | awk '{print $2}' | head -1)
    
    # Try alternate format: "can state BUS-OFF"
    if [[ -z "$state" ]]; then
        state=$(echo "$output" | grep -Eo 'can state [A-Z-]+' | awk '{print $3}' | head -1)
    fi
    
    # Check if interface is DOWN
    if echo "$output" | grep -q "state DOWN"; then
        echo "DOWN"
        return
    fi
    
    # Return state or UNKNOWN
    if [[ -z "$state" ]]; then
        echo "UNKNOWN"
    else
        echo "$state"
    fi
}

needs_recovery() {
    local iface="$1"
    local state="$2"
    
    case "$state" in
        BUS-OFF)
            log_warning "$iface: BUS-OFF detected (too many errors)"
            return 0
            ;;
        DOWN)
            log_warning "$iface: Interface DOWN"
            return 0
            ;;
        ERROR-PASSIVE)
            if [[ "$RECOVER_ON_ERROR_PASSIVE" == "yes" ]]; then
                log_warning "$iface: ERROR-PASSIVE detected"
                return 0
            fi
            return 1
            ;;
        MISSING)
            log_warning "$iface: Interface missing"
            return 0
            ;;
        ERROR-ACTIVE|UP)
            return 1
            ;;
        *)
            log_warning "$iface: Unknown state: $state"
            return 1
            ;;
    esac
}

# Check for WARNING state (high error count but still functional)
check_warning_state() {
    local iface="$1"
    
    # Only check if monitoring is enabled
    if [[ "$MONITOR_WARNING_STATE" != "yes" ]]; then
        return 0
    fi
    
    # Get error statistics
    local stats
    stats=$(ip -s link show "$iface" 2>/dev/null || echo "")
    
    if [[ -z "$stats" ]]; then
        return 0
    fi
    
    # Extract TX and RX errors
    local tx_errors
    local rx_errors
    tx_errors=$(echo "$stats" | grep -A1 "TX:" | tail -1 | awk '{print $3}')
    rx_errors=$(echo "$stats" | grep -A1 "RX:" | tail -1 | awk '{print $3}')
    
    # Check if either exceeds threshold
    if (( tx_errors > WARNING_ERROR_THRESHOLD )) || (( rx_errors > WARNING_ERROR_THRESHOLD )); then
        # Only log periodically to avoid spam
        local now
        now=$(date +%s)
        local last_warning_var="LAST_WARNING_${iface}"
        local last_warning="${!last_warning_var:-0}"
        
        if (( now - last_warning >= WARNING_LOG_INTERVAL_SEC )); then
            log_warning "$iface: WARNING state detected - TX errors: $tx_errors, RX errors: $rx_errors (threshold: $WARNING_ERROR_THRESHOLD)"
            log_warning "$iface: Check cables, termination (120Ω), and EMI sources"
            
            # Update last warning time
            eval "${last_warning_var}=$now"
        fi
    fi
}

# =============================================================================
# RATE LIMITING & SAFETY
# =============================================================================

check_rate_limit() {
    local iface="$1"
    local now
    now=$(date +%s)
    
    # Clean old history entries (older than 1 hour)
    local cutoff=$((now - 3600))
    if [[ -f "$RECOVERY_HISTORY_FILE" ]]; then
        grep -v "^$iface " "$RECOVERY_HISTORY_FILE" > "${RECOVERY_HISTORY_FILE}.tmp" 2>/dev/null || true
        awk -v cutoff="$cutoff" -v iface="$iface" \
            '$1 == iface && $2 >= cutoff {print}' \
            "$RECOVERY_HISTORY_FILE" >> "${RECOVERY_HISTORY_FILE}.tmp" 2>/dev/null || true
        mv "${RECOVERY_HISTORY_FILE}.tmp" "$RECOVERY_HISTORY_FILE" 2>/dev/null || true
    fi
    
    # Count recoveries in last hour
    local count=0
    if [[ -f "$RECOVERY_HISTORY_FILE" ]]; then
        # NOTE: `grep -c` prints "0" but exits with status 1 when there are no matches.
        # Using `|| echo 0` would therefore produce "0 0" and break arithmetic evaluation.
        count=$(grep -c "^$iface " "$RECOVERY_HISTORY_FILE" 2>/dev/null || true)
        count=${count:-0}
    fi
    
    if (( count >= MAX_RECOVERIES_PER_HOUR )); then
        log_error "$iface: Rate limit exceeded ($count recoveries/hour, max: $MAX_RECOVERIES_PER_HOUR)"
        return 1
    fi
    
    return 0
}

record_recovery() {
    local iface="$1"
    local now
    now=$(date +%s)
    echo "$iface $now" >> "$RECOVERY_HISTORY_FILE" 2>/dev/null || true
}

calculate_backoff() {
    local iface="$1"
    local count="${RECOVERY_COUNT[$iface]:-0}"
    
    # Exponential backoff: min(2^count * 0.5, max_backoff)
    local delay
    delay=$(awk -v count="$count" -v max="$EXP_BACKOFF_MAX_SEC" \
        'BEGIN {d = (2^count) * 0.5; if (d > max) d = max; print d}')
    
    echo "$delay"
}

detect_chronic_failure() {
    local iface="$1"
    local now
    now=$(date +%s)
    
    # Initialize if needed
    if [[ -z "${CHRONIC_FAILURES[$iface]:-}" ]]; then
        CHRONIC_FAILURES[$iface]="$now"
        return 1
    fi
    
    # Parse timestamps
    local timestamps=(${CHRONIC_FAILURES[$iface]})
    timestamps+=("$now")
    
    # Keep only recent failures (within window)
    local recent=()
    local cutoff=$((now - CHRONIC_WINDOW_SEC))
    for ts in "${timestamps[@]}"; do
        if (( ts >= cutoff )); then
            recent+=("$ts")
        fi
    done
    
    CHRONIC_FAILURES[$iface]="${recent[*]}"
    
    # Check if chronic
    if (( ${#recent[@]} >= CHRONIC_THRESHOLD )); then
        log_error "$iface: CHRONIC FAILURE detected (${#recent[@]} failures in ${CHRONIC_WINDOW_SEC}s)"
        return 0
    fi
    
    return 1
}

# =============================================================================
# CAN RECOVERY
# =============================================================================

load_modules() {
    if [[ "$AUTO_MODPROBE" != "yes" ]]; then
        return 0
    fi
    
    log "Loading SocketCAN modules..."
    "$MODPROBE_CMD" can 2>/dev/null || true
    "$MODPROBE_CMD" can_raw 2>/dev/null || true
    "$MODPROBE_CMD" can_dev 2>/dev/null || true
    "$MODPROBE_CMD" mcp251x 2>/dev/null || true
    sleep 0.5
}

perform_recovery() {
    local iface="$1"
    
    log "$iface: Starting recovery procedure..."
    
    # Get interface-specific settings
    local bitrate_var="BITRATE_${iface}"
    local restart_ms_var="RESTART_MS_${iface}"
    local bitrate="${!bitrate_var:-500000}"
    local restart_ms="${!restart_ms_var:-100}"
    
    # Check if we should use setup_can.sh
    local use_setup_can=false
    if [[ "$USE_SETUP_CAN_SH" == "always" ]] && [[ -x "$SETUP_CAN_SH" ]]; then
        use_setup_can=true
    elif [[ "$USE_SETUP_CAN_SH" == "auto" ]] && [[ -x "$SETUP_CAN_SH" ]]; then
        use_setup_can=true
    fi
    
    if $use_setup_can; then
        log "$iface: Using setup_can.sh for recovery"
        if sudo "$SETUP_CAN_SH" "$iface" "$bitrate" "$restart_ms"; then
            log "$iface: Recovery via setup_can.sh successful"
            return 0
        else
            log_warning "$iface: setup_can.sh failed, falling back to manual recovery"
        fi
    fi
    
    # Manual recovery sequence
    log "$iface: Bringing interface down..."
    if ! "$IP_CMD" link set "$iface" down 2>/dev/null; then
        log_error "$iface: Failed to bring interface down"
        return 1
    fi
    
    # Cooldown
    sleep "$(awk -v ms="$COOLDOWN_MIN_MS" 'BEGIN {print ms/1000}')"
    
    log "$iface: Configuring interface (bitrate=${bitrate}, restart-ms=${restart_ms})..."
    # Try with berr-reporting first (not supported on all hardware like MCP2515)
    if ! "$IP_CMD" link set "$iface" type can \
        bitrate "$bitrate" \
        restart-ms "$restart_ms" \
        berr-reporting on 2>/dev/null; then
        # Fallback: configure without berr-reporting (required for MCP2515/Raspberry Pi)
        log "$iface: berr-reporting not supported, trying without it..."
        if ! "$IP_CMD" link set "$iface" type can \
            bitrate "$bitrate" \
            restart-ms "$restart_ms" 2>/dev/null; then
            log_error "$iface: Failed to configure interface"
            return 1
        fi
    fi
    
    log "$iface: Bringing interface up..."
    if ! "$IP_CMD" link set "$iface" up 2>/dev/null; then
        log_error "$iface: Failed to bring interface up"
        return 1
    fi
    
    log "$iface: Recovery completed successfully"
    return 0
}

attempt_recovery() {
    local iface="$1"
    local state="$2"
    
    # Check rate limit
    if ! check_rate_limit "$iface"; then
        log_error "$iface: Skipping recovery due to rate limit"
        return 1
    fi
    
    # Check for chronic failures
    if detect_chronic_failure "$iface"; then
        log_error "$iface: Stopping recovery attempts (chronic failure)"
        return 1
    fi
    
    # Calculate backoff
    local count="${RECOVERY_COUNT[$iface]:-0}"
    if (( count > 0 )); then
        local backoff
        backoff=$(calculate_backoff "$iface")
        log "$iface: Waiting ${backoff}s before recovery attempt #$((count + 1))..."
        sleep "$backoff"
    fi
    
    # Handle MISSING interface specially
    if [[ "$state" == "MISSING" ]]; then
        log "$iface: Interface missing, attempting module load..."
        load_modules
        sleep 1
        
        # Check again
        if ! "$IP_CMD" link show dev "$iface" &>/dev/null; then
            log_error "$iface: Interface still missing after module load"
            return 1
        fi
    fi
    
    # Perform recovery
    if perform_recovery "$iface"; then
        record_recovery "$iface"
        RECOVERY_COUNT[$iface]=$((count + 1))
        LAST_RECOVERY_TIME[$iface]=$(date +%s)
        
        # Execute hook if defined
        if [[ -n "$ON_RECOVERY_HOOK" ]] && [[ -x "$ON_RECOVERY_HOOK" ]]; then
            "$ON_RECOVERY_HOOK" "$iface" "$state" &
        fi
        
        return 0
    else
        log_error "$iface: Recovery failed"
        return 1
    fi
}

# =============================================================================
# MAIN MONITORING LOOP
# =============================================================================

monitor_interface() {
    local iface="$1"
    
    # Load per-interface config
    load_config "/etc/default/can-watchdog-${iface}" 2>/dev/null || true
    
    log "$iface: Monitoring started (interval: ${CHECK_INTERVAL_SEC}s)"
    if [[ "$MONITOR_WARNING_STATE" == "yes" ]]; then
        log "$iface: WARNING state monitoring enabled (threshold: ${WARNING_ERROR_THRESHOLD} errors)"
    fi
    
    while true; do
        local state
        state=$(get_can_state "$iface")
        
        if needs_recovery "$iface" "$state"; then
            attempt_recovery "$iface" "$state" || true
        fi
        
        # Check for WARNING state (optional)
        check_warning_state "$iface"
        
        sleep "$CHECK_INTERVAL_SEC"
    done
}

# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

show_usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

CAN Bus Auto-Recovery Watchdog (user-independent, minimal resource usage)

Options:
  -i, --interfaces IFACES    Comma-separated list of interfaces (default: can0)
  -c, --check-interval SEC   Check interval in seconds (default: 1.5)
  -l, --log-file FILE        Log file path (default: none, uses journald)
  -h, --help                 Show this help message

Environment Variables:
  All settings can be configured via /etc/default/can-watchdog

Examples:
  $0 -i can0                 # Monitor can0 with default settings
  $0 -i can0,can1 -c 2.0     # Monitor can0 and can1, check every 2s
  systemctl start can-watchdog@can0.service  # Via systemd

Configuration:
  /etc/default/can-watchdog        - Global settings
  /etc/default/can-watchdog-can0   - Per-interface settings

Resource Usage:
  CPU:    ~0.01% per interface
  Memory: ~2-5 MB total
  Disk:   Minimal logging

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--interfaces)
            WATCHDOG_INTERFACES="$2"
            shift 2
            ;;
        -c|--check-interval)
            CHECK_INTERVAL_SEC="$2"
            shift 2
            ;;
        -l|--log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# =============================================================================
# STARTUP
# =============================================================================

log "======================================================================"
log "CAN Bus Auto-Recovery Watchdog"
log "======================================================================"
log "Interfaces: $WATCHDOG_INTERFACES"
log "Check interval: ${CHECK_INTERVAL_SEC}s"
log "Configuration: /etc/default/can-watchdog"
log "User-independent: yes"
log "Resource usage: ~0.01% CPU, ~2-5 MB memory per interface"
log "======================================================================"

# Parse interface list
IFS=',' read -ra INTERFACES <<< "$WATCHDOG_INTERFACES"

# Start monitoring (one per interface in background)
if (( ${#INTERFACES[@]} == 1 )); then
    # Single interface: run in foreground
    monitor_interface "${INTERFACES[0]}"
else
    # Multiple interfaces: run in background
    for iface in "${INTERFACES[@]}"; do
        monitor_interface "$iface" &
    done
    
    # Wait for all background jobs
    wait
fi
