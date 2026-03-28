# Pragati ROS2 Documentation Index

> **Purpose:** Central navigation hub for all active documentation in the pragati_ros2 project.  
> **Audience:** All team members - comprehensive document map and quick links.  
> **Use:** Find docs by purpose (status, guides, validation, archives).

**Last Updated:** 2026-01-02  
**Maintainers:** Systems & Documentation Team

> **🚨 FIELD TRIAL:** January 7-8, 2026 - See [Field Trial Section](#-field-trial-january-2026) below

---

## 🚨 Field Trial (January 2026)

| Document | Purpose |
|----------|---------|
| **[JANUARY_FIELD_TRIAL_PLAN_2026.md](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md)** | 🚨 Master plan, task status, blockers |
| [JANUARY_FIELD_TRIAL_TESTING_MATRIX.md](project-notes/JANUARY_FIELD_TRIAL_TESTING_MATRIX.md) | Test procedures for field |
| [RPI_INSTALLATION_VALIDATION_CHECKLIST.md](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md) | RPi deployment checklist |
| [DEPLOY_TO_RPI.md](project-notes/DEPLOY_TO_RPI.md) | Deployment procedures |

**Recent Updates (Dec 2025):**
- [QUEUE_SYNCHRONIZATION_FIX_2025-12-18.md](project-notes/QUEUE_SYNCHRONIZATION_FIX_2025-12-18.md)
- [LONG_RUN_TEST_ANALYSIS_2025-12-18.md](project-notes/LONG_RUN_TEST_ANALYSIS_2025-12-18.md)
- [VEHICLE_JOYSTICK_TO_MOTOR_COMMAND_FLOW_2025-12-19.md](project-notes/VEHICLE_JOYSTICK_TO_MOTOR_COMMAND_FLOW_2025-12-19.md)

---

## 🚀 Quick Links

| Purpose | Path |
|---------|------|
| **🚨 Field trial plan** | [`project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md`](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md) |
| Project overview & badges | [`../README.md`](../README.md) |
| Specifications (PRD/TSD) | [`specifications/README.md`](specifications/README.md) |
| Ground-truth status tracker | [`STATUS_REALITY_MATRIX.md`](STATUS_REALITY_MATRIX.md) |
| Hardware checklist | [`HARDWARE_TEST_CHECKLIST.md`](HARDWARE_TEST_CHECKLIST.md) |
| Cotton detection testing | [`guides/TESTING_AND_OFFLINE_OPERATION.md`](guides/TESTING_AND_OFFLINE_OPERATION.md) |
| Cotton detection integration | [`integration/COTTON_DETECTION_INTEGRATION_README.md`](integration/COTTON_DETECTION_INTEGRATION_README.md) |

---

## 📚 Status & Planning Docs

### Canonical Documents (Source of Truth)
- [`PRODUCTION_READINESS_GAP.md`](PRODUCTION_READINESS_GAP.md) — Production status and validation plan
- [`TODO_MASTER_CONSOLIDATED.md`](TODO_MASTER_CONSOLIDATED.md) — Active TODO list (103 items)
- [`CONSOLIDATED_ROADMAP.md`](CONSOLIDATED_ROADMAP.md) — Actionable work plan
- [`STATUS_REALITY_MATRIX.md`](STATUS_REALITY_MATRIX.md) — Evidence-based validation matrix

### Supporting Documents
- [`status/STATUS_TRACKER.md`](status/STATUS_TRACKER.md) — Project-wide status tracker
- [`guides/SYSTEM_MIGRATION.md`](guides/SYSTEM_MIGRATION.md) — Consolidated migration guide (OAK-D Lite, MG6010, Cotton Detection)
- [`DOCUMENTATION_ORGANIZATION.md`](DOCUMENTATION_ORGANIZATION.md) — Rules for creating/updating docs
- [`CONTRIBUTING_DOCS.md`](CONTRIBUTING_DOCS.md) — Documentation maintenance guidelines
- [`CLEANUP_PHASE2_SUMMARY.md`](CLEANUP_PHASE2_SUMMARY.md) — Phase 2 cleanup summary (Oct 15)

---

## 🛠️ Guides & How-Tos

### Cotton Detection Documentation ✨

**Production-Ready Guides (Updated Nov 4, 2025):**
- [`guides/TESTING_AND_OFFLINE_OPERATION.md`](guides/TESTING_AND_OFFLINE_OPERATION.md) — **NEW** Complete testing guide (offline, simulation, CI/CD)
- [`integration/COTTON_DETECTION_INTEGRATION_README.md`](integration/COTTON_DETECTION_INTEGRATION_README.md) — **UPDATED** ROS2 integration with 4 appendices
- [`guides/PERFORMANCE_OPTIMIZATION.md`](guides/PERFORMANCE_OPTIMIZATION.md) — **UPDATED** Memory optimization, thermal management (65.2°C)
- [`guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md`](guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md) — **NEW** OAK-D Lite setup, coordinates, troubleshooting

**Key Metrics (Validated Nov 1):**
- ✅ Detection: 70ms latency
- ✅ Service: 134ms latency
- ✅ Reliability: 100%
- ✅ RPi Build: 4m 33s (OOM fixed)
- ✅ Thermal: 65.2°C stable

### Core Guides
- [`guides/SYSTEM_MIGRATION.md`](guides/SYSTEM_MIGRATION.md) — Consolidated migration guide (OAK-D Lite camera, MG6010 motors, Cotton Detection topics)
- [`guides/CONTINUOUS_OPERATION_GUIDE.md`](guides/CONTINUOUS_OPERATION_GUIDE.md) — Configure continuous operation mode and troubleshooting

### Hardware & Setup
- [`guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md`](guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md) — **✨ NEW** OAK-D Lite complete guide (replaces CAMERA_INTEGRATION_GUIDE.md)
- [`guides/CAN_BUS_SETUP_GUIDE.md`](guides/CAN_BUS_SETUP_GUIDE.md) — CAN bus configuration for MG6010 motors
- [`guides/GPIO_SETUP_GUIDE.md`](guides/GPIO_SETUP_GUIDE.md) — GPIO wiring and configuration
- [`guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md`](guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md) — Deploy on Raspberry Pi
- [`guides/CALIBRATION_GUIDE.md`](guides/CALIBRATION_GUIDE.md) — Camera and system calibration
- [`guides/THREE_MOTOR_SETUP_GUIDE.md`](guides/THREE_MOTOR_SETUP_GUIDE.md) — Three-motor configuration
- [`guides/USB2_CONFIGURATION_GUIDE.md`](guides/USB2_CONFIGURATION_GUIDE.md) — USB2 mode configuration

### Development & Testing
- [`guides/BUILD_OPTIMIZATION_GUIDE.md`](guides/BUILD_OPTIMIZATION_GUIDE.md) — Speed up builds with ccache and parallel compilation
- [`guides/API_DOCUMENTATION_GUIDE.md`](guides/API_DOCUMENTATION_GUIDE.md) — Generate and browse API documentation
- [`guides/UNIT_TEST_GUIDE.md`](guides/UNIT_TEST_GUIDE.md) — Writing and running unit tests
- [`guides/SIMULATED_CAMERA_TESTING.md`](guides/SIMULATED_CAMERA_TESTING.md) — **✨ NEW** Test yanthra arm without camera hardware (simulation testing)
- [`guides/SIMULATED_CAMERA_TESTING_QUICKREF.md`](guides/SIMULATED_CAMERA_TESTING_QUICKREF.md) — **✨ NEW** Quick reference card for simulated testing
- [`guides/ERROR_HANDLING_GUIDE.md`](guides/ERROR_HANDLING_GUIDE.md) — Error handling patterns and auto-reconnect
- [`guides/FAQ.md`](guides/FAQ.md) — Frequently asked questions (40+ Q&A)
- [`guides/TROUBLESHOOTING.md`](guides/TROUBLESHOOTING.md) — General troubleshooting procedures

### Specific Features
- [`guides/MOTOR_TUNING_GUIDE.md`](guides/MOTOR_TUNING_GUIDE.md) — MG6010 PID tuning and optimization
- [`guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md`](guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md) — Safety monitor integration
- [`guides/SAFETY_MONITOR_EXPLANATION.md`](guides/SAFETY_MONITOR_EXPLANATION.md) — Safety monitor detailed explanation
- [`guides/START_SWITCH_TIMEOUT_GUIDE.md`](guides/START_SWITCH_TIMEOUT_GUIDE.md) — START_SWITCH timeout configuration
- [`guides/YOLO_MODELS.md`](guides/YOLO_MODELS.md) — YOLO model configuration and usage
- [`guides/CPP_USAGE_GUIDE.md`](guides/CPP_USAGE_GUIDE.md) — C++ node usage guide
- [`guides/CPP_VS_PYTHON_RECOMMENDATION.md`](guides/CPP_VS_PYTHON_RECOMMENDATION.md) — When to use C++ vs Python

### System Administration
- [`guides/SYSTEM_LAUNCH_GUIDE.md`](guides/SYSTEM_LAUNCH_GUIDE.md) — System launch procedures
- [`guides/SCRIPTS_GUIDE.md`](guides/SCRIPTS_GUIDE.md) — Available scripts and utilities
- [`guides/AUTOMATION_SETUP.md`](guides/AUTOMATION_SETUP.md) — Automation configuration
- [`guides/TABLE_TOP_VALIDATION_GUIDE.md`](guides/TABLE_TOP_VALIDATION_GUIDE.md) — Benchtop validation procedures
- [`guides/QUICK_REFERENCE.md`](guides/QUICK_REFERENCE.md) — Quick command reference

---

## ✅ Validation & Evidence

- [`validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md`](validation/COMPREHENSIVE_SYSTEM_VALIDATION_REPORT.md) — Consolidated software test results + Oct 7 hardware notes.
- [`validation/HARDWARE_TEST_RESULTS.md`](validation/HARDWARE_TEST_RESULTS.md) — Historical bench outcomes (needs refresh after next lab window).
- [`TESTING_AND_VALIDATION_PLAN.md`](TESTING_AND_VALIDATION_PLAN.md) — What to run before production sign-off.
- [`guides/MOTOR_TUNING_GUIDE.md`](guides/MOTOR_TUNING_GUIDE.md) — MG6010 motor tuning guide (for hardware validation)

Remember to drop new logs under `test_output/integration/` and link them here when available.

---

## 🗃️ Archives & Evidence

**See [`archive/INDEX.md`](archive/INDEX.md) for complete archive navigation**

### Recent Archives (October 2025)

**Phase 2 Cleanup (Oct 15, 2025)** — 41 historical docs archived:
- [`archive/2025-10/consolidation-meta/`](archive/2025-10/consolidation-meta/) — Phase 1 consolidation planning docs
- [`archive/2025-10/completion-reports/`](archive/2025-10/completion-reports/) — Historical completion summaries  
- [`archive/2025-10/session-summaries/`](archive/2025-10/session-summaries/) — Session notes
- [`archive/2025-10/execution-plans/`](archive/2025-10/execution-plans/) — Superseded execution plans
- [`archive/2025-10/stakeholder-docs/`](archive/2025-10/stakeholder-docs/) — One-time notifications
- [`archive/2025-10/superseded/`](archive/2025-10/superseded/) — Replaced by newer versions (TODO_CONSOLIDATED, ODrive motor guide)
- [`archive/2025-10/generated-reports/`](archive/2025-10/generated-reports/) — Oct 14-15 audit reports (from _generated/)

**Phase 1 Consolidation (Oct 15, 2025)** — 34 package docs archived:
- [`archive/2025-10/motor_control/`](archive/2025-10/motor_control/) — 19 motor control docs (merged into package README)
- [`archive/2025-10/cotton_detection/`](archive/2025-10/cotton_detection/) — Migration guide (merged)
- [`archive/2025-10/yanthra_move/`](archive/2025-10/yanthra_move/) — Meta cleanup docs
- [`archive/2025-10/phase-completion/`](archive/2025-10/phase-completion/) — Phase completion reports
- [`archive/2025-10/tier-completion/`](archive/2025-10/tier-completion/) — Tier completion reports

**Other Archives:**
- `archive/2025-10-audit/` — Audit materials (Oct 7, Oct 14)
- `archive/2025-10-analysis/` — Deep dive code reviews & ROS1 vs ROS2 comparison
- `archive/2025-10-test-results/` — Hardware test results
- `archive/2025-10-validation/` — Validation reports
- `evidence/2025-10-15/` — Implementation evidence (Safety Monitor completion)

---

## 🧭 Using This Index

1. Start with **`STATUS_REALITY_MATRIX.md`** for up-to-date truths and outstanding actions.
2. Consult the **Quick Links** table based on what you need (simulation vs. hardware).
3. When updating documentation, follow the rules in **`DOCUMENTATION_ORGANIZATION.md`** and update this index accordingly.
4. Archive stale material via the workflow in **`guides/CLEANUP_AND_MAINTENANCE_PLAN.md`**.
5. For historical documents, see **[`archive/INDEX.md`](archive/INDEX.md)**.

**Active Docs:** ~150 markdown files (non-archive)  
**Archived:** 200+ files in `archive/` (100% content preserved)  
**Latest Cleanup:** Nov 27, 2025 - Documentation reorganized, broken links fixed
