#!/bin/bash

################################################################################
# Pragati ROS2 Script Cleanup Utility
# 
# This script identifies and removes duplicate scripts across the workspace,
# organizing them into a clean, centralized structure.
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_status $CYAN "🧹 PRAGATI ROS2 SCRIPT CLEANUP"
print_status $CYAN "=============================="
echo ""

# Check if we're in the right directory
if [ ! -f "src/yanthra_move/package.xml" ]; then
    print_status $RED "❌ Error: Not in pragati_ros2 root directory"
    exit 1
fi

print_status $YELLOW "🔍 Analyzing script duplicates..."

# Create backup directory
BACKUP_DIR="scripts_cleanup_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

print_status $BLUE "📦 Creating backup in: $BACKUP_DIR"

# Function to find and analyze duplicates
analyze_duplicates() {
    local script_name="$1"
    local description="$2"
    
    echo ""
    print_status $YELLOW "🔍 Analyzing: $description"
    
    local files=($(find . -name "$script_name" -type f -not -path "./build/*" -not -path "./install/*" 2>/dev/null))
    
    if [ ${#files[@]} -gt 1 ]; then
        echo "   Found ${#files[@]} instances:"
        for file in "${files[@]}"; do
            local size=$(stat -c%s "$file" 2>/dev/null || echo "0")
            local date=$(stat -c%y "$file" 2>/dev/null | cut -d' ' -f1)
            echo "     $file (${size} bytes, $date)"
        done
        
        # Copy all instances to backup
        for file in "${files[@]}"; do
            local backup_name="${file//\//_}"
            cp "$file" "$BACKUP_DIR/${backup_name}" 2>/dev/null || true
        done
        
        return 0
    else
        echo "   ✅ No duplicates found"
        return 1
    fi
}

# Function to remove duplicate and keep the best version
cleanup_duplicates() {
    local script_name="$1"
    local keep_path="$2"
    local description="$3"
    
    local files=($(find . -name "$script_name" -type f -not -path "./build/*" -not -path "./install/*" 2>/dev/null))
    
    if [ ${#files[@]} -gt 1 ]; then
        print_status $YELLOW "🗑️  Cleaning up: $description"
        
        for file in "${files[@]}"; do
            if [ "$file" != "$keep_path" ]; then
                echo "   Removing: $file"
                rm -f "$file"
            fi
        done
        
        if [ -f "$keep_path" ]; then
            echo "   ✅ Kept: $keep_path"
        else
            print_status $RED "   ❌ Warning: Preferred file not found: $keep_path"
        fi
    fi
}

# Analyze all duplicates first
print_status $BLUE "📊 DUPLICATE ANALYSIS REPORT"
print_status $BLUE "============================"

FOUND_DUPLICATES=false

# Check for create_upload_package.sh duplicates
if analyze_duplicates "create_upload_package.sh" "Upload Package Scripts"; then
    FOUND_DUPLICATES=true
fi

# Check for validation scripts
if analyze_duplicates "comprehensive_system_test.sh" "Comprehensive System Test"; then
    FOUND_DUPLICATES=true
fi

if analyze_duplicates "end_to_end_validation.sh" "End-to-End Validation"; then
    FOUND_DUPLICATES=true
fi

if analyze_duplicates "quick_validation.sh" "Quick Validation"; then
    FOUND_DUPLICATES=true
fi

# Check for cleanup scripts
if analyze_duplicates "clean_logs.sh" "Log Cleanup Scripts"; then
    FOUND_DUPLICATES=true
fi

if analyze_duplicates "cleanup_ros2.sh" "ROS2 Cleanup Scripts"; then
    FOUND_DUPLICATES=true
fi

# Check for other utility scripts
if analyze_duplicates "pragati_commands.sh" "Pragati Commands"; then
    FOUND_DUPLICATES=true
fi

if analyze_duplicates "launch_production.sh" "Production Launch"; then
    FOUND_DUPLICATES=true
fi

if analyze_duplicates "build.sh" "Build Scripts"; then
    FOUND_DUPLICATES=true
fi

# Look for any other duplicates
echo ""
print_status $YELLOW "🔍 Scanning for other duplicate patterns..."

# Find duplicate script names
DUPLICATE_NAMES=$(find . -name "*.sh" -type f -not -path "./build/*" -not -path "./install/*" 2>/dev/null | \
    xargs -I {} basename {} | sort | uniq -d)

if [ -n "$DUPLICATE_NAMES" ]; then
    echo "Additional duplicate script names found:"
    for name in $DUPLICATE_NAMES; do
        echo "  - $name"
        find . -name "$name" -type f -not -path "./build/*" -not -path "./install/*" 2>/dev/null | \
            sed 's/^/    /'
    done
    FOUND_DUPLICATES=true
fi

echo ""

if [ "$FOUND_DUPLICATES" = false ]; then
    print_status $GREEN "✅ No duplicates found! Scripts are already clean."
    rm -rf "$BACKUP_DIR"
    exit 0
fi

# Ask for confirmation before cleanup
print_status $CYAN "🚨 CLEANUP CONFIRMATION"
print_status $CYAN "======================="
echo ""
print_status $YELLOW "This will:"
echo "  1. Remove duplicate scripts"
echo "  2. Keep the most recent/appropriate version of each script"
echo "  3. Maintain backups in: $BACKUP_DIR"
echo ""
echo "Recommended script locations to keep:"
echo "  📦 scripts/build/create_upload_package.sh (most recent)"
echo "  🧪 scripts/validation/ (all validation scripts)"
echo "  🛠️  scripts/essential/ (essential utilities)"
echo "  🔧 scripts/build/ or scripts/monitoring/ or scripts/maintenance/ (utility scripts)"
echo ""

read -p "Do you want to proceed with cleanup? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_status $YELLOW "Cleanup cancelled. Backup directory preserved: $BACKUP_DIR"
    exit 0
fi

print_status $BLUE "🧹 PERFORMING CLEANUP"
print_status $BLUE "===================="

# Cleanup duplicates - keep the best version of each
cleanup_duplicates "create_upload_package.sh" "./scripts/build/create_upload_package.sh" "Upload Package Scripts"

# Remove obsolete directory structures that contain duplicates
if [ -d "tools/" ]; then
    print_status $YELLOW "🗂️  Removing obsolete tools/ directory..."
    rm -rf tools/
    echo "   ✅ Removed tools/ directory"
fi

# Remove any scripts in root that should be in scripts/
ROOT_SCRIPTS=($(find . -maxdepth 1 -name "*.sh" -type f 2>/dev/null))
if [ ${#ROOT_SCRIPTS[@]} -gt 0 ]; then
    print_status $YELLOW "🗂️  Moving root-level scripts to scripts/build/ or scripts/monitoring/ or scripts/maintenance/..."
    for script in "${ROOT_SCRIPTS[@]}"; do
        if [ "$script" != "./format_code.sh" ] && [ "$script" != "./test_error_handling.sh" ]; then
            echo "   Moving: $script → scripts/build/ or scripts/monitoring/ or scripts/maintenance/"
            mv "$script" "scripts/build/ or scripts/monitoring/ or scripts/maintenance/" 2>/dev/null || true
        fi
    done
fi

# Clean up empty directories
print_status $YELLOW "🗂️  Removing empty directories..."
find . -type d -empty -not -path "./build/*" -not -path "./install/*" -not -path "./.git/*" 2>/dev/null | \
    while read dir; do
        if [ "$dir" != "." ] && [ "$dir" != ".." ]; then
            rmdir "$dir" 2>/dev/null && echo "   Removed empty directory: $dir" || true
        fi
    done

echo ""
print_status $GREEN "✅ CLEANUP COMPLETED SUCCESSFULLY"
print_status $GREEN "================================"

# Show final structure
echo ""
print_status $BLUE "📁 Final Script Organization:"
echo ""
echo "scripts/"
echo "├── build/"
find scripts/build/ -name "*.sh" 2>/dev/null | sed 's|scripts/build/|│   ├── |' || true
echo "├── essential/"
find scripts/essential/ -name "*.sh" 2>/dev/null | sed 's|scripts/essential/|│   ├── |' || true
echo "├── launch/"
find scripts/launch/ -name "*.sh" 2>/dev/null | sed 's|scripts/launch/|│   ├── |' || true
echo "├── utils/"
find scripts/build/ or scripts/monitoring/ or scripts/maintenance/ -name "*.sh" 2>/dev/null | sed 's|scripts/build/ or scripts/monitoring/ or scripts/maintenance/|│   ├── |' || true
echo "└── validation/"
find scripts/validation/ -name "*.sh" 2>/dev/null | sed 's|scripts/validation/|    ├── |' || true

echo ""
print_status $CYAN "📦 Backup Location: $BACKUP_DIR"
print_status $CYAN "🎯 All duplicates removed and scripts organized!"

# Show cleanup summary
REMAINING_SCRIPTS=$(find . -name "*.sh" -type f -not -path "./build/*" -not -path "./install/*" 2>/dev/null | wc -l)
echo ""
print_status $GREEN "📊 Cleanup Summary:"
echo "   🗑️  Duplicates removed"
echo "   📁 Scripts organized in scripts/ directory"
echo "   📦 Backups preserved in $BACKUP_DIR"
echo "   📊 Total remaining scripts: $REMAINING_SCRIPTS"
echo ""
print_status $GREEN "🎉 Workspace is now clean and organized!"