#!/bin/bash
################################################################################
# Module 04: Cross-Compilation Setup
# Installs ARM cross-compiler (only on dev machines, not RPi)
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

# Skip if running on RPi
if is_raspberry_pi; then
    log_skip "aarch64 cross-compiler" "running on Raspberry Pi"
    exit 0
fi

log_step "Installing ARM cross-compiler"

log_install "aarch64 cross-compiler" "apt"
if install_apt_packages \
        gcc-aarch64-linux-gnu \
        g++-aarch64-linux-gnu \
        binutils-aarch64-linux-gnu; then
    # Verify installation
    if command -v aarch64-linux-gnu-gcc &>/dev/null; then
        VERSION=$(aarch64-linux-gnu-gcc --version | head -1)
        log_success "aarch64 cross-compiler" "$VERSION"
    else
        log_fail "aarch64 cross-compiler" "binary not found after install"
        exit 1
    fi
else
    log_fail "aarch64 cross-compiler" "apt install failed"
    exit 1
fi
