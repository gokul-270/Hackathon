#!/bin/bash

################################################################################
# Pragati Cotton Picker - Complete Raspberry Pi Setup Script
#
# ⚠️  NOTE: For Ubuntu development machines, use setup_ubuntu_dev.sh instead!
# This script is specifically for Raspberry Pi deployment.
#
# See also:
#   - setup_ubuntu_dev.sh (Ubuntu development environment)
#   - docs/UBUNTU_SETUP_GUIDE.md (Ubuntu setup guide)
#   - docs/VERSION_ALIGNMENT_PROCEDURE.md (Multi-device management)
#
# This script installs ALL dependencies needed for a new Raspberry Pi to run
# the cotton picker ROS2 system from scratch.
#
# Usage:
#   chmod +x setup_raspberry_pi.sh
#   ./setup_raspberry_pi.sh
#
# What it does:
#   1. Updates system packages
#   2. Installs ROS2 Jazzy (if not present)
#   3. Installs all ROS2 dependencies
#   4. Installs hardware dependencies (CAN, GPIO, pigpio)
#   5. Installs vision dependencies (OpenCV, DepthAI)
#   6. Installs Python dependencies (from requirements.txt)
#   7. Configures system for optimal performance
#   8. Sets up CAN interface
#   9. Configures pigpio daemon
#   10. Builds the workspace
################################################################################

set -e  # Exit on any error

# Get script directory (needed for CAN watchdog installation)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

################################################################################
# LOGGING SETUP
################################################################################
LOG_DIR="$HOME/.pragati_setup_logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/setup_$(date +%Y%m%d_%H%M%S).log"
INSTALL_SUMMARY=()

# Tee all output to the log file (stdout+stderr)
exec > >(tee -a "$LOG_FILE") 2>&1

log_install() {
    # Record an install attempt: log_install "item name" "category"
    local item="$1" category="${2:-general}"
    echo "[$(date +%H:%M:%S)] [REQUEST] [$category] $item" >> "$LOG_FILE"
}

log_success() {
    local item="$1" detail="${2:-}"
    INSTALL_SUMMARY+=("OK|$item|$detail")
    echo "[$(date +%H:%M:%S)] [SUCCESS] $item${detail:+ ($detail)}" >> "$LOG_FILE"
}

log_fail() {
    local item="$1" detail="${2:-}"
    INSTALL_SUMMARY+=("FAIL|$item|$detail")
    echo "[$(date +%H:%M:%S)] [FAILED]  $item${detail:+ ($detail)}" >> "$LOG_FILE"
}

log_skip() {
    local item="$1" detail="${2:-}"
    INSTALL_SUMMARY+=("SKIP|$item|$detail")
    echo "[$(date +%H:%M:%S)] [SKIPPED] $item${detail:+ ($detail)}" >> "$LOG_FILE"
}

print_install_summary() {
    echo ""
    echo -e "${PURPLE}==========================================${NC}"
    echo -e "${PURPLE}  INSTALLATION SUMMARY${NC}"
    echo -e "${PURPLE}==========================================${NC}"
    printf "%-6s  %-45s  %s\n" "STATUS" "COMPONENT" "DETAIL"
    printf -- "------  %-45s  %s\n" "---------------------------------------------" "------"
    local ok=0 fail=0 skip=0
    for entry in "${INSTALL_SUMMARY[@]}"; do
        IFS='|' read -r status item detail <<< "$entry"
        case "$status" in
            OK)   printf "${GREEN}%-6s${NC}  %-45s  %s\n" "✅ OK" "$item" "$detail"; ((ok++)) ;;
            FAIL) printf "${RED}%-6s${NC}  %-45s  %s\n"  "❌ FAIL" "$item" "$detail"; ((fail++)) ;;
            SKIP) printf "${YELLOW}%-6s${NC}  %-45s  %s\n" "⏭ SKIP" "$item" "$detail"; ((skip++)) ;;
        esac
    done
    echo ""
    echo -e "  ${GREEN}Successful: $ok${NC}   ${RED}Failed: $fail${NC}   ${YELLOW}Skipped: $skip${NC}"
    echo -e "  ${CYAN}Full log: $LOG_FILE${NC}"
    echo -e "${PURPLE}==========================================${NC}"
    echo ""
}

print_status() {
    echo -e "${1}${2}${NC}"
}

print_header() {
    echo ""
    print_status $PURPLE "=========================================="
    print_status $PURPLE "$1"
    print_status $PURPLE "=========================================="
    echo ""
}

print_error() {
    print_status $RED "❌ ERROR: $1"
    exit 1
}

# Check if running on Raspberry Pi
check_raspberry_pi() {
    if [ ! -f /proc/device-tree/model ] || ! grep -q "Raspberry Pi" /proc/device-tree/model; then
        print_status $YELLOW "⚠️  Warning: This doesn't appear to be a Raspberry Pi"
        read -p "Continue anyway? (y/n): " continue_setup
        if [[ ! $continue_setup =~ ^[Yy]$ ]]; then
            exit 0
        fi
    else
        MODEL=$(tr -d "\0" < /proc/device-tree/model)
        print_status $GREEN "✅ Detected: $MODEL"
    fi
}

