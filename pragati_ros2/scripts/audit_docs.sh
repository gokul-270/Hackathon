#!/bin/bash
# Documentation Audit Script - November 1, 2025
# Comprehensive audit of all documentation for outdated information

set -e

AUDIT_DATE="2025-11-01"
REPORT_FILE="DOCUMENTATION_AUDIT_REPORT_${AUDIT_DATE}.md"

echo "🔍 Starting Comprehensive Documentation Audit..."
echo "Date: $AUDIT_DATE"
echo ""

# Create report header
cat > "$REPORT_FILE" << 'EOF'
# Documentation Audit Report - November 1, 2025

**Generated:** $(date)  
**Purpose:** Comprehensive audit of all documentation  
**Status:** 🔍 **AUDIT COMPLETE**

---

## 📊 Executive Summary

This report identifies documentation that needs updating based on:
- Outdated performance metrics
- Old status claims
- Pending/TODO items that may be complete
- Old dates and timestamps
- Broken or outdated references

---

## 🔍 Audit Results

EOF

echo "## 1️⃣ Scanning for Outdated Performance Metrics..." | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Find files mentioning old detection times
echo "### Files Mentioning Old Detection Times (7-8 seconds)" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
grep -r "7-8.*second\|7.*8.*second\|8.*second.*detection" docs/ README.md STATUS*.md \
    --include="*.md" 2>/dev/null | head -20 | tee -a "$REPORT_FILE" || echo "None found" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Find files mentioning 6 second latency
echo "### Files Mentioning 6 Second Latency (ROS2 CLI issue)" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
grep -r "6.*second.*latency\|6s.*latency" docs/ README.md STATUS*.md \
    --include="*.md" 2>/dev/null | head -20 | tee -a "$REPORT_FILE" || echo "None found" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

echo "## 2️⃣ Scanning for Status Claims..." | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Find "pending" status
echo "### Files With 'Pending' Status" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
grep -r "Status.*[Pp]ending\|validation pending\|testing pending" docs/ README.md \
    --include="*.md" 2>/dev/null | head -30 | tee -a "$REPORT_FILE" || echo "None found" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Find "TODO" items
echo "### Files With TODO Items" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
grep -r "TODO:\|\\[ \\] TODO" docs/ README.md \
    --include="*.md" 2>/dev/null | wc -l | tee -a "$REPORT_FILE"
echo "See full list in separate TODO extraction" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

echo "## 3️⃣ Scanning for Old Dates..." | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Find files with old October dates
echo "### Files Referencing October 2025 Dates (Before Oct 30)" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
grep -r "2025-10-2[0-8]\|October 2[0-8], 2025\|Oct 2[0-8]" docs/ README.md \
    --include="*.md" 2>/dev/null | wc -l | tee -a "$REPORT_FILE"
echo "files need date review" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

echo "## 4️⃣ Package READMEs Status..." | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Check package READMEs
for pkg in src/*/README.md; do
    if [ -f "$pkg" ]; then
        echo "- $pkg: EXISTS" | tee -a "$REPORT_FILE"
        # Check last modified
        stat -c "  Last modified: %y" "$pkg" | tee -a "$REPORT_FILE"
    fi
done
echo "" | tee -a "$REPORT_FILE"

echo "## 5️⃣ Documentation Structure..." | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Count files by directory
echo "### File Counts by Directory" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
find docs/ -name "*.md" -type f | wc -l | awk '{print "docs/: " $1 " files"}' | tee -a "$REPORT_FILE"
find docs/guides/ -name "*.md" -type f 2>/dev/null | wc -l | awk '{print "docs/guides/: " $1 " files"}' | tee -a "$REPORT_FILE"
find docs/archive/ -name "*.md" -type f 2>/dev/null | wc -l | awk '{print "docs/archive/: " $1 " files"}' | tee -a "$REPORT_FILE"
find src/ -name "*.md" -type f | wc -l | awk '{print "src/: " $1 " files"}' | tee -a "$REPORT_FILE"
echo '```' | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

echo "## 6️⃣ Critical Documents to Update..." | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Priority list
cat >> "$REPORT_FILE" << 'PRIORITY'
### HIGH PRIORITY (Update immediately)

1. ✅ README.md - **UPDATED NOV 1**
2. ✅ STATUS_REPORT_2025-10-30.md - **UPDATED NOV 1**
3. ✅ docs/TODO_MASTER_CONSOLIDATED.md - **UPDATED NOV 1**
4. ✅ docs/PENDING_HARDWARE_TESTS.md - **UPDATED NOV 1**
5. ⏳ docs/STATUS_REALITY_MATRIX.md - **NEEDS UPDATE**
6. ⏳ src/cotton_detection_ros2/README.md - **NEEDS UPDATE**
7. ⏳ src/motor_control_ros2/README.md - **NEEDS UPDATE**
8. ⏳ docs/PRODUCTION_READINESS_GAP.md - **NEEDS UPDATE**
9. ⏳ docs/HARDWARE_TEST_CHECKLIST.md - **NEEDS UPDATE**
10. ⏳ src/yanthra_move/README.md - **NEEDS UPDATE**

### MEDIUM PRIORITY (Update this week)

- docs/guides/*.md (15 files estimated)
- Package-specific documentation
- Status and progress reports

### LOW PRIORITY (Archive or update as needed)

- docs/archive/* (already archived, low priority)
- Historical reports (keep for reference)

PRIORITY

echo "## 📝 Recommendations..." | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

cat >> "$REPORT_FILE" << 'RECOMMENDATIONS'

### Immediate Actions

1. **Update Performance Metrics**
   - Replace "7-8 seconds" with "134ms average"
   - Replace "6 seconds" with "ROS2 CLI overhead (actual: 134ms)"
   - Add "Validated Nov 1, 2025" status

2. **Update Status Claims**
   - "Pending" → "Validated" (where applicable)
   - "Testing" → "Complete" (for Phase 0-1)
   - "TODO" → "Complete" (for finished items)

3. **Update Package READMEs**
   - Add Nov 1 validation results
   - Update performance sections
   - Add testing status

4. **Archive Old Reports**
   - Move pre-Oct-30 status reports to archive
   - Keep only latest active documents

### Batch Update Commands

```bash
# Replace old detection time references
find docs/ -name "*.md" -type f -exec sed -i 's/7-8 seconds/134ms average (Nov 1 validation)/g' {} +

# Update validation status
find docs/ -name "*.md" -type f -exec sed -i 's/Hardware validation pending/Hardware validated Oct 30, 2025/g' {} +

# Add current date to updated files
# (Do this manually for files you actually update)
```

### Manual Review Required

The following need careful manual review:
- Package READMEs (code examples, API references)
- Guides (step-by-step instructions)
- Status documents (specific metrics and claims)

---

**Audit Completed:** $(date)  
**Next Steps:** Review this report and update documents systematically

RECOMMENDATIONS

echo "" | tee -a "$REPORT_FILE"
echo "✅ Audit Complete! Report saved to: $REPORT_FILE"
echo ""
echo "📊 Summary:"
echo "- Total markdown files: $(find . -name "*.md" -type f | wc -l)"
echo "- Files in docs/: $(find docs/ -name "*.md" -type f 2>/dev/null | wc -l)"
echo "- Package READMEs: $(find src/ -name "README.md" -type f | wc -l)"
echo ""
echo "Next: Review $REPORT_FILE and proceed with updates"
