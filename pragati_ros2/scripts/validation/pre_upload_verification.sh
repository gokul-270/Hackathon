#!/bin/bash

# Pre-Upload Verification Script for Pragati ROS2
# Comprehensive system check before packaging and upload

set -e

# Workspace root directory
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Verification results
VERIFICATION_PASSED=true
ISSUES_FOUND=()
WARNINGS_FOUND=()
RECOMMENDATIONS=()

# Logging function
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Issue tracking functions
add_issue() {
    ISSUES_FOUND+=("$1")
    VERIFICATION_PASSED=false
}

add_warning() {
    WARNINGS_FOUND+=("$1")
}

add_recommendation() {
    RECOMMENDATIONS+=("$1")
}

clear
echo -e "${CYAN}🔍 PRAGATI ROS2 PRE-UPLOAD VERIFICATION${NC}"
echo -e "${CYAN}====================================${NC}"
echo -e "${PURPLE}Generated: $(date)${NC}"
echo ""

log "${BLUE}Starting comprehensive system verification...${NC}"

# 1. WORKSPACE STRUCTURE VERIFICATION
echo -e "${CYAN}📁 WORKSPACE STRUCTURE VERIFICATION${NC}"
echo -e "${CYAN}=================================${NC}"

# Check critical directories
CRITICAL_DIRS=(
    "src"
    "build" 
    "install"
    "launch_files"
    "scripts"
    "logs"
    "inputs"
    "outputs"
)

echo "Checking critical directories..."
for dir in "${CRITICAL_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "  ✅ $dir/ exists"
    else
        add_issue "Missing critical directory: $dir/"
    fi
done

# Check documentation files
CRITICAL_DOCS=(
    "README.md"
    "COMPREHENSIVE_ROS1_ROS2_COMPARISON_REPORT.md"
    "MIGRATION_FINAL_ANALYSIS.md"
    "COMPLETE_TOOLKIT_SUMMARY.md"
)

echo ""
echo "Checking documentation files..."
for doc in "${CRITICAL_DOCS[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "  ✅ $doc exists"
    else
        add_issue "Missing documentation: $doc"
    fi
done

# 2. BUILD SYSTEM VERIFICATION
echo ""
echo -e "${CYAN}🔧 BUILD SYSTEM VERIFICATION${NC}"
echo -e "${CYAN}===========================${NC}"

# Check if workspace is built
if [ -d "install" ] && [ -f "install/setup.bash" ]; then
    echo -e "  ✅ Workspace is built (install/ directory exists)"
    
    # Source and check packages
    source "$WORKSPACE_ROOT/install/setup.bash"
    
    # Check if key packages are available
    KEY_PACKAGES=(
        "yanthra_move"
        "odrive_control_ros2"
    )
    
    echo "Checking installed packages..."
    for pkg in "${KEY_PACKAGES[@]}"; do
        PACKAGE_CHECK=$(ros2 pkg list 2>/dev/null | grep "^$pkg$" || echo ""); if [ -n "$PACKAGE_CHECK" ]; then
            echo -e "  ✅ Package $pkg installed"
        else
            add_issue "Package $pkg not found in install"
        fi
    done
else
    add_issue "Workspace not built - missing install/ directory"
fi

# 3. SOURCE CODE VERIFICATION
echo ""
echo -e "${CYAN}💻 SOURCE CODE VERIFICATION${NC}"
echo -e "${CYAN}=========================${NC}"

