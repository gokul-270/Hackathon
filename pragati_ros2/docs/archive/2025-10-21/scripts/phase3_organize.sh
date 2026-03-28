#!/bin/bash
# Phase 3: Organize remaining active docs

cd /home/uday/Downloads/pragati_ros2

echo "Phase 3: Organizing active documentation"
echo "========================================"
echo ""

# Archive completed phase docs
echo "1. Archiving completed phase documents..."
for file in docs/PHASE*.md; do
    [ -f "$file" ] && git mv "$file" "docs/archive/2025-10-phases/$(basename $file)" 2>/dev/null || true
done

# Archive execution plans and old status
echo "2. Archiving old execution plans..."
git mv "docs/EXECUTION_PLAN_2025-09-30.md" "docs/archive/2025-10-plans/" 2>/dev/null || true
git mv "docs/STATUS_REVIEW_CORRECTION_2025-09-30.md" "docs/archive/2025-10-plans/" 2>/dev/null || true
git mv "docs/PHASE2_IMPLEMENTATION_PLAN.md" "docs/archive/2025-10-plans/" 2>/dev/null || true
git mv "docs/IMPLEMENTATION_PLAN_OCT2025.md" "docs/project-management/" 2>/dev/null || true

# Move guides to appropriate folders
echo "3. Organizing guides..."
# Hardware guides
git mv "docs/USB2_CONFIGURATION_GUIDE.md" "docs/guides/hardware/USB2_CONFIGURATION.md" 2>/dev/null || true

# Software guides  
git mv "docs/CPP_USAGE_GUIDE.md" "docs/guides/software/CPP_USAGE.md" 2>/dev/null || true
git mv "docs/BUILD_OPTIMIZATION_GUIDE.md" "docs/guides/software/BUILD_OPTIMIZATION.md" 2>/dev/null || true
git mv "docs/TESTING_AND_VALIDATION_PLAN.md" "docs/guides/software/TESTING_VALIDATION.md" 2>/dev/null || true

# Integration guides
git mv "docs/OAK_D_LITE_HYBRID_MIGRATION_PLAN.md" "docs/guides/integration/OAK_D_LITE_MIGRATION.md" 2>/dev/null || true
git mv "docs/OAK_D_LITE_MIGRATION_ANALYSIS.md" "docs/guides/integration/OAK_D_LITE_ANALYSIS.md" 2>/dev/null || true

# Architecture docs
git mv "docs/SAFETY_MONITOR_EXPLANATION.md" "docs/architecture/SAFETY_MONITOR.md" 2>/dev/null || true

# Archive analysis/review docs
echo "4. Archiving analysis documents..."
git mv "docs/SCRIPTS_CONSOLIDATION_ANALYSIS.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/DATA_FOLDERS_CONSOLIDATION_PLAN.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/COTTON_DETECTION_SENIOR_CODE_REVIEW.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/DEEP_DIVE_CODE_REVIEW.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/SECOND_DEEP_DIVE_REVIEW.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/CPP_NODE_COMPREHENSIVE_REVIEW_AND_TASKS.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/TASK_COMPARISON_PYTHON_VS_CPP.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/VERIFICATION_TRACEABILITY_MATRIX.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true
git mv "docs/ROS1_SCRIPT_VERIFICATION_REPORT.md" "docs/archive/2025-10-analysis/" 2>/dev/null || true

# Archive completion summaries
git mv "docs/PHASE0_COMPLETION_SUMMARY.md" "docs/archive/2025-10-phases/" 2>/dev/null || true
git mv "docs/PHASE1_1_COMPLETE.md" "docs/archive/2025-10-phases/" 2>/dev/null || true
git mv "docs/PHASE1_3_COMPLETE.md" "docs/archive/2025-10-phases/" 2>/dev/null || true
git mv "docs/PHASE1_4_COMPLETE.md" "docs/archive/2025-10-phases/" 2>/dev/null || true
git mv "docs/FIX_IMPLEMENTATION_SUMMARY.md" "docs/archive/2025-10-phases/" 2>/dev/null || true

# Archive old/redundant
git mv "docs/README_old.md" "docs/archive/2025-10-old/" 2>/dev/null || true
git mv "docs/DOCUMENTATION_ORGANIZATION.md" "docs/archive/2025-10-old/" 2>/dev/null || true

echo ""
echo "✓ Phase 3 complete"
echo ""
echo "Status: git status | head -30"
