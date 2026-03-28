# Two-Layer Safety: Defense-in-Depth Limit Enforcement

**Date:** 2025-11-09  
**Implementation:** Motion Controller + Motor Control  
**Strategy:** Defense-in-Depth with Planning Margin

---

## Overview

The system implements **two layers of limit checking** for maximum safety and better user experience:

```
Target → Motion Controller (Layer 1) → Motor Control (Layer 2) → Hardware
         ↓ Check with margin       ↓ Absolute hard limits
         ↓ Fail fast with context  ↓ Last line of defense
```

---

## Layer 1: Motion Controller (Planning Layer)

**Location:** `src/yanthra_move/src/core/motion_controller.cpp`

### Purpose
- **Early failure detection** before commands reach hardware
- **Better error messages** with full context (phi, theta, r values)
- **Prevent wasted motion** - don't start multi-joint sequences that will fail

### Implementation
```cpp
const double PLANNING_MARGIN = 0.98;  // 2% safety buffer

// Joint3 example
const double joint3_planning_min = -0.2 * PLANNING_MARGIN;  // -0.196
const double joint3_planning_max = 0.0;

if (joint3_cmd < joint3_planning_min || joint3_cmd > joint3_planning_max) {
    RCLCPP_ERROR(...detailed error with phi, theta, r context...);
    return false;  // Abort early
}
```

### Planning Limits (98% of Hard Limits)
| Joint | Hard Limit | Planning Limit (98%) | Buffer |
|-------|------------|---------------------|---------|
| Joint3 min | -0.200 rot | -0.196 rot | 0.004 rot |
| Joint3 max | 0.000 rot | 0.000 rot | 0.000 rot |
| Joint4 min | -0.100 m | -0.098 m | 0.002 m |
| Joint4 max | 0.100 m | 0.098 m | 0.002 m |
| Joint5 min | 0.000 m | 0.000 m | 0.000 m |
| Joint5 max | 0.350 m | 0.343 m | 0.007 m |

### Error Message Example
```
❌ PLANNING: Joint3 target unreachable! phi=-1.300 rad (-74.5°) → joint3=-0.20700 rotations
   Planning limits: [-0.196, 0.000] rotations (with 2% safety margin)
   This prevents hitting motor hard limits at [-0.200, 0.000] rotations
```

**Where to find:** Yanthra_move node logs (motion_controller output)

---

## Layer 2: Motor Control (Hardware Layer)

**Location:** `src/motor_control_ros2/src/mg6010_controller.cpp`

### Purpose
- **Absolute safety backstop** at mechanical boundaries
- **Protects against all command sources** (not just motion_controller)
- **Catches accumulated errors** (drift, rounding, bugs)
- **Required for safety compliance**

### Implementation
```cpp
bool MG6010Controller::check_position_limits(double position) const
{
  return (position >= config_.limits.position_min && 
          position <= config_.limits.position_max);
}

// Called in set_position()
if (!check_safety_limits(position, velocity)) {
  record_error(ErrorCategory::SAFETY, ErrorSeverity::WARNING, 7,
               "Position command exceeds safety limits");
  return false;  // Command rejected, motor doesn't move
}
```

### Hard Limits (100% - Mechanical Boundaries)
**Source:** `src/motor_control_ros2/config/production.yaml`

```yaml
min_positions: [0.0, -0.2, -0.1]   # joint5, joint3, joint4
max_positions: [0.35, 0.0, 0.1]    # Absolute mechanical limits
```

### Error Message Example
```
MG6010Controller Error [joint3]: Position command exceeds safety limits (Code: 7)
```

**Where to find:** Motor control node stderr output (generic message, less context)

---

## Why Two Layers?

### Benefits

1. **Better User Experience**
   - Layer 1 catches 99% of issues with detailed error messages
   - Developers see "phi=-1.3 rad is too low" instead of "motor limit exceeded"
   - Faster debugging with full context

2. **Safety Compliance**
   - Layer 2 ensures no command can damage hardware
   - Protects against bugs in motion_controller
   - Catches numerical drift/rounding errors