print_header "🤖 PRAGATI COTTON PICKER - RASPBERRY PI SETUP"
print_status $CYAN "This script will install ALL dependencies for a new Raspberry Pi"
echo ""
print_status $BLUE "📝 Installation log: $LOG_FILE"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Please do NOT run this script as root. Run as normal user with sudo privileges."
fi

# Check for sudo privileges
if ! sudo -v; then
    print_error "This script requires sudo privileges. Please run with a user that has sudo access."
fi

check_raspberry_pi

print_status $YELLOW "⚙️  This will install:"
echo "  • ROS2 Jazzy (if not installed)"
echo "  • Build tools (colcon, rosdep, ccache, ninja)"
echo "  • Hardware support (CAN, GPIO, pigpio)"
echo "  • Vision libraries (OpenCV, DepthAI)"
echo "  • Python dependencies"
echo "  • System configurations"
echo ""
read -p "Continue with installation? (y/n): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

################################################################################

################################################################################
# STEP 0: Fix System Clock (Critical for apt)
################################################################################
print_header "STEP 0/10: Synchronizing System Clock"
print_status $YELLOW "🕐 Checking system time..."

# Check if time is significantly off (more than 1 day)
CURRENT_YEAR=$(date +%Y)
if [ "$CURRENT_YEAR" -lt 2025 ]; then
    print_status $YELLOW "⚠️  System clock appears to be incorrect"
    print_status $YELLOW "🔧 Attempting to sync time with NTP..."

    # Install NTP client if not present
    if ! command -v timedatectl &> /dev/null; then
        sudo apt install -y systemd-timesyncd 2>/dev/null || true
    fi

    # Enable and start time sync
    sudo timedatectl set-ntp true 2>/dev/null || true

    # Wait a moment for sync
    sleep 2

    # Force immediate sync
    sudo systemctl restart systemd-timesyncd 2>/dev/null || true
    sleep 3

    # Check if fixed
    NEW_YEAR=$(date +%Y)
    if [ "$NEW_YEAR" -ge 2025 ]; then
        print_status $GREEN "✅ System clock synchronized: $(date)"
    else
        print_status $YELLOW "⚠️  Automatic sync failed, trying manual NTP sync..."
        sudo ntpdate -s time.nist.gov 2>/dev/null || sudo ntpdate -s pool.ntp.org 2>/dev/null || true
        print_status $YELLOW "Current time: $(date)"
        print_status $YELLOW "If time is still wrong, manually set it with: sudo date -s 'YYYY-MM-DD HH:MM:SS'"
    fi
else
    print_status $GREEN "✅ System clock is correct: $(date)"
fi

# STEP 1: Update System and Prerequisites
################################################################################
print_header "STEP 1/11: Updating System & Prerequisites"
log_install "system packages" "apt"
print_status $YELLOW "📦 Updating package lists..."
if sudo apt update && sudo apt upgrade -y; then
    log_success "system packages" "apt update + upgrade"
else
    log_fail "system packages" "apt update/upgrade failed"
fi

# Install openssh-server if not present (required for remote access)
if ! systemctl is-active --quiet ssh 2>/dev/null; then
    log_install "openssh-server" "apt"
    print_status $YELLOW "🔐 Installing SSH server..."
    if sudo apt install -y openssh-server && sudo systemctl enable ssh && sudo systemctl start ssh; then
        log_success "openssh-server" "installed and started"
        print_status $GREEN "✅ SSH server installed and started"
    else
        log_fail "openssh-server"
    fi
else
    log_skip "openssh-server" "already running"
fi

# Create required groups that don't exist by default on Ubuntu 24.04
print_status $YELLOW "👥 Creating required system groups..."
for grp in gpio spi i2c dialout plugdev; do
    if ! getent group $grp > /dev/null 2>&1; then
        sudo groupadd -f $grp
        print_status $GREEN "✅ Created group: $grp"
    fi
done

print_status $GREEN "✅ System updated"

################################################################################
# STEP 2: Install ROS2 Jazzy
################################################################################
print_header "STEP 2/11: Installing ROS2 Jazzy"

log_install "ros-jazzy-desktop" "apt"
log_install "ros-jazzy-rmw-cyclonedds-cpp" "apt"
if command -v ros2 &> /dev/null; then
    log_skip "ros-jazzy-desktop" "already installed"
    print_status $GREEN "✅ ROS2 is already installed"
    ros2 --help | head -1 || echo "ROS2 Jazzy"
else
    print_status $YELLOW "📦 Installing ROS2 Jazzy for Ubuntu..."

    # Set locale
    sudo apt install -y locales
    sudo locale-gen en_US en_US.UTF-8
    sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
    export LANG=en_US.UTF-8

    # Setup sources
    sudo apt install -y software-properties-common
    sudo add-apt-repository universe -y

    # Add ROS2 GPG key
    sudo apt install -y curl
    sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

    # Add repository to sources list
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

    sudo apt update
    if sudo apt install -y ros-jazzy-desktop; then
        log_success "ros-jazzy-desktop"
    else
        log_fail "ros-jazzy-desktop"
    fi

    # Install CycloneDDS RMW (required - ros-jazzy-desktop does NOT include it)
    if sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp; then
        log_success "ros-jazzy-rmw-cyclonedds-cpp" "installed with ros-jazzy-desktop"
    else
        log_fail "ros-jazzy-rmw-cyclonedds-cpp"
    fi

    if ! grep -q "source /opt/ros/jazzy/setup.bash" ~/.bashrc; then
        echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
    fi
    source /opt/ros/jazzy/setup.bash

    print_status $GREEN "✅ ROS2 Jazzy installed successfully"
