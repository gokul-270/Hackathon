#!/bin/bash
# cleanup_phase1.sh - Delete archive and obvious duplicates
# Generated: 2025-10-07
# Part of: COMPREHENSIVE_DOC_ANALYSIS_2025-10-07.md

set -e  # Exit on error

echo "=== Documentation Cleanup Phase 1 ==="
echo ""

# Safety check
if [ ! -d "docs/_archive" ]; then
    echo "ERROR: docs/_archive not found. Are you in the right directory?"
    exit 1
fi

echo "Step 1: Deleting archive directory..."
rm -rf docs/_archive/
echo "✅ Deleted docs/_archive/ (41 files)"

echo ""
echo "Step 2: Removing duplicate files..."

# Remove exact duplicate
if [ -f "docs/_generated/COMPREHENSIVE_ANALYSIS_REPORT.md" ]; then
    rm docs/_generated/COMPREHENSIVE_ANALYSIS_REPORT.md
    echo "✅ Deleted COMPREHENSIVE_ANALYSIS_REPORT.md (duplicate)"
fi

# Remove near-duplicate
if [ -f "docs/_generated/MASTER_OAKD_LITE_STATUS.md" ]; then
    rm docs/_generated/MASTER_OAKD_LITE_STATUS.md
    echo "✅ Deleted MASTER_OAKD_LITE_STATUS.md (near-duplicate)"
fi

# Remove redundant completion docs
if [ -f "docs/MIGRATION_COMPLETE_SUMMARY.md" ]; then
    rm docs/MIGRATION_COMPLETE_SUMMARY.md
    echo "✅ Deleted MIGRATION_COMPLETE_SUMMARY.md"
fi

if [ -f "docs/_generated/FINAL_PROJECT_COMPLETION_SUMMARY.md" ]; then
    rm docs/_generated/FINAL_PROJECT_COMPLETION_SUMMARY.md
    echo "✅ Deleted FINAL_PROJECT_COMPLETION_SUMMARY.md"
fi

echo ""
echo "Step 3: Cleaning _generated/ directory..."

cd docs/_generated/

# Delete old session summaries
rm -f SESSION_REVIEW_FINAL.md
rm -f SESSION_SUMMARY_2025-10-07.md
echo "✅ Deleted old session summaries"

# Delete raw data files
rm -f todo_index_raw.txt
rm -f ros2_interfaces_raw.txt
rm -f oakd_references_raw.txt
rm -f code_inventory.txt
rm -f docs_file_list.txt
rm -f docs_file_list_actual.txt
rm -f AUDIT_CONTEXT_2025-09-30.txt
echo "✅ Deleted raw data files"

# Delete logs (should be in logs/)
rm -f colcon_build.log
rm -f colcon_test.log
rm -f colcon_build_after_calibration_fix.log
rm -f analysis_session.log
rm -f *.log
echo "✅ Deleted misplaced log files"

# Delete meta-documentation
rm -f doc_summaries.md
rm -f doc_cleanup_recommendations.md
rm -f discrepancy_log.md
echo "✅ Deleted meta-documentation"

# Delete old generated scripts
rm -f COMMIT_READY.sh
echo "✅ Deleted obsolete scripts"

cd ../..

echo ""
echo "Step 4: Cleaning root directory..."

# Delete audit documents
rm -f DOCUMENTATION_AUDIT_EXEC_SUMMARY.md
rm -f DOCUMENTATION_AUDIT_WALKTHROUGH.md
rm -f AUDIT_GAP_ANALYSIS.md
rm -f BASELINE_SNAPSHOT.md
rm -f HARDWARE_TEST_SUCCESS.md
echo "✅ Deleted audit/baseline documents"

# Optional: Delete large manifest if verified as temporary
# rm -f pragati_ros2_20250930_133927_complete_manifest.txt

echo ""
echo "Step 5: Moving misplaced documentation..."

# Create validation directory if needed
mkdir -p docs/validation

# Move markdown files from logs/ to docs/
if [ -f "logs/launch_file_analysis.md" ]; then
    mv logs/launch_file_analysis.md docs/reports/
    echo "✅ Moved launch_file_analysis.md to docs/reports/"
fi

if [ -f "logs/colleague_workflow_validation_report.md" ]; then
    mv logs/colleague_workflow_validation_report.md docs/validation/
    echo "✅ Moved colleague_workflow_validation_report.md to docs/validation/"
fi

if [ -f "logs/FIX_VERIFICATION_SUMMARY.md" ]; then
    mv logs/FIX_VERIFICATION_SUMMARY.md docs/validation/
    echo "✅ Moved FIX_VERIFICATION_SUMMARY.md to docs/validation/"
fi

echo ""
echo "Step 6: Cleaning web dashboard history..."

if [ -d "docs/web_dashboard_history" ]; then
    rm -rf docs/web_dashboard_history/
    echo "✅ Deleted docs/web_dashboard_history/ (9 deprecated files)"
fi

echo ""
echo "=== Phase 1 Complete ==="
echo ""
echo "Files removed: ~65-75 files"
echo "Archive deleted: 41 files"
echo "Duplicates removed: ~20-25 files"
echo "Meta-docs removed: ~10 files"
echo ""
echo "Next steps:"
echo "1. Review changes: git status"
echo "2. Run verify_cleanup.sh to check results"
echo "3. Optionally run cleanup_phase2.sh for logs"
echo "4. Commit changes: git add -A && git commit -m 'docs: Comprehensive cleanup - remove 75 redundant files'"
