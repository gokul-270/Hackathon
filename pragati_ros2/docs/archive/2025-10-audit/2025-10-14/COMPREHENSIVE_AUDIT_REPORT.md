# PRAGATI ROS2 - COMPREHENSIVE DOCUMENTATION AUDIT REPORT
```
if (!protocol_->initialize(can_interface_, config_.can_id, 1000000)) {
  // HARDCODED to 1Mbps! Should be 250kbps for MG6010-i6  ← HISTORICAL NOTE
```

**Historical Finding (Sept 2025):** Code defaulted to 1 Mbps even though MG6010-i6 requires 250 kbps.

**Current Reality (Oct 2025):** `src/motor_control_ros2/src/mg6010_controller.cpp` now defaults to 250 kbps with a configurable override (see commit `bb2ba25`). The snippet above is retained for provenance only.

**Status:** ✅ Fixed — docs and sample configs reference `config/mg6010_test.yaml` + `launch/mg6010_test.launch.py` with 250 kbps defaults.
> ℹ️ **Reference Map (2025-10-14 refresh):** Historical archive links cited throughout this report now map to living sources.
> - Safety validation narratives → `docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md` (supersedes `docs/archive/2025-10-analysis/ros1_vs_ros2_comparison/*`).
> - Cotton detection deep dives → `docs/_generated/master_status.md` (Cotton Detection block) and `docs/_generated/restoration_summary_8ac7d2e.md` (replaces `docs/archive/2025-10-analysis/COTTON_DETECTION_SENIOR_CODE_REVIEW.md`).
> - October 7 audit trail → `docs/_generated/master_status.md` and `docs/guides/RESTORATION_NEXT_STEPS.md` (instead of `docs/archive/2025-10-audit/2025-10-07/*`).
> - October 14 simulation reruns → Historical failure (`~/pragati_test_output/integration/comprehensive_test_20251014_093408/`) and post-fix pass (`~/pragati_test_output/integration/comprehensive_test_20251014_095005/`), both summarised in `docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md` §"2025-10-14 Simulation rerun snapshot".
> - TODO/TASK dumps under `docs/archive/2025-10-generated/` → consolidated into `docs/cleanup/odrive_refs_all.txt`, `docs/cleanup/odrive_refs_non_legacy.txt`, and `doc_audit/todo_inventory.csv`.
> - Reference sweep evidence → `docs/cleanup/reference_sweep_2025-10-13.md` (confirms only historical inventories retain archive paths).

---

## EXECUTIVE SUMMARY

### Audit Statistics
- **Total Documentation Files Discovered:** 275+
- **TODO/FIXME/CRITICAL Items Found:** 2,469+
- **Documentation Lines Reviewed:** 50,000+ lines
- **Critical Issues Identified:** TBD (audit in progress)
- **Files Recommended for Deletion/Archive:** TBD
- **Outdated/Misleading Documents:** TBD

### Key Baseline Context (Historical)
This section captures the **pre–2025-10-13** snapshot that triggered the reconciliation push. For the living status view, see `docs/STATUS_REALITY_MATRIX.md`.

Updated references after the reconciliation work:
- **Navigation + Manipulation:** Simulation-first; hardware validation pending. Docs now defer to the status matrix instead of claiming “production ready.”
- **Cotton Detection:** C++ node with DepthAI manager is the canonical path. Calibration parity landed, but hardware validation still open (tracked in status matrix and interface spec).
- **Motor Control:** MG6010-i6 is primary at 250 kbps; hard-coded 1 Mbps bug fixed in October 2025 along with docs/launch/config alignment.
- **Vehicle Control:** ROS 2 Python stack builds/launches; README now flags pending hardware checks and limited automated tests.
- **System Integration Metrics:** Weighted 77 % score retained for historical context only. Current docs emphasise evidence-based reporting rather than a single completion percentage.

---

## PART 1: COMPLETE TODO/FIXME/CRITICAL INVENTORY

### Summary Statistics
Total instances found across all documentation:
```
TODO:     ~1500+ instances
FIXME:    ~50+ instances
CRITICAL: ~300+ instances  
HACK:     ~20+ instances
XXX:      ~10+ instances
TBC/TBA:  ~30+ instances
WIP:      ~50+ instances
[ ]:      ~500+ instances (unchecked checkboxes)
```

