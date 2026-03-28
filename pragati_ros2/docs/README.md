# Pragati Production System Documentation

> **Purpose:** Modular technical reference for the Pragati cotton picking robot production system.  
> **Audience:** Developers, operators, and technical stakeholders.  
> **Quick Navigation:** See [INDEX.md](INDEX.md) for complete documentation map or [START_HERE.md](START_HERE.md) for onboarding.

**Version:** 4.2.0  
**Last Updated:** 2025-10-16  
**System Status:** Phase 1 Complete, Phase 2 In Development

---

## 📚 Documentation Structure

This documentation is organized into modular sections for easy navigation and maintenance. Choose the section relevant to your needs:

---

## 🚀 Quick Start

**New to the system?** Start here:

1. **[System Overview](production-system/01-SYSTEM_OVERVIEW.md)** - High-level architecture and current status
2. **[Operator Guide](production-system/09-OPERATOR_GUIDE.md)** - How to operate and maintain the system

---

## 🏗️ System Architecture

Understand the hardware and software architecture:

| Document | Description | Lines |
|----------|-------------|-------|
| **[01. System Overview](production-system/01-SYSTEM_OVERVIEW.md)** | High-level overview, status, Phase 1 vs Phase 2 comparison | ~100 |
| **[02. Hardware Architecture](production-system/02-HARDWARE_ARCHITECTURE.md)** | Physical layout, RPi network, motors, cameras, startup sequence | ~130 |
| **[03. Cotton Detection](production-system/03-COTTON_DETECTION.md)** | Detection workflow, multi-cotton detection, pickability classification | ~590 |

---

## 🔧 Technical Details

Deep dive into system components:

| Document | Description | Lines |
|----------|-------------|-------|
| **[06. Real-Time Control](production-system/06-REALTIME_CONTROL.md)** | Control loops, ROS2 topics/services, timing | ~140 |
| **[07. Safety Systems](production-system/07-SAFETY_SYSTEMS.md)** | Multi-layer safety architecture, error handling | ~122 |
| **[08. Configuration](production-system/08-CONFIGURATION.md)** | YAML configs, motor parameters, camera settings | ~91 |

---

## 👨‍💼 Operations & Maintenance

For operators and field technicians:

| Document | Description | Lines |
|----------|-------------|-------|
| **[09. Operator Guide](production-system/09-OPERATOR_GUIDE.md)** | Startup checklist, operation procedures, maintenance, troubleshooting | ~120 |

---

## 🚀 Future Enhancements

Roadmap and planned improvements:

| Document | Description | Status |
|----------|-------------|--------|
| **[Phase 2 Roadmap](enhancements/PHASE_2_ROADMAP.md)** | Migration plan from Phase 1 to Phase 2 production system | In Development |
| **Multi-Cotton Detection** | Detailed documentation on pickability classification | ✅ See [03. Cotton Detection](production-system/03-COTTON_DETECTION.md) |
| **Continuous Operation** | Future continuous picking while moving | Planned |
| **Autonomous Navigation** | Future autonomous vehicle control | Planned |

---

## 📊 Current System Status

### Phase 1: Stop-and-Go (CURRENT)
⚠️ **Status:** Working but NOT Production Ready

- **Operation Mode:** Stop-and-Go (vehicle stops before picking)
- **Camera Mode:** On-demand triggered capture
- **Vehicle Control:** Manual control only
- **Picking Strategy:** Multi-cotton detection with pickability classification ✅
- **Throughput:** ~600-900 picks/hour (with multi-cotton improvement)

**Achievements:**
- ✅ Multi-cotton detection implemented
- ✅ Pickability classification functional (PICKABLE vs NON_PICKABLE)
- ✅ Sequential picking of all pickable cottons per stop
- ✅ 3× throughput improvement over single-cotton approach

### Phase 2: Continuous Operation (TARGET)
🎯 **Status:** In Development

- **Operation Mode:** Continuous motion (pick while moving)
- **Camera Mode:** Continuous streaming at 30 Hz
- **Vehicle Control:** Autonomous with manual override
- **Picking Strategy:** Predictive positioning while moving
- **Target Throughput:** ~1,800-2,000 picks/hour (8-10× improvement)

