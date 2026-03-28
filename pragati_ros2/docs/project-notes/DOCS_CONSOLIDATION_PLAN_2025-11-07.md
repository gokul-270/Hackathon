# Documentation Consolidation Plan - 2025-11-07

**Goal:** Reduce documentation clutter, establish single source of truth, improve navigation

**Status:** Ready for execution  
**Estimated Time:** 2-3 hours  
**Approach:** Reuse existing structure, archive dated content, promote evergreen guides

---

## Problem Summary

**Current State:**
- 55 markdown files at repository root (way too many)
- Overlapping status docs (PRODUCTION_READY_STATUS.md, STATUS_REPORT_2025-10-30.md, etc.)
- Dated session notes mixed with evergreen content
- Hard to find "what's the current status?"
- 35,339+ lines in docs/archive/ already

**Desired State:**
- 10-15 files maximum at root (evergreen only)
- Single source of truth: **CURRENT_STATUS.md**
- Dated content in docs/archive/2025-11-sessions/
- Technical guides in docs/guides/
- Clear navigation from docs/INDEX.md

---

## Consolidation Strategy

### Root Level (Keep Only These)
```
pragati_ros2/
├── README.md                    ✅ Keep - Project overview
├── CHANGELOG.md                 ✅ Keep - Version history
├── CONTRIBUTING.md              ✅ Keep - Contribution guide
├── CURRENT_STATUS.md            ✨ NEW - Single source of truth
├── TESTING_CHECKLIST.md         ✅ Keep - Quick reference
└── [2-3 other critical docs]    ✅ Keep if truly evergreen
```

### Move to docs/guides/ (Evergreen Technical Content)
- ARUCO_OPTIMIZATION.md
- QOS_OPTIMIZATION.md
- POSITION_FEEDBACK_DESIGN.md
- ENHANCED_LOGGING_GUIDE.md
- FIX_PLAN_JOINT_CONVERSIONS.md

### Archive to docs/archive/2025-11-sessions/ (Dated Content)
- ANSWERS_AND_IMPROVEMENTS_2025-11-06.md
- HARDWARE_TEST_CHECKLIST_2025-11-07.md
- JOINT5_URDF_ANALYSIS.md
- LAUNCH_STATUS.md
- PHASE1_DEPLOYED_2025-11-06.md
- README_2025-11-06_MOTOR_FIX.md
- SESSION_COMPLETE_2025-11-05.md
- SESSION_SUMMARY.md
- SYSTEM_VALIDATION_SUMMARY_2025-11-01.md
- TEST_READY_SUMMARY.md

### Archive to docs/archive/2025-10/ (October Reports)
- PRODUCTION_READY_STATUS.md
- STATUS_REPORT_2025-10-30.md

---

## New File: CURRENT_STATUS.md

**Purpose:** Single source of truth for "What's happening now?"

**Contents:**
1. System status (Production readiness, deployment, hardware, codebase)
2. Latest changes (last 5-7 with dates and impact)
3. Next steps (top 3-5 prioritized actions)
4. Quick links (to guides, testing checklist, archives)

