#!/bin/bash
# Documentation Reorganization Script
# Intelligently moves and organizes documentation files

set -e  # Exit on error

BASE_DIR="/home/uday/Downloads/pragati_ros2"
cd "$BASE_DIR"

echo "================================================"
echo "  Documentation Reorganization"
echo "  Started: $(date)"
echo "================================================"
echo ""

# Backup current state (in case we need to revert)
echo "1. Creating backup..."
git stash push -u -m "Pre-reorganization backup $(date +%Y%m%d_%H%M%S)"
echo "   ✓ Backup created (git stash)"
echo ""

# Phase 1: Move Root Level Files
echo "2. Organizing root level files..."

# Keep in root: README.md, LICENSE, CONTRIBUTING.md, CHANGELOG.md
# Move everything else

# Move completion/status docs to project-management
[ -f "COMPLETION_CHECKLIST.md" ] && git mv "COMPLETION_CHECKLIST.md" "docs/project-management/COMPLETION_CHECKLIST.md" 2>/dev/null || true
[ -f "REMAINING_TASKS.md" ] && git mv "REMAINING_TASKS.md" "docs/project-management/REMAINING_TASKS.md" 2>/dev/null || true
[ -f "SESSION_SUMMARY_OCT9.md" ] && git mv "SESSION_SUMMARY_OCT9.md" "docs/archive/2025-10/SESSION_SUMMARY_OCT9.md" 2>/dev/null || true
[ -f "PHASE_5_COMPLETE.md" ] && git mv "PHASE_5_COMPLETE.md" "docs/archive/2025-10/PHASE_5_COMPLETE.md" 2>/dev/null || true

# Move quick start to getting-started
[ -f "QUICK_START.md" ] && git mv "QUICK_START.md" "docs/getting-started/QUICK_START.md" 2>/dev/null || true

# Move hardware/test docs
[ -f "HARDWARE_TESTING_QUICKSTART.md" ] && git mv "HARDWARE_TESTING_QUICKSTART.md" "docs/guides/hardware/HARDWARE_TESTING_QUICKSTART.md" 2>/dev/null || true
[ -f "HARDWARE_TEST_RESULTS.md" ] && git mv "HARDWARE_TEST_RESULTS.md" "docs/archive/2025-10/HARDWARE_TEST_RESULTS.md" 2>/dev/null || true

# Move build/verification docs
[ -f "BUILD_VERIFICATION.md" ] && git mv "BUILD_VERIFICATION.md" "docs/guides/software/BUILD_VERIFICATION.md" 2>/dev/null || true

# Move RPi power management docs
[ -f "RPi_POWER_MGMT_FIX_SUMMARY.md" ] && git mv "RPi_POWER_MGMT_FIX_SUMMARY.md" "docs/guides/hardware/RPi_POWER_MGMT_FIX_SUMMARY.md" 2>/dev/null || true
[ -f "RPi_FIX_INSTRUCTIONS.md" ] && git mv "RPi_FIX_INSTRUCTIONS.md" "docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md" 2>/dev/null || true

# Move motor control docs to package-specific location
[ -f "CODE_DOC_MISMATCH_REPORT.md" ] && git mv "CODE_DOC_MISMATCH_REPORT.md" "src/motor_control_ros2/docs/CODE_DOC_MISMATCH_REPORT.md" 2>/dev/null || true
[ -f "MOTOR_CONTROL_COMPREHENSIVE_REVIEW.md" ] && git mv "MOTOR_CONTROL_COMPREHENSIVE_REVIEW.md" "src/motor_control_ros2/docs/MOTOR_CONTROL_COMPREHENSIVE_REVIEW.md" 2>/dev/null || true
[ -f "MOTOR_COMM_FIX_INSTRUCTIONS.md" ] && git mv "MOTOR_COMM_FIX_INSTRUCTIONS.md" "src/motor_control_ros2/docs/MOTOR_COMM_FIX_INSTRUCTIONS.md" 2>/dev/null || true
[ -f "MOTOR_COMM_ANALYSIS.md" ] && git mv "MOTOR_COMM_ANALYSIS.md" "src/motor_control_ros2/docs/MOTOR_COMM_ANALYSIS.md" 2>/dev/null || true

# Keep DOCUMENTATION_REORGANIZATION_PLAN in project-management
[ -f "DOCUMENTATION_REORGANIZATION_PLAN.md" ] && git mv "DOCUMENTATION_REORGANIZATION_PLAN.md" "docs/project-management/DOCUMENTATION_REORGANIZATION_PLAN.md" 2>/dev/null || true

echo "   ✓ Root level files organized"
echo ""

# Phase 2: Organize docs/ main folder
echo "3. Organizing docs/ main folder..."

# Move guides to appropriate subdirectories
cd docs/

# Hardware guides
for file in *CAN*.md *GPIO*.md *RPi*.md *RASPBERRY*.md; do
    [ -f "$file" ] && git mv "$file" "guides/hardware/$file" 2>/dev/null || true
done

# Software guides
for file in *BUILD*.md *TEST*.md *DEPLOY*.md *SCRIPT*.md; do
    [ -f "$file" ] && git mv "$file" "guides/software/$file" 2>/dev/null || true
done

# Integration guides
for file in *INTEGRATION*.md *MIGRATION*.md; do
    [ -f "$file" ] && git mv "$file" "guides/integration/$file" 2>/dev/null || true
done

# Move analysis docs to archive (most are outdated)
for file in *ANALYSIS*.md *REVIEW*.md *AUDIT*.md *STATUS*.md; do
    [ -f "$file" ] && git mv "$file" "archive/2025-10/$file" 2>/dev/null || true
done

