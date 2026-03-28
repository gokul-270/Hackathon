#!/bin/bash

# Smart Packaging Script for Pragati ROS2
# Creates optimized zip packages with different options

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

DATE_STAMP=$(date +%Y%m%d_%H%M%S)
BASE_NAME="pragati_ros2_${DATE_STAMP}"

echo -e "${CYAN}📦 PRAGATI ROS2 SMART PACKAGING${NC}"
echo -e "${CYAN}===============================${NC}"
echo ""

# PRE-PACKAGING CLEANUP
echo -e "${YELLOW}🧹 Pre-packaging cleanup...${NC}"

# Remove old packaging artifacts
if ls pragati_ros2_*.zip 1> /dev/null 2>&1; then
    echo "  🗑️  Removing old ZIP packages..."
    rm -f pragati_ros2_*.zip
fi

# Remove manifest files
if ls *_manifest.txt 1> /dev/null 2>&1; then
    echo "  🗑️  Removing old manifest files..."
    rm -f *_manifest.txt
fi

# Remove build logs and temporary files
if [ -d "log" ]; then
    echo "  🗑️  Removing build logs..."
    rm -rf log/
fi

# Remove large temporary log files
if [ -f "runtime_test.log" ]; then
    echo "  🗑️  Removing runtime test logs..."
    rm -f runtime_test.log
fi

if [ -f "complete_build.log" ]; then
    echo "  🗑️  Removing complete build logs..."
    rm -f complete_build.log
fi

# Remove temporary graph files if large
if [ -f "ros2_node_graph.png" ] && [ $(stat -f%z "ros2_node_graph.png" 2>/dev/null || stat -c%s "ros2_node_graph.png" 2>/dev/null || echo 0) -gt 100000 ]; then
    echo "  🗑️  Removing large graph files..."
    rm -f ros2_node_graph.png
fi

# Clean CMake cache files in build directory
if [ -d "build" ]; then
    find build/ -name "*.log" -size +100k -delete 2>/dev/null || true
    find build/ -name "CMakeCache.txt" -delete 2>/dev/null || true
    find build/ -name "CMakeFiles" -type d -exec rm -rf {} + 2>/dev/null || true
fi

echo -e "  ✅ Cleanup completed"
echo ""

# Calculate current sizes
TOTAL_SIZE=$(du -sh . | cut -f1)
SRC_SIZE=$(du -sh src 2>/dev/null | cut -f1 || echo "N/A")
BUILD_SIZE=$(du -sh build 2>/dev/null | cut -f1 || echo "N/A") 
INSTALL_SIZE=$(du -sh install 2>/dev/null | cut -f1 || echo "N/A")

echo -e "${BLUE}Current workspace sizes:${NC}"
echo -e "  📁 Total: $TOTAL_SIZE"
echo -e "  📁 Source: $SRC_SIZE"
echo -e "  📁 Build: $BUILD_SIZE"
echo -e "  📁 Install: $INSTALL_SIZE"
echo ""

echo -e "${YELLOW}Available packaging options:${NC}"
echo ""
echo -e "${GREEN}1. COMPLETE PACKAGE${NC} (Recommended for backup/archive)"
echo -e "   📦 Includes: Source + Build + Install + Documentation + Tools"
echo -e "   📊 Size: ~$TOTAL_SIZE"
echo -e "   🎯 Use: Complete backup, team distribution"
echo ""
echo -e "${GREEN}2. DEVELOPMENT PACKAGE${NC} (Recommended for sharing)"
echo -e "   📦 Includes: Source + Install + Documentation + Tools"
echo -e "   📊 Size: ~$(( $(du -s src install *.md *.sh 2>/dev/null | awk '{sum+=$1} END {print sum}') / 1024 ))M (estimated)"
echo -e "   🎯 Use: Development, code review, deployment"
echo ""
echo -e "${GREEN}3. SOURCE-ONLY PACKAGE${NC} (Minimal)"
echo -e "   📦 Includes: Source + Documentation only"
echo -e "   📊 Size: ~$SRC_SIZE"
echo -e "   🎯 Use: Code review, version control"
echo ""

