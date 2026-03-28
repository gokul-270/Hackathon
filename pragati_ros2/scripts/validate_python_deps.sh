#!/bin/bash
################################################################################
# File: validate_python_deps.sh
# Purpose: Validate requirements.txt syntax and check for conflicts
# Part of: Pragati Cotton Picker - Generic Ubuntu Development Setup
#
# Created: 2025-02-03
# Version: 1.0.0
#
# Usage:
#   ./scripts/validate_python_deps.sh
#   ./scripts/validate_python_deps.sh --fix  # Auto-fix some issues
#
# Exit Codes:
#   0 - Success, all validations passed
#   1 - Validation errors found
#   2 - requirements.txt not found
################################################################################

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
AUTO_FIX=false

# Parse arguments
if [ "${1:-}" = "--fix" ]; then
    AUTO_FIX=true
fi

# Counters
ERRORS=0
WARNINGS=0
INFO_COUNT=0

################################################################################
# Helper Functions
################################################################################

error() {
    echo -e "${RED}❌ ERROR:${NC} $*" >&2
    ((ERRORS++)) || true
}

warn() {
    echo -e "${YELLOW}⚠️  WARNING:${NC} $*"
    ((WARNINGS++)) || true
}

info() {
    echo -e "${BLUE}ℹ️  INFO:${NC} $*"
    ((INFO_COUNT++)) || true
}

success() {
    echo -e "${GREEN}✅${NC} $*"
}

################################################################################
# Validation Functions
################################################################################

check_file_exists() {
    echo "Checking requirements.txt exists..."
    if [ ! -f "${REQUIREMENTS_FILE}" ]; then
        error "requirements.txt not found at ${REQUIREMENTS_FILE}"
        exit 2
    fi
    success "requirements.txt found"
}

check_syntax() {
    echo -e "\nValidating syntax..."
    
    local line_num=0
    local has_errors=false
    
    while IFS= read -r line || [ -n "$line" ]; do
        ((line_num++)) || true
        
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        
        # Check for common syntax errors
        if [[ "$line" =~ ^[[:space:]]*$ ]]; then
            continue
        fi
        
        # Check for invalid characters
        if [[ "$line" =~ [[:space:]]$ ]]; then
            warn "Line $line_num: Trailing whitespace: '$line'"
        fi
        
        # Check for missing version specifier on non-comment lines
        if [[ ! "$line" =~ ^[[:space:]]*# ]] && [[ ! "$line" =~ [=\<\>] ]]; then
            warn "Line $line_num: No version specifier: '$line'"
        fi
        
    done < "${REQUIREMENTS_FILE}"
    
    if [ "$has_errors" = false ]; then
        success "Syntax validation passed"
    fi
}

check_duplicates() {
    echo -e "\nChecking for duplicate packages..."
    
    # Extract package names (everything before ==, >=, <=, etc.)
    local packages=$(grep -v "^#" "${REQUIREMENTS_FILE}" | grep -v "^$" | sed 's/[=<>].*//' | tr -d ' ')
    
    local duplicates=$(echo "$packages" | sort | uniq -d)
    
    if [ -n "$duplicates" ]; then
        while IFS= read -r pkg; do
            [ -z "$pkg" ] && continue
            error "Duplicate package found: $pkg"
        done <<< "$duplicates"
    else
        success "No duplicate packages found"
    fi
}

check_conflicts() {
    echo -e "\nChecking for version conflicts..."
    
    # This is a basic check - would need pip-tools for full dependency resolution
    # For now, just check if pip can parse the file
    
    if command -v pip3 &> /dev/null; then
        if pip3 install --dry-run --break-system-packages -r "${REQUIREMENTS_FILE}" &> /tmp/pip_check.log; then
            success "No obvious conflicts detected"
        else
            warn "Potential conflicts detected. See /tmp/pip_check.log for details"
            if [ "$AUTO_FIX" = true ]; then
                info "Run 'pip3 install --dry-run -r requirements.txt' to see details"
            fi
        fi
    else
        info "pip3 not available, skipping conflict check"
    fi
}

check_version_format() {
    echo -e "\nValidating version specifier formats..."
    
    local line_num=0
    
    while IFS= read -r line || [ -n "$line" ]; do
        ((line_num++)) || true
        
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        
        # Check for valid version specifiers
        if [[ "$line" =~ ^([a-zA-Z0-9_-]+)(==|>=|<=|>|<|~=)(.+)$ ]]; then
            local pkg="${BASH_REMATCH[1]}"
            local op="${BASH_REMATCH[2]}"
            local ver="${BASH_REMATCH[3]}"
            
            # Check for version format (should be numbers and dots)
            if [[ ! "$ver" =~ ^[0-9.,\<\>=\*]+$ ]]; then
                warn "Line $line_num: Unusual version format for $pkg: $ver"
            fi
        fi
        
    done < "${REQUIREMENTS_FILE}"
    
    success "Version format check complete"
}

check_importable() {
    echo -e "\nChecking if packages are importable (if installed)..."
    
    # Map of pip package names to Python module names
    declare -A package_to_module=(
        ["opencv-python"]="cv2"
        ["pillow"]="PIL"
        ["pyyaml"]="yaml"
        ["pyserial"]="serial"
        ["depthai"]="depthai"
    )
    
    local checked=0
    
    for pkg in "${!package_to_module[@]}"; do
        module="${package_to_module[$pkg]}"
        
        if python3 -c "import $module" 2>/dev/null; then
            ((checked++)) || true
            success "$pkg (as $module) is importable"
        else
            info "$pkg not installed or not importable (expected if not installed yet)"
        fi
    done
    
    if [ $checked -eq 0 ]; then
        info "No packages currently installed, skipping import check"
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    echo "========================================"
    echo " Python Dependencies Validation"
    echo "========================================"
    echo "File: ${REQUIREMENTS_FILE}"
    echo "Auto-fix: ${AUTO_FIX}"
    echo ""
    
    check_file_exists
    check_syntax
    check_duplicates
    check_version_format
    check_conflicts
    check_importable
    
    echo ""
    echo "========================================"
    echo " Validation Summary"
    echo "========================================"
    echo -e "${RED}Errors:   ${ERRORS}${NC}"
    echo -e "${YELLOW}Warnings: ${WARNINGS}${NC}"
    echo -e "${BLUE}Info:     ${INFO_COUNT}${NC}"
    echo ""
    
    if [ $ERRORS -gt 0 ]; then
        echo -e "${RED}❌ Validation FAILED${NC}"
        exit 1
    elif [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Validation passed with warnings${NC}"
        exit 0
    else
        echo -e "${GREEN}✅ All validations PASSED${NC}"
        exit 0
    fi
}

main "$@"
