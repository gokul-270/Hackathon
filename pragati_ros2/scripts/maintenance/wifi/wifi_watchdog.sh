#!/usr/bin/env bash
#
# WiFi Auto-Recovery Watchdog for Raspberry Pi
# =============================================
# Detects WiFi connectivity loss and recovers by reloading the brcmfmac driver
# when NetworkManager's built-in reconnect fails (driver firmware hang).
#
# The RPi 4B's Broadcom WiFi chip (brcmfmac) has a known issue where the
# driver firmware can hang after certain disconnects, preventing scan/associate.
# NetworkManager retry loops cannot recover from this; only a driver reload
# (modprobe -r / modprobe) or full reboot restores connectivity.
#
# Features:
#   - Ping-based connectivity check (gateway or custom target)
#   - Graduated recovery: NM restart first, driver reload if that fails
#   - Rate limiting and cooldown to prevent recovery loops
#   - Journald logging with structured messages
#   - Minimal resource usage (~0.01% CPU, ~2 MB memory)
#   - Configurable via /etc/default/wifi-watchdog
#
# Usage:
#   ./wifi_watchdog.sh                              # Monitor with defaults
#   ./wifi_watchdog.sh -t 192.168.137.1             # Custom ping target
#   ./wifi_watchdog.sh -i 10 -f 5                   # 10s interval, 5 fails
#   systemctl start wifi-watchdog.service            # Via systemd
#
# Configuration:
#   /etc/default/wifi-watchdog   - Settings override
#

set -euo pipefail

# =============================================================================
# CONFIGURATION DEFAULTS (override via /etc/default/wifi-watchdog or CLI)
# =============================================================================

# Ping target: "auto" = use default gateway, or specify an IP
PING_TARGET="${PING_TARGET:-auto}"

# WiFi interface to monitor
WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"

# Check interval in seconds
CHECK_INTERVAL_SEC="${CHECK_INTERVAL_SEC:-15}"

# Number of consecutive ping failures before recovery
MAX_FAILURES="${MAX_FAILURES:-3}"

# Ping timeout per attempt (seconds)
PING_TIMEOUT_SEC="${PING_TIMEOUT_SEC:-3}"

# Cooldown after a recovery before resuming checks (seconds)
RECOVERY_COOLDOWN_SEC="${RECOVERY_COOLDOWN_SEC:-60}"

# Maximum driver reloads per hour (safety limit)
MAX_RELOADS_PER_HOUR="${MAX_RELOADS_PER_HOUR:-5}"

# Modules to reload (in order for removal, reversed for loading)
BRCM_MODULES="${BRCM_MODULES:-brcmfmac_wcc brcmfmac}"

# Time to wait after module removal before reloading (seconds)
MODULE_RELOAD_DELAY_SEC="${MODULE_RELOAD_DELAY_SEC:-3}"

# Time to wait after module load for NM to reconnect (seconds)
NM_RECONNECT_WAIT_SEC="${NM_RECONNECT_WAIT_SEC:-30}"

# How often to log signal strength (every N successful checks, 0=disabled)
SIGNAL_LOG_INTERVAL="${SIGNAL_LOG_INTERVAL:-20}"

# =============================================================================
# LOAD CONFIGURATION FILE
# =============================================================================

load_config() {
    local file="$1"
    if [[ -f "$file" ]]; then
        # shellcheck source=/dev/null
        source "$file"
    fi
}

load_config "/etc/default/wifi-watchdog"

# =============================================================================
# STATE
# =============================================================================

CONSECUTIVE_FAILURES=0
RELOAD_TIMESTAMPS=()
CHECKS_SINCE_SIGNAL_LOG=0

# =============================================================================
# LOGGING
# =============================================================================

log() {
    local level="$1"
    shift
    logger -t "wifi-watchdog" -p "daemon.${level}" "$*"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level^^}] $*"
}

log_info()  { log "info" "$@"; }
log_warn()  { log "warning" "$@"; }
log_err()   { log "err" "$@"; }

# =============================================================================
# CLI ARGUMENT PARSING
# =============================================================================

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

WiFi Auto-Recovery Watchdog for Raspberry Pi

Options:
  -t TARGET    Ping target IP (default: auto-detect gateway)
  -w IFACE     WiFi interface (default: wlan0)
  -i SECONDS   Check interval (default: 15)
  -f COUNT     Consecutive failures before recovery (default: 3)
  -h           Show this help

All settings can be configured via /etc/default/wifi-watchdog

Examples:
  $(basename "$0")                          # Auto-detect gateway, defaults
  $(basename "$0") -t 192.168.137.1         # Specific ping target
  $(basename "$0") -i 10 -f 5              # 10s interval, 5 failures
  systemctl start wifi-watchdog.service     # Via systemd
