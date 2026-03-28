# Pragati Specifications

This folder contains the consolidated specification documents for the Pragati Cotton Picking Robot system.

**Last Updated:** 2026-01-02  
**Status:** Active - Comprehensive specification suite

---

## Quick Navigation

| Document | Purpose | Audience |
|----------|---------|----------|
| [PRD](./PRODUCT_REQUIREMENTS_DOCUMENT.md) | What & Why | All stakeholders |
| [TSD](./TECHNICAL_SPECIFICATION_DOCUMENT.md) | How (implementation) | Engineers |
| [Validation Matrix](./VALIDATION_MATRIX.md) | Requirement traceability | QA, Management |
| [Gap Tracking](./GAP_TRACKING.md) | Missing specifications | All teams |
| [Test Cases](./TEST_CASES.md) | Formal test procedures | QA, Engineers |
| [Config Schemas](./CONFIG_SCHEMAS.md) | YAML configuration guide | Engineers |

---

## Documents

### 📘 [Product Requirements Document (PRD)](./PRODUCT_REQUIREMENTS_DOCUMENT.md)
**Audience:** All stakeholders - Executives, Product Managers, Field Operators, External Partners

**Purpose:** Defines WHAT the system should do and WHY

**Contents:**
- Executive Summary & Business Objectives
- Product Overview & Capabilities
- Market & Use Cases
- Functional Requirements (Detection, Manipulation, Navigation, Communication)
- Performance Requirements & Targets
- Operational Requirements (Environment, Power, Maintenance)
- Safety & Compliance
- Quality & Success Metrics
- Development Phases (Phase 1 & Phase 2)
- Constraints & Assumptions

**Key Metrics:**
- Pick Success Rate: >95% (target)
- Spatial Accuracy: ±10mm @ 0.6m (validated)
- Detection Latency: 70ms (validated)
- Throughput: 600-900 picks/hour (Phase 1), 1,800-2,000 (Phase 2)

---

### 🔧 [Technical Specification Document (TSD)](./TECHNICAL_SPECIFICATION_DOCUMENT.md)
**Audience:** Engineers, Developers, System Integrators, QA, Maintenance Personnel

**Purpose:** Defines HOW the system is implemented

**Contents:**
- System Architecture (Distributed Multi-Arm)
- Hardware Specifications (RPi 5, OAK-D Lite, MG6010 Motors)
- Software Architecture (ROS2 Packages, Node Graph, State Machines)
- Component Specifications (Detection Pipeline, Motor Control, Motion Planning)
- Interface Specifications (ROS2 Topics/Services, Messages, Parameters)
- Communication Protocols (CAN, MQTT, DDS)
- Data Structures & Algorithms (IK, Trajectory Planning, Fusion)
- Safety & Monitoring Systems (100Hz Safety Monitor, Diagnostics)
- Configuration Management (YAML, Build Options)
- Build & Deployment (Development Workflow, RPi Deployment)
- Testing & Validation (Unit Tests, Integration Tests, Hardware Tests)
- Performance Optimization (Build, Runtime, Memory)
- Troubleshooting & Diagnostics (Common Issues, Recovery Procedures)

---

### 📋 [Validation Matrix](./VALIDATION_MATRIX.md) 🆕
**Audience:** QA Engineers, Management, Engineering Team

**Purpose:** Single source of truth for requirement validation status

**Contents:**
- All requirements mapped to test evidence
- Validation status (✅ Validated, 🚧 Partial, ⏳ Pending, ❌ Blocked)
- Critical path items for field trial
- Evidence document references

**Key Stats (as of Jan 2026):**
- 45 total requirements tracked
- 27% validated, 24% blocked (need hardware/field)
- 12 critical path items before production

---

### 🚨 [Gap Tracking](./GAP_TRACKING.md) 🆕
**Audience:** All teams - prioritized action items

**Purpose:** Consolidate all ⚠️ specification gaps for tracking

**Contents:**
- 38 gaps organized by category
- Priority levels (🔴 Critical → ⚪ Low)
- Owner assignments and target dates
- Resolution workflow and closure log

**Priority Summary:**
- 🔴 CRITICAL: 8 gaps (blocks field trial)
- 🟡 HIGH: 12 gaps (impacts validation)
- 🟢 MEDIUM: 13 gaps (completeness)
- ⚪ LOW: 5 gaps (documentation quality)

---

### 🧪 [Test Cases](./TEST_CASES.md) 🆕
**Audience:** QA Engineers, Field Team

