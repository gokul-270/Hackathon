#!/usr/bin/env bash
#
# Minimal Sysroot Sync - Essential libraries only
# ================================================
# Syncs only the directories needed for cross-compilation
# Much faster than full /usr sync
#

set -e

RPI_IP="192.168.137.238"
RPI_USER="ubuntu"
SYSROOT="${RPI_SYSROOT:-$HOME/rpi-sysroot}"
WINSSH="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Minimal Sysroot Sync (essential libraries only)${NC}"
echo ""

mkdir -p "$SYSROOT"/{opt/ros,usr,lib}

# Sync essential /usr subdirectories only
DIRS=(
    "usr/lib/aarch64-linux-gnu"
    "usr/include"
    "usr/share/pkgconfig"
    "lib/aarch64-linux-gnu"
)

for dir in "${DIRS[@]}"; do
    echo -e "${CYAN}Syncing /$dir...${NC}"
    "$WINSSH" "$RPI_USER@$RPI_IP" "cd / && tar czf - $dir 2>/dev/null" | tar xzf - -C "$SYSROOT"
    SIZE=$(du -sh "$SYSROOT/$dir" 2>/dev/null | cut -f1 || echo "0")
    echo -e "${GREEN}✅ /$dir synced ($SIZE)${NC}"
    echo ""
done

echo -e "${GREEN}✅ Essential libraries synced!${NC}"
du -sh "$SYSROOT"
echo ""
echo "Next: ./scripts/patch_sysroot_cmake.sh"