# Check source packages
if [ -d "src" ]; then
    SRC_PACKAGES=$(find src -maxdepth 1 -type d | wc -l)
    echo -e "  ✅ Source packages found: $((SRC_PACKAGES - 1))"
    
    # Check specific packages
    if [ -d "src/yanthra_move" ]; then
        echo -e "  ✅ yanthra_move source package exists"
    else
        add_issue "Missing yanthra_move source package"
    fi
    
    if [ -d "src/odrive_control_ros2" ]; then
        echo -e "  ✅ odrive_control_ros2 source package exists"
    else
        add_issue "Missing odrive_control_ros2 source package"
    fi
    
    # Check for CMakeLists.txt and package.xml
    echo "Checking package structure..."
    for pkg_dir in src/*/; do
        if [ -d "$pkg_dir" ]; then
            pkg_name=$(basename "$pkg_dir")
            if [ -f "${pkg_dir}CMakeLists.txt" ] && [ -f "${pkg_dir}package.xml" ]; then
                echo -e "  ✅ $pkg_name has proper ROS2 package structure"
            else
                add_warning "$pkg_name missing CMakeLists.txt or package.xml"
            fi
        fi
    done
else
    add_issue "Source directory (src/) not found"
fi

# 4. MONITORING TOOLS VERIFICATION
echo ""
echo -e "${CYAN}🛠️  MONITORING TOOLS VERIFICATION${NC}"
echo -e "${CYAN}===============================${NC}"

MONITORING_SCRIPTS=(
    "monitor_system_state.sh"
    "validate_expected_components.sh"
    "run_comprehensive_tests.sh"
    "detect_missing_components.sh"
    "final_migration_validation.sh"
    "launch_comparison.sh"
    "setup_and_test.sh"
)

echo "Checking monitoring and validation scripts..."
for script in "${MONITORING_SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        if [ -x "$script" ]; then
            echo -e "  ✅ $script (executable)"
        else
            echo -e "  ⚠️  $script (not executable)"
            add_warning "$script is not executable"
        fi
    else
        add_issue "Missing monitoring script: $script"
    fi
done

# 5. CONFIGURATION FILES VERIFICATION
echo ""
echo -e "${CYAN}⚙️  CONFIGURATION VERIFICATION${NC}"
echo -e "${CYAN}=============================${NC}"

# Check launch files
if [ -d "src/yanthra_move/launch" ]; then
    LAUNCH_FILES=$(find src/yanthra_move/launch -name "*.launch.py" | wc -l)
    echo -e "  ✅ Launch files found: $LAUNCH_FILES"
    
    # Check specific launch files
    if [ -f "src/yanthra_move/launch/yanthra_move.launch.py" ]; then
        echo -e "  ✅ Main launch file exists"
    else
        add_issue "Missing main launch file"
    fi
else
    add_issue "Launch directory not found"
fi

# Check config files
if [ -d "src/yanthra_move/config" ]; then
    CONFIG_FILES=$(find src/yanthra_move/config -name "*.yaml" | wc -l)
    echo -e "  ✅ Config files found: $CONFIG_FILES"
else
    add_warning "Config directory not found"
fi

# 6. SYSTEM FUNCTIONALITY TEST
echo ""
echo -e "${CYAN}🧪 SYSTEM FUNCTIONALITY TEST${NC}"
echo -e "${CYAN}===========================${NC}"

if [ -f "install/setup.bash" ]; then
    source "$WORKSPACE_ROOT/install/setup.bash"
    
    echo "Testing ROS2 environment..."
    if command -v ros2 &> /dev/null; then
        echo -e "  ✅ ROS2 command available"
        
        # Test package listing
        PACKAGE_CHECK=$(ros2 pkg list 2>/dev/null | grep "yanthra_move" || echo ""); if [ -n "$PACKAGE_CHECK" ]; then
            echo -e "  ✅ yanthra_move package visible to ROS2"
        else
            add_issue "yanthra_move package not visible to ROS2"
        fi
        
        # Test launch file availability
        if ros2 launch yanthra_move yanthra_move.launch.py --show-args &>/dev/null; then
            echo -e "  ✅ Launch files accessible"
        else
            add_warning "Launch files may have issues"
        fi
    else
        add_issue "ROS2 not available after sourcing workspace"
    fi
else
    add_issue "Cannot test functionality - workspace not built"
fi

# 7. FILE SIZE AND CLEANUP CHECK
echo ""
echo -e "${CYAN}📊 FILE SIZE AND CLEANUP CHECK${NC}"
echo -e "${CYAN}=============================${NC}"

# Calculate directory sizes
TOTAL_SIZE=$(du -sh . | cut -f1)
BUILD_SIZE=$(du -sh build 2>/dev/null | cut -f1 || echo "N/A")
INSTALL_SIZE=$(du -sh install 2>/dev/null | cut -f1 || echo "N/A")
SRC_SIZE=$(du -sh src 2>/dev/null | cut -f1 || echo "N/A")

echo "Directory sizes:"
echo -e "  📁 Total workspace: $TOTAL_SIZE"
echo -e "  📁 Source code: $SRC_SIZE"
echo -e "  📁 Build artifacts: $BUILD_SIZE"
echo -e "  📁 Install: $INSTALL_SIZE"

# Check for large unnecessary files
echo ""
echo "Checking for large files that could be excluded..."
find . -type f -size +10M 2>/dev/null | while read -r largefile; do
    size=$(du -h "$largefile" | cut -f1)
    echo -e "  ⚠️  Large file: $largefile ($size)"
    add_recommendation "Consider excluding large file: $largefile"
done

# Check for common unnecessary files
UNNECESSARY_PATTERNS=(
    "*.pyc"
    "*.pyo"
    "__pycache__"
    ".vscode"
    "*.swp"
    "*.swo"
    "*~"
)

echo "Checking for unnecessary files..."
for pattern in "${UNNECESSARY_PATTERNS[@]}"; do
    if find . -name "$pattern" -type f 2>/dev/null | grep -q .; then
        count=$(find . -name "$pattern" -type f 2>/dev/null | wc -l)
        add_recommendation "Found $count files matching $pattern - consider cleaning"
    fi
done

# 8. DEPENDENCY CHECK
echo ""
echo -e "${CYAN}📦 DEPENDENCY CHECK${NC}"
echo -e "${CYAN}=================${NC}"

# Check if rosdep can resolve dependencies
if command -v rosdep &> /dev/null && [ -f "install/setup.bash" ]; then
    source "$WORKSPACE_ROOT/install/setup.bash"
    echo "Checking package dependencies..."
    
    if rosdep check --from-paths src --ignore-src -r &>/dev/null; then
        echo -e "  ✅ All dependencies satisfied"
    else
        add_warning "Some dependencies may be missing"
        echo -e "  ⚠️  Run 'rosdep install --from-paths src --ignore-src -r -y' to install missing deps"
    fi
else
    add_warning "Cannot check dependencies - rosdep not available"
fi

# 9. GENERATE VERIFICATION REPORT
echo ""
echo -e "${CYAN}📋 VERIFICATION SUMMARY${NC}"
echo -e "${CYAN}=====================${NC}"

# Create verification report
REPORT_FILE="pre_upload_verification_$(date +%Y%m%d_%H%M%S).txt"

cat > "$REPORT_FILE" << EOF
PRAGATI ROS2 PRE-UPLOAD VERIFICATION REPORT
==========================================
Generated: $(date)

WORKSPACE OVERVIEW:
- Total Size: $TOTAL_SIZE
- Source Code: $SRC_SIZE  
- Build Artifacts: $BUILD_SIZE
- Install: $INSTALL_SIZE

VERIFICATION RESULTS:
EOF

if [ "$VERIFICATION_PASSED" = true ]; then
    echo -e "${GREEN}🎉 VERIFICATION PASSED!${NC}"
    echo "✅ VERIFICATION: PASSED" >> "$REPORT_FILE"
else
    echo -e "${RED}❌ VERIFICATION FAILED!${NC}"
    echo "❌ VERIFICATION: FAILED" >> "$REPORT_FILE"
fi

# Report issues
if [ ${#ISSUES_FOUND[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}🚨 CRITICAL ISSUES FOUND:${NC}"
    echo "" >> "$REPORT_FILE"
    echo "CRITICAL ISSUES:" >> "$REPORT_FILE"
    for issue in "${ISSUES_FOUND[@]}"; do
        echo -e "  ❌ $issue"
        echo "- $issue" >> "$REPORT_FILE"
    done
fi

# Report warnings
if [ ${#WARNINGS_FOUND[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  WARNINGS:${NC}"
    echo "" >> "$REPORT_FILE"
    echo "WARNINGS:" >> "$REPORT_FILE"
    for warning in "${WARNINGS_FOUND[@]}"; do
        echo -e "  ⚠️  $warning"
        echo "- $warning" >> "$REPORT_FILE"
    done
fi

# Report recommendations
if [ ${#RECOMMENDATIONS[@]} -gt 0 ]; then
    echo ""
    echo -e "${BLUE}💡 RECOMMENDATIONS:${NC}"
    echo "" >> "$REPORT_FILE"
    echo "RECOMMENDATIONS:" >> "$REPORT_FILE"
    for rec in "${RECOMMENDATIONS[@]}"; do
        echo -e "  💡 $rec"
        echo "- $rec" >> "$REPORT_FILE"
    done
fi

echo ""
echo -e "${CYAN}📁 UPLOAD READINESS ASSESSMENT${NC}"
echo -e "${CYAN}=============================${NC}"

if [ "$VERIFICATION_PASSED" = true ]; then
    echo -e "${GREEN}✅ READY FOR UPLOAD${NC}"
    echo -e "${GREEN}🎯 All critical components verified and functional${NC}"
    echo ""
    echo "READY FOR UPLOAD" >> "$REPORT_FILE"
    
    # Generate zip command suggestion
    echo -e "${BLUE}💡 SUGGESTED ZIP COMMAND:${NC}"
    echo -e "${YELLOW}zip -r pragati_ros2_$(date +%Y%m%d).zip . -x '*.git*' '*/__pycache__/*' '*.pyc' '*.pyo' '*.swp' '*.swo' '*~'${NC}"
    echo ""
    echo "SUGGESTED ZIP COMMAND:" >> "$REPORT_FILE"
    echo "zip -r pragati_ros2_$(date +%Y%m%d).zip . -x '*.git*' '*/__pycache__/*' '*.pyc' '*.pyo' '*.swp' '*.swo' '*~'" >> "$REPORT_FILE"
else
    echo -e "${RED}❌ NOT READY FOR UPLOAD${NC}"
    echo -e "${RED}🚨 Critical issues must be resolved first${NC}"
    echo ""
    echo "NOT READY FOR UPLOAD" >> "$REPORT_FILE"
    echo "Critical issues must be resolved before upload." >> "$REPORT_FILE"
fi

echo ""
echo -e "${PURPLE}📄 Verification report saved to: $REPORT_FILE${NC}"
echo -e "${PURPLE}🔍 Review the report before proceeding with upload${NC}"

# Exit with appropriate code
if [ "$VERIFICATION_PASSED" = true ]; then
    exit 0
else
    exit 1
fi