# Move plan docs to project-management or archive
for file in *PLAN*.md *EXECUTION*.md; do
    [ -f "$file" ] && {
        # Check if from October 2025 (keep) or older (archive)
        if [[ "$file" == *"OCT2025"* ]] || [[ "$file" == *"2025-10"* ]]; then
            git mv "$file" "project-management/$file" 2>/dev/null || true
        else
            git mv "$file" "archive/2025-10/$file" 2>/dev/null || true
        fi
    }
done

cd "$BASE_DIR"
echo "   ✓ docs/ main folder organized"
echo ""

# Phase 3: Consolidate guides/ subdirectory
echo "4. Consolidating docs/guides/..."

# Move existing guides to new structure
if [ -d "docs/guides" ]; then
    # Move to appropriate new locations
    [ -f "docs/guides/CAN_BUS_SETUP_GUIDE.md" ] && git mv "docs/guides/CAN_BUS_SETUP_GUIDE.md" "docs/guides/hardware/CAN_BUS_SETUP.md" 2>/dev/null || true
    [ -f "docs/guides/GPIO_SETUP_GUIDE.md" ] && git mv "docs/guides/GPIO_SETUP_GUIDE.md" "docs/guides/hardware/GPIO_SETUP.md" 2>/dev/null || true
    [ -f "docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md" ] && git mv "docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md" "docs/guides/hardware/RASPBERRY_PI_DEPLOYMENT.md" 2>/dev/null || true
    
    # Software guides
    [ -f "docs/guides/SCRIPTS_GUIDE.md" ] && git mv "docs/guides/SCRIPTS_GUIDE.md" "docs/guides/software/SCRIPTS.md" 2>/dev/null || true
    
    # Integration guides
    [ -f "docs/guides/COTTON_DETECTION_MIGRATION_GUIDE.md" ] && git mv "docs/guides/COTTON_DETECTION_MIGRATION_GUIDE.md" "docs/guides/integration/COTTON_DETECTION_MIGRATION.md" 2>/dev/null || true
    [ -f "docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md" ] && git mv "docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md" "docs/guides/integration/SAFETY_MONITOR_INTEGRATION.md" 2>/dev/null || true
    [ -f "docs/guides/CAMERA_INTEGRATION_GUIDE.md" ] && git mv "docs/guides/CAMERA_INTEGRATION_GUIDE.md" "docs/guides/integration/CAMERA_INTEGRATION.md" 2>/dev/null || true
fi

echo "   ✓ Guides consolidated"
echo ""

# Phase 4: Move mg6010 docs to motor_control_ros2
echo "5. Moving mg6010 docs to motor_control package..."

if [ -d "docs/mg6010" ]; then
    for file in docs/mg6010/*.md; do
        [ -f "$file" ] && {
            basename=$(basename "$file")
            git mv "$file" "src/motor_control_ros2/docs/MG6010_${basename}" 2>/dev/null || true
        }
    done
    rmdir "docs/mg6010" 2>/dev/null || true
fi

# Also move MG6010_README_UPDATES.md
[ -f "docs/MG6010_README_UPDATES.md" ] && git mv "docs/MG6010_README_UPDATES.md" "src/motor_control_ros2/docs/MG6010_README_UPDATES.md" 2>/dev/null || true

echo "   ✓ MG6010 docs moved to motor_control_ros2"
echo ""

# Phase 5: Archive old analysis and audit folders
echo "6. Archiving old analysis/audit/reports..."

# Move entire subdirectories to archive
[ -d "docs/analysis" ] && git mv "docs/analysis" "docs/archive/2025-10/analysis" 2>/dev/null || true
[ -d "docs/audit" ] && git mv "docs/audit" "docs/archive/2025-10/audit" 2>/dev/null || true
[ -d "docs/reports" ] && git mv "docs/reports" "docs/archive/2025-10/reports" 2>/dev/null || true

# Move existing archive to date-specific folder
if [ -d "docs/archive/PROJECT_STATUS_REALITY_CHECK.md" ]; then
    git mv "docs/archive/"*.md "docs/archive/2025-10/" 2>/dev/null || true
fi

echo "   ✓ Old folders archived"
echo ""

# Phase 6: Clean up artifacts and generated folders
echo "7. Archiving artifacts and generated content..."

[ -d "docs/artifacts" ] && git mv "docs/artifacts" "docs/archive/2025-10/artifacts" 2>/dev/null || true
[ -d "docs/_generated" ] && git mv "docs/_generated" "docs/archive/2025-10/generated" 2>/dev/null || true
[ -d "docs/comparison" ] && git mv "docs/comparison" "docs/archive/2025-10/comparison" 2>/dev/null || true
[ -d "docs/validation" ] && git mv "docs/validation" "docs/archive/2025-10/validation" 2>/dev/null || true

echo "   ✓ Artifacts archived"
echo ""

# Phase 7: Move integration docs
echo "8. Organizing integration docs..."

if [ -d "docs/integration" ]; then
    for file in docs/integration/*.md; do
        [ -f "$file" ] && {
            basename=$(basename "$file")
            git mv "$file" "docs/guides/integration/$basename" 2>/dev/null || true
        }
    done
    rmdir "docs/integration" 2>/dev/null || true
fi

echo "   ✓ Integration docs organized"
echo ""

echo "================================================"
echo "  Phase 1 Complete: File Movement"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Review moved files: git status"
echo "2. Run consolidation script (merge duplicates)"
echo "3. Update content (fix ODrive refs, remove old tasks)"
echo "4. Update internal links"
echo "5. Commit: git commit -m 'docs: Reorganize documentation structure'"
echo ""
echo "To undo: git reset --hard HEAD"