fi

# Ensure CycloneDDS RMW is installed (may be missing if ROS2 was pre-installed)
if ! dpkg -l ros-jazzy-rmw-cyclonedds-cpp &>/dev/null; then
    print_status $YELLOW "📦 Installing missing CycloneDDS RMW..."
    if sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp; then
        log_success "ros-jazzy-rmw-cyclonedds-cpp" "installed (was missing from pre-installed ROS2)"
        print_status $GREEN "✅ CycloneDDS RMW installed"
    else
        log_fail "ros-jazzy-rmw-cyclonedds-cpp"
    fi
else
    log_skip "ros-jazzy-rmw-cyclonedds-cpp" "already installed"
fi

# Source ROS2 for this session
source /opt/ros/jazzy/setup.bash 2>/dev/null || true

################################################################################
# STEP 3: Install ROS2 Build Tools
################################################################################
print_header "STEP 3/11: Installing ROS2 Build Tools"
print_status $YELLOW "📦 Installing colcon, rosdep, vcstool..."
log_install "ROS2 build tools (colcon/rosdep/vcstool)" "apt"

if sudo apt install -y \
    python3-colcon-common-extensions \
    python3-colcon-mixin \
    python3-rosdep \
    python3-vcstool \
    python3-pip \
    python3-setuptools \
    python3-wheel; then
    log_success "ROS2 build tools (colcon/rosdep/vcstool)"
else
    log_fail "ROS2 build tools (colcon/rosdep/vcstool)"
fi

# Initialize rosdep
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    print_status $YELLOW "🔧 Initializing rosdep..."
    sudo rosdep init
fi
rosdep update

print_status $GREEN "✅ Build tools installed"

################################################################################
# STEP 4: Install Build Optimization Tools
################################################################################
print_header "STEP 4/11: Installing Build Optimization Tools"
print_status $YELLOW "Installing ccache, ninja-build, and mold..."
log_install "ccache + ninja-build + mold + cmake" "apt"

if sudo apt install -y \
    ccache \
    ninja-build \
    mold \
    cmake; then
    log_success "ccache + ninja-build + mold + cmake"
else
    log_fail "ccache + ninja-build + cmake"
fi

# Configure ccache
if command -v ccache &> /dev/null; then
    ccache --set-config=max_size=5G
    ccache --set-config=compression=true
    print_status $GREEN "✅ ccache installed (5GB cache, ~98% faster rebuilds)"
fi

if command -v ninja &> /dev/null; then
    print_status $GREEN "✅ Ninja build system installed (~10-15% faster builds)"
fi

################################################################################
# STEP 5: Install Hardware Dependencies
################################################################################
print_header "STEP 5/11: Installing Hardware Dependencies"
print_status $YELLOW "🔌 Installing CAN, GPIO, Serial support..."
log_install "hardware deps (can-utils/i2c/serial/gpio)" "apt"

if sudo apt install -y \
    can-utils \
    i2c-tools \
    iw \
    python3-smbus \
    python3-serial \
    python3-spidev \
    net-tools \
    build-essential \
    libudev-dev; then
    log_success "hardware deps (can-utils/i2c/serial/gpio/iw)"
else
    log_fail "hardware deps (can-utils/i2c/serial/gpio/iw)"
fi

# Install pigpio for GPIO control (may not be available on all Ubuntu versions)
print_status $YELLOW "🔌 Installing pigpio..."
log_install "pigpio" "apt/source"

# Check if pigpiod is already installed
if command -v pigpiod &> /dev/null; then
    log_skip "pigpio" "already installed at $(which pigpiod)"
    print_status $GREEN "✅ pigpio already installed: $(which pigpiod)"
elif sudo apt install -y pigpio python3-pigpio libpigpio-dev 2>/dev/null; then
    log_success "pigpio" "installed from apt"
    print_status $GREEN "✅ pigpio installed from apt"
else
    print_status $YELLOW "⚠️  pigpio not available in apt, building from source..."
    cd /tmp
    if [ ! -f master.zip ]; then
        wget https://github.com/joan2937/pigpio/archive/master.zip
    fi
    rm -rf pigpio-master 2>/dev/null
    unzip -o master.zip
    cd pigpio-master
    if make && sudo make install; then
        log_success "pigpio" "built from source"
        print_status $GREEN "✅ pigpio built and installed from source"
    else
        log_fail "pigpio" "source build failed"
    fi
    cd -
    rm -rf /tmp/pigpio-master /tmp/master.zip 2>/dev/null || true
fi

# Install GPIO libraries (for RPi 4/5)
print_status $YELLOW "🔌 Installing GPIO libraries..."
log_install "GPIO libraries (libgpiod/python3-rpi.gpio)" "apt"
if sudo apt install -y libgpiod-dev gpiod python3-rpi.gpio; then
    log_success "GPIO libraries (libgpiod/python3-rpi.gpio)"
else
    log_fail "GPIO libraries (libgpiod/python3-rpi.gpio)"
fi

# Enable and start pigpio daemon with -l flag (required for IPv4 localhost binding)
# Always create/update our custom service to ensure -l flag is used
print_status $YELLOW "🔧 Configuring pigpiod systemd service..."

