> **Archived:** 2025-10-21
> **Reason:** Will consolidate into migration guide

# ODrive to MG6010-i6 Migration Guide

**Date:** 2024-10-09  
**Status:** Reference Document  
**Migration Status:** ✅ Complete (MG6010-i6 is now primary)

---

## Overview

This guide documents the migration from ODrive motor controllers to MG6010-i6 integrated servo motors for the Pragati cotton picking robot. This migration was completed in October 2024.

---

## Why We Migrated

### Problems with ODrive:
1. **External controller required** - Separate motor controller unit
2. **Complex wiring** - Motor, encoder, and controller all separate
3. **Higher cost** - Controller + motor + encoder
4. **Larger footprint** - Multiple components
5. **More failure points** - Each component can fail independently

### Benefits of MG6010-i6:
1. ✅ **Integrated servo** - Motor + encoder + driver in one unit
2. ✅ **Simpler wiring** - Just power and CAN bus
3. ✅ **Lower cost** - All-in-one solution
4. ✅ **Compact design** - Single unit installation
5. ✅ **Fewer failure points** - Single integrated system
6. ✅ **Proven in agriculture** - Colleague's successful implementation
7. ✅ **Better for field conditions** - Sealed integrated unit

---

## Key Differences

### Communication Protocol

| Aspect | ODrive | MG6010-i6 |
|--------|--------|-----------|
| **Protocol** | CANopen (variant) | LK-TECH Proprietary |
| **Default Bitrate** | 1Mbps | 250kbps |
| **CAN ID** | Configurable | 0x140 + motor_id (1-32) |
| **Response Time** | ~1-5ms | <0.25ms typical |
| **Protocol Complexity** | CANopen SDO/PDO | Simple command/response |

### Hardware Specifications

| Spec | ODrive S1 | MG6010-i6 |
|------|-----------|-----------|
| **Type** | External controller | Integrated servo |
| **Voltage** | 12-48V | 7.4-32V (24V nominal) |
| **Max Current** | 120A peak | 33A max (MG series) |
| **Torque** | Motor-dependent | 10 N.m max |
| **Encoder** | External (hall/abs) | 18-bit integrated |
| **Gear Ratio** | External | 6:1 integrated (i6 model) |
| **Size** | Controller + Motor | Single integrated unit |
| **Wiring** | 3-phase + encoder + CAN | Power + CAN (2-wire) |

### Cost Comparison

| Component | ODrive | MG6010-i6 |
|-----------|--------|-----------|
| Motor | ~$200 | Included |
| Encoder | ~$100 | Included |
| Controller | ~$300 | Included |
| **Total** | **~$600** | **~$300** |
| **Savings** | - | **50%** |

---

## Migration Process

### Step 1: Hardware Replacement

**ODrive Setup (OLD):**
```
[Motor] --3-phase--> [ODrive Controller] --CAN--> [ROS2]
   ^
   |
[Encoder]
```

**MG6010-i6 Setup (NEW):**
```
[MG6010-i6 Integrated Servo] --CAN--> [ROS2]
  (motor + encoder + driver all-in-one)
```

### Step 2: Wiring Changes

**ODrive (OLD):**
- 3-phase motor wires (3 wires)
- Encoder wires (4-8 wires depending on type)
- CAN H/L (2 wires)
- Power to controller (2 wires)
- Power to motor (from controller)

**MG6010-i6 (NEW):**
- CAN H/L (2 wires)
- Power (+24V, GND) (2 wires)
- **Total: 4 wires**

### Step 3: CAN Bus Configuration

**ODrive:**
```bash
# Typically 1Mbps
sudo ip link set can0 type can bitrate 1000000
```

**MG6010-i6:**
```bash
# Standard 250kbps
sudo ip link set can0 type can bitrate 250000
sudo ip link set can0 up
```

### Step 4: Software Changes

**No application code changes required!**

The motor_control_ros2 package provides a unified MotorControllerInterface that abstracts the differences. Simply change the motor type in configuration:

**OLD Config (`production.yaml`):**
```yaml
motors:
  base_rotation:
    type: odrive
    can_id: 1
```

**NEW Config (`production.yaml`):**
```yaml
motors:
  base_rotation:
    type: mg6010
    can_id: 1  # Will use 0x141 (0x140 + 1)
```

---

## Configuration Migration

### Motor Parameters

**ODrive Parameters:**
```yaml
motors:
  joint_name: base_rotation
  type: odrive
  can_id: 1
  encoder_cpr: 8192
  pole_pairs: 7
  current_limit: 40.0
  velocity_limit: 10.0
  p_gain: 20.0
  v_gain: 0.5
  v_int_gain: 0.1
```

