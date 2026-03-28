# Pragati Specification Gap Tracking

**Document Version:** 1.0
**Date:** 2026-01-02
**Status:** Active - Track resolution progress
**Purpose:** Consolidate all ⚠️ NEEDS SPECIFICATION gaps into actionable tracking

---

## Overview

This document consolidates all specification gaps (⚠️ markers) from the PRD and TSD into a single tracking table. Each gap is assigned an owner and target date for resolution.

**Priority Legend:**
- 🔴 **CRITICAL** - Blocks field trial or production
- 🟡 **HIGH** - Impacts system validation or safety
- 🟢 **MEDIUM** - Important for completeness
- ⚪ **LOW** - Nice to have, documentation quality

---

## Gap Summary

| Priority | Count | % of Total |
|----------|-------|------------|
| 🔴 CRITICAL | 8 | 18% |
| 🟡 HIGH | 17 | 39% |
| 🟢 MEDIUM | 14 | 32% |
| ⚪ LOW | 5 | 11% |
| **TOTAL** | **44** | 100% |

---

## 1. Hardware Specification Gaps

### 1.1 Vehicle Platform (🔴 CRITICAL)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-HW-001 | Vehicle payload capacity (must support 6 arms + cotton basket) | TSD §3.5 | 🔴 | HW Team | Jan 2026 | ⬜ Open |
| GAP-HW-002 | Vehicle ground clearance | TSD §3.5 | 🟡 | HW Team | Jan 2026 | ⬜ Open |
| GAP-HW-003 | Vehicle wheelbase and track width | TSD §3.5 | 🟡 | HW Team | Jan 2026 | ⬜ Open |
| GAP-HW-004 | Vehicle maximum speed (for continuous picking optimization) | TSD §3.5, PRD §4.3 | 🔴 | HW Team | Jan 2026 | ⬜ Open |

### 1.2 Power System (🔴 CRITICAL)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-PWR-001 | Battery type specification (LiFePO4, Li-ion, etc.) | TSD §3.6, PRD §6.2 | 🔴 | HW Team | Dec 2025 | ⬜ Open |
| GAP-PWR-002 | Battery capacity (Ah rating) | TSD §3.6 | 🔴 | HW Team | Dec 2025 | ⬜ Open |
| GAP-PWR-003 | Battery voltage specification | TSD §3.6 | 🟡 | HW Team | Dec 2025 | ⬜ Open |
| GAP-PWR-004 | Power consumption measurement (all systems) | PRD §6.2 | 🟡 | HW Team | Jan 2026 | 🔧 Partial — arm and steering motors measured (POWER_BUDGET_ANALYSIS.md, Mar 08). ODrive drive motors and EE motors still estimated. |
| GAP-PWR-005 | Battery charging specification | TSD §3.6 | 🟢 | HW Team | Feb 2026 | ⬜ Open |

### 1.3 End Effector (🟡 HIGH)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-EE-001 | Suction cup diameter and material | TSD §3.4 | 🟡 | HW Team | Dec 2025 | ⬜ Open |
| GAP-EE-002 | Vacuum pump model and power spec | TSD §3.4 | 🟡 | HW Team | Dec 2025 | ⬜ Open |
| GAP-EE-003 | Pressure sensor implementation status | TSD §3.4, PRD §4.2 | 🟢 | HW Team | Jan 2026 | ⬜ Open |
| GAP-EE-004 | Tubing diameter and length | TSD §3.4 | ⚪ | HW Team | Feb 2026 | ⬜ Open |
| GAP-EE-005 | Operating pressure (kPa) | TSD §3.4 | 🟢 | HW Team | Jan 2026 | ⬜ Open |
| GAP-EE-006 | Hold force specification | TSD §3.4 | 🟢 | HW Team | Jan 2026 | ⬜ Open |
| GAP-EE-007 | EE roller seed jamming — cotton seeds getting stuck in roller mechanism. Current roller pin size ~13mm. Pin spacing vs cotton seed size needs investigation. Discovered during Mar 2026 team review. | Field trial Mar 2026 | 🟢 | HW Team | Apr 2026 | ⬜ Open |

