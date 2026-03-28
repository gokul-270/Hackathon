# Documentation Consolidation Map

**Date:** 2025-10-15  
**Purpose:** File-by-file action plan for documentation consolidation  
**Policy:** No content loss - all content preserved via merge or archive

---

## Overview

| Area | Files Current | Files After | Action |
|------|---------------|-------------|--------|
| **Cotton Detection** | 3 | 2 | Merge 1, keep 2 |
| **Motor Control** | 20 | 1 | Merge 19 → 1 README |
| **Yanthra Move** | 4 | 2 | Archive 2 meta docs |
| **Root Docs** | 150+ | Organized | Archive historical, create tracker |

---

## Cotton Detection Package

### Current Files
```
src/cotton_detection_ros2/
├── README.md (118 lines)
├── MIGRATION_GUIDE.md (613 lines)
└── OFFLINE_TESTING.md (386 lines)
```

### Actions

#### 1. README.md → **UPDATE**
**Action:** Merge content from MIGRATION_GUIDE.md

**Additions:**
- Add "Migration from Python Wrapper" section
- Preserve all migration examples and caveats
- Add link to OFFLINE_TESTING.md
- Update status header:
  ```
  Last Updated: 2025-10-15
  Status: Beta - Pending Hardware Validation
  Validation: Sim [yes], Bench [pending], Field [pending]
  Hardware: OAK-D Lite camera required
  ```

**Estimate:** 2-3h merge + review

#### 2. MIGRATION_GUIDE.md → **ARCHIVE**
**Action:** Move to `docs/archive/2025-10/cotton_detection/`

**Rationale:** Migration phase complete; content merged into README

**Log Entry:**
```
[2025-10-15] ARCHIVE src/cotton_detection_ros2/MIGRATION_GUIDE.md
  → docs/archive/2025-10/cotton_detection/MIGRATION_GUIDE.md
  Content: Fully merged into README.md "Migration" section
  Reason: Migration from wrapper complete; historical reference only
```

#### 3. OFFLINE_TESTING.md → **KEEP**
**Action:** Keep as standalone; ensure linked from README

**Rationale:** Valuable standalone guide; frequently referenced

**Checklist:**
- [ ] Add prominent link in README
- [ ] Add to docs/INDEX.md
- [ ] Verify all paths still valid

---

## Motor Control Package

### Current Files
```
src/motor_control_ros2/
├── README.md (110 lines)
├── MOTOR_CONTROL_STATUS.md (473 lines) ❌ Merge
├── README_GENERIC_MOTORS.md (278 lines) ❌ Merge
├── SERVICES_NODES_GUIDE.md (332 lines) ❌ Merge
├── SAFETY_MONITOR_IMPLEMENTATION_COMPLETE.md (328 lines) ❌ Move to evidence
└── docs/
    ├── CODE_DOC_MISMATCH_REPORT.md ❌ Archive
    ├── DOCUMENTATION_CONSOLIDATION_PLAN.md ❌ Archive (meta)
    ├── DOCUMENTATION_GAPS_ANALYSIS.md ❌ Archive (meta)
    ├── DOCUMENTATION_REVIEW_COMPLETE.md ❌ Archive (meta)
    ├── MG6010_INDEX.md ❌ Merge
    ├── MG6010_MG6010_INTEGRATION_COMPLETE.md ❌ Archive (completion doc)
    ├── MG6010_MG6010_INTEGRATION_PLAN.md ❌ Archive (plan)
    ├── MG6010_MG6010_STATUS.md ❌ Merge
    ├── MG6010_PROTOCOL_COMPARISON.md ❌ Merge
    ├── MG6010_README.md ❌ Merge
    ├── MG6010_README_UPDATES.md ❌ Archive (meta)
    ├── MOTOR_COMM_ANALYSIS.md ❌ Archive
    ├── MOTOR_COMM_FIX_INSTRUCTIONS.md ❌ Archive
    ├── MOTOR_CONTROL_COMPREHENSIVE_REVIEW.md ❌ Archive
    └── TRACEABILITY_TABLE.md → Keep or merge (decide)
```

### Actions

#### 1. README.md → **MASSIVE UPDATE** (New Authoritative Source)