EOF
    exit 0
}

while getopts "t:w:i:f:h" opt; do
    case "$opt" in
        t) PING_TARGET="$OPTARG" ;;
        w) WIFI_INTERFACE="$OPTARG" ;;
        i) CHECK_INTERVAL_SEC="$OPTARG" ;;
        f) MAX_FAILURES="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

resolve_ping_target() {
    if [[ "$PING_TARGET" == "auto" ]]; then
        # Get default gateway via the wifi interface
        local gw
        gw=$(ip route show dev "$WIFI_INTERFACE" default 2>/dev/null | awk '{print $3}' | head -1)
        if [[ -z "$gw" ]]; then
            # Fallback: any default gateway
            gw=$(ip route show default 2>/dev/null | awk '{print $3}' | head -1)
        fi
        echo "$gw"
    else
        echo "$PING_TARGET"
    fi
}

is_wifi_interface_up() {
    ip link show "$WIFI_INTERFACE" up 2>/dev/null | grep -q "state UP"
}

is_wifi_connected() {
    # Check if NM reports the wifi as connected
    local state
    state=$(nmcli -t -f DEVICE,STATE dev status 2>/dev/null | grep "^${WIFI_INTERFACE}:" | cut -d: -f2)
    [[ "$state" == "connected" ]]
}

can_ping() {
    local target="$1"
    if [[ -z "$target" ]]; then
        return 1
    fi
    ping -c 1 -W "$PING_TIMEOUT_SEC" -I "$WIFI_INTERFACE" "$target" &>/dev/null
}

get_signal_info() {
    # Returns "RSSI dBm, tx_bitrate Mbps" or empty string if unavailable
    local info
    info=$(iw dev "$WIFI_INTERFACE" link 2>/dev/null) || return
    local signal tx_rate
    signal=$(echo "$info" | awk '/signal:/{print $2}')
    tx_rate=$(echo "$info" | awk '/tx bitrate:/{print $3}')
    if [[ -n "$signal" ]]; then
        echo "signal=${signal}dBm tx=${tx_rate:-?}Mbps"
    fi
}

log_signal_if_due() {
    # Log signal strength every SIGNAL_LOG_INTERVAL successful checks
    if (( SIGNAL_LOG_INTERVAL <= 0 )); then
        return
    fi
    ((CHECKS_SINCE_SIGNAL_LOG++)) || true
    if (( CHECKS_SINCE_SIGNAL_LOG >= SIGNAL_LOG_INTERVAL )); then
        CHECKS_SINCE_SIGNAL_LOG=0
        local sig
        sig=$(get_signal_info)
        if [[ -n "$sig" ]]; then
            log_info "WiFi status: $sig"
        fi
    fi
}