**Purpose:** Formal test procedures mapped to requirements

**Contents:**
- 17 test cases across 5 categories
- Test steps, expected results, actual results
- Execution schedule (Dec 2025 - Feb 2026)
- 7 tests passed, 10 pending

**Test Categories:**
- Detection (TC-DET-001 to 005)
- Manipulation (TC-ARM-001 to 005)
- Safety (TC-SAFE-001 to 003)
- Communication (TC-COM-001 to 002)
- System (TC-SYS-001 to 003)

---

### ⚙️ [Configuration Schemas](./CONFIG_SCHEMAS.md) 🆕
**Audience:** Engineers, DevOps

**Purpose:** Document YAML configuration file schemas

**Contents:**
- Schema definitions for all config files
- Key parameters with defaults and ranges
- Common configuration errors and fixes
- Parameter override examples

**Config Files Documented:**
- Motor control (mg6010_test.yaml, production.yaml)
- Cotton detection (production.yaml)
- Yanthra move (production.yaml)
- Vehicle control (production.yaml)

---

## Document Status

**Version:** 1.1  
**Date:** 2026-01-02  
**Status:** ✅ Active - Complete specification suite

### Known Gaps

**See [GAP_TRACKING.md](./GAP_TRACKING.md) for complete gap tracking.**

**Summary (38 total gaps):**
- 🔴 8 Critical - Must resolve before Jan 2026 field trial
- 🟡 12 High - Impacts validation or safety
- 🟢 13 Medium - Important for completeness
- ⚪ 5 Low - Documentation quality

---

## How to Use These Documents

### For Executives & Stakeholders:
- **Read:** PRD Executive Summary (Section 1)
- **Focus on:** Key metrics, development phases, business objectives

### For Product Managers:
- **Read:** Full PRD
- **Focus on:** Functional requirements, use cases, success metrics

### For Software Engineers:
- **Read:** TSD Sections 2, 4, 5, 6, 8
- **Focus on:** Software architecture, interfaces, algorithms

### For Hardware Engineers:
- **Read:** TSD Sections 2, 3, 7
- **Focus on:** Hardware specs, electrical interfaces, protocols

### For System Integrators:
- **Read:** TSD Sections 10, 11
- **Focus on:** Configuration, build procedures, deployment

### For QA Engineers:
- **Read:** PRD Section 8, TSD Section 12
- **Focus on:** Success metrics, test procedures, validation

### For Field Operators:
- **Read:** PRD Sections 6, TSD Section 14
- **Focus on:** Operational requirements, troubleshooting

### For Maintenance Personnel:
- **Read:** TSD Sections 9, 14, Appendix E
- **Focus on:** Safety systems, diagnostics, maintenance schedule

---

## Document Maintenance

### Review Schedule:
- **Monthly:** During active development
- **Quarterly:** During maintenance phase
- **After Major Milestones:** Field deployment, Phase 2 completion

### Update Process:
1. Identify outdated or incorrect information
2. Mark with ⚠️ or update directly
3. Update Document Control section (version, date, changes)
4. Get appropriate reviews/approvals
5. Distribute updated version

### Ownership:
- **PRD Owner:** Product Management Team
- **TSD Owner:** Engineering Team
- **Coordination:** Systems Engineering

---

## Related Documentation

- **Main Project README:** `../../README.md`
- **Documentation Index:** `../INDEX.md`
- **System Architecture:** `../architecture/SYSTEM_ARCHITECTURE.md`
- **ROS2 Interface Spec:** `../ROS2_INTERFACE_SPECIFICATION.md`
- **Hardware Test Checklist:** `../HARDWARE_TEST_CHECKLIST.md`
- **Package Documentation:** `../../src/*/README.md`

---

## Feedback & Contributions

All team members are encouraged to:
- Report inaccuracies or outdated information
- Propose improvements or clarifications
- Submit measurement data for ⚠️ marked items
- Contribute validation results

**Contact:** [Engineering Team Lead / Project Manager]

---

**Last Updated:** 2026-01-02  
**Document Version:** 1.1

---

## New Documents Added (January 2026)

| Document | Purpose | Lines |
|----------|---------|-------|
| VALIDATION_MATRIX.md | Requirement traceability | 204 |
| GAP_TRACKING.md | Gap consolidation | 207 |
| TEST_CASES.md | Formal test procedures | 580 |
| CONFIG_SCHEMAS.md | Configuration documentation | 374 |
| **Total new documentation** | - | **1,365 lines** |
