#!/bin/bash
# Phase 4: Clean up root directory

cd /home/uday/Downloads/pragati_ros2

echo "Phase 4: Cleaning root directory"
echo "================================="
echo ""

# Keep in root: README.md, CHANGELOG.md, LICENSE
# Move everything else

echo "1. Moving quick start to getting-started..."
git mv "QUICK_START.md" "docs/getting-started/QUICK_START.md" 2>/dev/null || true

echo "2. Moving hardware docs to guides..."
git mv "HARDWARE_TESTING_QUICKSTART.md" "docs/guides/hardware/HARDWARE_TESTING_QUICKSTART.md" 2>/dev/null || true
git mv "RPi_FIX_INSTRUCTIONS.md" "docs/guides/hardware/RPi_FIX_INSTRUCTIONS.md" 2>/dev/null || true
git mv "RPi_POWER_MGMT_FIX_SUMMARY.md" "docs/guides/hardware/RPi_POWER_MGMT_FIX.md" 2>/dev/null || true

echo "3. Moving build docs..."
git mv "BUILD_VERIFICATION.md" "docs/guides/software/BUILD_VERIFICATION.md" 2>/dev/null || true

echo "4. Moving project management docs..."
git mv "COMPLETION_CHECKLIST.md" "docs/project-management/COMPLETION_CHECKLIST.md" 2>/dev/null || true
git mv "REMAINING_TASKS.md" "docs/project-management/REMAINING_TASKS.md" 2>/dev/null || true
git mv "DOCUMENTATION_REORGANIZATION_PLAN.md" "docs/project-management/DOCUMENTATION_REORGANIZATION_PLAN.md" 2>/dev/null || true

echo "5. Archiving completed phases and sessions..."
git mv "PHASE_5_COMPLETE.md" "docs/archive/2025-10-phases/PHASE_5_COMPLETE.md" 2>/dev/null || true
git mv "SESSION_SUMMARY_OCT9.md" "docs/archive/2025-10-sessions/SESSION_SUMMARY_OCT9.md" 2>/dev/null || true
git mv "HARDWARE_TEST_RESULTS.md" "docs/archive/2025-10-test-results/HARDWARE_TEST_RESULTS.md" 2>/dev/null || true

echo ""
echo "✓ Phase 4 complete"
echo ""
echo "Remaining root files:"
find . -maxdepth 1 -name "*.md" -type f | sort
