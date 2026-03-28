#!/bin/bash
###############################################################################
# Module 00: Environment Detection
# Detects system type, OS version, and sets environment variables
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

log_step "Detecting environment"
log_install "environment detection" "system"

# Detect system type
if is_raspberry_pi; then
    export SYSTEM_TYPE="raspberry_pi"
    log_info "System: Raspberry Pi"
elif is_wsl; then
    export SYSTEM_TYPE="wsl"
    log_info "System: WSL"
else
    export SYSTEM_TYPE="ubuntu"
    log_info "System: Ubuntu (native)"
fi

# Detect Ubuntu version
UBUNTU_VER=$(get_ubuntu_version)
export UBUNTU_VERSION="$UBUNTU_VER"
log_info "Ubuntu version: $UBUNTU_VER"

# Detect architecture
ARCH=$(uname -m)
export ARCH="$ARCH"
log_info "Architecture: $ARCH"

# Check if cross-compilation is needed
if [ "$SYSTEM_TYPE" = "raspberry_pi" ]; then
    export NEEDS_CROSS_COMPILE=false
    log_info "Cross-compilation: Not needed (running on RPi)"
    log_skip "cross-compilation" "running on RPi"
else
    export NEEDS_CROSS_COMPILE=true
    log_info "Cross-compilation: Needed (dev machine)"
fi

log_success "environment detection" "system=$SYSTEM_TYPE arch=$ARCH ubuntu=$UBUNTU_VER"