### 1.4 Camera & Vision (🟢 MEDIUM)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-CAM-001 | Camera mounting bracket design | TSD §3.2 | 🟢 | HW Team | Jan 2026 | ⬜ Open |
| GAP-CAM-002 | Camera viewing angle relative to arm | TSD §3.2 | 🟢 | HW Team | Jan 2026 | ⬜ Open |
| GAP-CAM-003 | OAK-D Lite exact sensor model verification | TSD §3.2 | ⚪ | Eng Team | Feb 2026 | ⬜ Open |
| GAP-CAM-004 | OAK-D Lite temperature operating range verification | TSD §3.2 | 🟢 | Eng Team | Jan 2026 | ⬜ Open |

### 1.5 Electrical (🟡 HIGH)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-ELEC-001 | USB-to-CAN adapter model | TSD §3.7 | 🟢 | HW Team | Dec 2025 | ⬜ Open |
| GAP-ELEC-002 | E-stop GPIO pin assignment | TSD §3.7 | 🟡 | HW Team | Dec 2025 | ⬜ Open |
| GAP-ELEC-003 | E-stop hardwired status verification | TSD §3.6, PRD §7.1 | 🟡 | HW Team | Dec 2025 | ⬜ Open |
| GAP-ELEC-004 | Motor voltage range verification (36-52V or 12-60V) | PRD §7.1 | 🟢 | HW Team | Dec 2025 | ⬜ Open |
| GAP-GPIO-001 | **Resolved.** GPIO pin consolidation complete (openspec change `gpio-pin-consolidation`). Actions taken: (1) removed 11 stale GPIO pin members from `yanthra_move_system.hpp`, (2) fixed vehicle_control_node.py "GPIO 27" comments → "GPIO 22", (3) fixed BOARD→BCM pin numbers in `endeffector_control.py`, (4) updated TSD §4.4.1 and Appendix D pin tables, (5) updated GPIO_SETUP_GUIDE.md with pigpiod and correct pins, (6) created `docs/guides/GPIO_PIN_MAP.md` as consolidated reference. **Pending physical verification:** arm BCM 12 alias (END_EFFECTOR_DROP_ON vs COTTON_DROP_SERVO_PIN), vehicle auto_manual_switch (BCM 20 vs 26) and start_switch (BCM 6 vs 16) — see `docs/project-notes/GPIO_PIN_REVIEW.md`. E-stop pin remains tracked separately as GAP-ELEC-002. | Codebase audit Feb 2026 | 🟡 | Eng Team | Mar 2026 | ✅ Resolved |
| GAP-ELEC-005 | Encoder configuration verification — output shaft reading only (shaft-connected encoder is what we read). MG6010 steering and ODrive drive motors. Quadrature decoding correctness unverified. Discovered during Mar 2026 team review. | Field trial Mar 2026 | 🟢 | Eng Team | Apr 2026 | ⬜ Open |

---

### 1.6 Vehicle Drive Motors (🟡 HIGH)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-DRV-001 | ODrive drive motor temperature monitoring — no temperature sensors on any of the 3 drive motors. Thermal state completely unmonitored (unlike MG6010 steering motors which report 73-80°C). Discovered during Feb 2026 field trial analysis. | Field trial Feb 2026 | 🟡 | HW Team | Apr 2026 | ⬜ Open |
| GAP-DRV-002 | ODrive drive motor stall threshold calibration for field terrain conditions. Current thresholds cause persistent stall-recovery-restall loops (1,183 ERROR events in single field trial). | Field trial Feb 2026 | 🟡 | Eng Team | Mar 2026 | 🔧 Partial — V2 ODrive error recovery ✅ Mar 05 (stall-recovery-restall loop fixed). Field terrain threshold calibration pending (requires physical testing). |

---

## 2. Performance & Validation Gaps

### 2.1 Critical Measurements (🔴 CRITICAL)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-PERF-001 | Pick cycle time measurement (2.0 sec target) | PRD §5.2 | 🔴 | Field Team | Jan 2026 | ⬜ Open |
| GAP-PERF-002 | Pick success rate measurement (>85%) | PRD §5.2 | 🔴 | Field Team | Jan 2026 | ⬜ Open |
| GAP-PERF-003 | Detection false positive/negative rates | PRD §5.1 | 🟡 | Field Team | Jan 2026 | ⬜ Open |
| GAP-PERF-004 | Long-duration reliability test (24+ hours) | PRD §5.3 | 🟡 | Eng Team | Feb 2026 | ⬜ Open |
| GAP-PERF-005 | Battery runtime validation (4+ hours) | PRD §6.2 | 🟡 | Field Team | Jan 2026 | ⬜ Open |