**MG6010-i6 Equivalent:**
```yaml
motors:
  joint_name: base_rotation
  type: mg6010
  can_id: 1
  # Encoder integrated (18-bit, 262144 counts/rev)
  # Gear ratio: 6:1 (i6 model)
  current_limit: 15.0  # MG series max: 33A, recommended: 15A
  velocity_limit: 5.0  # rad/s
  p_gain: 50  # uint8_t (MG protocol uses integers)
  v_gain: 20  # uint8_t
  v_int_gain: 0  # Not commonly used with MG6010
```

**Key Differences:**
- MG6010 encoder is fixed (18-bit, integrated)
- Gear ratio is fixed by model (i6 = 6:1)
- PID gains are uint8_t (0-255), not floating point
- Lower current limits (15A typical vs 40A ODrive)

---

## Testing After Migration

### 1. CAN Communication Test
```bash
# Start test node
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status

# Expected output:
# ✅ CAN connection established
# ✅ Motor ON command sent successfully
# ✅ Motor status: temp, voltage, error flags
```

### 2. Position Control Test
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=position

# Motor should move through test positions
```

### 3. Full Robot Test
```bash
# Launch full robot control
ros2 launch pragati_complete.launch.py

# Test arm movements
ros2 service call /yanthra_move/move_arm ...
```

---

## Troubleshooting Migration Issues

### Issue: Motor not responding

**Possible Causes:**
1. Wrong CAN bitrate (use 250kbps for MG6010)
2. Wrong CAN ID (0x140 + motor_id, not raw ID)
3. CAN bus not terminated (needs 120Ω resistors)
4. Motor power not connected (24V)

**Solution:**
```bash
# Check CAN interface
ip -details link show can0
# Should show: bitrate 250000

# Monitor CAN traffic
candump can0
# Should see frames with ID 0x141, 0x142, etc.

# Check motor power
# Voltage should be 22-28V for 24V nominal
```

### Issue: Position not accurate

**Possible Causes:**
1. Encoder offset not calibrated
2. Wrong gear ratio in config
3. Direction inverted

**Solution:**
```yaml
# Update config
motors:
  direction: -1  # Try inverting if backwards
  transmission_factor: 6.0  # i6 model = 6:1
  encoder_offset: 0.0  # Adjust after calibration
```

### Issue: Motor stops with errors

**Check error flags:**
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status

# Look for error_flags in output
# 0x01: Voltage error
# 0x08: Temperature error
```

**Solutions:**
- Voltage error: Check power supply (should be 22-28V)
- Temperature error: Check cooling, reduce current limit

---

## Code Changes Summary

### Files Modified for Migration:
1. **Created:**
   - `src/mg6010_protocol.cpp/hpp` - MG6010 protocol implementation
   - `src/mg6010_controller.cpp/hpp` - MG6010 motor controller
   - `src/mg6010_can_interface.cpp/hpp` - CAN interface for MG6010
   - `launch/mg6010_test.launch.py` - Test launch file
   - `config/mg6010_test.yaml` - Test configuration

2. **Modified:**
   - `src/generic_motor_controller.cpp` - Added MG6010 support
   - `include/motor_abstraction.hpp` - Added MG6010 enum
   - `config/production.yaml` - Changed motor type to mg6010

3. **Unchanged:**
   - Application code (yanthra_move, vehicle_control, etc.)
   - ROS2 interfaces (topics, services, actions)
   - Launch file structure
   - Parameter system

**Migration was largely additive, not destructive!**

---

## Backwards Compatibility

### ODrive Support Status: LEGACY

ODrive support is **maintained but not actively developed**:
- ✅ Code still present
- ✅ Can be enabled via configuration
- ⚠️ Marked as legacy throughout
- ⚠️ No new features planned
- ℹ️ Bug fixes only if critical

### How to Use ODrive (if needed)

```yaml
# Just change motor type back to odrive
motors:
  type: odrive  # Instead of mg6010
  can_id: 1
```

**Warning:** ODrive code has not been actively tested since migration. Use at your own risk.

---

## Performance Comparison

### Communication Performance

| Metric | ODrive | MG6010-i6 | Winner |
|--------|--------|-----------|--------|
| Response Time | 1-5ms | <0.25ms | ✅ MG6010 |
| Command Rate | 100 Hz | 100+ Hz | ✅ MG6010 |
| Protocol Overhead | High (CANopen) | Low (proprietary) | ✅ MG6010 |
| Error Recovery | Moderate | Fast | ✅ MG6010 |

### Practical Performance

