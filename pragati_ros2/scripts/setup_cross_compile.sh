#!/usr/bin/env bash
#
# Cross-Compilation Setup Script
# =================================
#
# Automates the setup of cross-compilation environment for Raspberry Pi.
# Based on docs/CROSS_COMPILATION_GUIDE.md
#
# Usage:
#   ./scripts/setup_cross_compile.sh --setup --rpi-ip=192.168.137.238
#   ./scripts/setup_cross_compile.sh --doctor
#   ./scripts/setup_cross_compile.sh --resync --rpi-ip=192.168.137.238
#   ./scripts/setup_cross_compile.sh --patch
#

set -e

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_SYSROOT="/media/rpi-sysroot"
SYSROOT="${RPI_SYSROOT:-$DEFAULT_SYSROOT}"
RPI_USER="${RPI_USER:-ubuntu}"
RPI_IP=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Flags
MODE=""
DRY_RUN=false
ERRORS=0

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    ERRORS=$((ERRORS+1))
}

print_header() {
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

usage() {
    cat << EOF
${BOLD}Cross-Compilation Setup Script${NC}

${CYAN}Usage:${NC}
  $0 --setup --rpi-ip=<IP>      Full setup (interactive)
  $0 --doctor                   Check existing setup
  $0 --resync --rpi-ip=<IP>     Resync sysroot only
  $0 --patch                    Apply CMake patches only

${CYAN}Options:${NC}
  --rpi-ip=<IP>        Raspberry Pi IP address
  --rpi-user=<USER>    RPi username (default: ubuntu)
  --sysroot=<PATH>     Custom sysroot location (default: /media/rpi-sysroot)
  --dry-run            Show what would be done
  --help               Show this help

${CYAN}Examples:${NC}
  # First time setup
  $0 --setup --rpi-ip=192.168.137.238

  # Check if setup is complete
  $0 --doctor

  # Update sysroot after installing packages on RPi
  $0 --resync --rpi-ip=192.168.137.238

${CYAN}Environment Variables:${NC}
  RPI_SYSROOT          Custom sysroot location (overrides default)
  RPI_USER             RPi username (default: ubuntu)

EOF
}

# ============================================================================
# Preflight Checks
# ============================================================================

check_toolchain() {
    print_header "Checking Cross-Compiler Toolchain"
    
    if which aarch64-linux-gnu-gcc > /dev/null 2>&1; then
        VERSION=$(aarch64-linux-gnu-gcc --version | head -1)
        log_success "Toolchain installed: $VERSION"
        return 0
    else
        log_error "Toolchain missing"
        log_info "Install with: sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu"
        return 1
    fi
}

check_sysroot() {
    print_header "Checking Sysroot"
    
    log_info "Sysroot location: $SYSROOT"
    
    local dirs=(
        "$SYSROOT/opt/ros/jazzy"
        "$SYSROOT/usr/lib"
        "$SYSROOT/usr/include"
        "$SYSROOT/lib"
    )
    
    local missing=0
    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ]; then
            log_success "Found: $dir"
        else
            log_error "Missing: $dir"
            missing=$((missing+1))
        fi
    done
    
    if [ $missing -gt 0 ]; then
        log_info "Sync sysroot with: $0 --resync --rpi-ip=<IP>"
        return 1
    fi
    
    return 0
}

check_cmake_patches() {
    print_header "Checking CMake Patches"
    
    local hw_file="$SYSROOT/opt/ros/jazzy/share/hardware_interface/cmake/export_hardware_interfaceExport.cmake"
    
    if [ ! -f "$hw_file" ]; then
        log_warning "hardware_interface cmake file not found (may not be synced yet)"
        return 1
    fi
    
    if grep -q '_IMPORT_PREFIX' "$hw_file"; then
        log_success "hardware_interface patched"
        return 0
    else
        log_error "hardware_interface needs patching"
        log_info "Apply patches with: $0 --patch"
        return 1
    fi
}

check_toolchain_file() {
    print_header "Checking Toolchain File"
    
    local toolchain_file="$WORKSPACE_ROOT/cmake/toolchains/rpi-aarch64.cmake"
    
    if [ -f "$toolchain_file" ]; then
        log_success "Toolchain file present: $toolchain_file"
        return 0
    else
        log_error "Toolchain file missing: $toolchain_file"
        return 1
    fi
}

