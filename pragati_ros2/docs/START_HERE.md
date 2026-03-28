# Pragati ROS2 Documentation - Start Here 🚀

> **Purpose:** New user onboarding guide - quick answers to "What do I need?" and "Where should I start?"  
> **Audience:** New team members, stakeholders, and anyone needing quick context.  
> **Next Steps:** After reading, use [INDEX.md](INDEX.md) for detailed navigation or [README.md](README.md) for technical reference.

**Last Updated:** 2026-01-02  
**Status:** 🚨 **FIELD TRIAL PREP** - January 7-8, 2026  
**Critical Doc:** [`project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md`](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md)  
**Contributing:** See [CONTRIBUTING_DOCS.md](CONTRIBUTING_DOCS.md) for documentation maintenance guidelines

---

## 🚨 FIELD TRIAL: January 7-8, 2026

### Primary Planning Document
**Read:** [`project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md`](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md)

**Current Status (Dec 29):**
- ✅ YOLOv11 timing issue RESOLVED
- ✅ Camera USB 3.0 FIXED (two boards working)
- ✅ Long-Run Test #1 PASSED (5+ hours, 966 cycles)
- ⚠️ Vehicle: 2 working drive motors (degraded mode)
- 🔴 2-arm integration testing (Dec 29-30)

### Field Trial Docs
| Document | Purpose |
|----------|---------|
| [JANUARY_FIELD_TRIAL_PLAN_2026.md](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md) | Master plan, task status, blockers |
| [JANUARY_FIELD_TRIAL_TESTING_MATRIX.md](project-notes/JANUARY_FIELD_TRIAL_TESTING_MATRIX.md) | Test procedures for field |
| [RPI_INSTALLATION_VALIDATION_CHECKLIST.md](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md) | RPi deployment checklist |
| [DEPLOY_TO_RPI.md](project-notes/DEPLOY_TO_RPI.md) | Deployment procedures |

---

## 🎯 Quick Answer: What Do I Need?

### "I need field trial status" 🚨

**Read:** [`project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md`](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md)

**Configuration:** 2 arms + 3-wheel vehicle (2 working drive motors)

### "I need to deploy to RPi" 🧰

**Read:** [`project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md`](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md)

### "I need specs/requirements" 📝

**Read:** [`specifications/README.md`](specifications/README.md)
- PRD, TSD, Validation Matrix, Gap Tracking, Test Cases

### "I need cotton detection docs" 📷

**Quick Links:**
- [Testing & Offline Operation](guides/TESTING_AND_OFFLINE_OPERATION.md)
- [Integration Guide](integration/COTTON_DETECTION_INTEGRATION_README.md)
- [Performance Optimization](guides/PERFORMANCE_OPTIMIZATION.md)
- [Camera Setup](guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md)

**Key Metrics (Validated):**
- ✅ 70ms detection latency (RPi + OAK-D Lite)
- ✅ 65.2°C thermal (stable)
- ✅ 100% reliability (10/10 tests)

---

## 📚 Key Documents

### Field Trial (Jan 2026)
- [JANUARY_FIELD_TRIAL_PLAN_2026.md](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md) - **Master plan**
- [JANUARY_FIELD_TRIAL_TESTING_MATRIX.md](project-notes/JANUARY_FIELD_TRIAL_TESTING_MATRIX.md) - Test procedures

### Specifications
- [specifications/README.md](specifications/README.md) - PRD, TSD, Validation Matrix

### Deployment
- [RPI_INSTALLATION_VALIDATION_CHECKLIST.md](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md)
- [DEPLOY_TO_RPI.md](project-notes/DEPLOY_TO_RPI.md)

### Recent Updates (Dec 2025)
- [QUEUE_SYNCHRONIZATION_FIX_2025-12-18.md](project-notes/QUEUE_SYNCHRONIZATION_FIX_2025-12-18.md)
- [LONG_RUN_TEST_ANALYSIS_2025-12-18.md](project-notes/LONG_RUN_TEST_ANALYSIS_2025-12-18.md)
- [VEHICLE_JOYSTICK_TO_MOTOR_COMMAND_FLOW_2025-12-19.md](project-notes/VEHICLE_JOYSTICK_TO_MOTOR_COMMAND_FLOW_2025-12-19.md)

---

## ❓ FAQ

**Q: Where is the field trial plan?**  
A: [`project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md`](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md)

**Q: How do I deploy to RPi?**  
A: See [`project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md`](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md)

**Q: Where are the specs (PRD/TSD)?**  
A: [`specifications/README.md`](specifications/README.md)

**Q: Is the system validated?**  
A: Yes - see [JANUARY_FIELD_TRIAL_PLAN_2026.md](project-notes/JANUARY_FIELD_TRIAL_PLAN_2026.md) Section "Current Status" for latest.

---

**Document Version:** 3.0  
**Last Updated:** 2026-01-02  
**Status:** 🚨 Field Trial Prep (Jan 7-8, 2026)