### Critical Safety TODOs (HIGH PRIORITY)

#### 1. Safety Monitor TODOs - DOCUMENTED BUT CLARIFIED

**Files:** 
- `docs/EXECUTION_PLAN_2025-09-30.md`
- `docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md` *(supersedes the archived `docs/archive/2025-10-analysis/ros1_vs_ros2_comparison/safety_validation.md`)*
- `docs/STATUS_REALITY_MATRIX.md`

**Status:** ✅ **RESOLVED IN DOC CLEANUP (2025-10-13)**

The October reconciliation scrub updated `src/motor_control_ros2/README.md`, the root `README.md`, and the new `docs/STATUS_REALITY_MATRIX.md` to mark the SafetyMonitor as implemented. Remaining enhancements (telemetry trend logging, threshold tuning) are now tracked as backlog items instead of critical blockers.

**Action Taken:** Backfill conflicting audit notes with references to the status matrix and retire "critical" tags from safety docs. Any future enhancements should be logged as issues rather than blocking items.

#### 2. Cotton Detection Critical TODOs

**Files:**
- `docs/_generated/master_status.md` *(Cotton Detection section — replaces `docs/archive/2025-10-analysis/COTTON_DETECTION_SENIOR_CODE_REVIEW.md`)*
- `docs/_generated/restoration_summary_8ac7d2e.md`

**CRITICAL Items (P0 Priority):**

Line 347-348: **Subprocess STDOUT/STDERR Deadlock Risk**
```
Severity: CRITICAL | Priority: P0 | Effort: 30 min
Issue: Pipes created but never consumed → OS buffer fills → deadlock
```

Line 454-455: **Signal Handler Race Condition**
```
Severity: CRITICAL | Priority: P0 | Effort: Quick Win
Issue: Non-atomic flag access with signals
```

Line 686: **Restart Logic Never Implemented**
```python
# TODO: Implement restart logic if needed  ← NEVER IMPLEMENTED!
```

**Status:** ⚠️ According to `IMPLEMENTATION_FIXES.md`, these are marked as **IMPLEMENTED** (Oct 6, 2025)
**Action Needed:** Cross-verify implementation vs documentation claims (calibration service already verified during 2025-10-07 Raspberry Pi run; keep monitoring remaining TODOs)

#### 3. Hardware Integration Critical Gaps

**File:** `docs/STATUS_REALITY_MATRIX.md` *(Hardware Interfaces row — replaces the archived `docs/archive/2025-10-analysis/ros1_vs_ros2_comparison/hardware_interface_comparison.md`)*

**CRITICAL Findings:**
- Line 32: "Runtime operations expect hardware interfaces that are compiled out"
- Line 126: GPIO Control - compiled out (ENABLE_PIGPIO=OFF) but runtime expects it
- Line 130: End Effector - compiled out but expected
- Line 131: Vacuum Motor - compiled out but expected

**Risk:** 🔴 CRITICAL - Silent failures in production

#### 4. Motor Control Critical - Bitrate Hardcoded

**File:** `src/motor_control_ros2/docs/CODE_DOC_MISMATCH_REPORT.md`

**CRITICAL Issue #1:** Line 15-29
```cpp
// Line 90 in mg6010_controller.cpp
if (!protocol_->initialize(can_interface_, config_.can_id, 1000000)) {
    // HARDCODED to 1Mbps! Should be 250kbps for MG6010-i6
```

**Your Configuration:** 250kbps
**Code Reality:** 1Mbps (hardcoded)
**Result:** Motor won't communicate

**Recommendation:** IMMEDIATE FIX REQUIRED

---

## PART 2: OUTDATED & MISLEADING DOCUMENTATION

### Category A: Status Overclaiming

#### 1. README.md Badges (Updated 2025-10-13)
Historical note: the badges previously implied “Production Ready” status without evidence. The README has since been rewritten to link directly to the status matrix and to describe validation gaps in prose instead of badge percentages. Retain this section for audit transparency but refer readers to the updated README for current claims.

#### 2. README.md Cotton Detection Section (Updated 2025-10-13)
Title/summary now state "Implementation complete, validation pending" and defer to the status matrix for evidence. The historical mismatch is resolved but remains documented here for traceability.

### Category B: Conflicting Information

