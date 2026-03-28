#!/bin/bash
################################################################################
# Pragati Cotton Picker - Ubuntu Development Environment Setup
# Main orchestrator script that runs all setup modules
#
# Created: 2025-02-03
# Version: 1.0.0
#
# Usage:
#   ./setup_ubuntu_dev.sh [options]
#
# Options:
#   --dry-run       Show what would be done without executing
#   --skip-ros2     Skip ROS2 installation (if already installed)
#   --help          Show this help message
#
# Exit Codes:
#   0 - Success
#   1 - Error during setup
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_DIR="${SCRIPT_DIR}/scripts/setup"
MODULES_DIR="${SETUP_DIR}/modules"

# Source common functions
source "${SETUP_DIR}/common.sh"

# Parse arguments
DRY_RUN=false
SKIP_ROS2=false

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --skip-ros2)
            SKIP_ROS2=true
            ;;
        --help)
            head -n 20 "$0" | grep "^#" | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Run with --help for usage"
            exit 1
            ;;
    esac
    shift
done

################################################################################
# Log file setup (skipped in dry-run)
################################################################################

if [ "$DRY_RUN" = false ]; then
    LOG_DIR="${HOME}/.pragati_setup_logs"
    mkdir -p "$LOG_DIR"
    LOG_FILE="${LOG_DIR}/setup_ubuntu_dev_$(date +%Y%m%d_%H%M%S).log"
    exec > >(tee -a "$LOG_FILE") 2>&1
fi

# Record start time (used for total elapsed at the end)
SETUP_START=$SECONDS

################################################################################
# Main Setup Execution
################################################################################

echo "========================================"
echo " Pragati Cotton Picker"
echo " Ubuntu Development Environment Setup"
echo "========================================"
echo "Dry run: $DRY_RUN"
echo "Skip ROS2: $SKIP_ROS2"
echo ""

if [ "$DRY_RUN" = false ]; then
    echo "📝 Installation log: $LOG_FILE"
    echo ""
fi

# Create summary temp file and export so subshell modules can append to it
if [ "$DRY_RUN" = false ]; then
    export SUMMARY_FILE
    SUMMARY_FILE=$(mktemp /tmp/pragati_setup_summary_XXXXXX.txt)
    export TIMING_FILE
    TIMING_FILE=$(mktemp /tmp/pragati_setup_timing_XXXXXX.txt)
    # shellcheck disable=SC2064
    trap "rm -f '${SUMMARY_FILE}' '${TIMING_FILE}'" EXIT
fi

# Module execution order
MODULES=(
    "00_environment_detect.sh"
    "01_system_prep.sh"
)

if [ "$SKIP_ROS2" = false ]; then
    MODULES+=("02_ros2_jazzy.sh")
fi

MODULES+=(
    "03_build_tools.sh"
    "04_cross_compile.sh"
    "05_vision_libs.sh"
    "06_python_deps.sh"
    "07_workspace_build.sh"
)

# Execute modules
for module in "${MODULES[@]}"; do
    module_path="${MODULES_DIR}/${module}"

    if [ ! -f "$module_path" ]; then
        log_error "Module not found: $module"
        exit 1
    fi

    echo ""
    echo "========================================"
    echo " Running: $module"
    echo "========================================"

    if [ "$DRY_RUN" = true ]; then
        log_info "DRY RUN: Would execute $module"
    else
        module_start=$SECONDS
        if bash "$module_path"; then
            module_elapsed=$((SECONDS - module_start))
            [ -n "${TIMING_FILE:-}" ] && echo "MODULE|$module|${module_elapsed}" >> "$TIMING_FILE"
            log_success "$module completed"
        else
            module_elapsed=$((SECONDS - module_start))
            [ -n "${TIMING_FILE:-}" ] && echo "MODULE|$module|${module_elapsed}" >> "$TIMING_FILE"
            log_error "$module failed"
            exit 1
        fi
    fi
done

echo ""
echo "========================================"
echo " Setup Complete!"
echo "========================================"

if [ "$DRY_RUN" = false ]; then
    print_install_summary

    total_elapsed=$((SECONDS - SETUP_START))
    print_timing_summary "$total_elapsed"

    fail_count=$(grep -cF "FAIL|" "$SUMMARY_FILE" 2>/dev/null; true)
    if [ "$fail_count" -eq 0 ]; then
        log_success "Development environment ready!"

        # Auto-install pre-commit hooks if pre-commit is available
        if command -v pre-commit &>/dev/null; then
            log_info "Installing pre-commit hooks..."
            pre-commit install \
                && pre-commit install --hook-type pre-push \
                && log_success "Pre-commit hooks installed (commit + push)" \
                || log_warn "Pre-commit install failed (run 'pre-commit install && pre-commit install --hook-type pre-push' manually)"
        else
            log_warn "pre-commit not found. Install it for code quality hooks:"
            echo "    pip install pre-commit && pre-commit install && pre-commit install --hook-type pre-push"
        fi

        echo ""
        echo "Next steps:"
        echo "  1. Test build: ./build.sh pkg yanthra_move"
        echo "  2. Test cross-compile: ./build.sh rpi"
        echo "  3. Deploy to RPi: ./sync.sh --deploy-cross"
        echo ""
        echo "📝 Full log: $LOG_FILE"
    else
        log_error "Setup completed with errors"
        echo "📝 Full log: $LOG_FILE"
        # Give tee time to flush before exiting
        sleep 0.2
        exit 1
    fi
fi

# Give the tee subprocess time to flush all output to the log file before exiting
sleep 0.2
