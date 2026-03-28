#!/bin/bash

################################################################################
# Script Cleanup and Organization Tool
# 
# This script identifies and resolves duplicate/confusing validation scripts
# to create a clean, easy-to-use testing environment.
################################################################################

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

echo ""
print_status $PURPLE "🧹 SCRIPT CLEANUP AND ORGANIZATION"
print_status $PURPLE "=================================="
echo ""

# Phase 1: Identify duplicates and confusing scripts
print_status $BLUE "📋 Phase 1: Identifying problematic scripts..."
echo ""

# List scripts that are redundant or confusing
REDUNDANT_SCRIPTS=(
    "scripts/validation_scripts/final_migration_validation.sh"
    "scripts/validation_scripts/final_validation.sh"
    "scripts/validation_scripts/pre_upload_verification.sh"
    "scripts/validation_scripts/validate_critical_fixes.sh"
    "scripts/validation_scripts/validate_expected_components.sh"
    "scripts/validation_scripts/validate_services.sh"
)

DUPLICATED_TESTS=(
    "scripts/validation_scripts/test_hw_interface.sh"  # Duplicate of test_hardware_interface.sh
    "scripts/validation_scripts/test_odrive_fixed.sh"  # Redundant with test_odrive.sh
)

print_status $YELLOW "⚠️  Found redundant validation scripts:"
for script in "${REDUNDANT_SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        print_status $CYAN "   - $(basename "$script")"
    fi
done

echo ""
print_status $YELLOW "⚠️  Found duplicate test scripts:"
for script in "${DUPLICATED_TESTS[@]}"; do
    if [ -f "$script" ]; then
        print_status $CYAN "   - $(basename "$script")"
    fi
done

echo ""

# Phase 2: Create clear script organization
print_status $BLUE "🎯 Phase 2: Creating clear organization..."
echo ""

# Move redundant scripts to archive
print_status $CYAN "Moving redundant scripts to archive..."
for script in "${REDUNDANT_SCRIPTS[@]}" "${DUPLICATED_TESTS[@]}"; do
    if [ -f "$script" ]; then
        mv "$script" scripts/archive/ 2>/dev/null && print_status $GREEN "✅ Archived $(basename "$script")"
    fi
done

echo ""

# Phase 3: Create a clear testing guide
print_status $BLUE "📚 Phase 3: Creating clear testing guide..."

cat > scripts/TESTING_GUIDE.md << 'EOF'
# 🧪 **PRAGATI ROS2 TESTING GUIDE**
===============================

## 🎯 **MAIN TESTING SCRIPTS** (Use These!)

### 🏆 **RECOMMENDED: Complete Validation**
```bash
# Run complete system validation (filesystem + runtime)
./scripts/deployment/complete_validation.sh
```

### ⚡ **QUICK: Filesystem Only**
```bash
# Fast filesystem and build validation
./scripts/deployment/clean_system_validation.sh
```

### 🚀 **RUNTIME: Runtime Only** 
```bash
# ROS2 runtime functionality testing
./scripts/deployment/runtime_validation.sh
```

---

## 🔧 **COMPONENT TESTING SCRIPTS** (Advanced Use)

### Core Component Tests:
- `scripts/validation_scripts/test_odrive.sh` - ODrive hardware interface
- `scripts/validation_scripts/test_integration.sh` - System integration
- `scripts/validation_scripts/test_hardware_interface.sh` - Hardware interfaces
- `scripts/validation_scripts/test_launch.sh` - Launch file testing
- `scripts/validation_scripts/test_all_services.sh` - ROS2 services
- `scripts/validation_scripts/test_odrive_services.sh` - ODrive services
- `scripts/validation_scripts/test_safety_monitoring.sh` - Safety systems

### Python Tests:
- `scripts/validation_scripts/test_odrive.py` - Python ODrive testing
- `scripts/validation_scripts/test_odrive_simple.py` - Simple ODrive test

---

## 📦 **DEPLOYMENT SCRIPTS**

- `scripts/deployment/create_upload_package.sh` - Create deployment package
- `scripts/deployment/setup_and_test.sh` - Initial setup

---

## 🎯 **USAGE RECOMMENDATIONS**

### **For Regular Development:**
```bash
# After making changes
./scripts/deployment/complete_validation.sh
```

### **For CI/CD Pipeline:**
```bash
# Fast validation
./scripts/deployment/clean_system_validation.sh
```

### **For Debugging Issues:**
```bash
# Step-by-step validation
./scripts/deployment/clean_system_validation.sh
./scripts/deployment/runtime_validation.sh

# Or specific component
./scripts/validation_scripts/test_odrive.sh
```

### **For Deployment:**
```bash
# Full validation + packaging
./scripts/deployment/complete_validation.sh && \
./scripts/deployment/create_upload_package.sh
```

