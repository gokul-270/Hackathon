#!/bin/bash
# verify_cleanup.sh - Verify cleanup completed successfully
# Generated: 2025-10-07
# Part of: COMPREHENSIVE_DOC_ANALYSIS_2025-10-07.md

echo "=== Cleanup Verification ==="
echo ""

echo "1. Counting documentation files..."
DOC_COUNT=$(find . -type f \( -name "*.md" -o -name "*.txt" \) ! -path "*/logs/*" ! -path "*/.git/*" ! -path "*/venv/*" ! -path "*/build/*" ! -path "*/install/*" 2>/dev/null | wc -l)
echo "   Total documentation files: $DOC_COUNT"
echo "   Target: 100-120 files"
echo "   Before: 275 files"
if [ $DOC_COUNT -lt 150 ]; then
    echo "   ✅ PASS: File count reduced significantly"
else
    echo "   ⚠️  WARNING: File count still high"
fi

echo ""
echo "2. Checking for archive directory..."
if [ -d "docs/_archive" ]; then
    echo "   ⚠️  WARNING: docs/_archive/ still exists!"
else
    echo "   ✅ PASS: Archive deleted"
fi

echo ""
echo "3. Checking for archive references..."
ARCHIVE_REFS=$(grep -r "docs/_archive\|_archive/2025-10-06" . --exclude-dir=.git --exclude-dir=venv --exclude-dir=build --exclude-dir=install 2>/dev/null | wc -l)
echo "   Archive references found: $ARCHIVE_REFS"
if [ $ARCHIVE_REFS -eq 0 ]; then
    echo "   ✅ PASS: No archive references"
elif [ $ARCHIVE_REFS -lt 5 ]; then
    echo "   ⚠️  INFO: $ARCHIVE_REFS references (acceptable if in new analysis doc)"
else
    echo "   ⚠️  WARNING: Many archive references still present"
fi

echo ""
echo "4. Checking for duplicates..."
DUPES=$(find docs/ -type f -name "*.md" -exec md5sum {} \; 2>/dev/null | sort | uniq -d -w 32 | wc -l)
echo "   Duplicate files found: $DUPES"
if [ $DUPES -eq 0 ]; then
    echo "   ✅ PASS: No duplicates"
else
    echo "   ⚠️  WARNING: $DUPES duplicate files still present"
    echo "   Run: find docs/ -type f -name '*.md' -exec md5sum {} \; | sort | uniq -d -w 32"
fi

echo ""
echo "5. Checking documentation size..."
DOCS_SIZE=$(du -sh docs/ 2>/dev/null | awk '{print $1}')
echo "   docs/ directory size: $DOCS_SIZE"
echo "   Target: 3-4MB (before: 5.8MB)"

echo ""
echo "6. Checking log size..."
LOGS_SIZE=$(du -sh logs/ 2>/dev/null | awk '{print $1}')
LOG_COUNT=$(find logs/ -type f 2>/dev/null | wc -l)
echo "   logs/ directory size: $LOGS_SIZE"
echo "   Log files: $LOG_COUNT"
echo "   Target: 3-5MB, ~1000 files (before: 13MB, 3403 files)"

echo ""
echo "7. Verifying essential documents..."
ESSENTIAL_DOCS=(
    "README.md"
    "CHANGELOG.md"
    "docs/_generated/master_status.md"
    "docs/guides/COTTON_DETECTION_MIGRATION_GUIDE.md"
    "docs/reports/oakd_ros2_migration_analysis.md"
    "COMPREHENSIVE_DOC_ANALYSIS_2025-10-07.md"
)

ALL_PRESENT=true
for doc in "${ESSENTIAL_DOCS[@]}"; do
    if [ -f "$doc" ]; then
        echo "   ✅ $doc"
    else
        echo "   ❌ MISSING: $doc"
        ALL_PRESENT=false
    fi
done

echo ""
echo "8. Checking for removed files..."
SHOULD_BE_GONE=(
    "docs/_generated/COMPREHENSIVE_ANALYSIS_REPORT.md"
    "docs/_generated/MASTER_OAKD_LITE_STATUS.md"
    "docs/MIGRATION_COMPLETE_SUMMARY.md"
    "DOCUMENTATION_AUDIT_EXEC_SUMMARY.md"
    "DOCUMENTATION_AUDIT_WALKTHROUGH.md"
    "docs/web_dashboard_history/"
)

ALL_GONE=true
for doc in "${SHOULD_BE_GONE[@]}"; do
    if [ -e "$doc" ]; then
        echo "   ⚠️  STILL EXISTS: $doc"
        ALL_GONE=false
    else
        echo "   ✅ Removed: $doc"
    fi
done

echo ""
echo "=== Verification Complete ==="
echo ""

# Summary
if [ $DOC_COUNT -lt 150 ] && [ ! -d "docs/_archive" ] && [ $DUPES -eq 0 ] && $ALL_PRESENT && $ALL_GONE; then
    echo "✅ ✅ ✅ ALL CHECKS PASSED ✅ ✅ ✅"
    echo ""
    echo "Cleanup successful! Project documentation is now clean and organized."
    echo ""
    echo "Next steps:"
    echo "1. Review changes: git diff --stat"
    echo "2. Commit: git add -A && git commit -m 'docs: Major cleanup - remove 75+ redundant files'"
    echo "3. (Optional) Run cleanup_phase2.sh for log cleanup"
else
    echo "⚠️  SOME CHECKS FAILED"
    echo ""
    echo "Review the output above and re-run cleanup_phase1.sh if needed"
fi