**Target Structure:**
```markdown
# Motor Control ROS2 (Authoritative)

**Last Updated:** 2025-10-15
**Status:** Beta - Pending Hardware Validation  
**Validation:** Sim [yes], Bench [pending], Field [pending]  
**Hardware:** MG6010 motors, CAN interface @250kbps, GPIO for safety

## Table of Contents
1. Overview & Status
2. Hardware Compatibility
3. MG6010 Primary Controller
4. Safety Monitor
5. Services, Topics, Parameters
6. Configuration
7. Testing & Validation
8. Troubleshooting
9. Legacy ODrive Support
10. References

## 1. Overview & Status
[From MOTOR_CONTROL_STATUS.md - executive summary]
- Current implementation status
- Build status
- Validation status
- Known limitations
- Next steps

## 2. Hardware Compatibility
[From README_GENERIC_MOTORS.md - hardware section]
- MG6010 specifications
- CAN bus requirements (250kbps)
- Power requirements (48V nominal, 44-52V range)
- GPIO requirements
- Wiring diagrams

## 3. MG6010 Primary Controller
[From all MG6010_*.md files]
- Protocol overview (LK-TECH CAN Protocol V2.35)
- Motor specifications (MG6010E-i6)
- Configuration parameters
- Command set
- Protocol comparison (vs ODrive)
- Integration status

## 4. Safety Monitor
[Summary from SAFETY_MONITOR_IMPLEMENTATION_COMPLETE.md]
- Implementation status: ✅ Complete
- Safety checks implemented (6):
  1. Joint position limits
  2. Velocity limits
  3. Temperature monitoring
  4. Communication timeouts
  5. Motor error status
  6. Power supply voltage
- Hardware TODOs (from code):
  - GPIO ESTOP implementation
  - Emergency LED signaling
  - CAN ESTOP command
- Testing status
- [Link to full implementation doc in evidence/]

## 5. Services, Topics, Parameters
[From SERVICES_NODES_GUIDE.md]
- Nodes:
  - mg6010_integrated_test_node
  - odrive_service_node (legacy)
- Services:
  - /mg6010/motor_status
  - /mg6010/motor_enable
  - /mg6010/motor_disable
  - /mg6010/motor_homing
- Topics:
  - /joint_states
- Parameters (full reference)

## 6. Configuration
[From MG6010_README.md + SERVICES_NODES_GUIDE.md]
- Primary config: config/mg6010_test.yaml
- Production config: config/production.yaml
- Launch files
- Parameter descriptions
- Example configurations

## 7. Testing & Validation
[From MOTOR_CONTROL_STATUS.md]
- Build testing: ✅ Complete
- Unit testing: ⏳ Pending
- Hardware testing: ⏳ Awaiting MG6010 hardware
- Test procedures
- Hardware test checklist

## 8. Troubleshooting
[From various docs]
- Common issues
- CAN interface problems
- Motor communication issues
- Parameter validation errors
- Debug procedures

## 9. Legacy ODrive Support
[Brief summary]
- Status: Legacy, maintained for compatibility
- Not used in current Pragati deployment
- Available via launch flag if needed

## 10. References
- TODO_MASTER.md - All planned work
- STATUS_REALITY_MATRIX.md - Validation tracking
- docs/evidence/2025-10-15/SAFETY_MONITOR... - Full implementation details
- docs/archive/2025-10/motor_control/ - Historical docs
```

**Merge Sources Detail:**

| Source | Content to Extract | Target Section |
|--------|-------------------|----------------|
| MOTOR_CONTROL_STATUS.md | Executive summary, build status, completion checklist, quick start | §1 Overview, §7 Testing |
| README_GENERIC_MOTORS.md | 48V power mgmt, CANopen protocol, hardware setup, wiring | §2 Hardware, §6 Config |
| SERVICES_NODES_GUIDE.md | Complete services/nodes/params reference, ROS1→ROS2 mapping | §5 Services |
| MG6010_README.md | Getting started, basic config, launch examples | §6 Config, §7 Testing |
| MG6010_PROTOCOL_COMPARISON.md | Protocol details, bitrate clarification, command set | §3 MG6010 |
| MG6010_STATUS.md | Implementation status, next steps | §1 Overview |
| MG6010_INDEX.md | Document links (use for §10 References) | §10 References |
| TRACEABILITY_TABLE.md | Spec→implementation mapping | §3 MG6010 or §10 |

