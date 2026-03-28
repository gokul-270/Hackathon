#!/usr/bin/env bash
#
# Patch Sysroot CMake Files
# ==========================
# Patches hardcoded absolute paths in CMake export files within the sysroot
# Based on docs/CROSS_COMPILATION_GUIDE.md Step 4
#

set -e

SYSROOT="${RPI_SYSROOT:-/media/rpi-sysroot}"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Patching Sysroot CMake Files${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "Sysroot: ${GREEN}$SYSROOT${NC}"
echo ""

# Check if sysroot exists
if [ ! -d "$SYSROOT/opt/ros/jazzy" ]; then
    echo -e "${YELLOW}⚠️  Sysroot not found at $SYSROOT${NC}"
    echo "Run ./scripts/sync_sysroot_wsl.sh first"
    exit 1
fi

# Patch hardware_interface
HW_FILE="$SYSROOT/opt/ros/jazzy/share/hardware_interface/cmake/export_hardware_interfaceExport.cmake"

if [ -f "$HW_FILE" ]; then
    echo -e "${CYAN}Patching hardware_interface...${NC}"
    
    # Backup original
    cp "$HW_FILE" "${HW_FILE}.backup" 2>/dev/null || true
    
    # Apply patches
    sed -i 's|/opt/ros/jazzy/include|${_IMPORT_PREFIX}/include|g' "$HW_FILE"
    sed -i 's|/opt/ros/jazzy/lib|${_IMPORT_PREFIX}/lib|g' "$HW_FILE"
    
    # Verify
    if grep -q '_IMPORT_PREFIX' "$HW_FILE"; then
        echo -e "${GREEN}✅ hardware_interface patched${NC}"
    else
        echo -e "${YELLOW}⚠️  Patch may have failed${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  hardware_interface cmake file not found${NC}"
fi

# Patch geometric_shapes (if present)
GEO_FILE="$SYSROOT/opt/ros/jazzy/share/geometric_shapes/cmake/export_geometric_shapesExport.cmake"

if [ -f "$GEO_FILE" ]; then
    echo -e "${CYAN}Patching geometric_shapes...${NC}"
    
    # Backup original
    cp "$GEO_FILE" "${GEO_FILE}.backup" 2>/dev/null || true
    
    # Apply patches
    sed -i 's|/opt/ros/jazzy/include|${_IMPORT_PREFIX}/include|g' "$GEO_FILE"
    sed -i 's|/opt/ros/jazzy/lib|${_IMPORT_PREFIX}/lib|g' "$GEO_FILE"
    
    # Verify
    if grep -q '_IMPORT_PREFIX' "$GEO_FILE"; then
        echo -e "${GREEN}✅ geometric_shapes patched${NC}"
    else
        echo -e "${YELLOW}⚠️  Patch may have failed${NC}"
    fi
else
    echo "ℹ️  geometric_shapes not found (optional)"
fi

# Create dynamic linker symlink (critical for linking)
echo ""
echo -e "${CYAN}Creating dynamic linker symlink...${NC}"

LINKER_DIR="$SYSROOT/lib"
LINKER_TARGET="aarch64-linux-gnu/ld-linux-aarch64.so.1"
LINKER_LINK="$LINKER_DIR/ld-linux-aarch64.so.1"

if [ ! -d "$LINKER_DIR" ]; then
    echo -e "${YELLOW}⚠️  Creating $LINKER_DIR${NC}"
    mkdir -p "$LINKER_DIR"
fi

if [ -L "$LINKER_LINK" ]; then
    echo "ℹ️  Linker symlink already exists"
elif [ -f "$LINKER_LINK" ]; then
    echo -e "${YELLOW}⚠️  Linker exists as regular file (unexpected)${NC}"
else
    # Check if target exists
    if [ -f "$LINKER_DIR/$LINKER_TARGET" ]; then
        ln -s "$LINKER_TARGET" "$LINKER_LINK"
        echo -e "${GREEN}✅ Created linker symlink${NC}"
        echo "   $LINKER_LINK -> $LINKER_TARGET"
    else
        echo -e "${YELLOW}⚠️  Linker target not found: $LINKER_DIR/$LINKER_TARGET${NC}"
        echo "   Cross-compilation may fail during linking phase"
    fi
fi

# Verify symlink
if [ -L "$LINKER_LINK" ] && [ -f "$LINKER_LINK" ]; then
    echo -e "${GREEN}✅ Dynamic linker symlink verified${NC}"
else
    echo -e "${YELLOW}⚠️  Dynamic linker symlink missing or broken${NC}"
    echo "   This will cause linker errors during cross-compilation"
fi

echo ""
echo -e "${GREEN}✅ Sysroot patching complete!${NC}"
echo ""
echo "Summary:"
echo "  • CMake export files patched"
echo "  • Dynamic linker symlink configured"
echo ""
echo "Next step: Test cross-compilation"
echo "  export RPI_SYSROOT=$SYSROOT"
echo "  ./build.sh rpi -p motor_control_ros2"
echo ""