#### 1. Safety Monitor Status - Multiple Files Conflict

**Document A:** `docs/EXECUTION_PLAN_2025-09-30.md` (Line 16)
```
- ⚠️ Safety System: Framework exists with TODO placeholders
```

**Document B (historical):** `docs/archive/2025-10-analysis/ros1_vs_ros2_comparison/safety_validation.md` (Line 7)
**Current Source:** `docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md` §"Post-Migration Validation Updates"
```
Status: 🔴 **CRITICAL GAPS IDENTIFIED** - Production deployment blocked until resolved
```

**Document C (historical):** `docs/archive/2025-10-analysis/ros1_vs_ros2_comparison/FINAL_REPORT.md` (Line 20)
**Current Source:** `docs/_generated/master_status.md` (Safety Monitor reality row)
```
- ⚠️ **Safety TODOs Remain**: SafetyMonitor framework exists with TODO placeholders - 
  **technical debt, not operational blockers**
```

**Conflict (Historical):** These documents disagreed on whether missing telemetry items were CRITICAL blockers or technical debt.

**Resolution (Oct 2025):** SafetyMonitor implementation (joint/velocity/temperature/comm-timeout checks) landed and is documented in `src/motor_control_ros2/README.md`, `docs/STATUS_REALITY_MATRIX.md`, and `docs/guides/GAPS_AND_ACTION_PLAN.md`. Remaining follow-up items (trend logging, hardware telemetry export) are tracked as backlog enhancements.

**Action:** ✅ Single source of truth established — readers should use the Status Reality Matrix for live status; keep this audit section for traceability.

#### 2. Motor Control Documentation - ODrive vs MG6010

**Historical Snapshot:** Older revisions labeled the package "ODrive Control ROS2 - Production Ready ✅" even though MG6010 was already the target hardware.

**Current Reality (Oct 2025):** The package README now leads with MG6010 (`src/motor_control_ros2/README.md`, 2025-10-13) and positions ODrive as legacy. Supporting docs (`MOTOR_CONTROL_STATUS.md`, `MG6010_INDEX.md`) reinforce the MG-first message.

**Action:** ✅ Completed — keep this record for context.

### Category C: File-Based Paths Still Referenced

Multiple documents reference file-based communication that's being deprecated:

**Files:**
- `/home/ubuntu/pragati/outputs/cotton_details.txt`
- `/home/ubuntu/pragati/inputs/`

**Documents mentioning this:**
- `docs/IMPLEMENTATION_FIXES.md` (Line 112-117)
- `docs/project-management/IMPLEMENTATION_PLAN_OCT2025.md` (Line 265-276)

**Status:** Implementation plan says "Replace File I/O" but multiple docs still reference paths
**Issue:** Unclear if this is legacy or still in use

**Recommendation:** Clarify current state and update all references

---

## PART 3: CRITICAL GAPS (Cross-Validated with Code)

### Gap 1: Motor Bitrate Mismatch (resolved Oct 2025)

**Documentation Claims (pre-fix):** 250 kbps for MG6010-i6  
**Original Code Reality:** 1 Mbps hardcoded (mg6010_controller.cpp:90)

**Action Taken:** `mg6010_controller.cpp` now defaults to 250 kbps with configurable override; MG6010 test nodes and the dedicated CAN interface were updated on 2025-10-14 to ship with the same default. Docs call out MG6010 as the production controller (see commit `bb2ba25` plus the 2025-10-14 changelog entry and `src/motor_control_ros2/README.md`).

**Follow-up:** Await hardware validation logs before closing the backlog item in the status matrix.

### Gap 2: Missing Launch Files for MG6010 (Resolved Oct 2025)

**Historical Finding:** Documentation referenced `mg6010_control.launch.py` / `mg6010_test.launch.py`, but only ODrive launchers were present.

**Current Status:** `src/motor_control_ros2/launch/mg6010_test.launch.py` now ships with the package (confirmed 2025-10-13). Docs have been updated to reference the correct launch path.

**Follow-up:** Keep status matrix entry in sync and record hardware validation once runs complete.

### Gap 3: Missing Configuration Files (Resolved Oct 2025)

**Historical Finding:** Docs pointed to MG6010-specific YAML that was absent.

**Current Status:** `src/motor_control_ros2/config/mg6010_test.yaml` (and related files) now exist and are referenced from the README/launch instructions.

