#!/usr/bin/env bash
#
# Unified Sync Script for Deployment
# ====================================
#
# A single, reliable script to sync workspace to remote machines.
#
# Usage:
#   ./sync.sh                    # Sync source + scripts + config (default)
#   ./sync.sh --all              # Sync everything including data/models
#   ./sync.sh --source           # Sync only source code
#   ./sync.sh --build            # Sync and trigger native build on target
#   ./sync.sh --quick            # Quick sync (scripts only, no delete)
#   ./sync.sh --dry-run          # Show what would be synced
#   ./sync.sh --deploy-cross     # Deploy pre-cross-compiled ARM binaries (for RPi)
#   ./sync.sh --deploy-local     # Deploy locally-built x86 binaries (Ubuntu-to-Ubuntu)
#   ./sync.sh --provision        # Apply OS fixes + install/enable systemd services
#   ./sync.sh --verify           # Check fix/service status (read-only, on by default)
#   ./sync.sh --no-verify        # Skip automatic post-sync verification
#   ./sync.sh --test-mqtt        # Test MQTT connectivity from vehicle to arms
#   ./sync.sh --verify-fleet     # Check dashboard/agent versions across fleet
#
# Configuration:
#   Edit ~/.pragati_sync.conf or use command line args
#

set -e

# ============================================================================
# Configuration
# ============================================================================

# Resolve workspace root FIRST -- other config paths depend on WORKSPACE
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${SCRIPT_DIR}"

# ============================================================================
# Configuration
# ============================================================================

CONFIG_FILE_OLD="$HOME/.pragati_sync.conf"
CONFIG_FILE="$WORKSPACE/config.env"
PROFILE_NAME=""

# Load old config file for backward compatibility
if [ -f "$CONFIG_FILE_OLD" ]; then
    source "$CONFIG_FILE_OLD"
fi

# Load new config.env if exists (overrides old config)
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
elif [ ! -f "$CONFIG_FILE_OLD" ]; then
    # No config file found at all -- warn so operators know why hosts are missing
    echo "WARNING: No config file found at $CONFIG_FILE" >&2
    echo "  Create one with: cp config.env.example config.env" >&2
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

    # Override defaults with profile values if they exist
    if [ -n "${!ip_var}" ]; then
        export RPI_IP="${!ip_var}"
        echo "  Profile '$profile': Using IP ${!ip_var}"
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
}

# Defaults (can be overridden by config file, env vars, or command line)
RPI_USER="${RPI_USER:-ubuntu}"
RPI_IP="${RPI_IP:-}"  # Must be set by user (single IP or first IP)
RPI_TARGET_DIR="${RPI_TARGET_DIR:-}"  # Will be set to /home/$RPI_USER/pragati_ros2
RPI_SSH_KEY="${RPI_SSH_KEY:-}"  # Optional SSH key
RPI_IPS=()            # Array for multiple IPs (--ips option)
ALL_ARMS="${ALL_ARMS:-}"  # Legacy: Comma-separated list of ARM names
ALL_PROFILES="${ALL_PROFILES:-}"  # New: Comma-separated list of profile names
RPI_DIR=""  # Computed later from RPI_TARGET_DIR or default

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ============================================================================
# Parse Arguments
# ============================================================================

MODE="default"
DRY_RUN=false
TRIGGER_BUILD=false
DEPLOY_CROSS=false
DEPLOY_LOCAL=false
VERBOSE=false
SAVE_CONFIG=false
DO_PROVISION=false
DO_VERIFY=true
RPI_ROLE=""
ARM_ID=""           # Per-arm identity written to /etc/default/pragati-arm on provision
MQTT_ADDRESS_OVERRIDE=""  # Optional MQTT address override for this arm
COLLECT_LOGS=false
CONTINUE_SESSION=false  # With --collect-logs: reuse most recent session dir (instead of today's)
SESSION_NAME=""     # Session name for collected logs; auto-generated if empty
DATE_FILTER=""      # Raw --date value; resolved to DATE_TOKENS array after arg parsing
DO_RESTART=false    # Restart services after sync
DO_TEST_MQTT=false  # Test MQTT connectivity between vehicle and arms
DO_VERIFY_FLEET=false  # Verify dashboard/agent versions across fleet
DO_TIME_SYNC=true   # Sync RPi clock from dev machine (disable with --no-time-sync)
TIME_SYNC_ONLY=false  # Set when --time-sync is passed as standalone action
EXPLICIT_VERIFY=false  # Track whether user explicitly passed --verify (vs default)
USE_CHECKSUM=false  # Use --checksum for rsync (slower but byte-accurate, off by default)
SEQUENTIAL=false    # Multi-IP: run targets in parallel by default; --sequential to serialize

print_usage() {
    cat << EOF
${BOLD}Pragati ROS2 - Unified Sync Script${NC}

${CYAN}Usage:${NC}
  $0 --ip <IP> [OPTIONS]

${CYAN}Required (first time):${NC}
  --ip <IP>         Single Raspberry Pi IP address
  --ips <IP,IP>     Multiple RPi IPs (comma-separated) for multi-ARM deploy
  --all-targets     Deploy to vehicle + all configured arms (reads config.env)
  --profile <NAME>  Use configuration profile from config.env (e.g., rpi1, rpi2, vehicle1)
  --all-profiles    Deploy to all configured profiles
  --target <NAME>   Legacy: Use named target from ~/.pragati_sync.conf (deprecated)
  --all-arms        Legacy: Deploy to all configured ARM targets (deprecated)
  --user <USER>     Username on RPi (default: ubuntu)

${CYAN}Sync Modes:${NC}
  (default)      Sync source, scripts, config, launch files
  --all          Sync everything including data and models
  --source       Sync only src/ directory
  --scripts      Sync only scripts/
  --quick        Quick sync - scripts only, no --delete flag

${CYAN}Build Options:${NC}
  --build        Sync source and trigger NATIVE build on target
  --deploy-cross Deploy pre-cross-compiled ARM binaries from install_rpi/ (for RPi)
  --deploy-local Deploy locally-built x86 binaries from install/ (Ubuntu-to-Ubuntu)

${CYAN}Other Options:${NC}
  --dry-run      Show what would be synced without doing it
  --verbose      Show detailed smart_rsync output
  --save         Save IP/user to ~/.pragati_sync.conf for future use
  --provision    Apply OS-level fixes and enable/start systemd services on target RPi(s)
  --verify       Check fix and service status on target RPi(s) (read-only, on by default)
  --no-verify    Skip automatic post-sync verification
  --no-time-sync Skip automatic RPi clock synchronization from dev machine
  --role <ROLE>  Override role auto-detection (vehicle|arm) for provisioning
  --arm-id <ID>  Set arm identity on target RPi (e.g. arm1, arm2). Writes
                 /etc/default/pragati-arm during --provision. Required for multi-arm.
                 Also derives ROS_DOMAIN_ID from arm number (arm1->1, arm2->2).
  --mqtt-address <ADDR>  Override MQTT broker address written to /etc/default/pragati-arm
  --restart      Restart launch service + dashboard + agent + field-monitor after sync
  --time-sync    Sync RPi clock from dev machine (standalone action, no file sync)
  --no-time-sync Skip automatic RPi clock synchronization from dev machine
  --test-mqtt    Test MQTT connectivity from vehicle to all configured arms
  --verify-fleet Check dashboard and agent versions across all configured targets
  --checksum     Use checksum-based rsync (slower but byte-accurate transfer detection)
  --sequential   Multi-IP: run targets one at a time (default: parallel)
  --parallel     Multi-IP: run targets concurrently (default)
  --help         Show this help

  # Standalone actions (no file sync)
  $0 --ip <IP> --time-sync            # Sync RPi clock only
  $0 --ip <IP> --verify               # Check fix/service status (read-only)
  $0 --ip <IP> --restart              # Restart services only

${CYAN}Log Collection:${NC}
  --collect-logs               Pull ~/field_trial_logs/latest/ from all configured hosts
                               (VEHICLE_IP, ARM_1_IP … ARM_6_IP from config.env) into
                               ./collected_logs/<session>/
  --session-name <NAME>        Session directory name (default: date +%Y-%m-%d)
  --date <DATE>                Filter all log sources by date. Defaults to today
                               when not specified. Supported values:
                                  all             All logs (no date filter)
                                  today           Current calendar date
                                  yesterday       Previous calendar date
                                  last-week       Last 7 days (today through 6 days ago)
                                  YYYY-MM-DD      Explicit date (e.g. 2026-02-20)
  --continue                   Reuse most recent session directory (instead of today's date)
  --dry-run                    With --collect-logs: print rsync commands, don't run them

${CYAN}Examples:${NC}
  # Using profiles (recommended - configure with: ./scripts/config_manager.sh)
  $0                           # Use default profile from config.env
  $0 --profile rpi1            # Deploy to rpi1 profile
  $0 --profile vehicle1 --build # Deploy to vehicle1 and build
  $0 --all-profiles --build    # Deploy to all configured profiles

  # Manual IP (saves to config if --save used)
  $0 --ip 192.168.137.253 --save

  # After config saved:
  $0                           # Standard sync
  $0 --build                   # Sync + native build on RPi
  $0 --deploy-cross            # Deploy cross-compiled binaries
  $0 --all --build             # Full sync with build
  $0 --dry-run                 # Preview changes

  # Multi-ARM deployment
  $0 --ips 192.168.137.253,192.168.137.254 --build
  $0 --all-targets --deploy-cross            # Deploy to vehicle + all arms
  $0 --all-targets --provision               # Provision all RPis
  $0 --all-targets --deploy-cross --parallel # Parallel deploy to all

  # Provisioning & verification
  $0 --provision                 # Sync + apply OS fixes + install/enable services
  $0 --all-profiles --provision  # Provision all configured RPis
  $0 --provision --role vehicle  # Override role auto-detection
  $0 --provision --arm-id arm2   # Provision and set identity to arm2
  $0 --provision --arm-id arm2 --mqtt-address 192.168.1.100  # Custom MQTT address
  $0 --verify                   # Check fix/service status (read-only)
  $0 --no-verify                # Skip automatic post-sync verification

  # Log collection after a field trial
  $0 --collect-logs                          # Pull today's logs from all hosts (default)
  $0 --collect-logs --date all               # Pull ALL logs (no date filter)
  $0 --collect-logs --session-name trial-01  # Use a specific session name
  $0 --collect-logs --dry-run                # Preview rsync commands
  $0 --collect-logs --date today             # Collect only today's logs (explicit)
  $0 --collect-logs --date yesterday         # Collect only yesterday's logs
  $0 --collect-logs --date last-week         # Collect logs from the last 7 days
  $0 --collect-logs --date 2026-02-19        # Collect logs from a specific date
  $0 --collect-logs --continue                # Resume: reuse latest session dir

${CYAN}MQTT Connectivity Test:${NC}
  $0 --test-mqtt                             # Test vehicle -> arm MQTT connectivity

${CYAN}Fleet Dashboard Verification:${NC}
  $0 --verify-fleet                          # Check dashboard/agent versions on all targets

${CYAN}Build Strategies:${NC}
  1. Native build on RPi (recommended for development):
     $0 --build
     - Syncs source code to RPi
     - Builds natively on RPi using colcon
     - Slower but simpler, no cross-compile setup needed

  2. Cross-compile + deploy (faster for production):
     ./build.sh rpi            # Cross-compile on local PC
     $0 --deploy-cross         # Deploy binaries to RPi
     - Faster builds (uses local PC power)
     - Requires cross-compilation toolchain setup

${CYAN}Current Config:${NC}
  RPI_IP   = ${RPI_IP:-<not set>}
  RPI_USER = ${RPI_USER}
  ALL_ARMS = ${ALL_ARMS:-<not set>}
  Config   = ${CONFIG_FILE}

${CYAN}Saved Targets:${NC}
EOF
    # Show saved targets from config
    if [ -f "$CONFIG_FILE" ]; then
        grep -E "^[A-Z0-9]+_IP=" "$CONFIG_FILE" 2>/dev/null | while read line; do
            name=$(echo "$line" | cut -d'_' -f1 | tr '[:upper:]' '[:lower:]')
            ip=$(echo "$line" | cut -d'=' -f2)
            echo "  $name -> $ip"
        done
    fi
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --all)          MODE="all"; shift ;;
        --source)       MODE="source"; shift ;;
        --scripts)      MODE="scripts"; shift ;;
        --quick)        MODE="quick"; shift ;;
        --build)        TRIGGER_BUILD=true; shift ;;
        --deploy-cross) DEPLOY_CROSS=true; shift ;;
        --deploy-local) DEPLOY_LOCAL=true; shift ;;
        --dry-run)      DRY_RUN=true; shift ;;
        --verbose)      VERBOSE=true; shift ;;
        --save)         SAVE_CONFIG=true; shift ;;
        --ip)           RPI_IP="$2"; shift 2 ;;
        --ips)          IFS=',' read -ra RPI_IPS <<< "$2"; shift 2 ;;
        --profile)      PROFILE_NAME="$2"; shift 2 ;;
        --all-profiles) USE_ALL_PROFILES=true; shift ;;
        --provision)    DO_PROVISION=true; shift ;;
        --verify)       DO_VERIFY=true; EXPLICIT_VERIFY=true; shift ;;
        --no-verify)    DO_VERIFY=false; shift ;;
        --no-time-sync) DO_TIME_SYNC=false; shift ;;
        --role)         RPI_ROLE="$2"; shift 2 ;;
        --arm-id)       ARM_ID="$2"; shift 2 ;;
        --mqtt-address) MQTT_ADDRESS_OVERRIDE="$2"; shift 2 ;;
        --target)       TARGET_NAME="$2"; shift 2 ;;
        --all-arms)     USE_ALL_ARMS=true; shift ;;
        --all-targets)  USE_ALL_TARGETS=true; shift ;;
        --save-target)  SAVE_TARGET_NAME="$2"; shift 2 ;;
        --user)         RPI_USER="$2"; shift 2 ;;
        --collect-logs) COLLECT_LOGS=true; shift ;;
        --continue)     CONTINUE_SESSION=true; shift ;;
        --session-name) SESSION_NAME="$2"; shift 2 ;;
        --date)         DATE_FILTER="$2"; shift 2 ;;
        --restart)      DO_RESTART=true; shift ;;
        --test-mqtt)    DO_TEST_MQTT=true; shift ;;
        --verify-fleet) DO_VERIFY_FLEET=true; shift ;;
        --time-sync)   DO_TIME_SYNC=true; TIME_SYNC_ONLY=true; shift ;;
        --checksum)     USE_CHECKSUM=true; shift ;;
        --sequential)   SEQUENTIAL=true; shift ;;
        --parallel)     SEQUENTIAL=false; shift ;;
        --help|-h)      print_usage; exit 0 ;;
        *)              echo -e "${RED}Unknown option: $1${NC}"; print_usage; exit 1 ;;
    esac
done

# ============================================================================
# Detect action-only mode
# ============================================================================
# When user only requests actions (--restart, --provision, --verify, --time-sync)
# without any sync mode (--all, --source, --scripts, --quick), build (--build), or
# deploy (--deploy-cross, --deploy-local), skip the file sync entirely.
# Note: --verify defaults to true, so we only count it if explicitly passed.
# Note: --time-sync defaults to true for sync operations, but TIME_SYNC_ONLY
# is set when --time-sync is passed explicitly as a standalone action.
ACTION_ONLY=false
if [ "$MODE" = "default" ] && \
   [ "$TRIGGER_BUILD" = false ] && \
   [ "$DEPLOY_CROSS" = false ] && \
   [ "$DEPLOY_LOCAL" = false ] && \
   [ "$COLLECT_LOGS" = false ] && \
    [ "$DO_TEST_MQTT" = false ] && \
    [ "$DO_VERIFY_FLEET" = false ]; then
    # Check if any action flag was explicitly requested
    if [ "$DO_RESTART" = true ] || [ "$DO_PROVISION" = true ] || [ "$EXPLICIT_VERIFY" = true ] || [ "$TIME_SYNC_ONLY" = true ]; then
        ACTION_ONLY=true
    fi
fi

# Handle --save-target: Save current IP/user as a named target
if [ -n "${SAVE_TARGET_NAME:-}" ]; then
    if [ -z "$RPI_IP" ]; then
        echo -e "${RED}Error: --save-target requires --ip${NC}"
        exit 1
    fi

    TARGET_UPPER=$(echo "$SAVE_TARGET_NAME" | tr '[:lower:]' '[:upper:]')

    # Remove old entries for this target if they exist
    if [ -f "$CONFIG_FILE" ]; then
        grep -v "^${TARGET_UPPER}_" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" 2>/dev/null || true
        mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
    fi

    # Add new entries
    echo "${TARGET_UPPER}_IP=${RPI_IP}" >> "$CONFIG_FILE"
    echo "${TARGET_UPPER}_USER=${RPI_USER}" >> "$CONFIG_FILE"

    # Update ALL_ARMS list if not already present
    if [ -f "$CONFIG_FILE" ]; then
        CURRENT_ALL_ARMS=$(grep "^ALL_ARMS=" "$CONFIG_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"')
        if [ -z "$CURRENT_ALL_ARMS" ]; then
            echo "ALL_ARMS=\"${SAVE_TARGET_NAME}\"" >> "$CONFIG_FILE"
        elif [[ ! ",$CURRENT_ALL_ARMS," == *",${SAVE_TARGET_NAME},"* ]]; then
            # Remove old ALL_ARMS line and add updated one
            grep -v "^ALL_ARMS=" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp"
            mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
            echo "ALL_ARMS=\"${CURRENT_ALL_ARMS},${SAVE_TARGET_NAME}\"" >> "$CONFIG_FILE"
        fi
    fi

    echo -e "${GREEN}✓ Saved target '${SAVE_TARGET_NAME}' -> ${RPI_USER}@${RPI_IP}${NC}"
    echo -e "${GRAY}  Use: $0 --target ${SAVE_TARGET_NAME}${NC}"
fi

# Handle --target: Load named target from config
if [ -n "${TARGET_NAME:-}" ]; then
    TARGET_UPPER=$(echo "$TARGET_NAME" | tr '[:lower:]' '[:upper:]')

    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}Error: Config file not found: $CONFIG_FILE${NC}"
        exit 1
    fi

    TARGET_IP=$(grep "^${TARGET_UPPER}_IP=" "$CONFIG_FILE" 2>/dev/null | cut -d'=' -f2)
    TARGET_USER=$(grep "^${TARGET_UPPER}_USER=" "$CONFIG_FILE" 2>/dev/null | cut -d'=' -f2)

    if [ -z "$TARGET_IP" ]; then
        echo -e "${RED}Error: Target '${TARGET_NAME}' not found in config${NC}"
        echo "Available targets:"
        grep -E "^[A-Z0-9]+_IP=" "$CONFIG_FILE" 2>/dev/null | while read line; do
            name=$(echo "$line" | cut -d'_' -f1 | tr '[:upper:]' '[:lower:]')
            ip=$(echo "$line" | cut -d'=' -f2)
            echo "  $name -> $ip"
        done
        exit 1
    fi

    RPI_IP="$TARGET_IP"
    [ -n "$TARGET_USER" ] && RPI_USER="$TARGET_USER"
    echo -e "${CYAN}ℹ${NC}  Using target '${TARGET_NAME}': ${RPI_USER}@${RPI_IP}"
fi