---

## ✅ **WHAT EACH MAIN SCRIPT DOES**

| Script | Tests | Time | Use When |
|--------|-------|------|----------|
| `complete_validation.sh` | 50 tests (29+21) | ~60s | **Regular testing** |
| `clean_system_validation.sh` | 29 filesystem tests | ~15s | **Quick checks** |
| `runtime_validation.sh` | 21 runtime tests | ~45s | **Runtime debugging** |

---

## 📁 **FOLDER ORGANIZATION**

```
scripts/
├── deployment/           # Main testing & deployment
│   ├── complete_validation.sh     ⭐ MAIN SCRIPT
│   ├── clean_system_validation.sh ⭐ QUICK SCRIPT  
│   ├── runtime_validation.sh      ⭐ RUNTIME SCRIPT
│   └── create_upload_package.sh   📦 PACKAGING
├── validation_scripts/   # Component testing
│   ├── test_odrive.sh             🔧 ODrive testing
│   ├── test_integration.sh        🔧 Integration
│   └── test_*.sh                  🔧 Other components
└── archive/             # Old/redundant scripts
    └── *.sh             📦 Archived scripts
```

---

## 🚨 **IMPORTANT: Which Scripts NOT to Use**

**❌ Don't use these (archived):**
- `final_migration_validation.sh` - Replaced by complete_validation.sh
- `final_validation.sh` - Replaced by complete_validation.sh
- `pre_upload_verification.sh` - Replaced by complete_validation.sh
- `test_hw_interface.sh` - Duplicate of test_hardware_interface.sh
- `test_odrive_fixed.sh` - Redundant with test_odrive.sh

**✅ Use these instead:**
- `complete_validation.sh` - For comprehensive testing
- `clean_system_validation.sh` - For quick validation
- `runtime_validation.sh` - For runtime testing

EOF

print_status $GREEN "✅ Created comprehensive testing guide: scripts/TESTING_GUIDE.md"

echo ""

# Phase 4: Create a simple launcher script
print_status $BLUE "🚀 Phase 4: Creating simple launcher..."

cat > scripts/test.sh << 'EOF'
#!/bin/bash

################################################################################
# Simple Test Launcher
# 
# Easy-to-remember script for running tests
################################################################################

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() {
    echo -e "${1}${2}${NC}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
print_status $BLUE "🧪 PRAGATI ROS2 TEST LAUNCHER"
print_status $BLUE "============================="
echo ""

case "${1:-complete}" in
    "complete"|"all"|"full")
        print_status $CYAN "🎯 Running complete validation..."
        "$SCRIPT_DIR/deployment/complete_validation.sh"
        ;;
    "quick"|"fast"|"filesystem")
        print_status $CYAN "⚡ Running quick filesystem validation..."
        "$SCRIPT_DIR/deployment/clean_system_validation.sh"
        ;;
    "runtime"|"ros2")
        print_status $CYAN "🚀 Running runtime validation..."
        "$SCRIPT_DIR/deployment/runtime_validation.sh"
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [test_type]"
        echo ""
        echo "Test types:"
        echo "  complete    Complete validation (default)"
        echo "  quick       Quick filesystem validation"
        echo "  runtime     Runtime validation only"
        echo "  help        Show this help"
        echo ""
        echo "Examples:"
        echo "  $0                # Complete validation"
        echo "  $0 complete       # Complete validation"
        echo "  $0 quick          # Quick validation"
        echo "  $0 runtime        # Runtime validation"
        ;;
    *)
        print_status $CYAN "🎯 Running complete validation (default)..."
        "$SCRIPT_DIR/deployment/complete_validation.sh"
        ;;
esac
EOF

chmod +x scripts/test.sh
print_status $GREEN "✅ Created simple launcher: scripts/test.sh"

echo ""

# Final summary
print_status $PURPLE "🏆 CLEANUP COMPLETE!"
print_status $PURPLE "===================="
echo ""

print_status $GREEN "✅ Redundant scripts archived"
print_status $GREEN "✅ Clear testing guide created" 
print_status $GREEN "✅ Simple launcher created"

echo ""
print_status $CYAN "🎯 **NOW USE THESE SIMPLE COMMANDS:**"
echo ""
print_status $BLUE "   # Complete testing (recommended)"
print_status $CYAN "   ./scripts/test.sh"
echo ""
print_status $BLUE "   # Quick testing"
print_status $CYAN "   ./scripts/test.sh quick"
echo ""
print_status $BLUE "   # Runtime testing"
print_status $CYAN "   ./scripts/test.sh runtime"
echo ""
print_status $BLUE "   # View testing guide"
print_status $CYAN "   cat scripts/TESTING_GUIDE.md"

echo ""
print_status $GREEN "🎉 Testing is now clean, simple, and easy to use!"
