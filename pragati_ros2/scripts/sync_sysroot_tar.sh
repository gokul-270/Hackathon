#!/usr/bin/env bash
#
# Direct Sysroot Sync using SCP in batches
# =========================================
# Uses scp to copy directories in chunks to avoid buffer overflow
# Alternative to rsync when facing connection issues
#

set -e

RPI_IP="192.168.137.238"
RPI_USER="ubuntu"
SYSROOT="${RPI_SYSROOT:-$HOME/rpi-sysroot}"
WINSSH="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}Sysroot Sync via tar+ssh (reliable for large transfers)${NC}"
echo ""

# Create sysroot structure
mkdir -p "$SYSROOT"/{opt/ros,usr,lib}

# Method: Use tar over ssh to stream compressed data
# More reliable than rsync through Windows SSH

echo -e "${CYAN}[1/3] Syncing /opt/ros/jazzy (streaming tar)...${NC}"
"$WINSSH" "$RPI_USER@$RPI_IP" "cd /opt/ros && tar czf - jazzy" | tar xzf - -C "$SYSROOT/opt/ros"
SIZE=$(du -sh "$SYSROOT/opt/ros/jazzy" | cut -f1)
echo -e "${GREEN}✅ ROS2 Jazzy synced ($SIZE)${NC}"
echo ""

echo -e "${CYAN}[2/3] Syncing /usr (this will take longer)...${NC}"
"$WINSSH" "$RPI_USER@$RPI_IP" "tar czf - /usr 2>/dev/null" | tar xzf - -C "$SYSROOT" --strip-components=0
SIZE=$(du -sh "$SYSROOT/usr" | cut -f1)
echo -e "${GREEN}✅ /usr synced ($SIZE)${NC}"
echo ""

echo -e "${CYAN}[3/3] Syncing /lib...${NC}"
"$WINSSH" "$RPI_USER@$RPI_IP" "tar czf - /lib 2>/dev/null" | tar xzf - -C "$SYSROOT" --strip-components=0
SIZE=$(du -sh "$SYSROOT/lib" | cut -f1)
echo -e "${GREEN}✅ /lib synced ($SIZE)${NC}"
echo ""

echo -e "${GREEN}✅ Sysroot sync complete!${NC}"
du -sh "$SYSROOT"
echo ""
echo "Next: ./scripts/patch_sysroot_cmake.sh"