# Handle --all-arms: Deploy to all configured ARM targets
if [ "${USE_ALL_ARMS:-false}" = true ]; then
    if [ -z "$ALL_ARMS" ]; then
        echo -e "${RED}Error: No ARM targets configured${NC}"
        echo "Save targets first:"
        echo "  $0 --ip 192.168.137.253 --save-target arm1"
        echo "  $0 --ip 192.168.137.254 --save-target arm2"
        exit 1
    fi

    # Convert ALL_ARMS to IPs array (prefer config.env variables, fall back to old config)
    IFS=',' read -ra ARM_NAMES <<< "$ALL_ARMS"
    for arm_name in "${ARM_NAMES[@]}"; do
        ARM_UPPER=$(echo "$arm_name" | tr '[:lower:]' '[:upper:]')
        # Try shell variable from sourced config.env first (e.g. ARM1_IP, ARM_1_IP)
        local_var="${ARM_UPPER}_IP"
        ARM_IP_VAL="${!local_var:-}"
        if [ -z "$ARM_IP_VAL" ]; then
            # Try with underscore-separated form (e.g. ARM_1_IP for arm_1)
            local_var2=$(echo "${ARM_UPPER}_IP" | sed 's/\([A-Z]\)\([0-9]\)/\1_\2/')
            ARM_IP_VAL="${!local_var2:-}"
        fi
        if [ -n "$ARM_IP_VAL" ]; then
            RPI_IPS+=("$ARM_IP_VAL")
        fi
    done

    if [ ${#RPI_IPS[@]} -eq 0 ]; then
        echo -e "${RED}Error: No valid ARM IPs found in config${NC}"
        exit 1
    fi

    echo -e "${CYAN}ℹ${NC}  Using all configured ARMs: ${RPI_IPS[*]}"
fi

# Handle --all-targets: Deploy to vehicle + all configured ARM targets
if [ "${USE_ALL_TARGETS:-false}" = true ]; then
    # Add vehicle IP first
    _vehicle_ip="${VEHICLE_IP:-${VEHICLE1_IP:-}}"
    if [ -n "$_vehicle_ip" ]; then
        RPI_IPS+=("$_vehicle_ip")
    else
        echo -e "${YELLOW}⚠${NC}  No VEHICLE_IP set in config.env — skipping vehicle"
    fi

    # Add all arm IPs
    if [ -n "$ALL_ARMS" ]; then
        IFS=',' read -ra ARM_NAMES <<< "$ALL_ARMS"
        for arm_name in "${ARM_NAMES[@]}"; do
            ARM_UPPER=$(echo "$arm_name" | tr '[:lower:]' '[:upper:]')
            local_var="${ARM_UPPER}_IP"
            ARM_IP_VAL="${!local_var:-}"
            if [ -z "$ARM_IP_VAL" ]; then
                local_var2=$(echo "${ARM_UPPER}_IP" | sed 's/\([A-Z]\)\([0-9]\)/\1_\2/')
                ARM_IP_VAL="${!local_var2:-}"
            fi
            if [ -n "$ARM_IP_VAL" ]; then
                RPI_IPS+=("$ARM_IP_VAL")
            fi
        done
    fi

    if [ ${#RPI_IPS[@]} -eq 0 ]; then
        echo -e "${RED}Error: No valid IPs found in config.env (VEHICLE_IP, ARM_*_IP)${NC}"
        exit 1
    fi

    echo -e "${CYAN}ℹ${NC}  Using all targets (vehicle + arms): ${RPI_IPS[*]}"
fi

# Handle --profile: Load named profile from config.env
if [ -n "${PROFILE_NAME:-}" ]; then
    if [ ! -f "$WORKSPACE/config.env" ]; then
        echo -e "${RED}Error: Config file not found: $WORKSPACE/config.env${NC}"
        echo -e "${YELLOW}Run: ./scripts/config_manager.sh to create configuration${NC}"
        exit 1
    fi

    load_profile "$PROFILE_NAME"

    if [ -z "$RPI_IP" ]; then
        echo -e "${RED}Error: Profile '${PROFILE_NAME}' not found or has no IP address${NC}"
        echo ""
        echo "Available profiles:"
        if [ -n "$ALL_PROFILES" ]; then
            IFS=',' read -ra PROFILES <<< "$ALL_PROFILES"
            for p in "${PROFILES[@]}"; do
                p=$(echo "$p" | xargs)  # Trim whitespace
                p_upper=$(echo "$p" | tr '[:lower:]' '[:upper:]')
                p_ip="${p_upper}_IP"
                echo "  $p -> ${!p_ip:-<not set>}"
            done
        else
            echo "  (none configured)"
        fi
        exit 1
    fi

    echo -e "${CYAN}ℹ${NC}  Using profile '${PROFILE_NAME}': ${RPI_USER}@${RPI_IP}"
fi

# Handle --all-profiles: Deploy to all configured profiles
if [ "${USE_ALL_PROFILES:-false}" = true ]; then
    if [ -z "$ALL_PROFILES" ]; then
        echo -e "${RED}Error: No profiles configured${NC}"
        echo -e "${YELLOW}Run: ./scripts/config_manager.sh to create profiles${NC}"
        exit 1
    fi

    # Convert ALL_PROFILES to IPs array
    IFS=',' read -ra PROFILE_NAMES <<< "$ALL_PROFILES"
    for profile_name in "${PROFILE_NAMES[@]}"; do
        profile_name=$(echo "$profile_name" | xargs)  # Trim whitespace
        PROFILE_UPPER=$(echo "$profile_name" | tr '[:lower:]' '[:upper:]')
        PROFILE_IP_VAR="${PROFILE_UPPER}_IP"
        PROFILE_IP="${!PROFILE_IP_VAR}"

        if [ -n "$PROFILE_IP" ]; then
            RPI_IPS+=("$PROFILE_IP")
        fi
    done

    if [ ${#RPI_IPS[@]} -eq 0 ]; then
        echo -e "${RED}Error: No valid profile IPs found${NC}"
        exit 1
    fi

    echo -e "${CYAN}ℹ${NC}  Using all configured profiles: ${#RPI_IPS[@]} targets"
fi

# --collect-logs has its own multi-host logic (reads config.env directly).
# Skip multi-IP dispatch for collect-logs to avoid redundant sub-invocations.
if [ "$COLLECT_LOGS" = true ] && [ ${#RPI_IPS[@]} -gt 0 ]; then
    echo -e "${CYAN}ℹ${NC}  --collect-logs handles multi-host collection internally — skipping multi-IP dispatch"
    RPI_IPS=()
fi

# --verify-fleet has its own multi-host logic (reads config.env directly).
if [ "$DO_VERIFY_FLEET" = true ] && [ ${#RPI_IPS[@]} -gt 0 ]; then
    echo -e "${CYAN}ℹ${NC}  --verify-fleet handles multi-host queries internally — skipping multi-IP dispatch"
    RPI_IPS=()
fi

# If --ips provided, use that; otherwise use single --ip
if [ ${#RPI_IPS[@]} -gt 0 ]; then
    # Multi-target mode
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Multi-ARM Deployment Mode${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    if [ "$SEQUENTIAL" = true ]; then
        echo -e "Deploying to ${#RPI_IPS[@]} targets (sequential): ${RPI_IPS[*]}"
    else
        echo -e "Deploying to ${#RPI_IPS[@]} targets (parallel): ${RPI_IPS[*]}"
    fi
    echo ""

    FAILED_TARGETS=()
    SUCCESS_TARGETS=()

    # --- helper: build sub-invocation command for a given IP -------------------
    _build_sub_cmd() {
        local ip="$1"
        # Derive per-IP arm-id from config.env (ARM_<N>_IP / RPI<N>_IP mapping)
        local derived_arm_id=""
        if [ -n "$ARM_ID" ]; then
            if [ ${#RPI_IPS[@]} -eq 1 ]; then
                derived_arm_id="$ARM_ID"
            fi
        fi
        if [ -z "$derived_arm_id" ]; then
            local _i
            for _i in 1 2 3 4 5 6; do
                local _arm_var="ARM_${_i}_IP"
                local _rpi_var="RPI${_i}_IP"
                local _effective="${!_arm_var:-${!_rpi_var:-}}"
                if [ "$_effective" = "$ip" ]; then
                    derived_arm_id="arm${_i}"
                    break
                fi
            done
        fi

        # Build command with all original args except --ips/--all-arms/--all-profiles
        local cmd="$0 --ip $ip"
        [ "$MODE" != "default" ] && cmd="$cmd --$MODE"
        [ "$TRIGGER_BUILD" = true ] && cmd="$cmd --build"
        [ "$DEPLOY_CROSS" = true ] && cmd="$cmd --deploy-cross"
        [ "$DEPLOY_LOCAL" = true ] && cmd="$cmd --deploy-local"
        [ "$DRY_RUN" = true ] && cmd="$cmd --dry-run"
        [ "$VERBOSE" = true ] && cmd="$cmd --verbose"
        [ "$DO_PROVISION" = true ] && cmd="$cmd --provision"
        [ "$DO_VERIFY" = false ] && cmd="$cmd --no-verify"
        [ -n "$RPI_ROLE" ] && cmd="$cmd --role $RPI_ROLE"
        [ -n "$derived_arm_id" ] && cmd="$cmd --arm-id $derived_arm_id"
        [ -n "$MQTT_ADDRESS_OVERRIDE" ] && cmd="$cmd --mqtt-address $MQTT_ADDRESS_OVERRIDE"
        [ "$DO_RESTART" = true ] && cmd="$cmd --restart"
        [ "$COLLECT_LOGS" = true ] && cmd="$cmd --collect-logs"
        [ -n "$DATE_FILTER" ] && cmd="$cmd --date $DATE_FILTER"
        [ -n "$SESSION_NAME" ] && cmd="$cmd --session-name $SESSION_NAME"
        [ "$DO_TEST_MQTT" = true ] && cmd="$cmd --test-mqtt"
        [ "$CONTINUE_SESSION" = true ] && cmd="$cmd --continue"
        echo "$cmd"
    }

    if [ "$SEQUENTIAL" = true ]; then
        # ---------- sequential (legacy) path -----------------------------------
        for ip in "${RPI_IPS[@]}"; do
            echo -e "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${BOLD}${CYAN}  Syncing to: ${ip}${NC}"
            echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            CMD=$(_build_sub_cmd "$ip")
            if $CMD; then
                SUCCESS_TARGETS+=("$ip")
            else
                FAILED_TARGETS+=("$ip")
            fi
        done
    else
        # ---------- parallel path -------------------------------------------------
        # Launch sub-invocations as background jobs; capture output per target
        # so logs don't interleave. Print results sequentially when done.
        _multi_tmp=$(mktemp -d)
        declare -A _pids  # pid -> ip
        declare -A _logs  # ip -> logfile

        for ip in "${RPI_IPS[@]}"; do
            local_log="${_multi_tmp}/${ip}.log"
            CMD=$(_build_sub_cmd "$ip")
            # Run in background, redirect stdout+stderr to per-target log
            $CMD > "$local_log" 2>&1 &
            _pids[$!]="$ip"
            _logs[$ip]="$local_log"
        done

        echo -e "${CYAN}ℹ${NC}  Launched ${#_pids[@]} parallel jobs, waiting..."
        echo ""

        # Wait for all and collect exit codes
        # NOTE: `wait` returns the job's exit code; under set -e that would
        # abort the script on the first non-zero return.  Capture the code
        # explicitly so we always print output and summary afterward.
        declare -A _exit_codes
        _rc=0
        _done=0
        _total=${#_pids[@]}
        for pid in "${!_pids[@]}"; do
            _rc=0
            wait "$pid" || _rc=$?
            _exit_codes[$pid]=$_rc
            _done=$((_done + 1))
            _ip_label="${_pids[$pid]}"
            if [ "$_rc" -eq 0 ]; then
                echo -e "  ${GREEN}✓${NC} ${_ip_label} completed (${_done}/${_total})"
            else
                echo -e "  ${RED}✗${NC} ${_ip_label} failed [exit ${_rc}] (${_done}/${_total})"
            fi
        done
        echo ""

        # Print full output per target in deterministic order
        for ip in "${RPI_IPS[@]}"; do
            echo -e "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${BOLD}${CYAN}  Output: ${ip}${NC}"
            echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            cat "${_logs[$ip]}"
        done

        # Classify success/failure
        for pid in "${!_pids[@]}"; do
            ip="${_pids[$pid]}"
            if [ "${_exit_codes[$pid]}" -eq 0 ]; then
                SUCCESS_TARGETS+=("$ip")
            else
                FAILED_TARGETS+=("$ip")
            fi
        done

        rm -rf "$_multi_tmp"
    fi

    # Summary
    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Multi-ARM Deployment Summary${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [ ${#SUCCESS_TARGETS[@]} -gt 0 ]; then
        echo -e "${GREEN}✓ Successful:${NC} ${SUCCESS_TARGETS[*]}"
    fi
    if [ ${#FAILED_TARGETS[@]} -gt 0 ]; then
        echo -e "${RED}✗ Failed:${NC} ${FAILED_TARGETS[*]}"
        exit 1
    fi

    exit 0
fi

# ============================================================================
# Helper Functions (must be before --collect-logs which uses them)
# ============================================================================

log_info()    { echo -e "${CYAN}ℹ${NC}  $1"; }
log_success() { echo -e "${GREEN}✓${NC}  $1"; }
log_warn()    { echo -e "${YELLOW}⚠${NC}  $1"; }
log_error()   { echo -e "${RED}✗${NC}  $1"; }
log_step()    { echo -e "\n${BOLD}${CYAN}▶ $1${NC}"; }

# ============================================================================
# WSL Detection and SSH Bridge (must be before --collect-logs which uses them)
# ============================================================================

# Detect if running in WSL
is_wsl() {
    if [ -f /proc/version ] && grep -qi microsoft /proc/version; then
        return 0
    fi
    return 1
}

# Check if target IP is on Windows hotspot subnet (192.168.137.x)
is_windows_hotspot_ip() {
    local ip="$1"
    if [[ "$ip" =~ ^192\.168\.137\. ]]; then
        return 0
    fi
    return 1
}

# Get Windows SSH path if available
get_windows_ssh() {
    local win_ssh="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"
    if [ -f "$win_ssh" ]; then
        echo "$win_ssh"
        return 0
    fi
    # Try alternate path
    win_ssh="/mnt/c/Windows/System32/OpenSSH/ssh.exe"
    if [ -f "$win_ssh" ]; then
        echo "$win_ssh"
        return 0
    fi
    return 1
}

# Smart SSH wrapper - uses Windows SSH when needed on WSL
smart_ssh() {
    # Add SSH key if configured
    local ssh_opts=()
    if [ -n "$RPI_SSH_KEY" ]; then
        ssh_opts+=("-i" "$RPI_SSH_KEY")
    fi

    if is_wsl && is_windows_hotspot_ip "$RPI_IP"; then
        local win_ssh
        if win_ssh=$(get_windows_ssh); then
            if [ "${VERBOSE:-false}" = true ]; then
                log_info "Using Windows SSH bridge for WSL → Windows hotspot connectivity"
            fi
            "$win_ssh" "${ssh_opts[@]}" "$@"
            return $?
        else
            log_warn "WSL + Windows hotspot detected but Windows SSH not found"
            log_warn "Falling back to native SSH (may fail)"
        fi
    fi
    # Default: use native SSH
    ssh "${ssh_opts[@]}" "$@"
}

# Smart rsync wrapper - uses Windows SSH when needed on WSL
smart_rsync() {
    # Build SSH command with optional key
    local ssh_cmd="ssh"
    if [ -n "$RPI_SSH_KEY" ]; then
        ssh_cmd="ssh -i $RPI_SSH_KEY"
    fi

    # Inject --checksum when USE_CHECKSUM is enabled
    local extra_args=()
    [ "$USE_CHECKSUM" = true ] && extra_args+=(--checksum)

    if is_wsl && is_windows_hotspot_ip "$RPI_IP"; then
        local win_ssh
        if win_ssh=$(get_windows_ssh); then
            # rsync needs ssh in -e option
            if [ -n "$RPI_SSH_KEY" ]; then
                rsync -e "$win_ssh -i $RPI_SSH_KEY" "${extra_args[@]}" "$@"
            else
                rsync -e "$win_ssh" "${extra_args[@]}" "$@"
            fi
            return $?
        fi
    fi
    # Default: use native rsync
    rsync -e "$ssh_cmd" "${extra_args[@]}" "$@"
}

# rsync_with_retry: Wraps smart_rsync with retry logic for transient failures.
# Retries up to 2 times (3 attempts total) on exit codes 2/12/23/30.
# Fails immediately on exit code 1 (syntax/permission) or other errors.
rsync_with_retry() {
    local max_attempts=3
    local attempt=1
    local rc=0
    while [ "$attempt" -le "$max_attempts" ]; do
        smart_rsync "$@"
        rc=$?
        if [ "$rc" -eq 0 ]; then
            return 0
        fi
        # Exit code 1 = syntax/usage/permission error — no point retrying
        if [ "$rc" -eq 1 ]; then
            return "$rc"
        fi
        # Only retry on transient rsync errors:
        #   2  = protocol incompatibility
        #  12  = stream data error (network glitch)
        #  23  = partial transfer (some files vanished)
        #  30  = timeout
        case "$rc" in
            2|12|23|30)
                if [ "$attempt" -lt "$max_attempts" ]; then
                    log_warn "rsync failed (attempt ${attempt}/${max_attempts}), retrying in 3s..."
                    sleep 3
                fi
                ;;
            *)
                # Non-retryable error
                return "$rc"
                ;;
        esac
        attempt=$((attempt + 1))
    done
    return "$rc"
}

# ============================================================================
# Date Token Resolution (for --collect-logs --date)
# ============================================================================
#
# Populates the DATE_TOKENS array from the raw DATE_FILTER value.
# Supported inputs: today, yesterday, last-week, YYYY-MM-DD
# Sets DATE_TOKENS_DISPLAY (human-friendly label for output).
# Exits with error if DATE_FILTER is set but invalid.

DATE_TOKENS=()
DATE_TOKENS_DISPLAY=""

resolve_date_tokens() {
    local raw="$1"
    DATE_TOKENS=()

    case "$raw" in
        all)
            # Special value: no date filtering (collect everything)
            DATE_TOKENS=()
            DATE_TOKENS_DISPLAY="all (no date filter)"
            ;;
        today)
            DATE_TOKENS=("$(date +%Y%m%d)")
            DATE_TOKENS_DISPLAY="today (${DATE_TOKENS[0]})"
            ;;
        yesterday)
            DATE_TOKENS=("$(date -d yesterday +%Y%m%d)")
            DATE_TOKENS_DISPLAY="yesterday (${DATE_TOKENS[0]})"
            ;;
        last-week)
            local tokens_str=""
            for offset in 0 1 2 3 4 5 6; do
                DATE_TOKENS+=("$(date -d "${offset} days ago" +%Y%m%d)")
                tokens_str="${tokens_str} ${DATE_TOKENS[$offset]}"
            done
            DATE_TOKENS_DISPLAY="last-week (${tokens_str# })"
            ;;
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
            # Validate the date is real (date --date will error on e.g. 2026-13-01)
            if ! date -d "$raw" +%Y%m%d >/dev/null 2>&1; then
                echo -e "${RED}Error: --date '${raw}' is not a valid calendar date.${NC}" >&2
                echo -e "  Valid formats: today, yesterday, last-week, YYYY-MM-DD" >&2
                exit 1
            fi
            DATE_TOKENS=("$(echo "$raw" | tr -d '-')")
            DATE_TOKENS_DISPLAY="${raw} (${DATE_TOKENS[0]})"
            ;;
        *)
            echo -e "${RED}Error: --date '${raw}' is not a recognised date value.${NC}" >&2
            echo -e "  Valid values:" >&2
            echo -e "    all           All logs (no date filter)" >&2
            echo -e "    today         Current calendar date" >&2
            echo -e "    yesterday     Previous calendar date" >&2
            echo -e "    last-week     Last 7 days" >&2
            echo -e "    YYYY-MM-DD    Explicit date (e.g. 2026-02-20)" >&2
            exit 1
            ;;
    esac
}

# Resolve --date immediately after arg parsing so any error exits before SSH
DATE_EXPLICIT=false
if [ -n "$DATE_FILTER" ]; then
    DATE_EXPLICIT=true
    resolve_date_tokens "$DATE_FILTER"
    # --date all means "no date filter" — clear DATE_FILTER so downstream
    # code follows the unfiltered (latest symlink) path.
    if [ "$DATE_FILTER" = "all" ]; then
        DATE_FILTER=""
    fi
fi

# Default collect-logs to today's date when --date is not explicitly specified.
# Use --date all to explicitly collect all logs without date filtering.
DATE_FILTER_DEFAULTED=false
if [ "$COLLECT_LOGS" = true ] && [ "$DATE_EXPLICIT" = false ]; then
    DATE_FILTER="today"
    DATE_FILTER_DEFAULTED=true
    resolve_date_tokens "$DATE_FILTER"
fi

# ============================================================================
# Handle --collect-logs: Pull field trial logs from all configured hosts
# ============================================================================

if [ "$COLLECT_LOGS" = true ]; then
    # --continue: reuse the most recent session directory (by mtime)
    if [ "$CONTINUE_SESSION" = true ] && [ -z "$SESSION_NAME" ]; then
        local_logs_dir="${WORKSPACE}/collected_logs"
        if [ -d "$local_logs_dir" ]; then
            # Find most recent session directory by modification time
            latest_session=$(ls -1td "${local_logs_dir}"/*/ 2>/dev/null | head -1)
            if [ -n "$latest_session" ]; then
                SESSION_NAME="$(basename "${latest_session%/}")"
                log_info "Continuing session: ${SESSION_NAME}"
            fi
        fi
        # Graceful fallback: no previous session exists — create a new one
        if [ -z "$SESSION_NAME" ]; then
            SESSION_NAME="$(date +%Y-%m-%d)"
            log_warn "No previous session found; creating new session: ${SESSION_NAME}"
        fi
    elif [ -z "$SESSION_NAME" ]; then
        # Auto-generate: per-day folder (re-running same day adds new files)
        SESSION_NAME="$(date +%Y-%m-%d)"
    fi

    SESSION_DIR="${WORKSPACE}/collected_logs/${SESSION_NAME}"

    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Log Collection Mode${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "  Session : ${SESSION_NAME}"
    echo -e "  Output  : ${SESSION_DIR}"
    echo -e "  Config  : ${CONFIG_FILE}"
    [ -n "$DATE_TOKENS_DISPLAY" ] && echo -e "  Date    : ${DATE_TOKENS_DISPLAY}"
    [ "$CONTINUE_SESSION" = true ] && echo -e "  ${CYAN}(continue — reusing most recent session dir)${NC}"
    [ "$DRY_RUN" = true ] && echo -e "  ${YELLOW}(dry-run — no files will be transferred)${NC}"
    if [ "$DATE_FILTER_DEFAULTED" = true ]; then
        echo ""
        log_info "Collecting today's logs (use --date all for all logs)"
    fi
    echo ""

    # Build SSH options
    SSH_KEY_OPT=""
    if [ -n "$RPI_SSH_KEY" ]; then
        SSH_KEY_OPT="-i $RPI_SSH_KEY"
    fi

    # Helper: rsync one remote directory into a local destination.
    # Shows per-file progress, reports file count, cleans up empty dirs.
    #   _collect_one <label> <host_ip> <remote_path> <local_dest>
    _collect_one() {
        local label="$1"
        local host_ip="$2"
        local remote_path="$3"
        local local_dest="$4"

        echo -e "  ${CYAN}[$label]${NC} ${RPI_USER}@${host_ip}:${remote_path}"

        # First check if the remote path exists at all
        # Note: remote_path may start with ~ which must expand on the remote
        # side, so we avoid quoting it inside the test command.
        local remote_exists=false
        if smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
                "${RPI_USER}@${host_ip}" "test -d ${remote_path} || test -L ${remote_path}" 2>/dev/null; then
            remote_exists=true
        fi

        if [ "$remote_exists" = false ]; then
            echo -e "    ${GRAY}-> remote dir does not exist, skipping${NC}"
            return 1
        fi

        mkdir -p "$local_dest"

        # Build rsync SSH command (use Windows SSH on WSL hotspot)
        local ssh_cmd="ssh ${SSH_KEY_OPT}"
        if is_wsl && is_windows_hotspot_ip "$host_ip"; then
            local win_ssh
            if win_ssh=$(get_windows_ssh); then
                if [ -n "$RPI_SSH_KEY" ]; then
                    ssh_cmd="$win_ssh -i $RPI_SSH_KEY"
                else
                    ssh_cmd="$win_ssh"
                fi
            fi
        fi

        # Run rsync — show itemized changes (files being transferred)
        # Always skip files that already exist locally (dedup across re-runs)
        local rsync_output
        rsync_output=$(rsync -avz --itemize-changes --ignore-existing -e "$ssh_cmd" \
            "${RPI_USER}@${host_ip}:${remote_path}/" "${local_dest}/" 2>&1) || {
            echo -e "    ${RED}rsync FAILED:${NC}"
            echo "$rsync_output" | sed 's/^/      /'
            # Clean up empty destination dir
            rmdir "$local_dest" 2>/dev/null || true
            return 1
        }

        # Count files transferred (lines starting with >f or <f in itemized output)
        local file_count
        file_count=$(echo "$rsync_output" | grep -c '^>f' || true)

        if [ "$file_count" -eq 0 ]; then
            # Check whether files exist locally already (--ignore-existing skipped them)
            local existing_count
            existing_count=$(find "$local_dest" -type f 2>/dev/null | wc -l)
            if [ "$existing_count" -gt 0 ]; then
                echo -e "    ${GRAY}-> 0 new files (${existing_count} already collected)${NC}"
            else
                echo -e "    ${GRAY}-> remote dir exists but is empty${NC}"
                rmdir "$local_dest" 2>/dev/null || true
            fi
            return 1
        fi

        # Show the files that were copied
        echo "$rsync_output" | grep '^>f' | awk '{print $2}' | while read -r f; do
            echo -e "    ${GREEN}+${NC} ${f}"
        done
        echo -e "    ${GREEN}-> ${file_count} file(s) collected to ${local_dest}${NC}"
        return 0
    }

    # Helper: extract cotton_detection_node image paths from locally-downloaded ros2 logs.
    # Writes deduplicated absolute paths to two temp files (one for inputs, one for outputs).
    #   _extract_image_paths <ros2_logs_dir> <input_paths_tmpfile> <output_paths_tmpfile>
    _extract_image_paths() {
        local ros2_logs_dir="$1"
        local input_tmp="$2"
        local output_tmp="$3"

        # Input images: lines like "💾 Saved input image: /absolute/path/to/img.jpg"
        grep -rF "Saved input image:" "${ros2_logs_dir}/" 2>/dev/null \
            | sed 's/.*Saved input image: //' \
            | sort -u > "$input_tmp" || true

        # Output images: lines like "💾 Saved output image: /path/img.jpg (3 detections)"
        grep -rF "Saved output image:" "${ros2_logs_dir}/" 2>/dev/null \
            | sed 's/.*Saved output image: //' \
            | sed 's/ ([0-9]* detections)$//' \
            | sort -u > "$output_tmp" || true
    }

    # Helper: resolve group_id and role for an IP from entities.yaml.
    # Outputs two lines: first is group_id, second is role (e.g. "vehicle" or "arm_1").
    # Falls back to empty strings if the IP is not found in entities.yaml.
    # Usage:
    #   mapfile -t _info < <(_resolve_entity_from_yaml "192.168.1.100")
    #   group="${_info[0]}"   # e.g. "machine-1"
    #   role="${_info[1]}"    # e.g. "vehicle" or "arm_1"
    ENTITIES_YAML="${WORKSPACE}/web_dashboard/config/entities.yaml"
    _resolve_entity_from_yaml() {
        local ip="$1"
        if [ ! -f "$ENTITIES_YAML" ]; then
            echo ""
            echo ""
            return
        fi
        python3 - "$ip" "$ENTITIES_YAML" <<'PYEOF'
import sys, re

ip_arg = sys.argv[1]
yaml_path = sys.argv[2]

# Minimal YAML list parser — no dependency on PyYAML
# Parses the flat entities list produced by _save_entities_yaml()
group_id = ""
role = ""

try:
    with open(yaml_path) as f:
        content = f.read()

    # Split into per-entity blocks on "- id:" boundaries
    blocks = re.split(r'\n- id:', content)
    for block in blocks[1:]:  # skip preamble before first entity
        block = "- id:" + block
        def _field(name, text):
            m = re.search(r'^\s+' + name + r':\s*(.+)$', text, re.MULTILINE)
            return m.group(1).strip() if m else ""

        if _field("ip", block) != ip_arg:
            continue

        group_id = _field("group_id", block)
        entity_type = _field("entity_type", block)
        slot = _field("slot", block)

        # Derive role from slot: "vehicle" -> "vehicle", "arm-2" -> "arm_2"
        if entity_type == "vehicle" or slot == "vehicle":
            role = "vehicle"
        elif slot.startswith("arm-"):
            role = "arm_" + slot.split("-", 1)[1]
        else:
            role = entity_type or "target"
        break
except Exception:
    pass

print(group_id)
print(role)
PYEOF
    }

    # Helper: rsync from one host into a group/role subdir
    # Per-host directory isolation: each host's logs are collected into a
    # group-and-role-named subdirectory under the session directory. For example:
    #   collected_logs/<session>/tabletop-lab/vehicle/  — tabletop-lab vehicle logs
    #   collected_logs/<session>/tabletop-lab/arm_1/    — tabletop-lab arm 1 logs
    #   collected_logs/<session>/machine-1/vehicle/     — machine-1 vehicle logs
    #   collected_logs/<session>/machine-1/arm_1/       — machine-1 arm 1 logs
    # When group is unknown (no entities.yaml entry), falls back to:
    #   collected_logs/<session>/<role>/
    # Within each role directory, log sources are further organised:
    #   <role>/field_trial_logs/   — field trial session data
    #   <role>/setup_logs/        — setup script logs
    #   <role>/provision_logs/    — provisioning logs
    #   <role>/ros2_logs/         — ROS2 runtime logs
    #   <role>/app_logs/          — application-level logs
    #   <role>/images/            — detection images referenced in logs
    # This isolation ensures logs from different hosts never intermingle,
    # even when multiple hosts share the same log directory structure.
    collect_from_host() {
        local role="$1"   # e.g. "vehicle" or "arm_1"
        local host_ip="$2"
        local group="$3"  # e.g. "machine-1" or "tabletop-lab" (optional)
        # Group/role subdirectory provides per-host isolation
        # With group: <session>/<group>/<role>/   e.g. machine-1/vehicle/
        # Without:    <session>/<role>/            e.g. vehicle/  (backwards compat)
        local dest
        if [ -n "$group" ]; then
            dest="${SESSION_DIR}/${group}/${role}"
        else
            dest="${SESSION_DIR}/${role}"
        fi

        if [ "$DRY_RUN" = true ]; then
            echo -e "  ${GRAY}[dry-run] Would collect from ${RPI_USER}@${host_ip}:${NC}"
            if [ -n "$DATE_FILTER" ]; then
                echo -e "    ${YELLOW}Date filter: ${DATE_TOKENS_DISPLAY}${NC}"
                for _token in "${DATE_TOKENS[@]}"; do
                    local _ros2_date="${_token:0:4}-${_token:4:2}-${_token:6:2}"
                    echo -e "    ${GRAY}~/field_trial_logs/session_${_token}_*/   -> ${dest}/field_trial_logs/<session_dir>/${NC}"
                    echo -e "    ${GRAY}~/.pragati_setup_logs/setup_${_token}_*.log -> ${dest}/setup_logs/${NC}"
                    echo -e "    ${GRAY}~/.pragati_provision_logs/provision_${_token}_*.log -> ${dest}/provision_logs/${NC}"
                    echo -e "    ${GRAY}~/.ros/log/${_ros2_date}-*/              -> ${dest}/ros2_logs/<run_dir>/${NC}"
                    echo -e "    ${GRAY}~/.ros/log/*/${_ros2_date}-*/           -> ${dest}/ros2_logs/<id>/<run_dir>/${NC}"
                    echo -e "    ${GRAY}~/pragati_ros2/logs/*_${_token}_*.log   -> ${dest}/app_logs/${NC}"
                done
            else
                echo -e "    ${GRAY}~/field_trial_logs/latest/  -> ${dest}/${NC}"
                echo -e "    ${GRAY}~/.pragati_setup_logs/     -> ${dest}/setup_logs/${NC}"
                echo -e "    ${GRAY}~/.pragati_provision_logs/ -> ${dest}/provision_logs/${NC}"
                echo -e "    ${GRAY}~/.ros/log/latest/         -> ${dest}/ros2_logs/${NC}"
                echo -e "    ${GRAY}~/.ros/log/*/latest/       -> ${dest}/ros2_logs/<id>/${NC}"
                echo -e "    ${GRAY}~/pragati_ros2/logs/       -> ${dest}/app_logs/${NC}"
            fi
            echo -e "    ${GRAY}~/pragati_ros2/data/inputs/ (paths from logs) -> ${dest}/images/inputs/${NC}"
            echo -e "    ${GRAY}~/pragati_ros2/data/outputs/ (paths from logs) -> ${dest}/images/outputs/${NC}"
            return 0
        fi

        echo ""
        echo -e "  ${BOLD}${CYAN}Collecting from ${role} (${host_ip}):${NC}"
        echo -e "  ${GRAY}────────────────────────────────────────${NC}"

        local sources_ok=0

        # 1. Field trial logs
        if [ -n "$DATE_FILTER" ]; then
            # Date-filtered: enumerate matching session directories via SSH
            local _ft_session_dirs=()
            for _token in "${DATE_TOKENS[@]}"; do
                # ls -d exits non-zero when no match; capture output gracefully
                local _ls_out
                _ls_out=$(smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
                    "${RPI_USER}@${host_ip}" \
                    "ls -d ~/field_trial_logs/session_${_token}_*/ 2>/dev/null" || true)
                while IFS= read -r _dir; do
                    [ -n "$_dir" ] && _ft_session_dirs+=("$_dir")
                done <<< "$_ls_out"
            done

            if [ "${#_ft_session_dirs[@]}" -eq 0 ]; then
                echo -e "    ${YELLOW}-> no field_trial_logs sessions found for ${DATE_TOKENS_DISPLAY}${NC}"
            else
                for _session_dir in "${_ft_session_dirs[@]}"; do
                    local _session_name
                    _session_name="$(basename "${_session_dir%/}")"
                    _collect_one "Field Trial Logs (${_session_name})" "$host_ip" \
                        "~/field_trial_logs/${_session_name}" \
                        "${dest}/field_trial_logs/${_session_name}" \
                        && sources_ok=$((sources_ok + 1))
                done
            fi
        else
            _collect_one "Field Trial Logs" "$host_ip" \
                "~/field_trial_logs/latest" "${dest}" && sources_ok=$((sources_ok + 1))

            # Staleness warning: if the most recent file under `latest` is
            # older than 24 hours, warn the operator that the logs may be stale.
            if [ "$DRY_RUN" = false ]; then
                local _latest_age_s
                _latest_age_s=$(smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
                    "${RPI_USER}@${host_ip}" \
                    'newest=$(find ~/field_trial_logs/latest/ -type f -printf "%T@\n" 2>/dev/null | sort -rn | head -1); if [ -n "$newest" ]; then echo $(( $(date +%s) - ${newest%.*} )); fi' \
                    2>/dev/null || true)
                _latest_age_s=$(echo "$_latest_age_s" | tr -d '[:space:]')
                if [ -n "$_latest_age_s" ] && [ "$_latest_age_s" -gt 86400 ] 2>/dev/null; then
                    local _stale_hours=$((_latest_age_s / 3600))
                    log_warn "latest/ symlink target's newest file is ${_stale_hours}h old — logs may be stale"
                fi
            fi
        fi

        # 2. Setup logs
        if [ -n "$DATE_FILTER" ]; then
            local _setup_ssh_cmd="ssh ${SSH_KEY_OPT}"
            if is_wsl && is_windows_hotspot_ip "$host_ip"; then
                local _setup_win_ssh
                if _setup_win_ssh=$(get_windows_ssh); then
                    _setup_ssh_cmd="${_setup_win_ssh}${RPI_SSH_KEY:+ -i $RPI_SSH_KEY}"
                fi
            fi
            local _setup_total=0
            mkdir -p "${dest}/setup_logs"
            for _token in "${DATE_TOKENS[@]}"; do
                local _setup_out
                _setup_out=$(rsync -avz --itemize-changes --ignore-existing \
                    --include="setup_${_token}_*.log" \
                    --include="*/" \
                    --exclude="*" \
                    -e "$_setup_ssh_cmd" \
                    "${RPI_USER}@${host_ip}:~/.pragati_setup_logs/" \
                    "${dest}/setup_logs/" 2>&1) || true
                local _setup_n
                _setup_n=$(echo "$_setup_out" | grep -c '^>f' || true)
                _setup_total=$((_setup_total + _setup_n))
                if [ "$_setup_n" -gt 0 ]; then
                    echo "$_setup_out" | grep '^>f' | awk '{print $2}' | while read -r f; do
                        echo -e "    ${GREEN}+${NC} ${f}"
                    done
                fi
            done
            if [ "$_setup_total" -eq 0 ]; then
                echo -e "    ${YELLOW}-> no setup logs found for ${DATE_TOKENS_DISPLAY}${NC}"
                rmdir "${dest}/setup_logs" 2>/dev/null || true
            else
                echo -e "    ${GREEN}-> ${_setup_total} setup log file(s) collected to ${dest}/setup_logs/${NC}"
                sources_ok=$((sources_ok + 1))
            fi
        else
            _collect_one "Setup Logs" "$host_ip" \
                "~/.pragati_setup_logs" "${dest}/setup_logs" && sources_ok=$((sources_ok + 1))
        fi

        # 3. Provision logs
        if [ -n "$DATE_FILTER" ]; then
            local _prov_ssh_cmd="ssh ${SSH_KEY_OPT}"
            if is_wsl && is_windows_hotspot_ip "$host_ip"; then
                local _prov_win_ssh
                if _prov_win_ssh=$(get_windows_ssh); then
                    _prov_ssh_cmd="${_prov_win_ssh}${RPI_SSH_KEY:+ -i $RPI_SSH_KEY}"
                fi
            fi
            local _prov_total=0
            mkdir -p "${dest}/provision_logs"
            for _token in "${DATE_TOKENS[@]}"; do
                local _prov_out
                _prov_out=$(rsync -avz --itemize-changes --ignore-existing \
                    --include="provision_${_token}_*.log" \
                    --include="*/" \
                    --exclude="*" \
                    -e "$_prov_ssh_cmd" \
                    "${RPI_USER}@${host_ip}:~/.pragati_provision_logs/" \
                    "${dest}/provision_logs/" 2>&1) || true
                local _prov_n
                _prov_n=$(echo "$_prov_out" | grep -c '^>f' || true)
                _prov_total=$((_prov_total + _prov_n))
                if [ "$_prov_n" -gt 0 ]; then
                    echo "$_prov_out" | grep '^>f' | awk '{print $2}' | while read -r f; do
                        echo -e "    ${GREEN}+${NC} ${f}"
                    done
                fi
            done
            if [ "$_prov_total" -eq 0 ]; then
                echo -e "    ${YELLOW}-> no provision logs found for ${DATE_TOKENS_DISPLAY}${NC}"
                rmdir "${dest}/provision_logs" 2>/dev/null || true
            else
                echo -e "    ${GREEN}-> ${_prov_total} provision log file(s) collected to ${dest}/provision_logs/${NC}"
                sources_ok=$((sources_ok + 1))
            fi
        else
            _collect_one "Provision Logs" "$host_ip" \
                "~/.pragati_provision_logs" "${dest}/provision_logs" && sources_ok=$((sources_ok + 1))
        fi

        # 4. ROS2 node logs (latest session)
        # Supports both flat (~/.ros/log/YYYY-...) and per-identity
        # (~/.ros/log/<arm_id>/YYYY-...) log directory layouts.
        if [ -n "$DATE_FILTER" ]; then
            # Date-filtered: enumerate matching run directories via SSH.
            # ROS2 Jazzy names dirs YYYY-MM-DD-HH-MM-SS-us-host-pid/, so reformat token.
            local _ros2_run_dirs=()
            for _token in "${DATE_TOKENS[@]}"; do
                # Convert YYYYMMDD → YYYY-MM-DD for the directory prefix
                local _ros2_date="${_token:0:4}-${_token:4:2}-${_token:6:2}"
                local _ls_ros2
                # Search both flat and per-identity subdirectory layouts
                _ls_ros2=$(smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
                    "${RPI_USER}@${host_ip}" \
                    "ls -d ~/.ros/log/${_ros2_date}-*/ ~/.ros/log/*/${_ros2_date}-*/ 2>/dev/null" || true)
                while IFS= read -r _dir; do
                    [ -n "$_dir" ] && _ros2_run_dirs+=("$_dir")
                done <<< "$_ls_ros2"
            done

            if [ "${#_ros2_run_dirs[@]}" -eq 0 ]; then
                echo -e "    ${YELLOW}-> no ROS2 log runs found for ${DATE_TOKENS_DISPLAY}${NC}"
            else
                for _run_dir in "${_ros2_run_dirs[@]}"; do
                    # Preserve identity prefix in destination (e.g. arm2/2026-02-23-...)
                    local _run_path="${_run_dir%/}"
                    local _run_name
                    _run_name="$(basename "$_run_path")"
                    local _parent_name
                    _parent_name="$(basename "$(dirname "$_run_path")")"
                    local _dest_subdir _src_path
                    if [ "$_parent_name" = "log" ]; then
                        # Flat layout: ~/.ros/log/YYYY-MM-DD-...
                        _dest_subdir="${_run_name}"
                        _src_path="~/.ros/log/${_run_name}"
                    else
                        # Per-identity layout: ~/.ros/log/<arm_id>/YYYY-MM-DD-...
                        _dest_subdir="${_parent_name}/${_run_name}"
                        _src_path="~/.ros/log/${_parent_name}/${_run_name}"
                    fi
                    _collect_one "ROS2 Node Logs (${_dest_subdir})" "$host_ip" \
                        "${_src_path}" \
                        "${dest}/ros2_logs/${_dest_subdir}" \
                        && sources_ok=$((sources_ok + 1))
                done
            fi
        else
            # No date filter: collect latest symlink.
            # Check per-identity layout first, fall back to flat.
            local _ros2_identity_dirs
            _ros2_identity_dirs=$(smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
                "${RPI_USER}@${host_ip}" \
                "ls -d ~/.ros/log/*/latest 2>/dev/null" || true)
            if [ -n "$_ros2_identity_dirs" ]; then
                while IFS= read -r _latest_dir; do
                    [ -n "$_latest_dir" ] || continue
                    local _id_name
                    _id_name="$(basename "$(dirname "$_latest_dir")")"
                    _collect_one "ROS2 Node Logs (${_id_name}/latest)" "$host_ip" \
                        "~/.ros/log/${_id_name}/latest" \
                        "${dest}/ros2_logs/${_id_name}" \
                        && sources_ok=$((sources_ok + 1))
                done <<< "$_ros2_identity_dirs"
            else
                _collect_one "ROS2 Node Logs" "$host_ip" \
                    "~/.ros/log/latest" "${dest}/ros2_logs" && sources_ok=$((sources_ok + 1))
            fi
        fi

        # 5. Application logs (arm_client, etc.)
        if [ -n "$DATE_FILTER" ]; then
            # Date-filtered: rsync only files matching *_YYYYMMDD_*.log per token
            local _app_ssh_cmd="ssh ${SSH_KEY_OPT}"
            if is_wsl && is_windows_hotspot_ip "$host_ip"; then
                local _app_win_ssh
                if _app_win_ssh=$(get_windows_ssh); then
                    _app_ssh_cmd="${_app_win_ssh}${RPI_SSH_KEY:+ -i $RPI_SSH_KEY}"
                fi
            fi
            local _app_total=0
            mkdir -p "${dest}/app_logs"
            for _token in "${DATE_TOKENS[@]}"; do
                local _app_out
                _app_out=$(rsync -avz --itemize-changes --ignore-existing \
                    --include="*_${_token}_*.json" \
                    --include="*_${_token}_*.log" \
                    --include="*/" \
                    --exclude="*" \
                    -e "$_app_ssh_cmd" \
                    "${RPI_USER}@${host_ip}:~/pragati_ros2/logs/" \
                    "${dest}/app_logs/" 2>&1) || true
                local _app_n
                _app_n=$(echo "$_app_out" | grep -c '^>f' || true)
                _app_total=$((_app_total + _app_n))
                if [ "$_app_n" -gt 0 ]; then
                    echo "$_app_out" | grep '^>f' | awk '{print $2}' | while read -r f; do
                        echo -e "    ${GREEN}+${NC} ${f}"
                    done
                fi
            done
            if [ "$_app_total" -eq 0 ]; then
                echo -e "    ${YELLOW}-> no app logs found for ${DATE_TOKENS_DISPLAY}${NC}"
                rmdir "${dest}/app_logs" 2>/dev/null || true
            else
                echo -e "    ${GREEN}-> ${_app_total} app log file(s) collected to ${dest}/app_logs/${NC}"
                sources_ok=$((sources_ok + 1))
            fi
        else
            _collect_one "App Logs" "$host_ip" \
                "~/pragati_ros2/logs" "${dest}/app_logs" && sources_ok=$((sources_ok + 1))
        fi

        # 6. Detection images referenced in cotton_detection_node ROS2 logs
        local _img_input_tmp _img_output_tmp
        _img_input_tmp="$(mktemp)"
        _img_output_tmp="$(mktemp)"

        echo -e "  ${CYAN}[Detection Images]${NC} parsing ros2_logs for image paths..."

        _extract_image_paths "${dest}/ros2_logs" "$_img_input_tmp" "$_img_output_tmp"

        local _img_input_count _img_output_count
        _img_input_count=$(wc -l < "$_img_input_tmp" | tr -d ' ')
        _img_output_count=$(wc -l < "$_img_output_tmp" | tr -d ' ')

        if [ "$_img_input_count" -eq 0 ] && [ "$_img_output_count" -eq 0 ]; then
            echo -e "    ${GRAY}-> no images referenced in logs${NC}"
            rm -f "$_img_input_tmp" "$_img_output_tmp"
        else
            # Build SSH command (same WSL/hotspot logic as _collect_one)
            local _img_ssh_cmd="ssh"
            if [ -n "$RPI_SSH_KEY" ]; then
                _img_ssh_cmd="ssh -i $RPI_SSH_KEY"
            fi
            if is_wsl && is_windows_hotspot_ip "$host_ip"; then
                local _win_ssh
                if _win_ssh=$(get_windows_ssh); then
                    if [ -n "$RPI_SSH_KEY" ]; then
                        _img_ssh_cmd="$_win_ssh -i $RPI_SSH_KEY"
                    else
                        _img_ssh_cmd="$_win_ssh"
                    fi
                fi
            fi

            local _img_sources_ok=0

            # Always skip images that already exist locally (dedup across re-runs)

            # Transfer input images
            if [ "$_img_input_count" -gt 0 ]; then
                mkdir -p "${dest}/images/inputs"
                # Strip leading / so paths are relative to / for rsync --files-from
                sed 's|^/||' "$_img_input_tmp" > "${_img_input_tmp}.rel"
                local _rsync_in_out
                _rsync_in_out=$(rsync -avz --no-relative --itemize-changes --ignore-existing \
                    --files-from="${_img_input_tmp}.rel" \
                    -e "$_img_ssh_cmd" \
                    "${RPI_USER}@${host_ip}:/" \
                    "${dest}/images/inputs/" 2>&1) || true
                rm -f "${_img_input_tmp}.rel"
                local _in_count
                _in_count=$(echo "$_rsync_in_out" | grep -c '^>f' || true)
                if [ "$_in_count" -gt 0 ]; then
                    echo "$_rsync_in_out" | grep '^>f' | awk '{print $2}' | while read -r f; do
                        echo -e "    ${GREEN}+${NC} ${f}"
                    done
                    echo -e "    ${GREEN}-> ${_in_count} input image(s) collected to ${dest}/images/inputs/${NC}"
                    _img_sources_ok=$((_img_sources_ok + 1))
                else
                    echo -e "    ${GRAY}-> input images listed in logs but none transferred${NC}"
                fi
            fi

            # Transfer output images
            if [ "$_img_output_count" -gt 0 ]; then
                mkdir -p "${dest}/images/outputs"
                sed 's|^/||' "$_img_output_tmp" > "${_img_output_tmp}.rel"
                local _rsync_out_out
                _rsync_out_out=$(rsync -avz --no-relative --itemize-changes --ignore-existing \
                    --files-from="${_img_output_tmp}.rel" \
                    -e "$_img_ssh_cmd" \
                    "${RPI_USER}@${host_ip}:/" \
                    "${dest}/images/outputs/" 2>&1) || true
                rm -f "${_img_output_tmp}.rel"
                local _out_count
                _out_count=$(echo "$_rsync_out_out" | grep -c '^>f' || true)
                if [ "$_out_count" -gt 0 ]; then
                    echo "$_rsync_out_out" | grep '^>f' | awk '{print $2}' | while read -r f; do
                        echo -e "    ${GREEN}+${NC} ${f}"
                    done
                    echo -e "    ${GREEN}-> ${_out_count} output image(s) collected to ${dest}/images/outputs/${NC}"
                    _img_sources_ok=$((_img_sources_ok + 1))
                else
                    echo -e "    ${GRAY}-> output images listed in logs but none transferred${NC}"
                fi
            fi

            rm -f "$_img_input_tmp" "$_img_output_tmp"

            # Count image source as one unit: increment sources_ok if any image transferred
            if [ "$_img_sources_ok" -gt 0 ]; then
                sources_ok=$((sources_ok + 1))
            fi
        fi

        echo ""
        if [ "$sources_ok" -gt 0 ]; then
            echo -e "  ${GREEN}${role}: ${sources_ok}/6 log sources collected${NC}"
        else
            echo -e "  ${YELLOW}${role}: no log sources found on this host${NC}"
            # Remove the empty role directory
            rmdir "$dest" 2>/dev/null || true
            return 1
        fi
    }

    COLLECTED=0
    SKIPPED=0

    # Track collected IPs to avoid duplicates (same IP may appear under
    # both profile-based and role-indexed naming conventions).
    # COLLECTED_IPS stores IPs; COLLECTED_ROLES stores the corresponding role
    # name so the dedup message can report which role already claimed the IP.
    COLLECTED_IPS=()
    COLLECTED_ROLES=()

    _ip_already_collected() {
        local ip="$1"
        local idx=0
        for seen in "${COLLECTED_IPS[@]}"; do
            if [ "$seen" = "$ip" ]; then
                # Return the index via stdout so caller can look up the role
                echo "$idx"
                return 0
            fi
            idx=$((idx + 1))
        done
        return 1
    }

    _try_collect() {
        local role="$1"
        local host_ip="$2"
        local group="${3:-}"  # e.g. "machine-1" or "tabletop-lab" (optional)

        if [ -z "$host_ip" ]; then
            return 1
        fi

        local _dedup_idx
        if _dedup_idx=$(_ip_already_collected "$host_ip"); then
            local _prev_role="${COLLECTED_ROLES[$_dedup_idx]}"
            echo -e "  ${GRAY}Skipping ${role}: already collected from ${host_ip} as ${_prev_role}${NC}"
            return 1
        fi

        echo -e "  Checking ${role} (${host_ip}) …"
        if smart_ssh -o ConnectTimeout=5 -o BatchMode=yes \
                "${RPI_USER}@${host_ip}" exit 2>/dev/null; then
            collect_from_host "$role" "$host_ip" "$group" && COLLECTED=$((COLLECTED + 1))
            COLLECTED_IPS+=("$host_ip")
            COLLECTED_ROLES+=("$role")
        else
            echo -e "  ${YELLOW}Skipping ${role}: host not reachable (${host_ip})${NC}"
            SKIPPED=$((SKIPPED + 1))
            COLLECTED_IPS+=("$host_ip")
            COLLECTED_ROLES+=("$role")
        fi
    }

    # When --ip is explicitly passed, collect ONLY from that IP.
    # This allows the dashboard (and CLI users) to target a single host
    # without redundantly iterating all config.env hosts.
    if [ -n "$RPI_IP" ]; then
        # Resolve group and role from entities.yaml first (source of truth).
        # Falls back to config.env-based role resolution if not found in yaml.
        mapfile -t _ip_info < <(_resolve_entity_from_yaml "$RPI_IP")
        _ip_group="${_ip_info[0]:-}"
        _ip_role="${_ip_info[1]:-}"

        if [ -z "$_ip_role" ]; then
            # Fallback: infer role from config.env variables
            _ip_role="target"
            if [ "${VEHICLE_IP:-${VEHICLE1_IP:-}}" = "$RPI_IP" ]; then
                _ip_role="vehicle"
            else
                for i in 1 2 3 4 5 6; do
                    _a="ARM_${i}_IP" _r="RPI${i}_IP"
                    if [ "${!_a:-${!_r:-}}" = "$RPI_IP" ]; then
                        _ip_role="arm_${i}"
                        break
                    fi
                done
            fi
        fi

        if [ -n "$_ip_group" ]; then
            echo -e "  ${CYAN}Collecting from --ip ${RPI_IP} (group: ${_ip_group}, role: ${_ip_role})${NC}"
        else
            echo -e "  ${CYAN}Collecting from --ip ${RPI_IP} (role: ${_ip_role})${NC}"
        fi
        _try_collect "$_ip_role" "$RPI_IP" "$_ip_group" || true
    else
        # No --ip flag — iterate all hosts from entities.yaml (source of truth).
        # Falls back to config.env if entities.yaml is unavailable.
        # Logs go to <session>/<group>/<role>/ for per-host isolation.

        # Build list of unique IPs from config.env (vehicle + arms) as a fallback set,
        # but prefer resolving group/role from entities.yaml for each IP.

        # Collect from vehicle
        _vehicle_ip="${VEHICLE_IP:-${VEHICLE1_IP:-}}"
        if [ -n "$_vehicle_ip" ]; then
            mapfile -t _vinfo < <(_resolve_entity_from_yaml "$_vehicle_ip")
            _vgroup="${_vinfo[0]:-}"
            _vrole="${_vinfo[1]:-vehicle}"
            [ -z "$_vrole" ] && _vrole="vehicle"
            _try_collect "$_vrole" "$_vehicle_ip" "$_vgroup" || true
        fi

        # Collect from arms -- support both profile-based naming (RPI<N>_IP) and
        # role-indexed naming (ARM_<N>_IP), with deduplication.
        # Each arm's logs go to <session>/<group>/arm_<N>/ (per-host isolation)
        for i in 1 2 3 4 5 6; do
            # Role-indexed: ARM_1_IP … ARM_6_IP
            arm_ip_var="ARM_${i}_IP"
            arm_ip="${!arm_ip_var:-}"

            # Profile-based: RPI1_IP … RPI6_IP
            rpi_ip_var="RPI${i}_IP"
            rpi_ip="${!rpi_ip_var:-}"

            # Prefer ARM_N_IP if set, otherwise fall back to RPI<N>_IP
            effective_ip="${arm_ip:-$rpi_ip}"

            if [ -z "$effective_ip" ]; then
                continue
            fi

            mapfile -t _ainfo < <(_resolve_entity_from_yaml "$effective_ip")
            _agroup="${_ainfo[0]:-}"
            _arole="${_ainfo[1]:-}"
            [ -z "$_arole" ] && _arole="arm_${i}"

            _try_collect "$_arole" "$effective_ip" "$_agroup" || true
        done
    fi

    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    if [ "$DRY_RUN" = true ]; then
        echo -e "${CYAN}  Dry-run complete — no files transferred${NC}"
    elif [ "$COLLECTED" -gt 0 ]; then
        echo -e "${GREEN}✓ Collected from ${COLLECTED} host(s) → ${SESSION_DIR}${NC}"
        [ "$SKIPPED" -gt 0 ] && echo -e "${YELLOW}  (${SKIPPED} host(s) skipped)${NC}"
        echo ""
        echo -e "  To analyse: ${BOLD}python3 scripts/log_analyzer/cli.py ${SESSION_DIR} --field-summary${NC}"
    else
        echo -e "${YELLOW}  No logs collected (${SKIPPED} host(s) skipped / not configured)${NC}"
        echo -e "  Make sure VEHICLE_IP (or VEHICLE1_IP), ARM_1_IP (or RPI1_IP) … are set in config.env"
    fi
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"

    exit 0
fi

# ============================================================================
# Handle --verify-fleet: Check dashboard/agent versions across all targets
# ============================================================================

if [ "$DO_VERIFY_FLEET" = true ]; then
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Fleet Dashboard & Agent Verification${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "  Config  : ${CONFIG_FILE}"
    echo ""

    DASHBOARD_PORT=8090
    AGENT_PORT=8091

    # --- Discover all fleet IPs ---
    VF_IPS=()
    VF_LABELS=()
    VF_ROLES=()

    # Vehicle
    _vf_vehicle_ip="${VEHICLE_IP:-${VEHICLE1_IP:-}}"
    if [ -n "$_vf_vehicle_ip" ]; then
        VF_IPS+=("$_vf_vehicle_ip")
        VF_LABELS+=("vehicle")
        VF_ROLES+=("vehicle")
    fi

    # Arms
    for i in 1 2 3 4 5 6; do
        arm_ip_var="ARM_${i}_IP"
        arm_ip="${!arm_ip_var:-}"
        rpi_ip_var="RPI${i}_IP"
        rpi_ip="${!rpi_ip_var:-}"
        effective_ip="${arm_ip:-$rpi_ip}"
        if [ -n "$effective_ip" ]; then
            VF_IPS+=("$effective_ip")
            VF_LABELS+=("arm_${i}")
            VF_ROLES+=("arm")
        fi
    done

    if [ ${#VF_IPS[@]} -eq 0 ]; then
        log_error "No fleet IPs configured (set VEHICLE_IP, ARM_1_IP … ARM_6_IP in config.env)"
        exit 1
    fi

    log_info "Targets : ${VF_IPS[*]} (${#VF_IPS[@]} hosts)"
    echo ""

    # --- Query each target via SSH-proxied curl ---
    # We SSH into each RPi and curl localhost, because direct curl from WSL
    # cannot reach Windows hotspot IPs (192.168.137.x subnet).
    log_step "Querying dashboard and agent endpoints (via SSH)..."
    echo ""

    # Results arrays
    VF_HOSTNAMES=()
    VF_DASH_VERSIONS=()
    VF_DASH_STATUS=()
    VF_AGENT_STATUS=()
    VF_AGENT_VERSIONS=()
    VF_UPTIMES=()

    VF_ONLINE=0
    VF_OFFLINE=0

    for idx in "${!VF_IPS[@]}"; do
        ip="${VF_IPS[$idx]}"
        label="${VF_LABELS[$idx]}"

        # Set global RPI_IP so smart_ssh routes correctly (WSL → Windows SSH bridge)
        RPI_IP="$ip"

        # --- Check SSH reachability first ---
        ssh_ok=false
        if smart_ssh -o ConnectTimeout=5 -o BatchMode=yes "${RPI_USER}@${ip}" "true" 2>/dev/null; then
            ssh_ok=true
        fi

        # Query dashboard /api/system/info via SSH-proxied curl (localhost on RPi)
        dash_response=""
        if [ "$ssh_ok" = true ]; then
            dash_response=$(smart_ssh -o ConnectTimeout=5 "${RPI_USER}@${ip}" \
                "curl -s --connect-timeout 3 --max-time 5 http://localhost:${DASHBOARD_PORT}/api/system/info" 2>/dev/null) || true
        fi

        if [ -n "$dash_response" ]; then
            # Parse JSON fields using grep/sed (no jq dependency)
            dash_version=$(echo "$dash_response" | \
                grep -o '"dashboard_version"[[:space:]]*:[[:space:]]*"[^"]*"' | \
                sed 's/.*: *"//;s/"//')
            hostname=$(echo "$dash_response" | \
                grep -o '"hostname"[[:space:]]*:[[:space:]]*"[^"]*"' | \
                sed 's/.*: *"//;s/"//')
            uptime_s=$(echo "$dash_response" | \
                grep -o '"uptime_seconds"[[:space:]]*:[[:space:]]*[0-9]*' | \
                sed 's/.*: *//')

            VF_DASH_VERSIONS+=("${dash_version:-?}")
            VF_DASH_STATUS+=("running")
            VF_HOSTNAMES+=("${hostname:-?}")

            # Format uptime as human-readable
            if [ -n "$uptime_s" ]; then
                up_h=$((uptime_s / 3600))
                up_m=$(( (uptime_s % 3600) / 60))
                VF_UPTIMES+=("${up_h}h${up_m}m")
            else
                VF_UPTIMES+=("-")
            fi

            VF_ONLINE=$((VF_ONLINE + 1))
        else
            VF_DASH_VERSIONS+=("-")
            VF_DASH_STATUS+=("offline")
            VF_HOSTNAMES+=("-")
            VF_UPTIMES+=("-")
            VF_OFFLINE=$((VF_OFFLINE + 1))
        fi

        # Query agent /health via SSH-proxied curl (localhost on RPi)
        agent_response=""
        if [ "$ssh_ok" = true ]; then
            agent_response=$(smart_ssh -o ConnectTimeout=5 "${RPI_USER}@${ip}" \
                "curl -s --connect-timeout 3 --max-time 5 http://localhost:${AGENT_PORT}/health" 2>/dev/null) || true
        fi

        if [ -n "$agent_response" ]; then
            # Try to extract agent_version if present (it may not be in /health)
            agent_ver=$(echo "$agent_response" | \
                grep -o '"agent_version"[[:space:]]*:[[:space:]]*"[^"]*"' | \
                sed 's/.*: *"//;s/"//') || true
            VF_AGENT_STATUS+=("running")
            VF_AGENT_VERSIONS+=("${agent_ver:-n/a}")
        else
            VF_AGENT_STATUS+=("offline")
            VF_AGENT_VERSIONS+=("-")
        fi
    done

    # --- Print results table ---
    echo ""
    printf "  ${BOLD}%-18s %-10s %-18s %-10s %-12s %-10s %-10s${NC}\n" \
        "TARGET" "ROLE" "IP" "DASHBOARD" "VERSION" "AGENT" "UPTIME"
    printf "  %-18s %-10s %-18s %-10s %-12s %-10s %-10s\n" \
        "──────────────────" "──────────" "──────────────────" "──────────" "────────────" "──────────" "──────────"

    for idx in "${!VF_IPS[@]}"; do
        label="${VF_LABELS[$idx]}"
        ip="${VF_IPS[$idx]}"
        hostname="${VF_HOSTNAMES[$idx]}"
        role="${VF_ROLES[$idx]}"
        dash_status="${VF_DASH_STATUS[$idx]}"
        dash_ver="${VF_DASH_VERSIONS[$idx]}"
        agent_status="${VF_AGENT_STATUS[$idx]}"
        uptime="${VF_UPTIMES[$idx]}"

        # Use hostname as primary identifier; fall back to config label if offline
        if [ "$hostname" != "-" ] && [ "$hostname" != "?" ]; then
            target_name="$hostname"
        else
            target_name="$label"
        fi

        # Color-code statuses
        if [ "$dash_status" = "running" ]; then
            dash_display="${GREEN}running${NC}"
        else
            dash_display="${RED}offline${NC}"
        fi

        if [ "$agent_status" = "running" ]; then
            agent_display="${GREEN}running${NC}"
        else
            agent_display="${RED}offline${NC}"
        fi

        printf "  %-18s %-10s %-18s ${dash_display}%-3s %-12s ${agent_display}%-3s %-10s\n" \
            "$target_name" "$role" "$ip" "" "$dash_ver" "" "$uptime"
    done

    # --- Version drift detection ---
    echo ""
    # Collect unique non-empty dashboard versions (exclude "-" and "?")
    VF_UNIQUE_VERSIONS=()
    for v in "${VF_DASH_VERSIONS[@]}"; do
        if [ "$v" != "-" ] && [ "$v" != "?" ]; then
            # Check if already in unique list
            found=false
            for uv in "${VF_UNIQUE_VERSIONS[@]:-}"; do
                if [ "$uv" = "$v" ]; then
                    found=true
                    break
                fi
            done
            if [ "$found" = false ]; then
                VF_UNIQUE_VERSIONS+=("$v")
            fi
        fi
    done

    if [ ${#VF_UNIQUE_VERSIONS[@]} -gt 1 ]; then
        log_warn "VERSION DRIFT DETECTED: dashboards report different versions: ${VF_UNIQUE_VERSIONS[*]}"
        echo -e "  ${YELLOW}Re-deploy to all targets: ./sync.sh --deploy-cross --all-targets --restart${NC}"
    elif [ ${#VF_UNIQUE_VERSIONS[@]} -eq 1 ]; then
        log_success "All online dashboards report version: ${VF_UNIQUE_VERSIONS[0]}"
    fi

    # --- Summary ---
    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    if [ "$VF_OFFLINE" -eq 0 ]; then
        echo -e "${BOLD}${GREEN}  Fleet Status: ${VF_ONLINE}/${#VF_IPS[@]} targets ONLINE — all dashboards updated${NC}"
    elif [ "$VF_ONLINE" -eq 0 ]; then
        echo -e "${BOLD}${RED}  Fleet Status: 0/${#VF_IPS[@]} targets reachable — no dashboards responding${NC}"
    else
        echo -e "${BOLD}${YELLOW}  Fleet Status: ${VF_ONLINE}/${#VF_IPS[@]} targets ONLINE (${VF_OFFLINE} offline)${NC}"
    fi
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"

    [ "$VF_OFFLINE" -gt 0 ] && exit 1
    [ ${#VF_UNIQUE_VERSIONS[@]} -gt 1 ] && exit 1
    exit 0
fi

# ============================================================================
# Handle --test-mqtt: Test MQTT connectivity from vehicle to all arms
# ============================================================================

if [ "$DO_TEST_MQTT" = true ]; then
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  MQTT Connectivity Test${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "  Config  : ${CONFIG_FILE}"
    echo ""

    # Build SSH options
    SSH_KEY_OPT=""
    if [ -n "$RPI_SSH_KEY" ]; then
        SSH_KEY_OPT="-i $RPI_SSH_KEY"
    fi

    # --- Discover vehicle IP ---
    MQTT_VEHICLE_IP="${VEHICLE_IP:-${VEHICLE1_IP:-}}"
    if [ -z "$MQTT_VEHICLE_IP" ]; then
        log_error "No vehicle IP configured (set VEHICLE_IP or VEHICLE1_IP in config.env)"
        exit 1
    fi

    # --- Discover arm IPs ---
    MQTT_ARM_IPS=()
    MQTT_ARM_LABELS=()
    for i in 1 2 3 4 5 6; do
        arm_ip_var="ARM_${i}_IP"
        arm_ip="${!arm_ip_var:-}"
        rpi_ip_var="RPI${i}_IP"
        rpi_ip="${!rpi_ip_var:-}"
        effective_ip="${arm_ip:-$rpi_ip}"
        if [ -n "$effective_ip" ]; then
            MQTT_ARM_IPS+=("$effective_ip")
            MQTT_ARM_LABELS+=("arm_${i}")
        fi
    done

    if [ ${#MQTT_ARM_IPS[@]} -eq 0 ]; then
        log_error "No arm IPs configured (set ARM_1_IP … ARM_6_IP or RPI1_IP … in config.env)"
        exit 1
    fi

    log_info "Vehicle : ${MQTT_VEHICLE_IP}"
    log_info "Arms    : ${MQTT_ARM_IPS[*]} (${#MQTT_ARM_IPS[@]} targets)"
    echo ""

    # --- Prerequisite checks ---
    log_step "Checking prerequisites..."

    # Check SSH connectivity to vehicle
    if ! smart_ssh -o ConnectTimeout=5 -o BatchMode=yes \
            "${RPI_USER}@${MQTT_VEHICLE_IP}" "exit" 2>/dev/null; then
        log_error "Cannot SSH to vehicle (${MQTT_VEHICLE_IP})"
        exit 1
    fi
    log_success "SSH to vehicle OK"

    # Check mosquitto running on vehicle
    if ! smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
            "${RPI_USER}@${MQTT_VEHICLE_IP}" \
            "systemctl is-active --quiet mosquitto.service" 2>/dev/null; then
        log_error "mosquitto is not running on vehicle (${MQTT_VEHICLE_IP})"
        echo -e "  Fix: ${YELLOW}./sync.sh --provision --ip ${MQTT_VEHICLE_IP} --role vehicle${NC}"
        exit 1
    fi
    log_success "mosquitto active on vehicle"

    # Check mosquitto_pub available on vehicle
    if ! smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
            "${RPI_USER}@${MQTT_VEHICLE_IP}" \
            "command -v mosquitto_pub >/dev/null 2>&1" 2>/dev/null; then
        log_error "mosquitto_pub not found on vehicle (${MQTT_VEHICLE_IP})"
        echo -e "  Fix: ${YELLOW}ssh ${RPI_USER}@${MQTT_VEHICLE_IP} 'sudo apt-get install -y mosquitto-clients'${NC}"
        exit 1
    fi
    log_success "mosquitto_pub available on vehicle"

    # Check SSH connectivity and mosquitto_sub on each arm
    MQTT_REACHABLE_ARMS=()
    MQTT_REACHABLE_LABELS=()
    MQTT_UNREACHABLE=()
    for idx in "${!MQTT_ARM_IPS[@]}"; do
        arm_ip="${MQTT_ARM_IPS[$idx]}"
        arm_label="${MQTT_ARM_LABELS[$idx]}"

        if ! smart_ssh -o ConnectTimeout=5 -o BatchMode=yes \
                "${RPI_USER}@${arm_ip}" "exit" 2>/dev/null; then
            log_warn "${arm_label} (${arm_ip}): SSH unreachable — skipping"
            MQTT_UNREACHABLE+=("${arm_label}:${arm_ip}")
            continue
        fi

        if ! smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
                "${RPI_USER}@${arm_ip}" \
                "command -v mosquitto_sub >/dev/null 2>&1" 2>/dev/null; then
            log_warn "${arm_label} (${arm_ip}): mosquitto_sub not found — skipping"
            echo -e "    Fix: ${YELLOW}ssh ${RPI_USER}@${arm_ip} 'sudo apt-get install -y mosquitto-clients'${NC}"
            MQTT_UNREACHABLE+=("${arm_label}:${arm_ip}")
            continue
        fi

        MQTT_REACHABLE_ARMS+=("$arm_ip")
        MQTT_REACHABLE_LABELS+=("$arm_label")
    done

    if [ ${#MQTT_REACHABLE_ARMS[@]} -eq 0 ]; then
        log_error "No reachable arms with mosquitto_sub — cannot run test"
        exit 1
    fi

    echo ""
    log_step "Running MQTT connectivity test..."
    echo ""

    # Generate unique test topic (avoid collisions with real traffic)
    local_test_topic="pragati/mqtt_test"

    # --- Results table ---
    printf "  ${BOLD}%-14s %-20s %-12s %-10s${NC}\n" "ARM" "IP" "STATUS" "LATENCY"
    printf "  %-14s %-20s %-12s %-10s\n" "--------------" "--------------------" "------------" "----------"

    MQTT_PASS=0
    MQTT_FAIL=0

    for idx in "${!MQTT_REACHABLE_ARMS[@]}"; do
        arm_ip="${MQTT_REACHABLE_ARMS[$idx]}"
        arm_label="${MQTT_REACHABLE_LABELS[$idx]}"

        # Generate unique message per arm to avoid cross-contamination
        test_msg="mqtt_test_${arm_label}_$(date +%s%N)"

        # Measure round-trip time
        start_ns=$(date +%s%N)

        # Start subscriber on arm in background, publish from vehicle, then wait
        # The subscriber waits for exactly 1 message (-C 1) with a 5-second timeout.
        # We publish from the vehicle after a brief delay to ensure the subscriber is ready.
        received=$(smart_ssh -o ConnectTimeout=5 ${SSH_KEY_OPT} \
            "${RPI_USER}@${arm_ip}" \
            "timeout 5 mosquitto_sub -h ${MQTT_VEHICLE_IP} -t '${local_test_topic}' -C 1 &
             SUB_PID=\$!
             sleep 0.3
             mosquitto_pub -h ${MQTT_VEHICLE_IP} -t '${local_test_topic}' -m '${test_msg}'
             wait \$SUB_PID 2>/dev/null
             " 2>/dev/null) || true

        end_ns=$(date +%s%N)

        # Calculate latency in milliseconds
        latency_ms=$(( (end_ns - start_ns) / 1000000 ))

        # Trim whitespace / carriage returns from received message
        received=$(echo "$received" | tr -d '\r\n ')
        test_msg_clean=$(echo "$test_msg" | tr -d '\r\n ')

        if [ "$received" = "$test_msg_clean" ]; then
            printf "  ${GREEN}%-14s %-20s %-12s %-10s${NC}\n" "$arm_label" "$arm_ip" "PASS" "${latency_ms}ms"
            MQTT_PASS=$((MQTT_PASS + 1))
        else
            printf "  ${RED}%-14s %-20s %-12s %-10s${NC}\n" "$arm_label" "$arm_ip" "FAIL" "-"
            MQTT_FAIL=$((MQTT_FAIL + 1))
        fi
    done

    # Add unreachable arms to the table
    for entry in "${MQTT_UNREACHABLE[@]}"; do
        u_label="${entry%%:*}"
        u_ip="${entry#*:}"
        printf "  ${YELLOW}%-14s %-20s %-12s %-10s${NC}\n" "$u_label" "$u_ip" "SKIP" "-"
    done

    # --- Summary ---
    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    total_tested=$((MQTT_PASS + MQTT_FAIL))
    total_all=$((total_tested + ${#MQTT_UNREACHABLE[@]}))
    if [ "$MQTT_FAIL" -eq 0 ] && [ ${#MQTT_UNREACHABLE[@]} -eq 0 ]; then
        echo -e "${BOLD}${GREEN}  MQTT Test: ${MQTT_PASS}/${total_tested} arms PASSED${NC}"
    elif [ "$MQTT_FAIL" -eq 0 ]; then
        echo -e "${BOLD}${YELLOW}  MQTT Test: ${MQTT_PASS}/${total_tested} arms PASSED (${#MQTT_UNREACHABLE[@]} skipped)${NC}"
    else
        echo -e "${BOLD}${RED}  MQTT Test: ${MQTT_FAIL}/${total_tested} arms FAILED${NC}"
        [ ${#MQTT_UNREACHABLE[@]} -gt 0 ] && \
            echo -e "${YELLOW}  (${#MQTT_UNREACHABLE[@]} arm(s) skipped — unreachable or missing mosquitto-clients)${NC}"
    fi
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"

    [ "$MQTT_FAIL" -gt 0 ] && exit 1
    exit 0
fi

# ============================================================================
# Validate Configuration
# ============================================================================

# Check if IP is set
if [ -z "$RPI_IP" ]; then
    echo -e "${RED}Error: RPI_IP not set${NC}"
    echo ""
    echo "Please specify the Raspberry Pi IP address:"
    echo "  $0 --ip <IP_ADDRESS>"
    echo ""
    echo "To save for future use:"
    echo "  $0 --ip <IP_ADDRESS> --save"
    echo ""
    echo "Or create config file: $CONFIG_FILE"
    echo "  RPI_IP=192.168.137.253"
    echo "  RPI_USER=ubuntu"
    exit 1
fi

# Set destination directory (use config value or default)
if [ -n "$RPI_TARGET_DIR" ]; then
    RPI_DIR="$RPI_TARGET_DIR"
    # Expand tilde if present
    RPI_DIR="${RPI_DIR/#\~/$HOME}"
else
    RPI_DIR="/home/${RPI_USER}/pragati_ros2"
fi

# Save config if requested (default IP/user)
if [ "$SAVE_CONFIG" = true ]; then
    # Preserve existing named targets, update default
    if [ -f "$CONFIG_FILE" ]; then
        grep -v "^RPI_IP=\|^RPI_USER=" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" 2>/dev/null || true
        mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
    fi
    echo "RPI_IP=${RPI_IP}" >> "$CONFIG_FILE"
    echo "RPI_USER=${RPI_USER}" >> "$CONFIG_FILE"
    echo -e "${GREEN}✓ Default config saved to $CONFIG_FILE${NC}"
fi

# ============================================================================
# Provisioning & Verification Functions
# ============================================================================

# Detect RPi role based on existing service files and running services
# Returns "vehicle" or "arm" via stdout
detect_rpi_role() {
    if [ -n "$RPI_ROLE" ]; then
        echo "$RPI_ROLE"
        return 0
    fi

    local role_output
    role_output=$(smart_ssh "${RPI_USER}@${RPI_IP}" 'bash -s' << 'ROLE_DETECT'
# Check for existing service files first
if [ -f /etc/systemd/system/vehicle_launch.service ]; then
    echo "vehicle|vehicle_launch.service found"
    exit 0
fi
if [ -f /etc/systemd/system/arm_launch.service ]; then
    echo "arm|arm_launch.service found"
    exit 0
fi
# Fallback: check running services
if systemctl is-active --quiet mosquitto.service 2>/dev/null; then
    echo "vehicle|mosquitto.service active"
    exit 0
fi
# Default to arm
echo "arm|default (no service indicators found)"
ROLE_DETECT
    )
    local role="${role_output%%|*}"
    local role_reason="${role_output#*|}"
    # Log to stderr so callers see it but stdout stays clean for role value
    echo "  Role detection: ${role} (${role_reason})" >&2
    echo "$role"
}

# Run provisioning on the current target RPi
run_provision() {
    local role
    role=$(detect_rpi_role)
    local role_source="auto-detected"
    [ -n "$RPI_ROLE" ] && role_source="explicit"

    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Provisioning: ${RPI_USER}@${RPI_IP} (role: ${role}, ${role_source})${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Provision log will be saved to RPi at the end so evidence persists
    local provision_log_name="provision_$(date +%Y%m%d_%H%M%S).log"

    if [ "$role" = "arm" ] && [ "$role_source" = "auto-detected" ]; then
        # Check if this is a first-time provision with no services at all
        local has_services
        has_services=$(smart_ssh "${RPI_USER}@${RPI_IP}" 'bash -s' << 'CHECK_SVC'
if [ -f /etc/systemd/system/vehicle_launch.service ] || \
   [ -f /etc/systemd/system/arm_launch.service ] || \
   systemctl is-active --quiet mosquitto.service 2>/dev/null; then
    echo "yes"
else
    echo "no"
fi
CHECK_SVC
        )
        if [ "$has_services" = "no" ]; then
            log_warn "Role defaulted to arm -- use --role to override"
        fi
    fi

    local provision_ok=0
    local provision_fail=0
    local provision_skipped=0
    local provision_errors=""

    # --- Consolidated provision script ---
    # All sudo operations are assembled into a single bash script, uploaded to the RPi,
    # and executed with one `ssh -t sudo bash` call. This eliminates multiple SSH+sudo
    # round-trips and password prompts. Each step emits structured STEP_RESULT markers
    # for the caller to parse pass/fail/skip status.

    local prov_ts
    prov_ts=$(date +%s)
    local prov_tmp_dir="/tmp/pragati_provision_${prov_ts}"
    local prov_script_remote="${prov_tmp_dir}/provision.sh"
    local prov_results_remote="${prov_tmp_dir}/results.txt"

    # Compute clock target (UTC time string) on the dev machine BEFORE uploading.
    # The script uses this baked-in value to set RPi clock.
    local clock_target_utc
    clock_target_utc=$(date -u +"%Y-%m-%d %H:%M:%S")

    # Determine total step count based on role
    # Steps: 1=power_mgmt, 2=ssh_keepalive, 3=timezone_ntp, 4=clock_sync,
    #         5=pkg_mosquitto_clients, 6=pkg_mosquitto_broker (vehicle only),
    #         +1=polkit_policy, +1=sudoers, +1=boot_optimization, +1=hostname, +1=config_txt_can, last=service_install
    local total_steps=12
    if [ "$role" != "vehicle" ]; then
        total_steps=11  # no mosquitto broker step for arm
    fi

    # Compute step numbers for steps after mosquitto (inserted after mosquitto steps)
    # polkit_policy is the step right after mosquitto, then sudoers
    local polkit_step=7
    local sudoers_step=8
    local boot_opt_step=9
    local hostname_step=10
    local config_txt_step=11
    if [ "$role" != "vehicle" ]; then
        polkit_step=6
        sudoers_step=7
        boot_opt_step=8
        hostname_step=9
        config_txt_step=10
    fi

    # Determine target hostname from IP mapping
    local target_hostname=""
    case "$RPI_IP" in
        192.168.137.12)  target_hostname="pragati-arm1" ;;
        192.168.137.238) target_hostname="pragati-arm2" ;;
        192.168.137.203) target_hostname="pragati-vehicle" ;;
    esac

    log_step "Assembling consolidated provision script (${total_steps} steps)..."

    # Create temp dir and scp service files + can_watchdog.sh to RPi
    smart_ssh "${RPI_USER}@${RPI_IP}" "mkdir -p ${prov_tmp_dir}/systemd" 2>&1

    # Copy service files from local systemd/ to RPi temp dir
    # NOTE: Uses smart_ssh pipe instead of raw scp so WSL→hotspot routing works
    local svc_file
    # NOTE: wifi-watchdog.service removed — watchdog was interfering with NM autoconnect
    for svc_file in pigpiod.service can-watchdog@.service field-monitor.service boot_timing.service boot_timing.timer arm_launch.service vehicle_launch.service pragati-dashboard.service pragati-agent.service; do
        local local_svc="${SCRIPT_DIR}/systemd/${svc_file}"
        if [ -f "$local_svc" ]; then
            smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${prov_tmp_dir}/systemd/${svc_file}" < "$local_svc" 2>&1 || \
                log_warn "Failed to copy ${svc_file} (may not be needed for role ${role})"
        fi
    done

    # Copy can_watchdog.sh
    # NOTE: Uses smart_ssh pipe instead of raw scp so WSL→hotspot routing works
    local local_can_watchdog="${SCRIPT_DIR}/scripts/maintenance/can/can_watchdog.sh"
    if [ -f "$local_can_watchdog" ]; then
        smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${prov_tmp_dir}/can_watchdog.sh" < "$local_can_watchdog" 2>&1 || \
            log_warn "Failed to copy can_watchdog.sh"
    fi

    # Copy wifi_watchdog.sh
    # NOTE: wifi-watchdog disabled — was interfering with NM autoconnect recovery.
    # NM autoconnect with infinite retries handles reconnection better on its own.
    # Keeping script in repo for future use if needed.
    # local local_wifi_watchdog="${SCRIPT_DIR}/scripts/maintenance/wifi/wifi_watchdog.sh"
    # if [ -f "$local_wifi_watchdog" ]; then
    #     smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${prov_tmp_dir}/wifi_watchdog.sh" < "$local_wifi_watchdog" 2>&1 || \
    #         log_warn "Failed to copy wifi_watchdog.sh"
    # fi

    # Copy boot_timing_capture.sh
    local local_boot_timing="${SCRIPT_DIR}/scripts/diagnostics/boot_timing_capture.sh"
    if [ -f "$local_boot_timing" ]; then
        smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${prov_tmp_dir}/boot_timing_capture.sh" < "$local_boot_timing" 2>&1 || \
            log_warn "Failed to copy boot_timing_capture.sh"
    fi

    # Copy polkit policy file for dashboard service management
    local local_polkit="${SCRIPT_DIR}/configs/polkit/pragati-dashboard.pkla"
    if [ -f "$local_polkit" ]; then
        smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${prov_tmp_dir}/pragati-dashboard.pkla" < "$local_polkit" 2>&1 || \
            log_warn "Failed to copy pragati-dashboard.pkla"
    fi

    # Write the consolidated provision script to RPi (no sudo needed for writing to /tmp).
    # IMPORTANT: heredoc delimiter is UNQUOTED so local variables are expanded (baked in).
    smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${prov_script_remote}" << PROVISION_SCRIPT
set -e

# --- Consolidated Pragati Provision Script ---
# Generated by sync.sh at ${clock_target_utc} UTC
# Role: ${role} | Target: ${RPI_USER}@${RPI_IP}

TOTAL_STEPS=${total_steps}
ROLE="${role}"
CLOCK_TARGET="${clock_target_utc}"
TMP_DIR="${prov_tmp_dir}"
SVC_SRC="\${TMP_DIR}/systemd"
RPI_DIR_PATH="${RPI_DIR}"

# Structured output helper: STEP_RESULT:step_name:applied|skipped|failed[:detail]
step_result() {
    echo "STEP_RESULT:\$1:\$2:\${3:-}"
}

# Check internet connectivity (fast TCP probe — avoids hanging apt-get on offline RPi)
has_internet=false
if nc -zw2 8.8.8.8 53 2>/dev/null || nc -zw2 1.1.1.1 80 2>/dev/null; then
    has_internet=true
fi
if [ "\$has_internet" = true ]; then
    echo "  [OK] Internet connectivity confirmed"
else
    echo "  [WARN] No internet access detected — apt-get steps will be skipped"
fi

# Track if apt-get update has been run (avoid running it multiple times)
apt_updated=false
ensure_apt_updated() {
    if [ "\$apt_updated" = false ]; then
        apt-get -o Acquire::http::Timeout=10 -o Acquire::Connect::Timeout=10 update -qq 2>&1 || true
        apt_updated=true
    fi
}

########################################################################
# [1/${total_steps}] Power management fixes
########################################################################
echo "[1/${total_steps}] Checking power management..."

power_ok=true
# Install iw if missing (needed to verify WiFi power save status)
if ! command -v iw >/dev/null 2>&1; then
    if [ "\$has_internet" = true ]; then
        echo "  Installing iw (WiFi diagnostic tool)..."
        ensure_apt_updated
        apt-get -o Acquire::http::Timeout=10 -o Acquire::Connect::Timeout=10 install -y -qq iw 2>&1 || echo "  [WARN] Failed to install iw"
    else
        echo "  [WARN] iw not installed and no internet — skipping install, using NM config fallback"
    fi
fi

# Check WiFi power save
wifi_ps=\$(iw dev wlan0 get power_save 2>/dev/null | grep -o 'on\|off' || echo "unknown")
usb_autosuspend=\$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")

# When iw is not installed or no wlan0, fall back to checking NetworkManager config files
if [ "\$wifi_ps" = "unknown" ]; then
    if grep -rq 'wifi.powersave = 2' /etc/NetworkManager/conf.d/ 2>/dev/null; then
        wifi_ps="off"  # config says disabled, trust it
    fi
fi

if [ "\$wifi_ps" = "off" ] && [ "\$usb_autosuspend" = "-1" ]; then
    echo "  Power management already configured"
    step_result "power_mgmt" "skipped"
else
    echo "  Applying power management fixes..."
    if [ -x "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_power_management.sh" ]; then
        bash "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_power_management.sh" || power_ok=false
    elif [ -f "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_power_management.sh" ]; then
        bash "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_power_management.sh" || power_ok=false
    else
        echo "  [WARN] fix_rpi_power_management.sh not found at \${RPI_DIR_PATH}/scripts/maintenance/rpi/"
        power_ok=false
    fi
    if [ "\$power_ok" = true ]; then
        step_result "power_mgmt" "applied"
    else
        step_result "power_mgmt" "failed" "power management script failed"
    fi
fi

# NOTE: dtoverlay=disable-bt was tried here to reduce brcmfmac WiFi/BT coexistence
# issues, but it caused WiFi to fail on first boot (requires driver reload to connect).
# The bluetooth.service is already disabled at systemd level (step 4 boot optimization),
# which prevents BT userspace activity. That is sufficient.

########################################################################
# [2/${total_steps}] SSH keepalive configuration
########################################################################
echo ""
echo "[2/${total_steps}] Checking SSH keepalive..."

if grep -q "ClientAliveInterval 60" /etc/ssh/sshd_config.d/keepalive.conf 2>/dev/null; then
    echo "  SSH keepalive already configured"
    step_result "ssh_keepalive" "skipped"
else
    echo "  Applying SSH keepalive config..."
    keepalive_ok=true
    if [ -f "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh" ]; then
        bash "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_ssh_keepalive.sh" || keepalive_ok=false
    else
        echo "  [WARN] fix_rpi_ssh_keepalive.sh not found"
        keepalive_ok=false
    fi
    if [ "\$keepalive_ok" = true ]; then
        step_result "ssh_keepalive" "applied"
    else
        step_result "ssh_keepalive" "failed" "SSH keepalive script failed"
    fi
fi

########################################################################
# [3/${total_steps}] Timezone and NTP configuration
########################################################################
echo ""
echo "[3/${total_steps}] Checking timezone and NTP..."

tz_current=\$(timedatectl show --property=Timezone --value 2>/dev/null || echo "unknown")
ntp_current=\$(timedatectl show --property=NTP --value 2>/dev/null || echo "unknown")

if [ "\$tz_current" = "Asia/Kolkata" ] && [ "\$ntp_current" = "yes" ]; then
    echo "  Timezone (Asia/Kolkata) and NTP already configured"
    step_result "timezone_ntp" "skipped"
else
    echo "  Setting timezone and enabling NTP..."
    tz_ok=true
    if [ -f "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_timezone.sh" ]; then
        bash "\${RPI_DIR_PATH}/scripts/maintenance/rpi/fix_rpi_timezone.sh" || tz_ok=false
    else
        echo "  [WARN] fix_rpi_timezone.sh not found"
        tz_ok=false
    fi
    if [ "\$tz_ok" = true ]; then
        step_result "timezone_ntp" "applied"
    else
        step_result "timezone_ntp" "failed" "Timezone/NTP script failed"
    fi
fi

########################################################################
# [4/${total_steps}] Clock sync from dev machine
########################################################################
echo ""
echo "[4/${total_steps}] Checking clock sync..."

# RPi 4B has no battery-backed RTC, so clock resets on every power cycle.
# On LAN-only networks (no internet), NTP can't reach public servers.
rpi_epoch=\$(date +%s)
# Parse the baked-in clock target to epoch for drift comparison
clock_target_epoch=\$(date -u -d "\${CLOCK_TARGET}" +%s 2>/dev/null || echo 0)
if [ "\$clock_target_epoch" -gt 0 ]; then
    drift=\$(( clock_target_epoch - rpi_epoch ))
    [ "\$drift" -lt 0 ] && drift=\$((-drift))
else
    drift=999  # force sync if we can't parse
fi

if [ "\$drift" -le 5 ]; then
    echo "  Clock already in sync (drift: \${drift}s)"
    step_result "clock_sync" "skipped" "drift:\${drift}s"
else
    echo "  Syncing clock (drift: \${drift}s, target: \${CLOCK_TARGET} UTC)..."
    if date -u -s "\${CLOCK_TARGET}" >/dev/null 2>&1; then
        hwclock -w 2>/dev/null || true
        # Verify
        new_epoch=\$(date +%s)
        new_drift=\$(( clock_target_epoch - new_epoch ))
        [ "\$new_drift" -lt 0 ] && new_drift=\$((-new_drift))
        if [ "\$new_drift" -le 5 ]; then
            echo "  Clock synced (new drift: \${new_drift}s)"
            step_result "clock_sync" "applied" "drift_before:\${drift}s,drift_after:\${new_drift}s"
        else
            echo "  Clock set but drift remains: \${new_drift}s"
            step_result "clock_sync" "failed" "drift persists:\${new_drift}s"
        fi
    else
        echo "  Failed to set clock"
        step_result "clock_sync" "failed" "date -s command failed"
    fi
fi

########################################################################
# [5/${total_steps}] Package: mosquitto-clients
########################################################################
echo ""
echo "[5/${total_steps}] Checking mosquitto-clients package..."

if dpkg -l mosquitto-clients 2>/dev/null | grep -q "^ii"; then
    echo "  mosquitto-clients already installed"
    step_result "pkg_mosquitto_clients" "skipped"
elif [ "\$has_internet" = false ]; then
    echo "  [WARN] No internet — skipping mosquitto-clients install (run provision again with internet)"
    step_result "pkg_mosquitto_clients" "skipped" "no internet access"
else
    echo "  Installing mosquitto-clients..."
    ensure_apt_updated
    if apt-get -o Acquire::http::Timeout=10 -o Acquire::Connect::Timeout=10 install -y -qq mosquitto-clients 2>&1; then
        step_result "pkg_mosquitto_clients" "applied"
    else
        step_result "pkg_mosquitto_clients" "failed" "apt-get install failed"
    fi
fi

########################################################################
# [6/${total_steps}] Package: mosquitto broker (vehicle only)
########################################################################
$(if [ "$role" = "vehicle" ]; then
echo 'echo ""'
echo "echo \"[6/${total_steps}] Checking mosquitto broker package...\""
echo ''
echo 'if dpkg -l mosquitto 2>/dev/null | grep -q "^ii"; then'
echo '    echo "  mosquitto broker already installed"'
echo '    step_result "pkg_mosquitto_broker" "skipped"'
echo 'elif [ "$has_internet" = false ]; then'
echo '    echo "  [WARN] No internet — skipping mosquitto broker install (run provision again with internet)"'
echo '    step_result "pkg_mosquitto_broker" "skipped" "no internet access"'
echo 'else'
echo '    echo "  Installing mosquitto broker..."'
echo '    ensure_apt_updated'
echo '    if apt-get -o Acquire::http::Timeout=10 -o Acquire::Connect::Timeout=10 install -y -qq mosquitto 2>&1; then'
echo '        step_result "pkg_mosquitto_broker" "applied"'
echo '    else'
echo '        step_result "pkg_mosquitto_broker" "failed" "apt-get install failed"'
echo '    fi'
echo 'fi'
fi)

########################################################################
# [${polkit_step}/${total_steps}] Polkit policy for dashboard service management
########################################################################
echo ""
echo "[${polkit_step}/${total_steps}] Checking polkit policy for dashboard..."

POLKIT_SRC="\${TMP_DIR}/pragati-dashboard.pkla"
POLKIT_DEST="/etc/polkit-1/localauthority/50-local.d/pragati-dashboard.pkla"

if [ ! -f "\$POLKIT_SRC" ]; then
    echo "  [WARN] polkit policy file not found in provision payload"
    step_result "polkit_policy" "skipped" "source file missing"
elif [ -f "\$POLKIT_DEST" ] && cmp -s "\$POLKIT_SRC" "\$POLKIT_DEST"; then
    echo "  Polkit policy already installed (skipped)"
    step_result "polkit_policy" "skipped"
else
    mkdir -p /etc/polkit-1/localauthority/50-local.d
    if cp "\$POLKIT_SRC" "\$POLKIT_DEST" 2>&1; then
        echo "  [OK] Installed polkit policy for pragati dashboard"
        step_result "polkit_policy" "applied"
    else
        echo "  [FAIL] Could not install polkit policy"
        step_result "polkit_policy" "failed" "copy failed"
    fi
fi

########################################################################
# [${sudoers_step}/${total_steps}] Sudoers for passwordless systemctl/reboot
########################################################################
echo ""
echo "[${sudoers_step}/${total_steps}] Checking sudoers for agent privileges..."

SUDOERS_FILE="/etc/sudoers.d/pragati-agent"
SUDOERS_CONTENT="ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /usr/bin/journalctl, /usr/sbin/reboot, /usr/sbin/shutdown, /usr/bin/date, /sbin/hwclock"

# Check if sudoers file exists with correct content
if [ -f "\$SUDOERS_FILE" ] && grep -q "NOPASSWD.*systemctl.*journalctl.*reboot.*shutdown" "\$SUDOERS_FILE" 2>/dev/null; then
    echo "  Sudoers already configured for agent privileges (skipped)"
    step_result "sudoers" "skipped"
else
    echo "  Setting up sudoers for passwordless systemctl/journalctl/reboot/shutdown..."
    # Use visudo -c to validate syntax before writing
    echo "\$SUDOERS_CONTENT" > /tmp/pragati-sudoers-test
    if visudo -c -f /tmp/pragati-sudoers-test 2>/dev/null; then
        echo "\$SUDOERS_CONTENT" > "\$SUDOERS_FILE"
        chmod 440 "\$SUDOERS_FILE"
        rm -f /tmp/pragati-sudoers-test
        echo "  [OK] Created \$SUDOERS_FILE"
        step_result "sudoers" "applied"
    else
        rm -f /tmp/pragati-sudoers-test
        echo "  [FAIL] Sudoers syntax validation failed"
        step_result "sudoers" "failed" "syntax validation failed"
    fi
fi

########################################################################
# [${boot_opt_step}/${total_steps}] Boot optimization (disable unnecessary services)
########################################################################
echo ""
echo "[${boot_opt_step}/${total_steps}] Applying boot optimizations for headless RPi..."

boot_opt_applied=0
boot_opt_skipped=0

# 1. Disable cloud-init (~10s savings)
if [ -f /etc/cloud/cloud-init.disabled ]; then
    echo "  [OK] cloud-init already disabled (skipped)"
    boot_opt_skipped=\$((boot_opt_skipped + 1))
else
    touch /etc/cloud/cloud-init.disabled
    echo "  [OK] Created /etc/cloud/cloud-init.disabled"
    boot_opt_applied=\$((boot_opt_applied + 1))
fi
systemctl disable cloud-init.service cloud-init-local.service cloud-config.service cloud-final.service 2>/dev/null || true

# 2. Disable snapd (~15-25s savings)
if systemctl is-enabled snapd.service >/dev/null 2>&1; then
    systemctl disable snapd.service snapd.socket snapd.seeded.service 2>/dev/null || true
    echo "  [OK] Disabled snapd services"
    boot_opt_applied=\$((boot_opt_applied + 1))
else
    echo "  [OK] snapd already disabled (skipped)"
    boot_opt_skipped=\$((boot_opt_skipped + 1))
fi

# 3. NetworkManager-wait-online — DO NOT DISABLE
# On Ubuntu Desktop images, disabling this breaks networking after reboot.
# The ~7s savings is not worth the risk on these RPis.
echo "  [OK] NetworkManager-wait-online left enabled (required for Desktop images)"
boot_opt_skipped=\$((boot_opt_skipped + 1))

# 4. Disable unnecessary desktop/peripheral services (~10s savings)
_desktop_svcs="cups.service cups-browsed.service bluetooth.service avahi-daemon.service avahi-daemon.socket ModemManager.service power-profiles-daemon.service switcheroo-control.service colord.service"
_desktop_disabled=0
for _svc in \$_desktop_svcs; do
    if systemctl is-enabled "\$_svc" >/dev/null 2>&1; then
        systemctl disable "\$_svc" 2>/dev/null || true
        _desktop_disabled=\$((_desktop_disabled + 1))
    fi
done
if [ "\$_desktop_disabled" -gt 0 ]; then
    echo "  [OK] Disabled \${_desktop_disabled} desktop/peripheral services"
    boot_opt_applied=\$((boot_opt_applied + 1))
else
    echo "  [OK] Desktop/peripheral services already disabled (skipped)"
    boot_opt_skipped=\$((boot_opt_skipped + 1))
fi

# 5. Default target — DO NOT switch to multi-user.target
# On Ubuntu Desktop images, graphical.target pulls in NetworkManager.service.
# Switching to multi-user.target kills networking on headless RPis.
# These RPis use Desktop images despite being headless.
echo "  [OK] Default target left as-is (graphical.target required for networking)"
boot_opt_skipped=\$((boot_opt_skipped + 1))

# 6. Disable can_watchdog.service if it exists (non-template instance)
# Note: can-watchdog@can0.service (template) is managed in service_install step
if systemctl list-unit-files can_watchdog.service >/dev/null 2>&1 && \
   systemctl is-enabled can_watchdog.service >/dev/null 2>&1; then
    systemctl disable can_watchdog.service 2>/dev/null || true
    echo "  [OK] Disabled can_watchdog.service"
    boot_opt_applied=\$((boot_opt_applied + 1))
fi

# Note: plymouth splash is removed from cmdline.txt on arm RPis in the service_install step below

if [ "\$boot_opt_applied" -gt 0 ]; then
    echo "  Boot optimization: \${boot_opt_applied} applied, \${boot_opt_skipped} already configured"
    step_result "boot_optimization" "applied" "applied:\${boot_opt_applied},skipped:\${boot_opt_skipped}"
else
    echo "  Boot optimization: all \${boot_opt_skipped} items already configured"
    step_result "boot_optimization" "skipped" "all \${boot_opt_skipped} items already configured"
fi

########################################################################
# [${hostname_step}/${total_steps}] Set unique hostname
########################################################################
echo ""
echo "[${hostname_step}/${total_steps}] Checking hostname..."

TARGET_HOSTNAME="${target_hostname}"
if [ -n "\$TARGET_HOSTNAME" ]; then
    CURRENT_HOSTNAME=\$(hostname 2>/dev/null || echo "unknown")
    if [ "\$CURRENT_HOSTNAME" = "\$TARGET_HOSTNAME" ]; then
        echo "  Hostname already set to \${TARGET_HOSTNAME} (skipped)"
        step_result "hostname" "skipped" "already:\${TARGET_HOSTNAME}"
    else
        hostnamectl set-hostname "\$TARGET_HOSTNAME" 2>/dev/null || true
        # Also update /etc/hosts to avoid sudo warnings
        if grep -q "127.0.1.1" /etc/hosts 2>/dev/null; then
            sed -i "s/127.0.1.1.*/127.0.1.1\t\${TARGET_HOSTNAME}/" /etc/hosts
        else
            echo "127.0.1.1\t\${TARGET_HOSTNAME}" >> /etc/hosts
        fi
        echo "  Hostname set: \${CURRENT_HOSTNAME} -> \${TARGET_HOSTNAME}"
        step_result "hostname" "applied" "was:\${CURRENT_HOSTNAME},now:\${TARGET_HOSTNAME}"
    fi
else
    echo "  [WARN] No hostname mapping for this IP -- skipping"
    echo "  Known mappings: 192.168.137.12=pragati-arm1, 192.168.137.238=pragati-arm2, 192.168.137.203=pragati-vehicle"
    step_result "hostname" "skipped" "no mapping for IP"
fi

########################################################################
# [${config_txt_step}/${total_steps}] config.txt CAN dtoverlay management
########################################################################
echo ""
echo "[${config_txt_step}/${total_steps}] Checking config.txt CAN dtoverlay..."

CAN_DTOVERLAY="dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25,spimaxfrequency=1000000"
CONFIG_TXT="/boot/firmware/config.txt"
has_spi=false
has_dtoverlay=false
dtoverlay_correct=false

# Detect CAN HAT via SPI device presence
if ls /dev/spidev* >/dev/null 2>&1; then
    has_spi=true
fi

# Check current config.txt for mcp2515-can0 dtoverlay
if [ -f "\$CONFIG_TXT" ]; then
    # Match any uncommented dtoverlay=mcp2515-can0 line
    if grep -q "^dtoverlay=mcp2515-can0" "\$CONFIG_TXT" 2>/dev/null; then
        has_dtoverlay=true
        # Verify exact parameters
        if grep -q "^\${CAN_DTOVERLAY}\$" "\$CONFIG_TXT" 2>/dev/null; then
            dtoverlay_correct=true
        fi
    fi
fi

if [ "\$has_spi" = true ] && [ "\$has_dtoverlay" = true ] && [ "\$dtoverlay_correct" = true ]; then
    echo "  CAN dtoverlay already correct in config.txt"
    step_result "config_txt_can" "skipped" "dtoverlay present and correct"
elif [ "\$has_spi" = false ] && [ "\$has_dtoverlay" = false ]; then
    echo "  No CAN HAT detected and no dtoverlay configured (OK)"
    step_result "config_txt_can" "skipped" "no CAN HAT, no dtoverlay"
elif [ "\$has_spi" = true ] && [ "\$has_dtoverlay" = false ]; then
    echo "  [WARN] CAN HAT detected (SPI present) but dtoverlay missing from config.txt"
    echo "  Proposed: add '\${CAN_DTOVERLAY}' to \${CONFIG_TXT}"
    config_apply=false
    read -p "  Apply config.txt change? [y/N] " config_confirm < /dev/tty || config_confirm="n"
    if [ "\$config_confirm" = "y" ] || [ "\$config_confirm" = "Y" ]; then
        echo "" >> "\$CONFIG_TXT"
        echo "# CAN HAT (MCP2515) - added by sync.sh provision" >> "\$CONFIG_TXT"
        echo "\${CAN_DTOVERLAY}" >> "\$CONFIG_TXT"
        echo "  [OK] Added CAN dtoverlay to config.txt"
        echo "  [WARN] REBOOT REQUIRED for dtoverlay change to take effect"
        config_apply=true
    else
        echo "  Skipped (operator declined)"
    fi
    if [ "\$config_apply" = true ]; then
        step_result "config_txt_can" "applied" "added dtoverlay, reboot required"
    else
        step_result "config_txt_can" "skipped" "operator declined"
    fi
elif [ "\$has_spi" = true ] && [ "\$has_dtoverlay" = true ] && [ "\$dtoverlay_correct" = false ]; then
    echo "  [WARN] CAN dtoverlay present but parameters are wrong"
    current_line=\$(grep "^dtoverlay=mcp2515-can0" "\$CONFIG_TXT" 2>/dev/null | head -1)
    echo "  Current:  \${current_line}"
    echo "  Expected: \${CAN_DTOVERLAY}"
    config_apply=false
    read -p "  Replace with correct parameters? [y/N] " config_confirm < /dev/tty || config_confirm="n"
    if [ "\$config_confirm" = "y" ] || [ "\$config_confirm" = "Y" ]; then
        sed -i "s|^dtoverlay=mcp2515-can0.*|\${CAN_DTOVERLAY}|" "\$CONFIG_TXT"
        echo "  [OK] Updated CAN dtoverlay parameters in config.txt"
        echo "  [WARN] REBOOT REQUIRED for dtoverlay change to take effect"
        config_apply=true
    else
        echo "  Skipped (operator declined)"
    fi
    if [ "\$config_apply" = true ]; then
        step_result "config_txt_can" "applied" "fixed dtoverlay params, reboot required"
    else
        step_result "config_txt_can" "skipped" "operator declined"
    fi
elif [ "\$has_spi" = false ] && [ "\$has_dtoverlay" = true ]; then
    echo "  [WARN] CAN dtoverlay present in config.txt but no CAN HAT detected (no SPI device)"
    echo "  Proposed: comment out dtoverlay line in \${CONFIG_TXT}"
    config_apply=false
    read -p "  Comment out dtoverlay? [y/N] " config_confirm < /dev/tty || config_confirm="n"
    if [ "\$config_confirm" = "y" ] || [ "\$config_confirm" = "Y" ]; then
        sed -i "s|^dtoverlay=mcp2515-can0|# dtoverlay=mcp2515-can0|" "\$CONFIG_TXT"
        echo "  [OK] Commented out CAN dtoverlay in config.txt"
        echo "  [WARN] REBOOT REQUIRED for dtoverlay change to take effect"
        config_apply=true
    else
        echo "  Skipped (operator declined)"
    fi
    if [ "\$config_apply" = true ]; then
        step_result "config_txt_can" "applied" "commented out dtoverlay, reboot required"
    else
        step_result "config_txt_can" "skipped" "operator declined"
    fi
else
    echo "  [WARN] Unexpected config.txt state -- skipping"
    step_result "config_txt_can" "skipped" "unexpected state"
fi

# Clean up any leftover dtoverlay=disable-bt lines from earlier experiments.
# The overlay caused WiFi boot regression; bluetooth.service is disabled at
# systemd level instead (boot optimization step).
if [ -f "\$CONFIG_TXT" ] && grep -q "^dtoverlay=disable-bt" "\$CONFIG_TXT" 2>/dev/null; then
    disable_bt_count=\$(grep -c "^dtoverlay=disable-bt" "\$CONFIG_TXT" 2>/dev/null || echo "0")
    echo "  [CLEANUP] Removing ${disable_bt_count} dtoverlay=disable-bt line(s) from config.txt"
    sed -i '/^dtoverlay=disable-bt/d' "\$CONFIG_TXT"
    echo "  [OK] Removed disable-bt overlay (caused WiFi boot regression). Reboot required."
fi

########################################################################
# [${total_steps}/${total_steps}] Service installation
########################################################################
echo ""
echo "[${total_steps}/${total_steps}] Installing systemd services (role: \${ROLE})..."

svc_install_ok=0
svc_install_fail=0
svc_install_skipped=0
needs_daemon_reload=false
svc_errors=""

try_install_service() {
    local svc_file="\$1"
    local svc_name="\$2"
    local src="\${SVC_SRC}/\${svc_file}"
    local dest="/etc/systemd/system/\${svc_file}"

    if [ ! -f "\$src" ]; then
        echo "  [WARN] Service file not found: \$src"
        svc_install_fail=\$((svc_install_fail + 1))
        svc_errors="\${svc_errors}\n  - \${svc_name}: source file missing"
        return 1
    fi

    # Skip copy if installed file is identical
    if [ -f "\$dest" ] && cmp -s "\$src" "\$dest"; then
        echo "  [OK] \$svc_file already installed (skipped)"
        svc_install_skipped=\$((svc_install_skipped + 1))
        return 0
    fi

    if cp "\$src" /etc/systemd/system/ 2>&1; then
        echo "  [OK] Copied \$svc_file to /etc/systemd/system/"
        needs_daemon_reload=true
    else
        echo "  [FAIL] Could not copy \$svc_file"
        svc_install_fail=\$((svc_install_fail + 1))
        svc_errors="\${svc_errors}\n  - \${svc_name}: copy failed"
        return 1
    fi
    return 0
}

try_enable_service() {
    local svc_name="\$1"
    if systemctl is-enabled "\$svc_name" >/dev/null 2>&1 && \
       systemctl is-active "\$svc_name" >/dev/null 2>&1; then
        echo "  [OK] \$svc_name already enabled and active (skipped)"
        svc_install_ok=\$((svc_install_ok + 1))
        svc_install_skipped=\$((svc_install_skipped + 1))
        return 0
    fi
    if systemctl enable --now "\$svc_name" 2>&1; then
        echo "  [OK] Enabled and started: \$svc_name"
        svc_install_ok=\$((svc_install_ok + 1))
    else
        echo "  [FAIL] Could not enable: \$svc_name"
        svc_install_fail=\$((svc_install_fail + 1))
        svc_errors="\${svc_errors}\n  - \${svc_name}: enable/start failed"
    fi
}

# Copy can_watchdog.sh script (required by can-watchdog@.service ConditionPathExists)
CAN_WATCHDOG_SRC="\${TMP_DIR}/can_watchdog.sh"
if [ -f "\$CAN_WATCHDOG_SRC" ]; then
    if [ -f /usr/local/sbin/can_watchdog.sh ] && cmp -s "\$CAN_WATCHDOG_SRC" /usr/local/sbin/can_watchdog.sh; then
        echo "  [OK] can_watchdog.sh already installed (skipped)"
        svc_install_skipped=\$((svc_install_skipped + 1))
    elif cp "\$CAN_WATCHDOG_SRC" /usr/local/sbin/can_watchdog.sh && \
       chmod +x /usr/local/sbin/can_watchdog.sh; then
        echo "  [OK] Copied can_watchdog.sh to /usr/local/sbin/"
    else
        echo "  [FAIL] Could not copy can_watchdog.sh"
        svc_install_fail=\$((svc_install_fail + 1))
        svc_errors="\${svc_errors}\n  - can_watchdog.sh: copy failed"
    fi
else
    echo "  [WARN] can_watchdog.sh not found at \$CAN_WATCHDOG_SRC"
fi

# NOTE: wifi-watchdog disabled — was interfering with NM autoconnect.
# Copy wifi_watchdog.sh script (required by wifi-watchdog.service ConditionPathExists)
# WIFI_WATCHDOG_SRC="\${TMP_DIR}/wifi_watchdog.sh"
# Provisioning now stops and disables wifi-watchdog if found running.
if systemctl is-active --quiet wifi-watchdog.service 2>/dev/null; then
    echo "  [CLEANUP] Stopping wifi-watchdog.service (disabled — NM autoconnect is sufficient)"
    systemctl stop wifi-watchdog.service 2>/dev/null || true
    systemctl disable wifi-watchdog.service 2>/dev/null || true
    echo "  [OK] wifi-watchdog stopped and disabled"
fi

# Configure NM WiFi connections for robust auto-reconnect
# Sets infinite retries and high priority on all saved WiFi connections.
# Without this, NM uses default limited retries and may give up reconnecting
# after a hotspot restart or brcmfmac driver reload.
echo "  Configuring WiFi auto-reconnect (NM connection settings)..."
_wifi_conns_configured=0
for _conn in \$(nmcli -t -f NAME,TYPE con show 2>/dev/null | grep ':.*wireless' | cut -d: -f1); do
    if [ -n "\$_conn" ]; then
        nmcli connection modify "\$_conn" connection.autoconnect yes 2>/dev/null || true
        nmcli connection modify "\$_conn" connection.autoconnect-retries 0 2>/dev/null || true
        nmcli connection modify "\$_conn" connection.autoconnect-priority 100 2>/dev/null || true
        _wifi_conns_configured=\$((_wifi_conns_configured + 1))
    fi
done
if [ "\$_wifi_conns_configured" -gt 0 ]; then
    echo "  [OK] Configured \${_wifi_conns_configured} WiFi connection(s) for infinite auto-reconnect"
else
    echo "  [WARN] No saved WiFi connections found to configure"
fi

# Copy boot_timing_capture.sh script (required by boot_timing.service ExecStart)
BOOT_TIMING_SRC="\${TMP_DIR}/boot_timing_capture.sh"
if [ -f "\$BOOT_TIMING_SRC" ]; then
    if [ -f /usr/local/sbin/boot_timing_capture.sh ] && cmp -s "\$BOOT_TIMING_SRC" /usr/local/sbin/boot_timing_capture.sh; then
        echo "  [OK] boot_timing_capture.sh already installed (skipped)"
        svc_install_skipped=\$((svc_install_skipped + 1))
    elif cp "\$BOOT_TIMING_SRC" /usr/local/sbin/boot_timing_capture.sh && \
       chmod +x /usr/local/sbin/boot_timing_capture.sh; then
        echo "  [OK] Copied boot_timing_capture.sh to /usr/local/sbin/"
    else
        echo "  [FAIL] Could not copy boot_timing_capture.sh"
        svc_install_fail=\$((svc_install_fail + 1))
        svc_errors="\${svc_errors}\n  - boot_timing_capture.sh: copy failed"
    fi
else
    echo "  [WARN] boot_timing_capture.sh not found at \$BOOT_TIMING_SRC"
fi

# Fix GPIO udev rule — GROUP needs = (assignment), not == (match)
# Fixes journal error: '99-gpio.rules:1 Invalid operator for GROUP'
GPIO_RULES="/etc/udev/rules.d/99-gpio.rules"
CORRECT_RULE='SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"'
if [ -f "\$GPIO_RULES" ] && grep -q 'GROUP==' "\$GPIO_RULES"; then
    echo "\$CORRECT_RULE" > "\$GPIO_RULES"
    udevadm control --reload-rules 2>/dev/null || true
    echo "  [OK] Fixed 99-gpio.rules (GROUP== -> GROUP=)"
elif [ -f "\$GPIO_RULES" ]; then
    echo "  [OK] 99-gpio.rules already correct (skipped)"
else
    echo "\$CORRECT_RULE" > "\$GPIO_RULES"
    udevadm control --reload-rules 2>/dev/null || true
    echo "  [OK] Created 99-gpio.rules"
fi

# Common services
try_install_service "pigpiod.service" "pigpiod" || true
try_install_service "can-watchdog@.service" "can-watchdog" || true

# Role-specific services
if [ "\$ROLE" = "vehicle" ]; then
    try_install_service "vehicle_launch.service" "vehicle_launch" || true
else
    try_install_service "arm_launch.service" "arm_launch" || true
fi

# Field monitoring service (common to all roles)
try_install_service "field-monitor.service" "field-monitor" || true

# Boot timing capture (common to all roles — timer-activated oneshot)
try_install_service "boot_timing.service" "boot-timing" || true
try_install_service "boot_timing.timer" "boot-timing-timer" || true

# Web dashboard service (common to all roles — serves status UI on port 8090)
try_install_service "pragati-dashboard.service" "pragati-dashboard" || true

# RPi agent service (common to all roles — lightweight agent on port 8091)
try_install_service "pragati-agent.service" "pragati-agent" || true

# WiFi watchdog service (disabled — NM autoconnect handles recovery)
# try_install_service "wifi-watchdog.service" "wifi-watchdog" || true

# Daemon reload only if service files were actually copied
if [ "\$needs_daemon_reload" = true ]; then
    systemctl daemon-reload 2>&1 || echo "  [WARN] daemon-reload failed"
else
    echo "  [OK] No service files changed, daemon-reload skipped"
fi

# Enable common services
try_enable_service "pigpiod.service"
try_enable_service "can-watchdog@can0.service"
# wifi-watchdog disabled — NM autoconnect handles recovery
# try_enable_service "wifi-watchdog.service"

# Enable role-specific services
if [ "\$ROLE" = "vehicle" ]; then
    try_enable_service "vehicle_launch.service"

    # Enable and start mosquitto broker (vehicle only)
    try_enable_service "mosquitto.service"

    # Ensure mosquitto accepts external connections (v2.0+ defaults to localhost-only)
    if ss -tlnp 2>/dev/null | grep -q "0.0.0.0:1883"; then
        echo "  [OK] mosquitto already listening on all interfaces (skipped)"
    elif [ -f /etc/mosquitto/conf.d/external.conf ]; then
        echo "  [OK] mosquitto external.conf already exists (skipped)"
    else
        echo "  [INFO] Configuring mosquitto for external access..."
        printf 'listener 1883 0.0.0.0\nallow_anonymous true\n' > /etc/mosquitto/conf.d/external.conf
        systemctl restart mosquitto 2>/dev/null || true
        echo "  [OK] Created /etc/mosquitto/conf.d/external.conf and restarted mosquitto"
    fi

    # Verify mosquitto is listening on port 1883 (up to 10s timeout)
    echo "  [INFO] Verifying mosquitto port 1883..."
    mosquitto_up=false
    for _i in \$(seq 1 10); do
        if ss -tlnp 2>/dev/null | grep -q ":1883 "; then
            mosquitto_up=true
            break
        fi
        sleep 1
    done
    if [ "\$mosquitto_up" = true ]; then
        echo "  [OK] mosquitto listening on port 1883"
        svc_install_ok=\$((svc_install_ok + 1))
    else
        echo "  [FAIL] mosquitto not listening on port 1883 after 10s"
        svc_install_fail=\$((svc_install_fail + 1))
        svc_errors="\${svc_errors}\n  - mosquitto: port 1883 not open after 10s"
    fi
else
    try_enable_service "arm_launch.service"
fi

# Enable field-monitor.service (enable only, not start -- starts on next boot)
if systemctl is-enabled "field-monitor.service" >/dev/null 2>&1; then
    echo "  [OK] field-monitor.service already enabled (skipped)"
    svc_install_ok=\$((svc_install_ok + 1))
    svc_install_skipped=\$((svc_install_skipped + 1))
elif systemctl enable "field-monitor.service" 2>&1; then
    echo "  [OK] Enabled: field-monitor.service (will start on next boot)"
    svc_install_ok=\$((svc_install_ok + 1))
else
    echo "  [FAIL] Could not enable: field-monitor.service"
    svc_install_fail=\$((svc_install_fail + 1))
    svc_errors="\${svc_errors}\n  - field-monitor.service: enable failed"
fi

# Migrate boot_timing: disable old direct service, enable timer instead
if systemctl is-enabled "boot_timing.service" >/dev/null 2>&1; then
    systemctl disable "boot_timing.service" 2>&1 || true
    echo "  [OK] Disabled old boot_timing.service (replaced by timer)"
fi

# Enable boot_timing.timer (fires 60s after boot, triggers boot_timing.service)
if systemctl is-enabled "boot_timing.timer" >/dev/null 2>&1; then
    echo "  [OK] boot_timing.timer already enabled (skipped)"
    svc_install_ok=\$((svc_install_ok + 1))
    svc_install_skipped=\$((svc_install_skipped + 1))
elif systemctl enable "boot_timing.timer" 2>&1; then
    echo "  [OK] Enabled: boot_timing.timer (will capture timing 60s after boot)"
    svc_install_ok=\$((svc_install_ok + 1))
else
    echo "  [FAIL] Could not enable: boot_timing.timer"
    svc_install_fail=\$((svc_install_fail + 1))
    svc_errors="\${svc_errors}\n  - boot_timing.timer: enable failed"
fi

# Enable pragati-dashboard.service (enable + start now — dashboard should be up immediately)
if systemctl is-enabled "pragati-dashboard.service" >/dev/null 2>&1; then
    echo "  [OK] pragati-dashboard.service already enabled (skipped)"
    svc_install_ok=\$((svc_install_ok + 1))
    svc_install_skipped=\$((svc_install_skipped + 1))
elif systemctl enable --now "pragati-dashboard.service" 2>&1; then
    echo "  [OK] Enabled + started: pragati-dashboard.service (port 8090)"
    svc_install_ok=\$((svc_install_ok + 1))
else
    echo "  [FAIL] Could not enable: pragati-dashboard.service"
    svc_install_fail=\$((svc_install_fail + 1))
    svc_errors="\${svc_errors}\n  - pragati-dashboard.service: enable failed"
fi

# Enable pragati-agent.service (enable + start now — agent should be up immediately)
if systemctl is-enabled "pragati-agent.service" >/dev/null 2>&1; then
    echo "  [OK] pragati-agent.service already enabled (skipped)"
    svc_install_ok=\$((svc_install_ok + 1))
    svc_install_skipped=\$((svc_install_skipped + 1))
elif systemctl enable --now "pragati-agent.service" 2>&1; then
    echo "  [OK] Enabled + started: pragati-agent.service (port 8091)"
    svc_install_ok=\$((svc_install_ok + 1))
else
    echo "  [FAIL] Could not enable: pragati-agent.service"
    svc_install_fail=\$((svc_install_fail + 1))
    svc_errors="\${svc_errors}\n  - pragati-agent.service: enable failed"
fi

# Remove 'splash' from kernel cmdline on ALL RPis.
# plymouth-start has ConditionKernelCommandLine=splash — without it, the entire
# plymouth chain (start, quit, quit-wait) is skipped cleanly.  On headless RPis
# plymouth-quit-wait hangs permanently; on vehicle it adds ~18.5s to boot even
# with a monitor.  Removing splash saves boot time on all targets.
CMDLINE_FILE="/boot/firmware/cmdline.txt"
if [ -f "\$CMDLINE_FILE" ]; then
    if grep -q '\\bsplash\\b' "\$CMDLINE_FILE"; then
        sed -i 's/ splash//' "\$CMDLINE_FILE"
        echo "  [OK] Removed 'splash' from \$CMDLINE_FILE (prevents plymouth boot delay)"
    else
        echo "  [OK] 'splash' already absent from \$CMDLINE_FILE (skipped)"
    fi
else
    echo "  [WARN] \$CMDLINE_FILE not found — cannot check splash"
fi

# Emit structured service install summary
if [ "\$svc_install_fail" -gt 0 ]; then
    step_result "service_install" "failed" "ok:\${svc_install_ok},fail:\${svc_install_fail},skip:\${svc_install_skipped}"
else
    if [ "\$svc_install_skipped" -eq "\$((svc_install_ok + svc_install_skipped))" ] 2>/dev/null && \
       [ "\$svc_install_ok" -eq 0 ] 2>/dev/null; then
        step_result "service_install" "skipped" "all \${svc_install_skipped} services unchanged"
    else
        step_result "service_install" "applied" "ok:\${svc_install_ok},skip:\${svc_install_skipped}"
    fi
fi

echo ""
echo "PROVISION_SCRIPT_DONE"
PROVISION_SCRIPT

    # --- Execute consolidated provision script with single sudo call ---
    # One SSH session, one sudo password prompt for all provision steps.
    log_step "Executing provision script on RPi (single sudo session)..."
    local prov_exec_ok=true
    smart_ssh -t "${RPI_USER}@${RPI_IP}" \
        "sudo bash ${prov_script_remote} 2>&1 | tee ${prov_results_remote}" 2>&1 || prov_exec_ok=false

    # --- Parse structured output for per-step pass/fail/skip ---
    local prov_output
    prov_output=$(smart_ssh "${RPI_USER}@${RPI_IP}" "cat ${prov_results_remote} 2>/dev/null" 2>&1)
    local prov_output_clean
    prov_output_clean=$(echo "$prov_output" | tr -d '\r')

    # Parse STEP_RESULT lines: STEP_RESULT:step_name:status[:detail]
    local step_name step_status step_detail
    local applied_steps="" skipped_steps="" failed_steps=""
    while IFS=: read -r _marker step_name step_status step_detail; do
        case "$step_status" in
            applied)
                provision_ok=$((provision_ok + 1))
                applied_steps="${applied_steps} ${step_name}"
                ;;
            skipped)
                provision_ok=$((provision_ok + 1))
                provision_skipped=$((provision_skipped + 1))
                skipped_steps="${skipped_steps} ${step_name}"
                ;;
            failed)
                provision_fail=$((provision_fail + 1))
                failed_steps="${failed_steps} ${step_name}"
                provision_errors="${provision_errors}\n  - ${step_name}: ${step_detail:-unknown error}"
                ;;
        esac
    done <<< "$(echo "$prov_output_clean" | grep "^STEP_RESULT:")"

    # Print per-step summary
    echo ""
    log_step "Provision step results:"
    if [ -n "$applied_steps" ]; then
        log_success "Applied:${applied_steps}"
    fi
    if [ -n "$skipped_steps" ]; then
        log_info "Skipped:${skipped_steps}"
    fi
    if [ -n "$failed_steps" ]; then
        log_warn "Failed:${failed_steps}"
    fi

    # Check if the script completed (look for PROVISION_SCRIPT_DONE marker)
    if ! echo "$prov_output_clean" | grep -q "^PROVISION_SCRIPT_DONE$"; then
        if [ "$prov_exec_ok" = false ]; then
            log_warn "Provision script did not complete (set -e may have aborted early)"
            provision_fail=$((provision_fail + 1))
            provision_errors="${provision_errors}\n  - Provision script aborted before completion"
        fi
    fi

    # --- Clean up temp files on RPi ---
    # On success: remove temp dir. On failure: leave for inspection.
    if [ "$provision_fail" -eq 0 ]; then
        smart_ssh "${RPI_USER}@${RPI_IP}" "rm -rf ${prov_tmp_dir}" 2>&1 || true
        log_info "Cleaned up temp provision files on RPi"
    else
        log_warn "Temp provision files left on RPi for inspection: ${prov_tmp_dir}"
    fi

    # --- Dashboard role configuration (all roles) ---
    # Set the 'role' field in web_dashboard/config/dashboard.yaml so the dashboard
    # shows the correct tabs for this RPi's role (vehicle, arm, or dev).
    # Also disable fleet polling on non-dev dashboards (only dev PC polls the fleet).
    log_step "Configuring dashboard role (${role})..."
    local dash_role_script="/tmp/.pragati_dash_role_$$.sh"
    smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${dash_role_script}" << DASHROLE_CONTENT
set -e
DASH_CONFIG="\$HOME/pragati_ros2/web_dashboard/config/dashboard.yaml"
if [ -f "\$DASH_CONFIG" ]; then
    # Set role field (first occurrence of 'role:' at top level)
    sed -i 's/^role: .*/role: ${role}/' "\$DASH_CONFIG"
    echo "Set dashboard role to '${role}' in \$DASH_CONFIG"
else
    echo "Dashboard config not found at \$DASH_CONFIG (deploy web_dashboard first)"
    exit 1
fi
DASHROLE_CONTENT

    if smart_ssh -t "${RPI_USER}@${RPI_IP}" "bash ${dash_role_script}; rm -f ${dash_role_script}" 2>&1
    then
        provision_ok=$((provision_ok + 1))
        log_success "Dashboard role set to '${role}'"
    else
        provision_fail=$((provision_fail + 1))
        provision_errors="${provision_errors}\n  - Dashboard role config failed (deploy web_dashboard first)"
        log_warn "Dashboard role config failed (continuing)"
    fi

    # --- Arm identity configuration (arm role only) ---
    # Write /etc/default/pragati-arm so arm_launch.service knows its ARM_ID, MQTT_ADDRESS,
    # ROS_DOMAIN_ID, and ROS_LOCALHOST_ONLY.
    # Only written when --arm-id is explicitly specified; never overwrites on vehicle role.
    if [ "$role" = "arm" ] && [ -n "$ARM_ID" ]; then
        log_step "Writing arm identity config (/etc/default/pragati-arm)..."

        local arm_id_val="$ARM_ID"
        # Preserve existing MQTT_ADDRESS from the RPi if --mqtt-address was not passed.
        # This prevents --provision from silently reverting a previously-configured address.
        local arm_mqtt=""
        if [ -n "$MQTT_ADDRESS_OVERRIDE" ]; then
            arm_mqtt="$MQTT_ADDRESS_OVERRIDE"
        else
            # Try to read existing value from the RPi
            local existing_mqtt
            existing_mqtt=$(smart_ssh "${RPI_USER}@${RPI_IP}" \
                "grep -s '^MQTT_ADDRESS=' /etc/default/pragati-arm 2>/dev/null | cut -d= -f2" \
                2>/dev/null) || true
            existing_mqtt=$(echo "$existing_mqtt" | tr -d '\r' | xargs)  # strip whitespace + \r
            if [ -n "$existing_mqtt" ]; then
                arm_mqtt="$existing_mqtt"
                log_info "Preserving existing MQTT_ADDRESS=${arm_mqtt} from /etc/default/pragati-arm"
            else
                arm_mqtt="10.42.0.10"
                log_warn "No existing MQTT_ADDRESS found — using default ${arm_mqtt}"
                log_warn "  Set explicitly: ./sync.sh --provision --mqtt-address <VEHICLE_IP> --arm-id ${arm_id_val} --ip ${RPI_IP}"
            fi
        fi
        # Derive ROS_DOMAIN_ID from arm number: arm1→1, arm2→2, ..., armN→N.
        # Each arm gets its own domain to prevent cross-arm topic interference.
        local arm_num="${arm_id_val##arm}"
        local domain_id="${arm_num:-0}"

        # Write arm identity via temp file approach (avoids heredoc+TTY conflict)
        local arm_id_script="/tmp/.pragati_arm_id_$$.sh"
        smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${arm_id_script}" << ARMID_CONTENT
set -e
cat > /etc/default/pragati-arm << 'ARMEOF'
# Pragati arm identity -- written by sync.sh --provision --arm-id ${arm_id_val}
# To change: re-run sync.sh --provision --arm-id <arm_id>
ARM_ID=${arm_id_val}
MQTT_ADDRESS=${arm_mqtt}
ROS_DOMAIN_ID=${domain_id}
ROS_LOCALHOST_ONLY=1
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# CycloneDDS shared-memory (iceoryx) is broken on RPi 4B / ARM64.
# This config disables iceoryx and forces loopback UDP for DDS discovery.
CYCLONEDDS_URI=file:///home/ubuntu/pragati_ros2/config/cyclonedds.xml
ARMEOF
chmod 644 /etc/default/pragati-arm
echo "Written /etc/default/pragati-arm: ARM_ID=${arm_id_val} MQTT=${arm_mqtt} ROS_DOMAIN_ID=${domain_id} ROS_LOCALHOST_ONLY=1 RMW=cyclonedds CYCLONEDDS_URI=set"
ARMID_CONTENT

        if smart_ssh -t "${RPI_USER}@${RPI_IP}" "sudo bash ${arm_id_script}; rm -f ${arm_id_script}" 2>&1
        then
            provision_ok=$((provision_ok + 1))
            log_success "Arm identity set: ARM_ID=${arm_id_val}, MQTT=${arm_mqtt}, ROS_DOMAIN_ID=${domain_id}, ROS_LOCALHOST_ONLY=1, RMW=cyclonedds"

            # Restart arm_launch.service so it re-reads the identity file.
            # The service was started by enable --now (earlier in provisioning) before
            # this identity file existed, so it's running with hardcoded defaults.
            if smart_ssh -t "${RPI_USER}@${RPI_IP}" "sudo systemctl restart arm_launch.service" 2>&1; then
                log_success "arm_launch.service restarted with new identity"
            else
                log_warn "arm_launch.service restart failed (service may need manual restart)"
            fi
        else
            provision_fail=$((provision_fail + 1))
            provision_errors="${provision_errors}\n  - Arm identity config write failed"
            log_warn "Arm identity config write failed (continuing)"
        fi

        # Patch ~/.bashrc to source arm identity instead of hardcoded ROS env vars.
        # This ensures manual SSH sessions match the systemd auto-launch environment.
        log_step "Patching ~/.bashrc to source arm identity..."
        if smart_ssh "${RPI_USER}@${RPI_IP}" 'bash -s' << 'BASHRC_ID_PATCH'
# Remove any hardcoded ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY, and RMW_IMPLEMENTATION lines
# (now managed via /etc/default/pragati-arm)
sed -i '/^export ROS_DOMAIN_ID=/d' ~/.bashrc
sed -i '/^export ROS_LOCALHOST_ONLY=/d' ~/.bashrc
sed -i '/^export RMW_IMPLEMENTATION=/d' ~/.bashrc

# Add sourcing of /etc/default/pragati-arm (if not already present)
if ! grep -q '/etc/default/pragati-arm' ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati arm identity (managed by sync.sh --provision)" >> ~/.bashrc
    echo "if [ -f /etc/default/pragati-arm ]; then" >> ~/.bashrc
    echo "    set -a; source /etc/default/pragati-arm; set +a" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: /etc/default/pragati-arm sourcing to ~/.bashrc"
else
    echo "Already present: /etc/default/pragati-arm sourcing"
fi
BASHRC_ID_PATCH
        then
            log_success "~/.bashrc patched to source arm identity"
        else
            log_warn "~/.bashrc patch failed (non-critical -- manual SSH may use wrong domain)"
        fi
    elif [ "$role" = "arm" ] && [ -z "$ARM_ID" ]; then
        log_warn "No --arm-id specified -- /etc/default/pragati-arm not written."
        log_warn "  Arm will default to ARM_ID=arm1, ROS_DOMAIN_ID=0 at boot."
        log_warn "  To configure: ./sync.sh --provision --arm-id arm2 --ip ${RPI_IP}"
    fi

    # Write /etc/default/pragati-vehicle so vehicle_launch.service, pragati-dashboard,
    # and pragati-agent all share the same ROS2 env (domain, DDS config).
    # Vehicle always uses ROS_DOMAIN_ID=0 and ROS_LOCALHOST_ONLY=0 (needs network comms with arms).
    if [ "$role" = "vehicle" ]; then
        log_step "Writing vehicle identity config (/etc/default/pragati-vehicle)..."
        local veh_id_script="/tmp/.pragati_veh_id_$$.sh"
        smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${veh_id_script}" << VEH_ID_CONTENT
set -e
cat > /etc/default/pragati-vehicle << 'VEHEOF'
# Pragati vehicle identity -- written by sync.sh --provision
# To regenerate: re-run sync.sh --provision --role vehicle --ip <IP>
ROS_DOMAIN_ID=0
ROS_LOCALHOST_ONLY=0
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# CycloneDDS shared-memory (iceoryx) is broken on RPi 4B / ARM64.
# This config disables iceoryx and forces UDP for DDS discovery.
CYCLONEDDS_URI=file:///home/ubuntu/pragati_ros2/config/cyclonedds.xml
VEHEOF
chmod 644 /etc/default/pragati-vehicle
echo "Written /etc/default/pragati-vehicle: ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW=cyclonedds CYCLONEDDS_URI=set"
VEH_ID_CONTENT

        if smart_ssh -t "${RPI_USER}@${RPI_IP}" "sudo bash ${veh_id_script}; rm -f ${veh_id_script}" 2>&1
        then
            provision_ok=$((provision_ok + 1))
            log_success "Vehicle identity set: ROS_DOMAIN_ID=0, ROS_LOCALHOST_ONLY=0, RMW=cyclonedds, CYCLONEDDS_URI=set"

            # Restart vehicle services so they re-read the identity file.
            for svc in vehicle_launch.service pragati-dashboard.service pragati-agent.service; do
                if smart_ssh -t "${RPI_USER}@${RPI_IP}" "sudo systemctl restart ${svc}" 2>&1; then
                    log_success "${svc} restarted with new identity"
                else
                    log_warn "${svc} restart failed (may need manual restart)"
                fi
            done
        else
            provision_fail=$((provision_fail + 1))
            provision_errors="${provision_errors}\n  - Vehicle identity config write failed"
            log_warn "Vehicle identity config write failed (continuing)"
        fi

        # Patch ~/.bashrc to source vehicle identity for interactive SSH sessions.
        log_step "Patching ~/.bashrc to source vehicle identity..."
        if smart_ssh "${RPI_USER}@${RPI_IP}" 'bash -s' << 'BASHRC_VEH_PATCH'
sed -i '/^export ROS_DOMAIN_ID=/d' ~/.bashrc
sed -i '/^export ROS_LOCALHOST_ONLY=/d' ~/.bashrc
sed -i '/^export RMW_IMPLEMENTATION=/d' ~/.bashrc
sed -i '/^export CYCLONEDDS_URI=/d' ~/.bashrc
if ! grep -q '/etc/default/pragati-vehicle' ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati vehicle identity (written by sync.sh --provision)" >> ~/.bashrc
    echo "if [ -f /etc/default/pragati-vehicle ]; then" >> ~/.bashrc
    echo "    set -a; source /etc/default/pragati-vehicle; set +a" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: /etc/default/pragati-vehicle sourcing to ~/.bashrc"
else
    echo "Already present: /etc/default/pragati-vehicle sourcing"
fi
BASHRC_VEH_PATCH
        then
            provision_ok=$((provision_ok + 1))
            log_success "~/.bashrc patched to source vehicle identity"
        else
            log_warn "~/.bashrc patch failed (non-critical -- manual SSH may use wrong domain)"
        fi
    fi

    # --- Summary ---

    local total=$((provision_ok + provision_fail))
    local provision_applied=$((provision_ok - provision_skipped))
    echo ""
    if [ "$provision_fail" -gt 0 ]; then
        echo -e "${BOLD}${RED}════════════════════════════════════════════════════════════════${NC}"
        echo -e "${BOLD}${RED}  ✗ PROVISIONING FAILED: ${provision_fail} of ${total} steps failed${NC}"
        echo -e "${BOLD}${RED}════════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "  ${GREEN}Succeeded: ${provision_ok}${NC}"
        echo -e "  ${RED}Failed:    ${provision_fail}${NC}"
        echo -e "${RED}${BOLD}  Errors:${NC}${provision_errors}"
    else
        echo -e "${BOLD}${GREEN}  Provisioning: ${provision_ok}/${total} steps succeeded${NC}"
    fi
    echo -e "  Provision complete: ${provision_applied} applied, ${provision_skipped} skipped"
    echo ""

    # Save provision log to RPi so evidence persists after terminal scrolls
    local provision_status="OK"
    [ "$provision_fail" -gt 0 ] && provision_status="FAILED"
    local provision_summary="Provision ${provision_status}: ${provision_ok}/${total} succeeded (${provision_applied} applied, ${provision_skipped} skipped)"
    [ -n "$provision_errors" ] && provision_summary="${provision_summary}  Errors:${provision_errors}"

    smart_ssh "${RPI_USER}@${RPI_IP}" "bash -s" << PROV_LOG_SCRIPT
mkdir -p ~/.pragati_provision_logs
cat > ~/.pragati_provision_logs/${provision_log_name} << 'PROV_INNER'
Provision Log
=============
Date:   $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Host:   ${RPI_IP}
Role:   ${role} (${role_source})
Result: ${provision_status} (${provision_ok}/${total} steps)
PROV_INNER
echo "" >> ~/.pragati_provision_logs/${provision_log_name}
echo "Steps:" >> ~/.pragati_provision_logs/${provision_log_name}
echo "  Succeeded: ${provision_ok}" >> ~/.pragati_provision_logs/${provision_log_name}
echo "  Failed:    ${provision_fail}" >> ~/.pragati_provision_logs/${provision_log_name}
echo "  Applied:   ${provision_applied}" >> ~/.pragati_provision_logs/${provision_log_name}
echo "  Skipped:   ${provision_skipped}" >> ~/.pragati_provision_logs/${provision_log_name}
PROV_LOG_SCRIPT
    log_info "Provision log saved: ~/.pragati_provision_logs/${provision_log_name}"

    [ "$provision_fail" -gt 0 ] && return 1
    return 0
}

# Run verification (read-only) on the current target RPi
run_verify() {
    local role
    role=$(detect_rpi_role)
    local role_source="auto-detected"
    [ -n "$RPI_ROLE" ] && role_source="explicit"

    echo ""
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Verification: ${RPI_USER}@${RPI_IP} (role: ${role}, ${role_source})${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""

    local verify_output
    local DEV_EPOCH_FOR_VERIFY
    DEV_EPOCH_FOR_VERIFY=$(date -u +%s)
    # The remote script emits lines in one of these formats:
    #   [OK]      description          -- deploy check passed
    #   [FAIL]    description          -- deploy check failed (counts toward failure)
    #   [WARN]    description          -- provisioning issue (informational, does not fail)
    #   [INFO]    description          -- provisioning item OK
    #   SECTION=<name>                 -- section header marker
    #   DEPLOY_SUMMARY=ok/total        -- deploy check counts
    #   PROV_SUMMARY=ok/total/warn     -- provisioning check counts
    verify_output=$(smart_ssh "${RPI_USER}@${RPI_IP}" "bash -s" << VERIFY_SCRIPT
deploy_ok=0
deploy_total=0
prov_ok=0
prov_total=0
prov_warn=0
ROLE="${role}"

# Deploy check: hard pass/fail (blocks deployment success)
deploy_check() {
    local description="\$1"
    local result="\$2"
    deploy_total=\$((deploy_total + 1))
    if [ "\$result" = "OK" ]; then
        echo "[OK]      \$description"
        deploy_ok=\$((deploy_ok + 1))
    else
        echo "[FAIL]    \$description"
    fi
}

# Provisioning check: informational (warn if missing, doesn't block)
# Optional 3rd arg: tag (e.g. "MISMATCH") for hardware/config mismatches
prov_check() {
    local description="\$1"
    local result="\$2"
    local tag="\${3:-}"
    prov_total=\$((prov_total + 1))
    if [ "\$result" = "OK" ]; then
        echo "[INFO]    \$description"
        prov_ok=\$((prov_ok + 1))
    elif [ -n "\$tag" ] && [ "\$tag" = "MISMATCH" ]; then
        echo "[MISMATCH] \$description"
        prov_warn=\$((prov_warn + 1))
    else
        echo "[WARN]    \$description"
        prov_warn=\$((prov_warn + 1))
    fi
}

# ══════════════════════════════════════════════════════════════
# SECTION 1: Deploy Health (hard failures = deploy didn't work)
# ══════════════════════════════════════════════════════════════
echo "SECTION=deploy"

# ROS2 Jazzy installed
if [ -f /opt/ros/jazzy/setup.bash ]; then
    deploy_check "ROS2 Jazzy installed" "OK"
else
    deploy_check "ROS2 Jazzy installed" "FAIL"
fi

# Workspace built (install/setup.bash exists)
if [ -f "\${HOME}/pragati_ros2/install/setup.bash" ]; then
    deploy_check "ROS2 workspace built (install/setup.bash)" "OK"
else
    deploy_check "ROS2 workspace built (install/setup.bash)" "FAIL"
fi

# CAN interface can0 exists
if ip link show can0 &>/dev/null; then
    deploy_check "CAN interface can0 exists" "OK"
else
    deploy_check "CAN interface can0 exists" "FAIL"
fi

# SPI device exists (required by CAN HAT)
if [ -e /dev/spidev0.1 ]; then
    deploy_check "SPI device /dev/spidev0.1 exists" "OK"
else
    deploy_check "SPI device /dev/spidev0.1 exists" "FAIL"
fi

# CAN watchdog service active
if systemctl is-active --quiet can-watchdog@can0.service 2>/dev/null; then
    deploy_check "CAN watchdog service active" "OK"
else
    deploy_check "CAN watchdog service active" "FAIL"
fi

# can_watchdog.sh script installed
if [ -x /usr/local/sbin/can_watchdog.sh ]; then
    deploy_check "can_watchdog.sh installed at /usr/local/sbin/" "OK"
else
    deploy_check "can_watchdog.sh installed at /usr/local/sbin/" "FAIL"
fi

# WiFi watchdog service (disabled — NM autoconnect handles recovery)
# if systemctl is-active --quiet wifi-watchdog.service 2>/dev/null; then
#     deploy_check "WiFi watchdog service active" "OK"
# else
#     deploy_check "WiFi watchdog service active" "FAIL"
# fi

# wifi_watchdog.sh script installed (disabled — kept in repo for future use)
# if [ -x /usr/local/sbin/wifi_watchdog.sh ]; then
#     deploy_check "wifi_watchdog.sh installed at /usr/local/sbin/" "OK"
# else
#     deploy_check "wifi_watchdog.sh installed at /usr/local/sbin/" "FAIL"
# fi

# pigpiod service active
if systemctl is-active --quiet pigpiod.service 2>/dev/null || \
   systemctl is-active --quiet pigpiod_custom.service 2>/dev/null; then
    deploy_check "pigpiod service active" "OK"
else
    deploy_check "pigpiod service active" "FAIL"
fi

# Role-specific launch service installed & enabled
if [ "\$ROLE" = "vehicle" ]; then
    svc_name="vehicle_launch.service"
else
    svc_name="arm_launch.service"
fi
if systemctl is-enabled --quiet "\$svc_name" 2>/dev/null; then
    deploy_check "\${svc_name} installed and enabled" "OK"
else
    deploy_check "\${svc_name} installed and enabled" "FAIL"
fi

# Mosquitto active (vehicle only)
if [ "\$ROLE" = "vehicle" ]; then
    if systemctl is-active --quiet mosquitto.service 2>/dev/null; then
        deploy_check "Mosquitto service active" "OK"
    else
        deploy_check "Mosquitto service active" "FAIL"
    fi
fi

# Disk space sufficient (>500MB free on /)
disk_avail_kb=\$(df / --output=avail 2>/dev/null | tail -1 | tr -d ' ')
if [ "\$disk_avail_kb" -gt 512000 ] 2>/dev/null; then
    disk_mb=\$((disk_avail_kb / 1024))
    deploy_check "Disk space available (\${disk_mb}MB free)" "OK"
else
    disk_mb=\$((disk_avail_kb / 1024))
    deploy_check "Disk space low (\${disk_mb}MB free, need >500MB)" "FAIL"
fi

# CPU temperature OK (<75C)
cpu_temp_raw=\$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "0")
cpu_temp=\$((cpu_temp_raw / 1000))
if [ "\$cpu_temp" -lt 75 ] 2>/dev/null; then
    deploy_check "CPU temperature OK (\${cpu_temp}C)" "OK"
else
    deploy_check "CPU temperature high (\${cpu_temp}C, threshold 75C)" "FAIL"
fi

# Clock drift from dev machine (<30s acceptable)
rpi_epoch=\$(date -u +%s 2>/dev/null || echo "0")
dev_epoch="${DEV_EPOCH_FOR_VERIFY}"
if [ "\$dev_epoch" -gt 0 ] 2>/dev/null && [ "\$rpi_epoch" -gt 0 ] 2>/dev/null; then
    clock_drift=\$(( rpi_epoch - dev_epoch ))
    # Absolute value
    [ "\$clock_drift" -lt 0 ] && clock_drift=\$(( -clock_drift ))
    if [ "\$clock_drift" -lt 30 ]; then
        deploy_check "Clock in sync with dev machine (\${clock_drift}s drift)" "OK"
    else
        deploy_check "Clock drift from dev machine (\${clock_drift}s off -- run sync without --no-time-sync)" "FAIL"
    fi
fi

# ── Deploy content checks (did the synced files actually land?) ──

# setup.bash content correct (no hardcoded /mnt/ or PC-local paths)
if [ -f "\${HOME}/pragati_ros2/install/setup.bash" ]; then
    if grep -q "/mnt/" "\${HOME}/pragati_ros2/install/setup.bash" 2>/dev/null; then
        deploy_check "setup.bash has correct paths (still contains /mnt/ -- path fix failed)" "FAIL"
    elif grep -q "COLCON_CURRENT_PREFIX" "\${HOME}/pragati_ros2/install/setup.bash" 2>/dev/null; then
        deploy_check "setup.bash has correct paths" "OK"
    else
        deploy_check "setup.bash content looks wrong (missing COLCON_CURRENT_PREFIX)" "FAIL"
    fi
fi

# Workspace has content (packages installed)
pkg_count=\$(find "\${HOME}/pragati_ros2/install/share" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)
if [ "\$pkg_count" -gt 0 ]; then
    deploy_check "Workspace has \${pkg_count} ROS2 packages installed" "OK"
else
    deploy_check "No ROS2 packages found in install/share/ -- workspace may be empty" "FAIL"
fi

# Binary architecture check (only if native binaries exist)
rpi_bin=\$(find "\${HOME}/pragati_ros2/install" \( -name "*.so" -o -name "*.so.*" \) -type f 2>/dev/null | head -1)
if [ -z "\$rpi_bin" ]; then
    # No .so files -- look for ELF executables
    rpi_bin=\$(find "\${HOME}/pragati_ros2/install/lib" -maxdepth 2 -type f -executable 2>/dev/null \
        | while read f; do file "\$f" 2>/dev/null | grep -q "ELF" && echo "\$f" && break; done)
fi
if [ -n "\$rpi_bin" ]; then
    bin_arch=\$(file "\$rpi_bin" 2>/dev/null | grep -o "ARM aarch64\|x86-64\|x86_64" | head -1)
    if [ "\$bin_arch" = "ARM aarch64" ]; then
        deploy_check "Native binaries are aarch64 (correct for RPi)" "OK"
    elif [ -n "\$bin_arch" ]; then
        deploy_check "Native binaries are \${bin_arch} (WRONG -- need aarch64 for RPi)" "FAIL"
    fi
    # If file output doesn't match either pattern, skip silently (unusual format)
fi
# If no native binaries at all (pure Python workspace), skip -- not an error

# scripts/ directory exists and non-empty
if [ -d "\${HOME}/pragati_ros2/scripts" ] && [ -n "\$(ls -A "\${HOME}/pragati_ros2/scripts" 2>/dev/null)" ]; then
    script_count=\$(ls -1 "\${HOME}/pragati_ros2/scripts" 2>/dev/null | wc -l)
    deploy_check "scripts/ synced (\${script_count} files)" "OK"
else
    deploy_check "scripts/ directory missing or empty" "FAIL"
fi

# launch/ directory exists
if [ -d "\${HOME}/pragati_ros2/launch" ] && [ -n "\$(ls -A "\${HOME}/pragati_ros2/launch" 2>/dev/null)" ]; then
    deploy_check "launch/ synced" "OK"
else
    deploy_check "launch/ directory missing or empty" "FAIL"
fi

# data/models/ (optional -- only check if models dir exists)
if [ -d "\${HOME}/pragati_ros2/data/models" ]; then
    blob_count=\$(ls -1 "\${HOME}/pragati_ros2/data/models/"*.blob 2>/dev/null | wc -l)
    if [ "\$blob_count" -gt 0 ]; then
        deploy_check "ML models present (\${blob_count} .blob files)" "OK"
    else
        deploy_check "data/models/ exists but no .blob files -- cotton detection will fail" "FAIL"
    fi
fi

# systemd/ service files synced
if [ -d "\${HOME}/pragati_ros2/systemd" ] && [ -n "\$(ls -A "\${HOME}/pragati_ros2/systemd" 2>/dev/null)" ]; then
    deploy_check "systemd/ service files synced" "OK"
else
    deploy_check "systemd/ directory missing or empty -- --provision will fail" "FAIL"
fi

# Root runtime files
if [ -f "\${HOME}/pragati_ros2/emergency_motor_stop.sh" ]; then
    deploy_check "emergency_motor_stop.sh present (safety critical)" "OK"
else
    deploy_check "emergency_motor_stop.sh MISSING (safety critical)" "FAIL"
fi
if [ -f "\${HOME}/pragati_ros2/sync.sh" ]; then
    deploy_check "sync.sh present on RPi" "OK"
else
    deploy_check "sync.sh missing on RPi" "FAIL"
fi
if [ -f "\${HOME}/pragati_ros2/setup_raspberry_pi.sh" ]; then
    deploy_check "setup_raspberry_pi.sh present" "OK"
else
    deploy_check "setup_raspberry_pi.sh missing" "FAIL"
fi

# ~/.bashrc has ROS2 sourcing
if grep -q "source /opt/ros/jazzy/setup.bash" "\${HOME}/.bashrc" 2>/dev/null; then
    deploy_check "~/.bashrc sources ROS2 Jazzy" "OK"
else
    deploy_check "~/.bashrc missing ROS2 sourcing -- interactive SSH won't have ROS2" "FAIL"
fi
if grep -q "source ~/pragati_ros2/install/setup.bash" "\${HOME}/.bashrc" 2>/dev/null; then
    deploy_check "~/.bashrc sources workspace" "OK"
else
    deploy_check "~/.bashrc missing workspace sourcing" "FAIL"
fi

# ══════════════════════════════════════════════════════════════
# SECTION 2: Provisioning Status (informational, won't block)
# ══════════════════════════════════════════════════════════════
echo "SECTION=provisioning"

# USB autosuspend
usb_autosuspend=\$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
if [ "\$usb_autosuspend" = "-1" ]; then
    prov_check "USB autosuspend disabled (autosuspend=-1)" "OK"
else
    prov_check "USB autosuspend not disabled (autosuspend=\$usb_autosuspend) -- run --provision to fix" "WARN"
fi

# USB kernel param in cmdline.txt
if grep -q "usbcore.autosuspend=-1" /boot/firmware/cmdline.txt 2>/dev/null; then
    prov_check "USB autosuspend kernel param in cmdline.txt" "OK"
else
    prov_check "USB autosuspend kernel param not in cmdline.txt -- run --provision to fix" "WARN"
fi

# SSH keepalive
if grep -q "^ClientAliveInterval" /etc/ssh/sshd_config.d/keepalive.conf 2>/dev/null; then
    prov_check "SSH keepalive configured" "OK"
elif grep -q "^ClientAliveInterval" /etc/ssh/sshd_config 2>/dev/null; then
    prov_check "SSH keepalive configured (in sshd_config)" "OK"
else
    prov_check "SSH keepalive not configured -- run --provision to fix" "WARN"
fi

# WiFi power save
if command -v iw &>/dev/null; then
    wifi_ps=\$(iw dev wlan0 get power_save 2>/dev/null | awk '{print \$NF}')
    if [ "\$wifi_ps" = "off" ]; then
        prov_check "WiFi power save disabled" "OK"
    elif [ -z "\$wifi_ps" ]; then
        # iw exists but wlan0 not found or no output
        if ip link show wlan0 &>/dev/null; then
            prov_check "WiFi power save status unknown (iw returned empty)" "WARN"
        else
            prov_check "WiFi power save (no wlan0 interface -- N/A)" "OK"
        fi
    else
        prov_check "WiFi power save not disabled (currently: \${wifi_ps}) -- run --provision to fix" "WARN"
    fi
else
    # iw not installed -- check if connected via WiFi at all
    if ip link show wlan0 &>/dev/null; then
        prov_check "WiFi power save unknown (iw not installed) -- apt install iw to check" "WARN"
    else
        prov_check "WiFi power save (no WiFi -- N/A)" "OK"
    fi
fi

# NOTE: dtoverlay=disable-bt prov_check removed — the overlay caused WiFi boot
# regression and was reverted. bluetooth.service disabled at systemd level is sufficient.
# But warn if it's still present (cleanup happens during --provision).
if [ -f /boot/firmware/config.txt ] && grep -q "^dtoverlay=disable-bt" /boot/firmware/config.txt 2>/dev/null; then
    prov_check "config.txt disable-bt overlay present (causes WiFi boot regression) -- run --provision to remove" "WARN"
fi

# OAK-D udev rules
if [ -f /etc/udev/rules.d/80-movidius.rules ]; then
    prov_check "OAK-D camera udev rules installed" "OK"
else
    prov_check "OAK-D camera udev rules not installed -- run --provision to fix" "WARN"
fi

# Role-specific launch service running (service may be enabled but stopped after deploy)
if [ "\$ROLE" = "vehicle" ]; then
    svc_name="vehicle_launch.service"
else
    svc_name="arm_launch.service"
fi
if systemctl is-active --quiet "\$svc_name" 2>/dev/null; then
    prov_check "\${svc_name} running" "OK"
else
    if systemctl is-enabled --quiet "\$svc_name" 2>/dev/null; then
        prov_check "\${svc_name} enabled but not running -- restart with: sudo systemctl restart \${svc_name}" "WARN"
    else
        prov_check "\${svc_name} not installed -- run --provision to set up" "WARN"
    fi
fi

# Field monitoring service
if systemctl is-active --quiet field-monitor.service 2>/dev/null; then
    prov_check "field-monitor.service active" "OK"
elif systemctl is-enabled --quiet field-monitor.service 2>/dev/null; then
    prov_check "field-monitor.service enabled but not running" "WARN"
else
    prov_check "field-monitor.service not installed -- optional, run --provision to set up" "WARN"
fi

# Boot timing capture timer (fires 60s after boot to capture timing data)
if systemctl is-enabled --quiet boot_timing.timer 2>/dev/null; then
    prov_check "boot_timing.timer enabled (captures timing 60s after boot)" "OK"
else
    prov_check "boot_timing.timer not installed -- run --provision to set up" "WARN"
fi

# Boot timing capture script
if [ -x /usr/local/sbin/boot_timing_capture.sh ]; then
    prov_check "boot_timing_capture.sh installed at /usr/local/sbin/" "OK"
else
    prov_check "boot_timing_capture.sh NOT found at /usr/local/sbin/ -- run --provision" "WARN"
fi

# WiFi watchdog service (disabled — NM autoconnect handles recovery)
# if systemctl is-active --quiet wifi-watchdog.service 2>/dev/null; then
#     prov_check "wifi-watchdog.service active" "OK"
# elif systemctl is-enabled --quiet wifi-watchdog.service 2>/dev/null; then
#     prov_check "wifi-watchdog.service enabled but not running" "WARN"
# else
#     prov_check "wifi-watchdog.service not installed -- run --provision to set up" "WARN"
# fi

# WiFi watchdog script (disabled)
# if [ -x /usr/local/sbin/wifi_watchdog.sh ]; then
#     prov_check "wifi_watchdog.sh installed at /usr/local/sbin/" "OK"
# else
#     prov_check "wifi_watchdog.sh NOT found at /usr/local/sbin/ -- run --provision" "WARN"
# fi

# WiFi NM autoconnect settings (infinite retries)
_wifi_autoconnect_ok=true
for _conn in \$(nmcli -t -f NAME,TYPE con show 2>/dev/null | grep ':.*wireless' | cut -d: -f1); do
    _retries=\$(nmcli -t -f connection.autoconnect-retries con show "\$_conn" 2>/dev/null | cut -d: -f2)
    # NM stores "infinite" as -1 (set via autoconnect-retries=0)
    if [ "\$_retries" != "-1" ] && [ "\$_retries" != "0" ]; then
        _wifi_autoconnect_ok=false
        break
    fi
done
if [ "\$_wifi_autoconnect_ok" = true ]; then
    prov_check "WiFi autoconnect-retries=0 (infinite) on all connections" "OK"
else
    prov_check "WiFi autoconnect-retries not set to 0 -- run --provision to fix" "WARN"
fi

# Arm identity config (arm role only)
if [ "\$ROLE" = "arm" ]; then
    if [ -f /etc/default/pragati-arm ]; then
        arm_id_val=\$(grep "^ARM_ID=" /etc/default/pragati-arm 2>/dev/null | cut -d'=' -f2)
        arm_domain=\$(grep "^ROS_DOMAIN_ID=" /etc/default/pragati-arm 2>/dev/null | cut -d'=' -f2)
        arm_localhost=\$(grep "^ROS_LOCALHOST_ONLY=" /etc/default/pragati-arm 2>/dev/null | cut -d'=' -f2)
        prov_check "Arm identity configured (ARM_ID=\${arm_id_val:-?}, ROS_DOMAIN_ID=\${arm_domain:-?}, ROS_LOCALHOST_ONLY=\${arm_localhost:-?})" "OK"

        # Warn if ROS_DOMAIN_ID is missing (old provisioning format)
        if [ -z "\$arm_domain" ]; then
            prov_check "ROS_DOMAIN_ID missing from /etc/default/pragati-arm -- re-run --provision --arm-id to fix" "WARN"
        fi

        # Verify .bashrc sources the identity file (not hardcoded values)
        if grep -q '/etc/default/pragati-arm' ~/.bashrc 2>/dev/null; then
            prov_check "~/.bashrc sources /etc/default/pragati-arm" "OK"
        else
            prov_check "~/.bashrc does not source /etc/default/pragati-arm -- next sync will fix" "WARN"
        fi
        if grep -q '^export ROS_DOMAIN_ID=' ~/.bashrc 2>/dev/null; then
            prov_check "~/.bashrc has stale hardcoded ROS_DOMAIN_ID -- next sync will clean up" "WARN"
        fi
    else
        prov_check "Arm identity not configured -- defaults to arm1, ROS_DOMAIN_ID=0. Run --provision --arm-id to set" "WARN"
    fi
fi

# Timezone
rpi_tz=\$(timedatectl show --property=Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo "unknown")
if [ "\$rpi_tz" = "Asia/Kolkata" ]; then
    prov_check "Timezone set to Asia/Kolkata" "OK"
else
    prov_check "Timezone is \${rpi_tz} (expected Asia/Kolkata) -- run --provision to fix" "WARN"
fi

# NTP enabled
ntp_active=\$(timedatectl show --property=NTP --value 2>/dev/null || echo "unknown")
if [ "\$ntp_active" = "yes" ]; then
    prov_check "NTP enabled" "OK"
else
    prov_check "NTP not enabled -- run --provision to fix" "WARN"
fi

# Clock disparity: compare RPi local time vs dev machine local time
rpi_local=\$(date +"%Y-%m-%d %H:%M:%S %Z")
rpi_epoch_local=\$(date +%s)
dev_epoch_local="${DEV_EPOCH_FOR_VERIFY}"
if [ "\$dev_epoch_local" -gt 0 ] 2>/dev/null && [ "\$rpi_epoch_local" -gt 0 ] 2>/dev/null; then
    disparity=\$(( rpi_epoch_local - dev_epoch_local ))
    [ "\$disparity" -lt 0 ] && disparity=\$(( -disparity ))
    if [ "\$disparity" -lt 5 ]; then
        prov_check "Clock disparity: \${disparity}s (RPi: \${rpi_local})" "OK"
    elif [ "\$disparity" -lt 30 ]; then
        prov_check "Clock disparity: \${disparity}s (RPi: \${rpi_local}) -- minor drift" "WARN"
    else
        prov_check "Clock disparity: \${disparity}s (RPi: \${rpi_local}) -- run sync to fix" "WARN"
    fi
fi

# config.txt CAN dtoverlay
_has_spi=false
_has_dtoverlay=false
_dtoverlay_correct=false
CAN_DTOVERLAY_EXPECTED="dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25,spimaxfrequency=1000000"
if ls /dev/spidev* >/dev/null 2>&1; then
    _has_spi=true
fi
if [ -f /boot/firmware/config.txt ]; then
    if grep -q "^dtoverlay=mcp2515-can0" /boot/firmware/config.txt 2>/dev/null; then
        _has_dtoverlay=true
        if grep -q "^\${CAN_DTOVERLAY_EXPECTED}\$" /boot/firmware/config.txt 2>/dev/null; then
            _dtoverlay_correct=true
        fi
    fi
fi
if [ "\$_has_spi" = true ] && [ "\$_has_dtoverlay" = true ] && [ "\$_dtoverlay_correct" = true ]; then
    prov_check "config.txt CAN dtoverlay" "OK"
elif [ "\$_has_spi" = true ] && [ "\$_has_dtoverlay" = true ] && [ "\$_dtoverlay_correct" = false ]; then
    prov_check "config.txt CAN dtoverlay: wrong parameters -- run --provision to fix" "fail" "MISMATCH"
elif [ "\$_has_spi" = true ] && [ "\$_has_dtoverlay" = false ]; then
    prov_check "config.txt CAN dtoverlay: missing -- run --provision to add" "fail" "MISMATCH"
elif [ "\$_has_spi" = false ] && [ "\$_has_dtoverlay" = true ]; then
    prov_check "config.txt CAN dtoverlay: present without CAN HAT -- run --provision to review" "fail" "MISMATCH"
else
    # No SPI + no dtoverlay = consistent, OK
    prov_check "config.txt CAN dtoverlay" "OK"
fi

# OS version currency
_os_version_id=\$(grep "^VERSION_ID=" /etc/os-release 2>/dev/null | cut -d'"' -f2 || echo "unknown")
_os_pretty=\$(grep "^PRETTY_NAME=" /etc/os-release 2>/dev/null | cut -d'"' -f2 || echo "unknown")
# Extract point release (e.g. "24.04.1 LTS" -> "24.04.1", or just "24.04")
_os_point=\$(echo "\$_os_pretty" | grep -oP '\d+\.\d+(\.\d+)?' | head -1)
_os_expected_baseline="24.04.4"
if [ -z "\$_os_point" ]; then
    _os_point="\$_os_version_id"
fi
# Compare: version_id should be 24.04, point release >= baseline
if [ "\$_os_version_id" = "24.04" ]; then
    # Compare point releases numerically (strip dots for simple comparison)
    _actual_num=\$(echo "\$_os_point" | tr -d '.')
    _expected_num=\$(echo "\$_os_expected_baseline" | tr -d '.')
    # Pad to same length for comparison (e.g. "2404" -> "24040", "24041" stays)
    while [ \${#_actual_num} -lt \${#_expected_num} ]; do _actual_num="\${_actual_num}0"; done
    while [ \${#_expected_num} -lt \${#_actual_num} ]; do _expected_num="\${_expected_num}0"; done
    if [ "\$_actual_num" -ge "\$_expected_num" ] 2>/dev/null; then
        prov_check "OS version \${_os_point}" "OK"
    else
        prov_check "OS version \${_os_point} (behind baseline \${_os_expected_baseline}) -- apt update && apt upgrade recommended" "WARN"
    fi
else
    prov_check "OS version \${_os_version_id} (expected 24.04.x) -- unexpected OS" "WARN"
fi

echo ""
echo "DEPLOY_SUMMARY=\${deploy_ok}/\${deploy_total}"
echo "PROV_SUMMARY=\${prov_ok}/\${prov_total}/\${prov_warn}"
VERIFY_SCRIPT
    )

    # ── Parse and display the output with color-coded results ──
    local line
    local in_section=""
    while IFS= read -r line; do
        # Skip summary lines (parsed separately below)
        if [[ "$line" == "DEPLOY_SUMMARY="* ]] || [[ "$line" == "PROV_SUMMARY="* ]]; then
            continue
        fi
        # Section headers
        if [[ "$line" == "SECTION=deploy" ]]; then
            in_section="deploy"
            echo -e "  ${BOLD}Deploy Health${NC}"
            echo -e "  ${DIM}─────────────────────────────────────────────────${NC}"
            continue
        elif [[ "$line" == "SECTION=provisioning" ]]; then
            in_section="provisioning"
            echo ""
            echo -e "  ${BOLD}Provisioning Status${NC}"
            echo -e "  ${DIM}─────────────────────────────────────────────────${NC}"
            continue
        fi
        # Result lines
        if [[ "$line" == "[OK]"* ]]; then
            echo -e "  ${GREEN}✓${NC} ${line#\[OK\]      }"
        elif [[ "$line" == "[FAIL]"* ]]; then
            echo -e "  ${RED}${BOLD}✗${NC} ${line#\[FAIL\]    }"
        elif [[ "$line" == "[INFO]"* ]]; then
            echo -e "  ${GREEN}✓${NC} ${line#\[INFO\]    }"
        elif [[ "$line" == "[MISMATCH]"* ]]; then
            echo -e "  ${RED}⚠${NC} ${line#\[MISMATCH\] }"
        elif [[ "$line" == "[WARN]"* ]]; then
            echo -e "  ${YELLOW}⚠${NC} ${line#\[WARN\]    }"
        elif [[ -n "$line" ]]; then
            echo "$line"
        fi
    done <<< "$verify_output"

    # ── Extract summaries ──
    local deploy_summary prov_summary
    deploy_summary=$(echo "$verify_output" | grep "^DEPLOY_SUMMARY=" | cut -d'=' -f2)
    prov_summary=$(echo "$verify_output" | grep "^PROV_SUMMARY=" | cut -d'=' -f2)

    local deploy_ok="${deploy_summary%/*}"
    local deploy_total="${deploy_summary#*/}"
    # prov_summary format: ok/total/warn
    local prov_ok prov_total prov_warn_count
    prov_ok=$(echo "$prov_summary" | cut -d'/' -f1)
    prov_total=$(echo "$prov_summary" | cut -d'/' -f2)
    prov_warn_count=$(echo "$prov_summary" | cut -d'/' -f3)

    echo ""

    # ── Deploy result (determines pass/fail) ──
    if [ "$deploy_ok" = "$deploy_total" ]; then
        echo -e "${BOLD}${GREEN}  Deploy Health: ${deploy_ok}/${deploy_total} checks passed${NC}"
    else
        local deploy_fail=$((deploy_total - deploy_ok))
        echo -e "${BOLD}${RED}  Deploy Health: ${deploy_fail} of ${deploy_total} checks FAILED${NC}"
    fi

    # ── Provisioning result (informational) ──
    if [ "${prov_warn_count:-0}" -gt 0 ]; then
        echo -e "${YELLOW}  Provisioning:  ${prov_ok}/${prov_total} OK, ${prov_warn_count} warnings -- run --provision to fix${NC}"
    else
        echo -e "${GREEN}  Provisioning:  ${prov_ok}/${prov_total} OK${NC}"
    fi

    echo ""

    # ── Final verdict: only deploy checks determine pass/fail ──
    if [ "$deploy_ok" = "$deploy_total" ]; then
        log_success "All deploy health checks passed"
        return 0
    else
        local deploy_fail=$((deploy_total - deploy_ok))
        echo -e "${BOLD}${RED}════════════════════════════════════════════════════════════════${NC}"
        echo -e "${BOLD}${RED}  ✗ DEPLOY VERIFICATION FAILED: ${deploy_fail} of ${deploy_total} checks failed${NC}"
        echo -e "${BOLD}${RED}════════════════════════════════════════════════════════════════${NC}"
        echo ""
        # Re-list only the hard failures
        echo -e "${RED}${BOLD}  Failed checks:${NC}"
        while IFS= read -r line; do
            if [[ "$line" == "[FAIL]"* ]]; then
                echo -e "    ${RED}✗ ${line#\[FAIL\]    }${NC}"
            fi
        done <<< "$verify_output"
        echo ""
        echo -e "${YELLOW}  Fix: Run '${0} --provision' to auto-fix most issues${NC}"
        echo ""
        return 1
    fi
}

# ============================================================================
# Main Sync Logic
# ============================================================================

echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  Pragati ROS2 - Sync to Raspberry Pi${NC}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo ""

log_info "Target: ${BOLD}${RPI_USER}@${RPI_IP}:${RPI_DIR}${NC}"
if [ "$ACTION_ONLY" = true ]; then
    log_info "Mode: ${BOLD}action-only (no file sync)${NC}"
else
    log_info "Mode: ${BOLD}${MODE}${NC}"
fi
[ "$TRIGGER_BUILD" = true ] && log_info "Will trigger: ${BOLD}Native build on target${NC}"
[ "$DEPLOY_CROSS" = true ] && log_info "Will deploy: ${BOLD}Cross-compiled ARM binaries${NC}"
[ "$DEPLOY_LOCAL" = true ] && log_info "Will deploy: ${BOLD}Local x86 binaries${NC}"
[ "$DO_PROVISION" = true ] && log_info "Will run: ${BOLD}Provisioning (OS fixes + services)${NC}"
[ "$DO_VERIFY" = true ] && log_info "Will run: ${BOLD}Post-sync verification${NC}"
[ "$DO_RESTART" = true ] && log_info "Will run: ${BOLD}Service restart${NC}"
[ "$DRY_RUN" = true ] && log_warn "DRY RUN - no changes will be made"
echo ""

# ============================================================================
# Step 1: Test SSH Connection
# ============================================================================

log_step "Testing SSH connection..."

# Show info if using WSL bridge
if is_wsl && is_windows_hotspot_ip "$RPI_IP"; then
    if get_windows_ssh &>/dev/null; then
        log_info "WSL detected: Using Windows SSH for hotspot connectivity"
    fi
fi

if ! smart_ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${RPI_USER}@${RPI_IP}" "echo OK" &>/dev/null; then
    log_error "Cannot connect to ${RPI_USER}@${RPI_IP}"
    echo ""
    echo "  Troubleshooting:"
    echo "    1. Check RPi is powered on and connected"
    echo "    2. Verify IP address: ping ${RPI_IP}"
    echo "    3. Setup SSH keys: ssh-copy-id ${RPI_USER}@${RPI_IP}"
    echo ""
    echo "  Update IP: $0 --ip <correct-ip> --save"
    exit 1
fi

log_success "SSH connection OK"

# ============================================================================
# Step 1b: Sync RPi Clock from Dev Machine
# ============================================================================
# RPi often runs without internet, so its clock drifts. Pushing the dev
# machine's UTC time on every sync keeps log timestamps consistent across
# devices and avoids the cross-file timezone mismatch issues in the analyzer.
# This runs for ALL modes including action-only (provision/verify/restart)
# because clock drift affects log analysis and service behavior.

if [ "$DO_TIME_SYNC" = true ] && [ "$DRY_RUN" = false ]; then
    log_step "Checking RPi clock drift..."
    local_epoch=$(date -u +%s)

    # Step 1: Read RPi time WITHOUT sudo to measure drift
    if rpi_epoch=$(smart_ssh "${RPI_USER}@${RPI_IP}" "date -u +%s" 2>/dev/null); then
        # Compute absolute drift
        time_drift=$(( local_epoch - rpi_epoch ))
        [ "$time_drift" -lt 0 ] && time_drift=$(( -time_drift ))

        if [ "$time_drift" -le 5 ]; then
            # Drift within threshold — no sync needed
            log_success "Clock OK (${time_drift}s drift, threshold 5s)"
        else
            # Drift exceeds threshold — attempt to set clock via passwordless sudo
            log_info "Clock drift is ${time_drift}s — attempting sync..."
            local_utc=$(date -u +"%Y-%m-%d %H:%M:%S")
            if sync_output=$(smart_ssh "${RPI_USER}@${RPI_IP}" "sudo -n bash -s" << TIMESYNC_SCRIPT
if sudo -n date -u -s "${local_utc}" >/dev/null 2>&1; then
    sudo -n hwclock -w 2>/dev/null || true
    # Verify: re-read time and report post-sync drift
    post_epoch=\$(date -u +%s)
    echo "DATE_SET_OK=true"
    echo "POST_EPOCH=\${post_epoch}"
else
    echo "DATE_SET_OK=false"
fi
TIMESYNC_SCRIPT
            ); then
                date_set_ok=$(echo "$sync_output" | grep "^DATE_SET_OK=" | cut -d'=' -f2)
                if [ "$date_set_ok" = "true" ]; then
                    # Verify post-sync drift
                    post_epoch=$(echo "$sync_output" | grep "^POST_EPOCH=" | cut -d'=' -f2)
                    verify_epoch=$(date -u +%s)
                    if [ -n "$post_epoch" ] && [ "$post_epoch" -gt 0 ] 2>/dev/null; then
                        post_drift=$(( verify_epoch - post_epoch ))
                        [ "$post_drift" -lt 0 ] && post_drift=$(( -post_drift ))
                        if [ "$post_drift" -le 3 ]; then
                            log_success "Clock synced (was ${time_drift}s off, now ${post_drift}s)"
                        else
                            log_warn "Clock set attempted but post-sync drift is ${post_drift}s (>3s) — verify NTP or sudo"
                        fi
                    else
                        log_warn "Clock set but could not verify post-sync drift"
                    fi
                else
                    log_warn "sudo date -s failed silently — clock drift remains ${time_drift}s"
                    log_warn "  Fix: add 'ubuntu ALL=(ALL) NOPASSWD: /usr/bin/date, /sbin/hwclock' to /etc/sudoers.d/timesync"
                fi
            else
                log_warn "Clock sync failed (sudo requires password) — drift is ${time_drift}s"
                log_warn "  Fix: configure passwordless sudo for date/hwclock, or use --no-time-sync to skip"
            fi
        fi
    else
        log_warn "Could not read RPi clock — use --no-time-sync to skip"
    fi
fi

# ============================================================================
# Skip file sync steps for action-only mode (--restart, --provision, --verify, --time-sync)
# ============================================================================
if [ "$ACTION_ONLY" = true ]; then
    log_info "Action-only mode — skipping file sync, permissions, and bashrc patching"
else

# ============================================================================
# Step 2: Prepare Remote Directory
# ============================================================================

log_step "Preparing remote directory..."

if [ "$DRY_RUN" = false ]; then
    smart_ssh "${RPI_USER}@${RPI_IP}" "mkdir -p ${RPI_DIR}"
fi
log_success "Remote directory ready: ${RPI_DIR}"

# ============================================================================
# Step 3: Handle Cross-Compiled Deployment (if requested)
# ============================================================================

if [ "$DEPLOY_CROSS" = true ]; then
    log_step "Deploying cross-compiled binaries..."

    # Check if install_rpi exists
    if [ ! -d "${WORKSPACE}/install_rpi" ]; then
        log_error "install_rpi/ not found!"
        echo ""
        echo "  Cross-compile first:"
        echo "    cd ${WORKSPACE}"
        echo "    ./build.sh rpi"
        echo ""
        exit 1
    fi

    echo -e "${GRAY}  Syncing: install_rpi/ -> install/${NC}"

    if [ "$DRY_RUN" = false ]; then
        rsync_with_retry -avz --delete \
            "${WORKSPACE}/install_rpi/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/install/"
    else
        smart_rsync -avz --delete --dry-run \
            "${WORKSPACE}/install_rpi/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/install/" | head -20
    fi

    log_success "Cross-compiled binaries deployed"

    # Fix hardcoded paths in setup.bash (cross-compile embeds local PC paths)
    log_step "Fixing setup.bash paths for RPi..."
    smart_ssh "${RPI_USER}@${RPI_IP}" 'cat > ~/pragati_ros2/install/setup.bash << '\''SETUPEOF'\''
# Fixed setup.bash for cross-compiled workspace
# Automatically patched by sync.sh --deploy-cross

_colcon_prefix_chain_bash_source_script() {
  if [ -f "$1" ]; then
    if [ -n "$COLCON_TRACE" ]; then
      echo "# . \"$1\""
    fi
    . "$1"
  else
    echo "not found: \"$1\"" 1>&2
  fi
}

# source ROS2 Jazzy
COLCON_CURRENT_PREFIX="/opt/ros/jazzy"
_colcon_prefix_chain_bash_source_script "$COLCON_CURRENT_PREFIX/local_setup.bash"

# source this workspace (use relative path)
COLCON_CURRENT_PREFIX="$(builtin cd "$(dirname "${BASH_SOURCE[0]}")" > /dev/null && pwd)"
_colcon_prefix_chain_bash_source_script "$COLCON_CURRENT_PREFIX/local_setup.bash"

unset COLCON_CURRENT_PREFIX
unset _colcon_prefix_chain_bash_source_script
SETUPEOF'
    log_success "setup.bash paths fixed"

    # Deploy modes only need runtime files, not source code or build configs.
    # Source, CMakePresets, colcon.meta, build.sh are only for native builds.
    # Use default mode (or --build) if you need to rebuild on RPi.
    log_step "Syncing runtime files..."
    rsync_with_retry -avz --delete \
        --exclude='__pycache__/' --exclude='*.pyc' \
        "${WORKSPACE}/scripts/" \
        "${RPI_USER}@${RPI_IP}:${RPI_DIR}/scripts/"

    # launch/ contains ARM_client.py (MQTT bridge) used by pragati_complete.launch.py
    rsync_with_retry -avz \
        "${WORKSPACE}/launch/" \
        "${RPI_USER}@${RPI_IP}:${RPI_DIR}/launch/" 2>/dev/null || true

    # Sync config/ (cyclonedds.xml, etc. — runtime dependency for ROS2 nodes)
    # No --delete: RPi may have local config overrides
    [ -d "${WORKSPACE}/config" ] && \
        rsync_with_retry -avz \
            "${WORKSPACE}/config/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/config/"

    # Sync data/models/ (YOLO .blob files for DepthAI cotton detection)
    [ -d "${WORKSPACE}/data/models" ] && \
        rsync_with_retry -avz \
            "${WORKSPACE}/data/models/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/data/models/" 2>/dev/null || true

    # Sync systemd/ (service files needed by --provision)
    [ -d "${WORKSPACE}/systemd" ] && \
        rsync_with_retry -avz --delete \
            "${WORKSPACE}/systemd/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/systemd/"

    # Sync web_dashboard/ (FastAPI backend + frontend + config)
    # Excludes test files, __pycache__, and e2e tests (not needed on RPi)
    # Excludes config/dashboard.yaml to preserve RPi-specific role set by --provision
    [ -d "${WORKSPACE}/web_dashboard" ] && \
        rsync_with_retry -avz --delete \
            --exclude='__pycache__/' --exclude='*.pyc' \
            --exclude='backend/test_*.py' \
            --exclude='e2e_tests/' \
            --exclude='conftest.py' \
            --exclude='node_modules/' \
            --exclude='config/dashboard.yaml' \
            "${WORKSPACE}/web_dashboard/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/web_dashboard/"

    # Sync root runtime files only (no build configs)
    # - sync.sh: for re-syncing from RPi if needed
    # - setup_raspberry_pi.sh: for first-time RPi provisioning
    # - emergency_motor_stop.sh: safety critical
    rsync_with_retry -avz \
        "${WORKSPACE}/sync.sh" \
        "${WORKSPACE}/setup_raspberry_pi.sh" \
        "${WORKSPACE}/emergency_motor_stop.sh" \
        "${RPI_USER}@${RPI_IP}:${RPI_DIR}/" 2>/dev/null || true

    # Ensure bashrc has sourcing for ROS2 and workspace
    log_step "Ensuring ~/.bashrc has ROS2 sourcing..."
    smart_ssh "${RPI_USER}@${RPI_IP}" 'bash -s' << 'BASHRCEOF'
# Add ROS2 Jazzy sourcing if not present
if ! grep -q "source /opt/ros/jazzy/setup.bash" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# ROS2 Jazzy" >> ~/.bashrc
    echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
    echo "Added: source /opt/ros/jazzy/setup.bash"
else
    echo "Already present: ROS2 Jazzy sourcing"
fi

# Add workspace sourcing if not present
if ! grep -q "source ~/pragati_ros2/install/setup.bash" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati ROS2 Workspace" >> ~/.bashrc
    echo "if [ -f ~/pragati_ros2/install/setup.bash ]; then" >> ~/.bashrc
    echo "    source ~/pragati_ros2/install/setup.bash" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: Pragati workspace sourcing"
else
    echo "Already present: Pragati workspace sourcing"
fi

# Remove stale hardcoded ROS_DOMAIN_ID/ROS_LOCALHOST_ONLY/RMW_IMPLEMENTATION (now managed via /etc/default/pragati-arm)
sed -i '/^export ROS_DOMAIN_ID=/d' ~/.bashrc
sed -i '/^export ROS_LOCALHOST_ONLY=/d' ~/.bashrc
sed -i '/^export RMW_IMPLEMENTATION=/d' ~/.bashrc

# Add sourcing of arm identity file (if not already present)
if ! grep -q '/etc/default/pragati-arm' ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati arm identity (managed by sync.sh --provision)" >> ~/.bashrc
    echo "if [ -f /etc/default/pragati-arm ]; then" >> ~/.bashrc
    echo "    set -a; source /etc/default/pragati-arm; set +a" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: /etc/default/pragati-arm sourcing"
else
    echo "Already present: /etc/default/pragati-arm sourcing"
fi
BASHRCEOF
    log_success "~/.bashrc configured"
    log_success "Cross-compiled deployment complete"
fi

# ============================================================================
# Step 3b: Handle Local Build Deployment (Ubuntu-to-Ubuntu, if requested)
# ============================================================================

if [ "$DEPLOY_LOCAL" = true ]; then
    log_step "Deploying locally-built binaries (Ubuntu-to-Ubuntu)..."

    # Check if install/ exists
    if [ ! -d "${WORKSPACE}/install" ]; then
        log_error "install/ not found!"
        echo ""
        echo "  Build locally first:"
        echo "    cd ${WORKSPACE}"
        echo "    ./build.sh          # or: ./build.sh fast"
        echo ""
        exit 1
    fi

    echo -e "${GRAY}  Syncing: install/ -> install/${NC}"

    if [ "$DRY_RUN" = false ]; then
        rsync_with_retry -avz --delete \
            "${WORKSPACE}/install/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/install/"
    else
        smart_rsync -avz --delete --dry-run \
            "${WORKSPACE}/install/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/install/" | head -20
    fi

    log_success "Local binaries deployed"

    # Fix hardcoded paths in setup.bash (local build embeds local PC paths)
    log_step "Fixing setup.bash paths for target machine..."
    smart_ssh "${RPI_USER}@${RPI_IP}" 'cat > ~/pragati_ros2/install/setup.bash << '\''SETUPEOF'\''
# Fixed setup.bash for deployed workspace
# Automatically patched by sync.sh --deploy-local

_colcon_prefix_chain_bash_source_script() {
  if [ -f "$1" ]; then
    if [ -n "$COLCON_TRACE" ]; then
      echo "# . \"$1\""
    fi
    . "$1"
  else
    echo "not found: \"$1\"" 1>&2
  fi
}

# source ROS2 Jazzy
COLCON_CURRENT_PREFIX="/opt/ros/jazzy"
_colcon_prefix_chain_bash_source_script "$COLCON_CURRENT_PREFIX/local_setup.bash"

# source this workspace (use relative path)
COLCON_CURRENT_PREFIX="$(builtin cd "$(dirname "${BASH_SOURCE[0]}")" > /dev/null && pwd)"
_colcon_prefix_chain_bash_source_script "$COLCON_CURRENT_PREFIX/local_setup.bash"

unset COLCON_CURRENT_PREFIX
unset _colcon_prefix_chain_bash_source_script
SETUPEOF'
    log_success "setup.bash paths fixed"

    # Deploy modes only need runtime files, not source code or build configs.
    # Source, CMakePresets, colcon.meta, build.sh are only for native builds.
    # Use default mode (or --build) if you need to rebuild on target.
    log_step "Syncing runtime files..."
    rsync_with_retry -avz --delete \
        --exclude='__pycache__/' --exclude='*.pyc' \
        "${WORKSPACE}/scripts/" \
        "${RPI_USER}@${RPI_IP}:${RPI_DIR}/scripts/"

    # launch/ contains ARM_client.py (MQTT bridge) used by pragati_complete.launch.py
    rsync_with_retry -avz \
        "${WORKSPACE}/launch/" \
        "${RPI_USER}@${RPI_IP}:${RPI_DIR}/launch/" 2>/dev/null || true

    # Sync config/ (cyclonedds.xml, etc. — runtime dependency for ROS2 nodes)
    # No --delete: RPi may have local config overrides
    [ -d "${WORKSPACE}/config" ] && \
        rsync_with_retry -avz \
            "${WORKSPACE}/config/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/config/"

    # Sync data/models/ (YOLO .blob files for DepthAI cotton detection)
    [ -d "${WORKSPACE}/data/models" ] && \
        rsync_with_retry -avz \
            "${WORKSPACE}/data/models/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/data/models/" 2>/dev/null || true

    # Sync systemd/ (service files needed by --provision)
    [ -d "${WORKSPACE}/systemd" ] && \
        rsync_with_retry -avz --delete \
            "${WORKSPACE}/systemd/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/systemd/"

    # Sync web_dashboard/ (FastAPI backend + frontend + config)
    # Excludes test files, __pycache__, and e2e tests (not needed on RPi)
    # Excludes config/dashboard.yaml to preserve RPi-specific role set by --provision
    [ -d "${WORKSPACE}/web_dashboard" ] && \
        rsync_with_retry -avz --delete \
            --exclude='__pycache__/' --exclude='*.pyc' \
            --exclude='backend/test_*.py' \
            --exclude='e2e_tests/' \
            --exclude='conftest.py' \
            --exclude='node_modules/' \
            --exclude='config/dashboard.yaml' \
            "${WORKSPACE}/web_dashboard/" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/web_dashboard/"

    # Sync root runtime files only
    rsync_with_retry -avz \
        "${WORKSPACE}/sync.sh" \
        "${WORKSPACE}/setup_raspberry_pi.sh" \
        "${WORKSPACE}/emergency_motor_stop.sh" \
        "${RPI_USER}@${RPI_IP}:${RPI_DIR}/" 2>/dev/null || true

    # Ensure bashrc has sourcing for ROS2 and workspace
    log_step "Ensuring ~/.bashrc has ROS2 sourcing..."
    smart_ssh "${RPI_USER}@${RPI_IP}" 'bash -s' << 'BASHRCEOF'
# Add ROS2 Jazzy sourcing if not present
if ! grep -q "source /opt/ros/jazzy/setup.bash" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# ROS2 Jazzy" >> ~/.bashrc
    echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
    echo "Added: source /opt/ros/jazzy/setup.bash"
else
    echo "Already present: ROS2 Jazzy sourcing"
fi

# Add workspace sourcing if not present
if ! grep -q "source ~/pragati_ros2/install/setup.bash" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati ROS2 Workspace" >> ~/.bashrc
    echo "if [ -f ~/pragati_ros2/install/setup.bash ]; then" >> ~/.bashrc
    echo "    source ~/pragati_ros2/install/setup.bash" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: Pragati workspace sourcing"
else
    echo "Already present: Pragati workspace sourcing"
fi

# Remove stale hardcoded ROS_DOMAIN_ID/ROS_LOCALHOST_ONLY/RMW_IMPLEMENTATION (now managed via /etc/default/pragati-arm)
sed -i '/^export ROS_DOMAIN_ID=/d' ~/.bashrc
sed -i '/^export ROS_LOCALHOST_ONLY=/d' ~/.bashrc
sed -i '/^export RMW_IMPLEMENTATION=/d' ~/.bashrc

# Add sourcing of arm identity file (if not already present)
if ! grep -q '/etc/default/pragati-arm' ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati arm identity (managed by sync.sh --provision)" >> ~/.bashrc
    echo "if [ -f /etc/default/pragati-arm ]; then" >> ~/.bashrc
    echo "    set -a; source /etc/default/pragati-arm; set +a" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: /etc/default/pragati-arm sourcing"
else
    echo "Already present: /etc/default/pragati-arm sourcing"
fi
BASHRCEOF
    log_success "~/.bashrc configured"
    log_success "Local build deployment complete"
fi

# ============================================================================
# Step 4: Build rsync command based on mode
# (Skipped when --deploy-cross or --deploy-local handled syncing above)
# ============================================================================

if [ "$DEPLOY_CROSS" = true ] || [ "$DEPLOY_LOCAL" = true ]; then
    log_info "File sync handled by deploy mode — skipping standard sync"
else

log_step "Syncing files (mode: ${MODE})..."

# Common rsync options
if [ "$DRY_RUN" = true ]; then
    # Dry-run: show file list only (no misleading byte progress)
    RSYNC_OPTS="-az --dry-run --itemize-changes"
    [ "$VERBOSE" = true ] && RSYNC_OPTS="-avz --dry-run --itemize-changes"
else
    RSYNC_OPTS="-az --info=progress2"
    [ "$VERBOSE" = true ] && RSYNC_OPTS="-avz"
fi

# Common excludes (always exclude these)
COMMON_EXCLUDES=(
    --exclude='build/'
    --exclude='build_rpi/'
    --exclude='install/'
    --exclude='install_rpi/'
    --exclude='log/'
    --exclude='logs/'
    --exclude='.git/'
    --exclude='*.pyc'
    --exclude='__pycache__/'
    --exclude='.cache/'
    --exclude='*.o'
    --exclude='*.so'
    --exclude='venv/'
    --exclude='.vscode/'
    --exclude='*.bag'
    --exclude='*.db3'
    --exclude='*.mcap'
    --exclude='test_output/'
    --exclude='test_results/'
    --exclude='validation_logs/'
    --exclude='metrics/'
    --exclude='outputs/'
    --exclude='.ccache/'
    --exclude='archive/'
    # Desktop-only: Gazebo simulation (49MB) cannot run on RPi
    --exclude='**/vehicle_control/simulation/gazebo/'
    --exclude='node_modules/'
    --exclude='test-results/'
    # Dev/CI artifacts not needed on RPi
    --exclude='collected_logs/'
    --exclude='.opencode/'
    --exclude='openspec/'
    --exclude='docs/'
    --exclude='.github/'
    # web_dashboard/ is synced explicitly in deploy-cross/deploy-local (not via COMMON_EXCLUDES)
    --exclude='web_dashboard/backend/__pycache__/'
    --exclude='web_dashboard/backend/test_*.py'
    --exclude='web_dashboard/e2e_tests/'
    --exclude='web_dashboard/conftest.py'
    --exclude='web_dashboard/*.pyc'
    --exclude='examples/'
    --exclude='data/inputs/'
    --exclude='*.egg-info/'
    --exclude='.mypy_cache/'
    --exclude='.pytest_cache/'
    --exclude='*.log'
    --exclude='.clang-tidy'
    --exclude='.pre-commit-config.yaml'
)

# Bake git version for RPi builds (RPi doesn't have git installed)
if [ "$TRIGGER_BUILD" = true ]; then
    log_info "Baking git version for RPi build..."
    echo "$(git rev-parse --short HEAD) $(git rev-parse --abbrev-ref HEAD)" > "${WORKSPACE}/.git_version"
fi

case $MODE in
    "default")
        # Standard sync: source + scripts + config + launch + models + root files
        echo -e "${GRAY}  Syncing: src/, scripts/, config/, launch/, systemd/, data/models/, build.sh, *.xml${NC}"

        # Sync src/
        smart_rsync $RSYNC_OPTS --delete "${COMMON_EXCLUDES[@]}" \
            "${WORKSPACE}/src/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/src/"

        # Sync scripts/
        smart_rsync $RSYNC_OPTS --delete "${COMMON_EXCLUDES[@]}" \
            "${WORKSPACE}/scripts/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/scripts/"

        # Sync config/ (no --delete: RPi may have local config overrides)
        [ -d "${WORKSPACE}/config" ] && \
            smart_rsync $RSYNC_OPTS \
                "${WORKSPACE}/config/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/config/"

        # Sync launch/
        [ -d "${WORKSPACE}/launch" ] && \
            smart_rsync $RSYNC_OPTS --delete \
                "${WORKSPACE}/launch/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/launch/"

        # Sync data/models/ (YOLO .blob files for DepthAI)
        [ -d "${WORKSPACE}/data/models" ] && \
            smart_rsync $RSYNC_OPTS --delete \
                "${WORKSPACE}/data/models/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/data/models/"

        # Sync systemd/ (service files needed by --provision)
        [ -d "${WORKSPACE}/systemd" ] && \
            smart_rsync $RSYNC_OPTS --delete \
                "${WORKSPACE}/systemd/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/systemd/"

        # Sync root files (including sync.sh itself for RPi-to-RPi sync capability)
        smart_rsync $RSYNC_OPTS \
            "${WORKSPACE}/build.sh" \
            "${WORKSPACE}/sync.sh" \
            "${WORKSPACE}/CMakePresets.json" \
            "${WORKSPACE}/colcon.meta" \
            "${WORKSPACE}/setup_raspberry_pi.sh" \
            "${WORKSPACE}/emergency_motor_stop.sh" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/" 2>/dev/null || true

        # Sync .git_version if it exists (generated for --build mode)
        [ -f "${WORKSPACE}/.git_version" ] && \
            smart_rsync $RSYNC_OPTS \
                "${WORKSPACE}/.git_version" \
                "${RPI_USER}@${RPI_IP}:${RPI_DIR}/" 2>/dev/null || true
        ;;

    "all")
        # Full sync: everything except build artifacts and archive
        echo -e "${GRAY}  Syncing: entire workspace (excluding build artifacts)${NC}"

        smart_rsync $RSYNC_OPTS --delete "${COMMON_EXCLUDES[@]}" \
            "${WORKSPACE}/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/"
        ;;

    "source")
        # Source only
        echo -e "${GRAY}  Syncing: src/ only${NC}"

        smart_rsync $RSYNC_OPTS --delete "${COMMON_EXCLUDES[@]}" \
            "${WORKSPACE}/src/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/src/"
        ;;

    "scripts")
        # Scripts only
        echo -e "${GRAY}  Syncing: scripts/ only${NC}"

        smart_rsync $RSYNC_OPTS --delete "${COMMON_EXCLUDES[@]}" \
            "${WORKSPACE}/scripts/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/scripts/"
        ;;

    "quick")
        # Quick sync: scripts without --delete
        echo -e "${GRAY}  Quick sync: scripts/ (no delete)${NC}"

        smart_rsync $RSYNC_OPTS "${COMMON_EXCLUDES[@]}" \
            "${WORKSPACE}/scripts/" "${RPI_USER}@${RPI_IP}:${RPI_DIR}/scripts/"

        # Also sync commonly modified files
        smart_rsync $RSYNC_OPTS \
            "${WORKSPACE}/build.sh" \
            "${RPI_USER}@${RPI_IP}:${RPI_DIR}/" 2>/dev/null || true
        ;;
esac

log_success "Sync complete"

# ============================================================================
# Step 5: Set Permissions
# ============================================================================

log_step "Setting permissions..."

if [ "$DRY_RUN" = false ]; then
    smart_ssh "${RPI_USER}@${RPI_IP}" bash << REMOTE_PERMS
cd ${RPI_DIR} 2>/dev/null || exit 0
chmod +x build.sh setup_raspberry_pi.sh emergency_motor_stop.sh 2>/dev/null || true
find scripts -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
find scripts -name "*.py" -exec chmod +x {} \; 2>/dev/null || true
REMOTE_PERMS
fi

log_success "Permissions set"

# ============================================================================
# Step 6: Native Build on RPi (if requested)
# ============================================================================

if [ "$TRIGGER_BUILD" = true ]; then
    log_step "Building NATIVELY on Raspberry Pi..."
    log_info "This builds directly on RPi (not using cross-compiled binaries)"

    if [ "$DRY_RUN" = false ]; then
        smart_ssh -t "${RPI_USER}@${RPI_IP}" bash << REMOTE_BUILD
set -e
cd ${RPI_DIR}

# Source ROS2 Jazzy
if [ -f /opt/ros/jazzy/setup.bash ]; then
    source /opt/ros/jazzy/setup.bash
else
    echo "ERROR: ROS2 Jazzy not found at /opt/ros/jazzy"
    exit 1
fi

echo ""
echo "Building packages natively on RPi..."
echo "This may take a few minutes..."
echo ""

# Use colcon directly for native build
# (build.sh rpi is for cross-compilation, not native)
colcon build --symlink-install --parallel-workers \$(nproc) \\
    --cmake-args -DCMAKE_BUILD_TYPE=Release \\
    2>&1 | tail -30

echo ""
echo "✓ Native build complete!"
echo ""
echo "To run:"
echo "  source install/setup.bash"
echo "  ros2 launch vehicle_control vehicle_complete.launch.py"
REMOTE_BUILD
    else
        log_info "Would trigger native build on RPi"
    fi

    log_success "Build complete"
fi

# ============================================================================
# Ensure bashrc has ROS2 sourcing (all sync modes)
# ============================================================================

if [ "$DRY_RUN" = false ]; then
    log_step "Ensuring ~/.bashrc has ROS2 sourcing..."
    smart_ssh "${RPI_USER}@${RPI_IP}" 'bash -s' << 'BASHRCEOF'
# Add ROS2 Jazzy sourcing if not present
if ! grep -q "source /opt/ros/jazzy/setup.bash" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# ROS2 Jazzy" >> ~/.bashrc
    echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
    echo "Added: source /opt/ros/jazzy/setup.bash"
else
    echo "Already present: ROS2 Jazzy sourcing"
fi

# Add workspace sourcing if not present
if ! grep -q "source ~/pragati_ros2/install/setup.bash" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati ROS2 Workspace" >> ~/.bashrc
    echo "if [ -f ~/pragati_ros2/install/setup.bash ]; then" >> ~/.bashrc
    echo "    source ~/pragati_ros2/install/setup.bash" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: Pragati workspace sourcing"
else
    echo "Already present: Pragati workspace sourcing"
fi

# Remove stale hardcoded ROS_DOMAIN_ID/ROS_LOCALHOST_ONLY/RMW_IMPLEMENTATION (now managed via /etc/default/pragati-arm)
sed -i '/^export ROS_DOMAIN_ID=/d' ~/.bashrc
sed -i '/^export ROS_LOCALHOST_ONLY=/d' ~/.bashrc
sed -i '/^export RMW_IMPLEMENTATION=/d' ~/.bashrc

# Add sourcing of arm identity file (if not already present)
if ! grep -q '/etc/default/pragati-arm' ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Pragati arm identity (managed by sync.sh --provision)" >> ~/.bashrc
    echo "if [ -f /etc/default/pragati-arm ]; then" >> ~/.bashrc
    echo "    set -a; source /etc/default/pragati-arm; set +a" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "Added: /etc/default/pragati-arm sourcing"
else
    echo "Already present: /etc/default/pragati-arm sourcing"
fi
BASHRCEOF
    log_success "~/.bashrc configured"
fi

fi  # end of: if NOT deploy mode

fi  # end of: if NOT action-only mode

# ============================================================================
# Step 7: Provisioning (if requested)
# ============================================================================

PROVISION_RESULT=""
if [ "$DO_PROVISION" = true ]; then
    if [ "$DRY_RUN" = false ]; then
        if run_provision; then
            PROVISION_RESULT="success"
        else
            PROVISION_RESULT="partial"
        fi
    else
        log_info "Would run provisioning on RPi (dry-run)"
        PROVISION_RESULT="skipped"
    fi
fi

# ============================================================================
# Step 8: Verification (if requested)
# ============================================================================

VERIFY_RESULT=""
if [ "$DO_VERIFY" = true ]; then
    if [ "$DRY_RUN" = false ]; then
        if run_verify; then
            VERIFY_RESULT="pass"
        else
            VERIFY_RESULT="fail"
        fi
    else
        log_info "Would run verification on RPi (dry-run)"
        VERIFY_RESULT="skipped"
    fi
fi

# ============================================================================
# Step 9: Service Restart (if requested)
# ============================================================================

RESTART_RESULT=""
if [ "$DO_RESTART" = true ]; then
    if [ "$DRY_RUN" = false ]; then
        log_step "Restarting services on ${RPI_USER}@${RPI_IP}..."
        local_role=$(detect_rpi_role 2>/dev/null)

        # Write restart script to temp file, then execute with -t for sudo prompt.
        # IMPORTANT: heredoc delimiter is UNQUOTED so ${local_role} is expanded locally
        # (baked into the script text). This avoids needing sudo -E to pass env vars.
        restart_script="/tmp/.pragati_restart_$$.sh"
        smart_ssh "${RPI_USER}@${RPI_IP}" "cat > ${restart_script}" << RESTART_SCRIPT
ROLE="${local_role}"
restart_ok=0
restart_fail=0

# Restart role-specific launch service
if [ "\$ROLE" = "vehicle" ]; then
    if systemctl restart vehicle_launch.service 2>&1; then
        echo "[OK] Restarted vehicle_launch.service"
        restart_ok=\$((restart_ok + 1))
    else
        echo "[FAIL] Could not restart vehicle_launch.service"
        restart_fail=\$((restart_fail + 1))
    fi
else
    if systemctl restart arm_launch.service 2>&1; then
        echo "[OK] Restarted arm_launch.service"
        restart_ok=\$((restart_ok + 1))
    else
        echo "[FAIL] Could not restart arm_launch.service"
        restart_fail=\$((restart_fail + 1))
    fi
fi

# Restart field-monitor.service if enabled
if systemctl is-enabled --quiet field-monitor.service 2>/dev/null; then
    if systemctl restart field-monitor.service 2>&1; then
        echo "[OK] Restarted field-monitor.service"
        restart_ok=\$((restart_ok + 1))
    else
        echo "[FAIL] Could not restart field-monitor.service"
        restart_fail=\$((restart_fail + 1))
    fi
fi

# Restart pragati-dashboard.service if enabled
if systemctl is-enabled --quiet pragati-dashboard.service 2>/dev/null; then
    if systemctl restart pragati-dashboard.service 2>&1; then
        echo "[OK] Restarted pragati-dashboard.service"
        restart_ok=\$((restart_ok + 1))
    else
        echo "[FAIL] Could not restart pragati-dashboard.service"
        restart_fail=\$((restart_fail + 1))
    fi
fi

# Restart pragati-agent.service if enabled
if systemctl is-enabled --quiet pragati-agent.service 2>/dev/null; then
    if systemctl restart pragati-agent.service 2>&1; then
        echo "[OK] Restarted pragati-agent.service"
        restart_ok=\$((restart_ok + 1))
    else
        echo "[FAIL] Could not restart pragati-agent.service"
        restart_fail=\$((restart_fail + 1))
    fi
fi

# Brief pause then verify services came up
sleep 2

if [ "\$ROLE" = "vehicle" ]; then
    if systemctl is-active --quiet vehicle_launch.service 2>/dev/null; then
        echo "[VERIFIED] vehicle_launch.service is active"
    else
        echo "[WARN] vehicle_launch.service is not active after restart"
    fi
else
    if systemctl is-active --quiet arm_launch.service 2>/dev/null; then
        echo "[VERIFIED] arm_launch.service is active"
    else
        echo "[WARN] arm_launch.service is not active after restart"
    fi
fi

if systemctl is-enabled --quiet field-monitor.service 2>/dev/null; then
    if systemctl is-active --quiet field-monitor.service 2>/dev/null; then
        echo "[VERIFIED] field-monitor.service is active"
    else
        echo "[WARN] field-monitor.service is not active after restart"
    fi
fi

if systemctl is-enabled --quiet pragati-dashboard.service 2>/dev/null; then
    if systemctl is-active --quiet pragati-dashboard.service 2>/dev/null; then
        echo "[VERIFIED] pragati-dashboard.service is active"
    else
        echo "[WARN] pragati-dashboard.service is not active after restart"
    fi
fi

if systemctl is-enabled --quiet pragati-agent.service 2>/dev/null; then
    if systemctl is-active --quiet pragati-agent.service 2>/dev/null; then
        echo "[VERIFIED] pragati-agent.service is active"
    else
        echo "[WARN] pragati-agent.service is not active after restart"
    fi
fi

echo "RESTART_OK=\${restart_ok}"
echo "RESTART_FAIL=\${restart_fail}"
RESTART_SCRIPT

        # Execute restart script with -t (TTY for sudo prompt visible to user).
        # Script runs as root, so systemctl commands inside don't need sudo prefix.
        # Results saved to temp file on RPi, read back separately.
        restart_results="/tmp/.pragati_restart_results_$$.txt"
        smart_ssh -t "${RPI_USER}@${RPI_IP}" \
            "sudo bash ${restart_script} 2>&1 | tee ${restart_results}; rm -f ${restart_script}" 2>&1 || true

        # Read results back from RPi
        restart_output=""
        restart_output=$(smart_ssh "${RPI_USER}@${RPI_IP}" "cat ${restart_results} 2>/dev/null; rm -f ${restart_results}" 2>&1)

        # Check if the remote script ran at all (sudo may have failed)
        # Strip \r from PTY output (-t allocates TTY which adds carriage returns)
        restart_output=$(echo "$restart_output" | tr -d '\r')
        if echo "$restart_output" | grep -q "^RESTART_OK="; then
            echo "$restart_output" | grep -v "^RESTART_"

            r_fail=$(echo "$restart_output" | grep "^RESTART_FAIL=" | cut -d'=' -f2)
            r_fail="${r_fail:-0}"

            if [ "$r_fail" -gt 0 ] 2>/dev/null; then
                RESTART_RESULT="partial"
                log_warn "Service restart completed with failures"
            else
                RESTART_RESULT="success"
                log_success "Services restarted"
            fi
        else
            # SSH or sudo failed entirely — remote script didn't execute
            RESTART_RESULT="partial"
            log_warn "Service restart failed (sudo requires password?)"
            [ -n "$restart_output" ] && echo -e "  ${GRAY}${restart_output}${NC}" | head -3
        fi
    else
        log_info "Would restart services on RPi (dry-run)"
        RESTART_RESULT="skipped"
    fi
fi

# ============================================================================
# Summary
# ============================================================================

# Determine if any operation had failures
HAS_FAILURES=false
[ "$PROVISION_RESULT" = "partial" ] && HAS_FAILURES=true
[ "$VERIFY_RESULT" = "fail" ] && HAS_FAILURES=true
[ "$RESTART_RESULT" = "partial" ] && HAS_FAILURES=true

echo ""
if [ "$HAS_FAILURES" = true ]; then
    echo -e "${BOLD}${RED}════════════════════════════════════════════════════════════════${NC}"
    if [ "$ACTION_ONLY" = true ]; then
        echo -e "${BOLD}${RED}  ✗ Complete — WITH ISSUES (see details above)${NC}"
    else
        echo -e "${BOLD}${RED}  ✗ Sync Complete — WITH ISSUES (see details above)${NC}"
    fi
    echo -e "${BOLD}${RED}════════════════════════════════════════════════════════════════${NC}"
else
    echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════════════${NC}"
    if [ "$ACTION_ONLY" = true ]; then
        echo -e "${BOLD}${GREEN}  ✓ Complete!${NC}"
    else
        echo -e "${BOLD}${GREEN}  ✓ Sync Complete!${NC}"
    fi
    echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════════════${NC}"
fi
echo ""

if [ -n "$PROVISION_RESULT" ]; then
    if [ "$PROVISION_RESULT" = "success" ]; then
        echo -e "  ${GREEN}✓ Provisioning: All fixes applied successfully${NC}"
    elif [ "$PROVISION_RESULT" = "partial" ]; then
        echo -e "  ${RED}✗ Provisioning: Completed with some failures (see above)${NC}"
    elif [ "$PROVISION_RESULT" = "skipped" ]; then
        echo -e "  ${GRAY}― Provisioning: Skipped (dry-run)${NC}"
    fi
fi

if [ -n "$VERIFY_RESULT" ]; then
    if [ "$VERIFY_RESULT" = "pass" ]; then
        echo -e "  ${GREEN}✓ Verification: All checks passed${NC}"
    elif [ "$VERIFY_RESULT" = "fail" ]; then
        echo -e "  ${RED}✗ Verification: FAILED — see check details above${NC}"
    elif [ "$VERIFY_RESULT" = "skipped" ]; then
        echo -e "  ${GRAY}― Verification: Skipped (dry-run)${NC}"
    fi
fi

if [ -n "$RESTART_RESULT" ]; then
    if [ "$RESTART_RESULT" = "success" ]; then
        echo -e "  ${GREEN}✓ Restart: Services restarted successfully${NC}"
    elif [ "$RESTART_RESULT" = "partial" ]; then
        echo -e "  ${RED}✗ Restart: Completed with some failures (see above)${NC}"
    elif [ "$RESTART_RESULT" = "skipped" ]; then
        echo -e "  ${GRAY}― Restart: Skipped (dry-run)${NC}"
    fi
fi

if [ -n "$PROVISION_RESULT" ] || [ -n "$VERIFY_RESULT" ] || [ -n "$RESTART_RESULT" ]; then
    echo ""
fi

if [ "$ACTION_ONLY" = false ] && [ "$TRIGGER_BUILD" = false ] && [ "$DO_PROVISION" = false ] && \
   [ "$DEPLOY_CROSS" = false ] && [ "$DEPLOY_LOCAL" = false ]; then
    echo -e "${CYAN}Next steps on RPi:${NC}"
    echo ""
    echo "  # SSH to RPi"
    echo -e "  ${YELLOW}ssh ${RPI_USER}@${RPI_IP}${NC}"
    echo ""
    echo "  # Build natively on RPi (if source changed)"
    echo -e "  ${YELLOW}cd ${RPI_DIR}${NC}"
    echo -e "  ${YELLOW}source /opt/ros/jazzy/setup.bash${NC}"
    echo -e "  ${YELLOW}colcon build --symlink-install${NC}"
    echo ""
    echo "  # Run"
    echo -e "  ${YELLOW}source install/setup.bash${NC}"
    echo -e "  ${YELLOW}ros2 launch vehicle_control vehicle_complete.launch.py${NC}"
    echo ""
    echo -e "${GRAY}Tip: Use '$0 --build' to auto-build after sync${NC}"
    echo -e "${GRAY}     Use '$0 --deploy-cross' after './build.sh rpi' for faster deploys${NC}"
elif [ "$DEPLOY_CROSS" = true ] || [ "$DEPLOY_LOCAL" = true ]; then
    echo -e "${CYAN}To run on RPi:${NC}"
    echo -e "  ${YELLOW}ssh ${RPI_USER}@${RPI_IP}${NC}"
    echo -e "  ${YELLOW}source ~/pragati_ros2/install/setup.bash${NC}"
    echo -e "  ${YELLOW}ros2 launch vehicle_control vehicle_complete.launch.py${NC}"
fi

echo ""

# Exit with non-zero if provisioning had failures or verification failed
EXIT_CODE=0
[ "$PROVISION_RESULT" = "partial" ] && EXIT_CODE=1
[ "$VERIFY_RESULT" = "fail" ] && EXIT_CODE=1
exit $EXIT_CODE