| Aspect | ODrive | MG6010-i6 | Winner |
|--------|--------|-----------|--------|
| Setup Time | 2-3 hours | 30 minutes | ✅ MG6010 |
| Wiring Complexity | High (many wires) | Low (4 wires) | ✅ MG6010 |
| Troubleshooting | Complex | Simple | ✅ MG6010 |
| Field Reliability | Good | Excellent | ✅ MG6010 |
| Maintenance | Moderate | Low | ✅ MG6010 |

---

## Lessons Learned

### What Went Well:
1. ✅ Abstraction layer made migration smooth
2. ✅ Colleague's proven implementation provided confidence
3. ✅ Integrated servo simplified hardware dramatically
4. ✅ Cost savings exceeded expectations
5. ✅ Agricultural reliability improved

### Challenges Faced:
1. ⚠️ Initial bitrate mismatch (1Mbps vs 250kbps) - Fixed in audit
2. ⚠️ Protocol documentation in Chinese - Solved with colleague's code
3. ⚠️ Integer PID values different from ODrive floats - Documented
4. ℹ️ Motor response time so fast it required code adjustments

### Recommendations for Future:
1. **Start with 250kbps** for MG6010-i6 (don't use 1Mbps)
2. **Use colleague's proven parameters** as baseline
3. **Test each motor individually** before full integration
4. **Monitor temperature** during initial testing
5. **Keep ODrive code** as reference but mark as legacy

---

## Documentation References

### MG6010-i6 Documentation:
- **Main README:** `src/motor_control_ros2/README.md` (consolidated authoritative source)
- **Archived Details:** `docs/archive/2025-10/motor_control/` (pre-consolidation docs)
  - MG6010_README.md - Getting started guide
  - MG6010_PROTOCOL_COMPARISON.md - Protocol details
  - MOTOR_CONTROL_STATUS.md - System status
- **Testing:** `docs/archive/2025-10-audit/2025-10-14/QUICK_TEST_GUIDE.md`

### Migration Audit:
- **Bitrate Audit:** `docs/archive/2025-10-audit/2025-10-14/CAN_BITRATE_AUDIT_REPORT.md`
- **Legacy Audit:** `docs/archive/2025-10-audit/2025-10-14/ODRIVE_LEGACY_AUDIT.md`
- **Fixes:** `docs/CRITICAL_PRIORITY_FIXES_STATUS.md`

### ODrive Legacy Documentation:
- **Archive:** `docs/archive/odrive/` (if needed)
- **Legacy Code:** Still in `src/` but conditional

---

## Migration Checklist

### Pre-Migration:
- [ ] Review MG6010-i6 specifications
- [ ] Order motors (correct model: MG6010E-i6)
- [ ] Order CAN interface (if not present)
- [ ] Review wiring requirements
- [ ] Backup current ODrive configuration

### Hardware:
- [ ] Install MG6010-i6 motors
- [ ] Wire power (24V)
- [ ] Wire CAN bus (H, L, GND)
- [ ] Add 120Ω termination resistors
- [ ] Verify CAN bus connectivity

### Software:
- [ ] Update motor type in config files
- [ ] Set CAN bitrate to 250kbps
- [ ] Update motor IDs (0x140 + id)
- [ ] Adjust PID parameters (integers)
- [ ] Update current/velocity limits

### Testing:
- [ ] CAN communication test
- [ ] Motor ON/OFF test
- [ ] Status reading test
- [ ] Position control test
- [ ] Velocity control test
- [ ] Full robot integration test

### Documentation:
- [ ] Update robot documentation
- [ ] Record motor serial numbers
- [ ] Document calibration offsets
- [ ] Update maintenance procedures

---

## Support

### For MG6010-i6 Issues:
- See: `src/motor_control_ros2/README.md` (section 8: Troubleshooting)
- Archive: `docs/archive/2025-10/motor_control/` (detailed historical docs)
- Review: `docs/CRITICAL_PRIORITY_FIXES_STATUS.md`

### For Legacy ODrive:
- Refer to archived documentation
- ODrive support is best-effort only
- Consider migrating to MG6010-i6

---

## Conclusion

The migration from ODrive to MG6010-i6 was **highly successful**:
- ✅ **50% cost savings**
- ✅ **Dramatically simplified hardware**
- ✅ **Improved reliability**
- ✅ **Faster response times**
- ✅ **Easier maintenance**

**Recommendation:** MG6010-i6 is now the **standard** for Pragati robot motors. ODrive should only be used for legacy support or specific requirements.

---

**Migration Completed:** October 2024  
**Current Status:** MG6010-i6 Primary, ODrive Legacy  
**Document Version:** 1.0  
**Last Updated:** 2024-10-09
