#!/bin/bash
################################################################################
# Module 02: ROS2 Jazzy Installation
# Installs ROS2 Jazzy Jalisco
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

log_step "Installing ROS2 Jazzy"

# Check if already installed
if command -v ros2 &>/dev/null; then
    log_info "ROS2 already installed: $(ros2 --version)"
else
    # Add ROS2 repository
    log_step "Adding ROS2 repository"
    sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

    # Update and install
    apt_update_once
    log_install "ros-jazzy-desktop ros-jazzy-ros-base" "apt"
    if install_apt_packages ros-jazzy-desktop ros-jazzy-ros-base; then
        log_success "ros-jazzy-desktop" "installed"
    else
        log_fail "ros-jazzy-desktop" "apt install failed"
        exit 1
    fi

    # Install development tools
    log_install "python3-colcon-common-extensions python3-rosdep python3-vcstool" "apt"
    if install_apt_packages \
            python3-colcon-common-extensions \
            python3-rosdep \
            python3-vcstool; then
        log_success "ROS2 dev tools" "colcon, rosdep, vcstool"
    else
        log_fail "ROS2 dev tools" "apt install failed"
        exit 1
    fi

    # Initialize rosdep
    if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
        log_step "Initializing rosdep"
        sudo rosdep init
    fi

    rosdep update

    log_success "ROS2 Jazzy installed"
fi

################################################################################
# Install ros-jazzy-rmw-cyclonedds-cpp (not included in ros-jazzy-desktop)
################################################################################

if dpkg -l ros-jazzy-rmw-cyclonedds-cpp 2>/dev/null | grep -q "^ii"; then
    log_skip "ros-jazzy-rmw-cyclonedds-cpp" "already installed"
else
    log_install "ros-jazzy-rmw-cyclonedds-cpp" "apt"
    apt_update_once
    if sudo apt-get install -y ros-jazzy-rmw-cyclonedds-cpp; then
        # Verify the package is actually present after install
        if dpkg -l ros-jazzy-rmw-cyclonedds-cpp 2>/dev/null | grep -q "^ii"; then
            log_success "ros-jazzy-rmw-cyclonedds-cpp" "installed"
        else
            log_fail "ros-jazzy-rmw-cyclonedds-cpp" "required RMW not installed"
            exit 1
        fi
    else
        log_fail "ros-jazzy-rmw-cyclonedds-cpp" "apt install failed"
        exit 1
    fi
fi
