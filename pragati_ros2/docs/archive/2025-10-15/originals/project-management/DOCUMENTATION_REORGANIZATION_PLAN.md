# Documentation Reorganization Plan

**Date**: 2025-10-09  
**Current State**: 209 markdown files scattered across multiple locations  
**Goal**: Clean, organized, findable documentation structure

---

## Current Issues

### Problems Identified
1. **209 markdown files** - Too many, high duplication
2. **Scattered locations** - Root, docs/, docs/subfolder, module-specific
3. **Inconsistent naming** - Multiple files with similar names
4. **Duplicate information** - Same info in multiple places
5. **Outdated content** - References to ODrive, old cotton detection, pending tasks
6. **No clear hierarchy** - Hard to find anything

### Current Structure (Scattered)
```
pragati_ros2/
├── README.md (main)
├── *.md (root level - various status/review docs)
├── docs/
│   ├── README.md
│   ├── *.md (many analysis, plan, guide files)
│   ├── guides/
│   ├── analysis/
│   ├── reports/
│   ├── audit/
│   ├── archive/
│   ├── integration/
│   ├── mg6010/
│   └── cotton_detection_ros2/
├── src/motor_control_ros2/
│   └── docs/ (NEW - just created)
└── src/<package>/
    └── README.md (per-package)
```

---

## Recommendation: Commit First ✅

**Why**: You have uncommitted changes (modified files + new files)

**What to Commit**:
```bash
# Modified files:
- README.md (main)
- src/motor_control_ros2/src/mg6010_controller.cpp

# New files:
- CODE_DOC_MISMATCH_REPORT.md
- MOTOR_CONTROL_COMPREHENSIVE_REVIEW.md
- docs/MG6010_README_UPDATES.md
- src/motor_control_ros2/config/mg6010_test.yaml
- src/motor_control_ros2/docs/* (all new docs)
- src/motor_control_ros2/launch/mg6010_test.launch.py
```

**Commit Command**:
```bash
git add .
git commit -m "docs: Complete MG6010 documentation review and analysis

- Add MG6010 traceability table and gap analysis
- Add documentation consolidation plan
- Fix MG6010 controller bitrate configuration
- Add MG6010 test launch file and configuration
- Add comprehensive documentation review deliverables

Ref: Documentation-first review phase complete (14/14 tasks)"
```

---

## Proposed New Structure

### Clean, Hierarchical Organization

```
pragati_ros2/
├── README.md                              # Main project README (MG6010-first)
│
├── docs/                                  # Project-wide documentation
│   ├── README.md                          # Documentation index
│   │
│   ├── getting-started/                   # New users start here
│   │   ├── QUICK_START.md
│   │   ├── INSTALLATION.md
│   │   └── FIRST_TEST.md
│   │
│   ├── guides/                            # How-to guides
│   │   ├── hardware/
│   │   │   ├── CAN_BUS_SETUP.md
│   │   │   ├── GPIO_SETUP.md
│   │   │   └── RASPBERRY_PI_DEPLOYMENT.md
│   │   ├── software/
│   │   │   ├── BUILD_OPTIMIZATION.md
│   │   │   └── TESTING_GUIDE.md
│   │   └── integration/
│   │       └── COTTON_DETECTION_INTEGRATION.md
│   │
│   ├── reference/                         # Reference documentation
│   │   ├── SERVICES_API.md               # All ROS services
│   │   ├── TOPICS_API.md                 # All ROS topics
│   │   ├── PARAMETERS.md                 # All parameters
│   │   └── ERROR_CODES.md                # All error codes
│   │
│   ├── architecture/                      # System design
│   │   ├── OVERVIEW.md
│   │   ├── MOTOR_ABSTRACTION.md
│   │   └── SAFETY_MONITOR.md
│   │
│   ├── project-management/                # Project tracking
│   │   ├── STATUS.md                     # Current status
│   │   ├── ROADMAP.md                    # Future plans
│   │   └── CHANGELOG.md                  # Version history
│   │
│   └── archive/                           # Old/historical docs
│       └── 2025-10/                      # Date-based archival
│           └── old-analyses/
│
├── src/motor_control_ros2/                # Motor control package
│   ├── README.md                          # Package overview
│   └── docs/
│       ├── MG6010_GUIDE.md               # MG6010 setup
│       ├── MG6010_CALIBRATION.md         # MG6010 calibration
│       ├── MG6010_ERROR_CODES.md         # MG6010 errors
│       ├── ODRIVE_LEGACY.md              # ODrive (legacy)
│       ├── MOTOR_ABSTRACTION_API.md      # Developer API
│       ├── TRACEABILITY_TABLE.md         # Code-doc mapping
│       ├── GAPS_ANALYSIS.md              # Known issues
│       └── CONSOLIDATION_PLAN.md         # Improvement plan
│
├── src/yanthra_move/
│   └── README.md                          # Arm control
│
├── src/vehicle_control/
│   └── README.md                          # Vehicle control
│
├── src/cotton_detection_ros2/
│   └── docs/
│       ├── README.md                      # Detection overview
│       ├── OAK_D_LITE_GUIDE.md           # Camera setup
│       └── PHASE1_WRAPPER.md             # Python wrapper
│
└── src/pattern_finder/
    └── README.md                          # ArUco markers
```