**Follow-up:** Keep config defaults aligned with hardware bench feedback; update status matrix row when new evidence is recorded.

### Gap 4: Calibration Service Handler (Updated)

**Documentation:** `docs/ROS2_INTERFACE_SPECIFICATION.md`
- Documents `/cotton_detection/calibrate` service (detect_command: 2)

**Code Reality (2025-10-13):** `scripts/cotton_detect_ros2_wrapper.py:585-661`
- Handler exports calibration artifacts and returns success state.
- Verified during the October 7 Raspberry Pi hardware session (see `docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md`).

**Status:** ✅ IMPLEMENTED & TESTED (bug fix confirmed)
**Severity:** 🟢 LOW — keep documentation aligned with evidence trail.

**Recommendation:** Ensure interface spec and status matrix reference the hardware validation log; no code changes required.

### Gap 5: Simulation Launch Expects MG6010 Controller (New Oct 2025)

**Documentation:** `docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md` §"2025-10-14 Simulation rerun snapshot" (mirrors launch expectations from `docs/STATUS_REALITY_MATRIX.md`).

**Test Evidence:** `scripts/validation/comprehensive_system_validation.sh` run on 2025-10-14 (`~/pragati_test_output/integration/comprehensive_test_20251014_093408/`).

**Observed Reality:** In hardware-free simulation, the ROS graph never spawns `/mg6010_controller` or the legacy ODrive services (`/joint_homing`, `/joint_idle`, `/joint_status`, `/joint_configuration`, `/motor_calibration`). The automated "System Launch Verification" step fails, even though this absence is expected without CAN hardware.

**Status:** ✅ ADDRESSED FOR SIMULATION — `scripts/validation/comprehensive_test_suite.sh` now treats MG6010 nodes/services as optional when `SIMULATION_EXPECTS_MG6010=0` (default). Strict mode remains available for hardware runs.

**Recommendation:** Keep documenting simulation results with the relaxed setting. Before the next hardware session, export `SIMULATION_EXPECTS_MG6010=1` to re-enable the hard requirement and capture the corresponding logs for the status matrix.

---

## PART 4: FORGOTTEN/BURIED TASKS

### Discovered in Archive/Notes/Misc Files

#### 1. Hidden in .restored/8ac7d2e/

**File:** `.restored/8ac7d2e/COTTON_DETECTION_INTEGRATION_INVENTORY.md`

**Tasks Found:**
- Line 138: Performance benchmarking TODO
- Lines 237-249: Integration test TODOs

**Issue:** These tasks are in a "restored" directory - unclear if still relevant

#### 2. Hidden in docs/cleanup/

**File:** `docs/cleanup/odrive_refs_all.txt`

**Contains:** 16,000+ references to "odrive" across the codebase
**Issue:** Massive cleanup task documented but not tracked in main project docs

#### 3. Hidden TODO List

**File:** `doc_audit/todo_inventory.csv` *(consolidated from the archived `docs/archive/2025-10-generated/todos_scan_raw_2025-09-30.txt`)*

**Contains:** 98+ TODO items captured on September 30, 2025 (now merged with broader inventory)
**Issue:** Ensure consolidated CSV stays the single source of TODO truth

**Sample items:**
```
Line 2: TODO: Add mock hardware support
Line 3: TODO: Implement GPIO interface
Line 9: TODO: Add encoder calibration
...
```

**Recommendation:** Consolidate all TODO tracking into single system

---

## PART 5: CROSS-DOCUMENT MISMATCHES

### Mismatch 1: System Completion Percentage

**Document A:** `README.md` (Line 15)
```
## 🎯 **SYSTEM STATUS: 77% COMPLETE**
```

**Document B (historical):** `docs/archive/2025-10-audit/2025-10-07/PROJECT_STATUS_REALITY_CHECK_CORRECTED.md` (Line 10)
**Current Source:** `docs/_generated/master_status.md` (Overall Snapshot) and `docs/STATUS_REALITY_MATRIX.md`
```
**Corrected Overall Status:** ~50% Complete (previously estimated at 20%)
```

**Conflict:** 77% vs 50% - which is accurate?

**Resolution Needed:** Audit docs show 77% is based on weighted importance, 50% is raw task completion
**Recommendation:** Clarify methodology in README

