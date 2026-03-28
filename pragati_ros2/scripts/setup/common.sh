#!/bin/bash
################################################################################
# Common Functions and Variables for Setup Scripts
# Sourced by all setup modules
################################################################################

# Colors
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export BLUE='\033[0;34m'
export PURPLE='\033[0;35m'
export CYAN='\033[0;36m'
export NC='\033[0m'

# Counters (kept for backward compatibility)
export STEP_COUNT=0
export ERROR_COUNT=0
export WARNING_COUNT=0

# Summary file — set by orchestrator before sourcing modules; guarded in all uses.
# When unset, summary functions are silent (safe for direct module invocation).
export SUMMARY_FILE="${SUMMARY_FILE:-}"

################################################################################
# Logging Functions
################################################################################

log_step() {
    ((STEP_COUNT++))
    echo -e "\n${BLUE}[Step $STEP_COUNT]${NC} $*"
}

log_install() {
    # Record an install attempt: log_install "item name" "category"
    # Writes a REQUEST line to the log but does NOT push to the summary array.
    local item="$1" category="${2:-general}"
    echo -e "${BLUE}ℹ️${NC}  [INSTALL] [$category] $item"
}

log_success() {
    local item="$1" detail="${2:-}"
    echo -e "${GREEN}✅${NC} $item${detail:+ ($detail)}"
    [ -n "${SUMMARY_FILE:-}" ] && echo "OK|$item|$detail" >> "$SUMMARY_FILE"
}

log_error() {
    local item="$1" detail="${2:-}"
    echo -e "${RED}❌ ERROR:${NC} $item${detail:+ ($detail)}" >&2
    ((ERROR_COUNT++))
    [ -n "${SUMMARY_FILE:-}" ] && echo "FAIL|$item|$detail" >> "$SUMMARY_FILE"
}

log_fail() {
    # Explicit failure — use in place of log_error when the item name and detail
    # should be recorded in the summary (same behaviour, cleaner call site).
    local item="$1" detail="${2:-}"
    echo -e "${RED}❌ FAIL:${NC} $item${detail:+ ($detail)}" >&2
    ((ERROR_COUNT++))
    [ -n "${SUMMARY_FILE:-}" ] && echo "FAIL|$item|$detail" >> "$SUMMARY_FILE"
}

log_skip() {
    local item="$1" detail="${2:-}"
    echo -e "${YELLOW}⏭  SKIP:${NC} $item${detail:+ ($detail)}"
    [ -n "${SUMMARY_FILE:-}" ] && echo "SKIP|$item|$detail" >> "$SUMMARY_FILE"
}

log_warn() {
    echo -e "${YELLOW}⚠️  WARNING:${NC} $*"
    ((WARNING_COUNT++))
}

log_info() {
    echo -e "${BLUE}ℹ️${NC}  $*"
}

################################################################################
# Summary Table
################################################################################

# Format seconds into human-readable duration (e.g. 75 -> "1m 15s", 8 -> "8s")
format_elapsed() {
    local secs="$1"
    if [ "$secs" -ge 60 ]; then
        printf "%dm %ds" $((secs / 60)) $((secs % 60))
    else
        printf "%ds" "$secs"
    fi
}

print_install_summary() {
    echo ""
    echo -e "${PURPLE}==========================================${NC}"
    echo -e "${PURPLE}  INSTALLATION SUMMARY${NC}"
    echo -e "${PURPLE}==========================================${NC}"

    if [ -z "${SUMMARY_FILE:-}" ] || [ ! -f "$SUMMARY_FILE" ]; then
        echo -e "  ${YELLOW}(no summary data available)${NC}"
        echo -e "${PURPLE}==========================================${NC}"
        echo ""
        return
    fi

    printf "%-8s  %-45s  %s\n" "STATUS" "COMPONENT" "DETAIL"
    printf -- "--------  %-45s  %s\n" "---------------------------------------------" "------"

    local ok=0 fail=0 skip=0
    while IFS='|' read -r status item detail; do
        case "$status" in
            OK)   printf "${GREEN}%-8s${NC}  %-45s  %s\n" "✅ OK"   "$item" "$detail"; ((ok++))   || true ;;
            FAIL) printf "${RED}%-8s${NC}  %-45s  %s\n"  "❌ FAIL" "$item" "$detail"; ((fail++)) || true ;;
            SKIP) printf "${YELLOW}%-8s${NC}  %-45s  %s\n" "⏭ SKIP" "$item" "$detail"; ((skip++)) || true ;;
        esac
    done < "$SUMMARY_FILE"

    echo ""
    echo -e "  ${GREEN}Successful: $ok${NC}   ${RED}Failed: $fail${NC}   ${YELLOW}Skipped: $skip${NC}"
    echo -e "${PURPLE}==========================================${NC}"
    echo ""
}