### 2.2 Communication Validation (🟢 MEDIUM)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-COM-001 | ROS2 topic latency systematic measurement | PRD §5.4 | 🟢 | Eng Team | Jan 2026 | ⬜ Open |
| GAP-COM-002 | MQTT message delivery latency measurement | PRD §5.4 | 🟢 | Eng Team | Jan 2026 | ⬜ Open |

---

## 3. Environmental & Operational Gaps

### 3.1 Field Conditions (🟡 HIGH)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-ENV-001 | Cotton row spacing requirement — Measured 3 ft (0.91 m) at Nedungur (Manivel's field), Mar 2026 | PRD §10.2 | 🟡 | Field Team | Dec 2025 | 🔧 Partial — one site measured, need to verify across field |
| GAP-ENV-002 | Cotton plant height requirement — Avg <3 ft, max 4 ft cotton height, 4-5 ft total plant height at Nedungur, Mar 2026 | PRD §10.2 | 🟡 | Field Team | Dec 2025 | 🔧 Partial — one site measured, PRD §10.2 spec still needs update |
| GAP-ENV-003 | Cotton boll size specification | PRD §10.2 | 🟢 | Field Team | Dec 2025 | ⬜ Open |
| GAP-ENV-004 | Minimum illumination (lux) | PRD §6.1 | 🟢 | Eng Team | Jan 2026 | ⬜ Open |
| GAP-ENV-005 | Soil type compatibility | PRD §6.1 | ⚪ | Field Team | Feb 2026 | ⬜ Open |
| GAP-ENV-006 | Maximum slope tolerance | PRD §6.1 | 🟢 | HW Team | Jan 2026 | ⬜ Open |

### 3.2 Compliance & Certification (⚪ LOW for now)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-COMP-001 | Electrical safety standards (IEC 60204-1, etc.) | PRD §7.2 | ⚪ | Compliance | Q2 2026 | ⬜ Open |
| GAP-COMP-002 | Mechanical safety standards (ISO 12100, etc.) | PRD §7.2 | ⚪ | Compliance | Q2 2026 | ⬜ Open |
| GAP-COMP-003 | Agricultural equipment standards (ASABE, ISO 4254) | PRD §7.2 | ⚪ | Compliance | Q2 2026 | ⬜ Open |

---

## 4. Documentation Gaps

### 4.1 Technical Documentation (🟢 MEDIUM)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-DOC-001 | Joint limits documentation | PRD §4.2 | 🟢 | Eng Team | Dec 2025 | ⬜ Open |
| GAP-DOC-002 | Trajectory acceleration/jerk limits | PRD §4.2 | 🟢 | Eng Team | Jan 2026 | ⬜ Open |
| GAP-DOC-003 | Arm workspace envelope definition | PRD Appendix E | 🟢 | Eng Team | Jan 2026 | ⬜ Open |
| GAP-DOC-004 | IK algorithm detailed documentation | PRD Appendix E | ⚪ | Eng Team | Feb 2026 | ⬜ Open |
| GAP-DOC-005 | Maintenance schedule definition | PRD §6.3 | 🟢 | Ops Team | Feb 2026 | ⬜ Open |

---

## 5. Fleet Drift Gaps

### 5.1 Fleet Configuration Drift (🟡 HIGH)