### Mismatch 2: Cotton Detection Status

**Document A:** `README.md` (Line 137)
```
❌ **CRITICAL GAP**: Detection NOT validated with actual cotton samples
```

**Document B:** `docs/IMPLEMENTATION_FIXES.md` (Line 6)
```
**Status**: ✅ **ALL CRITICAL FIXES IMPLEMENTED**
**Hardware Test Status**: ⏳ Awaiting OAK-D Lite Hardware
```

**Conflict:** "All critical fixes implemented" vs "Critical gap exists"

**Resolution:** Both are true - fixes implemented but validation pending
**Recommendation:** Update README to clarify "Implementation complete, validation pending"

### Mismatch 3: Phase Completion Status

**Document A:** `docs/CPP_IMPLEMENTATION_TASK_TRACKER.md` (Line 13)
```
| Phase 0: Python Stability | 5 | 5 | 0 | 0 | 100% |
| Phase 1: DepthAI Integration | 8 | 5 | 0 | 3 | 63% |
```

**Document B:** `docs/PHASE0_COMPLETION_SUMMARY.md` (Line 18)
```
## Task Summary: 22/41 tasks complete (54%)
```

**Conflict:** 100% vs 54% for Phase 0

**Resolution:** Different scoping - tracker shows 5 critical fixes (100%), summary shows all 41 tasks (54%)
**Recommendation:** Clarify scope differences

---

## PART 6: CONFIGURATION ISSUES (Exact File:Line References)

### Issue 1: CAN Bitrate Configuration

**All Occurrences of Bitrate Values:**

| File | Line | Value | Context | Correct? |
|------|------|-------|---------|----------|
| `mg6010_controller.cpp` | 90 | 1000000 | Hardcoded in initialize() | ❌ NO |
| `mg6010_test_node.cpp` | 43 | 1000000 | Default parameter | ❌ NO |
| `mg6010_integrated_test_node.cpp` | 45 | 1000000 | Default parameter | ❌ NO |
| `README.md` | 510 | 1000000 | CAN setup example | ⚠️ MAYBE (generic) |
| `docs/guides/CAN_BUS_SETUP_GUIDE.md` | 45 | 1000000 | General CAN example | ⚠️ MAYBE |
| `docs/MOTOR_TUNING_GUIDE.md` | 49 | - | No bitrate specified | ⚠️ MISSING |
| `CODE_DOC_MISMATCH_REPORT.md` | 4 | 250000 | User's config | ✅ YES |
| `TRACEABILITY_TABLE.md` | 124 | - | Critical finding noted | ✅ DOCUMENTED |

**Recommendation:** 
1. Fix code to use 250kbps default for MG6010-i6
2. Update all docs to specify motor-specific bitrates
3. Add configuration guide for different motors

### Issue 2: USB Mode Configuration

**File:** `README.md` (Lines 575-576)
```
5. **USB2 Mode Forced**:
   - CottonDetect.py forces USB2 mode (line 317)
   - Cannot be changed via ROS2 parameters in Phase 1
```

**Issue:** Documentation says USB mode is forced, but launch file has usb_mode parameter

**File:** `cotton_detection_wrapper.launch.py`
```python
'usb_mode': LaunchConfiguration('usb_mode'),  # Parameter exists!
```

**Conflict:** Documentation says "cannot be changed" but parameter exists
**Recommendation:** Verify if parameter is functional or placeholder

---

## PART 7: MISSING HANDLERS & INCOMPLETE IMPLEMENTATIONS

### Handler 1: Calibration Service

**Documented:** `docs/ROS2_INTERFACE_SPECIFICATION.md`
```yaml
/cotton_detection/calibrate:
  Type: cotton_detection_ros2/srv/CottonDetection
  Description: Export camera calibration
  Command: detect_command: 2
```

**Code Reality (2025-10-13):** `cotton_detect_ros2_wrapper.py` (Lines 585-661)
```python
elif detect_command == 2:
  export_success = self._export_calibration()
  response.success = export_success
  response.message = "Calibration artifacts exported" if export_success else "Calibration export failed"
  return response
```

**Evidence:** Hardware validation run on October 7 recorded successful calibration exports (see `docs/validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md`).

