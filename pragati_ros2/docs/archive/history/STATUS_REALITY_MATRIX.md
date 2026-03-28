# Pragati ROS2 Status Reality Matrix


**Last Updated:** 2025-11-01  
**Date:** 2025-11-01  
**Maintainers:** Systems & Documentation Team  
**Purpose:** Single source for reconciling code/test reality with documentation claims. Update this file before changing high-level status docs or badges.

**Latest Update:** ✅ **PRODUCTION READY** (2025-11-01) — Hardware validated Oct 30, detection service latency validated at 134ms avg (Nov 1), system ready for field deployment.

---

## Legend

| Status | Meaning |
|--------|---------|
| ✅ Accurate | Documentation matches code/tests; no action required.
| ⚠️ Needs Update | Documentation exists but is stale, incomplete, or conflicting.
| 🔴 Incorrect | Documentation claims contradict reality; requires immediate correction.
| 🆕 Missing | No authoritative documentation exists yet; create one when stabilised.

Evidence citations reference file paths (and optional line numbers) within this repository. Tests reference scripts or outputs in `test_output/integration/` or `scripts/validation/`.

---

## 1. Core Subsystems

| Capability / Claim | Reality Check (Code / Tests) | Current Documentation | Status | Required Actions |
|--------------------|------------------------------|-----------------------|--------|------------------|
| **Navigation / Vehicle Control** deployment language | `src/vehicle_control/` package builds and launches; integration node (`ros2_vehicle_control_node`) runs with simulation defaults. Hardware IO and CAN paths remain untested since the ROS 2 migration; only one pytest exists. | `src/vehicle_control/README.md` (2025-10-14) removes "production ready" marketing, flags simulation-only validation, and enumerates hardware TODOs. | ✅ Accurate | Capture bench logs + CAN/GPIO verification during the next hardware session, then update readiness language across docs.
| **Motor Control (MG6010 primary)** production ready | Code in `src/motor_control_ros2/src/` implements MG6010 protocol/controller, CAN interface, safety monitor; config and launch files exist (`config/mg6010_test.yaml`, `launch/mg6010_test.launch.py`). | Docs are now MG-first: `src/motor_control_ros2/README.md` (2025-10-13) and root `README.md` highlight MG6010 primary path; `MOTOR_CONTROL_STATUS.md` aligns. Hardware validation still pending. | ⚠️ Monitoring | Record hardware bench results once available; propagate to status docs and matrix; keep legacy ODrive notes segregated.
| **Yanthra Move Manipulation** production-ready | `src/yanthra_move/` C++ code with motion planning and simulation defaults; hardware I/O helpers still TODO (`yanthra_move_system.cpp`, lines 70–130). Validation scripts exist but hardware logs pre-date DepthAI pipeline. | `src/yanthra_move/README.md` (2025-10-13) now flags simulation-first status, TODOs, and pending hardware validation; `DOCS_CLEANUP_SUMMARY.md` updated accordingly. | ⚠️ Monitoring | Capture next physical bench run + log references, then reassess readiness language across docs and badges.
| **Cotton detection primary implementation** is C++/DepthAI | C++ node `src/cotton_detection_ros2/src/cotton_detection_node.cpp`; DepthAI manager (`src/cotton_detection_ros2/src/depthai_manager.cpp`) compiled when `-DHAS_DEPTHAI=ON`. Launch file `launch/cotton_detection_cpp.launch.py` defaults to C++ path. | Root `README.md`, package `README.md`, `docs/ROS2_INTERFACE_SPECIFICATION.md`, and `docs/_generated/master_status.md` (2025-10-13 refresh) all position the C++ node as canonical while flagging hardware evidence gaps. | ⚠️ Monitoring | Capture hardware validation evidence (DepthAI field run + calibration export) and update Required Actions once logs exist; track remaining TODOs in interface spec appendix.
| **Python wrapper** retained for legacy | `scripts/cotton_detect_ros2_wrapper.py` still shipped; launch file `cotton_detection_wrapper.launch.py`. Now redundant for calibration (C++ parity landed Oct 2025) but still used by legacy automation. | Package README + interface spec appendix now emphasise legacy-only usage, simulation instructions, and deprecation plan; wrapper retirement trackers remain in migration guide. | ⚠️ Monitoring | Keep wrapper available for automation until hardware sign-off; once evidence captured, schedule retirement milestone + CI smoke tests for C++ path.
| **DepthAI direct detections & camera pipeline** | `DepthAIManager` handles device connection, detection queue; TODOs remain for runtime config (`TODO` markers lines 138, 166, etc.). DepthAI support disabled by default (CMake option). | README + interface spec describe `-DHAS_DEPTHAI=ON` flag, depthai parameter block, and outstanding TODOs. | ⚠️ Needs Update | After TODOs cleared + validation runs logged, flip status to ✅ and remove caveats; until then keep backlog noted in docs.
| **Safety Monitor** implemented and active | `src/motor_control_ros2/src/safety_monitor.cpp` implements joint limits, velocity, temperature, comm timeouts; integrated in controller. | Audit report, execution plan (Sept 30 doc), and package README now note implementation as complete with telemetry enhancements tracked as backlog. | ✅ Accurate | Keep backlog items (trend logging, telemetry export) tracked in documentation; capture hardware telemetry evidence during next MG6010 session.
| **Motor CAN bitrate** correctly set to 250 kbps default | `mg6010_controller.cpp` (line ~95) sets default 250000 and allows overrides. Config file `config/mg6010_test.yaml`; launch file `launch/mg6010_test.launch.py`. | Package docs and traceability table now reflect the 250 kbps default; historical notes preserved for context. | ✅ Accurate | Keep mentioning override instructions for alternate motors; capture hardware log confirming 250 kbps during next bench run.
| **Vehicle control + arm integration** weighted percentage | Weighting logic not codified; historical README referenced 77% without backing artifact. | README (Oct 2025) now defers to this matrix instead of quoting aggregate percentages. | ✅ Accurate | Keep the aggregate score retired unless a refreshed methodology is published here with supporting evidence.
| **Pattern Finder (ArUco utility)** required for calibration | Package builds (`colcon build --packages-select pattern_finder`) but executable (`aruco_finder`) is standalone, relies on hard-coded `/home/ubuntu` paths and external RealSense script. No ROS 2 node or recent validation. | `src/pattern_finder/README.md` (2025-10-13) now marks the tool as *legacy/optional*; calibration guides no longer treat it as required. | ⚠️ Monitoring | Archive remaining references in legacy docs and track the ROS 2 reimplementation decision in `docs/guides/GAPS_AND_ACTION_PLAN.md`.
| **Robot Description URDF** accurate for current hardware | `data/pragati_robot_description.urdf` and `docs/robot_description/` assets match the latest CAD inputs; TF tree verified via simulation launch (`ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true`). | `docs/robot_description/CHANGELOG.md` (2025-10-13) documents recent URDF refresh; README links direct users to the canonical URDF under `data/`. | ✅ Accurate | Re-run the TF validation script after hardware mount adjustments and capture diffs in the changelog before deploying new URDFs.

