#!/bin/bash
################################################################################
# Module 05: Vision Libraries
# Installs OpenCV and camera-related dependencies
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

log_step "Installing vision libraries"

# OpenCV dependencies
log_install "OpenCV" "apt"
if install_apt_packages \
        libopencv-dev \
        python3-opencv; then
    log_success "OpenCV" "libopencv-dev python3-opencv"
else
    log_fail "OpenCV" "apt install failed"
    exit 1
fi

# USB camera support
log_install "v4l camera support" "apt"
if install_apt_packages \
        v4l-utils \
        libv4l-dev; then
    log_success "v4l camera support" "v4l-utils libv4l-dev"
else
    log_fail "v4l camera support" "apt install failed"
    exit 1
fi

# Image codecs
log_install "image codecs (jpeg/png/tiff)" "apt"
if install_apt_packages \
        libjpeg-dev \
        libpng-dev \
        libtiff-dev; then
    log_success "image codecs (jpeg/png/tiff)" "libjpeg libpng libtiff"
else
    log_fail "image codecs (jpeg/png/tiff)" "apt install failed"
    exit 1
fi
