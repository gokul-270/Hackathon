#!/bin/bash
################################################################################
# Module 01: System Preparation
# Updates system and installs base dependencies
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

log_step "Preparing system"

# Update package lists
apt_update_once

# Install essential build tools
log_install "essential build tools" "apt"
if install_apt_packages \
        build-essential \
        cmake \
        git \
        wget \
        curl \
        software-properties-common \
        python3 \
        python3-pip \
        python3-venv; then
    log_success "essential build tools" "build-essential cmake git wget curl python3"
else
    log_fail "essential build tools" "apt install failed"
    exit 1
fi

# Install common utilities
log_install "common utilities" "apt"
if install_apt_packages \
        vim \
        tmux \
        htop \
        tree; then
    log_success "common utilities" "vim tmux htop tree"
else
    log_fail "common utilities" "apt install failed"
    exit 1
fi

# Install MQTT broker and client tools (for local dev/test of inter-arm comms)
log_install "MQTT packages" "apt"
if install_apt_packages \
        mosquitto \
        mosquitto-clients; then
    log_success "MQTT packages" "mosquitto mosquitto-clients"
else
    log_fail "MQTT packages" "apt install failed"
    exit 1
fi