**Date/Status Fixes:**
- Change "Last Updated: 2024-10-09" → "2025-10-15"
- Remove "October 2025" references unless validated
- Change "✅ PRODUCTION READY" → "⚠️ Beta - Pending Hardware Validation"
- Add explicit hardware dependency list

**Estimate:** 1-2 days (content volume, API verification, restructuring)

#### 2-6. Multiple Files → **ARCHIVE**

**Destination:** `docs/archive/2025-10/motor_control/`

**Files:**
```
MOTOR_CONTROL_STATUS.md → [merged to README]
README_GENERIC_MOTORS.md → [merged to README]
SERVICES_NODES_GUIDE.md → [merged to README]
docs/CODE_DOC_MISMATCH_REPORT.md → [meta doc]
docs/DOCUMENTATION_*.md → [meta docs]
docs/MG6010_MG6010_INTEGRATION_*.md → [completion/plan docs]
docs/MG6010_README.md → [merged to README]
docs/MG6010_README_UPDATES.md → [meta doc]
docs/MG6010_STATUS.md → [merged to README]
docs/MG6010_PROTOCOL_COMPARISON.md → [merged to README]
docs/MOTOR_COMM_*.md → [analysis/fix docs - keep for reference]
docs/MOTOR_CONTROL_COMPREHENSIVE_REVIEW.md → [review doc]
```

**Log Pattern:**
```
[2025-10-15] ARCHIVE src/motor_control_ros2/<FILE>
  → docs/archive/2025-10/motor_control/<FILE>
  Content: [Fully merged into README | Meta documentation | Historical reference]
  Reason: [Consolidation complete | No longer relevant | Historical only]
```

#### 7. SAFETY_MONITOR_IMPLEMENTATION_COMPLETE.md → **MOVE TO EVIDENCE**

**Action:** Move to `docs/evidence/2025-10-15/`

**New Location:** `docs/evidence/2025-10-15/SAFETY_MONITOR_IMPLEMENTATION_COMPLETE.md`

**Changes Before Move:**
- Fix date: "October 6, 2025" → actual commit date (check git log)
- Add disclaimer at top: "Historical implementation doc - see README for current status"

**README Addition:**
- Add concise Safety Monitor summary (§4)
- Link to full implementation doc in evidence/

**Rationale:** Detailed implementation evidence; too long for README; still valuable reference

---

## Yanthra Move Package

### Current Files
```
src/yanthra_move/
├── README.md (100 lines) ✅ Keep (already updated 2025-10-13)
├── CHANGELOG.md ✅ Keep
├── DOCS_CLEANUP_SUMMARY.md (93 lines) ❌ Archive (meta)
└── LEGACY_COTTON_DETECTION_DEPRECATED.md (46 lines) ❌ Archive (deprecation notice)
```

### Actions

#### 1. README.md → **MINOR UPDATE**
**Changes:**
- Add header if missing:
  ```
  Last Updated: 2025-10-15
  Status: Beta - Pending Hardware Validation
  Validation: Sim [yes], Bench [pending], Field [pending]
  Hardware: GPIO (pump, LEDs, switches), motor controllers
  ```
- Add links to:
  - `docs/TODO_MASTER.md`
  - `docs/status/STATUS_TRACKER.md`
- Note 29 code TODOs extracted to TODO_MASTER

**Estimate:** 15-30 min

#### 2-3. Meta Docs → **ARCHIVE**

**Files:**
```
DOCS_CLEANUP_SUMMARY.md → docs/archive/2025-10/yanthra_move/
LEGACY_COTTON_DETECTION_DEPRECATED.md → docs/archive/2025-10/yanthra_move/
```

**Rationale:** Meta documentation about documentation; no longer needed in main package

**Log Entries:**
```
[2025-10-15] ARCHIVE src/yanthra_move/DOCS_CLEANUP_SUMMARY.md
  → docs/archive/2025-10/yanthra_move/DOCS_CLEANUP_SUMMARY.md
  Content: Meta doc about 2025-09 cleanup
  Reason: Historical record; main README is authoritative

[2025-10-15] ARCHIVE src/yanthra_move/LEGACY_COTTON_DETECTION_DEPRECATED.md
  → docs/archive/2025-10/yanthra_move/LEGACY_COTTON_DETECTION_DEPRECATED.md
  Content: Deprecation notice for legacy cotton detection integration
  Reason: Topic covered in README; wrapper already deprecated
```