check_reload_rate_limit() {
    local now
    now=$(date +%s)
    local one_hour_ago=$((now - 3600))

    # Remove timestamps older than 1 hour
    local new_timestamps=()
    for ts in "${RELOAD_TIMESTAMPS[@]}"; do
        if (( ts > one_hour_ago )); then
            new_timestamps+=("$ts")
        fi
    done
    RELOAD_TIMESTAMPS=("${new_timestamps[@]}")

    if (( ${#RELOAD_TIMESTAMPS[@]} >= MAX_RELOADS_PER_HOUR )); then
        return 1  # Rate limited
    fi
    return 0
}

record_reload() {
    RELOAD_TIMESTAMPS+=("$(date +%s)")
}

# =============================================================================
# RECOVERY ACTIONS
# =============================================================================

try_nm_restart() {
    log_warn "Attempting NetworkManager restart (soft recovery)"
    nmcli radio wifi off 2>/dev/null || true
    sleep 2
    nmcli radio wifi on 2>/dev/null || true
    sleep 10

    # Check if NM reconnected
    if is_wifi_connected; then
        log_info "Soft recovery successful (NM restart)"
        return 0
    fi
    return 1
}

try_driver_reload() {
    if ! check_reload_rate_limit; then
        log_err "Driver reload rate limited (${MAX_RELOADS_PER_HOUR}/hour). Skipping."
        return 1
    fi

    log_warn "Attempting brcmfmac driver reload (hard recovery)"

    # Step 1: Disable wifi in NM to release the interface
    nmcli radio wifi off 2>/dev/null || true
    sleep 1

    # Step 2: Remove modules (order matters: dependent modules first)
    local mod
    for mod in $BRCM_MODULES; do
        if lsmod | grep -q "^${mod}"; then
            log_info "Removing module: $mod"
            modprobe -r "$mod" 2>/dev/null || true
        fi
    done

    sleep "$MODULE_RELOAD_DELAY_SEC"

    # Step 3: Reload base module (brcmfmac loads brcmfmac_wcc as dependency)
    local base_module
    base_module=$(echo "$BRCM_MODULES" | awk '{print $NF}')  # Last module = base
    log_info "Loading module: $base_module"
    modprobe "$base_module"

    sleep 3

    # Step 4: Re-enable wifi in NM
    nmcli radio wifi on 2>/dev/null || true

    record_reload

    # Step 5: Wait for NM to reconnect
    log_info "Waiting ${NM_RECONNECT_WAIT_SEC}s for NetworkManager to reconnect..."
    local waited=0
    while (( waited < NM_RECONNECT_WAIT_SEC )); do
        sleep 5
        waited=$((waited + 5))
        if is_wifi_connected; then
            log_info "Hard recovery successful (driver reload) after ${waited}s"
            return 0
        fi
    done

    log_err "Hard recovery failed: WiFi did not reconnect within ${NM_RECONNECT_WAIT_SEC}s"
    return 1
}

# =============================================================================
# MAIN LOOP
# =============================================================================

main() {
    log_info "WiFi watchdog starting"
    log_info "Interface: $WIFI_INTERFACE"
    log_info "Check interval: ${CHECK_INTERVAL_SEC}s"
    log_info "Max failures before recovery: $MAX_FAILURES"
    log_info "Ping target: $PING_TARGET"
    log_info "Rate limit: ${MAX_RELOADS_PER_HOUR} reloads/hour"
    log_info "Signal log interval: every ${SIGNAL_LOG_INTERVAL} checks"

    # Initial wait for system to settle after boot
    sleep 10

    # Log initial signal strength
    local init_sig; init_sig=$(get_signal_info)
    if [[ -n "$init_sig" ]]; then
        log_info "Initial WiFi status: $init_sig"
    fi

    while true; do
        local target
        target=$(resolve_ping_target)

        if [[ -z "$target" ]]; then
            # No gateway — WiFi either not connected or no DHCP lease
            if ! is_wifi_connected; then
                # WiFi is fully disconnected (likely brcmfmac firmware hang).
                # Count this as a failure so we escalate to driver reload
                # after MAX_FAILURES iterations instead of looping forever.
                ((CONSECUTIVE_FAILURES++)) || true
                log_warn "WiFi not connected, no gateway (${CONSECUTIVE_FAILURES}/${MAX_FAILURES})"
            else
                # Connected but no gateway — unusual, count as failure
                ((CONSECUTIVE_FAILURES++)) || true
            fi
        elif can_ping "$target"; then
            # All good
            if (( CONSECUTIVE_FAILURES > 0 )); then
                log_info "Connectivity restored (was at ${CONSECUTIVE_FAILURES} failures)"
            fi
            CONSECUTIVE_FAILURES=0
            log_signal_if_due
            sleep "$CHECK_INTERVAL_SEC"
            continue
        else
            ((CONSECUTIVE_FAILURES++)) || true
        fi

        log_warn "Ping failed (${CONSECUTIVE_FAILURES}/${MAX_FAILURES})"

        if (( CONSECUTIVE_FAILURES >= MAX_FAILURES )); then
            log_warn "Connectivity lost for ${CONSECUTIVE_FAILURES} consecutive checks"

            # Stage 1: Try NM restart (handles hotspot-restart scenario)
            if try_nm_restart; then
                CONSECUTIVE_FAILURES=0
                local sig; sig=$(get_signal_info)
                log_info "Entering cooldown (${RECOVERY_COOLDOWN_SEC}s)${sig:+ [$sig]}"
                sleep "$RECOVERY_COOLDOWN_SEC"
                continue
            fi

            # Stage 2: Reload driver (handles brcmfmac firmware hang)
            if try_driver_reload; then
                CONSECUTIVE_FAILURES=0
                local sig; sig=$(get_signal_info)
                log_info "Entering cooldown (${RECOVERY_COOLDOWN_SEC}s)${sig:+ [$sig]}"
                sleep "$RECOVERY_COOLDOWN_SEC"
                continue
            fi

            # Both stages failed
            log_err "All recovery attempts failed. Will retry next cycle."
            CONSECUTIVE_FAILURES=0
            sleep "$RECOVERY_COOLDOWN_SEC"
        fi

        sleep "$CHECK_INTERVAL_SEC"
    done
}

# Trap SIGTERM/SIGINT for clean shutdown
trap 'log_info "WiFi watchdog stopping (signal received)"; exit 0' SIGTERM SIGINT

main