---

## File Categorization

### Keep in Root (Minimal)
- `README.md` - Main project README
- `LICENSE` - License file
- `CONTRIBUTING.md` - How to contribute
- `CHANGELOG.md` - Version history

### Move to docs/ (Project-wide)
All project-level documentation organized by category.

### Move to src/<package>/docs/ (Package-specific)
Technical details specific to each package.

### Archive (Historical)
Old analyses, completed plans, outdated guides.

---

## Reorganization Steps

### Step 1: Commit Current State ✅
```bash
git add .
git commit -m "docs: Complete MG6010 documentation review"
```

### Step 2: Create New Directory Structure
```bash
mkdir -p docs/{getting-started,guides/{hardware,software,integration},reference,architecture,project-management,archive/2025-10}
```

### Step 3: Audit and Categorize Files
For each of 209 markdown files:
1. Read file to understand content
2. Check if outdated (ODrive-only, completed tasks, old dates)
3. Check for duplicates
4. Categorize: Keep, Update, Merge, Archive, Delete

### Step 4: Move and Consolidate
- Move files to new structure
- Merge duplicate content
- Update internal links
- Update references

### Step 5: Update Content
- Fix ODrive references (make generic or MG6010-first)
- Remove completed task lists
- Update outdated information
- Verify code references

### Step 6: Create Documentation Index
Central `docs/README.md` with:
- Purpose of each category
- How to find information
- Quick links to common tasks

### Step 7: Commit Reorganization
```bash
git add .
git commit -m "docs: Reorganize documentation structure

- Create hierarchical directory structure
- Consolidate duplicate content
- Archive outdated documents
- Update internal links
- Fix ODrive/old references

BREAKING: Documentation paths have changed"
```

---

## File Audit Plan

### Priority 1: Root Level Cleanup (Immediate)

**Current Root Files**:
```
CODE_DOC_MISMATCH_REPORT.md
MOTOR_CONTROL_COMPREHENSIVE_REVIEW.md
```

**Action**:
- Move to `src/motor_control_ros2/docs/` (motor control specific)

### Priority 2: docs/ Main Folder (High)

**Categories to Review**:
1. **Guides** (keep, consolidate, update)
   - BUILD_OPTIMIZATION_GUIDE.md → docs/guides/software/
   - CAN_BUS_SETUP_GUIDE.md → docs/guides/hardware/
   - etc.

2. **Analysis** (archive most, keep recent)
   - COTTON_DETECTION_DEEP_DIVE.md → keep
   - OLD analyses → archive

3. **Plans** (archive completed, keep active)
   - IMPLEMENTATION_PLAN_OCT2025.md → keep or archive if done
   - EXECUTION_PLAN_2025-09-30.md → archive (old date)

4. **Status/Review** (consolidate into STATUS.md)
   - Multiple status files → merge into docs/project-management/STATUS.md

### Priority 3: docs/subfolder (Medium)

**Subfolders to Review**:
- `guides/` - Keep structure, update content
- `analysis/` - Archive old, keep recent
- `reports/` - Archive old
- `audit/` - Archive if complete
- `archive/` - Already archived, review for deletion
- `mg6010/` - Move to src/motor_control_ros2/docs/
- `integration/` - Keep but consolidate

### Priority 4: Package-Specific (Medium)