# Determine pigpiod path
if [ -f /usr/local/bin/pigpiod ]; then
    PIGPIOD_PATH="/usr/local/bin/pigpiod"
elif [ -f /usr/bin/pigpiod ]; then
    PIGPIOD_PATH="/usr/bin/pigpiod"
else
    PIGPIOD_PATH="pigpiod"
fi

# Create systemd service (removed -l flag - was causing IPv6-only binding)
sudo tee /etc/systemd/system/pigpiod.service > /dev/null <<EOFPIGPIO
[Unit]
Description=Pigpio daemon for GPIO operations
After=network.target

[Service]
ExecStart=${PIGPIOD_PATH}
ExecStop=/bin/systemctl kill pigpiod
Type=forking
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOFPIGPIO

sudo systemctl daemon-reload
sudo systemctl enable pigpiod 2>/dev/null || true
sudo systemctl restart pigpiod 2>/dev/null || true

# Create udev rules for GPIO access
print_status $YELLOW "🔧 Setting up GPIO udev rules..."
sudo tee /etc/udev/rules.d/99-gpio.rules > /dev/null <<'EOFGPIO'
SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"
EOFGPIO
sudo udevadm control --reload-rules
sudo udevadm trigger

# Install MQTT broker and clients (mosquitto)
# - mosquitto broker runs on the vehicle RPi (multi-arm coordination)
# - mosquitto-clients needed on all RPis for MQTT pub/sub testing
print_status $YELLOW "📡 Installing MQTT (mosquitto) broker and clients..."
log_install "mosquitto + mosquitto-clients" "apt"
if sudo apt install -y mosquitto mosquitto-clients; then
    log_success "mosquitto + mosquitto-clients"
    # Don't enable broker by default — provision handles vehicle-specific config
    # (external listener, allow_anonymous, etc.)
    sudo systemctl disable mosquitto 2>/dev/null || true
    sudo systemctl stop mosquitto 2>/dev/null || true
    print_status $GREEN "✅ MQTT installed (broker disabled by default, enabled on vehicle via provision)"
else
    log_fail "mosquitto + mosquitto-clients"
fi

print_status $GREEN "✅ Hardware dependencies installed"

################################################################################
# STEP 6: Install Vision Dependencies
################################################################################
print_header "STEP 6/11: Installing Vision Dependencies"
print_status $YELLOW "📷 Installing OpenCV and DepthAI..."
log_install "OpenCV (libopencv-dev + python3-opencv + PCL)" "apt"

# Install OpenCV and PCL
if sudo apt install -y \
    libopencv-dev \
    python3-opencv \
    libopencv-contrib-dev \
    libpcl-dev; then
    log_success "OpenCV (libopencv-dev + python3-opencv + PCL)"
else
    log_fail "OpenCV (libopencv-dev + python3-opencv + PCL)"
fi

# Install DepthAI dependencies
print_status $YELLOW "📷 Installing DepthAI SDK (version 2.30)..."
sudo apt install -y \
    libusb-1.0-0-dev \
    udev \
    cmake \
    git

# Install DepthAI Python package (pinned to version 2.30)
print_status $YELLOW "📦 Installing DepthAI Python SDK 2.30..."
log_install "depthai==2.30.0.0 (Python SDK)" "pip"
if python3 -m pip install --break-system-packages depthai==2.30.0.0 depthai-sdk; then
    log_success "depthai==2.30.0.0 (Python SDK)"
else
    log_fail "depthai==2.30.0.0 (Python SDK)"
fi

# NOTE: DepthAI C++ library will be installed via ROS2 apt packages (ros-jazzy-depthai)
# This avoids the 30+ minute source build on RPi
print_status $GREEN "✅ DepthAI C++ will be installed via ROS2 packages (Step 7)"

# Verify DepthAI installation
if python3 -c "import depthai as dai; print('DepthAI version:', dai.__version__)" 2>/dev/null; then
    DEPTHAI_VER=$(python3 -c "import depthai as dai; print(dai.__version__)" 2>/dev/null)
    if [ "$DEPTHAI_VER" = "2.30.0.0" ]; then
        print_status $GREEN "✅ DepthAI Python SDK 2.30.0.0 installed successfully"
    else
        print_status $YELLOW "⚠️  DepthAI installed but version is $DEPTHAI_VER (expected 2.30.0.0)"
    fi
else
    print_status $YELLOW "⚠️  DepthAI Python verification failed (may need reboot)"
fi

# Install DepthAI system-wide for scripts like aruco_finder
print_status $YELLOW "🔧 Installing DepthAI system-wide for global scripts..."
if ! sudo -H python3 -c "import depthai" 2>/dev/null; then
    sudo -H pip3 install depthai==2.30.0.0 --break-system-packages
    print_status $GREEN "✅ DepthAI installed system-wide"
else
    print_status $YELLOW "⚠️  DepthAI already installed system-wide"
fi

# Add udev rules for OAK-D camera
print_status $YELLOW "🔧 Setting up OAK-D camera permissions..."
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

print_status $GREEN "✅ Vision dependencies installed"

################################################################################
# STEP 7: Install ROS2 Package Dependencies
################################################################################
print_header "STEP 7/11: Installing ROS2 Package Dependencies"
print_status $YELLOW "📦 Installing ROS2 packages..."
log_install "ROS2 core packages (rclcpp/tf2/cv-bridge/etc.)" "apt"