---

## 2. Testing & Validation

| Area | Reality Check | Documentation | Status | Actions |
|------|---------------|---------------|--------|---------|
|| Software test coverage | **Software Sprint Complete (2025-10-21):** 218 total tests (99 baseline + 119 new), 100% pass rate. motor_control_ros2: 70 tests (protocol, safety, parameters, CAN communication) with 29% coverage. yanthra_move: 17 coordinate transform tests. cotton_detection_ros2: 86 tests (54 baseline + 32 edge cases). Comprehensive suite re-ran 2025-10-14 09:50 IST and passes in simulation with `SIMULATION_EXPECTS_MG6010=0`. | README, package READMEs, and docs/status/SW_SPRINT_STATUS.md reflect sprint achievements. Comprehensive guides added (FAQ, Motor Tuning, API Docs, Performance Optimization). | ✅ Accurate | Capture hardware-backed run with motors when available; continue expanding test coverage for hardware-dependent components.
| Hardware testing (MG6010, DepthAI camera) | Hardware scripts exist but rely on physical setup. No new logs since Oct 7. | README claims 9/10 hardware tests pass; `HARDWARE_TEST_RESULTS.md` (Oct 7) matches. | ⚠️ Needs Update | Note hardware dependency; add reminder to rerun before production claim.
| Simulation mode support | Launch parameter `use_simulation` in `pragati_complete.launch.py`; C++ node handles `simulation_mode`. | New `docs/guides/SIMULATION_MODE_GUIDE.md` (2025-10-13) documents end-to-end flows for C++ node, wrapper, and yanthra_move, including smoke-test snippets. | ⚠️ Monitoring | Keep the guide synced with future launch changes; fold results from automated smoke tests into `test_output/integration/` once scripted.

---

## 3. Documentation Assets

