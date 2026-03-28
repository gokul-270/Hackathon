# Error Handling Guide - Hardware Failures

## Quick Answers

### 1. DepthAI Camera Errors (Camera Not Connected)
**Question**: Are DepthAI errors OK when camera is not connected?

**Answer**: ✅ **YES** - It depends on the mode:

| Mode | Camera Required? | Should Continue? |
|------|------------------|------------------|
| **Simulation mode** | ❌ No | ✅ YES - Continue with simulated data |
| **ArUco calibration** | ✅ Yes | ❌ NO - Cannot calibrate without camera |
| **Production (cotton picking)** | ✅ Yes | ❌ NO - Cannot detect cotton |

**Current Behavior**:
- System logs warning: `DepthAI camera initialization failed`
- Continues if `simulation_mode: true` in config
- **Should gracefully degrade** instead of crashing

**Recommendation**: Add graceful degradation
```yaml
# In production.yaml
enable_camera: true       # Try to use camera
simulation_mode: false    # Use real hardware

# System should:
# 1. Try to initialize camera
# 2. If fails and simulation_mode=false → ERROR and stop
# 3. If fails and simulation_mode=true → WARN and continue with simulation
```

---

### 2. Motor Communication Failures (Hardware Mode)
**Question**: If motors fail in hardware mode, should we continue?

**Answer**: ❌ **NO** - System should **STOP IMMEDIATELY**

**Reason**: Safety critical!
- Cannot move arm safely without motor control
- Could cause physical damage
- Could cause injury
- Invalid sensor data without real movement

**Current Behavior**: System should detect motor failures during:
1. **Startup homing** - Stop if homing fails
2. **Motion commands** - Stop if motor doesn't respond
3. **Position feedback** - Warn if feedback missing (but may continue)

**Recommendation**: Implement strict checks
```cpp
// In motion_controller.cpp
if (!joint_move_5_->move_joint(position, true)) {
    RCLCPP_ERROR(node_->get_logger(), "❌ CRITICAL: Motor 5 failed to respond!");
    requestEmergencyStop();
    return false;  // Stop immediately
}
```

---

### 3. Camera Not Connected (Online/Production Mode)
**Question**: If camera isn't connected when running online, should it continue?

**Answer**: ❌ **NO** - System should **STOP with clear error**

**Reason**: Cannot operate without vision
- No cotton detection = no work to do
- Blind robot is dangerous
- Operator needs to know system is down

**Recommended Behavior**:
```
[ERROR] ❌ CRITICAL: Camera initialization failed!
[ERROR] Cannot operate in production mode without camera.
[ERROR] Please:
[ERROR]   1. Check camera USB connection
[ERROR]   2. Check camera power
[ERROR]   3. Run: depthai-viewer (to test camera)
[ERROR] 
[ERROR] Or set simulation_mode: true for testing without camera
[INFO] System shutting down...
```

---

## Error Handling Strategy by Component

### Camera (DepthAI)
```python
Priority: HIGH (but not critical in simulation)

Startup Check:
✅ Try to initialize camera
❌ If fails in production mode → STOP with error
⚠️  If fails in simulation mode → WARN and continue

Runtime Check:
⚠️  If camera drops during operation → WARN, try reconnect
❌ If reconnect fails 3 times → STOP
```

### Motors (ODrive/CAN)
```python
Priority: CRITICAL (always)

Startup Check:
✅ Initialize CAN bus
✅ Detect all motors
✅ Home all motors
❌ If any step fails → STOP immediately

Runtime Check:
✅ Every motion command checks response
❌ If motor doesn't respond → EMERGENCY STOP
⚠️  If position feedback missing → WARN (may continue if commands work)
```

### GPIO (End Effector/Compressor)
```python
Priority: MEDIUM (work continues without, but warn)

Startup Check:
✅ Try to initialize GPIO
⚠️  If fails → WARN (disable end effector features)
✅ Continue operation

Runtime Check:
⚠️  If GPIO command fails → WARN each time
✅ Continue (arm still moves, just no cotton collection)
```

---

## Recommended System Behavior