if sudo apt install -y \
    ros-jazzy-ament-cmake \
    ros-jazzy-ament-cmake-python \
    ros-jazzy-rclcpp \
    ros-jazzy-rclpy \
    ros-jazzy-std-msgs \
    ros-jazzy-std-srvs \
    ros-jazzy-sensor-msgs \
    ros-jazzy-geometry-msgs \
    ros-jazzy-trajectory-msgs \
    ros-jazzy-control-msgs \
    ros-jazzy-lifecycle-msgs \
    ros-jazzy-vision-msgs \
    ros-jazzy-cv-bridge \
    ros-jazzy-image-transport \
    ros-jazzy-camera-info-manager \
    ros-jazzy-compressed-image-transport \
    ros-jazzy-tf2 \
    ros-jazzy-tf2-ros \
    ros-jazzy-tf2-geometry-msgs \
    ros-jazzy-hardware-interface \
    ros-jazzy-controller-manager \
    ros-jazzy-controller-interface \
    ros-jazzy-realtime-tools \
    ros-jazzy-pluginlib \
    ros-jazzy-diagnostic-updater \
    ros-jazzy-diagnostic-msgs \
    ros-jazzy-urdf \
    ros-jazzy-xacro \
    ros-jazzy-robot-state-publisher \
    ros-jazzy-joint-state-publisher \
    ros-jazzy-geometric-shapes \
    ros-jazzy-resource-retriever \
    ros-jazzy-yaml-cpp-vendor \
    ros-jazzy-rviz2 \
    ros-jazzy-rqt \
    ros-jazzy-rqt-common-plugins \
    ros-jazzy-rosidl-default-generators \
    ros-jazzy-rosidl-default-runtime; then
    log_success "ROS2 core packages (rclcpp/tf2/cv-bridge/etc.)"
else
    log_fail "ROS2 core packages (rclcpp/tf2/cv-bridge/etc.)"
fi

# Install DepthAI ROS2 packages
log_install "ROS2 DepthAI packages (ros-jazzy-depthai*)" "apt"
if sudo apt install -y \
    ros-jazzy-depthai \
    ros-jazzy-depthai-ros \
    ros-jazzy-depthai-bridge \
    ros-jazzy-depthai-ros-msgs; then
    log_success "ROS2 DepthAI packages (ros-jazzy-depthai*)"
else
    log_fail "ROS2 DepthAI packages (ros-jazzy-depthai*)" "may need manual installation"
    print_status $YELLOW "⚠️  Some DepthAI ROS packages may need manual installation"
fi

print_status $GREEN "✅ ROS2 packages installed"

################################################################################
# STEP 8: Install Python Dependencies
################################################################################
print_header "STEP 8/11: Installing Python Dependencies"
print_status $YELLOW "🐍 Installing Python packages..."
log_install "Python system packages (numpy/scipy/pytest/etc.)" "apt"

# Install system Python packages
# Note: python3-cantools and python3-opencv-contrib-python don't exist as apt packages
# They will be installed via pip instead
if sudo apt install -y \
    python3-numpy \
    python3-scipy \
    python3-yaml \
    python3-jsonschema \
    python3-pytest \
    python3-pytest-cov \
    python3-pigpio \
    python3-setproctitle; then
    log_success "Python system packages (numpy/scipy/pytest/etc.)"
else
    log_fail "Python system packages (numpy/scipy/pytest/etc.)"
fi

# Install user Python packages (--break-system-packages for Ubuntu 24.04)
log_install "Python pip packages (python-can/paho-mqtt/flask/etc.)" "pip"
if python3 -m pip install --break-system-packages \
    python-can \
    cantools \
    pyserial \
    RPi.GPIO \
    pyyaml \
    jsonschema \
    coloredlogs \
    structlog \
    empy \
    catkin_pkg \
    lark \
    setuptools \
    typeguard \
    "numpy<2.0.0" \
    opencv-python \
    opencv-contrib-python \
    paho-mqtt \
    flask \
    flask-cors \
    websockets \
    simple-pid \
    fastapi \
    uvicorn \
    httpx \
    psutil \
    zeroconf; then
    log_success "Python pip packages (python-can/paho-mqtt/flask/fastapi/etc.)"
else
    log_fail "Python pip packages (python-can/paho-mqtt/flask/fastapi/etc.)"
fi

print_status $GREEN "✅ Python dependencies installed"

################################################################################
# STEP 9: Configure System for Robot Operation
################################################################################
print_header "STEP 9/11: Configuring System"
print_status $YELLOW "⚙️  Applying system configurations..."

# Add user to required groups (groups were created in Step 1)
print_status $YELLOW "👥 Adding user to required groups..."
for grp in dialout gpio i2c spi video plugdev; do
    if getent group $grp > /dev/null 2>&1; then
        sudo usermod -a -G $grp $USER 2>/dev/null || true
    fi
done
print_status $GREEN "✅ User added to hardware groups"

# Configure MCP2515 CAN HAT in boot config (required for RPi CAN hardware)
print_status $YELLOW "🔧 Configuring MCP2515 CAN HAT..."
BOOT_CONFIG=""
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    BOOT_CONFIG="/boot/config.txt"
fi

