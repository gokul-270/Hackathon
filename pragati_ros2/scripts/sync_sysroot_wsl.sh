#!/usr/bin/env bash
#
# Sysroot Sync Script for WSL
# ===========================
# Syncs RPi filesystem to local sysroot for cross-compilation
# Uses Windows SSH to access RPi on different subnet
#

set -e

# Configuration
RPI_IP="${RPI_IP:-192.168.137.238}"
RPI_USER="${RPI_USER:-ubuntu}"
SYSROOT="${RPI_SYSROOT:-$HOME/rpi-sysroot}"
WINSSH="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Sysroot Sync for Cross-Compilation${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "RPi: ${GREEN}$RPI_USER@$RPI_IP${NC}"
echo -e "Sysroot: ${GREEN}$SYSROOT${NC}"
echo ""

# Test SSH connection
echo -e "${CYAN}[1/4] Testing RPi connection...${NC}"
if ! "$WINSSH" "$RPI_USER@$RPI_IP" "echo 'Connected'" 2>/dev/null | grep -q "Connected"; then
    echo -e "${YELLOW}⚠️  Cannot connect to RPi at $RPI_IP${NC}"
    echo "Make sure:"
    echo "  1. RPi is powered on"
    echo "  2. Windows hotspot is active"
    echo "  3. SSH is enabled on RPi"
    exit 1
fi
echo -e "${GREEN}✅ RPi is reachable${NC}"
echo ""

# Create sysroot directories
echo -e "${CYAN}[2/4] Creating sysroot directories...${NC}"
mkdir -p "$SYSROOT"/{opt/ros/jazzy,usr,lib}
echo -e "${GREEN}✅ Directories created${NC}"
echo ""

# Sync ROS2 Jazzy (~2-3 GB, 10-15 minutes)
echo -e "${CYAN}[3/4] Syncing ROS2 Jazzy...${NC}"
echo "This will take 10-15 minutes for first sync..."
echo "Command: rsync -az ubuntu@$RPI_IP:/opt/ros/jazzy/ $SYSROOT/opt/ros/jazzy/"
echo ""

# Run rsync in background and track PID
rsync -az --stats \
  -e "$WINSSH" \
  "$RPI_USER@$RPI_IP:/opt/ros/jazzy/" \
  "$SYSROOT/opt/ros/jazzy/" \
  > /tmp/sysroot_jazzy.log 2>&1 &

RSYNC_PID=$!

# Show progress
while kill -0 $RSYNC_PID 2>/dev/null; do
    if [ -f /tmp/sysroot_jazzy.log ]; then
        SIZE=$(du -sh "$SYSROOT/opt/ros/jazzy" 2>/dev/null | cut -f1 || echo "0")
        echo -ne "\r  Progress: $SIZE synced..."
    fi
    sleep 2
done

wait $RSYNC_PID
RSYNC_EXIT=$?

if [ $RSYNC_EXIT -eq 0 ]; then
    SIZE=$(du -sh "$SYSROOT/opt/ros/jazzy" | cut -f1)
    echo -e "\n${GREEN}✅ ROS2 Jazzy synced ($SIZE)${NC}"
else
    echo -e "\n${YELLOW}⚠️  Sync had issues but may have completed. Check manually.${NC}"
fi
echo ""

# Sync /usr (~8-10 GB, 20-30 minutes)
echo -e "${CYAN}[4/4] Syncing /usr directory...${NC}"
echo "This will take 20-30 minutes for first sync..."
echo "Command: rsync -az ubuntu@$RPI_IP:/usr/ $SYSROOT/usr/"
echo ""

rsync -az --stats \
  -e "$WINSSH" \
  "$RPI_USER@$RPI_IP:/usr/" \
  "$SYSROOT/usr/" \
  > /tmp/sysroot_usr.log 2>&1 &

RSYNC_PID=$!

while kill -0 $RSYNC_PID 2>/dev/null; do
    if [ -f /tmp/sysroot_usr.log ]; then
        SIZE=$(du -sh "$SYSROOT/usr" 2>/dev/null | cut -f1 || echo "0")
        echo -ne "\r  Progress: $SIZE synced..."
    fi
    sleep 5
done

wait $RSYNC_PID
RSYNC_EXIT=$?

if [ $RSYNC_EXIT -eq 0 ]; then
    SIZE=$(du -sh "$SYSROOT/usr" | cut -f1)
    echo -e "\n${GREEN}✅ /usr synced ($SIZE)${NC}"
else
    echo -e "\n${YELLOW}⚠️  Sync had issues but may have completed. Check manually.${NC}"
fi
echo ""

# Sync /lib (smaller, ~1-2 GB, 5-10 minutes)
echo -e "${CYAN}[5/5] Syncing /lib directory...${NC}"
echo "This will take 5-10 minutes..."

rsync -az --stats \
  -e "$WINSSH" \
  "$RPI_USER@$RPI_IP:/lib/" \
  "$SYSROOT/lib/" \
  > /tmp/sysroot_lib.log 2>&1 &

RSYNC_PID=$!

while kill -0 $RSYNC_PID 2>/dev/null; do
    if [ -f /tmp/sysroot_lib.log ]; then
        SIZE=$(du -sh "$SYSROOT/lib" 2>/dev/null | cut -f1 || echo "0")
        echo -ne "\r  Progress: $SIZE synced..."
    fi
    sleep 2
done

wait $RSYNC_PID
RSYNC_EXIT=$?

if [ $RSYNC_EXIT -eq 0 ]; then
    SIZE=$(du -sh "$SYSROOT/lib" | cut -f1)
    echo -e "\n${GREEN}✅ /lib synced ($SIZE)${NC}"
else
    echo -e "\n${YELLOW}⚠️  Sync had issues but may have completed. Check manually.${NC}"
fi
echo ""

# Summary
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Sysroot sync complete!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo "Total size:"
du -sh "$SYSROOT"
echo ""
echo "Next steps:"
echo "  1. Apply CMake patches:"
echo "     ./scripts/patch_sysroot_cmake.sh"
echo ""
echo "  2. Test cross-compilation:"
echo "     export RPI_SYSROOT=$SYSROOT"
echo "     ./build.sh rpi -p motor_control_ros2"
echo ""
echo "  3. Verify ARM64 binary:"
echo "     file install_rpi/lib/libmotor_control_ros2*.so"
echo ""