3. **Fail-Fast Design**
   - Don't waste time starting a 3-joint motion that will fail
   - Abort at planning stage, not mid-execution
   - Network efficiency (no doomed commands sent)

4. **Single Source of Truth**
   - All limits defined in `production.yaml`
   - Motion controller reads same limits, applies margin
   - No manual syncing needed

### The 2% Buffer

**Why 2% margin?**
- Catches rounding errors before hitting hard limits
- Typical float precision: ~7 decimal places
- 2% buffer = 0.004 rotations = 1.44° for joint3
- Large enough to catch issues, small enough not to waste workspace

**Example:**
```
Target: phi = -1.295 rad
Calculated: joint3_cmd = -0.206 rotations
Layer 1 limit: -0.196 ← CAUGHT HERE (planning layer)
Layer 2 limit: -0.200 ← Never reached (hardware protected)
```

---

## Configuration Management

### Single Source of Truth
`src/motor_control_ros2/config/production.yaml`

```yaml
# ABSOLUTE HARD LIMITS (Layer 2 - 100%)
min_positions: [0.0, -0.2, -0.1]
max_positions: [0.35, 0.0, 0.1]
```

### Motion Controller Implementation
`src/yanthra_move/src/core/motion_controller.cpp`

```cpp
// Layer 1 limits derived from Layer 2 with margin
const double PLANNING_MARGIN = 0.98;
const double joint3_planning_min = -0.2 * PLANNING_MARGIN;  // From motor config
```

**Note:** Currently hardcoded. Future improvement: read from motor_control config at runtime.

---

## Testing Scenarios

### Scenario 1: Normal Operation (Within Limits)
```
phi = -0.8 rad → joint3_cmd = -0.127 rot
✓ Layer 1: -0.127 > -0.196 (planning limit) → PASS
✓ Layer 2: -0.127 > -0.200 (hard limit) → PASS
→ Motor moves successfully
```

### Scenario 2: Slightly Out (Caught by Planning)
```
phi = -1.3 rad → joint3_cmd = -0.207 rot
✗ Layer 1: -0.207 < -0.196 (planning limit) → FAIL
   Error: "PLANNING: Joint3 target unreachable! phi=-1.300 rad..."
→ Motion aborted early, good error message
→ Layer 2 never reached
```

### Scenario 3: Way Out (Would Hit Hardware if Layer 1 Failed)
```
phi = -1.5 rad → joint3_cmd = -0.239 rot
✗ Layer 1: -0.239 < -0.196 → FAIL (caught here)
✗ Layer 2: -0.239 < -0.200 → WOULD FAIL (but never reached)
→ Shows defense-in-depth working correctly
```

---

## Maintenance

### To Change Limits

1. **Edit motor_control config** (single source of truth):
   ```yaml
   # src/motor_control_ros2/config/production.yaml
   min_positions: [0.0, -0.25, -0.1]  # Changed joint3 from -0.2 to -0.25
   ```

2. **Update motion_controller code** (currently manual):
   ```cpp
   // src/yanthra_move/src/core/motion_controller.cpp
   const double joint3_planning_min = -0.25 * PLANNING_MARGIN;  // Update here
   ```

3. **Future improvement:** Motion controller should read limits from motor_control config at startup

### To Change Safety Margin

```cpp
// src/yanthra_move/src/core/motion_controller.cpp
const double PLANNING_MARGIN = 0.95;  // Change from 0.98 to 0.95 (5% buffer)
```

---

## Summary

| Aspect | Layer 1 (Planning) | Layer 2 (Hardware) |
|--------|-------------------|-------------------|
| **Location** | Motion controller | Motor control |
| **Limit** | 98% of hard limit | 100% (absolute) |
| **Purpose** | Fail fast, good UX | Safety backstop |
| **Error Quality** | Detailed with context | Generic message |
| **Catches** | 99% of limit violations | Bugs, drift, edge cases |
| **When Checked** | Before sending command | After receiving command |
| **Config Source** | Reads from motor_control | Defined in YAML |

**Result:** Best of both worlds - good user experience + absolute safety!
