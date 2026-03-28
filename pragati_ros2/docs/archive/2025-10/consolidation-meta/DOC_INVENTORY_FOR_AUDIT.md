# Documentation Inventory for Audit

**Created:** 2025-10-07  
**Last Reviewed:** 2025-10-13 (automated snapshot)  
**Source:** COMPREHENSIVE_DOC_ANALYSIS_2025-10-07.md + `scripts/doc_inventory.py`  
**Purpose:** Categorized inventory for truth precedence scoring  
**Total Files:** 271 tracked documentation assets (all in `docs/` including archived materials)

> Snapshot generated with:
> ```bash
> python3 scripts/doc_inventory.py docs --snapshot docs/doc_inventory_snapshot.json --table
> ```

### Automated Snapshot — 2025-10-13

| Directory | Files | Size | Notes |
|-----------|-------|------|-------|
| `docs/` | 254 | ≈58.1 MB | Dominated by `*.zip` capture (50 MB) + 203 Markdown references |
| `docs/archive/2025-10-audit/` | 13 | ≈540 KB | Historical audit summaries + TODO inventories |

The authoritative JSON lives at `docs/doc_inventory_snapshot.json`. Use
`scripts/validation/doc_inventory_check.sh` to detect drift during CI or pre-merge reviews.

---

## Inventory Summary

| Category | Count | Size | Action | Priority |
|----------|-------|------|--------|----------|
| **Code Documentation** | 25 | ~400KB | Keep/Update | HIGH |
| **Generated Status** | 44 | ~800KB | Reduce to 8 | HIGH |
| **Archive (Superseded)** | 41 | ~500KB | **DELETE** | IMMEDIATE |
| **Duplicate/Redundant** | 30+ | ~600KB | Delete/Merge | HIGH |
| **Historical/Meta** | 25 | ~400KB | Archive | MEDIUM |
| **Essential Guides** | 20 | ~350KB | Keep | HIGH |
| **Test Reports** | 15 | ~250KB | Keep Latest | MEDIUM |
| **Analysis Reports** | 10 | ~300KB | Consolidate | MEDIUM |
| **Session/Temp Files** | 65+ | ~1.5MB | Delete | LOW |

**Reduction Target:** 275 files → 100-120 files (56% reduction)

---

## Category 1: Code Documentation (KEEP - Truth Level 1)

### Package READMEs (5 files) - **ESSENTIAL**
```
src/cotton_detection_ros2/README.md              # 8KB - Python/C++ camera package
src/motor_control_ros2/README.md                 # 12KB - Motor control (MG6010 primary)
src/robo_description/README.md                   # 4KB - URDF/visualization
src/vehicle_control/README.md                    # 16KB - Vehicle motion
src/yanthra_move/README.md                       # 10KB - Manipulator control
```

**Status:** Keep all, update with reality check  
**Truth Level:** Code-adjacent (documentation of current packages)  
**Action:** Verify against code in deep-dive tasks 7-11; scrub lingering references to removed legacy packages such as `dynamixel_msgs`

### Package Documentation Subdirs (19 files) - **REVIEW EACH**
```
src/*/docs/*.md                                  # Various implementation docs
src/*/CHANGELOG.md                               # Version histories
src/*/CONTRIBUTING.md                            # Contribution guides
```

**Status:** Keep relevant, archive historical  
**Action:** Review during module deep-dives

---

## Category 2: Generated Status Documents (CRITICAL REVIEW)

### docs/_generated/ (0 files as of 2025-10-13)

> **Status Update (Oct 2025):** The `_generated` directory was pruned during documentation cleanup; regenerate artifacts only if we reintroduce automated report pipelines. Keep this section as a placeholder for rebuilt outputs, but remove references to non-existent files in other docs.

5. **`COMPLETE_TESTING_SUMMARY.md`** (22KB) - **TEST SUMMARY**
   - **Truth Claim:** Comprehensive test results
   - **Priority:** Verify test claims
   - **Action:** Check test dates, re-run if old

