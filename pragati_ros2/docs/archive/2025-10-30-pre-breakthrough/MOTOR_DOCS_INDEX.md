# Motor Control Documentation Index

**Purpose:** Central navigation for all motor control documentation  
**Last Updated:** 2025-10-28  
**System:** MG6010-i6 motors with CAN bus @ 250 kbps

---

## 🚀 Quick Start

| Need | Document | Time |
|------|----------|------|
| **Quick test motor** | [docs/guides/MOTOR_TEST_QUICK_REF.md](docs/guides/MOTOR_TEST_QUICK_REF.md) | 5 min |
| **Understand calculations** | [docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md](docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md) | 15 min |
| **Full test guide** | [docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md](docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md) | 30 min |
| **Debug motors** | [docs/guides/MOTOR_DEBUG.md](docs/guides/MOTOR_DEBUG.md) | 10 min |

---

## 📚 Complete Documentation

### Core Guides (Read These First)

1. **[MOTOR_CALCULATION_COMPREHENSIVE.md](docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md)** ⭐ NEW
   - Complete calculation flow reference
   - Consolidates all motor calculation docs
   - Step-by-step examples with real numbers
   - Before/after fix comparison
   - **Status:** ✅ Consolidated and authoritative
   - **Lines:** 347

2. **[MOTOR_CONTROLLER_TEST_GUIDE.md](docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md)**
   - Complete test procedures
   - 4-terminal setup
   - Integration with yanthra_move
   - Success criteria
   - **Lines:** 361

3. **[MOTOR_TEST_QUICK_REF.md](docs/guides/MOTOR_TEST_QUICK_REF.md)**
   - Quick 4-terminal test procedure
   - Essential commands only
   - Validation checklist
   - **Lines:** 158

### Understanding Motor Behavior

4. **[MOTOR_INITIALIZATION_EXPLAINED.md](docs/guides/MOTOR_INITIALIZATION_EXPLAINED.md)**
   - Automatic homing sequence
   - Physical motor movement during init
   - Expected logs
   - Troubleshooting
   - **Lines:** 211

5. **[MOTOR_DEBUG.md](docs/guides/MOTOR_DEBUG.md)**
   - Motors 2 & 3 not responding
   - Lambda capture issue
   - Diagnostic commands
   - Hardware checks
   - **Lines:** 205

### Configuration & Fixes

6. **[TRANSMISSION_FACTOR_FIX.md](docs/guides/TRANSMISSION_FACTOR_FIX.md)**
   - Summary of the transmission factor fix
   - Before/after comparison
   - Motor movement reduction (23-38×)
   - Quick reference
   - **Lines:** 135

7. **[FINAL_MOTOR_FLOW_CORRECTED.md](docs/archive/2025-10-28/FINAL_MOTOR_FLOW_CORRECTED.md)** 
   - Your desired flow (now implemented)
   - Changes made to fix vigorous movements
   - Complete data flow
   - **Status:** ⚠️ Superseded by MOTOR_CALCULATION_COMPREHENSIVE.md (Archived)
   - **Lines:** 170

8. **[MOTOR_CALCULATION_FLOW.md](docs/archive/2025-10-28/MOTOR_CALCULATION_FLOW.md)**
   - Original calculation flow documentation
   - Real numbers with examples
   - **Status:** ⚠️ Superseded by MOTOR_CALCULATION_COMPREHENSIVE.md (Archived)
   - **Lines:** 302

---

## 🎯 Documentation by Use Case

### "Motors are moving too much / erratically"
→ Read: [TRANSMISSION_FACTOR_FIX.md](docs/guides/TRANSMISSION_FACTOR_FIX.md)  
→ Then: [MOTOR_CALCULATION_COMPREHENSIVE.md](docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md)

### "I need to test motors without camera"
→ Read: [MOTOR_TEST_QUICK_REF.md](docs/guides/MOTOR_TEST_QUICK_REF.md)  
→ Full guide: [MOTOR_CONTROLLER_TEST_GUIDE.md](docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md)

### "Motors 2 & 3 not responding"
→ Read: [MOTOR_DEBUG.md](docs/guides/MOTOR_DEBUG.md)

### "I need to understand how calculations work"
→ Read: [MOTOR_CALCULATION_COMPREHENSIVE.md](docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md) ⭐

### "What happens during motor initialization?"
→ Read: [MOTOR_INITIALIZATION_EXPLAINED.md](docs/guides/MOTOR_INITIALIZATION_EXPLAINED.md)

---

## 📦 Package-Specific Documentation

### src/motor_control_ros2/
- **[README.md](src/motor_control_ros2/README.md)** - Package overview, status, features
- **[docs/MG6010_INDEX.md](src/motor_control_ros2/docs/MG6010_INDEX.md)** - MG6010 integration docs
- **[docs/MG6010_INTEGRATION_COMPLETE.md](src/motor_control_ros2/docs/MG6010_MG6010_INTEGRATION_COMPLETE.md)** - Integration completion report