**Status:** ✅ **IMPLEMENTED & VERIFIED**
**Severity:** 🟢 LOW — remaining work is to catalog artifacts in `data/logs/` and reference them from the status matrix.

### Handler 2: motor_on() Call Missing

**Documented:** Code has `motor_on()` function implemented
**Code Reality:** Never called during initialization

**File:** `mg6010_controller.cpp` (Lines 53-106)
```cpp
bool MG6010Controller::initialize(...) {
    // ... setup code ...
    if (!protocol_->initialize(...)) return false;
    
    initialized_ = true;
    calibrated_ = true;
    return true;  // ← Returns without calling motor_on()!
}
```

**Issue:** Motor ON command exists but never sent
**Severity:** 🔴 CRITICAL - Motor won't activate

**Recommendation:** Add motor_on() call to initialization

### Handler 3: GPIO/Hardware Interfaces Compiled Out

**Documented:** Runtime expects GPIO/camera/end-effector
**Code Reality:** All compiled out (ENABLE_PIGPIO=OFF)

**Evidence:** `docs/STATUS_REALITY_MATRIX.md` (Hardware Interfaces row) and historical snapshot `docs/archive/2025-10-analysis/ros1_vs_ros2_comparison/hardware_interface_comparison.md`

**Missing Handlers:**
- GPIO pin control - placeholder logging only
- End effector control - placeholder logging only
- Vacuum motor control - placeholder logging only

**Severity:** 🔴 CRITICAL - Silent failures in production

---

## PART 8: DEPRECATED FEATURES STILL REFERENCED

### Deprecated 1: ODrive as Primary Controller (Addressed)

- `src/motor_control_ros2/README.md` now leads with MG6010 primary messaging (title updated 2025-10-13).
- Launch/config files include both MG6010 and legacy ODrive options; consider relocating ODrive assets to a `legacy/` folder during future cleanup.
- Status matrix tracks MG6010 as canonical; keep legacy references scoped to migration history.

### Deprecated 2: File-Based Cotton Detection Communication

**Still Referenced In:**
- Multiple docs reference `/home/ubuntu/pragati/outputs/cotton_details.txt`
- Implementation plan says "Replace File I/O" (Oct 2025)

**Reality:** QoS pub/sub partially implemented but file path still in use

**File:** `docs/project-management/IMPLEMENTATION_PLAN_OCT2025.md` (Line 265-276)
```markdown
### 2.1) ROS2 Pub/Sub Synchronization (Replace File I/O)
**Historical Context:**
- ROS1 had pub/sub sync issues
- Workaround: Write detections to `cotton_details.txt`
- **Problem:** Unreliable, slow, not suitable for production
```

**Recommendation:** Clarify if file-based path is:
- ✅ Deprecated and can be removed
- ⚠️ Still in use for backward compatibility
- 🔄 In transition (both exist)

### Deprecated 3: Dynamixel Messages Package

**Status:** REMOVED (Tier 1.1 Complete)

**Still Referenced In:**
- Some archive docs may still mention it
- Check for orphaned references

**Verification:** Legacy references are being scrubbed from guides; run `grep -r "dynamixel_msgs" docs/` as part of ongoing cleanup to ensure only historical notes remain.

---

## PART 9: FILES RECOMMENDED FOR ACTION

### DELETE (High Confidence)

#### Category: Exact Duplicates
1. `docs/archive/2025-10-generated/COMPREHENSIVE_ANALYSIS_REPORT.md` - Duplicate of `oakd_ros2_migration_analysis.md`
2. `docs/archive/2025-10-generated/MASTER_OAKD_LITE_STATUS.md` - Near-duplicate of `master_status.md`

#### Category: Self-Referential Meta-Docs
3. `docs/archive/cleanup_docs/` - 8 files, only reference each other
4. `docs/_archive/2025-10-06/` - 41 files, superseded or duplicated

#### Category: Deprecated Feature Docs
5. `docs/web_dashboard_history/` - 9 files, retain for historical reference while the active dashboard enhancement plan is documented elsewhere

### ARCHIVE (Move to docs/archive/)

#### Category: Superseded by Newer Versions
1. `docs/README_old.md` - Has backup, archive
2. `README.md.backup.2025-10-07` - Backup file, archive
3. `docs/archive/2025-10-old/README_old.md` - Old version, archive