check_ssh_access() {
    if [ -z "$RPI_IP" ]; then
        log_warning "No RPi IP provided, skipping SSH check"
        return 1
    fi
    
    print_header "Checking SSH Access to RPi"
    
    log_info "Testing SSH to $RPI_USER@$RPI_IP..."
    
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$RPI_USER@$RPI_IP" "echo 'SSH OK'" 2>/dev/null; then
        log_success "SSH connection successful"
        return 0
    else
        log_error "Cannot connect to RPi"
        log_info "Make sure:"
        log_info "  1. RPi is powered on and connected"
        log_info "  2. IP address is correct: $RPI_IP"
        log_info "  3. SSH key is configured: ssh-copy-id $RPI_USER@$RPI_IP"
        return 1
    fi
}

# ============================================================================
# Installation Functions
# ============================================================================

install_toolchain() {
    print_header "Installing Cross-Compiler Toolchain"
    
    if which aarch64-linux-gnu-gcc > /dev/null 2>&1; then
        log_info "Toolchain already installed, skipping"
        return 0
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would install: gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu"
        return 0
    fi
    
    log_info "Installing toolchain..."
    sudo apt-get update
    sudo apt-get install -y \
        gcc-aarch64-linux-gnu \
        g++-aarch64-linux-gnu \
        binutils-aarch64-linux-gnu
    
    log_success "Toolchain installed"
}

create_sysroot_dir() {
    print_header "Creating Sysroot Directory"
    
    if [ -d "$SYSROOT" ]; then
        log_info "Sysroot directory already exists: $SYSROOT"
        return 0
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would create: $SYSROOT"
        return 0
    fi
    
    log_info "Creating sysroot at: $SYSROOT"
    sudo mkdir -p "$SYSROOT"
    sudo chown "$USER:$USER" "$SYSROOT"
    
    log_success "Sysroot directory created"
}

sync_sysroot() {
    if [ -z "$RPI_IP" ]; then
        log_error "RPi IP address required for syncing"
        log_info "Use: $0 --resync --rpi-ip=<IP>"
        return 1
    fi
    
    print_header "Syncing Sysroot from RPi"
    
    log_info "Source: $RPI_USER@$RPI_IP"
    log_info "Target: $SYSROOT"
    log_warning "This will take 30-60 minutes on first sync (~13GB)"
    
    # Check SSH first
    if ! ssh -o ConnectTimeout=5 "$RPI_USER@$RPI_IP" "echo 'SSH OK'" 2>/dev/null; then
        log_error "Cannot connect to RPi"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would sync from RPi"
        return 0
    fi
    
    # Sync ROS2 Jazzy
    log_info "Syncing /opt/ros/jazzy (~2-3GB)..."
    rsync -avz --progress "$RPI_USER@$RPI_IP:/opt/ros/jazzy/" "$SYSROOT/opt/ros/jazzy/"
    
    # Sync system libraries
    log_info "Syncing /usr (~8-10GB)..."
    rsync -avz --progress \
        --exclude='share/doc' \
        --exclude='share/man' \
        "$RPI_USER@$RPI_IP:/usr/" "$SYSROOT/usr/"
    
    # Sync lib directory
    log_info "Syncing /lib..."
    rsync -avz --progress "$RPI_USER@$RPI_IP:/lib/" "$SYSROOT/lib/"
    
    log_success "Sysroot sync complete"
    log_info "Sysroot size: $(du -sh $SYSROOT | cut -f1)"
}

patch_cmake_files() {
    print_header "Patching CMake Files"
    
    if [ ! -d "$SYSROOT/opt/ros/jazzy" ]; then
        log_error "Sysroot not synced yet, cannot patch"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would patch CMake files"
        return 0
    fi
    
    # Patch hardware_interface
    local hw_file="$SYSROOT/opt/ros/jazzy/share/hardware_interface/cmake/export_hardware_interfaceExport.cmake"
    if [ -f "$hw_file" ]; then
        log_info "Patching hardware_interface..."
        sed -i 's|/opt/ros/jazzy/include|${_IMPORT_PREFIX}/include|g' "$hw_file"
        sed -i 's|/opt/ros/jazzy/lib|${_IMPORT_PREFIX}/lib|g' "$hw_file"
        log_success "hardware_interface patched"
    else
        log_warning "hardware_interface cmake file not found"
    fi
    
    # Patch geometric_shapes (if present)
    local gs_file="$SYSROOT/opt/ros/jazzy/share/geometric_shapes/cmake/export_geometric_shapesExport.cmake"
    if [ -f "$gs_file" ]; then
        log_info "Patching geometric_shapes..."
        sed -i 's|/opt/ros/jazzy/include|${_IMPORT_PREFIX}/include|g' "$gs_file"
        sed -i 's|/opt/ros/jazzy/lib|${_IMPORT_PREFIX}/lib|g' "$gs_file"
        log_success "geometric_shapes patched"
    fi
    
    log_success "CMake patches applied"
}