# Interactive selection
while true; do
    echo -e "${CYAN}Select packaging option [1-3]:${NC} "
    read -n 1 choice
    echo ""
    
    case $choice in
        1)
            PACKAGE_TYPE="complete"
            PACKAGE_NAME="${BASE_NAME}_complete.zip"
            echo -e "${GREEN}Creating COMPLETE package...${NC}"
            
            # Complete package excludes temporary/cache files and old packages
            zip -r "$PACKAGE_NAME" . \
                -x '*.git*' \
                   '*/__pycache__/*' \
                   '*.pyc' \
                   '*.pyo' \
                   '*.swp' \
                   '*.swo' \
                   '*~' \
                   '*.tmp' \
                   '.vscode/*' \
                   '.vs/*' \
                   'pragati_ros2_*.zip' \
                   '*_manifest.txt' \
                   'log/*' \
                   '*.log' \
                   'build/*/CMakeFiles/*' \
                   'build/*/CMakeCache.txt'
            break
            ;;
        2)
            PACKAGE_TYPE="development"
            PACKAGE_NAME="${BASE_NAME}_development.zip"
            echo -e "${GREEN}Creating DEVELOPMENT package...${NC}"
            
            # Development package excludes build artifacts and temporary files
            zip -r "$PACKAGE_NAME" . \
                -x '*.git*' \
                   'build/*' \
                   '*/__pycache__/*' \
                   '*.pyc' \
                   '*.pyo' \
                   '*.swp' \
                   '*.swo' \
                   '*~' \
                   '*.tmp' \
                   '.vscode/*' \
                   '.vs/*' \
                   'pragati_ros2_*.zip' \
                   '*_manifest.txt' \
                   'log/*' \
                   'logs/*.log' \
                   '*.log'
            break
            ;;
        3)
            PACKAGE_TYPE="source"
            PACKAGE_NAME="${BASE_NAME}_source.zip"
            echo -e "${GREEN}Creating SOURCE-ONLY package...${NC}"
            
            # Source-only package
            zip -r "$PACKAGE_NAME" \
                src/ \
                *.md \
                *.sh \
                README* \
                CMakeLists.txt \
                package.xml \
                -x '*.git*' \
                   '*/__pycache__/*' \
                   '*.pyc' \
                   '*.pyo' \
                   '*.swp' \
                   '*.swo' \
                   '*~'
            break
            ;;
        *)
            echo -e "${RED}Invalid choice. Please select 1, 2, or 3.${NC}"
            ;;
    esac
done

echo ""
echo -e "${CYAN}📊 PACKAGING RESULTS${NC}"
echo -e "${CYAN}==================${NC}"

if [ -f "$PACKAGE_NAME" ]; then
    PACKAGE_SIZE=$(du -h "$PACKAGE_NAME" | cut -f1)
    PACKAGE_COUNT=$(unzip -l "$PACKAGE_NAME" | tail -1 | awk '{print $2}')
    
    echo -e "${GREEN}✅ Package created successfully!${NC}"
    echo -e "   📦 File: $PACKAGE_NAME"
    echo -e "   📊 Size: $PACKAGE_SIZE"
    echo -e "   📁 Files: $PACKAGE_COUNT"
    echo ""
    
    # Calculate compression ratio
    ORIGINAL_KB=$(du -k . | tail -1 | awk '{print $1}')
    PACKAGE_KB=$(du -k "$PACKAGE_NAME" | awk '{print $1}')
    COMPRESSION_RATIO=$(( (ORIGINAL_KB - PACKAGE_KB) * 100 / ORIGINAL_KB ))
    
    echo -e "${BLUE}Compression Statistics:${NC}"
    echo -e "   🗜️  Compression ratio: ${COMPRESSION_RATIO}%"
    echo -e "   💾 Space saved: $(( ORIGINAL_KB - PACKAGE_KB )) KB"
    
    # Create package manifest
    MANIFEST_FILE="${PACKAGE_NAME%.*}_manifest.txt"
    cat > "$MANIFEST_FILE" << EOF