**src/motor_control_ros2/docs/** (NEW):
- Already well-organized
- Just created, keep as-is

**src/cotton_detection_ros2/docs/**:
- Consolidate if multiple files
- Update ODrive references

---

## Content Update Plan

### Issue 1: ODrive References
**Problem**: Many docs still ODrive-centric

**Files to Update**:
```bash
# Find all ODrive references
grep -r "ODrive" docs/ --include="*.md" | wc -l
```

**Update Strategy**:
1. Generic motor control docs → Make generic, mention both ODrive and MG6010
2. Setup guides → MG6010-first, ODrive as alternative
3. Legacy-specific → Move to ODRIVE_LEGACY.md

### Issue 2: Old Cotton Detection References
**Problem**: References to old ROS1 code, old architectures

**Files to Check**:
- docs/integration/*
- docs/cotton_detection_ros2/*
- Any file mentioning "detect_cotton_srv" (removed service)

**Update Strategy**:
1. Update to Phase 1 Python wrapper architecture
2. Remove ROS1 references
3. Update topic names (/cotton_detection/results)

### Issue 3: Completed Tasks
**Problem**: Many files have old task lists, pending items

**Pattern to Find**:
```bash
# Find task lists
grep -r "\[ \]" docs/ --include="*.md" | head -20
grep -r "TODO" docs/ --include="*.md" | head -20
grep -r "PENDING" docs/ --include="*.md" | head -20
```

**Update Strategy**:
1. Mark completed tasks as done [x]
2. Move active tasks to docs/project-management/ROADMAP.md
3. Archive docs with only completed tasks

### Issue 4: Duplicate Information
**Problem**: Same info in multiple files

**Common Duplicates**:
- CAN setup instructions (multiple places)
- Build instructions (multiple places)
- ROS2 installation (multiple places)

**Consolidation Strategy**:
1. Choose canonical location for each topic
2. Replace duplicates with links
3. Keep only essential duplicates (e.g., quick start in main README)

---

## Automated Audit Script

### Create Audit Tool
```bash
#!/bin/bash
# docs/archive/2025-10-21/scripts/audit_docs.sh

echo "Documentation Audit Report"
echo "=========================="
echo ""

echo "Total Markdown Files:"
find . -name "*.md" | wc -l

echo ""
echo "Files by Location:"
echo "  Root:"
find . -maxdepth 1 -name "*.md" | wc -l
echo "  docs/:"
find docs/ -name "*.md" 2>/dev/null | wc -l
echo "  src/:"
find src/ -name "*.md" 2>/dev/null | wc -l

echo ""
echo "ODrive References:"
grep -r "ODrive" --include="*.md" . 2>/dev/null | wc -l

echo ""
echo "Old Cotton Detection References:"
grep -r "detect_cotton_srv" --include="*.md" . 2>/dev/null | wc -l

echo ""
echo "Task Lists (Pending):"
grep -r "^\s*- \[ \]" --include="*.md" . 2>/dev/null | wc -l

echo ""
echo "TODO/PENDING markers:"
grep -r "TODO\|PENDING" --include="*.md" . 2>/dev/null | wc -l

echo ""
echo "Old Dates (2024 or earlier):"
grep -r "2024\|2023\|2022" --include="*.md" . 2>/dev/null | wc -l

echo ""
echo "Files over 500 lines:"
find . -name "*.md" -exec wc -l {} \; | awk '$1 > 500 {print}' | wc -l
```

---

## Implementation Timeline

### Day 1: Preparation
- [x] ✅ Commit current changes
- [ ] Run audit script
- [ ] Review top 20 largest files
- [ ] Identify critical duplicates

### Day 2-3: Structure Creation
- [ ] Create new directory structure
- [ ] Move motor_control_ros2 docs (already organized)
- [ ] Move guides to docs/guides/
- [ ] Create documentation index

### Day 4-5: Content Consolidation
- [ ] Merge duplicate setup guides
- [ ] Consolidate status reports
- [ ] Archive old analyses
- [ ] Update ODrive references

### Day 6-7: Validation & Polish
- [ ] Update all internal links
- [ ] Verify code references
- [ ] Test documentation paths
- [ ] Update main README

### Day 8: Final Commit
- [ ] Review changes
- [ ] Commit reorganization
- [ ] Create migration guide for documentation users

---

## Risk Mitigation

### Backup Strategy
1. **Git Commit First** ✅ - Can always revert
2. **Keep Archive Folder** - Don't delete, archive
3. **Document Moves** - Track what went where
4. **Incremental Commits** - Commit each major step

### Link Update Strategy
1. **Find All Links**: `grep -r "\[.*\](.*.md)" docs/`
2. **Update Incrementally**: Fix links as files move
3. **Use Relative Paths**: `../reference/PARAMETERS.md`
4. **Test Links**: Create link checker script

### Rollback Plan
If reorganization causes issues:
```bash
# Revert to pre-reorganization state
git log --oneline | head -5  # Find commit before reorganization
git revert <commit-hash>     # Or:
git reset --hard <commit-hash>
```

---

## Success Criteria

### Before
- 209 markdown files scattered everywhere
- Hard to find information
- Duplicate content
- Outdated references
- No clear hierarchy

### After
- ~50-80 well-organized markdown files
- Clear hierarchy (getting-started → guides → reference)
- One canonical location for each topic
- Updated content (MG6010-first, Phase 1 cotton detection)
- Easy to find information
- Links all work
- Archive preserves history

### Metrics
- **File reduction**: 209 → ~60 files (70% reduction via consolidation)
- **Time to find info**: <2 minutes for common tasks
- **Link validity**: 100% working links
- **Content freshness**: All dates 2025, current architecture
- **Duplication**: <5% duplicate content (only essential)

---

## Next Steps

1. **Immediate**: Commit current changes
2. **Review**: Run audit script, review results
3. **Plan**: Detailed file-by-file categorization
4. **Execute**: Follow 8-day timeline
5. **Validate**: Test documentation, fix links
6. **Deploy**: Final commit and documentation update

---

## Questions for You

1. **Commit Now?** 
   - Recommended: YES ✅
   - This preserves current state before reorganization

2. **Archive vs Delete?**
   - Recommended: Archive old docs to `docs/archive/2025-10/`
   - Don't delete (can review later if needed)

3. **Update Content During Move?**
   - Recommended: YES
   - Fix ODrive references, outdated info as we move files

4. **Timeline?**
   - Aggressive: 2-3 days (focus on critical paths)
   - Thorough: 7-8 days (review every file)
   - Which do you prefer?

---

**Ready to Proceed?**

Recommended first command:
```bash
git add .
git commit -m "docs: Complete MG6010 documentation review and analysis"
```

Then I'll create the audit script and we can start the reorganization!