| Document | Role | Reality vs Content | Status | Follow-up |
|----------|------|-------------------|--------|-----------|
| `README.md` | Entry point; exposes badges/claims. | Updated 2025-10-14: badges link here, cotton detection section reflects C++ primary path, historical metrics flagged as legacy, deployment checklist + roadmap defer to this matrix and Phase 3 backlog. | ✅ Accurate | When fresh hardware evidence is captured, replace the historical metric note with up-to-date numbers.
| `ROS2_INTERFACE_SPECIFICATION.md` | Cotton detection interfaces. | Updated 2025-10-13 and refreshed Oct 2025 to document C++ calibration export + legacy appendix context. | ⚠️ Monitoring | Ensure future revisions capture hardware validation results and wrapper retirement timeline.
| `docs/guides/SYSTEM_MIGRATION.md` | Consolidated migration guide (OAK-D, MG6010, Cotton Detection) | Created 2025-10-21; consolidates three major migrations. Originals archived to archive/2025-10-phase2/ | ⚠️ Monitoring | Close residual TODOs as Phase 3 work lands (runtime config, lifecycle node, benchmarking).
| `DOC_INVENTORY_FOR_AUDIT.md` | Cleanup guide. | Updated 2025-10-13 via `scripts/doc_inventory.py`; snapshot stored at `docs/doc_inventory_snapshot.json`. | ✅ Accurate | Quick validation now runs `scripts/validation/doc_inventory_check.sh`; keep weekly check in rotation.
| `enhancements/WEB_DASHBOARD_ENHANCEMENT_PLAN.md` | Dashboard roadmap. | New plan (2025-10-13) capturing current state and enhancement backlog for the operator dashboard. | ⚠️ Monitoring | Execute backlog items (data model refresh, ROS2 launch integration, tests); shell launcher `scripts/launch/web_dashboard.sh` available as interim solution.
| `docs/archive/2025-10-audit/*` | Historical audit evidence. | `AUDIT_SUMMARY.md` and `COMPREHENSIVE_AUDIT_REPORT.md` annotated with reconciliation notes; remaining files stored under the dated archive folder for provenance. | ✅ Accurate | Keep referencing the archive for historical context; new findings should land directly in living docs.
| `docs/cross_reference_matrix.csv` | Feature ↔ documentation ↔ code mapping for current implementation. | Refreshed 2025-10-14 to reflect C++ detection primary path and governance automation. | ✅ Accurate | Update alongside new interfaces or documentation claims. |

---

## 4. Feature Backlog & Enhancements (Documented vs Implemented)

| Feature / Enhancement | Documented In | Implementation Status | Documentation Adjustment |
|-----------------------|---------------|-----------------------|--------------------------|
| Calibration data export via C++ path | Implemented in `cotton_detection_node` (Oct 2025) with DepthAI YAML export and script fallback. | Implemented. | Update docs to direct users to C++ service; keep wrapper mention as optional fallback until retirement.
| Lifecycle node + diagnostics for cotton detection | `CPP_IMPLEMENTATION_TASK_TRACKER.md`. | Partially implemented (diagnostic updater present, lifecycle TODO). | Update tracker to reflect diagnostic progress, keep lifecycle node in backlog.
| Performance benchmarking to 2.5 s latency | Older analysis docs. | No automated benchmarks; manual testing needed. | Mark as outstanding validation item.

---

## 5. Action Log (to sync with plan)

1. ✅ **README rewrite** — Completed 2025-10-13. Badges now point to this matrix, cotton detection section reflects C++ primary path, MG6010 context clarified. _Owner: Documentation_.
2. ✅ **Cotton detection doc refresh** — Completed 2025-10-13. Interface spec, package README, and migration guide now align with C++ primary path and document remaining gaps. _Owner: Cotton Detection team_.
3. ✅ **Safety monitor clarification** — Completed 2025-10-13. Audit docs now reference implementation reality; enhancements tracked as backlog. _Owner: Motor Control team_.
4. ✅ **Doc inventory refresh** — Completed 2025-10-13. Automation delivered via `scripts/doc_inventory.py` + snapshot enforcement script. _Owner: Documentation_.
5. ✅ **Test results update** — Completed 2025-10-14. Simulation suite summary added at `test_output/integration/2025-10-14_simulation_suite_summary.md`; matrix references updated. _Owner: QA_.
6. ✅ **Governance doc** — Completed 2025-10-13. See `docs/maintenance/DOC_MAINTENANCE_POLICY.md`. _Owner: Systems_.
7. ✅ **Simulation validation refresh** — Completed 2025-10-14. Comprehensive suite updated with `SIMULATION_EXPECTS_MG6010` toggle; passing evidence stored under `~/pragati_test_output/integration/comprehensive_test_20251014_095005/`. _Owner: QA_.
8. ✅ **Documentation consolidation** — Completed 2025-10-15. Created `PRODUCTION_READINESS_GAP.md` (555 lines), `CONSOLIDATED_ROADMAP.md` (346 lines), and `CONSOLIDATION_SUMMARY.md`. Archived originals to `docs/archive/2025-10-15/`. Added pointer banners to overlapping docs. _Owner: Documentation_. _Commits: 9ad8905, fad5e5d_.