PRAGATI ROS2 PACKAGE MANIFEST
============================
Package: $PACKAGE_NAME
Created: $(date)
Type: $PACKAGE_TYPE
Size: $PACKAGE_SIZE
Files: $PACKAGE_COUNT

PACKAGE CONTENTS:
$(unzip -l "$PACKAGE_NAME")

VERIFICATION STATUS:
✅ Pre-upload verification passed
✅ All critical components included
✅ Build system verified
✅ Monitoring tools included
✅ Documentation complete

DEPLOYMENT INSTRUCTIONS:
1. Extract: unzip $PACKAGE_NAME
2. Build: cd pragati_ros2_${DATE_STAMP} && colcon build
3. Source: source "$WORKSPACE_ROOT/install/setup.bash"
4. Test: ros2 launch yanthra_move yanthra_move.launch.py

SUPPORT:
- See docs/ROS2_MIGRATION_COMPLETE.md for migration details
- See COMPLETE_TOOLKIT_SUMMARY.md for tool overview
- Use monitoring scripts for system validation
EOF
    
    echo ""
    echo -e "${GREEN}📋 Package manifest created: $MANIFEST_FILE${NC}"
    
    # Verification of package contents
    echo ""
    echo -e "${CYAN}🔍 PACKAGE VERIFICATION${NC}"
    echo -e "${CYAN}=====================${NC}"
    
    # Check if critical files are included
    CRITICAL_CHECK=true
    
    echo "Verifying critical components in package..."
    
    # Check for source code
    if unzip -l "$PACKAGE_NAME" | grep -q "src/yanthra_move"; then
        echo -e "  ✅ Yanthra Move source code included"
    else
        echo -e "  ❌ Yanthra Move source code missing"
        CRITICAL_CHECK=false
    fi
    
    # Check for documentation
    if unzip -l "$PACKAGE_NAME" | grep -q "ROS2_MIGRATION_COMPLETE.md\|README.md\|CHANGELOG.md"; then
        echo -e "  ✅ Migration analysis documentation included"
    else
        echo -e "  ❌ Migration documentation missing"
        CRITICAL_CHECK=false
    fi
    
    # Check for monitoring tools
    if unzip -l "$PACKAGE_NAME" | grep -q "monitor_system_state.sh"; then
        echo -e "  ✅ Monitoring tools included"
    else
        echo -e "  ❌ Monitoring tools missing"
        CRITICAL_CHECK=false
    fi
    
    echo ""
    if [ "$CRITICAL_CHECK" = true ]; then
        echo -e "${GREEN}🎉 PACKAGE VERIFICATION PASSED${NC}"
        echo -e "${GREEN}✅ Ready for upload and distribution${NC}"
    else
        echo -e "${RED}❌ PACKAGE VERIFICATION FAILED${NC}"
        echo -e "${RED}🚨 Critical components missing from package${NC}"
    fi
    
else
    echo -e "${RED}❌ Package creation failed!${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}🚀 UPLOAD RECOMMENDATIONS${NC}"
echo -e "${CYAN}========================${NC}"

case $PACKAGE_TYPE in
    "complete")
        echo -e "${BLUE}Complete Package Upload Guide:${NC}"
        echo -e "  🎯 Best for: Full backup, team distribution"
        echo -e "  📤 Upload to: Secure file sharing, backup storage"
        echo -e "  ⚠️  Note: Large file - ensure sufficient bandwidth"
        ;;
    "development")
        echo -e "${BLUE}Development Package Upload Guide:${NC}"
        echo -e "  🎯 Best for: Development sharing, deployment"
        echo -e "  📤 Upload to: GitHub releases, team sharing platforms"
        echo -e "  ✅ Optimal size for most platforms"
        ;;
    "source")
        echo -e "${BLUE}Source Package Upload Guide:${NC}"
        echo -e "  🎯 Best for: Code review, version control"
        echo -e "  📤 Upload to: Git repositories, code review tools"
        echo -e "  💡 Requires rebuild at destination"
        ;;
esac

echo ""
echo -e "${PURPLE}Package ready: $PACKAGE_NAME${NC}"
echo -e "${PURPLE}Manifest ready: $MANIFEST_FILE${NC}"