#### Category: Historical Reports (Keep for Reference)
1. All files in `docs/archive/2025-10-audit/2025-10-07/` - Keep as historical record
2. All files in `docs/archive/2025-10-analysis/` - Keep as analysis archive
3. All files in `docs/archive/2025-10-reports/` - Keep as report archive

### UPDATE (High Priority)

#### Category: Core Documentation Needing Updates
1. **`README.md`** - Update status claims, clarify Phase 1 vs Overall percentages
2. **`src/motor_control_ros2/README.md`** - Change title from ODrive to MG6010 primary
3. **`docs/ROS2_INTERFACE_SPECIFICATION.md`** - Update calibration service section to reference the implemented handler and link Oct 7 validation evidence
4. **`src/motor_control_ros2/docs/CODE_DOC_MISMATCH_REPORT.md`** - Verify if fixes applied

#### Category: Consistency Updates
5. **Safety Monitor docs** - Unify messaging (critical vs technical debt)
6. **Cotton Detection status** - Consistent wording across all docs
7. **Motor control** - All docs must reflect MG6010 primary, ODrive legacy

### CONSOLIDATE (Merge Similar Docs)

#### Category: Multiple Status Reviews
1. Consolidate `PROJECT_STATUS_REALITY_CHECK.md`, `COMPREHENSIVE_STATUS_REVIEW_*.md` into single source of truth
2. Consolidate multiple `SESSION_SUMMARY_*.md` files in archive

#### Category: Multiple Completion Reports
1. Consolidate `TIER*_COMPLETE.md`, `PHASE*_COMPLETE.md` into master tracking doc

---

## PART 10: PRIORITIZED ACTION ITEMS

### CRITICAL (Historic Findings & Status)

| # | Action | File:Line | Severity | Status (2025-10-13) | Notes |
|---|--------|-----------|----------|----------------------|-------|
| 1 | Fix MG6010 bitrate hardcode 1 Mbps → 250 kbps | `mg6010_controller.cpp:90` | 🔴 | ✅ Fixed Oct 2025 | Confirmed in repo; docs updated. Hardware validation still pending (status matrix). |
| 2 | Fix MG6010 test node bitrate default | `mg6010_test_node.cpp:43` | 🔴 | ✅ Fixed Oct 2025 | Default now 250 kbps. |
| 3 | Fix integrated test node bitrate | `mg6010_integrated_test_node.cpp:45` | 🔴 | ✅ Fixed Oct 2025 | Matches production bitrate. |
| 4 | Add `motor_on()` call to initialization | `mg6010_controller.cpp:106` | 🔴 | ✅ Verified Oct 2025 | `protocol_->motor_on()` invoked during initialization; controller marks motor enabled. Hardware validation still pending. |
| 5 | Create `mg6010_test.launch.py` | `launch/` | 🔴 | ✅ Added | Located at `src/motor_control_ros2/launch/mg6010_test.launch.py`. |
| 6 | Create `mg6010_test.yaml` config | `config/` | 🔴 | ✅ Added | Located at `src/motor_control_ros2/config/mg6010_test.yaml`. |

**Next critical focus:** Capture MG6010 hardware test evidence to close validation backlog.

### HIGH (Priorities & Progress)

| # | Action | Scope | Status (2025-10-13) | Follow-up |
|---|--------|-------|----------------------|-----------|
| 7 | Update `README.md` status claims | Root README | ✅ Completed | Continue linking evidence via status matrix. |
| 8 | Rename motor control README | `src/motor_control_ros2/README.md` | ✅ Completed | Maintain MG6010-first messaging. |
| 9 | Clarify safety monitor status | Multiple docs | ✅ Completed | Status matrix + guides aligned; keep monitoring hardware validation. |
| 10 | Verify cotton detection fixes | Docs vs code | ⚠️ In progress | Implementation landed; awaiting hardware validation logs. |
| 11 | Delete self-referential meta-docs | `docs/_archive/2025-10-06/` | ✅ Completed | Inventory snapshot enforces absence. |
| 12 | Remove legacy web dashboard docs | `docs/web_dashboard_history/` | ✅ Completed | Enhancement plan documents the active roadmap. |

### MEDIUM (Ongoing Cleanup)