**Sources:**
- PRODUCTION_READY_STATUS.md (Oct 30 validation)
- PHASE1_DEPLOYED_2025-11-06.md (motor fix)
- HARDWARE_TEST_CHECKLIST_2025-11-07.md (today's checklist)
- SESSION_COMPLETE_2025-11-05.md (refactoring summary)

**Maintenance:**
- Update when changes land (link from policy)
- Keep concise and high-signal
- Archive when creating new month's status

---

## Implementation Steps

### 1. Setup (5 min)
```bash
# Create working branch
git checkout -b docs/consolidation-2025-11

# Inventory current state
ls -1 *.md | wc -l  # Should show 55
```

### 2. Prepare destinations (2 min)
```bash
# Reuse existing archive structure
test -d docs/archive/2025-11-sessions || mkdir -p docs/archive/2025-11-sessions
mkdir -p docs/archive/2025-11-consolidation
```

### 3. Move evergreen guides (3 min)
```bash
git mv ARUCO_OPTIMIZATION.md docs/guides/
git mv QOS_OPTIMIZATION.md docs/guides/
git mv POSITION_FEEDBACK_DESIGN.md docs/guides/
git mv ENHANCED_LOGGING_GUIDE.md docs/guides/
git mv FIX_PLAN_JOINT_CONVERSIONS.md docs/guides/
```

### 4. Archive dated sessions (5 min)
```bash
# Move to 2025-11-sessions
git mv ANSWERS_AND_IMPROVEMENTS_2025-11-06.md docs/archive/2025-11-sessions/
git mv HARDWARE_TEST_CHECKLIST_2025-11-07.md docs/archive/2025-11-sessions/
git mv JOINT5_URDF_ANALYSIS.md docs/archive/2025-11-sessions/
git mv LAUNCH_STATUS.md docs/archive/2025-11-sessions/
git mv PHASE1_DEPLOYED_2025-11-06.md docs/archive/2025-11-sessions/
git mv README_2025-11-06_MOTOR_FIX.md docs/archive/2025-11-sessions/
git mv SESSION_COMPLETE_2025-11-05.md docs/archive/2025-11-sessions/
git mv SESSION_SUMMARY.md docs/archive/2025-11-sessions/
git mv SYSTEM_VALIDATION_SUMMARY_2025-11-01.md docs/archive/2025-11-sessions/
git mv TEST_READY_SUMMARY.md docs/archive/2025-11-sessions/

# Move to 2025-10 (reuse existing folder)
git mv STATUS_REPORT_2025-10-30.md docs/archive/2025-10/
git mv PRODUCTION_READY_STATUS.md docs/archive/2025-10/
```

### 5. Create CURRENT_STATUS.md (30 min)
Create new file at root with consolidated info from all archived status files.

### 6. Update docs/INDEX.md and docs/START_HERE.md (15 min)
- Add prominent link to CURRENT_STATUS.md
- Update all links to moved files
- Keep navigation simple and clear

### 7. Document consolidation (10 min)
Create docs/archive/2025-11-consolidation/README.md with mapping of what moved where.

### 8. Update references (20 min)
```bash
# Find all references to moved files
grep -RIn "ARUCO_OPTIMIZATION.md\|QOS_OPTIMIZATION.md" .

# Update each reference to new path
```

### 9. Quality checks (10 min)
- Open README.md, CURRENT_STATUS.md, docs/INDEX.md
- Click through all links
- Verify root has ~10-15 files

### 10. Commit and push (5 min)
```bash
git add -A
git commit -m "docs: consolidate and archive dated files; add CURRENT_STATUS.md"
git push -u origin docs/consolidation-2025-11
```

---

## Before/After Comparison

### Root Directory Files
**Before:** 55 files (many dated/overlapping)  
**After:** ~10-15 files (evergreen only + CURRENT_STATUS.md)

### Finding Current Status
**Before:** Check 5+ files (PRODUCTION_READY_STATUS.md, STATUS_REPORT_2025-10-30.md, PHASE1_DEPLOYED_2025-11-06.md, etc.)  
**After:** Check 1 file (CURRENT_STATUS.md)

### Finding Guides
**Before:** Mixed at root level  
**After:** Organized in docs/guides/

### Historical Information
**Before:** Mixed with current info at root  
**After:** Organized by month in docs/archive/

---

## Success Criteria

- [ ] Root directory has 10-15 files maximum
- [ ] CURRENT_STATUS.md exists and is comprehensive
- [ ] All dated files archived to appropriate month folders
- [ ] All evergreen guides moved to docs/guides/
- [ ] docs/INDEX.md and docs/START_HERE.md updated
- [ ] All links working (no broken references)
- [ ] Consolidation documented in docs/archive/2025-11-consolidation/
- [ ] Maintenance policy updated

---

## Rollback Plan

If something goes wrong:
```bash
# Discard all changes and return to main
git checkout main
git branch -D docs/consolidation-2025-11
```

All content preserved in Git history; nothing is deleted.

---

## Maintenance Policy (Going Forward)

1. **Keep root clean:** Only evergreen files + CURRENT_STATUS.md
2. **Update CURRENT_STATUS.md:** When changes land (not new files)
3. **Archive monthly:** Move dated notes to docs/archive/YYYY-MM-*/
4. **Guides location:** Put reusable technical content in docs/guides/
5. **Reuse structure:** Use existing folders; avoid creating new ones

---

## Next Actions

**Option A - Execute Now:**
I can execute this entire plan for you (2-3 hours)

**Option B - Review First:**
You review this plan, suggest changes, then I execute

**Option C - Manual Execution:**
You execute manually following this plan as a checklist

Which would you prefer?