| Gap ID | Description | Source | Priority | Owner | Target Date | Status |
|--------|-------------|--------|----------|-------|-------------|--------|
| GAP-FLEET-001 | Fleet OS Version Currency — arm2 runs Ubuntu 24.04.3 while arm1 and vehicle run 24.04.4. No automated detection of OS version drift across fleet. Security patches and bug fixes missing on arm2. Inconsistent behavior possible. Mitigation: `fleet_drift_report.py` detects OS version drift. Manual upgrade required (apt full-upgrade with physical access). | Fleet audit Mar 2026 | 🟡 | Eng Team | Apr 2026 | ⬜ Open |
| GAP-FLEET-002 | Fleet Package Consistency — arm1 carries 153 extra packages (ros-jazzy-desktop residue). arm2 behind on 11 pip packages. No automated package drift detection. Disk usage waste on arm1, potential version mismatch issues on arm2 (e.g., cantools 41.0.2 vs 41.1.1). Mitigation: `fleet_drift_report.py` detects package drift. Manual cleanup/upgrade required. | Fleet audit Mar 2026 | 🟡 | Eng Team | Apr 2026 | ⬜ Open |
| GAP-FLEET-003 | Fleet config.txt Correctness — arm1 has wrong CAN oscillator (12 MHz instead of 8 MHz). Vehicle has CAN dtoverlay for non-existent CAN HAT and missing spimaxfrequency. Vehicle/arm2 have CAN dtoverlay without CAN hardware. arm1 CAN bus runs at wrong baud rate (silent frame corruption). Vehicle/arm2 have unnecessary kernel module loaded. Mitigation: `setup_raspberry_pi.sh` fixed with SPI detection gate and correct oscillator. `sync.sh --provision` manages config.txt. `sync.sh --verify` detects mismatches. | Fleet audit Mar 2026 | 🟡 | Eng Team | Apr 2026 | ⬜ Open |

---

## Resolution Workflow

### How to Close a Gap

1. **Investigate:** Gather data, measurements, or design decisions
2. **Document:** Update the relevant section in PRD or TSD
3. **Verify:** Get appropriate review/approval
4. **Update:** Change status to ✅ Closed with date
5. **Cross-reference:** Update VALIDATION_MATRIX.md if applicable

### Status Definitions

| Status | Meaning |
|--------|---------|
| ⬜ Open | Not yet addressed |
| 🔄 In Progress | Being actively worked on |
| 📋 Under Review | Solution proposed, awaiting approval |
| ✅ Closed | Resolved and documented |
| ❌ Won't Fix | Decided not to address (with justification) |

---

## Priority Resolution Plan

### Before January 2026 Field Trial

**Must resolve (🔴 CRITICAL):**
- GAP-HW-001: Vehicle payload capacity
- GAP-HW-004: Vehicle maximum speed
- GAP-PWR-001: Battery type
- GAP-PWR-002: Battery capacity
- GAP-PERF-001: Pick cycle time measurement
- GAP-PERF-002: Pick success rate measurement

**Should resolve (🟡 HIGH):**
- GAP-EE-001, GAP-EE-002: End effector specs
- GAP-ELEC-002, GAP-ELEC-003: E-stop verification
- GAP-ENV-001, GAP-ENV-002: Field condition requirements

### Before November 2026 Production

**All remaining 🟡 HIGH and 🟢 MEDIUM gaps**

---

## Gap Closure Log

| Gap ID | Closed Date | Resolution Summary | Closed By |
|--------|-------------|-------------------|-----------|
| GAP-GPIO-001 | 2026-03-08 | GPIO pin consolidation complete — removed 11 stale GPIO pin members from `yanthra_move_system.hpp`, fixed vehicle/arm GPIO references, updated TSD/GPIO guides, created `GPIO_PIN_MAP.md`. Physical verification pending for 3 pin aliases (see `GPIO_PIN_REVIEW.md`). | Udayakumar (openspec: gpio-pin-consolidation) |

---

## Update History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-02 | System | Initial gap tracking document created |
| 2026-03-03 | Udayakumar | Added GAP-DRV-001/002 (drive motor temp + stall), GAP-EE-007 (roller seed jam), GAP-ELEC-005 (encoder config) from Mar 2026 team review |
| 2026-03-05 | Udayakumar | Added GAP-FLEET-001/002/003 (fleet OS drift, package consistency, config.txt correctness) from fleet audit |
| 2026-03-09 | Udayakumar | Gap Closure Log: added GAP-GPIO-001 closure. Updated GAP-DRV-002 to partial (V2 stall fix done). Updated GAP-PWR-004 to partial (power budget analysis done). |

---

**Next Review:** Weekly during field trial prep (Dec 2025 - Jan 2026)
**Owner:** Engineering Team Lead
**Escalation:** Unresolved 🔴 CRITICAL gaps → Project Manager