**Estimate:** 30 min

---

## Root Docs Consolidation

### Phase/Tier Completion Docs (Merge → STATUS_TRACKER.md)

**Files to Consolidate:**
```
docs/
├── PHASE0_COMPLETION_SUMMARY.md
├── PHASE0_PYTHON_CRITICAL_FIXES.md
├── PHASE1_1_COMPLETE.md
├── PHASE1_2_COMPLETE.md
├── PHASE1_3_COMPLETE.md
├── PHASE1_4_COMPLETE.md
├── PHASE1_DEPTHAI_CPP_INTEGRATION_GUIDE.md
├── TIER1_1_COMPLETE.md
├── TIER1_2_COMPLETE.md
├── TIER2_2_COMPLETE.md
├── TIER3_1_COMPLETE.md
└── ... (many more)
```

**Action:** Create `docs/status/STATUS_TRACKER.md`

**Structure:**
```markdown
# Project Status Tracker

**Last Updated:** 2025-10-15  
**Purpose:** Single source of truth for project completion status  
**Evidence:** Links to docs/STATUS_REALITY_MATRIX.md and TODO_MASTER.md

## Current Status Summary

| Area | Phase/Tier | Status | Validation | Next Steps |
|------|-----------|--------|------------|------------|
| Cotton Detection | Phase 1 | ✅ Complete (sim) | ⏳ Hardware pending | Hardware testing |
| Motor Control | MG6010 impl | ⚠️ Code complete | ⏳ Hardware pending | CAN validation |
| Yanthra Move | ROS2 migration | ⚠️ Sim working | ⏳ GPIO stubs | GPIO implementation |
| Documentation | Consolidation | 🔄 In progress | N/A | Complete by 2025-10-17 |

## Detailed Status by Area

### 1. Cotton Detection ROS2
[Extract from PHASE1_* completion docs]
- Phase 0: ✅ Complete
- Phase 1: ✅ Complete (84% originally, now code-complete in sim)
- Phase 2: 📋 Planned (DepthAI direct)
- Phase 3: 📋 Planned (Pure C++)

**Evidence:**
- docs/archive/2025-10/phase-completion/PHASE1_1-4_COMPLETE.md
- src/cotton_detection_ros2/README.md

### 2. Motor Control
[Extract from TIER* completion docs]
- Tier 1: Core refactoring → ✅ Complete
- Tier 2: Testing & docs → ⚠️ Partial (docs in progress)
- Tier 3: Operational robustness → ⚠️ Partial (hardware pending)

**Evidence:**
- docs/archive/2025-10/tier-completion/TIER1_1-2_COMPLETE.md
- src/motor_control_ros2/README.md

### 3. Yanthra Move
[Extract status]
- ROS2 Migration: ✅ Complete (simulation)
- Hardware Integration: ⏳ Pending (GPIO stubs)
- Validation: ⏳ Pending

**Evidence:**
- src/yanthra_move/README.md
- src/yanthra_move/CHANGELOG.md

## Reconciliation with Reality Matrix

[Reference or integrate docs/STATUS_REALITY_MATRIX.md]

The STATUS_REALITY_MATRIX.md provides detailed evidence-based tracking.
This tracker provides higher-level phase/tier status.

**See:** docs/STATUS_REALITY_MATRIX.md for:
- Detailed validation status
- Documentation accuracy tracking
- Hardware dependency matrix
- Action log

## Next Milestones

1. **Complete Doc Consolidation** (ETA: 2025-10-17)
2. **Hardware Validation Session** (ETA: TBD - awaiting hardware)
3. **Production Readiness Review** (ETA: After hardware validation)

## Historical Completion Docs

All phase/tier completion documents archived at:
`docs/archive/2025-10/phase-completion/` and `docs/archive/2025-10/tier-completion/`

See docs/archive/INDEX.md for full listing.
```

**Archive Destination:**
```
docs/archive/2025-10/
├── phase-completion/
│   ├── PHASE0_*.md
│   ├── PHASE1_*.md
│   └── ...
└── tier-completion/
    ├── TIER1_*.md
    ├── TIER2_*.md
    └── TIER3_*.md
```