if [ -n "$BOOT_CONFIG" ]; then
    # Enable SPI if not already enabled
    if ! grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
        echo "dtparam=spi=on" | sudo tee -a "$BOOT_CONFIG"
        print_status $GREEN "✅ SPI enabled"
    fi

    # CAN HAT detection — only add overlay if SPI hardware present
    if ls /dev/spidev* 1>/dev/null 2>&1; then
        print_status $GREEN "✅ SPI devices detected — CAN HAT likely present"

        # Add MCP2515 overlay if not present (8MHz oscillator for Pragati CAN HAT)
        if ! grep -q "mcp2515" "$BOOT_CONFIG"; then
            cat << 'EOFMCP' | sudo tee -a "$BOOT_CONFIG"

# MCP2515 CAN HAT configuration (8MHz oscillator)
# Change oscillator value if your CAN HAT uses different crystal:
#   8MHz:  oscillator=8000000 (Pragati default)
#   12MHz: oscillator=12000000
#   16MHz: oscillator=16000000
dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25,spimaxfrequency=1000000
EOFMCP
            print_status $GREEN "✅ MCP2515 CAN overlay added to boot config"
            print_status $YELLOW "⚠️  REBOOT REQUIRED for CAN hardware to be detected"
            NEEDS_REBOOT=1
        else
            print_status $GREEN "✅ MCP2515 CAN overlay already configured"
        fi
    else
        print_status $YELLOW "⚠️  No SPI devices detected (no CAN HAT) — skipping CAN dtoverlay"
    fi
else
    print_status $YELLOW "⚠️  Boot config not found, skipping MCP2515 setup"
fi

# Remove 'splash' from kernel cmdline on arm RPis (headless).
# plymouth-start has ConditionKernelCommandLine=splash — without it, the entire
# plymouth chain is skipped. On headless RPis, plymouth-quit-wait hangs permanently
# because plymouthd has no display, blocking multi-user.target and graphical.target.
CMDLINE_FILE=""
if [ -f /boot/firmware/cmdline.txt ]; then
    CMDLINE_FILE="/boot/firmware/cmdline.txt"
elif [ -f /boot/cmdline.txt ]; then
    CMDLINE_FILE="/boot/cmdline.txt"
fi
if [ -n "$CMDLINE_FILE" ]; then
    ROLE_CHECK=$(hostname 2>/dev/null)
    if echo "$ROLE_CHECK" | grep -qi 'arm'; then
        if grep -q '\bsplash\b' "$CMDLINE_FILE"; then
            sudo sed -i 's/ splash//' "$CMDLINE_FILE"
            print_status $GREEN "Removed 'splash' from $CMDLINE_FILE (headless arm RPi)"
            NEEDS_REBOOT=1
        else
            print_status $GREEN "'splash' already absent from $CMDLINE_FILE"
        fi
    else
        print_status $GREEN "Kept 'splash' in $CMDLINE_FILE (vehicle may have monitor)"
    fi
else
    print_status $YELLOW "Kernel cmdline file not found, skipping splash removal"
fi

# Configure CAN interface (production default: 500 kbps)
# Note: Use scripts/setup_can.sh or scripts/maintenance/can/install_can_watchdog.sh for runtime setup
print_status $YELLOW "🔧 Configuring CAN interface..."

# Create interfaces.d directory if it doesn't exist (Ubuntu 24.04 uses netplan by default)
if [ ! -d /etc/network/interfaces.d ]; then
    sudo mkdir -p /etc/network/interfaces.d
fi

if [ ! -f /etc/network/interfaces.d/can0 ]; then
    sudo tee /etc/network/interfaces.d/can0 > /dev/null <<'EOFCAN'
# CAN0 interface configuration for MG6010 motors (500 kbps)
# Note: This is a fallback config. Prefer using:
#   sudo ./scripts/setup_can.sh can0 500000 100
# Or install the watchdog service:
#   sudo ./scripts/maintenance/can/install_can_watchdog.sh can0
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
    up /sbin/ip link set can0 up
    down /sbin/ip link set can0 down
EOFCAN
    print_status $GREEN "✅ CAN0 interface configured (500 kbps for MG6010 motors)"
else
    print_status $YELLOW "⚠️  CAN0 interface already configured"
fi

# Install CAN watchdog service for auto-recovery
print_status $YELLOW "🔧 Installing CAN watchdog service..."
if [ -f "$SCRIPT_DIR/scripts/maintenance/can/install_can_watchdog.sh" ]; then
    if ! systemctl is-enabled can-watchdog@can0 &>/dev/null; then
        # Copy watchdog script to system location
        sudo cp "$SCRIPT_DIR/scripts/maintenance/can/can_watchdog.sh" /usr/local/sbin/can_watchdog.sh
        sudo chmod +x /usr/local/sbin/can_watchdog.sh

        # Copy systemd service if it exists
        if [ -f "$SCRIPT_DIR/systemd/can-watchdog@.service" ]; then
            sudo cp "$SCRIPT_DIR/systemd/can-watchdog@.service" /etc/systemd/system/
            sudo systemctl daemon-reload
            sudo systemctl enable can-watchdog@can0.service
            print_status $GREEN "✅ CAN watchdog service installed and enabled"
        else
            print_status $YELLOW "⚠️  CAN watchdog service file not found, skipping"
        fi
    else
        print_status $GREEN "✅ CAN watchdog already installed"
    fi