### 1. Startup Phase
```
[INFO] 🚀 Starting YanthraMove System...

[INFO] 📷 Initializing camera...
  ✅ Camera found: OAK-D
  ✅ Camera initialized successfully

[INFO] 🔧 Initializing motors...
  ✅ CAN bus initialized
  ✅ Motor 3 detected (ODrive 0x03)
  ✅ Motor 4 detected (ODrive 0x04)
  ✅ Motor 5 detected (ODrive 0x05)
  ✅ All motors homed successfully

[INFO] 🎮 Initializing GPIO...
  ✅ GPIO interface initialized
  ✅ End effector control ready
  ✅ Compressor control ready

[INFO] ✅ System ready for operation!
```

### 2. Startup Failure (Critical)
```
[INFO] 🚀 Starting YanthraMove System...

[INFO] 🔧 Initializing motors...
  ✅ CAN bus initialized
  ❌ ERROR: Motor 5 not responding on CAN ID 0x05

[ERROR] ❌ CRITICAL FAILURE: Motor initialization failed!
[ERROR] Cannot operate safely without all motors.
[ERROR] 
[ERROR] Troubleshooting:
[ERROR]   1. Check motor power supply
[ERROR]   2. Check CAN bus connections
[ERROR]   3. Verify ODrive firmware
[ERROR]   4. Run: candump can0 (to see CAN traffic)
[ERROR] 
[ERROR] System shutting down for safety...
```

### 3. Startup Failure (Non-Critical with Simulation)
```
[INFO] 🚀 Starting YanthraMove System...

[INFO] 📷 Initializing camera...
  ❌ ERROR: Camera initialization failed (USB device not found)

[WARN] ⚠️  Camera not available!
[INFO] Configuration: simulation_mode = true
[INFO] Continuing with simulated camera data...

[INFO] 🔧 Initializing motors...
  ✅ All motors ready

[INFO] ✅ System ready for SIMULATION mode!
[WARN] ⚠️  Production operation not possible without camera.
```

---

## Configuration Examples

### Production Mode (All Hardware Required)
```yaml
# config/production.yaml
yanthra_move:
  ros__parameters:
    simulation_mode: false    # Real hardware only
    enable_camera: true       # Camera required
    enable_gpio: true         # GPIO required
    
    # System will STOP if any critical hardware fails
```

### Development Mode (Allow Missing Hardware)
```yaml
# config/development.yaml
yanthra_move:
  ros__parameters:
    simulation_mode: true     # Allow simulation fallback
    enable_camera: true       # Try camera, but continue if missing
    enable_gpio: false        # Skip GPIO for testing
    
    # System will WARN but continue if hardware missing
```

### Simulation Mode (No Hardware)
```yaml
# config/simulation.yaml
yanthra_move:
  ros__parameters:
    simulation_mode: true     # Pure simulation
    enable_camera: false      # Don't try camera
    enable_gpio: false        # Don't try GPIO
    
    # System uses all simulated data
```

---

## Implementation Checklist

### ✅ Already Implemented:
- [x] GPIO graceful degradation (warns if fails, continues)
- [x] Motor homing checks (stops if homing fails)
- [x] Parameter validation (stops if config invalid)

### ⏳ Should Implement:
- [ ] Camera failure detection with mode-based handling
- [ ] Motor communication timeout detection
- [ ] Runtime motor health checks
- [ ] Graceful shutdown on critical failures
- [ ] Better error messages with troubleshooting steps

---

## Summary Table

| Component | Simulation Mode | Production Mode | Action on Failure |
|-----------|----------------|-----------------|-------------------|
| **Camera** | ⚠️ Warn, continue with sim data | ❌ Stop immediately | Show troubleshooting |
| **Motors** | ❌ Stop (critical even in sim) | ❌ Stop immediately | Emergency stop |
| **GPIO** | ⚠️ Warn, disable features | ⚠️ Warn, disable features | Continue without EE |
| **CAN Bus** | ❌ Stop (critical) | ❌ Stop immediately | Check connections |
| **Config** | ❌ Stop (critical) | ❌ Stop immediately | Fix YAML file |

---

## Your Specific Questions - Final Answers

1. **DepthAI errors OK?**
   - ✅ YES if `simulation_mode: true`
   - ❌ NO if `simulation_mode: false` (production)

2. **Continue if motors fail?**
   - ❌ NO - Always stop immediately (safety critical)

3. **Continue if camera disconnected online?**
   - ❌ NO - Stop with clear error message
   - Should prompt operator to fix camera or switch to simulation

4. **Parameter error?**
   - ✅ FIXED - Range now allows 0.1-10.0s (was 0.5-10.0s)
   - System will start now with 0.25s value
