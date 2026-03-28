#!/bin/bash
# ==============================================
# Field Trial Logging Script
# ==============================================
# Runs alongside ROS2 during field trials to capture data for
# diagnosing network disconnections on Ethernet-connected RPis.
#
# Usage:
#   ./field_trial_logging.sh [OPTIONS] [PING_TARGET]
#
# Options:
#   --role <vehicle|arm>     RPi role (auto-detected if omitted)
#   --ping-target <IP>       Router IP to ping (default: 192.168.1.1)
#   --broker-ip <IP>         Vehicle RPi / MQTT broker IP (default: 192.168.1.100)
#   --eth-iface <NAME>       Ethernet interface name (auto-detected if omitted)
#   --interval <SECONDS>     Monitoring interval (default: 30)
#
# Backward compatibility: first positional arg is accepted as ping target.
#
# Press Ctrl+C to stop. On shutdown the script collects system logs,
# creates a tar.gz archive, and prints a summary.
#
# Platform: Raspberry Pi 4B, Ubuntu 24.04
# ==============================================

set -euo pipefail

# ==============================================
# Configuration (defaults)
# ==============================================
ROLE=""
PING_TARGET="192.168.1.1"
BROKER_IP="192.168.1.100"
ETH_IFACE=""
MONITOR_INTERVAL=30
LOG_BASE_DIR="${LOG_BASE_DIR:-$HOME/field_trial_logs}"
ETHTOOL_INTERVAL=300  # 5 minutes

# ==============================================
# Argument parsing (named args with positional fallback)
# ==============================================
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --role)
            ROLE="$2"
            if [[ "$ROLE" != "vehicle" && "$ROLE" != "arm" ]]; then
                echo "Invalid role '$ROLE'. Must be 'vehicle' or 'arm'."
                exit 1
            fi
            shift 2
            ;;
        --ping-target)
            PING_TARGET="$2"
            shift 2
            ;;
        --broker-ip)
            BROKER_IP="$2"
            shift 2
            ;;
        --eth-iface)
            ETH_IFACE="$2"
            shift 2
            ;;
        --interval)
            MONITOR_INTERVAL="$2"
            shift 2
            ;;
        -h|--help)
            head -n 22 "$0" | tail -n +2 | sed 's/^# //' | sed 's/^#//'
            exit 0
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