else
    print_status $YELLOW "⚠️  CAN watchdog script not found at $SCRIPT_DIR/scripts/maintenance/can/"
fi

# Load CAN kernel modules
print_status $YELLOW "🔧 Loading CAN kernel modules..."
sudo modprobe can || true
sudo modprobe can-raw || true
sudo modprobe can-bcm || true
sudo modprobe mcp251x || true

# Make CAN modules load at boot
if ! grep -q "^can$" /etc/modules 2>/dev/null; then
    echo "can" | sudo tee -a /etc/modules
    echo "can-raw" | sudo tee -a /etc/modules
    echo "can-bcm" | sudo tee -a /etc/modules
fi

# Configure WiFi auto-reconnect (fixes issue where RPi doesn't reconnect after hotspot restarts)
print_status $YELLOW "📶 Configuring WiFi auto-reconnect..."

# 1. Disable WiFi power saving (prevents card from missing AP returning)
if [ ! -f /etc/NetworkManager/conf.d/wifi-powersave.conf ]; then
    sudo mkdir -p /etc/NetworkManager/conf.d
    sudo tee /etc/NetworkManager/conf.d/wifi-powersave.conf > /dev/null <<'EOFWIFI'
# Disable WiFi power saving for reliable reconnection
# powersave values: 0=default, 1=ignore, 2=disable, 3=enable
[connection]
wifi.powersave = 2
EOFWIFI
    print_status $GREEN "✅ WiFi power saving disabled"
else
    print_status $GREEN "✅ WiFi power save config already exists"
fi

# 2. Remove any problematic dispatcher script (can cause reconnect loops)
# The power-save disable + autoconnect settings are sufficient
sudo rm -f /etc/NetworkManager/dispatcher.d/99-wifi-reconnect 2>/dev/null || true

# 3. Configure any existing WiFi connections to auto-reconnect infinitely
print_status $YELLOW "🔧 Configuring saved WiFi connections for auto-reconnect..."
for conn in $(nmcli -t -f NAME,TYPE con show | grep wireless | cut -d: -f1); do
    if [ -n "$conn" ]; then
        nmcli connection modify "$conn" connection.autoconnect yes 2>/dev/null || true
        nmcli connection modify "$conn" connection.autoconnect-retries 0 2>/dev/null || true  # infinite retries
        nmcli connection modify "$conn" connection.autoconnect-priority 100 2>/dev/null || true
        print_status $GREEN "  ✅ Configured: $conn"
    fi
done

# Restart NetworkManager to apply changes
sudo systemctl restart NetworkManager 2>/dev/null || true
print_status $GREEN "✅ WiFi auto-reconnect configured"

# Configure swap (important for compilation on RPi)
if [ -f /etc/dphys-swapfile ]; then
    print_status $YELLOW "💾 Configuring swap space (2GB)..."
    sudo dphys-swapfile swapoff || true
    sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
    print_status $GREEN "✅ Swap configured (2GB)"
elif swapon --show | grep -q "/swapfile"; then
    # Swap is active - check if resize needed
    SWAP_SIZE=$(stat -c%s /swapfile 2>/dev/null || echo 0)
    if [ "$SWAP_SIZE" -lt 2147483648 ]; then
        print_status $YELLOW "💾 Resizing active swap to 2GB..."
        sudo swapoff /swapfile
        sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        print_status $GREEN "✅ Swap resized to 2GB"
    else
        print_status $GREEN "✅ Swap already active and adequate size"
    fi
elif [ ! -f /swapfile ] || [ $(stat -c%s /swapfile 2>/dev/null || echo 0) -lt 2147483648 ]; then
    print_status $YELLOW "💾 Creating swap file (2GB)..."
    sudo swapoff /swapfile 2>/dev/null || true
    sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab 2>/dev/null; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    fi
    print_status $GREEN "✅ Swap file created (2GB)"
else
    print_status $GREEN "✅ Swap already configured"
fi

# Configure DDS (CycloneDDS)
# CycloneDDS iceoryx (shared-memory) transport is broken on RPi 4B / ARM64.
# DDS participants that join at different times cannot discover each other through
# shared memory, causing Python nodes (arm_client, ros2 CLI) to never see C++ nodes.
# The config/cyclonedds.xml disables iceoryx and forces loopback UDP.
# CYCLONEDDS_URI is set by arm_launcher.sh / launcher.sh and /etc/default/pragati-arm.

# Remove any stale broken config files from previous installs (wrong namespace/schema)
if [ -f ~/.ros/cyclonedds.xml ]; then
    print_status $YELLOW "Removing stale ~/.ros/cyclonedds.xml (config now in repo at config/cyclonedds.xml)"
    rm -f ~/.ros/cyclonedds.xml
    log_success "CycloneDDS config cleanup" "removed stale ~/.ros/cyclonedds.xml"
fi

# Remove stale workspace copies with wrong XML namespace (CycloneDX instead of CycloneDDS)
for stale_xml in ~/pragati_ros2/cyclonedds.xml ~/pragati_ros2/cyclone_config.xml; do
    if [ -f "$stale_xml" ]; then
        rm -f "$stale_xml"
        log_skip "Removed stale $(basename $stale_xml)" "replaced by config/cyclonedds.xml"
    fi
done