Update this matrix after each action to keep the reconciliation effort transparent.

---

## 6. Hardware Validation Status

> **Update (Oct 30, 2025):** Hardware validation completed! Section below reflects historical context.
> **Current Status:** ✅ **PRODUCTION READY** - Phase 1 MVP achieved.

### Validation Results (Oct 29-30, 2025)

| Component | Result | Evidence |
|-----------|--------|----------|
| **Motor Control** | ✅ Complete | 2-motor system validated, <5ms response |
| **Cotton Detection** | ✅ Complete | 134ms latency, 100% reliability |
| **Camera Pipeline** | ✅ Complete | USB 2.0 mode, manual exposure tuned |
| **System Integration** | ✅ Complete | Zero crashes, stable operation |

### Current Production Status

**Phase 1 MVP: ACHIEVED**
- Operation: Stop-and-go with multi-cotton detection
- Camera: OAK-D Lite with USB 2.0 and manual exposure
- Motors: MG6010 with CAN @ 250kbps
- Throughput: ~600-900 picks/hour

**Phase 2 Target (Future)**
- Operation: Continuous motion
- Throughput: ~1,800-2,000 picks/hour
- Timeline: 8-12 weeks additional development

**For details:** See `docs/PRODUCTION_READINESS_GAP.md`

### Key Deliverables Created (2025-10-15)

1. **PRODUCTION_READINESS_GAP.md** (555 lines)
   - Executive summary of Phase 1 vs Phase 2
   - Critical hardware blocker identification
   - Gap matrix across 8 functional areas
   - Production readiness checklist with validation tasks
   - Success criteria for MVP and production
   - Risk assessment with mitigation strategies

2. **CONSOLIDATED_ROADMAP.md** (346 lines)
   - Work categorized by hardware dependency
   - 🔴 Blocked: 43-65h (hardware required)
   - 🟢 Immediate: 29-45h (software only)
   - 🟡 Phase 2: 200-300h (post-MVP)
   - 🔵 Future: ~370 items (backlog)

3. **CONSOLIDATION_SUMMARY.md** (317 lines)
   - Summary of consolidation effort
   - Key findings and critical blockers
   - Next actions for development and management

4. **Archive: docs/archive/2025-10-15/**
   - Snapshot of all original documentation
   - Enables audit trail and rollback

### Consolidation Results

**Status:** ✅ **COMPLETE** (2025-10-15 17:47 IST)

**Extraction Summary:**
- Extracted 302 raw TODO items from docs and code
- Removed 23 duplicates → 279 unique items
- Classified using automated taxonomy
- Generated stable IDs (format: T-PR2-2025-10-xxxxxxxx)

**Deliverables:**
1. ✅ `docs/archive/2025-10-15/todos_completed.md` — 172 completed items archived
2. ✅ `docs/archive/2025-10-15/todos_obsolete.md` — 4 obsolete items archived
3. ✅ `docs/TODO_MASTER_CONSOLIDATED.md` — 103 active items (53 backlog + 7 future + 43 code TODOs)
4. ✅ `docs/archive/2025-10-15/todos_all.json` — Full dataset with metadata

**Key Insight:** Original estimates (~2,540 items) included meta-documentation tasks and already-removed items. Actual unique TODOs extracted: 279.

### Canonical Document References

**For Production Readiness:**
- `docs/PRODUCTION_READINESS_GAP.md` — Phase 1 vs Phase 2, hardware blockers, validation checklists
- `docs/CONSOLIDATED_ROADMAP.md` — Actionable roadmap with hardware dependencies visible
- `docs/CONSOLIDATION_SUMMARY.md` — Executive summary of consolidation findings

**For Active Work:**
- `docs/TODO_MASTER_CONSOLIDATED.md` — Consolidated active work
- `docs/STATUS_REALITY_MATRIX.md` — This document (reality check)

**For Historical Context:**
- `docs/archive/2025-10-15/` — Snapshot of documentation state before consolidation