**Estimate:** 3-4h

---

## Archive Organization

### Directory Structure

```
docs/archive/
├── INDEX.md ← 🆕 Searchable index
├── 2023/
├── 2024/
└── 2025/
    ├── 2025-10-analysis/ ← Keep existing
    ├── 2025-10-audit/ ← Keep existing
    ├── 2025-10-phases/ ← Keep existing
    ├── 2025-10-sessions/ ← Keep existing
    ├── 2025-10-test-results/ ← Keep existing
    ├── 2025-10-validation/ ← Keep existing
    └── 2025-10/ ← 🆕 This consolidation
        ├── cotton_detection/
        │   └── MIGRATION_GUIDE.md
        ├── motor_control/
        │   ├── MOTOR_CONTROL_STATUS.md
        │   ├── README_GENERIC_MOTORS.md
        │   ├── SERVICES_NODES_GUIDE.md
        │   └── docs/ (all MG6010_*.md files)
        ├── yanthra_move/
        │   ├── DOCS_CLEANUP_SUMMARY.md
        │   └── LEGACY_COTTON_DETECTION_DEPRECATED.md
        ├── phase-completion/
        │   └── PHASE*.md files
        └── tier-completion/
            └── TIER*.md files
```

### Archive INDEX.md

**Create:** `docs/archive/INDEX.md`

**Structure:**
```markdown
# Documentation Archive Index

**Last Updated:** 2025-10-15  
**Purpose:** Searchable index of all archived documentation

## Quick Links

- [2025-10 Consolidation](#2025-10-consolidation)
- [2025-10 Audits & Analysis](#2025-10-audits)
- [Phase/Tier Completion](#phase-tier-completion)
- [Historical Status Reports](#historical-status)

## 2025-10 Consolidation

### Cotton Detection
| File | Original Location | Archived Date | Reason |
|------|-------------------|---------------|--------|
| MIGRATION_GUIDE.md | src/cotton_detection_ros2/ | 2025-10-15 | Content merged into README |

### Motor Control
| File | Original Location | Archived Date | Reason |
|------|-------------------|---------------|--------|
| MOTOR_CONTROL_STATUS.md | src/motor_control_ros2/ | 2025-10-15 | Content merged into README |
| README_GENERIC_MOTORS.md | src/motor_control_ros2/ | 2025-10-15 | Content merged into README |
| SERVICES_NODES_GUIDE.md | src/motor_control_ros2/ | 2025-10-15 | Content merged into README |
| ... | ... | ... | ... |

### Yanthra Move
| File | Original Location | Archived Date | Reason |
|------|-------------------|---------------|--------|
| DOCS_CLEANUP_SUMMARY.md | src/yanthra_move/ | 2025-10-15 | Meta doc; historical only |
| LEGACY_COTTON_DETECTION_DEPRECATED.md | src/yanthra_move/ | 2025-10-15 | Topic covered in README |

## Search Tips

Use `grep -r "keyword" docs/archive/` to search archived content.

Files are organized by year and category for easy navigation.
```

**Estimate:** 1h

---

## Evidence Organization

### Directory Structure

```
docs/evidence/
└── 2025-10-15/
    └── SAFETY_MONITOR_IMPLEMENTATION_COMPLETE.md
```

**Purpose:** Store detailed implementation evidence separate from active docs

**When to Use:**
- Implementation completion details (too long for README)
- Test results and validation reports
- Hardware setup documentation with photos/logs
- Benchmark results

**Link From:** Active READMEs with concise summaries

---

## Navigation Updates

### Create docs/INDEX.md