# Backward compatibility: first positional arg is ping target
if [[ ${#POSITIONAL_ARGS[@]} -ge 1 ]]; then
    PING_TARGET="${POSITIONAL_ARGS[0]}"
fi
if [[ ${#POSITIONAL_ARGS[@]} -ge 2 ]]; then
    MONITOR_INTERVAL="${POSITIONAL_ARGS[1]}"
fi

# ==============================================
# Role auto-detection
# ==============================================
ROLE_SOURCE=""
if [[ -n "$ROLE" ]]; then
    ROLE_SOURCE="explicit"
elif systemctl is-active --quiet mosquitto.service 2>/dev/null; then
    ROLE="vehicle"
    ROLE_SOURCE="auto-detected from mosquitto.service"
elif systemctl is-active --quiet arm_launch.service 2>/dev/null; then
    ROLE="arm"
    ROLE_SOURCE="auto-detected from arm_launch.service"
else
    ROLE="arm"
    ROLE_SOURCE="default -- no identifying services detected"
fi

# ==============================================
# Ethernet interface auto-detection
# ==============================================
detect_ethernet_iface() {
    if [[ -n "$ETH_IFACE" ]]; then
        echo "$ETH_IFACE"
        return
    fi
    # Check eth0 first
    if [[ -d "/sys/class/net/eth0" ]]; then
        echo "eth0"
        return
    fi
    # Check en* interfaces (excluding lo and wlan*)
    local iface
    for iface in /sys/class/net/en*; do
        if [[ -d "$iface" ]]; then
            echo "$(basename "$iface")"
            return
        fi
    done
    # Nothing found
    echo ""
}

ETH_IFACE_DETECTED=$(detect_ethernet_iface)
if [[ -z "$ETH_IFACE" && -n "$ETH_IFACE_DETECTED" && "$ETH_IFACE_DETECTED" != "eth0" ]]; then
    echo "[INFO] Auto-detected Ethernet interface: $ETH_IFACE_DETECTED"
fi
ETH_IFACE="${ETH_IFACE_DETECTED}"

# ==============================================
# Session directory setup
# ==============================================
SESSION_START=$(date +%Y%m%d_%H%M%S)
SESSION_START_EPOCH=$(date +%s)
SESSION_START_JOURNALCTL=$(date "+%Y-%m-%d %H:%M:%S")
SESSION_DIR="$LOG_BASE_DIR/session_${SESSION_START}"
SYSLOG_DIR="$SESSION_DIR/system_logs"

# PID tracking for all background processes
MONITOR_PID=""
ARM_PID=""
YANTHRA_PID=""
VEHICLE_PID=""
MOSQUITTO_PID=""
DMESG_PID=""
ETHTOOL_PID=""
MEMTRACK_PID=""
DISKMON_PID=""
CANSTATS_PID=""

if [ -d "$SESSION_DIR" ]; then
    echo "[ERROR] Session directory already exists: $SESSION_DIR"
    echo "        Another logging session may be running. Exiting."
    exit 1
fi
mkdir -p "$SYSLOG_DIR"

# Create "latest" symlink so sync.sh --collect-logs can find the current session.
# ln -sfn atomically replaces any existing symlink (-n prevents latest/latest nesting).
ln -sfn "$SESSION_DIR" "$LOG_BASE_DIR/latest"

# ==============================================
# Startup banner
# ==============================================
echo "=============================================="
echo "Field Trial Logging"
echo "=============================================="
echo "Session:   $SESSION_DIR"
echo "Hostname:  $(hostname)"
echo "Started:   $(date --iso-8601=seconds)"
if [[ "$ROLE_SOURCE" == "default -- no identifying services detected" ]]; then
    echo "[WARN] Role: $ROLE ($ROLE_SOURCE)"
else
    echo "Role:      $ROLE ($ROLE_SOURCE)"
fi
echo ""
echo "Monitoring:"
echo "  - Ethernet stats (${ETH_IFACE:-none})"
echo "  - Real-time dmesg streaming"
echo "  - CPU temperature"
echo "  - System load"
echo "  - Memory (free/available, task 19.2)"
echo "  - Per-process memory every 5m (task 19.3)"
echo "  - Disk space every 5m (task 19.4)"
if ip link show can0 &>/dev/null; then
    echo "  - CAN bus statistics every 60s (task 19.6)"
fi
if [[ "$ROLE" == "vehicle" ]]; then
    echo "  - Mosquitto broker logs"
fi
echo ""
echo "Services:"
if [[ "$ROLE" == "vehicle" ]]; then
    echo "  - vehicle_launch.service"
    echo "  - mosquitto.service"
else
    echo "  - arm_launch.service"
fi
echo ""
echo "Ping targets:"
echo "  - Router: $PING_TARGET (every ${MONITOR_INTERVAL}s)"
if [[ "$ROLE" == "arm" ]]; then
    echo "  - Vehicle RPi (broker): $BROKER_IP (every ${MONITOR_INTERVAL}s)"
else
    echo "  - Broker: self (vehicle is the broker)"
fi
echo "=============================================="
echo ""

# ==============================================
# Ethernet status capture
# ==============================================
get_ethernet_status() {
    # Returns: state rx_errors tx_errors drops
    if [[ -z "$ETH_IFACE" ]]; then
        echo "n/a n/a n/a n/a"
        return
    fi
    if [[ ! -d "/sys/class/net/$ETH_IFACE" ]]; then
        echo "n/a n/a n/a n/a"
        return
    fi

    local output
    output=$(ip -s link show "$ETH_IFACE" 2>/dev/null) || {
        echo "n/a n/a n/a n/a"
        return
    }

    # Parse link state
    local state="DOWN"
    if echo "$output" | grep -q "state UP"; then
        state="UP"
    fi

    # Parse RX line (3rd line of stats: errors dropped overrun mcast)
    # ip -s link output format:
    #   RX:  bytes packets errors dropped ...
    #        <val> <val>   <val>  <val>   ...
    #   TX:  bytes packets errors dropped ...
    #        <val> <val>   <val>  <val>   ...
    local rx_errors=0 rx_drops=0 tx_errors=0 tx_drops=0

    # Use awk to extract RX and TX error/drop counters
    read -r rx_errors rx_drops tx_errors tx_drops < <(
        echo "$output" | awk '
            /RX:/{getline; rx_err=$3; rx_drop=$4}
            /TX:/{getline; tx_err=$3; tx_drop=$4}
            END{print rx_err, rx_drop, tx_err, tx_drop}
        '
    ) || true

    echo "$state ${rx_errors:-0} ${tx_errors:-0} ${rx_drops:-0}"
}

# ==============================================
# CPU temperature capture
# ==============================================
get_cpu_temp() {
    local temp_file="/sys/class/thermal/thermal_zone0/temp"
    if [[ -r "$temp_file" ]]; then
        local raw
        raw=$(cat "$temp_file" 2>/dev/null) || { echo "n/a"; return; }
        # Convert millidegrees to Celsius (e.g., 52100 -> 52.1)
        echo "$(echo "scale=1; $raw / 1000" | bc 2>/dev/null || echo "n/a")"
    else
        echo "n/a"
    fi
}

# ==============================================
# System load capture
# ==============================================
get_system_load() {
    if [[ -r /proc/loadavg ]]; then
        awk '{print $1}' /proc/loadavg
    else
        echo "n/a"
    fi
}

# ==============================================
# Memory metrics capture (task 19.2)
# ==============================================
get_memory_metrics() {
    # Returns: mem_free_mb mem_avail_mb (from /proc/meminfo)
    if [[ ! -r /proc/meminfo ]]; then
        echo "n/a n/a"
        return
    fi
    awk '
        /^MemFree:/{free=$2}
        /^MemAvailable:/{avail=$2}
        END{printf "%.0f %.0f", free/1024, avail/1024}
    ' /proc/meminfo
}

# ==============================================
# Real-time dmesg streaming
# ==============================================
DMESG_KEYWORDS="eth|usb|netdev|carrier|link|brcmfmac|voltage|throttled|oom|out of memory|mcp251x|spi"

start_dmesg_streaming() {
    local logfile="$SESSION_DIR/dmesg_network.log"

    # Try dmesg --follow directly
    if dmesg --follow 2>/dev/null | grep -iE "$DMESG_KEYWORDS" >> "$logfile" 2>/dev/null & then
        DMESG_PID=$!
        # Verify it's still running after a brief pause
        sleep 0.5
        if kill -0 "$DMESG_PID" 2>/dev/null; then
            echo "[INFO] dmesg streaming started (PID $DMESG_PID)"
            return
        fi
    fi

    # Try with sudo -n (non-interactive)
    if sudo -n dmesg --follow 2>/dev/null | grep -iE "$DMESG_KEYWORDS" >> "$logfile" 2>/dev/null & then
        DMESG_PID=$!
        sleep 0.5
        if kill -0 "$DMESG_PID" 2>/dev/null; then
            echo "[INFO] dmesg streaming started via sudo (PID $DMESG_PID)"
            return
        fi
    fi

    # Fallback: periodic dmesg capture every 60s
    echo "[WARN] dmesg --follow not available -- falling back to periodic capture (60s)"
    (
        while true; do
            dmesg 2>/dev/null | grep -iE "$DMESG_KEYWORDS" >> "$logfile" 2>/dev/null || \
            sudo -n dmesg 2>/dev/null | grep -iE "$DMESG_KEYWORDS" >> "$logfile" 2>/dev/null || true
            sleep 60
        done
    ) &
    DMESG_PID=$!
    echo "[INFO] dmesg periodic capture started (PID $DMESG_PID)"
}

# ==============================================
# Optional ethtool capture
# ==============================================
start_ethtool_capture() {
    if [[ -z "$ETH_IFACE" ]]; then
        return
    fi
    if ! command -v ethtool &>/dev/null; then
        echo "[INFO] ethtool not available -- skipping detailed Ethernet stats"
        return
    fi

    local logfile="$SESSION_DIR/ethtool_stats.log"
    (
        while true; do
            echo "--- $(date --iso-8601=seconds) ---" >> "$logfile"
            ethtool -S "$ETH_IFACE" >> "$logfile" 2>&1 || true
            echo "" >> "$logfile"
            sleep "$ETHTOOL_INTERVAL"
        done
    ) &
    ETHTOOL_PID=$!
    echo "[INFO] ethtool capture started every ${ETHTOOL_INTERVAL}s (PID $ETHTOOL_PID)"
}

# ==============================================
# ARM_client capture
# ==============================================
start_arm_capture() {
    if systemctl is-active --quiet arm_launch.service 2>/dev/null; then
        echo "[INFO] Capturing ARM_client logs from arm_launch.service"
        journalctl -u arm_launch.service -f --no-pager 2>&1 \
            | tee -a "$SESSION_DIR/arm_client.log" &
        ARM_PID=$!
    else
        echo "[WARN] arm_launch.service is not running -- skipping ARM_client capture"
        echo "$(date --iso-8601=seconds) WARNING: arm_launch.service not active at startup" \
            > "$SESSION_DIR/arm_client.log"
    fi
}

# ==============================================
# yanthra_move capture
# ==============================================
# NOTE: yanthra_move_node runs inside arm_launch.service (via pragati_complete.launch.py).
# There is no standalone yanthra_move.service.  Its output is already captured by
# start_arm_capture() via journalctl -u arm_launch.service.  This function is kept
# as a no-op to avoid breaking callers; YANTHRA_PID stays empty.
start_yanthra_capture() {
    echo "[INFO] yanthra_move_node output captured via arm_launch.service (no separate service)"
}

# ==============================================
# vehicle_launch capture
# ==============================================
start_vehicle_capture() {
    if systemctl is-active --quiet vehicle_launch.service 2>/dev/null; then
        echo "[INFO] Capturing vehicle_launch logs from vehicle_launch.service"
        journalctl -u vehicle_launch.service -f --no-pager 2>&1 \
            | tee -a "$SESSION_DIR/vehicle_launch.log" &
        VEHICLE_PID=$!
    else
        echo "[WARN] vehicle_launch.service is not running -- skipping vehicle_launch capture"
        echo "$(date --iso-8601=seconds) WARNING: vehicle_launch.service not active at startup" \
            > "$SESSION_DIR/vehicle_launch.log"
    fi
}

# ==============================================
# Mosquitto broker log capture (vehicle only)
# ==============================================
start_mosquitto_capture() {
    if systemctl is-active --quiet mosquitto.service 2>/dev/null; then
        echo "[INFO] Capturing Mosquitto broker logs from mosquitto.service"
        journalctl -u mosquitto.service -f --no-pager 2>&1 \
            | tee -a "$SESSION_DIR/mosquitto_broker.log" &
        MOSQUITTO_PID=$!
    else
        echo "[WARN] mosquitto.service is not running -- skipping broker log capture"
        echo "$(date --iso-8601=seconds) WARNING: mosquitto.service not active at startup" \
            > "$SESSION_DIR/mosquitto_broker.log"
    fi
}

# ==============================================
# Network monitoring (background loop)
# ==============================================
network_monitor_loop() {
    local logfile="$SESSION_DIR/network_monitor.log"
    echo "# timestamp  ping_router  ping_broker  eth_state  eth_rx_errors  eth_tx_errors  eth_drops  cpu_temp  load  mem_free_mb  mem_avail_mb" > "$logfile"

    # Warn once if Ethernet interface is missing
    if [[ -z "$ETH_IFACE" ]]; then
        echo "[WARN] Ethernet interface not found -- monitoring ping only" >&2
    elif [[ ! -d "/sys/class/net/$ETH_IFACE" ]]; then
        echo "[WARN] Ethernet interface $ETH_IFACE not found" >&2
    fi

    # Warn once if thermal zone is missing
    if [[ ! -r /sys/class/thermal/thermal_zone0/temp ]]; then
        echo "[WARN] /sys/class/thermal/thermal_zone0/temp not available -- cpu_temp will show n/a" >&2
    fi

    while true; do
        local ts
        ts=$(date --iso-8601=seconds)

        # Ping router
        local rtt_router
        rtt_router=$(ping -c1 -W2 "$PING_TARGET" 2>/dev/null \
            | awk -F'[= ]' '/time=/{for(i=1;i<=NF;i++) if($i=="time") print $(i+1)}') || true
        rtt_router="${rtt_router:-timeout}"

        # Ping broker (arm role) or show "self" (vehicle role)
        local rtt_broker
        if [[ "$ROLE" == "arm" ]]; then
            rtt_broker=$(ping -c1 -W2 "$BROKER_IP" 2>/dev/null \
                | awk -F'[= ]' '/time=/{for(i=1;i<=NF;i++) if($i=="time") print $(i+1)}') || true
            rtt_broker="${rtt_broker:-timeout}"
        else
            rtt_broker="self"
        fi

        # Ethernet stats
        local eth_state eth_rx_err eth_tx_err eth_drops
        read -r eth_state eth_rx_err eth_tx_err eth_drops < <(get_ethernet_status)

        # CPU temp & load
        local cpu_temp load_avg
        cpu_temp=$(get_cpu_temp)
        load_avg=$(get_system_load)

        # Memory metrics (task 19.2)
        local mem_free mem_avail
        read -r mem_free mem_avail < <(get_memory_metrics)

        local iface_label="${ETH_IFACE:-eth0}"
        echo "${ts}  ping_router=${rtt_router}ms  ping_broker=${rtt_broker}ms  ${iface_label}_state=${eth_state}  ${iface_label}_rx_errors=${eth_rx_err}  ${iface_label}_tx_errors=${eth_tx_err}  ${iface_label}_drops=${eth_drops}  cpu_temp=${cpu_temp}C  load=${load_avg}  mem_free_mb=${mem_free:-n/a}  mem_avail_mb=${mem_avail:-n/a}" >> "$logfile"

        sleep "$MONITOR_INTERVAL"
    done
}

start_network_monitor() {
    echo "[INFO] Starting network monitor (interval=${MONITOR_INTERVAL}s, router=${PING_TARGET})"
    if [[ "$ROLE" == "arm" ]]; then
        echo "[INFO] Also pinging vehicle RPi (broker) at $BROKER_IP"
    fi
    network_monitor_loop &
    MONITOR_PID=$!
}

# ==============================================
# Per-process memory tracking (task 19.3)
# ==============================================
start_process_memory_tracking() {
    local logfile="$SESSION_DIR/process_memory.log"
    echo "# timestamp  pid  process  VmRSS_kb" > "$logfile"
    (
        while true; do
            local ts
            ts=$(date --iso-8601=seconds)
            # Capture VmRSS for known ROS2/robot processes
            for procname in ros2 python3 arm_client yanthra_move vehicle_control mg6010_controller; do
                while IFS= read -r pid; do
                    [[ -z "$pid" ]] && continue
                    local vmrss
                    vmrss=$(awk '/^VmRSS:/{print $2}' "/proc/${pid}/status" 2>/dev/null) || continue
                    [[ -z "$vmrss" ]] && continue
                    echo "${ts}  ${pid}  ${procname}  ${vmrss}" >> "$logfile"
                done < <(pgrep -x "$procname" 2>/dev/null || true)
            done
            sleep 300  # every 5 minutes
        done
    ) &
    MEMTRACK_PID=$!
    echo "[INFO] Per-process memory tracking started (PID $MEMTRACK_PID, interval=300s)"
}

# ==============================================
# Disk space monitoring (task 19.4)
# ==============================================
start_disk_monitoring() {
    local logfile="$SESSION_DIR/disk_monitor.log"
    echo "# timestamp  filesystem  size  used  avail  use_pct  mount" > "$logfile"
    (
        while true; do
            local ts
            ts=$(date --iso-8601=seconds)
            df -h 2>/dev/null | awk -v ts="$ts" 'NR>1 {
                use=$5; sub(/%/,"",use);
                if (use+0 > 0) printf "%s  %s  %s  %s  %s  %s%%  %s\n", ts, $1, $2, $3, $4, $5, $6
            }' >> "$logfile" || true
            # Warn if any filesystem >80% used
            df 2>/dev/null | awk 'NR>1 {use=$5; sub(/%/,"",use); if (use+0 > 80) print "[WARN] Disk >80% full:", $6, $5}' >&2 || true
            sleep 300  # every 5 minutes
        done
    ) &
    DISKMON_PID=$!
    echo "[INFO] Disk space monitoring started (PID $DISKMON_PID, interval=300s)"
}

# ==============================================
# CAN bus statistics (task 19.6)
# ==============================================
start_can_stats() {
    if ! ip link show can0 &>/dev/null; then
        echo "[INFO] can0 not present -- skipping CAN bus statistics"
        return
    fi
    local logfile="$SESSION_DIR/can_stats.log"
    echo "# CAN bus statistics (ip -s link show can0, every 60s)" > "$logfile"
    (
        while true; do
            echo "--- $(date --iso-8601=seconds) ---" >> "$logfile"
            ip -s link show can0 >> "$logfile" 2>&1 || true
            echo "" >> "$logfile"
            sleep 60
        done
    ) &
    CANSTATS_PID=$!
    echo "[INFO] CAN bus statistics started (interval=60s)"
}

# ==============================================
# Startup fix verification
# ==============================================
verify_applied_fixes() {
    local logfile="$SESSION_DIR/fix_verification.log"
    local ok_count=0
    local total_count=0

    echo "=== Fix Verification - $(date --iso-8601=seconds) ===" > "$logfile"
    echo "Hostname: $(hostname)" >> "$logfile"
    echo "Role: $ROLE" >> "$logfile"
    echo "" >> "$logfile"

    check_fix() {
        local description="$1"
        local result="$2"
        total_count=$((total_count + 1))
        if [[ "$result" == "OK" ]]; then
            echo "[OK]      $description" >> "$logfile"
            ok_count=$((ok_count + 1))
        else
            echo "[MISSING] $description" >> "$logfile"
        fi
    }

    # 1. USB autosuspend disabled
    local usb_autosuspend
    usb_autosuspend=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
    if [[ "$usb_autosuspend" == "-1" ]]; then
        check_fix "USB autosuspend disabled (autosuspend=-1)" "OK"
    else
        check_fix "USB autosuspend disabled (autosuspend=$usb_autosuspend)" "MISSING"
    fi

    # 2. USB kernel param in cmdline.txt
    if grep -q "usbcore.autosuspend=-1" /boot/firmware/cmdline.txt 2>/dev/null; then
        check_fix "USB autosuspend kernel param in cmdline.txt" "OK"
    else
        check_fix "USB autosuspend kernel param in cmdline.txt" "MISSING"
    fi

    # 3. SSH keepalive config
    if [[ -f /etc/ssh/sshd_config.d/keepalive.conf ]]; then
        check_fix "SSH keepalive config exists" "OK"
    else
        check_fix "SSH keepalive config exists" "MISSING"
    fi

    # 4. WiFi power save off
    local wifi_ps
    wifi_ps=$(iw dev wlan0 get power_save 2>/dev/null | awk '{print $NF}' || echo "n/a")
    if [[ "$wifi_ps" == "off" || "$wifi_ps" == "n/a" ]]; then
        check_fix "WiFi power save off (${wifi_ps})" "OK"
    else
        check_fix "WiFi power save off (${wifi_ps})" "MISSING"
    fi

    # 5. CAN watchdog service active
    if systemctl is-active --quiet can-watchdog@can0.service 2>/dev/null; then
        check_fix "CAN watchdog service active" "OK"
    else
        check_fix "CAN watchdog service active" "MISSING"
    fi

    # 6. pigpiod service active
    if systemctl is-active --quiet pigpiod.service 2>/dev/null || \
       systemctl is-active --quiet pigpiod_custom.service 2>/dev/null; then
        check_fix "pigpiod service active" "OK"
    else
        check_fix "pigpiod service active" "MISSING"
    fi

    # 7. Role-specific launch service active
    if [[ "$ROLE" == "vehicle" ]]; then
        if systemctl is-active --quiet vehicle_launch.service 2>/dev/null; then
            check_fix "vehicle_launch.service active" "OK"
        else
            check_fix "vehicle_launch.service active" "MISSING"
        fi
    else
        if systemctl is-active --quiet arm_launch.service 2>/dev/null; then
            check_fix "arm_launch.service active" "OK"
        else
            check_fix "arm_launch.service active" "MISSING"
        fi
    fi

    # 8. Mosquitto active (vehicle only)
    if [[ "$ROLE" == "vehicle" ]]; then
        if systemctl is-active --quiet mosquitto.service 2>/dev/null; then
            check_fix "Mosquitto service active" "OK"
        else
            check_fix "Mosquitto service active" "MISSING"
        fi
    fi

    echo "" >> "$logfile"
    echo "Summary: ${ok_count}/${total_count} checks passed" >> "$logfile"
    echo "[INFO] Fix verification: ${ok_count}/${total_count} checks passed (see fix_verification.log)"
}

# ==============================================
# ROS2 parameter dump at startup (task 19.5)
# ==============================================
dump_ros2_params() {
    local logfile="$SESSION_DIR/ros2_params.log"
    echo "=== ROS2 Parameter Dump - $(date --iso-8601=seconds) ===" > "$logfile"
    echo "Hostname: $(hostname)" >> "$logfile"
    echo "Role: $ROLE" >> "$logfile"
    echo "" >> "$logfile"

    if ! command -v ros2 &>/dev/null; then
        echo "[WARN] ros2 command not found -- skipping parameter dump" | tee -a "$logfile"
        return
    fi

    # Source ROS2 if available
    # shellcheck source=/dev/null
    [[ -f /opt/ros/jazzy/setup.bash ]] && source /opt/ros/jazzy/setup.bash 2>/dev/null || true
    [[ -f "$HOME/pragati_ros2/install/setup.bash" ]] && source "$HOME/pragati_ros2/install/setup.bash" 2>/dev/null || true

    # List active nodes and dump parameters for each (2s timeout per node)
    local nodes
    nodes=$(ros2 node list 2>/dev/null) || {
        echo "[WARN] ros2 node list failed -- ROS2 may not be running yet" | tee -a "$logfile"
        return
    }

    if [[ -z "$nodes" ]]; then
        echo "[INFO] No ROS2 nodes found at startup" >> "$logfile"
        echo "[INFO] ros2_params.log: no nodes found at startup"
        return
    fi

    echo "$nodes" | while IFS= read -r node; do
        [[ -z "$node" ]] && continue
        echo "--- Node: $node ---" >> "$logfile"
        timeout 2 ros2 param dump "$node" >> "$logfile" 2>&1 || \
            echo "  (param dump timed out or failed)" >> "$logfile"
        echo "" >> "$logfile"
    done

    echo "[INFO] ROS2 parameter dump complete (see ros2_params.log)"
}

# ==============================================
# Cleanup handler (called by trap on EXIT)
# ==============================================
cleanup() {
    set +e  # Don't exit on errors during cleanup
    echo ""
    echo "=============================================="
    echo "Shutting down..."
    echo "=============================================="

    # Kill all background processes and their process groups.
    # Background pipelines (journalctl | tee, dmesg | grep) each run in their
    # own process group.  Killing only the last stage ($!) leaves the data-source
    # process (journalctl, dmesg) orphaned.  `kill -- -$pid` sends the signal to
    # the entire process group, terminating all pipeline stages.
    for pid in $MONITOR_PID $ARM_PID $YANTHRA_PID $VEHICLE_PID $MOSQUITTO_PID $DMESG_PID $ETHTOOL_PID $MEMTRACK_PID $DISKMON_PID $CANSTATS_PID; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done

    # Collect system logs
    echo "[INFO] Collecting system logs..."

    # syslog
    if [ -r /var/log/syslog ]; then
        cp /var/log/syslog "$SYSLOG_DIR/syslog.txt" 2>/dev/null
    elif sudo -n cp /var/log/syslog "$SYSLOG_DIR/syslog.txt" 2>/dev/null; then
        true  # copied via sudo
    else
        echo "[WARN] Cannot read /var/log/syslog (no permission)"
    fi

    # journalctl since session start
    if journalctl --since "$SESSION_START_JOURNALCTL" --no-pager \
            > "$SYSLOG_DIR/journalctl.txt" 2>/dev/null; then
        true
    elif sudo -n journalctl --since "$SESSION_START_JOURNALCTL" --no-pager \
            > "$SYSLOG_DIR/journalctl.txt" 2>/dev/null; then
        true
    else
        echo "[WARN] Cannot collect journalctl output (no permission)"
    fi

    # dmesg -- fallback capture in case streaming wasn't available
    if dmesg > "$SYSLOG_DIR/dmesg.txt" 2>/dev/null; then
        true
    elif sudo -n dmesg > "$SYSLOG_DIR/dmesg.txt" 2>/dev/null; then
        true
    else
        echo "[WARN] Cannot collect dmesg output (no permission)"
    fi

    # Create archive
    local archive="$SESSION_DIR.tar.gz"
    tar czf "$archive" -C "$LOG_BASE_DIR" "session_${SESSION_START}" 2>/dev/null || true

    # Summary
    local end_ts
    end_ts=$(date +%s)
    local duration=$(( end_ts - SESSION_START_EPOCH ))
    local duration_min=$(( duration / 60 ))
    local duration_sec=$(( duration % 60 ))

    echo ""
    echo "=============================================="
    echo "Session Summary"
    echo "=============================================="
    echo "Duration:    ${duration_min}m ${duration_sec}s (${duration}s)"
    echo ""
    echo "Log files:"
    while IFS= read -r f; do
        local size
        size=$(du -h "$f" | cut -f1)
        printf "  %-40s %s\n" "$(basename "$f")" "$size"
    done < <(find "$SESSION_DIR" -type f -not -path "*/system_logs/*" | sort)
    if [ -d "$SYSLOG_DIR" ] && [ "$(ls -A "$SYSLOG_DIR" 2>/dev/null)" ]; then
        echo "  --- system logs ---"
        while IFS= read -r f; do
            local size
            size=$(du -h "$f" | cut -f1)
            printf "  %-40s %s\n" "$(basename "$f")" "$size"
        done < <(find "$SYSLOG_DIR" -type f | sort)
    fi
    echo "Session dir: $SESSION_DIR"
    if [ -f "$archive" ]; then
        echo "Archive:     $archive ($(du -h "$archive" | cut -f1))"
    fi
    echo "Ended:       $(date --iso-8601=seconds)"
    echo "=============================================="
}

trap cleanup EXIT

# ==============================================
# Main
# ==============================================

# Run fix verification at startup (non-blocking)
verify_applied_fixes

# Dump ROS2 parameters at startup (task 19.5, non-blocking)
dump_ros2_params

# Start common monitoring
start_dmesg_streaming
start_ethtool_capture
start_network_monitor

# Start per-process memory tracking (task 19.3)
start_process_memory_tracking

# Start disk space monitoring (task 19.4)
start_disk_monitoring

# Start CAN bus statistics (task 19.6, only if can0 exists)
start_can_stats

# Start role-specific service capture
if [[ "$ROLE" == "arm" ]]; then
    # task 19.1: mg6010_controller_node runs inside arm_launch.service process tree.
    # Its stdout/stderr is already captured by journalctl -u arm_launch.service below.
    # No separate motor_control.service journal entry is needed.
    start_arm_capture
    start_yanthra_capture
elif [[ "$ROLE" == "vehicle" ]]; then
    start_vehicle_capture
    start_mosquitto_capture
fi

echo ""
echo "[INFO] Logging active. Press Ctrl+C to stop."
echo ""

# Wait forever (until signal)
while true; do sleep 60; done
