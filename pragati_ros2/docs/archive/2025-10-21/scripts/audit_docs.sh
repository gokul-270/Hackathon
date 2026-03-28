#!/bin/bash
# Documentation Audit Script
# Analyzes current documentation state

cd /home/uday/Downloads/pragati_ros2

echo "================================================"
echo "  Documentation Audit Report"
echo "  Generated: $(date)"
echo "================================================"
echo ""

echo "1. TOTAL MARKDOWN FILES"
echo "   Total: $(find . -name "*.md" | wc -l) files"
echo ""

echo "2. FILES BY LOCATION"
echo "   Root level:        $(find . -maxdepth 1 -name "*.md" | wc -l) files"
echo "   docs/:             $(find docs/ -name "*.md" 2>/dev/null | wc -l) files"
echo "   src/ (all):        $(find src/ -name "*.md" 2>/dev/null | wc -l) files"
echo "   src/motor_control: $(find src/motor_control_ros2/ -name "*.md" 2>/dev/null | wc -l) files"
echo ""

echo "3. CONTENT ISSUES"
echo "   ODrive references:        $(grep -r "ODrive" --include="*.md" . 2>/dev/null | wc -l) occurrences"
echo "   Old cotton detect refs:   $(grep -r "detect_cotton_srv" --include="*.md" . 2>/dev/null | wc -l) occurrences"
echo "   Pending task lists:       $(grep -r "^[[:space:]]*- \[ \]" --include="*.md" . 2>/dev/null | wc -l) items"
echo "   TODO/PENDING markers:     $(grep -r "TODO\|PENDING" --include="*.md" . 2>/dev/null | wc -l) occurrences"
echo "   Old dates (2024-earlier): $(grep -r "2024\|2023\|2022" --include="*.md" . 2>/dev/null | wc -l) occurrences"
echo ""

echo "4. FILE SIZE DISTRIBUTION"
echo "   Over 1000 lines: $(find . -name "*.md" -exec wc -l {} \; 2>/dev/null | awk '$1 > 1000' | wc -l) files"
echo "   Over 500 lines:  $(find . -name "*.md" -exec wc -l {} \; 2>/dev/null | awk '$1 > 500' | wc -l) files"
echo "   Over 200 lines:  $(find . -name "*.md" -exec wc -l {} \; 2>/dev/null | awk '$1 > 200' | wc -l) files"
echo ""

echo "5. TOP 10 LARGEST FILES"
find . -name "*.md" -exec wc -l {} \; 2>/dev/null | sort -rn | head -10
echo ""

echo "6. DUPLICATE FILE NAMES"
echo "   (Files with same name in different locations)"
find . -name "*.md" -printf "%f\n" | sort | uniq -d | head -10
echo ""

echo "7. FILES IN ROOT DIRECTORY"
find . -maxdepth 1 -name "*.md" -type f
echo ""

echo "8. docs/ SUBDIRECTORIES"
find docs/ -type d 2>/dev/null | sort
echo ""

echo "9. POTENTIAL DUPLICATES (CAN setup)"
echo "   Files mentioning CAN setup:"
grep -l "CAN.*setup\|setup.*CAN" --include="*.md" -r . 2>/dev/null | wc -l
echo ""

echo "10. POTENTIAL DUPLICATES (Build instructions)"
echo "    Files mentioning build/colcon:"
grep -l "colcon build\|Build.*instruction" --include="*.md" -r . 2>/dev/null | wc -l
echo ""

echo "================================================"
echo "  Audit Complete"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Review this report"
echo "2. Commit current changes: git add . && git commit -m 'docs: ...'"
echo "3. Follow DOCUMENTATION_REORGANIZATION_PLAN.md"