6. **`HARDWARE_TEST_RESULTS.md`** (7KB) - **HARDWARE EVIDENCE**
   - **Truth Claim:** Hardware test outcomes
   - **Priority:** **CRITICAL** - Hardware truth level
   - **Action:** Extract hardware status for modules

7. **`SIMULATION_TEST_PROCEDURE.md`** (7KB) - **TEST PROCEDURES**
   - **Truth Claim:** Test methodology
   - **Priority:** Verify procedures still valid
   - **Action:** Update with current practices

8. **`cross_reference_matrix.csv`** (size TBD) - **FEATURE MATRIX**
   - **Truth Claim:** Feature cross-reference
   - **Priority:** **HIGH** - Use as anchor (task 6)
   - **Action:** Validate each entry

#### **DELETE (36 Files - Redundant/Superseded)**

```
docs/_generated/COMPREHENSIVE_ANALYSIS_REPORT.md       # 25KB - DUPLICATE of oakd_ros2_migration_analysis.md
docs/_generated/MASTER_OAKD_LITE_STATUS.md             # 23KB - Near-duplicate of master_status.md
docs/_generated/FINAL_PROJECT_COMPLETION_SUMMARY.md    # 21KB - Superseded
docs/_generated/SESSION_SUMMARY_*.md                   # 5 files - Temporal snapshots
docs/_generated/SESSION_REVIEW_FINAL.md                # 17KB - Old session notes
docs/_generated/doc_summaries.md                       # 29KB - Superseded by this inventory
docs/_generated/doc_cleanup_recommendations.md         # 16KB - Superseded
docs/_generated/todo_index_raw.txt                     # Raw data dump
docs/_generated/ros2_interfaces_raw.txt                # Raw data dump
docs/_generated/colcon_build.log                       # Build log (belongs in logs/)
docs/_generated/colcon_test.log                        # Test log (belongs in logs/)
docs/_generated/discrepancy_log.md                     # Merge into master_status.md
... (plus ~24 more session/temp files)
```

---

## Category 3: Archive Directory (Removed 2025-10-07)

### docs/_archive/2025-10-06/ (historical: 41 files, 500KB)

**Status:** ✅ Deleted during cleanup (`docs/archive/2025-10-21/scripts/cleanup_phase1.sh`) and confirmed absent as of 2025-10-13.  
**Rationale:** Superseded meta-documents replaced by the reconciliation plan and status matrix. Git history retains prior versions.

**Follow-up:**
- Ensure new archival material lives under `docs/archive/` (without the leading underscore) with clear dating.
- Remove stale references in generated reports that still cite `docs/_archive/2025-10-06/` (see Category 5 backlog).
- Keep `doc_inventory_snapshot.json` updated so re-introductions are caught by validation.

---

## Category 4: Root Directory Documents (MIXED)

### **KEEP & UPDATE (High Priority)**

1. **`README.md`** (15KB) - **MAIN PROJECT README**
   - **Truth Claim:** "100% COMPLETE", "PRODUCTION READY"
   - **🚩 Red Flag:** Conflicts with master_status.md
   - **Action:** Major update - remove false claims, add limitations
   - **Priority:** IMMEDIATE

2. **`CHANGELOG.md`** (45KB) - **VERSION HISTORY**
   - **Truth Claim:** "100% SUCCESS RATE" badge
   - **🚩 Red Flag:** Misleading badge
   - **Action:** Remove success badge, keep history
   - **Priority:** HIGH

3. **`RASPBERRY_PI_DEPLOYMENT_GUIDE.md`** (18KB) - **DEPLOYMENT GUIDE**
   - **Truth Claim:** Deployment procedures
   - **Action:** Verify steps still accurate
   - **Priority:** MEDIUM

4. **`BASELINE_VERSION.txt`** (82 bytes) - **VERSION MARKER**
   - **Action:** Keep as-is
   - **Priority:** LOW