| # | Action | Scope | Status (2025-10-13) | Notes |
|---|--------|-------|----------------------|-------|
| 13 | Consolidate status documents | Multiple | ⏳ Planned | Status matrix now central; consolidation still pending. |
| 14 | Merge completion reports | Tier/Phase docs | ⏳ Planned | Candidate for phased archival. |
| 15 | Update bitrate references | Guides/README | ⏳ Partial | Most core docs updated; scan remaining guides. |
| 16 | Clarify file-based vs pub/sub | Cotton detection docs | ⏳ Planned | Wrapper deprecation + C++ pathway coverage still to document. |
| 17 | Motor-specific config guide | New doc | ⏳ Planned | Could extend maintenance policy or guides. |

**Total Medium Priority Effort:** ~6.5 hours

### LOW (Backlog)

| # | Action | Severity | Effort | Type |
|---|--------|----------|--------|------|
| 18 | Fix markdown lint issues | 🔵 LOW | 2 hours | LINT FIX |
| 19 | Fix broken internal links | 🔵 LOW | 1 hour | LINK FIX |
| 20 | Fix spelling errors | 🔵 LOW | 30 min | TYPO FIX |
| 21 | Improve formatting consistency | 🔵 LOW | 2 hours | FORMAT |
| 22 | Archive old session summaries | 🔵 LOW | 15 min | ARCHIVE |

**Total Low Priority Effort:** ~5.5 hours

---

## PART 11: RAW ARTIFACTS & DATA FILES

All detailed findings, raw data, and supporting artifacts are available in:

```
doc_audit/
├── COMPREHENSIVE_AUDIT_REPORT.md (this file)
├── todo_full_raw.txt (2469+ TODO/FIXME/CRITICAL items with file:line)
├── docs_manifest_seed.txt (from find_files)
├── docs_manifest.csv (to be generated)
├── docs_manifest.json (to be generated)
├── todo_inventory.csv (to be generated)
├── todo_inventory.json (to be generated)
├── doc_claims.json (to be generated)
├── code_facts.json (to be generated)
├── mismatch_matrix.csv (to be generated)
├── critical_gaps.md (to be generated)
├── config_issues.md (to be generated)
├── deprecated_references.csv (to be generated)
├── missing_handlers.csv (to be generated)
├── cross_doc_mismatches.md (to be generated)
├── consolidation_candidates.csv (to be generated)
├── forgotten_tasks.md (to be generated)
├── prioritized_actions.csv (to be generated)
└── files_recommended_actions.md (to be generated)
```

---

## PART 12: METHODOLOGY & VALIDATION

### Review Process
1. ✅ Automated keyword extraction (TODO/FIXME/CRITICAL)
2. 🔄 Line-by-line manual review (IN PROGRESS)
3. ⏳ Cross-validation with code (PENDING)
4. ⏳ Configuration audit (PENDING)
5. ⏳ Link and asset validation (PENDING)

### Quality Assurance
- Every finding includes exact file path and line number
- Every recommendation includes specific action and effort estimate
- Every mismatch includes both conflicting sources
- Every gap includes severity and impact assessment

### Limitations
- Code fixes not automatically validated (manual code review required)
- Some buried tasks may still exist in untouched files
- Cross-references may be incomplete until full repo scan complete

---

## NEXT STEPS

### Immediate Actions (Next 1 Hour)
1. Apply 6 critical code fixes (45 minutes)
2. Create 2 missing files (25 minutes)

### Short Term (Next Week)
1. Update 12 high-priority documentation files
2. Delete deprecated/duplicate files
3. Create consolidated status document

### Medium Term (Next Month)
1. Implement all medium-priority updates
2. Create new configuration guides
3. Validate all cross-references

---

## APPENDICES

### Appendix A: Complete File Manifest
(To be generated from find_files + git ls-files)

### Appendix B: Complete TODO List
See `doc_audit/todo_full_raw.txt` for all 2469+ items

### Appendix C: Configuration Value Matrix
See `doc_audit/config_issues.md` (to be generated)

### Appendix D: Code-Doc Traceability
See `doc_audit/mismatch_matrix.csv` (to be generated)

---

**Report Status:** 🔄 IN PROGRESS - Part 1-11 Complete, Deep Analysis Ongoing  
**Last Updated:** 2025-10-09 17:42 UTC  
**Next Update:** After full line-by-line review complete