# Remove stale CYCLONEDDS_URI export pointing to deleted files
# (The correct CYCLONEDDS_URI is set by launcher scripts, not .bashrc)
sed -i '/CYCLONEDDS_URI/d' ~/.bashrc

if ! grep -q "RMW_IMPLEMENTATION" ~/.bashrc; then
    echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc
fi
log_success "CycloneDDS RMW configuration" "RMW_IMPLEMENTATION=rmw_cyclonedds_cpp set in .bashrc"
print_status $GREEN "✅ CycloneDDS configured (using defaults)"

print_status $GREEN "✅ System configuration complete"

################################################################################
# STEP 10: Install Workspace Dependencies and Build
################################################################################
print_header "STEP 10/11: Installing Workspace Dependencies"
print_status $YELLOW "📦 Installing project-specific ROS dependencies..."

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ -d "src" ]; then
    # Install dependencies from package.xml files
    rosdep install --from-paths src --ignore-src -r -y

    print_status $GREEN "✅ Workspace dependencies installed"

    echo ""
    print_status $CYAN "🔨 Ready to build workspace!"
    read -p "Build the workspace now? (y/n): " build_now

    if [[ $build_now =~ ^[Yy]$ ]]; then
        print_header "Building Workspace"
        print_status $YELLOW "🔨 Building with Raspberry Pi optimizations..."


        # Source ROS2 environment before building
        source /opt/ros/jazzy/setup.bash

        # Create COLCON_IGNORE in venv to prevent colcon from scanning it
        if [ -d "venv" ]; then
            touch venv/COLCON_IGNORE
            print_status $GREEN "✅ Created COLCON_IGNORE in venv directory"
        fi

        # Use the existing build_rpi.sh script if available
        if [ -f "build_rpi.sh" ]; then
            ./build_rpi.sh
        else
            # Build with RPi-optimized settings
            colcon build \
                --symlink-install \
                --parallel-workers 1 \
                --cmake-args \
                    -DCMAKE_BUILD_TYPE=Release \
                    -DCMAKE_CXX_FLAGS="-O2" \
                --event-handlers console_direct+
        fi

        if [ $? -eq 0 ]; then
            log_success "workspace build" "colcon build completed"
            print_status $GREEN "✅ Build successful!"

            # Add workspace sourcing to bashrc
            if ! grep -q "cotton-picker-ros2/install/setup.bash" ~/.bashrc; then
                echo "" >> ~/.bashrc
                echo "# Source Pragati Cotton Picker workspace" >> ~/.bashrc
                echo "source $SCRIPT_DIR/install/setup.bash" >> ~/.bashrc
                print_status $GREEN "✅ Workspace added to ~/.bashrc"
            fi
        else
            log_fail "workspace build" "colcon build failed -- check log"
            print_status $RED "❌ Build failed. Check errors above."
        fi
    fi
else
    print_status $YELLOW "⚠️  'src' directory not found. Skipping rosdep install."
fi

################################################################################
# COMPLETION
################################################################################
print_install_summary
print_header "🎉 RASPBERRY PI SETUP COMPLETE!"
print_status $GREEN "All dependencies have been installed successfully!"
echo ""
print_status $CYAN "📋 Summary:"
print_status $GREEN "  ✅ ROS2 Jazzy installed"
print_status $GREEN "  ✅ Build tools installed (colcon, ccache, ninja)"
print_status $GREEN "  ✅ Hardware support configured (CAN, GPIO, pigpio)"
print_status $GREEN "  ✅ Vision libraries installed (OpenCV, DepthAI)"
print_status $GREEN "  ✅ Python dependencies installed"
print_status $GREEN "  ✅ System configured for robot operation"
echo ""
print_status $YELLOW "⚠️  IMPORTANT: You need to log out and log back in for group changes to take effect!"
echo ""
print_status $CYAN "🚀 Next Steps:"
print_status $BLUE "  1. Reboot or log out and back in:"
print_status $BLUE "     sudo reboot"
print_status $BLUE "  2. After reboot, verify system:"
print_status $BLUE "     cd ~/cotton-picker-ros2"
print_status $BLUE "     bash scripts/deployment/rpi_verify.sh"
print_status $BLUE "  3. Test the CAN interface (500 kbps for MG6010 motors):"
print_status $BLUE "     sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on"
print_status $BLUE "     candump can0"
print_status $BLUE "  4. Source the workspace:"
print_status $BLUE "     source ~/cotton-picker-ros2/install/setup.bash"
print_status $BLUE "  5. Run full validation:"
print_status $BLUE "     bash scripts/deployment/validate_rpi_deployment.sh"
print_status $BLUE "  6. Launch the system:"
print_status $BLUE "     ros2 launch yanthra_move pragati_complete.launch.py"
echo ""
print_status $CYAN "📖 Documentation:"
print_status $BLUE "  • Installation Checklist: RPI_INSTALLATION_VALIDATION_CHECKLIST.md"
print_status $BLUE "  • Deployment Guide: docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md"
print_status $BLUE "  • Build Guide: BUILD_GUIDE.md"
print_status $BLUE "  • Dependency Info: DEPENDENCY_AUDIT_2025-11-17.md"
print_status $BLUE "  • Power Management Fixes: docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md"
echo ""
print_status $GREEN "🎯 Your Raspberry Pi is ready for cotton picking! 🤖🌱"
echo ""
print_status $CYAN "📝 Full installation log saved to: $LOG_FILE"