```markdown
# Documentation Index

**Last Updated:** 2025-10-15

## Quick Start
- [Project README](../README.md)
- [TODO Master List](TODO_MASTER.md) ← All work items
- [Status Tracker](status/STATUS_TRACKER.md) ← Current status
- [Status Reality Matrix](STATUS_REALITY_MATRIX.md) ← Evidence-based tracking

## Per-Package Documentation
- [Cotton Detection](../src/cotton_detection_ros2/README.md)
  - [Offline Testing Guide](../src/cotton_detection_ros2/OFFLINE_TESTING.md)
- [Motor Control](../src/motor_control_ros2/README.md)
- [Yanthra Move](../src/yanthra_move/README.md)

## Guides
- [Getting Started](getting-started/QUICK_START.md)
- [Calibration](CALIBRATION_GUIDE.md)
- [Simulation Mode](guides/SIMULATION_MODE_GUIDE.md)
- [Hardware Setup](guides/CAN_BUS_SETUP_GUIDE.md)

## Project Management
- [TODO Master](TODO_MASTER.md) - All planned work
- [Status Tracker](status/STATUS_TRACKER.md) - Current status
- [Gap Analysis](project-management/GAP_ANALYSIS_OCT2025.md)

## Evidence & Reports
- [Evidence](evidence/) - Implementation details
- [Archive](archive/) - Historical documents
  - [Archive Index](archive/INDEX.md) - Search archived docs

## Meta
- [Consolidation Plan](DOCUMENTATION_CONSOLIDATION_PLAN_2025-10-15.md)
- [Consolidation Map](CONSOLIDATION_MAP.md) ← This document
- [Consolidation Log](CONSOLIDATION_LOG.md) - Change tracking
```

---

## Execution Order

### Phase 1: Quick Wins ✅ COMPLETE
1. ✅ Safety net (DONE)
2. ✅ TODO_MASTER.md (DONE)
3. ✅ Created docs/status/ directory
4. ✅ Created docs/evidence/2025-10-15/ directory
5. ✅ Created docs/archive/2025-10/ subdirectories

### Phase 2: Yanthra Move ✅ COMPLETE
1. ✅ Updated README.md (header, links)
2. ✅ Archived 2 meta docs
3. ✅ Updated CONSOLIDATION_LOG.md
4. ✅ Committed

### Phase 3: Cotton Detection ✅ COMPLETE
1. ✅ Merged MIGRATION_GUIDE → README
2. ✅ Updated README header
3. ✅ Archived MIGRATION_GUIDE
4. ✅ Updated CONSOLIDATION_LOG.md
5. ✅ Committed

### Phase 4: Motor Control ✅ COMPLETE
1. ✅ Created new comprehensive README structure (762 lines)
2. ✅ Extracted and merged content from all 19 docs
3. ✅ Verified APIs against code
4. ✅ Fixed date/status claims
5. ✅ Moved SAFETY_MONITOR to evidence/
6. ✅ Archived all merged docs
7. ✅ Updated CONSOLIDATION_LOG.md
8. ✅ Committed (2dd7b2f)

### Phase 5: Root Docs ✅ COMPLETE
1. ✅ Created STATUS_TRACKER.md (417 lines)
2. ✅ Archived phase/tier completion docs (12 files)
3. ✅ Created archive INDEX.md (311 lines)
4. ✅ Committed (3263b36)

### Phase 6: Navigation ✅ COMPLETE
1. ✅ Created docs/INDEX.md (updated with new structure)
2. ✅ Updated internal links (4 docs updated)
3. ✅ Verified all links work
4. ✅ Committed

### Phase 7: Final QA ✅ COMPLETE
1. ✅ Link check (all validated)
2. ✅ Build test (colcon build working)
3. ✅ Updated CONSOLIDATION_LOG summary
4. ✅ Final commit (a4d5a84)
5. ✅ Merged to pragati_ros2 branch

---

## Success Criteria

- [x] Every file has a clear action (update/archive/keep) ✅
- [x] No content lost (all preserved via merge or archive) ✅
- [x] All moves logged in CONSOLIDATION_LOG.md ✅
- [x] New READMEs are comprehensive and authoritative ✅
- [x] All dates/status claims accurate ✅
- [x] All links functional ✅
- [x] Build still works ✅
- [x] TODO_MASTER.md references correct paths ✅
- [x] Archive INDEX.md complete and searchable ✅

**Status:** ✅ ALL SUCCESS CRITERIA MET

---

## Rollback Plan

If issues arise:
1. Each phase is a separate commit
2. Can roll back per-commit: `git revert <hash>`
3. Full rollback: `git checkout main` and delete branch
4. All original content preserved in git history

---

**Status:** ✅ **COMPLETE & MERGED**  
**Completed:** 2025-10-15  
**Total Time:** ~11-13 hours (faster than estimated!)  
**Branch:** Merged to pragati_ros2  
**Files Changed:** 54 files  
**Content Preserved:** 100%