### Configuration Files
- `src/motor_control_ros2/config/mg6010_three_motors.yaml` - 3-motor configuration
- `src/motor_control_ros2/config/mg6010_test.yaml` - Single motor test config

---

## 🔧 Quick Commands Reference

### Test Single Motor
```bash
ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p mode:=status -p motor_id:=1
```

### Test 3 Motors (with homing)
```bash
ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args --params-file src/motor_control_ros2/config/mg6010_three_motors.yaml
```

### Monitor Joint States
```bash
ros2 topic echo /joint_states
```

### Send Position Command
```bash
ros2 topic pub -1 /joint3_position_controller/command \
  std_msgs/msg/Float64 '{data: 0.5}'
```

### Emergency Stop
```bash
./emergency_motor_stop.sh
```

---

## 🔍 Key Configuration Values

### Current Configuration (CORRECT)
```yaml
motor_ids: [1, 2, 3]
joint_names: [joint3, joint4, joint5]
transmission_factors: [6.0, 12.7, 12.7]  # ✅ Correct
directions: [1, 1, 1]
homing_positions: [180.0, 360.0, 360.0]  # ✅ Output angles
```

### CAN Interface
- **Bitrate:** 250 kbps (250000)
- **Interface:** can0
- **Protocol:** MG6010 CAN protocol

---

## 📊 Documentation Status

| Document | Status | Superseded By | Action |
|----------|--------|---------------|--------|
| MOTOR_CALCULATION_COMPREHENSIVE.md | ✅ Active | - | Use this |
| MOTOR_CONTROLLER_TEST_GUIDE.md | ✅ Active | - | Use this |
| MOTOR_TEST_QUICK_REF.md | ✅ Active | - | Use this |
| MOTOR_INITIALIZATION_EXPLAINED.md | ✅ Active | - | Use this |
| MOTOR_DEBUG.md | ✅ Active | - | Use this |
| TRANSMISSION_FACTOR_FIX.md | ✅ Active | - | Use this |
| FINAL_MOTOR_FLOW_CORRECTED.md | ⚠️ Superseded | MOTOR_CALCULATION_COMPREHENSIVE.md | Archive |
| MOTOR_CALCULATION_FLOW.md | ⚠️ Superseded | MOTOR_CALCULATION_COMPREHENSIVE.md | Archive |

---

## 🎓 Learning Path

### Beginner (New to System)
1. Read [MOTOR_TEST_QUICK_REF.md](docs/guides/MOTOR_TEST_QUICK_REF.md)
2. Run quick test procedure
3. Understand [MOTOR_INITIALIZATION_EXPLAINED.md](docs/guides/MOTOR_INITIALIZATION_EXPLAINED.md)

### Intermediate (Understanding System)
1. Read [MOTOR_CALCULATION_COMPREHENSIVE.md](docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md)
2. Review [TRANSMISSION_FACTOR_FIX.md](docs/guides/TRANSMISSION_FACTOR_FIX.md)
3. Study [MOTOR_CONTROLLER_TEST_GUIDE.md](docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md)

### Advanced (Debugging/Tuning)
1. Read [MOTOR_DEBUG.md](docs/guides/MOTOR_DEBUG.md)
2. Review package [README.md](src/motor_control_ros2/README.md)
3. Study MG6010 protocol implementation in code

---

## 🛠️ Troubleshooting Index

| Symptom | Document | Section |
|---------|----------|---------|
| Vigorous movements | MOTOR_CALCULATION_COMPREHENSIVE.md | § Troubleshooting |
| Motors don't move | MOTOR_DEBUG.md | § Testing Steps |
| Wrong direction | MOTOR_CALCULATION_COMPREHENSIVE.md | § Troubleshooting |
| Motors 2 & 3 fail | MOTOR_DEBUG.md | § Lambda Capture Issue |
| Homing fails | MOTOR_INITIALIZATION_EXPLAINED.md | § Troubleshooting |
| CAN errors | MOTOR_DEBUG.md | § CAN Communication Issue |

---

## 📞 Additional Resources

### Related Documentation
- [EMERGENCY_STOP_README.md](EMERGENCY_STOP_README.md) - Emergency shutdown procedures
- [TEST_WITHOUT_CAMERA.md](TEST_WITHOUT_CAMERA.md) - System testing without camera
- [docs/guides/MOTOR_TUNING_GUIDE.md](docs/guides/MOTOR_TUNING_GUIDE.md) - PID tuning
- [docs/guides/THREE_MOTOR_SETUP_GUIDE.md](docs/guides/THREE_MOTOR_SETUP_GUIDE.md) - Multi-motor setup

### Archive
- [docs/archive/2025-10/motor_control/](docs/archive/2025-10/motor_control/) - Archived motor docs (18 files)

---

## ✅ Documentation Maintenance

**Last Consolidation:** 2025-10-28  
**Superseded Docs:** 2 files (marked above)  
**Active Docs:** 6 core + 3 supplementary  
**Archive Status:** Legacy docs preserved in archive/

**Next Review:** After next hardware validation session

---

**Created:** 2025-10-28  
**Maintainer:** Documentation Team  
**Status:** ✅ Complete and up-to-date