### **EVALUATE**

5. **`BASELINE_SNAPSHOT.md`** (4KB)
   - Check if still relevant or superseded
   - May be historical only

6. **`HARDWARE_TEST_SUCCESS.md`** (1KB)
   - **Claims hardware success**
   - Verify against HARDWARE_TEST_RESULTS.md
   - Check if consistent

7. **`pragati_ros2_20250930_133927_complete_manifest.txt`** (171KB!)
   - Large manifest file from Sept 30
   - Likely auto-generated
   - Consider archiving or regenerating

### **DELETE/MERGE**

8. **`AUDIT_GAP_ANALYSIS.md`** (14KB)
   - Likely duplicated in newer analyses
   - Merge relevant content into master_status.md

9. **`DOCUMENTATION_AUDIT_EXEC_SUMMARY.md`** (8KB)
   - Meta-documentation about audit
   - Superseded by comprehensive analysis

10. **`DOCUMENTATION_AUDIT_WALKTHROUGH.md`** (19KB)
    - Detailed audit walkthrough
    - Superseded by comprehensive analysis

11. **`MIGRATION_COMPLETE_SUMMARY.md`** (21KB)
    - Completion claim
    - Superseded by master_status.md

---

## Category 5: Guides & Documentation (KEEP)

### docs/guides/ (12 files) - **ESSENTIAL OPERATIONAL DOCS**

```
docs/guides/COTTON_DETECTION_MIGRATION_GUIDE.md      # Migration guide
docs/guides/CAMERA_INTEGRATION_GUIDE.md              # Camera setup
docs/guides/USB2_CONFIGURATION_GUIDE.md              # USB2 setup (important!)
docs/guides/YOLO_MODELS.md                           # Model documentation
docs/guides/ROS2_INTERFACE_SPECIFICATION.md          # Interface specs
... (plus 7 more guides)
```

**Status:** KEEP - Essential how-to documentation  
**Action:** Verify accuracy during module deep-dives  
**Priority:** HIGH - Update outdated sections

**Known Issues:**
- `ROS2_INTERFACE_SPECIFICATION.md` now documents C++ node as canonical and notes calibration export gap (wrapper only)
- `YOLO_MODELS.md` may list models not present in repo
- USB2 guide not linked from main README

---

## Category 6: Analysis & Reports

### docs/analysis/ (17 files) - **TECHNICAL COMPARISONS**

```
docs/analysis/ros1_vs_ros2_comparison/*.md           # ROS1 vs ROS2 analysis
```

**Status:** KEEP - Valuable technical reference  
**Action:** Consider consolidating into single doc  
**Priority:** LOW

### docs/reports/ (Various) - **PROJECT REPORTS**

```
docs/reports/oakd_ros2_migration_analysis.md         # 25KB - Keep (delete duplicate)
docs/reports/*.md                                     # Other reports
```

**Status:** Review and consolidate  
**Action:** Keep unique analyses, archive duplicates  
**Priority:** MEDIUM

---

## Category 7: Test Documentation

### docs/validation/ (4 files)

```
docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md
docs/validation/*.md
```

**Status:** Update or archive  
**Action:** Check if superseded by newer test results  
**Priority:** MEDIUM - Compare with task 12 findings

---

## Category 8: Integration & Artifacts

### docs/integration/ (3 files) - **MERGE INTO MAIN**

```
docs/integration/*.md
```

**Status:** Small directory, merge into main docs  
**Action:** Review and consolidate  
**Priority:** LOW

### docs/artifacts/ (13 files) - **PARAMETER REFERENCES**

```
docs/artifacts/*.yaml
docs/artifacts/*.md
```

**Status:** KEEP - Configuration artifacts  
**Action:** Verify files still referenced  
**Priority:** MEDIUM

---

## Category 9: Web Dashboard (ENHANCE)

### web_dashboard/ + historical docs