**Timeline:** ~12 weeks (see [Phase 2 Roadmap](enhancements/PHASE_2_ROADMAP.md))

---

## 🔍 Quick Reference

### Key System Facts
- **Architecture:** 5 independent Raspberry Pi 4 (4 arms + 1 vehicle)
- **Motors:** 22 total (12 arm joints + 4 end effectors + 6 vehicle)
- **Cameras:** 4× Luxonis OAK-D Lite with Myriad X VPU
- **Communication:** MQTT for inter-RPi, ROS2 within each RPi
- **Power:** 48V for MG6010 motors, 6V/12V for end effectors

### Key Technologies
- **ROS2 Jazzy** - Distributed coordination
- **MG6010E-i6 Motors** - CAN bus controlled servos (500 kbps)
- **GM25-BK370 Motors** - End effector gear motors with Hall encoders
- **YOLOv8** - Cotton detection with pickability classification
- **DepthAI SDK** - On-camera inference (C++ integration)

### Performance Metrics (Phase 1)
- **Detection accuracy:** ~90% (target: >95%)
- **Pick cycle time:** ~2-3 seconds per cotton
- **Picks per stop:** 2-5 pickable cottons (average 4-8 detected)
- **Current throughput:** ~600-900 picks/hour

---

## 📖 Additional Documentation

### Component-Specific Docs
- **Motor Control:** `src/motor_control_ros2/README.md`
- **Cotton Detection:** `src/cotton_detection_ros2/README.md`
- **Vehicle Control:** `src/vehicle_control/README.md`
- **Yanthra Move (Arm Control):** `src/yanthra_move/README.md`

### Historical/Archive
- **Audit Reports:** `docs/archive/2025-10-audit/`
- **Archived Docs:** `docs/archive/`
- **Project Notes:** `docs/project-notes/`

---

## 🆘 Need Help?

### Quick Navigation by Role

**🔧 Developer/Engineer:**
- Start with [System Overview](production-system/01-SYSTEM_OVERVIEW.md)
- Deep dive into [Cotton Detection](production-system/03-COTTON_DETECTION.md) or [Real-Time Control](production-system/06-REALTIME_CONTROL.md)
- Check [Configuration](production-system/08-CONFIGURATION.md) for parameters

**👨‍💼 Operator/Technician:**
- Read [Operator Guide](production-system/09-OPERATOR_GUIDE.md) for daily operations
- Refer to [Hardware Architecture](production-system/02-HARDWARE_ARCHITECTURE.md) for physical system understanding

**📊 Manager/Stakeholder:**
- Review [System Overview](production-system/01-SYSTEM_OVERVIEW.md) for current status
- Check [Phase 2 Roadmap](enhancements/PHASE_2_ROADMAP.md) for future plans and timeline

**🐛 Troubleshooting:**
- See [Safety Systems](production-system/07-SAFETY_SYSTEMS.md) for error handling
- Check [Operator Guide](production-system/09-OPERATOR_GUIDE.md) maintenance section

---

## 📝 Version History

### Version 4.2.0 (2025-10-10) - Current
- ✨ Added multi-cotton detection capability
- ✨ Implemented pickability classification (PICKABLE/NON_PICKABLE)
- ✨ Sequential picking of all pickable cottons per stop
- ✨ Expected 3× throughput improvement
- ✨ Modular documentation structure
- 🔧 Fixed ODrive references (updated to MG6010)

### Version 4.1.0 (2025-10-09)
- Initial comprehensive production system documentation
- C++ DepthAI integration complete
- 4-arm architecture deployed
- Phase 1 system operational

---

## 🔗 External Resources

- **MG Motors Documentation:** `/home/uday/Downloads/MG_motors.pdf`
- **OAK-D Lite:** https://shop.luxonis.com/products/oak-d-lite-1
- **GM25-BK370 End Effector:** https://www.airsoftmotor.com/micro-dc-reduction-motor/circular-reduction-motor/gm25-bk370-hall-encoder-dc-gear-motor.html

---

**📍 Location:** `/home/uday/Downloads/pragati_ros2/docs/`  
**📧 For questions or updates, refer to project documentation or team leads.**