smoke_test() {
    print_header "Running Smoke Test"
    
    log_info "Building motor_control_ros2 for RPi..."
    
    cd "$WORKSPACE_ROOT"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would run: ./build.sh rpi -p motor_control_ros2"
        return 0
    fi
    
    if ./build.sh rpi -p motor_control_ros2; then
        log_success "Build successful"
        
        # Check if output is ARM64
        local test_lib=$(find install_rpi/lib -name "libmotor_control_ros2*.so" | head -1)
        if [ -n "$test_lib" ]; then
            local arch=$(file "$test_lib" | grep -o "ARM aarch64")
            if [ -n "$arch" ]; then
                log_success "Output is ARM64: $arch"
                return 0
            else
                log_error "Output is not ARM64"
                return 1
            fi
        else
            log_warning "Could not find built library to verify"
            return 0
        fi
    else
        log_error "Build failed"
        return 1
    fi
}

# ============================================================================
# Main Functions
# ============================================================================

run_doctor() {
    print_header "Cross-Compilation Setup Doctor"
    
    log_info "Checking cross-compilation setup..."
    echo
    
    ERRORS=0
    
    check_toolchain || true
    echo
    
    check_toolchain_file || true
    echo
    
    check_sysroot || true
    echo
    
    check_cmake_patches || true
    echo
    
    if [ -n "$RPI_IP" ]; then
        check_ssh_access || true
        echo
    fi
    
    print_header "Summary"
    
    if [ $ERRORS -eq 0 ]; then
        log_success "All checks passed! Cross-compilation is ready."
        log_info "Test with: ./build.sh rpi -p motor_control_ros2"
    else
        log_error "$ERRORS issue(s) found"
        log_info "Run: $0 --setup --rpi-ip=<IP> to fix"
    fi
}

run_setup() {
    if [ -z "$RPI_IP" ]; then
        log_error "RPi IP address required"
        log_info "Use: $0 --setup --rpi-ip=<IP>"
        exit 1
    fi
    
    print_header "Cross-Compilation Setup"
    
    log_info "RPi: $RPI_USER@$RPI_IP"
    log_info "Sysroot: $SYSROOT"
    echo
    
    # Step 1: Install toolchain
    install_toolchain
    echo
    
    # Step 2: Check SSH
    check_ssh_access || exit 1
    echo
    
    # Step 3: Create sysroot directory
    create_sysroot_dir
    echo
    
    # Step 4: Sync sysroot
    sync_sysroot || exit 1
    echo
    
    # Step 5: Patch CMake files
    patch_cmake_files
    echo
    
    # Step 6: Smoke test
    smoke_test || log_warning "Smoke test failed, but setup is complete"
    echo
    
    print_header "Setup Complete!"
    
    log_success "Cross-compilation is ready"
    log_info "Build with: ./build.sh rpi"
    log_info "Deploy with: ./sync.sh --deploy-cross"
    
    # Save config for future use
    if [ "$SYSROOT" != "$DEFAULT_SYSROOT" ]; then
        log_info ""
        log_info "Add to ~/.bashrc for persistence:"
        log_info "  export RPI_SYSROOT=$SYSROOT"
    fi
}

run_resync() {
    if [ -z "$RPI_IP" ]; then
        log_error "RPi IP address required"
        log_info "Use: $0 --resync --rpi-ip=<IP>"
        exit 1
    fi
    
    check_ssh_access || exit 1
    echo
    
    sync_sysroot || exit 1
    echo
    
    patch_cmake_files
    echo
    
    log_success "Sysroot updated"
}

run_patch() {
    patch_cmake_files || exit 1
}

# ============================================================================
# Argument Parsing
# ============================================================================

if [ $# -eq 0 ]; then
    usage
    exit 0
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --setup)
            MODE="setup"
            shift
            ;;
        --doctor)
            MODE="doctor"
            shift
            ;;
        --resync)
            MODE="resync"
            shift
            ;;
        --patch)
            MODE="patch"
            shift
            ;;
        --rpi-ip=*)
            RPI_IP="${1#*=}"
            shift
            ;;
        --rpi-user=*)
            RPI_USER="${1#*=}"
            shift
            ;;
        --sysroot=*)
            SYSROOT="${1#*=}"
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# ============================================================================
# Main Execution
# ============================================================================

case "$MODE" in
    setup)
        run_setup
        ;;
    doctor)
        run_doctor
        ;;
    resync)
        run_resync
        ;;
    patch)
        run_patch
        ;;
    *)
        log_error "No mode specified"
        usage
        exit 1
        ;;
esac