**Status:** ACTIVE - Feature slated for enhancements  
**Code Reality:** Web dashboard implementation lives in the top-level `web_dashboard/` directory; historical notes were archived in October 2025 (`docs/archive/2025-10-reports/*`).  
**Action:** Align docs with `docs/enhancements/WEB_DASHBOARD_ENHANCEMENT_PLAN.md`, capture enhancement requirements, and migrate useful history into refreshed docs rather than deleting  
**Priority:** HIGH - Bring docs in line with the active roadmap

---

## Category 10: Log Files (CLEANUP SEPARATELY)

### logs/ (3,403 files, 13MB)

**Status:** Needs separate cleanup  
**Action:** Delete logs older than 7-14 days  
**Priority:** LOW - Doesn't affect documentation audit  
**Script:** Use cleanup_phase2.sh from comprehensive analysis

---

## Audit Priority Matrix

### **IMMEDIATE (Today)**
1. ✅ Review this inventory
2. ⬜ Delete archive: `rm -rf docs/_archive/2025-10-06/`
3. ⬜ Delete exact duplicates (COMPREHENSIVE_ANALYSIS_REPORT.md)
4. ⬜ Replace deprecated messaging with enhancement plan for the web dashboard (docs + backlogs)

### **HIGH (This Week) - Tasks 4-6**
1. ⬜ Extract status claims from 8 essential generated docs
2. ⬜ Update README.md - remove false claims
3. ⬜ Update master_status.md with gaps
4. ⬜ Cross-check with cross_reference_matrix.csv
5. ✅ Verify ROS2_INTERFACE_SPECIFICATION.md accuracy (updated 2025-10-13)

### **MEDIUM (Next Week) - Tasks 7-12**
1. ⬜ Deep-dive module verification (cotton_detection, yanthra_move, etc.)
2. ⬜ Re-run all tests, update test documentation
3. ⬜ Verify hardware test claims
4. ⬜ Update package READMEs

### **LOW (Ongoing)**
1. ⬜ Consolidate analysis docs
2. ⬜ Clean up logs
3. ⬜ Archive historical reports

---

## Key Red Flags Found

🚩 **Critical Issues:**
1. README claims "100% COMPLETE" - conflicts with master_status
2. Calibration service declared but handler MISSING (crash risk)
3. Archive never deleted (41 files, 500KB)
4. Multiple "FINAL" docs with conflicting claims
5. Test badges outdated (Sept 25)

🚩 **Documentation Gaps:**
1. Topic-based cotton detection integration not documented
2. USB2 requirement not explained in main README
3. Simulation mode not documented
4. Known limitations section missing

🚩 **Orphaned Documentation:**
1. Web dashboard docs lack an up-to-date enhancement roadmap (code exists)
2. Multiple YOLO models documented (only one exists)
3. ROS1 service documentation (removed)

---

## Usage in Audit Tasks

### Task 4: Extract Status Claims
- Focus on 8 essential generated docs
- Extract all completion percentages
- Note conflicts between docs

### Task 5: Cross-Check Primary vs Generated
- Compare README vs master_status.md
- Identify contradictions
- Apply truth precedence (code > tests > hardware > docs)

### Task 6: Leverage Cross-Reference Matrix
- Use as authoritative feature list
- Verify each entry against code
- Score each feature with rubric

### Tasks 7-11: Module Deep-Dives
- Use package READMEs as starting point
- Verify against actual code
- Update READMEs with findings

### Task 12: Test Status Verification
- Re-run tests from test documentation
- Update test summaries
- Verify hardware claims

---

## Next Steps

1. ✅ Review this inventory (Task 3 complete)
2. ⬜ Proceed to Task 4: Extract status claims from docs
3. ⬜ Use truth precedence rubric for scoring
4. ⬜ Begin module deep-dives with this inventory as guide

---

**Inventory Complete:** 2025-10-07  
**Files Categorized:** 275  
**Reduction Target:** 155 files (56%)  
**Next Task:** Extract and normalize status claims (Task 4)
