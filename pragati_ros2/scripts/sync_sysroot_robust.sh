#!/usr/bin/env bash
#
# Robust Sysroot Sync - Folder by folder with progress
# =====================================================
# Syncs each important directory separately with progress tracking
# Can resume if interrupted
#

set -e

RPI_IP="192.168.137.238"
RPI_USER="ubuntu"
SYSROOT="${RPI_SYSROOT:-$HOME/rpi-sysroot}"
WINSSH="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"
PROGRESS_FILE="/tmp/sysroot_sync_progress.txt"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Track what's been synced
if [ ! -f "$PROGRESS_FILE" ]; then
    echo "# Sysroot sync progress" > "$PROGRESS_FILE"
fi

mark_done() {
    echo "$1=DONE" >> "$PROGRESS_FILE"
}

is_done() {
    grep -q "^$1=DONE" "$PROGRESS_FILE" 2>/dev/null
}

sync_directory() {
    local name="$1"
    local remote_path="$2"
    local description="$3"

    if is_done "$name"; then
        echo -e "${GREEN}✅ $description (already synced)${NC}"
        return 0
    fi

    echo -e "${CYAN}Syncing: $description${NC}"
    echo "  Remote: $remote_path"
    echo "  This may take several minutes..."

    # Get size on RPi first
    SIZE_KB=$("$WINSSH" "$RPI_USER@$RPI_IP" "du -sk $remote_path 2>/dev/null | cut -f1" 2>/dev/null || echo "0")
    SIZE_MB=$((SIZE_KB / 1024))
    echo "  Size: ~${SIZE_MB}MB"

    # Create parent directory
    local parent_dir=$(dirname "$SYSROOT/$remote_path")
    mkdir -p "$parent_dir"

    # Sync with tar (more reliable than rsync through Windows SSH)
    echo "  Transferring..."
    if "$WINSSH" "$RPI_USER@$RPI_IP" "cd / && tar czf - $remote_path 2>/dev/null" | \
       tar xzf - -C "$SYSROOT" --strip-components=0 2>/dev/null; then

        LOCAL_SIZE=$(du -sh "$SYSROOT/$remote_path" 2>/dev/null | cut -f1 || echo "0")
        echo -e "${GREEN}✅ $description synced ($LOCAL_SIZE)${NC}"
        mark_done "$name"
        echo ""
        return 0
    else
        echo -e "${YELLOW}⚠️  $description had issues, will retry next run${NC}"
        echo ""
        return 1
    fi
}

echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Robust Sysroot Sync (folder-by-folder)${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo "RPi: $RPI_USER@$RPI_IP"
echo "Sysroot: $SYSROOT"
echo ""

# Test connection
echo -e "${CYAN}Testing RPi connection...${NC}"
if ! "$WINSSH" "$RPI_USER@$RPI_IP" "echo OK" 2>/dev/null | grep -q "OK"; then
    echo -e "${YELLOW}⚠️  Cannot connect to RPi${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Connected${NC}"
echo ""

# Create base structure
mkdir -p "$SYSROOT"/{opt/ros,usr/{lib,include},lib}

# Sync directories in order of importance
echo -e "${CYAN}[1/6] ROS2 Core${NC}"
sync_directory "ros_jazzy" "opt/ros/jazzy" "ROS2 Jazzy"

echo -e "${CYAN}[2/6] ARM64 Libraries${NC}"
sync_directory "usr_lib_aarch64" "usr/lib/aarch64-linux-gnu" "System libraries (aarch64)"

echo -e "${CYAN}[3/6] System Headers${NC}"
sync_directory "usr_include" "usr/include" "System headers"

echo -e "${CYAN}[4/6] Additional Libraries${NC}"
sync_directory "lib_aarch64" "lib/aarch64-linux-gnu" "Runtime libraries"

echo -e "${CYAN}[5/6] Python Libraries${NC}"
sync_directory "usr_lib_python3" "usr/lib/python3.12" "Python 3.12 libraries"

echo -e "${CYAN}[6/6] CMake and pkg-config${NC}"
sync_directory "usr_share" "usr/share/cmake" "CMake modules" || true

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Sysroot sync complete!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo ""
echo "Total size:"
du -sh "$SYSROOT"
echo ""
echo "Synced directories:"
du -sh "$SYSROOT"/*/* 2>/dev/null | head -20
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo "  1. Patch CMake files:"
echo "     ./scripts/patch_sysroot_cmake.sh"
echo ""
echo "  2. Test cross-compilation:"
echo "     export RPI_SYSROOT=$SYSROOT"
echo "     ./build.sh rpi -p motor_control_ros2"
echo ""
