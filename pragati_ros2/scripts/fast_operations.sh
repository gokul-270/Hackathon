#!/bin/bash

################################################################################
# PRAGATI FAST OPERATIONS - Optimized Workflow
################################################################################
# Fast, lightweight operations that won't overwhelm the system
################################################################################

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$WORKSPACE_ROOT"

print_status $CYAN "⚡ PRAGATI FAST OPERATIONS"
print_status $CYAN "==========================="

echo ""
print_status $BLUE "🚀 FAST OPERATIONS MENU:"
echo ""
echo "1) ⚡ Quick Check (2-3 seconds)"
echo "   - Validates workspace essentials"
echo "   - No heavy operations"
echo "   - Confirms everything is ready"
echo ""
echo "2) 🏗️  Fast Build (10-30 seconds)"
echo "   - Targeted package building"
echo "   - Limited parallel workers"
echo "   - Builds only what you need"
echo ""
echo "3) 📦 Smart Package (2-3 minutes)"
echo "   - Optimized packaging"
echo "   - Automatic cleanup"
echo "   - Ready for upload"
echo ""
echo "4) 🔍 Light Validation (5-10 seconds)"
echo "   - Essential checks only"
echo "   - No resource-intensive tests"
echo "   - Quick status confirmation"
echo ""

print_status $YELLOW "💡 PERFORMANCE OPTIMIZATIONS:"
echo "   • Limited CPU usage (--parallel-workers=2)"
echo "   • Targeted operations (not full workspace)"
echo "   • Fast checks instead of heavy validation"
echo "   • Automatic cleanup of old files"
echo "   • Quick feedback on status"
echo ""

read -p "Choose operation (1-4) or 'q' to quit: " choice

case $choice in
    1)
        print_status $BLUE "⚡ Running Quick Check..."
        "$WORKSPACE_ROOT/scripts/validation/quick_check.sh"
        ;;
    2)
        print_status $BLUE "🏗️  Starting Fast Build..."
        "$WORKSPACE_ROOT/scripts/build/fast_build.sh"
        ;;
    3)
        print_status $BLUE "📦 Creating Smart Package..."
        "$WORKSPACE_ROOT/scripts/build/create_upload_package.sh"
        ;;
    4)
        print_status $BLUE "🔍 Running Light Validation..."
        "$WORKSPACE_ROOT/scripts/validation/comprehensive_validation.sh"
        ;;
    q|Q)
        print_status $GREEN "👋 Goodbye!"
        exit 0
        ;;
    *)
        print_status $RED "❌ Invalid choice. Please select 1-4 or 'q' to quit."
        exit 1
        ;;
esac

echo ""
print_status $GREEN "🎉 OPERATION COMPLETE!"
echo ""
print_status $BLUE "💡 Remember: These operations are designed to be fast and system-friendly!"
echo "   They won't cause system unresponsiveness or require restarts."