print_timing_summary() {
    local total_elapsed="${1:-0}"

    echo ""
    echo -e "${PURPLE}==========================================${NC}"
    echo -e "${PURPLE}  TIMING SUMMARY${NC}"
    echo -e "${PURPLE}==========================================${NC}"

    if [ -z "${TIMING_FILE:-}" ] || [ ! -f "$TIMING_FILE" ]; then
        echo -e "  ${YELLOW}(no timing data available)${NC}"
        echo -e "${PURPLE}==========================================${NC}"
        echo ""
        return
    fi

    printf "  %-40s  %s\n" "STEP" "TIME"
    printf "  %-40s  %s\n" "----------------------------------------" "--------"

    while IFS='|' read -r record_type name elapsed; do
        case "$record_type" in
            MODULE)
                printf "  ${CYAN}%-40s${NC}  %s\n" "$name" "$(format_elapsed "$elapsed")"
                ;;
            PKGTIME)
                # Deferred — printed in packages section below
                ;;
        esac
    done < "$TIMING_FILE"

    # Print per-package build timings if any exist
    if grep -q "^PKGTIME|" "$TIMING_FILE" 2>/dev/null; then
        echo ""
        printf "  ${BLUE}%-40s  %s${NC}\n" "PACKAGE (colcon)" "TIME"
        printf "  %-40s  %s\n" "----------------------------------------" "--------"
        while IFS='|' read -r record_type name elapsed; do
            if [ "$record_type" = "PKGTIME" ]; then
                printf "  %-40s  %s\n" "$name" "$elapsed"
            fi
        done < "$TIMING_FILE"
    fi

    echo ""
    echo -e "  ${GREEN}Total elapsed: $(format_elapsed "$total_elapsed")${NC}"
    echo -e "${PURPLE}==========================================${NC}"
    echo ""
}

################################################################################
# Command Execution with Error Handling
################################################################################

run_cmd() {
    local description="$1"
    shift

    echo -n "  $description... "

    if "$@" &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        log_error "Command failed: $*"
        return 1
    fi
}

run_cmd_verbose() {
    local description="$1"
    shift

    log_info "$description"
    if "$@"; then
        log_success "Done"
        return 0
    else
        log_error "Command failed: $*"
        return 1
    fi
}

################################################################################
# System Detection
################################################################################

is_raspberry_pi() {
    [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model
}

is_wsl() {
    grep -qi microsoft /proc/version
}

get_ubuntu_version() {
    lsb_release -rs 2>/dev/null || echo "unknown"
}

################################################################################
# Package Management
################################################################################

apt_update_once() {
    if [ ! -f /tmp/apt_updated_$$ ]; then
        log_step "Updating package lists"
        sudo apt-get update
        touch /tmp/apt_updated_$$
    fi
}

install_apt_packages() {
    apt_update_once

    log_step "Installing packages: $*"
    sudo apt-get install -y "$@"
}

################################################################################
# Python Environment
################################################################################

ensure_python3() {
    if ! command -v python3 &>/dev/null; then
        log_error "Python3 not found"
        return 1
    fi

    local version
    version=$(python3 --version | awk '{print $2}')
    log_info "Python version: $version"
}

setup_venv() {
    local venv_path="${1:-venv}"

    if [ ! -d "$venv_path" ]; then
        log_step "Creating Python virtual environment"
        python3 -m venv "$venv_path"
    fi

    log_info "Virtual environment ready at: $venv_path"
}

################################################################################
# Exit Handler
################################################################################

cleanup() {
    rm -f /tmp/apt_updated_$$
}

trap cleanup EXIT
